"""TC-EVAL-05 在线引用锚点抽样（m3-5 C 组——agent 会话引用存在性打标）。

管道（记录级交付）：

1. **取引用**：查询审计月库（m3-2 G-22 交付）的 agent 会话 search 事件
   （action=``search.query``、outcome=accepted、actor 前缀 ``agent:`` 可配）
   → detail_json 的 ``chunk_ids`` 列表（design §4「查询词 + 返回 chunk_id
   列表」）；**读月库走 store 层 ``read_monthly_events`` 协议方法**（链遍历
   序、core 零方言 SQL）；
2. **存在性校验**：store 层 ``get_chunk``（引用不存在 ID = 幻觉证据——
   TC-EVAL-05 口径：伪造 ID / 已删除文档的悬空引用）；
3. **打标出数**：会话数 / 引用总数 / 去重 ID 数 / 存在数 / 缺失数 / 缺失
   比例 + per-session 缺失定位（幻觉证据可回溯到会话——记录级）。

开发态无真实 agent 会话：``scripts/eval_anchor_m35.py --demo`` 以**构造会话**
形态出数（沿 m2-5/m3-4 受阻先例如实登记，报告归档 eval/reports/）；
``--db``（sqlite 生产库）/pg DSN 形态对真实月库抽样（部署期用法）。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence

CITED_ACTION = "search.query"   # 引用来源 action（§4 字面——查询级审计面）
AGENT_ACTOR_PREFIX = "agent:"   # agent 会话 actor 形态（agent:<name>:user:<id>）


def collect_agent_citations(
    events: Sequence[dict],
    *,
    actor_prefix: str | None = None,
    actions: Sequence[str] = (CITED_ACTION,),
) -> list[dict]:
    """审计事件 → 引用记录（确定性过滤）。

    - action ∈ actions 且 outcome=accepted（refused 事件无引用面）；
    - actor_prefix 给定时按前缀过滤（``agent:``=agent 会话；None=全部 actor
      ——开发态 REST actor 为裸 user id，部署期按需放开）；
    - detail_json 无 chunk_ids（refused/实体面事件）跳过。
    """
    out: list[dict] = []
    for ev in events:
        if ev.get("action") not in actions or ev.get("outcome") != "accepted":
            continue
        if actor_prefix and not str(ev.get("actor") or "").startswith(actor_prefix):
            continue
        try:
            detail = json.loads(ev.get("detail_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        chunk_ids = detail.get("chunk_ids")
        if not isinstance(chunk_ids, list):
            continue
        out.append({
            "event_id": ev.get("id"),
            "org_id": ev.get("org_id"),
            "actor": ev.get("actor"),
            "query": detail.get("query"),
            "chunk_ids": [str(c) for c in chunk_ids],
        })
    return out


def check_anchor_existence(backend, chunk_ids: Iterable[str]) -> dict[str, bool]:
    """chunk_id → 是否在库（store 层 ``get_chunk``——存在性即锚点打标）。"""
    seen: dict[str, bool] = {}
    for cid in dict.fromkeys(chunk_ids):  # 去重（引用面重复率高）
        seen[cid] = backend.get_chunk(cid) is not None
    return seen


def build_sampling_report(
    citations: Sequence[dict], existence: dict[str, bool]
) -> dict:
    """打标出数（记录级）：会话/引用/去重/存在/缺失/缺失比例 + per-session
    缺失定位。空会话面零除防御（比例 0.0）。"""
    distinct = sorted(existence)
    missing_ids = sorted(cid for cid in distinct if not existence[cid])
    per_session_missing: dict[str, list[str]] = {}
    for cite in citations:
        miss = [c for c in cite["chunk_ids"] if c in existence and not existence[c]]
        if miss:
            per_session_missing[str(cite["event_id"])] = sorted(set(miss))
    n_distinct = len(distinct)
    return {
        "sessions": len(citations),
        "citations_total": sum(len(c["chunk_ids"]) for c in citations),
        "distinct_ids": n_distinct,
        "existing": n_distinct - len(missing_ids),
        "missing": len(missing_ids),
        "missing_ratio": round(len(missing_ids) / n_distinct, 4) if n_distinct else 0.0,
        "missing_ids": missing_ids,           # 幻觉证据（引用不存在的 ID）
        "per_session_missing": per_session_missing,
    }


def sample_anchors(
    backend, events: Sequence[dict], *, actor_prefix: str | None = None
) -> dict:
    """全链：审计事件 → 引用抽取 → 存在性校验 → 报告。

    events 来自 store 层 ``read_monthly_events``（月库链遍历读回——与真实
    部署数据源同一读路径；见 scripts/eval_anchor_m35.py）。
    """
    citations = collect_agent_citations(events, actor_prefix=actor_prefix)
    existence = check_anchor_existence(
        backend, (c for cite in citations for c in cite["chunk_ids"]))
    return build_sampling_report(citations, existence)
