"""PostgreSQL 连接工厂——唯一连接入口（design §3；D24/issue #32 P0-B：禁止绕过直连）。

职责（对齐 sqlite/connection.py 的工厂纪律，PG 侧等价断言——TC-SCAF-02 后端行
v1.4 / #42 必修4）：

- psycopg3 连接（`autocommit`——事务控制交调用方/迁移框架，普通 BEGIN/COMMIT
  对应 SQLite BEGIN IMMEDIATE 的 MVCC 等价——§4 PG 映射「BEGIN IMMEDIATE →
  普通事务」）；
- **str 参数以 unknown OID 下发**（StrDumperUnknown）：服务端按上下文推断类型，
  时间戳/JSONB 列直接接受 'YYYY-MM-DD HH:MM:SS' / JSON 文本——与 sqlite 直写
  字符串同形（方言差异收口本包）；
- PG 等价断言（不用 assert——`python -O` 剥离）：server_version ≥ 16（G-6
  口径）+ pgvector 扩展在场且 `<=>` 距离可调用；
- 审计按月分区表滚动（audit.py——§4 PG 映射「审计月库 → 按月分区表」，接口
  不变）；
- 连接池（psycopg_pool.ConnectionPool，TC-SCAF-02 PG 臂断言 min/max 参数）：
  每个池连接经 configure 回调施加同一工厂纪律。

任何一步失败都会关闭已打开的连接再抛 `RuntimeError`（不泄漏连接）。
"""

from __future__ import annotations

import re

import psycopg
from psycopg_pool import ConnectionPool

from .audit import ensure_audit

DSN_ENV = "LATTICE_PG_DSN"
# G-6 收窄口径：公司环境 PG 16 + pgvector 0.8.x（2026-10-22 确认）——工厂按此断言
MIN_SERVER_VERSION_NUM = 160000
DEFAULT_POOL_MIN = 2
DEFAULT_POOL_MAX = 8

_SCHEMA_ITEM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def connect(
    dsn: str, *, search_path: str | None = None, autocommit: bool = True
) -> psycopg.Connection:
    """打开主库连接并施加全部连接级纪律（sqlite connect 的 PG 等价）。

    search_path：逗号分隔的 schema 清单（标识符逐项校验——SET 语句不收参数）；
    缺省沿用服务端默认（通常 public）。
    """
    conn = psycopg.connect(dsn, autocommit=autocommit)
    try:
        setup_connection(conn, search_path=search_path)
        return conn
    except BaseException:
        conn.close()  # 失败路径不泄漏连接
        raise


def setup_connection(
    conn: psycopg.Connection, *, search_path: str | None = None
) -> None:
    """对已打开连接施加工厂纪律（连接池 configure 回调同用此入口）。

    - str → unknown OID dumper（时间戳/JSONB 字符串直写，方言差异收口本包）；
    - **session TimeZone 钉 UTC**（R2 P2-1，用户拍板选项 A）：`CURRENT_TIMESTAMP`
      与 TIMESTAMP 列的比较/DEFAULT 写入统一按 UTC 解释——与 SQLite
      `CURRENT_TIMESTAMP`（恒 UTC）语义对齐；展示分工=后端吐 UTC ISO 8601、
      前端按浏览器时区渲染（FR-8 同构）。未钉时非 UTC 目标环境（如
      Asia/Shanghai）授权过期比较偏移 8h、审计月界 00:00–08:00 写入落不到
      当月分区（丢窗口）；
    - search_path 设置（逐项标识符校验——代码内控值，非数据拼接）；
    - 版本与 pgvector 断言（显式 RuntimeError，非 assert——`python -O` 剥离）；
    - 审计月分区滚动（幂等）。
    """
    from psycopg.types.string import StrDumperUnknown

    conn.adapters.register_dumper(str, StrDumperUnknown)
    conn.execute("SET TIME ZONE 'UTC'")
    # 防御纵深（M0b-3 R2 P3-8）：Literal 转义（单引号加倍）的字面量安全性以
    # standard_conforming_strings=on 为前提（off 时反斜杠在 PG 字符串字面量内
    # 是转义字符——维度 key 等库内数据经 Literal 渲染时反斜杠+引号组合可破坏
    # 字面量边界）。PG 默认 on，但目标环境若被改回 off，工厂显式钉死。
    conn.execute("SET standard_conforming_strings = on")
    if search_path is not None:
        items = [s.strip() for s in search_path.split(",") if s.strip()]
        for item in items:
            if not _SCHEMA_ITEM_RE.match(item):
                raise RuntimeError(f"search_path 非法标识符: {item!r}")
        conn.execute(f"SET search_path TO {', '.join(items)}")
    _assert_server(conn)
    _assert_pgvector(conn)
    ensure_audit(conn)


def connect_pool(
    dsn: str,
    *,
    min_size: int = DEFAULT_POOL_MIN,
    max_size: int = DEFAULT_POOL_MAX,
    search_path: str | None = None,
    name: str = "lattice-pg-pool",
) -> ConnectionPool:
    """连接池（TC-SCAF-02 PG 臂：min/max 参数断言 + 每连接工厂纪律）。

    configure 回调对每个新建连接施加 setup_connection 同款纪律（版本/pgvector
    断言 + 审计分区滚动——与 sqlite「每连接 PRAGMA」同语义）。
    """
    kwargs: dict[str, object] = {"autocommit": True}
    if search_path is not None:
        items = [s.strip() for s in search_path.split(",") if s.strip()]
        for item in items:
            if not _SCHEMA_ITEM_RE.match(item):
                raise RuntimeError(f"search_path 非法标识符: {item!r}")
        # SET 语句不在 connect 参数面内——经 options 传递（服务端启动时生效）
        kwargs["options"] = "-c search_path=" + ",".join(items)

    def _configure(conn: psycopg.Connection) -> None:
        setup_connection(conn)  # options 已设 search_path，此处不再重复 SET

    return ConnectionPool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        name=name,
        kwargs=kwargs,
        configure=_configure,
        open=True,
    )


def _assert_server(conn: psycopg.Connection) -> None:
    """PG 版本断言（G-6：PG 16 起步——迭代扫描/halfvec 依赖 pgvector 0.8 特性面）。"""
    raw = conn.execute("SELECT current_setting('server_version_num')").fetchone()[0]
    if int(raw) < MIN_SERVER_VERSION_NUM:
        raise RuntimeError(
            f"PostgreSQL 版本不满足要求: server_version_num={raw} < {MIN_SERVER_VERSION_NUM}"
            "（G-6 收窄口径：PG 16 + pgvector 0.8.x）"
        )


def _assert_pgvector(conn: psycopg.Connection) -> None:
    """pgvector 扩展在场 + `<=>` 余弦距离可调用（sqlite-vec 断言的 PG 等价）。"""
    row = conn.execute(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()
    if row is None or row[0] is None:
        raise RuntimeError(
            "pgvector 扩展未安装（lattice 库需 CREATE EXTENSION vector——G-6）"
        )
    try:
        dist = conn.execute(
            "SELECT '[1.0, 2.0]'::vector <=> '[1.0, 2.0]'::vector"
        ).fetchone()
    except psycopg.Error as exc:
        raise RuntimeError(f"pgvector <=> 距离算子不可用: {exc}") from exc
    if dist is None or dist[0] is None or abs(float(dist[0])) > 1e-6:
        raise RuntimeError(f"pgvector <=> 距离断言失败: {dist!r}")
