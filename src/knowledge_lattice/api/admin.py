"""管理端点（design §6.2——M0a 最小集 + M2.4 m2-2 删库收口）：

- POST /api/dev/token（`dev_token_router`）：签发开发 JWT——**仅 dev/test 配置注册
  路由，生产 404**（TC-AUTH-01④）；只能给自己签或系统管理员签发（403 语义）；
- GET /api/orgs/{org}/dimensions · /datasets（`router`）：只读清单（页壳上传/检索
  表单所需）——普通组织作用域端点，**不受环境门控**（P2-4）；
- DELETE /api/orgs/{org}/datasets/{id}（M2.4 m2-2——T19 半句收口/TC-OPS-04）：
  **org_admin**；仍有文档 → 409 明确报错（RESTRICT——非裸外键异常）；治理事件
  与删行同事务入 outbox。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from knowledge_lattice.domain.audit_events import EVENT_DATASET_DELETE
from knowledge_lattice.domain.auth import AuthContext, issue_dev_jwt
from knowledge_lattice.store.backend import DatasetNotEmptyError

from .upload import get_auth, get_service, org_scoped

router = APIRouter()
dev_token_router = APIRouter()  # 仅 dev/test 注册（app.py 门控——生产 404）


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
    membership = service.backend.read_membership(auth.user_id, org)
    if membership is None or membership["role"] != "org_admin":
        raise HTTPException(status_code=403, detail="org_admin required（FR-4 操作矩阵）")
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
