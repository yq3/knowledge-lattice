"""检索层指标（FR-7：Recall@k / MRR 自算——集合运算、零 LLM）。

约定：结果以 chunk 标识列表（有序）给出、标注以命中 chunk 标识集合给出；
标识统一用 `(doc_id, seq)` 二元组（跨后端稳定——chunk_id 为 ULID 随摄取变化，
(doc_id, seq) 对同一语料与切分确定性不变）。
"""

from __future__ import annotations

from collections.abc import Sequence

ChunkKey = tuple[str, int]


def recall_at_k(results: Sequence[ChunkKey], labels: set[ChunkKey], *, k: int) -> float:
    """Recall@k = |top-k(results) ∩ labels| / |labels|（labels 空 → 0.0）。"""
    if not labels:
        return 0.0
    top = list(results)[:k]
    return len(set(top) & labels) / len(labels)


def reciprocal_rank(results: Sequence[ChunkKey], labels: set[ChunkKey]) -> float:
    """首个命中标注的倒数排名（无命中 → 0.0）。"""
    for rank, key in enumerate(results, start=1):
        if key in labels:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(
    runs: Sequence[tuple[Sequence[ChunkKey], set[ChunkKey]]]
) -> float:
    """MRR = mean(reciprocal_rank)（空集 → 0.0）。runs=[(结果序, 标注集)]。"""
    if not runs:
        return 0.0
    return sum(reciprocal_rank(r, l) for r, l in runs) / len(runs)
