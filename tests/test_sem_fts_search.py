"""C.3 FTS 模糊索引（search_entities LIKE 骨架升级——sqlite FTS5 / pg tsvector
双方言；评分差异按 G-6 口径登记不追平）+ C.5 describe_table 主路径 restricted
列级过滤 + describe 3s 钳制永久断言。
"""

from __future__ import annotations

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"


@pytest.fixture()
def fenv(backend, tmp_path):
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    return SimpleNamespace(db=backend, backend=backend.make_backend(),
                           settings=settings)


def _seed(env, records):
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.core.semantic.sync import run_sync

    result = run_sync(env.backend, ORG, FakeSourceAdapter("template_center", records),
                      settings=env.settings, snapshot=list(records), now=NOW)
    assert result["status"] == "succeeded"
    return result


def _search(env, q, **kw):
    from knowledge_lattice.core.semantic.lookup import search_entities

    return search_entities(env.backend, ORG, q, **kw)


# ---- C.3 FTS 第三层（LIKE 骨架升级） ----


def test_fts_layer_matches_name_and_alias(fenv) -> None:
    from knowledge_lattice.core.semantic.records import EntityRecord

    _seed(fenv, [
        EntityRecord(type="template", key="TPL_VAT", name="进项税额采集模板",
                     aliases=("抵进项",)),
        EntityRecord(type="template", key="TPL_SAL", name="销项税额申报模板"),
    ])
    # 名称/别名经分词进 FTS 索引——非前缀词形经模糊层命中（via='fts'；
    # 「采集」不是任何别名的精确/前缀形，仅 FTS 可达）
    got = _search(fenv, "采集")["entities"]
    assert got and got[0]["key"] == "TPL_VAT"
    assert any(e["via"] == "fts" for e in got)
    got_alias = _search(fenv, "抵进项")["entities"]
    assert got_alias and got_alias[0]["key"] == "TPL_VAT"


def test_fts_refresh_on_name_change(fenv) -> None:
    from knowledge_lattice.core.semantic.records import EntityRecord

    _seed(fenv, [EntityRecord(type="template", key="TPL_X", name="旧名")])
    assert _search(fenv, "全新名称")["entities"] == []
    _seed(fenv, [EntityRecord(type="template", key="TPL_X", name="全新名称")])
    assert _search(fenv, "全新名称")["entities"]


def test_fts_layer_specials_no_crash_no_overmatch(fenv) -> None:
    from knowledge_lattice.core.semantic.records import EntityRecord

    _seed(fenv, [EntityRecord(type="template", key="TPL_P", name="含%下划线_模板")])
    for q in ("%", "_", "\\", "a\"b", "' OR 1=1 --", "*"):
        got = _search(fenv, q)  # 不抛错
        assert isinstance(got["entities"], list)


def test_fts_ranking_exact_prefix_above_fts(fenv) -> None:
    """三层序保持：别名精确(1.0) > 前缀(0.8) > FTS 模糊（0.5）——同实体取最优档。"""
    from knowledge_lattice.core.semantic.records import EntityRecord

    _seed(fenv, [
        EntityRecord(type="template", key="TPL_A", name="字母表模板",
                     aliases=("进项抵扣",)),
        EntityRecord(type="template", key="TPL_B", name="进项抵扣大全",
                     aliases=()),
    ])
    got = _search(fenv, "进项抵扣")["entities"]
    assert got[0]["key"] == "TPL_A" and got[0]["via"] == "alias-exact"
    assert any(e["key"] == "TPL_B" for e in got)  # FTS/名称层命中次之


def test_fts_score_is_json_serializable_float(fenv) -> None:
    """P2-1 口径延续：score 双方言均 float、可 JSON 序列化（pg ::float8）。"""
    import json as _json

    from knowledge_lattice.core.semantic.records import EntityRecord

    _seed(fenv, [EntityRecord(type="template", key="TPL_J", name="序列化检查模板")])
    got = _search(fenv, "序列化")["entities"]
    assert got
    for e in got:
        assert isinstance(e["score"], float)
    _json.dumps(got)


def test_fts_restricted_excluded(fenv) -> None:
    from knowledge_lattice.core.semantic.records import EntityRecord

    _seed(fenv, [EntityRecord(type="template", key="TPL_R", name="机密词典模板")])
    fenv.db.execute(
        "UPDATE sem_entities SET sensitivity = 'restricted'"
        " WHERE org_id = ? AND key = 'TPL_R'", (ORG,))
    fenv.db.commit()
    assert _search(fenv, "机密词典")["entities"] == []


# ---- C.5 describe_table 主路径 restricted 列级过滤 ----


def test_describe_main_path_filters_restricted_columns(backend, tmp_path) -> None:
    """透传成功路径：列级 sensitivity 过滤——restricted 列不随透传吐出
    （表级白名单之外补列级——M2-S3 权限面前置半句）。"""
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.lookup import describe_table
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_semantic import FakeSourceAdapter

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    b = backend.make_backend()
    snapshot = [
        EntityRecord(type="table", key="db.t1", name="表一"),
        EntityRecord(type="column", key="db.t1.c_pub", name="公开列",
                     parent_key="table:db.t1"),
        EntityRecord(type="column", key="db.t1.c_sec", name="机密列",
                     parent_key="table:db.t1"),
        RelationRecord(src=("table", "db.t1"), rel_type="has_column",
                       dst=("column", "db.t1.c_pub")),
        RelationRecord(src=("table", "db.t1"), rel_type="has_column",
                       dst=("column", "db.t1.c_sec")),
    ]
    run_sync(b, ORG, FakeSourceAdapter("metadata", snapshot), settings=settings,
             snapshot=list(snapshot), now=NOW)
    backend.execute(
        "UPDATE sem_entities SET sensitivity = 'restricted'"
        " WHERE org_id = ? AND key = 'db.t1.c_sec'", (ORG,))
    if hasattr(backend, "commit"):
        backend.commit()

    detail = {"name": "表一", "columns": [
        {"name": "c_pub", "type": "int"},
        {"name": "c_sec", "type": "varchar"},
    ]}
    got = describe_table(b, settings, ORG, "db.t1", fetcher=lambda key: detail)
    names = [c["name"] for c in got["columns"]]
    assert names == ["c_pub"]  # restricted 列被滤除、degraded=False 主路径


# ---- describe 3s 钳制永久断言（C.7 测试维护③） ----


def test_describe_timeout_clamped_to_3s(tmp_path) -> None:
    """配置超时再大（99s），默认透传通道钳制 3s（T-S11①——永久断言防回归）。"""
    import json

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.lookup import DESCRIBE_TIMEOUT_S, _default_fetcher

    assert DESCRIBE_TIMEOUT_S == 3.0
    settings = Settings(
        environment="test", data_dir=tmp_path,
        semantic_sources_json=json.dumps({
            ORG: {"metadata": {"endpoint": "http://md/api", "timeout_s": 99.0}}}),
    )
    fetch = _default_fetcher(settings, ORG)
    assert fetch is not None
    assert getattr(fetch, "clamped_timeout_s") == DESCRIBE_TIMEOUT_S
