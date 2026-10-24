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

    # 服务壳（M0a-3）
    dev_jwt_secret: str = "dev-only-insecure-secret-0123456789ab"  # 仅 dev/test 签发（生产另配，D18）
    jwt_ttl_s: float = 12 * 3600.0
    mcp_timeout_s: float = 60.0  # MCP 60s 超时中间件（ragflow 纪律）

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
        dev_jwt_secret=_f("LATTICE_DEV_JWT_SECRET", "dev-only-insecure-secret-0123456789ab"),
        mcp_timeout_s=float(_num("LATTICE_MCP_TIMEOUT_S", 60.0)),
        log_level=env("LATTICE_LOG_LEVEL", "INFO"),
        log_format=env("LATTICE_LOG_FORMAT", "json"),
    )
