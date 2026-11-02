#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""m2-5 校准实验（真实百炼 embedding——A3② G-6 真实基线 + A4 G-8 两项）。

**真实 API 实验**（任务书裁定 2026-11-01：开发态统一用 .env DASHSCOPE_API_KEY；
仅本 benchmarks/ 脚本发起真实调用，门禁测试保持离线 fake providers）。
模型/端点按 A4 环境探测结论：`text-embedding-v4`（compatible-mode），
dimensions 枚举 [64,128,256,512,768,1024,1536,2048,3072]——**无 2560**
（项目默认 qwen3-embedding-4b:2560 百炼 404，开发态经 env 配置）。

子实验（--exp）：
  real      G-6 真实基线：真实 embedder 默认档黄金集 recall@10/MRR（双后端）
            × TokenBag 代理对照——验证 M1-5 TokenBag 代理结论（偏差 10.72pp
            构成、停用词假设、跨语言系统性低估）是否在真实模型下成立；
  mrl       G-8 ① MRL 截断：真实模型 dimensions 截断档 vs 默认全量档黄金集
            对比（服务端原生 MRL 截断——非 M1-5 客户端前缀截断代理面）；
            「截断开放为可选配置」判据落笔材料；
  threshold G-8 ② 指纹阈值：哨兵文本多次采样（--rounds 轮）余弦偏差分布
            → 0.99/0.95 两档保守临时值的校准建议或维持依据。

用法：
  uv run python benchmarks/calib_m2_5.py --exp real            # sqlite 臂
  LATTICE_PG_DSN=… uv run python benchmarks/calib_m2_5.py --exp real
  uv run python benchmarks/calib_m2_5.py --exp mrl
  uv run python benchmarks/calib_m2_5.py --exp threshold --rounds 20
产物：data/bench-results/m2-5-calib-<exp>[-<backend>].json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_common import save_result  # noqa: E402
from calib_m1_5 import run_golden  # noqa: E402 —— 黄金集评测基建（M1-5 先例）

EVAL_DIR = ROOT / "eval"
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "text-embedding-v4"   # A4 环境探测结论（qwen3-embedding-4b 百炼 404）


def _api_key() -> str:
    # key 只走 .env / 环境变量——不写死代码、不打印（硬约束 2）
    if os.environ.get("DASHSCOPE_API_KEY"):
        return os.environ["DASHSCOPE_API_KEY"]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DASHSCOPE_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("DASHSCOPE_API_KEY 未配置（.env / 环境变量）——真实校准无法运行")


class DashScopeEmbedder:
    """百炼 compatible-mode 真实嵌入（OpenAI 兼容 + dimensions 参数）。

    服务端原生 MRL 截断：dimensions 指定枚举档（64..3072）；None=模型默认
    输出档。确定性缓存（首次结果落盘 data/bench-results/embeddings-cache/
    ——同文本+同 dimensions 复跑零成本、可复现〔参数/种子固化——硬约束 6〕）。
    """

    def __init__(self, *, dimensions: int | None = None,
                 model: str = MODEL) -> None:
        import httpx

        self._client = httpx.Client(
            base_url=DASHSCOPE_BASE,
            headers={"Authorization": f"Bearer {_api_key()}"},
            timeout=60.0,
        )
        self.model = model
        self.model_name = model  # calib_m1_5.run_golden 的 settings.embed_model 同源面
        self.dimensions = dimensions
        self._cache: dict[str, list[float]] = {}
        cache_dir = ROOT / "data" / "bench-results" / "embeddings-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = cache_dir / (
            f"{model.replace('/', '_')}-dim{dimensions or 'default'}.json")

    @property
    def model_label(self) -> str:
        dim = self.dimensions if self.dimensions is not None else self._native_dim()
        return f"{self.model}:{dim}"

    def _native_dim(self) -> int:
        vecs = self._load()
        if not vecs:
            self.embed(["维度探测"])
        vecs = self._load()
        return len(next(iter(vecs.values())))

    def _load(self) -> dict[str, list[float]]:
        if not self._cache:
            if self._cache_path.exists():
                self._cache = json.loads(self._cache_path.read_text())
        return self._cache

    def _flush(self) -> None:
        self._cache_path.write_text(json.dumps(self._cache, ensure_ascii=False))

    def embed(self, texts):
        cache = self._load()
        missing = [t for t in texts if t not in cache]
        # 批量请求（10 条/批——网关限流保守档；429 退避重试）
        for lo in range(0, len(missing), 10):
            batch = missing[lo:lo + 10]
            body: dict = {"model": self.model, "input": batch,
                          "encoding_format": "float"}
            if self.dimensions is not None:
                body["dimensions"] = self.dimensions
            for attempt in range(5):
                resp = self._client.post("/embeddings", json=body)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    print(f"    429 限流——退避 {wait}s 重试", flush=True)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                break
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            for text, item in zip(batch, data):
                cache[text] = [float(x) for x in item["embedding"]]
        self._flush()
        return [cache[t] for t in texts]

    def embed_fresh(self, texts):
        """无缓存直呼（threshold 采样专用——抖动分布须真实多次调用）。"""
        body: dict = {"model": self.model, "input": list(texts),
                      "encoding_format": "float"}
        if self.dimensions is not None:
            body["dimensions"] = self.dimensions
        resp = self._client.post("/embeddings", json=body)
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [[float(x) for x in item["embedding"]] for item in data]

    def close(self) -> None:
        self._client.close()


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


# ============ exp: real（G-6 真实基线——双后端黄金集） ============


def exp_real(backend_name: str) -> dict:
    from fake_providers import TokenBagEmbedder

    real = DashScopeEmbedder()
    try:
        print(f"  真实档 label：{real.model_label}（探测中……）", flush=True)
        out = {"model": real.model, "label": real.model_label}
        out["real_default"] = run_golden(
            backend_name, real, int(real.model_label.rpartition(":")[2]))
        out["tokbag_proxy"] = run_golden(backend_name, TokenBagEmbedder(dim=32), 32)
        r, t = out["real_default"], out["tokbag_proxy"]
        out["delta_real_vs_tokbag_pp"] = {
            "recall@10": round((r["recall@10"] - t["recall@10"]) * 100, 2),
            "mrr": round((r["mrr"] - t["mrr"]) * 100, 2),
        }
        save_result(f"m2-5-calib-real-{backend_name}", out)
        return out
    finally:
        real.close()


# ============ exp: mrl（G-8 ①——真实模型 dimensions 截断档） ============


def exp_mrl(backend_name: str, trunc_dims: tuple[int, ...] = (512, 256)) -> dict:
    """全量档（默认输出）vs 截断档（服务端原生 MRL）黄金集对比。

    服务端 dimensions 截断是模型自带 MRL 头（非客户端前缀截断代理面）——
    M1-5 TokenBag 结论 r@10 0.00pp / MRR −1.63~−2.38pp 的真实模型验证。
    """
    full = DashScopeEmbedder()
    try:
        full_dim = int(full.model_label.rpartition(":")[2])
        out = {"model": full.model, "full_dim": full_dim, "trunc_dims": trunc_dims}
        out["full"] = run_golden(backend_name, full, full_dim)
        for dim in trunc_dims:
            trunc = DashScopeEmbedder(dimensions=dim)
            try:
                out[f"trunc_{dim}"] = run_golden(backend_name, trunc, dim)
            finally:
                trunc.close()
        f = out["full"]
        for dim in trunc_dims:
            t = out[f"trunc_{dim}"]
            out.setdefault("deltas_vs_full_pp", {})[f"trunc_{dim}"] = {
                "recall@10": round((t["recall@10"] - f["recall@10"]) * 100, 2),
                "mrr": round((t["mrr"] - f["mrr"]) * 100, 2),
            }
        save_result(f"m2-5-calib-mrl-{backend_name}", out)
        return out
    finally:
        full.close()


# ============ exp: threshold（G-8 ②——真实响应抖动分布） ============


def exp_threshold(rounds: int = 20) -> dict:
    """哨兵 3 条 × rounds 轮真实采样——同文本跨调用的余弦偏差分布
    （M1-5 校准建议 3 步的真实版：抖动底 → 对 0.99/0.95 的判定间隔）。"""
    from knowledge_lattice.adapters.embedder import SENTINELS

    emb = DashScopeEmbedder()
    try:
        # 每轮独立请求（embed_fresh——不经缓存）
        rounds_cos: list[list[float]] = []
        for i in range(rounds):
            vecs = emb.embed_fresh(SENTINELS)
            base = emb.embed(SENTINELS)  # 首轮基准（缓存档——与建档口径一致）
            rounds_cos.append([_cosine(b, v) for b, v in zip(base, vecs)])
            if (i + 1) % 5 == 0:
                print(f"    采样 {i + 1}/{rounds} 轮", flush=True)
            time.sleep(0.2)  # 跨秒级窗口——覆盖网关侧批次/版本抖动面

        flat = sorted(c for row in rounds_cos for c in row)
        n = len(flat)

        def pct(p: float) -> float:
            return flat[max(0, math.ceil(p * n) - 1)]

        out = {
            "model": emb.model, "rounds": rounds, "sentinels": len(SENTINELS),
            "samples": n,
            "cosine_min": round(flat[0], 6),
            "cosine_p05": round(pct(0.05), 6),
            "cosine_p50": round(pct(0.50), 6),
            "cosine_p95": round(pct(0.95), 6),
            "cosine_max": round(flat[-1], 6),
            "drift_pct_p95": round((1 - pct(0.95)) * 100, 4),
            "verdict_0_99": "warn 触发面" if pct(0.50) < 0.99 else
                            ("warn 边缘（p95 <0.99）" if pct(0.95) < 0.99
                             else "静默区（全样本 ≥0.99）"),
            "verdict_0_95": ("reject 误报面（存在 <0.95 样本）" if flat[0] < 0.95
                             else "静默区（全样本 ≥0.95）"),
        }
        save_result("m2-5-calib-threshold", out)
        return out
    finally:
        emb.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp", required=True,
                        choices=["real", "mrl", "threshold"])
    parser.add_argument("--backend", default="sqlite", choices=["sqlite", "pg"])
    parser.add_argument("--rounds", type=int, default=20)
    args = parser.parse_args()

    t0 = time.perf_counter()
    if args.exp == "real":
        result = exp_real(args.backend)
    elif args.exp == "mrl":
        result = exp_mrl(args.backend)
    else:
        result = exp_threshold(args.rounds)
    printable = {
        k: v for k, v in result.items()
        if not isinstance(v, dict) or k in
        ("delta_real_vs_tokbag_pp", "deltas_vs_full_pp") or "recall" not in str(v)
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))
    for key in ("real_default", "tokbag_proxy", "full"):
        if key in result:
            r = result[key]
            print(f"  [{key}] recall@10={r['recall@10']:.4f}"
                  f" recall@1={r.get('recall@1', float('nan')):.4f}"
                  f" mrr={r['mrr']:.4f}")
    print(f"\n[{args.exp}/{args.backend}] {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
