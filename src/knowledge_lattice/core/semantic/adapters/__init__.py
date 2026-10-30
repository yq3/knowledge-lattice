"""SourceAdapter 协议 + per-org 连接解析 + 适配器注册表（design §5.8 / #37 前置条件③）。

- SourceAdapter：只读、幂等、fetch(org) 输出**当前全量快照**（分页拼装或导出
  文件均可——传输方式无关；不做增量：全量快照语义是删除比例保护与 missing
  检测的前提，不可退让——#37 前置条件①）；
- 连接配置 per-org（#37 前置条件③）：`Settings.semantic_sources_json`
  （LATTICE_SEM_SOURCES_JSON，JSON：{org: {adapter: {endpoint, api_key, timeout_s}}}，
  部署时配置、重启生效）；未配置 org/适配器 → SemanticSourceNotConfigured
  fail-closed（不静默跳过——TC-SYNC-01）；
- ADAPTER_FACTORIES 注册表：默认两适配器（template_center / metadata），
  测试/部署侧经 register_adapter_factory 覆盖（沿 MAINTENANCE_BODIES 注册表
  惯例——跨进程无法传对象时的 import 钩子同族扩展点）。
- MCP 为允许传输形态之一（FR-S1 v0.7——本段不实现，协议传输无关）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from knowledge_lattice.config import Settings
from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

logger = logging.getLogger(__name__)

__all__ = [
    "SourceAdapter", "SourceConfig", "SemanticSourceNotConfigured",
    "UnknownAdapterError", "ADAPTER_FACTORIES", "register_adapter_factory",
    "build_adapter", "resolve_source_config", "derive_refs",
    "TemplateCenterAdapter", "MetadataAdapter",
]


class SemanticSourceNotConfigured(RuntimeError):
    """per-org 源连接未配置（TC-SYNC-01：报配置错误、不静默跳过）。"""


class UnknownAdapterError(ValueError):
    """适配器名不在登记表（REST 404 / 任务失败语义）。"""


@dataclass(frozen=True)
class SourceConfig:
    """单个源系统实例连接参数（per-org 解析产物）。"""

    endpoint: str
    api_key: str | None = None
    timeout_s: float = 30.0


class SourceAdapter(Protocol):
    """同步适配器协议（design §5.8——只读拉取、幂等、输出当前快照）。"""

    name: str

    def fetch(self, org: str) -> Iterable[EntityRecord | RelationRecord]: ...


def resolve_source_config(settings: Settings, org: str, adapter: str) -> SourceConfig:
    """per-org 实例解析（org → 源系统实例；未配置 fail-closed——TC-SYNC-01）。"""
    sources = settings.semantic_sources
    org_conf = sources.get(org)
    if not org_conf or adapter not in org_conf:
        raise SemanticSourceNotConfigured(
            f"semantic source not configured: org={org!r} adapter={adapter!r}"
            "——LATTICE_SEM_SOURCES_JSON 未覆盖该 org/适配器（不静默跳过）"
        )
    raw = dict(org_conf[adapter])
    return SourceConfig(
        endpoint=str(raw.get("endpoint", "")),
        api_key=raw.get("api_key"),
        timeout_s=float(raw.get("timeout_s", 30.0)),
    )


def derive_refs(
    records: Iterable[EntityRecord | RelationRecord],
) -> set[tuple[str, str]]:
    """引用面推导：快照 RelationRecord 中 backed_by / maps_to 的 dst (type, key)。

    metadata 适配器「只拉被引用到的表与列」的引用面来源（TC-SYNC-02——
    从本次同步快照的 RelationRecord 推导；YAML 显式列出归 m2s-3 并入）。
    """
    from knowledge_lattice.core.semantic.constants import REFERENCE_REL_TYPES

    return {
        tuple(rec.dst)
        for rec in records
        if isinstance(rec, RelationRecord) and rec.rel_type in REFERENCE_REL_TYPES
    }


# ---- 适配器注册表（默认工厂 + 覆盖扩展点） ----

# factory(org, settings) -> SourceAdapter
ADAPTER_FACTORIES: dict[str, Callable[[str, Settings], SourceAdapter]] = {}


def register_adapter_factory(name: str, factory: Callable[[str, Settings], SourceAdapter]) -> None:
    """注册/覆盖适配器工厂（测试 fake 注入 / 部署侧自定义 provider）。

    **工厂自担配置解析**（P3-r4，m2s-1 移交注记）：注册工厂覆盖默认 per-org
    配置校验（resolve_source_config 不再跑）——工厂内部自行解析所需配置并
    fail-fast；测试替身通常直接闭包快照数据、无配置面。另注：m2s-2 起
    describe_table 经 duck-typing 探测覆盖实例的 ``describe_table`` 方法
    （有则用作透传通道——测试注入点）。"""
    ADAPTER_FACTORIES[name] = factory


def build_adapter(name: str, org: str, settings: Settings) -> SourceAdapter:
    """按名构造适配器：注册表覆盖优先，其次默认 HTTP 形态实现。"""
    from knowledge_lattice.core.semantic.constants import SYNC_ADAPTERS

    override = ADAPTER_FACTORIES.get(name)
    if override is not None:
        return override(org, settings)
    if name == "template_center":
        from .template_center import TemplateCenterAdapter

        return TemplateCenterAdapter(resolve_source_config(settings, org, name))
    if name == "metadata":
        from .metadata import MetadataAdapter

        config = resolve_source_config(settings, org, name)
        # 引用面：本次同步的 template_center 快照 RelationRecord 推导（TC-SYNC-02
        # 口径——两适配器接力；template_center 未配置时引用面为空并告警，YAML
        # 显式列出归 m2s-3）
        refs: set[tuple[str, str]] = set()
        try:
            tc = build_adapter("template_center", org, settings)
            refs = derive_refs(tc.fetch(org))
        except SemanticSourceNotConfigured:
            logger.warning(
                "metadata refs empty: template_center not configured for org=%s"
                "（引用面推导不可用——YAML 显式列出归 m2s-3）", org,
            )
        return MetadataAdapter(config, refs=refs)
    raise UnknownAdapterError(
        f"unknown semantic sync adapter: {name!r}（合法值："
        f" {' | '.join((*SYNC_ADAPTERS, *ADAPTER_FACTORIES))}）"
    )


def _default_transport(config: SourceConfig) -> Callable[[str, str, dict | None], dict]:
    """HTTP 传输（httpx 同步客户端——真实源系统联调环境依赖申报，同 rerank 先例）。"""
    import httpx

    client = httpx.Client(
        base_url=config.endpoint,
        timeout=config.timeout_s,
        headers={"Authorization": f"Bearer {config.api_key}"} if config.api_key else None,
    )

    def transport(endpoint: str, path: str, params: dict | None = None) -> dict:
        resp = client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    return transport


# 底部再导出具体适配器（子模块反向引用本包符号——延迟至协议/配置定义之后防环）
from .metadata import MetadataAdapter  # noqa: E402,F401
from .template_center import TemplateCenterAdapter  # noqa: E402,F401
