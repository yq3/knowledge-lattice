"""TC-E2E-07 REST 上传 + 静态页壳【集成｜M0a→ui-1 重写】。

ui-1 重写口径（issue #20 ui-1 段）：web/ 由功能薄壳重建为原型级 UI——
应用框架（顶栏/导航/组织与身份切换/连接设置）+ 文档知识 + 检索测试 +
管理面功能平移（权限/任务审计），视图（views/*.js）+ i18n.js/api.js/app.js
经典脚本按序引入（无构建链）。本文件前两用例随新壳重写；第三用例
（REST multipart 上传 → 任务状态 → 检索闭环）保持不动。
ui-2 段（issue #20）：前两用例资产/注册断言扩 semantic/orgs 两视图与语义/
成员契约端点；第三用例仍不动。
m4-3a 段（D25 local）：资产/注册断言扩 views/login.js（VIEWS.auth）与 app.js
boot 门（AUTH/bootLocal）；契约 bundle 扩登录/首启/邀请接受端点。
m4-3b 段（D25 local）：资产/bundle 扩 views/users.js（VIEWS.users——用户/邀请管理），
契约端点扩 /api/users 与 /invitations；zh/en 键集相等断言覆盖新增 users.* 键。
"""

from __future__ import annotations

import json
import re


def _auth(app_env):
    return {"Authorization": f"Bearer {app_env['static']['u_full']}", "X-Org-Id": "org:tax"}


def test_shell_served_with_app_frame_and_i18n(app_env) -> None:
    """GET / 返回应用壳：app 骨架 + 语言切换 + i18n 机制资产 + 八视图脚本注册。"""
    client = app_env["client"]
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert 'class="app"' in html  # 应用骨架（topbar + rail + main）
    assert 'id="langSwitch"' in html  # 中 | EN 切换
    assert 'id="userPicker"' in html  # D25 local 用户菜单挂载点（sso 隐藏）
    assert 'data-i18n=' in html and 'lang="zh-CN"' in html  # i18n 机制 + 默认中文
    assert 'id="orgPicker"' in html and 'id="main"' in html  # 挂载点（组织 picker / 主区）
    # 资产清单（框架 + i18n + REST 适配层 + 八视图，按序经典脚本）
    assets = (
        "/static/style.css",
        "/static/i18n.js",
        "/static/api.js",
        "/static/app.js",
        "/static/views/login.js",
        "/static/views/users.js",
        "/static/views/docs.js",
        "/static/views/search.js",
        "/static/views/access.js",
        "/static/views/ops.js",
        "/static/views/semantic.js",
        "/static/views/orgs.js",
    )
    for asset in assets:
        assert client.get(asset).status_code == 200, asset
    # 资产按序引入（i18n → api → app → views/login → views/users → docs → views）
    pos = [html.index(src) for src in (
        "/static/i18n.js", "/static/api.js", "/static/app.js",
        "/static/views/login.js", "/static/views/users.js", "/static/views/docs.js",
    )]
    assert pos == sorted(pos)
    i18n = client.get("/static/i18n.js").text
    assert "I18N" in i18n and '"zh"' in i18n and '"en"' in i18n  # zh/en 双字典
    assert "localStorage" in i18n  # 持久化机制（FR-8）
    # D25/m4-3a：zh/en 键集完全相等；auth 三屏与用户菜单键在场
    zh_block, en_block = i18n.split("\n  en: {", 1)
    en_block = en_block.split("\n};", 1)[0]
    key_re = re.compile(r'^\s{4}"([^"]+)":', re.M)
    zh_keys, en_keys = set(key_re.findall(zh_block)), set(key_re.findall(en_block))
    assert zh_keys and zh_keys == en_keys
    for key in ("auth.setup.title", "auth.login.title", "auth.invite.title",
                "auth.err.expired", "user.menu.password",
                # m4-3b：用户/邀请管理页键集（nav + 页面/表单/链接/错误）
                "nav.users", "users.title", "users.link.title", "users.inv.title",
                "users.err.last_sysadmin"):
        assert key in zh_keys, key
    # 视图注册断言：app.js 定义注册表，六个视图文件各自注册；m4-3a 的 auth 视图
    # 注册在 login.js，boot 门状态机（AUTH/bootLocal）在 app.js；m4-3b 的 users
    # 视图注册在 views/users.js。
    app_js = client.get("/static/app.js").text
    assert "VIEWS" in app_js
    assert "AUTH" in app_js and "bootLocal" in app_js
    login_js = client.get("/static/views/login.js").text
    assert "VIEWS.auth" in login_js
    users_js = client.get("/static/views/users.js").text
    assert "VIEWS.users" in users_js
    assert "onEnterUsers" in users_js  # epoch/connected 守卫的装载入口
    for name in ("docs", "search", "access", "ops", "semantic", "orgs"):
        view_js = client.get(f"/static/views/{name}.js").text
        assert f"VIEWS.{name}" in view_js, name


def test_shell_uses_api_contract(app_env) -> None:
    """页壳走 API 契约（fetch 端点与 §6.2 一致——UI 只是壳；收口在 api.js + views/*）。"""
    client = app_env["client"]
    bundle = "".join(
        client.get(asset).text
        for asset in (
            "/static/api.js",
            "/static/views/login.js",
            "/static/views/users.js",
            "/static/views/docs.js",
            "/static/views/search.js",
            "/static/views/access.js",
            "/static/views/ops.js",
            "/static/views/semantic.js",
            "/static/views/orgs.js",
        )
    )
    for endpoint in (
        "/api/orgs/", "/documents", "/tasks", "/api/search", "/datasets", "/dimensions",
        "/semantic/entities", "/semantic/annotate", "/members",
        # D25 local（m4-3a）：boot 门 / 首启 / 登录 / 邀请接受
        "/api/auth/login", "/api/setup", "/api/auth/invitations/accept",
        # D25 local（m4-3b）：用户/邀请管理
        "/api/users", "/invitations",
    ):
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
