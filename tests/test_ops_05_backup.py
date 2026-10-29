"""TC-OPS-05 备份快照与恢复演练【集成｜M2】（m2-2 D 组——NFR-10）。

断言面：快照（sqlite `VACUUM INTO` / pg `pg_dump -Fc`）+ `data/objects/` 一并
备份 → 新环境恢复 → 跑迁移（幂等 / 旧版本库前进）→ 抽查检索与矩阵子集 →
数据完整、检索正常、user_version 前进；maintenance 挂载（backup_snapshot
任务体 + 节流口径）。

pg 臂工具经 `LATTICE_PG_DUMP_CMD`（容器形态 `docker exec lattice-pg pg_dump`）
注入——本机无 PATH pg_dump（部署工具链口径，D2 豁免）。
RPO ≤24h / RTO ≤4h 口径记录随演练报告（benchmarks/report-m2-2-ops05.md）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from knowledge_lattice.config import Settings

PG_DUMP_ENV = "LATTICE_PG_DUMP_CMD"


def _recall_probe(backend, org: str = "org:tax", user: str = "u_full") -> dict:
    """恢复库检索抽查：编译 ACL（恢复库内成员/授权数据源）+ FTS 召回命中。"""
    from knowledge_lattice.core.docs.acl import compile_acl

    plan = compile_acl(backend, user, org)
    hits = backend.recall_fts(["common"], plan, top_k=10)
    return {"hits": hits, "plan": plan}


# ============ sqlite 臂：完整恢复演练 ============


def test_sqlite_snapshot_restore_drill(db_path) -> None:
    """快照 → 新环境恢复 → 迁移幂等 → 检索与矩阵子集 → user_version 保持
    （sqlite 臂专属；pg 臂有独立 dump/restore 用例——互斥形态不做参数化 skip）。"""
    from conftest import _seed_standard_matrix

    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.backup import (
        restore_database,
        restore_objects,
    )
    from knowledge_lattice.store.sqlite.backend import SqliteBackend
    from dbwrap import SqliteDb

    conn = connect(db_path)
    migrate_db(conn)
    wrapper = SqliteDb(conn)
    _seed_standard_matrix(wrapper)
    backend = SqliteBackend(conn)
    # 对象目录造数（objects 一并备份断言面）
    objects_dir = db_path.parent / "objects"
    objects_dir.mkdir()
    (objects_dir / "obj-1.html").write_bytes(b"<html>x</html>")

    snap = backend.backup_snapshot(
        db_path.parent / "backups", objects_dir=objects_dir,
    )
    assert Path(snap["database"]).is_file() and Path(snap["database"]).stat().st_size > 0
    assert snap["objects"] and Path(snap["objects"]).is_file()

    # ---- 新环境恢复 ----
    new_dir = db_path.parent / "restored"
    new_db = restore_database(Path(snap["database"]), new_dir / "lattice.db")
    restore_objects(Path(snap["objects"]), new_dir / "objects")
    assert (new_dir / "objects" / "obj-1.html").read_bytes() == b"<html>x</html>"

    conn = connect(new_db)
    try:
        applied = migrate_db(conn)  # 迁移幂等重放（已最新 → 空）
        assert applied == []
        # user_version 与源一致（源=最新）；数据完整抽查
        from knowledge_lattice.store.sqlite.backend import SqliteBackend

        rb = SqliteBackend(conn)
        assert rb.org_active_chunk_count("org:tax") > 0  # 块在
        probe = _recall_probe(rb)  # 检索正常（FTS 命中 + ACL 编译走恢复库）
        assert probe["hits"], "恢复库 FTS 召回应命中"
        assert probe["plan"].org_id == "org:tax"
        # 矩阵子集（v1.1 有值交集口径）：u_cn（region=CN、无 tax_type 授权）
        # 不见 tax_type 有值的 d_cn；u_cn_vat（CN+VAT）双见
        from knowledge_lattice.core.docs.acl import compile_acl

        plan_cn = compile_acl(rb, "u_cn", "org:tax")
        visible = rb.visible_doc_ids(plan_cn, ["d_cn", "d_multi", "d_os"])
        assert visible == {"d_multi"}
        plan_cv = compile_acl(rb, "u_cn_vat", "org:tax")
        assert rb.visible_doc_ids(plan_cv, ["d_cn", "d_multi", "d_os"]) == {
            "d_cn", "d_multi",
        }
        # 跨组织隔离子集：u_gl 对 org:tax 编译即拒（无成员关系——存在性敏感）
        from knowledge_lattice.core.docs.acl import AclDeniedError

        with pytest.raises(AclDeniedError):
            compile_acl(rb, "u_gl", "org:tax")
    finally:
        conn.close()


def test_sqlite_restore_advances_user_version(tmp_path) -> None:
    """旧版本库（v4）恢复 → 跑迁移 → user_version 前进到最新（演练「前进」半句）。"""
    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.backup import restore_database, snapshot_database
    from knowledge_lattice.store.sqlite.migrate import _apply_one, discover

    src = connect(tmp_path / "lattice.db")
    try:
        migrations = discover()
        for m in migrations:
            if m.version <= 4:  # 停在 0004——构造「上一版本」库
                assert _apply_one(src, m)
        assert src.execute("PRAGMA user_version").fetchone()[0] == 4
        snap = snapshot_database(src, tmp_path / "backups")
    finally:
        src.close()

    new_db = restore_database(snap, tmp_path / "restored" / "lattice.db")
    conn = connect(new_db)
    try:
        applied = migrate_db(conn)
        assert 5 in applied  # 0005 重放——user_version 前进
        assert conn.execute("PRAGMA user_version").fetchone()[0] == max(
            m.version for m in migrations
        )
        # target_version 列在（0005 生效）
        assert conn.execute(
            "SELECT count(*) FROM pragma_table_info('tasks')"
            " WHERE name = 'target_version'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


# ============ pg 臂：pg_dump / pg_restore 演练 ============


@pytest.fixture()
def _pg_dump_tool(monkeypatch):
    """pg 臂备份工具注入（docker 容器形态——本机无 PATH pg_dump）。"""
    if not shutil_which_pgdump():
        monkeypatch.setenv(PG_DUMP_ENV, "docker exec lattice-pg pg_dump")
        monkeypatch.setenv("LATTICE_PG_RESTORE_CMD", "docker exec -i lattice-pg pg_restore")


def shutil_which_pgdump() -> bool:
    import shutil

    return shutil.which("pg_dump") is not None


def test_pg_snapshot_restore_drill(pg_db, tmp_path, _pg_dump_tool) -> None:
    """pg_dump（schema 级）→ 新库 pg_restore → 迁移幂等 → 检索与矩阵子集
    （pg 臂专属——pg_db fixture 无 DSN 即 skip，门禁设 DSN 全实跑）。"""
    import uuid as _uuid

    import psycopg

    from knowledge_lattice.store.postgres import migrate_db, setup_connection
    from knowledge_lattice.store.postgres.backup import restore_database, snapshot_database
    from knowledge_lattice.store.postgres.backend import PgBackend

    from conftest import _seed_standard_matrix

    _seed_standard_matrix(pg_db)
    dump = snapshot_database(pg_db.dsn, tmp_path / "backups", schema=pg_db.schema)
    assert dump.is_file() and dump.stat().st_size > 0

    # ---- 新库恢复（独立 database——真实恢复形态） ----
    admin = psycopg.connect(pg_db.dsn, autocommit=True)
    restore_db = f"lattice_restore_{_uuid.uuid4().hex[:10]}"
    restore_dsn = pg_db.dsn.rsplit("/", 1)[0] + "/" + restore_db
    try:
        admin.execute(f'CREATE DATABASE "{restore_db}"')
        # 恢复环境前置：目标库预装 pgvector（dump 的 chunk_vectors.embedding
        # 依赖 vector 类型——runbook 恢复步骤第 0 步）
        pre = psycopg.connect(restore_dsn, autocommit=True)
        try:
            pre.execute("CREATE EXTENSION IF NOT EXISTS vector")
        finally:
            pre.close()
        restore_database(restore_dsn, dump)

        rc = psycopg.connect(restore_dsn, autocommit=True)
        try:
            rc.execute(f'SET search_path TO "{pg_db.schema}", public')
            setup_connection(rc)  # 工厂纪律（含审计分区滚动——schema 同名恢复）
            applied = migrate_db(rc)
            assert applied == []  # 迁移幂等
            row = rc.execute("SELECT count(*) FROM schema_migrations").fetchone()
            assert row[0] >= 5  # 版本记录完整
            rb = PgBackend(rc)
            assert rb.org_active_chunk_count("org:tax") > 0
            probe = _recall_probe(rb)  # 检索正常（FTS 五列 GENERATED 随 dump 恢复）
            assert probe["hits"], "恢复库 FTS 召回应命中"
            from knowledge_lattice.core.docs.acl import compile_acl

            plan_cn = compile_acl(rb, "u_cn", "org:tax")
            assert rb.visible_doc_ids(plan_cn, ["d_cn", "d_multi", "d_os"]) == {
                "d_multi",
            }
            plan_cv = compile_acl(rb, "u_cn_vat", "org:tax")
            assert rb.visible_doc_ids(plan_cv, ["d_cn", "d_multi", "d_os"]) == {
                "d_cn", "d_multi",
            }
        finally:
            rc.close()
    finally:
        admin.execute(f'DROP DATABASE IF EXISTS "{restore_db}" WITH (FORCE)')
        admin.close()


# ============ maintenance 挂载（backup 任务体 + 节流 + audit bodies） ============


def test_maintenance_backup_body_sqlite(matrix, tmp_path, _pg_dump_tool) -> None:
    """快照任务体挂 maintenance（D2）：backup_interval_s=0 每轮真快照 + audit
    ship/seal/prune 三体出现在 stats（注册表 P3-N11——顺序 ship→seal→prune）。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.credentials import CredentialService
    from knowledge_lattice.worker.maintenance import MAINTENANCE_BODIES, run_maintenance

    backend = matrix.make_backend()
    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        backup_interval_s=0,  # 测试：每轮快照
    )
    creds = CredentialService(backend, settings, tmp_path / "objects")
    task_id = backend.create_task(None, task_type="maintenance")
    stats = run_maintenance(backend, creds, settings, task_id)

    # 注册表完整（P3-N11）：m2-1 四体 + m2-2 四体，且 ship 先于 seal/prune
    names = list(MAINTENANCE_BODIES)
    assert names.index("audit_shipped") < names.index("audit_months_sealed")
    assert names.index("audit_months_sealed") < names.index("audit_months_pruned")
    assert "backup_snapshot" in names
    # 快照真实落盘（backup_interval_s=0 → 非 throttled）
    snap = stats["backup_snapshot"]
    assert isinstance(snap, dict) and Path(snap["database"]).is_file()
    assert Path(snap["database"]).parent == tmp_path / "backups"
    assert stats["audit_shipped"] == {"shipped": 0}  # 无待搬运行
    assert stats["audit_months_sealed"]["sealed"] == []
    assert backend.get_task(task_id)["status"] == "done"


def test_maintenance_backup_throttle_and_unavailable(matrix, tmp_path, _pg_dump_tool) -> None:
    """节流（interval 内二轮 throttled）+ 工具可用性**分支断言**（P3-8/R2：
    无条件 skip——工具可用→真实快照+节流；不可用→unavailable 显式状态）。

    P2-4/R2：真实快照**失败**（工具在但子进程非零）不再混入 unavailable——
    落 errors 任务 failed（见 test_maintenance_backup_failure_fails_task）。
    """
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.credentials import CredentialService
    from knowledge_lattice.worker.maintenance import run_maintenance

    backend = matrix.make_backend()
    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        backup_interval_s=3600.0,  # 首轮跑、二轮节流
    )
    creds = CredentialService(backend, settings, tmp_path / "objects")
    task1 = backend.create_task(None, task_type="maintenance")
    stats1 = run_maintenance(backend, creds, settings, task1)
    first = stats1["backup_snapshot"]

    if matrix.is_sqlite:
        assert isinstance(first, dict) and Path(first["database"]).is_file()
        task2 = backend.create_task(None, task_type="maintenance")
        stats2 = run_maintenance(backend, creds, settings, task2)
        assert stats2["backup_snapshot"] == "throttled"  # interval 内二轮跳过
        assert backend.get_task(task2)["status"] == "done"
        return

    # pg 臂：按工具可用性分支（_pg_dump_tool 已尽力注入 docker 形态）
    from knowledge_lattice.store.postgres.backup import _resolve_command

    try:
        _resolve_command("LATTICE_PG_DUMP_CMD", "pg_dump")
        tool_available = True
    except Exception:
        tool_available = False
    if tool_available:
        assert isinstance(first, dict) and Path(first["database"]).is_file()
        task2 = backend.create_task(None, task_type="maintenance")
        stats2 = run_maintenance(backend, creds, settings, task2)
        assert stats2["backup_snapshot"] == "throttled"
        assert backend.get_task(task2)["status"] == "done"
    else:
        assert str(first).startswith("unavailable")  # 工具缺失——显式状态非失败
        assert backend.get_task(task1)["status"] == "done"


def test_maintenance_backup_failure_fails_task(matrix, tmp_path) -> None:
    """P2-4/R2 回归：「工具在但失败」（pg 臂 LATTICE_PG_DUMP_CMD=false——命令
    存在、退出码 1）→ BackupToolError 落 maintenance errors → 任务 **failed**
    且 error 前缀 backup_snapshot（NFR-10 可发现信号）；工具缺失（命令二进制
    不存在）维持 unavailable 不判失败。sqlite 臂恒真快照——本用例 pg 专属
    语义由 matrix 参数化下的 pg 臂承载（sqlite 臂断言真快照路径）。"""
    import pytest as _pytest

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings as _Settings
    from knowledge_lattice.core.docs.credentials import CredentialService
    from knowledge_lattice.worker.maintenance import run_maintenance

    backend = matrix.make_backend()
    settings = _Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    creds = CredentialService(backend, settings, tmp_path / "objects")
    if matrix.is_sqlite:
        # sqlite 无外部工具面：真快照路径（对照组——工具失败态不适用）
        task = backend.create_task(None, task_type="maintenance")
        stats = run_maintenance(backend, creds, settings, task)
        assert isinstance(stats["backup_snapshot"], dict)
        assert backend.get_task(task)["status"] == "done"
        return

    import os

    old = os.environ.get("LATTICE_PG_DUMP_CMD")
    try:
        # ① 工具在但失败：false 命令退出码 1 → 任务 failed + errors 前缀
        os.environ["LATTICE_PG_DUMP_CMD"] = "false"
        task = backend.create_task(None, task_type="maintenance")
        with _pytest.raises(RuntimeError, match="backup_snapshot"):
            run_maintenance(backend, creds, settings, task)
        row = backend.get_task(task)
        assert row["status"] == "failed"
        assert "backup_snapshot" in (row["error"] or "")
        # ② 工具缺失：命令二进制不存在 → unavailable、任务 done
        os.environ["LATTICE_PG_DUMP_CMD"] = "no-such-backup-binary"
        task2 = backend.create_task(None, task_type="maintenance")
        stats2 = run_maintenance(backend, creds, settings, task2)
        assert str(stats2["backup_snapshot"]).startswith("unavailable")
        assert backend.get_task(task2)["status"] == "done"
    finally:
        if old is None:
            os.environ.pop("LATTICE_PG_DUMP_CMD", None)
        else:
            os.environ["LATTICE_PG_DUMP_CMD"] = old
