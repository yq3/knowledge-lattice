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
D26 段（issue #34 local agent key）：资产/注册断言扩 views/agent_keys.js
（VIEWS.agent_keys + onEnterAgentKeys——按序在 users.js 之后）；bundle 契约扩
/agent-keys；zh/en 键集断言覆盖 nav.agent_keys / agentKeys.title /
agentKeys.key.title；视图数八→九（login/users/agent_keys/docs/search/access/ops/
semantic/orgs）。
2026-11-22 段（MCP 接入页）：资产/注册断言扩 views/mcp.js（VIEWS.mcp——用户在系统
页面即可读到接入指南，不必进代码仓）；顶栏 MCP 弹层并入该页（单一内容来源，改快捷
链接 + title）；zh/en 键集断言覆盖 nav.mcp / mcpPage.title / mcpPage.endpoint。
"""

from __future__ import annotations

import json
import re


def _auth(app_env):
    return {"Authorization": f"Bearer {app_env['static']['u_full']}", "X-Org-Id": "org:tax"}


def test_shell_served_with_app_frame_and_i18n(app_env) -> None:
    """GET / 返回应用壳：app 骨架 + 语言切换 + i18n 机制资产 + 九视图脚本注册。"""
    client = app_env["client"]
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert 'class="app"' in html  # 应用骨架（topbar + rail + main）
    assert 'id="langSwitch"' in html  # 中 | EN 切换
    assert 'id="userPicker"' in html  # D25 local 用户菜单挂载点（sso 隐藏）
    assert 'data-i18n=' in html and 'lang="zh-CN"' in html  # i18n 机制 + 默认中文
    assert 'id="orgPicker"' in html and 'id="main"' in html  # 挂载点（组织 picker / 主区）
    # 资产清单（框架 + i18n + REST 适配层 + 九视图，按序经典脚本）
    assets = (
        "/static/style.css",
        "/static/i18n.js",
        "/static/api.js",
        "/static/app.js",
        "/static/views/login.js",
        "/static/views/users.js",
        "/static/views/agent_keys.js",
        "/static/views/mcp.js",
        "/static/views/docs.js",
        "/static/views/search.js",
        "/static/views/access.js",
        "/static/views/ops.js",
        "/static/views/semantic.js",
        "/static/views/orgs.js",
    )
    for asset in assets:
        assert client.get(asset).status_code == 200, asset
    # 资产按序引入（i18n → api → app → views/login → views/users → agent_keys → docs → views）
    pos = [html.index(src) for src in (
        "/static/i18n.js", "/static/api.js", "/static/app.js",
        "/static/views/login.js", "/static/views/users.js",
        "/static/views/agent_keys.js", "/static/views/mcp.js",
        "/static/views/docs.js",
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
                "users.err.last_sysadmin",
                # D26：agent 长期凭据管理页（导航 + 页面标题 + 明文签发弹窗标题）
                "nav.agent_keys", "agentKeys.title", "agentKeys.key.title",
                # D26：签发后接入配置块（端点/请求头/复制）
                "agentKeys.key.endpoint", "agentKeys.key.copyConfig",
                # 2026-11-22：MCP 接入页（导航 + 页面标题 + 端点行 + 工具清单分区）
                "nav.mcp", "mcpPage.title", "mcpPage.endpoint", "mcpPage.sec.tools"):
        assert key in zh_keys, key
    # 视图注册断言：app.js 定义注册表，六个视图文件各自注册；m4-3a 的 auth 视图
    # 注册在 login.js，boot 门状态机（AUTH/bootLocal）在 app.js；m4-3b 的 users
    # 视图注册在 views/users.js；D26 的 agent_keys 视图注册在 views/agent_keys.js。
    app_js = client.get("/static/app.js").text
    assert "VIEWS" in app_js
    assert "AUTH" in app_js and "bootLocal" in app_js
    # 2026-11-22（用户要求）：左栏导航不挂实时计数——计数属页面内容，不属导航
    assert "ni-c" not in app_js, "导航又挂回计数位（ni-c）"
    login_js = client.get("/static/views/login.js").text
    assert "VIEWS.auth" in login_js
    users_js = client.get("/static/views/users.js").text
    assert "VIEWS.users" in users_js
    assert "onEnterUsers" in users_js  # epoch/connected 守卫的装载入口
    agent_keys_js = client.get("/static/views/agent_keys.js").text
    assert "VIEWS.agent_keys" in agent_keys_js
    assert "onEnterAgentKeys" in agent_keys_js  # 明文集只显示一次 + 撤销入口
    mcp_js = client.get("/static/views/mcp.js").text
    assert "VIEWS.mcp" in mcp_js
    assert "MCP_TOOLS" in mcp_js  # 工具清单（与 mcp/server.py 注册一致——见 test_mcp_guide_page）
    for name in ("docs", "search", "access", "ops", "semantic", "orgs"):
        view_js = client.get(f"/static/views/{name}.js").text
        assert f"VIEWS.{name}" in view_js, name


def test_member_identity_displays_username_not_id(app_env) -> None:
    """成员标识：界面显示 username，内部键仍是 user_id。

    local 形态 user_id 是不透明的 u_<hex>（2026-11-22 用户走查：成员表只有 ID，
    看不出谁是谁）。GET members 已联查 users 返回 username——前端必须留存并以
    user_id 为键、username 为显示名；授权导出行的 username 也要归一到 user_id，
    否则同一人会出现两行（一行 username 带授权、一行 id 无授权）。
    """
    app_js = app_env["client"].get("/static/app.js").text
    acc = app_env["client"].get("/static/views/access.js").text
    assert "function userLabel(" in app_js and "function userIdOf(" in app_js
    assert "username: m.username" in app_js, "GET members 的 username 未被留存"
    assert "userLabel(u)" in acc, "成员表未用 username 显示"
    assert "userIdOf(r.username)" in acc, "授权导出行未归一到 user_id"


def test_org_lifecycle_controls_gated_by_sysadmin(app_env) -> None:
    """组织级操作（建组织 / 停用 / 恢复）按身份门控。

    local 形态：会话 payload 带 is_system_admin → 非系统管理员不渲染这些控件
    （2026-11-22 修：此前 org_admin 看得到无权按钮）；
    sso 形态：该字段不在 token 里、前端无法预判 → 维持控件常显 + 服务端 403 兜底。
    """
    src = app_env["client"].get("/static/views/orgs.js").text
    assert "function canManageOrgLifecycle()" in src
    assert 'AUTH.mode === "local"' in src and "AUTH.user.is_system_admin" in src
    # 头部按钮 / 新建表单 / 行内启停 / 确认行 + 5 个动作入口（防绕过 DOM 直调）
    assert src.count("canManageOrgLifecycle()") >= 10
    head = src.split('data-act="orgNewToggle"', 1)[0].rsplit('class="head-act"', 1)[-1]
    assert "canManageOrgLifecycle()" in head, "头部建组织按钮未在门控内"


def test_shell_uses_api_contract(app_env) -> None:
    """页壳走 API 契约（fetch 端点与 §6.2 一致——UI 只是壳；收口在 api.js + views/*）。"""
    client = app_env["client"]
    bundle = "".join(
        client.get(asset).text
        for asset in (
            "/static/api.js",
            "/static/views/login.js",
            "/static/views/users.js",
            "/static/views/agent_keys.js",
            "/static/views/mcp.js",
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
        # D26（issue #34）：agent 长期凭据管理（local 专属）
        "/agent-keys",
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
