"""识别评测参考词典（TC-SEV-01——eval/semantic_golden.jsonl 的标注真相源）。

单一真相源：黄金集的 entity_key 必须在本词典内可解析（tests/test_sem_eval_golden
校验）。域：增值税（POC 首场景）。**seed_reference_org** 沿真实管线落库——
四同步源（template_center/metadata/report_center/scenario_config）走
run_sync，YAML 覆盖层 + 纯人工 concept/system 走 run_yaml_sync（m2s-3 全链
复用——评测对真实管线而非旁路造数）。

别名口径（与 annotate 四步匹配对齐）：

- kind=name/code：精确全词档（matched_by=exact）；
- manual/sync/abbr：别名档（matched_by=alias；拉丁面词边界校验）；
- match_mode=context：上下文短别名档（同句确定命中 + 有关系才保留——
  TC-SEM-04 样本面：免税）；
- 歧义别名（留抵/税率）：双实体共享 + 双方声明 disambiguation（CI 规则），
  消歧依赖共现①/L0 片段④（歧义指标样本面）。
"""

from __future__ import annotations

from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

NOW = "2026-10-31 09:00:00"


class _ListAdapter:
    """快照列表适配器（duck-typed SourceAdapter——评测种子专用）。"""

    def __init__(self, name: str, records: list) -> None:
        self.name = name
        self.records = list(records)

    def fetch(self, org_id: str):
        return list(self.records)


# ---- template_center：模板 + 模板字段 + has_field ----

TEMPLATE_CENTER: list = [
    EntityRecord(type="template", key="TPL_VAT_INPUT", name="进项发票采集模板",
                 aliases=("进项采集源",)),
    EntityRecord(type="template_field", key="TPL_VAT_INPUT.TAX_AMT",
                 name="票面税额", parent_key="template:TPL_VAT_INPUT"),
    EntityRecord(type="template_field", key="TPL_VAT_INPUT.TOTAL_AMT",
                 name="价税合计", parent_key="template:TPL_VAT_INPUT"),
    EntityRecord(type="template_field", key="TPL_VAT_INPUT.INV_NO",
                 name="发票号码", parent_key="template:TPL_VAT_INPUT"),
    EntityRecord(type="template_field", key="TPL_VAT_INPUT.INV_DATE",
                 name="开票日期", parent_key="template:TPL_VAT_INPUT"),
    EntityRecord(type="template", key="TPL_VAT_OUTPUT", name="销项发票采集模板"),
    EntityRecord(type="template_field", key="TPL_VAT_OUTPUT.TAX_AMT",
                 name="销项票面税额", parent_key="template:TPL_VAT_OUTPUT"),
    EntityRecord(type="template", key="TPL_FILING_MAIN", name="增值税申报主表模板"),
    EntityRecord(type="template_field", key="TPL_FILING_MAIN.PAYABLE",
                 name="应补税额栏", parent_key="template:TPL_FILING_MAIN"),
    EntityRecord(type="template", key="TPL_RETAINED_CONFIRM",
                 name="留抵税额确认模板"),
    EntityRecord(type="template_field", key="TPL_RETAINED_CONFIRM.AMT",
                 name="确认金额栏", parent_key="template:TPL_RETAINED_CONFIRM"),
    RelationRecord(src=("template", "TPL_VAT_INPUT"), rel_type="has_field",
                   dst=("template_field", "TPL_VAT_INPUT.TAX_AMT")),
    RelationRecord(src=("template", "TPL_VAT_INPUT"), rel_type="has_field",
                   dst=("template_field", "TPL_VAT_INPUT.TOTAL_AMT")),
    RelationRecord(src=("template", "TPL_VAT_INPUT"), rel_type="has_field",
                   dst=("template_field", "TPL_VAT_INPUT.INV_NO")),
    RelationRecord(src=("template", "TPL_VAT_INPUT"), rel_type="has_field",
                   dst=("template_field", "TPL_VAT_INPUT.INV_DATE")),
    RelationRecord(src=("template", "TPL_VAT_OUTPUT"), rel_type="has_field",
                   dst=("template_field", "TPL_VAT_OUTPUT.TAX_AMT")),
    RelationRecord(src=("template", "TPL_FILING_MAIN"), rel_type="has_field",
                   dst=("template_field", "TPL_FILING_MAIN.PAYABLE")),
    RelationRecord(src=("template", "TPL_RETAINED_CONFIRM"), rel_type="has_field",
                   dst=("template_field", "TPL_RETAINED_CONFIRM.AMT")),
]

# ---- metadata：表 + 列 + has_column / backed_by / maps_to ----

METADATA: list = [
    EntityRecord(type="table", key="ods.vat_input_invoice", name="进项发票明细表"),
    EntityRecord(type="column", key="ods.vat_input_invoice.tax_amt", name="税额",
                 parent_key="table:ods.vat_input_invoice"),
    EntityRecord(type="column", key="ods.vat_input_invoice.total_amt", name="价税金额",
                 parent_key="table:ods.vat_input_invoice"),
    EntityRecord(type="column", key="ods.vat_input_invoice.inv_no", name="发票号",
                 parent_key="table:ods.vat_input_invoice"),
    EntityRecord(type="column", key="ods.vat_input_invoice.inv_date",
                 name="开票日", parent_key="table:ods.vat_input_invoice"),
    EntityRecord(type="column", key="ods.vat_input_invoice.seller",
                 name="销方名称", parent_key="table:ods.vat_input_invoice"),
    EntityRecord(type="table", key="ods.vat_output_invoice", name="销项发票明细表"),
    EntityRecord(type="column", key="ods.vat_output_invoice.tax_amt",
                 name="销项税额列", parent_key="table:ods.vat_output_invoice"),
    EntityRecord(type="table", key="dim.taxpayer", name="纳税人信息表"),
    EntityRecord(type="column", key="dim.taxpayer.taxpayer_type",
                 name="纳税人类型", parent_key="table:dim.taxpayer"),
    EntityRecord(type="column", key="dim.taxpayer.credit_level",
                 name="信用等级", parent_key="table:dim.taxpayer"),
    EntityRecord(type="table", key="ods.filing_record", name="申报记录表"),
    EntityRecord(type="column", key="ods.filing_record.period", name="所属期",
                 parent_key="table:ods.filing_record"),
    EntityRecord(type="column", key="ods.filing_record.payable", name="应补税额",
                 parent_key="table:ods.filing_record"),
    RelationRecord(src=("table", "ods.vat_input_invoice"), rel_type="has_column",
                   dst=("column", "ods.vat_input_invoice.tax_amt")),
    RelationRecord(src=("table", "ods.vat_input_invoice"), rel_type="has_column",
                   dst=("column", "ods.vat_input_invoice.total_amt")),
    RelationRecord(src=("table", "ods.vat_input_invoice"), rel_type="has_column",
                   dst=("column", "ods.vat_input_invoice.inv_no")),
    RelationRecord(src=("table", "ods.vat_input_invoice"), rel_type="has_column",
                   dst=("column", "ods.vat_input_invoice.inv_date")),
    RelationRecord(src=("table", "ods.vat_input_invoice"), rel_type="has_column",
                   dst=("column", "ods.vat_input_invoice.seller")),
    RelationRecord(src=("table", "ods.vat_output_invoice"), rel_type="has_column",
                   dst=("column", "ods.vat_output_invoice.tax_amt")),
    RelationRecord(src=("table", "dim.taxpayer"), rel_type="has_column",
                   dst=("column", "dim.taxpayer.taxpayer_type")),
    RelationRecord(src=("table", "dim.taxpayer"), rel_type="has_column",
                   dst=("column", "dim.taxpayer.credit_level")),
    RelationRecord(src=("table", "ods.filing_record"), rel_type="has_column",
                   dst=("column", "ods.filing_record.period")),
    RelationRecord(src=("table", "ods.filing_record"), rel_type="has_column",
                   dst=("column", "ods.filing_record.payable")),
    RelationRecord(src=("template", "TPL_VAT_INPUT"), rel_type="backed_by",
                   dst=("table", "ods.vat_input_invoice")),
    RelationRecord(src=("template", "TPL_VAT_OUTPUT"), rel_type="backed_by",
                   dst=("table", "ods.vat_output_invoice")),
    RelationRecord(src=("template_field", "TPL_VAT_INPUT.TAX_AMT"),
                   rel_type="maps_to", dst=("column", "ods.vat_input_invoice.tax_amt")),
    RelationRecord(src=("template_field", "TPL_VAT_INPUT.INV_NO"),
                   rel_type="maps_to", dst=("column", "ods.vat_input_invoice.inv_no")),
    RelationRecord(src=("template_field", "TPL_FILING_MAIN.PAYABLE"),
                   rel_type="maps_to", dst=("column", "ods.filing_record.payable")),
]

# ---- report_center：报表 + 报表项 + has_item / derived_from ----

REPORT_CENTER: list = [
    EntityRecord(type="report", key="VAT_MAIN", name="增值税申报表主表"),
    EntityRecord(type="report_item", key="VAT_MAIN.L11", name="主表销项税额行",
                 parent_key="report:VAT_MAIN"),
    EntityRecord(type="report_item", key="VAT_MAIN.L12", name="主表进项税额行",
                 parent_key="report:VAT_MAIN"),
    EntityRecord(type="report_item", key="VAT_MAIN.L13", name="上期留抵税额行",
                 parent_key="report:VAT_MAIN"),
    EntityRecord(type="report_item", key="VAT_MAIN.L20", name="期末留抵税额行",
                 parent_key="report:VAT_MAIN"),
    EntityRecord(type="report_item", key="VAT_MAIN.L23", name="应纳税额合计行",
                 parent_key="report:VAT_MAIN"),
    EntityRecord(type="report", key="VAT_AUX_1", name="附列资料一"),
    EntityRecord(type="report_item", key="VAT_AUX_1.R1", name="专票销售额行",
                 parent_key="report:VAT_AUX_1"),
    EntityRecord(type="report_item", key="VAT_AUX_1.R2", name="普票销售额行",
                 parent_key="report:VAT_AUX_1"),
    RelationRecord(src=("report", "VAT_MAIN"), rel_type="has_item",
                   dst=("report_item", "VAT_MAIN.L11")),
    RelationRecord(src=("report", "VAT_MAIN"), rel_type="has_item",
                   dst=("report_item", "VAT_MAIN.L12")),
    RelationRecord(src=("report", "VAT_MAIN"), rel_type="has_item",
                   dst=("report_item", "VAT_MAIN.L13")),
    RelationRecord(src=("report", "VAT_MAIN"), rel_type="has_item",
                   dst=("report_item", "VAT_MAIN.L20")),
    RelationRecord(src=("report", "VAT_MAIN"), rel_type="has_item",
                   dst=("report_item", "VAT_MAIN.L23")),
    RelationRecord(src=("report", "VAT_AUX_1"), rel_type="has_item",
                   dst=("report_item", "VAT_AUX_1.R1")),
    RelationRecord(src=("report", "VAT_AUX_1"), rel_type="has_item",
                   dst=("report_item", "VAT_AUX_1.R2")),
    RelationRecord(src=("report_item", "VAT_MAIN.L12"), rel_type="derived_from",
                   dst=("template_field", "TPL_VAT_INPUT.TAX_AMT")),
    RelationRecord(src=("report_item", "VAT_MAIN.L13"), rel_type="derived_from",
                   dst=("template", "TPL_RETAINED_CONFIRM")),
    RelationRecord(src=("report_item", "VAT_MAIN.L23"), rel_type="derived_from",
                   dst=("column", "ods.filing_record.payable")),
]

# ---- scenario_config：场景 + uses ----

SCENARIO_CONFIG: list = [
    EntityRecord(type="scenario", key="SCN_MONTHLY_FILING", name="月度增值税申报"),
    EntityRecord(type="scenario", key="SCN_INPUT_CHECK", name="进项抵扣核查"),
    EntityRecord(type="scenario", key="SCN_RETAINED_REFUND", name="留抵退税申请"),
    RelationRecord(src=("scenario", "SCN_MONTHLY_FILING"), rel_type="uses",
                   dst=("template", "TPL_FILING_MAIN")),
    RelationRecord(src=("scenario", "SCN_MONTHLY_FILING"), rel_type="uses",
                   dst=("template", "TPL_VAT_INPUT")),
    RelationRecord(src=("scenario", "SCN_MONTHLY_FILING"), rel_type="uses",
                   dst=("template", "TPL_VAT_OUTPUT")),
    RelationRecord(src=("scenario", "SCN_INPUT_CHECK"), rel_type="uses",
                   dst=("template", "TPL_VAT_INPUT")),
    RelationRecord(src=("scenario", "SCN_RETAINED_REFUND"), rel_type="uses",
                   dst=("template", "TPL_RETAINED_CONFIRM")),
]

SYNC_SOURCES: dict[str, list] = {
    "template_center": TEMPLATE_CENTER,
    "metadata": METADATA,
    "report_center": REPORT_CENTER,
    "scenario_config": SCENARIO_CONFIG,
}

# ---- YAML：纯人工 concept/system + 覆盖层 ----

YAML_FILES: dict[str, str] = {
    "concepts/vat_core.yaml": """\
- id: concept:vat.input_credit
  name: 进项税额抵扣
  aliases: [进项抵扣, 抵进项, 认证抵扣]
  abbr: [JXDK]
  definition: 一般纳税人购进货物、服务、无形资产或不动产，取得合规扣税凭证后，从当期销项税额中抵减的进项税额。
  why: 影响当期应纳税额，是增值税申报的核心环节。
  l0: true
  owner: tax-domain
  refers_to: [template:TPL_VAT_INPUT]
- id: concept:vat.input_transfer_out
  name: 进项税额转出
  aliases: [进项转出, 抵扣转出]
  definition: 已抵扣进项税额因用途改变用于简易计税、免税项目或集体福利而转回，不能再从销项税额中抵减。
  l0: true
  owner: tax-domain
- id: concept:vat.output_tax
  name: 销项税额
  aliases: [销项]
  definition: 纳税人发生应税销售行为，按销售额与适用税率计算并向购买方收取的增值税额。
  l0: true
  owner: tax-domain
- id: concept:vat.retained_credit
  name: 期末留抵税额
  aliases: [留抵, 留抵税额]
  abbr: [LDSE]
  default_reading: [留抵]
  definition: 当期销项税额不足抵扣进项税额时，尚未抵扣完、结转下期继续抵扣的进项税额。
  l0: true
  owner: tax-domain
  refers_to: [report_item:VAT_MAIN.L20]
  disambiguation:
    - not: concept:vat.retained_refund
      hint: 指结转下期继续抵扣的余额
- id: concept:vat.retained_refund
  name: 留抵退税
  aliases: [{value: 留抵, match_mode: context}]
  abbr: [LDTS]
  definition: 符合条件的增量或存量留抵税额，按政策规定向税务机关申请退还。
  l0: true
  owner: tax-domain
  refers_to: [scenario:SCN_RETAINED_REFUND, system:tax.hall]
  disambiguation:
    - not: concept:vat.retained_credit
      hint: 留抵退税是把留抵税额退还给纳税人的政策
- id: concept:vat.small_scale
  name: 小规模纳税人
  aliases: [小规模]
  definition: 年应征增值税销售额未超过规定标准、会计核算不健全的纳税人，按简易办法依征收率缴纳增值税。
  l0: true
  owner: tax-domain
  related_to: [concept:vat.exemption]
- id: concept:vat.general_taxpayer
  name: 一般纳税人
  definition: 年应征增值税销售额超过规定标准、会计核算健全的纳税人，适用一般计税方法按税率计算销项与进项。
  l0: true
  owner: tax-domain
- id: concept:vat.tax_rate
  name: 增值税税率
  aliases: [税率]
  default_reading: [税率]
  definition: 一般计税方法下按应税销售行为适用的比例，如销售货物13%、交通运输9%、现代服务6%。
  l0: true
  owner: tax-domain
  related_to: [concept:vat.general_taxpayer]
  disambiguation:
    - not: concept:vat.levy_rate
      hint: 一般计税方法适用税率
- id: concept:vat.levy_rate
  name: 征收率
  aliases: [税率, 征收率]
  definition: 简易计税方法适用的比例，小规模纳税人按3%征收率缴纳增值税。
  l0: true
  owner: tax-domain
  related_to: [concept:vat.small_scale]
  disambiguation:
    - not: concept:vat.tax_rate
      hint: 小规模纳税人适用征收率，一般纳税人适用税率
- id: concept:vat.deduction_voucher
  name: 扣税凭证
  aliases: [抵扣凭证, 扣税凭证]
  definition: 增值税专用发票、海关进口增值税专用缴款书、农产品收购发票等可用于抵扣进项税额的凭证。
  l0: true
  owner: tax-domain
- id: concept:vat.exemption
  name: 增值税免税
  aliases: [{value: 免税, match_mode: context}]
  definition: 对属于增值税征税范围的应税销售行为给予不征收增值税的优惠。
  owner: tax-domain
- id: concept:vat.filing
  name: 增值税申报
  aliases: [纳税申报]
  definition: 按纳税期将销售额、进项、销项、应纳税额等信息填报增值税申报表并报送税务机关。
  l0: true
  owner: tax-domain
""",
    "concepts/systems.yaml": """\
- id: system:tax.hall
  name: 办税服务厅
  definition: 税务机关受理申报、发票、退税等业务的线下与线上服务渠道。
  owner: tax-domain
- id: system:invoice.platform
  name: 发票综合服务平台
  aliases: [发票平台, 综合服务平台]
  abbr: [FPPT]
  definition: 纳税人开具、勾选、查验发票的统一平台。
  l0: true
  owner: tax-domain
""",
    "templates/overlays.yaml": """\
- id: template:TPL_VAT_INPUT
  owner: tax-domain
  aliases: [进项采集模板, 进项模板]
  definition: 月度进项发票采集模板，按发票逐行采集。
  caliber: 只采集当期勾选认证的发票，不含海关缴款书。
  fields:
    - id: template_field:TPL_VAT_INPUT.TAX_AMT
      aliases: [进项税额]
      definition: 发票票面税额
- id: template:TPL_FILING_MAIN
  owner: tax-domain
  aliases: [主表模板]
  definition: 增值税及附加税费申报表主表的数据采集模板。
""",
    "report_items/overlays.yaml": """\
- id: report_item:VAT_MAIN.L13
  owner: tax-domain
  aliases: [上期留抵]
  definition: 上期结转的留抵税额填列行。
- id: report_item:VAT_MAIN.L20
  owner: tax-domain
  aliases: [期末留抵]
  definition: 期末尚未抵扣完的留抵税额填列行。
""",
}

ALL_ENTITY_KEYS: set[str] = {
    f"{r.type}:{r.key}" for r in TEMPLATE_CENTER if isinstance(r, EntityRecord)
} | {f"{r.type}:{r.key}" for r in METADATA if isinstance(r, EntityRecord)
} | {f"{r.type}:{r.key}" for r in REPORT_CENTER if isinstance(r, EntityRecord)
} | {f"{r.type}:{r.key}" for r in SCENARIO_CONFIG if isinstance(r, EntityRecord)
} | {
    "concept:vat.input_credit", "concept:vat.input_transfer_out",
    "concept:vat.output_tax", "concept:vat.retained_credit",
    "concept:vat.retained_refund", "concept:vat.small_scale",
    "concept:vat.general_taxpayer", "concept:vat.tax_rate",
    "concept:vat.levy_rate", "concept:vat.deduction_voucher",
    "concept:vat.exemption", "concept:vat.filing",
    "system:tax.hall", "system:invoice.platform",
    "template_field:TPL_VAT_INPUT.TAX_AMT",  # 覆盖层 fields 目标（已同步实体）
}


def seed_reference_org(backend, org_id: str, settings, *, repo_dir) -> dict:
    """参考词典落库（真实管线全链：四源 run_sync + YAML run_yaml_sync）。"""
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync
    from pathlib import Path

    results = {}
    for name, records in SYNC_SOURCES.items():
        results[name] = run_sync(
            backend, org_id, _ListAdapter(name, records),
            settings=settings, snapshot=list(records), now=NOW,
        )["status"]
    repo = Path(repo_dir)
    repo.mkdir(parents=True, exist_ok=True)
    for rel, content in YAML_FILES.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    results["yaml"] = run_yaml_sync(
        backend, org_id, YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
        settings=settings, now=NOW,
    )["status"]
    return results
