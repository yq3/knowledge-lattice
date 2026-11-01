"""m2s-6 TC-SEM-08 agent 中间件契约（design §6.3 步骤 2/4 + G-2 并存裁定
〔2026-10-31 用户拍板：①中间件注入 candidates 一行低信任提示 + ②工具描述
引导 agent 自调 annotate(fuzzy=true)〕）。

- 中间件住 agent 侧——本侧验收 = 接口契约（core/semantic/middleware 参考
  实现行为）+ 灰度对比记录（TC-YAML-05 评测集载体）；
- 注入规则：confidence=1.0 非歧义按类型注入 L1（概念带 brief、对象一行
  name+type+id）/ 歧义只注候选提示 / **alias 档 0.95 不注入 L1**
  （G-21 P3-4 确认设计意图——exact 精确全词才配自动注入）/ fuzzy 候选一行
  低信任提示（G-2 ①）/ ≤600 token 超出按 confidence 与出现顺序截断；
- annotate 200ms 超时本轮跳过（常量契约 ANNOTATE_TIMEOUT_MS）；
- G-2 ②：annotate 工具描述含「L1 无命中可自行调 annotate(fuzzy=true)」
  引导句（MCP 工具描述常量断言）。
"""

from __future__ import annotations


def _mention(**kw):
    base = {"span": [0, 4], "surface": "进项税额抵扣", "entity_id": 101,
            "entity_key": "concept:vat.input_credit", "type": "concept",
            "name": "进项税额抵扣", "confidence": 1.0, "via": "ac",
            "ambiguous": False,
            "brief": "一般纳税人取得合规扣税凭证后从当期销项税额中抵减的进项税额。"}
    base.update(kw)
    return base


def test_tc_sem_08_inject_l1_by_type() -> None:
    """confidence=1.0 非歧义按类型注入：概念带 brief（l1_concept）、对象只
    一行 name+type+id（l1_object）。"""
    from knowledge_lattice.core.semantic.middleware import inject_l1

    mentions = [
        _mention(),
        _mention(entity_id=201, entity_key="template:TPL_A", type="template",
                 name="进项采集模板", brief=None, span=[6, 12],
                 surface="进项采集模板"),
    ]
    out = inject_l1(mentions, [])
    kinds = [i["kind"] for i in out["injections"]]
    assert kinds.count("l1_concept") == 1 and kinds.count("l1_object") == 1
    concept = next(i for i in out["injections"] if i["kind"] == "l1_concept")
    assert "进项税额抵扣" in concept["text"] and "抵减" in concept["text"]
    obj = next(i for i in out["injections"] if i["kind"] == "l1_object")
    assert "id=201" in obj["text"] and "brief" not in obj


def test_tc_sem_08_alias_confidence_not_injected() -> None:
    """alias 档 0.95 不注入 L1（G-21 P3-4——设计意图确认：只有 exact 精确
    全词〔confidence=1.0〕才自动注入；别名命中存在同名歧义面）。"""
    from knowledge_lattice.core.semantic.middleware import inject_l1

    mentions = [_mention(confidence=0.95, via="ac", matched_by="alias")]
    out = inject_l1(mentions, [])
    assert out["injections"] == []


def test_tc_sem_08_ambiguous_only_candidates_hint() -> None:
    """歧义命中只注入候选提示（不注入 L1 正文行）。"""
    from knowledge_lattice.core.semantic.middleware import inject_l1

    mentions = [_mention(ambiguous=True, confidence=0.8)]
    out = inject_l1(mentions, [])
    assert [i["kind"] for i in out["injections"]] == ["ambiguous"]
    assert "确认" in out["injections"][0]["text"]


def test_tc_sem_08_fuzzy_candidate_low_trust_line() -> None:
    """fuzzy 候选一行低信任提示（G-2 ①——「疑似」措辞、计入 token 预算）。"""
    from knowledge_lattice.core.semantic.middleware import inject_l1

    candidates = [{"via": "fuzzy", "entity_id": 9, "name": "进项税额抵扣",
                   "entity_key": "concept:vat.input_credit",
                   "span": [0, 2], "surface": "留底",
                   "fuzzy_layer": "pinyin", "confidence": 0.75}]
    out = inject_l1([], candidates)
    fuzzy_lines = [i for i in out["injections"] if i["kind"] == "fuzzy"]
    assert fuzzy_lines and "疑似" in fuzzy_lines[0]["text"]
    assert out["tokens"] > 0, "fuzzy 提示计入本轮 token 预算"


def test_tc_sem_08_token_budget_truncation() -> None:
    """≤600 token：超出按 confidence 降序、同分按出现顺序截断（truncated）。"""
    from knowledge_lattice.core.semantic.middleware import (
        L1_TOKEN_BUDGET,
        inject_l1,
    )

    mentions = []
    for i in range(80):
        mentions.append(_mention(
            entity_id=1000 + i, span=[i, i + 4],
            brief="一般纳税人取得合规扣税凭证后从当期销项税额中抵减的进项税额。"
                  "本条为预算截断造数文本，长度超过单行预算。"))
    out = inject_l1(mentions, [], token_budget=600)
    assert out["truncated"] is True
    assert out["tokens"] <= L1_TOKEN_BUDGET
    # confidence 全 1.0 → 按出现顺序保留前缀（span 起点升序）
    kept = [i["entity_id"] for i in out["injections"]]
    assert kept == sorted(kept)


def test_tc_sem_08_constants_and_g2_tool_description() -> None:
    """契约常量（200ms 超时 / 600 token）+ G-2 ② 工具描述引导句。"""
    from knowledge_lattice.core.semantic.middleware import (
        ANNOTATE_TIMEOUT_MS,
        L1_TOKEN_BUDGET,
        annotate_call_contract,
    )
    from knowledge_lattice.mcp.server import ANNOTATE_TOOL_DESCRIPTION

    assert ANNOTATE_TIMEOUT_MS == 200          # NFR-11 / §6.3 步骤 4
    assert L1_TOKEN_BUDGET == 600              # §6.3 步骤 2④
    contract = annotate_call_contract()
    assert contract["on_timeout"] == "skip_round"
    # G-2 并存②：工具描述引导 agent 自调 fuzzy
    assert "fuzzy=true" in ANNOTATE_TOOL_DESCRIPTION
    assert "L1 无命中" in ANNOTATE_TOOL_DESCRIPTION
