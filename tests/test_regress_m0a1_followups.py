"""M0a-1 移交回归项（遗留承接②③）。

② 三条轻量回归测试：事务中 FK OFF → MigrationError / `:memory:` journal 失败 →
RuntimeError + 连接关闭 / `__init__` 导入身份（re-export 不覆盖同名子模块）；
③ R2 复审其余 P3 择要（触碰 migrate/connection 时顺手）：WAL 切换重试耗尽包装
RuntimeError、FK OFF 复查移入 try/finally（finally 恢复的直接取证在
test_scaf_03_migrations.py 的 fk_violation 用例——本文件事务场景 OFF 本为 no-op，
仅断言失败路径不留关闭态）；journal_mode 查询纳入重试已在 M0a-1 R2 落地
（connection.py 现行为）；跳过分支 foreign_keys==1 断言补在 test_scaf_03_migrations.py。
"""

from __future__ import annotations

import sqlite3
import types
import pytest
from pathlib import Path

from helpers import table_names

REGRESS_V3_SQL = (
    # 0002~0005 均被 builtin 占用（v1.1/uploads/tombstoned_at/task_target_
    # version〔M2.1 R2〕）——回归探针改用 0006
    "-- 0006 回归用最小迁移（触发 _apply_one 完整路径即可）\n"
    "CREATE TABLE regress_probe(x INTEGER);\n"
)


@pytest.fixture()
def regress_dirs(tmp_path: Path) -> list[Path]:
    from knowledge_lattice.store.sqlite.migrate import BUILTIN_DIRS

    extra = tmp_path / "regress_migrations"
    extra.mkdir()
    (extra / "0007_regress_probe.sql").write_text(REGRESS_V3_SQL, encoding="utf-8")
    return [BUILTIN_DIRS["docs"], BUILTIN_DIRS["semantic"], extra]


# ============ ② P3-1：事务中 FK OFF → MigrationError ============


def test_fk_off_in_transaction_raises_migration_error(conn, regress_dirs) -> None:
    """连接处于事务中 → `PRAGMA foreign_keys=OFF` 静默无效 → 复查检出 →
    MigrationError。注：本场景 OFF 本为 no-op（FK 从未真正关闭），raises 后
    `foreign_keys==1` 断言仅确认失败路径未留下关闭态外泄；finally 恢复动作的
    **直接取证**在 test_scaf_03_migrations.py 的 fk_violation 用例（M0a-1 R2）。"""
    from knowledge_lattice.store.sqlite.migrate import MigrationError, migrate_db

    assert "regress_probe" not in table_names(conn)  # 迁移未应用（前置）
    conn.execute("BEGIN")
    try:
        with pytest.raises(MigrationError, match="foreign_keys=OFF failed"):
            migrate_db(conn, dirs=regress_dirs)
    finally:
        conn.execute("ROLLBACK")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1  # 仍为 ON
    assert "regress_probe" not in table_names(conn)  # 迁移未生效
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 6  # 基线 + M2-S1 semantic_v1（0006）


# ============ ② P3-2：`:memory:` journal 失败 → RuntimeError + 连接关闭 ============


def test_connect_memory_rejected_and_connection_closed(monkeypatch) -> None:
    """`:memory:` 不支持 WAL（journal_mode 停留 memory）→ 复查失败 RuntimeError；
    打开的连接已关闭、不泄漏（经 sqlite3.connect 追踪取证）。"""
    from knowledge_lattice.store.sqlite import connect

    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        c = real_connect(*args, **kwargs)
        opened.append(c)
        return c

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)
    with pytest.raises(RuntimeError, match="journal_mode"):
        connect(":memory:")
    assert opened, "sqlite3.connect 未被调用"
    for c in opened:
        with pytest.raises(sqlite3.ProgrammingError):  # 已关闭连接不可再执行
            c.execute("SELECT 1")


# ============ ③ WAL 切换重试耗尽 → 包装 RuntimeError ============


def test_connect_wal_retry_exhausted_wrapped_runtimeerror(monkeypatch, tmp_path) -> None:
    """`PRAGMA journal_mode = WAL` 持续 OperationalError（并发持锁）→ 有限重试
    耗尽后抛 RuntimeError（连接工厂失败契约）而非裸 OperationalError；连接关闭。"""
    from knowledge_lattice.store.sqlite import connect

    class _WalLockedConn:
        """包装连接：仅 WAL 切换持续失败（其余 PRAGMA 真实执行）。"""

        def __init__(self, real: sqlite3.Connection) -> None:
            self._real = real
            self.closed = False

        def execute(self, sql, *args):
            if sql.strip() == "PRAGMA journal_mode = WAL":
                raise sqlite3.OperationalError("database is locked")
            return self._real.execute(sql, *args)

        def close(self):
            self.closed = True
            self._real.close()

    wrappers: list[_WalLockedConn] = []
    real_connect = sqlite3.connect

    def fake_connect(*args, **kwargs):
        w = _WalLockedConn(real_connect(*args, **kwargs))
        wrappers.append(w)
        return w

    monkeypatch.setattr(sqlite3, "connect", fake_connect)
    with pytest.raises(RuntimeError, match="journal_mode WAL"):
        connect(tmp_path / "wal.db")
    assert wrappers and all(w.closed for w in wrappers)  # 失败路径连接不泄漏


# ============ ② P3-12/13：`__init__` 导入身份 ============


def test_package_import_identity() -> None:
    """re-export 的 connect/migrate_db 与子模块定义同一；`pkg.migrate` 仍是模块
    （函数属性不覆盖同名子模块——footgun 防线）。"""
    import knowledge_lattice.store.sqlite as pkg
    from knowledge_lattice.store.sqlite import connection, migrate

    assert isinstance(pkg.migrate, types.ModuleType)
    assert pkg.migrate_db is migrate.migrate_db
    assert pkg.connect is connection.connect
    assert pkg.connection is connection
