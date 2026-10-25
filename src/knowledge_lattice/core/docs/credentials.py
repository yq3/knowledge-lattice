"""上传凭证（三步式——design §6.1 upload 契约 / §6.2 POST /api/uploads + PUT /
api/uploads/{id} / §6.3 agent 侧时序；#33 P1-3/#32 P0-D）。

三步流：
  ① agent 运行时（非 LLM）持 token 调 `issue()`——凭证绑定 **sub+org+服务身份**
     三要素 + expires_at（TTL 可配，默认 15min）；
  ② 运行时 PUT 字节到 upload_url——流式进 staging（前置校验先行：超声明 413 不
     静默截断〔附录 A-13〕/ >全局上限 413〔P3-13〕/ sha256 不符 400；失败即 unlink
     补偿清理〔P3-5/P3-21——无孤儿文件〕；失败 PUT 不计消费、可修正重传直至成功
     消费或过期）；
  ③ MCP `upload(upload_id, ...)` 消费——三一致校验（T11：换 org/换用户/换服务
     身份一律拒绝，**凭证绑定专属错误码**）+ 哈希复验（TOCTOU 防线）→ 走
     `ingest.create_document` **同一 code path**（pending 409 / ACL 写校验 / B-1①
     旧值校验不旁路）→ 摄取成功入队后置已用（v1.4 口径：「用掉」＝摄取成功入队
     ——与 T12 统一）。

file_ref 防线（TC-CRED-04/NFR-6 三防线）：`upload_id` 只收不透明
`upl_<ulid>`（路径穿越/绝对路径/URL/异形一律 400）；对象键由服务端派生，读取侧
白名单根目录 + realpath 规范化 + 前缀校验纵深（直插越界 object_key 的凭证行在
消费侧被拒——invalid_object_ref）。

时间契约（P3-10）：库内存储 UTC `YYYY-MM-DD HH:MM:SS`（CURRENT_TIMESTAMP 同
格式）；API 序列化统一 UTC ISO 8601（Z 后缀）——`to_utc_iso`。

分层纪律：本模块属 core 业务层——SQL 全部经 StorageBackend Admin 域凭证方法，
文件 staging 在 objects/ 目录（与 ingest 对象目录同根）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path

import ulid as _ulid

from knowledge_lattice.config import Settings

logger = logging.getLogger(__name__)

# 不透明凭证 id：upl_ + 26 位小写 ULID——路径/URL/异形一律拒绝（TC-CRED-04）
UPLOAD_ID_RE = re.compile(r"^upl_[0-9a-z]{26}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


# ============ 异常（code＝对外错误码——T12「全部带明确错误码」） ============


class CredentialError(Exception):
    """凭证链错误基类——code 为机器可读错误码、http_status 为 REST 语义。"""

    code = "credential_error"
    http_status = 400


class InvalidUploadIdError(CredentialError):
    code = "invalid_upload_id"  # 非不透明 id（穿越/绝对路径/URL/异形）——TC-CRED-04


class InvalidRequestError(CredentialError):
    code = "invalid_request"  # 签发声明不合法（sha256 非 hex / size<=0 / filename 空）


class CredentialNotFoundError(CredentialError):
    code = "upload_not_found"
    http_status = 404


class CredentialBindingError(CredentialError):
    """三一致校验失败（T11 凭证绑定专属错误码——sub/org/服务身份任一不符）。"""

    code = "binding_mismatch"
    http_status = 403


class CredentialExpiredError(CredentialError):
    code = "upload_expired"
    http_status = 410


class CredentialConsumedError(CredentialError):
    code = "upload_consumed"
    http_status = 409


class SizeExceededError(CredentialError):
    code = "size_exceeded"  # 超声明 size（413 不静默截断——附录 A-13）
    http_status = 413


class SizeOverLimitError(CredentialError):
    code = "size_over_limit"  # >全局上限（默认 200MB——P3-13，独立于声明生效）
    http_status = 413


class SizeMismatchError(CredentialError):
    code = "size_mismatch"  # PUT 字节数少于声明（不完整上传——拒绝）


class HashMismatchError(CredentialError):
    code = "sha256_mismatch"


class UploadNotReadyError(CredentialError):
    code = "upload_not_ready"  # 消费时字节未就位（乱序：③ 先于 ②）


class ObjectRefError(CredentialError):
    code = "invalid_object_ref"  # 对象键越界（白名单根外——纵深防御断言失败）


# ============ 时间契约（P3-10：库内 UTC 秒级 / API 面 UTC ISO Z） ============


def utc_now_ts() -> str:
    """当前 UTC 时间戳（`YYYY-MM-DD HH:MM:SS`——与 CURRENT_TIMESTAMP 同格式）。"""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def to_utc_iso(ts: str) -> str:
    """UTC 秒级存储 → ISO 8601 Z 后缀（API 序列化统一口径）。"""
    return ts.strip().replace(" ", "T") + "Z"


def validate_upload_id(upload_id: str) -> None:
    """不透明凭证 id 形态校验（file_ref 防线第一道——TC-CRED-04）。"""
    if not isinstance(upload_id, str) or not UPLOAD_ID_RE.match(upload_id):
        raise InvalidUploadIdError(
            f"upload_id 只收不透明凭证 id（upl_<ulid>）：{upload_id!r}"
            "——路径/URL/异形一律拒绝（NFR-6 三防线）"
        )


# ============ PUT 流式接收（P3-5：前置校验先行；P3-21：失败补偿清理） ============


class PutSink:
    """PUT 字节的流式落盘：声明校验先行（超限即断，不再收字节）、增量哈希、
    finalize 原子转正；abort 幂等清理 staging（失败路径无孤儿文件）。

    write/precheck 抛出的 CredentialError 由调用方负责 abort（api 层 except 即清）；
    本类不自行捕获——保证「任何异常路径 staging 都被清」由调用面统一兜底。
    """

    def __init__(self, service: "CredentialService", cred: dict) -> None:
        self._service = service
        self._cred = cred
        self._declared = int(cred["size"])
        self._digest = hashlib.sha256()
        self._total = 0
        self._staging = service.staging_dir / f"{cred['id']}.part"
        self._fh = None
        self._done = False

    def precheck(self, content_length: int) -> None:
        """Content-Length 预检（大流量快速失败——不落盘即拒）。"""
        self._check_size(self._total + content_length)

    def _check_size(self, total: int) -> None:
        if total > self._service._settings.upload_max_bytes:
            raise SizeOverLimitError(
                f"PUT 字节数超全局上限（{self._service._settings.upload_max_bytes}"
                f" 字节，P3-13）——已收 {total}"
            )
        if total > self._declared:
            raise SizeExceededError(
                f"PUT 字节数超声明 size（declared={self._declared}，got≥{total}）"
                "——拒绝且不静默截断（附录 A-13）"
            )

    def write(self, chunk: bytes) -> None:
        if self._done or self._fh is None:
            raise RuntimeError("sink not open")
        if not chunk:
            return
        self._check_size(self._total + len(chunk))
        self._fh.write(chunk)
        self._digest.update(chunk)
        self._total += len(chunk)

    def finalize(self) -> dict:
        """收尾：字节数与声明一致 + sha256 复核 → 原子转正 + 状态推进。"""
        assert self._fh is not None
        self._fh.close()
        self._fh = None
        try:
            if self._total != self._declared:
                raise SizeMismatchError(
                    f"PUT 字节数与声明 size 不符（declared={self._declared}，"
                    f"got={self._total}）——不完整上传拒绝"
                )
            actual = self._digest.hexdigest()
            if actual != self._cred["sha256"]:
                raise HashMismatchError(
                    f"sha256 不符（declared={self._cred['sha256'][:12]}…，"
                    f"actual={actual[:12]}…）——拒绝且凭证不标记已用（T12）"
                )
            final_key = f"uploads/{self._cred['id']}"
            final_path = self._service._objects_dir / final_key
            final_path.parent.mkdir(parents=True, exist_ok=True)
            self._staging.replace(final_path)  # 同目录原子转正
            self._done = True
            if not self._service._backend.mark_upload_uploaded(
                self._cred["id"], object_key=final_key
            ):
                raise CredentialConsumedError(
                    f"凭证 {self._cred['id']} 已被消费——PUT 拒绝（单次使用）"
                )
            return {"upload_id": self._cred["id"], "received": self._total,
                    "status": "uploaded"}
        except BaseException:
            self.abort()
            raise

    def abort(self) -> None:
        """失败/取消路径补偿清理（P3-21）——幂等。"""
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
        try:
            self._staging.unlink(missing_ok=True)
        except OSError:
            logger.warning("staging cleanup failed: %s", self._staging)


# ============ 服务 ============


class CredentialService:
    """凭证生命周期编排（issue / put / consume / purge——SQL 经 backend Admin 域）。"""

    def __init__(self, backend, settings: Settings, objects_dir: Path) -> None:
        self._backend = backend
        self._settings = settings
        self._objects_dir = Path(objects_dir)
        self.staging_dir = self._objects_dir / "staging"

    # ---- ① 签发 ----

    def issue(
        self,
        *,
        org_id: str,
        user_id: str,
        service_id: str | None,
        filename: str,
        size: int,
        sha256: str,
        content_type: str,
    ) -> dict:
        """签发凭证（绑定三要素 + expires_at）——返回 {upload_id, upload_url, expires_at}。"""
        if not filename or not isinstance(filename, str):
            raise InvalidRequestError("filename 必填")
        if not isinstance(size, int) or size <= 0:
            raise InvalidRequestError(f"size 必须为正整数：{size!r}")
        if not isinstance(sha256, str) or not _SHA256_RE.match(sha256):
            raise InvalidRequestError("sha256 必须为 64 位小写 hex")
        if size > self._settings.upload_max_bytes:
            raise SizeOverLimitError(
                f"声明 size 超全局上限（{self._settings.upload_max_bytes} 字节，P3-13）"
            )
        upload_id = f"upl_{str(_ulid.ULID()).lower()}"
        expires_at = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.gmtime(time.time() + self._settings.upload_credential_ttl_s),
        )
        self._backend.create_upload_credential(
            upload_id=upload_id, org_id=org_id, user_id=user_id, service_id=service_id,
            filename=filename, size=size, sha256=sha256, content_type=content_type,
            expires_at=expires_at,
        )
        self._backend.append_outbox(
            "upload.credential_issued",
            json.dumps(
                {"upload_id": upload_id, "org_id": org_id, "user_id": user_id,
                 "service_id": service_id, "size": size},
                ensure_ascii=False,
            ),
        )
        # upload_url 形态（M1-3 择型）：同源相对路径——运行时拼服务基址（口径申报）
        return {
            "upload_id": upload_id,
            "upload_url": f"/api/uploads/{upload_id}",
            "expires_at": to_utc_iso(expires_at),
        }

    # ---- ② PUT 字节 ----

    def _require_usable(self, upload_id: str, *, org_id: str, user_id: str,
                        service_id: str | None) -> dict:
        """PUT/消费共用前置：形态 → 在场 → **三一致绑定**（T11）→ 已消费（409）
        → 过期（410）——绑定校验先于状态语义（跨身份请求测不到状态分支）。"""
        validate_upload_id(upload_id)
        cred = self._backend.get_upload_credential(upload_id)
        if cred is None:
            raise CredentialNotFoundError(f"凭证不存在：{upload_id!r}")
        if (cred["org_id"], cred["user_id"], cred["service_id"]) != (
            org_id, user_id, service_id,
        ):
            raise CredentialBindingError(
                f"凭证绑定不匹配（T11：upload_id 绑定 sub+org+服务身份三一致）——"
                f"凭证=({cred['user_id']!r}@{cred['org_id']!r}/{cred['service_id']!r})"
                f" 请求=({user_id!r}@{org_id!r}/{service_id!r})"
            )
        if cred["status"] == "consumed":
            raise CredentialConsumedError(
                f"凭证 {upload_id} 已消费（摄取成功入队即用掉——v1.4 口径）"
            )
        if cred["expires_at"] <= utc_now_ts():
            raise CredentialExpiredError(f"凭证 {upload_id} 已过期（expires_at={cred['expires_at']}）")
        return cred

    def begin_put(self, upload_id: str, *, org_id: str, user_id: str,
                  service_id: str | None) -> PutSink:
        """打开 PUT 接收（校验先行——通过后返回流式 sink）。"""
        cred = self._require_usable(upload_id, org_id=org_id, user_id=user_id,
                                    service_id=service_id)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        sink = PutSink(self, cred)
        sink._fh = open(sink._staging, "wb")
        return sink

    def put_bytes(
        self, upload_id: str, *, org_id: str, user_id: str, service_id: str | None,
        chunks: Iterable[bytes],
    ) -> dict:
        """同步 PUT（分块流式——REST 流式路径与测试共用同一实现）。"""
        sink = self.begin_put(upload_id, org_id=org_id, user_id=user_id,
                              service_id=service_id)
        try:
            for chunk in chunks:
                sink.write(chunk)
            return sink.finalize()
        except BaseException:
            sink.abort()
            raise

    # ---- ③ 消费（MCP upload） ----

    def _resolve_object(self, cred: dict) -> Path:
        """对象路径解析（白名单根 + realpath 规范化 + 前缀校验——NFR-6 纵深）。"""
        key = cred["object_key"]
        if not isinstance(key, str) or not key or ".." in key or key.startswith("/"):
            raise ObjectRefError(f"对象键非法：{key!r}")
        root = self._objects_dir.resolve()
        path = (self._objects_dir / key).resolve()
        if path != root and root not in path.parents:
            raise ObjectRefError(f"对象键越界（白名单根外）：{key!r}")
        return path

    def consume(
        self,
        upload_id: str,
        *,
        org_id: str,
        user_id: str,
        service_id: str | None,
        dataset_id: str,
        dims: dict[str, list[str]],
        create_document: Callable[..., tuple[str, str]],
        title: str | None = None,
        doc_id: str | None = None,
    ) -> dict:
        """消费凭证进摄取：三一致 + 未过期 + 未使用 + 哈希复验 → create_document
        （同一 code path——版本制/ACL 写校验/B-1① 不旁路）→ **摄取成功入队后**
        置已用（create_document 抛错则凭证不动——失败不置、可重传，v1.4 口径）。"""
        cred = self._require_usable(upload_id, org_id=org_id, user_id=user_id,
                                    service_id=service_id)
        if cred["status"] != "uploaded" or not cred["object_key"]:
            raise UploadNotReadyError(
                f"凭证 {upload_id} 字节未就位（status={cred['status']!r}）——"
                "须先 PUT 到 upload_url 再消费（乱序拒绝）"
            )
        obj_path = self._resolve_object(cred)
        if not obj_path.is_file():
            raise UploadNotReadyError(f"凭证对象缺失：{cred['object_key']!r}")
        data = obj_path.read_bytes()
        if len(data) > self._settings.upload_max_bytes:
            raise SizeOverLimitError("凭证对象超全局上限（P3-13）")
        if hashlib.sha256(data).hexdigest() != cred["sha256"]:
            raise HashMismatchError(
                f"消费时哈希复验不符（T12/TOCTOU 防线）——declared={cred['sha256'][:12]}…"
            )

        source_uri = f"agent:{service_id}" if service_id else None  # agent 代传标来源（§6.1）
        doc_id_new, task_id = create_document(
            org_id=org_id,
            dataset_id=dataset_id,
            title=title or cred["filename"] or doc_id or "",
            dims=dims,
            owner_user_id=user_id,
            file_bytes=data,
            mime_type=cred["content_type"],
            filename=cred["filename"],
            doc_id=doc_id,
            source_uri=source_uri,
        )
        # 摄取成功入队 → 置已用（失败路径在上面抛错、凭证不动——可重传）
        if not self._backend.mark_upload_consumed(
            upload_id, doc_id=doc_id_new, task_id=task_id
        ):
            raise CredentialConsumedError(
                f"凭证 {upload_id} 已被消费（并发竞态——单次使用）"
            )
        try:  # 字节已入文档 canonical 对象——凭证暂存对象即清（不留双份）
            obj_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("credential object cleanup failed: %s", obj_path)
        doc = self._backend.get_document(doc_id_new)
        pending_version = doc["pending_version"] if doc else None
        self._backend.append_outbox(
            "upload.consume",
            json.dumps(
                {"upload_id": upload_id, "org_id": org_id, "user_id": user_id,
                 "service_id": service_id, "doc_id": doc_id_new, "task_id": task_id},
                ensure_ascii=False,
            ),
        )
        return {
            "doc_id": doc_id_new,
            "task_id": task_id,
            "status": "queued",
            "pending_version": pending_version,
        }

    # ---- 清理任务（maintenance——design §3；TC-CRED-05） ----

    def purge_expired(self) -> dict:
        """回收过期未消费凭证（含对象目录暂存文件同清——design §6.3）；
        已消费凭证（含过期）保留——凭证与文档/任务关联可追溯（M1-3 A6）。"""
        expired = self._backend.list_expired_upload_credentials(now=utc_now_ts())
        reclaimed: list[str] = []
        for row in expired:
            if row["object_key"]:
                try:
                    (self._objects_dir / row["object_key"]).unlink(missing_ok=True)
                except OSError:
                    logger.warning("reclaim object cleanup failed: %s", row["object_key"])
            self._backend.delete_upload_credential(row["id"])
            reclaimed.append(row["id"])
        # staging 残留（失败 PUT 未及清理的 .part——P3-21 兜底）
        if self.staging_dir.is_dir():
            for part in self.staging_dir.iterdir():
                try:
                    part.unlink()
                except OSError:
                    logger.warning("staging purge failed: %s", part)
        if reclaimed:
            self._backend.append_outbox(
                "upload.reclaim",
                json.dumps({"reclaimed": reclaimed}, ensure_ascii=False),
            )
        return {"reclaimed": len(reclaimed)}
