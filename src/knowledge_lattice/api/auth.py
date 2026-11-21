"""本地账号 REST（D25 / FR-9 / m4-2——`LATTICE_AUTH_MODE=local` 的认证面）。

两个 router（注册面在 ``app.py``）：

- ``public_router``（**恒注册**——sso/local 双形态）：``GET /api/auth/config`` /
  ``GET /api/setup/status``。sso 形态下仅这两个只读端点存在（setup_needed /
  completed / local_login_enabled 恒 false），其余 D25 端点 404（不注册即不存在）；
- ``local_router``（**仅 local 注册**）：首启 setup、登录/me/改密/登出、
  邀请 lookup/accept。

契约（`_m4-impl-contract.md` §5 冻结响应/错误码）：

- 错误体统一 ``{"error": str, "code": str}``——本模块只抛 :class:`AccountError`，
  由 ``app.py`` 的异常 handler 统一渲染（含 429 的 ``Retry-After`` 头）；
- 成功响应：setup/login/accept 为 session payload ``{token, expires_at, user,
  orgs}``；me 为 ``{user, orgs}``；改密为 ``{token, expires_at}``（tv++ 后的新
  会话）；logout 204；
- **密码/token 明文/摘要永不进审计**、永不进错误消息；store 全列含
  ``password_hash``/``token_hash``，对外响应一律经 :func:`public_user` 显式投影
  （禁止 ``**user``）；
- 登录限流键 ``f"{username}|{client_ip}"``（进程内单例 ``service.login_limiter``）；
  失败统一 401 ``invalid_credentials``（审计 reason 区分），锁定 429
  ``login_locked`` + ``Retry-After``。

分层：本模块只做协议转换/投影/审计编排；口令 scrypt、session JWT、限流器与
首启校验在 ``domain/accounts.py``，账号/邀请持久化在 store 的 ``AccountsBackend``
（m4-1——本段只调用，不改实现）。
"""

from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from knowledge_lattice.domain.accounts import (
    WeakPasswordError,
    hash_password,
    issue_session_token,
    validate_password,
    validate_username,
    verify_password,
)
from knowledge_lattice.domain.audit_events import (
    EVENT_AUTH_INVITE_ACCEPTED,
    EVENT_AUTH_LOGIN,
    EVENT_AUTH_LOGIN_REFUSED,
    EVENT_AUTH_LOGOUT,
    EVENT_AUTH_PASSWORD_CHANGED,
    EVENT_AUTH_PASSWORD_RESET,
    EVENT_INSTANCE_SETUP,
)
from knowledge_lattice.domain.auth import AuthContext, AuthError, hash_token
from knowledge_lattice.store.backend import (
    EmailTakenError,
    InvitationInvalidError,
    SetupCompletedError,
    UsernameTakenError,
)
from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

from .upload import get_auth, get_service

public_router = APIRouter()
local_router = APIRouter()

# ============ 错误载体（app.py 统一 handler —— {"error", "code"}） ============


class AccountError(Exception):
    """D25 账号面业务错误（m4-2）——status_code/code 双要素 + 可选响应头。

    契约 §5：错误体统一 ``{"error": str, "code": str}``；本类只承载语义，
    渲染在 ``app.py`` 的 ``AccountError`` 异常 handler（429 锁定需
    ``Retry-After`` 头——handler 透传 ``headers``）。
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.code = code
        self.headers = headers


# ============ 公共投影/助手（api/users.py 复用） ============


def public_user(user: dict) -> dict:
    """用户行 → 对外最小投影（**禁止 ``**user``**——store 全列含密码/令牌摘要）。

    字段集按 m4-2 任务冻结：id/username/display_name/email/status/
    is_system_admin/last_login_at/created_at。``password_hash``/``token_hash``/
    ``token_version``/``created_by``/``disabled_at`` 一律不出现在认证响应中。
    """
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "email": user["email"],
        "status": user["status"],
        "is_system_admin": bool(user["is_system_admin"]),
        "last_login_at": user["last_login_at"],
        "created_at": user["created_at"],
    }


def orgs_for_user(backend, user_id: str) -> list[dict]:
    """用户**有效**成员组织（``list_user_orgs`` 的 ``id`` 映射为 ``org_id``）。

    返回 ``[{org_id, name, role, status}]``——组织 status（active/disabled）如实
    返回，前端 boot 后据此提示停用组织（停用组织访问面由各端点 403，不受影响）。
    """
    return [
        {
            "org_id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "status": row["status"],
        }
        for row in backend.list_user_orgs(user_id)
    ]


def session_payload(service, user: dict) -> dict:
    """签发本地会话（``issue_session_token`` 用行内 token_version）→ session payload。

    ``{token, expires_at, user: public_user, orgs}``——setup/login/accept 共用；
    改密/重置后 token_version 已 ++（旧会话即时失效，新 token 用新版本）。
    """
    token, expires_at = issue_session_token(
        service.settings,
        user_id=user["id"],
        token_version=user["token_version"],
    )
    return {
        "token": token,
        "expires_at": expires_at,
        "user": public_user(user),
        "orgs": orgs_for_user(service.backend, user["id"]),
    }


def new_id(prefix: str) -> str:
    """生成业务 id（``u_<16hex>`` / ``inv_<16hex>``）——store 不生成 id（契约 §3）。"""
    return f"{prefix}_{secrets.token_hex(8)}"


def new_invite_token() -> str:
    """邀请/重置 token 明文（32B urlsafe——D25；库内只存其 sha256）。"""
    return secrets.token_urlsafe(32)


def invite_expires_at(settings) -> str:
    """邀请/重置 TTL 时点（UTC 库格式字符串——与 taskclock 同源）。"""
    return add_seconds(utc_now_ts(), settings.invite_ttl_s)


def invite_storage_hash(token: str) -> str:
    """邀请 token → 库内存储摘要（``users.token_hash`` 同款 sha256；明文不落库）。"""
    return hash_token(token)


def invitation_error(inv: dict | None, now: str) -> str | None:
    """邀请可用性分类（**纯判定**——不抛；lookup/accept/list 三面共用口径）。

    返回 ``revoked | consumed | expired | invalid``；**可用（pending）→ None**。
    判定序按契约 §5：revoked → consumed → expired（同一行多状态并存时以撤销
    优先——管理员显式动作压过单次/TTL 语义）。``now`` 为 UTC 库格式字符串。
    """
    if inv is None:
        return "invalid"
    if inv.get("revoked_at") is not None:
        return "revoked"
    if inv.get("consumed_at") is not None:
        return "consumed"
    expires_at = inv.get("expires_at")
    if expires_at is not None and str(expires_at) <= now:
        return "expired"
    return None


def invite_error(reason: str) -> AccountError:
    """不可用邀请 → 404 ``invite_<reason>``（消息含分类、不含 token 摘要/明文）。"""
    return AccountError(
        f"邀请 token 不可用（{reason}）", status_code=404, code=f"invite_{reason}"
    )


def _audit(backend, event_type: str, payload: dict) -> None:
    """审计事件入 outbox（payload 绝不携带密码/token——调用方纪律）。"""
    backend.append_outbox(event_type, json.dumps(payload, ensure_ascii=False))


def _validated_username(raw: str) -> str:
    try:
        return validate_username(raw)
    except ValueError as exc:
        raise AccountError(
            f"username 非法：{exc}", status_code=400, code="invalid_username"
        ) from exc


def _validated_password(raw: str, settings) -> None:
    try:
        validate_password(raw, settings.password_min_len)
    except WeakPasswordError as exc:
        raise AccountError(str(exc), status_code=400, code="weak_password") from exc


# ============ 公共只读端点（恒注册——sso/local 双形态） ============


@public_router.get("/api/auth/config")
async def auth_config(request: Request) -> dict:
    """Web boot 门（匿名）：``{auth_mode, setup_needed, local_login_enabled}``。

    sso 形态：setup_needed/local_login_enabled 恒 false（D25 口径——sso 不首启、
    不本地登录）；local 形态：零用户且无 instance_setup 行 → setup_needed=true。
    """
    service = get_service(request)
    local = service.settings.auth_mode == "local"
    setup_needed = False
    if local:
        backend = service.backend
        setup_needed = (
            backend.count_users() == 0 and backend.get_instance_setup() is None
        )
    return {
        "auth_mode": service.settings.auth_mode,
        "setup_needed": setup_needed,
        "local_login_enabled": local,
    }


@public_router.get("/api/setup/status")
async def setup_status(request: Request) -> dict:
    """首启状态（匿名）：``{setup_needed, completed}``；sso 形态双 false。"""
    service = get_service(request)
    if service.settings.auth_mode != "local":
        return {"setup_needed": False, "completed": False}
    backend = service.backend
    completed = backend.get_instance_setup() is not None
    return {
        "setup_needed": backend.count_users() == 0 and not completed,
        "completed": completed,
    }


# ============ 首启 setup（local 专属） ============


class SetupRequest(BaseModel):
    """``POST /api/setup`` 入参（契约 §5）：首管理员 + 可选首组织（成对）。"""

    username: str
    password: str
    display_name: str | None = None
    email: str | None = None
    org_id: str | None = None
    org_name: str | None = None
    init_password: str | None = None


@local_router.post("/api/setup", status_code=201)
async def setup_instance(request: Request, body: SetupRequest) -> dict:
    """零用户首启：建首 ``sysadmin``（可选同事务建首组织并任 ``org_admin``）。

    - ``LATTICE_INIT_PASSWORD`` 配置时 ``compare_digest`` 门禁——不符 403
      ``invalid_init_password``（常量时间比较，消息不回显期望值）；
    - username 非法 400 ``invalid_username``；弱密码 400 ``weak_password``；
      首组织 ``org_id``/``org_name`` 必须成对（400 ``invalid_org``）；
    - 已有用户 / 已有 instance_setup 行 / 并发竞争 → 409 ``setup_completed``
      （store 同事务 ``COUNT(users)==0`` + 单例行双保险）；
    - 成功 201 session payload；``instance.setup`` 审计与建档同事务，payload
      只含 user/org id（不含用户名之外的口令材料）。
    """
    service = get_service(request)
    settings = service.settings
    backend = service.backend
    if settings.init_password:
        supplied = body.init_password or ""
        if not secrets.compare_digest(supplied, settings.init_password):
            raise AccountError(
                "init_password 校验失败（LATTICE_INIT_PASSWORD 门禁——拒绝首启）",
                status_code=403,
                code="invalid_init_password",
            )
    username = _validated_username(body.username)
    _validated_password(body.password, settings)
    org_id = (body.org_id or "").strip() or None
    org_name = (body.org_name or "").strip() or None
    if (org_id is None) != (org_name is None):
        raise AccountError(
            "org_id/org_name 必须成对提供（首组织同事务创建）",
            status_code=400,
            code="invalid_org",
        )
    if backend.count_users() > 0 or backend.get_instance_setup() is not None:
        raise AccountError(
            "实例已完成首启 setup（零用户才允许首启——二次提交 409）",
            status_code=409,
            code="setup_completed",
        )
    user_id = new_id("u")
    audit = (
        EVENT_INSTANCE_SETUP,
        json.dumps(
            {"user_id": user_id, "org_id": org_id}, ensure_ascii=False
        ),
    )
    try:
        result = backend.setup_instance(
            admin_user_id=user_id,
            username=username,
            display_name=body.display_name,
            email=body.email,
            password_hash=hash_password(body.password),
            org_id=org_id,
            org_name=org_name,
            audit=audit,
        )
    except SetupCompletedError as exc:  # 并发竞争/已有行（预检后窗口）
        raise AccountError(str(exc), status_code=409, code="setup_completed") from exc
    except UsernameTakenError as exc:
        raise AccountError(str(exc), status_code=409, code="username_taken") from exc
    except EmailTakenError as exc:
        raise AccountError(str(exc), status_code=409, code="email_taken") from exc
    except ValueError as exc:  # store 兜底（org 单参等结构校验）
        raise AccountError(str(exc), status_code=400, code="invalid_org") from exc
    return session_payload(service, result["user"])


# ============ 登录/会话（local 专属） ============


class LoginRequest(BaseModel):
    """``POST /api/auth/login`` 入参——username 精确（不 lower）、password 明文仅本请求。"""

    username: str
    password: str


@local_router.post("/api/auth/login")
async def login(request: Request, body: LoginRequest) -> dict:
    """username+password → session payload；失败统一 401（不泄露账号存在性）。

    判定序：限流 ``check``（锁定 → 429 ``login_locked`` + ``Retry-After``）→
    未知用户 / 未设密码 / 停用 / invited / 密码错（审计 ``auth.login_refused``
    reason 区分；响应文案统一）→ 成功 reset 限流 + ``record_login`` +
    ``auth.login`` 审计 + session payload。
    """
    service = get_service(request)
    backend = service.backend
    limiter = service.login_limiter
    username = body.username.strip()
    client_ip = (request.client.host if request.client is not None else None) or "unknown"
    key = f"{username}|{client_ip}"
    retry_after = limiter.check(key)
    if retry_after is not None:
        limiter.record_failure(key)  # 锁定期间不重复计数/不延长（store 领域口径）
        _audit(
            backend, EVENT_AUTH_LOGIN_REFUSED,
            {"username": username, "reason": "locked", "ip": client_ip},
        )
        raise AccountError(
            "登录尝试过于频繁——已临时锁定，请稍后重试",
            status_code=429,
            code="login_locked",
            headers={"Retry-After": str(retry_after)},
        )
    user = backend.get_user_by_username(username)
    reason: str | None = None
    if user is None:
        reason = "unknown_user"
    elif user["password_hash"] is None:
        reason = "no_password"  # invited / 管理员建号未设密——不可密码登录
    elif user["disabled_at"] is not None:
        reason = "disabled"
    elif user["status"] != "active":
        reason = "invited"
    elif not verify_password(body.password, user["password_hash"]):
        reason = "bad_password"
    if reason is not None:
        limiter.record_failure(key)
        _audit(
            backend, EVENT_AUTH_LOGIN_REFUSED,
            {"username": username, "reason": reason, "ip": client_ip},
        )
        raise AccountError(
            "用户名或密码不正确", status_code=401, code="invalid_credentials"
        )
    limiter.reset(key)
    backend.record_login(user["id"])
    _audit(
        backend, EVENT_AUTH_LOGIN,
        {"user_id": user["id"], "username": user["username"]},
    )
    # record_login 后回读——响应 user.last_login_at 即本次登录时刻（回读失败用旧行兜底）
    refreshed = backend.get_user(user["id"]) or user
    return session_payload(service, refreshed)


@local_router.get("/api/auth/me")
async def current_user(
    request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    """当前用户 + 有效组织/角色（Bearer：local 会话；dev/test 下开发 token 兼容）。"""
    service = get_service(request)
    user = service.backend.get_user(auth.user_id)
    if user is None:
        raise AuthError("unknown user")
    return {
        "user": public_user(user),
        "orgs": orgs_for_user(service.backend, auth.user_id),
    }


class PasswordChangeRequest(BaseModel):
    """``POST /api/auth/password``：旧密验证 + 新密校验（tv++ 撤销旧会话）。"""

    old_password: str
    new_password: str


@local_router.post("/api/auth/password")
async def change_password(
    request: Request,
    body: PasswordChangeRequest,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """用户自改密码：旧密错 401（统一 ``invalid_credentials``）；弱密码 400。

    成功后 ``set_user_password(bump_token_version=True)``——``tv++`` 使所有旧
    会话即时失效；返回用**更新后** token_version 签发的新会话 ``{token,
    expires_at}``（Web 侧无感续期，其它设备被踢）。审计 ``auth.password_changed``
    与 UPDATE 同事务（payload 只含 user/actor）。
    """
    service = get_service(request)
    backend = service.backend
    settings = service.settings
    user = backend.get_user(auth.user_id)
    if (
        user is None
        or user["password_hash"] is None
        or not verify_password(body.old_password, user["password_hash"])
    ):
        raise AccountError(
            "旧密码不正确", status_code=401, code="invalid_credentials"
        )
    _validated_password(body.new_password, settings)
    audit = (
        EVENT_AUTH_PASSWORD_CHANGED,
        json.dumps(
            {"user_id": user["id"], "actor": auth.user_id}, ensure_ascii=False
        ),
    )
    updated = backend.set_user_password(
        user_id=user["id"],
        password_hash=hash_password(body.new_password),
        bump_token_version=True,
        audit=audit,
    )
    token, expires_at = issue_session_token(
        settings, user_id=updated["id"], token_version=updated["token_version"]
    )
    return {"token": token, "expires_at": expires_at}


@local_router.post("/api/auth/logout", status_code=204)
async def logout(request: Request, auth: AuthContext = Depends(get_auth)) -> None:
    """登出 204：无服务端撤销（无状态 session——客户端清 token 即可，G-34）。

    仅记 ``auth.logout`` 审计（payload 只含 user_id；不写 token/摘要）。
    """
    _audit(
        get_service(request).backend, EVENT_AUTH_LOGOUT, {"user_id": auth.user_id}
    )


# ============ 邀请/重置 lookup + accept（匿名——local 专属） ============


class InvitationTokenRequest(BaseModel):
    """邀请 token 载体（lookup 入参——body 传 token，避免 URL/日志留痕）。"""

    token: str


@local_router.post("/api/auth/invitations/lookup")
async def lookup_invitation(request: Request, body: InvitationTokenRequest) -> dict:
    """邀请/重置详情（匿名）：无效/过期/已用/撤销 → 404 ``invite_<reason>``。

    响应只回邀请展示所需字段（purpose/username/display_name/email/org_id/
    org_name/role/expires_at）——**不含 token 摘要**与用户密码材料。
    """
    service = get_service(request)
    inv = service.backend.find_invitation_by_token_hash(
        invite_storage_hash(body.token)
    )
    reason = invitation_error(inv, utc_now_ts())
    if reason is not None:
        raise invite_error(reason)
    if inv is None:  # 不可达（reason None 蕴含存在）——fail-closed 兜底
        raise invite_error("invalid")
    return {
        "purpose": inv["purpose"],
        "username": inv["username"],
        "display_name": inv["display_name"],
        "email": inv["email"],
        "org_id": inv["org_id"],
        "org_name": inv["org_name"],
        "role": inv["role"],
        "expires_at": inv["expires_at"],
    }


class InvitationAcceptRequest(BaseModel):
    """接受邀请/重置密码（匿名）：token + 新密码 +（invite 用途的）display_name。"""

    token: str
    password: str
    display_name: str | None = None


@local_router.post("/api/auth/invitations/accept")
async def accept_invitation(request: Request, body: InvitationAcceptRequest) -> dict:
    """接受邀请（invited→active）或重置密码（reset）→ 200 session payload。

    - 无效/过期/已用/撤销 → 404 ``invite_<reason>``（先分类再谈密码强度——
      防止对无效 token 探测密码策略无意义调用）；
    - 弱密码 400 ``weak_password``（不消费 token——可重试）；
    - ``accept_invitation`` 原子：consumed_at + 设密 + status=active + tv++
      + invite 用途补成员关系（已存在不降级）+ 审计（invite→``auth.invite_accepted``
      / reset→``auth.password_reset``）；并发双消费只有一方成功；
    - 成功响应与 login 同形（session payload）——前端可直接进应用。
    """
    service = get_service(request)
    backend = service.backend
    token_hash = invite_storage_hash(body.token)
    inv = backend.find_invitation_by_token_hash(token_hash)
    reason = invitation_error(inv, utc_now_ts())
    if reason is not None:
        raise invite_error(reason)
    if inv is None:  # 不可达（reason None 蕴含存在）——fail-closed 兜底
        raise invite_error("invalid")
    _validated_password(body.password, service.settings)
    purpose = inv["purpose"]
    audit_event = (
        EVENT_AUTH_INVITE_ACCEPTED if purpose == "invite" else EVENT_AUTH_PASSWORD_RESET
    )
    try:
        result = backend.accept_invitation(
            token_hash=token_hash,
            password_hash=hash_password(body.password),
            # reset 用途不接受 display_name（重置不是改档案——契约 §5）
            display_name=(body.display_name if purpose == "invite" else None),
            audit_event=audit_event,
            actor_label=inv["user_id"],
        )
    except InvitationInvalidError as exc:
        raise invite_error(exc.reason) from exc
    return session_payload(service, result["user"])


__all__ = [
    "AccountError",
    "public_user",
    "orgs_for_user",
    "session_payload",
    "new_id",
    "new_invite_token",
    "invite_expires_at",
    "invite_storage_hash",
    "invitation_error",
    "invite_error",
    "public_router",
    "local_router",
]
