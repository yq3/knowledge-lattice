"""R2 审查修复回归（Committer R1）。

- M0b-3 顺带：dot-key 维度（'a.b'）在 CTE 路径下只以引号字面量出现（P3-5 随
  json_each 删除消解——原 JSON path '$.a.b' 的 dot 语义不复存在）。
- **P1-1（必修）**：绑定参数名不得由库内数据（维度 key）拼接——渲染器自控序列命名
  + `InValue.param_prefix` 标识符白名单 fail-closed（构造即拒）；恶意 key 只保留在
  转义后的 JSON path Literal 与 AclDimensionRule。三条回归：①恶意 prefix 构造即拒；
  ②恶意维度 key 下渲染 SQL 外层常量齐全（org/版本/tombstone）、参数名全为合法
  标识符、SQL 注释记号只可能出现在字符串字面量内；③双组织库真实执行无跨组织行。
- **P2-1（应修）**：`read_grants` 取值 JOIN 校验 `v.dimension_id = dim.id`——FK
  合法但 dimension/value 不匹配的畸形授权行不计入任何维度。
- **P3-3（覆盖盲区，5 条轻量断言）**：now=None 库时钟分支 / dataset_ids=() 与
  doc_ids=() 恒假路径 / 向量路缺 embed_model 的 ValueError / 全 retired 空
  Plan / 维度无取值场景。
"""

from __future__ import annotations

import re

import pytest

from helpers import (
    NOW_TS,
    dim_id_for,
    grant_by_key,
    seed_dataset,
    seed_dim_value,
    seed_dimension,
    seed_grant,
    seed_membership,
    seed_org,
    seed_searchable_doc,
    seed_user,
    val_id_for,
)

from knowledge_lattice.core.docs.acl import AclDeniedError, compile_acl
from knowledge_lattice.store.acl_ast import (
    ColumnRef,
    InValue,
    build_visible_docs_cte_where,
)
from knowledge_lattice.store.sqlite.acl_render import (
    build_where_ast,
    render_select,
    render_sql,
)
from knowledge_lattice.store.sqlite.backend import SqliteBackend

_EVIL_KEY = "x_0) OR 1=1)) --"  # Committer R1 P1-1 攻击示例 key
# 括号数调优变体：在「先有 x 维度绑定 :g_x_0 + 双维度规则」形态下于修复前
# 可静默执行并注释掉全部外层常量（真实跨组织泄露——本文件双组织执行测试复现）
_EVIL_KEY_LEAK = "x_0) OR 1=1))) --"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# 剥除 SQL 字符串字面量（'' 转义处理后）——注释记号不得出现在字面量之外
_OUTSIDE_LITERALS = re.compile(r"'(?:[^']|'')*'")


def _seed_granted_dimension(conn, key: str, user_id: str = "u_full") -> None:
    dim_id = seed_dimension(conn, "org:tax", key)
    val_id = seed_dim_value(conn, dim_id, "A")
    seed_grant(conn, user_id=user_id, dim_id=dim_id, val_id=val_id)


# ============ P1-1①：恶意 param_prefix 构造即拒（fail-closed） ============


def test_invalue_rejects_non_identifier_param_prefix() -> None:
    for evil in (_EVIL_KEY, "ds; DROP TABLE chunks;--", "a b", "1abc", ""):
        with pytest.raises(ValueError, match="InValue.param_prefix"):
            InValue(expr=ColumnRef("je", "value"), param_prefix=evil, values=("A",))
    # 合法标识符照常接受（param_prefix 仅为 trace 标签，不进入 SQL）
    InValue(expr=ColumnRef("je", "value"), param_prefix="dim0", values=("A",))


# ============ P1-1②：恶意维度 key 下常量齐全、参数名全为合法标识符 ============


def test_malicious_dimension_key_cannot_strip_constants(sqlite_matrix) -> None:
    """维度 key 是库内数据（DDL 无字符集约束）：造 x + 恶意 key + zzz 三维度并授权
    （Committer 攻击配方：先有 x 绑定 :g_x_0，再以恶意 key 截断参数名注入注释），
    渲染产物必须仍含全部外层常量、参数名全为合法标识符、注释记号不出现在字面量外。"""
    for key in ("x", _EVIL_KEY, "zzz", "a.b"):
        _seed_granted_dimension(sqlite_matrix, key)
    plan = compile_acl(SqliteBackend(sqlite_matrix), "u_full", "org:tax", now=NOW_TS)
    rules = {r.key: r for r in plan.dimension_rules}
    assert rules[_EVIL_KEY].grants == ("A",)  # 授权展开照常——key 作为数据正常参与

    sql, params = render_select(plan)
    for fragment in ("d.org_id = :org", "c.version = d.active_version", "c.tombstone = 0"):
        assert fragment in sql, fragment  # 外层常量未被截断/注释
    assert params["org"] == "org:tax"
    for name in params:
        assert _IDENTIFIER.fullmatch(name), f"非法参数名: {name!r}"
    # 注释记号（-- 与 /*）不得出现在字符串字面量之外——注入面消除的直接证据
    stripped = _OUTSIDE_LITERALS.sub("''", sql)
    assert "--" not in stripped and "/*" not in stripped
    # 恶意 key 只以转义后的字面量出现（v1.1 CTE：dim.key = '<key>'；无 JSON path）
    assert f"dim.key = '{_EVIL_KEY}'" in sql
    # dot-key（P3-5 消解佐证）：含点 key 同样只以字面量出现、真实执行过滤正确
    assert "dim.key = 'a.b'" in sql
    # 行为照常：恶意/新增维度空值放行，u_full 可见集不变
    assert {r[2] for r in sqlite_matrix.execute(sql, params)} == {
        "d_cn", "d_multi", "d_empty_region", "d_os",
    }


# ============ P1-1③：双组织库真实执行无跨组织行 ============


def test_malicious_key_dual_org_execution_no_cross_org_leak(conn) -> None:
    """双组织库真实执行：org:tax 用户持恶意 key 维度授权，检索只命中 org:tax 文档。
    修复前（本测试形态已实测复现）：恶意 key 截断参数名注入 `) OR 1=1))) --`，
    注释掉 org/版本/tombstone 常量 → org:gl 的空维度文档 d_gl_empty 越权可见。"""
    for org in ("org:tax", "org:gl"):
        seed_org(conn, org)
        seed_dataset(conn, org, f"ds:{org}")
        seed_dimension(conn, org, "region")
        seed_dim_value(conn, dim_id_for(org, "region"), "CN")
        seed_dim_value(conn, dim_id_for(org, "region"), "OS")
    seed_user(conn, "u_tax")
    seed_membership(conn, "u_tax", "org:tax")
    grant_by_key(conn, "u_tax", key="region", value="CN")
    # Committer 攻击配方：先有维度 x（绑定 :g_x_0），再有恶意 key 维度；
    # 顺带 dot-key 维度（P3-5：v1.1 起 key 不进 JSON path——'a.b' 仅字面量）
    _seed_granted_dimension(conn, "x", user_id="u_tax")
    _seed_granted_dimension(conn, _EVIL_KEY_LEAK, user_id="u_tax")
    _seed_granted_dimension(conn, "a.b", user_id="u_tax")
    seed_user(conn, "u_gl_owner")
    seed_membership(conn, "u_gl_owner", "org:gl")
    seed_searchable_doc(
        conn, "d_tax", org_id="org:tax", dataset_id="ds:org:tax", dims={"region": ["CN"]},
        owner_user_id="u_tax",
    )
    seed_searchable_doc(
        conn, "d_gl", org_id="org:gl", dataset_id="ds:org:gl", dims={"region": ["OS"]},
        owner_user_id="u_gl_owner",
    )
    # 空维度文档（region 无值 → 空值模板放行）——org 常量被注释时的越权出口
    seed_searchable_doc(
        conn, "d_gl_empty", org_id="org:gl", dataset_id="ds:org:gl",
        owner_user_id="u_gl_owner",
    )

    plan = compile_acl(SqliteBackend(conn), "u_tax", "org:tax", now=NOW_TS)
    sql, params = render_select(plan)
    rows = {r[2] for r in conn.execute(sql, params)}
    assert rows == {"d_tax"}  # org 隔离成立：恶意 key 维度空值放行、org:gl 文档绝不出现
    assert "dim.key = 'a.b'" in sql and "$." not in sql  # dot-key 无 JSON path 语义


# ============ P2-1：畸形授权行（FK 合法、dimension/value 不匹配）不计入任何维度 ============


def test_malformed_grant_not_counted_in_any_dimension(sqlite_matrix) -> None:
    """region 维度挂 tax_type 的 VAT 取值（FK 合法、归属不匹配）：read_grants 不把
    该行计入任何维度——修复前会展开成 region=("CN","OS","VAT") 造成跨维度取值越权。"""
    sqlite_matrix.execute(
        "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id)"
        " VALUES('u_full', ?, ?)",
        (dim_id_for("org:tax", "region"), val_id_for("org:tax", "tax_type", "VAT")),
    )
    backend = SqliteBackend(sqlite_matrix)
    grants = backend.read_grants("u_full", "org:tax", now=NOW_TS)
    assert grants["region"] == ("CN", "OS")  # 畸形行不计入 region
    assert grants["tax_type"] == ("VAT",)    # 也不计入 tax_type
    # 行为：可见集不变（无越权放宽）
    sql, params = render_select(compile_acl(backend, "u_full", "org:tax", now=NOW_TS))
    assert {r[2] for r in sqlite_matrix.execute(sql, params)} == {
        "d_cn", "d_multi", "d_empty_region", "d_os",
    }


# ============ P3-3：覆盖盲区轻量断言（5 条） ============


def test_now_none_uses_db_clock(sqlite_matrix) -> None:
    """now=None → 库时钟（CURRENT_TIMESTAMP）：过期/有效判定与显式 now 一致
    （PAST_TS=2020 / FUTURE_TS=2099 与真实时钟的关系确定）。"""
    backend = SqliteBackend(sqlite_matrix)
    assert backend.read_grants("u_expired_grant", "org:tax")["region"] == ()  # 过期授权即失效
    assert backend.read_grants("u_full", "org:tax")["region"] == ("CN", "OS")
    with pytest.raises(AclDeniedError):
        compile_acl(backend, "u_expired_member", "org:tax")  # 成员过期（库时钟）
    sql, params = render_select(compile_acl(backend, "u_full", "org:tax"))
    assert {r[2] for r in sqlite_matrix.execute(sql, params)} == {
        "d_cn", "d_multi", "d_empty_region", "d_os",
    }


def test_empty_dataset_or_doc_filter_matches_nothing(sqlite_matrix) -> None:
    """dataset_ids=()/doc_ids=() 空序列 → 恒假（1 = 0）而非 `IN ()`；非空序列照常下推。"""
    backend = SqliteBackend(sqlite_matrix)
    for kwargs in ({"dataset_ids": ()}, {"doc_ids": ()}):
        plan = compile_acl(backend, "u_full", "org:tax", now=NOW_TS, **kwargs)
        sql, params = render_select(plan)
        assert "1 = 0" in sql and "IN ()" not in sql
        assert sqlite_matrix.execute(sql, params).fetchall() == []
    # 正向对照：非空过滤照常下推
    sql, params = render_select(
        compile_acl(backend, "u_full", "org:tax", now=NOW_TS, dataset_ids=("ds:vat_lib",))
    )
    assert {r[2] for r in sqlite_matrix.execute(sql, params)} == {"d_cn", "d_multi", "d_empty_region", "d_os"}
    sql, params = render_select(
        compile_acl(backend, "u_full", "org:tax", now=NOW_TS, doc_ids=("d_cn",))
    )
    assert {r[2] for r in sqlite_matrix.execute(sql, params)} == {"d_cn"}


def test_vector_route_without_embed_model_raises(sqlite_matrix) -> None:
    """向量路缺 embed_model → ValueError（谓词需要 model:dim 标签——D12）；
    基础路渲染不受影响（v1.1：向量路构造走 build_vec_parts）。"""
    from knowledge_lattice.store.acl_ast import build_vec_parts

    plan = compile_acl(SqliteBackend(sqlite_matrix), "u_full", "org:tax", now=NOW_TS)
    with pytest.raises(ValueError, match="embed_model"):
        build_vec_parts(plan)
    assert "embed_model" not in render_sql(build_where_ast(plan))[0]


def test_all_retired_dimensions_empty_plan(sqlite_matrix) -> None:
    """全部维度 retired → 空 Plan（dimension_rules==()）：渲染只剩外层常量、org 内
    全可见（唯一放宽路径的端点形态）；双写法一致。"""
    sqlite_matrix.execute("UPDATE dimensions SET status = 'retired' WHERE org_id = 'org:tax'")
    plan = compile_acl(SqliteBackend(sqlite_matrix), "u_cn", "org:tax", now=NOW_TS)
    assert plan.dimension_rules == ()
    all_docs = {"d_cn", "d_multi", "d_empty_region", "d_cit", "d_os"}
    assert {r[2] for r in sqlite_matrix.execute(*render_select(plan))} == all_docs


def test_dimension_without_values_not_exists_single(sqlite_matrix) -> None:
    """零取值维度（无任何 dimension_values 行）：授权集恒空 → NotExists 单条件，
    存量文档零消失。"""
    seed_dimension(sqlite_matrix, "org:tax", "novalue_dim")
    backend = SqliteBackend(sqlite_matrix)
    plan = compile_acl(backend, "u_full", "org:tax", now=NOW_TS)
    rules = {r.key: r for r in plan.dimension_rules}
    assert rules["novalue_dim"].is_empty
    from knowledge_lattice.store.acl_ast import build_visible_docs_rule_ast
    assert render_sql(build_visible_docs_rule_ast(rules["novalue_dim"], "org:tax"))[0] == (
        "NOT EXISTS (SELECT 1 FROM document_dimensions AS dd"
        " JOIN dimensions AS dim ON dim.id = dd.dimension_id"
        " WHERE dd.doc_id = d.id AND dim.key = 'novalue_dim' AND dim.org_id = :org)"
    )
    sql, params = render_select(plan)
    assert {r[2] for r in sqlite_matrix.execute(sql, params)} == {
        "d_cn", "d_multi", "d_empty_region", "d_os",
    }
