"""TC-SYNC-08 手动触发与权限矩阵 + semantic_sync 任务类型端到端（inline worker）。

- POST /api/orgs/{org}/semantic/sync/{adapter}：semantic:admin（org_admin 兼任，
  design §6.2/§6.3）→ 202 + outbox；普通成员 403；
- GET /semantic/builds · sync-runs：org_admin 可见、普通成员 403（design §6.2
  L1143——两查询端点同 semantic:admin）；
- 端到端：手动触发 → inline worker 执行 → sync-runs 可查（run succeeded + 统计）。
"""

from __future__ import annotations

import json

import pytest

from fake_semantic import tpl_snapshot
from helpers import seed_membership, seed_org, seed_user

ORG = "org:tax"
ORG_GL = "org:gl"

SNAPSHOT = tpl_snapshot(5)


@pytest.fixture()
def sem_app(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.adapters import ADAPTER_FACTORIES
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect
    from fake_providers import FakeEmbedder

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=2560,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
        worker_poll_s=0.2,  # P2-2/R2：兜底循环认领测试需要短轮询
        semantic_sources_json=json.dumps(
            {ORG: {"template_center": {"endpoint": "http://fake/tc"}}}),
    )
    embedder = FakeEmbedder(dim=2560)
    gate = EmbeddingGate()
    app = create_app(settings, embedder=embedder, gate=gate, run_startup_probe=False)

    # fake 适配器工厂注入（inline worker 同进程——registry 经 build_adapter 消费）
    from fake_semantic import FakeSourceAdapter

    monkeypatch.setitem(
        ADAPTER_FACTORIES, "template_center",
        lambda org, cfg: FakeSourceAdapter("template_center", SNAPSHOT),
    )

    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    for uid in ("u_full", "admin_tax"):
        seed_user(conn, uid)
    seed_membership(conn, "u_full", ORG)
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    static = {
        "u_full": "dev-static-u-full",
        "admin_tax": "dev-static-admin-tax",
    }
    for uid, token in static.items():
        conn.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                     (hash_token(token), uid))
    conn.commit()

    with TestClient(app) as client:
        yield {"client": client, "conn": conn, "settings": settings, "static": static}
    conn.close()


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- TC-SYNC-08 手动触发与权限矩阵 ----


def test_tc_sync_08_trigger_permission_matrix(sem_app) -> None:
    client, conn = sem_app["client"], sem_app["conn"]
    admin = sem_app["static"]["admin_tax"]
    member = sem_app["static"]["u_full"]

    # ② 普通成员：403（semantic:admin——org_admin 兼任）且零任务行
    resp = client.post(f"/api/orgs/{ORG}/semantic/sync/template_center",
                       headers=_h(member))
    assert resp.status_code == 403
    assert conn.execute(
        "SELECT count(*) FROM tasks WHERE type = 'semantic_sync'"
    ).fetchone()[0] == 0

    # 未知适配器 → 404
    resp = client.post(f"/api/orgs/{ORG}/semantic/sync/nope", headers=_h(admin))
    assert resp.status_code == 404

    # ① org_admin：202 + 任务标识 + outbox 留痕 + 任务行 payload
    resp = client.post(f"/api/orgs/{ORG}/semantic/sync/template_center",
                       headers=_h(admin))
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued" and body["task_id"]
    task = conn.execute(
        "SELECT type, payload FROM tasks WHERE id = ?", (body["task_id"],)
    ).fetchone()
    assert task[0] == "semantic_sync"
    assert json.loads(task[1]) == {"org": ORG, "adapter": "template_center",
                                   "force": False}  # B2 起 payload 恒带 force 键
    events = conn.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = 'semantic.sync'"
    ).fetchall()
    assert any(json.loads(p)["phase"] == "triggered" for (p,) in events)

    # ③ 查询端点：org_admin 可见、普通成员 403
    assert client.get(f"/api/orgs/{ORG}/semantic/sync-runs",
                      headers=_h(admin)).status_code == 200
    assert client.get(f"/api/orgs/{ORG}/semantic/builds",
                      headers=_h(admin)).status_code == 200
    assert client.get(f"/api/orgs/{ORG}/semantic/sync-runs",
                      headers=_h(member)).status_code == 403
    assert client.get(f"/api/orgs/{ORG}/semantic/builds",
                      headers=_h(member)).status_code == 403


def test_builds_endpoint_empty_list_this_segment(sem_app) -> None:
    """builds 本段恒空列表（构建接入归 m2s-2）。"""
    resp = sem_app["client"].get(
        f"/api/orgs/{ORG}/semantic/builds", headers=_h(sem_app["static"]["admin_tax"]))
    assert resp.status_code == 200
    assert resp.json() == {"builds": []}


# ---- semantic_sync 任务类型端到端（手动触发 → worker 执行 → sync-runs 可查） ----


def test_semantic_sync_e2e_inline_worker(sem_app) -> None:
    client, conn = sem_app["client"], sem_app["conn"]
    admin = sem_app["static"]["admin_tax"]

    resp = client.post(f"/api/orgs/{ORG}/semantic/sync/template_center",
                       headers=_h(admin))
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    # inline worker 执行（kick 同步消化 / 兜底循环线程并发认领——轮询至终态）
    task = _wait_task_status(conn, task_id, "done")
    assert task[0] == "done", f"semantic_sync task not done: {task}"

    # sync-runs 可查：run succeeded、实体与别名已落库
    resp = client.get(f"/api/orgs/{ORG}/semantic/sync-runs", headers=_h(admin))
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["adapter"] == "template_center"
    stats = runs[0]["stats_json"]
    assert isinstance(stats, dict) and stats.get("inserted", 0) > 0
    assert conn.execute("SELECT count(*) FROM sem_entities").fetchone()[0] > 0
    assert conn.execute("SELECT count(*) FROM sem_aliases").fetchone()[0] > 0
    # semantic.sync 完成事件（run 侧——phase 无 = worker 执行完成）
    events = conn.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = 'semantic.sync'"
    ).fetchall()
    assert any(json.loads(p).get("run_id") for (p,) in events)


# ---- P2-2：inline 兜底循环认领 semantic_sync（kick 唤醒丢失的兜底通道） ----


def test_p2_2_inline_fallback_loop_claims_semantic_sync(sem_app) -> None:
    """预置 pending semantic_sync 任务（不经 POST/kick——模拟 kick 唤醒丢失），
    兜底循环 wake 后即时认领执行至 done（防永久滞留 pending）。"""
    import time

    client, conn = sem_app["client"], sem_app["conn"]
    handle = client.app.state.worker
    backend = client.app.state.service.backend
    tid = backend.create_task(
        None, task_type="semantic_sync",
        payload=json.dumps({"org": ORG, "adapter": "template_center"}),
    )
    handle.wake()  # 唤醒兜底循环（不 kick——兜底路径自身须能消化）
    for _ in range(50):  # ≤10s（poll 0.2s）
        row = conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (tid,)
        ).fetchone()
        if row and row[0] == "done":
            break
        time.sleep(0.2)
    assert row[0] == "done", f"semantic_sync 未被兜底循环认领: {row}"
    assert conn.execute(
        "SELECT count(*) FROM sem_sync_runs WHERE status = 'succeeded'"
    ).fetchone()[0] == 1


# ---- B2：force 触发端到端（运维放行经 REST → 任务 payload → run stats） ----


def _wait_task_status(conn, tid: str, status: str, tries: int = 50) -> tuple:
    """轮询至任务终态（兜底循环线程被前序用例唤醒后与 kick 并发认领——
    执行体异线程，任务态到达有毫秒级窗口）。"""
    import time

    row = None
    for _ in range(tries):
        row = conn.execute(
            "SELECT status, payload, error FROM tasks WHERE id = ?", (tid,)
        ).fetchone()
        if row and row[0] == status:
            return row
        time.sleep(0.2)
    return row


def test_b2_force_trigger_e2e(sem_app) -> None:
    client, conn = sem_app["client"], sem_app["conn"]
    admin = sem_app["static"]["admin_tax"]

    resp = client.post(f"/api/orgs/{ORG}/semantic/sync/template_center?force=true",
                       headers=_h(admin))
    assert resp.status_code == 202
    body = resp.json()
    assert body["forced"] is True
    task = _wait_task_status(conn, body["task_id"], "done")
    assert task[0] == "done", f"force semantic_sync task not done: {task}"
    assert json.loads(task[1])["force"] is True
    run = conn.execute(
        "SELECT status, stats_json FROM sem_sync_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert run[0] == "succeeded"
    assert json.loads(run[1])["forced"] is True
    # 触发事件记 forced
    events = conn.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = 'semantic.sync'"
    ).fetchall()
    assert any(json.loads(p)["phase"] == "triggered" and json.loads(p)["forced"]
               for (p,) in events)
    # 无 force（默认）行为不变：payload.force=False、stats.forced=False
    resp2 = client.post(f"/api/orgs/{ORG}/semantic/sync/template_center",
                        headers=_h(admin))
    assert resp2.status_code == 202 and resp2.json()["forced"] is False
    task2 = _wait_task_status(conn, resp2.json()["task_id"], "done")
    assert json.loads(task2[1]) == {"org": ORG, "adapter": "template_center",
                                    "force": False}


# ---- P3-7：触发端点配置 fail-fast（未配置/畸形 → 400，非 202 后无声失败） ----


def test_p3_7_trigger_fails_fast_when_source_unconfigured(tmp_path) -> None:
    """无工厂覆盖 + 未配置该 org 源 → 400（fail-fast）；不产生任务行/outbox。"""
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect
    from fake_providers import FakeEmbedder
    from helpers import seed_membership, seed_user

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=2560,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
    )  # 无 LATTICE_SEM_SOURCES_JSON / 无工厂覆盖
    app = create_app(settings, embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
                     run_startup_probe=False)
    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    seed_user(conn, "admin_x")
    seed_membership(conn, "admin_x", ORG, role="org_admin")
    token = "dev-static-admin-x"
    conn.execute("UPDATE users SET token_hash = ? WHERE id = 'admin_x'",
                 (hash_token(token),))
    conn.commit()
    try:
        with TestClient(app) as client:
            resp = client.post(f"/api/orgs/{ORG}/semantic/sync/template_center",
                               headers=_h(token))
            assert resp.status_code == 400
            assert "not configured" in resp.json()["detail"]
            assert conn.execute(
                "SELECT count(*) FROM tasks WHERE type = 'semantic_sync'"
            ).fetchone()[0] == 0  # 无任务行
            assert conn.execute(
                "SELECT count(*) FROM audit_outbox WHERE event_type = 'semantic.sync'"
            ).fetchone()[0] == 0  # 无 outbox
    finally:
        conn.close()


# ---- P3-6⑤：TC-TASK-06① 故障隔离——semantic_sync 适配器故障不阻断 docs 检索 ----


def test_p3_6_semantic_failure_does_not_block_docs_search(sem_app, monkeypatch) -> None:
    """适配器 fetch 抛错 → semantic_sync 任务 failed（error 留痕）；docs 检索
    端点仍可用（语义轨道故障不外溢——TC-TASK-06①①半句）。"""
    import time

    from knowledge_lattice.core.semantic.adapters import ADAPTER_FACTORIES
    from fake_semantic import FakeSourceAdapter

    client, conn = sem_app["client"], sem_app["conn"]
    admin = sem_app["static"]["admin_tax"]

    class ExplodingAdapter(FakeSourceAdapter):
        def fetch(self, org):
            raise RuntimeError("source system unreachable (simulated)")

    monkeypatch.setitem(
        ADAPTER_FACTORIES, "template_center",
        lambda org, cfg: ExplodingAdapter("template_center", []),
    )
    resp = client.post(f"/api/orgs/{ORG}/semantic/sync/template_center",
                       headers=_h(admin))
    assert resp.status_code == 202
    tid = resp.json()["task_id"]
    for _ in range(50):
        row = conn.execute("SELECT status, error FROM tasks WHERE id = ?", (tid,)).fetchone()
        if row and row[0] == "failed":
            break
        time.sleep(0.2)
    assert row[0] == "failed" and "unreachable" in (row[1] or "")
    # run 侧 failed + 审计事件（重试预算内 3 次尝试 → ≥1 条 failed run 行）
    assert conn.execute(
        "SELECT count(*) FROM sem_sync_runs WHERE status = 'failed'"
    ).fetchone()[0] >= 1

    # docs 检索仍可用（故障隔离——语义任务失败不阻断文档域）
    resp = client.post("/api/search", headers={**_h(admin), "X-Org-Id": ORG},
                       json={"query": "增值税"})
    assert resp.status_code == 200
    assert "results" in resp.json() or "query" in resp.json()
