"""文档管理端点（design §6.2——M1-2 最小管理面：详情 / PATCH 维度 / DELETE）。

- GET /documents/{id}：在用/处理中双态四字段（M0a 已有——active/pending ×
  version/status/error，P0-2.2）；
- PATCH /documents/{id}/dimensions（§6.2）：修改维度——pending 期间 409
  （P0-2.1）；新旧取值均在操作者授权内（403，#31 P1-1/TC-AZ-01）；直接写
  document_dimensions（D6 刷维度不重嵌——dims_json 投影已随拍板①删除）；
- DELETE /documents/{id}：owner/org_admin；取消其任务（级联删——T19①/TC-VER-07）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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


class DimsPatchBody(BaseModel):
    """PATCH 维度请求体：{key: [values]} 按 key 全量替换（未提及的 key 不动——
    TC-AZ-01 [CN]→[OS] 语义；M1-2 最小面口径）。"""

    dims: dict[str, list[str]]


@router.patch("/api/orgs/{org}/documents/{doc_id}/dimensions")
async def patch_document_dims(
    org: str,
    doc_id: str,
    body: DimsPatchBody,
    request: Request,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """修改文档维度（M1-2 ACL 写链最小面——校验链见 core.ingest.patch_document_dims）。"""
    from knowledge_lattice.core.docs.ingest import (
        UploadConflictError,
        UploadNotFoundError,
        UploadPermissionError,
        UploadValidationError,
    )

    org = org_scoped(request, org, auth)
    service = get_service(request)
    try:
        service.ingest.patch_document_dims(
            org_id=org, doc_id=doc_id, dims=body.dims, actor_user_id=auth.user_id
        )
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UploadPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except UploadConflictError as exc:  # pending 期间 409（P0-2.1）
        return JSONResponse({"error": str(exc)}, status_code=409)
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    doc = service.backend.get_document(doc_id)
    return {"doc_id": doc_id, "dims": service.backend.get_document_dims(doc_id)}


@router.delete("/api/orgs/{org}/documents/{doc_id}", status_code=204)
async def delete_document(
    org: str, doc_id: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> None:
    """删除文档（owner/org_admin——FR-4 操作矩阵；取消其任务+级联删，T19①）。"""
    from knowledge_lattice.core.docs.ingest import (
        UploadNotFoundError,
        UploadPermissionError,
    )

    org = org_scoped(request, org, auth)
    service = get_service(request)
    try:
        service.ingest.delete_document(
            org_id=org, doc_id=doc_id, actor_user_id=auth.user_id
        )
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UploadPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
