"""TC-E2E-04 维度变更即时生效【集成｜M1——检索侧断言，双后端参数化】。

- 撤掉用户 OS 授权（或收紧文档维度）后**下一次查询即不可见**（查询时实时展开
  ——D6；无缓存/物化可见集）；
- v1.6 口径：dims_json 投影已删——文档维度变更直接写 `document_dimensions`，
  检索输出 dims 经 store 聚合回填（语义保持，UPDATE 不重嵌）；
- 多值维度其余取值不受影响（部分收紧只影响部分可见性）。
"""

from __future__ import annotations

from helpers import NOW_TS


def _search(ret_stack, user_id="u_full", query="采样词"):
    from knowledge_lattice.core.docs.retrieve import search

    return search(
        ret_stack["backend"], ret_stack["settings"],
        user_id=user_id, org_id="org:tax", query=query, top_k=10,
        embedder=ret_stack["embedder"], reranker=None, enhancer=None,
    )


def test_e2e_04_grant_revocation_immediate(ret_stack) -> None:
    """撤掉 u_full 的 OS 授权 → 下一次查询 d_os 即不可见（D6 实时展开）。"""
    db = ret_stack["db"]
    # 基线：u_full（region=[CN,OS]）可见 d_os（矩阵自带，content_seg="common sample"）
    resp = _search(ret_stack, query="common")
    assert "d_os" in {r["doc_id"] for r in resp["results"]}, "基线：授权内可见"

    # 撤销 OS 授权（DELETE 授权行——grant 维度取值级撤销）
    db.execute(
        "DELETE FROM user_dimension_grants"
        " WHERE user_id = 'u_full' AND value_id = ?",
        ("val:dim:org:tax:region:OS",),
    )
    resp2 = _search(ret_stack, query="common")
    assert "d_os" not in {r["doc_id"] for r in resp2["results"]}, (
        "撤销后下一次查询即不可见（查询时实时展开——D6，无缓存可见集）"
    )
    # 其余授权不受影响：d_cn/d_multi（含 CN）仍可见
    assert {"d_cn", "d_multi"} <= {r["doc_id"] for r in resp2["results"]}


def test_e2e_04_doc_dims_tighten_immediate(ret_stack) -> None:
    """文档维度收紧（直接写 document_dimensions——v1.6 口径）：下一次查询不可见。"""
    db = ret_stack["db"]
    # 基线：u_os（region=[OS]）可见 d_multi（region=[CN,OS]——多值命中）
    resp = _search(ret_stack, user_id="u_os", query="common")
    assert "d_multi" in {r["doc_id"] for r in resp["results"]}

    # 收紧：删除 d_multi 的 OS 维度行（PATCH document_dimensions 同源语义）
    db.execute(
        "DELETE FROM document_dimensions"
        " WHERE doc_id = 'd_multi' AND value_id = ?",
        ("val:dim:org:tax:region:OS",),
    )
    resp2 = _search(ret_stack, user_id="u_os", query="common")
    assert "d_multi" not in {r["doc_id"] for r in resp2["results"]}, (
        "维度收紧后立即不可见——d_multi 只剩 CN 行，对 u_os（仅 OS）不命中"
    )
    # 多值其余值不受影响：u_cn（region=[CN]）仍可见 d_multi
    resp3 = _search(ret_stack, user_id="u_cn", query="common")
    assert "d_multi" in {r["doc_id"] for r in resp3["results"]}, (
        "部分收紧不影响其他取值授权用户的可见性"
    )
    # dims 聚合回填随 document_dimensions 变化（输出面 v1.6 口径）
    top = next(r for r in resp3["results"] if r["doc_id"] == "d_multi")
    assert top["dims"] == {"region": ["CN"]}, "dims 经 store 聚合回填反映收紧后的真源"


def test_e2e_04_membership_expiry_immediate(ret_stack) -> None:
    """成员关系过期造数（PAST_TS——时间不推进系统时钟）：下一次查询整体拒绝。"""
    from knowledge_lattice.core.docs.acl import AclDeniedError
    import pytest

    db = ret_stack["db"]
    db.execute(
        "UPDATE user_org_memberships SET expires_at = ? WHERE user_id = 'u_full'",
        ("2020-01-01 00:00:00",),
    )
    with pytest.raises(AclDeniedError):
        _search(ret_stack)  # 第 0 步成员校验拒绝（403 语义）


def test_e2e_04_compile_now_snapshot(ret_stack) -> None:
    """:now 造数锚点真断言（P3-7——原空转测试改实断言）：编译期过期判定按
    :now 快照——同一过期授权行，锚点在过期前=仍有效（进 grants）、锚点在
    过期后=已失效（不进 grants）；DB 时钟无关（纯 :now 参数化语义）。
    载体=tax_type 补授临时 CIT（既有 VAT 无过期——不干扰收紧断言）。"""
    from helpers import FUTURE_TS, grant_by_key

    db = ret_stack["db"]
    grant_by_key(
        db, "u_full", org_id="org:tax", key="tax_type", value="CIT",
        expires_at="2026-12-31 00:00:00",  # 晚于 NOW_TS(2026-06-01)、早于 FUTURE_TS
    )
    # 锚点 NOW_TS（2026-06-01）：临时授权未过期 → 进 grants（tax_type 两值）
    plan_now = db.compile_acl("u_full", "org:tax", now=NOW_TS)
    tax_rule = next(r for r in plan_now.dimension_rules if r.key == "tax_type")
    assert set(tax_rule.grants) == {"VAT", "CIT"}
    # 锚点 FUTURE_TS（2099）：临时授权已过期 → 收紧为仅 VAT（过期即失效，不等清理）
    plan_future = db.compile_acl("u_full", "org:tax", now=FUTURE_TS)
    tax_rule_f = next(r for r in plan_future.dimension_rules if r.key == "tax_type")
    assert set(tax_rule_f.grants) == {"VAT"}, "编译期 :now 快照——过期授权不进规则集（T1）"
