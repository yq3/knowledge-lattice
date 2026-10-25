"""摄取管线编排（design §3 core/docs/ingest.py + §5.3 阶段编排）。

阶段：parse（docling→统一块结构）→ chunk（结构感知 256–512 / Excel 行块）→
index_fts（chunks+FTS 同一事务、状态→searchable_lexical、**首次上传即切换
active_version——D20**）→ embed（分批 64、写入前维度校验、指纹探针两档）→
全部完成 searchable_full；**覆盖上传在 searchable_full 时点单事务切换**
（switch_active_version——D20/TC-VER-04）。

版本在用制（M1-2，D21①/D22②）：
- 五字段状态机（active_version/active_status/active_error + pending_version/
  pending_status/pending_error）+ pending_dims_json（pending 期间不生效）；
- 失败版本号不复用：pending_version = max(历史版本)+1（TC-VER-03）；
- pending 失败立即物理删块（T8）；已删/被顶替版本在阶段边界被 guard 拦下
  （TC-VER-07）；
- 同文档并发覆盖上传 409（同一时刻只有一个 pending——T7）。

任务状态机：pending→leased→running→done|failed（§5.3）；阶段幂等续跑（TC-ING-07）：
断点粒度=阶段——重跑按文档状态判定已完成阶段，从上一完成阶段续。M0a 为进程内
执行器（TC-ING-07 口径）；子进程化随 M2。

分层纪律：编排不碰 SQL——阶段写入全部经 StorageBackend（insert 事务含状态推进与
首次上传切换；switch_active_version 切换事务；文档行 create/get；任务状态机
update_task）。
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
from knowledge_lattice.store.backend import VersionConflictError

__all__ = [
    "VersionConflictError",
    "UploadValidationError",
    "UploadPermissionError",
    "UploadConflictError",
    "UploadNotFoundError",
    "IngestService",
    "new_ulid",
]

logger = logging.getLogger(__name__)


class UploadValidationError(Exception):
    """上传参数校验失败（400 语义：库不存在 / 必选维度缺值 / 取值不存在 / dot-key）。"""


class UploadPermissionError(Exception):
    """上传/改维度越权（403 语义——值须在调用者授权内 P1-1 / 操作权限缺失）。"""


class UploadConflictError(Exception):
    """上传/改维度冲突（409 语义——pending 期间只有一个处理中版本，P0-2.3/T7）。"""


class UploadNotFoundError(Exception):
    """覆盖/删除/改维度的目标文档不存在或跨组织（404 语义）。"""


def new_ulid(prefix: str) -> str:
    return f"{prefix}_{str(_ulid.ULID()).lower()}"


def _validate_dim_keys(dims: dict[str, list[str]]) -> None:
    """写路径 dot-key 拒绝（m0b-1 P3-5 遗留——维度 key 含 '.' 一律 400）：
    dot 保留给路径/记号语义（历史 json_each '$.key' 模板的攻击面），维度 key
    走标识符白名单口径（^[A-Za-z_][A-Za-z0-9_]*$，acl_ast 同款）。"""
    for key in dims:
        if "." in key:
            raise UploadValidationError(
                f"dimension key must not contain '.': {key!r}（dot-key 拒绝——写路径校验）"
            )


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
        doc_id: str | None = None,
    ) -> tuple[str, str]:
        """校验（库/维度/取值在授权内）→ 存对象 → 建文档行（parsing）+ 任务（pending）。

        doc_id 缺省 = 首次上传（pending_version=1）；显式携带 = 覆盖上传（§5.3
        文档更新）：操作权限（owner/org_admin）+ pending 409 + 新版本号
        max(历史)+1 + pending_dims_json（pending 期间不生效，P0-2.1）。
        返回 (doc_id, task_id)。
        """
        datasets = {d["id"] for d in self._backend.list_datasets(org_id)}
        if dataset_id not in datasets:
            raise UploadValidationError(f"dataset not found in org: {dataset_id!r}")

        # P3-12：维度值去重（document_dimensions 主键 (doc,dim,value)——重复值会导致
        # index_fts 事务 IntegrityError 且重试永久失败）
        dims = {key: list(dict.fromkeys(values)) for key, values in dims.items()}
        _validate_dim_keys(dims)

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

        obj_name = f"{str(_ulid.ULID()).lower()}{Path(filename or 'bin').suffix}"
        self._objects_dir.mkdir(parents=True, exist_ok=True)
        (self._objects_dir / obj_name).write_bytes(file_bytes)
        content_hash = "sha256:" + hashlib.sha256(file_bytes).hexdigest()

        if doc_id is None:
            doc_id = new_ulid("doc")
            self._backend.create_document(
                doc_id=doc_id,
                org_id=org_id,
                dataset_id=dataset_id,
                title=title or (filename or doc_id),
                source_uri=f"user:{owner_user_id}",
                content_hash=content_hash,
                mime_type=mime_type or "application/octet-stream",
                parser="docling",
                owner_user_id=owner_user_id,
                raw_object_key=obj_name,
                pending_dims_json=json.dumps(dims, ensure_ascii=False) if dims else None,
            )
        else:
            self._start_overwrite(
                doc_id=doc_id,
                org_id=org_id,
                actor_user_id=owner_user_id,
                dataset_id=dataset_id,
                title=title,
                content_hash=content_hash,
                mime_type=mime_type or "application/octet-stream",
                raw_object_key=obj_name,
                pending_dims_json=json.dumps(dims, ensure_ascii=False) if dims else None,
            )
        task_id = self._backend.create_task(doc_id, task_type="ingest")
        return doc_id, task_id

    def _require_document(self, *, doc_id: str, org_id: str) -> dict:
        """覆盖/删除/改维度共用前置：存在 + org 一致（否则 404——存在性敏感）。"""
        doc = self._backend.get_document(doc_id)
        if doc is None or doc["org_id"] != org_id:
            raise UploadNotFoundError(f"document not found in org: {doc_id!r}")
        return doc

    def _require_write_permission(self, *, doc: dict, actor_user_id: str) -> None:
        """管理面操作权限（FR-4 操作矩阵）：覆盖上传/删除/改维度 = owner 或
        org_admin（检索路径无 owner 分支——D22③；管理权与维度写权限分离）。"""
        if doc["owner_user_id"] == actor_user_id:
            return
        membership = self._backend.read_membership(actor_user_id, doc["org_id"])
        if membership is None or membership["role"] != "org_admin":
            raise UploadPermissionError(
                f"operation not permitted: {actor_user_id!r} is neither owner"
                " nor org_admin（FR-4 操作矩阵）"
            )

    def _start_overwrite(
        self,
        *,
        doc_id: str,
        org_id: str,
        actor_user_id: str,
        dataset_id: str,
        title: str,
        content_hash: str,
        mime_type: str,
        raw_object_key: str,
        pending_dims_json: str | None,
    ) -> None:
        """覆盖上传入口（§5.3 文档更新）：操作权限 → pending 409 → 新版本号
        max(历史)+1（失败版本号不复用——P0-2.3）→ 开新 pending（不动 active_*）。"""
        doc = self._require_document(doc_id=doc_id, org_id=org_id)
        self._require_write_permission(doc=doc, actor_user_id=actor_user_id)
        if doc["pending_version"] is not None and doc["pending_status"] != "failed":
            raise UploadConflictError(
                f"document {doc_id!r} 已有进行中的 pending 版本"
                f"（v{doc['pending_version']}，{doc['pending_status']}）——"
                "同一时刻只有一个 pending（409，P0-2.3/T7）"
            )
        new_version = self._backend.max_document_version(doc_id) + 1
        self._backend.start_overwrite(
            doc_id=doc_id,
            pending_version=new_version,
            content_hash=content_hash,
            mime_type=mime_type,
            raw_object_key=raw_object_key,
            pending_dims_json=pending_dims_json,
        )

    # ============ 删除与改维度（M1-2 最小管理面——§6.2） ============

    def delete_document(self, *, org_id: str, doc_id: str, actor_user_id: str) -> None:
        """删除文档：操作权限 → 同事务取消任务 + 级联删（TC-VER-07/T19①）→
        对象文件清理（best effort）。管理动作入 outbox 审计。"""
        doc = self._require_document(doc_id=doc_id, org_id=org_id)
        self._require_write_permission(doc=doc, actor_user_id=actor_user_id)
        object_key = doc["raw_object_key"]
        self._backend.delete_document(doc_id)
        try:
            (self._objects_dir / object_key).unlink(missing_ok=True)
        except OSError:
            logger.warning("object file cleanup failed: %s", object_key)
        self._backend.append_outbox(
            "document.delete",
            json.dumps(
                {"org_id": org_id, "doc_id": doc_id, "actor": actor_user_id},
                ensure_ascii=False,
            ),
        )

    def patch_document_dims(
        self,
        *,
        org_id: str,
        doc_id: str,
        dims: dict[str, list[str]],
        actor_user_id: str,
    ) -> None:
        """PATCH /documents/{id}/dimensions（§6.2——M1-2 ACL 写链最小面）：

        校验链：操作权限（owner/org_admin）→ **pending 期间 409**（P0-2.1——
        切换事务会以 pending_dims_json 覆盖 document_dimensions，PATCH 与其竞态
        一律拒绝）→ dot-key/key/值存在（400）→ **新旧取值均在操作者授权内**
        （403，#31 P1-1：防把文档推向无权范围或操作自己看不见的值——含旧值，
        TC-AZ-01②）→ 按 key 全量替换 document_dimensions（D6 刷维度不重嵌）。
        管理动作入 outbox 审计（TC-AZ-01③）。
        """
        doc = self._require_document(doc_id=doc_id, org_id=org_id)
        self._require_write_permission(doc=doc, actor_user_id=actor_user_id)
        if doc["pending_version"] is not None:
            raise UploadConflictError(
                f"document {doc_id!r} 处理中（pending v{doc['pending_version']}）——"
                "pending 期间禁止修改维度（409，P0-2.1）"
            )

        dims = {key: list(dict.fromkeys(values)) for key, values in dims.items()}
        _validate_dim_keys(dims)
        dims_meta = {d["key"]: d for d in self._backend.list_dimensions(org_id)}
        grants = self._backend.read_grants(actor_user_id, org_id)
        current = self._backend.get_document_dims(doc_id)
        for key, values in dims.items():
            if key not in dims_meta:
                raise UploadValidationError(f"unknown dimension: {key!r}")
            valid_values = {v["value"] for v in dims_meta[key]["values"]}
            for value in values:
                if value not in valid_values:
                    raise UploadValidationError(
                        f"unknown value {value!r} for dimension {key!r}"
                    )
                if value not in grants.get(key, ()):  # 新值越权（TC-AZ-01②前半）
                    raise UploadPermissionError(
                        f"new value {value!r} of dimension {key!r} not within"
                        f" actor grants（{actor_user_id!r}）"
                    )
            # 旧值越权（TC-AZ-01②后半）：该 key 当前值须在操作者授权内——
            # 防操作者把文档推离自己不可见的状态（结果集维度校验）
            for old_value in current.get(key, ()):
                if old_value not in grants.get(key, ()):
                    raise UploadPermissionError(
                        f"current value {old_value!r} of dimension {key!r} not within"
                        f" actor grants（{actor_user_id!r}）——新旧取值均须在授权内"
                    )

        self._backend.set_document_dims(doc_id, dims)
        self._backend.append_outbox(
            "document.dims_change",
            json.dumps(
                {
                    "org_id": org_id,
                    "doc_id": doc_id,
                    "actor": actor_user_id,
                    "dims": dims,
                },
                ensure_ascii=False,
            ),
        )

    # ============ 执行器（进程内——M0a/M1；子进程化随 M2） ============

    def run_task(self, task_id: str, *, stop_after: str | None = None) -> None:
        """执行摄取任务（阶段幂等：重跑从上一完成阶段续——TC-ING-07）。

        stop_after：测试/中断缝（'parse'|'chunk'|'index_fts' 后返回，模拟进程中断；
        任务留在 running 态、**不写 done**——由重跑续上，P3-1）。异常统一落
        failed+error 并写文档失败态（P2-1：按 id 重读文档后落 active_error/pending；
        pending 失败立即删块——T8）。文档已删/版本被顶替时任务优雅取消（failed +
        'cancelled'——TC-VER-07，不冒泡）。
        """
        task = self._backend.get_task(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        doc = self._backend.get_document(task["doc_id"])
        if doc is None:
            # 文档已删（tasks.doc_id 置 NULL / 行已不在）：任务在取消态——重跑
            # 直接幂等拒绝（TC-VER-07：已删文档不再写块），非终态兜底落取消
            if task["status"] not in ("done", "failed"):
                self._backend.update_task(
                    task_id, status="failed", error="cancelled: document deleted"
                )
            return

        self._backend.update_task(task_id, status="leased")
        self._backend.update_task(task_id, status="running")
        try:
            outcome = self._run_stages(doc, stop_after=stop_after)
            if outcome == "interrupted":
                return  # 模拟中断：任务留 running，不写 done（P3-1）
            if outcome == "cancelled":
                # 文档已删/版本被顶替（含 failed 版本旧任务重跑）：取消在阶段边界
                # 生效（TC-VER-07——状态机无 cancelled 枚举，以 failed + 'cancelled:'
                # error 落账）
                self._backend.update_task(
                    task_id,
                    status="failed",
                    error="cancelled: document deleted or version superseded",
                )
                return
            self._backend.update_task(task_id, status="done")
        except Exception as exc:  # noqa: BLE001 —— 任务级失败统一落 failed+error
            logger.exception("ingest task failed: %s", task_id)
            self._backend.update_task(task_id, status="failed", error=str(exc))
            self._record_doc_error(doc, exc)
            raise

    def _record_doc_error(self, doc: dict, exc: Exception) -> None:
        """失败写文档侧：首次上传已切换 → active_error；pending 版本 →
        pending_status=failed + pending_error + **立即物理删块**（T8，同一事务）。

        P2-1：同次执行内 index_fts 的 D20 切换已改写 DB（pending 清空、
        active_version=1），调用方传入的 doc 快照是切换前的——按 id 重读后再判定
        落点，否则 UPDATE 零行、失败态整体丢失。
        """
        fresh = self._backend.get_document(doc["id"])
        if fresh is not None:
            doc = fresh
        version = doc.get("pending_version") or doc.get("active_version")
        if doc.get("pending_version") == version and version is not None:
            self._backend.set_doc_pending_failed(doc["id"], version, str(exc))
        else:
            self._backend.set_doc_active_error(doc["id"], version, str(exc))

    def _effective_version(self, doc: dict) -> int:
        return doc.get("pending_version") or doc["active_version"]

    def _guard_alive(self, doc_id: str, version: int) -> dict | None:
        """阶段开始前检查（TC-VER-07）：文档存在且 version 仍是**当前处理目标**
        （pending 未终态或已切在用）——否则返回 None（任务取消，不再写块）。

        failed 版本不是合法处理目标（P0-2.3：重试=再上传走新版本号，旧任务
        重跑不得重建失败版本块——版本号不复用）；首次上传失败（active_error，
        版本已切在用）不受影响——重试从 embed 续（TC-EMB-01/TC-E2E-01）。
        """
        doc = self._backend.get_document(doc_id)
        if doc is None:
            return None
        current = doc.get("pending_version") or doc.get("active_version")
        if current != version:
            return None
        if doc.get("pending_version") == version and doc.get("pending_status") == "failed":
            return None
        return doc

    def _index_fts_done(self, doc: dict, version: int) -> bool:
        """幂等续跑判定（TC-ING-07）：目标版本的块是否已写（index_fts 已提交）。"""
        if doc.get("active_version") == version and doc.get("active_status") in (
            "searchable_lexical",
            "searchable_full",
        ):
            return True  # 首次上传：D20 已切在用
        if doc.get("pending_version") == version and doc.get("pending_status") in (
            "searchable_lexical",
            "searchable_full",
        ):
            return True  # 覆盖上传：pending 版本块已提交（lexical 时点不切换——D20）
        return False

    def _run_stages(self, doc: dict, *, stop_after: str | None) -> str:
        """返回 'completed' | 'interrupted'（stop_after 中断缝）| 'cancelled'
        （文档已删/版本被顶替——阶段边界取消，TC-VER-07）。"""
        doc_id = doc["id"]
        version = self._effective_version(doc)
        # 阶段判定（幂等续跑）：目标版本块已写 → 跳过 parse/chunk/index_fts；
        # 目标版本已 searchable_full → 幂等 no-op（重跑 done 任务）
        done = self._guard_alive(doc_id, version)
        if done is None:
            return "cancelled"
        if not self._index_fts_done(done, version):
            doc = done
            parsed = self._parse_stage(doc)
            doc = self._guard_alive(doc_id, version)
            if doc is None:
                return "cancelled"
            if stop_after == "parse":
                return "interrupted"
            drafts = self._chunk_stage(doc, parsed)
            doc = self._guard_alive(doc_id, version)
            if doc is None:
                return "cancelled"
            if stop_after == "chunk":
                return "interrupted"
            self._index_fts_stage(doc, drafts)
            if stop_after == "index_fts":
                return "interrupted"
            doc = self._guard_alive(doc_id, version)
            if doc is None:
                return "cancelled"
        else:
            doc = done
        if (
            doc.get("active_version") == version
            and doc.get("active_status") == "searchable_full"
        ):
            return "completed"  # 幂等 no-op（重跑 done 任务）
        self._embed_stage(doc, version)
        return "completed"

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
        # v1.1（拍板 1）：chunk 不再携带 dims_json 投影——维度经 documents.
        # pending_dims_json 在 insert 事务内解析入 document_dimensions（D22 机制）
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
            }
            for d in drafts
        ]
        self._backend.insert(doc["id"], self._effective_version(doc), chunks)

    def _embed_stage(self, doc: dict, version: int) -> None:
        doc_id = doc["id"]
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
            # P2-3：core 只传浮点向量——vec_f32 BLOB 序列化收口 store 方言侧；
            # 回写防护（TC-VER-06）：tombstone=0 + 标签匹配 + (rid,label) 无行
            # （ON CONFLICT DO NOTHING 组）——已切换/已删块的回写零行生效
            self._backend.write_embeddings(
                label, [(row["rid"], v) for row, v in zip(batch, vectors)]
            )
        self._finish_embed(doc_id, version)

    def _finish_embed(self, doc_id: str, version: int) -> None:
        """embed 完成收尾（D20 切换时机分叉）：

        - 首次上传（version 已是在用）：进度写 active_status=searchable_full；
        - 覆盖上传（version 仍是 pending）：pending→searchable_full 后**单事务切换**
          （switch_active_version——乐观校验；被并发抢先切换且已 full 时幂等成功）。
        """
        doc = self._backend.get_document(doc_id)
        if doc is None:
            raise KeyError(f"document not found: {doc_id}")
        if doc.get("active_version") == version:
            self._backend.set_doc_active_status(doc_id, version, "searchable_full")
            return
        self._backend.set_doc_pending_status(doc_id, version, "searchable_full")
        try:
            self._backend.switch_active_version(doc_id, expected_pending=version)
        except VersionConflictError:
            fresh = self._backend.get_document(doc_id)
            if (
                fresh is not None
                and fresh.get("active_version") == version
                and fresh.get("active_status") == "searchable_full"
            ):
                return  # 并发已切换完成——幂等成功
            raise
