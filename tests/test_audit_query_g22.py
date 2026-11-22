"""m3-2 A 组：G-22 查询级异步审计（FR-6 / design §6.3⑥ + §4 detail_json + §5.6）。

覆盖面（开工口径裁定②）：REST POST /api/search + MCP search；REST/MCP
annotate + get_entity 六入口；refused 含 403（无成员/无权限/停用组织）与
get_entity 404（restricted 静默面——A-16 口径落地=T-S9⑥ 收口）。

载体：直写月库 audit_events（search.query / search.annotate /
search.get_entity 三 action——design §4 action 域字面含 search；ops 视图
查询道前缀 search. 自动路由，零前端改动）；异步形态=进程内后台批量 flush
（满 5s 或满批先刷、月库独立连接、uvicorn lifespan 关停 flush）。

- T-S9⑥：无权 annotate/get_entity restricted → 查询级审计可回溯（refused）
  + 无 outbox 权限事件；
- 审计访问分级（FR-6/TC-OPS-03 延展）：org_admin 全量（detail_json 含查询词
  与命中） / sysadmin 仅元数据（detail_json 剥离）；
- 丢失窗口 ≤5s（异步 flush 语义——FR-6 字面）；
- 链完整性：查询道直写与 outbox 搬运道交错不产生分叉（walk_chain 不破）。
"""

from __future__ import annotations

import json
import time

import pytest

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

ORG = "org:tax"
NOW = "2026-11-08 09:00:00"

EVENT_SEARCH = "search.query"
EVENT_ANNOTATE = "search.annotate"
EVENT_GET_ENTITY = "search.get_entity"


@pytest.fixture()
def qa_env(backend, tmp_path):
    """查询审计 REST+MCP 壳：org:tax 文档面（d_cn 可见）+ 语义图（restricted R
    + 邻居 N）+ 五用户（u_full 成员 / u_nomem 无成员 / admin_tax 管理员 /
    sysadmin 系统管理员 / u_secret sem_restricted 持权）。"""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from fake_providers import FakeEmbedder
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.domain.auth import hash_token

    seed_org(backend, ORG)
    seed_dataset(backend, ORG, "ds:vat_lib")
    seed_dimension(backend, ORG, "region")
    seed_dim_value(backend, dim_id_for(ORG, "region"), "CN")
    for uid in ("u_full", "u_nomem", "admin_tax", "sysadmin", "u_secret",
                "u_owner"):
        seed_user(backend, uid)
    seed_membership(backend, "u_full", ORG)
    seed_membership(backend, "admin_tax", ORG, role="org_admin")
    seed_membership(backend, "u_secret", ORG, role="sem_restricted")
    backend.execute("UPDATE users SET is_system_admin = 1 WHERE id = 'sysadmin'")
    seed_grant(backend, user_id="u_full", dim_id=dim_id_for(ORG, "region"),
               val_id=val_id_for(ORG, "region", "CN"))
    seed_searchable_doc(backend, "d_cn", dims={"region": ["CN"]},
                        content_seg="进项 抵扣 范围")

    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        probe_interval_s=0, maintenance_interval_s=0.0,
                        worker_mode="inline", worker_poll_s=0.05)
    b = backend.make_backend()
    recs = [
        EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣"),
        EntityRecord(type="concept", key="tax.neighbor", name="邻接概念"),
    ]
    run_sync(b, ORG, FakeSourceAdapter("template_center", recs),
             settings=settings, snapshot=list(recs), now=NOW)
    # restricted R（YAML sensitivity）+ R↔N related_to
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    repo = tmp_path / "yamlrepo"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "secret.yaml").write_text(
        "- id: concept:tax.secret\n  owner: o\n"
        "  name: 内部税收筹划方案\n"
        "  aliases: [内部税收筹划方案]\n"
        "  sensitivity: restricted\n"
        "  related_to: [concept:tax.neighbor]\n",
        encoding="utf-8")
    run_yaml_sync(b, ORG, YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=settings, now=NOW)
    clear_annotator_cache()
    assert run_build(b, ORG, settings=settings)["status"] == "ready"

    def _eid(key: str) -> int:
        return backend.execute(
            "SELECT id FROM sem_entities WHERE org_id = ? AND key = ?",
            (ORG, key)).fetchone()[0]

    tokens = {uid: f"dev-static-{uid.replace('_', '-')}"
              for uid in ("u_full", "u_nomem", "admin_tax", "sysadmin", "u_secret")}
    for uid, token in tokens.items():
        backend.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                        (hash_token(token), uid))
    backend.commit()

    kwargs = dict(embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
                  run_startup_probe=False)
    if backend.name == "pg":
        app = create_app(settings, backend=backend.make_backend(), **kwargs)
    else:
        app = create_app(settings, **kwargs)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, app=app, db=backend, backend=b,
            settings=settings, tokens=tokens,
            eid=_eid, secret_id=_eid("tax.secret"),
            neighbor_id=_eid("tax.neighbor"),
            qa=app.state.service.query_audit,
            hdr=lambda uid: {"Authorization": f"Bearer {tokens[uid]}",
                             "X-Org-Id": ORG},
        )


def _query_events(env, action: str) -> list[dict]:
    """月库查询道事件（flush 后经 read_org_audit——org_admin 全量视角）。"""
    return env.backend.read_org_audit(ORG, action=action, limit=500)


def _flush(env) -> None:
    n = env.qa.flush()
    assert n >= 0


def _thread_safe_backend(backend, tmp_path):
    """队列消费线程可用的 backend：sqlite=ThreadLocalBackend（生产装配同款
    ——每线程自取连接，§2 线程模型）；pg=共享 PgBackend（psycopg 连接线程
    共享安全）。"""
    if backend.name == "pg":
        return backend.make_backend()
    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

    path = tmp_path / "qa_threaded.db"
    boot = connect(path)
    migrate_db(boot)
    boot.close()
    return ThreadLocalBackend(path)


# ============ ① 队列单元：异步窗口 ≤5s + flush 语义 + 链完整 ============


def test_qa1_queue_flush_and_window(backend, tmp_path) -> None:
    """队列单元：enqueue 不落库（异步弱一致）；显式 flush 落月库且链自洽；
    后台线程 5s 窗口内自动 flush（丢失窗口 ≤5s——FR-6 字面）。"""
    from knowledge_lattice.query_audit import QueryAuditQueue, build_query_event

    b = _thread_safe_backend(backend, tmp_path)
    qa = QueryAuditQueue(b, flush_interval_s=0.2)
    qa.enqueue(build_query_event(
        EVENT_SEARCH, org_id=ORG, actor="u_full",
        detail={"query": "进项抵扣", "chunk_ids": []}))
    assert b.read_org_audit(ORG, action=EVENT_SEARCH) == [], (
        "入队不等于落库——查询级审计异步弱一致（§5.6）")
    # 后台线程：0.2s 周期 → 5s 窗口内必达
    qa.start()
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if b.read_org_audit(ORG, action=EVENT_SEARCH):
                break
            time.sleep(0.05)
        rows = b.read_org_audit(ORG, action=EVENT_SEARCH)
        assert rows, "丢失窗口 ≤5s：后台 flush 周期内事件必须可见（FR-6）"
        assert json.loads(rows[0]["detail_json"])["query"] == "进项抵扣"
    finally:
        qa.stop()  # 关停 flush（uvicorn lifespan 同款）


def test_qa1b_queue_stop_flushes_pending(backend, tmp_path) -> None:
    """stop() 关停即 flush 残留队列（lifespan 关停口径——崩溃外的正常关停零丢失）。

    m3-3 P3-3 隔离改造：**不 start 后台线程**——enqueue 即 wake 会令后台线程
    立即 flush（60s 周期形同虚设），旧形态无法证明落库出自 stop()。本形态
    队列无后台线程，落库只可能来自 stop() 的关停 flush。"""
    from knowledge_lattice.query_audit import QueryAuditQueue, build_query_event

    b = _thread_safe_backend(backend, tmp_path)
    qa = QueryAuditQueue(b, flush_interval_s=60.0)  # 不 start——无后台线程
    qa.enqueue(build_query_event(
        EVENT_SEARCH, org_id=ORG, actor="u_full", detail={"query": "q"}))
    assert b.read_org_audit(ORG, action=EVENT_SEARCH) == [], (
        "无后台线程时入队不落库——后续落库只可能出自 stop()")
    qa.stop()
    assert b.read_org_audit(ORG, action=EVENT_SEARCH), "stop 必须 flush 残留队列"


def test_qa1c_queue_retry_then_drop(backend, tmp_path, monkeypatch) -> None:
    """写失败重试（瞬时故障不丢）+ 连续失败防毒丸丢弃（有界丢弃计数）。"""
    from knowledge_lattice.query_audit import QueryAuditQueue, build_query_event

    b = _thread_safe_backend(backend, tmp_path)
    qa = QueryAuditQueue(b, flush_interval_s=60.0, max_retries=3)
    qa.enqueue(build_query_event(EVENT_SEARCH, org_id=ORG, actor="u"))
    calls = {"n": 0}
    real = b.append_query_events

    def flaky(events):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("transient store failure (simulated)")
        return real(events)

    monkeypatch.setattr(b, "append_query_events", flaky)
    qa.flush()   # 第 1 次失败 → 回队
    assert qa.pending == 1 and qa.dropped == 0, "瞬时失败应回队不丢"
    qa.flush()   # 第 2 次失败 → 回队
    assert qa.pending == 1
    qa.flush()   # 第 3 次成功（重试耗尽前恢复）
    assert qa.pending == 0
    assert b.read_org_audit(ORG, action=EVENT_SEARCH), "恢复后事件必须落库"

    # 连续失败超限 → 防毒丸丢弃（计数如实）
    monkeypatch.setattr(
        b, "append_query_events",
        lambda events: (_ for _ in ()).throw(RuntimeError("down")))
    qa.enqueue(build_query_event(EVENT_SEARCH, org_id=ORG, actor="u"))
    for _ in range(3):
        qa.flush()
    assert qa.pending == 0 and qa.dropped == 1, "连续失败超限应丢弃并计数"


# ============ ② REST search：accepted / refused（无成员·停用）============


def test_qa2_rest_search_accepted(qa_env) -> None:
    """REST POST /api/search 200 → search.query accepted：detail=查询词+返回
    chunk_id 列表（design §4 查询级审计字面）。"""
    env = qa_env
    r = env.client.post("/api/search", headers=env.hdr("u_full"),
                        json={"query": "进项抵扣 范围", "top_k": 5})
    assert r.status_code == 200, r.text
    _flush(env)
    rows = _query_events(env, EVENT_SEARCH)
    assert rows and rows[0]["outcome"] == "accepted"
    assert rows[0]["actor"] == "u_full" and rows[0]["org_id"] == ORG
    detail = json.loads(rows[0]["detail_json"])
    assert detail["query"] == "进项抵扣 范围"
    chunk_ids = {c["chunk_id"] for c in r.json()["results"]}
    assert set(detail["chunk_ids"]) == chunk_ids, "命中 chunk_id 列表如实（§4）"


def test_qa3_rest_search_refused_membership(qa_env) -> None:
    """无成员关系 403 → refused 可回溯（reason=membership_denied）。"""
    env = qa_env
    r = env.client.post("/api/search", headers=env.hdr("u_nomem"),
                        json={"query": "进项抵扣", "top_k": 3})
    assert r.status_code == 403
    assert r.json()["code"] == "membership_denied"
    _flush(env)
    rows = _query_events(env, EVENT_SEARCH)
    assert rows and rows[0]["outcome"] == "refused"
    assert json.loads(rows[0]["detail_json"])["reason"] == "membership_denied"


def test_qa4_rest_search_refused_org_disabled(qa_env) -> None:
    """停用组织 403 → refused 可回溯（reason=org_disabled——裁定②「停用组织
    均记」）。"""
    env = qa_env
    env.backend.set_org_status(ORG, "disabled")
    try:
        r = env.client.post("/api/search", headers=env.hdr("u_full"),
                            json={"query": "进项抵扣", "top_k": 3})
        assert r.status_code == 403
        assert r.json()["code"] == "org_disabled"
        _flush(env)
        rows = _query_events(env, EVENT_SEARCH)
        assert rows and rows[0]["outcome"] == "refused"
        assert json.loads(rows[0]["detail_json"])["reason"] == "org_disabled"
    finally:
        env.backend.set_org_status(ORG, "active")


# ============ ③ 审计访问分级：org_admin 全量 / sysadmin 仅元数据 ============


def test_qa5_redaction_sysadmin_metadata_only(qa_env) -> None:
    """FR-6 分级：org_admin 全量（含 detail_json 查询词） / sysadmin 仅元数据
    （detail_json 剥离——查询词与命中详情不含）。"""
    env = qa_env
    assert env.client.post("/api/search", headers=env.hdr("u_full"),
                           json={"query": "进项抵扣", "top_k": 3}).status_code == 200
    _flush(env)
    full = env.client.get(f"/api/orgs/{ORG}/audit?action=search.",
                          headers=env.hdr("admin_tax"))
    assert full.status_code == 200, full.text
    body = full.json()
    assert body["scope"] == "full"
    assert any(e["action"] == EVENT_SEARCH and "detail_json" in e
               for e in body["events"]), "org_admin 全量含查询词与命中详情"
    meta = env.client.get(f"/api/orgs/{ORG}/audit?action=search.",
                          headers=env.hdr("sysadmin")).json()
    assert meta["scope"] == "metadata"
    q_events = [e for e in meta["events"] if e["action"] == EVENT_SEARCH]
    assert q_events and all(
        "detail_json" not in e for e in q_events), (
        "sysadmin 仅元数据——查询级事件 detail_json 必须剥离（FR-6）")


# ============ ④ T-S9⑥：restricted 无权尝试（A-16 收口） ============


def test_qa6_ts9_6_restricted_query_audit_traceable(qa_env) -> None:
    """T-S9⑥：无权成员 annotate/get_entity restricted 后——查询级审计可回溯
    （get_entity 404=refused〔restricted 静默面〕；annotate 记普通查询如实
    返回面，mention 无 restricted id）+ 无 outbox 权限事件。"""
    env = qa_env
    # ① annotate 含 R 别名的文本 → 200，mentions 无 R（存在性不泄露）
    r = env.client.post(f"/api/orgs/{ORG}/semantic/annotate",
                        headers=env.hdr("u_full"),
                        json={"text": "内部税收筹划方案 的口径是什么"})
    assert r.status_code == 200, r.text
    assert not [m for m in r.json()["mentions"]
                if m["entity_id"] == env.secret_id]
    # ② get_entity(R) → 404（restricted 静默面）
    r2 = env.client.get(f"/api/orgs/{ORG}/semantic/entities/{env.secret_id}",
                        headers=env.hdr("u_full"))
    assert r2.status_code == 404
    _flush(env)
    # ③ annotate accepted 如实返回面（entity_ids 无 restricted id——不额外标记）
    ann = _query_events(env, EVENT_ANNOTATE)
    assert ann and ann[0]["outcome"] == "accepted"
    ann_detail = json.loads(ann[0]["detail_json"])
    assert env.secret_id not in ann_detail["entity_ids"], (
        "mention 列表无 restricted id——存在性不泄露，不额外标记（裁定②）")
    # ④ get_entity refused（reason=restricted——A-16 回溯面）
    ge = _query_events(env, EVENT_GET_ENTITY)
    assert ge and ge[0]["outcome"] == "refused"
    ge_detail = json.loads(ge[0]["detail_json"])
    assert ge_detail["reason"] == "restricted"
    assert str(env.secret_id) == str(ge_detail["entity_id"]) or \
        ge_detail.get("entity_id") == env.secret_id
    # ⑤ 无 outbox 权限事件（权限事件仅持权面——A-16/T-S9⑤ 对照）
    n = env.db.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = ?",
        ("semantic.restricted_access",)).fetchone()[0]
    assert n == 0, "无权尝试不产生 outbox 权限事件（T-S9⑥）"


def test_qa7_annotate_refused_membership(qa_env) -> None:
    """annotate 无成员 403 → search.annotate refused 可回溯（REST 面经
    org_scoped——reason=membership_denied）。"""
    env = qa_env
    r = env.client.post(f"/api/orgs/{ORG}/semantic/annotate",
                        headers=env.hdr("u_nomem"),
                        json={"text": "进项税额抵扣"})
    assert r.status_code == 403
    _flush(env)
    rows = _query_events(env, EVENT_ANNOTATE)
    assert rows and rows[0]["outcome"] == "refused"
    assert json.loads(rows[0]["detail_json"])["reason"] == "membership_denied"


def test_qa7b_get_entity_accepted_privileged(qa_env) -> None:
    """持权 get_entity(R) 200 → search.get_entity accepted（node_ids 如实）——
    查询级审计不区分持权面（普通查询如实记录），权限事件另走 outbox。"""
    env = qa_env
    r = env.client.get(
        f"/api/orgs/{ORG}/semantic/entities/{env.secret_id}",
        headers=env.hdr("u_secret"), params={"expand": ["related_to"]})
    assert r.status_code == 200, r.text
    _flush(env)
    rows = _query_events(env, EVENT_GET_ENTITY)
    assert rows and rows[0]["outcome"] == "accepted"
    detail = json.loads(rows[0]["detail_json"])
    assert detail["entity_id"] == env.secret_id
    assert env.neighbor_id in detail["node_ids"]


# ============ ⑤ MCP 三工具同覆盖 ============


def test_qa8_mcp_search_annotate_get_entity(qa_env) -> None:
    """MCP search/annotate/get_entity 三工具均入查询审计（accepted+refused）。"""
    env = qa_env
    import asyncio

    import httpx
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    def _mcp(app, token: str) -> Client:
        def factory(**kw):
            return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)

        return Client(StreamableHttpTransport(
            url="http://testserver/mcp",
            headers={"Authorization": f"Bearer {token}", "X-Org-Id": ORG},
            httpx_client_factory=factory))

    def _call(app, token: str, tool: str, args: dict) -> dict:
        async def flow():
            async with _mcp(app, token) as client:
                result = await client.call_tool(tool, args)
                return json.loads(result.content[0].text)

        return asyncio.run(flow())

    def _call_err(app, token: str, tool: str, args: dict):
        from fastmcp.exceptions import ToolError

        async def flow():
            async with _mcp(app, token) as client:
                await client.call_tool(tool, args)

        with pytest.raises(ToolError) as exc_info:
            asyncio.run(flow())
        return exc_info.value

    token = env.tokens["u_full"]
    out = _call(env.app, token, "search", {"query": "进项抵扣 范围", "top_k": 3})
    assert out["results"]
    _call(env.app, token, "annotate", {"text": "进项税额抵扣 的范围"})
    err = _call_err(env.app, token, "get_entity", {"id": env.secret_id})
    assert "404" in str(err)
    _flush(env)
    assert _query_events(env, EVENT_SEARCH), "MCP search 入查询审计"
    assert _query_events(env, EVENT_ANNOTATE), "MCP annotate 入查询审计"
    ge = _query_events(env, EVENT_GET_ENTITY)
    assert ge and ge[0]["outcome"] == "refused"
    assert json.loads(ge[0]["detail_json"])["reason"] == "restricted"


# ============ ⑥ 链完整性：查询道直写 × outbox 搬运道交错 ============


def test_qa9_chain_integrity_with_outbox_interleave(qa_env) -> None:
    """两写道交错（查询道直写月库 + 治理道 outbox 搬运）→ walk_chain 不破
    （分叉=读路径 fail-closed，防叉是硬约束）。"""
    env = qa_env
    # 治理道：outbox 事件（两条）
    env.backend.append_outbox(
        "dataset.updated", json.dumps({"org_id": ORG, "dataset_id": "ds:vat_lib"}))
    env.backend.append_outbox(
        "grants.replace", json.dumps({"org_id": ORG, "user_id": "u_full"}))
    # 查询道：先 flush 一批（与搬运道交错①：查询先落）
    from knowledge_lattice.query_audit import build_query_event
    for i in range(3):
        env.qa.enqueue(build_query_event(
            EVENT_SEARCH, org_id=ORG, actor="u_full", detail={"query": f"q{i}"}))
    env.qa.flush()
    # 治理道搬运
    assert env.backend.ship_outbox()["shipped"] >= 2
    # 交错②：搬运后查询道再落
    for i in range(3):
        env.qa.enqueue(build_query_event(
            EVENT_ANNOTATE, org_id=ORG, actor="u_full", detail={"text": f"t{i}"}))
    env.qa.flush()
    # 再搬运一轮（outbox 已空也应幂等）
    env.backend.ship_outbox()
    # 读路径链验证（破链 raise AuditChainError——此处不抛即通过）
    rows = env.backend.read_org_audit(ORG, limit=500)
    actions = [r["action"] for r in rows]
    assert EVENT_SEARCH in actions and EVENT_ANNOTATE in actions
    assert "dataset.updated" in actions and "grants.replace" in actions
    # 链头唯一性（walk_chain 已内嵌校验——显式再走一遍月库全量）
    from knowledge_lattice.store.taskclock import utc_now_ts

    env.backend.read_monthly_events(when=utc_now_ts())
