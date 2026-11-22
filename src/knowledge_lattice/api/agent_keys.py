"""Agent 长寿命凭据管理 REST（D26 / issue #34 阶段 2B——**local 专属 router**）。

端点（issue #34「API / UI」面；Web 管理页不在本段）：

- ``GET /api/orgs/{org}/agent-keys``——本组织 key 列表（**含已撤销**，供管理面
  对账）；行投影**不含 token_hash**，附 ``user_username``（用户缺失回 None）；
- ``POST /api/orgs/{org}/agent-keys``——代本组织 active 成员签发 key
  （``{user_id, label}``，``extra="forbid"``）；明文 key **只在 201 响应出现
  一次**（库内只存 sha256 摘要与展示前缀）；
- ``DELETE /api/orgs/{org}/agent-keys/{key_id}``——软撤销（即时生效、行保留）；
  已撤销幂等 204 且**零新审计**。

权限解析（每个端点同一顺序——D26「权限」节 + 组织作用域纪律）：

1. ``check_path_org``——路径 org 与 ``X-Org-Id`` 并存不一致 → 400；
2. 组织不存在 → 404 ``org_not_found``；
3. ``enforce_agent_key_org``——agent key **组织绑定**（key 绑 A 不得管理 B，
   sysadmin 的 key 同样受限）→ 403 ``org_mismatch``；
4. ``auth.is_system_admin`` 直接放行（sysadmin 豁免：无本组织 org_admin 成员
   关系也可管理；**可管停用组织**——便于撤销泄露 key）；
5. 否则 ``read_membership`` 须为 ``org_admin`` → 403 ``org_admin_required``；
6. 组织停用 → 403 ``org_disabled``（sysadmin 已在第 4 步放行）。

创建目标校验（D26）：目标用户不存在 404 ``user_not_found``；停用 /
``status != "active"``（invited 等）400 ``user_not_active``；非本组织成员
400 ``member_not_found``（角色不限——member/org_admin/sysadmin 均可归属）。

审计：``agent_key.created`` / ``agent_key.revoked`` 与写行**同一事务**（store
``audit=`` 先例）；payload 只含 actor/key_id/org_id/user_id/label——**明文 key
与 token_hash 永不进审计/日志/错误消息**（明文仅创建响应一次）。撤销 payload
只用请求路径与操作者，不在撤销前为补字段回查 key 行。

错误体统一 ``{"error", "code"}``：业务错误经 :class:`AccountError`（app.py
统一 handler）；org 上下文 400 与 org_mismatch 403 沿用既有
``OrgContextError`` / ``AclDeniedError`` 映射（与 ``org_scoped`` 同语义）。
"""

from __future__ import annotations

import json
import unicodedata

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from knowledge_lattice.domain.agent_keys import generate_agent_key
from knowledge_lattice.domain.audit_events import (
    EVENT_AGENT_KEY_CREATED,
    EVENT_AGENT_KEY_REVOKED,
)
from knowledge_lattice.domain.auth import AuthContext, OrgContextError, check_path_org

from .auth import AccountError, new_id
from .upload import enforce_agent_key_org, get_auth, get_service

router = APIRouter()

# label 长度上限（D26 API 契约：strip 后 1..64——展示/审计载荷有界）
LABEL_MAX_LEN = 64


# ============ 权限解析（每端点同一顺序——模块 docstring 1~6） ============


def _manage_org(request: Request, org: str, auth: AuthContext) -> str:
    """管理面组织解析：路径/头一致性 → 组织存在 → key 绑定 → sysadmin/org_admin。

    顺序刻意与 ``org_scoped`` 不同（D26）：本面允许 sysadmin 管理**停用组织**
    （撤销泄露 key 的运维路径），因此停用判据只在 org_admin 分支落地；agent key
    的组织绑定守卫在 sysadmin 放行**之前**——key 只在其绑定组织内有效，即使
    归属用户是 sysadmin（跨组织操作须用会话/委托身份）。
    """
    try:
        resolved = check_path_org(
            path_org=org, org_header=request.headers.get("x-org-id")
        )
    except OrgContextError as exc:
        raise OrgContextError(str(exc)) from exc
    service = get_service(request)
    status = service.backend.get_org_status(resolved)
    if status is None:
        raise AccountError(
            f"org not found: {resolved!r}", status_code=404, code="org_not_found"
        )
    enforce_agent_key_org(auth, resolved)
    if auth.is_system_admin:
        return resolved
    membership = service.backend.read_membership(auth.user_id, resolved)
    if membership is None or membership["role"] != "org_admin":
        raise AccountError(
            "org_admin required（D26——本组织 agent key 管理）",
            status_code=403,
            code="org_admin_required",
        )
    if status == "disabled":
        raise AccountError(
            f"org disabled: {resolved!r}——组织已停用（fail-closed：管理面 403；"
            "恢复走 PATCH /api/orgs/{org} status=active，sysadmin 专属）",
            status_code=403,
            code="org_disabled",
        )
    return resolved


# ============ 投影/参数助手 ============


def _key_view(row: dict, *, user_username: str | None) -> dict:
    """key 行 → 对外投影（**逐键显式**——store 行含 token_hash，禁止 ``**row``）。

    字段按 D26 管理面契约：id/org_id/user_id/label/prefix/created_by/created_at/
    last_used_at/revoked_at/revoked_by/expires_at + ``user_username``
    （``backend.get_user(user_id)`` 的人类可读键；用户行缺失回 None）。
    """
    return {
        "id": row["id"],
        "org_id": row["org_id"],
        "user_id": row["user_id"],
        "label": row["label"],
        "prefix": row["prefix"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "last_used_at": row["last_used_at"],
        "revoked_at": row["revoked_at"],
        "revoked_by": row["revoked_by"],
        "expires_at": row["expires_at"],
        "user_username": user_username,
    }


def _audit_payload(event_type: str, payload: dict) -> tuple[str, str]:
    return event_type, json.dumps(payload, ensure_ascii=False)


def _validated_label(raw: str) -> str:
    """label 归一与校验（strip 后 1..64；控制/格式字符拒绝——审计载荷卫生）。"""
    label = raw.strip()
    if not 1 <= len(label) <= LABEL_MAX_LEN:
        raise AccountError(
            f"label 长度须为 1..{LABEL_MAX_LEN}（strip 后）：{raw!r}",
            status_code=400,
            code="invalid_label",
        )
    if any(unicodedata.category(ch).startswith("C") for ch in label):
        raise AccountError(
            "label 不得包含控制/格式字符", status_code=400, code="invalid_label"
        )
    return label


def _username_of(backend, user_id: str, cache: dict[str, str | None]) -> str | None:
    """``get_user`` 取用户名的按行缓存（列表 N+1 收敛；缺失回 None）。"""
    if user_id not in cache:
        user = backend.get_user(user_id)
        cache[user_id] = None if user is None else user["username"]
    return cache[user_id]


# ============ 端点 ============


@router.get("/api/orgs/{org}/agent-keys")
async def list_agent_keys(
    org: str, request: Request, auth: AuthContext = Depends(get_auth)
) -> dict:
    """本组织 key 列表（org_admin / sysadmin）→ ``{"keys": [行投影]}``。

    含已撤销行（``revoked_at``/``revoked_by`` 如实返回）；**不返回 token_hash**，
    也不返回任何明文 key（明文只在创建响应出现一次）。
    """
    org = _manage_org(request, org, auth)
    backend = get_service(request).backend
    usernames: dict[str, str | None] = {}
    keys = [
        _key_view(
            row, user_username=_username_of(backend, row["user_id"], usernames)
        )
        for row in backend.list_agent_keys(org)
    ]
    return {"keys": keys}


class AgentKeyCreateRequest(BaseModel):
    """``POST /api/orgs/{org}/agent-keys``：``{user_id, label}``（未知字段 422）。"""

    model_config = {"extra": "forbid"}

    user_id: str
    label: str


@router.post("/api/orgs/{org}/agent-keys", status_code=201)
async def create_agent_key(
    org: str,
    request: Request,
    body: AgentKeyCreateRequest,
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """代本组织 active 成员签发 key → 201 ``{key, ...行投影}``。

    - ``key`` = ``lka_`` + 32 字节随机串，**仅此一次**返回明文；库内只存 sha256
      与展示前缀（``prefix``），审计 payload 不含明文/摘要；
    - 目标校验顺序（D26）：用户不存在 404 → 停用/非 active 400 → 非本组织成员
      400（角色不限）；
    - 永不过期（``expires_at=None``，字段预留）；创建与 ``agent_key.created``
      审计同事务（store 侧原子性）。
    """
    org = _manage_org(request, org, auth)
    service = get_service(request)
    backend = service.backend
    user_id = body.user_id.strip()

    target_auth = backend.get_user_auth(user_id)
    if target_auth is None:
        raise AccountError(
            f"user not found: {user_id!r}", status_code=404, code="user_not_found"
        )
    if target_auth["disabled_at"] is not None or target_auth["status"] != "active":
        raise AccountError(
            f"user not active: {user_id!r}（停用/invited 用户不可签发 agent key）",
            status_code=400,
            code="user_not_active",
        )
    target = backend.get_user(user_id)
    if target is None:  # 并发删除窗口（get_user_auth 通过后行消失——fail-closed）
        raise AccountError(
            f"user not found: {user_id!r}", status_code=404, code="user_not_found"
        )
    if backend.read_membership(user_id, org) is None:
        raise AccountError(
            f"member not found: user={user_id!r} org={org!r}"
            "（目标用户须为本组织成员，角色不限）",
            status_code=400,
            code="member_not_found",
        )

    label = _validated_label(body.label)
    plaintext, prefix, token_hash = generate_agent_key()
    key_id = new_id("ak")
    audit = _audit_payload(EVENT_AGENT_KEY_CREATED, {
        "actor": auth.user_id,
        "key_id": key_id,
        "org_id": org,
        "user_id": user_id,
        "label": label,
    })
    try:
        row = backend.create_agent_key(
            key_id=key_id,
            org_id=org,
            user_id=user_id,
            label=label,
            token_hash=token_hash,
            prefix=prefix,
            created_by=auth.user_id,
            expires_at=None,
            audit=audit,
        )
    except ValueError as exc:  # token_hash 全库 UNIQUE（32B 随机源撞库——重新签发）
        raise AccountError(
            "agent key 摘要冲突（32B 随机源撞库——重新签发）",
            status_code=409,
            code="agent_key_conflict",
        ) from exc
    return {"key": plaintext, **_key_view(row, user_username=target["username"])}


@router.delete("/api/orgs/{org}/agent-keys/{key_id}", status_code=204)
async def revoke_agent_key(
    org: str,
    key_id: str,
    request: Request,
    auth: AuthContext = Depends(get_auth),
) -> None:
    """软撤销本组织 key → 204；不存在/跨组织 404 ``agent_key_not_found``。

    已撤销 → 幂等 204（store 原样返回既有行且**零新审计**）；撤销与
    ``agent_key.revoked`` 审计同事务。payload 只用请求路径/操作者——不在撤销前
    为补 user_id/label 回查 key 行（D26 阶段 2B 纪律）。
    """
    org = _manage_org(request, org, auth)
    backend = get_service(request).backend
    row = backend.revoke_agent_key(
        key_id=key_id,
        org_id=org,
        revoked_by=auth.user_id,
        audit=_audit_payload(EVENT_AGENT_KEY_REVOKED, {
            "actor": auth.user_id,
            "key_id": key_id,
            "org_id": org,
        }),
    )
    if row is None:
        raise AccountError(
            f"agent key not found: {key_id!r}", status_code=404,
            code="agent_key_not_found",
        )


__all__ = ["router"]
