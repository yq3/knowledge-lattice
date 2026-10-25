"""TC-CRED-05 未消费凭证回收【单测｜M1】（双后端 + app.py 调度器）。

- 清理任务（maintenance 任务类型——design §3）回收过期未消费凭证；对象目录
  临时文件同清（design §6.3 时序）；已消费凭证（含过期）保留——凭证与文档/任务
  关联可追溯（M1-3 需求 A6）。
- app.py 内嵌调度器周期投递 maintenance 任务并在主进程执行（子进程 worker 随
  M2——M0a 进程内执行器口径）。
"""

from __future__ import annotations

import hashlib
import time

PAYLOAD = ("<html><body><h1>印花税税率表</h1><p>借款合同按借款金额万分之零点五贴花。</p></body></html>").encode()
SHA_HEX = hashlib.sha256(PAYLOAD).hexdigest()


def _issue(cred_env, *, payload: bytes = PAYLOAD) -> str:
    issued = cred_env["creds"].issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="doc.html", size=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
        content_type="text/html",
    )
    return issued["upload_id"]


def _expire(db, upload_id: str) -> None:
    db.execute(
        "UPDATE uploads SET expires_at = '2020-01-01 00:00:00' WHERE id = ?", (upload_id,)
    )


# ============ TC-CRED-05 清理任务 ============


def test_purge_reclaims_expired_unconsumed_and_objects(cred_env) -> None:
    """过期未消费凭证回收：issued（未 PUT）与 uploaded（已 PUT——对象文件同清）
    均回收；未过期不动；已消费（含过期）保留供追溯。"""
    env = cred_env
    creds = env["creds"]

    expired_issued = _issue(env)                       # 未 PUT 即过期
    expired_uploaded = _issue(env)                     # 已 PUT 过期——对象文件须同清
    creds.put_bytes(
        expired_uploaded, org_id="org:tax", user_id="u_full",
        service_id="agent-copilot", chunks=[PAYLOAD],
    )
    obj = creds._backend.get_upload_credential(expired_uploaded)
    obj_path = env["objects_dir"] / obj["object_key"]
    assert obj_path.is_file()

    alive = _issue(env)                                # 未过期——不动
    consumed = _issue(env)                             # 已消费（随后置过期）——保留
    creds.put_bytes(
        consumed, org_id="org:tax", user_id="u_full",
        service_id="agent-copilot", chunks=[PAYLOAD],
    )
    creds.consume(
        consumed, org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        dataset_id="ds:vat_lib", dims={"region": ["CN"]},
        create_document=env["ingest"].create_document,
    )

    _expire(env["db"], expired_issued)
    _expire(env["db"], expired_uploaded)
    _expire(env["db"], consumed)  # 已消费的过期凭证：不回收（追溯）

    result = creds.purge_expired()

    assert result["reclaimed"] == 2
    for gone in (expired_issued, expired_uploaded):
        assert env["db"].execute(
            "SELECT count(*) FROM uploads WHERE id = ?", (gone,)
        ).fetchone()[0] == 0
    assert not obj_path.exists()  # 对象文件同清
    assert env["db"].execute(
        "SELECT count(*) FROM uploads WHERE id = ?", (alive,)
    ).fetchone()[0] == 1
    assert env["db"].execute(
        "SELECT status FROM uploads WHERE id = ?", (consumed,)
    ).fetchone()[0] == "consumed"
    # 回收入审计 outbox（权限/治理事件——FR-6）
    events = env["db"].execute(
        "SELECT event_type FROM audit_outbox WHERE event_type = 'upload.reclaim'"
    ).fetchall()
    assert events, "未消费凭证回收未落审计"


def test_purge_keeps_within_window(cred_env) -> None:
    """expires_at 未到 → 不回收（90 天/窗口口径由 expires_at 本身承载）。"""
    env = cred_env
    upload_id = _issue(env)  # 未过期
    assert env["creds"].purge_expired()["reclaimed"] == 0
    assert env["db"].execute(
        "SELECT count(*) FROM uploads WHERE id = ?", (upload_id,)
    ).fetchone()[0] == 1


# ============ app.py 调度器（maintenance 周期投递 + 主进程执行） ============


def test_maintenance_scheduler_enqueues_and_runs(tmp_path) -> None:
    """内嵌调度器周期投递 maintenance 任务（tasks.type='maintenance'）并执行：
    过期凭证被回收、任务行终态 done。"""
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.credentials import CredentialService
    from fake_providers import FakeEmbedder

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        probe_interval_s=0, maintenance_interval_s=0.05,
    )
    app = create_app(
        settings, embedder=FakeEmbedder(dim=8), gate=EmbeddingGate(), run_startup_probe=False
    )

    from knowledge_lattice.store.sqlite import connect

    conn = connect(settings.db_path)
    conn.execute("INSERT OR IGNORE INTO orgs(id, name) VALUES('org:tax', 't')")
    conn.execute("INSERT OR IGNORE INTO users(id, username) VALUES('u_full', 'u_full')")
    conn.commit()

    creds = CredentialService(
        app.state.service.backend, settings, settings.data_dir / "objects"
    )
    upload_id = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="d.html", size=len(PAYLOAD), sha256=SHA_HEX, content_type="text/html",
    )["upload_id"]
    conn.execute(
        "UPDATE uploads SET expires_at = '2020-01-01 00:00:00' WHERE id = ?", (upload_id,)
    )
    conn.commit()

    with TestClient(app) as client:  # noqa: F841 —— lifespan 驱动调度器
        deadline = time.monotonic() + 10
        reclaimed = False
        while time.monotonic() < deadline:
            left = conn.execute(
                "SELECT count(*) FROM uploads WHERE id = ?", (upload_id,)
            ).fetchone()[0]
            if left == 0:
                reclaimed = True
                break
            time.sleep(0.05)
        assert reclaimed, "调度器未在窗口内回收过期凭证"

    rows = conn.execute(
        "SELECT type, status FROM tasks WHERE type = 'maintenance'"
    ).fetchall()
    assert rows, "调度器未投递 maintenance 任务"
    assert any(r[1] == "done" for r in rows)
    conn.close()
