"""FastAPI 入口（design §3）：装配路由 / MCP / DB / 静态页壳 + 启动与周期指纹探针。

组装：
- backend：连接工厂 + 迁移（引导连接跑一次）→ ThreadLocalBackend（每线程一连接，§2）；
- embedder：OpenAI 兼容客户端（测试可注入 fake）；gate：探针结果进程内状态；
- reranker/enhancer/breakers（M1-1 检索配方）：按 config 档位构造（none=显式
  降级路径）+ 查询侧熔断共享态（NFR-8）；
- MCP：FastMCP 单一 server（docs 组 search），http_app 挂载在根（/mcp 路径）、
  lifespan 由本 app 接管（StreamableHTTPSessionManager 初始化——fastmcp ASGI 集成）；
- 静态页壳：GET / 返回 index.html、/static/* 托管 web/（无构建工具——§5.7）；
- POST /api/dev/token 仅 dev/test 注册（生产 404——TC-AUTH-01④）。
"""

from __future__ import annotations

import asyncio
import logging
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
from knowledge_lattice.core.docs.quality import (
    NoopKeywordGenerator,
    QualityService,
)
from knowledge_lattice.domain.auth import AuthError, OrgContextError
from knowledge_lattice.mcp.server import build_mcp_server
from knowledge_lattice.store.sqlite import connect, migrate_db
from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"


class ServiceContext:
    """依赖容器（backend/settings/gate/ingest/credentials/quality/embedder/reranker/enhancer/breakers）。"""

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
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    bootstrap_conn = connect(settings.db_path)
    migrate_db(bootstrap_conn)
    bootstrap_conn.close()
    backend = ThreadLocalBackend(settings.db_path)

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
    # LLM 兜底 provider（quality_llm=none 默认 noop——不发网关调用；D12 同款形态）
    from knowledge_lattice.adapters.enhancer import OpenAICompatKeywordGenerator

    quality = QualityService(
        backend, settings,
        keyword_client=(
            NoopKeywordGenerator() if settings.quality_llm == "none"
            else OpenAICompatKeywordGenerator(settings)
        ),
    )
    ingest = IngestService(
        backend, embedder, settings, gate, settings.data_dir / "objects",
        quality=quality,
    )
    service = ServiceContext(
        settings=settings, backend=backend, gate=gate, ingest=ingest,
        credentials=credentials, quality=quality, embedder=embedder,
        reranker=reranker, enhancer=enhancer, breakers=breakers,
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

    # ---- 内嵌调度器：周期投递 maintenance 任务（design §3 v0.8.3——M1-3 落
    #      「未消费凭证回收」一项；子进程 worker 随 M2，当前主进程内执行） ----

    def _run_maintenance_once() -> None:
        task_id = backend.create_task(None, task_type="maintenance")
        try:
            backend.update_task(task_id, status="running")
            stats = credentials.purge_expired()
            backend.update_task(task_id, status="done")
            logger.info("maintenance done: %s", stats)
        except Exception as exc:  # noqa: BLE001 —— 任务级失败落 failed+error
            backend.update_task(task_id, status="failed", error=str(exc))
            raise

    async def _periodic_maintenance() -> None:
        while True:
            await asyncio.sleep(settings.maintenance_interval_s)
            try:
                await asyncio.to_thread(_run_maintenance_once)
            except Exception:  # noqa: BLE001 —— 周期任务失败不杀循环
                logger.exception("periodic maintenance failed")

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
        try:
            async with mcp_app.lifespan(mcp_app):  # MCP session manager 交给父 app
                yield
        finally:
            for task in (probe_task, maintenance_task):
                if task is not None:
                    task.cancel()

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

    from knowledge_lattice.api import admin, documents, quality, search, tasks, upload

    app.include_router(upload.router)
    app.include_router(documents.router)
    app.include_router(tasks.router)
    app.include_router(search.router)
    app.include_router(quality.router)  # 区分度环（M1-4——报告/PATCH/抽查）
    app.include_router(admin.router)  # dimensions/datasets 等普通端点——不受环境门控（P2-4）
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
