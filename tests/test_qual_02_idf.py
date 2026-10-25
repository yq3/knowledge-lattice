"""TC-QUAL-02 词面通用度【单测｜M1——双后端参数化】。

- token 平均 IDF 低于绝对阈值 → 判通用度低写 flags（reason=low_idf）；
- 新组织（冷启动：在用块数 < quality_cold_start_min）→ **引用全局语料 IDF**
  （不因组织语料为空而误判——detail.idf_scope=global）；
- 稀有 token 高 IDF → 不判通用（对照组）。
"""

from __future__ import annotations

import dataclasses
import json

from helpers import insert_chunk, seed_dataset, seed_doc_dims, seed_document

ORG = "org:tax"
ORG_GL = "org:gl"
LABEL = "fake-embed:8"
_VEC = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def _rid(db, chunk_id: str) -> int:
    return db.execute("SELECT rid FROM chunks WHERE id = ?", (chunk_id,)).fetchone()[0]


def _seed_corpus(db, *, doc_id: str, n: int, seg: str, org_id: str = ORG) -> None:
    """n 个单块文档，content_seg 全含给定通用词——推高 df。"""
    seed_document(
        db, doc_id=doc_id, org_id=org_id,
        dataset_id="ds:vat_lib" if org_id == ORG else "ds:gl",
        owner_user_id="u_owner",
    )
    seed_doc_dims(db, doc_id, {"region": ["CN"]}) if org_id == ORG else None
    for i in range(n):
        cid = insert_chunk(
            db, doc_id=doc_id, seq=i + 1, content=f"{doc_id} 语料块 {i}",
            content_seg=f"{seg} 语料 块 {i}",
        )
        db.insert_vector(_rid(db, cid), LABEL, list(_VEC))
    db.execute("UPDATE documents SET active_version = 1 WHERE id = ?", (doc_id,))
    db.commit()


def test_qual_05_low_idf_flagged(qual_env) -> None:
    """通用词块（token 全员高频）→ 平均 IDF 低 → low_idf flag。"""
    from knowledge_lattice.core.docs.quality import QualityService

    env = qual_env
    db = env["db"]
    # 隔离拥挤路（同向测试向量会误触拥挤——本用例只验词面口径）
    quality = QualityService(
        env["backend"],
        dataclasses.replace(env["settings"], quality_crowding_threshold=1.1),
    )
    # 组织语料 20 块，全部含「通用词」；另含区分词 df=1
    _seed_corpus(db, doc_id="d_idf_corpus", n=20, seg="通用词")

    seed_document(db, doc_id="d_generic", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_generic", {"region": ["CN"]})
    generic = insert_chunk(
        db, doc_id="d_generic", seq=1, content="通用内容",
        content_seg="通用词 通用词 通用词 通用词",
    )
    db.insert_vector(_rid(db, generic), LABEL, list(_VEC))
    rare = insert_chunk(
        db, doc_id="d_generic", seq=2, content="稀有内容",
        content_seg="稀有词甲 稀有词乙 稀有词丙",
    )
    db.insert_vector(_rid(db, rare), LABEL, list(_VEC))
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_generic'")
    db.commit()

    r_generic = quality.detect_chunk(_rid(db, generic))
    assert r_generic["reason"] in ("low_idf", "both"), "通用词块应判词面通用度低"
    assert r_generic["avg_idf"] is not None and r_generic["avg_idf"] < 3.0

    flag = env["backend"].list_quality_flags("d_generic")[0]
    assert flag["chunk_id"] == generic
    detail = json.loads(flag["detail_json"])
    assert detail["idf_scope"] == "org"  # 组织语料充足（22 块 ≥ 冷启动下限）
    assert detail["avg_idf"] < 3.0

    # 对照组：稀有词块（df=1 → IDF=log(22)≈3.09）不判通用
    r_rare = quality.detect_chunk(_rid(db, rare))
    assert r_rare["reason"] is None, "稀有词块不应判词面通用度低"


def test_qual_06_cold_start_uses_global_idf(qual_env) -> None:
    """冷启动：org:gl 无语料（块数 < cold_start_min）→ 全局语料 IDF 判定。"""
    from knowledge_lattice.core.docs.quality import QualityService

    env = qual_env
    db = env["db"]
    quality = QualityService(
        env["backend"],
        dataclasses.replace(env["settings"], quality_crowding_threshold=1.1),
    )
    # 全局语料：org:tax 20 块全含「跨组织常见词」
    _seed_corpus(db, doc_id="d_global_corpus", n=20, seg="跨组织常见词")

    # org:gl 新组织：仅 1 块（< cold_start_min=10）——组织内 df 无意义
    seed_dataset(db, ORG_GL, "ds:gl")
    seed_document(
        db, doc_id="d_gl_new", org_id=ORG_GL, dataset_id="ds:gl", owner_user_id="u_owner"
    )
    target = insert_chunk(
        db, doc_id="d_gl_new", seq=1, content="冷启动块",
        content_seg="跨组织常见词 跨组织常见词",
    )
    db.insert_vector(_rid(db, target), LABEL, list(_VEC))
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_gl_new'")
    db.commit()

    result = quality.detect_chunk(_rid(db, target))
    assert result["reason"] in ("low_idf", "both"), (
        "冷启动应引用全局语料 IDF 判出通用词（不因组织语料为空而漏判）"
    )
    flag = env["backend"].list_quality_flags("d_gl_new")[0]
    detail = json.loads(flag["detail_json"])
    assert detail["idf_scope"] == "global"
    # 全局口径：N=21（tax 20 + gl 1），df=21 → IDF≈0
    assert detail["avg_idf"] < 3.0
