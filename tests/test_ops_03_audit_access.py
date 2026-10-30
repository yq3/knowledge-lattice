"""TC-OPS-03 审计访问分级【集成｜M2】（m2-3 A 组——FR-6 分级 / §6.2
GET /api/orgs/{org}/audit）。

原文（TEST-CASES L479-482）：
- ① org_admin 查本组织审计 → 全量（含查询词与命中）；
- ② 系统管理员查询 → **仅元数据**（查询词与命中详情不含——确需内容走审批+
  临时授权）；
- ③ org_admin 查他组织 → 拒绝。

数据源 = 当月月库（B2 链遍历序）+ 未搬运 outbox（双源合并）；REST 端点为
sqlite（app_env 惯例）。
"""

from __future__ import annotations

import json

import pytest

from conftest import ORG

from test_ops_chain_read import _seed_outbox_events


def test_audit_read_chain_order_via_monthly(matrix) -> None:
    """月库行读序（B2 承接）：搬运后行集含 org_id/action/actor 语义列（供分级
    查询过滤）。"""
    from knowledge_lattice.store.taskclock import utc_now_ts

    backend = matrix.make_backend()
    _seed_outbox_events(matrix, 3)
    events = backend.read_monthly_events(when=utc_now_ts())
    assert len(events) == 3
    assert all(e["org_id"] == ORG for e in events)
    assert all(e["action"] == "document.upload" for e in events)
    assert all(e["actor"] == "u_full" for e in events)


@pytest.fixture()
def _audit_env(app_env):
    """app_env + admin_tax（org_admin）/u_gl_admin（org:gl org_admin）+ 造数
    事件（含查询词 detail_json——分级剥离断言面）。"""
    from helpers import seed_membership, seed_org, seed_user
    from knowledge_lattice.domain.auth import hash_token

    conn = app_env["conn"]
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    seed_user(conn, "u_gl_admin")
    seed_org(conn, "org:gl", "隔离组织")
    seed_membership(conn, "u_gl_admin", "org:gl", role="org_admin")
    tokens = {"admin_tax": "dev-static-admin-tax", "u_gl_admin": "dev-static-gl-admin"}
    for uid, token in tokens.items():
        conn.execute(
            "UPDATE users SET token_hash = ? WHERE id = ?", (hash_token(token), uid)
        )
    conn.commit()
    headers = {
        "admin_tax": {"Authorization": f"Bearer {tokens['admin_tax']}"},
        "u_gl_admin": {"Authorization": f"Bearer {tokens['u_gl_admin']}"},
        "sysadmin": {"Authorization": f"Bearer {app_env['static']['sysadmin']}"},
        "u_full": {"Authorization": f"Bearer {app_env['static']['u_full']}"},
    }
    # 造数事件：本组织（含查询词 detail_json）+ 他组织 + 查询级事件
    conn.execute(
        "INSERT INTO audit_outbox(id, event_type, payload_json) VALUES"
        " ('evt-a1', 'document.upload', ?)",
        (json.dumps({"org_id": ORG, "user_id": "u_full", "doc_id": "d1"}),),
    )
    conn.execute(
        "INSERT INTO audit_outbox(id, event_type, payload_json) VALUES"
        " ('evt-a2', 'search.query', ?)",
        (json.dumps({"org_id": ORG, "user_id": "u_cn",
                     "query": "增值税税率", "hits": ["chk:1", "chk:2"]}),),
    )
    conn.execute(
        "INSERT INTO audit_outbox(id, event_type, payload_json) VALUES"
        " ('evt-a3', 'document.upload', ?)",
        (json.dumps({"org_id": "org:gl", "user_id": "u_gl_admin", "doc_id": "d9"}),),
    )
    conn.commit()
    return {**app_env, "headers": headers, "conn": conn}


def test_audit_org_admin_own_org_full(_audit_env) -> None:
    """① org_admin 查本组织 → 全量（含 detail_json 查询词与命中）。"""
    client = _audit_env["client"]
    r = client.get(f"/api/orgs/{ORG}/audit", headers=_audit_env["headers"]["admin_tax"])
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "full"
    events = body["events"]
    ids = [e["id"] for e in events]
    assert "evt-a1" in ids and "evt-a2" in ids
    assert "evt-a3" not in ids, "他组织事件不得出现（org 过滤）"
    by_id = {e["id"]: e for e in events}
    assert by_id["evt-a2"]["detail_json"], "全量含查询词与命中（detail_json）"
    payload = json.loads(by_id["evt-a2"]["detail_json"])
    assert payload["query"] == "增值税税率"


def test_audit_system_admin_metadata_only(_audit_env) -> None:
    """② 系统管理员 → 仅元数据（detail_json 剥离——查询词与命中详情不含）。"""
    client = _audit_env["client"]
    r = client.get(f"/api/orgs/{ORG}/audit", headers=_audit_env["headers"]["sysadmin"])
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "metadata"
    assert body["events"], "元数据行应在场（分级≠不可见）"
    for e in body["events"]:
        assert "detail_json" not in e, "系统管理员仅元数据——查询词与命中详情不含"
        assert "action" in e and "actor" in e  # 元数据列在场


def test_audit_org_admin_other_org_rejected(_audit_env) -> None:
    """③ org_admin 查他组织 → 拒绝（403——org_scoped 成员校验 + 非 admin 身份
    双拦）。"""
    client = _audit_env["client"]
    # u_gl_admin（org:gl 的 org_admin）查 org:tax——无 tax 成员关系
    r = client.get(f"/api/orgs/{ORG}/audit", headers=_audit_env["headers"]["u_gl_admin"])
    assert r.status_code == 403
    # 同一 u_gl_admin 查自己组织（org:gl）→ 全量
    r = client.get("/api/orgs/org:gl/audit", headers=_audit_env["headers"]["u_gl_admin"])
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "full"
    assert [e["id"] for e in body["events"]] == ["evt-a3"]


def test_audit_plain_member_rejected_and_filters(_audit_env) -> None:
    """普通成员（非 admin）→ 403；action 过滤 + limit 生效。"""
    client = _audit_env["client"]
    r = client.get(f"/api/orgs/{ORG}/audit", headers=_audit_env["headers"]["u_full"])
    assert r.status_code == 403

    r = client.get(
        f"/api/orgs/{ORG}/audit",
        params={"action": "search", "limit": 5},
        headers=_audit_env["headers"]["admin_tax"],
    )
    assert r.status_code == 200
    events = r.json()["events"]
    assert all(e["action"].startswith("search") for e in events)
    assert len(events) <= 5
