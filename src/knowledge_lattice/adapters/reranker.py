"""Reranker provider 接口（D12 修订）+ Cohere 风格客户端 + none 实现。

网关已确认提供 Cohere 风格 `/rerank`（待决-5 关闭、G-7 闭环——M1-1 实装）：
POST {base}/rerank {model, query, documents, top_n} → {results: [{index,
relevance_score}]}（字段细节按实际响应核对——真实联调环境不可达时按 none 档
验收 TC-EMB-05，联调登记移交项）。`none` 为**显式降级路径**（运维/降级选项——
跳过重排、保序返回 RRF 序）。失败/超时由调用方（retrieve）降级——本实现不吞
异常；httpx timeout=NFR-8 rerank 1000ms 硬上限。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from knowledge_lattice.config import Settings


@dataclass(frozen=True)
class RankedDocument:
    """Cohere 风格重排结果项。index＝候选列表下标（0 起）。"""

    index: int
    relevance_score: float


@runtime_checkable
class Reranker(Protocol):
    def rerank(
        self, query: str, documents: Sequence[str], *, top_n: int | None = None
    ) -> list[RankedDocument]:
        """对候选（content 原文，≤32——NFR-8）重排，按相关性降序返回。"""
        ...


class NoopReranker:
    """none 实现：跳过重排，按输入顺序返回（RRF 序即最终序）。"""

    def rerank(
        self, query: str, documents: Sequence[str], *, top_n: int | None = None
    ) -> list[RankedDocument]:
        n = len(documents) if top_n is None else min(top_n, len(documents))
        return [RankedDocument(index=i, relevance_score=1.0) for i in range(n)]


class CohereCompatReranker:
    """Cohere 风格 /rerank 客户端（httpx 同步——调用方经线程池下放，D12/NFR-8）。

    契约（G-7 闭环）：请求 {model, query, documents, top_n}；响应
    {results: [{index, relevance_score}, ...]}。响应缺字段/非法 index 由调用方
    防御（TC-ACL-08 响应注入面）；网络失败/超时原样 raise → 调用方降级
    rerank_skipped。
    """

    def __init__(self, settings: Settings) -> None:
        import httpx

        self._settings = settings
        self._client = httpx.Client(
            base_url=settings.rerank_api_base,
            headers={"Authorization": f"Bearer {settings.rerank_api_key}"},
            timeout=settings.rerank_timeout_s,  # NFR-8：rerank 超时 1000ms 硬上限
        )

    def rerank(
        self, query: str, documents: Sequence[str], *, top_n: int | None = None
    ) -> list[RankedDocument]:
        body: dict[str, object] = {
            "model": self._settings.rerank_model,
            "query": query,
            "documents": list(documents),
        }
        if top_n is not None:
            body["top_n"] = top_n
        resp = self._client.post("/rerank", json=body)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [
            RankedDocument(
                index=int(item["index"]), relevance_score=float(item["relevance_score"])
            )
            for item in results
            if "index" in item and "relevance_score" in item
        ]
