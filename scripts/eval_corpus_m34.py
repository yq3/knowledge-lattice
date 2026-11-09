#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""m3-4 A 组：corpus.jsonl 扩容批（39 → 73 docs——TC-EVAL-02 语料侧成对扩容）。

一次性数据构建脚本（幂等：按 doc_id 去重合并后重写 corpus.jsonl）。新增三组：
- gk-zh-m01..09（纯中 9 篇：电子发票/认证勾选/纳税信用/欠税出境/稽查自查/
  发票挂失/小规模免征/预缴税款/减免备查）；
- gk-en-m01..12（纯英 12 篇：VAT invoice red-reversal/non-resident withholding/
  transfer pricing docs/customs valuation/export refund calc/digital services VAT/
  expatriate IIT annual reconciliation/R&D super deduction/tax treaty procedure/
  luxury consumption tax/stamp duty property transfer/filing calendar）；
- gk-mx-m01..13（中英混排 13 篇：平台经济/转让定价/非居民股息/税收协定/
  常设机构/奢侈品消费税/关税配额/证券印花税/环保税排放口/车船税/社保基数/
  出口退税无纸化/税务行政处罚听证）。

内容为合成领域文本（待决-1 真实语料未到位先行——沿 M1 语料同口径）；
每篇带 region/tax_type 维度（值域与既有矩阵一致：region CN/OS、tax_type VAT）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"

CN_VAT = {"region": ["CN"], "tax_type": ["VAT"]}
CN = {"region": ["CN"]}
OS = {"region": ["OS"]}
OS_VAT = {"region": ["OS"], "tax_type": ["VAT"]}

NEW_DOCS: list[dict] = [
    # ---- 纯中（gk-zh-m*）----
    {
        "doc_id": "gk-zh-m01", "title": "电子发票（数电票）开具与交付规范",
        "dataset": "ds:vat_lib", "dims": CN_VAT,
        "text": (
            "全面数字化的电子发票（简称数电票）通过电子发票服务平台开具，无需预先领取"
            "纸质票种，开票额度实行赋码管理。纳税人登录电子税务局进入发票业务模块，选择"
            "蓝字发票开具，填写购买方信息、项目名称、规格型号、金额税率后提交即完成开具。"
            "数电票交付支持邮箱交付、二维码交付和下载打印等多种方式，受票方以电子发票的"
            "XML数据文件为报销入账归档依据。开票额度不足时可申请调整，税务机关按纳税人"
            "信用与经营情况动态核定。红字发票应当通过红字发票确认单流程处理。"
        ),
    },
    {
        "doc_id": "gk-zh-m02", "title": "增值税专用发票认证勾选操作流程",
        "dataset": "ds:vat_lib", "dims": CN_VAT,
        "text": (
            "增值税专用发票实行综合服务平台勾选确认抵扣方式。纳税人登录增值税发票综合"
            "服务平台，在抵扣勾选模块按开票日期区间查询待勾选发票，核对发票代码、号码、"
            "金额与票面信息一致后批量勾选并确认签名。勾选确认的发票信息在申报期结束后"
            "自动归集到申报表附列资料，当期申报抵扣进项税额。异常发票（如作废、失控、"
            "红冲）不得勾选抵扣。未按期勾选确认的专用发票超过认证期限将无法抵扣进项"
            "税额，纳税人应当建立进项发票台账按月核对勾选状态。"
        ),
    },
    {
        "doc_id": "gk-zh-m03", "title": "纳税信用等级评定标准与复评程序",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "纳税信用级别按年度评价指标从高到低分为A、B、M、C、D五级。评价指标包括纳"
            "税人信用历史信息、税务内部信息与外部信息，主要扣分项有逾期申报、欠缴税款、"
            "发票违规与稽查补税。A级信用需年度评价指标得分九十以上且无严重失信记录，"
            "新设立企业适用M级。纳税人对评价结果有异议的，可在结果公布之日起向主管税"
            "务机关申请复评，税务机关受理后逐项核实并在规定时限内反馈复评结论。信用级"
            "别影响发票领用限额、出口退税管理与融资授信等多方面待遇。"
        ),
    },
    {
        "doc_id": "gk-zh-m04", "title": "欠税公告与阻止出境管理规定",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "纳税人欠缴应纳税款的，税务机关应当责令限期缴纳并从滞纳税款之日起按日加收"
            "滞纳金。欠税纳税人未结清税款、滞纳金又不提供担保的，税务机关可以通知出境"
            "管理机关阻止其法定代表人出境。欠税金额达到公告标准的，税务机关在办税场所"
            "和新闻媒体定期公告欠税名单。纳税人结清欠税或提供纳税担保后，税务机关应当"
            "及时解除阻止出境措施并停止公告。欠税信息同时纳入纳税信用评价，直接影响信"
            "用级别评定结果。"
        ),
    },
    {
        "doc_id": "gk-zh-m05", "title": "税务稽查选案与自查补税程序",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "税务稽查选案来源包括推送案源、督办案源、交办案源与自选题源，税收大数据风"
            "险扫描结果作为推送案源的主要来源。稽查局立案检查前，对风险等级较低的纳税"
            "人可先行启动自查程序，下达税务事项通知书告知自查期限，纳税人自查发现少缴"
            "税款的应当自行补正申报并补缴税款。自查补税仍面临被立案检查的可能。稽查实"
            "施环节可采取调取账簿、实地检查、询问当事人与银行账户查询等措施，纳税人应"
            "当配合并提供有关资料。"
        ),
    },
    {
        "doc_id": "gk-zh-m06", "title": "发票丢失挂失与补办流程",
        "dataset": "ds:vat_lib", "dims": CN_VAT,
        "text": (
            "使用税控系统的纳税人丢失已开具的增值税专用发票发票联和抵扣联的，应当于丢"
            "失当日书面报告主管税务机关并登报声明作废。凭报纸挂失声明与情况说明向税务"
            "机关申请补办，购买方可凭销售方提供的相应专用发票记账联复印件及销售方主管"
            "税务机关出具的证明作为增值税进项税额抵扣凭证。丢失空白发票的应当于丢失当"
            "日向税务机关报告并办理损失挂失，涉及被盗的还应向公安机关报案并取得报案证"
            "明。未按规定报告丢失发票将按发票管理办法处罚。"
        ),
    },
    {
        "doc_id": "gk-zh-m07", "title": "小规模纳税人免征增值税优惠政策",
        "dataset": "ds:vat_lib", "dims": CN_VAT,
        "text": (
            "小规模纳税人发生增值税应税销售行为，月销售额未超过免征额标准的，免征增值"
            "税；超过标准的按全额计算缴纳。适用减免的纳税人无需单独备案，在增值税纳税"
            "申报表中如实填报减免税额即可，同时应当留存销售额核算依据备查。开具增值税"
            "专用发票的部分不能享受免税，应按征收率缴纳。小规模纳税人也可放弃免税选择"
            "开具专用发票，一经选择三十六个月内不得变更。兼营免税与应税项目的应当分别"
            "核算，未分别核算的不得享受免税。"
        ),
    },
    {
        "doc_id": "gk-zh-m08", "title": "增值税预缴税款事项办理指南",
        "dataset": "ds:vat_lib", "dims": CN_VAT,
        "text": (
            "纳税人跨县（市）提供建筑服务、出租不动产或转让不动产的，应按照规定的预征"
            "率在建筑服务发生地或不动产所在地预缴增值税。建筑服务适用一般计税方法的以"
            "取得的全部价款和价外费用扣除支付的分包款后的余额按百分之二预征率预缴；出"
            "租不动产按百分之三预征率以不含税租金计算。预缴税款时应当填写增值税预缴"
            "税款表并提交与分包方签订的分包合同、发票等资料。预缴税款可在当期应纳税额"
            "中抵减，未抵减完的可结转下期继续抵减。"
        ),
    },
    {
        "doc_id": "gk-zh-m09", "title": "税收减免事项留存备查资料管理",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "享受税收优惠实行自行判别、申报享受、相关资料留存备查的办理方式，纳税人无"
            "需事前备案即可依法享受减免。留存备查资料应当与税收优惠事项密切相关，包括"
            "证明纳税人符合优惠条件的资格资质文件、核算记录与项目明细等。资料留存期限"
            "为享受优惠事项后若干年内，税务机关核查时应当按时提供。纳税人实际情形不符合"
            "优惠条件的应当停止享受并更正申报，虚假享受优惠将被追缴税款并加收滞纳金，"
            "同时影响纳税信用评价。"
        ),
    },
    # ---- 纯英（gk-en-m*）----
    {
        "doc_id": "gk-en-m01", "title": "VAT Invoice Red-Invoice Reversal Guide",
        "dataset": "ds:vat_lib", "dims": CN_VAT,
        "text": (
            "When a sale is cancelled, a discount is granted, or an invoice is issued with "
            "incorrect content, the seller must issue a red-letter invoice (credit note) to "
            "reverse the original blue invoice. For ordinary reversal the seller applies for "
            "a red invoice information form through the invoicing platform, stating the "
            "corresponding blue invoice code and number. Where the buyer has already "
            "certified the original invoice, the buyer must obtain a red invoice confirmation "
            "sheet before the seller may issue the red invoice. Both parties must adjust "
            "output VAT and input VAT respectively in the current tax period, and retain the "
            "red invoice and confirmation sheet for future inspection."
        ),
    },
    {
        "doc_id": "gk-en-m02", "title": "Withholding Income Tax for Non-Resident Enterprises",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "A non-resident enterprise without an establishment in China receiving dividends, "
            "interest, royalties or rental income from Chinese sources is subject to "
            "withholding income tax at the statutory rate, generally ten percent. The Chinese "
            "payer acts as the withholding agent and must withhold the tax at each payment "
            "and file the withholding return within seven days following the payment date. "
            "Where a applicable tax treaty provides a reduced rate, the non-resident must "
            "submit a treaty benefit claim form together with a tax residency certificate "
            "before payment. Failure to withhold makes the withholding agent liable for the "
            "unpaid tax plus late payment surcharges."
        ),
    },
    {
        "doc_id": "gk-en-m03", "title": "Transfer Pricing Documentation Requirements",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "Related-party transactions must follow the arm's length principle. Enterprises "
            "whose annual related-party transactions exceed the prescribed thresholds must "
            "prepare contemporaneous transfer pricing documentation comprising a master file, "
            "a local file and a special issue file for cost sharing or thin capitalisation. "
            "The documentation should describe the group organisational structure, functional "
            "analysis of each party, the selection and application of transfer pricing "
            "methods, and comparability analysis. The local file must be completed before the "
            "annual corporate income tax filing deadline and submitted to the tax authority "
            "upon request within thirty days. Missing or defective documentation may lead to "
            "transfer pricing adjustments and surcharges."
        ),
    },
    {
        "doc_id": "gk-en-m04", "title": "Customs Valuation Methods for Imported Goods",
        "dataset": "ds:vat_lib", "dims": OS,
        "text": (
            "Customs value for imported goods is determined primarily by the transaction value "
            "method, being the price actually paid or payable for the goods when sold for "
            "export, adjusted for certain additions such as commissions, packing costs and "
            "royalties. Where the transaction value cannot be used, the following methods "
            "apply in sequence: transaction value of identical goods, transaction value of "
            "similar goods, deductive value based on the resale price in the domestic market, "
            "computed value based on production cost plus profit, and fall-back method. "
            "Special relationships between buyer and seller do not automatically reject the "
            "transaction value provided the relationship did not influence the price."
        ),
    },
    {
        "doc_id": "gk-en-m05", "title": "Export VAT Refund Calculation Methods",
        "dataset": "ds:vat_lib", "dims": OS_VAT,
        "text": (
            "Export goods are subject to VAT refund or exemption depending on the trader "
            "category. Production enterprises apply the免抵退 method under which the input "
            "VAT attributable to exports offsets output VAT on domestic sales, with any "
            "excess refunded at the export rebate rate. Foreign trade enterprises apply the "
            "免退 method and claim refunds based on the purchase invoice amount multiplied by "
            "the applicable rebate rate. The rebate rate varies by commodity classification "
            "and is announced by the Ministry of Finance. Exporters must collect the export "
            "declaration form, sales contract and banking receipt within the prescribed "
            "period declared for the refund claim, otherwise the claim expires."
        ),
    },
    {
        "doc_id": "gk-en-m06", "title": "Cross-Border Digital Services VAT Treatment",
        "dataset": "ds:vat_lib", "dims": OS_VAT,
        "text": (
            "Cross-border supply of services and intangible assets to domestic consumers is "
            "subject to VAT on a reverse-charge or withholding basis. Where the overseas "
            "seller has no establishment within China, the domestic purchaser is obligated to "
            "withhold VAT at the applicable rate, typically six percent for modern services. "
            "Sales to domestic producers for use in production are exempt to avoid cascading "
            "taxation. Overseas electronic commerce operators selling digital services to "
            "domestic individual consumers may register through the simplified e-service "
            "platform and remit VAT on a quarterly basis. The place of supply rules determine "
            "whether the recipient is located within the taxing jurisdiction."
        ),
    },
    {
        "doc_id": "gk-en-m07", "title": "Expatriate Individual Income Tax Annual Reconciliation",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "Foreign employees working in China must complete the annual individual income "
            "tax reconciliation between March and June following the tax year. Residential "
            "individuals staying more than 183 days aggregate annual benefits from worldwide "
            "income taxation with foreign tax credit relief, while non-resident individuals "
            "are taxed on China-source income only. Housing allowances, home leave flights, "
            "children's education and language training subsidies may remain temporarily "
            "exempt during the transition period subject to filing requirements. The "
            "reconciliation return consolidates comprehensive income from salaries, author's "
            "remuneration and royalties, applies the cumulative withholding computation, and "
            "settles any balance of tax payable or refundable."
        ),
    },
    {
        "doc_id": "gk-en-m08", "title": "Research and Development Super Deduction Compliance",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "Enterprises engaged in qualifying research and development activities may claim "
            "an additional deduction equal to one hundred percent of the actual R&D expenses "
            "when computing taxable income, effectively deducting twice the amount spent. "
            "Qualifying expenses include directly consumed materials, personnel salaries of "
            "R&D staff, depreciation of instruments used exclusively for R&D, and outsourced "
            "research capped at a proportion of total spending. Enterprises must maintain an "
            "auxiliary ledger recording each project's expenses by category, retain project "
            "approval documents, and the negative list industries are excluded. The claim is "
            "made through the annual corporate income tax return without prior approval."
        ),
    },
    {
        "doc_id": "gk-en-m09", "title": "Tax Treaty Benefit Application Procedure",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "Non-resident taxpayers seeking reduced withholding rates under an applicable "
            "tax treaty follow the self-assessment enjoy and retain documentation procedure. "
            "Before income is paid, the beneficiary must submit the treaty benefit information "
            "reporting form to the withholding agent together with a tax residency certificate "
            "issued by the competent authority of the other contracting state in the same "
            "calendar year. The withholding agent reviews the documents, applies the treaty "
            "rate at payment, and retains the documents for inspection instead of filing them "
            "with the tax bureau. If qualification is later found incorrect, the taxpayer must "
            "voluntarily amend and pay the tax shortfall within a prescribed period to avoid "
            "penalties."
        ),
    },
    {
        "doc_id": "gk-en-m10", "title": "Luxury Goods Consumption Tax Scope",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "Consumption tax in China applies to a defined catalogue of luxury and "
            "environmentally sensitive goods including cigarettes, alcoholic liquor, premium "
            "cosmetics, jewellery, fireworks, refined oil products, passenger cars, motorcycles, "
            "golf equipment, high-end watches, yachts, disposable wooden chopsticks, solid "
            "wood flooring, batteries and coatings. The tax is levied at production, "
            "commissioned processing or import stages rather than at retail, with either ad "
            "valorem rates, specific duty per unit, or compound rates combining both. Premium "
            "cosmetics are defined as products meeting prescribed unit price thresholds. "
            "Refined oil categories cover gasoline, diesel and aviation kerosene taxed per "
            "liter."
        ),
    },
    {
        "doc_id": "gk-en-m11", "title": "Stamp Duty on Property Transfer Documents",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "Stamp duty is levied on taxable documents executed or received within China. "
            "For property transfer documents including sale contracts for real estate, the "
            "rate is five ten-thousandths of the contract value. Equity transfer documents "
            "for listed companies are stamped on both parties at one thousandth of the "
            "transaction value, with securities transaction stamp duty collected by the "
            "securities registration institution at settlement. Business account books are "
            "taxed at a fixed amount per funded capital record. Taxpayers must compute stamp "
            "duty on a quarterly or per-transaction basis and file within fifteen days after "
            "the period end. Electronic documents bearing the same legal effect are equally "
            "taxable."
        ),
    },
    {
        "doc_id": "gk-en-m12", "title": "Monthly Tax Filing Calendar and Deadlines",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "Taxpayers must observe the statutory monthly filing calendar. VAT and consumption "
            "tax returns are due within the first fifteen days of the month following the "
            "period; corporate income tax prepayments follow the same window. Individual "
            "income tax withholding returns are filed by the withholding agent within fifteen "
            "days after each month end. Where the deadline falls on a public holiday it is "
            "extended to the next working day. Quarterly small-scale VAT filers report in "
            "January, April, July and October. Annual reconciliation returns for corporate "
            "income tax are due within five months after the tax year ends. Late filing "
            "triggers daily surcharges and may affect the tax credit rating."
        ),
    },
    # ---- 中英混排（gk-mx-m*）----
    {
        "doc_id": "gk-mx-m01", "title": "平台经济 platform economy 税收征管要点",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "平台经济（platform economy）从业者取得的收入应当依法申报纳税。网络主播、"
            "灵活用工人员通过平台（platform）取得的服务收入，由平台企业按劳务报酬"
            "代扣代缴个人所得税（withholding individual income tax）。平台内经营者"
            "销售货物应当按规定开具发票并申报增值税。税务机关依托税收大数据"
            "（tax big data）对平台交易实施监测，对隐匿收入的开展风险应对。跨区域"
            "经营的平台企业按纳税地点规则划分收入，不得拆分交易规避税收。"
        ),
    },
    {
        "doc_id": "gk-mx-m02", "title": "转让定价 transfer pricing 关联申报实务",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "企业向税务机关报送年度关联业务往来报告表（related-party transaction "
            "return）时，应当披露关联方（related parties）信息与各类关联交易金额。"
            "关联劳务（related-party services）应当区分受益性劳务与非受益性劳务，"
            "非受益性劳务支付不得税前扣除。集团内无形资产（intangibles）许可使用费"
            "应当与经济价值创造相匹配，向境外关联方支付的特许权使用费需关注受益性"
            "测试与境外税收扣除凭证。关联申报数据异常将提高特别纳税调整风险等级。"
        ),
    },
    {
        "doc_id": "gk-mx-m03", "title": "非居民企业 non-resident enterprise 股息红利税务处理",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "非居民企业（non-resident enterprise）从中国居民企业取得的股息、红利"
            "（dividends）收入，按百分之十的税率缴纳预提所得税（withholding tax）。"
            "与我国签订税收协定（tax treaty）的国家或地区居民，符合受益所有人"
            "（beneficial owner）条件的可适用协定优惠税率如百分之五。分配利润的"
            "居民企业为扣缴义务人，应当在利润分配决定之日代扣代缴。非居民企业主张"
            "协定待遇应当报送相关资料并接受后续管理，利用导管公司（conduit company）"
            "不当获取优惠待遇的将被否定并追缴税款。"
        ),
    },
    {
        "doc_id": "gk-mx-m04", "title": "税收协定 tax treaty 相互协商程序 MAP",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "相互协商程序（Mutual Agreement Procedure, MAP）是税收协定（tax treaty）"
            "提供的争议解决机制。当纳税人认为缔约对方或我国的措施导致或将导致不符合"
            "协定规定的征税（taxation not in accordance with the treaty）时，可向"
            "其居民国主管当局（competent authority）提出申请。我国纳税人应通过省级"
            "税务机关向国家税务总局提交申请，说明案情并附相关材料。双方主管当局通过"
            "协商力求达成解决（resolution），结果可能包括消除双重征税（elimination "
            "of double taxation）。申请应在首次通知征税措施之日起三年内提出。"
        ),
    },
    {
        "doc_id": "gk-mx-m05", "title": "常设机构 permanent establishment 判定标准",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "常设机构（permanent establishment, PE）是税收协定中判定缔约国一方对"
            "另一方企业利润征税权的关键概念。固定场所型常设机构要求具备营业场所"
            "（fixed place of business）、场所相对固定且通过该场所开展核心经营活"
            "动。工程型常设机构以建筑工地（construction site）连续超过六个月为标"
            "准。非独立代理人（dependent agent）经常性以企业名义签订合同亦可构成"
            "代理型常设机构。准备性辅助性活动（preparatory or auxiliary activities）"
            "例外不构成常设机构。构成常设机构的企业应就归属于该机构的利润"
            "（attributable profits）在我国缴纳企业所得税。"
        ),
    },
    {
        "doc_id": "gk-mx-m06", "title": "奢侈品消费税 luxury goods 消费税调整动态",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "消费税（consumption tax）改革方向包括后移征收环节（shift of levy stage）"
            "与扩大高档消费品（luxury goods）税目范围。高档化妆品（premium "
            "cosmetics）已按高档美容修饰类化妆品界定征收，超豪华小汽车（super-luxury "
            "cars）在零售环节加征百分之十的消费税。贵重首饰及珠宝玉石（jewellery）"
            "在零售环节按百分之五征收。征收环节后移将改变纳税地点与入库级次，试点"
            "品目由生产环节调整为批发或零售环节（retail stage）征收。超豪华小汽车"
            "零售环节征税以每辆不含增值税零售价格一百三十万元为界。"
        ),
    },
    {
        "doc_id": "gk-mx-m07", "title": "关税配额 tariff-rate quota 与滑准税",
        "dataset": "ds:vat_lib", "dims": OS,
        "text": (
            "关税配额（tariff-rate quota, TRQ）制度下，配额内进口适用较低税率"
            "（in-quota rate），配额外进口适用最惠国税率或普通税率（out-of-quota "
            "rate）。我国对部分农产品（如小麦、玉米、大米、食糖）与化肥实施关税"
            "配额管理，配额总量由商务主管部门公布。滑准税（sliding duty）税率随进"
            "口货物完税价格（dutiable value）反向变化，价格越高税率越低，棉花进口"
            "适用滑准税。配额申请应当在规定期限内向指定机构提交，配额使用情况需按"
            "要求报告。"
        ),
    },
    {
        "doc_id": "gk-mx-m08", "title": "证券交易印花税 securities transaction stamp duty",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "证券交易印花税（securities transaction stamp duty）对在依法设立的证券"
            "交易所、全国中小企业股份转让系统成交的股票（stocks）交易征收，仅对卖"
            "出方（seller only）征收，税率为千分之一。印花税由证券登记结算机构"
            "（securities depository）代扣代缴。经国务院批准可对印花税实施减征"
            "（reduction）或暂免征收，历史上多次运用该工具调节市场活跃度。证券交易"
            "印花税收入归中央与地方按比例分享。纳税人应当区分证券交易印花税与产权"
            "转移书据印花税的不同税目与税率。"
        ),
    },
    {
        "doc_id": "gk-mx-m09", "title": "环保税 environmental protection tax 排放口申报",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "环境保护税（environmental protection tax）对直接向环境排放应税污染物"
            "（taxable pollutants）的企事业单位征收。纳税人应当按排放口（discharge "
            "outlet）分别申报大气污染物（air pollutants）、水污染物与固体废物。"
            "应税大气污染物按污染当量数从大到小排序，对前三项征收（top three "
            "pollutants）。污染物排放量按在线监测数据（online monitoring data）、"
            "排污系数或抽样测算方法顺次确定。噪声按超标分贝数计算。按季申报，自"
            "季度终了之日起十五日内报缴。依法设立的城乡污水集中处理场所达标排放"
            "不缴纳环保税。"
        ),
    },
    {
        "doc_id": "gk-mx-m10", "title": "车船税 vehicle and vessel tax 申报缴纳",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "车船税（vehicle and vessel tax）对依法登记的车辆、船舶征收，按辆、按"
            "整备质量吨位（gross mass）或净吨位（net tonnage）定额计算。乘用车按"
            "排气量分档确定年基准税额（annual benchmark tax amount），新能源车辆"
            "（new energy vehicles）免征或减半征收。从事机动车第三者责任强制保险"
            "的保险机构为车船税扣缴义务人（withholding agent），在收取保险费时代"
            "收车船税并开具注明已收税款信息的保险单。依法不需要登记的在机场、港口"
            "内部场所行驶或作业的车船免征。车船税按年申报，分月计算，一次性缴清。"
        ),
    },
    {
        "doc_id": "gk-mx-m11", "title": "社保 social insurance 缴费基数核定",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "社会保险费（social insurance contributions）缴费基数（contribution "
            "base）按职工本人上年度月平均工资核定，新入职职工以起薪当月工资为基数。"
            "缴费基数设有上下限（upper and lower limits），分别为当地全口径城镇单位"
            "就业人员平均工资的百分之三百与百分之六十。用人单位以全部职工缴费基数"
            "之和为单位缴费基数（employer contribution base）。社保缴费由税务部门"
            "统一征收（collected by tax authorities），用人单位自行申报缴费。未足"
            "额缴纳的由征收机构责令限期补缴并加收滞纳金（late fees）。"
        ),
    },
    {
        "doc_id": "gk-mx-m12", "title": "出口退税 export rebate 无纸化申报",
        "dataset": "ds:vat_lib", "dims": OS_VAT,
        "text": (
            "出口退（免）税实行无纸化申报（paperless declaration），出口企业通过"
            "电子税务局提交出口退税申报数据与电子凭证（electronic documents），无"
            "需报送纸质资料。申报前应当完成出口退（免）税备案，一、二类出口企业"
            "可享受申报免报送纸质凭证与优先审核待遇。申报数据包括出口货物报关单"
            "（export customs declaration）、增值税专用发票与出口发票信息。税务"
            "机关受理后经审核退库（refund processing），正常办理时限压缩至平均"
            "数个工作日内。分类管理类别（management category）低的出口企业审核"
            "更严。"
        ),
    },
    {
        "doc_id": "gk-mx-m13", "title": "税务行政处罚 tax administrative penalty 听证权利",
        "dataset": "ds:vat_lib", "dims": CN,
        "text": (
            "税务机关作出较大数额罚款（relatively large fines）等行政处罚决定前，"
            "应当告知当事人有要求听证（right to a hearing）的权利。当事人在告知书"
            "送达之日起五日内书面提出听证申请的，税务机关应当在收到申请后规定期限"
            "内组织听证，听证费用由税务机关承担。当事人可以亲自参加听证，也可以"
            "委托代理人（agent）参加。听证过程中当事人可进行陈述、申辩与质证"
            "（statement, defence and cross-examination）。税务机关应当根据听证"
            "情况作出决定。当事人对处罚决定不服的，可依法申请行政复议"
            "（administrative reconsideration）或提起行政诉讼。"
        ),
    },
]


def main() -> int:
    path = EVAL_DIR / "corpus.jsonl"
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["doc_id"]] = row
    added = 0
    for doc in NEW_DOCS:
        assert doc["doc_id"] not in rows, f"重复 doc_id：{doc['doc_id']}"
        rows[doc["doc_id"]] = doc
        added += 1
    ordered = sorted(rows.values(), key=lambda r: r["doc_id"])
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in ordered) + "\n",
        encoding="utf-8",
    )
    print(f"corpus.jsonl: {len(ordered)} docs（+{added}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
