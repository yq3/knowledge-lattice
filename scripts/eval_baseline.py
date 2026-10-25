#!/usr/bin/env python
"""M1 黄金集基线生成（TC-EVAL-01——双后端各一份基线报告，M1-5 校准实验输入）。

用法：
  uv run python scripts/eval_baseline.py --backend sqlite
  LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice \\
      uv run python scripts/eval_baseline.py --backend pg

产物：eval/reports/m1-baseline-<backend>.md（Recall@1/5/10 + MRR + 逐 query 明细
+ 语料/运行口径）。运行口径与 tests/test_eval_01_golden.py 同构（FakeEmbedder
确定性向量、reranker/enhancer none 档——跨后端可比性优先）。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

EVAL_DIR = ROOT / "eval"
ORG = "org:tax"


def _seed_matrix(db) -> None:
    """org:tax 造数（与 conftest 标准矩阵等价的最小面：org/dims/users/grants）。"""
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
        seed_grant(
            db, user_id="u_full", dim_id=dim_id_for(ORG, "region"),
            val_id=val_id_for(ORG, "region", value),
        )
    seed_grant(  # 语料含 tax_type=VAT 文档——u_full 须有对应授权（FR-4 写校验）
        db, user_id="u_full", dim_id=dim_id_for(ORG, "tax_type"),
        val_id=val_id_for(ORG, "tax_type", "VAT"),
    )
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["sqlite", "pg"], required=True)
    parser.add_argument("--out", default=None, help="报告输出路径（缺省 eval/reports/）")
    args = parser.parse_args()

    from fake_providers import TokenBagEmbedder
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.docs.quality import QualityService
    from knowledge_lattice.eval.harness import load_corpus, load_golden, run_evaluation

    corpus = load_corpus(EVAL_DIR / "corpus.jsonl")
    golden = load_golden(EVAL_DIR / "golden.jsonl")
    tmp = Path(tempfile.mkdtemp(prefix="lattice-eval-"))
    schema = None

    if args.backend == "sqlite":
        from dbwrap import SqliteDb
        from knowledge_lattice.store.sqlite import connect, migrate_db
        from knowledge_lattice.store.sqlite.backend import SqliteBackend

        conn = connect(tmp / "lattice.db")
        migrate_db(conn)
        db = SqliteDb(conn)
        _seed_matrix(db)
        backend = SqliteBackend(conn)
    else:
        import os
        import uuid

        import psycopg

        from dbwrap import PgDb
        from knowledge_lattice.store.postgres import migrate_db, setup_connection
        from knowledge_lattice.store.postgres.backend import PgBackend

        dsn = os.environ.get("LATTICE_PG_DSN")
        if not dsn:
            print("LATTICE_PG_DSN 未设置", file=sys.stderr)
            return 1
        schema = f"lattice_eval_{uuid.uuid4().hex[:12]}"
        conn = psycopg.connect(dsn, autocommit=True)
        conn.execute(f'CREATE SCHEMA "{schema}"')
        conn.execute(f'SET search_path TO "{schema}", public')
        setup_connection(conn)
        migrate_db(conn)
        _seed_matrix(PgDb(conn, schema, dsn))
        backend = PgBackend(conn)

    objects_dir = tmp / "objects"
    settings = Settings(
        environment="test", data_dir=tmp, embed_dim=32, embed_model="tokbag-embed",
    )
    embedder = TokenBagEmbedder(dim=32)
    gate = EmbeddingGate()
    quality = QualityService(backend, settings)
    service = IngestService(backend, embedder, settings, gate, objects_dir, quality=quality)

    started = time.monotonic()
    report = run_evaluation(
        backend=backend, settings=settings, embedder=embedder, gate=gate,
        corpus=corpus, golden=golden, user_id="u_full", org_id=ORG,
        objects_dir=objects_dir, ingest_service=service,
    )
    elapsed = time.monotonic() - started

    out_path = (
        Path(args.out) if args.out
        else EVAL_DIR / "reports" / f"m1-baseline-{args.backend}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# M1 黄金集基线——{args.backend}（TC-EVAL-01）",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}（评测运行 {elapsed:.1f}s）",
        f"- 语料：{report['corpus_docs']} docs（合成——待决-1 未到位先行）/ "
        f"黄金集：{report['queries']} queries（zh/en/mix 三态、多 token）",
        "- 运行口径：TokenBagEmbedder(dim=32) token 袋确定性向量（稠密路语义代理——"
        "真实模型随 M1-5 接入）；reranker/enhancer=none；recall_window=1024；"
        "双路召回 + RRF（完整配方、无增强第三路）",
        f"- **recall@1 = {report['recall@1']}** / recall@5 = {report['recall@5']} / "
        f"**recall@10 = {report['recall@10']}** / **MRR = {report['mrr']}**",
        "",
        "## 逐 query 明细",
        "",
        "| qid | lang | n_results | recall@10 | rr |",
        "|---|---|---|---|---|",
    ]
    for q in report["per_query"]:
        lines.append(
            f"| {q['qid']} | {q['lang']} | {q['n_results']} | {q['recall@10']} | {q['rr']} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"baseline written: {out_path}")
    print(json.dumps({k: v for k, v in report.items() if k != "per_query"}, indent=2))

    if schema is not None:
        conn.execute("SET search_path TO public")
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
