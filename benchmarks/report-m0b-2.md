# M0b-2 实验报告——ACL 双写法性能 / 向量同表 vs 分表 / 委托 token 客户端实测

> 任务：task-knowledge-lattice-m0b-2（2026-10-24，R2 修订版——吸收 Committer R1 审查
> P2×5/P3×15 与 Tester 3 条措辞瑕疵：分表向量路补窄基表干净口径并重跑、PG 并行计划
> 伪差异发现与口径统一、蓝绿共存期读路径实测、两条关键证据脚本化、删除 dims_json
> 与分表 v1.1 影响清单、措辞精度与口径披露全面修正）。
>
> 三项建议供 M0b-3 拍板后回写 schema v1.1：**①dims_json 去留 ②分表与否 ③模型迁移蓝绿
> 方案一/二**。依据：TC-PERF-01（v1.5.2 两档口径）、TC-PERF-02、TC-AUTH-04 附注；
> design §5.1 性能注 / §4 向量注 / §5.3 重嵌入蓝绿 / §8 M0b.2；known-gaps G-6/G-8。

---

## 0. 结论速览（三项建议）

| # | 拍板项 | 建议 | 一句话依据 |
|---|---|---|---|
| 1 | dims_json 去留 | **删 dims_json，选定 visible_docs（按文档）路线；PG 渲染器 CTE 加 `MATERIALIZED`（一词，sqlite ≥3.35 同语法可用）** | sqlite 全形态 **2.3~4.8×** 优势；PG 修复计划病理后 3/3 形态反超 json_each（本轮 50K 档 17~28% 优势）；visible_docs SQL 双方言参数记号归一化后**逐字相同**（json_each 则方言函数绑定）；12/12 组合结果集等价复核通过。残留工作量见 §2.6 影响清单 |
| 2 | 分表与否 | **分表 `chunk_vectors(rid, embed_model, embedding)`，`PRIMARY KEY(rid, embed_model)`；删 chunks.embedding、保留 chunks.embed_model 为摄取状态标签**（v1.1 形态详见 §3.5） | 向量路分表**零代价**（干净口径：sqlite 窄基表 **-8.9%** 反超、pg P50 **±2%** 等价且 P95 窄表反优 ~14%——R1 的 pg +11.5% 系并行计划伪差异、sqlite +6.5% 系宽基表上界，本轮统一串行后宽基表复现 +5.2%、窄基表 -8.9%）；不分表则 sqlite 非向量路被 10KB 宽行拖慢 **2.0×**（三跑稳定）；WAL 写入侧布局中性；蓝绿并存物理上要求键含 embed_model（PK(rid) 实测即 IntegrityError）。**本实验为精确扫描口径；M1 若上 HNSW，pgvector 2560 维 > 2000 维索引上限，`vector` 列不能直接建索引，需 `halfvec` 或表达式索引（另行实验）** |
| 3 | 蓝绿方案一/二 | **方案二（分表蓝绿）** | **功能零降级**（旧标签持续服务到原子切瞬间）+ 原子切零成本（配置翻转）+ 延后清理自主窗口；**共存窗口读性能**：sqlite 零放大（251.6 vs 251.6ms，先过滤后距离不触旧向量载荷）、pg **有读代价风险且幅度跑间波动**（多次观测约 -3%~+52%；表内 209.6/236.5 为其中一次观测，vs 单标签 197.6/200.2；串行全扫过双倍行页——定性为准，M1 真实 vacuum 策略下复测）；方案一迁移窗口向量路**全程功能降级**（BM25 单路）且置空+重写的 PG WAL ≈ 单次满写向量集的 **2.0×**（616.6+593.7 ≈ 1210MB vs 593.7MB）；方案二代价 = 迁移期双倍向量存储（50K 档 PG 高水位 628→1258MB，清理后页内复用、不即时归还 OS） |

---

## 1. 机器口径与复跑

| 项 | 值 |
|---|---|
| 机器 | macOS 26.5.2 arm64（Apple Silicon，10 标称核） |
| Python | 3.12.10（uv 托管） |
| SQLite | 3.47.1（WAL / synchronous=NORMAL / busy_timeout=5000 / foreign_keys=ON——`store/sqlite` 连接工厂生产同款 PRAGMA） |
| PostgreSQL | 16.15 + pgvector 0.8.7（Docker `lattice-pg`，4 vCPU / ~3.83GB 内存限额）；psycopg3 单连接 autocommit，str→unknown dumper、TimeZone=UTC（`store/postgres` 工厂纪律）；**实验 2 全部查询会话级禁用并行**（`SET max_parallel_workers_per_gather=0`——原因见 §3.2"并行计划伪差异"） |
| numpy | 2.5.4（合成向量 PCG64） |
| 随机种子 | `20261024`（文档维度分布 python `random.Random`；合成向量 `numpy.random.default_rng`——Generator 分布流跨 numpy 大版本理论可漂移，本报告结论不依赖向量具体取值，复跑对比请同 numpy 版本或以耗时/WAL 为准） |
| 造数路径 | 生产写路径全链：`backend.create_document` + `backend.insert`（pending_dims 解析 / document_dimensions / dims_json 冗余投影 / FTS 触发器 / tsvector GENERATED / D20 首次切换） |
| 嵌入 API | **零真实调用**——向量全部合成（2560 维 unit float32 ≈ 10KB/块，按 embed_model 标签写入） |
| 计时 | `time.perf_counter`；nearest-rank 分位（P50=中位；P95 = **ceil(0.95·n)-1** 下标——n<20 时 P95≈max，本报告实验 1/2 全部计时格 n≥20、实验 3 形态格 n=15/热调用 n=40 并在 §4.2 注明）；实验 1/2 预热 1~3 轮后采样、每次计时含 fetchall 全结果物化（同组内同口径）；**实验 3 各相位无显式预热**（首几次调用即数据点） |
| 计时公平性 | sqlite：python sqlite3 语句缓存（同 SQL 走已编译 prepared statement）；PG：psycopg3 `prepare_threshold=5`（预热轮后自动转服务端 prepared statement）。两后端均单连接顺序执行，无并发干扰 |

**复跑**（工作目录 `knowledge-lattice/`）：

```bash
export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
uv run python benchmarks/bench1_acl_dual_write.py     # 实验 1（~8 min）
uv run python benchmarks/bench2_vector_layout.py      # 实验 2（~9 min；pg 文本写路径 512MB×2 是大头）
uv run python benchmarks/bench3_mcp_client.py         # 实验 3（~12s；自动 spawn mcp==1.30.0 独立 env 的 driver）
```

原始数据表落 `data/bench-results/bench{1,2,3}.json`（`data/` 已 gitignore，脚本可复跑再生；
含完整 EXPLAIN ANALYZE/EQP 计划文本与 loops 解析判定）；benchmark 代码与常规 pytest 收集
双重隔离（`testpaths=["tests"]` + 文件名不以 `test_` 开头），门禁 `scripts/test_gate.sh`
双后端双模式 **249 passed + 1 deselected、0 skipped** 不受影响（2026-10-24 R2 实跑）。

---

## 2. 实验 1（TC-PERF-01）：按块 json_each vs 按文档 visible_docs

### 2.1 主数据表（2 档 × 2 后端 × 2 写法 × 3 用户形态；预热 3 轮，1 万档 n=30 / 5 万档 n=20；R2 权威跑 2026-10-24 21:5x）

| 块档 | 后端 | 用户形态 | 写法 | 结果行数 | P50 ms | P95 ms |
|---|---|---|---|---|---|---|
| 10000 | sqlite | u_narrow（region=CN, tax_type=VAT） | json_each(按块) | 3600 | 17.65 | 17.82 |
| 10000 | sqlite | u_narrow | visible_docs(按文档) | 3600 | 5.09 | 5.97 |
| 10000 | sqlite | u_broad（全集授权） | json_each | 10000 | 25.33 | 35.85 |
| 10000 | sqlite | u_broad | visible_docs | 10000 | 10.54 | 10.97 |
| 10000 | sqlite | u_empty_tax（tax_type 空授权=T22 形态） | json_each | 1260 | 13.41 | 13.56 |
| 10000 | sqlite | u_empty_tax | visible_docs | 1260 | 2.81 | 2.88 |
| 50000 | sqlite | u_narrow | json_each | 17800 | 90.50 | 100.55 |
| 50000 | sqlite | u_narrow | visible_docs | 17800 | 28.04 | 28.29 |
| 50000 | sqlite | u_broad | json_each | 50000 | 128.73 | 131.02 |
| 50000 | sqlite | u_broad | visible_docs | 50000 | 56.73 | 57.41 |
| 50000 | sqlite | u_empty_tax | json_each | 5800 | 69.00 | 69.55 |
| 50000 | sqlite | u_empty_tax | visible_docs | 5800 | 16.76 | 16.98 |
| 10000 | pg | u_narrow | json_each(按块 jsonb) | 3600 | 10.47 | 11.19 |
| 10000 | pg | u_narrow | visible_docs(按文档，inline) | 3600 | 69.41 | 70.66 |
| 10000 | pg | u_narrow | **visible_docs+MATERIALIZED(补充)** | 3600 | **8.17** | **9.85** |
| 10000 | pg | u_broad | json_each | 10000 | 14.57 | 15.15 |
| 10000 | pg | u_broad | visible_docs(inline) | 10000 | 85.47 | 88.14 |
| 10000 | pg | u_broad | **visible_docs+MATERIALIZED** | 10000 | **14.12** | **14.85** |
| 10000 | pg | u_empty_tax | json_each | 1260 | 5.86 | 6.17 |
| 10000 | pg | u_empty_tax | visible_docs(inline) | 1260 | 59.73 | 60.71 |
| 10000 | pg | u_empty_tax | **visible_docs+MATERIALIZED** | 1260 | **5.52** | **5.96** |
| 50000 | pg | u_narrow | json_each | 17800 | 54.24 | 54.96 |
| 50000 | pg | u_narrow | visible_docs(inline) | 17800 | 384.65 | 390.39 |
| 50000 | pg | u_narrow | **visible_docs+MATERIALIZED** | 17800 | **44.98** | **45.94** |
| 50000 | pg | u_broad | json_each | 50000 | 76.94 | 77.88 |
| 50000 | pg | u_broad | visible_docs(inline) | 50000 | 474.76 | 480.76 |
| 50000 | pg | u_broad | **visible_docs+MATERIALIZED** | 50000 | **55.44** | **56.47** |
| 50000 | pg | u_empty_tax | json_each | 5800 | 21.11 | 22.34 |
| 50000 | pg | u_empty_tax | visible_docs(inline) | 5800 | 22.03 | 23.44 |
| 50000 | pg | u_empty_tax | **visible_docs+MATERIALIZED** | 5800 | **15.94** | **16.62** |

sqlite visible_docs 优势倍数（P50）：**2.3~4.8×**（u_broad 两档 2.3~2.4×、u_narrow 3.2~3.5×、
u_empty_tax 4.1~4.8×）。PG inline 对 json_each 的劣化倍数（P50）：**不稳定**——u_narrow 7.1×、
u_broad 6.2×，但 u_empty_tax 本轮仅 1.04×（R1 同格为 9.0×：326.14/36.30）；病理是否出现
随计划选择在跑间/形态间摇摆，**只有 MATERIALIZED 全部 6 组（2 档 × 3 形态）稳定快于
json_each**（本轮 50K 档 3/3 反超 17~28%，1 万档 3/3 持平~微胜）。

### 2.2 等价性复核（验收 1——性能实验不改变正确性结论）

**12/12 组合（2 档 × 2 后端 × 3 用户）两写法结果集（rid,id,doc_id）多重集逐行等价 ✓**；PG 的
MATERIALIZED 补充变体同样纳入复核（全部 ✓）。TC-ACL-07 语义在 1/5 万实验规模下成立，
未见任何不等价迹象——**等价性结论未因规模改变**（R1/R2 两轮全等）。

### 2.3 计划形态：PG inline 的病理、不稳定与 MATERIALIZED 一词修复

- **sqlite**（EXPLAIN QUERY PLAN，工件内全文）：visible_docs CTE 一次物化（`LIST SUBQUERY` + `REUSE`），
  块侧走 `uq_chunks_docver` 索引——正是设计意图（按文档算一次）。
- **PG inline**（EXPLAIN ANALYZE，200 文档样本）：CTE 被内联成 Semi Join，文档级可见性
  谓词（两层嵌套 NOT EXISTS × 2 维度）**按块重复求值**——与写法意图（按文档算一次）正好相反。
- **PG + `AS MATERIALIZED`**：CTE 强制一次物化，外层对物化集 semi join。
- **EXPLAIN ANALYZE loops 实测（P2-5 脚本化，bench1 `capture_plans` 程序化解析、判定 PASS）**：
  inline 文档级谓词（Anti Join 分支）max **loops=2000（=块数**：按块重复求值）；
  MATERIALIZED CTE 段 Anti Join max **loops=200（=文档数**：按文档一次物化；
  外层 CTE Scan 对物化集按块探查 loops=2000——semi join 本分，与谓词重求值不同）。
- inline 的**计划不稳定**：同一格在跑间翻动（u_empty_tax 50K：R1 326ms / R2 22ms；
  R1 的 10K u_broad 格还出现同跑内 P50/P95 双峰 8.14/89.50——psycopg 自动 prepare 前后
  generic/custom 计划摇摆）——MATERIALIZED 后 6 组全部单峰稳定。
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

依据汇总：①sqlite 全形态 2.3~4.8× 优势（两档六格）；②PG 加 MATERIALIZED 后 6/6 组
不劣于 json_each（50K 档 3/3 反超 17~28%），且消除 inline 的计划不稳定性；③可移植性判据
满分（归一化后逐字同文，json_each 做不到）；④等价性 12/12 复核通过；⑤删 dims_json
消除「文档维度变更时服务层同步刷投影」的一致性维护点（design §4 取舍注）。

### 2.6 删除 dims_json 影响清单（P2-2——M0b-3 工作量预估，拍板前必读）

删列不是"删模板"即可收口，dims_json 当前共有四类消费方（文件:行号为 R2 时点源码）：

| # | 消费方 | 现状（源码锚点） | v1.1 改造 |
|---|---|---|---|
| 1 | 按块 ACL 渲染模板（基础路） | `store/sqlite/acl_render.py` render_select / `store/postgres/acl_render.py` render_select（json_each/jsonb 扫描 + dims_scan 工厂） | 删；基础路改走 visible_docs（已有） |
| 2 | FTS 路与向量路的 ACL 片段 | `build_fts_where_ast`（sqlite acl_render.py:171）、`build_where_ast(vector=True)`（双方言——向量路仅追加 embed_model 谓词）——**visible_docs 目前只有基础路形态，无 FTS/向量变体** | 新增 `render_fts_visible_docs_select`（FTS 虚表/tsvector JOIN 与 visible_docs CTE 组合，双方言各一）与向量路 CTE 变体；TC-ACL-06 三路同构断言与 TC-ACL-07 等价性测试改以 visible_docs 为基线（双后端复核） |
| 3 | search 结果 `dims` 输出契约 | `core/docs/retrieve.py:67`：`dims = json.loads(r.get("dims_json"))`——直接消费 recall_fts 投影列（`render_fts_recall_select` 投影 `c.dims_json`，design §6.1 契约字段） | 二选一（M0b-3 拍板项）：①检索 SQL 按 doc_id LEFT JOIN document_dimensions 聚合（sqlite `json_group_array` / PG `jsonb_agg`，TOP-20 行数级聚合、代价小）；②契约调整（dims 字段退化/移除——影响 MCP 契约与 prototype 页面展示） |
| 4 | 写路径投影 | `backend.insert` chunk 字段 dims_json（sqlite/postgres backend.py `_CHUNK_COLS`）、摄取链生成（core/docs/ingest）、tests 造数双写（tests/helpers.py `seed_doc_dims`：document_dimensions + UPDATE chunks.dims_json 投影） | 写侧删投影（chunk dict 去 dims_json 字段 + `_CHUNK_COLS` 去列）；`documents.pending_dims_json` **保留**（pending 期暂存 → 切换事务落 document_dimensions 的链路不变）；tests 造数与断言去投影 |

另：pgvector 一侧 `chunks.dims_json JSONB` 列与 sqlite `TEXT` 列随 v1.1 迁移去列；
维度变更刷新点（design §4「服务层同步刷投影」）整体删除。

---

## 3. 实验 2（TC-PERF-02）：向量同表 vs chunk_vectors 分表

口径：50,000 块（5,000 文档 × 10 块）、2560 维 float32（512MB 向量载荷/后端）、双后端、
两布局**同库先后度量**（同一份块行与向量）；写路径=生产链形态（同表=块先落库后 UPDATE
回写；分表=INSERT `chunk_vectors`，对称 2000 行/批显式事务 executemany）；查询=固定谓词
（org/version/tombstone + embed_model）隔离布局变量，不叠 ACL 编译产物；**recall 只投影
rid（不含正文读出与向量反序列化传输——距离在库内计算，客户端仅收 top-20 rid）**。

分表侧基表双口径（P2-1）：**宽基表**（`chunks`——Phase A 后仍带 10KB 向量行，R1 口径、
布局代价的上界）与**窄基表**（`chunks_narrow`——去掉 embedding/embed_model 的 CTAS 对照
表，**保留 tsvector 五列**并补 rid 唯一索引 + ANALYZE，近似 v1.1 真实分表布局的 chunks）。

### 3.1 写入相位与 WAL 放大

| 后端 | 布局 | 写入耗时 | 吞吐（行/s） | WAL MB | 备注 |
|---|---|---|---|---|---|
| sqlite | 同表 UPDATE | 2.60 s | 19,214 | 619.8 | 载荷 512MB → WAL 放大 1.21× |
| sqlite | 分表 INSERT | 1.38 s | 36,161 | 621.1 | INSERT 比 UPDATE 快 ~2×（无旧行重写） |
| pg | 同表 UPDATE | 62.09 s | 805 | 609.0 | 客户端文本载荷（~1GB 文本）传输主导 |
| pg | 分表 INSERT | 59.55 s | 840 | 599.7 | 布局差异被传输成本掩盖 |

**结论：WAL 放大是载荷属性（~1.2×），对布局中性**（sqlite 619.8 vs 621.1；pg 609.0 vs 599.7，
±2%）。吞吐为 **benchmark 批量口径**（2000 行/批 executemany 直连 SQL）——生产
`write_embeddings` 为 64/批逐行 UPDATE，绝对吞吐不可外推为生产值；**相对**布局比较两者同
路径对称、成立。PG 客户端文本形态 ~840 行/s 属传输瓶颈（M1 可二进制/COPY 提速，非布局
问题，登记不展开）。库尺寸（pg_total_relation_size 含 toast+索引）：pg chunks 表无向量
26MB → 同表后 679.5MB（含 UPDATE 死元组膨胀）；分表形态 chunk_vectors 627.7MB / chunks
保持 26MB 级。

### 3.2 查询形态：向量路与非向量路（R2 权威数据，n=20；pg 全部串行口径）

**先说 R2 的重要口径发现——PG 并行计划伪差异**：R1 的分表 recall"+11.5%"（84→93ms）
与 R2 初跑窄基表的"+125%"（89→196ms）**都不是布局代价**，而是 PG 并行计划按 heap 页数
阈值翻转：同表 chunks（42MB heap，含 UPDATE 死元组膨胀）走 3-worker 并行扫描（EXPLAIN
ANALYZE 117ms），22MB 的窄表跌出阈值走串行（216ms）——且该阈值随 vacuum 状态漂移
（vacuum 后同表 heap 缩回 ~20MB 也会掉回串行）。**本轮起实验 2 全部 PG 查询会话级禁用
并行统一串行口径**（可复现、布局可比）；生产侧并行收益与翻转向量为 M1 观察项（§5）。

| 后端 | 形态 | P50 ms | P95 ms | 相对同表 |
|---|---|---|---|---|
| sqlite | 向量召回 top-20（同表） | 276.15 | 287.60 | 基线 |
| sqlite | 向量召回 top-20（分表·宽基表=上界口径） | 290.57 | 311.02 | +5.2% |
| sqlite | 向量召回 top-20（分表·窄基表=干净口径） | **251.59** | 264.33 | **-8.9%** |
| sqlite | 元数据扫描（基线：向量全 NULL） | 41.60 | 42.07 | 基线 |
| sqlite | 元数据扫描（同表 10KB 宽行） | **83.74** | 85.67 | **2.01× 拖慢**（三跑稳定 2.0~2.1×） |
| sqlite | 元数据扫描（分表对照 narrow） | 41.19 | 41.81 | 与基线持平（-1%） |
| sqlite | 点查 rid IN ×20（chunks 基线 / 同表宽行 / chunk_vectors） | 0.02 / 0.02 / 0.02 | — | 三表无差异 |
| pg | 向量召回 top-20（同表） | 198.69 | 232.66 | 基线 |
| pg | 向量召回 top-20（分表·宽基表） | 201.28 | 207.81 | +1.3% |
| pg | 向量召回 top-20（分表·窄基表=干净口径） | **197.57** | 200.17 | **-0.6%（等价）** |
| pg | 元数据扫描（基线 NULL） | 27.03 | 27.46 | 基线 |
| pg | 元数据扫描（同表，TOAST 外置） | 21.40 | 23.03 | 基线带内（见注） |
| pg | 元数据扫描（分表对照 narrow） | 28.25 | 29.42 | 基线带内 |
| pg | 点查 rid IN ×20（chunks 基线 / 同表 / chunk_vectors） | 0.15 / 0.15 / 0.19 | — | 无实质差异 |

pg 元数据扫描注：R1 曾报"同表 +21.7% 拖累"（18.0→21.9ms），R2 统一串行口径后三口径
（27.0/21.4/28.3）在噪声带内交叠——**R1 数值未复现**（R1 值含并行/顺序热偏差噪声）；"同表
反而最快"系顺序/热缓存偏差，非"拖累为零"的实证。可下结论的口径：pg 宽行对非向量路的
拖累远小于 sqlite 的 2×、不作为分表依据（TOAST 外置定性不变，方向与 sqlite 的 2× 拖慢
形成对照）。两布局向量召回 top-20 rid 集合一致（同向量同谓词 ✓）。

**读侧结论（修正后）**：分表向量路**零代价**——sqlite 窄基表反超 8.9%（窄行页密度 +
距离计算前先过滤，宽行基表才是上界口径 +5.2%）、pg P50 等价（±2%）且 P95 窄表反优
~14%（200.17 vs 232.66）；不分表的代价明确：
sqlite 非向量路（可见性/BM25 前置过滤这类**每次检索必经**的全行覆盖扫描）被 10KB 宽行
拖慢 **2.01×**（页密度 ~1/2.4 + overflow 链），分表完全救回；pg 无此效应（TOAST 外置）。
本实验元数据扫描为全结果物化形态（实验 1 同款可见性产物）——FTS 索引裁剪后的 top-k
路径受宽行影响更小（§5 口径限制）。

### 3.3 模型迁移蓝绿判据实测（方案一 vs 方案二，50K 块档；含共存期读路径 P2-4）

| 后端 | 相位 | 耗时 | WAL MB | P50/P95 ms | 关键观察 |
|---|---|---|---|---|---|
| sqlite | 方案一：置空（UPDATE … embedding=NULL, embed_model=NULL） | 1.12 s | 207.5 | — | 置空即降级（向量路谓词落空，BM25 单路） |
| sqlite | 方案一：空间回收（VACUUM） | 2.39 s | — | — | 库文件 1252.8→649.7MB（重写整库） |
| pg | 方案一：置空 | 1.61 s | 616.6 | — | 置空 WAL ≈ 一次满写向量集（新元组版本 + FPI） |
| pg | 方案一：空间回收（VACUUM ANALYZE） | 1.56 s | — | — | chunks 679.5→64.9MB ✓（TOAST 尾部空页 truncate 归还 OS） |
| sqlite | 方案二：新标签并存写入（50K 行） | 1.96 s | 621.7 | — | 服务端 INSERT..SELECT（布局代价口径，不含嵌入 API） |
| **sqlite** | **方案二：共存期向量召回（窄基表，新旧各 50K 行、按新标签谓词）** | — | — | **251.6 / 254.0** | **vs 单标签 251.6/264.3：P50 零放大、P95 还略优**——先过滤后距离，旧标签行不触向量载荷 |
| sqlite | 方案二：旧标签延后清理 | 0.27 s | **4.3** | — | DELETE 只记释放页——极廉价 |
| sqlite | 方案二：空间回收 | 2.46 s | — | — | 1266.4→649.9MB |
| pg | 方案二：新标签并存写入 | 1.50 s | 593.7 | — | 覆盖率 old=50000 / new=50000 → 100% |
| **pg** | **方案二：共存期向量召回（窄基表，串行口径）** | — | — | **209.6 / 236.5** | **vs 单标签 197.6/200.2：P50 +6%、P95 +18%**——串行全扫需过双倍行页（10 万行），谓词过滤掉旧标签的距离计算 |
| pg | 方案二：旧标签延后清理 | 0.88 s | 551.9 | — | DELETE 记满量死元组 |
| pg | 方案二：空间回收 | 2.29 s | — | — | **1257.8MB 不归还 OS**：空页在文件前段（旧标签先写）、活行在尾段，plain VACUUM 只 truncate 尾部空页——空间进空闲表由后续写入复用 |

「current_model 原子切」= 配置标签翻转（§5.8 dict_rev 同款模式），零 SQL、瞬时——两方案同点。

迁移全周期 WAL（含新向量落库，各相实测相加）：**方案一 ≈ 置空 + 新写**（sqlite
207.5+621.7≈829MB / pg 616.6+593.7≈1210MB ≈ **单次满写向量集的 2.0×**）；
**方案二 ≈ 新写 + 清理**（sqlite 621.7+4.3≈626MB / pg 593.7+551.9≈1146MB ≈ 单次满写的
1.05~1.93×）——两方案总 WAL 同量级（pg 1210 vs 1146MB），**差异不在 WAL 在降级语义**：
方案一重嵌入窗口内向量路**全程功能降级**（设计已知口径），方案二旧标签持续服务到原子切
瞬间、**功能零降级**；共存窗口读性能 sqlite 零放大、pg P50 +6% / P95 +18%（上表）——
「零降级」全程限定为**功能**零降级，共存窗口 pg 有约一至两成的读放大。

### 3.4 建议二（分表与否）与建议三（蓝绿方案）

**建议二：分表 `chunk_vectors(rid, embed_model, embedding)`，`PRIMARY KEY(rid, embed_model)`**
（v1.1 形态见 §3.5）。依据：①非向量路保护（sqlite 2.01× 拖慢 vs 分表持平；pg 无实质差异）；
②向量路零代价（干净口径 sqlite -8.9%、pg ±2%——并行伪差异消除后的真实布局效应）；
③WAL 布局中性、sqlite 写入分表快 ~2×；④**蓝绿并存物理上要求键含 embed_model**——
`probe_pk_rid_conflict` 双后端实测（P2-5 脚本化）：仅 `PRIMARY KEY(rid)` 的分表在新标签
写入时即 `IntegrityError`（sqlite `UNIQUE constraint failed: cv_pkrid.rid` / PG
`UniqueViolation: duplicate key value violates unique constraint "cv_pkrid_pkey"`）；
⑤空间成本透明（向量集中一张表，chunks 窄表可整体留驻页缓存）。
**边界声明（P3-9）**：以上为**精确扫描（无 ANN）口径**；M1 若上 HNSW，pgvector 2560 维
超过 2000 维索引上限，`vector` 列不能直接建索引，需 `halfvec` 或表达式索引（known-gaps
G-6 / 调研 blog/04 §三/§四）——届时分表与否的结论需在 halfvec 口径下复验。

**建议三：方案二（分表蓝绿）**。依据：①功能零降级（方案一窗口期 BM25 单路是既定设计
取舍，但每次换模型都吃一次；方案二旧标签持续服务到切换瞬间）；②原子切零成本；③清理
窗口自主（低峰），sqlite 清理 WAL 仅 4.3MB；④方案一 pg 侧置空+重写 WAL ≈ 单次满写的
2.0×（§3.3 口径），方案二 ≈1.9× 且换回零降级。代价（拍板时知情）：迁移期向量存储双倍
（50K 档 pg 高水位 628→1258MB），清理后 plain VACUUM 不归还 OS（空页在文件前段、
页内复用消化）；共存窗口 pg 读放大 P50 +6% / P95 +18%（sqlite 零）；若存储预算极紧且
业务可接受降级窗口，方案一仍为可行退路（置空 1.6s、回收 1.6s、pg 空间确实归还）。

### 3.5 v1.1 分表形态建议（P2-3——拍板"分表"后的迁移形态与列影响清单）

| 项 | 建议 | 理由 |
|---|---|---|
| `chunks.embedding` | **删除**（sqlite 迁移重建表去列 / pg `ALTER TABLE ... DROP COLUMN`） | 宽行问题根源（sqlite 2.01× 拖慢的本体）；不删则分表收益只剩一半 |
| `chunks.embed_model` | **保留**，语义收窄为**摄取/重嵌入状态标签**（"批次钉标签→回写→断点续跑"机制：`mark_embedding_batch` 钉标签、`pending_embeddings` 按 `embed_model=:label AND embedding IS NULL` 清点、`write_embeddings` 回写防护——backend.py 两方言同构） | 删除它须另设等价状态列（等于重造同构机制）；保留成本 ~16B/行（窄行无碍）。**向量查询谓词迁出**：检索侧不再看 chunks.embed_model |
| 向量查询谓词 | 迁 `chunk_vectors`：`JOIN chunk_vectors cv ON cv.rid = c.rid AND cv.embed_model = :current`（`render_vec_recall_select` 改 JOIN 形态；`embedding IS NOT NULL` 谓词消失——cv 无行即未嵌入，语义同 TC-EMB-02「非当前标签视同未嵌入」） | 实测同构形态（本实验 sep 口径即此写法，零代价） |
| 回写路径 | `write_embeddings` 由 UPDATE chunks 改 INSERT cv（防护语义平移：rid 在批 + tombstone=0 + cv 无行 + chunks.embed_model=:label 钉标签校验） | sqlite 写入快 ~2×（实测）；PG 侧同 payload |
| 蓝绿 runbook | 覆盖率查询按 cv 标签（`count(distinct rid) per embed_model`）；重嵌入=新标签 INSERT 并存 → 100% 覆盖 → config 原子切 → 低峰 DELETE 旧标签 + VACUUM | §3.3 实测四相位 + 共存期读路径 |
| 影响清单 | DDL：分表建表 + PK(rid, embed_model) + FK ON DELETE CASCADE + v1.1 迁移（双方言）；store：write_embeddings/pending_embeddings/render_vec_recall_select/delete_by_doc（级联）；worker：reembed 任务类型（§5.3 置空语句改 INSERT/DELETE 两段）；tests：TC-EMB-02/06/07、test_pg_backend 向量断言、ingest_env 链路 | M0b-3/M1 排期依据 |

---

## 4. 实验 3（TC-AUTH-04 附注）：langchain-mcp-adapters 委托 token 客户端

### 4.1 版本耦合发现（先于一切形态问题）

- PyPI 全部 langchain-mcp-adapters 版本（≤0.3.2，2026-10-24）依赖 mcp 1.x 的
  `mcp.shared.context.RequestContext`；本项目 fastmcp 4.1.3 经 `fastmcp-slim==4.1.3`
  **范围钉** `mcp>=2.2,<3`（uv.lock 解析值 2.3.0）——两区间不相交，**同进程共存不可能**
  （真实入口 `langchain_mcp_adapters.client` 在项目 env import 即 `ImportError: cannot
  import name 'RequestContext' from 'mcp.shared.context'`，实测三次；顶层裸
  `import langchain_mcp_adapters` 因懒加载不触发——入口限定如前）。
- 处置：依赖**不进 pyproject**（§7 最小引入——不留「引入即坏」的组合）；客户端实测跑在
  uv 独立钉版 env（`--with langchain-mcp-adapters==0.3.1 --with mcp==1.30.0 --with
  pyjwt==2.15.1`——精确钉版防复跑解析漂移），服务端留项目 env。**这同时是部署侧的真实
  形态**：adapters 属于调用方（agent 运行时）的依赖栈，不随服务端部署（design §7 勘误
  批次补记口径，committer R1 §7.1 已登记）。
- 附带实证：**mcp 1.30.0 客户端 ⇄ fastmcp 4.1.3（mcp 2.3.0）服务端线级兼容**——握手成功，
  协商协议版本 `2025-11-25`，`initialize/list_tools/call_tool` 全通。
- TC-AUTH-04 附注结论回写用例文档时建议带上本条（adapters 版本演进至 mcp 2.x 兼容前，
  客户端集成须独立 env/独立依赖组）。

### 4.2 三种客户端形态与实测数据（真实 HTTP，uvicorn 线程 + FastMCP search + 开发 JWT；
每相位 n=15（持有会话热调用 n=40）、**无显式预热**、P95=ceil 口径——P3-8）

| 形态 | 代码形态 | 实测（P50/P95） |
|---|---|---|
| **A：每用户会话一个 client**（推荐） | `client = MultiServerMCPClient({...headers: {Authorization: Bearer <该用户 token>}})`；`async with client.session("lattice") as s:` 持有会话，`await s.call_tool("search", {...})` 热调用 | 会话建立（enter+initialize）**10.02 / 10.91 ms**；持有会话热调用 **2.20 / 3.16 ms**（n=40） |
| **A'：adapters 默认 langchain tool 路径** | `tools = await client.get_tools()` → `await tool.ainvoke({...})`——adapters 0.3.1 明确「**每次工具调用新建一个 session**」（官方 docstring） | 每调用（handshake+call）**16.27 / 25.01 ms**——热调用 P50 的 **7.4×** |
| **B：共享中继/每请求注入头** | 每次调用以调用方 token 现场构造 `MultiServerMCPClient` + `session()`（headers 是传输层构造参数，会话内固定，无法按请求换） | 每请求（建会话+调用）**16.49 / 35.65 ms** |

规模化足迹（形态 A，10 用户会话并持）：建立 124.2ms（≈12ms/会话，可并行化）；
**FD +10（1/会话）**；内存 ≈278KB/会话（ru_maxrss，macOS 计字节）；10/10 调用成功。
首次 `initialize` 30~42ms、首次 `list_tools` ~126~129ms（含 jieba 懒加载等一次性成本）。

### 4.3 token 过期刷新行为（dev JWT，ttl=2s 现场铸造）

- **认证执行点在工具层而非传输层**（M0a-3 形态：FastMCP http_app 无传输级 auth，
  `_auth_and_org` 在每次 tool call 验 Bearer）——因此**会话不因 token 过期而断**，
  过期后调用返回 `isError=True`（401 语义 ToolError），服务端日志可见 `Error calling tool 'search'`。
- 形态 A：同会话过期调用失败 → **重建会话（新 token）即恢复**（实测 ✓）；headers 构造时
  固定，会话内存活 token 不可替换。
- 形态 B：过期 token 当次调用失败 → **下一请求用新 token 即恢复**（无会话态可污染，实测 ✓）。
- **推断（未实测）**：A' 在过期场景应最鲁棒——每次调用新建会话/新头，不存在陈旧 token
  会话（机制同 B；driver 未对 A' 跑过期用例，标注为推断）。
- 结论：**A'（默认 langchain tool 路径）鲁棒但常态每调用 7.4× 开销**；**A 的正确姿势是
  「401 即弃会话重建」**（重建成本 10ms，可接受）；会话内热调用 2.2ms 的延迟收益是 A 存在
  的全部理由。**推荐形态 A + 401 重建**；连接池化/自定义 transport（headers 从 contextvar
  取）在 adapters 0.3.x 无现成挂钩（headers 是构造参数），不值得为省 10ms 自维护 transport
  分叉——留待 adapters 演进。

### 4.4 服务端观察（顺手记录，M1 硬化候选）

会话关闭时 uvicorn 偶发 `Unexpected ASGI message 'http.response.start' sent, after
response already completed`（客户端断开 GET/SSE 流后服务端仍尝试写）——噪音级、不影响
功能（driver 全部断言通过），登记为 M1 观察项。

---

## 5. 口径限制与不确定项（如实申报）

1. **实验规模上限 5 万块**（v1.5.2 缩档口径）：visible_docs 的文档集计算复杂度随文档数
   线性、json_each 随块数线性——10 万+/百万块外推未验证（M1 TC-PERF 轮补；sqlite-vec
   十万级边界调研提示见 §6）。
2. **PG visible_docs inline 的计划不稳定**在跑间/形态间摇摆（u_empty_tax 50K 两轮 15.5×
   vs 1.04×），病理出现与幅度不可预测；MATERIALIZED 后 6 组全稳。若 M0b-3 不采纳
   MATERIALIZED，该不稳定性风险自担。
3. **P95 样本量**：实验 1/2 全部计时格 n≥20（nearest-rank P95 脱离"=max"区）；实验 3
   形态格 n=15（ceil 口径下 P95=最大值，受单点影响）、热调用 n=40——形态格 P95 仍受单点影响（B 形态 35.65 含
   尖峰），以 P50 为主判据。
4. **PG 并行伪差（本轮新发现）**：实验 2 全部 PG 查询已禁用并行统一口径；生产默认并行度
   下向量召回绝对值更低（3-worker 实测 117 vs 串行 216ms）但随 heap 页数/vacuum 状态
   翻转，M1 需在真实 vacuum 策略下重标定。
5. **热缓存与同库顺序执行偏差**：两写法/两布局共享同一热库顺序测量（先测者冷、后测者
   热），未做冷缓存对照——pg 元数据扫描三口径交叠（27.0/21.4/28.3）部分源于此；
   效应量大的结论（sqlite 2.01×、蓝绿 WAL）远超该噪声带；pg 共存窗口读代价**方向存在
   但幅度在跑间噪声带内波动**（多次观测约 -3%~+52%，含顺序/热缓存影响——§3.3 表内
   209.6/236.5 为其中一次观测），以定性为准、M1 真实 vacuum 策略下复测。
6. **chunks_narrow 为 CTAS 代理**：列集已对齐 v1.1 形态（去 embedding/embed_model、
   保留 tsv 五列）+ rid 唯一索引 + ANALYZE，但无 PK 约束/外键/默认值，页布局与迁移产出
   的真实窄表仍有差异；结论方向经宽基表口径（上界）三角验证。
7. **实验 2 元数据扫描为全结果物化形态**（无 LIMIT 全量可见集）——宽行拖累在该形态最重；
   FTS 索引裁剪后的 top-k 路径拖累更小，未单独度量（M1 检索管线全链再标）；recall 只
   投影 rid，不含正文读出与向量反序列化传输。
8. **ACL 形态覆盖**：narrow/broad/单维空授权（T22）三形态；全空授权、大授权集（数十值）、
   停用取值/退役维度未单独计时（语义已由既有测试覆盖，性能上大授权集主要放大 InValue
   参数量，预期不改变两写法相对结论——推断，未实测）。
9. **PG 客户端写路径 ~840 行/s 为 benchmark 批量口径**（2000 行/批 executemany 文本形态
   直连 SQL）——生产 write_embeddings 为 64/批逐行 UPDATE，绝对吞吐不可外推（§3.1）。
10. **合成向量 ≠ 真实嵌入分布**（单位球均匀 vs 语义聚集）+ 合成 ACL 分布：对 IO/扫描类
    结论无影响，对距离计算分支预测/缓存局部性有微小影响；调研提醒"别信 benchmark、
    用真实语料验证"——本轮 PG 并行伪差异的发现与修正正是复验价值的例证（§6）。
11. **实验 3 为单机 localhost 回环**：会话建立 ~10ms 含 TCP+HTTP+MCP initialize 三往返；
    跨网段部署按 RTT 放大（每会话 ≈3×RTT + 10ms 处理）；无并发压测（SLO 压测已取消，
    顺延 M1）、无 TCP/HTTP/MCP 三层分解计时。
12. **蓝绿「新标签并存写入」用服务端 INSERT..SELECT 度量布局代价**（零真实嵌入 API
    口径）——真实重嵌入周期 = 嵌入 API 吞吐主导（P3-11 接入后另测），不在本实验量程。

## 6. 调研对照（P3-15——research/enterprise-rag/ 结论与本实验互证）

| 调研沉淀（文档锚点） | 本实验对照 | 判定 |
|---|---|---|
| **blog/07 §三/§四**：ACL 必须检索期 SQL 内前置过滤、勿应用层 post-trim | 两写法均为 SQL 内前置过滤；删 dims_json 删的是**文档维度投影**而非 ACL 前置过滤——真相源 `document_dimensions` 保留、授权查询时展开 | **核心吻合**（§2.6 影响清单第 2 条为展开） |
| **blog/03 §4.2/§4.1**：schema 两流派——JSON blob（dify）vs 强类型字段（ragflow） | 现 `chunks.dims_json` 即 JSON blob 投影；删列转 `document_dimensions` 规范化关系过滤 = 从 blob 转向强类型路线 | **吻合且是建议一的方向依据** |
| **blog/03 §4.3/§4.5、dimensions/03 §2**：正文与向量分离（kotaemon）是被低估选项；chunk 正文位置取舍 | 分表 `chunk_vectors` 即"正文留窄表、向量分表"的量化验证：sqlite 窄表向量路 -8.9% + 非向量路 2.01× 救回；pg 零代价（TOAST 下同族） | **吻合**——调研预告的"多一次回表"代价在两后端分别为负/零 |
| **blog/03 §5、blog/10 §3.3**：嵌入模型钉版本、索引是投影、重建是一等操作（quivr useful-early：lexical 先可用） | `PK(rid, embed_model)` 是"模型钉版本"的键形扩展；方案一降级语义 = quivr lexical-first；方案二在其上做到功能零降级 + 共存窗口实测 | **吻合并扩展**（蓝绿键形为新贡献） |
| **blog/04 §三/§四**：pgvector 精确扫描起步；**2560 维 > 2000 维索引上限，HNSW 需 halfvec**；sqlite-vec 十万级边界；别信 benchmark（真实语料验证、合成数据标明） | 本实验全程精确扫描口径（§3.4 已声明 halfvec 边界）；5 万档在边界内；合成数据全部标明；R1 的 pg"+11.5%"经本轮复验修正为并行伪差异——正是"复验"条目的实例 | **边界内运行 + 复验教训实证** |
| **blog/10 §4.1**：deepagents 经 `langchain-mcp-adapters` 接 MCP | 实验 3 直接实测 adapters 三形态，回灌依赖互斥发现（§4.1） | **强回灌**（本段最有价值的调研回流） |

未发现调研已明确警告却被正面违反的坑；MATERIALIZED/CTE 计划病理为调研未覆盖的**新发现**。

## 7. 工件索引

- 造数/计时脚本：`benchmarks/bench_common.py`（共享 harness）、`bench1_acl_dual_write.py`
  （双写法 + 等价性复核 + MATERIALIZED 变体 + EXPLAIN ANALYZE loops 解析判定）、
  `bench2_vector_layout.py`（对称写相位 + 宽/窄双基表口径 + PG 并行禁用 + PK(rid) 冲突
  探针 + 共存期读路径 + 蓝绿四相位）、`bench3_mcp_client.py` + `bench3_client_driver.py`
  （三形态 + 过期刷新，driver 跑 mcp==1.30.0 钉版独立 env）
- 原始数据：`data/bench-results/bench{1,2,3}.json`（含完整 EXPLAIN ANALYZE/EQP 计划文本、
  loops 解析判定、PK 冲突探针输出、全部分位数与蓝绿逐相位尺寸；`data/` gitignore，可复跑再生）
- 门禁回归证据：`scripts/test_gate.sh` GATE PASS（249 passed + 1 deselected ×2 模式，
  pg 臂 45 组参数化全实跑，2026-10-24 R2 复跑）
