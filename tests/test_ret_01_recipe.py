"""TC-RET-01~07 检索配方（M1 全配方——双后端参数化各跑）。

覆盖（TEST-CASES §二 TC-RET 组）：
- 01 RRF 融合（k=60 手算期望序列；单路 chunk 自然保留）；
- 02 向量缺失退化（searchable_lexical 中间态 BM25 可搜 + vector_pending）；
- 03 分数归一（min-max/clamp 双分支——ragflow 模式；阈值只作用于归一后分数）；
- 04 rerank 输入与候选（content 原文 / 候选 32 / 并发信号量 / 线程池不阻塞事件循环）；
- 05 LLM 增强 800ms 并行（超预算丢弃、总延迟不受影响）；
- 06 双降级开关（rerank 输入截断 256 token / 候选 32→16）；
- 07 参数红线（M1 半句：不可调参数被忽略）+ TC-E2E-01 检索侧（摄取→全配方→溯源字段）。

FTS 评分差异按名次集等价断言（A-17/G-6）：BM25 路名次由五列权重钉死（单列单
token 命中——权重主导排序，双后端名次集一致）；融合序断言在名次集等价下成立。
"""

from __future__ import annotations

import time

from fake_providers import FakeEmbedder, FakeEnhancer, FakeReranker, FixedVecEmbedder
from helpers import insert_chunk, seed_doc_dims, seed_document


# ============ 造数 helpers（本文件族共享形态） ============


def _add_chunk(db, *, doc_id, seq, content="占位", **cols):
    """可控列块造数（未列出的 FTS 列一律空——纯命中前提）。"""
    base = {
        "content": content,
        "title_seg": "",
        "content_seg": "",
        "keywords": "",
        "llm_keywords": "",
        "tags": "",
    }
    base.update(cols)
    return insert_chunk(db, doc_id=doc_id, seq=seq, version=1, **base)


def _embed_doc(backend, embedder, *, doc_id, label):
    """走后端写路径为整篇在用块补向量（mark → embed → write）。"""
    rows = backend.mark_embedding_batch(doc_id, 1, label)
    backend.write_embeddings(
        label, [(r["rid"], embedder.embed([r["content"]])[0]) for r in rows]
    )
    return rows


# ============ TC-RET-01 RRF 融合（k=60 手算） ============


def _seed_rrf_case(db, backend):
    """四块已知名次造数（doc d_rr，region=[CN]/tax_type=[VAT]——u_full 可见）：

    FTS 路（五列权重 8/5/3/1/0.5——tags>keywords>title>content）：
      X=rank1（tags）、Y=rank2（keywords）、W=rank3（title_seg）、Z=rank4（content_seg）
    向量路（qv=[1,0,0,0] 余弦距离）：Y=rank1（dist 0）、W=rank2（dist≈0.293）、
      X=rank3（dist 1）、Z 无向量行（不进向量路）
    手算 RRF(k=60)：Y=1/62+1/61 > X=1/61+1/63 > W=1/63+1/62 > Z=1/64（仅 BM25）
    """
    seed_document(db, doc_id="d_rr", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_rr", {"region": ["CN"], "tax_type": ["VAT"]})
    _add_chunk(db, doc_id="d_rr", seq=1, tags="增值税", content="X 原文")
    _add_chunk(db, doc_id="d_rr", seq=2, keywords="增值税", content="Y 原文")
    _add_chunk(db, doc_id="d_rr", seq=3, title_seg="增值税", content="W 原文")
    _add_chunk(db, doc_id="d_rr", seq=4, content_seg="增值税", content="Z 原文")
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_rr'")
    db.commit()
    # 向量直插（手工构造距离序——精确可控）
    rids = [r[0] for r in db.execute(
        "SELECT rid FROM chunks WHERE doc_id = 'd_rr' ORDER BY seq"
    ).fetchall()]
    qv_align = [1.0, 0.0, 0.0, 0.0]     # Y：与查询向量同向（dist 0）
    qv_mid = [0.7071067811865476, 0.7071067811865476, 0.0, 0.0]  # W：dist≈0.293
    qv_orth = [0.0, 1.0, 0.0, 0.0]      # X：正交（dist 1）
    return {"X": rids[0], "Y": rids[1], "W": rids[2], "Z": rids[3]}, qv_align, qv_mid, qv_orth


def test_ret_01_rrf_fusion_matches_hand_computed(ret_stack) -> None:
    """融合排序与手算 RRF(k=60) 一致；仅 BM25 路的 Z 自然保留（退化兼容）。"""
    from knowledge_lattice.core.docs.retrieve import search

    db, backend, settings = ret_stack["db"], ret_stack["backend"], ret_stack["settings"]
    rids, qv, _, _ = _seed_rrf_case(db, backend)
    # 向量行按手工距离序写入（label 与查询嵌入器一致——FixedVecEmbedder 4 维）
    embedder = FixedVecEmbedder(qv, model_name="fake-embed")
    label = embedder.model_label
    db.insert_vector(rids["Y"], label, qv)
    db.insert_vector(rids["W"], label, [0.7071067811865476, 0.7071067811865476, 0.0, 0.0])
    db.insert_vector(rids["X"], label, [0.0, 1.0, 0.0, 0.0])
    db.commit()

    resp = search(
        backend, settings,
        user_id="u_full", org_id="org:tax", query="增值税",
        top_k=10, embedder=embedder, reranker=None, enhancer=None,
    )
    order = [r["chunk_id"] for r in resp["results"]]
    expected_map = {rids[k]: f"chk:d_rr:v1:{i}" for i, k in enumerate(("X", "Y", "W", "Z"), 1)}
    # 手算序 Y > X > W > Z（k=60：Y=1/62+1/61 ≈ 0.032515；X=1/61+1/63 ≈ 0.032265；
    # W=1/63+1/62 ≈ 0.032005；Z=1/64 = 0.015625——仅 BM25 单路保留）
    assert order == [
        expected_map[rids["Y"]], expected_map[rids["X"]],
        expected_map[rids["W"]], expected_map[rids["Z"]],
    ], f"RRF 融合序应与手算一致，got {order}"
    # rank 协议：1 起连续
    assert [r["rank"] for r in resp["results"]] == [1, 2, 3, 4]
    # 归一分 ∈ [0,1] 且 top=1.0（min-max）
    assert resp["results"][0]["score"] == 1.0
    assert all(0.0 <= r["score"] <= 1.0 for r in resp["results"])


def test_ret_01_rrf_fuse_unit() -> None:
    """RRF 融合函数单测（k=60；单路/并列 tie-break 按 rid 稳定）。"""
    from knowledge_lattice.core.docs.retrieve import rrf_fuse

    fused = rrf_fuse([("fts", [11, 12, 13]), ("vec", [12, 11])], k=60)
    # 11=1/61+1/62、12=1/62+1/61（相等→rid 小者先）、13=1/63 仅 FTS
    assert [rid for rid, _ in fused] == [11, 12, 13]
    assert abs(fused[0][1] - (1 / 61 + 1 / 62)) < 1e-12
    single = rrf_fuse([("fts", [7])], k=60)
    assert single == [(7, 1 / 61)]  # 单路 chunk 按该路 RRF 分自然保留


# ============ TC-RET-02 向量缺失退化 ============


def test_ret_02_vector_missing_degrades_to_bm25(ret_stack) -> None:
    """searchable_lexical（块无 cv 行）：BM25 单路可搜、vector_pending=true、无异常。"""
    from knowledge_lattice.core.docs.retrieve import search

    db, backend, settings, embedder = (
        ret_stack["db"], ret_stack["backend"], ret_stack["settings"], ret_stack["embedder"],
    )
    seed_document(db, doc_id="d_lex", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_lex", {"region": ["CN"]})
    _add_chunk(db, doc_id="d_lex", seq=1, content_seg="印花税 全文", content="中间态原文")
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_lex'")
    db.commit()
    # 不写任何向量行（searchable_lexical 等价形态——embedding 全缺）

    resp = search(
        backend, settings,
        user_id="u_full", org_id="org:tax", query="印花税",
        top_k=8, embedder=embedder, reranker=None, enhancer=None,
    )
    assert resp["results"], "向量缺失时 BM25 单路应可搜（无空结果误判）"
    assert resp["notice"]["vector_pending"] is True
    assert resp["notice"]["degraded"] == []  # 块未就绪不是服务降级


def test_ret_02_vector_present_clears_pending(ret_stack) -> None:
    """结果块全部有当前标签向量 → vector_pending=false（块级状态置位口径）。"""
    from knowledge_lattice.core.docs.retrieve import search

    db, backend, settings, embedder = (
        ret_stack["db"], ret_stack["backend"], ret_stack["settings"], ret_stack["embedder"],
    )
    seed_document(db, doc_id="d_vec", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_vec", {"region": ["CN"]})
    _add_chunk(db, doc_id="d_vec", seq=1, content_seg="关税", content="完成态原文")
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_vec'")
    db.commit()
    _embed_doc(backend, embedder, doc_id="d_vec", label=settings.embed_model_label)

    resp = search(
        backend, settings,
        user_id="u_full", org_id="org:tax", query="关税",
        top_k=8, embedder=embedder, reranker=None, enhancer=None,
    )
    assert resp["results"]
    assert resp["notice"]["vector_pending"] is False
    assert resp["notice"]["degraded"] == []


# ============ TC-RET-03 分数归一（min-max / clamp 双分支） ============


def test_ret_03_normalize_unit() -> None:
    """归一函数双分支：集中分布 min-max；含离群 clamp(IQR) 后 min-max（主体不被压扁）。"""
    from knowledge_lattice.core.docs.retrieve import normalize_scores

    # 集中分布 → min-max 分支，保序、值域 [0,1]
    out, branch = normalize_scores([0.2, 0.25, 0.3, 0.22])
    assert branch == "minmax"
    assert out[0] == 0.0 and out[2] == 1.0
    assert out[1] == 0.5 and out[3] == 0.2  # 保序（0.25→0.5 / 0.22→0.2）

    # 含离群（0.98 ≫ 主体）→ clamp 分支：离群压到上界、主体区分度保留
    out_c, branch_c = normalize_scores([0.2, 0.21, 0.22, 0.23, 0.98])
    assert branch_c == "clamp"
    assert out_c[4] == 1.0 and out_c[0] == 0.0
    # 主体间距不被离群压扁：纯 min-max 下 (0.23-0.2)/0.78≈0.038；clamp 后显著放大
    assert out_c[3] >= 0.4, "clamp 分支应保留主体区分度（ragflow 模式离群隔离）"

    # 单值/等值不崩溃
    assert normalize_scores([0.5]) == ([1.0], "minmax")
    assert normalize_scores([0.5, 0.5]) == ([1.0, 1.0], "minmax")


def test_ret_03_threshold_applies_post_normalize(ret_stack) -> None:
    """阈值只作用于归一后分数（score_threshold 过滤归一分；召回期不做阈值过滤）。"""
    import dataclasses

    from knowledge_lattice.core.docs.retrieve import search

    db, backend = ret_stack["db"], ret_stack["backend"]
    seed_document(db, doc_id="d_thr", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_thr", {"region": ["CN"]})
    # 三块命中：tags/keywords/content（rerank 分数覆写集中分布）
    _add_chunk(db, doc_id="d_thr", seq=1, tags="增值税", content="A 原文")
    _add_chunk(db, doc_id="d_thr", seq=2, keywords="增值税", content="B 原文")
    _add_chunk(db, doc_id="d_thr", seq=3, content_seg="增值税", content="C 原文")
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_thr'")
    db.commit()

    settings = dataclasses.replace(
        ret_stack["settings"], reranker="cohere",
        rerank_truncate_tokens=None, score_threshold=0.55,
    )
    reranker = FakeReranker(scores={0: 0.90, 1: 0.60, 2: 0.10})  # 归一后 1.0 / 0.625 / 0.0
    resp = search(
        backend, settings,
        user_id="u_full", org_id="org:tax", query="增值税",
        top_k=8, embedder=ret_stack["embedder"], reranker=reranker, enhancer=None,
    )
    got = [r["snippet"] for r in resp["results"]]
    assert got == ["A 原文", "B 原文"], "归一分 0.0 的 C 应被阈值滤除（只作用于归一后分数）"
    assert [r["score"] for r in resp["results"]] == [1.0, 0.625]


def test_ret_03_outlier_scores_do_not_flatten(ret_stack) -> None:
    """rerank 分含离群 → clamp 分支集成路径：主体块分数区分度保留、值域 [0,1]。"""
    import dataclasses

    from knowledge_lattice.core.docs.retrieve import search

    db, backend = ret_stack["db"], ret_stack["backend"]
    seed_document(db, doc_id="d_out", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_out", {"region": ["CN"]})
    _add_chunk(db, doc_id="d_out", seq=1, tags="所得税", content="A 原文")
    _add_chunk(db, doc_id="d_out", seq=2, keywords="所得税", content="B 原文")
    _add_chunk(db, doc_id="d_out", seq=3, title_seg="所得税", content="C 原文")
    _add_chunk(db, doc_id="d_out", seq=4, content_seg="所得税", content="D 原文")
    _add_chunk(db, doc_id="d_out", seq=5, llm_keywords="所得税", content="E 原文")
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_out'")
    db.commit()

    settings = dataclasses.replace(ret_stack["settings"], reranker="cohere")
    reranker = FakeReranker(scores={0: 0.98, 1: 0.20, 2: 0.21, 3: 0.22, 4: 0.23})
    resp = search(
        backend, settings,
        user_id="u_full", org_id="org:tax", query="所得税",
        top_k=8, embedder=ret_stack["embedder"], reranker=reranker, enhancer=None,
    )
    scores = [r["score"] for r in resp["results"]]
    assert all(0.0 <= s <= 1.0 for s in scores)
    # 主体（B..E）在 clamp 后仍有区分度：B 与 E 的归一分差 > 纯 min-max 的 0.038
    by_snippet = {r["snippet"]: r["score"] for r in resp["results"]}
    assert by_snippet["E 原文"] - by_snippet["B 原文"] > 0.1


# ============ TC-RET-04 rerank 输入与候选（32 / 原文 / 信号量） ============


def _seed_many_hits(db, *, n=40, word="增值税") -> None:
    seed_document(db, doc_id="d_many", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_many", {"region": ["CN"]})
    for i in range(1, n + 1):
        _add_chunk(
            db, doc_id="d_many", seq=i,
            content_seg=f"{word} 序{i}",
            content=f"{word}原文序{i}",  # 原文形态与分词形态可区分（断言喂原文）
        )
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_many'")
    db.commit()


def test_ret_04_rerank_input_content_and_candidate_32(ret_stack) -> None:
    """rerank 输入=content 原文（非分词文本）、候选截断 32（NFR-8）。"""
    import dataclasses

    from knowledge_lattice.core.docs.retrieve import search

    db, backend = ret_stack["db"], ret_stack["backend"]
    _seed_many_hits(db)
    settings = dataclasses.replace(ret_stack["settings"], reranker="cohere")
    reranker = FakeReranker()
    search(
        backend, settings,
        user_id="u_full", org_id="org:tax", query="增值税",
        top_k=8, embedder=ret_stack["embedder"], reranker=reranker, enhancer=None,
    )
    assert len(reranker.calls) == 1
    query_got, docs_got = reranker.calls[0]
    assert query_got == "增值税"
    assert len(docs_got) == 32, "rerank 候选硬截断 32"
    for d in docs_got:
        assert d.startswith("增值税原文序"), "rerank 须喂 content 原文（非分词文本）"
        assert " " not in d, "分词形态（空格连接）不得进入 rerank 输入"


def test_ret_04_rerank_semaphore_and_event_loop_not_blocked(tmp_path) -> None:
    """并发请求下 rerank 信号量生效（峰值=上限）+ 模型调用经线程池不阻塞事件循环。"""
    import asyncio

    import httpx

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from helpers import (
        dim_id_for,
        seed_dataset,
        seed_dim_value,
        seed_dimension,
        seed_grant,
        seed_membership,
        seed_org,
        seed_user,
        val_id_for,
    )
    from knowledge_lattice.store.sqlite import connect

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8, embed_model="fake-embed",
        reranker="cohere", rerank_max_concurrency=2,
    )
    reranker = FakeReranker(delay_s=0.15, track_concurrency=True)
    app = create_app(
        settings, embedder=FakeEmbedder(dim=8, model_name="fake-embed"),
        gate=EmbeddingGate(), reranker=reranker, run_startup_probe=False,
    )

    conn = connect(settings.db_path)
    seed_org(conn, "org:tax")
    seed_dataset(conn, "org:tax", "ds:vat_lib")
    seed_dimension(conn, "org:tax", "region")
    seed_dim_value(conn, dim_id_for("org:tax", "region"), "CN")
    seed_user(conn, "u_full")
    seed_membership(conn, "u_full", "org:tax")
    seed_grant(
        conn, user_id="u_full", dim_id=dim_id_for("org:tax", "region"),
        val_id=val_id_for("org:tax", "region", "CN"),
    )
    from knowledge_lattice.domain.auth import hash_token

    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = 'u_full'",
        (hash_token("u_full-token"),),
    )
    _seed_many_hits_conn(conn)
    conn.commit()
    conn.close()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            t0 = time.monotonic()
            responses = await asyncio.gather(*[
                client.post(
                    "/api/search",
                    json={"query": "增值税", "top_k": 5},
                    headers={
                        "Authorization": "Bearer u_full-token",
                        "X-Org-Id": "org:tax",
                    },
                )
                for _ in range(4)
            ])
            elapsed = time.monotonic() - t0
        return responses, elapsed

    responses, elapsed = asyncio.run(run())
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert reranker.concurrency_peak == 2, "并发信号量：rerank 峰值=上限 2（第 3/4 个等待）"
    # rerank 段 2 批 ×0.15s（信号量=2 并行两批）——串行 4×0.15=0.6 起步，并行应显著低于
    assert elapsed < 0.5, f"并发 4 请求总耗时 {elapsed:.2f}s——rerank 应并行分批而非串行"


def _seed_many_hits_conn(conn, *, n=12, word="增值税") -> None:
    """app 并发用命中块（sqlite 直连造数——同 _seed_many_hits 形态）。"""
    from helpers import insert_chunk, seed_doc_dims, seed_document

    seed_document(conn, doc_id="d_many", dataset_id="ds:vat_lib", owner_user_id="u_full")
    seed_doc_dims(conn, "d_many", {"region": ["CN"]})
    for i in range(1, n + 1):
        insert_chunk(
            conn, doc_id="d_many", seq=i,
            content=f"{word}原文序{i}",
            content_seg=f"{word} 序{i}", title_seg="", keywords="", llm_keywords="", tags="",
        )
    conn.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_many'")


# ============ TC-RET-05 LLM 增强 800ms 并行窗口 ============


def _seed_enhance_case(db) -> None:
    seed_document(db, doc_id="d_enh", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_enh", {"region": ["CN"]})
    _add_chunk(db, doc_id="d_enh", seq=1, content_seg="增值税", content="主路原文")
    _add_chunk(db, doc_id="d_enh", seq=2, content_seg="消费税", content="增强路原文")
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_enh'")
    db.commit()


def test_ret_05_enhancement_within_budget_joins_rrf(ret_stack) -> None:
    """增强 <800ms 窗口：词条作为第三路 BM25 参与融合（不重做向量召回）。"""
    import dataclasses

    from knowledge_lattice.core.docs.retrieve import search

    db, backend = ret_stack["db"], ret_stack["backend"]
    _seed_enhance_case(db)
    settings = dataclasses.replace(
        ret_stack["settings"], enhancer="openai", enhance_budget_s=0.5,
    )
    enhancer = FakeEnhancer(terms=["消费税"], delay_s=0.1)
    resp = search(
        backend, settings,
        user_id="u_full", org_id="org:tax", query="增值税",
        top_k=8, embedder=ret_stack["embedder"], reranker=None, enhancer=enhancer,
    )
    snippets = [r["snippet"] for r in resp["results"]]
    assert "主路原文" in snippets and "增强路原文" in snippets, (
        "增强词命中的块应经第三路 BM25 进入融合结果"
    )
    # 不重做向量召回：增强词只产 BM25 路（增强块无向量行 → 只在第三路/主 BM25 路）
    assert enhancer.calls == ["增值税"]


def test_ret_05_enhancement_timeout_dropped(ret_stack) -> None:
    """增强超 800ms 预算：丢弃、原始两路结果不变、总延迟 ≈ 预算（并行不拖慢）。"""
    import dataclasses

    from knowledge_lattice.core.docs.retrieve import search

    db, backend = ret_stack["db"], ret_stack["backend"]
    _seed_enhance_case(db)
    settings = dataclasses.replace(
        ret_stack["settings"], enhancer="openai", enhance_budget_s=0.25,
    )
    enhancer = FakeEnhancer(terms=["消费税"], delay_s=0.9)  # 远超预算
    t0 = time.monotonic()
    resp = search(
        backend, settings,
        user_id="u_full", org_id="org:tax", query="增值税",
        top_k=8, embedder=ret_stack["embedder"], reranker=None, enhancer=enhancer,
    )
    elapsed = time.monotonic() - t0
    snippets = [r["snippet"] for r in resp["results"]]
    assert snippets == ["主路原文"], "超时增强丢弃——原始结果不受增强路影响"
    assert resp["notice"]["degraded"] == [], "增强超时是预算行为，不标降级"
    assert elapsed < 0.45, f"总延迟 {elapsed:.2f}s——并行窗口应在预算到点即放弃增强"


def test_ret_05_enhancement_failure_dropped(ret_stack) -> None:
    """增强端点失败：丢弃（不 500、不降级标注——增强是增益路非可用性前提）。"""
    import dataclasses

    from knowledge_lattice.core.docs.retrieve import search

    db, backend = ret_stack["db"], ret_stack["backend"]
    _seed_enhance_case(db)
    settings = dataclasses.replace(
        ret_stack["settings"], enhancer="openai", enhance_budget_s=0.5,
    )
    enhancer = FakeEnhancer(fail=True)
    resp = search(
        backend, settings,
        user_id="u_full", org_id="org:tax", query="增值税",
        top_k=8, embedder=ret_stack["embedder"], reranker=None, enhancer=enhancer,
    )
    assert [r["snippet"] for r in resp["results"]] == ["主路原文"]
    assert resp["notice"]["degraded"] == []


# ============ TC-RET-06 双降级开关（截断 256 / 候选 32→16） ============


def test_ret_06_truncate_and_candidate_switches(ret_stack) -> None:
    """开关①输入截断 256 token（jieba token 边界）②候选 32→16：生效且结果仍正确。"""
    import dataclasses

    from knowledge_lattice.adapters.tokenizer import segment
    from knowledge_lattice.core.docs.retrieve import search

    db, backend = ret_stack["db"], ret_stack["backend"]
    # 长文块：content 原文 >256 jieba token
    seed_document(db, doc_id="d_long", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_long", {"region": ["CN"]})
    long_content = "增值税专用发票" * 160  # jieba 2 token/重复 ×160 = 320 > 256（实测锚点）
    _add_chunk(db, doc_id="d_long", seq=1, content_seg="增值税", content=long_content)
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_long'")
    db.commit()
    assert len(segment(long_content)) > 256, "造数前提：原文超 256 token"

    settings = dataclasses.replace(
        ret_stack["settings"], reranker="cohere",
        rerank_truncate_tokens=256, rerank_candidates=16,
    )
    reranker = FakeReranker()
    _seed_many_hits(db, n=40, word="增值税")  # 另 40 短块命中（候选足够）
    resp = search(
        backend, settings,
        user_id="u_full", org_id="org:tax", query="增值税",
        top_k=8, embedder=ret_stack["embedder"], reranker=reranker, enhancer=None,
    )
    _, docs_got = reranker.calls[0]
    assert len(docs_got) == 16, "开关②：候选 32→16 生效"
    long_docs = [d for d in docs_got if "专用发票" in d]
    assert long_docs, "长文块应在候选内"
    assert all(len(segment(d)) <= 256 for d in long_docs), "开关①：输入截断 256 token 生效"
    assert len(docs_got[0]) > 0 and resp["results"], "降级路径结果仍正确（只是召回宽度变化）"


# ============ TC-RET-07② 不可调参数被忽略 + TC-E2E-01 检索侧（全配方） ============


def test_ret_07_tunable_params_ignored(app_env) -> None:
    """M1 半句：权重/阈值类参数不可调——请求体携带被忽略（服务端固定，行为不变）。"""
    from helpers import insert_chunk, seed_doc_dims, seed_document

    conn = app_env["conn"]
    seed_document(conn, doc_id="d_p7", dataset_id="ds:vat_lib", owner_user_id="u_full")
    seed_doc_dims(conn, "d_p7", {"region": ["CN"]})
    insert_chunk(
        conn, doc_id="d_p7", seq=1, content="红线参数原文",
        content_seg="红线 参数 原文", title_seg="", keywords="", llm_keywords="", tags="",
    )
    conn.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_p7'")
    conn.commit()

    headers = {"Authorization": f"Bearer {app_env['static']['u_full']}", "X-Org-Id": "org:tax"}
    plain = app_env["client"].post(
        "/api/search", json={"query": "红线 参数", "top_k": 8}, headers=headers
    )
    noisy = app_env["client"].post(
        "/api/search",
        json={
            "query": "红线 参数", "top_k": 8,
            "rrf_k": 1, "weights": {"title": 99}, "score_threshold": 0.99,
            "rerank_candidates": 1, "bm25_args": "0,0,0,0,0",
        },
        headers=headers,
    )
    assert plain.status_code == 200 and noisy.status_code == 200
    assert noisy.json()["results"] == plain.json()["results"], (
        "检索参数（权重/阈值/召回窗口）服务端固定——请求体噪音旋钮必须被忽略（§6.1 纪律）"
    )
    assert noisy.json()["results"]


def test_e2e_01_full_recipe_backend(ret_stack) -> None:
    """TC-E2E-01 检索侧（M1 全配方·双后端）：双路 + RRF + rerank 命中 + 溯源字段齐备。"""
    import dataclasses

    from knowledge_lattice.core.docs.retrieve import search

    db, backend, settings = ret_stack["db"], ret_stack["backend"], ret_stack["settings"]
    seed_document(db, doc_id="d_e2e", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_e2e", {"region": ["CN"], "tax_type": ["VAT"]})
    db.execute(
        "UPDATE documents SET source_uri = 'user:u_owner' WHERE id = 'd_e2e'"
    )  # 溯源形态对齐上传链（user:<uid>——M0a e2e 同款断言前提）
    _add_chunk(db, doc_id="d_e2e", seq=1, content_seg="增值税", content="全链原文")
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_e2e'")
    db.commit()
    _embed_doc(backend, ret_stack["embedder"], doc_id="d_e2e", label=settings.embed_model_label)

    full = dataclasses.replace(settings, reranker="cohere")
    resp = search(
        backend, full,
        user_id="u_full", org_id="org:tax", query="增值税",
        top_k=8, embedder=ret_stack["embedder"],
        reranker=FakeReranker(), enhancer=None,
    )
    assert resp["results"], "searchable_full 后双路+rerank 应命中"
    top = resp["results"][0]
    for field in ("chunk_id", "doc_id", "title", "page_no", "score", "dims", "source"):
        assert field in top, f"缺溯源字段 {field}（MCP 契约 §6.1）"
    assert top["dims"] == {"region": ["CN"], "tax_type": ["VAT"]}
    assert top["source"] == "user:u_owner"
    assert 0.0 <= top["score"] <= 1.0
    # 全配方无降级：双路 + rerank 均正常
    assert resp["notice"]["degraded"] == []
    assert resp["notice"]["vector_pending"] is False

    # datasets 过滤与 doc_filter 正确收窄（基线因子「库过滤」单测形态）
    narrowed = search(
        backend, full, user_id="u_full", org_id="org:tax", query="增值税",
        top_k=8, datasets=["ds:vat_lib"], embedder=ret_stack["embedder"],
        reranker=FakeReranker(), enhancer=None,
    )
    assert narrowed["results"]
    excluded = search(
        backend, full, user_id="u_full", org_id="org:tax", query="增值税",
        top_k=8, datasets=["ds:not_exist"], embedder=ret_stack["embedder"],
        reranker=FakeReranker(), enhancer=None,
    )
    assert excluded["results"] == []
    by_doc = search(
        backend, full, user_id="u_full", org_id="org:tax", query="增值税",
        top_k=8, doc_filter=["d_e2e"], embedder=ret_stack["embedder"],
        reranker=FakeReranker(), enhancer=None,
    )
    assert by_doc["results"] and all(r["doc_id"] == "d_e2e" for r in by_doc["results"])
