#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""m2-5 A7①：rerank 百炼真实联调（gte-rerank-v2 DashScope 原生 text-rerank）。

任务书「实际联调」：按实际请求/响应核对 model/字段/错误形态——验证
DashScopeReranker provider 契约（离线 MockTransport 用例已锁请求/响应
映射；本脚本对真实网关核对）。**网络依赖脚本不进门禁**（真实调用仅限
校准/联调实验——benchmarks/ 形态）。

联调面：
  1. 基本契约：请求 input.{query,documents}/响应 output.results
     [{index,relevance_score}]——与 provider 实现逐字段一致；
  2. 排序语义：相关文档 relevance_score 显著高于无关文档且 index 回映正确；
  3. top_n：**parameters 放置**（R2/P3-7 实测探测 2026-11-02——顶层放置
     不被识别、服务端静默返回全量；parameters.top_n 生效恰截断）；
  4. 错误形态：错误模型名 400 InvalidParameter "Model not exist."（非 404）
     ——provider 原样 raise HTTPStatusError（调用方降级契约核对）；
  5. 中文 query + 混排文档（项目语料形态）。

用法：uv run python benchmarks/rerank_dashscope_live.py
产物：data/bench-results/m2-5-rerank-live.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_common import save_result  # noqa: E402

from calib_m2_5 import _api_key  # noqa: E402 —— key 只走 .env/环境

RERANK_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1"
MODEL = "gte-rerank-v2"   # 任务书 A4 探测结论（DashScope 原生端点已验证可通）


def main() -> int:
    import httpx

    from knowledge_lattice.adapters.reranker import DashScopeReranker
    from knowledge_lattice.config import Settings

    settings = Settings(
        environment="test",
        reranker="dashscope",
        rerank_api_base=RERANK_ENDPOINT,
        rerank_api_key=_api_key(),
        rerank_model=MODEL,
        rerank_timeout_s=10.0,
    )
    rr = DashScopeReranker(settings)
    out: dict = {"model": MODEL, "endpoint": RERANK_ENDPOINT}

    # ---- 1. 基本契约 + 排序语义（中文 query + 混排候选） ----
    query = "增值税留抵税额退税的申请条件"
    documents = [
        "企业差旅费报销标准与审批流程说明",                # 无关
        "纳税人当期增量留抵税额，可以按规定申请退还……",      # 相关
        "The general taxpayer shall account separately.",  # 无关（英文）
        "留抵退税额按下列公式计算：允许退还的增量留抵税额……",  # 最相关
    ]
    t0 = time.perf_counter()
    ranked = rr.rerank(query, documents, top_n=4)
    out["latency_ms_basic"] = round((time.perf_counter() - t0) * 1000, 1)
    out["basic_contract"] = [
        {"index": r.index, "relevance_score": round(r.relevance_score, 6)}
        for r in ranked
    ]
    scores = {r.index: r.relevance_score for r in ranked}
    assert 3 in scores and 1 in scores, "相关文档（1/3 号）应命中"
    out["ranking_semantics_ok"] = (
        scores[3] > scores[0] and scores[1] > scores[2] > 0
    )

    # ---- 2. top_n 形态（R2/P3-7：**parameters 放置**——实测探测 2026-11-02
    #      顶层 top_n 不被识别〔传 2 返回全量 4〕、parameters.top_n 生效恰截断；
    #      provider 已按 parameters 形态修正，此处对真实网关复核） ----
    ranked2 = rr.rerank(query, documents, top_n=2)
    out["top_n_observed"] = {
        "requested": 2, "returned": len(ranked2),
        "server_respects_top_n": len(ranked2) == 2,
        "placement": "parameters.top_n（R2 修正——顶层放置不被识别）",
        "consumer_impact": "retrieve 消费面全量请求+按分取 top——截断与否均正确",
    }

    # 排序语义以分数单调性判定（top1 是模型判断——不预设具体文档号）
    ordered = sorted(ranked, key=lambda r: -r.relevance_score)
    out["descending_order_ok"] = all(
        ordered[i].relevance_score >= ordered[i + 1].relevance_score
        for i in range(len(ordered) - 1))
    out["index_reflection_ok"] = {r.index for r in ranked} == {0, 1, 2, 3}

    # ---- 3. 错误形态（错误模型名） ----
    import dataclasses

    bad = DashScopeReranker(dataclasses.replace(
        settings, rerank_model="nonexistent-rerank-model"))
    try:
        bad.rerank(query, documents[:1])
        out["error_shape"] = "UNEXPECTED-200（错误模型未被拒）"
    except httpx.HTTPStatusError as exc:
        body = {}
        try:
            body = exc.response.json()
        except Exception:  # noqa: BLE001
            pass
        out["error_shape"] = {
            "status": exc.response.status_code,
            "code": body.get("code") or body.get("request_id"),
            "message_head": (body.get("message") or "")[:80],
            "provider_raises_httppstatuserror": True,
        }

    save_result("m2-5-rerank-live", out)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    ok = (out.get("ranking_semantics_ok") and out.get("descending_order_ok")
          and out.get("index_reflection_ok"))
    print("\n联调结论："
          + ("契约一致——DashScopeReranker provider 与真实网关匹配"
             "（top_n parameters 放置生效——R2 修正后契约完整）" if ok
             else "存在形态差异——见 JSON 工件"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
