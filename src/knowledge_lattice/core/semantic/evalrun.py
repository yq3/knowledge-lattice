"""识别评测集装载与指标计算（A5——TC-SEV-01/02；core 纯计算、零 SQL）。

黄金集 `eval/semantic_golden.jsonl`（格式与标注规范见同目录
semantic_golden.README.md）——每行：

    {"qid": "s001", "kind": "pos_exact|pos_alias|pos_abbr|pos_ambiguous|
                            pos_context|neg",
     "lang": "zh|en|mix", "text": "……", "labels": [[entity_key, start, end]]}

labels 为**人工标注期望**：span [start, end) 左闭右开、下标落在原文 text 上、
entity_key 形如 "type:key"；负样本 labels 恒空。

指标（TC-SEV-02 门槛四指标——AC 层口径）：

- precision = 预测 mention 与标注 span+实体双匹配数 / 预测 mention 总数；
- recall = 双匹配数 / 标注总数；
- ambiguity（歧义消解率，只统计 kind=pos_ambiguous 条目中的**歧义 span
  标注**——P2-2/R3 口径：标注 surface 的 alias_norm 为多实体共享〔词典侧
  判定，与识别可用面同口径——restricted/fuzzy_only 不计〕的 span 才进
  分子分母；条目内伴随的确定性标注不计——不稀释 ≥0.85 门槛）= 选中正确
  实体数 / 歧义 span 标注数；**B1/m2s-5 收紧分子**：`ambiguous=true` 的
  主候选命中**不计**正确——未消解定案不算答对（G-21 R3 终审补登记项：
  严格口径 18/20=0.90 仍过门；定案〔含 B2 显式缺省主读 default 档〕才计）；
- neg_fp（负样本误报率）= 含 ≥1 预测 mention 的负样本条数 / 负样本条数。

匹配口径：span 完全相等（start/end 逐位）且实体 key 相等。评测确定性
（非 Flaky）：AC 自动机纯确定性匹配——同词典同输入两次评测逐位一致
（test_tc_sev_02_eval_deterministic_double_build 永久断言）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "load_golden", "run_recognition_eval", "EVAL_THRESHOLDS",
    "golden_eval_runner",
]

# TC-SEV-02 门槛：三指标 ≥ 阈值、负样本误报 ≤ 阈值（方向差异见 _below）
EVAL_THRESHOLDS = {
    "precision": 0.95,
    "recall": 0.80,
    "ambiguity": 0.85,
    "neg_fp": 0.05,
}

# 适用面门槛（参考词典部署判定）：可完整解析正样本 ≥20 条且 ≥80%——
# 部分重叠的 org（测试 fixture / 非参考部署）评测整体 skipped 不拦构建
EVAL_MIN_APPLICABLE = 20
EVAL_MIN_APPLICABLE_RATIO = 0.8


def load_golden(path: str | Path) -> list[dict]:
    """装载黄金集（JSONL；空行跳过；坏行 fail-fast——标注资产不容静默缺行）。"""
    items = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except ValueError as exc:
                raise ValueError(
                    f"golden set line {lineno} not JSON: {exc}") from exc
    return items


def run_recognition_eval(
    annotator,
    items: Sequence[dict],
    snapshot: dict,
) -> dict:
    """黄金集 → 指标（annotator 为 Annotator 实例——构建前评测用新快照实例）。

    适用面（TC-SEV-02 口径注记）：黄金集面向**参考词典**部署——仅当可完整
    解析（标注 key 全在场）的正样本条目 ≥20 且占比 ≥80% 时才运行评测与门槛
    （`EVAL_MIN_APPLICABLE`/`EVAL_MIN_APPLICABLE_RATIO`）；部分重叠的 org
    （测试 fixture / 非参考部署）整体 skipped——半套词典上的指标无意义且
    会误拦构建。负样本恒适用（计入适用判定分母外的独立面）。"""
    id_to_key = {e["id"]: f'{e["type"]}:{e["key"]}' for e in snapshot["entities"]}
    key_set = set(id_to_key.values())

    pos_items = [i for i in items if i["kind"] != "neg"]
    applicable = [i for i in pos_items
                  if all(lb[0] in key_set for lb in i["labels"])]
    if (len(applicable) < EVAL_MIN_APPLICABLE
            or len(applicable) / len(pos_items) < EVAL_MIN_APPLICABLE_RATIO):
        return {"skipped": (
            f"golden set not applicable to this dictionary"
            f"（可完整解析 {len(applicable)}/{len(pos_items)} 条"
            f" < {EVAL_MIN_APPLICABLE_RATIO:.0%} 或 <{EVAL_MIN_APPLICABLE} 条"
            "——参考词典部署外的 org 不做半套评测）")}

    # P2-2/R3：歧义 span 判定走词典侧（多实体共享同一 alias_norm——与识别
    # 可用面同口径：restricted 实体别名与 fuzzy_only 不入识别面，不构成歧义）
    from knowledge_lattice.core.semantic.norm import normalize_alias

    sensitivity = {e["id"]: e.get("sensitivity") for e in snapshot["entities"]}
    by_norm: dict[str, set[int]] = {}
    for a in snapshot["aliases"]:
        if sensitivity.get(a["entity_id"]) == "restricted":
            continue
        if a["match_mode"] not in ("exact", "context"):
            continue
        by_norm.setdefault(a["alias_norm"], set()).add(a["entity_id"])
    ambiguous_norms = {n for n, ids in by_norm.items() if len(ids) > 1}

    predicted_total = matched = labeled_total = 0
    ambiguous_labeled = ambiguous_correct = 0
    neg_total = neg_flagged = 0
    for item in items:
        labels = [lb for lb in item["labels"] if lb[0] in key_set]
        mentions = annotator.annotate(item["text"])["mentions"]
        if item["kind"] == "neg":
            neg_total += 1
            if mentions:
                neg_flagged += 1
            continue
        pred = {(m["span"][0], m["span"][1], m["entity_key"]): m
                for m in mentions}
        gold = {(s, e, k) for k, s, e in labels}
        predicted_total += len(pred)
        labeled_total += len(gold)
        matched += len(set(pred) & gold)
        if item["kind"] == "pos_ambiguous":
            for k, s, e in labels:
                # 只统计歧义 span 标注（surface 规范化后为共享别名）——
                # 伴随确定性标注（规范名/独占别名）不进分母
                if normalize_alias(item["text"][s:e]) not in ambiguous_norms:
                    continue
                ambiguous_labeled += 1
                hit = pred.get((s, e, k))
                # B1/m2s-5 收紧：ambiguous=true（未消解定案）的主候选命中
                # 不计正确——只有定案命中才计分子
                if hit is not None and not hit.get("ambiguous"):
                    ambiguous_correct += 1

    precision = (matched / predicted_total) if predicted_total else 1.0
    recall = (matched / labeled_total) if labeled_total else 1.0
    ambiguity = ((ambiguous_correct / ambiguous_labeled)
                 if ambiguous_labeled else None)
    neg_fp = (neg_flagged / neg_total) if neg_total else 0.0
    return {
        "items": len(pos_items) + neg_total,
        "applicable_pos": len(applicable),
        "neg_items": neg_total,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "ambiguity": None if ambiguity is None else round(ambiguity, 4),
        "neg_fp": round(neg_fp, 4),
        "_counts": {"predicted": predicted_total, "matched": matched,
                    "labeled": labeled_total,
                    "ambiguous_labeled": ambiguous_labeled,
                    "ambiguous_correct": ambiguous_correct},
    }


def golden_eval_runner(settings) -> Callable | None:
    """默认评测执行体工厂：黄金集文件 → runner(annotator, snapshot) → metrics。

    文件缺失/不可读 → None（构建评测 skipped——部署面未携带评测资产不拦截
    构建；TC-SEV-01 的集合格式校验由 tests/test_sem_eval_golden.py 把门）。"""
    path = settings.semantic_eval_golden_path
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        logger.warning("semantic eval golden set not found: %s（评测 skipped）",
                       path)
        return None
    items = load_golden(p)

    def runner(annotator, snapshot) -> dict:
        metrics = run_recognition_eval(annotator, items, snapshot)
        metrics.pop("_counts", None)
        return metrics

    return runner
