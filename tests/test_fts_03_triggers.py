"""TC-FTS-03 同步触发器与切换清列【单测｜M0a】。

① INSERT/DELETE chunk 后核对 FTS 行；② UPDATE 五列之一后核对（au 触发器先 'delete' 后插入）；
③ 模拟版本切换的 UPDATE（五列清空、tombstone=1）后以旧内容 MATCH → 零命中
（FTS 层无 tombstone 内容——机制层；矩阵层见 T9）。
"""

from __future__ import annotations

from helpers import insert_chunk, seed_document

from knowledge_lattice.store.backend import AclPlan
from knowledge_lattice.store.sqlite.backend import SqliteBackend


def _fts_row(conn, rid: int) -> tuple | None:
    return conn.execute(
        "SELECT title_seg, content_seg FROM chunks_fts WHERE rowid = ?", (rid,)
    ).fetchone()


def _match_rids(conn, term: str) -> set[int]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?", (f'"{term}"',)
        )
    }


def _setup(sqlite_matrix) -> int:
    seed_document(sqlite_matrix, doc_id="d_t3", dataset_id="ds:vat_lib", owner_user_id="u_full")
    insert_chunk(
        sqlite_matrix,
        doc_id="d_t3",
        seq=1,
        version=1,
        content="留抵退税申请条件说明",
        content_seg="留抵退税 申请 条件",
        title_seg="税务政策标题",
    )
    rid = sqlite_matrix.execute("SELECT rid FROM chunks WHERE doc_id = 'd_t3' AND seq = 1").fetchone()
    return rid[0]


def test_insert_delete_fts_consistency(sqlite_matrix) -> None:
    """① INSERT 后 FTS 行在（五列同步）；DELETE 后 FTS 行移除（ad 触发器）。"""
    rid = _setup(sqlite_matrix)
    assert _match_rids(sqlite_matrix, "留抵退税") == {rid}
    sqlite_matrix.execute("DELETE FROM chunks WHERE rid = ?", (rid,))
    assert _match_rids(sqlite_matrix, "留抵退税") == set()
    assert _fts_row(sqlite_matrix, rid) is None


def test_update_column_fts_consistency(sqlite_matrix) -> None:
    """② UPDATE 五列之一（content_seg）后 FTS 同步（au：旧词归零、新词命中）。"""
    rid = _setup(sqlite_matrix)
    assert _match_rids(sqlite_matrix, "留抵退税") == {rid}
    sqlite_matrix.execute(
        "UPDATE chunks SET content_seg = '进项转出 新词' WHERE rid = ?", (rid,)
    )
    assert _match_rids(sqlite_matrix, "留抵退税") == set()
    assert _match_rids(sqlite_matrix, "进项转出") == {rid}
    row = _fts_row(sqlite_matrix, rid)
    assert row is not None and row[1] == "进项转出 新词"


def test_switch_clear_columns_zero_match(sqlite_matrix) -> None:
    """③ 版本切换形态 UPDATE（五列清空 + tombstone=1）→ 旧内容 MATCH 零命中。"""
    rid = _setup(sqlite_matrix)
    assert _match_rids(sqlite_matrix, "留抵退税") == {rid}
    sqlite_matrix.execute(
        "UPDATE chunks SET tombstone = 1,"
        " title_seg = '', content_seg = '', keywords = '', llm_keywords = '', tags = ''"
        " WHERE rid = ?",
        (rid,),
    )
    # v1.1：旧版本向量清理 = 删 chunk_vectors 行（分表形态；原 UPDATE embedding=NULL）
    sqlite_matrix.execute("DELETE FROM chunk_vectors WHERE rid = ?", (rid,))
    assert _match_rids(sqlite_matrix, "留抵退税") == set()
    # 残留空行不影响 MATCH（#33 P0-2.4/T9）
    assert _fts_row(sqlite_matrix, rid) == ("", "")


def test_switch_clear_then_recall_fts_zero(sqlite_matrix) -> None:
    """清列后经检索链（recall_fts：MATCH + tombstone=0 + 版本条件）零命中——T9 机制层复证。"""
    _setup(sqlite_matrix)
    sqlite_matrix.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_t3'")
    rid = sqlite_matrix.execute("SELECT rid FROM chunks WHERE doc_id = 'd_t3'").fetchone()[0]
    sqlite_matrix.execute(
        "UPDATE chunks SET tombstone = 1, title_seg = '', content_seg = '',"
        " keywords = '', llm_keywords = '', tags = '' WHERE rid = ?",
        (rid,),
    )
    backend = SqliteBackend(sqlite_matrix)
    rows = backend.recall_fts(["留抵退税"], AclPlan(org_id="org:tax"), top_k=10)
    assert rows == []
