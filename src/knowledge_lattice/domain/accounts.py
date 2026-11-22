"""本地账号域（D25 / FR-9 / m4-1——`LATTICE_AUTH_MODE=local` 的领域底座）。

设计口径（design §5.5 D25 块 + §4 users/user_invitations DDL）：

- **口令**：stdlib ``hashlib.scrypt``（n=16384, r=8, p=1, dklen=32, 16B 随机
  salt, maxmem=64MiB）；编码自描述 ``scrypt$n=…,r=…,p=…$<b64salt>$<b64hash>``
  （urlsafe base64、去 padding）——参数随串携带，未来调参不破坏旧 hash 校验；
  verify 对畸形/越界参数 fail-closed 返回 False（不抛、不做昂贵计算）；
- **会话**：HS256 JWT，独立 ``LATTICE_SESSION_SECRET``、``aud=knowledge-lattice-web``、
  ``typ=session``、``tv``（token_version）——claims ``sub/iat/exp/aud/typ/tv``；
  改密/重置 ``tv++`` 撤销旧会话（解码只验签，tv 比对在 ``authenticate_session``
  读库后做，停用/邀请态同样在库侧判定）；
- **登录限流**：进程内 dict + ``threading.Lock`` + ``time.monotonic()``（单进程
  零中间件——NFR；多实例共享限流为 known-gaps G-25 族）。窗口内失败累计到上限
  即锁定，锁定期 ``check`` 返回剩余秒数（向上取整）；锁到期/窗口外清零；
- **首启门禁**：``validate_local_auth_settings`` 在 ``create_app`` 开头 fail-closed
  ——local 形态必须有独立且非公开的 ``session_secret``（≥32 字节，不得等于
  dev JWT / mock-idp 的仓库公开缺省值）。

分层：本模块只依赖 domain/config/store 协议（``get_user_auth``），不写方言
SQL（§3——SQL 在 store/<dialect>）。密码/token 明文**永不**进日志/审计/错误消息。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import math
import re
import secrets
import threading
import time
import unicodedata

import jwt as pyjwt

from knowledge_lattice.config import DEFAULT_SSO_MOCK_SECRET, Settings
from knowledge_lattice.domain.auth import AuthContext, AuthError
from knowledge_lattice.store.taskclock import TS_FMT

# ============ 会话 token 契约（D25——design §5.5 local 块） ============

SESSION_AUDIENCE = "knowledge-lattice-web"
SESSION_TYP = "session"
SESSION_ALGORITHM = "HS256"
# 会话 secret 最小长度（字节——`validate_local_auth_settings` 启动即拒短值）
SESSION_SECRET_MIN_BYTES = 32

# dev JWT 的仓库公开缺省值（Settings 字段默认；与 DEFAULT_SSO_MOCK_SECRET 同属
# 公开常量——local 会话 secret 复用它们等于允许伪造任意本地会话）
_DEV_JWT_SECRET_DEFAULT = Settings.__dataclass_fields__["dev_jwt_secret"].default

# ============ 口令校验（D25——设计未冻结细则，保持宽松：只定长度/空白下限） ============


class WeakPasswordError(ValueError):
    """密码强度不足（API 映射 400 weak_password——m4-2）。"""

    def __init__(self, min_len: int, message: str | None = None) -> None:
        self.min_len = int(min_len)
        super().__init__(message or f"密码强度不足：至少 {self.min_len} 位")


def validate_password(password: str, min_len: int) -> None:
    """密码校验（通过返回 None，不通过抛 :class:`WeakPasswordError`）。

    细则（设计未冻结——保持宽松，不引入复杂度/字符种类强制）：
    - 长度 ≥ ``min_len``（按 Unicode 码点计）；``min_len`` 下限 8 由 config
      ``_validate`` 保证；
    - 不接受全空白密码（长度达标但 ``strip()`` 为空——防误填空格）。
    """
    if not isinstance(password, str):
        raise ValueError("password 必须为字符串")
    if len(password) < min_len:
        raise WeakPasswordError(min_len)
    if not password.strip():
        raise WeakPasswordError(min_len, message="密码不能全为空白字符")


# ============ 用户名/邮箱规范化（D25——username 登录键精确、email 非登录键） ============

USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 64


def validate_username(username: str) -> str:
    """username 规范化 + 校验：strip 后 3..64、不含空白/控制字符。

    设计未冻结字符集细则——保持宽松（不引入邮箱式限制，允许中文/`.`/`_` 等），
    只拒绝结构上不可用的值。返回 strip 后的规范值；非法抛 ``ValueError``
    （API 层映射 400——m4-2）。username 不做 lower（登录键精确，store 同口径）。
    """
    if not isinstance(username, str):
        raise ValueError("username 必须为字符串")
    normalized = username.strip()
    if not USERNAME_MIN_LEN <= len(normalized) <= USERNAME_MAX_LEN:
        raise ValueError(
            f"username 长度须为 {USERNAME_MIN_LEN}..{USERNAME_MAX_LEN} 个字符"
            "（首尾空白已去除）"
        )
    for ch in normalized:
        # 空白 + 控制/格式/代理字符（Cc/Cf/Cs——零宽/方向控制等不可见字符
        # 会造成用户名肉眼不可辨，结构上拒绝；其余字符集保持宽松）
        if ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf", "Cs"):
            raise ValueError("username 不得包含空白或控制字符")
    return normalized


def normalize_email(email: str | None) -> str | None:
    """email 归一：``strip().lower() or None``（store 同口径；NULL 不参与唯一）。

    设计口径 email 可选、不作登录键——不引入格式校验（避免管理员预登记
    被过度约束）；空/仅空白 → None。
    """
    if email is None:
        return None
    normalized = email.strip().lower()
    return normalized or None


# ============ scrypt 口令编码（stdlib——零中间件；参数自描述便于未来调参） ============

_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_SALT_BYTES = 16
_SCRYPT_MAXMEM = 64 * 1024 * 1024  # 64MiB（n=16384,r=8 需 16MiB——余量充足）

# verify 侧参数上界（task 契约）：越界 → False（不抛、不计算）
_MAX_N = 1 << 20
_MAX_R = 32
_MAX_P = 8
_MAX_DKLEN = 64

_PASSWORD_SCHEME = "scrypt"
_PASSWORD_HASH_RE = re.compile(
    r"^scrypt\$n=(?P<n>[0-9]+),r=(?P<r>[0-9]+),p=(?P<p>[0-9]+)"
    r"\$(?P<salt>[A-Za-z0-9_-]+)\$(?P<digest>[A-Za-z0-9_-]+)$"
)


def _b64encode(raw: bytes) -> str:
    """urlsafe base64（去 padding——编码串无 `=`，便于 env/URL 复制）。"""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    """严格 urlsafe base64 解码（bad padding/非法字符 → binascii.Error）。"""
    padded = text + "=" * (-len(text) % 4)
    return base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)


def hash_password(password: str) -> str:
    """scrypt 编码（每次随机 16B salt——相同口令两次 hash 不同）。

    输出 ``scrypt$n=16384,r=8,p=1$<b64salt>$<b64hash>``（urlsafe b64 去 padding）。
    密码明文不落任何返回值之外的载体（调用方只把编码串写库）。
    """
    if not isinstance(password, str):
        raise ValueError("password 必须为字符串")
    salt = secrets.token_bytes(_SCRYPT_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    return (
        f"{_PASSWORD_SCHEME}$n={_SCRYPT_N},r={_SCRYPT_R},p={_SCRYPT_P}"
        f"${_b64encode(salt)}${_b64encode(digest)}"
    )


def _parse_password_hash(encoded: object) -> tuple[int, int, int, bytes, bytes] | None:
    """解析 scrypt 编码串 → (n, r, p, salt, digest)；畸形/越界 → None。

    上界按契约：n ≤ 2^20（且须为 2 的幂——OpenSSL 硬要求）/ r ≤ 32 / p ≤ 8 /
    dklen ≤ 64；另做非空/下界 sanity（n ≥ 2、r/p ≥ 1、salt/digest 非空）。
    """
    if not isinstance(encoded, str):
        return None
    match = _PASSWORD_HASH_RE.match(encoded)
    if match is None:
        return None
    n = int(match.group("n"))
    r = int(match.group("r"))
    p = int(match.group("p"))
    if n < 2 or n > _MAX_N or n & (n - 1):
        return None
    if r < 1 or r > _MAX_R:
        return None
    if p < 1 or p > _MAX_P:
        return None
    try:
        salt = _b64decode(match.group("salt"))
        digest = _b64decode(match.group("digest"))
    except (binascii.Error, ValueError):
        return None
    if not 1 <= len(salt) <= 64:
        return None
    if not 1 <= len(digest) <= _MAX_DKLEN:
        return None
    return n, r, p, salt, digest


def verify_password(password: str, encoded: str) -> bool:
    """校验口令与编码串（畸形/越界参数 → False，不抛异常）。

    参数取自编码串（兼容未来调参）；``hmac.compare_digest`` 常量时间比对。
    scrypt 参数在内存上界内仍可能被 OpenSSL 拒绝（``ValueError``）——一并
    按校验失败处理，不让畸形库值打成 500。
    """
    if not isinstance(password, str) or not isinstance(encoded, str):
        return False
    parsed = _parse_password_hash(encoded)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    try:
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)


# ============ 本地会话 JWT（D25——独立 secret / aud / typ / tv） ============


def issue_session_token(
    settings: Settings, *, user_id: str, token_version: int
) -> tuple[str, str]:
    """签发本地会话 token → ``(token, expires_at)``。

    ``expires_at`` 为 UTC ``YYYY-MM-DD HH:MM:SS``（与 taskclock/CURRENT_TIMESTAMP
    同格式——API 响应与库内时间可比）；TTL 取 ``settings.session_ttl_s``
    （秒，截断取整——会话语义不依赖亚秒精度）。
    """
    if not user_id:
        raise ValueError("issue_session_token 需要非空 user_id")
    now = int(time.time())
    expires = now + int(settings.session_ttl_s)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": expires,
        "aud": SESSION_AUDIENCE,
        "typ": SESSION_TYP,
        "tv": int(token_version),
    }
    token = pyjwt.encode(payload, settings.session_secret, algorithm=SESSION_ALGORITHM)
    return token, time.strftime(TS_FMT, time.gmtime(expires))


def decode_session_token(settings: Settings, token: str) -> dict:
    """验签并校验本地会话 token → claims dict；任何不合法 → :class:`AuthError`。

    校验：HS256（``algorithms=["HS256"]`` 防 alg 混淆）、aud='knowledge-lattice-web'、
    require exp/iat/sub/aud/typ/tv、``typ == 'session'``、``tv`` 为 int（bool
    不算——JSON true 是 int 子类陷阱）、``sub`` 非空字符串。过期/签名错/结构
    缺失一律 401 语义；错误消息不回显 token 明文。
    """
    if not isinstance(token, str) or not token:
        raise AuthError("missing session token")
    if not settings.session_secret:
        # local 形态的启动守卫本应拦住（create_app）；直连 domain 的调用方
        # fail-closed——空密钥无法验签
        raise AuthError("local session secret 未配置（LATTICE_SESSION_SECRET）")
    try:
        claims = pyjwt.decode(
            token,
            settings.session_secret,
            algorithms=[SESSION_ALGORITHM],
            audience=SESSION_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "aud", "typ", "tv"]},
        )
    except pyjwt.PyJWTError as exc:
        raise AuthError(f"invalid session token: {exc}") from exc
    if claims.get("typ") != SESSION_TYP:
        raise AuthError("invalid session token: typ mismatch")
    token_version = claims.get("tv")
    if not isinstance(token_version, int) or isinstance(token_version, bool):
        raise AuthError("invalid session token: tv must be int")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AuthError("invalid session token: missing sub")
    return claims


# ============ 登录限流（进程内——单进程零中间件，G-25 族开放点） ============


class LoginRateLimiter:
    """登录失败限流/锁定（进程内共享态——username+IP 键由 API 层构造）。

    口径（D25/FR-9）：窗口 ``window_s`` 内失败累计到 ``max_fails`` → 锁定
    ``lock_s``；锁定期间 ``check`` 返回剩余秒数（向上取整）；锁定到期清零
    失败计数（重新给满额机会）；窗口外亦清零。线程锁内 read-modify-write
    （REST 同步依赖走线程池——与 ServiceRateLimiter 同因，P3-8）。

    ``now`` 可注入（``time.monotonic()`` 语义的秒数——仅测试用；生产不传）。
    """

    __slots__ = ("max_fails", "window_s", "lock_s", "_state", "_lock")

    def __init__(self, max_fails: int, window_s: float, lock_s: float) -> None:
        self.max_fails = max(1, int(max_fails))
        self.window_s = max(0.0, float(window_s))
        self.lock_s = max(0.0, float(lock_s))
        # key → (window_start, failures, locked_until|None)
        self._state: dict[str, tuple[float, int, float | None]] = {}
        self._lock = threading.Lock()

    def _now(self, now: float | None) -> float:
        return time.monotonic() if now is None else float(now)

    def check(self, key: str, *, now: float | None = None) -> int | None:
        """锁定中 → 剩余秒数（ceil ≥1）；否则 None（窗口外顺带清零失败计数）。"""
        with self._lock:
            current = self._now(now)
            entry = self._state.get(key)
            if entry is None:
                return None
            window_start, _, locked_until = entry
            if locked_until is not None:
                if current < locked_until:
                    return max(1, math.ceil(locked_until - current))
                # 锁定到期：清零失败计数（重新给满额窗口）
                del self._state[key]
                return None
            if current - window_start >= self.window_s:
                del self._state[key]
                return None
            return None

    def record_failure(self, key: str, *, now: float | None = None) -> None:
        """记一次失败；达到上限即进入锁定（锁定期间再失败不延长锁定）。"""
        with self._lock:
            current = self._now(now)
            entry = self._state.get(key)
            if entry is None:
                self._state[key] = (current, 1, None)
                return
            window_start, failures, locked_until = entry
            if locked_until is not None:
                if current < locked_until:
                    return  # 已锁定：不重复计数/不延长
                self._state[key] = (current, 1, None)
                return
            if current - window_start >= self.window_s:
                self._state[key] = (current, 1, None)
                return
            failures += 1
            if failures >= self.max_fails:
                self._state[key] = (window_start, failures, current + self.lock_s)
            else:
                self._state[key] = (window_start, failures, None)

    def reset(self, key: str) -> None:
        """登录成功/管理员解锁：清空该键的失败与锁定态。"""
        with self._lock:
            self._state.pop(key, None)


# ============ 本地会话认证（authenticate local 分支） ============


def authenticate_session(backend, settings: Settings, token: str) -> AuthContext:
    """本地会话 token → AuthContext（via='local'）。

    判定序（fail-closed）：解码验签 → ``get_user_auth`` → 用户不存在 /
    ``disabled_at`` 非空 / ``status != 'active'``（invited 不可登录）/
    ``tv`` 与库内 ``token_version`` 不等（改密/重置/停用撤销）→ AuthError(401)。
    成功时 ``org_claim=None``（local 会话不绑定组织——Web 侧按当前组织走
    ``X-Org-Id``，与 D18 组织上下文规则一致）。
    """
    claims = decode_session_token(settings, token)
    user_id = claims["sub"]
    user = backend.get_user_auth(user_id)
    if user is None:
        raise AuthError("unknown user")
    if user["disabled_at"] is not None:
        raise AuthError("user disabled")
    if user["status"] != "active":
        raise AuthError("user not active")
    if claims["tv"] != user["token_version"]:
        raise AuthError("session revoked")
    return AuthContext(
        user_id=user_id,
        org_claim=None,
        via="local",
        is_system_admin=bool(user["is_system_admin"]),
    )


# ============ 启动守卫（local 形态——create_app 开头 fail-closed） ============


def validate_local_auth_settings(settings: Settings) -> None:
    """local 形态启动校验（``create_app`` 开头调用；sso 形态不做任何要求）。

    - ``session_secret`` 非空且 ≥32 字节（HS256 密钥强度；缺失提示
      ``LATTICE_SESSION_SECRET``）；
    - 不得等于仓库公开缺省值（``Settings.dev_jwt_secret`` 默认 /
      ``DEFAULT_SSO_MOCK_SECRET``）——公开密钥等于允许伪造任意本地会话，
      与 dev JWT prod 禁用（P2-5）/ mock-idp prod 缺省拒绝（P2-2）同口径。

    非法 → ``ValueError``（启动即拒；消息不回显 secret 值）。
    """
    if settings.auth_mode != "local":
        return
    secret = settings.session_secret or ""
    if not secret:
        raise ValueError(
            "LATTICE_AUTH_MODE=local 须配置 LATTICE_SESSION_SECRET"
            "（≥32 字节随机串——本地会话 HS256 签名密钥）"
        )
    if len(secret.encode("utf-8")) < SESSION_SECRET_MIN_BYTES:
        raise ValueError(
            "LATTICE_SESSION_SECRET 过短（须 ≥32 字节——本地会话 HS256 签名密钥）"
        )
    if secret in (_DEV_JWT_SECRET_DEFAULT, DEFAULT_SSO_MOCK_SECRET):
        raise ValueError(
            "LATTICE_SESSION_SECRET 不得使用仓库公开的 dev 缺省密钥"
            "（dev JWT / mock-idp 公开值——公开密钥可伪造任意会话，启动即拒）"
        )


__all__ = [
    "SESSION_AUDIENCE",
    "SESSION_TYP",
    "SESSION_ALGORITHM",
    "SESSION_SECRET_MIN_BYTES",
    "WeakPasswordError",
    "validate_password",
    "validate_username",
    "normalize_email",
    "hash_password",
    "verify_password",
    "issue_session_token",
    "decode_session_token",
    "LoginRateLimiter",
    "authenticate_session",
    "validate_local_auth_settings",
]
