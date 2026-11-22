"""TC-AUTH-08 邀请/接受/撤销/重置 + 审计无 secrets（D25 / FR-9）。

双后端参数化（``local_env``）。覆盖：
- org_admin 邀本组织新用户 → lookup → accept → 登录 + members 可见；
- 单次消费（二次 accept 404 consumed）、过期（造数 expires_at）、撤销、
  重发（旧链接 revoked）、列表 status 四态；
- accepted 链接用途校验：reset 链接改密 + 旧会话 401（tv++）；
- 权限：member 无邀请权 403、跨组织 org_admin 403；
- 已存在 active 用户直接加成员（`membership_added=true`）、已有成员 409；
- 已 disabled 用户邀请/加组 409 user_disabled；
- 审计：``auth.invite_created`` / ``auth.invite_accepted`` / ``auth.password_reset``
  / ``auth.invite_revoked`` 全量 payload 不含密码明文、邀请 token 明文/摘要、
  session token 明文与 password_hash。
"""

from __future__ import annotations

import hashlib
import json

from helpers import PAST_TS

ADMIN = {
    "username": "admin",
    "password": "admin-password-123",
    "display_name": "管理员",
    "org_id": "org:tax",
    "org_name": "税务组织",
}
PASSWORD = ADMIN["password"]


# ============ 助手 ============


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup(env, **overrides) -> dict:
    resp = env["client"].post("/api/setup", json={**ADMIN, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _invite(env, admin_token: str, *, username: str, role: str = "member",
            display_name: str | None = None, email: str | None = None,
            org: str = "org:tax") -> dict:
    payload = {"username": username, "role": role}
    if display_name is not None:
        payload["display_name"] = display_name
    if email is not None:
        payload["email"] = email
    resp = env["client"].post(
        f"/api/orgs/{org}/invitations", headers=_h(admin_token), json=payload
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _accept(env, token: str, password: str,
            display_name: str | None = None) -> object:
    payload: dict = {"token": token, "password": password}
    if display_name is not None:
        payload["display_name"] = display_name
    return env["client"].post("/api/auth/invitations/accept", json=payload)


def _login(env, username: str, password: str) -> object:
    return env["client"].post(
        "/api/auth/login", json={"username": username, "password": password}
    )


def _outbox(env, event_type: str) -> list[dict]:
    rows = env["db"].execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?", (event_type,)
    ).fetchall()
    return [json.loads(row[0]) for row in rows]


def _invitation_rows(env) -> list[tuple]:
    return env["db"].execute(
        "SELECT id, user_id, org_id, role, purpose, token_hash,"
        " consumed_at, revoked_at, expires_at FROM user_invitations"
    ).fetchall()


# ============ 邀请全链（新用户） ============


def test_org_invitation_end_to_end(local_env) -> None:
    """org_admin 邀请新用户 → lookup → accept → 登录 + members 含该用户。"""
    admin = _setup(local_env)
    created = _invite(
        local_env, admin["token"], username="newbie", role="member",
        display_name="新人", email="Newbie@Example.com",
    )
    assert created["membership_added"] is False
    user_id = created["user_id"]
    invitation = created["invitation"]
    assert user_id.startswith("u_") and invitation["id"].startswith("inv_")
    assert len(invitation["token"]) >= 40  # 32B urlsafe
    # 库内：invited 无密码；邀请只存 token sha256
    row = local_env["db"].execute(
        "SELECT status, password_hash FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    assert row[0] == "invited" and row[1] is None
    stored = local_env["db"].execute(
        "SELECT token_hash, purpose, org_id, role FROM user_invitations WHERE id = ?",
        (invitation["id"],),
    ).fetchone()
    assert stored[0] == hashlib.sha256(invitation["token"].encode()).hexdigest()
    assert stored[0] != invitation["token"]
    assert stored[1] == "invite" and stored[2] == "org:tax" and stored[3] == "member"

    lookup = local_env["client"].post(
        "/api/auth/invitations/lookup", json={"token": invitation["token"]}
    )
    assert lookup.status_code == 200, lookup.text
    assert lookup.json() == {
        "purpose": "invite",
        "username": "newbie",
        "display_name": "新人",
        "email": "newbie@example.com",  # store 归一 strip().lower()
        "org_id": "org:tax",
        "org_name": "税务组织",
        "role": "member",
        "expires_at": invitation["expires_at"],
    }
    assert invitation["token"] not in lookup.text

    accepted = _accept(local_env, invitation["token"], "newbie-password-123")
    assert accepted.status_code == 200, accepted.text
    session = accepted.json()
    assert set(session) == {"token", "expires_at", "user", "orgs"}
    assert session["user"]["id"] == user_id
    assert session["user"]["status"] == "active"
    assert session["user"]["display_name"] == "新人"
    assert session["orgs"] == [
        {"org_id": "org:tax", "name": "税务组织", "role": "member",
         "status": "active"}
    ]
    # 单次：二审 404 consumed
    replay = _accept(local_env, invitation["token"], "newbie-password-123")
    assert replay.status_code == 404
    assert replay.json()["code"] == "invite_consumed"

    login = _login(local_env, "newbie", "newbie-password-123")
    assert login.status_code == 200
    me = local_env["client"].get(
        "/api/auth/me", headers=_h(login.json()["token"])
    )
    assert me.json()["orgs"][0]["org_id"] == "org:tax"
    members = local_env["client"].get(
        "/api/orgs/org:tax/members", headers=_h(admin["token"])
    )
    assert members.status_code == 200
    member_row = next(
        item for item in members.json()["members"] if item["user_id"] == user_id
    )
    assert member_row["username"] == "newbie" and member_row["role"] == "member"
    # 审计：创建/接受事件在；payload 不含 token/密码明文
    assert _outbox(local_env, "auth.invite_created")
    accepted_events = _outbox(local_env, "auth.invite_accepted")
    assert accepted_events and accepted_events[0]["user_id"] == user_id
    payload_text = json.dumps(
        _outbox(local_env, "auth.invite_created")
        + accepted_events,
        ensure_ascii=False,
    )
    assert invitation["token"] not in payload_text
    assert "newbie-password-123" not in payload_text


def test_invitation_weak_password_does_not_consume(local_env) -> None:
    """弱密码 400（token 不消费——可重试）；未知 token 404 invite_invalid。"""
    admin = _setup(local_env)
    created = _invite(local_env, admin["token"], username="weakie")
    invitation = created["invitation"]
    weak = _accept(local_env, invitation["token"], "short")
    assert weak.status_code == 400 and weak.json()["code"] == "weak_password"
    assert local_env["client"].post(
        "/api/auth/invitations/lookup", json={"token": invitation["token"]}
    ).status_code == 200, "弱密码失败不得消费 token"
    ok = _accept(local_env, invitation["token"], "weakie-password-123")
    assert ok.status_code == 200

    unknown = _accept(local_env, "not-a-real-token", "whatever-password-1")
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "invite_invalid"
    missing = local_env["client"].post(
        "/api/auth/invitations/lookup", json={"token": "not-a-real-token"}
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "invite_invalid"


# ============ 过期 / 撤销 / 重发 / 列表状态 ============


def test_invitation_expiry_revoke_resend_and_list(local_env) -> None:
    """过期（造数）/撤销/重发旧链接失效 + 列表四态 status。"""
    admin = _setup(local_env)
    client = local_env["client"]

    # 过期：造数 expires_at = PAST_TS
    expired_inv = _invite(local_env, admin["token"], username="alice")["invitation"]
    local_env["db"].execute(
        "UPDATE user_invitations SET expires_at = ? WHERE id = ?",
        (PAST_TS, expired_inv["id"]),
    )
    local_env["db"].commit()
    lookup_expired = client.post(
        "/api/auth/invitations/lookup", json={"token": expired_inv["token"]}
    )
    assert lookup_expired.status_code == 404
    assert lookup_expired.json()["code"] == "invite_expired"
    accept_expired = _accept(local_env, expired_inv["token"], "alice-password-123")
    assert accept_expired.status_code == 404
    assert accept_expired.json()["code"] == "invite_expired"
    # 过期行不可撤销（404 invite_invalid）
    assert client.delete(
        f"/api/orgs/org:tax/invitations/{expired_inv['id']}",
        headers=_h(admin["token"]),
    ).status_code == 404

    # 撤销
    revoked_inv = _invite(local_env, admin["token"], username="brenda")["invitation"]
    assert client.delete(
        f"/api/orgs/org:tax/invitations/{revoked_inv['id']}",
        headers=_h(admin["token"]),
    ).status_code == 204
    lookup_revoked = client.post(
        "/api/auth/invitations/lookup", json={"token": revoked_inv["token"]}
    )
    assert lookup_revoked.status_code == 404
    assert lookup_revoked.json()["code"] == "invite_revoked"
    assert client.delete(
        f"/api/orgs/org:tax/invitations/{revoked_inv['id']}",
        headers=_h(admin["token"]),
    ).status_code == 404, "二次撤销 404 invite_invalid"
    assert _outbox(local_env, "auth.invite_revoked")

    # 重发（status=invited 用户重发 → revoke_pending 旧链接失效）
    first = _invite(local_env, admin["token"], username="carol")
    second = _invite(local_env, admin["token"], username="carol")
    assert first["user_id"] == second["user_id"]
    assert first["invitation"]["id"] != second["invitation"]["id"]
    old = client.post(
        "/api/auth/invitations/lookup", json={"token": first["invitation"]["token"]}
    )
    assert old.status_code == 404 and old.json()["code"] == "invite_revoked"
    assert client.post(
        "/api/auth/invitations/lookup", json={"token": second["invitation"]["token"]}
    ).status_code == 200

    # 列表：四态 status（expired / revoked / revoked / pending）
    listed = client.get(
        "/api/orgs/org:tax/invitations", headers=_h(admin["token"])
    )
    assert listed.status_code == 200
    status_by_id = {row["id"]: row["status"] for row in listed.json()["invitations"]}
    assert status_by_id[expired_inv["id"]] == "expired"
    assert status_by_id[revoked_inv["id"]] == "revoked"
    assert status_by_id[first["invitation"]["id"]] == "revoked"
    assert status_by_id[second["invitation"]["id"]] == "pending"
    for row in listed.json()["invitations"]:
        assert "token_hash" not in row and "token" not in row
        assert set(row) == {
            "id", "user_id", "username", "role", "purpose", "status",
            "created_at", "expires_at", "consumed_at", "revoked_at",
            "invited_by",
        }


# ============ 权限边界 ============


def test_invitation_permissions_member_and_cross_org(local_env) -> None:
    """member 无邀请权 403；跨组织 org_admin 403（org_scoped + org_admin 门控）。"""
    admin = _setup(local_env)
    client = local_env["client"]
    created = _invite(local_env, admin["token"], username="member1")
    assert _accept(
        local_env, created["invitation"]["token"], "member1-password-123"
    ).status_code == 200
    member_login = _login(local_env, "member1", "member1-password-123")
    member_token = member_login.json()["token"]
    member_id = created["user_id"]

    # member（非 org_admin）→ 403（GET/POST/DELETE）
    assert client.get(
        "/api/orgs/org:tax/invitations", headers=_h(member_token)
    ).status_code == 403
    assert client.post(
        "/api/orgs/org:tax/invitations", headers=_h(member_token),
        json={"username": "x", "role": "member"},
    ).status_code == 403
    assert client.delete(
        f"/api/orgs/org:tax/invitations/{created['invitation']['id']}",
        headers=_h(member_token),
    ).status_code == 403

    # member1 成为他组织 org_admin（org:other），但非 org:tax org_admin
    org_other = client.post(
        "/api/orgs", headers=_h(admin["token"]),
        json={"id": "org:other", "name": "其他组织", "org_admin": member_id},
    )
    assert org_other.status_code == 201, org_other.text
    assert client.get(
        "/api/orgs/org:tax/invitations", headers=_h(member_token)
    ).status_code == 403, "org_admin 只在自己组织有效"
    assert client.post(
        "/api/orgs/org:tax/invitations", headers=_h(member_token),
        json={"username": "x", "role": "member"},
    ).status_code == 403
    # 本组织 org_admin 面可用（sanity）
    own = client.post(
        "/api/orgs/org:other/invitations", headers=_h(member_token),
        json={"username": "outside", "role": "member"},
    )
    assert own.status_code == 201, own.text

    # 跨组织：org:tax 的 org_admin 对 org:other 无成员关系 → org_scoped 403
    assert client.get(
        "/api/orgs/org:other/invitations", headers=_h(admin["token"])
    ).status_code == 403
    assert client.post(
        "/api/orgs/org:other/invitations", headers=_h(admin["token"]),
        json={"username": "someone", "role": "member"},
    ).status_code == 403
    assert client.delete(
        f"/api/orgs/org:other/invitations/{own.json()['invitation']['id']}",
        headers=_h(admin["token"]),
    ).status_code == 403


# ============ 已存在用户分支 ============


def test_invite_existing_active_user_adds_membership(local_env) -> None:
    """active 用户直接加成员（membership_added=true）；已有成员/disabled 409。"""
    admin = _setup(local_env)
    client = local_env["client"]
    dana = _invite(local_env, admin["token"], username="dana")
    assert _accept(
        local_env, dana["invitation"]["token"], "dana-password-123"
    ).status_code == 200
    dana_id = dana["user_id"]

    created_org = client.post(
        "/api/orgs", headers=_h(admin["token"]),
        json={"id": "org:other", "name": "其他组织", "org_admin": admin["user"]["id"]},
    )
    assert created_org.status_code == 201

    added = client.post(
        "/api/orgs/org:other/invitations", headers=_h(admin["token"]),
        json={"username": "dana", "role": "org_admin"},
    )
    assert added.status_code == 201, added.text
    assert added.json() == {
        "user_id": dana_id, "membership_added": True, "invitation": None,
    }
    membership = local_env["backend"].read_membership(dana_id, "org:other")
    assert membership is not None and membership["role"] == "org_admin"
    assert any(
        row["user_id"] == dana_id
        for row in local_env["backend"].list_members("org:other")
    )
    # 已有成员（同组织再邀）→ 409 member_exists
    again = client.post(
        "/api/orgs/org:other/invitations", headers=_h(admin["token"]),
        json={"username": "dana", "role": "member"},
    )
    assert again.status_code == 409
    assert again.json()["code"] == "member_exists"

    # disabled 用户 → 409 user_disabled（先于成员关系判定）
    assert client.patch(
        f"/api/users/{dana_id}", headers=_h(admin["token"]),
        json={"disabled": True},
    ).status_code == 200
    disabled = client.post(
        "/api/orgs/org:other/invitations", headers=_h(admin["token"]),
        json={"username": "dana", "role": "member"},
    )
    assert disabled.status_code == 409
    assert disabled.json()["code"] == "user_disabled"

    # 已 invited 用户（全局预登记）→ 补发本组织邀请（membership_added=false）
    eve = client.post(
        "/api/users", headers=_h(admin["token"]),
        json={"username": "eve", "display_name": "伊芙"},
    )
    assert eve.status_code == 201, eve.text
    eve_id = eve.json()["user"]["id"]
    invited = client.post(
        "/api/orgs/org:other/invitations", headers=_h(admin["token"]),
        json={"username": "eve", "role": "member", "email": "eve@example.com"},
    )
    assert invited.status_code == 201, invited.text
    assert invited.json()["user_id"] == eve_id
    assert invited.json()["membership_added"] is False
    assert invited.json()["invitation"] is not None
    assert local_env["backend"].get_user(eve_id)["status"] == "invited"


# ============ 重置链接 ============


def test_reset_link_changes_password_and_revokes_sessions(local_env) -> None:
    """reset 链接：一次性改密 + tv++（旧会话 401）；disabled 409；未知 404。"""
    admin = _setup(local_env)
    client = local_env["client"]
    bob = _invite(local_env, admin["token"], username="bob")
    assert _accept(
        local_env, bob["invitation"]["token"], "bob-password-123"
    ).status_code == 200
    bob_id = bob["user_id"]
    bob_token = _login(local_env, "bob", "bob-password-123").json()["token"]
    assert client.get("/api/auth/me", headers=_h(bob_token)).status_code == 200

    reset = client.post(
        f"/api/users/{bob_id}/reset", headers=_h(admin["token"])
    )
    assert reset.status_code == 200, reset.text
    invitation = reset.json()["invitation"]
    assert set(reset.json()) == {"invitation"}
    purpose = local_env["db"].execute(
        "SELECT purpose, org_id, role FROM user_invitations WHERE id = ?",
        (invitation["id"],),
    ).fetchone()
    assert purpose == ("reset", None, None)

    lookup = client.post(
        "/api/auth/invitations/lookup", json={"token": invitation["token"]}
    )
    assert lookup.status_code == 200
    assert lookup.json()["purpose"] == "reset"
    assert lookup.json()["org_id"] is None and lookup.json()["role"] is None
    assert lookup.json()["username"] == "bob"

    accepted = _accept(
        local_env, invitation["token"], "reset-password-789"
    )
    assert accepted.status_code == 200, accepted.text
    assert client.get("/api/auth/me", headers=_h(bob_token)).status_code == 401, \
        "重置后旧会话必须失效（tv++）"
    assert _login(local_env, "bob", "bob-password-123").status_code == 401
    new_login = _login(local_env, "bob", "reset-password-789")
    assert new_login.status_code == 200
    # 重置不改变组织成员关系
    assert new_login.json()["orgs"][0]["org_id"] == "org:tax"
    assert _outbox(local_env, "auth.password_reset")

    # disabled 用户重置 → 409 user_disabled
    assert client.patch(
        f"/api/users/{bob_id}", headers=_h(admin["token"]),
        json={"disabled": True},
    ).status_code == 200
    blocked = client.post(
        f"/api/users/{bob_id}/reset", headers=_h(admin["token"])
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "user_disabled"
    # 未知用户 → 404
    unknown = client.post(
        "/api/users/u_does_not_exist/reset", headers=_h(admin["token"])
    )
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "user_not_found"


# ============ 审计无 secrets（TC-AUTH-08⑧） ============


def test_audit_outbox_never_contains_secrets(local_env) -> None:
    """全量 audit_outbox payload 不含密码明文、邀请 token、session token、hash。"""
    setup_password = "setup-password-111"
    admin = _setup(local_env, password=setup_password)
    client = local_env["client"]
    invitation = _invite(local_env, admin["token"], username="auditee")["invitation"]
    accept_password = "accept-password-222"
    accepted = _accept(local_env, invitation["token"], accept_password)
    assert accepted.status_code == 200
    login = _login(local_env, "auditee", accept_password)
    assert login.status_code == 200
    session_token = login.json()["token"]
    changed = client.post(
        "/api/auth/password", headers=_h(session_token),
        json={"old_password": accept_password, "new_password": "changed-password-333"},
    )
    assert changed.status_code == 200
    new_session = changed.json()["token"]
    assert client.post(
        "/api/auth/logout", headers=_h(new_session)
    ).status_code == 204

    rows = local_env["db"].execute("SELECT payload_json FROM audit_outbox").fetchall()
    payload_text = "\n".join(row[0] for row in rows)
    assert rows, "用例流程必须产生审计事件"
    for secret in (
        setup_password, accept_password, "changed-password-333",
        invitation["token"], session_token, new_session,
    ):
        assert secret not in payload_text, f"审计 payload 泄露明文秘密: {secret[:6]}…"
    hashes = local_env["db"].execute(
        "SELECT password_hash FROM users WHERE password_hash IS NOT NULL"
    ).fetchall()
    assert hashes
    for (password_hash,) in hashes:
        assert password_hash not in payload_text, "审计 payload 泄露 password_hash"
    token_hashes = local_env["db"].execute(
        "SELECT token_hash FROM user_invitations"
    ).fetchall()
    for (token_hash,) in token_hashes:
        assert token_hash not in payload_text, "审计 payload 泄露邀请 token 摘要"
