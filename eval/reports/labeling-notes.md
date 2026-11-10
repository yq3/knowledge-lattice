# M1 黄金集标注记录（TC-EVAL-01——M1-5 校准实验输入）

- 标注时间：2026-10-25（M1-4 段）；标注人：开发自标（合成语料——待决-1 真实
  语料未到位先行，design 既有注记；真实 query 标注随语料到位后替换/扩充）。
- 语料：`eval/corpus.jsonl`——39 docs，分类拆解：纯中 12 VAT 域（gk-vat-01~12）
  + 纯英 6 费用域（gk-exp-01~06）+ **中文费用域 4（gk-exp-zh1~4——v2 增补，
  zh 费用 query 的可达标注面）** + 中英混排 14（gk-mix-01~14，其中 5 篇
  gk-vat-0x 附英文索引句——en query 可达性）+ GBK 编码样例 1（gk-enc-01）
  + 多 chunk 文档 2（gk-multi-01/02）；维度挂 region（CN/OS）与 tax_type
  （VAT/空值）双形态；`gk-multi-*` 两篇为 2-chunk 文档（seq=1/2 是标注锚点）。
- 黄金集：`eval/golden.jsonl`——28 条 query（zh 12 / en 8 / mix 8；全部
  multi-token——jieba 切分 ≥2，m1-1 Tester 观察项覆盖）。

## 标注规则

1. **命中 chunk** = 「能独立回答该 query 的最小块」：单 chunk 文档标 (doc, 1)；
   多 chunk 文档按段落主题标 (doc, 1) 或 (doc, 2)；
2. **多标注**（q06~q09、q19、q21）：中英双语文档/成对政策文档同时标——
   Recall 分母为标注集全体，检索命中任一即计；
3. **跨语言标注的可检索性约束**（v2 修订）：中文 query 只标含中文内容的文档
   （英文主体文档仅当 query 为 en/mix 且文档带英文索引句时标注）——当前配方
   无跨语言召回能力（BM25 词面 + token 袋向量均不跨语言），标不可达标注只会
   把「能力空白」误记为「排序回退」；跨语言召回是 M1-5 之后的调参议题；
4. 语料 v2 增补：4 篇中文费用域文档（gk-exp-zh1~4）、5 篇 VAT 文档补英文
   索引句——修订原因同上（q06~q09/q17/q18 首轮基线全 miss）。

## 基线（详见 m1-baseline-*.md）

| 后端 | recall@1 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| sqlite | 0.6607 | 0.8393 | 0.8929 | 0.8345 |
| pg | 0.6071 | 0.7143 | 0.7857 | 0.7277 |

- 已登记差异（G-6/A-17）：PG `to_tsquery` 为 `&` AND 语义（design §5.2 钉死
  口径），含疑问词（是/什么）的中文 query 全词交集不可达 → PG 召回天然偏低
  ——q01 等疑问式 query 在 PG 臂 recall=0 即此差异的直接记录，属 M1-5 校准
  实验的已知输入（候选动作：query 侧停用词滤除 / OR 拼接口径变更需走口径
  变更流程，不得由实现侧单方回退）。
- 运行口径：TokenBagEmbedder(dim=32) token 袋确定性向量（稠密路语义代理——
  FakeEmbedder 哈希向量纯噪声会压过 BM25）；reranker/enhancer=none；
  recall_window=1024；双路召回 + RRF。

## M1-5 衔接

- 阈值/权重调参（分词、五列权重、score_threshold、quality_* 阈值）以本基线
  为对照；黄金集扩充（真实 query 替换合成、TC-EVAL-02 双语三态）按 FR-7 节奏。
- 区分度误报抽查：`scripts/quality_sample.py` 抽样 → 人工复核 → PATCH
  state/manual_tags 落记录（quality_flags 行 + audit_outbox 即记录形态）。

## m3-4 扩容（TC-EVAL-02 M3 完整集——2026-11-08）

- **规模**：语料 39 → **73 docs**（gk-zh-m01..09 纯中 9 + gk-en-m01..12 纯英 12
  + gk-mx-m01..13 混排 13——`scripts/eval_corpus_m34.py` 构建）；黄金集 28 →
  **60 query**（三态分布 zh 24 / en 18 / mix 18——`scripts/eval_golden_m34.py`
  构建，含逐条**可达性机检**：query 实词 token ⊆ 标注语料分词集合，疑问功能
  词不参与比对）。
- **合成候选生成（ragas 选型口径）**：`scripts/eval_synth_m34.py`——LLM 端点
  沿 m2-5 百炼先例（DashScope compatible-mode + `LATTICE_EVAL_LLM_*` env），
  经 ragas `BaseRagasLLM` 接口（与 m3-5 judge 同一抽象——
  `src/knowledge_lattice/eval/ragas_bridge.py`）。**当日真实端点受阻**：本 key
  chat 免费配额耗尽（qwen-plus/qwen-max/qwen-flash 403 AllocationQuota；
  qwen-turbo 持续 429 limit_requests；qwen3-max 404；无本地 ollama）——沿
  m2-5 受阻先例申报，本批候选以 `--offline` 确定性模板模式生成（data/
  eval-synth/m34-candidates-offline.jsonl，不入库），**人工抽检修正**后入库
  （修正幅度：模板问法全部改写为自然问法；en 候选 procedure/deadline/scope
  等不在档词逐条换为语料在档词；mix 候选取语料中英术语对重组）。配额恢复后
  重跑脚本（缺省 LLM 模式）产出 LLM 候选供人工复核**增补**（替换需重走标注
  评审）。
- **legacy 勘误**：q27 标签 mix→**zh**（m3-4 三态一致性机检暴露：query 文本
  「增值税发票开具规范 发票栏次」无 ASCII 字母，M1 标注笔误——非口径变更；
  M1 期基线报告 m1-baseline-*.md 中的 lang 列为当时记录，不改档）。
- **M3 基线**（`m3-baseline-*.md` / `*.json`——含逐 query hits 序）：

| 后端 | recall@1 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| sqlite | 0.7083 | 0.8417 | 0.9167 | 0.8031 |
| pg | 0.6250 | 0.7833 | 0.8333 | 0.7213 |

- 跨后端诚实零（逐 query recall@10=0，G-6 形态记录）：sqlite q24（M1 已知）/
  q50/q57（同题语料竞争 + BM25/token 袋多 token 噪声）；pg q01/q02/q10/q11/
  q20/q30/q36（含疑问词 query 的 AND 语义不可达——M1 既有差异面）。
- **deepeval 门禁下限冻结**：逐 query recall@10 exact 值（tests/
  test_eval_gate_m34.py `_R10_FLOORS`——门禁同环境实测，与 m3-baseline-*.json
  逐条一致）+ 聚合 0.05 余量；注入实证见 `m3-4-injection-evidence.md`。

## m3-5（TC-EVAL-03 judge 双语校准材料——2026-11-10）

- **材料**：`judge-materials-m35.jsonl`（50 条）+ 标注回流模板
  `judge-human-answersheet-m35.jsonl`——构建 `scripts/eval_judge_m35.py
  --materials`（确定性 seed=20261110，复跑同产物）；三态 zh 20 / en 15 /
  mix 15（黄金集三态等比抽样），构造 faithful 25 / unfaithful 25
  （faithful=标注语料连续句片段〔有依据〕；unfaithful=**语料内其他文档**
  句子〔跨文档真实业务表述、对 reference 无依据——幻觉面〕，非编造噪声）。
- **reference 近似口径**：标注键 → 语料**全文**（chunk 边界近似为整文档
  ——语料以单 chunk 文档为主；如实登记不冒充 chunk 精切）。
- **人工双评双轨**（用户裁定 2026-11-10）：用户侧按 answersheet 模板标注
  回流（label ∈ faithful|unfaithful + rater 标识）；coder 不代行——本轮
  chat 端点受阻（见 m3-5-blocked-claims.md）judge 侧无对照面，无代行小样。
- **judge 联调受阻申报**：chat 端点全档 403/429/404（与 m3-4 同形态）——
  真实 judge 判定与一致率/κ 出数待配额恢复复跑（路径见 blocked-claims）；
  校准框架与确定性用例已进门禁（tests/test_eval_judge_m35.py）。阈值定数
  归附录 A-6（监督侧 docs 批）。
