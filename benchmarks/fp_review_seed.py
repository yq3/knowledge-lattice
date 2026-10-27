#!/usr/bin/env python
"""B=②（M1-5 R2 用户裁定）：合成语料区分度误报抽查——人工复核底稿生成。

对 eval/corpus.jsonl（39 docs 合成语料）跑完整摄取管线（quality 阶段真实触达
——flags 由 detect 路径产生），随后：
1. `scripts/quality_sample.py` 确定性抽样 open flags（M1.7 记录形态）；
2. 逐 flag 附块原文/近邻内容/mean_sim/avg_idf（复核表底稿——stdout JSON）。

用法：uv run python benchmarks/fp_review_seed.py --out data/bench-results/m1-5-fp-review-sample.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "benchmarks"))

ORG = "org:tax"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=12)
    parser.add_argument("--seed", default="m1-5-fp")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    from calib_m1_5 import open_backend  # noqa: F401 —— 复用同构基建
    from fake_providers import TokenBagEmbedder

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.docs.quality import QualityService
    from knowledge_lattice.eval.harness import load_corpus

    tmp = Path(tempfile.mkdtemp(prefix="lattice-fpreview-"))
    db, backend, _schema, conn = open_backend("sqlite", tmp)
    settings = Settings(
        environment="test", data_dir=tmp, embed_dim=32, embed_model="tokbag-embed",
    )
    embedder = TokenBagEmbedder(dim=32)
    gate = EmbeddingGate()
    quality = QualityService(backend, settings)
    service = IngestService(
        backend, embedder, settings, gate, tmp / "objects", quality=quality
    )

    corpus = load_corpus(ROOT / "eval" / "corpus.jsonl")
    doc_ids = {}
    for doc in corpus:
        doc_id, task_id = service.create_document(
            org_id=ORG, dataset_id=doc.dataset, title=doc.title, dims=doc.dims,
            owner_user_id="u_full", file_bytes=doc.text.encode(doc.encoding),
            mime_type="text/plain", filename=f"{doc.doc_id}.txt",
        )
        service.run_task(task_id)
        doc_ids[doc.doc_id] = doc_id

    total_flags = backend.list_quality_flags(org_id=ORG, state="open")
    sample = quality.sample_open_flags(ORG, n=args.n, seed=args.seed)

    rows = []
    for flag in sample:
        chunk = backend.get_chunk(flag["chunk_id"])
        chunk_rows = backend.chunks_by_rids([chunk["rid"]]) if chunk else []
        content = chunk_rows[0]["content"] if chunk_rows else ""
        detail = json.loads(flag.get("detail_json") or "{}") if flag.get("detail_json") else {}
        # detect 路径 flags 的 detail 在 flag 行——sample 输出无 detail，补查
        full = backend.get_quality_flag(flag["flag_id"])
        det = json.loads(full["detail_json"]) if full and full["detail_json"] else {}
        neighbors = [
            {
                "chunk_id": n["chunk_id"], "sim": n["sim"],
                "content": (backend.chunks_by_rids(
                    [backend.get_chunk(n["chunk_id"])[
                        "rid"]])[0]["content"][:60] + "…")
                if backend.get_chunk(n["chunk_id"]) else "",
            }
            for n in det.get("neighbors", [])[:3]
        ]
        rows.append({
            "flag_id": flag["flag_id"], "doc": flag["doc_id"],
            "chunk_id": flag["chunk_id"], "reason": flag["reason"],
            "mean_sim": det.get("mean_sim"), "avg_idf": det.get("avg_idf"),
            "idf_scope": det.get("idf_scope"),
            "content_head": content[:80] + ("…" if len(content) > 80 else ""),
            "neighbors": neighbors,
        })

    payload = {
        "corpus_docs": len(corpus), "open_flags_total": len(total_flags),
        "sample_seed": args.seed, "sampled": len(rows), "flags": rows,
        "reasons_hist": {},
    }
    for f in total_flags:
        payload["reasons_hist"][f["reason"]] = payload["reasons_hist"].get(f["reason"], 0) + 1

    out = Path(args.out) if args.out else ROOT / "data" / "bench-results" / "m1-5-fp-review-sample.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n工件：{out}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
