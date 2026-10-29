---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2-2
target: knowledge-lattice
coderTaskId: ses_e7aa92652ffelY4GKwStpEK3Zv
testerTaskId: ses_e7a664ca0ffeUizUfw9UtN65Nm
committerTaskId: ses_e7a4cd604ffe7I3RsgppN609Bz
status: done
round: 3
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 8f385dc5321045849a82ef42f67e94c44e757507
reviewedSha: 8f385dc5321045849a82ef42f67e94c44e757507
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [RUNBOOK.md, .env.example, src/knowledge_lattice/domain/audit_events.py, src/knowledge_lattice/store/audit_chain.py, src/knowledge_lattice/store/sqlite/backup.py, src/knowledge_lattice/store/postgres/backup.py, src/knowledge_lattice/store/backend.py, src/knowledge_lattice/store/sqlite/backend.py, src/knowledge_lattice/store/sqlite/audit.py, src/knowledge_lattice/store/postgres/backend.py, src/knowledge_lattice/store/postgres/audit.py, src/knowledge_lattice/core/docs/ingest.py, src/knowledge_lattice/core/docs/credentials.py, src/knowledge_lattice/worker/maintenance.py, src/knowledge_lattice/worker/runner.py, src/knowledge_lattice/config.py, src/knowledge_lattice/api/admin.py, src/knowledge_lattice/api/tasks.py, src/knowledge_lattice/store/backup_common.py, tests/test_ops_01_outbox.py, tests/test_ops_02_monthly.py, tests/test_ops_04_delete_dataset.py, tests/test_ops_05_backup.py, tests/test_p3_followups_m2_2.py, tests/test_r2_p2_fixes.py, tests/m2_worker_services.py, tests/test_e2e_03_reclaim.py, tests/test_task_01_lease.py, benchmarks/dr_ops05_drill.py, benchmarks/report-m2-2-ops05.md]
endReason: null
createdAt: 2026-10-29T09:40:22+0800
updatedAt: 2026-10-29T15:05:17+0800
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

**本段已清偿**：
- [x] m2-1 移交必做 4 项（e2e_03 补丁+P3-N14 / RUNBOOK 0005 注记 / WORKER_MODE 常量 / chore 归档批）
- [x] m2-1 移交顺手 10 项（9 修 1 核销——R1 批）
- [x] 边界②裁定承载（outbox trim——R2 批 P3-1）
- [x] T19 删库半句（M1 验收限定——RESTRICT 收口）

**新移交**（Committer R3 §④ 终态清单）：
- [ ] **known-gaps 登记（supervised-coding 落笔——随本段 docs 批）**：A1 sqlite 月库 rowid 跨 VACUUM 稳定性（现码无月库 VACUUM 路径；未来纳入备份/压缩则 rowid 序验证可断——m2-3 审计读路径按 prev_hash 链遍历）；A2 pg seq 首次部署 rewrite 运维口径（volatile DEFAULT 全表 rewrite ACCESS EXCLUSIVE——升级先跑连接工厂避启动窗口；RUNBOOK 注记）
- [ ] **m2-3 收编**：B1 upload.reclaim 等字面量常量；B2 审计读路径 prev_hash 链遍历；B3 审计月库纳入备份口径（边界新①——sqlite snapshot 仅主库+objects，audit_*.db 未备份恢复后审计历史全失；RUNBOOK 备份节明确范围、自动快照随 m2-3）；B4 stats 新键 audit_outbox_trimmed 同步运维面板；B5 R1 期行语义列 detail_json 兜底口径；B6 last_row_hash NULLS 防御分支修正（ASC 或 WHERE seq IS NOT NULL）+ 显式 NULL seq 探针
- [ ] **记录不修**：C 组（P3-4 delete_dataset TOCTOU / P3-6 checkpoint busy / P3-7 _ensured 缓存 / P3-9 drill 收尾 / P3-10 补偿无审计 / P3-14 DSN argv / P3-16 零碎 / P3-新④ outbox 索引与 existed 定向 / P3-新⑥ 工具探测不验证可运行性）
- [ ] 编排侧交付前置（本段 docs 批落笔）：RUNBOOK 备份恢复节（含 B3 口径+A2 注记）、偏差①口径回写 TEST-CASES、检查点证据小节与 filesChanged 补全

## 轮次记录

- **R1 coder 返回（2026-10-29 10:58，全新会话 ses_e7aa92652ffelY4GKwStpEK3Zv）**：commits `91b5804`（chore 归档批——6 文件原样：TEST-CASES v1.8.2 + m2-1/m2-2 检查点 + m1-2/3/5 清偿注记，未含 supervised-coding.md）+ `066bf23`（066bf230cc4b778a88d84541e20dcbd97a63f050，R1 主批 28 files +3544/−297——origin/develop 已同步、未 push）。**交付**：A outbox 链路（domain/audit_events.py 事件登记处——docs 7 类实装+semantic 3 类+管理面 3 类预留常量；7 治理方法同事务接入；搬运任务挂 maintenance——ship→seal→prune 顺序；崩溃注入双向断言）；B 月库（哈希链 audit_chain.py canonical 冻结序、封存 0444+sidecar / pg seals 表、append-only 双态、12 月保留、保留期/封存守卫）；C 删库（DatasetNotEmptyError RESTRICT + DELETE /datasets 端点 + 级联补断言——**T19 半句收口**）；D 备份（双方言 backup.py + objects tar + maintenance 快照任务体 + 演练脚本/报告双臂 DRILL PASS + RPO/RTO 口径 + G-5 登记）。**必做 4 项全清**（e2e_03 OR→AND+SLOW_FIRST、RUNBOOK 0005 注记、WORKER_MODE 常量+专测、chore 归档批）；**顺手 10 项：9 修 1 核销**（P3-N2 修出并修 setup_connection DDL 竞态、N4 per-claim id、N5 事务内自算、N7 节流、N8/N10/N11/N13、R4-1 LIKE 参数化——取消终态零行强化、R4-2 核销〔既有成功态清 error〕）；零成本附加 N6/N12/N9。**自测**：门禁 **810+1 双后端双模式 0 skipped**（753+1→+57：ops_01=21/ops_02=8/ops_04=7/ops_05=7/p3_followups=14；pg 臂 289）；TC-OPS 专项 57p 附文件清单；pg 真并发 SKIP LOCKED 首次双连接触达 3 连过。**移交申报 6 项**：①sqlite 跨库事务非原子（WAL 无 super-journal——A2 搬运两步幂等形态，与任务书「同事务」字面偏差、注释显式声明供裁定）②pg 备份容器依赖（LATTICE_PG_DUMP_CMD docker exec；backup 对 BackupToolError 记 unavailable 不判任务失败）③哈希链 canonical 序冻结④update_task 第三分支强化⑤CRASH_FLAG 保留/SLOW_FLAG 目录模式弃用⑥maintenance stats 新增 4 键。**验证证据小节完整，待 Tester。**
- **Tester R1（2026-10-29 11:26，全新会话 ses_e7a664ca0ffeUizUfw9UtN65Nm）：PASS**。门禁 810+1 双模式 0 skipped 独立复跑（pg 臂 289）；+57 逐文件对账闭合（5 新文件 33 def，存量 3 文件 def 计数不变零删除）；**偏差①独立实证**：自制三形态崩溃注入（跨月批第 2 月 commit 中途崩/月内 INSERT 未提交崩/真进程 os._exit(1)）——5 行不丢不重、5 节哈希链 prev 链接+canonical 重算双验证、真进程级「同生共死」物理证明（业务与 outbox 双双不存在/双双在）——**裁定建议：接受**（sqlite WAL 无跨库原子事务为物理约束，两步幂等效果等价；pg 臂真同库单事务字面满足；建议活文档回写注明口径）；TC-OPS-02 哈希链跨月衔接/封存双形态/append-only 双态/保留期全核实；TC-OPS-04 T19 RESTRICT 专用异常+中文指引+409/404/403 端点全链；TC-OPS-05 演练双臂独立复现 DRILL PASS（数值吻合、objects tar 抽查、防路径穿越核实）；承接抽查 5 项属实（P3-N2 真并发/N4 per-claim/R4-1 零行/N5 事务内自算/R4-2 核销理由成立）；chore 批原样（28=28 无缺无增、未含 supervised-coding.md）；docs 零触碰（仅 TEST-CASES 2 行 chore 批）；零弱化零回归。**P3×3 不阻断**：①maintenance docstring 与 backup unavailable 语义不符（建议下轮修 docstring 或区分工具缺失/失败两态）②test_ops_05:261 条件 skip 未触发备查③检查点无独立验证证据小节（R1 内联覆盖，归档时补）。**RUNBOOK 备份节归 supervised-coding 落笔（D.4 分工——编排侧待办）**。testedSha=066bf230cc4b778a88d84541e20dcbd97a63f050。意见原文存「最新验证意见原文」节。**待 Committer。**
- **Committer R1（2026-10-29 11:38，全新会话 ses_e7a4cd604ffe7I3RsgppN609Bz）：NEEDS_CHANGES**。审查基线 739bbf3..066bf23（34 files +4560/−302 与申报一致）；分层✓（audit_chain 纯计算沿 taskclock 先例、零新依赖）；A 组 8 接入点逐一核实真同事务✓、语义/管理面仅常量未越界✓；安全面✓（list[str]+无 shell、LATTICE_PG_DUMP_CMD 部署信任域无注入、tar data 过滤器）；**偏差①裁定：接受**（与 Tester 一致——但「链完整」半句要 P2-2 修复后才成立，修复后补同月新事件崩溃注入实证）。**P2×4**：**P2-1 哈希链排序键≠插入序**（同秒并列时 (created_at,id) 全序与链尾错位——sqlite 秒精度+uuid4 随机 id、pg µs 截断；修法=链序定义插入序四路同源：sqlite rowid / pg seq 列或取消 µs 截断；现有用例全用不同秒恰绕过）；**P2-2 sqlite 搬运重试污染 prev**（崩溃窗口后已落库行被用错误 prev 重算推进——同月再入新事件必断链；修法=搬运前取已存 id→row_hash，已存行不重算不推进）；**P2-3 update_task running 分支无终态守卫**（取消在租约/执行起步窗口被复活——取消落账后 running 写把 failed(cancelled) 改 running 且永久滞留或复活跑完；修法=第一分支补 AND status IN 三态；TC-TASK-03 违例）；**P2-4 backup 工具缺失与真实失败混同**（pg_dump 真实失败降级 stats 字符串任务 done——NFR-10 可发现信号不成立；Tester P3-① 升级；修法=拆 BackupToolUnavailable 两态、真实失败落 errors 任务 failed、异常类移中立模块顺解 P3-15）。**P3×16**（★低成本高收益：P3-1 outbox 已搬运行永不清理/P3-2 事件语义列弱〔m2-3 审计分级受影响〕/P3-8 test_ops_05 条件 skip+PATH 断死 unavailable 门禁隐患/P3-11 untag 锚点应在 src/P3-13 N12 申报不成立〔env 映射了但 get_settings 不读〕/P3-15；其余：P3-3 协议签名漂移/P3-4 delete_dataset TOCTOU/P3-5 封存 chmod 崩溃窗/P3-6 checkpoint busy/P3-7 _ensured 缓存/P3-9 drill 结论误导/P3-10 输家补偿无审计/P3-12 常量登记未闭环/P3-14 DSN 入 argv/P3-16 零碎）。**边界 3 条**：①偏差①口径回写 TEST-CASES/RUNBOOK（supervised-coding——前提 P2-2 修复）②**outbox 已搬运行保留期是否纳入 FR-6 12 个月口径——任务书未定，需用户拍板**（R2 顺手修 or 登记移交）③RUNBOOK 备份节+检查点证据小节（编排侧交付前置待办）。**R2 建议范围：P2×4 全修带回归 + P3 顺手收 P3-1/2/3/5/8/11/13/15。**意见原文存「最新验证意见原文」节。**status=spec_confirm 待边界②拍板。**
- **边界②裁定（2026-10-29 11:40 用户「按建议执行」= (a) 并入 R2 顺手修）**：outbox 已搬运行纳入保留期清理——R2 加 trim 任务体（DELETE WHERE shipped_at IS NOT NULL AND shipped_at < 保留期，只删已搬运行——审计真相在月库，outbox 为投递队列；P3-1 承载）。**round→2、status=implementing、reviewedSha 置空；coder R2 范围：P2-1~4 全修带回归 + ★P3 顺手项（P3-1〔含本裁定〕/2/3/5/8/11/13/15）+ 偏差①修复后补同月新事件崩溃注入实证（Committer ④ 要求）。**边界①口径回写与边界③ RUNBOOK 备份节（编排侧）挂 R2 修复后/交付前置落笔。
- **R2 coder 返回（2026-10-29 12:00，续接会话）**：commit `0e0bcf8`（0e0bcf873a5376ca8220735fe39340d41c256652，13 files +646/−75——origin/develop 已同步、未 push）。**修复**：P2-1 链序=插入序四路同源（sqlite rowid / **pg 选 seq 序列列**——µs 方案对同事务批量 INSERT 无效〔CURRENT_TIMESTAMP 事务内恒定〕；幂等 ensure 落 audit.py 不新增迁移；存量行 NULL 段 NULLS FIRST 兜底零回填零触发器操作；canonical 不含 seq）；P2-2 搬运前取已存 id→row_hash、已存行不重算不推进（**偏差①补充实证**：崩溃窗口+同月新事件 5 行链完整）；P2-3 running 分支非终态谓词（双臂：cancel 后 running 零行、正常链不受影响、done 不复活）；P2-4 两态拆分（BackupToolUnavailable 中立模块 store/backup_common.py——顺解 P3-15；真实失败任务 failed 带 backup_snapshot 前缀；docstring 一致化）。**P3 顺手 8 项**：P3-1 outbox trim 任务体（cutoff 与 audit_keep_months 同源，只删已搬运行——边界②裁定承载）/P3-2 语义列投影（actor 回退链+target 按事件类型映射）/P3-3 协议签名同步+backup_snapshot 移 Admin 域/P3-5 封存 chmod 先行+半封存态补写+早退重放/P3-8 条件 skip 删除（工具可用性分支）/P3-11 untag 锚点落 src 三处/P3-13 get_settings 补三行 env 读取+往返断言/P3-12 maintenance.run 改常量。**自测**：门禁 **825+1 双后端双模式 0 skipped**（810→+15：test_r2_p2_fixes 13+backup failure 双臂 2；pg 臂 296）；P2-1 修前必败实证（stash 后 R1 代码 AssertionError 读序错位）。**移交申报 5 项**：①pg seq 存量 NULL 段对 R1 期历史行非严格插入序（POC 无生产存量、新行起严格——需历史严格化再登记专项）②绕过 DEFAULT 的显式造数需带 seq（测试已知悉）③P3-4/6/7/9/10/12 余量/14/16 记录移交④backup failure 用例 os.environ 直改+finally 恢复⑤stats 新增 audit_outbox_trimmed 键（m2-3 运维面板需同步）。**验证证据小节完整（附文件清单），待 Tester R2。**
- **Tester R2（2026-10-29 12:44，续接会话）：PASS**。门禁 825+1 双模式 0 skipped 独立复跑（pg 臂 296）；+15 逐用例对账闭合（r2_p2_fixes 7 函数=13 + backup 2）。**「修前必败」独立复现**：自制 R1 树副本（cp -R + git show 覆盖 10 文件）跑新用例 → **11 failed/2 passed**（2 个 passed 有方言形态学解释：P2-2 pg 单事务天然免疫/P3-5 半封存态 sqlite 专属）——每个 P2 用例真能抓住 R1 缺陷。**pg seq 实测定谳**（自制探针 PG-SEQ PASS）：幂等二跑/分区传播（pg_inherits 实查）/同事务批量各自求值递增（3,4,5）——选型理由实证；**存量行实测被填连续 seq（rewrite 逐行求值）优于申报①的 NULL 段保守描述**（方向=申报偏保守非缺陷）。**P2-2+偏差①终验**：独立探针双次崩溃+同秒 id 逆序交叉形态（7 行不丢不重、读序=链序、7 节链完整、封存末哈希=链尾）+ R1 三探针新代码全收敛。P2-3/P2-4 两态断言真实性核实（docstring 一致化✓、backup_common 分层✓、worker/core 零反向 import✓）。P3 8 项全部属实（含 P3-12 余量 upload.reclaim 系 m1-3 既有 R2 未触碰）。R2 diff 13 文件零越界、docs 零触碰、移交 P3 未处理项保持原样属实。**DRILL 双臂 R2 版独立复跑 PASS**。**P3×3 不阻断**：①申报①「存量 NULL 段」表述按实测口径修正登记（实际更优）②**sqlite rowid 跨 VACUUM 稳定性新观察**（无 INTEGER PK 表 rowid 不保证跨 VACUUM 保留——VACUUM INTO 恢复产物按读序链验证理论可断；建议 m2-3 审计读路径按 prev_hash 链遍历或登记 known-gaps）③upload.reclaim 字面量随 m2-3 收编。testedSha=0e0bcf873a5376ca8220735fe39340d41c256652。意见原文存「最新验证意见原文」节。**待 Committer R2 闭环复审。**
- **Committer R2 闭环终审（2026-10-29 12:56，续接会话）：NEEDS_CHANGES**。你 R1 的 P2×4 **全部 CLOSED**（P2-1 pg seq 实现形态接受——volatile DEFAULT rewrite 逐行求值效果优于处方窗口回填；P2-3 函数级完备性核查无漏网分支；偏差①**终态接受**〔附加条件满足——口径可回写：写侧同事务双方言/搬运侧 sqlite 两步幂等 pg 单事务〕；rowid/VACUUM 裁定登记 known-gaps + m2-3 按 prev_hash 遍历）；P3 顺手 8 项全 CLOSED（backup_snapshot 域归属 Admin 接受）。**唯一不可妥协项 P2-新①（时间炸弹）**：test_r2_p2_fixes.py:78（双臂）与 :274（pg 臂）的封存集断言 `["202610","202611"]` 中 202610 来自连接工厂当前月——**2026-11 起门禁必红**（时间依赖用例未造数，违反 TEST-CASES 口径段；R1 的 test_ops_02 同款断言稳定因它显式造了 OCT）。修法二选一：目标月成员断言+封存末哈希实断言（推荐，顺修 P3-新⑤ 同义反复）/ 照 test_ops_02 显式造 OCT。**P3-新②~⑦**：②seq 注释与实测不符+NULLS 方向反（防御分支不可达）③首次部署 rewrite 运维注记（RUNBOOK/PG 接线段）④outbox 索引与 existed 全月读（性能）⑤read_monthly_events docstring 旧序+封存末哈希断言同义反复（与①合并修）⑥工具探测不验证可运行性⑦trim 用例墙钟依赖（2027-12 起红——与①同批修）。**边界新①**：sqlite 备份不含审计月库（任务书 D1 未点名——RUNBOOK 备份节明确口径 + m2-3 收编，非本轮阻塞）。**R3 最小范围：P2-新① + P3-新⑤②⑦ 顺手，+0 增量纯测试/注释改动，R3 闭环即 APPROVED（代码语义面已无 P1/P2 未决）。round→3（maxRounds=3 最终轮）。**意见原文存「最新验证意见原文」节。
- **R3 coder 返回（2026-10-29 14:31，续接会话）**：commit `8f385dc`（8f385dc5321045849a82ef42f67e94c44e757507，5 files +59/−26——origin/develop 已同步、未 push）。**修复**：P2-新① 两处封存集断言 → `"202611" in sealed`（当前月依赖根除）+ 末哈希改**存储介质实断言**（sqlite read_seal sidecar / pg SELECT audit_month_seals——顺修 P3-新⑤ 同义反复）；P3-新⑤ 双方言 read_monthly_events docstring 改插入序口径；P3-新② pg seq 注释按 PG 16 实测改写（rewrite 逐行求值/幂等/NULL 防御分支可达性）+ `last_row_hash` 与读序 `(seq IS NULL) DESC` 方向修正（NULL 前=旧行前）；P3-新⑦ trim 用例 monkeypatch `maintenance.utc_now_ts` 固定墙钟（cutoff 恒 2025-11-01，2027-12 红线根除——run_maintenance now 单一来源全链生效）。**自测**：门禁 **825+1 双后端双模式 0 skipped**（与 R2 持平、+0 增量、pg 臂 296）；定向复跑 51p；改后断言形态摘录在案。**移交申报 3 项**：P3-新③ 归 RUNBOOK/PG 接线段（supervised-coding）、NULL 防御分支语义注（链自洽不受影响）、④⑥/边界新① 记录移交零触碰。**验证证据小节完整，待 Tester R3。**
- **Tester R3（2026-10-29 14:43，续接会话）：PASS（终态）**。**P2-新① 时间炸弹根除实测双向实证**（BREACH PROBE 双臂：预建工厂当月=202611 形态+移除 202610 纯化 → R3 成员断言+介质实断言全绿 / **R2 旧断言同形态实测必红**——Committer 判定成立、修复有效；含 202612 更远形态）；介质实断言真读 sidecar/seals 非同义反复✓；P3-新⑦ 墙钟单一来源 patch（maintenance 命名空间唯一调用点 L159）+ 定向强证据（真实月 10 月若 patch 失效必红、绿即生效）；P3-新② 注释与 R2 探针实测逐句吻合、NULLS DESC 读序正确；**P3 保留一项**（last_row_hash 的 NULLS DESC 防御分支与注释自相矛盾——显式 NULL seq 造数场景 LIMIT 1 误取、实测不可达零行为差异——随 m2-3 收口改 ASC 或补 WHERE seq IS NOT NULL）；门禁 **825+1 双后端双模式 0 skipped** 独立复跑持平 R2、+0 增量核实（唯一 diff = trim 用例签名加 monkeypatch）；R3 diff 5 文件零越界、docs/RUNBOOK 零触碰。testedSha=8f385dc5321045849a82ef42f67e94c44e757507。意见原文存「最新验证意见原文」节。**待 Committer R3 最终闭环（其 R2 预告：R3 闭环即 APPROVED）。**
- **Committer R3 最终闭环（2026-10-29 14:48，续接会话）：APPROVED**。P2-新① 修法与 R2 处方①逐字吻合（成员断言+介质实断言），Tester 11 月击穿形态双向实测采信（R3 绿/R2 旧断言红）；P3-新⑤②⑦ 落地属实；R3 支持路径语义零改动逐 hunk 核实（唯一行为面=不可达 NULL-seq 分支）；**Tester 保留 P3（last_row_hash NULLS 防御分支与 docstring 矛盾）裁定登记 m2-3 不阻断**（不可达零行为差异、maxRounds 终态不成比例、m2-3 审计读路径一并修）。**双通过达成：testVerdict=PASS（R3）+ reviewVerdict=APPROVED（R3）、双 SHA=8f385dc → status=approved。**编排侧交付前置三件 + 遗留清单终态（known-gaps A1 rowid/VACUUM+A2 seq rewrite / m2-3 收编 B1~B6 / 记录不修 C 组）见其报告 §④⑤。意见原文存「最新验证意见原文」节。
- **编排侧交付前置落笔完成（2026-10-29 14:52，supervised-coding 执笔——工作区 3+1 文件）**：①TEST-CASES v1.8.3（TC-OPS-01 搬运侧方言口径 / TC-OPS-02 链序插入序 / TC-OPS-05 备份范围——偏差①终态回写）②known-gaps G-13（rowid/VACUUM）+ G-14（seq 首次部署 rewrite）③RUNBOOK §4 备份恢复 Runbook（双后端 + sqlite 月库口径〔B3〕+ seq rewrite 注记〔A2〕+ 失败可发现性）④检查点自身更新（证据小节 + filesChanged 30 项 + 遗留清单）。**随交付 docs 批原样 commit。**
- **交付确认（2026-10-29 14:52 用户「同意」）**：交付链启动——①Coder docs 批 commit + push + PR ②Committer 评审留痕 ③manifest 入 PR ④汇报合入请求（不自动合入）。
- **交付①完成（Coder，2026-10-29 14:5x）**：docs 批 `1a272f9`（1a272f90c7b1792792f84d666785654cac9c8e4e，4 文件 +677/−18 原样、未含 supervised-coding.md）→ 同步 Already up to date → push `830d6a7..1a272f9`（SSH）→ **PR #3** 开立（https://github.com/yq3/knowledge-lattice/pull/3，base=develop，MERGEABLE，commits=5 逐一对应；body 含验证/偏差①终态/裁定/遗留 + Evidence Manifest 占位节）。
- **交付②完成（Committer，2026-10-29 14:57）**：`--approve` 平台拒绝（self-approve——PR 作者=gh 用户 yq3，沿 PR #2 先例）；**回退 COMMENTED 留痕**：review id `PRR_kwDOVZ9dhM8AAAABU2LQEA`（2026-10-29T06:57:30Z，锚定 PR HEAD 1a272f9、正文注明代码终态 reviewedSha=8f385dc），正文首行 APPROVED（R3 结论）+ 全链闭环/验收证据/裁定记录。**留痕中发现 RUNBOOK §4 两处 doc 侧非阻断项**（LATTICE_BACKUP_DIR 臆造配置名/§4.2 命令形态与实现不符）→ 已转交付③勘误。
- **交付③完成（Coder，2026-10-29 15:03）**：①RUNBOOK §4 勘误 commit `6d223c0`（supervised-coding 修正 3 处原样入库——§4.1 臆造配置名改固定路径 data/backups/、§4.2 stdout 流实现形态、§4.3 巡检引用；push 1a272f9..6d223c0）②Evidence Manifest JSON 入 PR #3 description（docsErrata=6d223c0 实填、JSON 解析通过、双 SHA 对齐、body 其余逐字节未动）。**PR #3 终态：OPEN/MERGEABLE、commits=6。交付链完成——待用户合入（不自动合入）。合入后：supervised-coding 落 §六 M2 行 m2-2 段完成态（v1.9）+ 检查点 done + 来源清偿回写 + 下一段 m2s-1（语义轨道首段——按段序 m2-2 后为 m2s-1，检查点另建）。**
- **合入完成（2026-10-29 15:05 用户指令「合入」）**：PR #3 state=**MERGED**，mergedAt=2026-10-29T07:05:03Z，mergeCommit=`27d2a17516121ad045523a05420d2e959bf91ef0`；origin/develop 前进 `739bbf3..27d2a17`（6 commits 全量入库）。**m2-2 正式完成（done）。**收尾：①§六 M2 行 m2-2 段完成态落笔（TEST-CASES v1.9——工作区，随下段 chore 归档批入库）②m2-1 检查点遗留清偿回写。下一段 m2s-1（语义轨道首段）。

## 最新验证意见原文

- （待填——后续轮次意见将续接）

<details><summary>Tester R1 报告原文（2026-10-29 11:26，全新会话 ses_e7a664ca0ffeUizUfw9UtN65Nm）</summary>

# task-knowledge-lattice-m2-2 R1 Tester 独立验收报告

**testedSha = `066bf230cc4b778a88d84541e20dcbd97a63f050` = HEAD（develop_opencode，已确认 `git rev-parse`）**
**工作区现状**：仅 `.opencode/` 2 个流程文件未提交改动（supervised-coding 编排方落笔），业务代码零残留。

---

## 一、门禁全量独立复跑（清单项 1）

```
LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice scripts/test_gate.sh
```

| 项 | 结果 | 与申报对账 |
|---|---|---|
| pg 臂收集 | **289**（[pg] 参数化 256 + PG 专用 33）全实跑 | ✅ 一致 |
| 常规模式 | **810 passed, 1 deselected, 0 skipped**（94.26s） | ✅ 一致 |
| `-O` 模式 | **810 passed, 1 deselected, 0 skipped**（141.06s） | ✅ 一致（两模式独立执行，耗时/警告数不同证实非复用结果） |
| 门禁结论 | **GATE PASS** | ✅ |

**+57 逐文件对账**（753→810）：

| 文件 | def test | 参数化 | 计入 |
|---|---|---|---|
| test_ops_01_outbox.py | 11 | 10×2 + 1 常量 | 21 |
| test_ops_02_monthly.py | 4 | 4×2 | 8 |
| test_ops_04_delete_dataset.py | 4 | 3×2 + 1 REST(sqlite) | 7 |
| test_ops_05_backup.py | 5 | 2 sqlite臂 + 1 pg臂 + 2×2 | 7 |
| test_p3_followups_m2_2.py | 9 | 5×2 + 1 REST + 3 进程级 | 14 |
| **合计** | 33 | | **57** = 810−753 ✅ |

**零删除核验**：commit 触达的存量测试仅 3 文件——`test_e2e_03_reclaim`（1→1 def）、`test_task_01_lease`（6→6 def）、`m2_worker_services.py`（helper，非收集对象）；其余 tests/ 零触碰。skip 总数 = **0**（唯一潜在条件 skip：`test_ops_05_backup.py:261` pg 臂注入 `LATTICE_PG_DUMP_CMD` 时跳过——门禁环境未设该 env，未触发）。

## 二、TC-OPS-01 outbox 一致性（清单项 2）

- **同事务写入**：`_outbox_insert`（sqlite `backend.py:1578`/pg `:1585`）不自行 commit、参与调用方事务。调用点逐一定位：create_document/upload、start_overwrite、delete_document、cancel_task、set_document_dims、create_upload_credential、mark_upload_consumed（7 治理）+ delete_dataset = **8 个同事务接入点**；maintenance.run 走 append_outbox（任务级，既有形态）。凭证签发/消费改造（`core/docs/credentials.py` diff）与取消审计（`:1264`，取消生效才记）均落实。语义 3 类 + 管理面 3 类仅常量预留（`domain/audit_events.py:35-46`）✅
- **崩溃注入真实性**：coder 测试注入点为事务内锚点方法 raise（业务语句已执行未提交→一并回滚+双向断言）。我**另做真进程级独立验证**（见下 Probe C）。
- **搬运回填**：`ship_outbox` shipped_at IS NULL → 月库（按事件原时刻路由）+ 回填；重复搬运零行 ✅

### 偏差①独立验证（Tester 自制注入，非复跑 coder 测试）

```
uv run python /var/folders/.../m22/test/crash_convergence_probe.py
```

- **Probe A（跨月批·第 2 月 commit 中途崩溃）**：中间态确证——1 月 2 行已提交留存、2 月空、5 行未回填 → 重跑 → **5 行不丢不重、5 节哈希链完整（prev 链接+canonical 重算双验证）、shipped_at 全回填**；三跑幂等。
- **Probe B（月内 INSERT 中途崩溃、事务未提交）**：close 回滚 → 重跑 → 3 行收敛、链完整。
- **Probe C（真进程 `os._exit(1)` 未 commit）**：重开库业务行与 outbox 行**双双不存在**（同生共死物理证明）；commit 形态双双在。

**裁定建议（偏差①：sqlite 搬运两步幂等 vs 任务书「同事务：搬运+回填」字面）——可接受**。理由：①SQLite WAL 跨文件无原子多库事务（super-journal 不可用），两步形态是该约束下的正确工程解；②pg 臂为真同库单事务（`postgres/backend.py:1611-1650` BEGIN…COMMIT 内含 mark_shipped），任务书字面在 pg 侧完整满足；③sqlite 侧经我三形态独立崩溃注入实证收敛到同一不变式（不丢不重+链完整），与「同事务」的**效果等价**——任务 A 组核心语义「业务改了就一定有审计」由写侧真同事务保证，与搬运侧形态无关；④偏差已在代码注释显式声明（`sqlite/backend.py:1631-1633`）。建议 supervised-coding 回写 TEST-CASES/RUNBOOK 时注明 sqlite 两步幂等口径（活文档，非本轮阻塞）。

## 三、TC-OPS-02 月库（清单项 3）

- 跨月滚动+哈希链：10 月创世（prev=None）→ 11 月首条 prev=10 月末 row_hash → 封存后 12 月链从 11 月末继续；`_verify_chain` 逐条重算 canonical ✅（门禁双臂通过）
- 封存双形态：sqlite sidecar（month/last_hash/rows/sealed_at）+ 0444 双文件；pg `audit_month_seals` 表 + sealed 触发器 + REVOKE ✅
- append-only：当月 UPDATE/DELETE 触发器 ABORT（双方言）+ 已封存 sqlite readonly 拒写/pg sealed EXCEPTION ✅
- 保留期：13 个月前整删（sqlite 文件+sidecar/pg DROP 分区）、12 个月边界月保留、二跑幂等 ✅
- 封存守卫：有未搬运行的月份 skip（`skipped_pending`），搬运后下轮再封 ✅
- canonical 序冻结于 `audit_chain._CHAIN_FIELDS`（10 字段、\x1f join）✅（申报③属实）

## 四、TC-OPS-04 删除级联与删库（清单项 4）

- 级联补断言：chunks/document_dimensions/quality_flags/chunk_vectors 归零 + 非终态任务 `failed/cancelled: document deleted` + document.delete 入 outbox；M2-S3 untag 预留锚点注释在场 ✅
- **T19 半句**：`delete_dataset`（sqlite `:1787`/pg `:1785`）前置 count 检查 → `DatasetNotEmptyError("…仍有 N 篇文档——先删文档再删库（RESTRICT…）")`——专用异常类、明确中文指引，非裸 IntegrityError ✅；REST 端点 `DELETE /datasets` org_admin 门控 403 / DatasetNotEmptyError→**409** / KeyError→404 / 二删 404 幂等 / dataset.delete 同事务入 outbox ✅（`api/admin.py:70-97`）
- 先删文档后删库 → 204 成功 ✅；RESTRICT 不动数据（库与文档都在）✅

## 五、TC-OPS-05 备份恢复（清单项 5）

**独立复跑 `benchmarks/dr_ops05_drill.py` 双臂**：

| 臂 | 快照 | 恢复 | 迁移/版本 | 验证 |
|---|---|---|---|---|
| sqlite | VACUUM INTO 0.013s | 0.001s | applied=[]、user_version=5 | FTS 命中+矩阵子集 {d_multi, drill}+docs=6/tasks=1 ✅ |
| pg | pg_dump -Fc 0.125s | 新库 pg_restore 0.186s | applied=[]、schema_migrations 5 条 | FTS 命中 4+矩阵子集 {d_multi} ✅ |

**DRILL PASS 复现**，数值与 coder 申报吻合。objects tar 内容独立抽查（成员清单含造数文件）✅；`restore_objects` 用 py3.12 data 过滤器防路径穿越 ✅。RPO≤24h（backup_interval_s=86400 节流）/RTO≤4h（人工流程主导）口径在 `benchmarks/report-m2-2-ops05.md`；G-5 同盘缺口维持登记 ✅。backup 挂 maintenance（`backup_snapshot` body，节流+unavailable 语义，任务不失败）✅。**注**：RUNBOOK 备份恢复节按任务 D.4 分工归 supervised-coding 落笔（coder 供演练数据已交付）——非 coder 缺陷，编排侧待办。

## 六、承接项抽查（清单项 6）

- **e2e_03 OR→AND**（`test_e2e_03_reclaim.py:155`）+ **SLOW_FIRST**（首任务必慢消除 flag 竞态）+ 观察窗 owner-pid 断言（lease_owner 必须=speaker supervisor.proc）✅
- **WORKER_MODE 常量收敛**（`config.py:14-16` + dataclass 默认/env fallback 双引用）+ `_validate` fail-closed（P3-N10）+ 专测 ✅
- **P3-N2**：pg 臂 claim_factory 改每线程独立连接（真并发 SKIP LOCKED；注释说明跳过 setup_connection 防 DDL 竞态）✅
- **P3-N4**：run_once per-claim `claim_id = base#rand6` 贯穿 claim/heartbeat/should_continue ✅
- **P3-R4-1**：update_task 第三分支 `NOT (status='failed' AND error LIKE :pattern)` 参数化——取消终态对后续 failed 写零行，error 保留 `cancelled:` 前缀 ✅（申报④属实）
- **P3-N5**：start_overwrite 在 BEGIN IMMEDIATE 内自算 max+1 并返回（窗口闭合）✅
- **R4-2 核销理由核实成立**：成功态双路径已清 active_error——`set_doc_active_status` 成功写顺带 `active_error = NULL`（双方言 `:1393`/`:1338`）+ 切换事务清 active_error（`:451`/`:438`，m1-2 R2 既有）✅
- CRASH_FLAG 保留（test_task_04 在用）/SLOW_FLAG 能力保留但测试侧弃用（申报⑤属实）；maintenance stats 新增 audit_shipped/audit_months_sealed/audit_months_pruned/backup_snapshot 4 键（申报⑥属实）

## 七、chore 归档批原样性（清单项 7）

`91b5804` 恰 6 文件：TEST-CASES（仅 v1.8.2 版本行 + §六 M2 行注记 2 行）、m2-1/m2-2 检查点、m1-2/3/5 清偿注记各 1-2 行——**未含 supervised-coding.md** ✅；m2-2 检查点自身随批入库属合理披露（R1 记录已申报）。R1 主批 28 文件与 filesChanged 申报**精确一致（28=28，无缺无增）**。

## 八、回归与纪律（清单项 8）

- docs/ 对基线 739bbf3 的 diff：**仅 TEST-CASES.md 2 行**（chore 批）——design/requirements/known-gaps **零触碰** ✅
- RUNBOOK：仅 0005 注记 + 「M2-1→M2.1」措辞归一 ✅（口径与任务书必做 2 一致：NULL 行只落任务行、run_task 回退 `_effective_version`）
- 存量测试改动全为强化（AND 收紧/断言新增/真并发修复），零弱化零删除 ✅
- 门禁基线 753+1（m2-1 R4 PASS 终态）→ 810+1 全绿，零回归 ✅

## 九、验收标准 6 条对照（清单项 9）

| 验收标准 | 判定 |
|---|---|
| TC-OPS-01 outbox 同事务+崩溃注入同生共死+搬运回填 | ✅（含真进程崩溃独立实证） |
| TC-OPS-02 滚动/封存只读/append-only/保留期/哈希链 | ✅ |
| TC-OPS-04 级联+RESTRICT+先删后删 | ✅（T19 收口） |
| TC-OPS-05 双后端快照+演练+报告 | ✅（双臂独立复现 DRILL PASS） |
| 承接必做 4 项 + 顺手项处理 | ✅（9 修 1 核销，抽查 5 项全部属实） |
| 门禁 753+1 起双后端双模式 0 skipped | ✅ 810+1 独立复跑 |

## 问题分级

- **P1/P2：无**
- **P3（均不阻断）**：
  1. `worker/maintenance.py:104-106` docstring 称「真实快照失败（子进程非零）照常 errors」，但 `pg/backup.py:64-68` 子进程失败同样抛 `BackupToolError` → 被捕获记 `unavailable`、任务 done——docstring 与实现不符（真实 pg_dump 失败从任务失败降级为 stats 字符串，非静默但有信号弱化）。coder 申报②已如实披露该语义；建议下轮修 docstring 或区分「工具缺失/工具失败」两态。
  2. `test_ops_05_backup.py:261` 条件 skip（pg 臂注入 dump 工具时）——本轮未触发，登记备查。
  3. m2-2 检查点暂无独立「验证证据」小节（m2-1 先例有）——R1 轮次记录内联已覆盖，供 supervised-coding 归档时补。

---

## 结论

**testVerdict: PASS**

偏差①裁定建议：**接受**（sqlite 两步幂等形态效果等价于「同事务：搬运+回填」，pg 臂字面满足；三形态独立崩溃注入实证收敛，建议活文档回写时注明口径）。

testedSha：`066bf230cc4b778a88d84541e20dcbd97a63f050`（= HEAD，确认无误）

附注（移交 supervised-coding/committer）：①RUNBOOK 备份恢复节按 D.4 分工待编排方落笔；②P3 三项不阻断、随轮次记录登记；③本报告逐字转交 coder 供知悉（PASS 无强制修复项）。

</details>

<details><summary>Committer R1 报告原文（2026-10-29 11:38，全新会话 ses_e7a4cd604ffe7I3RsgppN609Bz）</summary>

# task-knowledge-lattice-m2-2 R1 Committer 审查报告

**reviewedSha = `066bf230cc4b778a88d84541e20dcbd97a63f050`（= HEAD = testedSha）**
**审查基线**：`git diff 739bbf3..066bf23` = 34 files / +4560 −302 = chore 批 `91b5804`（6 files +1016/−5）+ R1 主批 `066bf23`（28 files +3544/−297）——与申报逐项一致；`origin/develop` 仍在 `739bbf3`，`develop_opencode` ahead 3 未 push；工作区仅 `.opencode/` 2 个流程文件（编排侧落笔）未提交，业务代码零残留。
**审查限制**：本会话 bash 仅放行 git/gh 只读命令，**未独立复跑 pytest**；门禁采信 Tester R1 独立复跑输出（`810 passed, 1 deselected, 0 skipped` × 常规 + `-O`，pg 臂 289），并做静态计数对账：+57 = 810−753，逐文件收集数 21/8/7/7/14 = 57、`[pg]` 参数化 232→256 = +24 恰为新参数化用例数——**对账一致**；diff 内无 skip/删除/断言放宽（唯一条件 skip 见 P3-8）。以下语义结论均为逐行实读。

---

## ① 审查清单逐项结论

| # | 项 | 结论 | 证据 |
|---|---|---|---|
| 1 | 分层与结构 | **PASS**（含 2 项 P3） | SQL 全在 `store/<dialect>`；`store/audit_chain.py` 为纯计算（沿 `store/taskclock.py` 先例）、`domain/audit_events.py` 登记处合理（design §3 L216 明示 core 共同依赖 `store/` 与 `domain/`）；backup 差异包内吸收；零新依赖（tarfile/subprocess/shutil 标准库，D2 合规）。扣分项：协议签名漂移 P3-3、maintenance 反向 import postgres 包 P3-15 |
| 2 | A~D 边界 | **A PASS / B PARTIAL / C PASS / D PARTIAL** | A：8 个同事务接入点逐一核实为真（create_document/start_overwrite/delete_document/cancel_task/set_document_dims/create_upload_credential/mark_upload_consumed/delete_dataset），语义 3 类 + 管理面 3 类仅常量预留未越界；B：封存双形态/append-only 双态/保留期/跨月衔接均实装，**但哈希链排序键有两个实质缺陷（P2-1/P2-2）**；C：RESTRICT→409/404/403 + 级联断言 + T19 收口成立（P3-4 TOCTOU、P3-11 锚点缺失）；D：双方言 backup + objects tar + maintenance 挂接 + 演练报告齐，**但失败信号语义待修（P2-4）**，RUNBOOK 备份节=编排侧待办（③） |
| 3 | 安全面 | **PASS（1 项 P2 归入链正确性）** | 命令构造 `list[str]` + 无 `shell=True`，`LATTICE_PG_DUMP_CMD` 为部署方 env（与 PATH 同信任域）——**无注入面**；`restore_objects` 用 `filter="data"`（py3.12，路径穿越防护）；封存强度=0444+sidecar / sealed 触发器+REVOKE（防改写非防同机删改，符合任务书口径，P3-5 为崩溃窗口）；canonical 拼接 `\x1f`、UTC 钉死、秒级格式双方言一致、NULL→""——**序列化本身确定**，问题在**排序键**（P2-1）。附带：DSN 入 argv 密码可见（P3-14） |
| 4 | 偏差①认定 | **接受**（附条件，见 ④） | sqlite 两步幂等是 WAL 无跨库原子事务下的正确工程解；pg 臂 `postgres/backend.py:1609-1650` 为真同库单事务；但「效果等价」中的**链完整**半句在重试路径有洞（P2-2 必须修后才成立） |
| 5 | P3-①认定 | **不接受为 P3，升级 P2-4** | 真实 pg_dump 失败与工具缺失同抛一类异常 → 任务 done + stats 字符串；docstring 的「真实快照失败照常 errors」与代码不符 |
| 6 | 顺手 9 修抽查 | **N4/N5/N7/N8/N10/N11/N13 PASS；R4-1 半闭环（P2-3）** | N5 事务内自算+WHERE 零行兜底双方言正确（`sqlite/backend.py:504-541`/`postgres/backend.py:487-530`）；N4 claim 级 id 贯通 claim/heartbeat/should_continue/_on_failure，owner 守卫接受 base id 属兼容设计；N13 退避序列 1/2/4/8/16/30 + 60s 稳定重置 + stop join/fd 关闭核实；R4-1 只守住第三分支，`running` 分支未守（P2-3） |
| 7 | update_task 第三分支存量影响 | **部分 PASS** | 取消终态对第三分支一切写零行；`fail_exhausted_tasks` 走直连 SQL 不受影响、failed 留人工路径未被误伤；`done` 分支既有非终态谓词可挡复活——**但 `running` 分支可绕过（P2-3），与任务书「幂等续跑不复活」不一致** |
| 8 | 测试质量 | **PARTIAL** | 断言总体真实（真断言锚点 `_outbox_insert`/`_mark_shipped`、真进程级注入由 Tester 独立补齐、级联/409/404/403 全链、恢复演练双臂实跑）；**缺 P2-1/P2-2/P2-3/P2-4 四条回归**（现有链验证用例全用不同秒事件，恰好绕过 P2-1/P2-2）；P3-8 条件 skip 属门禁隐患；drill 脚本 P3-9 |
| 9 | 需求边界 | **有（3 条，均非 coder 修复项）** | 见 ③ |

---

## ② 意见清单

### P1（阻断）
**无。**

### P2（重要，建议本轮全修；P2-1/P2-2 直接关系 FR-6 验收，P2-3 关系 TC-TASK-03）

#### P2-1 哈希链排序键≠实际插入序：同秒并列时链验证与封存末哈希错误（双方言）
- **位置**：`store/sqlite/audit.py:113-124`（`last_row_hash` `ORDER BY created_at DESC, id DESC`）、`store/sqlite/backend.py:1721-1725`（`read_monthly_events` `ORDER BY created_at, id`）、`store/postgres/audit.py:178-188`、`store/postgres/backend.py:1691`；触发源 `store/postgres/backend.py:1625`（`strftime("%Y-%m-%d %H:%M:%S")` 把 µs 截成秒）、sqlite outbox `created_at` 本身只有秒精度（`0001_schema_v1.sql:267`）+ id 为 `uuid4` 随机（`sqlite/backend.py:1583`）。
- **机制**：链的 `prev` 按「本轮批内 (created_at,id) 序」逐条推进，但月库 append-only。下一轮搬运的新行若与已搬行**同秒**且 id 更小，它在 `(created_at,id)` 全序中排在已搬行之前却被追加到链尾 → 排序序≠插入序；`last_row_hash` 取排序序末条（不是真实链尾）→ 再下一行 `prev` 接错；封存 sidecar / `audit_month_seals.last_hash` 同样取错（不是真实链尾）。pg 侧因 1625 行截断 µs，同秒多事件同样失去插入序。
- **确定性复现（sqlite）**：①append 2 行 → `UPDATE audit_outbox SET created_at='2026-11-05 11:00:00', id='aud_aaa'/'aud_bbb'`（按 id 逆序）→ ship；②append 1 行 → 同秒、id `aud_000` → ship；③再 append 1 行 → ship。按 `read_monthly_events` 顺序用 `compute_row_hash` 重算：插入序 aaa→bbb→000，验证序 aaa→000→bbb，`aud_000` 期望 prev=hash(aaa) 实得 hash(bbb) → **断链**。现有 `test_ops_02` 与 Tester 探针全部使用不同秒事件，未覆盖。
- **修法**：把链序定义为**插入序**并让写/读/验证/封存四路同源：
  - sqlite：`last_row_hash` 改 `ORDER BY rowid DESC LIMIT 1`；`read_monthly_events` 改 `ORDER BY rowid`（`audit_events` 非 WITHOUT ROWID，有隐式 rowid，零迁移）。
  - pg：优先增插入序列列（`CREATE SEQUENCE IF NOT EXISTS audit_events_seq` + `ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS seq BIGINT DEFAULT nextval('audit_events_seq')`，既有行按 `(created_at,id)` 窗口回填后设默认），`last_row_hash`/`read_monthly_events` 改 `ORDER BY seq`；最小替代=取消 `:1625` 的 µs 截断（hash 与落库统一 `%f`），使 `(created_at,id)` 近似插入序，并在 `audit_chain.py` 注释显式声明该前提。
- **回归**：新增「同秒 + id 逆序 + 跨两轮搬运」链验证用例（sqlite 必测；pg 构造同秒不同 µs 两行 + 同秒再入新行）。

#### P2-2 sqlite 搬运重试对已落库行重算哈希并推进 prev → 崩溃窗口后再入同月新事件必断链
- **位置**：`store/sqlite/backend.py:1669-1691`（`prev=last_row_hash` → 循环 `INSERT OR IGNORE` → `prev=event["row_hash"]` → `_mark_shipped`）。
- **机制**：崩溃点=月库已 commit、主库 `shipped_at` 未回填（现有用例与 Tester 探针的注入点）。重跑时 `rows` 仍含已落库行（`shipped_at IS NULL`），`prev` 从「已落库末行」起，循环对这些重复行**用错误 prev 重算 row_hash 并推进 prev**（`INSERT OR IGNORE` 丢弃写入但 prev 已被污染）；若此时同月又来了新 outbox 行（崩溃重启后 API 继续写的常态，下一轮 maintenance 才搬运），新行拿到的是污染后的 prev → 链断。现有 `test_ship_survives_crash_between_insert_and_mark` 重试时**没有新行**，未覆盖。
- **复现**：2 行 ship → monkeypatch `_mark_shipped` 抛错 → 再 append 1 行（同月）→ 正常 ship → `read_monthly_events` + `compute_row_hash` 重算 → 断链。
- **修法**：搬运前取本月已存在 `id→row_hash`；对已存在行 `prev = 已存 row_hash; continue`（不重算、不推进为计算值），仅真正新行计算并推进。pg 同事务形态无此问题（无需改，可抽公共 helper）。
- **回归**：扩展上述用例（崩溃后补一行同月新事件 + `_verify_chain`），sqlite 臂必须绿。

#### P2-3 `update_task(status="running")` 无终态守卫：取消在租约/执行起步窗口被复活（两方言）
- **位置**：`store/sqlite/backend.py:1116-1122`、`store/postgres/backend.py:1078-1084`（`UPDATE … WHERE id=:id` 无条件）；调用点 `core/docs/ingest.py:602-603`、`worker/maintenance.py:138`。
- **机制**：`update_task(leased)` 走第三分支，已被 R4-1 的 `NOT (status='failed' AND error LIKE 'cancelled:%')` 守住；紧随其后的 `running` 走第一分支无守卫 → 取消落账后 running 写把 failed(cancelled) 改成 running（lease 已被取消清空、lease_until=NULL）。worker 路径随后 `should_continue` 探测失败静默退出 → 任务**永久 running**（无租约、不进耗尽清扫、不可再认领）；直接 `run_task`（should_continue=None）则跑完写 done → **取消任务复活并切换文档**（TC-TASK-03 违例）。这是 R4-1「取消终态对后续一切写零行」口径在**同一函数内三分支不一致**。
- **修法**：第一分支补 `AND status IN ('pending','leased','running')`（与 done 同款，双方言）。
- **回归**：`cancel_task` 后 `update_task(status="running")` → 状态仍 failed + error 以 `cancelled:` 开头；正常 claim→running 不受影响（双臂）。

#### P2-4 backup「工具缺失」与「真实快照失败」混同 → 备份失败无任务级可发现信号（NFR-10）
- **位置**：`store/postgres/backup.py:37-40`（工具缺失）与 `:68-74`（returncode≠0）同抛 `BackupToolError`；`worker/maintenance.py:122-129` 捕获后一律 `"unavailable: …"` + warning，任务 **done**；docstring `:96-107` 声称「真实快照失败（子进程非零）照常 errors」——与代码不符（Tester P3-①）。
- **影响**：pg_dump 真实失败（DSN 错/磁盘满/权限）在任务面显示 done、`stats["errors"]` 为空，只有 stats 字符串 + warning 可发现 → 违背 NFR-10 运维口径（无法区分「未配置」与「坏了」）。
- **修法**：拆两态——新增 `BackupToolUnavailable(BackupToolError)` 仅用于 `_resolve_command` 找不到工具（并包装子进程 `FileNotFoundError/OSError`）；子进程非零仍 `BackupToolError` 上抛 → `run_maintenance` 的 errors → 任务 failed（error 前缀 `backup_snapshot`）。异常类移到方言中立模块（`store/backup_common.py` 或 `store/backend.py`），顺带消除 `worker/maintenance.py:110` 的反向包依赖（P3-15）。
- **回归**：新增「工具在但失败」用例（pg 臂 `LATTICE_PG_DUMP_CMD=false`）→ 任务 failed 且 errors 含 `backup_snapshot`；工具缺失分支维持 `unavailable`。

### P3（次要，建议顺手；标 ★ 为低成本高收益）

- **P3-1（★）已搬运 outbox 永不清理**：`maintenance.py` 注册表无 trim 体；`_mark_shipped` 只回填 `shipped_at`。检索级审计每次一句 → 主库 `audit_outbox` 无限增长，且 12 月保留期只删月库、全量 payload 在 outbox 永久留存（FR-6 保留期口径不完整）。建议加 `audit_outbox_trimmed` 体（`DELETE … WHERE shipped_at IS NOT NULL AND shipped_at < cutoff`，仅删已搬运行）或登记遗留。
- **P3-2（★）outbox→audit_events 语义列填充弱**：`store/audit_chain.py:49-60` 只认 `actor/target_type/target_id` 键；实际 payload 用 `user_id/doc_id/task_id/upload_id/dataset_id` → 凭证与检索级事件 actor 落 `system`、`target_type/target_id` 恒 NULL（信息不丢，全在 detail_json，但按 actor/target 查询的 m2-3 审计访问分级会受影响）。建议 `actor = payload.get("actor") or payload.get("user_id") or "system"`，`target_type/target_id` 按事件类型从 payload 的 `*_id` 补齐或在注释声明以 detail_json 为准。
- **P3-3 协议签名漂移**：`store/backend.py` 未同步本次 7 个方法的 `audit=`/`task_id=`/`pending_version: int|None`/返回 int 签名。runtime_checkable 只看方法面，无运行时影响，但协议是 design §3 的权威契约。另 `backup_snapshot` 放在 `AuditBackend` 语义上属 Ops，建议移 Admin 或单独 Ops 协议。
- **P3-4 delete_dataset 先查后删竞态**：count 检查在 `BEGIN` 之外，并发上传可把 409 变成裸 FK 异常（500）。建议把检查移入事务内。
- **P3-5 封存崩溃窗口**：先写 sidecar 再 chmod；若在两者间崩溃，幂等早退不再补 chmod → 该月「已封存」却仍可写。建议早退路径也重放 chmod，或 sidecar 最后写。
- **P3-6 WAL checkpoint busy 被忽略**：未检查 `wal_checkpoint(TRUNCATE)` 的 busy 返回，随即删 `-wal/-shm`；并发写者存在时可能丢已提交帧。建议 busy≠0 时不删伴生文件。
- **P3-7 `_ensured` 缓存不随 prune 失效**：进程内缓存，prune 删除文件却不 discard → 同进程再 ensure 同月会返回无 schema 的空库（现有时间线不可达，属潜伏）。建议仅在 `path.is_file()` 时信缓存，或 prune 时 discard。
- **P3-8（★）test_ops_05 条件 skip + PATH 依赖是门禁隐患**：仅在 env 注入时 skip（门禁 skip=失败）；且 pg 分支断死 `unavailable`，若目标机 PATH 有 pg_dump 该用例直接红。建议按工具可用性分支断言（可用→真实快照；不可用→unavailable），删除 skip。
- **P3-9 演练脚本收尾**：`dr_ops05_drill.py:285` 无论 pg 臂是否跳过都打印 `DRILL PASS`（证据误导）；`_Wrap/_Rows` 死代码。建议按实际完成臂输出结论。
- **P3-10 凭证消费补偿删除无审计**：并发输家补偿 `delete_document`（无 audit）→ 审计面残留幻影记录。建议补偿删除带 EVENT_DOCUMENT_DELETE+reason 的 audit，或注释登记边界。
- **P3-11（★）C1 untag 锚点只在测试 docstring**：任务书 C1 要求「本段预留注释锚点」，实际仅测试文件；建议在 `core/docs/ingest.py` / `store/*/backend.py:delete_document` 落一行 `# M2-S3：sem_chunk_entities 随删清挂此编排位`。
- **P3-12 事件常量登记未闭环**：`EVENT_MAINTENANCE_RUN` 定义但写入点仍用字面量；`upload.reclaim`/`search.*`/`embedding.probe_*` 仍为字面量。至少把 maintenance 写入改常量。
- **P3-13（★）N12 顺手项申报不成立**：`_worker_env` 新增 `LATTICE_EMBED_MODEL/LATTICE_EMBED_BATCH_SIZE/LATTICE_QUALITY_LLM`，但 `config.get_settings()` **不读取这三个 env** → 子进程仍然漂移，N12 目标未达成。修法：get_settings 补三行 env 读取 + 往返断言；否则删映射并如实记录未处理。
- **P3-14 pg 备份 DSN 入 argv**：含密码 DSN 作为命令行参数，`ps` 可见。建议改 `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD` 环境变量传连接。
- **P3-15 分层小瑕**：`worker/maintenance.py:110` 反向 import `store.postgres.backup.BackupToolError`；随 P2-4 把异常类挪到中立模块即解。
- **P3-16 零碎**：`test_task_01_lease.py` docstring 仍写「pg=单连接」（P3-N2 已改双连接）；`partition_name` 未使用；函数内重复 import datetime。

---

## ③ 需求边界问题（3 条，均非 coder 修复项）

1. **偏差①口径回写（交接 supervised-coding）**：任务书 A2「同事务：搬运+回填」在 SQLite 跨文件物理上不可满足；实现取两步幂等+注释声明，**本轮裁定接受**（理由同 Tester）。请回写 TEST-CASES TC-OPS-01 预期/RUNBOOK：注明「业务写同事务（写侧语义）在双方言成立；搬运侧 sqlite 为两步幂等（at-least-once + 月库 PK 去重）、pg 为单事务」。**前提是 P2-2 修复后「不丢不重+链完整」才真正成立。**
2. **FR-6 保留期 12 个月的 outbox 边界**：任务书 B3 只点名月库文件/分区；outbox 已搬运行（含全量 payload）无清理路径（P3-1）。是否把 outbox 纳入保留期口径，请 supervised-coding 回 spec 明确（本轮按 P3 记录，不写 coder）。
3. **RUNBOOK 备份恢复节（交付前置，编排侧待办）**：任务 D4 分工为 supervised-coding 落笔（coder 供演练数据已交付），当前 RUNBOOK 无备份恢复节，而 TC-OPS-05 验收含「+ RUNBOOK 备份节」——用户确认交付前必须补齐（双后端各一份，含 pgvector 预装、`LATTICE_PG_DUMP_CMD` 注入、RPO/RTO 操作序列）。同批请补检查点「独立验证证据」小节（Tester P3-③）。

---

## ④ 裁定汇总

- **偏差①（sqlite 搬运两步幂等 vs「同事务」字面）：接受**。① WAL 无跨文件原子事务为物理约束；② pg 臂真同库单事务字面满足；③ 「业务改了就一定有审计」由写侧真同事务保证，与搬运形态无关；④ 注释已显式声明。**但注意：Tester 的「链完整」实证只覆盖了无新事件的重试，P2-2 揭示的窗口必须修复后，本裁定才算完全成立**（修复后建议补一次同月新事件的崩溃注入实证）。
- **P3-①（backup unavailable 语义）：不接受为 P3，升级 P2-4**。「工具未配置」记 unavailable 可不判失败（部署面显式状态）；「工具在但快照失败」必须落 errors/任务 failed，否则 NFR-10 备份可运维信号不成立。仅修 docstring 不够——需拆两态。
- **CASE_BUG 裁定请求：本轮无（Tester 未提交）。**

---

## ⑤ 结论

**reviewVerdict: NEEDS_CHANGES**

**reviewedSha: `066bf230cc4b778a88d84541e20dcbd97a63f050`**

**R2 交办范围（建议）**：P2-1 ~ P2-4 全修并各带回归（P2-1/P2-2 属 FR-6 链正确性，优先）；P3 顺手项建议收：**P3-1、P3-2、P3-3、P3-5、P3-8、P3-11、P3-13、P3-15**（其余记录/移交）。修完重跑 `scripts/test_gate.sh`（双模式 0 skipped）并逐项对账新增用例数。

**放行条件**：P2×4 闭环 + 门禁双模式全绿 0 skipped + 新增回归具备「修前必败」杀伤力。**当前不得交付**；用户确认交付前还须满足 ③ 第 3 条（RUNBOOK 备份节 + 检查点证据小节，编排侧）。交付阶段（用户确认后）由本角色执行 `gh pr review` 留痕；本轮因 NEEDS_CHANGES 不执行。

</details>

<details><summary>Tester R2 报告原文（2026-10-29 12:44，续接会话 ses_e7a664ca0ffeUizUfw9UtN65Nm）</summary>

---

# task-knowledge-lattice-m2-2 R2 Tester 回归验证报告

**testedSha = `0e0bcf873a5376ca8220735fe39340d41c256652` = HEAD（develop_opencode，已确认 `git rev-parse`；父 = R1 `066bf23`）**
**R2 增量**：13 files +646/−75，与申报逐文件一致（含 `store/backup_common.py` 新增）。工作区仅 `.opencode/` 2 个流程文件未提交（编排方落笔），业务代码零残留。

---

## 一、门禁全量独立复跑（清单项 1）

| 项 | 结果 | 与申报对账 |
|---|---|---|
| pg 臂收集 | **296**（[pg] 参数化 263 + PG 专用 33）全实跑 | ✅ 一致 |
| 常规模式 | **825 passed, 1 deselected, 0 skipped**（95.14s） | ✅ 一致 |
| `-O` 模式 | **825 passed, 1 deselected, 0 skipped**（102.95s） | ✅ 一致 |
| 结论 | **GATE PASS** | ✅ |

**+15 对账**：`test_r2_p2_fixes.py` 7 函数（6×2 matrix 参数化 + 1 常量往返）= 13；`test_ops_05_backup.py` 新增 `test_maintenance_backup_failure_fails_task` ×2 = 2；合计 **15 = 825−810** ✅。pg 臂 263−256 = +7 ✅。存量测试仅 `test_ops_05_backup.py` 被改（skip 删除→分支断言，**强化**）。

## 二、P2-1 链序=插入序（重点）

1. **「修前必败」独立复现 ✅**——自制 R1 树副本（`cp -R` + `git show 066bf23:` 覆盖 R2 改动的 10 文件 + 删 `backup_common.py`），PYTHONPATH 前置确认加载 R1 版本后跑新用例：**11 failed, 2 passed**——P2-1 双臂失败形态正是 Committer 描述的缺陷观测（R1 读序 `aud_000` 排最前 vs 期望插入序）；P2-2(sqlite)/P2-3(双臂)/P3-1/P3-2/P3-5(sqlite)/P3-13 同样修前必败。**2 个 passed 均有方言形态学解释**：①P2-2 pg 臂——R1 pg ship 单事务天然免疫（处方本就叫「sqlite 搬运重试污染」）；②P3-5 pg 臂——半封存态是 sqlite 文件形态专属缺陷面。**杀伤力结论：每个 P2 修复的用例都能抓住 R1 缺陷**。
2. **pg seq 幂等 ensure + 分区传播 + 存量行为实测定谳（自制探针 PROBE PG-SEQ PASS）**：①ensure 二跑幂等 OK（含新月分区滚动三跑）；②seq 列传播父表+全部分区（pg_inherits 实查）；③新行 seq 单调递增、**同事务批量 INSERT 各自求值递增**（3,4,5）——选型理由实证；④**存量行 seq 终态实测=被填连续值（1,2 按物理序）而非申报①的 NULL**——PG 分区表 ADD COLUMN DEFAULT nextval（volatile）rewrite 逐行求值，**优于申报①保守描述**（非缺陷，供 Committer 知悉）；⑤混合场景 NULL 兜底衔接无洞。
3. **四路同源核实**（读码）：sqlite 四路全 rowid；pg 写侧 DEFAULT/读序/last_row_hash 同源；**canonical 不含 seq**（_CHAIN_FIELDS 10 字段未动）——跨方言哈希可移植性保持 ✅。
4. **封存末哈希=插入序末条**：新用例断言 + P2-2 探针独立验证 ✅。

## 三、P2-2 + 偏差①终验

- coder 用例复核：事件序列真含同月新行（崩溃窗口后 `_seed(1, "2026-11-20 09:00:00")`），5 行链完整断言对准杀伤点 ✅（Committer ④ 要求满足）。
- **独立自制探针 PROBE P2-2 PASS**（更严苛形态）：**双次崩溃注入** + 重跑批内含已存 5 行 + **与已存行同秒并列、id 逆序**的新行（P2-1/P2-2 交叉面）：崩溃窗口终态月库 7 行留存 5 行未回填 → 重跑 7 行不丢不重、读序=链序、链 7 节完整、7 行全回填、封存末哈希=链尾 ✓——`existed` 跳过逻辑在交叉形态下正确。
- **R1 三探针在新代码复跑 PASS**：Probe A/B/C 全部收敛——P2-2 改动未破坏原崩溃收敛性 ✅。

## 四、P2-3 running 终态守卫

双臂同构 `AND status IN ('pending','leased','running')` + 三断言（取消后 running 零行/正常链不受影响/done 不复活）；修前必败双臂已证 ✅。

## 五、P2-4 backup 两态

- 两态用例真实性：`false`（存在、退出 1）→任务 **failed** 且 error 含 `backup_snapshot`；`no-such-binary`（FileNotFoundError）→`unavailable`+done——与 NFR-10 语义对齐 ✅
- docstring 一致化 ✅；`store/backup_common.py` 中立模块 + grep 实证 worker/core 零反向 import（P3-15 顺解）✅；os.environ 直改+finally 恢复无泄漏（双模式全绿佐证）✅

## 六、P3 顺手 8 项抽查

| 项 | 证据 | 判定 |
|---|---|---|
| P3-1 trim 边界 | 只删已搬运行三态断言+幂等；cutoff 与 audit_keep_months 同源；注册表挂接 | ✅ |
| P3-2 语义列 | `_target_of` 六前缀映射 + actor 回退链；三事件形态断言 | ✅ |
| P3-3 协议签名 | 8 方法签名同步 + backup_snapshot Audit→Admin 域 | ✅ |
| P3-5 封存 chmod | 库先 0444→sidecar 末写；半封存态补写；早退重放 | ✅ |
| P3-8 skip 删除 | 探测分支断言替代 skip | ✅ |
| P3-11 锚点 | ingest.py:487 + sqlite:599 + pg:573 三处 | ✅ |
| P3-13 env 往返 | get_settings 3 行 + 往返断言（R1 树必败实证） | ✅ |
| P3-12 常量 | maintenance.run 改常量；upload.reclaim 残留系 m1-3 既有 R2 未触碰（余量申报属实） | ✅ |

## 七、R2 diff 纪律面

commit 恰 13 文件无越界 ✅；docs/ 零触碰 ✅；移交 P3-4/6/7/9/10/12余量/14/16 未处理保持原样属实 ✅；边界②裁定链完整（L98 用户 11:40 拍板 → trim 承载有据）✅；canonical 未纳入 seq ✅。

## 八、回归面与终态对照

存量零弱化；R1 全部验收面用例原样保留在 825 内通过；**DRILL 双臂 R2 版独立复跑 PASS**（sqlite 0.014s/uv=5；pg 0.130s/0.218s/schema_migrations 齐）。**Committer R1 放行条件全部闭环**（P2-1 独立复现杀伤力/P2-2 双崩溃交叉探针/P2-3/P2-4/门禁全绿）。

## 问题分级

- **P1/P2：无**
- **P3（不阻断）**：①申报①「存量 NULL 段」按实测口径修正登记（实际被填连续 seq 更优）；②**sqlite rowid 跨 VACUUM 稳定性新观察**——无 INTEGER PK 表 rowid 不保证跨 VACUUM 保留，VACUUM INTO 恢复产物按读序链验证理论可断（row_hash 内容自洽不受影响）；POC 验收面不含链验证不阻断；建议 m2-3 审计读路径按 prev_hash 链遍历或登记 known-gaps；③upload.reclaim 字面量随 m2-3 收编。

## 结论

**testVerdict: PASS**

testedSha：`0e0bcf873a5376ca8220735fe39340d41c256652`

附注移交 Committer 闭环复审：①P3 三项不阻断（含 rowid/VACUUM 新观察建议登记）；②申报①按实测口径修正登记；③边界①口径回写与边界③ RUNBOOK 备份节仍挂编排侧交付前置待办。

</details>

<details><summary>Committer R2 闭环审查报告原文（2026-10-29 12:56，续接会话 ses_e7a4cd604ffe7I3RsgppN609Bz）</summary>

# task-knowledge-lattice-m2-2 R2 闭环审查报告

**reviewedSha = `0e0bcf873a5376ca8220735fe39340d41c256652`（= HEAD = testedSha）**
**审查基线**：`git diff 066bf23..0e0bcf8` = 13 files / +646 −75，与申报逐文件一致；父 = R1 的 `066bf23`；工作区仅 `.opencode/` 2 个流程文件（编排侧落笔）。`origin/develop` 仍 `739bbf3`，未 push。
**审查限制**：bash 仅放行 git/gh 只读，**未独立复跑 pytest**；门禁采信 Tester R2 独立复跑（`825 passed, 1 deselected, 0 skipped` × 常规 + `-O`，pg 臂 296）并做静态对账：+15 = 825−810、`[pg]` 256→263 = +7——**对账一致**。diff 内零 skip/零删除；docs/ 零触碰。

---

## ① 逐条闭环判定表

| R1 条目 | R2 处置与证据（diff 实读） | 判定 |
|---|---|---|
| **P2-1** 链序=插入序 | sqlite 四路同源（`last_row_hash ORDER BY rowid DESC` / `read_monthly_events ORDER BY rowid` / 写入追加 / 封存经 last_row_hash）；pg 四路同源（seq DEFAULT nextval / 读序 seq / last_row_hash / 写入不带 seq）；**canonical 不含 seq**。回归 + Tester「修前必败」独立复现（11 failed/2 passed，2 passed 方言形态学解释）。 | **CLOSED**（附 P3-新②③⑤） |
| **P2-1 pg 实现形态** | Tester 实测：PG 16 对 volatile DEFAULT 执行 rewrite 逐行求值 → 既有行获连续 seq（物理序=插入序）；幂等二跑不 rewrite；分区传播实查；同事务批量各自求值递增。**效果优于「窗口回填后设默认」处方**（等价且无需 UPDATE——append-only 触发器本就拦 UPDATE）。 | **接受**（注释与实测不符 → P3-新②；首次部署 rewrite 运维口径 → P3-新③） |
| **P2-2** 搬运重试防污染 | `existed` 预取、已存行 continue 不重算不推进；回归真含同月新事件；Tester 双崩溃+同秒逆序交叉探针独立收敛 + R1 三探针复跑收敛。 | **CLOSED** |
| **P2-3** running 终态守卫 | 双方言第一分支补非终态谓词 + 三断言回归；**函数级完备性核查**：三分支全守卫；其余任务写路径（cancel/heartbeat/fail_exhausted/claim/delete_document 直连）均不构成复活面——**无漏网分支**。 | **CLOSED** |
| **P2-4** backup 两态 | 两态拆分 + docstring 一致化 + 反向 import 消除；回归两态断言。 | **CLOSED** |
| **P3-1** outbox 保留期 | trim 双方言 + 任务体（cutoff 同源）+ 三态/幂等断言；边界②承载有据。**执行序** ship→seal→prune→backup→trim（trim 最后）；同轮 ship 新写入行 shipped_at=now 不会被删；月库为审计真相源。 | **CLOSED**（附 P3-新④⑦） |
| **P3-2** 语义列投影 | actor 回退链 + `_target_of` 前缀映射 + 断言。**兼容性**：仅影响后续搬运；已落库行不可变自洽；R1 期行保持旧投影（POC 无生产存量声明可接受——m2-3 以 detail_json 兜底）。 | **CLOSED** |
| **P3-3** 协议/域归属 | 7 方法签名同步；backup_snapshot Audit→Admin。**域归属裁定：接受 Admin**（协议是 store 方法分组非业务边界；单独 Ops 只增噪音；docstring 已注运维语义）。 | **CLOSED**（附 P3-新⑤） |
| **P3-5** 封存 chmod | 库 0444 先→sidecar 末写；半封存态补写；早退重放。半封存路径未清 wal/shm/未 discard 缓存——封存检测先于缓存判断，无实际影响（不再开项）。 | **CLOSED** |
| **P3-8** skip 删除 | 探测分支断言替代 skip；门禁 0 skipped。 | **CLOSED**（附 P3-新⑥） |
| **P3-11** 锚点 | src 三处。 | **CLOSED** |
| **P3-13** env 往返 | 3 行读取 + 全链往返断言。 | **CLOSED** |
| **P3-12** 常量 | maintenance.run 改常量；upload.reclaim m1-3 既有余量申报属实。 | **CLOSED（余量）** |
| **偏差①终态** | P2-2 修复 + 同月新事件实证（coder 用例 + Tester 双探针）——附加条件满足。 | **终态接受**（口径可回写：写侧同事务双方言；搬运侧 sqlite 两步幂等 / pg 单事务） |
| **rowid/VACUUM** | 裁定：**登记 known-gaps + m2-3 按 prev_hash 遍历**，本轮不改。现码无任何路径 VACUUM 月库；风险仅未来月库纳入备份/压缩时浮现；row_hash 内容自洽不受影响。 | **登记，不阻断** |
| **边界③** | 仍缺（编排侧 D.4 分工）。 | **交付前置（非 coder）** |

---

## ② 新发现问题

### P2-新①（阻断）R2 新增用例的门禁时间炸弹：封存集断言依赖「当前月=2026-10」，2026-11 起必红
- **位置**：`tests/test_r2_p2_fixes.py:78`（`test_chain_same_second_id_reorder_two_ships`，**双臂**）、`:274`（`test_seal_completes_half_sealed_state`，pg 臂）。
- **机制**：`assert sealed["sealed"] == ["202610", "202611"]` 中 **202610 来自连接工厂「当前月」**文件/分区（sqlite/connection.py:71 / pg setup_connection→ensure_audit 建当月），测试自身只 ship 了 **202611**。今天（10-29）当前月=202610 断言成立；**2026-11 起**当前月=202611（与自建月重合），202610 不存在 → 断言必败；2026-12 起同样。R1 的 test_ops_02 同款断言稳定（它显式造数并 ship 了 OCT→202610）；新用例漏了这一步——时间依赖类用例未造数，违反 TEST-CASES 口径段。
- **杀伤力**：项目唯一质量闸 11 月首个门禁运行必然失败；非产品功能缺陷，属交付物的确定性测试缺陷。
- **修法（二选一）**：①改**目标月成员断言 + 封存末哈希实断言**（推荐，同时修 P3-新⑤）：`assert "202611" in sealed["sealed"]` + 该月 sidecar/`audit_month_seals.last_hash == rows[-1]["row_hash"]`；②照 test_ops_02 先造一条 OCT 事件并 ship（链首 prev 相应改）。
- **回归要求**：门禁双模式重跑；显式造数形态不依赖当前月。

### P3-新② seq 注释与实测不符 + 防回退分支排序方向反（不可达，防御性）
postgres/audit.py:128-130 声称「非常量 DEFAULT 不 rewrite、既有行 NULL、NULLS FIRST」——实测 rewrite 逐行求值填连续 seq；且 `read_monthly_events` 的 `ORDER BY (seq IS NULL) ASC` 是 NULLS LAST，与注释相反。当前部署路径 ALTER 已回填 → 分支不可达（仅显式 NULL 造数可达）。修法：按实测改注释 + 读序改 `(seq IS NULL) DESC`（或删分支）。另注：R1 期已封存月的 last_hash 按旧序计算，R2 后读序改插入序，同秒并列月二者不一致——POC 无生产存量，m2-3 存量场景标注。

### P3-新③ seq 首次部署代价（登记）
首次 ensure_audit 对既有 audit_events 的 volatile DEFAULT **rewrite 全表（ACCESS EXCLUSIVE）**——POC 量级可接受但属部署面事实：RUNBOOK/PG 接线段注明「升级前先跑一次连接工厂，避开启动窗口」；CREATE SEQUENCE/ALTER 加入每连接 ensure_audit 后并发首次建连目录竞态面略增（m2-1 setup_connection DDL 并发同族）。→ 遗留清单（PG 接线段）。

### P3-新④ outbox 扫描/索引与 existed 全月读（性能，可选）
`ship_outbox` 每轮 `WHERE shipped_at IS NULL ORDER BY created_at,id` 无索引；建议部分索引 `audit_outbox(shipped_at) WHERE shipped_at IS NULL`。sqlite `existed` 每批整月 SELECT——可改 `WHERE id IN (本批)`。→ 记录/顺手。

### P3-新⑤ 文档与断言小瑕（随 R3 顺手）
`store/backend.py:661-663` 与 `sqlite/backend.py:1739` 的 read_monthly_events docstring 仍写旧序；`test_r2_p2_fixes.py:79` 封存末哈希断言同义反复（rows 与再读同源，未断言 sidecar/seals）——与 P2-新① 修法①合并。

### P3-新⑥ 工具探测不验证可运行性（薄）
`test_ops_05` 用 `_resolve_command` 存在性判「可用」；env 指向 docker exec 而容器不存在时维护体抛 BackupToolError → KeyError 报错而非清晰分支。建议探测跑 `--version` 或 try/except。→ 记录。

### P3-新⑦ trim 用例墙钟依赖（远期）
`test_r2_p2_fixes.py:200-201` `stats["audit_outbox_trimmed"] == 0` 依赖 run_maintenance 墙钟与 2026-11 造数相对关系；**2027-12 起该行落入保留期 cutoff 被清 → 断言失败**。建议 monkeypatch `maintenance.utc_now_ts` 固定时点（与 P2-新① 同批）。

### 边界新① sqlite 备份不含审计月库（需求口径，非本轮缺陷）
sqlite/backup.py 只 VACUUM INTO 主库 + objects tar；`audit_YYYYMM.db` 月库**未纳入**——sqlite 恢复后审计历史全失（pg pg_dump 分区同库天然包含）。任务书 D1/NFR-10 未点名月库；TC-OPS-05「恢复后数据完整」口径需确认。**建议**：RUNBOOK 备份节明确月库备份方式（checkpoint 后复制/tar 或整 data/ 快照）；若纳入自动快照随 m2-3；pg `--no-privileges` 恢复后封存分区 REVOKE 丢失（sealed 触发器仍在）——RUNBOOK 注明。**不本轮阻塞**。

---

## ③ 结论

**reviewVerdict: NEEDS_CHANGES**

**不可妥协项（唯一）**：**P2-新①**——两处封存集断言 2026-11 起必红，必须改确定性造数/成员断言（顺修 P3-新⑤ 封存末哈希实断言）。

**R3 交办范围（最小）**：①P2-新① 两处断言改确定性形态；②P3-新⑤ 两条 docstring + 实断言；③P3-新② 注释按实测改写 + NULLS 方向；④P3-新⑦ trim 用例固定时点（低成本）；⑤门禁双模式重跑，+0 增量（纯测试/注释改动）0 skipped。其余 P3 不阻断入移交清单。**R3 闭环后即可 APPROVED（代码语义面已无 P1/P2 未决）。**

**reviewedSha: `0e0bcf873a5376ca8220735fe39340d41c256652`**

---

## ④ APPROVED 后的放行前置与遗留清单终态（预览）

**交付前置（编排侧）**：①RUNBOOK 备份恢复节（含边界新① sqlite 月库备份口径 + pgvector 预装 + LATTICE_PG_DUMP_CMD + RPO/RTO 序列）；②检查点「独立验证证据」小节；③偏差①口径回写 TEST-CASES/RUNBOOK。

**遗留移交清单终态**：known-gaps——rowid/VACUUM（含 prev_hash 遍历处置建议）、seq 首次部署 rewrite 运维注记；m2-3 收编——upload.reclaim 常量、审计读路径 prev_hash 遍历 + 月库备份纳入（边界新①）、stats 新键同步、R1 期行语义列 detail_json 兜底口径；记录不修——P3-4/6/7/9/10/14/16 + P3-新③④⑥。

（本轮 NEEDS_CHANGES，交付阶段 gh pr review 不执行；待 R3 闭环 + 用户确认交付后落 PR 结论。）

</details>

<details><summary>Tester R3 报告原文（2026-10-29 14:43，续接会话 ses_e7a664ca0ffeUizUfw9UtN65Nm）</summary>

---

# task-knowledge-lattice-m2-2 R3 Tester 终态验证报告（maxRounds 最终轮）

**testedSha = `8f385dc5321045849a82ef42f67e94c44e757507` = HEAD（develop_opencode，已确认；父 = R2 `0e0bcf8`）**
**R3 增量**：5 files +59/−26，与申报逐文件一致；工作区仅 `.opencode/` 2 个流程文件未提交（编排方落笔），业务代码零残留。

---

## 一、P2-新① 时间炸弹根除（核心）

**① diff 实读两处断言改后形态**：双臂链用例与 pg seal half 用例均改 `"202611" in sealed["sealed"]`——"202611" 月库恒由用例 ship 造数建立（NOV=2026-11-05），恒早于 `seal(now="2026-12-01")`，故恒 ∈ 封存集，与工厂当月无关。数学推演完备。

**② 11 月击穿实测（BREACH PROBE 双臂 PASS——非推演，真实执行）**：预建「工厂当月=202611」产物（sqlite `ensure_monthly_audit(2026-11)` / pg `ensure_month_partition(2026-11)`）+ 移除 202610 纯化：

```
sqlite: sealed 集 = ['202611'] → ① '202611' in sealed ✓ ② sidecar last_hash == 链尾 ✓
        ③ 反向对照: R2 旧断言形态在此形态下 必红
pg:     sealed 集 = ['202611'] → ① '202611' in sealed ✓ ② audit_month_seals.last_hash == 链尾 ✓
        ③ 反向对照: R2 旧断言形态在此形态下 必红
```

**击穿真实性与修复有效性双向实证**（含工厂同建 202612 的更远形态——seal 正确不封）。

**③ 介质实断言真实性**：sqlite `read_seal(db_dir, "202611")["last_hash"]` 真读 sidecar 文件；pg `SELECT last_hash FROM audit_month_seals` 真读 seals 表——均与链尾相等，非同义反复 ✅（P3-新⑤ 顺修落实）。

## 二、P3-新⑦ 墙钟固定

- **monkeypatch 入口正确性**：`maintenance.py` 中 `utc_now_ts` 仅两处——L35 值导入至模块命名空间 + L159 `run_maintenance` 内唯一调用点。字符串 setattr 正中命名空间，`_outbox_trim_body` 经 ctx 接收同一 now——**单一来源全链生效** ✅
- **cutoff 链路推演**：now 固定 2026-11-30 → month_shift(-12)=202511 → cutoff=2025-11-01 恒定；过期行 2025-10-02 恒删、新行 2026-11-05 恒留——真实时钟完全退出断言链路 ✅
- **patch 生效性强证据**：定向复跑双臂 passed——当前真实月=2026-10，若 patch 失效 cutoff=2025-10-01、`removed==1` 断言必红；绿即 patch 真实生效 ✅

## 三、P3-新②⑤

- 注释与 R2 PG-SEQ 探针实测**逐句吻合**；「NULL 防御分支仅显式造数可达」grep 证实 ✅
- NULLS DESC 读序（NULL 前=最早，保守归位）正确落地处方 ✅；docstring 三处统一「插入序」✅
- **⚠ 保留一项 P3 理论瑕疵（不阻断）**：`last_row_hash` 的 `(seq IS NULL) DESC` 与 docstring「NULL 排最前→末条取非 NULL 最大 seq」自相矛盾——LIMIT 1 优先取 NULL 段顶条（若存在显式 NULL seq + row_hash 非空行）。**可达性实测为零**（grep 无显式造数）→ 无行为差异。建议 m2-3 收口改 ASC 或补 `WHERE seq IS NOT NULL` 并同步注释。

## 四、门禁全量独立复跑

| 项 | 结果 | 对账 |
|---|---|---|
| pg 臂 | **296**（263 参数化 + 33 PG 专用）全实跑 | ✅ 持平 R2 |
| 常规 | **825 passed, 1 deselected, 0 skipped**（120.72s） | ✅ |
| `-O` | **825 passed, 1 deselected, 0 skipped**（131.24s） | ✅ |
| 结论 | **GATE PASS** | +0 增量 ✅ |

**+0 增量核实**：7 defs / 6 defs 持平；R2→R3 用例函数名单逐行 diff，唯一差异 = trim 用例签名加 `monkeypatch` ✅。定向复跑 3 用例 × 双臂 = 6 passed。

## 五、R3 diff 纪律面

commit 恰 5 文件零越界 ✅；docs/ 与 RUNBOOK 对 R2 基线**零触碰** ✅；移交项 ④⑥/边界新① 零触碰属实 ✅。

## 六、终态对照

| Committer R2 条目 | 判定 |
|---|---|
| **P2-新①（不可妥协）** | **CLOSED**——11 月击穿形态实测双向实证 |
| P3-新⑤ | **CLOSED** |
| P3-新② | **CLOSED**（读序正确；last_row_hash 留不可达 P3） |
| P3-新⑦ | **CLOSED** |
| 「R3 闭环即 APPROVED」前提 | 满足——R2 语义面零改动，门禁持平全绿 |

## 问题分级

- **P1/P2：无**
- **P3（登记）**：last_row_hash NULLS 理论分支（不可达）——随 m2-3 收口。

## 结论

**testVerdict: PASS（终态）**

testedSha：`8f385dc5321045849a82ef42f67e94c44e757507`

附注移交 Committer 最终闭环：①P3 一项随 m2-3 登记；②边界新①/边界③/P3-新③ 仍挂编排侧交付前置；③rowid/VACUUM 维持 R2 已裁定口径（known-gaps + m2-3 prev_hash 遍历）。

</details>

<details><summary>Committer R3 最终闭环报告原文（2026-10-29 14:48，续接会话 ses_e7a4cd604ffe7I3RsgppN609Bz）</summary>

# task-knowledge-lattice-m2-2 R3 最终闭环复审

**reviewedSha = `8f385dc5321045849a82ef42f67e94c44e757507`（= HEAD = testedSha）**
**审查基线**：`git diff 0e0bcf8..8f385dc` = 5 files / +59 −26，与申报逐文件一致；docs/ 与 RUNBOOK 对 R2 基线零触碰。
**审查限制**：bash 仅放行 git/gh 只读，未独立复跑 pytest；门禁采信 Tester R3 独立复跑（825+1 × 双模式 0 skipped，pg 臂 296）并静态对账 +0 增量成立。

## ① 逐项闭环判定

| 条目 | 证据（diff 实读） | 判定 |
|---|---|---|
| **P2-新①（不可妥协）** | 两处精确集断言 → 成员断言（与工厂当月解耦、逐月推演完备）+ 末哈希存储介质实断言（真读 sidecar/seals）；Tester BREACH PROBE 双臂双向实证（R3 绿/R2 旧断言红，含 202612 形态）；剩余断言逐月推演不依赖工厂当月。 | **CLOSED**（修法与处方①逐字吻合） |
| **P3-新⑤** | 三处 docstring 统一插入序；同义反复根除。 | **CLOSED** |
| **P3-新②** | 注释按 PG 16 实测改写；读序 NULLS DESC 正确；**last_row_hash 同被改 DESC 与 docstring 矛盾 → ②裁定登记**。 | **CLOSED（含登记 P3）** |
| **P3-新⑦** | 墙钟 patch 单一来源全链；cutoff 恒定；Tester 强证据。 | **CLOSED** |
| **R3 语义面零改动** | 5 文件逐 hunk：docstring/注释/不可达分支排序键/测试断言——支持路径行为零变化。 | **CONFIRMED** |
| **Tester 保留 P3** | 见 ② 裁定。 | **已裁** |

**R2 遗留条件复核**：P2×4 R2 已 CLOSED；偏差①终态接受不变；rowid/VACUUM 裁定不变。

## ② 新发现问题与裁定

### 保留 P3-新②′（登记 m2-3，不阻断）：last_row_hash NULLS DESC 防御分支与 docstring 自相矛盾
- 事实：`(seq IS NULL) DESC` 使 NULL 行排最前，LIMIT 1 在有显式 NULL seq 行时取 NULL 段顶条而非非 NULL 最大 seq——docstring 相反。可达性：支持路径不可达（volatile DEFAULT 已回填/INSERT 走 DEFAULT/ship 不含 seq；grep 无显式造数）。
- **裁定：登记 m2-3**（不可达零行为差异；maxRounds 终态不成比例；m2-3 审计读路径定义链验证语义时一并修——一行改 ASC 或 WHERE seq IS NOT NULL + 探针）。

### 其他观察（编排侧/记录）
1. 检查点 filesChanged 应补 R2/R3 两新文件（backup_common.py、test_r2_p2_fixes.py——D33）。
2. P3-新③ rewrite 运维口径需 RUNBOOK 落笔。
3. R3 无新增测试无弱化（修前必败断言原样保留）。

## ③ 结论

**reviewVerdict: APPROVED**

依据：①P2-新① 修复忠实且经 Tester 双向实测；②P3-新②⑤⑦ 落地；③支持路径语义零改动、零越界、+0 增量；④门禁 825+1 全程 0 skipped 链完好（R1 起 663+1）；⑤唯一残留不可达 P3 已裁定登记。**代码语义面已无 P1/P2 未决。**

**reviewedSha: `8f385dc5321045849a82ef42f67e94c44e757507`**

## ④ 遗留移交清单终态

**A. known-gaps（supervised-coding 落笔）**：A1 rowid/VACUUM（m2-3 按 prev_hash 遍历；月库引入 VACUUM 需显式稳定插入键）；A2 seq 首次部署 rewrite 运维口径（先跑连接工厂避启动窗口；ensure_audit 并发面同族记录）。

**B. m2-3 收编**：B1 upload.reclaim 常量；B2 审计读路径 prev_hash 链遍历；B3 审计月库纳入备份（sqlite snapshot 仅主库+objects——audit_*.db 恢复后全失；RUNBOOK 明确范围、自动快照随 m2-3）；B4 stats 新键同步运维面板；B5 R1 期行语义列 detail_json 兜底；B6 last_row_hash NULLS 修正+探针。

**C. 记录不修**：P3-4/6/7/9/10/14/16 + P3-新④⑥。

## ⑤ 编排侧交付前置（重申）

1. RUNBOOK 备份恢复节（含 B3 口径 + pgvector 预装 + LATTICE_PG_DUMP_CMD + RPO/RTO 序列 + A2 注记）；
2. 检查点「独立验证证据」小节 + filesChanged 补两文件；
3. 偏差①口径回写 TEST-CASES/RUNBOOK。

**交付阶段**：用户确认后 gh pr review 留痕（self-approve 限制时 COMMENTED + 首行 APPROVED——沿 m2-1 先例）；合入不经手。

</details>

## 独立验证证据（Tester 各轮独立复跑汇总）

- **门禁链**（每轮 Tester 独立复跑，非抄 coder）：R1 **810+1** / R2 **825+1** / R3 **825+1**（+0）——双后端双模式（常规 + `python -O`）全程 **0 skipped**；pg 臂 289→296→296 全实跑；基线链 663+1（m2-1 终态）→ 825+1，增量逐文件对账每轮闭合（+57 / +15 / +0）
- **TC-OPS 专项**（R1）：ops_01=21（同事务×7 接入点核实 + 崩溃注入）/ ops_02=8（滚动/链/封存/append-only/保留期）/ ops_04=7（T19 RESTRICT 409/404/403 全链）/ ops_05=7（双臂快照恢复 + DRILL 独立复现 PASS）——文件清单 test_ops_01/02/04/05 + p3_followups_m2_2
- **偏差①三探针**（R1 Tester 自制）：Probe A 跨月批 commit 中途崩 / B 月内 INSERT 未提交崩 / C 真进程 os._exit 同生共死——R1 收敛、R2 新代码复跑仍收敛；R2 追加双次崩溃+同秒 id 逆序交叉探针（7 行不丢不重、链 7 节完整）
- **修前必败实证**（R2 Tester 自制 R1 树副本）：11 failed / 2 passed（2 passed 方言形态学解释）
- **11 月击穿双向实证**（R3 Tester BREACH PROBE 双臂）：R3 断言绿 / R2 旧断言必红（含 202612 形态）
- **DRILL 双臂**（R1/R2 各独立复跑一次）：sqlite 0.013-0.014s 快照 + user_version=5 + 检索/矩阵子集；pg dump 0.125-0.138s + restore + schema_migrations 5 条 + FTS 命中
- **关键命令**：`docker start lattice-pg && export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice && scripts/test_gate.sh`；演练 `uv run python benchmarks/dr_ops05_drill.py`（报告 benchmarks/report-m2-2-ops05.md）
