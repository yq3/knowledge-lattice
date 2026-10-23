"""TC-SCAF-04 DDL 防护触发器全集【单测｜M0a】（sqlite-only）。

① design §4 文档侧全部触发器存在（sem_* 除外、audit append-only 触发器属月库不在主库）；
② 逐个行为断言（全部 ABORT）；`uq_chunks_docver(doc_id, version, seq)` 唯一索引语义。
附带 T23 触发器半句：过期成员关系 UPDATE expires_at 被拒【单测｜M0a】。
"""

from __future__ import annotations

import sqlite3

import pytest
from helpers import (
    FUTURE_TS,
    PAST_TS,
    insert_chunk,
    seed_dataset,
    seed_dim_value,
    seed_dimension,
    seed_document,
    seed_membership,
    seed_org,
    seed_user,
    trigger_names,
)

DOC_SIDE_TRIGGERS = {
    "trg_dimval_immutable",
    "trg_membership_delete_cleanup",
    "trg_membership_no_extend",
    "trg_documents_org_immutable",
    "trg_datasets_org_immutable",
    "trg_dimensions_org_immutable",
    "trg_documents_ds_org_check",
    "trg_documents_ds_immutable",
    "trg_docdims_consistency",
    "chunks_ai",
    "chunks_ad",
    "chunks_au",
}


def test_all_doc_side_triggers_exist(conn: sqlite3.Connection) -> None:
    assert DOC_SIDE_TRIGGERS <= trigger_names(conn)
    # audit append-only 触发器属月库（连接工厂滚动创建），不在主库 schema v1
    assert "audit_no_update" not in trigger_names(conn)
    assert "audit_no_delete" not in trigger_names(conn)


def test_trg_dimval_immutable(conn: sqlite3.Connection) -> None:
    seed_org(conn)
    dim_id = seed_dimension(conn)
    val_id = seed_dim_value(conn, dim_id, value="CN")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("UPDATE dimension_values SET value='ZH' WHERE id=?", (val_id,))
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("UPDATE dimension_values SET dimension_id=? WHERE id=?", (dim_id, val_id))
    # label 可改（显示名，不影响引用）
    conn.execute("UPDATE dimension_values SET label='中国大陆' WHERE id=?", (val_id,))


def _seed_two_orgs(conn: sqlite3.Connection) -> tuple[str, str]:
    seed_org(conn, "org:tax")
    seed_org(conn, "org:gl")
    return "org:tax", "org:gl"


def test_org_immutable_triggers(conn: sqlite3.Connection) -> None:
    tax, gl = _seed_two_orgs(conn)
    ds_id = seed_dataset(conn, org_id=tax)
    seed_user(conn, "u1")
    doc_id = seed_document(conn, org_id=tax, dataset_id=ds_id)
    dim_id = seed_dimension(conn, org_id=tax)

    with pytest.raises(sqlite3.IntegrityError, match="org_id is immutable"):
        conn.execute("UPDATE documents SET org_id=? WHERE id=?", (gl, doc_id))
    with pytest.raises(sqlite3.IntegrityError, match="org_id is immutable"):
        conn.execute("UPDATE datasets SET org_id=? WHERE id=?", (gl, ds_id))
    with pytest.raises(sqlite3.IntegrityError, match="org_id is immutable"):
        conn.execute("UPDATE dimensions SET org_id=? WHERE id=?", (gl, dim_id))


def test_trg_documents_ds_org_check(conn: sqlite3.Connection) -> None:
    tax, gl = _seed_two_orgs(conn)
    tax_ds = seed_dataset(conn, org_id=tax, ds_id="ds:vat")
    seed_user(conn, "u1")
    with pytest.raises(sqlite3.IntegrityError, match="dataset org mismatch"):
        conn.execute(
            "INSERT INTO documents(id, org_id, dataset_id, title, content_hash, mime_type, parser,"
            " owner_user_id, raw_object_key)"
            " VALUES('doc:x', ?, ?, 't', 'sha256:x', 'application/pdf', 'docling', 'u1', 'objects/x')",
            (gl, tax_ds),  # 文档挂 gl、库属 tax → ABORT
        )


def test_trg_documents_ds_immutable(conn: sqlite3.Connection) -> None:
    tax, gl = _seed_two_orgs(conn)
    tax_ds = seed_dataset(conn, org_id=tax, ds_id="ds:vat")
    tax_ds2 = seed_dataset(conn, org_id=tax, ds_id="ds:vat2")
    gl_ds = seed_dataset(conn, org_id=gl, ds_id="ds:gl")
    seed_user(conn, "u1")
    doc_id = seed_document(conn, org_id=tax, dataset_id=tax_ds)

    # 跨组织搬库 → ABORT
    with pytest.raises(sqlite3.IntegrityError, match="dataset move across org"):
        conn.execute("UPDATE documents SET dataset_id=? WHERE id=?", (gl_ds, doc_id))
    # 同组织换库 → 合法
    conn.execute("UPDATE documents SET dataset_id=? WHERE id=?", (tax_ds2, doc_id))


def test_trg_docdims_consistency(conn: sqlite3.Connection) -> None:
    tax, gl = _seed_two_orgs(conn)
    tax_ds = seed_dataset(conn, org_id=tax, ds_id="ds:vat")
    tax_ds_gl = seed_dataset(conn, org_id=gl, ds_id="ds:gl")
    seed_user(conn, "u1")
    doc_tax = seed_document(conn, doc_id="doc:tax", org_id=tax, dataset_id=tax_ds)
    doc_gl = seed_document(conn, doc_id="doc:gl", org_id=gl, dataset_id=tax_ds_gl)

    region = seed_dimension(conn, org_id=tax, key="region")
    region_cn = seed_dim_value(conn, region, value="CN")
    tax_type = seed_dimension(conn, org_id=tax, key="tax_type")
    tax_vat = seed_dim_value(conn, tax_type, value="VAT")
    gl_dim = seed_dimension(conn, org_id=gl, key="gl_kind")
    gl_val = seed_dim_value(conn, gl_dim, value="X")

    # value 与 dimension 不匹配 → ABORT
    with pytest.raises(sqlite3.IntegrityError, match="consistency violation"):
        conn.execute(
            "INSERT INTO document_dimensions(doc_id, dimension_id, value_id) VALUES(?, ?, ?)",
            (doc_tax, region, tax_vat),
        )
    # 维度 org ≠ 文档 org → ABORT
    with pytest.raises(sqlite3.IntegrityError, match="consistency violation"):
        conn.execute(
            "INSERT INTO document_dimensions(doc_id, dimension_id, value_id) VALUES(?, ?, ?)",
            (doc_tax, gl_dim, gl_val),
        )
    # 反向：gl 文档挂 tax 维度 → ABORT
    with pytest.raises(sqlite3.IntegrityError, match="consistency violation"):
        conn.execute(
            "INSERT INTO document_dimensions(doc_id, dimension_id, value_id) VALUES(?, ?, ?)",
            (doc_gl, region, region_cn),
        )
    # 一致行 → 合法
    conn.execute(
        "INSERT INTO document_dimensions(doc_id, dimension_id, value_id) VALUES(?, ?, ?)",
        (doc_tax, region, region_cn),
    )


def test_trg_membership_no_extend(conn: sqlite3.Connection) -> None:
    """T23 触发器半句（M0a 单测）：过期成员关系 UPDATE expires_at 被拒。"""
    tax, gl = _seed_two_orgs(conn)
    seed_user(conn, "u1")
    seed_membership(conn, "u1", tax, expires_at=PAST_TS)  # 已过期（造数：直接写过去时间戳）

    with pytest.raises(sqlite3.IntegrityError, match="expired membership"):
        conn.execute(
            "UPDATE user_org_memberships SET expires_at=? WHERE user_id='u1' AND org_id=?",
            (FUTURE_TS, tax),
        )

    # 未过期行续期合法
    seed_membership(conn, "u1", gl, expires_at=FUTURE_TS)
    conn.execute(
        "UPDATE user_org_memberships SET expires_at=? WHERE user_id='u1' AND org_id=?",
        ("2099-06-01 00:00:00", gl),
    )
    # NULL expires_at 行设置过期时间也合法
    seed_org(conn, "org:x")
    seed_membership(conn, "u1", "org:x")
    conn.execute(
        "UPDATE user_org_memberships SET expires_at=? WHERE user_id='u1' AND org_id='org:x'",
        (FUTURE_TS,),
    )


def test_uq_chunks_docver(conn: sqlite3.Connection) -> None:
    seed_org(conn, "org:tax")
    ds_id = seed_dataset(conn)
    seed_user(conn, "u1")
    doc_id = seed_document(conn)
    insert_chunk(conn, doc_id, seq=1, version=1)
    # 同文档同版本 seq 重复 → 拒
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert_chunk(conn, doc_id, seq=1, version=1, chunk_id="chk:dup")
    # 不同版本同 seq → 合法（含 version——#34 4.4）
    insert_chunk(conn, doc_id, seq=1, version=2, chunk_id="chk:v2s1")


def test_chunks_fts_sync_triggers(conn: sqlite3.Connection) -> None:
    """chunks_ai/ad/au：外部内容表 FTS 同步（机制层；TC-FTS-03 详测）。"""
    seed_org(conn, "org:tax")
    ds_id = seed_dataset(conn)
    seed_user(conn, "u1")
    doc_id = seed_document(conn)

    def fts_count(match: str) -> int:
        return conn.execute(
            "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?", (match,)
        ).fetchone()[0]

    # ai：INSERT 后 FTS 行就位（content 不进 FTS——rerank 专用；_seg 列为分词后文本，空格分隔 token）
    insert_chunk(conn, doc_id, seq=1, version=1, content_seg="进项税额 抵扣凭证")
    assert fts_count('"进项税额"') == 1
    # au：UPDATE 五列之一 → 先 'delete' 旧值再插入新值
    conn.execute(
        "UPDATE chunks SET keywords='留抵退税' WHERE doc_id=? AND seq=1 AND version=1",
        (doc_id,),
    )
    assert fts_count('"留抵退税"') == 1
    # ad：DELETE 后 FTS 行移除
    conn.execute("DELETE FROM chunks WHERE doc_id=? AND seq=1 AND version=1", (doc_id,))
    assert fts_count('"进项税额"') == 0
