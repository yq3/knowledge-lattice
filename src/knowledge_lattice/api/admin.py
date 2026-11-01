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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from knowledge_lattice.domain.audit_events import (
    EVENT_DATASET_DELETE,
    EVENT_DIMENSION_RETIRE,
    EVENT_DIMENSION_VALUE_CREATE,
    EVENT_DIMENSION_VALUE_DISABLE,
    EVENT_DIMENSION_VALUE_ENABLE,
    EVENT_GRANTS_REPLACE,
    EVENT_MEMBER_ADD,
    EVENT_MEMBER_REMOVE,
    EVENT_MEMBER_UPDATE,
)
from knowledge_lattice.domain.auth import AuthContext, check_path_org, issue_dev_jwt
from knowledge_lattice.store.backend import (
    DatasetNotEmptyError,
    DimensionValueExistsError,
    MembershipExistsError,
    MembershipExpiredError,
)
from knowledge_lattice.store.taskclock import TS_FMT, utc_now_ts

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
    """取值状态迁移（TC-OPS-07① + m2-6 A4 D19 恢复路径）：

    - ``status=disabled``（m2-3）：dry_run=只返回影响面预估；确认 → disabled
      + 审计同事务。T3 联动：收紧进计算（read_grants 既有过滤即时生效）；
    - ``status=active``（m2-6 A4——**重新启用**）：D19 恢复路径——文档含已停用
      取值时 PATCH/覆盖上传同锁（v1.6.3 口径），重新启用后解锁
      （locked_docs 判定面自动联动——treating_active 影响面视角）；幂等
      （已 active 零新审计）；审计同事务。
    """
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    if body.status == "disabled":
        audit = (EVENT_DIMENSION_VALUE_DISABLE, json.dumps(
            {"org_id": org, "dimension_id": dim_id, "value_id": value_id,
             "actor": auth.user_id, "dry_run": body.dry_run}, ensure_ascii=False))
        result = service.backend.disable_dimension_value(
            org, dim_id, value_id, dry_run=body.dry_run, audit=audit,
        )
    elif body.status == "active":
        if body.dry_run:
            raise HTTPException(
                status_code=400,
                detail="重新启用不支持 dry_run（enable 是恢复路径——无破坏面）",
            )
        audit = (EVENT_DIMENSION_VALUE_ENABLE, json.dumps(
            {"org_id": org, "dimension_id": dim_id, "value_id": value_id,
             "actor": auth.user_id}, ensure_ascii=False))
        result = service.backend.enable_dimension_value(
            org, dim_id, value_id, audit=audit,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="仅支持 status=disabled（取值停用——D19 软停用=收紧）或"
            " status=active（重新启用——D19 恢复路径）",
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


class GrantRow(BaseModel):
    """单条授权行（TC-OPS-08 PUT / CSV 导入共用形态——R2 P2-1：pydantic 校验
    缺键 422 而非 KeyError 500）。"""

    dim_key: str
    value: str
    expires_at: str | None = None  # 严格校验见 _parse_expires_at（R2 P2-2）


class GrantsReplaceRequest(BaseModel):
    """授权全量替换请求（TC-OPS-08）——目标全量态（local 授权清单）。"""

    grants: list[GrantRow]


@router.put("/api/orgs/{org}/members/{user_id}/grants")
async def replace_member_grants(
    org: str, user_id: str, request: Request,
    body: GrantsReplaceRequest, auth: AuthContext = Depends(get_auth),
) -> dict:
    """授权全量替换（TC-OPS-08——§6.2 端点语义）：**只替换 local 授权、sync
    不动**；支持行级 expires_at；grants.replace 审计与替换同事务。目标用户无
    有效成员关系 → 400（防孤儿授权）。R2 P2-1/P2-2：重复 (dim_key,value) 行
    → 400（先删后插 PK 冲突的 500 根除）；expires_at 严格校验。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    if service.backend.read_membership(user_id, org) is None:
        raise HTTPException(
            status_code=400,
            detail=f"目标用户在 {org!r} 无有效成员关系（防孤儿授权）",
        )
    rows: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for i, g in enumerate(body.grants, start=1):
        key = (g.dim_key.strip(), g.value.strip())
        if key in seen:
            raise HTTPException(
                status_code=400,
                detail=f"grants 第 {i} 行重复: {key[0]}={key[1]}"
                "（先删后插主键冲突——去重后重试）",
            )
        seen.add(key)
        expires_at = _parse_expires_at(
            g.expires_at, where=f"grants 第 {i} 行 expires_at",
        )
        rows.append((key[0], key[1], expires_at))
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

# 库内统一口径（CURRENT_TIMESTAMP 同格式）——m2-6 B⑥：常量收编 store/taskclock
# .TS_FMT（store 侧 strftime 字面量与本处旧 _EXPIRES_LIB_FORMAT 双源消除）
_EXPIRES_LIB_FORMAT = TS_FMT


def _parse_expires_at(raw: str | None, *, where: str) -> str | None:
    """expires_at 严格解析（R2 P2-2——sqlite 静默 fail-open 根除）：归一化核心
    收口 ``store.taskclock.normalize_expires_at``（m2-6 B③——store 直调面同
    一实现）；本薄壳只做 HTTP 400 映射（带 where 定位——行号/字段）。"""
    from knowledge_lattice.store.taskclock import normalize_expires_at

    try:
        return normalize_expires_at(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{exc}（{where}）——须为"
            f" 'YYYY-MM-DD HH:MM:SS' 或 ISO 8601（UTC）",
        ) from exc


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
        # expires_at 已由 store 双方言归一为库格式字符串（R3 P2-1 单点收口）
        writer.writerow(
            [row["username"], row["dim_key"], row["value"], row["expires_at"] or ""]
        )
    return PlainTextResponse(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="grants-{org}.csv"'},
    )


def _parse_grant_csv(text: str) -> tuple[list[dict], list[str]]:
    """解析导入 CSV：返回 (行集, 错误清单)。

    - **org 列出现（无论与路径一致与否）→ 整批拒绝**（A-12——CSV 不带 org 列；
      header 名规范化 lower()+strip——`Org`/` org ` 变体同拒，R2 P3-6）；
    - **重复行检测（R2 P2-1）**：同 (username,dim_key,value) 重复——expires_at
      相同 → 去重（幂等 CSV 单行语义）；不同 → 400 报两行号（显式拒绝优于
      静默 last-wins）；
    - expires_at 严格校验（R2 P2-2——`_parse_expires_at`）；
    - 缺必需列 → 错误。
    """
    reader = csv.DictReader(io.StringIO(text))
    fields = [(f or "").strip().lower() for f in (reader.fieldnames or [])]
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
    seen: dict[tuple[str, str, str], tuple[int, str | None]] = {}  # P2-1
    for i, raw in enumerate(reader, start=2):  # 2=数据首行（1 为 header）
        def _col(name: str) -> str:
            for key, value in raw.items():
                if key is not None and key.strip().lower() == name:
                    return (value or "").strip()
            return ""

        username = _col("username")
        dim_key = _col("dim_key")
        value = _col("value")
        if not username or not dim_key or not value:
            errors.append({"line": i, "username": username, "reason": "空字段"})
            continue
        expires_at = _parse_expires_at(_col("expires_at") or None, where=f"第 {i} 行")
        key = (username, dim_key, value)
        if key in seen:
            prev_line, prev_expires = seen[key]
            if prev_expires != expires_at:
                raise HTTPException(
                    status_code=400,
                    detail=f"CSV 重复行且 expires_at 冲突: 第 {prev_line} 行与"
                    f" 第 {i} 行同为 {username}/{dim_key}={value}"
                    f"（{prev_expires!r} ≠ {expires_at!r}）——显式二选一后重导",
                )
            continue  # 同值重复：去重（幂等）
        seen[key] = (i, expires_at)
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

    try:
        text = (await request.body()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:  # R2 P3-7：非 UTF-8 → 400 非 500
        raise HTTPException(
            status_code=400,
            detail=f"CSV 须为 UTF-8 编码（UnicodeDecodeError: {exc}）",
        ) from exc
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
    # m2-6：label 读 embedder（检索谓词源——reembed 蓝绿切换后与检索同刻切换；
    # settings 容器字段在 subprocess 部署形态由运维 env 重启收敛，embedder 优先
    # 保证面板与向量路一致）
    label = service.embedder.model_label if service.embedder is not None \
        else service.settings.embed_model_label
    coverage = service.backend.embedding_coverage(org, label)
    total = sum(c["total"] for c in coverage)
    done = sum(c["done"] for c in coverage)
    reembed = None
    for task in service.backend.list_tasks(org):  # 最近一条 reembed 任务行
        if task["type"] != "reembed":
            continue
        # R2 P2-3：窗口进度按**任务目标标签**（payload.embed_model）算——
        # 蓝绿窗口旧（当前）标签覆盖率通常 100%，不得冒充迁移进度；执行体
        # 未认领起步时目标标签零向量 → done=0（真实进度）。
        full = service.backend.get_task(task["id"]) or {}
        target_model = None
        try:
            payload = json.loads(full.get("payload") or "{}")
            if isinstance(payload, dict):
                target_model = payload.get("embed_model")
        except (ValueError, TypeError):
            payload = {}
        r_done = r_total = 0
        if target_model:
            rows = service.backend.embedding_coverage(org, target_model)
            r_total = sum(c["total"] for c in rows)
            r_done = sum(c["done"] for c in rows)
        reembed = {
            "task_id": task["id"], "status": task["status"],
            "error": task["error"],
            "created_at": task["created_at"],
            "target_model": target_model,
            "done": r_done, "total": r_total,
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
    org: str, request: Request, action: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """审计分级查询（TC-OPS-03——FR-6 分级）：

    - 本组织 **org_admin → 全量**（含查询词与命中详情 detail_json）；
    - **系统管理员 → 仅元数据**（detail_json 剥离——查询词与命中详情不含；
      确需内容走审批+临时授权）；
    - org_admin 查他组织 / 普通成员 → 403。

    数据源 = 当月月库（链遍历读序——B2）+ 未搬运 outbox 行（当月事件双源
    合并，**按 id 去重、月库优先**——R2 P3-2：sqlite 两步搬运崩溃窗形态下
    同一事件不重复出现）。
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

    # 读路径下沉 store（m2-6 B④——双源合并/去重/过滤/排序双方言收口
    # read_org_audit；B5 注记见其 docstring：读回行 row_hash 不自洽勿复算链）
    rows = service.backend.read_org_audit(
        resolved, action=action, limit=limit, now=utc_now_ts(),
    )
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


# ============================================================================
# m2-6 A3：members 增/改/删（m2-4 N-1 用户裁定选 a——JIT 建档后 API 面开通闭环，
#          D16「管理员不建账号只配授权」；形态按 design §5.6 授权维护闭环 +
#          trg_membership_no_extend〔T23〕约束设计——择型申报见检查点）
# ============================================================================


class MemberAddRequest(BaseModel):
    """加成员请求（POST /members）：user_id 须为既有用户（JIT 建档或其他途径
    ——管理员不建账号，D16）。"""

    user_id: str
    role: str = "member"
    expires_at: str | None = None


class MemberPatchRequest(BaseModel):
    """成员关系更新请求（PATCH）：role/expires_at 均可选——只动出现的字段
    （expires_at 键**显式出现**〔含 null〕= 改永不过期；键缺失 = 不变——
    pydantic v2 model_fields_set 检测；软停用=置过去/指定时点，零新列择型）。"""

    model_config = {"extra": "forbid"}

    role: str | None = None
    expires_at: str | None = None


def _audit_payload(event_type: str, payload: dict) -> tuple[str, str]:
    return event_type, json.dumps(payload, ensure_ascii=False)


def _last_admin_guard(service, org: str, target_user: str, *, after: dict) -> None:
    """唯一 active org_admin 自锁守卫（择型申报）：目标当前是 active org_admin
    且本次操作后其 admin 身份终结（移出/停用/降级——after 以「操作后」字段覆盖
    当前值），而组织再无其他 active org_admin → 409（防自锁——系统管理员可
    救，API 面先拦）。"""
    membership = service.backend.read_membership(target_user, org)
    if membership is None or membership["role"] != "org_admin":
        return  # 非 active admin——不受守卫
    after_role = after.get("role", "org_admin")
    after_expires = after.get("expires_at", membership["expires_at"])
    from knowledge_lattice.store.taskclock import utc_now_ts

    still_admin = (
        after_role == "org_admin"
        and (after_expires is None or after_expires > utc_now_ts())
    )
    if not still_admin and service.backend.count_active_org_admins(org) <= 1:
        raise HTTPException(
            status_code=409,
            detail=f"组织 {org!r} 最后一名 active org_admin 不得自锁"
            "（移出/停用/降级被拒——先指定继任管理员）",
        )


@router.post("/api/orgs/{org}/members", status_code=201)
async def add_member(
    org: str, request: Request, body: MemberAddRequest,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """加成员（A3——JIT 用户入组 API 面）：用户不存在 404（管理员不建账号，
    D16——建档走 SSO JIT）；已存在成员关系（含过期行）409（过期行恢复 =
    DELETE 后重加 + PUT grants 补授权——T23 先例三步）。审计同事务。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    if body.role not in ("member", "org_admin"):
        raise HTTPException(
            status_code=400, detail=f"invalid role: {body.role!r}（member | org_admin）",
        )
    expires_at = _parse_expires_at(body.expires_at, where="members expires_at")
    try:
        return service.backend.add_membership(
            org, body.user_id, role=body.role, expires_at=expires_at,
            audit=_audit_payload(EVENT_MEMBER_ADD, {
                "org_id": org, "user_id": body.user_id, "actor": auth.user_id,
                "role": body.role, "expires_at": expires_at,
            }),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"用户不存在: {body.user_id!r}（管理员不建账号——建档走 SSO"
            " JIT，D16）",
        ) from exc
    except MembershipExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/api/orgs/{org}/members/{user_id}")
async def patch_member(
    org: str, user_id: str, request: Request, body: MemberPatchRequest,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """成员关系更新（A3——角色变更/软停用/续期）：不存在 404；**已过期行 409**
    （T23 续期禁令——删行重加是唯一恢复路径）；唯一管理员自锁 409（守卫）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    if body.role is not None and body.role not in ("member", "org_admin"):
        raise HTTPException(
            status_code=400, detail=f"invalid role: {body.role!r}（member | org_admin）",
        )
    expires_at = ...  # Ellipsis 哨兵 = 不变（store 协议）
    if "expires_at" in body.model_fields_set:  # 键显式出现（含 null=改永久）
        expires_at = _parse_expires_at(body.expires_at, where="members expires_at")
    # 守卫的 after 视角：本次显式变更字段的操作后值（缺省=维持当前）
    after: dict = {}
    if body.role is not None:
        after["role"] = body.role
    if expires_at is not ...:
        after["expires_at"] = expires_at
    _last_admin_guard(service, org, user_id, after=after)
    try:
        updated = service.backend.update_membership(
            org, user_id, role=body.role, expires_at=expires_at,
            audit=_audit_payload(EVENT_MEMBER_UPDATE, {
                "org_id": org, "user_id": user_id, "actor": auth.user_id,
                "role": body.role, "expires_at":
                    None if expires_at is ... else expires_at,
            }),
        )
    except MembershipExpiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(
            status_code=404, detail=f"membership not found: {user_id!r} in {org!r}",
        )
    return updated


@router.delete("/api/orgs/{org}/members/{user_id}", status_code=204)
async def remove_member(
    org: str, user_id: str, request: Request,
    auth: AuthContext = Depends(get_auth),
) -> None:
    """移出成员（A3）：级联清本组织授权（trg_membership_delete_cleanup——
    T23 不破坏）；不存在 404；唯一管理员自删 409（守卫）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    _last_admin_guard(service, org, user_id, after={"role": None})
    deleted = service.backend.delete_membership(
        org, user_id,
        audit=_audit_payload(EVENT_MEMBER_REMOVE, {
            "org_id": org, "user_id": user_id, "actor": auth.user_id,
        }),
    )
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"membership not found: {user_id!r} in {org!r}",
        )


# ============================================================================
# m2-6 A4：values CRUD（新增 + D19 重新启用恢复路径——m2-3 已交付停用）
# ============================================================================


class ValueCreateRequest(BaseModel):
    """新增维度取值请求（POST /dimensions/{id}/values）。"""

    value: str
    label: str | None = None


@router.post(
    "/api/orgs/{org}/dimensions/{dim_id}/values", status_code=201,
)
async def create_dimension_value(
    org: str, dim_id: str, request: Request, body: ValueCreateRequest,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """新增维度取值（A4）：维度 retired 409（退役不扩值——T20 二次确认语义
    的对称面）；(dimension, value) 重复 409；审计同事务。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    value = (body.value or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="value 不得为空")
    try:
        created = service.backend.create_dimension_value(
            org, dim_id, value,
            audit=_audit_payload(EVENT_DIMENSION_VALUE_CREATE, {
                "org_id": org, "dimension_id": dim_id, "value": value,
                "actor": auth.user_id,
            }),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DimensionValueExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if created is None:
        raise HTTPException(
            status_code=404, detail=f"dimension not found: {dim_id!r}",
        )
    return created
