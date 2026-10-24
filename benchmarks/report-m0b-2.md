# M0b-2 实验报告——ACL 双写法性能 / 向量同表 vs 分表 / 委托 token 客户端实测

> 任务：task-knowledge-lattice-m0b-2（2026-10-24）。三项建议供 M0b-3 拍板后回写 schema v1.1：
> **①dims_json 去留 ②分表与否 ③模型迁移蓝绿方案一/二**。
> 依据：TC-PERF-01（v1.5.2 两档口径）、TC-PERF-02、TC-AUTH-04 附注；design §5.1 性能注 /
> §4 向量注 / §5.3 重嵌入蓝绿 / §8 M0b.2；known-gaps G-6/G-8。

---

## 0. 结论速览（三项建议）

| # | 拍板项 | 建议 | 一句话依据 |
|---|---|---|---|
| 1 | dims_json 去留 | **删 dims_json，选定 visible_docs（按文档）路线；PG 渲染器 CTE 加 `MATERIALIZED`（一词，sqlite ≥3.35 同语法可用）** | sqlite 3~5× 优势；PG 修复计划病理后持平~反超；visible_docs SQL 双方言参数记号归一化后**逐字相同**（json_each 则方言函数绑定）；12/12 组合结果集等价复核通过 |
| 2 | 分表与否 | **分表 `chunk_vectors(rid, embed_model, embedding)`，`PRIMARY KEY(rid, embed_model)`** | 向量路分表仅慢 7~12%（可接受）；不分表则 sqlite 非向量路（可见性/元数据扫描）被 10KB 宽行拖慢 **2.09×**；WAL 写入侧布局中性（±3%）；蓝绿并存只有分表键含 embed_model 才成立 |
| 3 | 蓝绿方案一/二 | **方案二（分表蓝绿）** | 零降级 + 原子切零成本（配置翻转）+ 延后清理自主窗口；方案一迁移窗口向量路全程降级且 PG 侧写放大约 2×（置空 614MB + 新向量 610MB WAL）；方案二代价 = 迁移期双倍向量存储（50K 档 PG 高水位 628→1258MB，清理后页内复用、不即时归还 OS） |

---

## 1. 机器口径与复跑

| 项 | 值 |
|---|---|
| 机器 | macOS 26.5.2 arm64（Apple Silicon，10 标称核） |
| Python | 3.12.10（uv 托管） |
| SQLite | 3.47.1（WAL / synchronous=NORMAL / busy_timeout=5000 / foreign_keys=ON——`store/sqlite` 连接工厂生产同款 PRAGMA） |
| PostgreSQL | 16.15 + pgvector 0.8.7（Docker `lattice-pg`，4 vCPU / ~3.83GB 内存限额）；psycopg3 单连接 autocommit，str→unknown dumper、TimeZone=UTC（`store/postgres` 工厂纪律） |
| numpy | 2.5.4（合成向量 PCG64） |
| 随机种子 | `20261024`（文档维度分布 python `random.Random`；合成向量 `numpy.random.default_rng`——Generator 分布流跨 numpy 大版本理论可漂移，本报告结论不依赖向量具体取值，复跑对比请同 numpy 版本或以耗时/WAL 为准） |
| 造数路径 | 生产写路径全链：`backend.create_document` + `backend.insert`（pending_dims 解析 / document_dimensions / dims_json 冗余投影 / FTS 触发器 / tsvector GENERATED / D20 首次切换） |
| 嵌入 API | **零真实调用**——向量全部合成（2560 维 unit float32 ≈ 10KB/块，按 embed_model 标签写入） |
| 计时 | `time.perf_counter`；nearest-rank 分位（P95 = ceil(0.95·n) 序）；预热后采样；每次计时含 fetchall 全结果物化（两写法同口径） |
| 计时公平性 | sqlite：python sqlite3 语句缓存（同 SQL 走已编译 prepared statement）；PG：psycopg3 `prepare_threshold=5`（预热轮后自动转服务端 prepared statement）。两后端均单连接顺序执行，无并发干扰 |

**复跑**（工作目录 `knowledge-lattice/`）：

```bash
export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
uv run python benchmarks/bench1_acl_dual_write.py     # 实验 1（~7 min，pg 5 万档造数 12s）
uv run python benchmarks/bench2_vector_layout.py      # 实验 2（~8 min；pg 文本写路径 512MB×2 是大头）
uv run python benchmarks/bench3_mcp_client.py         # 实验 3（~10s；自动 spawn mcp1.x 独立 env 的 driver）
```

原始数据表落 `data/bench-results/bench{1,2,3}.json`（`data/` 已 gitignore，脚本可复跑再生）；
benchmark 代码与常规 pytest 收集双重隔离（`testpaths=["tests"]` + 文件名不以 `test_` 开头），
门禁 `scripts/test_gate.sh` 双后端双模式 **249 passed + 1 deselected、0 skipped** 不受影响（2026-10-24 实跑）。

---

## 2. 实验 1（TC-PERF-01）：按块 json_each vs 按文档 visible_docs

### 2.1 主数据表（2 档 × 2 后端 × 2 写法 × 3 用户形态；预热 3 轮，1 万档 n=30 / 5 万档 n=15）

| 块档 | 后端 | 用户形态 | 写法 | 结果行数 | P50 ms | P95 ms |
|---|---|---|---|---|---|---|
| 10000 | sqlite | u_narrow（region=CN, tax_type=VAT） | json_each(按块) | 3600 | 17.21 | 18.00 |
| 10000 | sqlite | u_narrow | visible_docs(按文档) | 3600 | 4.99 | 5.15 |
| 10000 | sqlite | u_broad（全集授权） | json_each | 10000 | 24.77 | 25.43 |
| 10000 | sqlite | u_broad | visible_docs | 10000 | 10.44 | 10.58 |
| 10000 | sqlite | u_empty_tax（tax_type 空授权=T22 形态） | json_each | 1260 | 13.07 | 13.19 |
| 10000 | sqlite | u_empty_tax | visible_docs | 1260 | 2.74 | 2.79 |
| 50000 | sqlite | u_narrow | json_each | 17800 | 90.32 | 90.98 |
| 50000 | sqlite | u_narrow | visible_docs | 17800 | 28.17 | 28.35 |
| 50000 | sqlite | u_broad | json_each | 50000 | 129.43 | 131.68 |
| 50000 | sqlite | u_broad | visible_docs | 50000 | 56.18 | 56.46 |
| 50000 | sqlite | u_empty_tax | json_each | 5800 | 68.26 | 68.59 |
| 50000 | sqlite | u_empty_tax | visible_docs | 5800 | 16.12 | 16.48 |
| 10000 | pg | u_narrow | json_each(按块 jsonb) | 3600 | 10.91 | 11.62 |
| 10000 | pg | u_narrow | visible_docs(按文档) | 3600 | 69.20 | 69.82 |
| 10000 | pg | u_narrow | **visible_docs+MATERIALIZED(补充)** | 3600 | **8.25** | **9.23** |
| 10000 | pg | u_broad | json_each | 10000 | 14.75 | 15.21 |
| 10000 | pg | u_broad | visible_docs | 10000 | 8.14 | 89.50 ⚠ |
| 10000 | pg | u_broad | **visible_docs+MATERIALIZED** | 10000 | **7.53** | **8.17** |
| 10000 | pg | u_empty_tax | json_each | 1260 | 4.19 | 4.43 |
| 10000 | pg | u_empty_tax | visible_docs | 1260 | 3.84 | 4.49 |
| 10000 | pg | u_empty_tax | **visible_docs+MATERIALIZED** | 1260 | **3.39** | **3.97** |
| 50000 | pg | u_narrow | json_each | 17800 | 58.15 | 61.29 |
| 50000 | pg | u_narrow | visible_docs | 17800 | 379.24 | 387.02 |
| 50000 | pg | u_narrow | **visible_docs+MATERIALIZED** | 17800 | **44.35** | **46.02** |
| 50000 | pg | u_broad | json_each | 50000 | 75.85 | 78.31 |
| 50000 | pg | u_broad | visible_docs | 50000 | 476.86 | 486.98 |
| 50000 | pg | u_broad | **visible_docs+MATERIALIZED** | 50000 | 78.09 | 78.72 |
| 50000 | pg | u_empty_tax | json_each | 5800 | 36.30 | 37.65 |
| 50000 | pg | u_empty_tax | visible_docs | 5800 | 326.14 | 328.10 |
| 50000 | pg | u_empty_tax | **visible_docs+MATERIALIZED** | 5800 | **29.76** | **30.05** |

⚠ 计划不稳定：该格 P50/P95 双峰（generic/custom plan 在 psycopg 自动 prepare 前后摇摆，两次全量运行间也在 8ms↔86ms 间跳变）——inline 形态在 PG 上的固有不稳定，MATERIALIZED 后消失（8 组补充格全部单峰稳定）。

### 2.2 等价性复核（验收 1——性能实验不改变正确性结论）

**12/12 组合（2 档 × 2 后端 × 3 用户）两写法结果集（rid,id,doc_id）多重集逐行等价 ✓**；PG 的
MATERIALIZED 补充变体同样纳入复核（全部 ✓）。TC-ACL-07 语义在 1/5 万实验规模下成立，
未见任何不等价迹象——**等价性结论未因规模改变**。

### 2.3 计划形态：PG inline 的病理与 MATERIALIZED 一词修复

- **sqlite**（EXPLAIN QUERY PLAN）：visible_docs CTE 一次物化（`LIST SUBQUERY` + `REUSE`），
  块侧走 `uq_chunks_docver` 索引——正是设计意图（按文档算一次）。
- **PG inline**（EXPLAIN ANALYZE，200 文档样本）：CTE 被内联成 Semi Join，文档级可见性
  谓词（两层嵌套 NOT EXISTS × 2 维度）**按块重复求值**——反连接分支 `loops=2000`（=块数），
  与写法意图（按文档算一次）正好相反；5 万档实测 5~6× 劣化即来源于此。
- **PG + `AS MATERIALIZED`**：CTE 强制一次物化（loops=文档数），外层 semi join；
  5 万档 u_narrow/u_empty_tax **反超** json_each（44.35 vs 58.15 / 29.76 vs 36.30 ms），
  u_broad 持平（78.09 vs 75.85 ms）。
- `AS MATERIALIZED` 语法 sqlite ≥3.35 亦接受（3.47.1 实测可用；sqlite 本就默认物化，
  关键字为 no-op）——**渲染器可双方言统一加注**，不破坏「同一中性构造」。

### 2.4 可移植性判据（D24）

同一 AclPlan（u_narrow）双方言渲染产物，参数记号归一化（`%(x)s`→`:x`）后程序化比对：

- **visible_docs：逐字相同** ✓——CTE 体来自同一 `acl_ast.build_visible_docs_parts`，双方言
  仅参数记号风格差异（加 MATERIALIZED 后双方言仍可保持逐字相同）；
- json_each：**必然不同**——`json_each(c.dims_json, '$.region')`（sqlite）vs
  `jsonb_array_elements_text(jsonb_extract_path(c.dims_json, 'region'))`（PG），
  按块扫描是各方言专属注入点（dims_scan 工厂），语义等价但文本/函数族完全绑定方言。

### 2.5 建议一：**删 dims_json、选 visible_docs + PG 渲染器加 MATERIALIZED**

依据汇总：①sqlite 3~5× 优势（两档全部形态）；②PG 加 MATERIALIZED 后 2 胜 1 平，
且消除 inline 的计划不稳定性（⚠ 格）；③可移植性判据满分（归一化后逐字同文，
json_each 做不到）；④等价性 12/12 复核通过，正确性结论不受影响；⑤删 dims_json
消除「文档维度变更时服务层同步刷投影」的一致性维护点（design §4 取舍注）。
残留工作（M0b-3）：渲染器加一词 + 双删 json_each 模板 + schema v1.1 迁移去列。

---

## 3. 实验 2（TC-PERF-02）：向量同表 vs chunk_vectors 分表

口径：50,000 块（5,000 文档 × 10 块）、2560 维 float32（512MB 向量载荷/后端）、
双后端、两布局**同库先后度量**（同一份块行与向量）；写路径=生产链形态
（同表=块先落库后 UPDATE 回写；分表=INSERT `chunk_vectors`，对称 2000 行/批显式事务）；
查询=固定谓词（org/version/tombstone + embed_model）隔离布局变量，不叠 ACL 编译产物。

### 3.1 写入相位与 WAL 放大

| 后端 | 布局 | 写入耗时 | 吞吐（行/s） | WAL MB | 备注 |
|---|---|---|---|---|---|
| sqlite | 同表 UPDATE | 2.17 s | 23,091 | 619.8 | 载荷 512MB → WAL 放大 1.21× |
| sqlite | 分表 INSERT | 1.19 s | 41,856 | 621.1 | INSERT 比 UPDATE 快 1.8×（无旧行重写） |
| pg | 同表 UPDATE | 61.76 s | 810 | 610.8 | 客户端文本载荷（~1GB 文本）传输主导 |
| pg | 分表 INSERT | 59.78 s | 836 | 595.7 | 布局差异被传输成本掩盖 |

**结论：WAL 放大是载荷属性（~1.2×），对布局中性**（sqlite 619.8 vs 621.1；pg 610.8 vs 595.7，
±3%）。PG 写吞吐 ~810 行/s 由 pgvector 文本形态客户端传输主导（M1 可用二进制/COPY 提速，
非布局问题，登记不展开）。库尺寸（pg_total_relation_size 含 toast+索引）：pg chunks 表
无向量 28.1MB → 同表后 675.0MB；分表形态 chunk_vectors 627.7MB / chunks 保持 28MB 级。

### 3.2 查询形态：向量路与非向量路（回表/拖累度量）

| 后端 | 形态 | P50 ms | P95 ms | 相对基线 |
|---|---|---|---|---|
| sqlite | 向量召回 top-20（同表） | 268.39 | 271.93 | 基线 |
| sqlite | 向量召回 top-20（分表 JOIN） | 285.80 | 360.57 | +6.5%（P95 +33%） |
| sqlite | 元数据扫描（基线：向量全 NULL） | 39.27 | 40.09 | 基线 |
| sqlite | 元数据扫描（同表 10KB 宽行） | **82.07** | 82.62 | **2.09× 拖慢** |
| sqlite | 元数据扫描（分表对照 narrow 表） | 40.56 | 40.79 | 与基线持平（+3%） |
| sqlite | 点查 rid IN ×20（两布局） | 0.02 | 0.02 | 无差异 |
| pg | 向量召回 top-20（同表） | 83.72 | 86.86 | 基线 |
| pg | 向量召回 top-20（分表 JOIN） | 93.39 | 98.50 | +11.5% |
| pg | 元数据扫描（基线 NULL） | 18.00 | 18.52 | 基线 |
| pg | 元数据扫描（同表，TOAST 外置） | 21.90 | 22.67 | +21.7%（TOAST 指针+填充） |
| pg | 元数据扫描（分表对照 narrow） | 16.84 | 17.13 | 比基线还快 6.4% |
| pg | 点查 rid IN ×20（两布局） | 0.17 | 0.19 | 无差异 |

两布局向量召回 top-20 rid 集合一致（同向量同谓词，集合等价 ✓）。

**读侧结论**：分表的代价（向量路 +7~12%）小于不分表的代价（sqlite 非向量路 2.09×）。
sqlite 宽行把可见性/BM25 前置过滤这类**每次检索必经**的扫描拖慢一倍（10KB 行把页密度
打到 ~1/2.4，且 overflow 链随行增长）；pg 因 TOAST 外置只受 ~22% 拖累，分表后 narrow
表比 NULL 基线还略快（省 18B toast 指针/行）。**本实验的元数据扫描是全结果物化形态
（实验 1 同款可见性产物）；带索引裁剪的 top-k 路径（FTS 命中少量行）受宽行影响更小——
口径限制，见 §5。**

### 3.3 模型迁移蓝绿判据实测（方案一 vs 方案二，50K 块档）

| 后端 | 相位 | 耗时 | WAL MB | 关键观察 |
|---|---|---|---|---|
| sqlite | 方案一：置空（`UPDATE … SET embedding=NULL, embed_model=NULL`） | 0.51 s | 207.5 | 置空即降级（向量路谓词落空，BM25 单路） |
| sqlite | 方案一：空间回收（VACUUM） | 2.37 s | — | 库文件 1252→649MB（重写整库） |
| pg | 方案一：置空 | 1.96 s | 614.2 | 置空 WAL ≈ 满载写（新元组版本 + FPI） |
| pg | 方案一：空间回收（VACUUM ANALYZE） | 1.55 s | — | chunks 684→70MB ✓（TOAST 尾部空页 truncate 归还 OS） |
| sqlite | 方案二：新标签并存写入（50K 行） | 1.74 s | 621.7 | 服务端 INSERT..SELECT（布局代价口径，不含嵌入 API） |
| sqlite | 方案二：旧标签延后清理 | 0.38 s | **4.3** | DELETE 只记释放页——极廉价 |
| sqlite | 方案二：空间回收 | 2.20 s | — | 1266→649MB |
| pg | 方案二：新标签并存写入 | 1.47 s | 593.9 | 覆盖率 old=50000 / new=50000 → 100% |
| pg | 方案二：旧标签延后清理 | 0.82 s | 551.9 | DELETE 记满量死元组 |
| pg | 方案二：空间回收 | 1.21 s | — | **1257.8MB 不归还 OS**：空页在文件前段（旧标签先写）、活行在尾段，plain VACUUM 只 truncate 尾部空页——空间进空闲表由后续写入复用 |

「current_model 原子切」= 配置标签翻转（§5.8 dict_rev 同款模式），零 SQL、瞬时——两方案同点。
迁移全周期 WAL（含新向量落库）：方案一 ≈ 置空 + 新写（sqlite 207.5+620≈828MB / pg 614+610≈1224MB）；
方案二 ≈ 新写 + 清理（sqlite 621.7+4.3≈626MB / pg 593.9+551.9≈1146MB）——同量级，
差异不在 WAL 在**降级语义**：方案一重嵌入窗口内向量路全程不可用（设计已知口径），
方案二旧标签持续服务到原子切瞬间、零降级。

### 3.4 建议二（分表与否）与建议三（蓝绿方案）

**建议二：分表 `chunk_vectors(rid, embed_model, embedding)`，`PRIMARY KEY(rid, embed_model)`**。
依据：①非向量路保护（sqlite 2.09× 拖慢 vs 分表持平；pg +22% 拖慢 vs 分表 −6%）；②向量路
代价可接受（+7~12%）；③WAL 布局中性、写吞吐分表略优（sqlite INSERT 1.8× 于 UPDATE）；
④**蓝绿并存物理上要求键含 embed_model**——实测仅 `PRIMARY KEY(rid)` 的分表在新标签写入时
即 IntegrityError，键形是 v1.1 的必答项；⑤空间成本透明（向量集中一张表，chunks 窄表可整体
留驻页缓存）。代价与限制：分表后 sqlite 向量路 P95 方差增大（360 vs 272ms）、pg 高水位在
蓝绿窗口翻倍（见建议三）——可接受。

**建议三：方案二（分表蓝绿）**。依据：①零降级（方案一窗口期 BM25 单路是既定设计取舍，
但每次换模型都吃一次）；②原子切零成本；③清理窗口自主（低峰），sqlite 清理 WAL 仅 4.3MB；
④方案一在 PG 的写放大约 2×（置空 614MB + 新写 610MB，且置空本身即满量级 WAL）。
代价（需拍板时知情）：迁移期向量存储双倍（50K 档 PG 高水位 628→1258MB），清理后 plain
VACUUM 不归还 OS（空页在文件前段）——空间由后续写入复用；若必须归还，低峰 `VACUUM FULL`/
pg_repack（锁表/重写，另行窗口）。若存储预算极紧且业务可接受降级窗口，方案一仍为可行
退路（置空 2s、回收 1.5s，pg 空间确实归还）。

---

## 4. 实验 3（TC-AUTH-04 附注）：langchain-mcp-adapters 委托 token 客户端

### 4.1 版本耦合发现（先于一切形态问题）

- PyPI 全部 langchain-mcp-adapters 版本（≤0.3.2，2026-10-24）依赖 mcp 1.x 的
  `mcp.shared.context.RequestContext`；本项目 fastmcp 4.1.3 经 `fastmcp-slim==4.1.3`
  **精确钉死 mcp==2.3.0**——**同进程共存不可能**（adapters 0.3.1 在项目 env import 即
  `ImportError`，实测三次）。
- 处置：依赖**不进 pyproject**（§7 最小引入——不留「引入即坏」的组合）；客户端实测跑在
  uv 独立钉版 env（`uv run --no-project --with langchain-mcp-adapters==0.3.1 --with 'mcp<2'`
  → mcp 1.30.0），服务端留项目 env。**这同时是部署侧的真实形态**：adapters 属于调用方
  （agent 运行时）的依赖栈，不随服务端部署。
- 附带实证：**mcp 1.30.0 客户端 ⇄ fastmcp 4.1.3（mcp 2.3.0）服务端线级兼容**——握手成功，
  协商协议版本 `2025-11-25`，`initialize/list_tools/call_tool` 全通。
- TC-AUTH-04 附注结论回写用例文档时建议带上本条（adapters 版本演进至 mcp 2.x 兼容前，
  客户端集成须独立 env/独立依赖组）。

### 4.2 三种客户端形态与实测数据（真实 HTTP，uvicorn 线程 + FastMCP search + 开发 JWT）

| 形态 | 代码形态 | 实测（P50/P95） |
|---|---|---|
| **A：每用户会话一个 client**（推荐） | `client = MultiServerMCPClient({...headers: {Authorization: Bearer <该用户 token>}})`；`async with client.session("lattice") as s:` 持有会话，`await s.call_tool("search", {...})` 热调用 | 会话建立（enter+initialize）**9.38 / 10.09 ms**；持有会话热调用 **2.19 / 2.81 ms** |
| **A'：adapters 默认 langchain tool 路径** | `tools = await client.get_tools()` → `await tool.ainvoke({...})`——adapters 0.3.1 明确「**每次工具调用新建一个 session**」（官方 docstring） | 每调用（handshake+call）**15.56 / 17.47 ms**——是热调用的 **7.1×** |
| **B：共享中继/每请求注入头** | 每次调用以调用方 token 现场构造 `MultiServerMCPClient` + `session()`（headers 是传输层构造参数，会话内固定，无法按请求换） | 每请求（建会话+调用）**15.03 / 15.56 ms** |

规模化足迹（形态 A，10 用户会话并持）：建立 102.3ms（≈10ms/会话，可并行化）；
**FD +10（1/会话）**；内存 ≈192KB/会话（ru_maxrss，macOS 计字节）；10/10 调用成功。
首次 `initialize` 30~38ms、首次 `list_tools` ~126ms（含 jieba 懒加载等一次性成本）。

### 4.3 token 过期刷新行为（dev JWT，ttl=2s 现场铸造）

- **认证执行点在工具层而非传输层**（M0a-3 形态：FastMCP http_app 无传输级 auth，
  `_auth_and_org` 在每次 tool call 验 Bearer）——因此**会话不因 token 过期而断**，
  过期后调用返回 `isError=True`（401 语义 ToolError），服务端日志可见 `Error calling tool 'search'`。
- 形态 A：同会话过期调用失败 → **重建会话（新 token）即恢复**（实测 ✓）；headers 构造时
  固定，会话内存活 token 不可替换。
- 形态 B：过期 token 当次调用失败 → **下一请求用新 token 即恢复**（无会话态可污染，实测 ✓）。
- 结论：**A'（默认 langchain tool 路径）在过期场景反而最鲁棒**（每次调用都是新会话新头），
  但常态每调用 7× 开销；**A 的正确姿势是「401 即弃会话重建」**（重建成本 9.4ms，可接受）；
  会话内热调用 2.2ms 的延迟收益是 A 存在的全部理由。**推荐形态 A + 401 重建**；
  连接池化/自定义 transport（headers 从 contextvar 取）在 adapters 0.3.x 无现成挂钩
  （headers 是构造参数），不值得为省 9.4ms 自维护 transport 分叉——留待 adapters 演进。

### 4.4 服务端观察（顺手记录，M1 硬化候选）

会话关闭时 uvicorn 偶发 `Unexpected ASGI message 'http.response.start' sent, after
response already completed`（客户端断开 GET/SSE 流后服务端仍尝试写）——噪音级、不影响
功能（driver 全部断言通过），登记为 M1 观察项。

---

## 5. 口径限制与不确定项（如实申报）

1. **实验规模上限 5 万块**（v1.5.2 缩档口径）：visible_docs 的文档集计算复杂度随文档数
   线性、json_each 随块数线性——10 万+/百万块外推未验证（M1 TC-PERF 轮补）。
2. **PG visible_docs inline 的计划不稳定**（⚠ 格双峰）在 generic/custom plan 间摇摆；
   MATERIALIZED 后 8 组全稳。若 M0b-3 不采纳 MATERIALIZED，需在报告中保留该风险。
3. **实验 2 元数据扫描为全结果物化形态**（无 LIMIT 全量可见集）——宽行拖累在该形态最重；
   FTS 索引裁剪后的 top-k 路径拖累更小，本实验未单独度量（M1 检索管线全链再标）。
4. **PG 客户端写路径 ~810 行/s 为文本形态传输主导**——二进制/COPY 提速属 M1 优化项，
   未展开；布局比较不受影响（两布局同路径对称）。
5. **合成向量 ≠ 真实嵌入分布**（单位球均匀 vs 语义聚集）：对 IO/扫描类结论无影响，
   对距离计算的分支预测/缓存局部性有微小影响——计时结论不依赖。
6. **实验 3 为单机 localhost 回环**：会话建立 9.4ms 含 TCP+HTTP+MCP initialize 三往返；
   跨网段部署按 RTT 放大（每会话 ≈3×RTT + 10ms 处理）。并发会话上限未压测（TC-PERF-03
   SLO 压测已取消，顺延 M1）。
7. **蓝绿「新标签并存写入」用服务端 INSERT..SELECT 度量布局代价**（零真实嵌入 API 口径）——
   真实重嵌入周期 = 嵌入 API 吞吐主导（P3-11 接入后另测），不在本实验量程。

## 6. 工件索引

- 造数/计时脚本：`benchmarks/bench_common.py`（共享 harness）、`bench1_acl_dual_write.py`、
  `bench2_vector_layout.py`、`bench3_mcp_client.py` + `bench3_client_driver.py`
- 原始数据：`data/bench-results/bench{1,2,3}.json`（含完整计划文本 EXPLAIN/EQP、
  全部分位数、蓝绿逐相位尺寸；`data/` gitignore，可复跑再生）
- 门禁回归证据：`scripts/test_gate.sh` GATE PASS（249 passed + 1 deselected ×2 模式，
  pg 臂 45 组参数化全实跑，2026-10-24 20:47）
