"""TC-VER-05 MCP fetch 端到端【集成｜M1-2】。

fastmcp Client（e2e_06 同协议栈）经 MCP 以开发 JWT 调 fetch：
- 在用块 → 前后窗口内容；
- 旧版本块（覆盖切换后）→ replaced_by 对象（不返回旧内容、不报不存在）；
- 不存在/不可见 → 404 ToolError（不泄漏存在性）。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from test_ver_01_version_chain import HTML_V1, HTML_V2, ORG


def _client(app, headers: dict) -> Client:
    def factory(**kw):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)

    return Client(
        StreamableHttpTransport(
            url="http://testserver/mcp", headers=headers, httpx_client_factory=factory
        )
    )


def _seed_doc(app_env) -> tuple[str, str]:
    """上传 v1（u_full）→ 完成；返回 (doc_id, 在用 chunk_id)。"""
    service = app_env["app"].state.service
    doc_id, task_id = service.ingest.create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="增值税申报指南",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML_V1, mime_type="text/html", filename="g.html",
    )
    service.ingest.run_task(task_id)
    row = app_env["conn"].execute(
        "SELECT id FROM chunks WHERE doc_id = ? AND version = 1", (doc_id,)
    ).fetchone()
    return doc_id, row[0]


def test_mcp_fetch_window(app_env) -> None:
    doc_id, chunk_id = _seed_doc(app_env)
    token = app_env["jwt"]("u_full", org=ORG)

    async def flow():
        async with _client(app_env["app"], {"Authorization": f"Bearer {token}"}) as client:
            result = await client.call_tool("fetch", {"chunk_id": chunk_id, "window": 2})
            return json.loads(result.content[0].text)

    payload = asyncio.run(flow())
    assert payload["replaced_by"] is None
    assert payload["chunks"] and payload["chunks"][0]["chunk_id"] == chunk_id
    assert {"chunk_id", "seq", "content", "page_no"} <= set(payload["chunks"][0])


def test_mcp_fetch_replaced_by(app_env) -> None:
    """覆盖切换后 fetch v1 旧块 → replaced_by={doc_id, active_version}（§6.1）。"""
    doc_id, v1_chunk = _seed_doc(app_env)
    service = app_env["app"].state.service
    _, task2 = service.ingest.create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="v2", dims={"region": ["CN"]},
        owner_user_id="u_full", file_bytes=HTML_V2, mime_type="text/html",
        filename="g2.html", doc_id=doc_id,
    )
    service.ingest.run_task(task2)
    assert service.backend.get_document(doc_id)["active_version"] == 2

    token = app_env["jwt"]("u_full", org=ORG)

    async def flow():
        async with _client(app_env["app"], {"Authorization": f"Bearer {token}"}) as client:
            result = await client.call_tool("fetch", {"chunk_id": v1_chunk})
            return json.loads(result.content[0].text)

    payload = asyncio.run(flow())
    assert payload["chunks"] == [], "不返回旧内容（FR-1）"
    assert payload["replaced_by"] == {"doc_id": doc_id, "active_version": 2}


def test_mcp_fetch_not_found_and_invisible(app_env) -> None:
    """不存在 → 404；不可见用户（u_os 对 region=[CN] 文档）→ 404（不泄漏存在性）。"""
    doc_id, chunk_id = _seed_doc(app_env)

    async def flow(token: str, cid: str):
        async with _client(app_env["app"], {"Authorization": f"Bearer {token}"}) as client:
            result = await client.call_tool("fetch", {"chunk_id": cid})
            return json.loads(result.content[0].text)

    with pytest.raises(ToolError) as exc_info:
        asyncio.run(flow(app_env["jwt"]("u_full", org=ORG), "chk_none"))
    assert "404" in str(exc_info.value)

    with pytest.raises(ToolError) as exc_invisible:
        asyncio.run(flow(app_env["jwt"]("u_os", org=ORG), chunk_id))
    assert "404" in str(exc_invisible.value)
