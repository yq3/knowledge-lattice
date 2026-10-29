---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2-1
target: knowledge-lattice
coderTaskId: ses_e7f1590aaffe6puZo9qaiEbDsL
testerTaskId: ses_e7ec33135ffe1lyeKo27eKIKWu
committerTaskId: ses_e7eb24ce7ffe9GodZ4GSWxH3p7
status: done
round: 4
maxRounds: 4
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 830d6a77c79653ffe622960aa6be6214d03a4b58
reviewedSha: 830d6a77c79653ffe622960aa6be6214d03a4b58
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [.env.example, RUNBOOK.md, docs/TEST-CASES.md, src/knowledge_lattice/api/tasks.py, src/knowledge_lattice/api/upload.py, src/knowledge_lattice/app.py, src/knowledge_lattice/config.py, src/knowledge_lattice/core/docs/credentials.py, src/knowledge_lattice/core/docs/fetch.py, src/knowledge_lattice/core/docs/ingest.py, src/knowledge_lattice/core/docs/quality.py, src/knowledge_lattice/mcp/server.py, src/knowledge_lattice/store/backend.py, src/knowledge_lattice/store/factory.py, src/knowledge_lattice/store/postgres/backend.py, src/knowledge_lattice/store/postgres/migrations/docs/0004_tombstoned_at.sql, src/knowledge_lattice/store/postgres/migrations/docs/0005_task_target_version.sql, src/knowledge_lattice/store/sqlite/backend.py, src/knowledge_lattice/store/sqlite/migrations/docs/0004_tombstoned_at.sql, src/knowledge_lattice/store/sqlite/migrations/docs/0005_task_target_version.sql, src/knowledge_lattice/store/taskclock.py, src/knowledge_lattice/worker/__init__.py, src/knowledge_lattice/worker/__main__.py, src/knowledge_lattice/worker/ipc.py, src/knowledge_lattice/worker/maintenance.py, src/knowledge_lattice/worker/runner.py, tests/conftest.py, tests/m2_worker_services.py, tests/test_auth_01_token.py, tests/test_cred_01_issue_put.py, tests/test_cred_02_consume.py, tests/test_cred_04_reclaim.py, tests/test_cred_05_e2e_agent.py, tests/test_e2e_03_reclaim.py, tests/test_e2e_06_mcp.py, tests/test_p3_followups_m1_4.py, tests/test_p3_followups_m2_1.py, tests/test_pg_backend.py, tests/test_pg_scaff.py, tests/test_r2_committer_fixes.py, tests/test_regress_m0a1_followups.py, tests/test_ret_01_recipe.py, tests/test_scaf_03_migrations.py, tests/test_task_01_lease.py, tests/test_task_02_retry.py, tests/test_task_03_cancel.py, tests/test_task_04_isolation.py, tests/test_v11_schema.py, tests/test_wk_inline_loop.py, tests/test_wk_maintenance.py]
endReason: null
createdAt: 2026-10-28T13:07:39+0800
updatedAt: 2026-10-29T09:36:37+0800
---

# task-knowledge-lattice-m2-1: M2.1 worker 子进程化 + 任务租约/重试/取消 + maintenance 调度框架（M2 主线第一段）

## 任务原文

**需求**（design.md §8 M2.1 + §5.3 任务状态机 + §3 worker/maintenance 模块，v0.9.5；requirements §8 M2.1 行对齐。**M2 系列第一段，串行起点——M2-S1 语义轨道与管理面任务端点均依赖本段交付的 worker 任务框架**）：

**A. worker 子进程化**（design §2/§3/§5.3——anything-llm 最小进程隔离样板）：

1. `worker/runner.py` 任务执行循环 + `worker/ipc.py` 与主进程的唤醒协议（unix socket / stdin，design §2 部署图）——**IPC 唤醒 + 兜底轮询**双通道；任务状态机 `pending → leased → running → (done | failed)`（design §5.3）
2. **心跳与租约**：running 任务每 5s 更新 `heartbeat_at`、租约 60s（`lease_until`——§4 tasks 表既有列）；租约过期任务可被重认领；worker 崩溃后任务不丢（TC-TASK-01、TC-E2E-03 杀进程演练半句——M2 部分）
3. **重试上限**：`attempts ≥ 3` 转 failed 留人工、error 字段落原因（TC-TASK-02）；断点粒度 = 阶段（各阶段幂等，重跑从上一完成阶段续——既有 IngestService 阶段编排原样迁移）
4. **子进程隔离**：注入使 worker OOM 的解析任务 → 仅 worker 子进程死亡、主进程检索可用、worker 自动拉起（TC-TASK-04）；任务执行从 app.py 进程内执行器迁入 worker 子进程（现有 `_run_maintenance_once` 调度器雏形与内嵌执行器收编/迁移，app.py 保留装配）
5. **任务取消**：`POST /api/orgs/{org}/tasks/{id}/cancel`（api/tasks.py）——任务在**阶段边界**停止、幂等续跑不复活、取消后文档状态一致不滞留 parsing（TC-TASK-03 全链）
6. **日志贯通**：worker 启动挂 log.py 同套 handler、task_id 进 contextvars（design §3 v0.8.5 既有口径——主进程侧已落，worker 侧随本段补齐）

**B. 写竞争治理 + maintenance 调度框架**（design §5.3 NFR-9 + §3 maintenance 任务类型）：

1. SQLite 写竞争治理：`busy_timeout` + worker 短事务分批提交口径落实（查询级审计异步写、权限事件走 outbox 的**口径注记**——outbox 本体归 m2-2，本段不实现 outbox）
2. maintenance 任务族**框架**：周期调度迁入 worker 任务模型（app.py 内嵌调度器投递 maintenance 任务的形态保留，执行体进 worker）；本段落地三个任务体：**未消费凭证回收**（M1-3 已有实现收编进 worker）、**过期成员物理清理**、**tombstone 90 天物理清理**（design §3 清单）；**审计月库滚动/备份快照/sem_chunk_entities 对账的任务体不在本段**（分别归 m2-2 / M2-S3，框架预留 type 分发位）
3. maintenance 任务行保留策略（m1-3 移交 P3-19）：done/failed maintenance 行不无限累积（保留条数/天数上限，简单策略即可）

**C. embed 回写防护确认**（design §8 M2.1 尾项——M1 已按 #42 必修2 实现：`AND embedding IS NULL AND embed_model=:batch_label`）：本段仅**确认既有实现随 worker 迁移后语义不变**（TC-VER-06/TC-EMB-06 既有断言复跑），不重做。

**承接遗留事项**（并入本段处理，含相应测试用例更新）：

1. **并发真用例与租约**（m1-5 轮次记录移交 M2；m1-2 P3-7/P3-B「真实并发窗口用例——合并并发面收口、租约落地后统一」）：租约机制落地后补**真实并发窗口用例**（两执行器竞争同任务恰好一人认领、租约过期重认领不双跑）——TC-TASK-01/TC-E2E-03 承载
2. **m1-2 P3-8 fetch window clamp**（移交 M1-4/M2）：fetch 窗口钳制评估或实现（与 worker 迁移无耦合，顺手清偿或明确再移交）
3. **m1-3 P3-6/P3-10/P3-11 并发与资源面**（移交 M2「并发 PUT .part 共用 / PUT 整体读内存 / 极窗口文档保留」）：随本段并发面收口一并评估处理——属实则修、不属实则记录核销（注：这三项在 m1-3 检查点已标「部分由凭证制 PUT 重做收口」，先核对现状再动手）

**口径与边界**：

- 存量门禁 **663+1 双后端双模式零回归**是硬约束——现有测试大量直调 IngestService.run_task（进程内），迁移后测试形态改造（进程内直调保留为单测捷径或改走 worker，由 coder 按 design §3 分层定，TC-ING-02 口径句「M2 子进程化后=杀 worker」同步生效）
- docs/ 正文不改（无决策变更）；TEST-CASES 活文档回写由 supervised-coding 落笔（coder 禁改 docs/）
- worker 生命周期与部署形态遵循 D2 零中间件：单主进程 + 单 worker 子进程，无新外部依赖
- commit 格式 `[task-knowledge-lattice-m2-1] R<n>`，develop_opencode 分支，commit 前同步 origin/develop，不 push
- 新测试文件按模块前缀命名（task_ / wk_ / e2e_ 等），新建前 `git ls-files tests/` 查同名（M0a-3 流程改进登记）

**验收标准**：

- TC-TASK-01 心跳与租约：5s 心跳更新、60s 租约、过期重认领（含真实并发窗口用例——两执行器竞争恰一人认领）
- TC-TASK-02 重试上限：attempts ≥ 3 → failed 留 error 原因
- TC-TASK-03 任务取消：阶段边界停止、幂等续跑不复活、文档状态一致
- TC-TASK-04 子进程隔离：OOM 只杀 worker、主进程检索可用、自动拉起
- TC-E2E-03 杀进程演练半句（M2 部分：杀 worker 后任务经租约重认领续跑、文档可达 searchable_full）
- maintenance 框架 + 三任务体（凭证回收/过期成员清理/tombstone 90 天清理）+ 任务行保留策略
- 承接遗留 1/2/3 处理完毕或明确再移交（含测试）
- 门禁 663+1 起、双后端双模式全绿 0 skipped（新增用例计入）

## 需求确认

- [x] 用户已确认（2026-10-28 13:09「同意」——status=implementing）
- 历史遗留事项清单：并发真用例与租约（m1-5/m1-2 移交，本段 TC-TASK-01/TC-E2E-03 承载）；m1-2 P3-8 fetch window clamp；m1-3 P3-6/P3-10/P3-11 并发与资源面收口；m1-3 P3-19 maintenance 任务行保留策略。其余 M2 去向移交项（管理面组/SSO 组/审计清理备份组/G-6 halfvec 复测/G-8 复验/T19·T20 半句等）按段属 m2-2~m2-5 与语义轨道段，不在本段

## 遗留事项（跨任务移交）

**本段已清偿**（来源任务检查点勾选由 supervised-coding 回写）：
- [x] 并发真用例与租约（m1-5 轮次记录/m1-2 P3-7·P3-B 移交——TC-TASK-01/TC-E2E-03 承载，claim 原子双臂 + barrier 真并发恰一 winner）
- [x] m1-2 P3-8 fetch window clamp（FETCH_WINDOW_MAX=10 钳 [0,10]）
- [x] m1-3 P3-6/P3-10/P3-11 并发与资源面（staging 随机后缀/流式复验+64KB 拷贝/输家补偿删孤儿——全修）
- [x] m1-3 P3-19 maintenance 任务行保留策略（天数+条数截尾）

**新移交 m2-2**（来源 = 本任务 R1~R4 各轮 Committer/Tester 意见，Committer R4 §四 终态清单）：
- [ ] **e2e_03 同族轮询**：`test_e2e_03_reclaim.py:141` 的 `done/failed OR full` → AND；与 P3-N14（subprocess flag 竞态 + supervisor.proc 观察窗）合并改造（工厂「首任务必 crash/必慢」或 flag 先写）——R4 首轮门禁一次负载偶发、历史 8+ 次全量零复现，方向明确成本极低（**m2-2 首个 commit 顺带**）
- [ ] **RUNBOOK 0005 注记**：存量 `target_version=NULL` 任务取消/耗尽清扫只落任务行、文档侧不触碰（可能残留 parsing，需人工/重传）；run_task 回退 `_effective_version`（P3-N3）
- [ ] worker_mode 两处字面量（config.py:97/:158）收敛模块级常量（P3-N10 附带）
- [ ] P3-N2：P1 集成测试 real_switch 线程绑定/静默吞错——补强测试保真度
- [ ] P3-N4：per-claim worker_id（inline 同 runner kick/loop 共享 id）
- [ ] P3-N5：create_document 目标版本计算移入 _start_overwrite 并返回（闭合 pending==active 理论碰撞窗口）
- [ ] P3-N6：created_before 秒级粒度文档化（poll<1s 按 ~1s 生效）
- [ ] P3-N7：fail_exhausted_tasks 每轮零行 UPDATE 的 SQLite 写事务开销（可节流）
- [ ] P3-N8：target_version 入 API payload
- [ ] P3-N9：PG 后端 app/worker 接线归 m2-2（.env.example/RUNBOOK 注明当前仅 sqlite）
- [ ] P3-N10：数值配置校验（poll/lease/attempts/keep 负值）
- [ ] P3-N11：MAINTENANCE_BODIES 注册表/措辞
- [ ] P3-N12：_worker_env 完整性（embed_model/batch/quality_llm/upload_*/log_*）
- [ ] P3-N13：supervisor 指数退避 + stop join monitor + 旧 stdin fd 释放
- [ ] P3-N15：流式拷贝孤儿（P3-12）/ overwrite 输家残余（P3-13）/ trim 事务+tiebreaker（P3-14）/ maintenance 大 DELETE（P3-15）/ 取消审计事件（P3-17）/ 调度去重投递（P3-18）
- [ ] P3-N16：_write_extra_v4 名实更正；P3-N17：main() 非法 worker_mode 专测；P3-N18：inline 测试 claim 竞态
- [ ] P3-R4-1：update_task(failed) 条件写/owner 守卫（取消 vs 失败落账 µs 窗口）
- [ ] P3-R4-2：completed 路径清 active_error（full active 残留 error）
- [ ] P3-R4-3（可选）：P2-N1 场景 A 的 v2 块强断言
- [ ] R1 接受的记录项维持：双探针 2×/周期（m2-2 可 gate 共享）、outbox/其余 executor 分发位、Tester P3-c/P3-d（pg 单连接并发/顺序交错）
- [ ] P3-R4-4：本检查点 R4 轮次记录「P3-N 零触碰」措辞应读作「P3-N2~N18 零触碰 + N1(=P3-x′) 授权修复」（存档不改原文，以此更正）

## 轮次记录

- **R1 coder 返回（2026-10-28 14:37）**：coderTaskId=ses_e7f1590aaffe6puZo9qaiEbDsL；commit `d1aa293`（d1aa2933fbccbfcab8426db6d7661363042353db，develop_opencode、基于最新 origin/develop、未 push）。**交付**：worker 子进程化（runner.py TaskRunner 原子认领/心跳线程/type 分发/重试预算 + Supervisor 拉起 + stdin 唤醒 ipc.py + 双模式 LATTICE_WORKER_MODE inline/subprocess）；取消端点 + 阶段/批次边界 lost_lease 退出；maintenance 三任务体 + 保留策略 + 0004 迁移（tombstoned_at 双方言）；backend 补 6 方法（claim 原子性：sqlite 单语句子查询重估 / pg FOR UPDATE SKIP LOCKED）。**自测**：门禁 **720+1 双后端双模式 0 skipped**（存量 663+1 → +57 新用例；pg 臂 252）；TC-TASK-01=12p（含真实并发窗口：两执行器 barrier 竞争 3 轮恰一人认领）/02=12p/03=11p/04=1p（真实 subprocess SIGKILL）/TC-E2E-03=1p（kill -9 重认领 attempts==2 达 searchable_full）；maintenance=10p；C 组复跑 72p（write_embeddings 防护谓词零改动确认）。**承接遗留全清**：①并发真用例（claim 原子 + 恰一人认领断言）②P3-8 fetch window 钳 [0,10] ③P3-6/10/11 核对属实全修（staging 随机后缀/流式复验+64KB 拷贝/输家补偿删孤儿文档）。**移交申报 5 项**：worker 模式默认 inline（生产显式 subprocess——.env.example 登记）、双探针流量 2×/周期（m2-2 可收口 gate 共享）、outbox/其余 executor 分发位归 m2-2、tombstoned_at 存量回填自迁移时点起算（RUNBOOK 升级注意）、TC-ING-02 口径句在 inline 模式下中断缝仍为进程内重启（TEST-CASES 回写时注明模式条件——supervised-coding 落笔）。**验证证据小节完整，待 Tester。**
- **Tester R1（2026-10-28 14:56，ses_e7ec33135ffe1lyeKo27eKIKWu）：PASS**。独立复跑门禁 720+1 双模式 0 skipped（pg 臂 252）；+57 增量逐文件对账闭合（7 新文件 57 collected，6 存量文件 def test 计数不变零删除）；TC-TASK-01~04/TC-E2E-03/maintenance/承接遗留 3 项/C 组防护逐条独立证据（断言真实性核实：真 Barrier 并发恰一 winner、真实 subprocess SIGKILL、真 send_signal 杀 worker 全链、防护谓词 diff 零命中）；docs/ 零触碰实跑确认；存量零弱化（test_cred_02 反而加强、test_pg_backend 新增 running 不重复计断言）。**4 项 P3 不阻断**：P3-a 0004 回填缺直接断言（建议 m2-2 顺带补用例）/P3-b coder 申报 72p 文件集不可复现（关键事实已独立成立，下轮申报附清单）/P3-c pg 臂真并发用例两线程共享单连接（SKIP LOCKED 已覆盖、双连接真竞争仅 sqlite 具备——可归后续）/P3-d P3-6/P3-11 为顺序交错模拟（不变量级断言语义成立，如实记录）。testedSha=d1aa2933fbccbfcab8426db6d7661363042353db。意见原文存「最新验证意见原文」节。
- **Committer R1（2026-10-28 15:18，ses_e7eb24ce7ffe9GodZ4GSWxH3p7）：NEEDS_CHANGES**。审查基线 HEAD(d1aa293) vs 2ee115e（34 files +3039/−159）；docs/ 零触碰✓；分层纪律✓（SQL 全下沉双方言）；任务书 A/B/C 边界 PASS（outbox 未实现仅注记符合边界、write_embeddings 零改动）；迁移 0004 双方言等价✓。**P1×1**：P1-1 取消×切换/首传 D20 切换竞态——cancel 事务外 stale read pending_version，切换先行则 UPDATE 零行但 DELETE chunks 无条件执行，删掉刚切为在用的版本块（active_status=searchable_full 但全文零块）；修法=set_doc_pending_failed 双方言按 rowcount 守卫（零行即不删块）+ 回归双后端。**P2×7**：P2-1 终态写入无所有权守卫（取消被 done 覆盖/丢租约执行器覆盖新持有者）/P2-2 崩溃耗尽 attempts 任务滞留 leased 不转 failed（需过期耗尽清扫）/P2-3 取消按文档当前 pending 落失败——canceling 旧任务误杀新版本上传（根因 tasks 表无 target_version，需边界裁定 B）/P2-4 worker 默认装配按 LATTICE_PG_DSN 选 PG 而 app 恒 sqlite——split-brain/P2-5 subprocess 模式 quality LLM 恒 Noop 与 app 装配分叉/P2-6 runner 心跳测试空洞断言（sqlite 非线程安全 backend 心跳线程抛错被吞、断言恒真）/P2-7 inline 兜底循环只领 maintenance——重启后遗留 ingest 任务滞留（inline 是默认模式）。**P3×18**（P3-1 回填断言/P3-2 filesChanged 清单更正——**supervised-coding 已执行：27→34 项**/P3-3 env 模板漏 2 项与校验/P3-4 supervisor 退避与 stop join/P3-5 _worker_env 字段漂移（embed_model 漂移致向量标签永不被查询）/P3-6 MAINTENANCE_BODIES 注册表不存在/P3-7 LATTICE_WORKER_SERVICES 未文档化/P3-8 subprocess 测试 flag 竞态 flaky/P3-9 fake embedder 标签不保真（subprocess E2E 检索命中实为 FTS-only）/P3-10 取消覆盖缺 overwrite 有块场景/P3-11 TC-VER-08 口径与 RUNBOOK 回写（supervised-coding 落笔）/P3-12 流式拷贝失败留半截对象/P3-13 overwrite 输家补偿残余/P3-14 trim 非 PG 同事务无 tiebreaker/P3-15 maintenance 大 DELETE 占写锁/P3-16 注释笔误×3/P3-17 取消无审计事件（对照 FR-6）/P3-18 调度器无去重投递）。**需求边界 A~D**：A worker_mode 默认 inline vs 生产 subprocess（TC-TASK-04 隔离保证按默认部署不成立）——用户裁定；B tasks.target_version 列（根治 P2-2/P2-3）vs 最小守卫+登记——用户裁定；C TC-VER-08 造数口径回写（tombstoned_at 为基准）——supervised-coding 落笔不改实现；D fetch clamp [0,10] API 口径登记——supervised-coding 落笔。**status=spec_confirm 待 A/B 裁定；裁定后 round→2 发 coder R2（P1-1+P2×7+P3 顺手项）。意见原文存「最新验证意见原文」节。**
- **边界裁定（2026-10-28 15:2x 用户「按你的建议执行」）**：**A=(a) 默认 `subprocess`**（生产 fail-safe、符合 NFR-1 部署形态；测试显式 inline——P2-4 split-brain 修复随行）；**B=(a) `tasks.target_version` 列**（迁移 0005 双方言 + ingest 创建任务写入目标版本，cancel/耗尽清扫按该版本落 failed——同时根治 P2-2/P2-3）；**C/D 无异议**——supervised-coding 落笔。**round→2、status=implementing、reviewedSha 置空；coder R2 范围：P1-1 + P2-1~7（P2-3/P2-2 按 B=(a) 实施）+ P3 顺手项（P3-1/P3-9/P3-10/P3-16 等）。**
- **docs 批落笔（2026-10-28 15:26，supervised-coding 执笔——工作区，随 R2 修复批原样 commit）**：TEST-CASES v1.8.1（TC-VER-08 造数口径回写 tombstoned_at 基准 / TC-VER-05 补 FETCH_WINDOW_MAX=10 钳制口径 / TC-ING-07 补 worker 双模式中断条件）+ RUNBOOK §3 补 0004 升级注记（存量回填=迁移时点起算、保守窗口）。**R2 coder 须将此 2 文件原样 commit（doc-only commit 或随修复批，禁改内容）。**
- **R2 coder 返回（2026-10-28 16:22，续接会话）**：commits `7684880`（docs 批原样入库——supervised-coding 执笔 2 文件）+ `fd979ac`（fd979ac04e3aca585ea2346936d35ea34ba4d9，修复批——origin/develop 已同步、未 push；HEAD=fd979ac）。**修复**：P1-1 双方言 rowcount 守卫 + 确定性并发回归；P2-1 终态前/except 首行 should_continue + _on_failure done/owner 守卫 + worker_id 唯一化 + update_task done 非终态守卫；P2-2 fail_exhausted_tasks 清扫（每轮、类型过滤前）+ 文档侧按 target_version 收尾；P2-3 迁移 0005 tasks.target_version 双方言 + cancel/_fail 按任务目标版本（存量 NULL 行回退旧口径）+ _guard_alive 按 target_version；P2-4 store/factory.py build_backend 共享（DSN 告警不 split-brain）；P2-5 build_quality_service 共享工厂；P2-6 心跳测试重写（ThreadLocalBackend + 双采样前进断言）；P2-7 inline 兜底循环全类型（陈旧口径 created_before + kick 上限 1024）；**A 裁定落地**：默认 subprocess + 10 处 app 测试显式 inline + worker_mode 非法值 fail-closed；顺手项 P3-1（回填直断言双臂）/P3-9（embed_model 对齐——subprocess E2E 向量路真实验证）/P3-10（overwrite 有块取消直断言）/P3-16（笔误×3）/P3-3 部分（env 模板补 2 项）。**自测**：门禁 **745+1 双后端双模式 0 skipped**（720→+25：task_02+10/task_03+8/wk_inline_loop+5/回填 sqlite+pg 各 1；pg 臂 262）；C 组申报附文件清单（5 文件 100p，防护谓词仍零改动）。**移交申报 4 项**：0005 前存量行 target_version=NULL 回退口径（RUNBOOK 可补一句）/_on_failure failed→failed 覆盖窗口（双层拦截已够、记录）/P2-7 陈旧口径秒级粒度（poll<1s 按 ~1s 生效）/P3-4~18 记录项未展开。**验证证据小节完整（含专项文件清单），待 Tester R2。**
- **Tester R2（2026-10-28 16:57，续接会话）：FAIL**（唯一 P2 阻断）。门禁 745+1 双模式 0 skipped 独立复跑✓、+25 逐文件对账闭合✓（test_r2_committer_fixes 17→17 零新增属配置改、申报无误）、C 组 100p 实测✓；P1-1 守卫真实（Event 确定性交错非 sleep）✓、P2-1~5/P2-7 逐项核实为真✓、**P2-6 重写后具备可失败性（反证构造成立——心跳线程不跑则双断言必败）**✓、docs 批原样性✓、R1 四项 P3 闭环（a 修/b 附清单/c·d 记录）✓、回归面零弱化✓。**P2-A（FAIL 根因）**：A(a) 裁定 env 路径未生效——`config.py:158` get_settings fallback `worker_mode=env("LATTICE_WORKER_MODE", "inline")` 仍 inline，生产唯一启动路径（uvicorn factory 无参 → get_settings）默认实际 inline，与 dataclass 默认/.env.example 模板注释自相矛盾（旁证：其余 worker_* fallback 全部与 dataclass 一致、唯 worker_mode 漂移——遗漏非意图）；修法=一行 fallback 改 subprocess + 默认断言专测。**P3×3**：P3-x test_wk_inline_loop 两用例等待预算过紧（组合跑 ~4% 失败、重认领机制本身正常——deadline +10/+15→+60，TEST_BUG 转 coder）/P3-y 非法 worker_mode fail-closed 无专测/P3-z 存量 NULL target_version 回退无专测（与移交申报口径一致）。testedSha=fd979ac04e3aca585ea2346936d35ea34ba4d9。意见原文存「最新验证意见原文」节。**status=fixing→implementing、round→3（maxRounds=3 最终轮）。**
- **R3 coder 返回（2026-10-28 17:10，续接会话）**：commit `e02345b`（e02345b7f577882517996e98082df49a54422d9b，develop_opencode、origin/develop 已同步、未 push）。**修复**：P2-A——config.py:158 env fallback `"inline"`→`"subprocess"`（与 :97 数据类默认对齐，R2 半完成状态闭合；get_settings 无缓存直读 env，monkeypatch 隔离成立）；P3-x 两用例 deadline +10/+15→+60；P3-y 非法值 fail-closed 专测；P3-z NULL target_version 回退专测（双后端）。**自测**：门禁 **749+1 双后端双模式 0 skipped**（745→+4：P2-A 回归 1+P3-y 1+P3-z 双臂 2；pg 臂 263）；fallback 两侧一致实读（:97/:158）；波及面排查（其余 get_settings 调用点不受影响）。**申报**：P2-A 模式枚举仍两处字面量（:97/:158），建议 m2-2 卫生批收敛模块级常量。**验证证据小节完整，待 Tester R3。**
- **Tester R3（2026-10-28 17:24，续接会话）：PASS（终态）**。P2-A 三层独立验证（diff 单行无夹带 / 解释器直读生产路径 unset env → subprocess / 新用例无缓存假绿通道）；P3-y/z 断言真实（z 为 SQL 抹 NULL 双臂实跑）；门禁 **749+1 双后端双模式 0 skipped** 独立复跑、+4 对账闭合（pg 臂 263）；R3 diff 纪律面干净（2 文件、docs 零触碰、工作区纯净）。**P3-x′（test-only 不阻断）**：R2 的 P3-x 诊断不完整——真根因=轮询退出条件读序竞态（get_task/get_document 非原子双读，「切换已提交 full 可见、done 未落库」毫秒窗口采为 (running, full) → OR 条件提前 break），6+ 次全量门禁零复现、失败快照自证重认领机制正确；**精确补丁**（两用例退出条件 OR→AND + ①号用例 task 读入轮询体）随报告交付，随存档或 m2-2 首个 commit 落地；责任归属=R2 Tester 诊断「执行停顿」不全、coder 按处方如实执行、R3 深挖定位。testedSha=e02345b7f577882517996e98082df49a54422d9b。意见原文存「最新验证意见原文」节。**待 Committer R3 终审。**
- **Committer R3 终审（2026-10-28 17:38，续接会话）：NEEDS_CHANGES**。审查基线 HEAD(e02345b) vs R1 基线 d1aa293（增量 33 files + docs 批 7684880）。**R1 意见闭环判定**：P1-1/P2-1/2/4/5/6/7/P2-A/P3-1/2/9/10/11/16 全 CLOSED；P2-3 cancel/sweep 范围 CLOSED；边界 A/B 落地忠实（7684880 docs 批与 C/D 建议逐字一致无夹带）；update_task 条件写/0005 兼容/created_before 边界新风险扫描无存量破坏。**唯一阻断新发现 P2-N1**：`_record_doc_error`（ingest.py:627）未传任务 target_version——首传 T1 跑过 index_fts 后 embed 失败（网关不可达等典型失败）时重读文档看到并发覆盖上传的 pending v2 → set_doc_pending_failed(v2)+删 v2 块——**旧任务失败静默杀死并发新版本**（或将 active_error 写到新 active 版本）；系 R1 P2-3 同根因在失败路径的残留，B 裁定修复只覆盖 cancel/sweep；修法=run_task 传 version + _record_doc_error 三分支守卫（~5 行）+ 双后端确定性回归（首传失败不杀 v2/新 active 不被污染）。**P3-N1~N18 移交清单**（P3-x′ 补丁须落下一 commit、RUNBOOK 0005 注记、per-claim worker_id、create_document 版本计算窗口等）。**Committer 附出口**：若用户裁定 P2-N1 登记 known-gap 不阻塞交付可转 APPROVED（其余条件全满足）。**round=3=maxRounds 已达上限 → status=blocked（endReason=max_rounds）、停止循环、上报请示。**意见原文存「最新验证意见原文」节。
- **用户裁定（2026-10-28 17:41「a」= 授权追加 R4）**：**maxRounds 3→4、round→4、status=implementing、reviewedSha 置空、endReason 回 null**。R4 范围（刻意收窄）：P2-N1 修复（run_task 传 version + _record_doc_error 三分支守卫 + 双后端确定性回归×2）+ P3-x′ 测试补丁（两用例退出条件 OR→AND、①号 task 读入轮询体）。往返成因备注：R1 P2-3 处方与 B 裁定预案本身只覆盖 cancel/sweep 路径，失败路径残留系终审新挖出的处方缺口、非 coder 执行不到位。
- **R4 coder 返回（2026-10-28 17:53，续接会话）**：commit `830d6a7`（830d6a77c79653ffe622960aa6be6214d03a4b58，develop_opencode、origin/develop 已同步、未 push）。**修复**：P2-N1——run_task except 传 version + `_record_doc_error(*, version=None)` 三分支守卫（pending==version→T8 删块 / active==version→active_error / 均不匹配→不触碰；None 回退 _effective_version legacy 口径；set_doc_active_error 既有 WHERE active_version 谓词双方言核实天然对齐）；P3-x′——test_wk_inline_loop 两用例退出条件 OR→AND、①号 task 读入轮询体。**自测**：门禁 **753+1 双后端双模式 0 skipped**（749→+4：P2-N1 场景 A/B × 双臂；pg 臂 265）；场景 A（T1 embed 失败不杀并发 v2——v2 pending 保 parsing、块 0 删、t2 续跑至 full）/场景 B（v2 已切换后 T1 失败不污染 active_error）断言齐；wk_inline_loop 9p。**如实申报**：R4 首轮门禁常规模式 test_e2e_03_reclaim 出现一次负载偶发失败（subprocess 时序、单独复跑通过、第二轮双模式全绿）——其轮询条件与 P3-x′ 同族读序/预算问题，**移交 m2-2 套用同款 AND 条件**。P3-N 系列零触碰（按指示全量移交）。**验证证据小节完整，待 Tester R4。**
- **Tester R4（2026-10-28 18:04，续接会话）：PASS（终态）**。P2-N1 修复语义核实（三分支守卫 diff 实读 + set_doc_active_error WHERE active_version 谓词双方言核实双保险；场景 A/B 双臂断言方向全部对准「修后不误杀」——v2 块 0 删/pending_error None/active_error None，修前代码此场景必写，具真实杀伤力；Event 确定性非 sleep）；P3-x′ 补丁与 R3 报告逐字吻合 + **stress 实证竞态归零**（单文件 0/20、组合 0/10——R3 同模式复现率 ~1/8~1/15）；门禁 **753+1 双后端双模式 0 skipped** 独立复跑（+4 对账闭合、pg 臂 265）；R4 diff 纪律面零越界（P3-N 零触碰、docs 零触碰）。**e2e_03 偶发处置=接受移交 m2-2**（8+ 次全量零复现、R4 首轮负载首次、复跑过；与 P3-N14 合并处理）。**无新增问题。**testedSha=830d6a77c79653ffe622960aa6be6214d03a4b58。意见原文存「最新验证意见原文」节。**待 Committer R4 闭环复审。**
- **Committer R4 闭环复审（2026-10-28 18:11，续接会话）：APPROVED**。R4 增量 3 files +189/−12 与申报一致、docs 零触碰、P3-N2~N18 零夹带（N1=P3-x′ 系授权修复——coder 申报「P3-N 零触碰」措辞小瑕 P3-R4-4）；P2-N1 处方忠实（三分支守卫 :630-659 + set_doc_active_error WHERE active_version 谓词双方言 :1318/:1274 双保险 + _record_doc_error 唯一调用点核实向后兼容）；场景 A/B 断言修前必败三重杀伤力核实；P3-x′ 逐字补丁 + stress 归零；新风险扫描无新 P1/P2（P3-R4-1 update_task(failed) 条件写 µs 窗口 / P3-R4-2 completed 清 active_error / P3-R4-3 v2 块强断言可选——三项记录移交）；e2e_03 偶发处置接受；门禁 753+1 采信（R1 663+1 起全程 0 skipped、pg 臂 252→265）。**双通过达成：testVerdict=PASS（R4）+ reviewVerdict=APPROVED（R4）、reviewedSha=testedSha=HEAD=830d6a7 → status=approved，待用户确认交付。**遗留移交清单 23 项（m2-2 去向）已登记「遗留事项」节。意见原文存「最新验证意见原文」节。
- **交付确认（2026-10-29 09:26 用户「同意」）**：启动交付链——①Coder 同步 origin/develop + push develop_opencode + 开 PR（base=develop）②Committer gh pr review 留痕 ③Coder evidence manifest 入 PR description ④汇报合入请求（不自动合入）。**用户明示：交付链内部三步无需逐步确认（09:27）。**
- **交付①完成（Coder，2026-10-29 09:3x）**：同步 Already up to date（ff-only 干净）；push `2ee115e..830d6a7`（SSH）；**PR #2** 开立（https://github.com/yq3/knowledge-lattice/pull/2，base=develop，MERGEABLE/CLEAN，commits=5 逐一对应；body 含概览/验证/遗留/boundaryNote + Evidence Manifest 占位节）；监督侧文件未 push 未提交 ✓。
- **交付②完成（Committer，2026-10-29 09:32）**：`--approve` 被平台拒绝（self-approve——PR 作者=gh 认证用户 yq3，与 M1 系列 PR #54 同形态限制）；**回退以评审正文 COMMENTED 留痕成功**：review id `PRR_kwDOVZ9dhM8AAAABU0InhQ`（2026-10-29T01:32:20Z，锚定 830d6a7=PR HEAD），正文首行 APPROVED（R4 结论）+ 留痕说明（self-approve 限制显式注记）+ 全链闭环摘要 + R4 要点。审查结论不受影响（reviewVerdict=APPROVED）。
- **交付③完成（Coder，2026-10-29 09:35）**：Evidence Manifest JSON 入 PR #2 description（占位节替换、JSON 解析通过、双 SHA 对齐核验、body 其余内容逐字节一致）；PR 终态 OPEN/MERGEABLE/CLEAN。**交付链三步完成——待用户合入 PR #2（不自动合入）。合入后：supervised-coding 落 §六 M2 行本段完成态注记（TC-TASK-01~04/TC-E2E-03 等证据指针）+ 下一段 m2-2（审计 outbox/清理/备份——检查点另建，承接本段 23 项移交清单）。**
- **合入完成（2026-10-29 09:36 用户指令「合入」）**：PR #2 state=**MERGED**，mergedAt=2026-10-29T01:36:22Z，mergeCommit=`739bbf3d26edc50ae8ce1e5407759cfb31fdc319`；origin/develop 前进 `2ee115e..739bbf3`（5 commits 全量入库）。**m2-1 正式完成（done）。**收尾：①supervised-coding 落 §六 M2 行 m2-1 段完成态注记（TEST-CASES v1.8.2——工作区，随 m2-2 docs 批入库）②来源检查点（m1-2/m1-3/m1-5）清偿注记回写。下一段 m2-2（检查点另建）。

## 最新验证意见原文

- 意见原文按块内时序排列：Committer R1 → Tester R2 → Tester R3 → Committer R3 终审 → **Tester R4**；**Tester R1（时序最早）因追加锚点顺序位于本节末尾**——恢复时按实际轮次时序（Tester R1 → Committer R1 → … → Tester R4）取用

<details><summary>Committer R1 报告原文（2026-10-28 15:18，ses_e7eb24ce7ffe9GodZ4GSWxH3p7）</summary>

# Committer R1 审查报告 — task-knowledge-lattice-m2-1

## 〇、基线核对与审查范围

- **HEAD** = `d1aa2933fbccbfcab8426db6d7661363042353db`（`develop_opencode`，`git rev-parse` 核对）；父提交 `2ee115e` = `origin/develop` 当前值（同步成立）；工作区仅监管侧文件 `M .opencode/agent/supervised-coding.md` + `?? .opencode/workflows/task-knowledge-lattice-m2-1.md`，被测代码 = HEAD 纯态。
- **审查 diff** = `git diff d1aa293^..d1aa293`：34 files，+3039/−159；`docs/` 零触碰（`git diff ... -- docs/` 空）。
- **R1 无上一轮 Committer 意见**；已核对 Tester R1 的 4 项 P3 处置/表态（见 §五），以及任务书承接的 m1-5/m1-2/m1-3 三项遗留（真并发用例/P3-8 clamp/P3-6·10·11）。
- **审查限制**：本会话 bash 仅放行 git/gh 只读命令，**未独立复跑 pytest**；门禁证据采信 Tester R1 的 720+1 双模式 0 skipped 输出 + 静态审阅。静态计数与 Tester 一致（663+1 → +57 = 720+1；新 7 文件 57 collected；6 个存量测试文件仅基线顺延、`test_cred_02` 为加强；无新增 skip/xfail/删除）。
- **清单完整性问题（不阻塞代码结论，交付前须更正）**：frontmatter `filesChanged` 27 项 vs HEAD diff **34 文件**——漏 `src/knowledge_lattice/worker/__init__.py` 与 6 个存量测试文件（`test_cred_02_consume` / `test_pg_backend` / `test_pg_scaff` / `test_regress_m0a1_followups` / `test_scaf_03_migrations` / `test_v11_schema`），且 `tests/fixtures/m2_worker_services.py` 路径写错（实际为 `tests/m2_worker_services.py`）。详见 P3-2，由 supervised-coding 更正。

---

## 一、审查清单逐项结论（证据 = 行号/diff hunk）

| # | 项目 | 结论 |
|---|---|---|
| 1 | 分层纪律 | **PASS**：新增 SQL 全部在 `store/sqlite/backend.py` / `store/postgres/backend.py`（claim 1069-1110 / 1046-1085、heartbeat、cancel、清理三方法）；core `ingest.py` 只经 backend 协议；worker 无 SQL；`taskclock` 属 store。`auto_entities` 本段不涉及。 |
| 2 | 任务书 A/B/C 边界 | **PASS（附注）**：A 组 6 项齐备（IPC stdin + 兜底轮询、状态机、5s/60s、attempts 认领递增、子进程隔离、取消、contextvars）；B 组三任务体 + 保留策略 + app 调度器投递；outbox 仅注记未实现（`worker/runner.py:23-25`，符合边界）；C 组零改动（`git diff -S write_embeddings` 空）。注：`worker/maintenance.py:14-17` 声称的 `MAINTENANCE_BODIES` 注册表不存在（P3-6）；B.1 busy_timeout 沿用连接工厂既有实现。 |
| 3 | 迁移 0004 等价性 | **PASS**：双方言均 `ADD COLUMN + 回填 UPDATE + 部分索引`（sqlite 8-11 / pg 7-8）；sqlite `user_version`、pg `schema_migrations` 基线前进（测试同步）；回填起点=迁移时点，保守窗口语义正确（旧 tombstone 延后清理，无提前删除风险）。P3-1 回填缺直接断言；P3-11 TC-VER-08 文档口径需回写。 |
| 4 | 并发正确性 | **FAIL（P1×1 + P2×3）**：claim 原子性双方言实现正确（sqlite 单语句子查询重估 / pg SKIP LOCKED + READ COMMITTED 重估）；心跳线程与执行线程交互基本正确；但 **取消×切换/插入事务存在删除在用版本块的竞态（P1-1）**、终态写入无所有权守卫（P2-1）、崩溃耗尽 attempts 不转 failed（P2-2）、取消误伤新旧版本（P2-3）。 |
| 5 | worker 双模式语义 | **PARTIAL**：执行体共享 `TaskRunner`/`IngestService`（PASS）；但生产装配与 app 分叉：worker 按 `LATTICE_PG_DSN` 选 PG 而 app 恒 sqlite（P2-4）、quality LLM 客户端硬编码 Noop 而 app 按 `quality_llm` 选（P2-5）；`LATTICE_WORKER_SERVICES` 是通用扩展点（非仅测试），env 可控、无安全问题，但未文档化（P3-7）。 |
| 6 | 生产面风险 | supervisor 有固定 1s 退避（非指数/上限，P3-4）；monitor 线程 stop 时未 join，存在关停竞态（P3-4）；maintenance 周期投递 + worker 认领交互正确（`test_cred_04` 已覆盖 inline 全链）；stdin EOF 自感知正确；config 默认值合理但缺校验、`.env.example` 漏 2 项（P3-3）。 |
| 7 | coder 移交申报 5 项 | ① 默认 inline → **需求边界问题（A）**；② 双探针 2×/周期 → **接受**（POC 量级，m2-2 可 gate 共享）；③ outbox/其余 executor 归 m2-2 → **接受**（runner executor 分发字典即预留位）；④ 回填自迁移时点 → **接受**（保守方向安全；须落 RUNBOOK/known-gaps，P3-11）；⑤ TC-ING-02 inline 条件 → **接受**（supervised-coding 回写模式条件）。 |
| 8 | 测试质量 | **PARTIAL**：57 新用例无新增 skip/弱化，断言总体真实（真 Barrier、真 SIGKILL、真 kill -9）；但 **runner 心跳测试为空洞断言（P2-6）**；取消覆盖缺 overwrite pending 有块场景/取消×切换竞态/崩溃耗尽；subprocess 测试有 flag 写入竞态与 fake label 不保真（P3-8/9）。 |
| 9 | 需求边界 | 有，见 §三。 |

---

## 二、问题清单（P1 阻断 / P2 重要 / P3 次要）

### P1-1（阻断）取消与「版本切换/首次上传 D20 切换」竞态会删除**在用版本**的全部 chunks（数据丢失）

- **文件**：`src/knowledge_lattice/core/docs/ingest.py:394-406`（cancel 的 stale read）+ `src/knowledge_lattice/store/sqlite/backend.py:516-538` + `src/knowledge_lattice/store/postgres/backend.py:498-519`（`set_doc_pending_failed` 无条件删块）。
- **问题**：`IngestService.cancel_task` 在事务外先 `get_document` 取 `fresh`，再调 `set_doc_pending_failed(doc, fresh["pending_version"])`。若在「读 fresh」与「执行 set 事务」之间，在途执行器完成了：
  - 覆盖上传的 `switch_active_version`（pending→active，清空 pending_version），或
  - 首次上传 `insert` 事务内的 D20 切换（同样清空 pending_version），
  
  则 `set_doc_pending_failed` 的 `UPDATE documents ... WHERE pending_version=:v` **零行**（pending 已清），但紧接着的 `DELETE FROM chunks WHERE doc_id=:doc AND version=:v` **无条件执行**——删掉的正是刚刚切为在用的版本块（chunk_vectors 随 FK 级联删、FTS 触发器清空）。结果：`documents.active_status='searchable_full'` 但全文零块、检索/fetch 全空。此竞态在 SQLite 下尤其可达：cancel 的 `backend.cancel_task` 短写先提交，随后切换事务取得写锁并提交，cancel 的 `set` 事务再等待锁后执行；PG 下 cancel 的 `set` UPDATE 会等在切换事务的 documents 行锁之后，同样零行 + 删块。
- **修改建议**：
  1. 双方言 `set_doc_pending_failed` 改为「仅当文档仍指向该 pending 版本时才删块」：
     ```python
     cur = conn.execute(
         "UPDATE documents SET pending_status='failed', pending_error=:err, updated_at=CURRENT_TIMESTAMP"
         " WHERE id=:doc AND pending_version=:v", {...})
     if cur.rowcount == 0:          # 版本已切换/已清空/已被新版本取代——不得删块
         conn.execute("COMMIT"); return
     conn.execute("DELETE FROM chunks WHERE doc_id=:doc AND version=:v", {...})
     ```
     （PG 同构加 `cur.rowcount` 判断；`BEGIN`/`BEGIN IMMEDIATE` 事务不变。）
  2. 该守卫同时保护 `_record_doc_error` 在丢租约/并发切换下的同类误删。
  3. **补回归（双后端）**：先跑完首次上传（或覆盖上传）使版本切为 active，再以该版本号调 `set_doc_pending_failed(doc, v)` → 断言 `delete_by_doc(doc, v)` 仍 >0、`active_status` 不变；并加一条确定性并发用例（monkeypatch `switch_active_version`/`insert` 在切换前发信号 → 取消 → 放行切换 → 断言在用块保留、任务 failed）。

---

### P2-1（重要）终态写入无所有权/吸收态守卫：取消可被 `done` 覆盖；丢租约执行器可覆盖新持有者/已完成状态

- **文件**：`core/docs/ingest.py:551`（`update_task(done)`）、`:557-569`（except 写 failed + `_record_doc_error`）、`worker/runner.py:188-210`（`_on_failure`）。
- **问题**：
  1. `_run_stages` 在最后一次 `_alive()` 检查后进入 `_quality_stage`（detect 可能较慢），期间取消把任务置 failed；`run_task` 随后无条件 `update_task(status="done")`（且 `update_task` 会清 error）→ **取消终态被 done 覆盖**，API 已返回 `cancelled:true` 但任务最终 done。
  2. 丢租约后执行器的 stage 抛异常：except 只判断了 `failed + 'cancelled:'`；若新持有者已把任务置 done/running，旧执行器仍写 failed + `_record_doc_error` → 覆盖新持有者状态/文档状态。
  3. `_on_failure` 只判 `fresh["status"] != "failed"`，会覆盖 done；且未校验 `lease_owner`（inline 多执行器共用 `wk-{pid}`，无法区分）。
- **修改建议**：
  1. `run_task` 在 `_run_stages` 返回 `"completed"` 后、`update_task(done)` 前：`if should_continue is not None and not should_continue(): log lost_lease; return`（不写终态、不写文档）。
  2. `run_task` 的 `except` **首行**同样检查：`if should_continue is not None and not should_continue(): log lost_lease; return`（丢租约/取消后不写 failed、不 `_record_doc_error`）。
  3. `_on_failure`：`if fresh["status"] == "done": return`；`if fresh.get("lease_owner") not in (None, self._worker_id): return`；保留现有 cancelled 判断。
  4. 若要闭合 `检查→UPDATE` 的最后一跳，给 backend 增加条件终态写（`finish_task(task_id, worker_id, status, error)`，`WHERE status IN ('leased','running') AND lease_owner=:w`），或在 `update_task` 仅对 `done` 加 `AND status IN ('pending','leased','running')`（存量测试均从非终态写 done，已核对不破坏）。
  5. inline 模式建议 worker_id 用每 runner/每 claim 唯一值（如 `wk-{pid}-{uuid}`），否则同进程重认领时 owner 检查失效。
  6. **补测试**：(a) 阻塞 `_quality_stage` 时取消 → 任务保持 failed/cancelled；(b) `_on_failure` 对已 done 任务调用 → 保持 done；(c) 丢租约后 stage 抛错 → 新持有者状态不被覆盖。

---

### P2-2（重要）崩溃耗尽 attempts 后任务永久滞留 leased/running，不转 failed（违背验收「attempts ≥ 3 转 failed 留人工」）

- **文件**：`store/sqlite/backend.py:1090-1098`、`store/postgres/backend.py:1064-1068`（`attempts < max` 才可认领）；`worker/runner.py:95-115`（认领循环）、`:204-205`（仅执行器异常路径判 attempts）。
- **问题**：`attempts` 在认领时递增（口径正确），但 crash 路径没有「耗尽→failed」的收尾：claim(1) → kill → 过期 → claim(2) → kill → 过期 → claim(3) → kill → 过期后 `attempts=3`，claim 的 `attempts < max` 永远 False → 任务滞留在 `leased/running`，无 error、无 failed，人工不可见；若在 parse 之后崩溃，文档还会停在 pending parsing，覆盖上传被 409 锁死。TC-TASK-02 只覆盖执行器抛异常路径，TC-TASK-04/TC-E2E-03 只杀一次，未覆盖该耗尽路径。
- **修改建议**：
  1. 在 `claim_next_task`（双方言）候选语句前增加「过期且耗尽」清扫（或独立 `fail_exhausted_tasks(now, max_attempts)`，由 `TaskRunner.run_once` 每次调用）：
     ```sql
     UPDATE tasks SET status='failed',
       error='attempt limit exceeded (lease expired after N attempts — worker crash?)',
       updated_at=:now
     WHERE status IN ('leased','running') AND attempts >= :max
       AND lease_until IS NOT NULL AND lease_until <= :now
     ```
     清扫必须放在类型过滤之前（inline 兜底循环只领 maintenance 时也要执行）。
  2. 文档侧：耗尽任务若仍持有 pending 版本，应落 pending failed + 删块；**这需要 task→version 关联**（见 §三-B），本轮至少先把任务行置 failed/error 留人工，并在 known-gaps/检查点登记文档侧残留。
  3. **补测试**：模拟 claim→过期 3 轮不执行，第 4 次 claim/清扫后断言 status=failed、error 含原因、claim 返回 None。

---

### P2-3（重要）取消按「文档当前 pending 版本」落失败，canceling 旧任务会误杀新版本上传

- **文件**：`core/docs/ingest.py:394-406`；`tasks` 表无 target version 列（`store/sqlite/migrations/docs/0001_schema_v1.sql:236-246` 仅 doc_id）。
- **问题**：`cancel_task` 用 `fresh["pending_version"]` 而非被取消任务的版本。确定性场景：
  1. 首次上传任务 T1 跑到 `stop_after="index_fts"`（active v1 lexical，pending=None，T1 仍 running）；
  2. 发起覆盖上传 v2 → pending v2 + 任务 T2（start_overwrite 允许，因 pending 为 NULL）；
  3. 取消 **T1** → `backend.cancel_task(T1)` 成功，随后读到 pending v2（parsing）→ `set_doc_pending_failed(v2)` + 删 v2 块 → **T2 的新版本被旧任务的取消误杀**；T2 随后在 `_guard_alive` 处被判「cancelled」。
  
  这是取消语义「按 task_id 取消该任务」的明显违反，且与 P1-1 无关（v2 尚未切换）。
- **修改建议**：需要 task→目标版本关联才能根治（`tasks.target_version` 列，创建 ingest task 时写入 v1/vN；迁移 0005；cancel/sweep 均按该版本落 failed）；见 §三-B 的需求边界裁定。若暂不加列，至少加「被取消任务是否为该文档最新非终态任务」守卫（**注意 `created_at` 只有秒级、UUID 不可排序，需新增可排序序列或版本列，单纯 created_at 不可靠**），并在 known-gaps 登记窗口。**补测试**：上述 T1-running + v2-pending 场景取消 T1 → v2 保持 parsing、T2 仍可执行；取消 T2 → v2 failed + 块删除。

---

### P2-4（重要）worker 默认装配按 `LATTICE_PG_DSN` 选 PG，而主 app 恒 sqlite → 生产/门禁环境 split-brain

- **文件**：`worker/runner.py:342-352`（`dsn = os.environ.get("LATTICE_PG_DSN")` → `PgBackend`）；`app.py:176-179`（`connect/migrate_db/ThreadLocalBackend` 恒 sqlite）。
- **问题**：`.env.example:9-11` 明确把 `LATTICE_PG_DSN` 作为 PG 后端开关，门禁脚本也全局 export 该变量。若操作者/开发者在同一 shell 以 `LATTICE_WORKER_MODE=subprocess` 启动 app 且未注入 `LATTICE_WORKER_SERVICES`，父进程写 sqlite、worker 子进程连 PG：任务永远不被处理，文档/任务分离。docstring 声称「镜像 app.py 的 backend 构造」与实际不符。
- **修改建议**：`build_default_services` 与 `app.py` 共用同一后端工厂（建议 `Settings.storage_backend` 或共享 `build_backend(settings)`，两者同时迁移）；在 app 尚未支持 PG 前，**移除 worker 的 DSN 自动分支**（恒 sqlite）或 fail-closed 报错「PG 后端未接线」。补测试：设置 `LATTICE_PG_DSN` 时 worker 默认装配仍与 app 同后端（或明确拒绝启动），不产生跨库。

---

### P2-5（重要）subprocess 模式 quality LLM 客户端静默降级为 Noop（与 app 装配分叉）

- **文件**：`worker/runner.py:337-340,364-366`（恒 `NoopKeywordGenerator()`）；`app.py:211-217`（`quality_llm == "none"` 才 Noop，否则 `OpenAICompatKeywordGenerator`）。
- **问题**：任务执行迁入 worker 后，subprocess 部署下 `LATTICE_QUALITY_LLM=openai` 的 LLM 关键词兜底实际永远不会调用（worker 的 IngestService 是真正执行体）；inline 模式反而正确。这是「测试态与生产态分叉」的典型。
- **修改建议**：worker 镜像 app 的选择，或抽公共 `build_quality_service(backend, settings)` 供 app/worker 共用（推荐，防再次漂移）。补一条工厂单测：`settings.quality_llm="openai"` 时 worker 的 QualityService keyword client 为 `OpenAICompatKeywordGenerator`。

---

### P2-6（重要）runner 心跳测试为空洞断言：未验证心跳线程真的刷新（且 sqlite 用非线程安全 backend）

- **文件**：`tests/test_task_02_retry.py:127-170`。
- **问题**：`bk = backend.make_backend()` 是 fixture 的 `SqliteBackend`（`sqlite3.connect` 默认 `check_same_thread=True`），心跳线程跨线程调用必然抛 `ProgrammingError`，被 `_heartbeat_loop` 捕获吞掉；而 claim 已把 `heartbeat_at` 置为 `NOW_TS+7`（clock 第 1 次），断言 `hb > NOW_TS` **在心跳线程完全不工作时也恒真**。Tester 所称「fake clock 确定性断言心跳至少跑过一轮」不成立。runner 级心跳循环（本段新增的关键路径）实际未被任何测试验证。
- **修改建议**：
  1. sqlite 臂改用 `ThreadLocalBackend(tmp_path/"lattice.db")`（与 `test_task_03._thread_safe_backend` 同款），pg 臂用 `backend.make_backend()`；
  2. claim 后先记录 `claim_hb = get_task()["heartbeat_at"]`，等 2~3 个心跳间隔后断言 `_ts(row["heartbeat_at"]) > _ts(claim_hb)`（fake clock 下应达到 `NOW_TS+14` 起）；
  3. 同时把 test_task_02 其他 runner 用例（`_FailingIngest`/`_CancelledIngest`/`_SpyIngest`）也换成线程安全 backend，避免心跳线程持续抛错掩盖问题。

---

### P2-7（重要）inline 兜底循环只领 maintenance，ingest 任务在重启/超量后滞留（而 inline 是默认模式）

- **文件**：`app.py:87-133`（`kick` max_drain=64 且领全类型，`_loop` 仅 `run_once(task_types=("maintenance",))`）；`config.py:94`（默认 `worker_mode="inline"`）。
- **问题**：
  1. app 重启后遗留的 pending/leased 过期 ingest 任务，inline 模式下无人认领（只有下一次上传的 kick 顺手领）——与 A.2「租约过期任务可被重认领」在默认模式下不成立；
  2. 单次 kick 超过 64 个任务时剩余 ingest 任务被留在队列，兜底循环不领 ingest → 滞留；
  3. docstring 称「kick 的 ingest 认领与兜底循环不竞争」不实（kick 实际领全类型，可领 maintenance）。
- **修改建议**：兜底循环改为 `self._runner.run_once()`（全类型，与 subprocess 主循环一致）并保留 kick 的同步消化；或至少启动时做一次全类型过期扫 + 去掉/调大 `max_drain`；同步修正 docstring。**补测试**：app inline 模式直接 `create_document`（不经 kick）+ 小 `worker_poll_s` → 任务在 poll 内完成；以及过期 leased ingest 任务被循环重认领。改动后跑全量门禁（app_env 测试可能出现循环与直调并发的时序变化，需实测）。

---

### P3（次要/记录，不阻断）

| ID | 文件:行号 | 问题 | 建议 |
|---|---|---|---|
| P3-1 | `tests/test_v11_schema.py` / `tests/test_scaf_03_migrations.py` | 0004 存量 tombstone 回填缺直接断言（Tester P3-a） | 造 `tombstone=1 AND tombstoned_at IS NULL` → migrate → 断言回填非 NULL；m2-2 或本轮顺手 |
| P3-2 | `.opencode/workflows/task-knowledge-lattice-m2-1.md:16` | frontmatter `filesChanged` 27 项 vs HEAD diff 34 文件；路径 `tests/fixtures/m2_worker_services.py` 实际为 `tests/m2_worker_services.py` | supervised-coding 更正清单（补 `worker/__init__.py` + 6 个存量测试文件，改路径） |
| P3-3 | `.env.example:31-42` / `config.py:94-104,152-165` | 漏 `LATTICE_WORKER_RESTART_BACKOFF_S`、`LATTICE_EMBED_DIM`（get_settings 新增读取）；`worker_mode` 非法值静默回退 inline、lease/heartbeat/poll/keep 无校验 | 补 env 模板；create_app/worker 对非法 `worker_mode` fail-closed；对 `poll_s<=0`、`lease<=0`、`attempts<1` 给出校验或文档 |
| P3-4 | `worker/runner.py:263-296` | supervisor 固定 1s 退避（非指数/上限）；`stop()` 不 join monitor，存在「stop 后 monitor 仍 start 新 worker」竞态；旧 proc stdin fd 延迟释放 | 指数退避 + 上限/连续失败告警；`stop()` 先置 `_stop`、join monitor、再对最终 `_proc` 做关闭/terminate；关闭旧 stdin |
| P3-5 | `worker/runner.py:298-315` | `_worker_env` 仅映射部分字段：programmatic `Settings`（非 env）下 `embed_model/embed_batch_size/quality_llm/upload_ttl/upload_max_bytes/log_level/log_format/maintenance_interval_s/probe_thresholds` 与父进程漂移（embed_model 漂移会让 worker 写的向量标签永不被主进程查询） | 明确「子进程只支持 env 配置」并文档化，或序列化完整 settings 传入；至少补 `embed_model`/`embed_batch_size`/`quality_llm`/日志字段 |
| P3-6 | `worker/maintenance.py:14-17` | docstring 声称 `MAINTENANCE_BODIES` 注册表为扩展点，实际无此变量（硬编码 4 个 `_body`） | 实现注册表或改措辞为「runner executor 分发字典 + 本模块编辑扩展」 |
| P3-7 | `worker/runner.py:27-29,378-386` | `LATTICE_WORKER_SERVICES` 是通用生产钩子（非仅测试），`.env.example` 未登记、未记录加载了哪个工厂 | 文档化并 INFO 日志打印 factory module:attr；若仅测试用则加环境限制 |
| P3-8 | `tests/test_task_04_isolation.py:98-104,107-131`；`tests/test_e2e_03_reclaim.py:85-96` | flag 文件在「投递/唤醒之后」写入，worker 可能先认领并按正常路径完成 → 测试 flaky；`supervisor.proc` 可变属性观察死亡窗口（backoff 0.5s）可能错过 | 工厂改为「首个任务必 crash/必慢」的一次性模式（env 开关），或 flag 写入先于 notify/上传；观察死亡时先捕获 victim proc 对象再 `poll()` |
| P3-9 | `tests/m2_worker_services.py:48`；`tests/test_task_04_isolation.py:40` | 工厂 FakeEmbedder `model_name="fake-embed"`，父 Settings 默认 `qwen3-embedding-4b` → worker 写的向量标签与主进程查询标签不一致，subprocess E2E 的「检索命中」实际只能由 FTS 路满足（向量路空转） | 对齐 `Settings(embed_model="fake-embed")` 或工厂用默认 model_name，使 E2E 真实验证向量回写 |
| P3-10 | `tests/test_task_03_cancel.py:67-97,206-269` | 取消覆盖缺 overwrite pending **有块**场景（T8 删块未被直接断言）；缺取消×切换竞态、取消 leased 任务、崩溃耗尽用例 | 补 overwrite index_fts 后取消 → v2 pending failed、v2 块删除、v1 不动；补 P1-1/P2-2/P2-3 回归 |
| P3-11 | `docs/TEST-CASES.md` TC-VER-08；`RUNBOOK.md` | TC-VER-08 写「造数 created_at=91 天前」，实现以 `tombstoned_at` 为基准（正确但文档未回写）；RUNBOOK 无 0004 升级注意（旧 tombstone 自迁移时点起算 90 天） | supervised-coding 回写 TEST-CASES；RUNBOOK 活文档补升级注记（用户已确认方向，仅落笔） |
| P3-12 | `core/docs/ingest.py:238-247` | `_copy_streaming` 在 `try` 之外，流式拷贝中途失败（磁盘满/源读错）留下半截 canonical 对象（无 unlink 补偿） | 把 copy 纳入 `try/except` unlink，或 `_copy_streaming` 内部失败自清 |
| P3-13 | `core/docs/credentials.py:463-490` | P3-11 补偿仅覆盖 `doc_id is None` 的 fresh-create 路径；混合场景（同凭证一 fresh consume + 一 overwrite consume 并发）输家为 overwrite 时仍会留下 pending 版本+任务；测试断言「输家 uploads 行 uploaded」在真实竞态下不可能（应 consumed） | 记录残余（known-gaps/TEST-CASES）；或对 overwrite 输家做 pending failed + 删块补偿；测试修正状态语义 |
| P3-14 | `store/sqlite/backend.py:1162-1184` / `store/postgres/backend.py:1134-1155` | `trim_finished_tasks` 两次 DELETE 在 PG 非同一事务；`ORDER BY updated_at DESC LIMIT keep` 同秒无 tiebreaker，保留集合不确定 | 合入单事务（PG）；加 `id`/序列 tiebreaker；保留策略本就是「简单策略」，可接受但记录 |
| P3-15 | `worker/maintenance.py:50-63` | tombstone/成员删除为单条大 DELETE，长任务期间占写锁（NFR-9「worker 短事务分批」在 maintenance 未落实） | 量级增长后按批 LIMIT + commit；当前 10⁴~10⁵ 量级先记录 known-gaps |
| P3-16 | `worker/runner.py:389`；`tests/test_task_04_isolation.py:3`；`tests/test_task_01_lease.py:89` | docstring/注释笔误：`python -m knowledge.lattice.worker`（应为 `knowledge_lattice`）、`create_app(worker_mode="subprocess")`（实际是 Settings 字段）、「attempts → 1」已过时 | 顺手修正 |
| P3-17 | `core/docs/ingest.py:372-407` | 取消管理动作未落审计事件（对照 delete_document/upload 的 outbox 治理事件） | 确认是否属 FR-6 治理面；若属，补 `task.cancel` outbox 事件；否则记录口径 |
| P3-18 | `app.py:269-275` | 调度器每 interval 无条件投递 maintenance 任务，worker 长时间不可用时 maintenance 行持续累积（until 恢复后 retention 清理） | 可接受；建议投递前去重（已有 pending maintenance 则跳过）或记录 |

---

## 三、需求边界问题（不打给 coder 修，交 supervised-coding/用户裁定）

**有，以下 4 项：**

- **A（对应 coder 申报①）默认 `worker_mode=inline` 与任务书口径「单主进程 + 单 worker 子进程」（NFR-1/§2）的默认一致性未定。** `.env.example` 声明「生产显式 subprocess」，但默认值是 inline：按默认部署时 OOM 会杀主进程，TC-TASK-04 的隔离保证不成立；若改默认 subprocess，`app_env`/`test_cred_04` 等大量测试需显式设 inline（且测试门禁环境全局 `LATTICE_PG_DSN` 会触发 P2-4）。请用户裁定：(a) 默认 subprocess（生产 fail-safe，测试显式 inline），或 (b) 保持 inline 但在 RUNBOOK/部署清单强制显式设 subprocess 并在验收记录注明「隔离仅在 subprocess 模式成立」。**裁定前 coder 不擅自改默认值。**

- **B（P2-2/P2-3 的共同根因）`tasks` 表缺「目标版本」关联，取消/耗尽清扫无法可靠定位 pending 版本。** design §5.3 的 tasks 行只有 `doc_id`；取消按 task_id 却只能按「文档当前 pending_version」落失败，导致旧任务误杀新版本（P2-3）；崩溃耗尽也无法安全落 pending failed（P2-2）。请裁定：新增 `tasks.target_version`（迁移 0005，ingest 创建任务时写入；同时解决两处）还是接受当前语义并登记 known-gaps（不推荐，P2-3 的 T1-running + v2-pending 场景是现实路径）。**若选 schema，coder 按迁移 + 双方言 + 测试实施；若选后者，P2-3 按「最新任务」最小守卫并如实记录窗口。**

- **C（Tester P3-a/文档同步）** TC-VER-08 的造数口径写的是 `created_at=91 天前`，实现以 `tombstoned_at`（0004）为基准——实现更符合 design §4「旧版本保留 90 天」语义，但 TEST-CASES 是活文档、需回写。supervised-coding 回写 TC-VER-08 步骤/预期 + RUNBOOK 升级注记（回填自迁移时点起算，保守窗口）；**不改 coder 实现**。

- **D（记录项，无分歧）** fetch window 钳制 [0,10] 与 m1-2 P3-8 的历史建议「clamp ≤10」一致，属实施而非新决策；请在 TEST-CASES/known-gaps 登记 `FETCH_WINDOW_MAX=10` 与「超限静默钳制」的 API 口径（design §6.1 仅给默认 window=2，无上限），避免后续误判为契约变更。

**申报处置汇总**：①=A（待用户裁定）；②双探针 2×/周期=**接受**（POC 量级可忽略，m2-2 可 gate 共享）；③outbox/其余 executor 归 m2-2=**接受**（runner executor 分发字典即预留位）；④tombstoned_at 回填自迁移时点=**接受**（保守安全，落 RUNBOOK/known-gaps，P3-11）；⑤TC-ING-02 inline 条件=**接受**（supervised-coding 回写模式条件）。无越界实现。

---

## 四、Tester R1 报告核对（不替代其 PASS，但需更正 3 处证据强度）

- **属实**：门禁 720+1 双后端双模式 0 skipped、+57 逐文件对账、真 Barrier/真 SIGKILL/真 kill -9、docs/ 零触碰、C 组 `write_embeddings` diff 零命中、存量测试仅基线顺延且 `test_cred_02` 加强、TC-TASK-01/02/03/04/E2E-03/maintenance/承接遗留 3 项均有对应用例与实现落点——均复核一致。
- **需更正**：
  1. **TC-TASK-01 的 runner 心跳证据不成立**：`test_task_02:127` 的断言在心跳线程完全不工作时也通过（claim 已写 `heartbeat_at=NOW_TS+7`；sqlite 用非线程安全 backend，心跳线程实际抛错被吞）。见 P2-6。
  2. **subprocess E2E 的「检索命中」偏乐观**：worker fake embedder 标签 `fake-embed:8` 与父 Settings 默认 `qwen3-embedding-4b:8` 不一致，向量路空转，命中只能来自 FTS；不影响进程隔离/租约结论，但「成果可见」证据应注明 FTS-only。见 P3-9。
  3. **「C 组 72p 文件集」仍不可复现**（Tester 自己 P3-b 已记）——关键事实（防护谓词零改动 + 复跑绿）已独立成立，下轮申报请附文件清单。
- Tester P3-a/P3-c/P3-d 我独立同意：P3-a 归 P3-1；P3-c（pg 并发两线程共享单连接、SKIP LOCKED 已覆盖）与 P3-d（顺序交错模拟）不阻断，记录即可。

---

## 五、结论

- **reviewVerdict: NEEDS_CHANGES**
- **reviewedSha: `d1aa2933fbccbfcab8426db6d7661363042353db`**（= testedSha = HEAD；双 SHA 对齐）
- **P1：1**（P1-1 取消×切换竞态删除在用版本块）
- **P2：7**（P2-1 终态所有权守卫；P2-2 崩溃耗尽不 failed；P2-3 取消误杀新版本；P2-4 worker PG/sqlite split-brain；P2-5 quality LLM 装配分叉；P2-6 心跳测试空洞；P2-7 inline 兜底循环只领 maintenance）
- **P3：18 项**记录性意见（P3-1~P3-18；其中 P3-1/P3-2/P3-9/P3-10/P3-11 建议本轮顺手，"P3-2 由 supervised-coding 更正"）
- **需求边界问题：4 项**（A 默认模式、B tasks.target_version、C TC-VER-08 口径、D fetch clamp 记录）——请 supervised-coding 上报用户裁定；A/B 裁定前 coder 不擅自改默认/schema。
- **CASE_BUG 裁定**：本轮未收到 Tester 的 CASE_BUG 请求，无需裁定。

**放行条件**：P1-1 必须修复并带回归；P2-1~P2-7 全修（或其中 P2-3 按 §三-B 裁定结论落地）后重跑 `scripts/test_gate.sh` 全量双模式，提交 R2 修复轮；reviewedSha 置空待重审。**当前不得交付。**

</details>

<details><summary>Tester R2 报告原文（2026-10-28 16:57，续接会话 ses_e7ec33135ffe1lyeKo27eKIKWu）</summary>

---

# task-knowledge-lattice-m2-1 R2 回归验证报告（Tester）

**testedSha**: `fd979ac04e3aca585ea2346936d35ea34ba4d9`（develop_opencode HEAD，`git rev-parse` 实测；工作区仅监督侧 2 文件——被测代码 = HEAD 纯态）

---

## ① 门禁全量独立复跑 ✅

```
scripts/test_gate.sh（docker lattice-pg Up + LATTICE_PG_DSN 导出）
→ [pytest]   745 passed, 1 deselected（85s 级）
→ [pytest-O] 745 passed, 1 deselected
→ GATE PASS: 双后端双模式全绿，0 skipped（pg 臂 262 = [pg] 参数化 229 + PG 专用 33）
```

与 R2 申报（745+1 / pg 262）逐字一致。

**计数对账（720→745 的 +25）逐文件闭合**：
| 桶 | 实测 | 申报 |
|---|---|---|
| test_task_02_retry | 12→22（5 新函数 ×2 参数化）| +10 ✓ |
| test_task_03_cancel | 11→19（4 新函数 ×2）| +8 ✓ |
| test_wk_inline_loop | 新文件 5 | +5 ✓ |
| 回填双臂 | test_v11_schema +1（sqlite）/ test_pg_scaff +1（pg）| 各 1 ✓ |

**pg 臂分解**：task_02 [pg] 6→11（+5）、task_03 [pg] 5→9（+4）、pg_scaff 32→33（+1）= +10 → 262 ✓。
**test_r2_committer_fixes 归属**（任务书问项）：`def test` 17→17 **零新增**——仅 2 处 `worker_mode="inline"` 配置（A 裁定），不计入增量桶，申报无误。
**C 组 100p**（回应 R1 P3-b）：`test_ver_01 + test_ver_02 + test_emb_02 + test_emb_04_05_07 + test_ret_01` 实测 **100 collected** ✓，防护谓词 diff 仍零命中。

## ② P1-1 取消×切换竞态 ✅（修复真实、断言强）

- **双方言 rowcount 守卫**（sqlite `set_doc_pending_failed` / pg 同构）：UPDATE 零行 → COMMIT 直接返回、不执行 DELETE——Committer 处方原样落地
- **守卫覆盖 `_record_doc_error` 路径**（任务书问项）：✅ ——`_record_doc_error`（ingest.py:630-645）的 pending 分支走 `set_doc_pending_failed`，store 层守卫天然覆盖；active 分支走 `set_doc_active_error`（不删块，无此风险）
- **回归①** `test_set_doc_pending_failed_stale_version_keeps_active_blocks`：版本切换收编后以旧版本号直达调用 → `chunks count >= 1`（在用块保留——断言方向正确：修后不删）+ active_status 不变 + pending 未被伪造
- **回归②** `test_cancel_vs_switch_race_active_blocks_survive`：**Event 确定性交错，非 sleep 赌运气**——switch 阻塞在 Event、取消先行落账、放行后 v1 块保留 / v2 块删（T8）/ VersionConflictError 被让位守卫吞下（`error==[]`）

## ③ P2-1 / P2-2 / P2-3 逐项 ✅

- **P2-1**：`_run_stages` 完成后终态前 `_alive()` 探测 + `except` 首行探测（ingest.py diff 实读）；`_on_failure` done 守卫 + `lease_owner not in (None, self._worker_id)` 守卫；`worker_id = wk-{pid}-{uuid4[:8]}` 每 runner 唯一；`update_task(done)` 加 `AND status IN ('pending','leased','running')` 非终态守卫（双方言）。三条处方测试齐：quality 阶段取消保 failed / done 不被 clobber / 丢租约不覆盖新持有者（owner 断言 `wk-new-holder`、status 停 leased）
- **P2-2**：`fail_exhausted_tasks` 双方言（RETURNING 含 target_version），`run_once` **每轮先清扫**（类型过滤无关——inline maintenance 臂也执行 ✓）；3 轮 claim→过期不执行 → 第 4 次认领前 failed + error 含 attempts 数 + lease_owner 清空；文档侧按 target_version 落 pending failed（`fail_document_version`，NULL 早退登记移交）
- **P2-3**：0005 迁移双方言（sqlite `user_version==5` / pg `schema_migrations` 含 `(5,"task_target_version")`——测试同步实读）；`create_document` 一次计算版本同源传入 `_start_overwrite(pending_version=)` 与 `create_task(target_version=)`（防错位）；cancel 按任务 target_version（`_fail_doc_version` 仅当 `pending_version == target_version` 生效）；T1-running + v2-pending 主场景：取消 T1 → v2 原封 `parsing`、T2 照常跑完切换 ✓；P3-10：有块覆盖上传取消 → v2 块物理删除 + v1 不动 ✓；`_run_stages` 按 task 自带 version 判定归属 ✓；**存量 NULL 回退口径**：`run_task` version=None → `_effective_version(doc)` 兜底（ingest.py:569-571 实读）——代码在位，专测缺失记 P3-z

## ④ P2-6 心跳测试重写（重点核实）✅ 不再空洞

- `runner_backend` fixture：sqlite 臂**真用 ThreadLocalBackend**（每线程一连接，心跳线程写不再被 check_same_thread 吞）——且全部 runner 用例（_FailingIngest/_CancelledIngest/_Spy）同步换用 ✓
- 双采样断言：`hb1 > NOW_TS` → sleep(0.3)（≈6 个 0.05s 心跳轮）→ `hb2 > hb1` 且 `hb2 >= "2026-06-01 12:00:14"`（fake clock 每调用 +7s：claim=+7，两次心跳 ≥+14）
- **反证构造成立**：若心跳线程不跑，hb1==hb2==12:00:07（仅 claim 写入）→ `hb2 > hb1` 与 `≥ +14` **双双必败**。R1 被推翻的恒真断言已实质修复

## ⑤ P2-4 / P2-5 工厂真实性 ✅

- P2-4：`store/factory.py build_backend` 为唯一构造入口（app.py:182 与 runner.build_default_services 同源，DSN 告警不切 PG）；测试**写读实证**——设 `LATTICE_PG_DSN` 后 `build_default_services` 仍 ThreadLocalBackend + `create_task/get_task` 同库读写成功
- P2-5：`build_quality_service` 共享工厂（none→Noop / openai→OpenAICompatKeywordGenerator 双分支断言），app 与 worker 同源——subprocess 下 `LATTICE_QUALITY_LLM=openai` 不再静默 Noop

## ⑥ P2-7 + A 裁定 ⚠️（P2-7 ✅；A 裁定 dataclass 层 ✅ / **env 路径 ✗ → P2，见③问题**）

- **P2-7 三用例全真**：①不经 kick 的任务（直建 doc+task）在 poll 内被兜底循环完成；②过期 leased ingest（手工认领 wk-dead + 0.3s 短租约模拟崩溃残留）被循环重认领——**attempts==2、searchable_full**（flake 见 P3-x，traceback 证明重认领机制本身正常）；③新鲜任务陈旧口径不抢——`claim_next_task(created_before=now−poll)` 直接断言 None、无过滤恒可领（确定性、无 sleep 依赖）。`max_drain 64→1024` ✓
- **A 裁定**：`config.py:97` dataclass 默认 `"subprocess"` ✓；10 处 app 测试显式 inline **精确计数吻合**（conftest 1 + auth_01 1 + cred_01 1 + cred_04 1 + cred_05 2 + e2e_06 1 + r2_committer_fixes 2 + ret_01 1；task_04/e2e_03 为故意的 subprocess；ui_01_manual 是 manual 门外）；非法值 fail-closed 在 `create_app` + `main()` 双处 ✓（但无专测——P3-y）
- **✗ 漏网（P2）**：`config.py:158` `worker_mode=env("LATTICE_WORKER_MODE", "inline")` ——get_settings 的 env fallback 仍是 **inline**，显式传参覆盖 dataclass 默认。生产唯一路径 = README:64 `uvicorn "knowledge_lattice.app:create_app" --factory`（无参 → get_settings）→ **默认部署实际 inline**，A(a)「默认 subprocess、OOM 只杀子进程」在 env 路径未生效；且与 `.env.example` 新模板注释（「LATTICE_WORKER_MODE=subprocess（默认…）」）及 `config.py:97` 注释**自相矛盾**。全部测试显式传 worker_mode（程序化 Settings），门禁测不出此漂移。旁证：get_settings 其余全部 worker_* fallback 与 dataclass 默认一致（5.0/60.0/5.0/1.0/3/7/500/90），**唯独 worker_mode 漂移**——显系遗漏而非意图。（附注：worker 子进程 main() 同走 get_settings 拿 inline，但 main() 不按 worker_mode 分支，无行为影响。）

## ⑦ docs 批原样性 ✅

`7684880` 仅触碰 `docs/TEST-CASES.md`（8 行：v1.8.1 三处——TC-VER-08 tombstoned_at 基准 / TC-VER-05 `FETCH_WINDOW_MAX=10` / TC-ING-07 双模式中断条件）+ `RUNBOOK.md`（+4 行 0004 升级注记）——与检查点申报的 supervised-coding 落笔口径**逐字对应**，无夹带改动。（草稿未经独立 commit，「原样」以上述范围与内容一致性为准。）

## ⑧ R1 四项 P3 闭环核对

| R1 P3 | 处置 | 结论 |
|---|---|---|
| P3-a 0004 回填缺断言 | **已修**：`test_sqlite_0004_backfills_existing_tombstones`（0001~0003 子集库 + 造 tombstone=1 行 → 应用 0004 → 回填非 NULL 断言）+ pg 孪生用例 | ✅ 闭环 |
| P3-b C 组文件清单 | 已附 5 文件清单，实测 100p 吻合 | ✅ 闭环 |
| P3-c pg 并发共享单连接 | 维持记录（未修，双方言同构语句已覆盖）| ✅ 按约记录 |
| P3-d 顺序交错模拟 | 维持记录（不变量级断言成立）| ✅ 按约记录 |

顺手项核对：P3-9 双 subprocess 测试 `embed_model="fake-embed"` 与工厂标签对齐（向量路真实参与 E2E）✓；P3-16 三处笔误全修 ✓；P3-3 部分（env 模板补 `RESTART_BACKOFF_S`/`EMBED_DIM` ✓，数值校验未做——与「部分」申报一致）。

## ⑨ 回归面 ✅

R2 触及的存量测试 diff 逐 hunk 审读：test_pg_scaff/test_scaf_03/test_v11_schema/test_regress = 0005 插入引发的基线顺延（0006/0007 重编号、user_version 3→4→5）；auth/cred_01/cred_04/e2e_06/ret_01 = `worker_mode="inline"` 单行；cred_05 = `**kwargs` 兼容 create_task 新签名；task_01/task_04 = 注释勘误 + embed_model。**零断言弱化、零用例删除**（15 文件 def test 计数逐一对照，仅 v11+1/pg_scaff+1 为新增回填测试）。conftest +1 行（app_env inline）为配置非弱化。

## ⑩ 验收标准 8 条终态对照 ✅

TC-TASK-01~04 / TC-E2E-03 / maintenance / 承接遗留 / 门禁——全部门禁内实跑绿；另 A/B 裁定落地（B 完整、A 见 P2）。

---

## ③ 问题分级

**P2（重要，1 项——阻断 PASS）**

- **P2-A 裁定 env 路径默认值漂移**（详见 ⑥✗）。修复指令（逐字可执行）：
  1. `src/knowledge_lattice/config.py:158`：`worker_mode=env("LATTICE_WORKER_MODE", "inline")` → `worker_mode=env("LATTICE_WORKER_MODE", "subprocess")`
  2. 补回归（建议落 `tests/test_wk_inline_loop.py` 或 conftest 旁）：
     ```python
     def test_get_settings_worker_mode_default_subprocess(monkeypatch) -> None:
         monkeypatch.delenv("LATTICE_WORKER_MODE", raising=False)
         from knowledge_lattice.config import get_settings
         assert get_settings().worker_mode == "subprocess"  # A(a) 裁定：env 路径默认 subprocess
     ```

**P3（次要，3 项——不阻断，建议随 P2 修复批顺带）**

- **P3-x test_wk_inline_loop 两用例等待预算过紧（TEST_BUG，我修测试被权限拦截，转交 coder）**：实测证据——5 文件组合跑 ~4% 失败率（2/20+），traceback 显示任务**已被循环成功重认领**（attempts=2、owner=`wk-{pid}-{uuid}`、租约写入正常）但 ingest 执行停滞 14s+（heartbeat 冻结在认领时刻）耗尽 15s 截止；单跑 0/30、全量门禁 0/4 次未复现——负载相关的执行停顿，非机制缺陷。修复：`test_inline_loop_completes_unkicked_task` 的 `deadline = +10` 与 `test_inline_loop_reclaims_expired_leased_ingest` 的 `deadline = +15` 均 → `+60`（语义不变，仅放宽等待预算）。
- **P3-y 非法 worker_mode fail-closed 无专测**：create_app/main 双处校验在位但无用例。建议补一条 `Settings(worker_mode="bogus")` → `create_app` raises ValueError。
- **P3-z 存量 NULL target_version 回退无专测**：`run_task` NULL→`_effective_version` 兜底与 `fail_document_version` NULL 早退均无直接用例（唯一 NULL 造数 test_pg_backend:182 只测状态机）。与 coder 移交申报（RUNBOOK 补句）口径一致，维持移交即可；如顺手可补一条 NULL 行 run_task 用例。

## ④ 最终裁决

**testVerdict: FAIL**（唯一未决 P2：P2-A 裁定 env 路径默认值漂移——A(a) 的核心申报「默认 subprocess」在生产唯一启动路径上不成立，且与 .env.example 模板声明矛盾；修复为一行 fallback + 一条默认断言测试。其余全部验证项独立证据齐备：门禁 745+1 双模式 0 skipped、+25 逐文件对账闭合、P1-1/P2-1~7 修复断言全部核实为真、P2-6 重写后具备可失败性、R1 四项 P3 闭环。R3 建议：coder 提交 P2-A 一行修复 + P3-x 截止期放宽（+P3-y/z 顺手），tester 做定点复验 + 门禁全量即可。）

**testedSha**: `fd979ac04e3aca585ea2346936d35ea34ba4d9`

</details>

<details><summary>Tester R3 报告原文（2026-10-28 17:24，续接会话）</summary>

---

# task-knowledge-lattice-m2-1 R3 终态验证报告（Tester，maxRounds 最终轮）

**testedSha**: `e02345b7f577882517996e98082df49a54422d9b`（develop_opencode HEAD，父 = fd979ac ✓；工作区仅监督侧 2 文件，被测代码 = HEAD 纯态）

---

## ① P2-A 终态确认（R2 唯一 FAIL 根因）✅ 三层独立证据

1. **diff 实读**：R3 全量 diff 仅 2 文件——`config.py` **单 hunk 单行** `worker_mode=env("LATTICE_WORKER_MODE", "inline"→"subprocess")`，无任何夹带（diffstat：config.py +1−1 / test_wk_inline_loop.py +51−2）；docs/ 零触碰
2. **生产路径独立验证**（绕过测试、直接解释器实读）：
   ```
   unset LATTICE_WORKER_MODE → get_settings().worker_mode == 'subprocess'  ✓
   env=inline → 'inline'；env=subprocess → 'subprocess'（显式配置仍生效）✓
   Settings dataclass default = subprocess（两侧对齐）✓
   ```
   README:64 `uvicorn ...:create_app --factory`（无参 → get_settings）的默认部署自此真正落在 subprocess——A(a) 裁定全路径成立
3. **新用例断言真实**：`test_get_settings_worker_mode_default_subprocess` —— `monkeypatch.delenv` 后直调 `get_settings()`（无缓存现读 env，无假绿通道），即我 R2 报告中的处方原样落地；get_settings 换默认无暗伤（存量仅 2 处调用且只取 `embed_model_label`，实读确认）

## ② P3-x / P3-y / P3-z 落地核实

- **P3-x**：两处 deadline +10/+15 → +60 均已落地（diff 实读）。**但我的 R2 诊断不完整**——R3 复验中该 flake 仍复现（单文件 stress ~1/15、组合 ~1/12），新 traceback 推翻了「执行停顿」理论：文件总耗时仅 5.35s（60s 截止根本未等满），退出走的是轮询条件的 **doc-full 单边分支**。**真根因 = 测试读序竞态**（详见 ③-P3-x′）：`get_task` 与 `get_document` 非原子双读，执行器「切换事务已提交（full 可见）、done 未落库」的毫秒窗口被采为 (running, full) → OR 条件提前 break → done 断言踩空。**失败快照同时自证产品机制正常**（attempts=2、owner=`wk-{pid}-{uuid}` 唯一 id、doc 已达 searchable_full——重认领链路完整工作）
- **P3-y** ✅：`test_invalid_worker_mode_fail_closed` —— `pytest.raises(ValueError, match="invalid worker_mode.*bogus")` 真断言（create_app 的 fail-closed 校验首次有用例）
- **P3-z** ✅：`test_run_task_null_target_version_falls_back` —— **SQL 抹 NULL 造数真实**（`UPDATE tasks SET target_version = NULL` + 前置 `is None` 断言）→ run_task → done + active v1 searchable_full；**双臂实跑确认**（[sqlite]/[pg] 各 PASSED，门禁内含）

## ③ 门禁全量独立复跑 ✅ + 计数对账

```
scripts/test_gate.sh → [pytest] 749 passed, 1 deselected / [pytest-O] 749 passed, 1 deselected
→ GATE PASS: 双后端双模式全绿，0 skipped（pg 臂 263 = [pg] 参数化 230 + PG 专用 33）
```

+4 对账闭合：P3-y(1，无参数化) + P3-z(2，ver_env 双臂) + P2-A 用例(1) = 4；pg 臂 262→263 = P3-z 的 pg 臂（230=229+1）✓。与申报（749+1 / pg 263）逐字一致。

## ④ 问题分级

**P1：无。P2：无（R2 的 P2-A 已闭环）。P3：1 项新增（test-only，不阻断交付）——**

**P3-x′ `test_wk_inline_loop.py` 两用例轮询退出条件读序竞态（TEST_BUG，最终定性）**：
- 现象：stress 组合下 ~5-8% 失败；**6+ 次全量门禁执行（R2×2 coder+tester、R3×2、R1×2）零复现**；单跑 0/30+
- 定性：纯测试缺陷——轮询 `(task, doc)` 非原子，退出条件 `done OR full` 会在 (running, full) 合法中间态提前退出；**被测机制（租约过期重认领→完成）被失败快照自证正确**
- 责任归属说明：R2 时我诊断为「执行停顿、放宽 deadline」，coder 按处方如实执行；真根因藏于同一症状之下，系我 R3 深挖才定位——非 coder 引入
- **精确补丁（2 处，随存档或搭 m2-2 首个 commit 落地即可，本任务交付不受阻）**：两用例轮询退出条件由
  `if row["status"] == "done" or (doc and doc["active_status"] == "searchable_full"):`（①号用例为 doc 单边条件 + 循环后补读 task）
  改为**双条件 AND**：
  ```python
  if (row is not None and row["status"] == "done"
          and doc is not None and doc["active_status"] == "searchable_full"):
  ```
  （①号用例同步把 task 读入轮询体内；60s deadline 保留无害。我已按 TEST_BUG 协议尝试自修，edit/write 对 tests/ 的权限规则未放行，故转补丁指令。）

## ⑤ R2 修复条件逐项闭环

| R2 报告条件 | 状态 |
|---|---|
| P2-A：config.py:158 fallback → subprocess + 默认断言测试 | ✅ 修复 + 用例 + 生产路径独立验证 |
| P3-x：deadline 放宽 | ✅ 已落地（残留竞态另案 P3-x′，test-only） |
| P3-y：非法 worker_mode 用例 | ✅ |
| P3-z：NULL 回退双臂用例 | ✅ |
| 门禁全量 | ✅ 749+1 × 2 模式，0 skipped |

## 终态裁决

**testVerdict: PASS**

依据：①R2 唯一阻断项 P2-A 已修复并经 diff/解释器直读/用例三层独立验证，A(a) 裁定「默认 subprocess」在生产 env 路径真实生效；②门禁 749+1 双后端双模式 0 skipped 独立复跑，+4 增量逐文件对账闭合；③R3 diff 纪律面干净（2 文件、无 docs 触碰、无夹带、工作区纯净）；④唯一残留为 test-only 读序竞态（P3-x′），被测机制本身被失败快照自证正确、从未在任何全量门禁中复现，精确补丁已随报告交付、随存档落地，不构成交付阻断。

**testedSha**: `e02345b7f577882517996e98082df49a54422d9b`

</details>

<details><summary>Committer R3 终审报告原文（2026-10-28 17:38，续接会话 ses_e7eb24ce7ffe9GodZ4GSWxH3p7）</summary>

# Committer R3 终审报告 — task-knowledge-lattice-m2-1

## 〇、基线核对与审查限制

- **HEAD** = `e02345b7f577882517996e98082df49a54422d9b`（`develop_opencode`，`git rev-parse` 核对）；父 = `fd979ac`，再父 = `7684880`，R1 基线 = `d1aa293`；`origin/develop` 同步成立；工作区仅监管侧 `M .opencode/agent/supervised-coding.md` + `?? .opencode/workflows/task-knowledge-lattice-m2-1.md`，被测代码 = HEAD 纯态。
- **增量审查**：`git diff d1aa293..e02345b` = 33 files（R2 `fd979ac` + R3 `e02345b`）；`7684880` 仅 `docs/TEST-CASES.md`（8 行）+ `RUNBOOK.md`（+4 行），**无 design/requirements 触碰**。
- **审查限制**：本会话 bash 仅放行 git/gh 只读命令，**未独立复跑 pytest**；门禁采信 Tester R3 的 `749 passed, 1 deselected` × 双模式、0 skipped、pg 臂 263 输出 + 静态审阅。计数对账：720（R1）→ 745（R2，+25）→ 749（R3，+4），与 R2/R3 申报逐文件一致；49+ 新用例无新增 skip/xfail、存量零删除/零弱化。

---

## 一、R1 意见闭环判定表（逐条终态）

| R1 编号 | 处置证据（HEAD 实读） | 终态 |
|---|---|---|
| **P1-1** 取消×切换删除在用块 | 双方言 `set_doc_pending_failed` 均加 `cur.rowcount == 0 → COMMIT return`（sqlite `:516-545` / pg `:498-527`）；直接回归 `test_set_doc_pending_failed_stale_version_keeps_active_blocks` + `test_cancel_vs_switch_race_active_blocks_survive` | **CLOSED**（产品守卫正确；集成测试保真度见 P3-N2） |
| **P2-1** 终态所有权 | `run_task` done 前 `_alive` 探测 + except 首行 `_alive` 探测（`ingest.py:596-618`）；`_on_failure` done 守卫 + `lease_owner` 守卫（`runner.py:239-252`）；`update_task(done)` 双方言非终态守卫；worker_id `wk-{pid}-{uuid8}` | **CLOSED**（per-runner vs per-claim 见 P3-N4） |
| **P2-2** 崩溃耗尽不 failed | 双方言 `fail_exhausted_tasks`；`TaskRunner.run_once` **每轮先清扫**（类型过滤无关）；文档侧按 target_version 落 pending failed；两条测试 | **CLOSED**（legacy NULL 文档侧见 P3-N3） |
| **P2-3** 取消按目标版本 | 0005 迁移双方言；`create_document` 一次计算 target_version；`cancel_task` 按任务目标版本；T1/v2 主场景 + overwrite 有块取消测试 | **CLOSED（cancel/sweep 范围）**；**失败路径残留见 P2-N1（阻断）** |
| **P2-4** PG/sqlite split-brain | `store/factory.py:build_backend` 唯一后端工厂（app/worker 同源恒 sqlite；DSN 仅告警）；写读实证测试 | **CLOSED**（app 侧 PG 接线归 m2-2，见 P3-N9） |
| **P2-5** quality LLM 装配分叉 | `build_quality_service` 共享工厂；none/openai 双分支测试 | **CLOSED** |
| **P2-6** 心跳测试空洞 | ThreadLocalBackend + 双采样前进断言；心跳线程不跑则双断言必败 | **CLOSED** |
| **P2-7** inline 兜底循环 | 兜底循环 maintenance 即时 + ingest `created_before` 陈旧口径；`max_drain 64→1024`；三用例 | **CLOSED**（秒级粒度/test 竞态见 P3-N5/N6） |
| **P2-A** env 路径默认值 | `config.py:97` + `:158` 双侧 subprocess；`create_app` + worker `main()` 非法值 fail-closed；两个专测 | **CLOSED** |
| **P3-1** 0004 回填断言 | sqlite + pg 孪生用例（0001~0003 子集库造数 → migrate → 非 NULL） | **CLOSED** |
| **P3-2** filesChanged | frontmatter 27→50 项（含路径更正） | **CLOSED** |
| **P3-3** env 模板/校验 | env 模板补 2 项 + fail-closed 落地；数值校验未做（申报「部分」） | **部分**（数值校验留 P3-N10） |
| **P3-4~8/12~15/17/18** | 未展开修复 | **移交登记**（见 §五） |
| **P3-9** fake 标签 | `Settings(embed_model="fake-embed")` 对齐；向量路真实参与 E2E | **CLOSED** |
| **P3-10** overwrite 有块取消 | `test_cancel_overwrite_with_blocks_fails_pending_and_keeps_v1` | **CLOSED** |
| **P3-11** 文档回写 | `7684880` 与 R1 C/D 建议逐字一致、无夹带 | **CLOSED** |
| **P3-16** 笔误 | 三处全修正 | **CLOSED** |

**边界裁定落地**：A=(a) 全路径忠实（dataclass+env+10 处测试显式 inline+fail-closed+模板同步）；B=(a) cancel/sweep 范围落地、失败路径残留 P2-N1。**7684880 docs 批忠实**。

---

## 二、新发现问题分级

### P2-N1（**阻断**）`_record_doc_error` 仍按「文档当前 pending/active」落失败——首传失败会误杀并发新版本（P2-3 根因在失败路径的残留）

- **文件**：`src/knowledge_lattice/core/docs/ingest.py:627`（`_record_doc_error(doc, exc)` 未传 target version）+ `:630-645`；`run_task` 在 `:569` 已算出任务目标版本但未传给失败处理器。
- **问题（确定性场景，非理论）**：
  1. 首次上传任务 T1（target=1）跑过 `index_fts`（D20 切换：active v1、pending=NULL），进入 **embed 长阶段**；
  2. 用户在此期间发起覆盖上传 v2（`start_overwrite` 因 pending=NULL 放行）→ pending v2 + 任务 T2；
  3. T1 的 embed 失败（网关不可达/超时——重试设计要处理的典型失败）→ `run_task` except → `_record_doc_error` 重读文档看到 **pending v2** → `set_doc_pending_failed(v2)` + 删 v2 块 → **新版本 v2 被旧任务 T1 的失败静默杀死**；T2 随后 `_guard_alive(2)` None → failed/cancelled；
  4. 若 v2 已完成切换（active v2），T1 失败会把 `active_error` 写到 **v2** 上（好版本被旧任务错误污染）。
- **修改建议**：
  1. `run_task` except 调用改 `self._record_doc_error(doc, exc, version=version)`。
  2. `_record_doc_error(self, doc, exc, *, version: int | None = None)`：
     ```python
     fresh = self._backend.get_document(doc["id"])
     if fresh is not None: doc = fresh
     if version is None:
         version = doc.get("pending_version") or doc.get("active_version")
     if version is None: return
     if doc.get("pending_version") == version:
         self._backend.set_doc_pending_failed(doc["id"], version, str(exc))
     elif doc.get("active_version") == version:
         self._backend.set_doc_active_error(doc["id"], version, str(exc))
     # else: 目标版本已被切换/被新版本取代——不得触碰当前 pending/active
     ```
     store 层 P1 rowcount 守卫保留（第二道防线）。
  3. **补确定性回归（双后端）**：首传 T1 跑到 embed 前（monkeypatch embedder 在 index_fts 后置 Event 阻塞）→ 创建 v2 → 放行 embed 并令其 raise → 断言：T1 failed、v1 落 active_error（或对应态）、**v2 pending 保持 parsing、v2 块不被删**；随后 `service.run_task(t2)` 能完成至 v2 active full。反向补一条 v2 已切换后 T1 失败 → v2 active_error 保持 None。
- **定性**：P2（重要、阻断）——不删在用版本块（非 P1），但静默杀死并发新版本/污染新 active_error；可恢复（重传 v3）但属同根因文档一致性缺陷，修复量小（5 行 + 1 用例）。

### P3（次要/记录，不阻断）

| ID | 位置 | 问题 | 建议 |
|---|---|---|---|
| P3-N1 | test_wk_inline_loop:94-101,122-131 | P3-x′（Tester R3 终判）：轮询退出 `done OR full` 在 (running, full) 中间态提前 break；R3 仅放宽 deadline 未改条件 | 按 Tester R3 精确补丁 OR→AND + ①号 task 读入轮询体；随下一 commit 落地并重跑门禁 |
| P3-N2 | test_task_03_cancel:380-460 | P1 集成测试 `make_blocking_switch` 主线程取 real_switch → runner 线程 ProgrammingError 被静默吞——只覆盖 cancel-first 序 | 改为阻塞函数内按当前线程取 backend 或显式断言 switch 错误 |
| P3-N3 | ingest.py:403-411,438-440 + RUNBOOK §3 | 存量 NULL 任务 cancel/清扫只落任务行、文档侧不触碰——可能滞留 parsing；R2「回退旧口径」措辞不准确 | RUNBOOK 补 0005 注记 + 修正检查点措辞；m2-2 若实现旧口径须防 P2-N1 类误杀 |
| P3-N4 | runner.py:91-94 | worker_id 每 runner 唯一，inline kick/loop 共享同一 runner 无法区分自覆盖 | 改每 claim 唯一 token；inline-only，默认已 subprocess |
| P3-N5 | ingest.py:260-283,320-370 | create_document 在 _start_overwrite 检查前计算版本——极端并发 pending_version==active_version 碰撞理论窗口 | _start_overwrite pending 检查后自算并返回目标版本；m2-2 卫生批 |
| P3-N6 | test_wk_inline_loop:134-157 | created_before 秒级粒度：poll<1s 按 ~1s 生效；test_kick_beats_loop 秒边界极小概率误判 | 文档化/显式 created_at 造数；记录项 |
| P3-N7 | runner.py:135-160 + fail_exhausted_tasks | 每轮清扫 UPDATE 零行也占写锁 | 量级小可接受；可节流；记录 |
| P3-N8 | api/tasks.py:23-38 | target_version 未入 API payload | 按需补；非验收必需 |
| P3-N9 | store/factory.py + .env.example | app/worker 恒 sqlite；.env.example PG 段与现状不符 | .env.example/RUNBOOK 注明「PG 接线归 m2-2」 |
| P3-N10 | config.py | P3-3 数值校验未做（poll/lease/attempts/keep 负值） | m2-2 卫生批 |
| P3-N11 | maintenance.py:14-17 | MAINTENANCE_BODIES 仍不存在（P3-6 未修） | 改措辞或实现注册表 |
| P3-N12 | runner.py:298-315 | _worker_env 字段映射不全（P3-5 未修） | m2-2 补全或明确仅 env |
| P3-N13 | runner.py:263-296 | supervisor 固定退避/stop 不 join/fd 延迟（P3-4 未修） | m2-2 卫生批 |
| P3-N14 | test_task_04/test_e2e_03 | flag 竞态与 proc 观察窗（P3-8 未修）；门禁 0 复现 | 工厂模式改造；记录 |
| P3-N15 | 多处 | P3-12 流式拷贝孤儿 / P3-13 overwrite 输家残余 / P3-14 trim 事务+tiebreaker / P3-15 大 DELETE / P3-17 取消审计 / P3-18 调度去重 | 均记录/移交 |
| P3-N16 | test_pg_scaff:446 | `_write_extra_v4` 名实不符（历史 P3-17 残） | 顺手改名 |
| P3-N17 | runner.py:434-439 | main() 非法值 fail-closed 无专测（P3-y 只测 create_app） | 可补 |
| P3-N18 | test_wk_inline_loop:79-101 | 手工 claim vs 循环 aged claim 极小竞态 | 与 P3-N1 一并显式化 |

**新风险扫描（R2/R3 diff）结论**：update_task 条件写无存量破坏；0005 兼容（NULL 行为缺口见 P3-N3）；created_before 秒级已申报；**唯一产品级新发现即 P2-N1**。

---

## 三、P3-x′ 处置方式裁定

**可接受为 P3（test-only），不阻断交付**，条件：①精确补丁已存档；②必须落在下一个 commit（P2-N1 修复 commit 或 m2-2 首个）并门禁复跑——不得只存于报告文字；③检查点登记移交清单；④落地前门禁证据以 6+ 次全量零复现为准，期间若因该用例转红按测试缺陷优先修。

---

## 四、交付放行判定

| 条件 | 状态 |
|---|---|
| 门禁 749+1 双模式 0 skipped（R1 663+1 起全程） | ✅ |
| A=(a) 默认 subprocess 全路径 | ✅ |
| B=(a) 0005 + cancel/清扫 | ✅（失败路径残留 P2-N1 未收口） |
| C/D 文档回写 | ✅ |
| R1 意见闭环 | 全闭环（P2-3 cancel/sweep 范围；P3-3 部分；其余移交） |
| docs 冻结/工作区/双 SHA | ✅ |

### 结论

**reviewVerdict: NEEDS_CHANGES**

**唯一阻断项：P2-N1**——`_record_doc_error` 未按 target_version 收口。修复量小（传 version + 三分支守卫 + 1 条双后端确定性回归），建议与 P3-x′ 补丁同一 commit 落地后重跑门禁即可收口。

**若用户裁定「该失败路径缺陷登记 known-gap、不阻塞交付」**：其余条件全满足，可转 APPROVED 并按遗留清单登记。但按本项目 P2=阻断既有口径，正式结论 NEEDS_CHANGES。

**reviewedSha: `e02345b7f577882517996e98082df49a54422d9b`**（= testedSha = HEAD）

---

## 五、遗留移交清单确认（供检查点登记）

**必须落地（阻断收口后）**：①P2-N1 修复（_record_doc_error 按 target_version + 双后端回归）；②P3-x′ 补丁（OR→AND，随修复 commit 或 m2-2 首个 commit）。

**记录/移交（m2-2 或后续）**：RUNBOOK §3 补 0005 升级注记（NULL 任务 cancel/清扫只落任务行）+ 修正检查点 R2 措辞（P3-N3）；worker_mode 常量收敛；P3-3/P3-N10 数值校验；P3-N2（P1 集成测试保真度）；P3-N4（per-claim worker_id）；P3-N5（版本计算窗口）；P3-N6（秒级粒度文档）；P3-N7（清扫节流）；P3-N8（target_version 入 payload）；P3-N9（PG 接线注记）；P3-N11（MAINTENANCE_BODIES）；P3-N12（_worker_env）；P3-N13（supervisor 退避）；P3-N14（subprocess 测试 flag）；P3-N15（六项小项打包）；P3-N16（改名）；P3-N17（main 专测）；P3-N18（inline claim 竞态）；Tester R1 P3-c/P3-d 维持记录；双探针/outbox/executor 分发位归 m2-2（已接受）。

**CASE_BUG**：无正式请求；P3-x′ 按 TEST_BUG 转交处理。

</details>

<details><summary>Tester R4 报告原文（2026-10-28 18:04，续接会话）</summary>

---

# task-knowledge-lattice-m2-1 R4 终态验证报告（Tester）

**testedSha**: `830d6a77c79653ffe622960aa6be6214d03a4b58`（develop_opencode HEAD，父 = e02345b ✓；工作区仅监督侧 2 文件，被测代码 = HEAD 纯态）

---

## ① P2-N1 修复语义（重点项）✅

- **diff 实读三分支守卫**（ingest.py `_record_doc_error`）：`pending_version == version` → `set_doc_pending_failed`（T8 删块，store 层 P1 rowcount 守卫保留为第二道防线）；`elif active_version == version` → `set_doc_active_error`；**均不匹配 → 不触碰**（「旧任务失败不得静默杀死并发新版本」的处方原样落地）；`version=None`（legacy 直调）→ 回退 `_effective_version`，回退后仍 None → return。`run_task` except 首行改传 `version=version`（任务 target_version，R2 引入）
- **`set_doc_active_error` 谓词双方言核实** ✅：sqlite `:1321` / pg `:1277` 均 `WHERE active_version = :v` —— 即便三分支判定与落库间竞态，store 层零行兜底，双保险成立
- **场景 A** `test_record_doc_error_spares_concurrent_new_pending`（双臂）：T1 越过 index_fts（D20 已切 active v1）后 embed 阻塞 → 并发覆盖上传 v2 → 放行 raise。断言逐条核实：T1 failed 含原始错误 ✓；v1 落 `active_error` ✓；**v2 保 `parsing` + `pending_error is None` + v2 块 0 删**（核心「不误杀」断言方向正确——修前代码此场景必写 pending failed + 删块，测试具真实杀伤力）；T2 随后跑至 active v2 full ✓。Event 确定性阻塞、失败注入两线程同源（共享 embedder 实例），非 sleep 赌运气
- **场景 B** `test_record_doc_error_spares_new_active_after_switch`（双臂）：反向——v2 已完成切换（active v2 full）后 T1 失败 → **`active_error is None`**（修前 else 分支必把 active_error 写到新 active v2 上）+ `active_status` 不被污染 + v1 tombstone 块形态未被触碰 + T1 failed 含原错误 ✓
- P2-N1 系 Committer R3 指出的「P2-3 处方缺口（B 裁定只覆盖 cancel/sweep）」，R4 按 ~5 行处方 + 双后端确定性回归完整闭环

## ② P3-x′ 补丁忠实度 ✅ + 竞态消除实证

- 与我 R3 报告的精确补丁**逐字对照吻合**：①号用例 task 读入轮询体 + 双条件 AND（`row is not None and row["status"]=="done" and doc is not None and doc["active_status"]=="searchable_full"`）+ 断言双落点；②号用例 `done OR full` → AND，均附根因注释
- **stress 实证**：单文件 **0/20**、三文件组合 **0/10**（R3 同模式复现率 ~1/8~1/15）——读序竞态消除确认

## ③ 门禁全量独立复跑 ✅ + 计数对账

```
scripts/test_gate.sh → [pytest] 753 passed, 1 deselected / [pytest-O] 753 passed, 1 deselected
→ GATE PASS: 双后端双模式全绿，0 skipped（pg 臂 265 = [pg] 参数化 232 + PG 专用 33）
```

+4 对账闭合：场景 A/B × 双臂（task_03 用例 19→23 条、[pg] 9→11、`def test` 10→12）；pg 臂 263→265 = A-pg + B-pg ✓。与申报（753+1 / pg 265）逐字一致。

## ④ R4 diff 纪律面 ✅

仅申报的 3 文件（ingest.py +25 / test_task_03_cancel.py +158 / test_wk_inline_loop.py +18）；**P3-N 系列零触碰**（Committer 移交清单未被夹带处理）；docs/ 零触碰；工作区纯净。无越范围改动。

## ⑤ e2e_03 偶发处置评估：**接受移交 m2-2**

- 同族确认：`test_e2e_03_reclaim.py:141` 轮询条件 `final[0] in ("done","failed") or doc.get(...) == "searchable_full"` —— 与 P3-x′ 完全同族的 OR 单边读序问题（另有 P3-N14 flag 竞态/proc 观察窗）
- 概率面：该用例历经 **8+ 次全量门禁执行零复现**，R4 首轮首次触发（负载相关）、单独复跑通过、第二轮双模式全绿——含我的本轮门禁两次实跑亦绿
- 处置面：R4 范围禁改未动（范围纪律正确）；补丁方向明确（AND 条件 + P3-N14 工厂模式改造），归 m2-2 顺带成本极低
- 结论：**接受**，作为 m2-2 的显式移交项（与 P3-N14 合并处理）；本轮不构成交付阻断

## ⑥ Committer R3 放行条件终态对照

| 条件 | 状态 |
|---|---|
| P2-N1 修复（run_task 传 version + 三分支守卫）+ 双后端确定性回归×2 | ✅ CLOSED |
| P3-x′ 补丁落地（OR→AND + ①号 task 入轮询体）+ 门禁重跑 | ✅ CLOSED（stress 0/30 复现归零） |
| P3-N1~N18 移交清单 | ✅ 按用户授权全量移交 m2-2（零触碰核实） |

## ③′ 问题分级

**无新增问题。**（P3-x′ 残留为零——竞态已消除实证；e2e_03 偶发为已登记移交项的非新增事项。）

## ④ 最终裁决

**testVerdict: PASS**

依据：①Committer R3 唯一阻断项 P2-N1 按处方完整修复，场景 A/B 双臂确定性回归断言方向全部对准「修后不误杀」核心语义，store 层谓词双保险核实；②P3-x′ 忠实落地且竞态经 30 次 stress 归零；③门禁 753+1 双后端双模式 0 skipped 独立复跑，+4 逐项对账闭合；④范围纪律零越界；⑤唯一移交项（e2e_03 同族轮询）评估接受、方向明确。本任务全链（R1 交付 → R2 P2-A → R3 定点 → R4 P2-N1/P3-x′）至此闭环，待 Committer 闭环复审。

**testedSha**: `830d6a77c79653ffe622960aa6be6214d03a4b58`

</details>

<details><summary>Committer R4 闭环复审报告原文（2026-10-28 18:11，续接会话 ses_e7eb24ce7ffe9GodZ4GSWxH3p7）</summary>

# Committer R4 闭环复审报告 — task-knowledge-lattice-m2-1

## 〇、基线核对

- **HEAD** = `830d6a77c79653ffe622960aa6be6214d03a4b58`（`develop_opencode`；父 = `e02345b`；R1 基线 `d1aa293`）；`origin/develop` 已同步、未 push；工作区仅监管侧 2 文件，被测代码 = HEAD 纯态。
- **R4 增量** = `git diff e02345b..830d6a7`：**3 files，+189/−12**——`core/docs/ingest.py`（P2-N1）、`tests/test_task_03_cancel.py`（场景 A/B 回归 + 线程辅助）、`tests/test_wk_inline_loop.py`（P3-x′）；与申报完全一致；`docs/` 零触碰；P3-N2~N18 零夹带。
- **审查限制**：bash 仅放行 git/gh 只读，未独立复跑 pytest；采信 Tester R4 的 `753 passed, 1 deselected` × 双模式、0 skipped、pg 臂 265 + 静态审阅 + diff 实读。
- **SHA 链**：R1 `d1aa293` → R2 `fd979ac` → R3 `e02345b` → R4 `830d6a7`；`testedSha = reviewedSha = HEAD`。

---

## 一、放行条件逐项闭环判定

| # | R3 放行条件 | 证据（HEAD 实读） | 判定 |
|---|---|---|---|
| 1 | **P2-N1**：run_task 传 version + 三分支守卫 + None 回退 | `ingest.py:627` 改为 `self._record_doc_error(doc, exc, version=version)`；`_record_doc_error`（`:630-659`）：fresh 重读 → None 回退 → pending==version→T8（store 层 P1 rowcount 守卫第二道防线）/ active==version→active_error / **均不匹配→不触碰**。`set_doc_active_error` 谓词双方言实读（sqlite `:1318-1324`、pg `:1274-1280`）均 `WHERE id AND active_version = :v`——判定侧与落库侧双保险 | **CLOSED** |
| 1′ | 场景 A/B 断言方向（修前必败、修后成立） | 场景 A：修前旧代码会写 pending v2 failed + 不写 v1 active_error + T2 被 cancelled——三重杀伤力。场景 B：修前 else 分支必写 active_error v2。**两条均具真实可失败性**（Tester 独立复核一致） | **CLOSED** |
| 2 | **P3-x′** 落地 + 竞态归零 | 与 Tester R3 精确补丁逐字吻合；stress 0/20+0/10（R3 同模式复现率 ~1/8~1/15）；`(running, full)` 提前退出窗口结构上消除 | **CLOSED** |
| 3 | P3-N 移交零触碰 | R4 diff 仅 3 文件；P3-N1 即 P3-x′（授权修复）；P3-N2~N18 全部未触碰；无 docs/design 改动。（coder 申报「P3-N 零触碰」措辞不精确——P3-R4-4） | **CLOSED（措辞小瑕）** |
| 4 | 新风险扫描 | ①`_record_doc_error` 唯一调用点 run_task（grep），keyword-only 向后兼容；②正常路径全覆盖；③legacy NULL 口径与 R2 一致（歧义属 R3 P3-N3 未变）；④**未引入新 P1/P2** | **PASS** |
| 5 | e2e_03 偶发移交 m2-2 | 范围纪律正确；补丁方向明确；历史 8+ 次全量零复现 | **接受**（P3 移交非阻断） |
| 6 | 门禁 753+1 双模式 0 skipped（R1 663+1 起全程） | Tester R4 独立复跑；+4 对账闭合；pg 臂 252→262→263→265；无新增 skip/弱化/删除 | **PASS** |

**结论**：R3 唯一阻断项 P2-N1 按处方完整闭环；P3-x′ 竞态实证归零；P3-N 零夹带；门禁全绿；**放行条件全部满足。**

---

## 二、新发现问题分级

**P1：无。P2：无。**

| ID | 位置 | 问题 | 建议 |
|---|---|---|---|
| P3-R4-1 | ingest.py:620-627 | 取消与失败落账极窄窗口：_alive 检查后 update_task(failed) 前取消先行落 failed+cancelled: → 本次 failed 覆盖取消 error（最终仍取消吸收、文档侧有 version 守卫）——R1 P2-1 条件终态写只做了 done 的残留 | m2-2：update_task(failed) 加 AND status IN ('leased','running') 或 owner 条件；µs 级窗口 |
| P3-R4-2 | ingest.py:657-659 | 失败发生在已切 active 且已 full 的版本时 set_doc_active_error 留 error；幂等重跑 completed 路径不清除 | m2-2：completed/done 路径清 active_error 或仅非 full 时写 |
| P3-R4-3 | test_task_03 场景 A | n_v2==0 断言偏弱（v2 本就未写块）；杀伤力实来自 pending_status/pending_error/v1 active_error 三断言（已足够） | 可选：造 v2 已写块再触发使「块不误删」成强断言 |
| P3-R4-4 | 检查点 R4 申报 | 「P3-N 零触碰」与同 commit 的 P3-N1（=P3-x′）修复表述矛盾；实际 N2~N18 零触碰 + N1 授权修复 | 归档措辞更正，不影响结论 |

---

## 三、终态放行判定

### 结论

**reviewVerdict: APPROVED**

**reviewedSha: `830d6a77c79653ffe622960aa6be6214d03a4b58`**（= testedSha = HEAD）

R3 唯一阻断项已按处方闭环；P3-x′ 竞态实证消除；R4 范围纪律零越界；门禁 753+1 双模式 0 skipped；e2e_03 同族偶发接受移交 m2-2；新增问题均为 P3 记录项。**本任务满足交付放行条件。**

**CASE_BUG**：无正式请求。

**交付阶段（用户确认后）**：执行 `gh pr review` 将本结论与 evidence manifest（双 SHA=830d6a7、PASS/APPROVED、gate_commands、753+1、0 skipped）落在 PR；合入动作不经手。

---

## 四、遗留移交清单终态（m2-2 去向——已由 supervised-coding 登记检查点「遗留事项」节，共 23 项：e2e_03 同族轮询、RUNBOOK 0005 注记、worker_mode 常量、P3-N2~N18、P3-R4-1/2/3、R1 接受记录项维持）

**交付证据汇总**：门禁 753+1（sqlite+pg、常规+`-O`、0 skipped，pg 臂 265）；R1 663+1 → R4 753+1 全程 0 skipped；R4 diff 3 文件、docs 零触碰、P3-N2~N18 零夹带；双 SHA = 830d6a7。

</details>

<details><summary>Tester R1 报告原文（2026-10-28 14:56，ses_e7ec33135ffe1lyeKo27eKIKWu）——时序最早，因追加锚点顺序位于本节末尾</summary>

# task-knowledge-lattice-m2-1 R1 验收测试报告（Tester 独立复验）

**testedSha**: `d1aa2933fbccbfcab8426db6d7661363042353db`（develop_opencode HEAD，`git rev-parse` 确认；工作区仅 `M .opencode/agent/supervised-coding.md` + `?? .opencode/workflows/task-knowledge-lattice-m2-1.md` 两个监督侧文件——coder 申报属实，被测代码 = HEAD 纯态）

---

## ① 门禁全量独立复跑（验收项 1）✅

```
docker start lattice-pg → Up 3 days
export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
scripts/test_gate.sh
→ [pytest]   OK：720 passed, 1 deselected, 2 warnings in 103.71s
→ [pytest-O] OK：720 passed, 1 deselected, 3 warnings in 102.24s
→ GATE PASS: sqlite+pg 双后端、双模式全绿，0 skipped（pg 臂 252：[pg] 参数化 220 + PG 专用 32）
```

与 coder 申报逐字一致（720+1 = 720 passed + 1 deselected 即 manual TC-UI；pg 臂 252 实跑）。

**计数对账（663→720 的 +57）**：7 个新测试文件独立收集 `57 tests collected`，逐文件：
`task_01=12 / task_02=12 / task_03=11 / task_04=1 / e2e_03=1 / wk_maintenance=10 / p3_followups_m2_1=10`（合计 57）——与 coder 申报的逐文件数字**完全一致**；6 个存量文件 `def test` 计数前后不变（21/13/19/4/6/12 → 等值），无删除。对账闭合：**+57 恰为新增用例，无口径漂移**。

## ② TC-TASK-01 心跳与租约 ✅（12p 双臂）

- **租约 60s 精确断言**：`test_claim_pending_sets_lease_fields:62` —— `lease_until == "2026-06-01 12:01:00"`（NOW_TS=12:00:00 + 60s，字符串时间线精确比对，非近似）
- **5s 心跳**：`:76-77` heartbeat_at=12:00:05 且 lease_until 顺延至 12:01:05；runner 侧心跳线程用 fake clock 确定性推进（`test_task_02:127`）
- **过期重认领 + 不双跑**：`test_expired_lease_reclaimable_no_double_run` —— 未过期他人不可抢（12:00:59 → None）、过期（13:01:00）重认领、attempts==2、原持有者 wk-A 心跳 False / 新持有者 wk-B True
- **真实并发窗口**：`test_real_concurrent_claim_exactly_one_winner` —— `threading.Barrier(2)` 对齐、3 轮、`assert len(winners) == 1`（恒真不可能：results 长度 2 强校验、恰一 winner 断言在 winner 列表上）。sqlite 臂 ThreadLocalBackend 每线程真连接（真竞争）；pg 臂 SKIP LOCKED 语句覆盖（局限见 P3-c）
- **claim 原子性双方言**：sqlite = 单语句 `UPDATE … WHERE id=(SELECT …)` 子查询重估（sqlite/backend.py diff 实读）；pg = `FOR UPDATE SKIP LOCKED` CTE（postgres/backend.py diff 实读）。两臂均有用例实跑

## ③ TC-TASK-02 重试上限 ✅（12p 双臂）

- `test_retry_budget_three_attempts_then_failed:56-80`：attempts 1/2 → `pending` 回队，第 3 次 → `failed` + `error` 含 `"boom #3"`，第四次 `run_once()==False`（不复活）；执行器桩不写终态——runner 兜底路径同时被验证
- **ingest 真链路**：`test_ingest_real_chain_retry_then_fail:173` —— `embedder.fail=True` 注入（非桩执行器），3 次 run_once → failed/attempts==3/error 含 `unreachable`、文档落 `active_error`；修复后直调 run_task 续跑 → `searchable_full`（阶段幂等）
- claim 侧防线：`attempts ≥ max_attempts` 不再被认领（pending 也不领，防无限崩溃循环）

## ④ TC-TASK-03 任务取消 ✅（11p 双臂 + API）

- **阶段边界停止（非立即杀）**：`test_cancel_stops_running_task_at_stage_boundary` —— monkeypatch parse 阻塞、running 态确认后取消、release 后执行器在**下一阶段边界**经 `should_continue` 探测 lost_lease 静默退出（`error==[]` 不冒泡）、取消终态不被覆写。embed 批次边界：`test_cancel_during_embed_batch_boundary` —— 批大小 1 × 8 段长文、每批 sleep 150ms 制造窗口、取消后 `embedder.calls` 停止增长（**剩余批次零外呼**）、文档停 `searchable_lexical`
- **幂等续跑不复活**：取消后直调 `run_task` 拒绝 + runner 不认领 + 二次取消幂等（200）；实现侧 `set_doc_pending_status` 加 `pending_status != 'failed'` 防复活谓词、insert 事务内存活复核（diff 实读）
- **文档状态一致**：pending 版本 failed + `delete_by_doc()==0` 无块残留；首传已切换场景停 `searchable_lexical` 稳态、`pending_version is None`——不滞留 parsing
- **API 权限面**：u_cn 403 / 跨组织 404 / owner 200 `cancelled:true` / 不存在 404，全链经 TestClient 实跑

## ⑤ TC-TASK-04 子进程隔离 ✅（1p，真实 subprocess）

- **真实 subprocess 确认**：`runner.py:243` `subprocess.Popen([sys.executable, "-m", "knowledge_lattice.worker"], stdin=PIPE)` —— 非线程非 mock；测试经 `create_app(worker_mode="subprocess")` lifespan 拉起，`LATTICE_WORKER_SERVICES` 工厂钩子注入 fake 栈（跨进程唯一可行注入方式）
- **OOM 形态**：崩溃桩在 worker 进程内 `os.kill(os.getpid(), SIGKILL)`（`m2_worker_services.py:70`）——真实信号形态，非进程内异常模拟
- **主进程存活**：worker 死亡窗口内 `/api/search` 200；**supervisor 新 pid**：`proc.pid != first_pid` 轮询断言；**重启后正常任务**：REST 上传 → 轮询至 `searchable_full` → 检索命中（成果可见）

## ⑥ TC-E2E-03 杀进程演练（M2 半句）✅（1p + 机制半句双臂）

`test_kill_worker_lease_reclaim_completes` 全链实跑：REST 上传 → worker 认领（running + lease 落位确认）→ **真 `send_signal(SIGKILL)`** → 任务滞留 `leased/running` 且 attempts==1（租约未过期不可抢）→ supervisor 新 pid 拉起 → 租约过期（2s 注入）→ 新 worker 兜底轮询重认领 → **attempts==2** → `done` → `searchable_full` → `/api/search` 命中。机制半句（造数过期重认领）由 TC-TASK-01 双臂承载。

## ⑦ maintenance 框架 ✅（10p 双臂）

- **三任务体**：凭证回收（过期造数 → purged==1 + 行物理删除 + `maintenance.run` 审计事件）；过期成员清理（成员行删除 + 触发器级联清授权、有效成员/仅授权过期者不动——生命周期独立性断言）；tombstone 90 天清理（切换事务写 `tombstoned_at` 断言 → 未到期不删 → 造数过期后删 + `chunk_vectors` FK CASCADE + 在用块不动）
- **任务行保留策略**：天数截尾（3 超龄删）+ 条数截尾（keep_count=3 戉最旧 2）+ 非 maintenance 类型与进行中行不受管辖
- **任务体隔离**：单体 monkeypatch 抛错 → 任务 failed 落汇总原因、其余任务体照常执行
- **0004 迁移双方言**：`test_v11_schema`（sqlite applied==[2,3,4]、user_version==4）、`test_pg_scaff`（schema_migrations 含 `(4, "tombstoned_at", "docs")`）、回归探针迁移顺延 0005（乱序拒绝/fk 回滚/并发 advisory lock 全链随基线前进复跑）。迁移 SQL 双方言实读：`ADD COLUMN + 回填 UPDATE + 部分索引`。**回填直接断言缺失见 P3-a**

## ⑧ C 组 embed 回写防护 ✅

- **零改动证据**：`git diff d1aa293^..d1aa293` 对两个 backend 的 diff 无任何 write_embeddings 相邻 hunk（grep 零命中）；当前 HEAD 谓词文本实读确认在位（sqlite `:356`/pg `:359`：「rid 在批 + tombstone=0 + 标签匹配 + (rid,label) 无行」）
- **既有断言复跑**：ver/emb/ret 系文件独立复跑全绿（67p / 105p / 142p 三种组合），且全部门禁 720p 内含。申报「72p」具体文件集不可复现——见 P3-b

## ⑨ 承接遗留 3 项 ✅（test_p3_followups_m2_1.py 10p 双臂）

- **P3-8**：`window=999` → `len==2*FETCH_WINDOW_MAX+1==21` 且 seqs 精确 [10..30]；`window=-3` → 仅 [20]。边界值断言真实（非边界弱断言）
- **P3-6**：同凭证两 `begin_put` → `sink1._staging != sink2._staging`（随机后缀实现 diff 实读：`uuid4().hex[:12]`）+ 交错写互不串扰 + 双 finalize 成功 + 无 `.part` 残留。顺序交错模拟非线程真并发——修复本体是命名不变量，验收语义成立（P3-d 备注）
- **P3-10**：spy 断言 `file_src` 传入且无 `file_bytes`（不整体读内存）+ canonical 对象逐字节等于源 + 上传对象清理；实现侧 64KB 分块流式拷贝+增量哈希、consume 侧 64KB 流式哈希复验（diff 实读）
- **P3-11**：`mark_upload_consumed` 输家注入（竞态零行）→ `CredentialConsumedError` + **无孤儿文档**（title 查询空）+ **无孤儿任务**（非终态任务计数 0——注释点明 worker 会把孤儿任务真跑成重复文档，补偿必要）+ uploads 行保留 `uploaded`（单次使用语义归赢家）+ 对象零残留

## ⑩ 回归与纪律面 ✅

- **docs/ 零触碰**：`git diff --stat d1aa293^..d1aa293 -- docs/` 输出为空（实跑确认）；TC-ING-02 口径句回写归 supervised-coding，与边界一致
- **存量无弱化**：6 个被改存量文件 diff 逐 hunk 审读——全部为 0004 插入引发的版本号顺延（测试迁移 0004→0005/0006、user_version 3→4）；`test_cred_02` 反而**加强**（`.part` 精确路径改 glob + 新增全量 `*.part` 残留检查）；`test_pg_backend` 状态机断言改 claim 计数口径（新模型语义）且新增「running 不重复计」断言。`def test` 数量零删除
- **命名约定**：task_/wk_/e2e_ 前缀 + p3_followups_m2_1 沿用既有 m1_3/m1_4 系列惯例 ✓
- **busy_timeout**：连接工厂既有（5000ms，连接级断言），worker ThreadLocalBackend 同工厂 ✓；outbox 仅口径注记未实现——符合任务边界

## ⑪ 验收标准 8 条对照 ✅

| # | 标准 | 结论 |
|---|---|---|
| 1 | TC-TASK-01 心跳/租约/重认领+真并发 | ✅ 12p 双臂（§②） |
| 2 | TC-TASK-02 attempts≥3 failed 留原因 | ✅ 12p 双臂（§③） |
| 3 | TC-TASK-03 阶段边界/幂等/文档一致 | ✅ 11p（§④） |
| 4 | TC-TASK-04 OOM 只杀 worker/检索可用/自动拉起 | ✅ 1p 真实 subprocess（§⑤） |
| 5 | TC-E2E-03 杀进程重认领续跑至 searchable_full | ✅ 1p（§⑥） |
| 6 | maintenance 三任务体+保留策略 | ✅ 10p 双臂（§⑦） |
| 7 | 承接遗留 1/2/3 处理完毕 | ✅ ①真并发+租约 ②window 钳 ③P3-6/10/11 全修（§⑨） |
| 8 | 门禁 663+1 起双后端双模式 0 skipped | ✅ 720+1 独立复跑全绿（§①） |

---

## ③ 问题分级

**P1（阻断）：无。P2（重要）：无。**

**P3-a（次要，不影响结论）**：0004 迁移「存量 `tombstone=1` 行回填 tombstoned_at」缺直接断言——现有测试库均为 fresh DB（回填空转），仅覆盖了切换事务写入时点的场景。回填语义（存量行自迁移时点起算 90 天，RUNBOOK 已申报为升级注意）建议补一条用例：造 `tombstone=1 AND tombstoned_at IS NULL` 行 → migrate → 断言回填非 NULL。可归 m2-2 顺带，本轮不阻断。

**P3-b（次要）**：coder 申报「C 组复跑 72p」的文件集不可复现（我按 ver/emb/ret 相关组合得 67/105/142，均全绿）。关键事实（防护谓词零改动 + TC-VER-06/embed 既有断言零回归）已独立成立，但下轮申报请附文件清单，防计数口径漂移。

**P3-c（次要）**：pg 臂真并发认领用例两线程共享单条 psycopg 连接（`PgDb.make_backend` 包装同一连接），DB 层竞争被连接级串行化部分吸收——SKIP LOCKED 语句被覆盖、exactly-one-winner 不变量双臂均验证，但「两独立连接真竞争」场景仅 sqlite 臂具备。如需 pg 同强度，需 dbwrap 提供多连接形态，可归后续。

**P3-d（备注）**：P3-6/P3-11 用例为顺序交错/monkeypatch 模拟（非线程真并发）。两项修复本体（唯一后缀命名、输家补偿删除）是不变量级断言，验收语义成立；如实记录。

## ④ 最终裁决

**testVerdict: PASS**

- 门禁独立复跑全绿：720+1 × 双模式、0 skipped、pg 臂 252 实跑；+57 增量对账闭合
- TC-TASK-01~04 / TC-E2E-03 / maintenance / 承接遗留 3 项 / C 组防护全部有独立证据（断言真实性逐条核实，无恒真/串行假并发/弱断言）
- docs/ 零触碰、存量零弱化零删除、命名合规、工作区申报属实
- 4 项 P3 均不阻断，可随 m2-2 或下轮顺带处理（P3-a 建议补回填用例为首选）

**testedSha**: `d1aa2933fbccbfcab8426db6d7661363042353db`

</details>
