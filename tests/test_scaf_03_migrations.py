"""TC-SCAF-03 迁移框架：改表流程与 foreign_key_check【单测｜M0a】（sqlite-only）。

- ① 迁移期间临时关闭外键、结束恢复；正常迁移后 `PRAGMA foreign_key_check` 空；
- ② 迁移窗口内注入违反外键的数据 → 同迁移检出违例即回滚，库内状态与迁移前一致（#33 P1-1）；
- ③ `user_version` 只前进、重复运行迁移幂等（无重放副作用）；
- ④ P2-1 并发语义：版本判定在 BEGIN IMMEDIATE 写锁内重读——并发进程已应用同版本
  迁移时第二条连接干净跳过（绝不撞 "table already exists"）。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest
from helpers import (
    seed_dataset,
    seed_dim_value,
    seed_dimension,
    seed_grant,
    seed_org,
    seed_user,
    table_names,
    trigger_names,
)

# 测试迁移 v3（0002 已被 schema v1.1 占用——M0b-3）：「建新表→拷数据→删旧表」
# 形态（dimensions 重建 + remark 列）。
# 注意：SQLite DROP 被其他触发器体内引用的表会报错（no such table）——须先拆
# trg_membership_delete_cleanup 与 trg_docdims_consistency（体内 SELECT dimensions），
# 表重建后连同 trg_dimensions_org_immutable（随 DROP TABLE 连带删除）一并重建。
V3_REBUILD_SQL = """\
-- 0003 测试迁移：dimensions 重建加 remark 列（建新表→拷数据→删旧表）
DROP TRIGGER trg_membership_delete_cleanup;
DROP TRIGGER trg_docdims_consistency;
CREATE TABLE dimensions_new (
  id            TEXT PRIMARY KEY,
  org_id        TEXT NOT NULL REFERENCES orgs(id),
  key           TEXT NOT NULL,
  name          TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
  required      INTEGER NOT NULL DEFAULT 1,
  enabled       INTEGER NOT NULL DEFAULT 1,
  grant_source  TEXT NOT NULL DEFAULT 'local',
  value_source  TEXT NOT NULL DEFAULT 'local',
  remark        TEXT,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP,
  UNIQUE(org_id, key)
);
INSERT INTO dimensions_new(id, org_id, key, name, status, required, enabled, grant_source, value_source, created_at, updated_at)
  SELECT id, org_id, key, name, status, required, enabled, grant_source, value_source, created_at, updated_at FROM dimensions;
DROP TABLE dimensions;
ALTER TABLE dimensions_new RENAME TO dimensions;
CREATE TRIGGER trg_dimensions_org_immutable BEFORE UPDATE OF org_id ON dimensions
BEGIN SELECT RAISE(ABORT, 'dimensions.org_id is immutable'); END;
CREATE TRIGGER trg_membership_delete_cleanup AFTER DELETE ON user_org_memberships
BEGIN
  DELETE FROM user_dimension_grants
  WHERE user_id = OLD.user_id
    AND dimension_id IN (SELECT id FROM dimensions WHERE org_id = OLD.org_id);
END;
CREATE TRIGGER trg_docdims_consistency BEFORE INSERT ON document_dimensions
WHEN (SELECT dimension_id FROM dimension_values WHERE id = NEW.value_id) != NEW.dimension_id
  OR (SELECT org_id FROM dimensions WHERE id = NEW.dimension_id)
    != (SELECT org_id FROM documents WHERE id = NEW.doc_id)
BEGIN SELECT RAISE(ABORT, 'document_dimensions consistency violation'); END;
"""


def _migrated_conn(db_path: Path) -> sqlite3.Connection:
    from knowledge_lattice.store.sqlite import connect, migrate_db

    c = connect(db_path)
    migrate_db(c)
    return c


def _write_v2(tmp_path: Path) -> Path:
    mig_dir = tmp_path / "extra_migrations"
    mig_dir.mkdir()
    (mig_dir / "0003_test_rebuild_dimensions.sql").write_text(V3_REBUILD_SQL, encoding="utf-8")
    return mig_dir


def _v3_dirs(tmp_path: Path) -> list[Path]:
    from knowledge_lattice.store.sqlite.migrate import BUILTIN_DIRS

    return [BUILTIN_DIRS["docs"], BUILTIN_DIRS["semantic"], _write_v2(tmp_path)]


def test_fresh_migrate_applies_schema_v1(db_path: Path) -> None:
    from knowledge_lattice.store.sqlite.migrate import BUILTIN_DIRS, discover

    conn = _migrated_conn(db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2  # v1.1（0001+0002）
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    # 文档侧 §4 全量表落库 + v1.1 分表 chunk_vectors（M0b-3）；sem_* 不在（M2-S1）；
    # audit_events 不在主库（属月库）
    names = table_names(conn)
    expected = {
        "orgs", "datasets", "dimensions", "dimension_values", "users",
        "user_org_memberships", "user_dimension_grants", "documents",
        "document_dimensions", "acl_entries", "chunks", "chunks_fts",
        "chunk_vectors", "quality_flags", "tasks", "embedding_fingerprints",
        "audit_outbox",
    }
    assert expected <= names, f"missing tables: {expected - names}"
    assert not {n for n in names if n.startswith("sem_")}
    assert "audit_events" not in names

    # 内置迁移目录为二维结构 store/sqlite/migrations/{docs,semantic}
    assert (BUILTIN_DIRS["docs"] / "0001_schema_v1.sql").is_file()
    assert BUILTIN_DIRS["semantic"].is_dir()
    assert [m.version for m in discover()] == [1, 2]  # M0a-1 基线 + M0b-3 v1.1
    conn.close()


def test_migrate_idempotent_rerun_no_side_effects(db_path: Path) -> None:
    from knowledge_lattice.store.sqlite import migrate_db

    conn = _migrated_conn(db_path)
    seed_org(conn)
    seed_user(conn, "u0")
    seed_dataset(conn)
    conn.execute(
        "INSERT INTO documents(id, org_id, dataset_id, title, content_hash, mime_type, parser,"
        " owner_user_id, raw_object_key)"
        " VALUES('doc:1','org:tax','ds:vat','t','sha256:x','application/pdf','docling','u0','objects/x')"
    )
    before = conn.execute("SELECT count(*) FROM documents").fetchone()[0]

    applied = migrate_db(conn)
    assert applied == []  # user_version 已是最新，无重放
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == before
    conn.close()


def test_migration_rebuild_flow_with_fk_check(db_path: Path, tmp_path: Path) -> None:
    """① 正常「建新表→拷数据→删旧表」迁移：外键窗口内关闭、结束 foreign_key_check 空。"""
    from knowledge_lattice.store.sqlite import migrate_db

    conn = _migrated_conn(db_path)
    seed_org(conn)
    dim_id = seed_dimension(conn)
    seed_dim_value(conn, dim_id)
    extra_dirs = _v3_dirs(tmp_path)

    applied = migrate_db(conn, dirs=extra_dirs)
    assert applied == [3]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    cols = {r[1] for r in conn.execute("PRAGMA table_info(dimensions)")}
    assert "remark" in cols  # 新表结构生效
    assert conn.execute("SELECT key FROM dimensions").fetchone()[0] == "region"  # 数据拷贝保真

    # 迁移结束外键已恢复：孤儿行仍被拒
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id)"
            " VALUES('ghost-user', ?, ?)",
            (dim_id, f"val:{dim_id}:CN"),
        )
    conn.close()


def test_migration_fk_violation_detected_and_rolled_back(db_path: Path, tmp_path: Path) -> None:
    """② 迁移窗口内注入违例行 → 同迁移 foreign_key_check 检出即回滚，库态与迁移前一致。"""
    from knowledge_lattice.store.sqlite import migrate_db
    from knowledge_lattice.store.sqlite.migrate import MigrationError

    conn = _migrated_conn(db_path)
    seed_org(conn)
    seed_user(conn)
    dim_id = seed_dimension(conn)
    val_id = seed_dim_value(conn, dim_id)
    seed_grant(conn, dim_id=dim_id, val_id=val_id)  # 正常授权行（v1.1 态基线）
    extra_dirs = _v3_dirs(tmp_path)

    # setup：经迁移窗口同款写入路径（临时关闭外键）注入一行违反外键的脏数据
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id)"
        " VALUES('ghost-user', ?, ?)",
        (dim_id, val_id),
    )
    conn.execute("PRAGMA foreign_keys = ON")

    grants_before = conn.execute("SELECT count(*) FROM user_dimension_grants").fetchone()[0]
    with pytest.raises(MigrationError, match="foreign_key_check"):
        migrate_db(conn, dirs=extra_dirs)

    # P2-2：失败路径 finally 恢复外键的直接证据——raises 后、任何手动 PRAGMA 之前断言
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    # P3-6：回滚后触发器集合与迁移前一致（v2 迁移 DROP 的两个触发器随事务回滚恢复）
    assert {"trg_membership_delete_cleanup", "trg_docdims_consistency"} <= trigger_names(conn)

    # 回滚后库态与迁移前一致：user_version 未前进、DDL 未生效、既有数据不动
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    cols = {r[1] for r in conn.execute("PRAGMA table_info(dimensions)")}
    assert "remark" not in cols
    assert conn.execute("SELECT count(*) FROM user_dimension_grants").fetchone()[0] == grants_before

    # 清理注入行无需关闭外键（DELETE 本身不触发外键约束）；清理后孤儿插入仍被拒
    conn.execute("DELETE FROM user_dimension_grants WHERE user_id = 'ghost-user'")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id)"
            " VALUES('ghost-user2', ?, ?)",
            (dim_id, val_id),
        )
    conn.close()


# ============ P2-1 并发补偿测试（committer 建议的重读分支单测等价形式） ============


def test_apply_one_skips_when_version_already_applied(db_path: Path, tmp_path: Path) -> None:
    """写锁内重读分支：绕过 migrate_db 快速路径直调 _apply_one，库上版本已被
    并发推进（=3）时对同一 v3 迁移干净跳过——返回 False、无 "table already exists"。"""
    from knowledge_lattice.store.sqlite.migrate import _apply_one, discover

    conn = _migrated_conn(db_path)
    seed_org(conn)
    seed_dimension(conn)
    dirs = _v3_dirs(tmp_path)

    # 模拟并发进程已应用 v3：第二条连接真实跑完 0001+0002+v3
    from knowledge_lattice.store.sqlite import connect, migrate_db

    other = connect(db_path)
    try:
        assert migrate_db(other, dirs=dirs) == [3]
    finally:
        other.close()

    v3 = [m for m in discover(dirs) if m.version == 3][0]
    assert _apply_one(conn, v3) is False  # 写锁内重读 3>=3 → COMMIT + 跳过，绝不重放 DDL
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    # P3（M0a-1 遗留③-4）：干净跳过分支同样恢复 foreign_keys=ON（finally 覆盖跳过路径）
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_concurrent_migrate_both_processes_survive(db_path: Path, tmp_path: Path) -> None:
    """双连接 barrier 对齐并发跑 migrate_db：一者应用、另一者干净跳过；
    两者都正常返回（无 OperationalError 崩溃），每个版本恰好应用一次。"""
    from knowledge_lattice.store.sqlite import connect, migrate_db

    dirs = _v3_dirs(tmp_path)
    barrier = threading.Barrier(2)
    results: list[list[int] | BaseException] = []

    def run_migrate() -> None:
        c = connect(db_path)
        try:
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
    assert flattened == [1, 2, 3]  # 恰好应用一次，另一进程跳过
