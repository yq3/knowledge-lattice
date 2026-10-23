"""线程本地 backend 代理（design §2 线程模型：每线程一连接）。

FastAPI/anyio 线程池与后台任务会在不同线程使用 backend——SQLite 连接
check_same_thread 纪律下，各线程经**连接工厂**自取连接（WAL 多连接读写兼容，
NFR-9）。代理按线程惰性建 SqliteBackend 并透传；迁移在引导连接上先跑一次
（create_app 职责）。
"""

from __future__ import annotations

import threading
from pathlib import Path

from knowledge_lattice.store.sqlite.backend import SqliteBackend
from knowledge_lattice.store.sqlite.connection import connect


class ThreadLocalBackend:
    """`backend.foo(...)` → 当前线程的 SqliteBackend.foo(...)（透传代理）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._local = threading.local()

    def _current(self) -> SqliteBackend:
        backend = getattr(self._local, "backend", None)
        if backend is None:
            backend = SqliteBackend(connect(self._db_path))
            self._local.backend = backend
        return backend

    def __getattr__(self, name: str):
        return getattr(self._current(), name)
