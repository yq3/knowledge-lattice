"""任务端点（design §6.2——M0a：任务状态查询；M2.1：cancel）。

cancel（TC-TASK-03）：对非终态任务 POST cancel——阶段边界停止（在途 worker 经
should_continue 心跳探测）、幂等续跑不复活（failed+'cancelled:' 为吸收态）、
文档状态一致不滞留 parsing（pending 版本同款 T8 落失败 + 删块）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from knowledge_lattice.core.docs.ingest import (
    UploadNotFoundError,
    UploadPermissionError,
)
from knowledge_lattice.domain.auth import AuthContext

from .upload import get_auth, get_service, org_scoped

router = APIRouter()


def _task_payload(t: dict) -> dict:
    return {
        "task_id": t["id"],
        "doc_id": t["doc_id"],
        "type": t["type"],
        "status": t["status"],
        "attempts": t["attempts"],
        "target_version": t.get("target_version"),  # P3-N8（m2-1 移交→m2-2）：
        # 任务目标版本入 payload——取消/清扫语义（0005）对调用方可观测
        "error": t["error"],
        "lease_owner": t.get("lease_owner"),
        "lease_until": t.get("lease_until"),
        "heartbeat_at": t.get("heartbeat_at"),
        "created_at": t["created_at"],
        "updated_at": t["updated_at"],
    }


@router.get("/api/orgs/{org}/tasks")
async def list_tasks(
    org: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    org = org_scoped(request, org, auth)
    tasks = get_service(request).backend.list_tasks(org)
    return {"tasks": [_task_payload(t) for t in tasks]}


@router.get("/api/orgs/{org}/tasks/{task_id}")
async def get_task(
    org: str, task_id: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    org = org_scoped(request, org, auth)
    task = get_service(request).backend.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    doc = get_service(request).backend.get_document(task["doc_id"])
    if doc is None or doc["org_id"] != org:
        raise HTTPException(status_code=404, detail="task not found")
    return _task_payload(task)


@router.post("/api/orgs/{org}/tasks/{task_id}/cancel")
async def cancel_task(
    org: str, task_id: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    """任务取消（TC-TASK-03）：非终态 → failed+'cancelled: by user request'（在途
    worker 阶段边界停止）；已终态幂等返回现态（不复活）。权限 = owner/org_admin
    （FR-4 操作矩阵，与删除/覆盖上传同款）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    try:
        task = service.ingest.cancel_task(
            org_id=org, task_id=task_id, actor_user_id=auth.user_id
        )
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UploadPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    payload = _task_payload(task)
    payload["cancelled"] = (payload["status"] == "failed"
                            and (payload["error"] or "").startswith("cancelled:"))
    return payload
