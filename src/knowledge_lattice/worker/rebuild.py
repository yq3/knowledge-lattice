"""文档域重建类任务执行体（m2-6 A1/A2——design §5.3 重嵌入流程 / TC-EMB-06）。

- **reembed 蓝绿执行体**（``run_reembed_task``——TC-EMB-06 四步，m2-3 已交付
  投递入口、本段补 worker 执行体；**N-1 裁定选 a/R2 P2-2：全库迁移**——
  payload.org 仅记录投递上下文，扫描/覆盖率门/清理均全库〔org_id=None〕，
  全库在用块新标签覆盖率 100% 后方可原子切全局标签；触发权限 sysadmin
  专属〔api 层收口〕）：
  ① 新标签向量**并行写入** chunk_vectors（``pending_reembed_batch`` 全库扫描
     认领 = 非 tombstone 块〔在用 + pending 版本——切换终态不漏在途覆盖上传
     块〕中无 (rid,:new) cv 行，逐批钉签；**迁移外呼经 ``embedder.with_model``
     专用实例**——检索谓词与摄取管线继续用原实例旧标签，功能零降级）；
  ② 覆盖率 100%（限 tombstone=0 且 version=active_version——RUNBOOK §1 闭合
     口径；**全库**）后**原子切 config 标签**（零 SQL——``switch_embed_label``
     进程内对象图：embedder.apply_model〔检索谓词/摄取钉签共同源〕+ ingest/
     quality apply_settings + WorkerServices.settings 替换；semantic 查询/
     build 面经 ``config.effective_settings`` 从 embedder 派生——P2-1/R2）；
  ③ **竞态在途回写防护**：``repin_chunk_labels``（全库）把全部块的状态标签
     对齐新标签——旧模型在途批次（慢 fake Embedder 形态）迟到回写的
     ``write_embeddings`` 防护谓词 ``c.embed_model = :batch_label`` 不再匹配，
     零行生效，库内不出现孤儿行；
  ④ **旧标签延后清理**（``delete_vectors_by_label``——全库非新标签 cv 行
     全删，**全库单标签一致**；sqlite WAL 廉价 / PG 满量死元组页内复用——
     RUNBOOK 注记）+ **quality 重跑联动**（``invalidate_quality_cache``〔全库〕
     使缓存键 (content_sha, embed_model) 的模型维失效——recompute 候选= 全量、
     旧 vector_crowding flags 随重算清除；**阈值随新模型重标定**=运维配置动作
     〔quality_crowding_threshold 绝对阈值——M1-5 校准路径〕，重算按当前
     配置值用新标签向量）+ **semantic_build 强制重跑投递**（逐组织——dict_rev
     含嵌入标签，§5.8「相同则跳过」失效必然重建）。

  切换载体择型（申报）：design §5.3 的 config 四件套=环境变量（部署侧切换、
  重启生效）——本执行体的切换是**进程内对象图替换**（零 SQL：不动任何数据
  行）。inline 模式（测试/最小部署）下 worker 与主进程共享 embedder/ingest/
  quality 对象，切换即刻对检索/摄取生效；**subprocess 模式**下子进程切换仅
  作用于子进程对象图，主进程标签切换=运维改 env 重启（RUNBOOK §1 流程第 4
  步）——重启窗口内主进程检索谓词（旧标签）向量已被清理，向量路暂空、BM25
  可用（申报为 RUNBOOK 注意事项，docs 归监督侧）。

- **reindex 执行体**（``run_reindex_task``——A2）：终态/存活/在途 pending
  三重前置检查（P3-5/R2——取消不重置、pending 拒绝）后幂等重置
  （``delete_by_doc`` 清块 + active_status 回 parsing）→ 复用 ingest.run_task
  幂等管线（parse→chunk→index_fts→embed→quality 全链）。与 reembed 蓝绿
  口径天然对齐：embed 阶段钉**当前服务标签**（迁移期=旧标签，由 reembed
  全库扫描谓词兜底补新；已切换=新标签）——无需特判。中断重认领不丢不重：
  重置幂等 + insert 先删后插 + 阶段续跑。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import replace

from knowledge_lattice.adapters.embedder import validate_dim
from knowledge_lattice.config import Settings
from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_BUILD

logger = logging.getLogger(__name__)

# 覆盖率收敛轮上限：每轮= 扫描写入至空 + 复算覆盖率；未收敛（并发摄取持续
# 超越迁移速度）→ 任务 failed 留人工（G-27——**一次失败不自动回队**；subprocess
# 形态 attempts 框架级重试仍在，但收敛判定不依赖它）——极端窗口申报。
_MAX_CONVERGE_ROUNDS = 3


def _parse_label(label: str) -> tuple[str, int]:
    """目标标签 ``model:dim`` 解析（dim 侧必须纯整数——MRL 截断 ``:trunc``
    后缀形态同 dims 解析路径，非法 fail-closed）。"""
    name, sep, dim_raw = label.rpartition(":")
    if not sep or not name or not dim_raw.isdigit():
        raise ValueError(
            f"embed_model 非法: {label!r}——须为 'model:dim' 形态（如"
            " qwen3-embedding-4b:2560）"
        )
    return name, int(dim_raw)


def switch_embed_label(services, new_settings: Settings) -> None:
    """蓝绿切换点（TC-EMB-06 ②——原子、零 SQL）：进程内对象图替换。

    - embedder.apply_model：检索向量路谓词源（retrieve 的 embedder 优先）与
      摄取钉签源（_embed_stage 的 embedder.model_label）**同时**切到新标签；
    - ingest/quality apply_settings：embed 维度校验与 quality 检测标签随切；
    - services.settings 替换（worker 容器——semantic_build 的 dict_rev 标签
      源）；管理面覆盖率面板 label 读 service.embedder.model_label（api 层
      与检索谓词同源，m2-6 对齐）。
    """
    embedder = getattr(services, "_embedder", None)
    label = new_settings.embed_model_label
    name, dim = _parse_label(label)
    if embedder is not None:
        embedder.apply_model(name, dim)
    ingest = getattr(services, "ingest", None)
    if ingest is not None:
        ingest.apply_settings(new_settings)
    quality = getattr(services, "quality", None)
    if quality is not None:
        quality.apply_settings(new_settings)
    services.settings = new_settings


def _alive_or_none(should_continue: Callable[[], bool] | None) -> Callable[[], bool]:
    if should_continue is None:
        return lambda: True
    return should_continue


def run_reembed_task(
    services, task_id: str, *,
    should_continue: Callable[[], bool] | None = None,
) -> dict:
    """reembed 任务体（worker executor 调用——自管任务行状态，沿
    run_build_task 先例；取消/丢租约在批次边界静默退出不落终态，任务行归
    取消方/新持有者——TC-TASK-03 口径）。"""
    backend = services.backend
    task = backend.get_task(task_id)
    if task is None:
        raise RuntimeError(f"reembed task not found: {task_id!r}")
    try:
        payload = json.loads(task.get("payload") or "{}")
    except ValueError as exc:
        backend.update_task(task_id, status="failed", error=f"payload not JSON")
        raise RuntimeError(f"reembed payload not JSON: {task.get('payload')!r}") from exc
    org_id = payload.get("org")
    new_label = payload.get("embed_model")
    if not org_id or not new_label:
        backend.update_task(
            task_id, status="failed",
            error=f"reembed payload missing org/embed_model: {payload!r}",
        )
        return {"task_id": task_id, "status": "failed"}
    try:
        new_name, new_dim = _parse_label(new_label)
    except ValueError as exc:
        backend.update_task(task_id, status="failed", error=str(exc))
        return {"task_id": task_id, "status": "failed"}

    alive = _alive_or_none(should_continue)
    backend.update_task(task_id, status="running")
    settings: Settings = services.settings
    batch_size = settings.embed_batch_size

    # 迁移外呼专用 embedder：请求模型指向新名（网关按 model 参数路由），
    # 存储/服务标签不动（原实例继续旧标签服务——零降级）。
    base_embedder = getattr(services, "_embedder", None)
    migr_embedder = (
        base_embedder.with_model(new_name, new_dim)
        if base_embedder is not None else None
    )

    def _fill_until_empty() -> None:
        """扫描写入至空批（批次边界存活检查——取消细粒度生效）。

        **全库口径（N-1 裁定选 a——R2 P2-2）**：扫描不带组织过滤
        （org_id=None），任一组织的缺块都在补齐范围内。"""
        if migr_embedder is None:
            raise RuntimeError(
                "reembed requires an embedder（WorkerServices._embedder 未装配）"
            )
        while True:
            if not alive():
                raise _LostLease(
                    f"reembed aborted at batch boundary (lease lost/cancelled):"
                    f" {task_id}"
                )
            batch = backend.pending_reembed_batch(
                None, new_label, limit=batch_size
            )
            if not batch:
                return
            vectors = migr_embedder.embed([row["content"] for row in batch])
            if len(vectors) != len(batch):
                from knowledge_lattice.adapters.embedder import (
                    EmbeddingResponseError,
                )

                raise EmbeddingResponseError(
                    f"embedding response count mismatch: got {len(vectors)}"
                    f" != requested {len(batch)}——拒绝写入（防半批静默丢失）"
                )
            validate_dim(vectors, expected=new_dim)
            backend.write_embeddings(
                new_label, [(row["rid"], v) for row, v in zip(batch, vectors)]
            )

    try:
        # ① 写满（多轮收敛——并发摄取的新块由扫描谓词兜住）
        # 覆盖率门 = **全库**（design §5.3 L794/TC-EMB-06 L224 冻结口径——
        # 任一组织未达 100% 不得切换；payload.org 仅记录投递上下文）
        converged = False
        for _ in range(_MAX_CONVERGE_ROUNDS):
            _fill_until_empty()
            rows = backend.embedding_coverage(None, new_label)
            done = sum(r["done"] for r in rows)
            total = sum(r["total"] for r in rows)
            if done == total:
                converged = True
                break
            logger.info(
                "reembed converge round: full-library %s/%s（并发摄取窗口——再扫一轮）",
                done, total,
            )
        if not converged:
            # R3 P3-4：未收敛 fail-closed 收口（任务 failed **留人工核查**——
            # G-27 口径：不自动回队重投；错误信息明示处置面。不上抛：直调/
            # runner 两路径语义一致；切换/清理/联动均未发生）
            backend.update_task(
                task_id, status="failed",
                error="reembed 全库覆盖率未收敛（并发摄取持续超越——任务"
                "失败留人工核查后重投；切换与清理未发生）",
            )
            logger.error(
                "reembed full-library coverage not converged: org=%s label=%s",
                org_id, new_label,
            )
            return {
                "task_id": task_id, "status": "failed", "org": org_id,
                "new_label": new_label, "converged": False,
            }
        if not alive():
            raise _LostLease(f"reembed aborted before switch: {task_id}")

        # ② 原子切 config 标签（零 SQL——同标签幂等跳过）
        old_label = settings.embed_model_label
        if old_label != new_label:
            switch_embed_label(
                services,
                replace(settings, embed_model=new_name, embed_dim=new_dim),
            )
            logger.info(
                "reembed switched embed label (full library): %s -> %s",
                old_label, new_label,
            )

        # ③ 在途回写防护：状态标签对齐（迟到旧批次回写谓词不再匹配）——全库
        repinned = backend.repin_chunk_labels(None, new_label)
        # 切换后补扫一轮：re-pin 后无新标签向量的在途块兜底补齐
        _fill_until_empty()

        # ④ 清理 + 联动（全库单标签一致 + 逐组织 quality/semantic_build）
        removed = backend.delete_vectors_by_label(None, new_label)
        quality = getattr(services, "quality", None)
        if quality is not None:
            backend.invalidate_quality_cache(None)
            for org in backend.list_org_ids():
                try:
                    quality.recompute(org)  # 新标签向量全量重算（清旧 flags）
                except Exception:  # noqa: BLE001 —— 沿 ingest quality 阶段 best-effort
                    logger.exception(
                        "quality recompute after reembed failed: org=%s（可重跑补）",
                        org,
                    )
        import uuid

        build_tasks: list[str] = []
        for org in backend.list_org_ids():
            build_task_id = f"tsk_{uuid.uuid4()}"
            backend.create_task(
                None, task_type="semantic_build", task_id=build_task_id,
                payload=json.dumps({"org": org}),
                audit=(EVENT_SEMANTIC_BUILD, json.dumps({
                    "org_id": org, "task_id": build_task_id,
                    "phase": "forced_by_reembed",
                    "embed_model": new_label, "actor": "system",
                }, ensure_ascii=False)),
            )
            build_tasks.append(build_task_id)
        backend.update_task(task_id, status="done")
        logger.info(
            "reembed done (full library): %s->%s repinned=%s vectors_removed=%s"
            " build_tasks=%s",
            old_label, new_label, repinned, removed, build_tasks,
        )
        return {
            "task_id": task_id, "status": "done", "org": org_id,
            "old_label": old_label, "new_label": new_label,
            "repinned": repinned, "vectors_removed": removed,
            "build_task_ids": build_tasks,
        }
    except _LostLease:
        # 取消/丢租约：任务行归外部动作方所有——静默退出（TC-TASK-03）
        logger.warning("reembed lost lease/cancelled: %s", task_id)
        return {"task_id": task_id, "status": "lost_lease"}


class _LostLease(Exception):
    """批次边界租约失守（reembed 执行体内取消探测的深层信号）。"""


def run_reindex_task(
    services, task_id: str, *,
    should_continue: Callable[[], bool] | None = None,
) -> dict:
    """reindex 任务体（A2）：幂等重置 + 复用 ingest 幂等管线（重切分+重嵌入
    全链含 quality）；任务终态由 ingest.run_task 管理（done/failed/lost_lease
    同款口径）。

    P3-5/R2 防御（重置先于存活/终态检查的不可搜窗口根除）：
    - 任务已被取消（failed+'cancelled:'——claim 后取消的吸收态）→ **不重置**
      直接返回（在用块保留、状态不动）；
    - 文档存在 pending 覆盖上传在途（pending_version 非 None 且非 failed）且
      目标=active 版本 → 任务 failed 带原因（API 投递面同语义 409——双防线）。
    """
    backend = services.backend
    ingest = services.ingest
    if ingest is None:
        raise RuntimeError("ingest service not wired in worker services")
    task = backend.get_task(task_id)
    if task is None:
        raise RuntimeError(f"reindex task not found: {task_id!r}")
    if task["status"] == "failed" and (task.get("error") or "").startswith(
        "cancelled:"
    ):
        # 取消吸收态：重置不发生（P3-5①——取消不得把文档推向不可搜）
        logger.warning("reindex task cancelled before reset: %s", task_id)
        return {"task_id": task_id, "status": "cancelled"}
    doc_id = task.get("doc_id")
    if doc_id is None:
        backend.update_task(
            task_id, status="failed",
            error="reindex task has no doc_id（文档级任务——投递面契约）",
        )
        return {"task_id": task_id, "status": "failed"}
    doc = backend.get_document(doc_id)
    if doc is None:
        backend.update_task(
            task_id, status="failed", error="cancelled: document deleted"
        )
        return {"task_id": task_id, "status": "cancelled"}
    version = task.get("target_version") or doc.get("active_version")
    if version is None:
        backend.update_task(
            task_id, status="failed",
            error=f"reindex target version unknown: doc={doc_id!r}",
        )
        return {"task_id": task_id, "status": "failed"}
    pending_v = doc.get("pending_version")
    if version == doc.get("active_version") and pending_v is not None:
        # P3-5②/N-2 裁定选 a（R3）：pending 版本存在（**含 failed**）一律拒绝
        # ——失败 pending 行未清除时 ingest._guard_alive 仍以 pending 为当前
        # 目标（core 语义不动），重置 active 块会把文档推向 parsing 不可搜。
        backend.update_task(
            task_id, status="failed",
            error=(
                f"document {doc_id!r} has pending version v{pending_v}"
                f" ({doc.get('pending_status')})——pending 期间禁止 reindex"
                "（含失败版本——先处置失败上传/清理 pending 后重投；N-2 裁定 a）"
            ),
        )
        return {"task_id": task_id, "status": "failed"}

    alive = _alive_or_none(should_continue)
    if not alive():
        # 重置前存活检查（claim 后即刻取消的窗口——不触碰文档）
        logger.warning("reindex lost lease before reset: %s", task_id)
        return {"task_id": task_id, "status": "lost_lease"}

    # 幂等重置：清块 + 状态回 parsing（_index_fts_done 判定不再跳过——重切分
    # 强制重跑；重认领重跑重复执行无害）。文档暂不可搜=重索引窗口（申报）。
    backend.delete_by_doc(doc_id, version)
    if doc.get("active_version") == version:
        backend.set_doc_active_status(doc_id, version, "parsing")
    ingest.run_task(task_id, should_continue=should_continue)
    final = backend.get_task(task_id)
    return {"task_id": task_id, "status": final["status"] if final else "unknown"}
