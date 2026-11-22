"""文档管理端点（design §6.2——M1-2 最小管理面：详情 / PATCH 维度 / DELETE；
m3-1 D 组：be-① 文档列表 + be-② 可见性解释〔issue #20 契约冻结评论〕）。

- GET /documents/{id}：在用/处理中双态四字段（M0a 已有——active/pending ×
  version/status/error，P0-2.2）；
- PATCH /documents/{id}/dimensions（§6.2）：修改维度——pending 期间 409
  （P0-2.1）；新旧取值均在操作者授权内（403，#31 P1-1/TC-AZ-01）；直接写
  document_dimensions（D6 刷维度不重嵌——dims_json 投影已随拍板①删除）；
- DELETE /documents/{id}：owner/org_admin；取消其任务（级联删——T19①/TC-VER-07）；
- GET /documents（m3-1 D-①）：文档列表——org_admin=本组织全量（visible 按行
  回填）/ member=ACL 过滤后仅可见行（visible 恒 true）；分页 limit/offset +
  dataset 过滤 + quality_open；
- GET /documents/{id}/explain（m3-1 D-②）：可见性解释——**只解释不裁定**
  （检索路仍以 ACL 编译产物为唯一权威；explain 结论与编译产物同口径）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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


# ============================================================================
# m3-1 D 组（issue #20 be-①②——契约冻结评论 issuecomment-6649900631）
# ============================================================================


def _doc_row_out(row: dict, *, visible: bool) -> dict:
    """D-① 契约行投影：store 行（dataset_id 等）→ 契约字段名（dataset——与
    单文档 GET 同构）；dims 由 store _attach_dims 已回填。"""
    return {
        "doc_id": row["doc_id"],
        "title": row["title"],
        "dataset": row["dataset_id"],
        "dims": row.get("dims") or {},
        "active_version": row["active_version"],
        "active_status": row["active_status"],
        "active_error": row["active_error"],
        "pending_version": row["pending_version"],
        "pending_status": row["pending_status"],
        "chunk_count": row["chunk_count"],
        "quality_open": row["quality_open"],
        "updated_at": row["updated_at"],
        "visible": visible,
    }


@router.get("/api/orgs/{org}/documents")
async def list_documents(
    org: str, request: Request,
    dataset: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """文档列表（m3-1 D-①——issue #20 be-① 契约冻结）：

    - **org_admin = 本组织全量**（不过 ACL；visible 按行回填——以调用者本人
      ACL 编译产物为判据，管理面对账用：哪行对「自己」可见）；
    - **member = 服务端 ACL 过滤后仅可见行**（visible_docs CTE——与检索路
      同一编译产物；visible 恒 true）；
    - 行集含 pending 处理中文档（双态字段与单文档 GET 同构）；chunk_count=
      在用块计数；quality_open=open 态 flag 计数；dims 与检索路同源
      （document_dimensions——D22 _attach_dims 同源聚合）；
    - 排序 updated_at DESC（NULLS LAST + id 稳定序）；dataset 单库过滤；
    - 跨组织/停用组织 404·403 语义与既有端点一致（org_scoped 承载）。
    """
    org = org_scoped(request, org, auth)
    service = get_service(request)
    backend = service.backend
    from knowledge_lattice.core.docs.acl import compile_acl

    membership = backend.read_membership(auth.user_id, org)
    is_admin = membership is not None and membership["role"] == "org_admin"
    dataset_ids = [dataset] if dataset is not None else None
    if is_admin:
        rows, total = backend.list_org_documents(
            org, dataset_id=dataset, limit=limit, offset=offset,
        )
        # visible 按行回填：调用者本人 ACL 编译产物（管理面对账——哪些行
        # 过权限规则可见；admin 无维度授权时带值文档 False、空值文档 True）
        plan = compile_acl(backend, auth.user_id, org)
        visible_set = backend.visible_doc_ids(plan, [r["doc_id"] for r in rows])
        docs = [_doc_row_out(r, visible=r["doc_id"] in visible_set) for r in rows]
    else:
        rows, total = backend.visible_documents_page(
            compile_acl(backend, auth.user_id, org),
            dataset_ids=dataset_ids, limit=limit, offset=offset,
        )
        docs = [_doc_row_out(r, visible=True) for r in rows]
    return {"documents": docs, "total": total}


@router.get("/api/orgs/{org}/documents/{doc_id}/explain")
async def explain_document_visibility(
    org: str, doc_id: str, request: Request, user_id: str | None = None,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """可见性解释（m3-1 D-②——issue #20 be-② 契约冻结；**只解释不裁定**：
    检索路仍以 ACL 编译产物为唯一权威，explain 不进检索路径）。

    - user_id 缺省 = 解释自己（本人可见/不可见均可解释——不泄露他人面）；
      给他人解释须 org_admin（否则 403）；文档不在本组织 404；
    - 行序：membership（第 0 步——无行/过期即 deny 收口）→ 逐 active 维度
      （按 key 序）：文档有值→与有效授权求交（交集 allow / 无交集 deny /
      授权已过期 detail 注明等效无授权）；文档空值→skip 放行；retired 维度
      不出现；
    - visible = 无 deny 行；结论与 ACL 编译产物同口径（矩阵级漂移断言见
      test_docs_explain_m31）。
    """
    from knowledge_lattice.store.taskclock import utc_now_ts

    org = org_scoped(request, org, auth)
    service = get_service(request)
    backend = service.backend
    target = user_id
    if target is not None and target != auth.user_id:
        # 给他人解释须 org_admin（403——不泄露他人面）
        _require_org_admin_local(service, auth, org)
    if target is None:
        target = auth.user_id
    doc = backend.get_document(doc_id)
    if doc is None or doc["org_id"] != org:
        raise HTTPException(status_code=404, detail="document not found")

    rows: list[dict] = []
    # ---- 第 0 步：membership（deny 收口） ----
    now = utc_now_ts()
    m = backend.read_membership_row(target, org)
    if m is None:
        rows.append({
            "kind": "membership", "key": None, "label": org, "verdict": "deny",
            "detail": "无成员关系（访问被拒——第 0 步收口）",
        })
        membership_ok = False
    elif m["expires_at"] is not None and str(m["expires_at"]) <= now:
        rows.append({
            "kind": "membership", "key": None, "label": org, "verdict": "deny",
            "detail": f"成员关系已过期（expires_at={m['expires_at']}——过期即"
            "收口，不等清理任务）",
        })
        membership_ok = False
    else:
        expires = "永不过期" if m["expires_at"] is None else \
            f"expires_at={m['expires_at']}"
        rows.append({
            "kind": "membership", "key": None, "label": org, "verdict": "allow",
            "detail": f"role={m['role']}，{expires}",
        })
        membership_ok = True

    # ---- 逐 active 维度（按 key 序——与编译产物规则序一致） ----
    dims_doc = backend.get_document_dims(doc_id)
    grants = backend.read_grants(target, org) if membership_ok else {}
    raw_rows = backend.read_grant_rows(target, org)
    expired_by_key: dict[str, list[str]] = {}
    for g in raw_rows:
        if g["expires_at"] is not None and str(g["expires_at"]) <= now:
            expired_by_key.setdefault(g["key"], []).append(
                f"{g['value']}（过期于 {g['expires_at']}）"
            )
    for dim in backend.list_dimensions(org):  # 仅 active 维度（retired 不出现）
        key, label = dim["key"], dim["name"]
        doc_values = set(dims_doc.get(key) or ())
        if not doc_values:
            rows.append({
                "kind": "dimension", "key": key, "label": label,
                "verdict": "skip",
                "detail": "文档无值——空值放行（§5.1 统一模板）",
            })
            continue
        if not membership_ok:
            # 边界①（用户裁定选 A——m3-2）：membership deny 时保持维度行展开
            # （管理面对账信息），但 detail 不得声称「有效授权 []」（成员过期
            # 不清理授权行，空集是收口结果非事实授权面）——改参考口径
            rows.append({
                "kind": "dimension", "key": key, "label": label,
                "verdict": "deny",
                "detail": "成员关系无效，维度行仅供参考",
            })
            continue
        effective = set(grants.get(key) or ())
        inter = doc_values & effective
        if inter:
            rows.append({
                "kind": "dimension", "key": key, "label": label,
                "verdict": "allow",
                "detail": f"交集: {sorted(inter)}（有效授权 "
                f"{sorted(effective)} ∩ 文档值 {sorted(doc_values)}）",
            })
        else:
            expired_hits = sorted(
                v for v in expired_by_key.get(key, [])
                if any(v.startswith(f"{dv}（") for dv in doc_values)
            )
            if expired_hits:
                detail = (
                    "授权已过期（等效无授权）：" + "、".join(expired_hits)
                    + "——权限计算过滤过期（T1），恢复走重新授予"
                )
            else:
                detail = (
                    f"无交集授权（有效授权 {sorted(effective)} ∩ 文档值 "
                    f"{sorted(doc_values)} = ∅）"
                )
            rows.append({
                "kind": "dimension", "key": key, "label": label,
                "verdict": "deny", "detail": detail,
            })

    visible = all(r["verdict"] != "deny" for r in rows)
    return {"doc_id": doc_id, "visible": visible, "rows": rows}


def _require_org_admin_local(service, auth: AuthContext, org: str) -> None:
    """org_admin 门控（admin._require_org_admin 同款——本模块内联避免跨模块
    私有导入）。"""
    membership = service.backend.read_membership(auth.user_id, org)
    if membership is None or membership["role"] != "org_admin":
        raise HTTPException(
            status_code=403,
            detail="给他人解释须 org_admin（user_id 缺省=解释自己——D-② 契约）",
        )
