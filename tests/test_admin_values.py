"""m2-6 A4：values CRUD + D19 重新启用取值恢复路径。

- 新增取值（POST /dimensions/{id}/values——retired 维度 409 / 重复 409 / 审计 /
  label 展示名传递〔R2 P3-4〕）；
- **重新启用**（PATCH status=active——D19 恢复路径）：文档含已停用取值时
  PATCH/覆盖上传同锁（v1.6.3「维度写锁」口径），重新启用后**解锁**——
  locked_docs 判定面自动联动（disable 升 / enable 回落）；retired 维度
  enable 409（store R2 P3-4 + **REST 面映射 R3 P3-2**——与 create 对称）；
  幂等 applied=False（按 rowcount）；
- dry_run 仅 disabled 支持；维度退役二次确认（T20）兼容。

store 级双后端参数化（[sqlite]/[pg]）；REST 端点 sqlite（app_env 惯例）。
"""

from __future__ import annotations

import pytest

from conftest import ORG
from helpers import dim_id_for, val_id_for


# ============ store 级（双后端） ============


def test_create_dimension_value_semantics(matrix) -> None:
    """create：成功（status=active）/维度不存在 None/重复
    DimensionValueExistsError/retired ValueError；audit 同事务。"""
    from knowledge_lattice.store.backend import DimensionValueExistsError

    backend = matrix.make_backend()
    dim = dim_id_for(ORG, "tax_type")

    created = backend.create_dimension_value(
        ORG, dim, "NEW_VAL", audit=("dimension.value_create", "{}"),
    )
    assert created["status"] == "active"
    assert created["value"] == "NEW_VAL"

    assert backend.create_dimension_value(ORG, "dim:nope", "X") is None
    with pytest.raises(DimensionValueExistsError):
        backend.create_dimension_value(ORG, dim, "NEW_VAL")
    with pytest.raises(ValueError):
        # retired 维度不扩值（T20 对称面）
        matrix.execute(
            "UPDATE dimensions SET status = 'retired' WHERE id = ?", (dim,),
        )
        backend.create_dimension_value(ORG, dim, "ANOTHER")
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type ="
        " 'dimension.value_create'",
    ).fetchone()[0] == 1


def test_enable_dimension_value_unlock(matrix) -> None:
    """D19 恢复路径：disable → locked_docs 升（v1.6.3 写锁）→ enable →
    locked_docs 回落（解锁联动）；幂等零新审计；404 语义。"""
    backend = matrix.make_backend()
    vid = val_id_for(ORG, "region", "CN")

    # 基线：CN 在用——treating_active 视角（启用语义）无锁；非 treating 视角
    # 恒含本值（dry_run 停用预估语义——m2-3 既有口径）
    base = backend.dimension_value_impact(
        ORG, dim_id_for(ORG, "region"), vid, treating_active=True,
    )
    assert base["locked_docs"] == 0

    disabled = backend.disable_dimension_value(
        ORG, dim_id_for(ORG, "region"), vid, audit=("dimension.value_disable", "{}"),
    )
    assert disabled["applied"]
    after_disable = backend.dimension_value_impact(
        ORG, dim_id_for(ORG, "region"), vid,
    )
    assert after_disable["locked_docs"] >= 1, "停用后 d_cn/d_multi 被锁"

    enabled = backend.enable_dimension_value(
        ORG, dim_id_for(ORG, "region"), vid, audit=("dimension.value_enable", "{}"),
    )
    assert enabled["applied"]
    # 解锁联动：treating_active 视角下 locked_docs 回落（本值不再构成锁）
    after_enable = backend.dimension_value_impact(
        ORG, dim_id_for(ORG, "region"), vid, treating_active=True,
    )
    assert after_enable["locked_docs"] == 0, "重新启用后解锁"

    # 幂等：再 enable 零新审计
    backend.enable_dimension_value(ORG, dim_id_for(ORG, "region"), vid)
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type ="
        " 'dimension.value_enable'",
    ).fetchone()[0] == 1
    assert backend.enable_dimension_value(ORG, "dim:nope", vid) is None


def test_disable_then_enable_roundtrip_tightens_and_restores(matrix) -> None:
    """T3 联动闭环：disable → read_grants 收紧（u_cn 无 CN）→ enable → 恢复。"""
    backend = matrix.make_backend()
    vid = val_id_for(ORG, "region", "CN")
    dim = dim_id_for(ORG, "region")

    before = backend.read_grants("u_cn", ORG)
    backend.disable_dimension_value(ORG, dim, vid)
    tightened = backend.read_grants("u_cn", ORG)
    assert tightened.get("region") == (), "停用取值从授权展开消失（收紧）"
    backend.enable_dimension_value(ORG, dim, vid)
    restored = backend.read_grants("u_cn", ORG)
    assert restored.get("region") == before.get("region"), "重新启用后恢复"


# ============ REST 端点（sqlite——app_env） ============


@pytest.fixture()
def _value_env(app_env):
    from helpers import (
        seed_membership,
        seed_searchable_doc,
        seed_user,
    )

    from knowledge_lattice.domain.auth import hash_token

    conn = app_env["conn"]
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = 'admin_tax'",
        (hash_token("dev-static-admin-tax"),),
    )
    # 一篇引用 CN 的文档（locked_docs 联动断言的载体）
    seed_searchable_doc(
        conn, "d_cn_lock", dims={"region": ["CN"]}, owner_user_id="u_full",
    )
    conn.commit()
    return {
        **app_env,
        "admin": {"Authorization": "Bearer dev-static-admin-tax"},
        "plain": {"Authorization": f"Bearer {app_env['static']['u_cn']}"},
        "dim": dim_id_for(ORG, "region"),
        "vid_cn": val_id_for(ORG, "region", "CN"),
    }


def test_api_value_create_and_enable(_value_env) -> None:
    """POST values 201/重复 409/404；PATCH status=active 重新启用 + locked_docs
    联动 + 审计；dry_run 语义（enable 不支持 400）；权限 403。"""
    client = _value_env["client"]
    dim = _value_env["dim"]

    # 普通成员 403
    r = client.post(
        f"/api/orgs/{ORG}/dimensions/{dim}/values",
        headers=_value_env["plain"], json={"value": "XX"},
    )
    assert r.status_code == 403

    # 新增
    r = client.post(
        f"/api/orgs/{ORG}/dimensions/{dim}/values",
        headers=_value_env["admin"], json={"value": "XX"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "active"
    # 重复 409
    r = client.post(
        f"/api/orgs/{ORG}/dimensions/{dim}/values",
        headers=_value_env["admin"], json={"value": "XX"},
    )
    assert r.status_code == 409
    # 维度不存在 404
    r = client.post(
        f"/api/orgs/{ORG}/dimensions/dim:nope/values",
        headers=_value_env["admin"], json={"value": "YY"},
    )
    assert r.status_code == 404

    # D19 恢复路径端到端：disable → 锁升；enable → 解锁 + 审计
    r = client.patch(
        f"/api/orgs/{ORG}/dimensions/{dim}/values/{_value_env['vid_cn']}",
        headers=_value_env["admin"], json={"status": "disabled"},
    )
    assert r.status_code == 200
    assert r.json()["impact"]["locked_docs"] >= 1

    r = client.patch(
        f"/api/orgs/{ORG}/dimensions/{dim}/values/{_value_env['vid_cn']}",
        headers=_value_env["admin"], json={"status": "active", "dry_run": True},
    )
    assert r.status_code == 400, "enable 不支持 dry_run"

    r = client.patch(
        f"/api/orgs/{ORG}/dimensions/{dim}/values/{_value_env['vid_cn']}",
        headers=_value_env["admin"], json={"status": "active"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["impact"]["locked_docs"] == 0, "重新启用解锁联动"

    assert _value_env["conn"].execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type ="
        " 'dimension.value_enable'",
    ).fetchone()[0] == 1
    # 404（值不存在）
    r = client.patch(
        f"/api/orgs/{ORG}/dimensions/{dim}/values/val:nope",
        headers=_value_env["admin"], json={"status": "active"},
    )
    assert r.status_code == 404


def test_api_retired_dimension_rejects_value_writes(_value_env) -> None:
    """T20 兼容：retired 维度上新增取值 409（退役不扩值）。"""
    client = _value_env["client"]
    _value_env["conn"].execute(
        "UPDATE dimensions SET status = 'retired' WHERE id = ?", (_value_env["dim"],),
    )
    _value_env["conn"].commit()
    r = client.post(
        f"/api/orgs/{ORG}/dimensions/{_value_env['dim']}/values",
        headers=_value_env["admin"], json={"value": "ZZ"},
    )
    assert r.status_code == 409


# ============ R2 P3-4：label 传递 / retired enable 409 / applied 按 rowcount ============


def test_create_value_label_passed_through(matrix) -> None:
    """label 展示名显式传递（R2 P3-4——API 与 store 直调同参；缺省=value）。"""
    backend = matrix.make_backend()
    dim = dim_id_for(ORG, "tax_type")
    created = backend.create_dimension_value(ORG, dim, "LBL", label="展示名")
    assert created["label"] == "展示名"
    stored = matrix.execute(
        "SELECT label FROM dimension_values WHERE id = ?", (created["value_id"],),
    ).fetchone()[0]
    assert stored == "展示名"
    # 缺省 label=value
    created2 = backend.create_dimension_value(ORG, dim, "NOLBL")
    assert created2["label"] == "NOLBL"


def test_enable_rejected_on_retired_dimension(matrix) -> None:
    """retired 维度上 enable 409（与 create 对称——R2 P3-4：退役维度取值不
    复活，重建维度是唯一路径）。"""
    backend = matrix.make_backend()
    dim = dim_id_for(ORG, "region")
    vid = val_id_for(ORG, "region", "CN")
    backend.disable_dimension_value(ORG, dim, vid)
    matrix.execute(
        "UPDATE dimensions SET status = 'retired' WHERE id = ?", (dim,),
    )
    with pytest.raises(ValueError, match="retired"):
        backend.enable_dimension_value(ORG, dim, vid)


def test_enable_idempotent_applied_false(matrix) -> None:
    """幂等 enable（已 active）→ applied=False（按 rowcount——R2 P3-4）+
    零新审计。"""
    backend = matrix.make_backend()
    dim = dim_id_for(ORG, "region")
    vid = val_id_for(ORG, "region", "CN")
    first = backend.enable_dimension_value(ORG, dim, vid)  # 已 active 幂等
    assert first["applied"] is False
    # disable → enable → applied=True；再 enable → False
    backend.disable_dimension_value(ORG, dim, vid)
    second = backend.enable_dimension_value(ORG, dim, vid,
                                            audit=("dimension.value_enable", "{}"))
    assert second["applied"] is True
    third = backend.enable_dimension_value(ORG, dim, vid)
    assert third["applied"] is False
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type ="
        " 'dimension.value_enable'",
    ).fetchone()[0] == 1, "幂等路径零新审计"


def test_api_enable_on_retired_dimension_409(_value_env) -> None:
    """P3-2/R3：retired 维度上 enable 的 REST 面 409（与 create 对称——修复前
    store ValueError 未映射致 500）。链路：retire → disable 200 → enable 409。"""
    client = _value_env["client"]
    dim = _value_env["dim"]

    # 前置：维度退役（二次确认语义的直达形态——SQL 造数，retire 端点已由
    # m2-3 用例覆盖）
    _value_env["conn"].execute(
        "UPDATE dimensions SET status = 'retired' WHERE id = ?", (dim,),
    )
    _value_env["conn"].commit()

    # disable 在 retired 维度上：store 幂等零行（已 disabled 前提先造）
    r = client.patch(
        f"/api/orgs/{ORG}/dimensions/{dim}/values/{_value_env['vid_cn']}",
        headers=_value_env["admin"], json={"status": "disabled"},
    )
    assert r.status_code in (200, 404), r.text

    # enable → 409（retired 维度取值不启用）
    r = client.patch(
        f"/api/orgs/{ORG}/dimensions/{dim}/values/{_value_env['vid_cn']}",
        headers=_value_env["admin"], json={"status": "active"},
    )
    assert r.status_code == 409, r.text
    assert "retired" in r.json()["detail"]
