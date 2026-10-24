"""TC-SCAF-01 foreign_keys 每连接生效 + 孤儿行拒绝【单测｜M0a→M0b 双后端】。

- ① PRAGMA foreign_keys 返回 1（sqlite 臂；PG 无 PRAGMA 机制——原生外键常开，
  等价断言即 ②③ 的外键违例本身）；
- ② user_dimension_grants 插孤儿行（引用不存在 user）被拒：sqlite =
  `sqlite3.IntegrityError`（"FOREIGN KEY"）；pg = `psycopg ForeignKeyViolation`
  （**sqlstate 23503**——后端行 v1.4 / #42 必修4：psycopg 外键错误码断言，语义不变）；
- ③ document_dimensions 插孤儿行（引用不存在 doc）同上；
- ④ 工厂对 pragma 失败显式 raise RuntimeError（sqlite-only——非 assert，
  `python -O` 剥离，design §3）。
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from helpers import seed_dimension, seed_dim_value, seed_org


def test_foreign_keys_enabled_per_connection(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_orphan_user_dimension_grant_rejected(backend) -> None:
    seed_org(backend)
    dim_id = seed_dimension(backend)
    val_id = seed_dim_value(backend, dim_id)
    with pytest.raises(backend.fk_error, match=backend.fk_marker) as excinfo:
        backend.execute(
            "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id)"
            " VALUES('ghost-user', ?, ?)",
            (dim_id, val_id),
        )
    if backend.is_pg:
        # TC-SCAF-01 后端行 v1.4：psycopg 外键错误码逐值断言（23503）
        assert excinfo.value.sqlstate == backend.fk_sqlstate


def test_orphan_document_dimension_rejected(backend) -> None:
    seed_org(backend)
    dim_id = seed_dimension(backend)
    val_id = seed_dim_value(backend, dim_id)
    with pytest.raises(backend.fk_error, match=backend.fk_marker) as excinfo:
        backend.execute(
            "INSERT INTO document_dimensions(doc_id, dimension_id, value_id)"
            " VALUES('ghost-doc', ?, ?)",
            (dim_id, val_id),
        )
    if backend.is_pg:
        assert excinfo.value.sqlstate == backend.fk_sqlstate


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
