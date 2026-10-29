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
from collections.abc import Callable
from pathlib import Path

import ulid as _ulid

from knowledge_lattice.adapters.embedder import (
    EmbeddingGate,
    EmbeddingResponseError,
    Embedder,
    validate_dim,
)
from knowledge_lattice.adapters.parser_docling import (
    LEGACY_SUFFIXES,
    ParsedDocument,
    parse_document,
)
from knowledge_lattice.config import Settings
from knowledge_lattice.core.docs.chunking import ChunkDraft, chunk_blocks
from knowledge_lattice.core.docs.quality import (
    MojibakeQualityError,
    QualityService,
    mojibake_tier,
)
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


class _LostLeaseError(Exception):
    """执行中途租约失守/取消（should_continue=False 在不可返回的深处触发——
    embed 批次边界）：run_task 以 lost_lease 语义静默退出，不落终态不写文档侧。"""


def new_ulid(prefix: str) -> str:
    return f"{prefix}_{str(_ulid.ULID()).lower()}"


def _copy_streaming(src: Path, dst: Path) -> str:
    """流式拷贝 + sha256 增量哈希（P3-10——consume 路径 200MB 档不整体读内存）；
    返回 hex digest。"""
    digest = hashlib.sha256()
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            block = fsrc.read(64 * 1024)
            if not block:
                break
            digest.update(block)
            fdst.write(block)
    return digest.hexdigest()


def _validate_dim_keys(dims: dict[str, list[str]]) -> None:
    """写路径 dot-key 拒绝（m0b-1 P3-5 遗留——维度 key 含 '.' 一律 400）：
    dot 保留给路径/记号语义（历史 json_each '$.key' 模板的攻击面），维度 key
    走标识符白名单口径（^[A-Za-z_][A-Za-z0-9_]*$，acl_ast 同款）。"""
    for key in dims:
        if "." in key:
            raise UploadValidationError(
                f"dimension key must not contain '.': {key!r}（dot-key 拒绝——写路径校验）"
            )


def _require_values_in_grants(
    *,
    key: str,
    values,
    grants: dict[str, tuple[str, ...]],
    actor_user_id: str,
    what: str,
) -> None:
    """取值 ∈ 操作者授权校验（FR-4「新旧取值均须校验」）——**唯一实现**，三处共用：

    1. `create_document` 新值校验（what="upload"——P3-C〔m1-2 R2〕收敛：原 upload 侧
       内联副本已删，两份实现并一，防本段改造 upload 链时漂移）；
    2. `_start_overwrite` 旧值校验（what="current"——B-1①）；
    3. `patch_document_dims` 新旧值校验（what="new"/"current"——TC-AZ-01）。

    what 为文案前缀（403 语义与错误定位一致）。
    """
    allowed = grants.get(key, ())
    for value in values:
        if value not in allowed:
            raise UploadPermissionError(
                f"{what} value {value!r} of dimension {key!r} not within"
                f" actor grants（{actor_user_id!r}）——新旧取值均须在授权内（FR-4）"
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
        *,
        quality: QualityService | None = None,
    ) -> None:
        self._backend = backend
        self._embedder = embedder
        self._settings = settings
        self._gate = gate
        self._objects_dir = objects_dir
        # 区分度环挂接（M1-4 §5.3 quality 阶段——检测 best-effort，None=未装配）
        self._quality = quality

    # ============ 上传入口（写权限校验在 upload 即做——P0-2.1） ============

    def create_document(
        self,
        *,
        org_id: str,
        dataset_id: str,
        title: str,
        dims: dict[str, list[str]],
        owner_user_id: str,
        file_bytes: bytes | None = None,
        file_src: Path | None = None,
        mime_type: str,
        filename: str,
        doc_id: str | None = None,
        source_uri: str | None = None,
    ) -> tuple[str, str]:
        """校验（库/维度/取值在授权内）→ 存对象 → 建文档行（parsing）+ 任务（pending）。

        doc_id 缺省 = 首次上传（pending_version=1）；显式携带 = 覆盖上传（§5.3
        文档更新）：操作权限（owner/org_admin）+ pending 409 + 新版本号
        max(历史)+1 + pending_dims_json（pending 期间不生效，P0-2.1）。
        source_uri：缺省 `user:<owner>`；凭证消费（M1-3）传 `agent:<服务身份>`
        ——agent 代传内容标来源，随检索返回（§6.1）。

        字节来源二选一（M2.1 P3-10 清偿）：file_bytes（multipart 直传——请求侧
        已在内存）或 file_src（凭证消费路径——**流式拷贝 + 增量哈希**，200MB
        档不整体读内存）。返回 (doc_id, task_id)。
        """
        datasets = {d["id"] for d in self._backend.list_datasets(org_id)}
        if dataset_id not in datasets:
            raise UploadValidationError(f"dataset not found in org: {dataset_id!r}")
        if (file_bytes is None) == (file_src is None):
            raise UploadValidationError(
                "exactly one of file_bytes / file_src is required"
            )

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
            # P3-C 锚定（m1-2 R2）：upload 侧新值 ∈ 授权校验与 PATCH/覆盖上传共用
            # `_require_values_in_grants` 同一实现（原内联副本已删——防两份漂移）
            _require_values_in_grants(
                key=key, values=values, grants=grants,
                actor_user_id=owner_user_id, what="upload",
            )
        for key, meta in dims_meta.items():
            if meta["required"] and not dims.get(key):
                raise UploadValidationError(f"required dimension missing values: {key!r}")

        # TC-ING-04②：老格式拒收（.doc/.xls/.ppt）——提示转存新格式，不引入
        # LibreOffice（零中间件纪律）；在校验链之后、对象落盘之前快速失败
        suffix = Path(filename or "").suffix.lower()
        if suffix in LEGACY_SUFFIXES:
            raise UploadValidationError(
                f"老格式 {suffix} 不受支持——请转存为新格式"
                "（.docx/.xlsx/.pptx）后重传（TC-ING-04②）"
            )

        obj_name = f"{str(_ulid.ULID()).lower()}{Path(filename or 'bin').suffix}"
        self._objects_dir.mkdir(parents=True, exist_ok=True)
        obj_path = self._objects_dir / obj_name
        if file_bytes is not None:
            obj_path.write_bytes(file_bytes)
            content_hash = "sha256:" + hashlib.sha256(file_bytes).hexdigest()
        else:
            # P3-10：凭证消费路径流式拷贝 + 增量哈希（64KB 分块——峰值内存与
            # 对象体积解耦）；源对象经调用方（consume）先行哈希复验
            content_hash = "sha256:" + _copy_streaming(file_src, obj_path)

        # P3-9（m1-2）+ P2-3（R2 收窄）：对象先落盘、**文档行写失败** → unlink
        # 补偿（不留孤儿对象；校验已先行，本防护覆盖 DB 层失败——约束违例/
        # 磁盘满等）。补偿范围限定 create_document/_start_overwrite 本身——
        # **create_task 失败保留对象**（文档行已在库并引用该对象，删了反而
        # 造成「文档引用缺失对象」的不一致；任务缺失可由重试/维护面补）
        task_version: int | None = None
        try:
            if doc_id is None:
                doc_id = new_ulid("doc")
                self._backend.create_document(
                    doc_id=doc_id,
                    org_id=org_id,
                    dataset_id=dataset_id,
                    title=title or (filename or doc_id),
                    source_uri=source_uri or f"user:{owner_user_id}",
                    content_hash=content_hash,
                    mime_type=mime_type or "application/octet-stream",
                    parser="docling",
                    owner_user_id=owner_user_id,
                    raw_object_key=obj_name,
                    pending_dims_json=json.dumps(dims, ensure_ascii=False) if dims else None,
                )
                task_version = 1  # 首传：pending v1（create_document 置 1）
            else:
                task_version = self._backend.max_document_version(doc_id) + 1
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
                    pending_version=task_version,  # 与 _start_overwrite 同源版本号
                    grants=grants,  # B-1①：复用已读授权展开（同一 actor，不二次读）
                )
        except BaseException:
            try:
                (self._objects_dir / obj_name).unlink(missing_ok=True)
            except OSError:
                logger.warning("orphan object cleanup failed: %s", obj_name)
            raise
        # create_task 在补偿范围外（P2-3）：文档行已引用对象——失败上抛但对象保留；
        # target_version（0005）：首传=1 / 覆盖上传=新 pending 版本号——取消与
        # 崩溃耗尽清扫按任务目标版本落失败（不误杀新版本上传，P2-3）
        task_id = self._backend.create_task(
            doc_id, task_type="ingest", target_version=task_version
        )
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
        pending_version: int | None = None,
        grants: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        """覆盖上传入口（§5.3 文档更新）：操作权限 → **旧维度值校验**（B-1①，
        FR-4 严格口径——文档当前全部维度值 ∈ 操作者 grants，与新值共用同一
        公共校验 `_require_values_in_grants`，防两处漂移）→ pending 409 →
        新版本号 max(历史)+1（失败版本号不复用——P0-2.3）→ 开新 pending
        （不动 active_*）。

        pending_version（M2.1 R2）：调用方已计算的新版本号（与 create_task 的
        target_version 同源——一次读取两处消费，防「任务目标版本 ≠ 实开 pending
        版本」的错位）；缺省时本方法自算（兼容旧调用形态）。

        旧值校验理由：切换事务将**整体替换** document_dimensions（pending_dims_json
        覆盖），操作者须对现行状态有写权限——防「把文档拉回自己可见域而不曾
        看见现行状态」（如 u_cn 文档被 admin PATCH 成 [OS] 后 u_cn 写回 [CN]）。
        首上传无旧值不涉及（create 分支不经本方法）。"""
        doc = self._require_document(doc_id=doc_id, org_id=org_id)
        self._require_write_permission(doc=doc, actor_user_id=actor_user_id)
        if doc["pending_version"] is not None and doc["pending_status"] != "failed":
            raise UploadConflictError(
                f"document {doc_id!r} 已有进行中的 pending 版本"
                f"（v{doc['pending_version']}，{doc['pending_status']}）——"
                "同一时刻只有一个 pending（409，P0-2.3/T7）"
            )
        # B-1①：文档当前（旧）维度值 ∈ 操作者授权（全部维度——切换整体替换）
        if grants is None:
            grants = self._backend.read_grants(actor_user_id, org_id)
        for key, old_values in self._backend.get_document_dims(doc_id).items():
            _require_values_in_grants(
                key=key, values=old_values, grants=grants,
                actor_user_id=actor_user_id, what="current",
            )
        if pending_version is None:
            pending_version = self._backend.max_document_version(doc_id) + 1
        try:
            self._backend.start_overwrite(
                doc_id=doc_id,
                pending_version=pending_version,
                content_hash=content_hash,
                mime_type=mime_type,
                raw_object_key=raw_object_key,
                pending_dims_json=pending_dims_json,
            )
        except VersionConflictError as exc:
            # R2 P2-2：库级兜底（start_overwrite WHERE 零行）映射 409 语义——
            # 不映射则 REST 500 违 §6.2（服务层快照校验后、库级窗口内竞态）
            raise UploadConflictError(
                f"document {doc_id!r} 已有进行中的 pending 版本"
                "（库级兜底触发——并发覆盖窗口，P0-2.3/T7）"
            ) from exc

    # ============ 删除与改维度（M1-2 最小管理面——§6.2） ============

    def _fail_doc_version(self, doc_id: str, target_version: int, reason: str) -> None:
        """按**任务目标版本**落 pending failed + 删块（P2-3，M2.1 R2）。

        仅当文档当前 pending_version == target_version 且非 failed 时生效——
        目标版本已切换收编（pending 清空）/被新版本取代/无版本任务（None）时
        不触碰文档（防「取消旧任务误杀新版本上传」；切换竞态由 store 层
        set_doc_pending_failed 的 rowcount 守卫〔P1-1〕兜底）。取消（cancel_task）
        与崩溃耗尽清扫（fail_document_version）共用本实现。
        """
        doc = self._backend.get_document(doc_id)
        if (
            doc is not None
            and doc.get("pending_version") == target_version
            and doc.get("pending_status") not in ("failed", None)
        ):
            self._backend.set_doc_pending_failed(doc_id, target_version, reason)

    def fail_document_version(self, task_row: dict, reason: str) -> None:
        """崩溃耗尽清扫的文档侧收尾（P2-2，M2.1 R2）：按任务行 target_version
        落 pending failed + 删块（T8 同款）；无版本/版本不匹配不触碰。"""
        if task_row.get("doc_id") is None:
            return
        version = task_row.get("target_version")
        if version is None:
            return  # 存量行（0005 前）无版本关联——任务行已 failed 留人工，文档侧登记移交
        self._fail_doc_version(task_row["doc_id"], version, reason)

    def cancel_task(self, *, org_id: str, task_id: str, actor_user_id: str) -> dict:
        """任务取消（M2.1——TC-TASK-03，POST /api/orgs/{org}/tasks/{id}/cancel）：

        1. 任务定位（404 语义：不存在/无文档归属/跨组织——maintenance 等无文档
           任务不在 org 路径管辖内）；
        2. 操作权限（FR-4 操作矩阵：owner / org_admin——与删除/覆盖上传同款）；
        3. `backend.cancel_task` 原子转终态（非终态 → failed + 'cancelled: by user
           request' + 清租约；**已终态 → 不动**——幂等续跑不复活）；
        4. 文档侧一致性（不滞留 parsing）：**按任务 target_version**（0005/P2-3，
           非文档当前 pending）落 pending failed + 删块——取消旧任务（目标版本
           已是 active 或已被 v2 取代）不触碰新版本上传；首传已切换（无 pending）
           → 文档停在 searchable_lexical 稳态。

        在途 worker 在下一阶段/批次边界经 should_continue 探测到取消并停止
        （lost_lease——不写终态不改文档，取消结果为准）。返回取消后的任务行。
        """
        task = self._backend.get_task(task_id)
        if task is None or task.get("doc_id") is None:
            raise UploadNotFoundError(f"task not found in org: {task_id!r}")
        doc = self._require_document(doc_id=task["doc_id"], org_id=org_id)
        self._require_write_permission(doc=doc, actor_user_id=actor_user_id)

        cancelled = self._backend.cancel_task(
            task_id, reason="cancelled: by user request"
        )
        if cancelled is not None and task.get("target_version") is not None:
            self._fail_doc_version(
                doc["id"], task["target_version"], "cancelled by user request"
            )
        return self._backend.get_task(task_id)

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
            # 新值越权（TC-AZ-01②前半）——公共校验（与覆盖上传共用，R2 B-1①）
            _require_values_in_grants(
                key=key, values=values, grants=grants,
                actor_user_id=actor_user_id, what="new",
            )
            # 旧值越权（TC-AZ-01②后半）：该 key 当前值须在操作者授权内——
            # 防操作者把文档推离自己不可见的状态（结果集维度校验）
            _require_values_in_grants(
                key=key, values=current.get(key, ()), grants=grants,
                actor_user_id=actor_user_id, what="current",
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

    # ============ 执行器（M2.1 起经 worker TaskRunner 驱动；直调保留为单测捷径） ============

    def run_task(
        self, task_id: str, *, stop_after: str | None = None,
        should_continue: Callable[[], bool] | None = None,
    ) -> None:
        """执行摄取任务（阶段幂等：重跑从上一完成阶段续——TC-ING-07）。

        stop_after：测试/中断缝（'parse'|'chunk'|'index_fts' 后返回，模拟进程中断；
        任务留在 running 态、**不写 done**——由重跑续上，P3-1）。异常统一落
        failed+error 并写文档失败态（P2-1：按 id 重读文档后落 active_error/pending；
        pending 失败立即删块——T8）。文档已删/版本被顶替时任务优雅取消（failed +
        'cancelled'——TC-VER-07，不冒泡）。

        should_continue（M2.1 worker 框架）：阶段边界存活检查（租约心跳/取消探测，
        TC-TASK-03）——False 时任务停在当前阶段边界并返回 **不落任何终态**（任务
        行此刻由外部动作方所有：取消已写 failed / 租约已被重认领）。已取消终态
        （error 以 'cancelled:' 开头）的任务重跑直接幂等拒绝（取消不复活）。
        """
        task = self._backend.get_task(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        if task["status"] == "failed" and (task.get("error") or "").startswith("cancelled:"):
            # 取消终态：幂等续跑不复活（TC-TASK-03）——取消是吸收态
            return
        doc = self._backend.get_document(task["doc_id"])
        if doc is None:
            # 文档已删（tasks.doc_id 置 NULL / 行已不在）：任务在取消态——重跑
            # 直接幂等拒绝（TC-VER-07：已删文档不再写块），非终态兜底落取消
            if task["status"] not in ("done", "failed"):
                self._backend.update_task(
                    task_id, status="failed", error="cancelled: document deleted"
                )
            return

        def _alive() -> bool:
            return should_continue is None or should_continue()

        # 目标版本（0005/P2-3）：任务行携带的 v1/vN 优先——阶段守卫/幂等续跑按
        # 任务自己的版本判定（新 pending 顶替旧任务目标版本时旧任务优雅取消）；
        # 存量行（NULL）回退文档当前有效版本（M1 口径）
        version = task.get("target_version")
        if version is None:
            version = self._effective_version(doc)

        self._backend.update_task(task_id, status="leased")
        self._backend.update_task(task_id, status="running")
        try:
            outcome = self._run_stages(doc, version=version, stop_after=stop_after,
                                       should_continue=should_continue)
            if outcome == "interrupted":
                return  # 模拟中断：任务留 running，不写 done（P3-1）
            if outcome == "lost_lease":
                # 租约失守/取消先行落账（should_continue=False）：任务行归外部
                # 动作方所有（取消已写 failed 或新持有者已接管）——本执行器静默
                # 退出，不写终态不改文档（TC-TASK-03 阶段边界停止）
                logger.warning("ingest task lost lease/cancelled at stage boundary: %s", task_id)
                return
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
            # P2-1（M2.1 R2）终态前最后探测：quality 等长阶段内取消/丢租约时
            # done 不得覆盖取消终态（update_task 的 done 守卫为库级兜底）
            if not _alive():
                logger.warning(
                    "ingest task lost lease/cancelled before terminal write: %s", task_id
                )
                return
            self._backend.update_task(task_id, status="done")
        except _LostLeaseError:
            # embed 批次边界失守（深处不可返回处 raise）：同 lost_lease 语义——
            # 任务行归外部动作方所有，静默退出（TC-TASK-03）
            logger.warning("ingest task lost lease/cancelled in embed stage: %s", task_id)
            return
        except Exception as exc:  # noqa: BLE001 —— 任务级失败统一落 failed+error
            if not _alive():
                # P2-1（M2.1 R2）except 首行探测：丢租约/取消后的异常不写终态、
                # 不写文档侧——任务行归取消方/新持有者所有
                logger.warning(
                    "ingest task lost lease/cancelled before failure write: %s", task_id
                )
                return
            fresh = self._backend.get_task(task_id)
            if fresh is not None and fresh["status"] == "failed" and (
                fresh.get("error") or ""
            ).startswith("cancelled:"):
                # 取消与在途执行竞争（如取消已把 pending 落 failed、本执行器的
                # insert 存活复核 raise）：终态归取消所有——不覆盖、不写文档侧
                logger.warning("ingest task aborted by concurrent cancel: %s", task_id)
                return
            logger.exception("ingest task failed: %s", task_id)
            self._backend.update_task(task_id, status="failed", error=str(exc))
            self._record_doc_error(doc, exc, version=version)
            raise

    def _record_doc_error(
        self, doc: dict, exc: Exception, *, version: int | None = None
    ) -> None:
        """失败写文档侧：**按任务目标版本**（P2-N1，M2.1 R4）——pending 版本 →
        pending_status=failed + pending_error + **立即物理删块**（T8，同一事务）；
        已切在用版本 → active_error；版本已被切换收编/被新版本取代 → 不触碰
        当前 pending/active（旧任务失败不得静默杀死并发新版本上传）。

        P2-1：同次执行内 index_fts 的 D20 切换已改写 DB（pending 清空、
        active_version=1），调用方传入的 doc 快照是切换前的——按 id 重读后再判定
        落点，否则 UPDATE 零行、失败态整体丢失。
        version=None（legacy 直调无 target）→ 回退文档当前有效版本（M1 口径）；
        store 层 P1 rowcount 守卫保留为第二道防线。
        """
        fresh = self._backend.get_document(doc["id"])
        if fresh is not None:
            doc = fresh
        if version is None:
            version = doc.get("pending_version") or doc.get("active_version")
        if version is None:
            return
        if doc.get("pending_version") == version:
            self._backend.set_doc_pending_failed(doc["id"], version, str(exc))
        elif doc.get("active_version") == version:
            self._backend.set_doc_active_error(doc["id"], version, str(exc))
        # else：目标版本已被切换收编/被新版本取代——不得触碰当前 pending/active
        # （如首传 T1 失败时并发覆盖上传已开 pending v2——v2 归 T2 所有）

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

    def _run_stages(
        self, doc: dict, *, version: int | None = None,
        stop_after: str | None = None,
        should_continue: Callable[[], bool] | None = None,
    ) -> str:
        """返回 'completed' | 'interrupted'（stop_after 中断缝）| 'cancelled'
        （文档已删/版本被顶替——阶段边界取消，TC-VER-07）| 'lost_lease'
        （should_continue=False——租约失守/取消，M2.1）。

        version（M2.1 R2）：任务目标版本（0005/P2-3）——由 run_task 传入；None
        回退文档当前有效版本（直调/存量行 M1 口径）。阶段守卫按该版本判定归属。
        """

        def _alive() -> bool:
            return should_continue is None or should_continue()

        doc_id = doc["id"]
        if version is None:
            version = self._effective_version(doc)
        # 阶段判定（幂等续跑）：目标版本块已写 → 跳过 parse/chunk/index_fts；
        # 目标版本已 searchable_full → 幂等 no-op（重跑 done 任务）
        #
        # 边界检查次序（M2.1）：先 _alive（租约/取消探测）后 guard_alive——取消
        # 已同时落任务 failed + pending failed 时，任务行的终态归取消动作方所有
        # （lost_lease 静默退出），本执行器不得以 cancelled 结果覆写其 error。
        done = self._guard_alive(doc_id, version)
        if done is None:
            return "cancelled"
        if not _alive():
            return "lost_lease"
        if not self._index_fts_done(done, version):
            doc = done
            parsed = self._parse_stage(doc)
            if not _alive():
                return "lost_lease"
            doc = self._guard_alive(doc_id, version)
            if doc is None:
                return "cancelled"
            if stop_after == "parse":
                return "interrupted"
            drafts = self._chunk_stage(doc, parsed)
            if not _alive():
                return "lost_lease"
            doc = self._guard_alive(doc_id, version)
            if doc is None:
                return "cancelled"
            if stop_after == "chunk":
                return "interrupted"
            self._index_fts_stage(doc, drafts)
            if stop_after == "index_fts":
                return "interrupted"
            if not _alive():
                return "lost_lease"
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
        self._embed_stage(doc, version, should_continue=should_continue)
        if not _alive():
            return "lost_lease"
        self._quality_stage(doc)
        return "completed"

    def _quality_stage(self, doc: dict) -> None:
        """区分度检测 + LLM 兜底（§5.3 quality 阶段——detect → flags → LLM 关键词
        → 回写 llm_keywords，编排逐项）：**best-effort**——searchable_full 已达成，
        失败不回退文档状态（告警 + outbox，重算/重跑兜底可补）；未装配 quality
        服务（旧构造）为 no-op。

        P2-2（R2）：LLM 兜底在检测后自动接入（doc 作用域——本阶段新产 flags）；
        noop provider（quality_llm=none 默认）run_llm_keywords 早返回零成本。
        """
        if self._quality is None:
            return
        try:
            self._quality.detect_document(doc["id"], org_id=doc["org_id"])
        except Exception:  # noqa: BLE001 —— 检测失败不回退 searchable_full
            logger.exception("quality detect failed: %s", doc["id"])
            try:
                self._backend.append_outbox(
                    "quality.detect_failed",
                    json.dumps({"doc_id": doc["id"]}, ensure_ascii=False),
                )
            except Exception:  # noqa: BLE001
                logger.exception("quality.detect_failed audit write failed")
            return  # 检测失败即无新 flags——兜底不发起（重跑补）
        try:
            self._quality.run_llm_keywords(
                org_id=doc["org_id"], doc_id=doc["id"]
            )
        except Exception:  # noqa: BLE001 —— 兜底失败不阻断（增益路，可重跑）
            logger.exception("llm keywords stage failed: %s", doc["id"])

    # ---- 阶段实现（各自幂等/可重入） ----

    def _object_path(self, doc: dict) -> Path:
        return self._objects_dir / doc["raw_object_key"]

    def _parse_stage(self, doc: dict) -> ParsedDocument:
        self._backend.set_doc_pending_status(doc["id"], self._effective_version(doc), "parsing")
        parsed = parse_document(self._object_path(doc))
        # mojibake 质量门（§5.4 OneRAG 借鉴项——TC-ING-05 三档）：fail → raise
        #（任务 failed + T8 删块）；warn → 告警 + 审计（TXT 的「重试」已在编码
        # 探测候选内完成——decode_txt_bytes 取最优候选）；pass 静默。
        text = "\n".join(b.content for b in parsed.blocks)
        tier, ratio = mojibake_tier(text)
        if tier == "fail":
            raise MojibakeQualityError(
                f"mojibake quality gate: normal char ratio {ratio:.3f} < 0.40"
                "（解析产物疑似乱码——拒绝入库，TC-ING-05）"
            )
        if tier == "warn":
            logger.warning(
                "mojibake warn: doc=%s ratio=%.3f（编码候选已穷尽，按最优候选继续）",
                doc["id"], ratio,
            )
            self._backend.append_outbox(
                "quality.mojibake_warn",
                json.dumps(
                    {"doc_id": doc["id"], "ratio": round(ratio, 4)},
                    ensure_ascii=False,
                ),
            )
        return parsed

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

    def _embed_stage(
        self, doc: dict, version: int, *,
        should_continue: Callable[[], bool] | None = None,
    ) -> None:
        doc_id = doc["id"]
        self._gate.ensure_writable()  # 拒绝档：拒绝以同标签写入（可重试——TC-EMB-03）
        label = self._embedder.model_label
        pending = self._backend.mark_embedding_batch(doc_id, version, label)
        batch_size = self._settings.embed_batch_size
        for start in range(0, len(pending), batch_size):
            # 批次边界存活检查（M2.1——取消在 embed 长阶段内的细粒度边界生效，
            # TC-TASK-03；剩余批次零外呼）
            if should_continue is not None and not should_continue():
                raise _LostLeaseError(
                    f"embed stage aborted at batch boundary (lease lost/cancelled)"
                    f" doc={doc_id!r} v{version}"
                )
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
