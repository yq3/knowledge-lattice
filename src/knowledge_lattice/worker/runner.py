"""任务执行循环（worker/runner.py——design §3 + §5.3 任务状态机）。

TaskRunner（进程内库——inline 模式与子进程 main() 共用同一执行体）：
- **认领**：claim_next_task（pending 或租约过期的 leased/running——原子，两执行器
  竞争同任务恰好一人得手）；
- **心跳**：leased/running 期间独立线程每 worker_heartbeat_s 刷 heartbeat_at +
  lease_until；失守（重认领/取消）即停跳；
- **执行**：按 tasks.type 分发 executor（ingest→IngestService.run_task〔阶段幂等
  续跑原样迁移〕；maintenance→maintenance.run_maintenance；reindex/reembed/
  delete/semantic_* 为预留分发位——本段不认领，claim 按 type 过滤）；
- **取消协同**：should_continue（心跳探测）在阶段/批次边界停止在途执行
  （TC-TASK-03）；
- **重试**：执行异常且 attempts < task_max_attempts → 回 pending 供重认领
  （TC-TASK-02：attempts ≥ 3 保持 failed 留人工，error 落原因）；取消类
  （'cancelled:'）不可重试；终态所有权守卫（P2-1）：done 不被迟来异常覆盖、
  丢租约旧执行器不覆盖新持有者（worker_id 每 runner 唯一）；
- **崩溃耗尽清扫**（P2-2）：每轮认领前——租约过期且 attempts ≥ max 的任务
  转 failed 留人工，并按 target_version 落文档侧 pending failed；
- **日志贯通**：task_id 进 contextvars（log.py task_id_var——主进程侧同款）。

子进程入口（`python -m knowledge_lattice.worker`）：装配 backend/services →
挂 log.py 同套 handler → 启动探针（写入侧 gate——TC-EMB-03 拒绝档；与主进程
探针各自独立持有进程内 gate，口径申报：主/worker 双探针流量 = 2×哨兵调用/
周期，POC 量级可忽略）→ IPC 唤醒 + 兜底轮询双通道主循环。

写竞争治理口径（design §5.3 NFR-9——M2.1 落实 busy_timeout〔连接工厂既有〕+
worker 短事务分批提交〔各阶段写入本就逐事务提交〕）：**查询级审计异步写、
权限事件走 outbox 的本体归 m2-2**（本段仅此口径注记，不实现 outbox 搬运）。

服务装配扩展点：`LATTICE_WORKER_SERVICES=module:attr` 指向 build(settings) ->
WorkerServices 的工厂（部署侧自定义 provider / 测试注入 fake embedder 与崩溃
桩——跨进程无法传对象，经 import 钩子达成）。

worker_mode 默认 subprocess（M2.1 R2 边界裁定 A(a)——生产 fail-safe）；inline
为测试/最小部署的显式选项（app.py InlineWorkerHandle：kick 同步消化 + 兜底
循环全类型认领——ingest 陈旧口径 created_before，见 P2-7）。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass

from knowledge_lattice.config import Settings, get_settings
from knowledge_lattice.log import setup_logging, task_id_var
from knowledge_lattice.store.taskclock import utc_now_ts

logger = logging.getLogger(__name__)

# 本段 runner 认领的任务类型（reindex/reembed/delete/semantic_* 为预留分发位，
# 归后续段——不认领不误伤：未知类型的任务行原地留 pending）
CLAIMABLE_TASK_TYPES = ("ingest", "maintenance")


@dataclass
class WorkerServices:
    """worker 执行所需服务集（backend 必备；其余按任务类型按需）。

    _gate/_embedder 供子进程写入侧探针（inline 形态可不带——探针随 main()）。
    """

    backend: object
    settings: Settings
    ingest: object | None = None        # run_task(task_id, should_continue=...)
    credentials: object | None = None   # purge_expired()——maintenance 凭证回收
    _gate: object | None = None
    _embedder: object | None = None


class TaskRunner:
    """任务执行循环（认领→心跳→执行→重试；线程安全：多 runner/多线程 kick 并发
    语义由 claim 原子性保证——真实并发窗口下恰好一人认领）。"""

    def __init__(
        self,
        backend,
        settings: Settings,
        *,
        services: WorkerServices | None = None,
        executors: dict[str, object] | None = None,
        worker_id: str | None = None,
        clock=None,
    ) -> None:
        self._backend = backend
        self._settings = settings
        self._services = services or WorkerServices(backend=backend, settings=settings)
        # P2-1（M2.1 R2）：worker_id 每 runner 唯一（pid+uuid）——inline 多执行器
        # 共进程时 owner 校验仍可区分（防丢租约旧执行器覆盖新持有者终态）
        self._worker_id = worker_id or f"wk-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._clock = clock or utc_now_ts
        self._executors: dict[str, object] = {
            "ingest": self._exec_ingest,
            "maintenance": self._exec_maintenance,
        }
        if executors:
            self._executors.update(executors)

    # ---- 对外主口 ----

    def run_once(self, *, task_types=None, created_before=None) -> bool:
        """认领并执行一个任务；无可认领任务 → False（不抛——循环安全）。

        - task_types：认领类型过滤（None = CLAIMABLE_TASK_TYPES 全集）；
        - created_before（P2-7）：仅认领 created_at <= 该时点的「陈旧」任务——
          inline 兜底循环以此认领 ingest（投递方 kick 的同步消化恒先于循环抢到
          新任务，保 M1 上传时序语义；重启遗留/超量滞留任务照常被领）。

        每轮先执行**崩溃耗尽清扫**（P2-2）：租约过期且 attempts ≥ max 的
        leased/running 任务 → failed 留人工（error 落原因），并按 target_version
        落文档侧 pending failed（经 ingest 服务，无版本关联行只落任务行）。
        """
        self._sweep_exhausted()
        try:
            task = self._backend.claim_next_task(
                self._worker_id,
                lease_s=self._settings.worker_lease_s,
                task_types=task_types or CLAIMABLE_TASK_TYPES,
                max_attempts=self._settings.task_max_attempts,
                now=self._clock(),
                created_before=created_before,
            )
        except Exception:  # noqa: BLE001 —— 认领失败（锁竞争等）按无任务处理
            logger.exception("claim_next_task failed——本轮跳过（兜底轮询会再试）")
            return False
        if task is None:
            return False
        self._execute(task)
        return True

    def _sweep_exhausted(self) -> None:
        """P2-2（M2.1 R2）崩溃耗尽清扫：类型过滤无关（每轮先跑——任何认领路径
        都会收口滞留任务）。"""
        try:
            swept = self._backend.fail_exhausted_tasks(
                max_attempts=self._settings.task_max_attempts, now=self._clock()
            )
        except Exception:  # noqa: BLE001 —— 清扫失败不阻断本轮认领
            logger.exception("fail_exhausted_tasks sweep failed")
            return
        for row in swept:
            logger.error(
                "task exhausted after %s attempts (lease expired — worker crash?):"
                " %s → failed 留人工",
                row.get("attempts"), row.get("id"),
            )
            ingest = self._services.ingest
            fail = getattr(ingest, "fail_document_version", None)
            if fail is None:
                continue
            try:
                fail(row, "attempt limit exceeded (worker crash?)")
            except Exception:  # noqa: BLE001 —— 文档侧收尾失败不阻断（任务行已 failed）
                logger.exception("doc-side finalize failed for exhausted task: %s",
                                 row.get("id"))

    # ---- 执行与心跳 ----

    def _execute(self, task: dict) -> None:
        task_id = task["id"]
        token = task_id_var.set(task_id)  # 日志贯通：task_id 进上下文（design §3）
        stop = threading.Event()
        hb = threading.Thread(
            target=self._heartbeat_loop, args=(task_id, stop), daemon=True
        )
        hb.start()
        try:
            executor = self._executors.get(task["type"])
            if executor is None:  # 预留分发位兜底（type 过滤下理论不可达）
                raise RuntimeError(f"no executor for task type: {task['type']!r}")
            executor(task)
        except Exception as exc:  # noqa: BLE001 —— 失败处置（重试预算内回 pending）
            self._on_failure(task, exc)
        finally:
            stop.set()
            hb.join(timeout=self._settings.worker_heartbeat_s + 1.0)
            task_id_var.reset(token)

    def _heartbeat_loop(self, task_id: str, stop: threading.Event) -> None:
        interval = max(self._settings.worker_heartbeat_s, 0.05)
        lease_s = self._settings.worker_lease_s
        while not stop.wait(interval):
            try:
                ok = self._backend.heartbeat_task(
                    task_id, self._worker_id, lease_s=lease_s, now=self._clock()
                )
            except Exception:  # noqa: BLE001 —— 心跳失败不杀执行（下轮再试）
                logger.exception("heartbeat failed: %s", task_id)
                continue
            if not ok:
                # 租约失守（重认领/取消）——停跳；执行线程经 should_continue 探测
                logger.warning("heartbeat lost lease (reclaimed/cancelled?): %s", task_id)
                return

    def _should_continue(self, task_id: str):
        """阶段边界存活检查（run_task.should_continue）：心跳即探测（顺带续租）。"""
        def check() -> bool:
            try:
                return self._backend.heartbeat_task(
                    task_id, self._worker_id,
                    lease_s=self._settings.worker_lease_s, now=self._clock(),
                )
            except Exception:  # noqa: BLE001 —— 探测异常保守视作存活（下轮边界再探）
                logger.exception("liveness probe failed: %s", task_id)
                return True
        return check

    # ---- 内置 executors ----

    def _exec_ingest(self, task: dict) -> None:
        if self._services.ingest is None:
            raise RuntimeError("ingest service not wired in worker services")
        self._services.ingest.run_task(
            task["id"], should_continue=self._should_continue(task["id"])
        )

    def _exec_maintenance(self, task: dict) -> None:
        from knowledge_lattice.worker.maintenance import run_maintenance

        if self._services.credentials is None:
            raise RuntimeError("credentials service not wired in worker services")
        run_maintenance(
            self._backend, self._services.credentials, self._settings, task["id"]
        )

    # ---- 失败处置（重试上限——TC-TASK-02） ----

    def _on_failure(self, task: dict, exc: Exception) -> None:
        """失败处置（重试上限——TC-TASK-02；P2-1 终态所有权守卫，M2.1 R2）。"""
        task_id = task["id"]
        logger.exception("task execution failed: %s", task_id)
        try:
            fresh = self._backend.get_task(task_id)
        except Exception:  # noqa: BLE001
            fresh = None
        if fresh is None:
            return
        # P2-1 守卫 1：已 done（新持有者完成 / 本执行器完成后的迟来异常）不覆盖
        if fresh["status"] == "done":
            logger.warning("failure ignored: task already done: %s", task_id)
            return
        # P2-1 守卫 2：租约已归他人（重认领后的旧执行器迟来失败）不覆盖新持有者
        owner = fresh.get("lease_owner")
        if owner not in (None, self._worker_id):
            logger.warning(
                "failure ignored: lease owned by %r (lost to reclaimer): %s",
                owner, task_id,
            )
            return
        err = fresh.get("error") or ""
        if err.startswith("cancelled:"):
            return  # 取消/版本亡故是吸收态——不可重试（幂等续跑不复活）
        if fresh["status"] != "failed":
            # executor 异常早于其自身终态写入（如认领后即刻崩溃）——兜底落终态
            self._backend.update_task(task_id, status="failed", error=str(exc))
            fresh = self._backend.get_task(task_id) or fresh
        if fresh["attempts"] >= self._settings.task_max_attempts:
            return  # attempts ≥ 3：保持 failed 留人工（error 已落原因）
        logger.warning(
            "task requeued for retry (attempts=%s < %s): %s",
            fresh["attempts"], self._settings.task_max_attempts, task_id,
        )
        self._backend.update_task(task_id, status="pending")


# ============ 子进程形态 ============


class WorkerSupervisor:
    """主进程侧 worker 子进程监管（design §2「主进程 ×1（内含 worker 子进程）」）。

    - 拉起：`python -m knowledge_lattice.worker`（stdin 管道 = IPC 唤醒通道）；
    - 自动拉起（TC-TASK-04）：监控线程发现子进程死亡（OOM 等）→ 记日志 →
      退避后重启（被杀 worker 的在途任务经租约过期重认领续跑——TC-E2E-03）；
    - 唤醒：ParentWake 写 stdin 字节（破裂窗口静默——兜底轮询兜住）；
    - 关停：stop() → 关 stdin → 等待退出（超时 terminate）。

    子进程 settings 经环境变量传递（get_settings）——create_app 侧构造的
    Settings 对象不天然在 env，故 worker 相关字段显式映射注入（见 _worker_env）。
    """

    def __init__(self, settings: Settings, *, restart_backoff_s: float | None = None) -> None:
        self._settings = settings
        self._backoff = restart_backoff_s if restart_backoff_s is not None \
            else settings.worker_restart_backoff_s
        self._proc = None
        self._wake = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            env = dict(os.environ)
            env.update(self._worker_env(self._settings))
            self._proc = subprocess.Popen(
                [sys.executable, "-m", "knowledge_lattice.worker"],
                stdin=subprocess.PIPE, env=env,
            )
            self._wake = None if self._proc.stdin is None else _ParentWakeShim(self._proc)
        logger.info("worker subprocess started: pid=%s", self._proc.pid)

    def notify(self) -> None:
        wake = self._wake
        if wake is not None:
            wake.notify()

    @property
    def proc(self):
        return self._proc

    def start_monitor(self) -> None:
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def _monitor_loop(self) -> None:
        while not self._stop.wait(0.5):
            proc = self._proc
            if proc is not None and proc.poll() is not None:
                logger.error(
                    "worker subprocess died (code=%s)——%ss 后自动拉起"
                    "（在途任务经租约过期重认领，TC-TASK-04/TC-E2E-03）",
                    proc.returncode, self._backoff,
                )
                if self._stop.wait(self._backoff):
                    return
                try:
                    self.start()
                except Exception:  # noqa: BLE001 —— 拉起失败继续监控重试
                    logger.exception("worker restart failed")

    def stop(self, timeout_s: float = 5.0) -> None:
        self._stop.set()
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()  # EOF → 子进程干净退出
        except OSError:
            pass
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()

    @staticmethod
    def _worker_env(settings: Settings) -> dict[str, str]:
        """worker 相关 Settings 字段 → 环境变量（子进程 get_settings 读取）。
        其余 LATTICE_*（embed 网关、日志等）经 os.environ 继承。"""
        return {
            "LATTICE_DATA_DIR": str(settings.data_dir),
            "LATTICE_ENV": settings.environment,
            "LATTICE_EMBED_DIM": str(settings.embed_dim),
            "LATTICE_WORKER_LEASE_S": str(settings.worker_lease_s),
            "LATTICE_WORKER_HEARTBEAT_S": str(settings.worker_heartbeat_s),
            "LATTICE_WORKER_POLL_S": str(settings.worker_poll_s),
            "LATTICE_WORKER_STARTUP_PROBE": "1" if settings.worker_startup_probe else "0",
            "LATTICE_PROBE_INTERVAL_S": str(settings.probe_interval_s),
            "LATTICE_TASK_MAX_ATTEMPTS": str(settings.task_max_attempts),
            "LATTICE_MAINTENANCE_KEEP_DAYS": str(settings.maintenance_keep_days),
            "LATTICE_MAINTENANCE_KEEP_COUNT": str(settings.maintenance_keep_count),
            "LATTICE_TOMBSTONE_KEEP_DAYS": str(settings.tombstone_keep_days),
        }


class _ParentWakeShim:
    """ParentWake 的薄壳（延迟导入 ipc 避免主进程加载 worker 主模块依赖）。"""

    def __init__(self, proc) -> None:
        self._proc = proc
        from knowledge_lattice.worker.ipc import ParentWake

        self._wake = ParentWake(proc)

    def notify(self) -> None:
        self._wake.notify()


def build_default_services(settings: Settings) -> WorkerServices:
    """按 settings 装配 worker 服务集（生产默认）。

    P2-4/P2-5（M2.1 R2）：backend 经共享工厂 `store.factory.build_backend`
    （与 app.create_app 同源——恒 sqlite，LATTICE_PG_DSN 不再触发 worker 侧
    PG 自动分支，杜绝主/子进程跨库 split-brain）；quality 经共享工厂
    `core.docs.quality.build_quality_service`（LLM 兜底按 settings.quality_llm
    选择——与 app 同款，subprocess 部署下不再静默 Noop）。
    """
    from knowledge_lattice.adapters.embedder import EmbeddingGate, OpenAICompatEmbedder
    from knowledge_lattice.core.docs.credentials import CredentialService
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.docs.quality import build_quality_service
    from knowledge_lattice.store.factory import build_backend

    backend = build_backend(settings)  # 心跳线程独立连接（ThreadLocal）
    gate = EmbeddingGate()
    embedder = OpenAICompatEmbedder(settings)
    quality = build_quality_service(backend, settings)
    ingest = IngestService(
        backend, embedder, settings, gate, settings.data_dir / "objects",
        quality=quality,
    )
    credentials = CredentialService(backend, settings, settings.data_dir / "objects")
    return WorkerServices(
        backend=backend, settings=settings, ingest=ingest, credentials=credentials,
        _gate=gate, _embedder=embedder,
    )


def _load_services_factory(spec: str):
    """LATTICE_WORKER_SERVICES=module:attr 扩展点——部署自定义 provider / 测试注入。"""
    module_name, _, attr = spec.partition(":")
    import importlib

    module = importlib.import_module(module_name)
    factory = getattr(module, attr)
    return factory


def main() -> None:
    """子进程入口（`python -m knowledge_lattice.worker`）——装配/日志/探针/双通道循环。"""
    settings = get_settings()
    if settings.worker_mode not in ("inline", "subprocess"):
        raise ValueError(
            f"invalid worker_mode {settings.worker_mode!r}（合法值：inline | subprocess"
            "——fail-closed，不静默回退）"
        )
    setup_logging(settings.log_level, settings.log_format)  # log.py 同套 handler

    factory_spec = os.environ.get("LATTICE_WORKER_SERVICES")
    if factory_spec:
        logger.info("worker services from factory: %s", factory_spec)
        services = _load_services_factory(factory_spec)(settings)
    else:
        services = build_default_services(settings)
    runner = TaskRunner(
        services.backend, settings, services=services,
        worker_id=f"wk-{os.getpid()}",
    )

    # 写入侧探针（TC-EMB-03 拒绝档——embed 阶段 gate.ensure_writable 消费）：
    # 启动一次（worker_startup_probe=False 可关——测试注入 fake 栈时用）+
    # 周期档（与主进程探针各自独立——进程隔离后内存 gate 不共享）
    if settings.worker_startup_probe:
        _run_probe(services)
    probe_stop = threading.Event()

    def _probe_loop() -> None:
        if settings.probe_interval_s <= 0:
            return
        while not probe_stop.wait(settings.probe_interval_s):
            _run_probe(services)

    threading.Thread(target=_probe_loop, daemon=True).start()

    from knowledge_lattice.worker.ipc import StdinWake, _ParentGone

    wake = StdinWake()
    logger.info(
        "worker started: pid=%s mode=subprocess lease=%.0fs heartbeat=%.0fs poll=%.0fs",
        os.getpid(), settings.worker_lease_s, settings.worker_heartbeat_s,
        settings.worker_poll_s,
    )
    try:
        while True:
            try:
                if runner.run_once():
                    continue  # 队列可能还有任务——立即再认领
            except Exception:  # noqa: BLE001 —— run_once 自身不抛，此处防御
                logger.exception("worker loop iteration failed")
            # 空闲：等 IPC 唤醒字节，超时即兜底轮询周期（双通道，design §2）；
            # stdin EOF（_ParentGone）向上传播 → 干净退出
            wake.wait(settings.worker_poll_s)
    except _ParentGone:
        logger.info("worker exiting: parent gone (stdin EOF)")
        raise SystemExit(0)
    finally:
        probe_stop.set()


def _run_probe(services: WorkerServices) -> None:
    """写入侧指纹探针（gate 进程内状态——子进程形态独立探测，见模块 docstring）。"""
    gate = getattr(services, "_gate", None)
    embedder = getattr(services, "_embedder", None)
    if gate is None or embedder is None:
        return
    try:
        from knowledge_lattice.adapters.embedder import FingerprintProbe

        gate.update(FingerprintProbe(services.backend, embedder, services.settings).probe())
    except Exception:  # noqa: BLE001 —— 探针失败不阻断 worker（M1 同款降级语义）
        logger.exception("worker fingerprint probe failed")


if __name__ == "__main__":
    main()
