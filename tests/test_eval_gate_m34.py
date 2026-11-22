"""TC-EVAL-04 deepeval 门禁【评测与门禁｜M3】——检索层回归卡门。

design §8 M3 第 3 项「deepeval 门禁进 CI」——本项目 CI=本地 scripts/test_gate.sh
承接（门禁脚本跑全量 pytest，本模块即在其中）。**验收原句**：门禁能卡住一次
人为注入的检索层回归（如调坏权重）；正常变更不误报。

口径（检查点 C 组）：
- **确定性离线**：零 LLM——检索层指标为集合运算（Recall@k），deepeval 面为
  自定义 Metric + ``assert_test``（BaseMetric 子类、``measure``/``a_measure``
  同步确定性计算、输入=真实检索命中序〔harness per_query.hits——m3-4 起〕）；
  模块导入前关闭 deepeval 遥测与 dotenv 注入（离线可跑、不污染进程环境）；
- **逐 query 下限**（exact 冻结——系统确定性：TokenBagEmbedder/jieba/FTS/RRF
  全链确定性，基线值即可复现值）：任何 query 的 recall@10 回退即红；
- **聚合下限**（0.05 余量）：recall@5/@10、MRR 均值回退红——排序质量回退
  （recall@10 不掉但 RR 掉）也卡门；
- 下限来源：M3 完整集（60q/73docs）双后端实测（同口径基线报告
  eval/reports/m3-baseline-*.md / *.json）。**m3-5 起 clean env**
  （eval_seed.seed_clean_eval_matrix——与基线生成环境完全同源、语料外
  命中面移除；m3-4 沿用 conftest 标准矩阵 5 篇杂文档，recall@10 恰好
  一致但 RR 名次面漂移，见主用例 docstring）。

注入实证（TC-EVAL-04 验收动作）：人为注入检索层回归（如 retrieve.py 候选序
反转/RRF 权重调坏）→ 本模块红（逐 query recall@10 下限击穿）；恢复源码 → 绿
（记录归档 eval/reports/m3-4-injection-evidence.md）。
"""

from __future__ import annotations

import os

# deepeval 离线确定性口径（先于任何 deepeval 导入生效）：
# - DISABLE_DOTENV：禁止 deepeval autoload .env 污染测试进程环境（隔离纪律）
# - TELEMETRY_OPT_OUT：门禁不依赖外网（遥测关闭）
os.environ.setdefault("DEEPEVAL_DISABLE_DOTENV", "1")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")

from eval_seed import seed_clean_eval_matrix  # noqa: E402
from test_eval_01_golden import EVAL_DIR, ORG, _eval_env  # noqa: E402

from knowledge_lattice.eval.harness import load_corpus, load_golden, run_evaluation  # noqa: E402

# ---- 逐 query recall@10 下限（exact 冻结；m3-4 实测，来源见模块 docstring；
#      生成：门禁同环境实测逐 query 值——与 eval/reports/m3-baseline-*.json
#      per_query.recall@10 逐条一致；0 值=该后端当前配方诚实零〔如 sqlite q24/
#      q50/q57、pg 含疑问词 query 的 AND 不可达——G-6 已登记差异〕，聚合下限
#      承担其回退检测面）----
_R10_FLOORS: dict[str, dict[str, float]] = {
    "sqlite": {
        "q01": 1.0, "q02": 1.0, "q03": 1.0, "q04": 1.0, "q05": 1.0, "q06": 0.5, "q07": 0.5, "q08": 0.5,
        "q09": 0.5, "q10": 1.0, "q11": 1.0, "q12": 1.0, "q13": 1.0, "q14": 1.0, "q15": 1.0, "q16": 1.0,
        "q17": 1.0, "q18": 1.0, "q19": 1.0, "q20": 1.0, "q21": 1.0, "q22": 1.0, "q23": 1.0, "q24": 0.0,
        "q25": 1.0, "q26": 1.0, "q27": 1.0, "q28": 1.0, "q29": 1.0, "q30": 1.0, "q31": 1.0, "q32": 1.0,
        "q33": 1.0, "q34": 1.0, "q35": 1.0, "q36": 1.0, "q37": 1.0, "q38": 1.0, "q39": 1.0, "q40": 1.0,
        "q41": 1.0, "q42": 1.0, "q43": 1.0, "q44": 1.0, "q45": 1.0, "q46": 1.0, "q47": 1.0, "q48": 1.0,
        "q49": 1.0, "q50": 0.0, "q51": 1.0, "q52": 1.0, "q53": 1.0, "q54": 1.0, "q55": 1.0, "q56": 1.0,
        "q57": 0.0, "q58": 1.0, "q59": 1.0, "q60": 1.0,
    },
    "pg": {
        "q01": 0.0, "q02": 0.0, "q03": 1.0, "q04": 1.0, "q05": 1.0, "q06": 0.5, "q07": 0.5, "q08": 0.5,
        "q09": 0.5, "q10": 0.0, "q11": 0.0, "q12": 1.0, "q13": 1.0, "q14": 1.0, "q15": 1.0, "q16": 1.0,
        "q17": 1.0, "q18": 1.0, "q19": 0.5, "q20": 0.0, "q21": 0.5, "q22": 1.0, "q23": 1.0, "q24": 1.0,
        "q25": 1.0, "q26": 1.0, "q27": 1.0, "q28": 1.0, "q29": 1.0, "q30": 0.0, "q31": 1.0, "q32": 1.0,
        "q33": 1.0, "q34": 1.0, "q35": 1.0, "q36": 0.0, "q37": 1.0, "q38": 1.0, "q39": 1.0, "q40": 1.0,
        "q41": 1.0, "q42": 1.0, "q43": 1.0, "q44": 1.0, "q45": 1.0, "q46": 1.0, "q47": 1.0, "q48": 1.0,
        "q49": 1.0, "q50": 1.0, "q51": 1.0, "q52": 1.0, "q53": 1.0, "q54": 1.0, "q55": 1.0, "q56": 1.0,
        "q57": 1.0, "q58": 1.0, "q59": 1.0, "q60": 1.0,
    }
}

# ---- 逐 query RR exact 冻结（m3-5 P3-8——G-29③ 收紧：确定性系统排序回退
#      零成本卡门；recall@10 成员集不变、RR 掉即红；来源=基线 JSON per_query.rr）----
_RR_FLOORS: dict[str, dict[str, float]] = {
    "sqlite": {
        "q01": 0.1429, "q02": 1.0, "q03": 1.0, "q04": 1.0, "q05": 1.0, "q06": 1.0, "q07": 1.0, "q08": 1.0,
        "q09": 1.0, "q10": 0.1, "q11": 0.25, "q12": 1.0, "q13": 1.0, "q14": 1.0, "q15": 1.0, "q16": 0.1429,
        "q17": 1.0, "q18": 0.1, "q19": 1.0, "q20": 0.5, "q21": 0.3333, "q22": 1.0, "q23": 1.0, "q24": 0.0,
        "q25": 1.0, "q26": 1.0, "q27": 1.0, "q28": 1.0, "q29": 1.0, "q30": 0.3333, "q31": 1.0, "q32": 1.0,
        "q33": 1.0, "q34": 1.0, "q35": 1.0, "q36": 1.0, "q37": 1.0, "q38": 1.0, "q39": 1.0, "q40": 1.0,
        "q41": 1.0, "q42": 1.0, "q43": 1.0, "q44": 1.0, "q45": 0.2, "q46": 1.0, "q47": 1.0, "q48": 1.0,
        "q49": 1.0, "q50": 0.0, "q51": 0.5, "q52": 0.25, "q53": 0.3333, "q54": 1.0, "q55": 1.0, "q56": 1.0,
        "q57": 0.0, "q58": 1.0, "q59": 1.0, "q60": 1.0,
    },
    "pg": {
        "q01": 0.0, "q02": 0.0, "q03": 1.0, "q04": 1.0, "q05": 1.0, "q06": 0.5, "q07": 1.0, "q08": 0.25,
        "q09": 1.0, "q10": 0.0, "q11": 0.0, "q12": 0.5, "q13": 1.0, "q14": 1.0, "q15": 1.0, "q16": 1.0,
        "q17": 0.1429, "q18": 1.0, "q19": 0.2, "q20": 0.0, "q21": 1.0, "q22": 1.0, "q23": 1.0, "q24": 1.0,
        "q25": 1.0, "q26": 1.0, "q27": 0.3333, "q28": 1.0, "q29": 1.0, "q30": 0.0, "q31": 0.25, "q32": 1.0,
        "q33": 0.5, "q34": 0.3333, "q35": 1.0, "q36": 0.0, "q37": 1.0, "q38": 1.0, "q39": 0.5, "q40": 0.125,
        "q41": 1.0, "q42": 1.0, "q43": 1.0, "q44": 0.3333, "q45": 1.0, "q46": 1.0, "q47": 1.0, "q48": 1.0,
        "q49": 1.0, "q50": 1.0, "q51": 0.1111, "q52": 1.0, "q53": 1.0, "q54": 1.0, "q55": 1.0, "q56": 1.0,
        "q57": 1.0, "q58": 1.0, "q59": 1.0, "q60": 0.2,
    }
}


def _golden_recall_metric():
    from deepeval.metrics import BaseMetric

    class GoldenRecallMetric(BaseMetric):
        """黄金集 Recall@k（检索层、零 LLM）：context=期望命中集合（黄金标注）、
        retrieval_context=实际检索命中序（harness per_query.hits 真实序列）
        ——集合运算确定性指标，排序无关（k 内成员变动即分值变动）。"""

        def __init__(self, threshold: float, k: int = 10):
            self.threshold = threshold
            self.k = k

        def measure(self, test_case, *args, **kwargs):
            expected = set(test_case.context or [])
            actual = list(test_case.retrieval_context or [])[: self.k]
            self.score = (
                len(expected & set(actual)) / len(expected) if expected else 0.0
            )
            self.reason = (
                f"recall@{self.k}={self.score:.4f}"
                f"（k 内命中 {sorted(expected & set(actual))}"
                f" / 期望 {sorted(expected)}）"
            )
            return self.score

        async def a_measure(self, test_case, *args, **kwargs):
            return self.measure(test_case, *args, **kwargs)

    return GoldenRecallMetric


# ---- 聚合下限（双后端各档、0.05 余量；实测：sqlite r@5=0.8417/r@10=0.9167/
#      MRR=0.8031；pg r@5=0.7833/r@10=0.8333/MRR=0.7213——m3-baseline-*.md）----
_AGG_FLOORS = {
    "sqlite": {"recall5": 0.79, "recall10": 0.87, "mrr": 0.75},
    "pg": {"recall5": 0.73, "recall10": 0.78, "mrr": 0.67},
}


def test_tc_eval_04_deepeval_gate_blocks_retrieval_regression(backend, tmp_path) -> None:
    """TC-EVAL-04：M3 完整集全量跑 → deepeval 逐 query recall@10 卡门 + 聚合下限。

    **m3-5 clean env**（P3-8/P3-9 前提）：``eval_seed.seed_clean_eval_matrix``
    ——门禁环境与基线生成环境（scripts/eval_baseline.py）完全同源、语料外
    命中面移除（m3-4 沿用 conftest 标准矩阵的 5 篇杂文档会压缩 in-corpus
    名次——sqlite q11 RR 0.3333≠基线 0.25，RR exact 冻结因此暴露该漂移；
    recall@10 两环境恰好一致，m3-4 冻结面未受影响）。
    """
    from deepeval import assert_test
    from deepeval.test_case import LLMTestCase

    seed_clean_eval_matrix(backend)
    env = _eval_env(backend, tmp_path)

    corpus = load_corpus(EVAL_DIR / "corpus.jsonl")
    golden = load_golden(EVAL_DIR / "golden.jsonl")
    report = run_evaluation(
        backend=env["backend"],
        settings=env["settings"],
        embedder=env["embedder"],
        gate=env["gate"],
        corpus=corpus,
        golden=golden,
        user_id="u_full",
        org_id=ORG,
        objects_dir=env["objects_dir"],
        ingest_service=env["service"],
    )
    backend_name = env["db"].name
    assert report["queries"] == len(golden) == 60
    assert report["corpus_docs"] == len(corpus) == 73

    # ---- deepeval 面：逐 query Recall@10（真实命中序输入；下限=冻结基线）----
    # P3-2（m3-5）：完整性断言替代 floor=None fail-open——冻结表与 golden 的
    # qid 集合必须严丝合缝（防「golden 换 query、冻结表没跟上」静默绿）；
    # 判定用显式 raise（P3-7——python -O 下 assert 剥离，显式 raise 双模式等强）。
    metric_cls = _golden_recall_metric()
    floors = _R10_FLOORS[backend_name]
    rr_floors = _RR_FLOORS[backend_name]
    golden_qids = {c.qid for c in golden}
    if set(floors) != golden_qids or set(rr_floors) != golden_qids:
        raise AssertionError(
            f"冻结表 qid 集合与 golden 不一致（recall: {sorted(set(floors) ^ golden_qids)}；"
            f"rr: {sorted(set(rr_floors) ^ golden_qids)}）——新增/替换 query 须显式"
            "重测并同步 _R10_FLOORS/_RR_FLOORS 与基线 JSON（有意变更纪律）"
        )
    for case in golden:
        pq = next(q for q in report["per_query"] if q["qid"] == case.qid)
        floor = floors[case.qid]
        if pq["recall@10"] < floor:
            raise AssertionError(
                f"{case.qid} recall@10 实测 {pq['recall@10']} 低于冻结下限 {floor}"
                "（逐 query 卡门——检索层回归；若为配方有意变更请重测并更新冻结表）"
            )
        # P3-8（m3-5，G-29③ 收紧）：RR exact 冻结——确定性系统排序回退零成本
        # 卡门（top-10 成员集不变、名次掉即红；与基线 JSON 同源，见 P3-9 用例）
        if pq["rr"] != rr_floors[case.qid]:
            raise AssertionError(
                f"{case.qid} rr 实测 {pq['rr']} ≠ 冻结值 {rr_floors[case.qid]}"
                "（per-query RR exact——纯排序回退；若为配方有意变更请重测并更新冻结表）"
            )
        tc = LLMTestCase(
            input=case.query,
            actual_output=case.query,
            expected_output=case.query,
            context=[f"{doc}#{seq}" for doc, seq in case.labels],
            retrieval_context=[f"{doc}#{seq}" for doc, seq in pq["hits"]],
        )
        assert_test(tc, [metric_cls(threshold=floor)])

    # ---- 聚合下限（排序质量回退也卡门；P3-7 显式 raise——-O 等强）----
    agg = _AGG_FLOORS[backend_name]
    if report["recall@10"] < agg["recall10"]:
        raise AssertionError(
            f"recall@10 聚合回退：{report['recall@10']} < {agg['recall10']}")
    if report["recall@5"] < agg["recall5"]:
        raise AssertionError(
            f"recall@5 聚合回退：{report['recall@5']} < {agg['recall5']}")
    if report["mrr"] < agg["mrr"]:
        raise AssertionError(
            f"MRR 聚合回退：{report['mrr']} < {agg['mrr']}")


def test_tc_eval_04_frozen_tables_match_baseline_json() -> None:
    """P3-9（m3-5）：冻结表 vs 基线 JSON 自动同源校验（防「重测只更新一处」）。

    ``_R10_FLOORS``/``_RR_FLOORS`` 逐 qid 与 ``eval/reports/m3-baseline-*.json``
    per_query 值一致；``_AGG_FLOORS`` == round(基线聚合 − 0.05, 2)（0.05 余量
    推导式的机检化）。有意配方变更须**同时**更新基线 JSON 与冻结表——本用例
    即两处同步的看门人（TEST-CASES TC-EVAL-04 v1.9.18 维护口径）。
    """
    import json
    from pathlib import Path

    from test_eval_01_golden import EVAL_DIR

    golden_qids = None
    for backend_name in ("sqlite", "pg"):
        path = Path(EVAL_DIR) / "reports" / f"m3-baseline-{backend_name}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        per_q = {q["qid"]: q for q in data["per_query"]}
        if golden_qids is None:
            golden = load_golden(EVAL_DIR / "golden.jsonl")
            golden_qids = {c.qid for c in golden}
        if set(per_q) != golden_qids:
            raise AssertionError(
                f"[{backend_name}] 基线 JSON qid 集与 golden 不一致——重测未同步")
        for qid, pq in per_q.items():
            if _R10_FLOORS[backend_name][qid] != pq["recall@10"]:
                raise AssertionError(
                    f"[{backend_name}] {qid} recall@10 冻结值 "
                    f"{_R10_FLOORS[backend_name][qid]} ≠ 基线 JSON {pq['recall@10']}"
                    "——重测须同时更新冻结表与基线 JSON（同源纪律）")
            if _RR_FLOORS[backend_name][qid] != pq["rr"]:
                raise AssertionError(
                    f"[{backend_name}] {qid} rr 冻结值 "
                    f"{_RR_FLOORS[backend_name][qid]} ≠ 基线 JSON {pq['rr']}"
                    "——重测须同时更新冻结表与基线 JSON（同源纪律）")
        want = {
            "recall5": round(data["recall@5"] - 0.05, 2),
            "recall10": round(data["recall@10"] - 0.05, 2),
            "mrr": round(data["mrr"] - 0.05, 2),
        }
        if _AGG_FLOORS[backend_name] != want:
            raise AssertionError(
                f"[{backend_name}] 聚合下限 {_AGG_FLOORS[backend_name]} ≠ "
                f"round(基线−0.05,2)={want}——0.05 余量推导失同步")


def test_tc_eval_04_gate_metric_pure_semantics() -> None:
    """门禁指标纯语义（零 LLM 边界）：全命中/无命中/部分命中/空期望的确定性。"""
    from deepeval.test_case import LLMTestCase

    cls = _golden_recall_metric()
    m = cls(threshold=1.0)

    def _tc(expected: list[str], actual: list[str]):
        return LLMTestCase(
            input="q", actual_output="a", expected_output="a",
            context=expected, retrieval_context=actual,
        )

    assert m.measure(_tc(["gk-vat-01#1"], ["gk-vat-01#1", "x#1"])) == 1.0
    assert m.measure(_tc(["gk-vat-01#1"], ["x#1", "y#1"])) == 0.0
    assert m.measure(_tc(["a#1", "b#1"], ["b#1", "c#1", "d#1"])) == 0.5
    assert m.measure(_tc([], ["x#1"])) == 0.0
    # k 截断：期望在第 11 位不算 top-10 命中
    actual11 = [f"d{i}#1" for i in range(10)] + ["target#1"]
    assert m.measure(_tc(["target#1"], actual11)) == 0.0
