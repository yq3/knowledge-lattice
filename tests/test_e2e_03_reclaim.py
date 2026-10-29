"""TC-E2E-03 任务租约重认领【集成｜M2（杀进程演练）】。

M2 半句：真实 kill -9 运行中的 worker 子进程 → 任务滞留 leased（租约未过期
不可抢）→ supervisor 自动拉起新 worker → 租约过期（2s 测试注入）→ 新 worker
重认领续跑（attempts 递增、断点=阶段——慢执行桩一次性，重认领后直跑完成）→
文档可达 searchable_full。「杀 worker 不丢任务」验收的测试化（design §8 M2.6）。

机制半句（造数 lease_until 过期重认领）在 test_task_01_lease（双后端）承载。
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

import pytest

PAYLOAD = ("<html><body><h1>消费税申报</h1><p>委托加工收回的应税消费品连续生产。</p></body></html>").encode()


@pytest.fixture()
def reclaim_app(tmp_path, monkeypatch):
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from fake_providers import FakeEmbedder

    slow_flag = tmp_path / "slow_flag"
    monkeypatch.setenv("LATTICE_WORKER_SERVICES", "m2_worker_services:build_services")
    monkeypatch.setenv("LATTICE_TEST_SLOW_FLAG", str(slow_flag))
    monkeypatch.setenv("LATTICE_TEST_SLOW_S", "6")  # 制造 kill -9 窗口
    tests_dir = str(Path(__file__).resolve().parent)
    monkeypatch.setenv(
        "PYTHONPATH", tests_dir + os.pathsep + os.environ.get("PYTHONPATH", "")
    )
    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        embed_model="fake-embed",  # P3-9：与 worker fake 标签对齐——向量路真实验证
        probe_interval_s=0, maintenance_interval_s=0,
        worker_mode="subprocess", worker_lease_s=2.0, worker_poll_s=0.3,
        worker_heartbeat_s=1.0, worker_startup_probe=False,
        worker_restart_backoff_s=0.5,
    )
    app = create_app(
        settings, embedder=FakeEmbedder(dim=8), gate=EmbeddingGate(),
        run_startup_probe=False,
    )
    return {"app": app, "settings": settings, "slow_flag": slow_flag}


def test_kill_worker_lease_reclaim_completes(reclaim_app) -> None:
    from fastapi.testclient import TestClient
    from helpers import (
        seed_dataset,
        seed_dim_value,
        seed_dimension,
        seed_grant,
        seed_membership,
        seed_org,
        seed_user,
    )
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect

    app = reclaim_app["app"]
    settings = reclaim_app["settings"]
    with TestClient(app) as client:
        conn = connect(settings.db_path)
        seed_org(conn)
        seed_dataset(conn, ds_id="ds:vat_lib")
        dim_id = seed_dimension(conn)
        val_id = seed_dim_value(conn, dim_id)
        seed_user(conn, "u_full")
        seed_membership(conn, "u_full")
        seed_grant(conn, user_id="u_full", dim_id=dim_id, val_id=val_id)
        conn.execute(
            "UPDATE users SET token_hash = ? WHERE id = 'u_full'",
            (hash_token("dev-static-u-full"),),
        )
        conn.commit()

        supervisor = app.state.worker._supervisor
        headers = {"Authorization": "Bearer dev-static-u-full"}
        resp = client.post(
            "/api/orgs/org:tax/documents",
            headers=headers,
            files={"file": ("kill.html", PAYLOAD, "text/html")},
            data={"dataset": "ds:vat_lib", "dims": '{"region": ["CN"]}', "title": "kill"},
        )
        assert resp.status_code == 202
        body = resp.json()
        doc_id, task_id = body["doc_id"], body["task_id"]
        # 慢执行指认：worker 认领后 sleep 6s——制造 running 窗口
        reclaim_app["slow_flag"].write_text(doc_id, encoding="utf-8")
        supervisor.notify()

        # 等 worker 认领（running + lease/heartbeat 落位）
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            row = conn.execute(
                "SELECT status, lease_owner, heartbeat_at FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if row and row[0] == "running" and row[1]:
                break
            time.sleep(0.1)
        assert row is not None and row[0] == "running" and row[1], \
            f"worker 未认领任务（row={row}）"

        # kill -9 运行中的 worker（OOM/人工杀进程的真实信号形态）
        victim_pid = supervisor.proc.pid
        supervisor.proc.send_signal(signal.SIGKILL)
        supervisor.proc.wait(timeout=10)
        # 任务滞留 leased/running（租约未过期——他人不可抢，不双跑）
        row = conn.execute(
            "SELECT status, attempts FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        assert row[0] in ("leased", "running") and row[1] == 1

        # supervisor 自动拉起新 worker（TC-TASK-04 联动）
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            proc = supervisor.proc
            if proc is not None and proc.poll() is None and proc.pid != victim_pid:
                break
            time.sleep(0.1)
        assert supervisor.proc.poll() is None and supervisor.proc.pid != victim_pid

        # 租约过期（2s）→ 新 worker 兜底轮询重认领续跑 → searchable_full
        deadline = time.monotonic() + 40
        final = None
        while time.monotonic() < deadline:
            final = conn.execute(
                "SELECT status, attempts, error FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            doc = client.get(
                f"/api/orgs/org:tax/documents/{doc_id}", headers=headers
            ).json()
            if final[0] in ("done", "failed") or doc.get("active_status") == "searchable_full":
                break
            time.sleep(0.2)
        doc = client.get(f"/api/orgs/org:tax/documents/{doc_id}", headers=headers).json()
        assert final is not None and final[0] == "done", \
            f"重认领未完成（task={final}）"
        assert final[1] == 2  # attempts 递增（TC-E2E-03 预期）
        assert doc["active_status"] == "searchable_full"  # 文档可达 full
        # 主进程检索面命中（杀 worker 不丢任务——成果可见）
        hits = client.post(
            "/api/search", json={"query": "委托加工 应税消费品", "top_k": 5},
            headers={**headers, "X-Org-Id": "org:tax"},
        )
        assert hits.status_code == 200 and hits.json()["results"]
        conn.close()
