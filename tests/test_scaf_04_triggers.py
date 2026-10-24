"""TC-SCAF-04 DDL 防护触发器全集【单测｜M0a→M0b 双后端】。

① design §4 文档侧全部触发器存在（双方言各自全集：sqlite 12 个——含 chunks_ai/
ad/au；PG 9 个 plpgsql 等价物——ai/ad/au 由 tsvector 五列 GENERATED 取代；
sem_* 除外、audit append-only 触发器属月库/分区表不在主库 schema v1——sqlite
臂断言不在主库，pg 臂断言由连接工厂滚动创建〔等价物在场〕）；
② 逐个行为断言（全部 ABORT——sqlite=IntegrityError / pg=psycopg RaiseException，
消息逐字同源）；`uq_chunks_docver(doc_id, version, seq)` 唯一索引语义。
附带 T23 触发器半句：过期成员关系 UPDATE expires_at 被拒。
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


def test_all_doc_side_triggers_exist(backend) -> None:
    assert backend.doc_side_trigger_names() <= backend.trigger_names()
    if backend.is_sqlite:
        # audit append-only 触发器属月库（连接工厂滚动创建），不在主库 schema v1
        assert "audit_no_update" not in backend.trigger_names()
        assert "audit_no_delete" not in backend.trigger_names()
    else:
        # PG 等价物：audit_no_update/delete 由连接工厂在 audit_events 分区父表上滚动创建
        assert {"audit_no_update", "audit_no_delete"} <= backend.trigger_names()


def test_trg_dimval_immutable(backend) -> None:
    seed_org(backend)
    dim1 = seed_dimension(backend, key="region")
    dim2 = seed_dimension(backend, key="tax_type")
    val_id = seed_dim_value(backend, dim1, value="CN")
    with pytest.raises(backend.integrity_error, match="immutable"):
        backend.execute("UPDATE dimension_values SET value='ZH' WHERE id=?", (val_id,))
    # 真跨维度搬移（P3-10）：把 region 的值搬到 tax_type 下 → ABORT
    with pytest.raises(backend.integrity_error, match="immutable"):
        backend.execute(
            "UPDATE dimension_values SET dimension_id=? WHERE id=?", (dim2, val_id)
        )
    # label 可改（显示名，不影响引用）
    backend.execute("UPDATE dimension_values SET label='中国大陆' WHERE id=?", (val_id,))


def _seed_two_orgs(db) -> tuple[str, str]:
    seed_org(db, "org:tax")
    seed_org(db, "org:gl")
    return "org:tax", "org:gl"


def test_org_immutable_triggers(backend) -> None:
    tax, gl = _seed_two_orgs(backend)
    ds_id = seed_dataset(backend, org_id=tax)
    seed_user(backend, "u1")
    doc_id = seed_document(backend, org_id=tax, dataset_id=ds_id)
    dim_id = seed_dimension(backend, org_id=tax)

    with pytest.raises(backend.integrity_error, match="org_id is immutable"):
        backend.execute("UPDATE documents SET org_id=? WHERE id=?", (gl, doc_id))
    with pytest.raises(backend.integrity_error, match="org_id is immutable"):
        backend.execute("UPDATE datasets SET org_id=? WHERE id=?", (gl, ds_id))
    with pytest.raises(backend.integrity_error, match="org_id is immutable"):
        backend.execute("UPDATE dimensions SET org_id=? WHERE id=?", (gl, dim_id))


def test_trg_documents_ds_org_check(backend) -> None:
    tax, gl = _seed_two_orgs(backend)
    tax_ds = seed_dataset(backend, org_id=tax, ds_id="ds:vat")
    seed_user(backend, "u1")
    with pytest.raises(backend.integrity_error, match="dataset org mismatch"):
        backend.execute(
            "INSERT INTO documents(id, org_id, dataset_id, title, content_hash, mime_type,"
            " parser, owner_user_id, raw_object_key)"
            " VALUES('doc:x', ?, ?, 't', 'sha256:x', 'application/pdf', 'docling', 'u1', 'objects/x')",
            (gl, tax_ds),  # 文档挂 gl、库属 tax → ABORT
        )


def test_trg_documents_ds_immutable(backend) -> None:
    tax, gl = _seed_two_orgs(backend)
    tax_ds = seed_dataset(backend, org_id=tax, ds_id="ds:vat")
    tax_ds2 = seed_dataset(backend, org_id=tax, ds_id="ds:vat2")
    gl_ds = seed_dataset(backend, org_id=gl, ds_id="ds:gl")
    seed_user(backend, "u1")
    doc_id = seed_document(backend, org_id=tax, dataset_id=tax_ds)

    # 跨组织搬库 → ABORT
    with pytest.raises(backend.integrity_error, match="dataset move across org"):
        backend.execute("UPDATE documents SET dataset_id=? WHERE id=?", (gl_ds, doc_id))
    # 同组织换库 → 合法
    backend.execute("UPDATE documents SET dataset_id=? WHERE id=?", (tax_ds2, doc_id))


def test_trg_docdims_consistency(backend) -> None:
    tax, gl = _seed_two_orgs(backend)
    tax_ds = seed_dataset(backend, org_id=tax, ds_id="ds:vat")
    tax_ds_gl = seed_dataset(backend, org_id=gl, ds_id="ds:gl")
    seed_user(backend, "u1")
    doc_tax = seed_document(backend, doc_id="doc:tax", org_id=tax, dataset_id=tax_ds)
    doc_gl = seed_document(backend, doc_id="doc:gl", org_id=gl, dataset_id=tax_ds_gl)

    region = seed_dimension(backend, org_id=tax, key="region")
    region_cn = seed_dim_value(backend, region, value="CN")
    tax_type = seed_dimension(backend, org_id=tax, key="tax_type")
    tax_vat = seed_dim_value(backend, tax_type, value="VAT")
    gl_dim = seed_dimension(backend, org_id=gl, key="gl_kind")
    gl_val = seed_dim_value(backend, gl_dim, value="X")

    # value 与 dimension 不匹配 → ABORT
    with pytest.raises(backend.integrity_error, match="consistency violation"):
        backend.execute(
            "INSERT INTO document_dimensions(doc_id, dimension_id, value_id) VALUES(?, ?, ?)",
            (doc_tax, region, tax_vat),
        )
    # 维度 org ≠ 文档 org → ABORT
    with pytest.raises(backend.integrity_error, match="consistency violation"):
        backend.execute(
            "INSERT INTO document_dimensions(doc_id, dimension_id, value_id) VALUES(?, ?, ?)",
            (doc_tax, gl_dim, gl_val),
        )
    # 反向：gl 文档挂 tax 维度 → ABORT
    with pytest.raises(backend.integrity_error, match="consistency violation"):
        backend.execute(
            "INSERT INTO document_dimensions(doc_id, dimension_id, value_id) VALUES(?, ?, ?)",
            (doc_gl, region, region_cn),
        )
    # 一致行 → 合法
    backend.execute(
        "INSERT INTO document_dimensions(doc_id, dimension_id, value_id) VALUES(?, ?, ?)",
        (doc_tax, region, region_cn),
    )


def test_trg_membership_no_extend(backend) -> None:
    """T23 触发器半句（M0a 单测）：过期成员关系 UPDATE expires_at 被拒。"""
    tax, gl = _seed_two_orgs(backend)
    seed_user(backend, "u1")
    seed_membership(backend, "u1", tax, expires_at=PAST_TS)  # 已过期（造数：直接写过去时间戳）

    with pytest.raises(backend.integrity_error, match="expired membership"):
        backend.execute(
            "UPDATE user_org_memberships SET expires_at=? WHERE user_id='u1' AND org_id=?",
            (FUTURE_TS, tax),
        )

    # 未过期行续期合法
    seed_membership(backend, "u1", gl, expires_at=FUTURE_TS)
    backend.execute(
        "UPDATE user_org_memberships SET expires_at=? WHERE user_id='u1' AND org_id=?",
        ("2099-06-01 00:00:00", gl),
    )
    # NULL expires_at 行设置过期时间也合法
    seed_org(backend, "org:x")
    seed_membership(backend, "u1", "org:x")
    backend.execute(
        "UPDATE user_org_memberships SET expires_at=? WHERE user_id='u1' AND org_id='org:x'",
        (FUTURE_TS,),
    )


def test_uq_chunks_docver(backend) -> None:
    seed_org(backend, "org:tax")
    ds_id = seed_dataset(backend)
    seed_user(backend, "u1")
    doc_id = seed_document(backend)
    insert_chunk(backend, doc_id, seq=1, version=1)
    # 同文档同版本 seq 重复 → 拒
    with pytest.raises(backend.integrity_error, match="UNIQUE|unique constraint"):
        insert_chunk(backend, doc_id, seq=1, version=1, chunk_id="chk:dup")
    # 不同版本同 seq → 合法（含 version——#34 4.4）
    insert_chunk(backend, doc_id, seq=1, version=2, chunk_id="chk:v2s1")


def test_chunk_fts_columns_sync(backend) -> None:
    """chunks_ai/ad/au（sqlite）↔ tsvector 五列 GENERATED（pg）：索引随行同步——
    插入即就位、更新即重算（旧词归零）、删除即移除（机制层；TC-FTS-03 详测 sqlite）。"""
    seed_org(backend, "org:tax")
    ds_id = seed_dataset(backend)
    seed_user(backend, "u1")
    doc_id = seed_document(backend)

    insert_chunk(
        backend, doc_id, seq=1, version=1, content_seg="进项税额 抵扣凭证", keywords="旧词"
    )
    assert backend.fts_word_count("进项税额") == 1
    assert backend.fts_word_count("旧词") == 1
    # 更新五列之一 → 旧词索引项必须归零（au 先 delete 再 insert / GENERATED 重算）
    backend.execute(
        "UPDATE chunks SET keywords='留抵退税' WHERE doc_id=? AND seq=1 AND version=1",
        (doc_id,),
    )
    assert backend.fts_word_count("留抵退税") == 1
    assert backend.fts_word_count("旧词") == 0
    # 删除后索引项移除
    backend.execute(
        "DELETE FROM chunks WHERE doc_id=? AND seq=1 AND version=1", (doc_id,)
    )
    assert backend.fts_word_count("进项税额") == 0


def test_version_switch_clear_all_five_columns_zero_hits(backend) -> None:
    """R2 P3-2：版本切换「五列全清 → 索引重算 → 零命中」完整形态（design §5.3
    切换事务清五列；sqlite=au 触发器重写 FTS 行 / pg=GENERATED 重算为空 tsvector）
    ——双臂同一断言（sqlite 侧 TC-FTS-03 形态在 PG 臂补齐）。"""
    seed_org(backend, "org:tax")
    ds_id = seed_dataset(backend)
    seed_user(backend, "u1")
    doc_id = seed_document(backend)
    insert_chunk(
        backend, doc_id, seq=1, version=1,
        content_seg="留抵 退税 申请", title_seg="留抵退税 指南",
        keywords="留抵退税", llm_keywords="退税", tags="税",
    )
    # 五列均有词 → 全部可命中
    for word in ("留抵", "留抵退税", "退税", "税"):
        assert backend.fts_word_count(word) >= 1, word
    # 版本切换语义：旧版本块五列全清（tombstone=1 + embedding/五列置空）
    backend.execute(
        "UPDATE chunks SET tombstone = 1, embedding = NULL,"
        " title_seg = '', content_seg = '', keywords = '', llm_keywords = '', tags = ''"
        " WHERE doc_id = ? AND version = 1",
        (doc_id,),
    )
    # 五列全清后：任一列词零命中（sqlite=FTS 行被 au 重写为空 / pg=GENERATED 空 tsvector）
    for word in ("留抵", "留抵退税", "退税", "税"):
        assert backend.fts_word_count(word) == 0, word


# ============ sqlite-only：主库触发器清单（sqlite_master 形态断言） ============


def test_sqlite_doc_side_triggers_enumerated(conn: sqlite3.Connection) -> None:
    """sqlite 臂全集点名（12 个——PG 9 个 + ai/ad/au；与 dbwrap 清单一致的双保险）。"""
    names = trigger_names(conn)
    assert {
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
    } <= names
