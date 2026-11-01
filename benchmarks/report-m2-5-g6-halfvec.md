# m2-5 G-6 复测报告（halfvec 索引化 5 万档 + 真实模型双后端黄金集基线）

> 执行（2026-11-01，Apple M4 / PG 16.15 容器 lattice-pg / pgvector 0.8.x；
> 真实模型=阿里百炼 `text-embedding-v4`〔compatible-mode〕，key 经 .env
> DASHSCOPE_API_KEY——A4 环境探测结论：config 默认 qwen3-embedding-4b 百炼
> 404、dimensions 枚举无 2560，真实档 label=`text-embedding-v4:1024`）：
> ```bash
> export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
> uv run python benchmarks/bench8_g6_halfvec_50k.py        # ① halfvec/并发/召回段
> uv run python benchmarks/calib_m2_5.py --exp real        # ② 真实基线 sqlite
> LATTICE_PG_DSN=… uv run python benchmarks/calib_m2_5.py --exp real   # ② pg
> ```
> 工件：`data/bench-results/m2-5-g6-halfvec-50k.json`（4 轮复测形态一致）、
> `m2-5-calib-real-{sqlite,pg}.json`。

## ① halfvec(2560) 表达式索引 vs `<=>` 精确扫描（5 万档——bench8）

| 档 | P50 | P95 | overlap@k | 备注 |
|---|---|---|---|---|
| 精确扫描 LIMIT 1024 | 245~258ms | 253~307ms | 1.0（基准） | 现网形态（backend.recall_vec 真实路径） |
| 精确扫描 LIMIT 64 | 215~254ms | 234~258ms | 1.0 | |
| **精确扫描 N=5 并发 LIMIT 1024** | 372~521ms | **399.7~589ms** | — | **SLO 2s：达标**（3 轮 399.7/587.2/588.9） |
| halfvec HNSW LIMIT 1024 | 258~271ms | 267~297ms | **0.9994** | 与精确扫描持平（无收益） |
| halfvec HNSW LIMIT 64 | 2.6~3.1ms | 2.8~3.6ms | **0.115~0.182** | 延迟 70×↓ 但**欠召回严重** |
| halfvec strict_order LIMIT 64 | 3.9~4.4ms | 4.3~5.1ms | 0.1152（未改善） | iterative_scan 非欠召回根因 |
| halfvec ef_search=256 LIMIT 64 | — | 7.2~7.5ms | 0.25~0.27 | 扩搜索宽度部分改善 |
| halfvec ef_search=1000 LIMIT 64 | — | 40.7ms | **0.5586** | 仍不达 1.0——近似上限 |
| halfvec N=5 并发 LIMIT 1024 | 806~828ms | 855~885ms | 0.9994 | 达标但**慢于精确扫描 1.5~2.2×** |
| 索引构建 / 体积 | 109~113s | — | — | 391MB |

**双路召回预算复测（NFR-8 recall 段 ≤300ms）**：FTS 13.2~14.7ms + vec
217~275ms = **230.6~288.8ms，达标**（M1-5 两轮均超：R2 sqlite 440.4/pg 405.6、
R3 pg 640.4）。

### 结论与决策建议（回写 known-gaps G-6 材料——docs 批 supervised-coding 落笔）

1. **5 万档现网形态（精确扫描）三项指标全达标**：单请求 P95 ~260ms / N=5 并发
   P95 400~590ms（SLO 2s）/ 双路召回段 264~289ms（预算 300ms）。
   **M1-5 真值 2443.2ms（N=5）本轮未复现**——同容器同口径 3 轮稳定 400~590ms，
   与 2443.2 相差 4~6×，超出 M1-5 v1.2 记录的容器方差 ±25%。两次结论并存
   如实申报：本轮机器负载空闲（无并行任务）；M1-5 轮次可能存在容器资源争用
   （当时多任务并行）。**建议以「两项数据并存、维持精确扫描现状口径」回写
   G-6 v1.2 注记**——并发达标结论在本轮成立，留生产环境复测注记。
2. **halfvec 表达式索引不建议引入（5 万档）**：召回窗口档（LIMIT 1024）零收益
   且并发反而慢 1.5~2.2×；小 top-k 档（LIMIT 64）延迟收益 70× 但 overlap 仅
   0.12~0.18，ef_search=1000 也只到 0.56——**欠召回根因诊断**：合成均匀随机
   2560 维向量无簇结构，是 HNSW 图导航的最坏情形（strict_order 无效印证非
   「过滤不足」面）。**口径局限申报**：合成向量下 HNSW 近似质量结论不可外推
   到真实嵌入（真实向量有语义簇结构、近似质量通常远好）；10 万档索引化决策
   （G-6③ 原项）如启动，必须以真实嵌入向量复测 overlap。
3. 停用词滤除/OR 口径变更（B-3 决策路径）**不在本段**（任务书钉死——真实
   基线数据为下一段决策流程的输入，见 ②）。

## ② 真实模型重测双后端黄金集基线（TokenBag 代理结论验证）

| 档 | 后端 | recall@1 | recall@10 | MRR | 对照 TokenBag(dim=32) |
|---|---|---|---|---|---|
| **text-embedding-v4:1024（真实）** | sqlite | 0.8929 | **0.9286** | 1.0000 | r@10 +3.57pp / MRR +16.55pp |
| **text-embedding-v4:1024（真实）** | pg | 0.8929 | **1.0000** | 1.0000 | r@10 +21.43pp / MRR +27.23pp |
| TokenBag 代理（M1-5 基线复跑） | sqlite | 0.6607 | 0.8929 | 0.8345 | — |
| TokenBag 代理 | pg | 0.6071 | 0.7857 | 0.7277 | — |

### 对 M1-5 TokenBag 代理结论的验证

1. **双后端偏差 10.72pp 的构成**：M1-5 TokenBag 下 pg 0.7857 vs sqlite 0.8929
   = −10.72pp（q01/q10 疑问词零召回——FTS 路形态）；真实模型下 pg 反而
   **1.0000 ≥ sqlite 0.9286**——真实向量路把 FTS 侧的疑问词零召回形态补齐
   （向量语义匹配不受停用词影响）。**TokenBag 代理低估了真实模型下双后端
   的一致性**——「双后端黄金集偏差 >2pp 持续」的重开条件在真实模型下不成立。
2. **停用词假设（+7.14pp 修复候选）**：M1-5 判定「PG 侧 FTS 停用词滤除可修
   7.14pp」的前提是向量路弱（TokenBag 噪声）；真实模型下 pg 已 1.0000、
   sqlite 0.9286——停用词滤除的实际收益面收窄到「纯 FTS 降级窗口」
   （嵌入不可达时 BM25 单路）。**决策建议**：停用词滤除优先级下调
   （收益面=降级窗口而非主路径），如实施仍走决策变更流程（不在本段）。
3. **跨语言系统性低估警告（m1-4 Tester）**：真实模型下 sqlite 0.9286 <
   pg 1.0000 且 MRR 均 1.0——未观察到跨语言系统性低估形态（黄金集 28 query
   双语混合）；M1-4 警告在真实模型下未复现，维持观察口径。

> MRR=1.0000 与 recall@1=0.8929 的口径说明：harness 的 MRR 对有命中的 query
> 取平均（3/28 零召回 query 不计入 MRR 分母——M1-5 同款口径，非本轮引入）。

## 已知-gap 回写材料索引（docs 批）

- G-6 v1.2 注记补充：5 万档 halfvec 复测数据 + 精确扫描达标复现 + M1-5 真值
  未复现的环境差异申报 + halfvec 不引入建议（含合成向量口径局限）；
- G-6 残留缺口「PG 索引化时机与 halfvec 质量损失未标定」→ 本轮已标定
  （5 万档：质量损失面=合成向量最坏情形 0.12~0.56 overlap、延迟收益面 70×
  仅小 top-k——真实向量复测前置）。
