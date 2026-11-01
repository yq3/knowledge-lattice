"""TC-AUTH-04 委托 token 语义【单测｜M2——m2-4 A2/A3】+ RFC 8693 act 对象形态
（m1-3 检查点 L82 移交必须项闭环）+ A-9 请求体权限字段口径 + m2-3 管理面兼容回归（B）。

- 委托 token（D18 主方案·RFC 8693 Token Exchange）：aud=knowledge-lattice、
  sub=用户、act=agent 标识、org claim 单值——按 sub 计权、act 进审计（双身份）；
- 透传用户原始 token（aud 非本服务）→ 拒绝（MCP 规范明令）+ 审计；
- act 对象形态 {"sub": "<agent-client-id>"}（RFC 8693 §4.1）：链式嵌套时
  **最外层 sub = current actor**（RFC MUST——prior actors 仅信息性），完整链
  进审计 payload act_chain；
- 请求体权限字段 → 忽略并记审计、请求正常处理（FR-4/D18 v0.6.1 统一口径——
  附录 A-9 闭环）；
- 组织上下文沿 D18 统一规则（claim 优先/X-Org-Id 兜底/不一致 400——与
  resolve_org 对齐）。
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
    EVENT_AUTH_DELEGATED,
    EVENT_AUTH_PERMISSIONS_IGNORED,
    EVENT_AUTH_SSO_REFUSED,
)
from knowledge_lattice.domain.auth import AuthError, authenticate
from knowledge_lattice.store.sqlite import connect

SECRET = "unit-sso-secret"
AUD = "knowledge-lattice"


def _verifier() -> MockIdpVerifier:
    return MockIdpVerifier(secret=SECRET)


def _settings(tmp_path) -> Settings:
    return Settings(environment="test", data_dir=tmp_path, probe_interval_s=0,
                    worker_mode="inline")


def _delegated(verifier, *, sub="u_del_1", act="agent-x", org="org:tax", aud=(AUD,)):
    return verifier.issue_token(sub=sub, aud=aud, org=org, act=act)


def _authenticate(backend, settings, token, *, sso=None):
    """真 backend 形态认证（dbwrap 包装器 → SqliteBackend/PgBackend——同连接）。"""
    return authenticate(backend.make_backend(), settings, token, sso=sso)


def _outbox(backend, event_type: str) -> list[dict]:
    rows = backend.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?", (event_type,),
    ).fetchall()
    return [json.loads(r[0]) for r in rows]


# ============ TC-AUTH-04：按 sub 计权、act 进审计 ============


def test_delegated_token_weights_by_sub_act_audited(backend, tmp_path) -> None:
    """委托 token（string act）→ 按 sub 计权（AuthContext.user_id=sub）、act
    进审计（auth.delegated 双身份事件）。JIT 同时为 sub 建档。"""
    verifier = _verifier()
    token = _delegated(verifier)
    ctx = _authenticate(backend, _settings(tmp_path), token, sso=verifier)
    assert ctx.user_id == "u_del_1", "委托 token 按 sub 计权"
    assert ctx.act == "agent-x"
    assert ctx.via == "sso"
    assert ctx.org_claim == "org:tax"
    events = _outbox(backend, EVENT_AUTH_DELEGATED)
    assert len(events) == 1
    assert events[0]["user_id"] == "u_del_1"
    assert events[0]["act"] == "agent-x"
    assert events[0]["org"] == "org:tax"


def test_delegated_act_object_form(backend, tmp_path) -> None:
    """RFC 8693 act 对象形态 {"sub": "<agent-client-id>"} → 取对象 sub 为
    agent 标识、进审计（m1-3 移交必须项——原仅 string）。"""
    verifier = _verifier()
    token = verifier.issue_token(
        sub="u_del_1", aud=(AUD,), org="org:tax",
        act={"sub": "agent-client-7", "iss": "https://idp.example"},
    )
    ctx = _authenticate(backend, _settings(tmp_path), token, sso=verifier)
    assert ctx.act == "agent-client-7"
    events = _outbox(backend, EVENT_AUTH_DELEGATED)
    assert events[-1]["act"] == "agent-client-7"


def test_delegated_act_nested_chain(backend, tmp_path) -> None:
    """链式委托（RFC 8693 §4.1 Figure 6）：最外层 sub=current actor（计权/
    审计主标识），嵌套 prior actors 全量进审计 act_chain（信息性）。"""
    verifier = _verifier()
    token = verifier.issue_token(
        sub="u_del_1", aud=(AUD,), org="org:tax",
        act={"sub": "svc-16", "act": {"sub": "svc-77"}},
    )
    ctx = _authenticate(backend, _settings(tmp_path), token, sso=verifier)
    assert ctx.act == "svc-16", "current actor = 最外层 act.sub（RFC 8693 MUST）"
    events = _outbox(backend, EVENT_AUTH_DELEGATED)
    assert events[-1]["act"] == "svc-16"
    assert events[-1]["act_chain"] == ["svc-16", "svc-77"], "完整委托链进审计"


def test_delegated_act_nested_string_tail(backend, tmp_path) -> None:
    """嵌套尾端 string act 形态（宽容接受）：{"sub": "a", "act": "b"} → 主标识 a、链 [a, b]。"""
    verifier = _verifier()
    token = verifier.issue_token(
        sub="u_del_1", aud=(AUD,), act={"sub": "svc-a", "act": "svc-b"},
    )
    ctx = _authenticate(backend, _settings(tmp_path), token, sso=verifier)
    assert ctx.act == "svc-a"
    assert _outbox(backend, EVENT_AUTH_DELEGATED)[-1]["act_chain"] == ["svc-a", "svc-b"]


def test_passthrough_user_token_rejected_and_audited(backend, tmp_path) -> None:
    """透传用户原始 token（aud=其他 client——本服务不在受众内）→ 401 拒绝
    （MCP 规范明令）+ auth.sso_refused 审计（reason=audience_mismatch）。"""
    verifier = _verifier()
    user_token = verifier.issue_token(
        sub="u_del_1", aud=("some-other-client",), org="org:tax",
    )
    try:
        _authenticate(backend, _settings(tmp_path), user_token, sso=verifier)
        raise AssertionError("透传原始 token 应拒绝")
    except AuthError as exc:
        assert exc.code == 401
    events = _outbox(backend, EVENT_AUTH_SSO_REFUSED)
    assert len(events) == 1
    assert events[0]["reason"] == "audience_mismatch"
    assert events[0]["user_id"] == "u_del_1"


def test_delegated_invalid_act_forms_rejected_and_audited(backend, tmp_path) -> None:
    """act 非法形态（数字 / 无 sub 对象 / sub 非字符串 / 空串）→ 401 + 审计
    （A3——非法形态拒绝并审计）。"""
    verifier = _verifier()
    for bad in (42, {}, {"sub": 99}, {"sub": ""}, ["agent-x"], True):
        token = verifier.issue_token(sub="u_del_1", aud=(AUD,), act=bad)
        try:
            _authenticate(backend, _settings(tmp_path), token, sso=verifier)
            raise AssertionError(f"非法 act 形态 {bad!r} 应拒绝")
        except AuthError as exc:
            assert exc.code == 401
        events = _outbox(backend, EVENT_AUTH_SSO_REFUSED)
        assert events[-1]["reason"] == "invalid_act", f"{bad!r}"


def test_delegated_direct_login_no_act_event(backend, tmp_path) -> None:
    """SSO 直连（无 act）不产生 auth.delegated 事件（委托语义仅 agent 在场）。"""
    verifier = _verifier()
    token = verifier.issue_token(sub="u_del_2", aud=(AUD,))
    _authenticate(backend, _settings(tmp_path), token, sso=verifier)
    assert _outbox(backend, EVENT_AUTH_DELEGATED) == []


@pytest.mark.parametrize(
    "aud_override,expect_ok",
    [
        (None, False),               # 缺失（无 aud claim）
        (("svc-x", AUD), True),      # 数组多值含本服务 → 受众语义放行
        (("svc-x", "svc-y"), False),  # 数组多值不含本服务
        (12345, False),              # 非串（归一空元组）
    ],
    ids=["missing", "multi-contains", "multi-excludes", "non-string"],
)
def test_delegated_aud_edge_forms(backend, tmp_path, aud_override, expect_ok) -> None:
    """Tester P3-2：aud 边界四形态固化（缺失/多值含/多值不含/非串——防回归；
    多值含本服务放行为 RFC 受众语义：本服务 ∈ 受众集即可）。"""
    verifier = _verifier()
    token = verifier.issue_token(
        sub="u_del_aud", aud=(AUD,), extra={"aud": aud_override},
    )
    if expect_ok:
        ctx = _authenticate(backend, _settings(tmp_path), token, sso=verifier)
        assert ctx.user_id == "u_del_aud"
    else:
        try:
            _authenticate(backend, _settings(tmp_path), token, sso=verifier)
            raise AssertionError(f"aud={aud_override!r} 应拒绝")
        except AuthError as exc:
            assert exc.code == 401


# ============ app 级（sqlite）：org claim 流 / 请求体权限字段 / m2-3 兼容 ============


def _sso_app(tmp_path, *, seed_hit: bool = True):
    """app 级 SSO 环境：create_app 注入 mock verifier + org:tax 造数。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from fake_providers import FakeEmbedder

    settings = _settings(tmp_path)
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
    if seed_hit:  # 一条可命中块（检索正常处理断言用）
        seed_searchable_doc(
            conn, "d_ss0", org_id=ORG, dataset_id="ds1", owner_user_id="u_full",
            dims={"region": ["CN"]}, content_seg="留抵退税额按进项构成比例计算",
        )
    conn.commit()
    client = TestClient(app)
    return app, client, verifier, settings, conn


def test_delegated_org_claim_priority_and_conflict(tmp_path) -> None:
    """组织上下文沿 D18 统一规则：claim 优先（无头直通）/ 头一致直通 /
    并存不一致 → 400（与既有 resolve_org 行为对齐）。"""
    _, client, verifier, settings, _ = _sso_app(tmp_path)
    token = _delegated(verifier, sub="u_full", org=ORG)
    # claim 优先（无 X-Org-Id 头）
    resp = client.post("/api/search", json={"query": "留抵退税"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    # 头与 claim 一致 → 直通
    resp2 = client.post("/api/search", json={"query": "留抵退税"},
                        headers={"Authorization": f"Bearer {token}",
                                 "X-Org-Id": ORG})
    assert resp2.status_code == 200
    # 不一致 → 400
    resp3 = client.post("/api/search", json={"query": "留抵退税"},
                        headers={"Authorization": f"Bearer {token}",
                                 "X-Org-Id": "org:other"})
    assert resp3.status_code == 400


def test_request_body_permissions_ignored_and_audited(tmp_path) -> None:
    """A-9 统一口径：有效 token 下请求体夹带权限字段（permissions/roles 等）
    → 忽略并记审计、请求正常处理（不按请求体计权——按 sub）。"""
    _, client, verifier, settings, conn = _sso_app(tmp_path)
    token = _delegated(verifier, sub="u_full", org=ORG)
    resp = client.post(
        "/api/search",
        json={"query": "留抵退税", "permissions": ["admin"],
              "roles": ["org_admin"], "acl": {"region": ["CN", "OS"]}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, "权限字段忽略——请求正常处理"
    rows = conn.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
        (EVENT_AUTH_PERMISSIONS_IGNORED,),
    ).fetchall()
    assert rows, "权限字段忽略须记审计"
    payload = json.loads(rows[0][0])
    assert payload["user_id"] == "u_full"
    assert set(payload["ignored_fields"]) >= {"permissions", "roles", "acl"}


def test_request_body_permissions_ignored_dev_jwt_too(tmp_path) -> None:
    """dev JWT 路径同款口径（FR-4 对一切认证形态生效——不只 SSO）。

    m2-6 P3-11 固化（m2-4 R2 P3-11 行为已修无永久用例）：**org 解析失败
    （400）的请求不产生忽略事件**——ignored_fields 只在 org 解析成功后记
    （否则 400 拒绝请求混入「忽略」语义事件，审计面失真）；正常 200 恰 1 条。"""
    settings = _settings(tmp_path)
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.domain.auth import issue_dev_jwt
    from fake_providers import FakeEmbedder

    app = create_app(settings, embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
                     run_startup_probe=False)
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
        conn, "d_ss1", org_id=ORG, dataset_id="ds1", owner_user_id="u_full",
        dims={"region": ["CN"]}, content_seg="留抵退税额按进项构成比例计算",
    )
    conn.commit()
    with TestClient(app) as client:
        token = issue_dev_jwt(settings, user_id="u_full", org=ORG)
        # ① org 解析失败（claim 与头不一致 → 400）：不产生忽略事件
        resp_bad = client.post(
            "/api/search",
            json={"query": "留抵退税", "permissions": ["admin"]},
            headers={"Authorization": f"Bearer {token}", "X-Org-Id": "org:other"},
        )
        assert resp_bad.status_code == 400
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_outbox WHERE event_type = ?",
            (EVENT_AUTH_PERMISSIONS_IGNORED,),
        ).fetchone()[0] == 0, "org 解析失败的 400 请求不混入忽略事件"
        # ② 正常请求（带权限字段）：恰 1 条
        resp = client.post(
            "/api/search",
            json={"query": "留抵退税", "permissions": ["admin"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        rows = conn.execute(
            "SELECT COUNT(*) FROM audit_outbox WHERE event_type = ?",
            (EVENT_AUTH_PERMISSIONS_IGNORED,),
        ).fetchone()[0]
        assert rows == 1


def test_mcp_search_permissions_param_ignored_and_audited(tmp_path) -> None:
    """MCP search 工具 permissions 参数（deprecated——同 org 参数先例）→
    忽略并记审计、调用正常返回。"""
    import asyncio

    import httpx
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    app, _, verifier, settings, conn = _sso_app(tmp_path)
    token = _delegated(verifier, sub="u_full", org=ORG)

    def factory(**kw):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), **kw
        )

    async def flow():
        client = Client(
            StreamableHttpTransport(
                url="http://testserver/mcp",
                headers={"Authorization": f"Bearer {token}"},
                httpx_client_factory=factory,
            )
        )
        async with client:
            await client.call_tool(
                "search", {"query": "留抵退税", "permissions": ["admin"]},
            )

    with TestClient(app):
        asyncio.run(flow())
    rows = conn.execute(
        "SELECT COUNT(*) FROM audit_outbox WHERE event_type = ?",
        (EVENT_AUTH_PERMISSIONS_IGNORED,),
    ).fetchone()[0]
    assert rows == 1, "MCP 工具 permissions 参数忽略须记审计"


def test_m23_admin_endpoint_with_delegated_token(tmp_path) -> None:
    """m2-3 兼容回归（B 项）：SSO 委托 token（org claim 单值）调 m2-3 管理面
    端点——org claim 与路径一致 → 管理面鉴权路径（get_auth→org_scoped→
    org_admin 门控）正常工作；非 org_admin → 403。"""
    _, client, verifier, settings, conn = _sso_app(tmp_path)
    token = _delegated(verifier, sub="u_full", org=ORG)
    # u_full 非 org_admin → 403（门控生效——委托 token 不因 act 获得管理权）
    resp = client.get(f"/api/orgs/{ORG}/audit",
                      headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403, resp.text
    # 升 org_admin → 200（按 sub 计权走管理面）
    conn.execute(
        "UPDATE user_org_memberships SET role = 'org_admin'"
        " WHERE user_id = 'u_full' AND org_id = ?",
        (ORG,),
    )
    conn.commit()
    resp2 = client.get(f"/api/orgs/{ORG}/audit",
                       headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200, resp2.text
