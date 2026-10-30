"""TC-SYNC-01 per-org 连接解析 / TC-SYNC-02 metadata 只拉被引用（不全量镜像）。

适配器以协议测试替身验收（真实源系统不可达——HTTP 客户端形态 + 传输层注入，
环境依赖申报同 rerank 联调先例）。
"""

from __future__ import annotations

import json

import pytest

from fake_semantic import FakeTransport, md_canned, tc_canned

ORG = "org:tax"
ORG_GL = "org:gl"

NOW = "2026-10-29 12:00:00"


def _settings(sources: dict, tmp_path):
    from knowledge_lattice.config import Settings

    return Settings(
        environment="test", data_dir=tmp_path,
        semantic_sources_json=json.dumps(sources),
    )


# ---- TC-SYNC-01 per-org 连接解析 ----


def test_tc_sync_01_per_org_resolution(tmp_path) -> None:
    from knowledge_lattice.core.semantic.adapters import (
        TemplateCenterAdapter,
        resolve_source_config,
    )

    settings = _settings({
        ORG: {"template_center": {"endpoint": "http://tc.tax/api", "api_key": "k-tax",
                                  "timeout_s": 5.0}},
        "org:gl": {"template_center": {"endpoint": "http://tc.gl/api", "api_key": "k-gl"}},
    }, tmp_path)
    item = {"code": "TPL_1", "name": "模板一", "fields": []}
    transport = FakeTransport({
        "http://tc.tax/api": tc_canned([item]),
        "http://tc.gl/api": tc_canned([{**item, "code": "GL_1"}]),
    })

    a_tax = TemplateCenterAdapter(
        resolve_source_config(settings, ORG, "template_center"), transport=transport)
    a_gl = TemplateCenterAdapter(
        resolve_source_config(settings, "org:gl", "template_center"), transport=transport)
    tax_records = list(a_tax.fetch(ORG))
    gl_records = list(a_gl.fetch("org:gl"))

    # 各 org 解析各自实例（per-org 结构——#37 前置条件③）
    assert any(getattr(r, "key", None) == "TPL_1" for r in tax_records)
    assert any(getattr(r, "key", None) == "GL_1" for r in gl_records)
    tax_urls = [u for u in transport.requests if u.startswith("http://tc.tax/api")]
    gl_urls = [u for u in transport.requests if u.startswith("http://tc.gl/api")]
    assert tax_urls and gl_urls
    assert transport.requests[0].startswith("http://tc.tax/api")

    # timeout/凭证随 per-org 配置走
    assert a_tax._config.timeout_s == 5.0 and a_tax._config.api_key == "k-tax"
    assert a_gl._config.api_key == "k-gl"


def test_tc_sync_01_unconfigured_org_raises(tmp_path) -> None:
    """未配置 org 报配置错误——不静默跳过（TC-SYNC-01 后半句）。"""
    from knowledge_lattice.core.semantic.adapters import (
        SemanticSourceNotConfigured,
        resolve_source_config,
    )

    settings = _settings({ORG: {"template_center": {"endpoint": "http://tc/api"}}},
                         tmp_path)
    with pytest.raises(SemanticSourceNotConfigured):
        resolve_source_config(settings, "org:hr", "template_center")
    # org 配了但适配器没配 → 同为配置错误
    with pytest.raises(SemanticSourceNotConfigured):
        resolve_source_config(settings, ORG, "metadata")


def test_semantic_sources_json_malformed_fails_closed(tmp_path) -> None:
    from knowledge_lattice.config import Settings

    settings = Settings(environment="test", data_dir=tmp_path,
                        semantic_sources_json="{not-json")
    with pytest.raises(ValueError):
        _ = settings.semantic_sources


# ---- TC-SYNC-02 metadata 只拉被引用 ----


TC_SNAPSHOT = [
    # template_center 快照：模板 + 字段 + backed_by→t1 + maps_to→t1.c1
    ("template", "TPL_1"), ("template_field", "TPL_1.F1"),
]


def test_derive_refs_from_snapshot_relation_records() -> None:
    """引用面从本次同步快照的 RelationRecord 推导（backed_by/maps_to 的 dst）。"""
    from knowledge_lattice.core.semantic.adapters import derive_refs
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

    records = [
        EntityRecord(type="template", key="TPL_1", name="模板一"),
        EntityRecord(type="template_field", key="TPL_1.F1", name="字段一"),
        RelationRecord(src=("template", "TPL_1"), rel_type="backed_by",
                       dst=("table", "ods.t1")),
        RelationRecord(src=("template_field", "TPL_1.F1"), rel_type="maps_to",
                       dst=("column", "ods.t1.tax_amt")),
        RelationRecord(src=("template", "TPL_1"), rel_type="has_field",
                       dst=("template_field", "TPL_1.F1")),  # 非引用关系——不入引用面
    ]
    assert derive_refs(records) == {("table", "ods.t1"), ("column", "ods.t1.tax_amt")}


def test_tc_sync_02_metadata_pulls_referenced_only(backend, tmp_path) -> None:
    """源端 t1（被引用）+ t2/t3（未被引用）→ 只拉 t1 的 table/column 节点与
    has_column 关系——不做全量镜像（FR-S1）。"""
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.adapters import (
        MetadataAdapter,
        derive_refs,
    )
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_semantic import FakeSourceAdapter
    from helpers import seed_org

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    b = backend.make_backend()

    # ① template_center 同步：backed_by/maps_to 指向 t1（端点未落库 → 记冲突）
    tc_records = [
        EntityRecord(type="template", key="TPL_1", name="模板一"),
        EntityRecord(type="template_field", key="TPL_1.F1", name="字段一",
                     parent_key="template:TPL_1"),
        RelationRecord(src=("template", "TPL_1"), rel_type="has_field",
                       dst=("template_field", "TPL_1.F1")),
        RelationRecord(src=("template", "TPL_1"), rel_type="backed_by",
                       dst=("table", "ods.t1")),
        RelationRecord(src=("template_field", "TPL_1.F1"), rel_type="maps_to",
                       dst=("column", "ods.t1.tax_amt")),
    ]
    r1 = run_sync(b, ORG, FakeSourceAdapter("template_center", tc_records),
                  settings=settings, snapshot=tc_records, now=NOW)
    assert r1["status"] == "succeeded"
    assert len(r1["stats"]["conflicts"]) == 2  # t1/c1 端点尚不存在——冲突留痕

    # ② metadata 同步：引用面 = ① 快照的 RelationRecord 推导
    refs = derive_refs(tc_records)
    md_config_canned = md_canned({
        "ods.t1": {"name": "进项发票表", "columns": [
            {"name": "tax_amt", "type": "DECIMAL", "comment": "税额"},
            {"name": "inv_no", "type": "TEXT", "comment": "发票号"},
        ]},
        "ods.t2": {"name": "未引用表", "columns": [{"name": "x", "type": "TEXT"}]},
        "ods.t3": {"name": "未引用表2", "columns": [{"name": "y", "type": "TEXT"}]},
    })
    transport = FakeTransport({"http://md/api": md_config_canned})

    from knowledge_lattice.core.semantic.adapters import SourceConfig

    md = MetadataAdapter(
        SourceConfig(endpoint="http://md/api", api_key=None, timeout_s=10.0),
        refs=refs, transport=transport)
    r2 = run_sync(b, ORG, md, settings=settings, now=NOW)
    assert r2["status"] == "succeeded"

    keys = {r[0] for r in backend.execute("SELECT key FROM sem_entities").fetchall()}
    assert "ods.t1" in keys and "ods.t1.tax_amt" in keys and "ods.t1.inv_no" in keys
    assert "ods.t2" not in keys and "ods.t3" not in keys  # 不做全量镜像
    assert "ods.t2.x" not in keys and "ods.t3.y" not in keys
    # 只请求了被引用的表（t2/t3 零请求）
    assert all("/tables/ods.t1" in u for u in transport.requests)
    assert len(transport.requests) == 1

    # has_column 关系落库（table→column 白名单）
    rels = backend.execute(
        "SELECT rel_type, count(*) FROM sem_relations GROUP BY rel_type"
    ).fetchall()
    assert dict(rels)["has_column"] == 2

    # ③ 二次 template_center 同步：t1/c1 已在库 → backed_by/maps_to 关系落地
    #   （引用面驱动的两适配器接力——冷启动冲突在 metadata 落库后自动消解）
    r3 = run_sync(b, ORG, FakeSourceAdapter("template_center", tc_records),
                  settings=settings, snapshot=tc_records, now=NOW)
    assert r3["status"] == "succeeded"
    assert r3["stats"]["conflicts"] == []
    rels2 = dict(backend.execute(
        "SELECT rel_type, count(*) FROM sem_relations GROUP BY rel_type"
    ).fetchall())
    assert rels2["backed_by"] == 1 and rels2["maps_to"] == 1


def test_template_center_adapter_paging(tmp_path) -> None:
    """template_center HTTP 形态：分页拼全量（next_cursor 翻页）——P3-6② 名实
    对齐（本用例测 tc 分页，非 metadata）。"""
    from knowledge_lattice.core.semantic.adapters import TemplateCenterAdapter

    pages = {
        ("GET", "/templates"): {"items": [{"code": "P1", "name": "页一", "fields": []}],
                                "next_cursor": "c2"},
    }

    class PagingTransport:
        def __init__(self) -> None:
            self.calls: list[dict | None] = []

        def __call__(self, endpoint, path, params=None):
            self.calls.append(params)
            if params and params.get("cursor") == "c2":
                return {"items": [{"code": "P2", "name": "页二", "fields": []}],
                        "next_cursor": None}
            return pages[("GET", "/templates")]

    from knowledge_lattice.core.semantic.adapters import SourceConfig

    adapter = TemplateCenterAdapter(
        SourceConfig(endpoint="http://tc/api", api_key=None, timeout_s=10.0),
        transport=PagingTransport())
    keys = [r.key for r in adapter.fetch(ORG) if hasattr(r, "key")]
    assert keys == ["P1", "P2"]


# ---- P3-6③：build_adapter 默认分支套件（无注册覆盖——默认工厂 + per-org 解析） ----


def _patch_default_transport(monkeypatch, transport) -> None:
    """替换默认 HTTP 传输（build_adapter 默认分支不触网——工厂内部延迟导入，
    补丁在构造时生效）。"""
    from knowledge_lattice.core.semantic import adapters as sem_adapters

    monkeypatch.setattr(sem_adapters, "_default_transport", lambda cfg: transport)


def test_p3_6_build_adapter_default_tc_per_org(tmp_path, monkeypatch) -> None:
    """默认 tc 工厂：per-org 实例解析（build_adapter → resolve_source_config——
    各 org 打到各自 endpoint）。"""
    from knowledge_lattice.core.semantic.adapters import build_adapter

    settings = _settings({
        ORG: {"template_center": {"endpoint": "http://tc.tax/api"}},
        "org:gl": {"template_center": {"endpoint": "http://tc.gl/api"}},
    }, tmp_path)
    transport = FakeTransport({
        "http://tc.tax/api": tc_canned([{"code": "TPL_T", "name": "税模板", "fields": []}]),
        "http://tc.gl/api": tc_canned([{"code": "GL_T", "name": "总账模板", "fields": []}]),
    })
    _patch_default_transport(monkeypatch, transport)

    a_tax = build_adapter("template_center", ORG, settings)
    a_gl = build_adapter("template_center", "org:gl", settings)
    assert any(getattr(r, "key", None) == "TPL_T" for r in a_tax.fetch(ORG))
    assert any(getattr(r, "key", None) == "GL_T" for r in a_gl.fetch("org:gl"))
    assert any(u.startswith("http://tc.tax/api") for u in transport.requests)
    assert any(u.startswith("http://tc.gl/api") for u in transport.requests)


def test_p3_6_build_adapter_default_metadata_derives_refs(tmp_path, monkeypatch) -> None:
    """默认 metadata 工厂：引用面从 template_center 快照推导（fetch tc →
    derive_refs → 只拉被引用表——tc 冷启动冲突面自动进引用面）。"""
    from knowledge_lattice.core.semantic.adapters import build_adapter

    settings = _settings({
        ORG: {
            "template_center": {"endpoint": "http://tc/api"},
            "metadata": {"endpoint": "http://md/api"},
        },
    }, tmp_path)
    transport = FakeTransport({
        "http://tc/api": tc_canned([{
            "code": "TPL_1", "name": "模板一", "table": "ods.t1",
            "fields": [{"code": "F1", "name": "字段一", "column": "ods.t1.c1"}],
        }]),
        "http://md/api": md_canned({
            "ods.t1": {"name": "表一", "columns": [{"name": "c1", "type": "TEXT"}]},
            "ods.t9": {"name": "未引用", "columns": [{"name": "x", "type": "TEXT"}]},
        }),
    })
    _patch_default_transport(monkeypatch, transport)

    md = build_adapter("metadata", ORG, settings)
    records = list(md.fetch(ORG))
    keys = {getattr(r, "key", None) for r in records}
    assert "ods.t1" in keys and "ods.t1.c1" in keys
    assert "ods.t9" not in keys  # 引用面外不拉
    assert all("/tables/ods.t1" in u for u in transport.requests
               if u.startswith("http://md"))  # md 只请求被引用表


def test_p3_6_build_adapter_metadata_without_tc_config_warns(tmp_path, monkeypatch, caplog) -> None:
    """N4 场景固化：tc 未配置 org 时 metadata 不炸——引用面空 + WARNING、
    fetch 空转（首轮 succeeded 0 条属冷启动合法态——TC-SYNC-02 v1.9.1 注记）。"""
    from knowledge_lattice.core.semantic.adapters import build_adapter

    settings = _settings({ORG: {"metadata": {"endpoint": "http://md/api"}}}, tmp_path)
    transport = FakeTransport({"http://md/api": md_canned({
        "ods.t1": {"name": "表一", "columns": [{"name": "c1", "type": "TEXT"}]},
    })})
    _patch_default_transport(monkeypatch, transport)

    with caplog.at_level("WARNING"):
        md = build_adapter("metadata", ORG, settings)
        records = list(md.fetch(ORG))
    assert records == []  # 引用面空 → 零拉取（不做全量镜像）
    assert any("template_center not configured" in rec.message for rec in caplog.records)
    assert not [u for u in transport.requests if u.startswith("http://md")]
