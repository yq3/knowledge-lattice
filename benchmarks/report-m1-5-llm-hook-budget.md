# LLM 钩子时间预算评估（M1-5 承接项——m1-4 committer 残余③）

> 评估对象：`quality_llm` provider 开启前，每 flag 超时 10s（`quality_llm_timeout_s`）
> 对摄取 quality 阶段的时间占用评估。**不开 provider**（本记录为评估，非实装）。
> 产出日期：2026-10-26；测量脚本 `benchmarks/llm_hook_budget.py`；
> 数据工件 `data/bench-results/m1-5-llm-hook-budget.json`。

## 结论（数据陈述，判据落笔归 supervised-coding）

当前 `run_llm_keywords` 形态为**逐 flag 串行**（`core/docs/quality.py`）：

```
T(N flags) = N × (provider 延迟 + 每 flag 固有开销)
最坏情形   = N × 10s（quality_llm_timeout_s 逐 flag 计——provider 超时上限）
```

- 每 flag 固有开销（读块 + 双写 + FTS 同步触发）：sqlite 内存库实测
  **0.1~4ms**（50ms 延迟档实测每 flag 54.0ms，其中固定开销 ~4ms——含
  llm_keywords/auto_keywords 两写与 au 触发器 FTS 同步）；生产含网络往返放大；
- **quality 阶段（摄取管线）按 doc_id 作用域调用**——单文档占用上界 =
  该文档 open flags 数 × 10s。大文档（数百块 × 疑似全 flag）最坏达
  **数十分钟**（100 flags = 1000s 纯超时），会显著拖长摄取任务；
- **组织级批跑**（`run_llm_keywords(org_id=...)`）无上界——N = 组织全部
  open flags，最坏 N × 10s。

## 开 provider 前的缺口（本评估识别，不在本段实施）

1. **并发上限**：串行逐 flag 无并发——网关 RTT 档（~200ms，见 TC-PERF-04
   rerank 曲线同源量级）下 100 flags ≈ 20s+；如需并发须引入有界线程池
   （rerank 信号量同款形态，§5.2）；
2. **批上界/时间预算**：quality 阶段（摄取内）应有单文档预算上限（超限
   截断 + 告警 + 可重跑），否则大文档摄取超时风险传导到任务层；
3. **超时降级语义**：单 flag 超时目前只跳过（best-effort），不阻断——
   批量超时下的雪崩（每 flag 等满 10s）需短路（连续 K 超时熔断——NFR-8
   熔断器同款）。

## 测量口径

- 环境：Apple M4 / 16GB / macOS 26.5.2 / Python 3.12 / sqlite 3.47.1（见主报告环境段）；
- 数据：sqlite 内存库 + 20 open flags + FakeKeywordGenerator（延迟 0/50ms 两档）；
- 复跑：`uv run python benchmarks/llm_hook_budget.py`。
