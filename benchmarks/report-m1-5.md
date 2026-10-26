# M1-5 实验与收口报告（TC-PERF-03/04 标定 + 100k 重算改造实测 + G-6 黄金集校准基线 + 顺延申报）

> 任务：task-knowledge-lattice-m1-5（M1 验收收官段）。本报告**只陈述数据与现象**，
> 判据落笔（阈值/口径/结论回写 known-gaps、TEST-CASES §六）归 supervised-coding。
> JSON 明细：`data/bench-results/m1-5-*.json`；脚本：`benchmarks/bench4~7*.py`。
> 配套材料：`report-m1-5-m1-checklist.md`（§六 M1 逐条勾验索引）、
> `report-m1-5-tc-ui-walkthrough.md`（TC-UI 走查清单）、
> `report-m1-5-llm-hook-budget.md`（LLM 钩子预算评估）。

## 0. 环境说明

| 项 | 值 |
|---|---|
| 机型 | Apple M4（arm64）/ 16GB RAM / macOS 26.5.2 |
| Python / 依赖 | 3.12（uv 托管）/ numpy 2.5.4 / sqlite 3.47.1 |
| PG | PostgreSQL 16.15（docker `pgvector/pgvector:pg16`，容器内存上限 **3.825GB**）+ pgvector 0.8.7（extname `vector`） |
| 模型说明 | 本地无网关/ollama——**全部模型调用为模拟**（embed 延迟注入 = NFR-8 预算值 150ms；rerank = 200ms RTT 档；向量 = 合成 2560 维 unit float32，PCG64 seed=20261024 确定性）；真实 API 档随 M2 网关环境 |
| 计时口径 | time.perf_counter；P50/P95 nearest-rank（ceil(p·n)-1）；预热 3（jieba 首切分与语句缓存不进样本） |

## 1. 交付矩阵（本段实验+收口批）

| 组 | 项 | 状态 |
|---|---|---|
| A1 | 100k 档批量重算改造（M1-4 P2-4 前置）+ 内存实测 | ✅ §4 |
| A2 | TC-PERF-03 SLO 分项标定（1 万/5 万 × sqlite/pg） | ✅ §2 |
| A3 | TC-PERF-04 rerank 并发曲线 + CPU 嵌入吞吐 | ✅ §3 |
| A4 | G-6 halfvec/表达式索引 10 万块对比 | ⏸ **顺延**（用户 2026-10-26 裁定本段跳过——§8） |
| B1/B2 | G-8 MRL 截断 / 指纹阈值校准 | ⏸ 未执行（§9——时间预算耗尽于 A 组与收口） |
| B3 | G-6 双后端黄金集校准基线（数据面） | ◐ §5（B-3①真实模型受阻申报 + 偏差数据在档；②③④实验未执行） |
| B4 | 蓝绿共存 PG 读代价复测 | ⏸ 未执行（§9；M0b-2 定性结论在档） |
| C4 | LLM 钩子时间预算评估 | ✅ report-m1-5-llm-hook-budget.md |
| D | TC-UI 走查清单 / M1 勾验材料 / 门禁复验 | ✅（配套三材料 + §10） |

## 2. TC-PERF-03 SLO 标定（NFR-8：P95 ≤ 2s——1 万/5 万两档）

脚本 `bench5_slo_perf03.py`；**检索全配方真实管线**（`core.docs.retrieve.search`
——ACL 编译/双路召回/RRF/双断言/归一，与生产同 code path），查询用户
u_broad（最宽授权——最重扫描面），5 query × 预热 3 + 10 轮；分项耗时取自
P3-13 四段日志（M1-5 双计修正后 `enh_wait` 单列，本档 enhancer=none → 恒 0）。

三配置：**A base**（embed 0ms + 无 rerank——存储/融合纯段）/ **B embed150**
（embed 150ms——NFR-8 预算值）/ **C full**（embed 150ms + rerank 200ms·32 候选，
rerank_max_concurrency=4）。

### 单请求档（wall 与分段均为 P95，ms）

| 档位 | 后端 | 配置 | wall P50/P95 | embed | recall | fuse | rerank |
|---|---|---|---|---|---|---|---|
| 1 万块 | sqlite | A base | 38.6 / 41.2 | 0.1 | 28.8 | 12.7 | 0.0 |
| 1 万块 | sqlite | C full | 411.7 / 419.9 | 155.2 | 39.3 | 21.2 | 205.2 |
| 5 万块 | sqlite | A base | 186.8 / 197.8 | 0.1 | 139.6 | 59.6 | 0.0 |
| 5 万块 | sqlite | C full | 559.6 / 571.4 | 155.2 | 141.9 | 72.5 | 205.2 |
| 1 万块 | pg | A base | 83.5 / 243.4 | 0.1 | 119.0 | 34.8 | 0.0 |
| 1 万块 | pg | C full | 166.7 / 422.8 | 155.2 | 100.4 | 36.0 | 205.2 |
| 5 万块 | pg | A base | 42.7 / 119.8 | 0.1 | 67.7 | 47.5 | 0.0 |
| 5 万块 | pg | C full | 219.0 / 545.7 | 160.3 | 99.7 | 94.9 | 205.7 |

（B_embed150 行为 A 与 C 的插值——完整数据见 JSON；pg 臂 P50/P95 差距大于
sqlite，为 docker 容器 CPU 争用的观测噪声，逐请求样本在 JSON。）

### N=5 并发档（NFR-8 口径——5 线程持续 12s，C full 配置）

| 档位 | 后端 | rps | P50 | P95 | P99 | SLO（P95 ≤ 2000ms） |
|---|---|---|---|---|---|---|
| 1 万块 | sqlite | 16.58 | 399.8 | 417.4 | 437.9 | **PASS** |
| 5 万块 | sqlite | 12.33 | 558.1 | 633.4 | 662.2 | **PASS** |
| 1 万块 | pg | 22.50 | 176.9 | 428.8 | 446.4 | **PASS** |
| 5 万块 | pg | 16.67 | 239.8 | 581.6 | 606.4 | **PASS** |

### NFR-8 延迟预算表对照（5 万块 · C full · 各后端 P95）

| 预算项 | 预算 | sqlite 实测 | pg 实测 | 备注 |
|---|---|---|---|---|
| query 嵌入 | ≤150ms | 155.2 | 160.3 | 模拟值=预算+5~10ms 注入误差（模拟器 sleep 精度） |
| 双路召回 | ≤300ms | 141.9 | 99.7 | 两后端均在预算内（5 万块） |
| rerank | ≤1000ms | 205.2 | 205.7 | 模拟 RTT 200ms 档 |
| 其余（fuse 等） | ≤200ms | 72.5 | 94.9 | fuse=RRF+双断言+归一 |
| **合计 wall** | ≤2000ms | **571.4** | **545.7** | 单请求；N=5 并发 633.4 / 581.6 |
| LLM 增强 | 800ms 并行不计关键路径 | enh_wait=0 | enh_wait=0 | 本档 enhancer=none；双计修正后该段单列（§2 注） |

## 3. TC-PERF-04 rerank 并发与嵌入吞吐

脚本 `bench6_perf04.py`；rerank 走 `_run_rerank` **真实路径**（信号量 +
专用池 + 超时预算——P2-2「排队不计入调用超时」形态本体），provider 模拟
延迟 200ms，5 线程 × 24 请求：

| 信号量上限 | rps | P50 ms | P95 ms | provider 并发峰值 | 降级 |
|---|---|---|---|---|---|
| 1 | 4.84 | 207.5 | 210.3 | 1 | 否 |
| 2 | 8.13 | 205.2 | 210.2 | 2 | 否 |
| 4 | 12.27 | 204.8 | 205.2 | 4 | 否 |
| 8 | 24.52 | 203.8 | 205.2 | 5（=线程数） | 否 |

- 吞吐随信号量近线性（1→8 上限：4.84→24.52 rps）；等待者排队不计入单次
  调用超时（P95 恒 ~205ms ≈ 模拟延迟）——P2-2 形态按设计工作；
- CPU 嵌入分批吞吐（TokenBagEmbedder dim=2560 · batch=64 · 1200 段）：
  **20,205 块/分钟**（3.56s）——客户端处理上界；**真实 API 吞吐受阻申报**
  （本地无网关——与 B-3① 同源，M2 生产化容量规划补测）。

## 4. 100k 档批量重算改造实测（M1-4 P2-4 / TC-PERF-03 前置）

改造（commit 992a0e2 + 本批 `_crowding_means` 双流版）：`org_active_chunk_vectors`
返回 **packed float32 bytes 惰性流**（sqlite=vec_f32 BLOB 原样 / PG=named
cursor 服务端游标，不物化 float 对象）；`delete_open_flags` rid 分批 32,000/
语句（PG 65535 / sqlite 32766 参数上限——70,000 rid 删除双后端用例绿）；
`_crowding_means`＝候选驻留 float32 矩阵 + 池块流 + running top-k。

脚本 `bench4_recompute_100k.py`（子进程隔离测峰值 RSS——ru_maxrss 进程高
水位不可同进程叠加；数据源=合成 100k×2560 确定性向量，普通文件 read 流——
隔离算法私有内存）：

| 形态 | 规模 | 峰值内存 | 耗时 |
|---|---|---|---|
| 旧（`list[tuple[int, list[float]]]` 物化） | 10,000 行 | **1,092.7 MB** | 3.0s（仅物化） |
| 旧 · 线性外推 | 100,000 行 | **≈10.67 GB**（=16GB 机不可行；每行 80KB=packed bytes 的 11.2×） | — |
| 新（packed bytes 流 + 候选驻留 + 分块 running top-k） | 100k 池 · 5% 候选 | **673.1 MB** | 4.67s |
| 新 · 全量候选档 | 100k 池 · 100k 候选 | 候选矩阵上界 ≈0.95GB（单块 ndarray，§5.4「载入 numpy」同口径） | **74.5s（1.2 min）** |

- §5.4「10 万×2560 维分钟级可行」设计主张兑现（全量 74.5s）；
- SQL 侧流式正确性：双后端 `test_m1_5_dev.py`（packed bytes 契约 + 70k rid
  分批删除）+ `test_qual_04`（10k 全链重算，门禁内）覆盖；
- 候选清单（content/content_seg 字符串）仍为列表物化（~百 MB 量级 @100k）——
  本改造聚焦向量物化根因（>1GB→10.67GB），候选面未见 P2-4 级阻塞。

## 5. G-6 双后端黄金集校准基线（数据面）

来源：M1-4 双后端基线（`eval/reports/m1-baseline-{sqlite,pg}.md`，TokenBag
代理口径——真实模型重测见 §9 受阻申报）；本段计算偏差并归档
`data/bench-results/m1-5-g6-golden-baseline-deviation.json`：

| 指标 | sqlite | pg | 偏差 |
|---|---|---|---|
| recall@1 | 0.6607 | 0.6071 | −5.36pp |
| recall@5 | 0.8393 | 0.7143 | −12.50pp |
| **recall@10** | **0.8929** | **0.7857** | **−10.72pp**（>2pp——G-6 收窄②钩子触发口径） |
| MRR | 0.8345 | 0.7277 | −10.68pp |

逐 query 差异（r@10，共 6/28 条不同；**无一条双后端同零**）：

| qid | lang | sqlite | pg | 现象 |
|---|---|---|---|---|
| q01 留抵退税的申请条件是什么 | zh | 1.0 | 0.0 | PG `&` 全 token AND 下疑问词（的/是/什么类）不命中 |
| q10 消费税的征收范围包括哪些 | zh | 1.0 | 0.0 | 同上 |
| q19 simplified taxation method small-scale taxpayer | en | 1.0 | 0.5 | 多标注（2 labels）PG 部分召回 |
| q20 stamp duty loan contract rate | en | 1.0 | 0.0 | PG AND 零命中 |
| q21 VAT 留抵退税 excess input VAT refund 申请 | mix | 1.0 | 0.5 | 多标注部分召回 |
| q24 | mix | 0.0 | 1.0 | **反向**：sqlite OR 噪声压过目标、PG AND 反而命中 |

- 根因与 M1-4 committer 判定一致（m1-4 检查点：sqlite OR / PG `&` AND——
  `store/*/fts.py` 口径差）；q01/q10/q20 偏差与「停用词滤除约 +7.1pp」假设
  （2/28）方向吻合——**实验验证（B-3②）与 OR 口径决策材料（③）、ts_rank_cd
  对照（④）本段未执行**（§9）；
- B-3①（真实嵌入模型重测）**受阻**：本地无 ollama（未安装、`127.0.0.1:11434`
  不通）且无公司网关；可行路径＝公司网关端点或本地 ollama + qwen3-embedding
  模型 provisioning——TokenBag 代理对跨语言 query 系统性低估的疑点（q19/q20/
  q21 类缺口）在真实模型就位前无法定论。

## 6. LLM 钩子时间预算评估（C4）

见 `report-m1-5-llm-hook-budget.md`：逐 flag 串行模型 T(N)=N×(延迟+固有开销
~0.1-4ms)，最坏 N×10s；100 flags=1000s 纯超时；quality 阶段按 doc 作用域
（上界=单文档 open flags）；开 provider 前缺口=并发上限/批上界/超时熔断短路
（三项，不在本段实施）。

## 7. bench1~3（M0b-2 存档摘要——本段未复跑）

| 实验 | 结论指针 |
|---|---|
| bench1 ACL 双写法（TC-PERF-01） | visible_docs CTE（按文档）较 json_each（按块）1 万档 P95 17.8→5.4ms（u_narrow）等量级优势；两写法结果集逐行等价（全 tier/用户）——拍板 1 依据；`data/bench-results/bench1.json` + `report-m0b-2.md` §2 |
| bench2 向量布局 + 蓝绿（TC-PERF-02） | 分表 chunk_vectors 胜出（拍板 2）；蓝绿共存（拍板 3）：sqlite 零放大 / pg 读代价 −3%~+52% 波动（定性）；`bench2.json` + `report-m0b-2.md` §3 |
| bench3 客户端驱动（TC-AUTH-04 附注） | mcp 1.30.0 client ⇄ fastmcp4 server 协议兼容（initialize 47.9ms）；三形态会话建立成本（形态 A p50 10.3ms / A' 每请求全握手 / B 中继）；`bench3.json` + `report-m0b-2.md` §4 |

## 8. bench7（G-6 halfvec/表达式索引 10 万块）顺延声明

**用户 2026-10-26 裁定本段跳过**（非 M1 验收硬门槛；G-6 收窄③顺延）。断点
现象（定性）：10 万块精确扫描造数+对照在 3.825GB 内存容器上为长时基准
（COPY 100k×2560 向量文本 ~5GB + HNSW 表达式索引构建预计 15~30 分钟量级），
单次会话时间预算内无法与 M1 收口批并行完成；脚本已入库并头注顺延状态
（`benchmarks/bench7_g6_halfvec.py`——含完整实验形态：精确扫描基线 +
`(embedding::halfvec(2560)) halfvec_cosine_ops` 表达式索引对照 + LIMIT
1024/64 两档 + overlap@k 召回对照），后续段可直接复跑。

## 9. 顺延/未执行申报（判据落笔归 supervised-coding）

| 项 | 状态 | 原因/基础 |
|---|---|---|
| G-6 收窄③ halfvec 对比 | 顺延（用户裁定） | §8 |
| B-3① 真实嵌入模型重测 | 受阻 | §5——无网关/ollama 环境 |
| B-3② 停用词滤除 / ③ OR 决策材料 / ④ ts_rank_cd | 未执行 | 段内时间预算耗尽于 A 组与收口；偏差数据+逐 query 现象已归档（§5），实验可基于 M1-4 黄金集基建直接开展 |
| G-8 MRL 截断 / 指纹阈值校准 | 未执行 | 同上；真实网关抖动数据同 B-3① 受阻 |
| 蓝绿共存 PG 读代价复测（B4） | 未执行 | M0b-2 定性结论在档（§7） |

## 10. 门禁与复现

- 门禁：`LATTICE_PG_DSN=… bash scripts/test_gate.sh` → **661 passed / 1
  deselected（manual 走查标记）/ 0 skipped，双后端双模式**；pg 臂 225 实跑
  （[pg] 参数化 193 + PG 专用 32）。计数对账：M1-4 交付 604+1 → 本段 +57
  （`tests/test_m1_5_dev.py`：C3 fuse 4 + A1 改造 4 + C1 list_documents 5 +
  C2 畸形参数 44）；
- 复现：`uv run python benchmarks/bench4_recompute_100k.py`；
  `uv run python benchmarks/bench5_slo_perf03.py`（pg 臂需 LATTICE_PG_DSN）；
  `uv run python benchmarks/bench6_perf04.py`；`uv run python benchmarks/llm_hook_budget.py`。
