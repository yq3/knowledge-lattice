"""Reranker provider 接口（D12 修订）+ none 实现。

网关已确认提供 Cohere 风格 `/rerank`（待决-5 关闭、G-7 闭环）——客户端随 M1 检索
配方实装（httpx 异步/线程池）；`none` 为**显式降级路径**（运维/降级选项——TC-EMB-05）：
跳过重排、保序返回 RRF 序。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


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
