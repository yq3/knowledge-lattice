"""文档管理端点（design §6.2——M0a 最小：详情状态轮询；PATCH/DELETE/reindex 随 M1+）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from knowledge_lattice.domain.auth import AuthContext

from .upload import get_auth, get_service, org_scoped

router = APIRouter()


@router.get("/api/orgs/{org}/documents/{doc_id}")
async def document_detail(
    org: str, doc_id: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    """详情：在用/处理中双态字段（active/pending × version/status/error——P0-2.2）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    doc = service.backend.get_document(doc_id)
    if doc is None or doc["org_id"] != org:
        raise HTTPException(status_code=404, detail="document not found")
    return {
        "doc_id": doc["id"],
        "title": doc["title"],
        "dataset": doc["dataset_id"],
        "active_version": doc["active_version"],
        "active_status": doc["active_status"],
        "active_error": doc["active_error"],
        "pending_version": doc["pending_version"],
        "pending_status": doc["pending_status"],
        "pending_error": doc["pending_error"],
        "source": doc["source_uri"],
        "updated_at": doc["updated_at"],
    }
