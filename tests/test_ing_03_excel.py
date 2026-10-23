"""TC-ING-03 Excel 行块切分【单测｜M0a】。

多 sheet Excel 切分：按 sheet/行块切分；每个行块 chunk 重复表头（保留列语义）；
`sheet_name` 记录（FR-1）。
"""

from __future__ import annotations

from knowledge_lattice.adapters.parser_docling import ParsedBlock
from knowledge_lattice.core.docs.chunking import chunk_blocks


def _sheet_block(sheet: str, n_rows: int, cols: tuple[str, ...] = ("税种", "税率", "备注")) -> ParsedBlock:
    rows = [cols]
    for i in range(n_rows):
        rows.append((f"税种{i}", f"{i}%", f"备注{i}"))
    content = "\n".join(" | ".join(r) for r in rows)
    return ParsedBlock(kind="table", content=content, sheet_name=sheet, rows=tuple(rows), page_no=1)


def test_multi_sheet_row_blocks_with_repeated_header() -> None:
    """两 sheet（22/7 数据行）→ 行块切分、每块首行重复表头、sheet_name 记录。"""
    blocks = [
        _sheet_block("税率表", 22),
        _sheet_block("免税政策", 7),
    ]
    chunks = chunk_blocks(blocks, doc_title="Excel 文档", rows_per_block=20)
    by_sheet: dict[str, list] = {}
    for c in chunks:
        by_sheet.setdefault(c.sheet_name, []).append(c)
    # 税率表：22 行 → 20 + 2 两个行块；免税政策：7 行 → 单块
    assert len(by_sheet["税率表"]) == 2
    assert len(by_sheet["免税政策"]) == 1
    # 每个行块 chunk 重复表头（首行 = 表头）
    for sheet, sheet_chunks in by_sheet.items():
        for c in sheet_chunks:
            assert c.content.startswith("税种 | 税率 | 备注"), f"{sheet} 行块缺表头"
    # sheet_name 记录
    assert set(by_sheet) == {"税率表", "免税政策"}
    # 行内容落进对应行块（不丢行）
    assert "税种19" in by_sheet["税率表"][0].content
    assert "税种20" in by_sheet["税率表"][1].content
    assert "税种21" in by_sheet["税率表"][1].content
    # 表头进入分词列（列语义可检索）
    assert "税种" in by_sheet["税率表"][0].content_seg


def test_sheet_name_in_title_seg() -> None:
    """sheet 名进入 title_seg（高权列——按 sheet 名可检索）。"""
    chunks = chunk_blocks([_sheet_block("免税政策", 3)], doc_title="Excel 文档", rows_per_block=20)
    assert "免税" in chunks[0].title_seg and "政策" in chunks[0].title_seg


def test_small_sheet_single_block() -> None:
    """小 sheet 单块（表头 + 全部行）。"""
    chunks = chunk_blocks([_sheet_block("小表", 5)], doc_title="Excel 文档", rows_per_block=20)
    assert len(chunks) == 1
    assert "税种4" in chunks[0].content
