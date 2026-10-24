"""TC-ACL-03 空授权集 → NOT EXISTS 单条件【单测｜M0a→M0b 双后端】。

维度片段级断言（#38 P0-2 修订：断言落在维度片段、非整份产物）：tax_type 维度
片段为 `NOT EXISTS(…)` 单条件（v1.1 CTE 形态=无内层反连接——空授权只见该维
无任何行的文档；无 OR 分支，双方言同文），其余 active 维度（region）仍按统一
模板生成；全局不出现 `IN ()`（#34 必修 3 / T22）；行为断言：该用户只见
tax_type 为空的文档（region 约束照常叠加），非整体不可见。
"""

from __future__ import annotations

import pytest

from helpers import NOW_TS

from knowledge_lattice.store.acl_ast import InValue, ColumnRef


def _plan(matrix, user_id: str = "u_cn"):
    return matrix.compile_acl(user_id, "org:tax", now=NOW_TS)


def test_invalue_empty_values_rejected_at_construction() -> None:
    """「无 IN ()」为 Plan 层不变式：InValue 节点构造即拒绝空值集（机械执法）。"""
    with pytest.raises(ValueError, match="IN"):
        InValue(expr=ColumnRef("je", "value"), param_prefix="g_x", values=())


def test_tax_type_fragment_is_not_exists_single(matrix) -> None:
    """维度片段级断言：u_cn 在 tax_type 零授权 → 该维片段为 NOT EXISTS 单条件，
    无 OR EXISTS 分支；region 仍按统一模板（Or[NotExists, Exists[InValue]]）。"""
    plan = _plan(matrix)
    rules = {r.key: r for r in plan.dimension_rules}
    assert rules["tax_type"].is_empty
    fragment = matrix.render_sql(matrix.build_rule_ast(rules["tax_type"], _plan(matrix)))[0]
    # 双方言同一份文本（CTE 纯 JOIN/EXISTS——D24 可移植性判据）
    assert fragment == (
        "NOT EXISTS (SELECT 1 FROM document_dimensions AS dd"
        " JOIN dimensions AS dim ON dim.id = dd.dimension_id"
        " WHERE dd.doc_id = d.id AND dim.key = 'tax_type' AND dim.org_id = :org)"
        if matrix.is_sqlite else
        "NOT EXISTS (SELECT 1 FROM document_dimensions AS dd"
        " JOIN dimensions AS dim ON dim.id = dd.dimension_id"
        " WHERE dd.doc_id = d.id AND dim.key = 'tax_type' AND dim.org_id = %(org)s)"
    )
    assert " OR " not in fragment  # 无 OR 分支
    assert "dd2" not in fragment   # 无内层反连接（空授权=只见无行文档）
    # region 照常叠加（有值模板：含内层反连接）
    region_block = matrix.build_rule_ast(rules["region"], _plan(matrix))
    assert "dd2" in matrix.render_sql(region_block)[0]


def test_no_in_empty_list_anywhere(matrix) -> None:
    """全局不出现 `IN ()`（整份产物文本层兜底——SQL 语法非法防线）。"""
    sql, params = matrix.render_select(_plan(matrix))
    assert "IN ()" not in sql
    assert params  # 授权值全部经绑定参数


def test_behavior_only_tax_type_null_docs_visible(matrix) -> None:
    """u_cn（region=[CN]、tax_type 零授权）：只见 tax_type 为空的文档
    （d_multi / d_empty_region——region 约束照常叠加），非整体不可见。"""
    sql, params = matrix.render_select(_plan(matrix))
    assert {r[2] for r in matrix.execute(sql, params)} == {"d_multi", "d_empty_region"}
