"""M2.1 承接遗留清偿测试：m1-2 P3-8 fetch window clamp + m1-3 P3-6/P3-10/P3-11。

- P3-8：fetch 窗口宽度钳制 [0, 10]（防超大 window 拉全文档——fetch 语义是
  上下文窗口而非导出）；
- P3-6：同一凭证并发 PUT 的 staging 隔离（每 sink 唯一 .part——互不覆写）；
- P3-10：consume 流式化（哈希流式 + create_document(file_src) 流式拷贝——
  200MB 档不整体读内存）；
- P3-11：并发消费极窗口补偿（mark_consumed 输家 409 且不留已建文档+孤儿任务
  ——worker 自动认领会把孤儿任务真跑成重复文档，故必须补偿删除）。
"""

from __future__ import annotations

import hashlib
import threading

import pytest

from knowledge_lattice.core.docs.credentials import (
    CredentialConsumedError,
    CredentialService,
    PutSink,
)

PAYLOAD = ("<html><body><h1>资源税</h1><p>稀土矿原矿资源税适用税率表。</p></body></html>").encode()
SHA_HEX = hashlib.sha256(PAYLOAD).hexdigest()


def _issue(creds, *, payload: bytes = PAYLOAD) -> str:
    return creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="d.html", size=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
        content_type="text/html",
    )["upload_id"]


# ============ P3-8 fetch window clamp ============


def test_fetch_window_clamped_to_max(matrix) -> None:
    """window 超限钳到 10（前后各 10 → ≤21 块）；负值钳到 0（仅目标块）。"""
    from knowledge_lattice.core.docs.fetch import FETCH_WINDOW_MAX, fetch_chunks
    from helpers import seed_document, seed_doc_dims

    db = matrix
    db.execute(
        "INSERT INTO documents(id, org_id, dataset_id, title, content_hash, mime_type,"
        " parser, active_version, active_status, owner_user_id, raw_object_key)"
        " VALUES('d_fetch', 'org:tax', 'ds:vat_lib', 'fetch窗口', 'sha256:x',"
        " 'text/html', 'docling', 1, 'searchable_full', 'u_owner', 'objects/x')"
    )
    seed_doc_dims(db, "d_fetch", {"region": ["CN"]})
    chunks = [
        {
            "id": f"chk_f{i:02d}", "seq": i,
            "content": f"第{i}段 稀土资源税申报内容。",
            "title_seg": "", "content_seg": f"第{i}段 稀土 资源税", "token_count": 8,
        }
        for i in range(1, 41)
    ]
    backend = db.make_backend()
    backend.insert("d_fetch", 1, chunks)

    result = fetch_chunks(
        backend, user_id="u_full", org_id="org:tax",
        chunk_id="chk_f20", window=999,
    )
    assert len(result["chunks"]) == 2 * FETCH_WINDOW_MAX + 1  # 10+10+1=21（上限）
    seqs = [c["seq"] for c in result["chunks"]]
    assert min(seqs) == 10 and max(seqs) == 30

    result = fetch_chunks(
        backend, user_id="u_full", org_id="org:tax",
        chunk_id="chk_f20", window=-3,
    )
    assert [c["seq"] for c in result["chunks"]] == [20]  # 负值钳 0


# ============ P3-6 并发 PUT staging 隔离 ============


def test_concurrent_puts_isolated_staging(cred_env) -> None:
    """同凭证两个并发 PUT sink：staging 文件互不相同（唯一随机后缀）、互不覆写、
    两个 finalize 均可成功（re-PUT 合法路径——修正重传）。"""
    env = cred_env
    creds = cred_env["creds"]
    upload_id = _issue(creds)

    sink1 = creds.begin_put(
        upload_id, org_id="org:tax", user_id="u_full", service_id="agent-copilot"
    )
    sink2 = creds.begin_put(
        upload_id, org_id="org:tax", user_id="u_full", service_id="agent-copilot"
    )
    assert isinstance(sink1, PutSink) and isinstance(sink2, PutSink)
    assert sink1._staging != sink2._staging  # 各自唯一 .part（P3-6 核心）
    assert sink1._staging.is_file() and sink2._staging.is_file()

    # 交错写（模拟并发流）——两文件各自完整（总量互不串扰）
    sink1.write(PAYLOAD)
    sink2.write(PAYLOAD)
    sink1._fh.flush()
    sink2._fh.flush()
    assert sink1._staging.read_bytes() == PAYLOAD
    assert sink2._staging.read_bytes() == PAYLOAD

    r1 = sink1.finalize()
    r2 = sink2.finalize()  # re-PUT（uploaded→uploaded 放行——修正重传合法）
    assert r1["status"] == "uploaded" and r2["status"] == "uploaded"
    # staging 已清（finalize 转正后无 .part 残留）
    assert not list(creds.staging_dir.glob(f"{upload_id}.*.part"))


def test_abort_leaves_no_staging_residue(cred_env) -> None:
    """失败路径补偿清理（P3-21 语义在新命名下保持）：abort 后无该 sink 的 .part。"""
    creds = cred_env["creds"]
    upload_id = _issue(creds)
    sink = creds.begin_put(
        upload_id, org_id="org:tax", user_id="u_full", service_id="agent-copilot"
    )
    sink.write(PAYLOAD[:10])
    sink.abort()
    assert not list(creds.staging_dir.glob(f"{upload_id}.*.part"))


# ============ P3-10 consume 流式化 ============


def test_consume_streams_without_full_memory_read(cred_env) -> None:
    """consume 走 file_src 流式拷贝：create_document 收到 file_src 而非 file_bytes；
    canonical 对象逐字节等于源；上传对象照旧清理。"""
    env = cred_env
    creds, ingest = env["creds"], env["ingest"]

    upload_id = _issue(creds)
    creds.put_bytes(
        upload_id, org_id="org:tax", user_id="u_full",
        service_id="agent-copilot", chunks=[PAYLOAD],
    )

    seen_kwargs: list[dict] = []
    real_create = ingest.create_document

    def spy_create(**kwargs):
        seen_kwargs.append(kwargs)
        return real_create(**kwargs)

    result = creds.consume(
        upload_id, org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        dataset_id="ds:vat_lib", dims={"region": ["CN"]},
        create_document=spy_create,
    )
    assert result["status"] == "queued"
    # 流式契约：file_src 传入（file_bytes 不传——不整体读内存，P3-10）
    assert seen_kwargs and seen_kwargs[0]["file_src"] is not None
    assert "file_bytes" not in seen_kwargs[0] or seen_kwargs[0]["file_bytes"] is None
    # canonical 对象逐字节保真（流式拷贝正确性）
    doc = env["backend"].get_document(result["doc_id"])
    canonical = env["objects_dir"] / doc["raw_object_key"]
    assert canonical.read_bytes() == PAYLOAD
    assert not (env["objects_dir"] / "uploads" / upload_id).exists()  # 暂存对象已清


# ============ P3-11 并发消费极窗口补偿 ============


def test_consume_race_loser_compensates_orphan_doc(cred_env, monkeypatch) -> None:
    """并发消费极窗口：create_document 已建 doc+task 后 mark_consumed 输家 409——
    补偿删除本次新建文档（任务联动取消）、canonical 对象清理、凭证行保留
    （赢家已消费——单次使用语义不变）。"""
    env = cred_env
    creds, backend, ingest = env["creds"], env["backend"], env["ingest"]

    upload_id = _issue(creds)
    creds.put_bytes(
        upload_id, org_id="org:tax", user_id="u_full",
        service_id="agent-copilot", chunks=[PAYLOAD],
    )

    real_mark = backend.mark_upload_consumed
    state = {"failed_once": False}

    def mark_once_fails(*args, **kwargs):
        if not state["failed_once"]:
            state["failed_once"] = True
            return False  # 模拟并发赢家已消费（输家竞态零行）
        return real_mark(*args, **kwargs)

    monkeypatch.setattr(backend, "mark_upload_consumed", mark_once_fails)

    with pytest.raises(CredentialConsumedError):
        creds.consume(
            upload_id, org_id="org:tax", user_id="u_full", service_id="agent-copilot",
            dataset_id="ds:vat_lib", dims={"region": ["CN"]},
            create_document=ingest.create_document,
        )

    # 补偿：输家新建的文档已删（无孤儿 doc / 无孤儿任务——worker 不会真跑成重复文档）
    docs = env["db"].execute(
        "SELECT id FROM documents WHERE title = 'd.html'"
    ).fetchall()
    assert docs == [], f"输家文档未补偿删除: {docs}"
    orphans = env["db"].execute(
        "SELECT count(*) FROM tasks WHERE status IN ('pending','leased','running')"
    ).fetchone()[0]
    assert orphans == 0
    # 凭证行保留（单次使用语义归赢家——不因输家补偿而删除追溯链）
    row = env["db"].execute(
        "SELECT status FROM uploads WHERE id = ?", (upload_id,)
    ).fetchone()
    assert row[0] == "uploaded"  # 输家失败不置已用（可重传——v1.4 口径）
    # canonical 对象不残留（输家对象清理）
    leftovers = [p for p in env["objects_dir"].glob("*") if p.is_file()]
    assert leftovers == [], f"孤儿对象残留: {leftovers}"
