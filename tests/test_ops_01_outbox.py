"""TC-OPS-01 审计 outbox 一致性【集成｜M2】（m2-2 A 组）。

断言面（design §4 注「权限事件走 outbox：业务库同事务写 audit_outbox，后台搬运
保证业务改了就一定有审计」+ §5.3）：

- 治理动作全量接入（docs 侧本段可触发事件）：上传 / 覆盖上传 / 删除 / 取消 /
  维度值 PATCH / 凭证签发 / 凭证消费——业务写与 outbox **同一事务**；
- 崩溃注入：outbox 写入步抛错（事务内、业务语句已执行未提交）→ 业务一并回滚
  （同生共死）；业务写失败（维度解析错）→ outbox 不落（反向）；
- 搬运：shipped_at IS NULL → 月库 audit_events + 回填 shipped_at；搬运中断
  （月库已插、回填未做）重跑幂等不重复；
- 语义侧三类事件仅常量预留（m2s-1/m2s-3——断言归 TC-BUILD-03/TC-YAML-03/T-S9）。

双后端参数化（[sqlite]/[pg]）——audit/ship 方言差异在 store/<dialect> 包内吸收。
"""

from __future__ import annotations

import json

import pytest

from fake_providers import FakeEmbedder

from knowledge_lattice.adapters.embedder import EmbeddingGate
from knowledge_lattice.config import Settings
from knowledge_lattice.core.docs.ingest import IngestService

PAYLOAD = ("<html><body><h1>契税</h1><p>土地使用权出让缴纳契税。</p></body></html>").encode()
PAYLOAD_V2 = ("<html><body><h1>契税</h1><p>土地使用权出售视同转让。</p></body></html>").encode()


def _mk_service(matrix, tmp_path) -> IngestService:
    backend = matrix.make_backend()
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    return IngestService(
        backend, FakeEmbedder(dim=8, model_name="fake-embed"), settings,
        EmbeddingGate(), tmp_path / "objects",
    )


def _outbox_events(matrix, event_type: str) -> list[dict]:
    rows = matrix.execute(
        "SELECT id, event_type, payload_json, shipped_at FROM audit_outbox"
        " WHERE event_type = ? ORDER BY created_at, id",
        (event_type,),
    ).fetchall()
    return [
        {"id": r[0], "event_type": r[1], "payload": r[2], "shipped_at": r[3]}
        for r in rows
    ]


# ============ ① 治理动作同事务写 outbox（写入路径全量接入） ============


def test_upload_writes_outbox_same_tx(matrix, tmp_path) -> None:
    """上传（首传）治理事件：document.upload 与文档行/任务行同事务落库。"""
    service = _mk_service(matrix, tmp_path)
    doc_id, task_id = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="outbox",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=PAYLOAD, mime_type="text/html", filename="a.html",
    )
    events = _outbox_events(matrix, "document.upload")
    assert len(events) == 1
    payload = json.loads(events[0]["payload"])
    assert payload["org_id"] == "org:tax"
    assert payload["doc_id"] == doc_id
    assert payload["actor"] == "u_full"
    assert payload["task_id"] == task_id
    assert payload["version"] == 1
    # 同生：业务行与 outbox 行都在（任务行同样同库——断言任务在）
    assert matrix.execute(
        "SELECT count(*) FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()[0] == 1


def test_overwrite_writes_outbox_same_tx(matrix, tmp_path) -> None:
    """覆盖上传治理事件：document.overwrite（task_id 入 payload——与任务行
    同源；版本号由任务行 target_version 承载）。"""
    service = _mk_service(matrix, tmp_path)
    backend = matrix.make_backend()
    doc_id, _ = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="ov",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=PAYLOAD, mime_type="text/html", filename="a.html",
    )
    # 首传 pending 置 failed（409 语义解锁覆盖上传——「同一时刻只有一个 pending」）
    backend.set_doc_pending_failed(doc_id, 1, "test setup: release pending")
    doc_id2, task2 = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="ov2",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=PAYLOAD_V2, mime_type="text/html", filename="b.html",
        doc_id=doc_id,
    )
    assert doc_id2 == doc_id
    events = _outbox_events(matrix, "document.overwrite")
    assert len(events) == 1
    payload = json.loads(events[0]["payload"])
    assert payload["doc_id"] == doc_id
    assert payload["task_id"] == task2
    # 版本可经任务行追溯闭环（事件 → task_id → target_version）
    assert backend.get_task(task2)["target_version"] == 2


def test_delete_writes_outbox_same_tx(matrix, tmp_path) -> None:
    """删除治理事件：document.delete 与删除事务同生共死（改造自 M1 事务外写）。"""
    service = _mk_service(matrix, tmp_path)
    doc_id, _ = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="del",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=PAYLOAD, mime_type="text/html", filename="c.html",
    )
    service.delete_document(org_id="org:tax", doc_id=doc_id, actor_user_id="u_full")
    events = _outbox_events(matrix, "document.delete")
    assert len(events) == 1
    assert json.loads(events[0]["payload"])["doc_id"] == doc_id


def test_cancel_writes_outbox_same_tx(matrix, tmp_path) -> None:
    """取消治理事件（m2-1 P3-17 清偿）：task.cancel 与取消事务同生。"""
    service = _mk_service(matrix, tmp_path)
    doc_id, task_id = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="cx",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=PAYLOAD, mime_type="text/html", filename="d.html",
    )
    service.cancel_task(org_id="org:tax", task_id=task_id, actor_user_id="u_full")
    events = _outbox_events(matrix, "task.cancel")
    assert len(events) == 1
    payload = json.loads(events[0]["payload"])
    assert payload["task_id"] == task_id
    assert payload["doc_id"] == doc_id


def test_dims_patch_writes_outbox_same_tx(matrix, tmp_path) -> None:
    """维度值 PATCH 治理事件：document.dims_change 与替换事务同生。"""
    from helpers import seed_searchable_doc

    # 在用文档（active v1、无 pending——PATCH 前置条件；owner=u_full 全量授权）
    doc_id = seed_searchable_doc(
        matrix, "d_ops01_patch", owner_user_id="u_full", dims={"region": ["CN"]}
    )
    service = _mk_service(matrix, tmp_path)
    service.patch_document_dims(
        org_id="org:tax", doc_id=doc_id, dims={"region": ["CN", "OS"]},
        actor_user_id="u_full",
    )
    events = _outbox_events(matrix, "document.dims_change")
    assert len(events) == 1
    assert json.loads(events[0]["payload"])["dims"] == {"region": ["CN", "OS"]}


def test_credential_issue_consume_outbox_same_tx(matrix, tmp_path) -> None:
    """凭证签发/消费（TC-CRED 既有口径收口）：与业务写同事务（改造自事务外写）。"""
    import hashlib

    from knowledge_lattice.core.docs.credentials import CredentialService

    backend = matrix.make_backend()
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    creds = CredentialService(backend, settings, tmp_path / "objects")
    service = IngestService(
        backend, FakeEmbedder(dim=8), settings, EmbeddingGate(),
        tmp_path / "objects",
    )
    upload_id = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="f.html", size=len(PAYLOAD),
        sha256=hashlib.sha256(PAYLOAD).hexdigest(), content_type="text/html",
    )["upload_id"]
    assert len(_outbox_events(matrix, "upload.credential_issued")) == 1

    creds.put_bytes(
        upload_id, org_id="org:tax", user_id="u_full",
        service_id="agent-copilot", chunks=[PAYLOAD],
    )
    creds.consume(
        upload_id, org_id="org:tax", user_id="u_full",
        service_id="agent-copilot",
        dataset_id="ds:vat_lib", dims={"region": ["CN"]}, title="cred",
        create_document=service.create_document,
    )
    events = _outbox_events(matrix, "upload.consume")
    assert len(events) == 1
    assert matrix.execute(
        "SELECT status FROM uploads WHERE id = ?", (upload_id,)
    ).fetchone()[0] == "consumed"


# ============ ② 崩溃注入：业务与 outbox 同生共死（TC-OPS-01 核心） ============


def test_crash_between_business_and_outbox_rolls_back_both(matrix, tmp_path, monkeypatch) -> None:
    """outbox 写入步崩溃（业务语句已执行、事务未提交）→ 业务一并回滚——
    「业务改了就一定有审计」不允许「业务在、审计缺」的中间态。"""
    backend = matrix.make_backend()

    def _boom(self, conn, event_type, payload_json):
        raise RuntimeError("injected crash before outbox commit")

    monkeypatch.setattr(type(backend), "_outbox_insert", _boom)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    service = IngestService(
        backend, FakeEmbedder(dim=8), settings, EmbeddingGate(), tmp_path / "objects"
    )
    with pytest.raises(RuntimeError, match="injected crash"):
        service.create_document(
            org_id="org:tax", dataset_id="ds:vat_lib", title="crash",
            dims={"region": ["CN"]}, owner_user_id="u_full",
            file_bytes=PAYLOAD, mime_type="text/html", filename="g.html",
        )
    # 上传文档行回滚（同生共死——不能业务在、审计缺；matrix 既有 5 篇不动）
    assert matrix.execute(
        "SELECT count(*) FROM documents WHERE title = 'crash'"
    ).fetchone()[0] == 0
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'document.upload'"
    ).fetchone()[0] == 0


def test_business_failure_leaves_no_outbox(matrix, tmp_path) -> None:
    """业务写失败（PATCH 维度值不存在 → 事务回滚）→ outbox 不落（反向同生）。"""
    from helpers import seed_searchable_doc

    doc_id = seed_searchable_doc(
        matrix, "d_ops01_bf", owner_user_id="u_full", dims={"region": ["CN"]}
    )
    service = _mk_service(matrix, tmp_path)
    from knowledge_lattice.core.docs.ingest import UploadValidationError

    with pytest.raises(UploadValidationError):
        service.patch_document_dims(
            org_id="org:tax", doc_id=doc_id, dims={"region": ["NO_SUCH"]},
            actor_user_id="u_full",
        )
    assert len(_outbox_events(matrix, "document.dims_change")) == 0


# ============ ③ 搬运：outbox → 月库 audit_events + 回填 shipped_at ============


def test_ship_outbox_moves_rows_and_marks_shipped(matrix, tmp_path) -> None:
    """搬运（A2）：shipped_at IS NULL → 月库 audit_events（哈希链列写入）+ 回填
    shipped_at；重复搬运零行（已搬不再搬）。"""
    backend = matrix.make_backend()
    for i in range(3):
        backend.append_outbox(
            "document.upload", json.dumps({"n": i, "org_id": "org:tax"})
        )
    # 造数：事件时刻改到 2026-11（月库路由按事件原时刻，非搬运时点）
    matrix.execute(
        "UPDATE audit_outbox SET created_at = '2026-11-05 11:00:00'"
        " WHERE shipped_at IS NULL"
    )
    stats = backend.ship_outbox(now="2026-11-05 12:00:00")
    assert stats["shipped"] == 3

    shipped = matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE shipped_at IS NOT NULL"
    ).fetchone()[0]
    assert shipped == 3
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE shipped_at IS NULL"
    ).fetchone()[0] == 0

    rows = backend.read_monthly_events(when="2026-11-05 12:00:00")
    assert len(rows) == 3
    for row in rows:
        assert row["action"] == "document.upload"
        assert row["row_hash"]  # 哈希链列写入
    # 再跑：无新行可搬
    assert backend.ship_outbox(now="2026-11-05 12:01:00")["shipped"] == 0


def test_ship_survives_crash_between_insert_and_mark(matrix, tmp_path, monkeypatch) -> None:
    """搬运中断（月库已插、回填未做）重跑：月库幂等去重（id PK + IGNORE）、
    回填补齐——不丢不重（at-least-once + 幂等收敛）。

    注：sqlite 两步形态注入点=回填步（月库已插留存，重试 IGNORE 去重）；pg
    同事务形态注入点同位但整体回滚（重试全新搬运）——两种形态都收敛到
    「月库恰 1 行 + shipped_at 回填」。"""
    backend = matrix.make_backend()
    backend.append_outbox("document.upload", json.dumps({"org_id": "org:tax"}))
    matrix.execute(
        "UPDATE audit_outbox SET created_at = '2026-11-05 11:00:00'"
        " WHERE shipped_at IS NULL"
    )

    def _boom(self, conn, ids, now):
        raise RuntimeError("injected crash before shipped_at writeback")

    original = type(backend)._mark_shipped
    monkeypatch.setattr(type(backend), "_mark_shipped", _boom)
    with pytest.raises(RuntimeError, match="injected crash"):
        backend.ship_outbox(now="2026-11-05 12:00:00")
    monkeypatch.setattr(type(backend), "_mark_shipped", original)
    stats = backend.ship_outbox(now="2026-11-05 12:05:00")
    assert stats["shipped"] == 1
    rows = backend.read_monthly_events(when="2026-11-05 12:00:00")
    assert len(rows) == 1  # 幂等——不重复
    assert matrix.execute(
        "SELECT count(*) FROM audit_outbox WHERE shipped_at IS NOT NULL"
    ).fetchone()[0] == 1


# ============ ④ 语义侧三类事件常量预留（m2s-1/m2s-3——不实现） ============


def test_semantic_event_constants_reserved() -> None:
    """语义侧三类事件（#38 P1-7）仅常量预留——断言落 TC-BUILD-03/TC-YAML-03/T-S9。"""
    from knowledge_lattice.domain.audit_events import (
        EVENT_SEMANTIC_BUILD,
        EVENT_SEMANTIC_SYNC,
        EVENT_SEMANTIC_YAML_MERGE,
    )

    assert EVENT_SEMANTIC_SYNC == "semantic.sync"
    assert EVENT_SEMANTIC_BUILD == "semantic.build"
    assert EVENT_SEMANTIC_YAML_MERGE == "semantic.yaml_merge"
