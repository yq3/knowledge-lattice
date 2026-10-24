"""任务端点（design §6.2——M0a：任务状态查询；cancel 随 M2）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from knowledge_lattice.domain.auth import AuthContext

from .upload import get_auth, get_service, org_scoped

router = APIRouter()


@router.get("/api/orgs/{org}/tasks")
async def list_tasks(
    org: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    org = org_scoped(request, org, auth)
    tasks = get_service(request).backend.list_tasks(org)
    return {
        "tasks": [
            {
                "task_id": t["id"],
                "doc_id": t["doc_id"],
                "type": t["type"],
                "status": t["status"],
                "attempts": t["attempts"],
                "error": t["error"],
                "created_at": t["created_at"],
                "updated_at": t["updated_at"],
            }
            for t in tasks
        ]
    }


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
    return {
        "task_id": task["id"],
        "doc_id": task["doc_id"],
        "type": task["type"],
        "status": task["status"],
        "attempts": task["attempts"],
        "error": task["error"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
    }
