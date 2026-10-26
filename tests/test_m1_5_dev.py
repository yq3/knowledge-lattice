"""M1-5 承接开发项（TDD——先红后绿）：

- C3 fuse 段双计修正（m1-4 P3-9 顺延）：fuse 耗时不含增强 800ms 等待
  （并行窗口等待单列 enh_wait——NFR-8 分解前必须修）；
- A1 100k 档批量重算改造前置（M1-4 P2-4，TC-PERF-03 前置）：
  ① org_active_chunk_vectors 返回**packed bytes 流**（float32 小端——不再
  物化 Python float 对象列表；100k×2560 物化 >1GB 的根因消除）；
  ② delete_open_flags 分批（PG 65535 参数上限 / sqlite 32766 上限——
  ~6.5 万候选不再失败）；
- C1 MCP list_documents 工具实装（design §6.1 docs 组；T17/TC-AZ-02 执行
  主体；与 TC-AZ-03 管理列表两个端点两个口径）；
- C2 P3-11（m1-1 顺延）：PG to_tsquery 畸形参数降级（400/空召回而非 500）
  双后端对照。
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest
from fastmcp.exceptions import ToolError
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from helpers import (
    dim_id_for,
    seed_doc_dims,
    seed_document,
    seed_searchable_doc,
    val_id_for,
)

ORG = "org:tax"
LABEL = "fake-embed:8"


# ============ C3：fuse 段不含增强等待（双计修正） ============


def _parse_timing(line: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in re.findall(r"(\w+)=([0-9.]+)ms", line):
        out[key] = float(value)
    return out


def test_fuse_excludes_enhance_wait(ret_stack, caplog) -> None:
    """增强 700ms 等待不得计入 fuse 段：fuse 应为纯 RRF+断言+归一（<300ms），
    等待单列 enh_wait（≥600ms）——四段口径不变、新增观测字段。"""
    import dataclasses
    import logging

    from fake_providers import FakeEnhancer

    from knowledge_lattice.core.docs.retrieve import search

    backend = ret_stack["backend"]
    settings = dataclasses.replace(ret_stack["settings"], enhancer="fake")
    enhancer = FakeEnhancer(terms=["common"], delay_s=0.7)

    def _run() -> str:
        with caplog.at_level(logging.INFO):
            search(
                backend, settings,
                user_id="u_full", org_id=ORG, query="common sample", top_k=5,
                gate=None, embedder=ret_stack["embedder"], enhancer=enhancer,
            )
        lines = [r.message for r in caplog.records if "search timing" in r.message]
        assert lines, "应输出 search timing 日志"
        caplog.clear()
        return lines[-1]

    _run()  # 预热（jieba 首切分 ~1s 不计入断言窗口）
    timing = _parse_timing(_run())
    for seg in ("embed", "recall", "fuse", "rerank", "enh_wait"):
        assert seg in timing, f"耗时字段缺失 {seg}: {timing}"
    assert timing["fuse"] < 300.0, (
        f"fuse 段不得包含增强等待（双计修正——m1-4 P3-9）: {timing}"
    )
    assert timing["enh_wait"] >= 600.0, f"700ms 增强等待应单列 enh_wait: {timing}"


def test_timing_four_segments_unchanged_without_enhancer(ret_stack, caplog) -> None:
    """无增强路：四段日志保持 M1-4 口径（enh_wait=0 仍出场——观测字段常驻）。"""
    import logging

    from knowledge_lattice.core.docs.retrieve import search

    with caplog.at_level(logging.INFO):
        search(
            ret_stack["backend"], ret_stack["settings"],
            user_id="u_full", org_id=ORG, query="common sample", top_k=5,
            gate=None, embedder=ret_stack["embedder"],
        )
    line = [r.message for r in caplog.records if "search timing" in r.message][0]
    timing = _parse_timing(line)
    for seg in ("embed", "recall", "fuse", "rerank", "enh_wait"):
        assert seg in timing
    assert timing["enh_wait"] == 0.0
    assert "fts=" not in line


# ============ A1：批量重算改造（packed bytes 流 + delete_open_flags 分批） ============


def test_org_active_chunk_vectors_packed_bytes_stream(matrix, tmp_path) -> None:
    """向量数据源 = (rid, packed float32 bytes) 惰性流（M1-4 P2-4 改造）：
    bytes 长度 = dim×4、值与写入一致；生成器形态（不物化全量行）。"""
    import struct

    seed_searchable_doc(matrix, "d_vec")
    rid = matrix.execute("SELECT rid FROM chunks WHERE id = ?", ("chk:d_vec:v1:1",)).fetchone()[0]
    vector = [0.5, -0.25, 0.75, 1.0, 0.125, -0.625, 0.375, 0.875]
    matrix.insert_vector(rid, LABEL, vector)

    backend = matrix.make_backend()
    rows = backend.org_active_chunk_vectors(ORG, LABEL)
    assert not isinstance(rows, list), "应返回流式迭代器（100k 档不物化全量行）"
    rows = list(rows)
    assert len(rows) == 1 and rows[0][0] == rid
    packed = rows[0][1]
    assert isinstance(packed, (bytes, bytearray))
    assert len(packed) == len(vector) * 4, "float32 小端 packed bytes（dim×4 字节）"
    assert list(struct.unpack(f"<{len(vector)}f", bytes(packed))) == pytest.approx(
        vector, abs=1e-6
    )


def test_delete_open_flags_batches_beyond_param_limits(matrix) -> None:
    """超参数上限的候选集（~6.5 万——PG 65535/sqlite 32766 上限）分批删除：
    不抛异常、删除计数只含真实存在的 open flags（M1-4 P2-4 改造）。"""
    from helpers import insert_chunk

    seed_document(matrix, doc_id="d_flags", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(matrix, "d_flags", {"region": ["CN"]})
    backend = matrix.make_backend()
    real_rids = []
    for i in range(3):
        insert_chunk(matrix, doc_id="d_flags", seq=i + 1, content=f"块 {i}")
        rid = matrix.execute(
            "SELECT rid FROM chunks WHERE id = ?", (f"chk:d_flags:v1:{i + 1}",)
        ).fetchone()[0]
        backend.insert_quality_flag(
            chunk_id=f"chk:d_flags:v1:{i + 1}", doc_id="d_flags",
            reason="vector_crowding", detail_json="{}",
        )
        real_rids.append(rid)
    matrix.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_flags'")
    matrix.commit()

    # 70,000 rid（3 真实 + 69,997 不存在）——单语句形态在 PG（>65535 参数）与
    # sqlite（>32766 参数）均超限；分批后应正常返回 3
    rids = real_rids + [10_000_000 + i for i in range(69_997)]
    deleted = backend.delete_open_flags(rids, ["vector_crowding", "low_idf", "both"])
    assert deleted == 3
    assert backend.list_quality_flags("d_flags") == []


# ============ C1：MCP list_documents 工具（§6.1 docs 组 / TC-AZ-02） ============


def _mcp_client(app, token: str) -> Client:
    import httpx

    def factory(**kw):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)

    return Client(
        StreamableHttpTransport(
            url="http://testserver/mcp",
            headers={"Authorization": f"Bearer {token}"},
            httpx_client_factory=factory,
        )
    )


def _call_list_documents(app, token: str, **params) -> dict:
    async def flow():
        async with _mcp_client(app, token) as client:
            result = await client.call_tool("list_documents", params)
            return json.loads(result.content[0].text)

    return asyncio.run(flow())


def test_mcp_list_documents_contract(app_env) -> None:
    """§6.1 契约：datasets 统计（id/name/doc_count）+ documents 全字段
    （四态 + dims + chunk_count + source + updated_at）。"""
    env = app_env
    conn = env["conn"]
    seed_searchable_doc(conn, "d_cn", owner_user_id="u_full", dims={"region": ["CN"]}, content_seg="增值税 指南")
    seed_searchable_doc(
        conn, "d_plain", owner_user_id="u_full", dims={"region": ["CN"]},
        content_seg="消费税 指南", version=1,
    )
    conn.execute(
        "UPDATE documents SET active_status = 'searchable_full',"
        " source_uri = 'user:u_full',"
        " updated_at = '2026-10-26 12:00:00' WHERE id IN ('d_cn', 'd_plain')"
    )
    conn.commit()
    token = env["jwt"]("u_full", org=ORG)

    payload = _call_list_documents(env["app"], token)

    assert set(payload) >= {"datasets", "documents"}
    assert payload["datasets"] == [
        {"id": "ds:vat_lib", "name": "库 ds:vat_lib", "doc_count": 2}
    ]
    docs = {d["doc_id"]: d for d in payload["documents"]}
    assert set(docs) == {"d_cn", "d_plain"}
    doc = docs["d_cn"]
    assert doc["dataset"] == "ds:vat_lib"
    assert doc["active_version"] == 1
    assert doc["active_status"] == "searchable_full"
    assert doc["pending_version"] is None
    assert doc["pending_status"] is None
    assert doc["dims"] == {"region": ["CN"]}
    assert doc["chunk_count"] == 1
    assert doc["source"] == 'user:u_full'
    assert doc["updated_at"]
    assert doc["title"]


def test_mcp_list_documents_stats_per_caller_acl(app_env) -> None:
    """TC-AZ-02：一切统计按调用者权限计算——u_cn（region=[CN]）不可见 d_os
    （region=[OS]）的存在与数量（doc_count 不泄露）。"""
    env = app_env
    conn = env["conn"]
    seed_searchable_doc(conn, "d_cn", owner_user_id="u_full", dims={"region": ["CN"]})
    seed_searchable_doc(conn, "d_os", owner_user_id="u_full", dims={"region": ["OS"]})
    seed_searchable_doc(conn, "d_open", owner_user_id="u_full")  # 无 region 行——空值放行（D19）
    conn.commit()

    full = _call_list_documents(env["app"], env["jwt"]("u_full", org=ORG))
    cn = _call_list_documents(env["app"], env["jwt"]("u_cn", org=ORG))

    assert full["datasets"][0]["doc_count"] == 3
    assert cn["datasets"][0]["doc_count"] == 2, "d_os 不可见——数量不泄露"
    assert {d["doc_id"] for d in cn["documents"]} == {"d_cn", "d_open"}
    dumped = json.dumps(cn, ensure_ascii=False)
    assert "d_os" not in dumped, "不可见文档 id 不得出现在任何统计/明细面"


def test_mcp_list_documents_filters_and_limit(app_env) -> None:
    """input 契约：datasets 收窄 / active_status 过滤 / limit 截断（缺省 50）。"""
    env = app_env
    conn = env["conn"]
    seed_searchable_doc(conn, "d_cn", owner_user_id="u_full", dims={"region": ["CN"]})
    seed_searchable_doc(conn, "d_open", owner_user_id="u_full")
    # d_pending：pending 版本在途（active v1 + pending v2 parsing）
    seed_searchable_doc(conn, "d_pen", owner_user_id="u_full", dims={"region": ["CN"]}, version=1)
    conn.execute(
        "UPDATE documents SET pending_version = 2, pending_status = 'parsing'"
        " WHERE id = 'd_pen'"
    )
    conn.commit()
    token = env["jwt"]("u_full", org=ORG)

    limited = _call_list_documents(env["app"], token, limit=2)
    assert len(limited["documents"]) == 2

    conn.execute(
        "UPDATE documents SET active_status = 'searchable_full'"
        " WHERE id IN ('d_cn', 'd_open', 'd_pen')"
    )
    conn.commit()
    pending = _call_list_documents(env["app"], token, active_status="searchable_full")
    by_id = {d["doc_id"]: d for d in pending["documents"]}
    assert "d_pen" in by_id  # active v1 searchable_full 仍列出（pending 字段另示）
    assert by_id["d_pen"]["pending_version"] == 2
    assert by_id["d_pen"]["pending_status"] == "parsing"

    narrow = _call_list_documents(env["app"], token, datasets=["ds:none"])
    assert narrow["documents"] == [] and narrow["datasets"] == []

    # 未知状态值 → 400 ToolError（显式降级——不 500、不静默空列表误导 LLM）
    with pytest.raises(ToolError) as exc_info:
        _call_list_documents(env["app"], token, active_status="not_a_status")
    assert "400" in str(exc_info.value)


def test_backend_list_documents_for_acl_dual_backend(matrix) -> None:
    """backend 层双后端：visible_documents / visible_dataset_counts 按 plan 过滤
    （DB/服务/MCP 层双后端实跑——B-1① 口径）。"""
    backend = matrix.make_backend()
    from knowledge_lattice.core.docs.acl import compile_acl

    plan_cn = compile_acl(backend, "u_cn", ORG)
    plan_full = compile_acl(backend, "u_full", ORG)

    counts_full = backend.visible_dataset_counts(plan_full)
    counts_cn = backend.visible_dataset_counts(plan_cn)
    # u_full（region=[CN,OS]+tax_type=[VAT]）：d_cit（tax_type=CIT）不可见 → 4
    assert counts_full == [{"id": "ds:vat_lib", "name": "库 ds:vat_lib", "doc_count": 4}]
    # u_cn（region=[CN]+tax_type 零授权）：只见 region 命中且 tax 无行的文档 → 2
    assert counts_cn[0]["doc_count"] == 2, (
        "d_os（region=OS）/ d_cn·d_cit（tax_type 有行零授权）对 u_cn 不可见（T22）"
    )

    docs_cn = backend.visible_documents(plan_cn, limit=50)
    assert {d["doc_id"] for d in docs_cn} == {"d_multi", "d_empty_region"}
    d_multi = next(d for d in docs_cn if d["doc_id"] == "d_multi")
    assert d_multi["chunk_count"] == 1
    assert d_multi["dims"] == {"region": ["CN", "OS"]}

    narrow = backend.visible_documents(plan_full, dataset_ids=["ds:other"])
    assert narrow == []


# ============ C2 / P3-11（m1-1 顺延）：PG to_tsquery 畸形参数降级 ============


@pytest.mark.parametrize(
    "bad_query",
    [
        '"', "'", ":", "*", "(", ")", "&", "/", "\\", '"&:/*()',
        'a"b:c*d(e)&f/g', '""""', "&&&&", "::", "**", "((()))",
        '"未闭合引号', "term & (other | third) ! neg",
    ],
)
def test_search_malformed_query_degrades_not_500(app_env, bad_query) -> None:
    """REST 面：畸形 query（引号/:/*/括号/&）→ 200 空召回或 400，绝不 500。"""
    env = app_env
    resp = env["client"].post(
        "/api/search",
        json={"query": bad_query, "top_k": 5},
        headers={"Authorization": f"Bearer {env['jwt']('u_full', org=ORG)}"},
    )
    assert resp.status_code in (200, 400), (
        f"畸形 query 不得 500（got {resp.status_code}）: {bad_query!r}"
    )
    if resp.status_code == 200:
        assert resp.json()["results"] == [], "畸形 query 预期空召回"


@pytest.mark.parametrize(
    "bad_token",
    ['"', "'", ":", "*", "(", ")", "&", "/", "a:b", "a*b", "(a)", "a&b", '"&:/*()'],
)
def test_recall_fts_malformed_tokens_no_raise(matrix, bad_token) -> None:
    """backend 层双后端对照：畸形 token 直送 recall_fts 不抛异常（空/滤除/字面量化
    皆可——判据是不 500、返回 list）。"""
    from knowledge_lattice.core.docs.acl import compile_acl

    backend = matrix.make_backend()
    plan = compile_acl(backend, "u_full", ORG)
    rows = backend.recall_fts([bad_token, '"', ":"], plan, top_k=5)
    assert isinstance(rows, list)
