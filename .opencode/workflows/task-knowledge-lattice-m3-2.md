---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m3-2
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e46e0ea25ffeqWt3t1x5GAB4rz
testerTaskId: ses_e4681cc91ffe9UOA6doKqvN9ly
committerTaskId: ses_e4674cd1effez6sPCw1aaGW0Tx
status: done
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 995d6fd668215e457f0b654f0f63da26a7e3605a
reviewedSha: 995d6fd668215e457f0b654f0f63da26a7e3605a
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [src/knowledge_lattice/query_audit.py, src/knowledge_lattice/domain/audit_events.py, src/knowledge_lattice/core/semantic/constants.py, src/knowledge_lattice/store/backend.py, src/knowledge_lattice/store/audit_chain.py, src/knowledge_lattice/store/sqlite/backend.py, src/knowledge_lattice/store/sqlite/acl_render.py, src/knowledge_lattice/store/postgres/backend.py, src/knowledge_lattice/store/postgres/acl_render.py, src/knowledge_lattice/api/search.py, src/knowledge_lattice/api/semantic.py, src/knowledge_lattice/api/admin.py, src/knowledge_lattice/api/documents.py, src/knowledge_lattice/mcp/server.py, src/knowledge_lattice/app.py, src/knowledge_lattice/web/api.js, src/knowledge_lattice/web/app.js, src/knowledge_lattice/web/i18n.js, src/knowledge_lattice/web/style.css, src/knowledge_lattice/web/views/docs.js, src/knowledge_lattice/web/views/access.js, src/knowledge_lattice/web/views/orgs.js, tests/test_audit_query_g22.py, tests/test_sem_audit_g24b.py, tests/test_qa_ts7_ts8_m32.py, tests/test_admin_m31_endpoints.py, tests/test_admin_store_reads.py, tests/test_docs_explain_m31.py, tests/test_org_disable_m31.py]
endReason: null
createdAt: 2026-11-08T11:04:35+08:00
updatedAt: 2026-11-08T16:05:22+08:00
---

# task-knowledge-lattice-m3-2: 查询级审计批（含 ui-be 并入）

## 任务原文

**M3 第 2 段（_m3-plan §一 row 2；ui-be 独立轮取消并入——用户裁定 2026-11-08「没有专门的UI轮次了，并入M3-2吧」）**。

### A. G-22 查询级异步审计子系统（核心组）

**权威锚点**：FR-6「覆盖查询级（谁/何时/查了什么/返回哪些来源）；**查询级审计异步写，可接受丢失窗口 ≤ 5s**；保留期 12 个月（月库统一）；审计访问分级（org_admin 本组织全量 / sysadmin 仅元数据——查询词与命中详情不含）」+ design §6.3⑥「annotate / get_entity 普通查询走查询级异步审计，**与 docs 查询审计共用月库**」+ §4 月库 `audit_events.detail_json`（查询词、返回的 chunk_id 列表——表设计已就绪）+ §5.6「查询级审计异步写、权限事件走 outbox（月库与业务写天然隔离——#34 4.5）」。

- **覆盖面（按 design/FR 字面）**：docs 侧=REST `POST /api/search` + MCP `search` 工具；语义侧=REST/MCP `annotate` + `get_entity`。`search_entities`/`describe_table`/`l0` 不入（design §6.3⑥ 字面未含——known-gaps 登记开放点，不在本段扩）。
- **载体**：直写月库 `audit_events`（detail_json=查询词+返回 chunk_id/实体 id 列表；哈希链随月库触发器自动入链——TC-OPS-02 既有）；事件常量入 `domain/audit_events.py`（G-24⑧ 顺手统一，含把 `EVENT_SEMANTIC_RESTRICTED_ACCESS` 从 core/semantic/constants 迁入）。
- **异步形态（开工口径裁定①）**：进程内后台批量 flush（≤5s 窗口或满批先刷，月库独立连接、关停 flush）；不走 outbox、不与业务事务绑定（异步弱一致——崩溃丢尾部窗口可接受，登记）。
- **T-S9⑥ 真断言**：无权成员 annotate/get_entity restricted 后——查询级审计可回溯（A-16 口径落地：get_entity 404=refused 记录；annotate 记普通查询如实返回面〔mention 列表无 restricted id——存在性不泄露原则优先，不额外标记〕）；无 outbox 权限事件。TEST-CASES T-S9⑥ 摘「挂起」+ A-16 收口。
- **UI 联动**：零前端改动（ops 视图审计双泳道「查询道」已预留空态注记「待 m3-2」，落地即有数据——GET audit 端点经月库既有查询路径自动可见，验证即可）。
- **G-22 划销**（docs 批监督侧落笔）。

### B. G-24②⑧（顺手组）

- ②持权审计两漏记：get_entity `include=['attrs']` 时 restricted 根实体访问不落审计（审计前提为 curated 非空）；经关系展开「看到」restricted 端点（非根）不审计——补漏记（outbox 权限事件）。
- ⑧审计事件常量入 `domain/audit_events.py` 单一登记处（EVENT_SEMANTIC_RESTRICTED_ACCESS 迁入——与 A 组事件常量同批）。

### C. m2s-6 显式断言三补之另两补（测试补强组）

- T-S7 describe_table/l0 显式断言（现由白名单/成员关系旁证覆盖——补显式断言收口 TEST-CASES 步骤全集）。
- T-S8 真随机向量三路（现确定性 embedder 两路——补真随机向量形态下的三路断言）。
- （T-S9⑥ 为 A 组核心，依赖 G-22 闭环。）

### D. ui-be 前端对账（m3-1 移交——用户裁定并入；#20 issue 收尾）

m3-1 Committer 已定位契约差异（详见 m3-1 检查点 R1 Committer §五）：
1. **api.js contract-first 单函数对齐真契约**：createDataset 现发 `{name, description}`→真契约 `{key, title?}`（description 仅 PATCH）；createDimension 现发 `{key, name, required}`→真契约 `{key, label, …}`；PATCH orgs 受 D18 路径/头一致性约束（UI 恒发 `X-Org-Id=cfg.org`，跨组织行操作会 400——按调用对齐或省略头）。
2. **降级横幅撤除**：be-①（docs 列表）、be-②（explain）、m3-1 建库/建维度/停用 contract-first 降级全部撤除，接真端点。
3. **docs 视图**：visible 视角徽标列（org_admin 面）+ doc pane explain 卡实装 + 可见性矩阵子标签实装（org_admin·逐格取数）。
4. **mem.known→GET members 真源化**：会话注册表退化（零授权成员持久可见+成员行 role/到期补全）；GET members 替换 export-CSV 名单源（成员子标签/授权格 roster/身份菜单 usernames 同源合并保留）。
5. **#20 issue 收尾**：全部 UI 联动完成后监督侧评论+关闭（be-①②+ui-be 职责转移 m3-2 既定）。

前端改动范围：`src/knowledge_lattice/web/**`（不属 prototype/——白名单边界注意）+ `docs/TEST-CASES.md` 相关用例注记（监督侧落笔）。

### E. m3-1 移交后端小修（顺手组）

- **P3-1**（优先）：pg `list_members`（+存量 `list_orgs_for_user`）`expires_at` 补 `to_char` 归一（B⑦ 字符串契约——双后端 JSON 等价）+ 双后端断言（仿 test_admin_store_reads.py:129 先例）。
- **边界①文案**（用户裁定选 A）：explain membership deny 后维度行 detail 改「成员关系无效，维度行仅供参考」（不得声称「有效授权 []」）+ 用例更新。
- **P3-3**：未用导入清理（api/semantic.py:534 `_require_org_active`、tests/test_docs_explain_m31.py ORG_GL/FUTURE_TS/token_uid）。
- **P3-2/5/6/7/8**（应修尽修，不膨胀）：②outbox PK 宽捕收窄；⑤建库同名（UNIQUE(org_id,name)）409 文案区分 name/id 冲突+用例；⑥测试缺口 4 项（PATCH datasets description null 清空/PATCH orgs X-Org-Id 不一致 400/sysadmin 无成员关系 403/test_b4 无新任务行断言）；⑦render_documents_page_select 入双方言 __all__；⑧POST 请求体 extra=forbid 统一（含 status 拒绝语义对齐）。
- warnings 治理**不在本段**（→m3-4）。

### F. docs 批（supervised-coding 执笔，coder 供材料）

design §6.3⑥ 查询级审计实现注记+A-16 收口口径、known-gaps G-22 划销+G-24②⑧ 划销+开放点登记（search_entities/describe_table/l0 不入查询审计）、TEST-CASES T-S9⑥ 摘挂起+显式断言三补完成态+ui-be 对账完成态+新用例组登记、AGENTS/_m3-plan 状态行、RUNBOOK 可选（查询审计观测口径）。

### 开工口径裁定（任务确认时定）——已全部裁定（用户 2026-11-08「同意」按建议执行）

1. **异步形态**（建议）：进程内后台线程/任务批量 flush——满 5s 或满批（如 200 条）先刷、月库独立连接、uvicorn lifespan 关停 flush；崩溃丢尾部窗口 ≤5s 可接受（FR-6 字面——异步弱一致，与 outbox 同生共死语义分工明确）。
2. **覆盖面**（建议）：REST+MCP 的 search/annotate/get_entity 六个入口；refused 含 403（无成员/无权限/停用组织）与 get_entity 404（restricted 静默面）；**search_entities/describe_table/l0 不入**（design 字面，登记开放点）。
3. **采样率**（建议）：100% 全量（FR-6「覆盖查询级」无采样字样；不引入采样 env——过度设计）。
4. **保留期**：随月库滚动 12 个月统一（无单独口径）。
5. **审计访问分级**：查询级事件经既有 GET audit 端点可查——org_admin 本组织全量 / sysadmin 仅元数据（查询词与命中详情脱敏——TC-OPS-03 分级延展，需断言 sysadmin 看不到 detail_json 查询词）。

### 验收标准

1. 门禁 **1791+1 起零回归**（双后端双模式 0 skipped、pg 臂收集数 >0）——新增用例双后端参数化
2. T-S9⑥ 真断言（A-16 收口）+ refused 可回溯断言 + 丢失窗口 ≤5s 断言（异步 flush 语义）+ sysadmin 元数据脱敏断言
3. G-24② 两漏记补齐（outbox 事件断言）+ ⑧ 常量单一登记处（import 检查）
4. ui-be 对账：降级横幅全撤（浏览器级验证——沿 ui-3 先例 playwright DOM/自检）+ mem.known 真源化 + api.js 契约对齐（与真端点往返实测）
5. P3-1 双后端 JSON 等价断言 + 边界① detail 文案断言更新
6. 分层纪律（core 无方言 SQL；月库写收口 store/<dialect>；查询审计不进检索热路径同步等待）+ coder 禁改 docs/ 与 prototype/（web/ 属 D 组白名单）
7. 开发/提交固定 develop_opencode（commit `[task-knowledge-lattice-m3-2] R<n>`，commit 前同步 origin/develop=62613d8）；PR base=develop
8. #20 收尾材料（交付时监督侧评论关闭）

### 硬约束

- 门禁基线：**1791+1**（pg 臂 671=637+34）；skip = 失败；`docker start lattice-pg` + `LATTICE_PG_DSN`
- 查询审计写入**不得显著拖慢查询响应**（异步面——热路径仅入队；NFR-8 检索 SLO 复跑不回归）
- D-①② 契约（issue #20 冻结评论）不因 ui-be 对账而偏移——前端适配真契约，不改后端契约形状（发现契约问题=需求边界上报）

## 需求确认
- [x] 用户已确认（2026-11-08 11:05「同意」——任务范围+验收标准+5 条口径裁定按建议执行；status=spec_confirm→implementing）
- 历史遗留事项清单：（supervised-coding 扫描历史检查点汇总，默认并入新任务，见 README §4.6）
  - **并入本任务**：m3-1 移交 m3-2 全部（①ui-be 前端对账+②后端小修 P3-1/P3-3/边界①文案+③顺手 P3-2/5/6/7/8——m3-1 遗留节）；G-22（m2s-6 登记核心缺口）；T-S9⑥+A-16（m2s-6 挂起项）；G-24②⑧（m2s-6 followups→_m3-plan row2）；m2s-6 显式断言三补之 T-S7 describe_table/l0+T-S8 真随机向量（m2s-6 遗留②「显式断言三补」整体→m3-2）；#20 issue 收尾（m3-1 交付时留痕待本段）
  - **不并入（去向已登记）**：G-24⑥⑦⑨/G-23 残余/code versioning/R1 P3 残留→m3-3；#16 conftest teardown+warnings 治理→m3-4；部署期三件+TC-UI 走查（用户侧）不阻塞
  - **本段清偿后新增移交预期**：无（#20 关闭后 M3-UI 线全部收官）

## 遗留事项（跨任务移交）
- [x] **本轮清偿**（2026-11-08 交付，双 SHA=995d6fd）：G-22 查询级异步审计子系统（六入口/月库直写/≤5s 窗口/链防叉互斥/refused/T-S9⑥+A-16 收口/sysadmin 脱敏）+ G-24②⑧ + T-S7 describe_table·l0+T-S8 真随机向量显式断言 + ui-be 前端对账（api.js 契约对齐/降级全撤/visible 徽标/explain 卡/可见性矩阵/mem.known 真源化/i18n 660）+ m3-1 移交后端小修全清（P3-1/2/3/5/6/7/8+边界①文案）+ #20 issue 收尾（监督侧评论关闭随交付）。
- [ ] **移交 m3-3（含用户裁定 2026-11-08：P2-1 上调为 m3-3 段内修复）**：①**P2-1 pg 单连接共享修复（必做）**——QueryAuditQueue 改收 backend_factory（pg 形态独立连接/连接池单连）或 PgBackend._conn 连接级串行化+pg 臂测试双连接形态；②**链互斥并发测试（首轮必做，Committer P3-2）**——收编 Tester 注入脚本为正式用例（ThreadLocalBackend+barrier+ship_outbox×append_query_events 双线程+walk_chain 断言；pg 随 P2-1 双连接补）+P3-3 qa1b 隔离 stop() flush+P3-4 refused 分支断言补（MCP 停用/REST·MCP annotate·get_entity 拒绝面）；③文案残留 4 键+注释/CSS 清扫（P3-1：i18n :131/:323/:387/:388——access.mem.empty/footNote「无 GET members」矛盾文案+access.js:7/api.js:9-10/338/style.css:568-573）；④未用导入清扫（P3-8：新测试 uuid/RelationRecord/七 helper）；⑤顺路可选：audit 取数 try/except 包裹（api/semantic.py:540-553/mcp/server.py:620-630——500 风险）+flush existed 按批 id 查询（P3-5 同批经济）；⑥m3-3 既有范围不变（#15/G-24⑨语义 gate+G-23 残余+G-24⑥⑦+code versioning）。
- [ ] **登记 known-gaps（开放点，非段承接）**：查询审计覆盖面（search_entities/describe_table/l0 不入——design 字面）；可见性矩阵 m×n 无规模护栏；flush 全月扫描规模化 P3-5（生产化前修，与 P2-1 同批经济）；溢出/丢弃观测面（/stats 未暴露——可随 m3-3 顺手）；查询级 refused 写放大（G-26 延伸）；哈希链 \x1f 前置理论硬化。
- [ ] **移交 m3-4（不变）**：#16 conftest teardown+warnings 治理。
- [ ] **用户侧（不阻塞）**：TC-UI-01~05 人工走查（含本段新形态：矩阵/explain 卡/查询道数据——Committer 注记：D 组浏览器级为 coder 自查申报，不替代走查）。
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1: coder 完成（2026-11-08 12:49 报告，**全新会话**，coderTaskId=ses_e46e0ea25ffeqWt3t1x5GAB4rz，commit `995d6fd` 于 develop_opencode，29 files +2338/−202，父提交=62613d8（origin/develop 同步确认无前进），未 push；监督侧机械核验 ✓ HEAD/父提交/文件数/docs+prototype diff=0）——**A** ✅ G-22 六入口查询审计（REST search+MCP search/annotate/get_entity+REST annotate/get_entity；query_audit.py QueryAuditQueue 满批 200 或 5s 先刷+月库独立连接+lifespan 关停 drain+热路径 O(1) 入队；store 新 append_query_events 双方言直写月库 detail_json；哈希链 compute_row_hash 既有口径；**两写道链防叉互斥**〔sqlite 链基读取入 BEGIN IMMEDIATE〔ship_outbox 顺势加固〕/pg 事务级咨询锁 AUDIT_CHAIN_LOCK_KEY——test_qa9 双道交错三轮〕；refused 全记〔403 无成员/停用/semantic:read+get_entity 404 restricted|not_found 二值〕；T-S9⑥ 三断言〔test_qa6 无权 annotate 如实返回面+get_entity refused 可回溯+零 outbox 权限事件〕；sysadmin 脱敏〔test_qa5 scope=metadata 逐事件剥离〕；丢失窗口 ≤5s〔test_qa1〕+失败回队/防毒丸丢弃计数；action=search.query/annotate/get_entity→ops 查询道零前端改动落地即有数据〔playwright 实证〕）。**B** ✅ G-24②⑧（include=attrs 根实体删「curated 非空」前提+展开端点新 sem_restricted_ids 批量判定并入 entity_ids〔b2c 无 restricted 零事件不虚报〕；EVENT_SEMANTIC_RESTRICTED_ACCESS 迁 domain/audit_events+4 新查询常量入 __all__+test_g24c import 检查全 src 无 core 路径导入）。**C** ✅ T-S7 describe_table/l0 显式矩阵断言（同名 table key 双组织列集隔离+未登记 403+l0 逐片段比对）+T-S8 真随机向量三路（固定种子可复现，CTE 三路 SQL 归一化前缀逐字同构+运行时并集 ⊆ 可见块）。**D** ✅ ui-be 对账（api.js createDataset {key,title?}/createDimension {key,label}/X-Org-Id 调用方显式指定优先+setOrgStatus 按路径对齐；降级横幅全撤〔be-①/be-②/建库/建维度/停用〕；visible 徽标列 admin 面+explain 卡+可见性矩阵 4 并发逐格取数+点格下钻；mem.known→loadMembers 真源化〔名单源=GET members ∪ export ∪ 会话注册表〕；i18n 660=660 零缺零死〔删 12 死键〕；playwright DOM 自检全套）。**E** ✅ 全清（P3-1 to_char 归一+双后端断言/边界① detail 文案+test_d8 断言升级含「有效授权」禁入/P3-3 清理/P3-2 六处收窄 RuntimeError 专用上抛/P3-5 409 文案按约束源分流+test_a2b/P3-6 四项/P3-7 __all__/P3-8 extra=forbid+test_a2c）。择型申报 8 条（action 命名 search.* 域词/链防叉互质/pg 月库同库分区事务+咨询锁承载独立性·生产 app 侧 PG 未接线既有状态/queue 溢出丢最旧+防毒丸+enqueue 即 wake 上界不违/404 reason 二值回查/REST·MCP 拒绝层差异如实/i18n 查询道文案同步/矩阵 m×n 无规模护栏登记开放点）。自测：TDD 红→绿（ModuleNotFoundError 等）；**GATE PASS 1842+1**（基线 1791+51：4 新文件+E 组扩展+既有增强；pg 臂 696=662+34）；i18n 扫描器零缺零死；playwright DOM 套件；NFR-8 抽测（API 层 P95 2.0ms/审计增量 1.4ms<50ms/积压 0——sqlite+FakeEmbedder 简化口径申报）。申报材料：G-22 划销附注开放点（search_entities/describe_table/l0 不入+fetch/list_documents 未列）、异步弱一致登记、矩阵规模护栏、#20 收尾材料、docs 批建议清单。

- R1: tester **PASS**（2026-11-08 13:03，**全新会话**，testerTaskId=ses_e4681cc91ffe9UOA6doKqvN9ly，testedSha=995d6fd668215e457f0b654f0f63da26a7e3605a 复核一致）——门禁独立复跑 **GATE PASS 1842+1 双后端双模式 0 skipped**（pg 臂 696=662+34；+51 链式对账闭合：25 新函数×双臂+1 sqlite-only〔ts8 复用 matrix_env 单臂〕——g22 12+g24b 6+ts7ts8 3+admin 4+store_reads 1）。逐项勾验 A~E 全 ✅（A 六入口 enqueue 全接+flush ≤5s 真断言〔先断「入队不落库」再轮询〕+refused 三因+404 二值回查+T-S9⑥ 三断言+sysadmin 脱敏〔admin.py:1044-1046〕+热路径代码级核验〔enqueue=锁内 deque.append+Event.set 零 IO〕+NFR-8 抽测口径 ACCEPT〔增量 1.4ms 与 embedder 无关，简化不影响结论〕；B 两漏记 b2c 无虚报+import 检查真实文本扫描；C describe_table 200 面内容比对非旁证+T-S8 种子可复现+d_os 显式排除非恒真；D 契约对齐逐条对码+banner 零引用+i18n 独立复跑 zh=en=660 零缺零死复现；E P3-1 非恒真〔修复前 pg 为 datetime〕+边界①禁入断言+P3-2 六处计数实证）。**择型 8 条全 ACCEPT**（③申报属实但未点名 pg 单连接共享机理→单列 P2；⑧矩阵开放点口径成立→供上报 F 组 known-gaps 落笔）。**注入 2/2 有效**（①摘除脱敏→test_qa5 双臂红；②摘除链互斥→并发脚本〔shipper×querier 双线程 120 轮〕CHAIN-BROKEN 红且**暴露 test_qa9 顺序执行捕获面缺口**→P3-②；git diff src/ 零残留）。**回归零弱化**（0 函数删除 0 文件删除；断言增强只增不放宽）。分层 ✓（query_audit.py 顶层编排+SQL 全收口 store；web/ 7 文件白名单合法）；docs/prototype 零改动 ✓。**P1 无；P2×1**（**pg 形态 flush 线程与请求线程共用 self._conn 单连接**——psycopg 无跨线程锁，生产 uvicorn 并发可协议错乱波及请求线程；sqlite 默认形态无此问题；修法=独立连接/连接级串行化；**移交部署期 PG 接线必修**——本段不阻塞）；**P3×2**（①i18n 两键文案残留「待 m3-1 后端轮次」误导〔docs.upload.noDs/access.dims.new.foot 活引用〕②test_qa9 需补双线程并发交错形态〔本轮注入脚本可收编〕）。临时产物清理 ✓（.env 未读）。报告全文见「最新验证意见原文」（R1 Tester）。

- R1: committer **APPROVED**（2026-11-08 13:17，**全新会话**，committerTaskId=ses_e4674cd1effez6sPCw1aaGW0Tx，reviewedSha=995d6fd668215e457f0b654f0f63da26a7e3605a=testedSha=HEAD 三一致；diff 62613d8..995d6fd 29 files 逐文件核对；门禁采信 Tester 独立复跑+静态对账闭合〔**归因更正：单臂函数是 test_g24c 非 Tester 所称 ts8——matrix_env 基于 backend fixture 双臂**〕；docs/prototype 零 diff ✓；分层 ✓）——**P1 无；P2×1**：**P2-1 pg 形态 flush 线程与请求线程共享 PgBackend.self._conn 单连接**（query_audit.py:140→postgres/backend.py:3610/app.py:332；psycopg 无跨线程锁；**生产 app 恒 sqlite（factory 证据）无当前暴露**，pg 臂测试自身走共享形态属稳定性隐患；**裁定：部署期 PG 接线必修、本段不阻塞**——修法 backend_factory 独立连接/连接级串行化+pg 臂双连接；登记 known-gaps open point 不销账）；**P3×8**：P3-1 文案残留**扩展至 4 键**（i18n :131/:323/:387/:388——access.mem.empty/footNote 仍写「无 GET members」与本段真源化直接矛盾+注释/CSS 清扫）→m3-3 顺手批；P3-2 test_qa9 顺序形态无法捕获链互斥回归（注入实证）→**m3-3 首轮必做**（收编并发脚本）；P3-3 test_qa1b 无法隔离 stop() flush（enqueue 即 wake 干扰）同批；P3-4 refused 分支断言缺口（MCP 停用/REST·MCP annotate·get_entity 拒绝面无断言——覆盖率申报夸大）同批；P3-5 flush 全月 id 扫描 O(当月行数)/次+pg last_row_hash 无索引+ensure 分区每轮 DDL（规模化成本——existed 改按批 id 查询/索引/ensure 缓存）→登记 open point 生产化前修；P3-6 溢出/丢弃仅日志不可见于 /stats；P3-7 refused 写放大 G-26 延伸登记（**未认证调用不触发查询审计评估通过**）；P3-8 卫生项（未用导入×10/createDatasetWithDesc 注释与实现不符/access.js:300 注释/哈希链 \x1f 前置理论硬化/audit 取数未包裹 500 风险/**i18n 死键实为 11 删+6 改文案非「12 死键」更正**）。**无需求边界问题**（m3-1 两边界已落地核验：①documents.py:266-275+禁入断言 ②design v0.9.10 注记；PG 未按裁定①字面=择型申报+部署期项非验收矛盾）。**Tester 意见裁定**：P2-1 成立部署期必修/P3-1 成立扩展/P3-2 成立 m3-3 必做；择型 8 条全 ACCEPT 复核（②ship_outbox 加固逐行等价核验——v1.8.3 两步幂等未破坏/⑤EntityNotFound 消息不含 restricted 字样已核）。**docs 批建议**（design v0.9.11 §6.3⑥+A-16 收口+§4/§5.6 注记/known-gaps G-22+G-24②⑧ 划销+开放点 8 项登记/TEST-CASES T-S9⑥ 摘挂起+三补完成态+TC-OPS-11 登记+TC-UI-05 豁免销项/AGENTS·_m3-plan row3 扩容〔P3-1 文案+P3-2 并发测试+P3-3/4 补强〕/RUNBOOK 查询审计观测+PG 接线 checklist）。**遗留去向**：P2-1+P3-5/6/7→部署期/m3-3/m3-4 分流；**#20 收尾材料充分建议评论关闭**（注明 D 组浏览器级为 coder 自查申报+Tester 代码级核验+不替代用户 TC-UI 走查）；manifest 要点已给（codeSha/deliveryHead 双记+doc-only 证据+caveat 如实）。报告全文见「最新验证意见原文」（R1 Committer）。

- **双通过达成（2026-11-08 13:17，round=1 收敛）**：testVerdict=PASS + reviewVerdict=APPROVED，testedSha=reviewedSha=995d6fd668215e457f0b654f0f63da26a7e3605a=当前 HEAD——status=approved，待用户确认交付（交付序列：监督侧 docs 批→coder chore 归档批→push+PR base=develop→committer PR review→manifest→用户合入；#20 随交付评论关闭）。
- **交付裁定（2026-11-08 15:48，用户「P2-1（pg 单连接共享）需要排进M3-3修复，然后交付」——status=approved→归档中）**：**P2-1 去向改判**——Tester/Committer 原裁定「部署期 PG 接线必修」被用户上调为 **m3-3 段内修复**（QueryAuditQueue 改 backend_factory 独立连接或连接级串行化+pg 臂双连接形态；known-gaps 开放点措辞按此落笔）；其余 P3 去向维持（文案 4 键+注释清扫→m3-3 顺手、链互斥并发测试→m3-3 首轮必做、flush 规模化 P3-5→known-gaps 登记生产化前修〔与 P2-1 同批修复经济，m3-3 可顺路〕）；交付序列启动。
- **交付执行①：监督侧 docs 批完成（2026-11-08 15:53）**——design **v0.9.11**（版本行非决策声明+§6.3⑥ 查询审计实现注记收口〔六入口/异步形态/链防叉/refused A-16 收口/脱敏/action 命名〕+日期行）；known-gaps **G-22 划销**（概览+条目完成态）、**G-24 v4 注记②⑧ 划销**、**G-28 新增**（8 分项开放点——③P2-1 m3-3 用户裁定/⑤并发测试 m3-3/①②⑥⑧触发时/④生产化前）；TEST-CASES **v1.9.16**（T-S9⑥ 摘挂起+A-16 收口+TC-OPS-11 新组〔51 收集+注入 2 组说明+D 组 ui-be 完成态〕+TC-OPS-03 延展注记+TC-UI-05 豁免销项暂未逐条〔组级登记〕+§六 M3 行 m3-2 段）；AGENTS §1 M3 进度更新；_m3-plan row2 done+row3 扩容（G-28③⑤ 承接+文案清扫+顺手项）；RUNBOOK **§1.z 查询级审计观测**（形态/日志 grep/查询分级/PG 接线前置）。工作区 8 文件待 coder chore 归档批。#20 评论关闭随 PR 开出后执行。
- **交付执行②：Coder chore 归档批完成（2026-11-08 15:58 报告，续接会话）**——**chore `d19c9a6`**（8 files +466/−19 doc-only，git diff 995d6fd -- src/ tests/ 空）；origin/develop=62613d8 无前进确认；**push 成功 a287604..d19c9a6**（R1 995d6fd+chore d19c9a6）；**PR #24 已开**（base=develop，https://github.com/yq3/knowledge-lattice/pull/24 ，**--body-file 正确使用**〔m3-1 事故教训〕——body 回读双校验 7410 字节完整非路径字符串、锚点 10 处在位；**无 closing keywords**〔#20 监督侧评论关闭〕；MERGEABLE·CLEAN）。待办：Committer PR review 留痕 → Coder manifest → 监督侧 #20 评论关闭 → 用户合入。
- **交付执行③：Committer PR 审查留痕完成（2026-11-08 16:00 报告，续接会话）**——`--approve` 自审限制失败（沿先例），回退 **COMMENTED 完整留痕**（review id `PRR_kwDOVZ9dhM8AAAABWrpDGA`，anchor d19c9a6；body 含 APPROVED 结论/双 SHA〔code 995d6fd·delivery d19c9a6·base 62613d8〕/门禁采信 Tester 1842+1〔committer 未独立复跑注明〕/**P2-1 裁定更新：用户上调 m3-3 修复→G-28③**/P3 去向/manifest 放行条件）；**d19c9a6 doc-only 复核通过**（8 流程/文档文件、src/tests/scripts/prototype 零夹带、链路核对 ✓）；PR MERGEABLE·CLEAN。
- **交付执行④：Coder manifest 入 PR + 监督侧 #20 关闭（2026-11-08 16:03）**——manifest 17 键替换占位（回读双校验通过：10556 字节逐字节一致+json.loads 可解析+21 锚点在位；择型 1 条机械适配 `\x1f`→`\\x1f` JSON 合法转义）；**issue #20 已评论关闭**（M3-UI 线收官——be-①② m3-1+ui-be m3-2 全交付证据+浏览器级自查申报注记+TC-UI 走查指向）。**PR #24 终态：OPEN/MERGEABLE/CLEAN，commits=[995d6fd（R1）, d19c9a6（chore）]，base=develop——待用户合入**（无 closing keywords——#20 已由监督侧关闭）。合入后补记 mergeCommit 条目；该条目之后的工作区改动（检查点）随 m3-3 chore 归档批入库。

- **交付完成（终态）（2026-11-08 16:05，用户确认「合入」，status=done）**：**PR #24 MERGED**——mergeCommit `2fcf280e950eacd83b978e31fb87565385214a01`（mergedAt 2026-11-08T08:05:08Z，merge 形态沿先例、远端分支保留）；origin/develop 前进至 2fcf280，develop_opencode 已 ff 同步；issue #20 已于交付链内关闭（M3-UI 线收官）。**m3-2 段收官：round=1 一轮收敛（coder→tester PASS→committer APPROVED），门禁 1791+1→1842+1，G-22/G-24②⑧ 划销、T-S9⑥+A-16 收口、显式断言三补收官、ui-be 对账+#20 收尾、G-28 新增（P2-1 用户裁定 m3-3 修复）。M3 进度 2/5（m3-3 语义 hardening 批——下一段，含 G-28③⑤ 承接）；本条目之后的工作区改动（检查点）随 m3-3 chore 归档批入库。

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

<details>
<summary>R1 Tester 报告（2026-11-08 13:03，testVerdict=PASS）</summary>

# task-knowledge-lattice-m3-2 R1 勾验报告

**verdict: PASS**（附 P2×1 / P3×2 发现，均不阻塞交付，移交裁定）
**testedSha: `995d6fd668215e457f0b654f0f63da26a7e3605a`**（= develop_opencode HEAD，父提交 62613d8 复核一致）

## 一、门禁独立复跑

```
docker start lattice-pg && export LATTICE_PG_DSN=… && scripts/test_gate.sh
GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
[pytest]   OK：1842 passed, 1 deselected, 171 warnings in 227.72s
[pytest-O] OK：1842 passed, 1 deselected, 172 warnings in 232.39s
pg 臂 696 = [pg] 参数化 662 + PG 专用 34（全实跑）
```

- **1842+1 与 coder 自测一致**，deselected 1 = manual（TC-UI 人工走查，既定口径非 skip）；0 skipped ✓
- **链式对账自洽**：总数 1791→1842（+51）；pg 参数化 637→662（+25）、专用 34 不变（696=637+25+34 与任务口径吻合）；sqlite 臂 +26；新增 test 函数 26 个（g22 12 + g24b 6 + ts7ts8 3 + admin 4 + store_reads 1）= 25 个双臂函数 + 1 个 sqlite-only（ts8 复用 `matrix_env` 单臂 fixture）——51 = 25×2+1 ✓
- warnings 171/172（`python -O` 多 1）——治理挂 m3-4，不进门禁，如实记录

## 二、逐项勾验（A~E）

### A（G-22 核心）✅
| 项 | 证据 |
|---|---|
| 六入口全覆盖 | REST `search.py`（accepted chunk_ids / refused org_disabled+403 code）、`semantic.py`（annotate/get_entity）、`mcp/server.py`（search 传 `query_action`、annotate/get_entity）——六处 `enqueue_query_event` 全接 |
| 异步 flush ≤5s 断言真实性 | `query_audit.py` FLUSH_INTERVAL_S=5.0/BATCH_SIZE=200；test_qa1 先断言「入队不落库」（异步性）再轮询 ≤5s 可见——真断言非恒真；test_qa1b 关停 flush 残留、test_qa1c 瞬时失败回队/连续失败防毒丸丢弃计数 |
| 月库直写+哈希链入链 | 双方言 `append_query_events`（sqlite:2199/pg:3494）直写月库 + `compute_row_hash` 既有口径；**两写道互斥经注入实证有效**（见第四节——test_qa9 本身断言强度不足，见 P3-2） |
| refused 语义 | 403 三因（membership_denied/org_disabled/semantic:read denied）+ get_entity 404 restricted\|not_found 二值回查；test_qa3/qa4/qa7/qa6 |
| T-S9⑥ 三断言 | test_qa6：① annotate 200 如实返回面（mentions 无 restricted id，存在性不泄露）② get_entity 404 refused reason=restricted 可回溯 ③ outbox `semantic.restricted_access` 计数=0 |
| sysadmin 元数据脱敏 | `admin.py:1044-1046` scope=metadata 剥 detail_json；test_qa5 双臂断言 org_admin=full 含 / sysadmin=metadata 逐事件无 detail_json |
| 热路径非阻塞 | 代码级核验：`enqueue` = 锁内 `deque.append` + `Event.set`（O(1) 内存操作，零 IO，不等 flush）；月库连接独立（sqlite 月库 mconn / pg 经 backend） |
| NFR-8 抽测口径 | **裁定 ACCEPT**：抽测对象是「审计增量」（同负载开关审计差值 1.4ms<50ms），enqueue 开销 µs 级与 embedder 无关，sqlite+FakeEmbedder 简化不影响增量结论有效性；完整链路 SLO 以 m2-5 基线（1361.6ms PASS）+本段增量组合支撑——足以支撑「SLO 不回归」结论 |

### B（G-24②⑧）✅
- 两漏记：MCP `curated 非空` 前提删除（get_entity 无条件收集 `restricted_ids`）+ REST/MCP 展开端点 `sem_restricted_ids`（双方言实现+协议入 `backend.py`）批量判定并入 entity_ids；test_g24b1/b1b/b2/b2b 断言落事件、**test_g24b2c 对照断言无 restricted 零事件不虚报** ✓
- ⑧：`EVENT_SEMANTIC_RESTRICTED_ACCESS` 迁 `domain/audit_events`（`__all__` 在册）、core/semantic/constants 残留仅注释；test_g24c 全 src 正则扫描无旧路径导入——**import 检查真实**（文本扫描非旁证）✓

### C（T-S7/T-S8）✅
- T-S7 describe_table：同名 table key 双组织列集不同（tax `{tax_amt,inv_no}` vs gl `{gl_amt}`）**200 面内容比对**（非旁证）+ 未登记 403 + 跨组织 org_scoped 403；l0 逐片段比对（gl 含专属/tax 专属 not in）+ dict_rev 独立 ✓
- T-S8：`random.Random(20261108)` 固定种子可复现；CTE 三路参数记号归一后前缀逐字相等断言；运行时三路（FTS/随机向量/实体）并集 ⊆ 可见块 + **d_os 块显式排除**（ACL 失守即红，非恒真）✓

### D（ui-be）✅（代码级核验，沿 ui-3 先例；playwright 未复跑——如实申报）
- 契约对齐与 m3-1 Committer 差异清单逐条对码：`createDataset` 发 `{key, title?}`（描述经 `createDatasetWithDesc`→PATCH）、`createDimension` 调用方 access.js:737 发 `{key, label, required}`、`setOrgStatus` 显式 `X-Org-Id=org` 按路径对齐、apiFetch 缺省注入改「调用方显式指定优先」✓
- 降级横幅撤除：`be1BannerHTML`→`docsLoadErrHTML`（403/5xx 如实+重试）、`docs.vis.pendingBe2` 占位→`explainCardHTML` 接真端点、be-①②/建库/建维度/停用 contract-first 降级全撤，`banner` 类零引用 ✓（两处文案残留 → P3-①）
- visible 徽标（isAdmin 面 ✓/✗/—）/explain 卡（前端不演算 ACL）/可见性矩阵（org_admin 逐格 explain 取数+点格下钻）/mem.known→`loadMembers` 真源化（名单源 = GET members ∪ export ∪ 会话注册表，非管理员退化）✓
- i18n 独立复跑（自写扫描器 v4：t() 直调+动态前缀拼接+data-i18n 属性+index.html 壳全纳入）：**zh=660、en=660、键集相等、零缺、零死 → I18N-OK**，复现 coder 申报 ✓

### E ✅
- P3-1：pg `list_members`/`list_orgs_for_user` 补 `to_char` 归一；断言 `isinstance(str)`+fullmatch 正则+None 分支（修复前 pg 为 datetime——真实非恒真）✓
- 边界①：`documents.py` membership deny 维度行 detail=「成员关系无效，维度行仅供参考」；test_d8 断言升级含「有效授权」**禁入**断言 ✓
- P3-3 未用导入清理 ✓（import 收窄实证）；P3-2 六处 outbox UniqueViolation/IntegrityError 收窄 RuntimeError（pg 3+sqlite 3 计数实证）✓；P3-5 409 文案按约束源分流+test_a2b（name/id 双分支文案断言）✓；P3-6 四项（description null 清空+键缺失对照/头不一致 400/sysadmin 无成员 403×4/无新任务行前后对照）✓；P3-7 `render_documents_page_select` 入双方言 `__all__` ✓；P3-8 POST extra=forbid+status 422+无副作用断言 ✓

## 三、择型 8 条裁定

| # | 择型 | 裁定 | 理由 |
|---|---|---|---|
| 1 | action=`search.*` 域词 | **ACCEPT** | design.md:485 `action` 注释字面首列即 `search`；ops 查询道按前缀路由零前端改动落地（i18n.js:452-454 实证） |
| 2 | 链防叉互斥改造（sqlite BEGIN IMMEDIATE 顺势加固 ship_outbox / pg 事务级咨询锁 20261108） | **ACCEPT** | 注入实证互斥有效（第五节）；ship_outbox 加固后 TC-OPS-01 崩溃注入用例在门禁 1842 全绿内——崩溃注入语义不回归 ✓；锁键与 MIGRATION_LOCK_KEY(0x1A771CE) 异值，与 `hashtext(org)` 撞键=无害串行化（单锁无死锁环，既有注释同口径） |
| 3 | pg 月库同库事务+咨询锁·「生产 app 侧 PG 未接线既有状态」申报 | **ACCEPT（申报属实）** | pg 形态仅门禁 pg 臂覆盖、无生产部署属实；但申报未点名「**flush 后台线程与请求线程共用 PgBackend 单连接**」这一具体机理 → 单列 P2 移交裁定 |
| 4 | queue 溢出丢最旧+防毒丸+enqueue 即 wake | **ACCEPT** | MAX_PENDING=10⁴ 有界+dropped 计数（观测面）；max_retries=3 丢弃计数 test_qa1c 实证；enqueue 即 wake 只使实际延迟 <5s（interval 是上界非下界）——FR-6 上界不违 |
| 5 | 404 reason 二值回查 | **ACCEPT** | REST（sem_entity_by_id）/MCP（_entity_is_restricted）回查 sensitivity；回查结果只进审计 detail，客户端恒 404 统一面——存在性零泄露保持 |
| 6 | REST·MCP 拒绝层差异如实 | **ACCEPT** | REST `except AclDeniedError/HTTPException` vs MCP `except ToolError`——语言差异真实存在，reason 语义粒度两边如实（org_disabled/403 code/semantic:read denied） |
| 7 | i18n 查询道文案同步 | **ACCEPT** | 查询道三键（queryLane/queryNote/queryEmpty）zh/en 已真源化；对账独立复跑零缺零死 |
| 8 | 矩阵 m×n 无规模护栏开放点 | **ACCEPT（口径成立）** | 前端矩阵确为 members×docs 全量逐格取数无上限（代码级确认）；开放点登记归 F 组监督侧落笔（本段 docs/ 零改动系纪律要求）——**供上报：F 组须在 known-gaps 落笔该开放点** |

## 四、注入验证（2 组，均已恢复）

**注入① 摘除脱敏**（admin.py:1044-1046 剥离过滤→`items = list(rows)`）：
```
uv run pytest tests/test_audit_query_g22.py::test_qa5_redaction_sysadmin_metadata_only
→ FAILED [sqlite]（1 failed, 1 skipped=无 DSN 时 pg 臂跳过）
→ 带 DSN 补跑 [pg] → FAILED
```
**双臂均红** ✓——脱敏断言真实有效。恢复后 `git diff 995d6fd -- src/knowledge_lattice/api/admin.py` = 0 行。

**注入② 摘除链互斥**（sqlite/backend.py:2144/2224 两处 `BEGIN IMMEDIATE` 摘除=还原 deferred 竞态窗）+ 并发交错脚本（shipper×querier 双线程 barrier 对齐、120 轮、ThreadLocalBackend 生产装配形态）：

| 形态 | 结果 |
|---|---|
| 原实现 + 并发脚本 | `walk_chain OK rows=360` → **CHAIN-INTACT** |
| 注入版 + 并发脚本 | `AuditChainError: audit chain fork at prev=…` → **CHAIN-BROKEN** |
| 注入版 + test_qa9（顺序交错） | **2 passed（双臂仍绿）** |
| 恢复后 + 并发脚本 / g22 全量 | CHAIN-INTACT / 24 passed；`git diff 995d6fd -- src/` = 0 行 ✓ |

互斥机制有效性获对照实证；**test_qa9 单独不能捕获互斥回归**（顺序执行无竞态窗）→ P3-②。

## 五、回归零弱化

- 4 个既有测试文件 test 函数：12→16 / 9→10 / 13→13 / 8→8——**0 删除**；`git diff --diff-filter=D tests/` 为空——**0 文件删除** ✓
- 断言增强处（d8 加文案+禁入断言、b2 加 422/400 断言、b4 加无新任务行对照）均为**只增不放宽** ✓
- 门禁 1842 全绿含既有 TC-OPS-01 崩溃注入等存量用例 ✓

## 六、分层/白名单

- **core 无方言 SQL** ✓：查询审计编排落 `query_audit.py`（顶层，api/mcp 调用），SQL 全收口 `store/<dialect>/backend.py append_query_events`/`sem_restricted_ids`；`audit_chain.py` 仅纯函数（常量+哈希）✓
- **web/** 属 D 组白名单合法（7 文件 +443/−123，无越界）✓
- **docs/ + prototype/ 零改动**：`git diff --stat 62613d8..995d6fd -- docs/ prototype/` 为空 ✓

## 七、分级发现

**P2-1（实·pg 形态连接共享风险）** `query_audit.py` flush 线程经 `QueryAuditQueue(backend)` → pg `append_query_events`（postgres/backend.py:3494 起）使用 **`self._conn` 单共享连接**；生产 uvicorn 形态下请求线程（`to_thread(run_search, service.backend,…)`）与 flush 后台线程并发操作同一 psycopg 连接——psycopg 连接无内建跨线程锁，flush 短事务与请求并发可致协议错乱（flush 失败有重试+丢弃计数兜底，但连接错乱可波及请求线程，违背「审计不破坏查询」精神）。sqlite 默认形态无此问题（月库独立 mconn）。择型 3 申报「生产 app 侧 PG 未接线」属实但未点名此机理。
复现命令：代码审阅（postgres/backend.py:51 `self._conn = conn` + app.py `QueryAuditQueue(backend)` + threading 后台 `_run`）。
修法：pg 形态 flush 走独立连接（工厂/连接池单连），或 `append_query_events` 连接级串行化。移交：本段不阻塞，随部署期 PG 接线必修。

**P3-1（文·文案残留）** `web/i18n.js:131` `docs.upload.noDs`（「……（待 m3-1 后端轮次）或经 API 创建」）与 `:323` `access.dims.new.foot`（「……（待 m3-1 后端轮次）」）均为**活引用**（docs.js:200 / access.js:416），而 POST datasets/dimensions 已实装且有表单——文案误导。降级横幅行为已撤除，此为空态/脚注文案未同步。修法：两键文案改为「由组织管理员在建库/建维度表单创建」。

**P3-2（测·互斥回归捕获面缺失）** test_qa9 为顺序交错，注入实证摘除互斥后仍双臂绿——门禁无法捕获互斥回归（后果=破链 fail-closed 审计不可读）。修法：test_qa9 增双线程并发交错形态（本轮注入脚本可收编：ThreadLocalBackend + barrier + 双线程 ship_outbox×append_query_events + walk_chain 断言）。

**临时产物清理**：已全部清理（gate log、i18n 三版扫描器、注入脚本、两份 src 备份、inject_work 并发 db、/tmp 新旧 test 函数清单）——`git status` 仅余编排层检查点两文件（进仓前已存在）；`git diff 995d6fd -- src/ tests/` = 空；未读 `.env`；lattice-pg 容器按项目门禁配置保留运行。

## 八、结论

- 门禁独立复跑 **1842+1 双后端双模式 0 skipped** 与申报一致，链式对账自洽；
- A~E 五组逐项勾验全过，T-S9⑥/脱敏/漏记/显式断言/契约对账均真断言；i18n 对账独立复跑复现零缺零死；
- 注入 2 组：脱敏摘除双臂红（断言有效）；链互斥摘除并发脚本红（互斥有效）+暴露 test_qa9 断言强度缺口（P3-2）；
- 回归零弱化、分层纪律合规、docs/prototype 零改动；
- 发现 P2×1（pg 连接共享——移交部署期裁定）+ P3×2（文案残留/互斥测试形态），均不阻塞本段交付。

**testVerdict: PASS**
**testedSha: 995d6fd668215e457f0b654f0f63da26a7e3605a**

</details>

<details>
<summary>R1 Committer 报告（2026-11-08 13:17，reviewVerdict=APPROVED）</summary>

# task-knowledge-lattice-m3-2 R1 Committer 审查报告

## 审查对象与基线核对

- **审查对象**：`995d6fd668215e457f0b654f0f63da26a7e3605a`（= `develop_opencode` HEAD）。父提交 `62613d8` = `origin/develop`（m3-1 合并点）。`origin/develop_opencode` = `a287604`，本地领先 2（62613d8 + 995d6fd），未 push——与检查点记载一致。
- **R1 首审**：上一轮无 `reviewedSha`（检查点 `reviewedSha: null`），不存在"上轮意见处置"核对项；本轮对 `62613d8..995d6fd` **全部 29 个文件 diff 逐文件核对**（含周边上下文代码），未因任何区域"已看过"跳过。
- **diff 核对**：29 files +2338/−202，与检查点 `filesChanged` 逐条一致；`docs/` + `prototype/` **零 diff** ✓；工作区仅编排层两文件（m3-1 检查点 modified、m3-2 检查点 untracked），不在代码 diff 内。
- **门禁**：采信 Tester 独立复跑（GATE PASS **1842 passed / 1 deselected / 0 skipped**，双后端双模式，pg 臂 696）；**我未独立复跑**（审查环境只读，沿 m2-5/m3-1 先例声明采信）。**静态对账闭合**：新增测试函数 26 个（g22 12 + g24b 6 + ts7ts8 3 + admin 4 + store_reads 1）→ 25 个双臂 + 1 个无 fixture 单臂 = 51；1791+51=1842；pg 637+25=662+34=696 ✓。
  - **证据归因更正**：单臂函数是 **`test_g24c_constants_single_registry`**（无 fixture），**不是 Tester 报告所称的 ts8**——`matrix_env` 基于 `backend` fixture 参数化，ts8 走双臂；总数结论不变，但链式对账的归因需修正（见 §六）。
- **测试门禁审查**：diff 内无新增 `skip/skipif/xfail`；0 测试文件删除；0 测试函数删除；4 个既有测试文件增强均为**只增不放宽**（12→16 / 9→10 / 13→13 / 8→8）；deselected 1 = `manual`（TC-UI 既定口径，非 skip）✓。
- **分层/白名单**：core 无方言 SQL（`query_audit.py` 为顶层编排，SQL 全部收口 `store/<dialect>`）；`web/` 7 文件属 D 组白名单；docs/prototype 零改动 ✓。
- **逐组核对摘要**：A（六入口 enqueue 全接、队列锁/Event/drain/关停语义、sqlite BEGIN IMMEDIATE × pg 咨询锁两道写互斥、ship_outbox 顺势加固等价性、链哈希口径、refused 三因+404 二值、sysadmin 脱敏、detail_json JSON 转义安全）✓；B（G-24②①② REST/MCP 补记、无 restricted 零虚报、⑧常量迁移+真实文本扫描）✓；C（T-S7 200 面内容比对、T-S8 固定种子真随机向量+CTE 归一化+运行时并集 ⊆ 可见块+d_os 显式排除）✓；D（契约对齐、X-Org-Id 显式优先、降级零引用、visible/explain/矩阵、"前端不演算 ACL"、mem 三源合并）✓；E（P3-1/P3-2/P3-3/P3-5/P3-6/P3-7/P3-8 六处收窄计数实证、边界①文案+禁入断言）✓。

---

## 一、问题清单

### P1

无。

### P2

**P2-1（Tester 提出，本席复核成立）pg 形态 flush 线程与请求线程共享 `PgBackend.self._conn` 单连接**
- 位置：`src/knowledge_lattice/query_audit.py:140`（`self._backend.append_query_events`）→ `src/knowledge_lattice/store/postgres/backend.py:3610-3611`（`conn = self._conn; conn.execute("BEGIN")`）；构造点 `src/knowledge_lattice/app.py:332`（`QueryAuditQueue(backend)`）。
- 问题：psycopg 连接无跨线程内建锁；后台 flush 线程与请求线程（`asyncio.to_thread(run_search, service.backend, …)`）可并发操作同一连接，协议错乱可能波及请求线程——违背"审计不破坏查询"原则。sqlite 默认形态不受影响（`ThreadLocalBackend` 每线程一连接 + 月库独立连接）。
- **风险面核实**：当前 **app 生产装配恒 sqlite**（`store/factory.py:19-33`，检测 `LATTICE_PG_DSN` 仅告警），PG 仅门禁/测试臂；故**本段无生产暴露**。但 pg 臂测试自身也走该共享形态（`test_qa1` 轮询与 flusher 并发读写同一连接），属测试稳定性隐患。
- **裁定：部署期 PG 接线必修（本段不阻塞交付）**。修法建议：`QueryAuditQueue` 改收 `backend_factory`（或 pg 形态注入独立连接/连接池单连），或 `PgBackend` 对 `_conn` 做连接级串行化（代价是请求面串行）；修复时一并覆盖 pg 臂测试的双连接形态。登记 known-gaps open point（见 §四）。

### P3

**P3-1（Tester P3-1 复核成立，并扩展至 4 键 + 注释残留）用户可见文案仍宣称"待 m3-1 后端轮次 / 无 GET members"**
- `src/knowledge_lattice/web/i18n.js` zh：`:131`（`docs.upload.noDs`）、`:323`（`access.dims.new.foot`）、`:387`（`access.mem.empty`）、`:388`（`access.mem.footNote`）；en：`:805`、`:997`、`:1061`、`:1062`。**活引用**：`views/docs.js:200`、`views/access.js:212/214/416`。
- 其中 `access.mem.empty/footNote` 仍写"服务端无 GET members（m3-1 #13）"——与本段"GET members 真源化"直接矛盾，误导性强于 Tester 报告点名的两键。
- 修法：改为「名单源 = GET members ∪ 授权导出用户名 ∪ 本会话增改成员」「由组织管理员在建库/建维度表单创建」；同步英中日四键。附带注释清扫：`views/access.js:7`、`web/api.js:9-10/338`、`web/style.css:568-573`（`.banner` CSS 已无引用）。**建议 m3-3 首轮顺手批**（不阻塞）。

**P3-2（Tester P3-2 复核成立）`test_qa9` 顺序形态无法捕获链互斥回归**
- 位置：`tests/test_audit_query_g22.py:452-484`。Tester 注入实证：摘除 `BEGIN IMMEDIATE` 后并发脚本 CHAIN-BROKEN 而 `test_qa9` 双臂仍绿——门禁对本段核心不变量（两写道链防叉）无回归捕获面。
- 修法：收编 Tester 注入脚本为正式用例（`ThreadLocalBackend` + `barrier` + ship_outbox×append_query_events 双线程 N 轮 + `walk_chain`/`read_monthly_events` 断言）；PG 形态随 P2-1 修复以双连接补。**裁定：移交 m3-3 首轮必做项**（此轮将再动审计相关面，届时补最经济），并在 TEST-CASES m3-2 组备注该缺口。保留现有顺序用例。

**P3-3 `test_qa1b` 无法隔离"stop() 关停 flush"**
- 位置：`tests/test_audit_query_g22.py:200-210`。`qa.start()` 后 `enqueue` 即 `_wake.set()`，后台线程会先于/并行于 `stop()` 完成 flush；断言只能证明"事件可见"，不能证明"残留队列由 stop 刷出"。
- 修法：不 `start()`（`enqueue` → `stop()` 直接验证 stop 的最终 flush），或断言前置 `pending==1` 并暂停后台消费。并入 P3-2 测试补强批。

**P3-4 refused 分支断言缺口（覆盖率申报夸大）**
- `test_qa4` 仅覆盖 REST search 停用组织；`test_b3b`（`test_org_disable_m31.py:167-200`）执行了 MCP search 停用组织的 `_auth_and_org` 入队路径但**未断言审计行**；REST annotate/get_entity 停用组织、MCP annotate/get_entity `_sem_member` 拒绝面（`mcp/server.py:241-250/527-548/585-601`、`api/semantic.py:303-318/498-518`）均无断言。
- 修法：在 `test_b3b`/`qa4` 扩展 flush 后断言 `read_org_audit(..., action="search.")` 的 refused 行；再加 1~2 条 annotate/get_entity 停用面断言。并入测试补强批（P3）。

**P3-5 flush 写路径规模化成本（两方言）**
- `sqlite/backend.py:2225-2228` 与 `postgres/backend.py:3622-3628` 每轮 flush 都 `SELECT id FROM audit_events`（整月全部 id）构集合；pg `last_row_hash`（`store/postgres/audit.py:207-220`）按 `seq DESC` 无索引；再叠加"enqueue 即 wake"（`query_audit.py:112`）→ 事件在低流量下近乎逐条触发 flush。成本 O(当月行数)/次、月度累计 O(N²)；sqlite 为默认生产后端，100% 采样高流量下会放大 GIL/IO 占用（不直接阻塞检索，但与"不得显著拖慢查询响应"精神有张力）。
- 修法：`existed` 改为仅查本批 id（`WHERE id IN (batch)` / `id = ANY(%(ids)s)`，batch≤200 无需分片）；pg 补 `(created_at, seq)` 或 `seq` 索引（或缓存尾哈希）；pg `ensure_month_partition`（`postgres/backend.py:3618-3620`）每轮 DDL 需进程内 ensure 缓存（sqlite 已有 `_ensured` 先例）。**登记 open point，生产化/PG 接线前修**。

**P3-6 溢出/丢弃观测面仅日志**
- `query_audit.py:99/107-110/147-155`：`dropped`/`pending` 只存在于内存与日志，`GET /stats` 未暴露；FR-6 抖动窗口之外的丢失（溢出/毒丸）在管理面不可见。
- 修法：`/api/orgs/{org}/stats` 增 `query_audit: {pending, dropped}`（或 RUNBOOK 记日志 grep 口径）。并入 P3-5 批量或 m3-3。

**P3-7 refused 写放大边界需登记（G-26 延伸）**
- 评估结论：**未认证调用不触发查询审计**（REST `get_auth`/MCP `_auth_and_org` 均在入队前 401）✓；认证后无权用户每次尝试落一条 refused（含任意路径 org 字符串、任意 query 文本），上界 = 队列 10⁴（丢最旧）+ 月库累积。属可接受的审计面，但建议在 known-gaps G-26 栏补"查询级 refused"子项与有界口径（与现有"部署侧准入兜底"同栏）。

**P3-8 卫生/加固/证据准确性小项**
- 新测试未用导入：`tests/test_audit_query_g22.py:24`（`uuid`）、`:65`（`RelationRecord`）；`tests/test_sem_audit_g24b.py:40`（`RelationRecord`）；`tests/test_qa_ts7_ts8_m32.py:22-33` 七个 helper 未用（`dim_id_for/seed_dataset/seed_dimension/seed_dim_value/seed_grant/seed_searchable_doc/val_id_for`）。建议清扫（无 lint 工具，非阻塞）。
- `web/api.js:142-150` `createDatasetWithDesc` 注释称"描述失败仅 toast"，实现静默吞错——补 toast 或删注释。
- `web/views/access.js:300` 注释"格点落位即渲染"，实现仅在全部取数后 `render()` 一次——改注释或按格渲染。
- 哈希链 canonical 前置条件：`store/audit_chain.py:33-54` 以 `\x1f` 分隔字段并假定字段不含该字符；查询道 `org_id`/`target_id` 可控字符串（路径 org / MCP `key`）未做净化。实际风险低（读路径按存储字段确定性重算，且需 DB 写权限才可利用），建议 `build_query_event` 对 `org_id/target_id` 做控制字符净化或归档 known-gaps 理论硬化项。
- 审计数据源查询未包裹：`api/semantic.py:540-553`（`sem_entity_by_id`/`sem_restricted_ids`）与 `mcp/server.py:620-630` 在"查询已成功"后若 DB 抖动会 500——建议 audit-only 取数包 `try/except`（记日志降级），与"审计不阻断主路径"口径一致。
- **证据准确性**：i18n 死键申报"删 12"实为 **11 个整键删除 + 6 个同键改文案**（净 +14/语言，646→660 自洽）；单臂测试归因见上（g24c 非 ts8）。建议更正检查点/报告措辞。

---

## 二、需求边界问题

**无新增需求边界问题**（供上报：无）。

说明：
- m3-1 两条边界已裁定并落地——边界①用户选 A：`api/documents.py:266-275` 实现"成员关系无效，维度行仅供参考"且 `test_d8` 含"有效授权"禁入断言；边界②维护链豁免已随 design v0.9.10 注记。
- 本段"PG 未按裁定①字面使用独立连接"属**已申报的择型 3 + 部署期项**（Tester 已裁定"申报属实"），不是验收标准与实现矛盾，走 known-gaps 登记，不回 spec。
- 矩阵 m×n 无规模护栏、search_entities/describe_table/l0 不入查询审计，均为既定口径下的**开放点**，走 known-gaps 登记（见 §四），非需求歧义。

---

## 三、Tester 意见裁定

| 项 | 裁定 | 依据/处置 |
|---|---|---|
| **P2-1** pg 单连接共享 | **成立；部署期 PG 接线必修，本段不阻塞** | 生产 app 恒 sqlite（factory 证据）；PG 仅测试臂。修法：独立连接/连接级串行化；同时消除 pg 臂测试共享连接隐患。登记 open point，PG 切换前为前置条件（不做"登记即销账"）。 |
| **P3-1** 文案残留 | **成立，并扩展为 4 键 + 注释残留**（见 P3-1） | 非阻塞；移交 m3-3 首轮顺手批；不需回 spec。 |
| **P3-2** test_qa9 捕获面缺口 | **成立；移交 m3-3 首轮必做** | 实现已由注入验证；门禁缺回归捕获面。收编并发脚本为正式用例（优先 sqlite；pg 随 P2-1 双连接形态）。另附本席新增 P3-3（qa1b）同批。 |
| 择型 1（`search.*` 域词） | ACCEPT | 与 design §4 action 字面一致，ops 查询道前缀自动路由实证。 |
| 择型 2（链互斥改造 + ship_outbox 加固） | ACCEPT | 我逐行核对：sqlite 加固后"事务内取 rowid 尾哈希"与旧 `last_row_hash(db_dir, month)` 语义等价（旧实现即 rowid DESC 尾条；新实现把读链基纳入 BEGIN IMMEDIATE，且 `existed` 幂等跳过语义不变）——TC-OPS-01 崩溃注入在门禁全绿内，v1.8.3 两步幂等口径未破坏 ✓；pg 咨询锁键与 MIGRATION_LOCK_KEY 异值，`hashtext(org)` 撞键为无害串行化。 |
| 择型 3（pg 同库分区 + 咨询锁） | ACCEPT（附 P2-1 具体机理与修法） | 见 P2-1。 |
| 择型 4（溢出丢最旧/防毒丸/wake） | ACCEPT（附 P3-5 规模化注记） | 上界不违 FR-6；但 wake + 全月扫描的组合成本需在生产化前优化。 |
| 择型 5（404 reason 二值回查） | ACCEPT | 回查结果只进审计 detail，客户端恒 404 统一面；`EntityNotFound` 消息本身不含 restricted 字样（已核 `core/semantic/expand.py:84`）。 |
| 择型 6（REST/MCP 拒绝层差异） | ACCEPT | 差异如实；注意 REST annotate（membership 先行）与 MCP（org_disabled 先行）reason 优先级不同，仅审计 detail 差异，无功能影响。 |
| 择型 7（i18n 查询道文案） | ACCEPT | 查询道三键已真源化，Tester 独立复跑 660=660 复现。 |
| 择型 8（矩阵无规模护栏） | ACCEPT（口径成立） | F 组 known-gaps 落笔；另建议 TC-UI-05 豁免清单同步销项（矩阵占位/查询道空态两行）。 |

---

## 四、docs 批建议清单（supervised-coding 落笔，非 coder）

1. **design.md（v0.9.11，非决策变更声明）**
   - §6.3⑥ 查询级审计实现注记 + **A-16 收口**：六入口（REST/MCP search·annotate·get_entity）、进程内异步队列（5s/满批 200、月库直写、不走 outbox、崩溃尾部窗口 ≤5s 可接受——裁定①）、两写道链互斥（sqlite `BEGIN IMMEDIATE` / pg 事务级咨询锁）、refused 口径（403 三因 + get_entity 404 restricted/not_found；存在性零泄露）、sysadmin detail_json 剥离、action=`search.*`、ops 查询道落地即数据；`search_entities/describe_table/l0` 不入（指向 known-gaps 开放点）。
   - §4/§5.6：detail_json 内容（查询词 + chunk/entity id 列表）与月库保留期口径注记；可观测性（overflow/毒杀丢弃仅日志）。
2. **known-gaps.md**
   - **G-22 划销**（查询级异步审计已实现，T-S9⑥/A-16 收口）；**G-24②⑧ 划销**（②两漏记已补；⑧常量单一登记处）。
   - 新增开放点：①查询审计覆盖面（search_entities/describe_table/l0 不入，design 字面）；②可见性矩阵 m×n 全量逐格取数无规模护栏（前端 4 并发，O(m·n) 请求量）；③**PG 接线三件**（flush 不得共享请求连接〔P2-1〕/ensure 分区 DDL 缓存/last_row_hash·existed 索引或按批 id 查询）；④flush 全月扫描规模化（含 enqueue 即 wake 形态）；⑤链互斥并发测试缺口（P3-2）；⑥查询级 refused 写放大边界（G-26 延伸）；⑦溢出/丢弃观测面；⑧哈希链 canonical `\x1f` 前置与用户可控字段（可选理论硬化）。
3. **TEST-CASES.md**：T-S9⑥ 摘「挂起」+ A-16 收口；T-S7/T-S8 显式断言三补完成态；ui-be 对账完成态（visible 徽标/explain 卡/矩阵/mem 真源化/契约对齐/降级撤除）；新增 m3-2 用例组登记（建议 TC-OPS-11：12+6+3+5 函数 → 51 收集、含注入验证 2 组说明）；TC-OPS-03 延展注记（查询级事件 sysadmin 脱敏）；TC-UI-05 豁免清单销「矩阵占位待 be-①②」「查询审计道空态待 m3-2」两项；TC-UI 手动走查仍用户侧。
4. **AGENTS.md §1 / _m3-plan**：M3 进度 m3-2 交付（门禁 1842+1、#20 收尾、P3 移交去向）；row2 done、row3 m3-3 范围补「P3-1 文案 + P3-2 并发测试 + P3-3/P3-4 测试补强」。
5. **RUNBOOK（可选）**：查询审计观测（`query audit queue overflow` / `flush failed` / `drop` 日志 grep、月库事件量、关停 flush 语义）；PG 接线段 checklist 挂 P2-1 三件。
6. **issue #20 收尾材料**：代码（be-①② 契约未偏移 + UI 对账函数清单）+ 测试/门禁证据（1842+1、m3-1 D-①② 用例、i18n 660=660）+ 检查点链接；**材料充分，建议监督侧评论后关闭**。评论中如实注明：D 组浏览器级验证为 coder 自查申报（无截图/脚本入库），Tester 仅代码级核验，不替代用户侧 TC-UI 手动走查。

---

## 五、遗留事项去向建议

| 事项 | 去向 | 说明 |
|---|---|---|
| P2-1 pg 连接共享（+ensure DDL 缓存/last_row_hash 索引） | **部署期 PG 接线必修**（open point） | 阻断 PG 切换，不阻塞 sqlite 交付 |
| P3-1 文案残留（4 键）+ 注释/CSS 清扫 | m3-3 首轮顺手批 | 纯文本，零风险 |
| P3-2 链互斥并发测试（+P3-3 qa1b +P3-4 refused 分支断言 +P3-8 未用导入） | m3-3 首轮必做/顺手 | 测试补强为 m3-3 必做项 |
| P3-5 flush 规模化 / P3-6 观测面 / P3-7 G-26 延伸 | known-gaps 登记；生产化/PG 接线前修 | 可与 P2-1 同批 |
| P3-8 哈希链 `\x1f` 硬化 / audit 取数包裹 | known-gaps 登记（可选硬化） | 理论风险，不设排期 |
| G-22 / G-24②⑧ 划销；T-S9⑥ 摘挂起等 | docs 批（supervised） | 本段 docs 零改动，符合纪律 |
| warnings 171/172 治理 + #16 conftest teardown | m3-4 | 既定去向 |
| TC-UI 手动走查（含新矩阵/explain/查询道） | 用户侧 | M1+M2 达成宣告待勾项顺延 |
| #20 issue 关闭 | 监督侧（材料充分） | 建议 PR 留痕后评论关闭 |
| m3-1 边界①/② | 已裁定落地，无遗留 | ①实现+断言；②design v0.9.10 注记 |

---

## 六、evidence manifest 要点建议

- `taskId=task-knowledge-lattice-m3-2`、`round=1`、`maxRounds=3`；`coderTaskId=ses_e46e0ea25ffeqWt3t1x5GAB4rz`、`testerTaskId=ses_e4681cc91ffe9UOA6doKqvN9ly`。
- **双 SHA**：`testedSha=995d6fd668215e457f0b654f0f63da26a7e3605a`；`reviewedSha=995d6fd…`（本报告）；`HEAD=995d6fd…` 三一致；父提交 `62613d8`=origin/develop；分支 `develop_opencode`；未 push。
- `filesChanged` 29（+2338/−202）；`docs/prototype` 零 diff；工作区仅编排层检查点文件。
- **门禁**：`adoptedFrom=tester`（独立复跑，非 committer 自跑）；GATE PASS 1842 passed / 1 deselected（manual）/ **0 skipped** / 双后端双模式；pg 臂 696=662+34；链式对账 1791+51=1842，**26 新函数 = 25 双臂 + 1 单臂（`test_g24c`，非 ts8——更正 Tester 归因）**；warnings 171/172 如实登记（治理挂 m3-4）。
- **注入**：2/2 有效（①摘除脱敏 → `test_qa5` 双臂红；②摘除链互斥 → 并发脚本 CHAIN-BROKEN、单跑 `test_qa9` 仍绿——后者如实记为测试缺口 P3-2）；注入后 `git diff 995d6fd -- src/` 归零。
- **回归零弱化**：0 文件删除 / 0 测试函数删除 / 断言只增；deselected 1=manual。
- **择型与裁定**：5 条开工裁定逐条落地（PG 独立连接一项申报偏差→P2-1）；择型 8 条处置见 §三；P2-1/P3-1/P3-2 裁定见 §三。
- **boundaryQuestions: []**（m3-1 两条已裁定落地）。
- **handover**：PG 接线三件（部署期必修）；P3-1/P3-2/P3-3/P3-4/P3-8→m3-3；warnings→m3-4；TC-UI→用户侧；#20→监督侧关闭。
- **evidence caveat**：D 组浏览器级验证为 coder 自查申报（无截图/脚本制品），Tester 未复跑（如实申报）；i18n 660=660 为 Tester 独立复跑复现；i18n 死键精确为 11 键删除（+6 键改文案）而非"12 死键"——manifest/PR 描述按实际写。
- **交付序列核对点**：后续 docs 批 + coder chore 归档提交后，最终 PR HEAD 会变化（doc-only）；manifest 需同时记录 `codeSha=995d6fd` 与 `deliveryHead=<chore sha>`，并附 `git diff 995d6fd..<deliveryHead> -- src tests` 为空证据，方可放行。

---

## 七、结论

**reviewVerdict: APPROVED**

- P1 无；P2×1（P2-1 pg 单连接共享）**裁定为部署期 PG 接线必修、本段不阻塞**（生产 app 恒 sqlite，无当前暴露面；修法与登记已给）；P3 均为非阻塞建议（文案/测试补强/规模化/观测/卫生），去向已明确。
- A~E 五组逐项对照验收标准成立：六入口查询审计 + T-S9⑥/A-16 + ≤5s 窗口 + sysadmin 脱敏断言真实有效（注入双臂验证）；链防叉互斥实现正确且 ship_outbox 加固行为等价（v1.8.3 两步幂等未破坏）；refused 不入未认证面（G-26 评估通过）；G-24②⑧ 收口；T-S7/T-S8 显式断言；ui-be 对账/矩阵/explain/mem 真源化/i18n 660 完成；E 组 P3 全清 + 边界①文案落地；分层/白名单/冻结纪律合规；门禁 1842+1 双后端双模式 0 skipped（采信 Tester 独立复跑 + 静态对账）。
- **检查点建议更新**：`reviewedSha=995d6fd668215e457f0b654f0f63da26a7e3605a`、`reviewVerdict=APPROVED`、`status=approved`、`round=1`（testedSha 已一致）。
- **交付把关（待用户确认后执行）**：docs 批（supervised 执笔）→ coder chore 归档批（docs+检查点）→ push + PR base=develop → 我在 PR 上 `gh pr review` 留痕（本报告的阻断项/裁定/证据要点）→ 复核最终 HEAD 的 evidence manifest 双 SHA 与 `deliveryHead` → 放行用户合入。**合入动作不经手**。
- 本轮**未收到 CASE_BUG 裁定请求**，无附裁定。

**reviewVerdict: APPROVED**（reviewedSha = `995d6fd668215e457f0b654f0f63da26a7e3605a`）

</details>
