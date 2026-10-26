"""全部配置（design §3：模型版本、阈值、路径、网关地址；日志级别/格式——v0.8.5）。

M0a-1 骨架：连接工厂所需路径/PRAGMA 常量 + 嵌入四件套占位（D12）+ 日志配置；
模型网关地址、超时熔断（NFR-8）、指纹阈值等随 M0a-2/M1 摄取与检索链扩充。
环境变量覆盖（LATTICE_ 前缀）仅供开发/测试，生产配置级切换。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    environment: str = "dev"  # dev | test | prod（POST /api/dev/token 仅 dev/test 注册——TC-AUTH-01）
    data_dir: Path = Path("data")

    # 连接纪律（design §3 连接工厂；值与 store/sqlite/connection.py 一致）
    journal_mode: str = "wal"
    busy_timeout_ms: int = 5000
    synchronous: str = "NORMAL"

    # 嵌入四件套（D12——OpenAI 兼容 API；标签 model:dim 兼作向量召回查询谓词）
    embed_provider: str = "openai"
    embed_model: str = "qwen3-embedding-4b"
    embed_dim: int = 2560
    # OpenAI 兼容端点（内部网关；本地 ollama /v1 仅作开发/测试端点——design §7）
    embed_api_base: str = "http://127.0.0.1:11434/v1"
    embed_api_key: str = "local-dev"
    embed_timeout_s: float = 30.0
    embed_batch_size: int = 64
    # 指纹探针两档阈值（G-8 临时值，M1 校准）：min 余弦 <0.99 告警 / <0.95 拒绝写入
    probe_warn_threshold: float = 0.99
    probe_reject_threshold: float = 0.95
    probe_interval_s: float = 600.0  # 周期探测（运行中换底模可发现）
    # 重排：none＝显式降级路径（网关 Cohere 风格 /rerank——待决-5 已关闭、G-7 闭环）
    reranker: str = "none"
    # rerank 配方参数（NFR-8：候选 32 / 输入截断 256 token / 超时 1000ms 硬上限；
    # 截断开关缺省关（None）——P95 超时降级档才开 256（TC-RET-06 双降级开关）
    rerank_candidates: int = 32
    rerank_truncate_tokens: int | None = None
    rerank_timeout_s: float = 1.0
    rerank_max_concurrency: int = 4  # rerank API 并发信号量上限（§5.2；数值申报 M1-4 标定）
    rerank_api_base: str = "http://127.0.0.1:11434/v1"
    rerank_api_key: str = "local-dev"
    rerank_model: str = "qwen3-reranker-8b"
    # 查询侧嵌入超时（NFR-8 v0.8：query 嵌入超时 500ms——单次请求硬上限，
    # 摄取侧 embed_timeout_s=30s 不受影响）
    query_embed_timeout_s: float = 0.5
    # LLM 关键词增强（§5.2：800ms 硬预算并行；none＝不用增强路）
    enhancer: str = "none"
    enhance_budget_s: float = 0.8
    enhance_api_base: str = "http://127.0.0.1:11434/v1"
    enhance_api_key: str = "local-dev"
    enhance_model: str = "qwen3-llm"
    # 融合与召回窗口（design §5.2：RRF k=60；NFR-8 参考口径 knn 1024 / rerank 候选 32）
    rrf_k: int = 60
    recall_window: int = 1024
    # 归一后分数阈值（§5.2「阈值只作用于归一后的最终分」；0=不过滤——数值 M1-4 黄金集校准）
    score_threshold: float = 0.0
    # 熔断（NFR-8 v0.8：连续 3 次失败断开 60s、半开探测恢复）
    breaker_failures: int = 3
    breaker_cooldown_s: float = 60.0

    # 区分度反馈环（design §5.4 / FR-3——M1-4；阈值均为**绝对阈值初值**，
    # 真实语料重标定随 M1-5 校准实验——口径申报见交付报告）
    quality_neighbors: int = 8              # 拥挤近邻 top-k（§5.4「top-8」）
    quality_crowding_threshold: float = 0.92  # mean(top-k 余弦) > 阈值 → 拥挤（初值）
    quality_low_idf_threshold: float = 3.0  # token 平均 IDF < 阈值 → 词面通用（初值，nats）
    quality_cold_start_min: int = 10        # 组织在用块数低于此 → 冷启动引用全局语料 IDF
    quality_rescale_ratio: float = 0.5      # detected_at_scale < 当前规模×比例 → 重算
    quality_sample_percent: int = 10        # 周期抽样重算比例（%，rid 确定性散列抽样）
    # LLM 兜底（TC-QUAL-03）：none＝不用（默认——兜底是增益路非可用性前提）；
    # openai＝内部网关 chat completions（adapters/enhancer 同款形态）
    quality_llm: str = "none"
    quality_llm_api_base: str = "http://127.0.0.1:11434/v1"
    quality_llm_api_key: str = "local-dev"
    quality_llm_model: str = "qwen3-llm"
    quality_llm_timeout_s: float = 10.0

    # 服务壳（M0a-3）
    dev_jwt_secret: str = "dev-only-insecure-secret-0123456789ab"  # 仅 dev/test 签发（生产另配，D18）
    jwt_ttl_s: float = 12 * 3600.0
    mcp_timeout_s: float = 60.0  # MCP 60s 超时中间件（ragflow 纪律）

    # 上传凭证（M1-3 三步式——P3-10/P3-13 择型：TTL 15min、全局上限 200MB 均可配置）
    upload_credential_ttl_s: float = 900.0  # 凭证有效期（签发 → expires_at）
    upload_max_bytes: int = 200 * 1024 * 1024  # 全局上限（PUT 独立生效——413，P3-13）
    maintenance_interval_s: float = 300.0  # 调度器周期投递 maintenance 任务（0=关闭）

    # 运行日志（v0.8.5：结构化 JSON→stdout；本地开发可切人读格式）
    log_level: str = "INFO"
    log_format: str = "json"  # json | human

    @property
    def db_path(self) -> Path:
        return self.data_dir / "lattice.db"

    @property
    def embed_model_label(self) -> str:
        """模型标签 model:dim——写入 chunks.embed_model 兼作查询谓词（D12）。"""
        return f"{self.embed_model}:{self.embed_dim}"


def get_settings() -> Settings:
    """读取配置（LATTICE_* 环境变量覆盖默认值）。"""
    env = os.environ.get

    def _f(name: str, default: str) -> str:
        return env(name, default)

    def _num(name: str, default: float | int) -> float | int:
        raw = env(name)
        return type(default)(raw) if raw is not None else default

    return Settings(
        environment=env("LATTICE_ENV", "dev"),
        data_dir=Path(env("LATTICE_DATA_DIR", "data")),
        embed_api_base=_f("LATTICE_EMBED_API_BASE", "http://127.0.0.1:11434/v1"),
        embed_api_key=_f("LATTICE_EMBED_API_KEY", "local-dev"),
        embed_timeout_s=float(_num("LATTICE_EMBED_TIMEOUT_S", 30.0)),
        probe_warn_threshold=float(_num("LATTICE_PROBE_WARN", 0.99)),
        probe_reject_threshold=float(_num("LATTICE_PROBE_REJECT", 0.95)),
        probe_interval_s=float(_num("LATTICE_PROBE_INTERVAL_S", 600.0)),
        reranker=_f("LATTICE_RERANKER", "none"),
        rerank_candidates=int(_num("LATTICE_RERANK_CANDIDATES", 32)),
        rerank_timeout_s=float(_num("LATTICE_RERANK_TIMEOUT_S", 1.0)),
        rerank_max_concurrency=int(_num("LATTICE_RERANK_MAX_CONCURRENCY", 4)),
        query_embed_timeout_s=float(_num("LATTICE_QUERY_EMBED_TIMEOUT_S", 0.5)),
        enhancer=_f("LATTICE_ENHANCER", "none"),
        enhance_budget_s=float(_num("LATTICE_ENHANCE_BUDGET_S", 0.8)),
        rrf_k=int(_num("LATTICE_RRF_K", 60)),
        score_threshold=float(_num("LATTICE_SCORE_THRESHOLD", 0.0)),
        dev_jwt_secret=_f("LATTICE_DEV_JWT_SECRET", "dev-only-insecure-secret-0123456789ab"),
        mcp_timeout_s=float(_num("LATTICE_MCP_TIMEOUT_S", 60.0)),
        upload_credential_ttl_s=float(_num("LATTICE_UPLOAD_TTL_S", 900.0)),
        upload_max_bytes=int(_num("LATTICE_UPLOAD_MAX_BYTES", 200 * 1024 * 1024)),
        maintenance_interval_s=float(_num("LATTICE_MAINTENANCE_INTERVAL_S", 300.0)),
        log_level=env("LATTICE_LOG_LEVEL", "INFO"),
        log_format=env("LATTICE_LOG_FORMAT", "json"),
    )
