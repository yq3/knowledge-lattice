"""TC-ACL-04 生命周期与过滤解耦【单测｜M0a→M0b 双后端】。

① region 的 required 1→0、enabled 1→0 → 产物逐字不变（required/enabled 不影响
过滤——T4/T20，D5 v0.4）；② 某维度 status 置 retired → 不生成任何条件（唯一放宽
路径）；③ 新建维度 channel（无任何文档回填）→ 编译空值放行条件、存量文档零消失
（T20①——回填后才逐篇收紧）。维度条件在场/缺席逐字断言经 dim_marker 方言分派。
"""

from __future__ import annotations

from helpers import NOW_TS, dim_id_for, seed_dim_value, seed_dimension

from knowledge_lattice.store.acl_ast import NotExists


def _compile(matrix, user_id: str):
    return matrix.compile_acl(user_id, "org:tax", now=NOW_TS)


def _visible(matrix, user_id: str) -> set[str]:
    sql, params = matrix.render_select(_compile(matrix, user_id))
    return {r[2] for r in matrix.execute(sql, params)}


def test_required_enabled_flip_product_identical(matrix) -> None:
    """① required/enabled 1→0：Plan 与渲染产物（SQL 文本 + 参数表）逐字不变。"""
    before_plan = _compile(matrix, "u_full")
    before = matrix.render_select(before_plan)
    for column in ("required", "enabled"):
        matrix.execute(
            f"UPDATE dimensions SET {column} = 0 WHERE org_id = 'org:tax' AND key = 'region'"
        )
        assert _compile(matrix, "u_full") == before_plan  # Plan 层逐字不变
        assert matrix.render_select(_compile(matrix, "u_full")) == before  # 渲染层逐字不变
        matrix.execute(
            f"UPDATE dimensions SET {column} = 1 WHERE org_id = 'org:tax' AND key = 'region'"
        )  # 还原，逐一单因验证


def test_retired_dimension_generates_no_condition(matrix) -> None:
    """② retired 维度不生成任何条件（唯一放宽路径）；行为半句：region 退役后
    u_cn 的 d_os 变可见（放宽），tax_type 约束照常。"""
    assert _visible(matrix, "u_cn") == {"d_multi", "d_empty_region"}
    matrix.execute(
        "UPDATE dimensions SET status = 'retired' WHERE org_id = 'org:tax' AND key = 'region'"
    )
    plan = _compile(matrix, "u_full")
    assert [r.key for r in plan.dimension_rules] == ["tax_type"]  # region 规则消失
    sql, _ = matrix.render_select(plan)
    assert matrix.dim_marker("region") not in sql  # 不生成任何 region 条件
    # 行为：u_cn 放宽见 d_os（region 不再过滤）；d_cit 仍被 tax_type 挡住
    assert _visible(matrix, "u_cn") == {"d_multi", "d_empty_region", "d_os"}


def test_new_dimension_zero_disappear(matrix) -> None:
    """③ 新建 active 必选维度 channel（存量文档零回填）：编译出空值放行条件
    （u_full 无 channel 授权 → NOT EXISTS 单条件），存量文档零消失（T20①）。"""
    base_full = _visible(matrix, "u_full")
    base_cn = _visible(matrix, "u_cn")
    assert base_full == {"d_cn", "d_multi", "d_empty_region", "d_os"}

    seed_dimension(matrix, "org:tax", "channel")
    seed_dim_value(matrix, dim_id_for("org:tax", "channel"), "A")

    plan = _compile(matrix, "u_full")
    rules = {r.key: r for r in plan.dimension_rules}
    assert rules["channel"].is_empty
    block = matrix.build_dimension_rule_ast(rules["channel"])
    assert isinstance(block, NotExists)  # 空值放行条件（零授权 → 只见空值文档）
    fragment = matrix.render_sql(block)[0]
    if matrix.is_sqlite:
        assert fragment == "NOT EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.channel'))"
    else:
        assert fragment == (
            "NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text("
            "jsonb_extract_path(c.dims_json, 'channel')))"
        )
    # 存量文档零消失（全部 channel 空值 → 放行）
    assert _visible(matrix, "u_full") == base_full
    assert _visible(matrix, "u_cn") == base_cn
