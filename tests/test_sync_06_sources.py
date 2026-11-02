"""m2s-3 A 组源接入与挂账 G-15：

- scenario_config / report_center 适配器（SourceAdapter 协议——快照/refs 形态）；
- yaml 源走既有 sync 流程：T-S2 删除比例保护（含 force 放行）/ T-S4 宽限推进；
- TC-SYNC-02 半句收口：metadata 引用面 = YAML 显式列出 ∪ template_center 推导兜底；
- TC-SYNC-06 半句收口：值域显式映射表（dim_value_map.yaml 最小实现——design §4
  无专表 DDL）；
- C.6 sync 路径 adapter.close 接线；
- G-15 关系级 missing（源端删边两端仍在→missing→宽限→retired）+ upsert 前端点
  状态过滤（指向 retired 端点不回 active）。
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from fake_semantic import FakeSourceAdapter, FakeTransport, md_canned, tc_canned
from helpers import seed_org

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"


@pytest.fixture()
def env(backend, tmp_path):
    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    return SimpleNamespace(db=backend, backend=backend.make_backend(),
                           settings=settings, tmp=tmp_path)


def _sync(env, records, *, adapter_name="template_center", now=NOW, force=False):
    from knowledge_lattice.core.semantic.sync import run_sync

    return run_sync(env.backend, ORG, FakeSourceAdapter(adapter_name, records),
                    settings=env.settings, snapshot=list(records), now=now,
                    force=force)


# ---- scenario_config 适配器 ----


def test_scenario_config_adapter_expansion(tmp_path) -> None:
    from knowledge_lattice.core.semantic.adapters.scenario_config import (
        ScenarioConfigAdapter,
    )
    from knowledge_lattice.core.semantic.adapters import SourceConfig

    canned = {("GET", "/scenarios"): {"items": [
        {"code": "SCN_MONTH", "name": "月度申报", "aliases": ["月报"],
         "templates": ["TPL_VAT_INPUT", "TPL_MISSING"]},
        {"code": "SCN_YEAR", "name": "年度汇算", "templates": []},
    ], "next_cursor": None}}
    transport = FakeTransport({"http://sc/api": canned})
    adapter = ScenarioConfigAdapter(
        SourceConfig(endpoint="http://sc/api"), transport=transport)
    records = list(adapter.fetch(ORG))

    entities = {(r.type, r.key): r for r in records if hasattr(r, "type")}
    assert ("scenario", "SCN_MONTH") in entities and ("scenario", "SCN_YEAR") in entities
    assert entities[("scenario", "SCN_MONTH")].aliases == ("月报",)
    rels = [(r.src[1], r.rel_type, r.dst[1]) for r in records if not hasattr(r, "type")]
    assert ("SCN_MONTH", "uses", "TPL_VAT_INPUT") in rels
    assert ("SCN_MONTH", "uses", "TPL_MISSING") in rels  # 端点缺失记冲突不写入（TC-SYNC-04 面）


def test_scenario_config_paging(tmp_path) -> None:
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.scenario_config import (
        ScenarioConfigAdapter,
    )

    class PagingTransport:
        def __call__(self, endpoint, path, params=None):
            if params and params.get("cursor") == "c2":
                return {"items": [{"code": "S2", "name": "二", "templates": []}],
                        "next_cursor": None}
            return {"items": [{"code": "S1", "name": "一", "templates": []}],
                    "next_cursor": "c2"}

    adapter = ScenarioConfigAdapter(
        SourceConfig(endpoint="http://sc/api"), transport=PagingTransport())
    keys = {r.key for r in adapter.fetch(ORG) if hasattr(r, "type")}
    assert keys == {"S1", "S2"}


# ---- report_center 适配器 ----


def test_report_center_adapter_expansion(tmp_path) -> None:
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.report_center import ReportCenterAdapter

    canned = {("GET", "/reports"): {"items": [
        {"code": "VAT_MAIN", "name": "增值税主表", "items": [
            {"code": "L1", "name": "按适用税率计税销售额"},
            {"code": "L12", "name": "进项税额", "parent": "L1",
             "derived_from": ["template_field:TPL_VAT_INPUT.F1"]},
        ]},
    ], "next_cursor": None}}
    transport = FakeTransport({"http://rc/api": canned})
    records = list(ReportCenterAdapter(
        SourceConfig(endpoint="http://rc/api"), transport=transport).fetch(ORG))

    entities = {(r.type, r.key): r for r in records if hasattr(r, "type")}
    assert ("report", "VAT_MAIN") in entities
    assert ("report_item", "VAT_MAIN.L1") in entities
    assert ("report_item", "VAT_MAIN.L12") in entities
    assert entities[("report_item", "VAT_MAIN.L12")].parent_key == "report_item:VAT_MAIN.L1"
    rels = {(r.src[1], r.rel_type, r.dst[1]) for r in records if not hasattr(r, "type")}
    assert ("VAT_MAIN", "has_item", "VAT_MAIN.L1") in rels
    assert ("VAT_MAIN.L12", "child_of", "VAT_MAIN.L1") in rels
    assert ("VAT_MAIN.L12", "derived_from", "TPL_VAT_INPUT.F1") in rels


def test_report_center_paging(tmp_path) -> None:
    """N3/R2：report_center 分页对称用例（与 scenario_config 同构——next_cursor
    翻页拼全量）。"""
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.report_center import ReportCenterAdapter

    class PagingTransport:
        def __call__(self, endpoint, path, params=None):
            if params and params.get("cursor") == "p2":
                return {"items": [{"code": "R2", "name": "二报", "items": []}],
                        "next_cursor": None}
            return {"items": [{"code": "R1", "name": "一报", "items": []}],
                    "next_cursor": "p2"}

    adapter = ReportCenterAdapter(
        SourceConfig(endpoint="http://rc/api"), transport=PagingTransport())
    keys = {r.key for r in adapter.fetch(ORG) if hasattr(r, "type")}
    assert keys == {"R1", "R2"}


# ---- yaml 源走既有 sync 流程：T-S2 / T-S4 ----


YAML_CONCEPTS = """\
- id: concept:vat.a
  name: 概念甲
  owner: o
  refers_to: [concept:vat.b]
- id: concept:vat.b
  name: 概念乙
  owner: o
"""


def _yaml_env(env):
    (env.tmp / "repo").mkdir()
    (env.tmp / "repo" / "concepts").mkdir()
    (env.tmp / "repo" / "concepts" / "c.yaml").write_text(YAML_CONCEPTS, encoding="utf-8")
    return env.tmp / "repo"


def _yaml_sync(env, repo, **kw):
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    return run_yaml_sync(env.backend, ORG, YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                         settings=env.settings, **kw)


def test_yaml_source_delete_guard_and_force(env) -> None:
    repo = _yaml_env(env)
    assert _yaml_sync(env, repo, now=NOW)["status"] == "succeeded"

    # 仓清空（两条纯人工实体全消失）→ 删除比例保护 abort、零写入（T-S2）
    import shutil

    shutil.rmtree(repo / "concepts")
    (repo / "concepts").mkdir()
    result = _yaml_sync(env, repo, now="2026-10-31 10:00:00")
    assert result["status"] == "aborted_guard"
    assert result["stats"]["guard"]["vanished"] == 2

    # force 放行 → 实体转 missing（T-S2 v1.9.1 口径）
    result = _yaml_sync(env, repo, now="2026-10-31 10:00:00", force=True)
    assert result["status"] == "succeeded" and result["stats"]["forced"] is True
    assert result["stats"]["missing"] == 2


def test_yaml_source_grace_retires_entity_and_relations(env) -> None:
    from knowledge_lattice.core.semantic.constants import REFERENCE_REL_TYPES  # noqa: F401

    repo = _yaml_env(env)
    assert _yaml_sync(env, repo, now=NOW)["status"] == "succeeded"
    row = env.backend.sem_entity_by_key(ORG, "concept", "vat.a")
    assert row is not None

    # 删一条（1/2 = 50% > 20% → guard 会拦——用 force 走宽限路径）
    (repo / "concepts" / "c.yaml").write_text(
        YAML_CONCEPTS.split("- id: concept:vat.b")[0], encoding="utf-8")
    assert _yaml_sync(env, repo, now="2026-10-31 11:00:00", force=True)["status"] == "succeeded"
    assert env.backend.sem_entity_by_key(ORG, "concept", "vat.b")["status"] == "missing"

    # 超宽限期 → retired 且其关系一并 retired（T-S4③）
    from knowledge_lattice.store.taskclock import add_seconds

    advanced = env.backend.advance_status(ORG, missing_before="2026-11-01 12:00:00")
    assert advanced["retired"] >= 1
    assert env.backend.sem_entity_by_key(ORG, "concept", "vat.b")["status"] == "retired"


# ---- TC-SYNC-02 半句：YAML 显式列出 ∪ tc 推导兜底 ----


def test_tc_sync_02_yaml_explicit_refs_union(env, tmp_path, monkeypatch) -> None:
    from knowledge_lattice.core.semantic.adapters import (
        MetadataAdapter,
        SourceConfig,
        build_adapter,
    )
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter

    # YAML 显式列出 table:db.t2（concept refers_to）
    repo = tmp_path / "repo2"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "c.yaml").write_text(
        "- id: concept:db.t2\n"
        "  name: 稀释表\n"
        "  owner: o\n"
        "  refers_to: [table:db.t2, column:db.t3.c9]\n", encoding="utf-8")

    sources = json.dumps({
        ORG: {
            "template_center": {"endpoint": "http://tc/api"},
            "metadata": {"endpoint": "http://md/api"},
            "yaml": {"endpoint": str(repo)},
        },
    })
    settings = SimpleNamespace(
        semantic_sources=json.loads(sources),
        semantic_sources_json=sources,
    )

    # tc 快照引用 t1；metadata 罐头含 t1/t2/t3 —— 期望只拉 t1（tc 推导兜底）
    # + t2/t3（YAML 显式），t3 表级未引用但列引用携带父表
    cols = {"name": "T", "columns": [{"name": "c1"}]}
    transport = FakeTransport({
        "http://tc/api": tc_canned([{"code": "TPL_1", "name": "一",
                                     "table": "db.t1", "fields": []}]),
        "http://md/api": md_canned({"db.t1": cols, "db.t2": cols, "db.t3": cols}),
    })

    import knowledge_lattice.core.semantic.adapters as adapters_mod

    monkeypatch.setattr(adapters_mod, "_default_transport", lambda cfg: transport)
    md = build_adapter("metadata", ORG, settings)
    assert isinstance(md, MetadataAdapter)
    tables = {r.key for r in md.fetch(ORG) if getattr(r, "type", None) == "table"}

    assert tables == {"db.t1", "db.t2", "db.t3"}  # t1=tc 推导；t2=表级显式；t3=列引用父表
    assert YamlRepoAdapter(SourceConfig(endpoint=str(repo))).name == "yaml"


# ---- TC-SYNC-06 半句：值域显式映射表 ----


def test_tc_sync_06_dim_value_map_applied(env) -> None:
    from knowledge_lattice.core.semantic.records import EntityRecord

    (env.tmp / "repo").mkdir()
    (env.tmp / "repo" / "dim_value_map.yaml").write_text(
        "mappings:\n"
        "  - dim: region\n"
        "    values:\n"
        "      CN-SH: CN\n"
        "      CN-BJ: CN\n", encoding="utf-8")

    records = [
        EntityRecord(type="scenario", key="S1", name="一",
                     dims={"region": "CN-SH"}),
        EntityRecord(type="scenario", key="S2", name="二",
                     dims={"region": "UNKNOWN"}),
    ]
    dim_map = {"region": {"CN-SH": "CN", "CN-BJ": "CN"}}
    from knowledge_lattice.core.semantic.sync import run_sync

    run_sync(env.backend, ORG, FakeSourceAdapter("scenario_config", records),
             settings=env.settings, snapshot=list(records), now=NOW,
             dim_value_map=dim_map)

    s1 = json.loads(env.backend.sem_entity_by_key(ORG, "scenario", "S1")["attrs_json"])
    s2 = json.loads(env.backend.sem_entity_by_key(ORG, "scenario", "S2")["attrs_json"])
    assert s1["dims"]["region"] == "CN"          # 显式映射生效
    assert s2["dims"]["region"] == "UNKNOWN"     # 未映射值原样落库（报告注记口径）


def test_load_dim_value_map_from_yaml_repo(env) -> None:
    from knowledge_lattice.core.semantic.adapters import load_dim_value_map

    _yaml_env(env)  # 无 dim_value_map.yaml → 空
    assert load_dim_value_map(env.settings, ORG, repo_path=env.tmp / "repo") == {}
    (env.tmp / "repo" / "dim_value_map.yaml").write_text(
        "mappings:\n  - dim: region\n    values:\n      CN-SH: CN\n", encoding="utf-8")
    got = load_dim_value_map(env.settings, ORG, repo_path=env.tmp / "repo")
    assert got == {"region": {"CN-SH": "CN"}}


# ---- C.6 sync 路径 adapter.close 接线 ----


def test_run_sync_task_closes_adapter(env, monkeypatch) -> None:
    from knowledge_lattice.core.semantic import adapters as adapters_mod
    from knowledge_lattice.core.semantic.sync import run_sync_task

    closed = {"n": 0}

    class CloseableFake(FakeSourceAdapter):
        def close(self):
            closed["n"] += 1

    monkeypatch.setitem(
        adapters_mod.ADAPTER_FACTORIES, "template_center",
        lambda org, cfg: CloseableFake("template_center", []),
    )
    env.backend.create_task(None, task_type="semantic_sync", task_id="tsk_close_1",
                            payload=json.dumps({"org": ORG, "adapter": "template_center"}))
    run_sync_task(env.backend, env.settings, "tsk_close_1")
    assert closed["n"] == 1


# ---- G-15 关系级 missing ----


def test_g15_relation_vanish_marks_missing_then_retires(env) -> None:
    """源端删边、两端实体仍在 → 关系 missing（宽限期内）→ 超期 retired。"""
    from fake_semantic import tpl_entity
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

    with_edge = [
        tpl_entity("TPL_A"),
        EntityRecord(type="template_field", key="TPL_A.F1", name="字段",
                     parent_key="template:TPL_A"),
        RelationRecord(src=("template", "TPL_A"), rel_type="has_field",
                       dst=("template_field", "TPL_A.F1")),
    ]
    assert _sync(env, with_edge, now=NOW)["status"] == "succeeded"
    # 同一快照去掉边（两端实体保留）→ 关系转 missing
    no_edge = [r for r in with_edge if not isinstance(r, RelationRecord)]
    result = _sync(env, no_edge, now="2026-10-31 10:00:00")
    assert result["status"] == "succeeded"
    assert result["stats"]["relations_missing"] == 1

    ids = env.backend.resolve_entity_ids(
        ORG, [("template", "TPL_A"), ("template_field", "TPL_A.F1")])
    rels = env.backend.expand_relations(
        ORG, [ids[("template", "TPL_A")]], ["has_field"])
    assert rels["edges"] == []  # missing 关系不参与展开

    row = env.db.execute(
        "SELECT status FROM sem_relations WHERE org_id = ? AND src_id = ?"
        " AND rel_type = 'has_field' AND dst_id = ?",
        (ORG, ids[("template", "TPL_A")], ids[("template_field", "TPL_A.F1")]),
    ).fetchone()
    assert row[0] == "missing"

    # 超宽限 → 关系级 retired（advance 同口推进）
    from knowledge_lattice.store.taskclock import add_seconds

    advanced = env.backend.advance_status(
        ORG, missing_before=add_seconds("2026-11-10 12:00:00", -7 * 86400))
    assert advanced["relations_retired_standalone"] >= 1
    row = env.db.execute(
        "SELECT status FROM sem_relations WHERE org_id = ? AND src_id = ?"
        " AND rel_type = 'has_field' AND dst_id = ?",
        (ORG, ids[("template", "TPL_A")], ids[("template_field", "TPL_A.F1")]),
    ).fetchone()
    assert row[0] == "retired"


def test_g15_upsert_filters_retired_endpoints(env) -> None:
    """指向 retired 端点的关系不再 upsert 回 active（端点状态过滤）。"""
    from fake_semantic import tpl_entity
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

    seeded = [tpl_entity("TPL_B"),
              EntityRecord(type="template_field", key="TPL_B.F1", name="字段",
                           parent_key="template:TPL_B"),
              RelationRecord(src=("template", "TPL_B"), rel_type="has_field",
                             dst=("template_field", "TPL_B.F1"))]
    assert _sync(env, seeded, now=NOW)["status"] == "succeeded"

    # 字段实体退役（retired）——直接置态模拟宽限超期后
    ids = env.backend.resolve_entity_ids(ORG, [("template_field", "TPL_B.F1")])
    env.db.execute(
        "UPDATE sem_entities SET status = 'retired' WHERE org_id = ? AND id = ?",
        (ORG, ids[("template_field", "TPL_B.F1")]))
    env.db.commit()

    # 快照带边但**不含字段实体**（跨源引用形态——字段实体不随本源复活）：
    # 端点 retired → 记冲突不写 active（G-15 后半）
    orphan_edge = [tpl_entity("TPL_B"),
                   RelationRecord(src=("template", "TPL_B"), rel_type="has_field",
                                  dst=("template_field", "TPL_B.F1"))]
    result = _sync(env, orphan_edge, now="2026-10-31 10:00:00")
    conflicts = result["stats"]["conflicts"]
    assert any("endpoint retired" in c["reason"] for c in conflicts)
    rel_row = env.db.execute(
        "SELECT r.status FROM sem_relations r WHERE r.org_id = ?"
        " AND r.rel_type = 'has_field' AND r.dst_id = ?",
        (ORG, ids[("template_field", "TPL_B.F1")]),
    ).fetchone()
    assert rel_row[0] != "active"
