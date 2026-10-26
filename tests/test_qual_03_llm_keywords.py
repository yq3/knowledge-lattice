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
    """LLM 兜底：llm_keywords + auto_keywords 落库；keywords/embedding 不动。

    P1-1（R2 红灯自证改造）：provider 入参必须是**块正文**（R1 缺陷——flag 行
    无 content 字段，空串直传 provider）；空内容块跳过、不发起调用。
    """
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
    # P1-1 断言：入参为块正文（非空 + 含已知正文片段——修前空串直传必红）
    assert client.calls, "provider 调用记录非空"
    assert all(c.strip() for c in client.calls), (
        f"provider 收到空内容（P1-1）：{client.calls!r}"
    )
    assert any("合规扣税凭证" in c for c in client.calls), (
        "provider 入参应含块正文片段（P1-1——chunks_by_rids 取 content）"
    )

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


def test_qual_07b_llm_keywords_empty_content_skipped(qual_env) -> None:
    """P1-1 边界：空内容块（content=''）跳过——不发起调用、不写 llm_keywords
    （防空串清空既有值）。"""
    from knowledge_lattice.core.docs.quality import QualityService

    env = qual_env
    db = env["db"]
    # 直接造 flag：chunk 正文为空串
    seed_document(db, doc_id="d_empty_content", dataset_id="ds:vat_lib",
                  owner_user_id="u_owner")
    seed_doc_dims(db, "d_empty_content", {"region": ["CN"]})
    empty_chunk = insert_chunk(
        db, doc_id="d_empty_content", seq=1, content="", content_seg="",
        llm_keywords="既有兜底词",
    )
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_empty_content'")
    db.commit()
    env["backend"].insert_quality_flag(
        chunk_id=empty_chunk, doc_id="d_empty_content",
        reason="low_idf", detail_json="{}",
    )

    client = FakeKeywordClient()
    quality = QualityService(env["backend"], env["settings"], keyword_client=client)
    done = quality.run_llm_keywords(org_id=ORG)
    assert done == 0, "空内容块应跳过（不计入 done）"
    assert client.calls == [], "空内容块不得发起 provider 调用"
    kept = db.execute(
        "SELECT llm_keywords FROM chunks WHERE id = ?", (empty_chunk,)
    ).fetchone()[0]
    assert kept == "既有兜底词", "空 terms 不得清空既有 llm_keywords"


def test_qual_07c_llm_keywords_locator_only_keeps_existing(qual_env) -> None:
    """P1-1 半产出边界：provider 只回定位语（terms 空）→ 仅写 auto_keywords，
    llm_keywords 保留既有值（空串写入会清列——同样防护）。"""
    from knowledge_lattice.core.docs.quality import QualityService

    env = qual_env
    db = env["db"]
    doc_id, chunk_id = _seed_flagged(env)
    db.execute(
        "UPDATE chunks SET llm_keywords = '既有兜底词乙' WHERE id = ?", (chunk_id,)
    )
    db.commit()

    class LocatorOnlyClient:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, content: str) -> tuple[list[str], str]:
            self.calls += 1
            return [], "只给定位语不给关键词。"

    quality = QualityService(
        env["backend"], env["settings"], keyword_client=LocatorOnlyClient()
    )
    done = quality.run_llm_keywords(org_id=ORG)
    assert done >= 1
    kept = db.execute(
        "SELECT llm_keywords FROM chunks WHERE id = ?", (chunk_id,)
    ).fetchone()[0]
    assert kept == "既有兜底词乙", "terms 为空不得清空既有 llm_keywords"
    flag = env["backend"].list_quality_flags(doc_id)[0]
    assert flag["auto_keywords"] == "只给定位语不给关键词。"


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


def test_qual_08b_llm_keywords_hooked_into_quality_stage(qual_env) -> None:
    """P2-2（R2）：LLM 兜底接入摄取 quality 阶段——IngestService 挂 fake provider
    端到端：摄取完成（run_task done）→ 检测产生 flag → **doc 作用域兜底自动
    执行** → llm_keywords/auto_keywords 落库。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.docs.quality import QualityService

    env = qual_env
    db = env["db"]
    client = FakeKeywordClient()
    quality = QualityService(
        env["backend"], env["settings"], keyword_client=client
    )
    service = IngestService(
        env["backend"], env["embedder"], env["settings"], EmbeddingGate(),
        env["objects_dir"], quality=quality,
    )
    para = "重复条款：一般纳税人取得合规扣税凭证后从销项税额中抵减进项税额。" * 18
    doc_id, task_id = service.create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="兜底挂接样例",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=f"{para}\n\n{para}".encode(), mime_type="text/plain",
        filename="hook.txt",
    )
    service.run_task(task_id)

    assert db.execute(
        "SELECT status FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()[0] == "done"
    flags = env["backend"].list_quality_flags(doc_id, state="open")
    assert flags, "前置失败：quality 阶段应产生 flag"
    # 兜底自动执行：provider 收到块正文、llm_keywords/auto_keywords 已落库
    assert client.calls and all(c.strip() for c in client.calls)
    assert any("合规扣税凭证" in c for c in client.calls)
    for flag in flags:
        row = db.execute(
            "SELECT llm_keywords FROM chunks WHERE id = ?", (flag["chunk_id"],)
        ).fetchone()
        assert row[0] == "进项抵扣 专用发票校验", (
            f"摄取完成即兜底落库（P2-2）：{flag['chunk_id']} → {row[0]!r}"
        )
        assert flag["auto_keywords"] == "本段讲解增值税进项抵扣凭证的查验要求。"


def test_qual_08c_noop_provider_hook_costs_nothing(qual_env) -> None:
    """P2-2 零成本断言：noop provider（quality_llm=none）挂接摄取——run_task
    正常完成、无 llm_keywords 写入（早返回零调用）。"""
    env = qual_env
    db = env["db"]
    para = "重复条款：一般纳税人取得合规扣税凭证后从销项税额中抵减进项税额。" * 18
    doc_id, task_id = env["service"].create_document(  # qual_env：noop provider
        org_id=ORG, dataset_id="ds:vat_lib", title="noop 挂接样例",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=f"{para}\n\n{para}".encode(), mime_type="text/plain",
        filename="noop-hook.txt",
    )
    env["service"].run_task(task_id)
    assert db.execute(
        "SELECT status FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()[0] == "done"
    written = db.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND llm_keywords != ''",
        (doc_id,),
    ).fetchone()[0]
    assert written == 0, "noop provider 不得产生 llm_keywords 写入"
