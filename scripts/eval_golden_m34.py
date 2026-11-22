#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""m3-4 A 组：golden.jsonl 扩容批（28 → 60 query——TC-EVAL-02 M3 完整集）。

一次性数据构建脚本（幂等：已有 qid 跳过）。新增 q29~q60（zh 12 / en 10 /
mix 10）来自 scripts/eval_synth_m34.py 候选（本批 --offline 确定性候选——
端点配额受阻申报见该脚本 docstring）+ **人工抽检修正**（模板问法改写为自然
问法、用词与语料逐条核对——修正记录见 eval/reports/labeling-notes.md）。

可达性纪律（沿 M1 labeling-notes 规则 3）：query 用词逐字出现在标注语料
内（BM25 词面 + token 袋均无跨语言召回）——本脚本内置机检（jieba 切词后
实词 token 与标注 doc 分词集合比对，不通过即拒绝写入）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

EVAL_DIR = ROOT / "eval"

NEW_QUERIES: list[dict] = [
    # ---- zh +12（9 篇纯中语料 + 3 篇混排语料的纯中问法）----
    {"qid": "q29", "lang": "zh", "query": "电子发票数电票如何开具和交付", "labels": [["gk-zh-m01", 1]]},
    {"qid": "q30", "lang": "zh", "query": "专用发票勾选认证的流程和期限", "labels": [["gk-zh-m02", 1]]},
    {"qid": "q31", "lang": "zh", "query": "纳税信用等级分为哪几级怎么复评", "labels": [["gk-zh-m03", 1]]},
    {"qid": "q32", "lang": "zh", "query": "欠税什么情况会被公告或阻止出境", "labels": [["gk-zh-m04", 1]]},
    {"qid": "q33", "lang": "zh", "query": "税务稽查自查补税的程序是怎样的", "labels": [["gk-zh-m05", 1]]},
    {"qid": "q34", "lang": "zh", "query": "发票丢失了怎么挂失补办", "labels": [["gk-zh-m06", 1]]},
    {"qid": "q35", "lang": "zh", "query": "小规模纳税人免税的月销售额标准", "labels": [["gk-zh-m07", 1]]},
    {"qid": "q36", "lang": "zh", "query": "跨县提供建筑服务如何预缴增值税", "labels": [["gk-zh-m08", 1]]},
    {"qid": "q37", "lang": "zh", "query": "税收减免留存备查资料有哪些要求", "labels": [["gk-zh-m09", 1]]},
    {"qid": "q38", "lang": "mix", "query": "非居民企业 non-resident enterprise 股息红利预提所得税", "labels": [["gk-mx-m03", 1]]},
    {"qid": "q39", "lang": "zh", "query": "证券交易印花税的税率是多少", "labels": [["gk-mx-m08", 1]]},
    {"qid": "q40", "lang": "zh", "query": "车船税的扣缴义务人是谁", "labels": [["gk-mx-m10", 1]]},
    # ---- en +10（纯英语料）----
    {"qid": "q41", "lang": "en", "query": "red invoice reversal cancelled sale confirmation sheet", "labels": [["gk-en-m01", 1]]},
    {"qid": "q42", "lang": "en", "query": "withholding tax rate non-resident enterprise dividends", "labels": [["gk-en-m02", 1]]},
    {"qid": "q43", "lang": "en", "query": "transfer pricing documentation master file local file thresholds", "labels": [["gk-en-m03", 1]]},
    {"qid": "q44", "lang": "en", "query": "customs valuation transaction value method sequence", "labels": [["gk-en-m04", 1]]},
    {"qid": "q45", "lang": "en", "query": "export VAT rebate rate production enterprises method", "labels": [["gk-en-m05", 1]]},
    {"qid": "q46", "lang": "en", "query": "cross-border digital services reverse charge withholding", "labels": [["gk-en-m06", 1]]},
    {"qid": "q47", "lang": "en", "query": "expatriate individual income tax annual reconciliation worldwide income", "labels": [["gk-en-m07", 1]]},
    {"qid": "q48", "lang": "en", "query": "R&D super deduction auxiliary ledger qualifying expenses", "labels": [["gk-en-m08", 1]]},
    {"qid": "q49", "lang": "en", "query": "tax treaty residency certificate withholding agent", "labels": [["gk-en-m09", 1]]},
    {"qid": "q50", "lang": "en", "query": "consumption tax premium cosmetics yachts catalogue", "labels": [["gk-en-m10", 1]]},
    # ---- mix +10（混排语料——中英术语对取自语料原文）----
    {"qid": "q51", "lang": "mix", "query": "平台经济 platform economy 个税代扣代缴", "labels": [["gk-mx-m01", 1]]},
    {"qid": "q52", "lang": "mix", "query": "转让定价 transfer pricing 关联申报", "labels": [["gk-mx-m02", 1]]},
    {"qid": "q53", "lang": "mix", "query": "税收协定 tax treaty 相互协商程序", "labels": [["gk-mx-m04", 1]]},
    {"qid": "q54", "lang": "mix", "query": "常设机构 permanent establishment 判定标准", "labels": [["gk-mx-m05", 1]]},
    {"qid": "q55", "lang": "mix", "query": "奢侈品消费税 luxury goods 超豪华小汽车零售环节", "labels": [["gk-mx-m06", 1]]},
    {"qid": "q56", "lang": "mix", "query": "关税配额 tariff-rate quota 滑准税", "labels": [["gk-mx-m07", 1]]},
    {"qid": "q57", "lang": "mix", "query": "环境保护税 environmental protection tax 排放口申报", "labels": [["gk-mx-m09", 1]]},
    {"qid": "q58", "lang": "mix", "query": "社保缴费基数 social insurance contribution base 上下限", "labels": [["gk-mx-m11", 1]]},
    {"qid": "q59", "lang": "mix", "query": "出口退税 export rebate 无纸化申报", "labels": [["gk-mx-m12", 1]]},
    {"qid": "q60", "lang": "mix", "query": "税务行政处罚 tax administrative penalty 听证怎么申请", "labels": [["gk-mx-m13", 1]]},
]

_STOP_EN = {"for", "of", "the", "and", "to", "a", "an", "in", "on", "is", "are",
            "how", "what", "or"}
# 疑问/功能词（检索噪音面——不参与可达性机检；含疑问词的 query 在 PG AND
# 语义下天然不可达是 G-6 已登记差异，基线下限如实记录）
_STOP_ZH_FUNC = {"如何", "怎么", "怎样", "哪些", "多少", "什么", "几级", "情况",
                 "要求", "是谁", "吗", "呢", "包括"}


def _content_tokens(text: str) -> set[str]:
    """内容 token（zh 用 jieba、en 用小写词）——比对口径与检索分词同源。"""
    from knowledge_lattice.adapters.tokenizer import segment

    toks = set(segment(text))
    import re

    toks |= {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-&]*", text)}
    return toks


def _query_tokens(query: str, lang: str) -> set[str]:
    import re

    from knowledge_lattice.adapters.tokenizer import segment

    toks: set[str] = set()
    if lang in ("zh", "mix"):
        toks |= {
            t for t in segment(query)
            if not re.fullmatch(r"[\d\W]+", t) and len(t) >= 2
            and t not in _STOP_ZH_FUNC
        }
    if lang in ("en", "mix"):
        toks |= {
            w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-&]*", query)
            if w.lower() not in _STOP_EN
        }
    return toks


def main() -> int:
    golden_path = EVAL_DIR / "golden.jsonl"
    corpus = {}
    for line in (EVAL_DIR / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            corpus[row["doc_id"]] = row
    existing = {}
    for line in golden_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            existing[row["qid"]] = row

    # legacy 勘误（m3-4 机检暴露）：q27 原标签 mix 但文本纯中（无 ASCII 字母）
    # ——三态一致性断言要求标签可复现，勘误为 zh（M1 标注笔误，非口径变更）。
    if "q27" in existing and existing["q27"].get("lang") == "mix":
        existing["q27"]["lang"] = "zh"

    added, skipped = 0, 0
    problems: list[str] = []
    for q in NEW_QUERIES:
        if q["qid"] in existing:
            skipped += 1
            continue
        # 可达性机检：query 实词 token ⊆ 标注语料 token（标题+正文）
        for corpus_key, _seq in q["labels"]:
            doc = corpus[corpus_key]
            doc_toks = _content_tokens(doc["title"] + doc["text"])
            miss = _query_tokens(q["query"], q["lang"]) - doc_toks
            if miss:
                problems.append(
                    f"{q['qid']}({q['lang']}) 用词不在语料 {corpus_key} 内：{sorted(miss)}")
        existing[q["qid"]] = q
        added += 1
    if problems:
        print("可达性机检不通过（修正 query 或语料后重跑）：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    ordered = [existing[k] for k in sorted(existing, key=lambda x: int(x[1:]))]
    golden_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in ordered) + "\n",
        encoding="utf-8",
    )
    langs: dict[str, int] = {}
    for r in ordered:
        langs[r["lang"]] = langs.get(r["lang"], 0) + 1
    print(f"golden.jsonl: {len(ordered)} queries（+{added}，跳过已有 {skipped}）"
          f"——三态分布 {langs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
