"""m2s-4 R2 修复（R1 Tester FAIL 项 + O3 永久用例）：

- **IMPL_BUG（阻断）**：annotate 空**可用**别名词典运行期崩溃——
  build_automaton 在 entries 空时（pyahocorasick 空 trie `make_automaton()`
  不生效）`iter()` 抛 AttributeError → REST/MCP 500。三触发面：全
  restricted / 全 fuzzy_only / 零别名（零实体）。修复后语义：该 org 任何
  文本零标注（T-S9「restricted 表现为不存在」+ 负样本零标注——fail-closed
  不变 crash）。core 集成面双后端（[pg] 条目）+ REST HTTP 200 面；
- **O3**：G-19 `_in_window` 跨零点窗口（23:00-05:00 形态）永久用例
  （tester 探针 D1~D7 口径：23:30/02:00 窗内、12:00 窗外、05:00 边界含端、
  非法窗口 fail-open）。
"""

from __future__ import annotations

import json

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"


# ---- IMPL_BUG：core 集成面（双后端——backend fixture [pg] 参数化） ----


@pytest.fixture()
def env(backend, tmp_path):
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path,
                        semantic_eval_golden_path="")
    return SimpleNamespace(db=backend, backend=backend.make_backend(),
                           settings=settings)


def _sync_one(env, *, aliases=("税额概念",)):
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync

    recs = [EntityRecord(type="concept", key="c.one", name="税额概念",
                         aliases=aliases)]
    run_sync(env.backend, ORG, FakeSourceAdapter("template_center", recs),
             settings=env.settings, snapshot=list(recs), now=NOW)


def _annotate_via_build(env, text: str):
    """构建后走服务编排 annotate_text（REST/MCP 同路径——bug 触发面）。"""
    from knowledge_lattice.core.semantic.annotator import (
        annotate_text, clear_annotator_cache,
    )
    from knowledge_lattice.core.semantic.build import run_build

    clear_annotator_cache()
    build = run_build(env.backend, ORG, settings=env.settings)
    assert build["status"] == "ready", build
    return annotate_text(env.backend, env.settings, ORG, text)


def test_impl_bug_all_restricted_zero_mentions_not_crash(env) -> None:
    """触发面①：全部实体 restricted——任何文本零标注（表现为不存在），
    不抛 AttributeError。"""
    _sync_one(env)
    env.db.execute(
        "UPDATE sem_entities SET sensitivity = 'restricted'"
        " WHERE org_id = ?", (ORG,))
    env.db.commit()
    result = _annotate_via_build(env, "税额概念的口径是什么")
    assert result["mentions"] == [] and result["candidates"] == []
    assert result["dict_rev"]  # 已构建——服务面照常带 rev 锚点


def test_impl_bug_all_fuzzy_only_zero_mentions_not_crash(env) -> None:
    """触发面②：可用别名全部 fuzzy_only（不进自动机——TC-BUILD-02）→
    零可用面：零标注不崩溃。"""
    _sync_one(env, aliases=())          # 无 sync 别名
    # 可用面清空：name/code 别名移除后改挂 fuzzy_only（同 norm 先删后插）
    env.db.execute(
        "DELETE FROM sem_aliases WHERE org_id = ? AND kind IN ('name', 'code')",
        (ORG,))
    env.db.execute(
        "INSERT INTO sem_aliases(org_id, entity_id, alias, alias_norm, kind,"
        " match_mode, weight) SELECT ?, id, '税额概念', '税额概念', 'sync',"
        " 'fuzzy_only', 1.0 FROM sem_entities WHERE org_id = ? AND key = 'c.one'",
        (ORG, ORG))
    env.db.commit()
    result = _annotate_via_build(env, "税额概念的口径是什么")
    assert result["mentions"] == []


def test_impl_bug_empty_dictionary_zero_mentions_not_crash(env) -> None:
    """触发面③：零实体（零别名）词典构建后 annotate——零标注不崩溃。"""
    result = _annotate_via_build(env, "随便什么文本")
    assert result["mentions"] == [] and result["candidates"] == []
    assert result["dict_rev"]


# ---- IMPL_BUG：REST HTTP 面（三触发面 → 200 而非 500） ----


@pytest.fixture()
def rest_app(tmp_path):
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
        semantic_eval_golden_path="",
    )
    app = create_app(settings, gate=EmbeddingGate(), run_startup_probe=False)
    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    from helpers import seed_membership, seed_user

    seed_user(conn, "u_full")
    seed_membership(conn, "u_full", ORG)
    conn.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                 (hash_token("dev-static-u-full"), "u_full"))
    conn.commit()
    with TestClient(app) as client:
        yield {"client": client, "conn": conn, "settings": settings}
    conn.close()


def _post_annotate(rest_app, text: str):
    return rest_app["client"].post(
        f"/api/orgs/{ORG}/semantic/annotate",
        json={"text": text},
        headers={"Authorization": "Bearer dev-static-u-full",
                 "X-Org-Id": ORG})


def _build_app(rest_app):
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    return run_build(SqliteBackend(rest_app["conn"]), ORG,
                     settings=rest_app["settings"])


def test_impl_bug_rest_all_restricted_200(rest_app) -> None:
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    b = SqliteBackend(rest_app["conn"])
    recs = [EntityRecord(type="concept", key="c.one", name="税额概念")]
    run_sync(b, ORG, FakeSourceAdapter("template_center", recs),
             settings=rest_app["settings"], snapshot=list(recs), now=NOW)
    rest_app["conn"].execute(
        "UPDATE sem_entities SET sensitivity = 'restricted' WHERE org_id = ?",
        (ORG,))
    rest_app["conn"].commit()
    clear_annotator_cache()
    assert _build_app(rest_app)["status"] == "ready"
    resp = _post_annotate(rest_app, "税额概念是什么")
    assert resp.status_code == 200, resp.text        # 修复前 500
    assert resp.json()["mentions"] == []


def test_impl_bug_rest_all_fuzzy_only_200(rest_app) -> None:
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    b = SqliteBackend(rest_app["conn"])
    recs = [EntityRecord(type="concept", key="c.one", name="税额概念",
                         aliases=())]
    run_sync(b, ORG, FakeSourceAdapter("template_center", recs),
             settings=rest_app["settings"], snapshot=list(recs), now=NOW)
    rest_app["conn"].execute(
        "DELETE FROM sem_aliases WHERE org_id = ? AND kind IN ('name', 'code')",
        (ORG,))
    rest_app["conn"].execute(
        "INSERT INTO sem_aliases(org_id, entity_id, alias, alias_norm, kind,"
        " match_mode, weight) SELECT ?, id, '税额概念', '税额概念', 'sync',"
        " 'fuzzy_only', 1.0 FROM sem_entities WHERE org_id = ? AND key = 'c.one'",
        (ORG, ORG))
    rest_app["conn"].commit()
    clear_annotator_cache()
    assert _build_app(rest_app)["status"] == "ready"
    resp = _post_annotate(rest_app, "税额概念是什么")
    assert resp.status_code == 200, resp.text
    assert resp.json()["mentions"] == []


def test_impl_bug_rest_empty_dictionary_200(rest_app) -> None:
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache

    clear_annotator_cache()
    assert _build_app(rest_app)["status"] == "ready"   # 空词典可构建
    resp = _post_annotate(rest_app, "任何文本")
    assert resp.status_code == 200, resp.text
    assert resp.json()["mentions"] == []


# ---- O3：_in_window 跨零点窗口永久用例（tester 探针 D1~D7 口径） ----


def test_o3_in_window_overnight_wrap() -> None:
    """23:00-05:00 跨零点形态：23:30/02:00 窗内、12:00 窗外、05:00 边界
    含端点（lo<=t<=hi / t>=lo or t<=hi）。"""
    from knowledge_lattice.worker.maintenance import _in_window

    assert _in_window("2026-10-31 23:30:00", "23:00-05:00") is True
    assert _in_window("2026-10-31 02:00:00", "23:00-05:00") is True
    assert _in_window("2026-10-31 23:00:00", "23:00-05:00") is True   # lo 端
    assert _in_window("2026-10-31 05:00:00", "23:00-05:00") is True   # hi 端
    assert _in_window("2026-10-31 12:00:00", "23:00-05:00") is False
    assert _in_window("2026-10-31 05:01:00", "23:00-05:00") is False
    assert _in_window("2026-10-31 22:59:00", "23:00-05:00") is False


def test_o3_in_window_same_day_and_invalid_fail_open() -> None:
    """同日窗口（01:00-05:00）端点语义；非法窗口 fail-open（视为无窗口，
    不吞调度——告警日志在实现侧）。"""
    from knowledge_lattice.worker.maintenance import _in_window

    assert _in_window("2026-10-31 01:00:00", "01:00-05:00") is True
    assert _in_window("2026-10-31 03:30:00", "01:00-05:00") is True
    assert _in_window("2026-10-31 05:00:00", "01:00-05:00") is True
    assert _in_window("2026-10-31 00:59:00", "01:00-05:00") is False
    # 非法形态：解析失败 fail-open（True）——运维配置错误的可见面在日志
    assert _in_window("2026-10-31 09:00:00", "bogus") is True
    assert _in_window("2026-10-31 09:00:00", "9点-17点") is True
    assert _in_window("2026-10-31 09:00:00", "05:00-") is True


def test_o3_daily_body_window_no_dispatch_outside(monkeypatch, backend,
                                                  tmp_path) -> None:
    """窗外（12:00）零投递、窗内（23:30）投递——maintenance body 口径。"""
    import dataclasses
    import json as _json
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings
    from knowledge_lattice.worker.maintenance import MAINTENANCE_BODIES

    seed_org(backend, ORG)
    settings = Settings(
        environment="test", data_dir=tmp_path,
        semantic_sources_json=_json.dumps(
            {ORG: {"yaml": {"endpoint": "/tmp/never"}}}),
        semantic_eval_golden_path="",
        semantic_night_window="23:00-05:00")
    env = SimpleNamespace(db=backend, backend=backend.make_backend(),
                          settings=settings)
    body = MAINTENANCE_BODIES["semantic_daily_sync"]

    out = body(env.backend, None, settings, "2026-10-31 12:00:00")
    assert out["enqueued"] == 0 and out["window"] == "23:00-05:00"
    assert env.db.execute(
        "SELECT count(*) FROM tasks WHERE type = 'semantic_sync'"
        " AND status = 'pending'").fetchone()[0] == 0

    out2 = body(env.backend, None, settings, "2026-10-31 23:30:00")
    assert out2["enqueued"] == 1
    assert env.db.execute(
        "SELECT count(*) FROM tasks WHERE type = 'semantic_sync'"
        " AND status = 'pending'").fetchone()[0] == 1
