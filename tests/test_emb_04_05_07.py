"""TC-EMB-04/05/07 嵌入服务与模型治理（M1 检索行为——双后端参数化各跑）。

- 04 查询侧降级链：①嵌入端点不可达 → BM25 单路 + embed_unreachable（无 500 +
  审计）；②rerank 端点不可达 → RRF 序返回 + rerank_skipped（+ 审计）；双降级叠加。
- 05 Reranker none：管线照常（RRF 序、无重排阶段）+ 归一对「无 rerank 分」退化
  RRF 归一不崩溃。
- 07 混模型向量零距离：旧标签块绝不进向量路（cv.embed_model JOIN 谓词），
  只走 BM25；A 正常参与双路（TC-RET-02 的推广）。

另含 NFR-8 熔断（连续 3 失败断开 60s、半开恢复）单测——降级链的「慢 vs 不可达」
区分机制（造数推进注入时钟，不推进系统时钟）。
"""

from __future__ import annotations

import dataclasses

from fake_providers import FakeEmbedder, FakeReranker


def _seed_two_blocks(db, *, vec_doc="d_mix_a", plain_doc="d_mix_b") -> None:
    """两块 FTS 均可命中（同词）、一篇带向量一篇不带。"""
    from helpers import insert_chunk, seed_doc_dims, seed_document

    for doc in (vec_doc, plain_doc):
        seed_document(db, doc_id=doc, dataset_id="ds:vat_lib", owner_user_id="u_owner")
        seed_doc_dims(db, doc, {"region": ["CN"]})
        insert_chunk(
            db, doc_id=doc, seq=1, content=f"{doc} 增值税原文",
            content_seg="增值税", title_seg="", keywords="", llm_keywords="", tags="",
        )
        db.execute(f"UPDATE documents SET active_version = 1 WHERE id = '{doc}'")


def _search(ret_stack, query="增值税", **overrides):
    from knowledge_lattice.core.docs.retrieve import search

    settings = dataclasses.replace(ret_stack["settings"], **overrides.pop("settings_kw", {}))
    return search(
        ret_stack["backend"], settings,
        user_id="u_full", org_id="org:tax", query=query,
        embedder=overrides.pop("embedder", ret_stack["embedder"]),
        **overrides,
    )


def _outbox_events(db, event_type: str) -> list[str]:
    rows = db.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?", (event_type,)
    ).fetchall()
    return [r[0] for r in rows]


# ============ TC-EMB-04 查询侧降级链 ============


def test_emb_04_embed_unreachable_degrades_to_bm25(ret_stack) -> None:
    """① 嵌入端点不可达：请求成功仅 BM25 路、无 500、记 search.degraded 审计。"""
    embedder = FakeEmbedder(dim=8, model_name="fake-embed", fail=True)
    _seed_two_blocks(ret_stack["db"])
    resp = _search(
        ret_stack, settings_kw={"reranker": "none"},
        embedder=embedder, reranker=None, enhancer=None,
    )
    assert resp["results"], "降级 BM25 单路仍可搜（无空结果误判、无 500）"
    assert "embed_unreachable" in resp["notice"]["degraded"]
    assert resp["notice"]["vector_pending"] is True
    events = _outbox_events(ret_stack["db"], "search.degraded")
    assert events and "embed_unreachable" in events[-1], "降级须记 search.degraded 审计事件"


def test_emb_04_rerank_unreachable_returns_rrf_order(ret_stack) -> None:
    """② rerank 端点不可达：跳过重排按 RRF 序返回、记审计。"""
    _seed_two_blocks(ret_stack["db"])
    resp = _search(
        ret_stack, settings_kw={"reranker": "cohere"},
        reranker=FakeReranker(fail=True), enhancer=None,
    )
    assert resp["results"], "rerank 降级不空结果"
    assert "rerank_skipped" in resp["notice"]["degraded"]
    assert "embed_unreachable" not in resp["notice"]["degraded"], "向量路正常不降级"
    events = _outbox_events(ret_stack["db"], "search.degraded")
    assert events and "rerank_skipped" in events[-1]


def test_emb_04_double_degradation_notice(ret_stack) -> None:
    """双降级叠加：degraded 同含两枚举（一次请求、同源审计）。"""
    _seed_two_blocks(ret_stack["db"])
    resp = _search(
        ret_stack, settings_kw={"reranker": "cohere"},
        embedder=FakeEmbedder(dim=8, model_name="fake-embed", fail=True),
        reranker=FakeReranker(fail=True), enhancer=None,
    )
    assert resp["results"]
    assert set(resp["notice"]["degraded"]) == {"embed_unreachable", "rerank_skipped"}
    events = _outbox_events(ret_stack["db"], "search.degraded")
    assert events and "embed_unreachable" in events[-1] and "rerank_skipped" in events[-1]


def test_emb_04_probe_reject_closes_vector_route(ret_stack) -> None:
    """探针拒绝档：向量路关闭（TC-EMB-03②的 M1 复验半句）——probe_reject 标注。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate, ProbeResult

    gate = EmbeddingGate()
    gate.update(ProbeResult(status="reject", min_cosine=0.1))
    _seed_two_blocks(ret_stack["db"])
    from knowledge_lattice.core.docs.retrieve import search

    resp = search(
        ret_stack["backend"], ret_stack["settings"],
        user_id="u_full", org_id="org:tax", query="增值税",
        embedder=ret_stack["embedder"], reranker=None, enhancer=None, gate=gate,
    )
    assert resp["results"]
    assert "probe_reject" in resp["notice"]["degraded"]
    # 查询嵌入不发起（跨底模距离无意义——拒绝档直接关路）
    assert ret_stack["embedder"].calls == [] or all(
        "增值税" not in c for c in ret_stack["embedder"].calls
    )


# ============ TC-EMB-05 Reranker none 实现 ============


def test_emb_05_none_reranker_full_pipeline(ret_stack) -> None:
    """none 档：管线照常返回（RRF 序、无重排阶段）；归一退化 RRF 归一不崩溃。"""
    _seed_two_blocks(ret_stack["db"])
    reranker = FakeReranker()  # 即便误传实例，settings=none 也不得调用
    resp = _search(
        ret_stack, settings_kw={"reranker": "none"},
        embedder=ret_stack["embedder"], reranker=reranker, enhancer=None,
    )
    assert resp["results"], "none 档管线照常返回"
    assert reranker.calls == [], "none=无重排阶段（provider 不被调用）"
    assert resp["notice"]["degraded"] == [], "none 是配置态，非降级事件"
    scores = [r["score"] for r in resp["results"]]
    assert all(0.0 <= s <= 1.0 for s in scores), "无 rerank 分时归一退化 RRF 归一（不崩溃）"
    assert scores[0] == 1.0  # min-max 顶格


def test_emb_05_none_matches_explicit_noop(ret_stack) -> None:
    """none 档与显式 NoopReranker 语义一致（保序 RRF——FR-2 降级路径）。"""
    from knowledge_lattice.adapters.reranker import NoopReranker
    from knowledge_lattice.core.docs.retrieve import search

    _seed_two_blocks(ret_stack["db"])
    a = search(
        ret_stack["backend"], ret_stack["settings"],
        user_id="u_full", org_id="org:tax", query="增值税",
        embedder=ret_stack["embedder"], reranker=None, enhancer=None,
    )
    b = search(
        ret_stack["backend"], ret_stack["settings"],
        user_id="u_full", org_id="org:tax", query="增值税",
        embedder=ret_stack["embedder"], reranker=NoopReranker(), enhancer=None,
    )
    ids_a = [r["chunk_id"] for r in a["results"]]
    ids_b = [r["chunk_id"] for r in b["results"]]
    assert ids_a and ids_a == ids_b, "RRF 序即最终序"


# ============ TC-EMB-07 混模型向量零距离（cv.embed_model JOIN 口径） ============


def test_emb_07_stale_label_never_enters_vector_route(ret_stack) -> None:
    """B（旧标签向量）只走 BM25、绝不进向量路 top-k；A（当前标签）正常参与双路。"""
    from knowledge_lattice.core.docs.retrieve import search

    db, backend, settings, embedder = (
        ret_stack["db"], ret_stack["backend"], ret_stack["settings"], ret_stack["embedder"],
    )
    _seed_two_blocks(db, vec_doc="d_cur", plain_doc="d_old")
    # A=当前标签（走写路径）；B=旧标签（直插 bge-m3:8，向量合法且与查询同向）
    rows = backend.mark_embedding_batch("d_cur", 1, settings.embed_model_label)
    backend.write_embeddings(
        settings.embed_model_label,
        [(r["rid"], embedder.embed([r["content"]])[0]) for r in rows],
    )
    old_rows = db.execute(
        "SELECT rid, content FROM chunks WHERE doc_id = 'd_old' AND tombstone = 0"
    ).fetchall()
    old_rid = old_rows[0][0]
    db.insert_vector(old_rid, "bge-m3:8", embedder.embed(["对齐文本"])[0])
    db.commit()

    plan = db.compile_acl("u_full", "org:tax", embed_model=settings.embed_model_label)
    # 向量路召回（先 ACL 后距离）：非当前标签行被 cv JOIN 谓词排除
    qv = embedder.embed(["对齐文本"])[0]
    vec_rows = backend.recall_vec(qv, plan, top_k=10)
    vec_rids = {r["rid"] for r in vec_rows}
    assert old_rid not in vec_rids, "旧标签向量绝不进向量路 top-k（TC-EMB-07）"
    cur_rid = rows[0]["rid"]
    assert cur_rid in vec_rids, "当前标签向量正常参与向量路"
    # 名次协议：rank 1 起连续
    assert [r["rank"] for r in vec_rows] == list(range(1, len(vec_rows) + 1))

    # 集成：B 经 BM25 路出现（FTS 可命中），vector_pending 块级标注为 True
    resp = search(
        backend, settings,
        user_id="u_full", org_id="org:tax", query="增值税",
        top_k=8, embedder=embedder, reranker=None, enhancer=None,
    )
    doc_ids = {r["doc_id"] for r in resp["results"]}
    assert "d_old" in doc_ids, "B 只经 BM25 路出现"
    assert "d_cur" in doc_ids, "A 正常参与双路"
    assert resp["notice"]["vector_pending"] is True  # 结果含缺当前标签向量的块（d_old）


def test_emb_07_plan_embed_model_predicate(matrix) -> None:
    """渲染层半句（v1.6 口径复核）：向量路 SQL 含 cv.embed_model = :current_model
    JOIN 谓词——双后端参数名各按方言（TC-EMB-02 行为断言的渲染基础）。"""
    plan = matrix.compile_acl("u_full", "org:tax", embed_model="fake-embed:8")
    cte, cv_join, outer = matrix.build_vec_parts(plan)
    sql, params = matrix.render_sql(cv_join)
    if matrix.is_sqlite:
        assert "cv.embed_model = :current_model" in sql
    else:
        assert "cv.embed_model = %(current_model)s" in sql
    assert params["current_model"] == "fake-embed:8"


# ============ NFR-8 熔断（连续 3 失败断开 60s、半开恢复） ============


def test_breaker_opens_after_three_failures_and_half_opens() -> None:
    from knowledge_lattice.adapters.breaker import CircuitBreaker

    br = CircuitBreaker(failures=3, cooldown_s=60.0)
    assert br.allow(now=100.0)  # closed 正常放行
    br.record_failure(now=100.0)
    br.record_failure(now=100.5)
    assert br.allow(now=101.0), "2 次失败未达阈值仍放行（熔断=连续 3 次）"
    br.record_failure(now=101.5)
    assert not br.allow(now=102.0), "连续 3 次失败 → 断开（期间直接降级不等超时）"
    assert not br.allow(now=160.0), "60s 冷却窗口内保持断开（101.5+60=161.5 前）"
    assert br.allow(now=161.6), "冷却后半开放行（探测恢复）"
    br.record_failure(now=161.6)
    assert not br.allow(now=162.0), "半开探测失败 → 重新断开"
    assert br.allow(now=161.6 + 60.5), "再次冷却后恢复半开"


def test_breaker_success_resets_streak() -> None:
    from knowledge_lattice.adapters.breaker import CircuitBreaker

    br = CircuitBreaker(failures=3, cooldown_s=60.0)
    br.record_failure(now=1.0)
    br.record_failure(now=2.0)
    br.record_success()  # 成功清零连续失败计数（非累计）
    br.record_failure(now=3.0)
    br.record_failure(now=4.0)
    assert br.allow(now=5.0), "非连续 3 次失败不断开（成功重置计数）"
