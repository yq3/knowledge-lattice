"""TC-E2E-07 REST 上传 + 静态页壳【集成｜M0a】。

薄壳可用（上传/检索两视图最小闭环）、API 契约先行（UI 只是壳）：
- GET / 服务静态页（两视图 + i18n 机制资产）；
- 经 REST multipart 上传并查看任务状态与检索测试页（API 闭环）。
"""

from __future__ import annotations

import json


def _auth(app_env):
    return {"Authorization": f"Bearer {app_env['static']['u_full']}", "X-Org-Id": "org:tax"}


def test_shell_served_with_two_views_and_i18n(app_env) -> None:
    """GET / 返回页壳：上传/检索两视图 + 语言切换 + i18n 资产（FR-8 机制载体）。"""
    client = app_env["client"]
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="view-upload"' in html and 'id="view-search"' in html  # 两视图
    assert 'id="langSwitch"' in html  # 中 | EN 切换
    assert 'data-i18n=' in html and 'lang="zh-CN"' in html  # i18n 机制 + 默认中文
    # i18n 资产可加载（字典/行为/样式）
    for asset in ("/static/i18n.js", "/static/app.js", "/static/style.css"):
        assert client.get(asset).status_code == 200, asset
    i18n = client.get("/static/i18n.js").text
    assert "I18N" in i18n and '"zh"' in i18n and '"en"' in i18n  # zh/en 双字典
    assert "localStorage" in i18n  # 持久化机制


def test_shell_uses_api_contract(app_env) -> None:
    """页壳走 API 契约（fetch 端点与 §6.2 一致——UI 只是壳）。"""
    app_js = app_env["client"].get("/static/app.js").text
    for endpoint in ("/api/orgs/", "/documents", "/tasks", "/api/search", "/datasets", "/dimensions"):
        assert endpoint in app_js, f"页壳未使用契约端点 {endpoint}"


def test_rest_upload_task_status_and_search_loop(app_env) -> None:
    """REST multipart 上传 → 任务状态查询 → 检索命中（薄壳闭环的 API 侧）。"""
    client = app_env["client"]
    html = (
        "<html><body><h1>差旅费报销管理办法</h1>"
        "<p>员工出差住宿费实行限额标准内据实报销，报销时限为费用发生后 30 日内。</p></body></html>"
    ).encode("utf-8")
    resp = client.post(
        "/api/orgs/org:tax/documents",
        files={"file": ("policy.html", html, "text/html")},
        data={
            "dataset": "ds:vat_lib",
            "title": "差旅费报销管理办法",
            "dims": json.dumps({"region": ["CN"]}),
        },
        headers=_auth(app_env),
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["doc_id"] and body["task_id"]

    # 任务状态（后台任务在 TestClient 请求周期内完成）
    task = client.get(
        f"/api/orgs/org:tax/tasks/{body['task_id']}", headers=_auth(app_env)
    ).json()
    assert task["status"] == "done"
    doc = client.get(
        f"/api/orgs/org:tax/documents/{body['doc_id']}", headers=_auth(app_env)
    ).json()
    assert doc["active_status"] == "searchable_full"

    # 检索测试页同款端点
    hits = client.post(
        "/api/search",
        json={"query": "差旅费 住宿 报销"},
        headers=_auth(app_env),
    ).json()
    assert hits["results"]
    assert hits["results"][0]["title"] == "差旅费报销管理办法"
