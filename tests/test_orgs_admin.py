"""m2-5 A1：GET/POST /api/orgs（design §6.2 L1121——组织列表/创建组织）。

实现缺口补齐：端点在 §6.2 端点全集内、TC-AZ-04②「sysadmin 建组织/指定
org_admin」的 API 载体（此前无此端点——新组织首任 org_admin 无法经 API
建立：members POST 要求操作者已是本组织 org_admin，而 sysadmin 无成员
关系会 403，形成死锁；建组织时指定 org_admin 是唯一开通路径）。

- GET /api/orgs：系统管理员=全部组织；普通用户=本人 membership（角色/
  到期随行——TC-AZ-02 口径：不泄露非本人组织）；
- POST /api/orgs：**系统管理员专属**（其他 403）；{id, name, org_admin?}
  ——org_admin 指定即建首任 org_admin membership（用户不存在 404——D16
  管理员不建账号）；审计同事务；组织不可删只能停用（P1-1——本段只建）。
"""

from __future__ import annotations

import json

import pytest

from conftest import ORG, ORG_GL
from helpers import seed_membership, seed_org, seed_user


@pytest.fixture()
def orgs_env(app_env):
    """app_env + 隔离对照组织 org:gl + u_gl 静态 token。"""
    conn = app_env["conn"]
    seed_org(conn, ORG_GL, "隔离组织")
    seed_user(conn, "u_gl")
    seed_membership(conn, "u_gl", ORG_GL, role="org_admin")
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = ?",
        (_hash("dev-static-u-gl"), "u_gl"),
    )
    conn.commit()
    app_env["static"]["u_gl"] = "dev-static-u-gl"
    return app_env


def _hash(token: str) -> str:
    from knowledge_lattice.domain.auth import hash_token

    return hash_token(token)


def _hdr(env, uid: str) -> dict:
    return {"Authorization": f"Bearer {env['static'][uid]}"}


def test_get_orgs_member_sees_only_own_memberships(orgs_env) -> None:
    """普通用户（u_full）组织列表=本人 membership——不含 org:gl（TC-AZ-02
    口径：组织存在性对非成员不泄露）。"""
    r = orgs_env["client"].get("/api/orgs", headers=_hdr(orgs_env, "u_full"))
    assert r.status_code == 200, r.text
    orgs = r.json()["orgs"]
    ids = [o["org_id"] for o in orgs]
    assert ids == [ORG], f"普通用户只见本人 membership（got {ids}）"
    assert orgs[0]["role"] == "member"


def test_get_orgs_sysadmin_sees_all(orgs_env) -> None:
    """系统管理员=全部组织（org:tax + org:gl 双组织在列）。"""
    r = orgs_env["client"].get("/api/orgs", headers=_hdr(orgs_env, "sysadmin"))
    assert r.status_code == 200, r.text
    ids = sorted(o["org_id"] for o in r.json()["orgs"])
    assert ids == sorted([ORG, ORG_GL])


def test_create_org_denies_non_sysadmin(orgs_env) -> None:
    """非系统管理员（含 org_admin）建组织 403。"""
    r = orgs_env["client"].post(
        "/api/orgs", headers=_hdr(orgs_env, "u_gl"),
        json={"id": "org:new", "name": "新组织"},
    )
    assert r.status_code == 403


def test_create_org_with_org_admin_tc_az04(orgs_env) -> None:
    """TC-AZ-04②：sysadmin 建组织 + 指定首任 org_admin——组织落库、
    membership 建立（role=org_admin）、审计同事务；org_admin 随即可管理
    本组织（死锁解除的端到端验证：新 org_admin 给自己组织加成员 201）。"""
    conn = orgs_env["conn"]
    seed_user(conn, "u_new_admin")
    conn.commit()

    client = orgs_env["client"]
    r = client.post(
        "/api/orgs", headers=_hdr(orgs_env, "sysadmin"),
        json={"id": "org:newco", "name": "新组织", "org_admin": "u_new_admin"},
    )
    assert r.status_code == 201, r.text

    # 组织 + 首任 org_admin membership 落库
    assert conn.execute(
        "SELECT name FROM orgs WHERE id = ?", ("org:newco",)
    ).fetchone()[0] == "新组织"
    row = conn.execute(
        "SELECT role FROM user_org_memberships WHERE user_id = ?"
        " AND org_id = ?", ("u_new_admin", "org:newco"),
    ).fetchone()
    assert row and row[0] == "org_admin"

    # 审计同事务（org.created）
    events = [
        json.loads(e[0]) for e in conn.execute(
            "SELECT payload_json FROM audit_outbox WHERE event_type = 'org.created'"
        )
    ]
    assert events and events[-1]["org_id"] == "org:newco"
    assert events[-1]["org_admin"] == "u_new_admin"

    # 新 org_admin 随即可管理本组织（seed 另一用户后 POST members 201）
    seed_user(conn, "u_new_member")
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = ?",
        (_hash("dev-static-u-new-admin"), "u_new_admin"),
    )
    conn.commit()
    r2 = client.post(
        "/api/orgs/org:newco/members",
        headers={"Authorization": "Bearer dev-static-u-new-admin"},
        json={"user_id": "u_new_member", "role": "member"},
    )
    assert r2.status_code == 201, r2.text


def test_create_org_unknown_admin_user_404(orgs_env) -> None:
    """org_admin 指定不存在用户 → 404（D16 管理员不建账号）+ 组织零残留。"""
    conn = orgs_env["conn"]
    r = orgs_env["client"].post(
        "/api/orgs", headers=_hdr(orgs_env, "sysadmin"),
        json={"id": "org:ghost", "name": "幽灵", "org_admin": "u_ghost"},
    )
    assert r.status_code == 404
    assert conn.execute(
        "SELECT count(*) FROM orgs WHERE id = ?", ("org:ghost",)
    ).fetchone()[0] == 0, "org_admin 不存在时组织不得落库（同生共死）"


def test_create_org_duplicate_409(orgs_env) -> None:
    """重复建组织 409。"""
    r = orgs_env["client"].post(
        "/api/orgs", headers=_hdr(orgs_env, "sysadmin"),
        json={"id": ORG, "name": "重复"},
    )
    assert r.status_code == 409
