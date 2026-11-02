"""TC-OPS-05 恢复演练脚本（m2-2 D 组——NFR-10；报告归 benchmarks/report-m2-2-ops05.md）。

演练链路（双后端各一臂，真实服务层路径——IngestService 上传 / retrieve 检索）：

  造环境（迁移 + 矩阵造数 + 真实上传摄取）→ 快照（VACUUM INTO / pg_dump）
  → 新环境恢复（文件拷贝 / 新库 pg_restore）→ 跑迁移（幂等 / 版本前进）
  → 抽查检索（FTS 召回）与矩阵子集（维度 ACL 可见集）→ 数据完整对账。

用法：
  uv run python benchmarks/dr_ops05_drill.py                # 双臂（pg 需 LATTICE_PG_DSN）
  LATTICE_PG_DSN=... uv run python benchmarks/dr_ops05_drill.py --only sqlite
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

PAYLOAD = (
    "<html><body><h1>土地增值税清算</h1><p>房地产开发企业土地增值税清算规程。</p></body></html>"
).encode()
QUERY_TOKENS = ["土地", "增值税"]  # jieba 切分形态（与 content_seg 同口径）


def _drill_sqlite(report: dict) -> None:
    from fake_providers import FakeEmbedder

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.acl import compile_acl
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.backend import SqliteBackend
    from knowledge_lattice.store.sqlite.backup import (
        restore_database,
        restore_objects,
        snapshot as sqlite_snapshot,
    )

    steps: list[dict] = []
    root = Path(tempfile.mkdtemp(prefix="dr_ops05_sqlite_"))

    def step(name: str, fn):
        t0 = time.monotonic()
        out = fn()
        steps.append({"step": name, "seconds": round(time.monotonic() - t0, 3)})
        print(f"  [sqlite] {name}: {round(time.monotonic() - t0, 3)}s")
        return out

    # ① 造环境
    def _setup():
        (root / "src").mkdir(parents=True, exist_ok=True)
        conn = connect(root / "src" / "lattice.db")
        migrate_db(conn)
        from dbwrap import SqliteDb

        wrapper = SqliteDb(conn)
        from conftest import _seed_standard_matrix

        _seed_standard_matrix(wrapper)
        settings = Settings(environment="test", data_dir=root / "src", embed_dim=8)
        (root / "src" / "objects").mkdir(parents=True)
        service = IngestService(
            SqliteBackend(conn), FakeEmbedder(dim=8, model_name="fake-embed"),
            settings, EmbeddingGate(), root / "src" / "objects",
        )
        doc_id, task_id = service.create_document(
            org_id="org:tax", dataset_id="ds:vat_lib", title="drill",
            dims={"region": ["CN"]}, owner_user_id="u_full",
            file_bytes=PAYLOAD, mime_type="text/html", filename="drill.html",
        )
        service.run_task(task_id)
        doc = wrapper.execute(
            "SELECT active_status FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        assert doc and doc[0] == "searchable_full", f"源环境摄取未完成: {doc}"
        (root / "src" / "objects" / "drill.html").write_bytes(PAYLOAD)
        conn.close()
        return doc_id

    doc_id = step("setup+migrate+ingest", _setup)

    # ② 快照（主库 + objects + 审计月库——m2-3 B3/R2 P3-9）
    def _snapshot():
        conn = connect(root / "src" / "lattice.db")
        backend = SqliteBackend(conn)
        # 造审计事件并搬运（月库落盘——快照断言面）
        backend.append_outbox(
            "document.upload",
            json.dumps({"org_id": "org:tax", "user_id": "u_full",
                        "doc_id": "drill-doc"}),
        )
        backend.ship_outbox()
        snap = sqlite_snapshot(conn, root / "backups", root / "src" / "objects",
                               db_dir=root / "src")
        conn.close()
        return snap

    snap = step("snapshot(VACUUM INTO + objects tar + audit months tar)", _snapshot)

    # ③ 新环境恢复（主库 + objects + 月库 tar）
    def _restore():
        restore_database(Path(snap["database"]), root / "restored" / "lattice.db")
        if snap["objects"]:
            restore_objects(Path(snap["objects"]), root / "restored" / "objects")
        assert (root / "restored" / "objects" / "drill.html").read_bytes() == PAYLOAD
        # 月库恢复（m2-3 B3——R2 P3-9：恢复演练断言月库在场）
        import tarfile

        assert snap.get("audit_months"), "快照应含 audit_months（B3）"
        with tarfile.open(Path(snap["audit_months"]), "r:gz") as tar:
            tar.extractall(root / "restored", filter="data")
        monthly = sorted((root / "restored").glob("audit_*.db"))
        assert monthly, "恢复产物月库应在场（B3）"
        import sqlite3

        mconn = sqlite3.connect(monthly[0])
        try:
            assert mconn.execute(
                "SELECT count(*) FROM audit_events"
            ).fetchone()[0] >= 1, "恢复月库审计行在场"
        finally:
            mconn.close()

    step("restore(copy db + untar objects + untar audit months)", _restore)

    # ④ 跑迁移（幂等）+ user_version 一致性
    def _migrate():
        conn = connect(root / "restored" / "lattice.db")
        applied = migrate_db(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.close()
        assert applied == [], f"恢复库不应有待应用迁移: {applied}"
        assert version >= 5, version
        return version

    version = step("migrate(idempotent)+user_version", _migrate)

    # ⑤ 抽查检索 + 矩阵子集 + 数据对账
    def _verify():
        conn = connect(root / "restored" / "lattice.db")
        backend = SqliteBackend(conn)
        plan = compile_acl(backend, "u_full", "org:tax")
        hits = backend.recall_fts(QUERY_TOKENS, plan, top_k=5)
        assert hits, "恢复库检索未命中"
        plan_cn = compile_acl(backend, "u_cn", "org:tax")
        visible = backend.visible_doc_ids(
            plan_cn, ["d_cn", "d_multi", "d_os", doc_id]
        )
        assert visible == {"d_multi", doc_id}, visible  # v1.1 有值交集口径
        n_docs = conn.execute(
            "SELECT count(*) FROM documents"
        ).fetchone()[0]
        n_tasks = conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
        conn.close()
        return {"docs": n_docs, "tasks": n_tasks, "hits": len(hits)}

    counts = step("verify(search+matrix subset+integrity)", _verify)
    shutil.rmtree(root, ignore_errors=True)
    report["sqlite"] = {
        "steps": steps, "user_version": version, "counts": counts,
        "snapshot": {"database": Path(snap["database"]).name},
    }


def _drill_pg(report: dict, dsn: str) -> None:
    import psycopg

    from knowledge_lattice.store.postgres import migrate_db, setup_connection
    from knowledge_lattice.store.postgres.backup import (
        restore_database,
        snapshot_database,
    )
    from knowledge_lattice.store.postgres.backend import PgBackend
    from knowledge_lattice.store.postgres.connection import connect as pg_connect

    steps: list[dict] = []
    schema = f"drill_{uuid.uuid4().hex[:10]}"

    def step(name, fn):
        t0 = time.monotonic()
        out = fn()
        steps.append({"step": name, "seconds": round(time.monotonic() - t0, 3)})
        print(f"  [pg]     {name}: {round(time.monotonic() - t0, 3)}s")
        return out

    admin = psycopg.connect(dsn, autocommit=True)
    admin.execute(f'CREATE SCHEMA "{schema}"')
    src = pg_connect(dsn)
    src.execute(f'SET search_path TO "{schema}", public')
    migrate_db(src)
    try:
        # ① 造环境（矩阵造数 + SQL 直插在用块——演练数据面；检索走真实召回）
        from conftest import _seed_standard_matrix

        class _Wrap:
            def __init__(self, conn):
                self.raw = conn

            def execute(self, sql, params=()):
                if not isinstance(params, dict):
                    sql = sql.replace("?", "%s")
                cur = self.raw.execute(sql, params)
                if cur.description is None:
                    return _Rows([])
                return _Rows(cur.fetchall())

        class _Rows:
            def __init__(self, rows):
                self._rows = rows

            def fetchone(self):
                return self._rows[0] if self._rows else None

            def fetchall(self):
                return list(self._rows)

        from dbwrap import PgDb

        wrapper = PgDb(src, schema, dsn)
        step("setup+migrate", lambda: _seed_standard_matrix(wrapper))

        # ② 快照（schema 级 pg_dump）
        dump = step(
            "snapshot(pg_dump -Fc schema)",
            lambda: snapshot_database(dsn, Path(tempfile.mkdtemp()), schema=schema),
        )

        # ③ 新库恢复（CREATE DATABASE + CREATE EXTENSION + pg_restore）
        restore_db = f"lattice_drill_{uuid.uuid4().hex[:8]}"
        restore_dsn = dsn.rsplit("/", 1)[0] + "/" + restore_db

        def _restore():
            admin.execute(f'CREATE DATABASE "{restore_db}"')
            pre = psycopg.connect(restore_dsn, autocommit=True)
            pre.execute("CREATE EXTENSION IF NOT EXISTS vector")
            pre.close()
            restore_database(restore_dsn, dump)

        step("restore(new db + pg_restore)", _restore)

        # ④ 跑迁移（幂等）+ 版本记录
        rc = pg_connect(restore_dsn)
        rc.execute(f'SET search_path TO "{schema}", public')

        def _migrate():
            setup_connection(rc)
            applied = migrate_db(rc)
            n = rc.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
            assert applied == [] and n >= 5
            return n

        n_versions = step("migrate(idempotent)+schema_migrations", _migrate)

        # ⑤ 抽查检索 + 矩阵子集
        def _verify():
            backend = PgBackend(rc)
            from knowledge_lattice.core.docs.acl import compile_acl

            plan = compile_acl(backend, "u_full", "org:tax")
            hits = backend.recall_fts(["common"], plan, top_k=5)  # 矩阵块 content_seg
            assert hits, "恢复库检索未命中"
            plan_cn = compile_acl(backend, "u_cn", "org:tax")
            visible = backend.visible_doc_ids(plan_cn, ["d_cn", "d_multi", "d_os"])
            assert visible == {"d_multi"}, visible
            return {"hits": len(hits)}

        counts = step("verify(search+matrix subset)", _verify)
        rc.close()
        admin.execute(f'DROP DATABASE IF EXISTS "{restore_db}" WITH (FORCE)')
    finally:
        src.close()
        admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin.close()
    report["pg"] = {"steps": steps, "versions": n_versions, "counts": counts}


def main() -> None:
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["sqlite", "pg"], default=None)
    args = parser.parse_args()

    report: dict = {"drill": "TC-OPS-05 恢复演练", "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    print("=== TC-OPS-05 恢复演练（m2-2 / NFR-10）===")
    if args.only in (None, "sqlite"):
        _drill_sqlite(report)
    dsn = os.environ.get("LATTICE_PG_DSN")
    if args.only in (None, "pg"):
        if not dsn:
            print("  [pg] LATTICE_PG_DSN 未设置——pg 臂跳过（演练单臂完成）")
        else:
            os.environ.setdefault("LATTICE_PG_DUMP_CMD", "docker exec lattice-pg pg_dump")
            os.environ.setdefault(
                "LATTICE_PG_RESTORE_CMD", "docker exec -i lattice-pg pg_restore"
            )
            _drill_pg(report, dsn)
    print("\n=== 演练结果 JSON ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("DRILL PASS: 恢复后数据完整、检索正常、迁移幂等/版本记录齐备")


if __name__ == "__main__":
    main()
