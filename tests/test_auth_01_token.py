"""TC-AUTH-01 静态 token 边界【接口｜M0a】。

① dev 配置下 u1 调 POST /api/dev/token → 成功；② u1 给 u2 签发 → 403；
③ 系统管理员给他人签发 → 成功；④ 生产配置下调该端点 → 404（路由未注册）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from knowledge_lattice.app import create_app
from knowledge_lattice.config import Settings


def _auth(app_env, uid):
    return {"Authorization": f"Bearer {app_env['static'][uid]}"}


def test_dev_token_self_issue_ok(app_env) -> None:
    """① u_full 给自己签 → 200，token 可用作 Bearer（sub/org claim 生效）。"""
    resp = app_env["client"].post("/api/dev/token", headers=_auth(app_env, "u_full"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "u_full"
    assert body["token_type"] == "bearer"
    # 签发的 JWT 可直接调检索（org claim 单值）
    resp2 = app_env["client"].post(
        "/api/dev/token",
        json={"org": "org:tax"},
        headers=_auth(app_env, "u_full"),
    )
    token = resp2.json()["token"]
    hits = app_env["client"].post(
        "/api/search",
        json={"query": "增值税"},
        headers={"Authorization": f"Bearer {token}"},  # 无 X-Org-Id——org 来自 claim
    )
    assert hits.status_code == 200
    assert "results" in hits.json()


def test_dev_token_issue_for_other_403(app_env) -> None:
    """② u_full 给 u_cn 签发 → 403（只能给自己签）。"""
    resp = app_env["client"].post(
        "/api/dev/token",
        json={"user_id": "u_cn"},
        headers=_auth(app_env, "u_full"),
    )
    assert resp.status_code == 403


def test_dev_token_sysadmin_issue_for_other_ok(app_env) -> None:
    """③ 系统管理员给他人签发 → 成功。"""
    resp = app_env["client"].post(
        "/api/dev/token",
        json={"user_id": "u_cn", "org": "org:tax"},
        headers=_auth(app_env, "sysadmin"),
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "u_cn"
    # 签出的 token 以 u_cn 身份可用
    token = resp.json()["token"]
    hits = app_env["client"].post(
        "/api/search",
        json={"query": "增值税"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hits.status_code == 200


def test_dev_token_prod_404(tmp_path) -> None:
    """④ 生产配置：路由不注册 → 404（P1-7/T16——非 401/403）。"""
    settings = Settings(environment="prod", data_dir=tmp_path, probe_interval_s=0)
    app = create_app(settings, run_startup_probe=False)
    with TestClient(app) as client:
        resp = client.post(
            "/api/dev/token",
            json={},
            headers={"Authorization": "Bearer anything"},
        )
        assert resp.status_code == 404
