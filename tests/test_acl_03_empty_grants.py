"""TC-ACL-03 空授权集 → NOT EXISTS 单条件【单测｜M0a】。

维度片段级断言（#38 P0-2 修订：断言落在维度片段、非整份产物）：tax_type 维度
片段为 `NOT EXISTS(…'$.tax_type')` 单条件（无 OR EXISTS 分支），其余 active 维度
（region）仍按统一模板生成；全局不出现 `IN ()`（#34 必修 3 / T22）；行为断言：
该用户只见 tax_type 为空的文档（region 约束照常叠加），非整体不可见。
"""

from __future__ import annotations

import pytest

from helpers import NOW_TS

from knowledge_lattice.core.docs.acl import compile_acl
from knowledge_lattice.store.sqlite.acl_render import (
    ColumnRef,
    InValue,
    Or,
    build_dimension_rule_ast,
    render_select,
    render_sql,
)
from knowledge_lattice.store.sqlite.backend import SqliteBackend


def _plan(matrix, user_id: str = "u_cn"):
    return compile_acl(SqliteBackend(matrix), user_id, "org:tax", now=NOW_TS)


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
    fragment = render_sql(build_dimension_rule_ast(rules["tax_type"]))[0]
    assert fragment == "NOT EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.tax_type'))"
    assert " OR " not in fragment  # 无 OR EXISTS 分支
    assert isinstance(build_dimension_rule_ast(rules["region"]), Or)  # region 照常叠加


def test_no_in_empty_list_anywhere(matrix) -> None:
    """全局不出现 `IN ()`（整份产物文本层兜底——SQL 语法非法防线）。"""
    sql, params = render_select(_plan(matrix))
    assert "IN ()" not in sql
    assert params  # 授权值全部经绑定参数


def test_behavior_only_tax_type_null_docs_visible(matrix) -> None:
    """u_cn（region=[CN]、tax_type 零授权）：只见 tax_type 为空的文档
    （d_multi / d_empty_region——region 约束照常叠加），非整体不可见。"""
    sql, params = render_select(_plan(matrix))
    assert {r[2] for r in matrix.execute(sql, params)} == {"d_multi", "d_empty_region"}
