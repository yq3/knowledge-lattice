"""M1-4 承接遗留清偿组（组 1/组 3——触及即顺手；每条防回归断言）。

- P3-8 残：finalize mark_upload_uploaded 零行（并发消费竞态）→ 清 final 对象；
- P3-12 残：purge 对象 unlink 经 _resolve_object 纵深（越界键跳过并继续回收）；
- P3-13 残：UPLOAD_ID_RE / _SHA256_RE `\Z` 锚定（尾部换行拒绝）；
- finalize None/consumed 分支直测（m1-3 committer R2 登记）；
- 403 机器码：body.code=membership_denied（T12 一致性边缘）；
- P3-9（m1-2）：create_document DB 失败 → 对象 unlink（无孤儿）；
- P3-12（m1-1）：空 query 早返回 []（403 语义不被绕过）；
- P3-13（m1-1）：耗时日志四段对齐（embed/recall/fuse/rerank——M1-5 数据源）；
- P3-7：切换 UPDATE 加 pending_status='searchable_full'（lexical 态拒绝）。
"""

from __future__ import annotations

import hashlib

import pytest

from helpers import seed_doc_dims, seed_document

PAYLOAD = b"<html><body><h1>x</h1></body></html>"
SHA_HEX = hashlib.sha256(PAYLOAD).hexdigest()


# ============ P3-8 / finalize 分支（凭证链） ============


def _issue_put_started(cred_env):
    """签发并打开 sink、写全量字节（未 finalize——供各竞态分支造数）。"""
    creds = cred_env["creds"]
    issued = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="d.html", size=len(PAYLOAD), sha256=SHA_HEX, content_type="text/html",
    )
    sink = creds.begin_put(
        issued["upload_id"], org_id="org:tax", user_id="u_full",
        service_id="agent-copilot",
    )
    sink.write(PAYLOAD)
    return issued["upload_id"], sink


def test_p3_8_finalize_race_consumed_cleans_final_object(cred_env) -> None:
    """P3-8：finalize 时凭证已被并发消费（mark_upload_uploaded 零行）→ 先清刚
    转正的 final 对象再抛 CredentialConsumedError（无孤儿）。"""
    from knowledge_lattice.core.docs.credentials import CredentialConsumedError

    env = cred_env
    upload_id, sink = _issue_put_started(env)
    # 传输期间被并发消费（状态离开 issued/uploaded）
    env["db"].execute(
        "UPDATE uploads SET status = 'consumed' WHERE id = ?", (upload_id,)
    )
    with pytest.raises(CredentialConsumedError):
        sink.finalize()
    assert not (env["objects_dir"] / "uploads" / upload_id).exists(), (
        "并发消费竞态下转正对象必须清理（防孤儿）"
    )
    assert not env["creds"].staging_dir.joinpath(f"{upload_id}.part").exists()


def test_finalize_deleted_credential_mid_put_410(cred_env) -> None:
    """finalize None 分支：PUT 途中凭证被清理任务删除 → 410 语义（不 409/500）。"""
    from knowledge_lattice.core.docs.credentials import CredentialExpiredError

    env = cred_env
    upload_id, sink = _issue_put_started(env)
    env["db"].execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
    with pytest.raises(CredentialExpiredError) as exc_info:
        sink.finalize()
    assert exc_info.value.code == "upload_expired"
    assert not (env["objects_dir"] / "uploads" / upload_id).exists()


def test_finalize_status_flipped_consumed_409(cred_env) -> None:
    """finalize consumed 分支：途中状态被置 consumed（重读命中）→ 409 拒绝。"""
    from knowledge_lattice.core.docs.credentials import CredentialConsumedError

    env = cred_env
    upload_id, sink = _issue_put_started(env)
    env["db"].execute(
        "UPDATE uploads SET status = 'consumed' WHERE id = ?", (upload_id,)
    )
    with pytest.raises(CredentialConsumedError) as exc_info:
        sink.finalize()
    assert exc_info.value.code == "upload_consumed"
    assert not env["creds"].staging_dir.joinpath(f"{upload_id}.part").exists()


def test_p3_12_purge_skips_out_of_root_object_key(cred_env) -> None:
    """P3-12：过期凭证 object_key 越界（'..'）→ realpath/前缀纵深拒绝（跳过
    unlink、不炸任务）、凭证行照常回收。"""
    env = cred_env
    upload_id, _sink = _issue_put_started(env)
    env["db"].execute(
        "UPDATE uploads SET object_key = 'uploads/../evil.bin',"
        " expires_at = '2020-01-01 00:00:00' WHERE id = ?",
        (upload_id,),
    )
    env["db"].commit()
    result = env["creds"].purge_expired()  # 不 raise——纵深跳过
    assert result["reclaimed"] == 1
    assert env["db"].execute(
        "SELECT count(*) FROM uploads WHERE id = ?", (upload_id,)
    ).fetchone()[0] == 0


def test_p3_13_z_anchor_rejects_trailing_newline() -> None:
    """P3-13：正则 \Z... 锚定——`$` 会放过尾部换行；两正则拒绝之。"""
    from knowledge_lattice.core.docs.credentials import (
        UPLOAD_ID_RE,
        _SHA256_RE,
        InvalidRequestError,
        InvalidUploadIdError,
        validate_upload_id,
    )

    good = "upl_" + "a" * 26
    assert UPLOAD_ID_RE.match(good)
    assert not UPLOAD_ID_RE.match(good + "\n")
    assert not UPLOAD_ID_RE.match("upl_" + "A" * 26)  # 大写拒绝
    assert _SHA256_RE.match("a" * 64)
    assert not _SHA256_RE.match("a" * 64 + "\n")

    with pytest.raises(InvalidUploadIdError):
        validate_upload_id(good + "\n")

    creds_issue = None  # sha256 换行经签发入口拒（InvalidRequestError）
    from knowledge_lattice.core.docs.credentials import CredentialService

    class _B:  # 最小 backend 桩——签发在写库前校验
        def append_outbox(self, *a, **k): ...
        def create_upload_credential(self, **k): ...
    from knowledge_lattice.config import Settings

    svc = CredentialService(_B(), Settings(environment="test"), "/tmp/x")
    with pytest.raises(InvalidRequestError):
        svc.issue(
            org_id="o", user_id="u", service_id=None, filename="f", size=1,
            sha256="a" * 64 + "\n", content_type="text/plain",
        )


# ============ 403 机器码（body.code=membership_denied——T12 一致性） ============


def test_403_membership_denied_machine_code(app_env) -> None:
    """REST 403 带 body.code=membership_denied；默认码 acl_denied。"""
    from knowledge_lattice.core.docs.acl import AclDeniedError

    client = app_env["client"]
    # 非成员用户（u_cn 是 org:tax 成员——造非成员：签发无成员关系的用户 token）
    token = app_env["jwt"]("u_cn")  # u_cn 有成员关系——用不存在成员关系的 org
    resp = client.post(
        "/api/search", json={"query": "x"},
        headers={"Authorization": f"Bearer {token}", "X-Org-Id": "org:gl"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "membership_denied", resp.text

    # 默认码（非成员关系类拒绝）
    err = AclDeniedError("other denial")
    assert err.code == "acl_denied"


def test_403_message_no_bound_values_echo(cred_env) -> None:
    """403/绑定文案泛化：CredentialBindingError 不回显凭证绑定侧明文取值
    （m1-2 Tester R2 观察③——持 upload_id 者不得枚举绑定身份）。"""
    from knowledge_lattice.core.docs.credentials import CredentialBindingError

    creds = cred_env["creds"]
    issued = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="d.html", size=len(PAYLOAD), sha256=SHA_HEX, content_type="text/html",
    )
    with pytest.raises(CredentialBindingError) as exc_info:
        creds.begin_put(
            issued["upload_id"], org_id="org:tax", user_id="u_full",
            service_id="other-agent",  # 服务身份不符
        )
    msg = str(exc_info.value)
    assert "u_full@" not in msg and "agent-copilot" not in msg, (
        f"绑定错误文案不得回显凭证侧取值：{msg}"
    )


# ============ P3-9（m1-2）：create_document 失败无孤儿对象 ============


def test_p3_9_create_document_db_failure_cleans_object(ingest_env, monkeypatch) -> None:
    """对象已落盘、backend.create_document 抛错 → unlink 补偿（无孤儿）。"""
    from fake_providers import FakeEmbedder

    env = ingest_env
    svc = env["make_service"](FakeEmbedder(dim=8))

    def _boom(**kwargs):
        raise RuntimeError("db write failed (simulated)")

    monkeypatch.setattr(env["backend"], "create_document", _boom)
    with pytest.raises(RuntimeError, match="db write failed"):
        svc.create_document(
            org_id="org:tax", dataset_id="ds:vat_lib", title="t",
            dims={"region": ["CN"]}, owner_user_id="u_full",
            file_bytes=b"x", mime_type="text/plain", filename="orphan.txt",
        )
    leftovers = [
        p for p in env["objects_dir"].iterdir() if p.is_file()
    ] if env["objects_dir"].exists() else []
    assert leftovers == [], f"DB 失败后不得留孤儿对象：{leftovers}"


# ============ P3-12 / P3-13（m1-1）：空 query 口径 + 耗时四段 ============


def test_p3_12_blank_query_early_return(ret_stack, caplog) -> None:
    """空/全空白 query → 早返回 []（不触碰检索路）；非成员不被空查询绕过（403）。"""
    import logging

    from knowledge_lattice.core.docs.acl import AclDeniedError
    from knowledge_lattice.core.docs.retrieve import search

    with caplog.at_level(logging.INFO):
        payload = search(
            ret_stack["backend"], ret_stack["settings"],
            user_id="u_full", org_id="org:tax", query="   ", top_k=5,
            gate=None, embedder=ret_stack["embedder"],
        )
    assert payload == {"results": [], "notice": {"vector_pending": False, "degraded": []}}
    assert any("empty query" in r.message for r in caplog.records)

    # 403 语义保留：非成员（u_cn 对 org:gl 无成员关系）空查询仍拒绝
    with pytest.raises(AclDeniedError):
        search(
            ret_stack["backend"], ret_stack["settings"],
            user_id="u_cn", org_id="org:gl", query="  ", top_k=5,
        )


def test_p3_13_timing_log_four_segments(ret_stack, caplog) -> None:
    """耗时日志四段对齐：embed/recall/fuse/rerank（design §3——fts 段并入 recall
    口径不再出现）。"""
    import logging

    from knowledge_lattice.core.docs.retrieve import search

    with caplog.at_level(logging.INFO):
        search(
            ret_stack["backend"], ret_stack["settings"],
            user_id="u_full", org_id="org:tax", query="common sample", top_k=5,
            gate=None, embedder=ret_stack["embedder"],
        )
    timing = [r.message for r in caplog.records if "search timing" in r.message]
    assert timing, "应输出 search timing 日志"
    line = timing[0]
    for seg in ("embed=", "recall=", "fuse=", "rerank="):
        assert seg in line, f"四段缺失 {seg}: {line}"
    assert "fts=" not in line, "fts 段已并入 recall（四段口径）"


# ============ P3-7：切换 UPDATE 加 pending_status 守卫 ============


def test_p3_7_switch_rejected_before_searchable_full(ver_env) -> None:
    """pending 在 searchable_lexical 态直接 switch → VersionConflictError（加固：
    只允许 searchable_full 时点切换——D20；真并发用例随 M2）。"""
    from knowledge_lattice.store.backend import VersionConflictError

    env = ver_env
    conn = env["db"]
    seed_document(conn, doc_id="d_p37", dataset_id="ds:vat_lib", owner_user_id="u_full")
    seed_doc_dims(conn, "d_p37", {"region": ["CN"]})
    conn.execute(
        "INSERT INTO chunks(id, doc_id, seq, version, content)"
        " VALUES('chk:p37', 'd_p37', 1, 2, 'x')"
    )
    conn.execute(
        "UPDATE documents SET pending_version = 2, pending_status = 'searchable_lexical'"
        " WHERE id = 'd_p37'"
    )
    conn.commit()
    with pytest.raises(VersionConflictError, match="searchable_full"):
        env["backend"].switch_active_version("d_p37", expected_pending=2)
    # 前置 SELECT 守卫同样拦截（pending 未达 full——无部分写入）
    assert env["backend"].get_document("d_p37")["active_version"] == 0
