"""质量环端点（design §6.2——M1-4 区分度反馈环 REST 面）。

- GET /api/orgs/{org}/documents/{doc_id}/quality：质量报告明细——**近邻内容过
  请求者同一套 ACL**（T18/TC-QUAL-05：不可见近邻不出现在响应；detail_json 原始
  存储不改写）；可见性：owner / org_admin / 或经维度 ACL 可见该文档。
- PATCH /api/quality-flags/{id}（§6.2 line 1129）：人工补标 keywords/tags（写
  chunks 人工列——**原样写入不进 jieba**，TC-FTS-04）+ state 迁移
  （open|resolved|ignored——resolved/ignored 落 resolved_at）；权限 owner/org_admin；
  管理写入 outbox 审计。
- GET /api/quality-flags/sample?n=&seed=：误报抽查抽样（M1.7 记录形态——确定性
  抽样 open flags 供人工复核；复核结论经 PATCH 落 state + manual_tags 轨迹）。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from knowledge_lattice.domain.auth import AuthContext

from .upload import get_auth, get_service, org_scoped, resolve_request_org

router = APIRouter()


def _quality(request: Request):
    service = get_service(request)
    quality = getattr(service, "quality", None)
    if quality is None:  # 防御：服务未装配（理论不可达——create_app 必配）
        raise HTTPException(status_code=503, detail="quality service unavailable")
    return quality


@router.get("/api/orgs/{org}/documents/{doc_id}/quality")
async def document_quality_report(
    org: str, doc_id: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    """质量报告明细（近邻展示过 ACL——§6.2 line 1128 / TC-QUAL-05）。"""
    org = org_scoped(request, org, auth)
    service = get_service(request)
    quality = _quality(request)
    doc = service.backend.get_document(doc_id)
    if doc is None or doc["org_id"] != org:
        raise HTTPException(status_code=404, detail="document not found")
    # 可见性：owner / org_admin / 维度 ACL 可见（管理面列表与检索口径一致——FR-4）
    if doc["owner_user_id"] != auth.user_id:
        membership = service.backend.read_membership(auth.user_id, org)
        if membership is None or membership["role"] != "org_admin":
            from knowledge_lattice.core.docs.acl import compile_acl

            plan = compile_acl(service.backend, auth.user_id, org)
            visible = service.backend.visible_doc_ids(plan, [doc_id])
            if not visible:
                raise HTTPException(status_code=404, detail="document not found")
    # 近邻过滤在服务内经同一编译器 + visible_chunk_ids（T18 防旁路）
    return quality.quality_report(doc_id, user_id=auth.user_id, org_id=org)


class QualityFlagPatchBody(BaseModel):
    """PATCH 体：keywords/tags=人工词（空格分隔，原样写入不进 jieba——TC-FTS-04）；
    state=open|resolved|ignored。"""

    keywords: str | None = None
    tags: str | None = None
    state: Literal["open", "resolved", "ignored"] | None = None


@router.patch("/api/quality-flags/{flag_id}")
async def patch_quality_flag(
    flag_id: str, body: QualityFlagPatchBody, request: Request,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """区分度标记写入口（§6.2 line 1129——人工补标 / 状态迁移；契约细节为本段
    择型申报：keywords/tags 追加语义、state 三值、无则全空 400）。"""
    from knowledge_lattice.core.docs.quality import (
        QualityFlagNotFoundError,
        QualityPermissionError,
    )

    org = resolve_request_org(request, auth)
    if not (body.keywords or body.tags or body.state):
        raise HTTPException(
            status_code=400,
            detail="empty patch: keywords / tags / state 至少一项",
        )
    for field_name, value in (("keywords", body.keywords), ("tags", body.tags)):
        if value is not None and not value.strip():
            raise HTTPException(
                status_code=400, detail=f"{field_name} 不得为空白",
            )
    quality = _quality(request)
    try:
        return quality.patch_flag(
            flag_id,
            org_id=org,
            actor_user_id=auth.user_id,
            keywords=body.keywords.strip() if body.keywords else None,
            tags=body.tags.strip() if body.tags else None,
            state=body.state,
        )
    except QualityFlagNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QualityPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/api/quality-flags/sample")
async def sample_quality_flags(
    request: Request,
    n: int = 20,
    seed: str = "m1",
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """误报抽查抽样（org_admin——复核流程入口；记录形态见 PATCH manual_tags）。"""
    org = resolve_request_org(request, auth)
    service = get_service(request)
    membership = service.backend.read_membership(auth.user_id, org)
    if membership is None or membership["role"] != "org_admin":
        raise HTTPException(status_code=403, detail="org_admin required")
    quality = _quality(request)
    n = max(1, min(n, 100))
    return {"org": org, "flags": quality.sample_open_flags(org, n=n, seed=seed)}
