"""TC-FTS-02 五列加权【单测｜M0a】。

五个 chunk 分别只在 tags / keywords / title_seg / content_seg / llm_keywords 含目标词；
`bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)` 排序（五列按序 title/content/keywords/llm/tags）：
排序 tags(8) > keywords(5) > title_seg(3) > content_seg(1) > llm_keywords(0.5)。
（sqlite-only——bm25() 为 SQLite FTS5 评分。）
"""

from __future__ import annotations

from helpers import insert_chunk, seed_document

from knowledge_lattice.store.backend import AclPlan

_BM25_ARGS = "3.0, 1.0, 5.0, 0.5, 8.0"


def _seed_five(sqlite_matrix) -> None:
    seed_document(sqlite_matrix, doc_id="d_w", dataset_id="ds:vat_lib", owner_user_id="u_full")
    for seq, col in enumerate(
        ("tags", "keywords", "title_seg", "content_seg", "llm_keywords"), start=1
    ):
        row: dict[str, object] = {c: "" for c in
                                  ("tags", "keywords", "title_seg", "content_seg", "llm_keywords")}
        row[col] = "目标词"
        insert_chunk(sqlite_matrix, doc_id="d_w", seq=seq, content="占位", **row)
    sqlite_matrix.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_w'")


def test_bm25_weight_order_via_backend(sqlite_matrix) -> None:
    """经 recall_fts（bm25 加权 ORDER BY）名次：tags > keywords > title > content > llm。"""
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    _seed_five(sqlite_matrix)
    backend = SqliteBackend(sqlite_matrix)
    rows = backend.recall_fts(["目标词"], AclPlan(org_id="org:tax"), top_k=10)
    # seq 1..5 分别只在 tags/keywords/title_seg/content_seg/llm_keywords 含目标词
    assert [r["chunk_id"] for r in rows] == [f"chk:d_w:v1:{i}" for i in (1, 2, 3, 4, 5)]


def test_bm25_weight_order_raw_sql(sqlite_matrix) -> None:
    """直查 FTS 评分函数：bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0) 升序同名次（渲染器同款参数）。"""
    _seed_five(sqlite_matrix)
    rows = sqlite_matrix.execute(
        "SELECT c.tags, c.keywords, c.title_seg, c.content_seg, c.llm_keywords,"
        f" bm25(chunks_fts, {_BM25_ARGS}) AS s"
        " FROM chunks_fts f JOIN chunks c ON c.rid = f.rowid"
        " WHERE chunks_fts MATCH '目标词' ORDER BY s ASC"
    ).fetchall()
    assert len(rows) == 5
    nonempty_cols = [
        next(col for col in ("tags", "keywords", "title_seg", "content_seg", "llm_keywords")
             if r[["tags", "keywords", "title_seg", "content_seg", "llm_keywords"].index(col)] != "")
        for r in rows
    ]
    assert nonempty_cols == ["tags", "keywords", "title_seg", "content_seg", "llm_keywords"]
