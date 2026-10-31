"""m2s-4 annotate 核心（design §5.9 / §6.3——TC-SEM-01~04·07 + T-S12 生命周期）：

- TC-SEM-01 规范化同函数（NFKC/全半角/大小写/去空白 + span 回映原文下标）；
- TC-SEM-02 最长匹配优先 / 等长取 weight 高者；
- TC-SEM-03 消歧四级顺序：①共现定案 > ②会话焦点 > ③类型先验 > ④全部候选
  ambiguous=true（+ L0 片段兜底为第四步消歧——任务书 A2/A3）；
- TC-SEM-04 context 短别名条件保留（同句确定命中 + 有关系才留）；
- TC-SEM-07 契约（结构 / ≤4000 字 / context_entities ≤20）与 via='ac'；
- 负样本文本零标注（任务书 A2）；fuzzy_only 不进自动机（TC-BUILD-02 半句）；
  restricted 实体表现为不存在（T-S9 annotate 侧——M2-S3 权限面前 fail-closed）；
- T-S12：构建期间/构建失败沿用旧 dict_rev 实例、ready 后切换（懒加载
  (org, dict_rev) 缓存——A1 生命周期）。
"""

from __future__ import annotations

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"


# ---- 快照构造（Annotator 纯函数面——sem_active_snapshot 同形） ----


def _ent(i, type_, key, name, *, sensitivity="normal", curated="{}"):
    return {"id": i, "type": type_, "key": key, "name": name,
            "parent_id": None, "attrs_json": "{}", "sensitivity": sensitivity,
            "curated_json": curated, "curated_rev": None}


def _alias(entity_id, alias, norm, *, kind="manual", mode="exact", weight=1.0):
    return {"entity_id": entity_id, "alias": alias, "alias_norm": norm,
            "kind": kind, "match_mode": mode, "weight": weight}


def _rel(src, rel_type, dst):
    return {"src_id": src, "rel_type": rel_type, "dst_id": dst,
            "attrs_json": "{}", "source": "sync"}


@pytest.fixture()
def ann():
    """两概念（歧义别名「留抵」共享）+ 一模板（context 短别名）+ restricted +
    fuzzy_only 样本。"""
    from knowledge_lattice.core.semantic.annotator import Annotator

    ents = [
        _ent(1, "concept", "vat.retained_credit", "留抵税额",
             curated='{"definition": "期末留抵税额是尚未抵扣完、结转下期继续抵扣的进项税额。", "l0": true}'),
        _ent(2, "concept", "vat.retained_refund", "留抵退税",
             curated='{"definition": "留抵退税是将期末留抵税额按政策退还给纳税人。", "l0": true}'),
        _ent(3, "template", "TPL_FILING", "增值税申报模板"),
        _ent(4, "concept", "vat.exemption", "免税政策概念"),
        _ent(5, "concept", "tax.secret", "内部筹划口径", sensitivity="restricted"),
        _ent(6, "concept", "vat.fuzzy_one", "容错概念"),
    ]
    aliases = [
        _alias(1, "留抵税额", "留抵税额", kind="name"),
        _alias(1, "留抵", "留抵"),
        _alias(2, "留抵退税", "留抵退税", kind="name"),
        _alias(2, "留抵", "留抵"),
        _alias(3, "增值税申报模板", "增值税申报模板", kind="name"),
        _alias(4, "免税", "免税", mode="context"),
        _alias(5, "内部口径", "内部口径"),
        _alias(6, "容错", "容错", mode="fuzzy_only"),
    ]
    rels = [
        _rel(4, "related_to", 3),      # 免税 ↔ 申报模板（context 佐证关系）
        _rel(1, "related_to", 3),      # 留抵税额 ↔ 申报模板（共现①样本）
    ]
    return Annotator({"entities": ents, "aliases": aliases, "relations": rels})


def _mention_of(result, key: str):
    ms = [m for m in result["mentions"] if m["entity_key"] == key]
    assert ms, f"no mention of {key}: {result}"
    return ms[0]


# ---- TC-SEM-01 规范化同函数 ----


def test_tc_sem_01_norm_equivalence_and_span_map(ann) -> None:
    """全半角/大小写/去空白等价形命中，且 span 回映**原文**下标（surface 可切）。"""
    result = ann.annotate("本月的留抵税额怎么算")
    m = _mention_of(result, "concept:vat.retained_credit")
    assert m["span"][1] - m["span"][0] == len("留抵税额")
    assert m["surface"] == "留抵税额"       # 原文切片 == 匹配面
    assert m["via"] == "ac"
    assert m["matched_by"] == "exact"        # kind=name → 精确全词档
    assert m["resolved_by"] == "single"      # 单候选（无歧义面）


def test_tc_sem_01_norm_nfkc_fullwidth_and_spaces(ann) -> None:
    """内嵌空白去除后仍命中（与 alias_norm 同一规范化函数）——span 回映
    原文区间（含空白字符）。"""
    text = "增 值 税 申 报 模 板 在哪"
    result = ann.annotate(text)
    m = _mention_of(result, "template:TPL_FILING")
    assert m["span"] == [0, 13]              # 原文区间（含 6 个空白）
    assert m["surface"] == "增 值 税 申 报 模 板"


def test_tc_sem_01_norm_alias_norm_same_function() -> None:
    from knowledge_lattice.core.semantic.norm import normalize_alias

    for a, b in [("ＶＡＴ", "vat"), ("进 项 抵 扣", "进项抵扣"),
                 ("ＪＸＤＫ", "jxdk"), ("AbC", "abc")]:
        assert normalize_alias(a) == normalize_alias(b)


# ---- TC-SEM-02 最长匹配与权重 ----


def test_tc_sem_02_longest_match_wins(ann) -> None:
    """重叠别名「留抵」与「留抵税额」同现 → 留长 span。"""
    result = ann.annotate("留抵税额结转下期")
    assert len(result["mentions"]) == 1
    assert result["mentions"][0]["entity_key"] == "concept:vat.retained_credit"
    assert result["mentions"][0]["span"][1] - result["mentions"][0]["span"][0] == 4


def test_tc_sem_02_equal_length_higher_weight_wins() -> None:
    from knowledge_lattice.core.semantic.annotator import Annotator

    snap = {
        "entities": [_ent(1, "concept", "a.one", "甲概念"), _ent(2, "concept", "a.two", "乙概念")],
        "aliases": [_alias(1, "共享词", "共享词", weight=1.0),
                    _alias(2, "共享词", "共享词", weight=3.0)],
        "relations": [],
    }
    result = Annotator(snap).annotate("这里是共享词的用法")
    assert len(result["mentions"]) == 1
    assert result["mentions"][0]["entity_key"] == "concept:a.two"  # weight 高者


# ---- TC-SEM-03 消歧四级顺序 ----


def test_tc_sem_03_level1_cooccurrence_wins(ann) -> None:
    """①同句有与候选之一 1 跳关系的其他命中实体 → 共现定案（留抵→留抵税额，
    经 related_to(1,3) 与申报模板共现）。"""
    result = ann.annotate("增值税申报模板里的留抵怎么填")
    m = _mention_of(result, "concept:vat.retained_credit")
    assert m["resolved_by"] == "cooccurrence"
    assert m["ambiguous"] is False
    assert not any(c for c in result["candidates"])


def test_tc_sem_03_level2_context_entities(ann) -> None:
    """②无共现但传 context_entities → 会话焦点定案。"""
    result = ann.annotate("留抵的政策依据是什么",
                          context_entities=[2])   # 2 = retained_refund
    m = _mention_of(result, "concept:vat.retained_refund")
    assert m["resolved_by"] == "focus"
    assert m["ambiguous"] is False


def test_tc_sem_03_level3_prefer_types(ann) -> None:
    """③无②但传 prefer_types → 类型先验（两候选同为 concept——改用模板候选样本）。"""
    from knowledge_lattice.core.semantic.annotator import Annotator

    snap = {
        "entities": [_ent(1, "concept", "c.x", "概念X"), _ent(2, "template", "t.x", "模板X")],
        "aliases": [_alias(1, "甲", "甲"), _alias(2, "甲", "甲")],
        "relations": [],
    }
    a = Annotator(snap)
    r = a.annotate("这个甲是哪个", prefer_types=["template"])
    assert r["mentions"][0]["entity_key"] == "template:t.x"
    assert r["mentions"][0]["resolved_by"] == "prior"

    r2 = a.annotate("这个甲是哪个", prefer_types=["concept"])
    assert r2["mentions"][0]["entity_key"] == "concept:c.x"


def test_tc_sem_03_level4_ambiguous_returns_all_candidates(ann) -> None:
    """④三者皆无 → 全部候选 + ambiguous=true（confidence 不标 1.0）。"""
    result = ann.annotate("留抵是什么意思")
    assert len(result["mentions"]) == 1
    m = result["mentions"][0]
    assert m["ambiguous"] is True
    assert m["confidence"] < 1.0
    keys = {c["entity_key"] for c in result["candidates"]}
    assert keys == {"concept:vat.retained_credit", "concept:vat.retained_refund"}


def test_tc_sem_03_l0_fragment_fallback_disambiguates(ann) -> None:
    """L0 片段兜底（第四步消歧——任务书 A2）：无①②③时，句内上下文词与候选
    L0 definition 片段重叠可定案（「退还」佐证留抵退税）。"""
    result = ann.annotate("符合条件的留抵可以申请退还吗")
    m = _mention_of(result, "concept:vat.retained_refund")
    assert m["resolved_by"] == "l0"
    assert m["ambiguous"] is False


# ---- TC-SEM-04 context 短别名条件保留 ----


def test_tc_sem_04_context_alias_kept_with_relation(ann) -> None:
    """①同句有其他确定命中且两者有关系 → 保留。"""
    result = ann.annotate("增值税申报模板里免税栏怎么填")
    assert any(m["entity_key"] == "concept:vat.exemption"
               for m in result["mentions"])


def test_tc_sem_04_context_alias_dropped_no_relation(ann) -> None:
    """②同句有命中但无关系 → 丢弃（换成留抵税额——与免税无关系）。"""
    result = ann.annotate("留抵税额与免税的关系是什么")
    assert not any(m["entity_key"] == "concept:vat.exemption"
                   for m in result["mentions"])
    assert any(m["entity_key"] == "concept:vat.retained_credit"
               for m in result["mentions"])   # 非条件命中不受影响


def test_tc_sem_04_context_alias_dropped_alone(ann) -> None:
    """③无其他命中的文本中出现 → 丢弃。"""
    result = ann.annotate("免税额度是多少")
    assert result["mentions"] == []


# ---- TC-SEM-07 契约与限流（core 校验面） ----


def test_tc_sem_07_output_structure(ann) -> None:
    result = ann.annotate("增值税申报模板和留抵税额")
    keys = {"span", "surface", "entity_id", "entity_key", "type", "name",
            "confidence", "via", "matched_by", "resolved_by", "ambiguous",
            "brief"}
    for m in result["mentions"]:
        assert keys <= set(m)
        assert m["via"] == "ac"
        assert isinstance(m["span"], list) and len(m["span"]) == 2
    # mentions 按出现位置有序
    starts = [m["span"][0] for m in result["mentions"]]
    assert starts == sorted(starts)


def test_tc_sem_07_text_over_4000_rejected(ann) -> None:
    with pytest.raises(ValueError):
        ann.annotate("留抵" * 2500)


def test_tc_sem_07_context_entities_over_20_rejected(ann) -> None:
    with pytest.raises(ValueError):
        ann.annotate("留抵", context_entities=list(range(1, 22)))


def test_tc_sem_07_prefer_types_invalid_rejected(ann) -> None:
    with pytest.raises(ValueError):
        ann.annotate("留抵", prefer_types=["not_a_type"])


# ---- 负样本 / fuzzy_only / restricted ----


def test_negative_text_zero_mentions(ann) -> None:
    """负样本文本零标注（任务书 A2 验收半句）。"""
    for text in ("今天中午食堂有什么菜", "帮我订一张明天去上海的机票",
                 "这个季度的经营分析会改到周四下午"):
        assert ann.annotate(text)["mentions"] == []


def test_fuzzy_only_alias_never_matched(ann) -> None:
    """fuzzy_only 别名不进自动机（TC-BUILD-02——防误报；模糊兜底 M2-S3）。"""
    assert ann.annotate("这里有个容错词")["mentions"] == []


def test_restricted_entity_invisible(ann) -> None:
    """restricted 实体表现为不存在（T-S9 annotate 侧——不返回 span）。"""
    assert ann.annotate("内部口径说明一下")["mentions"] == []


# ---- T-S12 生命周期（DB——懒加载 (org, dict_rev) 缓存） ----


@pytest.fixture()
def aenv(backend, tmp_path):
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_semantic import FakeSourceAdapter

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    b = backend.make_backend()

    def _sync(names):
        recs = [EntityRecord(type="concept", key=f"k.{n}", name=n)
                for n in names]
        run_sync(b, ORG, FakeSourceAdapter("template_center", recs),
                 settings=settings, snapshot=list(recs), now=NOW)

    return SimpleNamespace(db=backend, backend=b, settings=settings, sync=_sync)


def test_t_s12_old_automaton_during_building_and_failure(aenv, monkeypatch) -> None:
    """构建期间/失败沿用旧 dict_rev 实例；ready 后切换新实例（T-S12/A1）。"""
    from knowledge_lattice.core.semantic.annotator import (
        clear_annotator_cache, get_annotator,
    )
    from knowledge_lattice.core.semantic.build import run_build

    clear_annotator_cache()
    aenv.sync(["留抵税额"])
    r1 = run_build(aenv.backend, ORG, settings=aenv.settings)
    assert r1["status"] == "ready"
    ann1, rev1 = get_annotator(aenv.backend, ORG, aenv.settings)
    assert rev1 == r1["dict_rev"]
    assert ann1.annotate("留抵税额怎么算")["mentions"]

    # live 前进（新 sync、尚未构建）——current 仍 r1：沿用旧实例
    aenv.sync(["留抵税额", "出口退税单证"])
    ann1b, rev1b = get_annotator(aenv.backend, ORG, aenv.settings)
    assert rev1b == rev1 and ann1b is ann1          # 构建中沿用旧实例
    assert ann1b.annotate("出口退税单证是什么")["mentions"] == []

    # 构建失败（切换阶段注入异常）→ r2 置 failed 不切 ready；annotate 仍 r1
    def _boom(*a, **kw):
        raise RuntimeError("injected switch failure")

    monkeypatch.setattr(aenv.backend, "sem_switch_build_ready", _boom)
    with pytest.raises(RuntimeError):
        run_build(aenv.backend, ORG, settings=aenv.settings)
    monkeypatch.undo()
    failed = aenv.backend.sem_list_builds(ORG, limit=5, status="failed")
    assert failed, "失败构建应落 failed 行"
    ann1c, rev1c = get_annotator(aenv.backend, ORG, aenv.settings)
    assert rev1c == rev1
    assert ann1c.annotate("出口退税单证是什么")["mentions"] == []

    # 重建成功 → ready r2 → 新实例切换
    r2 = run_build(aenv.backend, ORG, settings=aenv.settings)
    assert r2["status"] == "ready" and r2["dict_rev"] != rev1
    ann2, rev2 = get_annotator(aenv.backend, ORG, aenv.settings)
    assert rev2 == r2["dict_rev"]
    assert ann2.annotate("出口退税单证是什么")["mentions"]
    clear_annotator_cache()
