"""D26 阶段 4：agent key 端到端集成（issue #34——`local` 形态 agent 长期凭据）。

双后端参数化（``local_env``——sqlite 臂实跑 + pg 臂需 ``LATTICE_PG_DSN``，门禁
脚本把 skip 视为失败；pg 臂真实执行）。每用例空库启动，管理员经 ``POST /api/setup``
真实造出；agent key 一律经 REST 管理面（``POST /api/orgs/{org}/agent-keys``）签发，
与阶段 2B 同一契约。

覆盖（阶段 4 集成面）：
- **两个 agent 可区分**：key A/B（label=agent-a/agent-b）各经 fastmcp Client 调
  ``search`` → ``query_audit.flush()`` 后 ``read_org_audit(ORG, action="search.query")``
  断言两条审计的 ``act`` 分别为 agent-a/agent-b、``via=agent_key``、``entry=mcp``；
- **撤销即时生效**：撤销 key A → 再调 MCP → ToolError 401（revoked）；
- **org 绑定**：key 绑 ``org:tax`` + MCP 请求头 ``X-Org-Id: org:other`` → ToolError
  400（claim/头不一致）；同头一致时正常（对照组）；
- **上传三步同一 key**：key A ``POST /api/uploads``（REST）→ PUT 字节 → MCP
  ``upload(upload_id, dataset, dimensions)`` 成功入队/任务（``source_uri=agent:agent-a``）；
  再用 key B（同用户、不同 label）消费同一 upload_id → 三要素不匹配 403
  ``binding_mismatch``；最后 key A 重试 → 409 ``upload_consumed``（v1.4 口径：
  成功消费后单次；失败/绑定不符不置已用）；
- **sysadmin 豁免冒烟**：sysadmin（membership role=member）用 key 调
  GET/POST/DELETE agent-keys → 允许；非 sysadmin member key → 403
  ``org_admin_required``。

不在本文件重复（已由前序阶段覆盖）：``sso`` 形态三端点 404（test_agent_key_api）、
local session token 调 MCP 仍 401（m4 用例）、REST org 路径跨组织 2A/2B 测试。
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from helpers import seed_dataset, seed_dim_value, seed_dimension, seed_grant

ADMIN = {
    "username": "admin",
    "password": "admin-password-123",
    "display_name": "管理员",
    "org_id": "org:tax",
    "org_name": "税务组织",
}
ORG = "org:tax"
ORG_OTHER = "org:other-tax"
DATASET = "ds:vat_lib"

PAYLOAD = (
    "<html><body><h1>土地增值税清算实务</h1>"
    "<p>纳税人转让旧房及建筑物，可凭购房发票差额计征土地增值税。</p></body></html>"
).encode()
SHA_HEX = hashlib.sha256(PAYLOAD).hexdigest()


# ============ 助手 ============


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup(env) -> dict:
    resp = env["client"].post("/api/setup", json=ADMIN)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_key(env, token: str, *, user_id: str, label: str) -> dict:
    resp = env["client"].post(
        f"/api/orgs/{ORG}/agent-keys",
        headers=_h(token),
        json={"user_id": user_id, "label": label},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _revoke_key(env, token: str, key_id: str) -> None:
    resp = env["client"].delete(
        f"/api/orgs/{ORG}/agent-keys/{key_id}", headers=_h(token)
    )
    assert resp.status_code == 204, resp.text


def _insert_member(
    env, user_id: str, *, role: str = "member", is_system_admin: bool = False
) -> None:
    env["db"].execute(
        "INSERT INTO users(id, username, is_system_admin) VALUES(?, ?, ?)",
        (user_id, user_id, 1 if is_system_admin else 0),
    )
    env["db"].execute(
        "INSERT INTO user_org_memberships(user_id, org_id, role) VALUES(?, ?, ?)",
        (user_id, ORG, role),
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


def _search(env, token: str, *, headers: dict | None = None) -> dict:
    async def flow() -> dict:
        async with _mcp_client(env["app"], {**_h(token), **(headers or {})}) as client:
            result = await client.call_tool("search", {"query": "增值税"})
            return json.loads(result.content[0].text)

    return asyncio.run(flow())


def _upload(env, token: str, upload_id: str, *, dims=None) -> dict:
    async def flow() -> dict:
        async with _mcp_client(env["app"], _h(token)) as client:
            result = await client.call_tool(
                "upload",
                {
                    "upload_id": upload_id,
                    "dataset": DATASET,
                    "dimensions": dims or {"region": ["CN"]},
                },
            )
            return json.loads(result.content[0].text)

    return asyncio.run(flow())


def _upload_row(env, upload_id: str) -> tuple:
    return env["db"].execute(
        "SELECT status, doc_id, task_id FROM uploads WHERE id = ?", (upload_id,)
    ).fetchone()


def _seed_upload_targets(env, user_id: str) -> None:
    """最小可用上传目标：dataset + region 维度（CN）+ 管理员 CN 授权。"""
    db = env["db"]
    seed_dataset(db, ORG, DATASET)
    seed_dimension(db, ORG, "region")
    seed_dim_value(db, f"dim:{ORG}:region", "CN")
    seed_grant(
        db, user_id=user_id, dim_id=f"dim:{ORG}:region",
        val_id=f"val:dim:{ORG}:region:CN",
    )
    db.commit()


# ============ 两个 agent 可区分（查询审计 act/via/entry） ============


def test_two_agents_are_distinguishable_in_query_audit(local_env) -> None:
    """key A/B 各调 MCP search → 查询审计两条：act=label / via=agent_key / entry=mcp。"""
    admin = _setup(local_env)
    admin_id = admin["user"]["id"]
    token = admin["token"]
    key_a = _create_key(local_env, token, user_id=admin_id, label="agent-a")["key"]
    key_b = _create_key(local_env, token, user_id=admin_id, label="agent-b")["key"]

    assert _search(local_env, key_a)["results"] == []
    assert _search(local_env, key_b)["results"] == []

    local_env["app"].state.service.query_audit.flush()
    rows = local_env["backend"].read_org_audit(
        ORG, action="search.query", limit=10
    )
    accepted = [
        row for row in rows
        if row["outcome"] == "accepted"
        and json.loads(row["detail_json"]).get("via") == "agent_key"
    ]
    assert len(accepted) == 2, rows
    details = [json.loads(row["detail_json"]) for row in accepted]
    assert {d["act"] for d in details} == {"agent-a", "agent-b"}
    assert {d["via"] for d in details} == {"agent_key"}
    assert {d["entry"] for d in details} == {"mcp"}
    assert {row["actor"] for row in accepted} == {admin_id}
    assert all(d["query"] == "增值税" for d in details)


# ============ 撤销即时生效 ============


def test_revoke_takes_effect_immediately_for_mcp(local_env) -> None:
    """撤销 key A → 同一 key 再调 MCP → ToolError 401 revoked（即时生效）。"""
    admin = _setup(local_env)
    created = _create_key(
        local_env, admin["token"], user_id=admin["user"]["id"], label="agent-a"
    )
    key = created["key"]

    assert _search(local_env, key)["results"] == []
    _revoke_key(local_env, admin["token"], created["id"])

    with pytest.raises(ToolError) as excinfo:
        _search(local_env, key)
    message = str(excinfo.value)
    assert "401" in message and "revoked" in message, message


# ============ org 绑定（MCP claim/头一致性） ============


def test_mcp_org_binding_rejects_mismatched_header(local_env) -> None:
    """key 绑 org:tax + MCP 头 org:other → 400；头一致 → 正常（对照组）。"""
    admin = _setup(local_env)
    key = _create_key(
        local_env, admin["token"], user_id=admin["user"]["id"], label="agent-a"
    )["key"]

    # 对照组：key claim 与头一致（org:tax）→ 正常检索
    assert _search(local_env, key, headers={"X-Org-Id": ORG})["results"] == []

    with pytest.raises(ToolError) as excinfo:
        _search(local_env, key, headers={"X-Org-Id": ORG_OTHER})
    message = str(excinfo.value)
    assert "400" in message, message
    # 400 发生在 resolve_org（claim/头不一致），不落查询审计
    local_env["app"].state.service.query_audit.flush()
    rows = local_env["backend"].read_org_audit(
        ORG, action="search.query", limit=10
    )
    assert len(rows) == 1  # 仅对照组那条 accepted


# ============ 上传三步同一 key（+ 跨 key 绑定 / 重试语义） ============


def test_upload_three_steps_with_agent_key(local_env) -> None:
    """key A 签发→PUT→MCP upload 成功；key B 消费同凭证 403；key A 重试 409。"""
    admin = _setup(local_env)
    admin_id = admin["user"]["id"]
    _seed_upload_targets(local_env, admin_id)
    key_a = _create_key(
        local_env, admin["token"], user_id=admin_id, label="agent-a"
    )["key"]
    key_b = _create_key(
        local_env, admin["token"], user_id=admin_id, label="agent-b"
    )["key"]

    # ① 凭证签发（REST，key A——org claim 即绑定组织）+ ② PUT 字节
    resp = local_env["client"].post(
        "/api/uploads",
        json={
            "filename": "doc.html",
            "size": len(PAYLOAD),
            "sha256": SHA_HEX,
            "content_type": "text/html",
        },
        headers=_h(key_a),
    )
    assert resp.status_code == 201, resp.text
    upload_id = resp.json()["upload_id"]
    put = local_env["client"].put(
        f"/api/uploads/{upload_id}", content=PAYLOAD, headers=_h(key_a)
    )
    assert put.status_code == 200, put.text

    # ③ MCP upload（同一 key A——服务身份 = act = label）→ 成功入队/任务
    payload = _upload(local_env, key_a, upload_id)
    assert payload["doc_id"].startswith("doc_")
    assert payload["task_id"].startswith("tsk_")
    assert payload["status"] == "queued"
    assert payload["pending_version"] == 1
    assert _upload_row(local_env, upload_id) == (
        "consumed", payload["doc_id"], payload["task_id"],
    )
    doc = local_env["backend"].get_document(payload["doc_id"])
    assert doc["source_uri"] == "agent:agent-a"  # 服务身份=key label（agent 代传标来源）

    # key B（同用户、不同 label）消费同凭证 → 三要素（sub/org/服务身份）不匹配 403
    with pytest.raises(ToolError) as excinfo:
        _upload(local_env, key_b, upload_id)
    message = str(excinfo.value)
    assert "403" in message and "binding_mismatch" in message, message
    assert _upload_row(local_env, upload_id)[0] == "consumed"  # 绑定失败不改状态

    # 同一 key A 重试：成功消费后单次（v1.4 口径）→ 409 upload_consumed
    with pytest.raises(ToolError) as excinfo:
        _upload(local_env, key_a, upload_id)
    message = str(excinfo.value)
    assert "409" in message and "upload_consumed" in message, message


# ============ sysadmin 豁免冒烟 ============


def test_sysadmin_member_key_can_manage_agent_keys(local_env) -> None:
    """sysadmin（membership role=member）key 管理三端点放行；member key 403。"""
    admin = _setup(local_env)
    token = admin["token"]
    client = local_env["client"]

    _insert_member(local_env, "u_member")
    _insert_member(local_env, "u_sys", is_system_admin=True)
    member_key = _create_key(
        local_env, token, user_id="u_member", label="member-agent"
    )["key"]
    sys_key = _create_key(
        local_env, token, user_id="u_sys", label="sys-agent"
    )["key"]

    # 非 sysadmin member：三端点 403 org_admin_required
    for method, path, body in (
        ("get", f"/api/orgs/{ORG}/agent-keys", None),
        ("post", f"/api/orgs/{ORG}/agent-keys",
         {"user_id": "u_member", "label": "self"}),
        ("delete", f"/api/orgs/{ORG}/agent-keys/ak_missing", None),
    ):
        resp = (
            getattr(client, method)(path, headers=_h(member_key), json=body)
            if body is not None
            else getattr(client, method)(path, headers=_h(member_key))
        )
        assert resp.status_code == 403, f"{method} {path}: {resp.text}"
        assert resp.json()["code"] == "org_admin_required"

    # sysadmin（role=member）key：GET/POST/DELETE 全放行
    listing = client.get(f"/api/orgs/{ORG}/agent-keys", headers=_h(sys_key))
    assert listing.status_code == 200, listing.text
    assert len(listing.json()["keys"]) >= 1
    created = _create_key(
        local_env, sys_key, user_id="u_member", label="by-sysadmin"
    )
    assert created["created_by"] == "u_sys"
    _revoke_key(local_env, sys_key, created["id"])
    row = next(
        item for item in client.get(
            f"/api/orgs/{ORG}/agent-keys", headers=_h(sys_key)
        ).json()["keys"]
        if item["id"] == created["id"]
    )
    assert row["revoked_by"] == "u_sys"
