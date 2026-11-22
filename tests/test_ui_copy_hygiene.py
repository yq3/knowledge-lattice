"""界面文案卫生：内部设计/追踪编号不得进用户界面。

2026-11-22（用户走查）：控制台页面出现 `D7`、`#14` 这类仓内编号，用户会疑惑。
本组把「用户可见文案」与「仓内编号体系」机械隔开：

1. **i18n 字典的值**（真正渲染到页面的文案）不得含：决策编号 `D-n`、issue `#n`、
   缺口 `G-n`、需求 `FR-/NFR-n`、章节引用 `§`、里程碑 `M*-S*`、用例号 `TC-*`、
   阶段代号 `POC`、仓内文档路径（`docs/*.md` / `RUNBOOK` / `design.md` /
   `known-gaps`），以及裸接口路径 `/api/`；
2. **视图渲染串**不得把里程碑编号当可见徽标输出（此前检索页有 `>M2-S3<` 标签）；
3. 删除确认弹窗不得展示原始 HTTP 端点；语义实体详情不得留 REST↔MCP 实现对照行。

口径依据：AGENTS.md「编号体系沿用既有口径」——D/FR/G/T/TC 编号是**仓内**
纪律（评审、用例、缺口登记用），不是给业务/数据用户看的信息。

例外（有意放行）：`views/mcp.js` 的接入片段是**工程师面**内容，`curl ... /api/uploads`
这类代码块属于接入说明本身；代码**注释**里的编号亦不受约束（仓内惯例）。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "src/knowledge_lattice/web"
I18N = WEB / "i18n.js"

INTERNAL = [
    (re.compile(r"\bD\d{1,2}\b"), "决策编号 D-n"),
    (re.compile(r"#\d{2,}"), "issue 编号 #n"),
    (re.compile(r"\bG-\d+\b"), "缺口编号 G-n"),
    (re.compile(r"\bFR-\d+\b|\bNFR-\d+\b"), "需求编号 FR/NFR-n"),
    (re.compile(r"§"), "章节引用 §"),
    (re.compile(r"\bM\d-S\d\b"), "里程碑编号 M*-S*"),
    (re.compile(r"\bm\d+-\d+\b|\bui-\d+\b"), "里程碑/迭代编号 m*-*·ui-*"),
    (re.compile(r"\bTC-[A-Z]+-\d+\b"), "用例编号 TC-*"),
    (re.compile(r"\bPOC\b"), "阶段代号 POC"),
    (re.compile(r"docs/[\w-]+\.md|RUNBOOK|design\.md|known-gaps"), "仓内文档路径"),
    (re.compile(r"/api/"), "裸接口路径"),
]


def _dict_values() -> list[tuple[str, str, str]]:
    """(语言, 键, 值)——只取字典数据行，跳过注释。"""
    src = I18N.read_text(encoding="utf-8")
    zh, rest = src.split("\n  en: {", 1)
    en = rest.split("\n};", 1)[0]
    row = re.compile(r'^    "([^"]+)": "(.*)",?$', re.M)
    out: list[tuple[str, str, str]] = []
    for lang, block in (("zh", zh), ("en", en)):
        for key, value in row.findall(block):
            out.append((lang, key, value))
    return out


def test_no_internal_codes_in_user_facing_copy() -> None:
    values = _dict_values()
    assert len(values) > 500, "字典解析异常（值数量过少）"
    problems: list[str] = []
    for lang, key, value in values:
        for pat, label in INTERNAL:
            m = pat.search(value)
            if m:
                problems.append(f"[{lang}] {key}: {label} → {m.group(0)!r}")
    assert not problems, "界面文案含内部编号/实现细节：\n" + "\n".join(problems)


def test_views_have_no_milestone_badge() -> None:
    """视图不得把里程碑编号渲染成可见徽标（历史：检索页 <span class="tag">M2-S3</span>）。"""
    offenders = []
    for f in sorted((WEB / "views").glob("*.js")):
        src = f.read_text(encoding="utf-8")
        if re.search(r">\s*M\d-S\d\s*<", src):
            offenders.append(f.name)
    assert not offenders, f"视图仍渲染里程碑徽标：{offenders}"


def test_confirm_dialogs_have_no_raw_endpoints() -> None:
    """删除确认只讲后果，不展示 HTTP 端点。"""
    for name in ("access.js", "docs.js"):
        src = (WEB / "views" / name).read_text(encoding="utf-8")
        assert "DELETE /api/" not in src, f"{name} 的删除确认仍展示原始端点"


def test_semantic_detail_has_no_rest_mcp_equivalence_note() -> None:
    """语义实体详情不再附「REST 端点 ≡ MCP 工具」的实现对照行。"""
    src = (WEB / "views" / "semantic.js").read_text(encoding="utf-8")
    assert "≡ MCP" not in src


def test_maintenance_stat_keys_have_labels() -> None:
    """维护计数键（后端注册表英文名）必须有 zh/en 标签，且无孤儿键。

    2026-11-22（用户走查）：maintenance 计数页此前直接渲染后端键名（全英文）。
    标签映射在 views/ops.js 的 STAT_KEY_I18N；未知键运行时回落原始键名（前向兼容），
    但**已知键**必须有双语文本，否则该页又退化为英文。
    """
    ops = (WEB / "views" / "ops.js").read_text(encoding="utf-8")
    used = set(re.findall(r'"(ops\.stats\.k\.[a-zA-Z]+)"', ops))
    assert used, "views/ops.js 未引用任何 ops.stats.k.* 标签"
    i18n = I18N.read_text(encoding="utf-8")
    zh, rest = i18n.split("\n  en: {", 1)
    en = rest.split("\n};", 1)[0]
    for key in sorted(used):
        assert f'"{key}"' in zh, f"zh 缺 {key}"
        assert f'"{key}"' in en, f"en 缺 {key}"
    orphans = set(re.findall(r'"(ops\.stats\.k\.[a-zA-Z]+)":', zh)) - used
    assert not orphans, f"孤儿标签键（页面已不用）：{sorted(orphans)}"
