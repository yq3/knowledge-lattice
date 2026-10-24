"""PG spike 专用断言（M0b-1）：TC-SCAF-02/03 后端行 v1.4 + 审计按月分区表。

- TC-SCAF-02 PG 等价：连接池参数（min/max）+ pgvector `<=>` 距离函数可用 +
  连接工厂版本断言（server_version ≥ 16——G-6 收窄口径）；
- TC-SCAF-03 PG 等价：`schema_migrations` 表 + 约束校验（违例整事务回滚——
  PG 原生约束即时校验，无外键窗口）+ 幂等重放 + 并发 advisory lock 干净跳过；
- 审计月库 → 按月分区表（§4 PG 映射）：分区滚动幂等、按月建新分区、append-only
  触发器在分区父表生效、写入落对应分区（接口 roll_monthly 不变）。
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

# ============ TC-SCAF-02 PG 等价：连接池参数 + pgvector 距离函数 ============


def test_pg_connect_pool_params_and_probe(pg_db) -> None:
    """连接池 min/max 参数生效 + 池连接可执行 + `<=>` 余弦距离可用（同向量距离 0）。"""
    from knowledge_lattice.store.postgres import connect_pool

    pool = connect_pool(pg_db.dsn, min_size=1, max_size=2, name="scaf02-pool")
    try:
        assert pool.min_size == 1  # 连接池参数断言（TC-SCAF-02 后端行 v1.4）
        assert pool.max_size == 2
        with pool.connection() as conn:
            assert conn.execute("SELECT 1").fetchone()[0] == 1
            dist = conn.execute(
                "SELECT '[1.0, 2.0]'::vector <=> '[1.0, 2.0]'::vector"
            ).fetchone()[0]
            assert dist is not None and abs(float(dist)) < 1e-6  # 同向量余弦距离为 0
    finally:
        pool.close()


def test_pg_connect_factory_server_version_assert(pg_db) -> None:
    """连接工厂版本断言（≥16——G-6）：setup 后连接可查版本；16.15 实测通过。"""
    from knowledge_lattice.store.postgres import connect

    conn = connect(pg_db.dsn)
    try:
        version_num = int(
            conn.execute("SELECT current_setting('server_version_num')").fetchone()[0]
        )
        assert version_num >= 160000
        ext = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        assert ext is not None and ext[0].startswith("0.8")  # pgvector 0.8.x（G-6）
    finally:
        conn.close()


# ============ TC-SCAF-03 PG 等价：schema_migrations + 约束校验 + 幂等/并发 ============


def test_pg_fresh_migrate_schema_v1(pg_db) -> None:
    """全新 schema 迁移：schema_migrations 落 version=1；16 表等价落库（15 主表 +
    工厂滚动 audit_events 分区表——主库 schema 不含）；sem_* 不在；chunks 五列
    tsvector GENERATED 在场（FTS5 虚表 + ai/ad/au 的 PG 等价物）。"""
    from knowledge_lattice.store.postgres.migrate import BUILTIN_DIRS, discover

    rows = pg_db.execute(
        "SELECT version, name, domain FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert rows == [(1, "schema_v1", "docs")]

    names = pg_db.table_names()
    expected = {
        "orgs", "datasets", "dimensions", "dimension_values", "users",
        "user_org_memberships", "user_dimension_grants", "documents",
        "document_dimensions", "acl_entries", "chunks", "quality_flags",
        "tasks", "embedding_fingerprints", "audit_outbox",
    }
    assert expected <= names, f"missing tables: {expected - names}"
    assert "audit_events" in names  # 连接工厂滚动的分区父表（月库的 PG 等价）
    assert "audit_events_" in " ".join(names)  # 当月分区
    assert not {n for n in names if n.startswith("sem_")}
    assert "chunks_fts" not in names  # 无 FTS5 虚表——tsvector 五列 GENERATED 取代

    # 五列 GENERATED（attgenerated='s'）——ai/ad/au 触发器的等价形态
    generated = {
        r[0]
        for r in pg_db.execute(
            "SELECT a.attname FROM pg_attribute a"
            " WHERE a.attrelid = 'chunks'::regclass AND a.attgenerated = 's'"
        )
    }
    assert generated == {
        "title_tsv", "content_tsv", "keywords_tsv", "llm_keywords_tsv", "tags_tsv",
    }

    # vector 列在场（pgvector；`<=>` 可用已在工厂断言/距离测试覆盖——G-6 精确扫描起步）
    col_type = pg_db.execute(
        "SELECT udt_name FROM information_schema.columns"
        " WHERE table_schema = current_schema() AND table_name = 'chunks'"
        "   AND column_name = 'embedding'"
    ).fetchone()[0]
    assert col_type == "vector"

    # 迁移目录二维结构 store/postgres/migrations/{docs,semantic}（semantic 空占位）
    assert (BUILTIN_DIRS["docs"] / "0001_schema_v1.sql").is_file()
    assert BUILTIN_DIRS["semantic"].is_dir()
    assert [m.version for m in discover()] == [1]


def test_pg_migrate_idempotent_rerun(pg_db, tmp_path: Path) -> None:
    """幂等重放：再跑迁移无新版本应用、数据不动。"""
    from knowledge_lattice.store.postgres import migrate_db

    from helpers import seed_dataset, seed_org

    seed_org(pg_db)
    seed_dataset(pg_db)
    before = pg_db.execute("SELECT count(*) FROM datasets").fetchone()[0]
    assert migrate_db(pg_db.raw) == []
    assert pg_db.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall() == [(1,)]
    assert pg_db.execute("SELECT count(*) FROM datasets").fetchone()[0] == before


def _write_pg_v2(tmp_path: Path, violation: bool) -> Path:
    """构造 v2 测试迁移：加 remark 列；（violation=True 时）再插一行违反外键的数据——
    同事务内约束违例 → 整事务回滚（PG 原生约束即时校验，无外键窗口）。"""
    mig_dir = tmp_path / "pg_extra_migrations"
    mig_dir.mkdir(parents=True, exist_ok=True)
    sql = "-- 0002 测试迁移：dimensions 加 remark 列\nALTER TABLE dimensions ADD COLUMN remark TEXT;\n"
    if violation:
        sql += (
            "-- 违例行（引用不存在 user）：PG 原生外键即时拒绝 → 整事务回滚\n"
            "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id)"
            " SELECT 'ghost-user', id, id FROM dimensions LIMIT 1;\n"
        )
    (mig_dir / "0002_test_add_remark.sql").write_text(sql, encoding="utf-8")
    return mig_dir


def test_pg_migration_applies_and_tracks_schema_migrations(pg_db, tmp_path: Path) -> None:
    """正常迁移：v2 应用后 schema_migrations 前进到 2、DDL 生效、数据保真。"""
    from knowledge_lattice.store.postgres import migrate_db

    from helpers import seed_dimension, seed_org

    seed_org(pg_db)
    seed_dimension(pg_db)
    dirs = [_write_pg_v2(tmp_path, violation=False)]

    applied = migrate_db(pg_db.raw, dirs=dirs)
    assert applied == [2]
    assert pg_db.execute(
        "SELECT version, name FROM schema_migrations ORDER BY version"
    ).fetchall() == [(1, "schema_v1"), (2, "test_add_remark")]
    cols = {
        r[0]
        for r in pg_db.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'dimensions'"
        )
    }
    assert "remark" in cols
    assert pg_db.execute("SELECT key FROM dimensions").fetchone()[0] == "region"
    # 幂等重放：再跑无新版本
    assert migrate_db(pg_db.raw, dirs=dirs) == []


def test_pg_migration_violation_rolls_back_atomically(pg_db, tmp_path: Path) -> None:
    """违例回滚：v2 含外键违例 INSERT → 迁移失败、schema_migrations 不前进、
    已执行 DDL 一并回滚（库态与迁移前一致）——TC-SCAF-03 后端行「约束校验
    （违例回滚）」。"""
    import psycopg

    from knowledge_lattice.store.postgres import migrate_db
    from knowledge_lattice.store.postgres.migrate import BUILTIN_DIRS

    from helpers import seed_dimension, seed_org

    seed_org(pg_db)
    seed_dimension(pg_db)
    bad_dirs = [BUILTIN_DIRS["docs"], _write_pg_v2(tmp_path, violation=True)]

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrate_db(pg_db.raw, dirs=bad_dirs)

    # 回滚后库态与迁移前一致：版本未前进、DDL 未生效
    assert pg_db.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall() == [(1,)]
    cols = {
        r[0]
        for r in pg_db.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'dimensions'"
        )
    }
    assert "remark" not in cols
    assert pg_db.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'ghost-user'"
    ).fetchone()[0] == 0

    # 修复后同号迁移可正常应用（无残留半成品）
    good_dirs = [BUILTIN_DIRS["docs"], _write_pg_v2(tmp_path / "good", violation=False)]
    assert migrate_db(pg_db.raw, dirs=good_dirs) == [2]


def test_pg_concurrent_migrate_advisory_lock_clean_skip(pg_db, tmp_path: Path) -> None:
    """并发语义：双连接 barrier 对齐跑迁移——advisory lock 序列化，一者应用、
    另一者在锁内重读已应用版本后干净跳过（不撞 already exists、恰应用一次）。"""
    import psycopg

    from knowledge_lattice.store.postgres import migrate_db
    from knowledge_lattice.store.postgres.migrate import BUILTIN_DIRS

    dirs = [BUILTIN_DIRS["docs"], _write_pg_v2(tmp_path, violation=False)]
    schema = pg_db.schema

    barrier = threading.Barrier(2)
    results: list[list[int] | BaseException] = []

    def run_migrate() -> None:
        c = psycopg.connect(pg_db.dsn, autocommit=True)
        try:
            c.execute(f'SET search_path TO "{schema}", public')
            barrier.wait(timeout=10)
            results.append(migrate_db(c, dirs=dirs))
        except BaseException as exc:  # noqa: BLE001——记录失败供断言
            results.append(exc)
        finally:
            c.close()

    t = threading.Thread(target=run_migrate)
    t.start()
    run_migrate()
    t.join(timeout=30)

    assert len(results) == 2
    failures = [r for r in results if isinstance(r, BaseException)]
    assert failures == [], f"concurrent migrate crashed: {failures!r}"
    flattened = sorted(v for r in results for v in r)  # type: ignore[union-attr]
    assert flattened == [2]  # 恰好应用一次，另一连接干净跳过


# ============ 审计月库 → 按月分区表（§4 PG 映射） ============


def test_pg_audit_partition_rolling_idempotent(pg_db) -> None:
    """分区滚动幂等：同月重复 ensure 不重复建、返回同名；跨月滚动建新分区。"""
    from knowledge_lattice.store.postgres.audit import ensure_month_partition

    conn = pg_db.raw
    oct_ = ensure_month_partition(conn, when=datetime(2026, 10, 15, tzinfo=UTC))
    oct_again = ensure_month_partition(conn, when=datetime(2026, 10, 31, tzinfo=UTC))
    nov = ensure_month_partition(conn, when=datetime(2026, 11, 1, tzinfo=UTC))
    assert oct_ == oct_again == "audit_events_202610"
    assert nov == "audit_events_202611"

    parts = {
        r[0]
        for r in pg_db.execute(
            "SELECT tablename FROM pg_tables"
            " WHERE schemaname = current_schema() AND tablename LIKE 'audit_events_%%'"
        )
    }
    assert {"audit_events_202610", "audit_events_202611"} <= parts

    # 写入落对应分区（RANGE 按 created_at）
    pg_db.execute(
        "INSERT INTO audit_events(id, org_id, actor, action, outcome, created_at)"
        " VALUES('evt:oct', 'org:tax', 'user:u1', 'search', 'accepted', '2026-10-15 00:00:00')"
    )
    pg_db.execute(
        "INSERT INTO audit_events(id, org_id, actor, action, outcome, created_at)"
        " VALUES('evt:nov', 'org:tax', 'user:u1', 'search', 'accepted', '2026-11-02 00:00:00')"
    )
    assert pg_db.execute(
        "SELECT count(*) FROM audit_events_202610"
    ).fetchone()[0] == 1
    assert pg_db.execute(
        "SELECT count(*) FROM audit_events_202611"
    ).fetchone()[0] == 1
    assert pg_db.execute(
        "SELECT count(*) FROM audit_events"
    ).fetchone()[0] == 2  # 父表全量可见


def test_pg_audit_append_only_triggers(pg_db) -> None:
    """append-only：UPDATE/DELETE 均被拒（分区父表上的行级触发器——消息与 sqlite
    月库版逐字同源；#33 P2-10）。"""
    pg_db.execute(
        "INSERT INTO audit_events(id, org_id, actor, action, outcome)"
        " VALUES('evt:1', 'org:tax', 'user:u1', 'search', 'accepted')"
    )
    for sql in (
        "UPDATE audit_events SET action='grant' WHERE id='evt:1'",
        "DELETE FROM audit_events WHERE id='evt:1'",
    ):
        with pytest.raises(pg_db.integrity_error, match="append-only"):
            pg_db.execute(sql)


def test_pg_factory_rolls_current_month_partition(pg_db) -> None:
    """连接工厂滚动当月分区（setup_connection 内 ensure_audit——与 sqlite 连接工厂
    滚动当月月库同语义）。"""
    month = datetime.now(UTC).strftime("%Y%m")
    assert f"audit_events_{month}" in pg_db.table_names()
    # roll_monthly 接口不变（AuditBackend 协议——月库/分区差异在包内吸收）
    backend = pg_db.make_backend()
    assert backend.roll_monthly(datetime(2026, 5, 1, tzinfo=UTC)) == "audit_events_202605"
