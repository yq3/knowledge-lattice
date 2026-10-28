#!/usr/bin/env python
"""LLM 钩子时间预算评估测量（M1-5 承接项——m1-4 committer 残余③：开 quality_llm
provider 前评估每 flag 超时 10s 的 quality 阶段占用）。

模型（run_llm_keywords 形态——**逐 flag 串行**）：
    T(N flags) = N × (provider 延迟 + 每 flag 固有开销)
    每 flag 固有开销 = get_chunk + chunks_by_rids 读 + llm_keywords/auto_keywords
    两写 + FTS 同步触发（sqlite au / PG GENERATED）
    最坏情形 = N × quality_llm_timeout_s（10s——provider 超时上限逐 flag 计）

测量：sqlite 内存库 + 20 个 open flags + FakeKeywordGenerator（延迟 0/50ms
两档）→ 每 flag 固有开销与串行外推。

用法：uv run python benchmarks/llm_hook_budget.py
产物：data/bench-results/m1-5-llm-hook-budget.json
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from bench_common import save_result  # noqa: E402

N_FLAGS = 20


class FakeKeywordGenerator:
    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s

    def generate(self, content: str) -> tuple[list[str], str]:
        time.sleep(self.delay_s)
        return ["增值税", "申报"], "定位语"


def main() -> int:
    from helpers import insert_chunk, seed_dataset, seed_document, seed_org, seed_user
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.quality import QualityService
    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    out: dict = {"flags": N_FLAGS, "timeout_per_flag_s": 10.0}
    with tempfile.TemporaryDirectory() as td:
        conn = connect(Path(td) / "lattice.db")
        migrate_db(conn)
        seed_org(conn)
        seed_dataset(conn, "org:tax", "ds:vat")
        seed_user(conn, "u1")
        seed_document(conn, doc_id="d:llm", dataset_id="ds:vat", owner_user_id="u1")
        backend = SqliteBackend(conn)
        for i in range(N_FLAGS):
            insert_chunk(conn, doc_id="d:llm", seq=i + 1,
                         content=f"块 {i} 增值税 申报 内容", content_seg="增值税 申报")
            backend.insert_quality_flag(
                chunk_id=f"chk:d:llm:v1:{i + 1}", doc_id="d:llm",
                reason="low_idf", detail_json="{}")
        conn.commit()

        settings = Settings(environment="test", data_dir=Path(td), embed_dim=8)
        for delay in (0.0, 0.05):
            svc = QualityService(backend, settings, keyword_client=FakeKeywordGenerator(delay))
            t0 = time.perf_counter()
            done = svc.run_llm_keywords(org_id="org:tax")
            elapsed = time.perf_counter() - t0
            per_flag = elapsed / N_FLAGS
            overhead = per_flag - delay
            out[f"delay_{int(delay*1000)}ms"] = {
                "elapsed_s": round(elapsed, 3),
                "per_flag_ms": round(per_flag * 1000, 1),
                "fixed_overhead_ms": round(overhead * 1000, 1),
            }
            print(f"provider 延迟 {delay*1000:.0f}ms：{N_FLAGS} flags 串行 {elapsed:.2f}s"
                  f"（每 flag {per_flag*1000:.1f}ms，其中固有开销 {overhead*1000:.1f}ms）")
            # 重置 flags 供第二档测量（state 仍 open——重跑覆盖写语义）
            conn.execute("UPDATE quality_flags SET state = 'open' WHERE doc_id = 'd:llm'")
            conn.execute("UPDATE chunks SET llm_keywords = '' WHERE doc_id = 'd:llm'")
            conn.commit()

    f0 = out["delay_0ms"]["fixed_overhead_ms"]
    out["model"] = {
        "per_flag": "provider 延迟 + 固有开销 ~%.1fms（sqlite 内存库；生产含网络往返放大）" % f0,
        "worst_case_per_doc": "N_open_flags(doc) × 10s 超时上限（串行逐 flag）",
        "worst_case_100_flags_s": 100 * 10.0,
        "quality_stage_note": "摄取 quality 阶段按 doc_id 作用域调用（单文档 open flags 上限≈文档块数）",
    }
    print(json.dumps(out["model"], ensure_ascii=False, indent=2))
    path = save_result("m1-5-llm-hook-budget", out)
    print(f"工件：{path}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
