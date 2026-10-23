"""TC-ING-07 阶段幂等续跑【单测｜M0a】。

在 index_fts 完成后中断任务执行（M0a=重启进程内执行器），重跑同任务：
- 从 embed 阶段续跑，index_fts 不重复写块（uq_chunks_docver + 阶段状态判定）；
- 文档状态沿 parsing→chunked→searchable_lexical→searchable_full 前进。
"""

from __future__ import annotations

from fake_providers import FakeEmbedder

HTML_BYTES = (
    "<html><body><h1>增值税申报指南</h1><p>一般纳税人销售自产货物并提供安装服务的，"
    "应分别核算货物的销售额和安装服务的销售额。小规模纳税人适用简易计税方法。</p>"
    "</body></html>"
).encode("utf-8")


def _create(ingest_env):
    svc = ingest_env["make_service"](FakeEmbedder(dim=2560))
    doc_id, task_id = svc.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="增值税申报指南",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML_BYTES, mime_type="text/html", filename="vat.html",
    )
    return svc, doc_id, task_id


def _chunk_ids(conn, doc_id) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT id FROM chunks WHERE doc_id = ? ORDER BY seq", (doc_id,)
        )
    ]


def test_stage_status_progression(ingest_env) -> None:
    """状态沿 parsing→chunked→searchable_lexical→searchable_full 前进（逐阶段观察）。"""
    backend = ingest_env["backend"]
    svc, doc_id, task_id = _create(ingest_env)

    doc = backend.get_document(doc_id)
    assert doc["pending_status"] == "parsing"  # 上传即 parsing（初态）

    svc.run_task(task_id, stop_after="parse")
    doc = backend.get_document(doc_id)
    assert doc["pending_status"] == "parsing"  # parse 阶段进行中仍 parsing

    svc.run_task(task_id, stop_after="chunk")
    doc = backend.get_document(doc_id)
    assert doc["pending_status"] == "chunked"

    svc.run_task(task_id, stop_after="index_fts")
    doc = backend.get_document(doc_id)
    # D20 首次上传切换：active_version 0→1、active_status=searchable_lexical、pending 清空
    assert doc["active_version"] == 1
    assert doc["active_status"] == "searchable_lexical"
    assert doc["pending_version"] is None and doc["pending_status"] is None

    svc.run_task(task_id)
    doc = backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_full"
    assert backend.get_task(task_id)["status"] == "done"


def test_resume_from_embed_after_interrupt(ingest_env) -> None:
    """index_fts 后中断重跑：从 embed 续、不重复写块、不重复解析。"""
    conn = ingest_env["conn"]
    backend = ingest_env["backend"]
    svc, doc_id, task_id = _create(ingest_env)

    svc.run_task(task_id, stop_after="index_fts")  # 中断（进程重启模拟）
    ids_before = _chunk_ids(conn, doc_id)
    assert ids_before  # 块已入库

    # 重跑（同任务）：阶段状态判定 → 跳过 parse/chunk/index_fts
    svc.run_task(task_id)

    assert _chunk_ids(conn, doc_id) == ids_before  # index_fts 不重复写块（块 id 不变）
    assert backend.get_task(task_id)["status"] == "done"
    doc = backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_full"
    embedded = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE doc_id = ? AND embedding IS NOT NULL", (doc_id,)
    ).fetchone()[0]
    assert embedded == len(ids_before)


def test_index_fts_double_insert_idempotent(ingest_env) -> None:
    """index_fts 事务幂等（uq_chunks_docver + 先删后插）：同版本重复 insert 不产生重复块。"""
    conn = ingest_env["conn"]
    backend = ingest_env["backend"]
    svc, doc_id, task_id = _create(ingest_env)
    svc.run_task(task_id, stop_after="chunk")

    # 手工执行两次 index_fts 阶段（不同 chunk id 生成——模拟重跑）
    task = backend.get_task(task_id)
    doc = backend.get_document(task["doc_id"])
    svc._index_fts_stage(doc, svc._chunk_stage(doc, svc._parse_stage(doc)))
    count_1 = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0]
    doc = backend.get_document(task["doc_id"])
    svc._index_fts_stage(doc, svc._chunk_stage(doc, svc._parse_stage(doc)))
    count_2 = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0]
    assert count_1 > 0 and count_1 == count_2  # 幂等：不重复写块

    # uq_chunks_docver 兜底：同 (doc, version, seq) 直接插入被拒
    import sqlite3

    first = conn.execute(
        "SELECT id, seq FROM chunks WHERE doc_id = ? ORDER BY seq LIMIT 1", (doc_id,)
    ).fetchone()
    try:
        conn.execute(
            "INSERT INTO chunks(id, doc_id, seq, version, content, dims_json)"
            " VALUES('chk_dup', ?, ?, 1, 'x', '{}')",
            (doc_id, first[1]),
        )
        raise AssertionError("uq_chunks_docver 应拒绝同 (doc,version,seq)")
    except sqlite3.IntegrityError:
        pass


def test_rerun_done_task_noop(ingest_env) -> None:
    """done 任务重跑 → 幂等 no-op（块/向量不变、任务仍 done）。"""
    conn = ingest_env["conn"]
    backend = ingest_env["backend"]
    svc, doc_id, task_id = _create(ingest_env)
    svc.run_task(task_id)
    ids = _chunk_ids(conn, doc_id)
    svc.run_task(task_id)  # 重跑已完成任务
    assert _chunk_ids(conn, doc_id) == ids
    assert backend.get_task(task_id)["status"] == "done"
