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
    assert json.loads(task[1]) == {"org": ORG, "adapter": "template_center"}
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

    # inline worker 的 kick 由响应后台任务同步执行（TestClient）——任务应已终态
    task = conn.execute(
        "SELECT status, error FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
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
