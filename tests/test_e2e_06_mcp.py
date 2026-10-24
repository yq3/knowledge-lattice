"""TC-E2E-06 MCP 端到端（M0a 验收原句）【集成｜M0a】。

测试客户端（fastmcp Client——langchain-mcp-adapters 同协议栈）经 MCP 以**开发 JWT**
调 `search` → 返回带 chunk_id 的命中；60s 超时中间件挂载（超时请求不悬挂）。
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from knowledge_lattice.config import Settings


def _client(app, headers: dict) -> Client:
    def factory(**kw):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)

    return Client(
        StreamableHttpTransport(
            url="http://testserver/mcp", headers=headers, httpx_client_factory=factory
        )
    )


def _seed_hit(app_env) -> str:
    html = (
        "<html><body><h1>增值税留抵退税操作指引</h1>"
        "<p>一般纳税人符合条件可按月申请退还增量留抵税额，申请前完成纳税申报。</p></body></html>"
    ).encode()
    service = app_env["app"].state.service
    doc_id, task_id = service.ingest.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="增值税留抵退税操作指引",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=html, mime_type="text/html", filename="vat.html",
    )
    service.ingest.run_task(task_id)
    return doc_id


def test_mcp_search_with_dev_jwt_returns_chunk_id(app_env) -> None:
    """M0a 验收原句：经 MCP 以开发 JWT 调 search → 带 chunk_id 命中。"""
    _seed_hit(app_env)
    token = app_env["jwt"]("u_full", org="org:tax")  # 开发 JWT（POST /api/dev/token 同签发逻辑）

    async def flow():
        async with _client(app_env["app"], {"Authorization": f"Bearer {token}"}) as client:
            result = await client.call_tool("search", {"query": "留抵退税", "top_k": 5})
            return json.loads(result.content[0].text)

    payload = asyncio.run(flow())
    assert payload["results"]
    top = payload["results"][0]
    assert top["chunk_id"].startswith("chk_")
    assert "notice" in payload and "degraded" in payload["notice"]


def test_mcp_unauthenticated_401(app_env) -> None:
    """无 Bearer → 401（ToolError 透出）。"""
    async def flow():
        async with _client(app_env["app"], {}) as client:
            await client.call_tool("search", {"query": "x"})

    with pytest.raises(ToolError) as exc_info:
        asyncio.run(flow())
    assert "401" in str(exc_info.value)


def test_mcp_acl_denied_403(app_env) -> None:
    """u_cn（region=[CN]）检索 region=[OS] 文档 → 零命中；无成员关系用户 → 403（实测）。"""
    html = (
        "<html><body><h1>海外转让定价手册</h1><p>关联交易定价遵循独立交易原则。</p></body></html>"
    ).encode()
    service = app_env["app"].state.service
    _, task_id = service.ingest.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="海外转让定价手册",
        dims={"region": ["OS"]}, owner_user_id="u_full",
        file_bytes=html, mime_type="text/html", filename="tp.html",
    )
    service.ingest.run_task(task_id)

    token_cn = app_env["jwt"]("u_cn", org="org:tax")

    async def flow():
        async with _client(app_env["app"], {"Authorization": f"Bearer {token_cn}"}) as client:
            result = await client.call_tool("search", {"query": "转让定价 独立交易"})
            return json.loads(result.content[0].text)

    payload = asyncio.run(flow())
    assert payload["results"] == []  # OS 文档对 u_cn（仅 CN）不可见

    # 无成员关系用户（u_guest 非 org:tax 成员——TC-ACL-05 第 0 步语义）→ 403
    from helpers import seed_membership, seed_user

    seed_user(app_env["conn"], "u_guest")
    app_env["conn"].commit()
    token_guest = app_env["jwt"]("u_guest", org="org:tax")

    async def flow_guest():
        async with _client(app_env["app"], {"Authorization": f"Bearer {token_guest}"}) as client:
            await client.call_tool("search", {"query": "转让定价"})

    with pytest.raises(ToolError) as exc_info:
        asyncio.run(flow_guest())
    assert "403" in str(exc_info.value) and "membership" in str(exc_info.value)


def test_mcp_timeout_middleware_no_hang(tmp_path) -> None:
    """60s 超时中间件：注入短超时 + 慢检索 → 快速失败（不悬挂）；挂载值默认 60s。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=2560,
        probe_interval_s=0, mcp_timeout_s=0.2,  # 测试注入短超时（中间件同款路径）
    )
    from fake_providers import FakeEmbedder

    app = create_app(settings, embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
                     run_startup_probe=False)

    def slow_recall(*args, **kwargs):  # 模拟慢检索（> 超时预算）
        time.sleep(0.6)
        return []

    app.state.service.backend.recall_fts = slow_recall  # 代理实例属性——跨线程可见

    token = None
    from knowledge_lattice.domain.auth import issue_dev_jwt

    token = issue_dev_jwt(settings, user_id="u_full", org="org:tax")
    # u_full 需存在：直接造数
    from knowledge_lattice.store.sqlite import connect

    conn = connect(settings.db_path)
    conn.execute("INSERT OR IGNORE INTO orgs(id, name) VALUES('org:tax', 't')")
    conn.execute("INSERT OR IGNORE INTO datasets(id, org_id, name) VALUES('ds:vat_lib', 'org:tax', 'v')")
    conn.execute("INSERT OR IGNORE INTO users(id, username) VALUES('u_full', 'u_full')")
    conn.execute(
        "INSERT OR IGNORE INTO user_org_memberships(user_id, org_id) VALUES('u_full', 'org:tax')"
    )
    conn.commit()
    conn.close()

    async def flow():
        async with app.router.lifespan_context(app):
            async with _client(app, {"Authorization": f"Bearer {token}"}) as client:
                t0 = time.monotonic()
                with pytest.raises(ToolError) as exc_info:
                    await client.call_tool("search", {"query": "x"})
                return time.monotonic() - t0, str(exc_info.value)

    elapsed, message = asyncio.run(flow())
    assert "timed out" in message
    assert elapsed < 2.0  # 0.2s 超时生效、不悬挂（60s 同款中间件路径）


def test_mcp_timeout_default_60s(app_env) -> None:
    """默认配置挂载 60s 超时（config 口径——TC-E2E-06「60s 超时中间件挂载」）。"""
    assert app_env["settings"].mcp_timeout_s == 60.0
