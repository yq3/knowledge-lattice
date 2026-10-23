"""SQLite 迁移框架（design §3 迁移约定——#33 P1-1）。

外键处理约定：
  · 单步事务 BEGIN IMMEDIATE，`user_version` 在**同一事务内**前进；
  · 迁移窗口临时关闭外键（`PRAGMA foreign_keys` 仅在事务外生效，故先关后开事务，
    且设置后复查确认已为 0——连接若已处于事务中该 PRAGMA 会静默无效）；
  · 事务末尾 `PRAGMA foreign_key_check`（该检查不受 foreign_keys 开关影响），
    检出违例即回滚——否则 schema v2 的"建新表→拷数据→删旧表"会撞外键；
  · 结束（含失败路径）恢复 foreign_keys=ON；
  · 按 `user_version` 只应用 version 更高的迁移，重复运行幂等无副作用。

并发语义（多进程启动——主进程 + worker 同跑迁移）：版本判定**不能只依赖**循环外
读取的 `user_version`（发生在写锁之外）——`_apply_one` 在 BEGIN IMMEDIATE 取得
写锁后**重读** `user_version`，若并发进程已应用本迁移则干净跳过（COMMIT + 返回
False），绝不重放 DDL（否则第二条连接撞 "table already exists" 崩溃）。

迁移目录二维分目录 `store/<dialect>/migrations/{docs,semantic}/`（D24——同一迁移号
双方言各一份；语义表 M2-S1 才有迁移文件）。文件名 `NNNN_description.sql`，版本号
全局唯一（docs/semantic 同号视为冲突——user_version 是库级单值）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


class MigrationError(RuntimeError):
    """迁移失败（版本冲突 / SQL 不完整 / 迁移窗口外键开关失败 / foreign_key_check 违例）。"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    domain: str  # docs | semantic
    path: Path


MIGRATIONS_ROOT = Path(__file__).resolve().parent / "migrations"
BUILTIN_DIRS: dict[str, Path] = {
    "docs": MIGRATIONS_ROOT / "docs",
    "semantic": MIGRATIONS_ROOT / "semantic",
}


def discover(dirs: Iterable[Path] | None = None) -> list[Migration]:
    """扫描迁移目录，按版本号升序返回；同号多文件视为冲突。"""
    scan: Iterable[Path] = list(BUILTIN_DIRS.values()) if dirs is None else dirs
    found: dict[int, Migration] = {}
    for d in scan:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.sql")):
            m = _parse(f, domain=d.name)
            if m.version in found:
                raise MigrationError(
                    f"duplicate migration version {m.version:04d}: "
                    f"{found[m.version].path} vs {f}"
                )
            found[m.version] = m
    return [found[v] for v in sorted(found)]


def _parse(path: Path, *, domain: str) -> Migration:
    num, _, name = path.stem.partition("_")
    if not num.isdigit():
        raise MigrationError(f"migration filename must be NNNN_description.sql: {path}")
    return Migration(version=int(num), name=name or path.stem, domain=domain, path=path)


def migrate_db(conn: sqlite3.Connection, dirs: Iterable[Path] | None = None) -> list[int]:
    """应用全部 pending 迁移（version > user_version），返回**本次实际应用**的版本号列表。

    循环外读取的 `user_version` 仅作快速路径过滤；最终判定以 `_apply_one` 在
    BEGIN IMMEDIATE 写锁内的重读为准（并发进程已应用 → 干净跳过、不记入返回值）。
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    applied: list[int] = []
    for m in discover(dirs):
        if m.version <= current:
            continue  # 快速路径：user_version 只前进，已应用的不重放
        if _apply_one(conn, m):
            applied.append(m.version)
    return applied


def _apply_one(conn: sqlite3.Connection, m: Migration) -> bool:
    """单步应用一个迁移；返回是否实际应用（False=写锁内重读发现已被并发进程应用）。"""
    statements = _split_statements(m.path.read_text(encoding="utf-8"), origin=m)
    # 迁移窗口：PRAGMA foreign_keys 必须在事务外设置才生效——设置后复查，
    # 静默无效（连接已在事务中）即视为迁移窗口打开失败
    conn.execute("PRAGMA foreign_keys = OFF")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 0:
        raise MigrationError(
            f"migration {m.version:04d} ({m.name}): PRAGMA foreign_keys=OFF failed "
            "(connection in transaction?)"
        )
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # P2-1：写锁内重读——并发进程可能已推进 user_version；已应用则干净跳过
            locked_version = conn.execute("PRAGMA user_version").fetchone()[0]
            if locked_version >= m.version:
                conn.execute("COMMIT")
                return False
            for stmt in statements:
                conn.execute(stmt)
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise MigrationError(
                    f"migration {m.version:04d} ({m.name}): foreign_key_check "
                    f"violations={violations[:10]} — rolled back"
                )
            conn.execute(f"PRAGMA user_version = {m.version}")
            conn.execute("COMMIT")
            return True
        except BaseException:
            # SQLite 可能已自动回滚（I/O/损坏错误）——ROLLBACK 失败不得覆盖原始异常
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")  # 结束恢复（含失败路径）


def _split_statements(sql: str, *, origin: Migration) -> list[str]:
    """按 sqlite3.complete_statement 切分（正确处理触发体 BEGIN…END; 内的分号）。"""
    out: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines(keepends=True):
        buf.append(line)
        candidate = "".join(buf)
        if sqlite3.complete_statement(candidate):
            if _effective(candidate):
                out.append(candidate.strip())
            buf = []
    tail = "".join(buf).strip()
    if tail and _effective(tail):
        raise MigrationError(f"migration {origin.version:04d}: incomplete SQL tail {tail[:80]!r}")
    return out


def _effective(stmt: str) -> bool:
    """过滤纯注释/空白块。"""
    return any(not ln.strip().startswith("--") for ln in stmt.splitlines())
