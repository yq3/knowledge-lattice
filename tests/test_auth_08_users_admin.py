"""TC-AUTH-09/10⑤ 用户管理（sysadmin）/ 末位守卫 / local 首组织 active 校验。

双后端参数化（``local_env``）。覆盖：
- GET /api/users 列表投影（无 password_hash/token_hash）；POST 建号（invited、
  零密码、邀请链接）；username/email 冲突 409；org_id/role 成对 + 组织存在性；
- PATCH 停用/恢复（停用即时 401、恢复可登录、tv 不回退）/ 末位 sysadmin 409 /
  至少一项 + extra forbid 422 / 未知用户 404；
- sysadmin 权限面：非 sysadmin 一律 403、无 token 401；
- reset 链接（已有覆盖见 test_auth_07 的重置链路）；
- local 形态 POST /api/orgs：invited/disabled 用户任 org_admin → 409，不存在 404，
  active 用户 201（org_admin 接受 username 或用户 ID；sso 形态既有行为不变——
  由既有 admin 用例回归）。
"""

from __future__ import annotations

import json

ADMIN = {
    "username": "admin",
    "password": "admin-password-123",
    "display_name": "管理员",
    "org_id": "org:tax",
    "org_name": "税务组织",
}
PASSWORD = ADMIN["password"]
PUBLIC_USER_FIELDS = {
    "id", "username", "display_name", "email", "status", "is_system_admin",
    "last_login_at", "created_at",
}
# 管理面投影 = auth 面 public_user + disabled_at/created_by（契约 §5 GET /api/users）
ADMIN_USER_FIELDS = PUBLIC_USER_FIELDS | {"disabled_at", "created_by"}


# ============ 助手 ============


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup(env, **overrides) -> dict:
    resp = env["client"].post("/api/setup", json={**ADMIN, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_user(env, admin_token: str, **body) -> dict:
    resp = env["client"].post(
        "/api/users", headers=_h(admin_token), json=body
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _accept(env, token: str, password: str) -> object:
    return env["client"].post(
        "/api/auth/invitations/accept", json={"token": token, "password": password}
    )


def _login(env, username: str, password: str) -> object:
    return env["client"].post(
        "/api/auth/login", json={"username": username, "password": password}
    )


def _assert_no_secret_fields(user: dict, raw: str) -> None:
    assert "password_hash" not in user and "token_hash" not in user
    assert "password_hash" not in raw and "token_hash" not in raw


# ============ 列表 / 建号 ============


def test_sysadmin_list_and_create_user(local_env) -> None:
    """① 列表投影；② 建号 201（invited/零密码/邀请链接）；冲突 409；组织成对。"""
    admin = _setup(local_env)
    client = local_env["client"]
    listed = client.get("/api/users", headers=_h(admin["token"]))
    assert listed.status_code == 200
    users = listed.json()["users"]
    assert len(users) == 1
    assert set(users[0]) == ADMIN_USER_FIELDS
    assert users[0]["disabled_at"] is None
    _assert_no_secret_fields(users[0], listed.text)

    created = _create_user(
        local_env, admin["token"], username="carol", display_name="卡罗",
        email="Carol@Example.com", is_system_admin=True,
    )
    assert set(created) == {"user", "invitation"}
    user, invitation = created["user"], created["invitation"]
    assert user["status"] == "invited" and user["is_system_admin"] is True
    assert user["email"] == "carol@example.com"
    assert set(user) == ADMIN_USER_FIELDS
    assert user["created_by"] == admin["user"]["id"]
    assert invitation["id"].startswith("inv_") and invitation["token"]
    _assert_no_secret_fields(user, json.dumps(created, ensure_ascii=False))
    row = local_env["db"].execute(
        "SELECT password_hash, status FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    assert row[0] is None and row[1] == "invited", "管理员建号不设密码"

    # 接受邀请 → 成为 active sysadmin（is_system_admin 透传）
    assert _accept(
        local_env, invitation["token"], "carol-password-123"
    ).status_code == 200
    assert _login(local_env, "carol", "carol-password-123").status_code == 200

    # 冲突：username / email（email 归一后比较）
    dup_name = client.post(
        "/api/users", headers=_h(admin["token"]), json={"username": "carol"}
    )
    assert dup_name.status_code == 409
    assert dup_name.json()["code"] == "username_taken"
    dup_email = client.post(
        "/api/users", headers=_h(admin["token"]),
        json={"username": "carol2", "email": "CAROL@example.com"},
    )
    assert dup_email.status_code == 409
    assert dup_email.json()["code"] == "email_taken"

    # org_id/role 成对校验
    role_only = client.post(
        "/api/users", headers=_h(admin["token"]),
        json={"username": "dave", "role": "member"},
    )
    assert role_only.status_code == 400
    assert role_only.json()["code"] == "invalid_role"
    missing_role = client.post(
        "/api/users", headers=_h(admin["token"]),
        json={"username": "dave", "org_id": "org:tax"},
    )
    assert missing_role.status_code == 400
    assert missing_role.json()["code"] == "invalid_role"
    bad_role = client.post(
        "/api/users", headers=_h(admin["token"]),
        json={"username": "dave", "org_id": "org:tax", "role": "sem_restricted"},
    )
    assert bad_role.status_code == 400
    assert bad_role.json()["code"] == "invalid_role"
    missing_org = client.post(
        "/api/users", headers=_h(admin["token"]),
        json={"username": "dave", "org_id": "org:missing", "role": "member"},
    )
    assert missing_org.status_code == 404
    assert missing_org.json()["code"] == "org_not_found"
    # 失败分支零残留
    assert local_env["backend"].get_user_by_username("dave") is None

    # 带组织建号：接受邀请后直接获得组织成员关系
    frank = _create_user(
        local_env, admin["token"], username="frank",
        org_id="org:tax", role="member",
    )
    assert frank["user"]["status"] == "invited"
    accepted = _accept(
        local_env, frank["invitation"]["token"], "frank-password-123"
    )
    assert accepted.status_code == 200
    assert accepted.json()["orgs"][0]["org_id"] == "org:tax"
    assert accepted.json()["orgs"][0]["role"] == "member"


# ============ 停用/恢复/末位守卫 ============


def test_patch_disable_enable_and_last_sysadmin(local_env) -> None:
    """③ 停用即时 401 / 恢复可登录；⑤ 末位 sysadmin 409；至少一项 422。"""
    admin = _setup(local_env)
    client = local_env["client"]
    bob = _create_user(local_env, admin["token"], username="bob")
    bob_id = bob["user"]["id"]
    assert _accept(
        local_env, bob["invitation"]["token"], "bob-password-123"
    ).status_code == 200
    bob_token = _login(local_env, "bob", "bob-password-123").json()["token"]
    assert client.get("/api/auth/me", headers=_h(bob_token)).status_code == 200

    # 停用：即时 401（旧会话 + 新登录）
    disabled = client.patch(
        f"/api/users/{bob_id}", headers=_h(admin["token"]),
        json={"disabled": True},
    )
    assert disabled.status_code == 200, disabled.text
    assert set(disabled.json()) == {"user"}
    assert set(disabled.json()["user"]) == ADMIN_USER_FIELDS
    assert disabled.json()["user"]["disabled_at"] is not None
    _assert_no_secret_fields(disabled.json()["user"], disabled.text)
    assert client.get("/api/auth/me", headers=_h(bob_token)).status_code == 401
    assert _login(local_env, "bob", "bob-password-123").status_code == 401

    # 恢复：可重新登录（旧会话不复活——tv 不回退）
    enabled = client.patch(
        f"/api/users/{bob_id}", headers=_h(admin["token"]),
        json={"disabled": False},
    )
    assert enabled.status_code == 200
    assert client.get("/api/auth/me", headers=_h(bob_token)).status_code == 401, \
        "重新启用不得复活旧会话（tv 不回退）"
    relogin = _login(local_env, "bob", "bob-password-123")
    assert relogin.status_code == 200

    # 幂等 no-op（同值不报错）
    assert client.patch(
        f"/api/users/{bob_id}", headers=_h(admin["token"]),
        json={"disabled": False},
    ).status_code == 200

    # 末位 sysadmin：撤权/停用均 409
    demote = client.patch(
        f"/api/users/{admin['user']['id']}", headers=_h(admin["token"]),
        json={"is_system_admin": False},
    )
    assert demote.status_code == 409
    assert demote.json()["code"] == "last_sysadmin"
    self_disable = client.patch(
        f"/api/users/{admin['user']['id']}", headers=_h(admin["token"]),
        json={"disabled": True},
    )
    assert self_disable.status_code == 409
    assert self_disable.json()["code"] == "last_sysadmin"

    # 未知用户 404；请求体校验（至少一项 / extra forbid）
    assert client.patch(
        "/api/users/u_ghost", headers=_h(admin["token"]),
        json={"disabled": True},
    ).status_code == 404
    assert client.patch(
        f"/api/users/{bob_id}", headers=_h(admin["token"]), json={}
    ).status_code == 422
    assert client.patch(
        f"/api/users/{bob_id}", headers=_h(admin["token"]),
        json={"username": "nope"},
    ).status_code == 422

    # 指定继任 sysadmin 后可撤权（末位守卫解除）
    promoted = client.patch(
        f"/api/users/{bob_id}", headers=_h(admin["token"]),
        json={"is_system_admin": True},
    )
    assert promoted.status_code == 200
    assert promoted.json()["user"]["is_system_admin"] is True
    assert client.patch(
        f"/api/users/{admin['user']['id']}", headers=_h(admin["token"]),
        json={"is_system_admin": False},
    ).status_code == 200
    # 原 admin 已非 sysadmin → 403（新 sysadmin 面仍可用）
    assert client.get("/api/users", headers=_h(admin["token"])).status_code == 403
    bob_admin_token = _login(local_env, "bob", "bob-password-123").json()["token"]
    assert client.get("/api/users", headers=_h(bob_admin_token)).status_code == 200
    # bob 现为末位 sysadmin → 自我撤权 409
    assert client.patch(
        f"/api/users/{bob_id}", headers=_h(bob_admin_token),
        json={"is_system_admin": False},
    ).status_code == 409


# ============ 权限面 ============


def test_users_admin_requires_sysadmin(local_env) -> None:
    """⑥ 非 sysadmin 调 /api/users* → 403；无 token → 401。"""
    admin = _setup(local_env)
    client = local_env["client"]
    bob = _create_user(local_env, admin["token"], username="bob")
    bob_id = bob["user"]["id"]
    assert _accept(
        local_env, bob["invitation"]["token"], "bob-password-123"
    ).status_code == 200
    bob_token = _login(local_env, "bob", "bob-password-123").json()["token"]

    assert client.get("/api/users", headers=_h(bob_token)).status_code == 403
    assert client.post(
        "/api/users", headers=_h(bob_token), json={"username": "x"}
    ).status_code == 403
    assert client.patch(
        f"/api/users/{bob_id}", headers=_h(bob_token),
        json={"disabled": True},
    ).status_code == 403
    assert client.post(
        f"/api/users/{bob_id}/reset", headers=_h(bob_token)
    ).status_code == 403
    # 无 token → 401（受保护面）
    assert client.get("/api/users").status_code == 401
    assert client.post(
        "/api/users", json={"username": "x"}
    ).status_code == 401
    # org_admin（bob 非）也一样——org_admin 不能重置他人密码（TC-AUTH-09⑦）
    member = _create_user(local_env, admin["token"], username="orgadmin1")
    assert _accept(
        local_env, member["invitation"]["token"], "orgadmin-password-1"
    ).status_code == 200
    member_token = _login(local_env, "orgadmin1", "orgadmin-password-1").json()["token"]
    assert client.post(
        f"/api/users/{bob_id}/reset", headers=_h(member_token)
    ).status_code == 403


# ============ TC-AUTH-10⑤ local POST /api/orgs：org_admin 必须 active ============


def test_create_org_rejects_inactive_org_admin(local_env) -> None:
    """local 形态：invited/disabled 用户任 org_admin → 409；不存在 404；active 201。"""
    admin = _setup(local_env)
    client = local_env["client"]
    pending = _create_user(local_env, admin["token"], username="pending1")
    pending_id = pending["user"]["id"]

    invited = client.post(
        "/api/orgs", headers=_h(admin["token"]),
        json={"id": "org:new", "name": "新组织", "org_admin": pending_id},
    )
    assert invited.status_code == 409, invited.text
    assert "active" in invited.json()["detail"]
    assert local_env["backend"].get_org_status("org:new") is None, "组织零残留"

    active = _create_user(local_env, admin["token"], username="active1")
    active_id = active["user"]["id"]
    assert _accept(
        local_env, active["invitation"]["token"], "active1-password-1"
    ).status_code == 200
    assert client.patch(
        f"/api/users/{active_id}", headers=_h(admin["token"]),
        json={"disabled": True},
    ).status_code == 200
    disabled = client.post(
        "/api/orgs", headers=_h(admin["token"]),
        json={"id": "org:new", "name": "新组织", "org_admin": active_id},
    )
    assert disabled.status_code == 409, disabled.text
    assert "active" in disabled.json()["detail"]
    assert local_env["backend"].get_org_status("org:new") is None

    # 用户不存在仍 404（存在性敏感）
    missing = client.post(
        "/api/orgs", headers=_h(admin["token"]),
        json={"id": "org:new", "name": "新组织", "org_admin": "u_ghost"},
    )
    assert missing.status_code == 404

    # active 用户可任 org_admin（sanity——local 分支不误伤）
    ok = client.post(
        "/api/orgs", headers=_h(admin["token"]),
        json={"id": "org:new", "name": "新组织", "org_admin": admin["user"]["id"]},
    )
    assert ok.status_code == 201, ok.text
    assert local_env["backend"].get_org_status("org:new") == "active"


def test_create_org_accepts_username_in_local_mode(local_env) -> None:
    """local：org_admin 接受 username（与 /api/users、邀请面一致），ID 仍兼容。

    D25 评审修正：本地账号的人类可读键是 username（ID 为不透明 u_<hex>）；
    此前只按 ID 解析，sysadmin 在组织页填用户名会 404「用户不存在」。
    """
    admin = _setup(local_env)
    client = local_env["client"]
    made = _create_user(local_env, admin["token"], username="y00668221")
    user = made["user"]
    assert _accept(
        local_env, made["invitation"]["token"], "y00668221-password"
    ).status_code == 200

    resp = client.post(
        "/api/orgs", headers=_h(admin["token"]),
        json={"id": "org:demo", "name": "演示组织", "org_admin": "y00668221"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["org_admin"] == user["id"], "响应落稳定 ID"
    assert body["org_admin_username"] == "y00668221"
    membership = local_env["backend"].read_membership(user["id"], "org:demo")
    assert membership is not None and membership["role"] == "org_admin"

    events = [
        json.loads(r[0]) for r in local_env["db"].execute(
            "SELECT payload_json FROM audit_outbox"
            " WHERE event_type = 'org.created'"
        ).fetchall()
    ]
    assert events and events[-1]["org_admin"] == user["id"]
    assert events[-1]["org_admin_username"] == "y00668221"

    # username 路径的 409/404 分类与 ID 路径一致，且组织零残留
    _create_user(local_env, admin["token"], username="pending3")
    pending = client.post(
        "/api/orgs", headers=_h(admin["token"]),
        json={"id": "org:pending", "name": "未激活组织", "org_admin": "pending3"},
    )
    assert pending.status_code == 409 and "active" in pending.json()["detail"]
    ghost = client.post(
        "/api/orgs", headers=_h(admin["token"]),
        json={"id": "org:ghost", "name": "幽灵组织", "org_admin": "ghost-user"},
    )
    assert ghost.status_code == 404
    assert local_env["backend"].get_org_status("org:pending") is None
    assert local_env["backend"].get_org_status("org:ghost") is None


def test_add_member_accepts_username_in_local_mode(local_env) -> None:
    """local：加成员可按 username 指定（2026-11-22 UI 走查）。

    org_admin 侧没有用户目录（u_<hex> ID 既查不到也记不住），此前只能手输 ID，
    实际不可用。解析口径与建组织一致：先按 id 查、再按 username 换 id；未知仍 404。
    """
    admin = _setup(local_env)
    client = local_env["client"]
    made = _create_user(local_env, admin["token"], username="y00668221")
    user = made["user"]
    assert _accept(
        local_env, made["invitation"]["token"], "y00668221-password"
    ).status_code == 200

    resp = client.post(
        "/api/orgs/org:tax/members", headers=_h(admin["token"]),
        json={"user_id": "y00668221", "role": "member"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user_id"] == user["id"], "username 解析为稳定 ID"
    assert body["username"] == "y00668221"
    assert local_env["backend"].read_membership(user["id"], "org:tax") is not None

    # 未知 username 仍 404（与 ID 路径同分类，消息回显输入值）
    missing = client.post(
        "/api/orgs/org:tax/members", headers=_h(admin["token"]),
        json={"user_id": "no-such-user", "role": "member"},
    )
    assert missing.status_code == 404
