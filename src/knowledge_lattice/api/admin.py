"""管理端点（design §6.2——M0a 最小集 + M2.4 m2-2 删库收口 + **M2.3 m2-3 管理面**）：

- POST /api/dev/token（`dev_token_router`）：签发开发 JWT——**仅 dev/test 配置注册
  路由，生产 404**（TC-AUTH-01④）；只能给自己签或系统管理员签发（403 语义）；
- GET /api/orgs/{org}/dimensions · /datasets（`router`）：只读清单（页壳上传/检索
  表单所需）——普通组织作用域端点，**不受环境门控**（P2-4）；
- DELETE /api/orgs/{org}/datasets/{id}（M2.4 m2-2——T19 半句收口/TC-OPS-04）：
  **org_admin**；仍有文档 → 409 明确报错（RESTRICT——非裸外键异常）；治理事件
  与删行同事务入 outbox。

m2-3 管理面（§6.2 M2 新增端点——权限按 FR-4 操作矩阵统一 org_admin，重索引/
重嵌入 owner/org_admin 与删除/覆盖同款）：

- PATCH /dimensions/{id}/values/{value_id}：取值停用（dry_run 影响面预估——
  TC-OPS-07①）；
- POST /dimensions/{id}/retire：维度退役（二次确认 + 审计——TC-OPS-07②/T20 半句）；
- PUT /members/{id}/grants：授权全量替换（只替换 local、sync 不动——TC-OPS-08）；
- GET/POST /grants/export · import：CSV 批量（无 org 列 A-12、dry_run 差异预览、
  幂等全量替换——TC-OPS-06）；
- POST /documents/{id}/reindex?embed_model=：手动重索引 / 换模型重嵌入任务投递
  （TC-EMB-06——蓝绿执行体 m2-1 预留分发位，本段接 API 面）；
- GET /embedding-coverage：嵌入覆盖率只读面板（RUNBOOK §1 闭合口径；不做可改
  参数——改模型=走重嵌入流程）；
- GET /audit：审计分级查询（TC-OPS-03——org_admin 本组织全量 / 系统管理员仅
  元数据 / org_admin 查他组织拒绝）；
- GET /stats：运维面板（B4——maintenance stats 含 audit_outbox_trimmed）。
"""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from knowledge_lattice.domain.audit_events import (
    EVENT_DATASET_DELETE,
    EVENT_DIMENSION_RETIRE,
    EVENT_DIMENSION_VALUE_DISABLE,
    EVENT_GRANTS_REPLACE,
)
from knowledge_lattice.domain.auth import AuthContext, check_path_org, issue_dev_jwt
from knowledge_lattice.store.audit_chain import outbox_row_to_event
from knowledge_lattice.store.backend import DatasetNotEmptyError
from knowledge_lattice.store.taskclock import utc_now_ts

from .upload import get_auth, get_service, org_scoped

router = APIRouter()
dev_token_router = APIRouter()  # 仅 dev/test 注册（app.py 门控——生产 404）


def _require_org_admin(service, auth: AuthContext, org: str) -> None:
    """管理面写操作权限（FR-4 操作矩阵——org_admin；沿 delete_dataset 惯例）。"""
    membership = service.backend.read_membership(auth.user_id, org)
    if membership is None or membership["role"] != "org_admin":
        raise HTTPException(status_code=403, detail="org_admin required（FR-4 操作矩阵）")


def _require_owner_or_admin(service, auth: AuthContext, org: str, doc: dict) -> None:
    """文档级治理操作权限（owner/org_admin——与删除/覆盖上传同款）。"""
    if doc["owner_user_id"] == auth.user_id:
        return
    _require_org_admin(service, auth, org)


class DevTokenRequest(BaseModel):
    user_id: str | None = None  # 缺省=给自己签；给他人签须系统管理员
    org: str | None = None  # 嵌入 token 的 org claim（单值——按组织签发）
    act: str | None = None  # 服务身份 claim（M1-3 凭证三要素——委托 token act 开发形态）


@dev_token_router.post("/api/dev/token")
async def issue_dev_token(
    request: Request, auth: AuthContext = Depends(get_auth), body: DevTokenRequest | None = None
) -> dict:
    """开发 JWT 签发（仅 dev/test 注册——路由注册开关在 app.py，D18/TC-AUTH-01）。"""
    body = body or DevTokenRequest()
    target = body.user_id or auth.user_id
    if target != auth.user_id and not auth.is_system_admin:
        raise HTTPException(status_code=403, detail="只能给自己签发；代签须系统管理员")
    service = get_service(request)
    token = issue_dev_jwt(service.settings, user_id=target, org=body.org, act=body.act)
    return {
        "token": token,
        "token_type": "bearer",
        "user_id": target,
        "org": body.org,
        "act": body.act,
    }


@router.get("/api/orgs/{org}/dimensions")
async def list_dimensions(
    org: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    org = org_scoped(request, org, auth)
    return {"dimensions": get_service(request).backend.list_dimensions(org)}


@router.get("/api/orgs/{org}/datasets")
async def list_datasets(
    org: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    org = org_scoped(request, org, auth)
    return {"datasets": get_service(request).backend.list_datasets(org)}


@router.delete("/api/orgs/{org}/datasets/{dataset_id}", status_code=204)
async def delete_dataset(
    org: str, dataset_id: str, request: Request,
    auth: AuthContext = Depends(get_auth),
) -> None:
    """删除知识库（§6.2 服务层流程——T19 半句收口/TC-OPS-04②③）：
    org_admin 权限；仍有文档 → 409 RESTRICT（先删文档再删库）；治理事件
    dataset.delete 与删行同事务入 outbox（M2.4 治理动作全量接入）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    try:
        service.backend.delete_dataset(
            org, dataset_id,
            audit=(EVENT_DATASET_DELETE, json.dumps(
                {"org_id": org, "dataset_id": dataset_id, "actor": auth.user_id},
                ensure_ascii=False,
            )),
        )
    except DatasetNotEmptyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"dataset not found in org: {dataset_id!r}"
        ) from exc


# ============================================================================
# m2-3 管理面（§6.2 M2 新增——TC-OPS-06/07/08、TC-EMB-06、TC-OPS-03、B4）
# ============================================================================


class ValueStatusRequest(BaseModel):
    """取值停用请求（TC-OPS-07①）——status=disabled 带 dry_run 影响面预估。"""

    status: str
    dry_run: bool = False


@router.patch("/api/orgs/{org}/dimensions/{dim_id}/values/{value_id}")
async def patch_dimension_value(
    org: str, dim_id: str, value_id: str, request: Request,
    body: ValueStatusRequest, auth: AuthContext = Depends(get_auth),
) -> dict:
    """取值停用（TC-OPS-07①）：dry_run=只返回影响面预估；确认（不带 dry_run）
    → status=disabled + 审计同事务。**T3 联动**：停用=收紧进计算（read_grants
    既有 v.status='active' 过滤——下一次检索即时生效）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    if body.status != "disabled":
        raise HTTPException(
            status_code=400,
            detail="仅支持 status=disabled（取值停用——D19 软停用=收紧）",
        )
    audit = (EVENT_DIMENSION_VALUE_DISABLE, json.dumps(
        {"org_id": org, "dimension_id": dim_id, "value_id": value_id,
         "actor": auth.user_id, "dry_run": body.dry_run}, ensure_ascii=False))
    result = service.backend.disable_dimension_value(
        org, dim_id, value_id, dry_run=body.dry_run, audit=audit,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"value not found: {value_id!r}")
    return {"impact": {k: v for k, v in result.items() if k != "applied"},
            "applied": result["applied"]}


@router.post("/api/orgs/{org}/dimensions/{dim_id}/retire")
async def retire_dimension(
    org: str, dim_id: str, request: Request,
    confirm: bool = False, auth: AuthContext = Depends(get_auth),
) -> dict:
    """维度退役（TC-OPS-07②——**T20 半句：唯一放宽路径**）。无 confirm 只返回
    影响面预估（二次确认门）；confirm=true → status=retired + 审计同事务；
    已 retired → 409（幂等不重复退役）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    impact = service.backend.dimension_retire_impact(org, dim_id)
    if impact is None:
        raise HTTPException(status_code=404, detail=f"dimension not found: {dim_id!r}")
    if not confirm:
        return {"impact": impact, "confirm_required": True, "applied": False}
    # 已 retired 幂等检查（retire_dimension 本体幂等零审计——409 提示显式）
    if service.backend.get_dimension_status(org, dim_id) == "retired":
        raise HTTPException(status_code=409, detail="dimension already retired")
    result = service.backend.retire_dimension(
        org, dim_id,
        audit=(EVENT_DIMENSION_RETIRE, json.dumps(
            {"org_id": org, "dimension_id": dim_id, "actor": auth.user_id},
            ensure_ascii=False)),
    )
    return {"impact": result, "confirm_required": False, "applied": True}


class GrantsReplaceRequest(BaseModel):
    """授权全量替换请求（TC-OPS-08）——目标全量态（local 授权清单）。"""

    grants: list[dict]  # [{dim_key, value, expires_at?}]


@router.put("/api/orgs/{org}/members/{user_id}/grants")
async def replace_member_grants(
    org: str, user_id: str, request: Request,
    body: GrantsReplaceRequest, auth: AuthContext = Depends(get_auth),
) -> dict:
    """授权全量替换（TC-OPS-08——§6.2 端点语义）：**只替换 local 授权、sync
    不动**；支持行级 expires_at；grants.replace 审计与替换同事务。目标用户无
    有效成员关系 → 400（防孤儿授权）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    if service.backend.read_membership(user_id, org) is None:
        raise HTTPException(
            status_code=400,
            detail=f"目标用户在 {org!r} 无有效成员关系（防孤儿授权）",
        )
    rows = [
        (g["dim_key"], g["value"], g.get("expires_at")) for g in body.grants
    ]
    audit = (EVENT_GRANTS_REPLACE, json.dumps(
        {"org_id": org, "user_id": user_id, "actor": auth.user_id,
         "via": "api", "rows": len(rows)}, ensure_ascii=False))
    try:
        result = service.backend.replace_local_grants(
            org, user_id, rows, audit=audit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


_GRANT_CSV_COLUMNS = ("username", "dim_key", "value", "expires_at")


@router.get("/api/orgs/{org}/grants/export")
async def export_grants(
    org: str, request: Request, auth: AuthContext = Depends(get_auth),
) -> PlainTextResponse:
    """授权导出 CSV（TC-OPS-06——**无 org 列**：A-12 org 一律以路径为准；
    仅 local 授权行；sync 行不导出——导入侧 sync 不动的对称面）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_GRANT_CSV_COLUMNS)
    for row in service.backend.list_grants_for_export(org):
        if row["source"] != "local":
            continue  # sync 授权经同步适配器管理——CSV 面不触碰
        writer.writerow(
            [row["username"], row["dim_key"], row["value"], row["expires_at"] or ""]
        )
    return PlainTextResponse(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="grants-{org}.csv"'},
    )


def _parse_grant_csv(text: str) -> tuple[list[dict], list[str]]:
    """解析导入 CSV：返回 (行集, 错误清单)。**org 列出现（无论与路径一致与否）
    → 整批拒绝**（A-12——CSV 不带 org 列）；缺必需列 → 错误。"""
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    if "org" in fields:
        raise HTTPException(
            status_code=400,
            detail="CSV 含 org 列——整批拒绝（A-12：org 一律以路径为准，"
                   "CSV 不带 org 列）",
        )
    missing = [c for c in _GRANT_CSV_COLUMNS[:3] if c not in fields]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"CSV 缺少必需列: {missing}",
        )
    rows, errors = [], []
    for i, raw in enumerate(reader, start=2):  # 2=数据首行（1 为 header）
        username = (raw.get("username") or "").strip()
        dim_key = (raw.get("dim_key") or "").strip()
        value = (raw.get("value") or "").strip()
        expires_at = (raw.get("expires_at") or "").strip() or None
        if not username or not dim_key or not value:
            errors.append({"line": i, "username": username, "reason": "空字段"})
            continue
        rows.append({"line": i, "username": username, "dim_key": dim_key,
                     "value": value, "expires_at": expires_at})
    return rows, errors


@router.post("/api/orgs/{org}/grants/import")
async def import_grants(
    org: str, request: Request, dry_run: bool = False,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """授权批量导入（TC-OPS-06）：CSV=**目标全量态**（幂等全量替换——二跑零
    差异）；dry_run=差异预览不生效；**sync 维度行不动**（T-CSV 主断言——差异
    计算与替换都只对 local）；目标用户无有效成员关系 → **拒绝该用户行**
    （防孤儿授权，其余用户照常）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    backend = service.backend

    text = (await request.body()).decode("utf-8-sig")
    rows, rejected = _parse_grant_csv(text)

    # 成员关系校验（逐用户——无有效行 → 该用户全部行拒绝）
    username_cache: dict[str, str | None] = {}
    valid_rows = []
    for row in rows:
        username = row["username"]
        if username not in username_cache:
            user = backend.find_user_by_username(username)
            uid = user["id"] if user else None
            if uid is not None and backend.read_membership(uid, org) is None:
                uid = None  # 用户在但无本组织成员关系——防孤儿授权
            username_cache[username] = uid
        if username_cache[username] is None:
            rejected.append({"line": row["line"], "username": username,
                             "reason": "用户不存在或无有效成员关系（防孤儿授权）"})
            continue
        valid_rows.append(row)

    # 差异计算（键=(username, dim_key, value)；值=expires_at）——**按用户全量**
    # 语义：与 PUT /members/{id}/grants（TC-OPS-08）同构，CSV 中出现的用户按其
    # 行集全量替换、**未出现的用户不动**（增量文件安全）；diff 范围限定目标
    # 用户集，仅对 local 授权（sync 不动——T-CSV 主断言）。
    target_users = {row["username"] for row in valid_rows}
    current: dict[tuple[str, str, str], str | None] = {
        (r["username"], r["dim_key"], r["value"]): r["expires_at"]
        for r in backend.list_grants_for_export(org)
        if r["source"] == "local" and r["username"] in target_users
    }
    target: dict[tuple[str, str, str], str | None] = {}
    for row in valid_rows:
        target[(row["username"], row["dim_key"], row["value"])] = row["expires_at"]
    added = sorted(set(target) - set(current))
    removed = sorted(set(current) - set(target))
    changed = sorted(
        k for k in set(target) & set(current) if target[k] != current[k]
    )
    kept = sorted(set(target) & set(current) - set(changed))
    diff = {
        "added": [{"username": k[0], "dim_key": k[1], "value": k[2]} for k in added],
        "removed": [{"username": k[0], "dim_key": k[1], "value": k[2]} for k in removed],
        "changed": [
            {"username": k[0], "dim_key": k[1], "value": k[2],
             "expires_at": target[k]} for k in changed
        ],
        "kept": len(kept),
    }

    if dry_run:
        return {"dry_run": True, "applied": False, "diff": diff,
                "rejected": rejected}

    # 生效：按用户全量替换（含 kept 行重写——幂等；sync 行不动）
    by_user: dict[str, list[dict]] = {}
    for row in valid_rows:
        by_user.setdefault(row["username"], []).append(row)
    applied_users = 0
    for username, user_rows in sorted(by_user.items()):
        uid = username_cache[username]
        audit = (EVENT_GRANTS_REPLACE, json.dumps(
            {"org_id": org, "user_id": uid, "actor": auth.user_id,
             "via": "csv", "rows": len(user_rows)}, ensure_ascii=False))
        try:
            backend.replace_local_grants(
                org, uid,
                [(r["dim_key"], r["value"], r["expires_at"]) for r in user_rows],
                audit=audit,
            )
        except KeyError as exc:
            rejected.append({"username": username, "reason": f"维度/取值不存在: {exc}"})
            continue
        applied_users += 1
    return {
        "dry_run": False, "applied": True,
        "diff": {**diff, "changed": diff["changed"]},
        "applied_users": applied_users, "rejected": rejected,
    }


@router.post("/api/orgs/{org}/documents/{doc_id}/reindex", status_code=202)
async def reindex_document(
    org: str, doc_id: str, request: Request, background: BackgroundTasks,
    embed_model: str | None = None, auth: AuthContext = Depends(get_auth),
) -> JSONResponse:
    """手动重索引 / 换模型重嵌入入口（TC-EMB-06——§6.2 M2）：无 embed_model
    → 投递 `reindex` 任务（重走摄取管线）；携带 embed_model → 投递 `reembed`
    任务（方案二蓝绿——新旧标签并行写、覆盖率 100% 原子切标签；执行体随
    m2-1 预留分发位，任务行与 payload 本段就位）。权限 owner/org_admin。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    doc = service.backend.get_document(doc_id)
    if doc is None or doc["org_id"] != org:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id!r}")
    _require_owner_or_admin(service, auth, org, doc)

    if embed_model:
        task_type = "reembed"
        payload = json.dumps({"org": org, "embed_model": embed_model})
        target_version = None  # 全库任务（不限单版本）
    else:
        task_type = "reindex"
        payload = json.dumps({"org": org})
        target_version = doc["active_version"]
    task_id = service.backend.create_task(
        doc_id, task_type=task_type, target_version=target_version, payload=payload,
    )

    def _kick() -> None:  # 投递 worker（upload.py 同款）
        if service.worker is not None:
            service.worker.kick()

    background.add_task(_kick)
    return JSONResponse(
        {"task_id": task_id, "type": task_type, "doc_id": doc_id,
         "embed_model": embed_model},
        status_code=202,
    )


@router.get("/api/orgs/{org}/embedding-coverage")
async def embedding_coverage(
    org: str, request: Request, auth: AuthContext = Depends(get_auth),
) -> dict:
    """嵌入覆盖率只读面板（design §8 M2.3——**不做可改参数**：改模型=走重嵌入
    流程）。各库覆盖率按 RUNBOOK §1 闭合口径（分子/分母都限在用块：
    tombstone=0 且 version=active_version）；reembed 窗口 done/total 进度取
    全局在用块口径 + 最近 reembed 任务行状态。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    label = service.settings.embed_model_label
    coverage = service.backend.embedding_coverage(org, label)
    total = sum(c["total"] for c in coverage)
    done = sum(c["done"] for c in coverage)
    reembed = None
    for task in service.backend.list_tasks(org):  # 最近一条 reembed 任务行
        if task["type"] == "reembed":
            reembed = {
                "task_id": task["id"], "status": task["status"],
                "error": task["error"],
                "created_at": task["created_at"],
                "done": done, "total": total,  # 进度=全局在用块覆盖率
            }
            break
    return {
        "embed_model": label,
        "dim": service.settings.embed_dim,
        "coverage": coverage,
        "totals": {"done": done, "total": total},
        "reembed": reembed,
    }


@router.get("/api/orgs/{org}/audit")
async def query_audit(
    org: str, request: Request, action: str | None = None, limit: int = 100,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """审计分级查询（TC-OPS-03——FR-6 分级）：

    - 本组织 **org_admin → 全量**（含查询词与命中详情 detail_json）；
    - **系统管理员 → 仅元数据**（detail_json 剥离——查询词与命中详情不含；
      确需内容走审批+临时授权）；
    - org_admin 查他组织 / 普通成员 → 403。

    数据源 = 当月月库（链遍历读序——B2）+ 未搬运 outbox 行（当月事件双源合并）。
    """
    resolved = check_path_org(path_org=org, org_header=request.headers.get("x-org-id"))
    service = get_service(request)
    membership = service.backend.read_membership(auth.user_id, resolved)
    if membership is not None and membership["role"] == "org_admin":
        full = True
    elif auth.is_system_admin:
        full = False  # 系统管理员仅元数据（无本组织 admin 身份时）
    else:
        raise HTTPException(
            status_code=403, detail="audit query requires org_admin (own org) "
            "or system admin (metadata-only)——FR-6 分级",
        )

    rows: list[dict] = [
        outbox_row_to_event(r)  # 未搬运 outbox（投影同搬运侧）
        for r in service.backend.read_pending_outbox_events()
    ]
    rows.extend(service.backend.read_monthly_events(when=utc_now_ts()))
    rows = [r for r in rows if r.get("org_id") == resolved]
    if action:
        rows = [r for r in rows if (r.get("action") or "").startswith(action)]
    rows.sort(key=lambda r: (r.get("created_at") or "", r.get("id") or ""))
    rows = rows[-limit:]
    rows.reverse()  # 最近在前（面板序）

    if full:
        items = rows
    else:
        items = [
            {k: v for k, v in r.items() if k != "detail_json"} for r in rows
        ]
    return {"scope": "full" if full else "metadata", "events": items}


@router.get("/api/orgs/{org}/stats")
async def org_stats(
    org: str, request: Request, auth: AuthContext = Depends(get_auth),
) -> dict:
    """运维面板 stats（m2-3 B4——maintenance 任务族最近一次运行计数；含
    audit_outbox_trimmed 新键：已搬运 outbox 行保留期清理）。只读。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    return {"maintenance": service.backend.read_last_maintenance_stats()}
