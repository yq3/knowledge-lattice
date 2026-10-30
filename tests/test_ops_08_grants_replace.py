"""TC-OPS-08 members grants 全量替换【集成｜M2】（m2-3 A 组）。

原文（TEST-CASES L504-507）：
- 步骤：`PUT /api/orgs/{org}/members/{id}/grants` 替换 u1 的 local 授权，
  u1 另有 sync 授权。
- 预期：仅 local 授权被替换，sync 不动（§6.2 端点语义）；支持 expires_at；
  审计入 outbox。

双后端参数化（[sqlite]/[pg]）；REST 端点用例为 sqlite（app_env 惯例）。
"""

from __future__ import annotations

import json

import pytest

from conftest import ORG


def test_replace_local_grants_keeps_sync_and_supports_expires(matrix) -> None:
    """TC-OPS-08 主断言：u1 有 local（region CN/OS + tax_type VAT）+ sync
    （region CN via sync:hr）授权；全量替换 local=[region=OS, tax_type=CIT
    (expires_at)]——local 全换、sync 原样、expires_at 落列；审计入 outbox。"""
    from knowledge_lattice.domain.audit_events import EVENT_GRANTS_REPLACE

    backend = matrix.make_backend()
    # sync 授权造数（source='sync:hr'——同步适配器写入形态；取 u_cn 未持有
    # 的 tax_type=VAT，避免与既有 local 行 PK 冲突）
    matrix.execute(
        "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id, source,"
        " synced_at) VALUES('u_cn', ?, ?, 'sync:hr', CURRENT_TIMESTAMP)",
        ("dim:org:tax:tax_type", "val:dim:org:tax:tax_type:VAT"),
    )
    audit = (EVENT_GRANTS_REPLACE, json.dumps(
        {"org_id": ORG, "user_id": "u_cn", "actor": "admin_tax"}, ensure_ascii=False))

    result = backend.replace_local_grants(
        ORG, "u_cn",
        [("region", "OS", None), ("tax_type", "CIT", "2027-06-30 00:00:00")],
        audit=audit,
    )
    assert result == {"removed": 1, "inserted": 2}  # local 的 region=CN 被删

    rows = matrix.execute(
        "SELECT d.key, v.value, g.source, g.expires_at"
        " FROM user_dimension_grants g"
        " JOIN dimensions d ON d.id = g.dimension_id"
        " JOIN dimension_values v ON v.id = g.value_id"
        " WHERE g.user_id = 'u_cn' ORDER BY d.key, v.value, g.source"
    ).fetchall()

    def _norm(rows):
        # pg 臂 TIMESTAMP 列读出 datetime——归一化为与 sqlite 同形的字符串
        return [
            (k, v, s, e.strftime("%Y-%m-%d %H:%M:%S") if hasattr(e, "strftime") else e)
            for k, v, s, e in rows
        ]

    assert _norm(rows) == [
        ("region", "OS", "local", None),             # local 新行
        ("tax_type", "CIT", "local", "2027-06-30 00:00:00"),  # expires_at 落列
        ("tax_type", "VAT", "sync:hr", None),        # sync 不动（T-CSV 主断言同源）
    ]
    # 授权展开即时生效（读路径过滤）
    grants = backend.read_grants("u_cn", ORG)
    assert grants["region"] == ("OS",)
    assert grants["tax_type"] == ("CIT", "VAT")  # local CIT + sync VAT 并存
    # 审计入 outbox
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'grants.replace'"
    ).fetchone()[0] == 1


def test_replace_local_grants_idempotent_and_empty(matrix) -> None:
    """幂等：同一目标态二跑零变化；空清单=清空该用户全部 local（sync 保留）。"""
    backend = matrix.make_backend()
    matrix.execute(
        "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id, source)"
        " VALUES('u_cn', ?, ?, 'sync:hr')",
        ("dim:org:tax:tax_type", "val:dim:org:tax:tax_type:VAT"),
    )
    target = [("region", "OS", None)]
    first = backend.replace_local_grants(ORG, "u_cn", target)
    second = backend.replace_local_grants(ORG, "u_cn", target)  # 幂等二跑
    # 全量替换机制：先删后插（removed/inserted 为机制计数非 diff）；幂等性由
    # **数据不变**断言承载
    assert second == {"removed": 1, "inserted": 1}
    assert backend.read_grants("u_cn", ORG)["region"] == ("OS",)

    # 空清单 = 清空 local（sync 保留）
    cleared = backend.replace_local_grants(ORG, "u_cn", [])
    assert cleared == {"removed": 1, "inserted": 0}
    assert backend.read_grants("u_cn", ORG)["region"] == ()  # local 已清
    assert backend.read_grants("u_cn", ORG)["tax_type"] == ("VAT",)  # sync 保留


def test_replace_local_grants_invalid_target(matrix) -> None:
    """非法 (dim_key, value) → KeyError（400 语义）；他组织维度同拒。"""
    backend = matrix.make_backend()
    with pytest.raises(KeyError):
        backend.replace_local_grants(ORG, "u_cn", [("region", "NOPE", None)])
    with pytest.raises(KeyError):
        backend.replace_local_grants(ORG, "u_cn", [("no_dim", "CN", None)])
    # 失败零写入（原授权保留）
    assert backend.read_grants("u_cn", ORG)["region"] == ("CN",)


def test_api_replace_grants_flow(app_env) -> None:
    """REST 端点：org_admin 替换 → 200；非 org_admin → 403；目标用户无成员
    关系 → 400（防孤儿）；非法取值 → 400；审计入 outbox。"""
    from helpers import seed_membership, seed_user
    from knowledge_lattice.domain.auth import hash_token

    client, conn = app_env["client"], app_env["conn"]
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = 'admin_tax'",
        (hash_token("dev-static-admin-tax"),),
    )
    conn.commit()
    admin = {"Authorization": "Bearer dev-static-admin-tax"}
    member = {"Authorization": f"Bearer {app_env['static']['u_full']}"}

    # 非 org_admin → 403
    r = client.put(
        "/api/orgs/org:tax/members/u_cn/grants",
        headers=member,
        json={"grants": [{"dim_key": "region", "value": "OS"}]},
    )
    assert r.status_code == 403

    # 无成员关系目标 → 400（防孤儿授权）
    r = client.put(
        "/api/orgs/org:tax/members/u_nope/grants",
        headers=admin, json={"grants": []},
    )
    assert r.status_code == 400 and "成员关系" in r.json()["detail"]

    # 非法取值 → 400
    r = client.put(
        "/api/orgs/org:tax/members/u_cn/grants",
        headers=admin,
        json={"grants": [{"dim_key": "region", "value": "NOPE"}]},
    )
    assert r.status_code == 400

    # 正常替换（u_cn 原仅 local region=CN → 全量替换为 OS + expires_at）
    r = client.put(
        "/api/orgs/org:tax/members/u_cn/grants",
        headers=admin,
        json={"grants": [
            {"dim_key": "region", "value": "OS", "expires_at": "2027-01-31 00:00:00"},
        ]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"removed": 1, "inserted": 1}
    assert conn.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'grants.replace'"
    ).fetchone()[0] == 1
    # sync 授权不动（造一行对照）
    conn.execute(
        "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id, source)"
        " VALUES('u_cn', 'dim:org:tax:region', 'val:dim:org:tax:region:CN', 'sync:hr')"
    )
    conn.commit()
    r = client.put(
        "/api/orgs/org:tax/members/u_cn/grants",
        headers=admin, json={"grants": []},  # 清空 local
    )
    assert r.status_code == 200 and r.json() == {"removed": 1, "inserted": 0}
    assert conn.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'u_cn'"
        " AND source = 'sync:hr'"
    ).fetchone()[0] == 1


# ============ m2-3 R2：P2-1/P2-2 PUT 面 ============


def test_api_put_grants_duplicate_rows_rejected(app_env) -> None:
    """P2-1（PUT 面）：同 (dim_key,value) 重复行 → 400（先删后插 PK 冲突的
    500 根除）；缺 dim_key/value 键 → 422（pydantic 校验，非 500）。"""
    from helpers import seed_membership, seed_user
    from knowledge_lattice.domain.auth import hash_token

    client, conn = app_env["client"], app_env["conn"]
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = 'admin_tax'",
        (hash_token("dev-static-admin-tax"),),
    )
    conn.commit()
    admin = {"Authorization": "Bearer dev-static-admin-tax"}

    # 重复行 → 400
    r = client.put(
        "/api/orgs/org:tax/members/u_cn/grants",
        headers=admin,
        json={"grants": [
            {"dim_key": "region", "value": "OS"},
            {"dim_key": "region", "value": "OS"},  # PK 冲突形态
        ]},
    )
    assert r.status_code == 400
    assert "重复" in r.json()["detail"] or "duplicate" in r.json()["detail"].lower()

    # 缺键 → 422（pydantic 校验——修复前 KeyError 500）
    r = client.put(
        "/api/orgs/org:tax/members/u_cn/grants",
        headers=admin, json={"grants": [{"dim_key": "region"}]},
    )
    assert r.status_code == 422
    r = client.put(
        "/api/orgs/org:tax/members/u_cn/grants",
        headers=admin, json={"grants": [{"value": "OS"}]},
    )
    assert r.status_code == 422
    # 原授权未被破坏（失败零写入）
    assert conn.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'u_cn'"
        " AND source = 'local'"
    ).fetchone()[0] == 1


def test_api_put_grants_invalid_expires_rejected(app_env) -> None:
    """P2-2（PUT 面）：非法 expires_at → 400（sqlite 静默 fail-open 根除：
    修复前非法串原样写列、字符串比较恒真=临时授权永久化）。"""
    from helpers import seed_membership, seed_user
    from knowledge_lattice.domain.auth import hash_token

    client, conn = app_env["client"], app_env["conn"]
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = 'admin_tax'",
        (hash_token("dev-static-admin-tax"),),
    )
    conn.commit()
    admin = {"Authorization": "Bearer dev-static-admin-tax"}

    for bad in ("abc", "forever", "2027-02-30 00:00:00"):
        r = client.put(
            "/api/orgs/org:tax/members/u_cn/grants",
            headers=admin,
            json={"grants": [
                {"dim_key": "region", "value": "OS", "expires_at": bad},
            ]},
        )
        assert r.status_code == 400, f"{bad!r} 应被拒绝"
        assert bad in r.json()["detail"]
    assert conn.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'u_cn'"
        " AND source = 'local' AND value_id = 'val:dim:org:tax:region:OS'"
    ).fetchone()[0] == 0, "非法串不得入列"
