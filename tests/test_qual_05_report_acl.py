"""TC-QUAL-05 报告页近邻防旁路【单测｜M1——双后端参数化】（T18 单测形态）。

u_cn（region=[CN]）查看某 flags 明细，其近邻含 OS-only 块 → 近邻内容展示过
**同一套 ACL**（OS-only 块不出现）；`detail_json` 原始数据不因报告页而泄漏
（存储不改写——展示层过滤）。REST 面在 test_fts_04（PATCH/报告端点联动）覆盖。
"""

from __future__ import annotations

import json

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


def _seed_cross_acl_cluster(db) -> str:
    """拥挤簇横跨 region=CN 与 region=OS 文档（检测为组织口径——近邻含 OS-only）。"""
    seed_document(db, doc_id="d_cn_view", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_cn_view", {"region": ["CN"]})
    seed_document(db, doc_id="d_os_nb", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_os_nb", {"region": ["OS"]})
    i = 0
    for doc in ("d_cn_view", "d_os_nb"):
        cid = insert_chunk(
            db, doc_id=doc, seq=1, content=f"{doc} 拥挤块",
            content_seg=f"{doc} 拥挤 块",
        )
        db.insert_vector(_rid(db, cid), LABEL, _vec(i))
        i += 1
    # u_cn 可见的同簇块（第三邻——近邻池内）
    cid = insert_chunk(
        db, doc_id="d_cn_view", seq=2, content="d_cn_view 可见近邻块",
        content_seg="可见 近邻 块",
    )
    db.insert_vector(_rid(db, cid), LABEL, _vec(2))
    for doc in ("d_cn_view", "d_os_nb"):
        db.execute("UPDATE documents SET active_version = 1 WHERE id = ?", (doc,))
    db.commit()
    return "d_cn_view"


def test_qual_12_report_neighbors_filtered_by_acl(qual_env) -> None:
    """近邻展示过同一套 ACL：u_cn 的报告不含 OS-only 近邻；detail_json 原样保留。"""
    env = qual_env
    db, quality = env["db"], env["quality"]
    doc_id = _seed_cross_acl_cluster(db)

    # 检测（组织口径——近邻含 OS-only 块，写进 detail_json）
    target_rid = _rid(db, "chk:d_cn_view:v1:1")
    result = quality.detect_chunk(target_rid)
    assert result["reason"] in ("vector_crowding", "both"), "前置失败：应判拥挤"
    os_result = quality.detect_chunk(_rid(db, "chk:d_os_nb:v1:1"))
    assert os_result["reason"] in ("vector_crowding", "both"), "前置失败：OS 块同样拥挤"

    # 报告（u_cn：region=[CN]）——OS-only 近邻被剔除
    report = quality.quality_report(doc_id, user_id="u_cn", org_id=ORG)
    assert report["open_count"] >= 1
    flag = report["flags"][0]
    neighbor_docs = {n["doc_id"] for n in flag["neighbors"]}
    assert "d_os_nb" not in neighbor_docs, "OS-only 近邻不得出现在 u_cn 报告（T18）"
    assert "d_cn_view" in neighbor_docs, "可见近邻应保留（含内容 snippet）"
    visible_neighbor = [n for n in flag["neighbors"] if n["doc_id"] == "d_cn_view"][0]
    assert visible_neighbor["snippet"], "可见近邻应携带内容 snippet"

    # detail_json 原始存储不改写（OS-only rid 仍在——检测事实保留，仅展示过滤）
    raw = db.execute(
        "SELECT detail_json FROM quality_flags WHERE chunk_id = ?",
        ("chk:d_cn_view:v1:1",),
    ).fetchone()[0]
    rids_in_raw = {n["rid"] for n in json.loads(raw)["neighbors"]}
    os_rid = _rid(db, "chk:d_os_nb:v1:1")
    assert os_rid in rids_in_raw, "原始 detail_json 不因报告页改写"

    # u_os（region=[OS]）不可见 d_cn_view 文档本体——quality_report 编译其 ACL
    # 后近邻全被剔除（同一编译器语义；文档可见性入口在 REST 层另有 owner/管理分支）
    report_os = quality.quality_report("d_os_nb", user_id="u_os", org_id=ORG)
    os_flag = report_os["flags"][0]
    assert all(
        n["doc_id"] == "d_os_nb" for n in os_flag["neighbors"]
    ), "u_os 报告近邻应仅含 OS 文档块"


def test_qual_13_sample_open_flags_deterministic(qual_env) -> None:
    """误报抽查机制（M1.7 记录形态）：确定性抽样 open flags（复核入口）。"""
    env = qual_env
    db, quality = env["db"], env["quality"]
    doc_id = _seed_cross_acl_cluster(db)
    quality.detect_chunk(_rid(db, "chk:d_cn_view:v1:1"))
    quality.detect_chunk(_rid(db, "chk:d_cn_view:v1:2"))

    sample1 = quality.sample_open_flags(ORG, n=10, seed="m1")
    sample2 = quality.sample_open_flags(ORG, n=10, seed="m1")
    assert [f["flag_id"] for f in sample1] == [f["flag_id"] for f in sample2], (
        "同 seed 抽样应确定性可复现（复核记录可对账）"
    )
    assert sample1, "应抽到 open flags"
    assert all("mean_sim" in f or "avg_idf" in f for f in sample1)
    # 复核结论落点：patch_flag 状态迁移 + manual_tags 轨迹（记录形态闭环）
    flag_id = sample1[0]["flag_id"]
    out = quality.patch_flag(
        flag_id, org_id=ORG, actor_user_id="u_owner", state="resolved"
    )
    assert out["state"] == "resolved"
    assert quality.sample_open_flags(ORG, n=10, seed="m1") == [] or all(
        f["flag_id"] != flag_id
        for f in quality.sample_open_flags(ORG, n=10, seed="m1")
    ), "resolved 后不再进抽样面"
    events = db.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'quality_flag.patch'"
    ).fetchone()[0]
    assert events >= 1
