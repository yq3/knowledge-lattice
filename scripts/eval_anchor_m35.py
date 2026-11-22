#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""m3-5 C 组：TC-EVAL-05 在线引用锚点抽样（agent 会话引用存在性打标）。

管道（``knowledge_lattice.eval.anchor_sampling``——读取走 store 层
``read_monthly_events``，存在性走 ``get_chunk``，core 零方言 SQL）：

1. ``--demo --backend {sqlite,pg}``：**构造会话形态**出数（开发态无真实
   agent 会话——沿 m2-5/m3-4 受阻先例如实登记，报告归档 eval/reports/）。
   构造链路=真实链路：M3 完整集语料摄取（73 docs）→ 真实检索配方逐 query
   搜索 → **QueryAuditQueue 直写审计月库**（agent actor 形态
   ``agent:demo:user:u_full``）→ 部分会话注入**伪造 chunk_id**（幻觉证据
   面——如实登记注入数）→ 月库读回抽样打标；
2. ``--db <path>``：真实生产月库抽样（sqlite 主库路径——月库同目录；
   pg 经 LATTICE_PG_DSN + ``--pg``，部署期用法）。

用法：
  uv run python scripts/eval_anchor_m35.py --demo --backend sqlite
  LATTICE_PG_DSN=… uv run python scripts/eval_anchor_m35.py --demo --backend pg
  uv run python scripts/eval_anchor_m35.py --db /path/to/lattice.db [--month YYYYMM]
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
REPORTS = EVAL_DIR / "reports"

# 构造会话的幻觉注入面（伪造 chunk_id——如实登记：非真实 agent 幻觉，
# 管道「引用不存在 ID = 幻觉证据」判定面的确定性演示）
FABRICATED_IDS = ["chk_agent_demo_fabricated_01", "chk_agent_demo_fabricated_02"]


def _open_backend(name: str, tmp: Path):
    if name == "sqlite":
        from knowledge_lattice.store.sqlite import connect, migrate_db
        from knowledge_lattice.store.sqlite.backend import SqliteBackend

        conn = connect(tmp / "lattice.db")
        migrate_db(conn)
        return SqliteBackend(conn), conn, None

    import os
    import uuid

    import psycopg

    from knowledge_lattice.store.postgres import migrate_db, setup_connection
    from knowledge_lattice.store.postgres.backend import PgBackend

    dsn = os.environ.get("LATTICE_PG_DSN")
    if not dsn:
        print("LATTICE_PG_DSN 未设置", file=sys.stderr)
        sys.exit(1)
    schema = f"lattice_anchor_{uuid.uuid4().hex[:12]}"
    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute(f'CREATE SCHEMA "{schema}"')
    conn.execute(f'SET search_path TO "{schema}", public')
    setup_connection(conn)
    migrate_db(conn)
    return PgBackend(conn), conn, schema


def _close(backend, conn, schema) -> None:
    if schema is not None:
        conn.execute("SET search_path TO public")
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    conn.close()


def run_demo(backend_name: str) -> dict:
    """构造会话全链（真实检索配方 + 真实审计写入/读回路径）。"""
    from dbwrap import SqliteDb

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.docs.quality import QualityService
    from knowledge_lattice.core.docs.retrieve import search as run_search
    from knowledge_lattice.eval.anchor_sampling import sample_anchors
    from knowledge_lattice.eval.harness import load_corpus, load_golden
    from knowledge_lattice.query_audit import QueryAuditQueue, build_query_event

    tmp = Path(tempfile.mkdtemp(prefix="lattice-anchor-"))
    backend, conn, schema = _open_backend(backend_name, tmp)
    try:
        db = SqliteDb(conn) if backend_name == "sqlite" else None
        seed_clean_eval_matrix(db if db is not None else _PgSeedShim(conn))
        settings = Settings(
            environment="test", data_dir=tmp, embed_dim=32,
            embed_model="tokbag-embed",
        )
        from fake_providers import TokenBagEmbedder

        embedder = TokenBagEmbedder(dim=32)
        gate = EmbeddingGate()
        quality = QualityService(backend, settings)
        service = IngestService(backend, embedder, settings, gate,
                                tmp / "objects", quality=quality)
        corpus = load_corpus(EVAL_DIR / "corpus.jsonl")
        golden = load_golden(EVAL_DIR / "golden.jsonl")

        # 语料摄取（doc_id 映射→chunk_id 收集：agent 会话引用的真实锚点）
        key_to_chunk: dict[str, str] = {}
        for doc in corpus:
            doc_id, task_id = service.create_document(
                org_id=ORG, dataset_id=doc.dataset, title=doc.title,
                dims=doc.dims, owner_user_id="u_full",
                file_bytes=doc.text.encode(doc.encoding),
                mime_type="text/plain", filename=f"{doc.doc_id}.txt",
            )
            service.run_task(task_id)
            for r in backend.fetch_window(doc_id, version=1, seq_lo=0, seq_hi=10_000):
                key_to_chunk[f"{doc.doc_id}#{r['seq']}"] = r["chunk_id"]

        # 构造 agent 会话：真实检索配方 + 审计直写（m3-2 链路）；每 5 个会话
        # 注入一个伪造 chunk_id（幻觉证据判定面演示——注入数如实入报告）
        qa = QueryAuditQueue(backend, flush_interval_s=60.0)
        try:
            sessions = injected = 0
            for case in golden:
                payload = run_search(
                    backend, settings, user_id="u_full", org_id=ORG,
                    query=case.query, top_k=5, gate=gate, embedder=embedder,
                )
                chunk_ids = [r["chunk_id"] for r in payload["results"]]
                if sessions % 5 == 0:  # 12/60 会话注入 1 个伪造 ID
                    chunk_ids = chunk_ids + [FABRICATED_IDS[sessions % 2]]
                    injected += 1
                qa.enqueue(build_query_event(
                    "search.query", org_id=ORG,
                    actor="agent:demo:user:u_full",
                    detail={"query": case.query, "top_k": 5,
                            "chunk_ids": chunk_ids},
                ))
                sessions += 1
            qa.flush()
        finally:
            qa.stop()

        from knowledge_lattice.store.taskclock import utc_now_ts

        events = backend.read_monthly_events(when=utc_now_ts())
        report = sample_anchors(backend, events, actor_prefix="agent:")
        report["backend"] = backend_name
        report["form"] = "constructed_sessions"  # 如实登记：构造会话非真实 agent
        report["fabricated_injected"] = injected
        report["corpus_docs"] = len(corpus)
        return report
    finally:
        _close(backend, conn, schema)


class _PgSeedShim:
    """pg 臂种子垫片（dbwrap PgDb 同款 execute/commit 面——eval_seed 复用）。"""

    def __init__(self, conn) -> None:
        from dbwrap import PgDb

        self._db = PgDb(conn, "seed", "")

    def execute(self, sql, params=()):
        return self._db.execute(sql, params)

    def commit(self):
        self._db.commit()


def run_from_db(db_path: Path, month: str | None) -> dict:
    """真实生产库抽样（sqlite 主库路径——月库同目录）。"""
    from knowledge_lattice.eval.anchor_sampling import sample_anchors
    from knowledge_lattice.store.sqlite import connect
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    conn = connect(db_path)
    try:
        backend = SqliteBackend(conn)
        if month is None:
            from knowledge_lattice.store.taskclock import utc_now_ts

            month = utc_now_ts()[:4] + utc_now_ts()[5:7]
        events = backend.read_monthly_events(when=f"{month}-01 00:00:00")
        report = sample_anchors(backend, events, actor_prefix="agent:")
        report["form"] = "production"
        report["month"] = month
        return report
    finally:
        conn.close()


def _write_report(report: dict, out_json: Path, out_md: Path) -> None:
    out_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = [
        "# m3-5 TC-EVAL-05 在线引用锚点抽样记录",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 形态：**{'构造会话（开发态无真实 agent 会话——如实登记，沿 m2-5/m3-4 先例）' if report['form'] == 'constructed_sessions' else '真实生产月库'}**"
        + (f"（注入伪造 chunk_id {report.get('fabricated_injected', 0)} 个会话——"
           "幻觉证据判定面确定性演示）" if report["form"] == "constructed_sessions" else ""),
        f"- 后端：{report.get('backend', '-')}",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 会话数（agent: actor，accepted search）| {report['sessions']} |",
        f"| 引用总数（chunk_id 次）| {report['citations_total']} |",
        f"| 去重 chunk_id 数 | {report['distinct_ids']} |",
        f"| 存在（锚点有效）| {report['existing']} |",
        f"| **缺失（幻觉证据）** | **{report['missing']}** |",
        f"| 缺失比例（记录级）| {report['missing_ratio']} |",
    ]
    if report["missing_ids"]:
        lines.append("")
        lines.append("缺失 ID 清单：" + "、".join(report["missing_ids"]))
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--demo", action="store_true",
                        help="构造会话形态（开发态——真实链路+幻觉注入演示）")
    parser.add_argument("--backend", choices=["sqlite", "pg"], default="sqlite")
    parser.add_argument("--db", type=Path, help="sqlite 生产主库路径（真实月库抽样）")
    parser.add_argument("--month", help="YYYYMM（--db 缺省当月）")
    args = parser.parse_args()

    REPORTS.mkdir(parents=True, exist_ok=True)
    if args.db is not None:
        report = run_from_db(args.db, args.month)
        stem = f"m3-5-anchor-sampling-prod-{time.strftime('%Y%m%d')}"
    elif args.demo:
        report = run_demo(args.backend)
        stem = f"m3-5-anchor-sampling-{args.backend}"
    else:
        parser.error("--demo 或 --db 二选一")
        return 1
    _write_report(report, REPORTS / f"{stem}.json", REPORTS / f"{stem}.md")
    print(f"anchor sampling report: {REPORTS / stem}.json / .md")
    print(json.dumps(
        {k: v for k, v in report.items() if k != "per_session_missing"},
        ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
