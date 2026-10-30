"""FastAPI 入口（design §3）：装配路由 / MCP / DB / 静态页壳 + 启动与周期指纹探针。

组装：
- backend：连接工厂 + 迁移（引导连接跑一次）→ ThreadLocalBackend（每线程一连接，§2）；
- embedder：OpenAI 兼容客户端（测试可注入 fake）；gate：探针结果进程内状态；
- reranker/enhancer/breakers（M1-1 检索配方）：按 config 档位构造（none=显式
  降级路径）+ 查询侧熔断共享态（NFR-8）；
- worker（M2.1）：任务执行迁入 worker 框架——settings.worker_mode 二选一：
  `subprocess`（生产 §2 部署形态：WorkerSupervisor 拉起 `python -m
  knowledge_lattice.worker` 子进程，IPC 唤醒 + 兜底轮询，OOM 只杀子进程 +
  自动拉起）/ `inline`（进程内 TaskRunner 同一执行体——测试与最小部署捷径）；
  upload / MCP upload / maintenance 调度器只投递任务行 + kick，不再进程内直跑；
- maintenance 调度器（§3 v0.8.3）：周期投递 maintenance 任务行（执行体进 worker
  ——三任务体 + 保留策略见 worker/maintenance.py）；
- MCP：FastMCP 单一 server（docs 组 search），http_app 挂载在根（/mcp 路径）、
  lifespan 由本 app 接管（StreamableHTTPSessionManager 初始化——fastmcp ASGI 集成）；
- 静态页壳：GET / 返回 index.html、/static/* 托管 web/（无构建工具——§5.7）；
- POST /api/dev/token 仅 dev/test 注册（生产 404——TC-AUTH-01④）。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from knowledge_lattice.adapters.embedder import (
    EmbeddingGate,
    FingerprintProbe,
    OpenAICompatEmbedder,
)
from knowledge_lattice.config import Settings, get_settings
from knowledge_lattice.core.docs.acl import AclDeniedError
from knowledge_lattice.core.docs.credentials import CredentialError, CredentialService
from knowledge_lattice.core.docs.ingest import IngestService
from knowledge_lattice.domain.auth import AuthError, OrgContextError
from knowledge_lattice.mcp.server import build_mcp_server

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"


class ServiceContext:
    """依赖容器（backend/settings/gate/ingest/credentials/quality/embedder/reranker/enhancer/breakers/worker）。"""

    def __init__(
        self,
        *,
        settings,
        backend,
        gate,
        ingest,
        credentials,
        quality,
        embedder,
        reranker=None,
        enhancer=None,
        breakers=None,
        worker=None,
    ) -> None:
        self.settings = settings
        self.backend = backend
        self.gate = gate
        self.ingest = ingest
        self.credentials = credentials
        self.quality = quality
        self.embedder = embedder
        self.reranker = reranker
        self.enhancer = enhancer
        self.breakers = breakers
        self.worker = worker


class InlineWorkerHandle:
    """inline 模式 worker 句柄（app 侧投递口 → TaskRunner）：

    - kick()：同步消化任务队列（upload 响应后的 BackgroundTask / MCP 上传线程
      调用——保持 M1「响应返回前摄取已推进」的时序语义；重试回队随 attempts
      上限天然收敛）；
    - wake()：仅唤醒兜底循环（maintenance 调度器投递后调用——异步领取）；
    - 兜底循环线程（P2-7，M2.1 R2）：全类型认领——maintenance / semantic_sync /
      semantic_build（m2s-2）即时领（调度器与手动触发 wake 后低延迟领取；
      semantic_* 不设陈旧口径——kick 唤醒丢失时的兜底通道，P2-2/R2）+ ingest
      以「陈旧任务」口径领
      （created_at ≤ now−poll_s：重启遗留/超量滞留/租约过期的 ingest 任务在
      poll 周期内被领，与 subprocess 主循环语义一致）；新鲜 ingest 恒由投递方
      kick 的同步消化先抢到（claim 原子性 + 陈旧过滤——上传时序语义无竞态）。
      空闲轮询（worker_poll_s）+ 事件唤醒（IPC 双通道的进程内等价形态）。
    """

    def __init__(self, runner, *, poll_s: float, max_drain: int = 1024) -> None:
        self._runner = runner
        self._poll_s = poll_s
        self._max_drain = max_drain
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def kick(self) -> None:
        """同步消化任务队列（投递方调用）：反复认领执行至队列空——重试回队（attempts
        有界）也被本轮消化；保持 M1「响应返回前摄取已推进」的时序语义。"""
        self._wake.set()
        try:
            for _ in range(self._max_drain):  # 有界防护（attempts 上限天然收敛）
                if not self._runner.run_once():
                    break
        except Exception:  # noqa: BLE001 —— run_once 不抛；防御
            logger.exception("inline worker kick failed")

    def wake(self) -> None:
        self._wake.set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _aged_before(self) -> str:
        """ingest 陈旧口径时点：now − poll_s（claim 的 created_before 参数）。"""
        from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

        return add_seconds(utc_now_ts(), -max(self._poll_s, 0.0))

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                # ① maintenance 即时认领（调度器 wake 后毫秒级领取）
                if self._runner.run_once(task_types=("maintenance",)):
                    continue
                # ② semantic_sync / semantic_build 即时认领（P2-2/R2：手动触发/
                #    同步后自动投递的构建任务不设陈旧口径——kick 唤醒丢失（outbox
                #    抛错/进程间崩溃）时的兜底通道，防任务永久滞留 pending；
                #    m2s-1 P2-2 教训：新任务类型必进本循环）
                if self._runner.run_once(task_types=("semantic_sync",)):
                    continue
                if self._runner.run_once(task_types=("semantic_build",)):
                    continue
                # ③ ingest 陈旧认领（P2-7：重启遗留/超量滞留/租约过期——poll 内收口；
                #    新鲜 ingest 恒由投递方 kick 同步消化先抢，保上传时序语义）
                if self._runner.run_once(
                    task_types=("ingest",), created_before=self._aged_before()
                ):
                    continue
            except Exception:  # noqa: BLE001
                logger.exception("inline worker loop failed")
            self._wake.wait(self._poll_s)
            self._wake.clear()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)


class SubprocessWorkerHandle:
    """subprocess 模式 worker 句柄：kick/wake 同为 stdin 唤醒字节（worker 侧
    双通道循环领取；supervisor 监控死亡自动拉起——TC-TASK-04）。"""

    def __init__(self, supervisor) -> None:
        self._supervisor = supervisor

    def kick(self) -> None:
        self._supervisor.notify()

    def wake(self) -> None:
        self._supervisor.notify()

    def start(self) -> None:
        self._supervisor.start()
        self._supervisor.start_monitor()

    def stop(self) -> None:
        self._supervisor.stop()


def create_app(
    settings: Settings | None = None,
    *,
    embedder=None,
    gate: EmbeddingGate | None = None,
    reranker=None,
    enhancer=None,
    run_startup_probe: bool = True,
) -> FastAPI:
    """构建 FastAPI 应用（测试可注入 embedder/gate/reranker/enhancer、跳过启动探针）。"""
    settings = settings or get_settings()
    if settings.worker_mode not in ("inline", "subprocess"):
        raise ValueError(
            f"invalid worker_mode {settings.worker_mode!r}（合法值：inline | subprocess"
            "——fail-closed，不静默回退）"
        )
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    # P2-4/P2-5（M2.1 R2）：backend/quality 经共享工厂装配——与 worker 子进程
    # build_default_services 同源（杜绝主/子进程装配分叉）
    from knowledge_lattice.core.docs.quality import build_quality_service
    from knowledge_lattice.store.factory import build_backend

    backend = build_backend(settings)

    gate = gate or EmbeddingGate()
    embedder = embedder or OpenAICompatEmbedder(settings)
    # 检索配方 providers（M1-1）：reranker/enhancer 按 config 档位构造（none=降级
    # 路径）；查询侧熔断器共享态（NFR-8：连续 3 失败断开 60s、半开恢复）
    from knowledge_lattice.adapters.breaker import CircuitBreaker
    from knowledge_lattice.adapters.enhancer import NoopEnhancer, OpenAICompatEnhancer
    from knowledge_lattice.adapters.reranker import CohereCompatReranker, NoopReranker

    if reranker is None:
        reranker = (
            NoopReranker() if settings.reranker == "none"
            else CohereCompatReranker(settings)
        )
    if enhancer is None:
        enhancer = (
            NoopEnhancer() if settings.enhancer == "none"
            else OpenAICompatEnhancer(settings)
        )
    breakers = {
        "embed": CircuitBreaker(
            failures=settings.breaker_failures, cooldown_s=settings.breaker_cooldown_s
        ),
        "rerank": CircuitBreaker(
            failures=settings.breaker_failures, cooldown_s=settings.breaker_cooldown_s
        ),
    }
    credentials = CredentialService(backend, settings, settings.data_dir / "objects")
    # LLM 兜底 provider 经共享工厂（quality_llm=none 默认 noop——不发网关调用）
    quality = build_quality_service(backend, settings)
    ingest = IngestService(
        backend, embedder, settings, gate, settings.data_dir / "objects",
        quality=quality,
    )

    # ---- worker 框架（M2.1）与 maintenance 调度器（design §3 v0.8.3） ----
    #      投递侧统一形态：写任务行 + kick worker（执行体在 worker——inline 为
    #      TaskRunner、subprocess 为子进程；主进程不再进程内直跑任务）

    if settings.worker_mode == "subprocess":
        from knowledge_lattice.worker.runner import WorkerSupervisor

        supervisor = WorkerSupervisor(settings)
        worker_handle = SubprocessWorkerHandle(supervisor)
    else:
        from knowledge_lattice.worker.runner import TaskRunner, WorkerServices

        runner = TaskRunner(
            backend, settings,
            services=WorkerServices(
                backend=backend, settings=settings, ingest=ingest,
                credentials=credentials,
            ),
        )
        worker_handle = InlineWorkerHandle(runner, poll_s=settings.worker_poll_s)

    service = ServiceContext(
        settings=settings, backend=backend, gate=gate, ingest=ingest,
        credentials=credentials, quality=quality, embedder=embedder,
        reranker=reranker, enhancer=enhancer, breakers=breakers,
        worker=worker_handle,
    )

    mcp_server = build_mcp_server(service, settings)
    mcp_app = mcp_server.http_app(path="/mcp")

    async def _periodic_probe() -> None:
        while True:
            await asyncio.sleep(settings.probe_interval_s)
            try:
                probe = FingerprintProbe(backend, embedder, settings)
                # P2-6：探针内为同步 httpx（30s 超时）+SQLite 读写——to_thread 下放
                # 线程池执行，绝不阻塞事件循环（§2；ThreadLocalBackend 线程本地连接兼容）
                gate.update(await asyncio.to_thread(probe.probe))
            except Exception:  # noqa: BLE001 —— 周期探针失败不杀任务
                logger.exception("periodic fingerprint probe failed")

    def _enqueue_maintenance() -> None:
        backend.create_task(None, task_type="maintenance")
        worker_handle.wake()

    async def _periodic_maintenance() -> None:
        while True:
            await asyncio.sleep(settings.maintenance_interval_s)
            try:
                await asyncio.to_thread(_enqueue_maintenance)
            except Exception:  # noqa: BLE001 —— 周期投递失败不杀循环
                logger.exception("periodic maintenance enqueue failed")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        probe_task: asyncio.Task | None = None
        maintenance_task: asyncio.Task | None = None
        if run_startup_probe:
            try:  # 启动探针（首部署建档放行 / 两档判定——TC-EMB-03）；to_thread 防阻塞
                probe = FingerprintProbe(backend, embedder, settings)
                result = await asyncio.to_thread(probe.probe)
                gate.update(result)
                logger.info("startup fingerprint probe: %s", result)
            except Exception:  # noqa: BLE001 —— 网关不可达等：不阻断启动（降级语义随 M1）
                logger.exception("startup fingerprint probe failed")
        if settings.probe_interval_s > 0:
            probe_task = asyncio.create_task(_periodic_probe())
        if settings.maintenance_interval_s > 0:
            maintenance_task = asyncio.create_task(_periodic_maintenance())
        worker_handle.start()  # worker：inline 兜底循环 / subprocess 子进程 + 监控
        app.state.worker = worker_handle
        try:
            async with mcp_app.lifespan(mcp_app):  # MCP session manager 交给父 app
                yield
        finally:
            for task in (probe_task, maintenance_task):
                if task is not None:
                    task.cancel()
            worker_handle.stop()

    app = FastAPI(title="knowledge-lattice", lifespan=lifespan)
    app.state.service = service

    # 异常 → HTTP 语义（域异常统一映射；MCP 侧以 ToolError 透出同语义文本）
    @app.exception_handler(AuthError)
    async def _auth_error(_: Request, exc: AuthError):
        return JSONResponse({"error": str(exc)}, status_code=exc.code)

    @app.exception_handler(AclDeniedError)
    async def _acl_error(_: Request, exc: AclDeniedError):
        # body.code 机器码（T12 一致性——membership_denied 类，M1-4 收口）
        return JSONResponse(
            {"error": str(exc), "code": exc.code}, status_code=403
        )

    @app.exception_handler(OrgContextError)
    async def _org_error(_: Request, exc: OrgContextError):
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(CredentialError)  # M1-3：凭证链错误码映射（T12 明确错误码）
    async def _credential_error(_: Request, exc: CredentialError):
        return JSONResponse(
            {"error": str(exc), "code": exc.code}, status_code=exc.http_status
        )

    from knowledge_lattice.api import admin, documents, quality, search, semantic, tasks, upload

    app.include_router(upload.router)
    app.include_router(documents.router)
    app.include_router(tasks.router)
    app.include_router(search.router)
    app.include_router(quality.router)  # 区分度环（M1-4——报告/PATCH/抽查）
    app.include_router(admin.router)  # dimensions/datasets 等普通端点——不受环境门控（P2-4）
    app.include_router(semantic.router)  # 语义层同步（M2-S1——semantic:admin 门控）
    if settings.environment in ("dev", "test"):  # dev token 仅 dev/test（生产 404——D18/P2-4）
        app.include_router(admin.dev_token_router)

    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

    # MCP 挂最后（path="/mcp" 由内层 app 处理；未匹配路径落入其 404）
    app.mount("/", mcp_app)
    return app
