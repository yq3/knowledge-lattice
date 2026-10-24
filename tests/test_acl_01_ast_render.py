"""TC-ACL-01 AST builder 括号化与渲染等价【单测｜M0a→M0b 双后端】。

- 多维度条件以显式括号 AND 连接（无优先级歧义）；
- 产物由 AST 渲染（结构断言：节点树含 And/Or/NotExists/InValue），**无字符串拼接**
  ——授权值只出现在绑定参数里，SQL 文本不含数据值字面量；
- 渲染 SQL 可被库直接 prepare 且执行结果与手写等价 SQL 相同（design §5.1 示意
  ——双方言各持一份手写等价 SQL，均含逐字数据字面量、与渲染产物参数形态互证）。
"""

from __future__ import annotations

from helpers import NOW_TS

from knowledge_lattice.store.acl_ast import (
    And,
    Exists,
    InValue,
    NotExists,
    Or,
)
from knowledge_lattice.store.backend import AclDimensionRule

# design §5.1 示意 SQL 的手写等价形态（u_full：region=[CN,OS]、tax_type=[VAT]，
# 两维度均 active；取值直接写字面量——与渲染产物的参数形态互证等价）
HANDWRITTEN_SQLITE = (
    "SELECT c.rid, c.id, c.doc_id FROM chunks c JOIN documents d ON d.id = c.doc_id"
    " WHERE ((NOT EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.region'))"
    " OR EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.region') AS je"
    " WHERE je.value IN ('CN','OS')))"
    " AND (NOT EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.tax_type'))"
    " OR EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.tax_type') AS je"
    " WHERE je.value IN ('VAT'))))"
    " AND c.version = d.active_version AND c.tombstone = 0 AND d.org_id = 'org:tax'"
)

# PG 手写等价（json_each → jsonb 等价路径谓词——§4 PG 映射）
HANDWRITTEN_PG = (
    "SELECT c.rid, c.id, c.doc_id FROM chunks c JOIN documents d ON d.id = c.doc_id"
    " WHERE ((NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text("
    "jsonb_extract_path(c.dims_json, 'region')))"
    " OR EXISTS (SELECT 1 FROM jsonb_array_elements_text("
    "jsonb_extract_path(c.dims_json, 'region')) AS je"
    " WHERE je.value IN ('CN','OS')))"
    " AND (NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text("
    "jsonb_extract_path(c.dims_json, 'tax_type')))"
    " OR EXISTS (SELECT 1 FROM jsonb_array_elements_text("
    "jsonb_extract_path(c.dims_json, 'tax_type')) AS je"
    " WHERE je.value IN ('VAT'))))"
    " AND c.version = d.active_version AND c.tombstone = 0 AND d.org_id = 'org:tax'"
)


def _plan(matrix):
    return matrix.compile_acl("u_full", "org:tax", now=NOW_TS)


def test_plan_rules_sorted_by_key(matrix) -> None:
    """规则按维度 key 排序（产物逐字稳定的基础——T4 逐字 diff 依赖确定性顺序）。"""
    plan = _plan(matrix)
    assert plan.dimension_rules == (
        AclDimensionRule(key="region", grants=("CN", "OS")),
        AclDimensionRule(key="tax_type", grants=("VAT",)),
    )


def test_ast_node_tree_contains_required_nodes(matrix) -> None:
    """结构断言（TC-ACL-01）：节点树含 And/Or/NotExists/InValue——产物由 AST 渲染。"""
    plan = _plan(matrix)
    where = matrix.build_where_ast(plan)
    assert isinstance(where, And)

    acl = matrix.build_acl_ast(plan)
    assert isinstance(acl, And) and len(acl.parts) == 2  # 多维度 → 合取

    region_block = acl.parts[0]
    assert isinstance(region_block, Or)  # 维度内：空值放行 OR 有值交集
    null_pass, has_value = region_block.parts
    assert isinstance(null_pass, NotExists)
    assert isinstance(has_value, Exists)
    predicate = has_value.subquery.predicate
    assert isinstance(predicate, InValue)
    assert predicate.values == ("CN", "OS")  # 授权常量落在结构节点上


def test_no_string_concat_values_only_via_params(matrix) -> None:
    """无字符串拼接：授权值 / org 只出现在绑定参数，SQL 文本不含数据值字面量；
    多维度显式括号 AND（维度块间 ") AND ("）、维度内 OR。"""
    sql, params = matrix.render_sql(matrix.build_where_ast(_plan(matrix)))
    for literal in ("'CN'", "'OS'", "'VAT'", "org:tax"):
        assert literal not in sql
    assert set(params.values()) >= {"CN", "OS", "VAT", "org:tax"}
    assert ") AND (" in sql  # 维度块之间显式括号 AND
    assert " OR " in sql     # 维度内 OR（空值放行 | 有值交集）


def test_rendered_sql_prepare_and_equivalent_to_handwritten(matrix) -> None:
    """渲染 SQL 可被库直接 prepare（绑定参数执行不抛错），结果与手写等价
    SQL 相同（design §5.1 示意的逐段对比——行为等价，双方言各持手写形态）。"""
    plan = _plan(matrix)
    sql, params = matrix.render_select(plan)
    rows_rendered = sorted(matrix.execute(sql, params))       # prepare + execute
    handwritten = HANDWRITTEN_SQLITE if matrix.is_sqlite else HANDWRITTEN_PG
    rows_handwritten = sorted(matrix.execute(handwritten))
    assert rows_rendered == rows_handwritten
    # u_full（region=[CN,OS]、tax_type=[VAT]）可见集：d_cit（tax_type=CIT）不可见
    assert {r[2] for r in rows_rendered} == {"d_cn", "d_multi", "d_empty_region", "d_os"}
