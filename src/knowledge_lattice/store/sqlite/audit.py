"""审计月库滚动建表（design §4 注——v0.3 #32 P1-7 + v0.4 #33 P1-4）。

audit_events 属**月库** `audit_YYYYMM.db`（与主库同目录），当月可追加、过月封存只读；
月库建表与 append-only 触发器由连接工厂在滚动时创建（幂等）。写入搬运、封存、
哈希链与保留期删除属 M2（TC-OPS-02），不在本模块。
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

AUDIT_DDL = """\
CREATE TABLE IF NOT EXISTS audit_events (
  id          TEXT PRIMARY KEY,
  org_id      TEXT NOT NULL,
  actor       TEXT NOT NULL,         -- user:<id> / agent:<name>:user:<id>
  action      TEXT NOT NULL,         -- search|upload|grant|revoke|dimension_change|...
  target_type TEXT,
  target_id   TEXT,
  outcome     TEXT NOT NULL,         -- accepted | refused
  request_id  TEXT,
  detail_json TEXT,                  -- 查询词、返回的 chunk_id 列表（查询级审计）
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- append-only（v0.4 直接给出 DDL；SQLite 无 TRUNCATE，DELETE 均触发——#33 P2-10）
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only; retention via monthly file rotation'); END;
"""

_ensured: set[tuple[Path, str]] = set()  # 进程内缓存：同目录同月只 ensure 一次


def ensure_monthly_audit(db_dir: Path, when: datetime | None = None) -> Path:
    """确保当月月库存在且 schema 就绪，返回月库文件路径（幂等）。"""
    month = (when or datetime.now(UTC)).strftime("%Y%m")
    path = db_dir / f"audit_{month}.db"
    key = (path.resolve(), month)
    if key in _ensured:
        return path
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(AUDIT_DDL)  # 全部 IF NOT EXISTS——幂等
    finally:
        conn.close()
    _ensured.add(key)
    return path
