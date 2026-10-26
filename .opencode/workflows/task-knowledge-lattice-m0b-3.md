---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m0b-3
target: knowledge-lattice
coderTaskId: ses_e91982b7bffenn2qJjTzLDPRMo
testerTaskId: ses_e8fd0f9fdffe9Z6c4ZCzGwyrZN
committerTaskId: ses_e8fbc753cffeq73PW6A2eZ2So0
status: done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: f35044ad6bbb9ed4ba12d96d26d0a45990f5b461
reviewedSha: f35044ad6bbb9ed4ba12d96d26d0a45990f5b461
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["R1（43 files +1617/−737）：store/sqlite+migrations 与 store/postgres+migrations 各新增 0002_schema_v1_1.sql（删 dims_json/embedding+chunk_vectors PK(rid,embed_model)+FK CASCADE+存量 INSERT..SELECT 搬运+谓词索引重建）", "R1：store/acl_ast.py 重写（删 json_each 系 builder/CTE 三构造+build_vec_parts 谓词迁 cv/v.status 残留删除/过滤下推/fullmatch/不变式 docstring）", "R1：store/sqlite/acl_render.py 与 store/postgres/acl_render.py 重写（visible_docs AS MATERIALIZED 唯一路径、render_fts_recall_select 改 CTE、render_vec_recall_select JOIN chunk_vectors、投影去 dims_json）", "R1：store/sqlite/backend.py 与 store/postgres/backend.py（insert 去投影/embeddings 三路迁 chunk_vectors/recall_fts 附 _attach_dims 聚合回填）", "R1：store/backend.py 协议 docstring v1.1 / sqlite migrate.py finally 恢复告警 / postgres migrate.py DuplicateTable 恢复分支（P3-6）/ connection.py+vec.py 未使用清理（P3-11）/ sqlite __init__ docstring", "R1：core/docs/retrieve.py dims 聚合回填 / core/docs/ingest.py 去投影", "R1：tests/（26 files：新增 test_v11_schema.py 21 用例 + dbwrap 方言分派面更新 + helpers 去投影 + acl_01~07/emb_02/matrix/r2_review_fixes 迁 CTE + scaf_03 版本基线 2 + pg_scaff/pg_backend 可移植性/自清理 fixture + fts_03/scaf_04 切向量等价 + emb_01/ing_07/r2_committer_fixes 列引用迁移）", "R1：RUNBOOK.md 新增（蓝绿 runbook+分区回溯）+ .env.example 新增 + scripts/test_gate.sh（no-summary||true + PG 专用计数）+ benchmarks/report P3-F + bench1/bench2 退役守卫+P3-H/I + bench_common 死方法移除", "R2（14 files +163/−80）：store/postgres/migrate.py（P2-1 双捕获 DuplicateTable+UniqueViolation+复核迁 to_regclass〔P3-3 顺手〕+docstring）", "R2：tests/test_pg_scaff.py（P2-1 竞态测试改名参数化 23505/42P07 双分支 / P3-1 public_audit_guard 三面真清理 / P3-2 DSN 测试库限定 / P3-7 docstring×2）", "R2：tests/test_v11_schema.py（P2-2 下推 AST 结构断言 / P3-5 孤立行断言 / P3-9 注释校准 / P3-10 卫生）", "R2：store/postgres/connection.py（P3-8 SET standard_conforming_strings=on）/ 双方言 0002 注释（P3-4/P3-5）/ RUNBOOK.md（P2-1 注记+P3-6 闭合 SQL）/ postgres __init__+store backend.py+acl_ast.py+sqlite acl_render.py+test_r2_review_fixes+bench2+test_gate.sh（P3-7/P3-10）"]
endReason: null
createdAt: 2026-10-24T22:51:45+0800
updatedAt: 2026-10-25T08:45:18+0800
---

# task-knowledge-lattice-m0b-3: M0b-3 收官——三项拍板落库 schema v1.1 迁移 + M0a/M0b 遗留清偿 + 勘误批次收口

## 任务原文

（需求 + 验收标准，写全——这是恢复时唯一的上下文来源）

**目标项目**：`knowledge-lattice/`（企业知识层 POC，需求 v0.9 / 设计 v0.9，设计冻结纪律——实现问题走测试用例与 issue，coder 禁改 `docs/` 下需求/设计/用例文档，禁动 `prototype/`；**文档决策回写由 supervised-coding 收口落笔**）。M0b 三段拆分之收官段（M0b-1 done PR#47、M0b-2 done PR#48，develop HEAD=6f08334）。

**M0b 拆解总纲**：①M0b-1 PG 后端 spike（done）；②M0b-2 三实验+报告（done）；③本段（M0b-3）：实验结论落库（schema v1.1 迁移）+ 勘误批次 + 遗留批次清偿收口。**M0b-3 完成即 M0b 里程碑达成**（验收对照：TC-E2E-05 + TC-SCAF-03 v1.1 复跑 + 实验 1/2/3 交付完毕）。

**会话要求（用户常设约定）**：本任务三角色全新会话，不跨检查点复用任何 task_id。

**三项设计拍板（2026-10-24 用户确认"按建议执行"——M0b-2 实验报告 §0）**：
1. **删 dims_json**：选定 visible_docs（按文档）路线；PG 渲染器 CTE 加 `MATERIALIZED`（sqlite ≥3.35 同语法可用）；json_each 渲染模板删除
2. **分表**：`chunk_vectors(rid, embed_model, embedding)` PK(rid, embed_model)；删 chunks.embedding；保留 chunks.embed_model 为摄取状态标签（v1.1 形态详见报告 §3.5：谓词迁 cv JOIN、回写路径、蓝绿 runbook）
3. **重嵌入方案二（分表蓝绿，功能零降级）**：新旧模型并存、覆盖率 100% 原子切 current_model、旧标签延后清理；完整重嵌入流程/管理面入口归 M2，本段落 schema 形态与 runbook 登记

**运行时**：Python 3.12.10（uv）。测试 pytest；门禁 `scripts/test_gate.sh`（基线 249 passed + 1 manual deselected，pg 臂 0 skipped）。PG 容器 lattice-pg（16.15 + pgvector 0.8.7）；DSN `LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice`。嵌入 API：本段零真实调用（延续 M0b-2 口径；`.env` 勿动）。

**范围**：

1. **schema v1.1 迁移**（`store/<dialect>/migrations/docs/0002_schema_v1_1.sql` 双方言 + 迁移框架适配）：
   - 删 `chunks.dims_json`、删 `chunks.embedding`（存量向量搬运：INSERT..SELECT 入 chunk_vectors 后删列——空库/有库两形态都跑通）
   - 建 `chunk_vectors(rid, embed_model, embedding)` PK(rid, embed_model)（sqlite：embedding BLOB + sqlite-vec 距离；pg：vector 列 + `<=>` 精确扫描——沿用 M0b-1 形态）；rid 外键 chunks(rid) ON DELETE CASCADE（块删/版本切换清理联动）
   - `chunks.embed_model` 保留为摄取状态标签（待嵌/批次标记——write_embeddings/pending_embeddings/mark_embedding_batch 路径迁到新表）
   - **蓝绿就绪**：同 rid 多标签并存物理可行（PK 含 embed_model）；重嵌入 runbook 引用报告 §3.5 登记（完整流程 M2）
2. **渲染器收敛（拍板 1 落地）**：
   - 删 json_each 渲染模板（sqlite）；visible_docs 选定为唯一路径——PG 渲染器 CTE 加 `MATERIALIZED`（sqlite 同语法统一加注）
   - **FTS 路与向量路的 ACL 变体改用 visible_docs CTE**（现 `render_fts_recall_select`/向量路谓词基于 dims_json 的 json_each——改为 visible_docs CTE 形态；TC-ACL-06 三路共用同一 Plan 断言双后端复核）
   - 向量路谓词迁 `chunk_vectors.embed_model` JOIN（TC-EMB-02 谓词节点语义保持——Plan 层不动、渲染层迁移）
3. **dims 输出契约调整**：`retrieve.py` search 结果 `dims` 字段改从 `document_dimensions` 聚合（或按 §6.1 契约调整——两种都符合报告 §2.6，coder 择一并注明）；ingest/PATCH 去投影（`pending_dims_json` 保留——D22 版本在用制机制，非本次删除对象）
4. **M0a CTE 顺手项清偿**（visible_docs 选定后成为唯一路径，一并处理——M0a-2 移交）：①CTE 内层 `v.status='active'` 残留处置（口径+测试）；②竞态回归入仓（编译后退役同一 Plan 等价）；③CTE 恶意 key 断言（sqlite 侧；PG 侧 R2 已有）；④白名单 `re.match`→`fullmatch`；⑤标识符路径不变式 docstring；⑥CTE 过滤下推（dataset_ids/doc_ids 下推进 CTE——性能相关，实验已选定 CTE）
5. **M0b-1/M0b-2 移交批次清偿**：P3-4 jsonb 标量守卫（`jsonb_typeof='array'` 或注记）；P3-5 sqlite dot-key 维度 key 校验；P3-6 schema_migrations 锁外竞态（移入锁内或 duplicate_key 重试）；P3-11 未使用项清理 + `.env.example` 模板；R2-P3-1 ALTER DATABASE 测试可移植性；R2-P3-2 门禁 no-summary `|| true`；R2-P3-4 public audit 对象清理 fixture；R2-P3-7 门禁 PG_COLLECTED 范围（PG 专用测试计数）；R2-P3-8 历史审计分区 TRUNCATE 回溯登记（deploy runbook 注记）；P3-F 报告 +19/+18 统一；P3-H/I bench 可维护性；migrate 成功路径恢复失败告警（M0a-2 移交）；`_Renderer` 拼接文档化（M0a-2 移交）
6. **验收复跑（TC-E2E-05 + TC-SCAF-03）**：v1.1 迁移跑通（双后端）+ `foreign_key_check`/约束校验空 + **M0a 可达矩阵子集复跑绿**（T1~T5/T20/T22 + TC-SCAF/TC-ACL/TC-FTS/TC-EMB-02 + TC-ING/TC-E2E/TC-AUTH 全量——v1.1 后全量测试套件零回归，249 基线+新增）

**验收标准**：

| # | 验收项 | 判据 |
|---|---|---|
| 1 | v1.1 迁移双后端跑通 | 0002 迁移 sqlite+pg 均跑通；`foreign_key_check`/约束校验空；存量向量搬运正确（有库形态向量迁移后 chunk_vectors 行数=原 embedding 非空行数）；幂等重放无副作用；版本只前进 |
| 2 | M0a 可达矩阵子集复跑绿 | 全量测试套件（含参数化双臂）双模式绿、pg 臂 0 skipped；TC-ACL-06 三路共用 Plan 双后端复核；TC-EMB-02 谓词迁移后 Plan 层语义不变 |
| 3 | 拍板 1 落地完整 | dims_json 零残留（DDL/渲染器/写路径/检索输出）；json_each 模板删除；visible_docs+MATERIALIZED 唯一路径；dims 契约调整注明口径 |
| 4 | 拍板 2 落地完整 | chunk_vectors 双后端就位 PK(rid, embed_model)；chunks.embedding 删除；谓词/回写路径迁移；同 rid 多标签并存可插（蓝绿形态测试） |
| 5 | 蓝绿就绪 | 重嵌入 runbook 登记（引用报告 §3.5）；PK(rid) 冲突探针仍 PASS（probe 保留） |
| 6 | 遗留批次清偿 | 上列第 4/5 点全部条目完成或明确去向登记；门禁脚本增强后双场景仍实证 |
| 7 | docs 零违规 | coder 禁改 docs/——设计决策回写（design §4/§5.1/§5.2/§5.3/§7/§8、requirements §8/D12、known-gaps G-6/G-8、TEST-CASES TC-ACL-07 口径/TC-EMB 谓词/版本段 v1.6/TC-FTS-01 修订/DDL 勘误）由 supervised-coding 收口落笔 |

**边界（本段不做）**：重嵌入完整流程与管理面入口（M2——本段仅 schema 形态+runbook 登记）；FTS top-k 全链性能标定与 HNSW/halfvec 索引化（M1 TC-PERF）；真实嵌入 API（M0b-3 零调用）；语义层 sem_*（M2-S1）；M1 批次遗留（trigram 判据/T6 完整切换链/grants 写路径校验等——维持 M1）；pg 共存窗口读代价复测（M1 真实 vacuum 策略下）。

**Git**：分支 `develop_opencode`（开工第一步 `git fetch origin && git merge --no-edit origin/develop` 同步——develop HEAD=6f08334 含 M0b-2）；每轮 commit `[task-knowledge-lattice-m0b-3] R<n>`，commit 前同步 origin/develop；不 push。

**相关文档**：knowledge-lattice/benchmarks/report-m0b-2.md（**三项建议权威依据**——§0 结论速览 / §2.6 删 dims_json 影响清单 / §3.5 v1.1 分表形态建议表 / §3.3 蓝绿实测 / §6 调研对照）、docs/design.md（§4 DDL/§5.1 双写法/§5.2 检索管线/§5.3 重嵌入/§7/§8）、docs/TEST-CASES.md（TC-E2E-05/TC-SCAF-03/TC-ACL-06/TC-EMB-02/§六 M0b 行）、docs/known-gaps.md（G-6/G-8）、M0b-1/M0b-2 检查点（遗留移交清单——本段第 5 点的权威来源）、M0a-1/2/3 检查点（M0a 移交 M0b 批次清单）。

## 需求确认

- [x] 用户已确认（2026-10-24——需求复述确认 + 三项设计拍板"按建议执行"；三角色全新会话常设约定适用；文档决策回写归 supervised-coding 收口落笔）
- 历史遗留事项清单：M0b-1/M0b-2 移交批次已并入（见范围第 5 点）；M0a-2 的 M0b 批次（CTE 顺手项 6 项）已并入（范围第 4 点）；M0a-1 DDL 勘误登记与 TC-FTS-01 口径回写由 supervised-coding 收口落笔；pulsepet 系列 17 检查点经 2026-10-23 用户裁定豁免

## 遗留事项（跨任务移交）

- [ ] 无（本段为 M0b 收官段；M1 批次遗留维持 M1 去向不变）

## 交付记录（2026-10-25）

- **Committer 交付留痕（2026-10-25，review id PRR_kwDOTsiHgs8AAAABUDcMJQ）**：代码级 APPROVED 成立（f35044a 门禁 271+1 双模式）；**docs 回写核对发现 4 项 P2 缺项暂不放行**——①三处旧 SQL/列名（design §4 版本切换段 embedding=NULL / requirements:88 / TEST-CASES TC-VER-04）；②TC-SCAF-02/03 正文缺 v1.6 声称的补全（版本段超认领）；③design §4 索引 DDL 未更新 + TC-ING-06 索引面与 0002 注释不同步；④"DELETE WAL ≈4MB"缺 sqlite 限定（PG 552MB 满量死元组）；P3：TC-EMB-01/ING-07/E2E-05 正文、report §2.6 注记、design §4 列级注释
- **补正（2026-10-25 supervised-coding，docs commit `61638ed` 4 files +21/−18）**：P2×4 全部补正（design §4 版本切换段改 DELETE chunk_vectors+UPDATE tombstone / requirements:88 / TC-VER-04 / design 索引行新形态）+ TC-SCAF-02 正文补 PG 纪律与 DSN 约定 + TC-SCAF-03 正文补 v1.1 基线与竞态双捕获 + TC-EMB-01/ING-06/E2E-05 正文 + report §2.6 实现注记 + "4MB"sqlite 限定两处；manifest head 更新 61638ed（代码级 f35044a 不变）
- PR：https://github.com/yq3/lab/pull/49（base=develop，head=develop_opencode；commits=37a5f36[R1] + f35044a[R2] + 742011e[docs 回写] + 61638ed[docs 补正]；52 files）
- push：`742011e..61638ed develop_opencode -> develop_opencode`（用户已确认授权，SSH）
- 状态：代码级 approved + docs 补正已推——待 Committer doc-only 复核放行后请用户确认合入
- **doc-only 复核放行（2026-10-25，review id PRR_kwDOTsiHgs8AAAABUDdKuw）**：4×P2 补正逐项核对 ✓（三处旧 SQL 闭环 / TC-SCAF-02/03 正文落实且与 migrate.py 逐字一致 / 索引行与 0002 注释一致 / 4MB sqlite 限定）+ P3 顺手三项落笔；无新增 material 走样；PR head=61638ed、MERGEABLE/CLEAN、manifest head=61638ed 双 SHA 自洽——**最终放行，可交用户合入**；4 条记录级 P3 不阻塞（TC-SCAF-02 standard_conforming_strings 断言行/TC-ING-07 正文/PR body commit 列表/design §4 列注释措辞——合入后文档维护顺手项，登记 M1 顺手批次）
- **收尾补丁（2026-10-25，用户审计驱动）**：用户三问审计发现两处遗漏——①requirements.md 漏升版本号（正文已改 v1.1 口径但版本段停 v0.9，违反与 design 版本统一惯例）；②TC-SCAF-02 v1.6 声称的 standard_conforming_strings 断言在测试代码缺行（committer R2 P3 第 1 条）。补丁 commit `10d8d72`（2 files +11/−3）：requirements 版本段 v0.9.1 联动升版 + line 4 演进链 + test_pg_scaff 补断言（并入既有工厂测试函数）；门禁 271+1 双模式保持绿、manifest head 同步；committer 快速确认（review id PRR_kwDOTsiHgs8AAAABUDfE2A）——**P3 第 1 条闭环 + requirements 版本补齐 + 最终放行重申**；另 3 条记录级 P3 不阻塞（manifest docsCommitNote 措辞/PR body commit 列表/design-TEST-CASES 交叉引用版本刷新——合入后文档维护顺手项）
- **最终状态：committer 放行（2026-10-25），待用户合入**——合入即 M0b 里程碑达成
- **合入完成（2026-10-25 08:44 用户确认）**：PR #49 state=MERGED，mergeCommit=`1d37713fae50e8359496d3442b1fc43dcaa80b2e`；origin/develop 前进 `6f08334..1d37713`（merge commit 保留 R1+R2+docs+补正 完整历史）；develop_opencode 远端分支按 D30 约定保留——**M0b-3 正式完成（done），M0b 里程碑达成**（M0a+M0b 全部验收原句兑现；下一步 M1：完整检索配方+版本在用制全链+权限全链，新检查点新周期）

## 轮次记录

- R1: coder 完成（2026-10-24，**全新会话**，coderTaskId=ses_e91982b7bffenn2qJjTzLDPRMo，commit `37a5f363802b61c8a6c944994df08b9cc12f8a1d` 于 develop_opencode，43 files +1617/−737，父提交=6f08334 同步后）——六块全交付：①schema v1.1 迁移 0002 双方言（删 dims_json/embedding+存量 INSERT..SELECT 搬运+chunk_vectors PK(rid,embed_model)+FK CASCADE+谓词索引重建 (doc_id,embed_model) WHERE tombstone=0）；②渲染器收敛（json_each/jsonb 模板全删、visible_docs AS MATERIALIZED 唯一路径、FTS 路 ACL 变体改 CTE、向量谓词迁 cv JOIN——Plan 层不动）；③dims 契约择型①聚合（recall_fts 后 _attach_dims 按 document_dimensions 聚合回填，§6.1 契约字段保留）；④M0a CTE 顺手项 6/6；⑤M0b 批次 14/14（P3-6 DuplicateTable 恢复分支、R2-P3-1 current_database+原库默认还原、R2-P3-4 public_audit_guard 自清理、R2-P3-7 PG 专用计数 86=54+32、.env.example 入库、RUNBOOK.md 登记、P3-F 报告唯一修订、bench1/bench2 v1.0 退役守卫——防 CTE-vs-CTE 误导数据）；⑥额外申报：test_v11_schema.py 21 用例（存量搬运/空库/幂等/只前进/蓝绿并存/级联/PK 探针/竞态回归×2/下推/dot-key）。自测：test_v11 21 passed（sqlite 有库搬运载荷逐字节保真+PG <=> 距离保真+PK(rid) 探针双后端）+ 门禁 GATE PASS **271 passed+1 deselected 双模式**（249→271=+22，pg 臂 86 条全实跑 0 skipped）+ TC-ACL-06 6 passed/TC-EMB-02 4 passed/TC-SCAF-03+E2E 15 passed + dims_json 零残留 grep + 无 DSN EXIT=1。supervised-coding 机械核验：HEAD=37a5f36 在 develop_opencode ✓ commit 格式 ✓ docs/prototype 零 diff ✓ 工作区仅 supervised-coding 收口改动（m0b-2 检查点 M + m0b-3 ??）✓ origin/develop 已同步 ✓ 未 push ✓。口径注记 8 条（dims 契约择型①聚合/CTE 快照口径/TC-ACL-07 收敛/索引重建/版本切换清向量 DELETE chunk_vectors/bench 复跑指引 checkout a6ffa1c/0001 保留历史 DDL/pending_dims_json 保留）——供 supervised-coding 文档回写
- R1: tester PASS（2026-10-25，**全新会话**，testerTaskId=ses_e8fd0f9fdffe9Z6c4ZCzGwyrZN；testedSha=37a5f36 前置校验一致；报告原文见"最新验证意见原文"节）——门禁独立复跑 GATE PASS（271+1 deselected 双模式、PG 专用计数 86=54+32、0 skipped）；**构成对账**：+35/−13=净+22 逐条归属（21 新增+1 P3-6 回归；ACL-07 12↔12 改名收敛、r2_review_fixes 1 改名语义保持）；**v1.1 迁移双方言手工库独立探针**（不经项目代码建库：sqlite3 CLI/psql 直喂 0001+0002——搬运恰 2 非空行载荷逐字节保真、列消失 embed_model 保留、fk_check 空、幂等重放 applied=[]、双标签可插、PK(rid) 拒绝、级联清、孤儿 FK 拒、框架重放不回退）；**渲染器收敛+安全纪律**：CTE 逐字一致双方言独立文本级探针、TC-ACL-01~07+EMB-02 61 passed、恶意 key 三连+fullmatch+自控参数名+单趟纪律全在场；**遗留 20/20 逐条勾验全过**；**零弱化零删除**：删除 13 ID 全为拍板 1 选型收敛 sanctioned（json_each 专属断言）、ACL-07 断言面增强（精确期望文档集）、ACL-06 更强（CTE 文本前缀逐字）、EMB-02 新增 3 负向断言；边界全过（43 files、docs 零 diff、.env 未入库、bench 退役守卫 EXIT=0 合理、PG 探针残留自清）。零 IMPL_BUG/TEST_BUG/CASE_BUG

- R1: committer NEEDS_CHANGES（2026-10-25，**全新会话**，committerTaskId=ses_e8fbc753cffeq73PW6A2eZ2So0；reviewedSha=37a5f36 前置校验一致；报告原文见"最新验证意见原文"节 Committer R1 小节）——**P1×0 / P2×2**：P2-1 P3-6 修复未覆盖真实竞态异常类（M0b-1 原文指 pg_type 唯一键冲突 UniqueViolation 23505，实现只捕 DuplicateTable 42P07；测试注入同为 42P07 与生产失败模式不同=走过场；docstring/RUNBOOK 同源失真）／P2-2 CTE 下推测试断言空转（sql.split(")\n SELECT") 分隔符永不命中、cte_part 含外层谓词断言恒真——若实现回归测试仍绿）；**P3×10**：P3-1 public_audit_guard 函数名写成触发器名（lattice_audit_* 未清）/P3-2 public 破坏性清理限测试库说明/P3-3 _schema_migrations_exists 仅查 current_schema/P3-4 索引注释与查询面不符/P3-5 双守卫静默丢弃异常行未声明/P3-6 RUNBOOK 覆盖率 SQL 不闭合/P3-7 四处过时文档残留（postgres __init__/backend docstring/test docstring jsonb 字样）/P3-8 Literal 转义+standard_conforming_strings 防御纵深/P3-9 sqlite 蓝绿注释与行为不符/P3-10 零散卫生（未用 import、gate 文件清单通配、acl_ast 常量钉死）；**调研借鉴检查**：五项全部吻合（强类型路线/正文向量分离/模型钉版本扩展为受控双标签/精确扫描边界/无已知坑违反）；唯一偏差=报告 §2.6 LEFT JOIN 聚合建议实现为第二条 IN 查询（更符合 D24、文档回写注明即可）；**需求边界**：纯文档回写清单（design §4/§5.1/§5.2/§5.3/§6.1/§3/§7/§8、requirements §8/D12/D22、known-gaps G-8/G-6、TEST-CASES v1.6 多条）——无新增用户决策点；**Tester 5 处过强表述更正**（P3-6 PASS 不成立/下推断言不成立/public_audit_guard 第三面不成立/dims_json 残留少计/R2-P3-4 应降为部分）——不推翻门禁执行但证据链不足
- R1 committer NEEDS_CHANGES → **修复轮启动判定（supervised-coding）**：需求边界为文档回写清单、无实质分歧无需用户拍板 → 直接转 R2（round=2、reviewedSha 置空）；修复范围=P2×2 全修 + P3 顺手（P3-1 函数名清理/P3-2 测试库限定说明/P3-4 注释改写/P3-5 异常行声明+断言/P3-6 RUNBOOK SQL 补全/P3-7 四处残留清理/P3-9 注释改写/P3-10 卫生项/P3-8 SET standard_conforming_strings on 防御纵深），P3-3 登记（多 schema 场景影响小）——续接 Coder 会话 ses_e91982b7bffenn2qJjTzLDPRMo（用户 2026-10-25 确认修复计划）
- R2: 修复轮启动（fixing→implementing；round=2；reviewedSha 置空；修复范围=P2×2 + P3 顺手 9 件，续接 Coder 会话）

- R2: 修复轮启动（fixing→implementing；round=2；reviewedSha 置空；修复范围=P2×2 + P3 顺手 9 件，续接 Coder 会话）
- R2: coder 完成（2026-10-25，续接会话，commit `f35044ad6bbb9ed4ba12d96d26d0a45990f5b461` 于 develop_opencode，14 files +163/−80）——P2×2 全修+P3 全修（P3-3 顺手一并）逐条响应"已修"：P2-1 双捕获（DuplicateTable+UniqueViolation 23505 主形态）+复核迁 to_regclass（P3-3 顺手一行）+竞态测试改名参数化 23505/42P07 双分支（各跑恢复+fail-closed 两半）+**R1 形态红灯实证**（临时改回单捕获→23505 注入穿透 `pg_type_typname_nsp_index` failed→恢复双捕获 PASSED）+docstring/RUNBOOK 同步；P2-2 下推测试改 AST 结构断言（InValue dataset_id/id 在 cte.parts 与 outer.parts 分开断言、删恒真 SQL 切分）+**红灯实测**（移除下推→2 failed 断言消息逐字命中→恢复→2 passed）；P3-1 public_audit_guard 改 pg_proc 实测清单 lattice_audit% DROP FUNCTION CASCADE 三面真清理；P3-2 DSN 测试库限定 docstring；P3-4 双方言注释对齐；P3-5 孤立行声明+断言；P3-6 RUNBOOK 分子/分母闭合 SQL 实测可执行；P3-7 四处残留清零（grep 余下全为历史注记语境）；P3-8 SET standard_conforming_strings=on 实测 SHOW=on；P3-9 注释校准；P3-10 五件卫生。自测：门禁 GATE PASS 271+1 deselected 双模式（构成与 R1 持平）+ 无 DSN EXIT=1 + bench2 守卫复跑 EXIT=0 + 分项 49 passed。supervised-coding 机械核验：HEAD=f35044a 在 develop_opencode ✓ commit 格式 ✓ 14 files diff 与申报一致 ✓ docs/prototype 零 diff ✓ 工作区仅工作流文件 ✓ origin/develop 已同步 ✓ 未 push ✓

- R2: committer APPROVED（2026-10-25，续接会话，报告原文见"最新验证意见原文"节 Committer R2 小节；reviewedSha=f35044a=HEAD 核验一致）——P1×0/P2×0；R1 意见处置核对表全过（P2-1 双捕获语义正确+autocommit 边界确认、P2-2 AST 断言显式构造期望节点非自证、P3×10 全落地含 P3-3 顺手清偿）；修复质量抽查过（P3-1 清理顺序函数 CASCADE 先行正确、SET 与 Literal 转义叠加消除 off 逃逸面、R1 核心零行为改动）；新发现 P3×4 记录级不阻塞（PG legacy 孤立行断言未补/setup_connection docstring 未同步/DROP FUNCTION 无参签名适配/.to_regclass 对同名 view 边界知识）；**需求边界终版确认**：R1 清单继续有效 + R2 新增 6 条细化（standard_conforming_strings 连接纪律/竞态双捕获形态与 ADR 引用/索引实际查询面/合法成对行计数口径/public_audit_guard DSN 测试库约定/RUNBOOK 覆盖率 SQL 引用）——无新增用户决策点；Tester R2 报告核对属实（唯一注记：P3-5 孤儿行断言仅 sqlite 侧）
- **终态校验（2026-10-25 supervised-coding）**：testVerdict=PASS + reviewVerdict=APPROVED + reviewedSha=testedSha=HEAD(f35044a, develop_opencode) ✓ → status=approved，待用户确认交付；交付后 supervised-coding 按文档回写清单落笔（R1 §7 + R2 §6 终版）

## 最新验证意见原文

### Tester R2 复验报告原文（2026-10-25，testVerdict=PASS）

# task-knowledge-lattice-m0b-3 R2 复验报告（tester）

## 1. 前置校验

| 项 | 结果 |
|---|---|
| HEAD = `f35044ad6bbb9ed4ba12d96d26d0a45990f5b461`（develop_opencode） | ✓ |
| 父提交 = `37a5f36`（R1 PASS 基线） | ✓ |
| 工作区仅 supervised-coding 工作流文件（m0b-2 检查点 M + m0b-3 ??），全程未动 | ✓ |
| git 全程只读；红灯复现的两处 src 临时改动均以字节一致方式还原（`git diff` 为空实证） | ✓ |
| PG 容器在位；探针残留自清（pg_namespace 外来 schema 归零）、临时目录已清 | ✓ |

## 2. 门禁独立复跑

- `scripts/test_gate.sh`（DSN 在场）：**GATE PASS，双模式各 `271 passed, 1 deselected`，0 skipped**（19.50s / 17.95s）；PG 专用计数 **86 = [pg] 参数化 54 + PG 专用 32**（gate 已通配 `tests/test_pg_*.py`——P3-10 落地后计数面正确）
- `env -u LATTICE_PG_DSN`：友好文案 + **exit=1** ✓
- **与 R1 持平**：271+1 构成不变（竞态测试改名 `..._survives_create_race`，单条目内双异常类循环，收集数 1→1）✓

## 3. P2-1 / P2-2 复验（含红灯独立复现）

**P2-1（锁外建表竞态）——PASS**
- ① 实现形态：`migrate.py` 改 `except (pg_errors.DuplicateTable, pg_errors.UniqueViolation):` 双捕获（注释点名 pg_type 唯一键竞态形态）；`_schema_migrations_exists` 迁 `SELECT to_regclass('schema_migrations') IS NOT NULL`（P3-3 顺手，search_path 全覆盖）；docstring 同步申报文（23505 主形态/42P07 间或/fail-closed 不回退）
- ② 测试形态：`test_pg_ensure_schema_migrations_survives_create_race` 对 `(UniqueViolation, DuplicateTable)` 两类各跑**恢复分支**（表在场→复核干净继续）与 **fail-closed 分支**（DROP 后→同款异常照抛）+ 真实重建收尾；断言面用 `to_regclass`
- ③ **红灯独立复现（亲测）**：临时将捕获改回单 `except pg_errors.DuplicateTable`（R1 形态）→ 跑竞态测试 → **FAILED：`psycopg.errors.UniqueViolation: duplicate key value violates unique constraint "pg_type_typname_nsp_index"` 穿透**（test_pg_scaff.py:630）→ 字节一致还原 → 复跑 **1 passed**。证明测试真实甄别 23505 分支，非走过场

**P2-2（CTE 下推断言空转）——PASS**
- ① 测试形态：`test_dataset_doc_filters_pushed_into_cte` 改 **AST 节点树断言**——`InValue(ColumnRef("d","dataset_id"),...)` 与 `InValue(ColumnRef("d","id"),...)` 在 `build_cte_where(plan).parts` **分开断言**（:444-445，断言消息「dataset/doc 过滤未下推进 CTE」）、同条件在 `build_outer_where(plan).parts` 分开断言（:447）；R1 的恒真 SQL 切分（`split(")\n SELECT")` 不命中分隔符）已整段删除；行为半句保留
- ② **红灯独立复现（亲测）**：临时移除 `build_visible_docs_cte_where` 的 `*filter_nodes(plan)` → 双后端 **2 failed，断言消息逐字命中 `AssertionError: dataset 过滤未下推进 CTE`（test_v11_schema.py:444）** → 字节一致还原 → **2 passed**。证明断言对实现回归真实敏感

## 4. P3 逐条勾验表（对照 Committer R1 报告 P3-1~P3-10）

| 条目 | 判定 | 证据（独立执行） |
|---|---|---|
| P3-1 三面自清理 | **PASS** | fixture 改按 `pg_proc` 实测清单（`lattice_audit%`）`DROP FUNCTION … CASCADE` 先行 + 表 CASCADE 清触发器 + 末尾三面断言兜底；**独立实跑**：fixture 用例后 psql 直查 public 三面 = **0/0/0** |
| P3-2 DSN 测试库限定 | **PASS** | fixture docstring 明确「LATTICE_PG_DSN 必须指向专用测试库，不得指向承载开发/演示审计数据的共享库」（test_pg_scaff.py:67-69） |
| P3-3 复核多 schema | **PASS**（登记项 coder 顺手完成） | `to_regclass('schema_migrations')` 按 search_path 全覆盖解析（migrate.py:145-149） |
| P3-4 索引注释对齐 | **PASS** | 双方言 0002 注释改写为真实查询面（mark_embedding_batch 走 doc_id 前缀；pending_embeddings 为等值+NOT EXISTS 不走本索引，M1 量级再评估）；DDL 语句零改动 |
| P3-5 孤立行声明+断言 | **PASS** | 0002 双方言注释声明「embedding 非空而 embed_model NULL 属非法孤立态、显式丢弃」；test_v11 新增 `chk:orphan` 行（embedding 非空/标签 NULL）+ 断言不进 chunk_vectors（:110-115）；计数口径注释同步为「合法成对行数」 |
| P3-6 RUNBOOK SQL 闭合 | **PASS** | 分子/分母双 SQL 均限定 `tombstone=0 AND version=active_version`；**双方言在库实测**：种子含在用/墓碑/旧版本三块各带新标签向量 → 分子=1、分母=1（闭合）、裸 `GROUP BY` 对比=3（证实旧口径确实误导） |
| P3-7 四处残留清零 | **PASS** | postgres/__init__、store/backend.py 模板注释、test_pg_scaff 两处 jsonb docstring 全部改写；grep 余下命中全为消解注记与**负向断言**（`assert "json_each" not in sql`——应保留项） |
| P3-8 standard_conforming_strings | **PASS** | `setup_connection` 显式 `SET standard_conforming_strings = on`（含 off 场景反斜杠风险注释）；**实测**：工厂后 SHOW=on、手动 off 后工厂再入重钉 on |
| P3-9 蓝绿注释校准 | **PASS** | 注释改为「命中的是标签不符分支；PK 冲突路径由 test_pg_backend 覆盖」，与实际行为相符 |
| P3-10 卫生五件 | **PASS** | contextlib / `build_visible_docs_cte_where` / acl_render 4 个无用 re-import 移除；gate PG_ONLY 通配 `tests/test_pg_*.py`；bench2 未用 `sqlite3` 移除；acl_ast 增「标识符位只允许构造期常量」不变式 docstring |

## 5. 回归核对与 R1 过强表述消除确认

**R1 核心逻辑零触碰**：14 files 中 0002 双方言均为纯注释改动、acl_ast 仅 +4 行 docstring、sqlite 渲染器仅删 4 个无用导入、connection.py 仅 +5 行 SET——v1.1 迁移 DDL/渲染器收敛/dims 聚合主体零改动 ✓

**本人 R1 报告 5 处过强表述，本轮逐一正视并在新代码下复验消除**：

| R1 过强表述 | R2 现状 |
|---|---|
| ① P3-6「DuplicateTable 捕获+复核分支」PASS | 不成立→已收口：双捕获含 23505 主形态，红灯亲测穿透后恢复（§3） |
| ② 「CTE 与外层双在场断言」（test_v11:413-424） | 不成立（切分不命中恒真）→ 已改 AST 结构断言，红灯亲测敏感（§3） |
| ③ 「public_audit_guard 幂等 DROP TRIGGER/FUNCTION/TABLE」 | 不成立（函数面漏清）→ 已按 pg_proc 实测清单三面真清理，psql 独立查证 0/0/0 |
| ④ 「dims_json 仅 2 处历史注记」 | 少计（实为 6 处）→ R2 清理 4 处现行文档残留，余下均为 0001/0002 DDL、负向断言与消解注记（合规保留） |
| ⑤ 「R2-P3-4 PASS」 | 应为部分 → R2 补齐函数面后三面完整，本轮全判 PASS |

**零弱化**：竞态测试 R1 的恢复/fail-closed 两半保留并扩为双类各跑；下推测试行为断言保留；test_pg_scaff 删除面全为旧形态替换；门禁 271+1 与 R1 逐条持平 ✓

## 6. 边界复查

- **14 files +163/−80** 与申报逐项吻合 ✓；commit message 格式 `[task-knowledge-lattice-m0b-3] R2: …` ✓；父提交=37a5f36 ✓
- `git diff 37a5f36..f35044a -- knowledge-lattice/docs knowledge-lattice/prototype` 为空 ✓
- `.env` 无任何提交记录（仅 .env.example 在库）✓
- 工作区终态：仅 supervised-coding 工作流文件，无本轮验证残留（红灯两文件字节一致还原、PG 探针 schema 清零、临时目录已删）✓
- skip 清单：**0 skipped**（双模式门禁强制；1 deselected=manual 走查，约定内）

## 7. 结论

**testVerdict: PASS**

P2×2 经实现核验+红灯独立复现确认真实收口；P3×10 全部落地（含登记项 P3-3 顺手完成）；门禁 271+1 双模式与 R1 构成持平、0 skipped；R1 核心交付零触碰、本人 R1 报告 5 处过强表述全部消除在案。

testedSha: `f35044ad6bbb9ed4ba12d96d26d0a45990f5b461`

### Committer R1 报告原文（2026-10-25，reviewVerdict=NEEDS_CHANGES）

# task-knowledge-lattice-m0b-3 R1 Committer 审查报告

## 1. 前置校验

| 项 | 结果 |
|---|---|
| HEAD / testedSha / 审查对象 | `37a5f363802b61c8a6c944994df08b9cc12f8a1d` 三方一致；分支 `develop_opencode`；父提交 `6f08334`（M0b-2 合入基线） |
| diff 范围 | `37a5f36~1..37a5f36` = **43 files，+1617/−737**，与 filesChanged 申报逐项吻合 |
| 工作区 | 仅 `.opencode/workflows/task-knowledge-lattice-m0b-2.md`(M) + task-knowledge-lattice-m0b-3.md(??)，属 workflow 收口文件，未触碰 |
| docs / prototype | `git diff 6f08334..HEAD -- knowledge-lattice/docs knowledge-lattice/prototype` 为空 ✓ |
| `.env` | 未入库；仅 `.env.example`（模板无真实密钥）✓ |
| commit / push | 格式 `[task-knowledge-lattice-m0b-3] R1: …` 合规；未 push；origin/develop 已作为父提交同步 ✓ |
| 测试复跑 | 本次审查未独立复跑 pytest（bash 仅放行 git/gh 只读）；以下结论基于 Tester R1 报告 + 全量静态审阅 |

**门禁/测试证据核对**：Tester 申报 271 passed+1 deselected（双模式）、PG 专用 86=54+32、0 skipped，与基线与新增数算术一致（249+22）；`scripts/test_gate.sh` 的 `|| true`、PG_ONLY 计数、空 summary fail-closed 均在场。Tester 报告在 P3-6 与两处测试断言上存在过强表述（见 §8），不推翻门禁运行本身，但影响验收证据可信度。

## 2. 结论

**reviewVerdict: NEEDS_CHANGES**

P1 无；**P2×2**（P3-6 锁外竞态修复未覆盖真实异常类；CTE 下推测试断言空转）；其余为 P3。代码主体（schema v1.1 / CTE 收敛 / dims 聚合 / 蓝绿形态）静态正确，但上述两项属于“遗留项已清偿 + 测试已锁死”的申报与证据不成立，按审查清单属应修。

## 3. 问题清单

### P2（应修）

**P2-1｜`store/postgres/migrate.py:136`（及 `:118-124`、`tests/test_pg_scaff.py:588-624`）：P3-6 捕获的异常类与真实竞态不符**
- M0b-1 移交原文（检查点 line 243）明确：锁外 `CREATE TABLE IF NOT EXISTS` 的竞态是 **PG 的 `pg_type` 唯一键冲突**（23505 `UniqueViolation`），建议“移入锁内或捕获 `duplicate_key` 重试”。
- 实现只捕获 `psycopg.errors.DuplicateTable`（42P07）。并发首次启动最可能抛的是 `pg_type_typname_nsp_index` 唯一约束的 `UniqueViolation`，该分支不会命中，迁移仍会崩。
- `test_pg_ensure_schema_migrations_survives_duplicate_table_race` 的 `_RaceConn` 人为注入的正是 42P07，**测试与生产真实失败模式不同**——即使真实竞态未兜底，测试仍绿（走过场测试）。
- `RUNBOOK.md:64` 与 `migrate.py` docstring 同步宣称“DuplicateTable 恢复分支兜底”，同源失真。
- **建议**：`except (pg_errors.DuplicateTable, pg_errors.UniqueViolation):` 后复核存在性；回归测试至少补 23505 注入分支（更佳：真实双连接 fresh schema 竞态）；同步改 docstring/RUNBOOK。若选择“移入锁内”，则需在 `_apply_one` 前以事务级 advisory lock 包住建表。

**P2-2｜`tests/test_v11_schema.py:419-420`（`test_dataset_doc_filters_pushed_into_cte`）：断言并未真的验证“下推进 CTE”**
- `render_select` 产物是 `…)) SELECT …`（无换行）；`sql.split(")\n SELECT", 1)[0]` 的分隔符永不命中，`[0]` 返回整段剩余 SQL，随后 `rsplit(")", 1)[0]` 只是去掉整条 SQL 末尾的 `)`。
- 因此 `cte_part` 实际包含**外层**的 `d.dataset_id IN` / `d.id IN`，断言恒真；若 CTE 完全没有下推（实现回归），该测试仍会绿。Tester 报告“CTE 与外层双在场断言”不成立。
- **建议**：用 `split(") SELECT ", 1)` 正确切 CTE/主查询，或更稳地用 AST 结构断言：`matrix.build_cte_where(plan)` 的 `And.parts` 中含 `InValue(ColumnRef("d","dataset_id"))` / `InValue(ColumnRef("d","id"))`，且 `build_outer_where` 同条件在场；补一条“若移除 CTE 下推则测试红”的改法说明。

### P3（记录/顺手修）

**P3-1｜`tests/test_pg_scaff.py:66-70`：R2-P3-4 的“三面自清理”不成立**
`for name in ("audit_no_delete", "audit_no_update", "audit_no_truncate")` 是**触发器名**；实际函数名是 `lattice_audit_append_only` / `_delete` / `_truncate`。`DROP TABLE audit_events CASCADE` 只级联触发器，**public 里的 audit 函数不会被清掉**；末尾断言会 fail-closed，但 fixture 的“幂等自清理”对第三面无效。建议直接遍历 `_public_audit_objects(pg_db)[2]` 的 `proname` 执行 `DROP FUNCTION … CASCADE`（或按真实函数名清理）。

**P3-2｜`tests/test_pg_scaff.py:56-77`：public audit 清理对共享 dev 库是破坏性动作**
`DROP TABLE IF EXISTS audit_events CASCADE` 在 `public` 上是无差别删除；若 `LATTICE_PG_DSN` 指向的 `lattice` 库同时承载开发/演示审计数据，会被清掉。建议 fixture 限定专用测试库/独立 schema，或在测试文档明确 DSN 必须是测试库。

**P3-3｜`store/postgres/migrate.py:142-148`：`_schema_migrations_exists` 仅查 `current_schema()`**
对多 schema search_path，若表已在后续 schema，复核会假阴性并重抛；当前建表落在首个 schema，实际影响小。建议按 `to_regclass('schema_migrations')` 或 `current_schemas(false)` 逐项判断。

**P3-4｜`store/sqlite/migrations/docs/0002_schema_v1_1.sql:36-38`：索引注释与查询面不符**
`pending_embeddings(label)` 是 `embed_model` 等值 + `NOT EXISTS`，无法用 `(doc_id, embed_model)` 的 `doc_id` 前缀；只有 `mark_embedding_batch(doc_id, version)` 能。注释“mark_embedding_batch(doc_id)/pending_embeddings(label) 的扫描面改为 (doc_id, embed_model) 前缀”不准确。建议改注释，或补 `(embed_model) WHERE tombstone = 0`（如认为 label 清点会走热路径；当前数据量可不补）。

**P3-5｜`store/sqlite/migrations/docs/0002_schema_v1_1.sql:23-28`：双守卫会静默丢弃 `embedding` 非空但 `embed_model` NULL 的行**
验收 #1 的计数口径是“原 embedding 非空行数”；异常行会被静默丢弃，且 `test_v11_schema.py:56-119` 未覆盖该形态。建议明确这是非法/孤立行（迁移失败或注释声明丢弃），并补一行断言。

**P3-6｜`RUNBOOK.md:22`：覆盖率查询未 join `chunks` 限定在用版本**
`SELECT embed_model, count(DISTINCT rid) …` 与下一句“new:2560 行数 = 在用块数（tombstone=0 且版本在用）”口径不闭合；请给出 join `chunks` 的完整 SQL，或把分母 SQL 一并写出，避免运维误判 100%。

**P3-7｜`store/postgres/__init__.py:13`、`store/backend.py:24`、`tests/test_pg_scaff.py:716/777`：v1.1 后过时文档残留**
`postgres/__init__` 仍写“json_each → jsonb 等价路径谓词；visible_docs 双写法同构”；`store/backend.py` 仍写“NOT EXISTS json_each …”模板；PG 安全测试 docstring 仍提 `jsonb_extract_path`。均非可执行路径，但与“拍板 1 零残留/唯一路径”的文档一致性不符。建议随 R2 顺手改；不阻塞。

**P3-8｜`store/acl_ast.py` `Literal` 仅单引号加倍；`store/postgres/connection.py:57-85` 未钉 `standard_conforming_strings`**
PG 默认 `on` 下安全，且旧 json path 同款转义，**非新引入注入面**；但维度 key 是库内数据，若目标 PG 被配置为 `off`，反斜杠+引号组合理论上可破坏字面量。建议 `setup_connection` 显式 `SET standard_conforming_strings = on`（或把 key 改为绑定参数，彻底消除），作为防御纵深记录。

**P3-9｜`tests/test_v11_schema.py:255-258`：注释与行为不符**
“已回写标签零触碰（重写同 (rid,label) → PK 冲突吞掉）”实际因 `mark_embedding_batch(m:b)` 已把 `chunks.embed_model` 改为 `m:b`，此处命中的是**标签不符**分支；PK 冲突路径由 `test_pg_backend.py:151-153` 覆盖。建议改注释，避免误以为 sqlite 侧已测 ON CONFLICT。

**P3-10｜零散卫生**
- `tests/test_v11_schema.py:16` `contextlib` 未用；`tests/test_r2_review_fixes.py:42` `build_visible_docs_cte_where` 未用；`store/sqlite/acl_render.py` 的 `_filter_nodes_neutral/_org_eq/_tombstone_eq/_version_eq` 为 re-export 之外的无用导入（有 noqa，无门禁影响）。
- `scripts/test_gate.sh:38` PG_ONLY 只列 `test_pg_scaff.py`/`test_pg_backend.py` 两个固定文件，新增 `test_pg_*.py` 时会计数漏项；建议 `tests/test_pg_*.py` 通配。
- `benchmarks/bench2_vector_layout.py` `import sqlite3` 未用（守卫里实际用 `connect`）。
- `store/acl_ast.py` 的 `Func/TableRef/ColumnRef` 名称未做标识符白名单；当前 builder 全常量、无注入面，但“标识符路径不变式”只在 `param_value` prefix 上机械执行，建议构造层或 docstring 把“只允许常量”钉死。

## 4. 调研借鉴检查（用户常设要求）

| 调研沉淀 | 本段实现落点 | 结论 |
|---|---|---|
| **blog/03 §4.2**：schema 两流派——JSON blob vs 强类型字段；深度用强类型 | 删 `chunks.dims_json`，维度转 `document_dimensions` 关系过滤；`chunk_vectors` 强类型列 | **吻合**（报告 §2.6 第 2 条即此方向） |
| **blog/03 §4.3**：正文/向量分离，向量库只存 embedding 与引用（kotaemon 式） | `chunk_vectors(rid, embed_model, embedding)` 不含正文；正文留 `chunks`；回表代价由 M0b-2 实测 | **吻合**；本实现是“关系库内分表”而非独立向量引擎，但“向量列外移 + 正文常驻窄表”同构 |
| **blog/03 §5 / blog/10 §3.3**：模型钉版本（embed_model 记录在 chunk 上）+ 索引可重建 | `chunk_vectors.embed_model` 每行记录；PK 含 `embed_model`；蓝绿 runbook；`0002` 迁移可重建 | **吻合**；单标签钉死放宽为受控双标签窗口（报告方案二），是调研“可重建/可切换”思路的延伸，不是违反 |
| **blog/04**：pgvector 精确扫描起步；2560 维 > 2000 维 HNSW 上限，halfvec/表达式索引随 M1；sqlite-vec 十万级边界 | `vector` 列无维度 + `<=>` 精确扫描；`0002` 注释显式引 G-6；未上 ANN/索引 | **吻合**（边界已声明，M1 再议 halfvec） |
| **MATERIALIZED / CTE 实践** | 调研正文无 CTE 具体条目；本段以 M0b-2 报告 §2.3 计划病理为权威，双方言 `AS MATERIALIZED`，CTE 纯 JOIN/EXISTS | **吻合内部实验结论**；与调研 blog/07“引擎内前置过滤、勿 post-trim”一致 |
| **调研已知坑** | ① ACL 检索期 SQL 下推（blog/07）✓；② dims_json blob 一致性维护点消除（blog/03 §4.2）✓；③ 模型标签谓词防混模型（D12）✓；④ 精确扫描/halfvec 边界（blog/04）✓；⑤ 索引当投影/可重建（blog/03 §5）✓ | **无违反** |

唯一偏差（非违规）：报告 §2.6 择型①建议“检索 SQL LEFT JOIN document_dimensions 聚合（json_group_array/jsonb_agg）”，实现改为 store 层**第二条 IN 查询** `_attach_dims`。两者都属“从 document_dimensions 聚合”，且第二条查询避免 JSON 聚合的双方言差异，更符合 D24；top_k≤20 代价可忽略。建议在文档回写时注明实际形态（见 §7）。

## 5. schema v1.1 与渲染器收敛审查结论

### 5.1 0002 双方言 DDL

| 审查点 | 结论 |
|---|---|
| 删列与搬运顺序 | **正确**：`INSERT..SELECT` 在 `DROP COLUMN dims_json/embedding` 之前；SQLite 先 `DROP INDEX idx_chunks_vec_pending`（该部分索引 WHERE 引用 embedding，SQLite 拒绝 DROP 被索引引用的列）再重建；PG 显式 DROP INDEX 保持语句序一致 |
| 事务/失败回滚 | **正确**：SQLite `BEGIN IMMEDIATE` + 迁移窗口 `foreign_keys=OFF` + 事务末 `foreign_key_check` + `user_version` 同事务；PG `BEGIN` + advisory lock + 原生 FK 即时校验；两边均整事务回滚，幂等重放靠版本记录 |
| 键形/级联 | **正确**：`PK(rid, embed_model)`；`rid REFERENCES chunks(rid) ON DELETE CASCADE`；蓝绿同 rid 多标签可插、PK(rid) 冲突探针保留；版本切换时删块的级联已由测试与 `delete_by_doc` 覆盖 |
| 谓词索引重建 | **正确**：`(doc_id, embed_model) WHERE tombstone = 0`，删除列前先删旧索引；注释对 `pending_embeddings(label)` 的可用性表述过强（P3-4） |
| 版本只前进/框架兼容 | SQLite `user_version`、PG `schema_migrations` + 水位 fail-fast；`0002` 作为普通迁移被两框架正确应用；P3-6 的锁外建表竞态是唯一框架层缺陷（P2-1） |
| 蓝绿物理正确性 | PK(rid, embed_model) + `cv JOIN` 谓词 + 存量搬运 + 旧标签延后清理，与报告 §3.5 建议表一致；`chunks.embed_model` 收窄为状态标签，回写路径防护语义等价 |

### 5.2 渲染器收敛

| 审查点 | 结论 |
|---|---|
| ACL 安全红线静态复审 | **不回退**：绑定参数名仍由 `_Renderer` 自控 `g<seq>_<i>`；`InValue.param_prefix` `fullmatch` + fail-closed；`_Renderer` 单趟渲染；授权值/org/模型标签/查询串绑定；维度 key 仅 `Literal` 引号加倍；恶意 key 三连断言仍在。**未引入新注入面**（P3-8 为既有转义策略纵深项） |
| 三路 CTE 同构 | **正确**：基础/向量共用 `build_visible_docs_cte_where` / `build_visible_docs_outer_where`；`build_vec_parts` 的 `cv_join` 只追加 `Eq(cv.embed_model, BindParam(current_model))`；FTS 路共用同一 CTE，版本条件在 JOIN（T9）；TC-ACL-06 断言真实 |
| MATERIALIZED 位置 | **正确**：双方言同前缀；sqlite ≥3.35 语法可用 |
| 版本门控 | 基础/向量外层常量；FTS 在 JOIN；`d.org_id` 双在场；过滤下推 CTE + 外层双保险 |
| dims 契约（择型①） | `_attach_dims` 单条 IN 查询、键序稳定、SQL 收口 store；`retrieve.py` 保留 dims 字段形态，E2E 断言仍成立；PG recall_fts 仍 M1（既有 deferral） |

**结论**：schema v1.1 与渲染器收敛的实现本身**通过静态审查**；扣分项集中在 P2-1（框架竞态）与 P2-2（测试证据）及 P3 文档/测试卫生。

## 6. 遗留处置与零弱化复核结论

### 6.1 遗留 20 条

M0a CTE ①②③④⑤⑥ 全 ✅（⑥实现正确但测试空转 P2-2）；M0b 批次：P3-4 ✅消解、P3-5 ✅消解、**P3-6 ❌ P2-1**、P3-11 ✅、R2-P3-1 ✅、R2-P3-2 ✅、R2-P3-4 ⚠️ P3-1（第三面未清）、R2-P3-7 ✅（固定清单可维护性 P3-10）、R2-P3-8 ✅、P3-F ✅、P3-H/I ✅、migrate 告警 ✅、_Renderer ✅。

### 6.2 零弱化复核

- 无 skip；删除/改名 13 条语义保持或拍板 1 sanctioned；ACL-07 精确集合断言强于旧“两路相等”；ACL-06 新增 CTE 文本逐字一致更强断言；EMB-02 新增 3 负向断言；scaf_03 纯重编号；fts_03/scaf_04 等价改造；唯一新测试质量问题=P2-2 下推测试空转 + P3-9 注释不符。

## 7. 需求边界问题

**有（均为文档/口径同步，不构成本轮 coder 代码返工；无新增用户决策点）**。需 supervised-coding 收口回写：design.md（§4 DDL v1.1 形态与 0001 历史说明、§4 版本切换段删向量行、§5.1 CTE 唯一路径+MATERIALIZED+快照口径+下推、§5.2 向量谓词 cv JOIN+dims 来源、§5.3 方案二已选、§6.1 dims 来源聚合（注明 _attach_dims 实际形态）、§3/§8 M0b 行、§7 adapters 注记）、requirements.md（§8 M0b 行、D12 蓝绿已定、D22①唯一路径/②补清 chunk_vectors、line 88）、known-gaps.md（G-8 方案二已选、G-6 v1.1 注记）、TEST-CASES.md（版本段 v1.6 + TC-SCAF-03/ACL-06/ACL-07/EMB-01/02/06/07/E2E-04+附录 A-3/ING-06/07/VER-06/E2E-05 + TC-FTS-01 勘误一并落笔）、benchmarks/report（§2.6 择型实现形态注记）。

**无需用户新决策**：三项拍板已覆盖上述形态；其余均属口径登记。

## 8. Tester R1 报告核对

**属实/可采信**：HEAD/testedSha/43 files/docs 零 diff/工作区；门禁 271+1、0 skipped、PG 86=54+32；test_v11 21 条与收集构成；ACL-07 12 条改名算术；ACL-06/EMB-02 增强；dot-key/fullmatch/自控参数名/单趟纪律；遗留绝大多数；bench 退役守卫；PG 探针自清。

**需更正/过强（不推翻门禁运行，但影响证据强度）**：
1. P3-6 PASS 不成立（只核 DuplicateTable 分支存在，未核对 pg_type 23505 原文；测试注入同为 42P07）。
2. “test_v11_schema.py:413-424 CTE 与外层双在场”不成立（分隔符不命中，cte_part 实为整段 SQL）。
3. “public_audit_guard 幂等 DROP TRIGGER/FUNCTION/TABLE”不成立（函数名写成触发器名，lattice_audit_* 未清）。
4. “dims_json 仅 2 处历史注记”少计（postgres/__init__.py:13、store/backend.py:24、test_pg_scaff.py:716/777）。
5. “R2-P3-4 PASS”应降为“部分”（自清理第三面未实现）。

**结论**：Tester 的 PASS 在门禁执行层面可采信，但在 P3-6 与 CTE 下推两项的**证据链**不足；按 P2×2 退修。

**CASE_BUG 裁定请求**：本轮未收到 tester 提交的 CASE_BUG，无裁定。

## 9. reviewedSha

**reviewedSha: `37a5f363802b61c8a6c944994df08b9cc12f8a1d`**（= HEAD = testedSha）

交付把关：尚未进入用户确认交付阶段，未执行 gh pr review 留痕；若后续确认交付，需核对 evidence manifest 双 SHA 与最终 HEAD 一致后再放行。合入动作不经手。

### Tester R1 报告原文（2026-10-25，testVerdict=PASS）

# task-knowledge-lattice-m0b-3 R1 独立验证报告

## 1. 前置校验

| 项 | 结果 |
|---|---|
| HEAD = `37a5f363802b61c8a6c944994df08b9cc12f8a1d`（develop_opencode） | ✓ |
| 父提交 = `6f08334`（origin/develop 同步后） | ✓ |
| 工作区仅 supervised-coding 收口改动（m0b-2 检查点 M + m0b-3 ??），未触碰 | ✓ |
| PG 容器 lattice-pg（16.15 + pgvector 0.8.7，vector 扩展在位，开工时库内 0 外来 schema） | ✓ |
| git 全程只读（checkout 用 `git diff` 补丁反向 + `patch -R` 到临时目录，未动 git 状态） | ✓ |

## 2. 门禁独立复跑 + 构成对账

- `scripts/test_gate.sh`（DSN 在场）：**GATE PASS，双模式各 `271 passed, 1 deselected`，0 skipped**（常规 18.86s / `-O` 16.09s）；开场输出 PG 专用计数 **86 = [pg] 参数化 54 + PG 专用 32** ✓
- `env -u LATTICE_PG_DSN bash scripts/test_gate.sh`：友好文案 + **exit=1**（拒绝静默绿）✓
- **构成对账**：收集期 ID 逐条 diff（父提交 6f08334 经反向补丁重建副本收集 250 条 vs HEAD 272 条）——**+35/−13 = 净 +22**，逐条归属：
  - `test_v11_schema.py` 新增 **21**（backend 参数化 5×2 + matrix 参数化 4×2 + sqlite 有库/空库 2 + pg 有库 1）✓
  - `test_pg_scaff.py::test_pg_ensure_schema_migrations_survives_duplicate_table_race` 新增 **1**（P3-6 回归）✓
  - `test_acl_07` 12↔12 改名收敛（双写法 → CTE 唯一路径，净 0）；`test_r2_review_fixes` 1 条改名（`vector=True` → `build_vec_parts`，ValueError 语义不变，净 0）
  - 249+22=271、manual 1 保持 1 ✓

## 3. 验收表 7 项逐条勾验

| # | 验收项 | 判定 | 关键证据 |
|---|---|---|---|
| 1 | v1.1 迁移双后端跑通 | **PASS** | 0002 双方言 DDL（sqlite 39 行/PG 24 行）+ 手工探针双方言各一轮全过（见 §4）；`foreign_key_check` 空、搬运行数=非空行数、幂等重放 `applied=[]`、版本只前进（scaf_03 重编号断言） |
| 2 | 全量复跑绿 + 三路同构 + 谓词语义 | **PASS** | 门禁双模式 271+1、0 skipped；TC-ACL-06 断言 `vec_cte == base_cte`、`vec_outer == base_outer`（节点树逐字）；TC-EMB-02 谓词 `Eq(cv.embed_model, BindParam(current_model))` 列引用迁 cv、参数绑定不变 |
| 3 | 拍板 1 落地完整 | **PASS** | grep 核验：`dims_json` 仅存于 0001 历史 DDL/0002 删列语句/注释；`json_each/jsonb_extract_path` 可执行路径零残留（仅 2 处历史注记）；双方言渲染器 `_CTE_PREFIX` 均 `AS MATERIALIZED`；契约择型①注明（retrieve.py:79-82 + 口径注记） |
| 4 | 拍板 2 落地完整 | **PASS** | `chunk_vectors` PK(rid, embed_model) 双后端（pg_scaff 断言 `'PRIMARY KEY (rid, embed_model)'`）；chunks.embedding 删除；谓词/回写迁 cv（write_embeddings/pending_embeddings/mark_embedding_batch 全走新表）；同 rid 双标签并存可插（探针+用例双证实） |
| 5 | 蓝绿就绪 | **PASS** | RUNBOOK.md §1 引用报告 §3.5/§3.3（数字一致：P50+6%/P95+18%、552MB、1257.8MB）；门禁内 `test_pk_rid_only_conflict_probe` 双后端 PASS + bench2 `probe_pk_rid_conflict` 保留（bench2:110）；级联/并存/谓词分离实测复现（探针+21 用例） |
| 6 | 遗留批次清偿 | **PASS** | 20 条逐条见 §6，全部完成或消解登记 |
| 7 | docs 零违规 | **PASS** | `git diff 6f08334..HEAD -- knowledge-lattice/docs knowledge-lattice/prototype` 为空；文档回写留给 supervised-coding |

## 4. v1.1 迁移独立探针（双方言手工库搬运，不经项目代码建库）

**sqlite**（sqlite3 CLI 直喂 0001/0002 SQL 文件）：v1 库（user_version=1）灌 4 行 chunks（2 行 embedding 非空含不同载荷 + 1 行钉标签待嵌 + 1 行全空）→ 手动应用 0002 + 框架同款记账 → **user_version=2 ✓ / fk_check 空 ✓ / dims_json+embedding 列消失、embed_model 保留 ✓ / chunk_vectors=2 行且 hex 逐字节保真（`0000003f000000bf0000803f`）✓ / 待嵌行不搬运、标签保留 ✓ / 同 rid 双标签可插 ✓ / 同对重复 UNIQUE 拒绝 ✓ / PK(rid)-only 探针表第二标签拒绝 ✓ / 删块级联清双标签行 ✓ / 项目框架对该手工库重放 applied=[] ✓**

**PG**（docker exec psql + 专用 schema，测后 DROP CASCADE 清零）：v1 库经 0001（rid 为 identity 列——首尝试插显式 rid 被拒属探针脚本 bug，非交付问题）→ 灌同款混合数据 → 手动应用 0002（输出序列 CREATE TABLE / **INSERT 0 2**（搬运恰 2 非空行）/ DROP INDEX / ALTER×2 / CREATE INDEX）→ **schema_migrations=[1,2] ✓ / 列删除保留同 sqlite ✓ / 载荷文本保真 `[0.5,-0.5,1]` + `<=>` 距离 0 ✓ / 双标签并存 ✓ / 同对 duplicate key 拒绝（chunk_vectors_pkey）✓ / PK(rid) 探针 duplicate key ✓ / 删块级联 ✓ / 孤儿 rid FK 强制拒绝 ✓ / 项目框架重放 applied=[]、versions=[1,2] ✓**

## 5. 渲染器收敛与安全纪律复核

- **CTE 逐字一致（独立文本级探针，双方言 PASS）**：sqlite 基础/FTS 路共享同一 CTE 文本前缀；PG 基础/向量路 CTE 逐字相同；**双方言归一化参数记号后 CTE 完全一致**（D24）；四路均 `AS MATERIALIZED`、均无 json_each/jsonb/dims_json；渲染产物真实执行通过（探针文件用后即删）
- **TC-ACL-01~07 + EMB-02 + r2_review_fixes 显式复跑：61 passed（双后端）**；E2E-01+SCAF-03 8 passed
- **ACL 安全纪律（M0a-2 P1-1 红线）不回退**：`_IDENTIFIER_RE.fullmatch`（acl_ast.py:102，注释明确防尾部换行逃逸）；恶意 key 三连断言在场且绿——①恶意 prefix 构造即拒 ②Committer 攻击配方（x 维度先绑 `:g_x_0` + 括号调优变体）下外层常量齐全/参数名全合法/注释记号不出字面量外 ③双组织库真实执行无跨组织泄露；dot-key `dim.key = 'a.b'` 字面量、`$.` 零出现；参数名渲染器自控 `g<seq>_<i>`（双方言）；`_Renderer` 单趟纪律文档化（acl_ast.py:23-24 + 双渲染器 docstring）

## 6. 遗留批次 20 条勾验表

**M0a CTE 6 项**

| 条目 | 判定 | 证据 |
|---|---|---|
| ① v.status 快照口径 | PASS | acl_ast.py:212-216（CTE 不读 v.status/dim.status——编译时点授权集快照，停用/退役经下次编译生效） |
| ② 竞态回归入仓×2 | PASS | test_v11_schema.py:367-407（value_disable/retire 双用例双后端，编译后同 Plan 重执行不变+重编译收紧/放宽生效） |
| ③ 恶意 key+dot-key | PASS | test_r2_review_fixes.py:80-150 + test_v11_schema.py:427-453 |
| ④ fullmatch | PASS | acl_ast.py:36/102 |
| ⑤ 标识符不变式 docstring | PASS | acl_ast.py:14-24、sqlite/acl_render.py:11-15、pg/acl_render.py:9-11 |
| ⑥ CTE 过滤下推 | PASS | acl_ast.py:263（filter_nodes 进 `build_visible_docs_cte_where`）+ test_v11_schema.py:413-424（CTE 与外层双在场断言） |

**M0b 14 项**

| 条目 | 判定 | 证据 |
|---|---|---|
| P3-4 jsonb 标量守卫 | PASS（消解登记） | dims_json 删除后 jsonb 投影面不存在；retrieve.py:89 注记 vector_pending 口径 |
| P3-5 dot-key | PASS（消解登记） | `$.` 路径零出现（grep+探针双证）；key 仅引号字面量 |
| P3-6 锁外竞态 | PASS | migrate.py:117-139 DuplicateTable 捕获+复核分支；test_pg_scaff.py:588-624 三段式（恢复/fail-closed 照抛/真实重建） |
| P3-11 清理+.env.example | PASS | connection.py 删未用 `Path`、vec.py 删死方法 `parse_vector`；.env.example 23 行（嵌入网关/PG DSN/全 LATTICE_* 项） |
| R2-P3-1 可移植性 | PASS | test_pg_scaff `current_database()` 推导库名 + `RESET` 还原（不再硬编码 lattice） |
| R2-P3-2 友好文案可达 | PASS | test_gate.sh:61 `|| true` + :67 空 summary fail-closed |
| R2-P3-4 自清理 fixture | PASS | `public_audit_guard` 幂等 DROP TRIGGER/FUNCTION/TABLE（pg_scaff diff） |
| R2-P3-7 PG 计数 | PASS | test_gate.sh:37-39；实测 **86=54+32** |
| R2-P3-8 RUNBOOK 登记 | PASS | RUNBOOK.md §2（逐月回填代码样例 + 分区逐个落触发器 + TRUNCATE 拦截） |
| P3-F 报告唯一修订 | PASS | report-m0b-2.md diff 恰两处 +19→+18（§3.3/§3.4） |
| P3-H bench 可维护性 | PASS | bench1 `_loops_by_kind` None/0 区分 + 证据完整判定（防证据缺失误判 PASS） |
| P3-I bench 可维护性 | PASS | bench2 `recall_sql` 非法 layout/table 组合 fail-fast |
| migrate 告警恢复 | PASS | sqlite/migrate.py:131-144 finally + 成功路径恢复失败 `logger.warning` |
| _Renderer 文档化 | PASS | 双渲染器 + acl_ast「单趟渲染、绝不跨调用拼接」注记 |

## 7. skip 清单与零弱化核验

- **skip 总数：0**（双模式门禁强制 skip=失败；各分项复跑亦 0 skip；1 deselected = `test_ui_01_manual.py` manual 走查，门禁 `-m "not manual"` 约定内，非 skip）
- **零删除**：删除的 13 个收集 ID = acl_07 双写法对照 12（拍板 1 实验选型收敛的 json_each 专属断言——检查点明示 sanctioned）+ 1 条改名（语义保持：ValueError match 不变）；**其余 25 个测试文件收集 ID 一条未删**
- **零弱化**：26 文件 diff 审查——acl_07 条目数 10+2 保持、新断言为**精确期望文档集**（强于旧「两路相等」）；ACL-06 新增「CTE 文本前缀逐字一致」更强断言；EMB-02 新增 3 条负向断言；scaf_03 纯重编号+基线 2；fts_03/scaf_04 `UPDATE embedding=NULL` → `DELETE chunk_vectors` 等价改造；assert 行数对账 18/20 文件持平或净增（2 个 -1 均为 json_each 断言的多行合并等价替换）
- 边界：43 files 与申报一致 ✓；docs/prototype 零 diff ✓；.env 从未入库（仅 .env.example）✓；bench 退役守卫双实测 **EXIT=0+checkout a6ffa1c 指引**（合理——非规避复跑）✓；commit message 格式 `[task-knowledge-lattice-m0b-3] R1: …` ✓；探针 PG 残留 schema 已自清理（pg_namespace 归零）、临时目录已清

**测试门禁纪律声明**：以上全部门禁/分项/探针均为本人独立执行，未采信 coder 自测结论；唯一被环境拦截的 `git archive` 已用等价只读方案（diff 补丁 + `patch -R`）替代，不影响结论。

## 8. 结论

**testVerdict: PASS**

testedSha: `37a5f363802b61c8a6c944994df08b9cc12f8a1d`
