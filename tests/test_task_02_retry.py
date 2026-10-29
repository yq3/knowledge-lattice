"""TC-TASK-02 重试上限【单测｜M2】+ TaskRunner 执行循环单元（M2.1）。

- 重试上限：持续失败任务重跑——attempts < 3 每轮回 pending 供重认领，第 3 次
  失败后保持 failed 留人工、error 落原因；
- 取消类失败（'cancelled:'）不可重试（吸收态）；
- executor 异常早于自身终态写入 → runner 兜底落 failed；
- 未知任务类型不被认领（预留分发位不误伤）；
- task_id 进 contextvars（日志贯通——design §3 v0.8.5 worker 侧）；
- 心跳线程运行中刷 heartbeat_at（P2-6，M2.1 R2：真实断言——claim 后采样，等
  2~3 个心跳间隔再采样，fake clock 推进 ≥ NOW_TS+14；sqlite 臂 ThreadLocalBackend
  每线程一连接，心跳线程跨线程写不再被 check_same_thread 吞错）；
- P2-1（M2.1 R2）：终态所有权——quality 阶段取消不被 done 覆盖 / _on_failure
  不覆盖 done / 丢租约后 stage 抛错不覆盖新持有者；
- P2-2（M2.1 R2）：崩溃耗尽清扫——claim→过期 3 轮不执行 → 第 4 次认领前清扫
  转 failed + error 原因 + 文档侧按 target_version 落 pending failed。

双后端参数化；ingest 真链路重试（FakeEmbedder 失败注入）在 [sqlite]/[pg] 各跑。
"""

from __future__ import annotations

import threading
import time

import pytest
from fake_providers import FakeEmbedder
from helpers import NOW_TS

from knowledge_lattice.config import Settings
from knowledge_lattice.log import task_id_var
from knowledge_lattice.worker.runner import TaskRunner, WorkerServices


@pytest.fixture()
def wk_settings(tmp_path):
    return Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        worker_heartbeat_s=0.05, worker_lease_s=60.0,
        task_max_attempts=3,
    )


@pytest.fixture()
def runner_backend(backend, tmp_path):
    """runner 用线程安全 backend（P2-6）：sqlite=ThreadLocalBackend 每线程一连接
    （心跳线程独立连接，跨线程写不再抛 ProgrammingError 被吞）；pg=共享单连接
    （psycopg3 线程安全）。"""
    if backend.is_sqlite:
        from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

        return ThreadLocalBackend(tmp_path / "lattice.db")
    return backend.make_backend()


def _ts(v) -> str:
    if isinstance(v, str):
        return v
    return v.strftime("%Y-%m-%d %H:%M:%S")


class _FailingIngest:
    """持续失败桩：直接 raise（不写终态——runner 兜底路径同时被验证）。"""

    def __init__(self) -> None:
        self.calls = 0

    def run_task(self, task_id, *, stop_after=None, should_continue=None):
        self.calls += 1
        raise RuntimeError(f"boom #{self.calls}")


class _CancelledIngest:
    """取消类失败桩：自写 failed + 'cancelled:' error 后 raise。"""

    def __init__(self, backend) -> None:
        self._backend = backend

    def run_task(self, task_id, *, stop_after=None, should_continue=None):
        self._backend.update_task(task_id, status="failed", error="cancelled: by user")
        raise RuntimeError("lost race with cancel")


def test_retry_budget_three_attempts_then_failed(runner_backend, wk_settings) -> None:
    """TC-TASK-02：attempts ≥ 3 转 failed 留人工（error 落原因）。"""
    bk = runner_backend
    task_id = bk.create_task(None, task_type="ingest")
    failing = _FailingIngest()
    runner = TaskRunner(
        bk, wk_settings, worker_id="wk-test",
        services=WorkerServices(bk, wk_settings, ingest=failing),
    )

    assert runner.run_once() is True
    row = bk.get_task(task_id)
    assert row["status"] == "pending" and row["attempts"] == 1  # 回队供重认领

    assert runner.run_once() is True
    row = bk.get_task(task_id)
    assert row["status"] == "pending" and row["attempts"] == 2

    assert runner.run_once() is True
    row = bk.get_task(task_id)
    assert row["status"] == "failed" and row["attempts"] == 3  # 重试预算耗尽留人工
    assert "boom #3" in row["error"]  # error 落最后失败原因

    assert runner.run_once() is False  # failed 不再被认领（幂等不复活）
    assert failing.calls == 3


def test_cancelled_failure_not_retried(runner_backend, wk_settings) -> None:
    """取消类失败（error 'cancelled:'）是吸收态——不回队。"""
    bk = runner_backend
    task_id = bk.create_task(None, task_type="ingest")
    runner = TaskRunner(
        bk, wk_settings, worker_id="wk-test",
        services=WorkerServices(bk, wk_settings, ingest=_CancelledIngest(bk)),
    )
    assert runner.run_once() is True
    row = bk.get_task(task_id)
    assert row["status"] == "failed"
    assert row["error"] == "cancelled: by user"
    assert runner.run_once() is False  # 不重试


def test_unknown_task_type_not_claimed(runner_backend, wk_settings) -> None:
    """预留分发位（reindex/reembed/delete/semantic_*）：不认领不误伤。"""
    bk = runner_backend
    task_id = bk.create_task(None, task_type="reembed")
    runner = TaskRunner(bk, wk_settings, worker_id="wk-test")
    assert runner.run_once() is False
    # 任务行原地 pending（后续段的 executor 落地后接管）
    assert bk.get_task(task_id)["status"] == "pending"


def test_task_id_contextvar_during_execution(runner_backend, wk_settings) -> None:
    """日志贯通：task_id 进 contextvars（worker 侧——design §3 v0.8.5）。"""
    bk = runner_backend
    task_id = bk.create_task(None, task_type="ingest")
    seen: list[str | None] = []

    class _SpyIngest:
        def run_task(self, task_id, *, stop_after=None, should_continue=None):
            seen.append(task_id_var.get())

    runner = TaskRunner(
        bk, wk_settings, worker_id="wk-test",
        services=WorkerServices(bk, wk_settings, ingest=_SpyIngest()),
    )
    assert runner.run_once() is True
    assert seen == [task_id]
    assert task_id_var.get() is None  # 执行后复位（不泄漏到外层上下文）


def test_heartbeat_thread_refreshes_heartbeat_at(runner_backend, wk_settings) -> None:
    """P2-6（M2.1 R2）真实断言：claim 后采样 claim_hb，等 ≥2 个心跳间隔再采样
    ——心跳线程实际刷新（fake clock 每 tick +7s：claim=+7，两次心跳即 ≥ +14；
    旧断言在心跳线程完全不工作时恒真，已废）。sqlite 臂 ThreadLocalBackend
    心跳线程跨线程写真实生效。"""
    bk = runner_backend
    task_id = bk.create_task(None, task_type="ingest")

    entered = threading.Event()
    release = threading.Event()

    class _SlowIngest:
        def run_task(self, task_id, *, stop_after=None, should_continue=None):
            entered.set()
            release.wait(timeout=10)

    class _Clock:
        """每次调用推进 7s——claim 与各心跳采样严格不同。"""

        def __init__(self) -> None:
            self.ticks = 0

        def __call__(self) -> str:
            from knowledge_lattice.store.taskclock import add_seconds

            self.ticks += 1
            return add_seconds(NOW_TS, self.ticks * 7)

    clock = _Clock()
    runner = TaskRunner(
        bk, wk_settings, worker_id="wk-hb-test", clock=clock,
        services=WorkerServices(bk, wk_settings, ingest=_SlowIngest()),
    )
    done = threading.Event()

    def _run() -> None:
        runner.run_once()
        done.set()

    threading.Thread(target=_run, daemon=True).start()
    assert entered.wait(timeout=5)  # executor 已进入阻塞阶段（心跳线程在跳）
    # 采样 1（此刻可能已含若干心跳 tick——无妨，取相对推进证据）
    hb1 = _ts(bk.get_task(task_id)["heartbeat_at"])
    assert hb1 > NOW_TS  # claim/心跳已写入非平凡时点
    # 等 ≥2 个心跳间隔（heartbeat_s=0.05 → 0.3s ≈ 6 轮；clock 每轮 +7）
    time.sleep(0.3)
    hb2 = _ts(bk.get_task(task_id)["heartbeat_at"])
    # 心跳线程真实刷新：两次采样间推进 ≥2 ticks（+14s），且严格前进
    assert hb2 > hb1, f"heartbeat not refreshed (hb1={hb1}, hb2={hb2})"
    assert hb2 >= "2026-06-01 12:00:14"
    release.set()
    assert done.wait(timeout=10)


def test_ingest_real_chain_retry_then_fail(ver_env, tmp_path) -> None:
    """ingest 真链路重试：embed 持续不可达 → 三次尝试后 failed 留原因；文档
    落 active_error（首次上传 D20 已切换——P2-1 落点）。"""
    backend, settings = ver_env["backend"], ver_env["settings"]
    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        worker_heartbeat_s=0.05, task_max_attempts=3,
    )
    ver_env["embedder"].fail = True  # 持续失败注入
    runner = TaskRunner(
        backend, settings, worker_id="wk-test",
        services=WorkerServices(
            backend, settings, ingest=ver_env["service"], credentials=None
        ),
    )
    doc_id, task_id = ver_env["service"].create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="t",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=("<html><body><p>税务一般纳税人安装服务分别核算。</p></body></html>").encode(),
        mime_type="text/html", filename="a.html",
    )
    for _ in range(3):
        assert runner.run_once() is True
    row = backend.get_task(task_id)
    assert row["status"] == "failed" and row["attempts"] == 3
    assert "unreachable" in row["error"]
    doc = backend.get_document(doc_id)
    assert doc["active_version"] == 1  # D20：lexical 即切在用
    assert doc["active_status"] is not None
    assert doc["active_error"]  # 失败原因落文档侧
    # 修复后不再自动重试（预算耗尽）——但直调 run_task 仍可续（M1 语义保留）
    ver_env["embedder"].fail = False
    assert runner.run_once() is False
    ver_env["service"].run_task(task_id)
    row = backend.get_task(task_id)
    doc = backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_full"  # 阶段幂等续跑从 embed 续


# ============ P2-1（M2.1 R2）终态所有权守卫 ============


def test_cancel_during_quality_stage_keeps_failed(qual_env, tmp_path) -> None:
    """P2-1(a)：quality 阶段（最后一次边界检查之后的长阶段）中取消——done 不得
    覆盖取消终态（update_task done 守卫 + run_task 终态前最后探测双防线）。"""
    backend, service, quality = (
        qual_env["backend"], qual_env["service"], qual_env["quality"]
    )
    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        worker_heartbeat_s=0.05, worker_lease_s=60.0,
    )
    doc_id, task_id = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="q-cancel",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=("<html><body><p>质量阶段取消用例。</p></body></html>").encode(),
        mime_type="text/html", filename="q.html",
    )

    entered = threading.Event()
    release = threading.Event()
    real_detect = quality.detect_document

    def blocking_detect(*args, **kwargs):
        entered.set()
        release.wait(timeout=10)
        return real_detect(*args, **kwargs)

    quality.detect_document = blocking_detect

    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

    if qual_env["db"].is_sqlite:
        bk = ThreadLocalBackend(tmp_path / "lattice.db")
    else:
        bk = backend
    thread_ingest = IngestService(
        bk, qual_env["embedder"], settings, qual_env["gate"], qual_env["objects_dir"],
        quality=quality,
    )
    runner = TaskRunner(
        bk, settings, worker_id="wk-q-cancel",
        services=WorkerServices(bk, settings, ingest=thread_ingest),
    )
    done = threading.Event()

    def _run() -> None:
        runner.run_once()
        done.set()

    threading.Thread(target=_run, daemon=True).start()
    assert entered.wait(timeout=10)  # 已进入 quality 阶段（embed 已完成）
    # 取消（终态 failed + 'cancelled:'）→ 放行 quality → 执行器完成路径不得写 done
    service.cancel_task(org_id="org:tax", task_id=task_id, actor_user_id="u_full")
    release.set()
    assert done.wait(timeout=10)

    row = backend.get_task(task_id)
    assert row["status"] == "failed", "取消终态被 done 覆盖（P2-1）"
    assert row["error"] == "cancelled: by user request"


def test_on_failure_does_not_clobber_done(runner_backend, wk_settings) -> None:
    """P2-1(b)：_on_failure 对已 done 任务直接 return（迟来异常不覆盖完成态）。"""
    bk = runner_backend
    task_id = bk.create_task(None, task_type="ingest")

    class _DoneThenRaise:
        def run_task(self, task_id, *, stop_after=None, should_continue=None):
            bk.update_task(task_id, status="done")
            raise RuntimeError("late failure after done")

    runner = TaskRunner(
        bk, wk_settings, worker_id="wk-done-guard",
        services=WorkerServices(bk, wk_settings, ingest=_DoneThenRaise()),
    )
    assert runner.run_once() is True
    row = bk.get_task(task_id)
    assert row["status"] == "done"  # 保持完成态
    assert row["error"] is None


def test_lost_lease_failure_does_not_clobber_new_holder(
    runner_backend, wk_settings
) -> None:
    """P2-1(c)：丢租约后 stage 抛错——旧执行器 _on_failure 不覆盖新持有者状态。"""
    bk = runner_backend
    task_id = bk.create_task(None, task_type="ingest")

    claimed = threading.Event()
    release = threading.Event()

    class _SlowThenRaise:
        def run_task(self, task_id, *, stop_after=None, should_continue=None):
            claimed.set()
            release.wait(timeout=10)
            raise RuntimeError("stale executor failure")

    runner = TaskRunner(
        bk, wk_settings, worker_id="wk-stale",
        services=WorkerServices(bk, wk_settings, ingest=_SlowThenRaise()),
    )
    done = threading.Event()

    def _run() -> None:
        runner.run_once()
        done.set()

    threading.Thread(target=_run, daemon=True).start()
    assert claimed.wait(timeout=10)
    # 模拟租约过期被新持有者重认领（认领用真实时钟 → 过期点 = 真实 now + 61s）
    from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

    new_holder = bk.claim_next_task(
        "wk-new-holder", lease_s=60.0, now=add_seconds(utc_now_ts(), 61)
    )
    assert new_holder is not None and new_holder["id"] == task_id
    release.set()  # 旧执行器此刻抛错
    assert done.wait(timeout=10)

    row = bk.get_task(task_id)
    assert row["lease_owner"] == "wk-new-holder"  # 新持有者所有权未被夺走
    assert row["status"] == "leased"  # 旧执行器的 failed 写被守卫拦下


# ============ P2-2（M2.1 R2）崩溃耗尽清扫 ============


def test_exhausted_crash_tasks_swept_to_failed(runner_backend, wk_settings) -> None:
    """P2-2：claim→过期 3 轮不执行（worker 每轮认领后即崩的等效造数）→ 第 4 次
    run_once 前清扫转 failed + error 原因 + 不再可认领。"""
    from knowledge_lattice.store.taskclock import add_seconds

    bk = runner_backend
    task_id = bk.create_task(None, task_type="ingest")
    # 三轮「认领即崩」：每次认领（attempts+1）后不执行、租约过期（时钟 +61s）
    for round_no in range(1, 4):
        got = bk.claim_next_task(
            f"wk-crash-{round_no}", lease_s=60.0, now=add_seconds(NOW_TS, round_no * 61)
        )
        assert got is not None and got["attempts"] == round_no
    row = bk.get_task(task_id)
    assert row["status"] == "leased" and row["attempts"] == 3

    runner = TaskRunner(
        bk, wk_settings, worker_id="wk-sweep",
        services=WorkerServices(bk, wk_settings),
    )
    assert runner.run_once() is False  # 无可认领（attempts 耗尽）——但清扫已执行
    row = bk.get_task(task_id)
    assert row["status"] == "failed"
    assert "attempt limit exceeded" in row["error"]
    assert str(3) in row["error"]  # attempts 数入 error 原因
    assert row["lease_owner"] is None  # 租约清空（人工接管无歧义）


def test_exhausted_sweep_fails_pending_version_by_target(
    ver_env, tmp_path, monkeypatch
) -> None:
    """P2-2 文档侧收尾：耗尽任务持 pending 版本（parsing，块未写）→ 清扫按
    target_version 落 pending failed（不滞留 parsing；T8 删块无块可删）+ 任务行
    failed 留人工。"""
    backend, service = ver_env["backend"], ver_env["service"]
    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        worker_heartbeat_s=0.05, task_max_attempts=3,
    )
    doc_id, task_id = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="exhaust",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=("<html><body><p>耗尽清扫文档侧。</p></body></html>").encode(),
        mime_type="text/html", filename="e.html",
    )
    task = backend.get_task(task_id)
    assert task["target_version"] == 1  # 0005：任务行携带目标版本

    # 三轮认领即「崩」（不执行）+ 过期
    from knowledge_lattice.store.taskclock import add_seconds
    from helpers import NOW_TS as _NOW

    for round_no in range(1, 4):
        backend.claim_next_task(
            f"wk-x-{round_no}", lease_s=60.0, now=add_seconds(_NOW, round_no * 61)
        )
    swept = backend.fail_exhausted_tasks(
        max_attempts=3, now=add_seconds(_NOW, 4 * 61)
    )
    assert len(swept) == 1 and swept[0]["id"] == task_id
    # 文档侧收尾（runner 的 _sweep_exhausted 同款调用）
    service.fail_document_version(swept[0], "attempt limit exceeded (worker crash?)")

    doc = backend.get_document(doc_id)
    assert doc["pending_status"] == "failed"  # 不滞留 parsing
    assert doc["pending_error"] == "attempt limit exceeded (worker crash?)"
    row = backend.get_task(task_id)
    assert row["status"] == "failed" and "attempt limit exceeded" in row["error"]
    # 覆盖上传不再被 409 锁死（pending failed 放行新版本）
    doc2, task2 = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="exhaust-v2",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=("<html><body><p>第二版。</p></body></html>").encode(),
        mime_type="text/html", filename="e2.html", doc_id=doc_id,
    )
    assert backend.get_task(task2)["target_version"] == 2
