# m2-5 G-8 百炼实测报告（MRL 截断 + 指纹阈值）+ rerank 联调记录

> 执行（2026-11-01，百炼 compatible-mode，`text-embedding-v4` / `gte-rerank-v2`）：
> ```bash
> uv run python benchmarks/calib_m2_5.py --exp mrl             # MRL sqlite
> LATTICE_PG_DSN=… uv run python benchmarks/calib_m2_5.py --exp mrl   # MRL pg
> uv run python benchmarks/calib_m2_5.py --exp threshold --rounds 20
> uv run python benchmarks/rerank_dashscope_live.py
> ```
> 工件：`m2-5-calib-mrl-{sqlite,pg}.json` / `m2-5-calib-threshold.json` /
> `m2-5-rerank-live.json`。

## ① G-8 MRL 截断（真实模型 dimensions 档 vs 全量档）

百炼 `text-embedding-v4` 原生支持 `dimensions` 参数（枚举
[64,128,256,512,768,1024,1536,2048,3072]——服务端 MRL 头截断，非客户端
前缀截断）。黄金集对比（全量 1024 vs 截断 512/256，双后端）：

| 档 | 后端 | recall@10 | MRR | Δr@10 vs 全量 | ΔMRR vs 全量 |
|---|---|---|---|---|---|
| 全量 1024 | sqlite | 0.9286 | 1.0000 | — | — |
| 截断 512 | sqlite | 0.9286 | 1.0000 | **0.00pp** | **0.00pp** |
| 截断 256 | sqlite | 0.9286 | 1.0000 | **0.00pp** | **0.00pp** |
| 全量 1024 | pg | 1.0000 | 1.0000 | — | — |
| 截断 512 | pg | 1.0000 | 1.0000 | **0.00pp** | **0.00pp** |
| 截断 256 | pg | 1.0000 | 1.0000 | **0.00pp** | **0.00pp** |

**「截断开放为可选配置」判据落笔材料**（供 docs 批）：

1. 真实 MRL 模型（v4 服务端截断）在本项目黄金集（28 query 双语/39 文档）上
   **recall@10 与 MRR 本集分辨率内未观测到损失**（512/256 两档 × 双后端全 0.00pp；
   28 query 分辨率 ≈3.57pp，严格口径见 item 3——M3 完整集 TC-EVAL-02 复标）——显著优于
   M1-5 TokenBag 代理面（r@10 0.00pp 但 MRR −1.63~−2.38pp——客户端前缀截断
   对非 MRL 向量的破坏）；服务端原生 MRL 是无损截断。
2. 判据建议：**截断可作为可选配置开放**（`LATTICE_EMBED_DIM` + 模型
   dimensions 支持时）；收益面=存储（2560→1024：chunk_vectors 表 ~60% 缩减）/
   精确扫描延迟（维度线性）；代价面=本黄金集零、更大语料待标定。开放形态
   走 env 配置（现有 `LATTICE_EMBED_MODEL/LATTICE_EMBED_DIM` 已承载——零代码），
   **无需新 D 编号**（D12 既有「模型经配置」口径内）。
3. 口径申报：黄金集小（**28 query——分辨率约 3.57pp〔1/28〕**，「零损失」
   严格口径为「**本集分辨率内未观测到损失**」）；首次真实
   语料大规模部署时以 TC-EVAL-02（M3 完整黄金集）复标。

## ② G-8 指纹阈值（真实响应抖动分布——M1-5 校准建议 3 步的真实版）

哨兵 3 条 × 20 轮独立请求（跨秒级窗口）= 60 样本：

| 指标 | 值 |
|---|---|
| cosine min / p05 / p50 / p95 / max | **1.0 / 1.0 / 1.0 / 1.0 / 1.0**（6 位小数） |
| 漂移 p95 | 0.0% |

**校准建议（供 docs 批）**：**维持 0.99/0.95 两档不变**。依据：

1. 真实网关（百炼）同文本跨调用抖动底 ≈1.0（fp32 输出确定性、批次内无噪声）
   ——warn 档 0.99 与 reject 档 0.95 之间有 1%/5% 完整检出带，零误报面；
2. 探针语义（「网关静默换底模」防线）对真事件的检出余量充足：换底模的典型
   余弦偏差远大于 5%（M1-5 漂移判定剖面：>1% warn / >5% reject 分档合理）；
3. M1-5 可构造面结论（fp16 量化噪声底 1.0——halfvec 存储环回）与真实抖动
   底一致——良性变换不触阈值的设计得到双重验证。

## ③ A7① rerank 百炼真实联调（gte-rerank-v2 DashScope 原生 text-rerank）

| 联调面 | 结果 |
|---|---|
| 基本契约 | ✅ 请求 `input.{query,documents}` 嵌套 + 端点 `/api/v1/services/rerank/text-rerank/text-rerank`；响应 `output.results[{index,relevance_score}]`——与 `DashScopeReranker` provider（离线 MockTransport 用例锁定的映射）逐字段一致 |
| 排序语义 | ✅ 中文 query 下相关文档（留抵主题 0.18~0.19）> 英文无关（0.10）> 无关（0.006）；分数降序 + index 回映 {0,1,2,3} 全对 |
| **top_n 放置（R2/P3-7 已修）** | R1 实测「传 2 返回全量」根因=**顶层放置不被识别**——DashScope 的 top_n 在 `parameters` 下（探测 2026-11-02：`parameters.top_n=2` → 恰 2 条）。provider 已按 `parameters` 形态修正 + MockTransport 用例锁定 + live 复跑确认（respected=True）；消费面 `retrieve._run_rerank` 全量请求按分取 top——截断与否均正确 |
| 错误形态 | ✅ 错误模型名 → **400 InvalidParameter "Model not exist."**（非 404）；provider 原样 raise HTTPStatusError → 调用方 rerank_skipped 降级契约成立（离线用例已锁） |
| 延迟 | 基本契约轮（4 文档）：R1 轮工件 **196.6ms** / R2 轮（parameters 修正后复跑）工件 **360.3ms**——网关 RTT 跨轮波动约 1.8×（均在 rerank_timeout_s=1.0 硬上限内；以 JSON 工件为准——R2/P3-2 修正：R1 报告正文 ~470ms 为口头估计，撤回） |

**配置切换验收口径实证**（任务书 A7②）：供应商切换仅经 `LATTICE_RERANKER` +
`LATTICE_RERANK_API_BASE/API_KEY/MODEL`（+TRUNCATE_TOKENS）env——`.env.example`
rerank 段含百炼/Cohere 对照完整示例；`tests/test_emb_08_dashscope.py` 11 用例
锁定（端到端 env→get_settings→create_app 全链 DashScope 配置、未知档位
fail-closed）。embedding 侧 env 已全覆盖（M0b-3）+ 百炼 compatible-mode
OpenAI 兼容零代码——本报告 ①② 的真实调用即经该路径（env 配置驱动）。

## known-gaps 回写材料索引（docs 批 supervised-coding 落笔）

- **G-8 ①**：MRL 真实模型复验完成——服务端原生截断零损失（双后端 ×2 档）、
  代理面 MRR 损失不复现；「截断开放为可选配置」判据材料如上（建议开放、
  走 env 既有口径）；
- **G-8 ②**：真实网关抖动分布到位（60 样本全 1.0）——0.99/0.95 维持依据充分，
  「真实网关抖动分布受阻申报」状态解除；
- **G-7**：rerank 百炼形态联调完成——DashScope 原生契约实证（provider 已入
  仓）、top_n 差异登记（消费面零影响）；重开条件「实测响应与契约不符」
  触发于 Cohere 档位时仍有效（DashScope 档为独立 provider）。
