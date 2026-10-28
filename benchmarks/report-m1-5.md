# M1-5 实验与收口报告（TC-PERF-03/04 标定 + 100k 重算改造实测 + G-6 黄金集校准基线 + 顺延申报）

> 任务：task-knowledge-lattice-m1-5（M1 验收收官段）。本报告**只陈述数据与现象**，
> 判据落笔（阈值/口径/结论回写 known-gaps、TEST-CASES §六）归 supervised-coding。
> JSON 明细：`data/bench-results/m1-5-*.json`；脚本：`benchmarks/bench4~7*.py`。
> 配套材料：`report-m1-5-matrix.md`（越权矩阵收口——T1~T23+TC-AZ 双后端，R2 复跑 348/348）、
> `report-m1-5-m1-checklist.md`（§六 M1 逐条勾验索引）、
> `report-m1-5-tc-ui-walkthrough.md`（TC-UI 走查清单）、
> `report-m1-5-llm-hook-budget.md`（LLM 钩子预算评估）、
> `report-m1-5-g8-mrl.md` / `report-m1-5-g8-threshold.md`（G-8 两项校准）、
> `report-m1-5-g6-variants.md`（停用词/ts_rank_cd）/ `report-m1-5-bluegreen.md`
> （蓝绿复测）/ `report-m1-5-g6-real-model-deferred.md`（B-3① 受阻申报）。

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
| B1 | G-8 MRL 截断对比（2560 vs 前缀 1024，双后端） | ✅ report-m1-5-g8-mrl.md（r@10 损失 0.00pp / MRR −1.6~−2.4pp——TokenBag 代理口径，真实 MRL 模型部分随 B-3① 受阻申报） |
| B2 | G-8 指纹阈值校准（0.99/0.95 两档） | ✅（可构造面）report-m1-5-g8-threshold.md——同模型/fp16 噪声底实测 + 漂移判定剖面；**真实网关抖动分布受阻申报**（同 B-3①） |
| B3 | G-6 双后端黄金集校准基线 | ◐ 数据面 §5 + 实验②④ ✅（report-m1-5-g6-variants.md——停用词 +7.14pp 假设精确命中 / ts_rank_cd 零差异）；①真实模型**受阻申报**（report-m1-5-g6-real-model-deferred.md）；③ OR 口径**未动**（决策材料齐备） |
| B4 | 蓝绿共存 PG 读代价复测 | ✅ report-m1-5-bluegreen.md（10k 档共存读代价轻度 ~+6%/与噪声同量级——缓存受控对照） |
| C4 | LLM 钩子时间预算评估 | ✅ report-m1-5-llm-hook-budget.md |
| D | 越权矩阵收口（T1~T23+TC-AZ 双后端+E2E-05）/ TC-UI 清单 / M1 勾验材料 / 门禁复验 | ✅ report-m1-5-matrix.md（R2 复跑 348/348 全绿）+ 配套材料 + §10 |
| B=② | 合成语料区分度误报抽查（R2 用户裁定） | ✅ report-m1-5-fp-review.md——41 open flags 抽 12 逐条复核：词面路误报 11~12/12（同域小语料 IDF 稀释）、拥挤路零误报、漏报不可评（无金标申报） |

## 2. TC-PERF-03 SLO 标定（NFR-8：P95 ≤ 2s——1 万/5 万两档）

脚本 `bench5_slo_perf03.py`；**检索全配方真实管线**（`core.docs.retrieve.search`
——ACL 编译/双路召回/RRF/双断言/归一，与生产同 code path），查询用户
u_broad（最宽授权——最重扫描面），5 query × 预热 3 + 10 轮；分项耗时取自
P3-13 四段日志（M1-5 双计修正后 `enh_wait` 单列，本档 enhancer=none → 恒 0）。

> **R2 勘误（P1-1——Committer R1 审查项）**：R1 版 embedder 行号解析对中文
> query 抛错被 `_embed_query` 吞成 `embed_unreachable`——全部样本实为 **BM25
> 单路降级**（recall 段缺向量扫描、embed 段 ≈0.1ms），SLO 数据失真。R2 修复：
> 查询文本→语料行号显式 dict 映射（未知文本 KeyError fail-fast）+ **每请求
> 断言 `notice == {"vector_pending": False, "degraded": []}` 与结果非空**
> （预热样本亦断言但不进统计——P2-2；wall P50 改 nearest-rank——P3-5）。
> 下表为全配方净跑重测数据（rps 一致性检查列：rps ≈ 5/mean——5 线程串行环
> 自洽；P2-1：rps 按实测 elapsed 计，非名义 12s）。

三配置：**A base**（embed 0ms + 无 rerank——存储/融合纯段）/ **B embed150**
（embed 150ms——NFR-8 预算值）/ **C full**（embed 150ms + rerank 200ms·32 候选，
rerank_max_concurrency=4）。

### 单请求档（wall 与分段均为 P95，ms；B 行为 A/C 插值——完整数据见 JSON）

| 档位 | 后端 | A base wall | A recall | C full wall | C embed | C recall | C fuse | C rerank |
|---|---|---|---|---|---|---|---|---|
| 1 万块 | sqlite | 117.2 | 97.9 | 482.3 | 160.5 | 94.3 | 19.4 | 210.2 |
| 5 万块 | sqlite | 611.2 | 530.2 | 880.1 | 160.7 | 440.4 | 82.9 | 210.2 |
| 1 万块 | pg | 312.0* | 212.1* | 474.4 | 160.6 | 82.5 | 26.3 | 210.2 |
| 5 万块 | pg | 783.3 | 691.4 | 1106.2 | 156.0 | 640.4 | 103.1 | 210.2 |

（\*pg-1 万 A_base 为造数后首个测量相位，容器页缓存冷热噪声大（P50 69.1ms）；
后续相位热态稳定。pg 臂逐请求样本在 JSON。**pg-5 万行为 R3 池化重测值**——
与 R2 轮（A 512.7 / C 836.2）同容器不同轮——**两轮值并列申报（R2/R3），
观测带 ±30~50%**（实测离散：pg-5 万 C wall +32% / A base wall +53% / A recall
+52%——docker 3.825GB 容器 CPU/页缓存争用；结论对观测带稳健——两轮 N=5 均
显著超 2000ms）；JSON 保留 R3 轮；pg-1 万与 sqlite 两行为 R2 轮值（本轮未重测
——指令仅重跑 pg-5 万臂）。）

### N=5 并发档（NFR-8 口径——5 线程持续 12s，C full 配置）

| 档位 | 后端 | 连接形态 | mean | P50 | P95 | P99 | SLO（P95 ≤ 2000ms） |
|---|---|---|---|---|---|---|---|
| 1 万块 | sqlite | 每线程一连接 | 501.8 | 494.3 | 570.7 | 625.2 | **PASS** |
| 5 万块 | sqlite | 每线程一连接 | 1212.8 | 1199.7 | 1677.6 | 1707.5 | **PASS** |
| 1 万块 | pg | 单连接（R2 轮†） | 647.6 | 646.1 | 672.3 | 1004.3 | **PASS** |
| 5 万块 | pg | **每线程一连接（R3 池化重测）** | 1781.5 | 1647.4 | **2443.2** | 2606.2 | **FAIL** |

（†pg-1 万行为 R2 轮单连接串行化形态——对延迟为**悲观上界**（串行只慢不快），
其 PASS 结论在池化形态下依然成立；本轮指令仅重跑 pg-5 万臂，未重测该档。
rps 一致性：pg-5 万 mean 1781.5ms → 5/mean=2.81；实测 rps 2.21 系 elapsed
含错峰建连窗口（13.6s 中 ~2.8s 无请求）——按有效请求窗 ≈10.5s 计 30/10.5≈2.86
与一致性检查吻合。）

**PG 5 万块 N=5 超标（R3 池化后仍 FAIL——如实申报，按用户裁定②处置：
P95 基线出数为 M1 完成口径、未达标项登记 M2 halfvec 复测、不改 NFR-8 文本）**

- **数据**：P95 演进——R2 单连接串行化 3437.5ms（Tester 复跑 3599/4116 亦为
  串行形态，一并作废）→ **R3 每线程一连接 2443.2ms（-29%）**；单请求档
  P95 1106.2ms（本轮）/836.2ms（R2 轮）——两轮值并列（R2/R3），观测带
  ±30~50%（实测离散：C wall +32% / A base +53% / A recall +52%），但两轮
  N=5 均显著超 2000ms——超标结论对观测带稳健；
- **机理**：超标主项为 recall 段（单请求 640~691ms；N=5 下 P50 1647ms ≈
  2.5× 单请求）——5 路并发 `<=>` **精确扫描**（500MB 堆表全扫/路）对容器
  CPU/内存带宽的争用；连接串行化（R2 假象）消除后仍余扫描级争用。候选
  缓解路径（均已登记）：G-6 收窄③ halfvec/表达式索引（bench7 用户裁定
  顺延——M2 复测）与 NFR-8 既有降级开关（rerank 候选 32→16 等）；
- **口径披露**：测量环境为 docker 容器（3.825GB 内存上限）——数值为该环境
  标定输入；环境间外推未验证、不在本报告下判断。

### NFR-8 延迟预算表对照（5 万块 · C full · P95；**sqlite 列=R2 轮、pg 列=R3 池化重测轮**——轮次口径见 §2 披露）

| 预算项 | 预算 | sqlite 实测（R2 轮） | pg 实测（R3 池化轮） | 备注 |
|---|---|---|---|---|
| query 嵌入 | ≤150ms | 160.7 | 156.0 | 模拟值=预算+注入误差（sleep 精度）；向量还原（2560 float 构造）含在其内 |
| 双路召回 | ≤300ms | 440.4 | 640.4 | **两后端均超**——BM25 1024 窗 + 向量 1024 精确扫描双路之和（R1 假值 141.9/99.7 系单路失真作废） |
| rerank | ≤1000ms | 210.2 | 210.2 | 模拟 RTT 200ms 档（两轮同值） |
| 其余（fuse 等） | ≤200ms | 82.9 | 103.1 | fuse=RRF+双断言+归一 |
| **合计 wall（单请求）** | ≤2000ms | 880.1 | 1106.2 | 单请求档两后端均在预算内 |
| N=5 并发 | — | 1677.6 | 2443.2 | sqlite PASS / **pg 超标**（机理与裁定②处置见 §2） |
| LLM 增强 | 800ms 并行不计关键路径 | enh_wait=0 | enh_wait=0 | 本档 enhancer=none；双计修正后该段单列 |

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

改造（commit 992a0e2 + R1 收口 + R2 P3-1/P3-2 完善）：`org_active_chunk_vectors`
返回 **packed float32 bytes 惰性流**（sqlite=vec_f32 BLOB 原样 / PG=named
cursor 服务端游标，不物化 float 对象）；`delete_open_flags` rid 分批 32,000/
语句（PG 65535 / sqlite 32766 参数上限——70,000 rid 删除双后端用例绿）；
`_crowding_means`＝候选驻留 float32 矩阵 + 池块流 + running top-k（维度异行
两遍同口径防御——P3-1；候选归一化原地除——P3-2）。

脚本 `bench4_recompute_100k.py`（子进程隔离测峰值——ru_maxrss 进程高水位不可
同进程叠加；数据源=合成 100k×2560 确定性向量普通文件 read 流——隔离算法私有
内存；**内存口径（P2-5/P3-7）**：`peak_rss_mb`=子进程绝对高水位 /
`rss_delta_mb`=对 import 后基线增量，两口径同记；候选比例经 `--cand-percent`）：

| 形态 | 规模 | 峰值内存（peak / Δ） | 耗时 |
|---|---|---|---|
| 旧（`list[tuple[int, list[float]]]` 物化） | 10,000 行 | Δ **1,036~1,093 MB**（三轮观测带：R1 首 1,092.7 / R2-5% 轮 1,036.2 / R2-100% 轮 1,092.5——同形态子进程重测；**跨轮手工记录（值见本表；bench4 save_result 同名覆盖不留历史）**） | 3.0~4.7s（同三轮） |
| 旧 · 线性外推 | 100,000 行 | **≈10.67 GB**（111.9KB/行 = packed bytes 的 11.2×） | —（16GB 机不可行） |
| 新（流 + 候选驻留 + running top-k） | 100k 池 · **5%** 候选 | **684.0 / 644.2 MB** | 6.81s |
| 新 · **全量候选**（`--cand-percent 100` 实测） | 100k 池 · 100k 候选 | **2,990.4 / 2,949.1 MB** | **87.68s（1.5 min）** |

- §5.4「10 万×2560 维分钟级可行」设计主张兑现（全量 87.68s）。全量档峰值
  2990.4MB 的构成（按实测分解）：**候选 packed 字典（100k×10KB ≈1.0GB）与
  候选 ndarray（≈0.95GB）在逐行转填期共存**（dict.pop 腾挪只减不增但转填
  完成前双份在栏——峰值即此窗口）+ sims 块（8192×4096 float32 ≈128MB）+
  池块缓冲（4096×10KB）+ Python 分配器对百万级 10KB transient 的保持
  （释放不归还 OS）；5% 抽样档无转填共存窗口（候选 50MB 级）——峰值 684MB
  主要为分配器保持与 sims/池块；
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
  （2/28）方向吻合——**实验验证已完成**（B-3② 停用词 +7.14pp 假设精确命中 /
  B-3④ ts_rank_cd 零差异——report-m1-5-g6-variants.md；③ OR 口径未动、决策
  材料齐备）；
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

## 9. 顺延/受阻申报（判据落笔归 supervised-coding）

| 项 | 状态 | 原因/基础 |
|---|---|---|
| G-6 收窄③ halfvec 对比 | 顺延（用户裁定） | §8 |
| B-3① 真实嵌入模型重测 | **受阻——申报材料已产出** | 无网关/ollama 环境；接入方案/选型/重测步骤/判据见 report-m1-5-g6-real-model-deferred.md |
| B-3③ OR 口径变更 | **未动（按拍板走决策流程）** | 决策材料齐备：偏差 10.72pp 分解（§5）+ 停用词可收回 7.14pp + ts_rank_cd 无效路径排除（report-m1-5-g6-variants.md） |
| G-8② 真实网关抖动分布 | 受阻（同 B-3①） | 可构造面已实测（噪声底/判定剖面——report-m1-5-g8-threshold.md）；剩余标定待真实网关版本对 |
| G-8① 真实 MRL 模型验证 | 受阻（同 B-3①） | 代理机制面已实测（r@10 损失 0.00pp——report-m1-5-g8-mrl.md）；真实模型随 0.6b/网关就位补 |

## 10. 门禁与复现

- 门禁：`LATTICE_PG_DSN=… bash scripts/test_gate.sh` → **R2 复验 663 passed /
  1 deselected（manual 走查标记）/ 0 skipped，双后端双模式**；pg 臂 225 实跑
  （[pg] 参数化 193 + PG 专用 32）。计数对账：M1-4 交付 604+1 → R1 +57
  （`tests/test_m1_5_dev.py`：C3 fuse 4 + A1 改造 4 + C1 list_documents 5 +
  C2 畸形参数 44）→ **R2 +2**（P2-3 状态值全集 / P2-4 非成员 403）；
- 复现：`uv run python benchmarks/bench4_recompute_100k.py`；
  `uv run python benchmarks/bench5_slo_perf03.py`（pg 臂需 LATTICE_PG_DSN）；
  `uv run python benchmarks/bench6_perf04.py`；`uv run python benchmarks/llm_hook_budget.py`。
