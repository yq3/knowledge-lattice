"""FastMCP 单一 server（design §3 mcp/server.py + §6.1 docs 组——search/fetch 已落，
upload 随 M1-3）。

- `search` 工具：M1-1 完整配方（core/docs/retrieve——双路 + RRF + rerank + 增强
  + 归一）；工具描述「写给 LLM 看」纪律（§6.1）；`top_k ≤ 20` 服务端硬上限；
  检索参数（权重/阈值/召回窗口）不暴露；返回块带 chunk_id 溯源 + source
  （agent 代传可识别）；sync 工具由 FastMCP 线程池承接（模型 HTTP 调用不上
  事件循环——NFR-8）；
- `fetch` 工具（M1-2）：按 chunk_id 取内容窗口；旧版本块（tombstone/pending）
  返回 `replaced_by: {doc_id, active_version}` 替代提示（§6.1——不承诺块级映射、
  不返回旧内容、不报不存在，TC-VER-05）；不可见/不存在 → 404（不泄漏存在性）；
- `upload` 工具（M1-3，三步③）：inputSchema 只收不透明 `upload_id`（§6.1 line
  1071-1078——路径/URL 一律拒绝，P0-D）；三一致校验（T11）+ 哈希复验 → 走
  `ingest.create_document` 同一 code path（版本制/ACL 写校验不旁路）；凭证在
  摄取成功入队后置已用（v1.4 口径）；摄取由进程内执行器异步执行（M0a 口径，
  子进程 worker 随 M2）——工具立即返回 queued；
- 组织上下文（D18/TC-AUTH-02）：token org claim 优先 / 运行时注入 X-Org-Id 头兜底；
  并存且不一致 → 400（ToolError）；缺失 → 400；**工具参数 org 一律忽略并记审计**；
- 60s 超时中间件（ragflow 纪律——超时请求不悬挂，TC-E2E-06）；超时值随
  settings.mcp_timeout_s（默认 60，测试可注入短值）。

list_documents 随 M1-4；semantic 组随 M2-S。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from knowledge_lattice.config import Settings
from knowledge_lattice.core.docs.acl import AclDeniedError
from knowledge_lattice.core.docs.credentials import CredentialError
from knowledge_lattice.core.docs.fetch import FetchNotFoundError, fetch_chunks
from knowledge_lattice.core.docs.ingest import (
    UploadConflictError,
    UploadNotFoundError,
    UploadPermissionError,
    UploadValidationError,
)
from knowledge_lattice.core.docs.retrieve import search as run_search
from knowledge_lattice.domain.auth import (
    AuthContext,
    AuthError,
    OrgContextError,
    authenticate,
    resolve_org,
)

logger = logging.getLogger(__name__)

SEARCH_TOOL_DESCRIPTION = (
    "检索企业知识库。缺私有信息（制度/手册/申报口径）时调用；"
    "query 越具体越好（含税种、区域、文档关键词）；返回结果自带 chunk_id 溯源，"
    "回答时请引用。"
)

FETCH_TOOL_DESCRIPTION = (
    "按 chunk_id 取该块前后相邻的内容窗口（先搜后读）。"
    "旧版本块返回替代提示（replaced_by 指向当前在用版本）。"
)

UPLOAD_TOOL_DESCRIPTION = (
    "向知识库上传文档（agent 采集到的文件）。必须指定知识库与维度元数据，否则会被拒绝；"
    "upload_id 只收不透明凭证（由 POST /api/uploads 签发、运行时已 PUT 字节）——"
    "路径/URL 一律拒绝。"
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
    """组装 MCP server（service = app 侧依赖容器：backend/credentials/ingest 等）。"""

    mcp: FastMCP = FastMCP(
        name="knowledge-lattice",
        instructions="企业知识层 docs 组工具（search + fetch + upload；list_documents 随 M1-4）。",
    )
    mcp.add_middleware(ToolTimeoutMiddleware(timeout_s=settings.mcp_timeout_s))

    def _auth_and_org(ctx: Context, *, param_org: str | None) -> tuple[AuthContext, str]:
        """认证 + 组织上下文统一规则（D18）——401/400 语义以 ToolError 透出；
        返回完整 AuthContext（M1-3：act＝服务身份进凭证三一致校验）。"""
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
        return auth, org

    @mcp.tool(name="search", description=SEARCH_TOOL_DESCRIPTION)
    def search(
        query: str,
        top_k: int = 8,
        datasets: list[str] | None = None,
        doc_filter: list[str] | None = None,
        org: str | None = None,  # deprecated——忽略并记审计（D18：org 来自 token claim / 注入头）
        ctx: Context = None,
    ) -> dict:
        auth, org_id = _auth_and_org(ctx, param_org=org)
        try:
            return run_search(
                service.backend,
                settings,
                user_id=auth.user_id,
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
        except AclDeniedError as exc:  # code 随异常透出（membership_denied 类——T12）
            raise ToolError(f"403: {exc}（code={exc.code}）") from exc

    @mcp.tool(name="fetch", description=FETCH_TOOL_DESCRIPTION)
    def fetch(
        chunk_id: str,
        window: int = 2,
        ctx: Context = None,
    ) -> dict:
        """fetch（§6.1）：内容窗口 / 旧版本块 replaced_by 替代提示（TC-VER-05）。"""
        auth, org_id = _auth_and_org(ctx, param_org=None)
        try:
            return fetch_chunks(
                service.backend,
                user_id=auth.user_id,
                org_id=org_id,
                chunk_id=chunk_id,
                window=window,
            )
        except FetchNotFoundError as exc:
            raise ToolError(f"404: {exc}") from exc
        except AclDeniedError as exc:  # code 随异常透出（membership_denied 类——T12）
            raise ToolError(f"403: {exc}（code={exc.code}）") from exc

    @mcp.tool(name="upload", description=UPLOAD_TOOL_DESCRIPTION)
    def upload(
        upload_id: str,
        dataset: str,
        dimensions: dict[str, list[str]],
        doc_id: str | None = None,
        title: str | None = None,
        ctx: Context = None,
    ) -> dict:
        """upload（§6.1 三步③）：只收不透明 upload_id——三一致校验（T11）+ 哈希
        复验 → ingest.create_document 同一 code path（版本制/ACL 写校验不旁路）；
        凭证在摄取成功入队后置已用（失败不置、可重传——v1.4 口径）。"""
        auth, org_id = _auth_and_org(ctx, param_org=None)
        try:
            result = service.credentials.consume(
                upload_id,
                org_id=org_id,
                user_id=auth.user_id,
                service_id=auth.act,
                dataset_id=dataset,
                dims=dimensions,
                title=title,
                doc_id=doc_id,
                create_document=service.ingest.create_document,
            )
        except CredentialError as exc:  # T11/T12：凭证绑定/状态/校验专属错误码
            raise ToolError(f"{exc.http_status}: {exc}（code={exc.code}）") from exc
        except AclDeniedError as exc:  # P1-1：逐请求成员关系校验（§5.5/FR-4）
            raise ToolError(f"403: {exc}（code={exc.code}）") from exc
        except UploadValidationError as exc:
            raise ToolError(f"400: {exc}") from exc
        except UploadPermissionError as exc:
            raise ToolError(f"403: {exc}") from exc
        except UploadConflictError as exc:  # T7：pending 期间只有一个处理中版本
            raise ToolError(f"409: {exc}") from exc
        except UploadNotFoundError as exc:
            raise ToolError(f"404: {exc}") from exc

        def _run(task_id: str) -> None:  # 进程内执行器（M0a 口径；子进程 worker 随 M2）
            try:
                service.ingest.run_task(task_id)
            except Exception:  # noqa: BLE001 —— 任务级失败已落 failed+error
                logger.exception("background ingest failed: %s", task_id)

        threading.Thread(target=_run, args=(result["task_id"],), daemon=True).start()
        return result

    return mcp
