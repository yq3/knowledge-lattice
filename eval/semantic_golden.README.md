# 语义识别评测黄金集（TC-SEV-01——集合格式与标注规范）

> 识别评测的仓库级资产：`semantic_golden.jsonl`（172 条）+ 参考词典
> `semantic_seed.py`（标注 key 的真相源）。每次 `semantic_build` 自动以本集
> 跑识别评测、指标进构建报告并受门槛约束（TC-SEV-02——precision ≥0.95 /
> recall ≥0.80 / 歧义 ≥0.85 / 负样本误报 ≤0.05；较上版降 >2pp 不切 ready）。

## 集合格式（JSONL，每行一条）

```json
{"qid": "s001", "kind": "pos_exact", "lang": "zh",
 "text": "本月的进项税额抵扣范围包括哪些",
 "labels": [["concept:vat.input_credit", 3, 10]]}
```

- **qid**：全局唯一（s001 起顺序编号；重排/增删条目须重新编号）；
- **kind**：`pos_exact`（规范名/业务键——精确全词档）/ `pos_alias`（人工·
  同步别名）/ `pos_abbr`（拉丁缩写——词边界+大小写折叠）/ `pos_ambiguous`
  （歧义别名消歧——留抵/税率双实体共享面）/ `pos_context`（上下文短别名
  ——含无佐证丢弃形态）/ `neg`（负样本——无实体文本，labels 恒空）；
- **lang**：zh | en | mix（本版全 zh——双语问法 M3 完整黄金集承接，TC-EVAL-02）；
- **labels**：`[entity_key, start, end]`——span 左闭右开、下标落在**原文
  text** 上；同条目 span 不得重叠；标注**必须覆盖该文本的全部期望命中**
  （多实体并存的问法逐一列出——漏标即压 precision）。

## 标注规范

1. **真相源**：`entity_key` 必须可解析到 `semantic_seed.py` 的参考词典
   （tests/test_sem_eval_golden.py 校验 + 词典覆盖 ≥70%）；改词典须同步
   重校验全集（`uv run pytest tests/test_sem_eval_golden.py -q`）。
2. **span 取最长命中面**：文本同时含「留抵」与「留抵税额」时标注后者
   （annotate 最长匹配优先——TC-SEM-02；短面标注会假阴性）。
3. **歧义样本**（pos_ambiguous）标注业务上正确的实体：有上下文证据的按
   证据指向标注；**无佐证文本**按**显式缺省主读**标注——`default_reading`
   在参考词典 YAML 中显式声明（m2s-5/B2：留抵→期末留抵税额、税率→
   增值税税率；本集无佐证 qid 为 **s109**〔留抵〕与 **s117**〔税率〕，
   消解第⑤级 resolved_by='default' 定案——不再依赖实现第一候选
   (weight,id) 序）。未声明缺省主读的歧义面无佐证时返回全部候选
   `ambiguous=true`。
4. **上下文短别名样本**（pos_context）：佐证在场（同句确定命中 + 有关系）
   标注保留命中；无佐证形态（单独出现/同句无关系）**不标**——期望丢弃
   （TC-SEM-04），丢弃形态的条目用于防误召回。
5. **负样本**（neg）：无任何别名面的日常文本（~20%）+ 拉丁词边界陷阱
   （`XJXDKX`/`ldsee`——内部子串不得命中）；任何 ≥1 预测命中计 1 条误报。
6. **问法风格**：工单/群聊/agent 日志口语（非标题体）；单一问法 5~20 字。

## 指标口径（core/semantic/evalrun.py）

- precision/recall：span+实体双匹配（预测∩标注 / 各自分母）；
- ambiguity：只统计 pos_ambiguous 条目中的**歧义 span 标注**——标注
  surface 的 alias_norm 为多实体共享（词典侧判定，识别可用面口径）才进
  分子分母，条目内伴随的确定性标注不计（P2-2/R3：不稀释 ≥0.85 门槛——
  本集 20 条歧义条目共 25 标注，其中 5 条伴随〔s106/s107/s108/s110/s111〕
  → 分母 20）；**m2s-5/B1 分子收紧**：`ambiguous=true` 的主候选命中不计
  正确（未定案不算答对——收紧前口径 18/20=0.90 仍过门；B2 显式缺省主读
  就位后 s109/s117 经 default 档定案，严格口径 20/20=1.0）；
- neg_fp：负样本条目级误报率（≥1 命中即计）；
- 确定性：AC 自动机纯确定性匹配——同词典两次评测逐位一致（永久断言
  `test_tc_sev_02_eval_deterministic_double_build`）。

## 维护

- 改 `semantic_seed.py`（别名增删/提示词）→ 跑
  `uv run pytest tests/test_sem_eval_golden.py -q` 全量重校验；
- 门槛调整属口径变更：改 `EVAL_THRESHOLDS` 须在 TEST-CASES 登记版本注记。
