"""TC-OPS-02 审计月库滚动【集成｜M2】（m2-2 B 组——FR-6）。

断言面（design §4 注 + §4 PG 映射）：

- ① 跨月滚动：新月库由连接工厂建表+触发器+链列；旧月库**封存只读**
  （sqlite：末哈希 sidecar + 文件 0444 + 只读打开；pg：分区 sealed 触发器 +
    audit_month_seals 记录——「按既有分区口径」）；
- ② append-only：当月 UPDATE/DELETE 全 ABORT（既有触发器复核）；**已封存**
  月库写入拒绝（sqlite=readonly/权限；pg=sealed EXCEPTION）；
- ③ 保留期 12 个月：13 个月前月库整文件删除 / pg DROP 分区；12 个月内保留；
- ④ 哈希链（FR-6）：每月首条引用上月末哈希、月内逐条 prev=前条 row_hash、
  封存记末哈希（row_hash 可按 canonical 口径重算验证）。

双后端参数化（[sqlite]/[pg]）——sqlite 文件权限形态另有 sqlite-only 用例。
"""

from __future__ import annotations

import json

import pytest

from knowledge_lattice.store.audit_chain import compute_row_hash

OCT = "2026-10-15 10:00:00"
NOV = "2026-11-20 10:00:00"
DEC = "2026-12-05 10:00:00"


def _seed_outbox(backend, matrix, *, event_type="document.upload", count=2,
                 created_at: str = OCT, ship_now: str | None = None) -> None:
    """造一批事件并钉到指定时刻（逐批 ship 防多批 UPDATE 相互覆盖）。"""
    for i in range(count):
        backend.append_outbox(event_type, json.dumps({"n": i, "org_id": "org:tax"}))
    matrix.execute(
        "UPDATE audit_outbox SET created_at = ? WHERE shipped_at IS NULL",
        (created_at,),
    )
    if ship_now is not None:
        backend.ship_outbox(now=ship_now)


def _verify_chain(rows: list[dict], start_prev: str | None) -> None:
    """链完整性：首条 prev=start_prev；逐条 prev=前条 row_hash；row_hash 可重算。"""
    prev = start_prev
    for row in rows:
        assert row["prev_hash"] == prev, f"chain break at {row['id']}"
        assert row["row_hash"] == compute_row_hash(row, prev)
        prev = row["row_hash"]


# ============ ①④ 滚动 + 哈希链 + 封存记末 ============


def test_rolling_chain_and_seal_records_last_hash(matrix, tmp_path) -> None:
    """跨月滚动：月库逐月成形、链跨月衔接（新月首条=上月末哈希）、封存记末。"""
    backend = matrix.make_backend()

    # 10 月：2 行（创世月——prev 为 None）
    _seed_outbox(backend, matrix, count=2, created_at=OCT)
    assert backend.ship_outbox(now="2026-10-16 00:00:00")["shipped"] == 2
    oct_rows = backend.read_monthly_events(when=OCT)
    assert len(oct_rows) == 2
    _verify_chain(oct_rows, None)  # 创世月首条 prev=None（无更早月份）

    # 11 月：3 行——首条 prev=10 月末行 row_hash（FR-6）
    _seed_outbox(backend, matrix, count=3, created_at=NOV)
    assert backend.ship_outbox(now="2026-11-21 00:00:00")["shipped"] == 3
    nov_rows = backend.read_monthly_events(when=NOV)
    assert len(nov_rows) == 3
    _verify_chain(nov_rows, oct_rows[-1]["row_hash"])

    # 封存（12 月时点封存 10/11 月）：记末哈希；幂等重跑
    sealed = backend.seal_audit_months(now=DEC)
    assert sorted(sealed["sealed"]) == ["202610", "202611"]
    assert sealed["skipped_pending"] == []
    again = backend.seal_audit_months(now=DEC)
    assert again["sealed"] == []  # 幂等——已封存不再重复
    last_hashes = {}
    for month, rows in (("202610", oct_rows), ("202611", nov_rows)):
        last_hashes[month] = rows[-1]["row_hash"]
    if matrix.is_sqlite:
        from knowledge_lattice.store.sqlite.audit import read_seal

        db_dir = backend._db_dir()
        for month, rows in (("202610", oct_rows), ("202611", nov_rows)):
            seal = read_seal(db_dir, month)
            assert seal is not None
            assert seal["last_hash"] == rows[-1]["row_hash"]
            assert seal["rows"] == len(rows)
    else:
        for month, rows in (("202610", oct_rows), ("202611", nov_rows)):
            row = matrix.execute(
                "SELECT last_hash, rows FROM audit_month_seals WHERE month = ?",
                (month,),
            ).fetchone()
            assert row is not None
            assert row[0] == rows[-1]["row_hash"]
            assert row[1] == len(rows)

    # 封存后 12 月新月照常滚动（当月不封）——链从 11 月末继续
    _seed_outbox(backend, matrix, count=1, created_at=DEC)
    assert backend.ship_outbox(now="2026-12-06 00:00:00")["shipped"] == 1
    dec_rows = backend.read_monthly_events(when=DEC)
    _verify_chain(dec_rows, nov_rows[-1]["row_hash"])
    assert backend.seal_audit_months(now=DEC)["sealed"] == []  # 当月不封存


# ============ ② append-only：当月 ABORT + 已封存拒写 ============


def test_append_only_aborts_current_and_sealed(matrix, tmp_path) -> None:
    """当月 UPDATE/DELETE 全 ABORT（既有触发器复核）；已封存月库写入拒绝。"""
    backend = matrix.make_backend()
    _seed_outbox(backend, matrix, count=2, created_at=OCT)
    backend.ship_outbox(now="2026-10-16 00:00:00")

    # 当月（10 月仍在当月语义=未封存）UPDATE/DELETE ABORT
    if matrix.is_sqlite:
        import sqlite3

        from knowledge_lattice.store.sqlite.audit import month_path, open_monthly_ro

        mconn = sqlite3.connect(month_path(backend._db_dir(), "202610"))
        for sql in (
            "UPDATE audit_events SET action='x'",
            "DELETE FROM audit_events",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                mconn.execute(sql)
        mconn.close()
        # 封存后：文件无写位（rw 打开失败）+ ro 打开写操作拒绝
        backend.seal_audit_months(now=NOV)
        path = month_path(backend._db_dir(), "202610")
        assert not path.stat().st_mode & 0o222  # 0444——无任何写位
        with pytest.raises(sqlite3.OperationalError):
            sqlite3.connect(path).execute(
                "INSERT INTO audit_events(id, org_id, actor, action, outcome)"
                " VALUES('evt:x', 'o', 'u', 'a', 'accepted')"
            )
        ro = open_monthly_ro(path)
        with pytest.raises(sqlite3.OperationalError):
            ro.execute("UPDATE audit_events SET action='x'")
        ro.close()
    else:
        # 当月/未封存分区：UPDATE/DELETE 触发器 ABORT（父表行级触发器克隆）
        with pytest.raises(matrix.integrity_error, match="append-only"):
            matrix.execute("UPDATE audit_events SET action = 'x'")
        with pytest.raises(matrix.integrity_error, match="append-only"):
            matrix.execute("DELETE FROM audit_events")
        # 封存后：sealed 触发器拦 INSERT/UPDATE/DELETE（owner 亦拦）
        backend.seal_audit_months(now=NOV)
        with pytest.raises(matrix.integrity_error, match="sealed"):
            matrix.execute(
                "INSERT INTO audit_events(id, org_id, actor, action, outcome,"
                " created_at) VALUES('evt:x', 'o', 'u', 'a', 'accepted', %s)",
                ("2026-10-20 00:00:00",),
            )
        with pytest.raises(matrix.integrity_error, match="sealed"):
            matrix.execute("UPDATE audit_events SET action = 'x'")


# ============ ③ 保留期 12 个月：整文件/分区删除 ============


def test_retention_prunes_months_older_than_keep(matrix, tmp_path) -> None:
    """13 个月前月库删除；12 个月内（含边界月）保留。"""
    from knowledge_lattice.store.audit_chain import month_of, month_shift

    backend = matrix.make_backend()
    now_month = "202611"
    old13 = month_shift(now_month, -13)   # 202510 → 删
    edge12 = month_shift(now_month, -12)  # 202511 → 保留（最近 12 个月含当月）
    _seed_outbox(backend, matrix, count=1, created_at="2025-10-01 00:00:00",
                 ship_now="2025-10-02 00:00:00")
    _seed_outbox(backend, matrix, count=1, created_at="2025-11-01 00:00:00",
                 ship_now="2025-11-02 00:00:00")
    _seed_outbox(backend, matrix, count=1, created_at=OCT, ship_now=NOV)
    assert backend.read_monthly_events(when="2025-10-01 00:00:00")
    assert backend.read_monthly_events(when="2025-11-01 00:00:00")

    stats = backend.prune_audit_months(keep_months=12, now="2026-11-30 00:00:00")
    assert stats["pruned"] == [old13]
    assert backend.read_monthly_events(when="2025-10-01 00:00:00") == []  # 已删
    assert backend.read_monthly_events(when="2025-11-01 00:00:00")        # 边界保留
    assert backend.read_monthly_events(when=OCT)                           # 近月保留
    if matrix.is_sqlite:
        from knowledge_lattice.store.sqlite.audit import month_path

        assert not month_path(backend._db_dir(), old13).exists()
        assert month_path(backend._db_dir(), edge12).is_file()
    # 二跑幂等
    assert backend.prune_audit_months(
        keep_months=12, now="2026-11-30 00:00:00"
    )["pruned"] == []


# ============ 封存守卫：有未搬运行的月份不封 ============


def test_seal_skips_month_with_pending_outbox(matrix, tmp_path) -> None:
    """仍有未搬运 outbox 行（事件 created_at 落该月）→ 跳过封存（防「先封存
    后搬运」写入已封存月库的死锁）——搬运后下轮再封。"""
    backend = matrix.make_backend()
    _seed_outbox(backend, matrix, count=1, created_at=OCT)
    # 不 ship——10 月有未搬运行
    stats = backend.seal_audit_months(now=NOV)
    assert stats["sealed"] == [] and stats["skipped_pending"] == ["202610"]
    # 搬运后再封
    backend.ship_outbox(now="2026-11-01 00:00:00")
    stats = backend.seal_audit_months(now=NOV)
    assert stats["sealed"] == ["202610"]
