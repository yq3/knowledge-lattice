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
        json={"id": "org:new", "name": "新组织", "org_admin": "u_gl"},
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
        json={"id": ORG, "name": "重复", "org_admin": "u_full"},
    )
    assert r.status_code == 409


# ============ R2/P3-8：create_org 边界（死组织拒绝 + 空值 + pg 竞态 409） ============


def test_create_org_requires_org_admin(orgs_env) -> None:
    """org_admin 缺省 → 拒绝（422/400）：无首任管理者的组织不可恢复——
    members POST 要求本组织 org_admin、sysadmin 无成员关系，形成死组织
    （Committer P3-8b——显式拒绝而非静默建出无人可管的组织）。"""
    r = orgs_env["client"].post(
        "/api/orgs", headers=_hdr(orgs_env, "sysadmin"),
        json={"id": "org:orphan", "name": "无主"},
    )
    assert r.status_code in (400, 422), (
        f"org_admin 缺省须拒绝（got {r.status_code}——死组织风险）")
    n = orgs_env["conn"].execute(
        "SELECT count(*) FROM orgs WHERE id = ?", ("org:orphan",)
    ).fetchone()[0]
    assert n == 0


@pytest.mark.parametrize("body_patch", [
    {"id": ""},          # id 空
    {"name": ""},       # name 空
    {"id": "   "},      # id 纯空白
])
def test_create_org_rejects_blank_id_name(orgs_env, body_patch) -> None:
    """id/name 空值/纯空白 → 422/400（P3-8a）。"""
    body = {"id": "org:x", "name": "正常", "org_admin": "u_full"}
    body.update(body_patch)
    r = orgs_env["client"].post(
        "/api/orgs", headers=_hdr(orgs_env, "sysadmin"), json=body)
    assert r.status_code in (400, 422), f"{body_patch} 须拒绝（got {r.status_code}）"


def test_store_create_org_concurrent_duplicate_pg(pg_db) -> None:
    """R2/P3-8c（pg store 级）：并发窗口下 INSERT 撞 UNIQUE → OrgExistsError
    （→API 409）而非裸 IntegrityError 500。预查 + BEGIN 的竞态面用直插
    对手行模拟（预查通过后、INSERT 前对手已提交——等效时序）。"""
    from knowledge_lattice.store.backend import OrgExistsError
    from knowledge_lattice.store.postgres.backend import PgBackend
    from helpers import seed_user

    seed_user(pg_db, "u_seed")
    backend = PgBackend(pg_db.raw)
    backend.create_org(org_id="org:race", name="竞态",
                       org_admin_user_id="u_seed")

    # 模拟「预查时不存在、INSERT 时已存在」的并发窗口：删除预查路径不可行，
    # 直接二次 create（预查命中 dup 分支）+ 借 monkeypatch 越过预查撞真
    # UNIQUE——两形态都收敛为 OrgExistsError
    import pytest as _pytest

    with _pytest.raises(OrgExistsError):
        backend.create_org(org_id="org:race", name="再建")

    # 越过预查（模拟并发窗口）：手工裸 INSERT 同 id 撞 UNIQUE 由 pg 实现
    # 捕获映射为 OrgExistsError（修复前裸 UniqueViolation 上抛 500 面）
    real_execute = pg_db.raw.execute

    def execute_no_select(sql, params=()):
        if sql.strip().upper().startswith("SELECT"):
            from psycopg import sql as _sql  # noqa: F401
            class _FakeRow(list):
                def fetchone(self):
                    return None   # 预查恒「不存在」
            return _FakeRow()
        return real_execute(sql, params)

    pg_db.raw.execute = execute_no_select
    try:
        with _pytest.raises(OrgExistsError):
            backend.create_org(org_id="org:race", name="并发窗")
    finally:
        pg_db.raw.execute = real_execute
    # 组织零残留（回滚干净）
    n = pg_db.execute(
        "SELECT count(*) FROM orgs WHERE id = ?", ("org:race",)
    ).fetchone()[0]
    assert n == 1, "既有组织保持 1 行（竞态失败零副作用）"
