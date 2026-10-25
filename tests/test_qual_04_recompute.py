"""TC-QUAL-04 规模比例 + 抽样重算【单测｜M1——双后端参数化】。

- 仅「检测时规模 < 当前一定比例」的块与抽样命中块重算（其余不动——
  detected_at_scale/content_sha 不被触碰）；
- 批量走 numpy 矩阵乘（非 SQL 逐行——detail.recomputed 标记 + 万级块分钟级
  性能断言）；
- 重算覆盖语义：清旧 open 标记后按新检测结果重写（阈值变更后旧 flag 消失）。
"""

from __future__ import annotations

import dataclasses
import json
import time

from helpers import insert_chunk, seed_doc_dims, seed_document

ORG = "org:tax"
LABEL = "fake-embed:8"


def _rid(db, chunk_id: str) -> int:
    return db.execute("SELECT rid FROM chunks WHERE id = ?", (chunk_id,)).fetchone()[0]


def _vec(i: int) -> list[float]:
    """恒定微扰（成员间余弦 ≈ 0.997~1.0——全簇拥挤）。"""
    v = [0.0] * 8
    v[0] = 1.0
    v[1 if i % 2 else 2] = 0.05
    return v


def _seed_scale_doc(db, *, n: int, scale: int | None, sha: str | None, doc_id: str):
    seed_document(db, doc_id=doc_id, dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, doc_id, {"region": ["CN"]})
    ids = []
    for i in range(n):
        cid = insert_chunk(
            db, doc_id=doc_id, seq=i + 1, content=f"{doc_id} 块 {i}",
            content_seg=f"{doc_id} seg {i}",
            detected_at_scale=scale, content_sha=sha,
        )
        db.insert_vector(_rid(db, cid), LABEL, _vec(i))
        ids.append(cid)
    db.execute("UPDATE documents SET active_version = 1 WHERE id = ?", (doc_id,))
    db.commit()
    return ids


def _quality_with(env, **overrides):
    from knowledge_lattice.core.docs.quality import QualityService

    # 词面路默认关闭（小语料 IDF 偏低属 M1-5 标定问题——本文件隔离拥挤口径）
    merged = {"quality_low_idf_threshold": 0.0, **overrides}
    return QualityService(
        env["backend"], dataclasses.replace(env["settings"], **merged)
    )


def test_qual_09_recompute_scope_ratio_and_sampling(qual_env) -> None:
    """候选 = 规模比例 ∪ 抽样：stale 块重算、比例外近期块不触碰；抽样全覆盖档全体重算。"""
    env = qual_env
    db = env["db"]
    # 语义方向：「检测时规模 < 当前×比例」＝早期小语料时检测的块（漏报风险高）。
    # 当前规模 29（matrix 5 + stale 8 + fresh 8 + rest 8）；floor = 29×0.5 = 14
    stale = _seed_scale_doc(db, n=8, scale=8, sha=None, doc_id="d_stale")
    fresh = _seed_scale_doc(db, n=8, scale=29, sha="sha256:fresh-keep", doc_id="d_fresh")
    rest = _seed_scale_doc(db, n=8, scale=29, sha="sha256:rest-keep", doc_id="d_rest")
    current = env["backend"].org_active_chunk_count(ORG)
    assert current == 29

    # 关抽样（sample_percent=0）：候选 = stale 8 + matrix 未检测 5（NULL）——全确定性
    result = _quality_with(env, quality_sample_percent=0).recompute(ORG)
    assert result["candidates"] == 13
    assert result["current_scale"] == 29
    stale_scales = {
        db.execute("SELECT detected_at_scale FROM chunks WHERE id = ?", (c,)).fetchone()[0]
        for c in stale
    }
    assert stale_scales == {29}, "stale 块（检测时规模 8 < 14）应全部重算"
    stale_shas = {
        db.execute("SELECT content_sha FROM chunks WHERE id = ?", (c,)).fetchone()[0]
        for c in stale
    }
    assert all(s and s.startswith("sha256:") for s in stale_shas)
    untouched = db.execute(
        "SELECT count(*) FROM chunks WHERE content_sha IN"
        " ('sha256:fresh-keep', 'sha256:rest-keep')"
    ).fetchone()[0]
    assert untouched == 16, "比例外的近期块（抽样关闭）应保持完全未触碰"

    # 抽样全覆盖档（sample_percent=100）：全体候选——近期块也被重算
    _quality_with(env, quality_sample_percent=100).recompute(ORG)
    left = db.execute(
        "SELECT count(*) FROM chunks WHERE content_sha IN"
        " ('sha256:fresh-keep', 'sha256:rest-keep')"
    ).fetchone()[0]
    assert left == 0, "sample_percent=100 → 抽样全体命中，近期块也被重算"


def test_qual_10_recompute_overwrites_stale_flags(qual_env) -> None:
    """重算覆盖语义：阈值上调（更严）后旧拥挤 flag 清除；detail 带 recomputed 标记。"""
    env = qual_env
    db = env["db"]
    _seed_scale_doc(db, n=3, scale=None, sha=None, doc_id="d_flag")
    # 初次检测：互为近邻（余弦 ≈0.999）→ 拥挤 flags（隔离词面路）
    _quality_with(env).recompute(ORG)
    flags = env["backend"].list_quality_flags("d_flag")
    assert len(flags) == 3 and all(
        f["reason"] in ("vector_crowding", "both") for f in flags
    )

    # 更严阈值（0.99995 > 实际 mean_sim ≈0.9988）→ 重算清除（抽样全覆盖确保
    # d_flag 块进候选——重算只触碰候选，这是语义而非缺陷）
    result = _quality_with(
        env, quality_crowding_threshold=0.99995, quality_sample_percent=100
    ).recompute(ORG)
    assert env["backend"].list_quality_flags("d_flag") == [], "严阈值下旧 flag 应清除"
    assert result["cleared"] >= 3

    # 恢复阈值重算 → flags 重写 + detail 带 recomputed 标记（numpy 批量路径产物）
    _quality_with(env, quality_crowding_threshold=0.9, quality_sample_percent=100).recompute(ORG)
    flags = env["backend"].list_quality_flags("d_flag")
    assert len(flags) == 3
    detail = json.loads(flags[0]["detail_json"])
    assert detail.get("recomputed") is True, "批量重算路径应打 recomputed 标记"


def _bulk_seed(db, *, n: int, doc_id: str, batch: int = 500) -> None:
    """万级块批量直插（多行 VALUES——快路径；双后端 qmark 自动翻译）。"""
    seed_document(db, doc_id=doc_id, dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, doc_id, {"region": ["CN"]})
    cols = "(id, doc_id, seq, version, content, content_seg, detected_at_scale)"
    for start in range(0, n, batch):
        rows = []
        params: list[object] = []
        for i in range(start, min(start + batch, n)):
            rows.append("(?, ?, ?, 1, ?, ?, NULL)")
            params.extend([
                f"chk:bulk:{i}", doc_id, i + 1,
                f"{doc_id} bulk 块 {i}", f"{doc_id} bulk seg {i}",
            ])
        db.execute(f"INSERT INTO chunks{cols} VALUES " + ", ".join(rows), tuple(params))
    db.execute("UPDATE documents SET active_version = 1 WHERE id = ?", (doc_id,))
    db.commit()
    # 向量批量：同向微扰（真实距离计算路径，非跳过）
    rids = [
        r[0] for r in db.execute(
            "SELECT rid FROM chunks WHERE doc_id = ? ORDER BY rid", (doc_id,)
        ).fetchall()
    ]
    for start in range(0, len(rids), batch):
        chunk_rids = rids[start : start + batch]
        rows, params = [], []
        for j, rid in enumerate(chunk_rids):
            if db.is_sqlite:
                from knowledge_lattice.store.sqlite.vec import pack_f32

                rows.append("(?, ?, ?)")
                params.extend([rid, LABEL, pack_f32(_vec(j))])
            else:
                from knowledge_lattice.store.postgres.vec import format_vector

                rows.append("(?, ?, ?::vector)")
                params.extend([rid, LABEL, format_vector(_vec(j))])
        db.execute(
            "INSERT INTO chunk_vectors(rid, embed_model, embedding) VALUES "
            + ", ".join(rows),
            tuple(params),
        )
    db.commit()


def test_qual_11_recompute_10k_chunks_within_minutes(qual_env) -> None:
    """性能断言（TC-QUAL-04）：万级块 numpy 批量重算分钟级内完成（实测秒级）。"""
    env = qual_env
    db = env["db"]
    _bulk_seed(db, n=10_000, doc_id="d_bulk")
    assert env["backend"].org_active_chunk_count(ORG) == 10_005  # + matrix 5

    t0 = time.monotonic()
    result = env["quality"].recompute(ORG)
    elapsed = time.monotonic() - t0
    assert result["candidates"] == 10_005, "全部块 detected_at_scale IS NULL → 全体候选"
    assert elapsed < 120.0, f"万级块重算应在分钟级完成（got {elapsed:.1f}s）"
    # 拥挤判定真实发生（同向微扰簇 mean top-8 ≈ 0.999 > 0.92；matrix 5 块无
    # 向量不进拥挤路、词面路已隔离 → flagged 恰为 bulk 全体）
    assert result["flagged"] == 10_000
