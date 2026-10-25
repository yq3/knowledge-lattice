"""TC-FTS-04 keywords 列人工词纯净性【单测｜M1——双后端参数化】。

- `keywords` 仅含人工提交词（jieba 高频词不混入——重复会被 ×5 加权放大，#32 P1-3）；
- `llm_keywords` 仅由质量环 LLM 写入（来源分层：内容不交叉）；
- jieba 分词只产 `content_seg` / `title_seg`。

载体申报：PATCH /api/quality-flags/{id} 端点随 M1 区分度环（M1-4 段）实装——本
用例按「人工词写入 keywords 列」造数（列语义与 PATCH 写入同源），断言落在列纯
净性与加权放大面。
"""

from __future__ import annotations

from helpers import insert_chunk, seed_doc_dims, seed_document
from knowledge_lattice.adapters.tokenizer import segment


def test_fts_04_keywords_only_manual_terms(ret_stack) -> None:
    """keywords 仅含人工词：jieba 切分产物与 keywords 列零交集；权重放大面不污染。"""
    db = ret_stack["db"]
    content = "增值税一般纳税人销售货物并提供安装服务的，应当分别核算销售额"
    manual_words = "人工标记词 业务术语"  # 人工补标写入（PATCH 同源语义）
    llm_words = "LLM增强词"           # 质量环 LLM 写入

    seed_document(db, doc_id="d_kw", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_kw", {"region": ["CN"]})
    insert_chunk(
        db, doc_id="d_kw", seq=1, content=content,
        content_seg=" ".join(segment(content)),  # jieba 只产 content_seg/title_seg
        title_seg=" ".join(segment(content)),
        keywords=manual_words,                   # 人工提交词（来源：人工）
        llm_keywords=llm_words,                  # LLM 写入（来源：质量环）
        tags="",
    )
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_kw'")
    db.commit()

    row = db.execute(
        "SELECT keywords, llm_keywords, content_seg, title_seg FROM chunks"
        " WHERE doc_id = 'd_kw' AND tombstone = 0"
    ).fetchone()
    keywords, llm_keywords, content_seg, title_seg = row

    # ① 来源分层：keywords = 人工词集合、llm_keywords = LLM 词——写入面不交叉
    #（列级字面断言：各自列只含本来源写入的词面；token 级碎片共现不作断言——
    #  jieba 对「人工标记词」等非词典词的碎片切分与本用例无关）
    assert keywords == manual_words
    assert llm_keywords == llm_words
    for term in manual_words.split():
        assert term not in llm_keywords
    assert "LLM增强词" not in keywords

    # ② jieba 高频词不混入 keywords：分词产物与人工词列零交集
    jieba_tokens = set(segment(content))
    assert jieba_tokens & set(segment(keywords)) == set(), (
        "jieba 分词只产 content_seg/title_seg——keywords 列不得混入分词产物"
        "（重复词会被 ×5 加权放大）"
    )
    assert jieba_tokens & set(segment(llm_keywords)) == set()

    # ③ content_seg/title_seg 确为 jieba 形态（空格连接 token——与 keywords 写法可区分）
    assert content_seg == " ".join(segment(content))
    assert title_seg == " ".join(segment(content))
    # 人工词不在 jieba 产物中（列间零渗透的另一面）
    assert set(segment(keywords)).isdisjoint(jieba_tokens)


def test_fts_04_manual_keyword_weight_amplifies(ret_stack) -> None:
    """人工词 ×5 加权面（#32 P1-3 动机复验）：keywords 命中块名次高于 content 命中块。"""
    from knowledge_lattice.store.backend import AclPlan

    db, backend = ret_stack["db"], ret_stack["backend"]
    seed_document(db, doc_id="d_kw2", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_kw2", {"region": ["CN"]})
    insert_chunk(
        db, doc_id="d_kw2", seq=1, content="正文块", content_seg="独占词",
        title_seg="", keywords="", llm_keywords="", tags="",
    )
    insert_chunk(
        db, doc_id="d_kw2", seq=2, content="人工块", content_seg="",
        title_seg="", keywords="独占词", llm_keywords="", tags="",
    )
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_kw2'")
    db.commit()

    rows = backend.recall_fts(["独占词"], AclPlan(org_id="org:tax"), top_k=10)
    assert rows and rows[0]["chunk_id"] == "chk:d_kw2:v1:2", (
        "keywords(×5) 命中块名次应高于 content_seg(×1) 命中块——人工词纯净性保住加权收益"
    )
    assert [r["rank"] for r in rows] == [1, 2]
