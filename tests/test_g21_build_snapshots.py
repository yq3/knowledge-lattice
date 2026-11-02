"""m2s-5 G-21 方案 A：build 快照附表（sem_build_snapshots——迁移 0008 双方言）。

- get_annotator/render_l0 按 **current build id** 取快照构建实例；
  无快照回退 live + 告警（0008 之前 ready 行的兼容路径——回退告警保留）；
- **冷缓存/重启后服务 build 产物而非 live**（G-21 反转——m2s-4 方案 B
  「钉死 live」用例随本段按新语义改写）：
  ① 重启窗口 rev 锚点失真消除（live 领先 last ready 不再被服务）；
  ② 评测门槛拦下的词典不再于重启后被服务（failed 不切 ready 的治理语义
    跨进程生命周期持久——TC-BUILD-04/G-21 收口）；
- 快照与 ready 切换**同一事务**（switch/reactivate 的 snapshot_json 参数）
  ——ready 可见时快照必已在位。
"""

from __future__ import annotations

import json

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"


@pytest.fixture()
def env(backend, tmp_path):
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path,
                        semantic_eval_golden_path="")
    return SimpleNamespace(db=backend, backend=backend.make_backend(),
                           settings=settings)


def _sync(env, records, *, adapter="template_center", now=NOW):
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.core.semantic.sync import run_sync

    return run_sync(env.backend, ORG, FakeSourceAdapter(adapter, records),
                    settings=env.settings, snapshot=list(records), now=now)


def _build(env, **kw):
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build

    clear_annotator_cache()
    return run_build(env.backend, ORG, settings=env.settings, **kw)


# ---- 迁移 0008：附表落库（双方言） ----


def test_migration_0008_sem_build_snapshots_table(env) -> None:
    """0008 双方言迁移：sem_build_snapshots(build_id PK→sem_builds CASCADE,
    snapshot_json) 在场。"""
    tables = env.db.table_names()
    assert "sem_build_snapshots" in tables


# ---- ready 写快照 + 冷缓存服务 build 产物（G-21 反转主用例） ----


def test_ready_writes_snapshot_cold_cache_serves_build_product(env) -> None:
    """ready 切换同事务写快照附表；live 前进（新 sync 未构建）后**清缓存
    （=重启形态）→ 服务 build 快照产物**：新词典不可命中、rev 仍 current
    ready rev——m2s-4 方案 B「服务 live+旧 rev」行为反转（G-21 收口）。"""
    from knowledge_lattice.core.semantic.annotator import (
        annotate_text, clear_annotator_cache, get_annotator,
    )
    from knowledge_lattice.core.semantic.records import EntityRecord

    _sync(env, [EntityRecord(type="concept", key="c.base", name="基线概念")])
    r1 = _build(env)
    assert r1["status"] == "ready"
    build_id = r1["build_id"]

    # 快照附表在位且内容 = 构建时点快照（最小 JSON——实体/别名/关系）
    snap_json = env.backend.sem_load_build_snapshot(ORG, build_id)
    assert snap_json, "ready 构建须落快照附表（与切换同事务）"
    snap = json.loads(snap_json)
    assert any(e["key"] == "c.base" for e in snap["entities"])
    assert snap["aliases"] and snap["relations"] is not None

    # live 前进（新 sync、尚未构建）——冷缓存（重启形态）
    _sync(env, [EntityRecord(type="concept", key="c.base", name="基线概念"),
                EntityRecord(type="concept", key="c.new", name="窗口新概念")])
    clear_annotator_cache()

    ann, rev = get_annotator(env.backend, ORG, env.settings)
    assert rev == r1["dict_rev"]
    # 反转断言：服务 **build 产物**——窗口新概念（仅 live 有）不可命中
    assert ann.annotate("窗口新概念是什么")["mentions"] == []
    assert ann.annotate("基线概念说明")["mentions"]
    out = annotate_text(env.backend, env.settings, ORG, "窗口新概念是什么")
    assert out["mentions"] == [] and out["dict_rev"] == r1["dict_rev"]

    # 重建 ready r2 后冷缓存 → 服务 r2 快照（新概念可命中、rev=r2）
    r2 = _build(env)
    assert r2["status"] == "ready" and r2["dict_rev"] != r1["dict_rev"]
    clear_annotator_cache()
    out2 = annotate_text(env.backend, env.settings, ORG, "窗口新概念是什么")
    assert out2["mentions"] and out2["dict_rev"] == r2["dict_rev"]
    # 快照附表按 build 幂等隔离：r1/r2 各自快照互不覆盖
    assert env.backend.sem_load_build_snapshot(ORG, build_id)


# ---- 评测拦下（failed 不切 ready）：冷缓存不服务被拦词典（G-21 ②收口） ----


def test_eval_blocked_cold_cache_does_not_serve_gated_dict(env) -> None:
    """评测拦下的词典（failed 不切 ready）重启后**不再被服务**——annotate
    服务 last ready 快照（被拦概念零命中）+ 响应 ready rev：TC-BUILD-04
    「拦截治理」语义跨进程生命周期持久（G-21 问题②收口）。"""
    from knowledge_lattice.core.semantic.annotator import (
        annotate_text, clear_annotator_cache,
    )
    from knowledge_lattice.core.semantic.records import EntityRecord

    _sync(env, [EntityRecord(type="concept", key="c.base", name="基线概念")])
    r1 = _build(env, eval_runner=lambda a, s: {
        "precision": 0.99, "recall": 0.95, "ambiguity": 0.95, "neg_fp": 0.0,
        "items": 100})
    assert r1["status"] == "ready"

    _sync(env, [EntityRecord(type="concept", key="c.base", name="基线概念"),
                EntityRecord(type="concept", key="c.gated", name="被拦概念")])
    r2 = _build(env, eval_runner=lambda a, s: {
        "precision": 0.90, "recall": 0.95, "ambiguity": 0.95, "neg_fp": 0.0,
        "items": 100})     # 触绝对门槛 → failed 不切 ready
    assert r2["status"] == "failed"
    assert env.backend.sem_current_build(ORG)["dict_rev"] == r1["dict_rev"]
    # failed 行无快照（不切 ready 不产服务面产物）
    assert env.backend.sem_load_build_snapshot(ORG, r2["build_id"]) is None

    clear_annotator_cache()   # 重启/冷缓存形态
    out = annotate_text(env.backend, env.settings, ORG, "被拦概念的口径")
    assert out["mentions"] == [], "冷缓存不得服务被拦词典（G-21 反转）"
    assert out["dict_rev"] == r1["dict_rev"]
    # last ready 产物照常服务
    ok = annotate_text(env.backend, env.settings, ORG, "基线概念说明")
    assert ok["mentions"] and ok["dict_rev"] == r1["dict_rev"]


# ---- 无快照回退 live + 告警保留（0008 前存量 ready 行的兼容路径） ----


def test_missing_snapshot_falls_back_live_with_warning(env, caplog) -> None:
    """current ready 行无快照（0008 前存量/快照被清理）→ 回退 live 快照
    + 告警（G-21 回退告警保留——best-effort 兼容面，非服务语义）。"""
    import logging

    from knowledge_lattice.core.semantic.annotator import (
        clear_annotator_cache, get_annotator,
    )
    from knowledge_lattice.core.semantic.records import EntityRecord

    _sync(env, [EntityRecord(type="concept", key="c.base", name="基线概念")])
    r1 = _build(env)
    assert r1["status"] == "ready"

    _sync(env, [EntityRecord(type="concept", key="c.base", name="基线概念"),
                EntityRecord(type="concept", key="c.new", name="窗口新概念")])
    # 造「无快照」形态：直删附表行（模拟 0008 前存量 ready）
    env.db.execute("DELETE FROM sem_build_snapshots WHERE build_id = ?",
                   (r1["build_id"],))
    clear_annotator_cache()

    with caplog.at_level(logging.WARNING, logger="knowledge_lattice.core.semantic.annotator"):
        ann, rev = get_annotator(env.backend, ORG, env.settings)
    assert rev == r1["dict_rev"]
    # 回退 live：窗口新概念可命中（兼容 best-effort——m2s-4 方案 B 行为）
    assert ann.annotate("窗口新概念是什么")["mentions"]
    assert any("snapshot" in r.message.lower() or "fallback" in r.message.lower()
               for r in caplog.records), "回退 live 须告警（G-21 回退告警保留）"
