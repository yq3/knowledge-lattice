"""M2.1 subprocess worker 测试服务工厂（LATTICE_WORKER_SERVICES=module:attr 扩展点）。

子进程 worker 经本工厂获得 fake provider 栈（FakeEmbedder——跨进程无法传对象，
经 import 钩子注入），并提供崩溃/慢执行桩（TC-TASK-04 / TC-E2E-03）：

- LATTICE_TEST_CRASH_FLAG=<文件路径>：文件内容 = 目标 doc_id——执行该 doc 的任务时
  worker 自杀（SIGKILL——OOM killer 的真实信号形态；一次性：data_dir 下标记文件防
  崩溃循环，重启后的 worker 重认领同任务正常完成——租约重认领链路同时被验证）；
- LATTICE_TEST_SLOW_FLAG=<文件路径> + LATTICE_TEST_SLOW_S=<秒>：执行前 sleep
  （制造"running 中被外部 kill -9"的窗口；一次性同上）。

标志走文件（而非 env）：worker 子进程已在 lifespan 拉起，测试进程事后仍能经
文件系统精确指认目标文档（env 在子进程内不可变）。
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

from fake_providers import FakeEmbedder

from knowledge_lattice.adapters.embedder import EmbeddingGate
from knowledge_lattice.core.docs.credentials import CredentialService
from knowledge_lattice.core.docs.ingest import IngestService
from knowledge_lattice.store.sqlite import connect, migrate_db
from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend
from knowledge_lattice.worker.runner import WorkerServices


def _flag_target(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8").strip() or None


def build_services(settings) -> WorkerServices:
    bootstrap = connect(settings.db_path)
    migrate_db(bootstrap)
    bootstrap.close()
    backend = ThreadLocalBackend(settings.db_path)

    embedder = FakeEmbedder(dim=settings.embed_dim, model_name="fake-embed")
    gate = EmbeddingGate()
    ingest = IngestService(
        backend, embedder, settings, gate, settings.data_dir / "objects"
    )
    credentials = CredentialService(backend, settings, settings.data_dir / "objects")

    slow_s = float(os.environ.get("LATTICE_TEST_SLOW_S", "3"))
    marker_dir = settings.data_dir

    class _InstrumentedIngest:
        """崩溃/慢执行桩 + 透传真 IngestService（同签名 run_task）。"""

        def run_task(self, task_id: str, *, stop_after=None, should_continue=None):
            task = backend.get_task(task_id)
            doc_id = task.get("doc_id") if task else None
            if (
                doc_id is not None
                and doc_id == _flag_target(os.environ.get("LATTICE_TEST_CRASH_FLAG"))
                and not _fired(marker_dir, "crash")
            ):
                _mark(marker_dir, "crash")
                os.kill(os.getpid(), signal.SIGKILL)  # OOM killer 信号形态
            if (
                doc_id is not None
                and doc_id == _flag_target(os.environ.get("LATTICE_TEST_SLOW_FLAG"))
                and not _fired(marker_dir, "slow")
            ):
                _mark(marker_dir, "slow")
                time.sleep(slow_s)
            return ingest.run_task(
                task_id, stop_after=stop_after, should_continue=should_continue
            )

    return WorkerServices(
        backend=backend, settings=settings,
        ingest=_InstrumentedIngest(), credentials=credentials,
        _gate=gate, _embedder=embedder,
    )


def _mark(root: Path, name: str) -> None:
    (root / f".m2_test_{name}_fired").write_text("1", encoding="utf-8")


def _fired(root: Path, name: str) -> bool:
    return (root / f".m2_test_{name}_fired").exists()
