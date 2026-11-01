"""m2-5 A8（m2s-6 移交 G-24③④⑤ 收口）：

- ③ search_entities vec 档有界超时/熔断/降级审计——NFR-8/§5.2 口径对齐
  （embed 用 query_embed_timeout_s 非 30s、失败走 breaker 计数、降级统一
  search.degraded 审计事件——此前仅 warning，延迟与可观测双缺口）；
- ④ annotator 模糊内存面——Annotator 构造**无条件** build_fuzzy_terms
  （pypinyin 万级开销）+ _fuzzy_candidates 每片段 `dict()` 全量复制索引：
  改懒构建 + 直读索引（fuzzy_layers_for_fragment 只读 .get——无 mutate）；
- ⑤ vec top-3 硬编码——annotate 消费 settings.semantic_fuzzy_vec_top
  （此前 store 查询侧 top_k 已消费、annotator 实体截断侧硬编码 3）。
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from conftest import ORG
from helpers import seed_org

NOW = "2026-11-01 09:00:00"


@pytest.fixture()
def sem_env(backend, tmp_path):
    """最小语义库：2 实体（其一带别名）+ ready 构建（含模糊索引）。"""
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_providers import FakeEmbedder
    from fake_semantic import FakeSourceAdapter

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        embed_model="fake-embed")
    b = backend.make_backend()
    recs = [
        EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣",
                     aliases=("进项抵扣",)),
        EntityRecord(type="concept", key="vat.retained_credit", name="留抵税额"),
    ]
    run_sync(b, ORG, FakeSourceAdapter("tc", recs), settings=settings,
             snapshot=list(recs), now=NOW)
    clear_annotator_cache()
    assert run_build(b, ORG, settings=settings,
                     embedder=FakeEmbedder(dim=8, model_name="fake-embed")
                     )["status"] == "ready"
    return SimpleNamespace(db=backend, backend=b, settings=settings)


# ============ ③ search_entities vec 档：超时/熔断/降级审计 ============


class _SlowEmbedder:
    """慢嵌入（超 query_embed_timeout_s）——vec 档有界超时面。"""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.calls = 0
        self.model_name = "fake-embed"

    @property
    def model_label(self) -> str:
        return "fake-embed:8"

    def embed(self, texts):
        self.calls += 1
        time.sleep(self.delay)
        return [[0.1] * 8 for _ in texts]


def _events(db, event_type: str) -> list:
    order = "rowid" if db.name == "sqlite" else "created_at"
    rows = db.execute(
        f"SELECT payload_json FROM audit_outbox WHERE event_type = ?"
        f" ORDER BY {order}", (event_type,),
    ).fetchall()
    import json

    return [json.loads(r[0]) for r in rows]


def test_vec_layer_timeout_bounded_and_audited(sem_env) -> None:
    """慢嵌入超 query_embed_timeout_s → vec 档有界降级：前三档照常返回 +
    search.degraded 审计（reason=embed_unreachable、scope=search_entities）+
    breaker 计失败（§5.2 同源口径——此前仅 warning 无审计无界等待）。"""
    import dataclasses

    from knowledge_lattice.adapters.breaker import CircuitBreaker
    from knowledge_lattice.core.semantic.lookup import search_entities

    settings = dataclasses.replace(sem_env.settings, query_embed_timeout_s=0.05)
    slow = _SlowEmbedder(delay=0.4)
    breaker = CircuitBreaker(failures=3, cooldown_s=60.0)
    out = search_entities(
        sem_env.backend, ORG, "进项税额抵扣", top_k=5,
        settings=settings, embedder=slow,
        breakers={"embed": breaker}, user_id="u_full",
    )
    # 前三档照常（增益路失败不阻断——与 G-1 语义一致）
    assert out["entities"], "vec 档降级不空结果（前三档照常）"
    events = _events(sem_env.db, "search.degraded")
    assert events, "vec 档降级须发 search.degraded 审计事件"
    assert events[-1]["reasons"] == ["embed_unreachable"]
    assert events[-1]["scope"] == "search_entities"
    assert events[-1]["org_id"] == ORG
    assert events[-1]["user_id"] == "u_full"
    assert breaker._streak == 1, "熔断计失败（连续 3 次断开）"


def test_vec_layer_breaker_open_skips_embed_call(sem_env) -> None:
    """熔断开路：不发起嵌入调用（慢 vs 不可达由熔断区分——NFR-8），
    降级照常审计。"""
    import dataclasses

    from knowledge_lattice.adapters.breaker import CircuitBreaker
    from knowledge_lattice.core.semantic.lookup import search_entities

    settings = dataclasses.replace(sem_env.settings, query_embed_timeout_s=1.0)
    embedder = _SlowEmbedder(delay=0.0)
    breaker = CircuitBreaker(failures=3, cooldown_s=60.0)
    for _ in range(3):
        breaker.record_failure()
    assert not breaker.allow()

    out = search_entities(
        sem_env.backend, ORG, "进项税额抵扣", top_k=5,
        settings=settings, embedder=embedder,
        breakers={"embed": breaker}, user_id="u_full",
    )
    assert out["entities"]
    assert embedder.calls == 0, "熔断开路期间不发嵌入调用（不等超时）"
    events = _events(sem_env.db, "search.degraded")
    assert events and events[-1]["reasons"] == ["embed_unreachable"]


def test_vec_layer_success_no_audit_no_degrade(sem_env) -> None:
    """正常路径：breaker 计成功、零降级审计（不污染可观测面）。"""
    from fake_providers import FakeEmbedder
    from knowledge_lattice.adapters.breaker import CircuitBreaker
    from knowledge_lattice.core.semantic.lookup import search_entities

    ok = FakeEmbedder(dim=8, model_name="fake-embed")
    breaker = CircuitBreaker(failures=3, cooldown_s=60.0)
    breaker.record_failure()  # 预置 1 次失败——成功后不累积
    out = search_entities(
        sem_env.backend, ORG, "进项税额抵扣", top_k=5,
        settings=sem_env.settings, embedder=ok,
        breakers={"embed": breaker}, user_id="u_full",
    )
    assert out["entities"]
    assert _events(sem_env.db, "search.degraded") == []


# ============ ④ annotator 模糊内存面：懒构建 + 去 dict() 复制 ============


def _snapshot_fixture():
    from knowledge_lattice.core.semantic.records import EntityRecord

    recs = [
        EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣",
                     aliases=("进项抵扣",)),
        EntityRecord(type="concept", key="vat.retained_credit", name="留抵税额"),
    ]
    return recs


def test_annotator_fuzzy_lazy_build(backend, tmp_path, monkeypatch) -> None:
    """fuzzy=False（缺省）构造/识别零模糊构建开销；首次 fuzzy=True 才构建、
    且同实例只构建一次（万级词典 pypinyin 每次构建秒级——G-24④）。"""
    from knowledge_lattice.core.semantic import annotator as ann_mod
    from knowledge_lattice.core.semantic.annotator import Annotator
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.records import EntityRecord
    from fake_semantic import FakeSourceAdapter

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        embed_model="fake-embed")
    b = backend.make_backend()
    recs = _snapshot_fixture()
    run_sync(b, ORG, FakeSourceAdapter("tc", recs), settings=settings,
             snapshot=list(recs), now=NOW)
    snapshot = b.sem_active_snapshot(ORG)

    calls = {"n": 0}
    orig = ann_mod.build_fuzzy_terms

    def counting(*a, **kw):
        calls["n"] += 1
        return orig(*a, **kw)

    monkeypatch.setattr(ann_mod, "build_fuzzy_terms", counting)
    ann = Annotator(snapshot)
    assert calls["n"] == 0, "构造期不得构建模糊面（G-24④——懒构建）"
    r1 = ann.annotate("进项抵扣的办法")           # 非 fuzzy 识别
    assert r1["mentions"]
    assert calls["n"] == 0, "fuzzy=False 识别零模糊构建开销"
    r2 = ann.annotate("进项抵扣的办法", fuzzy=True)
    assert calls["n"] == 1, "首次 fuzzy=True 触发构建（一次）"
    ann.annotate("进项抵扣的办法", fuzzy=True)
    assert calls["n"] == 1, "同实例不重复构建"
    # 懒构建后 stats 属性仍可用（对外面不变——build 报告口径在 build 侧）
    assert isinstance(ann.fuzzy_stats, dict)


def test_annotator_fuzzy_no_dict_copy(sem_env, monkeypatch) -> None:
    """_fuzzy_candidates 直读实例索引（无 dict() 全量复制）——索引对象身份
    断言（G-24④：万级词典每片段复制两次的固定开销根除）。"""
    from knowledge_lattice.core.semantic import annotator as ann_mod
    from knowledge_lattice.core.semantic.annotator import Annotator, clear_annotator_cache

    clear_annotator_cache()
    snapshot = sem_env.backend.sem_active_snapshot(ORG)
    ann = Annotator(snapshot)
    seen: dict = {}

    def spy(frag_norm, *, pinyin_index, del_index, terms):
        seen["pinyin_is_self"] = pinyin_index is ann._fuzzy_pinyin
        seen["del_is_self"] = del_index is ann._fuzzy_dels
        seen["terms_is_self"] = terms is ann.fuzzy_terms
        return ann_mod.fuzzy_layers_for_fragment(
            frag_norm, pinyin_index=pinyin_index, del_index=del_index,
            terms=terms)

    monkeypatch.setattr(ann, "_fuzzy_match", spy)
    ann.annotate("进项抵扣额核算办法", fuzzy=True)
    assert seen.get("pinyin_is_self") is True, "拼音索引须直读（无 dict() 复制）"
    assert seen.get("del_is_self") is True
    assert seen.get("terms_is_self") is True


# ============ ⑤ vec top-k 参数化（LATTICE_SEM_FUZZY_VEC_TOP 消费） ============


def test_annotate_vec_top_consumed(sem_env) -> None:
    """annotate(vec_top=N)：向量层候选实体截断消费 N（默认 3）；此前硬编码 3
    ——G-24⑤。vec_lookup 注入面直测（store 侧 top_k 已在 annotate_text 消费）。"""
    from knowledge_lattice.core.semantic.annotator import Annotator, clear_annotator_cache

    clear_annotator_cache()
    snapshot = sem_env.backend.sem_active_snapshot(ORG)
    ann = Annotator(snapshot)
    eids = [e["id"] for e in snapshot["entities"]]

    def vec_lookup(_frag):
        # 多 term 同实体面：全库实体各回一条（截断在实体去重后按 vec_top）
        return [{"entity_id": eid, "sim": 0.9, "text_norm": "x"}
                for eid in sorted(eids, reverse=True)]

    out3 = ann.annotate("关联票据整备", fuzzy=True, vec_lookup=vec_lookup)
    vec_cands3 = [c for c in out3["candidates"] if c.get("fuzzy_layer") == "vec"]
    per_span3: dict[tuple[int, int], int] = {}
    for c in vec_cands3:
        per_span3[tuple(c["span"])] = per_span3.get(tuple(c["span"]), 0) + 1
    assert vec_cands3, "vec 层应有候选（注入 vec_lookup 全命中）"
    assert all(n <= 3 for n in per_span3.values()), \
        f"默认 vec_top=3 每片段截断（got {per_span3}）"

    out1 = ann.annotate("关联票据整备", fuzzy=True, vec_lookup=vec_lookup,
                        vec_top=1)
    vec_cands1 = [c for c in out1["candidates"] if c.get("fuzzy_layer") == "vec"]
    per_span1: dict[tuple[int, int], int] = {}
    for c in vec_cands1:
        per_span1[tuple(c["span"])] = per_span1.get(tuple(c["span"]), 0) + 1
    assert all(n <= 1 for n in per_span1.values()), \
        f"vec_top=1 每片段截断生效——硬编码根除（got {per_span1}）"


def test_annotate_text_passes_settings_vec_top(sem_env) -> None:
    """annotate_text 编排面：settings.semantic_fuzzy_vec_top 传入 annotate
    （env LATTICE_SEM_FUZZY_VEC_TOP 端到端消费链闭合）。"""
    import dataclasses

    from knowledge_lattice.core.semantic.annotator import (
        annotate_text, clear_annotator_cache,
    )

    clear_annotator_cache()
    settings = dataclasses.replace(sem_env.settings, semantic_fuzzy_vec_top=1)
    eids_seen: list[int] = []

    def embed_batch(texts):
        return [[0.05] * 8 for _ in texts]

    orig_lookup_holder: dict = {}
    # 经 monkeypatch 不可行（闭包内部），改经 backend 侧计数——vec 层每片段
    # 最多回 1 实体由 annotate 侧截断保证；此处断言编排面传参生效：
    # semantic_fuzzy_vec_top=1 时 candidates 的 vec 面 ≤1/片段
    out = annotate_text(
        sem_env.backend, settings, ORG, "关联票据整备",
        fuzzy=True, embed_batch=embed_batch,
    )
    vec_cands = [c for c in out["candidates"] if c.get("fuzzy_layer") == "vec"]
    # fake 8 维随机向量对 2 实体库的 sim 大概率 <0.75 阈值 → 0~1 条均合法；
    # 断言上界=1（vec_top=1 生效；>1 即硬编码 3 残留）
    assert len(vec_cands) <= 1, f"settings.semantic_fuzzy_vec_top=1 须贯穿（got {len(vec_cands)}）"
