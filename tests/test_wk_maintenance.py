"""maintenance 任务族（M2.1 B 组）：三任务体 + 任务行保留策略（框架预留 type 分发位）。

- 未消费凭证回收（M1-3 实现收编进 worker——TC-CRED-05 语义随 run_maintenance 保持）；
- 过期成员物理清理（触发 cleanup 级联清授权——§5.1）；
- tombstone 90 天物理清理（tombstoned_at 时点基准〔0004〕+ chunk_vectors FK 级联）；
- maintenance 任务行保留策略（m1-3 P3-19——done/failed 按天数/条数截尾）；
- 任务体相互隔离（单个体失败不阻断其余、任务行 failed 落汇总原因）。

双后端参数化（[sqlite]/[pg]）；子进程执行形态由 test_task_04/test_e2e_03 覆盖。
"""

from __future__ import annotations

import hashlib

from fake_providers import FakeEmbedder

from knowledge_lattice.config import Settings
from knowledge_lattice.core.docs.credentials import CredentialService
from knowledge_lattice.core.docs.ingest import IngestService
from knowledge_lattice.adapters.embedder import EmbeddingGate
from knowledge_lattice.worker.maintenance import run_maintenance

PAYLOAD = ("<html><body><h1>车船税</h1><p>纯电动乘用车不属于车船税征税范围。</p></body></html>").encode()


def _mk_env(matrix, tmp_path):
    backend = matrix.make_backend()
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    objects_dir = tmp_path / "objects"
    creds = CredentialService(backend, settings, objects_dir)
    return backend, settings, creds, objects_dir


def test_maintenance_purges_expired_credentials(matrix, tmp_path) -> None:
    """凭证回收收编：run_maintenance 执行体回收过期未消费凭证（TC-CRED-05 语义）。"""
    backend, settings, creds, _ = _mk_env(matrix, tmp_path)
    upload_id = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="d.html", size=len(PAYLOAD),
        sha256=hashlib.sha256(PAYLOAD).hexdigest(), content_type="text/html",
    )["upload_id"]
    matrix.execute(
        "UPDATE uploads SET expires_at = '2020-01-01 00:00:00' WHERE id = ?",
        (upload_id,),
    )
    task_id = backend.create_task(None, task_type="maintenance")
    stats = run_maintenance(backend, creds, settings, task_id)

    assert stats["credentials_purged"] == 1
    assert backend.get_task(task_id)["status"] == "done"
    assert matrix.execute(
        "SELECT count(*) FROM uploads WHERE id = ?", (upload_id,)
    ).fetchone()[0] == 0
    # 审计：maintenance.run 事件（FR-6 治理事件）
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'maintenance.run'"
    ).fetchone()[0] >= 1


def test_maintenance_purges_expired_memberships_and_cascades(matrix, tmp_path) -> None:
    """过期成员物理清理：过期行删除 + trg_membership_delete_cleanup 级联清授权；
    有效成员不动；授权过期但成员有效的不动（两者生命周期独立——§5.1）。"""
    backend, settings, creds, _ = _mk_env(matrix, tmp_path)
    task_id = backend.create_task(None, task_type="maintenance")
    stats = run_maintenance(backend, creds, settings, task_id)

    # matrix 造数：u_expired_member（成员过期 PAST_TS）+ 其 org:tax 授权
    assert stats["memberships_purged"] == 1
    assert matrix.execute(
        "SELECT count(*) FROM user_org_memberships WHERE user_id = 'u_expired_member'"
    ).fetchone()[0] == 0  # 过期行物理清理
    assert matrix.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'u_expired_member'"
        " AND dimension_id IN (SELECT id FROM dimensions WHERE org_id = 'org:tax')"
    ).fetchone()[0] == 0  # 级联清授权（触发器）
    assert matrix.execute(
        "SELECT count(*) FROM user_org_memberships WHERE user_id = 'u_full'"
    ).fetchone()[0] == 1  # 有效成员不动
    assert matrix.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'u_expired_grant'"
    ).fetchone()[0] == 2  # 授权过期≠成员过期：授权行保留（清理只看成员关系）


def test_maintenance_purges_aged_tombstones(ver_env, tmp_path) -> None:
    """tombstone 90 天物理清理：到期旧版本块删除（含残留向量行 FK 级联）、
    近期 tombstone 与在用块不动。"""
    matrix, backend = ver_env["db"], ver_env["backend"]
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    objects_dir = tmp_path / "objects"
    creds = CredentialService(backend, settings, objects_dir)

    # v1 → full；覆盖上传 v2 → full（v1 块 tombstone，tombstoned_at=当前）
    doc_id, t1 = ver_env["service"].create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="t",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=PAYLOAD, mime_type="text/html", filename="v1.html",
    )
    ver_env["service"].run_task(t1)
    _, t2 = ver_env["service"].create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="t",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=PAYLOAD, mime_type="text/html", filename="v2.html",
        doc_id=doc_id,
    )
    ver_env["service"].run_task(t2)
    v1_rid = matrix.execute(
        "SELECT rid FROM chunks WHERE doc_id = ? AND version = 1", (doc_id,)
    ).fetchone()[0]
    # 残留向量行（v1 tombstone 块——切换事务已删其向量；手插模拟异常残留）
    matrix.insert_vector(v1_rid, "stale:8", [0.1, 0.2])
    assert matrix.execute(
        "SELECT tombstoned_at FROM chunks WHERE rid = ?", (v1_rid,)
    ).fetchone()[0] is not None  # 切换事务写 tombstoned_at（0004）

    task_id = backend.create_task(None, task_type="maintenance")
    stats = run_maintenance(backend, creds, settings, task_id)
    # tombstoned_at=当前 → 未到 90 天窗口：不删
    assert stats["tombstones_purged"] == 0
    assert matrix.execute(
        "SELECT count(*) FROM chunks WHERE rid = ?", (v1_rid,)
    ).fetchone()[0] == 1

    # 造数过期（tombstoned_at = 2020）→ 清理生效（含向量行级联）
    matrix.execute(
        "UPDATE chunks SET tombstoned_at = '2020-01-01 00:00:00' WHERE rid = ?",
        (v1_rid,),
    )
    task_id = backend.create_task(None, task_type="maintenance")
    stats = run_maintenance(backend, creds, settings, task_id)
    assert stats["tombstones_purged"] == 1
    assert matrix.execute(
        "SELECT count(*) FROM chunks WHERE rid = ?", (v1_rid,)
    ).fetchone()[0] == 0
    assert matrix.execute(
        "SELECT count(*) FROM chunk_vectors WHERE rid = ?", (v1_rid,)
    ).fetchone()[0] == 0  # FK CASCADE
    assert matrix.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 2", (doc_id,)
    ).fetchone()[0] >= 1  # 在用块不动


def test_maintenance_task_row_retention(matrix, tmp_path) -> None:
    """任务行保留策略（m1-3 P3-19）：done/failed maintenance 行按天数 + 条数截尾，
    非 maintenance 类型与进行中行不动。"""
    backend, settings, creds, _ = _mk_env(matrix, tmp_path)

    def _done_row(updated_at: str) -> str:
        tid = backend.create_task(None, task_type="maintenance")
        backend.update_task(tid, status="done")
        matrix.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?", (updated_at, tid)
        )
        return tid

    old_rows = [_done_row(f"2026-05-{d:02d} 00:00:00") for d in (10, 11, 12)]  # 超龄
    fresh_rows = [_done_row("2026-06-25 00:00:00") for _ in range(3)]          # 7 天内

    removed = backend.trim_finished_tasks(
        keep_days=7, keep_count=3, task_type="maintenance", now="2026-06-28 12:00:00"
    )
    assert removed == 3  # 天数规则清超龄；条数上限 3 内的近期行保留
    for tid in old_rows:
        assert matrix.execute(
            "SELECT count(*) FROM tasks WHERE id = ?", (tid,)
        ).fetchone()[0] == 0
    for tid in fresh_rows:
        assert matrix.execute(
            "SELECT count(*) FROM tasks WHERE id = ?", (tid,)
        ).fetchone()[0] == 1

    # 条数上限：再投 2 行近期 done（共 5）→ keep_count=3 → 截最旧 2 行
    _done_row("2026-06-26 00:00:00")
    _done_row("2026-06-27 00:00:00")
    removed = backend.trim_finished_tasks(
        keep_days=7, keep_count=3, task_type="maintenance", now="2026-06-28 12:00:00"
    )
    assert removed == 2
    assert matrix.execute(
        "SELECT count(*) FROM tasks WHERE type = 'maintenance' AND status = 'done'"
    ).fetchone()[0] == 3

    # 非 maintenance 类型不动；进行中（pending）不动（doc_id=None 无 FK 牵涉）
    ingest_task = backend.create_task(None, task_type="ingest")
    backend.update_task(ingest_task, status="done")
    removed = backend.trim_finished_tasks(
        keep_days=7, keep_count=0, task_type="maintenance", now="2026-06-28 12:00:00"
    )
    assert removed == 3  # maintenance done 清空（keep_count=0）
    assert matrix.execute(
        "SELECT count(*) FROM tasks WHERE type = 'maintenance'"
    ).fetchone()[0] == 0
    assert matrix.execute(
        "SELECT count(*) FROM tasks WHERE id = ?", (ingest_task,)
    ).fetchone()[0] == 1  # ingest 行不受 maintenance 保留策略管辖


def test_maintenance_body_isolation(matrix, tmp_path, monkeypatch) -> None:
    """任务体相互隔离：单个体失败不阻断其余——任务行 failed 落汇总原因。"""
    backend, settings, creds, _ = _mk_env(matrix, tmp_path)

    def _boom(now=None):
        raise RuntimeError("membership purge exploded")

    monkeypatch.setattr(backend, "delete_expired_memberships", _boom)
    task_id = backend.create_task(None, task_type="maintenance")
    import pytest

    with pytest.raises(RuntimeError, match="maintenance partial failure"):
        run_maintenance(backend, creds, settings, task_id)
    row = backend.get_task(task_id)
    assert row["status"] == "failed"
    assert "memberships_purged: membership purge exploded" in row["error"]
    # 其余任务体仍执行（凭证回收正常返回）
    assert "credentials_purged" not in row["error"]
