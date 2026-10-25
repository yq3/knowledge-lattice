"""TC-FTS-04 keywords 列人工词纯净性【单测｜M1——双后端参数化】。

- `keywords` 仅含人工提交词（jieba 高频词不混入——重复会被 ×5 加权放大，#32 P1-3）；
- `llm_keywords` 仅由质量环 LLM 写入（来源分层：内容不交叉）；
- jieba 分词只产 `content_seg` / `title_seg`。

REST 面闭环（M1-4 硬条件——m1-1/m1-2 移交补验）：PATCH /api/quality-flags/{id}
写入路径端到端——人工词经 REST 写入 `keywords`，不污染（不经 jieba、不混
llm_keywords），加权收益在检索面生效。
"""

from __future__ import annotations

from helpers import insert_chunk, seed_doc_dims, seed_document
from knowledge_lattice.adapters.tokenizer import segment


def test_fts_04_keywords_only_manual_terms(ret_stack) -> None:
    """keywords 仅含人工词：jieba 切分产物与 keywords 列零交集；权重放大面不污染。"""
    db = ret_stack["db"]
    content = "增值税一般纳税人销售货物并提供安装服务的，应当分别核算销售额"
    manual_words = "人工标记词 业务术语"  # 人工补标写入（PATCH 同源语义）
    llm_words = "LLM增强词"           # 质量环 LLM 写入

    seed_document(db, doc_id="d_kw", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_kw", {"region": ["CN"]})
    insert_chunk(
        db, doc_id="d_kw", seq=1, content=content,
        content_seg=" ".join(segment(content)),  # jieba 只产 content_seg/title_seg
        title_seg=" ".join(segment(content)),
        keywords=manual_words,                   # 人工提交词（来源：人工）
        llm_keywords=llm_words,                  # LLM 写入（来源：质量环）
        tags="",
    )
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_kw'")
    db.commit()

    row = db.execute(
        "SELECT keywords, llm_keywords, content_seg, title_seg FROM chunks"
        " WHERE doc_id = 'd_kw' AND tombstone = 0"
    ).fetchone()
    keywords, llm_keywords, content_seg, title_seg = row

    # ① 来源分层：keywords = 人工词集合、llm_keywords = LLM 词——写入面不交叉
    #（列级字面断言：各自列只含本来源写入的词面；token 级碎片共现不作断言——
    #  jieba 对「人工标记词」等非词典词的碎片切分与本用例无关）
    assert keywords == manual_words
    assert llm_keywords == llm_words
    for term in manual_words.split():
        assert term not in llm_keywords
    assert "LLM增强词" not in keywords

    # ② jieba 高频词不混入 keywords：分词产物与人工词列零交集
    jieba_tokens = set(segment(content))
    assert jieba_tokens & set(segment(keywords)) == set(), (
        "jieba 分词只产 content_seg/title_seg——keywords 列不得混入分词产物"
        "（重复词会被 ×5 加权放大）"
    )
    assert jieba_tokens & set(segment(llm_keywords)) == set()

    # ③ content_seg/title_seg 确为 jieba 形态（空格连接 token——与 keywords 写法可区分）
    assert content_seg == " ".join(segment(content))
    assert title_seg == " ".join(segment(content))
    # 人工词不在 jieba 产物中（列间零渗透的另一面）
    assert set(segment(keywords)).isdisjoint(jieba_tokens)


def test_fts_04_manual_keyword_weight_amplifies(ret_stack) -> None:
    """人工词 ×5 加权面（#32 P1-3 动机复验）：keywords 命中块名次高于 content 命中块。"""
    from knowledge_lattice.store.backend import AclPlan

    db, backend = ret_stack["db"], ret_stack["backend"]
    seed_document(db, doc_id="d_kw2", dataset_id="ds:vat_lib", owner_user_id="u_owner")
    seed_doc_dims(db, "d_kw2", {"region": ["CN"]})
    insert_chunk(
        db, doc_id="d_kw2", seq=1, content="正文块", content_seg="独占词",
        title_seg="", keywords="", llm_keywords="", tags="",
    )
    insert_chunk(
        db, doc_id="d_kw2", seq=2, content="人工块", content_seg="",
        title_seg="", keywords="独占词", llm_keywords="", tags="",
    )
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_kw2'")
    db.commit()

    rows = backend.recall_fts(["独占词"], AclPlan(org_id="org:tax"), top_k=10)
    assert rows and rows[0]["chunk_id"] == "chk:d_kw2:v1:2", (
        "keywords(×5) 命中块名次应高于 content_seg(×1) 命中块——人工词纯净性保住加权收益"
    )
    assert [r["rank"] for r in rows] == [1, 2]


# ============ REST 面闭环（M1-4 硬条件——PATCH /api/quality-flags/{id} 补验） ============


def test_fts_04_rest_patch_endpoint_keywords_purity(app_env) -> None:
    """PATCH /api/quality-flags/{id} 端到端：人工词写入 keywords 列**不污染**——
    原样写入（不进 jieba）、llm_keywords 不动、加权收益在 FTS 生效（au 触发器
    / GENERATED 同步）；state 迁移与 manual_tags 轨迹随 PATCH 落库。"""
    client = app_env["client"]
    backend = app_env["app"].state.service.backend
    conn = app_env["conn"]
    from knowledge_lattice.store.sqlite.backend import SqliteBackend  # noqa: F401

    content = "跨境应税行为免征增值税的政策口径与备案要求说明段落"
    seed_document(conn, doc_id="d_kw3", dataset_id="ds:vat_lib", owner_user_id="u_full")
    seed_doc_dims(conn, "d_kw3", {"region": ["CN"]})
    chunk_id = insert_chunk(
        conn, doc_id="d_kw3", seq=1, content=content,
        content_seg=" ".join(segment(content)), title_seg="", llm_keywords="LLM已有词",
    )
    conn.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_kw3'")
    conn.commit()
    flag_id = backend.insert_quality_flag(
        chunk_id=chunk_id, doc_id="d_kw3", reason="vector_crowding",
        detail_json='{"mean_sim": 0.99}',
    )

    headers = {"Authorization": f"Bearer {app_env['static']['u_full']}",
               "X-Org-Id": "org:tax"}
    # 人工词与正文词汇面完全不相交（纯净性断言的锐度所在——人工标注的是
    # 「检索视角词」，不是对正文分词结果的复读）
    manual = "纳税信用等级 专用发票校验"
    resp = client.patch(
        f"/api/quality-flags/{flag_id}",
        json={"keywords": manual, "tags": "人工标签甲", "state": "resolved"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["keywords"] == manual, "keywords 列 = 人工提交词（原样写入）"
    assert body["tags"] == "人工标签甲"
    assert body["state"] == "resolved"

    row = conn.execute(
        "SELECT keywords, llm_keywords, tags FROM chunks WHERE id = ?", (chunk_id,)
    ).fetchone()
    keywords, llm_keywords, tags = row
    # ① 写入路径不污染：keywords 仅含人工提交词（未经 jieba 处理——字面等值）
    assert keywords == manual
    # ② llm_keywords 仅由质量环 LLM 写入——PATCH 不触碰（来源分层可断言）
    assert llm_keywords == "LLM已有词"
    assert tags == "人工标签甲"
    # ③ jieba 高频词不混入：分词产物与人工词列零交集（#32 P1-3）
    assert set(segment(content)) & set(segment(keywords)) == set()

    # ④ 加权收益在 FTS 生效：人工词经 keywords 命中该块（×5 加权路径）
    from knowledge_lattice.store.backend import AclPlan

    rows = backend.recall_fts(["纳税信用等级"], AclPlan(org_id="org:tax"), top_k=5)
    assert any(r["chunk_id"] == chunk_id for r in rows), (
        "PATCH 写入的人工词应可经 keywords 列命中（FTS 同步生效）"
    )
    # ⑤ state 迁移 + resolved_at + manual_tags 审计轨迹 + outbox 事件
    flag = backend.get_quality_flag(flag_id)
    assert flag["state"] == "resolved" and flag["resolved_at"] is not None
    assert "纳税信用等级" in (flag["manual_tags"] or "")
    events = conn.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'quality_flag.patch'"
    ).fetchone()[0]
    assert events >= 1


def test_fts_04_rest_patch_permissions_and_validation(app_env) -> None:
    """PATCH 面权限与校验：非 owner 非 org_admin 403；跨 org 404；空体 400。"""
    client = app_env["client"]
    backend = app_env["app"].state.service.backend
    conn = app_env["conn"]

    seed_document(conn, doc_id="d_kw4", dataset_id="ds:vat_lib", owner_user_id="u_full")
    seed_doc_dims(conn, "d_kw4", {"region": ["CN"]})
    chunk_id = insert_chunk(conn, doc_id="d_kw4", seq=1, content="权限样例块")
    conn.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_kw4'")
    conn.commit()
    flag_id = backend.insert_quality_flag(
        chunk_id=chunk_id, doc_id="d_kw4", reason="low_idf", detail_json="{}"
    )

    owner_h = {"Authorization": f"Bearer {app_env['static']['u_full']}", "X-Org-Id": "org:tax"}
    cn_h = {"Authorization": f"Bearer {app_env['static']['u_cn']}", "X-Org-Id": "org:tax"}

    # 空 patch 体 → 400
    resp = client.patch(f"/api/quality-flags/{flag_id}", json={}, headers=owner_h)
    assert resp.status_code == 400
    # 空白 keywords → 400
    resp = client.patch(
        f"/api/quality-flags/{flag_id}", json={"keywords": "  "}, headers=owner_h
    )
    assert resp.status_code == 400
    # 非 owner（u_cn 无 org_admin）→ 403
    resp = client.patch(
        f"/api/quality-flags/{flag_id}", json={"state": "ignored"}, headers=cn_h
    )
    assert resp.status_code == 403
    # 不存在 → 404
    resp = client.patch(
        "/api/quality-flags/qfl_nonexistent", json={"state": "ignored"}, headers=owner_h
    )
    assert resp.status_code == 404


def test_fts_04_rest_report_endpoint_filters_neighbors(app_env) -> None:
    """GET /api/orgs/{org}/documents/{id}/quality：近邻展示过 ACL（REST 面——
    TC-QUAL-05 端点形态）；u_cn 不见 OS-only 近邻。"""
    client = app_env["client"]
    service = app_env["app"].state.service
    backend, conn = service.backend, app_env["conn"]

    seed_document(conn, doc_id="d_rp_cn", dataset_id="ds:vat_lib", owner_user_id="u_full")
    seed_doc_dims(conn, "d_rp_cn", {"region": ["CN"]})
    seed_document(conn, doc_id="d_rp_os", dataset_id="ds:vat_lib", owner_user_id="u_full")
    seed_doc_dims(conn, "d_rp_os", {"region": ["OS"]})
    cn_chunk = insert_chunk(conn, doc_id="d_rp_cn", seq=1, content="报告近邻样例CN")
    os_chunk = insert_chunk(conn, doc_id="d_rp_os", seq=1, content="报告近邻样例OS")
    for doc in ("d_rp_cn", "d_rp_os"):
        conn.execute(f"UPDATE documents SET active_version = 1 WHERE id = '{doc}'")
    conn.commit()
    # detail 近邻含 OS-only 块（检测口径——组织内近邻）
    detail = (
        '{"mean_sim": 0.99, "neighbors": ['
        '{"rid": %d, "chunk_id": "%s", "doc_id": "d_rp_os", "sim": 0.99},'
        '{"rid": %d, "chunk_id": "%s", "doc_id": "d_rp_cn", "sim": 0.98}]}'
        % (
            conn.execute("SELECT rid FROM chunks WHERE id = ?", (os_chunk,)).fetchone()[0],
            os_chunk,
            conn.execute("SELECT rid FROM chunks WHERE id = ?", (cn_chunk,)).fetchone()[0],
            cn_chunk,
        )
    )
    backend.insert_quality_flag(
        chunk_id=cn_chunk, doc_id="d_rp_cn", reason="vector_crowding", detail_json=detail
    )

    cn_h = {"Authorization": f"Bearer {app_env['static']['u_cn']}"}
    resp = client.get("/api/orgs/org:tax/documents/d_rp_cn/quality", headers=cn_h)
    assert resp.status_code == 200, resp.text
    report = resp.json()
    neighbors = report["flags"][0]["neighbors"]
    assert {n["doc_id"] for n in neighbors} == {"d_rp_cn"}, (
        "u_cn 报告近邻须过 ACL——OS-only 块不出现（T18）"
    )
    assert neighbors[0]["snippet"], "可见近邻携带内容"
