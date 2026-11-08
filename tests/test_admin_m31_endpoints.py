"""m3-1 A/C 组：design §6.2 五方法组合实装 + GET 单维度/单取值 + sem_restricted
授予入口（issue #13 / G-24①——双后端 REST 端到端参数化）。

A 组（issue #13——§6.2 列明但实现缺失的 5 方法 + 连带只读 2 端点）：
- GET /api/orgs/{org}/members：成员列表（含 expires_at；**org_admin 门控**，
  org_scoped——过期成员行如实列出，过滤语义归权限计算）；
- POST /api/orgs/{org}/datasets：{key, title?}——组织内 key 冲突 409、初始空库、
  dataset.created 审计同事务；
- PATCH /api/orgs/{org}/datasets/{id}：title/description 修改（key 不可改——
  引用锚点）+ dataset.updated 审计；404 不存在/跨组织；
- POST /api/orgs/{org}/dimensions：{key, label}——key 冲突 409、默认
  enabled=true/required=false（D5：required 仅影响上传）、dimension.created 审计；
- PATCH /api/orgs/{org}/dimensions/{id}：label/required/enabled 修改
  （enabled/required 仅影响上传不影响过滤——D5 v0.4；**status 仍由退役端点管理**
  ——PATCH status=retired → 400）；retired 维度 PATCH → 409（values create/enable
  先例对称）；dimension.updated 审计；
- GET /api/orgs/{org}/dimensions/{id}：单维度只读（含 status——retired 如实展示）；
- GET /api/orgs/{org}/dimensions/{id}/values：取值列表（含 disabled——管理面
  对账；行含 status）；
- GET /api/orgs/{org}/dimensions/{id}/values/{value_id}：单取值只读。

C 组（G-24①——sem_restricted 管理面授予入口）：members 写路径 role 枚举扩展
（POST/PATCH 允许 role='sem_restricted'——单值列天然不兼任 org_admin，
T-S9 既有口径；唯一 active org_admin 守卫兼容：降级 sem_restricted 同守卫 409）。
"""

from __future__ import annotations

import json

import pytest

from conftest import ORG, ORG_GL
from helpers import dim_id_for, val_id_for

pytestmark = pytest.mark.usefixtures("rest_env")


def _hdr(env, uid: str) -> dict:
    return {"Authorization": f"Bearer {env['tokens'][uid]}"}


def _outbox_types(env, prefix: str) -> list[dict]:
    order = "rowid" if env["db"].name == "sqlite" else "created_at"
    rows = env["db"].execute(
        "SELECT event_type, payload_json FROM audit_outbox"
        f" WHERE event_type LIKE ? ORDER BY {order}",
        (f"{prefix}%",),
    ).fetchall()
    return [
        {"event_type": r[0], "payload": json.loads(r[1])} for r in rows
    ]


# ============ A1：GET members（org_admin 门控 + 含过期行） ============


def test_a1_members_list_org_admin_gate(rest_env) -> None:
    """GET members：org_admin 200（行含 user_id/username/role/expires_at——过期行
    如实列出）；member 403；跨组织 403（org_admin 门控沿 FR-4 操作矩阵）。"""
    client, env = rest_env["client"], rest_env
    r = client.get(f"/api/orgs/{ORG}/members", headers=_hdr(env, "admin_tax"))
    assert r.status_code == 200, r.text
    members = r.json()["members"]
    by_uid = {m["user_id"]: m for m in members}
    # 矩阵造数：u_full（member 永久）、u_expired_member（过期行如实列出）
    assert "u_full" in by_uid and "u_expired_member" in by_uid
    assert by_uid["u_full"]["role"] == "member"
    assert by_uid["u_full"]["expires_at"] is None
    assert by_uid["u_expired_member"]["expires_at"] is not None  # 过期行保留展示
    assert by_uid["admin_tax"]["role"] == "org_admin"
    for m in members:
        assert {"user_id", "username", "role", "expires_at"} <= set(m)

    # member 门控 403 / 跨组织 403
    assert client.get(
        f"/api/orgs/{ORG}/members", headers=_hdr(env, "u_full")
    ).status_code == 403
    assert client.get(
        f"/api/orgs/{ORG}/members", headers=_hdr(env, "u_gl")
    ).status_code == 403


# ============ A2/A3：datasets POST / PATCH ============


def test_a2_post_dataset_conflict_audit(rest_env) -> None:
    """POST datasets：201 初始空库；组织内 key 冲突 409；member 403；
    dataset.created 审计同事务入 outbox。"""
    client, env = rest_env["client"], rest_env
    r = client.post(
        f"/api/orgs/{ORG}/datasets", headers=_hdr(env, "admin_tax"),
        json={"key": "ds:new_lib", "title": "新制度库"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == "ds:new_lib" and body["name"] == "新制度库"
    # 初始空库：GET datasets 列出 + 库内零文档
    listed = client.get(
        f"/api/orgs/{ORG}/datasets", headers=_hdr(env, "u_full")
    ).json()["datasets"]
    assert "ds:new_lib" in [d["id"] for d in listed]
    docs = env["db"].execute(
        "SELECT count(*) FROM documents WHERE dataset_id = ?", ("ds:new_lib",)
    ).fetchone()[0]
    assert docs == 0, "新建库必须初始为空"

    # key 冲突 409
    r2 = client.post(
        f"/api/orgs/{ORG}/datasets", headers=_hdr(env, "admin_tax"),
        json={"key": "ds:new_lib"},
    )
    assert r2.status_code == 409, r2.text
    # 空 key 400
    assert client.post(
        f"/api/orgs/{ORG}/datasets", headers=_hdr(env, "admin_tax"),
        json={"key": "  "},
    ).status_code == 400
    # member 403（org_admin 门控）
    assert client.post(
        f"/api/orgs/{ORG}/datasets", headers=_hdr(env, "u_full"),
        json={"key": "ds:other"},
    ).status_code == 403
    # 审计
    events = _outbox_types(env, "dataset.created")
    assert events and events[-1]["payload"].get("dataset_id") == "ds:new_lib"


def test_a3_patch_dataset_title_description(rest_env) -> None:
    """PATCH datasets/{id}：title/description 修改 + dataset.updated 审计；
    不存在/跨组织 404；member 403。"""
    client, env = rest_env["client"], rest_env
    r = client.patch(
        f"/api/orgs/{ORG}/datasets/ds:vat_lib", headers=_hdr(env, "admin_tax"),
        json={"title": "VAT 实务库（改名）", "description": "2026 口径"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "VAT 实务库（改名）"
    row = env["db"].execute(
        "SELECT name, description FROM datasets WHERE id = ?", ("ds:vat_lib",)
    ).fetchone()
    assert row[0] == "VAT 实务库（改名）" and row[1] == "2026 口径"

    # 不存在 404 / member 403
    assert client.patch(
        f"/api/orgs/{ORG}/datasets/ds:none", headers=_hdr(env, "admin_tax"),
        json={"title": "x"},
    ).status_code == 404
    assert client.patch(
        f"/api/orgs/{ORG}/datasets/ds:vat_lib", headers=_hdr(env, "u_full"),
        json={"title": "x"},
    ).status_code == 403
    # 跨组织 404：org:gl 自有库 id 在 org:tax 路径
    env["db"].execute(
        "INSERT INTO datasets(id, org_id, name) VALUES(?, ?, ?)",
        ("ds:gl_lib", ORG_GL, "库 ds:gl_lib"),
    )
    env["db"].commit()
    assert client.patch(
        f"/api/orgs/{ORG}/datasets/ds:gl_lib", headers=_hdr(env, "admin_tax"),
        json={"title": "x"},
    ).status_code == 404

    events = _outbox_types(env, "dataset.updated")
    assert events and events[-1]["payload"].get("dataset_id") == "ds:vat_lib"


# ============ A4/A5：dimensions POST / PATCH ============


def test_a4_post_dimension_defaults_conflict(rest_env) -> None:
    """POST dimensions：{key, label} 201——默认 enabled=true/required=false
    （D5：required 仅影响上传）；key 冲突 409；member 403；
    dimension.created 审计。"""
    client, env = rest_env["client"], rest_env
    r = client.post(
        f"/api/orgs/{ORG}/dimensions", headers=_hdr(env, "admin_tax"),
        json={"key": "channel", "label": "业务渠道"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["key"] == "channel" and body["name"] == "业务渠道"
    assert body["enabled"] is True and body["required"] is False
    assert body["status"] == "active"
    row = env["db"].execute(
        "SELECT enabled, required FROM dimensions WHERE org_id = ? AND key = ?",
        (ORG, "channel"),
    ).fetchone()
    assert row == (1, 0), f"默认 enabled=true/required=false（got {row}）"

    # key 冲突 409（UNIQUE(org_id, key)）
    assert client.post(
        f"/api/orgs/{ORG}/dimensions", headers=_hdr(env, "admin_tax"),
        json={"key": "channel", "label": "重复"},
    ).status_code == 409
    # region 既有 key 同样 409
    assert client.post(
        f"/api/orgs/{ORG}/dimensions", headers=_hdr(env, "admin_tax"),
        json={"key": "region", "label": "重复"},
    ).status_code == 409
    # 空 key/label 400
    assert client.post(
        f"/api/orgs/{ORG}/dimensions", headers=_hdr(env, "admin_tax"),
        json={"key": " ", "label": "x"},
    ).status_code == 400
    # member 403
    assert client.post(
        f"/api/orgs/{ORG}/dimensions", headers=_hdr(env, "u_full"),
        json={"key": "d2", "label": "x"},
    ).status_code == 403
    events = _outbox_types(env, "dimension.created")
    assert events and events[-1]["payload"].get("key") == "channel"


def test_a5_patch_dimension_governance_boundaries(rest_env) -> None:
    """PATCH dimensions/{id}：label/required/enabled 修改 + 审计；**status 由
    退役端点管理**（PATCH status → 400）；retired 维度 → 409（对称先例）；
    不存在/跨组织 404。"""
    client, env = rest_env["client"], rest_env
    dim = dim_id_for(ORG, "region")
    r = client.patch(
        f"/api/orgs/{ORG}/dimensions/{dim}", headers=_hdr(env, "admin_tax"),
        json={"label": "作业区域（全球）", "required": False, "enabled": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "作业区域（全球）"
    assert body["required"] is False and body["enabled"] is False
    # 行为面：required/enabled 仅影响上传不影响过滤——read_grants 仍含 region
    grants = env["backend"].read_grants("u_cn", ORG)
    assert grants.get("region") == ("CN",), "enabled=false 不得影响过滤（D5）"

    # status 载体归退役端点：PATCH status → 400
    assert client.patch(
        f"/api/orgs/{ORG}/dimensions/{dim}", headers=_hdr(env, "admin_tax"),
        json={"status": "retired"},
    ).status_code == 400
    # 不存在 404 / member 403
    assert client.patch(
        f"/api/orgs/{ORG}/dimensions/dim:none", headers=_hdr(env, "admin_tax"),
        json={"label": "x"},
    ).status_code == 404
    assert client.patch(
        f"/api/orgs/{ORG}/dimensions/{dim}", headers=_hdr(env, "u_full"),
        json={"label": "x"},
    ).status_code == 403
    # retired 维度 PATCH → 409（生命周期终态不复活——values create/enable 对称）
    env["db"].execute(
        "UPDATE dimensions SET status = 'retired' WHERE org_id = ? AND key = ?",
        (ORG, "tax_type"),
    )
    env["db"].commit()
    assert client.patch(
        f"/api/orgs/{ORG}/dimensions/{dim_id_for(ORG, 'tax_type')}",
        headers=_hdr(env, "admin_tax"), json={"label": "x"},
    ).status_code == 409

    events = _outbox_types(env, "dimension.updated")
    assert events and events[-1]["payload"].get("dimension_id") == dim


# ============ A6/A7/A8：单维度 / 取值列表 / 单取值（只读） ============


def test_a6_get_single_dimension(rest_env) -> None:
    """GET dimensions/{id}：单维度行（含 status；成员可读——GET /dimensions
    同读面）；不存在/跨组织 404；retired 如实展示。"""
    client, env = rest_env["client"], rest_env
    dim = dim_id_for(ORG, "region")
    r = client.get(f"/api/orgs/{ORG}/dimensions/{dim}", headers=_hdr(env, "u_full"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == dim and body["key"] == "region"
    assert body["status"] == "active"
    assert {"id", "key", "name", "required", "enabled", "status"} <= set(body)

    assert client.get(
        f"/api/orgs/{ORG}/dimensions/dim:none", headers=_hdr(env, "u_full")
    ).status_code == 404
    # 跨组织维度 id → 404（org:gl 的 dim 在 org:tax 路径——存在性敏感）
    env["db"].execute(
        "INSERT INTO dimensions(id, org_id, key, name) VALUES(?, ?, ?, ?)",
        (dim_id_for(ORG_GL, "region"), ORG_GL, "region", "region"),
    )
    env["db"].commit()
    assert client.get(
        f"/api/orgs/{ORG}/dimensions/{dim_id_for(ORG_GL, 'region')}",
        headers=_hdr(env, "u_full"),
    ).status_code == 404
    # retired 如实展示（只读不裁定）
    env["db"].execute(
        "UPDATE dimensions SET status = 'retired' WHERE org_id = ? AND key = ?",
        (ORG, "tax_type"),
    )
    env["db"].commit()
    r2 = client.get(
        f"/api/orgs/{ORG}/dimensions/{dim_id_for(ORG, 'tax_type')}",
        headers=_hdr(env, "u_full"),
    )
    assert r2.status_code == 200 and r2.json()["status"] == "retired"


def test_a7_values_list_includes_disabled(rest_env) -> None:
    """GET dimensions/{id}/values：取值列表含 disabled（管理面对账——重新启用
    恢复路径的数据面）；行含 status；维度不存在 404。"""
    client, env = rest_env["client"], rest_env
    dim = dim_id_for(ORG, "region")
    # 造一个 disabled 取值（D19 软停用）
    env["db"].execute(
        "INSERT INTO dimension_values(id, dimension_id, value, label, status)"
        " VALUES(?, ?, ?, ?, 'disabled')",
        (val_id_for(ORG, "region", "EU"), dim, "EU", "欧洲区"),
    )
    env["db"].commit()
    r = client.get(
        f"/api/orgs/{ORG}/dimensions/{dim}/values", headers=_hdr(env, "u_full")
    )
    assert r.status_code == 200, r.text
    values = {v["value"]: v for v in r.json()["values"]}
    assert set(values) == {"CN", "OS", "EU"}
    assert values["CN"]["status"] == "active"
    assert values["EU"]["status"] == "disabled"
    for v in values.values():
        assert {"id", "value", "label", "status"} <= set(v)

    assert client.get(
        f"/api/orgs/{ORG}/dimensions/dim:none/values",
        headers=_hdr(env, "u_full"),
    ).status_code == 404


def test_a8_get_single_value(rest_env) -> None:
    """GET dimensions/{id}/values/{value_id}：单取值行；值不存在 404；
    维度不存在 404。"""
    client, env = rest_env["client"], rest_env
    dim = dim_id_for(ORG, "region")
    val = val_id_for(ORG, "region", "CN")
    r = client.get(
        f"/api/orgs/{ORG}/dimensions/{dim}/values/{val}",
        headers=_hdr(env, "u_full"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == val and body["value"] == "CN"
    assert body["status"] == "active"

    assert client.get(
        f"/api/orgs/{ORG}/dimensions/{dim}/values/val:none",
        headers=_hdr(env, "u_full"),
    ).status_code == 404
    assert client.get(
        f"/api/orgs/{ORG}/dimensions/dim:none/values/{val}",
        headers=_hdr(env, "u_full"),
    ).status_code == 404


# ============ C 组：sem_restricted 管理面授予入口（G-24①） ============


def test_c1_post_member_sem_restricted_role(rest_env) -> None:
    """POST members role=sem_restricted：201 + member.add 审计带 role
    （G-24①——POC 前仅 DB/dev 工具授予，本段补管理面入口）。"""
    client, env = rest_env["client"], rest_env
    from helpers import seed_user

    seed_user(env["db"], "u_sem")
    env["db"].commit()
    r = client.post(
        f"/api/orgs/{ORG}/members", headers=_hdr(env, "admin_tax"),
        json={"user_id": "u_sem", "role": "sem_restricted"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "sem_restricted"
    row = env["db"].execute(
        "SELECT role FROM user_org_memberships WHERE user_id = ? AND org_id = ?",
        ("u_sem", ORG),
    ).fetchone()
    assert row[0] == "sem_restricted"
    events = _outbox_types(env, "member.add")
    added = [e for e in events if e["payload"].get("user_id") == "u_sem"]
    assert added and added[-1]["payload"]["role"] == "sem_restricted"


def test_c2_patch_member_sem_restricted_role(rest_env) -> None:
    """PATCH members role=sem_restricted（member ↔ sem_restricted 互转）+
    member.update 审计带 role。"""
    client, env = rest_env["client"], rest_env
    r = client.patch(
        f"/api/orgs/{ORG}/members/u_full", headers=_hdr(env, "admin_tax"),
        json={"role": "sem_restricted"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "sem_restricted"
    # 还原（member）
    r2 = client.patch(
        f"/api/orgs/{ORG}/members/u_full", headers=_hdr(env, "admin_tax"),
        json={"role": "member"},
    )
    assert r2.status_code == 200 and r2.json()["role"] == "member"
    events = _outbox_types(env, "member.update")
    patched = [
        e for e in events
        if e["payload"].get("user_id") == "u_full"
        and e["payload"].get("role") == "sem_restricted"
    ]
    assert patched, "member.update 审计须带 role=sem_restricted"


def test_c3_invalid_role_still_rejected(rest_env) -> None:
    """role 枚举扩展后仍 fail-closed：非法 role 400（POST 与 PATCH 双面）。"""
    client, env = rest_env["client"], rest_env
    assert client.post(
        f"/api/orgs/{ORG}/members", headers=_hdr(env, "admin_tax"),
        json={"user_id": "u_full", "role": "superadmin"},
    ).status_code == 400
    assert client.patch(
        f"/api/orgs/{ORG}/members/u_full", headers=_hdr(env, "admin_tax"),
        json={"role": "viewer"},
    ).status_code == 400


def test_c4_last_admin_guard_covers_sem_restricted(rest_env) -> None:
    """唯一 active org_admin 守卫兼容：降级为 sem_restricted 同属身份终结
    （单值列不兼任——T-S9）→ 最后管理员降级 409 防自锁；双 admin 组织可降。"""
    client, env = rest_env["client"], rest_env
    # org:tax 双 admin（admin_tax + admin_full）：admin_full 可降级 sem_restricted
    r = client.patch(
        f"/api/orgs/{ORG}/members/admin_full", headers=_hdr(env, "admin_tax"),
        json={"role": "sem_restricted"},
    )
    assert r.status_code == 200, r.text
    # 此时 admin_tax 是唯一 active org_admin → 降级 sem_restricted 被守卫拒绝
    assert client.patch(
        f"/api/orgs/{ORG}/members/admin_tax", headers=_hdr(env, "admin_tax"),
        json={"role": "sem_restricted"},
    ).status_code == 409, "唯一 active org_admin 降级 sem_restricted 须 409 防自锁"
    # 还原 admin_full（admin_tax 仍 admin——操作权限有效）
    assert client.patch(
        f"/api/orgs/{ORG}/members/admin_full", headers=_hdr(env, "admin_tax"),
        json={"role": "org_admin"},
    ).status_code == 200
