#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""m3-4 A 组：TC-EVAL-02 合成候选生成（ragas 选型口径——一次性离线动作）。

LLM 端点沿 m2-5 百炼先例（用户裁定 2026-11-08 21:07）：DashScope OpenAI 兼容
端点，LATTICE_* env 零代码切换；生成走 ragas 的 BaseRagasLLM 接口（与 m3-5
响应层 judge 同一抽象面——judge 校准归 m3-5，本脚本只做候选生成）。

口径（检查点 A 组）：
- **一次性离线动作**：生成物（候选）落 data/eval-synth/（不入库），人工抽检
  修正后的最终黄金集入 eval/golden.jsonl——复跑评测不依赖本脚本与端点；
- 生成/联调动作**不进门禁**（沿 m2-5 百炼联调先例）；
- 每条候选要求用词出现在源文档内（当前配方 BM25 词面 + token 袋向量——无跨
  语言召回能力，标注可达性纪律沿 M1 labeling-notes 规则 3）。

**受阻申报（2026-11-08，m3-4）**：真实端点生成当日受阻——本 key 的 chat 免费配额
耗尽（qwen-plus/qwen-max/qwen-flash 403 AllocationQuota；qwen-turbo 持续 429
limit_requests；qwen3-max 404；无本地 ollama 端点）。处置沿 m2-5 受阻先例：
端点路径与验证证据保留（脚本本件），本批候选以 ``--offline`` 确定性模式生成
（模板从语料标题/正文术语构造、零 LLM），人工抽检修正后入库；配额恢复后可
直接重跑本脚本（缺省 LLM 模式）产出 LLM 候选供人工复核增补（补位不替换——
替换需重走标注评审）。

用法（需 eval 依赖组 + 端点凭据）：
  uv run --group eval python scripts/eval_synth_m34.py            # LLM 生成候选
  uv run --group eval python scripts/eval_synth_m34.py --offline  # 确定性模板候选
  uv run --group eval python scripts/eval_synth_m34.py --check    # 复核语料在场

env（缺 key 直接退出——不静默降级）：
  LATTICE_EVAL_LLM_API_BASE（缺省 DashScope compatible-mode）
  LATTICE_EVAL_LLM_KEY（fallback DASHSCOPE_API_KEY——沿 benchmarks/calib_m2_5
    的 .env 运行时读取形态，只读不打印）
  LATTICE_EVAL_LLM_MODEL（缺省 qwen-plus）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

EVAL_DIR = ROOT / "eval"
OUT_DIR = ROOT / "data" / "eval-synth"

# 生成目标（m3-4 扩容批语料前缀 → 目标语言态；见 scripts/eval_corpus_m34.py）
TARGETS: list[tuple[str, str]] = [
    # ---- zh：9 篇纯中 + 3 篇混排语料的纯中问法 ----
    *[(f"gk-zh-m{i:02d}", "zh") for i in range(1, 10)],
    ("gk-mx-m03", "zh"),
    ("gk-mx-m08", "zh"),
    ("gk-mx-m10", "zh"),
    # ---- en：12 篇纯英 + 2 篇混排语料的纯英问法 ----
    *[(f"gk-en-m{i:02d}", "en") for i in range(1, 13)],
    ("gk-mx-m05", "en"),
    ("gk-mx-m12", "en"),
    # ---- mix：13 篇混排语料 ----
    *[(f"gk-mx-m{i:02d}", "mix") for i in range(1, 14)],
]

_LANG_SPEC = {
    "zh": "纯中文（只出现汉字与数字标点，不得出现任何英文单词）",
    "en": "纯英文（only English words, digits and punctuation — no Chinese characters）",
    "mix": (
        "中英混排（同一条 query 里既有中文词汇又有对应的英文关键术语，"
        "如「增值税 VAT 留抵退税」形态——两种语言的业务词都要出现）"
    ),
}

_PROMPT = (
    "你是企业税务知识库的检索质量评测工程师。基于下面的文档内容，生成 {n} 条"
    "检索测试 query 候选，用于评测向量/关键词检索系统。\n"
    "要求：\n"
    "1. 语言形态：{lang_spec}；\n"
    "2. query 中的关键用词必须逐字出现在文档原文中（检索系统按词面匹配，"
    "不得使用文档里没有的同义改写词）；\n"
    "3. 模拟企业用户自然提问口吻（提问式或短语式均可），聚焦文档的核心业务点"
    "（条件/标准/程序/税率/时限等），每条 query 覆盖不同侧面；\n"
    "4. 每条 6~20 个词，不要编号，每行一条。\n"
    "文档标题：{title}\n文档内容：{text}\n输出（每行一条，共 {n} 条）："
)


# ---- ragas LLM 抽象面：与 m3-5 响应层 judge 共用（单一实现——见
# src/knowledge_lattice/eval/ragas_bridge.py build_openai_compat_ragas_llm） ----

def _build_llm():
    from knowledge_lattice.eval.ragas_bridge import build_openai_compat_ragas_llm

    return build_openai_compat_ragas_llm()


def _offline_candidates(title: str, text: str, lang: str) -> list[str]:
    """确定性模板候选（零 LLM）：从标题/正文术语构造，保证用词在文档内。

    模板面按三态分派：zh→中文模板 × 中文标题主题；en→英文模板 × 英文标题
    主题词；mix→标题/正文的中英术语对组合（m3 语料标题按「中文（English）」
    形态构造，术语对天然在场）。候选仅是**起点**——人工抽检修正是标注流程
    的一部分（labeling-notes 规则沿用）。
    """
    import re

    def zh_topic() -> str:
        # 标题去掉括注英文/书名号后缀，取主题短语
        t = re.sub(r"[（(].*?[)）]", "", title).replace("《", "").replace("》", "")
        return t.strip()

    def en_topic() -> str:
        # 英文标题取实词（去介冠词），lowercase 保留术语原形
        stop = {"for", "and", "the", "of", "on", "to", "with", "in", "a", "an"}
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z-]*", title)
                 if w.lower() not in stop]
        return " ".join(words)

    def mix_pair() -> tuple[str, str]:
        zh = zh_topic()
        m = re.search(r"[（(]([A-Za-z][A-Za-z \-]*?)[)）]", title)
        en = m.group(1).strip() if m else ""
        if not en:  # 兜底：正文首个英文术语
            m2 = re.search(r"[（(]([A-Za-z][A-Za-z \-]{2,})[)）]", text)
            en = m2.group(1).strip() if m2 else ""
        return zh, en

    if lang == "zh":
        t = zh_topic()
        return [f"{t}的条件是什么", f"如何办理{t}", f"{t}的时限要求是怎样规定的"]
    if lang == "en":
        t = en_topic()
        return [f"{t} requirements", f"how to apply {t.lower()}", f"{t} deadline"]
    zh, en = mix_pair()
    tail = {"判定": "判定标准", "标准": "适用标准"}.get(zh[-2:], "办理要求")
    out = []
    if zh and en:
        out.append(f"{zh} {en} 怎么办理")
        out.append(f"{zh}的{tail} {en} 适用条件")
    if not out and zh:
        out.append(f"{zh}的适用条件是什么")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=int, default=3, help="每 (doc,lang) 候选数")
    parser.add_argument("--check", action="store_true",
                        help="只校验目标语料在场（不调端点）")
    parser.add_argument("--offline", action="store_true",
                        help="确定性模板候选（零 LLM——端点受阻时的兜底形态，"
                             "候选仍需人工抽检；见模块 docstring 受阻申报）")
    args = parser.parse_args()

    corpus = {}
    for line in (EVAL_DIR / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            corpus[row["doc_id"]] = row
    missing = [doc_id for doc_id, _ in TARGETS if doc_id not in corpus]
    if missing:
        print(f"目标语料缺席（先跑 scripts/eval_corpus_m34.py）：{missing}",
              file=sys.stderr)
        return 1
    if args.check:
        print(f"check ok: {len(TARGETS)} (doc,lang) targets 全部在场")
        return 0

    llm = None if args.offline else _build_llm()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / ("m34-candidates-offline.jsonl" if args.offline
                          else "m34-candidates.jsonl")
    n_ok = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for doc_id, lang in TARGETS:
            doc = corpus[doc_id]
            if args.offline:
                candidates = _offline_candidates(
                    doc["title"], doc["text"], lang)[: args.candidates]
            else:
                prompt = _PROMPT.format(
                    n=args.candidates, lang_spec=_LANG_SPEC[lang],
                    title=doc["title"], text=doc["text"],
                )
                from langchain_core.prompts import PromptTemplate

                value = PromptTemplate.from_template("{q}").invoke({"q": prompt})
                result = llm.generate_text(value)
                raw = result.generations[0][0].text
                candidates = [
                    ln.strip(" \t-•0123456789.、）)）")
                    for ln in raw.splitlines() if ln.strip()
                ][: args.candidates]
            fh.write(json.dumps(
                {"doc_id": doc_id, "lang": lang, "candidates": candidates},
                ensure_ascii=False) + "\n")
            n_ok += 1
            print(f"[{n_ok}/{len(TARGETS)}] {doc_id}({lang}): {candidates}")
    print(f"candidates written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
