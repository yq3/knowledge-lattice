"""m3-2 C 组：m2s-6 显式断言三补之另两补（T-S7 describe_table/l0 + T-S8
真随机向量三路）。

- T-S7 显式矩阵断言（m2s-6 交付时由成员关系 403+白名单〔T-S11〕+l0 org
  作用域旁证覆盖——本文件补显式）：同名 table key 双组织登记、列集不同 →
  describe_table 各自组织内容隔离（200 面内容比对 + 未登记 key 403）；
  l0 导出只含本组织实体、dict_rev 独立；
- T-S8 真随机向量三路（m2s-6 测试臂向量路以确定性 embedder 覆盖——本文件
  补真随机向量形态）：CTE 三路同构（base/vec/entities 渲染 SQL 前缀逐字
  相同）+ 运行时三路（FTS/向量/实体）并集 ⊆ 可见块集合（任意向量不放宽
  ACL——#35 §13.1 不变式）。
"""

from __future__ import annotations

import json
import random
import re

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
from test_matrix_ts7_ts9 import matrix_env  # noqa: F401 —— T-S8 fixture 引入

ORG = "org:tax"
ORG_GL = "org:gl"
NOW = "2026-11-08 09:00:00"


@pytest.fixture()
def ts7_env(backend, tmp_path):
    """同名 table key（ods.vat_input_invoice）双组织登记、列集不同 +
    各组织专属 concept——describe_table/l0 显式隔离断言数据面。"""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from fake_providers import FakeEmbedder
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.domain.auth import hash_token

    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        probe_interval_s=0, maintenance_interval_s=0.0,
                        worker_mode="inline", worker_poll_s=0.05)
    b = backend.make_backend()
    for org, uid in ((ORG, "u_tax"), (ORG_GL, "u_gl")):
        seed_org(backend, org)
        seed_user(backend, uid)
        seed_membership(backend, uid, org)
    backend.commit()

    def _recs(tax_side: bool):
        table_key = "ods.vat_input_invoice"
        cols = (("tax_amt", "税额"), ("inv_no", "发票号")) if tax_side \
            else (("gl_amt", "总账金额"),)
        recs = [
            EntityRecord(type="table", key=table_key,
                         name="进项发票表" + ("（tax）" if tax_side else "（gl）")),
        ]
        rel = [
            (("table", table_key), "has_column",
             ("column", f"{table_key}.{ck}")) for ck, _ in cols
        ]
        recs.extend(
            EntityRecord(type="column", key=f"{table_key}.{ck}", name=cn,
                         parent_key=f"table:{table_key}")
            for ck, cn in cols)
        recs.extend(RelationRecord(src=s, rel_type=r, dst=d) for s, r, d in rel)
        return recs

    run_sync(b, ORG, FakeSourceAdapter("template_center", _recs(True)),
             settings=settings, snapshot=_recs(True), now=NOW)
    run_sync(b, ORG_GL, FakeSourceAdapter("template_center", _recs(False)),
             settings=settings, snapshot=_recs(False), now=NOW)
    # 组织专属 concept 经 YAML curated（l0: true——l0 导出面数据源）
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    def _yaml_sync(org: str, key: str, name: str, definition: str) -> None:
        repo = tmp_path / f"yamlrepo-{org.replace(':', '-')}"
        (repo / "concepts").mkdir(parents=True, exist_ok=True)
        (repo / "concepts" / "l0.yaml").write_text(
            f"- id: concept:{key}\n  owner: tax-domain\n"
            f"  name: {name}\n"
            f"  aliases: [{name}]\n"
            f"  definition: {definition}\n"
            f"  l0: true\n", encoding="utf-8")
        run_yaml_sync(b, org, YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                      settings=settings, now=NOW)

    _yaml_sync(ORG, "tax.only", "tax 专属概念", "tax 组织的核心口径定义。")
    _yaml_sync(ORG_GL, "gl.only", "gl 专属概念", "gl 组织的核心口径定义。")
    clear_annotator_cache()
    assert run_build(b, ORG, settings=settings)["status"] == "ready"
    assert run_build(b, ORG_GL, settings=settings)["status"] == "ready"

    tokens = {"u_tax": "dev-static-u-tax", "u_gl": "dev-static-u-gl"}
    for uid, token in tokens.items():
        backend.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                        (hash_token(token), uid))
    backend.commit()

    kwargs = dict(embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
                  run_startup_probe=False)
    if backend.name == "pg":
        app = create_app(settings, backend=backend.make_backend(), **kwargs)
    else:
        app = create_app(settings, **kwargs)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, db=backend, backend=b, settings=settings,
            tokens=tokens,
            hdr=lambda uid: {"Authorization": f"Bearer {tokens[uid]}"},
        )


# ---- T-S7 显式断言：describe_table / l0 ----


def test_ts7_describe_table_same_key_org_isolated(ts7_env) -> None:
    """同名 table key 双组织登记、列集不同：describe_table 各自只返回本组织
    的列（200 面内容比对——降级轻量节点亦按本组织列渲染）；未登记 key →
    403（白名单防枚举——T-S11②）；跨组织路径 org_scoped 403（旁证升级为
    显式矩阵行）。"""
    env = ts7_env
    # tax 面：同名表 → tax 的列（tax_amt/inv_no；无 metadata 源 → degraded
    # 轻量节点，列来自本组织 column 实体——仍构成组织隔离内容断言）
    r_tax = env.client.get(
        f"/api/orgs/{ORG}/semantic/tables/ods.vat_input_invoice/describe",
        headers=env.hdr("u_tax"))
    assert r_tax.status_code == 200, r_tax.text
    tax_cols = {c["name"] for c in r_tax.json().get("columns") or ()}
    assert tax_cols == {"tax_amt", "inv_no"}, tax_cols
    # gl 面：同名表 → gl 的列（gl_amt——tax 列不泄露）
    r_gl = env.client.get(
        f"/api/orgs/{ORG_GL}/semantic/tables/ods.vat_input_invoice/describe",
        headers=env.hdr("u_gl"))
    assert r_gl.status_code == 200, r_gl.text
    gl_cols = {c["name"] for c in r_gl.json().get("columns") or ()}
    assert gl_cols == {"gl_amt"}, gl_cols
    # tax 专属表 key 在 gl 未登记 → 403（防枚举）；对称面
    r_miss = env.client.get(
        f"/api/orgs/{ORG_GL}/semantic/tables/tax.only/describe",
        headers=env.hdr("u_gl"))
    assert r_miss.status_code == 403
    # 跨组织路径（u_gl 对 org:tax 路径）→ org_scoped 403
    r_cross = env.client.get(
        f"/api/orgs/{ORG}/semantic/tables/ods.vat_input_invoice/describe",
        headers=env.hdr("u_gl"))
    assert r_cross.status_code == 403


def test_ts7_l0_export_org_scoped(ts7_env) -> None:
    """l0 导出：gl 的 fragments 只含 gl 专属实体（tax 专属不出现在 gl 面，
  逐片段比对）；两组织 dict_rev 独立（m2s-6 旁证收口为显式断言）。"""
    env = ts7_env
    r_gl = env.client.get(f"/api/orgs/{ORG_GL}/semantic/l0",
                          headers=env.hdr("u_gl"))
    assert r_gl.status_code == 200, r_gl.text
    body = r_gl.json()
    fragments_text = json.dumps(body.get("fragments") or [], ensure_ascii=False)
    assert "gl 专属概念" in fragments_text
    assert "tax 专属概念" not in fragments_text, "tax 实体不得出现在 gl 的 l0 面"
    # dict_rev 独立
    rev_tax = env.db.execute(
        "SELECT dict_rev FROM sem_builds WHERE org_id = ? AND status='ready'",
        (ORG,)).fetchone()[0]
    rev_gl = env.db.execute(
        "SELECT dict_rev FROM sem_builds WHERE org_id = ? AND status='ready'",
        (ORG_GL,)).fetchone()[0]
    assert body["dict_rev"] == rev_gl != rev_tax


# ---- T-S8 真随机向量三路（参考 tests/test_tag_04_entity_recall.py 现形态） ----


def test_ts8_random_vector_three_routes_cte_and_acl(matrix_env) -> None:
    """真随机向量形态：①CTE 三路同构——base/vec(随机向量参数)/entities 渲染
    SQL 归一化参数记号后前缀逐字相同；②运行时三路并集 ⊆ 可见块集合
    （任意向量不放宽 ACL——d_os 块不在任何一路）。"""
    env = matrix_env
    from knowledge_lattice.core.docs.acl import compile_acl

    db = env.db
    label = env.settings.embed_model_label
    plan = db.compile_acl("u_cn", ORG, embed_model=label)

    # 真随机向量（非确定性 embedder 形态——任意方向的查询向量）：
    # 两块各插真随机向量 + 查询向量真随机（random.Random 固定种子保证可复现）
    rng = random.Random(20261108)
    dim = env.settings.embed_dim
    rids = {
        dd: db.execute(
            "SELECT rid FROM chunks WHERE doc_id = ? AND version = 1", (dd,)
        ).fetchone()[0]
        for dd in ("d_cn", "d_os")
    }
    for dd, rid in rids.items():
        db.insert_vector(rid, label, [rng.uniform(-1, 1) for _ in range(dim)])
    query_vec = [rng.uniform(-1, 1) for _ in range(dim)]

    # ① CTE 三路同构（真随机向量参数形态——参数记号归一化后前缀逐字相同）
    if db.name == "sqlite":
        from knowledge_lattice.store.sqlite.acl_render import (
            render_entity_recall_select,
            render_select,
            render_vec_recall_select,
        )
        from knowledge_lattice.store.sqlite.vec import pack_f32

        vec_arg = pack_f32(query_vec)
    else:
        from knowledge_lattice.store.postgres.acl_render import (
            render_entity_recall_select,
            render_select,
            render_vec_recall_select,
        )
        from knowledge_lattice.store.postgres.vec import format_vector

        vec_arg = format_vector(query_vec)

    eid = env.eid("vat.input_credit")
    ent_sql, _ = render_entity_recall_select(plan, [eid], [eid], top_k=30)
    base_sql, _ = render_select(plan)
    vec_sql, _ = render_vec_recall_select(plan, vec_arg, top_k=10)

    def _norm_cte(sql: str) -> str:
        cte = sql.split(")", 1)[0] if sql.startswith("WITH") else ""
        return re.sub(r"[:%]\(?[A-Za-z0-9_]+\)?s?", "?", cte)

    assert _norm_cte(ent_sql) == _norm_cte(base_sql) == _norm_cte(vec_sql), (
        "真随机向量形态下三路必须共用同一 visible_docs CTE（T-S8）")

    # ② 运行时三路：FTS / 向量（真随机 query_vec）/ 实体——并集 ⊆ 可见块
    b = env.backend
    visible = set(b.visible_chunk_ids(plan))
    os_rids = set(rids.values()) - {rids["d_cn"]}

    fts_rows = b.recall_fts(["进项"], plan, top_k=30)
    vec_rows = b.recall_vec(query_vec, plan, top_k=30)
    ent_rows = b.recall_by_entities([eid], plan, top_k=30)
    for name, rows in (("fts", fts_rows), ("vec", vec_rows), ("entities", ent_rows)):
        assert all(r["rid"] in visible for r in rows), (
            f"{name} 路（真随机向量形态）召回 ⊄ 可见块集合——T-S8 失守")
        assert not any(r["rid"] in os_rids for r in rows), (
            f"{name} 路召回无权文档 d_os 块——T-S8 失守")
