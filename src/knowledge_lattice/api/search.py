"""检索端点（design §6.2——POST /api/search：检索测试页）。

参数同 MCP search（§6.1）：m2s-6/M2-S3 起新增 ``entities``（≤20 实体 id）
与 ``auto_entities``（服务端〔**api/mcp 层——§3 规则 2**〕先对 query 跑
一遍 AC 识别再实体召回）——实体参数解析/展开经 core/semantic/recall
（识别钉 api/mcp 层，core/docs/retrieve 不调 annotate）；返回块附
matched_entities（实体路命中——§5.10）。

组织上下文经 resolve_org 统一规则：token org claim 优先 / X-Org-Id 头兜底、
不一致 400、缺失 400（v0.9.4 按实现登记——原「X-Org-Id 例外」为 v0.4 表述
已作废，D18）。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from knowledge_lattice.core.docs.retrieve import search as run_search
from knowledge_lattice.domain.auth import (
    REQUEST_PERMISSION_FIELD_KEYS,
    AuthContext,
    audit_ignored_permission_fields,
    resolve_org,
)

from .upload import get_auth, get_service

logger = logging.getLogger(__name__)

router = APIRouter()


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="allow")  # 权限字段检测需要（FR-4——忽略并记审计）
    query: str
    top_k: int = Field(default=8, ge=1, le=100)
    datasets: list[str] | None = None
    doc_filter: list[str] | None = None
    entities: list[int] | None = None      # 实体召回路种子（≤20——design §5.10）
    auto_entities: bool = False            # 服务端（api 层）AC 识别 query 后实体召回


@router.post("/api/search")
async def search(body: SearchRequest, request: Request) -> dict:
    service = get_service(request)
    auth: AuthContext = get_auth(request)
    org = resolve_org(
        org_claim=auth.org_claim, org_header=request.headers.get("x-org-id")
    )
    # 请求体权限字段 → 忽略并记审计、请求正常处理（FR-4/D18 v0.6.1 统一口径
    # ——附录 A-9；计权恒走 token 身份，请求体声明不参与）。审计在 org 上下文
    # 解析成功后落（P3-11——org 缺失/不一致的 400 请求不混入 ignored_fields
    # 事件，拒绝语义与忽略语义不叠加）
    present = [k for k in (body.model_extra or {}) if k in REQUEST_PERMISSION_FIELD_KEYS]
    audit_ignored_permission_fields(
        service.backend, user_id=auth.user_id, present_fields=present
    )
    # 实体参数解析（m2s-6：识别/展开钉 api/mcp 层——resolve_query_entities；
    # entities 与 auto_entities 并存时显式种子优先）
    entity_ctx = None
    if body.entities is not None or body.auto_entities:
        from knowledge_lattice.core.semantic.recall import (
            resolve_query_entities,
        )

        def _resolve():
            # P3-3/R3：标签/维度经 effective_settings 从 embedder 派生——
            # 与 semantic 查询/build 消费面同源（该路径无 vec 增益，一致性收口）
            from knowledge_lattice.config import effective_settings

            return resolve_query_entities(
                service.backend,
                effective_settings(service.settings, service.embedder), org,
                query=body.query, entities=body.entities,
                auto_entities=body.auto_entities,
            )

        try:
            entity_ctx = await asyncio.to_thread(_resolve)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    # 完整配方同步管线经 to_thread 下放（模型 HTTP 调用绝不阻塞事件循环——
    # NFR-8/TC-RET-04；MCP sync 工具由 FastMCP 线程池同款承接）
    return await asyncio.to_thread(
        run_search,
        service.backend,
        service.settings,
        user_id=auth.user_id,
        org_id=org,
        query=body.query,
        top_k=body.top_k,
        datasets=body.datasets,
        doc_filter=body.doc_filter,
        gate=service.gate,
        embedder=service.embedder,
        reranker=service.reranker,
        enhancer=service.enhancer,
        breakers=service.breakers,
        entity_ids=(entity_ctx or {}).get("entity_ids"),
        entity_seeds=(entity_ctx or {}).get("seeds"),
    )
