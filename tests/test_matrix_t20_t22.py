"""越权矩阵 T20 / T22 的 M0a 编译器单测先行形态（design §8 M0a.5）。

T20 新建维度零消失 / 回填只收紧 / 生命周期不放宽 / 仅退役放宽（审计半句「退役
事件入 outbox」随 M2——条件消失断言必做）；T22 无授权维度只见空值文档、空集
不出 `IN ()`（维度片段级断言）。
"""

from __future__ import annotations

from helpers import NOW_TS, dim_id_for, seed_dim_value, seed_dimension, seed_doc_dims

from knowledge_lattice.core.docs.acl import compile_acl
from knowledge_lattice.store.sqlite.acl_render import (
    build_dimension_rule_ast,
    render_select,
    render_sql,
)
from knowledge_lattice.store.sqlite.backend import SqliteBackend


def _compile(matrix, user_id: str):
    return compile_acl(SqliteBackend(matrix), user_id, "org:tax", now=NOW_TS)


def _visible(matrix, user_id: str) -> set[str]:
    sql, params = render_select(_compile(matrix, user_id))
    return {r[2] for r in matrix.execute(sql, params)}


def test_t20_new_dimension_lifecycle(matrix) -> None:
    """T20 全四断言（审计半句随 M2）：① 新建维度零消失；② 回填即收紧；
    ③ required/enabled 改不动可见性；④ 退役=唯一放宽（条件从产物消失）。"""
    base_full = _visible(matrix, "u_full")
    base_cn = _visible(matrix, "u_cn")
    assert base_full == {"d_cn", "d_multi", "d_empty_region", "d_os"}

    # ① 新建 active 必选维度 channel（存量文档零回填）→ 全用户检索零消失
    seed_dimension(matrix, "org:tax", "channel")
    seed_dim_value(matrix, dim_id_for("org:tax", "channel"), "A")
    assert _visible(matrix, "u_full") == base_full
    assert _visible(matrix, "u_cn") == base_cn

    # ② 回填 d_cn channel=[A]（u_full 无 channel 授权）→ d_cn 不可见（回填即收紧）
    seed_doc_dims(matrix, "d_cn", {"channel": ["A"]})
    assert _visible(matrix, "u_full") == {"d_multi", "d_empty_region", "d_os"}
    assert "d_empty_region" in _visible(matrix, "u_full")

    # ③ channel required 1→0、enabled 1→0 → 可见性不变（不放宽）
    for column in ("required", "enabled"):
        matrix.execute(
            f"UPDATE dimensions SET {column} = 0 WHERE org_id = 'org:tax' AND key = 'channel'"
        )
        assert _visible(matrix, "u_full") == {"d_multi", "d_empty_region", "d_os"}

    # ④ channel retire → channel 条件从产物消失（唯一放宽路径；退役事件入 outbox
    #    审计半句随 M2）；d_cn 恢复可见（放宽回基线）
    matrix.execute(
        "UPDATE dimensions SET status = 'retired' WHERE org_id = 'org:tax' AND key = 'channel'"
    )
    plan = _compile(matrix, "u_full")
    assert all(r.key != "channel" for r in plan.dimension_rules)  # 条件从 Plan 消失
    sql, _ = render_select(plan)
    assert "'$.channel'" not in sql
    assert _visible(matrix, "u_full") == base_full


def test_t22_no_grant_dimension_only_null_docs(matrix) -> None:
    """T22：u_cn（tax_type 零授权）检索全库——只见 tax_type 为空的文档（region
    约束照常叠加）；tax_type 维度片段为 NOT EXISTS 单条件（无 OR EXISTS 分支）、
    完整产物仍含 region 统一模板、全局无 `IN ()`。"""
    plan = _compile(matrix, "u_cn")
    rules = {r.key: r for r in plan.dimension_rules}
    assert rules["tax_type"].is_empty

    fragment = render_sql(build_dimension_rule_ast(rules["tax_type"]))[0]
    assert fragment == "NOT EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.tax_type'))"
    assert " OR " not in fragment

    sql, params = render_select(plan)
    assert "'$.region'" in sql and " OR " in sql  # region 统一模板照常在场
    assert "IN ()" not in sql
    assert set(params.values()) >= {"CN", "org:tax"}

    assert _visible(matrix, "u_cn") == {"d_multi", "d_empty_region"}
