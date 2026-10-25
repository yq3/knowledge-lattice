"""黄金集评测 harness（TC-EVAL-01——M1 小型黄金集最小实现）。

流程：合成语料批量摄取（TXT——顺路覆盖 TC-ING-04① 编码探测路径）→ 逐 query
跑完整检索配方 → 结果 chunk_id 映射 (doc_id, seq) → Recall@k / MRR（检索层、
零 LLM——响应层指标与 judge 属 M3）。

身份约定：语料/黄金集文件用**稳定语料键**（corpus key，如 `gk-vat-01`）；
doc_id 是摄取时生成的 ULID（首次上传不带显式 doc_id——「显式 doc_id=覆盖上传」
为 §6.2 契约不改），harness 在运行时建立 corpus key → doc_id 映射，标注与结果
均落到 (doc_id, seq) 后对齐。

语料与黄金集文件（应用根 `eval/`）：
- corpus.jsonl：{doc_id(=语料键), title, dataset, dims, text, encoding?}——合成
  样例（待决-1 真实语料未到位先行，design 既有注记；覆盖纯中/纯英/中英混排、
  GBK 编码样例与多 chunk 文档）；
- golden.jsonl：{qid, query, lang(zh|en|mix), labels: [[语料键, seq], …]}——
  标注命中 chunk（标注记录归档：eval/reports/labeling-notes.md）。

双后端各一份基线（G-6）：run_evaluation 在同一代码下对 sqlite/pg 参数化各跑，
基线数字归档 eval/reports/m1-baseline-<backend>.md（scripts/eval_baseline.py 生成）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from knowledge_lattice.config import Settings
from knowledge_lattice.eval.metrics import ChunkKey, mean_reciprocal_rank, recall_at_k

logger = logging.getLogger(__name__)

__all__ = [
    "CorpusDoc",
    "GoldenCase",
    "load_corpus",
    "load_golden",
    "build_corpus",
    "run_evaluation",
]


@dataclass(frozen=True)
class CorpusDoc:
    """合成语料文档（TXT 形态——batch ingest 输入）。doc_id 为稳定语料键。"""

    doc_id: str
    title: str
    dataset: str
    dims: dict[str, list[str]]
    text: str
    encoding: str = "utf-8"  # 写盘编码（GBK 样例覆盖编码探测路径，TC-ING-04①）


@dataclass(frozen=True)
class GoldenCase:
    qid: str
    query: str
    lang: str  # zh | en | mix
    labels: tuple[ChunkKey, ...]  # ((语料键, seq), …)


def load_corpus(path: str | Path) -> list[CorpusDoc]:
    docs = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        docs.append(
            CorpusDoc(
                doc_id=row["doc_id"], title=row["title"], dataset=row["dataset"],
                dims=row.get("dims") or {}, text=row["text"],
                encoding=row.get("encoding", "utf-8"),
            )
        )
    return docs


def load_golden(path: str | Path) -> list[GoldenCase]:
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cases.append(
            GoldenCase(
                qid=row["qid"], query=row["query"], lang=row.get("lang", "zh"),
                labels=tuple((d, int(s)) for d, s in row["labels"]),
            )
        )
    return cases


def build_corpus(
    docs: list[CorpusDoc],
    *,
    ingest_service,
    owner_user_id: str,
    org_id: str,
) -> dict[str, str]:
    """批量上线（B-1：验证批量摄取链——首次上传走完整管线 parse→…→quality）。
    返回 {语料键: doc_id}（运行时身份映射——黄金集标注经此落库内坐标）。"""
    out: dict[str, str] = {}
    for doc in docs:
        doc_id, task_id = ingest_service.create_document(
            org_id=org_id,
            dataset_id=doc.dataset,
            title=doc.title,
            dims=doc.dims,
            owner_user_id=owner_user_id,
            file_bytes=doc.text.encode(doc.encoding),
            mime_type="text/plain",
            filename=f"{doc.doc_id}.txt",
        )
        ingest_service.run_task(task_id)
        out[doc.doc_id] = doc_id
    return out


def run_evaluation(
    *,
    backend,
    settings: Settings,
    embedder,
    gate,
    corpus: list[CorpusDoc],
    golden: list[GoldenCase],
    user_id: str,
    org_id: str,
    objects_dir: Path,
    ingest_service=None,
    top_k: int = 10,
) -> dict:
    """摄取语料 → 跑黄金集 → {recall@1/@5/@10, mrr, per_query, corpus}。

    先校验标注可解析（语料键 → (doc_id, seq) 均在库内存在——语料/切分漂移即
    fail-fast，防指标静默失真）。结果映射到语料键后计指标（语料外命中——
    评测环境矩阵遗留文档——不计排名）。
    """
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.docs.retrieve import search as run_search

    service = ingest_service or IngestService(
        backend, embedder, settings, gate, objects_dir
    )
    corpus_ids = build_corpus(
        corpus,
        ingest_service=service,
        owner_user_id=user_id,
        org_id=org_id,
    )

    # 标注可解析校验：语料键 → doc_id → seq 集合
    key_to_chunk_id: dict[ChunkKey, str] = {}
    for corpus_key, doc_id in corpus_ids.items():
        rows = backend.fetch_window(doc_id, version=1, seq_lo=0, seq_hi=100_000)
        if not rows:
            raise ValueError(f"golden label 解析失败：语料 {corpus_key!r} 无块（摄取失败？）")
        for r in rows:
            key_to_chunk_id[(corpus_key, r["seq"])] = r["chunk_id"]
    id_to_key = {cid: key for key, cid in key_to_chunk_id.items()}
    for case in golden:
        for corpus_key, seq in case.labels:
            if (corpus_key, seq) not in key_to_chunk_id:
                raise ValueError(
                    f"golden label 解析失败：{case.qid} → ({corpus_key}, {seq})"
                    " 不在库内（切分漂移？——黄金集与语料需同步修订）"
                )

    per_query: list[dict] = []
    runs: list[tuple[list[ChunkKey], set[ChunkKey]]] = []
    for case in golden:
        payload = run_search(
            backend, settings,
            user_id=user_id, org_id=org_id, query=case.query, top_k=top_k,
            gate=gate, embedder=embedder,
        )
        result_keys: list[ChunkKey] = []
        for r in payload["results"]:
            key = id_to_key.get(r["chunk_id"])
            if key is not None:  # 语料外命中（矩阵遗留文档）不计排名——语料内评估
                result_keys.append(key)
        labels = set(case.labels)
        runs.append((result_keys, labels))
        per_query.append(
            {
                "qid": case.qid,
                "lang": case.lang,
                "n_results": len(result_keys),
                "recall@10": round(recall_at_k(result_keys, labels, k=10), 4),
                "rr": round(mean_reciprocal_rank([(result_keys, labels)]), 4),
            }
        )
    n = len(runs)
    report = {
        "queries": n,
        "recall@1": round(sum(recall_at_k(r, l, k=1) for r, l in runs) / n, 4) if n else 0.0,
        "recall@5": round(sum(recall_at_k(r, l, k=5) for r, l in runs) / n, 4) if n else 0.0,
        "recall@10": round(sum(recall_at_k(r, l, k=10) for r, l in runs) / n, 4) if n else 0.0,
        "mrr": round(mean_reciprocal_rank(runs), 4),
        "per_query": per_query,
        "corpus_docs": len(corpus),
    }
    logger.info("golden eval: %s", {k: v for k, v in report.items() if k != "per_query"})
    return report
