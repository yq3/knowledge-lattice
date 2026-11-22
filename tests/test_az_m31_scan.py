"""m3-1 越权面扫描（TC-OPS-09 式——新端点全集；双后端 REST 端到端参数化）。

扫描面（验收标准 2）：
- 跨组织 403/404：u_gl（org:gl org_admin）对 org:tax 新端点扫描——org 路径
  403（成员校验先行）；他组织资源 id 在本组织路径 404（存在性敏感）；
- member vs org_admin vs sysadmin 边界：GET members / POST datasets·dimensions
  / PATCH orgs（sysadmin 专属）/ explain 他人（org_admin 专属）；
- 停用组织新端点 403（org_disabled——B 组访问面在新端点上的延伸扫描）。
"""

from __future__ import annotations

import pytest

from conftest import ORG, ORG_GL
from helpers import dim_id_for

pytestmark = pytest.mark.usefixtures("rest_env")


def _hdr(env, uid: str) -> dict:
    return {"Authorization": f"Bearer {env['tokens'][uid]}"}


# ============ 跨组织扫描：u_gl → org:tax 新端点（全部 403） ============

_NEW_ENDPOINT_SCAN: list[tuple[str, str, dict | None]] = [
    ("get", "/members", None),
    ("post", "/members", {"user_id": "u_full", "role": "member"}),
    ("post", "/datasets", {"key": "ds:x"}),
    ("patch", "/datasets/ds:vat_lib", {"title": "x"}),
    ("post", "/dimensions", {"key": "d", "label": "x"}),
    ("patch", f"/dimensions/{dim_id_for(ORG, 'region')}", {"label": "x"}),
    ("get", f"/dimensions/{dim_id_for(ORG, 'region')}", None),
    ("get", f"/dimensions/{dim_id_for(ORG, 'region')}/values", None),
    ("get", f"/dimensions/{dim_id_for(ORG, 'region')}/values/val:none", None),
    ("get", "/documents", None),
    ("get", "/documents/d_cn/explain", None),
    ("get", "/documents/d_cn/explain?user_id=u_cn", None),
]


def test_new_endpoints_cross_org_denied(rest_env) -> None:
    """u_gl 对 org:tax 的新端点扫描：全部 403（org_scoped 成员校验先行——
    绝不返回他组织资源内容/行集）。"""
    client, env = rest_env["client"], rest_env
    headers = _hdr(env, "u_gl")
    for method, tail, body in _NEW_ENDPOINT_SCAN:
        path = f"/api/orgs/{ORG}{tail}"
        kwargs = {"json": body} if body is not None else {}
        r = getattr(client, method)(path, headers=headers, **kwargs)
        assert r.status_code == 403, (
            f"u_gl → {method.upper()} {path}：期望 403，实际 {r.status_code}"
            f"（{r.text[:120]}）——跨组织端点不得放行"
        )


def test_patch_orgs_cross_org_and_gate(rest_env) -> None:
    """PATCH /api/orgs/{org} 门控矩阵：sysadmin 200（唯一放行）；
    他组织 org_admin 403；本组织 org_admin 403（不能停自己的组织）；member 403；
    无认证 401。"""
    client, env = rest_env["client"], rest_env
    body = {"status": "disabled"}
    assert client.patch(
        f"/api/orgs/{ORG}", headers=_hdr(env, "sysadmin"), json=body
    ).status_code == 200
    # 恢复（后续扫描不受影响）
    assert client.patch(
        f"/api/orgs/{ORG}", headers=_hdr(env, "sysadmin"),
        json={"status": "active"},
    ).status_code == 200
    assert client.patch(
        f"/api/orgs/{ORG_GL}", headers=_hdr(env, "admin_tax"), json=body
    ).status_code == 403, "他组织 org_admin 越权须 403"
    assert client.patch(
        f"/api/orgs/{ORG_GL}", headers=_hdr(env, "u_gl"), json=body
    ).status_code == 403, "本组织 org_admin 亦不可停用（sysadmin 专属）"
    assert client.patch(
        f"/api/orgs/{ORG_GL}", headers=_hdr(env, "u_multi"), json=body
    ).status_code == 403
    assert client.patch(
        f"/api/orgs/{ORG_GL}", json=body
    ).status_code == 401


def test_cross_org_resource_ids_404_in_own_org(rest_env) -> None:
    """他组织资源 id 在本组织路径 → 404（存在性敏感）：org:tax 的维度 id 在
    org:gl 路径（GET 单维度/取值列表/单取值/PATCH——m2-5 R2/P2-4 同款真实
    路由纪律）；org:tax 文档 id 的 explain 在 org:gl 路径 404。"""
    client, env = rest_env["client"], rest_env
    tax_dim = dim_id_for(ORG, "region")
    headers = _hdr(env, "u_gl")  # org:gl org_admin——操作权限过、资源不存在
    cases = [
        ("get", f"/api/orgs/{ORG_GL}/dimensions/{tax_dim}"),
        ("get", f"/api/orgs/{ORG_GL}/dimensions/{tax_dim}/values"),
        ("get", f"/api/orgs/{ORG_GL}/dimensions/{tax_dim}/values/val:none"),
        ("patch", f"/api/orgs/{ORG_GL}/dimensions/{tax_dim}"),
        ("get", f"/api/orgs/{ORG_GL}/documents/d_cn/explain"),
        ("get", f"/api/orgs/{ORG_GL}/documents/d_cn"),  # 既有端点对照
    ]
    for method, path in cases:
        kwargs = {"json": {"label": "x"}} if method == "patch" else {}
        r = getattr(client, method)(path, headers=headers, **kwargs)
        assert r.status_code == 404, (
            f"{method.upper()} {path}：org:tax 资源 id 在 org:gl 须 404"
            f"（got {r.status_code}——{r.text[:100]}）"
        )


def test_role_boundaries_member_admin_sysadmin(rest_env) -> None:
    """member vs org_admin vs sysadmin 边界：GET members（member 403 /
    org_admin 200 / sysadmin 无成员关系 403）；POST datasets·dimensions
    （member 403 / org_admin 201）；explain 他人（member 403 / org_admin 200）。"""
    client, env = rest_env["client"], rest_env
    # GET members 三面
    assert client.get(
        f"/api/orgs/{ORG}/members", headers=_hdr(env, "u_full")
    ).status_code == 403
    assert client.get(
        f"/api/orgs/{ORG}/members", headers=_hdr(env, "admin_tax")
    ).status_code == 200
    assert client.get(
        f"/api/orgs/{ORG}/members", headers=_hdr(env, "sysadmin")
    ).status_code == 403, "sysadmin 无成员关系——org_scoped 同 403（D22）"
    # POST datasets/dimensions：member 403 / org_admin 201
    assert client.post(
        f"/api/orgs/{ORG}/datasets", headers=_hdr(env, "u_full"),
        json={"key": "ds:member_try"},
    ).status_code == 403
    assert client.post(
        f"/api/orgs/{ORG}/datasets", headers=_hdr(env, "admin_tax"),
        json={"key": "ds:ok1"},
    ).status_code == 201
    assert client.post(
        f"/api/orgs/{ORG}/dimensions", headers=_hdr(env, "u_full"),
        json={"key": "d_member", "label": "x"},
    ).status_code == 403
    assert client.post(
        f"/api/orgs/{ORG}/dimensions", headers=_hdr(env, "admin_tax"),
        json={"key": "d_ok", "label": "x"},
    ).status_code == 201
    # explain 他人：member 403 / org_admin 200（D-② 契约）
    assert client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain", headers=_hdr(env, "u_full"),
        params={"user_id": "u_cn"},
    ).status_code == 403
    assert client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain", headers=_hdr(env, "admin_tax"),
        params={"user_id": "u_cn"},
    ).status_code == 200


def test_disabled_org_new_endpoints_403(rest_env) -> None:
    """停用组织的新端点扫描：org:tax 停用后本组织成员（admin_tax）对新端点
    全部 403（org_disabled——token 有效、组织上下文拒绝）。"""
    client, env = rest_env["client"], rest_env
    assert client.patch(
        f"/api/orgs/{ORG}", headers=_hdr(env, "sysadmin"),
        json={"status": "disabled"},
    ).status_code == 200
    headers = _hdr(env, "admin_tax")
    for method, tail, body in _NEW_ENDPOINT_SCAN:
        path = f"/api/orgs/{ORG}{tail}"
        kwargs = {"json": body} if body is not None else {}
        r = getattr(client, method)(path, headers=headers, **kwargs)
        assert r.status_code == 403, (
            f"停用组织新端点须 403：{method.upper()} {path} → {r.status_code}"
            f"（{r.text[:100]}）"
        )
