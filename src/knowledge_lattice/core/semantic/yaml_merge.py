"""YAML 合并规则实现（design §5.8 合并规则表 L939-952 逐行——m2s-3）。

分层：yaml 源**走既有 sync 流程**（run_sync——T-S2 删除比例保护/force 放行/
T-S4 宽限推进/白名单触发器全部复用，勿另起炉灶）；纯人工实体（concept/
system）作为 source='curated' 实体走同一 upsert 面；覆盖层 curated 内容
（curated_json / manual·abbr 别名 / curated 关系）经 post_run 挂钩在**同一
run** 内落库、冲突并入 run stats（`stats.curated`——GET sync-runs 可查）。

规则表逐行落点：

- 已同步 id → 合并（curated_json + manual/abbr 别名 + source='curated' 关系
  + curated_rev=rev）——`apply_yaml_overlays`；
- 未同步/非 active（missing/retired）→ 不写入记冲突；实体恢复后自动生效
  （全量 corpus 幂等重跑即机制）；
- 纯人工实体与同步实体 (type,key) 相同 → 冲突不写入（同步实体不动）；
- 短词/常用词别名 → 合并侧 fail-closed 跳过并记冲突（CI 为第一道防线）；
- extra_relations 与同步关系重复 → 以同步为准、提示「可删除」；
- extra_relations 端点类型不在白名单 → 记冲突（入库时触发器兜底——T-S5）；
- YAML 删除覆盖项 → 清 curated_json 与 manual 别名、事实列不动（T-S1 分工）；
- L0 预算 / samples ≤3 → CI 责任列（yaml_corpus.validate_corpus，构建报告同源）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from knowledge_lattice.config import Settings
from knowledge_lattice.core.semantic.norm import normalize_alias
from knowledge_lattice.core.semantic.yaml_corpus import Corpus, YamlEntry, _alias_blocked

logger = logging.getLogger(__name__)

__all__ = ["run_yaml_sync", "apply_yaml_overlays", "make_merge_hook"]


def run_yaml_sync(
    backend,
    org_id: str,
    adapter,
    *,
    settings: Settings,
    now: str | None = None,
    finish_now: str | None = None,
    should_continue: Callable[[], bool] | None = None,
    force: bool = False,
) -> dict:
    """yaml 源一次完整同步 run：既有 sync 流程 + curated 合并挂钩（同 run 留痕）。"""
    from knowledge_lattice.core.semantic.sync import run_sync

    corpus = adapter.corpus()
    return run_sync(
        backend, org_id, adapter, settings=settings,
        now=now, finish_now=finish_now, should_continue=should_continue,
        force=force, post_run=make_merge_hook(backend, corpus),
    )


def make_merge_hook(backend, corpus: Corpus) -> Callable[[str, str], dict]:
    """post_run 挂钩工厂：curated 合并产物并入 run stats.curated。"""

    def hook(org_id: str, now: str) -> dict:
        return apply_yaml_overlays(backend, org_id, corpus, now)

    return hook


def _field_entry(f, parent_file: str) -> YamlEntry:
    ftype, _, fkey = f.id.partition(":")
    return YamlEntry(
        id=f.id, type=ftype, key=fkey, file=parent_file, pure=False,
        aliases=f.aliases, abbr=f.abbr, definition=f.definition,
    )


def apply_yaml_overlays(backend, org_id: str, corpus: Corpus, now: str) -> dict:
    """覆盖层合并主体（幂等全量重跑——恢复后自动生效的机制基础）。"""
    from knowledge_lattice.core.semantic.constants import rel_type_allowed

    conflicts: list[dict] = []
    rev = corpus.rev

    # ---- 目标面：条目 + 内嵌字段（字段覆盖层是独立实体的 curated 载体） ----
    targets: list[YamlEntry] = []
    for e in corpus.entries:
        targets.append(e)
        targets.extend(_field_entry(f, e.file) for f in e.fields)
    keys = sorted({(t.type, t.key) for t in targets})
    id_map = backend.resolve_entity_ids(org_id, keys)
    states = backend.sem_entity_states(org_id, sorted(id_map.values())) if id_map else {}

    # ---- 纯人工实体与同步实体同键 → 冲突（同步实体不动——规则表第 3 行） ----
    def _is_synced(t: YamlEntry) -> bool:
        eid = id_map.get((t.type, t.key))
        return eid is not None and states.get(eid, {}).get("source") == "sync"

    for t in targets:
        if t.pure and _is_synced(t):
            conflicts.append({
                "id": t.id, "reason": "pure entry collides with synced entity (type,key)",
            })

    # ---- curated 写入 + manual/abbr 别名（规则表第 1 行——R2/P2-1：corpus 内
    # 每个 active 目标**都产出一行**：payload 空写 {}（curated_rev 仍记录——
    # 该条目在场）、别名空产出行执行先删后插清空；stale 清理只管条目整体消失） ----
    existing_alias_norms: dict[int, set[str]] = {}
    if id_map:
        for a in backend.sem_entity_aliases(org_id, sorted(id_map.values())):
            if a["kind"] in ("name", "code", "sync"):
                existing_alias_norms.setdefault(a["entity_id"], set()).add(
                    a["alias_norm"])

    curated_rows: list[dict] = []
    alias_rows: list[dict] = []
    for t in targets:
        if t.pure and _is_synced(t):
            continue
        eid = id_map.get((t.type, t.key))
        if eid is None:
            conflicts.append({"id": t.id, "reason": "entity not synced (id unresolved)"})
            continue
        status = states.get(eid, {}).get("status")
        if status != "active":
            conflicts.append({"id": t.id, "reason": f"entity not synced (status={status!r})"})
            continue

        payload = t.curated_payload()
        curated_rows.append({
            "type": t.type, "key": t.key,
            "curated_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "curated_rev": rev,
            # P3-3/R2：sensitivity 按 YAML 当前值回写（含显式 normal；条目在场
            # 而未声明 → normal——YAML 为覆盖面 sensitivity 真源）
            "sensitivity": t.sensitivity if t.sensitivity in ("normal", "restricted")
                            else "normal",
        })
        # P3-1/R2：abbr 免短词/常用词拦截（缩写天然短——与 CI/文档口径统一）；
        # manual 别名保留 fail-closed 检查（CI 为第一道防线）
        # P3-2/R2：UNIQUE(org,entity,alias_norm) 冲突消解——同 norm 重复
        #（条目内）与既有 name/code/sync 别名撞 → 逐条 skip + 冲突记录
        taken = existing_alias_norms.get(eid, set())
        seen_norms: set[str] = set()
        pairs = []
        for spec, kind in [(a, "manual") for a in t.aliases] + \
                          [(a, "abbr") for a in t.abbr_specs()]:
            norm = normalize_alias(spec.value)
            if kind == "manual":
                blocked = _alias_blocked(spec)
                if blocked:  # 合并侧 fail-closed（CI 为第一道防线）
                    conflicts.append({"id": t.id, "reason": f"alias skipped: {blocked}"})
                    continue
            if not norm:
                conflicts.append({"id": t.id, "reason": "alias skipped: empty norm"})
                continue
            if norm in taken or norm in seen_norms:
                conflicts.append({
                    "id": t.id,
                    "reason": f"alias norm conflict skipped: {spec.value!r}"
                    f"（norm {norm!r} 已被 name/code/sync 或本条目占用）",
                })
                continue
            seen_norms.add(norm)
            pairs.append((spec.value, norm, kind, spec.match_mode))
        alias_rows.append({"type": t.type, "key": t.key, "aliases": pairs})

    written = backend.sem_write_curated_batch(org_id, curated_rows)
    backend.sem_replace_manual_aliases(org_id, alias_rows)

    # ---- extra_relations（人工补关系——规则表第 6/7 行） ----
    xr_pairs = [(e, xr) for e in corpus.entries for xr in e.extra_relations]
    endpoint_keys = sorted(
        {tuple(ref.split(":", 1)) for _, xr in xr_pairs for ref in (xr.src, xr.dst)}
    )
    endpoint_ids = (
        backend.resolve_entity_ids(org_id, [k for k in endpoint_keys if len(k) == 2])
        if endpoint_keys else {}
    )
    lookup_keys = []
    for _, xr in xr_pairs:
        src_id = endpoint_ids.get(tuple(xr.src.split(":", 1)))
        dst_id = endpoint_ids.get(tuple(xr.dst.split(":", 1)))
        if src_id is not None and dst_id is not None:
            lookup_keys.append((src_id, xr.rel, dst_id))
    existing = backend.sem_relations_lookup(org_id, lookup_keys) if lookup_keys else {}

    rel_rows: list[dict] = []
    for _, xr in xr_pairs:
        src_tk = tuple(xr.src.split(":", 1))
        dst_tk = tuple(xr.dst.split(":", 1))
        src_id, dst_id = endpoint_ids.get(src_tk), endpoint_ids.get(dst_tk)
        tag = f"{xr.rel} {xr.src}->{xr.dst}"
        if src_id is None or dst_id is None:
            missing = xr.src if src_id is None else xr.dst
            conflicts.append({"id": missing,
                              "reason": f"extra_relations endpoint not found ({tag})"})
            continue
        if not rel_type_allowed(xr.rel, src_tk[0], dst_tk[0]):
            conflicts.append({"id": tag,
                              "reason": "extra_relations endpoint types not in whitelist"})
            continue
        prior = existing.get((src_id, xr.rel, dst_id))
        if prior is not None and prior.get("source") == "sync":
            conflicts.append({"id": tag,
                              "reason": "duplicate of sync relation (can delete)"})
            continue
        rel_rows.append({
            "src_id": src_id, "rel_type": xr.rel, "dst_id": dst_id,
            "attrs_json": json.dumps(
                {"note": xr.note} if xr.note else {}, ensure_ascii=False),
            "synced_at": now, "source": "curated", "source_system": "yaml",
        })
    rel_written = 0
    if rel_rows:
        counts = backend.upsert_relations_batch(org_id, rel_rows)
        rel_written = counts["inserted"] + counts["updated"]

    # ---- YAML 删除覆盖项 → 清 curated 与 manual 别名（事实列不动——T-S1） ----
    cleared = backend.sem_clear_stale_curated(org_id, sorted(set(id_map.values())))

    stats = {
        "entities_written": written,
        "aliases_replaced": len(alias_rows),
        "relations_written": rel_written,
        # 在场关系键集（G-15 关系级消失检测的 hook 面——本轮回写的
        # extra_relations 不因 fetch 快照缺位而误判消失）
        "relation_keys": [
            [r["src_id"], r["rel_type"], r["dst_id"]] for r in rel_rows
        ],
        "curated_cleared": cleared,
        "conflicts": conflicts,
    }
    logger.info(
        "yaml merge: org=%s rev=%s written=%d cleared=%d conflicts=%d",
        org_id, rev, written, cleared, len(conflicts),
    )
    return stats
