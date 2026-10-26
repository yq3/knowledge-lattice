#!/usr/bin/env python
"""TC-PERF-03 SLO 标定（NFR-8——M1-5：P95 ≤2s 分项标定，1 万/5 万两档）。

口径（TEST-CASES TC-PERF-03 v1.5.2 + 检查点 A-2）：
- **检索全配方**（embedding→fuse→RRF→双后端 recall）：core.docs.retrieve.search
  真实管线（与生产同 code path——含 ACL 编译/双断言/归一），非 SQL 片段计时；
- **分项耗时**：P3-13 四段日志（embed/recall/fuse/rerank——M1-5 双计修正后
  enh_wait 单列；本档 enhancer=none，enh_wait=0）经 logging handler 逐请求采集；
- 档位：10k / 50k 块 × {sqlite, pg} 双后端；查询 u_broad（最宽授权——最重扫描面）；
- provider 模拟（本地无网关——申报口径）：embed=150ms（NFR-8 预算值，FakeEmbedder
  delay 注入；向量取语料真实行保召回有内容）/ rerank=200ms·32 候选（网关 Cohere
  风格典型 RTT 档）；三配置分离存储段与模型段：
    A base    embed=0ms  + rerank none —— 存储/融合纯段
    B embed150 embed=150ms + rerank none
    C full    embed=150ms + rerank 200ms（rerank_max_concurrency=4）
- N=5 并发档（NFR-8 口径）：5 线程持续检索 12s，聚合延迟分布（50k 档 C 配置）。

公平性：计时 time.perf_counter；P50/P95 nearest-rank（bench_common 同口径）；
预热 3（jieba 首切分与语句缓存不进样本）。

用法：
  uv run python benchmarks/bench5_slo_perf03.py [--scales 10000,50000] [--backends sqlite,pg]
产物：data/bench-results/m1-5-tc-perf-03-{scale}-{backend}.json（汇总
m1-5-tc-perf-03-summary.json）+ stdout 分项表。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from bench_common import (  # noqa: E402
    BENCH_ORG,
    RESULTS_DIR,
    open_bench_db,
    pg_dsn,
    print_header,
    sample_timings,
    save_result,
    seed_corpus,
    synth_vectors,
    vector_cache_path,
)

MODEL_LABEL = "synth-embed:2560"
QUERY_TERMS = ["增值税 申报 指南", "增值税 留抵 退税", "发票 抵扣 进项", "消费税 征收 范围", "申报 期限 滞纳金"]


class TimingHandler(logging.Handler):
    """采集 retrieve 的 search timing 四段日志（M1-5 双计修正后五字段）。"""

    _PAT = re.compile(r"embed=([\d.]+)ms recall=([\d.]+)ms fuse=([\d.]+)ms"
                      r" rerank=([\d.]+)ms enh_wait=([\d.]+)ms")

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.records: list[dict[str, float]] = []

    def emit(self, record: logging.LogRecord) -> None:
        if "search timing" not in record.getMessage():
            return
        m = self._PAT.search(record.getMessage())
        if m:
            segs = ("embed", "recall", "fuse", "rerank", "enh_wait")
            self.records.append({k: float(v) for k, v in zip(segs, m.groups())})


def seed_vectors(db, n: int) -> None:
    """chunk_vectors 全量合成向量（生产写路径形态：rid 序对齐 seed_corpus 产出）。"""
    vectors = synth_vectors(n)
    if db.is_sqlite:
        from knowledge_lattice.store.sqlite.vec import pack_f32

        rows = db.execute("SELECT rid FROM chunks ORDER BY rid")
        rids = [r[0] for r in rows]
        db.raw.executemany(
            "INSERT INTO chunk_vectors(rid, embed_model, embedding) VALUES(?, ?, ?)",
            [(rid, MODEL_LABEL, pack_f32([float(x) for x in vectors[i]]))
             for i, rid in enumerate(rids)],
        )
        db.raw.commit()
        return
    from knowledge_lattice.store.postgres.vec import format_vector

    rids = [r[0] for r in db.execute("SELECT rid FROM chunks ORDER BY rid")]

    def lines() -> Iterator[str]:
        for i, rid in enumerate(rids):
            yield f"{rid}\t{MODEL_LABEL}\t{format_vector([float(x) for x in vectors[i]])}"

    with db.raw.cursor().copy("COPY chunk_vectors(rid, embed_model, embedding) FROM STDIN") as cp:
        for line in lines():
            cp.write(line + "\n")


class DelayedQueryEmbedder:
    """查询侧嵌入模拟：返回语料真实行向量（保召回），可注延迟（NFR-8 预算档）。"""

    def __init__(self, vectors, delay_s: float) -> None:
        self._vectors = vectors
        self.delay_s = delay_s

    @property
    def model_label(self) -> str:
        return MODEL_LABEL

    def embed(self, texts):
        if self.delay_s:
            time.sleep(self.delay_s)
        idx = [int(t.rsplit(":", 1)[1]) for t in texts]  # 约定：query 文本形如 q:123
        return [[float(x) for x in self._vectors[i]] for i in idx]


def run_config(backend, settings, embedder, reranker, n_pool: int, vectors) -> dict:
    """单配置：3 预热 + 10 轮 × 5 query → 分段 P50/P95 + wall。"""
    from fake_providers import FakeReranker
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.retrieve import search

    handler = TimingHandler()
    logging.getLogger("knowledge_lattice.core.docs.retrieve").addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    try:
        queries = [f"q:{(i * 7919) % n_pool}" for i in range(len(QUERY_TERMS))]
        for _ in range(3):
            for q, terms in zip(queries, QUERY_TERMS):
                search(backend, settings, user_id="u_broad", org_id=BENCH_ORG,
                       query=terms, top_k=8, gate=EmbeddingGate(), embedder=embedder,
                       reranker=reranker)
        walls: list[float] = []
        for _ in range(10):
            for q, terms in zip(queries, QUERY_TERMS):
                t0 = time.perf_counter()
                search(backend, settings, user_id="u_broad", org_id=BENCH_ORG,
                       query=terms, top_k=8, gate=EmbeddingGate(), embedder=embedder,
                       reranker=reranker)
                walls.append((time.perf_counter() - t0) * 1000)
    finally:
        logging.getLogger("knowledge_lattice.core.docs.retrieve").removeHandler(handler)

    seg_stats = {}
    for seg in ("embed", "recall", "fuse", "rerank", "enh_wait"):
        xs = sorted(r[seg] for r in handler.records)
        n = len(xs)
        seg_stats[seg] = {
            "p50_ms": round(xs[max(0, (n + 1) // 2 - 1)], 1),
            "p95_ms": round(xs[max(0, (n * 95 + 99) // 100 - 1)], 1),
        }
    walls.sort()
    return {
        "n_requests": len(walls),
        "wall_p50_ms": round(walls[len(walls) // 2], 1),
        "wall_p95_ms": round(walls[max(0, (len(walls) * 95 + 99) // 100 - 1)], 1),
        "segments": seg_stats,
    }


def concurrency_phase(backend, settings, embedder, reranker, n_pool: int,
                      duration_s: float = 12.0) -> dict:
    """N=5 并发档（NFR-8 口径）：5 线程持续检索，聚合延迟分布。

    sqlite 连接线程绑定（check_same_thread 纪律）——backend 传
    ThreadLocalBackend（生产 §2 线程模型同款：每线程一连接）；pg 单连接
    psycopg 线程安全（连接级锁）直用。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.retrieve import search

    latencies: list[float] = []
    lock = threading.Lock()
    errors: list[str] = []
    stop = time.perf_counter() + duration_s

    def worker(wid: int) -> None:
        i = 0
        while time.perf_counter() < stop:
            terms = QUERY_TERMS[(wid + i) % len(QUERY_TERMS)]
            try:
                t0 = time.perf_counter()
                search(backend, settings, user_id="u_broad", org_id=BENCH_ORG,
                       query=terms, top_k=8, gate=EmbeddingGate(), embedder=embedder,
                       reranker=reranker)
                with lock:
                    latencies.append((time.perf_counter() - t0) * 1000)
            except Exception as exc:  # noqa: BLE001 —— 线程内异常不得静默吞
                with lock:
                    errors.append(f"{type(exc).__name__}: {exc}")
                return
            i += 1

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise RuntimeError(f"并发档线程失败：{errors[:3]}")
    latencies.sort()
    n = len(latencies)
    return {
        "concurrency": 5,
        "duration_s": duration_s,
        "requests": n,
        "rps": round(n / duration_s, 2),
        "p50_ms": round(latencies[n // 2], 1),
        "p95_ms": round(latencies[max(0, (n * 95 + 99) // 100 - 1)], 1),
        "p99_ms": round(latencies[max(0, (n * 99 + 99) // 100 - 1)], 1),
        "slo_p95_le_2000ms": latencies[max(0, (n * 95 + 99) // 100 - 1)] <= 2000.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scales", default="10000,50000")
    parser.add_argument("--backends", default="sqlite,pg")
    parser.add_argument("--skip-concurrency", action="store_true")
    args = parser.parse_args()
    scales = [int(s) for s in args.scales.split(",")]
    backends = args.backends.split(",")

    from fake_providers import FakeReranker
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings

    summary: dict = {}
    for backend_name in backends:
        for scale in scales:
            tag = f"perf03-{backend_name}-{scale}"
            print_header(f"TC-PERF-03：{backend_name} @ {scale:,} 块（造数中……）")
            t0 = time.perf_counter()
            with open_bench_db(backend_name, tag=tag) as db:
                seed_corpus(db, n_docs=scale // 10, chunks_per_doc=10)
                seed_vectors(db, scale)
                seed_elapsed = time.perf_counter() - t0
                print(f"造数完成 {seed_elapsed:.0f}s（chunks {scale:,} + vectors {scale:,}）")

                backend = db.make_backend()
                vectors = synth_vectors(scale)
                settings = Settings(
                    environment="test", data_dir=Path("/tmp"), embed_dim=2560,
                    embed_model="synth-embed", reranker="bench", rerank_candidates=32,
                    rerank_max_concurrency=4,
                )

                result: dict = {"scale": scale, "backend": backend_name,
                                "seed_elapsed_s": round(seed_elapsed, 1)}
                result["A_base"] = run_config(
                    backend, settings, DelayedQueryEmbedder(vectors, 0.0), None,
                    scale, vectors)
                result["B_embed150"] = run_config(
                    backend, settings, DelayedQueryEmbedder(vectors, 0.15), None,
                    scale, vectors)
                result["C_full"] = run_config(
                    backend, settings, DelayedQueryEmbedder(vectors, 0.15),
                    FakeReranker(delay_s=0.2), scale, vectors)
                if not args.skip_concurrency:
                    if db.is_sqlite:
                        from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

                        conc_backend = ThreadLocalBackend(db.sqlite_path)
                    else:
                        conc_backend = backend
                    result["C_full_n5"] = concurrency_phase(
                        conc_backend, settings, DelayedQueryEmbedder(vectors, 0.15),
                        FakeReranker(delay_s=0.2), scale)
                save_result(f"m1-5-tc-perf-03-{backend_name}-{scale}", result)
                summary[f"{backend_name}-{scale}"] = result
                for key in ("A_base", "B_embed150", "C_full"):
                    r = result[key]
                    seg = r["segments"]
                    print(
                        f"  {key:11s} wall P50/P95 {r['wall_p50_ms']:>7.1f}/"
                        f"{r['wall_p95_ms']:>7.1f} ms | embed {seg['embed']['p95_ms']:>6.1f}"
                        f" recall {seg['recall']['p95_ms']:>7.1f} fuse {seg['fuse']['p95_ms']:>6.1f}"
                        f" rerank {seg['rerank']['p95_ms']:>7.1f}"
                    )
                if "C_full_n5" in result:
                    c = result["C_full_n5"]
                    print(
                        f"  C@N=5      P50/P95/P99 {c['p50_ms']:.1f}/{c['p95_ms']:.1f}/"
                        f"{c['p99_ms']:.1f} ms  rps={c['rps']}  "
                        f"SLO(P95≤2000ms)={'PASS' if c['slo_p95_le_2000ms'] else 'FAIL'}"
                    )

    path = save_result("m1-5-tc-perf-03-summary", summary)
    print(f"\n汇总工件：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
