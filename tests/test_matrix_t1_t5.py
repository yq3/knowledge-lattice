"""越权矩阵 T1~T5 的 M0a 编译器单测先行形态（design §8 M0a.5——M1 矩阵复跑）。

在真实 SQLite 库上执行编译产物 SQL 断言可见性（不依赖 M0a-3 检索管线）。
T1 过期授权清理未跑仍不可见 / T2 成员续期不复活旧授权（行为半句——触发器半句
M0a-1 T23 已覆盖）/ T3 停用取值收紧 / T4 维度改可选/停用不放宽 / T5 可选维度
有值则过滤。
"""

from __future__ import annotations

import pytest

from helpers import NOW_TS, seed_membership

from knowledge_lattice.core.docs.acl import AclDeniedError, compile_acl
from knowledge_lattice.store.sqlite.acl_render import render_select
from knowledge_lattice.store.sqlite.backend import SqliteBackend


def _visible(matrix, user_id: str) -> set[str]:
    sql, params = render_select(
        compile_acl(SqliteBackend(matrix), user_id, "org:tax", now=NOW_TS)
    )
    return {r[2] for r in matrix.execute(sql, params)}


def test_t1_expired_grant_invisible_without_cleanup(matrix) -> None:
    """T1：过期授权（expires_at=昨天）清理任务从未运行仍不可见——展开 SQL 以
    `expires_at > :now` 过滤该行，CN 不在授权集；d_cn 不可见、d_empty_region 可见。"""
    backend = SqliteBackend(matrix)
    grants = backend.read_grants("u_expired_grant", "org:tax", now=NOW_TS)
    assert grants == {"region": (), "tax_type": ("VAT",)}  # CN 被过期过滤（隔离单因对照：VAT 仍在）
    # 清理任务从未运行：过期授权行仍在库内（不可见 ≠ 已删除）
    assert matrix.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'u_expired_grant'"
    ).fetchone()[0] == 2
    # region 零授权 → 只见 region 空值文档（d_empty_region；d_cn/d_multi/d_os 均有 region 值）
    assert _visible(matrix, "u_expired_grant") == {"d_empty_region"}


def test_t2_membership_renewal_does_not_revive_old_grants(matrix) -> None:
    """T2（行为半句）：① 过期期间检索 → 第 0 步拒绝；② DELETE membership 再重插
    （续期禁令下唯一路径）；③ 重插后授权集为空（级联清理）、d_cn 不可见。"""
    backend = SqliteBackend(matrix)
    with pytest.raises(AclDeniedError):  # ① 成员关系过期 → 编译入口拒绝
        compile_acl(backend, "u_expired_member", "org:tax", now=NOW_TS)
    # ② 恢复访问：先删再插
    matrix.execute("DELETE FROM user_org_memberships WHERE user_id = 'u_expired_member'")
    seed_membership(matrix, "u_expired_member", "org:tax")
    # ③ 触发器级联已清授权——重插后授权集为空，旧授权不复活
    assert backend.read_grants("u_expired_member", "org:tax", now=NOW_TS) == {
        "region": (),
        "tax_type": (),
    }
    assert matrix.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'u_expired_member'"
    ).fetchone()[0] == 0
    assert _visible(matrix, "u_expired_member") == {"d_empty_region"}  # d_cn 不可见


def test_t3_disabled_value_tightens(matrix) -> None:
    """T3：取值 OS 停用（disabled）→ 视为「存在但无人被授予」——u_full 授权集变
    [CN]，d_os 不可见；d_cn/d_multi 仍可见（收紧而非放宽，D19）。"""
    assert _visible(matrix, "u_full") == {"d_cn", "d_multi", "d_empty_region", "d_os"}
    # M0a 单测形态：直接 UPDATE（PATCH dry_run+确认属 M1 管理面）
    matrix.execute(
        "UPDATE dimension_values SET status = 'disabled'"
        " WHERE value = 'OS' AND dimension_id = (SELECT id FROM dimensions"
        "   WHERE org_id = 'org:tax' AND key = 'region')"
    )
    grants = SqliteBackend(matrix).read_grants("u_full", "org:tax", now=NOW_TS)
    assert grants["region"] == ("CN",)  # 授权集变 [CN]
    assert _visible(matrix, "u_full") == {"d_cn", "d_multi", "d_empty_region"}


def test_t4_optional_or_disabled_dimension_no_relax(matrix) -> None:
    """T4：region 分别 UPDATE required 1→0、enabled 1→0 → 产物逐字不变
    （生命周期与过滤解耦——D5；TC-ACL-04 的矩阵断言形态）。"""
    before = render_select(compile_acl(SqliteBackend(matrix), "u_cn", "org:tax", now=NOW_TS))
    for column in ("required", "enabled"):
        matrix.execute(
            f"UPDATE dimensions SET {column} = 0 WHERE org_id = 'org:tax' AND key = 'region'"
        )
        assert render_select(
            compile_acl(SqliteBackend(matrix), "u_cn", "org:tax", now=NOW_TS)
        ) == before  # 产物逐字不变（SQL 文本 + 参数）
        assert _visible(matrix, "u_cn") == {"d_multi", "d_empty_region"}  # 可见性不变
        matrix.execute(
            f"UPDATE dimensions SET {column} = 1 WHERE org_id = 'org:tax' AND key = 'region'"
        )


def test_t5_optional_dimension_valued_still_filters(matrix) -> None:
    """T5：tax_type 可选（required=0）、u_cn 无 tax_type 授权 → d_cit（tax_type=[CIT]）
    不可见（有值→需交集，空交集=不可见）；d_empty_region 可见（无值放行）——
    可选性不影响过滤语义。"""
    assert matrix.execute(
        "SELECT required FROM dimensions WHERE org_id = 'org:tax' AND key = 'tax_type'"
    ).fetchone()[0] == 0
    visible = _visible(matrix, "u_cn")
    assert "d_cit" not in visible
    assert "d_empty_region" in visible
    assert visible == {"d_multi", "d_empty_region"}
