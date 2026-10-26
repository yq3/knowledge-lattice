"""TC-EVAL-01 M1 小型黄金集【评测｜M1——双后端参数化基线】。

- 黄金集（28 条：纯中/纯英/中英混排）+ 合成语料（39 docs，含 GBK 编码样例与
  多 chunk 文档）批量上线 → Recall@k / MRR 检索层指标（集合运算、零 LLM）；
- **多 token 场景覆盖**（m1-1 Tester 观察项）：每条 query 的 jieba 切分 ≥2 token；
- 基线数字归档 eval/reports/m1-baseline-<backend>.md（scripts/eval_baseline.py
  生成——M1-5 校准实验输入；本用例断言回归下限，防基线无声回退）。
"""

from __future__ import annotations

import json
from pathlib import Path

from helpers import seed_dataset

from knowledge_lattice.adapters.tokenizer import segment_query
from knowledge_lattice.eval.harness import load_corpus, load_golden, run_evaluation

ORG = "org:tax"
EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"

# 评测向量代理：TokenBagEmbedder(dim=32)——token 袋确定性嵌入（稠密路有语义
# 排序信号；FakeEmbedder 哈希向量是纯噪声会压过 BM25——口径见基线报告）
_EVAL_DIM = 32

# 回归下限（低于基线报告数字留余量——防检索配方无声回退；数值来源见
# eval/reports/m1-baseline-*.md 的实测记录）。**按后端分别设限**：PG 的
# to_tsquery `&` AND 语义（design §5.2 钉死口径——与 sqlite OR 拼接是已登记
# 后端差异，G-6/A-17）使含疑问词的中文 query 全词交集不可达 → 召回天然偏低，
# 双后端基线差异本身即 G-6 的记录对象（M1-5 校准实验输入）
_FLOORS = {
    # 实测基线（eval/reports/m1-baseline-*.md）：sqlite r@10=0.8929/MRR=0.8345、
    # pg r@10=0.7857/MRR=0.7277——下限各留 ~0.05 余量防配方无声回退
    "sqlite": {"recall10": 0.84, "recall5": 0.79, "mrr": 0.78},
    "pg": {"recall10": 0.73, "recall5": 0.66, "mrr": 0.67},
}


def _eval_env(matrix, tmp_path):
    """评测栈（与 qual_env 同构、向量路换 TokenBagEmbedder——评测口径自持）。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.docs.quality import QualityService
    from fake_providers import TokenBagEmbedder

    backend = matrix.make_backend()
    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=_EVAL_DIM,
        embed_model="tokbag-embed",
    )
    embedder = TokenBagEmbedder(dim=_EVAL_DIM)
    gate = EmbeddingGate()
    objects_dir = tmp_path / "objects"
    quality = QualityService(backend, settings)
    service = IngestService(
        backend, embedder, settings, gate, objects_dir, quality=quality
    )
    return {
        "db": matrix, "backend": backend, "settings": settings, "gate": gate,
        "embedder": embedder, "objects_dir": objects_dir, "quality": quality,
        "service": service, "label": settings.embed_model_label,
    }


def test_eval_01_golden_baseline(matrix, tmp_path) -> None:
    env = _eval_env(matrix, tmp_path)
    db = env["db"]
    seed_dataset(db, ORG, "ds:expense_lib")  # 费用域语料库（语料文件引用）

    corpus = load_corpus(EVAL_DIR / "corpus.jsonl")
    golden = load_golden(EVAL_DIR / "golden.jsonl")
    assert len(corpus) == 39 and len(golden) == 28

    # 多 token 覆盖（m1-1 观察项）：全部 query jieba 切分 ≥2 token
    thin = [c.qid for c in golden if len(segment_query(c.query)) < 2]
    assert thin == [], f"单 token query 缺乏多 token 覆盖：{thin}"
    # 语言三态覆盖
    langs = {c.lang for c in golden}
    assert langs == {"zh", "en", "mix"}
    counts = {lang: sum(1 for c in golden if c.lang == lang) for lang in langs}
    assert counts["zh"] >= 10 and counts["en"] >= 8 and counts["mix"] >= 8

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

    assert report["queries"] == 28
    assert report["corpus_docs"] == 39
    # 语料全量上线（批量摄取链 B-1：searchable_full 全达）
    not_full = db.execute(
        "SELECT count(*) FROM documents WHERE active_status != 'searchable_full'"
        " AND id NOT IN ('d_cn','d_multi','d_empty_region','d_cit','d_os')"
    ).fetchone()[0]
    assert not_full == 0, "语料文档应全部 searchable_full"
    # GBK 样例与多 chunk 样例真实在场（标注锚点）
    gbk_chunks = db.execute(
        "SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.doc_id"
        " WHERE d.title = '消费税征收范围注释'"
    ).fetchone()[0]
    assert gbk_chunks >= 1, "GBK 编码样例应成功摄取"
    multi = db.execute(
        "SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.doc_id"
        " WHERE d.title = '增值税税率与征收率适用明细'"
    ).fetchone()[0]
    assert multi == 2, "多 chunk 文档应为 2 块（标注 seq=1/2 的锚点）"

    # 基线指标断言（检索层——下限守门，按后端分档）
    floor = _FLOORS[env["db"].name]
    assert report["recall@10"] >= floor["recall10"], (
        f"recall@10 回退：{report['recall@10']} < {floor['recall10']}"
        f"（逐条：{json.dumps(report['per_query'], ensure_ascii=False)}）"
    )
    assert report["recall@5"] >= floor["recall5"]
    assert report["mrr"] >= floor["mrr"], (
        f"MRR 回退：{report['mrr']} < {floor['mrr']}"
    )


def test_eval_01_metrics_pure_functions() -> None:
    """指标纯函数口径（零 LLM——集合运算）：Recall@k/MRR 边界。"""
    from knowledge_lattice.eval.metrics import (
        mean_reciprocal_rank,
        recall_at_k,
        reciprocal_rank,
    )

    results = [("d1", 1), ("d2", 1), ("d3", 1)]
    labels = {("d3", 1), ("d9", 1)}
    assert recall_at_k(results, labels, k=3) == 0.5
    assert recall_at_k(results, labels, k=2) == 0.0
    assert recall_at_k(results, set(), k=3) == 0.0
    assert reciprocal_rank(results, labels) == 1 / 3
    assert reciprocal_rank(results, {("x", 9)}) == 0.0
    assert mean_reciprocal_rank([]) == 0.0
    assert mean_reciprocal_rank(
        [([("a", 1)], {("a", 1)}), ([("b", 1), ("a", 1)], {("a", 1)})]
    ) == 0.75
