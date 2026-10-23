"""TC-SCAF 组共享 fixtures（M0a-1）。

`conn` fixture：全新 lattice.db → 连接工厂 → 迁移到 schema v1——与 TC-SCAF-01~05
的「前置：经 store 连接工厂取连接，schema v1 已落」一致。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "lattice.db"


@pytest.fixture()
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    from knowledge_lattice.store.sqlite import connect, migrate

    c = connect(db_path)
    migrate(c)
    yield c
    c.close()
