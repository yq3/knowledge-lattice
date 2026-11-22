"""pg 查询审计独立连接工厂（m3-3 G-28③/P2-1——用户裁定 2026-11-08 m3-3 修复）。

背景：``QueryAuditQueue`` flush 线程与请求线程共享 ``PgBackend._conn`` 单
连接——psycopg 连接无内建跨线程锁，uvicorn 并发形态下 flush 短事务与请求
并发可致协议错乱（m3-2 Tester/Committer P2-1；生产 app 恒 sqlite 无当前
暴露，pg 切换前为前置必修）。

形态：``audit_backend_factory(dsn, schema=...)`` → ``AuditBackendFactory``
（``Callable[[], ContextManager[PgBackend]]``）——**惰性单连接复用**（连接
池单连语义）：首次进入开独立连接（经 store/postgres/connection.connect
工厂纪律：dumper/UTC/版本/pgvector 断言 + 审计分区滚动，search_path 指向
目标 schema），后续进入复用同一连接与 PgBackend；``close()`` 显式收口
（QueryAuditQueue 单消费线程 + flush 串行化下复用安全；不采用「每轮 flush
开新连接」形态——连接工厂的幂等 DDL 与并发写事务存在 catalog 锁死锁面，
且每 5s 一轮的连接开销无谓）。

测试臂（pg 参数化 ``backend`` fixture 的独立 schema）与未来生产 PG 接线
（app 工厂注入）共用本入口——连接形态改动收口 store 层（分层纪律合法面）。
"""

from __future__ import annotations

import contextlib
import threading


class AuditBackendFactory:
    """查询审计独立连接工厂（惰性单连接——与请求连接零共享）。"""

    def __init__(self, dsn: str, *, schema: str | None = None) -> None:
        self._dsn = dsn
        self._search_path = f"{schema},public" if schema else None
        self._lock = threading.Lock()   # 首建防御（flush 串行化外的双保险）
        self._conn = None
        self._backend = None

    def _ensure(self):
        with self._lock:
            if self._conn is None:
                from .connection import connect

                conn = connect(self._dsn, search_path=self._search_path)
                self._conn = conn
                from .backend import PgBackend

                self._backend = PgBackend(conn)
            return self._backend

    @contextlib.contextmanager
    def _ctx(self):
        yield self._ensure()

    def __call__(self):
        """工厂调用面（QueryAuditQueue backend_factory 注入契约）。"""
        return self._ctx()

    def close(self) -> None:
        """显式收口（测试 teardown / app lifespan 关停；未开连接为 no-op）。"""
        with self._lock:
            conn, self._conn, self._backend = self._conn, None, None
        if conn is not None:
            conn.close()


def audit_backend_factory(dsn: str, *, schema: str | None = None):
    """构造查询审计独立连接工厂（QueryAuditQueue backend_factory 注入面）。

    - ``schema``：pg 测试臂的独立 schema（search_path="<schema>,public"——
      与 conftest._pg_db 同款上下文）；生产形态缺省 None（服务端默认
      search_path）；
    - 连接失败在首次进入 with 时抛出——由 QueryAuditQueue flush 的既有
      重试/防毒丸路径处置（回队重试，连续失败丢弃计数）。
    """
    return AuditBackendFactory(dsn, schema=schema)
