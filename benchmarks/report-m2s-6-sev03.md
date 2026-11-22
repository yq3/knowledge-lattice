# TC-SEV-03 检索增益评测报告（m2s-6——M2-S3 验收句）

> 任务：task-knowledge-lattice-m2s-6（A4）；**m3-4 数字随 M3 完整集重测**
> （黄金集 28→60 条 / 语料 39→73 篇——TC-EVAL-02 扩容；28 条期旧数字见
> 文末历史档）。口径：docs 黄金集（corpus.jsonl 73 篇 + golden.jsonl 60 条）
> 开/关实体召回路对比 recall@10 与 MRR；
> **不回退才允许 `auto_entities` 默认开启**（design §8 M2-S3 验收句）。
> 栈：参考词典（eval/semantic_seed）+ build + ingest 同事务打标 +
> TokenBagEmbedder(dim=32) 向量路、无 reranker（增益归因隔离——实体路是
> 唯一变量）；auto_entities=True 经 resolve_query_entities（AC 识别 →
> ENTITY_RECALL_RELS 展开 depth=1 → 实体路 RRF 第三路 k=60 权重 1.0）。
> 可重复执行：`uv run pytest tests/test_sev_03_entity_route_eval.py -q`
> （双后端参数化——本报告数字与测试断言互锁）。

## 一、开/关实体召回路对比（60 query——m3-4 完整集）

### sqlite

- off: recall@10=0.7, MRR=0.2627
- on: recall@10=0.75, MRR=0.2917

### pg（G-6 已登记差异：to_tsquery `&` AND 语义使基线天然偏低——增益结论不受影响）

- off(pg): recall@10=0.475, MRR=0.4854
- on(pg): recall@10=0.55, MRR=0.5026

### 不回退判定

**通过**——两后端两指标全维提升（m3-4 完整集 60 query：sqlite recall@10
+5.00pp / MRR +2.90pp；pg recall@10 +7.50pp / MRR +1.72pp）。实体召回路
对「query 提及业务概念、答案块以实体叙述」的样本人群有实质增益（零回退
样本——on ≥ off 全维成立）。

> **历史档（m2s-6 期，28 query/39 docs——m3-4 扩容前）**：sqlite
> off r@10=0.8214/MRR=0.3372、on r@10=0.9286/MRR=0.4087（+10.72pp/+7.15pp）；
> pg off r@10=0.5/MRR=0.4734、on r@10=0.625/MRR=0.5142（+12.50pp/+4.08pp）。
> 绝对值不可与 60 query 期直接比较（集合不同、均值口径基数变化）。

**结论**：满足「不回退才允许 auto_entities 默认开启」的前提——但默认值
维持 **False（保守档：显式参数形态）**，理由：①本增益建立在参考词典与
语料强同域的 POC 形态上，真实部署词典覆盖未知；②auto 路每 query 追加
一次 AC 识别 + expand SQL（P99 预算敏感——NFR-8）；保守默认让增益可被
显式 opt-in，切换默认值待真实语料（待决-1）M2 校准后定。

## 二、AC+模糊 recall@3 ≥0.92（TC-SEM-09/G-1 门槛）

识别黄金集 **180 条**（m2s-6 起 +8 条 pos_typo 错别字正样本——TC-SEV-01
v1.9.8 注记兑现：同音错字「留底→留抵」「消项→销项」「纳税申抱→纳税申报」
+ 编辑距离「一般纳税入」「JXDL→JXDK」「LDCE→LDSE」），适用面 145 条
（可完整解析正样本）、159 个标注：

- **AC+模糊 recall@3 = 1.0000 ≥ 0.92** ✅（两后端一致——识别面零 SQL 方言差）

口径注记：AC 层构建门槛（TC-SEV-02）**不含 pos_typo 条目**（错别字为模糊
层设计面，AC 层 miss 属设计内——不稀释 precision/recall 门槛分母）；
pos_typo 在 `fuzzy_recall_at_3`（AC+fuzzy 合并口径）参与判定。

## 三、灰度对比记录（TC-SEM-08 / TC-YAML-05——评测集载体）

同一 YAML 参考词典（concepts/systems 两个仓文件）双端装载：

- **本地 AC**：`localac.local_annotator_from_corpus(load_corpus(repo))`——
  过渡期 package（agent 侧；与 Annotator/norm 同一实现）；
- **服务端 annotate**：yaml 合并 → build → `annotate_text`。

对比面：YAML 内 14 个 concept/system 条目正问法（`请问{name}怎么处理`）。
结果（tests/test_yaml_05_local_ac.py::test_tc_yaml_05_gray_compare_on_golden）：

- **本地命中 ⊆ 服务端命中（14/14）**——迁移零改动承诺（本地覆盖面内不
  产生服务端不识别的命中）；
- 一致率 100%（纯人工词典部署形态：服务端词典 = YAML 识别面，mentions
  逐字段相等——span/entity_key/type/confidence/via/matched_by/resolved_by）。

## 四、关联验收

| 用例 | 结论 |
|---|---|
| TC-SEV-03 不回退 | ✅（本报告 §一） |
| auto_entities 默认值 | False（保守档——§一结论） |
| AC+模糊 recall@3 ≥0.92 | ✅ 1.0000（§二） |
| TC-TAG-04/05 | ✅ tests/test_tag_04_entity_recall.py（双后端） |
| TC-SEM-09 | ✅ tests/test_sem_09_fuzzy.py（双后端） |
| TC-SEM-08 / TC-YAML-05 | ✅ §三 + tests/test_sem_08_middleware.py / test_yaml_05_local_ac.py |
| T-S7/S8/S9 | ✅ tests/test_matrix_ts7_ts9.py（双后端） |
