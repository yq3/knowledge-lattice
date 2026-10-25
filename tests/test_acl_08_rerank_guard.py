"""TC-ACL-08 rerank 前后 ACL 双断言（防御纵深）【单测｜M1——双后端参数化各跑】。

- ① rerank 前（外发前）：候选须 ⊆ 用户可见块集合——越权块被剔除并记拦截审计；
- ② 返回前：rerank 返回序列混入越权块 → 二次断言拦下，最终 top-k 无越权块；
- ③ 防御纵深可测：单独移除任一断言（monkeypatch no-op）时对应用例失败；
- 正常路径双断言零剔除通过。

注入口径申报：TEST-CASES 前置为「mock ACL 编译器漏生成一个维度条件」——本实
现按「召回结果混入越权块」（wrap backend.recall_fts/recall_vec）等价落地：断
言数据源 = retrieve 内部**独立重编译**的二次 plan（不同调用、不同 SQL 路径），
防线针对渲染/引擎/注入面放宽；编译器纯逻辑正确性由 T1~T22 编译器矩阵背书
（断言层复用同一编译函数是「ACL 语义只实现一次」纪律的必然——§5.1）。
"""

from __future__ import annotations

import dataclasses

from fake_providers import FakeReranker


def _seed_acl_case(db) -> dict:
    """三块：d_ok（u_full 可见）两块 + d_secret（u_cn 授权外——region=[OS]）一块。

    u_full 授权 region=[CN,OS]（矩阵默认）——为使 d_secret 越权，测试内改用
    u_cn（region=[CN]）发起检索：d_secret(OS) 对 u_cn 不可见。
    """
    from helpers import insert_chunk, seed_doc_dims, seed_document

    for doc, dims in (
        ("d_ok", {"region": ["CN"]}),
        ("d_secret", {"region": ["OS"]}),
    ):
        seed_document(db, doc_id=doc, dataset_id="ds:vat_lib", owner_user_id="u_owner")
        seed_doc_dims(db, doc, dims)
        insert_chunk(
            db, doc_id=doc, seq=1, content=f"{doc} 增值税原文",
            content_seg="增值税", title_seg="", keywords="", llm_keywords="", tags="",
        )
        db.execute(f"UPDATE documents SET active_version = 1 WHERE id = '{doc}'")
    db.commit()
    return {"ok_doc": "d_ok", "secret_doc": "d_secret"}


def _rid_for(db, doc_id: str) -> int:
    return db.execute(
        "SELECT rid FROM chunks WHERE doc_id = ? AND tombstone = 0", (doc_id,)
    ).fetchone()[0]


def _search(ret_stack, monkeypatch=None, **overrides):
    from knowledge_lattice.core.docs.retrieve import search

    settings = dataclasses.replace(
        ret_stack["settings"], reranker="cohere", **overrides.pop("settings_kw", {})
    )
    return search(
        ret_stack["backend"], settings,
        user_id="u_cn", org_id="org:tax", query="增值税",
        embedder=ret_stack["embedder"], **overrides,
    )


def test_acl_08_pre_rerank_guard_drops_invisible(ret_stack, monkeypatch) -> None:
    """① 召回放宽（模拟编译/渲染 bug）：rerank 前兜底剔除越权块 + 拦截审计。"""
    db, backend = ret_stack["db"], ret_stack["backend"]
    docs = _seed_acl_case(db)
    secret_rid = _rid_for(db, docs["secret_doc"])

    real_fts = backend.recall_fts
    real_vec = backend.recall_vec

    def leaky_fts(tokens, plan, *, top_k=20):
        rows = real_fts(tokens, plan, top_k=top_k)
        # 模拟召回层放宽：把越权块塞进 FTS 路（rank 靠前——若断言缺失则直接外发）
        leaked = [
            {
                "rid": secret_rid, "chunk_id": "chk:d_secret:v1:1", "doc_id": "d_secret",
                "title": "秘密文档", "page_no": 1, "sheet_name": None, "score_raw": -99.0,
                "rank": 1, "content": "秘密文档 增值税原文（越权）",
                "dataset_id": "ds:vat_lib", "dataset_name": "库 ds:vat_lib",
                "source_uri": "user:u_owner", "dims": {"region": ["OS"]},
            }
        ]
        return leaked + rows

    def leaky_vec(qv, plan, *, top_k=20):
        rows = real_vec(qv, plan, top_k=top_k)
        return [
            {
                "rid": secret_rid, "chunk_id": "chk:d_secret:v1:1", "doc_id": "d_secret",
                "title": "秘密文档", "page_no": 1, "sheet_name": None, "dist": 0.0,
                "rank": 1, "content": "秘密文档 增值税原文（越权）",
                "dataset_id": "ds:vat_lib", "dataset_name": "库 ds:vat_lib",
                "source_uri": "user:u_owner", "dims": {"region": ["OS"]},
            }
        ] + rows

    monkeypatch.setattr(backend, "recall_fts", leaky_fts)
    monkeypatch.setattr(backend, "recall_vec", leaky_vec)

    reranker = FakeReranker()
    resp = _search(ret_stack, reranker=reranker, enhancer=None)
    # rerank 收到的候选全部 ⊆ 可见集（越权块在外发前被剔除）
    assert reranker.calls, "rerank 正常执行（拦截不阻断管线）"
    docs_sent = reranker.calls[0][1]
    assert all("越权" not in d for d in docs_sent), "rerank 输入不得含越权块"
    # 最终 top-k 无越权块
    assert all(r["doc_id"] == "d_ok" for r in resp["results"])
    # 拦截审计事件
    events = db.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = 'search.acl_intercept'"
    ).fetchall()
    assert events and "pre_rerank" in events[0][0]


def test_acl_08_final_guard_intercepts_rerank_response(ret_stack, monkeypatch) -> None:
    """② rerank 后可见性收紧（前断言后、返回前窗口）：二次断言拦下，top-k 无越权块。

    注入形式：backend.visible_chunk_ids 两阶段——首次（rerank 前断言）放行全集、
    二次（返回前）真集收紧（模拟前断言被绕过/权限中途变化：越权块经召回混入候选
    且穿过前断言，返回前真集兜底拦截）。
    """
    db, backend = ret_stack["db"], ret_stack["backend"]
    docs = _seed_acl_case(db)
    secret_rid = _rid_for(db, docs["secret_doc"])
    ok_rid = _rid_for(db, docs["ok_doc"])
    label = ret_stack["settings"].embed_model_label
    for r in backend.mark_embedding_batch(docs["ok_doc"], 1, label):
        backend.write_embeddings(label, [(r["rid"], ret_stack["embedder"].embed([r["content"]])[0])])

    real_visible = backend.visible_chunk_ids
    real_fts = backend.recall_fts
    calls = {"n": 0}

    def leaky_fts(tokens, plan, *, top_k=20):
        # 召回层放宽（模拟渲染 bug/注入面）：越权块混入 FTS 路（rank 靠前）
        rows = real_fts(tokens, plan, top_k=top_k)
        return [
            {
                "rid": secret_rid, "chunk_id": "chk:d_secret:v1:1", "doc_id": "d_secret",
                "title": "秘密文档", "page_no": 1, "sheet_name": None, "score_raw": -99.0,
                "rank": 1, "content": "秘密文档 增值税原文（越权）",
                "dataset_id": "ds:vat_lib", "dataset_name": "库 ds:vat_lib",
                "source_uri": "user:u_owner", "dims": {"region": ["OS"]},
            }
        ] + rows

    def two_phase_visible(plan, rids=None):
        calls["n"] += 1
        true_set = real_visible(plan)
        if calls["n"] == 1:
            return true_set | {secret_rid}  # 前断言放行（模拟绕过/宽松窗口）
        return true_set  # 返回前收紧（真实可见集）

    monkeypatch.setattr(backend, "recall_fts", leaky_fts)
    monkeypatch.setattr(backend, "visible_chunk_ids", two_phase_visible)

    reranker = FakeReranker()  # 正常 rerank——越权块已混入候选（前断言未拦）
    resp = _search(ret_stack, reranker=reranker, enhancer=None)
    assert reranker.calls, "rerank 正常执行"
    assert resp["results"] and all(r["doc_id"] == "d_ok" for r in resp["results"]), (
        "返回前二次断言必须拦下越权块（最终 top-k 干净）"
    )
    events = db.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = 'search.acl_intercept'"
    ).fetchall()
    assert events and "pre_return" in events[0][0]
    assert ok_rid in real_visible(
        ret_stack["db"].compile_acl("u_cn", "org:tax")
    )


def test_acl_08_defense_in_depth_each_guard_independent(ret_stack, monkeypatch) -> None:
    """③ 防御纵深可测：单独移除任一断言时，对应攻击面用例失败。"""
    import knowledge_lattice.core.docs.retrieve as retrieve_mod

    db, backend = ret_stack["db"], ret_stack["backend"]
    docs = _seed_acl_case(db)
    secret_rid = _rid_for(db, docs["secret_doc"])

    real_fts = backend.recall_fts

    def leaky_fts(tokens, plan, *, top_k=20):
        rows = real_fts(tokens, plan, top_k=top_k)
        return [
            {
                "rid": secret_rid, "chunk_id": "chk:d_secret:v1:1", "doc_id": "d_secret",
                "title": "秘密文档", "page_no": 1, "sheet_name": None, "score_raw": -99.0,
                "rank": 1, "content": "秘密（越权）",
                "dataset_id": "ds:vat_lib", "dataset_name": "库 ds:vat_lib",
                "source_uri": "user:u_owner", "dims": {"region": ["OS"]},
            }
        ] + rows

    monkeypatch.setattr(backend, "recall_fts", leaky_fts)

    # 移除前断言 → 越权块进入 rerank 输入（用例失败面）——但返回前断言仍拦最终输出
    monkeypatch.setattr(
        retrieve_mod, "_drop_invisible_pre_rerank", lambda *a, **k: (a[0], [])
    )
    reranker = FakeReranker()
    resp = _search(ret_stack, reranker=reranker, enhancer=None)
    assert any("越权" in d for d in reranker.calls[0][1]), (
        "移除前断言后越权块直达 rerank 输入（暴露防御纵深缺口——用例失败面）"
    )
    assert all(r["doc_id"] == "d_ok" for r in resp["results"]), "后断言兜底：最终输出仍干净"

    monkeypatch.undo()
    monkeypatch.setattr(backend, "recall_fts", leaky_fts)
    # 移除后断言 → 前断言已剔除、最终输出仍干净（两断言各自独立生效）
    monkeypatch.setattr(
        retrieve_mod, "_drop_invisible_final", lambda *a, **k: a[0]
    )
    reranker2 = FakeReranker()
    resp2 = _search(ret_stack, reranker=reranker2, enhancer=None)
    assert all("越权" not in d for d in reranker2.calls[0][1]), "前断言独立生效（剔除越权）"
    assert all(r["doc_id"] == "d_ok" for r in resp2["results"])


def test_acl_08_normal_path_zero_intercepts(ret_stack) -> None:
    """正常路径：双断言零剔除通过（无拦截审计、候选原样外发）。"""
    db, backend = ret_stack["db"], ret_stack["backend"]
    _seed_acl_case(db)
    reranker = FakeReranker()
    resp = _search(ret_stack, reranker=reranker, enhancer=None)
    assert reranker.calls and resp["results"]
    assert all(r["doc_id"] == "d_ok" for r in resp["results"])
    events = db.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = 'search.acl_intercept'"
    ).fetchall()
    assert events == [], "正常路径零剔除零审计"


def test_acl_08_rerank_response_with_out_of_range_index_degrades(ret_stack) -> None:
    """P3-9：rerank 响应 index 越界（响应注入面）——防御丢弃；全越界=无效响应
    视同失败走 rerank_skipped 降级（P3-3 联动），不伪装成功。"""
    db, backend = ret_stack["db"], ret_stack["backend"]
    docs = _seed_acl_case(db)

    class OutOfRangeReranker(FakeReranker):
        def rerank(self, query, documents, *, top_n=None):
            from knowledge_lattice.adapters.reranker import RankedDocument

            self.calls.append((query, list(documents)))
            return [
                RankedDocument(index=len(documents) + 5, relevance_score=0.99),
                RankedDocument(index=-1, relevance_score=0.98),
            ]  # 全部越界（负 index 同样非法）

    reranker = OutOfRangeReranker()
    resp = _search(ret_stack, reranker=reranker, enhancer=None)
    assert reranker.calls, "rerank 正常发起"
    assert "rerank_skipped" in resp["notice"]["degraded"], (
        "全越界响应＝无效响应——视同失败降级（P3-3），不得按「无有效项」伪装成功"
    )
    assert resp["results"] and all(r["doc_id"] == "d_ok" for r in resp["results"]), (
        "降级用 RRF 序返回——最终输出仍干净"
    )
    events = db.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = 'search.degraded'"
    ).fetchall()
    assert events and "rerank_skipped" in events[-1][0]
