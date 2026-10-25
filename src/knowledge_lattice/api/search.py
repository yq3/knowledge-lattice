"""检索端点（design §6.2——POST /api/search：检索测试页；组织经 X-Org-Id——例外端点）。

参数同 MCP search（§6.1）；组织上下文统一规则：token org claim 优先 / X-Org-Id 头
兜底、不一致 400、缺失 400（D18）。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from knowledge_lattice.core.docs.retrieve import search as run_search
from knowledge_lattice.domain.auth import (
    AuthContext,
    authenticate,
    resolve_org,
)

from .upload import get_service

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=8, ge=1, le=100)
    datasets: list[str] | None = None
    doc_filter: list[str] | None = None


def _auth(request: Request) -> AuthContext:
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        from knowledge_lattice.domain.auth import AuthError

        raise AuthError("missing Bearer token")
    service = get_service(request)
    return authenticate(service.backend, service.settings, header[7:].strip())


@router.post("/api/search")
async def search(body: SearchRequest, request: Request) -> dict:
    service = get_service(request)
    auth = _auth(request)
    org = resolve_org(
        org_claim=auth.org_claim, org_header=request.headers.get("x-org-id")
    )
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
    )
