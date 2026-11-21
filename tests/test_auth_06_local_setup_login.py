"""TC-AUTH-06/07/10 local 形态：首启 setup / 登录会话 / 限流 / 改密 / MCP 边界。

双后端参数化（``local_env``——sqlite + pg 同一代码；pg 臂需 ``LATTICE_PG_DSN``，
门禁脚本把 skip 视为失败）。所有用例**空库启动**、管理员经 ``POST /api/setup``
真实造出；``app_env``（sso 形态）零改动，仅在本文件末验证 D25 路由面 404。

覆盖：
- config/setup-status 前后态、setup 201 + 首组织 org_admin membership +
  instance.setup 审计（payload 只含 id）、二次 409、弱密码/非法 username/
  首组织单参 400、init_password 门禁 403（独立 sqlite app）；
- login 成功（last_login_at 回写）/ me / logout 204；失败矩阵统一 401
  （unknown/bad_password/disabled/invited/no_password——审计 reason 区分）；
- 限流 429 + Retry-After；成功 reset 限流；
- 改密 tv++：旧 token 401、新 token 200、旧密码 401、弱密码 400；
- local session token 调 MCP → ToolError 含 401/local（REST 不受影响）；
- sso 形态：config/status 200 且双 false；login/setup/users/me 404。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

ADMIN = {
    "username": "admin",
    "password": "admin-password-123",
    "display_name": "管理员",
    "org_id": "org:tax",
    "org_name": "税务组织",
}
PASSWORD = ADMIN["password"]
NEW_PASSWORD = "new-password-456"


# ============ 助手 ============


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup(env, **overrides) -> dict:
    resp = env["client"].post("/api/setup", json={**ADMIN, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _outbox(env, event_type: str | None = None) -> list[dict]:
    if event_type is None:
        rows = env["db"].execute(
            "SELECT payload_json FROM audit_outbox"
        ).fetchall()
    else:
        rows = env["db"].execute(
            "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
            (event_type,),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def _insert_user(
    env, *, user_id: str, username: str, password: str | None,
    status: str = "active", disabled: bool = False,
) -> None:
    """直插用户（登录失败矩阵的 disabled/invited/未设密三类造数）。"""
    from knowledge_lattice.domain.accounts import hash_password
    from knowledge_lattice.store.taskclock import utc_now_ts

    env["db"].execute(
        "INSERT INTO users(id, username, password_hash, status, disabled_at)"
        " VALUES(?, ?, ?, ?, ?)",
        (
            user_id,
            username,
            hash_password(password) if password else None,
            status,
            utc_now_ts() if disabled else None,
        ),
    )
    env["db"].commit()


def _mcp_client(app, headers: dict) -> Client:
    def factory(**kw):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)

    return Client(
        StreamableHttpTransport(
            url="http://testserver/mcp", headers=headers, httpx_client_factory=factory
        )
    )


# ============ TC-AUTH-06 首启 setup ============


def test_setup_config_status_and_first_admin(local_env) -> None:
    """① config/status 前置态 → setup 201（首 admin + 首组织 + 审计）→ 后置态。"""
    client = local_env["client"]
    config = client.get("/api/auth/config")
    assert config.status_code == 200
    assert config.json() == {
        "auth_mode": "local",
        "setup_needed": True,
        "local_login_enabled": True,
    }
    assert client.get("/api/setup/status").json() == {
        "setup_needed": True,
        "completed": False,
    }

    body = _setup(local_env)
    assert set(body) == {"token", "expires_at", "user", "orgs"}
    user = body["user"]
    assert user["username"] == "admin"
    assert user["display_name"] == "管理员"
    assert user["status"] == "active"
    assert user["is_system_admin"] is True
    assert user["last_login_at"] is None  # setup 不写 last_login_at（登录才写）
    # 显式投影：无密码/令牌摘要；响应文本不含密码明文
    assert "password_hash" not in user and "token_hash" not in user
    assert PASSWORD not in json.dumps(body, ensure_ascii=False)
    assert body["orgs"] == [
        {"org_id": "org:tax", "name": "税务组织", "role": "org_admin",
         "status": "active"}
    ]

    assert client.get("/api/auth/config").json()["setup_needed"] is False
    assert client.get("/api/setup/status").json() == {
        "setup_needed": False,
        "completed": True,
    }
    rows = local_env["db"].execute(
        "SELECT username, status, is_system_admin, password_hash FROM users"
    ).fetchall()
    assert len(rows) == 1 and rows[0][0] == "admin"
    assert rows[0][1] == "active" and bool(rows[0][2]) is True
    assert rows[0][3] and rows[0][3].startswith("scrypt$")
    membership = local_env["backend"].read_membership(user["id"], "org:tax")
    assert membership is not None and membership["role"] == "org_admin"
    assert local_env["backend"].get_instance_setup() is not None
    # 审计与建档同事务：payload 只含 user/org id（无密码）
    assert _outbox(local_env, "instance.setup") == [
        {"user_id": user["id"], "org_id": "org:tax"}
    ]


def test_setup_second_time_409(local_env) -> None:
    """③ 二次 setup → 409 setup_completed（用户数不变）。"""
    _setup(local_env)
    resp = local_env["client"].post("/api/setup", json=ADMIN)
    assert resp.status_code == 409
    assert resp.json()["code"] == "setup_completed"
    count = local_env["db"].execute("SELECT count(*) FROM users").fetchone()[0]
    assert count == 1


def test_setup_rejects_invalid_input(local_env) -> None:
    """弱密码 400 / username 非法 400 / 首组织单参 400——均零残留。"""
    client = local_env["client"]
    weak = client.post("/api/setup", json={**ADMIN, "password": "short"})
    assert weak.status_code == 400 and weak.json()["code"] == "weak_password"
    bad_name = client.post("/api/setup", json={**ADMIN, "username": "ab"})
    assert bad_name.status_code == 400
    assert bad_name.json()["code"] == "invalid_username"
    org_single = client.post("/api/setup", json={**ADMIN, "org_name": None})
    assert org_single.status_code == 400
    assert org_single.json()["code"] == "invalid_org"
    count = local_env["db"].execute("SELECT count(*) FROM users").fetchone()[0]
    assert count == 0, "校验失败不得留半状态（零用户）"
    assert local_env["backend"].get_instance_setup() is None


def test_setup_init_password_gate(tmp_path) -> None:
    """⑥ LATTICE_INIT_PASSWORD 门禁：缺失/错误 403 且零残留；正确 201。

    独立 sqlite app（init_password 是装配期配置——``local_env`` 恒空值；
    本用例不涉及方言差异，sqlite 单臂即可）。
    """
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from fake_providers import FakeEmbedder

    settings = Settings(
        environment="test",
        data_dir=tmp_path,
        auth_mode="local",
        session_secret="test-session-secret-0123456789abcdef",
        init_password="init-gate-secret",
        password_min_len=10,
        probe_interval_s=0,
        maintenance_interval_s=0,
        worker_mode="inline",
    )
    app = create_app(
        settings, embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
        run_startup_probe=False,
    )
    with TestClient(app) as client:
        missing = client.post("/api/setup", json=ADMIN)
        assert missing.status_code == 403
        assert missing.json()["code"] == "invalid_init_password"
        wrong = client.post("/api/setup", json={**ADMIN, "init_password": "nope"})
        assert wrong.status_code == 403
        assert app.state.service.backend.count_users() == 0
        assert app.state.service.backend.get_instance_setup() is None
        ok = client.post(
            "/api/setup", json={**ADMIN, "init_password": "init-gate-secret"}
        )
        assert ok.status_code == 201


# ============ TC-AUTH-07 登录与会话 ============


def test_login_success_me_logout(local_env) -> None:
    """① 成功登录（last_login_at 回写）/ me / logout 204（无状态——G-34）。"""
    admin = _setup(local_env)
    client = local_env["client"]
    login = client.post(
        "/api/auth/login", json={"username": "admin", "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert set(body) == {"token", "expires_at", "user", "orgs"}
    assert body["user"]["id"] == admin["user"]["id"]
    assert body["user"]["last_login_at"] is not None, "登录成功须回写 last_login_at"
    assert body["orgs"][0]["org_id"] == "org:tax"
    assert "password_hash" not in body["user"]

    me = client.get("/api/auth/me", headers=_h(body["token"]))
    assert me.status_code == 200
    assert me.json()["user"]["id"] == admin["user"]["id"]
    assert me.json()["user"]["last_login_at"] is not None
    assert me.json()["orgs"] == [
        {"org_id": "org:tax", "name": "税务组织", "role": "org_admin",
         "status": "active"}
    ]
    # 无/错 token → 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=_h("garbage")).status_code == 401

    out = client.post("/api/auth/logout", headers=_h(body["token"]))
    assert out.status_code == 204
    assert out.content == b""
    assert any(
        item["user_id"] == admin["user"]["id"]
        for item in _outbox(local_env, "auth.logout")
    )
    # 无服务端撤销：登出后 token 仍有效（客户端清 token——G-34）
    assert client.get("/api/auth/me", headers=_h(body["token"])).status_code == 200


def test_login_failure_matrix_uniform_401(local_env) -> None:
    """②③④ 未知/错密/disabled/invited/未设密 → 统一 401 + 审计 reason 区分。"""
    _setup(local_env)
    client = local_env["client"]
    _insert_user(local_env, user_id="u_invited", username="invited1",
                 password="invited-password-1", status="invited")
    _insert_user(local_env, user_id="u_disabled", username="disabled1",
                 password="disabled-password-1", disabled=True)
    _insert_user(local_env, user_id="u_nopassword", username="nopw1", password=None)
    cases = [
        ("ghost", "whatever-password"),          # 未知用户
        ("admin", "wrong-password-xyz"),         # 密码错
        ("disabled1", "disabled-password-1"),    # 停用（密码正确亦拒）
        ("invited1", "invited-password-1"),      # invited（未激活）
        ("nopw1", "nopw-password-1"),            # 未设本地密码（NULL hash）
    ]
    messages = set()
    for username, password in cases:
        resp = client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        assert resp.status_code == 401, (username, resp.text)
        assert resp.json()["code"] == "invalid_credentials"
        messages.add(resp.json()["error"])
    assert len(messages) == 1, "失败文案必须统一（不区分未知/错密/停用）"
    refused = _outbox(local_env, "auth.login_refused")
    reasons = {item["reason"] for item in refused}
    assert {
        "unknown_user", "bad_password", "disabled", "invited", "no_password",
    } <= reasons
    payload_text = json.dumps(refused, ensure_ascii=False)
    assert "wrong-password-xyz" not in payload_text
    assert "disabled-password-1" not in payload_text


def test_login_lockout_429_with_retry_after(local_env) -> None:
    """⑤ 连续失败超限 → 429 login_locked + Retry-After；锁定期间正确密码亦 429。"""
    _setup(local_env)
    client = local_env["client"]
    for _ in range(5):
        resp = client.post(
            "/api/auth/login", json={"username": "admin", "password": "bad-password"}
        )
        assert resp.status_code == 401
    locked = client.post(
        "/api/auth/login", json={"username": "admin", "password": PASSWORD}
    )
    assert locked.status_code == 429
    assert locked.json()["code"] == "login_locked"
    retry_after = locked.headers.get("retry-after")
    assert retry_after is not None and int(retry_after) >= 1
    # 键含 username——其他账号不受影响（登录面仍 401 而非 429）
    other = client.post(
        "/api/auth/login", json={"username": "someone-else", "password": "bad"}
    )
    assert other.status_code == 401
    assert any(
        item["reason"] == "locked"
        for item in _outbox(local_env, "auth.login_refused")
    ), "锁定拒绝须留 auth.login_refused（reason=locked）"


def test_login_success_resets_limiter(local_env) -> None:
    """⑤ 对称面：成功登录 reset 失败计数（4 次失败 + 成功 + 4 次失败仍不锁）。"""
    _setup(local_env)
    client = local_env["client"]
    for _ in range(4):
        assert client.post(
            "/api/auth/login", json={"username": "admin", "password": "bad"}
        ).status_code == 401
    ok = client.post(
        "/api/auth/login", json={"username": "admin", "password": PASSWORD}
    )
    assert ok.status_code == 200
    for _ in range(4):
        assert client.post(
            "/api/auth/login", json={"username": "admin", "password": "bad"}
        ).status_code == 401, "成功登录须清零失败计数"


def test_password_change_revokes_old_sessions(local_env) -> None:
    """⑥ 改密 tv++：旧 token 401、新 token 200、旧密码 401、弱密码 400。"""
    _setup(local_env)
    client = local_env["client"]
    login = client.post(
        "/api/auth/login", json={"username": "admin", "password": PASSWORD}
    )
    old_token = login.json()["token"]
    # 旧密错 → 401；弱新密 → 400（均不落库）
    wrong_old = client.post(
        "/api/auth/password",
        headers=_h(old_token),
        json={"old_password": "not-the-password", "new_password": NEW_PASSWORD},
    )
    assert wrong_old.status_code == 401
    assert wrong_old.json()["code"] == "invalid_credentials"
    weak_new = client.post(
        "/api/auth/password",
        headers=_h(old_token),
        json={"old_password": PASSWORD, "new_password": "short"},
    )
    assert weak_new.status_code == 400
    assert weak_new.json()["code"] == "weak_password"

    changed = client.post(
        "/api/auth/password",
        headers=_h(old_token),
        json={"old_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200, changed.text
    assert set(changed.json()) == {"token", "expires_at"}
    new_token = changed.json()["token"]
    assert client.get("/api/auth/me", headers=_h(old_token)).status_code == 401, \
        "改密后旧会话必须失效（tv++）"
    assert client.get("/api/auth/me", headers=_h(new_token)).status_code == 200
    old_login = client.post(
        "/api/auth/login", json={"username": "admin", "password": PASSWORD}
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/auth/login", json={"username": "admin", "password": NEW_PASSWORD}
    )
    assert new_login.status_code == 200
    assert any(
        item["user_id"] == new_login.json()["user"]["id"]
        for item in _outbox(local_env, "auth.password_changed")
    )


# ============ TC-AUTH-07⑨ / TC-AUTH-10 MCP 边界 ============


def test_local_session_token_rejected_by_mcp(local_env) -> None:
    """⑨ local session token 调 MCP → ToolError 401/local；REST 不受影响。"""
    admin = _setup(local_env)
    token = admin["token"]
    # REST 不受影响：local session + X-Org-Id 可正常检索（D25：session 只封 MCP）
    rest = local_env["client"].post(
        "/api/search", headers={**_h(token), "X-Org-Id": "org:tax"},
        json={"query": "增值税"},
    )
    assert rest.status_code == 200, rest.text

    async def flow():
        async with _mcp_client(
            local_env["app"], {"Authorization": f"Bearer {token}"}
        ) as client:
            await client.call_tool("search", {"query": "增值税"})

    with pytest.raises(ToolError) as excinfo:
        asyncio.run(flow())
    message = str(excinfo.value)
    assert "401" in message
    assert "local" in message
    assert "MCP" in message
    assert token not in message, "错误消息不得回显 token 明文"


# ============ TC-AUTH-10 sso 形态：D25 路由面 404（现状零变化） ============


def test_sso_mode_d25_surface(app_env) -> None:
    """⑤ sso 形态：config/status 200 且双 false；local 端点全部 404。"""
    client = app_env["client"]
    config = client.get("/api/auth/config")
    assert config.status_code == 200
    assert config.json() == {
        "auth_mode": "sso",
        "setup_needed": False,
        "local_login_enabled": False,
    }
    assert client.get("/api/setup/status").json() == {
        "setup_needed": False,
        "completed": False,
    }
    for method, path, payload in (
        ("post", "/api/auth/login", {"username": "u_full", "password": "x"}),
        ("post", "/api/setup", ADMIN),
        ("get", "/api/users", None),
        ("get", "/api/auth/me", None),
        ("post", "/api/auth/logout", None),
        ("post", "/api/auth/invitations/lookup", {"token": "x"}),
        ("get", "/api/orgs/org:tax/invitations", None),
    ):
        resp = getattr(client, method)(path, json=payload) if payload is not None \
            else getattr(client, method)(path)
        assert resp.status_code == 404, (
            f"sso 形态 {method.upper()} {path} 须 404（local_router 未注册）"
            f"——got {resp.status_code}"
        )
    # dev JWT 仍可（sso 形态既有语义——MCP 侧由 e2e_06 回归覆盖）
    jwt = app_env["jwt"]("u_full", org="org:tax")
    assert client.get("/api/auth/me", headers=_h(jwt)).status_code == 404
