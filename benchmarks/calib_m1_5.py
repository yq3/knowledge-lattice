#!/usr/bin/env python
"""M1-5 校准实验（G-8/G-6——benchmarks/ 纯实验，不改产品代码；判据落笔归
supervised-coding）。

子实验（--exp）：
  mrl        G-8 ① MRL 截断对比：TokenBag(dim=2560) 全维 vs 前缀 1024 截断
             （+重归一——MRL 部署机制形态，§5.3 `:trunc` 标签）vs 原生 1024，
             黄金集 recall@10/MRR（双后端）。**口径申报**：TokenBag 为确定性
             哈希向量、非 MRL 训练模型——本实验测「前缀截断机制」对非 MRL
             嵌入的影响（真实 MRL 模型前缀按训练保留语义，结果不可直接外推）；
  threshold  G-8 ② 指纹阈值：确定性重嵌入（同模型控制组）+ fp16 量化噪声底
             （halfvec 存储环回——真实良性变换）+ 精确余弦漂移扫描
             （Gram-Schmidt 造数）→ 0.99/0.95 两档判定剖面；
  bluegreen  B4 蓝绿共存 PG 读代价：单标签 10k 基线 vs 双标签共存（10k+10k，
             PK(rid, embed_model)）recall_vec P50/P95（M0b-2 移交复测）；
  stopwords  B-3 ② 停用词滤除评估：query 侧停用词过滤（monkeypatch
             segment_query——产品代码零改动）后黄金集复测（双后端）；
  tsrankcd   B-3 ④ ts_rank_cd 排序对照：PG 臂 TS_RANK_SUM 换 ts_rank_cd 同权重
             （monkeypatch fts.TS_RANK_SUM）黄金集复跑对照。

用法：
  uv run python benchmarks/calib_m1_5.py --exp mrl
  LATTICE_PG_DSN=… uv run python benchmarks/calib_m1_5.py --exp mrl   # pg 臂
  LATTICE_PG_DSN=… uv run python benchmarks/calib_m1_5.py --exp bluegreen
产物：data/bench-results/m1-5-calib-<exp>-<backend>.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_common import save_result  # noqa: E402

EVAL_DIR = ROOT / "eval"
ORG = "org:tax"


# ============ 黄金集评测基建（与 scripts/eval_baseline.py 同构） ============


def _seed_matrix(db) -> None:
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

    seed_org(db, ORG)
    seed_dataset(db, ORG, "ds:vat_lib")
    seed_dataset(db, ORG, "ds:expense_lib")
    seed_dimension(db, ORG, "region")
    seed_dim_value(db, dim_id_for(ORG, "region"), "CN")
    seed_dim_value(db, dim_id_for(ORG, "region"), "OS")
    seed_dimension(db, ORG, "tax_type")
    db.execute(
        "UPDATE dimensions SET required = 0 WHERE org_id = ? AND key = 'tax_type'", (ORG,)
    )
    seed_dim_value(db, dim_id_for(ORG, "tax_type"), "VAT")
    seed_user(db, "u_full")
    seed_membership(db, "u_full", ORG)
    for value in ("CN", "OS"):
        seed_grant(db, user_id="u_full", dim_id=dim_id_for(ORG, "region"),
                   val_id=val_id_for(ORG, "region", value))
    seed_grant(db, user_id="u_full", dim_id=dim_id_for(ORG, "tax_type"),
               val_id=val_id_for(ORG, "tax_type", "VAT"))
    db.commit()


def open_backend(backend_name: str, tmp: Path):
    if backend_name == "sqlite":
        from dbwrap import SqliteDb
        from knowledge_lattice.store.sqlite import connect, migrate_db
        from knowledge_lattice.store.sqlite.backend import SqliteBackend

        conn = connect(tmp / "lattice.db")
        migrate_db(conn)
        db = SqliteDb(conn)
        _seed_matrix(db)
        return db, SqliteBackend(conn), None, conn

    import os

    import psycopg

    from dbwrap import PgDb
    from knowledge_lattice.store.postgres import migrate_db, setup_connection
    from knowledge_lattice.store.postgres.backend import PgBackend

    dsn = os.environ.get("LATTICE_PG_DSN")
    if not dsn:
        raise SystemExit("LATTICE_PG_DSN 未设置——pg 臂无法运行")
    schema = f"lattice_calib_{uuid.uuid4().hex[:12]}"
    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute(f'CREATE SCHEMA "{schema}"')
    conn.execute(f'SET search_path TO "{schema}", public')
    setup_connection(conn)
    migrate_db(conn)
    db = PgDb(conn, schema, dsn)
    _seed_matrix(db)
    return db, PgBackend(conn), schema, conn


def drop_pg(conn, schema: str) -> None:
    conn.execute("SET search_path TO public")
    conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


class TruncatingEmbedder:
    """MRL 前缀截断形态：base(dim=2560) 全维嵌入 → 取前 keep 维 + 重归一。
    model_label 带 :trunc 后缀（design §5.3——与全维向量不混算）。"""

    def __init__(self, base, keep: int) -> None:
        self._base = base
        self.keep = keep
        self.full_dim = base.dim
        self.model_name = base.model_name  # settings.embed_model 同源（标签由 dim 决定）

    @property
    def model_label(self) -> str:
        return f"{self._base.model_name}:{self.keep}trunc"

    def embed(self, texts):
        out = []
        for vec in self._base.embed(texts):
            head = vec[: self.keep]
            norm = math.sqrt(sum(x * x for x in head)) or 1.0
            out.append([x / norm for x in head])
        return out


def run_golden(backend_name: str, embedder, embed_dim: int) -> dict:
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.docs.quality import QualityService
    from knowledge_lattice.eval.harness import load_corpus, load_golden, run_evaluation

    tmp = Path(tempfile.mkdtemp(prefix="lattice-calib-"))
    db, backend, schema, conn = open_backend(backend_name, tmp)
    try:
        settings = Settings(
            environment="test", data_dir=tmp, embed_dim=embed_dim,
            embed_model=embedder.model_name,
        )
        gate = EmbeddingGate()
        quality = QualityService(backend, settings)
        service = IngestService(
            backend, embedder, settings, gate, tmp / "objects", quality=quality
        )
        report = run_evaluation(
            backend=backend, settings=settings, embedder=embedder, gate=gate,
            corpus=load_corpus(EVAL_DIR / "corpus.jsonl"),
            golden=load_golden(EVAL_DIR / "golden.jsonl"),
            user_id="u_full", org_id=ORG, objects_dir=tmp / "objects",
            ingest_service=service,
        )
        report.pop("per_query", None)
        return report
    finally:
        if schema:
            drop_pg(conn, schema)
        conn.close()


# ============ exp: mrl ============


def exp_mrl(backend_name: str) -> dict:
    from fake_providers import TokenBagEmbedder

    full = TokenBagEmbedder(dim=2560)
    trunc = TruncatingEmbedder(TokenBagEmbedder(dim=2560), keep=1024)
    native = TokenBagEmbedder(dim=1024)

    out = {"backend": backend_name}
    out["full_2560"] = run_golden(backend_name, full, 2560)
    out["trunc_1024"] = run_golden(backend_name, trunc, 1024)
    out["native_1024"] = run_golden(backend_name, native, 1024)
    f, t, n = out["full_2560"], out["trunc_1024"], out["native_1024"]
    out["deltas_vs_full_pp"] = {
        "trunc_1024": {
            "recall@10": round((t["recall@10"] - f["recall@10"]) * 100, 2),
            "mrr": round((t["mrr"] - f["mrr"]) * 100, 2),
        },
        "native_1024": {
            "recall@10": round((n["recall@10"] - f["recall@10"]) * 100, 2),
            "mrr": round((n["mrr"] - f["mrr"]) * 100, 2),
        },
    }
    save_result(f"m1-5-calib-mrl-{backend_name}", out)
    return out


# ============ exp: threshold ============


def _exact_cosine_pair(base: list[float], cos: float, seed_tag: str) -> list[float]:
    """与 base 精确余弦 cos 的向量（Gram-Schmidt——tests/fake_providers 同式）。"""
    norm = math.sqrt(sum(x * x for x in base)) or 1.0
    b_hat = [x / norm for x in base]
    rng = random.Random(seed_tag)
    noise = [rng.uniform(-1, 1) for _ in base]
    nb = sum(n * bh for n, bh in zip(noise, b_hat))
    orth = [n - nb * bh for n, bh in zip(noise, b_hat)]
    on = math.sqrt(sum(x * x for x in orth)) or 1.0
    s = math.sqrt(1.0 - cos * cos)
    return [cos * bh + s * (x / on) for bh, x in zip(b_hat, orth)]


def exp_threshold() -> dict:
    import numpy as np

    from fake_providers import TokenBagEmbedder
    from knowledge_lattice.adapters.embedder import SENTINELS

    embedder = TokenBagEmbedder(dim=2560)

    # ① 同模型控制组：确定性重嵌入
    vecs = embedder.embed(SENTINELS)
    again = embedder.embed(SENTINELS)
    same_cos = min(
        sum(a * b for a, b in zip(x, y))
        / (math.sqrt(sum(a * a for a in x)) * math.sqrt(sum(b * b for b in y)))
        for x, y in zip(vecs, again)
    )

    # ② fp16 量化噪声底（halfvec 存储环回——良性变换实测）
    texts = [line for line in (EVAL_DIR / "corpus.jsonl").read_text().splitlines() if line.strip()]
    sample = [json.loads(t)["text"][:400] for t in texts] + list(SENTINELS)
    fp16_cos = []
    for text in sample:
        v = np.asarray(embedder.embed([text])[0], dtype=np.float32)
        rt = v.astype(np.float16).astype(np.float32)
        c = float(np.dot(v, rt) / (np.linalg.norm(v) * np.linalg.norm(rt)))
        fp16_cos.append(c)
    fp16_cos_sorted = sorted(fp16_cos)

    # ③ 漂移扫描：精确余弦 c 的哨兵 → 两档判定
    def classify(min_cos: float) -> str:
        if min_cos < 0.95:
            return "reject（拒绝写入+关查询向量路）"
        if min_cos < 0.99:
            return "warn（告警审计）"
        return "ok（静默）"

    sweep = []
    for cos in (0.9995, 0.999, 0.997, 0.995, 0.99, 0.98, 0.96, 0.95, 0.93, 0.90):
        # 三哨兵同漂移档（probe 取 min——最保守面）
        min_cos = cos
        sweep.append({
            "exact_cosine": cos,
            "drift_pct": round((1 - cos) * 100, 2),
            "decision_0.99_0.95": classify(min_cos),
        })

    out = {
        "same_model_determinism_min_cosine": round(same_cos, 6),
        "fp16_roundtrip": {
            "n": len(fp16_cos),
            "min": round(fp16_cos_sorted[0], 6),
            "p50": round(fp16_cos_sorted[len(fp16_cos) // 2], 6),
        },
        "drift_sweep": sweep,
        "threshold_geometry": {
            "warn_boundary": "min cosine < 0.99 → 漂移 ≥1% 可见（告警档）",
            "reject_boundary": "min cosine < 0.95 → 漂移 ≥5% 拒绝",
            "silent_zone": "漂移 <1% 两档均不触发（分辨率=1%/5% 两档粒度）",
        },
    }
    save_result("m1-5-calib-threshold", out)
    return out


# ============ exp: bluegreen（pg） ============


def exp_bluegreen() -> dict:
    import psycopg

    from bench_common import pg_dsn, synth_vectors
    from knowledge_lattice.core.docs.acl import compile_acl
    from knowledge_lattice.store.postgres import migrate_db, setup_connection
    from knowledge_lattice.store.postgres.backend import PgBackend
    from knowledge_lattice.store.postgres.vec import format_vector

    N = 10_000
    DIM = 2560
    LABEL_OLD, LABEL_NEW = "synth-embed:2560", "synth-embed-b:2560"
    schema = f"lattice_bg_{uuid.uuid4().hex[:8]}"
    conn = psycopg.connect(pg_dsn(), autocommit=True)
    conn.execute(f'CREATE SCHEMA "{schema}"')
    conn.execute(f'SET search_path TO "{schema}", public')
    setup_connection(conn)
    migrate_db(conn)
    out: dict = {"pool": N, "dim": DIM}
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO orgs(id, name) VALUES('org:bg', 'bg')")
        cur.execute("INSERT INTO datasets(id, org_id, name) VALUES('ds:bg', 'org:bg', 'bg')")
        cur.execute("INSERT INTO users(id, username) VALUES('u_bg', 'u_bg')")
        cur.execute("INSERT INTO user_org_memberships(user_id, org_id, role)"
                    " VALUES('u_bg', 'org:bg', 'member')")
        with cur.copy(
            "COPY documents(id, org_id, dataset_id, title, content_hash, mime_type, parser,"
            " owner_user_id, raw_object_key, active_version) FROM STDIN"
        ) as cp:
            for i in range(N // 10):
                cp.write(f"doc:{i:05d}\torg:bg\tds:bg\tbg {i}\ts:{i}\ttext/plain\t"
                         f"docling\tu_bg\to/{i}\t1\n")
        with cur.copy(
            "COPY chunks(rid, id, doc_id, seq, version, content, content_seg) FROM STDIN"
        ) as cp:
            for rid in range(1, N + 1):
                cp.write(f"{rid}\tchk:{rid:06d}\tdoc:{(rid - 1) // 10:05d}\t{(rid - 1) % 10 + 1}"
                         f"\t1\tbg 块 {rid}\tbg 块 {rid}\n")
        vectors = synth_vectors(N)
        vectors_b = synth_vectors(N + 500_000)  # 蓝标签向量（独立确定性源）

        def copy_vectors(label: str, vecs) -> None:
            with cur.copy("COPY chunk_vectors(rid, embed_model, embedding) FROM STDIN") as cp:
                for i in range(N):
                    cp.write(f"{i + 1}\t{label}\t" + "[" + ",".join(
                        repr(float(x)) for x in vecs[i]) + "]\n")

        backend = PgBackend(conn)
        plan = compile_acl(backend, "u_bg", "org:bg", embed_model=LABEL_OLD)
        query_vec = [float(x) for x in vectors[7919]]

        def timing(fn, warmup=10, n=15) -> dict:
            for _ in range(warmup):
                fn()
            xs = []
            for _ in range(n):
                t0 = time.perf_counter()
                rows = fn()
                xs.append((time.perf_counter() - t0) * 1000)
                assert rows, "recall_vec 应有结果"
            xs.sort()
            return {"p50_ms": round(xs[n // 2], 1),
                    "p95_ms": round(xs[max(0, (n * 95 + 99) // 100 - 1)], 1)}

        # ① 单标签基线（绿前：仅旧标签在库）——首轮计时不弃会混入冷页效应，
        #    先空跑一遍预热页缓存再计时（与后续相位同热态）
        copy_vectors(LABEL_OLD, vectors)
        cur.execute("ANALYZE chunk_vectors")
        timing(lambda: backend.recall_vec(query_vec, plan, top_k=1024), warmup=20, n=3)
        out["single_label_old"] = timing(lambda: backend.recall_vec(query_vec, plan, top_k=1024))

        # ② 蓝绿共存（新标签 100% 写入——表 ×2）
        copy_vectors(LABEL_NEW, vectors_b)
        cur.execute("ANALYZE chunk_vectors")
        out["dual_label_query_old"] = timing(lambda: backend.recall_vec(query_vec, plan, top_k=1024))
        plan_new = compile_acl(backend, "u_bg", "org:bg", embed_model=LABEL_NEW)
        out["dual_label_query_new"] = timing(
            lambda: backend.recall_vec(query_vec, plan_new, top_k=1024))

        # ③ 新标签部分覆盖（50%——迁移进行中形态）：删一半蓝行重测旧标签
        cur.execute(f"DELETE FROM chunk_vectors WHERE embed_model = '{LABEL_NEW}' AND rid % 2 = 0")
        cur.execute("ANALYZE chunk_vectors")
        out["partial50_query_old"] = timing(lambda: backend.recall_vec(query_vec, plan, top_k=1024))

        # ④ 单标签基线复测（同热态对照——②③ 的差值须对基线漂移校正）
        cur.execute(f"DELETE FROM chunk_vectors WHERE embed_model = '{LABEL_NEW}'")
        cur.execute("ANALYZE chunk_vectors")
        out["single_label_old_rerun"] = timing(
            lambda: backend.recall_vec(query_vec, plan, top_k=1024))

        for key in ("dual_label_query_old", "dual_label_query_new", "partial50_query_old"):
            out[f"{key}_delta_vs_single_p95_pct"] = round(
                (out[key]["p95_ms"] - out["single_label_old"]["p95_ms"])
                / out["single_label_old"]["p95_ms"] * 100, 1)
        rr = out["single_label_old_rerun"]["p95_ms"]
        out["baseline_rerun_drift_p95_pct"] = round(
            (rr - out["single_label_old"]["p95_ms"]) / out["single_label_old"]["p95_ms"] * 100, 1)
    finally:
        try:
            conn.execute("SET search_path TO public")
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except psycopg.Error:
            pass
        finally:
            conn.close()
    save_result("m1-5-calib-bluegreen", out)
    return out


# ============ exp: stopwords / tsrankcd（黄金集变体——monkeypatch） ============

STOPWORDS_ZH = {
    "的", "了", "是", "在", "我", "你", "他", "它", "们", "什么", "哪些", "怎样",
    "怎么", "吗", "呢", "吧", "和", "与", "或", "及", "对于", "按", "按照",
    "根据", "被", "把", "让", "向", "从", "到", "会对", "各", "每",
}
STOPWORDS_EN = {
    "the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "with",
    "is", "are", "what", "which", "how", "do", "does", "be",
}
STOPWORDS = STOPWORDS_ZH | STOPWORDS_EN


def exp_stopwords(backend_name: str) -> dict:
    """query 侧停用词滤除（B-3② 假设验证——q01/q10 约 +7.1pp）。"""
    from knowledge_lattice.adapters import tokenizer

    original = tokenizer.segment_query

    def filtered(query: str) -> list[str]:
        return [t for t in original(query) if t.lower() not in STOPWORDS]

    out = {"backend": backend_name, "stopword_list_size": len(STOPWORDS)}
    out["baseline"] = run_golden(backend_name, _tokbag(), 32)
    tokenizer.segment_query = filtered
    try:
        out["stopword_filtered"] = run_golden(backend_name, _tokbag(), 32)
    finally:
        tokenizer.segment_query = original
    b, s = out["baseline"], out["stopword_filtered"]
    out["delta_pp"] = {
        "recall@10": round((s["recall@10"] - b["recall@10"]) * 100, 2),
        "recall@1": round((s["recall@1"] - b["recall@1"]) * 100, 2),
        "mrr": round((s["mrr"] - b["mrr"]) * 100, 2),
    }
    save_result(f"m1-5-calib-stopwords-{backend_name}", out)
    return out


def _tokbag():
    from fake_providers import TokenBagEmbedder

    return TokenBagEmbedder(dim=32)


def exp_tsrankcd() -> dict:
    """B-3④：PG ts_rank（现状）vs ts_rank_cd（同权重）排序对照。"""
    from knowledge_lattice.store.postgres import fts as pg_fts

    original = pg_fts.TS_RANK_SUM
    cd_sum = " + ".join(
        f"{weight} * ts_rank_cd({column}, query)" for column, weight in pg_fts.TS_RANK_WEIGHTS
    )
    out = {}
    out["baseline_ts_rank"] = run_golden("pg", _tokbag(), 32)
    pg_fts.TS_RANK_SUM = cd_sum
    try:
        out["ts_rank_cd"] = run_golden("pg", _tokbag(), 32)
    finally:
        pg_fts.TS_RANK_SUM = original
    b, c = out["baseline_ts_rank"], out["ts_rank_cd"]
    out["delta_pp"] = {
        "recall@10": round((c["recall@10"] - b["recall@10"]) * 100, 2),
        "mrr": round((c["mrr"] - b["mrr"]) * 100, 2),
    }
    save_result("m1-5-calib-tsrankcd-pg", out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp", required=True,
                        choices=["mrl", "threshold", "bluegreen", "stopwords", "tsrankcd"])
    parser.add_argument("--backend", default="sqlite", choices=["sqlite", "pg"])
    args = parser.parse_args()

    t0 = time.perf_counter()
    if args.exp == "mrl":
        result = exp_mrl(args.backend)
    elif args.exp == "threshold":
        result = exp_threshold()
    elif args.exp == "bluegreen":
        result = exp_bluegreen()
    elif args.exp == "stopwords":
        result = exp_stopwords(args.backend)
    else:
        result = exp_tsrankcd()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n[{args.exp}/{args.backend}] {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
