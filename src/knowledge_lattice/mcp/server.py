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
- 认证形态（m2-4 M2.2）：委托 token / SSO（service.sso 验签器注入——aud/act/
  JIT 在 domain/auth）与可信子系统（X-On-Behalf-Of + 在场证据三约束，T13）；
  工具参数 permissions（权限声明）忽略并记审计（FR-4/D18 v0.6.1——附录 A-9）；
- 60s 超时中间件（ragflow 纪律——超时请求不悬挂，TC-E2E-06）；超时值随
  settings.mcp_timeout_s（默认 60，测试可注入短值）。

semantic 组（D23 §6.3——m2s-2 首批三工具：get_entity / search_entities /
describe_table；annotate 归 M2-S2 后段、search 实体参数归 M2-S3）：

- 权限（§6.3 权限口径）：组织隔离硬约束（org 作用域查询第一条件——T-S7）；
  semantic:read = 组织成员默认具备（无成员关系 403）；**不复用维度 ACL 编译器**；
  restricted 实体 fail-closed 静默（404/无命中/不出现——T-S9，持权路径 M2-S3）；
- get_entity：key/id 二选一 + expand 方向后缀 + depth≤2/fanout≤200（超限 400
  ——附录 A-11）；多跳由 Agent 迭代调用；
- search_entities：alias 精确 > 前缀 > 拼音（同音错字）> label 模糊 > 向量
  近邻（m2s-6 全档——拼音/向量经模糊索引，embedder 注入时 vec 档生效）；
  q≤200、top_k≤50；
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
    audit_ignored_permission_fields,
    authenticate,
    resolve_org,
)

logger = logging.getLogger(__name__)

SEARCH_TOOL_DESCRIPTION = (
    "检索企业知识库。缺私有信息（制度/手册/申报口径）时调用；"
    "query 越具体越好（含税种、区域、文档关键词）；返回结果自带 chunk_id 溯源，"
    "回答时请引用。可传 entities（实体 id 列表，≤20）启用实体召回路，或"
    " auto_entities=true 由服务端先识别 query 中的业务对象再召回——命中的块"
    "附带 matched_entities 说明召回原因（对话中已识别实体时优先用它们检索）。"
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
    "按名称、别名、同音词或语义相近的描述片段查业务实体（先查到实体再用 "
    "get_entity 取详情）。排序：别名精确命中 > 别名前缀 > 拼音（同音错字）> "
    "名称模糊 > 向量近邻（语义相近——via='vec'）；top_k ≤50、q ≤200。"
)

DESCRIBE_TABLE_TOOL_DESCRIPTION = (
    "查数据表的列详情（列名/类型/注释/样例——透传元数据系统，只对已登记的表开放）。"
    "回答「这张表有哪些列、某字段什么类型」时调用；columns 可按列名过滤。"
)

ANNOTATE_TOOL_DESCRIPTION = (
    "识别文本中的业务术语与业务对象（概念/系统/场景/模板/模板字段/报表项/表/列），"
    "返回实体 ID、位置 span 与消歧路径（AC 自动机四步消歧 + L0 片段兜底；歧义命中"
    "返回全部候选标 ambiguous=true，必要时向用户确认）。每轮对话前调用；"
    "text ≤4000 字、context_entities ≤20（最近几轮已确认实体，辅助消歧）。"
    "fuzzy=true 开启第 3 层模糊兜底（同音错字/编辑距离/语义近邻——低信任候选）；"
    "**L1 无命中且判断句中有业务对象时，可自行改调 annotate(fuzzy=true) 再试**"
    "（G-2 并存裁定②——工具描述引导 agent 自调）。"
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

    def _auth_and_org(ctx: Context, *, param_org: str | None,
                      param_permissions: list[str] | None = None
                      ) -> tuple[AuthContext, str]:
        """认证 + 组织上下文统一规则（D18）——401/400 语义以 ToolError 透出；
        返回完整 AuthContext（M1-3：act＝服务身份进凭证三一致校验）。

        m2-4 M2.2：①SSO/委托 token 验签（service.sso 注入——aud/act 语义与
        JIT 建档在 domain/auth）；②X-On-Behalf-Of 头在场 → 可信子系统三约束
        路径（TC-AUTH-05/T13）；③工具参数 org（D18）与 permissions（FR-4/
        A-9）忽略并记审计——**对一切认证形态生效**（R2 P2-1：审计块在认证
        成功后统一执行，trusted 分支不提前 return 跳过）。
        """
        request = getattr(ctx.request_context, "request", None) if ctx else None
        auth_header = request.headers.get("authorization") if request is not None else None
        if not auth_header or not auth_header.lower().startswith("bearer "):
            raise ToolError("401: missing Bearer token（MCP 调用须持委托 token / SSO / 开发 JWT）")
        try:
            on_behalf_of = (
                request.headers.get("x-on-behalf-of") if request is not None else None
            )
            user_assertion = (
                request.headers.get("x-user-assertion") if request is not None else None
            )
            if on_behalf_of is not None or user_assertion is not None:
                from knowledge_lattice.domain.auth import authenticate_trusted

                # 可信子系统：org 上下文由 X-Org-Id 承载（服务凭证无 org claim，
                # 约束③）；缺失/越界在 authenticate_trusted 内 fail-closed
                auth = authenticate_trusted(
                    service.backend,
                    service_token=auth_header[7:].strip(),
                    on_behalf_of=on_behalf_of,
                    user_assertion=user_assertion,
                    org=request.headers.get("x-org-id") if request is not None else None,
                    sso=getattr(service, "sso", None),
                    registry=getattr(service, "trusted", None),
                )
            else:
                auth = authenticate(
                    service.backend, settings, auth_header[7:].strip(),
                    sso=getattr(service, "sso", None),
                )
        except AuthError as exc:
            raise ToolError(f"{exc.code}: {exc}") from exc
        except OrgContextError as exc:
            raise ToolError(f"400: {exc}") from exc
        # ---- 组织上下文统一规则（trusted 路径 claim=已校验的 X-Org-Id，直通） ----
        org_header = request.headers.get("x-org-id") if request is not None else None
        try:
            org = resolve_org(org_claim=auth.org_claim, org_header=org_header)
        except OrgContextError as exc:
            raise ToolError(f"400: {exc}") from exc
        # ---- 工具参数忽略审计（公共块——一切认证形态，R2 P2-1；m2-4
        #      followup ⑤/m2-5：移至 resolve_org **成功后**——org 上下文 400
        #      的请求不写忽略事件（拒绝语义与忽略语义不叠加，与 REST 面
        #      m2-4 R2 P3-11 同口径） ----
        # 工具参数 org 一律忽略并记审计（D18——org 不是 LLM 可填参数）
        if param_org is not None:
            service.backend.append_outbox(
                "mcp.org_param_ignored",
                json.dumps(
                    {"user_id": auth.user_id, "ignored_org": param_org}, ensure_ascii=False
                ),
            )
        # 工具参数权限声明 → 忽略并记审计（FR-4/D18——附录 A-9 统一口径）
        if param_permissions is not None:
            audit_ignored_permission_fields(
                service.backend, user_id=auth.user_id,
                present_fields=["permissions"],
            )
        return auth, org

    def _sem_member(auth: AuthContext, org_id: str) -> None:
        """semantic:read 门控（§6.3 权限口径：组织成员默认具备——无成员关系
        403；语义层不复用维度 ACL 编译器）。"""
        if service.backend.read_membership(auth.user_id, org_id) is None:
            raise ToolError(
                f"403: semantic:read 需组织成员（no active membership:"
                f" user={auth.user_id!r} org={org_id!r}）"
            )

    def _sem_restricted(auth: AuthContext, org_id: str) -> bool:
        """semantic:restricted 持权判定（T-S9 持权路径——m2s-6）：membership
        role = sem_restricted（极少数敏感实体可见权，§6.3 权限口径③——
        org_admin 不默认兼任）。"""
        membership = service.backend.read_membership(auth.user_id, org_id)
        return bool(
            membership
            and membership.get("role") == "sem_restricted"
        )

    def _audit_restricted(auth: AuthContext, org_id: str, tool: str,
                          entity_ids: list[int]) -> None:
        """持权访问 restricted 实体的权限事件（A-16 口径持权面——outbox）。"""
        if not entity_ids:
            return
        from knowledge_lattice.core.semantic.constants import (
            EVENT_SEMANTIC_RESTRICTED_ACCESS,
        )

        try:
            service.backend.append_outbox(
                EVENT_SEMANTIC_RESTRICTED_ACCESS,
                json.dumps(
                    {"org_id": org_id, "user_id": auth.user_id, "tool": tool,
                     "entity_ids": sorted(set(entity_ids))},
                    ensure_ascii=False,
                ),
            )
        except Exception:  # noqa: BLE001 —— 审计失败不阻断识别主路径
            logger.exception("restricted access audit write failed")

    def _restricted_hit_ids(org_id: str, result: dict) -> list[int]:
        """annotate 结果中 restricted 实体命中（持权面审计数据源——同锚
        get_annotator 缓存实例判定，零额外构建）。"""
        from knowledge_lattice.core.semantic.annotator import get_annotator

        ann, _rev = get_annotator(service.backend, org_id, settings)
        if ann is None:
            return []
        out = []
        for m in result.get("mentions") or ():
            ent = ann.entities.get(m.get("entity_id"))
            if ent is not None and ent.get("sensitivity") == "restricted":
                out.append(m["entity_id"])
        return out

    def _entity_is_restricted(org_id: str, entity_id, key) -> bool:
        """get_entity 目标行 restricted 判定（持权面审计数据源）。"""
        if key is not None and ":" in key:
            type_, _, k = key.partition(":")
            row = service.backend.sem_entity_by_key(org_id, type_, k)
        else:
            row = service.backend.sem_entity_by_id(org_id, entity_id)
        return bool(row and row["sensitivity"] == "restricted")

    @mcp.tool(name="search", description=SEARCH_TOOL_DESCRIPTION)
    def search(
        query: str,
        top_k: int = 8,
        datasets: list[str] | None = None,
        doc_filter: list[str] | None = None,
        entities: list[int] | None = None,
        auto_entities: bool = False,
        org: str | None = None,  # deprecated——忽略并记审计（D18：org 来自 token claim / 注入头）
        permissions: list[str] | None = None,  # deprecated——忽略并记审计（FR-4：权限声明不来自请求方）
        ctx: Context = None,
    ) -> dict:
        """search（§6.1）：完整配方检索 + 实体召回路（M2-S3/m2s-6——§5.10）。

        entities/auto_entities 解析钉本（api/mcp）层——resolve_query_entities
        识别与展开（core/docs 不调 annotate，§3 规则 2）；返回块附
        matched_entities（实体路命中——agent 解释召回原因）。"""
        auth, org_id = _auth_and_org(
            ctx, param_org=org, param_permissions=permissions
        )
        entity_ctx = None
        if entities is not None or auto_entities:
            from knowledge_lattice.core.semantic.recall import (
                resolve_query_entities,
            )

            from knowledge_lattice.config import effective_settings

            try:
                entity_ctx = resolve_query_entities(
                    service.backend,
                    effective_settings(settings, service.embedder),
                    org_id, query=query,
                    entities=entities, auto_entities=auto_entities,
                )
            except ValueError as exc:
                raise ToolError(f"400: {exc}") from exc
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
                entity_ids=(entity_ctx or {}).get("entity_ids"),
                entity_seeds=(entity_ctx or {}).get("seeds"),
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

    # ---- semantic 组（D23 §6.3——m2s-2 三工具 + m2s-4 annotate） ----

    @mcp.tool(name="annotate", description=ANNOTATE_TOOL_DESCRIPTION)
    def semantic_annotate(
        text: str,
        context_entities: list[int] | None = None,
        prefer_types: list[str] | None = None,
        fuzzy: bool = False,
        ctx: Context = None,
    ) -> dict:
        """annotate（§6.3 / 任务书 m2s-4 A2 + m2s-6 模糊层）：AC 自动机识别 +
        四步消歧（精确全词→别名→上下文短别名→L0 片段兜底）+ 最长匹配优先；
        fuzzy=true 跑第 3 层模糊兜底（§5.9——同音错字/编辑距离/语义近邻，
        低信任候选落 candidates、中间件不自动注入）；负样本零标注；
        restricted 实体表现为不存在（T-S9——持 semantic:restricted 者可见）。"""
        auth, org_id = _auth_and_org(ctx, param_org=None)
        _sem_member(auth, org_id)
        can_restricted = _sem_restricted(auth, org_id)
        from knowledge_lattice.core.semantic.annotator import annotate_text

        from knowledge_lattice.config import effective_settings

        try:
            result = annotate_text(
                service.backend,
                effective_settings(settings, service.embedder), org_id, text,
                context_entities=context_entities,
                prefer_types=prefer_types,
                fuzzy=fuzzy,
                include_restricted=can_restricted,
                embedder=getattr(service, "embedder", None),
            )
            if can_restricted:
                _audit_restricted(
                    auth, org_id, "annotate", _restricted_hit_ids(org_id, result))
            return result
        except ValueError as exc:
            raise ToolError(f"400: {exc}") from exc

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
        多跳迭代调用）；restricted 实体 404（fail-closed——T-S9；持
        semantic:restricted 者可见，m2s-6 持权路径）。"""
        auth, org_id = _auth_and_org(ctx, param_org=None)
        _sem_member(auth, org_id)
        can_restricted = _sem_restricted(auth, org_id)
        try:
            result = get_entity(
                service.backend, org_id,
                entity_id=id, key=key, expand=expand, depth=depth,
                fanout_limit=fanout_limit, include=include,
                can_restricted=can_restricted,
            )
        except EntityNotFound as exc:
            raise ToolError(f"404: {exc}") from exc
        except ValueError as exc:
            raise ToolError(f"400: {exc}") from exc
        if can_restricted and result["entity"].get("curated") is not None \
                and _entity_is_restricted(org_id, id, key):
            _audit_restricted(auth, org_id, "get_entity", [result["entity"]["id"]])
        return result

    @mcp.tool(name="search_entities", description=SEARCH_ENTITIES_TOOL_DESCRIPTION)
    def semantic_search_entities(
        q: str,
        types: list[str] | None = None,
        top_k: int = 10,
        ctx: Context = None,
    ) -> dict:
        """search_entities（§6.3）：别名精确 > 前缀 > 拼音 > 名称模糊 > 向量
        近邻排序链（m2s-6 全档——拼音/向量层经模糊索引）；q ≤200、top_k ≤50。"""
        auth, org_id = _auth_and_org(ctx, param_org=None)
        _sem_member(auth, org_id)
        try:
            from knowledge_lattice.config import effective_settings

            return search_entities(
                service.backend, org_id, q, types=types, top_k=top_k,
                settings=effective_settings(settings, service.embedder),
                embedder=getattr(service, "embedder", None),
                # G-24③（m2-5）：vec 档有界超时/熔断/降级审计——共享 embed
                # 熔断器与 §5.2 检索向量路同一状态
                breakers=service.breakers, user_id=auth.user_id,
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
        except Exception as exc:  # noqa: BLE001 —— P1-1⑤/R2：默认通道意外异常
            # 不裸露为 fastmcp 内部错误栈——统一 ToolError 500（透传/构造类
            # 失败已在 core 降级，此处仅兜底防泄漏栈帧）
            logger.exception("describe_table unexpected failure: org=%s table=%s",
                             org_id, table)
            raise ToolError(
                f"500: describe_table 内部错误（{type(exc).__name__}——已记录，"
                "请稍后重试或联系运维）"
            ) from exc

    return mcp
