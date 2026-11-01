"""实体召回编排面（design §5.10——m2s-6/M2-S3；**识别钉 api/mcp 层**——
§3 规则 2：auto_entities 的 AC 识别在本面完成、core/docs/retrieve 不调
annotate；core 两包不交叉由 test_sem_00_layering 守卫）。

resolve_query_entities：search 调用方（REST /api/search 与 MCP search）的
实体参数解析与展开——

1. 显式 ``entities``（≤20——ENTITY_RECALL_MAX_SEEDS，超限 ValueError=400）：
   种子过滤 restricted / 非 active（语义层不因显式 id 泄露不可见实体——
   T-S9；被滤后为空 → 不启用实体路）；
2. ``auto_entities=True``：对 query 先跑一遍第 1 层 AC 识别（annotate_text
   ——歧义命中不作种子〔2026-10-31 用户裁定歧义 skip 的同款口径：未定案
   不进证据面〕）；识别异常不阻断检索（实体路是增益路非可用性前提）；
3. `semantic.expand(seeds, ENTITY_RECALL_RELS, depth=1)`——**不沿 uses**
   （高扇出防发散，TC-TAG-04）；结果保序去重 ≤50
   （ENTITY_RECALL_MAX_ENTITIES——种子优先，超出截断扩展尾）。

返回 ``{"seeds": [...], "entity_ids": [...]}`` 或 None（不启用实体路）。
expand_relations 的 seed 过滤责任在消费方（store 薄适配契约）：本面按
sem_entities_by_ids 重读实体行过滤（restricted / 非 active）。
"""

from __future__ import annotations

import logging

from knowledge_lattice.config import Settings
from knowledge_lattice.core.semantic.constants import (
    ENTITY_RECALL_MAX_ENTITIES,
    ENTITY_RECALL_MAX_SEEDS,
    ENTITY_RECALL_RELS,
)

logger = logging.getLogger(__name__)

__all__ = ["resolve_query_entities"]


def resolve_query_entities(
    backend, settings: Settings, org_id: str, *,
    query: str | None = None,
    entities: list[int] | None = None,
    auto_entities: bool = False,
) -> dict | None:
    """search 实体参数 → {seeds, entity_ids}（None=不启用实体路）。"""
    seeds: list[int] | None = None
    if entities is not None:
        ids = list(dict.fromkeys(int(e) for e in entities))
        if not (1 <= len(ids) <= ENTITY_RECALL_MAX_SEEDS):
            raise ValueError(
                f"entities 须 1..{ENTITY_RECALL_MAX_SEEDS} 个（design §5.10"
                "——实体召回路种子上限）")
        seeds = ids
    elif auto_entities:
        if not query:
            return None
        from knowledge_lattice.core.semantic.annotator import annotate_text

        try:
            result = annotate_text(backend, settings, org_id, query)
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001 —— 增益路失败不阻断检索
            logger.warning(
                "auto_entities annotate failed (%s: %s)——实体路本轮跳过",
                type(exc).__name__, exc)
            return None
        picked = [m["entity_id"] for m in result.get("mentions") or ()
                  if not m.get("ambiguous")]
        seeds = list(dict.fromkeys(picked))[:ENTITY_RECALL_MAX_SEEDS]
        if not seeds:
            return None

    if not seeds:
        return None

    # 种子过滤：restricted / 非 active 不进（T-S9 存在性零泄露；expand
    # 薄适配按 id 原样注入——过滤责任在本消费面）
    def _visible_active(ids: list[int]) -> list[int]:
        rows = backend.sem_entities_by_ids(org_id, ids)
        ok = {r["id"] for r in rows
              if r["status"] == "active" and r["sensitivity"] != "restricted"}
        return [i for i in ids if i in ok]

    seeds = _visible_active(seeds)
    if not seeds:
        return None

    graph = backend.expand_relations(
        org_id, seeds, list(ENTITY_RECALL_RELS), depth=1)
    expanded: list[int] = []
    for node in graph.get("nodes") or ():
        nid = node["id"]
        if nid not in seeds and nid not in expanded:
            expanded.append(nid)
    # 展开面过滤（同种子口径——restricted / 非 active 邻居不进）
    expanded = _visible_active(expanded)
    entity_ids = list(seeds) + expanded
    entity_ids = entity_ids[:ENTITY_RECALL_MAX_ENTITIES]
    if not entity_ids:
        return None
    return {"seeds": seeds, "entity_ids": entity_ids}
