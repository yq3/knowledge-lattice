"""FastMCP 单一 server（design §3 mcp/server.py + §6.1 docs 组——search/fetch/
upload/list_documents 全四工具就位，M1-5 收口）。

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
  摄取成功入队后置已用（v1.4 口径）；摄取经 worker 框架异步执行（M2.1——工具
  立即返回 queued）；
- `list_documents` 工具（M1-5，design §6.1）：列出权限内可见的知识库与文档及
  处理状态——input datasets/active_status/limit；output datasets（doc_count
  **按调用者权限统计**——TC-AZ-02：不可见文档的存在与数量不泄露）+ documents
  （双态四字段 + dims + chunk_count + source + updated_at）；与 TC-AZ-03 管理
  列表为**两个端点两个口径**（MCP 按调用者 ACL / 管理面 M2）；统计与清单复用
  visible_docs CTE（compile_acl 产物）与 _attach_dims（D22 真相源）；
- 组织上下文（D18/TC-AUTH-02）：token org claim 优先 / 运行时注入 X-Org-Id 头兜底；
  并存且不一致 → 400（ToolError）；缺失 → 400；**工具参数 org 一律忽略并记审计**；
- 60s 超时中间件（ragflow 纪律——超时请求不悬挂，TC-E2E-06）；超时值随
  settings.mcp_timeout_s（默认 60，测试可注入短值）。

semantic 组（D23 §6.3——m2s-2 首批三工具：get_entity / search_entities /
describe_table；annotate 归 M2-S2 后段、search 实体参数归 M2-S3）：

- 权限（§6.3 权限口径）：组织隔离硬约束（org 作用域查询第一条件——T-S7）；
  semantic:read = 组织成员默认具备（无成员关系 403）；**不复用维度 ACL 编译器**；
  restricted 实体 fail-closed 静默（404/无命中/不出现——T-S9，持权路径 M2-S3）；
- get_entity：key/id 二选一 + expand 方向后缀 + depth≤2/fanout≤200（超限 400
  ——附录 A-11）；多跳由 Agent 迭代调用；
- search_entities：alias 精确 > 前缀 > label 模糊（拼音/向量 M2-S3）；q≤200、
  top_k≤50；
- describe_table：只对已登记 table 实体开放（403 防枚举数仓）+ 3s 超时降级
  degraded=true + 5min 缓存（T-S11）。
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
from knowledge_lattice.core.docs.acl import AclDeniedError, compile_acl
from knowledge_lattice.core.docs.credentials import CredentialError
from knowledge_lattice.core.docs.fetch import FetchNotFoundError, fetch_chunks
from knowledge_lattice.core.docs.ingest import (
    UploadConflictError,
    UploadNotFoundError,
    UploadPermissionError,
    UploadValidationError,
)
from knowledge_lattice.core.docs.retrieve import search as run_search
from knowledge_lattice.core.semantic.expand import EntityNotFound, get_entity
from knowledge_lattice.core.semantic.lookup import (
    DescribeTableDenied,
    describe_table,
    search_entities,
)
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

LIST_DOCUMENTS_TOOL_DESCRIPTION = (
    "列出权限内可见的知识库与文档及处理状态。先了解库里有什么，再决定搜什么；"
    "全部统计按调用者权限计算（不可见文档不出现）。datasets 可按库收窄、"
    "active_status 可按处理状态过滤、limit 控制返回条数（缺省 50）。"
)

GET_ENTITY_TOOL_DESCRIPTION = (
    "读取业务实体详情并展开类型化关系（模板/字段/表/列/报表项/概念等）。"
    "key 形如 'type:key'（如 template:TPL_VAT_INPUT），或用 id；expand 指定关系"
    "类型可带方向后缀（'backed_by>' 出向、'derived_from<' 入向）；多跳场景请"
    "对返回节点迭代调用本工具（depth ≤2、fanout_limit ≤200）。"
)

SEARCH_ENTITIES_TOOL_DESCRIPTION = (
    "按名称、别名或描述片段查业务实体（先查到实体再用 get_entity 取详情）。"
    "排序：别名精确命中 > 别名前缀 > 名称模糊；top_k ≤50、q ≤200。"
)

DESCRIBE_TABLE_TOOL_DESCRIPTION = (
    "查数据表的列详情（列名/类型/注释/样例——透传元数据系统，只对已登记的表开放）。"
    "回答「这张表有哪些列、某字段什么类型」时调用；columns 可按列名过滤。"
)

# 文档 active_status 合法值（DDL 口径——#33 P0-2.2 列注释：
# searchable_lexical | searchable_full | degraded；`failed` 属 pending_status 域
# ——P2-3：非法值 400 而非静默空列表误导 LLM）
_ACTIVE_STATUSES = frozenset({"searchable_lexical", "searchable_full", "degraded"})
LIST_DOCUMENTS_HARD_LIMIT = 200  # limit 服务端硬上限（§6.1 缺省 50；防大响应）


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
        instructions=(
            "企业知识层 MCP 工具：docs 组（search + fetch + upload + "
            "list_documents）+ semantic 组（get_entity + search_entities + "
            "describe_table）。"
        ),
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

    def _sem_member(auth: AuthContext, org_id: str) -> None:
        """semantic:read 门控（§6.3 权限口径：组织成员默认具备——无成员关系
        403；语义层不复用维度 ACL 编译器）。"""
        if service.backend.read_membership(auth.user_id, org_id) is None:
            raise ToolError(
                f"403: semantic:read 需组织成员（no active membership:"
                f" user={auth.user_id!r} org={org_id!r}）"
            )

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

        def _run() -> None:  # 投递 worker（M2.1：inline 同步认领 / subprocess 唤醒
            #             字节——任务级失败已落 failed+error，不冒泡）
            if service.worker is not None:
                service.worker.kick()

        threading.Thread(target=_run, daemon=True).start()
        return result

    @mcp.tool(name="list_documents", description=LIST_DOCUMENTS_TOOL_DESCRIPTION)
    def list_documents(
        datasets: list[str] | None = None,
        active_status: str | None = None,
        limit: int = 50,
        ctx: Context = None,
    ) -> dict:
        """list_documents（§6.1）：权限内知识库与文档清单——datasets 统计
        （doc_count 按调用者权限）+ documents（双态四字段 + dims + chunk_count +
        source + updated_at）。T17：owner 经此看处理中/在用文档（管理面，无块
        内容）；TC-AZ-02：统计按调用者 ACL；TC-AZ-03：与管理列表（M2）两个
        端点两个口径。"""
        auth, org_id = _auth_and_org(ctx, param_org=None)
        if active_status is not None and active_status not in _ACTIVE_STATUSES:
            raise ToolError(
                f"400: invalid active_status {active_status!r}"
                f"（合法值：{sorted(_ACTIVE_STATUSES)}）"
            )
        limit = max(1, min(limit, LIST_DOCUMENTS_HARD_LIMIT))
        try:
            plan = compile_acl(service.backend, auth.user_id, org_id, dataset_ids=datasets)
            counts = service.backend.visible_dataset_counts(plan, dataset_ids=datasets)
            rows = service.backend.visible_documents(
                plan, dataset_ids=datasets, active_status=active_status, limit=limit
            )
        except AclDeniedError as exc:  # P2-4：与 search/fetch/upload 同款 403 映射
            raise ToolError(f"403: {exc}（code={exc.code}）") from exc
        documents = [
            {
                "doc_id": r["doc_id"],
                "dataset": r["dataset_id"],
                "dataset_name": r.get("dataset_name"),
                "title": r.get("title"),
                "active_version": r["active_version"],
                "active_status": r["active_status"],
                "pending_version": r["pending_version"],
                "pending_status": r["pending_status"],
                "dims": r.get("dims") or {},
                "chunk_count": r["chunk_count"],
                "source": r.get("source_uri"),
                "updated_at": r.get("updated_at"),
            }
            for r in rows
        ]
        return {"datasets": counts, "documents": documents}

    # ---- semantic 组（D23 §6.3——m2s-2 首批三工具） ----

    @mcp.tool(name="get_entity", description=GET_ENTITY_TOOL_DESCRIPTION)
    def semantic_get_entity(
        id: int | None = None,
        key: str | None = None,
        expand: list[str] | None = None,
        depth: int = 1,
        fanout_limit: int = 50,
        include: list[str] | None = None,
        ctx: Context = None,
    ) -> dict:
        """get_entity（§6.3）：实体详情 + 类型化关系展开（rel_type 分组邻接、
        多跳迭代调用）；restricted 实体 404（fail-closed——T-S9）。"""
        auth, org_id = _auth_and_org(ctx, param_org=None)
        _sem_member(auth, org_id)
        try:
            return get_entity(
                service.backend, org_id,
                entity_id=id, key=key, expand=expand, depth=depth,
                fanout_limit=fanout_limit, include=include,
            )
        except EntityNotFound as exc:
            raise ToolError(f"404: {exc}") from exc
        except ValueError as exc:
            raise ToolError(f"400: {exc}") from exc

    @mcp.tool(name="search_entities", description=SEARCH_ENTITIES_TOOL_DESCRIPTION)
    def semantic_search_entities(
        q: str,
        types: list[str] | None = None,
        top_k: int = 10,
        ctx: Context = None,
    ) -> dict:
        """search_entities（§6.3）：别名精确 > 前缀 > 名称模糊三层排序
        （拼音/向量归后续段）；q ≤200、top_k ≤50。"""
        auth, org_id = _auth_and_org(ctx, param_org=None)
        _sem_member(auth, org_id)
        try:
            return search_entities(
                service.backend, org_id, q, types=types, top_k=top_k
            )
        except ValueError as exc:
            raise ToolError(f"400: {exc}") from exc

    @mcp.tool(name="describe_table", description=DESCRIBE_TABLE_TOOL_DESCRIPTION)
    def semantic_describe_table(
        table: str,
        columns: list[str] | None = None,
        ctx: Context = None,
    ) -> dict:
        """describe_table（§6.3/T-S11）：表/列详情透传元数据系统——只对已登记
        table 实体开放（未登记 403）；元数据系统不可用返回轻量节点 +
        degraded=true；5 分钟缓存。"""
        auth, org_id = _auth_and_org(ctx, param_org=None)
        _sem_member(auth, org_id)
        try:
            return describe_table(
                service.backend, settings, org_id, table, columns=columns
            )
        except DescribeTableDenied as exc:
            raise ToolError(f"403: {exc}") from exc

    return mcp
