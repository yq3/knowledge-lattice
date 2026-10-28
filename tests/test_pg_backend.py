"""PgBackend 六域覆盖（M0b-1 PG spike——协议种子范围内）。

- Acl 域：双后端一致性在参数化矩阵组（T1~T5/T20/T22/TC-ACL-01~07）已全覆盖，
  此处补 read_membership 的 now=None 库时钟分支；
- Ingest 域：insert（chunks+阶段状态+D20 首次切换+pending_dims 解析）/ 标签钉死
  与待嵌清单 / write_embeddings（浮点向量 → pgvector 文本序列化收口方言侧——
  P2-3/D24）+ `<=>` 距离精确扫描实证（G-6 起步口径）/ 删除计数；
- Admin 域：任务状态机 / 文档行与状态推进 / 指纹基线 / 维度取值与库只读 /
  静态 token 与用户态；
- Audit 域：append_outbox；
- Search 域：种子方法签名在场（P3-17）且完整管线显式 NotImplementedError
  （M0b-2/M1 指针——不静默假实现）；
- 协议一致性：PgBackend 满足 StorageBackend（runtime_checkable——方法面齐备）；
  SemanticBackend 种子签名（P3-17）在 store/backend.py 定义面齐备。
"""

from __future__ import annotations

import json

import pytest

from helpers import (
    NOW_TS,
    seed_dataset,
    seed_dim_value,
    seed_dimension,
    seed_org,
    seed_user,
)


@pytest.fixture()
def pg_env(pg_db):
    """pg 臂最小摄取环境：org:tax + region 维度（CN/OS）+ u1。"""
    seed_org(pg_db)
    seed_dataset(pg_db)
    seed_dimension(pg_db, "org:tax", "region")
    seed_dim_value(pg_db, "dim:org:tax:region", "CN")
    seed_dim_value(pg_db, "dim:org:tax:region", "OS")
    seed_user(pg_db, "u1")
    pg_db.execute(
        "INSERT INTO user_org_memberships(user_id, org_id, role) VALUES('u1', 'org:tax', 'member')"
    )
    return pg_db


def _chunk(chunk_id: str, seq: int, content: str = "一般纳税人销售自产货物。") -> dict:
    return {
        "id": chunk_id,
        "seq": seq,
        "content": content,
        "title_seg": "增值税 指南",
        "content_seg": "一般纳税人 销售",
        "token_count": 8,
    }


# ============ Acl 域（now=None 库时钟分支） ============


def test_read_membership_db_clock_branch(pg_env) -> None:
    backend = pg_env.make_backend()
    assert backend.read_membership("u1", "org:tax") is not None  # 有效成员（库时钟）
    assert backend.read_membership("ghost", "org:tax") is None


# ============ Ingest 域 ============


def test_insert_first_upload_switch_and_dims_resolution(pg_env) -> None:
    """insert：chunks 落库（rid identity 自增）+ pending→active D20 首次切换 +
    pending_dims_json 同事务解析入 document_dimensions（解析失败回滚——P3-7 同源）。"""
    backend = pg_env.make_backend()
    backend.create_document(
        doc_id="doc:1", org_id="org:tax", dataset_id="ds:vat", title="VAT 指南",
        source_uri="user:u1", content_hash="sha256:x", mime_type="application/pdf",
        parser="docling", owner_user_id="u1", raw_object_key="objects/x",
        pending_dims_json=json.dumps({"region": ["CN"]}),
    )
    backend.insert("doc:1", 1, [_chunk("chk:1:1", 1), _chunk("chk:1:2", 2)])

    doc = backend.get_document("doc:1")
    assert doc["active_version"] == 1
    assert doc["active_status"] == "searchable_lexical"
    assert doc["pending_version"] is None
    assert doc["page_count"] == 1  # {None} 去重后的页数
    assert pg_env.execute("SELECT count(*) FROM chunks WHERE doc_id = 'doc:1'").fetchone()[0] == 2
    rids = pg_env.execute(
        "SELECT rid FROM chunks WHERE doc_id = 'doc:1' ORDER BY rid"
    ).fetchall()
    assert rids[0][0] < rids[1][0]  # identity 自增（VACUUM 后稳定——sqlite rid 同语义）
    dims = pg_env.execute(
        "SELECT dimension_id, value_id FROM document_dimensions WHERE doc_id = 'doc:1'"
    ).fetchall()
    assert dims == [("dim:org:tax:region", "val:dim:org:tax:region:CN")]

    # 幂等：同 (doc_id, version) 先删后插——块数不翻倍
    backend.insert("doc:1", 1, [_chunk("chk:1:1", 1)])
    assert pg_env.execute("SELECT count(*) FROM chunks WHERE doc_id = 'doc:1'").fetchone()[0] == 1


def test_pending_dims_mismatch_rolls_back(pg_env) -> None:
    """P3-7 同源：pending_dims 含已停用取值 → 解析计数不符 raise → 整事务回滚
    （pending_dims_json 保留供重试）。"""
    backend = pg_env.make_backend()
    backend.create_document(
        doc_id="doc:2", org_id="org:tax", dataset_id="ds:vat", title="t",
        source_uri="user:u1", content_hash="sha256:y", mime_type="application/pdf",
        parser="docling", owner_user_id="u1", raw_object_key="objects/y",
        pending_dims_json=json.dumps({"region": ["GONE"]}),
    )
    with pytest.raises(RuntimeError, match="pending_dims resolution mismatch"):
        backend.insert("doc:2", 1, [_chunk("chk:2:1", 1)])
    # 回滚：无块、无 pending_status 推进、pending_dims_json 保留
    assert pg_env.execute("SELECT count(*) FROM chunks WHERE doc_id = 'doc:2'").fetchone()[0] == 0
    doc = backend.get_document("doc:2")
    assert doc["pending_status"] == "parsing"
    assert doc["pending_dims_json"] is not None


def test_embedding_batch_roundtrip_and_exact_scan_distance(pg_env) -> None:
    """标签钉死 → 待嵌清单 → write_embeddings（pgvector 文本序列化收口方言侧，
    v1.1 落 chunk_vectors）→ `<=>` 余弦距离精确扫描实证（同向量距离 0、正交
    距离 1）；防护：tombstone/(rid,label) 冲突/标签不符零触碰。"""
    backend = pg_env.make_backend()
    backend.create_document(
        doc_id="doc:3", org_id="org:tax", dataset_id="ds:vat", title="t",
        source_uri="user:u1", content_hash="sha256:z", mime_type="text/plain",
        parser="docling", owner_user_id="u1", raw_object_key="objects/z",
        pending_dims_json=None,
    )
    backend.insert("doc:3", 1, [_chunk("chk:3:1", 1), _chunk("chk:3:2", 2)])

    claimed = backend.mark_embedding_batch("doc:3", 1, "m:8")
    assert len(claimed) == 2  # 两块全部认领（P3-1：原「or」弱断言收紧）
    rids = sorted(c["rid"] for c in claimed)
    pending = backend.pending_embeddings("m:8")
    assert [p["rid"] for p in pending] == rids

    vec_a, vec_b = [1.0, 0.0], [0.0, 1.0]
    written = backend.write_embeddings("m:8", [(rids[0], vec_a), (rids[1], vec_b)])
    assert written == 2

    # 精确扫描起步（G-6）：先过滤后距离——同向量距离 0、正交距离 1
    d_self = pg_env.cosine_distance(rids[0], vec_a)
    d_cross = pg_env.cosine_distance(rids[0], vec_b)
    assert abs(d_self) < 1e-6
    assert abs(d_cross - 1.0) < 1e-6

    # 已回写块零触碰（(rid,label) PK 冲突防护）；标签不符零触碰
    assert backend.write_embeddings("m:8", [(rids[0], vec_a)]) == 0
    assert backend.write_embeddings("other:8", [(rids[0], [0.0, 0.0])]) == 0


def test_delete_by_doc_counts(pg_env) -> None:
    backend = pg_env.make_backend()
    backend.create_document(
        doc_id="doc:4", org_id="org:tax", dataset_id="ds:vat", title="t",
        source_uri="user:u1", content_hash="sha256:w", mime_type="text/plain",
        parser="docling", owner_user_id="u1", raw_object_key="objects/w",
        pending_dims_json=None,
    )
    backend.insert("doc:4", 1, [_chunk("chk:4:1", 1)])
    rid = pg_env.execute("SELECT rid FROM chunks WHERE doc_id = 'doc:4'").fetchone()[0]
    assert backend.delete_by_doc("doc:4", 1) == 1
    assert backend.delete_by_doc("doc:4", 1) == 0
    assert pg_env.execute("SELECT count(*) FROM chunks WHERE rid = ?", (rid,)).fetchone()[0] == 0


# ============ Admin 域 ============


def test_task_state_machine(pg_env) -> None:
    backend = pg_env.make_backend()
    backend.create_document(
        doc_id="doc:5", org_id="org:tax", dataset_id="ds:vat", title="t",
        source_uri="user:u1", content_hash="sha256:v", mime_type="text/plain",
        parser="docling", owner_user_id="u1", raw_object_key="objects/v",
        pending_dims_json=None,
    )
    task_id = backend.create_task("doc:5")
    assert backend.get_task(task_id)["status"] == "pending"
    # M2.1 口径：attempts 随 claim 认领递增（一次认领 = 一次执行尝试）
    claimed = backend.claim_next_task("wk-1", lease_s=60.0)
    assert claimed is not None and claimed["id"] == task_id
    assert claimed["status"] == "leased" and claimed["attempts"] == 1
    backend.update_task(task_id, status="running")
    assert backend.get_task(task_id)["attempts"] == 1  # running 不重复计
    backend.update_task(task_id, status="done")
    tasks = backend.list_tasks("org:tax", doc_id="doc:5")
    assert [t["status"] for t in tasks] == ["done"]
    assert backend.list_tasks("org:gl") == []  # 组织隔离（第一条件 org_id）


def test_document_status_and_fingerprint(pg_env) -> None:
    backend = pg_env.make_backend()
    backend.create_document(
        doc_id="doc:6", org_id="org:tax", dataset_id="ds:vat", title="t",
        source_uri="user:u1", content_hash="sha256:u", mime_type="text/plain",
        parser="docling", owner_user_id="u1", raw_object_key="objects/u",
        pending_dims_json=None,
    )
    backend.set_doc_pending_status("doc:6", 1, "chunked")
    assert backend.get_document("doc:6")["pending_status"] == "chunked"
    # insert 完成 D20 首次切换（active_version 0→1）后，active_* 才可推进
    backend.insert("doc:6", 1, [_chunk("chk:6:1", 1)])
    backend.set_doc_active_status("doc:6", 1, "searchable_full")
    doc = backend.get_document("doc:6")
    assert doc["active_status"] == "searchable_full" and doc["active_error"] is None
    backend.set_doc_active_error("doc:6", 1, "embed failed")
    assert backend.get_document("doc:6")["active_error"] == "embed failed"

    assert backend.read_fingerprint("m:8") is None  # 首部署无基线
    backend.save_fingerprint("m:8", '{"sentinels": []}')
    assert backend.read_fingerprint("m:8") == '{"sentinels": []}'
    backend.save_fingerprint("m:8", '{"sentinels": [2]}')  # UPSERT
    assert backend.read_fingerprint("m:8") == '{"sentinels": [2]}'


def test_list_dimensions_datasets_and_user_auth(pg_env) -> None:
    from knowledge_lattice.domain.auth import hash_token

    backend = pg_env.make_backend()
    dims = backend.list_dimensions("org:tax")
    assert [d["key"] for d in dims] == ["region"]
    assert [v["value"] for v in dims[0]["values"]] == ["CN", "OS"]
    assert backend.list_datasets("org:tax")[0]["id"] == "ds:vat"

    pg_env.execute("UPDATE users SET token_hash = ? WHERE id = 'u1'", (hash_token("tok-u1"),))
    assert backend.find_user_by_token_hash(hash_token("tok-u1")) == {
        "id": "u1", "is_system_admin": False,
    }
    assert backend.find_user_by_token_hash("nope") is None
    assert backend.get_user_auth("u1") == {"is_system_admin": False, "disabled_at": None}
    assert backend.get_user_auth("ghost") is None


# ============ Audit 域 ============


def test_append_outbox(pg_env) -> None:
    backend = pg_env.make_backend()
    backend.append_outbox("grant", '{"user": "u1"}')
    rows = pg_env.execute(
        "SELECT event_type, payload_json, shipped_at FROM audit_outbox"
    ).fetchall()
    assert rows == [("grant", '{"user": "u1"}', None)]


# ============ Search 域种子签名（P3-17）与 M0b-2/M1 指针 ============


def test_search_seed_methods_present_and_explicitly_deferred(pg_env) -> None:
    """Search 方法面齐备：recall_fts/recall_vec 已随 M1-1 实装（此前显式
    NotImplementedError 的延迟边界兑现——design §8 M1.1 PG 追平全矩阵）；
    实体路/关系展开仍显式延迟（M2-S3/M2-S1——D23）。"""
    backend = pg_env.make_backend()
    for name in ("recall_fts", "recall_vec", "recall_by_entities", "expand_relations",
                 "visible_chunk_ids", "rids_without_vector"):
        assert callable(getattr(backend, name))
    with pytest.raises(NotImplementedError, match="M2-S3"):
        backend.recall_by_entities([1], None)
    with pytest.raises(NotImplementedError, match="M2-S1"):
        backend.expand_relations("org:tax", [1], ["uses"])


def test_pg_backend_satisfies_storage_backend_protocol(pg_env) -> None:
    """PgBackend 满足 StorageBackend 组合协议（runtime_checkable——六域方法面齐备）。"""
    from knowledge_lattice.store.backend import StorageBackend

    assert isinstance(pg_env.make_backend(), StorageBackend)


def test_semantic_backend_seed_signatures_defined() -> None:
    """P3-17：SemanticBackend 空 Protocol 补种子方法签名（实现随 M2-S1）。"""
    from knowledge_lattice.store.backend import SemanticBackend

    for name in (
        "upsert_entities_batch", "advance_status", "save_build", "load_build", "export_l0",
    ):
        assert hasattr(SemanticBackend, name)


def test_vec_render_vec_recall_select_shape(pg_env) -> None:
    """向量路渲染形态（v1.1 谓词迁 chunk_vectors——拍板 2）：visible_docs CTE
    （MATERIALIZED）+ `JOIN cv ON cv.rid = c.rid AND cv.embed_model` 谓词 +
    `<=>` 距离（cv.embedding）+ 先过滤后距离（ORDER BY dist LIMIT）+ 查询向量
    经绑定参数与 ::vector 转型；无 c.embedding/c.embed_model 残留引用。"""
    from knowledge_lattice.core.docs.acl import compile_acl
    from knowledge_lattice.store.postgres.acl_render import render_vec_recall_select
    from knowledge_lattice.store.postgres.vec import format_vector

    backend = pg_env.make_backend()
    plan = compile_acl(backend, "u1", "org:tax", now=NOW_TS, embed_model="m:8")
    sql, params = render_vec_recall_select(plan, format_vector([1.0, 0.0]), top_k=10)
    assert sql.startswith("WITH visible_docs(doc_id) AS MATERIALIZED (")
    assert "cv.embedding <=> %(q_vec)s::vector AS dist" in sql
    assert "JOIN chunk_vectors AS cv ON cv.rid = c.rid AND cv.embed_model = %(current_model)s" in sql
    assert "c.embedding" not in sql and "c.embed_model" not in sql  # 谓词已迁 cv
    assert sql.rstrip().endswith("ORDER BY dist LIMIT %(top_k)s")
    assert params["q_vec"] == "[1.0,0.0]"
    assert params["current_model"] == "m:8"
    # 向量路前置：Plan 缺 embed_model → ValueError（build_vec_parts——TC-EMB-02）
    plan_base = compile_acl(backend, "u1", "org:tax", now=NOW_TS)
    with pytest.raises(ValueError, match="embed_model"):
        render_vec_recall_select(plan_base, "[1.0]", top_k=10)
