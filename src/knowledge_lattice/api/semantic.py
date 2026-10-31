"""语义层端点（design §6.2 L1136-1143——M2-S1 管理面、m2s-2 构建面、
m2s-3 读端点 + YAML webhook）：

- POST /api/orgs/{org}/semantic/sync/{adapter}：手动触发同步——**semantic:admin**
  （org_admin 兼任，§6.3——普通成员 403）；入队 semantic_sync 任务（payload
  {org, adapter, force}）+ kick worker + outbox 留痕（TC-SYNC-08①②）；
  `?force=true` = B2 运维放行（跳过删除比例保护——T-S2 v1.9.1）；
  无工厂覆盖时 resolve_source_config fail-fast（P3-7——未配置/畸形 400）；
  **G-16 收口（m2s-2）**：任务行与触发事件经 create_task(audit=) **同一事务**；
- GET /api/orgs/{org}/semantic/sync-runs：同步记录与冲突报告（stats_json 内含
  conflicts 明细——TC-SYNC-04；curated 合并面 stats.curated 同 run 可查——
  m2s-3）；m2s-2 管理语义：limit 分页 + adapter/status 过滤（design §6.2）；
- POST /api/orgs/{org}/semantic/builds：触发构建（m2s-2——semantic:admin；
  入队 semantic_build 任务 {org}，任务行与 semantic.build 触发事件同事务）；
- GET /api/orgs/{org}/semantic/builds：构建列表 + 当前（current=最新 ready）
  ——limit/status 过滤；GET /semantic/builds/{id}：构建明细（manifest/stats）。

读端点（m2s-3——v1.9.5 拍板⑤；semantic:read = 组织成员默认具备，§6.3 权限
口径①②——无成员关系 403）：

- GET /api/orgs/{org}/semantic/entities?q=&types=&top_k=：实体检索，同 MCP
  `search_entities`（design §6.2 L1137）；
- GET /api/orgs/{org}/semantic/entities/{id}?expand=&depth=：实体详情与关系
  展开，同 `get_entity`（L1138）；
- GET /api/orgs/{org}/semantic/tables/{key}/describe?columns=：表/列详情透传，
  同 `describe_table`（L1139——仅已登记 table，未登记 403 防枚举）。

m2s-4 识别与报告面：

- POST /api/orgs/{org}/semantic/annotate：术语识别（semantic:read——同 MCP
  `annotate`，L1136；≤4000 字/context_entities≤20——TC-SEM-07）；
- GET /api/orgs/{org}/semantic/l0：L0 核心术语片段导出（semantic:read——
  TC-SEM-06：片段 + dict_rev）；
- GET /api/orgs/{org}/semantic/builds/{id}/report：构建报告（semantic:admin
  ——A4：计数/自动机规模与耗时/dict_rev 分量/缺源警告/冲突/评测指标）。

YAML webhook（design §6.2 L1142——TC-YAML-03；m2s-3）：

- POST /api/orgs/{org}/semantic/yaml/webhook：Git 合并回调——**签名 = 服务
  身份**（X-Lattice-Signature: sha256=HMAC-SHA256(body)），无/错签名一律 401；
  **不接受用户 Bearer 替代**（Git 回调入口仅服务身份——TC-YAML-03③）；
  验签通过 → 入队 semantic_sync {adapter: yaml}（yaml 合并 + 构建联动 §5.8）
  + semantic.yaml_merge 触发事件（create_task audit= 同事务——G-16 口径）；
  **凭证明文不落日志**（secret/签名串只参与常量时间比对，日志零出现）。

权限口径（§6.2 L1143）：管理面同 `semantic:admin`（org_admin 可见、普通
成员 403——TC-SYNC-08③）。分层纪律：识别面（auto_entities）钉 api/mcp 层；
端点只做协议转换 + 编排调用（core/semantic/{lookup,expand,sync,build}）。
"""

from __future__ import annotations

import asyncio
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


# ---- m2s-3 读端点（semantic:read——组织成员默认具备，§6.3 权限口径①②） ----


def _require_semantic_read(service, org: str, auth) -> None:
    """semantic:read 门控（组织成员默认具备——无成员关系 403；语义层不复用
    维度 ACL 编译器——§6.3 权限口径②）。"""
    if service.backend.read_membership(auth.user_id, org) is None:
        raise HTTPException(
            status_code=403,
            detail="semantic:read 需组织成员（no active membership:"
                   f" user={auth.user_id!r} org={org!r}）",
        )


@router.post("/api/orgs/{org}/semantic/annotate")
async def semantic_annotate(
    org: str, request: Request, auth=Depends(get_auth),
) -> dict:
    """术语识别（semantic:read——同 MCP annotate；design §6.2 L1136/§6.3）。

    body：{text, context_entities?≤20, prefer_types?}；text ≤4000 字（超长
    400——不静默截断，附录 A-10）。AC 四步消歧 + L0 片段兜底；restricted
    实体表现为不存在（T-S9 annotate 侧）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_read(service, org, auth)

    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body 须为 JSON 对象")
    text = body.get("text")
    if not isinstance(text, str):
        raise HTTPException(status_code=400, detail="text 必填（字符串）")
    ctx = body.get("context_entities")
    prefer = body.get("prefer_types")
    for name, val in (("context_entities", ctx), ("prefer_types", prefer)):
        if val is not None and not isinstance(val, list):
            raise HTTPException(status_code=400,
                                detail=f"{name} 须为数组")

    from knowledge_lattice.core.semantic.annotator import annotate_text

    def _run():
        return annotate_text(service.backend, service.settings, org, text,
                             context_entities=ctx, prefer_types=prefer)

    try:
        return await asyncio.to_thread(_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/orgs/{org}/semantic/l0")
async def semantic_l0_export(
    org: str, request: Request, auth=Depends(get_auth),
) -> dict:
    """L0 核心术语片段导出（semantic:read——TC-SEM-06：l0:true 条目渲染
    markdown + dict_rev；预算超限由 CI 拦截——此处只导出）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_read(service, org, auth)

    from knowledge_lattice.core.semantic.annotator import render_l0

    def _run():
        current = service.backend.sem_current_build(org)
        l0 = render_l0(service.backend.sem_active_snapshot(org))
        return {"dict_rev": current["dict_rev"] if current else None, **l0}

    return await asyncio.to_thread(_run)


@router.get("/api/orgs/{org}/semantic/builds/{build_id}/report")
async def get_semantic_build_report(
    org: str, build_id: int, request: Request, auth=Depends(get_auth),
) -> dict:
    """构建报告（semantic:admin——A4：计数/自动机规模与耗时/dict_rev 分量/
    缺源警告/冲突面/评测指标；未知/他组织 404）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_admin(service, org, auth)

    from knowledge_lattice.core.semantic.build import build_report

    report = await asyncio.to_thread(
        build_report, service.backend, org, build_id)
    if report is None:
        raise HTTPException(
            status_code=404, detail=f"semantic build not found: {build_id}"
        )
    return report


@router.get("/api/orgs/{org}/semantic/entities")
async def list_semantic_entities(
    org: str, request: Request, auth=Depends(get_auth),
    q: str = Query(..., min_length=1), types: list[str] = Query(None),
    top_k: int = Query(10, ge=1, le=50),
) -> dict:
    """实体检索（semantic:read——同 MCP search_entities；design §6.2 L1137）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_read(service, org, auth)
    from knowledge_lattice.core.semantic.lookup import search_entities

    try:
        return search_entities(service.backend, org, q, types=types, top_k=top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/orgs/{org}/semantic/entities/{entity_id}")
async def get_semantic_entity(
    org: str, entity_id: int, request: Request, auth=Depends(get_auth),
    expand: list[str] = Query(None), depth: int = Query(1),
    fanout_limit: int = Query(50), include: list[str] = Query(None),
) -> dict:
    """实体详情与关系展开（semantic:read——同 MCP get_entity；L1138；
    不存在/他组织/restricted/非 active 一律 404——存在性零泄露 T-S7/T-S9；
    参数越界经 core 校验 → 400——与 MCP 口径一致）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_read(service, org, auth)
    from knowledge_lattice.core.semantic.expand import EntityNotFound, get_entity

    try:
        return await asyncio.to_thread(
            get_entity, service.backend, org, entity_id=entity_id,
            expand=expand, depth=depth, fanout_limit=fanout_limit,
            include=include,
        )
    except EntityNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/orgs/{org}/semantic/tables/{table_key}/describe")
async def describe_semantic_table(
    org: str, table_key: str, request: Request, auth=Depends(get_auth),
    columns: list[str] = Query(None),
) -> dict:
    """表/列详情透传（semantic:read——同 MCP describe_table；L1139；仅已登记
    table 实体——未登记 403 防借此枚举数仓，T-S11②）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_semantic_read(service, org, auth)
    from knowledge_lattice.core.semantic.lookup import (
        DescribeTableDenied, describe_table,
    )

    try:
        return await asyncio.to_thread(
            describe_table, service.backend, service.settings, org, table_key,
            columns=columns,
        )
    except DescribeTableDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


# ---- m2s-3 YAML webhook（design §6.2 L1142——TC-YAML-03） ----


@router.post("/api/orgs/{org}/semantic/yaml/webhook", status_code=202)
async def semantic_yaml_webhook(
    org: str, request: Request, background: BackgroundTasks,
) -> dict:
    """Git 合并回调（TC-YAML-03）：签名=服务身份（HMAC-SHA256 over raw body，
    per-org secret 随 yaml 源配置）；验签通过 → 投递 yaml 合并（semantic_sync
    {adapter: yaml}）+ semantic.yaml_merge 事件（同事务）；无/错签名 401——
    用户 Bearer 不替代服务身份。凭证明文不落日志（常量时间比对、日志零出现）。"""
    from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_YAML_MERGE
    from knowledge_lattice.domain.auth import OrgContextError, check_path_org

    try:
        org = check_path_org(
            path_org=org, org_header=request.headers.get("x-org-id"))
    except OrgContextError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service = get_service(request)
    secret = _yaml_webhook_secret(service.settings, org)
    body = await request.body()
    signature = request.headers.get("x-lattice-signature", "")
    if not _signature_ok(secret, body, signature):
        # 不回显签名/secret（凭证明文不落日志）；请求体细节亦不落
        logger.warning(
            "semantic yaml webhook rejected: org=%s (invalid or missing signature)"
            "——Git 回调入口仅服务身份（TC-YAML-03②③）", org,
        )
        raise HTTPException(
            status_code=401,
            detail="webhook signature invalid（X-Lattice-Signature: "
                   "sha256=HMAC-SHA256(body)——服务身份校验失败）",
        )

    try:
        payload = json.loads(body) if body else {}
    except ValueError:
        payload = {}
    commit = payload.get("commit") or payload.get("after")

    backend = service.backend
    task_id = f"tsk_{uuid.uuid4()}"
    backend.create_task(
        None, task_type="semantic_sync", task_id=task_id,
        payload=json.dumps({"org": org, "adapter": "yaml"}),
        audit=(
            EVENT_SEMANTIC_YAML_MERGE,
            json.dumps(
                {"org_id": org, "task_id": task_id, "phase": "triggered",
                 "commit": commit},
                ensure_ascii=False, default=str,
            ),
        ),
    )

    def _kick() -> None:
        if service.worker is not None:
            service.worker.kick()

    background.add_task(_kick)
    return {"task_id": task_id, "status": "queued", "org": org,
            "adapter": "yaml"}


def _yaml_webhook_secret(settings, org: str) -> str | None:
    """per-org webhook secret（semantic_sources[org][yaml][webhook_secret]）。"""
    org_conf = settings.semantic_sources.get(org) or {}
    raw = org_conf.get("yaml") or {}
    secret = raw.get("webhook_secret")
    return str(secret) if secret else None


def _signature_ok(secret: str | None, body: bytes, header_value: str) -> bool:
    """sha256=hex HMAC 常量时间比对（secret 为 None 即未配置——一律拒绝：
    fail-closed，不落凭据细节）。"""
    import hashlib
    import hmac as _hmac

    if not secret:
        return False
    expected_prefix = "sha256="
    if not header_value.startswith(expected_prefix):
        return False
    expected = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return _hmac.compare_digest(
        header_value[len(expected_prefix):], expected)
