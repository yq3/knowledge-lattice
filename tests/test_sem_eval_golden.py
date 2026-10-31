"""m2s-4 识别评测集与门槛（A5——TC-SEV-01/02）：

- TC-SEV-01 评测集构建规格：eval/semantic_golden.jsonl 落仓库——150~200 条、
  负样本 ~20%、四类覆盖（精确/别名/缩写/歧义/上下文短别名）、标注规范随集
  （eval/semantic_golden.README.md）；条目自洽（span 切片非空、key 可解析到
  参考词典、同条目 span 不重叠）；
- TC-SEV-02 构建回归门槛：参考词典 org 跑 semantic_build 自动跑评测集
  （指标进构建报告）；门槛四指标：precision ≥0.95 / recall ≥0.80 /
  歧义 ≥0.85（只统计歧义样本）/ 负样本误报 ≤0.05——双后端一致。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from helpers import seed_org

ORG = "org:tax"
EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"
GOLDEN = EVAL_DIR / "semantic_golden.jsonl"
README = EVAL_DIR / "semantic_golden.README.md"
NOW = "2026-10-31 09:00:00"

KINDS = {"pos_exact", "pos_alias", "pos_abbr", "pos_ambiguous",
         "pos_context", "neg"}


def _load_seed():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "eval_semantic_seed", EVAL_DIR / "semantic_seed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_semantic_seed"] = mod
    spec.loader.exec_module(mod)
    return mod


def _items() -> list[dict]:
    return [json.loads(line)
            for line in GOLDEN.read_text(encoding="utf-8").split("\n")
            if line.strip()]


# ---- TC-SEV-01：集合格式与标注规范 ----


def test_tc_sev_01_set_size_and_neg_ratio() -> None:
    items = _items()
    assert 150 <= len(items) <= 200, f"评测集 {len(items)} 条越界（150~200）"
    neg = sum(1 for i in items if i["kind"] == "neg")
    assert 0.10 <= neg / len(items) <= 0.30, "负样本占比应 ~20%"


def test_tc_sev_01_coverage_and_annotation_spec() -> None:
    items = _items()
    kinds = {i["kind"] for i in items}
    assert kinds == KINDS, f"覆盖缺口：{KINDS - kinds}"
    assert README.exists(), "标注规范须随集落仓库（TC-SEV-01）"
    # 每条：qid 唯一 / lang / labels 结构
    qids = [i["qid"] for i in items]
    assert len(qids) == len(set(qids))
    for i in items:
        assert i["lang"] in ("zh", "en", "mix")
        for key, s, e in i["labels"]:
            assert isinstance(key, str) and ":" in key
            assert 0 <= s < e <= len(i["text"]), f"span 越界 {i['qid']}"
            assert i["text"][s:e].strip(), f"空切片 {i['qid']}"
        spans = sorted((s, e) for _, s, e in i["labels"])
        for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
            assert e1 <= s2, f"span 重叠 {i['qid']}"
        if i["kind"] == "neg":
            assert i["labels"] == [], f"负样本不应带标注 {i['qid']}"


def test_tc_sev_01_labels_resolve_to_reference_dictionary() -> None:
    """全部正样本 key 可解析到参考词典（eval/semantic_seed.py 单一真相源）。"""
    seed = _load_seed()
    known = set(seed.ALL_ENTITY_KEYS)
    items = _items()
    labeled = {k for i in items for k, _, _ in i["labels"]}
    unresolved = labeled - known
    assert not unresolved, f"标注 key 不在参考词典：{sorted(unresolved)}"
    # 参考词典的绝大多数实体都被至少一条正样本覆盖（召回面代表性）
    covered = labeled
    assert len(covered) >= len(known) * 0.7, \
        f"参考词典覆盖不足：{len(covered)}/{len(known)}"


# ---- TC-SEV-02：构建自动跑评测 + 门槛四指标（双后端） ----


@pytest.fixture()
def refenv(backend, tmp_path):
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path,
                        semantic_eval_golden_path=str(GOLDEN))
    b = backend.make_backend()
    seed = _load_seed()
    seed.seed_reference_org(b, ORG, settings, repo_dir=tmp_path / "yamlrepo")
    return SimpleNamespace(db=backend, backend=b, settings=settings)


def test_tc_sev_02_metrics_meet_thresholds_and_in_report(refenv) -> None:
    """参考词典构建 → 自动评测 → 四指标达标且进构建报告（双后端一致）。"""
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import build_report, run_build

    clear_annotator_cache()
    result = run_build(refenv.backend, ORG, settings=refenv.settings)
    assert result["status"] == "ready", result
    stats_json = refenv.backend.sem_get_build(
        ORG, result["build_id"])["stats_json"]
    stats = stats_json if isinstance(stats_json, dict) else json.loads(stats_json)
    ev = stats["eval"]
    assert "skipped" not in ev, f"评测被跳过：{ev}"
    m = ev["metrics"]
    assert m["items"] >= 100
    assert m["precision"] >= 0.95, m
    assert m["recall"] >= 0.80, m
    assert m["ambiguity"] >= 0.85, m
    assert m["neg_fp"] <= 0.05, m
    # 报告面（TC-SEV-02 预期半句：指标进构建报告）
    report = build_report(refenv.backend, ORG, result["build_id"])
    assert report["eval"]["metrics"]["precision"] == m["precision"]
    assert report["eval"]["thresholds"]["precision"] == pytest.approx(0.95)


def test_tc_sev_02_eval_deterministic_double_build(refenv) -> None:
    """非 Flaky：同词典重建（rev 不变跳过）→ 指标可复算一致。"""
    from knowledge_lattice.core.semantic.evalrun import (
        load_golden, run_recognition_eval,
    )
    from knowledge_lattice.core.semantic.annotator import Annotator

    snapshot = refenv.backend.sem_active_snapshot(ORG)
    ann = Annotator(snapshot)
    items = load_golden(GOLDEN)
    m1 = run_recognition_eval(ann, items, snapshot)
    m2 = run_recognition_eval(ann, items, snapshot)
    assert m1 == m2
    assert m1["precision"] >= 0.95 and m1["recall"] >= 0.80
