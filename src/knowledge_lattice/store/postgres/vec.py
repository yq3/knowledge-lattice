"""PG 向量序列化（design §3 store/postgres/vec.py——pgvector 等价）。

SQLite 后端 vec_f32 BLOB 的 PG 等价 = `vector` 列文本形态 `'[a,b,c]'`（pgvector）；
写入侧 `%(vec)s::vector` 显式转型。距离经 `<=>`（余弦，G-6：精确扫描起步——
索引化与 2000 维上限随 M1 halfvec/迭代扫描实验）。
"""

from __future__ import annotations

from collections.abc import Sequence


def format_vector(vector: Sequence[float]) -> str:
    """list[float] → pgvector 文本形态 `'[0.1,0.2]'`。"""
    return "[" + ",".join(repr(float(v)) for v in vector) + "]"
