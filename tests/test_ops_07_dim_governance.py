"""TC-OPS-07 维度退役与取值停用治理【集成｜M2】（m2-3 A 组——FR-4/dry_run）。

- ① `PATCH values status=disabled` 带 dry_run：影响面预估（受影响文档/授权/
  用户数）；确认后生效=**收紧进计算**（T3 联动——read_grants 三重过滤既有
  机制的治理入口）+ 审计入 outbox；
- ② `POST dimensions/{id}/retire`：影响面预估 + 二次确认（无 confirm 只返回
  预估）+ 审计；**T20 退役半句**——退役后编译产物不再含该维度条件（唯一
  放宽路径必有审计）。

双后端参数化（[sqlite]/[pg]）；REST 端点用例为 sqlite（app_env 惯例）。
"""

from __future__ import annotations

import json

import pytest

from conftest import ORG

DIM_REGION = "dim:org:tax:region"
VAL_CN = "val:dim:org:tax:region:CN"
VAL_OS = "val:dim:org:tax:region:OS"


# ============ ① 取值停用：dry_run 影响面 + 确认生效 + T3 联动 + 审计 ============


def test_disable_value_dry_run_returns_impact_without_applying(matrix) -> None:
    """dry_run 只返回影响面（docs=引用该值的文档数 / grants=引用行数 /
    users=持有者数），不落库、零审计。"""
    backend = matrix.make_backend()
    impact = backend.dimension_value_impact(ORG, DIM_REGION, VAL_CN)
    # matrix 造数：d_cn/d_multi 有 region=CN；CN 授权行 u_full/u_cn/u_cn_vat/
    # u_expired_grant/u_expired_member/admin_full 各一行（6 行 6 用户）
    assert impact == {"docs": 2, "grants": 6, "users": 6, "locked_docs": 2}

    result = backend.disable_dimension_value(
        ORG, DIM_REGION, VAL_CN, dry_run=True,
    )
    assert result == {"docs": 2, "grants": 6, "users": 6, "locked_docs": 2, "applied": False}
    # 未生效：取值仍 active
    assert matrix.execute(
        "SELECT status FROM dimension_values WHERE id = ?", (VAL_CN,)
    ).fetchone()[0] == "active"
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'dimension.value_disable'"
    ).fetchone()[0] == 0


def test_disable_value_confirmed_tightens_and_audits(matrix) -> None:
    """确认生效：status=disabled + 审计同事务；**T3 联动**——停用取值从授权
    展开中消失（u_cn 的 region 变空 → NOT EXISTS 单条件口径）。"""
    from knowledge_lattice.core.docs.acl import compile_acl
    from knowledge_lattice.domain.audit_events import EVENT_DIMENSION_VALUE_DISABLE

    backend = matrix.make_backend()
    audit = (EVENT_DIMENSION_VALUE_DISABLE, json.dumps(
        {"org_id": ORG, "dimension_id": DIM_REGION, "value_id": VAL_CN,
         "actor": "admin_tax"}, ensure_ascii=False))
    result = backend.disable_dimension_value(ORG, DIM_REGION, VAL_CN, audit=audit)
    assert result["applied"] is True and result["docs"] == 2

    assert matrix.execute(
        "SELECT status FROM dimension_values WHERE id = ?", (VAL_CN,)
    ).fetchone()[0] == "disabled"
    # 审计入 outbox（治理事件——TC-OPS-01 口径）
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'dimension.value_disable'"
    ).fetchone()[0] == 1
    # T3 联动：u_cn（仅 CN）→ region 空授权（NOT EXISTS）；u_full 仍有 OS
    grants_cn = backend.read_grants("u_cn", ORG)
    assert grants_cn["region"] == ()
    grants_full = backend.read_grants("u_full", ORG)
    assert grants_full["region"] == ("OS",)
    # 编译产物：u_cn 的 region 规则为空授权集（渲染 NOT EXISTS——T22 口径同源）
    plan = compile_acl(backend, "u_cn", ORG)
    rule = {r.key: r for r in plan.dimension_rules}["region"]
    assert rule.is_empty

    # 幂等：再停用不重复审计、影响面照常返回
    again = backend.disable_dimension_value(ORG, DIM_REGION, VAL_CN, audit=audit)
    assert again["applied"] is True
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'dimension.value_disable'"
    ).fetchone()[0] == 1


def test_disable_value_not_found_or_cross_org(matrix) -> None:
    """不存在/跨组织取值 → None（404 语义）。"""
    backend = matrix.make_backend()
    assert backend.dimension_value_impact(ORG, DIM_REGION, "val:nope") is None
    assert backend.disable_dimension_value(ORG, DIM_REGION, "val:nope") is None
    # 他组织维度（org:gl 无 region 维度行）
    assert backend.dimension_value_impact("org:gl", DIM_REGION, VAL_CN) is None


# ============ ② 维度退役：预估 + 二次确认 + 审计 + T20 半句 ============


def test_retire_dimension_confirm_flow_and_t20_half(matrix_channel) -> None:
    """无 confirm 只返回预估；confirm 后 status=retired + 审计；**T20 半句**：
    编译产物不再含该维度条件（唯一放宽路径）且退役事件已入 outbox。"""
    from knowledge_lattice.core.docs.acl import compile_acl
    from helpers import seed_doc_dims, seed_grant

    matrix = matrix_channel
    backend = matrix.make_backend()
    dim_channel = "dim:org:tax:channel"
    val_a = "val:dim:org:tax:channel:A"
    # 造数：u_full 持 channel=A；d_cn 回填 channel=[A]（回填即收紧——T20②）
    seed_grant(matrix, user_id="u_full", dim_id=dim_channel, val_id=val_a)
    seed_doc_dims(matrix, "d_cn", {"channel": ["A"]})

    plan_before = compile_acl(backend, "u_full", ORG)
    assert "channel" in {r.key for r in plan_before.dimension_rules}, (
        "退役前 channel 应在编译产物中（active 维度）"
    )

    # 预估（未确认）：docs=1（d_cn）、grants=1、values=1；不生效零审计
    impact = backend.dimension_retire_impact(ORG, dim_channel)
    assert impact == {"docs": 1, "grants": 1, "values": 1}
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'dimension.retire'"
    ).fetchone()[0] == 0

    # 确认退役：status=retired + 审计同事务
    result = backend.retire_dimension(
        ORG, dim_channel,
        audit=("dimension.retire", json.dumps(
            {"org_id": ORG, "dimension_id": dim_channel, "actor": "admin_tax"},
            ensure_ascii=False)),
    )
    assert result == {"docs": 1, "grants": 1, "values": 1}
    assert matrix.execute(
        "SELECT status FROM dimensions WHERE id = ?", (dim_channel,)
    ).fetchone()[0] == "retired"
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'dimension.retire'"
    ).fetchone()[0] == 1

    # T20④：编译产物不再含 channel 条件（唯一放宽路径）；u_full 不因 channel
    # 授权被收紧（region 规则照常）
    plan_after = compile_acl(backend, "u_full", ORG)
    keys = {r.key for r in plan_after.dimension_rules}
    assert "channel" not in keys, "退役维度不得生成条件（T20 半句）"
    assert "region" in keys and "tax_type" in keys
    # 幂等：再退役零新审计
    backend.retire_dimension(
        ORG, dim_channel,
        audit=("dimension.retire", "{}"),
    )
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'dimension.retire'"
    ).fetchone()[0] == 1


def test_retire_dimension_not_found(matrix) -> None:
    backend = matrix.make_backend()
    assert backend.dimension_retire_impact(ORG, "dim:nope") is None
    assert backend.retire_dimension(ORG, "dim:nope") is None


def test_disable_value_impact_locked_docs(matrix) -> None:
    """R2 边界3：影响面补 locked_docs（v1.6.3「维度写锁项」显式化）——组织内
    引用了**已停用取值（含本次将停用值）或 retired 维度取值**的文档数：这些
    文档的 PATCH / 覆盖上传将被 _require_values_in_grants 同锁（恢复路径=
    重新启用取值）。"""
    backend = matrix.make_backend()
    # 基线：无任何 disabled 值/retired 维度；停用 region/CN——本值视作 disabled
    # → 引用 CN 的文档 d_cn、d_multi 被锁
    impact = backend.dimension_value_impact(ORG, DIM_REGION, VAL_CN)
    assert impact["docs"] == 2 and impact["grants"] == 6
    assert impact["locked_docs"] == 2, "本值视作 disabled：d_cn/d_multi 锁面"

    # 退役 tax_type 后（retired 维度）：tax_type 有值文档（d_cn=VAT、d_cit=CIT）
    # 也入锁面 → locked = {d_cn, d_multi} ∪ {d_cn, d_cit} = 3
    backend.retire_dimension(
        ORG, "dim:org:tax:tax_type",
        audit=("dimension.retire", "{}"),
    )
    impact2 = backend.dimension_value_impact(ORG, DIM_REGION, VAL_CN)
    assert impact2["locked_docs"] == 3, "retired 维度文档并入锁面（跨维度文档级）"

    # 确认生效路径返回同口径
    result = backend.disable_dimension_value(
        ORG, DIM_REGION, VAL_CN,
        audit=("dimension.value_disable", "{}"),
    )
    assert result["locked_docs"] == 3
    # 已停用后的后续预估（对 VAL_OS）：存量 disabled（CN→d_cn/d_multi）+
    # retired 维度（d_cn/d_cit）+ 本值 OS 视作 disabled（d_multi/d_os）→ 4 篇
    impact3 = backend.dimension_value_impact(ORG, DIM_REGION, VAL_OS)
    assert impact3["locked_docs"] == 4, "存量 disabled + retired + 本值锁面叠加"


# ============ REST 端点（sqlite——app_env 惯例） ============


@pytest.fixture()
def _admin_env(app_env):
    """app_env + org_admin（admin_tax）静态 token。"""
    from helpers import seed_membership, seed_user
    from knowledge_lattice.domain.auth import hash_token

    conn = app_env["conn"]
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = 'admin_tax'",
        (hash_token("dev-static-admin-tax"),),
    )
    conn.commit()
    return {**app_env, "admin_headers": {"Authorization": "Bearer dev-static-admin-tax"}}


def test_api_disable_value_dry_run_and_confirm(_admin_env) -> None:
    """PATCH /dimensions/{id}/values/{value_id}：dry_run=1 只预估；确认生效；
    非 org_admin 403；404 语义。"""
    client, conn = _admin_env["client"], _admin_env["conn"]
    admin = _admin_env["admin_headers"]
    member = {"Authorization": f"Bearer {_admin_env['static']['u_full']}"}

    # 非 org_admin → 403
    r = client.patch(
        "/api/orgs/org:tax/dimensions/dim:org:tax:region/values/"
        "val:dim:org:tax:region:CN",
        headers=member, json={"status": "disabled"},
    )
    assert r.status_code == 403

    # dry_run → 预估不生效
    r = client.patch(
        "/api/orgs/org:tax/dimensions/dim:org:tax:region/values/"
        "val:dim:org:tax:region:CN",
        headers=admin, json={"status": "disabled", "dry_run": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["impact"]["grants"] >= 1 and body["applied"] is False
    assert conn.execute(
        "SELECT status FROM dimension_values WHERE id = 'val:dim:org:tax:region:CN'"
    ).fetchone()[0] == "active"

    # 确认 → 生效 + 审计
    r = client.patch(
        "/api/orgs/org:tax/dimensions/dim:org:tax:region/values/"
        "val:dim:org:tax:region:CN",
        headers=admin, json={"status": "disabled"},
    )
    assert r.status_code == 200 and r.json()["applied"] is True
    assert conn.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'dimension.value_disable'"
    ).fetchone()[0] == 1

    # 404
    r = client.patch(
        "/api/orgs/org:tax/dimensions/dim:org:tax:region/values/val:nope",
        headers=admin, json={"status": "disabled"},
    )
    assert r.status_code == 404


def test_api_retire_dimension_confirm_gate(_admin_env) -> None:
    """POST /dimensions/{id}/retire：无 confirm 只返回预估；?confirm=1 生效+
    审计；已 retired 409；非 org_admin 403。"""
    client, conn = _admin_env["client"], _admin_env["conn"]
    admin = _admin_env["admin_headers"]
    member = {"Authorization": f"Bearer {_admin_env['static']['u_full']}"}
    dim = "dim:org:tax:region"  # app_env 只造 region（CN/OS 两值）

    r = client.post(f"/api/orgs/org:tax/dimensions/{dim}/retire", headers=member)
    assert r.status_code == 403

    # 无 confirm → 预估（confirm_required）
    r = client.post(f"/api/orgs/org:tax/dimensions/{dim}/retire", headers=admin)
    assert r.status_code == 200
    body = r.json()
    assert body["confirm_required"] is True and body["impact"]["values"] == 2
    assert conn.execute(
        "SELECT status FROM dimensions WHERE id = ?", (dim,)
    ).fetchone()[0] == "active"

    # confirm → 生效 + 审计（T20 半句）
    r = client.post(
        f"/api/orgs/org:tax/dimensions/{dim}/retire", headers=admin,
        params={"confirm": "1"},
    )
    assert r.status_code == 200 and r.json()["applied"] is True
    assert conn.execute(
        "SELECT status FROM dimensions WHERE id = ?", (dim,)
    ).fetchone()[0] == "retired"
    assert conn.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'dimension.retire'"
    ).fetchone()[0] == 1

    # 已 retired → 409
    r = client.post(
        f"/api/orgs/org:tax/dimensions/{dim}/retire", headers=admin,
        params={"confirm": "1"},
    )
    assert r.status_code == 409

    r = client.post("/api/orgs/org:tax/dimensions/dim:nope/retire", headers=admin)
    assert r.status_code == 404
