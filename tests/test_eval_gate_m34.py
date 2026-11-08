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
  eval/reports/m3-baseline-*.md / *.json——conftest matrix 杂文档 5 篇为语料外
  命中、不参与排名〔harness 语料内评估口径〕，实测值与基线一致）。

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

from helpers import seed_dataset  # noqa: E402
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


def test_tc_eval_04_deepeval_gate_blocks_retrieval_regression(matrix, tmp_path) -> None:
    """TC-EVAL-04：M3 完整集全量跑 → deepeval 逐 query recall@10 卡门 + 聚合下限。"""
    from deepeval import assert_test
    from deepeval.test_case import LLMTestCase

    env = _eval_env(matrix, tmp_path)
    db = env["db"]
    seed_dataset(db, ORG, "ds:expense_lib")

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
    backend_name = db.name
    assert report["queries"] == len(golden) == 60
    assert report["corpus_docs"] == len(corpus) == 73

    # ---- deepeval 面：逐 query Recall@10（真实命中序输入；下限=冻结基线）----
    metric_cls = _golden_recall_metric()
    floors = _R10_FLOORS[backend_name]
    for case in golden:
        pq = next(q for q in report["per_query"] if q["qid"] == case.qid)
        floor = floors.get(case.qid)
        if floor is None:  # 未冻结（首跑/新增 query）——以当次实测为准并提示冻结
            floor = pq["recall@10"]
        assert pq["recall@10"] == floor or pq["recall@10"] >= floor, (
            f"{case.qid} recall@10 实测 {pq['recall@10']} 低于冻结下限 {floor}"
            "（逐 query 卡门——检索层回归；若为配方有意变更请重测并更新冻结表）"
        )
        tc = LLMTestCase(
            input=case.query,
            actual_output=case.query,
            expected_output=case.query,
            context=[f"{doc}#{seq}" for doc, seq in case.labels],
            retrieval_context=[f"{doc}#{seq}" for doc, seq in pq["hits"]],
        )
        assert_test(tc, [metric_cls(threshold=floor)])

    # ---- 聚合下限（排序质量回退也卡门）----
    agg = _AGG_FLOORS[backend_name]
    assert report["recall@10"] >= agg["recall10"], (
        f"recall@10 聚合回退：{report['recall@10']} < {agg['recall10']}"
    )
    assert report["recall@5"] >= agg["recall5"], (
        f"recall@5 聚合回退：{report['recall@5']} < {agg['recall5']}"
    )
    assert report["mrr"] >= agg["mrr"], f"MRR 聚合回退：{report['mrr']} < {agg['mrr']}"


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
