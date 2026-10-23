"""范围 2 契约：StorageBackend 协议（按域组合）+ AclPlan 结构化产物类型 +
嵌入/重排 provider 接口（D12/D24——M0a-1 只定义协议与数据结构，编译器/渲染器属 M0a-2）。
"""

from __future__ import annotations

import dataclasses

import pytest


def test_acl_plan_structure() -> None:
    from knowledge_lattice.store.backend import AclDimensionRule, AclPlan

    empty = AclDimensionRule(key="tax_type", grants=())
    full = AclDimensionRule(key="region", grants=("CN", "OS"))
    assert empty.is_empty  # 空授权集 → 渲染为 NOT EXISTS 单条件（无 `IN ()`——Plan 层不变式）
    assert not full.is_empty
    assert full.grants == ("CN", "OS")

    plan = AclPlan(
        org_id="org:tax",
        dimension_rules=(empty, full),
        dataset_ids=("ds:vat",),
        embed_model="qwen3-embedding-4b:2560",
    )
    assert plan.org_id == "org:tax"
    assert plan.dataset_ids == ("ds:vat",)
    assert plan.doc_ids is None  # None = 不过滤
    assert plan.embed_model == "qwen3-embedding-4b:2560"
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.org_id = "org:gl"  # type: ignore[misc]


def test_storage_backend_composed_of_domain_protocols() -> None:
    from knowledge_lattice.store.backend import (
        AdminBackend,
        AclBackend,
        AuditBackend,
        IngestBackend,
        SearchBackend,
        SemanticBackend,
        StorageBackend,
    )

    for domain in (SearchBackend, IngestBackend, AclBackend, AdminBackend, SemanticBackend, AuditBackend):
        assert issubclass(StorageBackend, domain)
    # 方法种子存在（清单非穷举——design §3 store/backend.py）
    for method in ("recall_fts", "recall_vec", "insert", "read_membership", "read_grants"):
        assert hasattr(StorageBackend, method)


def test_embedder_protocol_shape() -> None:
    from knowledge_lattice.adapters.embedder import Embedder

    class FakeEmbedder:
        def embed(self, texts):  # pragma: no cover - 形态测试
            return [[0.0] for _ in texts]

        @property
        def model_label(self) -> str:  # pragma: no cover - 形态测试
            return "fake:8"

    assert isinstance(FakeEmbedder(), Embedder)


def test_noop_reranker_preserves_input_order() -> None:
    from knowledge_lattice.adapters.reranker import NoopReranker

    out = NoopReranker().rerank("query", ["a", "b", "c"])
    assert [r.index for r in out] == [0, 1, 2]  # none 实现＝跳过重排：保序返回（RRF 序即最终序）
    assert all(0.0 <= r.relevance_score <= 1.0 for r in out)


def test_reranker_protocol_shape() -> None:
    from knowledge_lattice.adapters.reranker import NoopReranker, Reranker

    assert isinstance(NoopReranker(), Reranker)
