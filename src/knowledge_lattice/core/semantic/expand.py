"""关系展开与实体详情（design §5.9 get_entity / §6.3 工具契约——m2s-2 首批）。

- depth ≤2 / fanout_limit ≤200 / 节点总量默认 200（服务端常量——T-S6 附录 A-11
  拒绝口径：超限 400 不静默截断参数）；
- expand 方向后缀：`uses>` 出向 / `derived_from<` 入向 / 裸 rel_type 双向；
- 防环/截断在 store.sem_expand_graph（递归 CTE 等价 SQL——BFS 逐层）；
- restricted 实体：根 404、展开不出现（fail-closed——T-S9；持权路径 M2-S3
  权限面交付前一律不可见）；非 active（missing/retired）根同样 404（P3-6/R2
  ——工具面只服务 active 图，与 describe_table 口径对齐；状态面经管理端点）；
- dict_rev：当前构建（最新 ready）的词典版本——无构建时 None（服务按
  (org, dict_rev) 懒加载的取用锚点，§5.8）。

多跳由 Agent 迭代调用（design §5.9 时序③——不做单次深展开）。
"""

from __future__ import annotations

import json
import logging

from knowledge_lattice.core.semantic.constants import SEM_ENTITY_TYPES, SEM_REL_TYPE_NAMES

logger = logging.getLogger(__name__)

__all__ = ["get_entity", "EntityNotFound"]

DEFAULT_DEPTH = 1
MAX_DEPTH = 2
DEFAULT_FANOUT = 50
MAX_FANOUT = 200
NODE_LIMIT_DEFAULT = 200   # T-S6「节点上限 500（默认 200）」——服务端常量
NODE_LIMIT_MAX = 500


class EntityNotFound(LookupError):
    """实体不存在 / 他组织 / restricted（404——存在性零泄露，T-S7/T-S9）。"""


def get_entity(
    backend,
    org_id: str,
    *,
    entity_id: int | None = None,
    key: str | None = None,
    expand: list[str] | None = None,
    depth: int = DEFAULT_DEPTH,
    fanout_limit: int = DEFAULT_FANOUT,
    include: list[str] | None = None,
) -> dict:
    """get_entity（§6.3 契约）：entity + nodes/edges（depth=1 邻接或 depth=2
    两跳）+ truncated + dict_rev。

    key/id 二选一（皆无/皆有 → ValueError=400）；include ⊆
    {curated, attrs, aliases}（缺省 ['curated']——design 契约默认）。"""
    if not (1 <= depth <= MAX_DEPTH):
        raise ValueError(f"depth 必须在 1..{MAX_DEPTH}（服务端强制上限——附录 A-11）")
    if not (1 <= fanout_limit <= MAX_FANOUT):
        raise ValueError(f"fanout_limit 必须在 1..{MAX_FANOUT}（附录 A-11）")
    if (entity_id is None) == (key is None):
        raise ValueError("id 与 key 二选一（皆无/皆有不可——design §6.3）")
    include = list(include) if include else ["curated"]
    bad_include = set(include) - {"curated", "attrs", "aliases"}
    if bad_include:
        raise ValueError(f"include 非法值 {sorted(bad_include)}（合法：curated/attrs/aliases）")

    if key is not None:
        if ":" not in key:
            raise ValueError("key 形如 'type:key'（如 template:TPL_VAT_INPUT）")
        type_, _, k = key.partition(":")
        if type_ not in SEM_ENTITY_TYPES:
            raise ValueError(f"未知实体类型 {type_!r}（合法：{sorted(SEM_ENTITY_TYPES)}")
        row = backend.sem_entity_by_key(org_id, type_, k)
    else:
        row = backend.sem_entity_by_id(org_id, entity_id)
    if (row is None or row["sensitivity"] == "restricted"
            or row["status"] != "active"):
        # 他组织（org 第一条件隔离）/ 不存在 / restricted / 非 active
        # （missing/retired——P3-6/R2 与 describe_table 对齐：工具面只服务
        # active 图，状态面经管理端点）→ 同一 404（存在性零泄露）
        raise EntityNotFound(f"entity not found: id={entity_id!r} key={key!r}")

    outgoing, incoming = _parse_expand(expand)
    graph = backend.sem_expand_graph(
        org_id, row["id"], outgoing=outgoing, incoming=incoming,
        depth=depth, fanout_limit=fanout_limit, node_limit=NODE_LIMIT_DEFAULT,
    )

    entity = {"id": row["id"], "type": row["type"], "key": row["key"],
              "name": row["name"], "status": row["status"]}
    if "curated" in include:
        entity["curated"] = _loads(row["curated_json"])
    if "attrs" in include:
        entity["attrs"] = _loads(row["attrs_json"])
    if "aliases" in include:
        alias_rows = backend.sem_entity_aliases(org_id, [row["id"]])
        entity["aliases"] = [a["alias"] for a in alias_rows]

    current = backend.sem_current_build(org_id)
    return {
        "entity": entity,
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "truncated": graph["truncated"],
        "dict_rev": current["dict_rev"] if current else None,
    }


def _parse_expand(expand: list[str] | None) -> tuple[list[str], list[str]]:
    """方向后缀解析：`rel>` 出向 / `rel<` 入向 / 裸 rel 双向；未知 rel_type →
    ValueError（400——白名单外组合对 LLM 无意义）。"""
    outgoing: list[str] = []
    incoming: list[str] = []
    for spec in expand or []:
        if spec.endswith(">"):
            rel, direction = spec[:-1], "out"
        elif spec.endswith("<"):
            rel, direction = spec[:-1], "in"
        else:
            rel, direction = spec, "both"
        if rel not in SEM_REL_TYPE_NAMES:
            raise ValueError(
                f"未知关系类型 {rel!r}（合法：{sorted(SEM_REL_TYPE_NAMES)}）"
            )
        if direction in ("out", "both") and rel not in outgoing:
            outgoing.append(rel)
        if direction in ("in", "both") and rel not in incoming:
            incoming.append(rel)
    if not outgoing and not incoming:
        # 缺省 = 全部关系类型双向（§6.3 expand 可选）
        outgoing = incoming = sorted(SEM_REL_TYPE_NAMES)
    return outgoing, incoming


def _loads(text: str | None) -> dict:
    try:
        return json.loads(text) if text else {}
    except (TypeError, ValueError):
        return {}
