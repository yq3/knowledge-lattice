"""TC-SCAF-05 成员关系删除级联清授权【单测｜M0a→M0b 双后端】。

删除 org:tax membership → 该组织维度授权全清（含 source='sync:…'——#33 P0-1⑥）；
org:gl 授权不受影响（触发器按 dimensions.org_id 收敛，design §4；PG 侧为同款
plpgsql 触发器——分区/触发器等价，v1.4 后端行）。
"""

from __future__ import annotations

from helpers import (
    seed_dim_value,
    seed_dimension,
    seed_grant,
    seed_membership,
    seed_org,
    seed_user,
)


def _remaining_grants(db) -> list[tuple[str, str, str]]:
    return db.execute(
        "SELECT user_id, dimension_id, value_id FROM user_dimension_grants"
        " ORDER BY dimension_id, value_id"
    ).fetchall()


def test_membership_delete_cleans_org_scoped_grants(backend) -> None:
    seed_org(backend, "org:tax")
    seed_org(backend, "org:gl")
    seed_user(backend, "u1")
    seed_membership(backend, "u1", "org:tax")
    seed_membership(backend, "u1", "org:gl")

    region = seed_dimension(backend, org_id="org:tax", key="region")
    region_cn = seed_dim_value(backend, region, value="CN")
    region_os = seed_dim_value(backend, region, value="OS")
    gl_kind = seed_dimension(backend, org_id="org:gl", key="gl_kind")
    gl_val = seed_dim_value(backend, gl_kind, value="X")

    # org:tax 两笔授权（local + sync:hr——PK 为 user×dim×value，各占不同取值行）+ org:gl 一笔
    seed_grant(backend, "u1", region, region_cn, source="local")
    seed_grant(backend, "u1", region, region_os, source="sync:hr")
    seed_grant(backend, "u1", gl_kind, gl_val, source="local")

    backend.execute(
        "DELETE FROM user_org_memberships WHERE user_id='u1' AND org_id='org:tax'"
    )

    # tax 维度授权全清（含 sync 来源）；gl 授权不动
    assert _remaining_grants(backend) == [("u1", gl_kind, gl_val)]


def test_membership_delete_keeps_other_users_grants(backend) -> None:
    seed_org(backend, "org:tax")
    seed_user(backend, "u1")
    seed_user(backend, "u2")
    seed_membership(backend, "u1", "org:tax")
    seed_membership(backend, "u2", "org:tax")
    region = seed_dimension(backend, org_id="org:tax", key="region")
    region_cn = seed_dim_value(backend, region, value="CN")
    seed_grant(backend, "u1", region, region_cn)
    seed_grant(backend, "u2", region, region_cn)

    backend.execute(
        "DELETE FROM user_org_memberships WHERE user_id='u1' AND org_id='org:tax'"
    )

    # 触发器按 OLD.user_id 收敛：只清 u1，u2 保留
    assert _remaining_grants(backend) == [("u2", region, region_cn)]
