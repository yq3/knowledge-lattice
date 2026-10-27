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
import math
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
    """查询侧嵌入模拟：返回语料真实行向量（保召回有内容），可注延迟（NFR-8
    预算档）。P1-1（R2）：查询文本 → 行号经**显式 dict 映射**（确定性）——
    未知文本直接 KeyError（fail-fast，不再静默降级污染标定）。"""

    def __init__(self, vectors, delay_s: float, row_of_query: dict[str, int]) -> None:
        self._vectors = vectors
        self.delay_s = delay_s
        self._row_of = row_of_query

    @property
    def model_label(self) -> str:
        return MODEL_LABEL

    def embed(self, texts):
        if self.delay_s:
            time.sleep(self.delay_s)
        out = []
        for t in texts:
            row = self._vectors[self._row_of[t]]  # 未知文本 KeyError——不静默
            out.append([float(x) for x in row])
        return out


def _query_row_map(n_pool: int) -> dict[str, int]:
    """查询文本 → 语料行号（确定性：QUERY_TERMS 序 × 素数步进取模）。"""
    return {terms: (i * 7919) % n_pool for i, terms in enumerate(QUERY_TERMS)}


def run_config(backend, settings, embedder, reranker, n_pool: int, vectors) -> dict:
    """单配置：3 预热 + 10 轮 × 5 query → 分段 P50/P95 + wall（nearest-rank）。

    P1-1/R2：每请求断言 notice 全净（vector_pending=False 且 degraded=[]）与
    结果非空——嵌入异常/降级立即 fail-fast（不再被 _embed_query 吞成单路样本）。
    P2-2/R2：预热样本不进分段统计（预热后 handler.records.clear()）。"""
    handler = TimingHandler()
    log = logging.getLogger("knowledge_lattice.core.docs.retrieve")
    log.addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    try:
        for _ in range(3):  # 预热（jieba 首切分/语句缓存/页热——样本外）
            for terms in QUERY_TERMS:
                _once_terms_once(backend, settings, embedder, reranker, terms)
        handler.records.clear()  # P2-2：预热样本不进分段统计
        walls: list[float] = []
        for _ in range(10):
            for terms in QUERY_TERMS:
                t0 = time.perf_counter()
                _once_terms_once(backend, settings, embedder, reranker, terms)
                walls.append((time.perf_counter() - t0) * 1000)
    finally:
        log.removeHandler(handler)

    seg_stats = {}
    for seg in ("embed", "recall", "fuse", "rerank", "enh_wait"):
        xs = sorted(r[seg] for r in handler.records)
        n = len(xs)
        seg_stats[seg] = {
            "p50_ms": round(xs[max(0, math.ceil(0.50 * n) - 1)], 1),
            "p95_ms": round(xs[max(0, math.ceil(0.95 * n) - 1)], 1),
        }
    walls.sort()
    n = len(walls)
    return {
        "n_requests": n,
        "wall_p50_ms": round(walls[max(0, math.ceil(0.50 * n) - 1)], 1),  # P3-5：nearest-rank
        "wall_p95_ms": round(walls[max(0, math.ceil(0.95 * n) - 1)], 1),
        "segments": seg_stats,
        "notice_assert": "per-request == {'vector_pending': False, 'degraded': []}",
    }


def _once_terms_once(backend, settings, embedder, reranker, terms: str) -> None:
    """单请求体（P1-1 fail-fast：全配方净跑断言——降级/空结果立即失败）。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.retrieve import search

    payload = search(
        backend, settings, user_id="u_broad", org_id=BENCH_ORG,
        query=terms, top_k=8, gate=EmbeddingGate(), embedder=embedder,
        reranker=reranker,
    )
    assert payload["notice"] == {"vector_pending": False, "degraded": []}, (
        f"标定样本须全配方净跑：notice={payload['notice']}"
    )
    assert payload["results"], "标定样本应有非空结果"


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
                payload = search(
                    backend, settings, user_id="u_broad", org_id=BENCH_ORG,
                    query=terms, top_k=8, gate=EmbeddingGate(), embedder=embedder,
                    reranker=reranker,
                )
                # P1-1/R2：并发样本同样全配方净跑断言（降级即 fail）
                assert payload["notice"] == {"vector_pending": False, "degraded": []}
                assert payload["results"]
                with lock:
                    latencies.append((time.perf_counter() - t0) * 1000)
            except Exception as exc:  # noqa: BLE001 —— 线程内异常不得静默吞
                with lock:
                    errors.append(f"{type(exc).__name__}: {exc}")
                return
            i += 1

    t_start = time.perf_counter()
    threads = [threading.Thread(target=worker, args=(w,)) for w in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed_actual = time.perf_counter() - t_start  # P2-1：rps 按实测 elapsed
    if errors:
        raise RuntimeError(f"并发档线程失败：{errors[:3]}")
    latencies.sort()
    n = len(latencies)
    mean_ms = sum(latencies) / n
    return {
        "concurrency": 5,
        "duration_nominal_s": duration_s,
        "elapsed_actual_s": round(elapsed_actual, 2),
        "requests": n,
        "rps": round(n / elapsed_actual, 2),
        "mean_ms": round(mean_ms, 1),
        "rps_consistency_check": round(5 / (mean_ms / 1000), 2),  # ≈ rps（5 线程串行环）
        "p50_ms": round(latencies[max(0, math.ceil(0.50 * n) - 1)], 1),
        "p95_ms": round(latencies[max(0, math.ceil(0.95 * n) - 1)], 1),
        "p99_ms": round(latencies[max(0, math.ceil(0.99 * n) - 1)], 1),
        "slo_p95_le_2000ms": latencies[max(0, math.ceil(0.95 * n) - 1)] <= 2000.0,
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
                row_of_query = _query_row_map(scale)
                settings = Settings(
                    environment="test", data_dir=Path("/tmp"), embed_dim=2560,
                    embed_model="synth-embed", reranker="bench", rerank_candidates=32,
                    rerank_max_concurrency=4,
                )

                result: dict = {"scale": scale, "backend": backend_name,
                                "seed_elapsed_s": round(seed_elapsed, 1)}
                result["A_base"] = run_config(
                    backend, settings, DelayedQueryEmbedder(vectors, 0.0, row_of_query), None,
                    scale, vectors)
                result["B_embed150"] = run_config(
                    backend, settings, DelayedQueryEmbedder(vectors, 0.15, row_of_query), None,
                    scale, vectors)
                result["C_full"] = run_config(
                    backend, settings, DelayedQueryEmbedder(vectors, 0.15, row_of_query),
                    FakeReranker(delay_s=0.2), scale, vectors)
                if not args.skip_concurrency:
                    if db.is_sqlite:
                        from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

                        conc_backend = ThreadLocalBackend(db.sqlite_path)
                    else:
                        conc_backend = backend
                    result["C_full_n5"] = concurrency_phase(
                        conc_backend, settings,
                        DelayedQueryEmbedder(vectors, 0.15, row_of_query),
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
