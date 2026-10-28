"""TC-TASK-03 任务取消【集成｜M2】——POST /api/orgs/{org}/tasks/{id}/cancel 全链。

- 阶段边界停止：running 任务的执行器在下一阶段边界经 should_continue（心跳探测）
  探测到取消 → 静默退出（不写终态——取消结果为准）；
- 幂等续跑不复活：取消终态（failed + 'cancelled:'）重跑直接拒绝；runner 不再认领；
- 文档状态一致不滞留 parsing：取消时 pending 版本落 failed（T8 同款删块）；
  首次上传已切换（无 pending）→ 停在 searchable_lexical 稳态；
- API 面：200 幂等（已终态不动）/ 403 非授权者 / 404 跨组织或不存在。

服务层（ver_env 双后端参数化）+ API 面（app_env）。
"""

from __future__ import annotations

import threading
import time

import pytest
from fake_providers import FakeEmbedder

from knowledge_lattice.config import Settings
from knowledge_lattice.worker.runner import TaskRunner, WorkerServices

HTML = ("<html><body><h1>增值税申报</h1><p>一般纳税人安装服务分别核算。</p></body></html>").encode()


def _thread_safe_backend(ver_env, tmp_path):
    """跨线程执行（runner 线程 + 心跳线程）的 backend 形态：sqlite 每线程一连接
    （check_same_thread 纪律）/ pg 共享单连接（psycopg3 线程安全）。"""
    if ver_env["db"].is_sqlite:
        from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

        return ThreadLocalBackend(tmp_path / "lattice.db")
    return ver_env["backend"]


def _runner_stack(ver_env, tmp_path, settings):
    """runner 线程用的全套栈：thread-safe backend + 同配置 IngestService（依赖
    注入 ver_env 的 embedder/gate——与主线程 service 同一 FakeEmbedder 实例，
    便于失败/延迟注入联动；settings 用调用方局部覆盖——如 embed_batch_size）。"""
    from knowledge_lattice.core.docs.ingest import IngestService

    backend = _thread_safe_backend(ver_env, tmp_path)
    ingest = IngestService(
        backend, ver_env["embedder"], settings, ver_env["gate"],
        ver_env["objects_dir"],
    )
    runner = TaskRunner(
        backend, settings,
        services=WorkerServices(backend, settings, ingest=ingest),
        worker_id="wk-cancel-test",
    )
    return runner


def _mk_doc(env, *, title: str = "cancel-doc") -> tuple[str, str]:
    return env["service"].create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title=title,
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML, mime_type="text/html", filename="a.html",
    )


# ============ 服务层：取消 pending 任务 + 文档一致性 + 幂等不复活 ============


def test_cancel_pending_task_marks_doc_failed_no_parsing_stuck(ver_env) -> None:
    backend, service = ver_env["backend"], ver_env["service"]
    doc_id, task_id = _mk_doc(ver_env)

    task = service.cancel_task(
        org_id="org:tax", task_id=task_id, actor_user_id="u_full"
    )
    assert task["status"] == "failed"
    assert task["error"] == "cancelled: by user request"
    # 文档一致性：pending 版本 failed（不滞留 parsing）+ 块物理删除（T8）
    doc = backend.get_document(doc_id)
    assert doc["pending_version"] == 1
    assert doc["pending_status"] == "failed"
    assert doc["pending_error"] == "cancelled by user request"
    assert backend.delete_by_doc(doc_id, 1) == 0  # 无块残留

    # 幂等续跑不复活：直调 run_task 拒绝；runner 不认领
    service.run_task(task_id)
    assert backend.get_task(task_id)["status"] == "failed"
    runner = TaskRunner(
        backend, Settings(environment="test", data_dir=ver_env["settings"].data_dir),
        services=WorkerServices(backend, ver_env["settings"], ingest=service),
    )
    assert runner.run_once() is False

    # 二次取消：幂等（已终态不动）
    again = service.cancel_task(
        org_id="org:tax", task_id=task_id, actor_user_id="u_full"
    )
    assert again["status"] == "failed"
    assert again["error"] == "cancelled: by user request"


def test_cancel_first_upload_post_switch_stays_searchable_lexical(ver_env) -> None:
    """首次上传 D20 已切换（active 在用、无 pending）后取消 embed 阶段：文档停在
    searchable_lexical 稳态（一致，不滞留 parsing）。"""
    backend, service = ver_env["backend"], ver_env["service"]
    doc_id, task_id = _mk_doc(ver_env)
    service.run_task(task_id, stop_after="index_fts")  # 切换在用、停 running
    assert backend.get_document(doc_id)["active_status"] == "searchable_lexical"

    task = service.cancel_task(
        org_id="org:tax", task_id=task_id, actor_user_id="u_full"
    )
    assert task["status"] == "failed"
    doc = backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_lexical"  # 稳态保持
    assert doc["pending_version"] is None


def test_cancel_permission_and_scope(ver_env) -> None:
    """操作权限（FR-4：owner/org_admin）与跨组织 404。"""
    from knowledge_lattice.core.docs.ingest import (
        UploadNotFoundError,
        UploadPermissionError,
    )

    backend, service = ver_env["backend"], ver_env["service"]
    doc_id, task_id = _mk_doc(ver_env)
    with pytest.raises(UploadPermissionError):
        service.cancel_task(org_id="org:tax", task_id=task_id, actor_user_id="u_cn")
    with pytest.raises(UploadNotFoundError):
        service.cancel_task(org_id="org:gl", task_id=task_id, actor_user_id="u_full")
    # org_admin 可取消；owner 即上传者本人可取消
    task = service.cancel_task(org_id="org:tax", task_id=task_id, actor_user_id="admin_tax")
    assert task["status"] == "failed"


# ============ 阶段边界停止（在途取消——should_continue 心跳探测） ============


def test_cancel_stops_running_task_at_stage_boundary(ver_env, monkeypatch, tmp_path) -> None:
    """running 中取消：执行器在 parse 后的阶段边界停止（lost_lease——不写终态），
    取消结果为准、文档不滞留 parsing。"""
    backend, service = ver_env["backend"], ver_env["service"]
    settings = Settings(
        environment="test", data_dir=ver_env["settings"].data_dir,
        worker_heartbeat_s=0.05, worker_lease_s=60.0,
    )
    doc_id, task_id = _mk_doc(ver_env)

    from knowledge_lattice.adapters.parser_docling import ParsedDocument, ParsedBlock
    from knowledge_lattice.core.docs import ingest as ingest_mod

    entered = threading.Event()
    release = threading.Event()
    real_parsed = None

    def blocking_parse(path):
        entered.set()
        release.wait(timeout=10)
        return ParsedDocument(
            blocks=(ParsedBlock(kind="text", content="一般纳税人安装服务。"),)
        )

    monkeypatch.setattr(ingest_mod, "parse_document", blocking_parse)

    runner = _runner_stack(ver_env, tmp_path, settings)
    done = threading.Event()
    error: list[BaseException] = []

    def _run() -> None:
        try:
            runner.run_once()
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=_run)
    thread.start()
    assert entered.wait(timeout=10), "任务未进入 parse 阶段"
    # 等 running 态可见（认领 + running 推进）
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if backend.get_task(task_id)["status"] == "running":
            break
        time.sleep(0.05)
    assert backend.get_task(task_id)["status"] == "running"

    # 取消（parse 进行中）：任务 → failed + 文档 pending → failed（T8）
    task = service.cancel_task(
        org_id="org:tax", task_id=task_id, actor_user_id="u_full"
    )
    assert task["status"] == "failed"
    release.set()  # parse 返回 → 下一阶段边界应停止
    assert done.wait(timeout=10)
    thread.join(timeout=10)
    assert error == []  # 静默退出（不冒泡）

    # 取消结果为准（lost_lease 不覆盖）+ 文档一致
    row = backend.get_task(task_id)
    assert row["status"] == "failed"
    assert row["error"] == "cancelled: by user request"
    doc = backend.get_document(doc_id)
    assert doc["pending_status"] == "failed"  # 不滞留 parsing
    assert backend.delete_by_doc(doc_id, 1) == 0  # 无块写入（边界前停止）


def test_cancel_during_embed_batch_boundary(ver_env, tmp_path) -> None:
    """embed 长阶段内的细粒度边界：取消后剩余批次零外呼（FakeEmbedder.calls
    不再增长）、文档停 searchable_lexical、任务 failed。"""
    backend, service = ver_env["backend"], ver_env["service"]
    settings = Settings(
        environment="test", data_dir=ver_env["settings"].data_dir,
        worker_heartbeat_s=0.05, worker_lease_s=60.0,
        embed_batch_size=1,
    )
    # 多块长文（≥6 chunk——每段 ~300 字独立成块，批大小 1 → 多批次 embed 窗口）
    paragraphs = "".join(
        f"<p>{'增值税一般纳税人安装服务分别核算规定条款' * 18}第{i}段。</p>"
        for i in range(8)
    )
    payload = f"<html><body><h1>增值税申报</h1>{paragraphs}</body></html>".encode()
    doc_id, task_id = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="embed-cancel",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=payload, mime_type="text/html", filename="big.html",
    )
    embedder = ver_env["embedder"]

    runner = _runner_stack(ver_env, tmp_path, settings)
    # 先跑到 index_fts 后（searchable_lexical、embed 未开始）——主线程 service 直跑；
    # 直跑后任务留 running 且无租约（不可被认领）——手工回 pending 走认领路径
    service.run_task(task_id, stop_after="index_fts")
    backend.update_task(task_id, status="pending")
    calls_before = len(embedder.calls)

    # embed 批次进行中取消：embedder 每批 sleep 少许制造窗口，主线程取消
    original_embed = embedder.embed

    def slow_embed(texts):
        result = original_embed(texts)
        time.sleep(0.15)  # 每批 150ms——多批次窗口（批大小 1 × ≥6 块）
        return result

    embedder.embed = slow_embed  # type: ignore[method-assign]

    done = threading.Event()

    def _run() -> None:
        runner.run_once()
        done.set()

    threading.Thread(target=_run, daemon=True).start()
    # 等首批 embed 调用发生
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and len(embedder.calls) <= calls_before:
        time.sleep(0.02)
    assert len(embedder.calls) > calls_before, "embed 未启动"

    service.cancel_task(org_id="org:tax", task_id=task_id, actor_user_id="u_full")
    assert done.wait(timeout=10)

    row = backend.get_task(task_id)
    assert row["status"] == "failed"
    assert row["error"] == "cancelled: by user request"
    doc = backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_lexical"  # 稳态（未滞留 parsing）
    calls_after_cancel = len(embedder.calls)
    time.sleep(0.3)
    assert len(embedder.calls) == calls_after_cancel  # 剩余批次零外呼


# ============ API 面 ============


def test_cancel_endpoint_full_chain(app_env) -> None:
    client = app_env["client"]
    headers = {"Authorization": f"Bearer {app_env['static']['u_full']}"}
    admin_headers = {"Authorization": f"Bearer {app_env['static']['sysadmin']}"}
    # sysadmin 不是 org 成员（无管理权限豁免——D22）：u_full 是 owner（上传者）
    from knowledge_lattice.core.docs.ingest import IngestService

    service = app_env["app"].state.service
    doc_id, task_id = service.ingest.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="api-cancel",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML, mime_type="text/html", filename="a.html",
    )
    # 非授权者（u_cn 非 owner 非 admin）→ 403
    resp = client.post(
        f"/api/orgs/org:tax/tasks/{task_id}/cancel",
        headers={"Authorization": f"Bearer {app_env['static']['u_cn']}"},
    )
    assert resp.status_code == 403
    # owner 取消 → 200 + cancelled
    resp = client.post(f"/api/orgs/org:tax/tasks/{task_id}/cancel", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["cancelled"] is True
    assert body["status"] == "failed"
    assert body["error"] == "cancelled: by user request"
    # 文档不滞留 parsing
    doc = client.get(f"/api/orgs/org:tax/documents/{doc_id}", headers=headers).json()
    assert doc["pending_status"] == "failed"
    # 幂等：再取消 → 200 cancelled=True（现态）
    resp = client.post(f"/api/orgs/org:tax/tasks/{task_id}/cancel", headers=headers)
    assert resp.status_code == 200 and resp.json()["cancelled"] is True
    # 不存在 → 404
    resp = client.post("/api/orgs/org:tax/tasks/tsk_nope/cancel", headers=headers)
    assert resp.status_code == 404
