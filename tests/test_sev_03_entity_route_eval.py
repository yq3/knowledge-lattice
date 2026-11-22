"""m2s-6 TC-SEV-03 检索增益评测（design §8 M2-S3 验收句——A4）。

- docs 黄金集（m3-4 起 corpus.jsonl 73 篇 + golden.jsonl 60 条——TC-EVAL-02
  完整集；28 条期数字见报告历史档）开/关实体召回路对比 **recall@10 与 MRR**——**不回退才允许 auto_entities 默认开启**，否则保持
  显式参数（默认值断言：False——保守档，按实测结论）；
- 实体路面：参考词典（eval/semantic_seed——与语料同域）+ build + ingest
  同事务打标（语料块带 sem_chunk_entities）→ auto_entities=True 时 query
  先 AC 识别再召回（识别钉 api/mcp 层——resolve_query_entities）；
- **AC+模糊 recall@3 ≥0.92** 一并断言（识别黄金集 180 条含 pos_typo 错别字
  正样本——TC-SEV-01 v1.9.8 注记兑现；fuzzy_recall_at_3）；
- 基线数字归档 benchmarks/report-m2s-6-sev03.md（灰度对比记录同报告）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from helpers import seed_org

ORG = "org:tax"
EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


def _load_seed():
    spec = importlib.util.spec_from_file_location(
        "eval_semantic_seed_s3", EVAL_DIR / "semantic_seed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_semantic_seed_s3"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def sev_env(backend, tmp_path):
    """检索增益栈：参考词典 + build（FakeEmbedder 向量面）+ 语料摄取
    （tagger 注入——块级实体打标）+ TokenBag 向量（docs 评测口径）。"""
    from types import SimpleNamespace

    from fake_providers import FakeEmbedder, TokenBagEmbedder
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.docs.quality import QualityService
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.tagging import make_ingest_tagger
    from knowledge_lattice.eval.harness import load_corpus, load_golden

    seed = _load_seed()
    seed_org(backend, ORG)
    # docs 面（语料摄取上传校验前提）：dataset + 维度 + u_full 授权
    from helpers import (
        dim_id_for,
        seed_dataset,
        seed_dimension,
        seed_dim_value,
        seed_grant,
        seed_membership,
        seed_user,
        val_id_for,
    )

    seed_dataset(backend, ORG, "ds:vat_lib")
    seed_dataset(backend, ORG, "ds:expense_lib")
    seed_dimension(backend, ORG, "region")
    seed_dim_value(backend, dim_id_for(ORG, "region"), "CN")
    seed_dim_value(backend, dim_id_for(ORG, "region"), "OS")
    seed_dimension(backend, ORG, "tax_type")
    backend.execute(
        "UPDATE dimensions SET required = 0 WHERE org_id = ? AND key = ?",
        (ORG, "tax_type"))
    seed_dim_value(backend, dim_id_for(ORG, "tax_type"), "VAT")
    seed_user(backend, "u_full")
    seed_membership(backend, "u_full", ORG)
    for v in ("CN", "OS"):
        seed_grant(backend, user_id="u_full",
                   dim_id=dim_id_for(ORG, "region"),
                   val_id=val_id_for(ORG, "region", v))
    seed_grant(backend, user_id="u_full",
               dim_id=dim_id_for(ORG, "tax_type"),
               val_id=val_id_for(ORG, "tax_type", "VAT"))
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=32,
                        embed_model="tokbag-embed")
    b = backend.make_backend()
    seed.seed_reference_org(b, ORG, settings, repo_dir=tmp_path / "yamlrepo")
    clear_annotator_cache()
    build_embedder = FakeEmbedder(dim=32, model_name="tokbag-embed")
    assert run_build(b, ORG, settings=settings,
                     embedder=build_embedder)["status"] == "ready"

    gate = EmbeddingGate()
    quality = QualityService(b, settings)
    service = IngestService(
        b, build_embedder, settings, gate, tmp_path / "objects",
        quality=quality, tagger=make_ingest_tagger(b, settings),
    )
    corpus = load_corpus(EVAL_DIR / "corpus.jsonl")
    golden = load_golden(EVAL_DIR / "golden.jsonl")
    # 语料批量上线（真实摄取链——tag 同事务）
    from knowledge_lattice.eval.harness import build_corpus

    corpus_ids = build_corpus(corpus, ingest_service=service,
                              owner_user_id="u_full", org_id=ORG)
    tag_rows = backend.execute(
        "SELECT count(*) FROM sem_chunk_entities WHERE org_id = ?", (ORG,)
    ).fetchone()[0]
    assert tag_rows > 0, "语料块应带实体打标（实体路前提）"
    return SimpleNamespace(db=backend, backend=b, settings=settings,
                           gate=gate, embedder=build_embedder,
                           service=service, corpus_ids=corpus_ids,
                           corpus=corpus, golden=golden)


def _run_queries(env, *, auto_entities: bool):
    """黄金集逐 query：auto_entities=True 走识别→展开→实体路三路；False 基线
    双路。返回 per_query [{qid, results:[(corpus_key, seq)]}]。"""
    from knowledge_lattice.core.docs.retrieve import search as run_search
    from knowledge_lattice.core.semantic.recall import resolve_query_entities

    key_of = {}
    for corpus_key, doc_id in env.corpus_ids.items():
        rows = env.backend.fetch_window(doc_id, version=1, seq_lo=0,
                                        seq_hi=100_000)
        for r in rows:
            key_of[r["chunk_id"]] = (corpus_key, r["seq"])
    per_query = []
    for case in env.golden:
        entity_ids = entity_seeds = None
        if auto_entities:
            ctx = resolve_query_entities(
                env.backend, env.settings, ORG, query=case.query,
                auto_entities=True)
            if ctx is not None:
                entity_ids, entity_seeds = ctx["entity_ids"], ctx["seeds"]
        result = run_search(
            env.backend, env.settings, user_id="u_full", org_id=ORG,
            query=case.query, top_k=10, gate=env.gate, embedder=env.embedder,
            entity_ids=entity_ids, entity_seeds=entity_seeds,
        )
        per_query.append({
            "qid": case.qid,
            "results": [key_of[r["chunk_id"]] for r in result["results"]
                        if r["chunk_id"] in key_of],
            "labels": list(case.labels),
        })
    return per_query


def _metrics(per_query):
    from knowledge_lattice.eval.metrics import mean_reciprocal_rank

    runs = [(p["results"], set(p["labels"])) for p in per_query]
    return {
        "recall@10": round(_mean_recall(runs, 10), 4),
        "mrr": round(mean_reciprocal_rank(runs), 4),
    }


def _mean_recall(runs, k: int) -> float:
    from knowledge_lattice.eval.metrics import recall_at_k

    if not runs:
        return 0.0
    return sum(recall_at_k(res, labels, k=k) for res, labels in runs) / len(runs)


def test_tc_sev_03_entity_route_no_regression(sev_env) -> None:
    """开/关实体路对比：recall@10 与 MRR 不回退（每指标 on >= off − 1e-9）
    ——不回退判定通过 → auto_entities 允许默认开启（默认值仍 False 的
    保守档断言 + 报告登记结论）。"""
    off = _metrics(_run_queries(sev_env, auto_entities=False))
    on = _metrics(_run_queries(sev_env, auto_entities=True))
    assert on["recall@10"] >= off["recall@10"] - 1e-9, (
        f"recall@10 回退：off={off} on={on}")
    assert on["mrr"] >= off["mrr"] - 1e-9, (
        f"MRR 回退：off={off} on={on}")
    # 数字归档核对（benchmarks/report-m2s-6-sev03.md——数字漂移即测试红；
    # 分后端核对：报告按后端分档记录〔pg 基线差异 G-6 已登记〕）
    report = Path(__file__).resolve().parent.parent / "benchmarks" / \
        "report-m2s-6-sev03.md"
    assert report.exists(), "评测报告须落 benchmarks/"
    text = report.read_text(encoding="utf-8")
    suffix = "" if sev_env.db.name == "sqlite" else "(pg)"
    assert f"off{suffix}: recall@10={off['recall@10']}, MRR={off['mrr']}" \
        in text, f"报告数字与实测不一致（off/{sev_env.db.name}）：{off}"
    assert f"on{suffix}: recall@10={on['recall@10']}, MRR={on['mrr']}" \
        in text, f"报告数字与实测不一致（on/{sev_env.db.name}）：{on}"


def test_tc_sev_03_auto_entities_default_off() -> None:
    """检索增益不回退判定通过后 auto_entities 允许默认开启——**默认值仍
    False**（保守档：显式参数形态；MCP/REST 契约 default=false）。"""
    from knowledge_lattice.api.search import SearchRequest

    req = SearchRequest(query="x")
    assert req.auto_entities is False
    assert req.entities is None


def test_tc_sev_03_ac_fuzzy_recall_at_3(sev_env) -> None:
    """AC+模糊 recall@3 ≥0.92（识别黄金集 180 条含 pos_typo——G-1 门槛；
    参考词典部署 → 适用面满足）。"""
    from knowledge_lattice.core.semantic.evalrun import (
        fuzzy_recall_at_3,
        load_golden,
    )
    from knowledge_lattice.core.semantic.annotator import get_annotator

    items = load_golden(EVAL_DIR / "semantic_golden.jsonl")
    ann, _rev = get_annotator(sev_env.backend, ORG, sev_env.settings)
    snapshot = sev_env.backend.sem_active_snapshot(ORG)

    def vec_lookup(fragment: str):
        from knowledge_lattice.core.semantic.fuzzy import pinyin_norm

        # 向量层确定性注入：fragment 拼音与某 term 拼音同音时回高 sim
        #（TokenBag 噪声向量不可靠——评测确定性口径同三层短路〔拼音层先行，
        # vec 层只接漏网〕；此注入等价于「近邻层可命中同音面」的保守形态）
        pin = pinyin_norm(fragment)
        best = None
        for t in ann.fuzzy_terms:
            if t["pinyin"] and t["pinyin"] == pin and t["text_norm"] != \
                    __import__("knowledge_lattice.core.semantic.norm",
                               fromlist=["normalize_alias"]).normalize_alias(
                        fragment):
                best = t
                break
        if best is None:
            return []
        return [{"entity_id": best["entity_id"], "sim": 0.9,
                 "text_norm": best["text_norm"]}]

    metrics = fuzzy_recall_at_3(ann, items, snapshot, vec_lookup=vec_lookup)
    assert "recall_at_3" in metrics, metrics
    assert metrics["recall_at_3"] >= 0.92, (
        f"AC+模糊 recall@3 未达 0.92：{metrics}")
