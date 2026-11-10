#!/usr/bin/env python
"""黄金集基线生成（TC-EVAL-01/02——双后端各一份基线报告）。

用法（m3-5 P3-3 更新——数据已是 M3 完整集 60q/73docs，缺省 label=m3）：
  uv run python scripts/eval_baseline.py --backend sqlite            # → m3-baseline-sqlite.*
  LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice \\
      uv run python scripts/eval_baseline.py --backend pg
  uv run python scripts/eval_baseline.py --backend sqlite --label m3 --out /tmp/x.md

产物：eval/reports/<label>-baseline-<backend>.md + .json（Recall@1/5/10 + MRR
+ 逐 query 明细 + 语料/运行口径）。运行口径与 tests/test_eval_01_golden.py
同构（FakeEmbedder 确定性向量、reranker/enhancer none 档——跨后端可比性
优先）；**矩阵种子与门禁同源**（tests/eval_seed.py seed_clean_eval_matrix——
P3-8/P3-9 冻结表同源前提）。

**m1 档只读保护**：m1-baseline-*.md/json 为 M1 小型集历史档（28q/39docs，
随数据扩容不再复现）——label=m1 需显式 ``--allow-m1-overwrite``（防旧命令
静默覆盖历史档）。
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

from eval_seed import ORG, seed_clean_eval_matrix  # noqa: E402

EVAL_DIR = ROOT / "eval"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["sqlite", "pg"], required=True)
    parser.add_argument("--label", default="m3",
                        help="基线标签（m3=M3 完整集〔缺省〕/ m1=M1 历史档——"
                             "m1 需 --allow-m1-overwrite）")
    parser.add_argument("--allow-m1-overwrite", action="store_true",
                        help="显式允许覆盖 m1 历史档（m1-baseline-*.md/json——"
                             "28q/39docs 小型集，随数据扩容不再复现）")
    parser.add_argument("--out", default=None, help="报告输出路径（缺省 eval/reports/）")
    args = parser.parse_args()

    if args.label == "m1" and not args.allow_m1_overwrite:
        print(
            "m1 档为历史归档（M1 小型集 28q/39docs，数据已扩容为 M3 完整集）——"
            "覆盖需显式 --allow-m1-overwrite；当前数据请用 --label m3",
            file=sys.stderr,
        )
        return 1

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
        seed_clean_eval_matrix(db)
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
        seed_clean_eval_matrix(PgDb(conn, schema, dsn))
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
        else EVAL_DIR / "reports" / f"{args.label}-baseline-{args.backend}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {args.label.upper()} 黄金集基线——{args.backend}"
        + ("（TC-EVAL-01）" if args.label == "m1" else "（TC-EVAL-02 完整集）"),
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
    json_path = out_path.with_suffix(".json")
    json_path.write_text(
        json.dumps({"label": args.label, "backend": args.backend,
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    **{k: v for k, v in report.items()}},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"baseline written: {out_path}")
    print(f"baseline json:    {json_path}")
    print(json.dumps({k: v for k, v in report.items() if k != "per_query"}, indent=2))

    if schema is not None:
        conn.execute("SET search_path TO public")
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
