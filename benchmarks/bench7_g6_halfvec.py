#!/usr/bin/env python
"""G-6 收窄③评估（M1-5 / TC-PERF 联动）：2560 维 `<=>` 精确扫描 vs halfvec
表达式索引——10 万块 P95 对比（known-gaps G-6；公司环境 PG 16 + pgvector 0.8.x）。

> **状态：顺延未执行（2026-10-26 用户裁定）**——10 万块基准本段跳过（非 M1
> 验收硬门槛；G-6 收窄③顺延）。脚本保留入库，供后续段复跑；断点现象（定性）：
> 造数（COPY 100k×2560 向量文本 ~5GB）+ HNSW 表达式索引构建在 3.8GB 内存
> 容器上预计 15~30 分钟量级，单次会话时间预算内无法与 M1 收口批并行完成。

形态（官方文档路线——G-6 已核对 halfvec ≥0.7 / 索引上限 4000 维）：
- 基线：现网形态 `cv.embedding <=> q::vector`（vector 列精确扫描——M0b-3 起步
  口径，无索引）；
- 对照：表达式 HNSW 索引 `(embedding::halfvec(2560)) halfvec_cosine_ops`，查询
  `ORDER BY (cv.embedding::halfvec(2560)) <=> q::halfvec(2560)`（fp16 距离——
  与 float32 绝对分值不跨形态比对，名次集口径 A-17）。

两取数档：LIMIT 1024（config.recall_window——NFR-8 召回窗口）与 LIMIT 64
（rerank 候选档——索引收益敏感区）；8 查询 × 预热 2 + n=12。
召回对照：top-k rid 集与精确扫描的重叠率（overlap@k——halfvec 质量损失口径）。

用法：LATTICE_PG_DSN=... uv run python benchmarks/bench7_g6_halfvec.py
产物：data/bench-results/m1-5-g6-halfvec-100k.json
"""

from __future__ import annotations

import math
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from bench_common import pg_dsn, print_header, save_result, synth_vectors  # noqa: E402

N = 100_000
DIM = 2560
LABEL = "synth-embed:2560"
QUERY_ROWS = (7919, 15485863 % N, 32452843 % N, 49979687 % N, 67867979 % N,
              86028121 % N, 104395301 % N, 122949829 % N)
WARMUP = 2
RUNS = 12
LIMITS = (1024, 64)


def _fmt_vector(row) -> str:
    return "[" + ",".join(repr(float(x)) for x in row) + "]"


def seed(conn) -> None:
    """最小矩阵 + 10 万块 + 向量（COPY 批量）。"""
    cur = conn.cursor()
    cur.execute("INSERT INTO orgs(id, name) VALUES('org:bench', 'bench')")
    cur.execute("INSERT INTO datasets(id, org_id, name) VALUES('ds:bench', 'org:bench', 'bench')")
    cur.execute("INSERT INTO users(id, username) VALUES('u_broad', 'u_broad')")
    cur.execute("INSERT INTO user_org_memberships(user_id, org_id, role)"
                " VALUES('u_broad', 'org:bench', 'member')")
    # 1000 文档 × 100 块（COPY 最小列集——vec 路不触 FTS/dims 列）
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


def _timing(fn) -> dict:
    for _ in range(WARMUP):
        fn()
    xs = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        rows = fn()
        xs.append((time.perf_counter() - t0) * 1000)
        _ = rows
    xs.sort()
    n = len(xs)
    return {
        "p50_ms": round(xs[n // 2], 1),
        "p95_ms": round(xs[max(0, (n * 95 + 99) // 100 - 1)], 1),
    }


def main() -> int:
    import psycopg

    from knowledge_lattice.core.docs.acl import compile_acl
    from knowledge_lattice.store.postgres import migrate_db, setup_connection
    from knowledge_lattice.store.postgres.backend import PgBackend
    from knowledge_lattice.store.postgres.vec import format_vector

    print_header(f"G-6 halfvec vs 精确扫描：PG @ {N:,} 块 × {DIM} 维（造数中……）")
    dsn = pg_dsn()
    schema = f"lattice_bench_g6hv_{uuid.uuid4().hex[:8]}"
    raw = psycopg.connect(dsn, autocommit=True)
    out: dict = {}
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
        vectors = synth_vectors(N)
        queries = [format_vector([float(x) for x in vectors[i]]) for i in QUERY_ROWS]

        # ---- 基线：精确扫描（现网形态——backend.recall_vec 真实路径） ----
        for limit in LIMITS:
            all_stats = [_timing(lambda q=q: backend.recall_vec(
                _parse(q), plan, top_k=limit)) for q in queries]
            merged = _merge(all_stats)
            out[f"exact_limit{limit}"] = merged
            print(f"  精确扫描 LIMIT {limit}: P50 {merged['p50_ms']} / P95 {merged['p95_ms']} ms")

        # 精确扫描 top-k 基准集（召回重叠对照）
        exact_sets = {
            limit: {q_i: [r["rid"] for r in backend.recall_vec(_parse(q), plan, top_k=limit)]
                    for q_i, q in enumerate(queries)}
            for limit in LIMITS
        }

        # ---- 表达式 HNSW 索引（halfvec(2560)——官方文档形态） ----
        raw.execute("SET maintenance_work_mem = '256MB'")
        t0 = time.perf_counter()
        raw.execute(
            "CREATE INDEX ix_cv_halfvec_hnsw ON chunk_vectors"
            " USING hnsw ((embedding::halfvec(2560)) halfvec_cosine_ops)"
            " WITH (m = 16, ef_construction = 64)"
        )
        build_s = time.perf_counter() - t0
        raw.execute("ANALYZE chunk_vectors")
        print(f"  halfvec HNSW 索引构建 {build_s:.0f}s（m=16, ef_construction=64）")
        out["index_build_s"] = round(build_s, 1)

        # 半向量查询 SQL：与 render_vec_recall_select 同形（CTE+JOIN+ORDER BY 距离），
        # 距离表达式换为 (embedding::halfvec(2560)) <=> q::halfvec(2560)
        from knowledge_lattice.store.postgres.acl_render import render_vec_recall_select

        def halfvec_rows(q_text: str, limit: int):
            sql, params = render_vec_recall_select(plan, q_text, top_k=limit)
            sql = sql.replace(
                "cv.embedding <=> %(q_vec)s::vector AS dist",
                "(cv.embedding::halfvec(2560)) <=> (%(q_vec)s::halfvec(2560)) AS dist",
            )
            cur = raw.execute(sql, params)
            return cur.fetchall()

        explain = raw.execute(
            "EXPLAIN (COSTS OFF) SELECT c.rid FROM chunks c"
            " JOIN chunk_vectors cv ON cv.rid = c.rid AND cv.embed_model = %(l)s"
            " ORDER BY (cv.embedding::halfvec(2560)) <=> (%(q)s::halfvec(2560))"
            " LIMIT 64",
            {"l": LABEL, "q": queries[0]},
        ).fetchall()
        plan_text = "\n".join(r[0] for r in explain)
        out["index_plan_uses_hnsw"] = "hnsw" in plan_text.lower() or "ix_cv_halfvec" in plan_text
        print(f"  LIMIT 64 计划命中 HNSW 索引：{out['index_plan_uses_hnsw']}")

        for limit in LIMITS:
            all_stats = []
            overlap = []
            for q_i, q in enumerate(queries):
                all_stats.append(_timing(lambda q=q, lim=limit: halfvec_rows(q, lim)))
                rows = halfvec_rows(q, limit)
                got = {r[0] for r in rows}
                want = set(exact_sets[limit][q_i][:limit])
                overlap.append(
                    len(got & want) / len(want) if want else 1.0
                )
            merged = _merge(all_stats)
            merged["overlap_at_k_vs_exact"] = round(sum(overlap) / len(overlap), 4)
            out[f"halfvec_limit{limit}"] = merged
            print(f"  halfvec HNSW LIMIT {limit}: P50 {merged['p50_ms']} /"
                  f" P95 {merged['p95_ms']} ms，overlap@k={merged['overlap_at_k_vs_exact']}")

        idx_size = raw.execute(
            "SELECT pg_relation_size('ix_cv_halfvec_hnsw')"
        ).fetchone()[0]
        tbl_size = raw.execute("SELECT pg_total_relation_size('chunk_vectors')").fetchone()[0]
        out["index_bytes"] = int(idx_size)
        out["chunk_vectors_total_bytes"] = int(tbl_size)
        print(f"  索引体积 {int(idx_size) / 1024**2:.0f} MB（表总 {int(tbl_size) / 1024**2:.0f} MB）")
    finally:
        try:
            raw.execute("SET search_path TO public")
            raw.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except psycopg.Error:
            pass
        finally:
            raw.close()

    path = save_result("m1-5-g6-halfvec-100k", out)
    print(f"工件：{path}")
    return 0


def _parse(q_text: str) -> list[float]:
    return [float(x) for x in q_text.strip("[]").split(",")]


def _merge(stats: list[dict]) -> dict:
    """多查询分位合并（每查询 P50/P95 的 min/中位/max——P95 口径申报中位）。"""
    p50 = sorted(s["p50_ms"] for s in stats)
    p95 = sorted(s["p95_ms"] for s in stats)
    n = len(p50)
    return {
        "queries": n,
        "p50_ms": p50[n // 2],
        "p95_ms": p95[n // 2],
        "p95_max_ms": p95[-1],
    }


if __name__ == "__main__":
    raise SystemExit(main())
