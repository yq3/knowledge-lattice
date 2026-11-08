"""m3-3 C 组（G-28③⑤ 承接——用户裁定必做）+ D 组查询审计顺手批。

C 组：
- ③/P2-1：QueryAuditQueue 支持注入 backend_factory（pg 形态 flush 线程用
  **独立连接**——消除与请求线程共享 PgBackend._conn 单连接的协议错乱风险；
  sqlite 生产形态共享安全〔月库独立 mconn〕不变）+ pg 臂双连接形态验证；
- ⑤：链互斥并发测试收编（m3-2 Tester 注入脚本转正式用例）——ThreadLocalBackend
  + barrier + ship_outbox × append_query_events 双线程 N 轮 + walk_chain 断言
  （顺序用例 test_qa9 捕获面缺口——注入实证摘除互斥后顺序形态仍绿）；
  pg 臂随 P2-1 双连接补。

D 组：
- G-28⑦：dropped/pending 计数进 /stats（观测面——此前仅日志）；
- P3-3（m3-2）：qa1b 隔离 stop() flush（enqueue 即 wake 干扰消除——本文件
  重写形态并入 test_audit_query_g22 的原用例改造）；
- P3-4（m3-2）：refused 分支断言补——MCP 停用 / REST·MCP annotate·get_entity
  拒绝面；
- D-5：audit 取数 try/except（api/semantic.py / mcp/server.py——取数失败不
  500：404 面保守回查降级、权限事件取数失败跳过不影响主响应）。
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from conftest import ORG
from test_audit_query_g22 import qa_env  # noqa: F401 —— REST+MCP 壳复用

EVENT_SEARCH = "search.query"
EVENT_ANNOTATE = "search.annotate"
EVENT_GET_ENTITY = "search.get_entity"


def _thread_safe_backend(backend, tmp_path):
    """队列消费线程可用的 backend：sqlite=ThreadLocalBackend（生产装配同款
    ——每线程自取连接）；pg=共享 PgBackend（psycopg 连接线程共享安全，
    m3-2 形态——本文件 C-1 起以 backend_factory 双连接形态收窄）。"""
    if backend.name == "pg":
        return backend.make_backend()
    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

    path = tmp_path / "qa_threaded.db"
    boot = connect(path)
    migrate_db(boot)
    boot.close()
    return ThreadLocalBackend(path)


def _query_events(backend, action: str) -> list[dict]:
    return backend.read_org_audit(ORG, action=action, limit=500)


# ============ C-1 / G-28③ P2-1：backend_factory 独立连接 ============


def test_c1_backend_factory_flush_and_independence(backend, tmp_path) -> None:
    """backend_factory 注入形态：flush 经工厂取 backend 写月库（事件落库 +
    链完整）；工厂构造的 backend 与共享实例**不是同一对象**（独立连接注入面
    成立——pg 形态消除 flush 线程与请求线程共享单连接）。"""
    import contextlib

    from knowledge_lattice.query_audit import QueryAuditQueue, build_query_event

    b = _thread_safe_backend(backend, tmp_path)
    made: list = []

    @contextlib.contextmanager
    def factory():
        inner = _thread_safe_backend(backend, tmp_path)
        made.append(inner)
        try:
            yield inner
        finally:
            closer = getattr(inner, "close", None)
            if closer is not None:
                closer()

    qa = QueryAuditQueue(b, backend_factory=factory, flush_interval_s=60.0)
    qa.enqueue(build_query_event(
        EVENT_SEARCH, org_id=ORG, actor="u_full", detail={"query": "q"}))
    qa.flush()
    assert made, "flush 必须经工厂取 backend（独立连接注入面）"
    assert all(m is not b for m in made), "工厂产物与共享实例不同（独立连接）"
    rows = b.read_org_audit(ORG, action=EVENT_SEARCH)
    assert rows and json.loads(rows[0]["detail_json"])["query"] == "q"
    # 链完整（walk_chain 不抛即通过——read_monthly_events fail-closed）
    from knowledge_lattice.store.taskclock import utc_now_ts

    b.read_monthly_events(when=utc_now_ts())


def test_c1_pg_factory_connection_pid_independent(backend, tmp_path) -> None:
    """pg 臂双连接形态（G-28③ 字面）：工厂连接的 pg_backend_pid 与请求连接
    不同——flush 线程不共享请求连接（P2-1 修复的针对性验证；sqlite 臂验证
    工厂独立对象语义——无 pid 概念，改以连接对象不等断言）。"""
    from knowledge_lattice.query_audit import QueryAuditQueue, build_query_event

    if backend.name == "pg":
        from knowledge_lattice.store.postgres.audit_factory import (
            audit_backend_factory,
        )

        shared = backend.make_backend()
        pid_shared = shared._conn.execute(
            "SELECT pg_backend_pid()").fetchone()[0]
        factory = audit_backend_factory(backend.dsn, schema=backend.schema)
        with factory() as audit_b:
            pid_audit = audit_b._conn.execute(
                "SELECT pg_backend_pid()").fetchone()[0]
        assert pid_audit != pid_shared, (
            "flush 线程连接必须独立于请求连接（P2-1——共享单连接协议错乱风险）")

        qa = QueryAuditQueue(shared, backend_factory=factory,
                             flush_interval_s=60.0)
        qa.enqueue(build_query_event(
            EVENT_SEARCH, org_id=ORG, actor="u_full", detail={"query": "pid"}))
        qa.flush()
        rows = shared.read_org_audit(ORG, action=EVENT_SEARCH)
        assert rows and json.loads(rows[0]["detail_json"])["query"] == "pid"
    else:
        import contextlib

        shared = _thread_safe_backend(backend, tmp_path)

        @contextlib.contextmanager
        def factory():
            yield _thread_safe_backend(backend, tmp_path)

        qa = QueryAuditQueue(shared, backend_factory=factory,
                             flush_interval_s=60.0)
        qa.enqueue(build_query_event(
            EVENT_SEARCH, org_id=ORG, actor="u_full", detail={"query": "pid"}))
        qa.flush()
        assert shared.read_org_audit(ORG, action=EVENT_SEARCH)


# ============ C-2 / G-28⑤：链互斥并发测试收编（注入脚本转正式用例） ============


def test_c2_concurrent_ship_and_append_chain_intact(backend, tmp_path) -> None:
    """双写道**并发**交错：shipper 线程（outbox 搬运道）× querier 线程
    （查询道直写）barrier 对齐并发 N 轮 → walk_chain 链完整 + 行数对账。

    - sqlite 臂：两道均 ThreadLocalBackend（生产装配同款——每线程独立连接，
      互斥由月库 BEGIN IMMEDIATE 承载）；
    - pg 臂：搬运道走共享 PgBackend（请求连接）、查询道走**独立连接**
      （P2-1 双连接形态）——互斥由事务级咨询锁承载；
    - 捕获能力红线（m3-2 注入实证）：摘除互斥（BEGIN IMMEDIATE/咨询锁）后
      本用例变红——顺序形态 test_qa9 无此捕获面。
    """
    from knowledge_lattice.query_audit import build_query_event

    rounds = 120
    per_round = 3

    if backend.name == "pg":
        from knowledge_lattice.store.postgres.audit_factory import (
            audit_backend_factory,
        )

        ship_backend = backend.make_backend()          # 请求连接（搬运道）
        append_factory = audit_backend_factory(backend.dsn, schema=backend.schema)
    else:
        from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

        db_path = tmp_path / "qa_conc.db"
        from knowledge_lattice.store.sqlite import connect, migrate_db

        boot = connect(db_path)
        migrate_db(boot)
        boot.close()
        ship_backend = ThreadLocalBackend(db_path)     # 搬运道（独立连接）
        append_factory = None                          # 查询道：ThreadLocal 同款

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    ship_n = {"n": 0}
    append_n = {"n": 0}

    def shipper():
        try:
            barrier.wait(timeout=10)
            for i in range(rounds):
                ship_backend.append_outbox(
                    "maintenance.run",
                    json.dumps({"org_id": ORG, "i": i}, ensure_ascii=False))
                out = ship_backend.ship_outbox()
                ship_n["n"] += out.get("shipped", 0)
        except BaseException as exc:  # noqa: BLE001 —— 线程内异常汇聚
            errors.append(exc)

    def querier():
        try:
            barrier.wait(timeout=10)
            for i in range(rounds):
                events = [
                    build_query_event(
                        EVENT_SEARCH, org_id=ORG, actor="u_full",
                        detail={"query": f"q{i}-{j}"})
                    for j in range(per_round)
                ]
                if append_factory is not None:
                    with append_factory() as ab:
                        append_n["n"] += ab.append_query_events(events)
                else:
                    from knowledge_lattice.store.sqlite.threaded import (
                        ThreadLocalBackend,
                    )

                    qb = ThreadLocalBackend(db_path)
                    append_n["n"] += qb.append_query_events(events)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=shipper, name="qa-shipper")
    t2 = threading.Thread(target=querier, name="qa-querier")
    t1.start()
    t2.start()
    t1.join(timeout=120)
    t2.join(timeout=120)
    assert errors == [], f"并发双道线程异常：{[repr(e) for e in errors]}"
    assert ship_n["n"] >= rounds, "搬运道须完成全部轮次"
    assert append_n["n"] == rounds * per_round, "查询道直写计数如实"

    # 链完整 + 行数对账（walk_chain fail-closed——破链 raise AuditChainError）
    reader = (backend.make_backend() if backend.name == "pg"
              else _thread_safe_backend(backend, tmp_path))
    from knowledge_lattice.store.taskclock import utc_now_ts

    rows = reader.read_monthly_events(when=utc_now_ts())
    assert len(rows) >= ship_n["n"] + append_n["n"], (
        f"月库行数对账（got {len(rows)} < shipped {ship_n['n']} + appended "
        f"{append_n['n']}）")


# ============ P3-4（m3-2 Committer）：refused 分支断言补 ============


def test_c3_refused_org_disabled_rest_annotate_get_entity(qa_env) -> None:
    """REST annotate / get_entity 停用组织面：403 + refused（reason=
    org_disabled）可回溯——qa4 只覆盖 REST search，本用例补语义端点两面。"""
    env = qa_env
    env.backend.set_org_status(ORG, "disabled")
    try:
        r1 = env.client.post(f"/api/orgs/{ORG}/semantic/annotate",
                             headers=env.hdr("u_full"),
                             json={"text": "进项税额抵扣"})
        assert r1.status_code == 403
        assert r1.json()["code"] == "org_disabled"
        r2 = env.client.get(f"/api/orgs/{ORG}/semantic/entities/{env.neighbor_id}",
                            headers=env.hdr("u_full"))
        assert r2.status_code == 403
        assert r2.json()["code"] == "org_disabled"
        _f = env.qa.flush()
        ann = _query_events(env.backend, EVENT_ANNOTATE)
        assert ann and ann[0]["outcome"] == "refused"
        assert json.loads(ann[0]["detail_json"])["reason"] == "org_disabled"
        ge = _query_events(env.backend, EVENT_GET_ENTITY)
        assert ge and ge[0]["outcome"] == "refused"
        assert json.loads(ge[0]["detail_json"])["reason"] == "org_disabled"
    finally:
        env.backend.set_org_status(ORG, "active")


def test_c3_refused_membership_rest_get_entity_mcp_all(qa_env) -> None:
    """无成员面补断言：REST get_entity 403（qa7 只测 REST annotate）+
    MCP annotate / get_entity 拒绝面（ToolError 403 + refused 入队）。"""
    env = qa_env
    import asyncio

    import httpx
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    # REST get_entity 无成员：org_scoped 先拦（AclDeniedError→403 code=
    # membership_denied——与 qa3 同源语义；semantic:read 判定不达）
    r = env.client.get(f"/api/orgs/{ORG}/semantic/entities/{env.neighbor_id}",
                       headers=env.hdr("u_nomem"))
    assert r.status_code == 403
    assert r.json()["code"] == "membership_denied"

    def _mcp_err(token: str, tool: str, args: dict):
        from fastmcp.exceptions import ToolError

        def factory(**kw):
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=env.app), **kw)

        async def flow():
            async with Client(StreamableHttpTransport(
                    url="http://testserver/mcp",
                    headers={"Authorization": f"Bearer {token}",
                             "X-Org-Id": ORG},
                    httpx_client_factory=factory)) as client:
                await client.call_tool(tool, args)

        with pytest.raises(ToolError) as exc_info:
            asyncio.run(flow())
        return exc_info.value

    token_nomem = env.tokens["u_nomem"]
    err_ann = _mcp_err(token_nomem, "annotate", {"text": "进项税额抵扣"})
    assert "403" in str(err_ann)
    err_ge = _mcp_err(token_nomem, "get_entity", {"id": env.neighbor_id})
    assert "403" in str(err_ge)

    _f = env.qa.flush()
    # 同秒多事件 id tie-break 序不稳定——存在性断言（每拒绝面各至少一条）
    ge = _query_events(env.backend, EVENT_GET_ENTITY)
    reasons_ge = {json.loads(r["detail_json"])["reason"] for r in ge}
    assert reasons_ge >= {"semantic:read denied", "membership_denied"}, (
        "REST get_entity 无成员（org_scoped 面）与 MCP get_entity 拒绝面"
        f"（semantic:read）均须 refused 可回溯（got {reasons_ge}）")
    assert all(r["outcome"] == "refused" for r in ge)
    ann = _query_events(env.backend, EVENT_ANNOTATE)
    assert ann and ann[0]["outcome"] == "refused"
    assert json.loads(ann[0]["detail_json"])["reason"] == "semantic:read denied"


def test_c3_refused_org_disabled_mcp_tools(qa_env) -> None:
    """MCP 停用组织面：search / annotate / get_entity 三工具 403 +
    refused（reason=org_disabled）入查询审计（m3-2 已实现、缺断言——P3-4）。"""
    env = qa_env
    import asyncio

    import httpx
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    from fastmcp.exceptions import ToolError

    env.backend.set_org_status(ORG, "disabled")
    try:
        def factory(**kw):
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=env.app), **kw)

        token = env.tokens["u_full"]
        calls = {
            "search": {"query": "进项抵扣", "top_k": 3},
            "annotate": {"text": "进项税额抵扣"},
            "get_entity": {"id": env.neighbor_id},
        }
        for tool, args in calls.items():
            async def flow(t=tool, a=args):
                async with Client(StreamableHttpTransport(
                        url="http://testserver/mcp",
                        headers={"Authorization": f"Bearer {token}",
                                 "X-Org-Id": ORG},
                        httpx_client_factory=factory)) as client:
                    await client.call_tool(t, a)

            with pytest.raises(ToolError) as exc_info:
                asyncio.run(flow())
            assert "403" in str(exc_info.value), f"{tool} 停用组织须 403"
        _f = env.qa.flush()
        for action in (EVENT_SEARCH, EVENT_ANNOTATE, EVENT_GET_ENTITY):
            rows = _query_events(env.backend, action)
            assert rows and rows[0]["outcome"] == "refused", (
                f"MCP {action} 停用组织 refused 可回溯")
            assert json.loads(rows[0]["detail_json"])["reason"] == "org_disabled"
    finally:
        env.backend.set_org_status(ORG, "active")


# ============ D-4 / G-28⑦：dropped/pending 计数进 /stats ============


def test_d4_query_audit_dropped_pending_in_stats(qa_env) -> None:
    """/stats 暴露 query_audit.dropped / query_audit.pending（观测面——
    此前仅日志；溢出丢弃对运维可见）。小容量队列替换 + 溢出造数。"""
    from knowledge_lattice.query_audit import (
        QueryAuditQueue, build_query_event,
    )

    env = qa_env
    old_qa = env.qa
    tiny = QueryAuditQueue(env.backend, max_pending=2, flush_interval_s=60.0)
    app_service = env.app.state.service
    app_service.query_audit = tiny
    try:
        for i in range(4):   # 容量 2 → 丢最旧 2
            tiny.enqueue(build_query_event(
                EVENT_SEARCH, org_id=ORG, actor="u_full",
                detail={"query": f"overflow-{i}"}))
        assert tiny.dropped == 2
        stats = env.client.get(f"/api/orgs/{ORG}/stats",
                               headers=env.hdr("admin_tax"))
        assert stats.status_code == 200, stats.text
        qa_stats = stats.json().get("query_audit")
        assert qa_stats, "/stats 须含 query_audit 观测面（G-28⑦）"
        assert qa_stats["dropped"] == 2, "溢出丢弃计数进 /stats"
        assert qa_stats["pending"] == tiny.pending, "在队深度进 /stats"
    finally:
        app_service.query_audit = old_qa
        tiny.stop()
        old_qa.flush()


# ============ D-5：audit 取数包裹（取数失败不 500） ============


def test_d5_audit_lookup_failure_does_not_500(qa_env, monkeypatch) -> None:
    """为审计而做的回查（404 reason 判定 / restricted_ids 收集）失败时：
    主响应语义保持（404 保守 reason / 200 照常返回），不升级 500。"""
    env = qa_env
    orig_backend = env.app.state.service.backend
    # ① get_entity 404 分支的 restricted 回查失败 → 仍 404（reason 保守
    # not_found）。sem_entity_by_id 首次调用属核心查找（expand.py——须正常
    # 返回让 EntityNotFound 先行），第 2 次起=审计回查面（boom）。
    # sqlite 臂 service.backend 为 ThreadLocalBackend 代理——须按调用线程
    # 动态解析底层 backend（闭包捕获固定实例会跨线程踩 check_same_thread）。
    def _thread_backend():
        cur = orig_backend
        return cur._current() if hasattr(cur, "_current") else cur

    calls = {"n": 0}

    def flaky_by_id(*a, **kw):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("audit lookup store failure (simulated)")
        cur = _thread_backend()
        return type(cur).sem_entity_by_id(cur, *a, **kw)

    monkeypatch.setattr(
        env.app.state.service, "backend",
        _PatchedBackendProxy(orig_backend, {
            "sem_entity_by_id": flaky_by_id,
        }))
    r = env.client.get(f"/api/orgs/{ORG}/semantic/entities/99999",
                       headers=env.hdr("u_full"))
    assert r.status_code == 404, (
        "回查失败不得把 404 升级为 500（audit 取数兜底）")
    assert calls["n"] >= 2, "审计回查确已发生（boom 分支真实触达）"
    _f = env.qa.flush()
    ge = _query_events(env.backend, EVENT_GET_ENTITY)
    assert ge and ge[0]["outcome"] == "refused", "404 面仍落查询审计"
    assert json.loads(ge[0]["detail_json"])["reason"] == "not_found"

    # ② 持权 get_entity 的 restricted_ids 取数失败 → 200 照常（权限事件跳过）。
    # sem_restricted_ids 仅审计取数消费（boom 首调即炸——200 主响应不受累）
    def boom(*a, **kw):
        raise RuntimeError("audit lookup store failure (simulated)")

    monkeypatch.setattr(
        env.app.state.service, "backend",
        _PatchedBackendProxy(orig_backend, {
            "sem_restricted_ids": boom,
        }))
    r2 = env.client.get(
        f"/api/orgs/{ORG}/semantic/entities/{env.secret_id}",
        headers=env.hdr("u_secret"), params={"expand": ["related_to"]})
    assert r2.status_code == 200, (
        "持权 200 路径的权限事件取数失败不得升级 500（事件跳过不阻断主响应）")


class _PatchedBackendProxy:
    """测试专用 backend 代理：指定方法覆盖、其余透传底层（ThreadLocal 代理
    的 __getattr__ 语义保持——每属性访问动态解析，不跨线程固定连接）。"""

    def __init__(self, inner, overrides: dict) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_overrides", overrides)

    def __getattr__(self, name: str):
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            return overrides[name]
        return getattr(object.__getattribute__(self, "_inner"), name)
