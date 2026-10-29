"""审计月库滚动建表与生命周期（design §4 注——v0.3 #32 P1-7 / v0.4 #33 P1-4；
M2.4 m2-2 扩展：哈希链列 + 封存只读 + 保留期整文件删除——TC-OPS-02）。

audit_events 属**月库** `audit_YYYYMM.db`（与主库同目录），当月可追加、过月
封存只读（只读打开 + 文件权限 0444 + sidecar 记末哈希）、到期（默认 12 个月）
整文件删除（含 -wal/-shm 伴生文件）。

哈希链（FR-6）：每行 prev_hash / row_hash（store/audit_chain.py 统一口径）；
**每月首条引用上月末哈希**（向前找最近有行的月份）、**封存记末哈希**
（sidecar `audit_YYYYMM.db.seal.json`：month/last_hash/rows/sealed_at）。
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

AUDIT_DDL = """\
CREATE TABLE IF NOT EXISTS audit_events (
  id          TEXT PRIMARY KEY,
  org_id      TEXT NOT NULL,
  actor       TEXT NOT NULL,         -- user:<id> / agent:<name>:user:<id>
  action      TEXT NOT NULL,         -- search|upload|grant|revoke|dimension_change|...
  target_type TEXT,
  target_id   TEXT,
  outcome     TEXT NOT NULL,         -- accepted | refused
  request_id  TEXT,
  detail_json TEXT,                  -- 查询词、返回的 chunk_id 列表（查询级审计）
  prev_hash   TEXT,                  -- 哈希链：前一条 row_hash（月首条=上月末，FR-6）
  row_hash    TEXT,                  -- 本行哈希（canonical 拼接序见 store/audit_chain.py）
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- append-only（v0.4 直接给出 DDL；SQLite 无 TRUNCATE，DELETE 均触发——#33 P2-10）
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only; retention via monthly file rotation'); END;
"""

_CHAIN_COLUMNS = ("prev_hash", "row_hash")

_ensured: set[tuple[Path, str]] = set()  # 进程内缓存：同目录同月只 ensure 一次


def month_path(db_dir: Path, month: str) -> Path:
    return db_dir / f"audit_{month}.db"


def seal_path(db_dir: Path, month: str) -> Path:
    return db_dir / f"audit_{month}.db.seal.json"


def read_seal(db_dir: Path, month: str) -> dict | None:
    """封存记录（无 → None）：month/last_hash/rows/sealed_at。"""
    p = seal_path(db_dir, month)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def month_of_datetime(when: datetime | None = None) -> str:
    return (when or datetime.now(UTC)).strftime("%Y%m")


def ensure_monthly_audit(db_dir: Path, when: datetime | None = None) -> Path:
    """确保当月月库存在且 schema 就绪（含哈希链列——M0a 存量月库幂等补列），
    返回月库文件路径。

    封存月库（文件无写位）跳过 ensure 直接返回——只读封存态不再触碰
    （幂等 CREATE IF NOT EXISTS 对 0444 文件连接即失败，须前置短路）。
    """
    month = month_of_datetime(when)
    path = month_path(db_dir, month)
    if path.is_file() and not os.access(path, os.W_OK):
        return path  # 已封存只读——不 ensure（TC-OPS-02 封存语义）
    key = (path.resolve(), month)
    if key in _ensured:
        return path
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(AUDIT_DDL)  # 全部 IF NOT EXISTS——幂等
        _ensure_chain_columns(conn)
    finally:
        conn.close()
    _ensured.add(key)
    return path


def _ensure_chain_columns(conn: sqlite3.Connection) -> None:
    """存量月库补哈希链列（幂等——M0a 建的月库无 prev_hash/row_hash）。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(audit_events)")}
    for col in _CHAIN_COLUMNS:
        if col not in cols:
            conn.execute(f"ALTER TABLE audit_events ADD COLUMN {col} TEXT")
    conn.commit()


def open_monthly_ro(path: Path) -> sqlite3.Connection:
    """只读打开月库（封存月库的读取口径——写操作由 SQLite 拒绝 readonly）。"""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def last_row_hash(db_dir: Path, month: str) -> str | None:
    """指定月月库末行 row_hash（**rowid 序末条**——P2-1/R2：链序=插入序，
    audit_events 非 WITHOUT ROWID、隐式 rowid 即插入序；秒级 created_at +
    uuid4 随机 id 的 (created_at,id) 全序与插入序在同秒并列时错位）。
    无行/无库 → None。"""
    path = month_path(db_dir, month)
    if not path.is_file():
        return None
    conn = open_monthly_ro(path)
    try:
        row = conn.execute(
            "SELECT row_hash FROM audit_events"
            " WHERE row_hash IS NOT NULL ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def chain_start_hash(db_dir: Path, month: str) -> str | None:
    """月首条的 prev_hash：**上月末哈希**（FR-6）——上月无行则向前找最近有行
    的月份（链跨空月延续）；全无 → None（创世月）。"""
    from knowledge_lattice.store.audit_chain import prev_month

    m = prev_month(month)
    for _ in range(120):  # 10 年护栏——防脏数据目录死循环
        h = last_row_hash(db_dir, m)
        if h is not None:
            return h
        m = prev_month(m)
    return None


def monthly_rows(path: Path) -> int:
    conn = open_monthly_ro(path)
    try:
        return conn.execute("SELECT count(*) FROM audit_events").fetchone()[0]
    finally:
        conn.close()


def seal_monthly_audit(db_dir: Path, month: str) -> dict | None:
    """封存月库：记末哈希 sidecar + 文件权限 0444（含 -wal/-shm；幂等——
    已封存直接返回既有记录；无月库文件 → None）。

    封存语义（design §4 注）：过月只读——此后任何连接只能只读打开（无写位
    即 open rw 失败），append-only 由「文件权限 + 触发器」双保险。

    崩溃窗防护（P3-5/R2——sidecar **最后**写）：先 chmod 月库 0444 → 再写
    sidecar → chmod sidecar。若在两步间崩溃（半封存态=库 0444 但无 sidecar），
    重放时检测 `库不可写且无 sidecar` → 只读读 rows/last_hash 补写 sidecar
    （幂等早退路径也**重放 chmod**——防「早退检查与首次 chmod 间」的残留窗口）。
    """
    path = month_path(db_dir, month)
    if not path.is_file():
        return None
    sealed = read_seal(db_dir, month)
    if sealed is not None:
        os.chmod(path, 0o444)  # P3-5：早退路径重放 chmod（幂等——防残留可写）
        os.chmod(seal_path(db_dir, month), 0o444)
        return sealed  # 幂等
    if not os.access(path, os.W_OK):
        # 半封存态（P3-5）：库已 chmod、sidecar 未写（上次封存在两步间崩溃）——
        # 只读读取补写 sidecar（不再 checkpoint/写库）
        rows = monthly_rows(path)
        last_hash = last_row_hash(db_dir, month)
        return _write_seal(db_dir, month, rows, last_hash)
    # checkpoint WAL 进主文件（封存后 -wal 不可写，先行归档）并记末哈希
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    rows = monthly_rows(path)
    last_hash = last_row_hash(db_dir, month)
    os.chmod(path, 0o444)  # P3-5：库先只读——sidecar 后写（见 docstring）
    sealed = _write_seal(db_dir, month, rows, last_hash)
    for suffix in ("-wal", "-shm"):
        side = Path(str(path) + suffix)
        if side.exists():
            side.unlink(missing_ok=True)  # checkpoint 后伴生文件可清（目录可写即允许）
    _ensured.discard((path.resolve(), month))
    return sealed


def _write_seal(db_dir: Path, month: str, rows: int, last_hash: str | None) -> dict:
    """写封存记录 sidecar（0444——P3-5：封存动作的最后一步）。"""
    sealed = {
        "month": month,
        "last_hash": last_hash,
        "rows": rows,
        "sealed_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
    }
    sp = seal_path(db_dir, month)
    sp.write_text(json.dumps(sealed, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(sp, 0o444)
    return sealed


def month_shift(month: str, delta: int) -> str:
    """月份平移（store.audit_chain.month_shift 的 re-export——月库包内引用便利）。"""
    from knowledge_lattice.store.audit_chain import month_shift as _shift

    return _shift(month, delta)


def prune_monthly_audit(db_dir: Path, *, keep_months: int, now_month: str) -> list[str]:
    """保留期整文件删除：月早于（当前月 - keep_months）的月库连 sidecar 一起删
    （TC-OPS-02③：保留 12 个月 → 13 个月前的整文件删除；返回被删月份列表）。

    只读文件权限不阻删除（目录可写即可 unlink）——封存只读防的是内容改写。
    """
    cutoff = month_shift(now_month, -keep_months)  # 保留下界（含）：< cutoff 删
    removed: list[str] = []
    for db_file in sorted(db_dir.glob("audit_*.db")):
        stem = db_file.stem
        if not stem.startswith("audit_") or not stem[6:].isdigit():
            continue
        month = stem[6:]
        if month >= cutoff:
            continue
        for suffix in ("", "-wal", "-shm"):
            Path(str(db_file) + suffix).unlink(missing_ok=True)
        seal_path(db_dir, month).unlink(missing_ok=True)
        removed.append(month)
    return removed
