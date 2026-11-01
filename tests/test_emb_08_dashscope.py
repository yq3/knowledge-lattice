"""m2-5 A7：DashScope rerank provider（G-7「接口不变按形态实现对应 provider」
既定口径——百炼 rerank 为 DashScope 原生 text-rerank 服务，与 Cohere 风格
/rerank 契约不同）+ P3-14 rerank env 覆盖激活（m1-1 登记——Settings 字段在、
env 键缺；验收口径=供应商切换仅经 LATTICE_* env 零代码改动）。

联调（真实网关 gte-rerank-v2）不入门禁——网络依赖用例归
benchmarks/rerank_dashscope_live.py（skip-if-no-key 同等 fail-safe 口径的
脚本形态）；本文件全部离线（httpx.MockTransport）。
"""

from __future__ import annotations

import json

import httpx
import pytest


# ============ DashScopeReranker（离线 MockTransport） ============


def _settings(**kw):
    from knowledge_lattice.config import Settings

    base = dict(
        environment="test",
        reranker="dashscope",
        rerank_api_base="https://dashscope.example/api/v1",
        rerank_api_key="sk-test",
        rerank_model="gte-rerank-v2",
        rerank_timeout_s=1.0,
    )
    base.update(kw)
    return Settings(**base)


def _make(settings, handler):
    import httpx

    from knowledge_lattice.adapters.reranker import DashScopeReranker

    return DashScopeReranker(settings, transport=httpx.MockTransport(handler))


def test_dashscope_request_shape_and_response_mapping() -> None:
    """请求体嵌套 input.{query,documents} + 端点路径 /services/rerank/
    text-rerank/text-rerank；响应 output.results[{index,relevance_score}]
    映射为 RankedDocument（与百炼实测探测形态逐字段一致——A7①联调结论）。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "output": {"results": [
                {"index": 2, "relevance_score": 0.98},
                {"index": 0, "relevance_score": 0.31},
            ]},
            "usage": {"total_tokens": 100},
        })

    rr = _make(_settings(), handler)
    out = rr.rerank("增值税 申报", ["甲", "乙", "丙"], top_n=2)
    assert [r.index for r in out] == [2, 0]
    assert out[0].relevance_score == pytest.approx(0.98)
    # 请求形态（DashScope 原生——与 Cohere 平铺 documents 不同）
    assert captured["url"].endswith(
        "/services/rerank/text-rerank/text-rerank"
    ), "百炼原生 text-rerank 服务端点"
    assert captured["auth"] == "Bearer sk-test"
    assert captured["body"]["model"] == "gte-rerank-v2"
    assert captured["body"]["input"] == {
        "query": "增值税 申报", "documents": ["甲", "乙", "丙"]}
    assert captured["body"]["top_n"] == 2


def test_dashscope_top_n_omitted_when_none() -> None:
    """top_n 缺省不携带（None 语义——服务端默认全量返回）。"""
    captured: dict = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"output": {"results": []}})

    rr = _make(_settings(), handler)
    rr.rerank("q", ["a"])
    assert "top_n" not in captured["body"]


def test_dashscope_malformed_items_dropped() -> None:
    """响应缺 index/relevance_score 的项防御性丢弃（TC-ACL-08 响应注入面——
    与 CohereCompatReranker 同款口径，空响应交调用方降级判定）。"""
    def handler(request):
        return httpx.Response(200, json={"output": {"results": [
            {"index": 1, "relevance_score": 0.5},
            {"index": "x", "relevance_score": 0.4},   # 非法 index → 丢弃
            {"relevance_score": 0.3},                  # 缺 index → 丢弃
            {"index": 0},                              # 缺分 → 丢弃
        ]}})

    rr = _make(_settings(), handler)
    out = rr.rerank("q", ["a", "b"])
    assert [(r.index, r.relevance_score) for r in out] == [(1, 0.5)]


def test_dashscope_error_raises_not_swallowed() -> None:
    """网络失败/HTTP 错误原样 raise——本实现不吞异常（降级归调用方
    retrieve，与 Cohere 实现同款契约）。"""
    def handler(request):
        return httpx.Response(503, json={"code": "ServiceUnavailable"})

    rr = _make(_settings(), handler)
    with pytest.raises(httpx.HTTPStatusError):
        rr.rerank("q", ["a"])

    rr2 = _make(_settings(), lambda req: (_ for _ in ()).throw(
        httpx.ConnectError("unreachable")))
    with pytest.raises(httpx.ConnectError):
        rr2.rerank("q", ["a"])


def test_create_app_assembles_dashscope_provider(tmp_path) -> None:
    """LATTICE_RERANKER=dashscope 档位 → create_app 装配 DashScopeReranker
    （provider 档位选择零代码——仅配置切换）。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.adapters.reranker import DashScopeReranker
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from fake_providers import FakeEmbedder

    app = create_app(
        _settings(environment="test", data_dir=tmp_path, worker_mode="inline"),
        embedder=FakeEmbedder(dim=8), gate=EmbeddingGate(),
        run_startup_probe=False,
    )
    assert isinstance(app.state.service.reranker, DashScopeReranker)


def test_create_app_reranker_unknown_fails_closed(tmp_path) -> None:
    """未知 reranker 档位 fail-closed（不静默回退 none——配置错误应即刻暴露）。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from fake_providers import FakeEmbedder

    with pytest.raises(ValueError, match="reranker"):
        create_app(
            _settings(environment="test", data_dir=tmp_path,
                      worker_mode="inline", reranker="bogus-vendor"),
            embedder=FakeEmbedder(dim=8), gate=EmbeddingGate(),
            run_startup_probe=False,
        )


# ============ P3-14：rerank env 覆盖激活（Settings 字段在、env 键缺） ============


@pytest.mark.parametrize(
    "env_key,field,default",
    [
        ("LATTICE_RERANK_API_BASE", "rerank_api_base",
         "http://127.0.0.1:11434/v1"),
        ("LATTICE_RERANK_API_KEY", "rerank_api_key", "local-dev"),
        ("LATTICE_RERANK_MODEL", "rerank_model", "qwen3-reranker-8b"),
        ("LATTICE_RERANK_TRUNCATE_TOKENS", "rerank_truncate_tokens", None),
    ],
)
def test_rerank_env_overrides(monkeypatch, env_key, field, default) -> None:
    """LATTICE_RERANK_API_BASE/API_KEY/MODEL/TRUNCATE_TOKENS env 覆盖生效
    ——P3-14 激活（供应商切换仅经 env、零代码改动）。"""
    from knowledge_lattice.config import get_settings

    monkeypatch.setenv(env_key, "2048" if "TOKENS" in env_key else "https://ov.example")
    s = get_settings()
    expected = 2048 if "TOKENS" in env_key else "https://ov.example"
    assert getattr(s, field) == expected

    monkeypatch.delenv(env_key, raising=False)
    s2 = get_settings()
    assert getattr(s2, field) == default


def test_rerank_env_end_to_end_switch(monkeypatch, tmp_path) -> None:
    """端到端换供应商：四个 env + LATTICE_RERANKER=dashscope → get_settings
    → create_app 全链 DashScope 配置（零代码切换验收口径的最小闭环）。"""
    from knowledge_lattice.app import create_app
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.adapters.reranker import DashScopeReranker
    from knowledge_lattice.config import get_settings

    monkeypatch.setenv("LATTICE_RERANKER", "dashscope")
    monkeypatch.setenv("LATTICE_RERANK_API_BASE", "https://dashscope.aliyuncs.com/api/v1")
    monkeypatch.setenv("LATTICE_RERANK_API_KEY", "sk-from-env")
    monkeypatch.setenv("LATTICE_RERANK_MODEL", "gte-rerank-v2")
    monkeypatch.setenv("LATTICE_RERANK_TRUNCATE_TOKENS", "256")
    settings = get_settings()
    assert settings.rerank_truncate_tokens == 256

    import dataclasses

    settings = dataclasses.replace(
        settings, environment="test", data_dir=tmp_path, worker_mode="inline")
    from fake_providers import FakeEmbedder

    app = create_app(settings, embedder=FakeEmbedder(dim=8),
                     gate=EmbeddingGate(), run_startup_probe=False)
    rr = app.state.service.reranker
    assert isinstance(rr, DashScopeReranker)
    assert rr._settings.rerank_api_base == "https://dashscope.aliyuncs.com/api/v1"
    assert rr._settings.rerank_model == "gte-rerank-v2"
