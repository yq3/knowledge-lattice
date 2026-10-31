"""semantic_build 构建编排（design §5.8 构建产物 / §8 M2-S1 第 3 项——m2s-2
骨架段 → m2s-4 面上段：AC 自动机指标 + 构建报告 + 评测回归门槛；core 纯编排、
SQL 全下沉 store Semantic 域）。

流程（§5.8 四步）：

1. **快照读取**：active 实体（含 curated_json——G-17）+ 全部别名 + active 关系
   （store.sem_active_snapshot；m2s-4 增携 source_system——缺源警告面）；
2. **dict_rev 计算**：`hash(active 实体 + 别名 + yaml_rev + embed_model 标签)`
   ——与当前 ready 版本相同 → 跳过（TC-BUILD-01）；**dict_rev 各分量摘要**
   （entities/aliases/relations/yaml_rev/embed_model——A4 运维可观测：哪面
   变了触发重建一眼可辨）；
3. **产物与报告**（m2s-4）：AC 自动机规模（keys/nodes/skipped_fuzzy_only/
   skipped_restricted）与构建耗时；L0 片段计数与 token 估算；歧义别名/孤立
   节点/断链关系（active 关系指向非 active 端点——G-15 中间态）；缺源警告
   （五源无 active 实体——A4）；**评测指标**（TC-SEV-02——每次构建自动跑
   黄金集，指标进报告）；
4. **评测门槛**（TC-BUILD-04/TC-SEV-02）：绝对门槛四指标 + 较上一版 ready
   回归 >2pp → **不切 ready**（行置 failed、error 注明 eval 语义——需人工
   修复词典或确认后重建；eval_runner 注入面供测试）；
5. **原子切换**：building 行 upsert → 单语句 building→ready（旧行不动——
   T-S12）；失败路径 building→failed + error 载 stats，旧 ready 继续为当前；
6. **审计**：`semantic.build` 事件全终态入 outbox（ready/skipped/failed/
   eval_blocked——TC-BUILD-03）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable

from knowledge_lattice.config import Settings
from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_BUILD

logger = logging.getLogger(__name__)

__all__ = [
    "run_build", "run_build_task", "compute_dict_rev", "dict_rev_components",
    "build_report", "BuildInterrupted", "EVAL_REGRESSION_MAX_DROP",
]

# TC-BUILD-04：评测指标较上一版下降 >2 个百分点不切 ready（neg_fp 反向：
# 上升 >2pp 拦截）
EVAL_REGRESSION_MAX_DROP = 0.02


def _rev_payload(snapshot: dict, *, embed_model_label: str,
                 yaml_rev: str | None) -> dict:
    """dict_rev 哈希输入（规范化序列化——排序 + 紧凑分隔，双方言同 rev）。

    parent_id 以 -1 规避 None 与 int 的排序比较；curated_json 入实体元组 +
    yaml_rev 入顶层输入——YAML 改 definition 必触发重建（G-17 双保险）。"""
    return {
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


def _sha(obj) -> str:
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def compute_dict_rev(
    snapshot: dict, *, embed_model_label: str, yaml_rev: str | None = None
) -> str:
    """dict_rev = hash(active 实体〔含 curated_json——G-17/m2s-3〕+ 别名 +
    yaml_rev + embed_model 标签) 前 12 hex。"""
    return _sha(_rev_payload(snapshot, embed_model_label=embed_model_label,
                             yaml_rev=yaml_rev))


def dict_rev_components(
    snapshot: dict, *, embed_model_label: str, yaml_rev: str | None = None
) -> dict:
    """dict_rev 各分量摘要（A4 构建报告——entities/aliases/relations 分量
    sha + yaml_rev + embed_model 原值：变更面定位）。"""
    payload = _rev_payload(snapshot, embed_model_label=embed_model_label,
                           yaml_rev=yaml_rev)
    return {
        "entities": _sha(payload["entities"]),
        "aliases": _sha(payload["aliases"]),
        "relations": _sha(payload["relations"]),
        "yaml_rev": yaml_rev or "",
        "embed_model": embed_model_label,
    }


def _yaml_rev_of(snapshot: dict) -> str | None:
    """yaml_rev = active 实体 curated_rev 的字典序最大值（最近一次合并的
    corpus rev——全量合并语义下即当前 YAML 仓 rev；无 curated 实体为 None）。"""
    revs = [e.get("curated_rev") for e in snapshot["entities"] if e.get("curated_rev")]
    return max(revs) if revs else None


def _snapshot_json(snapshot: dict) -> str:
    """G-21 方案 A/m2s-5：构建快照序列化（实体〔含 curated_json〕+ 别名 +
    关系〔消歧共现/L0 佐证必需面〕的最小 JSON——迁移 0008 附表载体；与
    ready 切换同一事务写入）。"""
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True)


def _maybe_enqueue_retag(
    backend, org_id: str, dict_rev: str, stats: dict, prev_build: dict | None,
) -> bool:
    """TC-BUILD-05 消费面（m2s-5）：构建涉及**别名增删**才投递 semantic_retag
    ——新/旧构建的 dict_rev_components.aliases 分量摘要对比（变化 ⟺ 别名集
    增删/改动；仅 definition 变化不动别名面 → 不投，避免无谓重标风暴）。
    prev 缺省（首建/存量行无分量）→ 宁投勿漏（存量无行块由 retag 补标；
    无块时零候选幂等收尾）。stats.retag_enqueued 已在返回前落值。"""
    from knowledge_lattice.core.semantic.tagging import alias_set_changed, enqueue_retag

    prev_stats = None
    if prev_build is not None:
        prev_json = prev_build.get("stats_json") or "{}"
        if isinstance(prev_json, str):
            try:
                prev_json = json.loads(prev_json)
            except (TypeError, ValueError):
                prev_json = {}
        prev_stats = prev_json if isinstance(prev_json, dict) else None
    if not alias_set_changed(prev_stats, stats):
        logger.info(
            "semantic build alias set unchanged: org=%s rev=%s——不投 retag"
            "（仅非别名面变化，TC-BUILD-05）", org_id, dict_rev)
        return False
    return enqueue_retag(backend, org_id, dict_rev)


def _build_stats(snapshot: dict, *, annotator=None) -> dict:
    """构建报告统计（§5.8 产物之「构建报告」——冲突面随 sync run、此处为图
    统计 + 结构异常 + m2s-4 产物指标）。annotator 复用调用方已建实例（评测
    与自动机指标同一实例——不重复构建）。"""
    from knowledge_lattice.core.semantic.annotator import render_l0
    from knowledge_lattice.core.semantic.constants import SYNC_ADAPTERS

    entities_by_type: dict[str, int] = {}
    for e in snapshot["entities"]:
        entities_by_type[e["type"]] = entities_by_type.get(e["type"], 0) + 1
    relations_by_type: dict[str, int] = {}
    linked: set[int] = set()
    active_ids = {e["id"] for e in snapshot["entities"]}
    broken: list[dict] = []
    for r in snapshot["relations"]:
        relations_by_type[r["rel_type"]] = relations_by_type.get(r["rel_type"], 0) + 1
        linked.add(r["src_id"])
        linked.add(r["dst_id"])
        if r["src_id"] not in active_ids or r["dst_id"] not in active_ids:
            broken.append({"src_id": r["src_id"], "rel_type": r["rel_type"],
                           "dst_id": r["dst_id"]})
    # P1-1/R3：歧义别名清单按**识别可用面**——restricted 实体别名不入机
    # （T-S9 表现为不存在），其歧义面不存在、列入报告即误导+泄露 alias 面；
    # G-21 r6/m2s-5 随手：fuzzy_only 同滤（不入自动机——与 build_automaton/
    # evalrun 的识别可用面三处同口径）
    sensitivity = {e["id"]: e.get("sensitivity") for e in snapshot["entities"]}
    by_norm: dict[str, set[int]] = {}
    for a in snapshot["aliases"]:
        if sensitivity.get(a["entity_id"]) == "restricted":
            continue
        if a["match_mode"] not in ("exact", "context"):
            continue
        by_norm.setdefault(a["alias_norm"], set()).add(a["entity_id"])
    ambiguous = [
        {"alias_norm": norm, "entity_ids": sorted(ids)}
        for norm, ids in sorted(by_norm.items()) if len(ids) > 1
    ]
    # 缺源警告（A4）：五源无 active 实体（未同步/全量消失——G-19 兜底调度
    # 的可观测面；source_system 自 m2s-4 起随快照携带）
    sources_present = {e.get("source_system") for e in snapshot["entities"]
                       if e.get("source_system")}
    missing_sources = [
        {"source": name,
         "reason": "no active entities from this source（未同步或全量消失）"}
        for name in SYNC_ADAPTERS if name not in sources_present
    ]
    if annotator is None:
        from knowledge_lattice.core.semantic.annotator import Annotator

        annotator = Annotator(snapshot)
    l0 = render_l0(snapshot)
    return {
        "entities": len(snapshot["entities"]),
        "entities_by_type": entities_by_type,
        "aliases": len(snapshot["aliases"]),
        "relations": len(snapshot["relations"]),
        "relations_by_type": relations_by_type,
        "ambiguous_aliases": ambiguous,
        "orphan_nodes": sum(1 for e in snapshot["entities"]
                            if e["id"] not in linked),
        "broken_relations": {"count": len(broken), "sample": broken[:10]},
        "missing_sources": missing_sources,
        "ac_automaton": annotator.automaton_meta,
        "l0": {"fragments": len(l0["fragments"]),
               "token_estimate": l0["token_estimate"]},
    }


def _audit_build(backend, org_id: str, status: str, stats: dict) -> None:
    """semantic.build 事件（ready/skipped/failed 全终态——TC-BUILD-03）。"""
    backend.append_outbox(
        EVENT_SEMANTIC_BUILD,
        json.dumps(
            {"org_id": org_id, "status": status, **stats}, ensure_ascii=False,
            default=str,
        ),
    )


# ---- 评测门槛（TC-BUILD-04 / TC-SEV-02） ----


def _eval_directional_drop(metric: str, prev: float, new: float) -> bool:
    """指标回归判定（>2pp）：precision/recall/ambiguity 降、neg_fp 升。"""
    if metric == "neg_fp":
        return new > prev + EVAL_REGRESSION_MAX_DROP
    return new < prev - EVAL_REGRESSION_MAX_DROP


def _eval_gate(metrics: dict, prev_metrics: dict | None) -> dict:
    """门槛评估：绝对门槛 + 相对回归（None 指标跳过——如无歧义样本时
    ambiguity=None 不参与门槛）。"""
    from knowledge_lattice.core.semantic.evalrun import EVAL_THRESHOLDS

    below: list[str] = []
    for metric, threshold in EVAL_THRESHOLDS.items():
        value = metrics.get(metric)
        if value is None:
            continue
        if metric == "neg_fp":
            if value > threshold:
                below.append(metric)
        elif value < threshold:
            below.append(metric)
    info: dict = {"metrics": metrics, "thresholds": dict(EVAL_THRESHOLDS)}
    if below:
        info["below_threshold"] = True
        info["below"] = below
        return info
    if prev_metrics:
        regressions = [
            m for m in EVAL_THRESHOLDS
            if prev_metrics.get(m) is not None and metrics.get(m) is not None
            and _eval_directional_drop(m, prev_metrics[m], metrics[m])
        ]
        if regressions:
            info["regression"] = True
            info["regressed"] = regressions
            info["previous"] = {
                m: prev_metrics[m] for m in regressions
                if prev_metrics.get(m) is not None}
    return info


def _prev_eval_metrics(current: dict | None) -> dict | None:
    if not current:
        return None
    stats_json = current.get("stats_json") or "{}"
    if isinstance(stats_json, str):
        try:
            stats_json = json.loads(stats_json)
        except (TypeError, ValueError):
            return None
    ev = (stats_json or {}).get("eval") or {}
    return ev.get("metrics")


def run_build(
    backend,
    org_id: str,
    *,
    settings: Settings,
    should_continue: Callable[[], bool] | None = None,
    eval_runner: Callable[[object, dict], dict] | None = None,
) -> dict:
    """一次构建 run（§5.8——返回 {build_id?, dict_rev, status, stats}）。

    - dict_rev 与当前 ready 相同 → skipped（不产新行——TC-BUILD-01）；
    - **G-17/m2s-3**：curated_json 入快照、yaml_rev（=max curated_rev）入
      dict_rev 输入与 build 行——YAML 改 definition 必触发重建；
    - **G-18/O-1/m2s-3**：sem_insert_build 条件 upsert——同 rev 行已 ready
      时不重断 building（无 flap）；此时若 current 已同 rev → skipped 让位
      （并发赢家），否则 **重激活**（顶置 activated_at 成为 current——rev
      回退场景 current 不失真，sem_reactivate_build + ready 事件同事务）；
    - **评测门槛（m2s-4）**：eval_runner（缺省 = 黄金集 runner——文件缺失
      None → skipped）在新快照 Annotator 上跑指标；绝对门槛/较上一版回归
      >2pp → **行置 failed（不切 ready）**、stats.eval 留因——返回
      status="failed"（不上抛：非故障是治理拦截，人工修复词典后重建）；
    - ready/failed 事件与终态行**同一事务**（store switch/fail 的 audit=——
      P3-5/R2；G-16 构建侧收口）；
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
        # prev 保留引用（retag 投递判定的 diff 基线——TC-BUILD-05）
        prev_build = current

        if should_continue is not None and not should_continue():
            raise BuildInterrupted("build interrupted before switch (lease lost)")
        from knowledge_lattice.core.semantic.annotator import Annotator

        annotator = Annotator(snapshot)   # 评测与自动机指标同一实例
        stats = _build_stats(snapshot, annotator=annotator)
        stats["dict_rev_components"] = dict_rev_components(
            snapshot, embed_model_label=settings.embed_model_label,
            yaml_rev=yaml_rev)
        stats_json = json.dumps(stats, ensure_ascii=False, default=str)
        build_id, was_ready = backend.sem_insert_build(
            org_id, dict_rev, stats_json, yaml_rev=yaml_rev)

        # ---- 评测门槛（m2s-4——TC-BUILD-04/TC-SEV-02）----
        runner = eval_runner
        if runner is None:
            from knowledge_lattice.core.semantic.evalrun import (
                golden_eval_runner,
            )

            runner = golden_eval_runner(settings)
        if runner is None:
            stats["eval"] = {"skipped": "golden set not configured/found"}
        else:
            metrics = runner(annotator, snapshot)
            if not isinstance(metrics, dict) or "skipped" in metrics:
                stats["eval"] = (metrics if isinstance(metrics, dict)
                                 else {"skipped": "eval runner returned none"})
            else:
                stats["eval"] = _eval_gate(metrics, _prev_eval_metrics(current))
        if stats["eval"].get("below_threshold") or stats["eval"].get("regression"):
            reason = ("eval below threshold: " + ",".join(stats["eval"].get("below", []))
                      if stats["eval"].get("below_threshold")
                      else "eval regression >2pp: " + ",".join(
                          stats["eval"].get("regressed", [])))
            stats_json = json.dumps(stats, ensure_ascii=False, default=str)
            backend.sem_fail_build(
                org_id, build_id, stats_json,
                audit=(
                    EVENT_SEMANTIC_BUILD,
                    json.dumps({"org_id": org_id, "build_id": build_id,
                                "dict_rev": dict_rev, "status": "failed",
                                "reason": "eval_blocked", "detail": reason,
                                "stats": stats},
                               ensure_ascii=False, default=str),
                ),
            )
            logger.warning(
                "semantic build blocked by eval gate: org=%s rev=%s（%s——"
                "不切 ready，需人工确认后重建）", org_id, dict_rev, reason)
            return {"build_id": build_id, "dict_rev": dict_rev,
                    "status": "failed", "stats": stats}

        # eval 面就位后重序列化（ready/reactivate 行携带完整报告——回归门禁
        # 的 prev 指标取自上一 ready 行 stats.eval.metrics）
        stats_json = json.dumps(stats, ensure_ascii=False, default=str)

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
            # P3-5/R2：消费 sem_reactivate_build 返回值——False（竞态下行已非
            # ready）不得虚报 ready：current 同 rev（他者已接手）→ skipped；
            # 否则真异常（不重试不写脏事件）
            # snapshot_json（G-21 方案 A/m2s-5）：快照附表随重激活同事务 upsert
            if not backend.sem_reactivate_build(
                org_id, build_id, stats_json,
                audit=(
                    EVENT_SEMANTIC_BUILD,
                    json.dumps({"org_id": org_id, "build_id": build_id,
                                "dict_rev": dict_rev, "status": "ready",
                                "stats": stats, "reactivated": True},
                               ensure_ascii=False, default=str),
                ),
                snapshot_json=_snapshot_json(snapshot),
            ):
                now_current = backend.sem_current_build(org_id)
                if now_current is not None and now_current["dict_rev"] == dict_rev:
                    stats_skip = {"skipped": True,
                                  "current_build_id": now_current["id"],
                                  "reason": "reactivate-race-lost"}
                    logger.info(
                        "semantic build reactivate ceded: org=%s rev=%s"
                        " current_build=%s", org_id, dict_rev, now_current["id"])
                    return {"build_id": now_current["id"], "dict_rev": dict_rev,
                            "status": "skipped", "stats": stats_skip}
                raise RuntimeError(
                    f"build reactivate ineffective (not ready?): org={org_id!r}"
                    f" build={build_id}"
                )
            logger.info("semantic build reactivated (rev rollback): org=%s"
                        " build=%s rev=%s", org_id, build_id, dict_rev)
            stats["retag_enqueued"] = _maybe_enqueue_retag(
                backend, org_id, dict_rev, stats, prev_build)
            return {"build_id": build_id, "dict_rev": dict_rev, "status": "ready",
                    "stats": stats}
        ready_audit = (
            EVENT_SEMANTIC_BUILD,
            json.dumps({"org_id": org_id, "build_id": build_id, "dict_rev": dict_rev,
                        "status": "ready", "stats": stats},
                       ensure_ascii=False, default=str),
        )
        # snapshot_json（G-21 方案 A/m2s-5）：快照附表与 ready 切换同一事务
        # ——ready 可见时快照必已在位（冷缓存/重启服务 build 产物的数据基础）
        if not backend.sem_switch_build_ready(
            org_id, build_id, stats_json,
            audit=ready_audit, snapshot_json=_snapshot_json(snapshot),
        ):
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
        stats["retag_enqueued"] = _maybe_enqueue_retag(
            backend, org_id, dict_rev, stats, prev_build)
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


# ---- 构建报告（A4——REST GET /semantic/builds/{id}/report 数据源） ----


def build_report(backend, org_id: str, build_id: int) -> dict | None:
    """构建报告聚合：build 行 stats + 近期 sync run 冲突面（运维可观测——
    §5.8「构建报告（冲突、歧义别名、孤立节点、断链关系、评测指标）」）。"""
    row = backend.sem_get_build(org_id, build_id)
    if row is None:
        return None
    stats_json = row.get("stats_json") or "{}"
    if isinstance(stats_json, str):
        try:
            stats_json = json.loads(stats_json)
        except (TypeError, ValueError):
            stats_json = {}
    stats = stats_json if isinstance(stats_json, dict) else {}
    conflicts: dict[str, list] = {}
    for run in backend.sem_list_sync_runs(org_id, limit=50):
        try:
            run_stats = json.loads(run.get("stats_json") or "{}")
        except (TypeError, ValueError):
            continue
        entries = list(run_stats.get("conflicts") or [])
        curated = run_stats.get("curated") or {}
        entries.extend(curated.get("conflicts") or [])
        if entries:
            conflicts.setdefault(run.get("adapter") or "?", []).extend(
                entries[:20])
    return {
        "build_id": row["id"],
        "org_id": row.get("org_id", org_id),
        "dict_rev": row["dict_rev"],
        "yaml_rev": row.get("yaml_rev"),
        "status": row["status"],
        "created_at": row.get("created_at"),
        "activated_at": row.get("activated_at"),
        "counts": {
            "entities": stats.get("entities"),
            "entities_by_type": stats.get("entities_by_type"),
            "aliases": stats.get("aliases"),
            "relations": stats.get("relations"),
            "relations_by_type": stats.get("relations_by_type"),
        },
        "ac_automaton": stats.get("ac_automaton"),
        "dict_rev_components": stats.get("dict_rev_components"),
        "ambiguous_aliases": stats.get("ambiguous_aliases"),
        "orphan_nodes": stats.get("orphan_nodes"),
        "broken_relations": stats.get("broken_relations"),
        "missing_sources": stats.get("missing_sources"),
        "conflicts": conflicts,
        "eval": stats.get("eval"),
        "l0": stats.get("l0"),
    }


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
