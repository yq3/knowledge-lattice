"""m2-3 管理面：嵌入覆盖率面板 + 重索引/重嵌入投递 + stats（B4）+ 取消联动。

- **TC-EMB-06**（TEST-CASES L220，API 面）：触发手动重索引 → 投递 `reembed`
  任务（v1.4 独立任务类型——方案二蓝绿执行体 m2-1 预留分发位，本段接 API 面
  与任务行/payload 契约）；
- 覆盖率口径（RUNBOOK §1 闭合 SQL）：分子/分母都限**在用块**（tombstone=0 且
  version=active_version）——tombstone/旧版本块不计入分母；
- GET stats（B4）：maintenance stats 新键 audit_outbox_trimmed 同步运维面板；
- 任务取消 API 端到端复引（触发→取消语义——TC-TASK-03 已全覆盖，本组补
  reindex/reembed 任务行的取消同语义）。

双后端参数化（[sqlite]/[pg]）；REST 端点用例为 sqlite（app_env 惯例）。
"""

from __future__ import annotations

import json

import pytest

from conftest import ORG


# ============ 覆盖率口径（backend 级——双后端） ============


def test_embedding_coverage_active_only_denominator(matrix) -> None:
    """分母=在用块（tombstone=0 且 version=active_version）——tombstone 块与
    pending 版本块不计；分子=有当前标签 cv 行的在用块。"""
    backend = matrix.make_backend()
    label = "fake-embed:8"
    # matrix 5 篇文档各 1 chunk v1 在用；给 d_cn/d_multi 的块插当前标签向量
    rids = [
        matrix.execute("SELECT rid FROM chunks WHERE doc_id = ?", (d,)).fetchone()[0]
        for d in ("d_cn", "d_multi")
    ]
    for rid in rids:
        matrix.insert_vector(rid, label, [0.1] * 8)
    coverage = backend.embedding_coverage(ORG, label)
    assert coverage, "组织内知识库应列出"
    by_id = {c["dataset_id"]: c for c in coverage}
    ds = by_id["ds:vat_lib"]
    assert ds["total"] == 5  # 5 篇在用文档各 1 块
    assert ds["done"] == 2

    # tombstone 块不计分母：造 d_cn 的 tombstone 块（v2 旧块形态）
    matrix.execute(
        "INSERT INTO chunks(id, doc_id, seq, version, content, tombstone)"
        " VALUES('chk:tomb', 'd_cn', 99, 2, 'x', 1)"
    )
    coverage2 = backend.embedding_coverage(ORG, label)
    assert {c["dataset_id"]: c for c in coverage2}["ds:vat_lib"]["total"] == 5

    # pending 版本块不计（active_version=1、新块 version=2 且 tombstone=0）
    matrix.execute(
        "INSERT INTO chunks(id, doc_id, seq, version, content, tombstone)"
        " VALUES('chk:pend', 'd_cn', 98, 2, 'y', 0)"
    )
    coverage3 = backend.embedding_coverage(ORG, label)
    assert {c["dataset_id"]: c for c in coverage3}["ds:vat_lib"]["total"] == 5

    # 旧标签向量不计分子（换模型蓝绿口径——非当前标签视同未嵌入）
    rid_empty = matrix.execute(
        "SELECT rid FROM chunks WHERE doc_id = 'd_os'"
    ).fetchone()[0]
    matrix.insert_vector(rid_empty, "old-model:8", [0.2] * 8)
    coverage4 = backend.embedding_coverage(ORG, label)
    assert {c["dataset_id"]: c for c in coverage4}["ds:vat_lib"]["done"] == 2


# ============ REST 端点（sqlite——app_env） ============


@pytest.fixture()
def _mgmt_env(app_env):
    """app_env + admin_tax + 一篇已摄取文档（u_full owner——含当前标签向量）。"""
    from helpers import seed_membership, seed_user
    from knowledge_lattice.domain.auth import hash_token

    conn = app_env["conn"]
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = 'admin_tax'",
        (hash_token("dev-static-admin-tax"),),
    )
    conn.commit()
    client = app_env["client"]
    resp = client.post(
        f"/api/orgs/{ORG}/documents",
        headers={"Authorization": f"Bearer {app_env['static']['u_full']}"},
        files={"file": ("cov.html", b"<html><body>coverage sample</body></html>",
                        "text/html")},
        data={"dataset": "ds:vat_lib", "dims": '{"region": ["CN"]}', "title": "cov"},
    )
    assert resp.status_code == 202
    doc_id = resp.json()["doc_id"]
    ingest_task = resp.json()["task_id"]
    # inline worker 消化（BackgroundTasks 在响应后同步跑——kick 同步认领）
    return {
        **app_env,
        "admin": {"Authorization": "Bearer dev-static-admin-tax"},
        "member": {"Authorization": f"Bearer {app_env['static']['u_full']}"},
        "doc_id": doc_id,
        "ingest_task": ingest_task,
        "conn": conn,
    }


def test_api_reindex_and_reembed_task_enqueue(_mgmt_env) -> None:
    """TC-EMB-06 API 面：无 embed_model → reindex 任务（target_version=在用
    版本）；携带 embed_model → reembed 任务（payload 含 org+embed_model、
    不限单版本）；owner 与 org_admin 均可；无关成员 403；404。"""
    client, conn = _mgmt_env["client"], _mgmt_env["conn"]

    # owner（u_full）投递 reindex
    r = client.post(
        f"/api/orgs/{ORG}/documents/{_mgmt_env['doc_id']}/reindex",
        headers=_mgmt_env["member"],
    )
    assert r.status_code == 202
    body = r.json()
    assert body["type"] == "reindex" and body["embed_model"] is None
    task = conn.execute(
        "SELECT type, status, target_version, payload FROM tasks WHERE id = ?",
        (body["task_id"],),
    ).fetchone()
    assert task[0] == "reindex" and task[1] == "pending"
    assert task[2] == 1  # active_version
    assert json.loads(task[3])["org"] == ORG

    # org_admin 换模型重嵌入（reembed）
    r = client.post(
        f"/api/orgs/{ORG}/documents/{_mgmt_env['doc_id']}/reindex",
        headers=_mgmt_env["admin"], params={"embed_model": "new-model:1536"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["type"] == "reembed" and body["embed_model"] == "new-model:1536"
    task = conn.execute(
        "SELECT type, status, target_version, payload FROM tasks WHERE id = ?",
        (body["task_id"],),
    ).fetchone()
    assert task[0] == "reembed" and task[2] is None  # 全库任务不限单版本
    payload = json.loads(task[3])
    assert payload == {"org": ORG, "embed_model": "new-model:1536"}

    # 普通成员（非 owner 非 admin）→ 403
    r = client.post(
        f"/api/orgs/{ORG}/documents/{_mgmt_env['doc_id']}/reindex",
        headers={"Authorization": f"Bearer {_mgmt_env['static']['u_cn']}"},
    )
    assert r.status_code == 403
    # 不存在文档 → 404
    r = client.post(
        f"/api/orgs/{ORG}/documents/doc:nope/reindex", headers=_mgmt_env["admin"],
    )
    assert r.status_code == 404


def test_api_embedding_coverage_readonly(_mgmt_env) -> None:
    """覆盖率端点只读：embed_model=model:dim 形态、各库 done/total、reembed
    窗口进度（任务行数据源）；非 org_admin 403；GET 语义零写入。"""
    client, conn = _mgmt_env["client"], _mgmt_env["conn"]

    # 先投一个 reembed（面板 reembed 窗口数据源）
    r = client.post(
        f"/api/orgs/{ORG}/documents/{_mgmt_env['doc_id']}/reindex",
        headers=_mgmt_env["admin"], params={"embed_model": "new-model:1536"},
    )
    reembed_task_id = r.json()["task_id"]

    r = client.get(f"/api/orgs/{ORG}/embedding-coverage", headers=_mgmt_env["admin"])
    assert r.status_code == 200
    body = r.json()
    assert body["embed_model"], "当前模型标签（model:dim 形态）"
    assert isinstance(body["dim"], int)
    assert body["coverage"], "各库覆盖率在场"
    for c in body["coverage"]:
        assert 0 <= c["done"] <= c["total"]
    assert body["totals"]["total"] == sum(c["total"] for c in body["coverage"])
    assert body["totals"]["done"] == sum(c["done"] for c in body["coverage"])
    # reembed 窗口（任务行数据源 + 全局在用块进度）
    assert body["reembed"] is not None
    assert body["reembed"]["task_id"] == reembed_task_id
    assert body["reembed"]["status"] == "pending"
    assert body["reembed"]["total"] == body["totals"]["total"]

    # 非 org_admin → 403
    r = client.get(
        f"/api/orgs/{ORG}/embedding-coverage", headers=_mgmt_env["member"],
    )
    assert r.status_code == 403


def test_api_stats_maintenance_keys(_mgmt_env) -> None:
    """B4：GET stats 返回 maintenance stats（含 audit_outbox_trimmed 新键）；
    非 org_admin 403。"""
    client, conn = _mgmt_env["client"], _mgmt_env["conn"]
    # 造最近一次 maintenance.run stats（outbox 数据源）
    stats = {
        "credentials_purged": 0, "memberships_purged": 0, "tombstones_purged": 0,
        "task_rows_trimmed": 0, "audit_shipped": {"shipped": 0},
        "audit_months_sealed": {"sealed": []}, "audit_months_pruned": {"pruned": []},
        "backup_snapshot": None, "audit_outbox_trimmed": 3,
    }
    conn.execute(
        "INSERT INTO audit_outbox(id, event_type, payload_json) VALUES"
        " ('evt-maint-1', 'maintenance.run', ?)",
        (json.dumps({"task_id": "t", "stats": stats}),),
    )
    conn.commit()

    r = client.get(f"/api/orgs/{ORG}/stats", headers=_mgmt_env["admin"])
    assert r.status_code == 200
    body = r.json()
    assert body["maintenance"]["audit_outbox_trimmed"] == 3, "B4 新键同步面板"
    assert "audit_shipped" in body["maintenance"]

    r = client.get(f"/api/orgs/{ORG}/stats", headers=_mgmt_env["member"])
    assert r.status_code == 403


def test_api_cancel_reindex_task(_mgmt_env) -> None:
    """任务取消联动（A5 复引）：投递 reindex → POST cancel → 任务 failed+
    'cancelled:'（m2-1 取消机制在管理面任务类型上同语义——reindex 未被
    runner 认领仍处 pending，取消即吸收态）。"""
    client = _mgmt_env["client"]
    r = client.post(
        f"/api/orgs/{ORG}/documents/{_mgmt_env['doc_id']}/reindex",
        headers=_mgmt_env["admin"],
    )
    task_id = r.json()["task_id"]
    r = client.post(
        f"/api/orgs/{ORG}/tasks/{task_id}/cancel", headers=_mgmt_env["admin"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["cancelled"] is True
    assert body["status"] == "failed" and body["error"].startswith("cancelled:")
    # 幂等不复活
    r = client.post(
        f"/api/orgs/{ORG}/tasks/{task_id}/cancel", headers=_mgmt_env["admin"],
    )
    assert r.json()["status"] == "failed"
