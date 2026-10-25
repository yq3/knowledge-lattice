"""TC-VER-01~05 + T6/T8/T9/T21 版本在用制全链【单测｜M1-2】（双后端参数化）。

覆盖（design §5.3 阶段编排 + §4 五字段状态机；D20/D22①②）：
- 首次上传 active 0→1 在 searchable_lexical 即切（TC-VER-01）；
- 覆盖上传 lexical 时点不切换、searchable_full 时点单事务切换（TC-VER-02）；
- 切换事务逐项：旧块 tombstone=1 + chunk_vectors 行 DELETE + 五列 FTS 清空 +
  documents 五字段更新（WHERE pending_version=:expected 乐观校验）+
  pending_dims_json 落 document_dimensions（TC-VER-04）；中途失败全回滚；
- 失败版本号不复用（TC-VER-03）+ 失败块立即物理删除无 FTS 残留（T8）；
- 切换后 FTS 层无旧版本命中（T9——直查 FTS 绕过服务层）；
- v2 改维度切换前后无双方可见（T6——u_cn_vat 视角，recall 层断言）；
- 授权撤销后 owner 覆盖上传处理窗口检索不到任何版本（T21）；
- fetch 旧块替代提示（TC-VER-05——replaced_by 对象、不返回旧内容、不报不存在）。

召回层断言纪律（M1-1 教训）：切换各时点的可见面断言落 recall_fts 层（不只断
search() 最终结果）。
"""

from __future__ import annotations

import pytest

from helpers import NOW_TS, grant_by_key, seed_membership, seed_user

ORG = "org:tax"

HTML_V1 = (
    "<html><body><h1>增值税申报指南 v1</h1>"
    "<p>阿尔法条款：一般纳税人销售自产货物并提供安装服务的，应分别核算。</p></body></html>"
).encode("utf-8")
HTML_V2 = (
    "<html><body><h1>增值税申报指南 v2</h1>"
    "<p>贝塔条款：小规模纳税人发生增值税应税销售行为征收管理。</p></body></html>"
).encode("utf-8")


def _upload(env, *, dims=None, doc_id=None, owner="u_full", title="指南", content=HTML_V1):
    return env["service"].create_document(
        org_id=ORG,
        dataset_id="ds:vat_lib",
        title=title,
        dims=dims if dims is not None else {"region": ["CN"], "tax_type": ["VAT"]},
        owner_user_id=owner,
        file_bytes=content,
        mime_type="text/html",
        filename="guide.html",
        doc_id=doc_id,
    )


def _fts_hits(env, user_id: str, token: str) -> set[str]:
    """recall_fts 层可见 chunk_id 集（召回层断言——M1-1 纪律）。"""
    plan = env["db"].compile_acl(user_id, ORG, now=NOW_TS)
    return {r["chunk_id"] for r in env["backend"].recall_fts([token], plan, top_k=50)}


def _doc_chunk_ids(env, doc_id: str, version: int) -> set[str]:
    rows = env["db"].execute(
        "SELECT id FROM chunks WHERE doc_id = ? AND version = ?", (doc_id, version)
    ).fetchall()
    return {r[0] for r in rows}


# ============ TC-VER-01：首次上传在 searchable_lexical 即切换 ============


def test_ver_01_first_upload_switches_at_lexical(ver_env) -> None:
    embedder = ver_env["embedder"]
    embedder.fail = True  # 停在 lexical（嵌入失败不 500）

    doc_id, task_id = _upload(ver_env)
    with pytest.raises(Exception):  # noqa: B017 —— 任务级失败冒泡（run_task 语义）
        ver_env["service"].run_task(task_id)

    doc = ver_env["backend"].get_document(doc_id)
    assert doc["active_version"] == 1, "首次上传 lexical 时点即刻切在用（D20）"
    assert doc["active_status"] == "searchable_lexical"
    assert doc["pending_version"] is None and doc["pending_status"] is None
    assert doc["active_error"], "嵌入/质量失败写 active_error（#33 P0-2.2）"

    # BM25 即刻可搜（useful-early）
    assert _fts_hits(ver_env, "u_full", "阿尔法"), "lexical 时点 BM25 应命中"


# ============ TC-VER-02 + TC-VER-04：覆盖上传切换时机与切换事务内容 ============


def _overwrite_v2_to_lexical(env, doc_id: str, *, dims=None, owner="u_full"):
    """覆盖上传 v2 并推进到 searchable_lexical 时点（不切换——D20）。"""
    _, task2 = _upload(env, doc_id=doc_id, dims=dims, owner=owner, content=HTML_V2)
    env["service"].run_task(task2, stop_after="index_fts")
    return task2


def test_ver_02_overwrite_lexical_no_switch_full_switch(ver_env) -> None:
    doc_id, task1 = _upload(ver_env)
    ver_env["service"].run_task(task1)  # v1 → searchable_full

    # --- lexical 时点：不切换（检索只见 v1）---
    task2 = _overwrite_v2_to_lexical(ver_env, doc_id, dims={"region": ["CN"], "tax_type": ["VAT"]})
    doc = ver_env["backend"].get_document(doc_id)
    assert doc["active_version"] == 1 and doc["active_status"] == "searchable_full"
    assert doc["pending_version"] == 2 and doc["pending_status"] == "searchable_lexical"

    hits = _fts_hits(ver_env, "u_full", "阿尔法")
    assert any(cid.startswith("chk_") for cid in hits), "v1 全程服务（lexical 时点检索只见 v1）"
    assert _fts_hits(ver_env, "u_full", "贝塔") == set(), "pending v2 块不进 BM25 路"

    # --- full 时点：单事务切换（续跑 embed → searchable_full → switch）---
    ver_env["service"].run_task(task2)

    doc = ver_env["backend"].get_document(doc_id)
    assert doc["active_version"] == 2 and doc["active_status"] == "searchable_full"
    assert doc["pending_version"] is None and doc["pending_status"] is None
    assert doc["pending_error"] is None

    # TC-VER-04 事务内容逐项断言：
    old_rows = ver_env["db"].execute(
        "SELECT tombstone, title_seg, content_seg, keywords, llm_keywords, tags"
        " FROM chunks WHERE doc_id = ? AND version = 1",
        (doc_id,),
    ).fetchall()
    assert old_rows and all(
        r[0] == 1 and r[1] == "" and r[2] == "" and r[3] == "" and r[4] == "" and r[5] == ""
        for r in old_rows
    ), "旧块 tombstone=1 + 五列 FTS 内容清空"

    cv_left = ver_env["db"].execute(
        "SELECT count(*) FROM chunk_vectors cv JOIN chunks c ON c.rid = cv.rid"
        " WHERE c.doc_id = ? AND c.version = 1",
        (doc_id,),
    ).fetchone()[0]
    assert cv_left == 0, "旧版本块对应 chunk_vectors 向量行已 DELETE（v1.1 拍板②形态）"

    # dims 落地：pending_dims_json → document_dimensions（切换前不生效、切换即生效）
    dims_rows = ver_env["db"].execute(
        "SELECT dim.key, v.value FROM document_dimensions dd"
        " JOIN dimensions dim ON dim.id = dd.dimension_id"
        " JOIN dimension_values v ON v.id = dd.value_id WHERE dd.doc_id = ?",
        (doc_id,),
    ).fetchall()
    assert {(r[0], r[1]) for r in dims_rows} == {("region", "CN"), ("tax_type", "VAT")}
    assert ver_env["backend"].get_document(doc_id)["pending_dims_json"] is None

    # T9：切换后仅 v1 内容关键词零命中（绕过服务层直查 FTS 也测）
    assert _fts_hits(ver_env, "u_full", "阿尔法") == set(), "T9：FTS 层无旧版本命中"
    assert ver_env["db"].fts_word_count("阿尔法") == 0, "五列已清空——FTS 直查零命中"
    assert _fts_hits(ver_env, "u_full", "贝塔"), "v2 切换后可搜"


def test_ver_02_vec_recall_only_active_version(ver_env) -> None:
    """TC-E2E-02 召回层断言（向量路）：切换前后 recall_vec 只见在用版本块——
    v1 cv 行随切换事务 DELETE（v1.1 拍板②）+ 版本条件在 cv JOIN，tombstone 块
    零距离计算（M1-1 教训：不只断 search() 最终结果）。"""
    env = ver_env
    doc_id, task1 = _upload(env)
    env["service"].run_task(task1)
    label = env["embedder"].model_label
    plan = env["db"].compile_acl("u_full", ORG, now=NOW_TS, embed_model=label)

    qv = env["embedder"].embed(["阿尔法"])[0]
    vec_hits = {r["chunk_id"] for r in env["backend"].recall_vec(qv, plan, top_k=50)}
    assert vec_hits & _doc_chunk_ids(env, doc_id, 1), "v1 在用（已嵌入）向量路可见"

    task2 = _overwrite_v2_to_lexical(env, doc_id, dims={"region": ["CN"]})
    # lexical 时点：v2 块无 cv 行（待嵌）→ 向量路仍只见 v1
    vec_mid = {r["chunk_id"] for r in env["backend"].recall_vec(qv, plan, top_k=50)}
    assert not (vec_mid & _doc_chunk_ids(env, doc_id, 2)), "pending 块无 cv 行不进向量路"

    env["service"].run_task(task2)  # v2 嵌入完成 + 切换
    vec_after = {r["chunk_id"] for r in env["backend"].recall_vec(qv, plan, top_k=50)}
    assert not (vec_after & _doc_chunk_ids(env, doc_id, 1)), "tombstone 块不进向量路"
    assert vec_after & _doc_chunk_ids(env, doc_id, 2), "v2 嵌入后向量路可见"


def test_ver_04_switch_transaction_atomic_rollback(ver_env) -> None:
    """切换中途失败（dims 解析异常注入）→ 全回滚：v1 继续服务、pending 块零残留。"""
    doc_id, task1 = _upload(ver_env)
    ver_env["service"].run_task(task1)
    _overwrite_v2_to_lexical(ver_env, doc_id, dims={"region": ["CN"]})

    # 注入：pending_dims_json 指向不存在的取值 → 切换事务解析失败（P3-7 同款防护）
    ver_env["db"].execute(
        "UPDATE documents SET pending_dims_json = ? WHERE id = ?",
        ('{"region": ["NO_SUCH_VALUE"]}', doc_id),
    )

    from knowledge_lattice.core.docs.ingest import VersionConflictError

    with pytest.raises(RuntimeError, match="pending_dims"):
        ver_env["backend"].switch_active_version(doc_id, expected_pending=2)

    doc = ver_env["backend"].get_document(doc_id)
    assert doc["active_version"] == 1, "回滚：active 仍是 v1"
    assert doc["pending_version"] == 2 and doc["pending_status"] == "searchable_lexical"
    assert ver_env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 1 AND tombstone = 0",
        (doc_id,),
    ).fetchone()[0] > 0, "回滚：v1 块未 tombstone"
    assert _fts_hits(ver_env, "u_full", "阿尔法"), "回滚：v1 继续服务"
    assert _fts_hits(ver_env, "u_full", "贝塔") == set(), "回滚：pending 块不进召回"


def test_ver_04_optimistic_check_rejects_stale_expected(ver_env) -> None:
    """乐观校验：WHERE pending_version=:expected 不符 → 拒绝且不改任何状态。"""
    from knowledge_lattice.core.docs.ingest import VersionConflictError

    doc_id, task1 = _upload(ver_env)
    ver_env["service"].run_task(task1)
    _overwrite_v2_to_lexical(ver_env, doc_id, dims={"region": ["CN"]})

    with pytest.raises(VersionConflictError):
        ver_env["backend"].switch_active_version(doc_id, expected_pending=99)

    doc = ver_env["backend"].get_document(doc_id)
    assert doc["active_version"] == 1 and doc["pending_version"] == 2


# ============ TC-VER-03 + T8：失败版本号不复用、失败块无 FTS 残留 ============


def test_ver_03_failed_version_number_not_reused_and_blocks_deleted(ver_env) -> None:
    doc_id, task1 = _upload(ver_env)
    ver_env["service"].run_task(task1)

    # v2 在 embed 阶段失败
    ver_env["embedder"].fail = True
    _, task2 = _upload(ver_env, doc_id=doc_id, content=HTML_V2)
    with pytest.raises(Exception):  # noqa: B017
        ver_env["service"].run_task(task2)

    doc = ver_env["backend"].get_document(doc_id)
    assert doc["pending_status"] == "failed" and doc["pending_error"]
    assert doc["active_version"] == 1, "v1 不受影响"

    # T8：v2 块立即物理删除（ad 触发器移出 FTS）——MATCH 零命中
    assert ver_env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 2", (doc_id,)
    ).fetchone()[0] == 0, "失败版本块已物理删除"
    assert ver_env["db"].fts_word_count("贝塔") == 0, "T8：失败版本无 FTS 残留"
    assert _fts_hits(ver_env, "u_full", "阿尔法"), "v1 继续服务不受影响"

    # 重试：新 pending_version = max(历史)+1 = 3（失败版本号不复用）
    ver_env["embedder"].fail = False
    _, task3 = _upload(ver_env, doc_id=doc_id, content=HTML_V2)
    doc = ver_env["backend"].get_document(doc_id)
    assert doc["pending_version"] == 3, "TC-VER-03：失败版本号不复用（max+1）"
    assert doc["pending_status"] == "parsing"

    ver_env["service"].run_task(task3)
    doc = ver_env["backend"].get_document(doc_id)
    assert doc["active_version"] == 3 and doc["active_status"] == "searchable_full"
    # 历史（tombstone v1）可追溯
    assert ver_env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 1 AND tombstone = 1",
        (doc_id,),
    ).fetchone()[0] > 0, "tombstone 保留（90 天物理清理属 M2）"


# ============ T6：v2 改维度——切换前后无双方可见（完整切换链） ============


def test_t6_full_switch_chain_dims_visibility(ver_env) -> None:
    """T6（m0a-2 遗留 P3-4 补全——完整切换链）：admin_full 覆盖上传 v2 带
    region=[OS]（pending_dims_json），u_cn_vat 视角：pending 期间按 v1 维度判权
    （v2 新维度不生效）可见 v1；切换后按 v2 判权不可见；任一时刻两版本块不同时出现。"""
    # v1：region=[CN]+tax_type=[VAT]（u_cn_vat 双维度可见前提）
    doc_id, task1 = _upload(
        ver_env, dims={"region": ["CN"], "tax_type": ["VAT"]}, owner="admin_full"
    )
    ver_env["service"].run_task(task1)

    # 覆盖上传 v2 region=[OS]（admin_full 授权内——操作权限 org_admin + 写权限双前提）
    task2 = _overwrite_v2_to_lexical(
        ver_env, doc_id, dims={"region": ["OS"]}, owner="admin_full"
    )

    # pending 期间：按 v1 维度判权——u_cn_vat 可见 v1（P0-2.1：v2 新维度不生效）
    pending_hits = _fts_hits(ver_env, "u_cn_vat", "阿尔法")
    v1_ids = _doc_chunk_ids(ver_env, doc_id, 1)
    assert pending_hits & v1_ids, "pending 期间 u_cn_vat 可见 v1"
    assert _fts_hits(ver_env, "u_cn_vat", "贝塔") == set(), "pending 块任何时刻不可见"
    # pending_dims_json 尚未落 document_dimensions（v2 维度切换前不生效——T6）
    dim_keys = {
        r[0]
        for r in ver_env["db"].execute(
            "SELECT dim.key FROM document_dimensions dd"
            " JOIN dimensions dim ON dim.id = dd.dimension_id WHERE dd.doc_id = ?",
            (doc_id,),
        ).fetchall()
    }
    assert dim_keys == {"region", "tax_type"}, "pending 期间维度仍是 v1 的"

    # 切换后：按 v2 判权（region=[OS] 与 u_cn_vat 的 [CN] 无交集）→ 不可见
    ver_env["service"].run_task(task2)
    assert _fts_hits(ver_env, "u_cn_vat", "阿尔法") == set(), "切换后 u_cn_vat 不可见 v2"
    assert _fts_hits(ver_env, "u_cn_vat", "贝塔") == set()
    # 对照：u_os（region=[OS]）切换后可见 v2
    assert _fts_hits(ver_env, "u_os", "贝塔") & _doc_chunk_ids(ver_env, doc_id, 2)


# ============ T21：授权撤销后 owner 覆盖上传处理窗口检索不到任何版本 ============


def test_t21_owner_overwrite_window_after_grant_revoked(ver_env) -> None:
    """u_owner'（初始 region=[CN]+tax_type=[VAT]）覆盖上传 v2（upload 时点校验通过）
    → pending 期间撤销 region 授权 → 处理窗口 v1/v2 均零命中；切换后仍不可见。"""
    db = ver_env["db"]
    seed_user(db, "u_owner_prime")
    seed_membership(db, "u_owner_prime", ORG)
    grant_by_key(db, "u_owner_prime", key="region", value="CN")
    grant_by_key(db, "u_owner_prime", key="tax_type", value="VAT")

    doc_id, task1 = _upload(
        ver_env, dims={"region": ["CN"], "tax_type": ["VAT"]}, owner="u_owner_prime"
    )
    ver_env["service"].run_task(task1)

    # ① 覆盖上传 v2（region=[CN]——写权限校验在 upload 时点通过，FR-4）
    task2 = _overwrite_v2_to_lexical(
        ver_env, doc_id, dims={"region": ["CN"], "tax_type": ["VAT"]}, owner="u_owner_prime"
    )

    # ② pending 期间撤销 u_owner' 的 region 授权
    db.execute(
        "DELETE FROM user_dimension_grants WHERE user_id = ? AND dimension_id = ?",
        ("u_owner_prime", f"dim:{ORG}:region"),
    )

    # ③ 处理窗口（未切换）检索 d_t21：v1、v2 均零命中（查询时实时展开——D6）
    assert _fts_hits(ver_env, "u_owner_prime", "阿尔法") == set(), "v1 按维度判权不可见"
    assert _fts_hits(ver_env, "u_owner_prime", "贝塔") == set(), "pending 块本不可见"
    assert _fts_hits(ver_env, "u_owner_prime", "指南") == set(), "owner 身份不产生任何放宽"

    # ④ v2 完成、单事务切换后再检索：仍不可见
    ver_env["service"].run_task(task2)
    assert ver_env["backend"].get_document(doc_id)["active_version"] == 2
    assert _fts_hits(ver_env, "u_owner_prime", "贝塔") == set(), "切换后仍不可见（T21 验收句）"


# ============ TC-VER-05：fetch 旧块替代提示 ============


def test_ver_05_fetch_window_and_replaced_by(ver_env) -> None:
    from knowledge_lattice.core.docs.fetch import fetch_chunks

    doc_id, task1 = _upload(ver_env)
    ver_env["service"].run_task(task1)
    v1_ids = sorted(_doc_chunk_ids(ver_env, doc_id, 1))

    # 在用块：返回前后窗口内容
    out = fetch_chunks(
        ver_env["backend"], user_id="u_full", org_id=ORG, chunk_id=v1_ids[0], window=1
    )
    assert out["replaced_by"] is None
    assert out["chunks"] and out["chunks"][0]["chunk_id"] == v1_ids[0]
    assert {"chunk_id", "seq", "content", "page_no"} <= set(out["chunks"][0])

    # 覆盖切换 → 旧 chunk_id fetch：replaced_by 对象、不返回旧内容、不报不存在
    task2 = _overwrite_v2_to_lexical(ver_env, doc_id, dims={"region": ["CN"]})
    ver_env["service"].run_task(task2)

    out2 = fetch_chunks(
        ver_env["backend"], user_id="u_full", org_id=ORG, chunk_id=v1_ids[0], window=1
    )
    assert out2["chunks"] == [], "不返回旧内容（FR-1）"
    assert out2["replaced_by"] == {"doc_id": doc_id, "active_version": 2}

    # 不可见用户（文档 region=[CN] 对 u_os 无交集）：404 语义——不泄漏存在性
    from knowledge_lattice.core.docs.fetch import FetchNotFoundError

    with pytest.raises(FetchNotFoundError):
        fetch_chunks(
            ver_env["backend"], user_id="u_os", org_id=ORG, chunk_id=v1_ids[0], window=1
        )
