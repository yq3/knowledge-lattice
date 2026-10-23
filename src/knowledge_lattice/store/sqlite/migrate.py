"""SQLite 迁移框架（design §3 迁移约定——#33 P1-1）。

外键处理约定：
  · 单步事务 BEGIN IMMEDIATE，`user_version` 在**同一事务内**前进；
  · 迁移窗口临时关闭外键（`PRAGMA foreign_keys` 仅在事务外生效，故先关后开事务）；
  · 事务末尾 `PRAGMA foreign_key_check`（该检查不受 foreign_keys 开关影响），
    检出违例即回滚——否则 schema v2 的"建新表→拷数据→删旧表"会撞外键；
  · 结束（含失败路径）恢复 foreign_keys=ON；
  · 按 `user_version` 只应用 version 更高的迁移，重复运行幂等无副作用。

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
    """迁移失败（版本冲突 / SQL 不完整 / foreign_key_check 违例）。"""


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


def migrate(conn: sqlite3.Connection, dirs: Iterable[Path] | None = None) -> list[int]:
    """应用全部 pending 迁移（version > user_version），返回已应用版本号列表（升序）。

    每个迁移单步事务：窗口内关外键 → 执行 SQL → foreign_key_check → user_version
    前进 → COMMIT；任何一步失败整体回滚该迁移并恢复外键。
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    applied: list[int] = []
    for m in discover(dirs):
        if m.version <= current:
            continue  # user_version 只前进：已应用的不重放
        _apply_one(conn, m)
        applied.append(m.version)
    return applied


def _apply_one(conn: sqlite3.Connection, m: Migration) -> None:
    statements = _split_statements(m.path.read_text(encoding="utf-8"), origin=m)
    conn.execute("PRAGMA foreign_keys = OFF")  # 迁移窗口：必须在事务外设置才生效
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
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
        except BaseException:
            conn.execute("ROLLBACK")
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
