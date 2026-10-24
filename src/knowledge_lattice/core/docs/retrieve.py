"""检索管线编排（design §3 core/docs/retrieve.py——M0a BM25 单路子集）。

M0a 范围（§5.2 的 BM25 路）：
- query 经 jieba 切分（adapters/tokenizer）→ store/sqlite/fts 方言转义（双引号包裹）；
- bm25 五列加权（3.0, 1.0, 5.0, 0.5, 8.0）+ 版本条件（JOIN 上）+ 完整 ACL WHERE
  （compile_acl → AclPlan → 渲染器下推——M0a-2 复用）；
- top_k 服务端硬上限 20；返回 chunk_id/doc_id/title/page_no/score/dims/source 溯源字段；
- notice.degraded 标注探针拒绝档（probe_reject——TC-EMB-03 M0a 断言范围）。

向量路/rerank/RRF/LLM 增强/实体路均为 M1/M2-S3（§5.2 全配方）——M0a 检索本就
BM25 单路（向量路开闭行为断言随 M1 TC-EMB-07）。分层纪律：编排不碰 SQL——
召回经 SearchBackend.recall_fts。
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from knowledge_lattice.adapters import tokenizer
from knowledge_lattice.adapters.embedder import EmbeddingGate
from knowledge_lattice.config import Settings
from knowledge_lattice.core.docs.acl import AclDeniedError, compile_acl

TOP_K_HARD_LIMIT = 20  # 服务端硬上限（§5.2 / TC-RET-07①）


def search(
    backend,
    settings: Settings,
    *,
    user_id: str,
    org_id: str,
    query: str,
    top_k: int = 8,
    datasets: Sequence[str] | None = None,
    doc_filter: Sequence[str] | None = None,
    gate: EmbeddingGate | None = None,
) -> dict:
    """BM25 单路检索（M0a）——AclDeniedError 由调用方转 403 语义。

    返回 MCP/REST 同构契约：{results: [...], notice: {vector_pending, degraded}}。
    """
    top_k = max(1, min(top_k, TOP_K_HARD_LIMIT))
    plan = compile_acl(
        backend,
        user_id,
        org_id,
        dataset_ids=datasets,
        doc_ids=doc_filter,
    )
    tokens = tokenizer.segment_query(query)
    rows = backend.recall_fts(tokens, plan, top_k=top_k) if tokens else []

    degraded: list[str] = []
    if gate is not None and gate.rejected:
        degraded.append("probe_reject")  # 探针拒绝档：跨底模距离无意义（拍板2）

    scores = [-(r["score_raw"] or 0.0) for r in rows]  # bm25 越小越相关 → 取负后越大越好
    lo, hi = (min(scores), max(scores)) if scores else (0.0, 0.0)

    results = []
    for rank, r in enumerate(rows, start=1):
        raw = -(r["score_raw"] or 0.0)
        score = 1.0 if hi == lo else round((raw - lo) / (hi - lo), 4)  # min-max 归一
        try:
            dims = json.loads(r.get("dims_json") or "{}")
        except (TypeError, ValueError):
            dims = {}
        content = r.get("content") or ""
        results.append(
            {
                "chunk_id": r["chunk_id"],
                "doc_id": r["doc_id"],
                # P3-3：`dataset`＝知识库**名称**（MCP 契约 §6.1 示例为名称）；
                # id 另出 `dataset_id` 字段
                "dataset": r.get("dataset_name"),
                "dataset_id": r.get("dataset_id"),
                "title": r.get("title"),
                "page_no": r.get("page_no"),
                "sheet_name": r.get("sheet_name"),
                "score": score,
                "rank": rank,
                "dims": dims,
                "source": r.get("source_uri"),
                "snippet": content[:120],
            }
        )
    return {
        "results": results,
        # P3-4：M0a 口径——无向量路（M1 落地），vector_pending 恒 False（＝本里程碑
        # 无「本结果缺向量路」语义；M1 起按块级 embedding 状态置位——TC-RET-02）
        "notice": {"vector_pending": False, "degraded": degraded},
    }


__all__ = ["search", "TOP_K_HARD_LIMIT", "AclDeniedError"]
