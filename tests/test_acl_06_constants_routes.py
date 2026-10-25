"""TC-ACL-06 外层常量约束与三路同构【单测｜M0a→M1 双后端】。

主断言在 Plan 层（#42 P1-10）：外层常量约束为固定节点（c.version = d.active_version
AND c.tombstone = 0 AND d.org_id = :org）、FTS/向量/实体三路共用同一 Plan 与**同一
visible_docs CTE**（v1.1 唯一路径——ACL 维度规则全部在 CTE 内，三路外层共享可见集
引用）；向量路仅追加 chunk_vectors JOIN 谓词（TC-EMB-02——谓词迁 cv）。
FTS 路文本断言（M1-1 R2 起双方言——PG 渲染 Match 节点为五列 tsvector @@ OR）：
产物含可见集引用 + **版本条件在 chunks/documents JOIN 上**（T9 机制前提——
P0-1 回归锁定：PG 曾漏该条件使 pending 块可混入 BM25 路）。
组织限定是一切检索 SQL 第一条件（design §4）。
"""

from __future__ import annotations

from helpers import NOW_TS

from knowledge_lattice.store.acl_ast import (
    And,
    BindParam,
    ColumnRef,
    Eq,
    InSubquery,
    Literal,
)


def _plan(matrix):
    return matrix.compile_acl("u_full", "org:tax", now=NOW_TS)


def test_outer_constants_are_fixed_nodes(matrix) -> None:
    """常量约束为 Plan 层固定节点：版本/墓碑/org 三节点逐字出现在 WHERE 合取中，
    org 值经绑定参数（与 Plan.org_id 一致）。"""
    where = matrix.build_outer_where(_plan(matrix))
    expected = And((
        Eq(ColumnRef("c", "version"), ColumnRef("d", "active_version")),
        Eq(ColumnRef("c", "tombstone"), Literal(0)),
        Eq(ColumnRef("d", "org_id"), BindParam("org", "org:tax")),
    ))
    assert expected in where.parts
    _, params = matrix.render_select(_plan(matrix))
    assert params["org"] == "org:tax"


def test_three_routes_share_same_plan(matrix) -> None:
    """三路共用同一 Plan 与同一 CTE：基础/向量路的外层 WHERE 共享可见集引用与
    常量组；三路的 CTE WHERE 节点树逐字相同；向量路仅追加 cv JOIN 谓词
    （TC-EMB-02 联动——谓词仅向量路渲染）。FTS 路 AST 双方言同构
    （M1-1 起 PG 渲染 Match 节点——R2 扩双方言，P0-1 修法②）。"""
    from knowledge_lattice.config import get_settings

    label = get_settings().embed_model_label
    plan = matrix.compile_acl("u_full", "org:tax", now=NOW_TS)  # 基础路
    vec_plan = matrix.compile_acl("u_full", "org:tax", now=NOW_TS, embed_model=label)

    base_outer = matrix.build_outer_where(plan)
    base_cte = matrix.build_cte_where(plan)
    vec_cte, cv_join, vec_outer = matrix.build_vec_parts(vec_plan)

    # 三路同一 CTE：向量路 CTE 与基础路逐字相同（同一 Plan 同一授权展开）
    assert vec_cte == base_cte
    # 向量路外层 = 基础路外层（可见集引用 + 常量组 + 过滤）；谓词在 cv JOIN 上
    assert vec_outer == base_outer
    expected_pred = Eq(ColumnRef("cv", "embed_model"), BindParam("current_model", label))
    assert expected_pred in cv_join.on.parts  # 谓词为固定节点（结构断言）

    # FTS 路（双方言——AST 同构：parts[0] 为 MATCH 谓词节点、parts[1] 共享可见集引用）
    fts_where = matrix.build_fts_where_ast(plan, query="common")
    assert fts_where.parts[1] == base_outer.parts[0]
    # FTS 路 SQL 内嵌同一 CTE（文本前缀逐字一致——同一构造；双后端各查自家渲染器）
    if matrix.is_sqlite:
        from knowledge_lattice.store.sqlite.acl_render import render_fts_select

        fts_sql, _ = render_fts_select(plan, query="common")
    else:
        from knowledge_lattice.store.postgres.acl_render import render_fts_recall_select
        from knowledge_lattice.store.postgres.fts import build_tsquery

        fts_sql, _ = render_fts_recall_select(plan, build_tsquery(["common"]), top_k=10)
    base_sql, _ = matrix.render_select(plan)
    assert fts_sql.startswith(base_sql.split(") SELECT", 1)[0])


def test_fts_route_version_condition_on_join(matrix) -> None:
    """双方言渲染断言（M1-1 R2 扩——P0-1 回归锁定）：FTS 路**召回 SQL**（实装
    路径 render_fts_recall_select）的版本条件在 chunks/documents JOIN 上（主查询
    WHERE 内无版本条件——T9 机制前提）；组织限定在 CTE 与主查询 WHERE 双在场；
    维度条件在 CTE（不在主查询 WHERE）。PG 臂直查实装路径——该缺陷曾因「只
    断言 search() 最终结果」被兜底断言掩盖（Committer P0-1）。"""
    from knowledge_lattice.core.docs.acl import compile_acl

    plan = matrix.compile_acl("u_full", "org:tax", now=NOW_TS)
    if matrix.is_sqlite:
        from knowledge_lattice.store.sqlite.acl_render import render_fts_recall_select

        sql, params = render_fts_recall_select(plan, '"common"', top_k=10)
    else:
        from knowledge_lattice.store.postgres.acl_render import render_fts_recall_select
        from knowledge_lattice.store.postgres.fts import build_tsquery

        sql, params = render_fts_recall_select(plan, build_tsquery(["common"]), top_k=10)

    cte_part, main_part = sql.split(") SELECT ", 1)  # CTE 段 / 主查询段
    join_part, where_part = main_part.split(" WHERE ", 1)
    # 版本条件在 JOIN 上（T9）——PG 曾漏（P0-1）：pending 块混入 BM25 路
    assert "c.version = d.active_version" in join_part, "FTS 路版本条件必须在 JOIN 上"
    assert "c.version = d.active_version" not in where_part
    # 匹配谓词在场（方言各自形态）+ 可见集引用 + org 双在场 + 维度条件在 CTE
    if matrix.is_sqlite:
        assert "f.chunks_fts MATCH :q" in where_part
    else:
        assert "to_tsquery('simple', %(q)s)" in where_part
    assert "c.doc_id IN (SELECT doc_id FROM visible_docs)" in where_part
    assert "d.org_id" in where_part and "d.org_id" in cte_part
    assert "dim.key = 'region'" in cte_part  # 维度 ACL 在 CTE（同一构造）


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
