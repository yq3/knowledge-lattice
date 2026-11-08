"""m3-3 语义 hardening 批：A 组（G-24⑥⑦⑨ 收口）+ B 组（G-23 残余收口）。

A 组：
- ⑨前半（issue #15 / G-24⑨）：search_entities / annotate 的 fuzzy vec 层接线
  probe gate——探针拒绝后关查询侧向量路（NFR-8/§5.2 跨切面一致；降级审计
  reason=probe_reject 与 docs 检索同源）；
- ⑨后半：annotate fuzzy vec 补 query_embed_timeout_s 有界等待 + 共享熔断
  （service.breakers["embed"]）+ 降级审计（沿 search_entities 既有形态——
  G-24③ m2-5 实装口径，scope=annotate）；
- ⑥（G-24⑥）：auto_entities 超长（query >4000 字）auto 分支返回 None 不
  阻断检索（增益路失败不阻断——§5.10）；
- ⑦（G-24⑦，裁定① 2026-11-08）：mention 契约补可选 disambiguation 字段
  ——design §6.3② 核读结论：中间件 L1 注入规则字面「概念/系统：name +
  brief + disambiguation」且 YAML curated_json.disambiguation（{not, hint}）
  为自然数据来源 → 有自然落位，补字段（向后兼容：无该数据不出现该键）；
  中间件概念行消费它。

B 组（G-23①②③④⑤ 合并修法——裁定②内容哈希方向）：
- ① embed_model 入内容集合：模型迁移 + ready 切换后 fuzzy 写库崩溃窗口
  （旧标签行内容集合恰好相等）不再漏修——对账集合追加 embed_model 维度；
- ② 标记粘滞消除：修复成功清 current 行 index_write_failed/vec_skipped；
- ③ per-skip 全量重算收窄：build stats 存内容集合哈希（带 embed_model 维
  度），健康索引 skipped 构建快速通过（build_fuzzy_terms 零调用）——
  「再次 skipped 不重触」；
- ④ fuzzy_repaired 观测语义：被修复 build 行 stats 留 repaired 注记
  （标记清理与注记同面；审计事件由 skipped 事件携带——既有）；
- ⑤ 构建产物 code versioning 入 dict_rev（FUZZY_CODE_REV 常量）。
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from conftest import ORG
from helpers import seed_org

NOW = "2026-11-08 09:00:00"


@pytest.fixture()
def sem_env(backend, tmp_path):
    """最小语义库：2 实体（其一带别名）+ ready 构建（含模糊索引——
    FakeEmbedder 向量）。A/B 组共用（B 组用例内按需破坏索引/标记）。"""
    from fake_providers import FakeEmbedder
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync

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
    embedder = FakeEmbedder(dim=8, model_name="fake-embed")
    assert run_build(b, ORG, settings=settings, embedder=embedder)["status"] \
        == "ready"
    return SimpleNamespace(db=backend, backend=b, settings=settings,
                           embedder=embedder)


@pytest.fixture()
def disamb_env(backend, tmp_path):
    """带 curated disambiguation 的语义库：纯人工 YAML 概念（含
    disambiguation [{not, hint}]——concepts/ 目录覆盖层与同步实体同 key 会被
    规则表第 3 行剔除，故用纯人工形态）+ ready 构建——A-4 mention 契约面。"""
    from fake_providers import FakeEmbedder
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        embed_model="fake-embed")
    b = backend.make_backend()
    repo = tmp_path / "yamlrepo"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "vat.yaml").write_text(
        "- id: concept:vat.input_credit\n"
        "  owner: o\n"
        "  name: 进项税额抵扣\n"
        "  aliases: [进项抵扣, 抵进项]\n"
        "  definition: 购进货物或服务取得合规凭证后按规定抵减销项税额。\n"
        "  disambiguation:\n"
        "    - not: concept:vat.input_transfer_out\n"
        "      hint: 进项转出是抵扣后因用途改变转回，方向相反\n"
        "- id: concept:vat.input_transfer_out\n"
        "  owner: o\n"
        "  name: 进项税额转出\n"
        "  definition: 已抵扣进项税额因用途改变转回。\n",
        encoding="utf-8")
    run_yaml_sync(b, ORG, YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=settings, now=NOW)
    clear_annotator_cache()
    assert run_build(
        b, ORG, settings=settings,
        embedder=FakeEmbedder(dim=8, model_name="fake-embed"))["status"] \
        == "ready"
    return SimpleNamespace(db=backend, backend=b, settings=settings)


def _events(db, event_type: str) -> list:
    order = "rowid" if db.name == "sqlite" else "created_at"
    rows = db.execute(
        f"SELECT payload_json FROM audit_outbox WHERE event_type = ?"
        f" ORDER BY {order}", (event_type,),
    ).fetchall()
    return [json.loads(r[0]) for r in rows]


def _rejected_gate():
    from knowledge_lattice.adapters.embedder import EmbeddingGate, ProbeResult

    gate = EmbeddingGate()
    gate.update(ProbeResult(status="reject", min_cosine=0.5))
    assert gate.rejected
    return gate


class _CountingEmbedder:
    """调用计数嵌入器（gate 断言面：拒绝档零调用）。"""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.calls = 0
        self.model_name = "fake-embed"

    @property
    def model_label(self) -> str:
        return "fake-embed:8"

    def embed(self, texts):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return [[0.1] * 8 for _ in texts]


# ============ A-1 / G-24⑨前半：probe gate 接线（查询侧向量路关闭） ============


def test_a1_search_entities_gate_rejected_skips_vec(sem_env) -> None:
    """探针拒绝 → search_entities vec 档关闭：不发嵌入调用 + probe_reject
    降级审计（scope=search_entities）+ 前三档照常（§5.2 跨切面一致）。"""
    import dataclasses

    from knowledge_lattice.adapters.breaker import CircuitBreaker
    from knowledge_lattice.core.semantic.lookup import search_entities

    settings = dataclasses.replace(sem_env.settings, query_embed_timeout_s=1.0)
    embedder = _CountingEmbedder()
    out = search_entities(
        sem_env.backend, ORG, "进项税额抵扣", top_k=5,
        settings=settings, embedder=embedder,
        breakers={"embed": CircuitBreaker(failures=3, cooldown_s=60.0)},
        user_id="u_full", gate=_rejected_gate(),
    )
    assert out["entities"], "vec 档关闭前三档照常（增益路语义不变）"
    assert embedder.calls == 0, "探针拒绝档不发查询侧嵌入调用（跨底模距离无意义）"
    events = _events(sem_env.db, "search.degraded")
    assert events and events[-1]["reasons"] == ["probe_reject"], (
        "gate 拒绝须发 probe_reject 降级审计（与 docs 检索 notice 同源语义）")
    assert events[-1]["scope"] == "search_entities"


def test_a1_annotate_fuzzy_gate_rejected_skips_vec(sem_env) -> None:
    """探针拒绝 → annotate fuzzy vec 层关闭：embedder 零调用 + probe_reject
    降级审计（scope=annotate）；拼音/编辑距离层不受影响（识别照常）。"""
    from knowledge_lattice.core.semantic.annotator import (
        annotate_text, clear_annotator_cache,
    )

    clear_annotator_cache()
    embedder = _CountingEmbedder()
    out = annotate_text(
        sem_env.backend, sem_env.settings, ORG, "进项抵扣的关联票据整备",
        fuzzy=True, embedder=embedder, gate=_rejected_gate(),
    )
    assert out["mentions"], "AC 层识别不受 gate 影响"
    assert embedder.calls == 0, "探针拒绝档 fuzzy vec 层不得发起嵌入调用"
    events = _events(sem_env.db, "search.degraded")
    assert events and events[-1]["reasons"] == ["probe_reject"]
    assert events[-1]["scope"] == "annotate"


# ============ A-2 / G-24⑨后半：annotate fuzzy vec 有界/熔断/降级审计 ============


def test_a2_annotate_fuzzy_vec_bounded_and_audited(sem_env) -> None:
    """慢嵌入超 query_embed_timeout_s → 有界降级（不阻断识别）+ 熔断计失败 +
    search.degraded（reason=embed_unreachable、scope=annotate——沿 search_entities
    既有形态）。"""
    import dataclasses

    from knowledge_lattice.adapters.breaker import CircuitBreaker
    from knowledge_lattice.core.semantic.annotator import (
        annotate_text, clear_annotator_cache,
    )

    clear_annotator_cache()
    settings = dataclasses.replace(sem_env.settings, query_embed_timeout_s=0.05)
    # failures=10：annotate 多片段各计一次失败，避免途中断开清零计数
    #（断开语义另由 breaker_open 用例锁定）
    breaker = CircuitBreaker(failures=10, cooldown_s=60.0)
    out = annotate_text(
        sem_env.backend, settings, ORG, "进项抵扣的关联票据整备",
        fuzzy=True, embedder=_CountingEmbedder(delay=0.4),
        breakers={"embed": breaker}, user_id="u_full",
    )
    assert out["mentions"], "向量层降级不阻断识别（增益路语义）"
    assert breaker._streak >= 1, "有界超时须计熔断失败"
    events = _events(sem_env.db, "search.degraded")
    assert events and events[-1]["reasons"] == ["embed_unreachable"]
    assert events[-1]["scope"] == "annotate"
    assert events[-1]["org_id"] == ORG
    assert events[-1]["user_id"] == "u_full"


def test_a2_annotate_fuzzy_vec_breaker_open(sem_env) -> None:
    """熔断开路：fuzzy vec 层不发嵌入调用（慢 vs 不可达由熔断区分），
    降级照常审计。"""
    from knowledge_lattice.adapters.breaker import CircuitBreaker
    from knowledge_lattice.core.semantic.annotator import (
        annotate_text, clear_annotator_cache,
    )

    clear_annotator_cache()
    breaker = CircuitBreaker(failures=3, cooldown_s=60.0)
    for _ in range(3):
        breaker.record_failure()
    assert not breaker.allow()
    embedder = _CountingEmbedder()
    out = annotate_text(
        sem_env.backend, sem_env.settings, ORG, "进项抵扣的关联票据整备",
        fuzzy=True, embedder=embedder,
        breakers={"embed": breaker}, user_id="u_full",
    )
    assert out["mentions"]
    assert embedder.calls == 0, "熔断开路期间不发嵌入调用"
    events = _events(sem_env.db, "search.degraded")
    assert events and events[-1]["reasons"] == ["embed_unreachable"]
    assert events[-1]["scope"] == "annotate"


# ============ A-3 / G-24⑥：auto_entities 超长不阻断检索 ============


def test_a3_auto_entities_overlength_returns_none(sem_env) -> None:
    """query >4000 字（附录 A-10 上限）auto 分支返回 None（实体路跳过、检索
    不 400）——超长是输入形态而非调用方参数错误，增益路失败不阻断。"""
    from knowledge_lattice.core.semantic.recall import resolve_query_entities

    long_query = "进项抵扣" * 1200   # 4800 字 > 4000
    ctx = resolve_query_entities(
        sem_env.backend, sem_env.settings, ORG,
        query=long_query, auto_entities=True,
    )
    assert ctx is None, "超长 query auto 分支须返回 None（不阻断检索）"
    # 对照：显式 entities 分支参数错误仍上抛（调用方契约——>20 seeds 400）
    with pytest.raises(ValueError):
        resolve_query_entities(
            sem_env.backend, sem_env.settings, ORG,
            entities=list(range(1, 26)), auto_entities=False,
        )


# ============ A-4 / G-24⑦（裁定①）：mention 补可选 disambiguation ============


def test_a4_mention_carries_disambiguation(disamb_env) -> None:
    """curated disambiguation 的概念 mention 携带该字段（{not, hint} 原样）；
    无 disambiguation 数据的实体不出现该键（向后兼容非决策变更）。"""
    from knowledge_lattice.core.semantic.annotator import (
        annotate_text, clear_annotator_cache,
    )

    clear_annotator_cache()
    out = annotate_text(
        disamb_env.backend, disamb_env.settings, ORG, "进项抵扣怎么办理")
    by_key = {m["entity_key"]: m for m in out["mentions"]}
    m = by_key.get("concept:vat.input_credit")
    assert m is not None, "AC 层须命中（前置——disambiguation 断言的载体）"
    assert m.get("disambiguation") == [
        {"not": "concept:vat.input_transfer_out",
         "hint": "进项转出是抵扣后因用途改变转回，方向相反"}], (
        "mention 契约补可选 disambiguation（design §6.3② L1 行字面——"
        "name + brief + disambiguation）")
    # 对照实体（无 curated disambiguation）不携带该键
    out2 = annotate_text(
        disamb_env.backend, disamb_env.settings, ORG, "进项税额转出的口径")
    m2 = {m["entity_key"]: m for m in out2["mentions"]}.get(
        "concept:vat.input_transfer_out")
    assert m2 is not None
    assert "disambiguation" not in m2, "无数据不出现该键（向后兼容）"


def test_a4_middleware_concept_line_uses_disambiguation() -> None:
    """中间件 L1 概念行消费 disambiguation（§6.3② 字面「概念/系统：name +
    brief + disambiguation」——此前 mention 契约未携带导致中间件无从注入）。"""
    from knowledge_lattice.core.semantic.middleware import inject_l1

    mention = {
        "span": [0, 4], "surface": "进项抵扣", "entity_id": 101,
        "entity_key": "concept:vat.input_credit", "type": "concept",
        "name": "进项税额抵扣", "confidence": 1.0, "via": "ac",
        "ambiguous": False, "brief": "购进货物后按规定抵减销项税额。",
        "disambiguation": [
            {"not": "concept:vat.input_transfer_out",
             "hint": "进项转出是抵扣后因用途改变转回，方向相反"}],
    }
    out = inject_l1([mention], [])
    assert out["injections"] and out["injections"][0]["kind"] == "l1_concept"
    text = out["injections"][0]["text"]
    assert "方向相反" in text, "概念行须携带消歧提示（hint）"
    assert "进项税额抵扣" in text and "抵减销项税额" in text, (
        "name + brief 面保持（§6.3② 三件全）")
    # 对照：无 disambiguation 的概念行不受影响（向后兼容）
    plain = {**mention, "disambiguation": None}
    plain.pop("disambiguation")
    out2 = inject_l1([plain], [])
    assert out2["injections"][0]["text"].endswith("抵减销项税额。")


# ============ B-1 / G-23①：embed_model 入内容集合（模型迁移崩溃窗口） ============


def test_b1_fuzzy_repair_model_migration_crash_window(sem_env) -> None:
    """模型迁移 + ready 切换后 fuzzy 写库崩溃窗口：sem_fuzzy_terms 行仍为
    旧标签（内容集合恰与新期望相等、向量覆盖足够）→ skipped 构建对账**必须
    触发整替修复**（embed_model 入对账集合——修复前集合相等漏修、查询按新
    标签过滤向量层静默为空）。"""
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build

    label = sem_env.settings.embed_model_label   # fake-embed:8
    # 模拟崩溃窗口：ready 后索引写库前崩溃 → 行保留旧标签（内容/向量恰一致）
    sem_env.db.execute(
        "UPDATE sem_fuzzy_terms SET embed_model = ? WHERE org_id = ?",
        ("legacy-model:8", ORG))
    sem_env.db.commit()
    clear_annotator_cache()
    result = run_build(sem_env.backend, ORG, settings=sem_env.settings,
                       embedder=sem_env.embedder)
    assert result["status"] == "skipped"
    assert result["stats"].get("fuzzy_repaired"), (
        "旧标签行（内容集合恰好相等）必须触发修复——embed_model 入对账集合")
    models = {r[0] for r in sem_env.db.execute(
        "SELECT DISTINCT embed_model FROM sem_fuzzy_terms WHERE org_id = ?",
        (ORG,))}
    assert models == {label}, f"整替后全部行为当前标签（got {models}）"


# ============ B-2/B-4 / G-23②④：修复清标记 + 被修复行注记 ============


def test_b2_fuzzy_repair_clears_markers_and_annotates(sem_env) -> None:
    """标记触发面整体移除（G-23① 修法推论——embed_model+内容集合+向量覆盖
    对账完备后标记冗余）：仅标记 True 而索引健康 → **不触发**修复（幂等
    无害整替不再发生）；真实漂移触发修复后：current 行 stats.fuzzy 标记
    清除（粘滞消除）+ repaired 注记入行（观测语义）；skipped 返回与审计
    事件携带 fuzzy_repaired（既有）。"""
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build

    build_id = sem_env.db.execute(
        "SELECT id FROM sem_builds WHERE org_id = ? AND status = 'ready'"
        " ORDER BY id DESC LIMIT 1", (ORG,)).fetchone()[0]

    def _set_marker():
        stats_row = sem_env.db.execute(
            "SELECT stats_json FROM sem_builds WHERE org_id = ? AND id = ?",
            (ORG, build_id)).fetchone()[0]
        stats = json.loads(stats_row)
        stats["fuzzy"] = {
            **(stats.get("fuzzy") or {}), "index_write_failed": True}
        sem_env.db.execute(
            "UPDATE sem_builds SET stats_json = ? WHERE org_id = ? AND id = ?",
            (json.dumps(stats, ensure_ascii=False), ORG, build_id))
        sem_env.db.commit()

    # ① 仅标记（索引健康）→ 不触发修复（标记触发面移除——G-23①）
    _set_marker()
    clear_annotator_cache()
    r1 = run_build(sem_env.backend, ORG, settings=sem_env.settings,
                   embedder=sem_env.embedder)
    assert r1["status"] == "skipped"
    assert not r1["stats"].get("fuzzy_repaired"), (
        "健康索引 + 仅标记 → 不触发整替（标记触发面已移除——内容集合/"
        "向量覆盖对账完备）")

    # ② 真实漂移（删 name 行）+ 标记在 → 修复触发（内容集合对账）
    _set_marker()
    sem_env.db.execute(
        "DELETE FROM sem_fuzzy_terms WHERE org_id = ?"
        " AND kind = 'name'", (ORG,))
    sem_env.db.commit()
    clear_annotator_cache()
    result = run_build(sem_env.backend, ORG, settings=sem_env.settings,
                       embedder=sem_env.embedder)
    assert result["status"] == "skipped"
    assert result["stats"].get("fuzzy_repaired"), "内容漂移触发对账修复"

    after = json.loads(sem_env.db.execute(
        "SELECT stats_json FROM sem_builds WHERE org_id = ? AND id = ?",
        (ORG, build_id)).fetchone()[0])
    fuzzy = after.get("fuzzy") or {}
    assert not fuzzy.get("index_write_failed"), (
        "修复成功须清 current 行标记（G-23② 粘滞消除）")
    assert not fuzzy.get("vec_skipped"), "vec_skipped 标记同面清理"
    assert fuzzy.get("repaired"), "被修复 build 行留 repaired 注记（G-23④）"
    # 索引已修复（name 行回补）
    n = sem_env.db.execute(
        "SELECT count(*) FROM sem_fuzzy_terms WHERE org_id = ?"
        " AND kind = 'name'", (ORG,)).fetchone()[0]
    assert n >= 2, "破坏行已回补"


# ============ B-3 / G-23③（裁定②）：内容哈希快速通过 + 再次 skipped 不重触 ============


def test_b3_fuzzy_skip_fast_path_no_rebuild(sem_env, monkeypatch) -> None:
    """健康索引（哈希一致、无标记、覆盖足够）→ skipped 构建走快速通过：
    build_fuzzy_terms 零调用（per-skip 全量重算收窄）；连续第二次 skipped
    同样不重触（「再次 skipped 不重触」断言）。"""
    from knowledge_lattice.core.semantic import fuzzy as fuzzy_mod
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build

    calls = {"n": 0}
    orig = fuzzy_mod.build_fuzzy_terms

    def counting(*a, **kw):
        calls["n"] += 1
        return orig(*a, **kw)

    monkeypatch.setattr(fuzzy_mod, "build_fuzzy_terms", counting)
    for round_no in (1, 2):
        clear_annotator_cache()
        result = run_build(sem_env.backend, ORG, settings=sem_env.settings,
                           embedder=sem_env.embedder)
        assert result["status"] == "skipped"
        assert not result["stats"].get("fuzzy_repaired"), (
            f"健康索引第 {round_no} 次 skipped 不得触发修复")
    assert calls["n"] == 0, (
        "快速通过路径不得全量重算 build_fuzzy_terms（pypinyin 秒级固定开销——"
        "G-23③ 收窄；两次 skipped 均零调用）")


# ============ B-5 / G-23⑤：构建产物 code versioning 入 dict_rev ============


def test_b5_fuzzy_code_rev_in_dict_rev(monkeypatch) -> None:
    """FUZZY_CODE_REV 入 dict_rev：常量 bump（pinyin/编辑距离算法或规范化
    代码变更）→ 同一快照 dict_rev 变化 → 触发完整重建（含模糊索引）。"""
    from knowledge_lattice.core.semantic import build as build_mod
    from knowledge_lattice.core.semantic import fuzzy as fuzzy_mod

    snapshot = {
        "entities": [{"id": 1, "type": "concept", "key": "k", "name": "名",
                      "parent_id": None, "attrs_json": "{}",
                      "sensitivity": "normal", "curated_json": None}],
        "aliases": [{"entity_id": 1, "alias": "别名", "alias_norm": "别名",
                     "kind": "manual", "match_mode": "exact", "weight": 1}],
        "relations": [],
    }
    rev1 = build_mod.compute_dict_rev(snapshot, embed_model_label="m:8",
                                      yaml_rev=None)
    monkeypatch.setattr(fuzzy_mod, "FUZZY_CODE_REV",
                        fuzzy_mod.FUZZY_CODE_REV + 1)
    rev2 = build_mod.compute_dict_rev(snapshot, embed_model_label="m:8",
                                      yaml_rev=None)
    assert rev1 != rev2, "code version bump 必须改变 dict_rev（触发重建）"


# ============ B 组行为红线：dict_rev 分量可观测（既有口径保持） ============


def test_b5_dict_rev_components_exposes_code_rev(sem_env) -> None:
    """dict_rev_components 暴露 fuzzy_code_rev 分量（A4 运维可观测——变更面
    定位：算法代码变更触发重建时报告可辨）。"""
    from knowledge_lattice.core.semantic.build import dict_rev_components

    snapshot = sem_env.backend.sem_active_snapshot(ORG)
    comp = dict_rev_components(snapshot,
                               embed_model_label=sem_env.settings.embed_model_label,
                               yaml_rev=None)
    assert comp.get("fuzzy_code_rev"), "分量摘要含 fuzzy_code_rev"
