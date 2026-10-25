"""TC-CRED-03 MCP upload 三一致校验（服务层·双后端参数化）+ T11/T12 矩阵。

- TC-CRED-03：consume 三一致（sub+org+服务身份）——① 同三要素进摄取；② 换组织；
  ③ 换用户；④ 换服务身份；⑤ 哈希不符（消费时对象复验——TOCTOU 防线）；凭证在
  **摄取成功入队后**置已用（失败不置、可重传——v1.4 与 T12 统一）。
- T11（矩阵形态）：u_multi 持**合法** org:gl 上下文消费 org:tax 凭证 → 绑定专属
  错误码（成员关系与 claim 校验均不成立，拒绝只能来自绑定校验——#42 必修3）。
- T12（矩阵形态）：PUT 超量/哈希不符拒绝且凭证不标记已用；200MB 全局上限独立生效
  （本文件服务层形态；REST 面 413 断言在 test_cred_01）。
- 摄取衔接：consume 走 ingest.create_document 同一 code path（pending 409 / ACL
  写校验 / B-1① 旧值校验不旁路——B 组验收）。
"""

from __future__ import annotations

import hashlib

import pytest

from knowledge_lattice.core.docs.credentials import (
    CredentialBindingError,
    CredentialConsumedError,
    CredentialExpiredError,
    HashMismatchError,
    SizeExceededError,
    SizeOverLimitError,
    UploadNotReadyError,
)

PAYLOAD = ("<html><body><h1>城市维护建设税申报指引</h1><p>城建税随增值税附征。</p></body></html>").encode()
SHA_HEX = hashlib.sha256(PAYLOAD).hexdigest()


def _issue_put(cred_env, *, user_id="u_full", org_id="org:tax", service_id="agent-copilot",
               payload: bytes = PAYLOAD):
    creds = cred_env["creds"]
    issued = creds.issue(
        org_id=org_id, user_id=user_id, service_id=service_id,
        filename="doc.html", size=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
        content_type="text/html",
    )
    creds.put_bytes(
        issued["upload_id"], org_id=org_id, user_id=user_id, service_id=service_id,
        chunks=[payload],
    )
    return issued["upload_id"]


def _consume(cred_env, upload_id, *, user_id="u_full", org_id="org:tax",
             service_id="agent-copilot", dims=None, doc_id=None):
    creds, ingest = cred_env["creds"], cred_env["ingest"]
    return creds.consume(
        upload_id,
        org_id=org_id, user_id=user_id, service_id=service_id,
        dataset_id="ds:vat_lib", dims=dims or {"region": ["CN"]}, doc_id=doc_id,
        create_document=ingest.create_document,
    )


def _row(cred_env, upload_id):
    return cred_env["db"].execute(
        "SELECT status, doc_id, task_id FROM uploads WHERE id = ?", (upload_id,)
    ).fetchone()


# ============ TC-CRED-03 三一致校验 ============


def test_cred_03_same_triple_enters_ingestion(cred_env) -> None:
    """① 同 sub+org+服务身份 → 进摄取（文档+任务入队、凭证置已用并绑定追溯）。"""
    upload_id = _issue_put(cred_env)

    result = _consume(cred_env, upload_id)

    assert result["doc_id"].startswith("doc_")
    assert result["task_id"].startswith("tsk_")
    assert result["status"] == "queued"
    assert result["pending_version"] == 1
    row = _row(cred_env, upload_id)
    assert row[0] == "consumed" and row[1] == result["doc_id"] and row[2] == result["task_id"]
    # 摄取衔接：文档行就位（pending v1——版本制全链入口，M1-2 同 code path）
    doc = cred_env["backend"].get_document(result["doc_id"])
    assert doc["org_id"] == "org:tax" and doc["pending_version"] == 1
    # 消费后凭证对象即清（字节已入文档 canonical 对象——不留双份）
    obj = cred_env["backend"].get_upload_credential(upload_id)
    assert obj["status"] == "consumed"


def test_cred_03_cross_org_rejected_t11(cred_env) -> None:
    """T11①②（换组织）：u_multi 持**合法** org:gl 上下文（token+成员关系均合法）
    消费 org:tax 凭证 → 绑定专属错误码（拒绝只能来自绑定校验本身）。"""
    upload_id = _issue_put(cred_env)  # u_full@org:tax 签发

    with pytest.raises(CredentialBindingError) as exc_info:
        _consume(cred_env, upload_id, user_id="u_multi", org_id="org:gl")

    assert exc_info.value.code == "binding_mismatch"
    assert _row(cred_env, upload_id)[0] == "uploaded"  # 不标记已用（可重传）


def test_cred_03_different_user_rejected_t11(cred_env) -> None:
    """T11②（换用户）：u_cn（org:tax 合法成员）消费 u_full 凭证 → 绑定拒绝。"""
    upload_id = _issue_put(cred_env)

    with pytest.raises(CredentialBindingError):
        _consume(cred_env, upload_id, user_id="u_cn", org_id="org:tax")

    assert _row(cred_env, upload_id)[0] == "uploaded"


def test_cred_03_different_service_identity_rejected_t11(cred_env) -> None:
    """T11③（换服务身份）：同 sub+org、不同服务身份 → 绑定拒绝。"""
    upload_id = _issue_put(cred_env)

    with pytest.raises(CredentialBindingError):
        _consume(cred_env, upload_id, service_id="agent-rogue")

    assert _row(cred_env, upload_id)[0] == "uploaded"


def test_cred_03_hash_mismatch_rejected(cred_env) -> None:
    """⑤ 哈希不符：PUT 后篡改落盘对象 → 消费时复验拒绝（TOCTOU 防线）。"""
    from knowledge_lattice.core.docs.ingest import new_ulid

    upload_id = _issue_put(cred_env)
    obj = cred_env["backend"].get_upload_credential(upload_id)
    path = cred_env["objects_dir"] / obj["object_key"]
    path.write_bytes(b"tampered after put")

    with pytest.raises(HashMismatchError) as exc_info:
        _consume(cred_env, upload_id)
    assert exc_info.value.code == "sha256_mismatch"
    assert _row(cred_env, upload_id)[0] == "uploaded"  # 不置已用


def test_cred_03_expired_rejected(cred_env) -> None:
    upload_id = _issue_put(cred_env)
    cred_env["db"].execute(
        "UPDATE uploads SET expires_at = '2020-01-01 00:00:00' WHERE id = ?", (upload_id,)
    )
    with pytest.raises(CredentialExpiredError):
        _consume(cred_env, upload_id)
    assert _row(cred_env, upload_id)[0] == "uploaded"


def test_cred_03_consumed_rejected(cred_env) -> None:
    upload_id = _issue_put(cred_env)
    _consume(cred_env, upload_id)

    with pytest.raises(CredentialConsumedError):
        _consume(cred_env, upload_id)


def test_cred_03_not_ready_rejected(cred_env) -> None:
    """LLM 先于运行时 PUT 调 upload（乱序）→ 拒绝 upload_not_ready。"""
    creds = cred_env["creds"]
    issued = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="doc.html", size=len(PAYLOAD), sha256=SHA_HEX, content_type="text/html",
    )
    with pytest.raises(UploadNotReadyError):
        _consume(cred_env, issued["upload_id"])
    assert _row(cred_env, issued["upload_id"])[0] == "issued"


def test_cred_03_validation_failure_does_not_consume(cred_env) -> None:
    """摄取校验失败（如取值越权/未知取值）→ 凭证不置已用、修正后可重传（v1.4 口径）。"""
    upload_id = _issue_put(cred_env)

    from knowledge_lattice.core.docs.ingest import (
        UploadPermissionError,
        UploadValidationError,
    )

    # 未知取值 → 400 语义（UploadValidationError——同 multipart code path）
    with pytest.raises(UploadValidationError):
        _consume(cred_env, upload_id, dims={"region": ["XX-UNKNOWN"]})
    assert _row(cred_env, upload_id)[0] == "uploaded"

    # 取值越权 → 403 语义（u_cn 仅 region=[CN]，凭证由 u_full 签发不可用——
    # 越权路径经 u_cn 自签凭证验证：值在授权外 → UploadPermissionError）
    creds = cred_env["creds"]
    issued_cn = creds.issue(
        org_id="org:tax", user_id="u_cn", service_id="agent-copilot",
        filename="doc.html", size=len(PAYLOAD), sha256=SHA_HEX, content_type="text/html",
    )
    creds.put_bytes(
        issued_cn["upload_id"], org_id="org:tax", user_id="u_cn",
        service_id="agent-copilot", chunks=[PAYLOAD],
    )
    with pytest.raises(UploadPermissionError):
        _consume(cred_env, issued_cn["upload_id"], user_id="u_cn", dims={"region": ["OS"]})
    assert _row(cred_env, issued_cn["upload_id"])[0] == "uploaded"

    # 重新用合法参数消费 → 成功（失败未置已用）
    result = _consume(cred_env, upload_id)
    assert result["status"] == "queued"


def test_cred_03_pending_409_same_code_path(cred_env) -> None:
    """B 组：consume 走 M1-2 同一 code path——pending 期间再上传 409（T7），
    且第二张凭证不置已用（可重传）。"""
    upload_id_1 = _issue_put(cred_env)
    result_1 = _consume(cred_env, upload_id_1)  # pending v1（任务未跑）

    upload_id_2 = _issue_put(cred_env)
    from knowledge_lattice.core.docs.ingest import UploadConflictError

    with pytest.raises(UploadConflictError):
        _consume(cred_env, upload_id_2, doc_id=result_1["doc_id"])  # 同文档第二 pending → 409
    assert _row(cred_env, upload_id_2)[0] == "uploaded"  # 冲突不置已用


def test_cred_03_unknown_upload_id_404(cred_env) -> None:
    from knowledge_lattice.core.docs.credentials import CredentialNotFoundError

    with pytest.raises(CredentialNotFoundError):
        _consume(cred_env, "upl_doesnotexist00000000000000")


# ============ T12 矩阵（PUT 超量/哈希不符——服务层形态） ============


def test_t12_put_oversize_rejected_not_marked_used(cred_env) -> None:
    creds = cred_env["creds"]
    issued = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="doc.html", size=len(PAYLOAD), sha256=SHA_HEX, content_type="text/html",
    )
    with pytest.raises(SizeExceededError) as exc_info:
        creds.put_bytes(
            issued["upload_id"], org_id="org:tax", user_id="u_full",
            service_id="agent-copilot", chunks=[PAYLOAD, b"overflow"],
        )
    assert exc_info.value.code == "size_exceeded"
    # 凭证不标记已用：修正重传放行
    creds.put_bytes(
        issued["upload_id"], org_id="org:tax", user_id="u_full",
        service_id="agent-copilot", chunks=[PAYLOAD],
    )
    assert _row(cred_env, issued["upload_id"])[0] == "uploaded"


def test_t12_put_hash_mismatch_rejected_not_marked_used(cred_env) -> None:
    creds = cred_env["creds"]
    issued = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="doc.html", size=len(PAYLOAD), sha256=SHA_HEX, content_type="text/html",
    )
    tampered = bytearray(PAYLOAD)
    tampered[:4] = b"XXXX"  # 等长篡改——隔离 sha256 分支
    with pytest.raises(HashMismatchError):
        creds.put_bytes(
            issued["upload_id"], org_id="org:tax", user_id="u_full",
            service_id="agent-copilot", chunks=[bytes(tampered)],
        )
    assert _row(cred_env, issued["upload_id"])[0] == "issued"


def test_t12_global_cap_independent_413(cred_env) -> None:
    """200MB 全局上限独立生效：**默认上限服务**签发合法声明（2KB）——**小上限
    服务**（模拟上限收紧/存量行）PUT 同凭证 → PUT 面独立拦截（声明本身合法）。"""
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.credentials import CredentialService

    creds = cred_env["creds"]  # 默认 200MB——签发面放行
    payload = b"y" * 2048
    issued = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="big.bin", size=2048, sha256=hashlib.sha256(payload).hexdigest(),
        content_type="application/octet-stream",
    )
    small = CredentialService(  # 上限收紧至 1KB——PUT 面独立判定
        cred_env["backend"], Settings(environment="test", upload_max_bytes=1024),
        cred_env["objects_dir"],
    )
    with pytest.raises(SizeOverLimitError) as exc_info:
        small.put_bytes(
            issued["upload_id"], org_id="org:tax", user_id="u_full",
            service_id="agent-copilot", chunks=[payload],
        )
    assert exc_info.value.code == "size_over_limit"
