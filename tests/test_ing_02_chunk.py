"""TC-ING-02 结构感知切分【单测｜M0a】。

对带层级的文档切分；统计块 token 数：递归 token 256–512 打底、结构边界优先；
`heading_path` 记录层级路径；表格整块不拆散（§9 切分边界口径）。
"""

from __future__ import annotations

from knowledge_lattice.adapters import tokenizer
from knowledge_lattice.adapters.parser_docling import ParsedBlock
from knowledge_lattice.core.docs.chunking import CHUNK_MAX_TOKENS, CHUNK_MIN_TOKENS, chunk_blocks


def _para(marker: str, repeats: int = 50) -> str:
    """~2 token/重复 的段落（50 重复 ≈ 100 token——可预算的块体量）。"""
    return ("增值税申报 " + marker) * repeats


def test_recursive_token_range_and_structure_boundary() -> None:
    """段落按结构边界打包：非末块 token ∈ [256,512]、跨标题不并包。"""
    blocks = [
        ParsedBlock(kind="heading", content="总则", level=1),
        ParsedBlock(kind="text", content=_para("甲")),
        ParsedBlock(kind="text", content=_para("乙")),
        ParsedBlock(kind="text", content=_para("丙")),
        ParsedBlock(kind="heading", content="细则", level=1),
        ParsedBlock(kind="text", content=_para("丁")),
        ParsedBlock(kind="text", content=_para("戊")),
        ParsedBlock(kind="text", content=_para("己")),
    ]
    chunks = chunk_blocks(blocks, doc_title="测试文档")
    # 两个标题章节 → 各自成块（结构边界优先）
    assert len(chunks) == 2
    for ch in chunks:
        assert CHUNK_MIN_TOKENS <= ch.token_count <= CHUNK_MAX_TOKENS
    assert chunks[0].heading_path == ("总则",)
    assert chunks[1].heading_path == ("细则",)
    assert "甲" in chunks[0].content and "丙" in chunks[0].content
    assert "丁" in chunks[1].content and "己" in chunks[1].content
    # 分词列已生成（content_seg/title_seg——FTS 五列的输入）
    assert "增值税" in chunks[0].content_seg and "甲" in chunks[0].content_seg
    assert "总则" in chunks[0].title_seg or "测试文档" in chunks[0].title_seg


def test_heading_path_multilevel() -> None:
    """多级标题路径（parse 产物已带 heading_path——chunk 记录首块路径）。"""
    blocks = [
        ParsedBlock(kind="text", content=_para("甲", 130), heading_path=("指南", "第一章")),
    ]
    chunks = chunk_blocks(blocks, doc_title="测试文档")
    assert chunks[0].heading_path == ("指南", "第一章")


def test_oversized_paragraph_recursive_split() -> None:
    """单段超 512 token → 递归按句边界拆分（每块 ≤512、内容不丢）。"""
    big = "。".join(_para(f"段{i}", 40) for i in range(10)) + "。"  # ~800 token
    blocks = [ParsedBlock(kind="text", content=big)]
    chunks = chunk_blocks(blocks, doc_title="超长文档")
    assert len(chunks) >= 2
    assert all(c.token_count <= CHUNK_MAX_TOKENS for c in chunks)
    joined = "".join(c.content for c in chunks)
    for i in range(10):
        assert f"段{i}" in joined


def test_table_block_atomic() -> None:
    """表格整块不拆散（含超限表——§9 切分边界口径）。"""
    rows = tuple(("税种", "税率", f"备注{i}") for i in range(300))  # 远超 512 token
    table_content = "\n".join(" | ".join(r) for r in rows)
    blocks = [
        ParsedBlock(kind="text", content=_para("前文")),
        ParsedBlock(kind="table", content=table_content, rows=rows),
    ]
    chunks = chunk_blocks(blocks, doc_title="表格文档")
    tables = [c for c in chunks if c.kind == "table"]
    assert len(tables) == 1  # 不拆
    assert tables[0].token_count > CHUNK_MAX_TOKENS  # 表格豁免上限（整块）
    assert "备注299" in tables[0].content


def test_tail_chunk_below_min_allowed() -> None:
    """末尾余量 < 256 允许成小块（不为凑数硬并）。"""
    blocks = [
        ParsedBlock(kind="text", content=_para("甲", 250)),  # ≈500 token，近上限
        ParsedBlock(kind="text", content="结尾短段。"),
    ]
    chunks = chunk_blocks(blocks, doc_title="尾块文档")
    assert len(chunks) == 2
    assert chunks[-1].token_count < CHUNK_MIN_TOKENS
    assert "结尾短段" in chunks[-1].content


def test_token_count_matches_content() -> None:
    """token_count 与 content 实测一致（切分计量的可信度）。"""
    blocks = [ParsedBlock(kind="text", content=_para("甲"))]
    chunks = chunk_blocks(blocks, doc_title="计量")
    assert chunks[0].token_count == tokenizer.token_count(chunks[0].content)
