"""TC-YAML-04 CI 校验全集 + YAML 仓 corpus 装载（design §5.8 YAML 规范/合并规则表）。

corpus 布局（design §5.8 L905）：`_schema/*.schema.json` + `concepts/` +
`templates/` + `report_items/` + `scenarios/` + `l0.yaml`（+ 本段最小实现的
`dim_value_map.yaml`——TC-SYNC-06 值域显式映射表，design §4 无专表 DDL）。
CI 规则逐类拦截（TEST-CASES TC-YAML-04）：JSON Schema 结构 / 别名冲突 /
短词常用词 / L0 预算 / owner 必填（逐条报）/ 引用可解析 / 样本值 ≤3（逐条报）。
"""

from __future__ import annotations

import json

import pytest

CONCEPTS_VAT = """\
- id: concept:vat.input_credit
  name: 进项税额抵扣
  aliases: [进项抵扣, 认证抵扣]
  abbr: [JXDK]
  definition: >
    一般纳税人购进货物、服务等取得合规扣税凭证后，按规定从销项税额中抵减的进项税额。
  why: 影响当期应纳税额，是增值税申报的核心环节。
  examples: [本月进项抵扣怎么算, 抵进项的发票有哪些要求]
  samples: [例一, 例二]
  disambiguation:
    - not: concept:vat.input_transfer_out
      hint: 进项转出是抵扣后因用途改变需要转回，方向相反
  refers_to: [template:TPL_VAT_INPUT, table:db.vat_input]
  l0: true
  sensitivity: normal
  owner: tax-domain
"""

TEMPLATES_OVERLAY = """\
- id: template:TPL_VAT_INPUT
  owner: tax-domain
  aliases: [进项采集模板]
  definition: 月度进项发票采集模板，按发票逐行采集。
  caliber: 只采集当期勾选认证的发票。
  fields:
    - id: template_field:TPL_VAT_INPUT.TAX_AMT
      aliases: [税额, 进项税额]
      definition: 发票票面税额
  extra_relations:
    - rel: derived_from
      from: report_item:VAT_MAIN.L12
      to: template_field:TPL_VAT_INPUT.TAX_AMT
      note: 报表中心暂未配置取数关系，按业务口径人工补充
"""

DIM_VALUE_MAP = """\
mappings:
  - dim: region
    values:
      CN-SH: CN
      CN-BJ: CN
"""


@pytest.fixture()
def repo(tmp_path):
    """标准合法 YAML 仓（CI 零 error 的基线形态）。"""
    (tmp_path / "_schema").mkdir()
    (tmp_path / "_schema" / "entry.schema.json").write_text(
        json.dumps({"type": "object", "required": ["id"]}), encoding="utf-8")
    (tmp_path / "concepts").mkdir()
    (tmp_path / "concepts" / "vat.yaml").write_text(CONCEPTS_VAT, encoding="utf-8")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "TPL_VAT_INPUT.yaml").write_text(
        TEMPLATES_OVERLAY, encoding="utf-8")
    (tmp_path / "dim_value_map.yaml").write_text(DIM_VALUE_MAP, encoding="utf-8")
    return tmp_path


def _issues(repo, *, l0_budget=1500):
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus, validate_corpus

    return validate_corpus(load_corpus(repo), l0_budget=l0_budget)


def _errors(repo, **kw):
    return [i for i in _issues(repo, **kw) if i.severity == "error"]


# ---- corpus 装载 ----


def test_corpus_loads_entries_and_layers(repo) -> None:
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus

    corpus = load_corpus(repo)
    ids = [e.id for e in corpus.entries]
    assert "concept:vat.input_credit" in ids
    assert "template:TPL_VAT_INPUT" in ids

    pure = next(e for e in corpus.entries if e.id == "concept:vat.input_credit")
    assert pure.pure is True
    assert pure.type == "concept" and pure.key == "vat.input_credit"
    assert pure.name == "进项税额抵扣"
    assert [a.value for a in pure.aliases] == ["进项抵扣", "认证抵扣"]
    assert list(pure.abbr) == ["JXDK"]
    assert "template:TPL_VAT_INPUT" in pure.refers_to
    assert pure.l0 is True and pure.owner == "tax-domain"
    assert len(pure.samples) == 2  # ≤3 合法

    overlay = next(e for e in corpus.entries if e.id == "template:TPL_VAT_INPUT")
    assert overlay.pure is False
    assert overlay.fields[0].id == "template_field:TPL_VAT_INPUT.TAX_AMT"
    assert overlay.extra_relations[0].rel == "derived_from"
    assert overlay.extra_relations[0].src == "report_item:VAT_MAIN.L12"
    assert overlay.extra_relations[0].dst == "template_field:TPL_VAT_INPUT.TAX_AMT"

    assert corpus.dim_value_map.get("region", {}).get("CN-SH") == "CN"


def test_corpus_rev_is_content_hash(repo) -> None:
    """rev = 全仓内容哈希——重载稳定、内容变更必变（YAML commit 语义的本地形态）。"""
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus

    rev1 = load_corpus(repo).rev
    rev2 = load_corpus(repo).rev
    assert rev1 == rev2 and len(rev1) == 12
    (repo / "concepts" / "vat.yaml").write_text(
        CONCEPTS_VAT.replace("进项税额抵扣", "进项税额抵扣额"), encoding="utf-8")
    assert load_corpus(repo).rev != rev1


def test_valid_corpus_has_no_errors(repo) -> None:
    assert _errors(repo) == []


# ---- TC-YAML-04：CI 校验逐类拦截（错误可定位到文件） ----


def test_ci_owner_missing_reported_per_entry(repo) -> None:
    body = CONCEPTS_VAT.replace("owner: tax-domain", "")
    (repo / "concepts" / "vat.yaml").write_text(body, encoding="utf-8")
    (repo / "concepts" / "no_owner2.yaml").write_text(
        "- id: concept:vat.x\n  name: X\n  owner: o\n", encoding="utf-8")
    errs = _errors(repo)
    owner_errs = [e for e in errs if "owner" in e.message]
    assert len(owner_errs) == 1  # 逐条报（缺 owner 的那条；vat.yaml 两条目录只有一条缺）
    assert "concepts/vat.yaml" in owner_errs[0].file


def test_ci_samples_over_three_reported_per_entry(repo) -> None:
    body = CONCEPTS_VAT.replace(
        "samples: [例一, 例二]", "samples: [例一, 例二, 例三, 例四]")
    (repo / "concepts" / "vat.yaml").write_text(body, encoding="utf-8")
    errs = _errors(repo)
    assert any("samples" in e.message and "concepts/vat.yaml" in e.file for e in errs)


def test_ci_l0_budget_blocks(repo) -> None:
    """L0 总 token 超预算（默认 1500）→ CI 拦截（design 合并规则表末二行）。"""
    errs = _errors(repo, l0_budget=3)
    assert any("L0" in e.message for e in errs)


def test_ci_short_alias_blocked_unless_marked(repo) -> None:
    body = CONCEPTS_VAT.replace("aliases: [进项抵扣, 认证抵扣]",
                                "aliases: [进项抵扣, {value: 税, match_mode: context}, 抵]")
    (repo / "concepts" / "vat.yaml").write_text(body, encoding="utf-8")
    errs = _errors(repo)
    short = [e for e in errs if "short" in e.message]
    assert len(short) == 1  # 「税」标 context 放行；「抵」1 字未标 → 拦截


def test_ci_common_word_alias_blocked_unless_marked(repo) -> None:
    body = CONCEPTS_VAT.replace(
        "aliases: [进项抵扣, 认证抵扣]",
        "aliases: [进项抵扣, {value: 什么情况, match_mode: fuzzy_only}, 发票]")
    (repo / "concepts" / "vat.yaml").write_text(body, encoding="utf-8")
    errs = _errors(repo)
    assert any("common word" in e.message for e in errs)  # 「发票」常用词未标
    assert not any("什么情况" in e.message for e in errs)  # fuzzy_only 放行


def test_ci_ambiguous_alias_requires_disambiguation_or_context(repo) -> None:
    # vat.yaml 与另一条目共用别名「进项抵扣」——先去掉 vat.yaml 的消歧声明，
    # 两方都无 disambiguation → 拦截
    (repo / "concepts" / "vat.yaml").write_text(
        CONCEPTS_VAT.split("  disambiguation:")[0], encoding="utf-8")
    (repo / "concepts" / "other.yaml").write_text(
        "- id: concept:vat.input_ratio\n"
        "  name: 进项占比\n"
        "  aliases: [进项抵扣]\n"
        "  owner: tax-domain\n",
        encoding="utf-8")
    errs = _errors(repo)
    assert any("ambiguous" in e.message for e in errs)
    # 一方带 disambiguation → 放行（合并规则表：允许但要求说明）
    (repo / "concepts" / "other.yaml").write_text(
        "- id: concept:vat.input_ratio\n"
        "  name: 进项占比\n"
        "  aliases: [进项抵扣]\n"
        "  disambiguation:\n"
        "    - not: concept:vat.input_credit\n"
        "      hint: 占比是比率概念\n"
        "  owner: tax-domain\n",
        encoding="utf-8")
    assert not [e for e in _errors(repo) if "ambiguous" in e.message]


def test_ci_reference_malformed_and_whitelist(repo) -> None:
    body = CONCEPTS_VAT.replace(
        "refers_to: [template:TPL_VAT_INPUT, table:db.vat_input]",
        "refers_to: [template:TPL_VAT_INPUT, badref]")
    (repo / "concepts" / "vat.yaml").write_text(body, encoding="utf-8")
    assert any("malformed" in e.message for e in _errors(repo))

    # extra_relations 端点类型不在白名单（uses 只允许 scenario→template）
    body2 = TEMPLATES_OVERLAY.replace("rel: derived_from", "rel: uses")
    (repo / "templates" / "TPL_VAT_INPUT.yaml").write_text(body2, encoding="utf-8")
    assert any("whitelist" in e.message for e in _errors(repo))


def test_ci_pure_entry_type_only_concept_system(repo) -> None:
    (repo / "concepts" / "bad.yaml").write_text(
        "- id: template:TPL_X\n  name: X\n  owner: o\n", encoding="utf-8")
    errs = _errors(repo)
    assert any("concept/system" in e.message for e in errs)


def test_ci_sensitivity_invalid(repo) -> None:
    body = CONCEPTS_VAT.replace("sensitivity: normal", "sensitivity: secret")
    (repo / "concepts" / "vat.yaml").write_text(body, encoding="utf-8")
    assert any("sensitivity" in e.message for e in _errors(repo))


def test_ci_concept_reference_unresolvable_in_repo(repo) -> None:
    """concept/system 目标只能出自 YAML 仓——仓内无此条目 → error（其余类型缺目标为
    warning：可解析自同步实体——过渡期口径 §6.3）。"""
    body = CONCEPTS_VAT.replace(
        "refers_to: [template:TPL_VAT_INPUT, table:db.vat_input]",
        "refers_to: [concept:vat.not_in_repo]")
    (repo / "concepts" / "vat.yaml").write_text(body, encoding="utf-8")
    issues = _issues(repo)
    assert any(i.severity == "error" and "not in repo" in i.message for i in issues)
    # 同步实体类型（template）不在仓内 → warning 非 error
    body2 = body.replace("concept:vat.not_in_repo", "template:TPL_NOT_IN_REPO")
    (repo / "concepts" / "vat.yaml").write_text(body2, encoding="utf-8")
    issues = _issues(repo)
    assert not any(i.severity == "error" and "not in repo" in i.message for i in issues)


# ---- CI 脚本（scripts/sem_yaml_ci.py——exit 1 拦截 / 0 放行） ----


def test_ci_script_exit_codes(repo) -> None:
    import subprocess
    import sys

    ok = subprocess.run(
        [sys.executable, "scripts/sem_yaml_ci.py", str(repo)],
        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr

    (repo / "concepts" / "vat.yaml").write_text(
        CONCEPTS_VAT.replace("owner: tax-domain", ""), encoding="utf-8")
    bad = subprocess.run(
        [sys.executable, "scripts/sem_yaml_ci.py", str(repo)],
        capture_output=True, text=True)
    assert bad.returncode == 1
    assert "owner" in bad.stdout
