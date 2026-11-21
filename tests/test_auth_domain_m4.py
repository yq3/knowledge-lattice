"""M4 m4-1b 本地账号领域层（D25 / FR-9——config + domain/accounts + authenticate local 分支）。

覆盖：
- scrypt 编码格式/随机盐/正确与错误密码/畸形与越界参数（fail-closed 不抛）；
- session JWT round-trip + aud/typ/tv/exp/sub 篡改/签名错均 AuthError；
- validate_password / validate_username / normalize_email 边界；
- LoginRateLimiter 窗口、锁定、剩余秒（向上取整）、reset、锁到期清零；
- config `_validate`/`get_settings` env 读取与非法值 fail-closed；
- `validate_local_auth_settings` 缺失/过短/公开 secret 拒绝，sso 形态不受影响；
- `create_app` local 短 secret → ValueError；合法 secret → 服务可装配（sso 恒 None、
  login_limiter 驻 ServiceContext）；
- store 双后端：authenticate_session 成功/tv 不匹配/disabled/invited/未知用户；
  authenticate local 分支识别 session token、sso 形态不识别（dev JWT 落回语义）；
- 审计常量登记（`__all__` 单一登记处）。
"""

from __future__ import annotations

import base64
import calendar
import re
import time
from datetime import datetime

import jwt as pyjwt
import pytest

from knowledge_lattice.adapters.auth_sso import MockIdpVerifier, SsoClaims
from knowledge_lattice.config import DEFAULT_SSO_MOCK_SECRET, Settings, get_settings
from knowledge_lattice.domain import audit_events
from knowledge_lattice.domain.accounts import (
    SESSION_AUDIENCE,
    SESSION_TYP,
    LoginRateLimiter,
    WeakPasswordError,
    authenticate_session,
    decode_session_token,
    hash_password,
    issue_session_token,
    normalize_email,
    validate_local_auth_settings,
    validate_password,
    validate_username,
    verify_password,
)
from knowledge_lattice.domain.auth import (
    AuthError,
    _authenticate_sso_claims,
    authenticate,
    issue_dev_jwt,
)
from knowledge_lattice.store.taskclock import TS_FMT

# 测试专用 secret（≥32 字节；不等于 dev JWT / mock-idp 公开缺省值）
SESSION_SECRET = "unit-local-session-secret-0123456789abcdef"
SSO_SECRET = "unit-sso-secret-0123456789abcdef012"


def _local_settings(tmp_path, **overrides) -> Settings:
    overrides.setdefault("auth_mode", "local")
    overrides.setdefault("session_secret", SESSION_SECRET)
    return Settings(environment="test", data_dir=tmp_path, **overrides)


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ============ scrypt 口令编码（hash_password / verify_password） ============


def test_password_hash_format_and_random_salt() -> None:
    """编码格式 `scrypt$n=16384,r=8,p=1$<b64salt>$<b64hash>`；盐随机（两次不同）。"""
    encoded = hash_password("correct-horse-battery")
    match = re.fullmatch(
        r"scrypt\$n=16384,r=8,p=1\$([A-Za-z0-9_-]+)\$([A-Za-z0-9_-]+)", encoded
    )
    assert match is not None, encoded
    salt = _b64decode(match.group(1))
    digest = _b64decode(match.group(2))
    assert len(salt) == 16  # 16B 随机盐
    assert len(digest) == 32  # dklen=32
    assert "=" not in match.group(1) + match.group(2)  # urlsafe b64 去 padding（编码自洽）

    second = hash_password("correct-horse-battery")
    assert second != encoded, "每次 salt 随机——相同口令 hash 不得相同"
    assert verify_password("correct-horse-battery", encoded) is True
    assert verify_password("correct-horse-battery", second) is True


def test_password_verify_wrong_password_false() -> None:
    encoded = hash_password("correct-horse-battery")
    assert verify_password("wrong-password", encoded) is False
    assert verify_password("", encoded) is False
    assert verify_password("correct-horse-battery ", encoded) is False


@pytest.mark.parametrize(
    "encoded",
    [
        None,
        123,
        "",
        "not-a-hash",
        "bcrypt$n=16384,r=8,p=1$AAAA$BBBB",  # 非 scrypt scheme
        "scrypt$n=16384,r=8$AAAA$BBBB",  # 缺 p 参数
        "scrypt$n=16384,r=8,p=1$x$BBBB",  # salt 非法 base64 字符
        "scrypt$n=16384,r=8,p=1$AAAA",  # 缺 hash 段
        "scrypt$n=16384,r=8,p=1$AAAA$",  # 空 hash
        "scrypt$n=0,r=8,p=1$AAAA$BBBB",  # n 越下界
        "scrypt$n=16385,r=8,p=1$AAAA$BBBB",  # n 非 2 的幂
        f"scrypt$n={1 << 21},r=8,p=1$AAAA$BBBB",  # n > 2^20
        "scrypt$n=16384,r=33,p=1$AAAA$BBBB",  # r > 32
        "scrypt$n=16384,r=8,p=9$AAAA$BBBB",  # p > 8
        f"scrypt$n=16384,r=8,p=1$AAAA${'A' * 88}",  # dklen=66 > 64
    ],
)
def test_password_verify_malformed_fails_closed(encoded) -> None:
    """畸形/越界参数 → False（不抛、不做昂贵计算——fail-closed）。"""
    assert verify_password("whatever", encoded) is False


# ============ validate_password / validate_username / normalize_email ============


def test_validate_password_boundaries() -> None:
    validate_password("a" * 10, 10)  # 恰好达标
    validate_password("密" * 10, 10)  # Unicode 码点计数
    with pytest.raises(WeakPasswordError) as excinfo:
        validate_password("a" * 9, 10)
    assert excinfo.value.min_len == 10
    assert "10" in str(excinfo.value)
    with pytest.raises(WeakPasswordError):
        validate_password(" " * 10, 10)  # 全空白（长度达标但无有效字符）
    with pytest.raises(ValueError):
        validate_password(None, 10)  # type: ignore[arg-type]


def test_validate_username_normalizes_and_rejects() -> None:
    assert validate_username("  alice  ") == "alice"
    assert validate_username("a" * 64) == "a" * 64
    assert validate_username("张三丰") == "张三丰"  # 宽松：允许 Unicode
    assert validate_username("zhang.san_1") == "zhang.san_1"
    for bad in (
        "", "   ", "ab", "a" * 65, "ali ce", "ali\tce", "ali\x00ce",
        "ali\u200bce",  # 零宽字符（Cf——肉眼不可辨）
        None,
    ):
        with pytest.raises(ValueError):
            validate_username(bad)


def test_normalize_email() -> None:
    assert normalize_email("  Foo@Example.COM ") == "foo@example.com"
    assert normalize_email("") is None
    assert normalize_email("   ") is None
    assert normalize_email(None) is None


# ============ session JWT（issue/decode） ============

_MISSING = object()


def _manual_token(settings: Settings, **overrides) -> str:
    now = int(time.time())
    payload: dict[str, object] = {
        "sub": "u1",
        "iat": now,
        "exp": now + 60,
        "aud": SESSION_AUDIENCE,
        "typ": SESSION_TYP,
        "tv": 0,
    }
    for key, value in overrides.items():
        if value is _MISSING:
            payload.pop(key, None)
        else:
            payload[key] = value
    return pyjwt.encode(payload, settings.session_secret, algorithm="HS256")


def test_session_token_round_trip(tmp_path) -> None:
    settings = _local_settings(tmp_path, session_ttl_s=1234)
    before = int(time.time())
    token, expires_at = issue_session_token(settings, user_id="u1", token_version=3)
    claims = decode_session_token(settings, token)
    assert claims["sub"] == "u1"
    assert claims["aud"] == SESSION_AUDIENCE
    assert claims["typ"] == SESSION_TYP
    assert claims["tv"] == 3
    # expires_at = UTC `YYYY-MM-DD HH:MM:SS`（taskclock 同格式），与 exp 同秒
    parsed = datetime.strptime(expires_at, TS_FMT)
    assert calendar.timegm(parsed.timetuple()) == claims["exp"]
    assert before + 1234 <= claims["exp"] <= int(time.time()) + 1234


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "knowledge-lattice"},  # 受众错（委托 token 受众/其他服务）
        {"aud": _MISSING},  # 缺 aud
        {"typ": "access"},  # typ 非 session
        {"typ": _MISSING},  # 缺 typ
        {"tv": "0"},  # tv 非 int
        {"tv": True},  # bool 是 int 子类——必须拒绝
        {"tv": _MISSING},  # 缺 tv
        {"exp": _MISSING},  # 缺 exp
        {"iat": _MISSING},  # 缺 iat
        {"exp": int(time.time()) - 10},  # 已过期
        {"sub": _MISSING},  # 缺 sub
        {"sub": 42},  # sub 非字符串
    ],
)
def test_session_token_tampering_rejected(tmp_path, overrides) -> None:
    settings = _local_settings(tmp_path)
    token = _manual_token(settings, **overrides)
    with pytest.raises(AuthError) as excinfo:
        decode_session_token(settings, token)
    assert excinfo.value.code == 401


def test_session_token_wrong_secret_rejected(tmp_path) -> None:
    settings = _local_settings(tmp_path)
    other = _local_settings(tmp_path, session_secret="another-session-secret-0123456789abcd")
    token, _ = issue_session_token(other, user_id="u1", token_version=0)
    with pytest.raises(AuthError):
        decode_session_token(settings, token)


def test_session_token_empty_secret_rejected(tmp_path) -> None:
    settings = Settings(environment="test", data_dir=tmp_path)  # sso 默认空 secret
    with pytest.raises(AuthError):
        decode_session_token(settings, "anything")


# ============ LoginRateLimiter ============


def test_login_rate_limiter_lock_and_remaining_seconds() -> None:
    limiter = LoginRateLimiter(max_fails=5, window_s=900, lock_s=600)
    key = "alice|127.0.0.1"
    assert limiter.check(key, now=0.0) is None
    for _ in range(4):
        limiter.record_failure(key, now=0.0)
    assert limiter.check(key, now=0.0) is None, "未达上限不锁"
    limiter.record_failure(key, now=0.0)  # 第 5 次 → 锁定
    assert limiter.check(key, now=0.0) == 600
    # 剩余秒数向上取整（299.5 → 300；0.8 → 1）
    assert limiter.check(key, now=300.5) == 300
    assert limiter.check(key, now=599.2) == 1
    # 锁定期间再失败不延长锁定
    limiter.record_failure(key, now=300.5)
    assert limiter.check(key, now=599.0) == 1
    # 锁到期：清零失败计数（不沿用旧计数直接二次锁定）
    assert limiter.check(key, now=600.0) is None
    limiter.record_failure(key, now=601.0)
    assert limiter.check(key, now=601.0) is None


def test_login_rate_limiter_window_resets_failures() -> None:
    limiter = LoginRateLimiter(max_fails=5, window_s=900, lock_s=600)
    key = "bob|10.0.0.1"
    for _ in range(4):
        limiter.record_failure(key, now=0.0)
    assert limiter.check(key, now=899.9) is None
    assert limiter.check(key, now=900.0) is None, "窗口外清零失败计数"
    # 窗口清后重新给满额：再失败 4 次仍不锁（若未清零，4+4=8 ≥ 5 会锁）
    for _ in range(4):
        limiter.record_failure(key, now=900.0)
    assert limiter.check(key, now=900.0) is None


def test_login_rate_limiter_reset() -> None:
    limiter = LoginRateLimiter(max_fails=2, window_s=900, lock_s=600)
    key = "carol|10.0.0.2"
    limiter.record_failure(key, now=0.0)
    limiter.record_failure(key, now=0.0)
    assert limiter.check(key, now=0.0) == 600
    limiter.reset(key)  # 登录成功/管理员解锁
    assert limiter.check(key, now=0.0) is None
    limiter.record_failure(key, now=0.0)
    assert limiter.check(key, now=0.0) is None, "reset 后计数从零开始"


# ============ config（get_settings / _validate） ============


def test_settings_defaults_auth_mode_sso() -> None:
    """现有 `Settings()` 不传新字段仍可用且默认 sso（零行为变化）。"""
    settings = Settings()
    assert settings.auth_mode == "sso"
    assert settings.session_secret == ""
    assert settings.session_ttl_s == 12 * 3600
    assert settings.init_password == ""
    assert settings.invite_ttl_s == 72 * 3600
    assert settings.login_max_fails == 5
    assert settings.login_window_s == 900
    assert settings.login_lock_s == 600
    assert settings.password_min_len == 10


def test_get_settings_reads_auth_env(monkeypatch) -> None:
    monkeypatch.setenv("LATTICE_AUTH_MODE", "local")
    monkeypatch.setenv("LATTICE_SESSION_SECRET", SESSION_SECRET)
    monkeypatch.setenv("LATTICE_SESSION_TTL_S", "60")
    monkeypatch.setenv("LATTICE_INIT_PASSWORD", "init-password-1")
    monkeypatch.setenv("LATTICE_INVITE_TTL_S", "120")
    monkeypatch.setenv("LATTICE_LOGIN_MAX_FAILS", "3")
    monkeypatch.setenv("LATTICE_LOGIN_WINDOW_S", "30")
    monkeypatch.setenv("LATTICE_LOGIN_LOCK_S", "45")
    monkeypatch.setenv("LATTICE_PASSWORD_MIN_LEN", "12")
    settings = get_settings()
    assert settings.auth_mode == "local"
    assert settings.session_secret == SESSION_SECRET
    assert settings.session_ttl_s == 60.0
    assert settings.init_password == "init-password-1"
    assert settings.invite_ttl_s == 120.0
    assert settings.login_max_fails == 3
    assert settings.login_window_s == 30.0
    assert settings.login_lock_s == 45.0
    assert settings.password_min_len == 12


@pytest.mark.parametrize(
    ("env_key", "env_value"),
    [
        ("LATTICE_AUTH_MODE", "hybrid"),  # 非法枚举
        ("LATTICE_PASSWORD_MIN_LEN", "7"),  # 低于 8
        ("LATTICE_LOGIN_MAX_FAILS", "0"),  # 低于 1
        ("LATTICE_SESSION_TTL_S", "-1"),  # 负值
        ("LATTICE_INVITE_TTL_S", "-1"),
        ("LATTICE_LOGIN_WINDOW_S", "-0.5"),
        ("LATTICE_LOGIN_LOCK_S", "-1"),
    ],
)
def test_get_settings_rejects_invalid_auth_config(monkeypatch, env_key, env_value) -> None:
    monkeypatch.setenv(env_key, env_value)
    with pytest.raises(ValueError):
        get_settings()


def test_validate_local_auth_settings_rejects_missing_and_short(tmp_path) -> None:
    with pytest.raises(ValueError, match="LATTICE_SESSION_SECRET"):
        validate_local_auth_settings(
            Settings(environment="test", data_dir=tmp_path, auth_mode="local")
        )
    with pytest.raises(ValueError, match="LATTICE_SESSION_SECRET"):
        validate_local_auth_settings(
            Settings(
                environment="test", data_dir=tmp_path, auth_mode="local",
                session_secret="x" * 31,  # 31 字节 < 32
            )
        )
    # 恰好 32 字节通过
    validate_local_auth_settings(
        Settings(
            environment="test", data_dir=tmp_path, auth_mode="local",
            session_secret="x" * 32,
        )
    )


def test_validate_local_auth_settings_rejects_public_defaults(tmp_path) -> None:
    """不得复用仓库公开缺省密钥（dev JWT / mock-idp——公开值等于可伪造会话）。"""
    for secret in (Settings().dev_jwt_secret, DEFAULT_SSO_MOCK_SECRET):
        with pytest.raises(ValueError, match="公开"):
            validate_local_auth_settings(
                Settings(
                    environment="test", data_dir=tmp_path, auth_mode="local",
                    session_secret=secret,
                )
            )


def test_validate_local_auth_settings_ignores_sso_mode(tmp_path) -> None:
    """sso 形态不做任何要求（空/短/公开 secret 均不拒——现状零变化）。"""
    for secret in ("", "short", Settings().dev_jwt_secret, DEFAULT_SSO_MOCK_SECRET):
        validate_local_auth_settings(
            Settings(environment="test", data_dir=tmp_path, auth_mode="sso",
                     session_secret=secret)
        )


# ============ create_app 装配（local 守卫 / ServiceContext） ============


def _app_kwargs():
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from fake_providers import FakeEmbedder

    return dict(embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
                run_startup_probe=False)


def test_create_app_local_short_secret_rejected(tmp_path) -> None:
    from knowledge_lattice.app import create_app

    settings = Settings(
        environment="test", data_dir=tmp_path, auth_mode="local",
        session_secret="too-short", probe_interval_s=0,
        maintenance_interval_s=0, worker_mode="inline",
    )
    with pytest.raises(ValueError, match="LATTICE_SESSION_SECRET"):
        create_app(settings, **_app_kwargs())


def test_create_app_local_valid_secret_assembles_local_service(tmp_path) -> None:
    """合法 secret → app 可创建（TestClient 起停）；local 形态 sso 恒 None
    （显式注入的 sso_verifier 被忽略——D25 关闭 SSO/JIT）；login_limiter 驻
    ServiceContext（m4-2 消费）。"""
    from fastapi.testclient import TestClient

    from knowledge_lattice.app import create_app

    settings = Settings(
        environment="test", data_dir=tmp_path, auth_mode="local",
        session_secret=SESSION_SECRET, session_ttl_s=12 * 3600,
        login_max_fails=4, login_window_s=30, login_lock_s=20,
        probe_interval_s=0, maintenance_interval_s=0, worker_mode="inline",
        embed_dim=2560,
    )
    app = create_app(settings, sso_verifier=object(), **_app_kwargs())
    service = app.state.service
    assert service.sso is None, "local 形态不得构造/注入 SSO 验签器（D25）"
    assert isinstance(service.login_limiter, LoginRateLimiter)
    assert service.login_limiter.max_fails == 4
    assert service.login_limiter.window_s == 30.0
    assert service.login_limiter.lock_s == 20.0
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200


# ============ 审计常量登记 ============


def test_local_account_audit_constants_registered() -> None:
    expected = {
        "EVENT_AUTH_LOGIN": "auth.login",
        "EVENT_AUTH_LOGIN_REFUSED": "auth.login_refused",
        "EVENT_AUTH_LOGOUT": "auth.logout",
        "EVENT_AUTH_PASSWORD_CHANGED": "auth.password_changed",
        "EVENT_AUTH_PASSWORD_RESET": "auth.password_reset",
        "EVENT_AUTH_INVITE_CREATED": "auth.invite_created",
        "EVENT_AUTH_INVITE_ACCEPTED": "auth.invite_accepted",
        "EVENT_AUTH_INVITE_REVOKED": "auth.invite_revoked",
        "EVENT_USER_CREATED": "user.created",
        "EVENT_USER_DISABLED": "user.disabled",
        "EVENT_USER_ENABLED": "user.enabled",
        "EVENT_USER_SYSADMIN_CHANGED": "user.sysadmin_changed",
        "EVENT_INSTANCE_SETUP": "instance.setup",
    }
    for name, value in expected.items():
        assert getattr(audit_events, name) == value
        assert name in audit_events.__all__
    assert len(audit_events.__all__) == len(set(audit_events.__all__)), "登记表无重复"


# ============ store 双后端：authenticate_session / authenticate local 分支 ============


def _create_local_user(
    backend,
    *,
    user_id: str = "u_local",
    username: str = "alice",
    password: str = "correct-horse-battery",
    status: str = "active",
    is_system_admin: bool = False,
):
    """真 store 形态建号（`create_user`——与 m4-2 写路径同源）。"""
    store = backend.make_backend()
    store.create_user(
        user_id=user_id,
        username=username,
        display_name="Alice",
        email=None,
        password_hash=hash_password(password),
        status=status,
        is_system_admin=is_system_admin,
        created_by=None,
    )
    return store


def test_authenticate_session_success(backend, tmp_path) -> None:
    store = _create_local_user(backend, is_system_admin=True)
    settings = _local_settings(tmp_path)
    token, expires_at = issue_session_token(settings, user_id="u_local", token_version=0)
    assert datetime.strptime(expires_at, TS_FMT)  # UTC 库格式
    ctx = authenticate_session(store, settings, token)
    assert ctx.user_id == "u_local"
    assert ctx.via == "local"
    assert ctx.org_claim is None
    assert ctx.is_system_admin is True
    assert ctx.act is None


def test_authenticate_session_unknown_user(backend, tmp_path) -> None:
    store = backend.make_backend()
    settings = _local_settings(tmp_path)
    token, _ = issue_session_token(settings, user_id="u_ghost", token_version=0)
    with pytest.raises(AuthError) as excinfo:
        authenticate_session(store, settings, token)
    assert excinfo.value.code == 401


def test_authenticate_session_token_version_mismatch(backend, tmp_path) -> None:
    """改密/重置/停用 tv++ → 旧会话 401。"""
    store = _create_local_user(backend)
    settings = _local_settings(tmp_path)
    token, _ = issue_session_token(settings, user_id="u_local", token_version=0)
    backend.execute(
        "UPDATE users SET token_version = token_version + 1 WHERE id = ?",
        ("u_local",),
    )
    backend.commit()
    with pytest.raises(AuthError) as excinfo:
        authenticate_session(store, settings, token)
    assert excinfo.value.code == 401


def test_authenticate_session_disabled_user(backend, tmp_path) -> None:
    store = _create_local_user(backend)
    settings = _local_settings(tmp_path)
    token, _ = issue_session_token(settings, user_id="u_local", token_version=0)
    backend.execute(
        "UPDATE users SET disabled_at = ? WHERE id = ?",
        ("2020-01-01 00:00:00", "u_local"),
    )
    backend.commit()
    with pytest.raises(AuthError):
        authenticate_session(store, settings, token)


def test_authenticate_session_invited_user(backend, tmp_path) -> None:
    """invited（未接受邀请）不可登录——status != active → 401。"""
    store = _create_local_user(backend, status="invited")
    settings = _local_settings(tmp_path)
    token, _ = issue_session_token(settings, user_id="u_local", token_version=0)
    with pytest.raises(AuthError):
        authenticate_session(store, settings, token)


def test_authenticate_local_mode_accepts_session_token(backend, tmp_path) -> None:
    store = _create_local_user(backend)
    settings = _local_settings(tmp_path)
    token, _ = issue_session_token(settings, user_id="u_local", token_version=0)
    ctx = authenticate(store, settings, token)
    assert ctx.via == "local" and ctx.user_id == "u_local"


def test_authenticate_sso_mode_rejects_session_token(backend, tmp_path) -> None:
    """sso 形态（默认）不识别本地会话 token——同一 token 不被接受。"""
    store = _create_local_user(backend)
    token, _ = issue_session_token(
        _local_settings(tmp_path), user_id="u_local", token_version=0
    )
    sso_settings = Settings(environment="test", data_dir=tmp_path)  # auth_mode=sso
    assert sso_settings.auth_mode == "sso"
    with pytest.raises(AuthError) as excinfo:
        authenticate(store, sso_settings, token)
    assert excinfo.value.code == 401


def test_authenticate_local_mode_falls_back_to_dev_jwt(backend, tmp_path) -> None:
    """契约语义：local 会话失败后继续既有 dev JWT 分支（dev/test 便利）。

    这里显式验证「local 模式 + 合法开发 JWT → via=jwt」的落回路径（prod local
    由既有 prod 门禁拒绝 dev JWT/静态 token → 401）。
    """
    store = _create_local_user(backend)
    settings = _local_settings(tmp_path)
    dev_token = issue_dev_jwt(settings, user_id="u_local")
    ctx = authenticate(store, settings, dev_token)
    assert ctx.via == "jwt" and ctx.user_id == "u_local"


def test_authenticate_local_mode_ignores_sso_verifier(backend, tmp_path) -> None:
    """local 形态即使显式传 sso 验签器也不走 SSO 分支（不 JIT 建档）。"""
    store = backend.make_backend()
    settings = _local_settings(tmp_path)
    verifier = MockIdpVerifier(secret=SSO_SECRET)
    token = verifier.issue_token(sub="u_sso_ghost", aud=("knowledge-lattice",))
    with pytest.raises(AuthError):
        authenticate(store, settings, token, sso=verifier)
    assert backend.execute(
        "SELECT count(*) FROM users WHERE id = ?", ("u_sso_ghost",)
    ).fetchone()[0] == 0, "local 模式不得 JIT 建档（SSO 关闭）"


def test_authenticate_sso_claims_guard_rejects_local_mode(backend, tmp_path) -> None:
    """`_authenticate_sso_claims` 入口防御：local 模式一律拒绝（理论不可达）。"""
    store = backend.make_backend()
    settings = _local_settings(tmp_path)
    claims = SsoClaims(sub="u_guard", aud=("knowledge-lattice",))
    with pytest.raises(AuthError, match="local"):
        _authenticate_sso_claims(store, settings, claims)
    assert backend.execute(
        "SELECT count(*) FROM users WHERE id = ?", ("u_guard",)
    ).fetchone()[0] == 0
