"""semantic_build 任务类型 + REST 管理端点（POST/GET /semantic/builds）端到端。

- POST /api/orgs/{org}/semantic/builds：semantic:admin → 202 + semantic_build
  任务行（payload {org}）+ outbox 留痕；普通成员 403 零任务行；
- GET /semantic/builds：列表 + 当前（current=最新 ready）；GET /{id} 明细、
  未知/他组织 404；
- inline 兜底循环认领 semantic_build（m2s-1 P2-2 教训——新任务类型必进 _loop）；
- 同步成功后自动投递构建任务（design §5.8「同步或 YAML 合并后触发」）。
"""

from __future__ import annotations

import json
import time

import pytest

from fake_semantic import tpl_snapshot
from helpers import seed_membership, seed_org, seed_user

ORG = "org:tax"

SNAPSHOT = tpl_snapshot(4)


@pytest.fixture()
def build_app(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.adapters import ADAPTER_FACTORIES
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect
    from fake_providers import FakeEmbedder
    from fake_semantic import FakeSourceAdapter

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=2560,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
        worker_poll_s=0.2,
        semantic_sources_json=json.dumps(
            {ORG: {"template_center": {"endpoint": "http://fake/tc"}}}),
    )
    app = create_app(settings, embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
                     run_startup_probe=False)
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
    static = {"u_full": "dev-static-u-full", "admin_tax": "dev-static-admin-tax"}
    for uid, token in static.items():
        conn.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                     (hash_token(token), uid))
    conn.commit()

    with TestClient(app) as client:
        yield {"client": client, "conn": conn, "settings": settings, "static": static}
    conn.close()


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _wait_task_status(conn, tid: str, status: str, tries: int = 50) -> tuple:
    row = None
    for _ in range(tries):
        row = conn.execute(
            "SELECT status, payload FROM tasks WHERE id = ?", (tid,)
        ).fetchone()
        if row and row[0] == status:
            return row
        time.sleep(0.2)
    return row


# ---- POST /semantic/builds：触发与权限 ----


def test_post_builds_permission_and_task_row(build_app) -> None:
    client, conn = build_app["client"], build_app["conn"]
    admin = build_app["static"]["admin_tax"]
    member = build_app["static"]["u_full"]

    # 普通成员 403 且零任务行
    resp = client.post(f"/api/orgs/{ORG}/semantic/builds", headers=_h(member))
    assert resp.status_code == 403
    assert conn.execute(
        "SELECT count(*) FROM tasks WHERE type = 'semantic_build'"
    ).fetchone()[0] == 0

    # org_admin：202 + 任务行 payload {org} + outbox 触发留痕
    resp = client.post(f"/api/orgs/{ORG}/semantic/builds", headers=_h(admin))
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued" and body["task_id"] and body["org"] == ORG
    task = conn.execute(
        "SELECT type, payload FROM tasks WHERE id = ?", (body["task_id"],)
    ).fetchone()
    assert task[0] == "semantic_build"
    assert json.loads(task[1]) == {"org": ORG}
    events = conn.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = 'semantic.build'"
    ).fetchall()
    triggered = [json.loads(p) for (p,) in events
                 if json.loads(p).get("phase") == "triggered"]
    assert triggered and triggered[0]["task_id"] == body["task_id"]


def test_builds_e2e_trigger_to_ready(build_app) -> None:
    """POST 构建 → inline worker 执行 → 列表 + 当前 + 明细可查（REST 三件套）。"""
    client, conn = build_app["client"], build_app["conn"]
    admin = build_app["static"]["admin_tax"]

    # 先同步一份实体（空库构建=合法但无内容——本用例要断言 stats 内容）
    resp = client.post(f"/api/orgs/{ORG}/semantic/sync/template_center",
                       headers=_h(admin))
    assert resp.status_code == 202
    sync_done = _wait_task_status(conn, resp.json()["task_id"], "done")
    assert sync_done[0] == "done"

    resp = client.post(f"/api/orgs/{ORG}/semantic/builds", headers=_h(admin))
    assert resp.status_code == 202
    build_task = resp.json()["task_id"]
    done = _wait_task_status(conn, build_task, "done")
    assert done[0] == "done", f"semantic_build task not done: {done}"

    rows = client.get(f"/api/orgs/{ORG}/semantic/builds", headers=_h(admin)).json()
    assert rows["current"] is not None
    assert rows["current"]["status"] == "ready"
    assert [b["id"] for b in rows["builds"]] == [rows["current"]["id"]]
    stats = rows["current"]["stats_json"]
    assert isinstance(stats, dict) and stats.get("entities", 0) > 0

    detail = client.get(
        f"/api/orgs/{ORG}/semantic/builds/{rows['current']['id']}",
        headers=_h(admin)).json()
    assert detail["id"] == rows["current"]["id"]
    assert detail["dict_rev"] == rows["current"]["dict_rev"]

    # 未知 id → 404
    assert client.get(f"/api/orgs/{ORG}/semantic/builds/99999",
                      headers=_h(admin)).status_code == 404
    # 普通成员查询 403（semantic:admin）
    assert client.get(f"/api/orgs/{ORG}/semantic/builds",
                      headers=_h(build_app["static"]["u_full"])).status_code == 403


def test_builds_list_filters(build_app) -> None:
    """列表 status 过滤 + limit 管理语义（design §6.2 构建记录端点）。"""
    client, conn = build_app["client"], build_app["conn"]
    admin = build_app["static"]["admin_tax"]
    client.post(f"/api/orgs/{ORG}/semantic/sync/template_center", headers=_h(admin))
    _wait_task_status(conn, _latest_task(conn, "semantic_sync"), "done")

    resp = client.post(f"/api/orgs/{ORG}/semantic/builds", headers=_h(admin))
    _wait_task_status(conn, resp.json()["task_id"], "done")

    body = client.get(f"/api/orgs/{ORG}/semantic/builds?status=ready",
                      headers=_h(admin)).json()
    assert body["builds"] and all(b["status"] == "ready" for b in body["builds"])
    body = client.get(f"/api/orgs/{ORG}/semantic/builds?status=failed",
                      headers=_h(admin)).json()
    assert body["builds"] == []
    # 非法 status → 400
    assert client.get(f"/api/orgs/{ORG}/semantic/builds?status=nope",
                      headers=_h(admin)).status_code == 400


def _latest_task(conn, task_type: str) -> str:
    return conn.execute(
        "SELECT id FROM tasks WHERE type = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (task_type,),
    ).fetchone()[0]


# ---- inline 兜底循环认领 semantic_build（m2s-1 P2-2 教训） ----


def test_inline_fallback_loop_claims_semantic_build(build_app) -> None:
    """预置 pending semantic_build（不经 POST/kick——模拟唤醒丢失）→ 兜底循环
    wake 后即时认领执行至 done。"""
    client, conn = build_app["client"], build_app["conn"]
    handle = client.app.state.worker
    backend = client.app.state.service.backend
    tid = backend.create_task(
        None, task_type="semantic_build", payload=json.dumps({"org": ORG}))
    handle.wake()
    for _ in range(50):
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (tid,)).fetchone()
        if row and row[0] == "done":
            break
        time.sleep(0.2)
    assert row[0] == "done", f"semantic_build 未被兜底循环认领: {row}"
    assert conn.execute(
        "SELECT count(*) FROM sem_builds WHERE status = 'ready'"
    ).fetchone()[0] == 1


# ---- 同步成功后自动投递构建（design §5.8） ----


def test_sync_success_auto_enqueues_build(build_app) -> None:
    client, conn = build_app["client"], build_app["conn"]
    admin = build_app["static"]["admin_tax"]

    resp = client.post(f"/api/orgs/{ORG}/semantic/sync/template_center",
                       headers=_h(admin))
    assert resp.status_code == 202
    sync_tid = resp.json()["task_id"]
    assert _wait_task_status(conn, sync_tid, "done")[0] == "done"

    # 同步成功 → semantic_build 任务自动出现并被消化（inline kick/兜底循环）
    for _ in range(50):
        builds = conn.execute(
            "SELECT count(*) FROM sem_builds WHERE status = 'ready'"
        ).fetchone()[0]
        if builds >= 1:
            break
        time.sleep(0.2)
    assert builds >= 1, "同步成功后未自动投递/执行 semantic_build（design §5.8）"
