"""FastMCP 单一 server（design §3 mcp/server.py + §6.1 docs 组——search 已落）。

- `search` 工具：M1-1 完整配方（core/docs/retrieve——双路 + RRF + rerank + 增强
  + 归一）；工具描述「写给 LLM 看」纪律（§6.1）；`top_k ≤ 20` 服务端硬上限；
  检索参数（权重/阈值/召回窗口）不暴露；返回块带 chunk_id 溯源 + source
  （agent 代传可识别）；sync 工具由 FastMCP 线程池承接（模型 HTTP 调用不上
  事件循环——NFR-8）；
- 组织上下文（D18/TC-AUTH-02）：token org claim 优先 / 运行时注入 X-Org-Id 头兜底；
  并存且不一致 → 400（ToolError）；缺失 → 400；**工具参数 org 一律忽略并记审计**；
- 60s 超时中间件（ragflow 纪律——超时请求不悬挂，TC-E2E-06）；超时值随
  settings.mcp_timeout_s（默认 60，测试可注入短值）。

upload/fetch/list_documents 随 M1（凭证三步/版本链）；semantic 组随 M2-S。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from knowledge_lattice.config import Settings
from knowledge_lattice.core.docs.acl import AclDeniedError
from knowledge_lattice.core.docs.retrieve import search as run_search
from knowledge_lattice.domain.auth import AuthError, OrgContextError, authenticate, resolve_org

logger = logging.getLogger(__name__)

SEARCH_TOOL_DESCRIPTION = (
    "检索企业知识库。缺私有信息（制度/手册/申报口径）时调用；"
    "query 越具体越好（含税种、区域、文档关键词）；返回结果自带 chunk_id 溯源，"
    "回答时请引用。"
)


class ToolTimeoutMiddleware(Middleware):
    """60s 超时中间件（挂载即生效——超时 ToolError 返回、不悬挂）。"""

    def __init__(self, timeout_s: float = 60.0) -> None:
        super().__init__()
        self.timeout_s = timeout_s

    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        try:
            return await asyncio.wait_for(call_next(context), timeout=self.timeout_s)
        except asyncio.TimeoutError:
            raise ToolError(
                f"tool execution timed out after {self.timeout_s:.0f}s (60s 超时中间件)"
            ) from None


def build_mcp_server(service, settings: Settings) -> FastMCP:
    """组装 MCP server（service = app 侧依赖容器：backend/gate 等）。"""

    mcp: FastMCP = FastMCP(
        name="knowledge-lattice",
        instructions="企业知识层 docs 组工具（M0a：search；upload/fetch/list_documents 随 M1）。",
    )
    mcp.add_middleware(ToolTimeoutMiddleware(timeout_s=settings.mcp_timeout_s))

    def _auth_and_org(ctx: Context, *, param_org: str | None) -> tuple[str, str]:
        """认证 + 组织上下文统一规则（D18）——401/400 语义以 ToolError 透出。"""
        request = getattr(ctx.request_context, "request", None) if ctx else None
        auth_header = request.headers.get("authorization") if request is not None else None
        if not auth_header or not auth_header.lower().startswith("bearer "):
            raise ToolError("401: missing Bearer token（MCP 调用须持开发 JWT / 委托 token）")
        try:
            auth = authenticate(service.backend, settings, auth_header[7:].strip())
        except AuthError as exc:
            raise ToolError(f"401: {exc}") from exc
        # 工具参数 org 一律忽略并记审计（D18——org 不是 LLM 可填参数）
        if param_org is not None:
            service.backend.append_outbox(
                "mcp.org_param_ignored",
                json.dumps(
                    {"user_id": auth.user_id, "ignored_org": param_org}, ensure_ascii=False
                ),
            )
        org_header = request.headers.get("x-org-id") if request is not None else None
        try:
            org = resolve_org(org_claim=auth.org_claim, org_header=org_header)
        except OrgContextError as exc:
            raise ToolError(f"400: {exc}") from exc
        return auth.user_id, org

    @mcp.tool(name="search", description=SEARCH_TOOL_DESCRIPTION)
    def search(
        query: str,
        top_k: int = 8,
        datasets: list[str] | None = None,
        doc_filter: list[str] | None = None,
        org: str | None = None,  # deprecated——忽略并记审计（D18：org 来自 token claim / 注入头）
        ctx: Context = None,
    ) -> dict:
        user_id, org_id = _auth_and_org(ctx, param_org=org)
        try:
            return run_search(
                service.backend,
                settings,
                user_id=user_id,
                org_id=org_id,
                query=query,
                top_k=top_k,
                datasets=datasets,
                doc_filter=doc_filter,
                gate=service.gate,
                embedder=getattr(service, "embedder", None),
                reranker=getattr(service, "reranker", None),
                enhancer=getattr(service, "enhancer", None),
                breakers=getattr(service, "breakers", None),
            )
        except AclDeniedError as exc:
            raise ToolError(f"403: {exc}") from exc

    return mcp
