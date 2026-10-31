"""m2s-4 构建报告与评测回归门禁（A4/A5——TC-BUILD-02·04 + TC-SEV-02 联动）：

- TC-BUILD-02 半句：AC 自动机仅收 match_mode IN ('exact','context') 别名
  （fuzzy_only 不进——防误报）；构建报告含歧义别名/孤立节点/断链关系/评测指标；
- A4 报告面（GET /semantic/builds/{id}/report 的 core 数据源）：实体/别名计数、
  自动机规模与构建耗时、dict_rev 各分量、缺源警告；
- TC-BUILD-04：评测指标较上一版降 >2pp 不切 ready（需人工确认）；
  TC-SEV-02 绝对门槛：precision <0.95 等不切 ready。
"""

from __future__ import annotations

import json

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"


@pytest.fixture()
def benv(backend, tmp_path):
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


def _seed(entities, relations=()):
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

    out = [EntityRecord(**e) if isinstance(e, dict) else e for e in entities]
    out.extend(RelationRecord(**r) for r in relations)
    return out


def _build(env, **kw):
    from knowledge_lattice.core.semantic.build import run_build

    return run_build(env.backend, ORG, settings=env.settings, **kw)


def _stats(env, build_id: int) -> dict:
    stats = env.backend.sem_get_build(ORG, build_id)["stats_json"]
    return stats if isinstance(stats, dict) else json.loads(stats)


def _add_alias(env, key: str, alias: str, *, kind="manual",
               mode="exact", weight=1.0) -> None:
    from knowledge_lattice.core.semantic.norm import normalize_alias

    row = env.backend.sem_entity_by_key(
        ORG, key.split(":")[0], key.split(":", 1)[1])
    env.db.execute(
        "INSERT INTO sem_aliases(org_id, entity_id, alias, alias_norm, kind,"
        " match_mode, weight) VALUES(?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(org_id, entity_id, alias_norm) DO NOTHING",
        (ORG, row["id"], alias, normalize_alias(alias), kind, mode, weight))
    env.db.commit()


# ---- TC-BUILD-02：自动机只收 exact/context（fuzzy_only 不进） + 报告字段 ----


def test_tc_build_02_automaton_only_exact_context(benv) -> None:
    _sync(benv, _seed([
        {"type": "concept", "key": "vat.x", "name": "进项概念"},
        {"type": "table", "key": "ods.t1", "name": "进项明细表"},
    ]))
    _add_alias(benv, "concept:vat.x", "容错面", mode="fuzzy_only")
    _add_alias(benv, "concept:vat.x", "抵扣面")
    result = _build(benv)
    assert result["status"] == "ready"
    stats = _stats(benv, result["build_id"])
    auto = stats["ac_automaton"]
    assert {"keys", "nodes", "build_ms", "skipped_fuzzy_only"} <= set(auto)
    assert auto["skipped_fuzzy_only"] == 1        # fuzzy_only 不进自动机
    assert auto["keys"] >= 3                      # 两 name + 抵扣面
    # 语义面复核：fuzzy_only 面永不命中
    from knowledge_lattice.core.semantic.annotator import (
        Annotator, clear_annotator_cache, get_annotator,
    )

    clear_annotator_cache()
    ann, _rev = get_annotator(benv.backend, ORG, benv.settings)
    assert ann.annotate("容错面出现")["mentions"] == []
    assert ann.annotate("抵扣面出现")["mentions"]
    assert isinstance(ann, Annotator)


def test_report_counts_components_missing_sources(benv) -> None:
    """A4：计数 / 自动机规模与耗时 / dict_rev 分量 / 缺源警告进报告 stats。"""
    _sync(benv, _seed([
        {"type": "concept", "key": "vat.x", "name": "进项概念"},
    ]))
    result = _build(benv)
    stats = _stats(benv, result["build_id"])
    assert stats["entities"] == 1
    assert stats["entities_by_type"] == {"concept": 1}
    assert stats["aliases"] >= 1
    comps = stats["dict_rev_components"]
    assert {"entities", "aliases", "relations", "yaml_rev",
            "embed_model"} <= set(comps)
    assert all(comps[k] for k in ("entities", "aliases", "relations"))
    assert isinstance(comps["yaml_rev"], str) and isinstance(
        comps["embed_model"], str)
    missing = {w["source"] for w in stats["missing_sources"]}
    assert {"metadata", "scenario_config", "report_center", "yaml"} <= missing
    assert "template_center" not in missing          # 有数据源不警告
    # 报告聚合面（core build_report——REST /builds/{id}/report 数据源）
    from knowledge_lattice.core.semantic.build import build_report

    report = build_report(benv.backend, ORG, result["build_id"])
    assert report["build_id"] == result["build_id"]
    assert report["counts"]["entities"] == 1
    assert report["ac_automaton"]["keys"] >= 1
    assert report["dict_rev_components"]["entities"]
    assert {"source", "reason"} <= set(report["missing_sources"][0])


def test_report_broken_relations(benv) -> None:
    """断链关系（active 关系指向 missing 端点——G-15/N4 中间态）进构建报告。"""
    recs = _seed([
        {"type": "template", "key": "TPL_A", "name": "模板甲"},
        {"type": "table", "key": "ods.t_a", "name": "表甲"},
    ], relations=[{"src": ("template", "TPL_A"), "rel_type": "backed_by",
                   "dst": ("table", "ods.t_a")}])
    _sync(benv, recs)
    # 模拟端点 missing 窗口（N4 中间态：实体 missing、关系保持 active——
    # 关系级消失由下一轮同源 sync 收口，此处直接落状态面）
    benv.db.execute(
        "UPDATE sem_entities SET status = 'missing'"
        " WHERE org_id = ? AND key = 'ods.t_a'", (ORG,))
    benv.db.commit()
    result = _build(benv)
    stats = _stats(benv, result["build_id"])
    assert stats["broken_relations"]["count"] >= 1


# ---- TC-BUILD-04 / TC-SEV-02：评测回归与绝对门槛 ----


def _metrics(p=0.97, r=0.92, a=0.9, n=0.0, items=100):
    return {"precision": p, "recall": r, "ambiguity": a, "neg_fp": n,
            "items": items}


def test_tc_build_04_regression_blocks_ready(benv) -> None:
    """指标较上一版降 >2pp（0.98→0.955，均过绝对门槛——回归独立成立）不切
    ready（TC-BUILD-04/TC-SEV-02；用例文档示例 0.96→0.93 同时触绝对门槛，
    此处构造只触回归面的样本）。"""
    _sync(benv, _seed([{"type": "concept", "key": "vat.x", "name": "概念一"}]))
    r1 = _build(benv, eval_runner=lambda a, s: _metrics(p=0.98))
    assert r1["status"] == "ready"

    _sync(benv, _seed([{"type": "concept", "key": "vat.x", "name": "概念二"}]))
    r2 = _build(benv, eval_runner=lambda a, s: _metrics(p=0.955))
    assert r2["status"] == "failed"
    assert r2["stats"]["eval"]["regression"] is True
    # 旧版本继续服务（current 不动）
    current = benv.backend.sem_current_build(ORG)
    assert current["dict_rev"] == r1["dict_rev"]


def test_eval_absolute_threshold_blocks_ready(benv) -> None:
    """绝对门槛：precision <0.95 不切 ready（TC-SEV-02 门槛四指标）。"""
    _sync(benv, _seed([{"type": "concept", "key": "vat.x", "name": "概念一"}]))
    r1 = _build(benv, eval_runner=lambda a, s: _metrics(p=0.99))
    assert r1["status"] == "ready"

    _sync(benv, _seed([{"type": "concept", "key": "vat.x", "name": "概念二"}]))
    r2 = _build(benv, eval_runner=lambda a, s: _metrics(p=0.94))
    assert r2["status"] == "failed"
    assert r2["stats"]["eval"]["below_threshold"] is True
    assert benv.backend.sem_current_build(ORG)["dict_rev"] == r1["dict_rev"]


def test_eval_meeting_thresholds_ready_and_metrics_in_report(benv) -> None:
    _sync(benv, _seed([{"type": "concept", "key": "vat.x", "name": "概念一"}]))
    r = _build(benv, eval_runner=lambda a, s: _metrics(p=0.97, r=0.93))
    assert r["status"] == "ready"
    stats = _stats(benv, r["build_id"])
    assert stats["eval"]["metrics"]["precision"] == pytest.approx(0.97)
    assert stats["eval"]["metrics"]["recall"] == pytest.approx(0.93)

    from knowledge_lattice.core.semantic.build import build_report

    report = build_report(benv.backend, ORG, r["build_id"])
    assert report["eval"]["metrics"]["precision"] == pytest.approx(0.97)
    assert {"precision", "recall", "ambiguity", "neg_fp"} <= set(
        report["eval"]["thresholds"])


def test_eval_regression_allows_within_2pp(benv) -> None:
    """≤2pp 回归不拦截（0.97→0.955 降 1.5pp，且过绝对门槛——正常切 ready）。"""
    _sync(benv, _seed([{"type": "concept", "key": "vat.x", "name": "概念一"}]))
    assert _build(benv, eval_runner=lambda a, s: _metrics(
        p=0.97))["status"] == "ready"
    _sync(benv, _seed([{"type": "concept", "key": "vat.x", "name": "概念二"}]))
    r2 = _build(benv, eval_runner=lambda a, s: _metrics(p=0.955))
    assert r2["status"] == "ready"      # 降 1.5pp ≤ 2pp：放行
