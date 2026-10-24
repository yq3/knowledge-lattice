"""TC-ACL-05 第 0 步成员关系校验【单测｜M0a→M0b 双后端】。

无 membership（含系统管理员——豁免仅限管理端点，检索路径同样拒绝，D22）/
membership expires_at=昨天 / 他组织成员 → 编译入口即拒绝（403 语义），不产出
WHERE；membership 有效 → 正常产出 Plan。
"""

from __future__ import annotations

import pytest

from helpers import NOW_TS

from knowledge_lattice.core.docs.acl import AclDeniedError


def test_no_membership_rejected(matrix) -> None:
    """无 membership 行 → 拒绝；系统管理员身份不豁免（D22——豁免仅限管理端点）。"""
    assert matrix.execute(
        "SELECT count(*) FROM user_org_memberships WHERE user_id = 'sysadmin'"
    ).fetchone()[0] == 0
    with pytest.raises(AclDeniedError, match="no active membership"):
        matrix.compile_acl("sysadmin", "org:tax", now=NOW_TS)


def test_expired_membership_rejected(matrix) -> None:
    """membership expires_at=昨天（造数 PAST_TS）→ 编译入口拒绝，不产出 WHERE。"""
    with pytest.raises(AclDeniedError, match="no active membership"):
        matrix.compile_acl("u_expired_member", "org:tax", now=NOW_TS)


def test_other_org_membership_rejected(matrix) -> None:
    """仅属 org:gl 的成员对 org:tax 编译 → 拒绝（组织上下文与成员关系一致）。"""
    with pytest.raises(AclDeniedError):
        matrix.compile_acl("u_gl", "org:tax", now=NOW_TS)


def test_valid_membership_compiles(matrix) -> None:
    """membership 有效 → 正常产出 Plan（第 0 步放行后才展开授权）。"""
    plan = matrix.compile_acl("u_full", "org:tax", now=NOW_TS)
    assert plan.org_id == "org:tax"
    assert [r.key for r in plan.dimension_rules] == ["region", "tax_type"]


def test_org_admin_member_compiles_no_exemption_semantics(matrix) -> None:
    """org_admin 但无维度授权：编译正常（成员关系有效）——检索路径只有维度 ACL
    一种语义（#34 必修 2——无 owner/角色放宽分支），其可见集=全维度空值文档。"""
    plan = matrix.compile_acl("admin_tax", "org:tax", now=NOW_TS)
    assert all(r.is_empty for r in plan.dimension_rules)
    sql, params = matrix.render_select(plan)
    assert {r[2] for r in matrix.execute(sql, params)} == {"d_empty_region"}
