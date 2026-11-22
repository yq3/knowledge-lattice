"""agent 中间件注入规则契约——参考实现（design §6.3 agent 侧接入 / TC-SEM-08）。

**定位**：中间件住 agent 侧（deepagents before_model）——本模块是**服务仓内的
契约参考实现**（agent 侧可原样复用；服务端运行时不依赖本模块）。本侧验收
口径 = 接口契约（本模块行为）+ 灰度对比记录（评测集载体——
TC-YAML-05/test_sev_03）。

注入规则（§6.3 步骤 2 + G-2 并存裁定〔2026-10-31 用户拍板〕）：

1. **confidence=1.0 且非 ambiguous** 的命中按类型注入 L1：
   - concept/system：`name + brief + disambiguation`（概念带定义与消歧）；
   - 对象（template/template_field/report/report_item/table/column/
     scenario）：只注入 `name + type + id` 一行（详情留给 agent 经
     get_entity 获取）；
   - **alias 档 0.95 不注入 L1**（G-21 P3-4/m2s-6 确认设计意图：只有
     exact 精确全词档〔规范名/业务键命中〕才配自动注入——别名命中存在
     同名歧义面，交 agent 追问或自判）；
2. **歧义命中**只注入候选列表 + 提示「必要时向用户确认」；
3. **fuzzy 候选**（via='fuzzy'——candidates）：一行低信任提示（G-2 ①），
   措辞明示「疑似」，计入本轮 token 预算；
4. **本轮注入总量 ≤ 600 token**（L1_TOKEN_BUDGET）：超出按 confidence
   降序、同 confidence 按出现顺序截断（truncated=true）；
5. annotate 超时（ANNOTATE_TIMEOUT_MS=200ms）或失败 → 本轮跳过注入，
   不阻塞对话（NFR-11 降级——超时执行在 agent 侧运行时，本模块只提供
   常量契约）。
"""

from __future__ import annotations

from typing import Any

from knowledge_lattice.core.semantic.yaml_corpus import estimate_tokens

__all__ = [
    "inject_l1", "ANNOTATE_TIMEOUT_MS", "L1_TOKEN_BUDGET",
    "OBJECT_TYPES",
]

# §6.3 步骤 4：annotate 超时 200ms 本轮跳过（NFR-11——常量契约）
ANNOTATE_TIMEOUT_MS = 200
# §6.3 步骤 2④：本轮注入总量 ≤600 token
L1_TOKEN_BUDGET = 600
# 对象类实体（一行 name+type+id；概念/系统带 brief 与消歧）
OBJECT_TYPES = frozenset({
    "scenario", "template", "template_field", "report", "report_item",
    "table", "column",
})


def _concept_line(mention: dict) -> str:
    """concept/system 注入行：name + brief + 消歧提示（§6.3 ②——三件全）。

    G-24⑦（m3-3）：disambiguation 经 mention 契约携带（可选字段——
    curated_json {not, hint} 派生），L1 行按 hint 追加消歧句（「注意与…区
    分」）；无该字段时行内容与旧形态一致（向后兼容）。"""
    parts = [f"[{mention.get('type')}] {mention.get('name')}"]
    if mention.get("brief"):
        parts.append(f"：{mention['brief']}")
    hints = [str(d.get("hint")).rstrip("。；;，,")
             for d in (mention.get("disambiguation") or ())
             if isinstance(d, dict) and d.get("hint")]
    if hints:
        parts.append("（注意区分：" + "；".join(hints[:3]) + "）")
    return " ".join(parts)


def _object_line(mention: dict) -> str:
    """对象注入行：name + type + id 一行（详情留 get_entity）。"""
    return f"[{mention.get('type')}] {mention.get('name')}（id={mention.get('entity_id')}）"


def inject_l1(
    mentions: list[dict],
    candidates: list[dict],
    *,
    token_budget: int = L1_TOKEN_BUDGET,
) -> dict:
    """mentions + candidates → 本轮注入行（§6.3 步骤 2——纯函数契约面）。

    返回 {injections: [{entity_id, entity_key, confidence, kind, text}],
    truncated, tokens}——kind ∈ {l1_concept, l1_object, ambiguous, fuzzy}；
    fuzzy 行为 candidates 的一行汇总（低信任提示，G-2 ①）；预算截断按
    confidence 降序、同分按出现顺序（§6.3 ②④）。"""
    pending: list[dict] = []
    for m in mentions or ():
        if m.get("ambiguous") or m.get("confidence") != 1.0:
            continue                      # 0.95/歧义不自动注入 L1（G-21 P3-4）
        kind = "l1_object" if m.get("type") in OBJECT_TYPES else "l1_concept"
        text = _object_line(m) if kind == "l1_object" else _concept_line(m)
        pending.append({"entity_id": m.get("entity_id"),
                        "entity_key": m.get("entity_key"),
                        "confidence": m.get("confidence", 0.0),
                        "kind": kind, "text": text,
                        "order": m.get("span", [0, 0])[0]})
    ambiguous = [m for m in mentions or () if m.get("ambiguous")]
    if ambiguous:
        keys = sorted({m.get("entity_key") or str(m.get("entity_id"))
                       for m in ambiguous})
        pending.append({
            "entity_key": None, "entity_id": None, "confidence": 0.8,
            "kind": "ambiguous",
            "text": "存在歧义命中（" + "、".join(keys[:8])
                    + "）——必要时向用户确认", "order": 10 ** 9 - 1,
        })
    fuzzy_rows = [c for c in candidates or () if c.get("via") == "fuzzy"]
    if fuzzy_rows:
        names = sorted({f"{c.get('name')}（疑似，低信任）" for c in fuzzy_rows})
        pending.append({
            "entity_key": None, "entity_id": None, "confidence": 0.5,
            "kind": "fuzzy",
            "text": "模糊层候选（同音/错字/近邻——请自行核实）："
                    + "、".join(names[:8]), "order": 10 ** 9,
        })
    # 预算截断：confidence 降序 → 出现顺序（§6.3 ②④——高信任优先、同分先现）
    pending.sort(key=lambda p: (-p["confidence"], p["order"]))
    injections: list[dict] = []
    used = 0
    truncated = False
    for item in pending:
        cost = estimate_tokens(item["text"])
        if used + cost > token_budget:
            truncated = True
            continue
        used += cost
        injections.append({k: item[k] for k in
                           ("entity_id", "entity_key", "confidence", "kind",
                            "text")})
    return {"injections": injections, "truncated": truncated, "tokens": used}


def annotate_call_contract() -> dict[str, Any]:
    """中间件 annotate 调用契约（观察面——TC-SEM-08 记录用）。"""
    return {
        "timeout_ms": ANNOTATE_TIMEOUT_MS,
        "token_budget": L1_TOKEN_BUDGET,
        "on_timeout": "skip_round",     # 超时本轮跳过注入（NFR-11）
        "fuzzy": "candidates_only",     # G-2 并存：①一行低信任提示（本模块）
    }
