---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2-6
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e6a18509affeLOmueMfB4vItlo
testerTaskId: ses_e69ca7427ffe909TXr7yUZvXIO
committerTaskId: ses_e69aa3034ffeswmU0kfrWYy0rF
status: done
round: 3
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 00dc486ab3d6351702a079e07207dfc63903e059
reviewedSha: 1076f939d29d043e2015d073849664bd4f886785
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged:
  - scripts/test_gate.sh
  - src/knowledge_lattice/adapters/embedder.py
  - src/knowledge_lattice/api/admin.py
  - src/knowledge_lattice/app.py
  - src/knowledge_lattice/core/docs/ingest.py
  - src/knowledge_lattice/core/docs/quality.py
  - src/knowledge_lattice/domain/audit_events.py
  - src/knowledge_lattice/store/audit_chain.py
  - src/knowledge_lattice/store/backend.py
  - src/knowledge_lattice/store/postgres/backend.py
  - src/knowledge_lattice/store/postgres/migrations/docs/0010_task_seq.sql
  - src/knowledge_lattice/store/sqlite/backend.py
  - src/knowledge_lattice/store/sqlite/migrations/docs/0010_task_seq.sql
  - src/knowledge_lattice/store/taskclock.py
  - src/knowledge_lattice/web/app.js
  - src/knowledge_lattice/web/i18n.js
  - src/knowledge_lattice/web/style.css
  - src/knowledge_lattice/worker/__init__.py
  - src/knowledge_lattice/worker/rebuild.py
  - src/knowledge_lattice/worker/runner.py
  - tests/fake_providers.py
  - tests/test_admin_manage.py
  - tests/test_admin_members.py
  - tests/test_admin_store_reads.py
  - tests/test_admin_values.py
  - tests/test_auth_04_delegated.py
  - tests/test_auth_05_trusted.py
  - tests/test_backend_contract.py
  - tests/test_pg_api_diff.py
  - tests/test_pg_scaff.py
  - tests/test_regress_m0a1_followups.py
  - tests/test_scaf_03_migrations.py
  - tests/test_tag_02_retag.py
  - tests/test_task_02_retry.py
  - tests/test_v11_schema.py
  - tests/test_wk_rebuild.py
  - src/knowledge_lattice/config.py
  - src/knowledge_lattice/api/semantic.py
  - src/knowledge_lattice/mcp/server.py
endReason: null
createdAt: 2026-11-01T14:51:55+0800          # 创建时间（30 天清理审计用，见 README §4.5）
updatedAt: 2026-11-01T20:50:01+0800          # 每次写检查点必更新为当前时间（ISO 8601 含时区），不得沿用旧值
---

# task-knowledge-lattice-m2-6: 管理面补全与嵌入执行体——reindex/reembed 蓝绿执行体+members 增改删+values CRUD

## 任务原文

**段定义**（_m2-plan row 7.5——2026-10-30 用户拍板新增〔m2-3 R1 Committer 边界 1/2〕+ 2026-11-01 m2-4 N-1 裁定扩展）：**管理面补全与嵌入执行体**。验收：TC-EMB-06 全绿（双后端）+ members/values CRUD 用例 + 门禁基线 **1580+1** 只增不减。

**A 主线**：
- **A1 reembed 蓝绿执行体**（TC-EMB-06 越段项——m2-3 已交付管理面投递入口，本段补 **worker 执行体**）：runner 认领 `reembed` 任务 → ① 新标签向量**并行写入** `chunk_vectors`（扫描谓词 = 在用块中无 (rid, :new) cv 行；旧标签持续服务**功能零降级**）；② 覆盖率 100%（限 tombstone=0 且 version=active_version）后**原子切 config 标签**（零 SQL）；③ **竞态在途回写防护**（切换 config 瞬间的旧模型在途批次——ON CONFLICT/回写防护谓词，库内不出现孤儿行）；④ 旧标签**延后清理**（DELETE chunk_vectors WHERE embed_model=:old）+ **quality 重跑联动**（缓存键 (content_sha, embed_model)、旧 vector_crowding 已清、阈值随新模型重标定）+ **semantic_build 强制重跑**（dict_rev 含嵌入标签——design §5.8）；管理面嵌入覆盖率面板数据源（m2-3 已有端点——执行体产出真实数据）。**TC-EMB-06**。**N-1 裁定（2026-11-01 用户，R1 Committer 上报）**：reembed=**全库迁移**——扫描/覆盖率门/旧标签清理均**全库**（store 支持 org_id=None 或等价全库口径）、全库在用块新标签覆盖率 100% 后方可原子切全局标签（全库单标签一致——按 design §5.3 L794/TC-EMB-06 L224 冻结口径，不动正文）；触发权限=**sysadmin 专属**（换模型为系统级配置变更，org_admin/owner 均不可——FR-4 owner/org_admin 语义限单文档重索引；m2-3 已交付入口带 embed_model 时按此收口，不带 embed_model 的单文档 reindex 维持 owner/org_admin）；多组织双后端用例必补（org A 投递后 B/C 向量与标签同迁、全库仅单标签；未达成前不得切换）
- **A2 reindex 执行体**：runner 认领 `reindex` 任务（m2-1 框架已注册任务类型）——重切分+重嵌入全链（含 quality 阶段），任务状态机/心跳/取消沿 m2-1 框架；与 A1 蓝绿语义对齐（若 reindex 含嵌入则同蓝绿口径）。验收：端到端用例（投递→认领→完成→检索可见新产物、中断重认领不丢不重）。**N-2 裁定（2026-11-01 用户，R2 Committer 上报，选 (a) 保守拒绝）**：存在 pending_version（**含 pending_status=failed**）的文档一律拒绝 reindex——API 409+执行体 fail-closed（提示先处置失败上传/清理 pending 后重投）；不修 ingest._guard_alive 的版本存活语义（core 不动）；API 用例第二段（pending failed→重投）改 409+文档终态断言（现 202 用例 false green 必须重写）；执行体补 failed 形态用例；修复后文档保持 searchable_full、在用块保留
- **A3 members 增/改/删**（**m2-4 N-1 用户裁定选 a**——2026-11-01：JIT 建档后 API 面无法把新用户加入组织，PUT grants/CSV 均要求既有 membership，补 membership 写路径使 D16「管理员不建账号只配授权」API 面闭环）：POST/DELETE/PATCH membership 端点（含角色变更/软停用——形态按 design §5.6 授权维护闭环与既有 trg_membership_no_extend〔T23〕触发器约束设计并申报）；**审计入 outbox**；org_admin 门控；与 JIT 建档链路衔接（JIT 用户→管理员 API 加组织→配授权，全程不碰 DB——端到端用例）；T23 触发器语义不破坏（过期成员恢复路径 m2-3 先例：删行重加+补授权——若本段新增恢复路径须回归）
- **A4 values CRUD + D19 重新启用取值恢复路径**：维度取值管理面写路径（新增/停用/**重新启用**）——m2-3 已交付取值停用（v1.9.3 登记 PATCH 路径），本段补**重新启用**（D19 恢复路径：文档含已停用取值时 PATCH/覆盖上传同锁〔v1.6.3 口径〕，重新启用取值后解锁——locked_docs 面板联动）；维度退役二次确认/值序（P3-1 值序反向锁死——B 项清单⑩）兼容；审计入 outbox
- **A5 B5 读回行注记落 RUNBOOK**（m2-3 移交：read_monthly_events 经重投影后读回行 row_hash 不自洽——消费者勿以读回行复算链；_m2-plan 已登记口径，本段顺手写入 RUNBOOK §4 或审计节——docs 批由监督侧落笔，coder 申报位置）

**B 顺手**（m2-3 R3 Committer P3×10 登记清单——其检查点遗留事项节为权威，按 Committer 惯例核销或再挂）：① UI fresh 残余 UX（预填/逐行过期编辑/显示既有值/langchange 保留）；② 同秒 reembed 单调键（uuid4 非单调——本段 A1 执行体认领序直接相关，**优先做**）；③ replace_local_grants 直调解析器对齐；④ read_org_audit 下沉（api→store）；⑤ audit_chain 错误码；⑥ 格式常量共享（store strftime 字面量 vs api _EXPIRES_LIB_FORMAT 双源）；⑦ 协议 list_grants_for_export docstring 字符串契约；⑧ API 级 pg diff 断言（现 store 级+Tester 临时验证）；⑨ ULID 字样注释×2（实为 uuid4）；⑩ P3-1 值序反向锁死（用例值序与时间序同向未锁死 reversed+双分支写法松）。**m2-4 followups 五项按需顺手**（P3-11 固化用例〔org 解析顺序〕/gate pg 正则 `\[pg[^]]*\]`/test_auth_05 `_call` settings 形参残留/`_outbox_insert` 完整性错误掩码理论面/MCP 面忽略审计先于 resolve_org 窄面——登记去向「下批/m2-5 测试补强批」，触及顺手、不强求）。

**不做**：跨组织隔离全绿与 §六 M2 行总勾验（m2-5 收口段）；G-6/G-8 真实模型复测（m2-5）；真实 IdP 联调（m2-5/部署期）；语义轨道 followups（G-23/G-24 分项——下批/m2-5）；TC-UI-01~04 手动走查（用户侧）。

**验收标准**：TC-EMB-06 四步全绿（双后端——①并行写入零降级/②覆盖率 100% 原子切标签/③竞态在途无孤儿行/④旧标签清理+quality·semantic_build 联动）；A2 reindex 端到端；A3 members 增改删+JIT→入组→授权端到端（D16 API 面闭环）+T23 触发器回归；A4 重新启用解锁+locked_docs 联动；B 项按清单核销或登记去向；门禁双后端双模式 0 skipped、基线 **1580+1** 只增不减。

## 需求确认
- [x] 用户已确认（2026-11-01 14:58 用户「同意」——任务书含 A1~A5+B 项+不做边界+验收标准全量确认；A3 择型申报口径〔前置提示〕未表异议，走流程内择型申报→Committer 审查→docs 批回写先例；status=implementing）
- 历史遗留事项清单（supervised-coding 扫描汇总）：
  - **m2-3 移交 m2-6 P3×10**（其检查点遗留事项节为权威）→ 已入任务书 B 项①~⑩
  - **m2-4 N-1 裁定**（2026-11-01 用户选 a：members 增/改/删入本段）→ 已入任务书 A3
  - **m2-4 followups 五项**（登记去向「下批/m2-5 测试补强批」）→ B 项按需顺手（触及顺手、不强求——不强扩范围）
  - m2-4 其余移交（真实 IdP→m2-5、G-25/G-26→known-gaps 部署期、TC-UI→用户侧）——**无归 m2-6 项**
  - m2s-6/m2s-5 等 18 个历史检查点均 done 无未了结任务级遗留；m1-3 L82 余量（multipart 顺延无归属段、G-12 已登记）维持不动
- **开工前置提示（用户可在确认时一并表态，不阻塞）**：A3 members 端点形态（POST/DELETE/PATCH 的具体路径与角色变更语义）design §5.6 未逐字钉死——coder 将按「授权维护闭环+T23 约束」设计并**择型申报**，Committer 审查后如需口径回写走 docs 批（先例：m2-3 v1.9.3 ④端点登记）

## 遗留事项（跨任务移交）
- [x] **本轮清偿**：m2-3 移交 P3×10 全核销（B①~⑩——**B① 3/4 子项**：预填/既有值徽标/langchange 保留交付，逐行过期编辑见下行移交；B5 落 RUNBOOK §4〔A5〕）——来源 task-knowledge-lattice-m2-3，2026-11-01
- [x] **本轮清偿**：m2-4 移交 N-1 members 增/改/删（JIT→入组→授权→检索 API 全链 D16 闭环+T23 回归+唯一 admin 守卫）+followups ①②③（P3-11 固化用例/gate 正则 `\[pg[^]]*\]`/test_auth_05 `_call` 残留）——来源 task-knowledge-lattice-m2-4，2026-11-01
- [x] G-27 登记（reembed 覆盖率未收敛 fail-closed——known-gaps 已落笔；可选收窄=runner 按 error 分类回队）
- [x] **移交 m2-5 / TC-UI 手动走查批**：B①「逐行过期编辑」（Committer R1 裁定登记——UI grants 逐行独立 expires 输入，非门禁面）（✅ 已清偿：来源 task-knowledge-lattice-m2-5〔2026-11-02 双通过〕——B① 4/4 全清偿：逐行独立输入+初始=库内值+新选行预填+保存逐行读回〔playwright DOM 三断言〕；TC-UI-01~04 manual 走查归用户）
- [x] **移交下批卫生**：R3 Committer P3×3 文案/注释（pg 并发用例 docstring 旧称 FOR UPDATE／fail-closed 注释+错误文案旧称「自动重试」／coverage 端点 docstring 旧称「全局口径」——无功能影响）（✅ 已清偿：来源 task-knowledge-lattice-m2-5 R1〔2026-11-02〕）
- [x] **监督侧待办**：pg 存量 7 个 bench/eval 残留 schema（`lattice_eval_*`×5+`lattice_bench_g6hv_*`×2——历史会话产物非本任务产物）核对后 `DROP SCHEMA ... CASCADE` 清理（✅ 已清偿：supervised-coding 2026-11-02 m2-5 交付前置执行——7 schema 核对一致后 DROP CASCADE，残留计数归零）
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1: coder 完成（2026-11-01 16:19，**全新会话**，coderTaskId=ses_e6a18509affeLOmueMfB4vItlo，commit `f979405` 于 develop_opencode，36 files +2930/−220，父提交=c2ebb68 同步确认 origin/develop 无前进，未 push）——A1 reembed 蓝绿执行体（TC-EMB-06 四步：①并行写入含 pending 块②覆盖率 100% 进程内原子切标签〔embedder.apply_model+ingest/quality.apply_settings 对象图零 SQL〕③re-pin 在途回写防护零孤儿行④旧标签清理+quality 缓存失效全量重算+semantic_build 强制投递）+A2 reindex 执行体（幂等重置回 parsing+ingest 管线复用，中断重认领不丢不重）+A3 members 增改删（POST/PATCH/DELETE+org_admin 门控+审计同事务+T23 过期行 409 前置+唯一 active org_admin 自锁守卫 409+软停用=expires_at 承载零新列+JIT→入组→授权→检索 API 全链端到端——N-1 选 a / D16 闭环）+A4 values CRUD（POST 新增+D19 重新启用解锁 locked_docs 联动+retired 维度 409）+B①~⑩全核销（UI fresh 预填/既有值徽标/langchange 保留、0010 pg seq+sqlite rowid 同秒单调键、replace_local_grants expires 归一、read_org_audit 下沉、AuditChainError 机器码×5、TS_FMT 常量单源、docstring 字符串契约、API 级 pg diff〔create_app backend 注入〕、uuid4 注释、P3-1 值序反向锁死）+m2-4 followups 三项（P3-11 固化/gate 正则 `\[pg[^]]*\]`/auth_05 `_call` 残留；_outbox_insert 掩码与 MCP 审计顺序按登记不动）。自测：GATE PASS **1637+1 双后端双模式 0 skipped**（基线 1580+1，+57 对账：wk_rebuild 34〔17×双后端〕+members 11+values 8+store_reads +3+pg_api_diff 1；pg 臂收集 609=575 参数化+34 专用全实跑）；TDD 红灯×5（WorkerServices quality 形参/members 404+哨兵/values 3 failed/-O 双通道竞态/test_tag_02 排序源暴露）；UI playwright DOM 三断言（预填/既有值徽标/langchange 保留）。机械核验（supervised-coding 16:21）：HEAD=f979405 ✓、commit 格式 R1 ✓、36 files 全在 src/tests/scripts 零 docs/prototype/检查点改动 ✓、未 push ✓、工作区仅监督侧 4 文件原样 ✓。**择型申报 11 条**：①切标签载体=进程内对象图（design §5.3 config 四件套=env 冻结口径，不引库内 config 表；subprocess 模式主进程切换=运维改 env 重启〔重启窗口向量路暂空 BM25 可用——RUNBOOK 注意事项归 docs 批〕）②迁移外呼经 embedder.with_model 专用实例（主 embedder 旧标签不动保零降级）③扫描谓词含 pending 版本块（防覆盖上传在途块漏补）④竞态防护=re-pin 状态标签（顺序：写满→切换→re-pin→补扫→清理）⑤quality 联动=invalidate_quality_cache+recompute（阈值重标定=运维配置动作；recompute best-effort）⑥A3 端点形态：POST `{user_id,role,expires_at}` 201（用户不存在 404——D16 不建账号）/PATCH 键显式出现含 null=改永久（model_fields_set）/DELETE 204 级联清授权/唯一 admin 自锁守卫〔增补申报〕⑦A4 enable 幂等零新审计（沿 disable 先例）/dry_run 仅 disabled 400 ⑧A2 幂等重置+重索引窗口文档暂不可搜〔申报〕/取消后续投可续 ⑨B② claim/list_tasks 次级键 rowid/seq ⑩B⑧ create_app `backend=` 可选注入（向后兼容）⑪kick 去 `_wake.set()`（-O 门禁暴露的双通道认领竞态）。A5 RUNBOOK 位置申报=§4「审计月库」节（read_monthly_events 读回行 row_hash 不自洽注记+walk_chain 指引；代码侧注记已落 backend.py docstring）。
- R1: tester **PASS**（2026-11-01 16:58，**全新会话**，testerTaskId=ses_e69ca7427ffe909TXr7yUZvXIO，testedSha=f9794054973e376c573e877185a849aad7c1eee8 全 SHA 复核一致）——门禁独立复跑 **GATE PASS 1637+1 双后端双模式 0 skipped**（pg 臂 609=575 参数化〔新正则口径〕+34 专用全实跑；+57 逐文件归因独立核对一致：wk_rebuild 34〔双层参数化 matrix×env 实证〕+members 11+values 8+store_reads +3+pg_api_diff 1；零删除零弱化——diff 机器核验无删 def test_/parametrize 行）。分用例判定全 ✅：TC-EMB-06 四步双后端（①并行写入零降级=择型②专用实例结构保证②覆盖率限在用块口径不破③竞态注入实证红绿④清理+quality 缓存失效重算+semantic_build 强制投递断言）；A2 端到端含中断重认领不丢不重；A3 members 11 条+**JIT→入组→授权→检索全链 API 不碰 DB**（D16 闭环——首登 403+auth.user_jit_created 审计+T22 收紧+PUT 后放开）+T23 恢复路径回归；A4 D19 enable 解锁 locked_docs 联动（disable 升→enable 回落双后端+REST）；B①~⑩逐项核销（B① playwright DOM 三断言**独立复现**——既有值徽标/预填/langchange 保留）；m2-4 followups 三项清偿。**择型 11 条全 ACCEPT**（③附 TC-EMB-06 扫描谓词措辞 docs 批回写建议〔非决策〕、⑧附 RUNBOOK 注记可选项、①subprocess 申报诚实）。分层纪律 ✅（rebuild.py 在 worker/ 非core、store 双方言逐语句等价、审计同事务）；越权面 ✅（org_admin 门控+org_scoped）。**注入验证 2 组红绿**（①摘除回写防护谓词→孤儿行用例红 ②claim 回退 uuid4 排序→同秒序用例红——业务代码零残留）。临时产物清理 ✅（pg 零新增 schema/临时目录全删/uvicorn 停/自动化 Chrome 终止/工作区终态与验证前一致）。**P1/P2 无；P3×3**：P3-1 B①子项「逐行过期编辑」未逐字实现且未登记去向（saveGrants fresh 集共用输入框值——多行不能各带不同 expires；缓解面=预填+徽标+未动行沿用已大幅收敛；建议 R2 补或裁定登记去向，不构成打回事由）；P3-2 观察（pg 存量 7 个 bench/eval 残留 schema 非本任务产物——监督侧择机清理或登记）；P3-3 观察（择型⑧ RUNBOOK 运维注记可随 docs 批顺带）。观察项：双模式 167/168 warnings 为既有告警非本段引入。报告全文见「最新验证意见原文」details 块（R1 Tester）。
- R1: committer **NEEDS_CHANGES**（2026-11-01 17:13，**全新会话**，committerTaskId=ses_e69aa3034ffeswmU0kfrWYy0rF，reviewedSha=null——R1 未通过；testedSha=f979405=HEAD 一致；R1 首审 diff=c2ebb68..f979405 全量 36 files 逐文件核对；门禁采信 Tester 独立复跑+静态计数对账自洽——沿先例）。**P1:0；P2×2**：**P2-1** A1④ semantic_build 强制重跑不成立——`_exec_semantic_build`（runner.py:272-282）用 runner 构造期旧 `self._settings` 调 run_build_task，`switch_embed_label`（rebuild.py:72-93）只替换 `services.settings` 不改 TaskRunner._settings → dict_rev 仍按旧标签计算=与 current 相同 → run_build 走 skipped；测试只断言任务行存在未执行任务（test_wk_rebuild.py:161-168）；且 inline 形态 ServiceContext.settings/MCP settings 不随切 → 共享 embedder 已切新模型下 semantic vec 查询用新模型 query 向量查旧标签行（跨底模距离，api/semantic.py:425-431、mcp/server.py:557-558）、覆盖率面板 dim 旧值（admin.py:590）、周期指纹探针 dim 变更后每次抛维度异常（embedder.py:164）——修法：semantic executors 改读 services.settings 或引入可变 SettingsHolder、subprocess/inline 双形态同修+inline 把 ServiceContext/MCP settings 更新（或统一从 embedder model_label 派生）+补「reembed 后实际执行 semantic_build → status!=skipped、dict_rev 含新标签、sem_vec 行新标签」双后端用例。**P2-2** A1②/④ 组织级覆盖/清理+全局 config 切换——store 扫描/repin/清理/失效全 org 过滤（sqlite:2499-2550、pg:3770-3845）但 switch_embed_label 切**进程全局**标签 → 多组织下其余组织检索谓词立即变新标签而库内只有旧标签向量（向量路失效 BM25 兜底、旧标签残留），TC-EMB-06④「全库单标签一致」不成立（design:794/TEST-CASES:220-224 冻结口径=全库）；且 reembed 入口在文档路由下 `_require_owner_or_admin`（普通文档 owner 可触发进程全局 config 变更）超出 FR-4「重索引=owner/org_admin」原意——修法：按冻结口径改全库扫描/全库覆盖率门/全库清理+多组织双后端用例，或按 N-1 裁定 (b) 拆全局阶段；权限收到 org_admin（全局则 sysadmin）。**P3×8**：P3-1（=Tester P3-1）B①「逐行过期编辑」**裁定=接受登记去向**（检查点/挂账改注「B① 3/4 子项核销+逐行过期编辑→m2-5/TC-UI 手动走查批」，R2 顺手实现亦可不阻断）；P3-2 B⑥ 只做一半（store 侧 5 处 strftime 字面量未收编〔pg:1759/3167/3250/3526/3764〕+`_EXPIRES_LIB_FORMAT` 成死常量+taskclock docstring 过强——R2 顺手或登记）；P3-3 唯一 admin 守卫 pg datetime 比较 500（PATCH org_admin 幂等/空 PATCH 带 expires 时 datetime>str TypeError——REST 用例仅 sqlite 全绿假象）+守卫与写操作 TOCTOU（并发降级双 admin 可同见 count=2 终态 0 admin）——R2 建议修；P3-4 A4 细节（label 被静默丢弃/retired 维度 enable 未拒与 create 409 不对称/幂等 enable 恒 applied=True）——R2 建议修；P3-5 A2 取消/pending 窗口（重置先于存活检查——claim 后取消或 pending 覆盖上传在途时 active 块已删+状态 parsing 文档不可搜需用户自行发现；reset 前检查任务终态+pending_version 拒绝/改投）——R2 建议修；P3-6 测试质量（inline 兜底循环与直插任务用例时序 flake 风险/rebuild_env 未用 params 重复跑一倍 34→18 可省/cycle·orphan_rows .code 未断言/3 处 docstring 编号陈旧）——顺手或登记；P3-7（=Tester P3-2）pg 残留 schema 归监督侧运维清理；P3-8（=Tester P3-3）RUNBOOK 注记归 docs 批。**需求边界 N-1×1**（reembed 组织口径与触发权限——冻结文档=全库、m2-3 入口=owner/org_admin+payload {org}、实现=org 级覆盖+全局切换；裁定 (a) 全库迁移〔与 design/TC 一致，org_admin/sysadmin+全组织覆盖率门〕或 (b) 按组织迁移〔决策变更须 issue+D 号+全局切换拆独立阶段〕；P2-2 修复方向依赖此裁定——**待用户裁定**）。**择型 11 条裁定：①ACCEPT 附条件（P2-1 修复后完全成立）、②~⑪全 ACCEPT**（③扫描超集+docs 批措辞回写、⑧RUNBOOK 注记、⑨semantic_retag 尾序保留）。安全性深审 ✅（members/values 越权面/级联授权/审计同事务/JIT 链路/SQL 参数化——未发现 P1 级安全缺陷；P2-2 权限面唯一新暴露面）。测试质量：达验收覆盖但关键缺失=semantic_build 未执行（P2-1）/reembed 全单组织用例（P2-2）/守卫无 pg 用例。**R2 最小修复集**：P2-1+P2-2（按 N-1 裁定）+P3 应修尽修（P3-2/3/4/5 建议、P3-1/6/7/8 按登记）。docs 批建议八项（TEST-CASES v1.9.12/known-gaps 视裁定/design v0.9.8/RUNBOOK/AGENTS/_m2-plan/检查点/工作区 docs 批入库）。本轮只读零修改零 git 写。报告全文见「最新验证意见原文」details 块（R1 Committer）。
- **R1 需求边界上报（status=spec_confirm，待用户裁定 N-1）**：supervised-coding 2026-11-01 17:13 按协议置 spec_confirm——NEEDS_CHANGES 含需求边界问题不直接发 coder；N-1（reembed 组织口径与触发权限）原文复述给用户裁定，裁定后更新任务原文、round=2 调 coder 修复（P2×2+P3 应修尽修）。
- **R1→R2 边界裁定（2026-11-01 17:19 用户，spec_confirm→implementing，round 1→2）**：**N-1 选 (a) 全库迁移 + 权限收 sysadmin 专属**（用户理由：换模型是系统级配置项，org_admin 甚至都没有权限——FR-4 owner/org_admin 语义限单文档重索引）；裁定已落任务原文 A1（全库扫描/覆盖率门/清理+sysadmin 门控+多组织双后端用例必补；单文档 reindex 不带 embed_model 维持 owner/org_admin）。**R2 修复范围（沿 m2-4 应修尽修先例，用户未异议）**：P2-1（semantic executors 标签源修复〔runner 改读 services.settings 或 SettingsHolder〕+inline ServiceContext/MCP settings 同步+semantic_build 实际执行用例双后端）+P2-2（按 N-1 裁定全库口径+sysadmin 权限+多组织用例）+P3-2（B⑥ store 侧 5 处 strftime 收编 TS_FMT+删死常量+docstring）+P3-3（守卫 expires 归一化修复 pg 500+守卫与写操作同事务/锁定读+pg 用例）+P3-4（label 传递或显式不支持+retired 维度 enable 409+applied 按 rowcount）+P3-5（reindex reset 前检查任务终态+pending_version 在途拒绝/改投+双后端用例）+P3-6 顺手（测试质量四小项：inline 兜底隔离/rebuild_env 冗余 params 收 34→18/cycle·orphan .code 断言/docstring 编号陈旧）；**P3-1 B①逐行过期编辑按 Committer 裁定登记去向 m2-5/TC-UI 批**（R2 顺手实现亦可）；P3-7 pg 残留 schema 归监督侧核对清理；P3-8 RUNBOOK 注记归 docs 批。
- R2: coder 完成（2026-11-01 17:59，**续接会话**，coderTaskId=ses_e6a18509affeLOmueMfB4vItlo，commit `bd9598f1614c1e40a22e5d2e09005a885a060174` 于 develop_opencode，18 files +1044/−315，父提交=f979405，origin/develop=c2ebb68 无前进确认，未 push）——**P2-1** ✅ semantic 标签源统一：config.py 新增 `effective_settings(base, embedder)`（标签/维度统一从 embedder.model_label 派生），4 个 semantic executors 改传 effective（subprocess/inline 同修）+FingerprintProbe validate_dim 派生+coverage dim 派生+api/semantic.py·mcp/server.py 6 个闭包消费点改派生——build 写入与查询共用同源（m2s-6 vec 用例回归暴露半程方案分裂后收口）；新用例：semantic_build 实际执行（dict_rev≠首次/stats.embed_model=新标签/fuzzy 行新标签）+probe dim 跟随+coverage dim 断言。**P2-2** ✅ 按 N-1 裁定：store 4 方法+embedding_coverage 支持 org_id=None 全库口径+新增 list_org_ids；执行体全库扫描/全库覆盖率门/全库清理+逐组织 quality recompute 与 semantic_build 投递；api reembed 分支 **sysadmin 专属**（owner/org_admin 403、check_path_org 使 sysadmin 免本组织成员关系可触发）；多组织双后端用例（org:tax 投递后 org:gl 同迁+全库单标签+缺块形态不放行切换）+权限三态断言。**P3-3** ✅ 守卫整体下沉 store（BEGIN+pg FOR UPDATE 行锁+同事务 count+SQL 侧过期比较——500 与 TOCTOU 双根除；MembershipLastAdminError 新异常；API _last_admin_guard 删除只留 409 映射）+store 级双后端用例（含 pg datetime 路径）。**P3-4** ✅ label 显式传递（缺省=value）/retired 维度 enable 409 与 create 对称/applied 按 rowcount/docstring 修正+用例×3。**P3-5** ✅ reindex 三重前置（取消终态不重置/should_continue 探测/pending 在途 fail-closed——API 409+执行体双防线）+用例×3。**P3-2** ✅ pg 5 处 strftime 收编 TS_FMT+删 _EXPIRES_LIB_FORMAT 死常量+taskclock docstring 修正。**P3-6** ✅ 四小项（_quiet_inline fixture 停兜底循环隔离直插用例/rebuild_env·reindex_env params 收编去重 34→30/orphan 锁死 multi_heads 实际路径+cycle·orphan_rows 可达性 docstring 诚实收窄〔hash 自洽约束下不可静态构造〕/docstring 编号×3+排序断言）。**P3-1 不修申报**：B①逐行过期编辑按裁定登记 m2-5/TC-UI 批（UI 无门禁覆盖、优先保修复轮质量）。自测：TDD 红灯×3（新用例 12 failed 对应 P2-1/P2-2/P3-5/守卫 DID NOT RAISE/m2s-6 vec 回归暴露即证伪）；GATE PASS **1642+1 双后端双模式 0 skipped**（R1 1637+1 → +5 净增对账：wk_rebuild 收编去重 −4〔def test 零减少〕+members +2+values +6+manage +1；pg 臂 611=577 参数化+34 专用全实跑）。机械核验（supervised-coding 19:09）：HEAD=bd9598f ✓、commit 格式 R2 ✓、18 files 全在 src/tests ✓、监督侧 4 文件原样 ✓、未 push ✓；filesChanged 更新为累计并集 39（+config.py/api/semantic.py/mcp/server.py）。verdict 双置空待 R2 重验。**择型申报 7 条**：①P2-1=统一从 embedder.model_label 派生（effective_settings——全部消费面永远与 embedder 一致、无需广播 settings 引用替换；ServiceContext.settings 保留旧对象申报为可接受滞后〔embed 相关字段消费面已全派生〕）②P2-2=store 单方法双口径（org_id=None 动态过滤）+联动逐组织遍历+payload.org 保留投递上下文 ③P3-3=守卫整体下沉 store 事务化（行锁+同事务 count 串行化）④P3-4=label 加参显式传递 ⑤P3-5=投递面 409+执行体 fail-closed 双防线 ⑥P3-6①=停兜底循环线程 fixture（比独立 app 轻）⑦P3-6③=orphan 锁死实际路径+cycle/orphan_rows docstring 收窄不伪造断言。
- R2: tester **PASS**（2026-11-01 19:31，**续接 R1 会话**，testerTaskId=ses_e69ca7427ffe909TXr7yUZvXIO，testedSha=bd9598f1614c1e40a22e5d2e09005a885a060174 全 SHA 复核一致）——门禁独立复跑 **GATE PASS 1642+1 双后端双模式 0 skipped**（pg 臂 611=577+34 全实跑；+5 对账独立核对闭合：members +2/values +6/manage +1/wk_rebuild 收编去重 −4；**去重 −4 非删用例核实**——删的是未用 params 行、def test 零减少反 9→15、断言均升级替换改强；fixture 换名非删函数）。**修复闭环逐条勾验全 ✅**：P2-1 派生方案（effective_settings 穷尽核阅全部消费点——**reembed 后实际执行 semantic_build** status≠skipped/dict_rev 含新标签/probe dim 跟随/m2s-6 vec 回归同源）；P2-2 N-1 裁定落地（store 5 方法双方言 org_id=None 逐语句等价+全库覆盖率门+多组织双后端用例〔org:gl 同迁+全库 stray=0〕+sysadmin 三态断言+check_path_org 形态+单文档 reindex 维持 owner/org_admin）；P3-3 守卫下沉事务化（pg FOR UPDATE+SQL 侧比较+同事务 count——500/TOCTOU 双根除+store 级双后端用例含 pg datetime 路径）；P3-4 label/applied/retired 409（store 层）；P3-5 三重前置双防线；P3-2 pg 5 处收编+死常量删；P3-6 四小项（含 docstring 收窄诚实性）；P3-1 不修申报合规（web/ 零改动）。**择型 7 条全 ACCEPT**（①附 P3-2 残余——api/search.py:72 例外；其余全成立）。回归面 ✅：R1 57 条全在且绿、R1 择型 11 条语义零破坏（④re-pin 回归注入红绿复验）、m2-3 投递面 -O 修复不被隔离破坏、m2s-6 semantic 路径回归。**注入验证 3 组红绿**（①executor 回退旧 settings→semantic_build 用例红〔P2-1 缺陷形态精确重建〕②全库扫描回退恒 org 过滤→多组织用例红〔覆盖率门不收敛〕③R1 择型④回写谓词回归注入——业务代码零残留）。临时产物清理 ✅（pg 零新增 schema〔存量 7 个 bench/eval 残留维持 Committer P3-7 裁定〕/临时目录全删/工作区终态一致）。**P1/P2 无；P3×4**：P3-1（轻）A4 retired 维度 enable 的 **REST 面缺 ValueError→409 映射实证 500**（store 层成立、api/admin.py enable 分支与 create 分支不对称——单行级补丁，相对 R1 幂等 200 是 REST 面回归）；P3-2（轻，P2-1 残余）**api/search.py:72 resolve_query_entities 未派生**（MCP 同函数已派生——REST auto_entities=true 向量增益查旧标签谓词静默降级，inline 窗口限定，单行级）；P3-3 观察（switch_blocked 用例无负向判别断言——全库门语义已由 SQL 审读+注入②间接证实，建议后续补 org 永久缺块形态）；P3-4 观察（pg 残留 schema 维持监督侧清理登记）。报告全文见「最新验证意见原文」details 块（R2 Tester）。
- R2: committer **NEEDS_CHANGES**（2026-11-01 19:41，**续接 R1 会话**，committerTaskId=ses_e69aa3034ffeswmU0kfrWYy0rF，reviewedSha=null——R2 未通过；testedSha=bd9598f=HEAD 一致；R2 diff=f979405..bd9598f 18 files 逐文件核对；门禁采信 Tester 独立复跑+静态对账自洽）。**P1×1**：**P1-1** embedding_coverage org-scoped 调用泄露跨组织 datasets——R2 P2-2 全库化把外层 `WHERE ds.org_id=:org` 删掉未加动态过滤（sqlite:2532-2552/pg:3802-3824——org_filter 只加在子查询、外层 FROM datasets 无过滤）→ org_admin 调覆盖率面板可见**全库所有组织的 dataset_id/name**（total=0/done=0 行）——违反跨组织隔离（m2-5 TC-OPS-09/T15 硬约束；Tester 未捕获）；修法=外层动态 ds_filter+store/API 双后端测试（他组织 dataset 不出现、全库仍全量）。**P2×1**：**P2-1** reindex pending_status=failed 仍放行——API/执行体条件 `pending_status != "failed"`（admin.py:538-545/rebuild.py:323-337）failed 放行，但 ingest `_guard_alive` 仍 `pending_version or active_version` 取 pending 为当前目标（ingest.py:700-719）→ 202 后 delete_by_doc+set parsing→run_task 判 cancelled→**文档停在 parsing、在用块已删、不可搜且 reindex 恢复路径被自身堵死**（新 API 用例只断言 202 不查终态=false green）；修法按 N-2 裁定（A 保守 409 推荐/B 修 _guard_alive）。**P3×8**：P3-1 pg 守卫跨行 TOCTOU 残余（FOR UPDATE 只锁目标行——两并发请求互降两名 admin 各自 count=2 均通过→0 admin；R2「TOCTOU 根除」docstring 过强；修法=锁全组织 admin 行或 advisory_xact_lock+pg 并发用例；建议 R3 修否则登记 G-27）；P3-2（=Tester P3-1）retired enable REST 缺 ValueError→409 映射实证 500（admin.py:185-196 与 create 分支不对称——**R3 必修**单行）；P3-3 **更正 Tester P3-2**：api/search.py:72 未派生**不构成功能缺陷**（resolve_query_entities→annotate_text 未传 fuzzy/embedder——该路径无 vec 增益，settings 仅 legacy fallback 告警用）——接受为一致性小项 R3 顺手一行；P3-4 switch_blocked 用例无负向判别（建议 R3 补 org 永久缺块形态或改名）；P3-5 卫生（admin.py:58 TS_FMT 未用 import 删/audit_chain 顶层 docstring 未收窄/test_admin_values docstring 对齐）；P3-6 B①维持登记合规；P3-7 pg 残留监督侧；P3-8 RUNBOOK 归 docs 批。**需求边界 N-2×1**（pending 失败版本存在时 reindex 语义：(a) 保守 409——任何 pending_version 非空含 failed 一律拒绝待清理后重投 / (b) 放行——_guard_alive 视 failed pending 为亡故以 active 为目标重建〔触及 core ingest 语义需回归〕——**待用户裁定**，Committer 推荐 (a)；N-1 已按用户裁定闭合不再挂账）。**R1 意见闭环核验**：P2-1 语义闭合（附 P3-3 一致性）/P2-2 语义闭合但新引入 P1-1/P3-2 闭合/P3-3 部分闭合（pg 500 根除、跨行 TOCTOU 残余）/P3-4 部分闭合（store 成立、REST 500）/P3-5 部分闭合（parsing 双防线成立、failed 放行破坏）/P3-6 基本闭合/P3-1 不修合规。**N-1 落实语义审查 ✅**（全库门 SQL 语义正确+注入②判别；sysadmin check_path_org 形态无新绕过——测试缺口 sysadmin 无 membership 形态未覆盖 P3 级建议 R3 补）。**R2 择型 7 条裁定**：①③④⑤ ACCEPT 附条件（P3-3/P3-1/P3-2/P2-1 残余）、②ACCEPT 附 P1-1、⑥⑦全 ACCEPT。**未弱化确认 ✅**（去重 −4 性质复核、断言改强）。**Tester P3×2 裁定**：P3-1 retired REST 500=R3 必修；P3-2 search.py=不成立功能缺陷接受一致性小项。**R3 修复范围（最后一轮需一次过）**：P1-1+P2-1（按 N-2）+P3-1（或登记 G-27）+P3-2+P3-3 一行+P3-4+P3-5 卫生+sysadmin 无 membership 用例；B①维持登记。docs 批终版建议/遗留去向建议已列。本轮只读零修改零 git 写。报告全文见「最新验证意见原文」details 块（R2 Committer）。
- **R2 需求边界上报（status=spec_confirm，待用户裁定 N-2）**：supervised-coding 2026-11-01 19:41 按协议置 spec_confirm——NEEDS_CHANGES 含需求边界问题（N-2 pending failed reindex 语义）不直接发 coder；复述给用户裁定后 round=3（**最后一轮**）调 coder 修复（P1-1+P2-1+P3 应修尽修）。
- **R2→R3 边界裁定（2026-11-01 19:47 用户「按建议执行」，spec_confirm→implementing，round 2→3 最后一轮）**：**N-2 选 (a) 保守拒绝**——pending_version 非空（含 failed）一律 409/fail-closed 拒绝 reindex、core ingest 不动、false green 用例重写（裁定已落任务原文 A2）。**R3 修复范围（Committer §9 建议）**：必修=P1-1（embedding_coverage org-scoped 外层动态 ds_filter+store/API 双后端测试——他组织 dataset 不出现、全库仍全量）+P2-1（按 N-2 (a)——API 409+执行体 fail-closed+API 用例第二段改 409+文档终态断言+执行体 failed 形态用例）+P3-2（retired enable REST 补 except ValueError→409+REST 用例〔retire→disable 200→enable 409〕）；应修尽修=P3-1（pg 守卫跨行并发：锁全组织 active org_admin 行 FOR UPDATE 或 pg_advisory_xact_lock+两连接互降并发用例——若确有困难降级登记 known-gaps G-27 但 backend.py「TOCTOU 根除」docstring 必须改如实）+P3-3（api/search.py:72 改传 effective_settings 一行）+P3-4（switch_blocked 补负向判别或改名+独立负向用例）+P3-5（卫生三小项：admin.py:58 TS_FMT 未用 import 删/audit_chain 顶层 docstring 收窄或 test_ops_chain_read 补 .code/test_admin_values docstring 对齐）+sysadmin 无本组织 membership 触发 reembed 202 用例（权限形态实证）；B① 维持登记 m2-5 不动。
- R3: coder 完成（2026-11-01 20:05 报告，**续接会话**，coderTaskId=ses_e6a18509affeLOmueMfB4vItlo，commit `00dc486ab3d6351702a079e07207dfc63903e059` 于 develop_opencode，11 files +364/−57，父提交=bd9598f，origin/develop=c2ebb68 无前进确认，未 push；filesChanged 并集不变 39——R3 全部文件已在清单内）——**P1-1** ✅ embedding_coverage org-scoped 外层动态 ds_filter（sqlite/pg 双方言——他组织 dataset 泄露根除；gate 全库口径内层 org_filter 未动）+store 双后端用例（org:gl dataset 不出现/org-scoped 含本组织/None 含全部）+API 端点补断言。**P2-1** ✅ 按 N-2 (a)：API/执行体双防线对任何 pending_version 非空（含 failed）一律拒绝（API 409 带提示/执行体 failed 带原因）——ingest._guard_alive core 语义零改动；false green 用例重写（第二段 409+终态断言 searchable_full/在用块保留/任务零投递）+执行体 pending 参数化 ["parsing","failed"] 双形态双后端。**P3-1** ✅ pg 守卫咨询锁：`pg_advisory_xact_lock(hashtext(org))` 事务级串行化（**择型：弃全 admin 行 FOR UPDATE**——实测并发提交后等待方 EPQ 抛 tuple concurrently updated，docstring 记弃用因）+pg 并发互降用例（两连接恰一侧 ok 一侧 blocked、终态恒 1 admin；**注入证伪 5/5 红→恢复 3/3 绿**）；sqlite 单写者天然串行；协议 docstring「TOCTOU 根除」措辞如实化。**P3-2** ✅ enable 分支 except ValueError→409（与 create 对称）+REST 链路用例（retire→disable→enable 409）+docstring 对齐。**P3-3** ✅ api/search.py:72 改传 effective_settings（一致性收口）。**P3-4** ✅ 拆解：正路径改名 full_scan_fills_other_org_gaps+独立负向 no_switch_until_full_library_converged（monkeypatch 覆盖率恒缺一块→任务 failed+切换/清理/联动全未发生+旧标签向量保留〔写入阶段①合法——门拦的是切换〕）；**附带收口**：执行体「未收敛」从 raise 改 fail-closed（update_task failed+return——直调/runner 语义一致，负向红灯暴露）。**P3-5** ✅ 卫生三小项（TS_FMT import 删/audit_chain docstring 收窄「3 码+2 防御分支」/values docstring）。**sysadmin 无 membership 用例** ✅（删成员关系保留 is_system_admin→POST 202+done+切换断言）。**不修**：P3-6 B①（web/ 零改动）/P3-7/P3-8 按裁定。自测：TDD 红灯×3+注入证伪（P1-1 泄露 2 failed/P2-1 3 failed/P3-1 摘锁 5/5 红/P3-4 直调上抛暴露）；GATE PASS **1651+1 双后端双模式 0 skipped**（R2 1642+1 → +9 对账：wk_rebuild +4〔负向×2+failed 形态×2〕/manage +3〔no_cross_org_leak×2+sysadmin×1〕/members +1〔pg 并发〕/values +1〔REST 409〕；pg 臂 614=580+34 全实跑）。机械核验（supervised-coding 20:05）：HEAD=00dc486 ✓、commit 格式 R3 ✓、11 files 全在 src/tests ✓、监督侧 4 文件原样 ✓、未 push ✓。verdict 双置空待 R3 重验。**择型申报 3 条**：①P3-1=advisory_xact_lock（FOR UPDATE 集合锁 EPQ 竞态弃用——docstring 记因）②P3-4=monkeypatch 覆盖率恒缺一块（无合法静态永久缺块形态——精确注入收敛门）③P2-1 未收敛=raise 改 fail-closed（两路径语义一致）。
- R3: tester **PASS**（2026-11-01 20:22，**续接 R1/R2 会话**，testerTaskId=ses_e69ca7427ffe909TXr7yUZvXIO，testedSha=00dc486ab3d6351702a079e07207dfc63903e059 全 SHA 复核一致；**最后一轮严格标准——未发现任何新 P1/P2 缺陷**）——门禁独立复跑 **GATE PASS 1651+1 双后端双模式 0 skipped**（pg 臂 614=580+34 全实跑；+9 对账独立核对闭合：wk_rebuild +4/manage +3/members +1/values +1；def test 只增——diff 中 3 个「删除函数名」逐个核实均为重写/改名、2 行删 assert 为 N-2 语义变更替换非弱化）。**修复闭环逐条勾验全 ✅**：P1-1 跨组织泄露根除（双方言 ds_filter/org_filter 双层 SQL 审读分层验证——gate 全库门不受影响；**R2 漏检根因复盘**〔验证停在计数口径未到行集泄露面〕+**三组织/多 dataset 自构造独立验证 ALL PASS**〔含 total>0 真实行形态，强于 coder 造数〕+注入①判别实证）；P2-1 N-2 (a) 双防线（core ingest 零改动 diff 证实；false green 重写三重终态断言；pending 参数化双形态双后端；**注入②双防线独立性实证**——API 回退红而执行体 4 条仍绿）；P3-1 咨询锁（EPQ 弃用记因 docstring+注释双处诚实；pg 两连接真并发互降恰一侧 ok+终态恒 1 admin；**注入③ 5/5 红复核 coder 证伪声明**）；P3-2 REST 409 链路；P3-3 一行；P3-4 正路径改名+负向四重断言；P3-5 卫生；sysadmin 无 membership 202 用例。**择型 3 条全 ACCEPT**（③附行为注记：未收敛从「runner 自动重试」收窄为「failed 留人工」——fail-closed 已申报，后续可在 runner 按 error 分类回队〔docs 批可选登记〕；①hashtext 键冲突=跨组织偶发串行化纯性能面）。回归面 ✅（R1 57+R2 5 全存量绿、择型核心语义零回归〔re-pin/with_model/pending 超集/kick〕、m2-3 投递面延续）。**注入验证 3 组红绿**（①ds_filter 摘除泄露精确复现 ②pending failed 豁免回退+双防线独立性 ③advisory lock 摘除 5/5 红——业务代码零残留）。临时产物清理 ✅（pg 零新增〔存量 7 个维持监督侧〕/临时目录全删/工作区终态一致）。**P1/P2/P3 新增均无**；观察 4 条（择型③行为注记 docs 批可选/hashtext 性能面/pg 残留+RUNBOOK 维持登记/三轮遗留登记核对合规——B①→m2-5、m2-4 followups 余二→下批 m2-5）。报告全文见「最新验证意见原文」details 块（R3 Tester）。
- R3: committer **APPROVED**（2026-11-01 20:26，**续接 R1/R2 会话**，committerTaskId=ses_e69aa3034ffeswmU0kfrWYy0rF，reviewedSha=00dc486ab3d6351702a079e07207dfc63903e059=testedSha=HEAD **三一致**；R3 diff=bd9598f..00dc486 11 files 逐文件核对；门禁采信 Tester 独立复跑+对账/测试 diff 独立核验——3 个「删除函数名」核实为重写/改名、2 行删 assert 为 N-2 语义变更，**零弱化**）。**R2 意见闭环核验全 ✅**：P1-1 闭合（双方言外层 ds_filter+内层 org_filter 独立——gate 全库门不动；全部调用面核阅无同类泄露残留；注入①判别）；P2-1 闭合（N-2 (a) 双防线+core 零改动 diff 证实+false green 重写三重终态断言+注入②双防线独立性）；P3-1 闭合（advisory_xact_lock BEGIN 后即刻取锁、**无死锁面**〔每事务一锁无嵌套〕、EPQ 弃用记因双处诚实、注入③ 5/5 红复核）；P3-2~P3-5+sysadmin 无 membership 全清偿；B①维持登记合规。**R3 择型 3 条全 ACCEPT**（③附 docs 批登记——fail-closed 行为变化 + P3-2 文案）。安全性终审 ✅（P1-1 修复完整性/advisory lock 无死锁/409 无绕过/sysadmin 无新越权/审计无缺失——无新 P1/P2）。**P1:0 P2:0；P3×3 记录级**（P3-1 pg 并发用例 docstring 旧称「FOR UPDATE」/P3-2 fail-closed 注释+错误文案旧称「自动重试」/P3-3 coverage 端点 docstring 旧称「全局口径」——均文案精度无功能影响，转 docs 批+下批卫生）。**需求边界无新增**（N-1/N-2 均闭合；择型③行为变化归 docs 批登记）。**docs 批终版建议八项**（TEST-CASES v1.9.12——TC-EMB-06 全库口径+扫描谓词超集注记+coverage org 只列本组织+reindex pending 含 failed 409+sysadmin 含无 membership+未收敛 failed 留人工+B① 3/4 改注+members/values 端点形态+A5/B5+门禁 1651+1；known-gaps——fail-closed 登记/hashtext 性能面可选/B①+m2-4 followups 余二去向/pg 残留运维清理/**G-27 不再需要**；design v0.9.8 非决策——§5.3 全库迁移/sysadmin/切换载体/清理与回退窗口/fail-closed+§5.6/§6.2 端点表+§5.8 effective 标签源+reindex pending；RUNBOOK §1 蓝绿操作序列+重启窗口+未收敛处置+§4 重索引窗口+审计 B5+pg 残留可选；AGENTS §1 状态行；_m2-plan row 7.5 done+挂账；检查点终态；工作区 docs 随 chore 入库）。**遗留事项终版去向**（供遗留事项节回写）：B①→m2-5/TC-UI 批；m2-4 followups 余二→下批/m2-5 测试补强批；P3×3 文案/注释→docs 批+下批卫生；fail-closed 行为→docs 批登记（后续 runner 按 error 分类回队可选）；pg 残留→监督侧 DROP CASCADE；RUNBOOK 注记→docs 批；TC-UI→用户侧；无 G-27 新登记。**manifest 要点**：双 SHA=00dc486 三一致/门禁 1651+1 双模式 0 skipped（pg 614=580+34）/+9 对账/rounds=3（PASS·NC→PASS·NC→PASS·APPROVED）/specRulings（R1 任务书确认+N-1 全库·sysadmin+N-2 保守 409）/gapClosures/handover/stale=false。本轮只读零修改零 git 写。报告全文见「最新验证意见原文」details 块（R3 Committer）。
- **双通过达成（2026-11-01 20:26，round 3/3 收敛）**：testVerdict=PASS + reviewVerdict=APPROVED，testedSha=reviewedSha=00dc486=当前 HEAD（develop_opencode）——status=approved，待用户确认交付。
- **交付执行（2026-11-01 20:33，用户确认交付「同意」）**：① 监督侧 docs 批落笔完成（TEST-CASES **v1.9.12**——m2-6 段完成态+TC-EMB-06 实现口径注记+coverage org 口径+N-1/N-2 裁定+B① 3/4 改注；known-gaps **G-27** 新增〔未收敛 fail-closed+hashtext 性能面附注〕；design **v0.9.8**——§5.3 全库重嵌入+sysadmin+fail-closed/§5.6 members 写路径/§5.8 effective 标签源/§6.2 端点登记〔非决策〕；**RUNBOOK** §1 m2-6 执行体操作口径块+§4 审计月库读回行 B5 注记〔A5 移交收口〕；AGENTS §1+`_m2-plan` row 7.5 done/§二要点/§三挂账清偿回写/§五 m2-5 指引）；遗留事项节回写（m2-3 P3×10+m2-4 N-1·followups①②③ 清偿+B①/P3×3 移交去向）；② chore 归档批 **`1076f939d29d043e2015d073849664bd4f886785`**（8 files +911/−29 docs-only——doc-only 验证通过〔src/tests 零改动〕；reviewedSha 按 m2-2/m1-4/m2-4 先例更新为归档 HEAD、testedSha 保持 00dc486）；③ 交付链执行（2026-11-01 20:44，coder 续接会话——首次调用限额中断后核查未执行任何步骤、续接重跑）：push 成功（fcc80ef..1076f93，SSH）；**PR #12 已开**（base=develop，https://github.com/yq3/knowledge-lattice/pull/12 ，4 commits：f979405/bd9598f/00dc486/1076f93，body 含交付摘要+Evidence Manifest 占位）。④ Committer PR 审查留痕 **`PRR_kwDOVZ9dhM8AAAABVWwwYA`**（2026-11-01 20:46，COMMENTED 形态〔self-approve 限制沿 #2~#11 先例〕——正文首行 APPROVED+R1→R3 轨迹+门禁采信+残余登记+归档 commit 1076f93 doc-only 复核〔8 files 零 src/tests〕+合入留所有者）；⑤ Coder manifest JSON 入 PR #12 description（回读校验 json.loads 通过+原摘要 3682 字符零丢失；监督侧补正 sessions.coder 转写偏差一处——MfB/Bf4 颠倒，gh pr edit 修正后复核 JSON OK）。
- **合入（终章）**（2026-11-01 20:50，用户指令「合入」）：**PR #12 MERGED**——mergeCommit **`d3dfdc0f506632cdf6a4f131c0fb2a6f05bfb4b1`**（merge 形态沿 #2~#11 先例、远端分支保留）。origin/develop 前进至 d3dfdc0；本地 develop_opencode 已 ff 同步。下段（m2-5）开工时以 d3dfdc0 为基线（_m2-plan §五 指引补记随 m2-5 批）。本合入条目为 chore 批 1076f93 之后的工作区改动（随下段 m2-5 chore 归档批入库——沿先例）。**任务闭环（3 轮，1580+1→1651+1）**。
- **交付完成（终态）**（2026-11-01 20:48，status=done 自 20:33 起持续有效）：**PR #12 OPEN/MERGEABLE 待用户合入**：https://github.com/yq3/knowledge-lattice/pull/12 ——交付摘要+4 commits+Committer 留痕（PRR_kwDOVZ9dhM8AAAABVWwwYA）+17 键 evidence manifest（双 SHA=00dc486/1076f93+shaNote 归档先例+gate 1651+1+rounds=3+specRulings 3 条+gapClosures/gapRegistrations G-27/handover 4 条/stale=false）全在位。**未执行 merge（协议约定——合入指令归用户）**。本条目及④⑤为 chore 批 1076f93 之后的工作区改动（随下段 m2-5 chore 归档批入库——沿 m2s-6/m2-4 先例）。

## 最新验证意见原文

<details>
<summary>R1 Tester 报告全文（ses_e69ca7427ffe909TXr7yUZvXIO，2026-11-01，testVerdict=PASS）</summary>

# task-knowledge-lattice-m2-6 R1 独立验证报告

**testVerdict: PASS**
**testedSha: `f9794054973e376c573e877185a849aad7c1eee8`**（= f979405，develop_opencode HEAD，复核一致）
验证时间：2026-11-01；全新会话独立执行，未采信 coder 自测结论。

## 一、门禁独立复跑（双后端双模式）

```
docker start lattice-pg; export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
scripts/test_gate.sh
→ GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
  （pg 臂 609 条用例全实跑：[pg] 参数化 575 + PG 专用 34）
```

| 模式 | 结果 | 时长 |
|---|---|---|
| 常规 `uv run pytest -m "not manual" -q` | **1637 passed, 1 deselected, 0 skipped** | 211.65s |
| `python -O -m pytest -m "not manual" -q` | **1637 passed, 1 deselected, 0 skipped** | 236.57s |
| pg 臂收集（独立复算） | **609 = 575（正则 `\[pg[^]]*\]`）+ 34（test_pg_*）** | — |

- **对账**：1637 = 基线 1580 + **57**，逐文件归因独立核对一致：test_wk_rebuild **34**（新文件；6 rebuild_env×4 + 2 reindex_env×4 + 1 matrix×2，双层参数化 matrix×env 实证）+ test_admin_members **11**（4 store×2 + 3 REST）+ test_admin_values **8**（3 store×2 + 2 REST）+ test_admin_store_reads **+3**（7→9 函数：+read_org_audit 双后端、+audit_chain_error_codes 单条 = 14→17 收集数）+ test_pg_api_diff **1** = 57 ✓
- **零删除零弱化**：`git diff c2ebb68..f979405 -- tests/` 无任何被删 `def test_`/`parametrize` 行（机器核验 NO_REMOVED_TESTS）；与基线对照只增不减 ✓
- **skip 核对**：双模式 0 skipped（gate skip=失败语义拦截）；唯一 1 deselected = `-m "not manual"` 的 TC-UI 人工走查（政策性排除，非本任务范围）；任务范围内无 skip ✓

## 二、分用例判定表

| 用例 | 判定 | 证据摘要 |
|---|---|---|
| **TC-EMB-06①** 并行写入零降级 | ✅ | `test_tc_emb06_bluegreen_full_cycle`×4（中断缝①实证并行窗口：任务非终态）；`pending_reembed_batch` 双方言谓词（tombstone=0 AND NOT EXISTS (rid,:new)）逐语句等价；零降级结构保证=择型②专用实例（主实例旧标签不动，rebuild.py:139-143 + embedder.py:92-98） |
| **TC-EMB-06②** 覆盖率 100% 原子切标签 | ✅ | `embedding_coverage` 双方言分子分母均限 `active_version + tombstone=0`（在用块口径 TC 不破）；切换零 SQL：settings/embedder/ingest/quality 四对象图同批断言（test:145-148） |
| **TC-EMB-06③** 竞态在途回写无孤儿 | ✅ | test:155-159 迟到旧批次回写 `written==0`、单标签；防护谓词 `c.embed_model=:label`（sqlite:434/pg:528）+ re-pin（择型④顺序 写满→切换→re-pin→补扫→清理，rebuild.py:178-218）；**注入实证红/绿（见 §四）** |
| **TC-EMB-06④** 清理+quality+semantic_build 联动 | ✅ | `delete_vectors_by_label` 后全库单标签断言；`invalidate_quality_cache`+`recompute`（`test_tc_emb06_quality_rerun_linkage`×2：旧 vector_crowding 清除+缓存回写）；semantic_build 强制投递断言（tasks 表）；阈值重标定=运维配置（择型⑤一致） |
| **A2** reindex 端到端 | ✅ | `test_reindex_full_chain`×2（投递→新块 id≠旧块→当前标签向量→searchable_full→FTS 命中）；`test_reindex_interrupted_reclaim_no_loss`×2（中途停非终态→重认领 done→块集不丢不重） |
| **A3** members 增/改/删 | ✅ | 11 条全过：store 级 add（404/409 含过期行/审计同事务）、update（角色/软停用/改永久/ISO 归一/T23 拒）、delete（级联清本组织授权、他组织不受影响）、REST CRUD 全链（403 门控/404/201/409/204/审计三枚） |
| **A3** JIT→入组→授权→检索（D16 闭环） | ✅ | `test_jit_to_grants_full_api_chain`：mock-idp 首登 403 + `auth.user_jit_created` 审计==1 → POST members 201 → 无授权检索 200 空域收紧（T22）→ PUT grants → 检索 200，全程 API 不碰 DB 写 |
| **A3** T23 触发器语义 | ✅ | `test_t23_recovery_path_delete_readd_regrant`×2（过期行续期拒→DELETE 级联→重加→补授权→展开恢复）；store 过期行前置异常双方言 + API PATCH 409 |
| **A4** values CRUD + D19 重新启用 | ✅ | 8 条全过：create（retired 409/重复 409/404/审计）、**enable 解锁 locked_docs 联动**（disable 升→enable 回落，双后端+REST 端到端）、幂等零新审计、enable+dry_run→400、T3 收紧-恢复闭环 |
| **B①** UI fresh | ✅ | 实现面（existing 映射/预填/has-exp 徽标/langchange preserve）+ **独立 playwright DOM 三断言复现**（见下） |
| **B②** 同秒单调键 | ✅ | 0010 双方言（sqlite rowid 占位迁移 / pg seq IDENTITY 存量回填）；claim/list_tasks 次级键双方言同改（semantic_retag 尾部优先级保留）；**注入实证红/绿** |
| **B③④⑤⑥⑦⑨⑩** | ✅ | ③normalize_expires_at 双方言直调收口；④read_org_audit 下沉（api 只消费、双源合并/去重/排序双方言+测试）；⑤AuditChainError 五机器码 multi_heads/fork/hash_mismatch/cycle/orphan_rows+固化用例；⑥TS_FMT 单源（admin.py:299 双源消除）；⑦协议 docstring 字符串契约（backend.py:559-562）；⑨ULID→uuid4 注释×2 勘误（diff 证实）；⑩值序反向造数 (3,2,1)+断言==1 锁死「取最近≠取最大」双分支 |
| **B⑧** create_app backend 注入 | ✅ | 可选参数缺省走 build_backend 工厂（app.py:233-236，向后兼容——门禁 1637 全绿含全部既有装配路径）；消费面 test_pg_api_diff（pg_db 包装+API 级 dry_run diff 归一断言+方向性对照+幂等二跑） |
| **m2-4 followups** 三项 | ✅ | P3-11 固化用例（org 解析失败 400→零忽略事件）；gate 正则 `\[pg[^]]*\]`（独立复算 575 一致）；auth_05 `_call` 无 settings 残留形参 |
| **A5** RUNBOOK 位置申报 | ✅ | 申报 §4「审计月库」节与 RUNBOOK L129-133 实际小节吻合；代码侧 B5 注记已落 backend.py 协议 docstring（L678-681）；docs 落笔归监督侧（符合分工） |

**B① playwright DOM 三断言（独立复现，非采信 coder）**：
1. **既有值徽标**：u_full 的 CN chip = `chip on has-exp`、title=`库内既有到期: 2027-06-30 12:00:00`、data-expires 正确；OS chip 无徽标
2. **选中预填**：取消重选后（输入框原空）`#gExpires` 预填 `2027-06-30 12:00:00`、fresh 入集
3. **langchange 保留**：切 EN 后 chip 仍 `on has-exp`、用户输入 `2028-01-01 00:00:00` 与 picked/fresh 全保留

## 三、择型申报 11 条逐条结论

| # | 申报 | 结论 | 关键证据 |
|---|---|---|---|
| ① | 切标签载体=进程内对象图 | **ACCEPT** | apply_model+ingest/quality.apply_settings+services.settings 四点同批（rebuild.py:72-93），零 SQL 证实；inline 装配同实例共享核实（app.py:289-302）；subprocess 申报诚实——主进程=运维 env 重启，重启窗口向量路暂空 BM25 可用（RUNBOOK 注意事项归 docs 批）；切换后检索/摄取确用新标签（三源断言+reindex 钉当前标签） |
| ② | 迁移外呼 with_model 专用实例 | **ACCEPT** | 新实例请求模型指向新名、原实例 settings 不动（embedder.py:92-98）——旧标签持续服务零降级结构保证 |
| ③ | 扫描谓词含 pending 版本块 | **ACCEPT** | join 仅 doc_id 不限 version=对 TC「在用块」的防漏超集；覆盖率判定仍限在用块（TC 口径不破）；pending 补嵌防切换终态永久缺向量（专项测试实证）。建议 committer 裁定 TC-EMB-06 扫描谓词句措辞回写（非决策） |
| ④ | re-pin 竞态防护 | **ACCEPT** | 顺序写满→切换→re-pin→补扫→清理；切换→re-pin 微窗同任务内即刻收口，repin 后迟到写被谓词挡、清理兜底删非 keep 行——孤儿行结构上不可能残留；注入实证 |
| ⑤ | quality 联动=invalidate+recompute | **ACCEPT** | 缓存键模型维失效（detected_at_scale=NULL→全量重算候选）；recompute best-effort 沿先例；阈值重标定=运维配置动作（M1-5 校准路径）——与实现一致 |
| ⑥ | A3 端点形态四件 | **ACCEPT** | POST 201/用户不存在 404（D16 不建账号）；PATCH model_fields_set 键显式出现含 null=改永久（Ellipsis 哨兵=不变，store 协议）；DELETE 204 级联清授权（既有触发器承载+跨组织不受影响断言）；唯一 admin 自锁守卫=合理增补不越权（三方向 409+双 admin 放行）；均 org_admin 门控+org_scoped 路径校验 |
| ⑦ | A4 enable 幂等零新审计/dry_run 400 | **ACCEPT** | `UPDATE...WHERE status='disabled'`+rowcount 才写审计（双方言同构）；断言再 enable 零新审计；enable 恢复路径无破坏面故不设 dry_run——语义合理 |
| ⑧ | A2 幂等重置+窗口暂不可搜 | **ACCEPT（申报可接受）** | delete_by_doc+回 parsing 强制重切分；窗口不可搜为全量重切固有代价，TC 验收无可用性 SLA；取消后续投可续（幂等重置天然支持） |
| ⑨ | claim/list_tasks 次级键 rowid/seq | **ACCEPT** | 双方言同改+semantic_retag 尾部优先级保留（m2s-5 语义零回归）；双后端测试+注入实证 |
| ⑩ | create_app backend= 注入 | **ACCEPT** | 可选注入、缺省路径零破坏；API 级 pg diff 永久用例落地（m2-3 登记收口） |
| ⑪ | kick 去 _wake.set() | **ACCEPT** | -O 暴露的兜底线程与 kick 竞争认领竞态根除；双通道语义更正：kick=同步消化、wake=仅唤醒（maintenance 调度器路径不受影响）；兜底循环 reindex/reembed 即时认领保留（app.py:156）；m2-3 投递面测试改有界轮询终态=鲁棒收口 |

**分层纪律**：rebuild.py 位于 worker/（非 core）只经 backend 协议；新 store 方法双方言逐语句等价；审计入 outbox 均在 BEGIN..COMMIT 同事务内（A3/A4 全部写路径）——无违规。**越权面**：members/values 全部 org_admin 门控（403 显式断言）+org_scoped 路径校验（跨组织 403 由框架守卫承载，沿 m2-3/m2-4 既有覆盖）。

## 四、注入验证（2 组，恢复→红→恢复→绿）

| # | 注入 | 红证据 | 恢复 |
|---|---|---|---|
| ① | 摘除 write_embeddings 回写防护谓词（sqlite 去 `AND c.embed_model = :label`） | `test_tc_emb06_bluegreen_full_cycle[sqlite-sqlite]` **FAILED**——tests/test_wk_rebuild.py:158 `assert 1 == 0`（孤儿行防护精确触发） | 恢复后 [sqlite-sqlite]/[pg-pg] 2 passed；`git diff` 0 行 |
| ② | claim 单调键回退（sqlite ORDER BY rowid→id） | `test_claim_order_monotonic_within_same_second[sqlite]` **FAILED**——tests/test_wk_rebuild.py:386 `'tsk_a' != 'tsk_c'`（uuid4 字典序≠插入序） | 恢复后 [sqlite]/[pg] 2 passed；`git diff` 0 行 |

业务代码零残留（备份/恢复经 /var/folders 临时目录，两次注入后 git diff 均为空）。

## 五、临时产物清理确认

- **pg**：本次会话零新增 schema（per-test fixture 自清，双轮门禁+注入单测后核查）；存量 `pg_temp_3` 为标准会话临时命名空间
- **临时目录**：m26_inject（注入备份）、m26_ui（UI 验证库/uvicorn 日志/serve 脚本）全删
- **进程**：验证用 uvicorn 已停、playwright 自动化 Chrome（PID 44210，带自动化 flags 的独立实例，非用户浏览器）已终止
- **工作区终态**：与验证前一致——仅监督侧 4 文件（`.opencode/workflows/_m2-plan.md`、`task-knowledge-lattice-m2-4.md` 修改、`docs/TEST-CASES.md` 修改、`task-knowledge-lattice-m2-6.md` 未跟踪），业务代码 git diff 为零；HEAD 未动

## 六、问题清单

**P1：无。P2：无。**

**P3：**
- **P3-1（申报精度，IMPL_BUG 轻）**：B① 子项「**逐行过期编辑**」（m2-3 检查点 L90 权威清单原文）未逐字实现——saveGrants 保存时 fresh 集共用当前输入框值（app.js:273-276，同一保存内多行不能各带不同 expires），coder 申报「B①~⑩ 全核销」但该子项既未实现核销也未显式登记去向。缓解面：预填+既有值徽标+未动行沿用已大幅收敛原始 UX 问题。**建议**：R2 补实现或由监督侧/committer 裁定登记去向（不改验收用例本体——B 项清单为 Committer P3 记录级建议）。
- **P3-2（观察）**：pg 存量 7 个 bench/eval 残留 schema（`lattice_eval_*`×5、`lattice_bench_g6hv_*`×2，来自 scripts/eval_baseline.py 与 benchmarks/ 的历史会话）在本次验证开始前已存在——非本任务产物未处置，建议监督侧择机清理或登记。
- **P3-3（观察，可选 docs）**：择型⑧ 重索引窗口不可搜——申报已诚实声明；RUNBOOK 运维注记可随 docs 批顺带（可选项）。

**观察项（不计问题）**：择型③ pending 超集措辞建议随 docs 批回写 TC-EMB-06（非决策变更）；m2-4 followups 余两项（_outbox_insert 掩码/MCP 审计顺序）按任务书「不强求」边界维持登记去向「下批/m2-5」；双模式 167/168 warnings 为 JWT 测试密钥长度与 docling/pydantic deprecation 类既有告警，非本段引入。

## 七、结论

```
testVerdict: PASS
testedSha:   f9794054973e376c573e877185a849aad7c1eee8
```

门禁 1637+1 双后端双模式 0 skipped 独立复跑成立（+57 逐文件对账闭合、零删除零弱化）；TC-EMB-06 四步双后端全绿+A2 端到端+A3 members/JIT 闭环/T23 回归+A4 D19 解锁联动全过；B①~⑩ 核销（B① 含一个 P3 级子项申报精度问题）；m2-4 followups 三项清偿；择型 11 条全部 ACCEPT（③⑧附回写/注记建议）；注入验证 2 组红/绿实证测试有效性；临时产物零残留。P3-1 交监督侧裁量（不构成打回事由），P3-2/P3-3 为观察项。

</details>

<details>
<summary>R1 Committer 报告全文（ses_e69aa3034ffeswmU0kfrWYy0rF，2026-11-01，reviewVerdict=NEEDS_CHANGES）</summary>

# task-knowledge-lattice-m2-6 R1 Committer 审查报告（只读）

## 0. 审查基线、方法与总体结论

- **审查对象**：`git diff c2ebb68..f979405`（36 files，+2930/−220）；HEAD = `f9794054973e376c573e877185a849aad7c1eee8`（= f979405，develop_opencode）。R1 为首轮，检查点无上一 reviewedSha，基线取 m2-4 mergeCommit `c2ebb68`。
- **基线核对**：`filesChanged` 36 项与实际 diff 一致；本 commit 对 `docs/`、`.opencode/`、`AGENTS.md`、`RUNBOOK.md`、`prototype/` 零改动；工作区只有监督侧 4 文件，与 coder 申报一致。
- **审查方式**：只读审查，零文件修改、零 git 写、未执行 `gh pr review`。未独立复跑门禁；门禁结论采信 Tester 独立复跑证据（GATE PASS 1637+1 双后端双模式 0 skipped），并对其计数/对账做一致性核验：+57 逐文件算术自洽；tests diff 无新增任务范围 skip、无删 def test_/parametrize、无断言弱化。

**审查结论：`reviewVerdict = NEEDS_CHANGES`**
- **P1：无**
- **P2 ×2**（阻断）：P2-1（A1 ④ semantic_build 强制重跑未真正成立）、P2-2（全局切换 vs 组织级覆盖/清理，多组织下违反 TC-EMB-06 ④ 且权限面过宽）
- **P3 ×8**（记录级，不单独阻断）
- **需求边界问题 N-1 一项**（reembed 组织级/全库语义与权限，需监督侧/用户裁定）
- `testedSha` = `f9794054973e376c573e877185a849aad7c1eee8`（与 HEAD 一致）；`reviewedSha = null`（未通过，R2 修复后重审）

## 1. 问题清单

### P2-1（阻断）A1 ④：`semantic_build` 强制重跑实际不成立——执行体用旧 Settings，dict_rev 无新标签

- **位置**：`worker/runner.py:272-282`（`_exec_semantic_build` 以 `self._settings` 调用 `run_build_task`）；`worker/rebuild.py:72-93`（`switch_embed_label` 只替换 `services.settings`，不改 `TaskRunner._settings`）；`core/semantic/build.py:334-340`（dict_rev 按传入 settings 的 `embed_model_label` 计算，与 current 相同即 `skipped`）；`tests/test_wk_rebuild.py:161-168`（只断言 tasks 表存在 semantic_build 任务行，从未执行该任务）。
- **问题**：reembed 完成后投递的 `semantic_build` 由 `TaskRunner` 执行时仍使用 runner 构造期的旧 Settings；`switch_embed_label` 声称替换 `services.settings` 是「semantic_build 的 dict_rev 标签源」，但 executor 并不读该字段。结果：① dict_rev 仍按旧标签计算 → 与 current 相同 → `run_build` 走 skipped，A1 ④ 直接不成立（design §5.8 的「换模型 → 相同则跳过失效」未实现）；② inline 的 `ServiceContext.settings`/MCP `settings` 仍是旧标签，而共享 embedder 已切新模型——semantic vec 查询将用新模型 query 向量查旧标签旧模型行（跨底模距离），`api/semantic.py:425-431`、`mcp/server.py:557-558`；覆盖率面板 `dim` 仍为旧值（`api/admin.py:590`）；app 周期指纹探针用新 embedder + 旧 `settings.embed_dim`（`adapters/embedder.py:164`）会在 dim 变更后每次抛维度异常、门禁状态不再更新。
- **修法建议**：`_exec_semantic_build` / `_exec_semantic_sync` / `_exec_semantic_retag` 改读 `self._services.settings`（switch 已替换），或引入可变 SettingsHolder；subprocess 与 inline 两形态同修。inline 形态同时把 `ServiceContext.settings`/MCP 闭包 settings 更新为切换后对象（或统一从 embedder 的 `model_label` 派生 label 与 dim）。补用例：reembed 后实际执行 semantic_build 任务 → 断言 `status != "skipped"`、新 build 的 `dict_rev` 含新 `embed_model`、`sem_fuzzy_terms`/`sem_vec` 行标签为新标签；inline 下断言 coverage `embed_dim`、semantic vec 查询标签、周期探针与 embedder 一致。双后端均覆盖。

### P2-2（阻断）A1 ②/④：组织级覆盖/清理 + 全局 config 切换——多组织下违反「全库单标签一致」，且权限面过宽

- **位置**：`worker/rebuild.py:118/157-159/213/218/221`（payload 取 org，扫描/复钉/清理/失效全 org 过滤）；`store/sqlite/backend.py:2499-2550`、`store/postgres/backend.py:3770-3845`；`worker/rebuild.py:72-93`（切换进程全局标签）；`api/admin.py:501-527`（reembed 入口 `_require_owner_or_admin`——普通文档 owner 即可触发，payload 固定 `{org, embed_model}`）、`:541-594`（覆盖率面板按 org）。对照冻结口径：`docs/design.md:794`（全库扫描+全库完成+原子切标签+旧标签清理）、`docs/TEST-CASES.md:220-224`（TC-EMB-06 ④「全库单标签一致」）。
- **问题**：实现只保证 payload.org 一个组织的覆盖率 100%，随后即切换全局 config 标签并删除该组织旧标签。多组织部署下：① 其余组织的检索谓词立即变成新标签，但库内只有旧标签向量 → 向量路失效（BM25 兜底）、旧标签行残留，TC-EMB-06 ④ 不成立；② subprocess 形态下运维按 selection ① 改 env 重启后，其余组织同样无新标签向量；③ 任一文档 owner（非 org_admin）即可触发 org 级扫描+进程全局标签切换，超出 FR-4「重索引=owner/org_admin」原意（原意是单文档重索引，不含换模型全局 config 变更）。
- **修法建议**：按冻结口径改为全库扫描/全库覆盖率门/全库清理（store 方法支持 org_id=None 或遍历组织；切换前确保所有组织在用块新标签覆盖率 100%），并补多组织双后端用例（org A/B：在 A 投递 reembed 后断言 B 的向量与标签也完成迁移、全库仅单标签；未达成前不得切换）。若监督侧/用户确认是按组织迁移语义（见 N-1），则切换必须拆成独立的全局阶段（或系统管理员动作），禁止单组织任务内改全局标签；同时把 reembed 分支权限从 owner/org_admin 收到 org_admin（全局则 sysadmin），并补权限测试。

### P3-1（Tester P3-1）B① 申报精度：「逐行过期编辑」未实现且未登记去向
- **位置**：`web/app.js:268-278`；m2-3 检查点 L90 权威清单；任务书 B①。
- **处置（本 Committer 裁定）**：接受为「登记去向」，不要求 R2 实现。需在检查点 R1 coder 条目与 `_m2-plan` 挂账中把「B①~⑩全核销」改注为「B① 3/4 子项核销 + 逐行过期编辑登记去向（m2-5/TC-UI 手动走查批）」。若 R2 顺手实现每行独立输入，也可接受，不作为打回条件。

### P3-2 B⑥ 只做了一半 + 残留死常量/过强 docstring
- **位置**：`store/taskclock.py:7-9` docstring vs `store/postgres/backend.py:1759、3167、3250、3526、3764` 仍为字面量；`api/admin.py:57、298-299` 的 `_EXPIRES_LIB_FORMAT = TS_FMT` 已是无引用死常量。
- **修法**：R2 顺手把 store 侧 5 处 strftime 改为引用 `TS_FMT`，删除死常量与无用 import，修正 docstring；或至少登记为残余。非阻断。

### P3-3 唯一 admin 自锁守卫：pg datetime 比较 500 + 守卫与写操作非原子（TOCTOU）
- **位置**：`api/admin.py:684-705`（`:693` 取 `membership["expires_at"]`、`:698` 与 `utc_now_ts()` 字符串比较）；`store/postgres/backend.py:55-76`（read_membership 把 TIMESTAMP 原样返回为 datetime）。
- **问题**：① pg 500：目标为带 expires 的 org_admin 时，`PATCH {"role":"org_admin"}`（幂等）或空 PATCH 会走 `after_expires > utc_now_ts()`——`datetime > str` → TypeError → 500。sqlite 为字符串比较，故现有 REST 用例（仅 sqlite）全绿、pg 未覆盖。② TOCTOU：read_membership/count_active_org_admins 与随后的 update/delete 不在同一事务；双 admin 并发降级都可能看到 count=2，最终 0 admin。窄面。
- **修法**：守卫内先把 `expires_at` 归一为库格式字符串，或 store 侧 to_char 输出；守卫与写操作放进同一 store 事务（或锁定读），补 pg+并发用例。P3。

### P3-4 A4 细节：`label` 被忽略 / retired 维度 enable 未拒 / 幂等 enable 仍返回 applied=True
- **位置**：`api/admin.py:812-849`（label 接收但不传给 store）；`store/sqlite/backend.py:2405-2480`、`store/postgres/backend.py:3667-3745`（create 固定 label=value；enable 未检查维度 retired，applied 恒 True）；`tests/test_admin_values.py:1-10` docstring 与实现不符。
- **修法**：store 增加 label 参数或 API 明确「label 暂不支持」；enable 对 retired 维度 409（或 docs 明确无害并改 docstring）；applied 按 rowcount 返回；补测试。P3。

### P3-5 reindex 取消/并发 pending：重置先于存活检查，文档可能停在 parsing 且在用块已被删
- **位置**：`worker/rebuild.py:298-303`（在 alive/任务终态检查之前 delete_by_doc + set_doc_active_status(parsing)）；`core/docs/ingest.py:703-719/455-489/615-637`。
- **问题**：① 任务 claim 后、executor 开始前被取消：run_reindex_task 已删在用块并置 parsing，随后 ingest.run_task 因 cancelled 终态直接返回——文档不可搜且无任务重试；② 文档存在 pending 覆盖上传时触发 reindex：target=active_version，reset 后 _guard_alive 判 cancelled → active 块已删、状态 parsing；若 pending 上传失败/取消，文档长期不可搜。
- **修法**：reset 前检查任务终态与 should_continue；`doc.pending_version is not None` 时对 active 目标拒绝（409/400）或改投 pending 版本；补「reindex 期间取消」「pending 期间 reindex」双后端用例。P3（可恢复，但影响用户可见性）。

### P3-6 测试质量/可复跑性（合并记录）
1. `tests/test_admin_manage.py:200-252、294-305`：直插 pending 任务构造「未执行窗口」，但 inline 兜底循环对 reindex/reembed 每个 poll 即时认领（默认 5s）——负载下 flake 风险，建议隔离 inline worker。
2. `tests/test_wk_rebuild.py:109、272`：`rebuild_env`/`reindex_env` 的 params 未使用 request.param，与 matrix 相乘重复跑一倍（34→18 收集可省）。
3. `tests/test_admin_store_reads.py:184-235`：cycle 的 .code 从未断言、orphan_rows 被宽松放过——补断言或收窄 docstring。
4. 注释/编号陈旧：test_pg_scaff.py:506-520 docstring「0011/12<=13」（实际 0012/0013）；test_v11_schema.py:89-92「0002~0008」（已到 0010）；test_admin_values.py docstring；test_admin_store_reads.py:165-183 顺序未断言。
- **处置**：非阻断，R2 顺手修或登记测试卫生批。

### P3-7（Tester P3-2）pg 存量 7 个 bench/eval 残留 schema——观察项，不归 coder；监督侧核对后 DROP SCHEMA ... CASCADE 清理或登记。

### P3-8（Tester P3-3）RUNBOOK 运维注记——归 docs 批（RUNBOOK §1/§4）。

## 2. 需求边界问题

**有（N-1，1 项）**——不计入代码 P 级，交监督侧/用户裁定：

- **N-1 reembed 的组织口径与触发权限**：冻结文档 `design §5.3`（L794）与 `TC-EMB-06`（L224）明确「全库扫描/覆盖率 100%/全库单标签一致」；m2-3 已交付入口 `POST /api/orgs/{org}/documents/{doc_id}/reindex?embed_model=...`，payload `{org, embed_model}`，权限 `owner/org_admin`；任务书 A1 未明确组织范围与权限；实现选择了「org 级覆盖/清理 + 全局切换」。**需裁定**：(a) 全库迁移（与 design/TC 一致；触发应为 org_admin 或 sysadmin，且需全组织覆盖率门）；或 (b) 按组织迁移（则必须修改 design/TC/RUNBOOK 口径，且全局 config 切换不能发生在单组织任务内，需独立全局阶段/系统管理员动作）。无论裁定结果，P2-2 的「单组织覆盖即切全局标签」不成立；若选 (b)，docs 批需同步回写。此项不计入 coder 本轮 P 级，但 P2-2 的修复方向依赖此裁定。

## 3. A1~A5 + B 项逐项审查（摘要）

| 项 | 判定 | 要点 |
|---|---|---|
| A1 ① | ✅（附注） | 并行写入/零降级结构保证成立；扫描含 pending 为防漏超集 |
| A1 ② | ❌（P2-2/P2-1） | 覆盖率/切换语义按 org；runner/ServiceContext 未切；「零 SQL」本身成立 |
| A1 ③ | ✅ | re-pin+谓词防护；注入红绿实证 |
| A1 ④ | ❌（P2-2/P2-1） | 清理按 org；semantic_build 仅投递被断言、执行体用旧 settings → skipped |
| A2 | ✅（附 P3-5） | 幂等重置+全链；端到端/中断重认领通过 |
| A3 | ✅（附 P3-3） | 端点+门控+审计+T23+守卫+JIT 全链；pg datetime/TOCTOU 见 P3-3 |
| A4 | ✅（附 P3-4） | D19 解锁联动正确；细节见 P3-4 |
| A5 | ✅（代码侧） | B5 注记已落 backend.py；RUNBOOK 落笔归监督侧 |
| B① | ⚠️（P3-1） | 3/4 子项；逐行过期编辑登记去向 |
| B②③④⑤⑦⑧⑨⑩ | ✅ | 逐项核销成立（B⑤测试断言不足见 P3-6、B⑥见 P3-2） |
| B⑥ | ⚠️（P3-2） | api 侧已接 TS_FMT；store 侧未收编 |
| m2-4 followups | ✅ | 三项清偿；余两项维持登记 |
| 门禁 | ✅（采信 Tester） | 1637+1 双后端双模式 0 skipped；无 skip/删除/弱化 |

## 4. 择型申报 11 条逐条裁定

① **ACCEPT（附条件）**——载体方向正确、subprocess 申报诚实；但 services.settings 未接上 runner（P2-1）、inline ServiceContext/MCP 未随切（同根因），必须修后完全成立。②~⑪ **全 ACCEPT**（③附 docs 批措辞回写建议、⑧附 RUNBOOK 注记、⑨semantic_retag 尾序保留实证）。

## 5. 安全性深审

members/values 写路径越权面 ✅（org_scoped+org_admin 门控、store org 过滤、角色白名单 API 收口）；DELETE 级联授权 ✅（既有触发器按 org、他组织不受影响）；审计同事务 ✅（member 事件入 _target_of 映射）；JIT 链路不破 ✅；SQL 参数化 ✅（新增 store 方法全参数化、embed_model fail-closed、expires 统一严格解析）；P2-2 权限面=唯一新暴露面（文档 owner 可触发全局 config 变更），必须随 P2-2/N-1 收口。未发现 P1 级安全缺陷。

## 6. 测试质量与门禁审查

达到验收覆盖（A1 除 semantic_build 执行面/A2/A3/A4/B 主体均有双后端用例；TDD+注入证据充分）；关键缺失：semantic_build 未执行（P2-1）、reembed 全单组织用例（P2-2）、守卫无 pg 用例（P3-3）、cycle/orphan .code 未断言（P3-6）、inline 直插用例时序竞争（P3-6）。TC-UI manual 政策符合；test_pg_api_diff skipif=DSN 未设置既有约定，门禁下 0 skipped。

## 7. Tester P3×3 处置裁定

| Tester 项 | 裁定 | 去向 |
|---|---|---|
| P3-1 B①逐行过期编辑 | 接受+登记去向 | 检查点/_m2-plan 改注「B① 3/4+逐行过期编辑→m2-5/TC-UI 手动走查批」；R2 顺手亦可 |
| P3-2 pg 残留 schema | 观察项不归代码 | 监督侧核对后 DROP CASCADE；检查点/运维记录登记 |
| P3-3 RUNBOOK 注记 | 归 docs 批 | RUNBOOK §1/§4（与 A5 同批） |

## 8. docs 批建议清单（监督侧落笔）

1. **TEST-CASES v1.9.12（非决策）**：版本行 m2-6 段交付；§六 M2 行 m2-6 完成态（TC-EMB-06 执行体四步〔修复后含②④全库口径〕、A2、A3 members/JIT/T23、A4 D19、新增端点形态）；TC-EMB-06① 扫描谓词注记（含 pending 超集）；④ 按 N-1 裁定回写全库口径+P2-1 修复后补 semantic_build 实际执行；TC-OPS-07 values create/enable；TC-TASK-03 reindex 取消/pending（若 P3-5 修复）。
2. **known-gaps**：按 N-1 裁定决定是否新增条目；若 P2-1 只修 worker、inline API 侧残余，登记「inline 进程内切标签的 ServiceContext/探针 dim 最终一致性」（G-27 候选）。pg 残留不进产品 gaps。
3. **design v0.9.8（非决策）**：§5.3 实现口径（reembed 四步/切换载体/全库或组织范围与权限〔按 N-1〕/旧标签清理时点与回退窗口）；§5.6/§6.2 端点表（members 三端点+values 两端点+审计事件）；§5.8 semantic_build dict_rev 标签源与强制重跑口径。
4. **RUNBOOK**：§1 蓝绿操作序列（投递/等待/覆盖率门/切 env/重启/VACUUM）+subprocess 重启窗口+inline 限制+回退窗口关闭+阈值重标定+任务完成≠主进程已切换；§1/§4 重索引窗口与取消/pending 注意；§4 审计节 B5 注记（A5）；可选 pg 残留清理步骤。
5. **AGENTS.md**：§1 状态行（m2-6 交付、下一段 m2-5、门禁 1637+1）。
6. **_m2-plan**：row 7.5 done、§二要点、§三挂账（B① 子项去向、B⑥ 残余、m2-4 followups 余两项、N-1 裁定结果）、基线 1637+1。
7. **检查点**：R1 coder 条目措辞修正（B①/B⑥）、Tester P3×3 处置、Committer 报告、终态回写。
8. 工作区已有 docs 批由监督侧随交付 chore 入库。

**遗留事项去向建议**：B①逐行过期编辑→m2-5/TC-UI 批；B⑥ store 字面量→R2 顺手或下批卫生批；m2-4 followups 余两项→维持「下批/m2-5 测试补强批」；Tester P3-2→监督侧运维清理；P3-3→RUNBOOK docs 批。

## 9. 交付把关建议

本轮不放行交付（P2×2 未闭合）。R2 最小修复集：P2-1+P2-2（按 N-1 裁定）+P3 应修尽修（P3-2/3/4/5 建议；P3-1/6/7/8 按记录/登记处置）。R2 后重审：Tester 在 R2 HEAD 独立复跑门禁；Committer 按 f979405..新 HEAD 逐条核 P2/P3 处置与回归；APPROVED 后进入交付：用户确认→双 SHA 一致→manifest 完整→检查点终态+docs 批+chore 归档→gh pr review 留痕（不执行合并）。

## 10. CASE_BUG 裁定：本轮未收到裁定请求，无输出。

## 11. 结论

```
reviewVerdict: NEEDS_CHANGES
testedSha:     f9794054973e376c573e877185a849aad7c1eee8（= HEAD，Tester PASS 一致）
reviewedSha:   null（未通过；R2 修复后重审）
P1: 0 | P2: 2（P2-1、P2-2） | P3: 8 | 需求边界: N-1 ×1 | CASE_BUG: 无
```

核心判定：A1 ②④ 的「原子切标签 + semantic_build 强制重跑 + 全库单标签一致」在当前实现下未真正成立（P2-1/P2-2）；A2/A3/A4/A5 与 B 项主体、门禁证据、安全门控与审计同事务均通过，剩余为 P3/登记级问题。修复 P2 后重审。

</details>

<details>
<summary>R2 Tester 报告全文（ses_e69ca7427ffe909TXr7yUZvXIO 续接，2026-11-01，testVerdict=PASS）</summary>

# task-knowledge-lattice-m2-6 R2 修复轮独立验证报告

**testVerdict: PASS**
**testedSha: `bd9598f1614c1e40a22e5d2e09005a885a060174`**（= bd9598f，develop_opencode HEAD，全 40 位复核一致；父提交=f979405=R1 PASS SHA）
验证时间：2026-11-01；续接 R1 Tester 会话独立执行，未采信 coder 自测结论。

## 一、门禁独立复跑（双后端双模式）

```
docker start lattice-pg; export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
scripts/test_gate.sh
→ GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
  （pg 臂 611 条用例全实跑：[pg] 参数化 577 + PG 专用 34）
```

| 模式 | 结果 | 时长 |
|---|---|---|
| 常规 | **1642 passed, 1 deselected, 0 skipped** | 184.78s |
| python -O | **1642 passed, 1 deselected, 0 skipped** | 184.49s |
| pg 臂收集（独立复算） | **611 = 577 + 34** | — |

- **+5 净增对账（独立核对闭合）**：members 11→**13**（+2=`test_last_admin_guard_store_level` matrix×2）+ values 8→**14**（+6=3 个 P3-4 store 级用例×2）+ manage **+1**（新增 `test_api_reindex_rejected_while_pending`，P3-5②）+ wk_rebuild 34→**30**（params 收编去重 −4）= +5 ✓
- **去重 −4 非删用例（核实）**：删除的是两个 fixture 的 `@pytest.fixture(params=["sqlite","pg"])` 未使用参数化行（`rebuild_env`/`reindex_env`——与 matrix 相乘重复跑一倍）；**def test 零减少反而 9→15 增加**；被删断言行均为升级替换（`==202`→`==202, r.text`、orphan 断言 `in (multi_heads, orphan_rows)`→收窄 `== multi_heads` 改强、semantic_build 投递断言升级为实际执行断言）；manage 的 2 个「删除函数名」为 fixture 换名 `_mgmt_env`→`_mgmt_env_quiet`（函数保留）✓
- skip 核对：双模式 0 skipped；1 deselected=TC-UI manual（政策性排除）✓

## 二、R1 Committer 意见修复闭环逐条判定

| 项 | 判定 | 证据摘要 |
|---|---|---|
| **P2-1** semantic_build 强制重跑 | ✅（附 P3-2 残余，见问题清单） | `config.effective_settings(base, embedder)`（config.py:187-208，标签/维度从 model_label 派生、None/畸形回退 base）；runner 4 executors 全改派生（maintenance 也改读 services.settings）；api/semantic.py 4 处 + mcp/server.py 3 处闭包消费点改派生；FingerprintProbe 维度从 label 派生（embedder.py:165-168）；coverage dim 派生（admin.py:614）。**reembed 后实际执行用例**（`test_reembed_then_semantic_build_executed` 双后端）：真执行 status=done 非 skipped、`dict_rev != 首次`、`dict_rev_components.embed_model=新标签`、`sem_fuzzy_terms` 行标签⊆新标签——**注入实证**（见 §五①）红/绿证明判别力；probe dim 跟随用例（`test_fingerprint_probe_dim_follows_embedder`：8→16 维切换后探针不再抛维度异常、基线按新标签建档） |
| **P2-2** N-1 全库迁移+sysadmin 专属 | ✅ | store 5 方法双方言 `org_id=None` 动态过滤（sqlite/pg `org_filter` 逐语句等价）+ `list_org_ids` + 协议 docstring 契约声明（backend.py:651-681）；执行体全库扫描/全库覆盖率门（`embedding_coverage(None)` 全库求和）/全库 repin/清理/失效+逐组织 quality recompute 与 semantic_build 投递（rebuild.py:150-265）；**多组织双后端用例**（`test_reembed_full_library_multi_org`：org:gl 造独立文档+块+旧标签向量→投递 org:tax 后 org:gl 块同迁、全库 stray=0 单标签一致、build 逐组织投递）；API 权限三态（owner 403/org_admin 403/sysadmin 202 且 inline 同步执行到 done——manage 用例）；reembed 分支用 `check_path_org` 免 org_scoped（sysadmin 系统级动作免本组织成员关系）✓；单文档 reindex 维持 owner/org_admin+org_scoped ✓ |
| **P3-3** 守卫下沉 store 事务化 | ✅ | sqlite `BEGIN IMMEDIATE` 内守卫+count（单写者串行化等效）；pg `SELECT...FOR UPDATE` 行锁+`expires_at > CURRENT_TIMESTAMP` 全 SQL 侧比较（datetime 不出库——500 根除）+同事务 `_count_active_admins`（TOCTOU 根除）；`MembershipLastAdminError` 新异常+API 只做 409 映射（`_last_admin_guard` API 层删除）；**store 级双后端用例**（带 FUTURE_TS expires 的 admin 降级/停用/删除三向 raise+双 admin 放行+过期 admin PAST_TS 不受守卫——pg datetime 路径覆盖） |
| **P3-4** A4 细节 | ✅（附 P3-1 缺口） | label 显式传递（store +label 参数缺省=value，API 传递 `body.label`；store 级用例断言落库「展示名」+缺省=value）；applied 按 rowcount（幂等 enable `applied=False` 用例）；retired enable 409——**store 层成立**（ValueError+用例×2 双后端），**REST 面缺口见问题清单 P3-1** |
| **P3-5** reindex 三重前置 | ✅ | ①取消终态不重置（rebuild.py:297-302，`test_reindex_cancelled_before_reset`：文档保持 searchable_full、在用块保留）；②重置前存活检查（:340-344）；③pending 在途 fail-closed（:323-338 执行体 failed 带原因 + API 409 admin.py 投递面）——`test_reindex_rejected_while_pending_version` + `test_api_reindex_rejected_while_pending` 双防线用例 |
| **P3-2** B⑥ 收尾 | ✅ | pg 5 处 strftime 全部收编 TS_FMT（pg backend 11 处 TS_FMT 引用：1759/3167/3250/3526/3764 原位全改）；`_EXPIRES_LIB_FORMAT` 死常量删除（admin.py diff 证实）；taskclock docstring 修正为如实表述 |
| **P3-6** 测试质量四小项 | ✅ | ①`_quiet_inline` fixture（停兜底循环线程——只用于直插窗口用例，kick 通道不受影响）；②params 收编去重（−4 已核）；③orphan 锁死 `multi_heads` 实际路径（断言改强）+ cycle/orphan_rows 可达性 docstring 诚实收窄（hash 自洽约束下不可静态构造——不伪造断言）+ read_org_audit 排序断言（`sorted(reverse=True)`）；④docstring 编号修正×3（pg_scaff 0010/0011、v11_schema 0002~0010×2） |
| **P3-1 不修申报** | ✅ 合规 | `src/knowledge_lattice/web/` 在 R2 diff **零改动**（git diff --stat=0 行）——按 Committer 裁定登记 m2-5/TC-UI 批，零改动即合规；检查点 R2 条目已登记去向 |

## 三、R2 择型申报 7 条逐条结论

| # | 申报 | 结论 | 关键证据 |
|---|---|---|---|
| ① | 统一从 embedder.model_label 派生（effective_settings）；ServiceContext.settings 保留旧对象=可接受滞后 | **ACCEPT（附残余登记 P3-2）** | **穷尽核阅** `embed_model_label`/`embed_dim` 全部消费点：retrieve.py:257 embedder 优先 ✓；ingest/quality 经 apply_settings 对象替换（switch 同批）✓；semantic build/annotator/lookup 经 executor effective（runner 4 处）+api/semantic 4 处+mcp 3 处 effective ✓；probe label 派生 ✓；coverage dim effective ✓。剩余 `service.settings` 消费点逐一排除：resolve_source_config/webhook secret/dev token/upload 凭证/describe_table 均非 embed 字段；`run_search(settings)` 内 vec_label embedder 优先、`_embed_query` 仅用 timeout 非维度字段 ✓。**例外**：api/search.py:72 `resolve_query_entities` 未派生（MCP 同函数已派生）——见问题清单 P3-2，方案本身成立、覆盖面申报不完全 |
| ② | store 单方法双口径（org_id=None 动态过滤）+逐组织联动+payload.org 保留 | **ACCEPT** | 双方言 5 方法 org_filter 逐语句等价+注入②判别实证（回退恒过滤→多组织用例红：覆盖率门不收敛）；payload.org 保留作投递上下文合理（sysadmin 触发点记录） |
| ③ | 守卫整体下沉 store 事务化 | **ACCEPT** | sqlite BEGIN IMMEDIATE 单写者串行化 / pg FOR UPDATE+SQL 侧比较+同事务 count——500 与 TOCTOU 双根除；API 只留 409 映射；pg datetime 路径双后端用例 |
| ④ | label 加参显式传递 | **ACCEPT（retired 409 部分成立）** | label 传递+缺省=value 断言落库 ✓；applied rowcount ✓；retired enable 的 REST 映射缺失见问题清单 P3-1（store 级成立） |
| ⑤ | 投递面 409+执行体 fail-closed 双防线 | **ACCEPT** | API 409（manage 新用例）+执行体三重前置（取消不重置/存活检查/pending 拒绝）各具判别用例——单防线失效另一道仍守 |
| ⑥ | 停兜底循环线程 fixture（比独立 app 轻） | **ACCEPT** | `_quiet_inline` 只 set `_stop/_wake`（测试侧隔离）；kick 同步消化通道不受影响——R1 择型⑪语义保留实证（`_mgmt_env` 投递用例仍断言同步执行到终态） |
| ⑦ | orphan 锁死实际路径+cycle/orphan_rows docstring 收窄不伪造断言 | **ACCEPT** | 断言从宽松元组收窄为 `== "multi_heads"`（改强非放宽）；cycle/orphan_rows 的不可静态构造说明诚实（append 前 hash 自洽约束下 prev 指向批外→必然先构成第二链头被 multi_heads 拦）——符合「无虚假绿」纪律 |

## 四、回归面结论

- **R1 的 57 条新用例全在且绿**：门禁 1642 全绿覆盖（wk_rebuild def test 9→15 只增；members/values/manage/store_reads/pg_api_diff 全保留）；零删除零弱化机器核验通过（§一）
- **R1 择型 11 条语义不被 R2 破坏**：①切换对象图同构增强（switch_embed_label 未变+semantic 面经派生补齐）；②with_model 专用实例不变（rebuild.py:144-148）；③扫描 pending 超集保留（sqlite:2577 join 不限 version）；④re-pin 顺序保留——**回归注入红/绿复验**（摘除回写防护谓词→full_cycle 红→恢复→双后端绿）；⑤quality 联动同构（invalidate+逐组织 recompute）；⑪kick 语义保留（app.py 零改动——不在 18 files；`_quiet_inline` 仅测试侧）
- **m2-3 投递面适配不被 P3-6① 破坏**：`_quiet_inline` 只用于直插「未执行窗口」用例；投递类用例（`_mgmt_env`）保持 inline 同步执行+有界轮询终态断言（-O 竞态修复语义不变）✓
- **m2s-6 semantic 路径回归**：门禁 1642 全绿含 sem_* 全套；P2-1 的 build 写入/查询同源用例（dict_rev 组件+模糊行标签）双后端通过 ✓

## 五、注入验证（3 组，恢复→红→恢复→绿）

| # | 注入 | 红证据 | 恢复 |
|---|---|---|---|
| ① | semantic_build executor 回退构造期 settings（摘除 effective_settings 派生——runner.py） | `test_reembed_then_semantic_build_executed[sqlite]` **FAILED**——test_wk_rebuild.py:531 `assert 'c8f65971ec27' != 'c8f65971ec27'`（dict_rev 恒等→skipped 复现，P2-1 缺陷形态精确重建） | 恢复后双后端 2 passed；git diff 0 行 |
| ② | store 全库扫描回退（sqlite `pending_reembed_batch` 的 org_id=None 动态过滤改恒 org 过滤） | `test_reembed_full_library_multi_org[sqlite]` **FAILED**——rebuild.py:203 `RuntimeError: reembed 全库覆盖率未收敛`（org_id=None→`d.org_id=NULL` 恒假→扫描空→门永不收敛；P2-2 判别力实证） | 恢复后 multi_org+switch_blocked 双后端 4 passed；git diff 0 行 |
| ③（回归） | R1 择型④同款注入：摘除 write_embeddings 回写防护谓词 | `test_tc_emb06_bluegreen_full_cycle[sqlite]` **FAILED**（孤儿行防护仍有效） | 恢复后双后端 2 passed；git diff 0 行 |

业务代码零残留（备份/恢复经 /var/folders 临时目录，三次注入后 git diff 均为空）。

## 六、临时产物清理确认

- **pg**：非系统 schema 总数 7 = R1 报告过的存量 bench/eval 残留（`lattice_eval_*`×5+`lattice_bench_g6hv_*`×2），**本次会话零新增**（维持 Committer P3-7 裁定：监督侧核对清理，coder/验证侧不动）
- **临时目录**：m26r2_inject 全删；**进程**：无残留（本轮未启服务/浏览器）
- **工作区终态**：与验证前一致——仅监督侧 4 文件，业务代码 git diff 为零；HEAD 未动

## 七、问题清单

**P1：无。P2：无。**

**P3：**
- **P3-1（IMPL_BUG 轻）A4 retired 维度 enable 的 REST 面返回 500 而非 409**：store 层 `enable_dimension_value` 对 retired 维度 raise ValueError（409 语义）+store 级用例成立，但 `api/admin.py` `patch_dimension_value` 的 enable 分支**缺 `except ValueError → 409` 映射**（create 分支 R1 起就有）——REST `PATCH status=active` 在 retired 维度上**实证 500**（本验证 TestClient 复现：retire→disable 200→enable ValueError 500）。且相对 R1 行为（幂等 200）是 REST 面回归。窄面（retire 维度后 disable→enable 的运维序列）。**修复建议**：enable 分支补 `except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc))`（与 create 对称——coder 择型④「409 与 create 对称」申报的最后一公里）。
- **P3-2（IMPL_BUG 轻，P2-1 修复残余）REST search 实体解析路径未派生**：`api/search.py:72` `resolve_query_entities(service.settings)` 未改 `effective_settings`（MCP 同函数 mcp/server.py 已派生）——recall.py:60 内部 `annotate_text(settings)` → annotator vec 增益查询谓词用 `settings.embed_model_label`。inline 切换后 REST `auto_entities=true` 的向量增益查旧标签谓词落空（**静默降级**：词面模糊仍工作、无错误结果；subprocess 生产形态主进程不切换、重启后收敛——窗口限定）。与申报①「embed 相关消费面已全派生」不符处。**修复建议**：search.py:72 改传 `effective_settings(service.settings, service.embedder)`。
- **P3-3（观察，测试判别力）**：`test_reembed_switch_blocked_until_full_library_covered` 的缺块会被全库扫描补齐，per-org 门与全库门在该形态下最终态相同——用例名声称的「未达成不得切换」无负向判别断言。全库门语义已由 SQL 审读（`embedding_coverage(None)` 全库求和）+注入②间接证实，非正确性风险。建议后续补「org 永久缺块→任务重试不切换」形态（如 pending_status 阻塞造数）。
- **P3-4（观察，沿 R1/Committer P3-7）**：pg 存量 7 个 bench/eval 残留 schema 维持登记——监督侧核对后 DROP CASCADE，非 coder 面。

**观察项（不计问题）**：择型③（R1）TC-EMB-06 扫描谓词措辞回写与择型⑧ RUNBOOK 注记均归 docs 批（R1 报告建议维持）；本报告 P3-1/P3-2 均为窄面轻缺陷、不影响 P2 修复闭环判定，可由 coder 顺手修（两处均为单行级补丁）或经 committer 裁定登记去向；双模式 167/168 warnings 为既有告警非本轮引入。

## 八、结论

```
testVerdict: PASS
testedSha:   bd9598f1614c1e40a22e5d2e09005a885a060174
```

R1 Committer P2×2+P3×8 修复闭环逐条勾验通过：**P2-1** semantic 标签源统一（派生方案穷尽核阅成立+实际执行判别用例+注入红绿实证）、**P2-2** N-1 裁定全库迁移+sysadmin 专属落地（store 双口径双方言等价+多组织双后端用例+权限三态）、P3-2/3/4/5/6 全清偿、P3-1 不修申报合规（UI 零改动+登记去向）。门禁 1642+1 双后端双模式 0 skipped 独立复跑（+5 对账闭合、去重非删用例、def test 只增 9→15）；R1 57 条用例与择型语义零回归（择型④回归注入复验）；注入验证 3 组红/绿。残留 P3×2 轻缺陷（retired enable REST 500、REST search 实体解析未派生）+P3×2 观察——均为单行级/登记级，不阻断 PASS，交 committer 终审裁处（顺手修或随 docs 批登记）。

</details>

<details>
<summary>R2 Committer 报告全文（ses_e69aa3034ffeswmU0kfrWYy0rF 续接，2026-11-01，reviewVerdict=NEEDS_CHANGES）</summary>

# task-knowledge-lattice-m2-6 R2 Committer 终审报告（只读）

## 0. 基线、方法与总体结论

- **审查对象**：`git diff f979405..bd9598f`（18 files，+1044/−315）；HEAD = `bd9598f1614c1e40a22e5d2e09005a885a060174`。R2 commit 对 docs/、.opencode/、AGENTS.md、RUNBOOK.md、prototype/、scripts/ 零改动；工作区仅监督侧 4 文件。
- **审查方式**：只读，零文件修改、零 git 写、未执行 gh pr review。未独立复跑门禁；采信 Tester 独立复跑（GATE PASS 1642+1 双后端双模式 0 skipped）并做对账/测试质量核验：+5 对账自洽；去重的是未使用 params，def test 9→15 只增、断言均升级替换——**未弱化**。
- **结论：`reviewVerdict = NEEDS_CHANGES`**
  - **P1 ×1（阻断）**：`embedding_coverage` org-scoped 调用返回**全库 datasets**——跨组织数据集名/ID 泄露（R2 P2-2 全库化引入的回归，Tester 未捕获）。
  - **P2 ×1（阻断）**：A2 reindex 在 **pending_status=failed** 的 pending 版本仍存在时被 API/执行体放行，随后 `_guard_alive` 判 cancelled——**202 成功后文档被置 parsing、在用块被删**（不可搜；R2 新加 API 用例只断言 202，是 false green）。
  - **P3 ×8**（记录级；其中 guard 并发残余、retired enable REST 500 建议 R3 修）
  - **需求边界 N-2 ×1**（pending 失败版本上的 reindex 语义：忽略 failed pending 放行 vs 保守 409，需监督侧/用户裁定）；**N-1 已按用户裁定 (a) 落地**。
  - `testedSha` = `bd9598f1614c1e40a22e5d2e09005a885a060174`（= HEAD，Tester PASS 一致）；`reviewedSha = null`（未通过，R3 修复后重审；R3 为 maxRounds=3 最后一轮）。

## 1. 问题清单

### P1-1（阻断）`embedding_coverage` org-scoped 调用泄露其他组织数据集（跨组织信息泄露）

- **位置**：`store/sqlite/backend.py:2532-2552`（org_filter 只加在子查询 `d.org_id = :org`，外层 `FROM datasets ds ORDER BY ds.id` 无 `ds.org_id` 过滤）；`store/postgres/backend.py:3802-3824`（同构）；消费面 `api/admin.py:576-594`（GET /api/orgs/{org}/embedding-coverage 的 coverage 列表直接返回）。
- **问题**：R2 为支持 `org_id=None` 全库覆盖率门，把外层 `WHERE ds.org_id = :org` 删掉后未加动态 `ds` 过滤。结果 org-scoped 调用（如管理面板）虽然子查询计数只统计本组织，但外层仍列出全库所有 datasets——其他组织的 dataset_id/dataset_name 以 total=0/done=0 行返回给该 org_admin。违反跨组织隔离（m2-5 TC-OPS-09/T15 硬约束）——数据集名/ID 也属跨组织元数据泄露。
- **修法**：外层加动态过滤 `ds_filter = " WHERE ds.org_id = :org" if org_id is not None else ""`；双方言同步；补测试：matrix 造 org:gl dataset+doc/chunk，`embedding_coverage(ORG, label)` 断言结果不含 ds:gl_lib；`embedding_coverage(None, label)` 断言包含；API 覆盖率端点同样断言 coverage 仅本组织。**P1 阻断**。

### P2-1（阻断）A2 reindex：pending_status=failed 时 API/执行体放行，随后 reset + `_guard_alive` 取消——文档不可搜

- **位置**：`api/admin.py:538-545`（pending 检查条件 `pending_status != "failed"`——failed 放行）；`worker/rebuild.py:323-337`（执行体同条件）；`core/docs/ingest.py:700-719`（`_effective_version`/`_guard_alive` 仍 `pending_version or active_version`）；`tests/test_admin_manage.py:361-380`（新 API 用例：pending parsing→409，随后 pending_status=failed→202；未断言文档状态）；`tests/test_wk_rebuild.py:594-626`（执行体用例只覆盖 pending parsing）。
- **问题**：文档 active v1 + pending v2 失败（pending_version=2, pending_status='failed'，pending 行未清除）时：① API 因 failed 放行投递 reindex（target=active v1），inline kick 同步执行；② run_reindex_task 同一条件放行 → delete_by_doc(doc,1) 删除在用块 + set_doc_active_status(parsing)；③ ingest.run_task 的 _guard_alive 取 current=pending_version(2)≠target(1) → 返回 None → outcome cancelled；④ 文档停在 active_status=parsing、在用块已删、pending failed 仍在——**不可搜**（FTS/向量/检索全不可见；reindex 恢复路径被自身堵死；再 reindex 重复同样结局）。新 API 用例只断言第二个 POST 为 202 不查终态——**false green**；这是 R1 P3-5 的未闭合变体。
- **修法（R3 二选一，建议 A，另见 N-2）**：
  - **A（保守，推荐）**：API 与执行体对任何 `pending_version is not None` 一律 409/failed（含 failed），提示「待新上传终态/清理 pending 后重投」；API 用例第二个 POST 期望 409；执行体用例补 failed 形态；文档保持 searchable_full、在用块保留。
  - **B（放行）**：修正 ingest._guard_alive/_effective_version——pending_status='failed' 时 current=active_version（failed 版本亡故）；reindex 放行并重建；补「failed pending + reindex→done、文档 searchable_full、块集正确」双后端用例。触及 core ingest 语义，需评估既有 ingest 回归（建议仅在有用户裁定 N-2 后选 B）。
  - 无论 A/B，现有 202+破坏的形态不可交付。P2 阻断。

### P3-1 最后管理员守卫：pg 跨行并发仍可 0 admin（R2「TOCTOU 根除」不成立）

- **位置**：`store/postgres/backend.py:3611、3639、3672、3681`（FOR UPDATE 只锁目标行，随后 _count_active_admins）；`store/backend.py:40-43、605-606`（docstring 声称「TOCTOU 根除」）。
- **问题**：两个并发请求分别降级 A、B 两名 admin 时，T1 锁 A 行、T2 锁 B 行（互不冲突）；各自 count 在 READ COMMITTED 下都看到 2，均通过并提交 → 0 admin。sqlite BEGIN IMMEDIATE 全局单写者无此问题；pg 的跨行 TOCTOU 未根除。R2 声明过强；实际窄（需两管理员并发互降）。
- **修法**：事务内先锁本组织全部 active org_admin 行（`SELECT ... WHERE org_id=... AND role='org_admin' FOR UPDATE`）或按 org 取 pg_advisory_xact_lock，再 count；补 pg 并发用例（两连接互降→恰一侧成功、终态 1 admin）。P3，建议 R3 修。

### P3-2（Tester P3-1，R2 回归）retired 维度 enable 的 REST 面 500（非 409）

- **位置**：`api/admin.py:185-196`（enable_dimension_value 调用未包 except ValueError）；store 侧 sqlite:2489-2530 / pg:3759-3800 已正确 raise ValueError。
- **问题**：store 级用例成立；REST PATCH {"status":"active"} 在 retired 维度上未捕获 → 500（Tester 实证）。相对 R1 的幂等 200 是 REST 面回归；create 分支已有 except ValueError→409（admin.py:842），enable 不对称。
- **修法**：enable 分支补 `except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc))`；补 REST 用例（retire→disable 200→enable 409）。P3，R3 必修（单行+一测）。

### P3-3（Tester P3-2 的更正）api/search.py:72 未派生——不构成功能缺陷，仅一致性残余

- **核对结论**：Tester 称「REST auto_entities 向量增益查旧标签谓词静默降级」**不成立**——resolve_query_entities→annotate_text 未传 fuzzy/embedder，该路径根本没有向量增益；settings 仅在 get_annotator 的 legacy snapshot 缺失 fallback 中用于 live_rev 漂移告警，非用户可见检索降级。接受为一致性小项：R3 顺手改 effective_settings 一行即可；不单列阻断、不需 known-gaps。

### P3-4 switch_blocked 用例无负向判别（Tester P3-3 观察）

- 用例造的 org:gl 缺块会被全库扫描补齐，最终态与「per-org 门」相同——用例名声称的「单 org 100% 不放行」无判别断言。全库门语义由 SQL 审读+Tester 注入②间接证实，非正确性风险。修法：补「org 永久缺块→任务重试不切换」形态，或改名并新增独立负向用例。P3 测试质量，R3 顺手。

### P3-5 卫生/精度项（合并记录）

- `api/admin.py:58` TS_FMT import 已无引用——删（P3）。
- `tests/test_admin_store_reads.py:191-193` 顶层 docstring 仍称覆盖 cycle/orphan_rows，实际只断言 3 码——改注或在 test_ops_chain_read 补 .code（P3）。
- `tests/test_admin_values.py:1-10` 模块 docstring 与实现不符——随 P3-2 修复对齐（P3）。
- P3 级别不阻断；R3 顺手修。

### P3-6 B①「逐行过期编辑」——按 R1 裁定登记去向，R2 不修合规（web/ 零改动已核实）。docs/挂账批需把 R1 coder「B①~⑩全核销」改注为「B① 3/4 子项核销+逐行过期编辑→m2-5/TC-UI」。P3 记录，无代码动作。

### P3-7（Tester P3-4）pg 存量 7 个 bench/eval 残留 schema——观察项，维持监督侧核对后 DROP SCHEMA ... CASCADE 清理或登记；非 coder 面。

### P3-8（Tester P3-3 延伸）RUNBOOK 运维注记——归 docs 批：reembed 全库迁移/切换（subprocess env 重启、inline 立即生效但主进程 ServiceContext 非 embed 字段滞后）、重索引窗口、reindex pending failed 语义（N-2 裁定后）、pg 残留清理——RUNBOOK §1/§4。

## 2. 需求边界问题

**有（N-2，1 项新增；N-1 已闭合）**——不计入代码 P 级，交监督侧/用户裁定：

- **N-2：pending 失败版本存在时的 reindex 语义**。当前 R2 实现/API 用例选择「pending_status=failed 后放行」，但 ingest._guard_alive 仍把 failed pending 视为当前目标 → 202 后 reset 并取消，文档不可搜（P2-1）。需裁定：
  - (a) **保守 409**：只要 pending_version 非空（含 failed）一律拒绝 reindex，待新上传/清理后重投（改动小、无 core 语义变更；建议 R3 默认）；
  - (b) **放行**：failed pending 版本亡故，_guard_alive 以 active_version 为当前目标，reindex 正常重建（更符合直觉，但触及 core ingest 语义，需回归）。
  - 当前「202+破坏」不是可接受语义；P2-1 的修复方向依赖此裁定。
- **N-1（R1）已按用户 2026-11-01 裁定选 (a) 全库迁移+sysadmin 专属落地**：R2 扫描/门/清理全库、多组织用例、sysadmin 三态均成立；check_path_org 免 org_scoped 的越权面分析未发现新绕过（sysadmin 全局身份；单文档 reindex 仍 owner/org_admin+org_scoped）。N-1 不再挂账。

## 3. R1 意见闭环核验（摘要）

| R1 项 | 判定 | 残余 |
|---|---|---|
| P2-1 semantic_build | ✅ 闭合 | P3-3 一致性（api/search.py:72——非功能缺陷） |
| P2-2 全库+sysadmin | ✅ 语义闭合 | **新引入 P1-1**（外层泄露）；P3-4 负向缺 |
| P3-2 B⑥ | ✅ 闭合 | P3-5 卫生（TS_FMT 未用 import） |
| P3-3 守卫 | ⚠️ 部分闭合 | pg 500 根除 ✅；跨行 TOCTOU 残余（P3-1）、docstring 过强 |
| P3-4 A4 | ⚠️ 部分闭合 | store ✅；REST enable 500（P3-2） |
| P3-5 reindex 前置 | ⚠️ 部分闭合 | parsing 双防线 ✅；failed 放行破坏（P2-1）+false green |
| P3-6 测试质量 | ✅ 基本闭合 | P3-4/P3-5 残余 |
| P3-1 B①不修 | ✅ 合规 | docs/挂账改注 |
| P3-7/8 | ✅ | 维持登记 |

**门禁/未弱化**：Tester 独立 1642+1/0 skipped；去重 −4 为未用 params（非删用例）；R1 57 条语义零破坏。未弱化确认 ✅（P1/P2 是新增缺陷，不是测试弱化）。

## 4. N-1 落实语义审查（摘要）

- 全库覆盖率门语义正确（embedding_coverage(None) 全库求和、注入②判别）；switch_blocked 无负向（P3-4）。
- sysadmin 权限形态：reembed 分支 is_system_admin 放行、不要求本组织 membership（系统级动作）；未发现新绕过（非 sysadmin 403、单文档 reindex 仍 org_scoped、doc 必须属 path org、全库迁移不返回组织数据）。测试缺口：sysadmin 无 membership 形态未覆盖（P3 级，建议 R3 补一个用例）。
- 并发/时序：顺序沿用 R1 且 Tester 回归注入红绿；gate 全库与 P1-1 的 org-scoped 外层需分开修（勿把外层过滤也去掉）。

## 5. R2 择型 7 条裁定

①ACCEPT（附 P3-3——api/search.py:72 无 vec 增益、R3 顺手统一）；②ACCEPT（附 P1-1——外层漏过滤非双口径本身问题）；③ACCEPT（附 P3-1——pg 跨行 TOCTOU 未根除、docstring 过强）；④ACCEPT（附 P3-2——REST 映射缺失）；⑤ACCEPT（附 P2-1/N-2——failed pending 双防线都放行）；⑥⑦全 ACCEPT（⑦附 P3-5 docstring 未收窄）。

## 6. Tester 新 P3×2 裁定

| Tester 项 | 裁定 |
|---|---|
| P3-1 retired enable REST 500 | **真实缺陷（R2 回归），R3 必修**（单行+REST 用例，与 create 对称） |
| P3-2 api/search.py:72 | **不成立为功能缺陷；接受为一致性小项**（该路径无 vec 基增益——Tester 结论更正；R3 顺手一行） |
| P3-3 switch_blocked 无负向 | P3 测试质量，R3 顺手 |
| P3-4 pg 残留 | 观察，维持监督侧 |

## 7. 安全性深审

P1-1 跨组织泄露=本轮唯一 P1 级安全面（读面元数据泄露）；reembed sysadmin 权限无新绕过（测试缺口 P3 级）；members/values 写路径维持 R1 结论（守卫下沉后 API 只 409 映射，pg 500 根除、跨行并发残余 P3-1）；审计同事务无缺失面；SQL 全参数化无注入面。**未发现新的 P1 级鉴权/数据写入绕过**。

## 8. 测试质量与未弱化确认

门禁采信+对账自洽；未弱化 ✅（去重性质复核、断言改强）。**关键测试缺口（R3 补）**：①P1-1 org-scoped 不含他组织 dataset 用例；②P2-1 failed-pending 双防线用例+终态断言（现有 202 用例 false green）；③P3-1 pg 并发互降用例；④P3-2 REST 409 用例；⑤P3-4 负向；⑥P3-5 docstring/import；⑦sysadmin 无 membership 202 用例。政策符合（TC-UI manual 不在门禁、DSN skipif 既有约定、web/ 零改动符合 B① 登记）。

## 9. R3 修复范围建议（maxRounds=3 最后一轮）

**必修**：1. P1-1（外层动态过滤+store/API 双后端测试）；2. P2-1（按 N-2 裁定——默认建议 (a) 保守 409：任何 pending_version 非空拒绝+API 用例第二段改 409+文档态断言+执行体 failed 形态用例）。
**建议同轮（P3 应修尽修）**：3. P3-1（锁全组织 admin 行/advisory lock+pg 并发用例；或登记 known-gaps 但 docstring 必须改如实）；4. P3-2（REST 409 映射+用例）；5. P3-3（search.py:72 一行）；6. P3-4（负向/改名）；7. P3-5（卫生三小项）；8. sysadmin 无 membership 用例。B①维持登记；P3-7/8 归监督侧/docs。
**R3 后**：Tester 独立复跑门禁（+N 对账/0 skipped）；Committer 按 bd9598f..R3 HEAD 逐条核；APPROVED 进入交付。

## 10. docs 批终版建议清单（R3 通过后监督侧落笔）

1. TEST-CASES（v1.9.12 或 R3 版本，非决策）：版本行/§六 M2 行 m2-6 交付+TC-EMB-06 全库口径注记（扫描/门/清理全库+sysadmin 专属）+coverage org 只列本组织（P1 修复口径）+reindex pending failed 语义（N-2 裁定）+members/values 端点形态+扫描谓词含 pending 超集+A5/B5；2. known-gaps：P3-1 若不修→G-27；reembed 切换窗口/B①→m2-5/m2-4 followups 余二/N-2 结果；3. design v0.9.8（非决策）：§5.3 全库迁移/sysadmin/切换载体/清理与回退窗口、§5.6/§6.2 端点表、§5.8 effective 标签源、reindex pending failed；4. RUNBOOK：§1 全库蓝绿操作序列+重启窗口+阈值重标定、§1/§4 重索引窗口+pending failed 注意、§4 审计 B5、pg 残留清理可选；5. AGENTS §1 状态行；6. _m2-plan row 7.5 done+挂账；7. 检查点终态；8. 工作区 docs 随 chore 入库。
**遗留事项去向**：B①→m2-5/TC-UI；P3-1（若挂）→known-gaps；P3-3→R3 一行；P3-4/5/6→R3；P3-7→监督侧清理；P3-8→docs 批；m2-4 followups 余二→下批/m2-5（维持）。

## 11. 交付把关建议

本轮不放行交付（P1-1/P2-1 未闭合）。R3 最后一轮需一次过：修复 P1/P2+建议 P3→Tester R3 HEAD 独立复跑→Committer 逐条核（含注入判别与回归）→APPROVED 后：用户确认交付→双 SHA 一致→manifest 完整→检查点终态+docs 批+chore 归档→gh pr review 留痕（不执行合并）。

## 12. CASE_BUG 裁定：无。

## 13. 结论

```
reviewVerdict: NEEDS_CHANGES
testedSha:     bd9598f1614c1e40a22e5d2e09005a885a060174（= HEAD，Tester PASS 一致）
reviewedSha:   null（未通过；R3 修复后重审；maxRounds=3 最后一轮）
P1: 1（embedding_coverage org-scoped 跨组织 datasets 泄露）
P2: 1（reindex pending failed：202 后 reset+取消→文档不可搜；API 用例 false green）
P3: 8（guard pg 跨行 TOCTOU、retired enable REST 500、search.py 一致性[非功能]、switch_blocked 无负向、audit/docstring/TS_FMT 卫生、B① 登记、pg 残留、RUNBOOK）
需求边界: N-2 ×1（pending failed reindex 语义；N-1 已闭合）
CASE_BUG: 无
```

R1 的 P2-1/P2-2 主体与 P3-2/3/4/5/6 修复方向成立（effective_settings 派生、全库扫描/门/清理、sysadmin、守卫事务化、reindex 前置、测试质量）——但 R2 全库化引入 **P1 跨组织泄露**，reindex pending failed 路径仍有 **P2 破坏面**，且 Tester 的 P3-2 结论需更正（api/search.py 无 vec 增益）。修复 P1/P2（及 R3 顺手 P3）后重审；R3 为最后一轮，需一次过。

</details>

<details>
<summary>R3 Tester 报告全文（ses_e69ca7427ffe909TXr7yUZvXIO 续接，2026-11-01，testVerdict=PASS）</summary>

# task-knowledge-lattice-m2-6 R3 修复轮独立验证报告（最终轮）

**testVerdict: PASS**
**testedSha: `00dc486ab3d6351702a079e07207dfc63903e059`**（= 00dc486，develop_opencode HEAD，全 40 位复核一致；父提交=bd9598f=R2 PASS SHA）
验证时间：2026-11-01；续接 R1/R2 Tester 会话独立执行，未采信 coder 自测结论。**最后一轮严格标准：未发现任何新 P1/P2 缺陷。**

## 一、门禁独立复跑（双后端双模式）

```
docker start lattice-pg; export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
scripts/test_gate.sh
→ GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
  （pg 臂 614 条用例全实跑：[pg] 参数化 580 + PG 专用 34）
```

| 模式 | 结果 | 时长 |
|---|---|---|
| 常规 | **1651 passed, 1 deselected, 0 skipped** | 186.23s |
| python -O | **1651 passed, 1 deselected, 0 skipped** | 187.11s |
| pg 臂收集（独立复算） | **614 = 580 + 34** | — |

- **+9 对账（独立核对闭合）**：wk_rebuild 30→**34**（负向用例×2 后端 + pending 参数化 +2）+ manage 7→**10**（no_cross_org_leak ×2 + sysadmin 无 membership ×1）+ members 13→**14**（pg 并发互降）+ values 14→**15**（REST 409 链路）= +9 ✓
- **def test 只增不减**：wk_rebuild 15→16、manage 6→8、members 8→9、values 8→9、store_reads 9→9；diff 中 3 个「删除函数名」逐个核实均为**重写/改名**（①`test_api_reindex_rejected_while_pending` fixture 换名+false green 重写、②`switch_blocked`→`full_scan_fills_other_org_gaps` P3-4 改名、③`reindex_rejected_while_pending_version` 参数化重建）；被删的 2 行 assert 为 N-2 裁定语义变更替换（failed 放行 202 → 一律 409），非弱化 ✓
- skip 核对：双模式 0 skipped；1 deselected=TC-UI manual（政策性）✓

## 二、R2 Committer 意见修复闭环逐条判定

| 项 | 判定 | 证据摘要 |
|---|---|---|
| **P1-1**（我 R2 未捕获——重点补课）org-scoped coverage 跨组织 dataset 泄露 | ✅ | **SQL 审读**：双方言 `ds_filter = " WHERE ds.org_id = ..." if org_id is not None else ""` 外层动态过滤（sqlite/pg 逐语句等价）；内层 `org_filter` 独立——**gate 全库口径（org_id=None 内外均无过滤）未动**，两者分层验证（store 级用例双向断言：org-scoped 不含 ds:gl_lib + None 全含且 gl total=1/done=0）；API 端点补断言（scoped_ids 无 ds:gl_lib）。**我的 R2 漏检复盘**：R2 勾验 embedding_coverage 时只核了「分子/分母在用块口径」与全库门，未核外层 `FROM datasets` 的行集范围——审查颗粒度停在计数正确性、未到行集泄露面。**本轮补课三重独立验证**：①coder store/API 用例审读通过；②**自构造独立验证 ALL PASS**（三组织 org:tax×2 datasets+org:gl+org:third、他组织放 total=1 真实行形态——org-scoped 精确返回本组织 2 个、None 返回全部 4 个、API 端点 org_admin 视角同断言）；③注入①判别力实证（摘 ds_filter→用例红，缺陷形态精确重建）。P1-1 判闭合 |
| **P2-1**（N-2 裁定 a）pending 含 failed 一律拒绝 | ✅ | API `if pending_v is not None:`（failed 豁免删除）→409 带处置提示；执行体同条件 failed 带原因（rebuild.py）——**core ingest 零改动核实**（core/docs/ingest.py 不在 11 files，diff 证实）；**false green 用例重写质量**：第二段改 409 + 终态三重断言（文档 searchable_full/在用块保留/任务零投递）；执行体 `@pytest.mark.parametrize("pending_status", ["parsing","failed"])` 双形态双后端 + 文档不动/块保留断言增强；**注入②实证**（API 侧回退 failed 豁免→API 用例红而执行体 4 条仍绿——双防线独立性顺带实证） |
| **P3-1** pg 守卫跨行 TOCTOU | ✅ | `pg_advisory_xact_lock(hashtext(org))` 事务级咨询锁（update/delete 两入口同款，BEGIN 后即刻取锁）；**弃用方案记因诚实**（全 admin 行 FOR UPDATE 在并发提交后 EPQ 重评抛 tuple concurrently updated——协议 docstring 与代码注释双处如实记录）；协议 docstring「TOCTOU 根除」过强措辞已如实化（「pg 事务级咨询锁串行化跨行并发、sqlite 单写者串行」）；**pg 并发用例质量**：两独立连接（串行 setup 避 catalog 竞态并注释说明）+ threading 真并发互降 + 断言 `sorted(results)==["blocked","ok"]` 恰一侧 + 终态恒 1 admin；**注入③复核**：摘锁后 5/5 连续红（与 coder 证伪声明一致）、恢复后 3/3 绿 |
| **P3-2** retired enable REST 409 | ✅ | enable 分支 `except ValueError → 409`（与 create 对称——我 R2 报告 P3-1 的单行补丁落地）；REST 链路用例 retire→disable→enable 409（`test_api_enable_on_retired_dimension_409`：断言 409+detail 含 retired）；values docstring 对齐 |
| **P3-3** search.py:72 一致性 | ✅ | `effective_settings(service.settings, service.embedder)` 一行（注释如实标注「该路径无 vec 增益，一致性收口」——采纳 Committer 对我 R2 结论的更正） |
| **P3-4** switch_blocked 拆解 | ✅ | 正路径改名 `test_reembed_full_scan_fills_other_org_gaps`（docstring 说明改名理由）；独立负向 `test_reembed_no_switch_until_full_library_converged`（monkeypatch 覆盖率恒缺一块→任务 failed+错误含「未收敛」+**settings/embedder 不切换+旧标签向量保留+零 semantic_build 投递**四重断言）；附带收口：未收敛从 raise 改 fail-closed（update_task failed+return——切换/清理/联动均未发生语义保持，见择型③） |
| **P3-5** 卫生三小项 | ✅ | admin.py:58 未用 TS_FMT import 删（diff 证实）；audit_chain 测试 docstring 收窄为「**断言 3 码**（multi_heads/hash_mismatch/fork）；cycle/orphan_rows 为防御分支」如实声明；values docstring 对齐 |
| **sysadmin 无 membership 202** | ✅ | `test_api_reembed_sysadmin_without_membership`：删成员关系+断言 is_system_admin=1 前置→POST 202→轮询 done——check_path_org 免 org_scoped 形态实证（R2 Committer §4 测试缺口闭合） |

## 三、R2 漏检 P1 的补课结论（专项）

- **漏检根因**：R2 勾验 P2-2 时对 `embedding_coverage` 的验证停在「计数口径正确性」（在用块口径/全库门），未审计外层 FROM 子句的**行集范围**随 org_id 参数化的变化——R2 全库化重构把外层 `WHERE ds.org_id` 删掉时，org-scoped 分支的行集边界随之丢失，我的用例审读与 SQL 审读都没覆盖这一层。
- **本轮补课动作**：①双方言逐句审读（ds_filter/org_filter 双层独立）；②coder store+API 用例质量审读（双向断言）；③**自构造第三组织/多 dataset 独立验证 ALL PASS**（含 total>0 真实行形态，比 coder 用例的造数更强）；④注入①红/绿证明用例判别力；⑤注入回归面复查（embedding_coverage 的另外两个消费面——API 端点与 gate——在 R3 后语义分层正确：端点 org-scoped 泄露根除、gate 全库门不受影响）。

## 四、R3 择型申报 3 条逐条结论

| # | 申报 | 结论 | 依据 |
|---|---|---|---|
| ① | advisory_xact_lock（弃全 admin 行 FOR UPDATE——EPQ 竞态） | **ACCEPT** | 方案审读：事务级锁、同组织串行化、BEGIN 后即刻取锁覆盖守卫判定全程；EPQ 弃用因 docstring+注释双处如实（`tuple concurrently updated` 实测）；**hashtext 键冲突面无害声明成立**——hashtext 碰撞仅致跨组织偶发串行化（性能非正确性），事务结束即释放；sqlite 侧 BEGIN IMMEDIATE 天然串行无对应面；注入③ 5/5 红+恢复 3/3 绿复核 coder 声明可信 |
| ② | monkeypatch 覆盖率恒缺一块（无合法静态永久缺块形态） | **ACCEPT** | 判别力：stuck_coverage 恒 `done-1`→收敛判定永 false→3 轮上限触发失败收口——负向形态锁死「未达标不切换不清理不投递+旧向量保留」四重断言；patch 的是 env.backend 实例（与 run_reembed_task 消费同一实例）真实生效；「无合法静态永久缺块形态」的申报诚实（pending 阻塞造数会牵扯 ingest 语义） |
| ③ | 未收敛 raise→fail-closed 收口（直调/runner 语义一致） | **ACCEPT（附注）** | 行为变化如实指出：R1 申报的「极端并发摄取窗口任务重试收敛」（raise→runner 自动重试）收窄为「一次失败 failed 留人工」——fail-closed 保守方向、错误信息明确（含「切换与清理未发生」）、直调不抛异常两路径语义一致、任务书申报在案；后续若需自动重试可在 runner 层按 error 分类回队（登记即可，非缺陷） |

## 五、回归面结论（最后一轮全面回归）

- **门禁 1651 全绿**覆盖 R1（57 条）+R2（+5）全部存量用例语义；def test 三轮累计只增
- **R2 核心用例零破坏**：多组织全库迁移（org:gl 同迁+stray=0）、sysadmin 三态+无 membership 形态、semantic_build 实际执行（dict_rev 组件/模糊行新标签）、probe dim 跟随、m2s-6 vec 同源——全绿（门禁）+ 用例本体未被本轮 diff 触碰
- **R1/R2 择型核心语义**：re-pin 顺序（rebuild.py R3 diff 未触及 switch/repin/谓词段）、with_model 专用实例、扫描 pending 超集（sqlite:2577 join 不限 version 原样）、kick 双通道（app.py R2/R3 均零改动）——零回归
- **m2-3 投递面适配**：`_quiet_inline`/`_mgmt_env_quiet` 隔离形态延续，投递同步执行+轮询终态断言保持 ✓

## 六、注入验证（3 组，恢复→红→恢复→绿）

| # | 注入 | 红证据 | 恢复 |
|---|---|---|---|
| ① | 摘除 embedding_coverage 外层 ds_filter（sqlite——P1-1 缺陷形态重建） | `test_embedding_coverage_org_scoped_no_cross_org_leak[sqlite]` **FAILED**——test_admin_manage.py:457 `assert 'ds:gl_lib' not in {'ds:gl_lib', 'ds:vat_lib'}`（泄露精确复现） | 恢复后双后端 2 passed；git diff 0 行 |
| ② | API pending 拒绝条件回退 failed 豁免（R2 P2-1 缺陷形态重建） | `test_api_reindex_rejected_while_pending` **FAILED**（第二段 409 断言红）；执行体 pending 参数化 4 条同时仍绿——**双防线独立性实证** | 恢复后 1 passed；git diff 0 行 |
| ③ | 摘除 pg advisory lock（update_membership——R2 P3-1 缺陷形态重建） | `test_last_admin_guard_concurrent_demote_pg` **5/5 连续 FAILED**（互降并发无锁→守卫失效，与 coder 证伪声明一致） | 恢复后 3/3 passed；git diff 0 行 |

业务代码零残留（备份/恢复经 /var/folders 临时目录，三次注入后 git diff 均为空）。

## 七、临时产物清理确认

- **pg**：非系统 schema 总数 7 = R1/R2 报告过的存量 bench/eval 残留（`lattice_eval_*`×5+`lattice_bench_g6hv_*`×2），**本次会话零新增**（维持监督侧清理裁定）
- **临时目录**：m26r3_inject 与 P1-1 独立验证临时库全删；**进程**：无残留
- **工作区终态**：与验证前一致——仅监督侧 4 文件，业务代码 git diff 为零；HEAD 未动

## 八、问题清单

**P1：无。P2：无。P3：无（新增）。**

**观察项（不计问题）**：
1. 择型③行为注记：reembed 覆盖率未收敛从「runner 自动重试」收窄为「failed 留人工」——fail-closed 已申报且语义一致；后续如需自动收敛可在 runner 按 error 分类回队（登记 docs 批可选）。
2. hashtext 咨询锁的跨组织偶发串行化（键碰撞）——纯性能面、事务级即释，无需处置。
3. pg 存量 7 个 bench/eval schema 与 RUNBOOK 注记（P3-7/P3-8）——维持监督侧/docs 批登记（三轮一致）。
4. 三轮累计遗留登记核对：B①逐行过期编辑→m2-5/TC-UI 批（合规）；m2-4 followups 余两项→下批/m2-5（合规）。

## 九、结论

```
testVerdict: PASS
testedSha:   00dc486ab3d6351702a079e07207dfc63903e059
```

R2 Committer P1×1+P2×1+P3×8+N-2 修复闭环逐条勾验**全部闭合**：P1-1 跨组织 dataset 泄露根除（SQL 双层审读+coder 用例+我的三组织/多 dataset 独立自构造验证 ALL PASS+注入①判别实证——含 R2 漏检根因复盘与补课记录）；P2-1 按 N-2 裁定 (a) 双防线收口（core 零改动+false green 重写+参数化 failed 形态+注入②含双防线独立性实证）；P3-1 咨询锁（EPQ 弃用记因诚实+pg 真并发用例+注入③ 5/5 红复核）；P3-2/3/4/5+sysadmin 无 membership 用例全清偿。门禁 **1651+1 双后端双模式 0 skipped** 独立复跑（+9 对账闭合、def test 只增、零弱化）；R1/R2 全部用例与择型语义零回归；注入验证 3 组红/绿。**最后一轮未发现任何新 P1/P2 缺陷，testVerdict=PASS**——提请 committer 终审（testedSha=HEAD 一致）。

</details>

<details>
<summary>R3 Committer 报告全文（ses_e69aa3034ffeswmU0kfrWYy0rF 续接，2026-11-01，reviewVerdict=APPROVED）</summary>

# task-knowledge-lattice-m2-6 R3 Committer 终审报告（只读）

## 0. 基线、方法与总体结论

- **审查对象**：`git diff bd9598f..00dc486`（11 files，+364/−57）；HEAD = `00dc486ab3d6351702a079e07207dfc63903e059`。R3 commit 对 docs/、.opencode/、AGENTS.md、RUNBOOK.md、prototype/、scripts/ 零改动；工作区仅监督侧 4 文件。
- **审查方式**：只读，零文件修改、零 git 写、未执行 gh pr review。未独立复跑门禁；采信 Tester 独立复跑（GATE PASS 1651+1 双后端双模式 0 skipped；pg 614=580+34）并对对账/测试 diff 做独立核验：+9 对账自洽；def test 只增（3 个「删除函数名」逐个核实为重写/改名）；被删 2 行 assert 为 N-2 语义变更替换（202→409），未弱化。
- **结论：`reviewVerdict = APPROVED`**
  - **P1：无；P2：无**。R2 的 P1-1（跨组织数据集泄露）、P2-1（pending failed reindex 破坏面）均闭合；P3-1~P3-5 + sysadmin 用例全清偿；N-1/N-2 用户裁定落实。
  - **P3 ×3（记录级，不阻断）**：R3 两处文案/注释与新行为不一致 + 一处 R2 遗留 docstring。
  - **需求边界：无新增**（N-1/N-2 均闭合；N-2 裁定 (a) 已落任务原文 A2）。
  - `testedSha` = HEAD；**`reviewedSha` = `00dc486ab3d6351702a079e07207dfc63903e059`**——testedSha = reviewedSha = HEAD **三一致，双通过达成**（round 3/3，maxRounds=3）。

## 1. 问题清单（P1/P2 无；P3 记录级）

### P3-1（记录级）pg 并发守卫用例 docstring 残留旧方案「全 admin 行 FOR UPDATE」
- `tests/test_admin_members.py:434` docstring 仍写「全 admin 行 FOR UPDATE 串行化」——与实现（advisory lock）/择型①矛盾；测试本体有效，仅描述陈旧。处置：下批卫生/docs 批改注。

### P3-2（记录级）fail-closed 收口行为变化：注释/错误文案仍按旧「自动重试」表述
- `worker/rebuild.py:60-61`（_MAX_CONVERGE_ROUNDS 注释）、`:203-208`（fail-closed 分支注释「留重试」+错误文案「任务重试收敛」，实际 update_task(failed) 后 return 无自动重试）。行为已申报、Tester ACCEPT、fail-closed 方向正确；文案精度问题。处置：接受行为变更+docs 批登记（RUNBOOK/known-gaps：未收敛=failed 留人工）；下批改注释/文案。

### P3-3（记录级）覆盖率端点 docstring 仍写旧「全局在用块口径」进度
- `api/admin.py:576-579` docstring 未随 R2 P2-3（按任务 payload 目标标签）更新。处置：docs 批/下批改注。

> 其余观察（Tester 4 条均不计问题）：择型③行为注记（P3-2 同源）；hashtext 键碰撞纯性能面；pg 残留+RUNBOOK 维持监督侧/docs 批；B①→m2-5/TC-UI、m2-4 followups 余二→下批/m2-5（登记合规）。

## 2. R2 Committer 意见闭环核验（摘要表）

| R2 项 | 判定 | 复核证据 |
|---|---|---|
| P1-1 跨组织泄露 | **✅ 闭合** | 双方言外层 ds_filter（sqlite:2541-2551/pg:3819-3829）+内层 org_filter 独立——org_id=None 全库门内外均无过滤（gate 语义不动）；store matrix 双后端双向断言+API 追加断言；Tester 三组织自构造+注入①实证；**全部调用面核阅**（admin 面板/reembed 窗口 org、reembed 任务 None）无同类泄露残留 |
| P2-1 pending failed 破坏面 | **✅ 闭合（N-2 a）** | API `pending_v is not None`（admin.py:543-554）→409 带处置提示；执行体同条件 failed（rebuild.py:335-346）；**core ingest 零改动**（不在 11 files）；false green 重写（第二段 409+终态三重断言）+执行体双形态参数化；注入②双防线独立性实证 |
| P3-1 pg 跨行 TOCTOU | **✅ 闭合（附 P3-1 docstring）** | advisory_xact_lock 两入口 BEGIN 后即刻取得（pg:3606-3613/3677-3681）；EPQ 弃用因 docstring+注释双处如实；sqlite 单写者天然串行；协议 docstring 措辞如实化；pg 真并发互降用例恰一侧 blocked+终态 1 admin+注入③ 5/5 红复核 |
| P3-2 REST 500 | **✅ 闭合** | enable 分支 except ValueError→409（admin.py:194-200 与 create 对称）；REST 链路用例 |
| P3-3 search 一致性 | **✅ 闭合** | effective_settings 改传+注释如实（采纳 R2 更正） |
| P3-4 负向判别 | **✅ 闭合** | 正路径改名+独立负向四重断言；fail-closed 收口（行为变化见 P3-2） |
| P3-5 卫生 | **✅ 闭合（附 P3-3 docstring）** | import 删/docstring 收窄×2 |
| sysadmin 无 membership | **✅ 闭合** | 删成员关系→202→done→切换断言（check_path_org 形态实证） |
| B① 不修 | **✅ 登记合规** | web/ 零改动；m2-5/TC-UI 批 |
| P3-7/8 | **✅** | 维持监督侧/docs 批 |

**门禁/未弱化**：Tester 独立 1651+1/0 skipped；零弱化；R1/R2 存量用例与择型核心语义零回归（re-pin/with_model/pending 超集/kick/m2s-6 同源）。

## 3. R3 择型 3 条裁定

①**ACCEPT**（advisory lock——事务级、同组织串行化、无死锁面〔每事务一锁无嵌套即释〕、EPQ 弃用因双处如实、注入③复核；残余=P3-1 docstring）；②**ACCEPT**（monkeypatch 判别力强+申报诚实）；③**ACCEPT（附 docs 批登记+P3-2 文案）**（fail-closed 保守方向、两路径一致、错误含「切换与清理未发生」；RUNBOOK/known-gaps 登记「未收敛=failed 留人工」；后续 runner 按 error 分类回队可选）。

## 4. 安全性终审

P1-1 修复完整性 ✅（全部调用面核阅无同类泄露残留）；advisory lock 无死锁面 ✅（单锁无嵌套、事务级即释、hashtext 碰撞纯性能）；409 拒绝面无绕过 ✅（双防线+core 零改动+任务创建前拒绝）；sysadmin 无 membership 无新越权面 ✅（非 sysadmin 403、单文档 reindex 仍 org_scoped、全库迁移不返回组织数据）；审计/写路径维持 ✅。**未发现新的 P1/P2 级鉴权/数据写入/跨组织读取缺陷。**

## 5. 测试质量与未弱化确认

门禁采信+对账自洽；零弱化（改名/重写/语义替换逐项核实）；新增用例均具判别力（Tester 3 组注入红/绿+diff 核阅）；残余 P3×3 为文案/注释记录级；政策符合（TC-UI manual/DSN skipif/web 零改动）。

## 6. 需求边界

**无新增（N-n）**。N-1（全库+sysadmin）与 N-2（pending 含 failed 保守拒绝）均已落实闭环；R3 未暴露新口径冲突。择型③行为变化属实现选择（已申报/ACCEPT），归 docs 批登记。

## 7. docs 批终版建议清单（监督侧落笔）

1. **TEST-CASES v1.9.12（非决策）**：版本行/§六 M2 行 m2-6 交付+TC-EMB-06 全库口径（扫描/门/清理全库+sysadmin 专属+全库单标签一致）+注记（①扫描谓词含 pending 超集/coverage org 只列本组织〔P1-1 口径〕/reindex pending 含 failed 409〔N-2〕/reembed sysadmin 含无 membership/未收敛 failed 留人工〔择型③〕/members+values 端点形态/A5·B5/B① 3/4 改注）+门禁 1651+1。
2. **known-gaps**：fail-closed 登记（未收敛不再自动重试）；hashtext 碰撞性能面可选；B①→m2-5/TC-UI；m2-4 followups 余二→下批/m2-5；pg 残留运维清理；**G-27 不再需要**。
3. **design v0.9.8（非决策）**：§5.3 全库迁移/sysadmin/切换载体/清理与回退窗口/fail-closed；§5.6/§6.2 members 三端点+values 两端点+coverage org 口径；§5.8 effective 标签源；reindex pending（N-2）；A3 守卫 advisory lock 实现口径。
4. **RUNBOOK**：§1 全库蓝绿操作序列（sysadmin/全库门/切 env 重启/VACUUM）+subprocess 重启窗口+inline 限制+**未收敛 failed 留人工处置**+阈值重标定；§1/§4 重索引窗口+pending failed 注意；§4 审计 B5；pg 残留清理可选。
5. **AGENTS §1**：m2-6 交付、下一段 m2-5、门禁 1651+1。
6. **_m2-plan**：row 7.5 done、§二要点、§三挂账、基线 1651+1、下一段 m2-5。
7. **检查点**：终态回写（本报告+R1 coder「B①~⑩全核销」改注「B① 3/4+登记」+P3 处置+N-1/N-2 裁定）。
8. 工作区监督侧 docs 随交付 chore/docs 批入库。

## 8. 遗留事项终版去向（供监督侧回写检查点遗留事项节）

- B①「逐行过期编辑」→ m2-5/TC-UI 批（登记不修；R1 条目改注「B① 3/4」）。
- m2-4 followups 余二（`_outbox_insert` 掩码/MCP 审计顺序）→ 下批/m2-5 测试补强批（维持）。
- P3 记录级三项（P3-1 test docstring 旧称 FOR UPDATE/P3-2 fail-closed 注释+文案旧称自动重试/P3-3 coverage 端点 docstring 旧称全局口径）→ docs 批+下批卫生。
- fail-closed 行为变更（择型③）→ docs 批登记（RUNBOOK/known-gaps）；后续 runner 按 error 分类回队可选。
- pg 存量 7 个 bench/eval schema → 监督侧核对后 DROP CASCADE。
- RUNBOOK 注记（P3-8）→ docs 批（§1/§4）。
- TC-UI-01~04 手动走查 → 用户侧（维持）。
- 无 G-27 新登记（advisory lock 已闭合 pg 跨行 TOCTOU）。

## 9. manifest 要点

- **双 SHA**：HEAD = testedSha = reviewedSha = `00dc486ab3d6351702a079e07207dfc63903e059`（三一致）。
- **门禁**：GATE PASS 1651+1 双后端双模式 0 skipped（pg 臂 614=580+34 全实跑；+9 对账闭合；def test 只增、零弱化）。
- **rounds=3**（R1 PASS/NC → R2 PASS/NC → R3 PASS/APPROVED）；verdicts：R3 PASS/APPROVED。
- **specRulings**：R1 任务书确认（2026-11-01 14:58）；N-1（17:19）全库迁移+sysadmin 专属；N-2（19:47）pending 含 failed 一律 409/fail-closed。
- **gapClosures**：P1-1/P2-1/P3-1~P3-5/sysadmin 用例；N-1/N-2；B① 登记；m2-4 followups 余二登记；pg 残留维持。
- **handover**：B①→m2-5/TC-UI；m2-4 followups 余二→下批/m2-5；P3×3 文案→docs 批+下批卫生；fail-closed→docs 批；pg 残留→监督侧；TC-UI→用户侧。
- **stale=false**：R3 diff 零 docs/scripts/prototype/检查点改动；工作区仅监督侧 4 文件；临时产物已清。

## 10. 交付把关建议

本报告结论 APPROVED，双通过达成。按流程：用户确认交付后，Committer 执行 gh pr review 留痕（PR base=develop、分支 develop_opencode），不执行合并；检查点终态+docs 批+chore 归档批由监督侧按 SSH 流程入库/推送。证据 manifest 以上要点+门禁原始输出+filesChanged（累计 39）+工作区终态+注入 3 组红/绿记录归档；双 SHA 与 HEAD 一致；stale=false。

## 11. CASE_BUG 裁定：无。

## 12. 结论

```
reviewVerdict: APPROVED
reviewedSha:   00dc486ab3d6351702a079e07207dfc63903e059
testedSha:     00dc486ab3d6351702a079e07207dfc63903e059（= HEAD，三一致）
P1: 0 | P2: 0 | P3: 3（记录级，不阻断） | 需求边界: 无新增（N-1/N-2 闭合） | CASE_BUG: 无
rounds: 3/3（最后一轮）
```

R2 的 P1-1 跨组织泄露、P2-1 pending failed 破坏面均闭合（SQL 双层过滤+双防线+core 零改动+注入判别实证）；P3-1~P3-5 与 sysadmin 无 membership 用例全清偿；N-1/N-2 用户裁定落实；门禁 1651+1 双后端双模式 0 skipped、+9 对账闭合、def test 只增、零弱化；R1/R2 存量与择型核心语义零回归。残余 3 项为文案/注释/docstring 记录级，转 docs 批与下批卫生，不影响功能、安全与交付质量。

**终审通过，放行交付。**

</details>
