"""TC-EMB-02 embed_model 查询谓词（编译/Plan 层）【单测｜M0a】。

断言落在 AclPlan 结构层（#42 P1-10 / v1.4 拆分）：Plan 含谓词节点
（embed_model 字段=当前 config 标签）+ 渲染参数绑定该标签；SQLite 渲染 SQL 文本
快照仅作渲染器附带断言（sqlite-only）。检索行为半句（旧标签块只走 BM25、不进
向量路 top-k）拆至 TC-EMB-07 随 M1（M0a 检索本就 BM25 单路、行为不可测）。
"""

from __future__ import annotations

from knowledge_lattice.config import get_settings
from knowledge_lattice.core.docs.acl import compile_acl
from knowledge_lattice.store.sqlite.acl_render import (
    BindParam,
    ColumnRef,
    Eq,
    build_where_ast,
    render_sql,
)
from knowledge_lattice.store.sqlite.backend import SqliteBackend

from helpers import NOW_TS


def test_embed_model_predicate_node_and_param_binding(matrix) -> None:
    """向量路编译产物含 `embed_model = :current_model` 谓词：Plan 层为固定节点、
    参数绑定当前 config 标签（model:dim——D12）。"""
    label = get_settings().embed_model_label
    assert label == "qwen3-embedding-4b:2560"  # 当前 config 标签（默认值钉住）

    plan = compile_acl(
        SqliteBackend(matrix), "u_full", "org:tax", now=NOW_TS, embed_model=label
    )
    assert plan.embed_model == label  # Plan 含谓词节点（v1.4 上移）

    where = build_where_ast(plan, vector=True)
    expected = Eq(ColumnRef("c", "embed_model"), BindParam("current_model", label))
    assert expected in where.parts  # 谓词为固定节点（结构断言）

    sql, params = render_sql(where)
    assert "c.embed_model = :current_model" in sql  # 渲染器附带断言（sqlite-only）
    assert params["current_model"] == label         # 参数绑定当前 config 标签


def test_base_route_does_not_render_embed_predicate(matrix) -> None:
    """基础/FTS/实体路不渲染该谓词——三路共用同一 Plan，谓词仅向量路追加。"""
    plan = compile_acl(
        SqliteBackend(matrix), "u_full", "org:tax", now=NOW_TS,
        embed_model=get_settings().embed_model_label,
    )
    sql, _ = render_sql(build_where_ast(plan))
    assert "embed_model" not in sql
