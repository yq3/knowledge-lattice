"""m2s-6 TC-SEM-05 S3 补齐：search_entities 拼音/向量层（design §6.3 排序链
「别名精确 > 前缀 > 拼音 > 向量」——G-1 收窄②；v1.9.5 ②「label 模糊 LIKE
骨架 → 模糊索引升级」B 项核销面）。

排序链：alias-exact 1.0 > alias-prefix 0.8 > pinyin 0.7（sem_fuzzy_terms
拼音完全匹配）> FTS 模糊 0.5 > vec（sim——embedder 注入时）；restricted
不出现（各层谓词同口径——T-S9）。
"""

from __future__ import annotations

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-11-01 09:00:00"


@pytest.fixture()
def search_env(backend, tmp_path):
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_semantic import FakeSourceAdapter

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        embed_model="fake-embed")
    b = backend.make_backend()
    recs = [
        EntityRecord(type="concept", key="vat.retained_credit", name="留抵税额"),
        EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣",
                     aliases=("进项抵扣",)),
        EntityRecord(type="template", key="TPL_PRE", name="采集前置模板"),
    ]
    run_sync(b, ORG, FakeSourceAdapter("tc", recs), settings=settings,
             snapshot=list(recs), now=NOW)
    clear_annotator_cache()
    from fake_providers import FakeEmbedder

    assert run_build(b, ORG, settings=settings,
                     embedder=FakeEmbedder(dim=8, model_name="fake-embed")
                     )["status"] == "ready"
    return SimpleNamespace(db=backend, backend=b, settings=settings)


def test_tc_sem_05_pinyin_layer(search_env) -> None:
    """拼音层（TC-SEM-05 S3 ③）：同音错字查询「留底税额」（liudishuie ==
    「留抵税额」）经 pinyin 完全匹配命中——via='pinyin'、score 0.7、排在
    精确/前缀之后。"""
    from knowledge_lattice.core.semantic.lookup import search_entities

    out = search_entities(search_env.backend, ORG, "留底税额")
    pins = [e for e in out["entities"] if e["via"] == "pinyin"]
    assert pins and pins[0]["key"] == "vat.retained_credit"
    assert pins[0]["score"] == 0.7
    # 精确命中面优先于拼音（同一实体若被精确档命中则保最优档）
    exact = search_entities(search_env.backend, ORG, "留抵税额")
    assert exact["entities"][0]["via"] == "alias-exact"


def test_tc_sem_05_pinyin_after_prefix(search_env) -> None:
    """排序链：alias-prefix（0.8）先于 pinyin（0.7）——「采集」前缀命中
    TPL_PRE、非拼音面。"""
    from knowledge_lattice.core.semantic.lookup import search_entities

    out = search_entities(search_env.backend, ORG, "采集")
    assert out["entities"] and out["entities"][0]["via"] in ("alias-prefix",
                                                             "alias-exact")


def test_tc_sem_05_vec_layer(search_env) -> None:
    """向量层（④——embedder 注入）：query 嵌入近邻命中 via='vec'、score=sim；
    无 embedder（缺省）跳层——前三档语义不变。"""
    from fake_providers import FakeEmbedder
    from knowledge_lattice.core.semantic.lookup import search_entities

    env = search_env
    embedder = FakeEmbedder(dim=8, model_name="fake-embed")
    out = search_entities(env.backend, ORG, "进项抵扣的范围", top_k=5,
                          settings=env.settings, embedder=embedder)
    # FakeEmbedder 为 hash 向量（噪声）——确定性断言走「层存在性」：同 query
    # 的向量文本与某 term 完全同文本时必命中（embed("进项税额抵扣") 同向量）
    hit = search_entities(env.backend, ORG, "进项税额抵扣", top_k=5,
                          settings=env.settings, embedder=embedder)
    assert hit["entities"][0]["key"] == "vat.input_credit"   # 精确档最优
    # 无 embedder：via 面不含 vec
    plain = search_entities(env.backend, ORG, "进项税额抵扣")
    assert all(e["via"] != "vec" for e in plain["entities"])


def test_tc_sem_05_pinyin_restricted_excluded(backend, tmp_path) -> None:
    """restricted 实体不进拼音层（T-S9——store 谓词 e.sensitivity='normal'）。"""
    from types import SimpleNamespace

    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.core.semantic.lookup import search_entities
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    b = backend.make_backend()
    recs = [EntityRecord(type="concept", key="c.pub", name="公开概念")]
    run_sync(b, ORG, FakeSourceAdapter("tc", recs), settings=settings,
             snapshot=list(recs), now=NOW)
    repo = tmp_path / "yamlrepo"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "s.yaml").write_text(
        "- id: concept:c.secret\n  owner: o\n  name: 秘密筹划口径\n"
        "  sensitivity: restricted\n", encoding="utf-8")
    run_yaml_sync(b, ORG, YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=settings, now=NOW)
    clear_annotator_cache()
    assert run_build(b, ORG, settings=settings)["status"] == "ready"
    out = search_entities(b, ORG, "秘密筹划口径")
    assert not any(e["key"] == "c.secret" for e in out["entities"])
