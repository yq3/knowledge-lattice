"""TC-TASK-02 重试上限【单测｜M2】+ TaskRunner 执行循环单元（M2.1）。

- 重试上限：持续失败任务重跑——attempts < 3 每轮回 pending 供重认领，第 3 次
  失败后保持 failed 留人工、error 落原因；
- 取消类失败（'cancelled:'）不可重试（吸收态）；
- executor 异常早于自身终态写入 → runner 兜底落 failed；
- 未知任务类型不被认领（预留分发位不误伤）；
- task_id 进 contextvars（日志贯通——design §3 v0.8.5 worker 侧）；
- 心跳线程运行中刷 heartbeat_at（fake clock 确定性断言）。

双后端参数化；ingest 真链路重试（FakeEmbedder 失败注入）在 [sqlite]/[pg] 各跑。
"""

from __future__ import annotations

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


def test_retry_budget_three_attempts_then_failed(backend, wk_settings) -> None:
    """TC-TASK-02：attempts ≥ 3 转 failed 留人工（error 落原因）。"""
    bk = backend.make_backend()
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


def test_cancelled_failure_not_retried(backend, wk_settings) -> None:
    """取消类失败（error 'cancelled:'）是吸收态——不回队。"""
    bk = backend.make_backend()
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


def test_unknown_task_type_not_claimed(backend, wk_settings) -> None:
    """预留分发位（reindex/reembed/delete/semantic_*）：不认领不误伤。"""
    bk = backend.make_backend()
    task_id = bk.create_task(None, task_type="reembed")
    runner = TaskRunner(bk, wk_settings, worker_id="wk-test")
    assert runner.run_once() is False
    # 任务行原地 pending（后续段的 executor 落地后接管）
    assert bk.get_task(task_id)["status"] == "pending"


def test_task_id_contextvar_during_execution(backend, wk_settings) -> None:
    """日志贯通：task_id 进 contextvars（worker 侧——design §3 v0.8.5）。"""
    bk = backend.make_backend()
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


def test_heartbeat_thread_refreshes_heartbeat_at(backend, wk_settings) -> None:
    """心跳线程：running 期间按 worker_heartbeat_s 刷 heartbeat_at（fake clock
    确定性推进——两个采样时点不同）。"""
    bk = backend.make_backend()
    task_id = bk.create_task(None, task_type="ingest")

    import threading

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
        bk, wk_settings, worker_id="wk-test", clock=clock,
        services=WorkerServices(bk, wk_settings, ingest=_SlowIngest()),
    )
    assert runner.run_once() is True
    assert entered.wait(timeout=5)
    # 心跳线程至少跑过一轮（heartbeat_s=0.05）
    import time

    time.sleep(0.3)
    release.set()
    row = bk.get_task(task_id)
    hb = row["heartbeat_at"]
    hb = hb.strftime("%Y-%m-%d %H:%M:%S") if not isinstance(hb, str) else hb
    assert hb > NOW_TS  # 已被心跳推进（> claim 时点）


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
