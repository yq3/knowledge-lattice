"""TC-ACL-07 visible_docs 备选逐字等价【单测｜M0a→M0b 后按结论保留】。

对同一用户/文档矩阵，「按块 json_each 模板」与「按文档 visible_docs CTE（基于
document_dimensions）」结果集完全一致（T5/T6/T22 两写法都测——#34 必修 3）；M0b
实验选定后保留其一为常规断言、另一删除（design §5.1 性能注）。
"""

from __future__ import annotations

import pytest

from helpers import NOW_TS, insert_chunk, seed_doc_dims, seed_document

from knowledge_lattice.core.docs.acl import compile_acl
from knowledge_lattice.store.sqlite.acl_render import (
    render_select,
    render_visible_docs_select,
)
from knowledge_lattice.store.sqlite.backend import SqliteBackend

# 覆盖 T5 形态（u_cn：tax_type 零授权→空集单条件）、多值（d_multi）、空值
# （d_empty_region）、全空授权（admin_tax）；u_os/u_cn_vat 为补充交叉
_USERS = ["u_full", "u_cn", "u_cn_vat", "u_os", "admin_tax"]


def _rows_both_writings(matrix, user_id: str) -> tuple[list, list]:
    plan = compile_acl(SqliteBackend(matrix), user_id, "org:tax", now=NOW_TS)
    by_chunk = sorted(matrix.execute(*render_select(plan)))
    by_doc = sorted(matrix.execute(*render_visible_docs_select(plan)))
    return by_chunk, by_doc


@pytest.mark.parametrize("user_id", _USERS)
def test_same_result_set_both_writings(matrix, user_id) -> None:
    """同一矩阵两写法结果集逐字等价（行级：rid/chunk_id/doc_id 全同）。"""
    by_chunk, by_doc = _rows_both_writings(matrix, user_id)
    assert by_chunk == by_doc
    assert by_chunk  # 非空结果集（等价性有实际内容）


def test_visible_docs_sql_shape(matrix) -> None:
    """渲染器附带断言：CTE 基于 document_dimensions、组织限定在场、无 `IN ()`。"""
    plan = compile_acl(SqliteBackend(matrix), "u_full", "org:tax", now=NOW_TS)
    sql, params = render_visible_docs_select(plan)
    assert sql.startswith(
        "WITH visible_docs(doc_id) AS (SELECT d.id FROM documents d WHERE d.org_id = :org"
    )
    assert "document_dimensions" in sql
    assert "c.doc_id IN (SELECT doc_id FROM visible_docs)" in sql
    assert "IN ()" not in sql
    assert params["org"] == "org:tax"


def test_version_pair_scenario_both_writings(matrix) -> None:
    """T6 形态（M0a 版本条件半句——完整切换链随 M1）：d_cn 追加 pending v2 块
    （version=2、active_version 仍 1）→ 两写法都只见 v1 块；d_tomb 在用 v2、
    v1 块 tombstone=1 → 两写法都只见 v2 块。"""
    # d_cn 的 pending v2 块（dims_json 投影按 doc 全量重投影——不重复插 document_dimensions）
    insert_chunk(
        matrix, doc_id="d_cn", seq=1, version=2, chunk_id="chk:d_cn:v2:1",
        content_seg="common sample", title_seg="common sample",
    )
    seed_doc_dims(matrix, "d_cn", {})  # 空合并=按 document_dimensions 全量重投影
    # d_tomb：v1 块 tombstone=1（region=[CN]）、在用 v2 块（region 空值）
    seed_document(
        matrix, doc_id="d_tomb", dataset_id="ds:vat_lib", owner_user_id="u_owner"
    )
    insert_chunk(
        matrix, doc_id="d_tomb", seq=1, version=1, chunk_id="chk:d_tomb:v1:1",
        content_seg="common sample", title_seg="common sample", tombstone=1,
    )
    insert_chunk(
        matrix, doc_id="d_tomb", seq=1, version=2, chunk_id="chk:d_tomb:v2:1",
        content_seg="common sample", title_seg="common sample",
    )
    matrix.execute("UPDATE documents SET active_version = 2 WHERE id = 'd_tomb'")
    seed_doc_dims(matrix, "d_tomb", {"region": ["CN"]})

    expected_u_full = {"d_cn", "d_multi", "d_empty_region", "d_os", "d_tomb"}
    for user_id in ("u_full", "u_cn"):
        by_chunk, by_doc = _rows_both_writings(matrix, user_id)
        chunk_ids = {r[1] for r in by_chunk}
        doc_ids = {r[2] for r in by_chunk}
        # 版本条件（两写法一致）：d_tomb 只见在用 v2 块（v1 块 tombstone=1 不可见）
        assert "chk:d_tomb:v2:1" in chunk_ids and "chk:d_tomb:v1:1" not in chunk_ids
        if user_id == "u_full":
            # u_full（region=[CN,OS]+tax_type=[VAT]）：d_cn 只见在用 v1 块
            #（pending v2 块不生效——P0-2.1），可见集含全部基线文档
            assert "chk:d_cn:v1:1" in chunk_ids and "chk:d_cn:v2:1" not in chunk_ids
            assert doc_ids == expected_u_full
        else:
            # u_cn（tax_type 零授权）：d_cn 整体不可见（T22 维度过滤照常叠加）
            assert "d_cn" not in doc_ids
            assert not any(cid.startswith("chk:d_cn") for cid in chunk_ids)
        assert by_chunk == by_doc
