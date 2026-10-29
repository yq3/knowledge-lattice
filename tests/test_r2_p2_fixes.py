"""m2-2 R2 修复回归（Committer R1 P2×4 + 顺手项——每条「修前必败」）。

- P2-1：哈希链排序键=插入序（sqlite rowid / pg seq）——同秒并列 + id 逆序 +
  跨两轮搬运，链验证与封存末哈希按插入序自洽（修前 (created_at,id) 全序与
  插入序错位 → 断链）；
- P2-2：sqlite 搬运重试不污染 prev——崩溃窗口（月库已插、回填未做）后同月
  再入新事件，重跑 ship 链完整（偏差①补充实证）；
- P2-3：update_task(running) 终态守卫——取消不被复活（TC-TASK-03）；
- P2-4：backup 两态——真实失败落 errors 任务 failed；工具缺失 unavailable；
- P3-1/P3-2/P3-5/P3-13 顺手项回归。

双后端参数化（[sqlite]/[pg]）。
"""

from __future__ import annotations

import json
import os

import pytest

from knowledge_lattice.store.audit_chain import compute_row_hash

NOV = "2026-11-05 11:00:00"


def _verify_chain(rows: list[dict], start_prev: str | None) -> None:
    prev = start_prev
    for row in rows:
        assert row["prev_hash"] == prev, f"chain break at {row['id']}"
        assert row["row_hash"] == compute_row_hash(row, prev)
        prev = row["row_hash"]


# ============ P2-1：链序=插入序（同秒 id 逆序 + 跨两轮搬运） ============


def test_chain_same_second_id_reorder_two_ships(matrix) -> None:
    """P2-1 回归（修前必败）：同秒两行按 id 逆序落链（aaa→bbb），再入同秒
    id 更小的新行（aud_000）——插入序 aaa→bbb→000；(created_at,id) 读序
    aaa→000→bbb 与链序错位 → 修前 `_verify_chain` 在 aud_000 处断链
    （prev 期望=hash(aaa)、实得 hash(bbb)）；修后读序=rowid/seq=插入序。"""
    backend = matrix.make_backend()

    def _seed(n: int, ids: list[str]) -> None:
        for i in range(n):
            backend.append_outbox("document.upload", json.dumps({"n": i}))
        matrix.execute(
            "UPDATE audit_outbox SET created_at = ? WHERE shipped_at IS NULL", (NOV,)
        )
        # 钉 id 造逆序（id 主键可改——未搬运行）
        rows = matrix.execute(
            "SELECT id FROM audit_outbox WHERE shipped_at IS NULL"
            " ORDER BY created_at, id"
        ).fetchall()
        assert len(rows) == len(ids)
        for (old_id,), new_id in zip(rows, ids):
            matrix.execute(
                "UPDATE audit_outbox SET id = ? WHERE id = ?", (new_id, old_id)
            )

    # 第一轮：2 行同秒、id 逆序（aaa 先 append、bbb 后 append——但让 (created_at,id)
    # 序=插入序恰好一致不构成杀伤；真正的杀伤在第二轮新行 id 更小）
    _seed(2, ["aud_aaa", "aud_bbb"])
    assert backend.ship_outbox(now="2026-11-06 00:00:00")["shipped"] == 2
    first = backend.read_monthly_events(when=NOV)
    assert [r["id"] for r in first] == ["aud_aaa", "aud_bbb"]

    # 第二轮：同秒、id 'aud_000' < 'aud_aaa'——(created_at,id) 序把它排在最前，
    # 但插入序在链尾
    _seed(1, ["aud_000"])
    assert backend.ship_outbox(now="2026-11-07 00:00:00")["shipped"] == 1
    rows = backend.read_monthly_events(when=NOV)
    assert [r["id"] for r in rows] == ["aud_aaa", "aud_bbb", "aud_000"]  # 插入序
    _verify_chain(rows, None)  # 修前：此行断链（aud_000 prev 错接 bbb→重算不符）
    # 封存末哈希=插入序末条（非排序序「最大 id」）
    sealed = backend.seal_audit_months(now="2026-12-01 00:00:00")
    assert sealed["sealed"] == ["202610", "202611"]  # 无行当月库照封（幂等语义）
    assert rows[-1]["row_hash"] == backend.read_monthly_events(when=NOV)[-1]["row_hash"]


# ============ P2-2：搬运重试不污染 prev（崩溃窗口 + 同月新事件） ============


def test_ship_retry_after_crash_with_new_same_month_event(matrix, monkeypatch) -> None:
    """P2-2 回归（修前必败 + 偏差①补充实证）：2 行正常 ship → 新一批 2 行在
    「月库已插、回填未做」处注入崩溃 → 崩溃窗口后同月再入 1 行新事件 → 重跑
    ship → 链完整（修前：重试对已落库行用错误 prev 重算并推进 → 新行 prev 被
    污染 → `_verify_chain` 断链）。"""
    backend = matrix.make_backend()

    def _seed(n: int, created_at: str) -> None:
        for i in range(n):
            backend.append_outbox("document.upload", json.dumps({"n": i, "org_id": "org:tax"}))
        matrix.execute(
            "UPDATE audit_outbox SET created_at = ? WHERE shipped_at IS NULL",
            (created_at,),
        )

    # 第一轮：2 行正常搬运（链基线）
    _seed(2, "2026-11-05 10:00:00")
    assert backend.ship_outbox(now="2026-11-05 12:00:00")["shipped"] == 2

    # 崩溃窗口：新一批 2 行——注入点=月库插入后、shipped_at 回填前
    _seed(2, "2026-11-10 08:00:00")

    def _boom(self, conn, ids, now):
        raise RuntimeError("injected crash before shipped_at writeback")

    original = type(backend)._mark_shipped
    monkeypatch.setattr(type(backend), "_mark_shipped", _boom)
    with pytest.raises(RuntimeError, match="injected crash"):
        backend.ship_outbox(now="2026-11-10 09:00:00")  # 月库已插 2 行、回填未做
    monkeypatch.setattr(type(backend), "_mark_shipped", original)

    # 崩溃窗口后 API 继续写：同月新事件（R1 用例缺这半句——P2-2 的杀伤点）
    _seed(1, "2026-11-20 09:00:00")
    stats = backend.ship_outbox(now="2026-11-21 00:00:00")
    assert stats["shipped"] == 3  # 2 行重搬（已存去重）+ 1 行新事件

    rows = backend.read_monthly_events(when=NOV)
    assert len(rows) == 5  # 月库不重复（2+2+1）
    _verify_chain(rows, None)  # 修前：此处断链（新行 prev=污染值）
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE shipped_at IS NOT NULL"
    ).fetchone()[0] == 5


# ============ P2-3：update_task running 终态守卫 ============


def test_update_task_running_guard_after_cancel(matrix) -> None:
    """P2-3 回归（修前必败）：取消落账后 update_task(status='running') 零行
    生效——状态仍 failed + error 以 cancelled: 开头（修前被改成 running →
    无租约永久滞留 / 直调跑完写 done 复活）；正常 claim→running 不受影响。"""
    backend = matrix.make_backend()
    task_id = backend.create_task(None, task_type="ingest")
    backend.cancel_task(task_id, reason="cancelled: by user request")
    backend.update_task(task_id, status="running")  # 在途执行器的起步写
    row = backend.get_task(task_id)
    assert row["status"] == "failed"  # 修前：'running'（取消被复活）
    assert (row["error"] or "").startswith("cancelled:")
    # 正常路径不受影响：新任务 claim → running 照常推进
    t2 = backend.create_task(None, task_type="ingest")
    backend.update_task(t2, status="leased")
    backend.update_task(t2, status="running")
    assert backend.get_task(t2)["status"] == "running"
    # done 终态同样不被 running 复活（同一守卫语义的补角）
    backend.update_task(t2, status="done")
    backend.update_task(t2, status="running")
    assert backend.get_task(t2)["status"] == "done"


# ============ P3-1：已搬运 outbox 保留期清理 ============


def test_trim_shipped_outbox_only_old_shipped(matrix, tmp_path) -> None:
    """P3-1 回归：已搬运行过期删、未搬运/新行不动、幂等——「业务改了就一定
    有审计」的未落地承诺（shipped_at IS NULL）永不删。"""
    backend = matrix.make_backend()
    # 已搬运·过期（2025-10——早于 cutoff 2025-11）
    backend.append_outbox("document.upload", json.dumps({"org_id": "o"}))
    matrix.execute(
        "UPDATE audit_outbox SET created_at = '2025-10-01 00:00:00'"
        " WHERE shipped_at IS NULL"
    )
    backend.ship_outbox(now="2025-10-02 00:00:00")
    # 已搬运·新（2026-11）
    backend.append_outbox("document.upload", json.dumps({"org_id": "o"}))
    matrix.execute(
        "UPDATE audit_outbox SET created_at = ? WHERE shipped_at IS NULL", (NOV,)
    )
    backend.ship_outbox(now="2026-11-06 00:00:00")
    # 未搬运（新事件）
    backend.append_outbox("document.upload", json.dumps({"org_id": "o"}))

    removed = backend.trim_shipped_outbox(before_ts="2025-11-01 00:00:00")
    assert removed == 1
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE shipped_at IS NOT NULL"
    ).fetchone()[0] == 1  # 新已搬运行保留
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE shipped_at IS NULL"
    ).fetchone()[0] == 1  # 未搬运行永不删
    assert backend.trim_shipped_outbox(before_ts="2025-11-01 00:00:00") == 0  # 幂等

    # maintenance 任务体挂接（注册表序：prune 后 trim）
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.credentials import CredentialService
    from knowledge_lattice.worker.maintenance import (
        MAINTENANCE_BODIES,
        run_maintenance,
    )

    assert "audit_outbox_trimmed" in MAINTENANCE_BODIES
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    creds = CredentialService(backend, settings, tmp_path / "objects")
    task = backend.create_task(None, task_type="maintenance")
    stats = run_maintenance(backend, creds, settings, task)
    assert stats["audit_outbox_trimmed"] == 0  # 已清空——幂等零行


# ============ P3-2：outbox→audit_events 语义列投影 ============


def test_outbox_event_semantic_columns(matrix) -> None:
    """P3-2 回归：actor 取 actor→user_id→system 链；target_type/target_id 按
    事件类型从 payload 的 *_id 投影（m2-3 审计分级查询前置）。"""
    backend = matrix.make_backend()
    backend.append_outbox("upload.credential_issued", json.dumps(
        {"upload_id": "upl_x", "org_id": "org:tax", "user_id": "u_full", "size": 1}
    ))
    backend.append_outbox("document.upload", json.dumps(
        {"org_id": "org:tax", "doc_id": "doc_x", "actor": "u_full"}
    ))
    backend.append_outbox("maintenance.run", json.dumps({"task_id": "tsk_x"}))
    matrix.execute(
        "UPDATE audit_outbox SET created_at = ? WHERE shipped_at IS NULL", (NOV,)
    )
    backend.ship_outbox(now="2026-11-06 00:00:00")
    rows = {r["action"]: r for r in backend.read_monthly_events(when=NOV)}
    # user_id 回退（凭证事件无 actor 键）
    assert rows["upload.credential_issued"]["actor"] == "u_full"
    assert rows["upload.credential_issued"]["target_type"] == "upload"
    assert rows["upload.credential_issued"]["target_id"] == "upl_x"
    # document.* → doc_id 投影
    assert rows["document.upload"]["target_type"] == "document"
    assert rows["document.upload"]["target_id"] == "doc_x"
    # 未知/无 target 事件：actor=system、语义列留空（以 detail_json 为准）
    assert rows["maintenance.run"]["actor"] == "system"
    assert rows["maintenance.run"]["target_type"] is None


# ============ P3-5：封存半崩溃态补齐 sidecar ============


def test_seal_completes_half_sealed_state(matrix) -> None:
    """P3-5 回归：库已 chmod 0444 但 sidecar 未写（封存两步间崩溃）→ 重放
    只读补写 sidecar；已封存早退路径重放 chmod（sidecar 被误改可写时修正）。"""
    backend = matrix.make_backend()
    backend.append_outbox("document.upload", json.dumps({"org_id": "o"}))
    matrix.execute(
        "UPDATE audit_outbox SET created_at = ? WHERE shipped_at IS NULL", (NOV,)
    )
    backend.ship_outbox(now="2026-11-06 00:00:00")

    if matrix.is_sqlite:
        from knowledge_lattice.store.sqlite.audit import (
            month_path,
            read_seal,
            seal_monthly_audit,
            seal_path,
        )

        db_dir = backend._db_dir()
        path = month_path(db_dir, "202611")
        # 人工造半封存态：chmod 0444、无 sidecar
        import os as _os

        _os.chmod(path, 0o444)
        assert read_seal(db_dir, "202611") is None
        sealed = seal_monthly_audit(db_dir, "202611")  # 重放——只读补 sidecar
        assert sealed is not None and sealed["rows"] == 1
        assert read_seal(db_dir, "202611")["last_hash"] == sealed["last_hash"]
        assert not path.stat().st_mode & 0o222  # 仍只读
        # 早退路径重放 chmod：sidecar 被误开写位 → 再 seal 修正
        _os.chmod(seal_path(db_dir, "202611"), 0o644)
        seal_monthly_audit(db_dir, "202611")  # 早退路径重放 chmod（P3-5）
        assert not seal_path(db_dir, "202611").stat().st_mode & 0o222
    else:
        # pg：seals 表幂等 + 已封存分区再 seal 不重复记录
        first = backend.seal_audit_months(now="2026-12-01 00:00:00")
        assert first["sealed"] == ["202610", "202611"]
        again = backend.seal_audit_months(now="2026-12-01 00:00:00")
        assert again["sealed"] == []
        rows = matrix.execute(
            "SELECT count(*) FROM audit_month_seals WHERE month = '202611'"
        ).fetchone()[0]
        assert rows == 1


# ============ P3-13：env→get_settings 往返（worker 映射三字段） ============


def test_get_settings_reads_worker_env_roundtrip(monkeypatch) -> None:
    """P3-13 回归：_worker_env 映射的 embed_model/embed_batch_size/quality_llm
    在 get_settings 被读取（否则子进程映射漂移仍成立——N12 不闭环）。"""
    from knowledge_lattice.config import get_settings
    from knowledge_lattice.worker.runner import WorkerSupervisor

    monkeypatch.setenv("LATTICE_EMBED_MODEL", "fake-embed")
    monkeypatch.setenv("LATTICE_EMBED_BATCH_SIZE", "7")
    monkeypatch.setenv("LATTICE_QUALITY_LLM", "openai")
    s = get_settings()
    assert s.embed_model == "fake-embed"
    assert s.embed_batch_size == 7
    assert s.quality_llm == "openai"
    # _worker_env → 子进程 env → get_settings 全链路往返一致
    env = WorkerSupervisor._worker_env(s)
    assert env["LATTICE_EMBED_MODEL"] == "fake-embed"
    assert env["LATTICE_EMBED_BATCH_SIZE"] == "7"
    assert env["LATTICE_QUALITY_LLM"] == "openai"
