"""同步流程编排（design §5.8——每个适配器一次 run；core 纯编排、SQL 全下沉
store Semantic 域）。

流程（§5.8 六步 + m2s-1 实现注记）：

1. `sem_sync_runs` 落 running 记录；
2. `fetch()` 全量快照 → 实体 (type,key) 集合（快照内去重）；
3. **删除比例保护**（T-S2）：快照相对库内该来源 active 实体
   （source='sync' AND source_system=本适配器 AND status='active'——基数口径
   #38 P2）消失比例 > 阈值（默认 20%，可配）→ run 置 `aborted_guard`、
   告警日志、**零写入**；
4. 分批 upsert（每批 ≤ semantic_batch_rows 行、单批单事务——NFR-11；批间
   失败重跑幂等，TC-SYNC-03）：①实体只写事实列 + status='active' +
   synced_at（**从不写 curated_json**——T-S1 列级分工）；②快照消失实体 →
   missing；③关系 upsert（端点解析不到/白名单外记冲突不写入——TC-SYNC-04，
   明细结构 {src, dst, rel_type, reason} 为 #40 P2 测试约定）；④别名
   name/code/sync 三 kind 先删后插（manual/abbr 原样——TC-SYNC-05）；
5. **宽限期推进**（T-S4）：missing 且 synced_at < now−grace_days → retired
   且其 active 关系一并 retired；
6. run 终态 + stats_json + `semantic.sync` 审计 outbox 事件（TC-SYNC-07）。

实现决策注记（与 design §5.8 字面顺序的差异申报）：

- **步骤⑤宽限推进在关系 upsert 之后**（design 列序 ③ 先于 ④）：快照内指向
  missing 实体的关系先落 active、随后被 advance 随端点一并 retired——避免
  「先 retire 端点、后写 active 关系」的悬挂态；T-S4 断言语义不变。
- **关系消失标记**（源端删除某条边但两端实体仍在）design 流程未列——本段
  不做关系级 missing（status 列已留位，演进缝；实体退役联动已覆盖主路径）。
- **维度属性载体 = attrs_json 结构化键 `dims`**（design §4 无 sem_entity_dims
  专表 DDL——最小实现；实体维度 ACL 为 NFR-5 演进缝、触发前不启用过滤，
  可见性不受影响；值域显式映射表归 m2s-3 YAML 链——records.py 同注）。
- **填充率骤降告警阈值（本段定，可配）**：库内基线携带率 ≥
  `semantic_dim_alert_baseline`（默认 0.8）且快照携带率 < 基线 ×
  `semantic_dim_alert_drop`（默认 0.5）→ WARNING + stats.dims_fill.alert
  （参照删除比例保护的对冲——防缺值静默变宽，TC-SYNC-06②）。
- 步骤⑤后 design 还有「投递 semantic_build」——构建归 m2s-2（本段无动作）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence

from knowledge_lattice.config import Settings
from knowledge_lattice.core.semantic.constants import rel_type_allowed
from knowledge_lattice.core.semantic.norm import normalize_alias
from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord
from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_SYNC
from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

logger = logging.getLogger(__name__)

__all__ = ["run_sync", "run_sync_task", "SyncInterrupted"]


class SyncInterrupted(RuntimeError):
    """批间存活检查失守（任务取消/租约丢失）——run 落 failed、可重跑续齐。"""


def run_sync(
    backend,
    org_id: str,
    adapter,
    *,
    settings: Settings,
    snapshot: Sequence | None = None,
    now: str | None = None,
    should_continue: Callable[[], bool] | None = None,
) -> dict:
    """一个适配器一次同步 run（§5.8）。返回 {run_id, status, stats}。

    snapshot 显式注入（测试/重放）；缺省经 adapter.fetch(org) 取全量快照。
    失败路径：run 落 failed + 审计事件后原异常上抛（调用方任务态处置）。
    """
    now = now or utc_now_ts()
    run_id = backend.sem_start_run(org_id, adapter.name, now=now)
    try:
        records = list(snapshot) if snapshot is not None else list(adapter.fetch(org_id))
        status, stats = _sync_records(
            backend, org_id, adapter, records, settings, now, should_continue
        )
    except BaseException as exc:
        logger.exception(
            "semantic sync failed: org=%s adapter=%s", org_id, adapter.name
        )
        backend.sem_finish_run(
            org_id, run_id, status="failed", stats_json="{}",
            error=str(exc), now=now,
        )
        _audit_sync(backend, org_id, adapter.name, run_id, "failed", {"error": str(exc)})
        raise
    backend.sem_finish_run(
        org_id, run_id, status=status,
        stats_json=json.dumps(stats, ensure_ascii=False, default=str), now=now,
    )
    _audit_sync(backend, org_id, adapter.name, run_id, status, stats)
    logger.info(
        "semantic sync done: org=%s adapter=%s status=%s stats=%s",
        org_id, adapter.name, status, stats,
    )
    return {"run_id": run_id, "status": status, "stats": stats}


# ---- 流程主体 ----


def _sync_records(backend, org_id, adapter, records, settings, now, should_continue):
    dedup: dict[tuple[str, str], EntityRecord] = {}
    for rec in records:
        if isinstance(rec, EntityRecord):
            dedup[(rec.type, rec.key)] = rec  # 快照内后到覆盖（分页拼装语义）
    entities = list(dedup.values())
    relations = [r for r in records if isinstance(r, RelationRecord)]
    snap_keys = set(dedup)

    # ③ 删除比例保护（先于一切写入——T-S2 零写入语义）
    active_keys = backend.sem_active_source_keys(org_id, adapter.name)
    vanished = active_keys - snap_keys
    if active_keys and len(vanished) > settings.semantic_delete_guard * len(active_keys):
        ratio = len(vanished) / len(active_keys)
        logger.warning(
            "semantic sync delete-guard aborted: org=%s adapter=%s active=%d"
            " vanished=%d ratio=%.3f > %.2f — zero writes (T-S2)",
            org_id, adapter.name, len(active_keys), len(vanished), ratio,
            settings.semantic_delete_guard,
        )
        return "aborted_guard", {
            "inserted": 0, "updated": 0, "missing": 0, "retired": 0,
            "conflicts": [],
            "guard": {"active": len(active_keys), "vanished": len(vanished),
                      "ratio": ratio, "threshold": settings.semantic_delete_guard},
        }

    # 维度填充率库内基线（本 run 写入前——骤降判定基准）
    lib = backend.sem_source_fill_stats(org_id, adapter.name)
    lib_ratio = (lib["filled"] / lib["total"]) if lib["total"] else None

    # ④① 实体分批 upsert（父先子后）+ ④④ 同批别名重建
    inserted = updated = batches = 0
    for chunk in _chunks(_order_entities(entities), settings.semantic_batch_rows):
        if should_continue is not None and not should_continue():
            raise SyncInterrupted(
                "sync interrupted between batches (lease lost/cancelled)"
            )
        counts = backend.upsert_entities_batch(
            org_id, [_entity_row(e, adapter.name, now) for e in chunk]
        )
        inserted += counts["inserted"]
        updated += counts["updated"]
        batches += 1
        backend.rebuild_sync_aliases(org_id, [_alias_row(e) for e in chunk])

    # ④② 快照消失实体 → missing
    missing = 0
    if vanished:
        ids = backend.resolve_entity_ids(org_id, sorted(vanished))
        missing = backend.mark_entities_missing(org_id, list(ids.values()))

    # ④③ 关系 upsert + 端点冲突（明细结构为 #40 P2 测试约定）
    conflicts: list[dict] = []
    rel_rows: list[dict] = []
    endpoint_keys = sorted(
        {tuple(r.src) for r in relations} | {tuple(r.dst) for r in relations}
    )
    id_map = backend.resolve_entity_ids(org_id, endpoint_keys)
    for rel in relations:
        src_id = id_map.get(tuple(rel.src))
        dst_id = id_map.get(tuple(rel.dst))
        conflict = {"src": _type_key(rel.src), "dst": _type_key(rel.dst),
                    "rel_type": rel.rel_type}
        if src_id is None:
            conflicts.append({**conflict, "reason": "src endpoint not found"})
        elif dst_id is None:
            conflicts.append({**conflict, "reason": "dst endpoint not found"})
        elif not rel_type_allowed(rel.rel_type, rel.src[0], rel.dst[0]):
            # 防御（适配器不该产出；库内 trg_sem_rel_check 为最后防线——T-S5）
            conflicts.append({**conflict, "reason": "endpoint types not in whitelist"})
        else:
            rel_rows.append({
                "src_id": src_id, "rel_type": rel.rel_type, "dst_id": dst_id,
                "attrs_json": json.dumps(rel.attrs or {}, ensure_ascii=False,
                                         sort_keys=True),
                "synced_at": now,
            })
    rel_inserted = rel_updated = 0
    for chunk in _chunks(rel_rows, settings.semantic_batch_rows):
        counts = backend.upsert_relations_batch(org_id, chunk)
        rel_inserted += counts["inserted"]
        rel_updated += counts["updated"]

    # ⑤ 宽限期推进（超期 missing → retired + 关系联动——顺序注记见模块 docstring）
    advanced = backend.advance_status(
        org_id, missing_before=add_seconds(now, -settings.semantic_grace_days * 86400)
    )

    # 维度填充率骤降告警（口径见模块 docstring）
    dims_fill = _dims_fill_stats(entities, lib_ratio, settings)
    if dims_fill["alert"]:
        logger.warning(
            "semantic sync dim fill-rate drop: org=%s adapter=%s library=%.2f"
            " snapshot=%.2f (< library×%.2f) — 缺值面骤降，检查源端维度携带",
            org_id, adapter.name, lib_ratio or 0.0, dims_fill["snapshot"],
            settings.semantic_dim_alert_drop,
        )

    stats = {
        "inserted": inserted, "updated": updated, "missing": missing,
        "retired": advanced["retired"], "conflicts": conflicts,
        "relations_inserted": rel_inserted, "relations_updated": rel_updated,
        "relations_retired": advanced["relations_retired"],
        "batches": batches, "dims_fill": dims_fill,
    }
    return "succeeded", stats


# ---- worker 任务入口（semantic_sync 任务类型——payload {org, adapter}） ----


def run_sync_task(backend, settings: Settings, task_id: str, *,
                  should_continue: Callable[[], bool] | None = None) -> dict:
    """semantic_sync 任务体（worker executor 调用——自管任务行状态）。"""
    from knowledge_lattice.core.semantic.adapters import build_adapter

    task = backend.get_task(task_id)
    if task is None:
        raise RuntimeError(f"semantic_sync task not found: {task_id!r}")
    try:
        payload = json.loads(task.get("payload") or "{}")
    except ValueError as exc:
        raise RuntimeError(
            f"semantic_sync task payload not JSON: {task.get('payload')!r}"
        ) from exc
    try:
        org_id, adapter_name = payload["org"], payload["adapter"]
    except KeyError as exc:
        raise RuntimeError(
            f"semantic_sync task payload missing {exc}: {payload!r}"
        ) from exc
    backend.update_task(task_id, status="running")
    adapter = build_adapter(adapter_name, org_id, settings)
    result = run_sync(
        backend, org_id, adapter, settings=settings, should_continue=should_continue
    )
    backend.update_task(task_id, status="done")
    return result


# ---- 内部工具 ----


def _audit_sync(backend, org_id, adapter_name, run_id, status, stats) -> None:
    """semantic.sync 审计事件（成功/aborted_guard/failed 全终态——TC-SYNC-07）。"""
    backend.append_outbox(
        EVENT_SEMANTIC_SYNC,
        json.dumps(
            {"org_id": org_id, "adapter": adapter_name, "run_id": run_id,
             "status": status, "stats": stats},
            ensure_ascii=False, default=str,
        ),
    )


def _entity_row(e: EntityRecord, source_system: str, now: str) -> dict:
    """EntityRecord → upsert 行（维度随 attrs_json.dims 结构化承载——见模块注记）。"""
    attrs = dict(e.attrs)
    if e.dims:
        attrs["dims"] = dict(e.dims)
    return {
        "type": e.type, "key": e.key, "name": e.name,
        "attrs_json": json.dumps(attrs, ensure_ascii=False, sort_keys=True),
        "parent_key": e.parent_key, "source_system": source_system, "synced_at": now,
    }


def _alias_row(e: EntityRecord) -> dict:
    """name/code/sync 三 kind 别名（norm 去重保首——name > code > sync 优先）。"""
    seen: set[str] = set()
    pairs: list[tuple[str, str, str]] = []
    for alias, kind in ((e.name, "name"), (e.key, "code"),
                        *((a, "sync") for a in e.aliases)):
        norm = normalize_alias(alias)
        if norm and norm not in seen:
            seen.add(norm)
            pairs.append((alias, norm, kind))
    return {"type": e.type, "key": e.key, "aliases": pairs}


def _order_entities(entities: list[EntityRecord]) -> list[EntityRecord]:
    """父先子后（层级一跳：字段→模板/列→表/项→报表——设计类型系单层父子）。"""
    snap_keys = {(e.type, e.key) for e in entities}

    def level(e: EntityRecord) -> int:
        if not e.parent_key or ":" not in e.parent_key:
            return 0
        ptype, _, pkey = e.parent_key.partition(":")
        return 1 if (ptype, pkey) in snap_keys else 0

    return sorted(entities, key=level)


def _dims_fill_stats(entities, lib_ratio, settings: Settings) -> dict:
    total = len(entities)
    filled = sum(1 for e in entities if e.dims)
    snap_ratio = (filled / total) if total else None
    alert = bool(
        lib_ratio is not None
        and lib_ratio >= settings.semantic_dim_alert_baseline
        and (snap_ratio if snap_ratio is not None else 0.0)
        < lib_ratio * settings.semantic_dim_alert_drop
    )
    return {
        "carried": filled > 0 or bool(lib_ratio),
        "library": lib_ratio, "snapshot": snap_ratio,
        "filled": filled, "total": total, "alert": alert,
    }


def _type_key(tk: tuple[str, str]) -> str:
    return f"{tk[0]}:{tk[1]}"


def _chunks(seq, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]
