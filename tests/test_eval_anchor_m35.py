"""m3-5 C 组：TC-EVAL-05 在线引用锚点抽样（agent 会话引用存在性打标）。

管道（``src/knowledge_lattice/eval/anchor_sampling.py``）：
查询审计月库（m3-2 G-22 交付——读取走 store 层 ``read_monthly_events`` 协议
方法，core 零方言 SQL）→ agent 会话 search 事件引用 chunk_id → 存在性校验
（store 层 ``get_chunk``）→ 打标出数（引用不存在 ID = 幻觉证据——记录级）。

无真实 agent 会话（开发态）：以**构造会话**形态出数（沿 m2-5/m3-4 受阻先例
如实登记——script 层 demo 管道 + eval/reports/ 报告归档，见
scripts/eval_anchor_m35.py）；本模块门禁用例以构造事件验证管道确定性。
"""

from __future__ import annotations

import json

from knowledge_lattice.eval.anchor_sampling import (
    build_sampling_report,
    check_anchor_existence,
    collect_agent_citations,
    sample_anchors,
)

ORG = "org:tax"


def _event(eid: str, actor: str, *, action: str = "search.query",
           outcome: str = "accepted", chunk_ids: list[str] | None = None,
           query: str = "进项抵扣") -> dict:
    detail: dict = {"query": query, "top_k": 10}
    if chunk_ids is not None:
        detail["chunk_ids"] = chunk_ids
    return {
        "id": eid, "org_id": ORG, "actor": actor, "action": action,
        "outcome": outcome, "detail_json": json.dumps(detail, ensure_ascii=False),
    }


# ============ ① 引用抽取（事件过滤器——确定性） ============


def test_tc_eval_05_collect_citations_filters() -> None:
    """抽取过滤：仅 accepted 的 search 引用事件；agent: 前缀过滤（开发态
    REST actor 为裸 user id——prefix 可配）；无 chunk_ids 的 detail 跳过。"""
    events = [
        _event("e1", "agent:demo:user:u_full", chunk_ids=["c1", "c2"]),
        _event("e2", "agent:demo:user:u_full", outcome="refused",
               chunk_ids=["c3"]),                       # refused 不计引用
        _event("e3", "u_full", chunk_ids=["c4"]),        # 裸 user actor
        _event("e4", "agent:demo:user:u_full", action="search.annotate",
               chunk_ids=["c5"]),                        # 非 search.query
        _event("e5", "agent:demo:user:u_full"),          # detail 无 chunk_ids
        _event("e6", "agent:demo:user:u_full", action="search.annotate",
               outcome="accepted"),                      # annotate 事件带实体面
    ]
    all_cited = collect_agent_citations(events)
    assert [c["event_id"] for c in all_cited] == ["e1", "e3"]

    agent_only = collect_agent_citations(events, actor_prefix="agent:")
    assert [c["event_id"] for c in agent_only] == ["e1"]
    assert agent_only[0]["chunk_ids"] == ["c1", "c2"]
    assert agent_only[0]["query"] == "进项抵扣"
    assert agent_only[0]["org_id"] == ORG


# ============ ② 存在性校验 + 打标出数（双后端） ============


def test_tc_eval_05_existence_and_report(matrix) -> None:
    """存在性校验走 store 层（get_chunk）：库内 chunk 命中、伪造 ID 判缺失
    （幻觉证据）；报告记录级出数（会话数/引用数/去重数/缺失数/缺失比例）。"""
    backend = matrix.make_backend()
    rows = backend.fetch_window("d_cn", version=1, seq_lo=0, seq_hi=100)
    assert rows, "标准矩阵 d_cn 应有 chunk（fixture 前提）"
    real_ids = [r["chunk_id"] for r in rows]
    fabricated = ["chk_fabricated_halluc_1", "chk_fabricated_halluc_2"]

    existence = check_anchor_existence(backend, real_ids + fabricated)
    assert all(existence[i] for i in real_ids)
    assert not any(existence[i] for i in fabricated)

    events = [
        _event("s1", "agent:demo:user:u_full",
               chunk_ids=real_ids + [fabricated[0]]),
        _event("s2", "agent:demo:user:u_full", chunk_ids=[fabricated[1]]),
        _event("s3", "agent:demo:user:u_full", chunk_ids=real_ids[:1]),
    ]
    report = sample_anchors(backend, events, actor_prefix="agent:")
    assert report["sessions"] == 3
    assert report["citations_total"] == len(real_ids) + 3
    assert report["distinct_ids"] == len(real_ids) + 2
    assert report["existing"] == len(real_ids)
    assert report["missing"] == 2
    assert sorted(report["missing_ids"]) == sorted(fabricated)
    assert report["missing_ratio"] == round(2 / (len(real_ids) + 2), 4)
    # 记录级：per-session 缺失定位（幻觉证据可回溯到会话）
    assert report["per_session_missing"]["s1"] == [fabricated[0]]
    assert report["per_session_missing"]["s2"] == [fabricated[1]]
    assert "s3" not in report["per_session_missing"]


def test_tc_eval_05_report_pure_structure() -> None:
    """报告纯函数：空会话面（无 agent 事件）零除防御 + 比例 0.0。"""
    report = build_sampling_report([], {})
    assert report["sessions"] == 0
    assert report["missing_ratio"] == 0.0
    assert report["missing_ids"] == []


# ============ ③ 全链 e2e：构造 agent 会话 → 查询审计月库 → 抽样 ============


def test_tc_eval_05_pipeline_e2e_via_query_audit(matrix) -> None:
    """全链（双后端）：QueryAuditQueue 直写月库（m3-2 链路——哈希链同口径）→
    store 层 read_monthly_events 读回 → 管道打标——与真实部署数据源同一读路径。"""
    from knowledge_lattice.query_audit import QueryAuditQueue, build_query_event
    backend = matrix.make_backend()
    rows = backend.fetch_window("d_cn", version=1, seq_lo=0, seq_hi=100)
    real_ids = [r["chunk_id"] for r in rows]
    fabricated = "chk_agent_halluc_e2e"

    qa = QueryAuditQueue(backend, flush_interval_s=60.0)  # 不 start——无后台线程
    try:
        qa.enqueue(build_query_event(
            "search.query", org_id=ORG, actor="agent:demo:user:u_full",
            detail={"query": "进项抵扣 范围", "top_k": 5,
                    "chunk_ids": real_ids + [fabricated]},
        ))
        qa.enqueue(build_query_event(
            "search.query", org_id=ORG, actor="agent:other:user:u_full",
            detail={"query": "消费税 征收范围", "top_k": 5,
                    "chunk_ids": real_ids[:1]},
        ))
        qa.flush()
    finally:
        qa.stop()

    from knowledge_lattice.store.taskclock import utc_now_ts

    events = backend.read_monthly_events(when=utc_now_ts())
    search_events = [e for e in events if e["action"] == "search.query"]
    assert len(search_events) == 2, "构造会话应经审计月库可回溯"

    report = sample_anchors(backend, events, actor_prefix="agent:")
    assert report["sessions"] == 2
    assert report["missing_ids"] == [fabricated]
    assert report["existing"] >= 1
