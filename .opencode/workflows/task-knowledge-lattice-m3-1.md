---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m3-1
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e473a6ec4ffehxosh9HoSIpJM0
testerTaskId: ses_e470eb7c3ffekQYY7IfQv2dBz2
committerTaskId: ses_e4700f2e3ffe2DHytNqnum4jqT
status: approved
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 33fb8150c9f77551146e28e271828cda7ce8fd3e
reviewedSha: 33fb8150c9f77551146e28e271828cda7ce8fd3e
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [store/sqlite/migrations/docs/0011_org_status.sql, store/postgres/migrations/docs/0011_org_status.sql, src/knowledge_lattice/store/backend.py, src/knowledge_lattice/store/sqlite/backend.py, src/knowledge_lattice/store/postgres/backend.py, src/knowledge_lattice/store/sqlite/acl_render.py, src/knowledge_lattice/store/postgres/acl_render.py, src/knowledge_lattice/api/admin.py, src/knowledge_lattice/api/documents.py, src/knowledge_lattice/api/upload.py, src/knowledge_lattice/api/search.py, src/knowledge_lattice/api/semantic.py, src/knowledge_lattice/mcp/server.py, src/knowledge_lattice/domain/audit_events.py, tests/test_admin_m31_endpoints.py, tests/test_org_disable_m31.py, tests/test_docs_explain_m31.py, tests/test_az_m31_scan.py, tests/conftest.py, tests/test_scaf_03_migrations.py, tests/test_v11_schema.py, tests/test_regress_m0a1_followups.py, tests/test_pg_scaff.py]
endReason: null
createdAt: 2026-11-08T09:26:40+08:00
updatedAt: 2026-11-08T10:55:01+08:00
---

# task-knowledge-lattice-m3-1: 管理面补强批（含 be-①② 并入）

## 任务原文

**M3 首段（_m3-plan §一 row 1，拆分方案用户确认 2026-11-02；be-①② 并入用户拍板 2026-11-05；D-①② 契约冻结评论 issue #20 issuecomment-6649900631，2026-11-05 已发布）**。

### A. issue #13：§6.2 五方法组合实装 + GET 单维度/单取值端点

design §6.2 列明但实现缺失的 5 个方法组合（历史口径差，M2 验收句已清偿 ≠ 端点全集）：

1. `GET /api/orgs/{org}/members` —— 成员列表（含 expires_at；org_admin 门控，org_scoped）
2. `POST /api/orgs/{org}/datasets` —— 新建库（org_admin 门控）
3. `PATCH /api/orgs/{org}/datasets/{id}` —— 库修改（删除仍走服务层流程先删文档再删库——P1-1，不在本段）
4. `POST /api/orgs/{org}/dimensions` —— 新建维度（org_admin 门控）
5. `PATCH /api/orgs/{org}/dimensions/{id}` —— 维度修改（enabled/required 仅影响上传、不影响过滤——D5 v0.4；生命周期 status 仍由退役端点管理）
6. `GET /api/orgs/{org}/dimensions/{id}/values` —— 取值列表
7. 连带新增：`GET /api/orgs/{org}/dimensions/{id}`（单维度）、`GET /api/orgs/{org}/dimensions/{id}/values/{value_id}`（单取值）——只读端点

行为细节按「开工口径裁定」（见下）+ design §6.2 行文 + m2-6 members/values CRUD 先例（key 冲突 409、审计同事务入 outbox、org_scoped、404/400 语义）。

### B. issue #14：组织停用载体 + 停用语义

- `orgs.status` 列（active/disabled，默认 active）——双方言迁移
- 停用端点：`PATCH /api/orgs/{org}`（status 载体；UI 已按此 contract-first 预留——m3-UI 挂账②）
- 停用语义按「开工口径裁定」（见下）实装 + 用例覆盖
- `GET /api/orgs` 响应补 status 列（sysadmin 全量 / 普通用户 membership）

### C. G-24①：sem_restricted 管理面授予入口

- 授予载体现状：membership `role='sem_restricted'`（m2s-6，POC 仅 DB/dev 工具授予）
- 本段补管理面入口：复用 members 写路径 role 枚举扩展（POST/PATCH members 允许 role='sem_restricted'；org_admin 门控 + org_admin 不兼任约束〔T-S9 既有口径〕+ 审计同事务）——若调研发现更自然入口（独立端点），开工时申报裁定
- known-gaps G-24① 划销（docs 批监督侧落笔）

### D. issue #20 be-①②（契约冻结——issuecomment-6649900631，逐条照此实装）

**D-① 文档列表 `GET /api/orgs/{org}/documents`**：
- 查询参数：`dataset?`（单库过滤）· `limit?`（默认 50，1..200）· `offset?`（默认 0）
- 响应：`{ "documents": [ { doc_id, title, dataset, dims: {key: [values]}, active_version, active_status, active_error, pending_version, pending_status, chunk_count, quality_open, updated_at, visible } ], "total" }`
- 语义：org_admin = 本组织全量（visible 按行回填，管理面对账用）；member = 服务端 ACL 过滤后仅可见行（visible 恒 true）；行集不含 tombstone、含 pending 处理中文档（双态字段与单文档 GET 同构）；dims 聚合与检索路同源（document_dimensions——D22）；排序 updated_at DESC；跨组织/停用组织 404·403 语义与既有端点一致

**D-② 可见性解释 `GET /api/orgs/{org}/documents/{doc_id}/explain?user_id?`**：
- 权限：user_id 缺省 = 解释自己（本人可见/不可见均可解释）；给他人解释须 org_admin（否则 403）；文档不在本组织 404
- 响应：`{ "doc_id", "visible": bool, "rows": [ { kind: "membership"|"dimension", key?, label, verdict: "allow"|"deny"|"skip", detail } ] }`
- 行序：成员关系（第 0 步——过期即 deny 收口）→ 逐 active 维度：文档有值→与有效授权求交（交集 allow / 无交集 deny / 授权已过期 detail 注明等效无授权）；文档空值→skip 放行；retired 维度不出现
- 语义红线：**只解释不裁定**——检索路仍以 ACL 编译产物为唯一权威；不泄露跨组织数据；结论与编译产物同口径（漂移即测试断言）

### E. docs 批（supervised-coding 执笔，coder 供材料）

design §6.2 契约回写（五方法+GET 单维度/单取值+PATCH orgs 停用+be-①② 行）、known-gaps G-24① 划销、TEST-CASES 新用例登记（supervised-coding 落笔；coder 禁改 docs/ 与 prototype/）。

### 开工口径裁定（任务确认时定，避免 spec_confirm 往返）——已全部裁定（用户 2026-11-08「同意」）

1. **#14 停用语义**（✅ 按建议执行）：
   - PATCH /api/orgs/{org} 权限：sysadmin 专属（org_admin 不能停自己的组织——防误操作锁死；与 POST orgs 同门控）
   - 停用后行为（fail-closed）：该组织所有 `/api/orgs/{org}/...` 端点一律 403（认证 token 仍有效但组织上下文拒绝）；MCP 会话同 403；webhook 拒绝；进行中任务让跑完（不中断），新任务投递拒绝；恢复 = PATCH status=active（幂等）；审计 org.disabled/org.enabled 同事务入 outbox
   - GET /api/orgs 列表：停用组织仍列出（带 status 列），成员关系保留——仅访问面 403
   - 性质认定：design P1-1「组织不可删只能停用」既有决策，本段为实现载体+行为细化——按**非决策变更**处理（版本行声明、D 编号与冻结结论不动）
2. **POST datasets/dimensions 行为细节**（✅ 按建议执行）：POST datasets `{key, title?}` 组织内 key 冲突 409、初始空库、dataset.created 审计；POST dimensions `{key, label, ...}` key 冲突 409、默认 enabled=true/required=false（required 仅影响上传——D5）、dimension.created 审计；两者均 org_admin 门控
3. be-①② 契约已冻结 ✅（无需再裁定）

### 验收标准

1. 门禁 **1715+1 起零回归**（双后端双模式 0 skipped、pg 臂收集数 >0）——新增用例全部双后端参数化（含 REST 端到端 `[pg]` 条目——m2-5 REST-PG 先例）
2. 新端点越权面：纳入 TC-OPS-09 式越权扫描（跨组织 404/403、member vs org_admin vs sysadmin 边界、停用组织 403）
3. D-①② 逐条对照冻结评论实现+用例（explain 与 ACL 编译产物同口径断言——「漂移即测试断言」红线）
4. 审计同事务（新端点写操作全入 outbox）
5. 分层纪律：core 无方言 SQL（store/<dialect> 双方言）、auto_entities 钉 api/mcp 层、import-linter 零违例
6. coder 禁改 docs/ 与 prototype/（docs 批由 supervised-coding 落笔）；TEST-CASES 验收口径变化经用户确认后由 supervised-coding 落笔
7. 开发/提交固定 develop_opencode（commit `[task-knowledge-lattice-m3-1] R<n>`，commit 前同步 origin/develop——当前 origin/develop=cb340f5 已含前置编排批 507b017）；PR base=develop
8. issue #13/#14/#20 关闭材料（交付时回写）

### 硬约束

- 门禁基线：1715+1 双后端双模式 0 skipped（pg 臂 guard 633=599 参数化+34 专用）；skip = 失败
- `docker start lattice-pg` + `LATTICE_PG_DSN` 起 pg 臂；测试命名沿前缀惯例（api_/az_/e2e_…）
- D-①② 契约形状以 issue #20 冻结评论为唯一权威，不得偏移（偏移 = 需求边界问题上报，不擅自改）

## 需求确认
- [x] 用户已确认（2026-11-08 09:27「同意」——任务范围+验收标准+两条口径裁定按建议执行；status=spec_confirm→implementing）
- 历史遗留事项清单：（supervised-coding 扫描历史检查点汇总，默认并入新任务，见 README §4.6）
  - **并入本任务**：m2-5 移交 M3 backlog ①（#13 五方法+GET 单维度/单取值）②（#14 组织停用）——本任务 A/B 组；G-24① sem_restricted 授予入口——C 组；issue #20 be-①②（用户拍板 2026-11-05 并入，契约已冻结）——D 组
  - **不并入（去向已登记）**：③语义 gate G-24⑨→m3-3；④m2s-6 语义 followups 四项→m3-2/m3-3；G-22 查询级审计→m3-2（UI 零改动）；#16 conftest teardown→m3-4；部署期三件 + TC-UI-01~05 人工走查（用户侧）——均不阻塞本段
  - **已清偿确认**：m2-5 挂账「工作区未入库随 m3-1 chore 归档批入库」——经核 task-knowledge-lattice-m2-5.md、_m3-plan.md、AGENTS.md 均已随 PR #21（cb340f5）入库，无需处理；_m3-plan §二该条随本段收尾勾销
  - **后继（不在本检查点）**：ui-be 前端对账轮（本段交付后触发——api.js contract-first 单函数对齐真契约+降级撤除+矩阵/explain 实装+mem.known→GET members 真源化；沿 M3-UI 会话「规格+委派+验收」轻流程，不新增段序占位）

## 遗留事项（跨任务移交）
- [x] **本轮清偿**（2026-11-08 交付，双 SHA=33fb815）：m2-5 移交①#13 五方法+GET 单维度/单取值（A 组）；②#14 组织停用载体+语义（B 组，裁定口径逐条）；G-24① sem_restricted 授予入口（C 组）；issue #20 be-①② 实现面（D 组，契约冻结评论逐条对照）；_m3-plan 挂账「工作区未入库随 m3-1 chore 归档批」（实际已随 PR #21 入库，本检查点随本段 chore 归档批入库）。
- [ ] **移交 m3-2（用户裁定 2026-11-08：ui-be 轮取消独立轮次并入）**：①前端对账——api.js contract-first 单函数对齐真契约（createDataset {name,description}→{key,title?}、createDimension {key,name,required}→{key,label}、PATCH orgs X-Org-Id 头一致性按调用对齐）、be-①/be-②/m3-1 建库建维度/停用降级横幅撤除、docs 视图 visible 徽标列+doc pane explain 卡+可见性矩阵实装、mem.known→GET members 真源化、GET members 替换 export-CSV 名单源；②后端小修——P3-1 pg list_members（+存量 list_orgs_for_user）expires_at to_char 归一+双后端断言、P3-3 未用导入清理、**边界① detail 文案改口径**（membership deny 行 detail「成员关系无效，维度行仅供参考」）；③顺手——P3-2 宽捕收窄/P3-5 同名 409 文案区分/P3-6 测试缺口 4 项/P3-7 __all__/P3-8 POST extra=forbid 统一；④m3-2 既有范围不变（G-22 查询级审计+T-S9⑥+G-24②⑧）。
- [ ] **移交 m3-3**（不变）：G-24⑥⑦⑨、G-23 残余、code versioning、R1 P3 残留。
- [ ] **移交 m3-4**（不变）：#16 conftest teardown + warnings 治理（Tester P3②）。
- [ ] **issue 状态**：#13/#14 随本段 PR 合入后关闭；#20 be-①② 已交付、issue **待 m3-2 前端对账收尾后关闭**（原「ui-be 轮」职责转移 m3-2——用户裁定 2026-11-08）。
- [ ] **用户侧（不阻塞）**：TC-UI-01~05 人工走查维持（走查按 report-ui3-tc-ui-walkthrough.md；m3-2 前端对账后如有 UI 变化需复验相关步骤）。
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1: coder 完成（2026-11-08 10:15 报告，**全新会话**，coderTaskId=ses_e473a6ec4ffehxosh9HoSIpJM0，commit `33fb815` 于 develop_opencode，23 files +3042/−74，父提交=cb340f5（origin/develop 同步确认无前进），未 push；监督侧机械核验 ✓ HEAD/父提交/文件数一致）——**A** ✅ #13 五方法+GET 单维度/单取值（GET members 含过期行 org_admin 门控/POST·PATCH datasets key→id 列冲突 409+dataset.created·updated 审计/POST·PATCH dimensions 默认 enabled=true·required=false+retired 409+status 归退役端点 400/GET values 含 disabled 行/单维度·单取值只读 org_scoped 读面）；**B** ✅ #14 停用（0011 双方言迁移 orgs.status CHECK/PATCH orgs sysadmin 专属幂等翻转+org.disabled·enabled 同事务审计/停用 fail-closed：org_scoped·resolve_request_org·search·MCP _auth_and_org·webhook 验签后·reindex/audit 六处统一 403 org_disabled；进行中任务让跑完〔worker 不查组织态 b4 实证〕新投递入口拒绝；GET orgs 补 status 列停用仍列出）；**C** ✅ G-24① members role 枚举扩展 sem_restricted（api 层枚举+单值列天然不兼任 org_admin+唯一 admin 守卫兼容 409——c4 实证；无独立端点偏离）；**D** ✅ be-①②（D-① 13 字段全量+total+limit 1..200 越界 422+org_admin 全量 visible 按本人编译产物回填/member visible_documents_page 恒 true+pending 含入+dims _attach_dims 同源+updated_at DESC NULLS LAST 双方言；D-② membership 第 0 步 deny 收口→逐 active 维度 key 序求交 allow/deny·空值 skip·retired 不现·过期授权 detail 注明；user_id 缺省自解释·他人 org_admin 403·跨组织 404；**test_d11 矩阵 9 成员×5 文档全组合 explain.visible == compile_acl 同口径断言**）。择型申报 7 条（admin 面 visible=调用者本人视角/停用拦截统一 _require_org_active 六处+PATCH orgs 自身不拦〔恢复可达〕/GET values 含 disabled/explain membership label=org_id/datasets key→id 列映射/status 拒绝 400/过期成员自解释经 org_admin 代解释可达）。自测：TDD 红→绿（36 failed→38 passed×双臂）；GATE PASS **1791+1**（基线 1715+76 新增=4 文件×sqlite/pg 双臂各 38；pg 臂 671=637+34 全实跑）；分层纪律 ✓（SQL 全下沉 store 双方言/test_sem_00_layering 过）；docs/prototype 零改动（diff=0 核验）。

- R1: tester **PASS**（2026-11-08 10:30，**全新会话**，testerTaskId=ses_e470eb7c3ffekQYY7IfQv2dBz2，testedSha=33fb8150c9f77551146e28e271828cda7ce8fd3e 复核一致）——门禁独立复跑 **GATE PASS 1791+1 双后端双模式 0 skipped**（pg 臂 671=637 参数化+34 专用；1715+76 对账闭合：4 新文件×双臂各 38，pg 参数化 599+38=637）。逐项勾验 A/B/C/D 全 ✅（B 停用五要素逐条实证：sysadmin 专属门控矩阵/六处 fail-closed 403 落位〔upload.py:99·132/search.py:58/mcp/server.py:229/semantic.py:536 验签后/reindex·audit 自守卫〕/任务让跑完 b4/恢复幂等同值零新审计/GET orgs status 双面；D 契约冻结评论逐字比对：D-① 13 字段+total 精确断言+limit 422+双 admin 视角互证+member 行集 CTE 精确集合+pending 同构+数量不泄露；D-② 行序 key 序断言+三 verdict+过期授权 detail+membership 第 0 步收口+retired 不现+**test_d11 矩阵 9 成员×5 文档 45 组合 explain.visible==compile_acl 独立计算布尔恒等——红线最强形态核验达标**；pg B⑦ to_char 归一跨后端一致）。**择型 7 条全 ACCEPT**（无 REJECT 无供上报——admin visible 本人视角/六处拦截+PATCH 不拦逻辑必然/values 含 disabled D19 口径/label=org_id 契约未冻结/key→id 映射从严不放宽/status 400 同构/过期自解释 403 与检索路同口径）。**注入 2/2 红→恢复**（①explain visible=True 漂移→6 failed 含 d11 矩阵；②_require_org_active 摘除→3 failed；git diff src/ 零残留）。**回归零弱化**（存量测试函数删除 0；4 存量文件纯迁移号机械顺延+断言不变；0 skipped 逐个核对无新增 skip 逻辑）。分层 ✓（core/semantic 零改动、SQL 全下沉、import-linter 绿）；docs/prototype 白名单 ✓。**P1 无；P2 无；P3×2**（①test_docs_explain_m31.py:28 ORG_GL import 未用可删②门禁 172 条 warnings 存量噪音非本段引入）。临时产物清理 ✓（gate.log/注入备份删、src/ 零残留、.env 未读）。报告全文见「最新验证意见原文」（R1 Tester）。

- R1: committer **APPROVED**（2026-11-08 10:43，**全新会话**，committerTaskId=ses_e4700f2e3ffe2DHytNqnum4jqT，reviewedSha=33fb8150c9f77551146e28e271828cda7ce8fd3e=testedSha=HEAD 三一致；diff cb340f5..33fb815 23 files 逐文件核对；门禁采信 Tester 独立复跑〔同 SHA 其后无提交，沿 m2-5 先例声明〕+静态对账闭合〔38/臂→76、1715+76=1791、pg 637+34=671、0 skip、0 test 函数删除〕；白名单 ✓ core/web/docs/prototype 零触碰；契约冻结评论已取原文逐条比对）——**P1 无；P2 无；P3×8**：P3-1 pg list_members（及存量 list_orgs_for_user）expires_at 未 to_char 归一——双后端 JSON 形态不等价（B⑦ 面唯一例外，Tester「B⑦ 归一」措辞仅对 explain 两方法成立需校正），建议随 ui-be 轮修+补双后端断言；P3-2 审计 outbox PK 理论碰撞被宽捕掩码（沿 m2-4 ④/m2-5 R2 先例收窄）；P3-3 未用导入（semantic.py:534/test_docs_explain 3 处）；P3-4 _require_org_active 注释与调用序不符（search/MCP 在成员校验前调——非成员多 1 bit 停用信息，fail-closed 不受影响）；P3-5 建库同名（UNIQUE(org_id,name)）409 文案误导（key/id 与 name 冲突混一）；P3-6 测试缺口 4 小项（description null 清空/X-Org-Id 不一致 400/sysadmin 无成员关系 403/b4 无新任务行断言）；P3-7 render_documents_page_select 未入 __all__；P3-8 POST 请求体 extra 宽松不一致（POST status 静默忽略 vs PATCH 400）。**测试质量结论：真实路由端到端非伪绿，d11 矩阵恒等+注入 6 红/3 红断言强度达标**。**需求边界问题×2（供上报不交 coder）**：①D-②「过期即 deny 收口」字面 vs 实现 membership deny 后仍展开维度行（detail 可能声称「有效授权 []」而成员过期不清理授权行——事实不准确；visible 结论 d11 锁定不受影响；选项 A 保持展开改 detail 口径 / B membership deny 截断行集）；②停用「新任务投递拒绝」仅拦用户面入口——后台维护链（日度兜底 sync/semantic_build/retag/全库 reembed forced build）仍可为停用组织投递（worker 不查组织态；「让跑完」语义的自然延伸）；建议裁定豁免口径或登记缺口。**docs 批建议清单**（design §6.2 逐行注记+新增 3 行+实现状态注记更新/known-gaps G-24① 划销/TEST-CASES m3-1 组登记+§六 M3 行/AGENTS·_m3-plan 状态/issue #13·#14 关闭材料+#20 待 ui-be 收尾/RUNBOOK 可选）。**遗留去向**：ui-be 前端对账轮（契约差异已定位：createDataset {name,description}→真契约 {key,title?}/createDimension {key,name,required}→{key,label}/PATCH orgs X-Org-Id 头一致性/GET members 替换 export-CSV 名单源/降级横幅撤除+矩阵·explain 实装）；P3-1/P3-3 随 ui-be；warnings 治理→m3-4；边界×2→supervised-coding spec 确认。manifest 要点已给（双 SHA/rounds=1/verdicts/specRulings/gate adoptedFrom 注明 committer 未独立复跑/boundaryQuestions×2/handover）。报告全文见「最新验证意见原文」（R1 Committer）。

- **双通过达成（2026-11-08 10:43，round=1 收敛）**：testVerdict=PASS + reviewVerdict=APPROVED，testedSha=reviewedSha=33fb8150c9f77551146e28e271828cda7ce8fd3e=当前 HEAD——status=approved，待用户确认交付（含 2 条需求边界问题需用户裁定——见 R1 Committer §二；裁定若涉代码改动走 R2 小轮，若登记豁免则随 docs 批注记）。
- **交付裁定（2026-11-08 10:45，用户「没有专门的UI轮次了，并入M3-2吧」——status=approved→归档中）**：**边界①选 A**——explain membership deny 保持维度行展开（保管理面对账信息），detail 改口径「成员关系无效，维度行仅供参考」（不得声称「有效授权 []」）——文案修复**落 m3-2**；**边界②豁免口径**——停用=冻结**用户访问面**，系统维护链（日度兜底 sync/semantic_build/对账 retag/全库 reembed forced build）豁免（保数据一致性、恢复不破缺、服务身份不暴露用户面）——随 docs 批落 design 实现口径注记（非决策变更）；**段序调整**——ui-be 前端对账轮取消独立轮次，范围并入 m3-2（前端对账 api.js contract-first 对齐/降级横幅撤除/矩阵·explain 实装/mem.known→GET members 真源化 + 后端小修 P3-1 expires_at 归一/P3-3 未用导入/边界① detail 文案 + P3-2/5/6/7/8 顺手）；交付序列启动（监督侧 docs 批→coder chore 归档批→push+PR base=develop→committer PR review→manifest→用户合入）。
- **交付执行①：监督侧 docs 批完成（2026-11-08 10:50）**——design **v0.9.10**（版本行非决策声明+§6.2 表格 m3-1 注记 8 处+新增 5 行〔PATCH orgs/GET documents/GET explain/GET 单维度/GET 单取值〕+实现状态注记块 v0.9.10 状态更新〔五方法已实装/停用有载体/sem_restricted 有入口/be-①② 已实装+剩余 P3-1 缺口登记〕+§6.3 sem_restricted 载体注记更新）；known-gaps **G-24① 划销**（概览行 v3 注记——②⑧→m3-2、⑥⑦⑨→m3-3 维持）；TEST-CASES **v1.9.15**（新增 TC-OPS-10 组〔m3-1 四文件 76 用例 A/B/C/D 逐组登记+注入验证〕+TC-OPS-09 m3-1 扩展注记+§六 M3 行 m3-1 段〔门禁 1791+1〕）；AGENTS §1 M3 进行中+m3-1 交付句；_m3-plan row1 done+row2 扩容（ui-be 并入）+§二挂账勾销/改向+§三下段指引 m3-2（基线 1791+1）；RUNBOOK **§1.y 组织停用与恢复**（命令/影响面/维护链豁免/恢复）。工作区 7 文件（6 改+检查点新入库）待 coder chore 归档批。issue 回写（#13/#14 交付评论+PR closing、#20 be-①② 交付评论）随 PR 开出后执行。
- **交付执行②：Coder chore 归档批完成（2026-11-08 10:52 报告，续接会话）**——**chore `bc189f0`**（doc-only 复核 ✓ git diff 33fb815 -- src/ tests/ 为空；7 文件 +398/−26：docs 批 6+检查点新入库）；origin/develop=cb340f5 无前进确认；**push 成功 507b017..bc189f0**（R1 33fb815+chore bc189f0 两提交）；**PR #23 已开**（base=develop，https://github.com/yq3/knowledge-lattice/pull/23 ，body 含四组摘要+门禁证据+`Closes #13`/`Closes #14` closing keywords〔#20 注明待 m3-2〕+`<!-- EVIDENCE-MANIFEST -->` 占位+评审记录）；**issue #20 评论留痕**（issuecomment-6716383438——be-①② 交付+待 m3-2 收尾）。待办：Committer gh pr review 留痕 → Coder manifest 入 PR description → 用户合入。
- **交付执行③：Committer PR 审查留痕完成（2026-11-08 10:55 报告，续接会话）**——`--approve` 因 GitHub 自审限制失败（PR 作者=yq3，沿 #2~#17 先例），回退 **COMMENTED 形态完整留痕**（review id `PRR_kwDOVZ9dhM8AAAABWqxnGQ`，anchor bc189f0，body 含 APPROVED 结论/双 SHA 33fb815/门禁采信 Tester 独立复跑〔committer 未独立复跑如实注明〕/P3×8 与边界②处置去向/manifest 放行条件/合人留给所有者）；**bc189f0 doc-only 复核通过**（7 文件流程/文档、src/tests diff 空、PR 全量 30 文件=23+7 与本地一致、MERGEABLE）；**发现 2 处 doc 笔误**（①TEST-CASES TC-OPS-10 载体行与 PR 描述 A/C=13、D=12 写反——实为 A/C=12、D=13〔总和 38/臂不变〕②检查点「新增 4 行」实为 5 行；_m3-plan row4 未列 warnings）——监督侧已修 3 处（TEST-CASES 载体行/检查点 5 行/_m3-plan row4 补 warnings 治理）；PR 描述侧笔误随 coder 交付收尾批修。

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

<details>
<summary>R1 Tester 报告（2026-11-08 10:30，testVerdict=PASS）</summary>

# task-knowledge-lattice-m3-1 R1 验证报告

**testedSha**: `33fb8150c9f77551146e28e271828cda7ce8fd3e`（= develop_opencode HEAD，父提交 cb340f5，开工前复核一致 ✓）
**testVerdict**: **PASS**

## 一、门禁独立复跑

| 项 | 结果 |
|---|---|
| 命令 | `docker start lattice-pg` + `LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice scripts/test_gate.sh` |
| 结果 | **GATE PASS：1791 passed / 1 deselected（manual 常驻） / 0 skipped**，双模式（常规 + `python -O`）各 216.69s 全绿 |
| pg 臂收集 | **671 = [pg] 参数化 637 + PG 专用 34** ✓（与 coder 申报一致，>0 门禁守卫过） |
| 用例对账 | 1715（基线）+ 76（新增）= 1791 ✓；76 = 4 新文件 × 双臂各 38 ✓；pg 参数化 599+38=637 ✓（38 用例全部双后端参数化）；pg 专用 34 不变 ✓ |

## 二、逐项勾验（对照检查点任务原文 + 裁定口径 + issuecomment-6649900631 契约冻结原文逐字比对）

**A（issue #13）✅**：7 端点全实装——GET members（org_admin 门控+过期行如实列出，test_a1）、POST/PATCH datasets（key→id 映射、组织内 key 冲突 409、初始空库以 SQL 直查断言 documents=0、dataset.created/updated 审计 payload 断言，test_a2/a3）、POST/PATCH dimensions（默认 enabled=true/required=false API 响应+DB 行 (1,0) 双核、retired 409、**PATCH status→400 归退役端点**，test_a4/a5）、GET 单维度/values 列表（含 disabled）/单取值（test_a6/a7/a8）。行为面断言抓 D5 本义：enabled=false 后 `read_grants` 仍含 region=CN（test_a5:231）。

**B（issue #14）✅ 五要素逐条**：
1. sysadmin 专属：org_admin（本组织/他组织）403、member 403、无认证 401、sysadmin 200（test_b2 + test_az_scan 门控矩阵）✓
2. 六处 fail-closed 403：**org_scoped**（upload.py:99）/ **resolve_request_org**（upload.py:132）/ **search**（search.py:58）/ **MCP _auth_and_org**（mcp/server.py:229 ToolError 403）/ **webhook 验签后**（semantic.py:536 先取态、验签过才 403——无签名仍 401 不泄露，test_b3c 双断言）/ **reindex·audit 自守卫**（admin.py:885/1027）——全部落位实证 ✓
3. 进行中任务让跑完：inline worker 轮询 pending 任务到终态 + 新上传 403（test_b4）✓
4. 恢复幂等：同值重复 200 零新审计（org.disabled 恰 1 条/org.enabled 恰 1 条）+ 恢复后端点回通 200（test_b5）✓
5. GET orgs 补 status 列：sysadmin 全量面 + membership 面双断言、停用组织仍列出（test_b6）✓
- 迁移 0011 双方言同构（ADD COLUMN status TEXT NOT NULL DEFAULT 'active' + CHECK）；`set_org_status` 实现幂等语义正确（`UPDATE ... AND status != :status` → rowcount 判 applied、不存在返回 None、翻转同事务入 outbox）

**C（G-24①）✅**：`_MEMBER_ROLES` 枚举扩展 sem_restricted（POST/PATCH members 双面，test_c1/c2）；非法 role 仍 400（superadmin/viewer——fail-closed 不放宽，test_c3）；唯一 admin 守卫兼容——双 admin 可降、唯一 admin 降 sem_restricted 409 防自锁（test_c4）。

**D（issue #20 契约冻结评论逐条）✅**：
- D-①：**13 字段+total 精确断言**（test_d1 `字段全集 ≤ set(row)`）、limit 1..200（0/201→422）、offset 分页不重叠、updated_at DESC 全页非升序断言、dataset 过滤+不存在库空集 200、org_admin 全量 visible 按调用者本人编译产物回填（admin_tax 无授权/ admin_full 4 真 1 假两视角互证，test_d1/d1b）、member 行集=visible_docs CTE 过滤精确集合断言 + visible 恒 true + total 过滤后计数（test_d2）、pending 处理中文档在行集（双态字段同构）+ chunk_count/quality_open 同源计数 + member 面数量不泄露（test_d4）
- D-②：行序 [membership, region, tax_type]（key 序）断言（test_d5）、deny/skip/allow 三 verdict + 过期授权 detail 注明（test_d6/d7）、membership 第 0 步收口（过期成员自解释 403——与检索路同口径；admin 代解释 membership deny 注明过期；无成员关系 deny，test_d8）、权限边界（member 代他人 403/admin 代他人 200/自解释含显式 user_id 200/文档不在本组织 404/跨组织 403，test_d9）、retired 维度不出现（test_d10）、停用取值收紧与编译产物同口径（test_d12）
- **「漂移即断言」红线核验（独立强度审查）：test_d11 = 9 有效成员 × 5 文档全 45 组合，`explain.visible is expected` 布尔恒等断言（expected 来自 `compile_acl+visible_doc_ids` 独立计算）**——这是最强形态的同口径断言，不依赖手写预期，抽验达标 ✓
- pg 侧 `to_char(expires_at,'YYYY-MM-DD HH24:MI:SS')` B⑦ 字符串契约归一，与 `utc_now_ts()`（CURRENT_TIMESTAMP 同格式）字符串比较链路跨后端一致 ✓

## 三、择型申报 7 条裁定——**7 条全 ACCEPT，无 REJECT，无「供上报」项**

| # | 申报 | 裁定 | 理由 |
|---|---|---|---|
| 1 | admin 面 visible=调用者本人视角 | ACCEPT | 冻结评论「visible 按行回填，管理面对账用」——行级判据主体只能是调用者；test_d1/d1b 双 admin 视角互证；泄露面仅 admin 本人可见性，不泄露他人授权 |
| 2 | 停用拦截统一 `_require_org_active` 六处 + PATCH orgs 自身不拦 | ACCEPT | 六处落位实证；PATCH 不拦是逻辑必然——sysadmin 无成员关系过不了 org_scoped，且恢复路径必须对停用组织可达（否则停用不可逆锁死） |
| 3 | GET values 含 disabled | ACCEPT | D19 重新启用恢复路径的既有口径要求停用值可见；行含 status 如实展示，非放宽 |
| 4 | explain membership label=org_id | ACCEPT | 契约只冻结 rows 形状与行序，label 内容未冻结；membership 行无更自然标签载体 |
| 5 | datasets key→id 列映射（契约字面 `{key, title?}` vs 表无 key 列） | ACCEPT | 本段无 schema 变更；id=key、name=title(缺省=key) 满足口径裁定②字面；冲突语义从严（id 全局 PK 冲突 ⊇ 组织内冲突）不放宽；契约冻结评论对 datasets POST 回读形状未冻结，无违背 |
| 6 | status 非法值 400 | ACCEPT | 与 dimension PATCH status→400 同构（显式语义校验优于 pydantic 422）；test_b2 覆盖 |
| 7 | 过期成员自解释经 org_admin 代解释可达 | ACCEPT | org_scoped 成员校验=组织上下文准入，过期即 403 是 fail-closed 必然（与检索路 compile_acl 第 0 步收口同口径，test_d8 显式断言一致性）；契约「解释自己」针对有效成员；代解释语义完整且 admin 本有管理面 |

## 四、注入验证（2 组，沿 m2-5 先例）

| 组 | 注入 | 结果 | 恢复 |
|---|---|---|---|
| ① | `documents.py` explain `visible = all(...)` → `visible = True`（模拟与编译产物漂移） | **红**：6 failed——test_d5/d6/d7/d8/**d11（矩阵恒等）**/d12 全部抓到（`assert True is False`） | 逐字节恢复（备份 diff 验证） |
| ② | `upload.py` `_require_org_active` 拦截摘除 | **红**：3 failed——test_b3（全端点扫描）/test_b4（新投递 403）/test_az 新端点扫描（证据：`GET /members → 200 vs 期望 403`） | 逐字节恢复 |
| 残留核验 | `git diff 33fb815 --stat -- src/` = 空 ✓；`git status --short -- src/` = 空 ✓；临时备份已删 | — | — |

## 五、回归零弱化

- 存量测试函数删除数 = **0**（git diff 无删除行、无文件删除/改名）
- 4 个存量改动文件（scaf_03/v11_schema/regress_m0a1/pg_scaff）逐行核对：**纯迁移号机械顺延**（0011 内置占用→自制迁移 0012~0014）+ 0011 断言新增，断言强度不变
- skip 逐个核对：**门禁 0 skipped**；grep 命中的 3 处均为既有 fail-closed 兜底（PG_DSN 未设则 skip→门禁视为失败的既有机制），本段未新增任何 skip 逻辑
- 注入后恢复复跑：4 新文件双臂 **76 passed** 全绿确认

## 六、分层/白名单核验

- `core/`、`semantic/` 零改动（diff 为空）——新增 SQL 全部下沉 store/双方言 16 方法，explain 消费既有 `compile_acl` 产物，「只解释不裁定」架构面成立 ✓
- `auto_entities` 未在改动清单、未触碰 ✓
- `git diff --stat cb340f5..33fb815 -- docs/ prototype/` = **空** ✓（coder 禁改 docs/prototype 遵守）
- import-linter = test_sem_00_layering 在门禁 1791 内绿 ✓

## 七、分级发现

- **P1（阻塞）：无**
- **P2（应修）：无**
- **P3（建议）×2**：
  1. `tests/test_docs_explain_m31.py:28`——`ORG_GL` import 未使用（该文件全文仅 import 行出现 1 次），lint 噪音；可删。不影响判定。
  2. 门禁 172 条 warnings（InsecureKeyLengthWarning / docling+pydantic DeprecationWarning）——存量噪音非本段引入，登记不阻塞；建议后续段统一治理。

## 八、结论

**testVerdict: PASS**——门禁独立复跑 1791+1 双后端双模式 0 skipped 全绿；A/B/C/D 四组逐条勾验全过（含契约冻结评论逐字比对、test_d11 矩阵红线断言强度独立核验达标）；择型 7 条全 ACCEPT；2 组注入验证测试有效性证实且业务代码零残留；回归零弱化。建议编排方推进 reviewer 审查。

**临时产物清理申报**：gate.log 已删；注入备份（documents.py.bak/upload.py.bak）已删；业务代码经 `git diff 33fb815 -- src/` 复核零残留；`lattice-pg` 容器保持运行（项目标准门禁基础设施，非测试专用进程，供后续轮次使用）；.env 未读取。

</details>

<details>
<summary>R1 Committer 报告（2026-11-08 10:43，reviewVerdict=APPROVED）</summary>

# task-knowledge-lattice-m3-1 R1 审查报告（Committer）

## 审查对象与基线核对

| 项 | 核对结果 |
|---|---|
| review 对象 | `33fb8150c9f77551146e28e271828cda7ce8fd3e` = `develop_opencode` HEAD = `testedSha`；`reviewedSha` 检查点为 null（R1 首审）✓ |
| diff 基线 | 父提交 `cb340f5` = `origin/develop`（`git rev-parse` 三方一致）✓；23 files +3042/−74 与申报一致 ✓ |
| 分支 | `develop_opencode...origin/develop_opencode [ahead 3]`，未 push；工作区仅检查点文件 untracked（无临时产物/业务代码残留）✓ |
| 白名单 | `git diff --stat cb340f5..33fb815 -- docs/ prototype/` 与 `-- src/knowledge_lattice/core/ src/knowledge_lattice/web/` 均为空 ✓ |
| 契约权威 | issue #20 冻结评论 `issuecomment-6649900631` 已取原文逐条比对（D-①/D-②）|
| 门禁 | **采信 Tester 独立复跑**（同 SHA、其后无任何提交；沿 m2-5 先例声明）：1791 passed / 1 deselected / 0 skipped、pg 臂 671=637+34、双模式。**Committer 未能独立复跑**——本会话 bash 策略拒绝 `uv run pytest`（非代码问题），改以静态对账：4 新文件 test 函数 12+8+13+5=38/臂 → 76；1715+76=1791；pg 参数化 599+38=637 +34=671，链式闭合 ✓；diff 中 0 个 `pytest.mark.skip/skipif`、0 个 test 函数删除、存量 4 文件仅迁移号机械顺延 ✓ |

逐文件核对：migrations 0011 双方言同构（ADD COLUMN status NOT NULL DEFAULT 'active' + CHECK）；store protocol 14 个新方法双方言各有实现（含 `render_documents_page_select` 双方言）；api 6 处停用拦截落位；explain 只解释不裁定（消费 `compile_acl` 同一产物）；D-①/D-② 字段与语义逐条对照冻结评论；新写路径审计均与业务写同事务入 outbox。

---

## 一、问题清单

**P1（阻塞）：无。**
**P2（应修）：无。**

**P3（建议，不阻塞；按优先级）**

1. **P3-1 跨后端 `expires_at` 表示形态不一致（B⑦ 面唯一例外）** — `src/knowledge_lattice/store/postgres/backend.py:4292-4304`（`list_members` 直接 `SELECT m.expires_at`，psycopg 回读 datetime）vs `store/sqlite/backend.py:3010-3022`（字符串）。`GET /api/orgs/{org}/members` 在 PG 上经 FastAPI 序列化为 ISO（带 `T`），SQLite 为 `YYYY-MM-DD HH:MM:SS`。本段 explain 的两处数据源（`read_membership_row`/`read_grant_rows`）已 `to_char` 归一 ✓，**仅 `list_members` 未归一**；存量 `list_orgs_for_user`（m2-5 面）同型。影响：非阻断（`normalize_expires_at` 接受 ISO，回写不坏），但 ui-be 轮显示会出现 `01-01T00:00` 形态且双后端 JSON 不等价。建议：pg `list_members` 补 `to_char(expires_at,'YYYY-MM-DD HH24:MI:SS')`（顺带 `list_orgs_for_user`），补一条双后端断言（`isinstance(expires_at, str)` + 逐值相等，仿 `test_admin_store_reads.py:129` 先例）。**注：Tester 报告「B⑦ to_char 归一跨后端一致」仅对 explain 两方法成立，manifest/报告措辞需校正。**
2. **P3-2 审计写入异常被宽捕掩码** — `store/sqlite/backend.py:2286/1716/2328`、`store/postgres/backend.py:1745/1789/1826` 的 `except IntegrityError/UniqueViolation` 覆盖了同一 try 内的 `_outbox_insert`：outbox PK 理论碰撞会被误报为「dataset/dimension 已存在 409」。沿 m2-4 followup④（`upsert_user_jit` 专用上抛）与 m2-5 R2 P3（create_org 同型）先例，建议收窄 try 范围或转专用 RuntimeError。理论不可达，无功能影响。
3. **P3-3 未用导入/变量** — `api/semantic.py:534` `_require_org_active` 导入未用（实际用 `get_org_status`）；`tests/test_docs_explain_m31.py:28` `ORG_GL`、`:29` `FUTURE_TS`、`:384` `token_uid` 未用。建议随 ui-be/下一批清理（Tester P3① 同批）。
4. **P3-4 `_require_org_active` 注释与调用序不符（信息面小口）** — `api/upload.py:106` 声称「调用点均在成员校验之后」，但 `api/search.py:58` 在 ACL 成员校验前调用（MCP `_auth_and_org` 亦在成员校验前）：非成员可探知某组织「已停用」（相对 `membership_denied` 多 1 bit 信息）。fail-closed 不受影响。建议：或在 search/MCP 移至成员校验后（与 org_scoped 同序），或改注释并在 docs 记录该口径。
5. **P3-5 建库同名冲突文案误导** — `api/admin.py:430-438` 将 title→`datasets.name`，schema `UNIQUE(org_id, name)` 冲突被统一映射为「dataset 已存在…key 冲突/跨组织占用」；不同 key 但同名 title 的 409 文案不实。建议区分 name/id 冲突消息，并补 POST/PATCH 同名 409 用例。
6. **P3-6 测试缺口（小项）** — ①PATCH datasets `description: null` 显式清空未测（docstring 已声明语义）；②PATCH orgs `X-Org-Id` 与路径不一致 → 400 未测；③POST/PATCH datasets/dimensions 的 sysadmin（无成员关系）403 未测；④`test_b4` 仅断言上传 403，未断言「无新任务行产生」。均非阻塞，建议下批补。
7. **P3-7 导出纪律** — `render_documents_page_select` 未加入双方言 `__all__`（`store/sqlite/acl_render.py:52-59`、`store/postgres/acl_render.py:47-51`），不影响运行，属风格一致性。
8. **P3-8 POST 请求体 extra 宽松不一致** — `DimensionCreateRequest`/`DatasetCreateRequest` 未 `extra=forbid`（PATCH 均 forbid）：POST dimensions 携带 `status` 被静默忽略，与 PATCH「status→400」口径不一致；建议统一 forbid 或登记。

**测试质量结论**：新用例为真实路由 REST 端到端（TestClient 真实 app + 双后端参数化），非伪绿——`test_d11` 以 9 成员×5 文档 45 组合对 `explain.visible` 与「`compile_acl`+`visible_doc_ids` 独立计算」做布尔恒等断言，且 Tester 注入 `visible=True` 有 6 条红（含 d11）；注入 `_require_org_active` 摘除有 3 条红，源码零残留。断言强度达标。

---

## 二、需求边界问题（供上报，不交 coder 修）

1. **D-②「过期即 deny 收口」字面 vs 实现继续展开维度行** — 实现（`api/documents.py:248-256`）在 membership deny 时仍遍历 active 维度，以空授权集计算 verdict，detail 可能写「无交集授权（有效授权 [] ∩ …）」；而成员过期**不清理授权行**，目标用户实际可能仍有授权（仅成员步收口使其无效），该 detail 属事实不准确。`visible` 结论仍与编译产物一致（d11 锁定）。冻结评论「收口」措辞可读为「仅出 membership 行」。建议 spec 确认：A) 保持展开，但 detail 不得声称「有效授权 []」（改为「成员关系无效，维度行仅供参考」）；或 B) membership deny 即截断行集。
2. **停用组织「新任务投递拒绝」的边界** — 实现只拦用户面入口（上传/reindex/语义触发/webhook）。后台维护链仍可为停用组织投递新任务：每日兜底 sync（`worker/maintenance.py:195-215`）、sync 成功后的 `semantic_build`（`core/semantic/sync.py:390`）、对账 retag（`core/semantic/tagging.py:96`）、全库 reembed 的 forced `semantic_build`（`worker/rebuild.py:255-266`）；worker 执行体不查组织态。建议 spec 明确「系统维护链豁免（停用仅冻结访问面）」或登记已知缺口并补投递面守卫。

---

## 三、Tester 意见裁定

- **P3① `ORG_GL` import 未用**：**确认**（并追加 `FUTURE_TS`/`token_uid`/`semantic.py:534` 同型项）。裁定：非阻塞、不要求本段修；随 ui-be 轮或下一批顺手清理（若走 R2 修复轮可一并）。
- **P3② 172 条 warnings 存量噪音**：**确认登记**。非本段引入（dev JWT 弱密钥 InsecureKeyLengthWarning + docling/pydantic Deprecation），去向测试基建批（m3-4，与 issue #16 conftest teardown 同批）或独立 issue；本段不修。
- **CASE_BUG**：本轮**未收到**裁定请求（Tester 报告无 CASE_BUG，仅 P3×2），无裁定结论。

---

## 四、docs 批建议清单（supervised-coding 落笔，非本轮 coder 范围）

A. **design.md**（版本行声明「非决策变更，D 编号与冻结结论不动」）：
1. §6.2 端点表逐行补实装注记：`GET members`（org_admin 门控、含过期行、username 联查）；`POST/PATCH datasets`（`{key,title?}`、id=key/name=title、UNIQUE 冲突 409、key 不可改、审计同事务）；`POST/PATCH dimensions`（默认 enabled=true/required=false、key 冲突 409、retired 409、**status 归退役端点（PATCH status→400）**、D5）；`GET 单维度/单取值`（org_scoped 读面、retired 如实）；`GET values`（含 disabled、status 列）。
2. **新增行**：`PATCH /api/orgs/{org}`（sysadmin 专属、status 载体、幂等、org.disabled/org.enabled 同事务审计、停用语义与恢复路径）；`GET /api/orgs/{org}/documents`（D-① 逐字段+total+limit 1..200+dataset+排序+visible 双口径+pending/dims 同源）；`GET /api/orgs/{org}/documents/{id}/explain`（D-② 权限矩阵+行序+三 verdict+只解释不裁定）。
3. **改 §6.2 实现状态注记（v0.9.9 块）**：删除「5 个未实现」与「停用无载体」；登记 5 方法已实装、停用已有载体；原「design 无 GET 单维度/单取值」条目改为「本段补齐」。
4. §6.2/§5.6 停用语义注记（P1-1 载体、六处 fail-closed、任务语义、恢复幂等、GET orgs status 列）；`sem_restricted` 管理面入口注记（G-24① 已实装）。
5. （建议）§6.2 补一句 `expires_at` 恒为库格式字符串（与 B⑦ 统一，覆盖 GET members）——若采纳 P3-1。

B. **known-gaps.md**：G-24 行与条目 **①划销**（管理面入口已实装：POST/PATCH members role 枚举 + org_admin 门控 + 唯一 admin 守卫；POC 可直接 API 授予），保留②⑧→m3-2、⑥⑦⑨→m3-3；更新状态列/日期。

C. **TEST-CASES.md**（活文档，新增版本行）：登记 m3-1 用例组——A 组 8 端点（含 expired 行、默认值、conflict 409、status 400、retired 409、values 含 disabled）；B 组（PATCH orgs 门控矩阵/停用全端点 403/MCP 403/webhook 验签后 403/任务让跑完+新投递拒绝/恢复幂等/GET orgs status 双面）；C 组（sem_restricted 授予/非法 role 400/唯一 admin 守卫 409）；D-①②（13 字段+total+limit+分页+排序+dataset+visible 双视角+member 行集不泄露+pending/dims/quality_open；explain 行序/三 verdict/过期 detail/membership 收口/权限矩阵/retired 不现/停用取值联动/**矩阵恒等漂移红线**）；全部双后端参数化；TC-OPS-09/TC-AZ-04 追加新端点扫描注记；§六 M3 行 m3-1 段完成态（门禁 1791+1）。

D. **AGENTS.md §1 / _m3-plan**：M3 首段 m3-1 交付（#13/#14/G-24①/#20 be-①②清偿）；§一 row1→done、§二勾销 backlog；登记 **ui-be 前端对账轮已触发**（不新增段序）；工作区检查点文件随 chore 归档批入库。

E. **issue 回写**：#13/#14 关闭材料（端点清单+测试文件+门禁数）；#20 记录 be-①② 已交付、**issue 待 ui-be 收尾后再关**（冻结评论既定）；G-24① 划销指针。

F. （可选）**RUNBOOK** 停用/恢复运维口径小节（恢复命令、影响面）。

---

## 五、遗留事项去向建议

**本段清偿**：#13（5 方法+GET 单维度/单取值）、#14（orgs.status+停用语义）、G-24①、#20 be-①②（实现面）。

**新移交 / 去向**：
1. **ui-be 前端对账轮（紧接交付触发）**——契约差异已定位：`createDataset` UI 现发 `{name, description}`，真契约 `{key, title?}`（description 仅 PATCH）；`createDimension` 现发 `{key, name, required}`，真契约 `{key, label,…}`；`PATCH orgs` 受 D18 路径/头一致性约束（UI 恒发 `X-Org-Id=cfg.org`，跨组织行操作会 400，需按调用对齐/省略头）；GET documents 字段与 `dataset` 名匹配（limit 200 合法）；GET members 响应 `{members:[{user_id,username,role,expires_at}]}` 替换 export-CSV 名单源；explain/矩阵实装与 `be-①/be-②/m3-1` 降级横幅撤除。
2. **m3-2**：G-22/T-S9⑥、G-24②⑧（P3-1 未在 ui-be 修则随此批）。
3. **m3-3**：G-24⑥⑦⑨、G-23 残余。
4. **m3-4（测试基建）**：Tester P3② warnings 治理 + issue #16 conftest teardown。
5. **边界项**（上节 1/2）→ supervised-coding 回 spec 确认（不交 coder）。
6. 交付流程：docs 批 → coder chore 归档（含本检查点）→ push + PR（base=develop）→ committer gh pr review 留痕 → manifest → 用户合入；**Committer 不合入**。

---

## 六、evidence manifest 要点建议（沿 m2-5 先例）

```json
{
  "head": "33fb8150c9f77551146e28e271828cda7ce8fd3e",
  "testedSha": "33fb815...",
  "reviewedSha": "33fb815...",
  "base": "cb340f5",
  "branch": "develop_opencode",
  "rounds": 1,
  "verdicts": {"coder": "R1", "tester": "PASS", "committer": "APPROVED"},
  "gate": {"command": "LATTICE_PG_DSN=... scripts/test_gate.sh", "result": "1791 passed / 1 deselected / 0 skipped", "pg": "671=637+34", "baseline": "1715+76", "modes": ["pytest", "pytest -O"],
           "adoptedFrom": "tester independent rerun (same SHA, no subsequent commits)"},
  "specRulings": {"kickoff": ["#14 停用语义", "POST datasets/dimensions 细节"], "coderSelections": "7/7 ACCEPT", "testerP3": ["ORG_GL import→后续清理", "172 warnings→登记不修"]},
  "gapClosures": ["G-24①"],
  "issues": {"#13": "implemented, close after merge", "#14": "implemented, close after merge", "#20": "be-①② implemented; issue open until ui-be round"},
  "boundaryQuestions": ["explain membership 收口字面", "停用后后台维护链投递边界"],
  "handover": ["ui-be 前端对账轮（含 POST datasets/dimensions 契约、PATCH orgs 头一致性、GET members/explain 实装）", "m3-2 G-22/G-24②⑧", "m3-3 G-24⑥⑦⑨/G-23", "m3-4 #16+warnings"],
  "stale": false
}
```
另注：Tester 报告「B⑦ 归一」仅覆盖 explain 两方法（见 P3-1 校正）；committer 未独立复跑门禁的事实需如实记入 manifest/PR 描述。

---

## 七、结论

**reviewVerdict: APPROVED**（P1 无、P2 无；P3×8 均为非阻塞建议，其中 P3-1 建议随 ui-be 轮一并修并补双后端断言；两项需求边界问题交 supervised-coding 回 spec 确认）。

- 安全面：跨组织 403/404 边界、member/org_admin/sysadmin 矩阵、SQL 全参数化（新 SQL 无数据值拼接）、审计同事务、fail-closed 六处与 PATCH orgs 恢复可达性均核对通过；**未发现越权/泄露/静默降级**。
- 测试门禁：采信 Tester 独立复跑（同 SHA），静态对账闭合、0 skip、零弱化、注入 2/2 有效。
- 分层/白名单：core 零改动、SQL 全下沉、docs/prototype 零触碰 ✓。
- 交付阶段动作（gh pr review 留痕、manifest 双 SHA 复核）**待用户确认交付后执行**；本轮无 PR、未做任何写入。

</details>
