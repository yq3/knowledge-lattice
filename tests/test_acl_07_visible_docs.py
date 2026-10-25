"""TC-ACL-07 visible_docs 唯一路径回归【单测｜M0a→M0b 双后端】。

M0b-2 实验选定（2026-10-24 拍板 1）：按文档 visible_docs CTE 为唯一路径——
按块 json_each 模板已删（12/12 等价性复核 + sqlite 2.3~4.8× 优势 + PG
MATERIALIZED 6/6 不劣 + 可移植性满分，报告 §2.5）；本文件保留常规断言：
同一用户/文档矩阵下 CTE 路径行为正确（T5/T6/T22 形态）、SQL 形态断言
（MATERIALIZED / document_dimensions / 可见集引用 / 无 IN () / 无 json_each）。
"""

from __future__ import annotations

import pytest

from helpers import NOW_TS, insert_chunk, seed_doc_dims, seed_document

# 覆盖 T5 形态（u_cn：tax_type 零授权→空集单条件）、多值（d_multi）、空值
# （d_empty_region）、全空授权（admin_tax）；u_os/u_cn_vat 为补充交叉
_USERS = ["u_full", "u_cn", "u_cn_vat", "u_os", "admin_tax"]


def _rows(matrix, user_id: str) -> list:
    plan = matrix.compile_acl(user_id, "org:tax", now=NOW_TS)
    return sorted(matrix.execute(*matrix.render_select(plan)))


@pytest.mark.parametrize("user_id", _USERS)
def test_visible_docs_result_set_per_user(matrix, user_id) -> None:
    """CTE 唯一路径的按用户可见集（原双写法等价断言的保留半句——by_doc 常规断言）。"""
    rows = _rows(matrix, user_id)
    assert rows  # 非空结果集（断言有实际内容）
    by_doc = {r[2] for r in rows}
    if user_id == "u_full":
        assert by_doc == {"d_cn", "d_multi", "d_empty_region", "d_os"}
    elif user_id == "u_cn":  # tax_type 零授权 → 只见 tax 无行文档（T5/T22）
        assert by_doc == {"d_multi", "d_empty_region"}
    elif user_id == "u_cn_vat":  # region=[CN]+tax_type=[VAT]
        assert by_doc == {"d_cn", "d_multi", "d_empty_region"}
    elif user_id == "u_os":  # region=[OS]+tax_type 零授权（d_os 无 tax 行 → 放行）
        assert by_doc == {"d_multi", "d_empty_region", "d_os"}
    elif user_id == "admin_tax":  # 全维度零授权 → 只见全空值文档
        assert by_doc == {"d_empty_region"}


def test_visible_docs_sql_shape(matrix) -> None:
    """渲染器附带断言（双方言同构）：CTE 基于 document_dimensions、MATERIALIZED
    加注、组织限定在场、外层 `c.doc_id IN (SELECT doc_id FROM visible_docs)`、
    无 `IN ()`、无 json_each/dims_json（拍板 1 零残留）。"""
    plan = matrix.compile_acl("u_full", "org:tax", now=NOW_TS)
    sql, params = matrix.render_select(plan)
    org_param = ":org" if matrix.is_sqlite else "%(org)s"
    assert sql.startswith(
        "WITH visible_docs(doc_id) AS MATERIALIZED (SELECT d.id FROM documents d"
        f" WHERE d.org_id = {org_param}"
    )
    assert "document_dimensions" in sql
    assert "c.doc_id IN (SELECT doc_id FROM visible_docs)" in sql
    assert "IN ()" not in sql
    assert "json_each" not in sql and "dims_json" not in sql
    assert params["org"] == "org:tax"


def test_version_pair_scenario(matrix) -> None:
    """T6 形态（M0a 版本条件半句——完整切换链随 M1）：d_cn 追加 pending v2 块
    （version=2、active_version 仍 1）→ 只见 v1 块；d_tomb 在用 v2、v1 块
    tombstone=1 → 只见 v2 块。"""
    # d_cn 的 pending v2 块（不重复插 document_dimensions——文档维度按 doc 生效）
    insert_chunk(
        matrix, doc_id="d_cn", seq=1, version=2, chunk_id="chk:d_cn:v2:1",
        content_seg="common sample", title_seg="common sample",
    )
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
        rows = _rows(matrix, user_id)
        chunk_ids = {r[1] for r in rows}
        doc_ids = {r[2] for r in rows}
        # 版本条件：d_tomb 只见在用 v2 块（v1 块 tombstone=1 不可见）
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

    # P0-1 召回层断言（M1-1 R2 补——双后端）：BM25 路只召回在用版本块。
    # pending v2 块与 tombstone v1 块不得出现在 recall_fts 结果——**直接断言
    # 召回层**而非 search() 最终结果（后者有 ACL 兜底断言、会掩盖召回层缺陷——
    # R1 的 PG 臂 117 全绿仍漏掉该缺陷的原因）。
    backend = matrix.make_backend()
    plan = matrix.compile_acl("u_full", "org:tax", now=NOW_TS)
    fts_rows = backend.recall_fts(["common"], plan, top_k=50)
    hit_ids = {r["chunk_id"] for r in fts_rows}
    assert "chk:d_cn:v1:1" in hit_ids and "chk:d_tomb:v2:1" in hit_ids, (
        "在用版本块应正常召回（断言前提）"
    )
    assert "chk:d_cn:v2:1" not in hit_ids, "pending v2 块不得进 BM25 路（P0-1）"
    assert "chk:d_tomb:v1:1" not in hit_ids, "tombstone 块不得进 BM25 路（T9）"
    # 名次协议在场（rank 1 起连续——断言前提自检）
    assert [r["rank"] for r in fts_rows] == list(range(1, len(fts_rows) + 1))
