"""M1-2 承接遗留清偿组【单测｜R3】。

- **P2-新 半开探测令牌泄漏**（m1-1 committer）：「探针拒绝 + 熔断半开」叠加时
  `_breaker_allows` 在探针 gate 判断之前被调用——半开探测令牌被消耗但无
  success/failure 回写，`_probing` 永不复位（向量路不自愈需重启 + 每请求误写
  search.degraded）。修法=allow 调用移入「确实会发起调用」分支（embedder 非空
  且 gate 未拒绝才探测）；rerank 侧同款（none 档/无 reranker 不消耗令牌）。
  本文件**缺陷态注入必红**：若 allow 回到无条件调用，用例即失败。
- **PG 臂 malformed-grant 回归**（m0b-1 移交）：read_grants 维度归属校验
  （v.dimension_id = dim.id）PG 侧无用例——双后端参数化补齐。
"""

from __future__ import annotations

import pytest

from helpers import NOW_TS, dim_id_for, val_id_for

ORG = "org:tax"


def _half_open_breaker():
    """构造半开态熔断器：3 失败断开 → 注入时钟推进 cooldown（state=half_open）。"""
    from knowledge_lattice.adapters.breaker import CircuitBreaker

    breaker = CircuitBreaker(failures=3, cooldown_s=60.0)
    t0 = 1000.0
    for _ in range(3):
        breaker.record_failure(now=t0)
    assert breaker.state(now=t0) == "open"
    assert breaker.state(now=t0 + 61.0) == "half_open"
    return breaker


def _reject_gate():
    """探针拒绝态 gate（TC-EMB-03② 同款——向量路同步关闭）。"""
    from knowledge_lattice.adapters.embedder import EmbeddingGate, ProbeResult

    gate = EmbeddingGate()
    gate.update(ProbeResult(status="reject", min_cosine=0.1))
    assert gate.rejected
    return gate


# ============ P2-新：半开探测令牌不因「探针拒绝」叠加而泄漏 ============


def test_p2new_probe_reject_plus_halfopen_token_not_consumed(ret_stack) -> None:
    """叠加场景（embed 侧）：熔断半开 + 探针拒绝同时成立 → search 不消耗探测
    令牌（向量路因 gate 关闭本就不发调用）——下一次请求仍可放行半开探测。

    缺陷态（修前）：`_breaker_allows` 无条件调用消耗令牌（_probing=True 且无
    回写）→ 本用例第二次 search 时 allow()=False、向量路永久半开锁死。
    """
    from knowledge_lattice.core.docs.retrieve import search

    breaker = _half_open_breaker()
    gate = _reject_gate()

    for _ in range(2):  # 两次叠加请求——修前第二次已因令牌泄漏而向量路锁死
        payload = search(
            ret_stack["backend"],
            ret_stack["settings"],
            user_id="u_full",
            org_id=ORG,
            query="common sample",
            top_k=5,
            gate=gate,
            embedder=ret_stack["embedder"],
            breakers={"embed": breaker},
        )
        assert "probe_reject" in payload["notice"]["degraded"], "探针拒绝档标注"

    # 令牌未泄漏断言：半开探测仍可放行（allow()=True——修前为 False）
    assert breaker.allow(now=1061.0) is True, (
        "半开探测令牌被「探针拒绝」叠加请求消耗（P2-新）——"
        "allow 应移入「确实会发起调用」分支"
    )


def test_p2new_embedder_none_does_not_touch_embed_breaker(ret_stack) -> None:
    """embedder=None（向量路配置态关闭）不消耗熔断探测令牌——无调用即无探测。"""
    from knowledge_lattice.core.docs.retrieve import search

    breaker = _half_open_breaker()
    payload = search(
        ret_stack["backend"],
        ret_stack["settings"],
        user_id="u_full",
        org_id=ORG,
        query="common sample",
        top_k=5,
        gate=None,
        embedder=None,
        breakers={"embed": breaker},
    )
    assert payload["notice"]["degraded"] == [], "无 embedder=配置态非降级"
    assert breaker.allow(now=1061.0) is True, "none 配置态不得消耗半开探测令牌"


def test_p2new_rerank_none_does_not_touch_rerank_breaker(ret_stack) -> None:
    """rerank 侧同款：reranker=None / none 档不消耗 rerank 熔断探测令牌
    （m1-1 注：none 档「不可达」——但令牌守恒语义相同）。"""
    from knowledge_lattice.core.docs.retrieve import search

    breaker = _half_open_breaker()
    search(
        ret_stack["backend"],
        ret_stack["settings"],
        user_id="u_full",
        org_id=ORG,
        query="common sample",
        top_k=5,
        gate=None,
        embedder=ret_stack["embedder"],
        reranker=None,  # none 档
        breakers={"embed": _half_open_breaker(), "rerank": breaker},
    )
    assert breaker.allow(now=1061.0) is True, "none 档不得消耗 rerank 半开探测令牌"


# ============ 遗留 #6：PG 臂 malformed-grant 回归（read_grants 维度归属） ============


def test_malformed_grant_not_counted_in_any_dimension(matrix) -> None:
    """畸形授权行（FK 合法、dimension/value 归属不匹配——region 维度挂 tax_type
    的 VAT 取值）不计入任何维度（v.dimension_id = dim.id JOIN 校验，m0a-2 P2-1
    读侧收口）——sqlite 形态在 test_r2_review_fixes，本用例补 PG 臂（双后端实跑）。"""
    matrix.execute(
        "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id)"
        " VALUES('u_full', ?, ?)",
        (dim_id_for(ORG, "region"), val_id_for(ORG, "tax_type", "VAT")),
    )
    backend = matrix.make_backend()
    grants = backend.read_grants("u_full", ORG, now=NOW_TS)
    assert grants["region"] == ("CN", "OS"), "畸形行不计入 region"
    assert grants["tax_type"] == ("VAT",), "也不计入 tax_type"

    # 行为面：可见集不变（无跨维度取值越权放宽）
    plan = matrix.compile_acl("u_full", ORG, now=NOW_TS)
    rows = sorted(matrix.execute(*matrix.render_select(plan)))
    assert {r[2] for r in rows} == {"d_cn", "d_multi", "d_empty_region", "d_os"}
