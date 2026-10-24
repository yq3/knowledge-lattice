"""TC-ACL-06 外层常量约束与 FTS 路同构【单测｜M0a→M0b 双后端】。

主断言在 Plan 层（#42 P1-10）：外层常量约束为固定节点（c.version = d.active_version
AND c.tombstone = 0 AND d.org_id = :org）、FTS/向量/实体三路共用同一 Plan；
SQLite 渲染断言（sqlite-only——v1.4「SQL 文本断言仅对 SQLite 渲染器」）：FTS 路
产物为 chunks_fts MATCH + 同一 ACL 片段 + **版本条件在 JOIN 上**（T9 机制前提）。
组织限定是一切检索 SQL 第一条件（design §4）。PG FTS 路（to_tsquery/ts_rank）
随 M0b-2/M1——本文件 FTS 路文本/执行断言均 sqlite-only。
"""

from __future__ import annotations

from helpers import NOW_TS

from knowledge_lattice.store.acl_ast import (
    And,
    BindParam,
    ColumnRef,
    Eq,
    Literal,
)


def _plan(matrix):
    return matrix.compile_acl("u_full", "org:tax", now=NOW_TS)


def test_outer_constants_are_fixed_nodes(matrix) -> None:
    """常量约束为 Plan 层固定节点：版本/墓碑/org 三节点逐字出现在 WHERE 合取中，
    org 值经绑定参数（与 Plan.org_id 一致）。"""
    where = matrix.build_where_ast(_plan(matrix))
    expected = And((
        Eq(ColumnRef("c", "version"), ColumnRef("d", "active_version")),
        Eq(ColumnRef("c", "tombstone"), Literal(0)),
        Eq(ColumnRef("d", "org_id"), BindParam("org", "org:tax")),
    ))
    assert expected in where.parts
    _, params = matrix.render_select(_plan(matrix))
    assert params["org"] == "org:tax"


def test_three_routes_share_same_plan(matrix) -> None:
    """三路共用同一 Plan：基础/向量路的 WHERE 共享同一 ACL 片段；向量路仅追加
    embed_model 谓词（TC-EMB-02 联动——谓词仅向量路渲染）。FTS 路的 AST 同构
    断言 sqlite-only（PG FTS 路随 M0b-2/M1）。"""
    from knowledge_lattice.config import get_settings

    plan = matrix.compile_acl(
        "u_full", "org:tax", now=NOW_TS,
        embed_model=get_settings().embed_model_label,  # 向量路标签随 Plan 携带
    )
    base = matrix.build_where_ast(plan)
    vec = matrix.build_where_ast(plan, vector=True)

    acl_fragment = matrix.build_acl_ast(plan)
    assert base.parts[0] == acl_fragment
    assert vec.parts[0] == acl_fragment
    assert vec.parts[:-1] == base.parts  # 向量路 = 基础路 + embed_model 谓词
    if matrix.is_sqlite:
        fts = matrix.build_fts_where_ast(plan, query="common")
        assert fts.parts[1] == acl_fragment  # FTS 路 parts[0] 是 MATCH 谓词


def test_fts_route_version_condition_on_join(sqlite_matrix) -> None:
    """SQLite 渲染断言（sqlite-only）：FTS 路产物 = chunks_fts MATCH + 同一 ACL
    片段 + 版本条件在 JOIN 上（WHERE 内无版本条件）；组织限定同样在场。"""
    from knowledge_lattice.core.docs.acl import compile_acl
    from knowledge_lattice.store.sqlite.acl_render import render_fts_select
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    plan = compile_acl(SqliteBackend(sqlite_matrix), "u_full", "org:tax", now=NOW_TS)
    sql, params = render_fts_select(plan, query="common")
    join_part, where_part = sql.split(" WHERE ", 1)  # 首个 WHERE 即主查询（子查询在 WHERE 表达式内）
    assert "c.version = d.active_version" in join_part
    assert "c.version = d.active_version" not in where_part
    assert "f.chunks_fts MATCH :q" in where_part
    assert "d.org_id = :org" in where_part
    assert "'$.region'" in where_part  # 同一 ACL 片段
    assert params["q"] == "common"


def test_fts_route_results_equal_base_route(sqlite_matrix) -> None:
    """FTS 路与基础路在同一 Plan 下结果集相同（全文命中全集 + ACL 过滤——sqlite-only）。"""
    from knowledge_lattice.core.docs.acl import compile_acl
    from knowledge_lattice.store.sqlite.acl_render import (
        render_fts_select,
        render_select,
    )
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    plan = compile_acl(SqliteBackend(sqlite_matrix), "u_full", "org:tax", now=NOW_TS)
    base_sql, base_params = render_select(plan)
    fts_sql, fts_params = render_fts_select(plan, query="common")
    rows_base = sorted(sqlite_matrix.execute(base_sql, base_params))
    rows_fts = sorted(sqlite_matrix.execute(fts_sql, fts_params))
    assert rows_fts == rows_base
    assert {r[2] for r in rows_fts} == {"d_cn", "d_multi", "d_empty_region", "d_os"}
