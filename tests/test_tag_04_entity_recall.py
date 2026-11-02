"""m2s-6 实体召回路 store/core 面（TC-TAG-04 / TC-TAG-05 + TC-ACL-06 扩展——
design §5.10；双后端参数化）。

- TC-TAG-04 expand 召回关系集：ENTITY_RECALL_RELS 白名单（refers_to/
  has_field/maps_to/related_to）、**不沿 uses**、结果 ≤50、1 跳；
- TC-TAG-05 实体路 SQL：得分 = Σhits×（种子 1.0 / 扩展 0.5）、k_entity
  默认 30、matched_entities、三路 RRF 融合进 rerank（§5.10 顺序不变——
  ACL 兜底断言在前）；
- TC-ACL-06 扩展（任务书 A1）：实体路渲染 SQL 与基础/向量路共用同一
  visible_docs CTE 文本（双方言归一化参数记号后逐字相同）。
"""

from __future__ import annotations

import pytest

from helpers import (
    dim_id_for,
    seed_dataset,
    seed_dimension,
    seed_dim_value,
    seed_grant,
    seed_membership,
    seed_org,
    seed_searchable_doc,
    seed_user,
    val_id_for,
)

ORG = "org:tax"
NOW = "2026-11-01 09:00:00"


@pytest.fixture()
def recall_env(backend, tmp_path):
    """实体召回栈：维度 ACL 造数（region CN/OS）+ 语义图（种子→refers_to 扩展
    + uses 高扇出场景）+ build 就位 + 两块打标（种子命中/扩展命中）。"""
    from types import SimpleNamespace

    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord
    from knowledge_lattice.core.semantic.sync import run_sync

    seed_org(backend, ORG)
    seed_dataset(backend, ORG, "ds:vat_lib")
    seed_dimension(backend, ORG, "region")
    seed_dim_value(backend, dim_id_for(ORG, "region"), "CN")
    seed_dim_value(backend, dim_id_for(ORG, "region"), "OS")
    for uid in ("u_cn", "u_os", "u_owner"):
        seed_user(backend, uid)
        seed_membership(backend, uid, ORG)
    seed_grant(backend, user_id="u_cn", dim_id=dim_id_for(ORG, "region"),
               val_id=val_id_for(ORG, "region", "CN"))
    seed_grant(backend, user_id="u_os", dim_id=dim_id_for(ORG, "region"),
               val_id=val_id_for(ORG, "region", "OS"))
    # 语料：CN 可见 / OS 不可见（T-S8 面复用）
    seed_searchable_doc(backend, "d_cn", dims={"region": ["CN"]},
                        content_seg="进项 税额 抵扣 范围 凭证")
    seed_searchable_doc(backend, "d_os", dims={"region": ["OS"]},
                        content_seg="海外 进项 税额 抵扣 口径")

    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    b = backend.make_backend()
    recs = [
        EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣"),
        EntityRecord(type="template", key="TPL_VAT_INPUT", name="进项发票采集模板"),
        EntityRecord(type="template_field", key="TPL_VAT_INPUT.TAX_AMT",
                     name="票面税额"),
        EntityRecord(type="scenario", key="SCN_MONTHLY", name="月度申报"),
        EntityRecord(type="template", key="TPL_FILING", name="申报主表模板"),
        RelationRecord(src=("concept", "vat.input_credit"), rel_type="refers_to",
                       dst=("template", "TPL_VAT_INPUT")),
        RelationRecord(src=("template", "TPL_VAT_INPUT"), rel_type="has_field",
                       dst=("template_field", "TPL_VAT_INPUT.TAX_AMT")),
        RelationRecord(src=("scenario", "SCN_MONTHLY"), rel_type="uses",
                       dst=("template", "TPL_FILING")),   # uses——不应被召回展开
    ]
    run_sync(b, ORG, FakeSourceAdapter("template_center", recs),
             settings=settings, snapshot=list(recs), now=NOW)
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache

    clear_annotator_cache()
    assert run_build(b, ORG, settings=settings)["status"] == "ready"

    def _eid(key: str) -> int:
        return backend.execute(
            "SELECT id FROM sem_entities WHERE org_id = ? AND key = ?",
            (ORG, key)).fetchone()[0]

    ids = {k: _eid(k) for k in
           ("vat.input_credit", "TPL_VAT_INPUT", "TPL_VAT_INPUT.TAX_AMT",
            "TPL_FILING", "SCN_MONTHLY")}
    # 打标：d_cn 块命中种子（hits=2）；d_os 块命中扩展字段（hits=1）
    for dd, eid, hits in (("d_cn", ids["vat.input_credit"], 2),
                          ("d_os", ids["TPL_VAT_INPUT.TAX_AMT"], 1)):
        rid = backend.execute(
            "SELECT rid FROM chunks WHERE doc_id = ? AND version = 1",
            (dd,)).fetchone()[0]
        backend.execute(
            "INSERT INTO sem_chunk_entities(org_id, chunk_rid, doc_id, version,"
            " entity_id, hits, dict_rev) VALUES (?, ?, ?, 1, ?, ?, 'r1')",
            (ORG, rid, dd, eid, hits))
    return SimpleNamespace(db=backend, backend=b, settings=settings, ids=ids)


# ---- TC-TAG-04 expand 召回关系集 ----


def test_tc_tag_04_expand_rels_no_uses(recall_env) -> None:
    """召回展开只沿低扇出白名单（refers_to/has_field/maps_to/related_to）——
    uses 场景→模板不出现在扩展集；1 跳。"""
    from knowledge_lattice.core.semantic.constants import ENTITY_RECALL_RELS
    from knowledge_lattice.core.semantic.recall import resolve_query_entities

    out = resolve_query_entities(
        recall_env.backend, recall_env.settings, ORG,
        entities=[recall_env.ids["vat.input_credit"]])
    assert out is not None
    # 种子 + refers_to 扩展（TPL_VAT_INPUT）；uses 面的 TPL_FILING 不出现
    assert recall_env.ids["vat.input_credit"] in out["entity_ids"]
    assert recall_env.ids["TPL_VAT_INPUT"] in out["entity_ids"]
    assert recall_env.ids["TPL_FILING"] not in out["entity_ids"]
    assert recall_env.ids["SCN_MONTHLY"] not in out["entity_ids"]
    # 关系集白名单常量（design §5.10——不含 uses）
    assert set(ENTITY_RECALL_RELS) == {"refers_to", "has_field", "maps_to",
                                       "related_to"}


def test_tc_tag_04_expand_cap_50(recall_env) -> None:
    """展开结果 ≤50（ENTITY_RECALL_MAX_ENTITIES）——种子优先保序。"""
    from knowledge_lattice.core.semantic.constants import (
        ENTITY_RECALL_MAX_ENTITIES,
    )

    # has_field 扩展链：种子 60 个 template → 每 template 1 字段
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

    recs = []
    for i in range(60):
        recs.append(EntityRecord(type="template", key=f"TPL_X{i}",
                                 name=f"模板X{i}"))
        recs.append(EntityRecord(type="template_field", key=f"TPL_X{i}.F",
                                 name=f"字段X{i}",
                                 parent_key=f"template:TPL_X{i}"))
        recs.append(RelationRecord(
            src=("template", f"TPL_X{i}"), rel_type="has_field",
            dst=("template_field", f"TPL_X{i}.F")))
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.core.semantic.sync import run_sync

    run_sync(recall_env.backend, ORG,
             FakeSourceAdapter("tc", recs), settings=recall_env.settings,
             snapshot=list(recs), now=NOW)
    seed_ids = [recall_env.db.execute(
        "SELECT id FROM sem_entities WHERE org_id = ? AND key = ?",
        (ORG, f"TPL_X{i}")).fetchone()[0] for i in range(60)]
    # 种子 60 → 调用侧截 20（resolve 上限）；展开 +字段 → 截 50
    from knowledge_lattice.core.semantic.recall import resolve_query_entities

    out = resolve_query_entities(
        recall_env.backend, recall_env.settings, ORG, entities=seed_ids[:20])
    assert out is not None
    assert len(out["seeds"]) <= 20
    assert len(out["entity_ids"]) <= ENTITY_RECALL_MAX_ENTITIES == 50
    assert out["entity_ids"][:len(out["seeds"])] == out["seeds"]  # 种子优先


def test_tc_tag_04_seed_filters(recall_env) -> None:
    """种子过滤：restricted / 非 active 种子不进（T-S9 存在性零泄露）。"""
    from knowledge_lattice.core.semantic.recall import resolve_query_entities

    missing_id = 999_999
    out = resolve_query_entities(
        recall_env.backend, recall_env.settings, ORG, entities=[missing_id])
    assert out is None                      # 全滤空 → 不启用实体路

    with pytest.raises(ValueError):         # 超上限（>20）→ 400 语义
        resolve_query_entities(
            recall_env.backend, recall_env.settings, ORG,
            entities=list(range(1, 22)))


# ---- TC-TAG-05 实体路 SQL 与 matched_entities ----


def test_tc_tag_05_seed_and_expanded_weights(recall_env) -> None:
    """得分 = Σhits×（种子 1.0 / 扩展 0.5）——种子块 d_cn（hits=2 种子）得分
    2.0 高于扩展块；无权块召回排序带 rank（名次协议）。"""
    b = recall_env.backend
    plan = recall_env.db.compile_acl("u_os", ORG)   # u_os 只见 d_os（扩展块）
    rows = b.recall_by_entities(
        [recall_env.ids["vat.input_credit"],
         recall_env.ids["TPL_VAT_INPUT.TAX_AMT"]], plan,
        top_k=30, seed_ids=[recall_env.ids["vat.input_credit"]])
    # u_os 可见 d_os：扩展实体命中（hits=1 × 0.5）
    assert rows, "扩展命中块应召回"
    row = rows[0]
    assert row["score_raw"] == pytest.approx(0.5)
    assert row["matched_entities"] == [recall_env.ids["TPL_VAT_INPUT.TAX_AMT"]]
    assert row["rank"] == 1

    plan_cn = recall_env.db.compile_acl("u_cn", ORG)
    rows_cn = b.recall_by_entities(
        [recall_env.ids["vat.input_credit"]], plan_cn, top_k=30)
    assert rows_cn[0]["score_raw"] == pytest.approx(2.0)   # hits=2 × 种子 1.0


def test_tc_tag_05_k_entity_default_30(recall_env) -> None:
    """k_entity 默认 30（settings.k_entity）——recall_by_entities top_k 缺省。"""
    assert recall_env.settings.k_entity == 30


def test_tc_tag_05_rrf_and_matched_entities(recall_env) -> None:
    """三路 RRF：实体路行经 retrieve.search 融合，返回块附 matched_entities；
    实体路权重可配默认 1.0；未启用实体路时 results 无 matched_entities。"""
    from knowledge_lattice.core.docs.retrieve import search as run_search

    result = run_search(
        recall_env.backend, recall_env.settings,
        user_id="u_cn", org_id=ORG, query="进项税额抵扣", top_k=5,
        embedder=None, reranker=None,
        entity_ids=[recall_env.ids["vat.input_credit"],
                    recall_env.ids["TPL_VAT_INPUT"],
                    recall_env.ids["TPL_VAT_INPUT.TAX_AMT"]],
        entity_seeds=[recall_env.ids["vat.input_credit"]],
    )
    assert result["results"], "实体路应召回 d_cn 块"
    hit = [r for r in result["results"] if r["doc_id"] == "d_cn"]
    assert hit, "d_cn（种子命中块）应在结果中"
    assert hit[0].get("matched_entities") == [
        recall_env.ids["vat.input_credit"]]
    # 未启用：无 matched_entities 键（§6.1「未启用时省略」）
    plain = run_search(
        recall_env.backend, recall_env.settings,
        user_id="u_cn", org_id=ORG, query="进项税额抵扣", top_k=5,
        embedder=None, reranker=None,
    )
    assert all("matched_entities" not in r for r in plain["results"])


def test_tc_tag_05_entity_route_weight_configurable(recall_env) -> None:
    """RRF 权重可配：实体路权重调低后实体块融合分下降（rrf_fuse weights 面）。"""
    from knowledge_lattice.core.docs.retrieve import rrf_fuse

    routes = [("fts", [10, 11]), ("entities", [12])]
    fused_default = dict(rrf_fuse(routes, k=60))
    fused_low = dict(rrf_fuse(routes, k=60, weights={"entities": 0.5}))
    assert fused_low[12] < fused_default[12]
    # 默认权重 = 1.0：同 rank（各路第 1）融合分相等（tie-break rid）
    assert fused_default[12] == pytest.approx(fused_default[10])
    # 默认（无 weights）= 1.0
    assert dict(rrf_fuse(routes, k=60))[12] == pytest.approx(
        dict(rrf_fuse(routes, k=60, weights={"entities": 1.0}))[12])


# ---- TC-ACL-06 扩展：实体路 CTE 同构（任务书 A1） ----


def test_tc_acl_06_entity_route_cte_isomorphism(recall_env) -> None:
    """实体路渲染 SQL 与基础/向量路共用同一 visible_docs CTE——双方言
    归一化参数记号后 CTE 前缀逐字相同（TC-ACL-06 断言扩展到实体路）。"""
    import re

    db = recall_env.db
    name = db.name
    if name == "sqlite":
        from knowledge_lattice.store.sqlite.acl_render import (
            render_entity_recall_select,
            render_select,
            render_vec_recall_select,
        )
        from knowledge_lattice.store.sqlite.vec import pack_f32
        vec_arg = pack_f32([0.0] * 8)
    else:
        from knowledge_lattice.store.postgres.acl_render import (
            render_entity_recall_select,
            render_select,
            render_vec_recall_select,
        )
        vec_arg = "[0,0,0,0,0,0,0,0]"

    plan = db.compile_acl("u_cn", ORG, embed_model="fake-embed:8")
    ent_sql, _p = render_entity_recall_select(plan, [1, 2], [1], top_k=30)
    base_sql, _bp = render_select(plan)
    vec_sql, _vp = render_vec_recall_select(plan, vec_arg, top_k=10)

    def _norm_cte(sql: str) -> str:
        cte = sql.split(")", 1)[0] if sql.startswith("WITH") else ""
        return re.sub(r"[:%]\(?[A-Za-z0-9_]+\)?s?", "?", cte)

    assert _norm_cte(ent_sql) == _norm_cte(base_sql) == _norm_cte(vec_sql), (
        "实体路必须与基础/向量路共用同一 visible_docs CTE（T-S8）")
    # 实体路特有面：sem_chunk_entities JOIN + 种子/扩展 CASE + GROUP BY
    assert "sem_chunk_entities" in ent_sql
    assert "CASE WHEN" in ent_sql and "GROUP BY" in ent_sql
