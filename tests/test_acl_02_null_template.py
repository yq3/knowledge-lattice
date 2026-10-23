"""TC-ACL-02 统一空值模板（有值交集 / 无值放行）【单测｜M0a】。

本地 fixture（#40 P1-R3：**不复用标准矩阵**——只启用 region 单个维度，消除多维度
混淆）。主断言在 AclPlan 结构层（#42 P1-10）：每维 Plan 为
`(NotExists | Or[Exists, InValue])` 组合、空值模板与授权常量落在结构节点上；
行为断言：u_cn_r 见 d_cn_r+d_empty_r、u_os_r 只见 d_empty_r（不见 d_cn_r）——
维度间 AND、维度内 OR（D5）。SQLite 渲染 SQL 文本快照仅作渲染器附带断言
（sqlite-only，不锁 PG 实现）。
"""

from __future__ import annotations

import pytest

from helpers import (
    NOW_TS,
    grant_by_key,
    seed_dataset,
    seed_dim_value,
    seed_dimension,
    seed_membership,
    seed_org,
    seed_searchable_doc,
    seed_user,
)

from knowledge_lattice.core.docs.acl import compile_acl
from knowledge_lattice.store.backend import AclDimensionRule
from knowledge_lattice.store.sqlite.acl_render import (
    ColumnRef,
    Exists,
    Func,
    InValue,
    Literal,
    NotExists,
    Or,
    build_dimension_rule_ast,
    build_where_ast,
    render_select,
    render_sql,
)
from knowledge_lattice.store.sqlite.backend import SqliteBackend


@pytest.fixture()
def single_region(conn):
    """只启用 region 单维度的本地 fixture（d_cn_r=[CN]、d_empty_r 无值；
    u_cn_r=[CN]、u_os_r=[OS]——均为有效成员）。"""
    seed_org(conn)
    seed_dataset(conn, org_id="org:tax", ds_id="ds:vat_lib")
    seed_dimension(conn, "org:tax", "region")
    seed_dim_value(conn, "dim:org:tax:region", "CN")
    seed_dim_value(conn, "dim:org:tax:region", "OS")
    for uid in ("u_cn_r", "u_os_r"):
        seed_user(conn, uid)
        seed_membership(conn, uid, "org:tax")
    grant_by_key(conn, "u_cn_r", key="region", value="CN")
    grant_by_key(conn, "u_os_r", key="region", value="OS")
    seed_searchable_doc(conn, "d_cn_r", dims={"region": ["CN"]}, owner_user_id="u_cn_r")
    seed_searchable_doc(conn, "d_empty_r", owner_user_id="u_cn_r")
    return conn


def _compile(conn, user_id: str):
    return compile_acl(SqliteBackend(conn), user_id, "org:tax", now=NOW_TS)


def test_plan_structure_null_template_nodes(single_region) -> None:
    """主断言（Plan 结构层）：每维 Plan 为 (NotExists | Or[Exists, InValue]) 组合，
    空值模板（json_each 扫描 '$.region'）与授权常量（InValue.values）落在结构节点上。"""
    plan = _compile(single_region, "u_cn_r")
    assert plan.dimension_rules == (AclDimensionRule(key="region", grants=("CN",)),)
    block = build_dimension_rule_ast(plan.dimension_rules[0])
    assert isinstance(block, Or)
    null_pass, has_value = block.parts
    assert isinstance(null_pass, NotExists)
    # 空值模板：NOT EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.region'))
    assert null_pass.subquery.from_table == Func(
        "json_each", (ColumnRef("c", "dims_json"), Literal("$.region"))
    )
    assert isinstance(has_value, Exists)
    predicate = has_value.subquery.predicate
    assert isinstance(predicate, InValue) and predicate.values == ("CN",)


def test_behavior_u_cn_r_sees_valued_and_null(single_region) -> None:
    """u_cn_r（region=[CN]）可见 d_cn_r（有值交集）与 d_empty_r（空值放行）。"""
    sql, params = render_select(_compile(single_region, "u_cn_r"))
    assert {r[2] for r in single_region.execute(sql, params)} == {"d_cn_r", "d_empty_r"}


def test_behavior_u_os_r_sees_only_null(single_region) -> None:
    """u_os_r（region=[OS]）只见 d_empty_r——d_cn_r 的 [CN] 与授权集 [OS] 无交集。"""
    sql, params = render_select(_compile(single_region, "u_os_r"))
    assert {r[2] for r in single_region.execute(sql, params)} == {"d_empty_r"}


def test_sql_text_snapshot_renderer_side(single_region) -> None:
    """渲染器附带断言（sqlite-only）：单维 WHERE 文本快照 + 参数表。
    参数名为渲染器序列名（g<seq>_<i>，与维度 key 无关——Committer R1 P1-1）。"""
    sql, params = render_sql(build_where_ast(_compile(single_region, "u_cn_r")))
    assert sql == (
        "(NOT EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.region'))"
        " OR EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.region') AS je"
        " WHERE je.value IN (:g0_0)))"
        " AND (c.version = d.active_version AND c.tombstone = 0 AND d.org_id = :org)"
    )
    assert params == {"g0_0": "CN", "org": "org:tax"}
