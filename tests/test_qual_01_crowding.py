"""TC-QUAL-01 向量拥挤度口径【单测｜M1——双后端参数化】。

- ① 与库内 8 个近邻高相似的 chunk → 判拥挤（top-8 mean(sim) > 绝对阈值）写
  quality_flags（reason=vector_crowding，detail 含近邻分布与 mean_sim）；
- ② 仅与 **tombstone 旧版本块**或**他组织块**高相似 → **不**判拥挤——近邻限定
  「组织内 + 仅在用版本」（#33 P1-10）；
- ③ 摄取管线 quality 阶段真实触达（run_task 完成即检测——§5.3 阶段编排）。

造数：向量直接写 chunk_vectors（db.insert_vector——测试直插路径，绕过写防护
属预期：本用例测检测口径不测写入）；内容块经 helpers.insert_chunk。
"""

from __future__ import annotations

import dataclasses
import json

from helpers import insert_chunk, seed_dataset, seed_doc_dims, seed_document

ORG = "org:tax"
ORG_GL = "org:gl"
LABEL = "fake-embed:8"

# 8 维基向 + 恒定微扰（成员间余弦 ≈ 0.997~1.0——拥挤簇造数；扰动不得随 i 放大，
# 否则大 i 向量偏离簇心导致余弦塌陷）
_BASE = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
_EPS = 0.05


def _near_base(i: int) -> list[float]:
    v = list(_BASE)
    v[1 if i % 2 else 2] = _EPS
    return v


# 与基向量近正交（余弦 ≈ 0）——非拥挤对照
_FAR = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def _rid_of(db, chunk_id: str) -> int:
    return db.execute("SELECT rid FROM chunks WHERE id = ?", (chunk_id,)).fetchone()[0]


def _seed_cluster(db, doc_id: str, *, n: int, start_seq: int = 1) -> list[str]:
    seed_document(db, doc_id=doc_id, dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, doc_id, {"region": ["CN"]})
    ids = []
    for i in range(n):
        cid = insert_chunk(
            db, doc_id=doc_id, seq=start_seq + i, content=f"{doc_id} 条款{i}",
            content_seg=f"{doc_id} seg {i}",
        )
        db.insert_vector(_rid_of(db, cid), LABEL, _near_base(i))
        ids.append(cid)
    db.execute("UPDATE documents SET active_version = 1 WHERE id = ?", (doc_id,))
    db.commit()
    return ids


def test_qual_01_crowding_flagged_with_8_similar_neighbors(qual_env) -> None:
    """① 组织内在用 8 近邻高相似 → 判拥挤写 flags + 检测标记（scale/content_sha）。"""
    env = qual_env
    db = env["db"]
    # 隔离词面路（小语料 IDF 偏低属标定问题——本用例只验拥挤口径）
    from knowledge_lattice.core.docs.quality import QualityService

    quality = QualityService(
        env["backend"],
        dataclasses.replace(env["settings"], quality_low_idf_threshold=0.0),
    )
    _seed_cluster(db, "d_cluster", n=8)

    target = insert_chunk(
        db, doc_id="d_cluster", seq=99, content="拥挤目标块",
        content_seg="拥挤 目标 块",
    )
    db.insert_vector(_rid_of(db, target), LABEL, _near_base(99))
    db.commit()

    result = quality.detect_chunk(_rid_of(db, target))
    assert result["reason"] == "vector_crowding"
    assert result["mean_sim"] is not None and result["mean_sim"] > 0.92

    flags = env["backend"].list_quality_flags("d_cluster")
    assert len(flags) == 1
    flag = flags[0]
    assert flag["chunk_id"] == target
    assert flag["reason"] == "vector_crowding"
    assert flag["state"] == "open"
    detail = json.loads(flag["detail_json"])
    assert len(detail["neighbors"]) == 8  # top-8 全体（库里恰 8 个近邻）
    assert detail["mean_sim"] > 0.92
    # 检测标记：语料规模 + 内容指纹（#42 P1-3 缓存键基础）
    row = db.execute(
        "SELECT detected_at_scale, content_sha FROM chunks WHERE id = ?", (target,)
    ).fetchone()
    assert row[0] == env["backend"].org_active_chunk_count(ORG) == 14  # matrix 5 + 簇 9
    assert row[1] and row[1].startswith("sha256:")


def test_qual_02_crowding_excludes_tombstone_old_version(qual_env) -> None:
    """②a 仅与 tombstone 旧版本块相似 → 不判拥挤（近邻限定在用版本——#33 P1-10）。"""
    env = qual_env
    db, quality = env["db"], env["quality"]
    # v1：8 个相似块（随后整体 tombstone——模拟覆盖上传切换后）
    seed_document(db, doc_id="d_ver", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_ver", {"region": ["CN"]})
    v1_ids = []
    for i in range(8):
        cid = insert_chunk(
            db, doc_id="d_ver", seq=i + 1, version=1, content=f"旧版本条款{i}",
            content_seg=f"旧 版本 条款 {i}", tombstone=1,
        )
        db.insert_vector(_rid_of(db, cid), LABEL, _near_base(i))
        v1_ids.append(cid)
    # v2 在用：目标块与 v1 高相似，但 v2 内无其他相似块
    target = insert_chunk(
        db, doc_id="d_ver", seq=1, version=2, content="新版本目标块",
        content_seg="新 版本 目标 块 稀有标记甲",
    )
    db.insert_vector(_rid_of(db, target), LABEL, _near_base(50))
    db.execute(
        "UPDATE documents SET active_version = 2, active_status = 'searchable_full'"
        " WHERE id = 'd_ver'"
    )
    db.commit()

    # 隔离词面路（小语料 IDF 天然偏低——非本用例口径）：只验拥挤
    from knowledge_lattice.core.docs.quality import QualityService

    no_idf = QualityService(
        env["backend"],
        dataclasses.replace(env["settings"], quality_low_idf_threshold=0.0),
    )
    result = no_idf.detect_chunk(_rid_of(db, target))
    # tombstone 旧版本块不进近邻池 → 无近邻 → 不判拥挤
    assert result["reason"] is None
    assert env["backend"].list_quality_flags("d_ver") == []


def test_qual_03_crowding_excludes_other_org(qual_env) -> None:
    """②b 仅与他组织（org:gl）块相似 → 不判拥挤（近邻限定本组织——#33 P1-10）。"""
    env = qual_env
    db, quality = env["db"], env["quality"]
    # org:gl 相似簇（u_owner 无 membership 于 gl——纯造数，不经上传链）
    seed_dataset(db, ORG_GL, "ds:gl")
    seed_document(
        db, doc_id="d_gl_nb", org_id=ORG_GL, dataset_id="ds:gl", owner_user_id="u_owner"
    )
    for i in range(8):
        cid = insert_chunk(
            db, doc_id="d_gl_nb", seq=i + 1, content=f"gl 邻居{i}",
            content_seg=f"gl 邻居 {i}",
        )
        db.insert_vector(_rid_of(db, cid), LABEL, _near_base(i))
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_gl_nb'")

    # org:tax 目标块：与 gl 簇同向，但本组织无相似块
    target = _seed_cluster(db, "d_tax_iso", n=0)  # 建文档（无簇）
    target = insert_chunk(
        db, doc_id="d_tax_iso", seq=1, content="本组织孤立块",
        content_seg="本 组织 孤立 块 稀有标记乙",
    )
    db.insert_vector(_rid_of(db, target), LABEL, _near_base(77))
    db.commit()

    from knowledge_lattice.core.docs.quality import QualityService

    no_idf = QualityService(
        env["backend"],
        dataclasses.replace(env["settings"], quality_low_idf_threshold=0.0),
    )
    result = no_idf.detect_chunk(_rid_of(db, target))
    assert result["reason"] is None, "他组织块不得互为拥挤近邻（#33 P1-10）"
    assert env["backend"].list_quality_flags("d_tax_iso") == []


def test_qual_04_ingest_pipeline_quality_stage(qual_env) -> None:
    """③ 摄取管线 quality 阶段：run_task 完成 → 未检测块自动检测（§5.3 编排）。

    拥挤造数：同一文档两段相同文本（FakeEmbedder 确定性向量——同文本同向量，
    余弦 1.0）互为近邻 → 拥挤 flag 落库。
    """
    env = qual_env
    db = env["db"]
    # 段落 ≈300 jieba token（>256 min）：两段落各自成块（256+256<512 会并块，
    # 300+300>512 触发溢出 flush）——块数前提在下方断言。无标题行：两块内容
    # **完全相同**（FakeEmbedder 确定性向量 → 余弦 1.0 互为拥挤近邻）
    para = "重复样板条款：增值税一般纳税人销售货物并提供安装服务应当分别核算。" * 18
    txt = f"{para}\n\n{para}"
    doc_id, task_id = env["service"].create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="拥挤样例",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=txt.encode("utf-8"), mime_type="text/plain", filename="dup.txt",
    )
    env["service"].run_task(task_id)

    n_chunks = db.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0]
    assert n_chunks == 2, f"拥挤造数前提：应为 2 块（got {n_chunks}）"

    doc = db.execute(
        "SELECT active_status FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    assert doc[0] == "searchable_full"  # 检测 best-effort 不回退状态
    flags = env["backend"].list_quality_flags(doc_id)
    assert flags, "quality 阶段应产生拥挤 flag（同文本双块互为近邻）"
    assert all(f["reason"] in ("vector_crowding", "both", "low_idf") for f in flags)
    # 检测标记落库（quality 阶段真实触达）
    marked = db.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND detected_at_scale IS NOT NULL",
        (doc_id,),
    ).fetchone()[0]
    assert marked == db.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0]
