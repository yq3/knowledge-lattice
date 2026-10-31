"""语义层管理端点（design §6.2 L1141/1143——M2-S1 起、m2s-2 补全构建面）：

- POST /api/orgs/{org}/semantic/sync/{adapter}：手动触发同步——**semantic:admin**
  （org_admin 兼任，§6.3——普通成员 403）；入队 semantic_sync 任务（payload
  {org, adapter, force}）+ kick worker + outbox 留痕（TC-SYNC-08①②）；
  `?force=true` = B2 运维放行（跳过删除比例保护——T-S2 v1.9.1）；
  无工厂覆盖时 resolve_source_config fail-fast（P3-7——未配置/畸形 400）；
  **G-16 收口（m2s-2）**：任务行与触发事件经 create_task(audit=) **同一事务**；
- GET /api/orgs/{org}/semantic/sync-runs：同步记录与冲突报告（stats_json 内含
  conflicts 明细——TC-SYNC-04）；m2s-2 管理语义：limit 分页 + adapter/status
  过滤（design §6.2）；
- POST /api/orgs/{org}/semantic/builds：触发构建（m2s-2——semantic:admin；
  入队 semantic_build 任务 {org}，任务行与 semantic.build 触发事件同事务）；
- GET /api/orgs/{org}/semantic/builds：构建列表 + 当前（current=最新 ready）
  ——limit/status 过滤；GET /semantic/builds/{id}：构建明细（manifest/stats）。

权限口径（§6.2 L1143）：查询端点同 `semantic:admin`（org_admin 可见、普通
成员 403——TC-SYNC-08③）。分层纪律：识别面（auto_entities）钉 api/mcp 层；
端点只做协议转换 + 编排调用（core/semantic/{sync,build}）。
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from knowledge_lattice.core.semantic.constants import SYNC_ADAPTERS
from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_BUILD, EVENT_SEMANTIC_SYNC

from .upload import get_auth, get_service, org_scoped

logger = logging.getLogger(__name__)
router = APIRouter()

_BUILD_STATUSES = ("building", "ready", "failed")
_RUN_STATUSES = ("running", "succeeded", "failed", "aborted_guard")


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
    force: bool = False,
    auth=Depends(get_auth),
) -> dict:
    """手动触发同步（semantic:admin + outbox；立返任务标识——TC-SYNC-08①②）。

    force=true（B2 运维放行，T-S2 v1.9.1 口径）：跳过删除比例保护执行同步
    （引用面合法收缩 > 阈值时的运维路径）；guard 告警仍发、run stats 注记
    forced、任务 payload 与 outbox 事件记录 forced。

    P3-7：无注册工厂覆盖时先 resolve_source_config fail-fast——未配置/畸形
    → 400（而非 202 后 worker 侧无声失败）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_admin(service, org, auth)

    from knowledge_lattice.core.semantic.adapters import (
        ADAPTER_FACTORIES,
        SemanticSourceNotConfigured,
        resolve_source_config,
    )

    if adapter not in (*SYNC_ADAPTERS, *ADAPTER_FACTORIES):
        raise HTTPException(
            status_code=404, detail=f"unknown semantic sync adapter: {adapter!r}"
        )
    if adapter not in ADAPTER_FACTORIES:  # 注册工厂覆盖（测试 fake）跳过配置校验
        try:
            resolve_source_config(service.settings, org, adapter)
        except SemanticSourceNotConfigured as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:  # sources JSON 畸形（fail-closed——TC-SYNC-01）
            raise HTTPException(
                status_code=400, detail=f"semantic sources config invalid: {exc}"
            ) from exc

    backend = service.backend
    # G-16 收口（m2s-2）：任务行 + 触发事件同一事务（create_task audit=——
    # m2-2 outbox 先例；旧形态两事务的崩溃丢审计窗口闭合）
    task_id = f"tsk_{uuid.uuid4()}"
    backend.create_task(
        None, task_type="semantic_sync", task_id=task_id,
        payload=json.dumps({"org": org, "adapter": adapter, "force": force}),
        audit=(
            EVENT_SEMANTIC_SYNC,
            json.dumps(
                {"org_id": org, "adapter": adapter, "task_id": task_id,
                 "phase": "triggered", "actor": auth.user_id, "forced": force},
                ensure_ascii=False,
            ),
        ),
    )

    def _kick() -> None:  # inline 同步认领 / subprocess 唤醒字节（M2.1 同款）
        if service.worker is not None:
            service.worker.kick()

    background.add_task(_kick)
    return {"task_id": task_id, "status": "queued", "org": org,
            "adapter": adapter, "forced": force}


@router.get("/api/orgs/{org}/semantic/sync-runs")
async def list_semantic_sync_runs(
    org: str, request: Request, auth=Depends(get_auth),
    limit: int = Query(50, ge=1, le=200),
    adapter: str | None = None,
    status: str | None = None,
) -> dict:
    """同步记录与冲突报告（semantic:admin——TC-SYNC-08③/TC-SYNC-04；
    m2s-2 管理语义：limit 分页 + adapter/status 过滤）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_admin(service, org, auth)
    if status is not None and status not in _RUN_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid status {status!r}（合法值：{list(_RUN_STATUSES)}）",
        )
    return {"runs": service.backend.sem_list_sync_runs(
        org, limit=limit, adapter=adapter, status=status)}


@router.post("/api/orgs/{org}/semantic/builds", status_code=202)
async def trigger_semantic_build(
    org: str, request: Request, background: BackgroundTasks,
    auth=Depends(get_auth),
) -> dict:
    """触发构建（semantic:admin——m2s-2）：入队 semantic_build 任务 {org}
    + kick worker；任务行与 semantic.build 触发事件同事务（G-16 口径）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_admin(service, org, auth)

    backend = service.backend
    task_id = f"tsk_{uuid.uuid4()}"
    backend.create_task(
        None, task_type="semantic_build", task_id=task_id,
        payload=json.dumps({"org": org}),
        audit=(
            EVENT_SEMANTIC_BUILD,
            json.dumps(
                {"org_id": org, "task_id": task_id, "phase": "triggered",
                 "actor": auth.user_id},
                ensure_ascii=False,
            ),
        ),
    )

    def _kick() -> None:
        if service.worker is not None:
            service.worker.kick()

    background.add_task(_kick)
    return {"task_id": task_id, "status": "queued", "org": org}


@router.get("/api/orgs/{org}/semantic/builds")
async def list_semantic_builds(
    org: str, request: Request, auth=Depends(get_auth),
    limit: int = Query(50, ge=1, le=200),
    status: str | None = None,
) -> dict:
    """构建列表 + 当前（semantic:admin——current=最新 ready 行，design §5.8
    原子切换语义；status 过滤/limit 分页为 m2s-2 管理语义）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_admin(service, org, auth)
    if status is not None and status not in _BUILD_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid status {status!r}（合法值：{list(_BUILD_STATUSES)}）",
        )
    return {
        "builds": service.backend.sem_list_builds(org, limit=limit, status=status),
        "current": service.backend.sem_current_build(org),
    }


@router.get("/api/orgs/{org}/semantic/builds/{build_id}")
async def get_semantic_build(
    org: str, build_id: int, request: Request, auth=Depends(get_auth),
) -> dict:
    """构建明细（semantic:admin——stats/manifest 面；未知/他组织 404）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_admin(service, org, auth)
    build = service.backend.sem_get_build(org, build_id)
    if build is None:
        raise HTTPException(
            status_code=404, detail=f"semantic build not found: {build_id}"
        )
    return build
