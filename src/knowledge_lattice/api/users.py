"""用户/邀请管理 REST（D25 / FR-9 / m4-2——**local 专属 router**）。

端点（契约 `_m4-impl-contract.md` §5 冻结）：

- ``GET/POST /api/users`` · ``PATCH /api/users/{id}`` · ``POST /api/users/{id}/reset``
  ——全局账号管理，**sysadmin 专属**；
- ``GET/POST /api/orgs/{org}/invitations`` · ``DELETE .../{id}``——本组织邀请管理，
  **org_admin 专属** + ``org_scoped``（成员/停用组织/路径头一致性）。

错误体统一 ``{"error", "code"}``（:class:`AccountError`——app.py 统一 handler）。
本模块只调用 m4-1 的 ``AccountsBackend`` 写方法（全部带 ``audit=`` 同事务）：
用户/邀请的原子性、单次消费、重发撤销、末位 sysadmin 守卫均在 store 域内，
API 层只做权限/参数/错误码映射与响应投影。

审计 payload 纪律：只含 id/username/role/actor 等结构字段——**密码、token 明文
与摘要永不进 payload**（store 侧 invite accept 事件同样由 store 构造、不含 token）。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, model_validator

from knowledge_lattice.domain.accounts import validate_username
from knowledge_lattice.domain.audit_events import (
    EVENT_AUTH_INVITE_CREATED,
    EVENT_AUTH_INVITE_REVOKED,
    EVENT_MEMBER_ADD,
    EVENT_USER_CREATED,
    EVENT_USER_DISABLED,
    EVENT_USER_ENABLED,
    EVENT_USER_SYSADMIN_CHANGED,
)
from knowledge_lattice.domain.auth import AuthContext
from knowledge_lattice.store.backend import (
    EmailTakenError,
    LastSysadminError,
    MembershipExistsError,
    UsernameTakenError,
)
from knowledge_lattice.store.taskclock import utc_now_ts

from .auth import (
    AccountError,
    invitation_error,
    invite_expires_at,
    invite_storage_hash,
    new_id,
    new_invite_token,
    public_user,
)
from .upload import get_auth, get_service, org_scoped

router = APIRouter()

# 邀请角色白名单（D25：org_admin 邀本组织 member/org_admin；sem_restricted 不经
# 邀请授予——语义层敏感权限由管理面显式授予，G-24①）
_INVITE_ROLES = ("member", "org_admin")


# ============ 权限助手 ============


def _require_sysadmin(auth: AuthContext) -> None:
    """全局账号管理门控（GET/POST/PATCH/reset /api/users*）。"""
    if not auth.is_system_admin:
        raise AccountError(
            "系统管理员专属操作（D25——全局账号管理）",
            status_code=403,
            code="sysadmin_required",
        )


def _require_org_admin(service, auth: AuthContext, org: str) -> None:
    """本组织邀请管理门控（沿 admin.py ``_require_org_admin`` 同判据：
    ``read_membership`` 有效行且 role='org_admin'——过期/无行均 403）。"""
    membership = service.backend.read_membership(auth.user_id, org)
    if membership is None or membership["role"] != "org_admin":
        raise AccountError(
            "org_admin required（FR-4 操作矩阵——本组织邀请管理）",
            status_code=403,
            code="org_admin_required",
        )


def _audit_payload(event_type: str, payload: dict) -> tuple[str, str]:
    return event_type, json.dumps(payload, ensure_ascii=False)


def _validated_username(raw: str) -> str:
    try:
        return validate_username(raw)
    except ValueError as exc:
        raise AccountError(
            f"username 非法：{exc}", status_code=400, code="invalid_username"
        ) from exc


def _admin_user(user: dict) -> dict:
    """管理面用户投影（契约 §5 GET /api/users 十字段——auth 面 public_user 的
    超集：补 ``disabled_at``/``created_by``，管理页据此展示停用态与建号来源）。

    仍为**逐键显式投影**（禁止 ``**user``——store 行含 password_hash/token_hash）。
    """
    return {
        **public_user(user),
        "disabled_at": user["disabled_at"],
        "created_by": user["created_by"],
    }


def _invitation_body(invitation: dict, token: str) -> dict:
    """邀请创建响应（明文 token 只在响应中出现一次——库内只存 sha256）。"""
    return {
        "id": invitation["id"],
        "token": token,
        "expires_at": invitation["expires_at"],
    }


def _mint_invitation(
    *, backend, settings, user_id: str, org_id: str | None, role: str | None,
    invited_by: str, purpose: str, purpose_extra: dict | None = None,
) -> tuple[str, dict]:
    """签发邀请/重置 token 并落库（``create_invitation`` + ``auth.invite_created``）。

    返回 ``(明文 token, 邀请行)``；重发 ``revoke_pending=True``（旧链接失效）。
    audit payload 只含 id/org/role/actor——不含 token 明文或摘要。
    """
    token = new_invite_token()
    invitation_id = new_id("inv")
    expires_at = invite_expires_at(settings)
    audit = _audit_payload(EVENT_AUTH_INVITE_CREATED, {
        "invitation_id": invitation_id,
        "user_id": user_id,
        "org_id": org_id,
        "role": role,
        "purpose": purpose,
        "actor": invited_by,
        **(purpose_extra or {}),
    })
    row = backend.create_invitation(
        invitation_id=invitation_id,
        user_id=user_id,
        org_id=org_id,
        role=role,
        purpose=purpose,
        token_hash=invite_storage_hash(token),
        invited_by=invited_by,
        expires_at=expires_at,
        revoke_pending=True,
        audit=audit,
    )
    return token, row


# ============ 全局账号管理（sysadmin） ============


@router.get("/api/users")
async def list_users(
    request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    """全局账号列表（sysadmin）：显式投影——``list_users`` 行含 token_hash，
    经 :func:`_admin_user` 裁剪后对外（password_hash 本就不在 store 列表面）。"""
    _require_sysadmin(auth)
    users = get_service(request).backend.list_users()
    return {"users": [_admin_user(user) for user in users]}


class UserCreateRequest(BaseModel):
    """``POST /api/users``（sysadmin 直接建号——不设密码，返回邀请/设密链接）。

    ``org_id``/``role`` 成对：有组织则 ``role ∈ {member, org_admin}``；无组织则
    role 必须缺省/None（全局预登记，接受邀请后不自动入组）。
    """

    username: str
    display_name: str | None = None
    email: str | None = None
    is_system_admin: bool = False
    org_id: str | None = None
    role: str | None = None


@router.post("/api/users", status_code=201)
async def create_user(
    request: Request, body: UserCreateRequest,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """管理员建号（invited，无密码）→ 201 ``{user, invitation}``。

    - ``org_id``/``role`` 成对（400 ``invalid_role``）；组织不存在 404
      ``org_not_found``；role 只允许 member/org_admin；
    - username/email 冲突 409 ``username_taken``/``email_taken``（store 语义化）；
    - ``create_invited_user`` 用户 + 邀请 + 审计同事务（``user.created``——
      建号为该端点主事件；邀请创建的独立事件由本组织邀请端点承载）；
    - 邀请 token 明文只在响应中出现一次（库内只存 sha256）。
    """
    _require_sysadmin(auth)
    service = get_service(request)
    backend = service.backend
    username = _validated_username(body.username)
    org_id = (body.org_id or "").strip() or None
    role = (body.role or "").strip() or None
    if org_id is None and role is not None:
        raise AccountError(
            "org_id 与 role 必须成对提供（无组织时 role 须缺省/None）",
            status_code=400,
            code="invalid_role",
        )
    if org_id is not None:
        if role not in _INVITE_ROLES:
            raise AccountError(
                f"invalid role: {role!r}（member | org_admin）",
                status_code=400,
                code="invalid_role",
            )
        if backend.get_org_status(org_id) is None:
            raise AccountError(
                f"org not found: {org_id!r}", status_code=404, code="org_not_found"
            )
    user_id = new_id("u")
    invitation_id = new_id("inv")
    token = new_invite_token()
    expires_at = invite_expires_at(service.settings)
    audit = _audit_payload(EVENT_USER_CREATED, {
        "user_id": user_id,
        "username": username,
        "org_id": org_id,
        "role": role,
        "is_system_admin": bool(body.is_system_admin),
        "invitation_id": invitation_id,
        "actor": auth.user_id,
    })
    try:
        result = backend.create_invited_user(
            user_id=user_id,
            username=username,
            display_name=body.display_name,
            email=body.email,
            invitation_id=invitation_id,
            org_id=org_id,
            role=role,
            token_hash=invite_storage_hash(token),
            invited_by=auth.user_id,
            expires_at=expires_at,
            is_system_admin=bool(body.is_system_admin),
            audit=audit,
        )
    except UsernameTakenError as exc:
        raise AccountError(str(exc), status_code=409, code="username_taken") from exc
    except EmailTakenError as exc:
        raise AccountError(str(exc), status_code=409, code="email_taken") from exc
    return {
        "user": _admin_user(result["user"]),
        "invitation": _invitation_body(result["invitation"], token),
    }


class UserPatchRequest(BaseModel):
    """``PATCH /api/users/{id}``：disabled / is_system_admin（至少一项，extra forbid）。"""

    model_config = {"extra": "forbid"}

    disabled: bool | None = None
    is_system_admin: bool | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "UserPatchRequest":
        if self.disabled is None and self.is_system_admin is None:
            raise ValueError("至少提供 disabled 或 is_system_admin 之一")
        return self


@router.patch("/api/users/{user_id}")
async def patch_user(
    user_id: str, request: Request, body: UserPatchRequest,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """停用/恢复/授撤 sysadmin（sysadmin）→ 200 ``{user}``。

    - 用户不存在 404 ``user_not_found``；末位 active sysadmin 的停用/撤权 409
      ``last_sysadmin``（store 同事务守卫）；
    - 停用即时 401（``disabled_at`` + ``tv++``——旧会话不复活）；启用清
      ``disabled_at`` 但 tv 不回退（旧 token 仍失效，需重新登录）；
    - 「至少一项」由 pydantic 校验（422）；非法字段 422。
    """
    _require_sysadmin(auth)
    service = get_service(request)
    try:
        updated = service.backend.update_user_flags(
            user_id=user_id,
            disabled=body.disabled,
            is_system_admin=body.is_system_admin,
            actor=auth.user_id,
            audits=[
                EVENT_USER_DISABLED,
                EVENT_USER_ENABLED,
                EVENT_USER_SYSADMIN_CHANGED,
            ],
        )
    except KeyError as exc:
        raise AccountError(
            f"user not found: {user_id!r}", status_code=404, code="user_not_found"
        ) from exc
    except LastSysadminError as exc:
        raise AccountError(str(exc), status_code=409, code="last_sysadmin") from exc
    return {"user": _admin_user(updated)}


@router.post("/api/users/{user_id}/reset")
async def reset_user_password(
    user_id: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    """生成一次性重置链接（sysadmin）→ 200 ``{invitation}``。

    - 用户不存在 404 ``user_not_found``；停用用户 409 ``user_disabled``
      （停用态不可重置——先恢复，防「重置即复活」旁路）；
    - ``purpose='reset'``（org_id/role 为空——重置不改变组织成员关系），
      ``revoke_pending=True``（旧重置链接失效）；审计 ``auth.invite_created``；
    - 接受重置链接 = ``POST /api/auth/invitations/accept``（``tv++`` 全旧会话失效，
      审计 ``auth.password_reset``）；org_admin 无本端点（不能重置他人密码）。
    """
    _require_sysadmin(auth)
    service = get_service(request)
    backend = service.backend
    target = backend.get_user(user_id)
    if target is None:
        raise AccountError(
            f"user not found: {user_id!r}", status_code=404, code="user_not_found"
        )
    if target["disabled_at"] is not None:
        raise AccountError(
            f"用户已停用（{user_id!r}）——先恢复再重置密码",
            status_code=409,
            code="user_disabled",
        )
    token, inv = _mint_invitation(
        backend=backend,
        settings=service.settings,
        user_id=user_id,
        org_id=None,
        role=None,
        invited_by=auth.user_id,
        purpose="reset",
    )
    return {"invitation": _invitation_body(inv, token)}


# ============ 本组织邀请管理（org_admin + org_scoped） ============


class OrgInvitationCreateRequest(BaseModel):
    """``POST /api/orgs/{org}/invitations``：username + role（member/org_admin）。"""

    username: str
    role: str
    display_name: str | None = None
    email: str | None = None


@router.get("/api/orgs/{org}/invitations")
async def list_org_invitations(
    org: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    """本组织邀请列表（org_admin）：status = pending/consumed/revoked/expired。

    显式投影（不泄露 token_hash）；``status`` 按 ``invitation_error`` 同口径
    计算（revoked→consumed→expired），未消费未撤销未过期 = pending。
    """
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    now = utc_now_ts()
    invitations = []
    for row in service.backend.list_invitations(org):
        reason = invitation_error(row, now)
        invitations.append({
            "id": row["id"],
            "user_id": row["user_id"],
            "username": row["username"],
            "role": row["role"],
            "purpose": row["purpose"],
            "status": reason or "pending",
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "consumed_at": row["consumed_at"],
            "revoked_at": row["revoked_at"],
            "invited_by": row["invited_by"],
        })
    return {"invitations": invitations}


@router.post("/api/orgs/{org}/invitations", status_code=201)
async def create_org_invitation(
    org: str, request: Request, body: OrgInvitationCreateRequest,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """邀请进本组织（org_admin）→ 201 ``{user_id, membership_added, invitation}``。

    分支（契约 §5）：
    - 已有用户且 **disabled** → 409 ``user_disabled``；
    - 已有用户 **status='invited'** → 重发邀请（``revoke_pending=True``，旧链接
      失效；不重置密码、不改档案）；
    - 已有用户 **active 且无有效成员关系** → 直接 ``add_membership``（审计
      ``member.add``），``membership_added=true``、``invitation=null``；
    - 已有成员（含过期行——store 语义 409）→ 409 ``member_exists``；
    - 新用户 → ``create_invited_user``（invited + 邀请，审计 ``auth.invite_created``），
      ``membership_added=false`` + 邀请链接。

    org_scoped 先行（路径/头一致性 + 成员 + 组织停用），再 org_admin 门控；
    跨组织（操作者非本组织 org_admin）→ 403。
    """
    org = org_scoped(request, org, auth)
    service = get_service(request)
    backend = service.backend
    _require_org_admin(service, auth, org)
    if body.role not in _INVITE_ROLES:
        raise AccountError(
            f"invalid role: {body.role!r}（member | org_admin）",
            status_code=400,
            code="invalid_role",
        )
    username = _validated_username(body.username)
    existing = backend.get_user_by_username(username)
    if existing is not None:
        user_id = existing["id"]
        if existing["disabled_at"] is not None:
            raise AccountError(
                f"用户已停用（{username!r}）——不可邀请/加组，先恢复",
                status_code=409,
                code="user_disabled",
            )
        if existing["status"] == "invited":
            token, inv = _mint_invitation(
                backend=backend,
                settings=service.settings,
                user_id=user_id,
                org_id=org,
                role=body.role,
                invited_by=auth.user_id,
                purpose="invite",
                purpose_extra={"username": username},
            )
            return {
                "user_id": user_id,
                "membership_added": False,
                "invitation": _invitation_body(inv, token),
            }
        try:
            added = backend.add_membership(
                org, user_id, role=body.role,
                audit=_audit_payload(EVENT_MEMBER_ADD, {
                    "org_id": org, "user_id": user_id, "role": body.role,
                    "actor": auth.user_id,
                }),
            )
        except MembershipExistsError as exc:
            raise AccountError(
                str(exc), status_code=409, code="member_exists"
            ) from exc
        except KeyError as exc:  # 并发删除窗口——用户不存在
            raise AccountError(
                f"user not found: {user_id!r}", status_code=404,
                code="user_not_found",
            ) from exc
        return {
            "user_id": added["user_id"],
            "membership_added": True,
            "invitation": None,
        }
    # 新用户：invited 建档 + 邀请 + 审计同事务
    user_id = new_id("u")
    invitation_id = new_id("inv")
    token = new_invite_token()
    expires_at = invite_expires_at(service.settings)
    audit = _audit_payload(EVENT_AUTH_INVITE_CREATED, {
        "invitation_id": invitation_id,
        "user_id": user_id,
        "username": username,
        "org_id": org,
        "role": body.role,
        "purpose": "invite",
        "actor": auth.user_id,
    })
    try:
        result = backend.create_invited_user(
            user_id=user_id,
            username=username,
            display_name=body.display_name,
            email=body.email,
            invitation_id=invitation_id,
            org_id=org,
            role=body.role,
            token_hash=invite_storage_hash(token),
            invited_by=auth.user_id,
            expires_at=expires_at,
            is_system_admin=False,
            audit=audit,
        )
    except UsernameTakenError as exc:
        raise AccountError(str(exc), status_code=409, code="username_taken") from exc
    except EmailTakenError as exc:
        raise AccountError(str(exc), status_code=409, code="email_taken") from exc
    return {
        "user_id": result["user"]["id"],
        "membership_added": False,
        "invitation": _invitation_body(result["invitation"], token),
    }


@router.delete("/api/orgs/{org}/invitations/{invitation_id}", status_code=204)
async def revoke_org_invitation(
    org: str, invitation_id: str, request: Request,
    auth: AuthContext = Depends(get_auth),
) -> None:
    """撤销 pending 邀请（org_admin）→ 204；未知/非 pending/跨组织 → 404。

    store ``revoke_invitation`` 仅对未消费、未撤销、未过期的本组织行生效
    （rowcount→False = 404 ``invite_invalid``）；审计 ``auth.invite_revoked``
    仅在实际撤销时同事务写入。
    """
    org = org_scoped(request, org, auth)
    service = get_service(request)
    _require_org_admin(service, auth, org)
    applied = service.backend.revoke_invitation(
        invitation_id=invitation_id,
        org_id=org,
        actor=auth.user_id,
        audit=_audit_payload(EVENT_AUTH_INVITE_REVOKED, {
            "invitation_id": invitation_id,
            "org_id": org,
            "actor": auth.user_id,
        }),
    )
    if not applied:
        raise AccountError(
            f"邀请不可撤销（不存在/已消费/已撤销/已过期）: {invitation_id!r}",
            status_code=404,
            code="invite_invalid",
        )


__all__ = ["router"]
