---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2-3
target: knowledge-lattice
coderTaskId: ses_e7565e421ffeibNhg99G5B37wU
testerTaskId: ses_e75356242ffeqpGuedInlPvXe0
committerTaskId: ses_e74efae1dffeocAWiS1Yfl3633
status: done
round: 3
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: dcf3923732ae89a5ca26e977c1eb108be5d8881b
reviewedSha: 6633914
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [store/backend.py, store/sqlite/backend.py, store/postgres/backend.py, store/audit_chain.py, store/postgres/audit.py, store/sqlite/backup.py, store/postgres/backup.py, api/admin.py, domain/audit_events.py, core/docs/credentials.py, worker/maintenance.py, web/index.html, web/app.js, web/i18n.js, web/style.css, scripts/test_gate.sh, benchmarks/dr_ops05_drill.py, tests/test_ops_chain_read.py, tests/test_ops_03_audit_access.py, tests/test_ops_06_csv_grants.py, tests/test_ops_07_dim_governance.py, tests/test_ops_08_grants_replace.py, tests/test_admin_manage.py, tests/test_admin_store_reads.py, tests/test_ops_05_backup.py, docs/TEST-CASES.md, RUNBOOK.md, AGENTS.md, .opencode/workflows/_m2-plan.md, .opencode/workflows/task-knowledge-lattice-m2s-1.md]
endReason: null
createdAt: 2026-10-30T10:14:29+0800
updatedAt: 2026-10-30T15:14:50+0800
---

# task-knowledge-lattice-m2-3: M2.3 管理面 API + 最小 UI + m2-2 移交 B1~B6 收编

## 任务原文

**需求**（design §8 M2 第 3 项 + §6.2 管理面端点〔L1111 起〕+ §5.7 前端薄壳〔prototype 五视图双基准〕；requirements FR-4〔操作矩阵与维度治理〕/FR-6〔审计分级〕/FR-8〔i18n〕；前置 m2-1 worker 任务框架〔PR #2〕、m2-2 审计/备份〔PR #3〕已交付——任务取消机制/审计 outbox/月库/备份快照底座就绪）：

**A. 管理面 API（§6.2 M2 新增端点——api/admin.py 为主落点，既有 admin.py 审计查询/dev-token 现状先核）**：

1. **维度治理**：①取值停用 `PATCH /api/orgs/{org}/dimensions/{id}/values` status=disabled 带 **dry_run 影响面预估**（FR-4——返回受影响文档/授权计数，确认后生效+审计）；②维度退役 `POST /api/orgs/{org}/dimensions/{id}/retire`（影响面预估+二次确认〔confirm 参数〕+审计；**T20 半句收口**——退役放宽必须有审计；退役后 PATCH enabled/required 不影响过滤的口径不变）
2. **grants 写路径 + expires_at**：`PUT /api/orgs/{org}/members/{id}/grants` 授权全量替换（**只替换 local 授权、sync 不动**；支持 expires_at——grants 表 expires_at 列现状先核，无则迁移；**TC-OPS-08**）
3. **CSV 批量导入/导出**：`GET/POST /api/orgs/{org}/grants/export · import`（**TC-OPS-06**：CSV 无 org 列〔A-12——org 一律以路径为准，CSV 含 org 列不论一致与否整批拒绝〕；dry_run 差异预览后生效；幂等全量替换〔二跑零差异〕；sync 维度行不动〔T-CSV 主断言〕；目标用户无有效成员关系拒绝该行〔防孤儿授权〕；500 行批量正确〔M2.6 验收句提前收口〕）
4. **任务取消**：`POST /api/orgs/{org}/tasks/{id}/cancel`（接 m2-1 worker 取消机制——cancel 语义已就绪，API 门控 org_admin/owner；M2 标注解除）
5. **手动重索引 + 重嵌入入口**：`POST /api/orgs/{org}/documents/{id}/reindex`（投递 reindex 任务；**换模型重嵌入入口**——`?embed_model=` 或等价形态投递 reembed 任务〔**TC-EMB-06**——方案二蓝绿全流程 M0b-2 已定，m2-1 已有 reembed 任务类型，本段接 API 面与语义层强制重建联动登记〕）
6. **嵌入覆盖率面板**（只读端点——`GET /api/orgs/{org}/embedding-coverage` 或挂 stats：当前 embed_model/维度/各库覆盖率〔tombstone=0 且 version=active_version 口径〕；reembed 窗口 done/total 进度〔任务行数据源〕；**不做可改参数**——改模型=走重嵌入流程，design §8 明示）
7. **审计分级查询收口**：`GET /api/orgs/{org}/audit`（**TC-OPS-03**：org_admin 本组织全量〔含查询词与命中〕/ 系统管理员仅元数据〔查询词与命中详情不含——确需内容走审批+临时授权〕/ org_admin 查他组织拒绝；既有 admin.py 审计查询现状先核，分级不全则补全；**B2/B5 承接**〔见 D 组〕）

**B. 最小 UI（web/ 薄壳——prototype/index.html 五视图双基准〔信息结构+UI 风格〕；既有 i18n 机制复用 FR-8）**：权限视图（grants 管理/CSV 导入导出）、维度治理视图（停用 dry_run/退役）、任务与审计视图（取消/重嵌入入口/覆盖率面板/审计分级查询）——管理面操作页面化；服务端不感知语言；**TC-UI 手动走查组不进门禁**（manual 标记沿用）。

**C. m2-2 移交 B1~B6 收编**（其检查点遗留事项节为权威）：
- **B1**：upload.reclaim 等字面量事件常量化（domain/audit_events.py 补齐）
- **B2**：审计读路径改 **prev_hash 链遍历**（G-13 对冲——不依赖 rowid/seq 读序；月库侧读取按链验证）
- **B3**：**审计月库纳入备份口径**——sqlite 自动备份快照〔maintenance 备份任务〕纳入 audit_*.db 月库文件（现仅主库+objects——恢复后审计历史全失）；RUNBOOK §4 备份范围注记更新（监督侧落笔、随本段 docs 批入库）
- **B4**：stats 新键 **audit_outbox_trimmed** 同步运维面板（GET stats 端点/面板展示）
- **B5**：R1 期行语义列 detail_json 兜底口径（早期审计行无语义列时读路径兜底）
- **B6**：last_row_hash NULLS 防御分支修正（ASC 排序或 WHERE seq IS NOT NULL——m2-2 检查点 R3 记录）+ 显式 NULL seq 探针测试

**D. chore 归档批**（独立 commit，沿先例）：工作区监督侧文件原样入库——`docs/TEST-CASES.md`（v1.9.2）+ `AGENTS.md` + `.opencode/workflows/_m2-plan.md` + `task-knowledge-lattice-m2s-1.md`；**不含 `.opencode/agent/supervised-coding.md`**。

**R2 范围增补**（2026-10-30 12:42 用户拍板「按建议的来」后落笔）：

- **必修（Committer P2×4 + 边界3）**：P2-1 CSV/PUT 重复行（解析期按 username,dim_key,value 去重+同值不同 expires 显式 400 报行号或明确 last-wins 且 dry_run/apply 同规则+PUT pydantic 模型校验+重复行用例）；P2-2 expires_at 格式校验（API 边界 PUT/CSV 共用严格时间解析、非法 400、双方言同口径测试——修复 sqlite fail-open 安全语义）；P2-3 reembed 进度按任务 payload.embed_model 目标标签算 embedding_coverage（执行体未落地前 done=0/not_started——不把旧标签覆盖率当进度）+测试改；P2-4 补 matrix 级用例（list_grants_for_export/find_user_by_username/read_pending_outbox_events/read_last_maintenance_stats + CSV 差异读路径——pg 臂覆盖）+修 test_ops_06 docstring；**边界3：停用影响面补 locked_docs 字段**（v1.6.3「维度写锁项」显式化——v1.9.3 已登记口径）
- **择机收（P3×17，coder 自行判断纳入——量小建议全收 1/2/3/4/5/6/7/8/10/11/12）**：P3-1 月库兜底取最后一条；P3-2 双源合并按 id 去重；P3-3 limit Query 校验；P3-4 dimension.* target 投影对齐；P3-5 walk_chain 分叉/多链头/孤儿/环永久用例；P3-6 org 头规范化（大小写/strip）；P3-7 非 UTF-8 CSV 400；P3-8 backup stats 补 audit_months 键；P3-10 sysadmin 用例断言补全+兼任永久用例；P3-11 重复断言行清理；P3-12 maintenance.run 字面量改常量。P3-9（drill 脚本）与 P3-14（UI 解析）可顺 R2 或登记 m2-6；P3-13/15/16/17 为注记/登记类不动代码
- **登记（已处置）**：两口径裁定落 TEST-CASES v1.9.3（监督侧已落笔）；RUNBOOK §4 已随 B3 更新；边界1/2 新增 **m2-6 补段**（reindex/reembed 蓝绿执行体+members/values CRUD——_m2-plan 段序已更新 m2-4→m2-6→m2-5）；边界4/5 v1.9.3 已登记
- **docs 批随 R2 commit 入库（coder 原样 commit）**：docs/TEST-CASES.md（v1.9.3）、RUNBOOK.md（§4 月库口径）、.opencode/workflows/_m2-plan.md（m2-6 段）

**口径与边界**：

- C 组记录项（m2-2「记录不修」清单）仍按所属段处理，本段不强制；G-15/G-16（m2s-1 登记）不涉本段
- **分层纪律**：core 不碰 SQL；api 层薄编排；权限装饰器/审计 outbox 调用面沿既有惯例
- design/requirements 正文**禁改**；TEST-CASES/RUNBOOK 回写由 supervised-coding 落笔（B3 的 RUNBOOK 注记同）
- m2-4（SSO/委托 token）不在本段；语义端点（m2s-1 已交三端点；builds 面上归 m2s-2）
- TC-OPS-03/06/07/08、T20 半句、TC-EMB-06 以 TEST-CASES 原文为唯一口径（L479-507/L674/L220）
- commit 格式 `[task-knowledge-lattice-m2-3] R<n>`，develop_opencode 分支（先 ff 至 origin/develop=428c67f），commit 前同步 origin/develop，不 push
- 新测试文件模块前缀（admin_/ops_/csv_ 等），新建前 `git ls-files tests/` 查同名
- 门禁基线 **911+1 双后端双模式 0 skipped**（m2s-1 终态）——零回归硬约束

**验收标准**：

- **TC-OPS-03** 审计分级（org_admin 全量/系统管理员仅元数据/他组织拒绝——双后端）
- **TC-OPS-06** CSV 批量导入（500 行幂等替换/org 列一律拒绝/sync 不动/孤儿拒绝/二跑零差异——双后端）
- **TC-OPS-07** 维度退役与取值停用治理（dry_run 影响面/二次确认/审计/T20 半句——双后端）
- **TC-OPS-08** grants 全量替换（local 替换 sync 不动/expires_at——双后端）
- **TC-EMB-06** 重嵌入入口（API 触发 reembed 蓝绿流程——任务投递与进度面；双后端）
- 任务取消 API 端到端（触发→worker 取消语义——m2-1 机制衔接）
- 嵌入覆盖率面板（只读、口径 tombstone=0 且 version=active_version）
- **B1~B6 全部收编**（B2 链遍历+G-13 对冲、B3 月库纳入备份、B6 NULLS 修正+探针——各附测试）
- 最小 UI 三视图（i18n 双语、服务端不感知语言；TC-UI 组维持 manual 不进门禁）
- chore 归档批入库
- 门禁 911+1 起、双后端双模式全绿 0 skipped（新增用例计入）

## 需求确认

- [x] 用户已确认（2026-10-30 10:16 确认开工，status=implementing）
- 历史遗留事项清单：m2-2 移交 **B1~B6**（C 组豁免——按所属段）+ docs 批挂账（TEST-CASES v1.9.2/AGENTS.md/_m2-plan.md/m2s-1 检查点——chore 归档批承载）；m2s-1 移交项归 m2s-2/m2s-3（语义轨道）不并入本段

## 遗留事项（跨任务移交）

- [ ] **交付 chore 顺手（监督侧 docs-only，随检查点归档 commit）**：RUNBOOK §4.1 产物清单旧行删除合并；v1.9.3 版本行措辞「R2 批」→「R2/R3 批」；_m2-plan m2-6 行补 B5 登记项（read_monthly_events 读回行 row_hash 不自洽——消费者勿以读回行复算链）
- [ ] 移交 **m2-6**（R3 Committer P3 登记）：UI fresh 残余 UX（预填/逐行过期编辑/显示既有值/langchange 保留）；同秒 reembed 单调键；replace_local_grants 直调解析器对齐；read_org_audit 下沉；audit_chain 错误码；格式常量共享；协议 list docstring 字符串契约；API 级 pg diff 断言；ULID 字样注释×2；P3-1 值序反向锁死
- [ ] 移交 **m2-4**：无（token 交叉项原定）
- [ ] 无其他新增移交项（B1~B6 全部随本段清偿；G-15/G-16 归语义轨道）

## 轮次记录

- **R1**（coder ses_e7565e421ffeibNhg99G5B37wU，2026-10-30 11:10）：R1 commit `8289949`（21 files，+3865/−68）+ chore `787116c`（HEAD=787116c）。自测证据：门禁 `GATE PASS` **964+1 双模式 0 skipped**（pg 臂 344=311 参数化+33 专用；基线 911+1 零回归 +53 新用例）；TDD 红灯（B1 AttributeError/TC-OPS-07 7 failed/B3 KeyError）；UI playwright DOM 自测（五视图/三视图切换/EN 零裸中文/停用全链 0 error）。**实现决策注记**（待 Tester/Committer 关注）：① grants.expires_at 迁移无需——0001 既有列+过期触发器；② **CSV 导入语义=按用户全量替换**（CSV 出现的用户按行集全量替换、未出现用户不动——增量文件安全；export→import 往返幂等/二跑零差异/500 行 ✓；「组织级全量」口径需重裁定则申报）；③ B2 链遍历 walk_chain（prev_hash→row_hash 索引+逐行 canonical 重算；链头=prev 不在批内 hash 集；破链/分叉/孤儿/多链头 fail-closed AuditChainError；读 SQL 去 ORDER BY——shuffle/逆序恢复同序实证 G-13 对冲）；④ 审计分级：admin.py 原无审计查询本段新建；sysadmin 无成员关系可查（仅元数据）、兼任 org_admin 时全量优先；⑤ B4 stats 数据源=outbox 最近 maintenance.run→当月月库兜底；⑥ reindex/reembed=任务投递面（payload {org,embed_model}；reindex target_version=在用版本、reembed=None 全库；蓝绿执行体归后续段——TC-EMB-06 本段验收=API 触发与进度面）；⑦ 偏差申报：A5 取消端点 m2-1 已交付仅补联动测试；UI 权限视图成员清单从 export CSV 去重（未新造端点防越 design 端点表）；顺修 scripts/test_gate.sh 失败分支 `$log）` 全角括号 unbound 既有 bug（首次被失败路径触发）。

**R1 Tester**（ses_e75356242ffeqpGuedInlPvXe0，2026-10-30 11:35）：**testVerdict=PASS**（testedSha=787116c）。独立复跑门禁 964+1 双模式 0 skipped（pg 臂 344=311+33；911+53 净增闭合、零删除零弱化）；TC-OPS-03/06/07/08+T20 半句+TC-EMB-06（本段 API 面——越段项标注不判 FAIL）+取消联动+覆盖率全过；**B1~B6 逐项 ✅**（B2 独立 6 边界单测：空集/单行创世与月首外部 prev 不误报/乱序恢复/多链头/分叉/孤儿/篡改 fail-closed——canonical=10 语义列全量排除链键与排序键；B3 双后端恢复实证；B6 探针）。**口径模糊项 2（单列不判 FAIL，供 Committer 裁定）**：①TC-OPS-06「全量替换」语义面——按用户 vs 组织级，判别场景（CSV 外用户 local 行是否删除）用例无断言，两种语义下明示断言均满足；②TC-OPS-03 sysadmin 兼任 org_admin 全量优先——实现合理（内容权来自组织授权语境，FR-6 防的是无授权语境系统读取），建议 TEST-CASES 补口径登记。**文档挂账（监督侧待清偿）**：RUNBOOK §4 L125-128 未随 B3 更新（现文仍写「自动快照不含月库」与实现矛盾——任务书 C-B3 注记归监督侧落笔但未落，chore 批未携带；交付链 docs commit 补落沿 m2-2 6d223c0 先例）。备注：T20 审计挂治理路径（直接 SQL 不产审计——用例步骤语义即治理路径，可接受）；UI 无测试文件进门禁（manual 政策 ✓）；test_gate.sh 顺修零弱化。报告全文见「最新验证意见原文」。

**R1 Committer**（ses_e74efae1dffeocAwiS1Yfl3633，2026-10-30 12:38）：**reviewVerdict=NEEDS_CHANGES**（reviewedSha=null——R1 未通过；testedSha=787116c=HEAD 一致）。P1:0；**P2×4**：P2-1 CSV/PUT 授权重复行未处理 IntegrityError→500+部分生效（修复=解析期按 username,dim_key,value 去重+同值不同 expires 显式 400 报行号或明确 last-wins 同规则+PUT pydantic 模型校验+重复行用例）；P2-2 expires_at 无格式校验——sqlite 静默 fail-open（非法串写入 TEXT 列字符串比较恒真=临时授权变永久）/pg 500 跨方言不一致（修复=API 边界严格时间解析 400+双方言同口径测试）；P2-3 reembed 窗口进度取当前标签覆盖率而非任务目标标签（payload.embed_model 未用——旧标签 100% 时面板恒 N/N 与实际无关；修复=按任务 payload 目标标签算 embedding_coverage+执行体未落地前 done=0/not_started+测试改）；P2-4 TC-OPS-06/07/08 双后端证据缺口——4 个新 store 方法（list_grants_for_export/find_user_by_username/read_pending_outbox_events/read_last_maintenance_stats）零 pg 臂覆盖+test_ops_06 docstring 与事实不符（修复=R2 补 matrix 级用例+修 docstring）。**P3×17 记录级**（月库兜底取第一条/双源合并重复事件/limit 校验/dimension.* target 投影缺口/walk_chain 分叉多链头孤儿环无永久用例/org 头大小写绕过/非 UTF-8 CSV 500/backup stats 缺 audit_months 键/drill 脚本未含月库/sysadmin 用例断言缺口/断言重复行/maintenance.run 字面量回归/B5 重投影后 row_hash 不自洽注记/UI split(",") 解析+成员清单受限+EN 全角括号+后填不生效/审计仅当月无时间范围/全角括号根因存疑/pre-m2-2 无哈希月库行残留提示）。**两项口径裁定**：①TC-OPS-06=(a) **按用户全量替换成立**（用例④逐用户部分生效决定语义+与 PUT 原语同构+组织级误删风险——监督侧 TEST-CASES v1.9.3 落判别断言+「用户缺席=不动；清空走 PUT 空清单」口径）；②TC-OPS-03 sysadmin 兼任 org_admin 全量优先=**口径成立**（内容权来自组织授权语境，FR-6 防的是无授权语境系统读取——补口径登记+永久用例）。**边界问题 6 项**（1/2 需用户拍板落段，3~6 监督侧落笔）：①reembed/reindex 执行体无承接段（runner 不认领、202 后永久 pending——建议落 m2-5 或新段）；②members GET/values CRUD 未落段（UI 从 export CSV 反推成员；D19 重新启用取值无端点）；③停用影响面「维度写锁项」口径（v1.6.3 要求 vs 实现 docs 计数——裁定登记或 R2 补 locked_docs）；④/embedding-coverage 与 /stats 端点表回写+values PATCH 路径登记；⑤审计查询仅当月（无时间范围——登记已知范围）；⑥RUNBOOK+TEST-CASES v1.8.3 注记与 B3 实现矛盾（docs commit 补落——已定处置）。**关键面**：链遍历通过（含边界注记）/审计分级通过/同事务审计通过/CSV 核心通过输入校验不通过/UI/分层/门禁/chore 通过。报告全文见「最新验证意见原文」details 块（R1 Committer）。

**R1 裁定与 R2 启动**（2026-10-30 12:42 用户拍板「按建议的来」）：两口径裁定（TC-OPS-06=按用户全量替换 / TC-OPS-03 sysadmin 兼任全量优先）接受并落 TEST-CASES v1.9.3；边界1/2=**新增 m2-6 补段**（reindex/reembed 蓝绿执行体+members/values CRUD——段序 m2-4→m2-6→m2-5，_m2-plan 已更新）；边界3=locked_docs 字段并入 R2；边界4/5=v1.9.3 登记；边界6=RUNBOOK §4 已更新（监督侧落笔完毕）。监督侧 docs（v1.9.3/RUNBOOK/_m2-plan）随 R2 commit 入库。status=implementing（round=2）。

**R2**（coder ses_e7565e421ffeibNhg99G5B37wU 续接，2026-10-30 13:11）：commit **`6f7fbea`**（单 commit 含 docs 批——TEST-CASES v1.9.3/RUNBOOK §4/_m2-plan m2-6 段原样入库；19 files +879/−94，HEAD=6f7fbea）。**逐条修复对照**：P2-1 解析期按 (username,dim_key,value) 去重——同值同 expires 静默去重/不同 expires 400 报两行号+PUT GrantRow pydantic（缺键 422）+行内重复 400（部分生效根除）；P2-2 `_parse_expires_at` 库格式+ISO 8601 严格解析归一化、非法 400 带行号（PUT/CSV 共用；**fail-open 证伪用例**——非法串 count==0 零入列）；P2-3 端点按最近 reembed 任务 payload.embed_model 目标标签算 embedding_coverage+target_model 字段+执行体未起步 done=0+list_tasks ULID 次级排序键（同秒并列稳定）；P2-4 新文件 test_admin_store_reads.py（matrix 双臂——4 store 读方法+CSV 差异读路径）+test_ops_06 docstring 修正（pg 臂 344→351）；**边界3** locked_docs 双方言（组织内引用非 active 取值或 retired 维度取值的文档数——基线 2→retire 后 3→预估 4 逐级断言）；P3-1 月库兜底 reversed 取最后一条；P3-2 审计双源 id 去重月库优先（手工造崩溃窗 evt-dup==1）；P3-3 limit Query(ge=1,le=500)；P3-4 _target_of 映射 dimension_id；P3-5 walk_chain 分叉/多链头/孤儿/环/篡改 5 永久用例；P3-6 org 头名 strip().lower()；P3-7 UnicodeDecodeError→400；P3-8 backup stats 补 audit_months（pg 显式 None 分区口径注释）；P3-9 drill 脚本补月库快照/恢复断言（DRILL PASS）；P3-10 sysadmin evt-a3 排除+兼任永久用例；P3-11 重复断言行删；P3-12 maintenance.run 常量参数化（源码零字面量）；P3-14 UI 引号 CSV 解析+expires 保存时点统一+全角半角化（playwright 后填生效实证）；P3-13/15/16/17 不动（遵裁定）。**自测**：门禁 `GATE PASS` **994+1 双模式 0 skipped**（pg 臂 351=318+33；964+1→994+1 零回归 +30）；TDD 红灯（P2-1/2 批 8 failed、locked_docs KeyError、limit=0 返 200）；UI 回归后填生效；drill PASS。verdict 双置空待 R2 重验（R1 历史：testVerdict=PASS/testedSha=787116c——见上）。

**R2 Tester**（ses_e75356242ffeqpGuedInlPvXe0 续接，2026-10-30 14:10）：**testVerdict=PASS**（testedSha=6f7fbea）。独立复跑门禁 994+1 双模式 0 skipped（pg 臂 351=318+33；+30 逐文件对账闭合、tests 零删除）；修复项逐条 PASS——**独立加强**：P2-1 跨用户部分生效根除实证（前正常行零写入——解析期整批拒绝先于 apply）；P2-2 写路径面穷尽核阅（grants.expires_at API 写入口仅 PUT/CSV 两处共用解析器；store 直调不校验=内部协议信任面注记）；P2-3 同秒并列独立验证（ULID 次级排序键双方言对称实证）；locked_docs 异构造数独立复算一致（4）；P3-5 临时脚本转正式（cycle 用例 docstring 诚实标注 heads=0 结构拦截先行）。**口径裁定落地核对**：②sysadmin 兼任完整落地；①TC-OPS-06 语义成立但**判别断言「CSV 外用户 local 行原样保留」无永久 pytest 用例承载（D-1——TEST_BUG 类，语义实现两轮独立实证正确、缺回归网钉死，≈10 行；建议 R3 或显式接受）**。D-2：sysadmin 用例 docstring 措辞（member≠org_admin 断言有效）。docs 批核验与监督侧落笔一致（RUNBOOK 挂账已清偿）。报告全文见「最新验证意见原文」details 块（R2 Tester）。

**R2 Committer**（ses_e74efae1dffeocAwiS1Yfl3633 续接，2026-10-30 14:19）：**reviewVerdict=NEEDS_CHANGES**（reviewedSha=null——R2 未通过；R1 P2 闭环但 **R2 新引入 P2×2**）。**D-1 裁定=(a) R3 微补**（R3 本已因 P2 开启、10 行边际成本；m2-6 不保证触及 CSV import）。**P2×2**：P2-1 CSV dry_run 差异在 pg 把 datetime 与归一化字符串相比（current 取 list_grants_for_export 原值未归一——export 侧已归一但 diff 侧漏；pg 上非空 expires 恒报 changed/kept 丢失、二跑零差异在 pg 不成立；修复=current 按 _EXPIRES_LIB_FORMAT 归一或 store 统一返字符串+pg 可执行 diff 用例）；P2-2 **UI 保存把单框 expires 应用到全部选中行——静默清除既有临时授权（R1→R2 回归 fail-open**：选中受临时授权成员+切换任一 chip+空过期框保存→全部变永久；修复=原已存在 key 沿用 accessState.picked、仅新选中 key 应用输入框+playwright 断言）。**P3×15**（建议 R3 收 1/4/5/6/7/11/12——月库兜底假覆盖〔outbox 未过滤 ship 后三条仍在、reversed 未验证+硬编码 10-11 日期〕/协议 docstring 未同步 locked_docs·audit_months/「ULID 时间有序」注释不实〔uuid4 非单调——同秒仍可能取旧任务〕/orphan 用例实为 multi-head/locked_docs 未在 UI 展示/测试 docstring 残留×2/PUT 与 CSV 重复行语义不一致登记/iso 格式文案/pg 导出归一缺测/plan stale/replace_local_grants 信任面/UI 空行/空字段行口径）；P3-2/3 docs 两项归监督侧（v1.9.3 版本行 TC-OPS-05 注记与正文 L492 不符、RUNBOOK §4 产物清单缺月库 tar）。**R3 最小范围**：P2-1/P2-2/D-1 判别用例+顺手 P3-1/4/5/6/7/11；docs 修正归监督侧最终 docs commit。**round=3（maxRounds=3 最后一轮）**。报告全文见「最新验证意见原文」details 块（R2 Committer）。

**R3**（coder ses_e7565e421ffeibNhg99G5B37wU 续接，2026-10-30 14:37）：commit **`dcf3923`**（13 files +169/−40，含 docs 批原样——TEST-CASES TC-OPS-05 正文口径+v1.9.3 重复行语义句/RUNBOOK 产物清单/_m2-plan stale 行，HEAD=dcf3923）。**逐条修复对照**：P2-1 **list_grants_for_export 双方言统一返回库格式字符串**（pg 内 strftime 归一——store 单点收口、export/diff/审计消费面同源比较；export 侧死分支清理）——pg 臂证伪→修复对照（修前 datetime!=str 2 failed→修后 37 passed）+diff 幂等双臂用例；P2-2 **fresh 集方案**（装载态 picked=库内既有 expires+fresh 清空；toggle 仅显式〔重〕选中标 fresh；save 未动 key 沿用库内值、fresh key 应用输入框——「不动=不变，动=显式」）——playwright 前后对照（R2 代码临时授权被清→R3 CN 2027-06-30 保留+OS 空=显式新选）；D-1 判别用例 `test_csv_import_users_absent_local_rows_untouched`（CSV 仅含 u_cn→u_full local 行逐值保留）；P3-1 月库兜底真覆盖（DELETE outbox maintenance.run+当月派生日期——时间炸弹根除）；P3-4 协议 docstring 补 locked_docs/audit_months；P3-5 ULID 注释改实（uuid4 非单调=确定性 tiebreak；同秒歧义登记 m2-6）；P3-6 真 orphan 用例（主链+不相交环触发 len 分支）+multi-head 改名注记；P3-7 UI locked_docs 展示+i18n 键；P3-10 pg 归一测试（同批）；P3-11 docstring 残留×2 修正。**自测**：门禁 `GATE PASS` **1000+1 双模式 0 skipped**（pg 臂 353=320+33；994+1→1000+1 零回归 +6）。verdict 双置空待 R3 重验（R2 历史：testVerdict=PASS/testedSha=6f7fbea——见上）。

**R3 Tester**（ses_e75356242ffeqpGuedInlPvXe0 续接，2026-10-30 14:56）：**testVerdict=PASS（收敛——建议放行交付）**（testedSha=dcf3923）。独立复跑门禁 **1000+1 双模式 0 skipped**（pg 臂 353=320+33；+6 闭合、三轮零删除零弱化）；修复项逐条 PASS——**独立证伪级验证**：P2-1 消费方穷尽核阅（全仓仅 export/diff 两处消费、无第三处 datetime）+pg 臂独立构造（changed==[]/kept==1+方向性 changed 恰含该键——值级比较非恒等）；P2-2 playwright 三场景独立实证（不动 chip 保存临时授权保留/重选+空框=显式转永久两步显式动作/非 fresh 不应用输入框——R2 回归修复+用户意图表达无静默面）；D-1 真实造数逐值断言（v1.9.3 判别断言自此有门禁承载）；P3-1 独立加强（payload 值与时间序反向→取链序最近非值最大——排除假实现）。**三轮轨迹**：964→994→1000 单调递增；两口径裁定「用例文字+测试承载」双面闭环；文档链闭环（R1 挂账 R2 清偿、D-2 措辞 R3 修正）。**登记项不阻断**：N-1 同秒 reembed 歧义（m2-6）/N-2 replace_local_grants 直调解析器（m2-6）/N-3 宽松双分支写法微注记。报告全文见「最新验证意见原文」details 块（R3 Tester）。

**R3 Committer 终审**（ses_e74efae1dffeocAwiS1Yfl3633 续接，2026-10-30 15:02）：**reviewVerdict=APPROVED**（reviewedSha=dcf3923=testedSha=HEAD 三一致——docs 批已含于 R3 commit 无需补轮）。P1:0 P2:0；**P3×10 登记放行不突破 maxRounds=3**：①RUNBOOK §4.1 产物清单旧行残留（监督侧交付 chore 顺手）②B5 读回行 row_hash 不自洽未入 m2-6 登记（补）③「ULID」注释字样（实为 uuid4——注释级）④P3-1 用例值序与时间序同向未锁死 reversed+双分支写法松⑤UI fresh 残余 UX（不预填/不显示既有值/langchange 清空——m2-6）⑥格式常量双源（store strftime 字面量 vs api _EXPIRES_LIB_FORMAT）⑦协议 list_grants_for_export 字符串契约 docstring ⑧API 级 pg diff 断言（现 store 级+Tester 临时验证）⑨测试注释 ULID 字样 ⑩v1.9.3 版本行「R2 批」措辞（实 R2/R3 两批）。**关键面**：P2-1 通过（store 单点归一优于 api 归一——datetime 不外泄、三消费面同源、created_at 先例一致）；P2-2 通过（fresh 集「不动=不变，动=显式」、静默清除根除、两步显式可接受）；D-1 闭环；零回归（964→994→1000 单调、零删除零弱化）。**双通过达成（round=3 收敛）**。交付前置两件：检查点入库+manifest（若 chore 推进 HEAD 按 m2-2/m1-4 先例记 reviewedSha=docs-only HEAD、testedSha 保持 dcf3923）；supervised-coding.md 不入库。报告全文见「最新验证意见原文」details 块（R3 Committer）。

**交付链**（2026-10-30 15:06 用户确认交付）：① 监督侧 docs nit 落笔（RUNBOOK §4.1 旧行合并/v1.9.3 版本行 R2→R2·R3 措辞/_m2-plan m2-6 行补 B5 登记）+ 检查点归档 docs-only commit（reviewedSha 按 m2-2/m1-4 先例更新为归档 HEAD、testedSha 保持 dcf3923）→ ② Coder push+PR → ③ Committer 留痕 → ④ manifest → ⑤ 待用户合入。

**交付链执行**（2026-10-30 15:12 三步完毕）：① 监督侧 docs nit 落笔+归档 commit **`6633914`**（docs-only——reviewedSha 按先例更新、testedSha 保持 dcf3923；push b82a723..6633914）；② **PR #5**（base=develop，5 commits，OPEN）；③ Committer 评审留痕 **PRR_kwDOVZ9dhM8AAAABVEqvmQ**（2026-10-30T07:10:51Z，COMMENTED 载体正文首行 APPROVED）；④ evidence manifest 入 PR description（15 键——双 SHA/门禁四段基线/rounds=3/specRulings×4/handover，校验通过）。**待用户合入指令**（不自动合入）。

**合入完成**（2026-10-30 15:14 用户指令「合入」）：`gh pr merge 5 --merge` → **MERGED**，mergeCommit **`ad5ab2ae9f434cdaf33e1597105d43ec0d1b22dd`**；origin/develop 428c67f→ad5ab2a，本地 develop_opencode 已 ff 同步。收尾：检查点 status=done；TEST-CASES v1.9.4（§六 M2 行 m2-3 段完成态——工作区随下段 chore 批）；_m2-plan/AGENTS.md 进度更新。任务闭环（3 轮，911+1→1000+1）。

## 最新验证意见原文

- （待填）

<details>
<summary>R1 Tester 报告全文（2026-10-30 11:35，testVerdict=PASS）</summary>

# m2-3 段 Tester 独立验证报告

**testedSha**: `787116c04c9ff62db0b9b6ee49b421801f1a4cf8`（develop_opencode；R1=8289949 + chore=787116c，增量 428c67f..787116c 25 文件 +3865/−68）

## testVerdict: **PASS**

## 1. 执行的验证（全部独立复跑，未采信 coder 自测）

| 验证 | 命令/方式 | 结果 |
|---|---|---|
| 新测试快速臂（无 DSN） | `uv run pytest tests/test_ops_{03,05,06,07,08,chain_read}*.py tests/test_admin_manage.py` | 42 passed + 20 skipped（skip 全为 pg 臂待 DSN，门禁实跑） |
| Tester 独立验证 ×6（临时文件，验后已删） | sysadmin 兼任/越组织过滤、CSV 增量语义、export→import 往返、walk_chain 6 边界、canonical 字段集 | **6/6 passed** |
| **全量门禁** | `docker start lattice-pg && export LATTICE_PG_DSN=… && scripts/test_gate.sh` | **GATE PASS：双模式各 `964 passed, 1 deselected, 0 skipped`；pg 臂 344（311 参数化 + 33 专用）全实跑** |
| UI DOM 独立抽查 | 临时 uvicorn + playwright-cli（5 视图/EN 切换/裸中文扫描） | 三视图切换 ✓、`lang=en`+title 同步 ✓、EN 态零裸中文 ✓、console 仅 favicon 404（无害） |
| 门禁期间 skip 逐个核对 | summary 行审查 | **0 skipped**（1 deselected = TC-UI manual 组，政策内不进门禁） |

## 2. 分用例判定表

| 用例 | 判定 | 证据摘要 |
|---|---|---|
| **TC-OPS-03**①②③（L479） | ✅ PASS | `test_ops_03_audit_access.py` 4 用例（双源合并/org 过滤/403 面）随门禁双后端双模式过；②断言 detail_json 逐键剥离、含查询词 payload（"增值税税率"）；③ u_gl_admin 查他组织 403 + 查己组织全量 |
| TC-OPS-03 注记④（sysadmin 兼任） | ✅ 口径核验通过（见审查面④） | 独立测试：兼任 org_admin → `scope=full` 含 detail_json；纯 sysadmin 无成员关系查他组织 → `scope=metadata` + **只见该组织事件**（越组织过滤独立验证） |
| **TC-OPS-06**①⑤（L494） | ✅ PASS | 500 行 dry_run→生效→落库核对（`applied_users==500`）；二跑 dry_run added/removed/changed 全空 + `kept==2`；生效二跑数据恒定 |
| ②②'（org 列 A-12） | ✅ PASS | org 列一致/不一致均 400 整批拒绝 + 零写入断言 |
| ③ sync 不动（T-CSV） | ✅ PASS | CSV 后 `('region','CN','local')+('region','OS','sync:hr')` 并存逐行断言 |
| ④ 无成员关系拒绝该行 | ✅ PASS | u_orphan/u_missing 双形态 rejected、其余用户照常（applied_users==1）、零孤儿授权 |
| **TC-OPS-07**（L499） | ✅ PASS | dry_run 影响面（docs=2/grants=6/users=6）不落库零审计；确认生效=T3 联动（read_grants 收紧 + compile_acl `rule.is_empty`）+ 审计同事务 + 幂等零重复审计；retire 二次确认门/409/审计/产物条件消失 |
| **T20 半句**（L674） | ✅ PASS | 存量 `test_matrix_t20_t22.py` 全四断言零改动仍过（含④检索面 `_visible` 回基线）；`test_ops_07` 补退役路径审计半句（走 retire_dimension，outbox `dimension.retire`==1） |
| **TC-OPS-08**（L504） | ✅ PASS | local 全换（CN→OS+CIT）/sync:hr 原样/expires_at 落列/read_grants 展开即时生效（CIT+VAT 并存）/outbox `grants.replace`==1；REST 403/400 面；幂等与空清单清空 |
| **TC-EMB-06**（L220，本段 API 面） | ✅ PASS（越段项标注） | reindex（target_version=在用版本）/reembed（payload=`{org,embed_model}`、target_version=None 全库）202 + 任务行断言；owner/org_admin 双通、无关成员 403、404。**越段项**（蓝绿执行体/原子切标签/旧标签清理/quality·semantic_build 重跑）归后续段，不判 FAIL（R1 注记⑥与任务书口径一致） |
| 任务取消联动 | ✅ PASS | 投递→cancel→`failed`+`cancelled:` 前缀 + 幂等不复活；runner `CLAIMABLE_TASK_TYPES=("ingest","maintenance","semantic_sync")` 不认领 reindex/reembed（原地 pending，源码核阅）——不影响既有门禁用例（964 全绿实证） |
| 嵌入覆盖率面板 | ✅ PASS | 分母=在用块（tombstone/pending 版本块不计入）、分子限当前标签、旧标签不计 done、reembed 窗口进度=任务行+全局闭合口径；只读（GET 零写入）、非 admin 403 |

## 3. B1~B6 逐项结论

| 项 | 判定 | 独立证据 |
|---|---|---|
| **B1** upload.reclaim 常量化 | ✅ | 常量登记 + `__all__` + credentials.py 源码级零字面量断言；功能侧 purge_expired→outbox 事件面闭环 |
| **B2** prev_hash 链遍历 | ✅ | 读 SQL 已去 ORDER BY（双方言源码核阅）；shuffle/逆序恢复插入序；破链 fail-closed；独立 6 边界单测全过：**空集/单行（创世空串与月首外部 prev 均单链头不误报）/乱序恢复/多链头/同 prev 分叉/孤儿/哈希篡改**。canonical 字段集=`_CHAIN_FIELDS` 10 语义列**全量**（排除 prev/row_hash 链键与 seq/rowid 排序键）——审查面③两项均确认 |
| **B3** 月库纳入备份 | ✅ | sqlite tar 含 `audit_*.db`+`-wal/-shm`+`*.seal.json`（解包行数=源）；pg 分区口径实证（dump→restore→链读 2 行在场）双后端 |
| **B4** stats 面板 | ✅ | GET /stats 含 `audit_outbox_trimmed==3` 新键（outbox 最近 maintenance.run 数据源）；403 面在场 |
| **B5** R1 期行 detail_json 兜底 | ✅ | 语义列缺省行读路径重投影（org/actor/target 恢复）、已投影行不覆盖（对照组断言） |
| **B6** pg last_row_hash NULL seq | ✅ | `WHERE seq IS NOT NULL`+`ORDER BY seq DESC` 修正；显式 NULL seq 探针（不误取 + 读路径全量链序正确）；sqlite rowid 序回归同测 |

## 4. 重点审查面结论

- **② CSV 语义独立裁定**：实现=「按用户全量替换」（CSV 出现用户按行集替换、未出现用户不动）。以独立测试实证增量文件行为（CSV 外用户 u_full 的 local 授权原样保留）。**裁定意见**：TC-OPS-06/T-CSV 的全部**明示**断言（幂等、二跑零差异、500 行、sync 不动、export→import 往返零差异、防孤儿）在两种语义下均满足——用例「幂等全量替换」句未断言「CSV 外用户的 local 行是否删除」这一**判别性场景** → **口径模糊，不判 FAIL**，供 Committer 裁定：若认定「全量=组织级」，需改实现语义并在用例补判别断言（用例=需求，改动须经 Committer 审）。
- **④ 审计分级 sysadmin 兼任**：实现口径（有本组织 org_admin 成员关系 → 全量优先；纯 sysadmin → 仅元数据）与 FR-6 不构成冲突面——内容读取权来自组织 admin 授权语境，「仅元数据」防的正是**无授权语境的系统性内容读取**；③拒绝面未破坏。用例②步骤语义=「无成员关系的系统管理员查询」。建议监督侧在 TEST-CASES TC-OPS-03 落一行口径登记（**非决策变更**）。
- **⑥ reembed 投递面**：payload/任务行/进度联动齐全；runner 不认领为显式设计（claim 过滤），门禁零回归实证无影响。
- **⑦ UI/manual 政策**：tests/ 无 UI 测试文件，门禁 `-m "not manual"` 且 TC-UI 组维持 manual 标记——UI 不进门禁 ✓。test_gate.sh 顺修仅两处 echo 文本 `$log`→`${log}`，失败分支退出/skip 拦截/pg 臂在场断言逻辑**零改动，不弱化** ✓。
- **分层**：audit_chain.py 纯计算零 SQL（源码核阅）；新 SQL 全部落 store/ 双方言对称实现；api/admin.py 薄编排（权限装饰 `org_admin`/`owner_or_admin` 沿惯例）；disable/retire/grants.replace 审计均与写**同事务**（BEGIN…COMMIT 内 outbox_insert，双方言对称）。
- **安全门控**：CSV 导入导出/reembed/reindex/覆盖率/stats/维度治理=org_admin（owner_or_admin 仅文档级 reindex）——各端点均有 403 断言；审计查询 org_scoped+双源 org 过滤，sysadmin 越组织查询独立验证只见目标组织。

## 5. 与 coder 自测对账

| 项 | coder 自报 | 独立复跑 | 一致性 |
|---|---|---|---|
| 门禁 | 964+1 双模式 0 skipped | **964 passed + 1 deselected（manual）× 2 模式，0 skipped** | ✅ 逐字一致 |
| pg 臂 | 344 = 311 参数化 + 33 专用 | 344 = 311 + 33 | ✅ |
| 增量 | 基线 911+1 零回归 +53 | 新测试文件收集 62 条 − test_ops_05 m2-2 期存量 9 条 = +53 净增；911 基线用例全量在场（`--diff-filter=D` 零删除、唯一 M 文件 test_ops_05 为追加） | ✅ 闭合 |
| TDD 红灯/UI DOM 自测 | 申报 | 不采信——以门禁复跑与 playwright 独立抽查替代 | ✅ 行为等价复现 |

## 6. 缺陷清单

**FAIL 项：无。**

**口径模糊/待裁定项（单列，不算 FAIL）**：
1. **TC-OPS-06 全量替换语义面**（按用户 vs 组织级）——判别场景用例无断言，证据见 §4②，供 Committer 裁定。
2. **TC-OPS-03 sysadmin 兼任 org_admin 全量优先**——实现合理、用例未覆盖此场景，建议补一行口径登记（非决策变更）。

**文档挂账（监督侧待清偿，非 coder 验收面）**：
3. **RUNBOOK §4 L125-128 未随 B3 更新**：现文仍写「自动快照**不含**月库文件……自动快照纳入月库随 m2-3 收编」——实现已收编（backup.py + 双测试），文档与实现矛盾（运维误导风险）。检查点 D 组明确该注记归监督侧落笔、chore 批未携带。**建议本段收口时补落**。

**备注（非缺陷）**：
4. T20「退役必审计」挂治理路径（retire_dimension），直接 SQL UPDATE status 不产生审计——用例步骤④语义即治理路径（dry_run+确认+审计），可接受；若要求 DB 层强制属决策变更。
5. ops 视图 console 仅 favicon.ico 404——无害。

---

**结论**：m2-3 R1 交付在 TEST-CASES.md 验收口径内全部成立——**testVerdict: PASS**，testedSha=`787116c`。验证过程中新增的独立测试文件已删除，工作区已还原（`git status` 仅存监督侧既有工作区状态），仓库零残留。

</details>

<details>
<summary>R1 Committer 报告全文（2026-10-30 12:38，reviewVerdict=NEEDS_CHANGES）</summary>

## 审查基线核对（R1 首轮）

- 审查对象：`HEAD=787116c`（R1=`8289949` + chore=`787116c`），基线 `428c67f`（m2s-1 合入）→ 增量 25 文件 +3865/−68，与检查点 `filesChanged` 逐项吻合；无上一轮 reviewedSha（本任务首轮），无历史意见处置项。
- chore `787116c` = 4 文件（TEST-CASES v1.9.2 / AGENTS.md / `_m2-plan.md` / m2s-1 检查点），**不含 `supervised-coding.md`**；工作区仍有该文件 M 状态（监督侧，未入库）——交付时须继续排除。
- 测试门禁：diff 中测试**零删除、零 skip、零断言放宽**（tests 全部 +1557、无 `skip/skipif/xfail`）；`scripts/test_gate.sh` 仅两处 echo 文本。
- 门禁计数采信 Tester 独立复跑（964+1 双后端双模式 0 skipped，pg 臂 344=311+33）；本轮不重复跑门禁，做语义抽查。

## 一、问题清单（P1/P2/P3）

### P1（阻塞）：无

### P2（须 R2 修复，不宜放行）

**P2-1｜CSV/PUT 授权重复行 → 未处理 IntegrityError → 500 + 部分生效**
`src/knowledge_lattice/api/admin.py:229-231`（PUT 行构造）、`:374-388`（CSV 逐用户 apply）；`store/sqlite/backend.py:1987-2005`、`store/postgres/backend.py:2251-2275`（先删后插，PK=(user_id,dimension_id,value_id)）。
同一 `(username, dim_key, value)` 在 CSV 出现两次（或 PUT 里出现两次）时，`target` 字典去重（dry_run 干净），apply 阶段第二条 INSERT 违反主键 → 两方言均抛 IntegrityError，API 只捕 `KeyError` → 500；CSV 前序用户已提交（部分生效），与 dry_run 预览不一致。
**修复建议**：解析期按 `(username,dim_key,value)` 去重并校验（同值不同 expires 显式 400 报行号，或明确 last-wins 且 dry_run/apply 同规则）；PUT 行用 pydantic 模型校验（缺键当前也是 500）；补重复行用例。

**P2-2｜`expires_at` 无格式校验：sqlite 静默 fail-open、pg 500（跨方言不一致）**
`src/knowledge_lattice/api/admin.py:293`（CSV）、`:229-231`（PUT）；`store/sqlite/backend.py:1987-2005`。
非法时间串在 sqlite 被原样写入 TEXT 列，`read_grants` 按字符串比较（`'abc' > '2026-…'` 为真）→ 临时授权被当成永久授权（安全语义失败开放）；pg 则因 TIMESTAMP 类型转换报错 → 500。
**修复建议**：API 边界（PUT/CSV 共用）解析 `expires_at` 为严格时间格式（或 pydantic datetime），非法 → 400；两方言同口径补测。

**P2-3｜reembed 窗口"进度"取的是当前标签覆盖率，不是任务目标标签**
`src/knowledge_lattice/api/admin.py:452-460`。
`reembed.done/total = 当前 settings.embed_model_label 的全局在用块覆盖率`；蓝绿窗口开始时旧标签覆盖率通常是 100%，面板会显示"reembed 窗口 · N/N"，与实际重嵌入进度无关；任务 payload 里明明带着 `embed_model` 目标标签却未使用。`test_admin_manage.py:184-187` 只断言 `total`，把错误口径固化。
**修复建议**：从最近 reembed 任务 `payload.embed_model` 取目标标签，用 `embedding_coverage(org, target_label)` 计算 done/total；执行体未落地前至少返回 `done=0/not_started`，不要把旧标签覆盖率当进度；同步更新测试。

**P2-4｜"TC-OPS-06/07/08 双后端"证据缺口：新增 4 个 store 方法无 pg 臂覆盖；测试 docstring 与事实不符**
`tests/test_ops_06_csv_grants.py:13`（声称"diff 语义断言双后端经 store 方法承载"，文件内无任何 matrix 用例）；`store/*/backend.py` 新方法 `list_grants_for_export`、`find_user_by_username`、`read_pending_outbox_events`、`read_last_maintenance_stats` 全库仅 api 层调用（grep 无 tests 直接引用）→ pg 实现零回归网；验收句明确"双后端"。
**修复建议**：R2 补 matrix 级用例（至少 export/list/find/pending/maintenance 五法 + CSV 差异所需读路径），修正 docstring；这与 Tester 的独立临时测试不冲突，但临时测试不构成门禁。

### P3（记录级，不阻塞；建议随 R2 顺手或登记）

1. `store/sqlite/backend.py:2105-2111`、`store/postgres/backend.py:2374-2380`：月库兜底分支按链序（旧→新）遍历后**取第一条** `maintenance.run`，与"最近一次"矛盾（outbox 分支取最新）——改为取最后一条；补 fallback 用例。
2. `src/knowledge_lattice/api/admin.py:497-507`：sqlite 两步搬运崩溃窗（月库已插、shipped_at 未回填）下，`pending outbox + 月库` 双源合并会**返回同一事件两次**；按 id 去重（月库优先）。
3. `src/knowledge_lattice/api/admin.py:472,506`：`limit` 未校验——`limit=0` 时 `rows[-0:]` 返回全量，负数语义异常；用 `Query(100, ge=1, le=500)`。
4. `src/knowledge_lattice/store/audit_chain.py:85`：`dimension.*` 的 target 投影读取 payload `target_id`，但本段两个治理事件写的是 `dimension_id/value_id` → target 列为空（语义列投影缺口）；对齐映射或 payload。
5. `tests/test_ops_chain_read.py`：`walk_chain` 仅覆盖哈希篡改；**分叉/多链头/孤儿/环**的 fail-closed 分支无仓内回归用例（Tester 的 6 边界测试是临时脚本）——建议补永久用例（任务书"B2 各附测试"）。
6. `src/knowledge_lattice/api/admin.py:277-283`：A-12 org 列检查为大小写敏感且未 strip，`Org` / ` org ` 头会绕过（虽被忽略，但与"一律拒绝"口径有缝）；头名规范化后再判。
7. `src/knowledge_lattice/api/admin.py:316`：非 UTF-8 CSV 触发 `UnicodeDecodeError` → 500；捕获后 400。
8. `src/knowledge_lattice/worker/maintenance.py:134`：backup stats 只回传 `database/objects`，新 `audit_months` 产物从运维面板不可见；补键（B3 可发现性）。
9. `benchmarks/dr_ops05_drill.py:96`：演练脚本仍只快照主库+objects（未传 `db_dir`），已不反映 B3 生产备份范围；docs/benchmark 批或 R2 更新。
10. `tests/test_ops_03_audit_access.py:102-112`：sysadmin 元数据用例未断言 `evt-a3`（他组织）被排除；补断言。另 sysadmin 兼任 org_admin 的组合角色无永久用例（口径裁定二）。
11. `tests/test_ops_chain_read.py:148-149`：同一断言重复两行（拷贝残留）。
12. `src/knowledge_lattice/store/{sqlite,postgres}/backend.py`：B4 新 SQL/比较 reintroduce `'maintenance.run'` 字面量，与 B1 常量化方向相悖；用 `EVENT_MAINTENANCE_RUN`（SQL 走参数）。
13. `store/*/backend.py read_monthly_events` + `audit_chain.backfill_semantic_cols`：返回行经 B5 重投影后 `row_hash` 与字段不再自洽——任何"读回再验链"的消费者会误报；文档注明或返回 raw/投影双份。
14. `web/app.js:177-183`：导出 CSV 用 `split(",")` 解析（未处理引号/逗号字段），且成员清单仅来自本地授权（sync-only/无授权的成员无法在 UI 选到）；`:440` EN 态仍用全角括号；`:231-236` 过期时间单输入框只在点击 chip 时取值（后填不生效）。最小 UI 可接受，建议登记后续 members 端点落地时替换。
15. `src/knowledge_lattice/api/admin.py:497-507`：审计查询只读**当月**月库，无时间范围参数（历史月不可查）——当前需求未明示历史查询，建议在 TEST-CASES 登记口径。
16. `scripts/test_gate.sh:54,68`：仅 echo 文本、门禁语义零弱化已确认；但"`$log）` 全角括号 unbound 既有 bug"这一根因存疑（bash 变量名不含全角标点，两种写法等价），改动无害、不影响放行，建议不再据此宣称修复。
17. 残留提示（非本轮缺陷）：pre-m2-2 无哈希月库行会被 `walk_chain` fail-closed；m2-2 检查点已记录"POC 无生产存量"，若将来迁移存量数据需补链或容错方案。

## 二、两项口径裁定（必答）

### 裁定 1：TC-OPS-06「全量替换」= **（a）按用户全量替换成立**

依据：
1. **用例④决定语义**：TC-OPS-06④"目标用户无有效成员关系 → 拒绝该用户行（防孤儿授权），其余用户照常"——这是逐用户部分生效；组织级"全量替换"无法在部分行被拒时仍保持"全量"自洽。
2. **与设计原语同构**：`PUT /members/{id}/grants` 已是"授权全量替换（只替换 local、sync 不动）"；CSV 是同一原语的批量载体，T-CSV 的"local 授权按 CSV 替换"对 CSV 中出现的用户成立。
3. **运维安全直觉**：500 行增量文件 vs 组织 2000 用户——组织级替换会把 CSV 未出现的所有用户 local 授权静默清空，仅为一次 dry_run 预览不足以承担该不可逆面；默认必须是"未出现用户不动"。
4. **限制须登记**：该语义下"清空某用户全部 local 授权"无法用 CSV 表达（需 PUT 空清单，已支持并测试）。因此监督侧需在 TEST-CASES v1.9.3 落两笔：①补判别断言"CSV 外用户 local 行原样保留"；②登记"用户缺席=不动；清空走 PUT 空清单"的运维口径（非决策变更）。若改（b）组织级，则须改实现+全部用例并接受上述误删风险——我不建议。

### 裁定 2：TC-OPS-03 sysadmin 兼任 org_admin"全量优先"= **口径成立，无须改实现**

依据：FR-6 的分级是"**org_admin 本组织全量 / 系统管理员仅元数据**"；sysadmin 在被查组织同时具备 org_admin 成员关系时，其内容读取权来自组织授权语境，不是"无授权语境的系统读取"，与 FR-6 不冲突。实现只在**路径解析出的组织**内按成员关系判 full；sysadmin 兼任 A 组织 admin 去查 B 组织仍是 metadata（③拒绝面未破坏），Tester 独立测试亦验证。需监督侧在 TEST-CASES TC-OPS-03 补一行口径登记（非决策变更），并建议补永久用例覆盖"兼任"与"sysadmin 跨组织只见目标组织事件"。

（未收到 CASE_BUG 裁定请求，本节即两项口径裁定。）

## 三、关键面显式结论

- **B2 链遍历：通过（含边界注记）**。链头=prev 不在本批 row_hash 集，月首外部 prev、创世空串、空批/单行均正确；canonical=10 语义列，正确排除 `prev_hash/row_hash` 与 sqlite rowid / pg seq 排序键，未来加列受冻结 docstring 约束；哈希不符/分叉/多链头/孤儿/环均 fail-closed。合法数据误报面：空批/单行/跨月/封存后 append 均无问题（封存月由 pending 跳过+0444/触发器双保险）；唯一理论误报是 pre-m2-2 无哈希月库行（POC 无生产存量，登记即可）。AuditChainError→FastAPI 500 属 fail-closed，异常消息含 head 数/id/哈希前缀，日志可定位；无结构化错误码（P3 建议加 `code=audit_chain_broken`）。B5 在链验证后投影、已投影行不覆盖，顺序正确；但返回行不再可复算（P3 注记）。
- **CSV 健壮性：核心通过、输入校验不通过**。引号/换行/BOM（utf-8-sig）由 csv 模块处理，SQL 全参数化（无注入面），500 行性能与 dry_run/生效两阶段、A-12 整批拒绝零写入均成立；但重复行 500、expires 未校验、非 UTF-8 500、org 头大小写/空格绕过（P2-1/P2-2/P3）。
- **审计分级：通过**。org_admin 本组织 full（含 detail_json）、纯 sysadmin metadata（detail_json 剥离）、他组织 org_admin/普通成员 403 均成立；剥离面枚举完整（detail_json 是唯一承载查询词/命中的列）。org 过滤在 Python 读后统一做——月库天然全组织、pending outbox 也是全组织，当前无泄露面（过滤在返回与剥离之前），但建议后续把 org 条件下沉到 pending outbox 读取并集中为 `read_org_audit`（P3）；补 sysadmin 跨组织排除断言（P3）。
- **同事务审计：通过**。disable/retire/grants.replace 均 BEGIN…COMMIT 内插入 outbox，异常 rollback；双方言对称（sqlite BEGIN IMMEDIATE / pg BEGIN）；dry_run/未确认路径零写入零审计；幂等重复操作零新审计。测试有状态+outbox 双断言，非恒真。
- **B1/B3/B4/B5/B6**：B1 常量登记+调用面源码断言 ✓；B3 月库 tar（含 -wal/-shm/seal sidecar）+ pg dump 恢复实证 ✓（drill/stats 可见性 P3）；B4 新键入 outbox stats 与面板 ✓（fallback 取旧值 P3）；B5 兜底 ✓；B6 `WHERE seq IS NOT NULL` + NULL seq 探针 ✓。
- **分层**：`audit_chain.py` 纯计算零 SQL ✓；新 SQL 全部落 store 双方言 ✓；core 零新 SQL ✓；api 层 CSV 差异/逐用户编排偏厚（约 100 行业务逻辑在 API），可后续下沉为 core/admin 服务（P3）。
- **UI**：未新增 design §6.2 之外的端点（成员清单取 export CSV 的注记⑦**可接受**——无越表端点；但 UI 选不到"无 local 授权的成员"，且 `members/values` CRUD 端点后续仍需落段）；新 i18n 键中英齐全、动态文案均走 `t()`；所有服务端/DOM 注入面均经 `esc()`/`textContent`（XSS 面通过）；服务端错误文案在 EN 态仍为中文属 FR-8 允许。无截图类证据需 Vision 核对（Tester 已做 DOM 抽查；TC-UI manual 政策不变）。
- **test_gate.sh**：仅两处失败分支 echo 文本，失败退出/skip 拦截/pg 臂在场断言零改动，**门禁语义零弱化**。
- **chore**：内容与 D 组一致、无 supervised-coding.md、docs-only；通过。

## 四、需求边界问题（不计 P 分级）

1. **reindex/reembed 执行体无承接段**：`worker/runner.py:60` 明确不认领 reindex/reembed，本段只做投递面；`/reindex` 202 后任务永久 pending，TC-EMB-06 的蓝绿执行体/原子切标签/旧标签清理/quality·semantic_build 重跑在 `_m2-plan`/检查点遗留中**没有落段归属**。建议监督侧把"reembed 执行体 + reindex 执行器"登记到 m2-5 或新段，并在检查点遗留事项落笔——否则 M2 "含换模型重嵌入流程"无法诚实勾验。
2. **§6.2 的 members GET / values CRUD 未落段**：UI 只能用 export CSV 反推成员（注记⑦），D19 软停用的"重新启用取值"恢复路径无端点（当前 PATCH 只接受 disabled）；建议登记到后续管理面 CRUD 段（m2-4/m2-5 或新段）。
3. **TEST-CASES v1.6.3（版本行）要求 M2 停用取值 dry_run 影响面"须含维度写锁项"**；实现影响面只有 docs/grants/users（`docs` 数量在语义上≈被锁文档数，但未单列）。请监督侧裁定登记"docs 即写锁面"或要求 R2 补 `locked_docs` 字段；另影响面把过期授权也计入 grants/users（P3 口径）。
4. **端点表/路径口径**：`/embedding-coverage` 与 `/stats` 不在 design §6.2 表（任务书 A6/B4 已授权，建议非决策回写登记）；`PATCH .../values/{value_id}` 与任务书字面 `PATCH .../values` 存在路径差异（design 未钉死，建议 TEST-CASES 登记最终路径）。
5. **审计查询只覆盖当月**（无时间范围参数）——当前需求未明示历史查询，建议登记为已知范围，避免运维误读。
6. **RUNBOOK §4 L125-128 与 TEST-CASES v1.8.3 TC-OPS-05 注记均仍写"自动快照不含月库/随 m2-3 收编"**，与 B3 实现矛盾——属监督侧 docs 批，见下。

## 五、RUNBOOK 挂账处置与交付就绪判定

- **处置方式可接受**：docs-only commit 补落，沿 m2-2 `6d223c0` 先例；不重跑双验证（无代码变化）。但建议同一 docs commit 一并落：①RUNBOOK §4 产物清单加 `audit-months-<ts>.tar.gz`（月库+-wal/-shm+seal sidecar）与恢复解包步骤、删"不含月库/随 m2-3 收编"句；②TEST-CASES v1.8.3 TC-OPS-05 注记同步改"自动快照已含月库（m2-3 B3）"；③v1.9.3 承载上述两项口径登记 + 写锁项 + 端点/路径/移交登记；④本任务检查点与证据 manifest。
- **交付就绪判定：不就绪**。
  - 当前 R1 不能放行：P2-1/P2-2/P2-3/P2-4 需 R2 修复并重跑门禁（预期 964+1 起、新增用例计入、0 skipped）。
  - R2 通过后：docs-only HEAD 可按先例作为 `reviewedSha`（`testedSha` 保持代码 SHA），evidence manifest 写入 PR description 且双 SHA=最终 HEAD；chore 不得携带工作区 `.opencode/agent/supervised-coding.md`；m2-3 检查点（当前 untracked）须随交付入库。
  - 未完成上述 docs/manifest 前，不执行 `gh pr review` 放行。

## 六、结论

- **reviewVerdict: NEEDS_CHANGES**
- **reviewedSha: null（R1 未通过；审查对象 HEAD=`787116c`，testedSha=`787116c` 与 HEAD 一致；chore=`787116c` 内容合规）**
- **P1: 0；P2: 4（CSV/PUT 重复行 500+部分生效、expires_at 未校验跨方言不一致、reembed 进度取错标签、TC-OPS-06/07/08 双后端 store 覆盖与 docstring 不符）；P3: 17 项记录级**
- **两项口径裁定：TC-OPS-06 = (a) 按用户全量替换成立（用例补判别断言+限制登记）；TC-OPS-03 sysadmin 兼任 org_admin = 全量优先成立（补口径登记）**
- **RUNBOOK 挂账：docs-only 补落可接受，须在交付前完成**
- **关键面：链遍历/审计分级/同事务审计通过；CSV 核心通过但输入校验不通过；UI/分层/门禁/chore 通过（注记级问题已列）**

</details>

<details>
<summary>R2 Tester 报告全文（2026-10-30 14:10，testVerdict=PASS）</summary>

# m2-3 段 R2 修复轮 Tester 独立验证报告

**testedSha**: `6f7fbea8fe1d7ffef3a4a2227b374dfaf7e44e4b`（develop_opencode；R2 增量 787116c..6f7fbea，19 文件 +879/−94，docs 批同 commit）

## testVerdict: **PASS**

## 1. 门禁复跑（独立执行，非采信 coder 自测）

`docker start lattice-pg && export LATTICE_PG_DSN=… && scripts/test_gate.sh`

| 项 | coder 自报 | 独立复跑 | 一致性 |
|---|---|---|---|
| 双模式 | 994+1，0 skipped | **`994 passed, 1 deselected` × 2 模式（常规+python -O），0 skipped** | ✅ 逐字一致 |
| pg 臂 | 351 = 318 + 33 | **351 = [pg] 参数化 318 + PG 专用 33** | ✅ |
| 增量 | 964→994（+30）零回归 | **+30 对账闭合**：test_ops_03 +3 / test_ops_06 +6 / test_ops_08 +2 / test_admin_store_reads 5×双臂=10 / test_ops_07 locked_docs 1×双臂=2 / test_ops_chain_read +7（dimension 投影 1×双臂 + walk_chain 5 单元）−1 重复断言行（同用例内，不涉计数）；R1 964 全量在场（tests/ 零删除——`--name-status` 核验，唯一 M 文件为追加） | ✅ |
| skip 核对 | — | **0 skipped**（1 deselected = TC-UI manual 组，政策内） | ✅ |

## 2. 修复项逐条判定表

| 项 | 判定 | 独立证据 |
|---|---|---|
| **P2-1** 重复行 | ✅ | PUT `GrantRow` pydantic（缺键 422×2 形态断言+失败零写入）；行内重复 400；CSV 同值同 expires 去重生效（落库 count==1）、冲突 expires 400 报双行号+零写入。**独立加强**：跨用户场景（u_cn 正常行在前 + u_full 冲突行在后）→ 400 且 **u_cn 的目标行零写入**——解析期整批拒绝先于任何 apply，部分生效根除实证；dry_run 同规则同拒 |
| **P2-2** expires_at 严格解析 | ✅ | 4 非法形态（abc/2027-13-99/next friday/2027/01/01）400 带行号 + **count==0 零入列断言**（fail-open 证伪）；4 合法形态（库格式/T/Z/+00:00）归一化逐值断言；PUT 面同拒。**写路径面穷尽核阅**：grants.expires_at 的 API 写入口仅 PUT 与 CSV 两处（共用 `_parse_expires_at`）；`core/` 层零写路径；upload.py 的 expires_at 属 uploads 凭证表非 grants。**残余面注记**：store 层 `replace_local_grants` 直调仍不校验——属内部协议信任面（与 sync 写入同级），无 API 绕过。pg 跨方言一致性由共用解析器保证（门禁 pg 臂实跑同测） |
| **P2-3** 覆盖率目标标签 | ✅ | 端点改按最近 reembed 任务 `payload.embed_model` 算 `embedding_coverage` + `target_model` 字段；重写用例断言目标标签 1 向量 done==1、换 green:1536 零向量 **done==0**（旧标签 100% 不冒充进度）。**独立加强（同秒并列）**：同 created_at 强制同秒投两条 reembed（green/blue）→ 面板取 **id（ULID）更大**的任务、target_model 正确跟随、done==0——`ORDER BY created_at DESC, id DESC` 次级排序键（双方言对称）实证 |
| **P2-4** store 读方法 pg 臂 | ✅ | 新文件 test_admin_store_reads.py **5 用例全部 matrix 参数化**（pg 臂收集 318=311+7 中占 5——非 sqlite-only）；列形状/sync 标注/稳定序/find_user/pending 搬运清空/最近一条胜出+月库兜底取最后一条/None 空态——真实造数断言非恒真；test_ops_06 docstring 已改为与事实一致 |
| **边界3** locked_docs | ✅ | 双方言对称 SQL（`d.status!='active' OR v.status!='active' OR v.id=:vid`——本次将停用值视作 disabled）；coder 用例基线 2→retire tax_type 后 3→VAL_OS 预估 4 逐级断言。**独立加强（异构造数）**：disabled(tax_type/VAT)={d_cn,d_cit} ∪ retired(channel，d_cit 引用) ∪ 本值(region/OS)={d_multi,d_os} → **4** 独立复算一致；不存在/跨组织仍 None（404 语义不破坏）。口径与 v1.9.3 登记（「disabled 取值+retired 维度文档级锁面」）一致 |
| **P3-1** 月库兜底取最后一条 | ✅ | `reversed(read_monthly_events)` 双方言；用例造三条不同时戳断言「最近一条胜出」+ 搬运后兜底同值 |
| **P3-2** 双源 id 去重 | ✅ | 月库优先去重实现+用例真实构造崩溃窗形态（月库直插+outbox 留 pending）断言 `evt-dup` 出现一次 |
| **P3-3** limit Query | ✅ | `Query(100, ge=1, le=500)`；0/−1/501 → 422 断言 |
| **P3-4** dimension_id 投影 | ✅ | `_target_of` 映射改 dimension_id；搬运后 target_type/target_id 双事件断言（value_id 在 detail_json 保真口径） |
| **P3-5** walk_chain 永久用例 | ✅ | fork/multi_head/orphan/cycle/tampered 5 用例转正式（R1 临时验证收编；cycle 用例 docstring 诚实标注「heads=0 结构拦截先行」——与真实环不可达性分析一致） |
| **P3-6** org 头规范化 | ✅ | header `strip().lower()` 后判；`Org`/` org `/`ORG` 三变体 400 断言 |
| **P3-7** 非 UTF-8 400 | ✅ | UnicodeDecodeError→400；`\xff\xfe` 字节流实测 400+detail |
| **P3-8** backup stats | ✅ | `_backup_body` 补 audit_months 键；pg snapshot 显式 None（分区在库内口径注释）；用例 sqlite 臂断言 tar 落盘、pg 臂断言 None |
| **P3-9** drill 月库段 | ✅ | 脚本造审计事件搬运→快照含 audit_months→恢复解包断言月库在场+行数≥1 |
| **P3-10** sysadmin 用例 | ✅ | ① evt-a3（他组织）排除断言补齐；② 兼任 org_admin → full（含 detail_json）+ 兼任 A 查 B 仍 metadata——即 R1 临时测试的永久化 |
| **P3-11/12** | ✅ | 重复断言行删（−1）；EVENT_MAINTENANCE_RUN 常量参数化（SQL 走绑定参数，双方言） |
| **P3-14** UI | ✅ | 引号 CSV 正则解析（值含逗号不错位）、expires 保存时点统一（后填生效）、全角括号半角化（6 处）——diff 逐处核对与声称一致 |
| P3-13/15/16/17 | ➖ 不动 | 遵 R1 Committer 裁定（记录级遗留）——无回归引入 |

## 3. 口径裁定落地核对（R1 单列两项）

| 裁定 | 落地状态 |
|---|---|
| ① TC-OPS-06 按用户全量替换 + 判别断言 | **部分落地**：v1.9.3 预期句已落判别断言与「清空走 PUT 空清单」运维口径 ✓；语义复验 R2 后仍成立（独立测试：CSV 外 u_full CN+OS 原样）✓；**但「CSV 外用户 local 行原样保留」无永久 pytest 用例承载**（tests/ 全文检索零命中——见缺陷清单 D-1） |
| ② TC-OPS-03 sysadmin 兼任全量优先 | **完整落地**：v1.9.3 口径登记 ✓ + 永久用例（P3-10：兼任→full / 跨组织→metadata / evt-a3 排除）✓ |

## 4. 新 30 用例强度抽查

无恒真/无 mock 自证：重复行与非法 expires 均带**零写入**数据库态断言；P3-2 用例真实构造 sqlite 两步搬运崩溃窗（月库直插+回填缺失）；P2-3 用例真实插 `chunk_vectors` 目标标签向量；P2-4 用例断言列形状/排序契约/搬运排水；locked_docs 用例逐级造数（disabled→retired→本值叠加）。异常分支断言到错误消息内容（行号/键名/编码提示）。R1 基线用例零弱化（唯一 M 文件 test_ops_05 为追加+强化，pg 臂分支补齐）。

## 5. 零回归抽查

api/admin.py 大改后：TC-OPS-03 全组（含新 limit/去重/sysadmin 用例）、TC-OPS-06 全组（500 行/A-12/sync 不动/防孤儿/二跑零差异）、TC-OPS-07（dry_run/确认/T20 半句/locked_docs）、TC-OPS-08、覆盖率端点重写、audit limit 改动——全部随门禁双模式实跑通过。walk_chain 主体（乱序恢复/破链）与 B1~B6 存量用例未动且全绿。

## 6. docs 批核验

TEST-CASES v1.9.3（两项口径登记+locked_docs+端点/路径登记+审计范围登记+TC-OPS-05 同步）、RUNBOOK §4（**R1 挂账已清偿**——「已含月库」+tar 产物形态+pg 分区口径，旧矛盾句划线保留史痕）、_m2-plan m2-6 补段——三文件与监督侧落笔声明一致，非 coder 擅改（版本行明确「随 m2-3 R2 批入库」），design/requirements 正文未触碰。

## 7. 缺陷清单

**FAIL 项：无。**

**遗留缺口（建议 R3 或随 m2-6 补，不阻塞本轮 PASS）**：
- **D-1**（覆盖缺口，TEST_BUG 类）：v1.9.3 TC-OPS-06 预期句判别断言「CSV 外用户 local 行原样保留」无永久 pytest 用例承载（`grep -rn "未出现\|CSV 外\|absent" tests/` 零命中）。语义实现正确（两轮独立实证），缺的是裁定口径的**回归网钉死**。建议 R3 补一条 app_env 用例（≈10 行）或在交付裁定中显式接受为已知。复现：`grep -rn "CSV 外\|未出现用户" tests/test_ops_06_csv_grants.py` → 无输出。
- **D-2**（措辞，非缺陷）：`test_audit_sysadmin_excludes_other_org_and_dual_role` ①docstring 称「sysadmin（无 org:tax 成员关系）」，实际 app_env 中 sysadmin 持 org:tax **member** 关系——断言本身有效（member≠org_admin → metadata），仅注释不精确。

**残余面注记（登记即可）**：store 层 `replace_local_grants` 对 expires_at 不做格式校验（信任面=内部协议调用方，API 边界已收敛）；P3-13/15/16/17 按裁定遗留 m2-6/登记。

---

**结论**：R2 对 Committer P2×4 + 边界3 + P3×10 的修复全部独立证实有效，门禁 994+1 双后端双模式 0 skipped 与声称一致、964 基线零回归，两项口径裁定按 v1.9.3 落地（其一测试承载缺口 D-1 单列）——**testVerdict: PASS**，testedSha=`6f7fbea`。独立验证临时文件已删除，仓库零残留（`git status` 仅存监督侧既有工作区状态）。

</details>

<details>
<summary>R2 Committer 报告全文（2026-10-30 14:19，reviewVerdict=NEEDS_CHANGES）</summary>

## 审查基线核对（R2 复审）

- 审查对象：`HEAD=6f7fbea`，增量 `787116c..6f7fbea`：19 文件 +879/−94，与检查点 `filesChanged` 一致；`testedSha=6f7fbea` 与 HEAD 一致；`reviewedSha` 仍为 null（R1 NEEDS_CHANGES 后置空）——本轮为 R2 重审。
- R1 意见处置：**P2-1/P2-2/P2-3/P2-4 四项全部落实**（解析期去重+400/422、`_parse_expires_at` 严格解析、target_model 目标标签、四个 store 读方法 matrix 双臂）；**边界 3 locked_docs** 双后端落地；**P3-1~12、14 收编**；P3-13/15/16/17 遵 R1 裁定未动。两口径 v1.9.3 已登记；m2-6 补段已入 `_m2-plan`；RUNBOOK §4 已更新。**R1 的 P2 已闭环，未发现回归性破坏**（但 R2 新引入两处需修，见下）。
- 测试门禁：diff 中测试零删除、零 skip；新增 30 用例（+30 逐文件对账与检查点一致；pg 臂 344→351 真实收集）；R1 既有断言无放宽。Tester R2 门禁 994+1 双后端双模式 0 skipped，采信其独立复跑。

## 一、D-1 裁定

**裁定：（a）R3 微修补用例。** 依据：

1. **R3 已不可避免**——本轮复审发现两处 P2（见下），本来就需开 R3；D-1 的 ~10 行 app_env 用例边际成本极低。
2. **m2-6 不是可靠承接点**：`_m2-plan` 的 m2-6 范围是"reindex/reembed 蓝绿执行体 + members/values CRUD"，**并不必然触及 CSV import**；把 v1.9.3 刚登记的判别断言挂在"可能不相关"的段上，等于长期无回归网。
3. **v1.9.3 已把"CSV 外用户 local 行原样保留"写成预期句**，但 `tests/` 无永久承载（Tester 的 grep 结论属实）；按本项目"门禁=CI"的纪律，用例=需求，预期句必须有 pytest 钉死，不能只靠两轮临时独立实证。
4. Tester 的 D-2（sysadmin 用例 docstring 措辞）属 P3，随 R3 顺手修正即可，不另开轮。

R3 最小范围：`test_ops_06` 加一条"CSV 仅含 u_cn，u_full 的 local 行原样保留"的判别用例；连同下述 P2 修复后重跑门禁（预期 994+1 起、新增用例计入、0 skipped）。

## 二、问题清单（P1/P2/P3）

### P1（阻塞）：无

### P2（须 R3 修复，不宜放行）

**P2-1｜CSV dry_run 差异在 pg 上把 `expires_at` 的 datetime 与规范化字符串相比——二跑零差异/kept 在 pg 必假**
`src/knowledge_lattice/api/admin.py:430-442`（`current` 直接取 `list_grants_for_export` 原值；`target` 为 `_parse_expires_at` 归一化后的字符串）。
- `list_grants_for_export` 的 pg 实现返回 `g.expires_at` 为 **datetime**（`store/postgres/backend.py:2303-2318`），sqlite 为 TEXT；`export_grants` 已在 `admin.py:314-321` 做了 `strftime` 归一（**导出侧正确**），但**差异计算的 `current` 未归一**。
- 后果：pg 上 CSV 带非空 `expires_at` 时，`target[k] != current[k]` 恒真（str vs datetime）→ dry_run 把全部未变行报为 `changed`、`kept` 丢失；TC-OPS-06 的"二跑零差异"和"双后端"在 pg 上不成立。apply 落库本身正常，但预览语义错误。
- 现有测试未覆盖：`test_ops_06` 明确 REST 仅 sqlite；`test_admin_store_reads` 只断言 store 层 `expires_at is not None`，未覆盖 API diff 的跨方言类型。
- **修复**：`current` 取值时按 `_EXPIRES_LIB_FORMAT` 归一（与 export 同一 helper），或让 `list_grants_for_export` 双方言统一返回字符串；补一条 pg 臂可执行的 diff 用例（可抽 `_compute_grants_diff` 纯函数用 pg datetime 造数，或最小化 store 层断言）。

**P2-2｜权限视图"保存"把单框 expires 应用到全部选中行——静默清除既有临时授权（R1→R2 回归，fail-open）**
`src/knowledge_lattice/web/app.js:244-252`（`saveGrants` 用 `expiresNow` 覆盖所有 key）+ `:208-240`（`renderGrantChips` 仍把既有 `r.expiresAt` 放进 `picked`，但不再被 save 使用）+ `index.html:128-130`（`gExpires` 从不按成员预填）。
- R1 行为：既有授权行保留其原 `expires_at`；R2 为修"后填不生效"改为保存时点统一应用，副作用是**选中受临时授权成员、切换任一 chip、过期框留空保存 → 该成员全部 local 授权变永久**；UI 也不显示既有过期值，管理员无从察觉。
- 这与 P2-2 要根除的"临时授权永久化"同属安全语义失败开放，且是 R2 新增回归。
- **修复**：保存时对"原已存在 key"沿用 `accessState.picked[k]`，仅对"新选中 key"应用输入框（或按成员预填统一/混合态显示 + 显式"清除过期"动作）；补一条 UI 手工/playwright 断言：既有临时授权在仅切换 chip 后保存不被清空。若监督侧坚持以"最小 UI 非验收面"降级，需在检查点显式接受该回归并登记 m2-6，但我不建议放行。

### P3（记录级；随 R3 顺手或登记）

1. **月库兜底测试是假覆盖**：`tests/test_admin_store_reads.py:75-98`。`read_last_maintenance_stats` 的 outbox 分支**不按 shipped_at 过滤**，`ship_outbox()` 后三条 maintenance.run 仍在 outbox 中，`stats2` 实际走 outbox 分支而非月库兜底；`reversed()` 修复未被验证。且造数硬编码 `2026-10-11/12/13`（若测试改为清空 outbox 进入兜底，11 月即失败）。建议：测试内 `DELETE FROM audit_outbox`（或 trim）后断言月库兜底，并用当月相对日期/时钟注入。
2. **docs v1.9.3 版本行与正文不一致**：版本行称"⑥TC-OPS-05 v1.8.3 注记同步：自动快照已含月库"，但 `docs/TEST-CASES.md:492` 正文仍写"自动快照纳入随 m2-3""恢复完整性验收以主库+objects 为准"。属监督侧 docs 批（coder 原样 commit，未擅改），须在最终 docs commit 修正。
3. **RUNBOOK §4 产物清单未含月库 tar**：`RUNBOOK.md:112` 仍写"产物：lattice-snap-<ts>.db + objects-<ts>.tar"；月库 tar 只在下方段落出现。建议产物清单补 `audit-months-<ts>.tar.gz`（与 R1 建议①一致）。
4. **协议 docstring 未同步新增字段**：`store/backend.py:432-446` 的 `dimension_value_impact`/`disable_dimension_value` 仍写 `{docs, grants, users}`，`backup_snapshot` 仍写 `{database, objects, created_at}`；实际已返回 `locked_docs`/`audit_months`。契约文档需补，否则后续调用方可能按旧契约消费。
5. **"ULID 时间有序"注释不实**：`store/sqlite/backend.py:1103`、`store/postgres/backend.py:1068`。`tasks.id = tsk_{uuid4}`（`create_task` 未改），同秒并列下 `id DESC` 只是确定性 tiebreak，**不是"最近优先"**；`embedding_coverage` 同秒双 reembed 仍可能取旧任务。Tester 的"同秒 ULID 独立验证"仅证明了 id 序确定性；R2 测试亦主动删旧任务回避同秒。建议改注释/改用 rowid 或单调键；同秒歧义登记 m2-6。
6. **walk_chain"孤儿"用例名不副实**：`tests/test_ops_chain_read.py` 新 `test_walk_chain_orphan_rows_detected` 实为第二链头（multi-head）形态；`len(ordered) != len(rows)` 孤儿分支仍无覆盖。建议补"主链 + 不相交环（prev 在批内 hash 集但不可达）"用例。
7. **locked_docs 未在 UI 展示**：`web/app.js:347,362` 的 dry_run 确认文案只显示 docs/grants/users；`i18n.js` 无 `dims.impact.locked` 键。API 已返回，最小 UI 未消费；建议补一行展示（v1.6.3 的"写锁项"目的即让管理员看到影响）。
8. **PUT 与 CSV 重复行语义不一致**：PUT 对任何重复 `(dim_key,value)` 直接 400（`admin.py:229-256`），CSV 同 expires 静默去重、不同 expires 400（`admin.py:346-380`）。两处均可辩护，但建议登记口径或统一（CSV=人工文件宽容去重、API=严格拒绝）。
9. **expires 格式子集与文档口径**：`admin.py:271-299` 拒绝 date-only ISO（`2027-12-31`）、非 `+00:00` 时区、毫秒、小写 z；错误文案写"ISO 8601（UTC）"略宽。建议文案/注释明确"T 分隔、UTC、秒精度"，或接受 date-only（按 UTC 零点）以贴合管理员直觉。
10. **pg 导出归一化缺测试**：`export_grants` 的 `strftime` 路径仅 sqlite REST 覆盖；pg datetime 归一只有代码审查，无测试。属 P2-1 修复的同一测试缺口，建议同批补。
11. **测试 docstring 残留**：`tests/test_ops_03_audit_access.py` sysadmin 用例称"无 org:tax 成员关系"实为 member（D-2，Tester 已报）；`tests/test_ops_06_csv_grants.py:275-284` 仍称"他组织路径 → 403"但只测了本组织 member 403（R1 P3 未收）。
12. **`_m2-plan` m2-6 行 stale**：已列"UI split 解析替换"，但 R2 已完成；建议更新（属监督侧）。
13. **store 层 `replace_local_grants` 仍不校验 expires_at**：API 边界已收敛；直调属内部协议信任面（Tester 已注记），后续 sync 写路径落地前需保证同解析器，登记即可。
14. **UI CSV 正则解析对内部空行**：`app.js:177-190` 的 `l.match(...)` 对空行返回 `[""]`，`cols[1]` 为 undefined；服务端导出不会产生空行，最小 UI 可接受，登记即可。
15. **CSV 空字段行 + 按用户全量替换**：`admin.py:346-380` 空字段行进 rejected、其余行照常按用户替换，可能删掉该行对应既有授权（dry_run 可见）；属 R1 已记录口径，建议 TEST-CASES 补一句。

## 三、关键面显式结论

- **P2-2（expires 解析/写路径）**：**API 边界闭合成立**。PUT/CSV 共用 `_parse_expires_at`；sqlite fail-open 由"非法串零入列"用例证伪；pg 由同一解析器保证入参一致；导出侧 pg TIMESTAMP `strftime` 归一正确；残余仅 store 直调信任面（已注记）。**但差异计算侧 pg datetime 未归一（P2-1）**，属解析修复未延伸到的读取面。
- **P2-1/P2-3（重复行/目标标签）**：**主修复成立**。CSV 重复同 expires 去重、冲突 400 报双行号、解析期先于 apply（跨用户部分生效根除）；PUT `GrantRow` pydantic 缺键 422、重复 400；`target_model` 取任务 payload、目标标签覆盖率、done=0 起步，测试真造 `chunk_vectors` 行、非恒真；m2-6 执行体可按 payload 衔接。**但同秒"最近 reembed"仍按随机 UUID 排序（P3-5）**，且 UI 保存会清既有 expires（P2-2）。
- **locked_docs**：**SQL 口径与 v1.9.3 一致**。双方言对称；逐级断言+Tester 异构造数独立复算；不存在/跨组织仍 None。**协议 docstring（P3-4）与 UI 展示（P3-7）未同步**，不构成语义错误。
- **R2 新增 30 用例质量**：matrix 双臂真实；walk_chain 5 条永久用例断言强度足够，**但 orphan 用例实为 multi-head（P3-6）**；**月库兜底用例是假覆盖（P3-1）**；CSV diff 的 pg 面仍无测试（P2-1）。无恒真/mock 自证；无时间炸弹（Oct 日期因走 outbox 分支当前不炸，但修兜底测试须同时改当月相对日期）。
- **docs 批**：与裁定一致、未见擅改；**版本行 TC-OPS-05 注记与正文 L492 不符、RUNBOOK 产物清单缺月库 tar（P3-2/3——监督侧修正）**。
- **零回归**：采信 Tester 994+1；测试 diff 零删除/零 skip；R1 既有断言未放宽。

## 四、结论与交付就绪

- **reviewVerdict: NEEDS_CHANGES**
- **reviewedSha: null**（R2 未通过；审查对象 HEAD=`6f7fbea`，testedSha=`6f7fbea` 与 HEAD 一致；R1 P2 已闭环，但 R2 新引入 P2×2）
- **P1: 0；P2: 2**；**P3: 15 项记录级**（其中 P3-1/2/3/4/6/7 建议随 R3 收；docs 两项归监督侧）
- **D-1 裁定：（a）R3 微补**
- **R3 最小范围**：P2-1 归一+pg diff 用例；P2-2 保留既有逐行 expires+playwright 断言；D-1 判别用例；顺手 P3-1 兜底测试、P3-4 协议 docstring、P3-5 注释、P3-6 orphan 用例、P3-7 UI locked_docs、P3-11/12 文案；docs 两项由监督侧在最终 docs commit 修。重跑门禁，0 skipped。
- **交付就绪：不就绪**。R3 通过后仍需：① docs 批修正（v1.9.3 TC-OPS-05 正文/RUNBOOK 产物清单/plan stale 行）；② 本任务检查点随交付入库；③ evidence manifest：testedSha=R3 代码 SHA、reviewedSha=最终 docs-only HEAD（双 SHA=HEAD）；④ supervised-coding.md 不得入库。

</details>

<details>
<summary>R3 Tester 报告全文（2026-10-30 14:56，testVerdict=PASS 收敛）</summary>

# m2-3 段 R3 修复轮 Tester 独立验证报告（最后一轮）

**testedSha**: `dcf3923732ae89a5ca26e977c1eb108be5d8881b`（develop_opencode；R3 增量 6f7fbea..dcf3923，13 文件 +169/−40，docs 批同 commit）

## testVerdict: **PASS**（收敛——见 §7）

## 1. 门禁复跑（独立执行）

| 项 | coder 自报 | 独立复跑 | 一致性 |
|---|---|---|---|
| 双模式 | 1000+1，0 skipped | **`1000 passed, 1 deselected` × 2 模式，0 skipped** | ✅ 逐字一致 |
| pg 臂 | 353 = 320 + 33 | **353 = [pg] 参数化 320 + PG 专用 33** | ✅ |
| 增量 | 994→1000（+6） | **+6 闭合**：test_admin_store_reads +2 matrix（×双臂=4）+ test_ops_06 D-1（1）+ test_ops_chain_read 真 orphan（1）；pg 臂 +2=store_reads 新 matrix×2 | ✅ |
| 零回归 | R2 994 基线 | tests/ 零删除（4 个 M 文件全为追加/修正），994 用例全量在场双模式实跑 | ✅ |

## 2. 修复项逐条判定表

| 项 | 判定 | 独立证据（不依赖 coder 用例） |
|---|---|---|
| **P2-1** pg diff 失真 | ✅ | **消费方穷尽核验**：`list_grants_for_export` 全仓调用点仅 api/admin.py 两处（L314 export / L432 diff current 字典）——store 单点收口后两处均得字符串，**无第三处 datetime 消费**；api 层 export 死分支（R2 的 isinstance-strftime）已清。**pg 臂独立构造**（非复用 coder 断言）：写非空 expires → store 读回 `isinstance str` 且与目标串相等；复刻 import 的 current/target 字典比较——同值 → changed==[]、kept==1；**changed 分支方向性**（换目标串 → changed 恰含该键）——证明 pg 臂比较是值级而非恒等/恒不等。coder 证伪声称（修前 datetime!=str 恒 changed）与修后行为自洽 |
| **P2-2** UI 清临时授权回归 | ✅ | **playwright 三场景独立实证**（真实 server + 真实库）：① 装载态 CN chip 预填 on（picked 来自库内行）→ **不动 chip + 空框保存 → `2027-06-30 00:00:00` 保留**（R2 代码下必被清成 NULL——回归修复实证）；② **显式清除路径可达**：取消选中 → 重选（fresh）+ 空框 → 保存 → 转永久（expires NULL）——用户意图表达=重选+空框，两步显式动作，无静默面；③ 重新装载 + 输入框填 2030 值 + 不动 chip → 保存 → NULL 保持（非 fresh key 不应用输入框值——与 R2「后填生效」语义正确交叉）。装载态 `fresh.clear()` 代码核阅一致 |
| **D-1**（R2 单列） | ✅ | `test_csv_import_users_absent_local_rows_untouched`：**真实造数**（断言 u_full 既有 2 行 local 在前）→ CSV 仅含 u_cn → `after == before` **逐值断言**（value_id+expires_at 全列）——强度合格，v1.9.3 判别断言自此有门禁承载 |
| **P3-1** 月库兜底真覆盖 | ✅ | coder 抓点正确（stats 查询不滤 shipped_at——R2 用例仅 ship 不清行则恒走 outbox 分支，reversed() 从未被执行）；R3 显式 DELETE + `utc_now_ts()[:8]` 当月派生（时间炸弹根除）。**独立加强**：payload 值与时间序**反向**（t1=9/t2=1/t3=5）→ ship+DELETE 后断言取 **5（链序最近）而非 9（值最大）**——排除「取最大值」假实现；双臂全过 |
| **P3-4** 协议 docstring | ✅ | locked_docs（dimension_value_impact/disable）+ audit_months（backup_snapshot）双方言 docstring 补齐——与实现签名一致 |
| **P3-5** ULID 注释改实 | ✅ | 「ULID 时间有序」→「随机非单调、不保证时间序——确定性 tiebreak」双方言注释修正（诚实修正 R2 过度声称）；同秒歧义登记 m2-6（_m2-plan 行已落）——R2 的同秒测试语义相应降格为「确定性」口径，一致 |
| **P3-6** 真 orphan 用例 | ✅ | 主链 a→b + **不相交环** x↔y（环 prev 互指批内 hash 集、不增 heads、主链走完 ordered=2<4）→ `match="orphan"` 真触发 len 分支；原用例改名 multi-head 并注记两形态区分——diff 逐行核阅，构造与 walk_chain 算法对齐 |
| **P3-7** UI locked_docs | ✅ | 确认文案拼接 `imp.locked_docs` + i18n 键 `dims.impact.locked` 中英双语齐全 |
| **P3-10/11** | ✅ | store 级归一断言（P2-1 用例承载）；docstring 残留×2 修正（test_ops_03 sysadmin 措辞与实际 fixture 形态一致化——即 R2 的 D-2；test_ops_06 权限用例 403 声明范围改实） |
| **docs 批** | ✅ | TEST-CASES TC-OPS-05 正文口径更新（「已含月库」+ tar 产物 + drill 断言）+ TC-OPS-06 补重复行语义句（「API 严格/文件宽容」+空字段行进 rejected 口径）；RUNBOOK §4.1 产物清单补 `audit-months-<ts>.tar.gz`；_m2-plan m2-6 行更新（同秒单调键、replace_local_grants 直调解析器对齐等登记——含 R2 残余面注记的承接）。三文件与监督侧声明一致，正文冻结纪律未破 |

## 3. 新 6 用例强度抽查

无恒真：D-1 逐值 before/after 全列断言；P2-1 双用例断言到类型（`isinstance str`）与逐值相等；P3-1 用例含真覆盖路径（DELETE outbox）+ 当月派生日期；orphan 用例 match 错误消息分支。零断言放宽、零 skip 引入。

## 4. 与 coder 自测对账

门禁 1000+1 / pg 臂 353=320+33 / +6——三项独立复跑逐字一致。P2-1 修前证伪（pg datetime!=str）方向可信（与 R2 已知的 pg TIMESTAMP 读出形态一致）；UI playwright 前后对照以三场景独立复现替代采信。

## 5. 缺陷清单

**FAIL 项：无。**

**登记项（不阻断，随 m2-6/交付裁定量）**：
- **N-1**（继承登记）：同秒 reembed「最近」歧义——id tiebreak 仅保证确定性非时间序（R3 已诚实改注 + _m2-plan m2-6 登记）。
- **N-2**（继承登记）：`replace_local_grants` store 直调不经 `_parse_expires_at`（API 边界已收敛；m2-6 登记对齐项）。
- **N-3**（微注记）：P3-1 用例的 `assert ... == [] or not [...]` 为宽松双分支写法（DELETE 后恒走前支，or 短路无害——非恒真风险，仅风格）。

## 6. 三轮轨迹回顾

R1（964+1，Tester PASS + 2 口径单列）→ Committer NEEDS_CHANGES（P2×4+P3×17+两裁定）→ R2（994+1，P2×4 全修 + 口径落地 + D-1 单列）→ Committer R2 复审（P2×2 新引入 + D-1 催办）→ **R3（1000+1，P2×2 + D-1 + P3×6 收敛）**。每轮门禁单调递增、零删除零弱化、两口径裁定完整落地（判别断言自此有永久用例）、RUNBOOK/TEST-CASES 文档链闭环（R1 的文档挂账 R2 清偿、R2 的 D-2 措辞 R3 修正）。

## 7. 收敛性意见（round=3/maxRounds=3 最后一轮）

**已收敛，建议放行交付**。依据：
1. Committer R2 复审的 P2×2（均为 R2 新引入回归面）全部修复并经独立证伪级验证（pg diff 值级语义、UI 临时授权三场景）；
2. R2 单列的 D-1 已补永久用例——两项口径裁定的「用例文字 + 测试承载」双面闭环；
3. 门禁 1000+1 双后端双模式 0 skipped，pg 臂 353 全实跑，三轮零回归零弱化；
4. 无新增未决 P 级问题；残留三项均为已登记的继承项（m2-6 承接），无阻断交付面。

遗留移交（不阻塞本段）：m2-6 承接清单已在 _m2-plan 落笔（蓝绿执行体/members+values CRUD/read_org_audit 下沉/audit_chain 错误码/同秒单调键/解析器对齐），TC-UI manual 走查仍待用户（政策内）。

---

**结论**：m2-3 段 R3 修复全部独立证实有效——**testVerdict: PASS（收敛）**，testedSha=`dcf3923`。验证临时产物（playwright 会话/临时 server/临时测试文件）已全部清理，仓库零残留。

</details>

<details>
<summary>R3 Committer 报告全文（2026-10-30 15:02，reviewVerdict=APPROVED）</summary>

## 基线核对（R3 终审）

- 审查对象：`HEAD=dcf3923`，增量 `6f7fbea..dcf3923`：13 文件 +169/−40，与检查点 `filesChanged` 一致；`testedSha=dcf3923` 与 HEAD 一致；`round=3`（maxRounds=3 最后一轮）。
- R2 意见处置：**P2-1/P2-2 两处 P2 已修**；**D-1（R2 裁定 (a)）已落地**；R2 建议顺手 P3-1/4/5/6/7/10/11 均已收；docs 批（TEST-CASES TC-OPS-05 正文/TC-OPS-06 重复行语义、RUNBOOK 产物清单、_m2-plan m2-6 行）随 R3 commit 入库；P3-13/15/16/17 遵 R2 裁定未动。测试 diff 零删除、零 skip；门禁 1000+1 双后端双模式 0 skipped（+6 与检查点逐项对账闭合，pg 臂 353），采信 Tester R3 独立复跑。

## 一、P2 修复核验

### P2-1（pg diff 失真）——**方案成立、实现完整**

- **方案选择**：`list_grants_for_export` 在 store 单点返回库格式字符串（pg `strftime("%Y-%m-%d %H:%M:%S")`），api `export_grants` 的死归一分支删除。这比建议的"api 侧归一"更优：`datetime` 形态不再外泄 api 层，**export/diff/审计三个消费面同源比较**，且与既有 `created_at` 在 store 归一先例一致。理由成立。
- **消费面穷尽**：全仓 `list_grants_for_export` 仅 `api/admin.py:314`（export）与 `:432`（diff）两处；无第三处 datetime 消费（Tester 独立 grep 一致）。
- **归一正确性**：pg TIMESTAMP（UTC 连接）→ 库格式字符串；sqlite TEXT 原样；`None` 保持 None；csv 导出 `expires_at or ""`；与 `_parse_expires_at` 的库格式一致。
- **测试**：`test_list_grants_for_export_expires_normalized_str`（matrix 双臂，`isinstance(str)` + 值级断言，修前 pg datetime 必红）+ `test_grants_diff_idempotent_after_replace`（replace→读回同键等值——pg 修复前恒不等）；证伪→修复对照成立。
- **残余 P3（见清单）**：store 内格式字面量与 api `_EXPIRES_LIB_FORMAT` 未共享常量；协议 docstring 未注明"库格式字符串"；committed 用例为 store 级（API diff 的 `changed==[]/kept` 由 Tester 临时独立验证，未入永久网）。

### P2-2（UI 清既有临时授权）——**主回归已修、语义可接受**

- "fresh 集"语义：装载态 `picked`=库内既有 expires、`fresh` 清空；toggle 仅显式（重）选中入 fresh；save 未动 key 沿用库内值、fresh key 应用输入框（空=永久）。**"不动=不变，动=显式"**成立，R2 的静默清除面根除。
- 显式清除路径：需"取消再选中"两步 + 空输入框；Tester playwright 三场景（不动保留 / 重选+空框=显式永久 / 非 fresh 不应用输入框）独立实证。**两步动作可接受**，但非理想：输入框不预填/不显示既有过期值，重选（如误点回补）时空框即永久——属 P3 UX（登记 m2-6 预填/逐行过期编辑），不构成 P2。
- 附带：`langchange` 会重渲染并清空 fresh（未保存改动丢失）为既有行为，P3 记录。

### D-1（R2 裁定 (a)）——**已闭环**

`test_csv_import_users_absent_local_rows_untouched`：CSV 仅含 u_cn → u_full 的 local 行（CN+OS）逐值/逐 expires 原样保留；真实造数、非恒真；v1.9.3 判别断言自此有永久门禁承载。

## 二、意见清单

### P1（阻塞）：无

### P2（须修）：无

### P3（记录级；登记放行，不另开轮）

1. **RUNBOOK 产物清单残留旧行**：`RUNBOOK.md` §4.1 已加"产物清单（m2-3 B3 起）：… + audit-months-<ts>.tar.gz"，但其下一行仍保留旧 `#   产物：lattice-snap-<ts>.db + objects-<ts>.tar`（不完整、易误读）。建议 supervision 随最终 chore 删旧行/合并（docs-only，无需代码轮）。
2. **B5 读回行 `row_hash` 不自洽未登记**（R2 P3-13）：`m2-6` 行已含 N-1 同秒 reembed、N-2 `replace_local_grants` 直调解析器、`read_org_audit` 下沉、`audit_chain` 错误码，但**未列**"`read_monthly_events` 返回行经 B5 重投影后 `row_hash` 与语义列不自洽（消费者勿以读回行复算链）"。建议补入 m2-6 行或 `read_monthly_events` docstring。
3. **"ULID"注释仍不实**：`store/sqlite/backend.py:1103`、`store/postgres/backend.py:1068` 改为"确定性 tiebreak、非时间序"方向正确，但仍写"id 为 ULID 随机非单调"——tasks.id 实为 `tsk_{uuid4}`（非 ULID）。建议改"UUID4 随机"或删 ULID 字样（注释级；同秒歧义已登记 m2-6，行为无差异）。
4. **P3-1 committed 用例未区分 reversed 与"取最大 payload 值"**：`test_read_last_maintenance_stats_latest_wins` 的三条造数 payload 值（1,2,3）与时间序同向，`reversed` 与"值最大"均得 3；Tester 的"反向造数"独立验证未入永久用例。建议把 payload 值改成与时间序反向（如 3,2,1）以锁死 `reversed` 路径；另 `assert ... == [] or not [...]` 双分支偏松（N-3）。
5. **UI fresh 残余 UX**：`gExpires` 不预填/不显示既有过期值；重选既有 chip + 空框=永久（显式两步但默认空）；`langchange` 重渲染清空未保存 fresh。建议 m2-6 预填/逐行过期编辑或至少显示既有过期值（`app.js:208-260`）。
6. **格式常量双源**：`store/postgres/backend.py` 的 `strftime("%Y-%m-%d %H:%M:%S")` 与 `api/admin.py:_EXPIRES_LIB_FORMAT` 各自字面量；建议共享常量（store 层或 domain）防未来漂移。
7. **协议 docstring 未注明 `list_grants_for_export` 的字符串契约**：`store/backend.py:480-483` 仍只列字段；pg 实现已注明、sqlite 未；建议协议层补"expires_at 库格式字符串"（与 P3-4 同类）。
8. **P2-1 的 API diff 永久 pg 用例**：committed 为 store 级；REST 仅 sqlite。若后续可加 pg app fixture，建议补 `changed==[]/kept` 的 API 级断言（当前由 store 契约单点 + Tester 临时验证兜住）。
9. **`tests/test_admin_store_reads.py` 注释残留"同秒 ULID"**（第 67/77 行附近）：与 P3-3 同源；测试用语改为 UUID4 或"确定性 tiebreak"。
10. **v1.9.3 版本行措辞**：仍写"随 m2-3 R2 批入库"，R3 又补了 TC-OPS-05/06 正文；建议版本行改"R2/R3 批"或加一句 R3 增补（docs nit）。

以上均为 P3/登记级：不涉及验收行为、数据正确性或安全面；**不值得突破 maxRounds=3 开 R4**，登记放行。

## 三、登记项确认

- **N-1（同秒 reembed 歧义）**：`_m2-plan` m2-6 行已含"同秒 reembed 歧义单调键" ✓；代码注释已改为"确定性 tiebreak、非时间序" ✓（ULID 字样残留见 P3-3）。
- **N-2（`replace_local_grants` 直调解析器）**：m2-6 行已含"replace_local_grants 直调解析器对齐" ✓。
- **R2 P3-5**：同秒歧义 → m2-6 ✓；**R2 P3-13（B5 row_hash 不自洽）→ 未登记**（P3-2，建议补）。
- **R2 P3-15/16（审计当月范围/门禁根因）**：v1.9.3 已登记审计范围；门禁根因属记录，不阻断。
- **N-3（宽松双分支断言）**：未显式入 m2-6，属测试微注记；建议随 P3-4 顺手。

## 四、关键面显式结论

- **P2-1**：**通过**——store 单点归一、消费面同源、pg 证伪/修复对照 + diff 幂等双臂；格式常量/协议 docstring/API 级 pg 断言为 P3。
- **P2-2**：**通过**——fresh 集实现"未动=库内值、显式重选=输入框"；R2 静默清除回归根除；重选空框/不显示既有值/语言切换重置为 P3 UX。
- **D-1**：**闭环**——判别用例真实造数、逐值断言，v1.9.3 口径有永久门禁承载。
- **P3 抽查**：P3-1 月库兜底**真覆盖**（DELETE outbox + 当月派生日期，时间炸弹根除；reversed 断言强度 P3）；P3-6 真 orphan ✓；P3-7 UI locked_docs ✓；P3-4 协议 docstring ✓；P3-10 pg 归一 ✓；P3-11 docstring×2 ✓。
- **docs 批**：TC-OPS-05 正文已改为"已含月库+恢复验收含 tar+drill" ✓；TC-OPS-06 重复行/空字段行语义登记 ✓；_m2-plan m2-6 更新 ✓（B5 登记缺，P3）；RUNBOOK 新产物清单有、旧行残留（P3）。
- **零回归**：1000+1 双模式 0 skipped；+6 逐项闭合；三轮 964→994→1000 单调；tests 零删除/零弱化；`test_gate.sh` 未动；R1/R2 既有断言未被放宽。

## 五、结论与交付就绪

- **reviewVerdict: APPROVED**
- **reviewedSha: `dcf3923732ae89a5ca26e977c1eb108be5d8881b`**（=testedSha=HEAD，三一致；docs 批已含于 R3 commit，无需代码轮/重验）
- **P1: 0；P2: 0；P3: 10 项记录级**——**登记放行，不突破 maxRounds=3**。
- **D-1：闭合**。
- **交付就绪判定：就绪（代码/测试/门禁），交付前置两件**：
  1. **manifest 前置**：检查点 `.opencode/workflows/task-knowledge-lattice-m2-3.md`（当前 untracked）须随交付入库；evidence manifest 写入 PR description，`testedSha=dcf3923`、`reviewedSha` 与最终 HEAD 一致（若检查点 chore 推进 HEAD，按 m2-2/m1-4 先例记 reviewedSha=该 docs-only HEAD、testedSha 保持 dcf3923；P3 docs 一行项可并入该 chore，不做代码轮）；**工作区 `.opencode/agent/supervised-coding.md` 的 M 状态不得入库**。
  2. **留痕**：用户确认交付后执行 `gh pr review` 落审查结论；合入动作不由 Committer 经手。

</details>
