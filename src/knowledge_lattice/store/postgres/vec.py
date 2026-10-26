"""PG 向量序列化（design §3 store/postgres/vec.py——pgvector 等价）。

SQLite 后端 vec_f32 BLOB 的 PG 等价 = `vector` 列文本形态 `'[a,b,c]'`（pgvector）；
写入侧 `%(vec)s::vector` 显式转型。距离经 `<=>`（余弦，G-6：精确扫描起步——
索引化与 2000 维上限随 M1 halfvec/迭代扫描实验）。

M1-5（TC-PERF-03 前置，M1-4 P2-4）：读取侧新增 `parse_vector_bytes`——文本
直转 **packed float32 bytes**（不物化 Python float 对象列表；100k×2560 档
float 对象 >1GB 的根因消除，numpy 侧 `np.frombuffer` 零拷贝消费）。
"""

from __future__ import annotations

import struct
from collections.abc import Sequence


def format_vector(vector: Sequence[float]) -> str:
    """list[float] → pgvector 文本形态 `'[0.1,0.2]'`。"""
    return "[" + ",".join(repr(float(v)) for v in vector) + "]"


def parse_vector(text: str) -> list[float]:
    """pgvector 文本形态 `'[0.1,0.2]'` → list[float]（读取侧；psycopg 未注册
    pgvector 适配器时 vector 列以文本返回）。"""
    body = text.strip()
    if body.startswith("["):
        body = body[1:]
    if body.endswith("]"):
        body = body[:-1]
    if not body:
        return []
    return [float(x) for x in body.split(",")]


def parse_vector_bytes(text: str) -> bytes:
    """pgvector 文本形态 → packed float32 小端 bytes（M1-5 流式重算数据源）。

    与 parse_vector 同值（float() 解析后 struct.pack float32——与写入侧
    pack_f32 舍入一致）；逐段 pack、不物化 float 对象列表（内存 O(1)/行）。
    """
    body = text.strip()
    if body.startswith("["):
        body = body[1:]
    if body.endswith("]"):
        body = body[:-1]
    if not body:
        return b""
    return struct.pack(f"<{body.count(',') + 1}f", *(float(x) for x in body.split(",")))
