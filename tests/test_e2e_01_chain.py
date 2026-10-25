"""TC-E2E-01 摄取→检索全链【集成｜M0a（BM25 单路）】。

REST multipart 上传 docx（region=[CN]）→ 轮询文档状态 → 各时点检索：
- searchable_lexical 时点 BM25 命中（中间态可搜——useful-early）；
- searchable_full 后仍命中（双路+rerank 随 M1）；
- 结果带 chunk_id/doc_id/title/page_no/score/dims/source 溯源字段（MCP 契约 §6.1）；
- datasets 过滤与 doc_filter 正确收窄；top_k 服务端硬上限 20（TC-RET-07①）。
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _auth(app_env, uid="u_full"):
    return {"Authorization": f"Bearer {app_env['static'][uid]}"}


def _upload(app_env, *, path=None, dims=None, dataset="ds:vat_lib", uid="u_full"):
    path = path or (FIXTURES / "sample.docx")
    files = {"file": (path.name, path.read_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    data = {"dataset": dataset, "dims": json.dumps(dims if dims is not None else {"region": ["CN"]})}
    return app_env["client"].post(
        f"/api/orgs/org:tax/documents",
        files=files,
        data=data,
        headers={**_auth(app_env, uid), "X-Org-Id": "org:tax"},
    )


def test_full_chain_lexical_then_full(app_env) -> None:
    client = app_env["client"]
    embedder = app_env["embedder"]

    # --- searchable_lexical 时点：嵌入不可达 → 文档停在 lexical、BM25 可搜（不 500）---
    embedder.fail = True
    resp = _upload(app_env)
    assert resp.status_code == 202
    body = resp.json()
    doc_id, task_id = body["doc_id"], body["task_id"]
    assert body["status"] == "queued" and body["pending_version"] == 1

    doc = client.get(f"/api/orgs/org:tax/documents/{doc_id}", headers=_auth(app_env)).json()
    assert doc["active_version"] == 1  # D20 首次上传已切换
    assert doc["active_status"] == "searchable_lexical"  # 停在 lexical（中间态可搜）
    task = client.get(f"/api/orgs/org:tax/tasks/{task_id}", headers=_auth(app_env)).json()
    assert task["status"] == "failed"  # 嵌入失败可重试（TC-EMB-01/03 同款）

    hits = client.post(
        "/api/search",
        json={"query": "一般纳税人 安装服务 分别核算", "top_k": 8},
        headers={**_auth(app_env), "X-Org-Id": "org:tax"},
    )
    assert hits.status_code == 200
    payload = hits.json()
    assert payload["results"], "searchable_lexical 时点 BM25 应命中"
    row = payload["results"][0]
    # 溯源字段齐备（MCP 契约 §6.1）
    for field in ("chunk_id", "doc_id", "title", "page_no", "score", "dims", "source"):
        assert field in row, f"缺溯源字段 {field}"
    assert row["dims"] == {"region": ["CN"]}
    assert row["source"] == "user:u_full"
    assert 0.0 <= row["score"] <= 1.0

    # --- searchable_full 时点：嵌入恢复 → 重试任务 → full（双路+rerank 命中——M1 全配方）---
    embedder.fail = False
    # 任务重试：直接再跑同任务（阶段幂等从 embed 续）——经内部 runner 触发
    app_env["app"].state.service.ingest.run_task(task_id)
    doc = client.get(f"/api/orgs/org:tax/documents/{doc_id}", headers=_auth(app_env)).json()
    assert doc["active_status"] == "searchable_full"
    hits2 = client.post(
        "/api/search",
        json={"query": "一般纳税人", "top_k": 8},
        headers={**_auth(app_env), "X-Org-Id": "org:tax"},
    ).json()
    assert hits2["results"]
    # M1 全配方断言：full 时点双路可开（向量行已回写）+ 无降级标注 + 块级 vector_pending=False
    assert hits2["notice"]["degraded"] == [], "嵌入/rerank 均可用——无降级（rerank=none 为配置态）"
    assert hits2["notice"]["vector_pending"] is False, "结果块已全部嵌入（searchable_full）"
    full_hit_docs = {r["doc_id"] for r in hits2["results"]}
    assert doc_id in full_hit_docs

    # --- datasets 过滤 / doc_filter 收窄 ---
    narrowed = client.post(
        "/api/search",
        json={"query": "一般纳税人", "datasets": ["ds:vat_lib"]},
        headers={**_auth(app_env), "X-Org-Id": "org:tax"},
    ).json()
    assert narrowed["results"]
    excluded = client.post(
        "/api/search",
        json={"query": "一般纳税人", "datasets": ["ds:not_exist"]},
        headers={**_auth(app_env), "X-Org-Id": "org:tax"},
    ).json()
    assert excluded["results"] == []
    by_doc = client.post(
        "/api/search",
        json={"query": "一般纳税人", "doc_filter": [doc_id]},
        headers={**_auth(app_env), "X-Org-Id": "org:tax"},
    ).json()
    assert by_doc["results"] and all(r["doc_id"] == doc_id for r in by_doc["results"])

    # --- top_k 服务端硬上限 20：真实断言见 test_r2_committer_fixes.py
    # （P3-15：本处样例块数少，`<= 20` 恒真属空转断言，已移除；
    #   P3-R2-1 修正：注释原指 test_r2_review_fixes.py——top_k 断言实在
    #   test_r2_committer_fixes.py::test_p3_x_top_k_hard_limit）---


def test_upload_validation_dims_out_of_grants(app_env) -> None:
    """上传值须在授权内（P0-2.1 upload 时点校验——u_cn 无 OS 授权 → 403）。"""
    resp = _upload(app_env, dims={"region": ["OS"]}, uid="u_cn")
    assert resp.status_code == 403
    # 必选维度缺值 → 400
    resp2 = _upload(app_env, dims={}, uid="u_full")
    assert resp2.status_code == 400
    # 库不存在 → 400
    resp3 = _upload(app_env, dataset="ds:none", uid="u_full")
    assert resp3.status_code == 400
