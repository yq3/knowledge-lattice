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
  prev_hash   TEXT,             -- 哈希链：前一条 row_hash（月首条=上月末，FR-6）
  row_hash    TEXT,             -- 本行哈希（canonical 拼接见 store/audit_chain.py）
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

# R2 P2-4（用户拍板选项 A）：PG TRUNCATE 不触发行级 UPDATE/DELETE 触发器
# （SQLite 无 TRUNCATE、DELETE 均被拦——无此缺口），须 statement 级 BEFORE
# TRUNCATE 触发器补齐 append-only 等价（#33 P2-10 / FR-6），消息同源。
# 注：父表上的 TRUNCATE 触发器只拦「TRUNCATE 父表」、既不克隆到分区也不拦
# 「直接 TRUNCATE 分区」（PG 16 实测）——ensure_month_partition 对每个分区
# 显式落同款触发器补齐分区直 TRUNCATE 形态。
APPEND_ONLY_TRUNCATE_FN_DDL = """\
CREATE OR REPLACE FUNCTION lattice_audit_append_only_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only; TRUNCATE is forbidden';
  RETURN NULL;
END
$$
"""

APPEND_ONLY_TRUNCATE_TRIGGER_DDL = """\
DROP TRIGGER IF EXISTS audit_no_truncate ON {target};
CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON {target}
  FOR EACH STATEMENT EXECUTE FUNCTION lattice_audit_append_only_truncate()
"""

# ---- 封存（M2.4 m2-2——TC-OPS-02①：过月分区只读） ----
#
# PG 的「只读打开 + 文件权限」等价物 = 分区上落 sealed 触发器（BEFORE
# INSERT OR UPDATE OR DELETE——owner 亦拦，比 REVOKE 更强）+ REVOKE PUBLIC
# 写权限（纵深）。封存记录入 audit_month_seals（month PK / last_hash /
# rows / sealed_at——「封存记末哈希」，FR-6）。
SEALED_FN_DDL = """\
CREATE OR REPLACE FUNCTION lattice_audit_month_sealed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events month % is sealed (read-only)', TG_TABLE_NAME;
END
$$
"""

SEALED_TRIGGER_DDL = """\
DROP TRIGGER IF EXISTS audit_month_sealed ON {target};
CREATE TRIGGER audit_month_sealed BEFORE INSERT OR UPDATE OR DELETE ON {target}
  FOR EACH ROW EXECUTE FUNCTION lattice_audit_month_sealed()
"""

SEALS_TABLE_DDL = """\
CREATE TABLE IF NOT EXISTS audit_month_seals (
  month     TEXT PRIMARY KEY,
  last_hash TEXT,
  rows      INTEGER NOT NULL,
  sealed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

# ---- 插入序列（P2-1/R2：链序=插入序） ----
#
# (created_at,id) 全序在「同秒（CURRENT_TIMESTAMP 秒级依赖 / 测试造数）+ uuid4
# 随机 id」下与插入序错位；µs 方案对「同事务批量（transaction_timestamp 恒定）」
# 无效——**单调序列列**是唯一可靠插入序。幂等 ensure（非迁移——月库表不在主库
# 迁移域）：
#   · CREATE SEQUENCE IF NOT EXISTS（schema 内，各测试 schema 独立）；
#   · ADD COLUMN IF NOT EXISTS seq BIGINT DEFAULT nextval(...)——分区父表 ALTER
#     自动传播到全部分区；非常量 DEFAULT 不 rewrite、**既有行保持 NULL 不回填**
#     （append-only BEFORE UPDATE 触发器拦 UPDATE；NULL 行在读序中 NULLS FIRST
#     段按 (created_at,id) 兜底——R1 期存量近似插入序，衔接无洞）。
SEQ_DDL = """\
CREATE SEQUENCE IF NOT EXISTS audit_events_seq
"""

SEQ_COLUMN_DDL = """\
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS seq BIGINT
  DEFAULT nextval('audit_events_seq')
"""


def month_bounds(month: str) -> tuple[str, str]:
    """'YYYYMM' → [当月首日 0 点, 次月首日 0 点)（RANGE 分区边界，UTC 月界——
    session TimeZone 已由连接工厂钉 UTC，P2-1）。"""
    year, mon = int(month[:4]), int(month[4:6])
    start = f"{year:04d}-{mon:02d}-01"
    ny, nm = (year + 1, 1) if mon == 12 else (year, mon + 1)
    end = f"{ny:04d}-{nm:02d}-01"
    return start, end


def partition_name(month: str) -> str:
    return f"audit_events_{month}"


def ensure_month_partition(conn: psycopg.Connection, when: datetime | None = None) -> str:
    """确保指定月的分区存在（幂等），返回分区名——月库文件的 PG 等价滚动动作。

    分区自身同步落 audit_no_truncate 触发器（幂等 DROP/CREATE）：分区是独立
    表，父表 statement 级触发器覆盖不到「直接 TRUNCATE 分区」形态（P2-4）。
    """
    month = (when or datetime.now(UTC)).strftime("%Y%m")
    name = partition_name(month)
    start, end = month_bounds(month)
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF audit_events"
        f" FOR VALUES FROM ('{start}') TO ('{end}')"
    )
    conn.execute(APPEND_ONLY_TRUNCATE_TRIGGER_DDL.format(target=name))
    return name


def ensure_audit(conn: psycopg.Connection, when: datetime | None = None) -> None:
    """确保分区父表 + append-only 触发器（行级 + TRUNCATE statement 级）+
    插入序列（P2-1/R2——链序=插入序）+ 当月分区就绪（连接工厂滚动入口，幂等）。"""
    conn.execute(AUDIT_PARENT_DDL)
    _ensure_chain_columns(conn)
    conn.execute(APPEND_ONLY_FN_DDL)
    conn.execute(APPEND_ONLY_DELETE_FN_DDL)
    conn.execute(APPEND_ONLY_TRUNCATE_FN_DDL)
    conn.execute(APPEND_ONLY_TRIGGERS_DDL)
    conn.execute(APPEND_ONLY_TRUNCATE_TRIGGER_DDL.format(target="audit_events"))
    conn.execute(SEQ_DDL)
    conn.execute(SEQ_COLUMN_DDL)
    ensure_month_partition(conn, when)


def _ensure_chain_columns(conn: psycopg.Connection) -> None:
    """存量父表补哈希链列（幂等——ALTER 自动传播到全部既有分区）。"""
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_schema = current_schema() AND table_name = 'audit_events'"
        "   AND column_name IN ('prev_hash', 'row_hash')"
    ).fetchall()
    have = {r[0] for r in rows}
    for col in ("prev_hash", "row_hash"):
        if col not in have:
            conn.execute(f"ALTER TABLE audit_events ADD COLUMN {col} TEXT")


def last_row_hash(conn: psycopg.Connection, month: str) -> str | None:
    """指定月分区末行 row_hash（**插入序末条**——seq 单调；无行 → None）。"""
    start, end = month_bounds(month)
    row = conn.execute(
        "SELECT row_hash FROM audit_events"
        " WHERE created_at >= %(s)s AND created_at < %(e)s"
        "   AND row_hash IS NOT NULL"
        f" ORDER BY (seq IS NULL) ASC, seq DESC, created_at DESC, id DESC LIMIT 1",
        {"s": start, "e": end},
    ).fetchone()
    return row[0] if row else None


def month_row_count(conn: psycopg.Connection, month: str) -> int:
    start, end = month_bounds(month)
    return conn.execute(
        "SELECT count(*) FROM audit_events"
        " WHERE created_at >= %(s)s AND created_at < %(e)s",
        {"s": start, "e": end},
    ).fetchone()[0]


def seal_month_partition(conn: psycopg.Connection, month: str) -> dict:
    """封存分区（幂等）：sealed 触发器 + REVOKE 写权限 + audit_month_seals
    记录（末哈希——FR-6「封存记末哈希」）。"""
    conn.execute(SEALED_FN_DDL)
    conn.execute(SEALED_TRIGGER_DDL.format(target=partition_name(month)))
    conn.execute(
        f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON {partition_name(month)} FROM PUBLIC"
    )
    conn.execute(SEALS_TABLE_DDL)
    conn.execute(
        "INSERT INTO audit_month_seals(month, last_hash, rows)"
        " VALUES(%(m)s, %(h)s, %(n)s)"
        " ON CONFLICT (month) DO NOTHING",
        {"m": month, "h": last_row_hash(conn, month),
         "n": month_row_count(conn, month)},
    )
    return {"month": month, "last_hash": last_row_hash(conn, month)}
