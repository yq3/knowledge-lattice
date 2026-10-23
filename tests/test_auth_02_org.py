"""TC-AUTH-02 组织上下文统一规则【接口｜M0a 范围】（D18 / T14 展开）。

① token 有 org claim + 注入头一致 → 正常（claim 优先）；② claim 与头不一致 → 400；
③ 无 claim 无头 → 400；④ 工具参数携带 org → 忽略并记审计；⑤ REST 路径 org 与
X-Org-Id 并存且不一致 → 400。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError


def _mcp_client(app, headers: dict) -> Client:
    def factory(**kw):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)

    transport = StreamableHttpTransport(
        url="http://testserver/mcp", headers=headers, httpx_client_factory=factory
    )
    return Client(transport)


def _run(coro):
    return asyncio.run(coro)


def _seed_hit(app_env) -> None:
    """种一篇可命中文档（经内部 ingest 直跑——MCP 断言需要非空命中）。"""
    from knowledge_lattice.adapters.parser_docling import ParsedBlock
    from knowledge_lattice.core.docs.chunking import chunk_blocks

    conn = app_env["conn"]
    html = (
        "<html><body><h1>留抵退税指引</h1><p>增量留抵税额可按月申请退还，需完成汇总勾选。</p></body></html>"
    ).encode()
    service = app_env["app"].state.service
    doc_id, task_id = service.ingest.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="留抵退税指引",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=html, mime_type="text/html", filename="lpi.html",
    )
    service.ingest.run_task(task_id)
    return doc_id


def _outbox(app_env) -> list[tuple[str, str]]:
    return [
        (r[0], r[1])
        for r in app_env["conn"].execute("SELECT event_type, payload_json FROM audit_outbox")
    ]


def test_mcp_claim_and_header_consistent_ok(app_env) -> None:
    """① claim=org:tax + X-Org-Id=org:tax → 正常（claim 优先）——M0a 验收主路径。"""
    _seed_hit(app_env)
    token = app_env["jwt"]("u_full", org="org:tax")

    async def flow():
        async with _mcp_client(
            app_env["app"],
            {"Authorization": f"Bearer {token}", "X-Org-Id": "org:tax"},
        ) as client:
            result = await client.call_tool("search", {"query": "留抵退税"})
            return json.loads(result.content[0].text)

    payload = _run(flow())
    assert payload["results"], "MCP search 应返回带 chunk_id 的命中"
    assert payload["results"][0]["chunk_id"].startswith("chk_")


def test_mcp_claim_header_mismatch_400(app_env) -> None:
    """② claim=org:tax + X-Org-Id=org:gl → 400（ToolError 透出）。"""
    token = app_env["jwt"]("u_full", org="org:tax")

    async def flow():
        async with _mcp_client(
            app_env["app"],
            {"Authorization": f"Bearer {token}", "X-Org-Id": "org:gl"},
        ) as client:
            await client.call_tool("search", {"query": "x"})

    with pytest.raises(ToolError) as exc_info:
        _run(flow())
    assert "400" in str(exc_info.value) and "不一致" in str(exc_info.value)


def test_mcp_org_missing_400(app_env) -> None:
    """③ 无 claim（静态 token）+ 无 X-Org-Id 头 → 400（缺失即报错，无隐式默认）。"""
    async def flow():
        async with _mcp_client(
            app_env["app"], {"Authorization": f"Bearer {app_env['static']['u_full']}"}
        ) as client:
            await client.call_tool("search", {"query": "x"})

    with pytest.raises(ToolError) as exc_info:
        _run(flow())
    assert "400" in str(exc_info.value)


def test_mcp_tool_org_param_ignored_and_audited(app_env) -> None:
    """④ 工具参数 org → 忽略并记审计（org 不是 LLM 可填参数——D18）。"""
    _seed_hit(app_env)
    token = app_env["jwt"]("u_full", org="org:tax")

    async def flow():
        async with _mcp_client(
            app_env["app"],
            {"Authorization": f"Bearer {token}"},
        ) as client:
            result = await client.call_tool(
                "search", {"query": "留抵退税", "org": "org:gl"}  # 恶意/误传 org 参数
            )
            return json.loads(result.content[0].text)

    payload = _run(flow())
    assert payload["results"], "参数 org 被忽略——按 claim org:tax 正常检索"
    events = [e for e in _outbox(app_env) if e[0] == "mcp.org_param_ignored"]
    assert len(events) == 1  # 记审计
    assert json.loads(events[0][1])["ignored_org"] == "org:gl"


def test_rest_path_org_header_mismatch_400(app_env) -> None:
    """⑤ REST 路径 org 与 X-Org-Id 并存且不一致 → 400。"""
    resp = app_env["client"].get(
        "/api/orgs/org:gl/tasks",
        headers={
            "Authorization": f"Bearer {app_env['static']['u_full']}",
            "X-Org-Id": "org:tax",
        },
    )
    assert resp.status_code == 400
    assert "不一致" in resp.json()["error"]
    # 一致时放行（u_full 非 org:gl 成员 → 403 成员关系——非 400）
    resp2 = app_env["client"].get(
        "/api/orgs/org:gl/tasks",
        headers={
            "Authorization": f"Bearer {app_env['static']['u_full']}",
            "X-Org-Id": "org:gl",
        },
    )
    assert resp2.status_code == 403
