"""Excel 表格型切分（design §3 core/docs/excel_chunking.py——sheet/行块）。

按 sheet 行块切分：每块 = 表头行 + N 数据行（**重复表头**保留列语义——TC-ING-03）；
`sheet_name` 记录进 chunk（FR-1）并进 title_seg（高权列，按 sheet 名可检索）。
"""

from __future__ import annotations

from knowledge_lattice.adapters import tokenizer
from knowledge_lattice.adapters.parser_docling import ParsedBlock
from knowledge_lattice.core.docs.chunking import ChunkDraft

DEFAULT_ROWS_PER_BLOCK = 20


def _row_line(row: tuple[str, ...]) -> str:
    return " | ".join(cell or "" for cell in row)


def chunk_sheet_table(
    block: ParsedBlock, *, doc_title: str, rows_per_block: int = DEFAULT_ROWS_PER_BLOCK
) -> list[ChunkDraft]:
    """单 sheet 表 → 行块 chunk 列表（每块首行重复表头）。"""
    rows = block.rows or ()
    if not rows:
        return []
    header, data_rows = rows[0], rows[1:]
    sheet = block.sheet_name or ""
    title_seg = tokenizer.join_seg(" ".join(x for x in (doc_title, sheet, *header) if x))

    chunks: list[ChunkDraft] = []
    for start in range(0, max(1, len(data_rows)), rows_per_block):
        batch = data_rows[start : start + rows_per_block]
        content = "\n".join([_row_line(header), *(_row_line(r) for r in batch)])
        chunks.append(
            ChunkDraft(
                seq=0,  # chunk_blocks 收尾统一编号
                kind="table",
                content=content,
                heading_path=block.heading_path,
                page_no=block.page_no,
                sheet_name=block.sheet_name,
                bbox_json=block.bbox_json,
                token_count=tokenizer.token_count(content),
                title_seg=title_seg,
                content_seg=tokenizer.join_seg(content),
            )
        )
    return chunks
