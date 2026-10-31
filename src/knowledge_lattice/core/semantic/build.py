"""semantic_build 构建编排（design §5.8 构建产物 / §8 M2-S1 第 3 项——m2s-2
骨架段；core 纯编排、SQL 全下沉 store Semantic 域）。

流程（§5.8 四步的骨架实现——AC 自动机/模糊索引/L0 片段归 M2-S2 后段，
本段交付 dict_rev 计算 + 原子切换 + 构建报告统计）：

1. **快照读取**：active 实体 + 全部别名（manual/abbr 含——人工别名变更同样
   触发新 rev）+ active 关系（store.sem_active_snapshot）；
2. **dict_rev 计算**：`hash(active 实体 + 别名 + yaml_rev + embed_model 标签)`
   ——**embed_model 标签必须进输入**（#42 P1-2：换模型 → rev 变 → 「相同跳过」
   失效、强制重建；§5.3 重嵌入④）。与当前 ready 版本相同 → 跳过（不产新行，
   TC-BUILD-01）；快照排除 synced_at/updated_at 等易变列——纯内容变更语义；
3. **原子切换**：building 行 upsert → 单语句 building→ready（旧行不动——
   design §4 status 枚举无 superseded，「当前」= 最新 ready 行，旧 ready 保留
   服务〔§5.8 懒加载语义〕）；失败路径 building→failed + error 载 stats，旧
   ready 继续为当前（T-S12 骨架半句——失败不切指针）；
4. **审计**：`semantic.build` 事件全终态入 outbox（ready/skipped/failed——
   TC-BUILD-03，#38 P1-7）。

评测回归门槛（>2pp 不切 ready）与重标投递（semantic_retag）归后续段
（TC-BUILD-04/05——依赖评测指标与打标面）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable

from knowledge_lattice.config import Settings
from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_BUILD

logger = logging.getLogger(__name__)

__all__ = ["run_build", "run_build_task", "compute_dict_rev"]


def compute_dict_rev(
    snapshot: dict, *, embed_model_label: str, yaml_rev: str | None = None
) -> str:
    """dict_rev = hash(active 实体〔含 curated_json——G-17/m2s-3〕+ 别名 +
    yaml_rev + embed_model 标签) 前 12 hex。

    规范化序列化（排序 + 紧凑分隔）保证同快照双方言同 rev；parent_id 以 -1
    规避 None 与 int 的排序比较。curated_json 入实体元组 + yaml_rev 入顶层
    输入——YAML 改 definition 必触发重建（§5.8 构建产物第 1 步，双保险）。"""
    payload = {
        "embed_model": embed_model_label,
        "yaml_rev": yaml_rev or "",
        "entities": sorted(
            [str(e["id"]), e["type"], e["key"], e["name"],
             str(e["parent_id"] if e["parent_id"] is not None else -1),
             e["attrs_json"], e["sensitivity"],
             e.get("curated_json") or "{}"]
            for e in snapshot["entities"]
        ),
        "aliases": sorted(
            [str(a["entity_id"]), a["alias_norm"], a["kind"],
             a["match_mode"], str(a["weight"])]
            for a in snapshot["aliases"]
        ),
        "relations": sorted(
            [str(r["src_id"]), r["rel_type"], str(r["dst_id"]), r["attrs_json"]]
            for r in snapshot["relations"]
        ),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _yaml_rev_of(snapshot: dict) -> str | None:
    """yaml_rev = active 实体 curated_rev 的字典序最大值（最近一次合并的
    corpus rev——全量合并语义下即当前 YAML 仓 rev；无 curated 实体为 None）。"""
    revs = [e.get("curated_rev") for e in snapshot["entities"] if e.get("curated_rev")]
    return max(revs) if revs else None


def _build_stats(snapshot: dict) -> dict:
    """构建报告骨架（§5.8 产物之「构建报告」——冲突面归 sync run、此处为图统计
    与结构异常：歧义别名 / 孤立节点；评测指标归后续段）。"""
    entities_by_type: dict[str, int] = {}
    for e in snapshot["entities"]:
        entities_by_type[e["type"]] = entities_by_type.get(e["type"], 0) + 1
    relations_by_type: dict[str, int] = {}
    linked: set[int] = set()
    for r in snapshot["relations"]:
        relations_by_type[r["rel_type"]] = relations_by_type.get(r["rel_type"], 0) + 1
        linked.add(r["src_id"])
        linked.add(r["dst_id"])
    by_norm: dict[str, set[int]] = {}
    for a in snapshot["aliases"]:
        by_norm.setdefault(a["alias_norm"], set()).add(a["entity_id"])
    ambiguous = [
        {"alias_norm": norm, "entity_ids": sorted(ids)}
        for norm, ids in sorted(by_norm.items()) if len(ids) > 1
    ]
    return {
        "entities": len(snapshot["entities"]),
        "entities_by_type": entities_by_type,
        "aliases": len(snapshot["aliases"]),
        "relations": len(snapshot["relations"]),
        "relations_by_type": relations_by_type,
        "ambiguous_aliases": ambiguous,
        "orphan_nodes": sum(1 for e in snapshot["entities"]
                            if e["id"] not in linked),
    }


def _audit_build(backend, org_id: str, status: str, stats: dict) -> None:
    """semantic.build 事件（ready/skipped/failed 全终态——TC-BUILD-03）。"""
    from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_BUILD

    backend.append_outbox(
        EVENT_SEMANTIC_BUILD,
        json.dumps(
            {"org_id": org_id, "status": status, **stats}, ensure_ascii=False,
            default=str,
        ),
    )


def run_build(
    backend,
    org_id: str,
    *,
    settings: Settings,
    should_continue: Callable[[], bool] | None = None,
) -> dict:
    """一次构建 run（§5.8——返回 {build_id?, dict_rev, status, stats}）。

    - dict_rev 与当前 ready 相同 → skipped（不产新行——TC-BUILD-01）；
    - **G-17/m2s-3**：curated_json 入快照、yaml_rev（=max curated_rev）入
      dict_rev 输入与 build 行——YAML 改 definition 必触发重建；
    - **G-18/O-1/m2s-3**：sem_insert_build 条件 upsert——同 rev 行已 ready
      时不重断 building（无 flap）；此时若 current 已同 rev → skipped 让位
      （并发赢家），否则 **重激活**（顶置 activated_at 成为 current——rev
      回退场景 current 不失真，sem_reactivate_build + ready 事件同事务）；
    - ready/failed 事件与终态行**同一事务**（store switch/fail 的 audit=——
      P3-5/R2，沿 create_task 先例；G-16 构建侧收口）；
    - 切换无效且 current 已是同 rev ready（并发输者——P2-2/R2）→ 按 skipped
      返回：不抛错（不触发任务重试）、不写 failed 事件（赢家已记录 ready）；
    - 其余失败 → building 行置 failed（仅真生效写事件）+ 异常上抛。"""
    build_id: int | None = None
    dict_rev: str | None = None
    try:
        snapshot = backend.sem_active_snapshot(org_id)
        yaml_rev = _yaml_rev_of(snapshot)
        dict_rev = compute_dict_rev(
            snapshot, embed_model_label=settings.embed_model_label,
            yaml_rev=yaml_rev,
        )
        current = backend.sem_current_build(org_id)
        if current is not None and current["dict_rev"] == dict_rev:
            stats = {"skipped": True, "current_build_id": current["id"]}
            _audit_build(backend, org_id, "skipped",
                         {"build_id": current["id"], "dict_rev": dict_rev,
                          "stats": stats})
            logger.info("semantic build skipped (dict_rev unchanged): org=%s rev=%s",
                        org_id, dict_rev)
            return {"build_id": current["id"], "dict_rev": dict_rev,
                    "status": "skipped", "stats": stats}

        if should_continue is not None and not should_continue():
            raise BuildInterrupted("build interrupted before switch (lease lost)")
        stats = _build_stats(snapshot)
        stats_json = json.dumps(stats, ensure_ascii=False, default=str)
        build_id, was_ready = backend.sem_insert_build(
            org_id, dict_rev, stats_json, yaml_rev=yaml_rev)
        if was_ready:
            # O-1：同 rev 行已 ready——并发赢家让位或 rev 回退重激活（G-18）
            now_current = backend.sem_current_build(org_id)
            if now_current is not None and now_current["dict_rev"] == dict_rev:
                stats_skip = {"skipped": True, "current_build_id": now_current["id"],
                              "reason": "concurrent-ready"}
                logger.info(
                    "semantic build ceded to concurrent winner: org=%s rev=%s"
                    " current_build=%s", org_id, dict_rev, now_current["id"])
                return {"build_id": now_current["id"], "dict_rev": dict_rev,
                        "status": "skipped", "stats": stats_skip}
            backend.sem_reactivate_build(
                org_id, build_id, stats_json,
                audit=(
                    EVENT_SEMANTIC_BUILD,
                    json.dumps({"org_id": org_id, "build_id": build_id,
                                "dict_rev": dict_rev, "status": "ready",
                                "stats": stats, "reactivated": True},
                               ensure_ascii=False, default=str),
                ),
            )
            logger.info("semantic build reactivated (rev rollback): org=%s"
                        " build=%s rev=%s", org_id, build_id, dict_rev)
            return {"build_id": build_id, "dict_rev": dict_rev, "status": "ready",
                    "stats": stats}
        ready_audit = (
            EVENT_SEMANTIC_BUILD,
            json.dumps({"org_id": org_id, "build_id": build_id, "dict_rev": dict_rev,
                        "status": "ready", "stats": stats},
                       ensure_ascii=False, default=str),
        )
        if not backend.sem_switch_build_ready(org_id, build_id, stats_json,
                                              audit=ready_audit):
            # P2-2/R2：rowcount=0——行非 building。若 current 已是同 rev ready
            #（并发赢家先切），本执行者按 skipped 收场（不抛错不重试不写
            # failed 事件——行终态与 ready 事件属赢家）；否则才是真异常。
            now_current = backend.sem_current_build(org_id)
            if now_current is not None and now_current["dict_rev"] == dict_rev:
                stats_skip = {"skipped": True, "current_build_id": now_current["id"],
                              "reason": "concurrent-ready"}
                logger.info(
                    "semantic build ceded to concurrent winner: org=%s rev=%s"
                    " current_build=%s", org_id, dict_rev, now_current["id"])
                return {"build_id": now_current["id"], "dict_rev": dict_rev,
                        "status": "skipped", "stats": stats_skip}
            raise RuntimeError(
                f"build switch ineffective (not building?): org={org_id!r}"
                f" build={build_id}"
            )
        logger.info("semantic build ready: org=%s build=%s rev=%s entities=%s",
                    org_id, build_id, dict_rev, stats["entities"])
        return {"build_id": build_id, "dict_rev": dict_rev, "status": "ready",
                "stats": stats}
    except BaseException as exc:
        fail_stats = {"error": str(exc), "dict_rev": dict_rev}
        if build_id is not None:
            try:
                # failed 事件经 audit= 与行同事务，且仅 building→failed 真生效
                # 时写入（sem_fail_build 返回生效性——P2-2/R2 防脏 failed 审计）
                backend.sem_fail_build(
                    org_id, build_id,
                    json.dumps(fail_stats, ensure_ascii=False, default=str),
                    audit=(
                        EVENT_SEMANTIC_BUILD,
                        json.dumps({"org_id": org_id, "build_id": build_id,
                                    "dict_rev": dict_rev, "status": "failed",
                                    "stats": fail_stats},
                                   ensure_ascii=False, default=str),
                    ),
                )
            except Exception:  # noqa: BLE001 —— 失败收尾失败不掩盖原始异常
                logger.exception("sem_fail_build failed: org=%s build=%s",
                                 org_id, build_id)
        if isinstance(exc, BuildInterrupted):
            raise
        logger.exception("semantic build failed: org=%s", org_id)
        raise


class BuildInterrupted(RuntimeError):
    """切换前存活检查失守（任务取消/租约丢失）——不落 failed 行（未建行）。"""


# ---- worker 任务入口（semantic_build 任务类型——payload {org}） ----


def run_build_task(
    backend, settings: Settings, task_id: str, *,
    should_continue: Callable[[], bool] | None = None,
) -> dict:
    """semantic_build 任务体（worker executor 调用——自管任务行状态）。"""
    task = backend.get_task(task_id)
    if task is None:
        raise RuntimeError(f"semantic_build task not found: {task_id!r}")
    try:
        payload = json.loads(task.get("payload") or "{}")
    except ValueError as exc:
        raise RuntimeError(
            f"semantic_build task payload not JSON: {task.get('payload')!r}"
        ) from exc
    org_id = payload.get("org")
    if not org_id:
        raise RuntimeError(
            f"semantic_build task payload missing org: {payload!r}"
        )
    backend.update_task(task_id, status="running")
    result = run_build(
        backend, org_id, settings=settings, should_continue=should_continue
    )
    backend.update_task(task_id, status="done")
    return result
