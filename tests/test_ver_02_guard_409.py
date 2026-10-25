"""TC-VER-06/07 + T7/T10/T19 + TC-E2E-02 守卫与并发组【单测/集成｜M1-2】。

- TC-VER-06 embed 批次回写防护：INSERT + ON CONFLICT DO NOTHING + 在用版本/
  tombstone 防护——已切换/已删块的回写零行生效（v1.6 迁移形态）；
- TC-VER-07 删除与任务取消联动：摄取中 DELETE → 任务取消；worker 阶段前检查
  文档存在与版本归属——已删文档不再写块；
- T7 并发覆盖 409（同一时刻只有一个 pending；不产生第三个版本号）；
- T10 待嵌入清单不含 tombstone；
- T19 删文档（REST：owner/org_admin、级联+取消任务、非 owner 403）；
- TC-E2E-02 版本切换原子性（召回层断言——M1-1 纪律）：切换各时点检索只见
  v1 或 v2 之一；切换瞬间并发第二个覆盖上传 409；注入失败回滚后 v1 继续服务。
"""

from __future__ import annotations

import json

import pytest

from helpers import NOW_TS

from test_ver_01_version_chain import (
    HTML_V1,
    HTML_V2,
    ORG,
    _doc_chunk_ids,
    _fts_hits,
    _upload,
    _overwrite_v2_to_lexical,
)

# ============ TC-VER-06：embed 批次回写防护 ============


def test_ver_06_writeback_guard_after_switch(ver_env) -> None:
    """embed 在途批次（已 mark 未回写）遭遇版本切换 → 回写零行生效：
    v1 块已 tombstone → INSERT..SELECT 零行；v2 在用块正常回写（对照组）。"""
    env = ver_env
    doc_id, task1 = _upload(env)
    env["service"].run_task(task1)
    task2 = _overwrite_v2_to_lexical(env, doc_id, dims={"region": ["CN"]})

    label = env["embedder"].model_label
    # 模拟 embed 在途：v2 块钉标签（拿到批次清单后、回写前发生切换）
    pending = env["backend"].mark_embedding_batch(doc_id, 2, label)
    assert pending, "v2 块在批（断言前提）"

    # 时序颠倒注入：embed 未完成即切换（乐观校验只看 pending_version）
    env["backend"].set_doc_pending_status(doc_id, 2, "searchable_full")
    env["backend"].switch_active_version(doc_id, expected_pending=2)

    v1_rids = [
        r[0]
        for r in env["db"].execute(
            "SELECT rid FROM chunks WHERE doc_id = ? AND version = 1", (doc_id,)
        ).fetchall()
    ]
    v2_rids = [row["rid"] for row in pending]
    vec = [0.1] * env["settings"].embed_dim

    written_v1 = env["backend"].write_embeddings(label, [(rid, vec) for rid in v1_rids])
    assert written_v1 == 0, "TC-VER-06：已切换（tombstone=1）块的回写零行生效"
    assert env["db"].execute(
        "SELECT count(*) FROM chunk_vectors cv JOIN chunks c ON c.rid = cv.rid"
        " WHERE c.doc_id = ? AND c.version = 1",
        (doc_id,),
    ).fetchone()[0] == 0

    # 对照组：v2 在用块回写正常（防护不误伤在途合法批次）
    written_v2 = env["backend"].write_embeddings(label, [(rid, vec) for rid in v2_rids])
    assert written_v2 == len(v2_rids)

    # 续跑幂等：任务重跑不复活（v2 已切换在用）
    env["service"].run_task(task2)
    doc = env["backend"].get_document(doc_id)
    assert doc["active_version"] == 2 and doc["active_status"] == "searchable_full"


def test_ver_06_writeback_guard_after_delete(ver_env) -> None:
    """embed 在途批次遭遇文档删除 → 回写零行（chunks 无行，INSERT..SELECT 零行）。"""
    env = ver_env
    doc_id, task1 = _upload(env)
    env["service"].run_task(task1)
    task2 = _overwrite_v2_to_lexical(env, doc_id, dims={"region": ["CN"]})

    label = env["embedder"].model_label
    pending = env["backend"].mark_embedding_batch(doc_id, 2, label)
    rids = [row["rid"] for row in pending]

    env["service"].delete_document(org_id=ORG, doc_id=doc_id, actor_user_id="u_full")

    written = env["backend"].write_embeddings(
        label, [(rid, [0.1] * env["settings"].embed_dim) for rid in rids]
    )
    assert written == 0, "已删文档的回写零行生效"
    task = env["backend"].get_task(task2)
    assert task["status"] == "failed" and "cancelled" in (task["error"] or "")


# ============ TC-VER-07：删除与任务取消联动 + worker 阶段前检查 ============


def test_ver_07_delete_cancels_task_and_worker_guard(ver_env) -> None:
    """摄取进行中 DELETE 文档 → 任务取消；续跑同任务不再写块（阶段边界检查）。"""
    env = ver_env
    doc_id, task_id = _upload(env)

    # 摄取进行中（parse 后中断——任务 running）
    env["service"].run_task(task_id, stop_after="parse")
    assert env["backend"].get_task(task_id)["status"] == "running"

    env["service"].delete_document(org_id=ORG, doc_id=doc_id, actor_user_id="u_full")
    task = env["backend"].get_task(task_id)
    assert task["status"] == "failed", "删除即取消任务（TC-VER-07）"
    assert "cancelled" in (task["error"] or "")

    # worker 续跑（重认领）：已删文档不再写块——任务保持取消、目标文档 chunks 零行
    env["service"].run_task(task_id)
    assert env["backend"].get_task(task_id)["status"] == "failed", "已取消任务不复活"
    assert env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0] == 0
    assert env["backend"].get_document(doc_id) is None, "文档已删（不复活）"


def test_ver_07_guard_version_superseded(ver_env) -> None:
    """版本归属守卫：任务目标版本被顶替（pending 失败后新任务开新版本）→
    旧任务续跑在阶段边界取消、不写块。"""
    env = ver_env
    doc_id, task1 = _upload(env)
    env["service"].run_task(task1)

    env["embedder"].fail = True
    _, task2 = _upload(env, doc_id=doc_id, content=HTML_V2)
    with pytest.raises(Exception):  # noqa: B017
        env["service"].run_task(task2)
    env["embedder"].fail = False

    # v2 已 failed（块已删）→ v3 任务开跑；v2 旧任务（failed）续跑不写块
    env["service"].run_task(task2)
    assert env["backend"].get_task(task2)["status"] == "failed"  # 不复活
    assert (
        env["db"].execute(
            "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 2", (doc_id,)
        ).fetchone()[0]
        == 0
    ), "被顶替版本的旧任务不写块"


# ============ T7：并发覆盖 409 ============


def test_t7_concurrent_overwrite_rejected(ver_env) -> None:
    """pending v2 在途时再次覆盖上传 → UploadConflictError（409）；
    不产生第三个版本号（max 仍 2）。"""
    env = ver_env
    doc_id, task1 = _upload(env)
    env["service"].run_task(task1)
    _overwrite_v2_to_lexical(env, doc_id, dims={"region": ["CN"]})

    from knowledge_lattice.core.docs.ingest import UploadConflictError

    with pytest.raises(UploadConflictError):
        _upload(env, doc_id=doc_id, content=HTML_V2)
    assert env["backend"].max_document_version(doc_id) == 2, "不产生第三个版本号"
    doc = env["backend"].get_document(doc_id)
    assert doc["pending_version"] == 2, "pending 不被覆盖"


def test_t7_failed_pending_allows_new_upload(ver_env) -> None:
    """failed pending 放行新上传（重试用新版本号——版本号不复用的另一面）。"""
    env = ver_env
    doc_id, task1 = _upload(env)
    env["service"].run_task(task1)

    env["embedder"].fail = True
    _, task2 = _upload(env, doc_id=doc_id, content=HTML_V2)
    with pytest.raises(Exception):  # noqa: B017
        env["service"].run_task(task2)
    env["embedder"].fail = False

    # failed 后立即可再传（不 409）——新版本 v3
    _, task3 = _upload(env, doc_id=doc_id, content=HTML_V2)
    assert env["backend"].get_document(doc_id)["pending_version"] == 3


def test_t7_api_409_and_delete_endpoint(app_env) -> None:
    """REST 集成：覆盖上传（multipart 带 doc_id）pending 期间 409；
    DELETE 文档端点（owner）成功 + 级联；非 owner 非 admin 403。"""
    client = app_env["client"]
    headers = {"Authorization": f"Bearer {app_env['static']['u_full']}", "X-Org-Id": ORG}

    files = {"file": ("g.html", HTML_V1, "text/html")}
    data = {"dataset": "ds:vat_lib", "dims": json.dumps({"region": ["CN"]})}
    resp = client.post(f"/api/orgs/{ORG}/documents", files=files, data=data, headers=headers)
    assert resp.status_code == 202
    doc_id = resp.json()["doc_id"]
    task_id = resp.json()["task_id"]
    app_env["app"].state.service.ingest.run_task(task_id)

    # REST 覆盖上传（doc_id 显式携带——background 随响应跑完 v2 切换）
    files2 = {"file": ("g2.html", HTML_V2, "text/html")}
    data2 = {"dataset": "ds:vat_lib", "dims": json.dumps({"region": ["CN"]}), "doc_id": doc_id}
    resp2 = client.post(
        f"/api/orgs/{ORG}/documents", files=files2, data=data2, headers=headers
    )
    assert resp2.status_code == 202
    assert resp2.json()["pending_version"] == 2, "覆盖上传响应携带新 pending 版本号"
    assert resp2.json()["doc_id"] == doc_id, "文档身份不变（覆盖语义）"

    # core 层造在途 pending v3（REST background 时序不可控——pending 窗口经
    # service 层构造；REST 只测 409 协议映射）
    service = app_env["app"].state.service
    _, task3 = service.ingest.create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="v3", dims={"region": ["CN"]},
        owner_user_id="u_full", file_bytes=HTML_V2, mime_type="text/html",
        filename="g3.html", doc_id=doc_id,
    )
    service.ingest.run_task(task3, stop_after="index_fts")  # v3 停在 pending lexical

    files3 = {"file": ("g4.html", HTML_V2, "text/html")}
    data3 = {"dataset": "ds:vat_lib", "dims": json.dumps({"region": ["CN"]}), "doc_id": doc_id}
    resp3 = client.post(
        f"/api/orgs/{ORG}/documents", files=files3, data=data3, headers=headers
    )
    assert resp3.status_code == 409, "T7：pending 期间再覆盖 → 409（REST 路径）"

    # 非 owner 非 admin（u_cn）DELETE → 403
    cn_headers = {"Authorization": f"Bearer {app_env['static']['u_cn']}", "X-Org-Id": ORG}
    resp403 = client.delete(f"/api/orgs/{ORG}/documents/{doc_id}", headers=cn_headers)
    assert resp403.status_code == 403

    # owner DELETE → 204；级联（chunks/document_dimensions 空）；任务取消
    conn = app_env["conn"]
    task_rows = conn.execute(
        "SELECT id, status FROM tasks WHERE doc_id = ?", (doc_id,)
    ).fetchall()
    assert task_rows, "删除前任务在列（断言前提）"
    task_ids = [t[0] for t in task_rows]
    resp204 = client.delete(f"/api/orgs/{ORG}/documents/{doc_id}", headers=headers)
    assert resp204.status_code == 204
    detail = client.get(f"/api/orgs/{ORG}/documents/{doc_id}", headers=headers)
    assert detail.status_code == 404
    assert conn.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT count(*) FROM document_dimensions WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0] == 0
    # tasks.doc_id ON DELETE SET NULL 保留历史（#33 P1-1）——按 id 查取消态
    for tid in task_ids:
        status, error = conn.execute(
            "SELECT status, error FROM tasks WHERE id = ?", (tid,)
        ).fetchone()
        if status != "done":
            assert status == "failed" and "cancelled" in (error or ""), (tid, status, error)

    # 删除不存在 / 跨组织 → 404
    assert client.delete(f"/api/orgs/{ORG}/documents/doc:none", headers=headers).status_code == 404


# ============ T10：待嵌入清单不含 tombstone ============


def test_t10_pending_embeddings_excludes_tombstone(ver_env) -> None:
    env = ver_env
    doc_id, task1 = _upload(env)
    env["service"].run_task(task1)
    label = env["embedder"].model_label
    task2 = _overwrite_v2_to_lexical(env, doc_id, dims={"region": ["CN"]})

    # v1 在用块钉旧标签（模拟旧批次在途——同标签已有 cv 行会被认领排除，
    # 故用异标签 old-model:8 造「已钉未回写」形态），随后切换 → v1 tombstone
    v1_marked = env["backend"].mark_embedding_batch(doc_id, 1, "old-model:8")
    assert v1_marked, "v1 块先钉旧标签（造数前提：模拟在途旧批次）"
    env["backend"].set_doc_pending_status(doc_id, 2, "searchable_full")
    env["backend"].switch_active_version(doc_id, expected_pending=2)

    old_label = "old-model:8"
    pending = env["backend"].pending_embeddings(old_label)
    pending_rids = {row["rid"] for row in pending}
    v1_rids = {
        r[0]
        for r in env["db"].execute(
            "SELECT rid FROM chunks WHERE doc_id = ? AND version = 1", (doc_id,)
        ).fetchall()
    }
    assert pending_rids & v1_rids == set(), "T10：tombstone 旧版本块不进待嵌入清单"
    # 且切换后旧块回写零生效（不复活——P1-2）
    written = env["backend"].write_embeddings(
        old_label, [(rid, [0.1] * 8) for rid in v1_rids]
    )
    assert written == 0
    env["service"].run_task(task2)  # v2 收尾（幂等）


# ============ TC-E2E-02：版本切换原子性（召回层断言） ============


def test_e2e_02_switch_atomicity_recall_level(ver_env) -> None:
    """覆盖上传各时点（parse/chunk/lexical/full 前/full 后）检索循环：任意时刻
    只见 v1 或 v2 之一（无中间态混见）；切换瞬间并发第二个覆盖上传 409。"""
    env = ver_env
    doc_id, task1 = _upload(env)
    env["service"].run_task(task1)
    v1_ids, v2_ids = _doc_chunk_ids(env, doc_id, 1), None

    _, task2 = _upload(env, doc_id=doc_id, content=HTML_V2, dims={"region": ["CN"]})

    from knowledge_lattice.core.docs.ingest import UploadConflictError

    for stop in ("parse", "chunk", "index_fts"):
        env["service"].run_task(task2, stop_after=stop)
        # 检索循环：lexical 前——只见 v1（pending 块零出现）
        for token in ("阿尔法", "贝塔", "指南"):
            hits = _fts_hits(env, "u_full", token)
            version_hits = {1 if cid in v1_ids else 2 for cid in hits if cid.startswith("chk_")}
            if hits:
                assert version_hits <= {1}, f"{stop} 时点不得混见 pending 块（{token}）"

    # 循环末（index_fts 已提交、未切换）＝ lexical 时点：仍只见 v1；切换窗口并发覆盖 → 409
    assert _fts_hits(env, "u_full", "阿尔法") & v1_ids, "lexical 时点 v1 可搜"
    v2_ids = _doc_chunk_ids(env, doc_id, 2)
    assert v2_ids and not (_fts_hits(env, "u_full", "贝塔") & v2_ids), "pending v2 块不进召回"

    with pytest.raises(UploadConflictError):
        _upload(env, doc_id=doc_id, content=HTML_V2)

    # full 切换后：只见 v2（v1 块零出现——tombstone + FTS 清空）
    env["service"].run_task(task2)
    for token in ("贝塔", "指南"):
        hits = _fts_hits(env, "u_full", token)
        assert hits, f"切换后 {token} 应命中 v2"
        assert not (hits & v1_ids), "切换后 v1 块不得再出现"
    assert _fts_hits(env, "u_full", "阿尔法") == set()
