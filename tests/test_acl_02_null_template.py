"""TC-ACL-02 统一空值模板（有值交集 / 无值放行）【单测｜M0a→M0b 双后端】。

本地 fixture（#40 P1-R3：**不复用标准矩阵**——只启用 region 单个维度，消除多维度
混淆）。主断言在 AclPlan 结构层（#42 P1-10）：每维 Plan 为
`NotExists[dd 行存在 ∧ 无一行命中授权集]` 组合（v1.1 CTE 形态——可见=无行或有命中；
空授权=无任何 dd 行才可见），空值模板与授权常量落在结构节点上；
行为断言：u_cn_r 见 d_cn_r+d_empty_r、u_os_r 只见 d_empty_r（不见 d_cn_r）——
维度间 AND、维度内空值放行（D5）。SQLite 渲染 SQL 文本快照仅作渲染器附带断言
（sqlite-only，不锁 PG 实现——v1.4）。
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

from knowledge_lattice.store.backend import AclDimensionRule


@pytest.fixture()
def single_region(backend):
    """只启用 region 单维度的本地 fixture（d_cn_r=[CN]、d_empty_r 无值；
    u_cn_r=[CN]、u_os_r=[OS]——均为有效成员）。"""
    seed_org(backend)
    seed_dataset(backend, org_id="org:tax", ds_id="ds:vat_lib")
    seed_dimension(backend, "org:tax", "region")
    seed_dim_value(backend, "dim:org:tax:region", "CN")
    seed_dim_value(backend, "dim:org:tax:region", "OS")
    for uid in ("u_cn_r", "u_os_r"):
        seed_user(backend, uid)
        seed_membership(backend, uid, "org:tax")
    grant_by_key(backend, "u_cn_r", key="region", value="CN")
    grant_by_key(backend, "u_os_r", key="region", value="OS")
    seed_searchable_doc(backend, "d_cn_r", dims={"region": ["CN"]}, owner_user_id="u_cn_r")
    seed_searchable_doc(backend, "d_empty_r", owner_user_id="u_cn_r")
    return backend


@pytest.fixture()
def single_region_sqlite(conn):
    """sqlite 直连形态（渲染器文本快照 sqlite-only 断言用）。"""
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


def test_plan_structure_null_template_nodes(single_region) -> None:
    """主断言（Plan 结构层，v1.1 CTE 形态）：每维 Plan 为 NotExists 组合——
    外层（该维无 dd 行=空值放行）+ 内层反连接（无一行取值 ∈ 授权集=有值过滤），
    授权常量（InValue.values）落在结构节点上。"""
    from knowledge_lattice.store.acl_ast import InValue, NotExists

    plan = single_region.compile_acl("u_cn_r", "org:tax", now=NOW_TS)
    assert plan.dimension_rules == (AclDimensionRule(key="region", grants=("CN",)),)
    block = single_region.build_rule_ast(plan.dimension_rules[0], plan)
    assert isinstance(block, NotExists)
    # 空值放行半句：外层 NotExists（文档在该维无任何 document_dimensions 行）
    assert block.subquery.from_table.name == "document_dimensions"
    # 有值交集半句：内层反连接（无一行命中授权集 → 不可见）
    inner = block.subquery.predicate.parts[-1]
    assert isinstance(inner, NotExists)
    assert inner.subquery.from_table.name == "document_dimensions"
    [v_join] = inner.subquery.joins
    assert v_join.table.name == "dimension_values"
    predicate = inner.subquery.predicate.parts[-1]
    assert isinstance(predicate, InValue) and predicate.values == ("CN",)


def test_behavior_u_cn_r_sees_valued_and_null(single_region) -> None:
    """u_cn_r（region=[CN]）可见 d_cn_r（有值交集）与 d_empty_r（空值放行）。"""
    sql, params = single_region.render_select(single_region.compile_acl("u_cn_r", "org:tax", now=NOW_TS))
    assert {r[2] for r in single_region.execute(sql, params)} == {"d_cn_r", "d_empty_r"}


def test_behavior_u_os_r_sees_only_null(single_region) -> None:
    """u_os_r（region=[OS]）只见 d_empty_r——d_cn_r 的 [CN] 与授权集 [OS] 无交集。"""
    sql, params = single_region.render_select(single_region.compile_acl("u_os_r", "org:tax", now=NOW_TS))
    assert {r[2] for r in single_region.execute(sql, params)} == {"d_empty_r"}


def test_sql_text_snapshot_renderer_side(single_region_sqlite) -> None:
    """渲染器附带断言（sqlite-only）：单维 CTE 文本快照 + 参数表。
    参数名为渲染器序列名（g<seq>_<i>，与维度 key 无关——Committer R1 P1-1）；
    MATERIALIZED 双方言统一加注（sqlite ≥3.35 同语法、默认物化 no-op）。"""
    from knowledge_lattice.core.docs.acl import compile_acl
    from knowledge_lattice.store.sqlite.acl_render import render_select
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    plan = compile_acl(SqliteBackend(single_region_sqlite), "u_cn_r", "org:tax", now=NOW_TS)
    sql, params = render_select(plan)
    assert sql == (
        "WITH visible_docs(doc_id) AS MATERIALIZED (SELECT d.id FROM documents d"
        " WHERE d.org_id = :org"
        " AND NOT EXISTS (SELECT 1 FROM document_dimensions AS dd"
        " JOIN dimensions AS dim ON dim.id = dd.dimension_id"
        " WHERE dd.doc_id = d.id AND dim.key = 'region' AND dim.org_id = :org"
        " AND NOT EXISTS (SELECT 1 FROM document_dimensions AS dd2"
        " JOIN dimension_values AS v ON v.id = dd2.value_id AND v.dimension_id = dd2.dimension_id"
        " WHERE dd2.doc_id = dd.doc_id AND dd2.dimension_id = dd.dimension_id"
        " AND v.value IN (:g0_0))))"
        " SELECT c.rid, c.id, c.doc_id"
        " FROM chunks c JOIN documents d ON d.id = c.doc_id"
        " WHERE c.doc_id IN (SELECT doc_id FROM visible_docs)"
        " AND (c.version = d.active_version AND c.tombstone = 0 AND d.org_id = :org)"
    )
    assert params == {"g0_0": "CN", "org": "org:tax"}
