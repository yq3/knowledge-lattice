"""m2-5 A5（P3-7——m1-5 Committer 接受为 M2 hardening）：quality 两遍流
（区分度重算 _crowding_means）边界处理强化。

两遍流 = 「取候选行 + 数池规模」一遍 + 「池分块流过」二遍（两次独立流式
查询）。边界两面（m1-5 R3 移交）：

1. **non-finite 向量防御**——NaN/inf 行（手工行/异常数据）会让 numpy sims
   传染：NaN 池块行把**所有**候选与它的相似度变 NaN → partition 位置未定
   → 有效近邻被挤掉或 NaN 进 topk → mean=NaN → 拥挤块整体漏标（静默）。
   修：候选行与池块行 non-finite 一律剔除（语义=无法判定不误报不漏标）；
2. **两遍流池缩水窗口**——第一遍 pool_n 定 k=min(neighbors, pool_n-1)、
   第二遍实际行数 M < pool_n（并发删除/清理窗口）→ 填充列 -2.0 残留进
   mean → 均值被稀释 → 拥挤块漏标。修：均值只对有效近邻列（> -1.5——
   排除填充 -2.0 与自身排除 -1.0）计算。
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from helpers import insert_chunk, seed_doc_dims, seed_document

ORG = "org:tax"
LABEL = "fake-embed:8"


def _rid(db, chunk_id: str) -> int:
    return db.execute("SELECT rid FROM chunks WHERE id = ?", (chunk_id,)).fetchone()[0]


def _vec(i: int) -> list[float]:
    v = [0.0] * 8
    v[0] = 1.0
    v[1 if i % 2 else 2] = 0.05
    return v


def _seed_crowded(db, *, n: int, doc_id: str) -> list[str]:
    """n 块全拥挤簇（成员间余弦 ≈ 0.997~1.0）。"""
    seed_document(db, doc_id=doc_id, dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, doc_id, {"region": ["CN"]})
    ids = []
    for i in range(n):
        cid = insert_chunk(
            db, doc_id=doc_id, seq=i + 1, content=f"{doc_id} 块 {i}",
            content_seg=f"{doc_id} seg {i}", detected_at_scale=None,
            content_sha=None,
        )
        db.insert_vector(_rid(db, cid), LABEL, _vec(i))
        ids.append(cid)
    db.execute("UPDATE documents SET active_version = 1 WHERE id = ?", (doc_id,))
    db.commit()
    return ids


def _quality(env, **overrides):
    from knowledge_lattice.core.docs.quality import QualityService

    merged = {"quality_low_idf_threshold": 0.0, **overrides}
    return QualityService(
        env["backend"], dataclasses.replace(env["settings"], **merged)
    )


@pytest.fixture()
def crowd_env(qual_env):
    """10 块拥挤簇 + 全量重算档（sample_percent=100 + rescale_ratio=1.5——
    detected_at_scale=None 恒命中）。"""
    _seed_crowded(qual_env["db"], n=10, doc_id="d_crowd")
    return qual_env


# ============ non-finite 防御（单元面——numpy 边界，双后端同语义） ============


def _packed(vec: list[float]) -> bytes:
    import struct

    return struct.pack("<8f", *vec)


class _VecStreamBackend:
    """org_active_chunk_vectors 最小替身：固定行流（packed bytes——
    与真 backend 同契约；DB 层 sqlite 将 NaN 存 NULL 天然排除，pg REAL/向量
    列 NaN 可真实存在——non-finite 防御钉在 numpy 边界，双后端同语义）。"""

    def __init__(self, rows: list[tuple[int, list[float]]]) -> None:
        self._rows = rows

    def org_active_chunk_vectors(self, org_id, label):
        return iter((rid, _packed(v)) for rid, v in self._rows)


def _means(rows, cand_rids):
    import numpy as np

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.quality import QualityService

    service = QualityService(
        _VecStreamBackend(rows), Settings(environment="test"))
    return service._crowding_means(np, ORG, LABEL, cand_rids)


def test_crowding_nan_pool_row_excluded() -> None:
    """NaN 池行剔除：其余候选均值不受传染（修复前 NaN 进 sims → mean=NaN
    → 全体候选静默漏标）。"""
    rows = [(rid, _vec(rid)) for rid in range(1, 10)]
    rows.append((99, [math.nan] * 8))          # 异常行入池
    means = _means(rows, list(range(1, 10)))
    assert means, "NaN 池行不得让全体候选无均值（静默漏标）"
    assert all(m > 0.9 for m in means.values()), \
        f"有效候选均值不被 NaN 传染（got {means}）"
    assert 99 not in means


def test_crowding_nan_candidate_row_skipped() -> None:
    """NaN 候选行：跳过（不进均值面——无法判定不误报），其余照常。"""
    rows = [(rid, _vec(rid)) for rid in range(1, 10)]
    rows[0] = (1, [math.nan] * 8)              # 候选之一为 NaN
    means = _means(rows, list(range(1, 10)))
    assert 1 not in means, "NaN 候选行不标拥挤（均值无意义）"
    assert len(means) == 8 and all(m > 0.9 for m in means.values())


def test_recompute_pool_shrink_between_two_passes(crowd_env, monkeypatch) -> None:
    """两遍流池缩水窗口：第一遍 10 行定 k=8；第二遍流只剩 3 行（并发删除）。
    修复前：3 个真实近邻 + 5 个填充 -2.0 → mean≈-0.88 → 拥挤块漏标；
    修复后：均值按有效近邻列（≈1.0）→ 照常标拥挤。"""
    backend = crowd_env["backend"]
    real = backend.org_active_chunk_vectors
    state = {"calls": 0}

    def shrinking(org_id, label):
        rows = list(real(org_id, label))
        state["calls"] += 1
        if state["calls"] == 1:
            return iter(rows)          # 第一遍：全量（定 pool_n=10 → k=8）
        return iter(rows[:3])          # 第二遍起：缩水至 3 行

    monkeypatch.setattr(backend, "org_active_chunk_vectors", shrinking)

    out = _quality(crowd_env, quality_sample_percent=100,
                   quality_rescale_ratio=1.5).recompute(ORG)
    assert state["calls"] >= 2, "两遍流形态（候选遍 + 池块遍）"
    assert out["flagged"] >= 2, (
        f"池缩水窗口不得稀释均值致漏标（flagged={out['flagged']}——"
        "填充列 -2.0 混入 mean 的两遍流窗口）")
    # 修复后均值来自有效近邻列——detail.mean_sim ≈ 1.0（非 ≈-0.88 的稀释值）
    detail = crowd_env["db"].execute(
        "SELECT detail_json FROM quality_flags WHERE reason IN"
        " ('vector_crowding','both') LIMIT 1"
    ).fetchone()
    assert detail is not None
    mean_sim = __import__("json").loads(detail[0])["mean_sim"]
    assert mean_sim > 0.9, f"mean_sim 须为有效近邻均值（got {mean_sim}）"
