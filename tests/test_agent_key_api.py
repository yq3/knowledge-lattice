"""D26 阶段 2B：agent key REST API + MCP 冒烟（issue #34——`local` 形态管理面）。

双后端参数化（``local_env``——sqlite + pg 同一代码；pg 臂需 ``LATTICE_PG_DSN``，
门禁脚本把 skip 视为失败）。每用例空库启动，管理员经 ``POST /api/setup`` 真实
造出；sso 形态 404 用 ``app_env``（既有 SSO 壳，零改动）。

覆盖：
- 创建/列表/认证/撤销全链：201 明文仅响应一次、列表无 token_hash/无明文、
  ``authenticate`` 与 REST 可用、撤销即时 401、二次 DELETE 幂等 204；
- 权限矩阵：member key 三端点 403 org_admin_required；他组织 org_admin（key 绑
  A 调 B）403 org_mismatch / 非 key 身份 403 org_admin_required；sysadmin
  （membership role=member）用 key 管理 → 允许（豁免）；
- 创建目标校验：未知用户 404、非成员 400、disabled/invited 400（零残留）；
- label/请求体校验：strip 后 1..64、控制字符 400、未知字段 422；
- 组织上下文：X-Org-Id 不一致 400；key 绑 A 调 B 403（sysadmin key 同样）；
- 停用组织：sysadmin 可管（撤销泄露 key）；org_admin 403 org_disabled；
- 审计：agent_key.created/revoked 同事务落 outbox、payload 不含明文/摘要、
  二次撤销零新审计；
- MCP 冒烟：agent key 调 search 成功；X-Org-Id 不一致 ToolError 400；
  query_audit.flush 后 read_org_audit 断言 act/via/entry；
- sso 形态：GET/POST/DELETE 同路径 404。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from helpers import PAST_TS

ADMIN = {
    "username": "admin",
    "password": "admin-password-123",
    "display_name": "管理员",
    "org_id": "org:tax",
    "org_name": "税务组织",
}
ORG = "org:tax"
ORG_OTHER = "org:other-tax"

_KEY_FIELDS = {
    "id", "org_id", "user_id", "user_username", "label", "prefix",
    "created_by", "created_at", "last_used_at", "revoked_at", "revoked_by",
    "expires_at",
}


# ============ 助手 ============


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup(env) -> dict:
    resp = env["client"].post("/api/setup", json=ADMIN)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _insert_org(env, org_id: str, name: str) -> None:
    env["db"].execute("INSERT INTO orgs(id, name) VALUES(?, ?)", (org_id, name))
    env["db"].commit()


def _insert_user(
    env, user_id: str, *, orgs=(), role: str = "member", status: str = "active",
    disabled_at: str | None = None, is_system_admin: bool = False,
) -> None:
    """直插账号（无密码——key 认证不读口令；local session 走 dev JWT 兜底）。"""
    env["db"].execute(
        "INSERT INTO users(id, username, is_system_admin, status, disabled_at)"
        " VALUES(?, ?, ?, ?, ?)",
        (
            user_id, user_id, 1 if is_system_admin else 0, status, disabled_at,
        ),
    )
    for org_id in orgs:
        env["db"].execute(
            "INSERT INTO user_org_memberships(user_id, org_id, role)"
            " VALUES(?, ?, ?)",
            (user_id, org_id, role),
        )
    env["db"].commit()


def _create_key(
    env, token: str, *, user_id: str, label: str = "ci-agent", org: str = ORG,
) -> dict:
    resp = env["client"].post(
        f"/api/orgs/{org}/agent-keys",
        headers=_h(token),
        json={"user_id": user_id, "label": label},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _list_keys(env, token: str, *, org: str = ORG) -> dict:
    resp = env["client"].get(f"/api/orgs/{org}/agent-keys", headers=_h(token))
    assert resp.status_code == 200, resp.text
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


def _mcp_client(app, headers: dict) -> Client:
    def factory(**kw):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)

    return Client(
        StreamableHttpTransport(
            url="http://testserver/mcp", headers=headers, httpx_client_factory=factory
        )
    )


# ============ 全链：创建 / 列表 / 认证 / 撤销 ============


def test_create_list_authenticate_and_revoke_flow(local_env) -> None:
    """admin 自建 key → 201（明文仅响应一次）→ 列表无 token_hash/无明文 →
    authenticate/REST 可用 → DELETE 204 后 401 → 二次 DELETE 幂等 204。"""
    admin = _setup(local_env)
    admin_id = admin["user"]["id"]
    token = admin["token"]
    client = local_env["client"]

    created = _create_key(
        local_env, token, user_id=admin_id, label="agent-a"
    )
    plaintext = created["key"]
    key_id = created["id"]
    assert plaintext.startswith("lka_")
    assert created["prefix"] == plaintext[:12]
    assert set(created) == _KEY_FIELDS | {"key"}
    assert created["org_id"] == ORG
    assert created["user_id"] == admin_id
    assert created["user_username"] == "admin"
    assert created["label"] == "agent-a"
    assert created["created_by"] == admin_id
    assert created["created_at"] is not None
    assert created["expires_at"] is None
    assert created["revoked_at"] is None and created["revoked_by"] is None
    assert "token_hash" not in created

    # 列表：行投影、无 token_hash、无明文
    listing = _list_keys(local_env, token)
    rows = listing["keys"]
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == key_id and row["user_username"] == "admin"
    assert all("token_hash" not in item for item in rows)
    assert plaintext not in client.get(
        f"/api/orgs/{ORG}/agent-keys", headers=_h(token)
    ).text

    # domain 认证 + REST 可用（key 不绕过 ACL：admin 有成员关系）
    from knowledge_lattice.domain.auth import authenticate

    auth = authenticate(local_env["backend"], local_env["settings"], plaintext)
    assert auth.via == "agent_key" and auth.act == "agent-a"
    assert auth.org_claim == ORG and auth.user_id == admin_id
    key_headers = _h(plaintext)
    ok = client.get(f"/api/orgs/{ORG}/documents", headers=key_headers)
    assert ok.status_code == 200, ok.text
    # last_used_at 由认证热路径回写
    assert _list_keys(local_env, token)["keys"][0]["last_used_at"] is not None

    # 撤销 → 204；再用 → 401；二次撤销幂等 204
    revoked = client.delete(
        f"/api/orgs/{ORG}/agent-keys/{key_id}", headers=_h(token)
    )
    assert revoked.status_code == 204, revoked.text
    denied = client.get(f"/api/orgs/{ORG}/documents", headers=key_headers)
    assert denied.status_code == 401, denied.text
    again = client.delete(
        f"/api/orgs/{ORG}/agent-keys/{key_id}", headers=_h(token)
    )
    assert again.status_code == 204, again.text
    missing = client.delete(
        f"/api/orgs/{ORG}/agent-keys/ak_unknown", headers=_h(token)
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "agent_key_not_found"

    row = _list_keys(local_env, token)["keys"][0]
    assert row["revoked_at"] is not None
    assert row["revoked_by"] == admin_id

    # 审计：created/revoked 各一条；payload 无明文/摘要；二次撤销零新审计
    created_events = _outbox(local_env, "agent_key.created")
    revoked_events = _outbox(local_env, "agent_key.revoked")
    assert created_events == [{
        "actor": admin_id,
        "key_id": key_id,
        "org_id": ORG,
        "user_id": admin_id,
        "label": "agent-a",
    }]
    assert revoked_events == [{
        "actor": admin_id, "key_id": key_id, "org_id": ORG,
    }]
    payload_text = json.dumps(
        created_events + revoked_events, ensure_ascii=False
    )
    assert plaintext not in payload_text
    assert "token_hash" not in payload_text


# ============ 权限矩阵 ============


def test_permission_matrix_member_other_org_and_sysadmin_exemption(local_env) -> None:
    """member key 三端点 403；他组织 org_admin 403；sysadmin(member) key 放行。"""
    admin = _setup(local_env)
    token = admin["token"]
    client = local_env["client"]

    _insert_user(local_env, "u_member", orgs=[ORG], role="member")
    member_key = _create_key(
        local_env, token, user_id="u_member", label="member-agent"
    )["key"]
    for method, path, body in (
        ("get", f"/api/orgs/{ORG}/agent-keys", None),
        ("post", f"/api/orgs/{ORG}/agent-keys", {
            "user_id": "u_member", "label": "self",
        }),
        ("delete", f"/api/orgs/{ORG}/agent-keys/ak_missing", None),
    ):
        resp = (
            getattr(client, method)(path, headers=_h(member_key), json=body)
            if body is not None
            else getattr(client, method)(path, headers=_h(member_key))
        )
        assert resp.status_code == 403, f"{method} {path}: {resp.text}"
        assert resp.json()["code"] == "org_admin_required"

    # 他组织 org_admin：key 绑 ORG_OTHER 调 ORG 路径 → 403 org_mismatch
    _insert_org(local_env, ORG_OTHER, "另一组织")
    _insert_user(local_env, "u_other_admin", orgs=[ORG_OTHER], role="org_admin")
    other_created = _create_key(
        local_env, token, user_id="u_other_admin", label="other-agent",
        org=ORG_OTHER,
    )
    other_key = other_created["key"]
    # 跨组织撤销：store 按 (id, org) 定位 → 404（不泄露他组织 key）
    cross = client.delete(
        f"/api/orgs/{ORG}/agent-keys/{other_created['id']}", headers=_h(token)
    )
    assert cross.status_code == 404
    assert cross.json()["code"] == "agent_key_not_found"
    for method, body in (
        ("get", None),
        ("post", {"user_id": "u_member", "label": "cross"}),
        ("delete", None),
    ):
        url = f"/api/orgs/{ORG}/agent-keys"
        if method == "delete":
            url = f"{url}/ak_missing"
        resp = (
            getattr(client, method)(url, headers=_h(other_key), json=body)
            if body is not None
            else getattr(client, method)(url, headers=_h(other_key))
        )
        assert resp.status_code == 403, f"{method}: {resp.text}"
        assert resp.json()["code"] == "org_mismatch"

    # 非 key 身份（dev JWT）的他组织 org_admin：无本组织成员关系 → 403
    from knowledge_lattice.domain.auth import issue_dev_jwt

    other_jwt = issue_dev_jwt(
        local_env["settings"], user_id="u_other_admin", org=ORG_OTHER
    )
    resp = client.get(
        f"/api/orgs/{ORG}/agent-keys", headers=_h(other_jwt)
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "org_admin_required"

    # 本组织 org_admin（非 sysadmin）可正常创建/列表
    _insert_user(local_env, "u_admin2", orgs=[ORG], role="org_admin")
    admin2_jwt = issue_dev_jwt(
        local_env["settings"], user_id="u_admin2", org=ORG
    )
    by_admin = _create_key(
        local_env, admin2_jwt, user_id="u_member", label="by-org-admin"
    )
    assert by_admin["created_by"] == "u_admin2"
    assert any(
        row["id"] == by_admin["id"]
        for row in _list_keys(local_env, admin2_jwt)["keys"]
    )

    # sysadmin 豁免：membership role=member，但用其 key 可管理（创建/列表/撤销）
    _insert_user(
        local_env, "u_sys", orgs=[ORG], role="member", is_system_admin=True
    )
    sys_key = _create_key(
        local_env, token, user_id="u_sys", label="sys-agent"
    )["key"]
    assert len(_list_keys(local_env, sys_key)["keys"]) >= 1
    created = _create_key(
        local_env, sys_key, user_id="u_member", label="by-sysadmin"
    )
    assert created["created_by"] == "u_sys"
    deleted = client.delete(
        f"/api/orgs/{ORG}/agent-keys/{created['id']}", headers=_h(sys_key)
    )
    assert deleted.status_code == 204, deleted.text
    assert _list_keys(local_env, token)["keys"]  # admin 仍可读


# ============ 创建目标校验 ============


def test_create_target_validation(local_env) -> None:
    """未知用户 404；非成员 400 member_not_found；disabled/invited 400
    user_not_active——且失败路径零 key 行/零 create 审计。"""
    admin = _setup(local_env)
    token = admin["token"]
    client = local_env["client"]

    _insert_user(local_env, "u_member", orgs=[ORG])
    _insert_user(local_env, "u_outsider")  # 无任何组织成员关系
    _insert_user(local_env, "u_disabled", orgs=[ORG], disabled_at=PAST_TS)
    _insert_user(local_env, "u_invited", orgs=[ORG], status="invited")

    for user_id, status, code in (
        ("u_ghost", 404, "user_not_found"),
        ("u_outsider", 400, "member_not_found"),
        ("u_disabled", 400, "user_not_active"),
        ("u_invited", 400, "user_not_active"),
    ):
        resp = client.post(
            f"/api/orgs/{ORG}/agent-keys",
            headers=_h(token),
            json={"user_id": user_id, "label": "target-check"},
        )
        assert resp.status_code == status, f"{user_id}: {resp.text}"
        assert resp.json()["code"] == code

    assert local_env["db"].execute(
        "SELECT count(*) FROM agent_keys"
    ).fetchone()[0] == 0
    assert _outbox(local_env, "agent_key.created") == []


def test_create_request_validation(local_env) -> None:
    """label strip 后 1..64 / 禁控制字符 → 400 invalid_label；未知字段 422。"""
    admin = _setup(local_env)
    admin_id = admin["user"]["id"]
    token = admin["token"]
    client = local_env["client"]

    for bad in ("", "   ", "x" * 65, "bad\nlabel", "bad\x00label"):
        resp = client.post(
            f"/api/orgs/{ORG}/agent-keys",
            headers=_h(token),
            json={"user_id": admin_id, "label": bad},
        )
        assert resp.status_code == 400, f"{bad!r}: {resp.text}"
        assert resp.json()["code"] == "invalid_label"

    extra = client.post(
        f"/api/orgs/{ORG}/agent-keys",
        headers=_h(token),
        json={"user_id": admin_id, "label": "ok", "role": "org_admin"},
    )
    assert extra.status_code == 422, extra.text

    # strip 后落库/审计（前后空白不保留）
    created = _create_key(
        local_env, token, user_id=admin_id, label="  agent-strip  "
    )
    assert created["label"] == "agent-strip"
    assert _outbox(local_env, "agent_key.created")[0]["label"] == "agent-strip"


# ============ 组织上下文 / key 绑定 / 停用组织 ============


def test_org_context_header_mismatch_and_key_binding(local_env) -> None:
    """X-Org-Id 不一致 400；key 绑 A 调 B 403 org_mismatch（sysadmin key 同样）。"""
    admin = _setup(local_env)
    admin_id = admin["user"]["id"]
    token = admin["token"]
    client = local_env["client"]
    missing_org = client.get(
        "/api/orgs/org:missing/agent-keys", headers=_h(token)
    )
    assert missing_org.status_code == 404
    assert missing_org.json()["code"] == "org_not_found"
    _insert_org(local_env, ORG_OTHER, "另一组织")

    bad_header = client.get(
        f"/api/orgs/{ORG}/agent-keys",
        headers={**_h(token), "X-Org-Id": ORG_OTHER},
    )
    assert bad_header.status_code == 400

    key = _create_key(
        local_env, token, user_id=admin_id, label="bound-tax"
    )["key"]
    # 同路径 + 错头 → 400（check_path_org 先于 key 绑定判定）
    wrong_header = client.get(
        f"/api/orgs/{ORG}/agent-keys",
        headers={**_h(key), "X-Org-Id": ORG_OTHER},
    )
    assert wrong_header.status_code == 400

    # key 绑 ORG（owner 是 sysadmin）调 ORG_OTHER 路径 → 403 org_mismatch
    for method, suffix in (("get", ""), ("delete", "/ak_missing")):
        url = f"/api/orgs/{ORG_OTHER}/agent-keys{suffix}"
        resp = getattr(client, method)(url, headers=_h(key))
        assert resp.status_code == 403, f"{method}: {resp.text}"
        assert resp.json()["code"] == "org_mismatch"
    post_cross = client.post(
        f"/api/orgs/{ORG_OTHER}/agent-keys",
        headers=_h(key),
        json={"user_id": admin_id, "label": "cross"},
    )
    assert post_cross.status_code == 403
    assert post_cross.json()["code"] == "org_mismatch"


def test_sysadmin_can_manage_disabled_org(local_env) -> None:
    """停用组织：sysadmin 会话可列/撤销（泄露 key 应急）；org_admin 403
    org_disabled；sysadmin 自己的 key（同组织绑定）同样放行。"""
    admin = _setup(local_env)
    admin_id = admin["user"]["id"]
    token = admin["token"]
    client = local_env["client"]

    _insert_user(local_env, "u_admin2", orgs=[ORG], role="org_admin")
    _insert_user(local_env, "u_member", orgs=[ORG])
    leaked = _create_key(
        local_env, token, user_id="u_member", label="leaked-agent"
    )
    admin_key = _create_key(
        local_env, token, user_id=admin_id, label="admin-agent"
    )["key"]

    local_env["db"].execute(
        "UPDATE orgs SET status = 'disabled' WHERE id = ?", (ORG,)
    )
    local_env["db"].commit()

    # sysadmin（local session）可管停用组织
    assert len(_list_keys(local_env, token)["keys"]) == 2
    revoked = client.delete(
        f"/api/orgs/{ORG}/agent-keys/{leaked['id']}", headers=_h(token)
    )
    assert revoked.status_code == 204, revoked.text
    # sysadmin key 绑本组织 → 同样放行
    assert len(_list_keys(local_env, admin_key)["keys"]) == 2

    # org_admin（非 sysadmin）→ 403 org_disabled（成员校验先通过）
    from knowledge_lattice.domain.auth import issue_dev_jwt

    admin2_jwt = issue_dev_jwt(
        local_env["settings"], user_id="u_admin2", org=ORG
    )
    denied = client.get(
        f"/api/orgs/{ORG}/agent-keys", headers=_h(admin2_jwt)
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "org_disabled"

    # member 非 org_admin → 先落 org_admin_required（权限判定序见契约）
    member_jwt = issue_dev_jwt(
        local_env["settings"], user_id="u_member", org=ORG
    )
    member_denied = client.get(
        f"/api/orgs/{ORG}/agent-keys", headers=_h(member_jwt)
    )
    assert member_denied.status_code == 403
    assert member_denied.json()["code"] == "org_admin_required"


# ============ MCP 冒烟 ============


def test_mcp_search_with_agent_key_and_query_audit(local_env) -> None:
    """agent key 调 MCP search 成功；X-Org-Id 不一致 ToolError 400；查询审计
    act=label / via=agent_key / entry=mcp。"""
    admin = _setup(local_env)
    admin_id = admin["user"]["id"]
    token = admin["token"]
    created = _create_key(
        local_env, token, user_id=admin_id, label="agent-a"
    )
    key = created["key"]

    async def flow(headers: dict) -> dict:
        async with _mcp_client(local_env["app"], headers) as client:
            result = await client.call_tool("search", {"query": "增值税"})
            return json.loads(result.content[0].text)

    payload = asyncio.run(flow(_h(key)))
    assert payload["results"] == []  # 空库合法（成功即契约）

    # org claim（key 绑定组织）与 X-Org-Id 不一致 → 400
    with pytest.raises(ToolError) as excinfo:
        asyncio.run(flow({**_h(key), "X-Org-Id": ORG_OTHER}))
    assert "400" in str(excinfo.value)

    local_env["app"].state.service.query_audit.flush()
    rows = local_env["backend"].read_org_audit(
        ORG, action="search.query", limit=10
    )
    assert rows, "查询审计事件须落库"
    accepted = [
        row for row in rows
        if json.loads(row["detail_json"]).get("act") == "agent-a"
    ]
    assert len(accepted) == 1
    assert accepted[0]["outcome"] == "accepted"
    detail = json.loads(accepted[0]["detail_json"])
    assert detail["act"] == "agent-a"
    assert detail["via"] == "agent_key"
    assert detail["entry"] == "mcp"
    assert detail["query"] == "增值税"


# ============ sso 形态：D26 路由面 404 ============


def test_sso_mode_agent_key_surface_404(app_env) -> None:
    """sso 形态（默认）：agent key 三端点 404（local 专属 router 未注册）。"""
    client = app_env["client"]
    for method, path, body in (
        ("get", f"/api/orgs/{ORG}/agent-keys", None),
        ("post", f"/api/orgs/{ORG}/agent-keys", {
            "user_id": "u_full", "label": "agent-a",
        }),
        ("delete", f"/api/orgs/{ORG}/agent-keys/ak_x", None),
    ):
        resp = (
            getattr(client, method)(path, json=body)
            if body is not None
            else getattr(client, method)(path)
        )
        assert resp.status_code == 404, (
            f"sso 形态 {method.upper()} {path} 须 404"
            f"（agent_keys.router 仅 local 注册）——got {resp.status_code}"
        )
