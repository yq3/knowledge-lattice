"""TC-SCAF-02 连接 PRAGMA 全集【单测｜M0a】（sqlite-only）。

journal_mode=wal / busy_timeout=5000 / synchronous=NORMAL(1) / foreign_keys=1 逐项一致
（design §3 连接工厂）；sqlite-vec 扩展加载成功——`vec_distance_cosine` 可调用
（known-gaps G-11 收窄动作①：M0a 连接工厂断言补扩展加载可用）。
"""

from __future__ import annotations

import sqlite3


def test_pragma_full_set(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_sqlite_vec_distance_cosine_callable(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT vec_distance_cosine(vec_f32('[1.0, 2.0]'), vec_f32('[1.0, 2.0]'))"
    ).fetchone()
    assert row is not None and row[0] is not None
    assert abs(row[0]) < 1e-6  # 同向量余弦距离为 0


def test_pragmas_hold_on_second_connection(db_path: "object") -> None:
    """每连接生效：新连接再取一次，全集依旧。"""
    from knowledge_lattice.store.sqlite import connect

    c1 = connect(db_path)
    c1.close()
    c2 = connect(db_path)
    try:
        assert conn_pragmas(c2) == ("wal", 5000, 1, 1)
    finally:
        c2.close()


def conn_pragmas(conn: sqlite3.Connection) -> tuple[object, ...]:
    return (
        conn.execute("PRAGMA journal_mode").fetchone()[0],
        conn.execute("PRAGMA busy_timeout").fetchone()[0],
        conn.execute("PRAGMA synchronous").fetchone()[0],
        conn.execute("PRAGMA foreign_keys").fetchone()[0],
    )
