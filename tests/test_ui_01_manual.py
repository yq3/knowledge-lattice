"""TC-UI-01 语言切换与持久化【手动走查｜M0a 机制就位】——**不进 CI 断言**。

pytest 标记 manual（默认 skip）：本组为浏览器人工执行用例（TEST-CASES TC-UI 口径段
——前端薄壳无构建链/测试框架，不进 CI 自动化）。机制断言的自动化部分已由
TC-E2E-07 覆盖（两视图 + i18n 资产 + 双字典 + localStorage 机制代码在场）。

==================== 手动走查步骤（交付说明同款） ====================

前置：`cd knowledge-lattice && LATTICE_DATA_DIR=/tmp/lattice-data uv run uvicorn "knowledge_lattice.app:create_app" --factory --port 8000`
→ 打开 http://127.0.0.1:8000/ 。无后端时也可直接开
src/knowledge_lattice/web/index.html（i18n 机制不依赖 API——静态字典在前端）。

① 默认中文（清 localStorage 后打开）：
   1. DevTools → Application → Local Storage → 删除 lattice.lang（及全部键）→ 刷新页面；
   2. 预期：全页中文文案；`<html lang="zh-CN">`（DevTools Elements 根节点）；
      `<title>知识库薄壳</title>`；左侧导航「文档上传 / 检索测试」。

② 切换即时全页生效：
   1. 点头部「EN」→ 预期：全页 UI 文案即时切英文（导航 Upload / Search Test、
      表头 chunk_id/Document/…、按钮、placeholder、页脚），无刷新、无残留中文 UI 文案；
      `<html lang="en">`、`<title>Knowledge Lattice Shell</title>` 同步；
   2. 再点「中」→ 全部即时切回中文，`<html lang="zh-CN">` 与中文 title 同步。

③ localStorage 持久化：
   1. EN 态下刷新页面（F5）→ 预期：仍为英文（localStorage.lattice.lang == "en"）；
   2. 重开浏览器新窗口访问 → 仍为英文；
   3. 切回中文后刷新 → 中文保持。

（业务数据不译、服务端不感知语言——TC-UI-02/03/04 的完整走查随 M1 检索页扩展。）
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.manual,
    pytest.mark.skip(reason="TC-UI-01 为手动走查用例（浏览器人工执行、不进 CI——TEST-CASES TC-UI 口径段）"),
]


def test_ui_01_manual_walkthrough() -> None:
    """占位：走查步骤见模块 docstring（manual 标记——默认跳过）。"""
