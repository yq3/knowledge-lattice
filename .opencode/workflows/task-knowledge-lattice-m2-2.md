---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2-2
target: knowledge-lattice
coderTaskId: null
testerTaskId: null
committerTaskId: null
status: implementing
round: 1
maxRounds: 3
testVerdict: null
reviewVerdict: null
testedSha: null
reviewedSha: null
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: []
endReason: null
createdAt: 2026-10-29T09:40:22+0800
updatedAt: 2026-10-29T09:42:23+0800
---

# task-knowledge-lattice-m2-2: M2.4+M2.5 审计 outbox 一致性 + 月库滚动/封存 + 删除级联收口 + 备份恢复演练（M2 主线第二段）

## 任务原文

**需求**（design.md §8 M2.4/M2.5 + §4 audit_outbox DDL〔0001 已建表〕+ §3 maintenance 任务族〔m2-1 预留分发位〕+ NFR-10 备份恢复；requirements §8 M2 行对齐。前置：m2-1 已交付 worker 任务框架〔PR #2〕——本段任务体全部挂 worker 任务模型）：

**A. 审计 outbox 一致性链路**（design §4 注「权限事件走 outbox：业务库同事务写 audit_outbox，后台搬运保证业务改了就一定有审计」+ §5.3；TC-OPS-01；m1-2 移交「outbox 非同事务 + 上传无审计」）：

1. **outbox 写入路径全量接入**：治理动作业务库**同事务**写 `audit_outbox`（0001 既有表）——本段接入 docs 侧可触发的事件类型：上传/覆盖上传/删除/取消（m1-2「上传无审计」+ m2-1 移交 P3-17 取消审计）、维度值 PATCH（M1 既有端点）、凭证签发/消费（TC-CRED 侧既有审计口径核对）、维护动作（maintenance.run 沿用）；**语义侧三类事件（semantic.sync/build、YAML 合并）仅预留 event_type 常量与注释锚点，不实现**（归 m2s-1/m2s-3——TC-OPS-01 中 #38 P1-7 语义三类断言落 TC-BUILD-03/TC-YAML-03/T-S9，随语义轨道段验收）
2. **搬运任务**：后台任务把 shipped_at IS NULL 的 outbox 行搬至月库 `audit_events` 并回填 shipped_at（同事务：搬运+回填）；挂 maintenance 任务族（m2-1 executor 分发位——新增任务体，非独立 type）；runner.py 既有「查询级审计异步写、权限事件走 outbox」口径注记兑现
3. **崩溃注入语义**（TC-OPS-01 核心）：业务提交后立即崩溃的注入场景下业务与 outbox 同生共死——「业务改了就一定有审计」

**B. 审计月库滚动/封存/保留**（design §4 注 + FR-6；TC-OPS-02；现状：双方言 audit.py 已有 ensure_monthly_audit/ensure_month_partition 骨架〔M0a〕）：

1. 跨月滚动：新月库由连接工厂建表+触发器（既有）；**旧月库封存只读**（sqlite：只读打开+文件权限+封存记末哈希；pg：分区形态按既有实现口径）
2. **append-only 断言**：UPDATE/DELETE 当月与已封存月库 audit_events 全部 ABORT（既有触发器复核 + 已封存月库侧补全）
3. **保留期 12 个月**：造数 13 个月前月库文件 → 整文件删除（挂 maintenance；pg 分区口径同语义——drop partition）
4. **哈希链**（FR-6）：每月首条引用上月末哈希、封存记末哈希——核实现状（月库 DDL 是否已有链列），缺失则补（双方言；sqlite 文件库与 pg 分区各自形态，SQL 下沉 store/<dialect>）

**C. 删除级联与删库流程收口**（design §8 M2.4 尾；TC-OPS-04；**T19 删库半句收口**——M1 验收限定项，v0.6.1/#39）：

1. DELETE 文档：chunks/document_dimensions/quality_flags 级联删除、任务取消、（M2-S3 起 untag——本段预留注释锚点）——M1 既有 delete_document 复核 + 补断言
2. **对仍有文档的库（dataset）发删除 → 明确报错（RESTRICT 语义、非裸外键异常）——T19 半句**；先删文档后删库 → 成功
3. 90 天 tombstone 物理清理已随 m2-1 交付（TC-VER-08 ✅）——本段仅验收引用，不重做

**D. 备份快照与恢复演练**（design §2 NFR-10 + §8 M2.5；TC-OPS-05；**双后端各一份 runbook——D24：sqlite `VACUUM INTO` / pg pg_dump**）：

1. `store/<dialect>/backup.py`：sqlite `VACUUM INTO` 快照 + pg `pg_dump` 快照（进程外命令调起属部署工具链不违 D2；含 `data/objects/` 一并备份——tar/目录拷贝）
2. 快照任务挂 maintenance 任务族（m2-1 分发位）
3. **恢复演练**（benchmarks/ 报告归档）：快照 → 新环境恢复 → 跑迁移 → 抽查检索与矩阵子集 → 数据完整、检索正常、user_version/schema_migrations 前进；RPO ≤24h / RTO ≤4h 口径记录（G-5 快照目的地缺口维持 known-gaps 登记）
4. RUNBOOK.md 补备份恢复节（活文档——supervised-coding 落笔框架、coder 供演练数据）

**承接遗留事项**（m2-1 移交 23 项中归本段，分级）：

**必做**（Committer R4 §四 明示 m2-2 首个 commit 顺带）：
1. **e2e_03 同族轮询补丁**：`test_e2e_03_reclaim.py:141` 退出条件 `done/failed OR full` → AND（P3-x′ 同款）+ **P3-N14**（subprocess 测试 flag 竞态 + supervisor.proc 观察窗——工厂「首任务必 crash/必慢」模式或 flag 先写）
2. **RUNBOOK 0005 注记**：存量 `target_version=NULL` 任务取消/耗尽清扫只落任务行、文档侧不触碰（可能残留 parsing，需人工/重传）；run_task 回退 `_effective_version`（P3-N3；修正 m2-1 R2「回退旧口径」措辞）
3. **worker_mode 常量收敛**：config.py:97/:158 两处字面量 → 模块级常量（防同类漂移）
4. **docs/归档批入库**（独立 chore commit，沿 9997b12/78c3f7f 先例——消息 `[task-knowledge-lattice-m2-2] chore: 流程检查点归档`）：①TEST-CASES v1.8.2（supervised-coding 已落笔工作区——§六 M2 行 m2-1 段注记）原样入库；②m2-1 检查点（done 终态）入库 + m1-2/m1-3/m1-5 清偿注记（supervised-coding 已落笔工作区）原样入库——**全部禁改内容**；本段交付后 v1.9 回写（TC-OPS 组完成态）由 supervised-coding 落笔

**顺手/评估**（属实则修、零成本顺手、否则记录顺移）：P3-N2（P1 集成测试 real_switch 线程绑定）、P3-N4（per-claim worker_id）、P3-N5（create_document 版本计算窗口）、P3-N7（清扫 UPDATE 节流——本段接 maintenance 扩展时顺手）、P3-N8（target_version 入 API payload）、P3-N10（config 数值校验）、P3-N11（MAINTENANCE_BODIES 措辞/注册表——本段加任务体时顺手兑现注册表）、P3-N13（supervisor 指数退避+stop join）、P3-R4-1（update_task(failed) 条件写）、P3-R4-2（completed 路径清 active_error）

**继续顺移（记录项，不强制本轮）**：P3-N6/N9/N12/N15/N16/N17/N18、双探针 gate 共享（可选收口）、Tester P3-c/P3-d

**口径与边界**：

- T20 退役审计半句、TC-OPS-03（审计访问分级）/06（CSV）/07（维度退役）/08（grants 替换）归 m2-3 管理面段——本段不做（TC-OPS-01 的八类权限事件中「授权替换/取值停用/维度退役」三类依赖管理面写端点，本段以**既有端点可触发的事件**验收并预留类型常量；管理面落地后补验——TEST-CASES 回写时注明分批口径）
- docs/ 正文不动（无决策变更）；TEST-CASES/RUNBOOK 活文档回写由 supervised-coding 落笔（coder 禁改，除指定原样 commit 项）
- 分层纪律：SQL 下沉双方言；audit/backup 差异在 store/<dialect> 包内吸收
- commit 格式 `[task-knowledge-lattice-m2-2] R<n>`，develop_opencode 分支（需先 reset 到 origin/develop=739bbf3 或基于其新建——m2-1 已合入），commit 前同步 origin/develop，不 push
- 新测试文件模块前缀命名（ops_/audit_/bak_/e2e_ 等），新建前 `git ls-files tests/` 查同名
- 门禁基线 **753+1 双后端双模式 0 skipped**（m2-1 终态）——零回归硬约束

**验收标准**：

- TC-OPS-01：outbox 同事务写入（本段可触发事件类 + 崩溃注入同生共死）+ 搬运回填 shipped_at
- TC-OPS-02：月库滚动/封存只读/append-only ABORT/12 个月保留删除/哈希链（首条引用上月末、封存记末）
- TC-OPS-04：删除级联 + 删库 RESTRICT 明确报错（**T19 半句收口**）+ 先删文档后删库成功
- TC-OPS-05：双后端备份快照 + 恢复演练通过（演练报告归 benchmarks/）+ RUNBOOK 备份节
- 承接必做 4 项清偿（e2e_03 补丁/RUNBOOK 0005/常量收敛/docs 批入库）；顺手项处理或记录
- 门禁 753+1 起、双后端双模式全绿 0 skipped（新增用例计入）

## 需求确认

- [x] 用户已确认（2026-10-29 09:42「同意」——status=implementing；**用户重申跨检查点会话隔离纪律：本检查点 Coder/Tester/Committer 全新会话（不续接 m2-1 的 ses_e7f15…/ses_e7ec…/ses_e7eb2…），检查点内多轮才各自续接**；分支已 ff 至 739bbf3）
- 历史遗留事项清单：m2-1 移交 23 项（其检查点「遗留事项」节）——必做 4 项并入本段、顺手 10 项评估处理、其余顺移；m1-2 P3-6（outbox 非同事务+上传无审计）并入 A 组；T19 删库半句（M1 验收限定）并入 C 组。TC-OPS-03/06/07/08 与 T20 半句归 m2-3 管理面段不在本段

## 遗留事项（跨任务移交）

- [ ] 无（本段新增移交项随轮次记录登记）

## 轮次记录

- （待填）

## 最新验证意见原文

- （待填）
