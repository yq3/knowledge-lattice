"""m3-5 B 组：响应层指标接入形态（ragas faithfulness / answer_relevancy）。

m3-4 P3-6 清偿 + B 组固化：``retrieval_report_to_samples`` docstring 与实现
不符（user_input=qid、reference=None——m3-5 误导陷阱）→ **改签名接收 golden**
填 user_input=query / reference=黄金标注；响应层评测输入行
（``response_layer_rows``——纯 python、门禁可测）经 ``rows_to_ragas_samples``
惰性转 ragas SingleTurnSample（真实 LLM judge 链路不进门禁——沿 m3-4 口径）。
"""

from __future__ import annotations

from pathlib import Path

from knowledge_lattice.eval.harness import GoldenCase, load_corpus, load_golden
from knowledge_lattice.eval.ragas_bridge import response_layer_rows

ROOT = Path(__file__).resolve().parent.parent

_REPORT = {
    "queries": 2,
    "per_query": [
        {"qid": "q01", "lang": "zh", "hits": [["gk-vat-01", 1], ["gk-zh-m01", 1]]},
        {"qid": "q02", "lang": "en", "hits": [["gk-exp-01", 1]]},
    ],
}
_GOLDEN = [
    GoldenCase(qid="q01", query="增值税税率是多少", lang="zh",
               labels=(("gk-vat-01", 1),)),
    GoldenCase(qid="q02", query="what is the expense policy", lang="en",
               labels=(("gk-exp-01", 1), ("gk-exp-02", 1))),
]
_TEXTS = {
    "gk-vat-01": "增值税基本税率为百分之十三。",
    "gk-zh-m01": "数电票通过电子发票服务平台开具。",
    "gk-exp-01": "Expense reports must be submitted monthly.",
    "gk-exp-02": "Receipts are required for reimbursement.",
}


def test_response_layer_rows_p3_6_semantics() -> None:
    """P3-6：user_input=query 文本（非 qid）、reference=黄金标注语料文本、
    retrieved_contexts=命中序语料文本（坐标 → 文本解析）。"""
    rows = response_layer_rows(_REPORT, _GOLDEN, _TEXTS)
    assert len(rows) == 2
    r1, r2 = rows
    # user_input = query 文本（P3-6 陷阱面——原实现误填 qid）
    assert r1["user_input"] == "增值税税率是多少"
    assert r2["user_input"] == "what is the expense policy"
    # reference = 黄金标注语料文本（多标注拼接——judge 对照面）
    assert r1["reference"] == "增值税基本税率为百分之十三。"
    assert r2["reference"] == (
        "Expense reports must be submitted monthly."
        "\nReceipts are required for reimbursement."
    )
    # retrieved_contexts = 命中序语料文本（harness hits 的坐标序保留）
    assert r1["retrieved_contexts"] == [
        "增值税基本税率为百分之十三。", "数电票通过电子发票服务平台开具。"]
    assert r2["retrieved_contexts"] == ["Expense reports must be submitted monthly."]
    # 元数据保留（qid/lang——judge 材料/校准对账键）
    assert r1["qid"] == "q01" and r1["lang"] == "zh"


def test_response_layer_rows_response_injection() -> None:
    """response 注入：responses 按 qid 填（缺省 None——被评对象未给即空，
    真实 LLM 指标运行时由 ragas 校验必填面）。"""
    responses = {"q01": "增值税基本税率为百分之十三。"}
    rows = response_layer_rows(_REPORT, _GOLDEN, _TEXTS, responses=responses)
    by_qid = {r["qid"]: r for r in rows}
    assert by_qid["q01"]["response"] == "增值税基本税率为百分之十三。"
    assert by_qid["q02"]["response"] is None


def test_response_layer_rows_real_corpus_golden_consistency() -> None:
    """真实 M3 完整集一致性：60 行、reference 全可解析（黄金键 → 语料文本）、
    retrieved_contexts 无悬空键（语料漂移即显式 raise）。"""
    corpus = load_corpus(ROOT / "eval" / "corpus.jsonl")
    golden = load_golden(ROOT / "eval" / "golden.jsonl")
    report = {"per_query": [
        {"qid": c.qid, "lang": c.lang, "hits": [list(t) for t in c.labels]}
        for c in golden
    ]}
    texts = {d.doc_id: d.text for d in corpus}
    rows = response_layer_rows(report, golden, texts)
    assert len(rows) == 60
    assert all(r["reference"] for r in rows)
    # 悬空键 fail-fast：report 引用语料外 doc → ValueError（防静默空 context）
    bad = {"per_query": [{"qid": "q01", "lang": "zh", "hits": [["no-such-doc", 1]]}]}
    try:
        response_layer_rows(bad, _GOLDEN[:1], _TEXTS)
        raise AssertionError("悬空语料键应显式拒绝")
    except ValueError as exc:
        assert "no-such-doc" in str(exc)
