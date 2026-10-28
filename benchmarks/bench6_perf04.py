#!/usr/bin/env python
"""TC-PERF-04 rerank 并发与嵌入吞吐（M1-5——配套性能抽测，NFR-3 风险标定输入）。

口径（TEST-CASES TC-PERF-04）：
- **rerank 并发信号量上限下的吞吐曲线**：_run_rerank 真实路径（信号量 +
  _RERANK_POOL + 超时预算——P2-2 排队不计入调用超时的形态本体），reranker
  模拟延迟 200ms（网关 Cohere 风格典型 RTT 档），并发上限 ∈ {1, 2, 4, 8}，
  5 并发线程 × 24 请求 → 吞吐 rps / P50 / P95 / 并发峰值观测；
- **CPU 嵌入分批吞吐（块/分钟）**：本地无网关（B-3① 受阻申报同源）——测
  TokenBagEmbedder（CPU 确定性嵌入，dim=2560）批量 embed 吞吐作为**客户端
  处理上界**；真实 API 吞吐需网关环境（M2 生产化容量规划补测）。

用法：uv run python benchmarks/bench6_perf04.py
产物：data/bench-results/m1-5-tc-perf-04.json + stdout 曲线表
"""

from __future__ import annotations

import dataclasses
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from bench_common import RESULTS_DIR, machine_profile, print_header, save_result  # noqa: E402


def rerank_curve(limit: int, delay_s: float = 0.2, n_threads: int = 5,
                 per_thread: int = 24) -> dict:
    """并发上限 limit 下：n_threads 线程 × per_thread 次 rerank 的吞吐/延迟。"""
    from fake_providers import FakeReranker
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs import retrieve
    from knowledge_lattice.core.docs.retrieve import _run_rerank

    settings = dataclasses.replace(
        Settings(environment="test", data_dir=Path("/tmp"), reranker="bench",
                 rerank_max_concurrency=limit, rerank_timeout_s=5.0)
    )
    reranker = FakeReranker(delay_s=delay_s, track_concurrency=True)
    candidates = [{"rid": i, "content": f"候选块 {i} 增值税 申报"} for i in range(32)]
    latencies: list[float] = []
    lock = threading.Lock()
    degraded: list[list[str]] = []
    threads: list[threading.Thread] = []

    def worker() -> None:
        local: list[float] = []
        for _ in range(per_thread):
            t0 = time.perf_counter()
            deg: list[str] = []
            _run_rerank(settings, reranker, None, "增值税 申报", candidates, deg)
            local.append((time.perf_counter() - t0) * 1000)
            if deg:
                degraded.append(deg)
        with lock:
            latencies.extend(local)

    t0 = time.perf_counter()
    for _ in range(n_threads):
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0
    latencies.sort()
    n = len(latencies)
    return {
        "semaphore_limit": limit,
        "delay_ms": delay_s * 1000,
        "requests": n,
        "elapsed_s": round(elapsed, 2),
        "rps": round(n / elapsed, 2),
        "p50_ms": round(latencies[n // 2], 1),
        "p95_ms": round(latencies[max(0, (n * 95 + 99) // 100 - 1)], 1),
        "provider_concurrency_peak": reranker.concurrency_peak,
        "degraded": bool(degraded),
    }


def embed_throughput() -> dict:
    """CPU 嵌入分批吞吐：TokenBagEmbedder（dim=2560，确定性 token 袋——评测
    代理同源实现）× 语料文本批量 embed（batch=64——config.embed_batch_size）。"""
    from fake_providers import TokenBagEmbedder
    from knowledge_lattice.adapters.tokenizer import join_seg

    texts_raw = [
        "增值税一般纳税人销售货物提供应税劳务的申报口径说明。",
        "企业差旅费报销标准与审批流程。",
        "The general taxpayer shall account separately for sales of goods.",
    ] * 400  # 1200 段
    texts = [join_seg(t) for t in texts_raw]  # 与摄取管线同形态（空格分词串）
    embedder = TokenBagEmbedder(dim=2560)

    t0 = time.perf_counter()
    out = []
    batch = 64
    for lo in range(0, len(texts), batch):
        out.extend(embedder.embed(texts[lo : lo + batch]))
    elapsed = time.perf_counter() - t0
    return {
        "texts": len(texts),
        "dim": 2560,
        "batch": batch,
        "elapsed_s": round(elapsed, 2),
        "chunks_per_min": round(len(texts) / elapsed * 60),
        "note": "CPU 确定性嵌入代理（客户端处理上界）；真实 API 吞吐需网关环境",
    }


def main() -> int:
    print_header("TC-PERF-04：rerank 并发曲线 + CPU 嵌入吞吐")
    curves = [rerank_curve(limit) for limit in (1, 2, 4, 8)]
    print("| 信号量上限 | rps | P50 ms | P95 ms | provider 并发峰值 | 降级 |")
    print("|---|---|---|---|---|---|")
    for c in curves:
        print(
            f"| {c['semaphore_limit']} | {c['rps']} | {c['p50_ms']} | {c['p95_ms']}"
            f" | {c['provider_concurrency_peak']} | {c['degraded']} |"
        )
    embed = embed_throughput()
    print(f"\nCPU 嵌入吞吐（TokenBag dim=2560, batch=64）：{embed['chunks_per_min']} 块/分钟"
          f"（{embed['texts']} 段 {embed['elapsed_s']}s）")
    payload = {
        "machine": machine_profile(),
        "rerank_curves": curves,
        "embed_cpu_throughput": embed,
        "blocked": "真实 API 吞吐（embed/rerank 网关端）——本地无网关环境（B-3① 同源受阻），M2 生产化容量规划补测",
    }
    path = save_result("m1-5-tc-perf-04", payload)
    print(f"工件：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
