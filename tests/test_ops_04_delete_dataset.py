"""TC-OPS-04 删除级联与删库流程【集成｜M2】（m2-2 C 组——T19 半句收口）。

断言面：

- ① DELETE 文档级联复核+补断言：chunks / document_dimensions / quality_flags /
  chunk_vectors 级联消失、非终态任务取消（error='cancelled: document deleted'）；
  （M2-S3 起 untag 同事务——**预留注释锚点**：sem_chunk_entities 行随删清挂
  core/docs/ingest.delete_document 编排位，语义轨道段届时补断言）
- ② 对仍有文档的库（dataset）删除 → **RESTRICT 明确报错**（DatasetNotEmptyError
  → 409——非裸外键异常，T19 半句）；权限/org 归属边界（404/403）
- ③ 先删文档后删库 → 成功（§6.2 服务层流程）

90 天 tombstone 物理清理已随 m2-1 交付（TC-VER-08 ✅）——本组仅引用不重做。

双后端参数化（[sqlite]/[pg]）；REST 端点用例为 sqlite（app_env 惯例）。
"""

from __future__ import annotations

import pytest

from knowledge_lattice.store.backend import DatasetNotEmptyError


def _mk_doc_with_rows(matrix, doc_id: str = "d_del") -> str:
    """造一篇带块/维度/向量/flag/在途任务的全要素文档。"""
    from helpers import seed_searchable_doc

    seed_searchable_doc(matrix, doc_id, dims={"region": ["CN"]})
    row = matrix.execute("SELECT rid FROM chunks WHERE doc_id = ?", (doc_id,)).fetchone()
    rid = row[0]
    matrix.insert_vector(rid, "fake-embed:8", [0.1] * 8)
    matrix.execute(
        "INSERT INTO quality_flags(id, chunk_id, doc_id, reason, detail_json, state)"
        " VALUES('qfl_1', (SELECT id FROM chunks WHERE rid = ?), ?,"
        " 'vector_crowding', '{}', 'open')",
        (rid, doc_id),
    )
    matrix.execute(
        "INSERT INTO tasks(id, doc_id, type, status, target_version)"
        " VALUES('tsk_ops04', ?, 'ingest', 'running', 1)",
        (doc_id,),
    )
    return doc_id


# ============ ① DELETE 文档级联复核 + 补断言 ============


def test_delete_document_cascades_and_cancels_tasks(matrix, tmp_path) -> None:
    """DELETE 文档：chunks / document_dimensions / quality_flags / chunk_vectors
    级联消失；非终态任务取消（cancelled: document deleted）；同事务 outbox 审计。
    （M2-S3 untag 预留锚点：sem_chunk_entities 随删清随语义轨道段补断言）"""
    from fake_providers import FakeEmbedder

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.ingest import IngestService

    doc_id = _mk_doc_with_rows(matrix)
    backend = matrix.make_backend()
    service = IngestService(
        backend, FakeEmbedder(dim=8),
        Settings(environment="test", data_dir=tmp_path, embed_dim=8),
        EmbeddingGate(), tmp_path / "objects",
    )
    service.delete_document(org_id="org:tax", doc_id=doc_id, actor_user_id="u_owner")

    for table in ("chunks", "document_dimensions", "quality_flags"):
        assert matrix.execute(
            f"SELECT count(*) FROM {table} WHERE doc_id = ?", (doc_id,)
        ).fetchone()[0] == 0, f"{table} 级联残留"
    assert matrix.execute(
        "SELECT count(*) FROM chunk_vectors WHERE rid"
        " IN (SELECT rid FROM chunks WHERE doc_id = ?)",
        (doc_id,),
    ).fetchone()[0] == 0  # 块已删（FK CASCADE 随行消失——无孤儿向量）
    task = matrix.execute(
        "SELECT status, error FROM tasks WHERE id = 'tsk_ops04'"
    ).fetchone()
    assert task[0] == "failed" and task[1] == "cancelled: document deleted"
    assert matrix.execute(
        "SELECT count(*) FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()[0] == 0
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'document.delete'"
    ).fetchone()[0] == 1


# ============ ②③ 删库 RESTRICT（T19 半句）与「先删文档后删库」 ============


def test_delete_dataset_with_documents_restricted(matrix) -> None:
    """仍有文档的库删除 → DatasetNotEmptyError（RESTRICT 明确语义——非裸
    外键异常）；不存在/跨组织 → KeyError（404）。"""
    backend = matrix.make_backend()
    from helpers import seed_document

    seed_document(matrix, doc_id="d_in_lib", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    with pytest.raises(DatasetNotEmptyError, match="先删文档再删库"):
        backend.delete_dataset("org:tax", "ds:vat_lib")
    # 库与文档都还在（RESTRICT 不动数据）
    assert matrix.execute(
        "SELECT count(*) FROM datasets WHERE id = 'ds:vat_lib'"
    ).fetchone()[0] == 1
    assert matrix.execute(
        "SELECT count(*) FROM documents WHERE id = 'd_in_lib'"
    ).fetchone()[0] == 1
    with pytest.raises(KeyError):
        backend.delete_dataset("org:tax", "ds:no_such")
    with pytest.raises(KeyError):
        backend.delete_dataset("org:gl", "ds:vat_lib")


def test_delete_dataset_succeeds_after_documents_removed(matrix) -> None:
    """先删文档后删库 → 成功（§6.2 服务层流程，TC-OPS-04③）——独立新库
    （不依赖 matrix 既有文档计数）。"""
    from helpers import seed_dataset, seed_document

    backend = matrix.make_backend()
    seed_dataset(matrix, "org:tax", "ds:ops04")
    seed_document(
        matrix, doc_id="d_gone", dataset_id="ds:ops04", owner_user_id="u_owner"
    )
    with pytest.raises(DatasetNotEmptyError):
        backend.delete_dataset("org:tax", "ds:ops04")  # 有文档——RESTRICT
    matrix.execute("DELETE FROM documents WHERE id = 'd_gone'")
    backend.delete_dataset("org:tax", "ds:ops04")      # 清空后成功
    assert matrix.execute(
        "SELECT count(*) FROM datasets WHERE id = 'ds:ops04'"
    ).fetchone()[0] == 0


def test_delete_dataset_api_restrict_and_flow(app_env) -> None:
    """REST 端点（§6.2）：仍有文档 → 409 明确报错（非裸外键 500）；非
    org_admin → 403；先删文档后删库 → 204；二删 404；治理事件入 outbox。"""
    from knowledge_lattice.domain.auth import hash_token

    from helpers import seed_membership, seed_user

    client, conn, static = app_env["client"], app_env["conn"], app_env["static"]
    headers = {"Authorization": f"Bearer {static['u_full']}"}
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", "org:tax", role="org_admin")
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = 'admin_tax'",
        (hash_token("dev-static-admin-tax"),),
    )
    conn.commit()
    admin_headers = {"Authorization": "Bearer dev-static-admin-tax"}
    # 库内有文档（app_env 现场上传 1 篇——u_full owner）
    resp = client.post(
        "/api/orgs/org:tax/documents",
        headers=headers,
        files={"file": ("ops04.html", b"<html><body>ops04</body></html>", "text/html")},
        data={"dataset": "ds:vat_lib", "dims": '{"region": ["CN"]}', "title": "ops04"},
    )
    assert resp.status_code == 202
    doc_id = resp.json()["doc_id"]

    r = client.delete("/api/orgs/org:tax/datasets/ds:vat_lib", headers=admin_headers)
    assert r.status_code == 409
    assert "先删文档再删库" in r.json()["detail"]
    r = client.delete("/api/orgs/org:tax/datasets/ds:vat_lib", headers=headers)
    assert r.status_code == 403  # 非 org_admin（FR-4 操作矩阵）
    # 先删文档（owner=u_full）后删库 → 204
    r = client.delete(f"/api/orgs/org:tax/documents/{doc_id}", headers=headers)
    assert r.status_code == 204
    r = client.delete("/api/orgs/org:tax/datasets/ds:vat_lib", headers=admin_headers)
    assert r.status_code == 204
    r = client.delete("/api/orgs/org:tax/datasets/ds:vat_lib", headers=admin_headers)
    assert r.status_code == 404  # 幂等不复活
    # 删库治理事件入 outbox（M2.4 治理动作全量接入——audit 同事务）
    assert conn.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'dataset.delete'"
    ).fetchone()[0] == 1
