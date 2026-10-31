"""实体检索与表详情透传（design §6.3——m2s-2 首批工具的查询面收口；
design §3 未单列本模块、随 m2s-2 增设——search_entities/describe_table 编排）。

- search_entities（TC-SEM-05 前半）：alias_norm 精确 > 前缀 + name 模糊三层
  （拼音/向量 M2-S3——G-1）；q ≤200、top_k ≤50；restricted 实体不出现
  （fail-closed——T-S9）；
- describe_table（T-S11）：只对已登记 table 实体开放（未登记 → 403——防借此
  枚举整个数仓）；透传元数据系统（3s 超时 + 5min 缓存）；不可用 → 本地轻量
  节点 + degraded=true。
"""

from __future__ import annotations

import logging
import time

from knowledge_lattice.config import Settings
from knowledge_lattice.core.semantic.constants import SEM_ENTITY_TYPES
from knowledge_lattice.core.semantic.norm import normalize_alias

logger = logging.getLogger(__name__)

__all__ = [
    "search_entities", "describe_table", "DescribeTableDenied",
    "clear_describe_cache", "DESCRIBE_TIMEOUT_S",
]

MAX_Q_LEN = 200       # §6.3 input 契约：q ≤200
MAX_TOP_K = 50        # §6.3：top_k ≤50
DESCRIBE_TIMEOUT_S = 3.0   # T-S11：透传超时 3s
_DESCRIBE_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}


def clear_describe_cache() -> None:
    """清空透传缓存（测试隔离 / 运维强制刷新）。"""
    _DESCRIBE_CACHE.clear()


class DescribeTableDenied(PermissionError):
    """未登记的表名（403——T-S11②：防枚举数仓；非 table 实体同口径）。"""


def search_entities(
    backend,
    org_id: str,
    q: str,
    *,
    types: list[str] | None = None,
    top_k: int = 10,
) -> dict:
    """search_entities（§6.3 契约）：entities[{id,type,key,name,brief,score,via}]。

    brief 取 curated_json.definition → attrs_json.definition → attrs_json.comment
    （一句话定义——YAML 覆盖层归 m2s-3，本段多为 None）。"""
    if not q or len(q) > MAX_Q_LEN:
        raise ValueError(f"q 长度须在 1..{MAX_Q_LEN}")
    if not (1 <= top_k <= MAX_TOP_K):
        raise ValueError(f"top_k 必须在 1..{MAX_TOP_K}（§6.3 上限）")
    if types:
        bad = set(types) - set(SEM_ENTITY_TYPES)
        if bad:
            raise ValueError(f"types 非法值 {sorted(bad)}（合法：{sorted(SEM_ENTITY_TYPES)}")

    q_norm = normalize_alias(q)
    rows = backend.sem_search_entities(
        org_id, q_norm, q, types=types, top_k=top_k
    )
    best: dict[int, dict] = {}
    for r in rows:  # 已按 score DESC 排序——首个即该实体最优档
        if r["id"] in best:
            continue
        best[r["id"]] = r
    entities = []
    for r in list(best.values())[:top_k]:
        curated = _loads(r["curated_json"])
        attrs = _loads(r["attrs_json"])
        brief = (curated.get("definition")
                 or attrs.get("definition") or attrs.get("comment"))
        entities.append({
            "id": r["id"], "type": r["type"], "key": r["key"],
            "name": r["name"], "brief": brief,
            "score": r["score"], "via": r["via"],
        })
    return {"entities": entities}


def describe_table(
    backend,
    settings: Settings,
    org_id: str,
    table: str,
    *,
    columns: list[str] | None = None,
    fetcher=None,
) -> dict:
    """describe_table（T-S11）：已登记 table 实体 → 元数据系统透传
    （{name, columns:[{name,type?,comment?,sample?}]}）+ degraded 标志。

    - 白名单：sem_entities 内 type='table' 的 active 实体才放行（T-S11②）；
    - 缓存 5min（settings.semantic_describe_cache_s——T-S11④，只缓存成功结果）；
    - 降级：透传异常（超时/不可达/未知表/**源未配置或配置畸形**——fetcher
      构造亦在 try 内，P1-1②/R2）→ 本地轻量列节点 + degraded=true（T-S11③
      ——不缓存降级结果，恢复后即透传）；
    - columns 参数：按列名过滤（§6.3 input）。"""
    entity = _resolve_table_entity(backend, org_id, table)

    cache_key = (org_id, entity["key"])
    now = time.monotonic()
    ttl = settings.semantic_describe_cache_s
    cached = _DESCRIBE_CACHE.get(cache_key)
    if cached and ttl > 0 and now - cached[0] < ttl:
        return _shape_describe(entity["key"], cached[1], columns, degraded=False)

    try:
        fetch = fetcher if fetcher is not None else _default_fetcher(settings, org_id)
        detail = fetch(entity["key"])
        if ttl > 0:
            _DESCRIBE_CACHE[cache_key] = (now, detail)
        return _shape_describe(entity["key"], detail, columns, degraded=False)
    except Exception as exc:  # noqa: BLE001 —— 透传/构造失败一律降级（T-S11③）
        logger.warning(
            "describe_table degraded: org=%s table=%s (%s: %s)——回退本地轻量节点",
            org_id, entity["key"], type(exc).__name__, exc,
        )
        # 轻量列名 = column key 去表键前缀（与透传 columns[].name 同形）
        prefix = entity["key"] + "."
        light = {
            "name": entity["name"],
            "columns": [
                {"name": c["key"][len(prefix):] if c["key"].startswith(prefix)
                 else c["name"]}
                for c in backend.sem_table_columns(org_id, entity["id"])
            ],
        }
        return _shape_describe(entity["key"], light, columns, degraded=True)


def _resolve_table_entity(backend, org_id: str, table: str) -> dict:
    """table 实体解析：key 或数字 id（§6.3 input "table 实体的 key 或 id"）。"""
    row = None
    if table.isdigit():
        row = backend.sem_entity_by_id(org_id, int(table))
    if row is None:
        row = backend.sem_entity_by_key(org_id, "table", table)
    if (row is None or row["type"] != "table" or row["status"] != "active"
            or row["sensitivity"] == "restricted"):
        raise DescribeTableDenied(
            f"table not registered: {table!r}（describe_table 仅对已登记 table"
            " 实体开放——T-S11②）"
        )
    return row


def _default_fetcher(settings: Settings, org_id: str):
    """默认透传通道：注册工厂覆盖（duck-typed describe_table）优先，否则
    per-org 配置解析 → MetadataAdapter.describe_table（超时钳制 3s——T-S11）。

    默认分支按次构造适配器，**用后即关**（P1-1④/R2：_default_transport
    持有 httpx.Client，不关则 describe 每 5min/表泄漏一个连接池）。"""
    from knowledge_lattice.core.semantic.adapters import (
        ADAPTER_FACTORIES,
        MetadataAdapter,
        SourceConfig,
        resolve_source_config,
    )

    override = ADAPTER_FACTORIES.get("metadata")
    if override is not None:
        adapter = override(org_id, settings)
        describe = getattr(adapter, "describe_table", None)
        if callable(describe):
            return describe

    cfg = resolve_source_config(settings, org_id, "metadata")
    config = SourceConfig(
        endpoint=cfg.endpoint, api_key=cfg.api_key,
        timeout_s=min(cfg.timeout_s, DESCRIBE_TIMEOUT_S),
    )
    adapter = MetadataAdapter(config, refs=())

    def _fetch_once(table_key: str) -> dict:
        try:
            return adapter.describe_table(table_key)
        finally:
            adapter.close()

    return _fetch_once


def _shape_describe(table_key: str, detail: dict, columns, *, degraded: bool) -> dict:
    cols = [
        {"name": c.get("name"),
         **({"type": c["type"]} if c.get("type") else {}),
         **({"comment": c["comment"]} if c.get("comment") else {}),
         **({"sample": str(c["sample"])} if c.get("sample") is not None else {})}
        for c in detail.get("columns") or ()
    ]
    if columns:
        wanted = set(columns)
        cols = [c for c in cols if c["name"] in wanted]
    return {"table": table_key, "name": detail.get("name"),
            "columns": cols, "degraded": degraded}


def _loads(text: str | None) -> dict:
    import json

    try:
        return json.loads(text) if text else {}
    except (TypeError, ValueError):
        return {}
