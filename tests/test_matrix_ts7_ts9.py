"""m2s-6 越权矩阵（T-S7 / T-S8 / T-S9——design §6.3 权限口径；双后端 CI
常跑、并入越权用例集）。

- T-S7 语义组织隔离：A 组织调用方 annotate / get_entity / search_entities /
  l0 对 B 组织实体全部不可达；两组织 dict_rev 互相独立；
- T-S8 实体召回不放宽 ACL：同一用户同一查询 FTS/向量/实体三路并集 ⊆
  可见块集合；无权文档里命中实体的块实体路也召回不到；
- T-S9 restricted：无权 annotate 无 span、get_entity 404、关系展开不出现、
  search_entities 无命中；**持权路径（m2s-6 交付）**：role=sem_restricted
  成员可见 + 持权访问入权限审计（semantic.restricted_access——A-16 口径）。
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
ORG_GL = "org:gl"
NOW = "2026-11-01 09:00:00"


@pytest.fixture()
def matrix_env(backend, tmp_path):
    """两组织语义栈：org:tax 主图（含 restricted R + 邻居 N + 共享别名）+
    org:gl 隔离图；维度 ACL 面（u_cn 只见 CN 文档——T-S8）。"""
    from types import SimpleNamespace

    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord
    from knowledge_lattice.core.semantic.sync import run_sync

    for org, ds in ((ORG, "ds:vat_lib"), (ORG_GL, "ds:vat_lib_gl")):
        seed_org(backend, org)
        seed_dataset(backend, org, ds)
        seed_dimension(backend, org, "region")
        seed_dim_value(backend, dim_id_for(org, "region"), "CN")
        seed_dim_value(backend, dim_id_for(org, "region"), "OS")
    for uid in ("u_cn", "u_gl", "u_owner"):
        seed_user(backend, uid)
    seed_membership(backend, "u_owner", ORG)
    seed_membership(backend, "u_cn", ORG)
    seed_membership(backend, "u_gl", ORG_GL)
    seed_grant(backend, user_id="u_cn", dim_id=dim_id_for(ORG, "region"),
               val_id=val_id_for(ORG, "region", "CN"))

    # org:tax 文档：d_cn（u_cn 可见，实体 E 打标）/ d_os（u_cn 不可见，实体 E 打标）
    seed_searchable_doc(backend, "d_cn", dims={"region": ["CN"]},
                        content_seg="进项 抵扣 范围")
    seed_searchable_doc(backend, "d_os", dims={"region": ["OS"]},
                        content_seg="海外 进项 抵扣 口径")

    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    b = backend.make_backend()
    tax_recs = [
        EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣"),
        EntityRecord(type="template", key="TPL_TAX", name="税务模板"),
        # 邻接概念（restricted R 经 YAML sensitivity 声明——EntityRecord 无该面）
        EntityRecord(type="concept", key="tax.neighbor", name="邻接概念"),
        RelationRecord(src=("concept", "vat.input_credit"), rel_type="refers_to",
                       dst=("template", "TPL_TAX")),
    ]
    gl_recs = [
        EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣"),
        EntityRecord(type="template", key="TPL_GL", name="GL 模板"),
        RelationRecord(src=("concept", "vat.input_credit"), rel_type="refers_to",
                       dst=("template", "TPL_GL")),
    ]
    run_sync(b, ORG, FakeSourceAdapter("template_center", tax_recs),
             settings=settings, snapshot=list(tax_recs), now=NOW)
    run_sync(b, ORG_GL, FakeSourceAdapter("template_center", gl_recs),
             settings=settings, snapshot=list(gl_recs), now=NOW)
    # restricted R（YAML sensitivity: restricted）+ R→N related_to
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    repo = tmp_path / "yamlrepo"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "secret.yaml").write_text(
        "- id: concept:tax.secret\n  owner: o\n"
        "  name: 内部税收筹划方案\n"
        "  aliases: [筹划方案内部口径]\n"
        "  sensitivity: restricted\n"
        "  related_to: [concept:tax.neighbor]\n",
        encoding="utf-8")
    run_yaml_sync(b, ORG, YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=settings, now=NOW)
    clear_annotator_cache()
    assert run_build(b, ORG, settings=settings)["status"] == "ready"
    assert run_build(b, ORG_GL, settings=settings)["status"] == "ready"

    def _eid(org: str, key: str) -> int:
        return backend.execute(
            "SELECT id FROM sem_entities WHERE org_id = ? AND key = ?",
            (org, key)).fetchone()[0]

    # 打标（同 dict_rev=r1）：d_cn / d_os 都命中 E（T-S8 前置——无权文档里
    # 命中实体的块）
    rev = backend.execute(
        "SELECT dict_rev FROM sem_builds WHERE org_id = ? AND status = 'ready'",
        (ORG,)).fetchone()[0]
    for dd, hits in (("d_cn", 2), ("d_os", 5)):
        rid = backend.execute(
            "SELECT rid FROM chunks WHERE doc_id = ? AND version = 1",
            (dd,)).fetchone()[0]
        backend.execute(
            "INSERT INTO sem_chunk_entities(org_id, chunk_rid, doc_id, version,"
            " entity_id, hits, dict_rev) VALUES (?, ?, ?, 1, ?, ?, ?)",
            (ORG, rid, dd, _eid(ORG, "vat.input_credit"), hits, rev))
    return SimpleNamespace(
        db=backend, backend=b, settings=settings,
        eid=lambda k: _eid(ORG, k), gl_eid=lambda k: _eid(ORG_GL, k))


# ---- T-S7 语义组织隔离 ----


def test_ts7_cross_org_isolation(matrix_env) -> None:
    """u_gl（org:gl）对 org:tax 实体五面全不可达 + 两组织 dict_rev 独立。"""
    from knowledge_lattice.core.semantic.annotator import annotate_text
    from knowledge_lattice.core.semantic.expand import EntityNotFound, get_entity
    from knowledge_lattice.core.semantic.lookup import search_entities

    env = matrix_env
    # annotate：GL 用户在自己组织识别（GL 词典服务，无 tax 实体泄漏）
    r = annotate_text(env.backend, env.settings, ORG_GL, "进项税额抵扣怎么办")
    tax_ids_in_gl = [m["entity_id"] for m in r["mentions"]
                     if m["entity_id"] == env.eid("vat.input_credit")]
    # 同名 key 在 GL 也有实体（同名不同 id）——断言命中的是 GL 实体而非 tax
    gl_mentions = [m for m in r["mentions"]
                   if m["entity_key"] == "concept:vat.input_credit"]
    assert gl_mentions and all(
        m["entity_id"] == env.gl_eid("vat.input_credit") for m in gl_mentions)
    assert not tax_ids_in_gl

    # get_entity：GL 用户查 tax 实体 id → 404（org 第一条件隔离）
    with pytest.raises(EntityNotFound):
        get_entity(env.backend, ORG_GL, entity_id=env.eid("vat.input_credit"))
    # search_entities：GL 组织内查 tax 专属 key（TPL_TAX 只在 tax）→ 无命中
    out = search_entities(env.backend, ORG_GL, "税务模板")
    assert not any(e["key"] == "TPL_TAX" for e in out["entities"])
    # l0 / dict_rev 独立
    rev_tax = env.db.execute(
        "SELECT dict_rev FROM sem_builds WHERE org_id = ? AND status='ready'",
        (ORG,)).fetchone()[0]
    rev_gl = env.db.execute(
        "SELECT dict_rev FROM sem_builds WHERE org_id = ? AND status='ready'",
        (ORG_GL,)).fetchone()[0]
    assert rev_tax != rev_gl


# ---- T-S8 实体召回不放宽 ACL ----


def test_ts8_entity_route_no_acl_widening(matrix_env) -> None:
    """三路并集 ⊆ 用户可见块集合；无权文档（d_os）命中实体的块实体路也
    召回不到。"""
    from knowledge_lattice.core.docs.acl import compile_acl
    from knowledge_lattice.core.docs.retrieve import search as run_search

    env = matrix_env
    eid = env.eid("vat.input_credit")
    result = run_search(
        env.backend, env.settings, user_id="u_cn", org_id=ORG,
        query="进项抵扣 的范围", top_k=10,
        entity_ids=[eid], entity_seeds=[eid],
    )
    # u_cn 可见集 = {d_cn}（region=CN）——d_os 不可出现在任何结果
    assert all(r["doc_id"] != "d_os" for r in result["results"]), (
        "实体路召回无权文档块——T-S8 失守")
    assert any(r["doc_id"] == "d_cn" for r in result["results"])

    # 三路并集 ⊆ 可见块（独立重编译可见集——TC-ACL-08 双断言数据源）
    plan = compile_acl(env.db.make_backend(), "u_cn", ORG)
    visible = env.backend.visible_chunk_ids(plan)
    # 直接对 recall_by_entities 断言（实体路独立面）
    rows = env.backend.recall_by_entities([eid], plan, top_k=30)
    assert rows, "实体路应召回（d_cn 打标）"
    assert all(r["rid"] in visible for r in rows), (
        "实体路结果 ⊄ 可见块集合——T-S8 失守")
    os_rids = {r[0] for r in env.db.execute(
        "SELECT rid FROM chunks WHERE doc_id = 'd_os' AND version = 1")}
    assert not any(r["rid"] in os_rids for r in rows), (
        "无权文档里命中实体的块被实体路召回——T-S8 失守")


# ---- T-S9 restricted 静默不可见 + 持权路径 ----


def test_ts9_restricted_silent(matrix_env) -> None:
    """无权成员：annotate 无 span / get_entity 404 / 关系展开不出现 /
    search_entities 无命中（restricted 别名「内部税收筹划方案」）。"""
    from knowledge_lattice.core.semantic.annotator import annotate_text
    from knowledge_lattice.core.semantic.expand import EntityNotFound, get_entity
    from knowledge_lattice.core.semantic.lookup import search_entities

    env = matrix_env
    secret_id = env.eid("tax.secret")
    # annotate：文本含 restricted 实体名 → 无 span（表现为不存在）
    r = annotate_text(env.backend, env.settings, ORG,
                      "内部税收筹划方案 的口径是什么")
    assert not [m for m in r["mentions"]
                if m["entity_id"] == secret_id]
    # get_entity → 404
    with pytest.raises(EntityNotFound):
        get_entity(env.backend, ORG, entity_id=secret_id)
    # 关系展开：从邻居 N 展开 → R 节点不出现
    graph = get_entity(env.backend, ORG, entity_id=env.eid("tax.neighbor"),
                       expand=["related_to"])
    assert all(n["id"] != secret_id for n in graph["nodes"])
    # search_entities：restricted 名称无命中
    out = search_entities(env.backend, ORG, "内部税收筹划方案")
    assert not any(e["id"] == secret_id for e in out["entities"])


def test_ts9_restricted_authorized_path(matrix_env) -> None:
    """持权路径（m2s-6）：role=sem_restricted 成员 annotate 有 span /
    get_entity 放行 + 展开含 restricted 端点；持权访问入权限审计
    （semantic.restricted_access——A-16 口径持权面）。"""
    from knowledge_lattice.core.semantic.annotator import annotate_text
    from knowledge_lattice.core.semantic.expand import get_entity

    env = matrix_env
    seed_user(env.db, "u_secret")
    seed_membership(env.db, "u_secret", ORG, role="sem_restricted")
    secret_id = env.eid("tax.secret")

    r = annotate_text(env.backend, env.settings, ORG,
                      "内部税收筹划方案 的口径是什么",
                      include_restricted=True)
    hits = [m for m in r["mentions"] if m["entity_id"] == secret_id]
    assert hits and hits[0]["surface"] == "内部税收筹划方案"

    out = get_entity(env.backend, ORG, entity_id=secret_id, can_restricted=True)
    assert out["entity"]["id"] == secret_id
    # 展开含 restricted 端点（持权放行——include_restricted）
    graph = get_entity(env.backend, ORG, entity_id=env.eid("tax.neighbor"),
                       expand=["related_to"], can_restricted=True)
    assert any(n["id"] == secret_id for n in graph["nodes"])
    # 持权访问审计（annotate 面——事件入 outbox；api/mcp 层注入路径模拟：
    # _has_semantic_restricted 判定 + _audit_restricted_access 落事件）
    from knowledge_lattice.api.semantic import (
        _audit_restricted_access,
        _has_semantic_restricted,
    )

    class _S:
        backend = env.backend

    class _A:
        user_id = "u_secret"

    assert _has_semantic_restricted(_S, ORG, _A) is True
    _audit_restricted_access(_S, ORG, _A, "annotate", [secret_id])
    events = env.db.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
        ("semantic.restricted_access",)).fetchall()
    assert events and str(secret_id) in events[0][0], (
        "持权 restricted 访问应产生权限事件（A-16 口径）")


def test_ts9_restricted_role_gate(matrix_env) -> None:
    """role 载体：普通 member / org_admin 不持 semantic:restricted——
    include_restricted 只对 sem_restricted 角色生效（api/mcp 判定面）。"""
    from knowledge_lattice.api.semantic import _has_semantic_restricted

    env = matrix_env
    seed_user(env.db, "u_admin")
    seed_membership(env.db, "u_admin", ORG, role="org_admin")

    class _S:  # duck-typed service（权限判定只读 backend）
        backend = env.backend

    class _A:
        user_id: str

    a = _A(); a.user_id = "u_cn"
    assert _has_semantic_restricted(_S, ORG, a) is False
    a2 = _A(); a2.user_id = "u_admin"
    assert _has_semantic_restricted(_S, ORG, a2) is False, (
        "org_admin 不默认兼任 semantic:restricted（§6.3 权限口径③最小面）")
    seed_user(env.db, "u_secret2")
    seed_membership(env.db, "u_secret2", ORG, role="sem_restricted")
    a3 = _A(); a3.user_id = "u_secret2"
    assert _has_semantic_restricted(_S, ORG, a3) is True
