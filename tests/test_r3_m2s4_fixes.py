"""m2s-4 R3 修复（R2 Committer NEEDS_CHANGES → 用户裁定「按建议执行」）：

- **P1-1**：render_l0 滤 restricted（fail-closed——L0 是 agent system prompt
  输入面，正文泄露比 alias 命中严重；M2-S3 权限面后按 semantic:restricted
  放行）+ 双后端永久用例（YAML 覆盖层造 restricted+l0 → 片段不可见、构建
  报告 ambiguous_aliases 不含其 alias_norm）；
- **P2-1 方案 B**：`/semantic/l0` 与 annotate **同锚点**（同一 get_annotator
  取数路径——消除 sync→build 窗口内容/rev 错配）+ 永久用例钉死**冷缓存**
  行为（构建中/评测拦下后：服务 live 字典 + 响应旧 ready dict_rev——
  known-gaps **G-21** 登记项，方案 A 承接 M2-S3/m2-5）；
- **P2-2**：ambiguity 分母只统计**歧义 span 标注**（多实体共享同一
  alias_norm 的 span——词典侧判定；不含条目内伴随确定性标注）；
- **P2-3**：ac_automaton meta 透传 get_stats() 的 memory_bytes/edges/words；
- **覆盖缺口④**：全角输入经 annotate 永久用例（ＪＸＤＫ 全角折叠命中 /
  XJXDKX 词边界不命中 / 独立 JXDK 命中——TC-SEM-01 拉丁面永久证据）；
- **P3 顺手**：P3-1 `_cand_ids` 统一 pop（输出无下划线私有键）；P3-2 裸
  JSON → 400；P3-10 `_worker_env` 补两键映射；P3-11 `items is True/False`
  显式判断 + boolean items 在 errors 处理。
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
                           settings=settings, repo=tmp_path / "yamlrepo")


def _sync(env, records, *, adapter="template_center", now=NOW):
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.core.semantic.sync import run_sync

    return run_sync(env.backend, ORG, FakeSourceAdapter(adapter, records),
                    settings=env.settings, snapshot=list(records), now=now)


def _yaml_sync(env, files: dict, *, now=NOW):
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
                         settings=env.settings, now=now)


def _build(env, **kw):
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build

    clear_annotator_cache()
    return run_build(env.backend, ORG, settings=env.settings, **kw)


# ---- P1-1：restricted+l0 → L0 导出/报告不可见（双后端） ----


def test_p1_1_restricted_l0_entity_invisible_in_l0_and_report(env) -> None:
    """YAML 覆盖层造 restricted+l0 实体：`/semantic/l0` 片段不可见、构建
    报告 ambiguous_aliases 不含其 alias_norm（识别面 restricted 不参与——
    P1-1 fail-closed；M2-S3 权限面后按 semantic:restricted 放行）。"""
    from knowledge_lattice.core.semantic.records import EntityRecord

    # 两同步模板实体 + templates/ 覆盖层（concepts/=纯人工域，撞同步实体
    # 会被规则表第 3 行剔除——restricted+l0 的合法 YAML 形态走覆盖层）：
    # 正常 l0 条目 + restricted+l0 条目（别名「共享面」与公开侧构成歧义
    # ——报告歧义清单的识别面口径不含 restricted 侧）
    _sync(env, [
        EntityRecord(type="template", key="TPL_OPEN", name="公开模板"),
        EntityRecord(type="template", key="TPL_SECRET", name="机密模板",
                     aliases=("共享面",)),
    ])
    _yaml_sync(env, {
        "templates/a.yaml": (
            "- id: template:TPL_OPEN\n  owner: o\n"
            "  definition: 公开模板的定义正文。\n  l0: true\n"),
        "templates/b.yaml": (
            "- id: template:TPL_SECRET\n  owner: o\n  aliases: [共享面]\n"
            "  definition: 机密模板的限制正文。\n  l0: true\n"
            "  sensitivity: restricted\n"),
    })
    result = _build(env)
    assert result["status"] == "ready", result

    # L0 导出（/semantic/l0 数据源——P2-1 起与 annotate 同锚点）
    from knowledge_lattice.core.semantic.annotator import (
        clear_annotator_cache, get_annotator, render_l0,
    )

    clear_annotator_cache()
    ann, rev = get_annotator(env.backend, ORG, env.settings)
    assert rev == result["dict_rev"]
    l0 = render_l0(ann.snapshot)
    texts = json.dumps(l0, ensure_ascii=False)
    assert "公开模板" in texts
    assert "机密模板" not in texts and "限制正文" not in texts

    # 构建报告：识别面歧义别名清单不含 restricted 实体的 alias_norm
    from knowledge_lattice.core.semantic.build import build_report

    report = build_report(env.backend, ORG, result["build_id"])
    norms = [a["alias_norm"] for a in report["ambiguous_aliases"]]
    assert "共享面" not in norms          # restricted 侧不构成识别面歧义
    # restricted 实体本身在 annotate 面亦不可见（T-S9 既有口径复核）
    assert ann.annotate("机密模板与共享面的口径")["mentions"] == []


# ---- P2-1 方案 B：/semantic/l0 与 annotate 同锚点 + 冷缓存行为钉死 ----


def test_p2_1_l0_same_anchor_and_cold_cache_live_with_old_rev(env) -> None:
    """构建中冷缓存（sync→build 窗口/重启形态）：annotate 与 /semantic/l0
    **同一 get_annotator 实例**——服务 live 字典 + 响应旧 ready dict_rev
    （known-gaps **G-21** 方案 B 钉死：内容/rev 错配两侧一致、不再 l0 独读
    live；方案 A〔build 快照附表〕M2-S3/m2-5 承接）。"""
    from knowledge_lattice.core.semantic.annotator import (
        annotate_text, clear_annotator_cache, get_annotator, render_l0,
    )
    from knowledge_lattice.core.semantic.records import EntityRecord

    _sync(env, [EntityRecord(type="concept", key="c.base", name="基线概念")])
    r1 = _build(env)
    assert r1["status"] == "ready"

    # live 前进（新 sync、尚未构建）——模拟构建中冷缓存（清缓存=重启形态）
    _sync(env, [EntityRecord(type="concept", key="c.base", name="基线概念"),
                EntityRecord(type="concept", key="c.new", name="窗口新概念")])
    clear_annotator_cache()

    ann_a, rev_a = get_annotator(env.backend, ORG, env.settings)
    ann_b, rev_b = get_annotator(env.backend, ORG, env.settings)
    assert ann_a is ann_b and rev_a == rev_b == r1["dict_rev"]  # 同锚点单例
    # 服务 live 字典（窗口新概念可命中）+ 响应旧 ready rev——G-21 登记形态
    assert ann_a.annotate("窗口新概念是什么")["mentions"]
    out = annotate_text(env.backend, env.settings, ORG, "窗口新概念是什么")
    assert out["mentions"] and out["dict_rev"] == r1["dict_rev"]
    # /semantic/l0 同锚点：内容与 rev 与 annotate 一致（不再恒读 live 裸快照）
    l0 = render_l0(ann_a.snapshot)
    assert l0["fragments"] or l0["token_estimate"] >= 0
    assert get_annotator(env.backend, ORG, env.settings)[1] == out["dict_rev"]


def test_p2_1_eval_blocked_cold_cache_serves_gated_dict_g21(env) -> None:
    """评测拦下后冷缓存：被拦词典已在 live 表、build failed 不切 ready——
    重启（清缓存）后 annotate 服务被拦词典 + 响应旧 ready dict_rev（G-21：
    评测门禁治理语义仅进程生命周期内的对冲已登记；门禁在构建路径内仍有效）。"""
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

    clear_annotator_cache()   # 重启/冷缓存形态
    out = annotate_text(env.backend, env.settings, ORG, "被拦概念的口径")
    # G-21 钉死：服务 live（被拦）词典 + 响应旧 ready rev
    assert out["mentions"], "冷缓存应服务 live 字典（G-21 登记行为）"
    assert out["dict_rev"] == r1["dict_rev"]


# ---- P2-2：ambiguity 分母只统计歧义 span 标注 ----


class _StubAnnotator:
    """可控 stub（run_recognition_eval 只调 annotate(text)）——P2-2 口径
    用例：20 歧义条目（各 1 个「甲」歧义 span）+ 5 伴随确定性标注（乙），
    按文本判定故意答错 3 个歧义。"""

    def __init__(self, wrong_texts: set[str]):
        self.wrong_texts = wrong_texts

    def annotate(self, text: str, **kw) -> dict:
        mentions = []
        if "甲" in text:
            start = text.index("甲")
            key = "concept:amb.wrong" if text in self.wrong_texts \
                else "concept:amb.right"
            mentions.append({"span": [start, start + 1], "surface": "甲",
                             "entity_key": key})
        if "乙" in text:
            start = text.index("乙")
            mentions.append({"span": [start, start + 1], "surface": "乙",
                             "entity_key": "concept:sure"})
        return {"mentions": mentions, "candidates": []}


def _p2_2_snapshot():
    return {
        "entities": [
            {"id": 1, "type": "concept", "key": "amb.right", "name": "甲正",
             "parent_id": None, "attrs_json": "{}", "sensitivity": "normal",
             "curated_json": "{}", "curated_rev": None},
            {"id": 2, "type": "concept", "key": "amb.wrong", "name": "甲误",
             "parent_id": None, "attrs_json": "{}", "sensitivity": "normal",
             "curated_json": "{}", "curated_rev": None},
            {"id": 3, "type": "concept", "key": "sure", "name": "乙",
             "parent_id": None, "attrs_json": "{}", "sensitivity": "normal",
             "curated_json": "{}", "curated_rev": None},
        ],
        "aliases": [
            {"entity_id": 1, "alias": "甲", "alias_norm": "甲", "kind": "manual",
             "match_mode": "exact", "weight": 1.0},
            {"entity_id": 2, "alias": "甲", "alias_norm": "甲", "kind": "manual",
             "match_mode": "exact", "weight": 1.0},
            {"entity_id": 3, "alias": "乙", "alias_norm": "乙", "kind": "name",
             "match_mode": "exact", "weight": 1.0},
        ],
        "relations": [],
    }


def test_p2_2_ambiguity_denominator_only_ambiguous_spans() -> None:
    """分母=歧义 span 标注（同一 alias_norm 多实体共享——词典侧判定）；
    伴随确定性标注（乙）不稀释：答错 3 条 → 17/20=0.85 卡边（旧条目级口径
    22/25=0.88 会放行——稀释实证）。"""
    from knowledge_lattice.core.semantic.evalrun import run_recognition_eval

    # 20 条歧义条目（每条 1 个「甲」歧义 span）；前 3 条带伴随「乙」确定性
    # 标注（s106/s107/s108 形态：歧义条目内混入确定性命中）——歧义 span
    # 标注 20、伴随 3；另加 2 条纯「乙」条目（伴随确定性标注补足 5）
    items = []
    wrong_texts = set()
    for i in range(1, 21):
        prefix = "乙" if i <= 3 else ""
        text = f"{prefix}问题甲{i:02d}怎么处理"
        start = text.index("甲")
        labels = [["concept:amb.right", start, start + 1]]
        if prefix:
            labels.append(["concept:sure", 0, 1])   # 乙在首位
        items.append({"qid": f"a{i:03d}", "kind": "pos_ambiguous",
                      "lang": "zh", "text": text, "labels": labels})
        if i in (2, 5, 9):                 # 答错的 3 个歧义条目
            wrong_texts.add(text)
    for i in range(1, 3):
        items.append({"qid": f"b{i:03d}", "kind": "pos_alias",
                      "lang": "zh", "text": f"第{i}笔乙的业务",
                      "labels": [["concept:sure", 2, 3]]})

    stub = _StubAnnotator(wrong_texts=wrong_texts)
    m = run_recognition_eval(stub, items, _p2_2_snapshot())
    # 歧义 span 标注 20（伴随「乙」不计分母）；答对 17 → 0.85 卡边
    assert m["_counts"]["ambiguous_labeled"] == 20
    assert m["_counts"]["ambiguous_correct"] == 17
    assert m["ambiguity"] == pytest.approx(0.85)
    # 伴随确定性标注不稀释：precision/recall 均满（乙命中在、甲答错只影响
    # ambiguity 分子）；旧条目级口径（23 标注计分母）会得 20/23≈0.87 放行


def test_p2_2_golden_ambiguity_recomputed_on_reference(env,
                                                       tmp_path) -> None:
    """黄金集在参考词典上重算：歧义分母=20（25 标注去 5 伴随）、全对 →
    ambiguity=1.0；precision/recall/neg_fp 不受口径影响。"""
    import importlib.util
    import sys
    from pathlib import Path

    from knowledge_lattice.core.semantic.annotator import Annotator
    from knowledge_lattice.core.semantic.evalrun import (
        load_golden, run_recognition_eval,
    )

    eval_dir = Path(__file__).resolve().parent.parent / "eval"
    spec = importlib.util.spec_from_file_location(
        "eval_semantic_seed_r3", eval_dir / "semantic_seed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_semantic_seed_r3"] = mod
    spec.loader.exec_module(mod)
    mod.seed_reference_org(env.backend, ORG, env.settings,
                           repo_dir=tmp_path / "yamlrepo")
    snapshot = env.backend.sem_active_snapshot(ORG)
    ann = Annotator(snapshot)
    items = load_golden(eval_dir / "semantic_golden.jsonl")
    m = run_recognition_eval(ann, items, snapshot)
    assert m["_counts"]["ambiguous_labeled"] == 20   # 25−5 伴随
    assert m["ambiguity"] == pytest.approx(1.0)
    assert m["precision"] == pytest.approx(1.0)
    assert m["recall"] == pytest.approx(1.0)
    assert m["neg_fp"] == pytest.approx(0.0)


# ---- P2-3：ac_automaton meta 内存/边/词量 ----


def test_p2_3_automaton_meta_memory_edges_words(env) -> None:
    """任务 A1「内存占用与构建耗时纳入构建报告」——get_stats() 透传
    memory_bytes（total_size）/edges（links_count）/words（words_count）。"""
    from knowledge_lattice.core.semantic.records import EntityRecord

    _sync(env, [EntityRecord(type="concept", key="c.x", name="进项概念",
                             aliases=("进项面",))])
    result = _build(env)
    assert result["status"] == "ready"
    from knowledge_lattice.core.semantic.build import build_report

    report = build_report(env.backend, ORG, result["build_id"])
    auto = report["ac_automaton"]
    assert {"keys", "nodes", "build_ms", "memory_bytes", "edges",
            "words"} <= set(auto)
    assert auto["words"] >= 2              # name + code + sync 别名 ≥2 词
    assert auto["edges"] >= auto["keys"]   # trie 边数 ≥ 词数
    assert auto["memory_bytes"] > 0        # sizeof_node×nodes（字节）


# ---- 覆盖缺口④：全角输入经 annotate（TC-SEM-01 拉丁面永久证据） ----


def test_fullwidth_and_case_boundary_permanent() -> None:
    """全角ＪＸＤＫ 折叠命中 / XJXDKX 词边界不命中（大小写折叠后边界仍拦）/
    独立 JXDK 命中——TC-SEM-01 拉丁面永久用例（探针曾覆盖、已删）。"""
    from knowledge_lattice.core.semantic.annotator import Annotator

    snap = {
        "entities": [{"id": 1, "type": "concept", "key": "vat.x", "name": "概念甲",
                      "parent_id": None, "attrs_json": "{}",
                      "sensitivity": "normal", "curated_json": "{}",
                      "curated_rev": None}],
        "aliases": [{"entity_id": 1, "alias": "JXDK", "alias_norm": "jxdk",
                     "kind": "abbr", "match_mode": "exact", "weight": 1.0}],
        "relations": [],
    }
    ann = Annotator(snap)
    assert ann.annotate("本月的ＪＸＤＫ怎么算")["mentions"], "全角折叠命中"
    assert ann.annotate("XJXDKX 是随机串")["mentions"] == [], "词边界不命中"
    assert ann.annotate("独立 JXDK 才是缩写")["mentions"], "独立命中"
    assert ann.annotate("小写 jxdk 也命中")["mentions"], "大小写折叠"


# ---- P3-1：输出无下划线私有键 ----


def test_p3_1_mentions_have_no_private_keys() -> None:
    """非歧义 mention 也无 `_cand_ids`（统一 pop——P3-1；API/MCP JSON 面
    不带内部字段）。"""
    from knowledge_lattice.core.semantic.annotator import Annotator

    snap = _p2_2_snapshot()
    ann = Annotator(snap)
    result = ann.annotate("这里是甲的用法")
    assert result["mentions"]
    for m in result["mentions"]:
        assert not [k for k in m if k.startswith("_")], \
            f"私有键泄露: {[k for k in m if k.startswith('_')]}"


# ---- P3-2：裸 JSON → 400 ----


def test_p3_2_annotate_malformed_json_400(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect
    from helpers import seed_membership, seed_user

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
        semantic_eval_golden_path="",
    )
    app = create_app(settings, gate=EmbeddingGate(), run_startup_probe=False)
    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    seed_user(conn, "u_full")
    seed_membership(conn, "u_full", ORG)
    conn.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                 (hash_token("dev-static-u-full"), "u_full"))
    conn.commit()
    with TestClient(app) as client:
        resp = client.post(
            f"/api/orgs/{ORG}/semantic/annotate",
            content="{not-json",
            headers={"Authorization": "Bearer dev-static-u-full",
                     "X-Org-Id": ORG,
                     "Content-Type": "application/json"})
        assert resp.status_code == 400, resp.text   # 修复前 500
    conn.close()


# ---- P3-10：_worker_env 补两键映射 ----


def test_p3_10_worker_env_sem_keys_closed(tmp_path) -> None:
    """全 LATTICE_SEM_* 往返闭合：新增 DAILY_SYNC_INTERVAL_S /
    EVAL_GOLDEN_PATH 两键显式映射（程序化 Settings 子进程不漂移）。"""
    from knowledge_lattice.config import Settings
    from knowledge_lattice.worker.runner import WorkerSupervisor

    settings = Settings(environment="test", data_dir=tmp_path,
                        semantic_daily_sync_interval_s=3600.0,
                        semantic_eval_golden_path="/abs/golden.jsonl")
    envmap = WorkerSupervisor._worker_env(settings)
    assert envmap["LATTICE_SEM_DAILY_SYNC_INTERVAL_S"] == "3600.0"
    assert envmap["LATTICE_SEM_EVAL_GOLDEN_PATH"] == "/abs/golden.jsonl"
    assert envmap["LATTICE_SEM_NIGHT_WINDOW"] == settings.semantic_night_window


# ---- P3-11：items 布尔显式判断 + boolean items 语义 ----


def test_p3_11_items_boolean_explicit(monkeypatch) -> None:
    """`items: 1` 不再因 `1 == True` 被当布尔子 schema 放行；items: true
    放行任意元素 / items: false 非空数组不通过（JSON Schema 口径）。"""
    import sys

    import knowledge_lattice.core.semantic.yaml_corpus as yc

    monkeypatch.setitem(sys.modules, "jsonschema", None)  # 强制回退路径
    # self-check：items: 1（int）是非法形态——旧实现 1 == True 误放行
    assert yc._minimal_schema_self_check({"items": 1}) is not None
    assert yc._minimal_schema_self_check({"items": True}) is None
    assert yc._minimal_schema_self_check({"items": False}) is None
    # errors：items: false → 非空数组不通过、空数组通过
    assert yc._minimal_schema_errors(["x"], {"items": False})
    assert yc._minimal_schema_errors([], {"items": False}) == []
    assert yc._minimal_schema_errors(["x", 1], {"items": True}) == []
