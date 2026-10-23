"""token→user 解析 + 组织上下文统一规则（design §3 domain/auth.py + §5.5）。

M0a 落（D18 骨架）：
- 开发 JWT：POST /api/dev/token 签发（HS256、claims sub/org、短 TTL）——仅 dev/test
  注册路由（生产 404，TC-AUTH-01④）；验签解析 sub/org claim；
- 静态 token：sha256(users.token_hash) 直查——仅开发/测试（含 CI，D18）；生产拒绝；
- 组织上下文统一规则（TC-AUTH-02）：MCP 委托 token org claim 优先 / 运行时注入
  X-Org-Id 头兜底；并存且不一致 → 400；缺失即 400（无隐式默认）；工具参数 org
  一律忽略并记审计（MCP server 侧处理）。

SSO 验签 / JIT 建档 / 委托 token 完整语义随 M2（TC-AUTH-03~05）。
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import jwt as pyjwt

from knowledge_lattice.config import Settings

JWT_ALGORITHM = "HS256"


class AuthError(Exception):
    """鉴权失败——code 为 HTTP 语义（401 未认证 / 403 越权）。"""

    def __init__(self, message: str, *, code: int = 401) -> None:
        super().__init__(message)
        self.code = code


class OrgContextError(Exception):
    """组织上下文规则违例（400 语义——不一致/缺失）。"""


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    org_claim: str | None  # token org claim（单值——按组织签发）
    via: str  # jwt | static
    is_system_admin: bool


# ============ 开发 JWT（dev/test 签发与验签） ============


def issue_dev_jwt(settings: Settings, *, user_id: str, org: str | None = None) -> str:
    now = time.time()
    payload: dict[str, object] = {"sub": user_id, "iat": now, "exp": now + settings.jwt_ttl_s}
    if org:
        payload["org"] = org
    return pyjwt.encode(payload, settings.dev_jwt_secret, algorithm=JWT_ALGORITHM)


def decode_jwt(settings: Settings, token: str) -> dict:
    """验签并解码（签名不符/过期 → AuthError 401）。"""
    try:
        return pyjwt.decode(token, settings.dev_jwt_secret, algorithms=[JWT_ALGORITHM])
    except pyjwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc


def hash_token(token: str) -> str:
    """静态 token → sha256 hex（users.token_hash 存储与比对形态）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ============ 请求认证（Bearer JWT 优先 / 静态 token 兜底——静态仅 dev/test） ============


def authenticate(backend, settings: Settings, token: str) -> AuthContext:
    """Bearer token → AuthContext（用户须存在且未禁用）。

    - 非 JWT 形态 → 按 sha256 查 users.token_hash（生产环境拒绝——D18 静态 token
      仅开发/测试与 CI）；
    - JWT 验签失败 → 401。
    """
    try:
        claims = decode_jwt(settings, token)
    except AuthError:
        if settings.environment == "prod":
            raise AuthError("static token auth disabled in production (D18)")
        user = backend.find_user_by_token_hash(hash_token(token))
        if user is None:
            raise AuthError("invalid token")
        return AuthContext(
            user_id=user["id"], org_claim=None, via="static",
            is_system_admin=user["is_system_admin"],
        )
    user_id = claims.get("sub")
    if not user_id:
        raise AuthError("token missing sub claim")
    user = backend.get_user_auth(user_id)
    if user is None:
        raise AuthError(f"unknown user: {user_id}")
    if user["disabled_at"] is not None:
        raise AuthError(f"user disabled: {user_id}")
    return AuthContext(
        user_id=user_id,
        org_claim=claims.get("org"),
        via="jwt",
        is_system_admin=user["is_system_admin"],
    )


# ============ 组织上下文统一规则（§5.5——claim 优先 / 头兜底 / 不一致·缺失 400） ============


def resolve_org(*, org_claim: str | None, org_header: str | None) -> str:
    """MCP/检索端点统一解析：claim 与注入头并存且不一致 → 400；缺失 → 400。"""
    if org_claim is not None and org_header is not None and org_claim != org_header:
        raise OrgContextError(
            f"org claim {org_claim!r} 与 X-Org-Id {org_header!r} 不一致（D18 统一规则）"
        )
    org = org_claim or org_header
    if not org:
        raise OrgContextError("org 上下文缺失：token org claim 或 X-Org-Id 头必填其一（无隐式默认）")
    return org


def check_path_org(*, path_org: str, org_header: str | None) -> str:
    """REST 组织作用域路径（/api/orgs/{org}/...）：路径 org 与头并存且不一致 → 400
    （§6.2——头缺失时以路径为准）。"""
    if org_header is not None and path_org != org_header:
        raise OrgContextError(
            f"路径 org {path_org!r} 与 X-Org-Id {org_header!r} 不一致（D18 统一规则）"
        )
    return path_org
