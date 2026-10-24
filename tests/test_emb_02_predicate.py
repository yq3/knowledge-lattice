"""TC-EMB-02 embed_model 查询谓词（编译/Plan 层）【单测｜M0a→M0b 双后端】。

断言落在 AclPlan 结构层（#42 P1-10 / v1.4 拆分）：Plan 含谓词节点
（embed_model 字段=当前 config 标签）+ 渲染参数绑定该标签；v1.1（拍板 2）谓词
迁 `chunk_vectors`——`JOIN cv ON cv.rid = c.rid AND cv.embed_model = :current_model`
（节点语义保持：Eq + BindParam 固定节点、值=Plan.embed_model，仅列引用 c→cv；
渲染 SQL 文本断言按方言分派（sqlite=`:current_model` / pg=`%(current_model)s`
——附带断言，不锁实现）。检索行为半句（旧标签块只走 BM25、不进向量路 top-k）
拆至 TC-EMB-07 随 M1（M0a 检索本就 BM25 单路、行为不可测）。
"""

from __future__ import annotations

from helpers import NOW_TS

from knowledge_lattice.config import get_settings
from knowledge_lattice.store.acl_ast import BindParam, ColumnRef, Eq


def test_embed_model_predicate_node_and_param_binding(matrix) -> None:
    """向量路编译产物含 `cv.embed_model = :current_model` 谓词（v1.1 迁 chunk_vectors
    JOIN）：Plan 层为固定节点、参数绑定当前 config 标签（model:dim——D12）。"""
    label = get_settings().embed_model_label
    assert label == "qwen3-embedding-4b:2560"  # 当前 config 标签（默认值钉住）

    plan = matrix.compile_acl("u_full", "org:tax", now=NOW_TS, embed_model=label)
    assert plan.embed_model == label  # Plan 含谓词节点（v1.4 上移）

    cte, cv_join, outer = matrix.build_vec_parts(plan)
    expected = Eq(ColumnRef("cv", "embed_model"), BindParam("current_model", label))
    assert expected in cv_join.on.parts  # 谓词为固定节点（结构断言——列引用迁 cv）

    sql, params = matrix.render_sql(cv_join)
    if matrix.is_sqlite:
        assert "cv.embed_model = :current_model" in sql  # 渲染器附带断言
    else:
        assert "cv.embed_model = %(current_model)s" in sql
    assert "chunk_vectors AS cv" in sql
    assert params["current_model"] == label             # 参数绑定当前 config 标签
    # 向量路外层 WHERE 与基础路同构（可见集引用 + 常量组——无 embed_model 谓词）
    assert "embed_model" not in matrix.render_sql(outer)[0]
    assert "embed_model" not in matrix.render_sql(cte)[0]


def test_base_route_does_not_render_embed_predicate(matrix) -> None:
    """基础/FTS/实体路不渲染该谓词——三路共用同一 Plan，谓词仅向量路 JOIN。"""
    plan = matrix.compile_acl(
        "u_full", "org:tax", now=NOW_TS,
        embed_model=get_settings().embed_model_label,
    )
    sql, _ = matrix.render_select(plan)
    assert "embed_model" not in sql
