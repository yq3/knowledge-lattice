"""向量 BLOB 序列化（design §3 store/sqlite/vec.py——P0-1 BLOB 距离配套）。

sqlite-vec `vec_f32` 的 BLOB 形态 = 逐 float32 小端序（无头）。距离函数
（vec_distance_cosine）作用于该 BLOB 列——M0a-3 落序列化助手，距离查询随 M1 向量路。
"""

from __future__ import annotations

import struct
from collections.abc import Sequence


def pack_f32(vector: Sequence[float]) -> bytes:
    """list[float] → vec_f32 BLOB（小端 float32 连续存储）。"""
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack_f32(blob: bytes) -> list[float]:
    """vec_f32 BLOB → list[float]。"""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))
