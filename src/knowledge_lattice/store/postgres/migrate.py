"""PostgreSQL 迁移框架（design §3 迁移约定的 PG 等价——M0b-1，TC-SCAF-03 后端行 v1.4）。

与 sqlite/migrate.py 的语义对照（§4 PG 映射）：

- `user_version` → **`schema_migrations` 表**（version/name/domain/applied_at），
  版本号只前进、重复运行幂等（已应用版本不重放）；**乱序防护（R2 P2-3）**：
  未应用且 version ≤ MAX(applied) 水位的迁移（如已应用 0003 后补入 0002）
  直接 `MigrationError` fail-fast——绝不乱序应用（SQLite `user_version` 单调
  语义等价；锁内复核同款校验防并发推进后的竞态）；
- `BEGIN IMMEDIATE` → 普通事务 + **事务级 advisory lock**（`pg_advisory_xact_lock`）
  序列化并发迁移——取锁后在锁内重读已应用版本，并发连接已应用同一迁移时干净
  跳过（绝不重放 DDL 撞 "already exists"）；
- 迁移窗口 `PRAGMA foreign_keys=OFF` + `foreign_key_check` → **PG 原生约束即时
  校验**（DDL 可事务化）：迁移事务内任何违例语句即失败 → 整事务回滚（含已执行
  DDL 与 schema_migrations 写入），库内状态与迁移前一致——外键无需（也不允许）
  窗口性关闭；
- 迁移目录二维分目录 `store/postgres/migrations/{docs,semantic}/`（同一迁移号
  双方言各一份——§3 边界规则 3；语义表 M2-S1 才有迁移文件）；
- 语句切分：dollar-quoting（$$ / $tag$）感知——plpgsql 触发器体内的分号不切断。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import psycopg


class MigrationError(RuntimeError):
    """迁移失败（版本冲突 / SQL 不完整 / 违例回滚）。"""


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

# 事务级 advisory lock 键（固定常量——所有连接/库共用，序列化并发迁移）
MIGRATION_LOCK_KEY = 0x1A77_1CE  # 'lattice-migrations' 语义的稳定位型


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


def migrate_db(conn: psycopg.Connection, dirs: Iterable[Path] | None = None) -> list[int]:
    """应用全部 pending 迁移，返回**本次实际应用**的版本号列表（幂等：已应用不重放）。

    版本只前进（R2 P2-3）：未应用且 ≤ MAX(applied) 水位 → MigrationError
    fail-fast（乱序补入小编号迁移属部署错误，绝不静默乱序应用）。
    """
    _ensure_schema_migrations(conn)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    watermark = max(applied, default=0)
    applied_now: list[int] = []
    for m in discover(dirs):
        if m.version in applied:
            continue  # 快速路径：版本只前进，已应用的不重放
        _assert_forward_only(m, watermark, applied)
        if _apply_one(conn, m):
            applied_now.append(m.version)
            applied.add(m.version)
            watermark = m.version
    return applied_now


def _assert_forward_only(m: Migration, watermark: int, applied: set[int]) -> None:
    """未应用且 ≤ 水位 → 乱序/回补迁移，fail-fast（user_version 单调语义等价）。"""
    if m.version <= watermark and m.version not in applied:
        raise MigrationError(
            f"migration {m.version:04d} ({m.name}) 未应用且 ≤ 已应用水位 "
            f"{watermark:04d}——版本只前进（乱序补入小编号迁移拒绝执行；"
            "SQLite user_version 单调语义等价，R2 P2-3）"
        )


def applied_versions(conn: psycopg.Connection) -> list[int]:
    """已应用版本清单（升序）——schema_migrations 的查询面。"""
    _ensure_schema_migrations(conn)
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return [r[0] for r in rows]


def _ensure_schema_migrations(conn: psycopg.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  version    INTEGER PRIMARY KEY,"
        "  name       TEXT NOT NULL,"
        "  domain     TEXT NOT NULL,"
        "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )


def _apply_one(conn: psycopg.Connection, m: Migration) -> bool:
    """单步应用一个迁移；返回是否实际应用（False=advisory lock 内重读发现已被
    并发连接应用——干净跳过，绝不重放 DDL）。"""
    statements = _split_statements(m.path.read_text(encoding="utf-8"), origin=m)
    conn.execute("BEGIN")
    try:
        # 并发序列化（BEGIN IMMEDIATE 的 MVCC 等价）：事务级 advisory lock +
        # 锁内重读已应用集合与水位（并发推进后同款校验——R2 P2-3 锁内复核）
        conn.execute("SELECT pg_advisory_xact_lock(%(k)s)", {"k": MIGRATION_LOCK_KEY})
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        locked_applied = {r[0] for r in rows}
        if m.version in locked_applied:
            conn.execute("COMMIT")
            return False
        _assert_forward_only(m, max(locked_applied, default=0), locked_applied)
        for stmt in statements:
            conn.execute(stmt)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, domain)"
            " VALUES (%(v)s, %(n)s, %(d)s)",
            {"v": m.version, "n": m.name, "d": m.domain},
        )
        conn.execute("COMMIT")
        return True
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except psycopg.Error:
            pass  # 连接/事务已坏时保留原始异常链
        raise


# ============ 语句切分（dollar-quoting / 引号 / 注释感知） ============

_DOLLAR_TAG_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def _split_statements(sql: str, *, origin: Migration) -> list[str]:
    """按顶层分号切分；跳过单引号串、dollar-quoting 块（plpgsql 体）与注释。

    末尾不完整语句（分号缺失）视为迁移文件错误——fail fast。
    """
    out: list[str] = []
    start = 0  # 当前语句起点（切片式——不逐字符缓冲）
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":  # 单引号串（'' 转义）
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        m = _DOLLAR_TAG_RE.match(sql, i)
        if m:  # dollar-quoting 块（$tag$ … $tag$，plpgsql 函数体）
            tag = m.group(0)
            end = sql.find(tag, i + len(tag))
            if end == -1:
                raise MigrationError(
                    f"migration {origin.version:04d}: 未闭合的 dollar-quoting {tag}"
                )
            i = end + len(tag)
            continue
        if ch == "-" and sql[i : i + 2] == "--":  # 行注释
            nl = sql.find("\n", i)
            i = n if nl == -1 else nl
            continue
        if ch == "/" and sql[i : i + 2] == "/*":  # 块注释
            close = sql.find("*/", i + 2)
            if close == -1:
                raise MigrationError(f"migration {origin.version:04d}: 未闭合的块注释")
            i = close + 2
            continue
        if ch == ";":
            candidate = sql[start:i].strip()
            if _effective(candidate):
                out.append(candidate)
            i += 1
            start = i
            continue
        i += 1
    tail = sql[start:].strip()
    if tail and _effective(tail):
        raise MigrationError(
            f"migration {origin.version:04d}: incomplete SQL tail {tail[:80]!r}"
        )
    return out


def _effective(stmt: str) -> bool:
    """过滤纯注释/空白块。"""
    return any(not ln.strip().startswith("--") for ln in stmt.splitlines())
