"""TC-YAML-01 合并正路 / TC-YAML-02 冲突与拦截规则（合并规则表逐行）/ T-S1 YAML
场景（curated 与事实列分工）/ G-17（YAML 改 definition 必触发重建）。

驱动面：YamlRepoAdapter + run_yaml_sync（yaml 源走既有 sync 流程——T-S2/T-S4/
白名单触发器复用；curated 合并经 post_run 挂钩同 run 留痕）。
"""

from __future__ import annotations

import json

import pytest

from fake_semantic import FakeSourceAdapter, tpl_entity
from helpers import seed_org
from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"

TC_SNAPSHOT = [
    tpl_entity("TPL_VAT_INPUT", name="模板TPL_VAT_INPUT"),
    EntityRecord(type="template_field", key="TPL_VAT_INPUT.F1", name="字段一",
                 parent_key="template:TPL_VAT_INPUT"),
    RelationRecord(src=("template", "TPL_VAT_INPUT"), rel_type="has_field",
                   dst=("template_field", "TPL_VAT_INPUT.F1")),
]

CONCEPTS = """\
- id: concept:vat.input_credit
  name: 进项税额抵扣
  aliases: [进项抵扣]
  abbr: [JXDK]
  definition: 从销项税额中抵减的进项税额。
  owner: tax-domain
  refers_to: [template:TPL_VAT_INPUT]
  l0: true
"""

OVERLAY = """\
- id: template:TPL_VAT_INPUT
  owner: tax-domain
  aliases: [进项采集模板]
  definition: 月度进项发票采集模板。
  fields:
    - id: template_field:TPL_VAT_INPUT.F1
      aliases: [进项字段]
      definition: 字段一说明
"""


def _write_repo(repo, *, concepts=CONCEPTS, overlay=OVERLAY):
    (repo / "concepts").mkdir(exist_ok=True)
    (repo / "concepts" / "vat.yaml").write_text(concepts, encoding="utf-8")
    if overlay is not None:
        (repo / "templates").mkdir(exist_ok=True)
        (repo / "templates" / "t.yaml").write_text(overlay, encoding="utf-8")


@pytest.fixture()
def yenv(backend, tmp_path):
    """双臂环境：org + template_center 已同步（overlay 目标实体在场）。"""
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.sync import run_sync

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    backend.make_backend()  # 触发连接纪律断言（双臂同构）
    run_sync(backend.make_backend(), ORG,
             FakeSourceAdapter("template_center", TC_SNAPSHOT),
             settings=settings, snapshot=list(TC_SNAPSHOT), now=NOW)
    repo = tmp_path / "yamlrepo"
    repo.mkdir()
    _write_repo(repo)
    return SimpleNamespace(db=backend, backend=backend.make_backend(),
                           settings=settings, repo=repo)


def _yaml_sync(env, *, force=False, now=NOW):
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    adapter = YamlRepoAdapter(SourceConfig(endpoint=str(env.repo)))
    return run_yaml_sync(env.backend, ORG, adapter,
                         settings=env.settings, now=now, force=force)


def _entity(env, eid: str):
    etype, _, key = eid.partition(":")
    return env.backend.sem_entity_by_key(ORG, etype, key)


def _curated(env, eid: str) -> dict:
    row = _entity(env, eid)
    return json.loads(row["curated_json"] or "{}")


# ---- TC-YAML-01 合并正路 ----


def test_tc_yaml_01_merge_happy_path(yenv) -> None:
    result = _yaml_sync(yenv)
    assert result["status"] == "succeeded"

    # 覆盖层挂到已同步实体：curated_json + curated_rev（记 YAML rev）
    tpl = _entity(yenv, "template:TPL_VAT_INPUT")
    assert _curated(yenv, "template:TPL_VAT_INPUT")["definition"] == "月度进项发票采集模板。"
    assert tpl["curated_rev"]
    # 字段覆盖层同样落 curated
    assert _curated(yenv, "template_field:TPL_VAT_INPUT.F1")["definition"] == "字段一说明"
    # manual/abbr 别名写入（kind 区分——同步三 kind 不动）
    aliases = yenv.backend.sem_entity_aliases(ORG, [tpl["id"]])
    kinds = {a["alias"]: a["kind"] for a in aliases}
    assert kinds.get("进项采集模板") == "manual"
    assert kinds.get("模板TPL_VAT_INPUT") == "name"  # 事实列别名原样
    # 纯人工实体（仅 concept/system 可建）：source='curated'
    concept = _entity(yenv, "concept:vat.input_credit")
    assert concept is not None and concept["source"] == "curated"
    assert _curated(yenv, "concept:vat.input_credit")["definition"] == "从销项税额中抵减的进项税额。"
    cal = yenv.backend.sem_entity_aliases(ORG, [concept["id"]])
    cal_kinds = {a["alias"]: a["kind"] for a in cal}
    assert cal_kinds.get("进项抵扣") == "manual"
    assert cal_kinds.get("JXDK") == "abbr"
    # refers_to 关系（source='curated'）
    rels = yenv.backend.expand_relations(ORG, [concept["id"]], ["refers_to"])
    assert rels["edges"], "refers_to 关系应写入"


def test_tc_yaml_01_stats_carry_curated_section(yenv) -> None:
    result = _yaml_sync(yenv)
    curated = result["stats"]["curated"]
    assert curated["entities_written"] >= 3  # concept + template + field
    assert curated["conflicts"] == []


# ---- TC-YAML-02 规则表逐行 ----


def test_rule_unsynced_id_not_written_conflict_then_recovers(yenv) -> None:
    """未同步 id → 不写入记冲突；实体恢复后自动生效（补恢复断言）。"""
    (yenv.repo / "templates" / "ghost.yaml").write_text(
        "- id: template:TPL_GHOST\n  owner: o\n  aliases: [幽灵模板]\n"
        "  definition: 未同步模板\n", encoding="utf-8")
    result = _yaml_sync(yenv)
    conflicts = result["stats"]["curated"]["conflicts"]
    assert any(c["id"] == "template:TPL_GHOST" for c in conflicts)
    assert _entity(yenv, "template:TPL_GHOST") is None  # 不写入
    # 恢复：template_center 补上该模板 → 再合并自动生效
    from knowledge_lattice.core.semantic.sync import run_sync

    snapshot = [*TC_SNAPSHOT, tpl_entity("TPL_GHOST")]
    run_sync(yenv.backend, ORG, FakeSourceAdapter("template_center", snapshot),
             settings=yenv.settings, snapshot=list(snapshot), now=NOW)
    _yaml_sync(yenv)
    assert _curated(yenv, "template:TPL_GHOST")["definition"] == "未同步模板"


# B4①/m2s-4：旧 test_rule_pure_collides_with_synced_entity（仅断言 source 列）
# 已删——强用例 test_p2_2_colliding_pure_entry_leaves_sync_entity_untouched
# （test_r2_m2s3_fixes.py：name/attrs/source_system/status/三类别名逐列不变）
# 全覆盖弱断言面。


def test_rule_short_or_common_alias_skipped_with_conflict(yenv) -> None:
    """合并侧 fail-closed：短词/常用词别名（未标 context/fuzzy_only）不写入。"""
    (yenv.repo / "templates" / "short.yaml").write_text(
        "- id: template:TPL_VAT_INPUT\n  owner: o\n"
        "  aliases: [短, 进项采集模板]\n  definition: d\n", encoding="utf-8")
    result = _yaml_sync(yenv)
    curated = result["stats"]["curated"]
    assert any("short" in c["reason"] or "common" in c["reason"] for c in curated["conflicts"])
    tpl = _entity(yenv, "template:TPL_VAT_INPUT")
    aliases = {a["alias"] for a in yenv.backend.sem_entity_aliases(ORG, [tpl["id"]])}
    assert "短" not in aliases and "进项采集模板" in aliases


def test_rule_extra_relation_duplicate_of_sync(yenv) -> None:
    """extra_relations 与同步关系重复 → 以同步为准、提示可删（规则表第 6 行）。"""
    # TC_SNAPSHOT 含 has_field: template:TPL_VAT_INPUT → template_field:TPL_VAT_INPUT.F1
    (yenv.repo / "templates" / "extra.yaml").write_text(
        "- id: template:TPL_VAT_INPUT\n  owner: o\n  definition: d\n"
        "  extra_relations:\n"
        "    - rel: has_field\n"
        "      from: template:TPL_VAT_INPUT\n"
        "      to: template_field:TPL_VAT_INPUT.F1\n", encoding="utf-8")
    result = _yaml_sync(yenv)
    conflicts = result["stats"]["curated"]["conflicts"]
    assert any("duplicate of sync relation" in c["reason"] for c in conflicts)
    rels = yenv.backend.expand_relations(ORG, [_entity(yenv, "template:TPL_VAT_INPUT")["id"]], ["has_field"])
    assert all(e.get("source") != "curated" for e in rels["edges"])


def test_rule_extra_relation_whitelist_violation(yenv) -> None:
    (yenv.repo / "templates" / "bad_rel.yaml").write_text(
        "- id: template:TPL_VAT_INPUT\n  owner: o\n  definition: d\n"
        "  extra_relations:\n"
        "    - rel: uses\n"
        "      from: template:TPL_VAT_INPUT\n"
        "      to: template_field:TPL_VAT_INPUT.F1\n", encoding="utf-8")
    result = _yaml_sync(yenv)
    conflicts = result["stats"]["curated"]["conflicts"]
    assert any("whitelist" in c["reason"] for c in conflicts)


def test_rule_yaml_delete_clears_curated_only(yenv) -> None:
    """YAML 删除覆盖项 → 清 curated_json 与 manual 别名；事实列不受影响。"""
    assert _yaml_sync(yenv)["status"] == "succeeded"
    (yenv.repo / "templates" / "t.yaml").unlink()
    result = _yaml_sync(yenv)
    assert result["status"] == "succeeded"
    tpl = _entity(yenv, "template:TPL_VAT_INPUT")
    assert json.loads(tpl["curated_json"] or "{}") == {}
    assert tpl["curated_rev"] is None
    aliases = {a["alias"]: a["kind"] for a in yenv.backend.sem_entity_aliases(ORG, [tpl["id"]])}
    assert "进项采集模板" not in aliases
    assert aliases.get("模板TPL_VAT_INPUT") == "name"  # 事实列别名原样
    assert tpl["name"] == "模板TPL_VAT_INPUT"  # 事实列不动


# ---- T-S1（YAML 场景验收句）----


def test_t_s1_sync_does_not_overwrite_curated(yenv) -> None:
    """YAML 写入 definition 与 manual 别名后，源端改 name 再同步——curated_json
    与 manual 别名不变、name 更新（T-S1 列级分工）。"""
    assert _yaml_sync(yenv)["status"] == "succeeded"
    changed = [
        tpl_entity("TPL_VAT_INPUT", name="进项模板（改名）"),
        EntityRecord(type="template_field", key="TPL_VAT_INPUT.F1", name="字段一",
                     parent_key="template:TPL_VAT_INPUT"),
        RelationRecord(src=("template", "TPL_VAT_INPUT"), rel_type="has_field",
                       dst=("template_field", "TPL_VAT_INPUT.F1")),
    ]
    from knowledge_lattice.core.semantic.sync import run_sync

    run_sync(yenv.backend, ORG, FakeSourceAdapter("template_center", changed),
             settings=yenv.settings, snapshot=list(changed), now="2026-10-31 10:00:00")
    tpl = _entity(yenv, "template:TPL_VAT_INPUT")
    assert tpl["name"] == "进项模板（改名）"  # 事实列更新
    assert _curated(yenv, "template:TPL_VAT_INPUT")["definition"] == "月度进项发票采集模板。"
    aliases = {a["alias"]: a["kind"] for a in yenv.backend.sem_entity_aliases(ORG, [tpl["id"]])}
    assert aliases.get("进项采集模板") == "manual"  # manual 别名原样


# ---- G-17：YAML 改 definition 必触发重建 ----


def test_g17_definition_change_triggers_new_dict_rev(yenv) -> None:
    from knowledge_lattice.core.semantic.build import run_build

    assert _yaml_sync(yenv)["status"] == "succeeded"
    r1 = run_build(yenv.backend, ORG, settings=yenv.settings)
    assert r1["status"] == "ready"
    rev1 = r1["dict_rev"]

    (yenv.repo / "templates" / "t.yaml").write_text(
        OVERLAY.replace("月度进项发票采集模板。", "月度进项发票采集模板（口径修订版）。"),
        encoding="utf-8")
    assert _yaml_sync(yenv)["status"] == "succeeded"
    r2 = run_build(yenv.backend, ORG, settings=yenv.settings)
    assert r2["status"] == "ready"
    assert r2["dict_rev"] != rev1  # curated_json 入快照 → definition 变更必新 rev
    # yaml_rev 记录在 build 行（= corpus rev）
    build = yenv.backend.sem_get_build(ORG, r2["build_id"])
    assert build["yaml_rev"]
    # 当前构建的 yaml_rev 亦随行
    current = yenv.backend.sem_current_build(ORG)
    assert current["dict_rev"] == r2["dict_rev"] and current["yaml_rev"] == build["yaml_rev"]
