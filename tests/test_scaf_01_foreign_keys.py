"""TC-SCAF-01 foreign_keys 每连接生效 + 孤儿行拒绝【单测｜M0a】（both——M0a 仅 SQLite）。

- ① PRAGMA foreign_keys 返回 1；
- ② user_dimension_grants 插孤儿行（引用不存在 user）抛 sqlite3.IntegrityError；
- ③ document_dimensions 插孤儿行（引用不存在 doc）抛 sqlite3.IntegrityError；
- ④ 工厂对 pragma 失败显式 raise RuntimeError（非 assert——`python -O` 剥离，design §3）。
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from helpers import seed_dimension, seed_dim_value, seed_org


def test_foreign_keys_enabled_per_connection(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_orphan_user_dimension_grant_rejected(conn: sqlite3.Connection) -> None:
    seed_org(conn)
    dim_id = seed_dimension(conn)
    val_id = seed_dim_value(conn, dim_id)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute(
            "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id)"
            " VALUES('ghost-user', ?, ?)",
            (dim_id, val_id),
        )


def test_orphan_document_dimension_rejected(conn: sqlite3.Connection) -> None:
    seed_org(conn)
    dim_id = seed_dimension(conn)
    val_id = seed_dim_value(conn, dim_id)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute(
            "INSERT INTO document_dimensions(doc_id, dimension_id, value_id)"
            " VALUES('ghost-doc', ?, ?)",
            (dim_id, val_id),
        )


def test_pragma_failure_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch, db_path: "object"
) -> None:
    """查询 PRAGMA foreign_keys 返回 0 → 工厂显式 RuntimeError（而非 assert 语句）。"""
    from knowledge_lattice.store.sqlite import connect

    real_connect = sqlite3.connect

    class _Row:
        def fetchone(self) -> tuple[int]:
            return (0,)

    def fake_sqlite_connect(*args: object, **kwargs: object) -> object:
        inner = real_connect(*args, **kwargs)  # type: ignore[arg-type]
        try:
            wrapper = MagicMock(wraps=inner)

            def execute(sql: str, *rest: object) -> object:
                if sql.strip().upper() == "PRAGMA FOREIGN_KEYS":
                    return _Row()  # 模拟 pragma 未生效
                return inner.execute(sql, *rest)  # type: ignore[arg-type]

            wrapper.execute = execute  # type: ignore[method-assign]
            return wrapper
        except BaseException:
            inner.close()  # P3-22：包装失败不泄漏真实连接
            raise

    monkeypatch.setattr(sqlite3, "connect", fake_sqlite_connect)
    with pytest.raises(RuntimeError, match="foreign_keys"):
        connect(db_path)
