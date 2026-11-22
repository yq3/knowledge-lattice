"""MCP 接入页一致性（views/mcp.js ↔ mcp/server.py ↔ docs/MCP-INTEGRATION.md）。

2026-11-22 新增：控制台「MCP 接入」页（views/mcp.js）把 docs/MCP-INTEGRATION.md 的
**用户面**搬进产品，用户不必进代码仓查文档。内容双源（页面 / 文档）是本设计的已
知漂移风险，这里钉死三处最易漂移的事实：

1. **工具清单**——页面 `MCP_TOOLS` 必须等于 `mcp/server.py` 的 `@mcp.tool` 注册集合，
   且**顺序一致**（页面顺序 = 文档 §5 阅读顺序；增删工具必须三处同改）；
2. **文档同表**——`docs/MCP-INTEGRATION.md` §5 工具表必须等于同一集合（文档是仓内
   长尾参考，改了代码漏改文档同样红）；
3. **入口单一**——左侧导航「运维 → MCP 接入」是唯一入口。历史：顶栏曾挂 sso 专属
   弹层（只写 D18 委托 token），local 形态被 `body.auth-local #mcpPicker` 整体隐藏，
   导致 local 用户完全看不到；页面按 local/sso 分支后该弹层并入页面，顶栏快捷入口
   亦于 2026-11-22 按用户要求移除——顶栏不得复活重复入口，`mcpPicker` 选择器不得回流。

纯静态断言（读源码文本）：不起服务、不碰数据库、不导入被测模块。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "src/knowledge_lattice/mcp/server.py"
VIEW = ROOT / "src/knowledge_lattice/web/views/mcp.js"
DOC = ROOT / "docs/MCP-INTEGRATION.md"
INDEX = ROOT / "src/knowledge_lattice/web/index.html"
CSS = ROOT / "src/knowledge_lattice/web/style.css"
I18N = ROOT / "src/knowledge_lattice/web/i18n.js"
APP = ROOT / "src/knowledge_lattice/web/app.js"


def _server_tools() -> list[str]:
    return re.findall(r'@mcp\.tool\(name="([a-z_]+)"', SERVER.read_text(encoding="utf-8"))


def _view_tools() -> list[str]:
    src = VIEW.read_text(encoding="utf-8")
    assert "const MCP_TOOLS = [" in src, "views/mcp.js 未找到工具清单常量"
    block = src.split("const MCP_TOOLS = [", 1)[1].split("];", 1)[0]
    return re.findall(r'^\s*\["([a-z_]+)",\s*"mcpPage\.tool\.', block, re.M)


def _doc_tools() -> list[str]:
    text = DOC.read_text(encoding="utf-8")
    assert "## 5. 工具清单" in text, "docs/MCP-INTEGRATION.md 未找到 §5 工具清单"
    section = text.split("## 5. 工具清单", 1)[1].split("\n## 6.", 1)[0]
    return re.findall(r"^\| `([a-z_]+)` \|", section, re.M)


def test_tool_list_matches_server_registration() -> None:
    """页面工具清单 == @mcp.tool 注册集合（顺序一致——页面即文档 §5 的阅读序）。"""
    server, view = _server_tools(), _view_tools()
    assert server, "未解析到 mcp/server.py 的 @mcp.tool 注册"
    assert view == server, f"页面 {view} != 服务端注册 {server}"


def test_doc_tool_table_matches_server_registration() -> None:
    """文档 §5 工具表 == 同一集合（文档漂移同样红——仓内读者以它为准）。"""
    server, doc = _server_tools(), _doc_tools()
    assert doc == server, f"文档 {doc} != 服务端注册 {server}"


def test_tool_descriptions_i18n_complete() -> None:
    """每个工具在 zh/en 两套字典里都有 mcpPage.tool.* 用途文案（FR-8 双语）。"""
    src = I18N.read_text(encoding="utf-8")
    assert "\n  en: {" in src
    zh, rest = src.split("\n  en: {", 1)
    en = rest.split("\n};", 1)[0]
    for name in _view_tools():
        key = f'"mcpPage.tool.{name}"'
        assert key in zh, f"zh 缺 {key}"
        assert key in en, f"en 缺 {key}"
    # 反向：字典里不得留已删除工具的孤儿键（工具增删后清理）
    orphans = {
        k for k in re.findall(r'"mcpPage\.tool\.([a-z_]+)"', zh)
        if k not in _view_tools()
    }
    assert not orphans, f"孤儿工具文案键：{sorted(orphans)}"


def test_rendered_code_blocks_exist_in_snippet_source() -> None:
    """mcpCodeBlock("k") 引用的每段代码都必须来自 mcpSnippets()（中英共用单源）。"""
    src = VIEW.read_text(encoding="utf-8")
    keys = set(re.findall(r'mcpCodeBlock\("([a-zA-Z]+)"', src))
    assert keys, "页面未渲染任何代码块（接入页的核心内容）"
    for k in sorted(keys):
        assert re.search(rf"\n    {k}: ", src), f"代码片段 {k} 未在 mcpSnippets() 中定义"


def test_view_registered_and_nav_entry_present() -> None:
    """视图注册 + 左栏导航项（放在导航最后一项）。"""
    app = APP.read_text(encoding="utf-8")
    assert 'VIEWS.mcp' in VIEW.read_text(encoding="utf-8")
    assert '["mcp", t("nav.mcp")]' in app, "左栏缺少 MCP 接入导航项"
    assert '"nav.mcp"' in I18N.read_text(encoding="utf-8")


def test_entry_is_left_nav_only() -> None:
    """入口单一：左栏导航项；顶栏不得复活快捷入口 / 弹层（历史上曾被整条隐藏）。"""
    app = APP.read_text(encoding="utf-8")
    assert '["mcp", t("nav.mcp")]' in app, "左栏缺少 MCP 接入导航项"
    html = INDEX.read_text(encoding="utf-8")
    assert "mcpPicker" not in html, "顶栏又出现 MCP 快捷入口（用户 2026-11-22 要求移除）"
    assert 'data-v="mcp"' not in html, "顶栏又出现指向 MCP 页的按钮"
    css = CSS.read_text(encoding="utf-8")
    assert "mcpPicker" not in css, "残留 #mcpPicker 选择器（元素已移除）"


def test_topbar_dropdown_content_removed() -> None:
    """顶栏弹层已并入页面——不得留第二份内容（防两份说明漂移）。"""
    html = INDEX.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    assert "menu-mcp" not in html, "顶栏仍挂着旧 MCP 弹层容器"
    assert "mcpMenu" not in html and "mcpMenu" not in app, "残留 mcpMenu 动作/接线"


def test_all_page_i18n_keys_exist_both_languages() -> None:
    """views/mcp.js 引用的每个 mcpPage.* 键在 zh/en 都存在，且字典无孤儿键。

    比"跑起来看"更早暴露问题：缺键时 t() 原样返回键名，页面会出现 mcpPage.xxx。
    """
    src = VIEW.read_text(encoding="utf-8")
    used = set(re.findall(r'"(mcpPage\.[a-zA-Z.]+)"', src))
    assert used, "views/mcp.js 未引用任何 mcpPage.* 键"
    i18n = I18N.read_text(encoding="utf-8")
    zh, rest = i18n.split("\n  en: {", 1)
    en = rest.split("\n};", 1)[0]
    for key in sorted(used):
        assert f'"{key}"' in zh, f"zh 缺 {key}"
        assert f'"{key}"' in en, f"en 缺 {key}"
    orphans = set(re.findall(r'"(mcpPage\.[a-zA-Z.]+)":', zh)) - used
    assert not orphans, f"字典里的孤儿键（页面已不用）：{sorted(orphans)}"


def test_section_numbers_are_generated_not_baked_into_copy() -> None:
    """分区序号由渲染顺序生成，不写进 i18n 文案。

    历史：首版把「① 拿到凭据」…「⑦ 安全清单」写死进字典值，sso 形态没有「上传」
    一节，直接显示会跳号（⑤ 后接 ⑦）。现状 = viewMcp 里的计数器 + mcpSec(++n)。
    """
    i18n = I18N.read_text(encoding="utf-8")
    baked = [
        (key, value) for key, value in re.findall(
            r'"(mcpPage\.sec\.[a-z]+)": "([^"]*)"', i18n)
        if re.search(r"[\u2460-\u2473]", value)  # ①..⑳
    ]
    assert not baked, f"分区标题仍写死圈号（会随形态跳号）：{baked}"
    src = VIEW.read_text(encoding="utf-8")
    assert "let n = 0;" in src and "mcpSec(++n" in src, "分区序号未由渲染计数器生成"


def test_sections_render_as_cards_not_flat_document_flow() -> None:
    """分区一律走 mcpSec()（.card + .lane-h 卡头）。

    2026-11-22 用户走查：首版是扁平文档流——裸标题 + 无边代码块 + 段落全落在同一层
    灰底上，标题/代码块/段落揉在一起读不出分区边界。改为一节一卡：卡头分隔线断开
    标题与正文，卡内只放一种内容。本断言防止退回扁平流（.sec-title 裸标题 + 无边
    代码块）。
    """
    src = VIEW.read_text(encoding="utf-8")
    assert 'class="sec-title"' not in src, "又回到裸标题的文档流（分区应用 mcpSec 卡片）"
    n_sections = len(re.findall(r"mcpSec\(|sec\(\"mcpPage\.sec\.", src))
    assert n_sections >= 7, f"分区卡数量异常（{n_sections}）"
    css = CSS.read_text(encoding="utf-8")
    for rule in ("#mcp-guide .mcp-sec", "#mcp-guide .mcp-n", "#mcp-guide .mcp-code-h"):
        assert rule in css, f"style.css 缺 {rule}（分区卡/序号/代码面板头皮）"
