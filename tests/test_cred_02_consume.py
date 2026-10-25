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


def _issue_put(cred_env, *, user_id: str = "u_full", org_id: str = "org:tax",
               service_id: str | None = "agent-copilot", payload: bytes = PAYLOAD) -> str:
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


def _consume(cred_env, upload_id: str, *, user_id: str = "u_full",
             org_id: str = "org:tax", service_id: str | None = "agent-copilot",
             dims: dict[str, list[str]] | None = None, doc_id: str | None = None):
    creds, ingest = cred_env["creds"], cred_env["ingest"]
    return creds.consume(
        upload_id,
        org_id=org_id, user_id=user_id, service_id=service_id,
        dataset_id="ds:vat_lib", dims=dims or {"region": ["CN"]}, doc_id=doc_id,
        create_document=ingest.create_document,
    )


def _row(cred_env, upload_id: str):
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


# ============ R2 修复：P1-1 逐请求成员关系校验（§5.5/FR-4——Committer R1） ============


def test_p1_1_membership_expired_consume_rejected(cred_env) -> None:
    """P1-1：凭证 TTL 内成员关系过期 → consume 403（AclDeniedError）；凭证不置
    已用、无 doc/task 产生；恢复正常成员后消费成功（回归绿）。

    恢复走「删过期行→重加」（trg_membership_no_extend 拒绝 UPDATE 复活——T23；
    删行触发授权级联清理，须补回 u_full 的 region 授权）。"""
    from knowledge_lattice.core.docs.acl import AclDeniedError

    from helpers import dim_id_for, seed_grant, seed_membership, val_id_for

    upload_id = _issue_put(cred_env)
    docs_before = cred_env["db"].execute("SELECT count(*) FROM documents").fetchone()[0]

    cred_env["db"].execute(
        "UPDATE user_org_memberships SET expires_at = ? WHERE user_id = 'u_full'"
        " AND org_id = 'org:tax'",
        ("2020-01-01 00:00:00",),
    )

    with pytest.raises(AclDeniedError) as exc_info:
        _consume(cred_env, upload_id)
    assert "membership" in str(exc_info.value)
    # 凭证仍 uploaded（未消费）、无文档/任务产生
    assert _row(cred_env, upload_id)[0] == "uploaded"
    assert cred_env["db"].execute("SELECT count(*) FROM documents").fetchone()[0] == docs_before

    # 恢复正常成员（删过期行→重加+补回授权）→ 同凭证消费成功
    cred_env["db"].execute(
        "DELETE FROM user_org_memberships WHERE user_id = 'u_full' AND org_id = 'org:tax'"
    )
    seed_membership(cred_env["db"], "u_full", "org:tax")
    for value in ("CN", "OS"):
        seed_grant(
            cred_env["db"], user_id="u_full", dim_id=dim_id_for("org:tax", "region"),
            val_id=val_id_for("org:tax", "region", value),
        )
    result = _consume(cred_env, upload_id)
    assert result["status"] == "queued"
    assert _row(cred_env, upload_id)[0] == "consumed"


def test_p1_1_membership_expired_put_rejected(cred_env) -> None:
    """P1-1（begin_put 同款校验）：成员过期后 PUT 也拒（403 语义——凭证链统一）。"""
    from knowledge_lattice.core.docs.acl import AclDeniedError

    creds = cred_env["creds"]
    issued = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="doc.html", size=len(PAYLOAD), sha256=SHA_HEX, content_type="text/html",
    )
    cred_env["db"].execute(
        "UPDATE user_org_memberships SET expires_at = ? WHERE user_id = 'u_full'"
        " AND org_id = 'org:tax'",
        ("2020-01-01 00:00:00",),
    )
    with pytest.raises(AclDeniedError):
        creds.put_bytes(
            issued["upload_id"], org_id="org:tax", user_id="u_full",
            service_id="agent-copilot", chunks=[PAYLOAD],
        )
    assert _row(cred_env, issued["upload_id"])[0] == "issued"


# ============ R2 修复：P2-1 maintenance staging 清扫不删进行中 .part（Committer R1） ============


def test_p2_1_inflight_sink_survives_purge(cred_env) -> None:
    """① in-flight sink 期间跑 purge → 新鲜 .part 不被清扫、finalize 仍 200。"""
    creds = cred_env["creds"]
    issued = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="doc.html", size=len(PAYLOAD), sha256=SHA_HEX, content_type="text/html",
    )
    sink = creds.begin_put(
        issued["upload_id"], org_id="org:tax", user_id="u_full", service_id="agent-copilot"
    )
    try:
        sink.write(PAYLOAD)
        # PUT 进行中（staging .part 在场）跑清理任务：新鲜 .part 不得被删
        assert creds.purge_expired()["reclaimed"] == 0
        assert creds.staging_dir.joinpath(f"{issued['upload_id']}.part").is_file()
        result = sink.finalize()
    except BaseException:
        sink.abort()
        raise
    assert result["status"] == "uploaded"
    assert _row(cred_env, issued["upload_id"])[0] == "uploaded"


def test_p2_1_finalize_rejects_expired_410_no_orphan(cred_env) -> None:
    """finalize 前重读凭证：PUT 途中过期 → 410 语义拒绝（不先转正后 409）、
    staging 清理、无孤儿 final 对象。"""
    from knowledge_lattice.core.docs.credentials import CredentialExpiredError

    creds = cred_env["creds"]
    issued = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="doc.html", size=len(PAYLOAD), sha256=SHA_HEX, content_type="text/html",
    )
    sink = creds.begin_put(
        issued["upload_id"], org_id="org:tax", user_id="u_full", service_id="agent-copilot"
    )
    sink.write(PAYLOAD)
    # 传输期间凭证过期（长 PUT 跨 expires_at）
    cred_env["db"].execute(
        "UPDATE uploads SET expires_at = '2020-01-01 00:00:00' WHERE id = ?",
        (issued["upload_id"],),
    )
    with pytest.raises(CredentialExpiredError) as exc_info:
        sink.finalize()
    assert exc_info.value.code == "upload_expired"
    # staging 清理 + 无 final 对象（uploads/<id> 不存在）
    assert not creds.staging_dir.joinpath(f"{issued['upload_id']}.part").exists()
    assert not (cred_env["objects_dir"] / "uploads" / issued["upload_id"]).exists()


def test_p2_1_purge_sweeps_only_stale_parts(cred_env) -> None:
    """② 陈旧 .part（mtime 超阈值）被清理；新鲜 .part 保留。"""
    import os
    import time as _time

    creds = cred_env["creds"]
    staging = creds.staging_dir
    staging.mkdir(parents=True, exist_ok=True)
    stale = staging / "upl_stale0000000000000000000000.part"
    fresh = staging / "upl_fresh0000000000000000000000.part"
    stale.write_bytes(b"x")
    fresh.write_bytes(b"y")
    # 阈值 = max(ttl, 2×interval)（cred_env 默认 900s）——陈旧件回拨 mtime
    threshold_s = max(
        creds._settings.upload_credential_ttl_s, 2 * creds._settings.maintenance_interval_s
    )
    old_ts = _time.time() - threshold_s - 60
    os.utime(stale, (old_ts, old_ts))

    creds.purge_expired()

    assert not stale.exists(), "陈旧 .part 应被清扫"
    assert fresh.exists(), "新鲜 .part（进行中 PUT）不得被清扫"


# ============ R2 顺手：P3-15 outbox 事件断言 / P3-3 symlink realpath 分支 ============


def test_p3_15_outbox_events_credential_lifecycle(cred_env) -> None:
    """签发与消费两条 outbox 事件：upload.credential_issued / upload.consume——
    payload 含 service_id / doc_id / task_id（审计面）。"""
    import json as _json

    upload_id = _issue_put(cred_env)
    result = _consume(cred_env, upload_id)

    events = cred_env["db"].execute(
        "SELECT event_type, payload_json FROM audit_outbox"
        " WHERE event_type IN ('upload.credential_issued', 'upload.consume') ORDER BY created_at"
    ).fetchall()
    by_type = {r[0]: _json.loads(r[1]) for r in events}
    assert set(by_type) == {"upload.credential_issued", "upload.consume"}

    issued_ev = by_type["upload.credential_issued"]
    assert issued_ev["upload_id"] == upload_id
    assert issued_ev["service_id"] == "agent-copilot"
    assert issued_ev["user_id"] == "u_full" and issued_ev["org_id"] == "org:tax"

    consume_ev = by_type["upload.consume"]
    assert consume_ev["upload_id"] == upload_id
    assert consume_ev["service_id"] == "agent-copilot"
    assert consume_ev["doc_id"] == result["doc_id"]
    assert consume_ev["task_id"] == result["task_id"]


def test_p3_3_object_ref_symlink_realpath_branch(cred_env) -> None:
    """P3-3：objects/ 内 symlink 指向白名单根外、object_key 无 `..`（`link/evil`）
    ——路径字面在根内、realpath 落根外 → 前缀校验拒绝（真正触达 realpath/前缀分支）。"""
    import os

    from knowledge_lattice.core.docs.credentials import ObjectRefError

    upload_id = _issue_put(cred_env)

    # 白名单根外目录 + 越界文件；objects/link 为指向它的符号链接
    outside = cred_env["objects_dir"].parent / "outside_root"
    outside.mkdir(exist_ok=True)
    evil = outside / "evil.bin"
    evil.write_bytes(b"evil")
    link_dir = cred_env["objects_dir"] / "link"
    if link_dir.is_symlink():
        link_dir.unlink()
    os.symlink(outside, link_dir)

    # 直插 object_key='link/evil'（无 `..`——前置字符串分支放行，落 realpath/前缀分支）
    cred_env["db"].execute(
        "UPDATE uploads SET object_key = 'link/evil' WHERE id = ?", (upload_id,)
    )
    with pytest.raises(ObjectRefError) as exc_info:
        _consume(cred_env, upload_id)
    assert exc_info.value.code == "invalid_object_ref"
