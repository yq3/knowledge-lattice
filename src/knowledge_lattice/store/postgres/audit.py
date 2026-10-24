"""审计按月分区表滚动（design §4 PG 映射——v0.3 #32 P1-7 / v0.4 #33 P1-4 的 PG 等价）。

SQLite 后端的审计**月库** `audit_YYYYMM.db`（连接工厂滚动建表 + append-only 触发器）
在 PG 上映射为**按月分区表**（§2/§4 PG 映射：连接工厂滚动建分区，接口不变）：

- `audit_events` 为 `PARTITION BY RANGE (created_at)` 分区表，落在当前 search_path
  首 schema（与 sqlite「月库文件与主库同目录」对应）；
- `audit_events_YYYYMM` 分区由连接工厂/`roll_monthly` 滚动创建（幂等）——当月
  可追加、过月封存只读的保留策略属 M2（TC-OPS-02）；
- append-only 触发器建在分区父表上（行级触发器自动克隆到各分区，含后续新建
  分区）——RAISE EXCEPTION 消息与 sqlite 版逐字同源；
- 方言差异注记：分区表唯一约束必须包含分区键 → PRIMARY KEY (id, created_at)
  （sqlite 月库为 id 单列——§4 PG 映射允许的等价偏差，语义不受影响：id 仍全局
  唯一由写入侧 ULID 保证）。
"""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg

AUDIT_PARENT_DDL = """\
CREATE TABLE IF NOT EXISTS audit_events (
  id          TEXT NOT NULL,
  org_id      TEXT NOT NULL,
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,
  target_type TEXT,
  target_id   TEXT,
  outcome     TEXT NOT NULL,
  request_id  TEXT,
  detail_json TEXT,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at)
"""

APPEND_ONLY_FN_DDL = """\
CREATE OR REPLACE FUNCTION lattice_audit_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only';
END
$$
"""

APPEND_ONLY_DELETE_FN_DDL = """\
CREATE OR REPLACE FUNCTION lattice_audit_append_only_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only; retention via monthly file rotation';
END
$$
"""

APPEND_ONLY_TRIGGERS_DDL = """\
DROP TRIGGER IF EXISTS audit_no_update ON audit_events;
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION lattice_audit_append_only();
DROP TRIGGER IF EXISTS audit_no_delete ON audit_events;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION lattice_audit_append_only_delete()
"""


def month_bounds(month: str) -> tuple[str, str]:
    """'YYYYMM' → [当月首日 0 点, 次月首日 0 点)（RANGE 分区边界）。"""
    year, mon = int(month[:4]), int(month[4:6])
    start = f"{year:04d}-{mon:02d}-01"
    ny, nm = (year + 1, 1) if mon == 12 else (year, mon + 1)
    end = f"{ny:04d}-{nm:02d}-01"
    return start, end


def partition_name(month: str) -> str:
    return f"audit_events_{month}"


def ensure_month_partition(conn: psycopg.Connection, when: datetime | None = None) -> str:
    """确保指定月的分区存在（幂等），返回分区名——月库文件的 PG 等价滚动动作。"""
    month = (when or datetime.now(UTC)).strftime("%Y%m")
    name = partition_name(month)
    start, end = month_bounds(month)
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF audit_events"
        f" FOR VALUES FROM ('{start}') TO ('{end}')"
    )
    return name


def ensure_audit(conn: psycopg.Connection, when: datetime | None = None) -> None:
    """确保分区父表 + append-only 触发器 + 当月分区就绪（连接工厂滚动入口，幂等）。"""
    conn.execute(AUDIT_PARENT_DDL)
    conn.execute(APPEND_ONLY_FN_DDL)
    conn.execute(APPEND_ONLY_DELETE_FN_DDL)
    conn.execute(APPEND_ONLY_TRIGGERS_DDL)
    ensure_month_partition(conn, when)
