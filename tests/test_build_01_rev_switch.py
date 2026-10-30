"""TC-BUILD-01 dict_rev 与跳过 / TC-BUILD-03 原子切换与审计（m2s-2 构建骨架）。

- dict_rev = hash(active 实体 + 别名 + yaml_rev + **embed_model 标签**)——换模型
  必然新 rev（#42 P1-2：embed 标签必须进 dict_rev 输入）；
- 与当前 ready 版本相同 → 跳过（不产新 build 行）；
- 切换原子性：构建失败（切换阶段异常）→ 新行 failed、旧 ready 继续 = 当前
  （T-S12 骨架半句——懒加载/引用计数随 annotate 段）；
- 构建完成/失败事件入 audit_outbox（TC-BUILD-03——#38 P1-7）。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fake_semantic import FakeSourceAdapter, tpl_snapshot
from helpers import seed_org

ORG = "org:tax"

NOW = "2026-10-30 12:00:00"


@pytest.fixture()
def build_env(backend, tmp_path):
    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_model="fake-embed")
    env = SimpleNamespace(db=backend, backend=backend.make_backend(), settings=settings)
    # 库内先落一份 active 快照（构建输入——sem_entities/aliases/relations）
    from knowledge_lattice.core.semantic.sync import run_sync

    run_sync(env.backend, ORG, FakeSourceAdapter("template_center", tpl_snapshot(5)),
             settings=settings, snapshot=tpl_snapshot(5), now=NOW)
    return env


def _rows(env) -> list[tuple]:
    return env.db.execute(
        "SELECT id, dict_rev, status FROM sem_builds ORDER BY id"
    ).fetchall()


# ---- TC-BUILD-01：dict_rev 相同跳过 / 变更后新 rev ----


def test_tc_build_01_same_rev_skips_second_build(build_env) -> None:
    from knowledge_lattice.core.semantic.build import run_build

    r1 = run_build(build_env.backend, ORG, settings=build_env.settings)
    assert r1["status"] == "ready" and r1["build_id"] and r1["dict_rev"]
    r2 = run_build(build_env.backend, ORG, settings=build_env.settings)
    assert r2["status"] == "skipped"
    assert r2["dict_rev"] == r1["dict_rev"]
    rows = _rows(build_env)
    assert len(rows) == 1, "dict_rev 相同不得产新 build 行（TC-BUILD-01）"
    assert rows[0][2] == "ready"


def test_tc_build_01_alias_change_produces_new_rev(build_env) -> None:
    from knowledge_lattice.core.semantic.build import run_build

    r1 = run_build(build_env.backend, ORG, settings=build_env.settings)
    eid = build_env.db.execute(
        "SELECT id FROM sem_entities WHERE key = 'TPL_0'"
    ).fetchone()[0]
    build_env.db.execute(
        "INSERT INTO sem_aliases(org_id, entity_id, alias, alias_norm, kind)"
        " VALUES(?, ?, '人工别名零', '人工别名零', 'manual')", (ORG, eid))
    build_env.db.commit()
    r2 = run_build(build_env.backend, ORG, settings=build_env.settings)
    assert r2["status"] == "ready"
    assert r2["dict_rev"] != r1["dict_rev"], "别名变更必须产生新 dict_rev"
    rows = _rows(build_env)
    assert len(rows) == 2
    # 当前指针 = 最新 ready
    current = build_env.backend.sem_current_build(ORG)
    assert current["id"] == r2["build_id"] and current["dict_rev"] == r2["dict_rev"]


def test_tc_build_01_embed_model_label_enters_dict_rev(build_env, tmp_path) -> None:
    """embed_model 标签进 dict_rev 输入（任务书 A.1 硬要求 / #42 P1-2）：
    同一快照换嵌入模型标签 → 新 rev 必然构建（「相同跳过」失效）。"""
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.build import run_build

    r1 = run_build(build_env.backend, ORG, settings=build_env.settings)
    other = Settings(environment="test", data_dir=tmp_path, embed_model="other-embed")
    r2 = run_build(build_env.backend, ORG, settings=other)
    assert r2["status"] == "ready"
    assert r2["dict_rev"] != r1["dict_rev"]
    assert build_env.backend.sem_current_build(ORG)["id"] == r2["build_id"]


# ---- TC-BUILD-03：原子切换 / 失败不切 / outbox 事件 ----


def test_build_failure_keeps_old_ready_current(build_env, monkeypatch) -> None:
    """构建失败（切换阶段异常）→ 新行 failed、旧 ready 继续=当前（失败不切指针）。"""
    from knowledge_lattice.core.semantic.build import run_build

    r1 = run_build(build_env.backend, ORG, settings=build_env.settings)
    eid = build_env.db.execute(
        "SELECT id FROM sem_entities WHERE key = 'TPL_0'"
    ).fetchone()[0]
    build_env.db.execute(
        "INSERT INTO sem_aliases(org_id, entity_id, alias, alias_norm, kind)"
        " VALUES(?, ?, '变更别名', '变更别名', 'manual')", (ORG, eid))
    build_env.db.commit()

    def boom(*a, **kw):
        raise RuntimeError("switch exploded (simulated)")

    monkeypatch.setattr(build_env.backend, "sem_switch_build_ready", boom)
    with pytest.raises(RuntimeError, match="switch exploded"):
        run_build(build_env.backend, ORG, settings=build_env.settings)

    rows = _rows(build_env)
    assert len(rows) == 2
    assert rows[0][2] == "ready" and rows[1][2] == "failed"
    current = build_env.backend.sem_current_build(ORG)
    assert current["id"] == r1["build_id"], "失败后旧 ready 保留为当前（T-S12 骨架）"
    failed_stats = build_env.db.execute(
        "SELECT stats_json FROM sem_builds WHERE status = 'failed'"
    ).fetchone()[0]
    assert "switch exploded" in json.loads(failed_stats).get("error", "")


def test_build_success_stats_and_outbox_event(build_env) -> None:
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_BUILD

    r = run_build(build_env.backend, ORG, settings=build_env.settings)
    stats = r["stats"]
    assert stats["entities"] == 10          # tpl_snapshot(5) = 5 模板 + 5 字段
    assert stats["aliases"] > 0
    assert stats["relations"] == 5          # has_field ×5
    assert stats["entities_by_type"]["template"] == 5
    assert stats["relations_by_type"]["has_field"] == 5

    events = build_env.db.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
        (EVENT_SEMANTIC_BUILD,),
    ).fetchall()
    assert len(events) == 1
    payload = json.loads(events[0][0])
    assert payload["status"] == "ready" and payload["build_id"] == r["build_id"]
    assert payload["dict_rev"] == r["dict_rev"]


def test_build_skip_emits_outbox_event(build_env) -> None:
    """跳过也留痕（status=skipped——运维可追溯「为什么没新版本」）。"""
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_BUILD

    run_build(build_env.backend, ORG, settings=build_env.settings)
    r2 = run_build(build_env.backend, ORG, settings=build_env.settings)
    assert r2["status"] == "skipped"
    events = build_env.db.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
        (EVENT_SEMANTIC_BUILD,),
    ).fetchall()
    statuses = [json.loads(p[0])["status"] for p in events]
    assert statuses == ["ready", "skipped"]


def test_build_retry_after_failure_same_rev(build_env, monkeypatch) -> None:
    """失败行同 rev 重试：UNIQUE(org,dict_rev) 下 upsert 复用行、重试可 ready。"""
    from knowledge_lattice.core.semantic.build import run_build

    eid = build_env.db.execute(
        "SELECT id FROM sem_entities WHERE key = 'TPL_0'"
    ).fetchone()[0]
    build_env.db.execute(
        "INSERT INTO sem_aliases(org_id, entity_id, alias, alias_norm, kind)"
        " VALUES(?, ?, '重试别名', '重试别名', 'manual')", (ORG, eid))
    build_env.db.commit()

    calls = {"n": 0}
    orig = build_env.backend.sem_switch_build_ready

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first attempt boom")
        return orig(*a, **kw)

    monkeypatch.setattr(build_env.backend, "sem_switch_build_ready", flaky)
    with pytest.raises(RuntimeError, match="first attempt boom"):
        run_build(build_env.backend, ORG, settings=build_env.settings)
    monkeypatch.setattr(build_env.backend, "sem_switch_build_ready", orig)

    r2 = run_build(build_env.backend, ORG, settings=build_env.settings)
    assert r2["status"] == "ready"
    assert len(_rows(build_env)) == 1, "同 rev 重试复用同一 build 行（不堆 failed 尸体）"
