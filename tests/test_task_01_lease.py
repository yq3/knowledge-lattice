"""TC-TASK-01 心跳与租约【单测｜M2】+ TC-E2E-03 机制半句（M2 前：造数过期重认领）。

- 认领：pending → leased（lease_owner/lease_until/heartbeat_at 落位）；
- 心跳：worker_heartbeat_s 周期刷 heartbeat_at + lease_until；失守（非 owner/
  终态/被重认领）→ False；
- 租约 60s 口径：lease_until = now + lease_s（字符串时间线推进断言）；
- 过期重认领（TC-E2E-03 机制）：造数 lease_until 过期的 running 任务 → 被重认领、
  attempts 递增、原持有者心跳 False（不双跑）；
- **真实并发窗口**（承接遗留 1）：两执行器 barrier 对齐并发认领同任务——恰好
  一人得手（多轮强化）；类型过滤（maintenance 不被 ingest 认领误领）。

双后端参数化（[sqlite]/[pg]——claim SQL 方言分派：单语句子查询 / SKIP LOCKED；
并发臂连接形态：sqlite=ThreadLocalBackend 每线程一连接 / pg=单连接线程安全）。
"""

from __future__ import annotations

import threading

import pytest
from helpers import NOW_TS

CLAIM_LEASE_S = 60.0


def _ts(v) -> str:
    """时间戳断言归一：sqlite 侧为字符串、pg 侧 psycopg 返回 datetime——统一
    到 `YYYY-MM-DD HH:MM:SS` 文本比较。"""
    if isinstance(v, str):
        return v
    return v.strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture()
def bk(backend):
    """真实 StorageBackend（本线程——单线程用例直接用）。"""
    return backend.make_backend()


@pytest.fixture()
def claim_factory(backend, tmp_path):
    """并发臂的 backend 工厂：sqlite 每线程一连接（check_same_thread 纪律）、
    pg **每线程独立连接**（P3-N2/P3-c——psycopg 连接非线程安全且共享单连接
    时两认领线程被驱动串行化，SKIP LOCKED 的真实并发窗口从未被触达；独立
    连接 + 同 schema + 工厂纪律（setup_connection 幂等）恢复真并发保真度）。"""
    if backend.is_sqlite:
        from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

        proxy = ThreadLocalBackend(tmp_path / "lattice.db")
        return lambda: proxy

    import psycopg

    from knowledge_lattice.store.postgres.backend import PgBackend

    dsn, schema = backend.dsn, backend.schema

    def _new_conn_backend():
        # 最小初始化：只 SET search_path——**不跑 setup_connection**（其内
        # ensure_audit 是 DDL（CREATE/DROP TRIGGER），两线程同时建连接会并发
        # 撞 pg_class/pg_trigger 目录行（InternalError: tuple concurrently
        # updated）；审计表已由 fixture 主连接 ensure 就绪，并发臂纯 DML）
        conn = psycopg.connect(dsn, autocommit=True)
        try:
            conn.execute(f'SET search_path TO "{schema}", public')
            conn.execute("SET TIME ZONE 'UTC'")
        except BaseException:
            conn.close()
            raise
        return PgBackend(conn)

    return _new_conn_backend


def _mk_task(bk, *, task_type: str = "ingest") -> str:
    return bk.create_task(None, task_type=task_type)


def test_claim_pending_sets_lease_fields(bk, backend) -> None:
    task_id = _mk_task(bk)
    task = bk.claim_next_task("wk-A", lease_s=CLAIM_LEASE_S, now=NOW_TS)
    assert task is not None and task["id"] == task_id
    assert task["status"] == "leased"
    assert task["lease_owner"] == "wk-A"
    assert _ts(task["lease_until"]) == "2026-06-01 12:01:00"  # now + 60s（租约 60s 口径）
    assert _ts(task["heartbeat_at"]) == NOW_TS
    # 无第二个可认领任务
    assert bk.claim_next_task("wk-B", lease_s=CLAIM_LEASE_S, now=NOW_TS) is None


def test_heartbeat_refresh_and_owner_guard(bk) -> None:
    task_id = _mk_task(bk)
    bk.claim_next_task("wk-A", lease_s=CLAIM_LEASE_S, now=NOW_TS)
    ok = bk.heartbeat_task(
        task_id, "wk-A", lease_s=CLAIM_LEASE_S, now="2026-06-01 12:00:05"
    )
    assert ok is True
    row = bk.get_task(task_id)
    assert _ts(row["heartbeat_at"]) == "2026-06-01 12:00:05"  # 每 5s 更新 heartbeat_at
    assert _ts(row["lease_until"]) == "2026-06-01 12:01:05"
    # 非 owner / 终态 → False
    assert bk.heartbeat_task(task_id, "wk-B", lease_s=CLAIM_LEASE_S) is False
    bk.update_task(task_id, status="failed", error="x")
    assert bk.heartbeat_task(task_id, "wk-A", lease_s=CLAIM_LEASE_S) is False


def test_expired_lease_reclaimable_no_double_run(bk) -> None:
    """TC-E2E-03 机制半句：租约过期任务可被重认领；原持有者心跳 False（不双跑）。"""
    task_id = _mk_task(bk)
    first = bk.claim_next_task("wk-A", lease_s=CLAIM_LEASE_S, now=NOW_TS)
    assert first is not None
    bk.update_task(task_id, status="running")  # M2.1 R2 口径：attempts 随 claim 认领递增（running 不再重复计）

    # 未过期：他人不可抢
    assert bk.claim_next_task(
        "wk-B", lease_s=CLAIM_LEASE_S, now="2026-06-01 12:00:59"
    ) is None
    # 过期（> 60s）：重认领成功（crash 后任务不丢；attempts 已随本次 claim 递增）
    second = bk.claim_next_task(
        "wk-B", lease_s=CLAIM_LEASE_S, now="2026-06-01 13:01:00"
    )
    assert second is not None and second["id"] == task_id
    assert second["lease_owner"] == "wk-B"
    bk.update_task(task_id, status="running")
    assert bk.get_task(task_id)["attempts"] == 2  # 重认领续跑 attempts 递增
    # 原持有者失守——阶段边界探测据此停止（不双跑）
    assert bk.heartbeat_task(
        task_id, "wk-A", lease_s=CLAIM_LEASE_S, now="2026-06-01 13:01:01"
    ) is False
    assert bk.heartbeat_task(
        task_id, "wk-B", lease_s=CLAIM_LEASE_S, now="2026-06-01 13:01:01"
    ) is True


def test_claim_attempts_guard_and_running_increments(bk) -> None:
    """TC-TASK-02 的 claim 侧防线：attempts ≥ max_attempts 不再被认领。"""
    task_id = _mk_task(bk)
    for expected in (1, 2, 3):
        got = bk.claim_next_task("wk-A", lease_s=CLAIM_LEASE_S, now=NOW_TS)
        assert got is not None and got["attempts"] == expected  # 认领即计一次尝试
        bk.update_task(task_id, status="running")
        assert bk.get_task(task_id)["attempts"] == expected  # running 不重复计
        bk.update_task(task_id, status="pending")  # 手工回队模拟重试路径
    assert bk.get_task(task_id)["attempts"] == 3
    # 重试预算耗尽（pending 也不认领——防御）
    assert bk.claim_next_task("wk-A", lease_s=CLAIM_LEASE_S, now=NOW_TS) is None


def test_claim_type_filter(bk) -> None:
    task_id = _mk_task(bk, task_type="maintenance")
    assert bk.claim_next_task(
        "wk-A", lease_s=CLAIM_LEASE_S, task_types=("ingest",), now=NOW_TS
    ) is None
    got = bk.claim_next_task(
        "wk-A", lease_s=CLAIM_LEASE_S, task_types=("maintenance",), now=NOW_TS
    )
    assert got is not None and got["id"] == task_id


def test_real_concurrent_claim_exactly_one_winner(backend, claim_factory) -> None:
    """承接遗留 1（m1-5/m1-2 P3-7/P3-B）：真实并发窗口——两执行器 barrier 对齐
    并发认领同任务，恰好一人得手（3 轮强化；sqlite 单写序列化 / pg SKIP LOCKED）。"""
    setup = backend.make_backend()
    for round_no in range(3):
        task_id = setup.create_task(None, task_type="ingest")
        barrier = threading.Barrier(2, timeout=10)
        results: list[dict | None] = []
        lock = threading.Lock()

        def claim(worker: str) -> None:
            b = claim_factory()
            barrier.wait()
            got = b.claim_next_task(worker, lease_s=CLAIM_LEASE_S, now=NOW_TS)
            with lock:
                results.append(got)

        threads = [
            threading.Thread(target=claim, args=(f"wk-A{round_no}",)),
            threading.Thread(target=claim, args=(f"wk-B{round_no}",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        assert len(results) == 2
        winners = [r for r in results if r is not None]
        assert len(winners) == 1, f"round {round_no}: 恰好一人认领（got {results!r}）"
        assert winners[0]["id"] == task_id
        row = setup.get_task(task_id)
        assert row["status"] == "leased"
        assert row["lease_owner"] in (f"wk-A{round_no}", f"wk-B{round_no}")
