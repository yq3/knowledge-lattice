"""摄取管线编排（design §3 core/docs/ingest.py + §5.3 阶段编排的 M0a 子集）。

阶段：parse（docling→统一块结构）→ chunk（结构感知 256–512 / Excel 行块）→
index_fts（chunks+FTS 同一事务、状态→searchable_lexical、**首次上传即切换
active_version——D20**）→ embed（分批 64、写入前维度校验、指纹探针两档）→
全部完成 searchable_full。

任务状态机：pending→leased→running→done|failed（§5.3）；阶段幂等续跑（TC-ING-07）：
断点粒度=阶段——重跑按文档状态判定已完成阶段（在用版本≥1 即 index_fts 已提交），
从 embed 续跑、不重复写块。M0a 为进程内执行器（TC-ING-07 口径）；子进程化随 M2。

分层纪律：编排不碰 SQL——阶段写入全部经 StorageBackend（insert 事务含状态推进与
首次上传切换；文档行 create/get；任务状态机 update_task）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import ulid as _ulid

from knowledge_lattice.adapters.embedder import (
    EmbeddingGate,
    EmbeddingResponseError,
    Embedder,
    validate_dim,
)
from knowledge_lattice.adapters.parser_docling import ParsedDocument, parse_document
from knowledge_lattice.config import Settings
from knowledge_lattice.core.docs.chunking import ChunkDraft, chunk_blocks

logger = logging.getLogger(__name__)


class UploadValidationError(Exception):
    """上传参数校验失败（400 语义：库不存在 / 必选维度缺值 / 取值不存在）。"""


class UploadPermissionError(Exception):
    """上传取值越权（403 语义——值须在调用者授权内，P1-1）。"""


def new_ulid(prefix: str) -> str:
    return f"{prefix}_{str(_ulid.ULID()).lower()}"


class IngestService:
    """摄取编排（依赖经构造注入——backend/embedder/gate 均可测试替换）。"""

    def __init__(
        self,
        backend,
        embedder: Embedder,
        settings: Settings,
        gate: EmbeddingGate,
        objects_dir: Path,
    ) -> None:
        self._backend = backend
        self._embedder = embedder
        self._settings = settings
        self._gate = gate
        self._objects_dir = objects_dir

    # ============ 上传入口（写权限校验在 upload 即做——P0-2.1） ============

    def create_document(
        self,
        *,
        org_id: str,
        dataset_id: str,
        title: str,
        dims: dict[str, list[str]],
        owner_user_id: str,
        file_bytes: bytes,
        mime_type: str,
        filename: str,
    ) -> tuple[str, str]:
        """校验（库/维度/取值在授权内）→ 存对象 → 建文档行（parsing）+ 任务（pending）。

        返回 (doc_id, task_id)。
        """
        datasets = {d["id"] for d in self._backend.list_datasets(org_id)}
        if dataset_id not in datasets:
            raise UploadValidationError(f"dataset not found in org: {dataset_id!r}")

        # P3-12：维度值去重（document_dimensions 主键 (doc,dim,value)——重复值会导致
        # index_fts 事务 IntegrityError 且重试永久失败）
        dims = {key: list(dict.fromkeys(values)) for key, values in dims.items()}

        dims_meta = {d["key"]: d for d in self._backend.list_dimensions(org_id)}
        grants = self._backend.read_grants(owner_user_id, org_id)
        for key, values in dims.items():
            if key not in dims_meta:
                raise UploadValidationError(f"unknown dimension: {key!r}")
            valid_values = {v["value"] for v in dims_meta[key]["values"]}
            for value in values:
                if value not in valid_values:
                    raise UploadValidationError(
                        f"unknown value {value!r} for dimension {key!r}"
                    )
                if value not in grants.get(key, ()):  # 值须在调用者授权内（P1-1）
                    raise UploadPermissionError(
                        f"value {value!r} of dimension {key!r} not within uploader grants"
                    )
        for key, meta in dims_meta.items():
            if meta["required"] and not dims.get(key):
                raise UploadValidationError(f"required dimension missing values: {key!r}")

        doc_id = new_ulid("doc")
        obj_name = f"{str(_ulid.ULID()).lower()}{Path(filename or 'bin').suffix}"
        self._objects_dir.mkdir(parents=True, exist_ok=True)
        (self._objects_dir / obj_name).write_bytes(file_bytes)
        self._backend.create_document(
            doc_id=doc_id,
            org_id=org_id,
            dataset_id=dataset_id,
            title=title or (filename or doc_id),
            source_uri=f"user:{owner_user_id}",
            content_hash="sha256:" + hashlib.sha256(file_bytes).hexdigest(),
            mime_type=mime_type or "application/octet-stream",
            parser="docling",
            owner_user_id=owner_user_id,
            raw_object_key=obj_name,
            pending_dims_json=json.dumps(dims, ensure_ascii=False) if dims else None,
        )
        task_id = self._backend.create_task(doc_id, task_type="ingest")
        return doc_id, task_id

    # ============ 执行器（进程内——M0a/M1；子进程化随 M2） ============

    def run_task(self, task_id: str, *, stop_after: str | None = None) -> None:
        """执行摄取任务（阶段幂等：重跑从上一完成阶段续——TC-ING-07）。

        stop_after：测试/中断缝（'parse'|'chunk'|'index_fts' 后返回，模拟进程中断；
        任务留在 running 态、**不写 done**——由重跑续上，P3-1）。异常统一落
        failed+error 并写文档失败态（P2-1：按 id 重读文档后落 active_error/pending）。
        """
        task = self._backend.get_task(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        doc = self._backend.get_document(task["doc_id"])
        if doc is None:
            raise KeyError(f"document not found: {task['doc_id']}")

        self._backend.update_task(task_id, status="leased")
        self._backend.update_task(task_id, status="running")
        try:
            interrupted = self._run_stages(doc, stop_after=stop_after)
            if interrupted:
                return  # 模拟中断：任务留 running，不写 done（P3-1）
            self._backend.update_task(task_id, status="done")
        except Exception as exc:  # noqa: BLE001 —— 任务级失败统一落 failed+error
            logger.exception("ingest task failed: %s", task_id)
            self._backend.update_task(task_id, status="failed", error=str(exc))
            self._record_doc_error(doc, exc)
            raise

    def _record_doc_error(self, doc: dict, exc: Exception) -> None:
        """失败写文档侧：首次上传已切换 → active_error；否则 pending_status=failed（不 500）。

        P2-1：同次执行内 index_fts 的 D20 切换已改写 DB（pending 清空、active_version=1），
        调用方传入的 doc 快照是切换前的——按 id 重读后再判定落点，否则 UPDATE 零行、
        失败态整体丢失。
        """
        fresh = self._backend.get_document(doc["id"])
        if fresh is not None:
            doc = fresh
        version = doc.get("pending_version") or doc.get("active_version")
        if doc.get("active_version") and doc["active_version"] == version:
            self._backend.set_doc_active_error(doc["id"], version, str(exc))
        else:
            self._backend.set_doc_pending_status(doc["id"], version, "failed")

    def _effective_version(self, doc: dict) -> int:
        return doc.get("pending_version") or doc["active_version"]

    def _run_stages(self, doc: dict, *, stop_after: str | None) -> bool:
        """返回是否在 stop_after 处提前返回（中断缝——True 时调用方不写 done）。"""
        doc_id = doc["id"]
        # 阶段判定（幂等续跑）：在用版本已切（D20 首次上传在 searchable_lexical 即切）→
        # parse/chunk/index_fts 已提交，从 embed 续；searchable_full → 幂等 no-op
        switched = doc.get("active_version", 0) >= 1 and doc.get("active_status") in (
            "searchable_lexical",
            "searchable_full",
        )
        if not switched:
            parsed = self._parse_stage(doc)
            if stop_after == "parse":
                return True
            drafts = self._chunk_stage(doc, parsed)
            if stop_after == "chunk":
                return True
            self._index_fts_stage(doc, drafts)
            if stop_after == "index_fts":
                return True
            doc = self._backend.get_document(doc_id)  # 切换后字段已变（active_*）
        if doc.get("active_status") == "searchable_full":
            return False  # 幂等 no-op（重跑 done 任务）
        self._embed_stage(doc)
        return False

    # ---- 阶段实现（各自幂等/可重入） ----

    def _object_path(self, doc: dict) -> Path:
        return self._objects_dir / doc["raw_object_key"]

    def _parse_stage(self, doc: dict) -> ParsedDocument:
        self._backend.set_doc_pending_status(doc["id"], self._effective_version(doc), "parsing")
        return parse_document(self._object_path(doc))

    def _chunk_stage(self, doc: dict, parsed: ParsedDocument) -> list[ChunkDraft]:
        drafts = chunk_blocks(parsed.blocks, doc_title=doc["title"])
        self._backend.set_doc_pending_status(doc["id"], self._effective_version(doc), "chunked")
        return drafts

    def _index_fts_stage(self, doc: dict, drafts: list[ChunkDraft]) -> None:
        dims = json.loads(doc.get("pending_dims_json") or "{}")
        dims_json = json.dumps(dims, ensure_ascii=False) if dims else "{}"
        chunks = [
            {
                "id": new_ulid("chk"),
                "seq": d.seq,
                "content": d.content,
                "title_seg": d.title_seg,
                "content_seg": d.content_seg,
                "token_count": d.token_count,
                "heading_path": " > ".join(d.heading_path) if d.heading_path else None,
                "page_no": d.page_no,
                "sheet_name": d.sheet_name,
                "bbox_json": d.bbox_json,
                "dims_json": dims_json,
            }
            for d in drafts
        ]
        self._backend.insert(doc["id"], self._effective_version(doc), chunks)

    def _embed_stage(self, doc: dict) -> None:
        doc_id, version = doc["id"], doc["active_version"]
        self._gate.ensure_writable()  # 拒绝档：拒绝以同标签写入（可重试——TC-EMB-03）
        label = self._embedder.model_label
        pending = self._backend.mark_embedding_batch(doc_id, version, label)
        batch_size = self._settings.embed_batch_size
        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            vectors = self._embedder.embed([row["content"] for row in batch])
            if len(vectors) != len(batch):  # P3-8：返回条数不符——防 zip 静默丢块
                raise EmbeddingResponseError(
                    f"embedding response count mismatch: got {len(vectors)}"
                    f" != requested {len(batch)}——拒绝写入（防半批静默丢失）"
                )
            validate_dim(vectors, expected=self._settings.embed_dim)  # 不符 raise、不写库
            # P2-3：core 只传浮点向量——vec_f32 BLOB 序列化收口 store 方言侧
            self._backend.write_embeddings(
                label, [(row["rid"], v) for row, v in zip(batch, vectors)]
            )
        self._backend.set_doc_active_status(doc_id, version, "searchable_full")
