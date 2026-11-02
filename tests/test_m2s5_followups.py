"""m2s-5 挂账收编（m2s-4 R3 移交——G-21 R3 终审补登记项）。

- **B1 ambiguity 分子收紧**：`ambiguous=true` 的主候选命中不再计「正确」
  （严格口径——未消解定案不算答对）；黄金集同步（参考集 18/20=0.90 仍过
  门 ≥0.85 的收紧前口径 + B2 显式缺省主读后 20/20）；
- **B2 歧义缺省读法显式化**：YAML 覆盖层增 `default_reading` 字段（本实体
  为这些共享别名的缺省主读——消解实现不再依赖第一候选 (weight,id) 序）；
  消解第⑤级 resolved_by='default'；README 两无佐证 qid（s109/s117）列出。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"
EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


# ---- B1：ambiguity 分子收紧（ambiguous=true 主候选命中不计正确） ----


class _AmbStubAnnotator:
    """可控 stub：命中标注实体但按开关标 ambiguous——B1 口径探针。"""

    def __init__(self, ambiguous: bool):
        self.ambiguous = ambiguous

    def annotate(self, text: str, **kw) -> dict:
        start = text.index("甲")
        return {"mentions": [{"span": [start, start + 1], "surface": "甲",
                              "entity_key": "concept:amb.right",
                              "ambiguous": self.ambiguous}],
                "candidates": []}


def _amb_snapshot():
    return {
        "entities": [
            {"id": 1, "type": "concept", "key": "amb.right", "name": "甲正",
             "parent_id": None, "attrs_json": "{}", "sensitivity": "normal",
             "curated_json": "{}", "curated_rev": None},
            {"id": 2, "type": "concept", "key": "amb.wrong", "name": "甲误",
             "parent_id": None, "attrs_json": "{}", "sensitivity": "normal",
             "curated_json": "{}", "curated_rev": None},
        ],
        "aliases": [
            {"entity_id": 1, "alias": "甲", "alias_norm": "甲", "kind": "manual",
             "match_mode": "exact", "weight": 1.0},
            {"entity_id": 2, "alias": "甲", "alias_norm": "甲", "kind": "manual",
             "match_mode": "exact", "weight": 1.0},
        ],
        "relations": [],
    }


def _items20():
    return [{"qid": f"a{i:03d}", "kind": "pos_ambiguous", "lang": "zh",
             "text": f"问题甲{i:02d}怎么处理",
             "labels": [["concept:amb.right",
                         2 + (1 if i >= 100 else 0), 3 + (1 if i >= 100 else 0)]]}
            for i in range(1, 21)]


def test_b1_ambiguous_primary_candidate_not_counted_correct() -> None:
    """严格口径：ambiguous=true 的主候选命中（span+实体双匹配）**不计**正确
    ——歧义消解未定案不算答对；定案（ambiguous=false）才计。"""
    from knowledge_lattice.core.semantic.evalrun import run_recognition_eval

    snap = _amb_snapshot()
    items = _items20()
    # 未定案（ambiguous=true）：20 命中全对也不计 → ambiguity=0.0
    m_amb = run_recognition_eval(_AmbStubAnnotator(ambiguous=True), items, snap)
    assert m_amb["_counts"]["ambiguous_labeled"] == 20
    assert m_amb["_counts"]["ambiguous_correct"] == 0, \
        "ambiguous=true 主候选命中不得计正确（B1 收紧）"
    assert m_amb["ambiguity"] == 0.0
    # 定案（ambiguous=false）才计 → 20/20=1.0
    m_ok = run_recognition_eval(_AmbStubAnnotator(ambiguous=False), items, snap)
    assert m_ok["_counts"]["ambiguous_correct"] == 20
    assert m_ok["ambiguity"] == pytest.approx(1.0)
    # precision/recall 不受 B1 影响（双匹配照计——主候选确有命中）
    assert m_amb["precision"] == pytest.approx(1.0)


def test_b1_golden_strict_denominator_and_threshold() -> None:
    """黄金集在参考词典上实测（严格口径 + B2 缺省主读就位）：歧义分母 20、
    ambiguity 达标（≥0.85）——门槛断言与实现口径同步。"""
    import importlib.util
    import sys

    from knowledge_lattice.core.semantic.annotator import Annotator
    from knowledge_lattice.core.semantic.evalrun import (
        EVAL_THRESHOLDS, load_golden, run_recognition_eval,
    )

    spec = importlib.util.spec_from_file_location(
        "eval_semantic_seed_m2s5", EVAL_DIR / "semantic_seed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_semantic_seed_m2s5"] = mod
    spec.loader.exec_module(mod)

    import tempfile

    backend = None
    from knowledge_lattice.store.sqlite import connect, migrate_db

    tmp = Path(tempfile.mkdtemp())
    conn = connect(tmp / "l.db")
    migrate_db(conn)
    seed_org(conn, ORG)
    from knowledge_lattice.config import Settings
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    b = SqliteBackend(conn)
    settings = Settings(environment="test", data_dir=tmp)
    mod.seed_reference_org(b, ORG, settings, repo_dir=tmp / "yamlrepo")
    snapshot = b.sem_active_snapshot(ORG)
    ann = Annotator(snapshot)
    items = load_golden(EVAL_DIR / "semantic_golden.jsonl")
    m = run_recognition_eval(ann, items, snapshot)
    assert m["_counts"]["ambiguous_labeled"] == 20, "歧义 span 分母 20（P2-2 口径保持）"
    assert m["ambiguity"] >= EVAL_THRESHOLDS["ambiguity"], \
        f"严格口径下仍须过门: {m['ambiguity']} < {EVAL_THRESHOLDS['ambiguity']}"


# ---- B2：歧义缺省读法显式化（YAML default_reading） ----


@pytest.fixture()
def env(backend, tmp_path):
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path,
                        semantic_eval_golden_path="")
    return SimpleNamespace(db=backend, backend=backend.make_backend(),
                           settings=settings, repo=tmp_path / "repo")


def _yaml_sync(env, files: dict, **kw):
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    env.repo.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = env.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return run_yaml_sync(env.backend, ORG,
                         YamlRepoAdapter(SourceConfig(endpoint=str(env.repo))),
                         settings=env.settings, now=NOW, **kw)


AMBIG_YAML = (
    "- id: concept:amb.primary\n  name: 歧义主读\n  owner: o\n"
    "  aliases: [{value: 歧面, match_mode: exact}]\n"
    "  default_reading: [歧面]\n"
    "  definition: 主读实体定义。\n"
    "- id: concept:amb.other\n  name: 歧义另读\n  owner: o\n"
    "  aliases: [{value: 歧面, match_mode: exact}]\n"
    "  definition: 另读实体定义。\n"
)


def test_b2_default_reading_resolves_fifth_level(env) -> None:
    """显式缺省主读声明：无佐证歧义命中按 default_reading 定案
    （resolved_by='default'、非 ambiguous、confidence 上限 0.9——人工显式
    配置证据档；消解不再依赖第一候选 (weight,id) 序）。"""
    from knowledge_lattice.core.semantic.annotator import (
        Annotator, clear_annotator_cache,
    )
    from knowledge_lattice.core.semantic.build import run_build

    _yaml_sync(env, {"concepts/amb.yaml": AMBIG_YAML})
    clear_annotator_cache()
    r = run_build(env.backend, ORG, settings=env.settings)
    assert r["status"] == "ready", r

    snap = env.backend.sem_active_snapshot(ORG)
    ann = Annotator(snap)
    out = ann.annotate("歧面是什么意思")
    assert len(out["mentions"]) == 1
    m = out["mentions"][0]
    assert m["resolved_by"] == "default", "缺省主读定案（B2 第⑤级）"
    assert m["ambiguous"] is False
    assert m["entity_key"] == "concept:amb.primary"
    assert m["confidence"] <= 0.9, "default 档 confidence 上限 0.9（非确证）"
    # 消歧证据更高档不受影响：共现① 仍先于 default（同句关系佐证定案）
    out2 = ann.annotate("歧面与歧义另读的关系")
    # 「歧义另读」规范名确定命中 → 共现①把「歧面」定到有关系的另读实体


def test_b2_no_declaration_stays_ambiguous(env) -> None:
    """对照组：无 default_reading 声明的共享别名——无佐证时仍返回全部候选
    ambiguous=true（缺省主读不落回隐式第一候选——显式化语义）。"""
    from knowledge_lattice.core.semantic.annotator import (
        Annotator, clear_annotator_cache,
    )
    from knowledge_lattice.core.semantic.build import run_build

    _yaml_sync(env, {"concepts/amb.yaml": AMBIG_YAML.replace(
        "  default_reading: [歧面]\n", "")})
    clear_annotator_cache()
    r = run_build(env.backend, ORG, settings=env.settings)
    assert r["status"] == "ready", r
    snap = env.backend.sem_active_snapshot(ORG)
    ann = Annotator(snap)
    out = ann.annotate("歧面是什么意思")
    assert out["mentions"] and out["mentions"][0]["ambiguous"] is True, \
        "无声明不落回隐式第一候选——仍 ambiguous（G-21 R3 消解依赖显式化）"
    assert out["candidates"], "全部候选照出"


def test_b2_ci_validates_default_reading(tmp_path) -> None:
    """CI 校验：default_reading 值须是本实体声明的别名/缩写；同一缺省主读
    不得多实体重复声明（唯一性——配置错误前置拦截）。"""
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus, \
        validate_corpus

    repo = tmp_path / "repo"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "bad.yaml").write_text(
        "- id: concept:x\n  name: X\n  owner: o\n"
        "  aliases: [共享词]\n  default_reading: [未声明的别名]\n",
        encoding="utf-8")
    issues = validate_corpus(load_corpus(repo))
    assert any("default_reading" in i.message for i in issues
               if i.severity == "error"), "声明值不在别名面须报错"

    (repo / "concepts" / "dup.yaml").write_text(
        "- id: concept:a\n  name: A\n  owner: o\n"
        "  aliases: [双声明]\n  default_reading: [双声明]\n"
        "- id: concept:b\n  name: B\n  owner: o\n"
        "  aliases: [双声明]\n  default_reading: [双声明]\n",
        encoding="utf-8")
    issues2 = validate_corpus(load_corpus(repo))
    assert any("default_reading" in i.message and "唯一" in i.message
               for i in issues2 if i.severity == "error"), \
        "同一缺省主读多实体声明须报错（唯一性）"


def test_b2_reference_seed_declares_default_readings() -> None:
    """参考词典 seed：留抵→期末留抵税额、税率→增值税税率的缺省主读显式
    声明（README 两无佐证 qid s109/s117 的读法依据——curated 落库面）。"""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "eval_semantic_seed_dr", EVAL_DIR / "semantic_seed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_semantic_seed_dr"] = mod
    spec.loader.exec_module(mod)

    text = mod.YAML_FILES["concepts/vat_core.yaml"]
    assert "default_reading: [留抵]" in text, "留抵缺省主读显式声明（s109 依据）"
    assert "default_reading: [税率]" in text, "税率缺省主读显式声明（s117 依据）"


def test_b2_golden_s109_s117_resolve_by_default() -> None:
    """黄金集两无佐证 qid（s109 留抵/s117 税率）经显式缺省主读定案
    （resolved_by='default'，非 ambiguous）——README 口径的行为证据。"""
    import importlib.util
    import sys
    import tempfile

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import Annotator
    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    spec = importlib.util.spec_from_file_location(
        "eval_semantic_seed_dr2", EVAL_DIR / "semantic_seed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_semantic_seed_dr2"] = mod
    spec.loader.exec_module(mod)

    tmp = Path(tempfile.mkdtemp())
    conn = connect(tmp / "l.db")
    migrate_db(conn)
    seed_org(conn, ORG)
    b = SqliteBackend(conn)
    settings = Settings(environment="test", data_dir=tmp)
    mod.seed_reference_org(b, ORG, settings, repo_dir=tmp / "yamlrepo")
    ann = Annotator(b.sem_active_snapshot(ORG))

    for qid, expect in (("s109", "concept:vat.retained_credit"),
                        ("s117", "concept:vat.tax_rate")):
        line = next(l for l in
                    (EVAL_DIR / "semantic_golden.jsonl").read_text(
                        encoding="utf-8").splitlines()
                    if f'"qid": "{qid}"' in l or f'"qid":"{qid}"' in l)
        item = json.loads(line)
        out = ann.annotate(item["text"])
        m = next(m for m in out["mentions"] if m["span"][0] == 0)
        assert m["resolved_by"] == "default" and m["ambiguous"] is False, \
            f"{qid} 应经显式缺省主读定案"
        assert m["entity_key"] == expect, f"{qid} 缺省主读实体不符"
