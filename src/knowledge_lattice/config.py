"""全部配置（design §3：模型版本、阈值、路径、网关地址；日志级别/格式——v0.8.5）。

M0a-1 骨架：连接工厂所需路径/PRAGMA 常量 + 嵌入四件套占位（D12）+ 日志配置；
模型网关地址、超时熔断（NFR-8）、指纹阈值等随 M0a-2/M1 摄取与检索链扩充。
环境变量覆盖（LATTICE_ 前缀）仅供开发/测试，生产配置级切换。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# ---- worker 模式枚举（M2.4 m2-2 必做 3：两处字面量收敛——dataclass 默认与
# get_settings env fallback 同源，防同类漂移〔m2-1 R3 P2-A 半完成状态的收口〕） ----
WORKER_MODE_INLINE = "inline"        # 进程内 TaskRunner（测试/最小部署显式选项）
WORKER_MODE_SUBPROCESS = "subprocess"  # 子进程隔离（默认——M2.1 R2 裁定 A(a)）
WORKER_MODES = (WORKER_MODE_INLINE, WORKER_MODE_SUBPROCESS)


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

    # worker 任务框架（M2.1——design §5.3 任务状态机/心跳/租约/重试 + §2 部署形态）
    # 默认 subprocess（M2.1 R2 边界裁定 A(a)：生产 fail-safe——OOM 只杀 worker 子
    # 进程 + 自动拉起，NFR-1/§2「主进程 ×1（内含 worker 子进程）」默认成立；
    # 测试/最小部署显式 inline——进程内同一 TaskRunner 执行体）
    # 常量收敛（M2.4 m2-2 必做 3）：默认值引用模块级常量（下方 get_settings
    # env fallback 同源——m2-1 R3 移交项 P3-N10 附带收口）
    worker_mode: str = WORKER_MODE_SUBPROCESS  # inline=进程内 | subprocess=子进程隔离（§2）
    worker_heartbeat_s: float = 5.0  # running 任务心跳周期（heartbeat_at/lease_until 刷新）
    worker_lease_s: float = 60.0  # 租约时长（过期任务可被重认领——worker 崩溃不丢任务）
    worker_poll_s: float = 5.0  # 兜底轮询周期（IPC 唤醒之外的第二通道）
    worker_startup_probe: bool = True  # worker 子进程启动指纹探针（写入侧 gate——TC-EMB-03 拒绝档）
    worker_restart_backoff_s: float = 1.0  # 子进程死亡后自动拉起的退避
    task_max_attempts: int = 3  # 重试上限（attempts ≥ 3 转 failed 留人工——TC-TASK-02）
    # maintenance 任务行保留策略（m1-3 P3-19——done/failed 行不无限累积）
    maintenance_keep_days: int = 7
    maintenance_keep_count: int = 500
    tombstone_keep_days: int = 90  # tombstone 块物理清理窗口（design §4 chunks 行注释）
    # 审计月库（M2.4 m2-2——TC-OPS-02）：保留期（月）与备份节流
    audit_keep_months: int = 12  # 保留 12 个月（13 个月前整文件/分区删除——FR-6）
    backup_interval_s: float = 86400.0  # 快照最小间隔（RPO ≤24h 口径；0=每轮 maintenance 都跑）

    # 语义层同步（M2-S1——design §5.8；D23 语义轨道）
    semantic_sources_json: str = ""  # per-org 源连接 JSON：{org: {adapter: {endpoint, api_key, timeout_s}}}（#37 前置条件③——部署时配置、重启生效）
    semantic_delete_guard: float = 0.20  # 删除比例保护阈值（快照相对库内该来源 active 实体消失比例 > 阈值 → aborted_guard 零写入——T-S2）
    semantic_grace_days: int = 7  # missing 宽限期（天）——超期转 retired 且关系一并 retired（T-S4）
    semantic_batch_rows: int = 1000  # 同步分批行数上限（每批提交——NFR-11 写锁治理）
    semantic_dim_alert_baseline: float = 0.8  # 维度填充率骤降告警：库内基线携带率 ≥ 此值才参与判定（口径注记见 core/semantic/sync.py）
    semantic_dim_alert_drop: float = 0.5  # 快照携带率 < 基线 × 此值 → 告警（防缺值静默变宽——TC-SYNC-06②）
    semantic_night_window: str = ""  # 错峰窗口（如 "01:00-05:00"——m2s-4 起对每日兜底调度生效：窗口外不投递；分批即天然限速）
    semantic_describe_cache_s: float = 300.0  # describe_table 透传缓存 TTL（T-S11④：5min；0=关缓存——m2s-2）
    semantic_l0_token_budget: int = 1500  # L0 总 token 预算（§5.8 l0 行——CI 拦截阈值；TC-YAML-04）
    semantic_daily_sync_interval_s: float = 86400.0  # G-19 五源每日兜底：距上次成功 run 超过该间隔才投递（0=关闭；webhook/手动触发的成功 run 同口径去重）
    semantic_eval_golden_path: str = "eval/semantic_golden.jsonl"  # 识别评测黄金集路径（TC-SEV-01——相对进程 CWD；文件缺失 → 构建评测 skipped 不拦截）
    # semantic_batch_rows 上界 1000 = design §5.8「每批 ≤1000 行提交」硬约束
    # （NFR-11 写锁治理）——校验收口（P3-5/R2），不可配置突破

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

    @property
    def semantic_sources(self) -> dict[str, dict[str, dict]]:
        """per-org 源系统连接（JSON 解析——畸形配置 fail-closed，TC-SYNC-01）。"""
        import json

        if not self.semantic_sources_json:
            return {}
        parsed = json.loads(self.semantic_sources_json)
        if not isinstance(parsed, dict):
            raise ValueError(
                "LATTICE_SEM_SOURCES_JSON 必须是 {org: {adapter: {...}}} JSON 对象"
            )
        return parsed


def get_settings() -> Settings:
    """读取配置（LATTICE_* 环境变量覆盖默认值）。

    数值校验（P3-N10，m2-1 移交→m2-2 顺手清偿）：任务框架数值配置负值/
    非法 worker_mode 即刻 raise（fail-closed——不带着自相矛盾的配置起服务）。
    """
    env = os.environ.get

    def _f(name: str, default: str) -> str:
        return env(name, default)

    def _num(name: str, default: float | int) -> float | int:
        raw = env(name)
        return type(default)(raw) if raw is not None else default

    settings = Settings(
        environment=env("LATTICE_ENV", "dev"),
        data_dir=Path(env("LATTICE_DATA_DIR", "data")),
        embed_dim=int(_num("LATTICE_EMBED_DIM", 2560)),
        # P3-13/R2：_worker_env 映射的三字段在此**读取**——env→get_settings 往返
        # 闭环（否则子进程映射了也不读，N12「防子进程漂移」不成立）
        embed_model=_f("LATTICE_EMBED_MODEL", "qwen3-embedding-4b"),
        embed_batch_size=int(_num("LATTICE_EMBED_BATCH_SIZE", 64)),
        quality_llm=_f("LATTICE_QUALITY_LLM", "none"),
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
        worker_mode=env("LATTICE_WORKER_MODE", WORKER_MODE_SUBPROCESS),
        worker_heartbeat_s=float(_num("LATTICE_WORKER_HEARTBEAT_S", 5.0)),
        worker_lease_s=float(_num("LATTICE_WORKER_LEASE_S", 60.0)),
        worker_poll_s=float(_num("LATTICE_WORKER_POLL_S", 5.0)),
        worker_startup_probe=env("LATTICE_WORKER_STARTUP_PROBE", "1") not in ("0", "false", "no"),
        worker_restart_backoff_s=float(_num("LATTICE_WORKER_RESTART_BACKOFF_S", 1.0)),
        task_max_attempts=int(_num("LATTICE_TASK_MAX_ATTEMPTS", 3)),
        maintenance_keep_days=int(_num("LATTICE_MAINTENANCE_KEEP_DAYS", 7)),
        maintenance_keep_count=int(_num("LATTICE_MAINTENANCE_KEEP_COUNT", 500)),
        tombstone_keep_days=int(_num("LATTICE_TOMBSTONE_KEEP_DAYS", 90)),
        audit_keep_months=int(_num("LATTICE_AUDIT_KEEP_MONTHS", 12)),
        backup_interval_s=float(_num("LATTICE_BACKUP_INTERVAL_S", 86400.0)),
        semantic_sources_json=_f("LATTICE_SEM_SOURCES_JSON", ""),
        semantic_delete_guard=float(_num("LATTICE_SEM_DELETE_GUARD", 0.20)),
        semantic_grace_days=int(_num("LATTICE_SEM_GRACE_DAYS", 7)),
        semantic_batch_rows=int(_num("LATTICE_SEM_BATCH_ROWS", 1000)),
        semantic_dim_alert_baseline=float(_num("LATTICE_SEM_DIM_ALERT_BASELINE", 0.8)),
        semantic_dim_alert_drop=float(_num("LATTICE_SEM_DIM_ALERT_DROP", 0.5)),
        semantic_night_window=_f("LATTICE_SEM_NIGHT_WINDOW", ""),
        semantic_describe_cache_s=float(_num("LATTICE_SEM_DESCRIBE_CACHE_S", 300.0)),
        semantic_l0_token_budget=int(_num("LATTICE_SEM_L0_TOKEN_BUDGET", 1500)),
        semantic_daily_sync_interval_s=float(_num(
            "LATTICE_SEM_DAILY_SYNC_INTERVAL_S", 86400.0)),
        semantic_eval_golden_path=_f("LATTICE_SEM_EVAL_GOLDEN_PATH",
                                     "eval/semantic_golden.jsonl"),
        log_level=env("LATTICE_LOG_LEVEL", "INFO"),
        log_format=env("LATTICE_LOG_FORMAT", "json"),
    )
    _validate(settings)
    return settings


def _validate(s: Settings) -> None:
    """数值/枚举校验（P3-N10）——负值与非法枚举 fail-closed。"""
    if s.worker_mode not in WORKER_MODES:
        raise ValueError(
            f"invalid worker_mode {s.worker_mode!r}（合法值："
            f" {' | '.join(WORKER_MODES)}——fail-closed，不静默回退）"
        )
    numeric_failures = []
    for name in (
        "worker_heartbeat_s", "worker_lease_s", "worker_poll_s",
        "worker_restart_backoff_s", "task_max_attempts",
        "maintenance_keep_days", "maintenance_keep_count", "tombstone_keep_days",
        "audit_keep_months", "upload_credential_ttl_s", "maintenance_interval_s",
        "semantic_describe_cache_s",
        "semantic_l0_token_budget",
        "semantic_daily_sync_interval_s",
    ):
        value = getattr(s, name)
        if value < 0:
            numeric_failures.append(f"{name}={value!r}")
    if s.task_max_attempts < 1:
        numeric_failures.append(f"task_max_attempts={s.task_max_attempts!r}（须 ≥1）")
    if not 0.0 <= s.semantic_delete_guard <= 1.0:
        numeric_failures.append(
            f"semantic_delete_guard={s.semantic_delete_guard!r}（须 ∈ [0,1]）"
        )
    if s.semantic_grace_days < 0 or s.semantic_batch_rows < 1:
        numeric_failures.append(
            f"semantic_grace_days={s.semantic_grace_days!r}（须 ≥0）/"
            f"semantic_batch_rows={s.semantic_batch_rows!r}（须 ≥1）"
        )
    if s.semantic_batch_rows > 1000:
        numeric_failures.append(
            f"semantic_batch_rows={s.semantic_batch_rows!r}（须 ≤1000——design §5.8"
            " 每批 ≤1000 行提交的硬约束，NFR-11 写锁治理）"
        )
    for name in ("semantic_dim_alert_baseline", "semantic_dim_alert_drop"):
        value = getattr(s, name)
        if not 0.0 <= value <= 1.0:
            numeric_failures.append(f"{name}={value!r}（须 ∈ [0,1]）")
    if numeric_failures:
        raise ValueError(
            # P3-r5（m2s-1 移交）：前缀改范围语义——失败项不再全是「≥0」（还有
            # [0,1] 区间与 ≥1/≤1000 边界），旧文案 "must be >= 0" 以偏概全
            "invalid config values (value out of allowed range): "
            + "; ".join(numeric_failures)
        )
