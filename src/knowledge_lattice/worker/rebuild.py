"""文档域重建类任务执行体（m2-6 A1/A2——design §5.3 重嵌入流程 / TC-EMB-06）。

- **reembed 蓝绿执行体**（``run_reembed_task``——TC-EMB-06 四步，m2-3 已交付
  投递入口、本段补 worker 执行体）：
  ① 新标签向量**并行写入** chunk_vectors（``pending_reembed_batch`` 扫描认领
     = org 内非 tombstone 块〔在用 + pending 版本——切换终态不漏在途覆盖上传
     块〕中无 (rid,:new) cv 行，逐批钉签；**迁移外呼经 ``embedder.with_model``
     专用实例**——检索谓词与摄取管线继续用原实例旧标签，功能零降级）；
  ② 覆盖率 100%（限 tombstone=0 且 version=active_version——RUNBOOK §1 闭合
     口径）后**原子切 config 标签**（零 SQL——``switch_embed_label`` 进程内
     对象图：embedder.apply_model〔检索谓词/摄取钉签共同源〕+ ingest/quality
     apply_settings + WorkerServices.settings 替换）；
  ③ **竞态在途回写防护**：``repin_chunk_labels`` 把 org 内全部块的状态标签
     对齐新标签——旧模型在途批次（慢 fake Embedder 形态）迟到回写的
     ``write_embeddings`` 防护谓词 ``c.embed_model = :batch_label`` 不再匹配，
     零行生效，库内不出现孤儿行；
  ④ **旧标签延后清理**（``delete_vectors_by_label``——org 内非新标签 cv 行
     全删，全库单标签一致；sqlite WAL 廉价 / PG 满量死元组页内复用——RUNBOOK
     注记）+ **quality 重跑联动**（``invalidate_quality_cache`` 使缓存键
     (content_sha, embed_model) 的模型维失效——recompute 候选= 全量、旧
     vector_crowding flags 随重算清除；**阈值随新模型重标定**=运维配置动作
     〔quality_crowding_threshold 绝对阈值——M1-5 校准路径〕，重算按当前
     配置值用新标签向量）+ **semantic_build 强制重跑投递**（dict_rev 含
     嵌入标签——§5.8「相同则跳过」失效必然重建）。

  切换载体择型（申报）：design §5.3 的 config 四件套=环境变量（部署侧切换、
  重启生效）——本执行体的切换是**进程内对象图替换**（零 SQL：不动任何数据
  行）。inline 模式（测试/最小部署）下 worker 与主进程共享 embedder/ingest/
  quality 对象，切换即刻对检索/摄取生效；**subprocess 模式**下子进程切换仅
  作用于子进程对象图，主进程标签切换=运维改 env 重启（RUNBOOK §1 流程第 4
  步）——重启窗口内主进程检索谓词（旧标签）向量已被清理，向量路暂空、BM25
  可用（申报为 RUNBOOK 注意事项，docs 归监督侧）。

- **reindex 执行体**（``run_reindex_task``——A2）：幂等重置
  （``delete_by_doc`` 清块 + active_status 回 parsing）→ 复用 ingest.run_task
  幂等管线（parse→chunk→index_fts→embed→quality 全链）。与 reembed 蓝绿
  口径天然对齐：embed 阶段钉**当前服务标签**（迁移期=旧标签，由 reembed
  扫描谓词兜底补新；已切换=新标签）——无需特判。中断重认领不丢不重：重置
  幂等 + insert 先删后插 + 阶段续跑。
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
# 超越迁移速度）→ raise 交任务重试（attempts 有界收敛）——极端窗口申报。
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
        """扫描写入至空批（批次边界存活检查——取消细粒度生效）。"""
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
                org_id, new_label, limit=batch_size
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
        converged = False
        for _ in range(_MAX_CONVERGE_ROUNDS):
            _fill_until_empty()
            rows = backend.embedding_coverage(org_id, new_label)
            done = sum(r["done"] for r in rows)
            total = sum(r["total"] for r in rows)
            if done == total:
                converged = True
                break
            logger.info(
                "reembed converge round: org=%s %s/%s（并发摄取窗口——再扫一轮）",
                org_id, done, total,
            )
        if not converged:
            raise RuntimeError(
                f"reembed 覆盖率未收敛（org={org_id!r}——并发摄取持续超越，"
                "任务重试收敛）"
            )
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
                "reembed switched embed label: org=%s %s -> %s",
                org_id, old_label, new_label,
            )

        # ③ 在途回写防护：状态标签对齐（迟到旧批次回写谓词不再匹配）
        repinned = backend.repin_chunk_labels(org_id, new_label)
        # 切换后补扫一轮：re-pin 后无新标签向量的在途块兜底补齐
        _fill_until_empty()

        # ④ 清理 + 联动
        removed = backend.delete_vectors_by_label(org_id, new_label)
        quality = getattr(services, "quality", None)
        if quality is not None:
            backend.invalidate_quality_cache(org_id)
            try:
                quality.recompute(org_id)  # 新标签向量全量重算（清旧 flags）
            except Exception:  # noqa: BLE001 —— 沿 ingest quality 阶段 best-effort
                logger.exception(
                    "quality recompute after reembed failed: org=%s（可重跑补）",
                    org_id,
                )
        import uuid

        build_task_id = f"tsk_{uuid.uuid4()}"
        backend.create_task(
            None, task_type="semantic_build", task_id=build_task_id,
            payload=json.dumps({"org": org_id}),
            audit=(EVENT_SEMANTIC_BUILD, json.dumps({
                "org_id": org_id, "task_id": build_task_id,
                "phase": "forced_by_reembed",
                "embed_model": new_label, "actor": "system",
            }, ensure_ascii=False)),
        )
        backend.update_task(task_id, status="done")
        logger.info(
            "reembed done: org=%s %s->%s repinned=%s vectors_removed=%s"
            " build_task=%s",
            org_id, old_label, new_label, repinned, removed, build_task_id,
        )
        return {
            "task_id": task_id, "status": "done", "org": org_id,
            "old_label": old_label, "new_label": new_label,
            "repinned": repinned, "vectors_removed": removed,
            "build_task_id": build_task_id,
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
    同款口径）。"""
    backend = services.backend
    ingest = services.ingest
    if ingest is None:
        raise RuntimeError("ingest service not wired in worker services")
    task = backend.get_task(task_id)
    if task is None:
        raise RuntimeError(f"reindex task not found: {task_id!r}")
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

    # 幂等重置：清块 + 状态回 parsing（_index_fts_done 判定不再跳过——重切分
    # 强制重跑；重认领重跑重复执行无害）。文档暂不可搜=重索引窗口（申报）。
    backend.delete_by_doc(doc_id, version)
    if doc.get("active_version") == version:
        backend.set_doc_active_status(doc_id, version, "parsing")
    ingest.run_task(task_id, should_continue=should_continue)
    final = backend.get_task(task_id)
    return {"task_id": task_id, "status": final["status"] if final else "unknown"}
