"""M4 m4-1 账号底座 store 层（D25 / FR-9——迁移 0012 + AccountsBackend 双方言）。

覆盖（`backend` fixture 双后端参数化，sqlite + PG 同一代码）：
- 迁移 0012：users 扩列 / 部分唯一索引（NULL 可共存、非 NULL 重复拒绝）/
  user_invitations + instance_setup 两新表 / setup id=1 CHECK / FK / 水位 12；
- setup：成功（含首组织 + org_admin membership + instance_setup 行 + 审计）、
  二次拒绝、已有用户无 setup 行拒绝、org 单参拒绝；
- 用户：create/get/find/list/get_user_auth 字段口径、username/email 冲突、
  invited 用户原子建档、停用/启用 tv 语义、末位 sysadmin 守卫、sysadmin 授撤、
  set_password tv++、record_login；
- 邀请/重置：create（只存 sha256、明文不落库）、revoke_pending 重发、find/list/
  revoke、accept 成功（membership/status/tv/consumed/审计）、单次、过期、撤销、
  未知 token 分类、reset 不建 membership；
- list_user_orgs 过期成员过滤。

口径：审计 payload 不含密码/token（断言）；now 一律 taskclock UTC 字符串。
"""

from __future__ import annotations

import hashlib
import json

import pytest

from helpers import FUTURE_TS, PAST_TS, seed_org, seed_user

# ============ 迁移 0012 ============


def test_migration_0012_accounts_schema(backend) -> None:
    """users 扩列 + 部分唯一索引 + 两新表 + 水位 12（sqlite/PG 各自入口）。"""
    if backend.is_sqlite:
        cols = {r[1] for r in backend.execute("PRAGMA table_info(users)")}
        assert {
            "email", "password_hash", "status", "token_version", "created_by",
            "last_login_at",
        } <= cols
        assert backend.execute("PRAGMA user_version").fetchone()[0] >= 12
        idx = backend.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index'"
            " AND name = 'ux_users_email'"
        ).fetchone()
        assert idx is not None and "WHERE email IS NOT NULL" in idx[0]
        inv_idx = backend.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
            " AND name = 'idx_user_invitations_user'"
        ).fetchone()
        assert inv_idx is not None
    else:
        cols = {
            r[0]
            for r in backend.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = current_schema() AND table_name = 'users'"
            )
        }
        assert {
            "email", "password_hash", "status", "token_version", "created_by",
            "last_login_at",
        } <= cols
        from knowledge_lattice.store.postgres.migrate import applied_versions

        assert 12 in applied_versions(backend.raw)
        assert backend.execute(
            "SELECT name FROM schema_migrations WHERE version = ?", (12,)
        ).fetchone() == ("local_accounts",)
        idx = backend.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema()"
            " AND indexname = 'ux_users_email'"
        ).fetchone()
        assert idx is not None and "WHERE (email IS NOT NULL)" in idx[0]
        inv_idx = backend.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
            " AND indexname = 'idx_user_invitations_user'"
        ).fetchone()
        assert inv_idx is not None

    # 两新表在场
    tables = backend.table_names()
    assert {"user_invitations", "instance_setup"} <= tables

    # 部分唯一索引：两个 NULL email 可共存；重复非 NULL 拒绝
    seed_user(backend, "u_null1", "u_null1")
    seed_user(backend, "u_null2", "u_null2")
    backend.execute(
        "UPDATE users SET email = ? WHERE id = ?", ("dup@example.com", "u_null1")
    )
    with pytest.raises(backend.integrity_error):
        backend.execute(
            "UPDATE users SET email = ? WHERE id = ?", ("dup@example.com", "u_null2")
        )

    # status CHECK：invited/active 之外拒绝
    with pytest.raises(backend.integrity_error):
        backend.execute(
            "INSERT INTO users(id, username, status) VALUES(?, ?, ?)",
            ("u_bad_status", "u_bad_status", "disabled"),
        )

    # setup 单例 CHECK（id=1 之外拒绝）+ FK（admin_user_id 必须存在）
    from knowledge_lattice.store.taskclock import utc_now_ts

    seed_user(backend, "u_setup_admin", "u_setup_admin")
    backend.execute(
        "INSERT INTO instance_setup(id, completed_at, admin_user_id)"
        " VALUES(?, ?, ?)",
        (1, utc_now_ts(), "u_setup_admin"),
    )
    with pytest.raises(backend.integrity_error):
        backend.execute(
            "INSERT INTO instance_setup(id, completed_at, admin_user_id)"
            " VALUES(?, ?, ?)",
            (2, utc_now_ts(), "u_setup_admin"),
        )
    assert backend.execute(
        "SELECT count(*) FROM instance_setup"
    ).fetchone()[0] == 1

    # user_invitations FK：未知 user 拒绝
    with pytest.raises(backend.fk_error):
        backend.execute(
            "INSERT INTO user_invitations(id, user_id, purpose, token_hash,"
            " invited_by, expires_at) VALUES(?, ?, 'invite', ?, 'u_admin', ?)",
            ("inv_bad_fk", "u_ghost", "th_bad_fk", FUTURE_TS),
        )


# ============ setup（首启单例） ============


def _setup(backend, *, org: tuple[str, str] | None = None):
    b = backend.make_backend()
    return b.setup_instance(
        admin_user_id="u_root", username=" root ", display_name="Root",
        email=" Root@Example.COM ", password_hash="scrypt$n=1$abc$def",
        org_id=org[0] if org else None, org_name=org[1] if org else None,
        audit=("instance.setup", json.dumps({"actor": "system"})),
    )


def test_setup_instance_success_with_first_org(backend) -> None:
    """成功：active sysadmin + 首组织 + org_admin membership + setup 行 + 审计。"""
    b = backend.make_backend()
    out = _setup(backend, org=("org:first", "首组织"))

    user = out["user"]
    assert user["id"] == "u_root"
    assert user["username"] == "root"  # strip，不 lower
    assert user["email"] == "root@example.com"  # strip().lower()
    assert user["status"] == "active"
    assert user["is_system_admin"] is True
    assert user["password_hash"] == "scrypt$n=1$abc$def"
    assert out["org"] == {"id": "org:first", "name": "首组织"}

    setup = b.get_instance_setup()
    assert setup is not None
    assert setup["admin_user_id"] == "u_root"
    # completed_at 取事务开始时的 utc_now_ts，users.created_at 走 DB 默认
    # CURRENT_TIMESTAMP——同一秒内相等，跨秒边界时 setup 时间早于建档时间；
    # 断言非空 + 单调序（不做跨秒精确相等——防时钟边界假红）。
    assert setup["completed_at"] and user["created_at"]
    assert setup["completed_at"] <= user["created_at"]
    assert b.count_users() == 1

    mem = backend.execute(
        "SELECT role FROM user_org_memberships WHERE user_id = ? AND org_id = ?",
        ("u_root", "org:first"),
    ).fetchone()
    assert mem == ("org_admin",)

    assert b.get_user_auth("u_root") == {
        "is_system_admin": True, "disabled_at": None,
        "status": "active", "token_version": 0,
    }
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'instance.setup'"
    ).fetchone()[0] == 1


def test_setup_instance_without_org(backend) -> None:
    b = backend.make_backend()
    out = _setup(backend)
    assert out["org"] is None
    assert b.count_users() == 1
    assert backend.execute("SELECT count(*) FROM orgs").fetchone()[0] == 0


def test_setup_instance_rejects_second_call(backend) -> None:
    from knowledge_lattice.store.backend import SetupCompletedError

    _setup(backend, org=("org:first", "首组织"))
    with pytest.raises(SetupCompletedError):
        _setup(backend)
    # 失败不再写审计（仍为 1 条）
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'instance.setup'"
    ).fetchone()[0] == 1


def test_setup_instance_rejects_existing_users_without_setup_row(backend) -> None:
    """库内已有用户、instance_setup 无行——仍然拒绝（防绕过零用户前置）。"""
    from knowledge_lattice.store.backend import SetupCompletedError

    seed_user(backend, "u_existing", "existing")
    assert backend.execute("SELECT count(*) FROM instance_setup").fetchone()[0] == 0
    with pytest.raises(SetupCompletedError):
        _setup(backend)
    assert backend.execute("SELECT count(*) FROM instance_setup").fetchone()[0] == 0


def test_setup_instance_requires_org_pair(backend) -> None:
    """org_id/org_name 单参 → ValueError（API 层 400 校验可后置，store fail-fast）。"""
    b = backend.make_backend()
    with pytest.raises(ValueError, match="成对"):
        b.setup_instance(
            admin_user_id="u_root", username="root", display_name=None,
            email=None, password_hash="scrypt$x", org_id="org:first",
            org_name=None, audit=None,
        )
    # 未开启事务/未落任何行
    assert b.count_users() == 0
    assert backend.execute("SELECT count(*) FROM orgs").fetchone()[0] == 0


# ============ 用户写/读路径 ============


def _create_user(b, *, user_id="u_a", username="alice", email=None,
                 status="active", is_system_admin=False, audit=None):
    return b.create_user(
        user_id=user_id, username=username, display_name=username.strip().title(),
        email=email, password_hash="scrypt$n=1$abc$def", status=status,
        is_system_admin=is_system_admin, created_by="u_root", audit=audit,
    )


def test_create_user_crud_fields_and_conflicts(backend) -> None:
    from knowledge_lattice.store.backend import (
        EmailTakenError,
        UsernameTakenError,
    )

    b = backend.make_backend()
    created = _create_user(
        b, username=" alice ", email=" Alice@Example.COM ",
    )
    assert created["username"] == "alice"
    assert created["email"] == "alice@example.com"
    assert created["display_name"] == "Alice"
    assert created["status"] == "active"
    assert created["token_version"] == 0
    assert created["is_system_admin"] is False
    assert created["created_by"] == "u_root"
    assert created["disabled_at"] is None
    assert created["last_login_at"] is None
    assert isinstance(created["created_at"], str)
    assert created["password_hash"] == "scrypt$n=1$abc$def"

    assert b.get_user("u_a") == created
    assert b.get_user("ghost") is None
    assert b.get_user_by_username("alice") == created
    assert b.get_user_by_username("Alice") is None  # 登录键精确，不 lower
    assert b.get_user_auth("u_a") == {
        "is_system_admin": False, "disabled_at": None,
        "status": "active", "token_version": 0,
    }

    users = b.list_users()
    assert [u["id"] for u in users] == ["u_a"]
    assert "password_hash" not in users[0]
    assert users[0]["username"] == "alice"

    # username 冲突（含并发唯一约束兜底路径的语义化异常）
    with pytest.raises(UsernameTakenError):
        _create_user(b, user_id="u_b", username="alice")
    assert b.count_users() == 1

    # email 冲突（email 归一后大小写不敏感）
    with pytest.raises(EmailTakenError):
        _create_user(b, user_id="u_c", username="bob", email="ALICE@example.com")
    assert b.count_users() == 1

    # audit 同事务
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'user.created'"
    ).fetchone()[0] == 0  # 本用例未传 audit——零写入


def test_create_user_with_audit_same_transaction(backend) -> None:
    b = backend.make_backend()
    _create_user(
        b, audit=("user.created", json.dumps({"user_id": "u_a"})),
    )
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'user.created'"
    ).fetchone()[0] == 1


def test_create_invited_user_atomic_and_conflicts(backend) -> None:
    """invited 用户 + 邀请行原子写；冲突时邀请行零残留（整体回滚）。"""
    from knowledge_lattice.store.backend import (
        EmailTakenError,
        UsernameTakenError,
    )

    seed_org(backend, "org:tax")
    b = backend.make_backend()
    out = b.create_invited_user(
        user_id="u_inv", username="bob", display_name="Bob",
        email="Bob@Example.com", invitation_id="inv_atomic", org_id="org:tax",
        role="member", token_hash="th_atomic", invited_by="u_admin",
        expires_at=FUTURE_TS, is_system_admin=False,
        audit=("auth.invite_created", json.dumps({"invitation_id": "inv_atomic"})),
    )
    assert out["user"]["status"] == "invited"
    assert out["user"]["password_hash"] is None
    assert out["user"]["email"] == "bob@example.com"
    assert out["invitation"]["token_hash"] == "th_atomic"
    assert out["invitation"]["org_name"] == "税务组织"
    assert out["invitation"]["purpose"] == "invite"
    assert out["invitation"]["consumed_at"] is None

    # username 冲突：新邀请行随用户插入失败一并回滚
    with pytest.raises(UsernameTakenError):
        b.create_invited_user(
            user_id="u_inv2", username="bob", display_name=None, email=None,
            invitation_id="inv_rollback", org_id="org:tax", role="member",
            token_hash="th_rollback", invited_by="u_admin",
            expires_at=FUTURE_TS, is_system_admin=False,
            audit=("auth.invite_created", "{}"),
        )
    assert b.get_invitation("inv_rollback") is None
    assert b.get_user("u_inv2") is None

    # email 冲突
    with pytest.raises(EmailTakenError):
        b.create_invited_user(
            user_id="u_inv3", username="carol", display_name=None,
            email="BOB@example.com", invitation_id="inv_email", org_id=None,
            role=None, token_hash="th_email", invited_by="u_admin",
            expires_at=FUTURE_TS, is_system_admin=False, audit=None,
        )
    assert b.get_user("u_inv3") is None
    assert backend.execute(
        "SELECT count(*) FROM user_invitations"
    ).fetchone()[0] == 1


# ============ 停用/启用/sysadmin ============


def test_update_user_flags_disable_enable_tv(backend) -> None:
    b = backend.make_backend()
    _create_user(b)

    out = b.update_user_flags(
        user_id="u_a", disabled=True, is_system_admin=None, actor="u_admin",
        audits=["user.disabled", "user.enabled"],
    )
    assert out["disabled_at"] is not None
    assert out["token_version"] == 1  # 停用 tv++（旧会话不复活）
    # 停用态认证面可读（API 依此 401）
    assert b.get_user_auth("u_a")["disabled_at"] is not None

    # 幂等：再次停用零变化零审计
    out = b.update_user_flags(
        user_id="u_a", disabled=True, is_system_admin=None, actor="u_admin",
        audits=["user.disabled"],
    )
    assert out["token_version"] == 1
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'user.disabled'"
    ).fetchone()[0] == 1

    # 启用：清 disabled_at，tv 不回退
    out = b.update_user_flags(
        user_id="u_a", disabled=False, is_system_admin=None, actor="u_admin",
        audits=["user.disabled", "user.enabled"],
    )
    assert out["disabled_at"] is None
    assert out["token_version"] == 1
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'user.enabled'"
    ).fetchone()[0] == 1

    # 全 None（不改）——幂等零审计
    b.update_user_flags(
        user_id="u_a", disabled=None, is_system_admin=None, actor="u_admin",
        audits=["user.disabled", "user.enabled", "user.sysadmin_changed"],
    )
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type IN"
        " ('user.disabled', 'user.enabled', 'user.sysadmin_changed')"
    ).fetchone()[0] == 2


def test_update_user_flags_sysadmin_toggle_and_audit(backend) -> None:
    b = backend.make_backend()
    _create_user(b, user_id="u_root", username="root", is_system_admin=True)
    _create_user(b, user_id="u_two", username="two")

    out = b.update_user_flags(
        user_id="u_two", disabled=None, is_system_admin=True, actor="u_root",
        audits=["user.sysadmin_changed"],
    )
    assert out["is_system_admin"] is True

    # 幂等：同值不改不审计
    b.update_user_flags(
        user_id="u_two", disabled=None, is_system_admin=True, actor="u_root",
        audits=["user.sysadmin_changed"],
    )
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'user.sysadmin_changed'"
    ).fetchone()[0] == 1

    # 同时停用 + 撤 sysadmin：两事件都写（仍有 u_root 兜底）
    out = b.update_user_flags(
        user_id="u_two", disabled=True, is_system_admin=False, actor="u_root",
        audits=["user.disabled", "user.sysadmin_changed"],
    )
    assert out["is_system_admin"] is False and out["disabled_at"] is not None
    assert out["token_version"] == 1
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'user.disabled'"
    ).fetchone()[0] == 1
    # sysadmin_changed 累计 2：授予（False→True）+ 撤权（True→False）
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'user.sysadmin_changed'"
    ).fetchone()[0] == 2
    # 审计 payload 含 actor 与目标，且不含密码
    payload = json.loads(backend.execute(
        "SELECT payload_json FROM audit_outbox"
        " WHERE event_type = 'user.sysadmin_changed'"
    ).fetchone()[0])
    assert payload["actor"] == "u_root" and payload["user_id"] == "u_two"
    assert "password" not in json.dumps(payload).lower()

    # 二元组形态（调用方自带 payload）同样按实际变化过滤
    custom = json.dumps({"custom": True})
    b.update_user_flags(
        user_id="u_two", disabled=None, is_system_admin=True, actor="u_root",
        audits=[("user.sysadmin_changed", custom)],
    )
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type ="
        " 'user.sysadmin_changed' AND payload_json = ?", (custom,)
    ).fetchone()[0] == 1


def test_last_sysadmin_guard(backend) -> None:
    """末位 active sysadmin 停用/撤权 → LastSysadminError；有继任后放行。

    停用的 sysadmin 不计入 active 计数（guard 用 disabled_at IS NULL 过滤）。
    """
    from knowledge_lattice.store.backend import LastSysadminError

    b = backend.make_backend()
    _create_user(b, user_id="u_root", username="root", is_system_admin=True)
    _create_user(b, user_id="u_normal", username="normal")

    with pytest.raises(LastSysadminError):
        b.update_user_flags(
            user_id="u_root", disabled=True, is_system_admin=None,
            actor="u_root", audits=["user.disabled"],
        )
    with pytest.raises(LastSysadminError):
        b.update_user_flags(
            user_id="u_root", disabled=None, is_system_admin=False,
            actor="u_root", audits=["user.sysadmin_changed"],
        )
    # 两次拒绝均未落写/未写审计
    assert b.get_user("u_root")["disabled_at"] is None
    assert b.get_user("u_root")["is_system_admin"] is True
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type IN"
        " ('user.disabled', 'user.enabled', 'user.sysadmin_changed')"
    ).fetchone()[0] == 0

    # 加第二名 sysadmin 后：停用 second（root 仍 active——放行）
    _create_user(b, user_id="u_second", username="second", is_system_admin=True)
    out = b.update_user_flags(
        user_id="u_second", disabled=True, is_system_admin=None,
        actor="u_root", audits=["user.disabled"],
    )
    assert out["disabled_at"] is not None
    with pytest.raises(LastSysadminError):
        b.update_user_flags(
            user_id="u_root", disabled=True, is_system_admin=None,
            actor="u_root", audits=["user.disabled"],
        )

    # 恢复 second 后 root 可撤权（有继任）
    b.update_user_flags(
        user_id="u_second", disabled=False, is_system_admin=None,
        actor="u_root", audits=["user.enabled"],
    )
    out = b.update_user_flags(
        user_id="u_root", disabled=None, is_system_admin=False,
        actor="u_root", audits=["user.sysadmin_changed"],
    )
    assert out["is_system_admin"] is False
    # 用户不存在 → KeyError（404）
    with pytest.raises(KeyError):
        b.update_user_flags(
            user_id="u_ghost", disabled=True, is_system_admin=None,
            actor="u_root", audits=["user.disabled"],
        )


# ============ 密码与登录时间 ============


def test_set_user_password_bump_tv(backend) -> None:
    b = backend.make_backend()
    _create_user(b)

    out = b.set_user_password(
        user_id="u_a", password_hash="scrypt$n=1$new$hash",
        bump_token_version=True,
        audit=("auth.password_changed", json.dumps({"user_id": "u_a"})),
    )
    assert out["password_hash"] == "scrypt$n=1$new$hash"
    assert out["token_version"] == 1
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'auth.password_changed'"
    ).fetchone()[0] == 1

    # bump=False（建号预置初始密码）：tv 不动
    out = b.set_user_password(
        user_id="u_a", password_hash="scrypt$n=1$pre$hash",
        bump_token_version=False,
    )
    assert out["password_hash"] == "scrypt$n=1$pre$hash"
    assert out["token_version"] == 1

    with pytest.raises(KeyError):
        b.set_user_password(
            user_id="u_ghost", password_hash="x", bump_token_version=True,
        )


def test_record_login(backend) -> None:
    b = backend.make_backend()
    _create_user(b)
    assert b.get_user("u_a")["last_login_at"] is None
    b.record_login("u_a")
    last = b.get_user("u_a")["last_login_at"]
    assert isinstance(last, str) and len(last) == 19  # 'YYYY-MM-DD HH:MM:SS'
    b.record_login("u_ghost")  # 未知用户：零行 UPDATE（幂等 no-op）


# ============ 邀请/重置 ============


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_create_invitation_stores_hash_only_and_lists(backend) -> None:
    seed_org(backend, "org:tax")
    seed_user(backend, "u_target", "target")
    seed_user(backend, "u_admin", "admin")
    b = backend.make_backend()

    raw_token = "plain-secret-invite-token"
    token_hash = _hash_token(raw_token)
    inv = b.create_invitation(
        invitation_id="inv_1", user_id="u_target", org_id="org:tax",
        role="member", purpose="invite", token_hash=token_hash,
        invited_by="u_admin", expires_at=FUTURE_TS, revoke_pending=False,
        audit=("auth.invite_created", json.dumps({"invitation_id": "inv_1"})),
    )
    assert inv["token_hash"] == token_hash
    assert inv["username"] == "target"
    assert inv["display_name"] is None
    assert inv["org_name"] == "税务组织"
    assert inv["purpose"] == "invite"
    assert inv["expires_at"] == FUTURE_TS

    # 只按 sha256 精确查：明文 token 查不到
    assert b.find_invitation_by_token_hash(raw_token) is None
    assert b.find_invitation_by_token_hash(token_hash)["id"] == "inv_1"
    assert b.get_invitation("inv_1")["id"] == "inv_1"
    assert b.get_invitation("inv_ghost") is None

    listed = b.list_invitations("org:tax")
    assert [r["id"] for r in listed] == ["inv_1"]
    assert listed[0]["username"] == "target"

    # 明文 token 不落库：行内任一列不出现
    row = backend.execute(
        "SELECT * FROM user_invitations WHERE id = ?", ("inv_1",)
    ).fetchone()
    assert raw_token not in repr(row)
    assert token_hash in repr(row)

    # 撤销：pending → True；二次 → False（未知/非 pending 404 语义）
    assert b.revoke_invitation(
        invitation_id="inv_1", org_id="org:tax", actor="u_admin",
        audit=("auth.invite_revoked", json.dumps({"invitation_id": "inv_1"})),
    )
    assert b.revoke_invitation(
        invitation_id="inv_1", org_id="org:tax", actor="u_admin",
    ) is False
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'auth.invite_revoked'"
    ).fetchone()[0] == 1
    # 跨组织撤销不生效（org 作用域）
    seed_org(backend, "org:gl", "隔离组织")
    assert b.revoke_invitation(
        invitation_id="inv_1", org_id="org:gl", actor="u_admin",
    ) is False


def test_create_invitation_revoke_pending(backend) -> None:
    """重发（revoke_pending=True）：同 user/org/purpose 旧 pending 行先失效。"""
    seed_org(backend, "org:tax")
    seed_user(backend, "u_target", "target")
    b = backend.make_backend()

    b.create_invitation(
        invitation_id="inv_old", user_id="u_target", org_id="org:tax",
        role="member", purpose="invite", token_hash="th_old",
        invited_by="u_admin", expires_at=FUTURE_TS, revoke_pending=False,
    )
    b.create_invitation(
        invitation_id="inv_new", user_id="u_target", org_id="org:tax",
        role="member", purpose="invite", token_hash="th_new",
        invited_by="u_admin", expires_at=FUTURE_TS, revoke_pending=True,
    )
    old = b.get_invitation("inv_old")
    new = b.get_invitation("inv_new")
    assert old["revoked_at"] is not None
    assert new["revoked_at"] is None and new["consumed_at"] is None
    # 其它 purpose 不受影响
    b.create_invitation(
        invitation_id="inv_reset", user_id="u_target", org_id="org:tax",
        role=None, purpose="reset", token_hash="th_reset",
        invited_by="u_admin", expires_at=FUTURE_TS, revoke_pending=False,
    )
    b.create_invitation(
        invitation_id="inv_new2", user_id="u_target", org_id="org:tax",
        role="member", purpose="invite", token_hash="th_new2",
        invited_by="u_admin", expires_at=FUTURE_TS, revoke_pending=True,
    )
    assert b.get_invitation("inv_reset")["revoked_at"] is None
    assert b.get_invitation("inv_new")["revoked_at"] is not None


def test_accept_invitation_success_invite(backend) -> None:
    """accept invite：consumed + 设密 + active + tv++ + membership + 审计。"""
    seed_org(backend, "org:tax")
    seed_user(backend, "u_admin", "admin")
    b = backend.make_backend()
    b.create_invited_user(
        user_id="u_inv", username="invitee", display_name=None,
        email="invitee@example.com", invitation_id="inv_accept",
        org_id="org:tax", role="member", token_hash="th_accept",
        invited_by="u_admin", expires_at=FUTURE_TS, is_system_admin=False,
        audit=("auth.invite_created", "{}"),
    )

    out = b.accept_invitation(
        token_hash="th_accept", password_hash="scrypt$n=1$pw$hash",
        display_name=" Invitee Name ",
        audit_event="auth.invite_accepted", actor_label="u_inv",
    )
    assert out["user"]["status"] == "active"
    assert out["user"]["password_hash"] == "scrypt$n=1$pw$hash"
    assert out["user"]["token_version"] == 1
    assert out["user"]["display_name"] == "Invitee Name"
    assert out["invitation"]["consumed_at"] is not None

    mem = backend.execute(
        "SELECT role FROM user_org_memberships WHERE user_id = ? AND org_id = ?",
        ("u_inv", "org:tax"),
    ).fetchone()
    assert mem == ("member",)

    # 审计：事件名由 API 传，payload 不含密码/hash
    payload_json = backend.execute(
        "SELECT payload_json FROM audit_outbox"
        " WHERE event_type = 'auth.invite_accepted'"
    ).fetchone()[0]
    payload = json.loads(payload_json)
    assert payload["actor"] == "u_inv"
    assert payload["invitation_id"] == "inv_accept"
    assert "scrypt" not in payload_json

    # 单次：二次消费 → consumed
    from knowledge_lattice.store.backend import InvitationInvalidError

    with pytest.raises(InvitationInvalidError) as excinfo:
        b.accept_invitation(
            token_hash="th_accept", password_hash="scrypt$n=1$pw2$hash",
            display_name=None, audit_event="auth.invite_accepted",
            actor_label="u_inv",
        )
    assert excinfo.value.reason == "consumed"


def test_accept_invitation_invalid_states(backend) -> None:
    """未知 token / 过期 / 撤销 三分类。"""
    from knowledge_lattice.store.backend import InvitationInvalidError

    seed_org(backend, "org:tax")
    seed_user(backend, "u_admin", "admin")
    b = backend.make_backend()

    with pytest.raises(InvitationInvalidError) as excinfo:
        b.accept_invitation(
            token_hash="th_unknown", password_hash="scrypt$x",
            display_name=None, audit_event="auth.invite_accepted",
            actor_label="u_x",
        )
    assert excinfo.value.reason == "invalid"

    # 过期
    b.create_invited_user(
        user_id="u_exp", username="expired", display_name=None, email=None,
        invitation_id="inv_exp", org_id="org:tax", role="member",
        token_hash="th_exp", invited_by="u_admin", expires_at=PAST_TS,
        is_system_admin=False, audit=None,
    )
    with pytest.raises(InvitationInvalidError) as excinfo:
        b.accept_invitation(
            token_hash="th_exp", password_hash="scrypt$x", display_name=None,
            audit_event="auth.invite_accepted", actor_label="u_exp",
        )
    assert excinfo.value.reason == "expired"

    # 撤销
    b.create_invited_user(
        user_id="u_rev", username="revoked", display_name=None, email=None,
        invitation_id="inv_rev", org_id="org:tax", role="member",
        token_hash="th_rev", invited_by="u_admin", expires_at=FUTURE_TS,
        is_system_admin=False, audit=None,
    )
    assert b.revoke_invitation(
        invitation_id="inv_rev", org_id="org:tax", actor="u_admin",
    )
    with pytest.raises(InvitationInvalidError) as excinfo:
        b.accept_invitation(
            token_hash="th_rev", password_hash="scrypt$x", display_name=None,
            audit_event="auth.invite_accepted", actor_label="u_rev",
        )
    assert excinfo.value.reason == "revoked"

    # 失败路径不写消费审计
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox"
        " WHERE event_type = 'auth.invite_accepted'"
    ).fetchone()[0] == 0


def test_accept_invitation_existing_membership_not_downgraded(backend) -> None:
    """已存在成员关系不降级（org_admin 已存在 + 邀请 member → 仍 org_admin）。"""
    seed_org(backend, "org:tax")
    seed_user(backend, "u_admin", "admin")
    b = backend.make_backend()
    b.create_invited_user(
        user_id="u_up", username="up", display_name=None, email=None,
        invitation_id="inv_up", org_id="org:tax", role="member",
        token_hash="th_up", invited_by="u_admin", expires_at=FUTURE_TS,
        is_system_admin=False, audit=None,
    )
    from helpers import seed_membership

    seed_membership(backend, "u_up", "org:tax", role="org_admin")
    b.accept_invitation(
        token_hash="th_up", password_hash="scrypt$x", display_name=None,
        audit_event="auth.invite_accepted", actor_label="u_up",
    )
    role = backend.execute(
        "SELECT role FROM user_org_memberships WHERE user_id = ? AND org_id = ?",
        ("u_up", "org:tax"),
    ).fetchone()[0]
    assert role == "org_admin"


def test_accept_invitation_reset_purpose_no_membership(backend) -> None:
    """reset 用途：改密 + tv++ + status active，不建 membership。"""
    seed_org(backend, "org:tax")
    seed_user(backend, "u_admin", "admin")
    b = backend.make_backend()
    _create_user(b, user_id="u_reset", username="resetme", email="reset@example.com")
    b.create_invitation(
        invitation_id="inv_reset2", user_id="u_reset", org_id=None, role=None,
        purpose="reset", token_hash="th_reset2", invited_by="u_admin",
        expires_at=FUTURE_TS, revoke_pending=False,
        audit=("auth.invite_created", "{}"),
    )
    before_tv = b.get_user("u_reset")["token_version"]
    out = b.accept_invitation(
        token_hash="th_reset2", password_hash="scrypt$n=1$reset$hash",
        display_name=None, audit_event="auth.password_reset",
        actor_label="u_reset",
    )
    assert out["user"]["password_hash"] == "scrypt$n=1$reset$hash"
    assert out["user"]["token_version"] == before_tv + 1
    assert out["user"]["status"] == "active"
    assert out["invitation"]["purpose"] == "reset"
    assert backend.execute(
        "SELECT count(*) FROM user_org_memberships WHERE user_id = ?",
        ("u_reset",),
    ).fetchone()[0] == 0
    assert backend.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'auth.password_reset'"
    ).fetchone()[0] == 1


# ============ list_user_orgs（有效成员关系） ============


def test_list_user_orgs_filters_expired_and_reports_org_status(backend) -> None:
    from helpers import seed_membership

    seed_org(backend, "org:tax")
    seed_org(backend, "org:gl", "隔离组织")
    seed_org(backend, "org:old", "过期组织")
    seed_user(backend, "u_multi", "multi")
    seed_membership(backend, "u_multi", "org:tax", role="org_admin")
    seed_membership(backend, "u_multi", "org:gl", expires_at=FUTURE_TS)
    seed_membership(backend, "u_multi", "org:old", expires_at=PAST_TS)
    backend.execute("UPDATE orgs SET status = 'disabled' WHERE id = ?", ("org:gl",))

    b = backend.make_backend()
    orgs = b.list_user_orgs("u_multi")
    assert [(o["id"], o["role"], o["status"]) for o in orgs] == [
        ("org:gl", "member", "disabled"),
        ("org:tax", "org_admin", "active"),
    ]
    assert {o["name"] for o in orgs} == {"隔离组织", "税务组织"}
    # 无有效成员关系 → 空表（不做隐式默认）
    seed_user(backend, "u_none", "none")
    assert b.list_user_orgs("u_none") == []
