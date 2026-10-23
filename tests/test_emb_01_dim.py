"""TC-EMB-01 嵌入维度校验【单测｜M0a】。

前置：config 钉 dim=2560；Embedder mock 返回 1024 维向量。
预期：写入前校验 len != dim → raise，不写库；库内无残缺向量行；任务 failed 可重试
（无半写状态——TC-EMB-03 拒绝档同款「文档停 searchable_lexical」）。
"""

from __future__ import annotations

import pytest

from fake_providers import FakeEmbedder

from knowledge_lattice.adapters.embedder import EmbeddingDimensionError, validate_dim

HTML_BYTES = (
    "<html><body><h1>留抵退税指南</h1><p>符合条件的一般纳税人可按月申请退还增量留抵税额，"
    "申请前需完成纳税申报和汇总勾选确认。</p></body></html>"
).encode("utf-8")


def test_validate_dim_unit() -> None:
    with pytest.raises(EmbeddingDimensionError):
        validate_dim([[0.0] * 1024], expected=2560)
    validate_dim([[0.0] * 2560], expected=2560)  # 不抛


def _create_doc(ingest_env) -> tuple[str, str]:
    svc = ingest_env["make_service"](FakeEmbedder(dim=2560))
    return svc.create_document(
        org_id="org:tax",
        dataset_id="ds:vat_lib",
        title="留抵退税指南",
        dims={"region": ["CN"]},
        owner_user_id="u_full",
        file_bytes=HTML_BYTES,
        mime_type="text/html",
        filename="guide.html",
    )


def test_embed_dim_mismatch_no_partial_write(ingest_env) -> None:
    """mock 返回 1024 维 → raise、不写库、无残缺向量行、任务 failed 可重试。"""
    backend = ingest_env["backend"]
    doc_id, task_id = _create_doc(ingest_env)

    # 前半管线正常（embed 前阶段不依赖 Embedder）
    svc_ok = ingest_env["make_service"](FakeEmbedder(dim=2560))
    svc_ok.run_task(task_id, stop_after="index_fts")
    doc = backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_lexical"  # D20 已切换（中间态可搜）

    # embed 阶段维度不符（1024 ≠ 2560）——service 用坏 Embedder 续跑
    bad = ingest_env["make_service"](FakeEmbedder(dim=2560, return_dim=1024))
    with pytest.raises(EmbeddingDimensionError):
        bad.run_task(task_id)

    # 任务 failed、带 error；文档停 searchable_lexical + active_error（不 500）
    task = backend.get_task(task_id)
    assert task["status"] == "failed"
    assert "dim mismatch" in task["error"]
    doc = backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_lexical"
    assert doc["active_error"]
    # 库内无残缺向量行（该批全未写入）
    rows = ingest_env["conn"].execute(
        "SELECT COUNT(*) FROM chunks WHERE doc_id = ? AND embedding IS NOT NULL", (doc_id,)
    ).fetchone()[0]
    assert rows == 0

    # 可重试：修复后重跑 → done + searchable_full + 全部块有向量
    svc_retry = ingest_env["make_service"](FakeEmbedder(dim=2560))
    svc_retry.run_task(task_id)
    assert backend.get_task(task_id)["status"] == "done"
    doc = backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_full"
    assert doc["active_error"] is None  # 成功清 error
    total = ingest_env["conn"].execute(
        "SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0]
    embedded = ingest_env["conn"].execute(
        "SELECT COUNT(*) FROM chunks WHERE doc_id = ? AND embedding IS NOT NULL", (doc_id,)
    ).fetchone()[0]
    assert total > 0 and total == embedded
