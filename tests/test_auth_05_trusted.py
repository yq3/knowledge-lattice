"""TC-AUTH-05 可信子系统三约束【单测｜M2——m2-4 A4】+ T13 生产形态收口。

服务凭证（服务 token——mTLS 形态归真实部署期，择型申报）+ 白名单（条目带
allowed_orgs + 按服务限流——真实载体＝LATTICE_TRUSTED_SERVICES_JSON 配置，
M1 dev 白名单模拟收口）+ X-On-Behalf-Of: <user_id> + 用户在场证据
（X-User-Assertion: 用户 SSO id_token/短期断言——校验 sub 与 X-On-Behalf-Of
一致，防服务凭证冒充离线用户，#33 P1-5 约束②）。

- ① 白名单内 + allowed_orgs 匹配 + 在场证据一致 → 按声明用户计权、双身份
  （service+user）进审计；
- ② org 越界 / ③ sub 不符（冒充） / ④ 白名单外 / 在场证据缺失·无效 /
  声明用户未建档·禁用 / 限流超限 → 拒绝且 outcome=refused 进审计（T13）。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from conftest import ORG
from helpers import (
    dim_id_for,
    seed_dataset,
    seed_dimension,
    seed_dim_value,
    seed_grant,
    seed_membership,
    seed_org,
    seed_searchable_doc,
    seed_user,
    val_id_for,
)

from knowledge_lattice.adapters.auth_sso import MockIdpVerifier
from knowledge_lattice.app import create_app
from knowledge_lattice.config import Settings
from knowledge_lattice.domain.audit_events import (
    EVENT_AUTH_PERMISSIONS_IGNORED,
    EVENT_AUTH_TRUSTED_SUBSYSTEM,
)
from knowledge_lattice.domain.auth import (
    AuthError,
    OrgContextError,
    ServiceRateLimiter,
    TrustedServiceRegistry,
    authenticate_trusted,
)
from knowledge_lattice.store.sqlite import connect

SECRET = "unit-sso-secret"
AUD = "knowledge-lattice"

WHITELIST = [
    {"service_id": "svc-ok", "token": "svc-secret-1",
     "allowed_orgs": [ORG], "rate_limit_rpm": 100},
    {"service_id": "svc-lim", "token": "svc-secret-2",
     "allowed_orgs": [ORG], "rate_limit_rpm": 2},
]


def _verifier() -> MockIdpVerifier:
    return MockIdpVerifier(secret=SECRET)


def _settings(tmp_path, *, env: str = "test") -> Settings:
    return Settings(environment=env, data_dir=tmp_path)


def _registry() -> TrustedServiceRegistry:
    return TrustedServiceRegistry.from_json(json.dumps(WHITELIST))


def _store(backend):
    """真 backend 形态（dbwrap 包装器 → SqliteBackend/PgBackend——同连接）。"""
    return backend.make_backend()


_DEFAULT = object()  # sentinel——区分「未传」与显式 None（registry=None 须直传）


def _call(backend, settings, *, token="svc-secret-1", obo="u_obo",
          assertion_sub="u_obo", org=ORG, sso=None, registry=_DEFAULT,
          limiter=None, with_assertion=True):
    verifier = sso or _verifier()
    assertion = (
        verifier.issue_token(sub=assertion_sub, aud=("agent-client",))
        if with_assertion else None
    )
    return authenticate_trusted(
        _store(backend),
        service_token=token, on_behalf_of=obo, user_assertion=assertion,
        org=org, sso=verifier,
        registry=_registry() if registry is _DEFAULT else registry,
        limiter=limiter,
    )


def _refused(backend) -> list[dict]:
    rows = backend.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
        (EVENT_AUTH_TRUSTED_SUBSYSTEM,),
    ).fetchall()
    events = [json.loads(r[0]) for r in rows]
    return [e for e in events if e.get("outcome") == "refused"]


def _accepted(backend) -> list[dict]:
    rows = backend.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
        (EVENT_AUTH_TRUSTED_SUBSYSTEM,),
    ).fetchall()
    events = [json.loads(r[0]) for r in rows]
    return [e for e in events if e.get("outcome") != "refused"]


# ============ ① 三约束齐备 → 按声明用户计权、双身份审计 ============


def test_trusted_all_constraints_pass(backend, tmp_path) -> None:
    """① 白名单内 + allowed_orgs 匹配 + 在场证据一致 → via=trusted、按声明
    用户计权（user_id=X-On-Behalf-Of）、act=service_id、双身份审计 accepted。"""
    seed_user(backend, "u_obo")
    ctx = _call(backend, _settings(tmp_path))
    assert ctx.user_id == "u_obo", "按声明用户计权"
    assert ctx.act == "svc-ok", "服务身份进 AuthContext（审计/凭证三要素同源）"
    assert ctx.via == "trusted"
    assert ctx.org_claim == ORG
    events = _accepted(backend)
    assert len(events) == 1
    assert events[0]["service_id"] == "svc-ok"
    assert events[0]["user_id"] == "u_obo"
    assert events[0]["org"] == ORG


def test_trusted_assertion_aud_not_enforced(backend, tmp_path) -> None:
    """在场证据是身份断言（用户签给 agent client 的 id_token）——不做本服务
    aud 校验（择型：断言非访问 token；exp 验签照常）。"""
    seed_user(backend, "u_obo")
    ctx = _call(backend, _settings(tmp_path))  # assertion aud=("agent-client",)
    assert ctx.user_id == "u_obo"


# ============ ②③④ 及扩展拒绝面：全部 refused 审计（T13） ============


def test_trusted_org_out_of_allowed_rejected(backend, tmp_path) -> None:
    """② org 越界（请求 org 不在条目 allowed_orgs）→ 403 + refused 审计。"""
    seed_user(backend, "u_obo")
    try:
        _call(backend, _settings(tmp_path), org="org:other")
        raise AssertionError("org 越界应拒绝")
    except AuthError as exc:
        assert exc.code == 403
    refused = _refused(backend)
    assert len(refused) == 1
    assert refused[0]["reason"] == "org_not_allowed"
    assert refused[0]["service_id"] == "svc-ok"


def test_trusted_subject_mismatch_rejected(backend, tmp_path) -> None:
    """③ 在场证据 sub 与 X-On-Behalf-Of 不符（冒充离线用户）→ 403 + refused。"""
    seed_user(backend, "u_obo")
    seed_user(backend, "u_victim")
    try:
        _call(backend, _settings(tmp_path), obo="u_victim",
              assertion_sub="u_obo")  # 服务只持 u_obo 的断言，却声明 u_victim
        raise AssertionError("sub 不符应拒绝（冒充）")
    except AuthError as exc:
        assert exc.code == 403
    refused = _refused(backend)
    assert refused[-1]["reason"] == "subject_mismatch"
    assert refused[-1]["user_id"] == "u_victim"


def test_trusted_unknown_service_rejected(backend, tmp_path) -> None:
    """④ 白名单外服务凭证 → 401 + refused 审计。"""
    seed_user(backend, "u_obo")
    try:
        _call(backend, _settings(tmp_path), token="rogue-service-token")
        raise AssertionError("白名单外应拒绝")
    except AuthError as exc:
        assert exc.code == 401
    refused = _refused(backend)
    assert refused[-1]["reason"] == "unknown_service"
    assert refused[-1]["service_id"] is None


def test_trusted_no_whitelist_configured_rejected(backend, tmp_path) -> None:
    """未配置白名单（registry 空/None）→ 可信子系统整体关闭（fail-closed）。"""
    seed_user(backend, "u_obo")
    try:
        _call(backend, _settings(tmp_path), registry=TrustedServiceRegistry.from_json("[]"))
        raise AssertionError("空白名单应拒绝")
    except AuthError as exc:
        assert exc.code == 401
    try:
        _call(backend, _settings(tmp_path), registry=None)
        raise AssertionError("registry=None 应拒绝")
    except AuthError:
        pass


def test_trusted_missing_user_assertion_rejected(backend, tmp_path) -> None:
    """在场证据缺失 → 拒绝（约束②——防服务凭证单凭白名单冒充离线用户）。"""
    seed_user(backend, "u_obo")
    try:
        _call(backend, _settings(tmp_path), with_assertion=False)
        raise AssertionError("缺在场证据应拒绝")
    except AuthError as exc:
        assert exc.code == 401
    assert _refused(backend)[-1]["reason"] == "missing_user_assertion"


def test_trusted_invalid_user_assertion_rejected(backend, tmp_path) -> None:
    """在场证据验签失败（他方密钥签发）→ 401 + refused。"""
    seed_user(backend, "u_obo")
    forged = MockIdpVerifier(secret="attacker").issue_token(sub="u_obo", aud=(AUD,))
    try:
        authenticate_trusted(
            _store(backend),
            service_token="svc-secret-1", on_behalf_of="u_obo",
            user_assertion=forged, org=ORG,
            sso=_verifier(), registry=_registry(),
        )
        raise AssertionError("验签失败的在场证据应拒绝")
    except AuthError as exc:
        assert exc.code == 401
    assert _refused(backend)[-1]["reason"] == "invalid_user_assertion"


def test_trusted_unknown_or_disabled_user_rejected(backend, tmp_path) -> None:
    """声明用户未建档（离线用户从未 SSO 登录）或已禁用 → 拒绝 + refused。"""
    try:  # 未建档：在场证据虽真（IdP 证明其身份），库内无账号不可计权
        _call(backend, _settings(tmp_path), obo="u_ghost",
              assertion_sub="u_ghost")
        raise AssertionError("未建档用户应拒绝")
    except AuthError as exc:
        assert exc.code == 403
    assert _refused(backend)[-1]["reason"] == "unknown_user"
    seed_user(backend, "u_dis")
    backend.execute(
        "UPDATE users SET disabled_at = CURRENT_TIMESTAMP WHERE id = ?", ("u_dis",)
    )
    try:
        _call(backend, _settings(tmp_path), obo="u_dis", assertion_sub="u_dis")
        raise AssertionError("禁用用户应拒绝")
    except AuthError as exc:
        assert exc.code == 401
    assert _refused(backend)[-1]["reason"] == "user_disabled"


def test_trusted_rate_limited(backend, tmp_path) -> None:
    """按服务限流（rate_limit_rpm=2）：窗口内第 3 次 → 429 + refused 审计。"""
    seed_user(backend, "u_obo")
    limiter = ServiceRateLimiter()
    for _ in range(2):
        ctx = _call(backend, _settings(tmp_path), token="svc-secret-2",
                    limiter=limiter)
        assert ctx.act == "svc-lim"
    try:
        _call(backend, _settings(tmp_path), token="svc-secret-2", limiter=limiter)
        raise AssertionError("超限流应 429")
    except AuthError as exc:
        assert exc.code == 429
    assert _refused(backend)[-1]["reason"] == "rate_limited"
    # 被拒不占配额、不重置窗口：第 4 次仍 429（Tester P3-3 断言强化——
    # 「拒绝后窗口不重置」——若被拒请求计数/重置窗口，此处将放行）
    try:
        _call(backend, _settings(tmp_path), token="svc-secret-2", limiter=limiter)
        raise AssertionError("窗口内第 4 次仍应 429")
    except AuthError as exc:
        assert exc.code == 429
    # 独立服务不共用配额（svc-ok 不受 svc-lim 窗口影响）
    ctx = _call(backend, _settings(tmp_path), limiter=limiter)
    assert ctx.act == "svc-ok"


def test_trusted_missing_org_context_400(backend, tmp_path) -> None:
    """org 上下文缺失（无 X-Org-Id）→ 400（D18 无隐式默认——OrgContextError）。"""
    seed_user(backend, "u_obo")
    try:
        _call(backend, _settings(tmp_path), org=None)
        raise AssertionError("org 缺失应 400")
    except OrgContextError:
        pass


def test_trusted_missing_on_behalf_of_rejected(backend, tmp_path) -> None:
    """X-On-Behalf-Of 头缺失（域函数独立调用形态）→ 401（协议三件套不全）。"""
    seed_user(backend, "u_obo")
    try:
        _call(backend, _settings(tmp_path), obo=None)
        raise AssertionError("缺 X-On-Behalf-Of 应拒绝")
    except AuthError as exc:
        assert exc.code == 401


# ============ 白名单载体：配置解析 fail-closed ============


@pytest.mark.parametrize("bad", [
    "not-json", "[]extra", '{"service_id": "x"}',  # 非 JSON / 非数组元素
    '[{"service_id": "x"}]',  # 缺 token
    '[{"token": "leak-me-secret", "allowed_orgs": []}]',  # 缺 service_id（条目带 token——P3-1）
    '[{"service_id": "x", "token": "leak-me-secret", "allowed_orgs": "org:tax"}]',  # orgs 非数组
    '[{"service_id": "", "token": "leak-me-secret", "allowed_orgs": []}]',  # 空 id
    '["leak-me-secret"]',  # 条目非对象
])
def test_trusted_registry_malformed_config_fail_closed(bad) -> None:
    """畸形白名单配置 → 构造即 raise（fail-closed——不静默忽略条目）；异常
    消息不回显条目内容（P3-1——token 明文不得进启动日志）。"""
    with pytest.raises(ValueError) as excinfo:
        TrustedServiceRegistry.from_json(bad)
    assert "leak-me-secret" not in str(excinfo.value), (
        "畸形配置异常消息不得泄露 token 明文"
    )


def test_trusted_registry_normalization() -> None:
    """合法配置归一：token 存 sha256（不存明文）、条目可按哈希检索。"""
    registry = _registry()
    entry = registry.match(__import__("hashlib").sha256(b"svc-secret-1").hexdigest())
    assert entry is not None and entry.service_id == "svc-ok"
    assert entry.allowed_orgs == (ORG,)
    assert registry.match("0" * 64) is None


# ============ app 级（sqlite）：REST 集成——T13 生产形态 ============


def _trusted_app(tmp_path, *, whitelist=WHITELIST):
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from fake_providers import FakeEmbedder

    settings = Settings(environment="test", data_dir=tmp_path, probe_interval_s=0,
                        worker_mode="inline",
                        trusted_services_json=json.dumps(whitelist))
    verifier = _verifier()
    app = create_app(
        settings, embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
        run_startup_probe=False, sso_verifier=verifier,
    )
    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    seed_dataset(conn, ORG, "ds1")
    seed_dimension(conn, ORG, "region")
    seed_dim_value(conn, dim_id_for(ORG, "region"), "CN")
    seed_user(conn, "u_full")
    seed_membership(conn, "u_full", ORG)
    seed_grant(conn, "u_full", dim_id_for(ORG, "region"),
               val_id_for(ORG, "region", "CN"))
    seed_searchable_doc(
        conn, "d_ts0", org_id=ORG, dataset_id="ds1", owner_user_id="u_full",
        dims={"region": ["CN"]}, content_seg="留抵退税额按进项构成比例计算",
    )
    conn.commit()
    return app, TestClient(app), verifier, conn


def test_trusted_rest_search_full_flow(tmp_path) -> None:
    """REST 集成：服务凭证 + X-On-Behalf-Of + 在场证据 + X-Org-Id → /api/search
    按声明用户（u_full）计权检索成功；act=service_id 进审计（双身份）。"""
    app, client, verifier, conn = _trusted_app(tmp_path)
    with client:
        assertion = verifier.issue_token(sub="u_full", aud=("agent-client",))
        resp = client.post(
            "/api/search",
            json={"query": "留抵退税"},
            headers={
                "Authorization": "Bearer svc-secret-1",
                "X-On-Behalf-Of": "u_full",
                "X-User-Assertion": assertion,
                "X-Org-Id": ORG,
            },
        )
        assert resp.status_code == 200, resp.text
        rows = conn.execute(
            "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
            (EVENT_AUTH_TRUSTED_SUBSYSTEM,),
        ).fetchall()
        payload = json.loads(rows[-1][0])
        assert payload["service_id"] == "svc-ok"
        assert payload["user_id"] == "u_full"


def test_trusted_rest_org_out_of_scope_403(tmp_path) -> None:
    """REST 集成：allowed_orgs 外的 org → 403 + refused 审计（T13 双身份：
    service_id + 声明 user）。"""
    app, client, verifier, conn = _trusted_app(tmp_path)
    with client:
        assertion = verifier.issue_token(sub="u_full", aud=("agent-client",))
        resp = client.post(
            "/api/search",
            json={"query": "留抵退税"},
            headers={
                "Authorization": "Bearer svc-secret-1",
                "X-On-Behalf-Of": "u_full",
                "X-User-Assertion": assertion,
                "X-Org-Id": "org:other",
            },
        )
        assert resp.status_code == 403
        rows = conn.execute(
            "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
            (EVENT_AUTH_TRUSTED_SUBSYSTEM,),
        ).fetchall()
        payload = json.loads(rows[-1][0])
        assert payload["outcome"] == "refused"
        assert payload["reason"] == "org_not_allowed"
        assert payload["service_id"] == "svc-ok" and payload["user_id"] == "u_full"


def test_trusted_rest_spurious_on_behalf_of_401(tmp_path) -> None:
    """普通用户 token 请求夹带 X-On-Behalf-Of（伪造服务形态）→ 白名单外 401
    （不降级为按 token 用户计权——fail-closed）。"""
    app, client, verifier, conn = _trusted_app(tmp_path)
    with client:
        token = verifier.issue_token(sub="u_full", aud=(AUD,))
        resp = client.post(
            "/api/search",
            json={"query": "留抵退税"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-On-Behalf-Of": "u_full",
            },
        )
        assert resp.status_code == 401
        rows = conn.execute(
            "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
            (EVENT_AUTH_TRUSTED_SUBSYSTEM,),
        ).fetchall()
        assert json.loads(rows[-1][0])["reason"] == "unknown_service"


def test_trusted_rest_rate_limited(tmp_path) -> None:
    """REST 请求路径限流真实生效（限流器共享态回归——防「每请求新建限流器」
    导致按服务限流失效）：svc-lim rpm=2 → 前两次 200、第三次 429。"""
    app, client, verifier, conn = _trusted_app(tmp_path)
    with client:
        assertion = verifier.issue_token(sub="u_full", aud=("agent-client",))
        headers = {
            "Authorization": "Bearer svc-secret-2",
            "X-On-Behalf-Of": "u_full",
            "X-User-Assertion": assertion,
            "X-Org-Id": ORG,
        }
        for _ in range(2):
            resp = client.post("/api/search", json={"query": "留抵退税"},
                               headers=headers)
            assert resp.status_code == 200
        resp3 = client.post("/api/search", json={"query": "留抵退税"},
                            headers=headers)
        assert resp3.status_code == 429
        rows = conn.execute(
            "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
            (EVENT_AUTH_TRUSTED_SUBSYSTEM,),
        ).fetchall()
        payloads = [json.loads(r[0]) for r in rows]
        refused = [p for p in payloads if p.get("outcome") == "refused"]
        assert refused[-1]["reason"] == "rate_limited"
        assert refused[-1]["service_id"] == "svc-lim"


def test_trusted_rest_without_whitelist_401(tmp_path) -> None:
    """未配置白名单的服务形态请求 → 401（可信子系统整体关闭）。"""
    app, client, verifier, _ = _trusted_app(tmp_path, whitelist=[])
    with client:
        assertion = verifier.issue_token(sub="u_full", aud=("agent-client",))
        resp = client.post(
            "/api/search",
            json={"query": "留抵退税"},
            headers={
                "Authorization": "Bearer svc-secret-1",
                "X-On-Behalf-Of": "u_full",
                "X-User-Assertion": assertion,
                "X-Org-Id": ORG,
            },
        )
        assert resp.status_code == 401


def test_trusted_rest_missing_org_400(tmp_path) -> None:
    """观察2：REST 可信面 org 缺失（trusted 头齐备但无 X-Org-Id）→ 400
    （D18 无隐式默认——域函数已测，此处固化 REST 接线层行为）。"""
    app, client, verifier, _ = _trusted_app(tmp_path)
    with client:
        assertion = verifier.issue_token(sub="u_full", aud=("agent-client",))
        resp = client.post(
            "/api/search",
            json={"query": "留抵退税"},
            headers={
                "Authorization": "Bearer svc-secret-1",
                "X-On-Behalf-Of": "u_full",
                "X-User-Assertion": assertion,
                # 无 X-Org-Id
            },
        )
        assert resp.status_code == 400


def test_trusted_assertion_bearer_prefix_case_insensitive(backend, tmp_path) -> None:
    """P3-3：在场证据 Bearer 前缀大小写不敏感（'bearer <jwt>' 同样接受）。"""
    seed_user(backend, "u_obo")
    verifier = _verifier()
    assertion = "bearer " + verifier.issue_token(sub="u_obo", aud=("agent-client",))
    ctx = authenticate_trusted(
        _store(backend),
        service_token="svc-secret-1", on_behalf_of="u_obo",
        user_assertion=assertion, org=ORG,
        sso=verifier, registry=_registry(),
    )
    assert ctx.user_id == "u_obo" and ctx.act == "svc-ok"


def test_rate_limiter_thread_safe() -> None:
    """P3-8：限流计数线程安全——并发 allow 不丢计数（无锁 read-modify-write
    会少记 → 允许数超限；锁下恰等于 limit）。300 = 4 workers × 75 轮（每轮
    Barrier(4) 对齐起跑，最大化竞态窗口且无整除性死锁）。"""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    limiter = ServiceRateLimiter()
    barrier = threading.Barrier(4)

    def hit(_i: int) -> bool:
        barrier.wait()  # 对齐起跑，最大化竞态窗口
        return limiter.allow("svc", 200)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(hit, range(300)))
    assert sum(results) == 200, "并发窗口内放行数必须恰等于 limit（不丢计数）"


# ============ MCP 可信路径接线专项（P2-1——R1 缺口回归） ============


def test_mcp_trusted_search_param_ignore_audited(tmp_path) -> None:
    """P2-1 核心：MCP 可信路径（X-On-Behalf-Of 形态）**同样执行**工具参数
    忽略审计——search 带 org+permissions 参数 → 调用正常返回且
    mcp.org_param_ignored 与 auth.request_permissions_ignored 双事件落
    outbox（D18「工具参数中的 org 一律忽略并记审计」/FR-4·A-9 对一切认证
    形态生效；R1 该分支提前 return 跳过审计）。"""
    import asyncio

    import httpx
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    app, _, verifier, conn = _trusted_app(tmp_path)
    assertion = verifier.issue_token(sub="u_full", aud=("agent-client",))
    headers = {
        "Authorization": "Bearer svc-secret-1",
        "X-On-Behalf-Of": "u_full",
        "X-User-Assertion": assertion,
        "X-Org-Id": ORG,
    }

    def factory(**kw):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), **kw
        )

    async def flow():
        client = Client(
            StreamableHttpTransport(
                url="http://testserver/mcp", headers=headers,
                httpx_client_factory=factory,
            )
        )
        async with client:
            await client.call_tool(
                "search",
                {"query": "留抵退税", "org": "org:llm-filled",
                 "permissions": ["admin"]},
            )

    from fastapi.testclient import TestClient
    with TestClient(app):
        asyncio.run(flow())
    org_events = conn.execute(
        "SELECT COUNT(*) FROM audit_outbox WHERE event_type = ?",
        ("mcp.org_param_ignored",),
    ).fetchone()[0]
    perm_events = conn.execute(
        "SELECT COUNT(*) FROM audit_outbox WHERE event_type = ?",
        (EVENT_AUTH_PERMISSIONS_IGNORED,),
    ).fetchone()[0]
    assert org_events == 1, "可信路径 org 参数忽略须记审计（P2-1）"
    assert perm_events == 1, "可信路径 permissions 参数忽略须记审计（P2-1）"


def test_mcp_trusted_impersonation_403(tmp_path) -> None:
    """P2-1 附加：MCP 可信冒充（在场证据 sub≠X-On-Behalf-Of）→ ToolError 403
    + refused 审计（接线层真实路径——域函数直测之外的端到端覆盖）。"""
    import asyncio

    import httpx
    import pytest as _pytest
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    from fastmcp.exceptions import ToolError

    app, _, verifier, conn = _trusted_app(tmp_path)
    # 服务持 u_obo2 的断言，却声明 u_full（冒充）
    assertion = verifier.issue_token(sub="u_obo2", aud=("agent-client",))
    from helpers import seed_user
    seed_user(conn, "u_obo2")
    conn.commit()
    headers = {
        "Authorization": "Bearer svc-secret-1",
        "X-On-Behalf-Of": "u_full",
        "X-User-Assertion": assertion,
        "X-Org-Id": ORG,
    }

    def factory(**kw):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), **kw
        )

    async def flow():
        client = Client(
            StreamableHttpTransport(
                url="http://testserver/mcp", headers=headers,
                httpx_client_factory=factory,
            )
        )
        async with client:
            await client.call_tool("search", {"query": "留抵退税"})

    from fastapi.testclient import TestClient
    with TestClient(app):
        with _pytest.raises(ToolError) as excinfo:
            asyncio.run(flow())
    assert "403" in str(excinfo.value)
    rows = conn.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
        (EVENT_AUTH_TRUSTED_SUBSYSTEM,),
    ).fetchall()
    payloads = [json.loads(r[0]) for r in rows]
    refused = [p for p in payloads if p.get("outcome") == "refused"]
    assert refused[-1]["reason"] == "subject_mismatch"
