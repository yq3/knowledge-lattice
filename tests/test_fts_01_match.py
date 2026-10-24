"""TC-FTS-01 MATCH 转义【单测｜M0a】。

构造 query 含 `"`、`*`、`NEAR`、`AND`、`-`、空格、全角字符；经 jieba 切分后拼查询串执行 MATCH：
- 每个 token 以双引号包裹、内部 `"` 转义为 `""`，token 间以 `OR` 拼接；
- 无 malformed 异常、操作符不被激活（AND/NEAR 作字面量可命中含该字面量的块——design §4 查询侧口径）。
"""

from __future__ import annotations

import pytest
from helpers import insert_chunk, seed_document

from knowledge_lattice.adapters import tokenizer
from knowledge_lattice.store.sqlite.fts import build_match_expr, escape_token


def test_escape_token_double_quote() -> None:
    """内部 `"` → `""`（防御纵深：jieba 通常切开引号，此处直测转义函数）。"""
    assert escape_token('x"y') == '"x""y"'
    assert escape_token('增值税') == '"增值税"'


def test_expr_shape_or_join_and_quoted() -> None:
    """token 间 OR 拼接、每个 token 双引号包裹（合成 token 直测，含全角/操作符）。"""
    expr = build_match_expr(["留抵退税", "AND", 'a"b', "（全角"])
    assert expr == '"留抵退税" OR "AND" OR "a""b" OR "（全角"'


def test_expr_special_query_tokens_dropped_punct_only() -> None:
    """纯标点 token（`*`、`-`、空串）不进表达式——unicode61 不索引纯标点、且空 token 有 malformed 风险。"""
    expr = build_match_expr(["增值税", "*", "-", "", "  "])
    assert expr == '"增值税"'


@pytest.mark.parametrize(
    "query",
    [
        '增值税 "留抵退税" 申请',
        "留抵退税 AND NEAR 条件",
        "发票 * -0.03 税率",
        "全角（括号）测试",
        'a"b AND c',
    ],
)
def test_no_malformed_on_special_queries(sqlite_matrix, query) -> None:
    """特殊字符 query 经 jieba 切分拼串后执行 MATCH 不抛 malformed（零命中也合法）。"""
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    seed_document(sqlite_matrix, doc_id="d_q", dataset_id="ds:vat_lib", owner_user_id="u_full")
    insert_chunk(sqlite_matrix, doc_id="d_q", seq=1, content_seg="普通内容")
    tokens = tokenizer.segment_query(query)
    expr = build_match_expr(tokens)
    for tok in tokens:
        assert f'"{tok.replace(chr(34), chr(34) * 2)}"' in expr or not tok.strip()
    rows = list(sqlite_matrix.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?", (expr,)))
    assert isinstance(rows, list)  # 无 sqlite3.OperationalError 即未 malformed


def test_operators_as_literals_match(sqlite_matrix) -> None:
    """AND / NEAR 作为字面量可命中含该字面量的块（不被激活为操作符）。"""
    seed_document(sqlite_matrix, doc_id="d_op", dataset_id="ds:vat_lib", owner_user_id="u_full")
    insert_chunk(
        sqlite_matrix,
        doc_id="d_op",
        seq=1,
        content_seg="条件 AND 逻辑 NEAR 邻近 增值税 留抵",
        content="条件 AND 逻辑 NEAR 邻近",
    )
    expr = build_match_expr(tokenizer.segment_query("AND NEAR"))
    assert '"AND" OR "NEAR"' == expr
    rows = list(sqlite_matrix.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?", (expr,)))
    assert rows, "操作符字面量应命中含该字面量的块"


def test_fullwidth_and_space_query_hits(sqlite_matrix) -> None:
    """空格/全角混排 query 正常召回（jieba 切分后 OR 语义）。"""
    seed_document(sqlite_matrix, doc_id="d_fw", dataset_id="ds:vat_lib", owner_user_id="u_full")
    insert_chunk(
        sqlite_matrix, doc_id="d_fw", seq=1, content_seg="留抵 退税 申请 条件", content="留抵退税申请条件"
    )
    expr = build_match_expr(tokenizer.segment_query("留抵退税（申请）"))
    rows = list(sqlite_matrix.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?", (expr,)))
    assert rows
