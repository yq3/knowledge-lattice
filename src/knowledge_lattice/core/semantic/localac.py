"""过渡期本地 AC 自动机（design §6.3 过渡期段 / TC-YAML-05——m2s-6）。

**两端共用同一 package**：agent 侧本地版（Git YAML → 本地 Annotator）与
服务端 annotate 用**同一实现**（Annotator + norm.normalize_alias +
yaml_corpus 装载）——「迁移零改动」承诺的实现载体；规范化函数与 schema
单源（norm/yaml_corpus），两端 mentions 完全一致（TC-YAML-05 断言）。

本地版识别面（#35 §12.3）：**只覆盖 concept/system 与 L0**（纯人工实体）
——覆盖层（templates/…）实体本体是同步来的、本地不存在；服务端词典含
同步实体时会多识别（超集），**共享面逐位一致**由同源实现保证。
"""

from __future__ import annotations

from knowledge_lattice.core.semantic.annotator import Annotator

__all__ = ["local_annotator_from_corpus", "snapshot_from_corpus"]


def snapshot_from_corpus(corpus) -> dict:
    """YAML corpus（yaml_corpus.load_corpus 产物）→ 识别快照（Annotator
    输入形态：entities/aliases/relations）——**纯人工实体（concept/system）
    全量**；别名为 name/manual/abbr（含 match_mode=context 的别名保留
    mode；fuzzy_only 保留——Annotator 侧不进 AC 自动机、与构建面同口径）；
    关系 = refers_to/related_to/extra_relations 中**两端均为纯人工类型**
    的边（跨到同步实体的边本地无端点，跳过——共现消歧①的佐证面在本地
    相应收窄，属过渡期已知差异并随服务端切换消失）。"""
    from knowledge_lattice.core.semantic.constants import (
        PURE_YAML_ENTITY_TYPES,
    )
    from knowledge_lattice.core.semantic.norm import normalize_alias

    entities: list[dict] = []
    aliases: list[dict] = []
    by_key: dict[str, int] = {}
    next_id = 1
    for entry in corpus.entries:
        if entry.type not in PURE_YAML_ENTITY_TYPES:
            continue
        eid = next_id
        next_id += 1
        by_key[entry.id] = eid
        entities.append({
            "id": eid, "type": entry.type, "key": entry.key,
            "name": entry.name or entry.key,
            "parent_id": None, "attrs_json": "{}",
            "sensitivity": entry.sensitivity or "normal",
            "curated_json": _dumps(entry.curated_payload()),
            "curated_rev": getattr(corpus, "rev", None),
        })
        specs = [(entry.name or entry.key, "name", "exact", 1.0)]
        specs.extend((s.value, "manual", s.match_mode, 1.0)
                     for s in entry.aliases)
        specs.extend((s.value, "abbr", s.match_mode, 1.0)
                     for s in entry.abbr_specs())
        seen_norms: set[str] = set()
        for value, kind, mode, weight in specs:
            norm = normalize_alias(str(value or ""))
            if not norm:
                continue
            # P3-2/R2 同款消解：manual/abbr 与本条目 name 同 norm → skip
            #（与服务端入库语义对齐——name 占用时 manual 行不写，档位=exact）
            if norm in seen_norms:
                continue
            seen_norms.add(norm)
            aliases.append({
                "entity_id": eid, "alias": str(value), "alias_norm": norm,
                "kind": kind, "match_mode": mode, "weight": weight,
            })
    relations: list[dict] = []
    for entry in corpus.entries:
        if entry.type not in PURE_YAML_ENTITY_TYPES:
            continue
        src = by_key.get(entry.id)
        if src is None:
            continue
        related = set(entry.related_to or ())
        for ref in list(entry.refers_to or ()) + list(entry.related_to or ()):
            dst = by_key.get(ref)
            if dst is None:
                continue        # 跨到同步实体（本地无端点）——过渡期已知差异
            relations.append({
                "src_id": src,
                "rel_type": "related_to" if ref in related else "refers_to",
                "dst_id": dst, "attrs_json": "{}", "source": "curated",
            })
    return {"entities": entities, "aliases": aliases, "relations": relations}


def local_annotator_from_corpus(corpus) -> Annotator:
    """YAML corpus → 本地 Annotator（过渡期 agent 侧识别面——与服务端
    annotate 同一实现；接口不变：输入文本、输出 mentions）。"""
    return Annotator(snapshot_from_corpus(corpus))


def _dumps(obj) -> str:
    import json

    return json.dumps(obj or {}, ensure_ascii=False, sort_keys=True)
