"""Committer R1 审查项回归（P2-1~6 + P3 顺手项——每条修复的防回归断言）。

（命名注：`test_r2_review_fixes.py` 为 M0a-2 存量文件，本文件是 M0a-3 的 R2 回归。）

- P2-1 one-shot 上传 embed 失败 → active_error 落库、文档停 searchable_lexical、任务 failed
- P2-2 100+450 token 相邻段 → 溢出即 flush，无 >512 非末块
- P2-3 core 不再 import SQLite 方言序列化（write_embeddings 收浮点向量）
- P2-4 prod 下 dimensions/datasets 路由可达（非 404）；dev token 路由 404
- P2-5 prod 下 dev 默认密钥签发的 JWT → 401
- P2-6 启动/周期探针经 asyncio.to_thread（源级断言 + ticker 不被慢探针阻塞）
- P3-1 stop_after 中断 → 任务留 running（不写 done）
- P3-3 检索输出 dataset=名称 + dataset_id 字段（§6.1 契约）
- P3-4 notice.vector_pending M0a 恒 False（口径断言）
- P3-5 英文超长句硬切按原文字符区间（无单词黏连）
- P3-7 pending_dims 解析行数不符 → raise 回滚、pending_dims_json 保留
- P3-8 embed 返回条数不足 → raise、无半写（含探针条数守卫）
- P3-12 上传 dims 重复值去重（document_dimensions 不撞主键）
- P3-15 top_k=100 → 服务端硬上限 20（真实断言：>20 个可命中块）
"""

from __future__ import annotations

import inspect
import time

import pytest
from fastapi.testclient import TestClient
from fake_providers import FakeEmbedder

from knowledge_lattice.adapters.embedder import (
    EmbeddingGate,
    EmbeddingResponseError,
    FingerprintProbe,
)
from knowledge_lattice.app import create_app
from knowledge_lattice.config import Settings
from knowledge_lattice.core.docs import ingest as ingest_mod
from knowledge_lattice.core.docs.chunking import CHUNK_MAX_TOKENS, chunk_blocks
from knowledge_lattice.core.docs.retrieve import TOP_K_HARD_LIMIT, search
from knowledge_lattice.domain.auth import issue_dev_jwt

HTML_BYTES = (
    "<html><body><h1>留抵退税指南</h1><p>符合条件的一般纳税人可按月申请退还增量留抵税额。</p></body></html>"
).encode("utf-8")


def _upload_doc(env, *, embedder, dims=None):
    svc = env["make_service"](embedder)
    doc_id, task_id = svc.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="留抵退税指南",
        dims=dims if dims is not None else {"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML_BYTES, mime_type="text/html", filename="g.html",
    )
    return svc, doc_id, task_id


# ============ P2-1：one-shot 上传 embed 失败 → active_error 落库 ============


def test_p2_1_one_shot_embed_failure_writes_active_error(ingest_env) -> None:
    backend = ingest_env["backend"]
    svc, doc_id, task_id = _upload_doc(
        ingest_env, embedder=FakeEmbedder(dim=2560, fail=True)
    )
    # 同一次 run_task 内：index_fts 成功（D20 已切换）→ embed 失败
    with pytest.raises(ConnectionError):
        svc.run_task(task_id)

    doc = backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_lexical"  # 停在中间态（不 500）
    assert doc["active_error"], "active_error 必须落库（P2-1：切换后快照导致丢写）"
    assert "unreachable" in doc["active_error"]
    assert backend.get_task(task_id)["status"] == "failed"


# ============ P2-2：100+450 相邻段不并入成 >512 非末块 ============


def test_p2_2_overflow_flush_no_oversized_mid_chunk() -> None:
    from knowledge_lattice.adapters.parser_docling import ParsedBlock
    from knowledge_lattice.adapters import tokenizer

    unit = "增值税甲"  # 2 token/重复（预算：50→100、225→450）
    blocks = [
        ParsedBlock(kind="text", content=unit * 50),   # 100 token
        ParsedBlock(kind="text", content=unit * 225),  # 450 token
    ]
    assert tokenizer.token_count(blocks[0].content) == 100
    assert tokenizer.token_count(blocks[1].content) == 450
    chunks = chunk_blocks(blocks, doc_title="溢出")
    assert len(chunks) == 2, "100+450 应溢出即 flush（不并入成 550）"
    assert all(c.token_count <= CHUNK_MAX_TOKENS for c in chunks)
    assert chunks[0].token_count < 256  # 欠 min 的碎块允许（硬上限优先）
    assert "甲" in chunks[1].content


# ============ P2-3：core 不碰方言序列化（write_embeddings 收浮点向量） ============


def test_p2_3_core_has_no_dialect_import() -> None:
    src = inspect.getsource(ingest_mod)
    assert "store.sqlite" not in src, "core/docs/ingest.py 不得 import SQLite 方言（P2-3）"
    protocol_src = inspect.getsource(
        __import__(
            "knowledge_lattice.store.backend", fromlist=["IngestBackend"]
        ).IngestBackend.write_embeddings
    )
    assert "Sequence[float]" in protocol_src, "协议 write_embeddings 应收浮点向量（P2-3）"


def test_p2_3_write_embeddings_accepts_floats(ingest_env) -> None:
    """write_embeddings 直收 (rid, list[float]) 并正确落 BLOB（方言序列化收口 store）。"""
    from helpers import insert_chunk, seed_document
    from knowledge_lattice.store.sqlite.vec import unpack_f32

    conn = ingest_env["conn"]
    seed_document(conn, doc_id="d_vec", dataset_id="ds:vat_lib", owner_user_id="u_full")
    insert_chunk(conn, doc_id="d_vec", seq=1, version=1, content="x")
    rid = conn.execute("SELECT rid FROM chunks WHERE doc_id='d_vec'").fetchone()[0]
    conn.execute("UPDATE chunks SET embed_model = 'm:8' WHERE rid = ?", (rid,))
    conn.commit()
    written = ingest_env["backend"].write_embeddings("m:8", [(rid, [0.5, -0.5, 1.0])])
    assert written == 1
    blob = conn.execute(
        "SELECT embedding FROM chunk_vectors WHERE rid = ?", (rid,)
    ).fetchone()[0]
    assert blob is not None
    assert unpack_f32(blob) == pytest.approx([0.5, -0.5, 1.0])


# ============ P2-4 + P2-5：prod 路由可达性 / dev JWT 拒绝 ============


@pytest.fixture()
def prod_client(tmp_path):
    settings = Settings(environment="prod", data_dir=tmp_path, probe_interval_s=0,
                         worker_mode="inline")
    app = create_app(settings, run_startup_probe=False)
    with TestClient(app) as client:
        yield client, settings


def test_p2_4_prod_metadata_reachable_not_404(prod_client) -> None:
    """prod 下 dimensions/datasets 路由注册（可达）：鉴权失败应 401 而非 404。"""
    client, settings = prod_client
    token = issue_dev_jwt(settings, user_id="u_full", org="org:tax")
    resp = client.get(
        "/api/orgs/org:tax/dimensions", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401, "prod 认证待 M2 SSO——但路由必须可达（P2-4，404=门控回归）"
    resp2 = client.get(
        "/api/orgs/org:tax/datasets", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp2.status_code == 401
    # 静态页壳 prod 仍可用
    assert client.get("/").status_code == 200


def test_p2_4_prod_dev_token_route_404(prod_client) -> None:
    client, _ = prod_client
    assert client.post("/api/dev/token", json={}).status_code == 404


def test_p2_5_prod_rejects_dev_jwt_signed_with_default_secret(prod_client) -> None:
    """prod 下以公开默认 dev 密钥签发的 JWT → 401（不进入 dev-JWT 验签分支）。"""
    client, settings = prod_client
    token = issue_dev_jwt(settings, user_id="u_full", org="org:tax")
    resp = client.post(
        "/api/search",
        json={"query": "增值税"},
        headers={"Authorization": f"Bearer {token}", "X-Org-Id": "org:tax"},
    )
    assert resp.status_code == 401
    assert "P2-5" in resp.json()["error"] or "production" in resp.json()["error"]
    # 静态 token 同样拒绝
    resp2 = client.post(
        "/api/search",
        json={"query": "增值税"},
        headers={"Authorization": "Bearer any-static", "X-Org-Id": "org:tax"},
    )
    assert resp2.status_code == 401


# ============ P2-6：探针经 asyncio.to_thread（源级断言 + ticker 实证） ============


def test_p2_6_probe_calls_go_through_to_thread() -> None:
    from knowledge_lattice import app as app_module

    src = inspect.getsource(app_module)
    assert src.count("asyncio.to_thread(probe.probe)") == 2, (
        "启动与周期探针各一处须 asyncio.to_thread（P2-6——同步 httpx 30s 不得上事件循环）"
    )


def test_p2_6_probe_in_thread_via_gate(tmp_path) -> None:
    """启动探针经 to_thread：慢探针（0.3s）不阻塞 lifespan 内并发定时器。

    P3-R2-2 修正：改时间断言——原 `len(ticks) == 6` 为恒真计数（await task 会等
    ticker 跑满，阻塞场景下计数同样为 6、不构成实证）；现断言相邻 tick 间隔
    （正常 ≈60ms；若探针同步上事件循环，会产生 ≥300ms 的间隙）。
    """
    import asyncio

    settings = Settings(environment="test", data_dir=tmp_path, probe_interval_s=0,
                         worker_mode="inline")
    slow = FakeEmbedder(dim=2560, delay_s=0.3)
    gate = EmbeddingGate()
    app = create_app(settings, embedder=slow, gate=gate, run_startup_probe=True)
    ticks: list[float] = []

    async def main():
        async def ticker():
            for _ in range(6):  # 60ms 周期——若探针阻塞循环则 tick 间隙拉大
                ticks.append(time.monotonic())
                await asyncio.sleep(0.06)

        task = asyncio.create_task(ticker())
        async with app.router.lifespan_context(app):
            pass
        await task

    asyncio.run(main())
    assert gate.status == "ok"  # 探针完成（建档放行）
    assert len(ticks) == 6
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    max_gap = max(gaps)
    assert max_gap < 0.2, (
        f"ticker 相邻 tick 最大间隙 {max_gap:.3f}s（正常 ≈0.06s；探针若同步阻塞"
        "事件循环会产生 ≥0.3s 间隙——时间断言实证 to_thread 下放）"
    )


# ============ P3-1：stop_after 中断 → 任务留 running ============


def test_p3_1_stop_after_leaves_task_running(ingest_env) -> None:
    backend = ingest_env["backend"]
    svc, doc_id, task_id = _upload_doc(ingest_env, embedder=FakeEmbedder(dim=2560))
    svc.run_task(task_id, stop_after="index_fts")
    assert backend.get_task(task_id)["status"] == "running", "中断缝不写 done（P3-1）"
    svc.run_task(task_id)
    assert backend.get_task(task_id)["status"] == "done"


# ============ P3-3 + P3-4：检索输出契约 ============


def test_p3_3_dataset_name_and_id_contract(ingest_env) -> None:
    embedder = FakeEmbedder(dim=2560)
    svc, doc_id, task_id = _upload_doc(ingest_env, embedder=embedder)
    svc.run_task(task_id)
    resp = search(
        ingest_env["backend"], ingest_env["settings"],
        user_id="u_full", org_id="org:tax", query="留抵退税",
        embedder=embedder,  # M1 完整配方：provider 注入后向量路开启
    )
    assert resp["results"]
    top = resp["results"][0]
    assert top["dataset"] == "库 ds:vat_lib", "dataset＝知识库名称（MCP 契约 §6.1）"
    assert top["dataset_id"] == "ds:vat_lib"
    # P3-4：M1 起块级语义——vector_pending=结果块是否缺当前标签向量（TC-RET-02）；
    # 本用例块已全量嵌入（run_task 完成 embed 阶段）→ False
    assert resp["notice"]["vector_pending"] is False


# ============ P3-5：英文超长句硬切保原文（无单词黏连） ============


def test_p3_5_english_hard_split_preserves_words() -> None:
    from knowledge_lattice.adapters.parser_docling import ParsedBlock
    from knowledge_lattice.adapters import tokenizer

    original = "VAT invoice reconciliation " * 200  # 单句 ~600 token（无句读）
    chunks = chunk_blocks(
        [ParsedBlock(kind="text", content=original)], doc_title="英文硬切"
    )
    assert len(chunks) >= 2
    for c in chunks:
        assert c.token_count <= CHUNK_MAX_TOKENS
        assert "VATinvoice" not in c.content and "invoicereconciliation" not in c.content
    joined = " ".join(c.content for c in chunks)
    assert "VAT invoice reconciliation" in joined  # 词间空格保留
    total = sum(c.token_count for c in chunks)
    assert total == tokenizer.token_count(original)  # token 无损（不丢不黏）


# ============ P3-7：pending_dims 解析行数不符 → 回滚保留 ============


def test_p3_7_pending_dims_mismatch_rolls_back(ingest_env) -> None:
    backend = ingest_env["backend"]
    backend.create_document(
        doc_id="doc_p37", org_id="org:tax", dataset_id="ds:vat_lib", title="坏维度",
        source_uri="user:u_full", content_hash="sha256:x", mime_type="text/html",
        parser="docling", owner_user_id="u_full", raw_object_key="x.html",
        pending_dims_json='{"region": ["XX_NOT_EXIST"]}',
    )
    chunks = [{"id": "chk_p37_1", "seq": 1, "content": "内容", "content_seg": "内容"}]
    with pytest.raises(RuntimeError, match="pending_dims resolution mismatch"):
        backend.insert("doc_p37", 1, chunks)
    # 回滚：块未写、pending_dims_json 保留供重试、状态未推进
    conn = ingest_env["conn"]
    assert conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id='doc_p37'").fetchone()[0] == 0
    doc = backend.get_document("doc_p37")
    assert doc["pending_dims_json"] == '{"region": ["XX_NOT_EXIST"]}'
    assert doc["active_version"] == 0


# ============ P3-8：embed 返回条数不足 → raise 无半写 ============


def test_p3_8_embedding_count_mismatch_raises(ingest_env) -> None:
    class ShortEmbedder(FakeEmbedder):
        def embed(self, texts):
            out = super().embed(texts)
            return out[:-1]  # 少返回一条（模拟网关截断响应）

    backend = ingest_env["backend"]
    svc, doc_id, task_id = _upload_doc(ingest_env, embedder=ShortEmbedder(dim=2560))
    with pytest.raises(EmbeddingResponseError):
        svc.run_task(task_id)
    assert backend.get_task(task_id)["status"] == "failed"
    doc = backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_lexical"  # 不置 full
    assert doc["active_error"]
    n = ingest_env["conn"].execute(
        "SELECT COUNT(*) FROM chunk_vectors cv JOIN chunks c ON c.rid = cv.rid"
        " WHERE c.doc_id = ?",
        (doc_id,),
    ).fetchone()[0]
    assert n == 0, "条数不符整批拒绝写入（防 zip 静默丢块后仍置 full）"


def test_p3_8_probe_count_guard(ingest_env) -> None:
    class ShortProbeEmbedder(FakeEmbedder):
        def embed(self, texts):
            out = super().embed(texts)
            return out[:-1]

    probe = FingerprintProbe(
        ingest_env["backend"], ShortProbeEmbedder(dim=2560), ingest_env["settings"]
    )
    with pytest.raises(EmbeddingResponseError):
        probe.probe()


# ============ P3-12：上传 dims 重复值去重 ============


def test_p3_12_duplicate_dim_values_deduped(ingest_env) -> None:
    svc, doc_id, task_id = _upload_doc(
        ingest_env, embedder=FakeEmbedder(dim=2560), dims={"region": ["CN", "CN", "CN"]}
    )
    svc.run_task(task_id)
    conn = ingest_env["conn"]
    rows = conn.execute(
        "SELECT COUNT(*) FROM document_dimensions WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0]
    assert rows == 1, "重复维度值去重——document_dimensions 主键不冲突、任务不失败"
    assert ingest_env["backend"].get_document(doc_id)["active_status"] == "searchable_full"


# ============ P3-15：top_k 硬上限真实断言（>20 个可命中块） ============


def test_p3_15_top_k_hard_limit_with_enough_hits(ingest_env) -> None:
    from helpers import insert_chunk, seed_document

    conn = ingest_env["conn"]
    seed_document(conn, doc_id="d_cap", dataset_id="ds:vat_lib", owner_user_id="u_full")
    for seq in range(1, 26):  # 25 个可命中块（增值税=单 token——查询/索引同分词口径）
        insert_chunk(
            conn, doc_id="d_cap", seq=seq, version=1,
            content="硬上限测度块", content_seg="增值税 硬上限", title_seg="增值税",
        )
    conn.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_cap'")
    conn.commit()

    resp = search(
        ingest_env["backend"], ingest_env["settings"],
        user_id="u_full", org_id="org:tax", query="增值税", top_k=100,
    )
    assert len(resp["results"]) == TOP_K_HARD_LIMIT == 20, (
        "25 块可命中 + top_k=100 → 恰好截断为服务端硬上限 20（P3-15）"
    )
