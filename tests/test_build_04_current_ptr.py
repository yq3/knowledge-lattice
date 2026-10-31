"""G-18 current 指针收口（迁移 0007 activated_at——rev 回退重激活）+ O-1 sqlite
同 rev 竞态条件 upsert（DO UPDATE … WHERE status != 'ready'——ready 行不被重断
building、无 flap 双 ready 事件）。

验收：任务书 B.2；known-gaps G-18（重开条件 M2-S3 开工——本段收口）。
"""

from __future__ import annotations

import pytest

from helpers import seed_org

ORG = "org:tax"


@pytest.fixture()
def benv(backend, tmp_path):
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    return SimpleNamespace(db=backend, backend=backend.make_backend(), settings=settings)


def _seed_entity(env, key: str, name: str) -> None:
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_semantic import FakeSourceAdapter

    run_sync(env.backend, ORG,
             FakeSourceAdapter("template_center",
                               [EntityRecord(type="template", key=key, name=name)]),
             settings=env.settings,
             snapshot=[EntityRecord(type="template", key=key, name=name)],
             now="2026-10-31 09:00:00")


def _build(env):
    from knowledge_lattice.core.semantic.build import run_build

    return run_build(env.backend, ORG, settings=env.settings)


# ---- 迁移 0007：activated_at 落库 + 水位顺延 ----


def _columns(benv, table: str) -> set[str]:
    """方言无关列名集（sqlite PRAGMA / pg information_schema）。"""
    try:
        rows = benv.db.execute(f"PRAGMA table_info({table})").fetchall()
        return {r[1] for r in rows}
    except Exception:
        rows = benv.db.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = ?", (table,)).fetchall()
        return {r[0] for r in rows}


def test_migration_0007_schema_columns_and_levels(benv) -> None:
    """迁移 0007 落库面（B4③/m2s-4 改名——名实相符：activated_at 与
    source_system 两列 + semantic 域水位 [6,7]，不止 activated_at）。"""
    assert "activated_at" in _columns(benv, "sem_builds")
    # sem_relations.source_system（G-15 关系级 per-adapter 作用域）
    assert "source_system" in _columns(benv, "sem_relations")
    # 迁移号顺延：semantic 域 [6, 7]
    from knowledge_lattice.store.postgres.migrate import discover as pg_discover
    from knowledge_lattice.store.sqlite.migrate import discover as sq_discover

    for discover in (sq_discover, pg_discover):
        semantic = [m.version for m in discover() if m.domain == "semantic"]
        assert semantic == [6, 7]


def test_current_build_fallback_order_when_activated_at_null(benv) -> None:
    """既有 ready 行回填 activated_at=created_at——current 语义不漂移
    （B4③/m2s-4 改名——名实相符：本用例实断言 activated_at 置空时的兜底
    排序，而非迁移回填本身）。"""
    _seed_entity(benv, "TPL_A", "A")
    assert _build(benv)["status"] == "ready"
    benv.db.execute(
        "UPDATE sem_builds SET activated_at = NULL")
    benv.db.commit()
    # 模拟旧库未回填的窗口由迁移负责——此处直接断言 current 在 activated_at 为空时
    # 仍有兜底排序（id DESC），重激活路径随后覆盖
    current = benv.backend.sem_current_build(ORG)
    assert current is not None and current["status"] == "ready"


# ---- G-18：rev 回退 → current 指针跟随重激活 ----


def test_g18_rev_rollback_reactivates_older_build(benv) -> None:
    _seed_entity(benv, "TPL_A", "A")
    r1 = _build(benv)
    assert r1["status"] == "ready"

    _seed_entity(benv, "TPL_A", "A2")  # 内容前进 → 新 rev
    r2 = _build(benv)
    assert r2["status"] == "ready" and r2["dict_rev"] != r1["dict_rev"]
    assert benv.backend.sem_current_build(ORG)["dict_rev"] == r2["dict_rev"]

    # 源端回退到 r1 内容 → dict_rev 复原：复用 r1 行、重激活为 current
    _seed_entity(benv, "TPL_A", "A")
    r3 = _build(benv)
    assert r3["status"] == "ready"
    assert r3["dict_rev"] == r1["dict_rev"]
    assert r3["build_id"] == r1["build_id"]  # UNIQUE(org,dict_rev) 行复用
    current = benv.backend.sem_current_build(ORG)
    assert current["dict_rev"] == r1["dict_rev"]
    assert current["id"] == r1["build_id"]   # G-18 收口：current 不再失真
    assert current["activated_at"] is not None


# ---- O-1：sqlite 同 rev 竞态条件 upsert ----


def test_o1_insert_on_ready_row_returns_existing_without_flap(benv) -> None:
    """同 rev 行已 ready 时 sem_insert_build 不重断 building（无 flap），
    run_build 走重激活/让位路径——零双 ready 事件。"""
    from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_BUILD

    _seed_entity(benv, "TPL_A", "A")
    r1 = _build(benv)
    assert r1["status"] == "ready"

    # 直接复刻竞态窗口：行已 ready，再次 insert 同 rev
    build_id, was_ready = benv.backend.sem_insert_build(
        ORG, r1["dict_rev"], "{}", yaml_rev=None)
    assert was_ready is True
    assert build_id == r1["build_id"]
    status = benv.db.execute(
        "SELECT status FROM sem_builds WHERE id = ?", (build_id,)).fetchone()[0]
    assert status == "ready"  # 未被重断 building（O-1 条件 upsert）

    # run_build 同 rev 且 current 未动 → 让位 skipped、零新增 ready 事件
    events_before = benv.db.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = ?"
        " AND payload_json LIKE '%%\"status\": \"ready\"%%'",  # %%=psycopg 占位转义（sqlite 双通配等价）
        (EVENT_SEMANTIC_BUILD,)).fetchone()[0]
    result = _build(benv)
    assert result["status"] == "skipped"
    events_after = benv.db.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = ?"
        " AND payload_json LIKE '%%\"status\": \"ready\"%%'",  # %%=psycopg 占位转义（sqlite 双通配等价）
        (EVENT_SEMANTIC_BUILD,)).fetchone()[0]
    assert events_after == events_before  # 无 ready flap（O-1 收口）


def test_double_build_same_rev_single_ready_event(benv) -> None:
    """同 rev 顺序双 build（B4③/m2s-4 改名——名实相符：顺序调用非真并发；
    真并发形态由 pg 臂条件 upsert 语义与 O-1 用例覆盖）：每 rev 至多一条
    ready 事件、current 稳定（O-1/G-18）。"""
    from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_BUILD

    _seed_entity(benv, "TPL_A", "A")
    results = [_build(benv), _build(benv)]
    statuses = sorted(r["status"] for r in results)
    assert statuses == ["ready", "skipped"]
    ready_events = benv.db.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = ?"
        " AND payload_json LIKE '%%\"status\": \"ready\"%%'",  # %%=psycopg 占位转义（sqlite 双通配等价）
        (EVENT_SEMANTIC_BUILD,)).fetchone()[0]
    assert ready_events == 1
