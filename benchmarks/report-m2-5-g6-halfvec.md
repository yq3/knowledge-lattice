# m2-5 G-6 复测报告（R2 修订版——全链 SLO 同口径对照 + halfvec 召回段 + 真实模型基线）

> **R2 口径修正（P2-2）**：R1 版曾把 bench8 的**召回 SQL 片段**数据当作
> 全链 SLO 对照 M1-5 真值（口径错配——已撤回）。本版分三层数据：① bench5
> 形态**全链 search() 同口径复跑**（与 M1-5 真值 2443.2ms 同脚本同造数同
> 并发形态）；② bench8 **召回段**（halfvec vs 精确扫描——ACL 简化 workload，
> 申报口径局限）；③ 真实模型黄金集基线。
>
> 执行（2026-11-01 R1 / 2026-11-02 R2 复跑，Apple M4 / PG 16.15 容器
> lattice-pg / pgvector 0.8.x；真实模型=阿里百炼 `text-embedding-v4`
> 〔compatible-mode〕，key 经 .env DASHSCOPE_API_KEY）：
> ```bash
> export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
> # ① 全链 SLO（R2/P2-2——bench5 同口径：seed_corpus 双维度 ACL + 全配方
> #    search() + ThreadLocalPgBackend 每线程一连接 + N=5 12s）
> uv run python benchmarks/bench5_slo_perf03.py --scales 50000 --backends pg
> # ② 召回段对照（bench8——halfvec/精确扫描/并发/召回段计时；仅末轮 JSON
> #    落盘、历轮 stdout 数据见下表——R2/P3-4 注记）
> uv run python benchmarks/bench8_g6_halfvec_50k.py
> # ③ 真实基线（sqlite/pg 双臂）
> uv run python benchmarks/calib_m2_5.py --exp real
> ```
> 工件：`m1-5-tc-perf-03-pg-50000.json`（R2 复跑覆写）、
> `m2-5-g6-halfvec-50k.json`（bench8 末轮）、`m2-5-calib-real-{sqlite,pg}.json`。

## ① 全链 SLO 同口径复跑（R2/P2-2——M1-5 真值对照主表）

**bench5 形态 = M1-5 2443.2ms 的产生口径**：`core.docs.retrieve.search()`
全配方（query embed 150ms 模拟 + FTS/向量双路召回 + RRF fuse + rerank
200ms 模拟·32 候选）、`seed_corpus` 生产写路径造数（5 万块 + **双维度
region/tax_type ACL + 三用户授权分布**——u_broad 最宽授权）、
ThreadLocalPgBackend 每线程一连接（M1-5 R3 池化口径）、5 线程 12s 聚合
延迟分布、每请求 notice 全净断言（无降级样本）。

| 指标 | M1-5 真值（2026-10-27） | **R2 同口径复跑（2026-11-02）** |
|---|---|---|
| pg 5 万 C_full N=5 **P95** | **2443.2ms（>2s FAIL）** | **1361.6ms（≤2s PASS）** |
| P50 / P99 | — | 1074.6 / 1545.5 ms |
| rps | — | 3.54（一致性校验 3.62 ✓） |
| 单请求 C_full wall P95 | 836.2~1106.2ms（两轮） | 911.4ms |
| 分段 P95（embed/recall/fuse/rerank） | — | 160.9 / 464.3 / 78.2 / 210.3 ms |

**结论口径（供 docs 批）**：

1. **同口径复跑达标（P95 1361.6ms ≤2s），M1-5 真值 2443.2ms 本轮未复现**
   （-44%）——同一脚本、同一造数（seed_corpus 双维度 ACL）、同一池化连接
   形态，差异归因环境负载（M1-5 R3 轮次容器多任务并行；R1 Tester 已证
   该容器跨轮方差，M1-5 自身记录 ±25% 带亦难覆盖 44%——如实并列两数据）。
   **不以此关闭 G-6 v1.2 的超标登记**：G-6 回写建议写「同口径复跑达标 +
   M1-5 真值并列保留 + 生产环境首部署复测」，重开条件维持原文；
2. 单请求四段全绿：recall 段（含 FTS+vec 双路 + 双维度 ACL 编译）P95
   464.3ms——与 M1-5 的双路召回预算缺口（440/640ms）同量级、**仍超 300ms
   预算**（该缺口登记维持，未随环境改善消失）；fuse/rerank/embed 三段在
   NFR-8 预算内。

## ② halfvec(2560) 表达式索引 vs 精确扫描——**召回段对照**（bench8，5 万档）

**口径申报（R2 修正）**：本节为**召回 SQL 片段**（`render_vec_recall_select`
/`recall_vec` 单路）数据；ACL 造数为简化形态（无维度单成员，M1-5 的
seed_corpus 双维度不同 workload）——**与 M1-5/① 的全链数据不可直接对照**；
halfvec 索引仅作用于召回段，**全链 SLO 的 halfvec 档未测**（本段如实申报，
非无收益结论）。历轮仅末轮 JSON 落盘（stdout 四轮形态一致——399.7~589 /
253~307 / overlap 0.115~0.182 波动带内）。

| 档 | P50 | P95 | overlap@k | 备注 |
|---|---|---|---|---|
| 精确扫描 LIMIT 1024 | 245~258ms | 253~307ms | 1.0（基准） | 现网形态（backend.recall_vec 真实路径） |
| 精确扫描 LIMIT 64 | 215~254ms | 234~258ms | 1.0 | |
| **精确扫描 N=5 并发 LIMIT 1024** | 372~521ms | **399.7~588.9ms** | — | 召回段并发（4 轮带） |
| halfvec HNSW LIMIT 1024 | 258~271ms | 267~297ms | **0.9994** | 与精确扫描持平（召回段零收益） |
| halfvec HNSW LIMIT 64 | 2.6~3.1ms | 2.8~3.6ms | **0.115~0.182** | 召回段 70×↓ 但**欠召回严重** |
| halfvec strict_order LIMIT 64 | 3.9~4.4ms | 4.3~5.1ms | 0.1152（未改善） | iterative_scan 非欠召回根因 |
| halfvec ef_search=256 LIMIT 64 | — | 7.2~7.5ms | 0.25~0.27 | 扩搜索宽度部分改善 |
| halfvec ef_search=1000 LIMIT 64 | — | 40.7ms | **0.5586** | 仍不达 1.0——近似上限 |
| halfvec N=5 并发 LIMIT 1024 | 806~828ms | 855~885ms | 0.9994 | 召回段并发慢于精确 1.5~2.2× |
| 索引构建 / 体积 | 109~113s | — | — | 391MB |
| 双路召回段（FTS+vec 精确） | — | 230.6~288.8ms | — | 简化 ACL workload（≤300ms——非①同口径） |

### 结论与决策建议（回写 known-gaps G-6 材料——docs 批 supervised-coding 落笔）

1. **halfvec 表达式索引不建议引入（5 万档召回段证据）**：召回窗口档（LIMIT
   1024）零收益且并发反而慢 1.5~2.2×；小 top-k 档延迟收益 70× 但 overlap 仅
   0.12~0.18，ef_search=1000 也只到 0.56——欠召回根因（合成均匀随机 2560
   维向量无簇结构 = HNSW 最坏情形；strict_order 无效印证非「过滤不足」面）。
   **全链 SLO 未测 halfvec 档**（见①口径申报）；10 万档索引化决策如启动
   须以真实嵌入向量复测 overlap；
2. G-6 v1.2 注记回写建议：①全链 SLO 同口径复跑数据（1361.6ms PASS +
   2443.2 并列保留 + 生产首部署复测注记）+ ②召回段 halfvec 数据与不引入
   建议 + ③双路召回预算缺口维持（①的 464.3ms 佐证）；
3. 停用词/OR 口径变更**不在本段**（真实基线数据为下一段决策输入，见③）。

## ③ 真实模型重测双后端黄金集基线（TokenBag 代理结论验证）

| 档 | 后端 | recall@1 | recall@10 | MRR | 对照 TokenBag(dim=32) |
|---|---|---|---|---|---|
| **text-embedding-v4:1024（真实）** | sqlite | 0.8929 | **0.9286** | 1.0000 | r@10 +3.57pp / MRR +16.55pp |
| **text-embedding-v4:1024（真实）** | pg | 0.8929 | **1.0000** | 1.0000 | r@10 +21.43pp / MRR +27.23pp |
| TokenBag 代理（M1-5 基线复跑） | sqlite | 0.6607 | 0.8929 | 0.8345 | — |
| TokenBag 代理 | pg | 0.6071 | 0.7857 | 0.7277 | — |

> **指标口径（R2 修正——与 eval/metrics.py 算法一致）**：MRR =
> mean(reciprocal_rank) **含全部 28 query**（零召回 query 的 RR=0 计入
> 分母）——**MRR=1.0 = 全部 query 首命中均在 rank 1**；与 recall@1=0.8929
> 的差异来自 6 条双 label query（labels 含 2 个 chunk，top1 恰命中其一 →
> recall@1=0.5 而 RR=1.0——recall 按 |top-k ∩ labels|/|labels| 计分母）。

### 对 M1-5 TokenBag 代理结论的验证

1. **双后端偏差 10.72pp 的构成**：TokenBag 下 pg 0.7857 vs sqlite 0.8929
   = −10.72pp（FTS 疑问词零召回形态）；真实模型下 pg **1.0000 ≥ sqlite
   0.9286**——向量语义匹配补齐 FTS 侧形态。**28 query 小集的分辨率约
   3.57pp（1/28）**：pg 1.0000 是饱和态——「双后端偏差 >2pp 重开条件」
   **本轮不成立但保留重开**（docs 批不得以 28 query 关闭——R1 Committer
   方向审查意见采纳）；
2. **停用词假设（+7.14pp 修复候选）**：真实模型下收益面收窄到「纯 FTS
   降级窗口」（嵌入不可达时 BM25 单路）——决策建议优先级下调（如实施仍
   走决策变更流程，不在本段）；
3. **跨语言系统性低估（m1-4 Tester 警告）**：本轮黄金集（28 query 双语
   混合）未观察到系统性低估形态——维持观察口径。

## 已知-gap 回写材料索引（docs 批）

- G-6 v1.2 注记补充（按上文①②③三层口径——全链复跑数据 + 召回段 halfvec
  不引入建议〔含合成向量局限〕+ 双路召回缺口维持 + 真实基线 28-query
  分辨率限定）；
- G-6 残留缺口「PG 索引化时机与 halfvec 质量损失未标定」→ 召回段已标定
  （合成向量最坏情形 overlap 0.12~0.56、延迟收益面 70× 仅小 top-k——
  真实向量复测前置）。
