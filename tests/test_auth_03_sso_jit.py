"""TC-AUTH-03 SSO JIT 建档【单测｜M2——m2-4 A1】（双后端参数化）。

- mock IdP（自签 JWT——待决-2 未决，协议中立可插拔接口 + mock 实现）首次
  验签通过 → users 表自动落库（id/username/display_name——D16 管理员不建
  账号只配授权）；二次登录复用既有行（不重复建档、管理员改动不覆盖）。
- T16 生产形态复核（A5）：prod + SSO verifier → SSO token 可用、dev JWT /
  静态 token 全拒绝、POST /api/dev/token 404（路由门控在 app.py——已有
  TC-AUTH-01④，此处补认证面 prod 形态）。
"""

from __future__ import annotations

import json

from helpers import seed_user

from knowledge_lattice.adapters.auth_sso import MockIdpVerifier
from knowledge_lattice.config import Settings
from knowledge_lattice.domain.audit_events import EVENT_AUTH_USER_JIT
from knowledge_lattice.domain.auth import AuthError, authenticate

SECRET = "unit-sso-secret"
AUD = "knowledge-lattice"


def _verifier() -> MockIdpVerifier:
    return MockIdpVerifier(secret=SECRET)


def _settings(tmp_path, *, env: str = "test") -> Settings:
    return Settings(environment=env, data_dir=tmp_path)


def _authenticate(backend, settings, token, *, sso=None):
    """真 backend 形态认证（dbwrap 包装器 → SqliteBackend/PgBackend——同连接）。"""
    return authenticate(backend.make_backend(), settings, token, sso=sso)


def _outbox_events(backend, event_type: str) -> list[dict]:
    rows = backend.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
        (event_type,),
    ).fetchall()
    return [json.loads(r[0]) for r in rows]

# ============ TC-AUTH-03：首次登录 JIT 建档 / 二次复用（D16） ============


def test_sso_first_login_jit_creates_user(backend, tmp_path) -> None:
    """① mock SSO 首次验签通过 → users 自动落库 id/username/display_name +
    JIT 建档审计事件。"""
    verifier = _verifier()
    token = verifier.issue_token(
        sub="u_sso_1", aud=(AUD,), org="org:tax",
        username="zhang.san", display_name="张三",
    )
    ctx = _authenticate(backend, _settings(tmp_path), token, sso=verifier)
    assert ctx.user_id == "u_sso_1"
    assert ctx.via == "sso"
    assert ctx.org_claim == "org:tax"
    assert ctx.act is None  # 直连（无 act）——服务身份缺席
    row = backend.execute(
        "SELECT username, display_name FROM users WHERE id = ?", ("u_sso_1",)
    ).fetchone()
    assert row is not None, "首次登录应 JIT 建档（users 落库）"
    assert row[0] == "zhang.san"
    assert row[1] == "张三"
    jit = _outbox_events(backend, EVENT_AUTH_USER_JIT)
    assert len(jit) == 1 and jit[0]["user_id"] == "u_sso_1"


def test_sso_second_login_reuses_row(backend, tmp_path) -> None:
    """② 二次登录复用既有行：不重复建档、created_at 不变、管理员改过的
    display_name 不被 IdP claim 覆盖。"""
    verifier = _verifier()
    token = verifier.issue_token(
        sub="u_sso_2", aud=(AUD,), username="li.si", display_name="李四",
    )
    _authenticate(backend, _settings(tmp_path), token, sso=verifier)
    created_at = backend.execute(
        "SELECT created_at FROM users WHERE id = ?", ("u_sso_2",)
    ).fetchone()[0]
    # 管理员改 display_name（授权/档案维护——D16 管理员只配授权不动账号）
    backend.execute("UPDATE users SET display_name = ? WHERE id = ?",
                    ("管理员改的", "u_sso_2"))
    # 二次登录（IdP 仍带旧 display_name）
    token2 = verifier.issue_token(
        sub="u_sso_2", aud=(AUD,), username="li.si", display_name="李四",
    )
    ctx = _authenticate(backend, _settings(tmp_path), token2, sso=verifier)
    assert ctx.user_id == "u_sso_2"
    row = backend.execute(
        "SELECT username, display_name, created_at FROM users WHERE id = ?",
        ("u_sso_2",),
    ).fetchone()
    assert row[1] == "管理员改的", "二次登录不得覆盖既有档案字段"
    assert row[2] == created_at
    count = backend.execute(
        "SELECT COUNT(*) FROM users WHERE id = ?", ("u_sso_2",)
    ).fetchone()[0]
    assert count == 1
    assert len(_outbox_events(backend, EVENT_AUTH_USER_JIT)) == 1, "复用不重复记 JIT 事件"


def test_sso_username_fallback_to_sub(backend, tmp_path) -> None:
    """IdP 不带 preferred_username/name claim → username 回退 sub、display_name 空。"""
    verifier = _verifier()
    token = verifier.issue_token(sub="u_sso_3", aud=(AUD,))
    _authenticate(backend, _settings(tmp_path), token, sso=verifier)
    row = backend.execute(
        "SELECT username, display_name FROM users WHERE id = ?", ("u_sso_3",)
    ).fetchone()
    assert row[0] == "u_sso_3"
    assert row[1] is None


def test_sso_username_conflict_rejected(backend, tmp_path) -> None:
    """既有不同 id 同 username 用户 → JIT 建档 fail-closed 拒绝（users.username
    UNIQUE——不静默顶替他人账号）。"""
    seed_user(backend, "u_existing", username="zhang.san")
    verifier = _verifier()
    token = verifier.issue_token(
        sub="u_sso_9", aud=(AUD,), username="zhang.san",
    )
    try:
        _authenticate(backend, _settings(tmp_path), token, sso=verifier)
        raise AssertionError("username 冲突应拒绝")
    except AuthError as exc:
        assert exc.code == 401
    assert backend.execute(
        "SELECT COUNT(*) FROM users WHERE id = ?", ("u_sso_9",)
    ).fetchone()[0] == 0


# ============ 验签边界 ============


def test_sso_bad_signature_rejected(backend, tmp_path) -> None:
    """非本 IdP 密钥签发（验签失败）→ 401（dev 形态下也不得误认）。"""
    verifier = _verifier()
    forged = MockIdpVerifier(secret="attacker-secret").issue_token(
        sub="u_evil", aud=(AUD,),
    )
    try:
        _authenticate(backend, _settings(tmp_path), forged, sso=verifier)
        raise AssertionError("验签失败应 401")
    except AuthError as exc:
        assert exc.code == 401


def test_sso_expired_token_rejected(backend, tmp_path) -> None:
    """过期 token → 401（短 TTL 委托/直连同款验签语义）。"""
    verifier = _verifier()
    token = verifier.issue_token(sub="u_sso_4", aud=(AUD,), ttl_s=-10)
    try:
        _authenticate(backend, _settings(tmp_path), token, sso=verifier)
        raise AssertionError("过期 token 应 401")
    except AuthError:
        pass


def test_sso_without_verifier_rejected(backend, tmp_path) -> None:
    """未注入 SSO verifier（缺省 dev 形态）→ SSO token 不被接受（401）。"""
    verifier = _verifier()
    token = verifier.issue_token(sub="u_sso_5", aud=(AUD,))
    try:
        _authenticate(backend, _settings(tmp_path), token)  # sso=None 缺省
        raise AssertionError("无 verifier 时 SSO token 应 401")
    except AuthError as exc:
        assert exc.code == 401


def test_sso_disabled_user_rejected(backend, tmp_path) -> None:
    """JIT 建档后用户被禁用（disabled_at）→ 401。"""
    verifier = _verifier()
    token = verifier.issue_token(sub="u_sso_6", aud=(AUD,))
    _authenticate(backend, _settings(tmp_path), token, sso=verifier)
    backend.execute(
        "UPDATE users SET disabled_at = CURRENT_TIMESTAMP WHERE id = ?",
        ("u_sso_6",),
    )
    token2 = verifier.issue_token(sub="u_sso_6", aud=(AUD,))
    try:
        _authenticate(backend, _settings(tmp_path), token2, sso=verifier)
        raise AssertionError("禁用用户应 401")
    except AuthError as exc:
        assert exc.code == 401


def test_sso_token_missing_sub_rejected(backend, tmp_path) -> None:
    """sub claim 缺失 → 401（全局用户解析失败）。"""
    verifier = _verifier()
    token = verifier.issue_token(sub="", aud=(AUD,))
    try:
        _authenticate(backend, _settings(tmp_path), token, sso=verifier)
        raise AssertionError("缺 sub 应 401")
    except AuthError:
        pass


# ============ T16 生产形态复核（A5）：prod 下 SSO 可用 / dev 全拒绝 ============


def test_sso_verifier_factory_injection() -> None:
    """A5 auth 装配分层：build_sso_verifier 配置化注入——none=缺省 dev 形态
    （None，现有门禁/测试零感知）/ mock-idp=mock 实现 / 未知名 fail-closed。"""
    from knowledge_lattice.adapters.auth_sso import (
        MockIdpVerifier, build_sso_verifier,
    )

    assert build_sso_verifier(Settings(sso_provider="none")) is None
    verifier = build_sso_verifier(Settings(
        sso_provider="mock-idp", sso_mock_secret=SECRET,
    ))
    assert isinstance(verifier, MockIdpVerifier)
    try:
        build_sso_verifier(Settings(sso_provider="oidc-real"))
        raise AssertionError("未知 provider 应 fail-closed")
    except ValueError:
        pass


def test_prod_sso_accepted_dev_forms_rejected(backend, tmp_path) -> None:
    """prod + SSO verifier：SSO token 认证通过；dev JWT（默认公开密钥形态）与
    静态 token 全 401（T16——生产认证只走 SSO/委托 token）。"""
    from knowledge_lattice.domain.auth import hash_token, issue_dev_jwt

    prod = _settings(tmp_path, env="prod")
    verifier = _verifier()
    # 预建用户（prod 无 JIT 也可——JIT 属 SSO 路径正常行为，这里 sub 走 JIT）
    sso_token = verifier.issue_token(sub="u_prod_1", aud=(AUD,), org="org:tax")
    ctx = _authenticate(backend, prod, sso_token, sso=verifier)
    assert ctx.via == "sso" and ctx.user_id == "u_prod_1"
    # dev JWT：prod 下不进入验签分支（公开默认密钥可伪造——P2-5）
    dev_jwt = issue_dev_jwt(prod, user_id="u_prod_1", org="org:tax")
    try:
        _authenticate(backend, prod, dev_jwt, sso=verifier)
        raise AssertionError("prod 下 dev JWT 应 401")
    except AuthError as exc:
        assert exc.code == 401
    # 静态 token：prod 拒绝
    backend.execute(
        "UPDATE users SET token_hash = ? WHERE id = ?",
        (hash_token("static-x"), "u_prod_1"),
    )
    try:
        _authenticate(backend, prod, "static-x", sso=verifier)
        raise AssertionError("prod 下静态 token 应 401")
    except AuthError as exc:
        assert exc.code == 401
