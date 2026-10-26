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
