"""m2s-3 R2 修复批（R1 Committer P2×2 + 边界 1〔JSON Schema〕+ 边界 4〔L0/owner〕
+ N2/N3 + P3 顺手项）——逐条回归。

- P2-1 合并面完整语义：corpus 每个 active 目标产一行（payload 空写 {}、别名空
  产出行执行先删后插清空）；stale 清理只管条目整体消失；
- P2-2 同键冲突同步实体保护：curated 源实体写入前剔除既有 sync 键（规则表第
  3 行——同步实体 name/attrs/source_system/三类别名不动）；
- 边界 1（升 P2）：_schema/entry.schema.json 按条目 JSON Schema 校验；
- 边界 4：l0/owner 入 curated_json（m2s-4 L0 导出/构建报告数据源）；
- P3-1/2/3/4·5/7/8/10·11 + N2/N3 见各用例 docstring。
"""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from fake_semantic import FakeSourceAdapter, tpl_entity
from helpers import seed_org

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"

CONCEPTS = """\
- id: concept:vat.input_credit
  name: 进项税额抵扣
  owner: tax-domain
  definition: 从销项税额中抵减的进项税额。
  aliases: [进项抵扣]
  abbr: [JXDK]
  l0: true
  refers_to: [template:TPL_1]
"""

OVERLAY_ALIASES_ONLY = """\
- id: template:TPL_1
  owner: tax-domain
  aliases: [进项采集模板]
"""


@pytest.fixture()
def env(backend, tmp_path):
    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    # 模板实体在场（覆盖层目标）
    from knowledge_lattice.core.semantic.sync import run_sync

    run_sync(backend.make_backend(), ORG,
             FakeSourceAdapter("template_center", [tpl_entity("TPL_1")]),
             settings=settings, snapshot=[tpl_entity("TPL_1")], now=NOW)
    repo = tmp_path / "repo"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "c.yaml").write_text(CONCEPTS, encoding="utf-8")
    (repo / "templates").mkdir()
    (repo / "templates" / "t.yaml").write_text(OVERLAY_ALIASES_ONLY, encoding="utf-8")
    return SimpleNamespace(db=backend, backend=backend.make_backend(),
                           settings=settings, repo=repo)


def _merge(env, **kw):
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    return run_yaml_sync(env.backend, ORG,
                         YamlRepoAdapter(SourceConfig(endpoint=str(env.repo))),
                         settings=env.settings, **kw)


def _entity(env, eid: str):
    etype, _, key = eid.partition(":")
    return env.backend.sem_entity_by_key(ORG, etype, key)


def _curated(env, eid: str) -> dict:
    return json.loads(_entity(env, eid)["curated_json"] or "{}")


def _manual_norms(env, eid: str) -> set[str]:
    row = _entity(env, eid)
    from knowledge_lattice.core.semantic.norm import normalize_alias

    return {
        normalize_alias(a["alias"])
        for a in env.backend.sem_entity_aliases(ORG, [row["id"]])
        if a["kind"] in ("manual", "abbr")
    }


# ---- P2-1：合并面完整语义（规则表第 1 行无 payload 前置） ----


def test_p2_1_alias_only_overlay_writes_and_clears(env) -> None:
    """① alias-only 覆盖层：manual 别名写入 + curated_rev 记录（curated_json
    空亦产出行——payload {}）。"""
    result = _merge(env)
    assert result["status"] == "succeeded"
    tpl = _entity(env, "template:TPL_1")
    assert tpl["curated_rev"], "alias-only 条目同样记录 curated_rev"
    # curated 面仅剩 owner（b4 口径——payload 空亦产出行）；无 definition 等内容字段
    assert _curated(env, "template:TPL_1") == {"owner": "tax-domain"}
    from knowledge_lattice.core.semantic.norm import normalize_alias

    assert normalize_alias("进项采集模板") in _manual_norms(env, "template:TPL_1")


def test_p2_1_delete_aliases_clears_old_manual(env) -> None:
    """② 既有条目删空别名（保留 definition）→ 先删后插清空旧 manual/abbr。
    R3：补前序 merge（带别名）——R1 缺陷代码下无旧别名可清，空转修复。"""
    (env.repo / "templates" / "t.yaml").write_text(
        "- id: template:TPL_1\n  owner: tax-domain\n"
        "  definition: 第一版定义\n  aliases: [进项采集模板, {value: 抵扣项, match_mode: context}]\n"
        "  abbr: [JXDK]\n", encoding="utf-8")
    assert _merge(env)["status"] == "succeeded"
    assert _manual_norms(env, "template:TPL_1"), "前置：旧 manual/abbr 在场"

    (env.repo / "templates" / "t.yaml").write_text(
        "- id: template:TPL_1\n  owner: tax-domain\n"
        "  definition: 只有定义没有别名\n", encoding="utf-8")
    assert _merge(env)["status"] == "succeeded"
    assert _manual_norms(env, "template:TPL_1") == set(), "删空别名须清空旧 manual/abbr"
    assert _curated(env, "template:TPL_1")["definition"] == "只有定义没有别名"


def test_p2_1_delete_definition_rewrites_payload(env) -> None:
    """③ 删 definition（条目保留、别名保留）→ curated_json 按当前 corpus 重写
    （旧 definition 不残留）。"""
    (env.repo / "templates" / "t.yaml").write_text(
        "- id: template:TPL_1\n  owner: tax-domain\n"
        "  definition: 第一版定义\n  aliases: [进项采集模板]\n", encoding="utf-8")
    assert _merge(env)["status"] == "succeeded"
    assert _curated(env, "template:TPL_1")["definition"] == "第一版定义"

    (env.repo / "templates" / "t.yaml").write_text(
        "- id: template:TPL_1\n  owner: tax-domain\n"
        "  aliases: [进项采集模板]\n", encoding="utf-8")
    assert _merge(env)["status"] == "succeeded"
    assert "definition" not in _curated(env, "template:TPL_1"), \
        "条目仍在场（非整体消失）→ payload 按当前 corpus 重写，旧 definition 清除"
    assert _manual_norms(env, "template:TPL_1")  # 别名保留


def test_p2_1_stale_clear_still_entry_scoped(env) -> None:
    """stale 清理仍只管条目整体消失：删除 t.yaml 条目 → curated 清空+别名清空。"""
    assert _merge(env)["status"] == "succeeded"
    (env.repo / "templates" / "t.yaml").unlink()
    assert _merge(env)["status"] == "succeeded"
    tpl = _entity(env, "template:TPL_1")
    assert json.loads(tpl["curated_json"] or "{}") == {}
    assert tpl["curated_rev"] is None
    assert _manual_norms(env, "template:TPL_1") == set()


# ---- P2-2：同键冲突——同步实体在冲突判定前不被覆盖 ----


def test_p2_2_colliding_pure_entry_leaves_sync_entity_untouched(env) -> None:
    """规则表第 3 行实际保护面：sync 概念实体的 name/attrs/source_system/status
    与 name/code/sync 三类别名原样；冲突记 stats（entity_conflicts + curated
    conflicts 双面）；YAML 侧 manual 别名与 curated 不写入。"""
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync

    synced = [EntityRecord(type="concept", key="dup.key", name="同步概念",
                           aliases=("同步别名",), attrs={"code": "DK"})]
    run_sync(env.backend, ORG, FakeSourceAdapter("scenario_config", synced),
             settings=env.settings, snapshot=list(synced), now=NOW)
    before = _entity(env, "concept:dup.key")

    (env.repo / "concepts" / "dup.yaml").write_text(
        "- id: concept:dup.key\n  name: 人工概念\n  owner: o\n"
        "  aliases: [人工别名]\n  definition: 不应写入\n", encoding="utf-8")
    result = _merge(env)
    assert result["status"] == "succeeded"

    after = _entity(env, "concept:dup.key")
    assert after["name"] == before["name"] == "同步概念", "同步实体 name 不被覆盖"
    assert after["attrs_json"] == before["attrs_json"]
    assert after["source_system"] == before["source_system"] == "scenario_config"
    assert after["source"] == "sync"
    assert after["status"] == "active"
    # 三类别名原样（name/code/sync 仍是同步重建面）；YAML manual 别名不在场
    from knowledge_lattice.core.semantic.norm import normalize_alias

    alias_kinds = {a["alias"]: a["kind"]
                   for a in env.backend.sem_entity_aliases(ORG, [after["id"]])}
    assert alias_kinds.get("同步概念") == "name"
    assert alias_kinds.get("dup.key") == "code"
    assert alias_kinds.get("同步别名") == "sync"
    assert normalize_alias("人工别名") not in _manual_norms(env, "concept:dup.key")
    assert _curated(env, "concept:dup.key") == {}
    # 冲突双面留痕
    assert any("collides with synced entity" in c["reason"]
               for c in result["stats"]["entity_conflicts"])
    assert any("collides with synced entity" in c["reason"]
               for c in result["stats"]["curated"]["conflicts"])

    # R3/误 retire 链永久断言：删除冲突 YAML 条目后再跑 yaml sync——冲突键
    # 从未进入 yaml 基数（预过滤先于 upsert）→ 不标 missing，同步实体仍 active
    (env.repo / "concepts" / "dup.yaml").unlink()
    result2 = _merge(env)
    assert result2["status"] == "succeeded"
    assert result2["stats"]["missing"] == 0, "同步实体不得因 YAML 删条目被误标 missing"
    assert _entity(env, "concept:dup.key")["status"] == "active"


# ---- 边界 1（升 P2）：_schema JSON Schema 条目级校验 ----


def test_b1_json_schema_entry_level_validation(tmp_path) -> None:
    """_schema/entry.schema.json 按条目校验：违例条目 → CI error（文件定位）；
    手写规则保留为补充（schema 通过但 owner 缺仍被手写规则拦）。"""
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus, validate_corpus

    repo = tmp_path / "repo"
    (repo / "_schema").mkdir(parents=True)
    (repo / "_schema" / "entry.schema.json").write_text(json.dumps({
        "type": "object",
        "required": ["id", "name", "owner"],
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "l0": {"type": "boolean"},
            "aliases": {"type": "array", "items": {"type": "string"}},
        },
    }), encoding="utf-8")
    (repo / "concepts").mkdir()
    (repo / "concepts" / "ok.yaml").write_text(
        "- id: concept:ok\n  name: 合规\n  owner: o\n  l0: true\n", encoding="utf-8")
    corpus = load_corpus(repo)
    assert not [i for i in validate_corpus(corpus) if i.severity == "error"]

    # 违例①：name 类型错（schema 面）
    (repo / "concepts" / "bad_type.yaml").write_text(
        "- id: concept:bt\n  name: 123\n  owner: o\n", encoding="utf-8")
    errs = [i for i in validate_corpus(load_corpus(repo)) if i.severity == "error"]
    assert any("schema" in i.message and "concepts/bad_type.yaml" in i.file
               for i in errs)
    # 违例②：schema required 缺 l0 无关、缺 owner 由 schema+手写双拦
    (repo / "concepts" / "bad_type.yaml").unlink()
    (repo / "concepts" / "no_owner.yaml").write_text(
        "- id: concept:no\n  name: 无主\n", encoding="utf-8")
    errs = [i for i in validate_corpus(load_corpus(repo)) if i.severity == "error"]
    assert any("owner" in i.message for i in errs)  # 手写规则（补充面）不弱化
    # 违例③：l0 非布尔（schema 面）
    (repo / "concepts" / "no_owner.yaml").unlink()
    (repo / "concepts" / "bad_l0.yaml").write_text(
        "- id: concept:bl\n  name: 布尔错\n  owner: o\n  l0: yes-please\n",
        encoding="utf-8")
    errs = [i for i in validate_corpus(load_corpus(repo)) if i.severity == "error"]
    assert any("schema" in i.message and "l0" in i.message for i in errs)


# ---- 边界 4：l0/owner 入 curated_json ----


def test_b4_l0_owner_persisted(env) -> None:
    assert _merge(env)["status"] == "succeeded"
    payload = _curated(env, "concept:vat.input_credit")
    assert payload["l0"] is True, "L0 标记入 curated_json（m2s-4 导出数据源）"
    assert payload["owner"] == "tax-domain", "owner 落库（构建报告数据源）"
    tpl_payload = _curated(env, "template:TPL_1")
    assert tpl_payload.get("owner") == "tax-domain"
    assert "l0" not in tpl_payload or tpl_payload["l0"] is False


# ---- P3-1：abbr 短词口径统一（合并侧免拦——与 CI/文档口径一致） ----


def test_p3_1_abbr_short_not_blocked_at_merge(env) -> None:
    (env.repo / "concepts" / "c.yaml").write_text(
        CONCEPTS.replace("abbr: [JXDK]", "abbr: [税]"), encoding="utf-8")
    result = _merge(env)
    curated_conflicts = result["stats"]["curated"]["conflicts"]
    assert not [c for c in curated_conflicts if "alias skipped" in c["reason"]], \
        "缩写天然短——合并侧不拦（与 CI『abbr 不参与短词拦截』口径一致）"
    from knowledge_lattice.core.semantic.norm import normalize_alias

    assert normalize_alias("税") in _manual_norms(env, "concept:vat.input_credit")


# ---- P3-2：别名 UNIQUE 冲突消解（冲突记录而非整 run 失败） ----


def test_p3_2_alias_norm_collision_skipped_not_crash(env) -> None:
    """manual 别名与既有 name 别名同 norm → 逐条 skip + 冲突记录，run 成功。"""
    (env.repo / "templates" / "t.yaml").write_text(
        "- id: template:TPL_1\n  owner: o\n"
        "  aliases: [模板tpl_1]\n"   # 与 name 别名同 norm（normalize 后同）
        "  definition: d\n", encoding="utf-8")
    result = _merge(env)
    assert result["status"] == "succeeded", "UNIQUE 冲突不得使整 run 失败"
    assert any("alias norm conflict" in c["reason"]
               for c in result["stats"]["curated"]["conflicts"])
    kinds = {a["alias"]: a["kind"]
             for a in env.backend.sem_entity_aliases(
                 ORG, [_entity(env, "template:TPL_1")["id"]])}
    assert kinds.get("模板TPL_1") == "name", "既有 name 别名原样（不被顶替）"
    assert "模板tpl_1" not in kinds, "冲突 norm 的 manual 别名不写入"


def test_p3_2_ci_flags_duplicate_norm_within_entity(tmp_path) -> None:
    """CI 查重：同条目内重复 alias_norm（aliases 与 abbr 撞）→ error。"""
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus, validate_corpus

    repo = tmp_path / "r"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "c.yaml").write_text(
        "- id: concept:x\n  name: X\n  owner: o\n"
        "  aliases: [抵进项]\n  abbr: [抵进项]\n", encoding="utf-8")
    errs = [i for i in validate_corpus(load_corpus(repo)) if i.severity == "error"]
    assert any("duplicate" in i.message and "抵进项" in i.message for i in errs)


# ---- P3-3：sensitivity 按 YAML 当前值回写（含显式 normal / 缺省归 normal） ----


def test_p3_3_sensitivity_follows_yaml_current_value(env) -> None:
    body = "- id: template:TPL_1\n  owner: o\n  sensitivity: restricted\n"
    (env.repo / "templates" / "t.yaml").write_text(body, encoding="utf-8")
    assert _merge(env)["status"] == "succeeded"
    assert _entity(env, "template:TPL_1")["sensitivity"] == "restricted"

    (env.repo / "templates" / "t.yaml").write_text(
        body.replace("restricted", "normal"), encoding="utf-8")
    assert _merge(env)["status"] == "succeeded"
    assert _entity(env, "template:TPL_1")["sensitivity"] == "normal", \
        "显式 normal 必须回写（原 COALESCE 只增不减缺陷）"

    (env.repo / "templates" / "t.yaml").write_text(
        "- id: template:TPL_1\n  owner: o\n", encoding="utf-8")
    assert _merge(env)["status"] == "succeeded"
    assert _entity(env, "template:TPL_1")["sensitivity"] == "normal", \
        "YAML 真源：条目在场而未声明 → normal"


def test_p3_3_stale_clear_keeps_non_corpus_sensitivity(env) -> None:
    """条目整体消失（stale 清理面）不动 sensitivity——覆盖层外的值不受合并影响。"""
    (env.repo / "templates" / "t.yaml").write_text(
        "- id: template:TPL_1\n  owner: o\n  sensitivity: restricted\n",
        encoding="utf-8")
    assert _merge(env)["status"] == "succeeded"
    (env.repo / "templates" / "t.yaml").unlink()
    assert _merge(env)["status"] == "succeeded"
    assert _entity(env, "template:TPL_1")["sensitivity"] == "restricted", \
        "stale 清理只清 curated/别名（sensitivity 收口归声明面——登记注记）"


# ---- P3-4·5：activated_at 严格递增扩到 switch + reactivate 返回值消费 ----


@pytest.fixture()
def benv(backend, tmp_path):
    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    return SimpleNamespace(db=backend, backend=backend.make_backend(),
                           settings=settings)


def _seed(benv, key: str, name: str) -> None:
    from knowledge_lattice.core.semantic.sync import run_sync

    rec = tpl_entity(key, name=name)
    run_sync(benv.backend, ORG, FakeSourceAdapter("template_center", [rec]),
             settings=benv.settings, snapshot=[rec], now=NOW)


def _build(benv):
    from knowledge_lattice.core.semantic.build import run_build

    return run_build(benv.backend, ORG, settings=benv.settings)


def test_p3_4_switch_strictly_increasing_after_reactivate(benv) -> None:
    """重激活顶置未来时间戳（max+1s）后，同秒窗口内新 rev 的 switch 必须同样
    严格递增——current 跟随最新 ready（不滞留重激活行）。"""
    _seed(benv, "TPL_A", "A")
    r1 = _build(benv)
    assert r1["status"] == "ready"
    _seed(benv, "TPL_A", "A2")
    r2 = _build(benv)
    assert r2["status"] == "ready"
    _seed(benv, "TPL_A", "A")  # rev 回退 → 重激活 r1（activated_at = max+1s 未来）
    r3 = _build(benv)
    assert r3["status"] == "ready" and r3["build_id"] == r1["build_id"]
    assert benv.backend.sem_current_build(ORG)["id"] == r1["build_id"]

    # 同秒窗口内内容再前进 → 新 rev 的 switch 严格递增 → current 跟随新行
    _seed(benv, "TPL_A", "A3")
    r4 = _build(benv)
    assert r4["status"] == "ready" and r4["build_id"] not in (r1["build_id"], r2["build_id"])
    current = benv.backend.sem_current_build(ORG)
    assert current["id"] == r4["build_id"], \
        "switch 的 activated_at 须严格递增（重激活未来时间戳不得压住后续 ready）"


def test_p3_5_reactivate_false_degrades_not_fake_ready(benv, monkeypatch) -> None:
    """reactivate 返回 False（竞态下行已非 ready）：current 同 rev → skipped；
    否则 RuntimeError（不得虚报 ready/写 reactivated 日志语义）。"""
    _seed(benv, "TPL_A", "A")
    r1 = _build(benv)
    _seed(benv, "TPL_A", "A2")
    r2 = _build(benv)
    _seed(benv, "TPL_A", "A")  # 回退

    calls = {"n": 0}

    def fake_reactivate(org_id, build_id, stats_json, *, audit=None):
        calls["n"] += 1
        return False  # 竞态注入：行已非 ready

    monkeypatch.setattr(benv.backend, "sem_reactivate_build", fake_reactivate)
    with pytest.raises(RuntimeError, match="reactivate ineffective"):
        _build(benv)
    assert calls["n"] == 1
    # 行未被伪造 ready：current 仍是 r2
    assert benv.backend.sem_current_build(ORG)["id"] == r2["build_id"]
    assert benv.db.execute(
        "SELECT status FROM sem_builds WHERE id = ?", (r1["build_id"],)
    ).fetchone()[0] == "ready"  # 行本身保持 ready（仅未重激活）


# ---- P3-7：_content_rev 跳过点目录（.git 抖动） ----


def test_p3_7_content_rev_ignores_dotdirs(env) -> None:
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus

    assert _merge(env)["status"] == "succeeded"
    rev1 = load_corpus(env.repo).rev
    git_dir = env.repo / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "refs").mkdir()
    (git_dir / "refs" / "heads").mkdir(exist_ok=True)
    (git_dir / "refs" / "heads" / "main").write_text("aaa\n", encoding="utf-8")
    assert load_corpus(env.repo).rev == rev1, ".git 变动不得扰动 rev"
    (git_dir / "refs" / "heads" / "main").write_text("bbb\n", encoding="utf-8")
    assert load_corpus(env.repo).rev == rev1
    # 内容文件变更仍换 rev（跳过面仅限点目录）
    (env.repo / "concepts" / "c.yaml").write_text(
        CONCEPTS.replace("进项税额抵扣", "进项税额抵扣额"), encoding="utf-8")
    assert load_corpus(env.repo).rev != rev1


# ---- P3-8：CI 三缺口 ----


def test_p3_8_ci_global_id_uniqueness(tmp_path) -> None:
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus, validate_corpus

    repo = tmp_path / "r"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "a.yaml").write_text(
        "- id: concept:dup\n  name: 甲\n  owner: o\n", encoding="utf-8")
    (repo / "concepts" / "b.yaml").write_text(
        "- id: concept:dup\n  name: 乙\n  owner: o\n", encoding="utf-8")
    errs = [i for i in validate_corpus(load_corpus(repo)) if i.severity == "error"]
    assert any("duplicate id" in i.message for i in errs)


def test_p3_8_ci_match_mode_enum(tmp_path) -> None:
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus, validate_corpus

    repo = tmp_path / "r"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "c.yaml").write_text(
        "- id: concept:x\n  name: X\n  owner: o\n"
        "  aliases: [{value: 抵扣, match_mode: sometimes}]\n", encoding="utf-8")
    errs = [i for i in validate_corpus(load_corpus(repo)) if i.severity == "error"]
    assert any("match_mode" in i.message for i in errs)


def test_p3_8_ci_related_to_src_must_be_concept(tmp_path) -> None:
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus, validate_corpus

    repo = tmp_path / "r"
    (repo / "scenarios").mkdir(parents=True)
    (repo / "scenarios" / "s.yaml").write_text(
        "- id: scenario:S1\n  name: 场景\n  owner: o\n"
        "  related_to: [concept:x]\n", encoding="utf-8")
    errs = [i for i in validate_corpus(load_corpus(repo)) if i.severity == "error"]
    assert any("related_to" in i.message and "concept" in i.message for i in errs)


# ---- P3-10①：G-15 store CASE 第二道防线直调用例 ----


def test_p3_10_store_case_guard_direct(backend, tmp_path) -> None:
    """绕过 core 预过滤直调 upsert_relations_batch：① INSERT 指向 retired/
    missing 端点 → 落 missing（不 active）；② 既有非 active 行 UPDATE 不复活。"""
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord
    from knowledge_lattice.core.semantic.sync import run_sync

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    b = backend.make_backend()
    recs = [tpl_entity("TPL_G"), EntityRecord(type="template_field", key="TPL_G.F",
                                              name="字段",
                                              parent_key="template:TPL_G")]
    run_sync(b, ORG, FakeSourceAdapter("template_center", recs), settings=settings,
             snapshot=list(recs), now=NOW)
    ids = b.resolve_entity_ids(
        ORG, [("template", "TPL_G"), ("template_field", "TPL_G.F")])
    f_id = ids[("template_field", "TPL_G.F")]
    backend.execute(
        "UPDATE sem_entities SET status = 'retired' WHERE org_id = ? AND id = ?",
        (ORG, f_id))
    backend.execute(
        "INSERT INTO sem_entities(org_id, type, key, name, source, source_system,"
        " status, synced_at) VALUES(?, 'template_field', 'TPL_G.M', '缺场字段',"
        " 'sync', 'template_center', 'missing', ?)", (ORG, NOW))
    backend.commit()
    m_id = backend.execute(
        "SELECT id FROM sem_entities WHERE org_id = ? AND key = 'TPL_G.M'",
        (ORG,)).fetchone()[0]

    rows = [
        {"src_id": ids[("template", "TPL_G")], "rel_type": "has_field",
         "dst_id": f_id, "attrs_json": "{}", "synced_at": NOW},   # retired dst
        {"src_id": ids[("template", "TPL_G")], "rel_type": "has_field",
         "dst_id": m_id, "attrs_json": "{}", "synced_at": NOW},   # missing dst
    ]
    counts = b.upsert_relations_batch(ORG, rows)
    assert counts["inserted"] == 2
    statuses = {
        r[0]: r[1] for r in backend.execute(
            "SELECT dst_id, status FROM sem_relations WHERE org_id = ?", (ORG,))
    }
    assert statuses[f_id] == "missing", "retired 端点 INSERT 落 missing（CASE 守卫）"
    assert statuses[m_id] == "missing", "missing 端点 INSERT 落 missing（潜伏态）"

    # ② 既有非 active 行（retired）再 upsert → 不复活 active
    backend.execute(
        "UPDATE sem_relations SET status = 'retired'"
        " WHERE org_id = ? AND dst_id = ?", (ORG, f_id))
    backend.commit()
    b.upsert_relations_batch(ORG, [rows[0]])
    status = backend.execute(
        "SELECT status FROM sem_relations WHERE org_id = ? AND dst_id = ?",
        (ORG, f_id)).fetchone()[0]
    assert status == "retired", "非 active 行 UPDATE 不得复活为 active"


# ---- P3-10②：yaml 生产路径（run_sync_task 组合面） ----


def test_p3_10_yaml_production_path_via_task(backend, tmp_path) -> None:
    """run_sync_task 生产路径：sources_json 解析 → YamlRepoAdapter → post_run
    curated 合并 → 值域映射装载 → FTS refresh → 构建任务投递 → close 全链。"""
    import json as _json

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.sync import run_sync_task

    seed_org(backend, ORG)
    repo = tmp_path / "prodrepo"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "c.yaml").write_text(CONCEPTS, encoding="utf-8")
    (repo / "dim_value_map.yaml").write_text(
        "mappings:\n  - dim: region\n    values:\n      CN-SH: CN\n",
        encoding="utf-8")
    settings = Settings(
        environment="test", data_dir=tmp_path,
        semantic_sources_json=_json.dumps({ORG: {"yaml": {"endpoint": str(repo)}}}),
    )
    b = backend.make_backend()
    b.create_task(None, task_type="semantic_sync", task_id="tsk_yaml_prod",
                  payload=_json.dumps({"org": ORG, "adapter": "yaml"}))
    result = run_sync_task(b, settings, "tsk_yaml_prod")

    assert result["status"] == "succeeded"
    assert result["stats"]["curated"]["entities_written"] >= 1
    concept = b.sem_entity_by_key(ORG, "concept", "vat.input_credit")
    assert concept is not None and concept["source"] == "curated"
    payload = _json.loads(concept["curated_json"] or "{}")
    assert payload["definition"] and payload["l0"] is True and payload["owner"]
    # curated 别名替换后 FTS 时效：manual 别名 token 进索引、可检索
    from knowledge_lattice.core.semantic.lookup import search_entities

    hit = search_entities(b, ORG, "进项抵扣")
    assert hit["entities"] and hit["entities"][0]["key"] == "vat.input_credit"
    seg_rows = backend.execute(
        "SELECT seg_text FROM sem_search_texts WHERE org_id = ?", (ORG,)).fetchall()
    # manual 别名 token 进索引（分词形态——「进项抵扣」切分为 进项/抵扣）
    assert any("抵扣" in r[0] for r in seg_rows), "manual 别名须进 FTS 索引"
    # 成功 run 后自动投递 semantic_build（§5.8）
    queued = backend.execute(
        "SELECT payload FROM tasks WHERE type = 'semantic_build'").fetchall()
    assert queued and _json.loads(queued[-1][0])["org"] == ORG


# ---- P3-11：CI 脚本预算接线（settings 环境变量面） ----


def test_p3_11_ci_budget_reads_settings_env(repo_baseline, tmp_path) -> None:
    """--l0-budget 缺省 → LATTICE_SEM_L0_TOKEN_BUDGET 环境变量（settings 接线）；
    显式 flag 优先。"""
    baseline = repo_baseline
    env = {
        **__import__("os").environ,
        "LATTICE_SEM_L0_TOKEN_BUDGET": "1",
        "LATTICE_DATA_DIR": str(tmp_path),
    }
    tight = subprocess.run(
        [sys.executable, "scripts/sem_yaml_ci.py", str(baseline)],
        capture_output=True, text=True, env=env)
    assert tight.returncode == 1, "环境变量小预算应拦截（settings 接线生效）"

    env_ok = {**env, "LATTICE_SEM_L0_TOKEN_BUDGET": "1500"}
    ok = subprocess.run(
        [sys.executable, "scripts/sem_yaml_ci.py", str(baseline)],
        capture_output=True, text=True, env=env_ok)
    assert ok.returncode == 0

    override = subprocess.run(
        [sys.executable, "scripts/sem_yaml_ci.py", str(baseline),
         "--l0-budget", "1500"],
        capture_output=True, text=True, env=env)
    assert override.returncode == 0, "显式 flag 覆盖环境变量"


@pytest.fixture()
def repo_baseline(tmp_path):
    """合法最小仓（CI 零 error 基线——供脚本类用例复用）。"""
    repo = tmp_path / "ci_baseline"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "c.yaml").write_text(
        "- id: concept:ok\n  name: 合规概念\n  owner: o\n"
        "  aliases: [合规别名]\n  l0: true\n", encoding="utf-8")
    return repo


# ---- R3/N6：schema 语义非法——可定位 error 不崩溃 + 双路径对称 ----


_INVALID_SCHEMA = json.dumps({"type": "not-a-type", "required": "id"})


def test_n6_invalid_schema_locatable_error_not_crash(tmp_path) -> None:
    """有效 JSON 但语义非法的 entry.schema.json（type 非法/required 非数组）：
    jsonschema 在场路径**一次性自校验** → 可定位 error（_schema/entry.schema.json）
    + entry_schema 置 None（条目走手写补充面）——validate_corpus 不崩溃。"""
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus, validate_corpus

    repo = tmp_path / "n6"
    (repo / "_schema").mkdir(parents=True)
    (repo / "_schema" / "entry.schema.json").write_text(_INVALID_SCHEMA,
                                                        encoding="utf-8")
    (repo / "concepts").mkdir()
    (repo / "concepts" / "c.yaml").write_text(
        "- id: concept:ok\n  name: 合规\n  owner: o\n", encoding="utf-8")

    issues = validate_corpus(load_corpus(repo))  # 不得抛 SchemaError
    schema_errs = [i for i in issues if i.severity == "error"
                   and i.file == "_schema/entry.schema.json"]
    assert schema_errs, "schema 语义非法须产可定位 error（非 traceback）"
    assert not [i for i in issues if "schema violation" in i.message], \
        "schema 已废弃 → 条目不再走 schema 面（手写补充面接管）"


def test_n6_non_object_schema_reports_error(tmp_path) -> None:
    """非对象 schema 文件（合法 JSON 数组）→ error。"""
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus, validate_corpus

    repo = tmp_path / "n6b"
    (repo / "_schema").mkdir(parents=True)
    (repo / "_schema" / "entry.schema.json").write_text("[1, 2]", encoding="utf-8")
    (repo / "concepts").mkdir()
    (repo / "concepts" / "c.yaml").write_text(
        "- id: concept:ok\n  name: 合规\n  owner: o\n", encoding="utf-8")
    issues = validate_corpus(load_corpus(repo))
    assert any(i.severity == "error" and i.file == "_schema/entry.schema.json"
               for i in issues)


def test_n6_fallback_path_symmetric(tmp_path, monkeypatch) -> None:
    """回退路径（jsonschema 缺席）双对称：①同一批条目违例的**定位等价**
    （文件+路径前缀）；②同一份语义非法 schema 同样报可定位 error（回退侧
    最小 schema 合法性检查——零依赖环境门禁不静默削弱）。"""
    import sys as _sys

    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus, validate_corpus

    repo = tmp_path / "n6c"
    (repo / "_schema").mkdir(parents=True)
    (repo / "_schema" / "entry.schema.json").write_text(json.dumps({
        "type": "object",
        "required": ["id", "name", "owner"],
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "l0": {"type": "boolean"},
        },
    }), encoding="utf-8")
    (repo / "concepts").mkdir()
    (repo / "concepts" / "c.yaml").write_text(
        "- id: concept:bt\n  name: 123\n  owner: o\n", encoding="utf-8")       # name 类型
    (repo / "concepts" / "d.yaml").write_text(
        "- id: concept:bl\n  name: 布尔错\n  owner: o\n  l0: yes-please\n",
        encoding="utf-8")                                                        # l0 类型

    # jsonschema 在场路径基线（双路径等价的参照侧）
    lib_result = validate_corpus(load_corpus(repo))
    lib_schema_errs = [i for i in lib_result if "schema violation" in i.message]
    lib_files = {i.file for i in lib_schema_errs}
    assert lib_files == {"concepts/c.yaml", "concepts/d.yaml"}

    monkeypatch.setitem(_sys.modules, "jsonschema", None)  # 强制 ImportError 回退
    try:
        fb_issues = validate_corpus(load_corpus(repo))
    finally:
        monkeypatch.undo()
    fb_schema_errs = [i for i in fb_issues if "schema violation" in i.message]
    # 定位等价：同两条目（bad_type/bad_l0）各报 error、文件定位与库路径一致
    assert {i.file for i in fb_schema_errs} == lib_files, \
        f"回退路径定位等价（got { {i.file for i in fb_schema_errs} }）"
    assert any("name" in i.message for i in fb_schema_errs)
    assert any("l0" in i.message for i in fb_schema_errs)

    # ② 同一份语义非法 schema：回退侧同样报可定位 error、不崩溃
    (repo / "_schema" / "entry.schema.json").write_text(_INVALID_SCHEMA,
                                                        encoding="utf-8")
    monkeypatch.setitem(_sys.modules, "jsonschema", None)
    try:
        issues2 = validate_corpus(load_corpus(repo))
    finally:
        monkeypatch.undo()
    assert any(i.severity == "error" and i.file == "_schema/entry.schema.json"
               for i in issues2), "回退路径对语义非法 schema 须对称报 error"
    assert not [i for i in issues2 if "schema violation" in i.message]
