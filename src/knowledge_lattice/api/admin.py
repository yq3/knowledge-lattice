"""管理端点（design §6.2——M0a 最小集）：

- POST /api/dev/token：签发开发 JWT——**仅 dev/test 配置注册路由，生产 404**
  （TC-AUTH-01④）；只能给自己签或系统管理员签发（403 语义）；
- GET /api/orgs/{org}/dimensions · /datasets：只读清单（页壳上传/检索表单所需）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from knowledge_lattice.domain.auth import AuthContext, issue_dev_jwt

from .upload import get_auth, get_service, org_scoped

router = APIRouter()


class DevTokenRequest(BaseModel):
    user_id: str | None = None  # 缺省=给自己签；给他人签须系统管理员
    org: str | None = None  # 嵌入 token 的 org claim（单值——按组织签发）


@router.post("/api/dev/token")
async def issue_dev_token(
    request: Request, auth: AuthContext = Depends(get_auth), body: DevTokenRequest | None = None
) -> dict:
    """开发 JWT 签发（仅 dev/test 注册——路由注册开关在 app.py，D18/TC-AUTH-01）。"""
    body = body or DevTokenRequest()
    target = body.user_id or auth.user_id
    if target != auth.user_id and not auth.is_system_admin:
        raise HTTPException(status_code=403, detail="只能给自己签发；代签须系统管理员")
    service = get_service(request)
    token = issue_dev_jwt(service.settings, user_id=target, org=body.org)
    return {
        "token": token,
        "token_type": "bearer",
        "user_id": target,
        "org": body.org,
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
