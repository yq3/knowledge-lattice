"""语义层同步端点（design §6.2 L1141/1143——M2-S1）：

- POST /api/orgs/{org}/semantic/sync/{adapter}：手动触发同步——**semantic:admin**
  （org_admin 兼任，§6.3——普通成员 403）；入队 semantic_sync 任务（payload
  {org, adapter}）+ kick worker + outbox 留痕（TC-SYNC-08①②）；
- GET /api/orgs/{org}/semantic/sync-runs：同步记录与冲突报告（stats_json 内含
  conflicts 明细——TC-SYNC-04）；
- GET /api/orgs/{org}/semantic/builds：构建记录（**本段恒空列表**——构建接入
  归 m2s-2）。

权限口径（§6.2 L1143）：两查询端点同 `semantic:admin`（org_admin 可见、普通
成员 403——TC-SYNC-08③）。分层纪律：识别面（auto_entities）钉 api/mcp 层且
本段无识别面；端点只做协议转换 + 编排调用（core/semantic/sync）。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from knowledge_lattice.core.semantic.constants import SYNC_ADAPTERS
from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_SYNC

from .upload import get_auth, get_service, org_scoped

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_semantic_admin(service, org: str, auth) -> None:
    """semantic:admin 门控（org_admin 兼任——design §6.3 语义层权限）。"""
    membership = service.backend.read_membership(auth.user_id, org)
    if membership is None or membership["role"] != "org_admin":
        raise HTTPException(
            status_code=403,
            detail="semantic:admin required（org_admin 兼任——§6.3 语义层权限）",
        )


@router.post("/api/orgs/{org}/semantic/sync/{adapter}", status_code=202)
async def trigger_semantic_sync(
    org: str,
    adapter: str,
    request: Request,
    background: BackgroundTasks,
    auth=Depends(get_auth),
) -> dict:
    """手动触发同步（semantic:admin + outbox；立返任务标识——TC-SYNC-08①②）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_admin(service, org, auth)

    from knowledge_lattice.core.semantic.adapters import ADAPTER_FACTORIES

    if adapter not in (*SYNC_ADAPTERS, *ADAPTER_FACTORIES):
        raise HTTPException(
            status_code=404, detail=f"unknown semantic sync adapter: {adapter!r}"
        )

    backend = service.backend
    task_id = backend.create_task(
        None, task_type="semantic_sync",
        payload=json.dumps({"org": org, "adapter": adapter}),
    )
    backend.append_outbox(
        EVENT_SEMANTIC_SYNC,
        json.dumps(
            {"org_id": org, "adapter": adapter, "task_id": task_id,
             "phase": "triggered", "actor": auth.user_id},
            ensure_ascii=False,
        ),
    )

    def _kick() -> None:  # inline 同步认领 / subprocess 唤醒字节（M2.1 同款）
        if service.worker is not None:
            service.worker.kick()

    background.add_task(_kick)
    return {"task_id": task_id, "status": "queued", "org": org, "adapter": adapter}


@router.get("/api/orgs/{org}/semantic/sync-runs")
async def list_semantic_sync_runs(
    org: str, request: Request, auth=Depends(get_auth)
) -> dict:
    """同步记录与冲突报告（semantic:admin——TC-SYNC-08③/TC-SYNC-04）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_admin(service, org, auth)
    return {"runs": service.backend.sem_list_sync_runs(org)}


@router.get("/api/orgs/{org}/semantic/builds")
async def list_semantic_builds(
    org: str, request: Request, auth=Depends(get_auth)
) -> dict:
    """构建记录（semantic:admin——本段恒空列表，构建接入归 m2s-2）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_admin(service, org, auth)
    return {"builds": service.backend.sem_list_builds(org)}
