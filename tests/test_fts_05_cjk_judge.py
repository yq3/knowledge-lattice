"""TC-FTS-05 中文分词效果判据 + 词表/trigram 兜底判定（M0a-1 移交——M1-1 落判据）。

design §10「jieba 中英混排：tokenizer 独立模块（可换 trigram/自定义词表）；M1
真实 query 标注集是判据」+ 调研沉淀（research/enterprise-rag/blog/04:91、
blog/10:87——「应用层 jieba 预分词 + trigram 兜底是同构方案」）：

- **效果判据**（何为不达标）：query 与语料经同一分词器切分后 token 对齐率
  <1.0 即错位——错位则 BM25 召回为空（token 不相交 → MATCH 不命中）；
- **兜底判定**（不达标时启用什么）：
  · `dict`——query 为已知业务术语（运营词表可修）：add_word 后对齐恢复
    （本用例实测验证恢复有效性）；
  · `trigram`——词表不可修（query 与语料无公共词元、仅子串关系可召回）：
    需 FTS trigram 索引/列兜底（schema 变更，黄金集校准后按需启用——M1-4）；
- 黄金集全量校准（真实 query 标注集）留 M1-4 TC-EVAL；本文件为判据落点 +
  小型验证（判据函数行为 + jieba add_word 实效）。
"""

from __future__ import annotations

from knowledge_lattice.adapters.tokenizer import (
    cjk_fallback_verdict,
    segment_query,
    token_alignment,
)

# 实测锚点（jieba 默认词典，2026-10-25 本机固化）：
#   '留抵退税' → ['留抵', '退税']；'留抵退税额 应分别核算' → ['留', '抵退', '税额', …]
#   —— query 与语料错位（'留抵'/'退税' 均不在语料 token 中 → BM25 召回为空）
_QUERY = "留抵退税"
_CONTENT = "留抵退税额 应分别核算"
_SUBSTR_QUERY = "般纳税"  # 语料「一般纳税人」的子串——词表不可修、仅子串可召回


def test_fts_05_alignment_metric_detects_mismatch() -> None:
    """判据①：对齐率——命中语料=1.0；错位（jieba 碎片化）<1.0。"""
    assert token_alignment("出口退税申报", "出口退税申报流程说明") == 1.0
    rate = token_alignment(_QUERY, _CONTENT)
    assert rate < 1.0, "「留抵退税」vs「留抵退税额」默认切分错位——判据应报不达标"
    assert rate == 0.0  # 实测锚点：'留抵'/'退税' 与 ['留','抵退','税额',…] 零交集


def test_fts_05_mismatch_means_bm25_miss(ret_stack) -> None:
    """判据②（后果实证）：token 零交集 → BM25 召回为空——错位即不可达。"""
    from helpers import insert_chunk, seed_doc_dims, seed_document
    from knowledge_lattice.store.backend import AclPlan

    db, backend = ret_stack["db"], ret_stack["backend"]
    seed_document(db, doc_id="d_judge", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_judge", {"region": ["CN"]})
    insert_chunk(
        db, doc_id="d_judge", seq=1, content=_CONTENT,
        content_seg=" ".join(segment_query(_CONTENT)), title_seg="",
        keywords="", llm_keywords="", tags="",
    )
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_judge'")
    db.commit()
    rows = backend.recall_fts(
        segment_query(_QUERY), AclPlan(org_id="org:tax"), top_k=10
    )
    assert rows == [], "对齐率 0 → BM25 零命中（判据与召回后果一致）"


def test_fts_05_verdict_routes_fallback() -> None:
    """判据③（兜底路由）：ok / dict（词表可修）/ trigram（词表不可修）。"""
    assert cjk_fallback_verdict("出口退税申报", "出口退税申报流程说明") == "ok"
    # 错位 + query 为已知业务术语 → 词表兜底
    assert cjk_fallback_verdict(_QUERY, _CONTENT, dict_terms=["留抵退税"]) == "dict"
    # 错位 + 词表不可修（子串关系）→ trigram 兜底
    assert cjk_fallback_verdict(_SUBSTR_QUERY, "一般纳税人") == "trigram"
    assert cjk_fallback_verdict(_QUERY, _CONTENT) == "trigram", (
        "未登记词表时按 trigram 兜底判定（词表是运营前置输入）"
    )


def test_fts_05_dict_fallback_actually_restores_alignment() -> None:
    """小型验证：add_word('留抵退税') 后对齐恢复 1.0（词表兜底路径实测有效）。"""
    import jieba

    jieba.add_word(_QUERY)
    try:
        assert token_alignment(_QUERY, _CONTENT) == 1.0, (
            "业务术语入典后 query/语料同切出整词——对齐恢复（dict 兜底实效）"
        )
        assert segment_query(_CONTENT)[0] == _QUERY  # 语料侧同样切出整词（前缀命中）
    finally:
        jieba.del_word(_QUERY)
        # 还原后回退错位（判定可重复——非永久词典变更）
        assert token_alignment(_QUERY, _CONTENT) == 0.0


def test_fts_05_trigram_fallback_is_substring_recall(ret_stack) -> None:
    """小型验证（trigram 判定语义）：子串关系存在于 LIKE 面——BM25 unicode61 不可达。"""
    from knowledge_lattice.store.backend import AclPlan

    db, backend = ret_stack["db"], ret_stack["backend"]
    # 语料块（同 test_fts_05_mismatch 形态）已有？本用例独立造数
    from helpers import insert_chunk, seed_doc_dims, seed_document

    seed_document(db, doc_id="d_tri", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_tri", {"region": ["CN"]})
    insert_chunk(
        db, doc_id="d_tri", seq=1, content="一般纳税人销售货物",
        content_seg="一般 纳税人 销售 货物", title_seg="",
        keywords="", llm_keywords="", tags="",
    )
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_tri'")
    db.commit()

    tokens = segment_query(_SUBSTR_QUERY)  # ['般', '纳税']
    assert backend.recall_fts(tokens, AclPlan(org_id="org:tax"), top_k=10) == [], (
        "子串 query 在 BM25 路不可达（'般'/'纳税' 不在预分词列）——trigram 判定的依据"
    )
    # 子串关系在 LIKE 面存在（trigram 索引可召回的等价证据）——本用例块的 content
    hit = db.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = 'd_tri' AND content LIKE ?",
        ("%般纳税%",),
    ).fetchone()[0]
    assert hit == 1
