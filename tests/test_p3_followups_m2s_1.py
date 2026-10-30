"""m2s-1 移交收编 P3-r1/r2/r4/r5（m2s-2 C 组——检查点遗留节为权威）。

- P3-r1：force 运行失败路径 run 侧 stats 补 `forced` 键（审计不再丢 forced 语义）；
- P3-r2：force 覆盖 guard 时 stats 补 guard 明细 {active,vanished,ratio,threshold}；
- P3-r4：fail-fast API 覆盖面（畸形 JSON→400 / 成员+force→403 零任务行 /
  admin+force+未配置→400）；
- P3-r5：config 校验错误前缀文案改范围语义。

（P3-r3 两场景固化进 tests/test_r2_m2s1_fixes.py——Committer 建议「固化进本文件」。）
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fake_semantic import FakeSourceAdapter, tpl_entity
from helpers import seed_membership, seed_org, seed_user

ORG = "org:tax"

NOW = "2026-10-30 12:00:00"


@pytest.fixture()
def sync_env(backend, tmp_path):
    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    return SimpleNamespace(db=backend, backend=backend.make_backend(), settings=settings)


def run(env, records, *, now=NOW, adapter_name="template_center", **kw):
    from knowledge_lattice.core.semantic.sync import run_sync

    return run_sync(
        env.backend, ORG, FakeSourceAdapter(adapter_name, records),
        settings=env.settings, snapshot=list(records), now=now, **kw
    )


# ---- P3-r1：force 失败路径 stats 补 forced 键 ----


def test_p3_r1_force_failure_stats_keep_forced(sync_env) -> None:
    run(sync_env, [tpl_entity("TPL_A")])  # 建基线（force 语义与 guard 无关）

    class Exploding(FakeSourceAdapter):
        def fetch(self, org):
            raise RuntimeError("source down (simulated)")

    from knowledge_lattice.core.semantic.sync import run_sync

    with pytest.raises(RuntimeError, match="source down"):
        run_sync(sync_env.backend, ORG, Exploding("template_center", []),
                 settings=sync_env.settings, force=True)

    row = sync_env.db.execute(
        "SELECT status, stats_json FROM sem_sync_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "failed"
    stats = json.loads(row[1])
    assert stats.get("forced") is True, "失败路径 stats 必须带 forced 键（P3-r1）"
    assert "source down" in stats.get("error", "")

    events = sync_env.db.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = 'semantic.sync'"
    ).fetchall()
    failed = [json.loads(p) for (p,) in events
              if json.loads(p)["status"] == "failed"]
    assert failed and failed[-1]["forced"] is True, "失败审计事件保留 forced 语义"


# ---- P3-r2：force 覆盖 guard 时 stats 补 guard 明细 ----


def test_p3_r2_force_override_stats_guard_detail(sync_env) -> None:
    run(sync_env, [tpl_entity(f"TPL_{i}") for i in range(10)])
    # 快照消失 3/10 = 30% > 20% 阈值 → guard 命中；force 放行执行
    r = run(sync_env, [tpl_entity(f"TPL_{i}") for i in range(7)], force=True)
    assert r["status"] == "succeeded"
    guard = r["stats"]["guard"]
    assert guard["active"] == 10
    assert guard["vanished"] == 3
    assert abs(guard["ratio"] - 0.3) < 1e-9
    assert guard["threshold"] == sync_env.settings.semantic_delete_guard
    assert r["stats"]["forced"] is True

    # 非 force 再度收缩（7 active → 快照仅 1，消失 6/7 > 20%）→ aborted_guard
    # 且 guard 明细原样在场（不回归）
    r2 = run(sync_env, [tpl_entity("TPL_0")])
    assert r2["status"] == "aborted_guard"
    assert r2["stats"]["guard"]["active"] == 7
    assert r2["stats"]["guard"]["vanished"] == 6


# ---- P3-r4：fail-fast API 覆盖面 ----


def _make_app(tmp_path, *, sources_json: str | None = None):
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect
    from fake_providers import FakeEmbedder

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=2560,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
        **({} if sources_json is None else
           {"semantic_sources_json": sources_json}),
    )
    app = create_app(settings, embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
                     run_startup_probe=False)
    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    for uid in ("u_full", "admin_tax"):
        seed_user(conn, uid)
    seed_membership(conn, "u_full", ORG)
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    for uid, token in (("u_full", "dev-static-u-full"),
                       ("admin_tax", "dev-static-admin-tax")):
        conn.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                     (hash_token(token), uid))
    conn.commit()
    return app, conn, {"u_full": "dev-static-u-full",
                       "admin_tax": "dev-static-admin-tax"}


def test_p3_r4_malformed_sources_json_400(tmp_path) -> None:
    """LATTICE_SEM_SOURCES_JSON 畸形 → 400（fail-closed——TC-SYNC-01 API 面）。"""
    from fastapi.testclient import TestClient

    app, conn, static = _make_app(tmp_path, sources_json="{not-json")
    try:
        with TestClient(app) as client:
            resp = client.post(
                f"/api/orgs/{ORG}/semantic/sync/template_center",
                headers={"Authorization": f"Bearer {static['admin_tax']}"})
            assert resp.status_code == 400
            assert "invalid" in resp.json()["detail"]
            assert conn.execute(
                "SELECT count(*) FROM tasks WHERE type = 'semantic_sync'"
            ).fetchone()[0] == 0
    finally:
        conn.close()


def test_p3_r4_member_force_403_zero_tasks(tmp_path) -> None:
    """普通成员 + force → 403 零任务行（force 不绕过权限——B2 边界）。"""
    from fastapi.testclient import TestClient

    app, conn, static = _make_app(
        tmp_path, sources_json=json.dumps(
            {ORG: {"template_center": {"endpoint": "http://fake/tc"}}}))
    try:
        with TestClient(app) as client:
            resp = client.post(
                f"/api/orgs/{ORG}/semantic/sync/template_center?force=true",
                headers={"Authorization": f"Bearer {static['u_full']}"})
            assert resp.status_code == 403
            assert conn.execute(
                "SELECT count(*) FROM tasks WHERE type = 'semantic_sync'"
            ).fetchone()[0] == 0
    finally:
        conn.close()


def test_p3_r4_admin_force_unconfigured_400(tmp_path) -> None:
    """admin + force + 未配置源 → 400（force 不绕过配置校验——零任务行零 outbox）。"""
    from fastapi.testclient import TestClient

    app, conn, static = _make_app(tmp_path)  # 无 sources 配置
    try:
        with TestClient(app) as client:
            resp = client.post(
                f"/api/orgs/{ORG}/semantic/sync/template_center?force=true",
                headers={"Authorization": f"Bearer {static['admin_tax']}"})
            assert resp.status_code == 400
            assert conn.execute(
                "SELECT count(*) FROM tasks WHERE type = 'semantic_sync'"
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT count(*) FROM audit_outbox WHERE event_type = 'semantic.sync'"
            ).fetchone()[0] == 0
    finally:
        conn.close()


# ---- P3-r5：config 校验错误前缀文案改范围语义 ----


def test_p3_r5_config_error_prefix_range_semantics(tmp_path, monkeypatch) -> None:
    from knowledge_lattice.config import get_settings

    monkeypatch.setenv("LATTICE_WORKER_POLL_S", "-1")
    monkeypatch.setenv("LATTICE_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError) as exc_info:
        get_settings()
    msg = str(exc_info.value)
    assert "out of allowed range" in msg
    assert "must be >= 0" not in msg, "P3-r5：旧前缀文案不得残留"
    assert "worker_poll_s=-1" in msg  # 具体字段与值仍定位得到
