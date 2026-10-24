"""结构感知切分（design §3 core/docs/chunking.py——docling 结构树 + 递归 token）。

- 递归 token 256–512 打底（TC-ING-02）：结构边界优先（标题章节不跨并、段落边界其次、
  超长段落按句边界递归拆分）；**表格整块不拆散**（超限豁免——§9 切分边界口径）；
  末尾余量允许 < min 成小块；
- `heading_path` 记录层级路径（取块内首块路径）；Excel 表格走 excel_chunking（行块/
  重复表头，TC-ING-03）；
- jieba 生成 `content_seg` / `title_seg`（adapters/tokenizer——§5.3 阶段编排）；
  token 计量 = jieba token 数。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from knowledge_lattice.adapters.parser_docling import ParsedBlock
from knowledge_lattice.adapters import tokenizer

CHUNK_MIN_TOKENS = 256
CHUNK_MAX_TOKENS = 512

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")


@dataclass(frozen=True)
class ChunkDraft:
    """切分产物（index_fts 阶段的输入——content/seg 列与溯源结构字段齐备）。"""

    seq: int
    kind: str  # text | table
    content: str
    heading_path: tuple[str, ...]
    page_no: int | None
    sheet_name: str | None
    bbox_json: str | None
    token_count: int
    title_seg: str
    content_seg: str


def _title_seg(doc_title: str, heading_path: tuple[str, ...]) -> str:
    return tokenizer.join_seg(" ".join((doc_title, *heading_path)).strip())


def _hard_split(sentence: str, max_tokens: int) -> list[str]:
    """单句超限 → 按原文字符区间在 token 边界硬切（jieba.tokenize 带位置——
    P3-5：不经 segment+join，防英文被拼成 `Ageneraltaxpayer`）。"""
    import jieba

    parts: list[str] = []
    buf_start = 0
    count = 0
    for _word, start, _end in jieba.tokenize(sentence):
        if count >= max_tokens:  # 下一 token 将超限 → 在其起点切
            parts.append(sentence[buf_start:start])
            buf_start = start
            count = 0
        count += 1
    parts.append(sentence[buf_start:])
    return parts


def _split_oversized(content: str, max_tokens: int) -> list[str]:
    """超长段落递归拆分：句边界优先，句内仍超按原文字符区间硬切。"""
    parts: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for sentence in _SENTENCE_SPLIT_RE.split(content):
        if not sentence:
            continue
        n = tokenizer.token_count(sentence)
        if n > max_tokens:  # 单句超限 → token 边界硬切
            if buf:
                parts.append("".join(buf))
                buf, buf_tokens = [], 0
            for part in _hard_split(sentence, max_tokens):
                pn = tokenizer.token_count(part)
                if buf_tokens + pn > max_tokens and buf:
                    parts.append("".join(buf))
                    buf, buf_tokens = [], 0
                buf.append(part)
                buf_tokens += pn
            continue
        if buf_tokens + n > max_tokens and buf:
            parts.append("".join(buf))
            buf, buf_tokens = [], 0
        buf.append(sentence)
        buf_tokens += n
    if buf:
        parts.append("".join(buf))
    return [p for p in (part.strip() for part in parts) if p]


def chunk_blocks(
    blocks: Sequence[ParsedBlock],
    *,
    doc_title: str,
    min_tokens: int = CHUNK_MIN_TOKENS,
    max_tokens: int = CHUNK_MAX_TOKENS,
    rows_per_block: int = 20,
) -> list[ChunkDraft]:
    """统一块结构 → 切分草稿（seq 从 1 起；表格/Excel 行块独立成块）。"""
    chunks: list[ChunkDraft] = []
    buf: list[ParsedBlock] = []
    buf_tokens = 0
    buf_path: tuple[str, ...] = ()

    def _flush() -> None:
        nonlocal buf, buf_tokens
        if not buf:
            return
        content = "\n".join(b.content for b in buf)
        chunks.append(
            ChunkDraft(
                seq=0,  # 统一编号在收尾
                kind="text",
                content=content,
                heading_path=buf_path or buf[0].heading_path,
                page_no=buf[0].page_no,
                sheet_name=None,
                bbox_json=buf[0].bbox_json,
                token_count=tokenizer.token_count(content),
                title_seg=_title_seg(doc_title, buf_path or buf[0].heading_path),
                content_seg=tokenizer.join_seg(content),
            )
        )
        buf, buf_tokens = [], 0

    for block in blocks:
        if block.kind == "table":
            _flush()
            if block.sheet_name is not None and block.rows:
                # Excel 表：sheet 行块切分（重复表头——TC-ING-03）
                from knowledge_lattice.core.docs.excel_chunking import chunk_sheet_table

                chunks.extend(
                    chunk_sheet_table(block, doc_title=doc_title, rows_per_block=rows_per_block)
                )
            else:
                # 非表格结构（docx/pdf 表等）——整块不拆（超限豁免——§9 切分边界口径）
                chunks.append(
                    ChunkDraft(
                        seq=0,
                        kind="table",
                        content=block.content,
                        heading_path=block.heading_path,
                        page_no=block.page_no,
                        sheet_name=block.sheet_name,
                        bbox_json=block.bbox_json,
                        token_count=tokenizer.token_count(block.content),
                        title_seg=_title_seg(doc_title, block.heading_path),
                        content_seg=tokenizer.join_seg(block.content),
                    )
                )
            continue

        if block.kind == "heading":
            # 结构边界优先：已有足量块 → 先收束再开新章
            if buf and buf_tokens >= min_tokens:
                _flush()
            buf_path = block.heading_path + (block.content,)
            buf.append(block)
            buf_tokens += tokenizer.token_count(block.content)
            continue

        n = tokenizer.token_count(block.content)
        if n > max_tokens:  # 超长段落先递归拆分再入流
            _flush()
            for part in _split_oversized(block.content, max_tokens):
                pn = tokenizer.token_count(part)
                # P2-2：溢出即 flush（无 min_tokens 前置）——否则 100+450 并入成 550
                # 非末块，违反 TC-ING-02 的 256–512 上限（欠 min 的碎块由结构边界
                # 自然合并，硬上限不破）
                if buf_tokens + pn > max_tokens and buf:
                    _flush()
                    buf_path = block.heading_path
                buf.append(
                    ParsedBlock(
                        kind="text", content=part, heading_path=block.heading_path,
                        page_no=block.page_no, bbox_json=block.bbox_json,
                    )
                )
                buf_tokens += pn
            continue

        # P2-2：同上——溢出即 flush，去掉 buf_tokens >= min_tokens 前置
        if buf_tokens + n > max_tokens and buf:
            _flush()
            buf_path = block.heading_path
        if not buf:
            buf_path = block.heading_path
        buf.append(block)
        buf_tokens += n

    _flush()
    return [
        ChunkDraft(
            **{
                **c.__dict__,
                "seq": i,
            }
        )
        for i, c in enumerate(chunks, start=1)
    ]
