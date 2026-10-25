"""TC-QUAL-03 LLM 兜底写独立列【单测｜M1——双后端参数化】。

- 对 open flags 触发 LLM 关键词生成 → 写 `llm_keywords`（独立低权列）+ 一句
  定位语进 `auto_keywords`；
- **不动** `keywords`（人工列）与 embedding（口径如实——非 Contextual
  Retrieval）；
- noop provider（quality_llm=none 默认）零调用零写入。
"""

from __future__ import annotations

from helpers import insert_chunk, seed_doc_dims, seed_document

ORG = "org:tax"
LABEL = "fake-embed:8"
_VEC = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


class FakeKeywordClient:
    """确定性 fake：content → 固定关键词 + 定位语。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, content: str) -> tuple[list[str], str]:
        self.calls.append(content)
        return ["进项抵扣", "专用发票校验"], "本段讲解增值税进项抵扣凭证的查验要求。"


def _seed_flagged(qual_env) -> tuple[str, str]:
    """造一个 open flag（拥挤：同文档两块同向量互为近邻——段落 ≈300 token 各自成块）。"""
    env = qual_env
    db = env["db"]
    para = "重复条款：一般纳税人取得合规扣税凭证后从销项税额中抵减进项税额。" * 18
    doc_id, task_id = env["service"].create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="LLM 兜底样例",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=f"{para}\n\n{para}".encode(), mime_type="text/plain",
        filename="llm.txt",
    )
    env["service"].run_task(task_id)
    assert db.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0] == 2, "拥挤造数前提：应为 2 块"
    flags = env["backend"].list_quality_flags(doc_id, state="open")
    assert flags, "前置失败：应有 open flag"
    return doc_id, flags[0]["chunk_id"]


def test_qual_07_llm_keywords_written_to_independent_column(qual_env) -> None:
    """LLM 兜底：llm_keywords + auto_keywords 落库；keywords/embedding 不动。"""
    from knowledge_lattice.core.docs.quality import QualityService

    env = qual_env
    db = env["db"]
    doc_id, chunk_id = _seed_flagged(env)
    before = db.execute(
        "SELECT c.keywords, c.llm_keywords, cv.embedding FROM chunks c"
        " JOIN chunk_vectors cv ON cv.rid = c.rid AND cv.embed_model = ?"
        " WHERE c.id = ?",
        (LABEL, chunk_id),
    ).fetchone()
    keywords_before, llm_before, emb_before = before

    client = FakeKeywordClient()
    quality = QualityService(env["backend"], env["settings"], keyword_client=client)
    done = quality.run_llm_keywords(org_id=ORG)
    assert done >= 1
    assert client.calls, "LLM provider 应被调用（open flags）"

    after = db.execute(
        "SELECT c.keywords, c.llm_keywords, cv.embedding FROM chunks c"
        " JOIN chunk_vectors cv ON cv.rid = c.rid AND cv.embed_model = ?"
        " WHERE c.id = ?",
        (LABEL, chunk_id),
    ).fetchone()
    keywords_after, llm_after, emb_after = after
    # llm_keywords 独立列写入（低权 0.5~1——加权面在 FTS 层）
    assert "进项抵扣" in llm_after and "专用发票校验" in llm_after
    # 人工列 keywords 不动（来源分层——TC-FTS-04）
    assert keywords_after == keywords_before
    # embedding 不动（非 Contextual Retrieval——口径如实）
    if env["db"].is_sqlite:
        assert emb_after == emb_before  # BLOB 逐字节
    else:
        assert emb_after == emb_before  # pgvector 文本形态

    flag = env["backend"].list_quality_flags(doc_id)[0]
    assert flag["auto_keywords"] == "本段讲解增值税进项抵扣凭证的查验要求。"
    # 审计事件
    events = db.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'quality.llm_keywords'"
    ).fetchone()[0]
    assert events >= 1


def test_qual_08_noop_keyword_client_no_calls(qual_env) -> None:
    """noop（quality_llm=none 默认）：零调用零写入——兜底是增益路非可用性前提。"""
    env = qual_env
    db = env["db"]
    doc_id, chunk_id = _seed_flagged(env)
    before = db.execute(
        "SELECT llm_keywords FROM chunks WHERE id = ?", (chunk_id,)
    ).fetchone()[0]

    done = env["quality"].run_llm_keywords(org_id=ORG)  # qual_env 默认 noop
    assert done == 0
    after = db.execute(
        "SELECT llm_keywords FROM chunks WHERE id = ?", (chunk_id,)
    ).fetchone()[0]
    assert after == before
