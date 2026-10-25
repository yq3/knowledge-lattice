"""TC-ACL-01 AST builder 括号化与渲染等价【单测｜M0a→M0b 双后端】。

- 多维度条件以显式括号 AND 连接（无优先级歧义）；
- 产物由 AST 渲染（结构断言：节点树含 And/NotExists/InValue），**无字符串拼接**
  ——授权值只出现在绑定参数里，SQL 文本不含数据值字面量；
- 渲染 SQL 可被库直接 prepare 且执行结果与手写等价 SQL 相同（design §5.1 示意
  ——v1.1 起双方言共用同一份手写形态：visible_docs CTE 纯 JOIN/EXISTS、无
  JSON 方言函数，D24 可移植性判据"归一化后逐字相同"的实证面）。
"""

from __future__ import annotations

from helpers import NOW_TS

from knowledge_lattice.store.acl_ast import (
    And,
    InSubquery,
    InValue,
    Literal,
    NotExists,
)
from knowledge_lattice.store.backend import AclDimensionRule

# design §5.1 示意 SQL 的手写等价形态（u_full：region=[CN,OS]、tax_type=[VAT]，
# 两维度均 active；取值直接写字面量——与渲染产物的参数形态互证等价）。
# v1.1（拍板 1）：visible_docs CTE 唯一路径——双方言同一份手写文本（仅参数记号
# 差异：sqlite :org / PG %(org)s——测试按方言替换 org 记号）。
_HANDWRITTEN_BODY = (
    "WITH visible_docs(doc_id) AS (SELECT d.id FROM documents d WHERE d.org_id = 'org:tax'"
    " AND NOT EXISTS (SELECT 1 FROM document_dimensions AS dd"
    " JOIN dimensions AS dim ON dim.id = dd.dimension_id"
    " WHERE dd.doc_id = d.id AND dim.key = 'region' AND dim.org_id = 'org:tax'"
    " AND NOT EXISTS (SELECT 1 FROM document_dimensions AS dd2"
    " JOIN dimension_values AS v ON v.id = dd2.value_id AND v.dimension_id = dd2.dimension_id"
    " WHERE dd2.doc_id = dd.doc_id AND dd2.dimension_id = dd.dimension_id"
    " AND v.value IN ('CN','OS')))"
    " AND NOT EXISTS (SELECT 1 FROM document_dimensions AS dd"
    " JOIN dimensions AS dim ON dim.id = dd.dimension_id"
    " WHERE dd.doc_id = d.id AND dim.key = 'tax_type' AND dim.org_id = 'org:tax'"
    " AND NOT EXISTS (SELECT 1 FROM document_dimensions AS dd2"
    " JOIN dimension_values AS v ON v.id = dd2.value_id AND v.dimension_id = dd2.dimension_id"
    " WHERE dd2.doc_id = dd.doc_id AND dd2.dimension_id = dd.dimension_id"
    " AND v.value IN ('VAT'))))"
    " SELECT c.rid, c.id, c.doc_id FROM chunks c JOIN documents d ON d.id = c.doc_id"
    " WHERE c.doc_id IN (SELECT doc_id FROM visible_docs)"
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
    """结构断言（TC-ACL-01）：节点树含 And/NotExists/InValue——产物由 AST 渲染。

    v1.1 CTE 形态：单维块 = NotExists[dd∈dim 行存在，且无一行取值命中授权集]；
    授权常量落在内层反连接的 InValue 节点上（v.value IN grants）。"""
    from knowledge_lattice.store.acl_ast import ColumnRef, Eq

    plan = _plan(matrix)
    outer_where = matrix.build_outer_where(plan)
    assert isinstance(outer_where, And)
    assert isinstance(outer_where.parts[0], InSubquery)  # c.doc_id IN (visible_docs)

    blocks = [matrix.build_rule_ast(rule, plan) for rule in plan.dimension_rules]
    region_block = blocks[0]
    assert isinstance(region_block, NotExists)  # 可见 = 该维无行 或 有命中
    [dd_join] = region_block.subquery.joins
    assert dd_join.table.name == "dimensions"
    # 谓词合取：doc 关联 + key 字面量 + org 参数 + 内层反连接（有值交集）
    conds = region_block.subquery.predicate.parts
    assert conds[1] == Eq(ColumnRef("dim", "key"), Literal("region"))
    inner = conds[-1]
    assert isinstance(inner, NotExists)
    [v_join] = inner.subquery.joins
    assert v_join.table.name == "dimension_values"
    predicate = inner.subquery.predicate.parts[-1]
    assert isinstance(predicate, InValue)
    assert predicate.values == ("CN", "OS")  # 授权常量落在结构节点上


def test_no_string_concat_values_only_via_params(matrix) -> None:
    """无字符串拼接：授权值 / org 只出现在绑定参数，SQL 文本不含数据值字面量；
    维度块以 NOT EXISTS 链 AND 连接；有值交集的内层反连接在场。"""
    sql, params = matrix.render_select(_plan(matrix))
    for literal in ("'CN'", "'OS'", "'VAT'", "org:tax"):
        assert literal not in sql
    assert set(params.values()) >= {"CN", "OS", "VAT", "org:tax"}
    assert " AND NOT EXISTS" in sql  # 维度块之间 AND 连接（CTE WHERE）
    assert "document_dimensions AS dd2" in sql  # 有值交集（内层反连接）
    assert "json_each" not in sql and "dims_json" not in sql  # 按块模板已删（拍板 1）


def test_rendered_sql_prepare_and_equivalent_to_handwritten(matrix) -> None:
    """渲染 SQL 可被库直接 prepare（绑定参数执行不抛错），结果与手写等价
    SQL 相同（design §5.1 示意的逐段对比——行为等价；v1.1 双方言同一份手写
    CTE 形态，仅 org 记号按方言替换）。"""
    plan = _plan(matrix)
    sql, params = matrix.render_select(plan)
    rows_rendered = sorted(matrix.execute(sql, params))       # prepare + execute
    rows_handwritten = sorted(matrix.execute(_HANDWRITTEN_BODY))
    assert rows_rendered == rows_handwritten
    # u_full（region=[CN,OS]、tax_type=[VAT]）可见集：d_cit（tax_type=CIT）不可见
    assert {r[2] for r in rows_rendered} == {"d_cn", "d_multi", "d_empty_region", "d_os"}
