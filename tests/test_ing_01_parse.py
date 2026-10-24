"""TC-ING-01 docling 解析→统一块结构【单测｜M0a】。

解析 docx（多级标题+表格）/pptx/xlsx/HTML/原生 PDF 样例（tests/fixtures/ 自造）→
输出统一块结构（content / heading_path / page_no / bbox_json / sheet_name）；
标题层级与页码保真；表格边界保留供切分。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_lattice.adapters.parser_docling import parse_document

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_docx_multilevel_headings_and_table() -> None:
    doc = parse_document(FIXTURES / "sample.docx")
    assert doc.parser == "docling"
    blocks = doc.blocks
    headings = [b for b in blocks if b.kind == "heading"]
    texts = [b for b in blocks if b.kind == "text"]
    tables = [b for b in blocks if b.kind == "table"]
    # 多级标题保真：一级「增值税申报指南」+ 两个二级
    assert [h.content for h in headings] == ["增值税申报指南", "一般纳税人", "小规模纳税人"]
    assert headings[0].level == 1 and headings[1].level == 2
    # 正文块 heading_path 记录层级路径
    by_content = {t.content: t for t in texts}
    path_1 = by_content["一般纳税人销售自产货物并提供安装服务的，应分别核算货物的销售额和安装服务的销售额。"]
    assert list(path_1.heading_path) == ["增值税申报指南", "一般纳税人"]
    path_2 = by_content["小规模纳税人发生应税销售行为，适用简易计税方法计税。"]
    assert list(path_2.heading_path) == ["增值税申报指南", "小规模纳税人"]
    # 表格边界保留（rows 结构 + 内容）
    assert len(tables) == 1
    assert tables[0].rows[0] == ("税种", "税率", "备注")
    assert tables[0].rows[1] == ("增值税", "13%", "标准税率")
    assert "增值税" in tables[0].content


def test_parse_pptx_slide_pages() -> None:
    doc = parse_document(FIXTURES / "sample.pptx")
    blocks = doc.blocks
    titles = [b for b in blocks if b.kind == "heading"]
    texts = [b for b in blocks if b.kind == "text"]
    # 页码保真：slide 序号
    assert [t.page_no for t in titles] == [1, 2]
    assert all(t.page_no in (1, 2) for t in texts)
    assert any("进项税额" in t.content for t in texts)


def test_parse_xlsx_sheet_names() -> None:
    doc = parse_document(FIXTURES / "sample.xlsx")
    tables = [b for b in doc.blocks if b.kind == "table"]
    assert len(tables) == 2
    # sheet_name 记录（FR-1）
    assert {t.sheet_name for t in tables} == {"税率表", "免税政策"}
    rows_by_sheet = {t.sheet_name: t.rows for t in tables}
    assert rows_by_sheet["税率表"][0] == ("税种", "税率", "适用")
    assert rows_by_sheet["税率表"][1] == ("增值税", "13%", "一般货物")
    assert rows_by_sheet["税率表"][3] == ("增值税", "6%", "现代服务")
    assert rows_by_sheet["免税政策"][1] == ("农产品", "自产自销")


def test_parse_html_headings() -> None:
    doc = parse_document(FIXTURES / "sample.html")
    blocks = doc.blocks
    headings = [b for b in blocks if b.kind == "heading"]
    texts = [b for b in blocks if b.kind == "text"]
    assert [h.content for h in headings] == ["费用制度总则", "住宿标准"]
    assert headings[0].level == 1 and headings[1].level == 2
    assert any("一类城市每晚不超过" in t.content for t in texts)
    assert list(texts[0].heading_path) == ["费用制度总则"]


@pytest.mark.pdf_models
def test_parse_pdf_native_page_and_bbox() -> None:
    """原生 PDF：内容/页码/bbox 保真（标题层级经 layout 模型识别——大字号行）。"""
    doc = parse_document(FIXTURES / "sample.pdf")
    blocks = doc.blocks
    assert blocks, "PDF 解析应产出块"
    contents = " ".join(b.content for b in blocks)
    assert "general taxpayer" in contents.lower()
    assert "simplified taxation" in contents.lower()
    # 页码与 bbox 保真
    assert all(b.page_no == 1 for b in blocks)
    assert all(isinstance(b.bbox_json, str) and json.loads(b.bbox_json) for b in blocks)
    headers = [b for b in blocks if b.kind == "heading"]
    assert any("VAT Filing Guide" in h.content for h in headers)
