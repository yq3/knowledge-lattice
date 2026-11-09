"""TC-EVAL-02 M3 完整黄金集【评测｜M3】——三态覆盖的可机检断言面。

M1 小型集（28 query）扩容为 M3 完整集（TC-EVAL-02 验收句「黄金集覆盖
纯中/纯英/中英混排三态」——覆盖可机检，进测试）：

- 三态规模与分布（zh/en/mix 各自下限——合成扩容先行，真实 query 占比待
  m3-5/待决-1 语料到位后收口）；
- **lang 标签 × 文本一致性机检**：zh=含 CJK 无 ASCII 字母、en=无 CJK 含
  ASCII 字母、mix=两者兼有（标签错标即红）；
- 标注静态可解析（语料键在 corpus.jsonl 在场、qid 唯一、multi-token 纪律
  ——沿 M1 TC-EVAL-01 口径）；
- 语料侧成对扩容支撑（纯英/混排语料面 + m3 新增前缀组在场）。

合成候选生成：ragas 选型口径（LLM 端点沿 m2-5 百炼先例——DashScope
OpenAI 兼容、LATTICE_* env 零代码切换；一次性离线动作、生成物入库、复跑
不依赖端点——scripts/eval_synth_m34.py；标注记录见
eval/reports/labeling-notes.md）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from knowledge_lattice.adapters.tokenizer import segment_query
from knowledge_lattice.eval.harness import load_corpus, load_golden

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"

# ---- M3 完整集规模（28 → 60；三态分布 24/18/18）----
M3_TOTAL = 60
M3_LANG_COUNTS = {"zh": 24, "en": 18, "mix": 18}
M3_CORPUS_DOCS = 73  # 39 → 73（zh +9 / en +12 / mix +13——成对扩容）

_CJK = re.compile(r"[\u4e00-\u9fff]")
_ASCII_LETTER = re.compile(r"[A-Za-z]")


def _lang_state(text: str) -> str:
    """文本语言三态判定（机检口径）：has_cjk × has_ascii_letter → zh/en/mix。

    数字/标点不参与判定（「增值税13%税率」= zh；「VAT rate 13%」= en）。
    """
    has_cjk = bool(_CJK.search(text))
    has_ascii = bool(_ASCII_LETTER.search(text))
    if has_cjk and has_ascii:
        return "mix"
    return "zh" if has_cjk else "en"


def test_eval_02_m3_complete_set_three_state_coverage() -> None:
    """TC-EVAL-02 验收句：黄金集覆盖三态（规模 + 分布 + 标签一致性）。"""
    golden = load_golden(EVAL_DIR / "golden.jsonl")
    assert len(golden) == M3_TOTAL, (
        f"M3 完整集应 {M3_TOTAL} 条（28 扩容），实际 {len(golden)}"
    )
    counts = {lang: sum(1 for c in golden if c.lang == lang) for lang in M3_LANG_COUNTS}
    assert counts == M3_LANG_COUNTS, f"三态分布应为 {M3_LANG_COUNTS}，实际 {counts}"

    # lang 标签 × 文本一致性（错标即红——三态覆盖不是贴标签而是可复现口径）
    mismatches = [
        (c.qid, c.lang, _lang_state(c.query)) for c in golden
        if _lang_state(c.query) != c.lang
    ]
    assert mismatches == [], f"lang 标签与文本三态不一致：{mismatches}"

    # qid 唯一 + multi-token 纪律（沿 M1：jieba 切分 ≥2）
    qids = [c.qid for c in golden]
    assert len(set(qids)) == len(qids), "qid 不得重复"
    thin = [c.qid for c in golden if len(segment_query(c.query)) < 2]
    assert thin == [], f"单 token query 缺乏多 token 覆盖：{thin}"


def test_eval_02_labels_statically_resolvable() -> None:
    """标注静态可解析：语料键在场 + 每条 query ≥1 标注 + seq≥1。"""
    corpus = load_corpus(EVAL_DIR / "corpus.jsonl")
    keys = {d.doc_id for d in corpus}
    golden = load_golden(EVAL_DIR / "golden.jsonl")
    for case in golden:
        assert case.labels, f"{case.qid} 无标注"
        for corpus_key, seq in case.labels:
            assert corpus_key in keys, (
                f"{case.qid} 标注语料 {corpus_key!r} 不在 corpus.jsonl（同步漂移）"
            )
            assert seq >= 1


def test_eval_02_corpus_paired_expansion() -> None:
    """语料侧成对扩容支撑三态 query：规模 + 纯英/混排语料面 + 新增前缀组。"""
    corpus = load_corpus(EVAL_DIR / "corpus.jsonl")
    assert len(corpus) == M3_CORPUS_DOCS, (
        f"语料应扩至 {M3_CORPUS_DOCS} docs（39 扩容），实际 {len(corpus)}"
    )
    # 语言面（标题+正文为语料可检索主体）：纯英 docs ≥18、混排 docs ≥27
    en_docs = [d for d in corpus if _lang_state(d.title + d.text) == "en"]
    mix_docs = [d for d in corpus if _lang_state(d.title + d.text) == "mix"]
    assert len(en_docs) >= 18, f"纯英语料不足 18（en query 可达面）：{len(en_docs)}"
    assert len(mix_docs) >= 27, f"混排语料不足 27（mix query 可达面）：{len(mix_docs)}"
    # m3 新增三组前缀（成对扩容证据：zh/en/mix 各自新增组）
    prefixes = {"gk-zh-m", "gk-en-m", "gk-mx-m"}
    present = {p for p in prefixes if any(d.doc_id.startswith(p) for d in corpus)}
    assert present == prefixes, f"m3 新增语料前缀组缺席：{prefixes - present}"

    # docs 字段完整性（dims 与既有维度值域一致——region ∈ CN/OS、tax_type ∈ VAT）
    for d in corpus:
        assert d.title and d.text
        for key, values in d.dims.items():
            assert key in ("region", "tax_type"), f"{d.doc_id} 未知维度 {key}"
            assert set(values) <= ({"CN", "OS"} if key == "region" else {"VAT"}), (
                f"{d.doc_id} 维度值越界：{key}={values}"
            )


def test_eval_02_lang_state_helper_pure() -> None:
    """三态判定口径纯函数边界（数字/标点不参与判定）。"""
    assert _lang_state("留抵退税的申请条件是什么") == "zh"
    assert _lang_state("增值税13%税率是多少") == "zh"  # 数字不改变 zh 判定
    assert _lang_state("travel expense reimbursement deadline") == "en"
    assert _lang_state("VAT 留抵退税 excess input VAT refund 申请") == "mix"
    assert _lang_state("金额 100 元与 200 元") == "zh"
