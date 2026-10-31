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
- **关系级消失**（G-15——m2s-3 收口）：源端删除某条边但两端实体仍在 →
  本源 active 关系键集（per source_system）减快照键集 → `missing`（synced_at
  保留为宽限起算锚）；advance_status 同口推进超宽限关系 → `retired`
  （stats 单列 `relations_missing` / advance 返回 `relations_retired_standalone`）。
- **upsert 前端点状态过滤**（G-15 后半）：快照关系端点解析到非 active 实体
  → 记冲突不写入（'src/dst endpoint not active'——指向 retired 端点的关系
  不回 active；store upsert 的 CASE 守卫为第二道防线）。
- **维度属性载体 = attrs_json 结构化键 `dims`**（design §4 无 sem_entity_dims
  专表 DDL——最小实现；实体维度 ACL 为 NFR-5 演进缝、触发前不启用过滤，
  可见性不受影响；值域显式映射表 m2s-3 起随 YAML 仓 dim_value_map.yaml 维护
  ——run_sync 的 dim_value_map 参数承载，未映射值原样落库——records.py 同注）。
- **post_run 挂钩**（m2s-3）：_sync_records ⑤ 后、stats 组装前调用
  post_run(org_id, now) → 附加 stats（yaml 源的 curated 合并面——同 run
  留痕；缺省 None 零影响）。
- **填充率骤降告警阈值（本段定，可配）**：库内基线携带率 ≥
  `semantic_dim_alert_baseline`（默认 0.8）且快照携带率 < 基线 ×
  `semantic_dim_alert_drop`（默认 0.5）→ WARNING + stats.dims_fill.alert
  （参照删除比例保护的对冲——防缺值静默变宽，TC-SYNC-06②）。
- 步骤⑤后 design「投递 semantic_build」——m2s-2 起接入：**任务体** run_sync_task
  在 run 成功（succeeded）后投递 semantic_build 任务（run_sync 直调面不投递
  ——测试/重放路径零副作用；aborted_guard/failed 不触发）。
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
    finish_now: str | None = None,
    should_continue: Callable[[], bool] | None = None,
    force: bool = False,
    post_run: Callable[[str, str], dict] | None = None,
    dim_value_map: dict[str, dict[str, str]] | None = None,
) -> dict:
    """一个适配器一次同步 run（§5.8）。返回 {run_id, status, stats}。

    snapshot 显式注入（测试/重放）；缺省经 adapter.fetch(org) 取全量快照。
    finish_now：run 终态时刻（None=库时钟 CURRENT_TIMESTAMP——P3-2：finished_at
    不再恒等于 started_at）。force：跳过删除比例保护执行同步（B2 运维放行
    ——guard 告警仍发、stats.forced=True、审计事件记 forced）。失败路径：run
    落 failed + 审计事件后原异常上抛（调用方任务态处置）。
    post_run（m2s-3）：⑤ 后附加 stats 挂钩（yaml curated 合并面）；
    dim_value_map：维度值域显式映射（TC-SYNC-06——YAML 仓 dim_value_map.yaml）。
    """
    now = now or utc_now_ts()
    run_id = backend.sem_start_run(org_id, adapter.name, now=now)
    try:
        records = list(snapshot) if snapshot is not None else list(adapter.fetch(org_id))
        status, stats = _sync_records(
            backend, org_id, adapter, records, settings, now, should_continue,
            force, post_run=post_run, dim_value_map=dim_value_map,
        )
    except BaseException as exc:
        logger.exception(
            "semantic sync failed: org=%s adapter=%s", org_id, adapter.name
        )
        # P3-r1（m2s-1 移交）：失败路径 stats 补 forced 键——run 行与审计事件
        # 都保留 force 语义（此前仅 stats_json="{}" + error，forced 语义丢失）
        fail_stats = {"error": str(exc), "forced": bool(force)}
        backend.sem_finish_run(
            org_id, run_id, status="failed",
            stats_json=json.dumps(fail_stats, ensure_ascii=False, default=str),
            error=str(exc), now=finish_now,
        )
        _audit_sync(backend, org_id, adapter.name, run_id, "failed", fail_stats)
        raise
    backend.sem_finish_run(
        org_id, run_id, status=status,
        stats_json=json.dumps(stats, ensure_ascii=False, default=str), now=finish_now,
    )
    _audit_sync(backend, org_id, adapter.name, run_id, status, stats)
    logger.info(
        "semantic sync done: org=%s adapter=%s status=%s stats=%s",
        org_id, adapter.name, status, stats,
    )
    return {"run_id": run_id, "status": status, "stats": stats}


# ---- 流程主体 ----


def _check_alive(should_continue) -> None:
    """批/段边界存活检查（m2-1 阶段边界口径——取消/失租约不等整轮；P3-3：
    实体批、别名重建、关系批三处边界统一走本口）。"""
    if should_continue is not None and not should_continue():
        raise SyncInterrupted("sync interrupted at batch boundary (lease lost/cancelled)")


def _sync_records(backend, org_id, adapter, records, settings, now, should_continue,
                  force=False, *, post_run=None, dim_value_map=None):
    dedup: dict[tuple[str, str], EntityRecord] = {}
    for rec in records:
        if isinstance(rec, EntityRecord):
            dedup[(rec.type, rec.key)] = rec  # 快照内后到覆盖（分页拼装语义）
    entities = list(dedup.values())
    relations = [r for r in records if isinstance(r, RelationRecord)]
    snap_keys = set(dedup)
    relation_source = getattr(adapter, "relation_source", "sync")

    # P2-2/R2（规则表第 3 行）：curated 源（yaml）的纯人工条目与同步实体
    # (type,key) 相同 → **写入前**剔除该键的实体 upsert 与别名重建（同步实体
    # name/attrs/parent/source_system/三类别名原样不动、不移出原源基数——否则
    # YAML 侧后续删除会把同步实体误标 missing）；其关系一并剔除；冲突随
    # stats.entity_conflicts 留痕（curated.conflicts 由合并钩子同记）。
    entity_conflicts: list[dict] = []
    if relation_source == "curated" and entities:
        pre_ids = backend.resolve_entity_ids(
            org_id, sorted({(e.type, e.key) for e in entities}))
        pre_states = (
            backend.sem_entity_states(org_id, sorted(pre_ids.values()))
            if pre_ids else {}
        )
        collided = {
            key for key, eid in pre_ids.items()
            if pre_states.get(eid, {}).get("source") == "sync"
        }
        if collided:
            entities = [e for e in entities if (e.type, e.key) not in collided]
            relations = [r for r in relations
                         if tuple(r.src) not in collided
                         and tuple(r.dst) not in collided]
            entity_conflicts = [
                {"id": f"{t}:{k}",
                 "reason": "pure entry collides with synced entity (type,key)"
                           " —— synced entity untouched"}
                for t, k in sorted(collided)
            ]
            logger.warning(
                "yaml pure entries collide with synced entities: org=%s keys=%s"
                "（写入前剔除——规则表第 3 行）",
                org_id, sorted(f"{t}:{k}" for t, k in collided),
            )

    # ③ 删除比例保护（先于一切写入——T-S2 零写入语义；force=B2 运维放行）
    active_keys = backend.sem_active_source_keys(org_id, adapter.name)
    vanished = active_keys - snap_keys
    guard_hit = bool(
        active_keys and len(vanished) > settings.semantic_delete_guard * len(active_keys)
    )
    guard_info: dict | None = None
    if guard_hit:
        ratio = len(vanished) / len(active_keys)
        guard_info = {"active": len(active_keys), "vanished": len(vanished),
                      "ratio": ratio, "threshold": settings.semantic_delete_guard}
        logger.warning(  # 告警恒发（force 放行也告警——引用面收缩的可见信号）
            "semantic sync delete-guard %s: org=%s adapter=%s active=%d"
            " vanished=%d ratio=%.3f > %.2f%s",
            "aborted (zero writes)" if not force else "OVERRIDDEN by force",
            org_id, adapter.name, len(active_keys), len(vanished), ratio,
            settings.semantic_delete_guard,
            "" if not force else " — force 放行执行同步（B2）",
        )
        if not force:
            return "aborted_guard", {
                "inserted": 0, "updated": 0, "missing": 0, "retired": 0,
                "conflicts": [], "forced": False,
                "guard": guard_info,
            }

    # 维度填充率库内基线（本 run 写入前——骤降判定基准）
    lib = backend.sem_source_fill_stats(org_id, adapter.name)
    lib_ratio = (lib["filled"] / lib["total"]) if lib["total"] else None

    # ④① 实体分批 upsert（父先子后）+ ④④ 同批别名重建（段边界存活检查——P3-3）
    inserted = updated = batches = 0
    for chunk in _chunks(_order_entities(entities), settings.semantic_batch_rows):
        _check_alive(should_continue)
        counts = backend.upsert_entities_batch(
            org_id, [_entity_row(e, adapter.name, now, relation_source,
                                 dim_value_map) for e in chunk]
        )
        inserted += counts["inserted"]
        updated += counts["updated"]
        batches += 1
        _check_alive(should_continue)  # 别名重建前边界（upsert 已提交、重建未起）
        backend.rebuild_sync_aliases(org_id, [_alias_row(e) for e in chunk])

    # ④② 快照消失实体 → missing
    missing = 0
    if vanished:
        ids = backend.resolve_entity_ids(org_id, sorted(vanished))
        missing = backend.mark_entities_missing(org_id, list(ids.values()))

    # ④③ 关系 upsert + 端点冲突（明细结构为 #40 P2 测试约定；G-15 端点状态
    # 过滤——retired 端点记冲突不写入〔指向 retired 端点的关系不回 active〕，
    # missing 端点放行由 store CASE 守卫落潜伏态。N4/R2 注：**已 active** 的
    # 关系行在端点 missing 窗口内保持 active（UPDATE CASE 不降级）——展开侧
    # sem_expand_graph 只走两端 active，missing 端点的边不可见；超期由端点
    # retired 的级联收口——不留可见悬挂边）
    conflicts: list[dict] = []
    rel_rows: list[dict] = []
    endpoint_keys = sorted(
        {tuple(r.src) for r in relations} | {tuple(r.dst) for r in relations}
    )
    id_map = backend.resolve_entity_ids(org_id, endpoint_keys)
    endpoint_states = (
        backend.sem_entity_states(org_id, sorted(id_map.values()))
        if id_map else {}
    )
    for rel in relations:
        src_id = id_map.get(tuple(rel.src))
        dst_id = id_map.get(tuple(rel.dst))
        conflict = {"src": _type_key(rel.src), "dst": _type_key(rel.dst),
                    "rel_type": rel.rel_type}
        if src_id is None:
            conflicts.append({**conflict, "reason": "src endpoint not found"})
        elif dst_id is None:
            conflicts.append({**conflict, "reason": "dst endpoint not found"})
        elif endpoint_states.get(src_id, {}).get("status") == "retired":
            conflicts.append({**conflict, "reason": "src endpoint retired"})
        elif endpoint_states.get(dst_id, {}).get("status") == "retired":
            conflicts.append({**conflict, "reason": "dst endpoint retired"})
        elif not rel_type_allowed(rel.rel_type, rel.src[0], rel.dst[0]):
            # 防御（适配器不该产出；库内 trg_sem_rel_check 为最后防线——T-S5）
            conflicts.append({**conflict, "reason": "endpoint types not in whitelist"})
        else:
            # missing 端点放行（宽限期内可恢复——store INSERT/UPDATE 的 CASE
            # 守卫将其落为 missing 潜伏态，端点恢复后下轮 upsert 置回 active）
            rel_rows.append({
                "src_id": src_id, "rel_type": rel.rel_type, "dst_id": dst_id,
                "attrs_json": json.dumps(rel.attrs or {}, ensure_ascii=False,
                                         sort_keys=True),
                "synced_at": now,
                "source": relation_source, "source_system": adapter.name,
            })
    rel_inserted = rel_updated = 0
    for chunk in _chunks(rel_rows, settings.semantic_batch_rows):
        _check_alive(should_continue)  # 关系批边界（P3-3——取消不等整轮）
        counts = backend.upsert_relations_batch(org_id, chunk)
        rel_inserted += counts["inserted"]
        rel_updated += counts["updated"]

    # ④③b post_run 挂钩（m2s-3——yaml curated 合并面：curated_json/manual 别名/
    # extra_relations；须先于关系级消失标记——hook 写入的关系即「在场」键集）
    stats_extra: dict = {}
    if post_run is not None:
        stats_extra = post_run(org_id, now) or {}

    # ④③c 关系级消失（G-15）：本源 active 关系 − 在场键集 → missing
    # （源端独立删边、两端实体仍在；synced_at 保留为宽限起算锚；在场集 =
    # 快照关系 ∪ hook 写入关系〔stats_extra.relation_keys〕）
    relations_missing = 0
    present_rel_keys = {(r["src_id"], r["rel_type"], r["dst_id"]) for r in rel_rows}
    present_rel_keys |= {
        tuple(k) for k in stats_extra.get("relation_keys", ())
    }
    lib_rel_keys = backend.sem_active_source_relation_keys(org_id, adapter.name)
    vanished_rels = lib_rel_keys - present_rel_keys
    if vanished_rels:
        relations_missing = backend.sem_mark_relations_missing(
            org_id, sorted(vanished_rels))

    # ⑤ 宽限期推进（超期 missing → retired + 关系联动——顺序注记见模块 docstring；
    #    推进口径为 org 全量、不按 source_system 收口——多适配器共享同一时间窗，
    #    本段接受口径〔P3-8〕，按源收口归后续段需要时再议；G-15：关系级 missing
    #    同口推进——relations_retired_standalone）
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
        "entity_conflicts": entity_conflicts,
        "relations_inserted": rel_inserted, "relations_updated": rel_updated,
        "relations_missing": relations_missing,
        "relations_retired": advanced["relations_retired"],
        "relations_retired_standalone": advanced.get("relations_retired_standalone", 0),
        "batches": batches, "dims_fill": dims_fill, "forced": bool(force),
    }
    if stats_extra:
        stats["curated"] = stats_extra
    if guard_info is not None:
        # P3-r2（m2s-1 移交）：force 覆盖 guard 的 stats 补 guard 明细——
        # 引用面收缩幅度（active/vanished/ratio/threshold）随 run 留痕
        stats["guard"] = guard_info
    return "succeeded", stats


# ---- worker 任务入口（semantic_sync 任务类型——payload {org, adapter}） ----


def run_sync_task(backend, settings: Settings, task_id: str, *,
                  should_continue: Callable[[], bool] | None = None) -> dict:
    """semantic_sync 任务体（worker executor 调用——自管任务行状态）。

    payload：{org, adapter, force?}——force=true 经 B2 运维放行跳过删除比例保护。
    m2s-3：yaml 适配器挂 curated 合并钩子（post_run）+ 值域映射装载；适配器
    传输资源 finally 显式关闭（C.6——默认 HTTP 传输持有 httpx.Client）。"""
    from knowledge_lattice.core.semantic.adapters import (
        build_adapter, close_adapter, load_dim_value_map,
    )

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

    post_run = None
    if adapter_name == "yaml":
        from knowledge_lattice.core.semantic.yaml_merge import make_merge_hook

        post_run = make_merge_hook(backend, adapter.corpus())
    dim_map = load_dim_value_map(settings, org_id)
    try:
        result = run_sync(
            backend, org_id, adapter, settings=settings,
            should_continue=should_continue, force=bool(payload.get("force")),
            post_run=post_run, dim_value_map=dim_map,
        )
    finally:
        close_adapter(adapter)  # C.6：sync 路径传输资源不泄漏
    backend.update_task(task_id, status="done")
    if result["status"] == "succeeded":
        # design §5.8「同步或 YAML 合并后触发构建」——成功 run 后投递
        # semantic_build 任务（worker 循环/kick 顺带消化；dict_rev 相同则
        # 构建侧自跳过——TC-BUILD-01，不产冗余 build 行）
        backend.create_task(
            None, task_type="semantic_build",
            payload=json.dumps({"org": org_id}),
        )
    return result


# ---- 内部工具 ----


def _audit_sync(backend, org_id, adapter_name, run_id, status, stats) -> None:
    """semantic.sync 审计事件（成功/aborted_guard/failed 全终态——TC-SYNC-07；
    force 放行显式记 forced——B2）。"""
    backend.append_outbox(
        EVENT_SEMANTIC_SYNC,
        json.dumps(
            {"org_id": org_id, "adapter": adapter_name, "run_id": run_id,
             "status": status, "forced": bool(stats.get("forced")) if isinstance(stats, dict) else False,
             "stats": stats},
            ensure_ascii=False, default=str,
        ),
    )


def _entity_row(e: EntityRecord, source_system: str, now: str,
                source: str = "sync",
                dim_value_map: dict[str, dict[str, str]] | None = None) -> dict:
    """EntityRecord → upsert 行（维度随 attrs_json.dims 结构化承载——见模块注记；
    值域显式映射先于落库：dim → {源值: 本地值}，未映射值原样——TC-SYNC-06）。"""
    attrs = dict(e.attrs)
    if e.dims:
        mapped = dict(e.dims)
        for dim, value in list(mapped.items()):
            mapped[dim] = (dim_value_map or {}).get(dim, {}).get(value, value)
        attrs["dims"] = mapped
    return {
        "type": e.type, "key": e.key, "name": e.name,
        "attrs_json": json.dumps(attrs, ensure_ascii=False, sort_keys=True),
        "parent_key": e.parent_key, "source_system": source_system,
        "synced_at": now, "source": source,
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
