"""token→user 解析 + 组织上下文统一规则（design §3 domain/auth.py + §5.5）。

M0a 落（D18 骨架）：
- 开发 JWT：POST /api/dev/token 签发（HS256、claims sub/org、短 TTL）——仅 dev/test
  注册路由（生产 404，TC-AUTH-01④）；验签解析 sub/org claim；
- 静态 token：sha256(users.token_hash) 直查——仅开发/测试（含 CI，D18）；生产拒绝；
- 组织上下文统一规则（TC-AUTH-02）：MCP 委托 token org claim 优先 / 运行时注入
  X-Org-Id 头兜底；并存且不一致 → 400；缺失即 400（无隐式默认）；工具参数 org
  一律忽略并记审计（MCP server 侧处理）。

M2.2 生产化认证段（m2-4——TC-AUTH-03/04/05/T13）：
- SSO 验签 + JIT 建档（D16）：`sso` 验签器（协议中立可插拔——adapters/
  auth_sso.py）注入时优先走 IdP 验签 → sub 解析全局用户；首次登录 JIT 建档
  （users 自动落库，管理员不建账号只配授权），二次登录复用既有行；
- 委托 token（D18 主方案·RFC 8693）：aud=knowledge-lattice、sub=用户、act=
  agent 标识（string | object{"sub"}——链式取最外层 sub=current actor、全链
  进审计）、org claim 单值——按 sub 计权、act 进审计（双身份）；透传用户
  原始 token（aud 非本服务）→ 拒绝并审计（MCP 规范明令）；
- 可信子系统降级三约束（#33 P1-5/T13）：服务凭证白名单（allowed_orgs+按
  服务限流）+ X-On-Behalf-Of + 用户在场证据（sub 一致——防冒充离线用户），
  拒绝路径 outcome=refused 进审计。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass

import jwt as pyjwt

from knowledge_lattice.config import Settings

JWT_ALGORITHM = "HS256"
DEFAULT_SSO_AUDIENCE = "knowledge-lattice"  # 委托 token 受众（D18——可配覆盖）

# 请求体/工具参数权限字段识别键（FR-4/D18 v0.6.1 统一口径——附录 A-9：
# 忽略并记审计、请求正常处理；键集合按「权限声明」常见命名收敛，其余未知
# 字段本就不进业务模型——pydantic/MCP schema 天然忽略）
REQUEST_PERMISSION_FIELD_KEYS = frozenset(
    {"permissions", "roles", "acl", "grants", "scopes"}
)


class AuthError(Exception):
    """鉴权失败——code 为 HTTP 语义（401 未认证 / 403 越权 / 429 限流）。"""

    def __init__(self, message: str, *, code: int = 401) -> None:
        super().__init__(message)
        self.code = code


class OrgContextError(Exception):
    """组织上下文规则违例（400 语义——不一致/缺失）。"""


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    org_claim: str | None  # token org claim（单值——按组织签发）
    via: str  # jwt | static | sso | trusted
    is_system_admin: bool
    act: str | None = None  # 服务身份（委托 token act / 可信子系统 service_id；
    #  开发 JWT 同名 claim 承载；静态 token 无服务身份 → None=直连）


# ============ 开发 JWT（dev/test 签发与验签） ============


def issue_dev_jwt(
    settings: Settings,
    *,
    user_id: str,
    org: str | None = None,
    act: str | None = None,
) -> str:
    """开发 JWT 签发（sub/org/act——act 为服务身份，M1-3 委托 token act claim 的开发形态）。"""
    now = time.time()
    payload: dict[str, object] = {"sub": user_id, "iat": now, "exp": now + settings.jwt_ttl_s}
    if org:
        payload["org"] = org
    if act is not None:
        payload["act"] = act
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


# ============ 审计辅助（认证事件——m2-4；payload 原文进 detail_json） ============


def _audit(backend, event_type: str, payload: dict) -> None:
    """认证事件入 outbox（失败即传播——审计完整性优先，不静默吞）。"""
    backend.append_outbox(event_type, json.dumps(payload, ensure_ascii=False))


# ============ SSO/委托 token（TC-AUTH-03/04——m2-4 A1/A2/A3） ============


def resolve_act_claim(act: object) -> tuple[str, list[str]]:
    """RFC 8693 §4.1 act claim 形态解析 → (当前 agent 标识, 完整委托链)。

    - string：直接为 agent 标识（m1-3 既有形态）；
    - object：取顶层 ``sub``（string）为**当前 actor**——RFC 8693 MUST「只
      考虑 current actor（最外层），嵌套 prior actors 仅信息性」，完整链
      （最外→最内）进审计 payload ``act_chain`` 供追溯；
    - 其余形态（数字/缺 sub/sub 非字符串或空/list/bool）→ AuthError（拒绝
      并审计由调用方承载）。
    """
    if act is None:
        return "", []
    chain: list[str] = []
    node: object = act
    while True:
        if isinstance(node, str):
            if not node:
                raise AuthError("token act claim must not be empty")
            chain.append(node)
            return chain[0], chain
        if isinstance(node, dict):
            sub = node.get("sub")
            if not isinstance(sub, str) or not sub:
                raise AuthError(
                    "token act object requires string 'sub' (RFC 8693 §4.1)"
                )
            chain.append(sub)
            nxt = node.get("act")
            if nxt is None:
                return chain[0], chain
            node = nxt
            continue
        raise AuthError(
            "token act claim must be a string or an object with 'sub'"
            " (RFC 8693 §4.1)"
        )


def _authenticate_sso_claims(backend, settings: Settings, claims) -> AuthContext:
    """SSO/委托 token 验签通过后的语义校验 + JIT 建档 + 认证审计。

    SSO 拒绝面审计口径一致（P3-6）：audience_mismatch / missing_sub /
    invalid_act / user_disabled 全部留 ``auth.sso_refused``（reason 级）。
    """
    from knowledge_lattice.domain.audit_events import (
        EVENT_AUTH_DELEGATED,
        EVENT_AUTH_SSO_REFUSED,
        EVENT_AUTH_USER_JIT,
    )

    audience = settings.sso_audience or DEFAULT_SSO_AUDIENCE
    if audience not in claims.aud:
        # 透传用户原始 token（签给其他 client 的 token 原样转发）——MCP 规范
        # 明令拒绝；aud 非空但不含本服务即属此形态
        _audit(backend, EVENT_AUTH_SSO_REFUSED, {
            "user_id": claims.sub or None,
            "reason": "audience_mismatch",
            "aud": list(claims.aud),
            "expected": audience,
        })
        raise AuthError(
            f"token audience {list(claims.aud)} 不含本服务 {audience!r}"
            "（透传用户原始 token 拒绝——MCP 规范）"
        )
    if not claims.sub:
        _audit(backend, EVENT_AUTH_SSO_REFUSED, {
            "user_id": None, "reason": "missing_sub",
        })
        raise AuthError("token missing sub claim")
    try:
        act, act_chain = resolve_act_claim(claims.act)
    except AuthError as exc:
        _audit(backend, EVENT_AUTH_SSO_REFUSED, {
            "user_id": claims.sub,
            "reason": "invalid_act",
            "act": repr(claims.act),
            "error": str(exc),
        })
        raise
    # JIT 建档（D16：管理员不建账号只配授权——首次登录自动落库，二次复用）；
    # 建档与 JIT 审计**同事务**（P3-5——upsert audit= 先例：outbox 写失败即
    # 整体回滚，不出现「已建号但永久缺 JIT 事件」的半状态；复用路径 store
    # 侧不写审计）
    jit_event = json.dumps({
        "user_id": claims.sub,
        "username": claims.username or claims.sub,
        "display_name": claims.display_name,
    }, ensure_ascii=False)
    try:
        user = backend.upsert_user_jit(
            user_id=claims.sub,
            username=claims.username or claims.sub,
            display_name=claims.display_name,
            audit=(EVENT_AUTH_USER_JIT, jit_event),
        )
    except ValueError as exc:  # username 冲突（users.username UNIQUE）——fail-closed
        raise AuthError(str(exc)) from exc
    if user["disabled_at"] is not None:
        _audit(backend, EVENT_AUTH_SSO_REFUSED, {
            "user_id": claims.sub, "reason": "user_disabled",
        })
        raise AuthError(f"user disabled: {claims.sub}")
    if act:  # 委托 token：双身份审计（sub 计权 + act 进审计——TC-AUTH-04）
        _audit(backend, EVENT_AUTH_DELEGATED, {
            "user_id": claims.sub,
            "act": act,
            "act_chain": act_chain,
            "org": claims.org,
        })
    return AuthContext(
        user_id=claims.sub,
        org_claim=claims.org,
        via="sso",
        is_system_admin=user["is_system_admin"],
        act=act or None,
    )


# ============ 请求认证（SSO/委托优先 → dev JWT / 静态 token——后两者仅 dev/test） ============


def authenticate(backend, settings: Settings, token: str, *, sso=None) -> AuthContext:
    """Bearer token → AuthContext（用户须存在且未禁用）。

    - ``sso`` 验签器在场（auth 装配分层注入——m2-4 A5）：优先 IdP 验签——
      成功走 SSO/委托语义（aud 校验/act 解析/JIT 建档，TC-AUTH-03/04）；
      验签失败（非本 IdP 签发）落回后续分支（dev/test 下仍可用开发形态）；
    - dev/test：开发 JWT 验签（P2-5：prod **不进入该分支**——dev secret 默认
      值是仓库公开常量，prod 下验签等于允许伪造任意身份）；
    - 非 JWT 形态 → 按 sha256 查 users.token_hash（静态 token 同样仅 dev/test，
      生产拒绝——D18）；
    - 验签失败/未知用户/禁用 → 401。
    """
    if sso is not None:
        from knowledge_lattice.adapters.auth_sso import SsoVerificationError

        try:
            claims = sso.verify(token)
        except SsoVerificationError:
            claims = None  # 非本 IdP 签发 → dev/test 落回开发形态分支
        if claims is not None:
            return _authenticate_sso_claims(backend, settings, claims)
    claims: dict | None = None
    if settings.environment != "prod":  # P2-5：prod 不验 dev JWT（公开默认密钥可伪造）
        try:
            claims = decode_jwt(settings, token)
        except AuthError:
            claims = None
    if claims is not None:
        user_id = claims.get("sub")
        if not user_id:
            raise AuthError("token missing sub claim")
        act = claims.get("act")
        if act is not None and not isinstance(act, str):
            raise AuthError("token act claim must be a string")
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
            act=act,
        )
    if settings.environment == "prod":
        # P3-R2-3：对外文案不带内部审查号——语义（prod 停用 dev JWT/静态 token）不变
        raise AuthError(
            "production requires SSO/delegated token (M2)——dev JWT 与静态 token 均停用"
        )
    user = backend.find_user_by_token_hash(hash_token(token))
    if user is None:
        raise AuthError("invalid token")
    return AuthContext(
        user_id=user["id"], org_claim=None, via="static",
        is_system_admin=user["is_system_admin"], act=None,
    )


# ============ 可信子系统降级三约束（TC-AUTH-05/T13——m2-4 A4） ============


@dataclass(frozen=True)
class TrustedServiceEntry:
    """白名单条目（真实载体＝LATTICE_TRUSTED_SERVICES_JSON 配置——M1 dev 白名单
    模拟收口）。token 存 sha256（配置明文不落库）。"""

    service_id: str
    token_hash: str
    allowed_orgs: tuple[str, ...]
    rate_limit_rpm: int | None  # None=不限


class TrustedServiceRegistry:
    """服务凭证白名单（mTLS 形态归真实部署期——本段服务 token 形态）。

    自带进程内共享限流器（单进程零中间件——NFR；与条目同生命周期，REST/MCP
    请求路径不各自新建——否则按服务限流失效）。
    """

    def __init__(self, entries: tuple[TrustedServiceEntry, ...]) -> None:
        self.entries = entries
        self.rate_limiter = ServiceRateLimiter()

    @classmethod
    def from_json(cls, raw: str | None) -> "TrustedServiceRegistry":
        """JSON 数组解析（畸形 fail-closed raise ValueError——不静默忽略条目）。

        条目形态：{service_id, token, allowed_orgs: [org...], rate_limit_rpm?}。
        """
        if not raw:
            return cls(())
        items = json.loads(raw)
        if not isinstance(items, list):
            raise ValueError("trusted services 配置须为 JSON 数组")
        entries = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(
                    f"trusted services 条目须为对象（got {type(item).__name__}）"
                )
            service_id = item.get("service_id")
            token = item.get("token")
            orgs = item.get("allowed_orgs")
            if not isinstance(service_id, str) or not service_id:
                # P3-1：异常消息只带键名清单——条目值（含 token 明文）不进日志
                raise ValueError(
                    f"trusted services 条目缺 service_id（条目键：{sorted(item)}）"
                )
            if not isinstance(token, str) or not token:
                raise ValueError(f"trusted services 条目缺 token：{service_id!r}")
            if not isinstance(orgs, list) or not all(isinstance(o, str) for o in orgs):
                raise ValueError(
                    f"trusted services 条目 allowed_orgs 须为字符串数组：{service_id!r}"
                )
            rpm = item.get("rate_limit_rpm")
            if rpm is not None and (not isinstance(rpm, int) or rpm < 1):
                raise ValueError(
                    f"trusted services 条目 rate_limit_rpm 须为正整数：{service_id!r}"
                )
            entries.append(TrustedServiceEntry(
                service_id=service_id,
                token_hash=hash_token(token),
                allowed_orgs=tuple(orgs),
                rate_limit_rpm=rpm,
            ))
        return cls(tuple(entries))

    def match(self, token_hash: str) -> TrustedServiceEntry | None:
        for entry in self.entries:
            if entry.token_hash == token_hash:
                return entry
        return None


class ServiceRateLimiter:
    """按服务固定窗口限流（单进程内存态——NFR 零中间件；窗口内请求数上限）。

    计数路径持线程锁（P3-8：REST/MCP 同步依赖走线程池，read-modify-write
    丢计数会超发放行；锁下计数精确）。进程内态不改（多实例共享限流为
    known-gaps G-25 架构项——重开条件=多实例部署）。
    """

    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, service_id: str, limit: int, *, now: float | None = None) -> bool:
        """窗口内计数放行；超限拒绝。被拒请求不重置窗口（计数不回退）。"""
        with self._lock:
            now = time.monotonic() if now is None else now
            window_start, count = self._windows.get(service_id, (now, 0))
            if now - window_start >= 60.0:  # 固定 60s 窗口（rpm 语义）
                window_start, count = now, 0
            allowed = count < limit
            if allowed:
                self._windows[service_id] = (window_start, count + 1)
            else:
                self._windows[service_id] = (window_start, count)
            return allowed


def authenticate_trusted(
    backend,
    *,
    service_token: str,
    on_behalf_of: str | None,
    user_assertion: str | None,
    org: str | None,
    sso,
    registry: TrustedServiceRegistry | None,
    limiter: ServiceRateLimiter | None = None,
) -> AuthContext:
    """可信子系统降级三约束判定（#33 P1-5/T13——拒绝路径 outcome=refused 进审计）。

    判定序（fail-closed）：④白名单匹配 → 在场证据在场且验签 → ③sub 与
    X-On-Behalf-Of 一致 → 声明用户已建档未禁用 → ②org ∈ allowed_orgs →
    按服务限流 → ①按声明用户计权、双身份（service+user）审计 accepted。

    - 在场证据是身份断言（用户签给 agent client 的 id_token）——验签但不做
      本服务 aud 校验（断言非访问 token；exp 验签照常）；``Bearer `` 前缀
      大小写不敏感（P3-3）；
    - org 缺失 → OrgContextError（D18 无隐式默认）；
    - 未配置白名单（registry None/空）→ 可信子系统整体关闭（401）。
    """
    from knowledge_lattice.adapters.auth_sso import SsoVerificationError
    from knowledge_lattice.domain.audit_events import EVENT_AUTH_TRUSTED_SUBSYSTEM

    # 限流器共享态优先级：显式传入（测试）> registry 自带（请求路径——进程内
    # 按服务共享窗口）> 独立实例（无 registry 形态的兜底）
    limiter = limiter or (
        registry.rate_limiter if registry is not None else ServiceRateLimiter()
    )

    def _refuse(reason: str, *, code: int, service_id: str | None,
                user_id: str | None, org_id: str | None = None) -> AuthError:
        _audit(backend, EVENT_AUTH_TRUSTED_SUBSYSTEM, {
            "outcome": "refused",
            "reason": reason,
            "service_id": service_id,
            "user_id": user_id,
            "org": org_id,
        })
        return AuthError(
            f"trusted subsystem refused: {reason}（service={service_id!r}"
            f" user={user_id!r}）",
            code=code,
        )

    # ④ 白名单外 / 未配置白名单
    if registry is None or not registry.entries:
        raise _refuse("no_whitelist", code=401, service_id=None,
                      user_id=on_behalf_of, org_id=org)
    entry = registry.match(hash_token(service_token))
    if entry is None:
        raise _refuse("unknown_service", code=401, service_id=None,
                      user_id=on_behalf_of, org_id=org)
    # 约束②：用户在场证据（防服务凭证冒充离线用户）
    if not on_behalf_of:
        raise _refuse("missing_on_behalf_of", code=401,
                      service_id=entry.service_id, user_id=None, org_id=org)
    if not user_assertion:
        raise _refuse("missing_user_assertion", code=401,
                      service_id=entry.service_id, user_id=on_behalf_of, org_id=org)
    if sso is None:
        raise _refuse("no_sso_verifier", code=401,
                      service_id=entry.service_id, user_id=on_behalf_of, org_id=org)
    raw_assertion = user_assertion.strip()
    if raw_assertion.lower().startswith("bearer "):  # P3-3：大小写不敏感裁前缀
        raw_assertion = raw_assertion[7:].strip()
    try:
        assertion_claims = sso.verify(raw_assertion)
    except SsoVerificationError as exc:
        _audit(backend, EVENT_AUTH_TRUSTED_SUBSYSTEM, {
            "outcome": "refused", "reason": "invalid_user_assertion",
            "service_id": entry.service_id, "user_id": on_behalf_of, "org": org,
        })
        raise AuthError(
            f"trusted subsystem refused: invalid_user_assertion"
            f"（service={entry.service_id!r} user={on_behalf_of!r}）: {exc}"
        ) from exc
    # ③ 冒充：在场证据 sub 与声明用户不符
    if assertion_claims.sub != on_behalf_of:
        raise _refuse("subject_mismatch", code=403,
                      service_id=entry.service_id, user_id=on_behalf_of, org_id=org)
    # 声明用户须已建档（SSO 登录过）且未禁用——按其计权
    user = backend.get_user_auth(on_behalf_of)
    if user is None:
        raise _refuse("unknown_user", code=403,
                      service_id=entry.service_id, user_id=on_behalf_of, org_id=org)
    if user["disabled_at"] is not None:
        raise _refuse("user_disabled", code=401,
                      service_id=entry.service_id, user_id=on_behalf_of, org_id=org)
    # ② org 越界（org 缺失 → 400，D18 无隐式默认）
    if org is None:
        raise OrgContextError(
            "org 上下文缺失：X-Org-Id 头必填（可信子系统——D18 无隐式默认）"
        )
    if org not in entry.allowed_orgs:
        raise _refuse("org_not_allowed", code=403,
                      service_id=entry.service_id, user_id=on_behalf_of, org_id=org)
    # ① 白名单条目按服务限流（校验通过后计数——被拒请求不占合法配额）
    if entry.rate_limit_rpm is not None and not limiter.allow(
        entry.service_id, entry.rate_limit_rpm
    ):
        raise _refuse("rate_limited", code=429,
                      service_id=entry.service_id, user_id=on_behalf_of, org_id=org)
    _audit(backend, EVENT_AUTH_TRUSTED_SUBSYSTEM, {
        "outcome": "accepted",
        "service_id": entry.service_id,
        "user_id": on_behalf_of,
        "org": org,
    })
    return AuthContext(
        user_id=on_behalf_of,
        org_claim=org,
        via="trusted",
        is_system_admin=user["is_system_admin"],
        act=entry.service_id,
    )


# ============ 请求体权限字段（FR-4/D18 v0.6.1 统一口径——附录 A-9） ============


def audit_ignored_permission_fields(backend, *, user_id: str,
                                    present_fields: list[str]) -> None:
    """请求体/工具参数权限字段在场 → 忽略并记审计（请求正常处理——不计权
    变化）。由 api/mcp 层在识别到场后调用（识别钉在 api/mcp——§3）。"""
    if not present_fields:
        return
    from knowledge_lattice.domain.audit_events import (
        EVENT_AUTH_PERMISSIONS_IGNORED,
    )

    _audit(backend, EVENT_AUTH_PERMISSIONS_IGNORED, {
        "user_id": user_id,
        "ignored_fields": present_fields,
    })


# ============ 组织上下文统一规则（§5.5——claim 优先 / 头兜底 / 不一致·缺失 400） ============


def resolve_org(*, org_claim: str | None, org_header: str | None) -> str:
    """无 org 路径段 REST 端点与 MCP 的统一解析（v0.9.4 口径）：claim 与注入头
    并存且不一致 → 400；缺失 → 400（无隐式默认）。"""
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
