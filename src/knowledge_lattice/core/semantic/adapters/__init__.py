"""SourceAdapter 协议 + per-org 连接解析 + 适配器注册表（design §5.8 / #37 前置条件③）。

- SourceAdapter：只读、幂等、fetch(org) 输出**当前全量快照**（分页拼装或导出
  文件均可——传输方式无关；不做增量：全量快照语义是删除比例保护与 missing
  检测的前提，不可退让——#37 前置条件①）；
- 连接配置 per-org（#37 前置条件③）：`Settings.semantic_sources_json`
  （LATTICE_SEM_SOURCES_JSON，JSON：{org: {adapter: {endpoint, api_key, timeout_s}}}，
  部署时配置、重启生效）；未配置 org/适配器 → SemanticSourceNotConfigured
  fail-closed（不静默跳过——TC-SYNC-01）；
- ADAPTER_FACTORIES 注册表：默认五适配器（template_center / metadata /
  scenario_config / report_center / yaml——m2s-3 起源齐），测试/部署侧经
  register_adapter_factory 覆盖（沿 MAINTENANCE_BODIES 注册表惯例——跨进程
  无法传对象时的 import 钩子同族扩展点）。
- MCP 为允许传输形态之一（FR-S1 v0.7——本段不实现，协议传输无关）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from knowledge_lattice.config import Settings
from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

logger = logging.getLogger(__name__)

__all__ = [
    "SourceAdapter", "SourceConfig", "SemanticSourceNotConfigured",
    "UnknownAdapterError", "ADAPTER_FACTORIES", "register_adapter_factory",
    "build_adapter", "resolve_source_config", "derive_refs", "close_adapter",
    "yaml_reference_refs", "load_dim_value_map",
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
    """同步适配器协议（design §5.8——只读拉取、幂等、输出当前快照）。

    可选属性：``relation_source``（本源关系的 source 取值，缺省 'sync'——
    yaml 源为 'curated'，§5.8 合并规则表第 1 行）；``close()``（持有传输
    资源的适配器应实现——C.6 接线经 close_adapter）。"""

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
    """按名构造适配器：注册表覆盖优先，其次默认实现（HTTP / 本地目录形态）。"""
    from knowledge_lattice.core.semantic.constants import SYNC_ADAPTERS

    override = ADAPTER_FACTORIES.get(name)
    if override is not None:
        return override(org, settings)
    if name == "template_center":
        from .template_center import TemplateCenterAdapter

        return TemplateCenterAdapter(resolve_source_config(settings, org, name))
    if name == "scenario_config":
        from .scenario_config import ScenarioConfigAdapter

        return ScenarioConfigAdapter(resolve_source_config(settings, org, name))
    if name == "report_center":
        from .report_center import ReportCenterAdapter

        return ReportCenterAdapter(resolve_source_config(settings, org, name))
    if name == "yaml":
        from .yaml_repo import YamlRepoAdapter

        return YamlRepoAdapter(resolve_source_config(settings, org, name))
    if name == "metadata":
        from .metadata import MetadataAdapter

        config = resolve_source_config(settings, org, name)
        # 引用面（TC-SYNC-02——m2s-3 收口「YAML 显式列出」半句）：
        # ① YAML 仓显式声明的 table/column 引用 ∪ ② template_center 快照
        # RelationRecord 推导（兜底保留——v1.9.1 口径）；两者均 fail-open
        # （未配置源：引用面相应为空并告警，首轮冷启动合法态）。
        refs: set[tuple[str, str]] = yaml_reference_refs(settings, org)
        tc = None
        try:
            tc = build_adapter("template_center", org, settings)
            refs |= derive_refs(tc.fetch(org))
        except SemanticSourceNotConfigured:
            logger.warning(
                "metadata refs: template_center not configured for org=%s"
                "（推导兜底不可用——引用面仅 YAML 显式列出）", org,
            )
        finally:
            if tc is not None:
                close_adapter(tc)  # refs 接力用的临时适配器即建即关（C.6）
        return MetadataAdapter(config, refs=refs)
    raise UnknownAdapterError(
        f"unknown semantic sync adapter: {name!r}（合法值："
        f" {' | '.join((*SYNC_ADAPTERS, *ADAPTER_FACTORIES))}）"
    )


def close_adapter(adapter) -> None:
    """适配器显式关闭（C.6——默认 HTTP 传输持有 httpx.Client，不关则每次
    sync run 泄漏一个连接池；duck-typed：无 close 的替身静默跳过）。"""
    closer = getattr(adapter, "close", None)
    if callable(closer):
        closer()


def _yaml_repo_path(settings: Settings, org: str) -> str | None:
    """yaml 源仓库路径（未配置返回 None——引用面/映射面 fail-open 的判据）。"""
    org_conf = settings.semantic_sources.get(org)
    if not org_conf or "yaml" not in org_conf:
        return None
    raw = org_conf.get("yaml") or {}
    endpoint = raw.get("endpoint")
    return str(endpoint) if endpoint else None


def yaml_reference_refs(settings: Settings, org: str) -> set[tuple[str, str]]:
    """YAML 显式列出的 table/column 引用面（TC-SYNC-02 半句收口——m2s-3）。

    来源：corpus 条目 refers_to/related_to 与 extra_relations 中 type 为
    table/column 的端点；未配置 yaml 源 → 空集（不告警——yaml 为可选源）；
    已配置但仓库不可读/畸形 → WARNING + 空集（引用面推导 fail-open，metadata
    仍可经 template_center 兜底工作）。
    """
    path = _yaml_repo_path(settings, org)
    if not path:
        return set()
    try:
        from knowledge_lattice.core.semantic.yaml_corpus import load_corpus

        corpus = load_corpus(path)
    except (OSError, ValueError) as exc:
        logger.warning(
            "yaml refs unavailable: org=%s path=%s (%s: %s)——引用面回退"
            " template_center 推导", org, path, type(exc).__name__, exc,
        )
        return set()
    refs: set[tuple[str, str]] = set()
    for entry in corpus.entries:
        for ref in (*entry.refers_to, *entry.related_to):
            rtype, _, rkey = ref.partition(":")
            if rtype in ("table", "column"):
                refs.add((rtype, rkey))
        for xr in entry.extra_relations:
            for ref in (xr.src, xr.dst):
                rtype, _, rkey = ref.partition(":")
                if rtype in ("table", "column"):
                    refs.add((rtype, rkey))
    return refs


def load_dim_value_map(
    settings: Settings, org: str, *, repo_path: str | Path | None = None,
) -> dict[str, dict[str, str]]:
    """值域显式映射表（TC-SYNC-06 半句收口——design §4 无专表 DDL，任务书
    授权最小实现：YAML 仓 `dim_value_map.yaml` 维护，dim → {源值: 本地值}）。

    未配置 yaml 源 / 仓库无该文件 → 空映射（原值透传——报告注记口径）。"""
    from pathlib import Path as _Path

    path = repo_path if repo_path is not None else _yaml_repo_path(settings, org)
    if not path:
        return {}
    try:
        from knowledge_lattice.core.semantic.yaml_corpus import load_corpus

        return load_corpus(_Path(str(path))).dim_value_map
    except (OSError, ValueError) as exc:
        logger.warning(
            "dim value map unavailable: org=%s (%s: %s)——维度值原样落库",
            org, type(exc).__name__, exc,
        )
        return {}


class _DefaultHttpTransport:
    """默认 HTTP 传输 + 客户端生命周期（P1-1④/R2——每次构造新建的
    httpx.Client 必须可显式关闭：describe 路径每 5min/表一次长期运行，
    依赖 GC 泄漏连接池）。可调用形态与注入用 transport 同契约。"""

    def __init__(self, config: SourceConfig) -> None:
        import httpx

        self._client = httpx.Client(
            base_url=config.endpoint,
            timeout=config.timeout_s,
            headers=(
                {"Authorization": f"Bearer {config.api_key}"}
                if config.api_key else None
            ),
        )

    def __call__(self, endpoint: str, path: str, params: dict | None = None) -> dict:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()


def _default_transport(config: SourceConfig) -> Callable[[str, str, dict | None], dict]:
    """HTTP 传输（httpx 同步客户端——真实源系统联调环境依赖申报，同 rerank 先例）。

    返回值可调用且带 ``close()``（R2 起）——按次构造的调用方（describe_table
    默认通道）用后即关；长驻调用方（一次同步 run 的 fetch）随适配器 close。"""
    return _DefaultHttpTransport(config)


# 底部再导出具体适配器（子模块反向引用本包符号——延迟至协议/配置定义之后防环）
from .metadata import MetadataAdapter  # noqa: E402,F401
from .template_center import TemplateCenterAdapter  # noqa: E402,F401
