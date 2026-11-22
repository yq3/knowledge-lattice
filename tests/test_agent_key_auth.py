"""D26 阶段 2A：agent key 认证核心（issue #34——`local` 形态 agent 长期凭据）。

双后端参数化（``local_env``——sqlite + pg 同一代码；pg 臂需 ``LATTICE_PG_DSN``，
门禁脚本把 skip 视为失败）。api 层 key 端点属阶段 2B（本文件不依赖），key 一律
经 ``backend.create_agent_key`` 直造（阶段 1 库底座——AgentKeyBackend）。

覆盖：
- ``generate_agent_key`` / ``hash_agent_key`` 形态（前缀/展示前缀/摘要）；
- ``authenticate_agent_key`` 成功：via/act/org_claim/user_id/is_system_admin；
- 拒绝矩阵：非 local 形态 / 未知 hash / revoked / expired（UPDATE 造过去时间）/
  用户 disabled / 状态非 active / 用户不存在 —— 统一 AuthError(401)；
- ``authenticate`` 顶部前缀分流：``lka_`` 失败**不 fallback** dev JWT/静态 token；
- ``last_used_at``：首次认证回写、60s 内节流不重写、窗口外重写、touch 异常不阻断；
- ``build_query_event`` 身份三键（act/via/entry）恒进 detail_json（缺省 None、
  原 detail 键保留）；
- REST 组织路径端点：key 绑 A 调 B → 403 ``org_mismatch``（sysadmin key 同受限）；
- 集成：agent key 调 REST search 的查询审计带 act/via/entry="rest"。
"""

from __future__ import annotations

import json
import logging
import secrets
import uuid

import pytest

from helpers import FUTURE_TS, PAST_TS

ADMIN = {
    "username": "admin",
    "password": "admin-password-123",
    "display_name": "管理员",
    "org_id": "org:tax",
    "org_name": "税务组织",
}
ORG = "org:tax"
ORG_OTHER = "org:other-tax"


# ============ 造数助手 ============


def _setup(env) -> dict:
    resp = env["client"].post("/api/setup", json=ADMIN)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _setup_admin_id(env) -> str:
    row = env["db"].execute(
        "SELECT id FROM users WHERE username = 'admin'"
    ).fetchone()
    assert row is not None
    return row[0]


def _insert_org(env, org_id: str, name: str) -> None:
    env["db"].execute("INSERT INTO orgs(id, name) VALUES(?, ?)", (org_id, name))


def _insert_user(
    env, user_id: str, *, orgs=(), status: str = "active",
    disabled_at: str | None = None, is_system_admin: bool = False,
) -> None:
    """直插账号（密码栏留空——agent key 认证不读口令）+ 成员关系。"""
    env["db"].execute(
        "INSERT INTO users(id, username, is_system_admin, status, disabled_at)"
        " VALUES(?, ?, ?, ?, ?)",
        (user_id, user_id, 1 if is_system_admin else 0, status, disabled_at),
    )
    for org_id in orgs:
        env["db"].execute(
            "INSERT INTO user_org_memberships(user_id, org_id, role)"
            " VALUES(?, ?, 'member')",
            (user_id, org_id),
        )
    env["db"].commit()


def _create_key(
    env, *, user_id: str, org_id: str = ORG, label: str = "ci-agent",
    expires_at: str | None = None,
) -> tuple[str, dict]:
    """直造 key（阶段 2B 前无 api 端点）：返回 (明文, 库行)。"""
    from knowledge_lattice.domain.agent_keys import generate_agent_key

    plaintext, prefix, token_hash = generate_agent_key()
    row = env["backend"].create_agent_key(
        key_id=f"ak:{uuid.uuid4()}",
        org_id=org_id,
        user_id=user_id,
        label=label,
        token_hash=token_hash,
        prefix=prefix,
        created_by="u:tester",
        expires_at=expires_at,
    )
    return plaintext, row


def _auth(env, token: str):
    from knowledge_lattice.domain.agent_keys import authenticate_agent_key

    return authenticate_agent_key(env["backend"], env["settings"], token)


def _key_row(env, token: str) -> dict | None:
    from knowledge_lattice.domain.agent_keys import hash_agent_key

    return env["backend"].get_agent_key_by_hash(hash_agent_key(token))


def _set_last_used(env, key_id: str, value: str | None) -> None:
    env["db"].execute(
        "UPDATE agent_keys SET last_used_at = ? WHERE id = ?", (value, key_id)
    )
    env["db"].commit()


# ============ key 形态 ============


def test_generate_and_hash_agent_key() -> None:
    """plaintext = lka_ + token_urlsafe(32)；prefix=前 12 字符；摘要 64 hex。"""
    from knowledge_lattice.domain.agent_keys import (
        AGENT_KEY_PREFIX,
        generate_agent_key,
        hash_agent_key,
    )

    plaintext, prefix, token_hash = generate_agent_key()
    assert plaintext.startswith(AGENT_KEY_PREFIX)
    assert len(plaintext) > len(AGENT_KEY_PREFIX) + 32  # 32 字节随机源
    assert prefix == plaintext[:12] and len(prefix) == 12
    assert token_hash == hash_agent_key(plaintext) and len(token_hash) == 64
    assert all(c in "0123456789abcdef" for c in token_hash)
    assert generate_agent_key()[0] != plaintext, "每次生成须为新随机 key"


# ============ 认证成功 ============


def test_authenticate_agent_key_success(local_env) -> None:
    """成功：via=agent_key / act=label / org_claim=key.org / user_id / 管理标记。"""
    admin = _setup(local_env)
    admin_id = admin["user"]["id"]
    token, row = _create_key(
        local_env, user_id=admin_id, label="tax-agent", expires_at=None
    )

    auth = _auth(local_env, token)
    assert auth.user_id == admin_id
    assert auth.org_claim == ORG
    assert auth.via == "agent_key"
    assert auth.act == "tax-agent"
    assert auth.is_system_admin is True  # setup 管理员

    # 非管理员成员：同一认证面按用户行取权限（role 不在 AuthContext，成员资格
    # 由 api 层每请求校验——key 不绕过 ACL）
    _insert_user(local_env, "u_member", orgs=[ORG])
    member_token, _ = _create_key(
        local_env, user_id="u_member", label="member-agent"
    )
    member_auth = _auth(local_env, member_token)
    assert member_auth.user_id == "u_member"
    assert member_auth.org_claim == ORG
    assert member_auth.act == "member-agent"
    assert member_auth.is_system_admin is False


# ============ 拒绝矩阵（一律 AuthError 401） ============


def test_agent_key_unknown_hash_401(local_env) -> None:
    """未知 key（含格式合法但库里没有）→ 统一 invalid agent key（不泄露存在性）。"""
    from knowledge_lattice.domain.auth import AuthError

    _setup(local_env)
    token = "lka_" + secrets.token_urlsafe(32)
    with pytest.raises(AuthError) as excinfo:
        _auth(local_env, token)
    assert excinfo.value.code == 401
    assert "invalid agent key" in str(excinfo.value)


def test_agent_key_revoked_401(local_env) -> None:
    from knowledge_lattice.domain.auth import AuthError

    admin = _setup(local_env)
    token, row = _create_key(local_env, user_id=admin["user"]["id"])
    local_env["backend"].revoke_agent_key(
        key_id=row["id"], org_id=ORG, revoked_by=admin["user"]["id"],
    )
    with pytest.raises(AuthError) as excinfo:
        _auth(local_env, token)
    assert excinfo.value.code == 401
    assert "revoked" in str(excinfo.value)


def test_agent_key_expired_401(local_env) -> None:
    """expires_at 过去（库格式字符串比较）→ 401 expired。"""
    from knowledge_lattice.domain.auth import AuthError

    admin = _setup(local_env)
    token, row = _create_key(
        local_env, user_id=admin["user"]["id"], expires_at=FUTURE_TS
    )
    # 直接 UPDATE 造过去时间（store 侧字段预留；判定归认证面）
    local_env["db"].execute(
        "UPDATE agent_keys SET expires_at = ? WHERE id = ?", (PAST_TS, row["id"])
    )
    local_env["db"].commit()
    with pytest.raises(AuthError) as excinfo:
        _auth(local_env, token)
    assert excinfo.value.code == 401
    assert "expired" in str(excinfo.value)


def test_agent_key_user_disabled_or_inactive_401(local_env) -> None:
    """key 不绕过用户状态：disabled / invited / 用户行不存在 → 401。"""
    from knowledge_lattice.domain.auth import AuthError

    _setup(local_env)
    _insert_user(local_env, "u_disabled", orgs=[ORG], disabled_at=PAST_TS)
    disabled_token, _ = _create_key(local_env, user_id="u_disabled")
    with pytest.raises(AuthError, match="user disabled"):
        _auth(local_env, disabled_token)

    _insert_user(local_env, "u_invited", orgs=[ORG], status="invited")
    invited_token, _ = _create_key(local_env, user_id="u_invited")
    with pytest.raises(AuthError, match="user not active"):
        _auth(local_env, invited_token)

    # 用户行不存在：FK 级联下 key 行也会被删，正常入口先落 unknown hash；这里
    # 注入 get_user_auth=None 覆盖防御分支（key 行在、用户读口为空）
    token, row = _create_key(local_env, user_id=_setup_admin_id(local_env))
    real = local_env["backend"].get_user_auth
    local_env["backend"].get_user_auth = lambda _uid: None
    try:
        with pytest.raises(AuthError, match="unknown user"):
            _auth(local_env, token)
    finally:
        local_env["backend"].get_user_auth = real


def test_agent_key_non_local_mode_401(local_env) -> None:
    """非 local 形态：agent key 整体关闭（401）——即使 key 行本身有效。"""
    import dataclasses

    from knowledge_lattice.domain.auth import AuthError, authenticate

    admin = _setup(local_env)
    token, _ = _create_key(local_env, user_id=admin["user"]["id"])
    sso_settings = dataclasses.replace(local_env["settings"], auth_mode="sso")

    with pytest.raises(AuthError) as excinfo:
        from knowledge_lattice.domain.agent_keys import authenticate_agent_key

        authenticate_agent_key(local_env["backend"], sso_settings, token)
    assert excinfo.value.code == 401
    assert "仅 local 形态可用" in str(excinfo.value)
    # authenticate 顶部同样分流（sso 形态不落回 dev JWT/静态 token）
    with pytest.raises(AuthError, match="仅 local 形态可用"):
        authenticate(local_env["backend"], sso_settings, token)


def test_agent_key_no_fallback_to_dev_forms(local_env) -> None:
    """lka_ 前缀失败不 fallback：即便静态 token 摘要撞上，也必须 401。"""
    from knowledge_lattice.domain.auth import AuthError, authenticate, hash_token

    admin = _setup(local_env)
    uid = admin["user"]["id"]
    token = "lka_" + secrets.token_urlsafe(32)
    # 若发生 static fallback，该行会命中——必须以 invalid agent key 拒绝
    local_env["db"].execute(
        "UPDATE users SET token_hash = ? WHERE id = ?", (hash_token(token), uid)
    )
    local_env["db"].commit()
    with pytest.raises(AuthError) as excinfo:
        authenticate(local_env["backend"], local_env["settings"], token)
    assert excinfo.value.code == 401
    assert "invalid agent key" in str(excinfo.value)
    assert "invalid token" not in str(excinfo.value)


# ============ last_used_at 节流 ============


def test_agent_key_last_used_throttle(local_env) -> None:
    """首次写；60s 窗口内不重写（值保持不变）；窗口外重写。"""
    from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

    admin = _setup(local_env)
    token, row = _create_key(local_env, user_id=admin["user"]["id"])
    assert _key_row(local_env, token)["last_used_at"] is None

    auth = _auth(local_env, token)
    assert auth.via == "agent_key"
    first = _key_row(local_env, token)["last_used_at"]
    assert first is not None, "首次认证须回写 last_used_at"

    # 60s 内：置哨兵 now-30（> cutoff）→ 二次认证不得重写（值原样）
    inside = add_seconds(utc_now_ts(), -30)
    _set_last_used(local_env, row["id"], inside)
    _auth(local_env, token)
    assert _key_row(local_env, token)["last_used_at"] == inside, (
        "60s 窗口内不得重复回写（节流）"
    )

    # 窗口外：置 now-120（< cutoff）→ 重写为当前时刻
    outside = add_seconds(utc_now_ts(), -120)
    _set_last_used(local_env, row["id"], outside)
    _auth(local_env, token)
    rewritten = _key_row(local_env, token)["last_used_at"]
    assert rewritten is not None and rewritten > outside


def test_agent_key_last_used_throttle_skips_store_write(local_env, monkeypatch) -> None:
    """domain 侧先判窗口：窗口内认证 **0 次** store 调用；窗口外**恰好 1 次**。

    store 的 `WHERE last_used_at < cutoff` 只保证值不变，UPDATE+commit 仍会每
    请求执行（SQLite 单写者热路径写放大）——本用例钉住「不触库」。
    """
    from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

    admin = _setup(local_env)
    token, row = _create_key(local_env, user_id=admin["user"]["id"])
    calls: list[tuple] = []
    real = local_env["backend"].touch_agent_key_last_used

    def spy(key_id: str, *, now: str, cutoff: str) -> bool:
        calls.append((key_id, now, cutoff))
        return real(key_id, now=now, cutoff=cutoff)

    monkeypatch.setattr(local_env["backend"], "touch_agent_key_last_used", spy)

    # 首次（last_used_at NULL）= 窗口外：恰好一次回写
    _auth(local_env, token)
    assert len(calls) == 1 and calls[0][0] == row["id"]

    # 窗口内（行值 now-30 >= cutoff）：认证成功但 0 次 store 调用、值不变
    inside = add_seconds(utc_now_ts(), -30)
    _set_last_used(local_env, row["id"], inside)
    before = len(calls)
    _auth(local_env, token)
    assert len(calls) == before, "窗口内不得触库（domain 侧先判节流）"
    assert _key_row(local_env, token)["last_used_at"] == inside

    # 窗口外（行值 now-120 < cutoff）：恰好 1 次 store 调用并回写
    outside = add_seconds(utc_now_ts(), -120)
    _set_last_used(local_env, row["id"], outside)
    before = len(calls)
    _auth(local_env, token)
    assert len(calls) == before + 1, "窗口外恰好一次 store 回写（不多不少）"
    assert calls[-1][0] == row["id"]
    assert _key_row(local_env, token)["last_used_at"] > outside


def test_agent_key_touch_failure_does_not_block(local_env, monkeypatch, caplog) -> None:
    """last_used_at 回写异常只告警——认证不得被旁路观测失败阻断。"""
    admin = _setup(local_env)
    token, _ = _create_key(local_env, user_id=admin["user"]["id"])

    def _boom(_key_id: str, *, now: str, cutoff: str) -> bool:
        raise RuntimeError("injected touch failure")

    monkeypatch.setattr(
        local_env["backend"], "touch_agent_key_last_used", _boom
    )
    with caplog.at_level(logging.WARNING):
        auth = _auth(local_env, token)
    assert auth.via == "agent_key"
    assert _key_row(local_env, token)["last_used_at"] is None, (
        "回写失败不得留下半写状态"
    )
    assert "last_used_at" in caplog.text


# ============ build_query_event 身份三键 ============


def test_build_query_event_identity_fields() -> None:
    """act/via/entry 恒进 detail_json；原 detail 键保留；缺省为 None。"""
    from knowledge_lattice.query_audit import build_query_event

    event = build_query_event(
        "search.query", org_id=ORG, actor="u1", detail={"query": "进项抵扣"},
        act="ci-agent", via="agent_key", entry="rest",
    )
    detail = json.loads(event["detail_json"])
    assert detail == {
        "query": "进项抵扣", "act": "ci-agent", "via": "agent_key",
        "entry": "rest",
    }

    # 缺省（人类直连/既有调用点未传）：三键恒出现、值为 None
    default = build_query_event("search.query", org_id=ORG, actor="u1")
    assert json.loads(default["detail_json"]) == {
        "act": None, "via": None, "entry": None,
    }


# ============ REST org 路径端点组织绑定 ============


def test_agent_key_org_mismatch_403(local_env) -> None:
    """key 绑 org:tax、用户同时是两组织成员：调 org:other-tax 路径 → 403
    org_mismatch（sysadmin key 同样受限——成员校验不再是唯一防线）。"""
    admin = _setup(local_env)
    uid = admin["user"]["id"]
    assert admin["user"]["is_system_admin"] is True
    _insert_org(local_env, ORG_OTHER, "另一组织")
    local_env["db"].execute(
        "INSERT INTO user_org_memberships(user_id, org_id, role) VALUES(?, ?, 'member')",
        (uid, ORG_OTHER),
    )
    local_env["db"].commit()
    token, _ = _create_key(local_env, user_id=uid, org_id=ORG, label="bound-tax")
    headers = {"Authorization": f"Bearer {token}"}

    ok = local_env["client"].get(f"/api/orgs/{ORG}/documents", headers=headers)
    assert ok.status_code == 200, ok.text

    denied = local_env["client"].get(
        f"/api/orgs/{ORG_OTHER}/documents", headers=headers
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["code"] == "org_mismatch"
    assert ORG in denied.json()["error"] and ORG_OTHER in denied.json()["error"]

    # 已有 400 语义不变：路径 org 与 X-Org-Id 头不一致 → 400（check_path_org 先）
    bad_header = local_env["client"].get(
        f"/api/orgs/{ORG}/documents",
        headers={**headers, "X-Org-Id": ORG_OTHER},
    )
    assert bad_header.status_code == 400


# ============ 集成：REST search 查询审计身份三键 ============


def test_rest_search_query_audit_identity_fields(local_env) -> None:
    """agent key 调 REST search → search.query accepted detail 带
    act=label / via=agent_key / entry=rest。"""
    admin = _setup(local_env)
    token, _ = _create_key(local_env, user_id=admin["user"]["id"], label="search-agent")
    resp = local_env["client"].post(
        "/api/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "进项抵扣", "top_k": 1},
    )
    assert resp.status_code == 200, resp.text
    service = local_env["app"].state.service
    service.query_audit.flush()
    rows = local_env["backend"].read_org_audit(
        ORG, action="search.query", limit=10
    )
    assert rows, "查询审计事件须落库"
    assert rows[0]["outcome"] == "accepted"
    detail = json.loads(rows[0]["detail_json"])
    assert detail["act"] == "search-agent"
    assert detail["via"] == "agent_key"
    assert detail["entry"] == "rest"
    assert detail["query"] == "进项抵扣"
