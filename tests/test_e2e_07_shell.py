"""TC-E2E-07 REST 上传 + 静态页壳【集成｜M0a→ui-1 重写】。

ui-1 重写口径（issue #20 ui-1 段）：web/ 由功能薄壳重建为原型级 UI——
应用框架（顶栏/导航/组织与身份切换/连接设置）+ 文档知识 + 检索测试 +
管理面功能平移（权限/任务审计），五文件视图（views/*.js）+ i18n.js/api.js/app.js
经典脚本按序引入（无构建链）。本文件前两用例随新壳重写；第三用例
（REST multipart 上传 → 任务状态 → 检索闭环）保持不动。
"""

from __future__ import annotations

import json


def _auth(app_env):
    return {"Authorization": f"Bearer {app_env['static']['u_full']}", "X-Org-Id": "org:tax"}


def test_shell_served_with_app_frame_and_i18n(app_env) -> None:
    """GET / 返回应用壳：app 骨架 + 语言切换 + i18n 机制资产 + 五视图脚本注册。"""
    client = app_env["client"]
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert 'class="app"' in html  # 应用骨架（topbar + rail + main）
    assert 'id="langSwitch"' in html  # 中 | EN 切换
    assert 'data-i18n=' in html and 'lang="zh-CN"' in html  # i18n 机制 + 默认中文
    assert 'id="orgPicker"' in html and 'id="main"' in html  # 挂载点（组织 picker / 主区）
    # 资产清单（框架 + i18n + REST 适配层 + 四视图，按序经典脚本）
    assets = (
        "/static/style.css",
        "/static/i18n.js",
        "/static/api.js",
        "/static/app.js",
        "/static/views/docs.js",
        "/static/views/search.js",
        "/static/views/access.js",
        "/static/views/ops.js",
    )
    for asset in assets:
        assert client.get(asset).status_code == 200, asset
    # 资产按序引入（i18n → api → app → views）
    pos = [html.index(src) for src in (
        "/static/i18n.js", "/static/api.js", "/static/app.js", "/static/views/docs.js",
    )]
    assert pos == sorted(pos)
    i18n = client.get("/static/i18n.js").text
    assert "I18N" in i18n and '"zh"' in i18n and '"en"' in i18n  # zh/en 双字典
    assert "localStorage" in i18n  # 持久化机制（FR-8）
    # 视图注册断言：app.js 定义注册表，四个视图文件各自注册
    app_js = client.get("/static/app.js").text
    assert "VIEWS" in app_js
    for name in ("docs", "search", "access", "ops"):
        view_js = client.get(f"/static/views/{name}.js").text
        assert f"VIEWS.{name}" in view_js, name


def test_shell_uses_api_contract(app_env) -> None:
    """页壳走 API 契约（fetch 端点与 §6.2 一致——UI 只是壳；收口在 api.js + views/*）。"""
    client = app_env["client"]
    bundle = "".join(
        client.get(asset).text
        for asset in (
            "/static/api.js",
            "/static/views/docs.js",
            "/static/views/search.js",
            "/static/views/access.js",
            "/static/views/ops.js",
        )
    )
    for endpoint in ("/api/orgs/", "/documents", "/tasks", "/api/search", "/datasets", "/dimensions"):
        assert endpoint in bundle, f"页壳未使用契约端点 {endpoint}"


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
