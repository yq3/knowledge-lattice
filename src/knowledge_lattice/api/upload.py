"""REST 端点：上传入口（design §6.2——M0a multipart 直传；凭证三步随 M1-3）。

POST /api/orgs/{org}/documents：multipart 上传 → 校验（api 只做协议转换，业务校验
在 core 摄取入口——v0.8.3）→ 建文档+任务（pending）→ 后台执行摄取管线（M0a 进程内
执行器）→ 202 {doc_id, task_id, status: queued}。

M1-2：`doc_id` Form 字段显式携带 = 覆盖上传（文档更新——§5.3）：操作权限
（owner/org_admin）+ pending 409（T7）+ 新版本号 max+1；pending_version 随响应。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from knowledge_lattice.core.docs.acl import AclDeniedError
from knowledge_lattice.core.docs.ingest import (
    UploadConflictError,
    UploadNotFoundError,
    UploadPermissionError,
    UploadValidationError,
)
from knowledge_lattice.domain.auth import (
    AuthContext,
    AuthError,
    OrgContextError,
    authenticate,
    check_path_org,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_service(request: Request):
    return request.app.state.service


def get_auth(request: Request) -> AuthContext:
    """Bearer 认证依赖（401 → 401；无头 → 401）。"""
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        raise AuthError("missing Bearer token")
    service = get_service(request)
    return authenticate(service.backend, service.settings, header[7:].strip())


def org_scoped(request: Request, org: str, auth: AuthContext) -> str:
    """组织作用域统一规则：路径 org 与 X-Org-Id 并存且不一致 → 400；成员关系校验 403。"""
    try:
        resolved = check_path_org(path_org=org, org_header=request.headers.get("x-org-id"))
    except OrgContextError as exc:
        raise OrgContextError(str(exc)) from exc
    service = get_service(request)
    if service.backend.read_membership(auth.user_id, resolved) is None:
        raise AclDeniedError(
            f"no active membership: user={auth.user_id!r} org={resolved!r}"
        )
    return resolved


@router.post("/api/orgs/{org}/documents", status_code=202)
async def upload_document(
    org: str,
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    dataset: str = Form(...),
    title: str | None = Form(None),
    dims: str = Form(""),
    doc_id: str | None = Form(None),  # 覆盖更新显式携带（文档身份——§6.2）
    auth: AuthContext = Depends(get_auth),
) -> JSONResponse:
    service = get_service(request)
    org = org_scoped(request, org, auth)
    try:
        dims_dict: dict[str, list[str]] = json.loads(dims) if dims else {}
    except json.JSONDecodeError as exc:
        return JSONResponse({"error": f"dims must be JSON: {exc}"}, status_code=400)
    if not isinstance(dims_dict, dict) or not all(
        isinstance(v, list) and all(isinstance(x, str) for x in v) for v in dims_dict.values()
    ):
        return JSONResponse(
            {"error": "dims must be {dimension_key: [values]}"}, status_code=400
        )

    file_bytes = await file.read()
    try:
        new_doc_id, task_id = service.ingest.create_document(
            org_id=org,
            dataset_id=dataset,
            title=title or "",
            dims=dims_dict,
            owner_user_id=auth.user_id,
            file_bytes=file_bytes,
            mime_type=file.content_type or "application/octet-stream",
            filename=file.filename or "upload.bin",
            doc_id=doc_id,
        )
    except UploadValidationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except UploadPermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except UploadConflictError as exc:  # T7：pending 期间只有一个处理中版本
        return JSONResponse({"error": str(exc)}, status_code=409)
    except UploadNotFoundError as exc:  # 覆盖目标不存在/跨组织（存在性敏感）
        return JSONResponse({"error": str(exc)}, status_code=404)

    pending_version = service.backend.get_document(new_doc_id)["pending_version"]

    def _run() -> None:  # 后台执行摄取（任务级失败已落 failed+error——不冒泡响应）
        try:
            service.ingest.run_task(task_id)
        except Exception:  # noqa: BLE001
            logger.exception("background ingest failed: %s", task_id)

    background.add_task(_run)
    return JSONResponse(
        {
            "doc_id": new_doc_id,
            "task_id": task_id,
            "status": "queued",
            "pending_version": pending_version,
        },
        status_code=202,
    )
