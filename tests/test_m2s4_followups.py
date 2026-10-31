"""m2s-4 收编挂账（m2s-3 移交 B2/B3/B4）：

- B2⑦ 自校验回退健壮性：JSON Schema **回退路径**（零依赖 only）对 type 数组 /
  布尔子 schema / tuple items 的 false positive 修正——合法 schema 不再被
  `_minimal_schema_self_check` 误拦、条目校验子集同口径（except 兜底不崩溃）；
- B3④ 覆盖层删除不回退最后声明 sensitivity 值——口径化（保留最后声明值，
  fail-closed 方向）+ 永久用例钉死；
- B3⑤ 非法 sensitivity 不再静默归 normal——合并侧记冲突（收紧注记）；
- B4② sem_replace_manual_aliases inserted 计数修正（ON CONFLICT 跳过行不计数）；
- B4①/B4③（弱断言删除/测试改名）见 test_yaml_02_merge.py 与
  test_build_04_current_ptr.py 改动（无新增用例）。
"""

from __future__ import annotations

import json

import pytest

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"


# ---- B2⑦：回退路径 schema 合法性检查不再误拦合法 schema ----


def _force_fallback(monkeypatch):
    import sys
    import types

    import knowledge_lattice.core.semantic.yaml_corpus as yc

    monkeypatch.setitem(sys.modules, "jsonschema", None)
    return yc


def test_b2_7_self_check_accepts_type_array(monkeypatch, tmp_path) -> None:
    """type: ["string","null"]（数组形态）是合法 schema——回退路径不误拦。"""
    yc = _force_fallback(monkeypatch)
    schema = {"type": "object", "properties": {
        "note": {"type": ["string", "null"]}}}
    assert yc._minimal_schema_self_check(schema) is None


def test_b2_7_self_check_accepts_boolean_subschema(monkeypatch) -> None:
    """布尔子 schema（true/false——允许/拒绝任何值）是合法 JSON Schema。"""
    yc = _force_fallback(monkeypatch)
    assert yc._minimal_schema_self_check(
        {"properties": {"a": True, "b": False}}) is None


def test_b2_7_self_check_accepts_tuple_items(monkeypatch) -> None:
    """items 数组形态（tuple 校验）是合法 schema——不误拦。"""
    yc = _force_fallback(monkeypatch)
    schema = {"type": "array",
              "items": [{"type": "string"}, {"type": "integer"}]}
    assert yc._minimal_schema_self_check(schema) is None


def test_b2_7_self_check_still_rejects_illegal(monkeypatch) -> None:
    """修正不放宽：未知 type / 非法 required / items 非法形态仍拦截。"""
    yc = _force_fallback(monkeypatch)
    assert yc._minimal_schema_self_check({"type": "strin"}) is not None
    assert yc._minimal_schema_self_check({"type": ["object", 1]}) is not None
    assert yc._minimal_schema_self_check(
        {"required": "id"}) is not None          # 非数组
    assert yc._minimal_schema_self_check(
        {"items": 3}) is not None                # 非对象/数组
    assert yc._minimal_schema_self_check(
        {"properties": {"x": {"type": "bogus"}}}) is not None


def test_b2_7_errors_boolean_and_tuple_semantics(monkeypatch) -> None:
    """条目校验子集同口径：true 放行 / false 拒绝 / tuple 按位校验 / type
    数组 any-of。"""
    yc = _force_fallback(monkeypatch)
    # true 子 schema：任何值合法
    assert yc._minimal_schema_errors({"a": 1}, {"properties": {"a": True}}) == []
    # false 子 schema：恒不通过
    assert yc._minimal_schema_errors({"a": 1}, {"properties": {"a": False}})
    # tuple items 按位
    errs = yc._minimal_schema_errors(
        ["x", "y"], {"items": [{"type": "string"}, {"type": "integer"}]})
    assert len(errs) == 1 and "$[1]" in errs[0]
    # type 数组 any-of
    assert yc._minimal_schema_errors(
        None, {"type": ["string", "null"]}) == []
    assert yc._minimal_schema_errors(
        3, {"type": ["string", "null"]})


def test_b2_7_malformed_schema_does_not_crash(monkeypatch) -> None:
    """畸形输入（None/循环引用外的怪形态）不崩溃——except 兜底返回可定位
    信息（fail-closed 方向不变）。"""
    yc = _force_fallback(monkeypatch)
    out = yc._minimal_schema_self_check(None)
    assert out and "对象" in out
    errs = yc._minimal_schema_errors({"a": 1}, None)
    assert errs


# ---- B3④⑤：sensitivity 两口径 ----


@pytest.fixture()
def senv(backend, tmp_path):
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_semantic import FakeSourceAdapter
    from helpers import seed_org
    from knowledge_lattice.core.semantic.records import EntityRecord

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    b = backend.make_backend()
    recs = [EntityRecord(type="template", key="TPL_1", name="模板一")]
    run_sync(b, ORG, FakeSourceAdapter("template_center", recs),
             settings=settings, snapshot=list(recs), now=NOW)
    repo = tmp_path / "yamlrepo"
    repo.mkdir()
    return SimpleNamespace(db=backend, backend=b, settings=settings, repo=repo)


def _yaml_sync(env, files: dict, *, now=NOW):
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    for rel, content in files.items():
        p = env.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    adapter = YamlRepoAdapter(SourceConfig(endpoint=str(env.repo)))
    return run_yaml_sync(env.backend, ORG, adapter,
                         settings=env.settings, now=now)


def _sensitivity(env, key: str):
    row = env.backend.sem_entity_by_key(ORG, "template", key)
    return row["sensitivity"]


def test_b3_4_overlay_delete_keeps_last_declared_sensitivity(senv) -> None:
    """口径（B3④）：覆盖层删除**不回退**最后声明 sensitivity——restricted 保留
    （fail-closed：撤回覆盖不等于解除限制；解除须重新声明 normal）。"""
    _yaml_sync(senv, {
        "templates/a.yaml":
            "- id: template:TPL_1\n  owner: o\n  sensitivity: restricted\n"
            "  definition: d\n"})
    assert _sensitivity(senv, "TPL_1") == "restricted"
    # 删除整个覆盖条目 → curated 清空，sensitivity 保留最后声明值（口径化）
    _yaml_sync(senv, {"templates/a.yaml": ""})
    row = senv.backend.sem_entity_by_key(ORG, "template", "TPL_1")
    assert json.loads(row["curated_json"] or "{}") == {}
    assert row["curated_rev"] is None
    assert _sensitivity(senv, "TPL_1") == "restricted"    # 不回退
    # 重新声明 normal 才解除（YAML 为 sensitivity 覆盖面真源）
    _yaml_sync(senv, {
        "templates/a.yaml":
            "- id: template:TPL_1\n  owner: o\n  sensitivity: normal\n"})
    assert _sensitivity(senv, "TPL_1") == "normal"


def test_b3_5_illegal_sensitivity_conflict_not_silent(senv) -> None:
    """收紧（B3⑤）：非法 sensitivity 不静默归 normal——合并面记冲突。"""
    result = _yaml_sync(senv, {
        "templates/b.yaml":
            "- id: template:TPL_1\n  owner: o\n  sensitivity: secret\n"
            "  definition: d\n"})
    conflicts = result["stats"]["curated"]["conflicts"]
    assert any("sensitivity" in c["reason"] and "secret" in c["reason"]
               for c in conflicts), conflicts
    # fail-safe 方向不变：落 normal
    assert _sensitivity(senv, "TPL_1") == "normal"


# ---- B4②：sem_replace_manual_aliases inserted 计数 ----


def test_b4_2_manual_alias_inserted_count_excludes_conflict_skips(senv) -> None:
    """ON CONFLICT DO NOTHING 跳过行不计入 inserted（stats 微瑕修正）。"""
    # 先写一条与 name 别名同 norm 的 manual 别名 → 替换时被 UNIQUE 跳过
    _yaml_sync(senv, {
        "templates/c.yaml":
            "- id: template:TPL_1\n  owner: o\n  aliases: [模板一, 人工面]\n"})
    row = senv.backend.sem_entity_by_key(ORG, "template", "TPL_1")
    # 再次整替：「模板一」与 kind=name 别名同 norm → 跳过；「人工面」正常插入
    inserted = senv.backend.sem_replace_manual_aliases(ORG, [{
        "type": "template", "key": "TPL_1",
        "aliases": [("模板一", "模板一", "manual", "exact"),
                    ("人工面", "人工面", "manual", "exact")],
    }])
    aliases = {a["alias"] for a in senv.backend.sem_entity_aliases(
        ORG, [row["id"]]) if a["kind"] == "manual"}
    assert aliases == {"人工面"}                    # 模板一被 name 别名占用
    assert inserted == 1                            # 只计真插入行
