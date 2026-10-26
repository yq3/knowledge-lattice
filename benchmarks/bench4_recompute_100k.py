#!/usr/bin/env python
"""TC-PERF-03 前置（M1-4 P2-4 / M1-5 改造的内存实测）：100k×2560 档批量重算
（QualityService 拥挤路）峰值内存与耗时。

对比两形态（各自独立子进程测——ru_maxrss 是进程高水位，不可同进程叠加）：
- **旧形态**（物化 float 对象列表：list[tuple[int, list[float]]]）：10k 行实测
  （100k 档外推 ~8GB——本机 16GB 不可全量跑，按 10k 实测 + 线性外推申报）；
- **新形态**（packed bytes 流 + 候选驻留 ndarray + 分块 running top-k）：
  100k 池全量 + 5% 候选（5000）重算实测；另附全量候选（100k）驻留矩阵口径
  外推（n_cand×dim×4B ≈ 1.02GB 单块 ndarray——§5.4「载入 numpy」同口径）。

数据：合成 2560 维 unit float32（bench_common.synth_vectors——确定性 seed，
mmap 缓存复用）；不落 DB（本实验隔离 numpy 拥挤路的内存形态；SQL 侧流式
正确性由 tests/test_m1_5_dev.py 双后端覆盖，10k 全链在 test_qual_11 门禁内）。

用法：uv run python benchmarks/bench4_recompute_100k.py
产物：data/bench-results/m1-5-recompute-100k.json + stdout 摘要
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from bench_common import (  # noqa: E402
    SEED,
    machine_profile,
    print_header,
    save_result,
    synth_vectors,
    vector_cache_path,
)

POOL_N = 100_000
DIM = 2560
CAND_PERCENT = 5  # 周期抽样档（config.quality_sample_percent 默认 10——取 5 保守）


def rss_mb() -> float:
    """当前进程峰值 RSS（MB）——macOS ru_maxrss 单位为字节、Linux 为 KB（区分）。"""
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if platform.system() == "Darwin" else peak / 1024


_MEASURE_NEW = "new"
_MEASURE_OLD = "old"


def _child(mode: str) -> dict:
    """子进程内跑单形态（隔离高水位），打印 JSON 由父进程回收。"""
    import numpy as np

    from knowledge_lattice.core.docs.quality import QualityService

    class FakeVectorBackend:
        """org_active_chunk_vectors 流式假体——普通文件 read 顺序取行（经
        np.load(mmap) 读会把整文件页计入进程 RSS——生产数据源是 DB 流而非
        mmap，此处用 read() 隔离出算法私有内存；取值与 synth_vectors 同文件
        逐字节一致）。"""

        def __init__(self, npy_path: Path, n: int, dim: int) -> None:
            import numpy as np

            with open(npy_path, "rb") as f:
                version = np.lib.format.read_magic(f)
                np.lib.format.read_array_header_1_0(f)  # 头偏移定位（v1 形态）
                self._offset = f.tell()
            self._row_bytes = dim * 4
            self._n = n

        def org_active_chunk_vectors(self, org_id: str, embed_model: str):
            with open(vector_cache_path(POOL_N), "rb") as f:
                f.seek(self._offset)
                for rid in range(1, self._n + 1):
                    yield rid, f.read(self._row_bytes)

    vectors = synth_vectors(POOL_N)  # 确保缓存文件存在（首次生成）
    rids = list(range(1, POOL_N + 1))
    n_cand = POOL_N * CAND_PERCENT // 100
    cand_rids = rids[:: POOL_N // n_cand][:n_cand]

    from knowledge_lattice.config import Settings

    settings = Settings(environment="test", data_dir=Path("/tmp"), embed_dim=DIM)
    import dataclasses

    if mode == _MEASURE_OLD:
        before = rss_mb()
        t0 = time.perf_counter()
        materialized = [
            (rid, [float(x) for x in row]) for rid, row in zip(rids[:10_000], vectors[:10_000])
        ]
        elapsed = time.perf_counter() - t0
        payload = {
            "mode": "old_materialized_10k",
            "rows": len(materialized),
            "rss_delta_mb": round(rss_mb() - before, 1),
            "elapsed_s": round(elapsed, 2),
        }
        del materialized
    else:
        service = QualityService(
            FakeVectorBackend(vector_cache_path(POOL_N), POOL_N, DIM), settings
        )
        t0 = time.perf_counter()
        means = service._crowding_means(np, "org:bench", "synth-embed:2560", cand_rids)
        elapsed = time.perf_counter() - t0
        payload = {
            "mode": "new_streaming_100k_pool",
            "pool": POOL_N,
            "candidates": len(cand_rids),
            "rss_delta_mb": round(rss_mb(), 1),
            "elapsed_s": round(elapsed, 2),
            "mean_sim_avg": round(float(np.mean(list(means.values()))), 5),
        }
    print("RESULT:" + json.dumps(payload))


def main() -> int:
    print_header("TC-PERF-03 前置：100k×2560 批量重算内存/耗时（M1-4 P2-4 改造实测）")
    out: dict = {"machine": machine_profile(), "pool": {"n": POOL_N, "dim": DIM, "seed": SEED}}

    for mode, label in ((_MEASURE_NEW, "新形态"), (_MEASURE_OLD, "旧形态")):
        proc = subprocess.run(
            [sys.executable, __file__, "--child", mode],
            capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent,
        )
        line = next(
            (ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT:")), None
        )
        if line is None:
            print(proc.stdout[-2000:], proc.stderr[-2000:])
            raise SystemExit(f"{label} 子进程失败（exit {proc.returncode}）")
        payload = json.loads(line[7:])
        out[payload["mode"]] = payload
        print(f"{label}：{json.dumps(payload, ensure_ascii=False)}")

    old = out["old_materialized_10k"]
    new = out["new_streaming_100k_pool"]
    per_row_kb = old["rss_delta_mb"] * 1024 / old["rows"]
    out["derived"] = {
        "old_per_row_kb": round(per_row_kb, 1),
        "old_extrapolated_100k_gb": round(per_row_kb * POOL_N / 1024 / 1024, 2),
        "packed_bytes_per_row_kb": round(DIM * 4 / 1024, 1),
        "new_full_candidates_matrix_gb": round(POOL_N * DIM * 4 / 1024**3, 2),
        "verdict": (
            f"旧形态 100k 档外推 ≈{round(per_row_kb * POOL_N / 1024 / 1024, 2)}GB"
            f"（float 对象 {round(per_row_kb / (DIM * 4 / 1024), 1)}× 于 packed bytes）——16GB 机不可行；"
            f"新形态 100k 池 5% 候选实测峰值 {new['rss_delta_mb']}MB，"
            f"全量候选上限 ≈{round(POOL_N * DIM * 4 / 1024**3, 2)}GB 单块 ndarray（§5.4 同口径）"
        ),
    }
    print("\n判据：" + out["derived"]["verdict"])
    path = save_result("m1-5-recompute-100k", out)
    print(f"工件：{path}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--child":
        _child(sys.argv[2])
    else:
        raise SystemExit(main())
