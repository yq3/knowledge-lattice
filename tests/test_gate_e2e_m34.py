"""m3-4 E-3 P3-10：A-1 probe gate 四接线点**端点级** e2e（m3-3 移交建议项）。

m3-3 交付的单测（tests/test_sem_g24_m33.py test_a1_*）在 core 层直调
search_entities/annotate——本文件补**端点级**：REST（/api/search 检索 +
/api/orgs/{org}/semantic/entities + …/annotate）与 MCP（search_entities/
annotate 工具）四接线点，探针拒绝档下：

1. **零嵌入调用**（计数 Embedder——查询侧向量路关闭不发 embed）；
2. 增益路失败不阻断（检索/识别照常返回——§5.2 跨切面一致）；
3. **probe_reject 审计端点可见**：GET /api/orgs/{org}/audit?action=search.degraded
   （org_admin）读到四接线点的 search.degraded 事件（reasons=[probe_reject]、
   语义两点带 scope=search_entities/annotate、docs 检索点无 scope——负载
   形态与 core 写入一致）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from conftest import ORG
from helpers import dim_id_for, seed_dataset, seed_dim_value, seed_dimension, seed_org
from test_mcp_semantic_tools import _call  # noqa: E401 —— MCP 调用形态复用

NOW = "2026-11-08 09:00:00"


class _CountingFakeEmbedder:
    """FakeEmbedder 计数包装（查询侧 embed 调用可见——协议面同 FakeEmbedder）。"""

    def __init__(self, dim: int = 8):
        from fake_providers import FakeEmbedder

        self._inner = FakeEmbedder(dim=dim, model_name="fake-embed")
        self.calls = 0

    @property
    def dim(self) -> int:
        return self._inner.dim

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    @property
    def model_label(self) -> str:
        return self._inner.model_label

    def embed(self, texts):
        self.calls += 1
        return self._inner.embed(texts)

    def embed_query(self, query: str):
        self.calls += 1
        return self._inner.embed_query(query)


@pytest.fixture()
def gate_env(backend, tmp_path):
    """REST+MCP 壳 + 语义图 ready 构建 + 可检索文档；**构建完成后**把 gate 置
    拒绝档（构建/摄取写路径需要嵌入——先构建后拒绝，端点调用期零嵌入断言窗口
    从拒绝后起算）。"""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.domain.auth import hash_token
    from fake_semantic import FakeSourceAdapter
    from helpers import seed_grant, seed_membership, seed_searchable_doc, seed_user, val_id_for

    seed_org(backend, ORG)
    seed_dataset(backend, ORG, "ds:vat_lib")
    seed_dimension(backend, ORG, "region")
    seed_dim_value(backend, dim_id_for(ORG, "region"), "CN")
    for uid in ("u_full", "admin_tax"):
        seed_user(backend, uid)
    seed_membership(backend, "u_full", ORG)
    seed_membership(backend, "admin_tax", ORG, role="org_admin")
    seed_grant(backend, user_id="u_full", dim_id=dim_id_for(ORG, "region"),
               val_id=val_id_for(ORG, "region", "CN"))
    seed_searchable_doc(backend, "d_cn", dims={"region": ["CN"]},
                        content_seg="留抵 退税 申请", owner_user_id="u_full")
    tokens = {"u_full": "dev-static-u-full", "admin_tax": "dev-static-admin-tax"}
    for uid, token in tokens.items():
        backend.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                        (hash_token(token), uid))
    backend.commit()

    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        probe_interval_s=0, worker_mode="inline")
    embedder = _CountingFakeEmbedder(dim=8)
    gate = EmbeddingGate()
    kwargs = dict(embedder=embedder, gate=gate, run_startup_probe=False)
    if backend.name == "pg":
        app = create_app(settings, backend=backend.make_backend(), **kwargs)
    else:
        app = create_app(settings, **kwargs)

    with TestClient(app) as client:
        service = client.app.state.service
        recs = [
            EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣"),
        ]
        run_sync(service.backend, ORG, FakeSourceAdapter("template_center", recs),
                 settings=settings, snapshot=list(recs), now=NOW)
        clear_annotator_cache()
        assert run_build(service.backend, ORG, settings=settings,
                         embedder=embedder)["status"] == "ready"
        baseline_calls = embedder.calls
        # 构建后置拒绝档（端点调用窗口内零嵌入是断言对象）
        from knowledge_lattice.adapters.embedder import ProbeResult

        gate.update(ProbeResult(status="reject", min_cosine=None))
        yield SimpleNamespace(
            client=client, app=app, db=backend, embedder=embedder, gate=gate,
            tokens=tokens, baseline_calls=baseline_calls,
        )


def _degraded_events(env) -> list[dict]:
    """审计端点读取 search.degraded 事件（org_admin 面TC-OPS-03）。"""
    r = env.client.get(
        f"/api/orgs/{ORG}/audit",
        params={"action": "search.degraded"},
        headers={"Authorization": f"Bearer {env.tokens['admin_tax']}"},
    )
    assert r.status_code == 200
    return r.json()["events"]


def test_p3_10_rest_search_probe_reject_notice_and_no_embed(gate_env) -> None:
    """①REST /api/search：拒绝档 → notice.degraded 含 probe_reject、结果照常
    返回（BM25 路）、零嵌入、审计事件落库（无 scope——docs 检索负载形态）。"""
    env = gate_env
    r = env.client.post(
        "/api/search", json={"query": "留抵退税", "top_k": 5},
        headers={"Authorization": f"Bearer {env.tokens['u_full']}",
                 "x-org-id": ORG},
    )
    assert r.status_code == 200
    body = r.json()
    assert "probe_reject" in body["notice"]["degraded"], "拒绝档须标注降级（不 500）"
    assert body["results"], "BM25 路照常返回（增益路失败不阻断）"
    assert env.embedder.calls == env.baseline_calls, "查询侧向量路关闭——零嵌入调用"

    events = _degraded_events(env)
    assert events, "probe_reject 降级审计须端点可见"
    payload = json.loads(events[0]["detail_json"])
    assert payload["reasons"] == ["probe_reject"]
    assert "scope" not in payload, "docs 检索降级负载无 scope（m3-3 core 写入口径）"


def test_p3_10_rest_semantic_search_entities_probe_reject(gate_env) -> None:
    """②REST GET …/semantic/entities：拒绝档 → 实体照常返回（前三档）+ 零嵌入
    + scope=search_entities 的 probe_reject 审计。"""
    env = gate_env
    r = env.client.get(
        f"/api/orgs/{ORG}/semantic/entities",
        params={"q": "进项"},
        headers={"Authorization": f"Bearer {env.tokens['u_full']}"},
    )
    assert r.status_code == 200
    assert r.json()["entities"], "vec 档关闭前三档照常（增益路语义不变）"
    assert env.embedder.calls == env.baseline_calls, "vec 档不得发起嵌入调用"

    payloads = [json.loads(e["detail_json"]) for e in _degraded_events(env)]
    scoped = [p for p in payloads if p.get("scope") == "search_entities"]
    assert scoped and scoped[0]["reasons"] == ["probe_reject"]


def test_p3_10_rest_annotate_probe_reject(gate_env) -> None:
    """③REST POST …/semantic/annotate（fuzzy=true）：拒绝档 → AC 层识别照常 +
    零嵌入 + scope=annotate 的 probe_reject 审计。"""
    env = gate_env
    r = env.client.post(
        f"/api/orgs/{ORG}/semantic/annotate",
        json={"text": "进项税额抵扣的票据整理", "fuzzy": True},
        headers={"Authorization": f"Bearer {env.tokens['u_full']}"},
    )
    assert r.status_code == 200
    assert r.json()["mentions"], "AC 层识别不受 gate 影响（不 500）"
    assert env.embedder.calls == env.baseline_calls, "fuzzy vec 层不得发起嵌入调用"

    payloads = [json.loads(e["detail_json"]) for e in _degraded_events(env)]
    scoped = [p for p in payloads if p.get("scope") == "annotate"]
    assert scoped and scoped[0]["reasons"] == ["probe_reject"]


def test_p3_10_mcp_semantic_tools_probe_reject(gate_env) -> None:
    """④MCP search_entities / annotate：拒绝档 → 两工具照常返回（前三档/AC）+
    零嵌入 + 两 scope 的 probe_reject 审计（MCP 与 REST 同接线）。"""
    from knowledge_lattice.domain.auth import issue_dev_jwt

    env = gate_env
    token = issue_dev_jwt(env.app.state.service.settings, user_id="u_full", org=ORG)

    out = _call(env.app, token, "search_entities", {"q": "进项", "top_k": 5})
    assert out["entities"], "MCP search_entities 前三档照常"
    ann = _call(env.app, token, "annotate", {"text": "进项税额抵扣的票据", "fuzzy": True})
    assert ann["mentions"], "MCP annotate AC 层照常"
    assert env.embedder.calls == env.baseline_calls, "两工具 fuzzy/vec 层零嵌入调用"

    payloads = [json.loads(e["detail_json"]) for e in _degraded_events(env)]
    scopes = {p.get("scope") for p in payloads if p.get("scope")}
    assert {"search_entities", "annotate"} <= scopes, (
        f"MCP 两接线点的 probe_reject 审计须端点可见：{sorted(scopes)}"
    )
