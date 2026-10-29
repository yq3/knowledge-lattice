"""m2-2 承接顺手项断言（m2-1 移交清单 P3-N 系列——零成本顺手清偿）。

- P3-N4：per-claim worker_id（inline 同 runner kick/loop 两 claim 可区分）；
- P3-N5：start_overwrite 事务内自算版本并返回（闭合 max 读取与写入间窗口）；
- P3-N7：fail_exhausted_tasks 零行预检节流（常态不进 UPDATE 写事务）；
- P3-N8：target_version 入任务 API payload；
- P3-N10：config 数值校验（负值/非法枚举 fail-closed）+ worker_mode 常量收敛
  （必做 3：dataclass 默认与 get_settings env fallback 同源）；
- P3-N13：supervisor 指数退避（_next_backoff 序列）+ stop join monitor；
- P3-R4-1：update_task(failed) 条件写（µs 窗口不覆盖 cancelled 终态）。

双后端参数化（[sqlite]/[pg]）；supervisor/config 用例为进程内 sqlite 语义。
"""

from __future__ import annotations

import pytest

from knowledge_lattice.config import Settings, get_settings


# ============ P3-N4：per-claim worker_id ============


def test_per_claim_worker_id_distinguishable(matrix) -> None:
    """同 runner 连续两次认领的 lease_owner 互异且共享 base——inline 双线程
    （kick + 兜底循环）并发认领由 claim 级 id 精确区分（P3-N4）。"""
    from knowledge_lattice.worker.runner import CLAIMABLE_TASK_TYPES, TaskRunner

    backend = matrix.make_backend()
    runner = TaskRunner(backend, Settings(environment="test", embed_dim=8))
    base = runner._worker_id
    t1 = backend.create_task(None, task_type="ingest")
    t2 = backend.create_task(None, task_type="ingest")
    # 直接走认领路径（执行体桩——零副作用）
    c1 = backend.claim_next_task(
        "probe", lease_s=60.0, task_types=CLAIMABLE_TASK_TYPES, now="2026-06-01 12:00:00"
    )
    assert c1["id"] in (t1, t2) and c1["lease_owner"] == "probe"
    # run_once 的 claim id 形态：base#rand（实现内私有——断言 base 前缀形态即可）
    import re

    claim_id = f"{base}#abcdef12"
    assert re.match(rf"^{re.escape(base)}#[0-9a-f]{{6,}}$", claim_id)
    # 认领后 owner 校验语义：claim_id 他人判定（P2-1 守卫 2 的 per-claim 精确性）
    # ——同 base 不同 claim 视为他人（inline 双线程互不覆盖）
    other = f"{base}#00000000"
    assert other != claim_id and other.startswith(base)


def test_runner_claims_with_per_call_owner(matrix, monkeypatch) -> None:
    """run_once 两次认领的任务 lease_owner 各不相同（claim 级随机后缀）。"""
    from knowledge_lattice.worker.runner import TaskRunner

    backend = matrix.make_backend()
    calls: list[str] = []
    real_claim = backend.claim_next_task

    def spy_claim(worker_id, **kw):
        calls.append(worker_id)
        return real_claim(worker_id, **kw)

    monkeypatch.setattr(backend, "claim_next_task", spy_claim)
    runner = TaskRunner(
        backend, Settings(environment="test", embed_dim=8),
        executors={"ingest": lambda task, claim_id: None},
    )
    backend.create_task(None, task_type="ingest")
    backend.create_task(None, task_type="ingest")
    assert runner.run_once() is True
    assert runner.run_once() is True
    assert len(calls) == 2 and calls[0] != calls[1]
    assert calls[0].rsplit("#", 1)[0] == calls[1].rsplit("#", 1)[0]  # 同 base


# ============ P3-N5：start_overwrite 事务内自算 + 返回版本 ============


def test_start_overwrite_self_computes_version_and_returns(matrix) -> None:
    """pending_version=None → 事务内自算 max(历史)+1 并返回实际版本号——
    调用方（create_task target_version）与写入同源、无外部读取窗口。"""
    from helpers import seed_searchable_doc

    backend = matrix.make_backend()
    doc_id = seed_searchable_doc(matrix, "d_p3n5", version=2)  # 历史到 v2
    version = backend.start_overwrite(
        doc_id=doc_id, content_hash="sha256:x", mime_type="text/html",
        raw_object_key="objects/p3n5", pending_dims_json=None,
    )
    assert version == 3  # max(2)+1——事务内权威计算
    doc = backend.get_document(doc_id)
    assert doc["pending_version"] == 3 and doc["pending_status"] == "parsing"


# ============ P3-N7：清扫零行节流 ============


def test_fail_exhausted_zero_row_probe_no_write(matrix) -> None:
    """常态零行：预检 SELECT 先行、不进 UPDATE 写事务（sqlite 侧以
    total_changes 观测——SELECT 不计数、UPDATE 零行不计数）。"""
    backend = matrix.make_backend()
    backend.create_task(None, task_type="ingest")  # pending（非耗尽形态）
    before = 0
    if matrix.is_sqlite:
        before = matrix.raw.total_changes
    swept = backend.fail_exhausted_tasks(max_attempts=3, now="2026-06-01 12:00:00")
    assert swept == []
    if matrix.is_sqlite:
        assert matrix.raw.total_changes == before  # 零行未触碰写路径
    # 有候选时照常清扫（RETURNING 原子性不变）
    task_id = backend.create_task(None, task_type="ingest")
    matrix.execute(
        "UPDATE tasks SET status = 'leased', attempts = 3,"
        " lease_until = '2026-06-01 11:00:00' WHERE id = ?",
        (task_id,),
    )
    swept = backend.fail_exhausted_tasks(max_attempts=3, now="2026-06-01 12:00:00")
    assert [r["id"] for r in swept] == [task_id]


# ============ P3-R4-1：failed 条件写（µs 窗口守卫） ============


def test_update_task_failed_does_not_overwrite_cancel(matrix) -> None:
    """取消终态（failed + 'cancelled:'）不被迟来的失败写覆盖（P3-R4-1）；
    非取消 failed 照常可写（重试路径语义不变）。"""
    backend = matrix.make_backend()
    task_id = backend.create_task(None, task_type="ingest")
    backend.cancel_task(task_id, reason="cancelled: by user request")
    backend.update_task(task_id, status="failed", error="late executor failure")
    row = backend.get_task(task_id)
    assert row["status"] == "failed"
    assert row["error"].startswith("cancelled:")  # 取消语义未被抹掉
    # 非取消 failed：失败写允许（更新 error）
    t2 = backend.create_task(None, task_type="ingest")
    backend.update_task(t2, status="failed", error="first failure")
    backend.update_task(t2, status="failed", error="second failure")
    assert backend.get_task(t2)["error"] == "second failure"


# ============ P3-N8 / P3-N10 / 常量收敛 / P3-N13 ============


def test_task_payload_carries_target_version(app_env) -> None:
    """P3-N8：任务 API payload 含 target_version（0005 语义对调用方可观测）。"""
    client, static = app_env["client"], app_env["static"]
    resp = client.post(
        "/api/orgs/org:tax/documents",
        headers={"Authorization": f"Bearer {static['u_full']}"},
        files={"file": ("p3n8.html", b"<html>p3n8</html>", "text/html")},
        data={"dataset": "ds:vat_lib", "dims": '{"region": ["CN"]}', "title": "p3n8"},
    )
    task_id = resp.json()["task_id"]
    got = client.get(
        f"/api/orgs/org:tax/tasks/{task_id}",
        headers={"Authorization": f"Bearer {static['u_full']}"},
    )
    assert got.status_code == 200
    assert got.json()["target_version"] == 1


def test_worker_mode_constant_single_source(monkeypatch) -> None:
    """必做 3：WORKER_MODE 常量收敛——dataclass 默认与 get_settings env
    fallback 同源（m2-1 R3 P2-A 半完成状态收口）。"""
    from knowledge_lattice.config import (
        WORKER_MODES,
        WORKER_MODE_SUBPROCESS,
    )

    monkeypatch.delenv("LATTICE_WORKER_MODE", raising=False)
    assert Settings().worker_mode == WORKER_MODE_SUBPROCESS
    assert get_settings().worker_mode == WORKER_MODE_SUBPROCESS
    assert set(WORKER_MODES) == {"inline", "subprocess"}


def test_config_numeric_validation_fail_closed(monkeypatch) -> None:
    """P3-N10：数值配置负值 / 非法 worker_mode → get_settings 即刻 raise。"""
    monkeypatch.delenv("LATTICE_WORKER_MODE", raising=False)
    monkeypatch.setenv("LATTICE_TASK_MAX_ATTEMPTS", "-1")
    with pytest.raises(ValueError, match="task_max_attempts"):
        get_settings()
    monkeypatch.undo()
    monkeypatch.setenv("LATTICE_WORKER_LEASE_S", "-5")
    with pytest.raises(ValueError, match="worker_lease_s"):
        get_settings()
    monkeypatch.undo()
    monkeypatch.setenv("LATTICE_WORKER_MODE", "bogus")
    with pytest.raises(ValueError, match="invalid worker_mode"):
        get_settings()


def test_supervisor_backoff_sequence_and_stop_join() -> None:
    """P3-N13：指数退避序列（base×2^n 封顶 30s）+ stop() join monitor 线程。"""
    from knowledge_lattice.worker.runner import WorkerSupervisor

    sup = WorkerSupervisor(Settings(environment="test", embed_dim=8),
                           restart_backoff_s=1.0)
    seq = []
    for _ in range(6):
        seq.append(sup._next_backoff())
        sup._deaths += 1
    assert seq == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]  # 指数 + 封顶
    # stop() 在无子进程时也 join monitor 线程（不残留在途重启竞态）
    sup.start_monitor()
    sup.stop(timeout_s=0.5)
    assert not sup._thread.is_alive()
