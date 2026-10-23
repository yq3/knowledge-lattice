"""审计月库滚动建表（范围 5——连接工厂部分）。

audit_events + append-only 触发器属月库 audit_YYYYMM.db、由连接工厂滚动创建
（design §4 注）；主库 schema v1 不含（TC-SCAF-04 已断言）。TC-OPS-02 的月库
行为断言（封存/哈希链/保留期）属 M2，不在本组。
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def test_connect_rolls_current_monthly_audit(db_path: Path) -> None:
    from knowledge_lattice.store.sqlite import connect

    connect(db_path).close()

    month = datetime.now(UTC).strftime("%Y%m")
    audit_file = db_path.parent / f"audit_{month}.db"
    assert audit_file.is_file()

    ac = sqlite3.connect(audit_file)
    try:
        names = {r[0] for r in ac.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        triggers = {r[0] for r in ac.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert "audit_events" in names
        assert {"audit_no_update", "audit_no_delete"} <= triggers

        ac.execute(
            "INSERT INTO audit_events(id, org_id, actor, action, outcome)"
            " VALUES('evt:1', 'org:tax', 'user:u1', 'search', 'accepted')"
        )
        # append-only：UPDATE / DELETE 均 ABORT
        for sql in (
            "UPDATE audit_events SET action='grant' WHERE id='evt:1'",
            "DELETE FROM audit_events WHERE id='evt:1'",
        ):
            try:
                ac.execute(sql)
            except sqlite3.IntegrityError as e:
                assert "append-only" in str(e)
            else:
                raise AssertionError(f"expected append-only ABORT for: {sql}")
    finally:
        ac.close()


def test_ensure_monthly_audit_idempotent(db_path: Path) -> None:
    from knowledge_lattice.store.sqlite.audit import ensure_monthly_audit

    when = datetime(2026, 4, 15, tzinfo=UTC)
    p1 = ensure_monthly_audit(db_path.parent, when=when)
    p2 = ensure_monthly_audit(db_path.parent, when=when)
    assert p1 == p2 and p1.name == "audit_202604.db"
    assert len(list(db_path.parent.glob("audit_*.db"))) == 1


def test_monthly_audit_rolls_by_month(db_path: Path) -> None:
    from knowledge_lattice.store.sqlite.audit import ensure_monthly_audit

    ensure_monthly_audit(db_path.parent, when=datetime(2026, 10, 31, tzinfo=UTC))
    ensure_monthly_audit(db_path.parent, when=datetime(2026, 11, 1, tzinfo=UTC))
    files = sorted(p.name for p in db_path.parent.glob("audit_*.db"))
    assert files == ["audit_202610.db", "audit_202611.db"]
