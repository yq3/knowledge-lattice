"""分层守卫：core/semantic 与 core/docs 包级互斥（design §3 边界规则——import-linter
配置未随仓落盘，本测试兜底执法：两包任何模块不得 import 对方）。

适配器钉位注：api / mcp 层的 auto_entities 识别不涉本段；store 层双向被引用合法。
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "knowledge_lattice"


def _py_files(pkg: str):
    return (SRC / pkg).rglob("*.py")


def _assert_no_import(pkg: str, forbidden: str) -> None:
    bad: list[str] = []
    for f in _py_files(pkg):
        text = f.read_text(encoding="utf-8")
        if forbidden in text:
            bad.append(str(f.relative_to(SRC)))
    assert not bad, f"包级互斥被破：{pkg}/ 不得引用 {forbidden}——{bad}"


def test_core_semantic_does_not_import_core_docs() -> None:
    _assert_no_import("core/semantic", "knowledge_lattice.core.docs")


def test_core_docs_does_not_import_core_semantic() -> None:
    _assert_no_import("core/docs", "knowledge_lattice.core.semantic")
