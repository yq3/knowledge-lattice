"""TC-EVAL-03 judge 双语校准核心（m3-5 A 组——确定性部分，进门禁）。

三件（本模块纯 python、零 LLM、零网络）：

- **双语 judge prompt**（``build_judge_prompt``）：zh/en/mix 三态 lang 说明 +
  中英双语判定指令——验收原句「judge prompt 双语」；判 faithfulness 二值
  （faithful / unfaithful——响应层忠实度面，与 B 组 ragas 指标同一被评对象）；
- **判读解析**（``parse_judge_verdict``）：judge 自然语言输出 → 二值；不可
  解析显式 ValueError（不静默猜——校准数据的判定来源必须可追溯）；
- **一致率 / Cohen's κ**（``agreement_rate``/``cohens_kappa``/
  ``calibration_report``）：judge vs 人工双评标签吻合度量。**阈值数值归附录
  A-6（监督侧 docs 批——校准数据出来后定数）**，本模块只出度量不出判定。

真实 judge 联调（``run_judge``）：经 ragas_bridge ``build_openai_compat_ragas_llm``
（DashScope OpenAI 兼容端点沿 m2-5 百炼先例，``LATTICE_EVAL_LLM_*`` env 零代码
切换——用户裁定 2026-11-10）；联调动作**不进门禁**（沿 m3-4 口径）。

~50 条人工双评材料（``build_materials``）：黄金集三态抽样 × 两种构造
（faithful=标注语料抽取句 / unfaithful=语料干扰句——跨文档同题域真实表述），
seed 固定确定性可复现；材料入库沿 labeling-notes 先例（eval/reports/）。
人工双评=双轨（用户侧标注回流为主；代行小样须如实申报——用户裁定口径）。
"""

from __future__ import annotations

import random
import re
from collections.abc import Sequence

VERDICT_FAITHFUL = "faithful"
VERDICT_UNFAITHFUL = "unfaithful"

# 判定标签（二值——与 ragas faithfulness 面对齐的「响应是否有依据」）
LABELS = (VERDICT_FAITHFUL, VERDICT_UNFAITHFUL)

# 三态 lang 说明（注入 judge prompt——被评材料的语言形态，沿 m3-4 合成口径）
LANG_SPECS = {
    "zh": "纯中文（only Chinese text）",
    "en": "纯英文（only English text）",
    "mix": "中英混排（mixed Chinese and English）",
}

# 判读词表两级：**长词**任意位置检索（否定形先于肯定形——"unfaithful" 含
# "faithful" 子串、"不忠实" 含 "忠实"）；**短词**（是/否/yes/no/0/1）只在
# 「末行判定词」整体匹配（防自由文本中的单字误命中——如「这是一个无法
# 判定的输出」含「是」但不是判定词）。
_NEG_LONG = ("unfaithful", "不忠实", "无依据", "编造", "fabricat",
             "not faithful", "faithful: no", "verdict: no")
_POS_LONG = ("faithful", "忠实", "有依据", "verdict: yes")
_NEG_SHORT = ("no", "否", "0")
_POS_SHORT = ("yes", "是", "1")
_LABEL_PREFIX = ("verdict", "判定", "结论", "判断", "answer", "result")


def build_judge_prompt(item: dict, *, lang: str) -> str:
    """双语 judge prompt（TC-EVAL-03——验收原句「judge prompt 双语」）。

    item 字段：query / response / reference（判 faithfulness 三要素——
    reference=黄金标注语料文本，judge 对照面）。输出要求单行二值判定
    （可带简短理由，判读经 ``parse_judge_verdict``）。
    """
    return (
        "你是企业知识库响应质量评测的裁判（judge / 裁判）。判断下面的"
        "「回答 response」是否完全有依据于「参考资料 reference」——即回答中的"
        "每个事实性陈述都能在参考资料中找到支持（faithfulness / 忠实度）。\n"
        "You are a judge for enterprise knowledge-base response quality. "
        "Decide whether the response is fully grounded in the reference "
        "(faithfulness): every factual claim in the response must be "
        "supported by the reference.\n\n"
        f"语言形态 / language: {LANG_SPECS[lang]}\n\n"
        f"问题 / query:\n{item['query']}\n\n"
        f"参考资料 / reference:\n{item['reference']}\n\n"
        f"回答 / response:\n{item['response']}\n\n"
        "判定 / verdict（单行，二选一 / exactly one of:\n"
        "「faithful」= 有依据 / grounded；「unfaithful」= 无依据或超出参考"
        "资料 / unsupported):"
    )


def parse_judge_verdict(text: str) -> str:
    """judge 输出 → 二值判定（faithful / unfaithful）。

    两级匹配：长判定词（faithful/忠实/unfaithful/不忠实…）在全文检索
    （否定形优先——子串包含关系）；短判定词（yes/no/是/否/1/0）在**末行**
    剥离标签前缀（verdict:/判定：…）与标点后整体匹配。两级均未命中 →
    ValueError（不静默猜——校准判定来源必须可解析）。
    """
    if not text or not text.strip():
        raise ValueError(f"judge 输出为空，无法判定: {text!r}")
    lowered = text.strip().lower()
    for marker in _NEG_LONG:
        if marker in lowered:
            return VERDICT_UNFAITHFUL
    for marker in _POS_LONG:
        if marker in lowered:
            return VERDICT_FAITHFUL
    lines = [ln for ln in lowered.splitlines() if ln.strip()]
    if lines:
        token = lines[-1].strip()
        for prefix in _LABEL_PREFIX:
            if token.startswith(prefix):
                token = token[len(prefix):]
        token = token.strip("：: ，,。.；;（）()-—\t ")
        if token in _NEG_SHORT:
            return VERDICT_UNFAITHFUL
        if token in _POS_SHORT:
            return VERDICT_FAITHFUL
    raise ValueError(f"judge 输出无二值判定词: {text!r}")


# ============ 一致率 / κ（确定性数学——阈值归 A-6 监督侧） ============


def agreement_rate(a: Sequence[str], b: Sequence[str]) -> float:
    """简单一致率 = 吻合数 / n。空集 / 长度不齐显式拒（校准输入 bug）。"""
    if not a or not b:
        raise ValueError("一致率不可计算于空标签集")
    if len(a) != len(b):
        raise ValueError(f"标签长度不齐: {len(a)} != {len(b)}")
    return sum(x == y for x, y in zip(a, b)) / len(a)


def cohens_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's κ（_chance-corrected agreement_）。

    κ = (po − pe) / (1 − pe)：po=观察一致率、pe=边缘分布独立乘积和。
    退化约定（pe=1——双方恒单类）：完全一致 → 1.0、否则 0.0（κ 数学上
    0/0，按「无机会修正空间」处理）；输入校验同 ``agreement_rate``。
    """
    if not a or not b:
        raise ValueError("κ 不可计算于空标签集")
    if len(a) != len(b):
        raise ValueError(f"标签长度不齐: {len(a)} != {len(b)}")
    n = len(a)
    cats = sorted(set(a) | set(b))
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((list(a).count(c) / n) * (list(b).count(c) / n) for c in cats)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1.0 - pe)


def calibration_report(judge: Sequence[str], human: Sequence[str]) -> dict:
    """judge vs 人工校准报告：n / 一致率 / κ / 混淆矩阵（judge→human 计数）。"""
    rep = {
        "n": len(judge),
        "agreement": agreement_rate(judge, human),
        "kappa": cohens_kappa(judge, human),
    }
    labels = sorted(set(judge) | set(human))
    rep["labels"] = labels
    rep["confusion"] = {
        j: {h: sum(1 for x, y in zip(judge, human) if x == j and y == h)
            for h in labels}
        for j in labels
    }
    return rep


# ============ ~50 条人工双评材料（确定性构建） ============


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """句读切分为**原文偏移区间**（[start, end)——含句尾空白；按偏移取片段
    保证 response 是 reference 的逐字符子串，中英文句读同口径）。"""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in re.finditer(r"[。！？.!?]+(?:\s|$)", text):
        spans.append((start, m.end()))
        start = m.end()
    tail = text.rstrip()
    if start < len(tail):
        spans.append((start, len(tail)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def build_materials(
    texts: dict[str, str],
    golden: Sequence,
    *,
    n: int = 50,
    seed: int = 20261110,
) -> list[dict]:
    """~50 条人工双评材料（确定性、seed 固定可复现——TC-EVAL-03 口径）。

    - **三态抽样**：按 golden lang 层等比抽 n 条（zh/en/mix 全覆盖）；
    - **两种构造**（供一致率非退化——judge 与人工须真判，不能全对/全错）：
      ``faithful``=reference（黄金标注语料文本）的抽取句——有依据；
      ``unfaithful``=**语料内其他文档**的句子（同题域真实业务表述、非编造
      噪声）——对 reference 无依据（幻觉面）；
    - reference 近似口径：标注键 → 语料**全文**（chunk 边界近似为整文档——
      语料以单 chunk 文档为主，如实登记不冒充 chunk 精切）。
    """
    rng = random.Random(seed)
    by_lang: dict[str, list] = {}
    for case in golden:
        by_lang.setdefault(case.lang, []).append(case)

    quota = {}
    total = sum(len(v) for v in by_lang.values())
    remaining = n
    langs_sorted = sorted(by_lang)
    for i, lang in enumerate(langs_sorted):
        if i == len(langs_sorted) - 1:
            quota[lang] = remaining
        else:
            take = max(1, round(n * len(by_lang[lang]) / total))
            take = min(take, len(by_lang[lang]), remaining)
            quota[lang] = take
            remaining -= take

    picked: list = []
    for lang in langs_sorted:
        pool = sorted(by_lang[lang], key=lambda c: c.qid)
        k = min(quota[lang], len(pool))
        picked.extend(rng.sample(pool, k))

    corpus_keys = sorted(texts)
    items: list[dict] = []
    for idx, case in enumerate(picked):
        label_docs = list(dict.fromkeys(doc for doc, _ in case.labels))
        reference = "\n".join(texts[doc] for doc in label_docs)
        distractor_pool = [
            doc for doc in corpus_keys
            if doc not in label_docs and texts[doc].strip()
        ]
        if idx % 2 == 0:  # faithful：reference 连续句片段（1~2 句——有依据）
            spans = _sentence_spans(reference)
            if spans:
                i = rng.randrange(len(spans))
                take = min(len(spans) - i, 1 + rng.randrange(2))
                response = reference[spans[i][0]:spans[i + take - 1][1]].strip()
            else:
                response = reference
            construction = VERDICT_FAITHFUL
        else:  # unfaithful：语料干扰句（跨文档真实表述、对 reference 无依据）
            d = texts[rng.choice(distractor_pool)]
            d_spans = _sentence_spans(d)
            if d_spans:
                s, e = d_spans[rng.randrange(len(d_spans))]
                response = d[s:e].strip()
            else:
                response = d.strip()
            construction = VERDICT_UNFAITHFUL
        items.append({
            "item_id": f"jm-{idx + 1:02d}",
            "qid": case.qid,
            "lang": case.lang,
            "query": case.query,
            "reference": reference,
            "response": response,
            "construction": construction,
        })
    return items


# ============ 真实 judge 联调（脚本路径——不进门禁） ============


def run_judge(llm, items: Sequence[dict], *, max_parse_retries: int = 1) -> list[str]:
    """对材料逐条跑 judge（真实 LLM 端点——ragas BaseRagasLLM 接口）。

    判读失败重试一次（追加强制词表后缀）；仍不可解析 → ValueError 上抛
    （校准数据不含猜的判定）。返回与 items 等长的二值判定列表。
    """
    from langchain_core.prompts import PromptTemplate

    verdicts: list[str] = []
    for item in items:
        prompt = build_judge_prompt(item, lang=item["lang"])
        value = PromptTemplate.from_template("{q}").invoke({"q": prompt})
        text = llm.generate_text(value).generations[0][0].text or ""
        try:
            verdicts.append(parse_judge_verdict(text))
            continue
        except ValueError:
            if max_parse_retries <= 0:
                raise
        strict = PromptTemplate.from_template("{q}").invoke({
            "q": prompt
            + "\n（重试——上一输出无法判读 / retry, previous output was "
              "unparseable。只输出 faithful 或 unfaithful / output exactly "
              "one word: faithful or unfaithful）",
        })
        text = llm.generate_text(strict).generations[0][0].text or ""
        verdicts.append(parse_judge_verdict(text))  # 再失败即上抛
    return verdicts
