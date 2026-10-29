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


# ============ P1-1（M2.1 R2）取消×切换竞态守卫——在用版本块不得误删 ============


def test_set_doc_pending_failed_stale_version_keeps_active_blocks(ver_env) -> None:
    """P1-1 回归①：版本已切换收编（pending 清空）后，以旧版本号调
    set_doc_pending_failed → UPDATE 零行 → **不删块**（在用块保留、状态不变）。
    旧实现无条件 DELETE——active searchable_full 但全文零块的数据丢失。"""
    backend, service = ver_env["backend"], ver_env["service"]
    doc_id, task_id = _mk_doc(ver_env)
    service.run_task(task_id)  # → active v1 searchable_full（pending 已清）

    # 以已切换的 v1（现 active、pending=None）调用——stale pending 场景的等效直达
    backend.set_doc_pending_failed(doc_id, 1, "stale cancel race")

    doc = backend.get_document(doc_id)
    assert doc["active_version"] == 1
    assert doc["active_status"] == "searchable_full"  # 在用状态不被破坏
    # v1 块保留（dbwrap execute：qmark → pg 自动翻译）
    n = ver_env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 1", (doc_id,)
    ).fetchone()[0]
    assert n >= 1, "在用版本块被误删（P1-1）"
    # pending 字段未被伪造（pending 仍空）
    assert doc["pending_version"] is None


def test_cancel_vs_switch_race_active_blocks_survive(ver_env, monkeypatch) -> None:
    """P1-1 回归②（确定性交错）：切换事务先行提交、取消的文档侧失败后到——
    在用块保留、任务 failed（取消终态不被覆盖）。"""
    backend, service = ver_env["backend"], ver_env["service"]
    doc_id, t1 = _mk_doc(ver_env, title="p1-race")
    service.run_task(t1)  # v1 active full
    # 覆盖上传 v2（pending v2 + T2 target=2）
    _, t2 = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="p1-race-v2",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML, mime_type="text/html", filename="v2.html", doc_id=doc_id,
    )
    # 阻塞切换：T2 跑到 switch 前发信号并阻塞 → 取消 T2 → 切换放行（先行提交）
    import threading

    from knowledge_lattice.store.backend import VersionConflictError

    switch_entered = threading.Event()
    release_switch = threading.Event()

    def make_blocking_switch(target_backend):
        real_switch = target_backend.switch_active_version

        def blocking_switch(doc_id_, expected_pending):
            switch_entered.set()
            release_switch.wait(timeout=10)
            return real_switch(doc_id_, expected_pending)

        return blocking_switch

    monkeypatch.setattr(backend, "switch_active_version", make_blocking_switch(backend))
    # T2 直跑到 embed 完成（v2 pending searchable_full）后在切换处阻塞
    # ——直接构造该态更快：v2 已 searchable_full（index_fts 直插 + 状态推进）
    backend.set_doc_pending_status(doc_id, 2, "searchable_lexical")
    from knowledge_lattice.core.docs.ingest import new_ulid

    drafts = [{
        "id": new_ulid("chk"), "seq": 1, "content": "v2 块内容",
        "title_seg": "", "content_seg": "v2 块 内容", "token_count": 4,
    }]
    backend.insert(doc_id, 2, drafts)
    backend.set_doc_pending_status(doc_id, 2, "searchable_full")

    done = threading.Event()
    error: list[BaseException] = []

    # 线程安全形态（sqlite check_same_thread）：ThreadLocal backend + 同配置 service
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

    if ver_env["db"].is_sqlite:
        thread_backend = ThreadLocalBackend(
            ver_env["settings"].data_dir / "lattice.db"
        )
    else:
        thread_backend = backend
    monkeypatch.setattr(
        thread_backend, "switch_active_version", make_blocking_switch(thread_backend),
    )
    thread_service = IngestService(
        thread_backend, ver_env["embedder"], ver_env["settings"], ver_env["gate"],
        ver_env["objects_dir"],
    )

    def _run() -> None:
        try:
            thread_service.run_task(t2)  # 续跑：index_fts 已完成 → embed → switch
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)
        finally:
            done.set()

    threading.Thread(target=_run, daemon=True).start()
    assert switch_entered.wait(timeout=10)
    # 取消先行落账：任务 failed + （target=2 → pending v2 failed → 删 v2 块）
    task = service.cancel_task(org_id="org:tax", task_id=t2, actor_user_id="u_full")
    assert task["status"] == "failed"
    # 切换放行：pending 已 failed → 乐观校验零行 → VersionConflictError 被
    # run_task 的「并发取消让位」守卫吞下（终态归取消所有——静默退出）
    release_switch.set()
    assert done.wait(timeout=10)
    assert error == []  # 不冒泡（取消让位语义）

    # P1-1 断言核心：v1 在用块保留、active 状态未被破坏
    n_v1 = ver_env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 1", (doc_id,)
    ).fetchone()[0]
    assert n_v1 >= 1, "在用 v1 块被取消竞态误删（P1-1）"
    doc = backend.get_document(doc_id)
    assert doc["active_version"] == 1
    assert doc["active_status"] == "searchable_full"
    # v2 块已被取消删除（T8）；v2 pending failed
    n_v2 = ver_env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 2", (doc_id,)
    ).fetchone()[0]
    assert n_v2 == 0


# ============ P2-3（M2.1 R2）取消按任务目标版本——不误杀新版本上传 ============


def test_cancel_old_task_spares_new_pending_version(ver_env) -> None:
    """P2-3 主场景：T1 running（target=1，v1 已切 active）+ 覆盖上传 v2 pending →
    取消 T1 → v2 保持 parsing 不受触碰、T2 照常可执行至切换。旧实现按文档当前
    pending（v2）落失败——新版本上传被旧任务取消误杀。"""
    backend, service = ver_env["backend"], ver_env["service"]
    doc_id, t1 = _mk_doc(ver_env, title="p2-3")
    service.run_task(t1, stop_after="index_fts")  # v1 active lexical、T1 running
    _, t2 = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="p2-3-v2",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML, mime_type="text/html", filename="v2.html", doc_id=doc_id,
    )
    assert backend.get_task(t2)["target_version"] == 2

    # 取消 T1（旧任务）——不得触碰 v2
    task = service.cancel_task(org_id="org:tax", task_id=t1, actor_user_id="u_full")
    assert task["status"] == "failed"
    assert task["error"] == "cancelled: by user request"
    doc = backend.get_document(doc_id)
    assert doc["pending_version"] == 2
    assert doc["pending_status"] == "parsing"  # v2 原封不动（不滞留也不误杀）
    assert doc["active_status"] == "searchable_lexical"  # v1 在用不受触碰

    # T2 照常可执行至完成（v2 full + 切换）
    service.run_task(t2)
    doc = backend.get_document(doc_id)
    assert doc["active_version"] == 2
    assert doc["active_status"] == "searchable_full"
    assert backend.get_task(t2)["status"] == "done"


def test_cancel_overwrite_with_blocks_fails_pending_and_keeps_v1(ver_env) -> None:
    """P2-3/P3-10：覆盖上传 index_fts 完成后（v2 pending 有块）取消 T2 →
    v2 pending failed + v2 块物理删除（T8 直断言）+ v1 在用块与状态不动。"""
    backend, service = ver_env["backend"], ver_env["service"]
    doc_id, t1 = _mk_doc(ver_env, title="p3-10")
    service.run_task(t1)  # v1 active full
    _, t2 = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="p3-10-v2",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML, mime_type="text/html", filename="v2.html", doc_id=doc_id,
    )
    service.run_task(t2, stop_after="index_fts")  # v2 pending lexical（有块）
    n_v2 = ver_env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 2", (doc_id,)
    ).fetchone()[0]
    assert n_v2 >= 1  # 前置：v2 块在场

    backend.update_task(t2, status="pending")  # stop_after 留 running——回可取消态
    task = service.cancel_task(org_id="org:tax", task_id=t2, actor_user_id="u_full")
    assert task["status"] == "failed"

    doc = backend.get_document(doc_id)
    assert doc["pending_version"] == 2
    assert doc["pending_status"] == "failed"  # 按任务 target（2）落失败
    n_v2_after = ver_env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 2", (doc_id,)
    ).fetchone()[0]
    assert n_v2_after == 0  # T8：v2 块物理删除（不留检索残留）
    n_v1 = ver_env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 1", (doc_id,)
    ).fetchone()[0]
    assert n_v1 >= 1  # v1 在用块不动
    assert doc["active_version"] == 1
    assert doc["active_status"] == "searchable_full"


# ============ P2-N1（M2.1 R4）_record_doc_error 按任务目标版本收口 ============


def _thread_ingest(ver_env, tmp_path):
    """线程安全 IngestService（sqlite check_same_thread——ThreadLocal backend；
    共享 ver_env 的 embedder/gate：失败/阻塞注入对两线程同源生效）。"""
    from knowledge_lattice.core.docs.ingest import IngestService

    backend = _thread_safe_backend(ver_env, tmp_path)
    return IngestService(
        backend, ver_env["embedder"], ver_env["settings"], ver_env["gate"],
        ver_env["objects_dir"],
    )


def test_record_doc_error_spares_concurrent_new_pending(ver_env, tmp_path, monkeypatch) -> None:
    """P2-N1 场景 A：首传 T1 越过 index_fts（D20 切换 active v1、pending=NULL）
    进 embed 长阶段失败——并发覆盖上传的 pending v2 **不被旧任务失败杀死**
    （v2 保持 parsing、无块被删），v1 落 active_error；T2 随后可完成至切换。"""
    import threading

    backend, service = ver_env["backend"], ver_env["service"]
    doc_id, t1 = _mk_doc(ver_env, title="p2-n1-a")

    entered = threading.Event()
    release = threading.Event()
    real_embed = ver_env["embedder"].embed
    state = {"first": True}

    def embed_block_then_raise(texts):
        if state["first"]:  # T1 的 embed 批次：阻塞 → 放行后 raise
            state["first"] = False
            entered.set()
            release.wait(timeout=10)
            raise RuntimeError("embed exploded (P2-N1-A)")
        return real_embed(texts)

    monkeypatch.setattr(ver_env["embedder"], "embed", embed_block_then_raise)
    thread_service = _thread_ingest(ver_env, tmp_path)

    done = threading.Event()
    error: list[BaseException] = []

    def _run() -> None:
        try:
            thread_service.run_task(t1)
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)
        finally:
            done.set()

    threading.Thread(target=_run, daemon=True).start()
    assert entered.wait(timeout=10)  # T1 已进 embed（index_fts 已提交：D20 切换在用）
    assert backend.get_document(doc_id)["active_version"] == 1

    # 并发覆盖上传 v2（pending 为 NULL → start_overwrite 放行；T2 target=2）
    _, t2 = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="p2-n1-a-v2",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML, mime_type="text/html", filename="v2.html", doc_id=doc_id,
    )
    assert backend.get_document(doc_id)["pending_version"] == 2

    release.set()  # T1 的 embed 放行 → raise → 失败路径
    assert done.wait(timeout=10)
    assert any("embed exploded" in str(e) for e in error)

    row = backend.get_task(t1)
    assert row["status"] == "failed"
    assert "embed exploded" in row["error"]  # T1 原始失败原因保留
    doc = backend.get_document(doc_id)
    assert doc["active_version"] == 1
    assert doc["active_error"] and "embed exploded" in doc["active_error"]  # v1 落 active_error
    assert doc["pending_version"] == 2
    assert doc["pending_status"] == "parsing"  # v2 原封不动（不滞留失败也不被删）
    assert doc["pending_error"] is None
    n_v2 = ver_env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 2", (doc_id,)
    ).fetchone()[0]
    assert n_v2 == 0  # 无 v2 块被误删（本就未写——直断言防未来回归）

    # T2 随后正常完成：v2 full + 切换（restore embed 为真实实现）
    monkeypatch.setattr(ver_env["embedder"], "embed", real_embed)
    service.run_task(t2)
    doc = backend.get_document(doc_id)
    assert doc["active_version"] == 2
    assert doc["active_status"] == "searchable_full"
    assert backend.get_task(t2)["status"] == "done"


def test_record_doc_error_spares_new_active_after_switch(ver_env, tmp_path, monkeypatch) -> None:
    """P2-N1 场景 B（反向）：T1 在 embed 长阶段失败时 v2 已完成切换（active v2）
    ——旧任务失败不得把 active_error 写到新在用版本上（v2 的 active_error 保持
    None、状态 searchable_full 不动；v1 块保持切换时的 tombstone 形态）。"""
    import threading

    backend, service = ver_env["backend"], ver_env["service"]
    doc_id, t1 = _mk_doc(ver_env, title="p2-n1-b")

    entered = threading.Event()
    release = threading.Event()
    real_embed = ver_env["embedder"].embed
    state = {"first": True}

    def embed_block_then_raise(texts):
        if state["first"]:
            state["first"] = False
            entered.set()
            release.wait(timeout=10)
            raise RuntimeError("embed exploded (P2-N1-B)")
        return real_embed(texts)

    monkeypatch.setattr(ver_env["embedder"], "embed", embed_block_then_raise)
    thread_service = _thread_ingest(ver_env, tmp_path)

    done = threading.Event()
    error: list[BaseException] = []

    def _run() -> None:
        try:
            thread_service.run_task(t1)
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)
        finally:
            done.set()

    threading.Thread(target=_run, daemon=True).start()
    assert entered.wait(timeout=10)

    # v2 完成全链并切换（embed 用后续真实批次）——active v2 full
    _, t2 = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="p2-n1-b-v2",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML, mime_type="text/html", filename="v2.html", doc_id=doc_id,
    )
    service.run_task(t2)
    assert backend.get_document(doc_id)["active_version"] == 2

    release.set()  # T1 embed 放行 → raise → except（version=1）
    assert done.wait(timeout=10)
    assert any("embed exploded" in str(e) for e in error)

    row = backend.get_task(t1)
    assert row["status"] == "failed"
    assert "embed exploded" in row["error"]
    doc = backend.get_document(doc_id)
    assert doc["active_version"] == 2
    assert doc["active_status"] == "searchable_full"  # 新在用状态不被污染
    assert doc["active_error"] is None  # 旧任务失败不写新 active（P2-N1 核心断言）
    assert doc["pending_version"] is None
    # v1 块保持切换事务的 tombstone 形态（未被错误路径触碰）
    n_v1_tomb = ver_env["db"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND version = 1 AND tombstone = 1",
        (doc_id,),
    ).fetchone()[0]
    assert n_v1_tomb >= 1
