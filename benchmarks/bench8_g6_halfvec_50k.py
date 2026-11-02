#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""G-6 收窄③复测（m2-5 / TC-PERF 联动——known-gaps G-6 v1.2 注记的 M2 兑现）：
**5 万档** halfvec(2560) 表达式 HNSW 索引 vs `<=>` 精确扫描——单请求 P95 +
**N=5 并发 P95 复测**（M1-5 真值 2443.2ms > 2s SLO，索引化后是否达标）+
**双路召回预算复测**（M1-5 两轮均超 300ms：R2 sqlite 440.4 / pg 405.6、
R3 pg 640.4）。

与 bench7（10 万档顺延版）的差异：本脚本为 **5 万档 + 并发 + 召回段**——
TC-PERF-01 缩档口径（1/5 万，2026-10-24 用户拍板）。形态与 bench7 同源：
- 基线：现网形态 `cv.embedding <=> q::vector`（vector 列精确扫描——
  backend.recall_vec 真实路径）；
- 对照：表达式 HNSW 索引 `(embedding::halfvec(2560)) halfvec_cosine_ops`，
  查询 `ORDER BY (cv.embedding::halfvec(2560)) <=> q::halfvec(2560)`
  （fp16 距离——名次集口径 A-17，绝对分值不跨形态比对）；
- 并发：5 线程 × 每线程独立连接（M1-5 R2 池化口径——客户端单连接串行化
  假象已作废；并发样本 = 全部请求延迟的合并分位）；
- 召回段：FTS 路 + 向量路两段 SQL 分开计时（§5.2 耗时分段口径——
  NFR-8 预算表的 recall 段）。

用法：LATTICE_PG_DSN=… uv run python benchmarks/bench8_g6_halfvec_50k.py
产物：data/bench-results/m2-5-g6-halfvec-50k.json
"""

from __future__ import annotations

import math
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from bench_common import pg_dsn, print_header, save_result, synth_vectors  # noqa: E402

N = 50_000
DIM = 2560
LABEL = "synth-embed:2560"
QUERY_ROWS = (7919, 15485863 % N, 32452843 % N, 49979687 % N, 67867979 % N,
              86028121 % N, 104395301 % N, 122949829 % N)
WARMUP = 2
RUNS = 12            # 单请求档每查询轮次（M1-5/bench7 同口径）
CONC = 5             # N=5 并发档（M1-5 真值口径）
CONC_RUNS = 12       # 每线程轮次 → 并发样本 = CONC × CONC_RUNS = 60
LIMITS = (1024, 64)  # recall_window / rerank 候选档


def _fmt_vector(row) -> str:
    return "[" + ",".join(repr(float(x)) for x in row) + "]"


def seed(conn) -> None:
    """最小矩阵 + 5 万块 + 向量（COPY——bench7 同形态）。"""
    cur = conn.cursor()
    cur.execute("INSERT INTO orgs(id, name) VALUES('org:bench', 'bench')")
    cur.execute("INSERT INTO datasets(id, org_id, name) VALUES('ds:bench', 'org:bench', 'bench')")
    cur.execute("INSERT INTO users(id, username) VALUES('u_broad', 'u_broad')")
    cur.execute("INSERT INTO user_org_memberships(user_id, org_id, role)"
                " VALUES('u_broad', 'org:bench', 'member')")
    with cur.copy(
        "COPY documents(id, org_id, dataset_id, title, content_hash, mime_type, parser,"
        " owner_user_id, raw_object_key, active_version) FROM STDIN"
    ) as cp:
        for i in range(N // 100):
            cp.write(f"doc:{i:05d}\torg:bench\tds:bench\tbench 文档 {i}\tsha256:{i}"
                     f"\ttext/plain\tdocling\tu_broad\tobjects/{i}\t1\n")
    with cur.copy(
        "COPY chunks(rid, id, doc_id, seq, version, content, content_seg) FROM STDIN"
    ) as cp:
        rid = 1
        for i in range(N // 100):
            for j in range(100):
                cp.write(f"{rid}\tchk:{rid:07d}\tdoc:{i:05d}\t{j + 1}\t1\t"
                         f"bench 块 {rid} 增值税 申报\tbench 块 {rid} 增值税 申报\n")
                rid += 1
    vectors = synth_vectors(N)
    t0 = time.perf_counter()
    with cur.copy("COPY chunk_vectors(rid, embed_model, embedding) FROM STDIN") as cp:
        for i in range(N):
            cp.write(f"{i + 1}\t{LABEL}\t{_fmt_vector(vectors[i])}\n")
    print(f"  向量 COPY {time.perf_counter() - t0:.0f}s（{N:,} × {DIM} 维）")
    cur.execute("ANALYZE chunks")
    cur.execute("ANALYZE chunk_vectors")
    conn.commit()


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[max(0, math.ceil(p * len(xs)) - 1)] * 1000


def _merge(all_stats: list[dict]) -> dict:
    p50 = sorted(s["p50_ms"] for s in all_stats)
    p95 = sorted(s["p95_ms"] for s in all_stats)
    n = len(p50)
    return {"queries": n, "p50_ms": p50[n // 2], "p95_ms": p95[n // 2],
            "p95_max_ms": p95[-1]}


def _timing(fn, *, warmup=WARMUP, runs=RUNS) -> dict:
    for _ in range(warmup):
        fn()
    xs = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        xs.append(time.perf_counter() - t0)
    xs.sort()
    return {"p50_ms": xs[len(xs) // 2] * 1000,
            "p95_ms": xs[max(0, (len(xs) * 95 + 99) // 100 - 1)] * 1000}


def main() -> int:
    import psycopg

    from knowledge_lattice.core.docs.acl import compile_acl
    from knowledge_lattice.store.postgres import migrate_db, setup_connection
    from knowledge_lattice.store.postgres.backend import PgBackend
    from knowledge_lattice.store.postgres.acl_render import render_vec_recall_select
    from knowledge_lattice.store.postgres.vec import format_vector

    print_header(f"G-6 halfvec vs 精确扫描（5 万档复测）：PG @ {N:,} × {DIM} 维")
    dsn = pg_dsn()
    schema = f"lattice_bench_g6r_{uuid.uuid4().hex[:8]}"
    raw = psycopg.connect(dsn, autocommit=True)
    out: dict = {"n": N, "dim": DIM, "conc": CONC}
    try:
        raw.execute(f'CREATE SCHEMA "{schema}"')
        raw.execute(f'SET search_path TO "{schema}", public')
        setup_connection(raw)
        migrate_db(raw)
        t0 = time.perf_counter()
        seed(raw)
        print(f"造数完成 {time.perf_counter() - t0:.0f}s")

        backend = PgBackend(raw)
        plan = compile_acl(backend, "u_broad", "org:bench", embed_model=LABEL)
        plan_fts = compile_acl(backend, "u_broad", "org:bench")
        vectors = synth_vectors(N)
        queries = [format_vector([float(x) for x in vectors[i]]) for i in QUERY_ROWS]

        def _parse(q_text: str) -> list[float]:
            return [float(x) for x in q_text.strip("[]").split(",")]

        def halfvec_rows(q_text: str, limit: int):
            sql, params = render_vec_recall_select(plan, q_text, top_k=limit)
            sql = sql.replace(
                "cv.embedding <=> %(q_vec)s::vector AS dist",
                "(cv.embedding::halfvec(2560)) <=> (%(q_vec)s::halfvec(2560)) AS dist",
            )
            return raw.execute(sql, params).fetchall()

        # ============ ① 基线：精确扫描（单请求 + 双路召回段） ============
        for limit in LIMITS:
            stats = [_timing(lambda q=q: backend.recall_vec(
                _parse(q), plan, top_k=limit)) for q in queries]
            merged = _merge(stats)
            out[f"exact_limit{limit}"] = merged
            print(f"  精确扫描 LIMIT {limit}: P50 {merged['p50_ms']}"
                  f" / P95 {merged['p95_ms']} ms")

        # 双路召回段（FTS + vec 两段——NFR-8 recall 段预算口径）
        from knowledge_lattice.adapters.tokenizer import segment_query

        tokens = segment_query("增值税 申报 指南")
        fts_stat = _timing(lambda: backend.recall_fts(tokens, plan_fts, top_k=1024))
        vec_stat = _timing(lambda q=queries[0]: backend.recall_vec(
            _parse(q), plan, top_k=1024))
        out["recall_segments_exact"] = {
            "fts_p95_ms": fts_stat["p95_ms"], "vec_p95_ms": vec_stat["p95_ms"],
            "total_p95_ms": fts_stat["p95_ms"] + vec_stat["p95_ms"],
        }
        print(f"  双路召回段（精确扫描）: FTS {fts_stat['p95_ms']:.1f} +"
              f" vec {vec_stat['p95_ms']:.1f} ="
              f" {fts_stat['p95_ms'] + vec_stat['p95_ms']:.1f} ms（预算 300ms）")

        # 精确 top-k 基准集（overlap 对照）
        exact_sets = {
            limit: {q_i: [r["rid"] for r in backend.recall_vec(
                _parse(q), plan, top_k=limit)]
                for q_i, q in enumerate(queries)}
            for limit in LIMITS
        }

        # ============ ② N=5 并发 P95（精确扫描——M1-5 真值复测） ============
        def conc_bench(run_query, *, tag: str) -> dict:
            """5 线程 × 独立连接 × CONC_RUNS 轮——合并请求样本分位。"""
            def worker(q_text: str) -> list[float]:
                cn = psycopg.connect(dsn, autocommit=True)
                try:
                    cn.execute(f'SET search_path TO "{schema}", public')
                    for _ in range(1):  # 每线程预热 1 轮
                        run_query(cn, q_text)
                    xs = []
                    for _ in range(CONC_RUNS):
                        t0 = time.perf_counter()
                        run_query(cn, q_text)
                        xs.append(time.perf_counter() - t0)
                    return xs
                finally:
                    cn.close()

            per_query = []
            for q in queries[:4]:  # 4 查询 × 5 线程（M1-5 轮询形态）
                with ThreadPoolExecutor(max_workers=CONC) as pool:
                    futures = [pool.submit(worker, q) for _ in range(CONC)]
                    samples = [x for f in futures for x in f.result()]
                per_query.append({
                    "samples": len(samples),
                    "p50_ms": _pct(samples, 0.50),
                    "p95_ms": _pct(samples, 0.95),
                })
            p95s = sorted(s["p95_ms"] for s in per_query)
            merged = {"threads": CONC, "queries": len(per_query),
                      "p50_ms": sorted(s["p50_ms"] for s in per_query)[
                          len(per_query) // 2],
                      "p95_ms": p95s[len(per_query) // 2],
                      "p95_max_ms": p95s[-1]}
            out[tag] = merged
            print(f"  {tag}: P50 {merged['p50_ms']:.1f} / P95 {merged['p95_ms']:.1f}"
                  f" / max-P95 {merged['p95_max_ms']:.1f} ms"
                  f"（SLO 2s：{'达标' if merged['p95_ms'] <= 2000 else '超标'}）")
            return merged

        def _q_exact(cn, q_text: str):
            sql, params = render_vec_recall_select(plan, q_text, top_k=1024)
            cn.execute(sql, params).fetchall()

        conc_bench(_q_exact, tag=f"exact_conc{CONC}_limit1024")

        # ============ ③ halfvec 表达式 HNSW 索引 ============
        raw.execute("SET maintenance_work_mem = '256MB'")
        t0 = time.perf_counter()
        raw.execute(
            "CREATE INDEX ix_cv_halfvec_hnsw ON chunk_vectors"
            " USING hnsw ((embedding::halfvec(2560)) halfvec_cosine_ops)"
            " WITH (m = 16, ef_construction = 64)"
        )
        build_s = time.perf_counter() - t0
        raw.execute("ANALYZE chunk_vectors")
        out["index_build_s"] = round(build_s, 1)
        print(f"  halfvec HNSW 索引构建 {build_s:.0f}s（m=16, ef_construction=64）")

        explain = raw.execute(
            "EXPLAIN (COSTS OFF) SELECT c.rid FROM chunks c"
            " JOIN chunk_vectors cv ON cv.rid = c.rid AND cv.embed_model = %(l)s"
            " ORDER BY (cv.embedding::halfvec(2560)) <=> (%(q)s::halfvec(2560))"
            " LIMIT 64", {"l": LABEL, "q": queries[0]},
        ).fetchall()
        plan_text = "\n".join(r[0] for r in explain)
        out["index_plan_uses_hnsw"] = "hnsw" in plan_text.lower()
        print(f"  LIMIT 64 计划命中 HNSW 索引：{out['index_plan_uses_hnsw']}")

        # ============ ④ halfvec：单请求 + overlap + 并发 + 召回段 ============
        for limit in LIMITS:
            all_stats, overlap = [], []
            for q_i, q in enumerate(queries):
                all_stats.append(_timing(lambda q=q, lim=limit: halfvec_rows(q, lim)))
                got = {r[0] for r in halfvec_rows(q, limit)}
                want = set(exact_sets[limit][q_i][:limit])
                overlap.append(len(got & want) / len(want) if want else 1.0)
            merged = _merge(all_stats)
            merged["overlap_at_k_vs_exact"] = round(
                sum(overlap) / len(overlap), 4)
            out[f"halfvec_limit{limit}"] = merged
            print(f"  halfvec HNSW LIMIT {limit}: P50 {merged['p50_ms']} /"
                  f" P95 {merged['p95_ms']} ms，overlap@k="
                  f"{merged['overlap_at_k_vs_exact']}")

        # ④b iterative_scan=strict_order（pgvector ≥0.8——G-6 ③「HNSW 带 ACL
        #     过滤欠召回」的对冲配置）：默认档欠召回时（LIMIT 64 典型），
        #     strict_order 逐批扩扫直到序完整——overlap 修复幅度与延迟代价
        for limit in LIMITS:
            raw.execute("SET hnsw.iterative_scan = strict_order")
            try:
                all_stats, overlap = [], []
                for q_i, q in enumerate(queries):
                    all_stats.append(_timing(
                        lambda q=q, lim=limit: halfvec_rows(q, lim)))
                    got = {r[0] for r in halfvec_rows(q, limit)}
                    want = set(exact_sets[limit][q_i][:limit])
                    overlap.append(len(got & want) / len(want) if want else 1.0)
                merged = _merge(all_stats)
                merged["overlap_at_k_vs_exact"] = round(
                    sum(overlap) / len(overlap), 4)
                out[f"halfvec_strict_limit{limit}"] = merged
                print(f"  halfvec strict_order LIMIT {limit}: P50"
                      f" {merged['p50_ms']} / P95 {merged['p95_ms']} ms，"
                      f"overlap@k={merged['overlap_at_k_vs_exact']}")
            finally:
                raw.execute("SET hnsw.iterative_scan = 'off'")

        # ④c ef_search 扩宽（欠召回根因诊断：默认 ef_search=40 < k=64——
        #     HNSW 图搜索宽度不足时 top-k 近似质量塌陷，与 iterative_scan
        #     （过滤扩扫）是两个正交机制）。ef=256/1024 两档验证。
        for ef in (256, 1000):
            raw.execute(f"SET hnsw.ef_search = {ef}")
            try:
                overlap = []
                for q_i, q in enumerate(queries):
                    got = {r[0] for r in halfvec_rows(q, 64)}
                    want = set(exact_sets[64][q_i][:64])
                    overlap.append(len(got & want) / len(want) if want else 1.0)
                stat = _timing(lambda q=queries[0]: halfvec_rows(q, 64))
                out[f"halfvec_ef{ef}_limit64"] = {
                    "p50_ms": stat["p50_ms"], "p95_ms": stat["p95_ms"],
                    "overlap_at_k_vs_exact": round(
                        sum(overlap) / len(overlap), 4),
                }
                print(f"  halfvec ef_search={ef} LIMIT 64: P95"
                      f" {stat['p95_ms']:.1f} ms，overlap@64="
                      f"{out[f'halfvec_ef{ef}_limit64']['overlap_at_k_vs_exact']}")
            finally:
                raw.execute("SET hnsw.ef_search = 40")

        def _q_halfvec(cn, q_text: str):
            sql, params = render_vec_recall_select(plan, q_text, top_k=1024)
            sql = sql.replace(
                "cv.embedding <=> %(q_vec)s::vector AS dist",
                "(cv.embedding::halfvec(2560)) <=> (%(q_vec)s::halfvec(2560)) AS dist",
            )
            cn.execute(sql, params).fetchall()

        conc_bench(_q_halfvec, tag=f"halfvec_conc{CONC}_limit1024")

        idx_size = raw.execute(
            "SELECT pg_relation_size('ix_cv_halfvec_hnsw')").fetchone()[0]
        out["index_bytes"] = int(idx_size)
        print(f"  索引体积 {int(idx_size) / 1024**2:.0f} MB")
    finally:
        try:
            raw.execute("SET search_path TO public")
            raw.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except psycopg.Error:
            pass
        finally:
            raw.close()

    path = save_result("m2-5-g6-halfvec-50k", out)
    print(f"工件：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
