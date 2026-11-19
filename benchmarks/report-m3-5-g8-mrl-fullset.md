# m3-5 D 组：G-8① MRL 截断判据复测（M3 完整集 60q/73docs）

> 执行（2026-11-10，百炼 compatible-mode `text-embedding-v4`，服务端原生
> dimensions 截断——非客户端前缀截断代理面）：
> ```bash
> uv run python benchmarks/calib_m2_5.py --exp mrl --backend sqlite
> LATTICE_PG_DSN=… uv run python benchmarks/calib_m2_5.py --exp mrl --backend pg
> ```
> 工件：`data/bench-results/m2-5-calib-mrl-{sqlite,pg}.json`（m3-5 复测覆盖
> m2-5 同名产物——28q 旧档数字归档于 report-m2-5-g8-real-model.md）。

## 复测背景（G-8① 判据落笔归 M3 完整集）

m2-5 首次真实模型实测（28 query / 39 docs，分辨率 ≈3.57pp）：512/256 两档 ×
双后端 r@10 与 MRR 全 0.00pp——「本集分辨率内未观测到损失」；判据正式落笔
待 M3 完整集复标（TC-EVAL-02 扩容后 60 query，分辨率 ≈**1.67pp**，1/60）。
m3-4 已交付双后端完整集基线载体（sqlite r@10 0.9167/MRR 0.8031、pg
0.8333/0.7213——TokenBag 代理口径）；本复测在同一 60q/73docs 数据上以
真实模型跑全量档 vs 截断档。

## 结果（真实模型 text-embedding-v4，60 query × 73 docs，双后端）

| 档 | 后端 | recall@1 | recall@5 | recall@10 | MRR | Δr@10 vs 全量 | ΔMRR vs 全量 |
|---|---|---|---|---|---|---|---|
| 全量 1024 | sqlite | 0.9167 | 0.9667 | 0.9667 | 0.9833 | — | — |
| 截断 512 | sqlite | 0.9167 | 0.9667 | 0.9667 | 0.9833 | **0.00pp** | **0.00pp** |
| 截断 256 | sqlite | 0.9333 | 0.9667 | 0.9667 | 0.9917 | **0.00pp** | **+0.84pp** |
| 全量 1024 | pg | 0.9167 | 1.0000 | 1.0000 | 0.9833 | — | — |
| 截断 512 | pg | 0.9167 | 1.0000 | 1.0000 | 0.9833 | **0.00pp** | **0.00pp** |
| 截断 256 | pg | 0.9167 | 1.0000 | 1.0000 | 0.9833 | **0.00pp** | **0.00pp** |

## 判据材料结论（供监督侧 docs 批落笔——G-8 收口/known-gaps 回写）

1. **「截断开放为可选配置」判据在 M3 完整集分辨率（≈1.67pp）内成立**：
   512/256 两档 × 双后端 recall@10 全 0.00pp；MRR 无损失档位（sqlite 256 档
   +0.84pp 为正向波动——排序并列/边缘命中的截断扰动，非损失证据）。与
   m2-5 28q 结论一致，且分辨率由 3.57pp 收紧至 1.67pp。
2. 判据建议（沿 m2-5 报告 item 2 口径）：截断可作为可选配置开放
   （`LATTICE_EMBED_MODEL/LATTICE_EMBED_DIM` env 承载、零代码、无需新 D
   编号）；收益面=存储与精确扫描延迟（维度线性）；代价面=本黄金集零，
   更大真实语料（待决-1）部署时复标。
3. 口径申报：真实模型档（text-embedding-v4）与本仓默认代理口径
   （TokenBag dim=32）数字不可比——m3-baseline-*.md 为代理口径门禁基线，
   本报告为真实模型判据材料（互不替代）；语料为合成集（待决-1 维持未决），
   「未观测到损失」严格口径为「本集分辨率内」。

## 端点状态注记

- embeddings 端点可用（本复测即真实调用；确定性缓存
  `data/bench-results/embeddings-cache/`——同文本同档复跑零成本）。
- 同 key 的 **chat 端点当日仍全档受阻**（qwen-plus/flash/max 403 Free quota
  exhausted、qwen-turbo 429、qwen3-max 404）——A/B/E 组真实 LLM 面受阻申报
  见 `eval/reports/m3-5-blocked-claims.md`。
