"""SQLite 连接工厂——唯一连接入口（design §3；issue #32 P0-B / NFR-4：禁止绕过直连）。

职责：WAL / busy_timeout / foreign_keys=ON（每连接生效 + 显式断言，非 assert——
`python -O` 会剥离）/ synchronous=NORMAL / sqlite-vec 扩展加载（含
`vec_distance_cosine` 可调用断言——known-gaps G-11 收窄动作①）/ 审计月库滚动建表。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

from .audit import ensure_monthly_audit

BUSY_TIMEOUT_MS = 5000
CONNECT_TIMEOUT_S = 5.0


def connect(path: str | Path) -> sqlite3.Connection:
    """打开主库连接并施加全部连接级纪律（design §3 伪代码的实装）。

    isolation_level=None：事务控制交调用方/迁移框架（BEGIN IMMEDIATE 单步事务）。
    """
    conn = sqlite3.connect(path, timeout=CONNECT_TIMEOUT_S, isolation_level=None)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    # 不用 assert（python -O 会剥离——#33 P1-1）
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("foreign_keys pragma failed")

    _load_vec_extension(conn)
    ensure_monthly_audit(Path(path).parent)
    return conn


def _load_vec_extension(conn: sqlite3.Connection) -> None:
    """加载 sqlite-vec（距离函数作用于 BLOB 列——P0-1）并断言 vec_distance_cosine 可调用。"""
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)
    try:
        row = conn.execute(
            "SELECT vec_distance_cosine(vec_f32('[0.5]'), vec_f32('[0.5]'))"
        ).fetchone()
    except sqlite3.Error as exc:
        raise RuntimeError(f"sqlite-vec extension not usable: {exc}") from exc
    if row is None or row[0] is None:
        raise RuntimeError("sqlite-vec vec_distance_cosine unavailable")
