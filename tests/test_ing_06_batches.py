"""TC-ING-06 嵌入分批与钉标签【单测｜M1——双后端参数化】（v1.6 随 v1.1 写路径）。

- 摄取 >64 块文档（Embedder fake——D12 形态）：逐批写 chunk_vectors(rid,
  embed_model, embedding)；分批 64（embed 调用切片 64/64/余量）；每行
  embed_model = '<model>:<dim>' 标签；
- 待嵌清点谓词 = chunks 无 (rid, :label) cv 行；
- 批次间断点续跑（批次失败 → 重跑从缺向量块续，不重嵌已完成块）。
"""

from __future__ import annotations

from helpers import insert_chunk

ORG = "org:tax"

# 段落 ≈300 jieba token（>256 min）：66 段各成块（相邻 300+300 > 512 溢出 flush）
_PARA_TMPL = "专项规定条款第{n}号：增值税一般纳税人销售货物并提供安装服务应当分别核算销售额与安装服务的销售额，未分别核算的从高适用税率。"


def _big_txt(n_paragraphs: int) -> bytes:
    paras = [
        (_PARA_TMPL.format(n=i) + "序列标记词甲乙丙丁。") * 9 for i in range(n_paragraphs)
    ]
    return ("批量嵌入样例文档\n\n" + "\n\n".join(paras)).encode("utf-8")


def test_ing_06_batched_embeddings_and_labels(qual_env) -> None:
    """>64 块：chunk_vectors 全量落标签行；embed 调用按 64 分批；谓词不漏不重。"""
    env = qual_env
    db, backend, label = env["db"], env["backend"], env["label"]
    n_expected = 66
    doc_id, task_id = env["service"].create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="批量嵌入样例",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=_big_txt(n_expected), mime_type="text/plain", filename="bulk.txt",
    )
    env["service"].run_task(task_id)

    n_chunks = db.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0]
    assert n_chunks == n_expected, f"切分前提：{n_expected} 块（got {n_chunks}）"

    # 逐批写入 chunk_vectors：全量 66 行、标签一致、维度匹配
    rows = db.execute(
        "SELECT count(*) FROM chunk_vectors cv JOIN chunks c ON c.rid = cv.rid"
        " WHERE c.doc_id = ? AND cv.embed_model = ?",
        (doc_id, label),
    ).fetchone()[0]
    assert rows == n_expected
    # embed 调用切片 = 64 分批（66 → 64 + 2）
    call_sizes = [len(c) for c in env["embedder"].calls]
    assert call_sizes == [64, 2], f"分批 64 预期（got {call_sizes}）"
    # 待嵌清点谓词（v1.1 等价）：已完成块不再进清单
    assert backend.pending_embeddings(label) == []
    # chunks.embed_model 摄取状态标签 = 批次标签（认领钉死）
    states = db.execute(
        "SELECT DISTINCT embed_model FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchall()
    assert states == [(label,)]


def test_ing_06_resume_after_batch_failure(qual_env) -> None:
    """断点续跑：批次中途失败 → 任务 failed；重跑从缺向量块续（已完成块不重嵌）。"""
    from fake_providers import FakeEmbedder

    env = qual_env
    db = env["db"]
    label = env["label"]

    class FailAfterFirstBatch:
        """首批成功、第二批 raise（批次中断造数——TC-ING-06/TC-ING-07 缝）。"""

        def __init__(self) -> None:
            self.inner = FakeEmbedder(dim=8, model_name="fake-embed")
            self.calls = 0

        @property
        def model_label(self) -> str:
            return self.inner.model_label

        def embed(self, texts):
            self.calls += 1
            if self.calls >= 2:
                raise ConnectionError("embedding endpoint unreachable (fake)")
            return self.inner.embed(texts)

    failing = FailAfterFirstBatch()
    settings = env["settings"]
    from knowledge_lattice.core.docs.ingest import IngestService

    svc = IngestService(env["backend"], failing, settings, env["gate"], env["objects_dir"])
    doc_id, task_id = svc.create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="断点续跑样例",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=_big_txt(70), mime_type="text/plain", filename="resume.txt",
    )
    import pytest

    with pytest.raises(ConnectionError):
        svc.run_task(task_id)
    assert env["backend"].get_task(task_id)["status"] == "failed"
    written = db.execute(
        "SELECT count(*) FROM chunk_vectors cv JOIN chunks c ON c.rid = cv.rid"
        " WHERE c.doc_id = ? AND cv.embed_model = ?",
        (doc_id, label),
    ).fetchone()[0]
    assert written == 64, "首批 64 已回写（中断于第二批）"

    # 重跑（正常 embedder）：只嵌剩余块——经 pending 谓词续跑
    svc_ok = IngestService(
        env["backend"], env["embedder"], settings, env["gate"], env["objects_dir"]
    )
    svc_ok.run_task(task_id)
    task = env["backend"].get_task(task_id)
    assert task["status"] == "done"
    total = db.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0]
    final = db.execute(
        "SELECT count(*) FROM chunk_vectors cv JOIN chunks c ON c.rid = cv.rid"
        " WHERE c.doc_id = ? AND cv.embed_model = ?",
        (doc_id, label),
    ).fetchone()[0]
    assert final == total == 70, "续跑补齐全部向量"
    # 续跑批大小 = 剩余 6（70−64）——已完成块不重嵌
    resume_sizes = [len(c) for c in env["embedder"].calls]
    assert resume_sizes == [6], f"续跑应只嵌剩余块（got {resume_sizes}）"
