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
def _quiet_inline(app_env):
    """P3-6①/R2：停 inline 兜底循环线程——直插 pending 任务构造「未执行
    窗口」的用例隔离（防循环 poll 周期抢走任务造负载下 flake；kick 同步
    消化通道不受影响——本 fixture 只用于不依赖兜底的直插用例）。"""
    handle = getattr(app_env["app"].state, "worker", None)
    if handle is not None and hasattr(handle, "_stop"):
        handle._stop.set()
        handle._wake.set()
    yield app_env


def _setup_mgmt(app_env):
    """管理面造数（_mgmt_env / _mgmt_env_quiet 共用）：admin_tax + 一篇已
    摄取文档（u_full owner——含当前标签向量）。"""
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


@pytest.fixture()
def _mgmt_env(app_env):
    """管理面环境（兜底循环在线——投递/轮询类用例）。"""
    return _setup_mgmt(app_env)


@pytest.fixture()
def _mgmt_env_quiet(_quiet_inline):
    """管理面环境 + 兜底循环已停（P3-6①/R2——直插 pending 任务的
    「未执行窗口」用例隔离，防循环抢任务 flake）。"""
    return _setup_mgmt(_quiet_inline)


def test_api_reindex_and_reembed_task_enqueue(_mgmt_env) -> None:
    """TC-EMB-06 API 面（m2-6 执行体接管后）：无 embed_model → reindex 任务
    （target_version=在用版本；owner/org_admin 可投）；携带 embed_model →
    reembed 任务（payload 含 org+embed_model、不限单版本；**sysadmin 专属**
    ——N-1 裁定选 a/R2 P2-2：换模型为系统级全库迁移，org_admin/owner 均 403）。
    **m2-6 起 inline worker 同步认领执行**——投递即执行到终态（本用例事实
    升级为 A1/A2 的 API 级集成：reindex done 重索引、reembed done 蓝绿切换
    断言）。"""
    client, conn = _mgmt_env["client"], _mgmt_env["conn"]
    sysadmin = {"Authorization": f"Bearer {_mgmt_env['static']['sysadmin']}"}

    def _task_row(task_id: str):
        return conn.execute(
            "SELECT type, status, target_version, payload FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    def _await_terminal(task_id: str, *, timeout_s: float = 15.0) -> tuple:
        """有界轮询终态（inline 双通道竞态的鲁棒收口：reembed/reindex 可能被
        兜底循环线程抢先认领——kick 不保证恒为先；-O 门禁实测暴露）。"""
        import time as _time

        deadline = _time.monotonic() + timeout_s
        row = _task_row(task_id)
        while row[1] not in ("done", "failed") and _time.monotonic() < deadline:
            _time.sleep(0.05)
            row = _task_row(task_id)
        return row

    # owner（u_full）投递 reindex → 同步执行 done（重索引全链）
    r = client.post(
        f"/api/orgs/{ORG}/documents/{_mgmt_env['doc_id']}/reindex",
        headers=_mgmt_env["member"],
    )
    assert r.status_code == 202
    body = r.json()
    assert body["type"] == "reindex" and body["embed_model"] is None
    task = _await_terminal(body["task_id"])
    assert task[0] == "reindex" and task[1] == "done", (
        f"reindex 被 inline worker 同步执行到终态（m2-6 执行体）: {task[1]}"
    )
    assert task[2] == 1  # active_version
    assert json.loads(task[3])["org"] == ORG

    # 换模型重嵌入：sysadmin 专属（N-1 裁定）——owner 与 org_admin 均 403
    for headers, who in ((_mgmt_env["member"], "owner"),
                         (_mgmt_env["admin"], "org_admin")):
        r = client.post(
            f"/api/orgs/{ORG}/documents/{_mgmt_env['doc_id']}/reindex",
            headers=headers, params={"embed_model": "new-model:1536"},
        )
        assert r.status_code == 403, f"{who} 不得触发全库 reembed（sysadmin 专属）"

    r = client.post(
        f"/api/orgs/{ORG}/documents/{_mgmt_env['doc_id']}/reindex",
        headers=sysadmin, params={"embed_model": "new-model:1536"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["type"] == "reembed" and body["embed_model"] == "new-model:1536"
    task = _await_terminal(body["task_id"])
    assert task[0] == "reembed" and task[2] is None  # 全库任务不限单版本
    payload = json.loads(task[3])
    assert payload == {"org": ORG, "embed_model": "new-model:1536"}
    assert task[1] == "done", (
        f"reembed 蓝绿执行体同步完成（TC-EMB-06 四步）: {task[1]}"
    )
    # 切换终态：embedder 标签（面板 label 源）已切新标签；全库单标签一致
    assert _mgmt_env["embedder"].model_label == "new-model:1536"
    labels = {
        row[0] for row in conn.execute(
            "SELECT DISTINCT cv.embed_model FROM chunk_vectors cv"
            " JOIN chunks c ON c.rid = cv.rid"
            " JOIN documents d ON d.id = c.doc_id WHERE d.org_id = ?", (ORG,),
        )
    }
    assert labels == {"new-model:1536"}, f"旧标签已清理（单标签一致）: {labels}"

    # P2-1/R2：覆盖率面板 dim 经 effective_settings 从 embedder 派生——切换
    # 后与 embedder 一致（settings 容器滞后的 inline 形态下面板不失真）
    r = client.get(f"/api/orgs/{ORG}/embedding-coverage",
                   headers=_mgmt_env["admin"])
    assert r.status_code == 200
    assert r.json()["embed_model"] == "new-model:1536"
    assert r.json()["dim"] == 1536, "dim 从当前生效标签派生（非旧 settings）"

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


def test_api_embedding_coverage_readonly(_mgmt_env_quiet) -> None:
    """覆盖率端点只读：embed_model=model:dim 形态、各库 done/total；reembed
    窗口进度按**任务目标标签**（payload.embed_model——R2 P2-3）而非当前标签
    ——蓝绿窗口旧标签覆盖率不冒充进度；非 org_admin 403。

    m2-6 注记：经端点投递的 reembed 会被 inline worker 同步执行完——「未
    起步 done=0」窗口改用**直插任务行**（不经端点 kick）构造（执行体存在
    前的历史形态语义保持可测）。"""
    client, conn = _mgmt_env_quiet["client"], _mgmt_env_quiet["conn"]

    # 直插 pending reembed（面板 reembed 窗口数据源——目标标签 new-model:1536；
    # doc_id 关联文档——list_tasks 经 documents JOIN 组织过滤）
    reembed_task_id = conn.execute(
        "INSERT INTO tasks(id, doc_id, type, status, payload)"
        " VALUES('tsk-cov-reembed', ?, 'reembed', 'pending', ?)"
        " RETURNING id",
        (_mgmt_env_quiet["doc_id"],
         json.dumps({"org": ORG, "embed_model": "new-model:1536"})),
    ).fetchone()[0]

    # 造目标标签部分向量（1 块）——reembed 进度=目标标签覆盖率
    rid = conn.execute(
        "SELECT rid FROM chunks WHERE doc_id = ?", (_mgmt_env_quiet["doc_id"],)
    ).fetchone()[0]
    from knowledge_lattice.store.sqlite.vec import pack_f32

    conn.execute(
        "INSERT INTO chunk_vectors(rid, embed_model, embedding)"
        " VALUES(?, 'new-model:1536', ?)",
        (rid, pack_f32([0.0] * 8)),
    )
    conn.commit()

    r = client.get(f"/api/orgs/{ORG}/embedding-coverage", headers=_mgmt_env_quiet["admin"])
    assert r.status_code == 200
    body = r.json()
    assert body["embed_model"], "当前模型标签（model:dim 形态）"
    assert isinstance(body["dim"], int)
    assert body["coverage"], "各库覆盖率在场"
    for c in body["coverage"]:
        assert 0 <= c["done"] <= c["total"]
    assert body["totals"]["total"] == sum(c["total"] for c in body["coverage"])
    assert body["totals"]["done"] == sum(c["done"] for c in body["coverage"])
    # reembed 窗口（R2 P2-3）：按任务 payload.embed_model 目标标签算进度
    assert body["reembed"] is not None
    assert body["reembed"]["task_id"] == reembed_task_id
    assert body["reembed"]["target_model"] == "new-model:1536"
    assert body["reembed"]["status"] == "pending"
    assert body["reembed"]["total"] >= 1
    assert body["reembed"]["done"] == 1, "目标标签已有向量块计入 reembed 进度"
    # 无目标标签向量时（执行体未认领起步）done=0——不冒充当前标签覆盖率
    conn.execute("DELETE FROM tasks WHERE id = ?", (reembed_task_id,))
    conn.execute(
        "INSERT INTO tasks(id, doc_id, type, status, payload)"
        " VALUES('tsk-cov-reembed2', ?, 'reembed', 'pending', ?)",
        (_mgmt_env_quiet["doc_id"], json.dumps({"org": ORG, "embed_model": "green:1536"})),
    )
    conn.commit()
    r = client.get(f"/api/orgs/{ORG}/embedding-coverage", headers=_mgmt_env_quiet["admin"])
    body = r.json()
    assert body["reembed"]["task_id"] == "tsk-cov-reembed2"  # 唯一 reembed 任务
    assert body["reembed"]["done"] == 0, "目标标签零向量 → done=0（非当前标签覆盖率）"

    # 非 org_admin → 403
    r = client.get(
        f"/api/orgs/{ORG}/embedding-coverage", headers=_mgmt_env_quiet["member"],
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


def test_api_cancel_reindex_task(_mgmt_env_quiet) -> None:
    """任务取消联动（A5 复引）：投递 reindex → POST cancel → 任务 failed+
    'cancelled:'（m2-1 取消机制在管理面任务类型上同语义）。

    m2-6 注记：经端点投递的 reindex 会被 inline worker 同步执行完（done）
    ——取消语义的可测窗口改用**直插 pending 任务行**（不经端点 kick）构造；
    取消对非终态任务的吸收态语义不变。"""
    client, conn = _mgmt_env_quiet["client"], _mgmt_env_quiet["conn"]
    conn.execute(
        "INSERT INTO tasks(id, doc_id, type, status, target_version, payload)"
        " VALUES('tsk-cancel-reindex', ?, 'reindex', 'pending', 1, ?)",
        (_mgmt_env_quiet["doc_id"], json.dumps({"org": ORG})),
    )
    conn.commit()
    task_id = "tsk-cancel-reindex"
    r = client.post(
        f"/api/orgs/{ORG}/tasks/{task_id}/cancel", headers=_mgmt_env_quiet["admin"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["cancelled"] is True
    assert body["status"] == "failed" and body["error"].startswith("cancelled:")
    # 幂等不复活
    r = client.post(
        f"/api/orgs/{ORG}/tasks/{task_id}/cancel", headers=_mgmt_env_quiet["admin"],
    )
    assert r.json()["status"] == "failed"


def test_api_reindex_rejected_while_pending(_mgmt_env) -> None:
    """P3-5② 投递面防线：目标文档存在进行中 pending 版本 → reindex 409
    （切换事务与重置互相破坏；执行体同语义 fail-closed——见 test_wk_rebuild）。"""
    client, conn = _mgmt_env["client"], _mgmt_env["conn"]
    conn.execute(
        "UPDATE documents SET pending_version = 2, pending_status = 'parsing'"
        " WHERE id = ?", (_mgmt_env["doc_id"],),
    )
    conn.commit()
    r = client.post(
        f"/api/orgs/{ORG}/documents/{_mgmt_env['doc_id']}/reindex",
        headers=_mgmt_env["admin"],
    )
    assert r.status_code == 409
    assert "pending" in r.json()["detail"]
    # pending 终态（failed）后放行
    conn.execute(
        "UPDATE documents SET pending_status = 'failed'"
        " WHERE id = ?", (_mgmt_env["doc_id"],),
    )
    conn.commit()
    r = client.post(
        f"/api/orgs/{ORG}/documents/{_mgmt_env['doc_id']}/reindex",
        headers=_mgmt_env["admin"],
    )
    assert r.status_code == 202
