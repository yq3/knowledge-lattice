"""TC-TASK-04 子进程隔离【集成｜M2】——OOM 只杀 worker、主进程检索可用、自动拉起。

真实 subprocess 形态（design §2 部署图）：Settings(worker_mode="subprocess")
经 create_app → lifespan 拉起 worker 子进程；经 LATTICE_WORKER_SERVICES 工厂注入 fake 栈与
崩溃桩（见 tests/m2_worker_services.py——跨进程无法传对象，import 钩子注入）。

链路：上传崩溃文档（executor 内 SIGKILL 自杀——OOM killer 信号形态）→
① 仅 worker 子进程死亡（主进程存活）；② 主进程检索 REST 全程 200 可用；
③ supervisor 自动拉起新 worker；④ 重启后的 worker 完成后续正常任务。
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest

PAYLOAD = ("<html><body><h1>印花税税率表</h1><p>借款合同按借款金额万分之零点五贴花。</p></body></html>").encode()


@pytest.fixture()
def subprocess_app(tmp_path, monkeypatch):
    """subprocess worker 形态 app（sqlite + fake 服务工厂 + 崩溃标志文件）。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from fake_providers import FakeEmbedder

    crash_flag = tmp_path / "crash_flag"
    monkeypatch.setenv("LATTICE_WORKER_SERVICES", "m2_worker_services:build_services")
    monkeypatch.setenv("LATTICE_TEST_CRASH_FLAG", str(crash_flag))
    tests_dir = str(Path(__file__).resolve().parent)
    monkeypatch.setenv(
        "PYTHONPATH", tests_dir + os.pathsep + os.environ.get("PYTHONPATH", "")
    )
    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        embed_model="fake-embed",  # P3-9：与 worker fake 标签对齐——向量路真实验证
        probe_interval_s=0, maintenance_interval_s=0,
        worker_mode="subprocess", worker_lease_s=2.0, worker_poll_s=0.3,
        worker_heartbeat_s=0.5, worker_startup_probe=False,
        worker_restart_backoff_s=0.5,
    )
    app = create_app(
        settings, embedder=FakeEmbedder(dim=8), gate=EmbeddingGate(),
        run_startup_probe=False,
    )
    return {"app": app, "settings": settings, "crash_flag": crash_flag}


def _seed(client_factory, app) -> None:
    """org:tax 造数（helpers 种子函数——与各服务壳测试同款）。"""
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect
    from helpers import (
        seed_dataset,
        seed_dim_value,
        seed_dimension,
        seed_grant,
        seed_membership,
        seed_org,
        seed_user,
    )

    conn = connect(app.state.service.settings.db_path)
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
    conn.close()


def test_worker_oom_isolation_main_survives_and_restarts(subprocess_app) -> None:
    from fastapi.testclient import TestClient

    app = subprocess_app["app"]
    settings = subprocess_app["settings"]
    with TestClient(app) as client:
        _seed(None, app)
        supervisor = app.state.worker._supervisor
        first_pid = supervisor.proc.pid
        assert supervisor.proc.poll() is None, "worker 子进程应已拉起"

        headers = {"Authorization": "Bearer dev-static-u-full"}
        # 崩溃任务：正常上传（首传）→ 以返回的 doc_id 指认崩溃标志 → worker 认领
        # 即自杀（SIGKILL——OOM 信号形态）
        service = app.state.service
        doc_id, task_id = service.ingest.create_document(
            org_id="org:tax", dataset_id="ds:vat_lib",
            title="crash", dims={"region": ["CN"]}, owner_user_id="u_full",
            file_bytes=PAYLOAD, mime_type="text/html", filename="crash.html",
        )
        subprocess_app["crash_flag"].write_text(doc_id, encoding="utf-8")
        supervisor.notify()  # IPC 唤醒（双通道的快通道）

        # ① 仅 worker 子进程死亡（SIGKILL——OOM 形态）
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if supervisor.proc.poll() is not None:
                break
            time.sleep(0.1)
        assert supervisor.proc.poll() is not None, "worker 未在窗口内死亡（崩溃桩未触发？）"

        # ② 主进程检索可用（检索面 200——空结果也是可用）
        resp = client.post(
            "/api/search", json={"query": "印花税", "top_k": 5},
            headers={**headers, "X-Org-Id": "org:tax"},
        )
        assert resp.status_code == 200
        assert resp.json()["results"] == []  # 尚无可搜内容

        # ③ supervisor 自动拉起（新 pid）
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            proc = supervisor.proc
            if proc is not None and proc.poll() is None and proc.pid != first_pid:
                break
            time.sleep(0.1)
        proc = supervisor.proc
        assert proc is not None and proc.poll() is None and proc.pid != first_pid, \
            "worker 未自动拉起"

        # ④ 重启后的 worker 完成正常任务（正常上传 → searchable_full）
        resp = client.post(
            "/api/orgs/org:tax/documents",
            headers=headers,
            files={"file": ("normal.html", PAYLOAD, "text/html")},
            data={"dataset": "ds:vat_lib", "dims": '{"region": ["CN"]}', "title": "normal"},
        )
        assert resp.status_code == 202
        body = resp.json()
        deadline = time.monotonic() + 30
        doc = None
        while time.monotonic() < deadline:
            doc = client.get(
                f"/api/orgs/org:tax/documents/{body['doc_id']}", headers=headers
            ).json()
            if doc.get("active_status") == "searchable_full":
                break
            time.sleep(0.2)
        assert doc is not None and doc["active_status"] == "searchable_full", \
            f"重启后 worker 未完成正常任务（doc={doc}）"
        # 主进程检索恢复命中（重启 worker 的劳动成果可见）
        resp = client.post(
            "/api/search", json={"query": "印花税", "top_k": 5},
            headers={**headers, "X-Org-Id": "org:tax"},
        )
        assert resp.status_code == 200
        assert resp.json()["results"], "主进程应能检索到已完成文档"
