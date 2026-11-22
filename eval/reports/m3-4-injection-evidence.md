# m3-4 TC-EVAL-04 预注入回归验证记录（deepeval 门禁）

- 日期：2026-11-08（m3-4 交付轮）
- 验收原句：门禁能卡住一次人为注入的检索层回归；正常变更不误报
  （design §8 M3 第 5 项 / TEST-CASES TC-EVAL-04）。

## 注入物

`src/knowledge_lattice/core/docs/retrieve.py` 检索最终序（无 rerank 档）——
RRF 排序反转（升序 worst-first，「调坏权重/排序」类回归的最小形态）：

```diff
-        ordered = sorted(candidates, key=lambda c: -c["rrf_score"])
+        ordered = sorted(candidates, key=lambda c: c["rrf_score"])
```

## 实证链（命令与结果摘要）

| 步骤 | 命令 | 结果 |
|---|---|---|
| 注入 | 如上单行修改 | — |
| 门禁（红） | `uv run pytest tests/test_eval_gate_m34.py -q` | **2 failed**（`[sqlite]`/`[pg]` 双臂均卡）——首红 `q01 recall@10 实测 0.0 低于冻结下限 1.0`（逐 query 冻结下限击穿；聚合下限同被击穿） |
| 恢复 | `git checkout -- src/knowledge_lattice/core/docs/retrieve.py` | 源码零残留（`git status --short src/` 无 retrieve.py 条目） |
| 门禁（绿） | 同命令重跑 | **3 passed**（含指标纯语义用例） |

## 结论

- 逐 query recall@10 冻结下限（exact）+ 聚合下限（0.05 余量）双层卡门：
  注入的排序反转使大量 query 的 top-10 成员翻转 → 双后端门禁红；
- 正常变更不误报的口径：全链确定性（TokenBagEmbedder/jieba/FTS/RRF），
  冻结值即可复现值——配方有意变更走「重测并更新冻结表」（测试断言消息
  中明示该路径），非有意回退则被卡；
- 门禁离线确定性：deepeval 自定义 Metric 零 LLM（集合运算），模块导入前
  `DEEPEVAL_DISABLE_DOTENV=1` + `DEEPEVAL_TELEMETRY_OPT_OUT=1`（不依赖
  外网/真实端点）。
