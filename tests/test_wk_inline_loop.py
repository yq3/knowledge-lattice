"""P2-7（M2.1 R2）inline 兜底循环全类型认领 + P2-4/P2-5 共享装配工厂。

- 兜底循环（app inline 模式）：不经 kick 投递的任务（重启遗留/直建）在 poll
  周期内被循环认领完成；租约过期的 leased ingest 任务被循环重认领（inline
  默认语义与 subprocess 主循环一致——P2-7）；
- kick 抢先：新鲜任务恒由投递方 kick 同步消化（陈旧口径 created_before——
  上传时序语义保持，app_env 全量门禁实测时序）；
- build_backend（P2-4）：与 app 同后端（恒 sqlite）；设 LATTICE_PG_DSN 不产生
  跨库 split-brain（worker 默认装配同后端）；
- build_quality_service（P2-5）：quality_llm 档位选择与 app 同源
  （none→Noop / openai→OpenAICompatKeywordGenerator）。

sqlite-only（subprocess 形态由 test_task_04/e2e_03 承载）。
"""

from __future__ import annotations

import time

import pytest

HTML = ("<html><body><h1>土地增值税</h1><p>转让旧建筑物评估价格扣除项目。</p></body></html>").encode()


@pytest.fixture()
def inline_app(tmp_path):
    """inline 模式 app（小 poll——兜底循环快速领取）。"""
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from fake_providers import FakeEmbedder

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        probe_interval_s=0, maintenance_interval_s=0,
        worker_mode="inline", worker_poll_s=0.2,
    )
    app = create_app(
        settings, embedder=FakeEmbedder(dim=8), gate=EmbeddingGate(),
        run_startup_probe=False,
    )
    client = TestClient(app)
    client.__enter__()
    yield {"app": app, "settings": settings, "client": client}
    client.__exit__(None, None, None)


def _seed(app) -> None:
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect
    from helpers import (
        seed_dataset,
        seed_dim_value,
        seed_dimension,
        seed_grant,
        seed_membership,
        seed_org,
        seed_user,
    )

    conn = connect(app.state.service.settings.db_path)
    seed_org(conn)
    seed_dataset(conn, ds_id="ds:vat_lib")
    dim_id = seed_dimension(conn)
    val_id = seed_dim_value(conn, dim_id)
    seed_user(conn, "u_full")
    seed_membership(conn, "u_full")
    seed_grant(conn, user_id="u_full", dim_id=dim_id, val_id=val_id)
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = 'u_full'",
        (hash_token("dev-static-u-full"),),
    )
    conn.commit()
    conn.close()


def test_inline_loop_completes_unkicked_task(inline_app) -> None:
    """P2-7①：不经 kick 投递的任务（直建 doc+task）——兜底循环在 ~2×poll 内
    陈旧认领并完成（重启遗留/超量滞留同款路径）。"""
    env = inline_app
    _seed(env["app"])
    service = env["app"].state.service
    doc_id, task_id = service.ingest.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="loop-task",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML, mime_type="text/html", filename="l.html",
    )
    # 不 kick——只 wake 循环（等价投递方只投不消化 / app 重启遗留）
    service.worker.wake()
    deadline = time.monotonic() + 60  # P3-x：组合跑负载停顿预算放宽（原 10s ~4% 超时）
    row = doc = None
    while time.monotonic() < deadline:
        # P3-x′（R4）：task 读入轮询体内 + 双条件 AND 退出——防「doc 先达 full、
        # task 终态写尚未落库」读序竞态提前退出（终态与文档态一致才算完成）
        row = service.backend.get_task(task_id)
        doc = service.backend.get_document(doc_id)
        if (row is not None and row["status"] == "done"
                and doc is not None and doc["active_status"] == "searchable_full"):
            break
        time.sleep(0.1)
    assert row is not None and row["status"] == "done", \
        f"兜底循环未领取非 kick 任务（task={row}）"
    assert doc is not None and doc["active_status"] == "searchable_full", \
        f"任务完成但文档未达 full（doc={doc}）"


def test_inline_loop_reclaims_expired_leased_ingest(inline_app) -> None:
    """P2-7②：租约过期的 leased ingest 任务（模拟执行中崩溃残留）被兜底循环
    重认领续跑至完成——inline 模式下 A.2「租约过期可重认领」成立。"""
    env = inline_app
    _seed(env["app"])
    service = env["app"].state.service
    doc_id, task_id = service.ingest.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="reclaim-task",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML, mime_type="text/html", filename="r.html",
    )
    # 手工认领后不执行（等价崩溃残留）：短租约 0.3s
    claimed = service.backend.claim_next_task("wk-dead", lease_s=0.3)
    assert claimed is not None and claimed["id"] == task_id
    time.sleep(0.5)  # 租约过期

    deadline = time.monotonic() + 60  # P3-x：组合跑负载停顿预算放宽（原 15s ~4% 超时）
    row = doc = None
    while time.monotonic() < deadline:
        row = service.backend.get_task(task_id)
        doc = service.backend.get_document(doc_id)
        # P3-x′（R4）：双条件 AND 退出——原「done OR full」在 task 终态写与文档
        # 状态推进间存在读序竞态（full 先见、done 后落），单边条件可提前退出
        if (row is not None and row["status"] == "done"
                and doc is not None and doc["active_status"] == "searchable_full"):
            break
        time.sleep(0.1)
    assert row is not None and row["status"] == "done", \
        f"过期 leased 任务未被循环重认领（task={row}）"
    assert row["attempts"] == 2  # 重认领 attempts 递增
    assert doc["active_status"] == "searchable_full"


def test_kick_beats_loop_for_fresh_task(inline_app) -> None:
    """P2-7③（上传时序语义保持）：新鲜任务（created_at > now−poll）不被循环的
    陈旧口径认领——claim 的 created_before 过滤直接断言。"""
    env = inline_app
    _seed(env["app"])
    service = env["app"].state.service
    doc_id, task_id = service.ingest.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="fresh-task",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML, mime_type="text/html", filename="f.html",
    )
    # 循环的陈旧口径（now − poll）对刚建任务必不命中
    from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

    worker = service.worker
    stale_before = add_seconds(utc_now_ts(), -worker._poll_s)
    got = service.backend.claim_next_task(
        "wk-loop", lease_s=60.0, task_types=("ingest",),
        created_before=stale_before,
    )
    assert got is None, "新鲜任务被循环陈旧口径抢走（上传时序语义被破坏）"
    # 无过滤（kick 路径）恒可认领
    got = service.backend.claim_next_task("wk-kick", lease_s=60.0)
    assert got is not None and got["id"] == task_id


# ============ P2-4/P2-5 共享装配工厂 ============


def test_build_backend_shared_and_dsn_no_split_brain(tmp_path, monkeypatch) -> None:
    """P2-4：build_backend 与 app 同后端（ThreadLocalBackend + 迁移就绪）；
    设置 LATTICE_PG_DSN 时 worker 默认装配仍同后端（不再自动连 PG）。"""
    from knowledge_lattice.config import Settings
    from knowledge_lattice.store.factory import build_backend
    from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend
    from knowledge_lattice.worker.runner import WorkerServices, build_default_services

    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    backend = build_backend(settings)
    assert isinstance(backend, ThreadLocalBackend)

    # 设 DSN（模拟门禁/生产 shell 全局 export）——worker 默认装配不切 PG
    monkeypatch.setenv(
        "LATTICE_PG_DSN", "postgresql://postgres:lattice@localhost:5432/lattice"
    )
    services = build_default_services(settings)
    assert isinstance(services, WorkerServices)
    assert isinstance(services.backend, ThreadLocalBackend), \
        "worker 默认装配按 DSN 切 PG（split-brain 复发——P2-4）"
    # 同一 sqlite 库可写读（与 app 同库）
    task_id = services.backend.create_task(None, task_type="maintenance")
    assert services.backend.get_task(task_id) is not None


def test_build_quality_service_branches(tmp_path) -> None:
    """P2-5：quality_llm 档位——none→NoopKeywordGenerator / openai→
    OpenAICompatKeywordGenerator（app 与 worker 共用同一工厂）。"""
    from knowledge_lattice.adapters.enhancer import OpenAICompatKeywordGenerator
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.quality import (
        NoopKeywordGenerator,
        build_quality_service,
    )

    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    q_none = build_quality_service(None, settings)
    assert isinstance(q_none._keywords, NoopKeywordGenerator)

    settings_llm = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8, quality_llm="openai"
    )
    q_llm = build_quality_service(None, settings_llm)
    assert isinstance(q_llm._keywords, OpenAICompatKeywordGenerator), \
        "worker subprocess 部署下 LATTICE_QUALITY_LLM=openai 仍 Noop（P2-5）"


# ============ P2-A / P3-y / P3-z（M2.1 R3） ============


def test_get_settings_worker_mode_default_subprocess(monkeypatch) -> None:
    """P2-A（R3 唯一 FAIL 根因）：A(a) 裁定的 env 路径默认值——get_settings 在
    LATTICE_WORKER_MODE 未设时须回退 subprocess（与 Settings 数据类默认一致；
    R2 只改了数据类默认，env 路径 fallback 漂移为 inline——生产 env 部署下
    OOM 隔离保证失效）。get_settings 无进程内缓存（每次调用现读 env），
    monkeypatch 删 env 后直接断言。"""
    monkeypatch.delenv("LATTICE_WORKER_MODE", raising=False)
    from knowledge_lattice.config import get_settings

    assert get_settings().worker_mode == "subprocess"  # A(a) 裁定：env 路径默认 subprocess


def test_invalid_worker_mode_fail_closed(tmp_path) -> None:
    """P3-y：非法 worker_mode → create_app fail-closed（ValueError，不静默回退）。"""
    import pytest

    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings

    with pytest.raises(ValueError, match="invalid worker_mode.*bogus"):
        create_app(Settings(environment="test", data_dir=tmp_path,
                            worker_mode="bogus"))


def test_run_task_null_target_version_falls_back(ver_env) -> None:
    """P3-z：存量行（0005 前）target_version=NULL → run_task 回退
    _effective_version（文档当前有效版本——M1 口径），照常完成。"""
    backend, service = ver_env["backend"], ver_env["service"]
    doc_id, task_id = service.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="legacy-null-tv",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML, mime_type="text/html", filename="legacy.html",
    )
    # 造存量形态：抹掉 target_version（0005 前的任务行）
    ver_env["db"].execute(
        "UPDATE tasks SET target_version = NULL WHERE id = ?", (task_id,)
    )
    assert backend.get_task(task_id)["target_version"] is None

    service.run_task(task_id)  # NULL → _effective_version 兜底（M1 直调口径）

    assert backend.get_task(task_id)["status"] == "done"
    doc = backend.get_document(doc_id)
    assert doc["active_version"] == 1
    assert doc["active_status"] == "searchable_full"
