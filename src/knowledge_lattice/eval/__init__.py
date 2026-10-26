"""评测（design §3 eval/——M1-4 前移小型黄金集 + Recall@k/MRR 检索层指标）。

分层纪律（FR-7）：检索层指标（Recall@k / MRR——黄金 chunk 标注的集合运算、
零 LLM）随 M1-4 落地；响应层指标（faithfulness / answer_relevancy，ragas）与
judge 门禁属 M3。黄金集与语料数据文件在应用根 `eval/`（corpus.jsonl /
golden.jsonl / reports/——M1-5 校准实验输入，随仓库归档）。
"""

from knowledge_lattice.eval.harness import (
    CorpusDoc,
    GoldenCase,
    build_corpus,
    load_corpus,
    load_golden,
    run_evaluation,
)
from knowledge_lattice.eval.metrics import mean_reciprocal_rank, recall_at_k

__all__ = [
    "CorpusDoc",
    "GoldenCase",
    "build_corpus",
    "load_corpus",
    "load_golden",
    "run_evaluation",
    "recall_at_k",
    "mean_reciprocal_rank",
]
