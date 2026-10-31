"""打标/重标编排（design §5.3「M2-S3 起同事务追加语义打标」+ §5.8 第 4 步
重标判断——m2s-5；core 纯编排、SQL 下沉 store）。

- **ingest 打标**（TC-TAG-01）：`make_ingest_tagger` 工厂产出 (doc, chunks) →
  sem_tags 的计算面——用**当前 ready 构建的 AC 自动机**（G-21 方案 A 后=
  build 快照产物）做第 1 层识别（annotate 全确定性流——exact/alias/context
  条件保留 + 四步消歧；不跑模糊兜底），按 (chunk, entity) 聚合 hits。经
  依赖注入挂进 IngestService（core/docs 不得 import core/semantic——分层
  守卫 test_sem_00_layering；装配点在 app.py / worker runner）；
- **打标失败不阻断**：tagger 可抛错，ingest 侧捕获记 warning +
  `semantic.tag_failed` 审计——文档先可用，块以「无行 = dict_rev 落后面」
  进入 retag 候选集（附录 A-14 口径——无标记字段，落后比对即候选集）；
- **semantic_retag 任务**（TC-TAG-02）：payload {org, dict_rev}——对 dict_rev
  落后（含无行）的活跃块分批重标（≤1000 行/批——NFR-11 写锁治理），块级
  标签整替（DELETE+INSERT 同事务）幂等收敛；任务优先级最低（claim ORDER BY
  尾部——worker 侧）；
- **投递判定**（TC-BUILD-05 消费面）：构建成功且别名集 diff（dict_rev_
  components.aliases 分量摘要变化 ⟺ 别名增删/改动）才投递——仅改
  definition 不投（避免无谓重标风暴）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from knowledge_lattice.config import Settings

from .annotator import Annotator, get_annotator

logger = logging.getLogger(__name__)

__all__ = [
    "make_ingest_tagger", "compute_sem_tags", "run_retag_task",
    "enqueue_retag", "alias_set_changed", "TAG_EVENT_FAILED",
]

# 打标失败审计事件（ingest 侧捕获时落——文档先可用，标后补）
TAG_EVENT_FAILED = "semantic.tag_failed"


def compute_sem_tags(
    annotator: Annotator, dict_rev: str, chunks: list[dict],
) -> dict:
    """chunks → sem_tags（纯计算面——store insert 事务内消费）。

    每 chunk 跑 annotate 第 1 层识别，(chunk, entity) 聚合 hits；
    **ambiguous=true 的 mention 不落标**（用户裁定①/m2s-5 R2：消歧未定案
    不贴——fail-closed，防未定案证据进入未来实体召回；定案命中〔含
    default⑤ 显式缺省主读档〕照常落）；restricted 实体防御性过滤
    （Annotator 已不入机——双层保险，T-S9）；超长块跳过（chunking 上限
    512 << 4000，防御性兜底不阻断）。"""
    rows: list[tuple[int, int, int]] = []
    for ch in chunks:
        content = ch.get("content") or ""
        if not content or len(content) > 4000:
            continue
        mentions = annotator.annotate(content)["mentions"]
        agg: dict[int, int] = {}
        for m in mentions:
            if m.get("ambiguous"):
                continue    # 裁定①：未消解定案不贴标（fail-closed）
            eid = m["entity_id"]
            ent = annotator.entities.get(eid)
            if ent is None or ent.get("sensitivity") == "restricted":
                continue    # T-S9：restricted 不落标（表现为不存在）
            agg[eid] = agg.get(eid, 0) + 1
        for eid, hits in sorted(agg.items()):
            rows.append((ch["seq"], eid, hits))
    return {"dict_rev": dict_rev, "rows": rows}


def make_ingest_tagger(backend, settings: Settings) -> Callable:
    """ingest 打标签工厂：返回 (doc, chunks) → sem_tags | None。

    无构建（org 无 ready build）→ None（不打标——「先构建再识别」操作序为
    部署形态，info 级不告警）；异常上抛交 ingest 侧统一捕获（失败不阻断）。"""

    def tagger(doc: dict, chunks: list[dict]) -> dict | None:
        ann, rev = get_annotator(backend, doc["org_id"], settings)
        if ann is None:
            logger.info(
                "semantic tagging skipped (no ready build): org=%s doc=%s"
                "——构建后由 retag/对账补做",
                doc["org_id"], doc["id"],
            )
            return None
        return compute_sem_tags(ann, rev, chunks)

    return tagger


# ---- retag 投递与执行（TC-BUILD-05 消费面 / TC-TAG-02） ----


def enqueue_retag(backend, org_id: str, dict_rev: str) -> bool:
    """投递 semantic_retag 任务（payload {org, dict_rev}；pending 去重）。"""
    payload = json.dumps({"org": org_id, "dict_rev": dict_rev})
    if backend.pending_task_exists("semantic_retag", payload):
        return False
    backend.create_task(None, task_type="semantic_retag", payload=payload)
    logger.info("semantic_retag enqueued: org=%s dict_rev=%s", org_id, dict_rev)
    return True


def alias_set_changed(prev_stats: dict | None, new_stats: dict) -> bool:
    """别名集 diff 判定（TC-BUILD-05）：dict_rev_components.aliases 分量摘要
    变化 ⟺ 别名增删/改动（weight/match_mode 变化同样影响识别面——保守投递）。
    prev 无 stats（首建/存量行）→ 视为变化（首建后全量块本就无标，投递幂等）；
    分量摘要缺省（早期构建行）→ 视为变化（fail-safe 宁投勿漏）。"""
    if not prev_stats:
        return True
    prev_alias = (prev_stats.get("dict_rev_components") or {}).get("aliases")
    new_alias = (new_stats.get("dict_rev_components") or {}).get("aliases")
    if not prev_alias or not new_alias:
        return True
    return prev_alias != new_alias


def run_retag_task(
    backend, settings: Settings, task_id: str, *,
    should_continue: Callable[[], bool] | None = None,
) -> dict:
    """semantic_retag 任务体（worker executor 调用——自管任务行状态）。

    payload {org, dict_rev}：目标 rev 以**执行时 current ready rev** 为准
    （payload 记投递时 rev，仅作日志对照——滞后投递自动追新）；无 current
    build → done no-op。分批 ≤ semantic_batch_rows（NFR-11），批间存活检查；
    块级标签整替（同事务 DELETE+INSERT）——幂等收敛，重跑零候选即收尾。"""
    task = backend.get_task(task_id)
    if task is None:
        raise RuntimeError(f"semantic_retag task not found: {task_id!r}")
    try:
        payload = json.loads(task.get("payload") or "{}")
    except ValueError as exc:
        raise RuntimeError(
            f"semantic_retag task payload not JSON: {task.get('payload')!r}"
        ) from exc
    org_id = payload.get("org")
    if not org_id:
        raise RuntimeError(
            f"semantic_retag task payload missing org: {payload!r}")

    backend.update_task(task_id, status="running")
    current = backend.sem_current_build(org_id)
    if current is None:
        backend.update_task(task_id, status="done")
        return {"org": org_id, "chunks_retagged": 0, "reason": "no ready build"}
    target_rev = current["dict_rev"]
    if payload.get("dict_rev") not in (None, target_rev):
        logger.info(
            "semantic_retag target moved: org=%s payload_rev=%s → current=%s"
            "（以执行时 current 为准）",
            org_id, payload.get("dict_rev"), target_rev)

    ann, rev = get_annotator(backend, org_id, settings)
    if ann is None or rev != target_rev:
        # P3-2/R2：缓存锚与目标不一致（并发切 build）时按快照附表重建；
        # 0008 前存量行无快照 → 回退 live + 告警（防 json.loads(None) TypeError）
        snap_json = backend.sem_load_build_snapshot(org_id, current["id"])
        if snap_json is not None:
            ann = Annotator(json.loads(snap_json))
        else:
            logger.warning(
                "retag target build has no snapshot: org=%s build_id=%s"
                "——fallback to live snapshot（0008 前存量行兼容路径）",
                org_id, current["id"])
            ann = Annotator(backend.sem_active_snapshot(org_id))
    batch = max(1, int(getattr(settings, "semantic_batch_rows", 1000)))
    retagged = 0
    cursor = 0
    while True:
        if should_continue is not None and not should_continue():
            logger.warning(
                "semantic_retag aborted at batch boundary (lease lost/"
                "cancelled): task=%s org=%s", task_id, org_id)
            return {"org": org_id, "chunks_retagged": retagged,
                    "aborted": True}
        candidates = backend.sem_retag_candidates(
            org_id, target_rev, limit=batch, after_rid=cursor)
        if not candidates:
            break
        # P1/R2：**整替**以本批全部候选为清理面（三元组收窄）——零命中候选
        # 块（别名删除/restricted 化/裁定① 歧义 skip）的旧标随批清除，lagging
        # 可收敛；rows 为空也进事务清理（不早退）
        clear = [{"chunk_rid": c["rid"], "doc_id": c["doc_id"],
                  "version": c["version"]} for c in candidates]
        rows: list[dict] = []
        for c in candidates:
            tags = compute_sem_tags(ann, target_rev, [{"seq": 0, "content":
                                                        c["content"]}])
            for _seq, entity_id, hits in tags["rows"]:
                rows.append({"chunk_rid": c["rid"], "doc_id": c["doc_id"],
                             "version": c["version"], "entity_id": entity_id,
                             "hits": hits, "dict_rev": target_rev})
        backend.sem_replace_chunk_tags(org_id, rows, clear=clear)
        retagged += len(candidates)
        # 游标推进（无命中块无行可写、不消候选——防原地死循环；重跑从头幂等）
        cursor = candidates[-1]["rid"]
    backend.update_task(task_id, status="done")
    logger.info("semantic_retag done: org=%s rev=%s chunks=%s",
                org_id, target_rev, retagged)
    return {"org": org_id, "dict_rev": target_rev, "chunks_retagged": retagged}
