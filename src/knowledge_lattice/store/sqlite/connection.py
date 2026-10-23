"""SQLite 连接工厂——唯一连接入口（design §3；issue #32 P0-B / NFR-4：禁止绕过直连）。

职责：WAL / busy_timeout / foreign_keys=ON（每连接生效 + 显式断言，非 assert——
`python -O` 会剥离）/ synchronous=NORMAL / sqlite-vec 扩展加载（含
`vec_distance_cosine` 可调用断言——known-gaps G-11 收窄动作①）/ 审计月库滚动建表。

全部 PRAGMA 设置后逐项复查（journal_mode 在 `:memory:`/不支持 WAL 的文件系统上会
静默回退——WAL 是 design §2 并发模型的前提，必须显式失败）；任何一步失败都会关闭
已打开的连接再抛 `RuntimeError`（不泄漏连接）。

模块名 connection.py：避免与 `connect()` 函数（design §3 钉死签名）同名互覆盖。
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import sqlite_vec

from .audit import ensure_monthly_audit

BUSY_TIMEOUT_MS = 5000
CONNECT_TIMEOUT_S = 5.0
SYNCHRONOUS_NORMAL = 1
_WAL_RETRY_ATTEMPTS = 5


def connect(path: str | Path) -> sqlite3.Connection:
    """打开主库连接并施加全部连接级纪律（design §3 伪代码的实装）。

    isolation_level=None：事务控制交调用方/迁移框架（BEGIN IMMEDIATE 单步事务）。
    """
    conn = sqlite3.connect(path, timeout=CONNECT_TIMEOUT_S, isolation_level=None)
    try:
        # busy_timeout 最先设置：纯连接级、永不遇库锁；其后需要访问库文件的
        # PRAGMA 在并发启动（另一连接持迁移写锁）时可等待锁释放
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        # journal_mode 先查后设 + 有限重试：模式切换（delete→WAL）需独占访问，
        # 并发首次初始化时另一连接可能正持锁且该路径不调用 busy handler——
        # 直接 SQLITE_BUSY；已是 wal 则跳过设置（查询不遇写锁）
        for attempt in range(_WAL_RETRY_ATTEMPTS):
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if mode == "wal":
                break
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError:
                if attempt == _WAL_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(0.05 * (attempt + 1))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")

        # 不用 assert（python -O 会剥离——#33 P1-1）；逐项复查，静默回退即显式失败
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        if mode != "wal":
            raise RuntimeError(f"journal_mode pragma failed: {mode!r} != 'wal'")
        if conn.execute("PRAGMA busy_timeout").fetchone()[0] != BUSY_TIMEOUT_MS:
            raise RuntimeError("busy_timeout pragma failed")
        if conn.execute("PRAGMA synchronous").fetchone()[0] != SYNCHRONOUS_NORMAL:
            raise RuntimeError("synchronous pragma failed: expected NORMAL (1)")
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("foreign_keys pragma failed")

        _load_vec_extension(conn)
        ensure_monthly_audit(Path(path).parent)
    except BaseException:
        conn.close()  # 失败路径不泄漏连接
        raise
    return conn


def _load_vec_extension(conn: sqlite3.Connection) -> None:
    """加载 sqlite-vec（距离函数作用于 BLOB 列——P0-1）并断言 vec_distance_cosine 可调用。"""
    try:
        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)
    except Exception as exc:
        raise RuntimeError(f"sqlite-vec extension load failed: {exc}") from exc
    try:
        row = conn.execute(
            "SELECT vec_distance_cosine(vec_f32('[0.5]'), vec_f32('[0.5]'))"
        ).fetchone()
    except sqlite3.Error as exc:
        raise RuntimeError(f"sqlite-vec extension not usable: {exc}") from exc
    if row is None or row[0] is None:
        raise RuntimeError("sqlite-vec vec_distance_cosine unavailable")
