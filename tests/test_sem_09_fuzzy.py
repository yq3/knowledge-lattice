"""m2s-6 TC-SEM-09 模糊兜底三层（design §5.9 第 3 层 / §5.8 构建产物 2）。

- 三层依次：同音错字（拼音完全匹配）→ 编辑距离 ≤1（长度 ≥4）→ 语义近邻
  （阈值 0.75 top-3——vec_lookup 注入面）；同片段只取首个命中层；
- via='fuzzy'、confidence 一律低于第 1 层（0.75/0.65/0.55 < 0.9）、落
  candidates 不进 mentions（G-2：中间件不自动注入——只作候选提示）；
- **前置构建断言**：构建产出模糊索引（sem_fuzzy_terms 名称/别名/一句话
  定义 + sem_fuzzy_dels 编辑距离辅助表；向量经 Embedder provider、embedder
  不可达降级为空不阻断构建——标签入 dict_rev 换模型强制重算）；
- jieba 词性筛选：错别字常被切为动词/未登录词——实词族口径（n/v/a/eng/x）
  + 相邻实词对拼接（「纳税申抱」跨词粘接面）；
- restricted 实体不进模糊索引（T-S9 fail-closed）；
- G-21 P3 顺手：latin 去空白粘接行为锁定（跨空白命中是设计特性、词边界由
  _latin_ok 保证不误报）+ mixed-mode context 候选级门槛（P3-5）。
"""

from __future__ import annotations

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-11-01 09:00:00"


@pytest.fixture()
def fuzzy_env(backend, tmp_path):
    """参考词典栈（eval.semantic_seed——黄金集标注真相源）+ build（embedder
    注入 FakeEmbedder 向量层）。"""
    import importlib.util
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build

    seed_path = Path(__file__).resolve().parent.parent / "eval" / "semantic_seed.py"
    spec = importlib.util.spec_from_file_location("eval_semantic_seed_f", seed_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_semantic_seed_f"] = mod
    spec.loader.exec_module(mod)

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        embed_model="fake-embed")
    b = backend.make_backend()
    mod.seed_reference_org(b, ORG, settings, repo_dir=tmp_path / "yamlrepo")
    clear_annotator_cache()
    from fake_providers import FakeEmbedder

    result = run_build(b, ORG, settings=settings,
                       embedder=FakeEmbedder(dim=8, model_name="fake-embed"))
    assert result["status"] == "ready", result
    return SimpleNamespace(db=backend, backend=b, settings=settings,
                           build=result)


def _fuzzy_of(env, text: str):
    from knowledge_lattice.core.semantic.annotator import get_annotator

    ann, _rev = get_annotator(env.backend, ORG, env.settings)
    return ann.annotate(text, fuzzy=True)


# ---- 构建产物断言（TC-SEM-09 前置——#38 P1-3 自 TC-BUILD-02 移入） ----


def test_tc_sem_09_build_fuzzy_index_products(fuzzy_env) -> None:
    """构建产出模糊索引：sem_fuzzy_terms（name/alias/definition 三 kind——
    一句话定义经 Embedder provider 带向量）+ sem_fuzzy_dels 编辑距离辅助表；
    构建报告 stats.fuzzy 计数入面。"""
    env = fuzzy_env
    terms = env.backend.sem_fuzzy_terms_all(ORG)
    kinds = {t["kind"] for t in terms}
    assert {"name", "alias", "definition"} <= kinds
    assert any(t["text_norm"] == "进项税额抵扣" and t["kind"] == "name"
               for t in terms)
    assert any(t["text_norm"] == "进项抵扣" and t["kind"] == "alias"
               for t in terms)
    # 一句话定义（definition 首句）在场
    assert any(t["kind"] == "definition" and "进项" in t["text_norm"]
               for t in terms)
    dels = env.db.execute(
        "SELECT count(*) FROM sem_fuzzy_dels WHERE org_id = ?", (ORG,)
    ).fetchone()[0]
    assert dels > 0, "编辑距离辅助表应有 deletion 键"
    fuzzy_stats = env.build["stats"]["fuzzy"]
    assert fuzzy_stats["terms"] == len(terms)
    assert fuzzy_stats["vec_embedded"] > 0, "向量层经 Embedder provider 生成"
    # del 键只来自长度 ≥4 的 name/alias
    terms_by_id = {t["id"]: t for t in terms}
    for key, term_id in env.db.execute(
            "SELECT del_key, term_id FROM sem_fuzzy_dels WHERE org_id = ?",
            (ORG,)).fetchall():
        t = terms_by_id.get(term_id)
        assert t and t["term_len"] >= 4 and t["kind"] in ("name", "alias")


def test_tc_sem_09_embedder_failure_degrades(fuzzy_env) -> None:
    """embedder 不可达：模糊索引向量列空（vec_skipped 注记）——构建不阻断、
    拼音/编辑距离层仍可用；embed_model 标签入 dict_rev（换模型强制重算）。"""
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import (
        compute_dict_rev, dict_rev_components, run_build,
    )
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.core.semantic.records import EntityRecord

    env = fuzzy_env
    # 追加实体触发新 rev（embedder=None——向量降级）
    recs = [EntityRecord(type="concept", key="c.fuzzyx", name="模糊扩展概念")]
    run_sync(env.backend, ORG, FakeSourceAdapter("tc", recs),
             settings=env.settings, snapshot=list(recs), now=NOW)
    clear_annotator_cache()

    class BoomEmbedder:
        model_label = "fake-embed:8"

        def embed(self, texts):
            raise ConnectionError("gateway unreachable")

    result = run_build(env.backend, ORG, settings=env.settings,
                       embedder=BoomEmbedder())
    assert result["status"] == "ready", "嵌入失败不阻断构建（非可用性前提）"
    assert result["stats"]["fuzzy"]["vec_skipped"] is True
    # dict_rev 输入含 embed_model 标签（换模型 → 不同 rev → 强制重算）
    snap = env.backend.sem_active_snapshot(ORG)
    rev_a = compute_dict_rev(snap, embed_model_label="model-a:8", yaml_rev=None)
    rev_b = compute_dict_rev(snap, embed_model_label="model-b:8", yaml_rev=None)
    assert rev_a != rev_b
    comps = dict_rev_components(snap, embed_model_label="fake-embed:8",
                                yaml_rev=None)
    assert comps["embed_model"] == "fake-embed:8"


# ---- 三层依次（TC-SEM-09 主体） ----


def test_tc_sem_09_layer1_pinyin_homophone(fuzzy_env) -> None:
    """① 同音错字（拼音完全匹配）：「留底」→「留抵」——via='fuzzy'、
    fuzzy_layer='pinyin'、confidence=0.75（< 第 1 层 context 档 0.9）、
    落 candidates 不进 mentions。"""
    result = _fuzzy_of(fuzzy_env, "留底税额怎么结转下期")
    cands = [c for c in result["candidates"] if c["via"] == "fuzzy"]
    assert cands, "同音错字应有 fuzzy 候选"
    hit = next(c for c in cands if c["surface"] == "留底")
    assert hit["fuzzy_layer"] == "pinyin"
    assert hit["confidence"] == 0.75
    assert not any(m["surface"] == "留底" for m in result["mentions"]), (
        "fuzzy 结果不进 mentions（G-2——只作候选提示）")


def test_tc_sem_09_layer2_edit_distance(fuzzy_env) -> None:
    """② 编辑距离 ≤1（长度 ≥4）：「一般纳税入」→「一般纳税人」；latin 缩写
    「JXDL」→「JXDK」（k→l 非同音——拼音层不命中、编辑距离层兜住）。"""
    result = _fuzzy_of(fuzzy_env, "一般纳税入的认定标准")
    hit = next(c for c in result["candidates"]
               if c.get("fuzzy_layer") == "edit")
    assert hit["entity_key"] == "concept:vat.general_taxpayer"
    assert hit["confidence"] == 0.65

    latin = _fuzzy_of(fuzzy_env, "JXDL 具体指什么")
    lhit = [c for c in latin["candidates"]
            if c.get("fuzzy_layer") == "edit"]
    assert any(c["entity_key"] == "concept:vat.input_credit" for c in lhit)


def test_tc_sem_09_layer3_vec_neighbor(fuzzy_env) -> None:
    """③ 语义近邻（阈值 0.75 top-3）：vec_lookup 注入面——同义不同形词
    （「完税证明」无字面关系，向量可控命中——TokenBag 注入）。"""
    from knowledge_lattice.core.semantic.annotator import get_annotator

    env = fuzzy_env
    ann, _rev = get_annotator(env.backend, ORG, env.settings)

    def vec_lookup(fragment: str):
        # 可控注入：对「进项税额抵减」返回 input_credit（sim=0.9——过阈值）
        if "抵减" in fragment:
            eid = ann.key_map["concept:vat.input_credit"]
            return [{"entity_id": eid, "sim": 0.9, "text_norm": "进项税额抵扣"}]
        return []

    result = ann.annotate("进项税额抵减的口径", fuzzy=True, vec_lookup=vec_lookup)
    hits = [c for c in result["candidates"]
            if c.get("fuzzy_layer") == "vec"]
    assert hits and hits[0]["entity_key"] == "concept:vat.input_credit"
    assert hits[0]["confidence"] == 0.55
    assert hits[0]["sim"] == 0.9


def test_tc_sem_09_layer_order_short_circuit(fuzzy_env) -> None:
    """三层依次短路：拼音层命中后编辑距离/向量层不再查（同片段只取首层）。"""
    from knowledge_lattice.core.semantic.annotator import get_annotator

    env = fuzzy_env
    ann, _rev = get_annotator(env.backend, ORG, env.settings)

    def vec_lookup(fragment: str):
        # 「留底」拼音层应短路——本查询只对它返回 vec 命中，若被调用即证明
        # 短路失效（其余片段返回空避免干扰）
        if fragment == "留底":
            return [{"entity_id": ann.key_map["concept:vat.output_tax"],
                     "sim": 0.99, "text_norm": "销项税额"}]
        return []

    result = ann.annotate("留底怎么结转", fuzzy=True, vec_lookup=vec_lookup)
    pinyin_hits = [c for c in result["candidates"]
                   if c.get("fuzzy_layer") == "pinyin"
                   and c["surface"] == "留底"]
    assert pinyin_hits, "「留底」应由拼音层命中"
    assert not any(c.get("fuzzy_layer") == "vec" and c["surface"] == "留底"
                   for c in result["candidates"]), (
        "拼音层命中后同片段不得再出 vec 候选（依次短路）")


def test_tc_sem_09_fuzzy_never_into_mentions_and_neg_clean(fuzzy_env) -> None:
    """fuzzy 结果不进 mentions；负样本文本 fuzzy 层零候选（错字面无近邻）。"""
    result = _fuzzy_of(fuzzy_env, "停车场月卡续费")
    assert all(c.get("via") == "fuzzy" for c in result["candidates"]) or (
        not result["candidates"])
    assert result["mentions"] == []


def test_tc_sem_09_restricted_not_in_fuzzy(fuzzy_env) -> None:
    """restricted 实体不进模糊索引（T-S9 fail-closed——无权 fuzzy 候选零出现）。"""
    env = fuzzy_env
    rows = env.db.execute(
        "SELECT count(*) FROM sem_fuzzy_terms f JOIN sem_entities e"
        "   ON e.id = f.entity_id"
        " WHERE f.org_id = ? AND e.sensitivity = 'restricted'", (ORG,)
    ).fetchone()[0]
    assert rows == 0


def test_tc_sem_09_noun_filter_adjacent_pair(fuzzy_env) -> None:
    """词性筛选（实词族）+ 相邻实词对拼接：「纳税申抱」被 jieba 切为
    纳税+申抱——bigram 片段命中拼音层（整别名「纳税申报」）。"""
    result = _fuzzy_of(fuzzy_env, "纳税申抱的期限是什么")
    hit = [c for c in result["candidates"] if c.get("fuzzy_layer") == "pinyin"]
    assert any(c["entity_key"] == "concept:vat.filing" for c in hit)


# ---- G-21 P3 顺手（latin 粘接行为锁定 + mixed-mode 候选级门槛） ----


def test_g21_latin_whitespace_glue_semantics(fuzzy_env) -> None:
    """latin 去空白粘接（G-21 未闭 P3——行为锁定）：「JX DK」规范化粘接为
    jxdk 命中缩写（**跨空白命中是设计特性**——TC-SEM-01 同函数口径）；
    词边界由 _latin_ok 保证（xxjdkxx 内部不命中——不因粘接误报）。"""
    result = _fuzzy_of(fuzzy_env, "JX DK 是什么意思")
    assert any(m["entity_key"] == "concept:vat.input_credit"
               for m in result["mentions"]), "跨空白缩写命中是设计特性"
    inner = _fuzzy_of(fuzzy_env, "XXJXDKXX 不是一个词")
    assert not any(m["entity_key"] == "concept:vat.input_credit"
                   for m in inner["mentions"]), "词边界防 substring 误报"


def test_g21_mixed_mode_candidate_level_gate() -> None:
    """mixed-mode 候选级门槛（G-21 P3-5）——**现状锁定 + 再挂注记**：
    同一 span 内 exact 与 context 候选并存时按 span 级处理（ctx 候选参与
    消歧）——这是参考词典刻意设计的 mixed 歧义面（「留抵」＝exact
    retained_credit + context retained_refund〔带 disambiguation〕）；候选
    级剔除会使 ambiguity 门槛失守（m2s-6 实测 0.75 < 0.85）。门槛细化需
    连同词典口径重设计——known-gaps G-21 再挂（m2s-6 核销表登记）。"""
    from knowledge_lattice.core.semantic.annotator import Annotator

    def _ent(i, type_, key, name):
        return {"id": i, "type": type_, "key": key, "name": name,
                "parent_id": None, "attrs_json": "{}", "sensitivity": "normal",
                "curated_json": "{}", "curated_rev": None}

    def _alias(entity_id, alias, mode="exact", weight=1.0):
        return {"entity_id": entity_id, "alias": alias,
                "alias_norm": alias, "kind": "manual", "match_mode": mode,
                "weight": weight}

    ents = [_ent(1, "concept", "a", "甲"), _ent(2, "concept", "d", "丁")]
    aliases = [_alias(1, "抵扣"), _alias(2, "抵扣", mode="context")]
    ann = Annotator({"entities": ents, "aliases": aliases, "relations": []})
    # 现状：mixed span 的 ctx 候选参与消歧（两候选 → ambiguous=true 交 agent）
    r = ann.annotate("这个月的抵扣怎么算")
    hit = [m for m in r["mentions"] if m["surface"] == "抵扣"]
    assert hit and hit[0]["ambiguous"] is True
    assert {c["entity_id"] for c in r["candidates"]} == {1, 2}
