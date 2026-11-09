"""m2s-6 R2 修复（Committer P2×3 + 顺手 P3-3）。

- **P2-1 模糊索引向量链路**：inline 装配断线（app.py WorkerServices 未传
  _embedder）+ 写失败/降级不可自愈（同 dict_rev skip 不补写、失败标记不
  落库）——按用户裁定 5「最终一致+修复路径」：skipped 分支做索引对账
  （行数/向量覆盖率）后补写；失败标记持久化进 build stats（build_report
  可见）；`embed_fn is None` 时 vec_skipped=True（fuzzy.py 不再误报）。
- **P2-2 向量层生产链路**（按 Committer 推荐方案①）：REST/MCP 两端点
  search_entities 注入 settings/embedder（via='vec' 档接线）；工具描述与
  lookup 实际排序链对齐；确定性 embedder 断言 via='vec'/阈值过滤/实体去重；
  A3 向量层生产路径真链路用例（annotate_text(fuzzy=True) → embedder.embed
  → backend.sem_fuzzy_vec_search → 阈值/top-3）。
- **顺手 P3-3**：test_yaml_05_local_ac.py 恒真断言改直接断言（该文件内改，
  本文件不重复覆盖）。

后端覆盖（R3/P3-2 修正——原「sqlite 单后端」为少报）：**8/11 双后端参数化**
（pg 臂覆盖 sem_fuzzy_index_stats / sem_update_build_stats / 修复链与内容
对账）+ **3 条 sqlite 专有**（inline 装配 / REST 端点 / 工具描述常量——
TestClient 栈为 sqlite 形态）。

**R3 增补（P2-2）**：词典收缩 + 等行数改名（计数/覆盖对账盲区）与持久化
失败标记两类内容集合对账触发用例。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from fake_semantic import FakeSourceAdapter
from helpers import seed_org

ORG = "org:tax"
NOW = "2026-11-01 09:00:00"
EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


def _load_seed():
    spec = importlib.util.spec_from_file_location(
        "eval_semantic_seed_r2", EVAL_DIR / "semantic_seed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_semantic_seed_r2"] = mod
    spec.loader.exec_module(mod)
    return mod


# ============ P2-1：模糊索引向量链路收敛 ============


def test_p2_1_inline_build_has_vectors(tmp_path, monkeypatch) -> None:
    """inline 装配修复（app.py WorkerServices 补 _embedder）：inline 模式
    （配置支持的「最小部署显式选项」）下 semantic_build 的模糊索引向量经
    真实 embedder 写入——vec_embedded > 0（修复前恒 0）。"""
    import time

    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.adapters import ADAPTER_FACTORIES
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect
    from knowledge_lattice.store.sqlite.backend import SqliteBackend
    from fake_providers import FakeEmbedder
    from fake_semantic import tpl_snapshot
    from helpers import seed_membership, seed_user

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=2560,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
        worker_poll_s=0.2,
        semantic_sources_json=json.dumps(
            {ORG: {"template_center": {"endpoint": "http://fake/tc"}}}),
    )
    app = create_app(settings, embedder=FakeEmbedder(dim=2560),
                     gate=EmbeddingGate(), run_startup_probe=False)
    monkeypatch.setitem(
        ADAPTER_FACTORIES, "template_center",
        lambda org, cfg: FakeSourceAdapter("template_center", tpl_snapshot(2)))

    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    conn.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                 (hash_token("dev-static-admin-tax"), "admin_tax"))
    conn.commit()

    with TestClient(app) as client:
        h = {"Authorization": "Bearer dev-static-admin-tax"}
        resp = client.post(f"/api/orgs/{ORG}/semantic/sync/template_center",
                           headers=h)
        assert resp.status_code == 202
        # 同步成功自动投递 build；inline kick/兜底循环消化
        t0 = time.monotonic()
        done = 0
        while time.monotonic() - t0 < 60.0:
            done = conn.execute(
                "SELECT count(*) FROM tasks WHERE type = 'semantic_build'"
                " AND status = 'done'").fetchone()[0]
            if done:
                break
            time.sleep(0.1)
        assert done, "inline worker 应消化 semantic_build 任务"

        stats = SqliteBackend(conn).sem_fuzzy_index_stats(ORG)
        assert stats["terms"] > 0
        assert stats["vec_embedded"] > 0, (
            "inline 模式 build 应经真实 embedder 写入向量（P2-1 断线修复）")
    conn.close()


@pytest.fixture()
def repair_env(backend, tmp_path):
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_providers import FakeEmbedder

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        embed_model="fake-embed")
    b = backend.make_backend()
    embedder = FakeEmbedder(dim=8, model_name="fake-embed")
    records: list = []           # 全量快照语义（run_sync——防删除比例保护误触）

    def build(**kw):
        clear_annotator_cache()
        return run_build(b, ORG, settings=settings, **kw)

    def add_entity(key: str, name: str):
        records.append(EntityRecord(type="concept", key=key, name=name))
        run_sync(b, ORG, FakeSourceAdapter("tc", list(records)),
                 settings=settings, snapshot=list(records), now=NOW)

    return SimpleNamespace(db=backend, backend=b, settings=settings,
                           embedder=embedder, build=build,
                           add_entity=add_entity, records=records)


def test_p2_1_write_failure_persisted_and_skipped_repairs(
        repair_env, monkeypatch) -> None:
    """写失败 → index_write_failed **持久化**进 build stats（build_report
    可见）→ 同 dict_rev 的后续 skipped 构建对账补写修复（真实收敛路径——
    裁定 5「最终一致+修复路径」）。"""
    env = repair_env
    env.add_entity("c.a", "甲概念")
    assert env.build(embedder=env.embedder)["status"] == "ready"
    assert env.backend.sem_fuzzy_index_stats(ORG)["vec_embedded"] > 0

    # 新 rev 构建注入写失败（词典变更 → 不 skip）
    env.add_entity("c.b", "乙概念")
    real_replace = env.backend.sem_fuzzy_replace

    def boom(*a, **kw):
        raise RuntimeError("injected write failure")

    monkeypatch.setattr(env.backend, "sem_fuzzy_replace", boom)
    result = env.build(embedder=env.embedder)
    assert result["status"] == "ready", "模糊索引写失败不阻断构建"
    monkeypatch.setattr(env.backend, "sem_fuzzy_replace", real_replace)

    # 失败标记持久化：build_report（读库内 stats_json）可见
    from knowledge_lattice.core.semantic.build import build_report

    report = build_report(env.backend, ORG, result["build_id"])
    assert report["fuzzy"].get("index_write_failed") is True, (
        "index_write_failed 须持久化进 build 行 stats（build_report 可见）")
    # 索引仍是旧词典（terms 未变——写失败未生效）
    stats_after_fail = env.backend.sem_fuzzy_index_stats(ORG)
    terms_before = stats_after_fail["terms"]

    # 同 dict_rev 的后续构建 → skipped + 对账补写修复
    repaired = env.build(embedder=env.embedder)
    assert repaired["status"] == "skipped", "同 rev 构建应 skipped"
    assert repaired["stats"].get("fuzzy_repaired"), (
        "skipped 分支应对账补写并注记 fuzzy_repaired")
    stats_fixed = env.backend.sem_fuzzy_index_stats(ORG)
    assert stats_fixed["terms"] > terms_before, "新词典 term 行补写到位"
    assert stats_fixed["vec_embedded"] > 0, "向量随修复写入"
    # 满覆盖基准 = 可嵌行数（code/sync 键不嵌——NULL 属预期，P2-2/R2）
    from knowledge_lattice.core.semantic.fuzzy import build_fuzzy_terms

    _t, _d, expect = build_fuzzy_terms(
        env.backend.sem_active_snapshot(ORG), None,
        embed_model_label=env.settings.embed_model_label)
    assert stats_fixed["terms"] == expect["terms"]
    assert stats_fixed["vec_embedded"] == expect["vec_expected"], (
        "向量覆盖率补齐到可嵌基准（修复路径完整）")


def test_p2_1_vec_degraded_then_skipped_repairs(repair_env) -> None:
    """embedder 缺失构建（vec 全空）→ 有 embedder 的后续 skipped 构建对账
    补齐向量（vec_embedded == terms）——降级自愈路径。"""
    env = repair_env
    env.add_entity("c.x", "丙概念")
    assert env.build(embedder=None)["status"] == "ready"   # 降级：向量空
    degraded = env.backend.sem_fuzzy_index_stats(ORG)
    assert degraded["terms"] > 0 and degraded["vec_embedded"] == 0

    repaired = env.build(embedder=env.embedder)            # 同 rev → skipped
    assert repaired["status"] == "skipped"
    assert repaired["stats"].get("fuzzy_repaired")
    fixed = env.backend.sem_fuzzy_index_stats(ORG)
    assert fixed["vec_embedded"] > 0, (
        "有 embedder 的 skipped 构建应补齐向量覆盖（降级自愈——0 → 可嵌基准）")


def test_p2_1_no_repair_when_consistent(repair_env) -> None:
    """索引一致时 skipped 构建零补写（对账不空转——幂等收敛）。"""
    env = repair_env
    env.add_entity("c.y", "丁概念")
    env.build(embedder=env.embedder)
    again = env.build(embedder=env.embedder)
    assert again["status"] == "skipped"
    assert not again["stats"].get("fuzzy_repaired"), "一致态不触发补写"


def test_r3_p2_2_shrink_and_rename_triggers_repair(repair_env,
                                                   monkeypatch) -> None:
    """R3 P2-2：内容集合对账——**词典收缩**与**等行数改名**两类陈旧（纯
    计数/覆盖对账的盲区）都须触发 skipped 修复（裁定 5「最终一致」）。

    场景 A（收缩）：两实体 ready → 收缩为一实体（行数减少）+ 写失败 →
    现存行数 > 期望（旧索引行更多）——计数对账不触发、内容对账必须触发。
    场景 B（等行数改名）：同数量实体换名（text_norm 集合不同）——行数与
    向量覆盖全等、内容集合不同，必须触发。"""
    from knowledge_lattice.core.semantic.fuzzy import build_fuzzy_terms

    env = repair_env
    env.add_entity("c.a", "甲概念")
    env.add_entity("c.b", "乙概念")
    env.build(embedder=env.embedder)
    assert env.backend.sem_fuzzy_index_stats(ORG)["vec_embedded"] > 0

    def _expected_norms() -> set[tuple]:
        rows, _d, _s = build_fuzzy_terms(
            env.backend.sem_active_snapshot(ORG), None,
            embed_model_label=env.settings.embed_model_label)
        return {(r["entity_id"], r["kind"], r["text_norm"]) for r in rows}

    # ---- 场景 A：收缩（移除 c.b——快照语义全量替换）+ 写失败 ----
    env.records[:] = [r for r in env.records if r.key != "c.b"]
    from knowledge_lattice.core.semantic.sync import run_sync

    # 缩容 run + 宽限推进 run（now+9d：c.b missing 超 7 天宽限 → retired
    # 出快照——terms 期望收缩；retired 实体不进 build_fuzzy_terms 输入）。
    # force=true：缩容 50% 触发删除比例保护——B2 运维放行口径（合法收缩）
    run_sync(env.backend, ORG, FakeSourceAdapter("tc", list(env.records)),
             settings=env.settings, snapshot=list(env.records), now=NOW,
             force=True)
    run_sync(env.backend, ORG, FakeSourceAdapter("tc", list(env.records)),
             settings=env.settings, snapshot=list(env.records),
             now="2026-11-10 09:00:00", force=True)

    def boom(*a, **kw):
        raise RuntimeError("injected write failure")

    real_replace = env.backend.sem_fuzzy_replace
    monkeypatch.setattr(env.backend, "sem_fuzzy_replace", boom)
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache

    clear_annotator_cache()
    from knowledge_lattice.core.semantic.build import run_build

    shrunk = run_build(env.backend, ORG, settings=env.settings,
                       embedder=env.embedder)
    assert shrunk["status"] == "ready"
    monkeypatch.setattr(env.backend, "sem_fuzzy_replace", real_replace)
    stats_after = env.backend.sem_fuzzy_index_stats(ORG)
    assert stats_after["terms"] > 0, "写失败后旧索引仍在"

    repaired = run_build(env.backend, ORG, settings=env.settings,
                         embedder=env.embedder)   # 同 rev → skipped
    assert repaired["status"] == "skipped"
    assert repaired["stats"].get("fuzzy_repaired"), (
        "词典收缩后的陈旧索引（行数不少反多）必须经内容集合对账触发修复")
    have = {(r["entity_id"], r["kind"], r["text_norm"])
            for r in env.backend.sem_fuzzy_terms_all(ORG)}
    assert have == _expected_norms(), "修复后索引内容 = 当前快照期望集合"

    # ---- 场景 B：等行数改名（text_norm 集合变化、行数/向量覆盖不变）----
    for r in env.records:
        if r.key == "c.a":
            r.name = "甲概念改名"
    run_sync(env.backend, ORG, FakeSourceAdapter("tc", list(env.records)),
             settings=env.settings, snapshot=list(env.records), now=NOW,
             force=True)
    clear_annotator_cache()
    # 改名构建同样注入写失败——索引停留在改名前内容（行数/覆盖全等的陈旧）
    monkeypatch.setattr(env.backend, "sem_fuzzy_replace", boom)
    renamed = run_build(env.backend, ORG, settings=env.settings,
                        embedder=env.embedder)
    assert renamed["status"] == "ready"
    monkeypatch.setattr(env.backend, "sem_fuzzy_replace", real_replace)
    # 等行数改名后 skipped：内容集合对账触发
    again = run_build(env.backend, ORG, settings=env.settings,
                      embedder=env.embedder)
    assert again["status"] == "skipped"
    assert again["stats"].get("fuzzy_repaired"), (
        "等行数改名的陈旧（计数/覆盖全等、内容不同）必须触发修复")
    have_b = {(r["entity_id"], r["kind"], r["text_norm"])
              for r in env.backend.sem_fuzzy_terms_all(ORG)}
    assert have_b == _expected_norms()


def test_r3_p2_2_persisted_marker_no_longer_triggers_repair(repair_env) -> None:
    """R3 P2-2 持久化标记的观测与清面语义——**m3-3 G-23① 裁定后口径更新**：
    embed_model 入内容集合 + 内容/向量覆盖对账完备后，``index_write_failed``
    标记的**触发面整体移除**（健康索引仅标记 True 不再触发幂等整替——
    「即使内容集合恰好一致也应触发」的 m2s-6 旧口径作废）；标记保留写入
    与清面语义：真实漂移触发修复时一并清除（见 test_b2——m3-3）。
    〔m3-4 P3-6 更名：原名 ``..._persisted_marker_triggers_repair`` 与
    m3-3 后断言语义相反（标记**不**触发修复）——名称对齐语义。〕"""
    from knowledge_lattice.core.semantic.build import run_build

    env = repair_env
    env.add_entity("c.m", "戊概念")
    env.build(embedder=env.embedder)

    # 人工把 current 行 stats 的 fuzzy.index_write_failed 置 True（模拟崩溃
    # 前已持久化标记、索引内容却恰好完整的场景）
    current = env.backend.sem_current_build(ORG)
    import json as _json

    raw = current["stats_json"]
    stats = _json.loads(raw) if isinstance(raw, str) else dict(raw)
    stats.setdefault("fuzzy", {})["index_write_failed"] = True
    env.backend.sem_update_build_stats(
        ORG, current["id"], _json.dumps(stats, ensure_ascii=False))

    again = env.build(embedder=env.embedder)
    assert again["status"] == "skipped"
    assert not again["stats"].get("fuzzy_repaired"), (
        "健康索引 + 仅标记 → 不触发整替（标记触发面移除——m3-3 G-23①："
        "embed_model 入集合后内容/覆盖对账完备，幂等整替的粘滞成本消除）")


def test_p2_1_embedder_none_marks_vec_skipped(backend, tmp_path) -> None:
    """fuzzy.build_fuzzy_terms：embed_fn 缺失且有待嵌行 → vec_skipped=True
    （构建报告不再误报「未降级」）。"""
    from knowledge_lattice.core.semantic.fuzzy import build_fuzzy_terms

    snapshot = {"entities": [{"id": 1, "type": "concept", "key": "k",
                              "name": "概念甲", "curated_json": "{}",
                              "sensitivity": "normal"}],
                "aliases": [], "relations": []}
    _terms, _dels, stats = build_fuzzy_terms(snapshot, None,
                                             embed_model_label="m:8")
    assert stats["terms"] > 0
    assert stats["vec_skipped"] is True, "embed_fn=None 须标记降级"


# ============ P2-2：向量层生产链路 + search_entities 端点接线 ============


class _MappingEmbedder:
    """按文本映射确定性向量（无映射文本 → 与映射向量正交的基向量）。"""

    def __init__(self, dim: int, mapping: dict[str, list[float]],
                 *, model_name: str = "fake-embed") -> None:
        self.dim = dim
        self.mapping = {k: list(v) for k, v in mapping.items()}
        self.model_name = model_name
        base = [0.0] * dim
        base[dim - 1] = 1.0
        self._default = base

    @property
    def model_label(self) -> str:
        return f"{self.model_name}:{self.dim}"

    def embed(self, texts):
        return [list(self.mapping.get(t, self._default)) for t in texts]


@pytest.fixture()
def vec_env(backend, tmp_path):
    """向量层专用栈：两个概念实体，term 向量经映射 embedder 精确控制。"""
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        embed_model="fake-embed")
    b = backend.make_backend()
    dim = 8
    v0 = [1.0] + [0.0] * (dim - 1)
    v1 = [0.0, 1.0] + [0.0] * (dim - 2)
    # 「完税证明」：与词典零字面/拼音/编辑距离关系、向量 == v0（近邻面）
    embedder = _MappingEmbedder(dim, {"扣税凭证": v0, "留抵税额": v0,
                                      "免税政策": v1, "完税证明": v0})
    recs = [
        EntityRecord(type="concept", key="c.voucher", name="扣税凭证",
                     aliases=("留抵税额",)),       # 同实体双 term（去重面）
        EntityRecord(type="concept", key="c.exempt", name="免税政策"),
    ]
    run_sync(b, ORG, FakeSourceAdapter("tc", recs), settings=settings,
             snapshot=list(recs), now=NOW)
    clear_annotator_cache()
    assert run_build(b, ORG, settings=settings,
                     embedder=embedder)["status"] == "ready"
    return SimpleNamespace(db=backend, backend=b, settings=settings,
                           embedder=embedder, v0=v0, v1=v1, dim=dim)


def test_p2_2_vec_via_threshold_and_dedup(vec_env) -> None:
    """search_entities 向量层三断言：via='vec' 命中（「完税证明」与词典零
    字面/拼音/编辑距离关系、向量近邻 v0）/ 阈值以下过滤（正交向量 sim=0）/
    同实体多 term 去重（c.voucher 的 name+alias 双 term 同向量）。"""
    from knowledge_lattice.core.semantic.lookup import search_entities

    env = vec_env
    out = search_entities(env.backend, ORG, "完税证明", top_k=10,
                          settings=env.settings, embedder=env.embedder)
    vec_rows = [e for e in out["entities"] if e["via"] == "vec"]
    assert vec_rows, "映射向量命中 term 应经 via='vec' 返回"
    keys = [e["key"] for e in vec_rows]
    assert "c.voucher" in keys and "c.exempt" not in keys
    assert len(keys) == len(set(keys)), "同实体多 term（name+alias）去重"

    # 正交查询：default 向量与 v0/v1 正交 → sim=0 < 0.75 全过滤
    orthogonal = _MappingEmbedder(env.dim, {})  # 恒 default（基向量 dim-1 位）
    out2 = search_entities(env.backend, ORG, "完税证明", top_k=10,
                           settings=env.settings, embedder=orthogonal)
    assert not [e for e in out2["entities"] if e["via"] == "vec"], (
        "阈值（0.75）以下向量命中必须过滤")


def test_p2_2_annotate_fuzzy_vec_production_chain(vec_env) -> None:
    """A3 向量层**生产路径**真链路（Committer 口径）：annotate_text(fuzzy=True)
    → embedder.embed（内部缺省通道）→ backend.sem_fuzzy_vec_search → 阈值/
    top-3 生效——无任何注入/monkeypatch。fragment「抵扣」（jieba 独立名词
    片段）与本词典零字面/拼音/编辑距离关系（「扣税凭证」拼音/编辑距离均远）。"""
    from knowledge_lattice.core.semantic.annotator import annotate_text

    env = vec_env
    # 映射缺失 → default 正交 → 不命中（阈值过滤的生产路径面）
    r0 = annotate_text(env.backend, env.settings, ORG, "抵扣怎么开具",
                       fuzzy=True, embedder=env.embedder)
    assert not [c for c in r0["candidates"]
                if c.get("fuzzy_layer") == "vec"]

    # 映射加「抵扣」→ v0：经 embed→vec_search→top-3 真链路命中
    env.embedder.mapping["抵扣"] = env.v0
    r1 = annotate_text(env.backend, env.settings, ORG, "抵扣怎么开具",
                       fuzzy=True, embedder=env.embedder)
    hits = [c for c in r1["candidates"] if c.get("fuzzy_layer") == "vec"]
    assert hits, "向量层生产链路应命中"
    assert hits[0]["entity_key"] == "concept:c.voucher"
    assert hits[0]["confidence"] == 0.55
    assert hits[0]["sim"] == pytest.approx(1.0, abs=1e-3)


def test_p2_2_search_entities_rest_endpoint_vec(tmp_path, monkeypatch) -> None:
    """REST /semantic/entities 端点接线：settings/embedder 注入后 via='vec'
    档在真实端点出现（修复前恒跳层）。自建栈保证 build 期与查询期同一
    embedder（FixedVec——任意文本同向量，sim=1.0 全命中）。"""
    import time

    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.adapters import ADAPTER_FACTORIES
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect
    from fake_providers import FixedVecEmbedder
    from helpers import seed_membership, seed_user

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=2560,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
        worker_poll_s=0.2,
        semantic_sources_json=json.dumps(
            {ORG: {"template_center": {"endpoint": "http://fake/tc"}}}),
    )
    embedder = FixedVecEmbedder([1.0] + [0.0] * 2559, model_name="fake-embed")
    app = create_app(settings, embedder=embedder, gate=EmbeddingGate(),
                     run_startup_probe=False)
    from fake_semantic import tpl_snapshot

    monkeypatch.setitem(
        ADAPTER_FACTORIES, "template_center",
        lambda org, cfg: FakeSourceAdapter("template_center", tpl_snapshot(2)))

    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    conn.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                 (hash_token("dev-static-admin-tax"), "admin_tax"))
    conn.commit()
    with TestClient(app) as client:
        h = {"Authorization": "Bearer dev-static-admin-tax"}
        resp = client.post(f"/api/orgs/{ORG}/semantic/sync/template_center",
                           headers=h)
        assert resp.status_code == 202
        t0 = time.monotonic()
        while time.monotonic() - t0 < 60.0:
            if conn.execute(
                    "SELECT count(*) FROM tasks WHERE type ="
                    " 'semantic_build' AND status = 'done'").fetchone()[0]:
                break
            time.sleep(0.1)
        # 查询词与词典零字面/拼音关系（「zzz」）——via='vec' 是唯一来源
        out = client.get(f"/api/orgs/{ORG}/semantic/entities",
                         params={"q": "zzz"}, headers=h).json()
        vec_rows = [e for e in out["entities"] if e["via"] == "vec"]
        assert vec_rows, "REST 端点应接线向量层（settings/embedder 注入）"
        assert all(e["score"] == pytest.approx(1.0) for e in vec_rows)
    conn.close()


def test_p2_2_tool_descriptions_updated() -> None:
    """工具描述对齐（P2-2 + P3-11 顺手）：search_entities 描述含拼音+向量
    档；search 描述含 entities/auto_entities 参数。"""
    from knowledge_lattice.mcp.server import (
        SEARCH_ENTITIES_TOOL_DESCRIPTION,
        SEARCH_TOOL_DESCRIPTION,
    )

    assert "拼音" in SEARCH_ENTITIES_TOOL_DESCRIPTION
    assert "向量" in SEARCH_ENTITIES_TOOL_DESCRIPTION
    assert "归后续段" not in SEARCH_ENTITIES_TOOL_DESCRIPTION
    assert "entities" in SEARCH_TOOL_DESCRIPTION
    assert "auto_entities" in SEARCH_TOOL_DESCRIPTION
