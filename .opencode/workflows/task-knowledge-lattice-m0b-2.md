---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m0b-2
target: knowledge-lattice
coderTaskId: ses_e9236e248ffeRQxs9M6quuudSD
testerTaskId: ses_e920a8e4effev2ENq3zW9CV3sI
committerTaskId: ses_e91fc8be7ffetapXWzTrxNf0kK
status: approved
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: a6ffa1cc07a5b2b8fbecd0e235da835ed99e41af
reviewedSha: a6ffa1cc07a5b2b8fbecd0e235da835ed99e41af
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["R1（6 files +1992）：benchmarks/bench_common.py（共享 harness：双后端库就位/确定性造数种子 20261024/合成向量 2560 维/nearest-rank 分位计时）", "R1：benchmarks/bench1_acl_dual_write.py（实验 1：双写法两档双后端 P95+12 组等价性复核+PG MATERIALIZED 变体+可移植性比对+EXPLAIN 证据）", "R1：benchmarks/bench2_vector_layout.py（实验 2：对称写相位 WAL 精确计量+向量路/元数据/点查+蓝绿方案一/二逐相位实测）", "R1：benchmarks/bench3_mcp_client.py（实验 3 编排：真实 FastMCP server+spawn mcp 1.x 独立 env driver）", "R1：benchmarks/bench3_client_driver.py（实验 3 客户端驱动：三形态计时+10 会话并持+过期刷新）", "R1：benchmarks/report-m0b-2.md（实验报告：原始数据+三项建议+口径限制+复跑入口）", "R2（5 files +508/−217）：bench2_vector_layout.py（P2-1 双基表口径宽=上界/窄=干净+窄表 rid 索引+ANALYZE / P2-4 蓝绿共存期读路径 / P2-5 probe_pk_rid_conflict 双后端 / P3-6 chunk_vectors 点查 / P3-7 n≥20 / PG 会话级禁并行口径统一）", "R2：bench1_acl_dual_write.py（P2-5 EXPLAIN ANALYZE loops 程序化解析+PASS/FAIL 判定 / P3-7 五万档 n=20）", "R2：bench3_mcp_client.py（P3-13 钉 mcp==1.30.0/pyjwt==2.15.1 / P3-2 范围钉表述）", "R2：bench3_client_driver.py（P3-8 ceil 统一+样本 15/40+口径申报）", "R2：report-m0b-2.md（P2-2 影响清单 / P2-3 v1.1 形态建议表 / P3-15 调研对照小节 / P3 措辞口径全修 / R2 权威数据表——实验 2 结论大修：分表向量路零代价、pg 元数据拖累撤销、并行伪差异实证）"]
endReason: null
createdAt: 2026-10-24T19:57:49+0800
updatedAt: 2026-10-24T22:36:16+0800
---

# task-knowledge-lattice-m0b-2: M0b-2 五实验——ACL 双写法性能 / 向量同表 vs 分表 / 委托 token 客户端实测 + 实验报告

## 任务原文

（需求 + 验收标准，写全——这是恢复时唯一的上下文来源）

**目标项目**：`knowledge-lattice/`（企业知识层 POC，需求 v0.9 / 设计 v0.9，设计冻结纪律——实现问题走测试用例与 issue，coder 禁改 `docs/` 下需求/设计/用例文档，禁动 `prototype/`）。M0b 三段拆分之第二段（M0b-1 已合入：PR#47，mergeCommit=aa74e7c，develop HEAD=aa74e7c）。

**M0b 拆解总纲（2026-10-24 用户确认）**：①M0b-1 PG 后端 spike（**已完成 done**）；②本段（M0b-2）：实验（**口径修订已落笔 TEST-CASES v1.5.2：TC-PERF-03 SLO 压测取消、TC-PERF-01 档位 1/5 万两档**）；③M0b-3：结论回写 schema v1.1 迁移 + 勘误批次 + P3 遗留批次清偿收口。

**会话要求（用户常设约定）**：本任务 coder / tester / committer 三角色全新会话，不跨检查点复用任何 task_id。

**运行时**：Python **3.12.10**（uv 托管）。测试 pytest；benchmark harness 形态由 coder 定（独立脚本或 pytest marker 排除——**不得拖慢常规门禁**）。依赖新增对照 design §7 最小化（langchain-mcp-adapters 为实验 3 必需——design §8 M0b.3 实测项钦定）。

**环境约定（就绪，与 M0b-1 相同）**：
- PG 容器 `lattice-pg`（PostgreSQL 16.15 + pgvector 0.8.7，端口 5432，POSTGRES_DB=lattice）；DSN：`LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice`
- Docker Desktop 4 CPU / ~3.83GB 内存——实验 2 的 5 万块 × 2560 维合成向量 ≈ 500MB/后端，内存口径已确认够用
- **嵌入 API：本段预计零真实调用**——文档向量全部合成（确定性伪随机 2560 维 float32，按 embed_model 标签写入）；百炼 API 接入（P3-11 env 覆盖 + .env.example）维持 M0b-3 收口。`.env` 内 DASHSCOPE_API_KEY 勿动勿读

**范围**（design §8 M0b.1~M0b.3 + M0b.4 压测已取消；M0b.5 已由 M0b-1 交付；M0b.6 归 M0b-3）：

1. **实验 1（TC-PERF-01）按块 json_each vs 按文档 visible_docs ACL 计算性能**：
   - 同一授权展开函数两种写法（M0a-2 已交付双写法 + M0b-1 PG 渲染器），1 万 / 5 万两档合成块数据，双后端（sqlite/pg）各跑，P95 计时（每档每组预热后多次采样，采样口径 coder 定、报告注明）
   - 计时对象：ACL 过滤后的可见性查询（编译产物 SQL 真实执行——M0b-1 已具备 PG 可见性产物执行能力）
   - **可移植性判据**（D24）：visible_docs 写法纯 JOIN/EXISTS 无 JSON 方言函数、两后端共用渲染逻辑的程度 vs json_each 的方言绑定
   - 公平性口径：PG 侧 prepared statement/连接池因素、SQLite 侧 PRAGMA 状态，报告中注明并尽量对齐
2. **实验 2（TC-PERF-02）向量同表 vs chunk_vectors 分表**：
   - chunks.embedding 同表 vs chunk_vectors(rid, embed_model, embedding) 分表的回表耗时 + WAL 放大（~10KB/块——2560 维 float32），5 万块档，双后端
   - **模型迁移蓝绿判据**（D12/#41，G-8 重嵌入方案）：分表形态下新旧模型并存、覆盖率 100% 原子切 current_model、旧向量延后清理的可行性评估——实验报告给方案一（置空重建、迁移期向量路降级）vs 方案二（分表蓝绿、零降级）的建议
3. **实验 3（TC-AUTH-04 附注）langchain-mcp-adapters 委托 token 客户端实测**：
   - 客户端形态对比：每用户会话一个 client vs 自定义 transport 每请求注入头——可行性 + 代码形态
   - 连接开销量化（建连耗时/连接复用行为）；token 过期刷新行为实测
   - 经真实 FastMCP server（M0a-3 已交付 search 工具）+ 开发 JWT 驱动
4. **实验报告**：落盘 `knowledge-lattice/benchmarks/report-m0b-2.md`（含原始数据表 + 三项建议：**dims_json 去留 / 分表与否 / 蓝绿方案一二**——供 M0b-3 用户拍板后回写 schema v1.1）；造数/计时脚本入 `knowledge-lattice/benchmarks/`（可复跑）
5. **遗留承接（本段相关）**：无硬性承接项；M0b-1 移交的 M0b-2 顺手项不存在（M0b-1 遗留均已指向 M0b-3/M1）

**验收标准**：

| # | 验收项 | 判据 |
|---|---|---|
| 1 | 实验 1 数据齐全 | 2 档 × 2 后端 × 2 写法 P95 数据完整；双写法结果集等价性在实验规模下复核（性能实验不改变正确性结论——TC-ACL-07 语义仍成立）；报告含路线建议 |
| 2 | 实验 2 数据齐全 | 同表 vs 分表回表耗时 + WAL 放大数据（双后端）；蓝绿判据结论 + 方案一/二建议 |
| 3 | 实验 3 结论 | 客户端形态推荐（含代码形态示意）+ 连接开销量化 + token 过期刷新实测行为 |
| 4 | 实验报告落盘 | `benchmarks/report-m0b-2.md` 三项建议明确（dims_json 去留 / 分表与否 / 蓝绿方案），数据可复跑（脚本入仓） |
| 5 | 门禁保持绿 | `scripts/test_gate.sh` 双后端双模式全绿、pg 臂 0 skipped——benchmark 代码不进常规测试收集（marker/目录隔离），存量 249 passed + 1 manual skipped 基线不回归 |
| 6 | 边界合规 | docs/ 零改动（实验报告在 benchmarks/）；TC-AUTH-04 附注结论可回写用例文档（由 supervised-coding 收口落笔） |

**边界（本段不做）**：TC-PERF-03 SLO 压测（**已取消**——TEST-CASES v1.5.2 已落笔）；v1.1 迁移与 dims_json/分表结论落库（M0b-3——本段只出建议）；HNSW/halfvec 索引化实验（M1 TC-PERF）；rerank/RRF/归一（M1）；真实嵌入 API 调用（零调用——百炼接入随 M0b-3 P3-11）；语义层（M2-S）；PG 完整检索管线 recall_fts/ts_rank（M1——实验 1 只测可见性 SQL）；10 万块档（已取消）。

**Git**：分支 `develop_opencode`（开工第一步 `git fetch origin && git merge --no-edit origin/develop` 同步——develop HEAD=aa74e7c 含 M0b-1）；每轮 commit `[task-knowledge-lattice-m0b-2] R<n>`，commit 前同步 origin/develop；不 push。

**相关文档**：knowledge-lattice/docs/design.md（§5.1 ACL 双写法与性能注 / §4 向量 BLOB 与 M0b 分表实验注 / §5.3 换模型重嵌入与蓝绿（§5.8 dict_rev 原子切换参照）/ §6 MCP 契约 / §8 M0b / §10 风险表）、docs/TEST-CASES.md（**v1.5.2**：TC-PERF-01 两档口径 / TC-PERF-02 / TC-PERF-03 取消注记 / TC-AUTH-04 附注 / §六 M0b 行）、docs/known-gaps.md（G-8 嵌入模型治理——方案一二判据挂 M0b 分表实验 / G-6）、M0b-1 检查点（PG 后端能力现状：可见性产物执行、渲染器、backend 种子）、M0a-2 检查点（双写法等价语义）、research/enterprise-rag/（blog/04 向量存储、blog/10 检索配方）。

## 需求确认

- [x] 用户已确认（2026-10-24——需求复述确认；三角色全新会话常设约定适用；嵌入 API 零调用口径、benchmarks/ 落盘、三项建议供 M0b-3 拍板的流程均已确认）
- 历史遗留事项清单：M0b-1 检查点移交批次均指向 M0b-3/M1，本段无硬性承接；TEST-CASES v1.5.2 口径修订已由 supervised-coding 落笔（2026-10-24，TC-PERF-03 取消 + TC-PERF-01 两档）；requirements/design 正文「M0b 压测」字样勘误登记归 M0b-3 勘误批次（正文冻结纪律）；pulsepet 系列 17 检查点经 2026-10-23 用户裁定豁免

## 遗留事项（跨任务移交）

- [ ] 无（本段为 M0b 第二段；实验结论的落库动作移交 M0b-3——见任务原文第 4 点）

## 轮次记录

- R1: coder 完成（2026-10-24，**全新会话**，coderTaskId=ses_e9236e248ffeRQxs9M6quuudSD，commit `43120920f31d3b97c50dc5360147dda2e7d35e31` 于 develop_opencode，6 files 全在 benchmarks/，父提交=aa74e7c 同步后）——三实验+报告全交付：实验 1（双写法 1/5 万×双后端×3 用户形态 P95 + **12 组等价性复核逐行等价** + 可移植性程序化比对 + EXPLAIN/EQP 计划证据）；实验 2（对称写相位 WAL 精确计量 + 向量路/元数据扫描/点查 + 蓝绿方案一/二逐相位实测）；实验 3（真实 FastMCP HTTP 全链 + mcp 1.x 独立 env driver 三形态计时 + 10 会话并持 + token 过期刷新）。**重大发现 6 条**：①langchain-mcp-adapters（≤0.3.2 依赖 mcp 1.x）与 fastmcp 4.1.3（钉 mcp==2.3.0）同进程互斥——依赖未引入、客户端走 uv 独立 env（§7 最小引入合规）；②PG visible_docs CTE 内联计划病理（按块重复求值）+ 双峰摇摆——`AS MATERIALIZED` 一词双修，sqlite ≥3.35 同语法可用；③分表键必须含 embed_model（PK(rid) 在新标签并存即 IntegrityError——蓝绿物理要求，v1.1 必答项）；④PG 蓝绿高水位 VACUUM 不归还 OS（页内复用，需归还时 VACUUM FULL/pg_repack）；⑤认证执行点在工具层——过期会话不断、调用 401，形态 A 刷新=弃会话重建（9.4ms）；⑥等价性 12/12 成立无"停止上报"触发。核心数据：sqlite visible_docs 3~5× 优 / pg MATERIALIZED 后 2 胜 1 平；WAL 布局中性（≈载荷 1.2×）；分表向量路 +6.5~11.5%、但救回元数据扫描（同表 sqlite 2.09× 拖慢）；方案二零降级（清理 sqlite WAL 仅 4.3MB）。**三项建议**：①删 dims_json 选 visible_docs+MATERIALIZED；②分表 chunk_vectors 且 PK(rid, embed_model)；③方案二。自测：门禁 GATE PASS（249 passed+1 deselected 双模式、pg 臂 0 skipped、benchmarks/ 双重隔离不进收集）+ 报告 EXIT=0。supervised-coding 机械核验：HEAD=4312092 在 develop_opencode ✓ commit 格式 ✓ 工作区仅 supervised-coding 收口改动（TEST-CASES v1.5.2 M + m0b-1 检查点 M + m0b-2 检查点 ??——coder 零触碰）✓ origin/develop 已同步 ✓ 未 push ✓。依赖申报：pyproject/uv.lock 零改动（langchain-mcp-adapters 未引入——同进程互斥，实验 3 经独立 env，§7 口径合规申报）
- R1: tester PASS（2026-10-24，**全新会话**，testerTaskId=ses_e920a8e4effev2ENq3zW9CV3sI；testedSha=4312092 前置校验一致；报告原文见"最新验证意见原文"节）——门禁独立复跑 GATE PASS + 双重隔离核实（testpaths=tests + benchmarks/ 无 pytest 形态）；**三实验全部亲跑复现**：实验 1 两档全量（等价性 12/12 亲跑、MATERIALIZED 效应复现且更强 3 胜、EXPLAIN loops 2000 vs 200 亲测、双峰不稳定属性复现）、实验 2 两项逐位复现（WAL 619.8/621.1、pg 高水位 1257.8→1257.8）+ 2.09× 拖慢精确复现 2.06× + IntegrityError 双后端独立复现、实验 3 全链复现（401→恢复、10/10 并持、A' 7.2× 热调用）；**报告自洽性审查**：三项建议全部数据支撑、口径限制申报诚实（七条明示）；边界全过（6 files 全在 benchmarks/、零依赖引入、嵌入 API 零调用、docs/ 零改动）；**零 IMPL_BUG/TEST_BUG/CASE_BUG**；移交 3 条报告措辞精度瑕疵（非阻塞）：①"sqlite 3~5× 优势（两档全部形态）"概括偏乐观（自家 u_broad 数据 2.3~2.4×，应表述 2.3~4.9×）；②"精确钉死 mcp==2.3.0"实为 fastmcp-slim METADATA 范围钉 `mcp>=2.2.0,<3.0.0`（2.3.0 是 lock 解析值）；③"import 即失败"仅在真实入口成立（顶层裸 import 懒加载不炸）——数据真实、方向正确、结论自洽，建议收口时转 coder 微调措辞或 committer 裁定记录在案
- R1: committer NEEDS_CHANGES（2026-10-24，**全新会话**，committerTaskId=ses_e91fc8be7ffetapXWzTrxNf0kK，报告经两次调用交付完整；reviewedSha=4312092 前置校验一致；报告原文见"最新验证意见原文"节）——**P1×0 / P2×5 / P3×15**：P2-1 实验 2 分表向量路用宽 chunks 基表（chunks_narrow 已建未用于 recall——布局对比不公平，+6.5~11.5% 偏保守）／P2-2 "删 dims_json"影响清单不完整（FTS 路向量路渲染变体、retrieve dims 输出契约、ingest 投影——拍板前应见工作量）／P2-3 分表建议未给 v1.1 迁移形态（chunks.embedding 去留、embed_model 处置、谓词迁移）／P2-4 蓝绿"零降级"未测共存期读路径（双倍向量扫描 P95 可能近翻倍——"功能零降级"≠"性能零降级"）／P2-5 两条关键证据未脚本化（IntegrityError 实验、EXPLAIN ANALYZE loops——"实测"不可从交付物审计）；P3×15（措辞精度 5 条含 tester 3 条+"8 组"实为 6 组+"5~6×"漏 u_empty 9×、点查未测 chunk_vectors、n<20 时 P95≈max 未披露、bench3 round vs ceil 口径不一致、精确扫描口径未声明、热缓存顺序偏差缺限制、A' 鲁棒性系推断、方案一写放大表述易误读、bench3 依赖未钉版本、写吞吐外推、调研对照未引用）；**调研借鉴检查（用户特别指示重点章节）**：整体有效吸收（前置过滤核心吻合/正文向量分离吻合且 P2-1 修正后更干净/模型钉版本 PK 扩展合理/adapters 实测为本段最有价值调研回灌/精确扫描处调研边界内），**未发现调研已警告却正面违反的坑**；MATERIALIZED 计划病理为调研未覆盖的新发现；主要不足=借鉴未在报告显式对照（建议 R2 加 5~8 行"调研对照"小节）+ pgvector 2000 维索引/halfvec 边界未写进建议；**Tester 3 条瑕疵裁定：R2 小修**（报告是用户拍板唯一数据依据+3 处可验证事实性偏差+本轮已因 P2 触发 R2 顺带修+另有 2 处 tester 未列的自洽性错误一并修）；**需求边界问题×2（非阻塞文档级，归勘误）**：①design §7 依赖清单未列 langchain-mcp-adapters（coder 独立 env 处置合规且更优，勘误补记"实验客户端依赖归属调用方运行时"）；②design §8/requirements §8 正文"1/5/10 万块/压测"字样与 TEST-CASES v1.5.2 不一致（已登记 M0b-3 勘误批次，非本段缺陷）；**前置问题指出**：检查点"最新验证意见原文"节此前为空（supervised-coding 漏归档 tester 报告全文——已补）
- R1 committer NEEDS_CHANGES → **spec 确认（2026-10-24 用户确认）**：R2 修复计划=P2×5 全修（P2-1 分表 recall 改 chunks_narrow 基表重跑 bench2 更新报告 / P2-2 报告补"删 dims_json 影响清单"（FTS/向量路渲染变体、retrieve dims 契约、ingest 投影）/ P2-3 报告补 v1.1 分表形态建议（embedding 去留、embed_model 处置、谓词迁移）/ P2-4 蓝绿共存期读路径测量（用窄基表报 P50/P95）/ P2-5 IntegrityError 实验与 EXPLAIN ANALYZE loops 脚本化）+ P3×15 与 Tester 3 条全修（committer 裁定 R2 小修——报告文字与脚本小改：措辞精度、样本量披露、round/ceil 统一、调研对照小节、halfvec 边界、mcp 钉版本等）；边界问题 2 条归 M0b-3 勘误批次（无需拍板：①design §7 补"实验客户端依赖归属调用方运行时"注记；②正文"压测/三档"字样勘误——已登记）
- R2: 修复轮启动（fixing→implementing；round=2；reviewedSha 置空；修复范围=P2×5 + P3×15 + Tester 3 条，续接 Coder 会话 ses_e9236e248ffeRQxs9M6quuudSD）

- R2: 修复轮启动（fixing→implementing；round=2；reviewedSha 置空；修复范围=P2×5 + P3×15 + Tester 3 条，续接 Coder 会话 ses_e9236e248ffeRQxs9M6quuudSD）
- R2: coder 完成（2026-10-24，续接会话，commit `a6ffa1cc07a5b2b8fbecd0e235da835ed99e41af` 于 develop_opencode，5 files +508/−217）——P2×5 全修+P3×15 与 Tester 3 条全修逐条响应"已修"。**实验 2 结论大修（数据诚实申报）**：①R1"分表向量路 +6.5~11.5%"证伪为 **PG 并行计划伪差异**（42MB 宽表走 3-worker 117ms vs 22MB 窄表串行 216ms，EXPLAIN 实证；统一会话级禁并行后三口径 198.7/201.3/197.6 ±2%——**分表向量路零代价**，sqlite 窄基表反超 -8.9%，宽基表上界口径保留报两行）；②pg 元数据"+21.7% 拖累"撤销（R1 值含并行/顺序热偏差，tester 复跑亦未复现——正式撤回）；③sqlite 2.01× 元数据拖慢三跑稳定（分表核心依据不变）；④蓝绿共存期读路径实测（P2-4）：sqlite 零放大 251.6/254.0、pg P50 +6%/P95 +19%；⑤方案一写放大修正 2.25×→2.0×（自己发现算错并修正）。**三项建议方向均不变**：建议一依据更强（MATERIALIZED 6/6 不劣）、建议二结论不变依据大修（对分表更有利）、建议三语义限定（功能零降级）。P2-5 两条证据脚本化实证（IntegrityError 双后端 + loops 2000 vs 200 PASS 判定）；P3-15 调研对照小节落笔（6 行对照表含"删维度投影非 ACL 前置过滤"辨析）；P3-7 样本量 n≥20（实验 2 全相位、实验 1 五万档）、实验 3 热调用 n=40。自测：门禁 GATE PASS（249+1 deselected 双模式）+ bench1 重跑等价性 12/12 ✓ EXIT=0 + 实验数据工件再生。supervised-coding 机械核验：HEAD=a6ffa1c 在 develop_opencode ✓ commit 格式 ✓ 5 files diff 与申报一致 ✓ 工作区仅 supervised-coding 收口改动 ✓ origin/develop 已同步 ✓ 未 push ✓

- R2: tester PASS（2026-10-24，续接会话，报告原文见"最新验证意见原文"节 Tester R2 小节；testedSha=a6ffa1c 前置校验一致）——门禁 GATE PASS 双模式零回归+隔离不破；**实验 2 结论大修经独立复跑成立**：三口径复现（sqlite 窄基表 -9.0% 精确复现、pg ±2% 等价量级成立）、**并行伪差异归因亲测自洽**（会话级禁并行统一施加于源码 :512 + bench2.json pg_parallelism:disabled 标记；R1 同表 84ms 系并行扫描受益——归因成立）、元数据 2.03× 三跑稳定、**pg 元数据拖累撤销复现**（同表最快，与 R1 轮未复现观察一致）、蓝绿共存期 sqlite 零放大精确复现；P2×5 逐条勾验全过（P2-5 两条证据亲测输出与报告逐字一致）；P3×15+3 全部落实非纸面响应（⑤摇摆声明被二次实证——u_empty_tax 复跑恰落 R1 侧）；实验 1 回归等价性 12/12 + pg MATERIALIZED 6/6 不劣复现；零弱化（R1 核心逻辑只增不减）；**移交瑕疵④（REPORT 精度，非阻塞）**：pg 共存期读放大"+6%/+19%"在四处作为确定性数字申报且 §5.5 断言"远超噪声带"——tester 两次独立观测（+52%/-3%×3 轮）证明幅度本身在跑间噪声带内波动，定性方向（pg 有读代价风险、sqlite 零放大）成立且方案选择逻辑不翻转，但具体数字应降级为定性申报或标注波动带——移交 committer 裁定

- R2: committer APPROVED（2026-10-24，续接会话——首次调用返回空、续接重试交付完整报告，与 M0a-1 先例同；报告原文见"最新验证意见原文"节 Committer R2 小节；reviewedSha=a6ffa1c=HEAD 核验一致）——P1×0/P2×0；R1 意见处置核对表全过（P2×5 真实修复非纸面、P3×15 与 Tester 3 条基本落实）；**实验 2 结论大修审查**：并行伪差异归因成立但 §0 速览过度概括（sqlite +6.5% 系宽基表上界非并行伪差异——P3-C）、禁并行对实验 1 口径无影响（bench1 未禁并行两轮可比）、pg 拖累撤销部分充分（"同表最快"系顺序/热缓存偏差——P3-D）、三项建议自洽、修正过程可审计非静默改数；**瑕疵④裁定：数字降级定性申报+标注波动带（-3%~+52%），删除"远超噪声带"，不为此单开实验轮**；新发现 P3-A~L 报告文字/口径残余（15.5× 误标/n=15 P95=最大值非第二大/§0 归因概括/pg 元数据表述过强/零代价 P50 口径标注/+18% vs +19% 不一致/远超噪声带改写/loops 判定边界/组合校验等——均不翻转实验结论与方案选择）；需求边界无新增（上轮 2 条维持 M0b-3 勘误）；P3-A~G 报告文字修订授权 supervised-coding 交付收口落笔（若以新 commit 落笔则 doc-only 复核更新 reviewedSha）；调研对照小节已闭环（R1 P3-15）
- **终态校验（2026-10-24 supervised-coding）**：testVerdict=PASS + reviewVerdict=APPROVED + reviewedSha=testedSha=HEAD(a6ffa1c, develop_opencode) ✓ → status=approved；P3-A~G 报告文字残余按 committer 授权由 supervised-coding 交付收口落笔（无需重跑实验）
- **报告修订落笔（2026-10-24 supervised-coding，committer R2 第 5/9 节授权）**：report-m0b-2.md 七处 doc-only 修订——P3-A（15.5× 误标改 9.0×=326.14/36.30）/P3-B（n=15 ceil 口径 P95=最大值）/P3-C（§0 归因区分：pg +11.5% 并行伪差异 vs sqlite +6.5% 宽基表上界）/P3-D（pg 元数据撤销表述过强改"未复现+噪声带交叠+不作为分表依据"）/P3-E（零代价标 P50 口径+P95 窄表反优 14%）/P3-F（+19% 统一 +18%）/P3-G（§0+§5.5 共存期数字降级定性申报+标注 -3%~+52% 波动带、删除"远超噪声带"）——随交付 docs commit 入库；committer 已预声明此路径（doc-only 复核更新 reviewedSha）

## 最新验证意见原文

### Tester R1 报告原文（2026-10-24，testVerdict=PASS）

# task-knowledge-lattice-m0b-2 验证报告（R1 独立复验）

## 1. 前置校验

- `git rev-parse HEAD` = `43120920f31d3b97c50dc5360147dda2e7d35e31` = 申报 testedSha ✓（develop_opencode，父提交 aa74e7c）
- 工作区：仅 supervised-coding 收口改动（TEST-CASES v1.5.2 M、m0b-1 检查点 M、m0b-2 检查点 ??）——与申报一致，未触碰；验证全程 git 只读，收尾 status 与开工一致，零残留（实验产物落 `data/`，已 gitignore）

## 2. 门禁独立复跑 + 双重隔离

| 项 | 结果 | 证据 |
|---|---|---|
| `scripts/test_gate.sh`（DSN 在场） | **GATE PASS** | 双模式各 `249 passed, 1 deselected`，pg 臂 45 组参数化全实跑，**0 skipped** |
| `env -u LATTICE_PG_DSN` | **EXIT=1** | "GATE FAIL: LATTICE_PG_DSN 未设置——拒绝静默绿" ✓ |
| 隔离第一重 | ✓ | `testpaths=["tests"]`，`pytest --collect-only -q` 收集 250 条、benchmarks/ 零收集 |
| 隔离第二重 | ✓ | benchmarks/ 内无 `test_` 前缀函数、无 `import pytest`（grep 核实） |
| 零弱化零删除 | ✓ | `git diff HEAD~1 HEAD --stat` 仅 benchmarks/ 6 files（+1992 行），tests/ 零触碰；skip 数 0，无弱化 |

## 3. 验收表 6 项逐条

| # | 验收项 | 判定 | 证据 |
|---|---|---|---|
| 1 | 实验 1 数据齐全 | **PASS** | 亲跑 EXIT=0：2 档×2 后端×3 形态×(2 写法+PG 补充变体) P50/P95 全出；**等价性 12/12 亲跑复核通过**（内置不等价即 exit 2）；可移植性程序化比对亲测（visible_docs 归一化逐字相同=是 / json_each=否）；EXPLAIN/EQP 计划证据在 bench1.json |
| 2 | 实验 2 数据齐全 | **PASS** | 亲跑 EXIT=0：写相位/WAL/向量路/元数据/点查/蓝绿 6 相位全出，双后端 |
| 3 | 实验 3 结论 | **PASS** | driver 退出码 0；三形态计时+代码形态（driver 源码与报告 §4.2 一致）；10/10 并持成功；过期刷新 401→恢复全链复现 |
| 4 | 报告落盘可复跑 | **PASS** | report-m0b-2.md 三项建议明确；三脚本复跑入口实跑验证；数据工件 data/bench-results/*.json 再生 |
| 5 | 门禁保持绿 | **PASS** | 249+1 双模式全绿、pg 臂 0 skipped、benchmark 不进收集（双重隔离核实） |
| 6 | 边界合规 | **PASS** | docs/prototype 零改动（commit 仅 benchmarks/）；pyproject/uv.lock diff=0 行（零依赖引入属实）；.env 未入库（commit 清单核实）；commit 格式 `[task-knowledge-lattice-m0b-2] R1` ✓ |

## 4. 实验 1/2/3 复跑 vs 报告对照（量级与方向）

**实验 1**（两档全量亲跑，sqlite 数字近乎复刻报告）：

| 关键声明 | 报告 | 复跑 | 判定 |
|---|---|---|---|
| sqlite visible_docs 全面优 | 17.21/4.99 … 90.32/28.17 | 17.98/5.11 … 90.38/27.84 | 同向 ✓（倍数 2.3~4.9×，见 §5 瑕疵①） |
| PG inline 病理（380~487ms） | 379.24/476.86 | 380.39（u_narrow） | 复现 ✓ |
| ⚠ 双峰不稳定 | 10k u_broad 8.14/89.50 | 86.93 高峰；连 u_empty_tax 也翻病理（58.92） | 不稳定属性复现 ✓（报告 §5.2 已申报） |
| MATERIALIZED 效应 | 2 胜 1 平（44.35 vs 58.15 等） | 3 胜（30.88 vs 56.14 / 52.15 vs 66.88 / 15.65 vs 23.19） | 同向更强 ✓ |
| EXPLAIN loops | inline=2000（块）/mat=文档数 | 亲测 ANALYZE：2000 vs 200 | 复现 ✓ |

**实验 2**（5 万档全量亲跑）：

| 关键声明 | 报告 | 复跑 | 判定 |
|---|---|---|---|
| WAL 布局中性 ±3% | sqlite 619.8/621.1、pg 610.8/595.7 | **619.8/621.1 逐位一致**、pg 602.8/602.1（±0.1%） | ✓ |
| sqlite 元数据扫描 2.09× 拖慢 | 39.27→82.07 | 39.69→81.84（**2.06×**） | 精确复现 ✓ |
| pg 同表 TOAST 拖累 +21.7% | 18.00→21.90 | 26.66→20.69（未复现，小效应抖动带内） | 方向性结论不变（pg 拖累 ≪ sqlite 反而更强）|
| 向量路分表 +6.5~11.5% | 268→286 / 84→93 | 273.9→278.9（+1.8%）/ 84.9→90.2（+6.2%） | 同向且更小 ✓；sqlite P95 方差增大未复现（280 vs 281）|
| pg 写吞吐 ~810 行/s | 61.76s/810 | 61.52s/812.7 | ✓ |
| 蓝绿 6 相位 | 置空 207.5/614.2MB 等 | 207.5（逐位）/616.3；清理 4.3（逐位）/551.9（逐位）；覆盖率 100% 断言过 | ✓ |
| pg 高水位不归还 OS | 1257.8MB VACUUM 后不变 | **1257.8 → 1257.8**（逐位）；方案一 679.7→65.1 归还对照 | ✓ |

**实验 3**（亲跑）：A 10.14/2.22ms（报告 9.38/2.19）、A' 15.98（15.56，=7.2× 热调用）、B 15.25（15.03）；10/10 成功、FD+10、≈197KB/会话；401→重建恢复全链复现；`Error calling tool 'search'` 服务端日志可见；ASGI 噪音与 §4.4 申报一致。**driver 无 mock**：真实 HTTP+FastMCP search（首调内容校验 text 块 1）。

## 5. 报告自洽性审查（防凑数）

| 建议 | 数据支撑判定 |
|---|---|
| ①删 dims_json 选 visible_docs+MATERIALIZED | **支撑**：方向全对（sqlite 全形态占优、PG MATERIALIZED 复跑 3 胜、可移植性逐字相同亲测、等价 12/12、dims_json 一致性维护点论据成立）。**瑕疵①**：结论速览与 §2.5 称"sqlite 3~5× 优势（两档全部形态）"，但其主表 u_broad 形态两档均 ~2.3~2.4×——概括偏乐观，应为"2.3~4.9×"（方向/选型不受影响）|
| ②分表 PK(rid, embed_model) | **支撑**：2.09× 拖慢精确复现、IntegrityError 实测在案且我独立复现（sqlite `UNIQUE constraint failed: chunk_vectors.rid` + PG SQLSTATE 23505 + bench2 正向 10 万行并存成功）、WAL 中性 |
| ③方案二 | **支撑**：零降级（覆盖率断言）、原子切零 SQL、清理 4.3MB 逐位、方案一 PG 写放大 ~2×（616+594 vs 594+552）同量级复现、不归还 OS 代价知情申报（1257.8 复现）|
| 口径限制申报 | **诚实**：§5 七条全明示（5 万上限/双峰/全物化口径/文本传输主导/合成向量/localhost/INSERT..SELECT 替代重嵌入）；序列化与 store 层逐字节校准有 assert |

## 6. 边界与重大发现核实

- **6 files 全在 benchmarks/** ✓；docs/prototype/pyproject/uv.lock/.env 零触碰 ✓
- **嵌入 API 零调用** ✓：bench1/2 全合成（PCG64 seed=20261024，缓存 npy）、bench3 `_FakeEmbedder`，无外呼
- **重大发现①依赖互斥**：结论**成立**——uv.lock mcp 唯一版本 2.3.0；adapters 未进 pyproject/uv.lock；独立 env 装配形态核实（`--no-project --with` 两条命令亲跑）。**瑕疵②**：fastmcp-slim 4.1.3 METADATA 实为 `mcp>=2.2.0,<3.0.0`（范围钉），非报告所称"精确钉死 mcp==2.3.0"（2.3.0 是 lock 解析值）；**瑕疵③**："import 即 ImportError"仅在真实入口（`langchain_mcp_adapters.client`/`.tools`）成立——顶层裸 import 因懒加载不炸（我亲测 mcp 2.3.0 下真实入口报 `cannot import name 'RequestContext' from 'mcp.shared.context'`，符号与报告精确吻合；mcp<2 下全链跑通）。互斥实质不受影响
- **发现②MATERIALIZED 一词修复** ✓（loops 亲测）；**③键形** ✓（双后端 IntegrityError 独立复现）；**④VACUUM 不归还** ✓（1257.8 逐位）；**⑤认证执行点在工具层** ✓；**⑥等价 12/12** ✓

**失败分类**：零 IMPL_BUG、零 TEST_BUG、零 CASE_BUG。三个报告文字精度瑕疵（①"3~5× 全形态"与自家 u_broad 数据不符、②"==2.3.0 精确钉"实为范围钉、③"import 即失败"的入口限定）属 REPORT 表述精度问题，数据真实、方向正确、结论自洽，不影响验收判据——建议 supervised-coding 收口时转 coder 微调措辞（或 committer 裁定记录在案）。

## 7. 结论

**testVerdict: PASS**

- 验收表 6/6 PASS；三实验全部亲跑复现，数据与报告量级一致、优劣方向零颠倒，两项逐位复现（WAL 619.8/621.1、pg 高水位 1257.8）
- 遗留移交：3 条报告措辞精度修正建议（非阻塞）
- **testedSha: `43120920f31d3b97c50dc5360147dda2e7d35e31`**

### Committer R1 报告原文（2026-10-24，reviewVerdict=NEEDS_CHANGES；经两次调用合并全文）

# 1. 前置校验

| 项 | 核对结果 |
|---|---|
| HEAD | `43120920f31d3b97c50dc5360147dda2e7d35e31` |
| testedSha | 同 HEAD ✓ |
| reviewedSha | 检查点为 null（本轮首审；R2 后需按新 SHA 重审） |
| 父提交 | `aa74e7c`（M0b-1 合入基线）✓ |
| 分支/工作区 | `develop_opencode`；工作区仅 `.opencode/workflows/task-knowledge-lattice-m0b-1.md`、`knowledge-lattice/docs/TEST-CASES.md` modified 与 `task-knowledge-lattice-m0b-2.md` untracked，均为 supervised-coding 收口改动，不在 diff ✓；未 push（领先 origin/develop_opencode 2 commits） |
| 本轮 diff | `4312092~1..4312092` = 6 个 A 文件、1992 行，全部在 `knowledge-lattice/benchmarks/`；无测试、无 docs、无 pyproject/uv.lock ✓ |
| 测试门禁 | diff 零测试改动，无 `skip/skipif`/删除/断言放宽；`testpaths=["tests"]` + benchmarks 文件名非 `test_*` 双重隔离成立；门禁脚本未改；Tester 独立复跑 PASS（249 passed + 1 deselected ×2 模式、0 skipped）与 `-m "not manual"` 口径一致（manual 为 deselected 而非 skipped） |
| 检查点完整性 | `filesChanged` 与 diff 一致；但 **"最新验证意见原文"节为空**（"（暂无）"），无完整 Tester 报告/证据清单可逐字核对——交付前需 supervised-coding 补全；本轮审查以 round 记录摘要 + 静态审阅为准 |
| 历史意见 | R1 首轮，无上轮 committer 意见；M0b-1 检查点无本段硬性移交项 ✓ |

未独立复跑实验/pytest（仅 git 只读 + 静态审阅，符合本环境约定）。

# 2. 结论

**reviewVerdict: NEEDS_CHANGES**

核心数据与三项建议方向成立，无 P1、无产品代码改动、无测试门禁风险；但报告作为用户拍板 schema v1.1 的依据，存在 **1 项实验 2 公平性测量偏差（P2）**、**4 项报告/可复跑性缺口（P2）** 及若干事实性措辞问题（P3），建议做一轮文档 + benchmark-only 的 R2 小修。

# 3. 问题清单

## P1

无。

## P2

### P2-1｜实验 2 分表向量路用了宽 `chunks` 基线，布局对比不公平
- 文件：`knowledge-lattice/benchmarks/bench2_vector_layout.py:454`（`recall_sql(db, "sep", "chunks")`）、`:194-228`（`recall_sql`）；`report-m0b-2.md:154,160,168-173,203`
- 问题：Phase A 已把 10KB 向量写回 `chunks`，Phase B 只新增 `chunk_vectors`，未清空 `chunks.embedding`；但分表 recall 仍以宽 `chunks` 为基表做扫描（`FROM chunks c JOIN chunk_vectors cv`）。真实分表布局的 `chunks` 应是无 embedding 的窄表（脚本已建 `chunks_narrow` 却未用于 recall）。因此分表向量路计时额外承担了宽行基表扫描，报告 "+6.5~11.5%" 是**偏保守/不干净**的布局对比；sqlite 侧尤其明显（表扫描会读 overflow 页）。
- 建议：分表 recall 改用 `chunks_narrow`（或新增 `recall_sep_narrow` 并同表报两行）；重跑 bench2 后更新 §3.2/§3.4 与结论；若保留现测量，必须在报告中明确"分表侧仍沿用宽 chunks，代价为上界"。

### P2-2｜"删 dims_json 选 visible_docs" 的 M0b-3 影响清单不完整
- 文件：`report-m0b-2.md:118-124`（建议一/残留工作）；参照 `src/knowledge_lattice/core/docs/retrieve.py:67`、`store/sqlite/acl_render.py:197-235`、`store/postgres/acl_render.py:179-197`
- 问题：报告的残留工作只写"渲染器加一词 + 双删 json_each 模板 + schema v1.1 迁移去列"，但 `dims_json` 还被：①FTS 路 `build_fts_where_ast` 与向量路 `build_where_ast(vector=True)` 使用（`render_visible_docs_select` 目前只有基础路，无 FTS/向量变体）；②`retrieve.py` 用它输出 search 结果的 `dims` 字段（design §6.1 契约）。删列不是"删模板"即可收口。
- 建议：在报告增加"删除 dims_json 影响清单"：FTS/向量 ACL 改用 visible_docs CTE（新增渲染变体 + TC-ACL-06/07 双后端复核）；search 的 `dims` 改为从 `document_dimensions` 聚合或按契约调整；ingest/PATCH/tests 去投影。这属于 M0b-3 范围，但用户拍板前应看到工作量。

### P2-3｜"分表"建议未给 v1.1 迁移形态，chunks.embedding/embed_model 去留未定
- 文件：`report-m0b-2.md:198-204`；参照 `store/sqlite/backend.py:235-264`（`write_embeddings`/`pending_embeddings`）、`store/postgres/acl_render.py:179-197`、TEST-CASES `TC-EMB-02`
- 问题：建议二只给 `chunk_vectors(rid, embed_model, embedding)` 与 PK，未说明：`chunks.embedding` 是否删除（不删则宽行问题仍在）；`chunks.embed_model` 是否保留为摄取/重嵌入状态标签（现有 `write_embeddings`/`pending_embeddings`/`mark_embedding_batch` 依赖它）；向量查询谓词如何迁到 `chunk_vectors`；哪些测试/DDL 要改。用户拍板"分表"后，M0b-3 仍需二次决策。
- 建议：增加一段"v1.1 分表形态建议"：明确删 `chunks.embedding`；`chunks.embed_model` 的处置（建议保留为"待嵌/批次标签"或删除并另设状态列，二选一并给理由）；向量谓词迁到 `cv.embed_model`；列影响清单（store/retrieval/reembed/tests/TC-EMB-02）。

### P2-4｜蓝绿"零降级"未测共存期读路径
- 文件：`report-m0b-2.md:190-194,206-212`；`bench2_vector_layout.py:315-407`
- 问题：方案二实测了写入/WAL/空间/覆盖率，但**未测新旧标签并存期间的向量召回**。窗口内 `chunk_vectors` 同时有两份 512MB 向量，按 `embed_model` 谓词的精确扫描要读双倍行（过滤后仍需扫描），P95 可能接近翻倍；报告把方案二概括为"零降级"，实际是"功能零降级"，性能未量化。
- 建议：在 `phase_blue_green` 新标签写入后、旧标签删除前，补一次 `recall_sep`（用 P2-1 的窄基表）并报 P50/P95；若不做，§5 口径限制需明确写"共存窗口向量路扫描量 2×，未实测，M1/蓝绿 runbook 补"。

### P2-5｜两条关键证据未入脚本，报告却写"实测"
- 文件：`bench2_vector_layout.py:70-73`（注释称 PK(rid) 实测 IntegrityError，但全脚本无该实验）；`bench1_acl_dual_write.py:149-186`（`capture_plans` 用 `EXPLAIN (COSTS OFF)`，无 ANALYZE）；`report-m0b-2.md:101`（loops=2000）、`:201-202`（IntegrityError）
- 问题：报告把"PK(rid) 新标签写入即 IntegrityError"和"反连接 loops=2000 vs 200"作为建议二/计划病理的关键证据，但仓库脚本不可复现；Tester 称独立复现为 ad-hoc，无法从交付物审计。验收 #4"数据可复跑"因此不完整。
- 建议：在 bench2 增加一个小函数（临时表 PK(rid) 插两标签、catch IntegrityError，双后端）；在 bench1 `capture_plans` 增加 `EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)` 并解析 loops（或把 ad-hoc 命令与输出写进报告/JSON 工件）。

## P3

1. **`report-m0b-2.md:14,120`**："sqlite 3~5×（两档全部形态）"与自家表不符——P50/P95 比值实际 **2.3~4.8×**（u_broad 2.3~2.4×）。建议改"2.3~4.8×"（Tester ①）。
2. **`report-m0b-2.md:222`**："fastmcp-slim 精确钉死 mcp==2.3.0"不准确——实为 `mcp>=2.2,<3.0` 范围，2.3.0 是 uv 解析值；结论"与 adapters(mcp 1.x) 范围不相交"仍成立。建议改为范围表述（Tester ②）。
3. **`report-m0b-2.md:222-223`**："import 即失败"仅对真实入口 `langchain_mcp_adapters.client` 成立；顶层包可能因懒加载不炸。建议精确到入口（Tester ③）。
4. **`report-m0b-2.md:87`**："8 组补充格全部单峰稳定"与 §2.1 表只有 **6** 组 MATERIALIZED 格不一致；改为 6 或补足 8 组数据。
5. **`report-m0b-2.md:101`**："5~6× 劣化"概括偏窄——u_narrow 6.52×、u_broad 6.29×、u_empty 8.99×（P50 比），建议改"6~9×"或"u_narrow/u_broad 6× 级、u_empty 9×"。
6. **`report-m0b-2.md:158,164`**："点查 rid IN ×20（两布局）"名不副实：代码只测了 `chunks`（同表宽行）与 `chunks_narrow`（NULL 期基线），**未测 `chunk_vectors` 上的分表点查**。建议改标签为"chunks / narrow 对照"，或补 `chunk_vectors` 点查。
7. **`report-m0b-2.md:32,52` + `bench_common.py:373-388`**：5 万档 n=15、实验 2 recall n=8 时 nearest-rank P95 即**最大值**（单一离群敏感）；实验 2 的"P95 方差增大（360 vs 272ms）"由 max-of-8 支撑，证据偏弱。建议至少注明"n<20 时 P95≈max"，或将关键格 n 提到 ≥20。
8. **`bench3_client_driver.py:110-111,129-130,142-143,158-159`**：P95 用 `round(0.95n)-1`，与 `bench_common` 的 `ceil(0.95n)-1` 不一致，且报告 §1 统一声称 ceil。建议统一为 ceil（或统一注明两套口径），并注明实验 3 样本量 12~15、无显式预热。
9. **`report-m0b-2.md:168-173,198-204`**：实验 2 为**精确扫描（无 ANN）**，且 pgvector 2560 维索引化需 halfvec（design G-6 / 调研 blog/04 已提示）。建议在建议二与 §5 明示："本实验为精确扫描口径；M1 若上 HNSW，`vector(2560)` 不能直接建索引，需 halfvec/表达式索引"。
10. **`report-m0b-2.md:267-283`（口径限制）**：缺"热缓存/同库顺序执行"限制——两写法/两布局共享同一热库，先测者冷、后测者热，且未做冷缓存对照；建议补一条。另可补"元数据扫描用 `chunks_narrow` CTAS 代理，索引集与生产窄表不完全一致"。
11. **`report-m0b-2.md:253`**："A' 在过期场景最鲁棒"是推断——driver 只实测了 A/B 的过期行为，未对 A' 跑过期 token。建议标"推断（每次新建会话/新头）"。
12. **`report-m0b-2.md:208`**："方案一在 PG 的写放大约 2×"易误读为相对方案二；实际是相对"单次新写"翻倍，方案一/二总 WAL 同量级（1224 vs 1146MB）。建议按 §3.3 口径改写。
13. **`bench3_mcp_client.py:164-166`**：`--with 'mcp<2'`、`pyjwt>=2.15` 未钉精确版本，复跑可能解析到不同 mcp 1.x；建议钉 `mcp==1.30.0`（与报告一致）或记录 lock。
14. **`report-m0b-2.md:141-142,145`**：PG 绝对写吞吐（~810 行/s）来自 benchmark 的 2000 行/批直接 SQL，生产 `write_embeddings` 为 64/批、逐行 UPDATE；相对布局比较成立，绝对吞吐不应外推为生产值，建议标注。
15. **`report-m0b-2.md:3-6`**：报告"依据"只列 design/TEST-CASES，未引用 research/enterprise-rag 的结论；建议加一小节"调研对照"（见下），使借鉴可追溯（非阻塞）。

# 4. 调研借鉴检查（重点章节）

## 4.1 逐项对照

| 调研沉淀 | 本次 benchmark/结论 | 判定 |
|---|---|---|
| **blog/04 §三/§四**：sqlite-vec 为暴力扫描、边界约十万级向量；pgvector 精确扫描起步；2560 维索引化需 halfvec（≤2000 维索引上限） | 实验 2 用 50K×2560 精确扫描（无 ANN），处于调研边界内；报告 §5.1 声明 10 万+ 未验证 | **有效吸收**；但"无 ANN/halfvec"未写进建议（P3-9） |
| **blog/04 §二 / dimensions/03 §1.3**：pgvector 过滤即 SQL WHERE；多租户用分区/分表；无量化、halfvec 降内存 | 实验 1 两写法都是 SQL 内过滤；无索引化实验（M1）；未做多租户分区（超出本段） | **吸收/部分适用**；分区与 halfvec 属 M1/M3，非本段缺陷 |
| **blog/03 §4.1/4.2**：schema 两流派——JSON blob（dify）vs 强类型字段（ragflow） | 现 `chunks.dims_json` 是 JSON blob 投影；visible_docs 走 `document_dimensions` 规范化表。删 dims_json 实为**从 blob 转向强类型关系过滤** | **有效吸收（方向一致）**；报告未点明，建议补一句 |
| **blog/03 §4.3/4.5、blog/10 §3.5、blog/07 §三/四**：正文与向量分离（kotaemon）是被低估选项；ACL 必须检索期前置过滤、勿应用层 post-trim；ACL 随索引摄入/冗余进索引字段 | 分表 `chunk_vectors` 正是"向量只存引用+载荷、正文留窄表"的投影分离；两 ACL 写法都在 SQL 内前置过滤；删 dims_json 与"ACL 冗余字段"表面相反，但该列是**文档维度投影**而非用户 ACL 字段，真相源 `document_dimensions` 保留、权限仍查询时展开 | **核心吻合**；需在报告解释"删的是维度投影，不是 ACL 前置过滤"，并补下游影响（P2-2） |
| **blog/03 §5 / blog/10 §3.3**：嵌入模型钉版本、索引是投影、重建是一等操作（quivr useful-early） | PK(rid, embed_model) 是蓝绿并存的物理前提；方案一"置空→BM25 单路"对应 useful-early；方案二零降级是改进 | **有效吸收并扩展**；报告未引用，建议补 |
| **blog/10 §4.1**：deepagents 用 `langchain-mcp-adapters` 接 MCP | 实验 3 直接实测 adapters 三形态，并发现与 fastmcp 4.1.3/mcp 2.x 的依赖互斥 | **强吸收**；这是本段最有价值的调研回灌之一 |
| **blog/04 §三/§四 提醒**：别信 benchmark，用真实 query/语料验证；合成数据要标明 | 向量合成、ACL 数据合成均如实申报；但无真实 query 分布对照 | **部分吸收**；ACL/布局微基准对 query 分布不敏感，可接受；建议在 §5 补"合成 ACL 分布"限制 |
| **dimensions/03 §2**：pgvector/平台侧向量布局；chunk 正文位置取舍（dify/anything-llm/ragflow/kotaemon） | 实验 2 同时度量"正文留窄表 + 向量分表"与"同表宽行"，正是该取舍的量化 | **有效吸收**；但测量基表偏宽（P2-1），修正后更能支撑调研结论 |
| **blog/04 中文 BM25 / 混合检索 / RRF** | 本段不测；M1 范围 | **未适用（范围外）** |
| **blog/08 评测 / blog/06 引用** | 本段不测；M3 范围 | **未适用（范围外）** |

## 4.2 对用户五个具体问题的回答

1. **"删 dims_json 选 visible_docs"与调研"ACL 前置过滤/查询时展开"的吻合度**：**核心吻合**（检索期引擎内过滤，非 post-trim；权限变更查询时生效）。与"ACL 冗余进索引字段"看似相反，但 `dims_json` 是文档维度投影、不是用户授权字段；删除后改用规范化的 `document_dimensions`，反而更接近调研 blog/03 §4.2 的"强类型字段"路线。**报告需补这句解释**，否则读者会误以为违背调研结论。
2. **分表结论与调研向量布局经验的对照**：**吻合** blog/03 §4.3 的"正文/向量分离"与 §5 的"索引是投影"；分表 +7~12% 正是调研预告的"多一次回表"代价。但当前测量让分表基表仍是宽 `chunks`（P2-1），代价被高估；改用 `chunks_narrow` 后是更干净的验证。PK(rid, embed_model) 是对"模型钉版本"的合理扩展。
3. **MATERIALIZED/CTE 计划病理是否为调研已见问题**：**调研未覆盖，属本段新发现**。调研没有 PG CTE 内联/计划摇摆的先例，因此不存在"已知坑未避开"；MATERIALIZED 一词修复方向正确。需把 EXPLAIN ANALYZE loops 证据脚本化（P2-5）。
4. **蓝绿/重嵌入方案与调研模型迁移实践的对照**：**吻合并改进**。quivr 的"lexical 先可用、向量后台补齐"正是方案一的降级语义；方案二在此之上做到功能零降级。报告应引用该对照，并补共存期读路径测量（P2-4），否则"零降级"只覆盖写/空间。
5. **是否遗漏调研提示应测的维度**：**有遗漏，但多数属 M1/范围外**：
   - pgvector 2000 维索引/halfvec（调研明确提示，**应写进建议边界**，P3-9）；
   - ANN/HNSW 与精确扫描的差异（M1 TC-PERF，但报告应声明本实验口径）；
   - 冷/热缓存、同库顺序执行偏差（应补限制，P3-10）；
   - 蓝绿共存期读放大（P2-4）；
   - 大授权集/停用取值/全空授权的 ACL 形态（实验只覆盖 narrow/broad/单维空集，建议补一条限制）；
   - 真实 query 分布（调研提醒；本类微基准可接受合成，但应声明）；
   - 并发/写锁（SLO 压测已取消，M1 顺延，报告已提）。
   - sqlite-vec 十万级边界：已由 5 万档 + §5.1 限制覆盖，**未踩坑**。

**总评**：benchmark 设计与结论**整体有效吸收了调研**（前置过滤、正文/向量分离、模型钉版本/重建、嵌入式精确扫描边界、adapters 接入），未发现调研已明确警告却被正面违反的坑；主要不足是"借鉴未在报告中显式对照"以及 pgvector 维度/索引边界未写进建议。建议在 R2 报告加 5~8 行"调研对照"即可闭环。

# 5. 测量方法学审查结论

| 维度 | 结论 |
|---|---|
| Harness 计时口径 | `perf_counter`、nearest-rank、预热（实验 1 为 3 轮）、fetchall 全结果物化、同 SQL 文本、生产连接工厂 PRAGMA/psycopg 纪律——**合格**。但 5 万档 n=15、实验 2 recall n=8 时 P95=max；实验 3 用 round 且无预热——**需披露/统一**（P3-7、P3-8） |
| 实验 1 公平性 | 同一 AclPlan/授权展开、双方言渲染器真实产物、PG `prepare_threshold=5`、SQLite 生产 PRAGMA、单连接无并发——**公平性措施到位**。未做冷缓存对照/顺序偏差分析；PG inline 计划双峰已如实记录并用 MATERIALIZED 复核——**可接受**。P95 样本量是主要统计弱点，但效应量（2.3~4.8×、6~9×）远大于噪声，**不改变结论** |
| 实验 1 造数代表性 | 三用户覆盖 narrow/broad/空授权单维（T22）；文档维度覆盖空/单值/多值；走生产写路径双写一致——**覆盖 ACL 判定分支**。缺全空授权、大授权集、停用取值/退役维度形态；chunk 仅 ~12 token，小于生产 256~512——对 ACL 结构代价影响有限，但应作为限制（P3-10） |
| 实验 2 WAL 对称性 | 两布局同为 2000 行/批显式事务、同载荷、sqlite 关 autocheckpoint + WAL 文件高水位、PG LSN diff——**对称性成立**，Tester 复核属实；WAL 布局中性结论可信 |
| 实验 2 回表/向量路 | **存在基表偏差**：分表 recall 仍走宽 `chunks`，未用 `chunks_narrow`（P2-1）；`chunk_vectors` 点查未测（P3-6）；recall 只返回 rid，不含正文/向量反序列化（报告未声明）；元数据扫描为全结果物化、窄表为 CTAS 代理——需限定。**主决策（分表）仍成立**，且修正后分表代价只会更小 |
| 实验 2 蓝绿 | 写/WAL/空间/覆盖率四相位实测扎实；**共存期读路径未测**（P2-4）；"零降级"应限定为功能零降级 |
| 实验 3 计时 | 真实 HTTP/uvicorn/FastMCP/dev JWT，形态 A/A'/B + 10 会话并持 + 401 行为——**链路真实、结论方向可靠**。局限：localhost 回环、无并发压测、样本 12~15、无组件级拆分（TCP/HTTP/MCP 三层未分解）、P95 定义与主 harness 不一致；报告 §5.6 已申报部分，建议补齐其余 |
| 总体 | **无 P1 级测量错误**；三项建议均有数据支撑；主要修正项是实验 2 分表基表公平性、蓝绿共存读路径、P95 样本量披露、两条未脚本化证据——均为 R2 可闭环的文档/benchmark 级修改，不涉及产品代码 |

# 6. Tester 3 条瑕疵裁定

**裁定：R2 小修（并入 P2 报告修订同轮），不采用"记录在案直接交付"。**

理由：
1. 报告是用户拍板 schema v1.1 的**唯一数据依据**，三处均为可验证的事实性偏差（3~5×、mcp==2.3.0、import 即失败），修改零代码风险；
2. 本轮已因 P2-1~P2-5 需要 R2（报告 + benchmark 脚本），三条措辞可顺带修，不额外增加轮次成本；
3. 另有 **2 处 Tester 未列的自洽性错误**（"8 组"实为 6 组；"5~6×"漏 u_empty 的 ~9×）应一并修正；
4. 若 supervised-coding 最终决定不跑 R2（例如用户要求立即交付），则三条必须作为 M0b-3 勘误批次**首批**登记，且不得在用户拍板材料中保留错误表述——但当前 P2 已触发 R2，故按"R2 小修"执行。

本轮**无 CASE_BUG 裁定请求**（Tester 明确零 CASE_BUG）；以上仅为报告质量问题，不涉及用例预期裁定。

# 7. 需求边界问题

**有（非阻塞、文档级；交 supervised-coding 回 spec/勘误批次，不建议写回 coder 任务）**：

1. **design §7 依赖清单未列 `langchain-mcp-adapters`**，但 design §8 M0b.3 与本任务要求实测该项。coder 的"独立 uv env、不进 pyproject"处置**合规且更优**（避免引入与 fastmcp 4.1.3/mcp 2.x 不相交的依赖），但 §7 与 §8 的口径不一致应在 M0b-3 勘误批次补记："实验用客户端依赖归属调用方运行时，不进服务端依赖清单"。
2. **design §8 / requirements §8 正文仍写"1/5/10 万块"与"SLO 压测"**，与 TEST-CASES v1.5.2（1/5 万两档、TC-PERF-03 取消）及本任务口径不一致。该不一致**已登记**为 M0b-3 勘误批次，本段实现与报告均按 v1.5.2 执行，**非本段实现缺陷**；但交付材料应明确该正文勘误仍未落笔。

除上述已登记/待勘误项外，**未发现实现与 design/TEST-CASES 的验收口径冲突**。

# 8. Tester 报告核对

**前置问题**：检查点"最新验证意见原文"节为空（"（暂无）"），我无法读到 Tester 报告全文，只能核对 round 记录摘要 + diff/代码静态证据。这属于**证据清单不完整**，交付前需 supervised-coding 补全（门禁原始输出、三实验 stdout/JSON 摘要、复跑命令与结果），否则"双 SHA 与 evidence manifest 一致"无法确认。

对摘要的抽查：

| Tester 摘要 | 核对结果 |
|---|---|
| testedSha=4312092、6 files 全在 benchmarks/、零依赖引入、docs/ 零改动 | **属实**（diff/name-status 一致；pyproject/uv.lock 不在 diff） |
| 门禁独立复跑 PASS、双重隔离、pg 臂 0 skipped | **与仓库状态一致**：diff 零测试改动；`testpaths=["tests"]` + 非 `test_*` 文件名成立；gate `-m "not manual"` → 1 deselected/0 skipped 与 249 passed 口径一致 |
| 实验 1 两档全量、等价性 12/12、MATERIALIZED 3 胜、双峰复现 | **结构上可复现**：`run_tier` 12 组合 + fail-fast 等价性；报告表与代码一致；Tester 亲跑声明可信但未附原始输出 |
| 实验 2 WAL 619.8/621.1、PG 高水位 1257.8、2.06× 拖慢 | **报告数字与代码一致**；2.06× 与 2.09× 的偏差属正常复跑波动 |
| 实验 2 IntegrityError 双后端独立复现 | **仓库脚本无此实验**（P2-5）；Tester 的复现为 ad-hoc，无法从交付物审计 |
| 实验 1 EXPLAIN loops 2000 vs 200 亲测 | **`capture_plans` 仅 `EXPLAIN (COSTS OFF)`，无 ANALYZE**（P2-5）；同样属 ad-hoc |
| 实验 3 401→恢复、10/10 并持 | **代码与报告一致**（driver 的过期/重建/10 会话逻辑）；可信 |
| 报告自洽性三项建议均有数据支撑、七条口径限制诚实 | **基本属实**；但 Tester 漏检"8 组/6 组"、"5~6× 漏 u_empty"、"点查两布局"三处自洽性问题 |
| 3 条措辞瑕疵 | **三条均属实**（见 P3-1~P3-3） |
| 零 IMPL_BUG/TEST_BUG/CASE_BUG | **与本次审查一致**：无产品代码/测试改动，benchmark 为新增；无 CASE_BUG |

结论：Tester 的 PASS 结论与主要数据可信；但其"报告自洽性审查"未覆盖上述 3 处小问题，且两条关键证据未脚本化，需在 R2 一并修正。

# 9. reviewedSha

```
reviewedSha: 43120920f31d3b97c50dc5360147dda2e7d35e31
```

本轮审查对象即 HEAD；因 verdict=NEEDS_CHANGES，R2 产生新 commit 后应按检查点纪律将 `reviewedSha` 置空并重审新 SHA。**本轮不执行 `gh pr review`/交付留痕**（未到用户确认交付阶段；且证据清单尚未补全）。

### Tester R2 报告原文（2026-10-24，testVerdict=PASS）

# task-knowledge-lattice-m0b-2 R2 复验报告（回归验证）

## 1. 前置校验

- `git rev-parse HEAD` = `a6ffa1cc07a5b2b8fbecd0e235da835ed99e41af` = 申报 testedSha ✓（develop_opencode，父提交 = R1 `4312092`）
- 工作区：仅 supervised-coding 收口改动（TEST-CASES v1.5.2 M、两检查点 M/?）——与申报一致，未触碰；收尾 status 与开工一致，零残留
- R2 diff = 5 files（bench1/bench2/bench3×2/report，全在 `benchmarks/`，+508/−217）与申报逐文件一致 ✓

## 2. 门禁独立复跑 + 隔离核实

| 项 | 结果 |
|---|---|
| `test_gate.sh` | **GATE PASS**：双模式各 249 passed + 1 deselected，pg 臂 45 组全实跑、0 skipped |
| `env -u LATTICE_PG_DSN` | **EXIT=1** ✓ |
| 隔离 | collect-only 250 条（benchmarks 零收集）+ 无 `test_`/`import pytest` ✓ |
| 零弱化 | diff 审查：R1 核心逻辑（write_phase/recall_sql/等价复核/portability/三形态驱动）全部保留且只增不减；n 15→20、COSTS OFF→ANALYZE、round→ceil 均为增强；R1 数据表被 R2 权威表替换属数据更新非删除 ✓ |

## 3. 实验 2 结论大修复现（核心）

**三口径向量路**（5 万档亲跑 vs R2 权威表）：

| 形态 | R2 权威 P50/P95 | 复跑 | 判定 |
|---|---|---|---|
| sqlite 同表 | 276.15/287.60 | 277.48/279.88 | ✓ |
| sqlite 分表·宽=上界 | 290.57/311.02（+5.2%） | 288.28/340.81（+3.9%） | 同向 ✓ |
| sqlite 分表·窄=干净 | 251.59/264.33（**-8.9%**） | 252.44/254.72（**-9.0%**） | **精确复现** ✓ |
| pg 同表 | 198.69/232.66 | 202.87/206.92 | ✓ |
| pg 分表·宽 | 201.28/207.81（+1.3%） | 218.94/221.38（+8.0%） | pg 抖动带内，同向 |
| pg 分表·窄 | 197.57/200.17（**-0.6% 等价**） | 209.30/219.82（+3.2%） | **±2% 等价量级成立**，"零代价"方向 ✓ |

**并行伪差异实证**：`SET max_parallel_workers_per_gather=0` 会话级统一施加于 PG 全部查询相（源码 :512，写入 run_dialect、先于一切计时）✓；bench2.json 带 `pg_parallelism: disabled` 标记 ✓。R1 "+11.5%" 归因伪差异的判定与我的复跑自洽：统一串行后 pg 三口径收敛（202.9/218.9/209.3），R1 时代同表 84ms 系并行扫描受益——归因成立。

**元数据扫描**：sqlite 基线 41.21 → 同表 83.59 = **2.03×**（申报 2.01× 三跑稳定 ✓）；pg 三口径 32.30/21.09/33.09（**同表最快**——"R1 pg 拖累撤销"复现 ✓，与我 R1 轮未复现拖累的观察一致）。

**蓝绿共存期（P2-4）**：sqlite 共存 252.8/254.8 vs 单标签 252.44/254.72——**零放大精确复现** ✓；覆盖率 old=50000/new=50000 断言过 ✓。**pg 共存期发现幅度复现性问题**（见 §6 瑕疵④）：我两次独立观测 +52%（bench2 全量）/ -3%×3 轮（独立复测：共存 205~208 vs 单标签 212~213）vs 申报 +6%/+19%——功能零降级三次复现、定性方向（pg 有读代价风险）成立，但具体数字跑间波动 -3%~+52%。

## 4. P2×5 逐条勾验

| # | 项 | 判定 | 证据 |
|---|---|---|---|
| P2-1 | 双基表口径 | **✓** | 宽/窄两行都报（§3.2）；narrow 补 rid 唯一索引+ANALYZE+PG 保留 tsv 五列（:91-104，防并行阈值漂移）；复跑复现 |
| P2-2 | 影响清单 | **✓** | §2.6 四类消费方（渲染模板/FTS+向量路变体/dims 契约/写路径投影）+源码锚点+`pending_dims_json` 保留注记 |
| P2-3 | v1.1 形态建议 | **✓** | §3.5 六行表：embedding 删、embed_model 保留为状态标签（含理由）、谓词迁 JOIN、回写路径、runbook、影响清单 |
| P2-4 | 共存期读路径 | **✓（附瑕疵④）** | 脚本真实存在（:420-439）、新旧各 50K、新标签谓词、n=20；sqlite 零放大复现；pg 幅度见瑕疵④ |
| P2-5 | 证据脚本化 | **✓** | `probe_pk_rid_conflict` 双后端（NO-CONFLICT 即报"结论失效"），亲测输出与报告 §3.4 逐字一致（`UNIQUE constraint failed: cv_pkrid.rid` / `UniqueViolation ... cv_pkrid_pkey`）；bench1 loops 程序化解析+**PASS 判定亲跑输出**（2000 vs 200，外层 CTE Scan 2000=semi join 本分辨析） |

## 5. P3×15 + Tester 3 条核对

15/15+3/3 全部落实：①"2.3~4.8×"含形态分解 ✓ ②范围钉 `mcp>=2.2,<3`（lock 解析值 2.3.0）✓ ③入口限定（真实入口 vs 顶层懒加载）✓ ④"6 组" ✓ ⑤inline 劣化改"不稳定+分形态（7.1×/6.2×/1.04×）"——我复跑 u_empty_tax 50K inline 328.64ms 恰落 R1 侧（326），**摇摆声明被二次实证** ✓ ⑥点查三表（含 chunk_vectors）✓ ⑦n≥20 全覆盖+披露 ✓ ⑧ceil 统一+无预热申报 ✓ ⑨精确扫描+halfvec 边界 ✓ ⑩热缓存/CTAS 代理限制 ✓ ⑪A' 标"推断（未实测）" ✓ ⑫方案一 2.0×（自纠 2.25→2.0，核对 1210/593.7=2.04 自洽）✓ ⑬钉 `mcp==1.30.0`/`pyjwt==2.15.1`（复跑生效）✓ ⑭吞吐口径不可外推 ✓ ⑮调研对照小节（6 行，与 committer §4 结论方向一致：删投影非删前置过滤辨析在案）✓；Tester 3 条=P3-1/2/3 ✓。

## 6. 实验 1 回归 + 报告权威性

- **bench1 回归**：EXIT=0、**等价性 12/12**、五万档 n=20 全格与权威表 ±4% 内（sqlite 12 格近乎复刻；pg MATERIALIZED **6/6 不劣复现**——45.18 vs 61.49 反超 27%、78.19 vs 77.05 持平、30.30 vs 31.23 反超 3%）；loops PASS 判定脚本输出与报告 §2.3 逐字一致
- **实验 3 回归**：EXIT=0、A 10.33/2.23ms、A' 17.25（7.7×）、B 16.45、10/10 并持、401→恢复、钉版生效
- **三项建议自洽**：①"零代价"有数据（-8.9%/-0.6%，复现）✓ ②分表+键形（IntegrityError 双后端脚本化实证）✓ ③方案二"**功能**零降级"限定处处一致（§0/§3.3/§3.4/§5）✓
- **瑕疵④（本轮唯一新发现，REPORT 精度）**：pg 共存期读放大"P50 +6%/P95 +19%"在 §0/§3.3/§3.4/§5.5 四处作为确定性数字申报，且 §5.5 断言其"远超噪声带"——我的两次独立观测（+52% 全量跑、-3%×3 轮独立复测）证明该幅度本身就在跑间噪声带内波动（-3%~+52%）。定性方向（pg 共存窗口存在读代价风险、sqlite 零放大）成立且方案选择逻辑不翻转（即使 +52% 也不改变方案二推荐——方案一是全程功能降级），但具体数字应降级为定性申报或标注波动带。移交 committer 裁定

## 7. 边界复查

pyproject/uv.lock/docs/prototype diff=0 行 ✓；.env 未入库 ✓；commit 格式 `[task-knowledge-lattice-m0b-2] R2: ...` ✓；benchmarks/ 共 6 文件（5 改 + bench_common 未动）✓；嵌入 API 零调用维持 ✓。

## 8. 结论

**testVerdict: PASS**

- 门禁 249+1 双模式全绿零回归；P2×5/P3×15+3 全部真实落实（非纸面响应）；实验 2 结论大修的数据基础（三口径/并行伪差异/拖累撤销/共存期）经独立复跑与针对性复测成立，sqlite 侧四项精确复现；实验 1/3 回归无损，零弱化
- 零 IMPL_BUG、零 TEST_BUG、零 CASE_BUG；移交 1 条 REPORT 精度瑕疵（④pg 共存期数字复现性，非阻塞、不改方案方向）
- **testedSha: `a6ffa1cc07a5b2b8fbecd0e235da835ed99e41af`**
