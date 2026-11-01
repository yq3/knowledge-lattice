"""m2-6 A3：members 增/改/删（m2-4 N-1 用户裁定选 a——JIT 建档后 API 面开通闭环）。

- POST/PATCH/DELETE membership（含角色变更/软停用——软停用 = expires_at 承载，
  零新列择型）；审计入 outbox（与写同一事务）；org_admin 门控；
- **T23 触发器语义不破坏**：已过期成员关系不得原地变更（store 前置语义异常
  ——双方言统一），恢复路径 = 删行重加 + 补授权（m2-3 先例三步）；
- **唯一 active org_admin 守卫**：最后一个管理员不得自删/自停/自降级（409
  防自锁——择型申报）；
- **JIT 端到端**（D16 API 面闭环）：mock-idp 首登 JIT 建档 → 管理员 API 加
  组织 → PUT grants 配授权 → 检索可见——全程不碰 DB。

store 级双后端参数化（[sqlite]/[pg]）；REST 端点 sqlite（app_env 惯例）。
"""

from __future__ import annotations

import json

import pytest

from conftest import ORG
from helpers import FUTURE_TS, PAST_TS, seed_user


# ============ store 级（双后端） ============


def test_add_membership_crud_semantics(matrix) -> None:
    """add：成功（默认 member）/用户不存在 KeyError/已存在（含过期行）
    MembershipExistsError；audit 同事务（outbox 行在）。"""
    from knowledge_lattice.store.backend import MembershipExistsError

    backend = matrix.make_backend()
    seed_user(matrix, "u_new")
    created = backend.add_membership(
        ORG, "u_new", audit=("member.add", json.dumps({"org_id": ORG})),
    )
    assert created == {"user_id": "u_new", "role": "member", "expires_at": None}

    # 用户不存在 → KeyError（404 语义）
    with pytest.raises(KeyError):
        backend.add_membership(ORG, "u_ghost")

    # 已存在 → MembershipExistsError（409）
    with pytest.raises(MembershipExistsError):
        backend.add_membership(ORG, "u_new")

    # 过期行同样 409（恢复走删行重加——T23）
    from helpers import seed_membership

    seed_user(matrix, "u_exp2")
    seed_membership(matrix, "u_exp2", ORG, expires_at=PAST_TS)
    with pytest.raises(MembershipExistsError):
        backend.add_membership(ORG, "u_exp2")

    # audit 同事务
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'member.add'"
    ).fetchone()[0] >= 1


def test_update_membership_role_and_soft_disable(matrix) -> None:
    """update：角色变更 member→org_admin；软停用（expires_at 置过去时点——
    read_membership 即刻过滤）；改永不过期（None）；expires 归一（ISO→库格式）。"""
    backend = matrix.make_backend()
    seed_user(matrix, "u_role")
    from helpers import seed_membership

    seed_membership(matrix, "u_role", ORG)

    updated = backend.update_membership(
        ORG, "u_role", role="org_admin",
        audit=("member.update", "{}"),
    )
    assert updated["role"] == "org_admin"

    # 软停用：expires_at 过去时点 → read_membership None（权限计算过滤）
    backend.update_membership(ORG, "u_role", expires_at=PAST_TS)
    assert backend.read_membership("u_role", ORG) is None

    # 恢复被 T23 拒（过期行不得原地续期）
    from knowledge_lattice.store.backend import MembershipExpiredError

    with pytest.raises(MembershipExpiredError):
        backend.update_membership(ORG, "u_role", expires_at=FUTURE_TS)

    # 未过期行改永不过期 + ISO 输入归一
    seed_user(matrix, "u_perm")
    seed_membership(matrix, "u_perm", ORG, expires_at=FUTURE_TS)
    updated = backend.update_membership(ORG, "u_perm", expires_at=None)
    assert updated["expires_at"] is None
    seed_user(matrix, "u_iso")
    seed_membership(matrix, "u_iso", ORG)
    updated = backend.update_membership(
        ORG, "u_iso", expires_at="2030-06-01T12:00:00Z"
    )
    assert updated["expires_at"] == "2030-06-01 12:00:00"

    # 不存在 → None（404）
    assert backend.update_membership(ORG, "u_ghost", role="member") is None


def test_delete_membership_cascades_grants(matrix) -> None:
    """delete：删除 + trg_membership_delete_cleanup 级联清本组织授权（T23
    语义不破坏）；他组织授权不受影响；404 语义 False。"""
    backend = matrix.make_backend()
    seed_user(matrix, "u_del")
    from helpers import grant_by_key, seed_membership

    seed_membership(matrix, "u_del", ORG)
    seed_membership(matrix, "u_del", "org:gl")
    grant_by_key(matrix, "u_del", org_id=ORG, key="region", value="CN")
    grant_by_key(matrix, "u_del", org_id=ORG, key="tax_type", value="VAT")

    assert backend.delete_membership(
        ORG, "u_del", audit=("member.remove", "{}"),
    )
    # 本组织授权级联清空；org:gl 成员关系仍在
    assert matrix.execute(
        "SELECT count(*) FROM user_dimension_grants g JOIN dimensions d"
        " ON d.id = g.dimension_id WHERE g.user_id = 'u_del' AND d.org_id = ?",
        (ORG,),
    ).fetchone()[0] == 0
    assert backend.read_membership("u_del", "org:gl") is not None
    # 幂等 404：再删 False
    assert not backend.delete_membership(ORG, "u_del")


def test_t23_recovery_path_delete_readd_regrant(matrix) -> None:
    """T23 恢复路径回归（m2-3 先例三步）：过期行 → DELETE（级联清授权）→
    POST 重加 → PUT grants 补授权 → 授权展开恢复。"""
    backend = matrix.make_backend()
    seed_user(matrix, "u_rec")
    from helpers import grant_by_key, seed_membership

    seed_membership(matrix, "u_rec", ORG, expires_at=PAST_TS)
    grant_by_key(matrix, "u_rec", org_id=ORG, key="region", value="CN")

    # 过期行：read 已过滤；原地续期被拒
    assert backend.read_membership("u_rec", ORG) is None

    # 三步恢复
    assert backend.delete_membership(ORG, "u_rec")
    assert matrix.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'u_rec'"
    ).fetchone()[0] == 0, "删行级联清授权（补授权语义的起点）"
    backend.add_membership(ORG, "u_rec", role="member", expires_at=FUTURE_TS)
    backend.replace_local_grants(
        ORG, "u_rec", [("region", "CN", None)], audit=("grants.replace", "{}"),
    )
    grants = backend.read_grants("u_rec", ORG)
    assert grants.get("region") == ("CN",)
    assert backend.read_membership("u_rec", ORG)["role"] == "member"


# ============ REST 端点（sqlite——app_env） ============


@pytest.fixture()
def _member_env(app_env):
    from helpers import seed_membership

    from knowledge_lattice.domain.auth import hash_token

    conn = app_env["conn"]
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = 'admin_tax'",
        (hash_token("dev-static-admin-tax"),),
    )
    seed_user(conn, "u_plain")
    seed_membership(conn, "u_plain", ORG)
    conn.commit()
    return {
        **app_env,
        "admin": {"Authorization": "Bearer dev-static-admin-tax"},
        "plain": {"Authorization": f"Bearer {app_env['static']['u_cn']}"},
    }


def test_api_members_crud(_member_env) -> None:
    """POST 201/PATCH 200/DELETE 204 全链 + 审计事件三枚；org_admin 门控
    （普通成员 403）；用户不存在 404；重复 409。"""
    client = _member_env["client"]

    # 普通成员 403
    r = client.post(
        f"/api/orgs/{ORG}/members", headers=_member_env["plain"],
        json={"user_id": "u_newbie"},
    )
    assert r.status_code == 403

    # 新用户（先 JIT 形态：库内无此用户）→ 404
    r = client.post(
        f"/api/orgs/{ORG}/members", headers=_member_env["admin"],
        json={"user_id": "u_not_exist"},
    )
    assert r.status_code == 404

    # 正常新增（expires ISO 归一）
    seed_user(_member_env["conn"], "u_newbie")
    _member_env["conn"].commit()
    r = client.post(
        f"/api/orgs/{ORG}/members", headers=_member_env["admin"],
        json={"user_id": "u_newbie", "expires_at": "2030-06-01T12:00:00Z"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["expires_at"] == "2030-06-01 12:00:00"

    # 重复 409
    r = client.post(
        f"/api/orgs/{ORG}/members", headers=_member_env["admin"],
        json={"user_id": "u_newbie"},
    )
    assert r.status_code == 409

    # PATCH 角色变更 + 审计
    r = client.patch(
        f"/api/orgs/{ORG}/members/u_newbie", headers=_member_env["admin"],
        json={"role": "org_admin"},
    )
    assert r.status_code == 200 and r.json()["role"] == "org_admin"

    # PATCH 软停用（expires 过去）→ read_membership 过滤（org_scoped 403 可证）
    r = client.patch(
        f"/api/orgs/{ORG}/members/u_newbie", headers=_member_env["admin"],
        json={"expires_at": "2020-01-01 00:00:00"},
    )
    assert r.status_code == 200
    # 停用后 T23：再 PATCH → 409
    r = client.patch(
        f"/api/orgs/{ORG}/members/u_newbie", headers=_member_env["admin"],
        json={"expires_at": "2099-01-01 00:00:00"},
    )
    assert r.status_code == 409

    # DELETE → 204；再删 404；审计事件三枚（add/update/remove）
    r = client.delete(
        f"/api/orgs/{ORG}/members/u_newbie", headers=_member_env["admin"],
    )
    assert r.status_code == 204
    r = client.delete(
        f"/api/orgs/{ORG}/members/u_newbie", headers=_member_env["admin"],
    )
    assert r.status_code == 404
    for evt in ("member.add", "member.update", "member.remove"):
        assert _member_env["conn"].execute(
            "SELECT count(*) FROM audit_outbox WHERE event_type = ?", (evt,),
        ).fetchone()[0] >= 1, f"{evt} 审计入 outbox"


def test_api_members_last_admin_guard(_member_env) -> None:
    """唯一 active org_admin 不得自删/自停/自降级（409 防自锁——择型申报）。"""
    client = _member_env["client"]

    # admin_tax 自删 → 409（org:tax 唯一 admin）
    r = client.delete(
        f"/api/orgs/{ORG}/members/admin_tax", headers=_member_env["admin"],
    )
    assert r.status_code == 409
    # 自停用 → 409
    r = client.patch(
        f"/api/orgs/{ORG}/members/admin_tax", headers=_member_env["admin"],
        json={"expires_at": "2020-01-01 00:00:00"},
    )
    assert r.status_code == 409
    # 自降级 → 409
    r = client.patch(
        f"/api/orgs/{ORG}/members/admin_tax", headers=_member_env["admin"],
        json={"role": "member"},
    )
    assert r.status_code == 409

    # 补第二个 admin 后自降级放行
    seed_user(_member_env["conn"], "admin2")
    from helpers import seed_membership

    seed_membership(_member_env["conn"], "admin2", ORG, role="org_admin")
    _member_env["conn"].commit()
    r = client.patch(
        f"/api/orgs/{ORG}/members/admin_tax", headers=_member_env["admin"],
        json={"role": "member"},
    )
    assert r.status_code == 200


# ============ JIT 端到端（D16 API 面闭环——mock-idp） ============


def test_jit_to_grants_full_api_chain(tmp_path) -> None:
    """JIT 建档（SSO 首登）→ 管理员 API 加组织 → PUT grants 配授权 →
    检索 200——全程 API，不碰 DB 写（D16「管理员不建账号只配授权」闭环）。"""
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.auth_sso import MockIdpVerifier
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.domain.auth import hash_token
    from helpers import seed_dataset, seed_dimension, seed_dim_value, seed_org
    from knowledge_lattice.store.sqlite import connect

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        embed_model="fake-embed", probe_interval_s=0,
        worker_mode="inline",
        sso_provider="mock-idp", sso_mock_secret="e2e-sso-secret",
    )
    from fake_providers import FakeEmbedder

    app = create_app(settings, embedder=FakeEmbedder(dim=8), run_startup_probe=False)
    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    seed_dataset(conn, ORG, "ds:vat_lib")
    seed_dimension(conn, ORG, "region")
    seed_dim_value(conn, "dim:org:tax:region", "CN")
    seed_dim_value(conn, "dim:org:tax:region", "OS")
    # 管理员（静态 token 引导——仅 dev/test）
    conn.execute(
        "INSERT INTO users(id, username, token_hash) VALUES('admin_tax',"
        " 'admin_tax', ?)", (hash_token("dev-static-admin-tax"),),
    )
    conn.execute(
        "INSERT INTO user_org_memberships(user_id, org_id, role)"
        " VALUES('admin_tax', ?, 'org_admin')", (ORG,),
    )
    conn.commit()

    verifier = MockIdpVerifier(secret="e2e-sso-secret")
    sso_token = verifier.issue_token(sub="u_jit", aud=("knowledge-lattice",))

    with TestClient(app) as client:
        # ① SSO 首登：检索 403（JIT 建档成功但无成员关系——自动建档+审计）
        r = client.post(
            "/api/search", headers={
                "Authorization": f"Bearer {sso_token}", "X-Org-Id": ORG,
            }, json={"query": "增值税"},
        )
        assert r.status_code == 403, "JIT 建档成功但未入组——检索拒绝"
        jit = conn.execute(
            "SELECT count(*) FROM audit_outbox WHERE event_type ="
            " 'auth.user_jit_created'", (),
        ).fetchone()[0]
        assert jit == 1, "JIT 建档审计入 outbox"

        admin = {"Authorization": "Bearer dev-static-admin-tax"}
        # ② 管理员 API 加组织
        r = client.post(
            f"/api/orgs/{ORG}/members", headers=admin,
            json={"user_id": "u_jit", "role": "member"},
        )
        assert r.status_code == 201, r.text

        # ③ 无授权检索通过但空域收紧（T22：有成员关系无授权 → 只见该维为空
        # 的文档——访问权 200、可见域收紧；库内 region 文档均不可见）
        r = client.post(
            "/api/search", headers={
                "Authorization": f"Bearer {sso_token}", "X-Org-Id": ORG,
            }, json={"query": "增值税"},
        )
        assert r.status_code == 200
        assert r.json()["results"] == [], "无 region 授权——region 有值文档不可见"

        # ④ PUT grants 配授权
        r = client.put(
            f"/api/orgs/{ORG}/members/u_jit/grants", headers=admin,
            json={"grants": [{"dim_key": "region", "value": "CN"}]},
        )
        assert r.status_code == 200, r.text

        # ⑤ 检索 200（授权生效——D16 API 面全链闭环）
        r = client.post(
            "/api/search", headers={
                "Authorization": f"Bearer {sso_token}", "X-Org-Id": ORG,
            }, json={"query": "增值税"},
        )
        assert r.status_code == 200, r.text
    conn.close()


# ============ R2 P3-3：最后管理员守卫事务化（store 级双后端——pg datetime 路径） ============


def test_last_admin_guard_store_level(matrix) -> None:
    """守卫事务内判定（R2 P3-3）：唯一 active org_admin（**带 expires 的
    pg datetime 路径**——幂等 role 更新/空 PATCH 不再 Python 侧 datetime>str
    500）降级/停用/删除 → MembershipLastAdminError；双 admin 放行；
    过期 admin（非 active）不受守卫。独立组织（org:guard）——不受矩阵
    org:tax 既有 admin 计数干扰。"""
    from knowledge_lattice.store.backend import MembershipLastAdminError

    from helpers import seed_org

    GUARD_ORG = "org:guard"
    seed_org(matrix, GUARD_ORG, "守卫专用组织")
    backend = matrix.make_backend()
    from helpers import FUTURE_TS, seed_membership

    seed_user(matrix, "adm_exp")
    seed_membership(matrix, "adm_exp", GUARD_ORG, role="org_admin",
                    expires_at=FUTURE_TS)

    # 幂等 role 更新（role 不变）+ 带 expires 行——pg 侧 datetime 全程 SQL 比较
    updated = backend.update_membership(GUARD_ORG, "adm_exp", role="org_admin")
    assert updated["role"] == "org_admin"

    # 唯一 admin 降级/停用/删除 → 拒
    with pytest.raises(MembershipLastAdminError):
        backend.update_membership(GUARD_ORG, "adm_exp", role="member")
    with pytest.raises(MembershipLastAdminError):
        backend.update_membership(GUARD_ORG, "adm_exp",
                                  expires_at="2020-01-01 00:00:00")
    with pytest.raises(MembershipLastAdminError):
        backend.delete_membership(GUARD_ORG, "adm_exp")

    # 补第二个 active admin → 降级放行
    seed_user(matrix, "adm2")
    seed_membership(matrix, "adm2", GUARD_ORG, role="org_admin")
    updated = backend.update_membership(GUARD_ORG, "adm_exp", role="member")
    assert updated["role"] == "member"
    assert backend.delete_membership(GUARD_ORG, "adm_exp")

    # 过期 admin（非 active）——不受守卫（删除走 T23 恢复路径）
    seed_user(matrix, "adm_old")
    seed_membership(matrix, "adm_old", GUARD_ORG, role="org_admin",
                    expires_at=PAST_TS)
    assert backend.delete_membership(GUARD_ORG, "adm_old")


# ============ R3 P3-1：pg 守卫跨行并发（互降双 admin 恰一侧成功） ============


def test_last_admin_guard_concurrent_demote_pg(pg_db):
    """R3 P3-1：两连接并发互降两名 active org_admin——pg_advisory_xact_lock
    (hashtext(org)) 事务级咨询锁跨行串行化（**全 admin 行 FOR UPDATE 方案已
    弃用**——并发提交后 EPQ 抛 tuple concurrently updated，R3 择型见提交注记）：
    恰一侧成功、另一侧 MembershipLastAdminError，终态恒 1 admin
    （修复前 READ COMMITTED 双方 count=2 均放行 → 0 admin）。

    pg 专用（sqlite BEGIN IMMEDIATE 单写者天然串行——无此并发形态；
    DSN 未设 skip，门禁 skip=失败）。"""
    import threading

    import psycopg

    from knowledge_lattice.store.backend import MembershipLastAdminError
    from knowledge_lattice.store.postgres import setup_connection
    from knowledge_lattice.store.postgres.backend import PgBackend

    from helpers import seed_membership, seed_org, seed_user

    GUARD = "org:guard2"
    seed_org(pg_db, GUARD, "并发守卫组织")
    for uid in ("adm_a", "adm_b"):
        seed_user(pg_db, uid)
        seed_membership(pg_db, uid, GUARD, role="org_admin")

    # 两连接**串行** setup（setup_connection 的 CREATE OR REPLACE FUNCTION
    # 并发执行会撞 pg catalog 的 tuple concurrently updated——与本守卫无关），
    # 业务调用才并发
    conns = []
    for _ in range(2):
        raw = psycopg.connect(pg_db.dsn, autocommit=True)
        raw.execute(f'SET search_path TO "{pg_db.schema}", public')
        setup_connection(raw)
        conns.append(raw)

    results: dict[str, object] = {}

    def _demote(name: str, raw, target: str) -> None:
        backend = PgBackend(raw)
        try:
            backend.update_membership(GUARD, target, role="member")
            results[name] = "ok"
        except MembershipLastAdminError:
            results[name] = "blocked"

    t1 = threading.Thread(target=_demote, args=("t1", conns[0], "adm_a"))
    t2 = threading.Thread(target=_demote, args=("t2", conns[1], "adm_b"))
    t1.start(); t2.start(); t1.join(); t2.join()
    for raw in conns:
        raw.close()

    assert sorted(results.values()) == ["blocked", "ok"], (
        f"互降恰一侧成功: {results}"
    )
    admins = pg_db.execute(
        "SELECT count(*) FROM user_org_memberships"
        " WHERE org_id = ? AND role = 'org_admin'"
        "   AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
        (GUARD,),
    ).fetchone()[0]
    assert admins == 1, "终态恒 1 admin（0 admin 自锁窗口根除）"
