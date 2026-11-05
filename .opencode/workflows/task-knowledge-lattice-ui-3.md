# task-knowledge-lattice-ui-3 · i18n 终审 + 真实数据形态 + TC-UI 对照走查组重写（issue #20 收官段）

> 段位：M3-UI 第 4 段（收官）。ui-1/2 已交付六视图原型级实装；本段收口 issue E 项非功能要求 + TC-UI 走查组随新 UI 重写（原走查状态作废——issue 评论 2 连带注记口径）。
> 基线：门禁 1715+1 双后端双模式 0 skipped（13bffba 后工作区）。

## 硬约束

1. **文件白名单**：
   - `src/knowledge_lattice/web/**`
   - `docs/TEST-CASES.md`（**活文档**——仅 TC-UI 组重写 + TC-E2E-07 条目更新 + 版本行；版本行声明「非决策变更、冻结结论不动、用例数不变」）
   - `benchmarks/report-ui3-tc-ui-walkthrough.md`（**新增**——新 UI 手动走查清单，沿 report-m1-5-tc-ui-walkthrough.md 先例形态）
   - `tests/test_e2e_07_shell.py`（仅当机制断言需微调；第三用例一字不动）
   - 禁区：prototype/（只读）、docs/ 其余正文（requirements/design 冻结）、src/** 其余、tests/** 其余。零 commit / push / add。
2. 沿 ui-1/2 代码约定与设计系统（不新增设计语言；真实形态的样式复用既有类 + 必要小补充集中 style.css「ui-3 additions」节）。
3. i18n 全文案走 t()；分页/截断/时间等新形态文案同样入字典（zh/en 同步）。

## 工作项

### A. i18n 终审（FR-8 / TC-E2E-07 机制断言保活）

1. 键对账脚本全量跑：t() 引用 + data-i18n* vs zh/en 双字典——零缺键（ui-2 已 612=612，本段新增键后复跑）。
2. **硬编码文案扫描**：模板字符串/属性中的裸中文（排除：代码注释、业务数据字段渲染〔标题/实体名等来自 API 的值〕、API 路径与工具名/状态枚举〔TC-UI-02 排除项口径〕）——发现即修（入字典）。
3. EN 态全视图走查一遍：无混语言（含 toast/placeholder/title/空态/教学文案）。

### B. 真实数据形态系统化（issue E 项「原型未画，实装段定」的约定落档）

对六类形态做**全视图盘点 → 补漏 → 约定**（盘点表进交付报告；约定文案入走查清单）：

1. **空态**：docs（无库/空库/be-① 降级）、search（无结果/403）、access（无授权行/无维度/矩阵占位）、ops（无任务/无审计/maintenance null）、semantic（未接入/无权限/无结果/404 零泄露）、orgs（无组织）——已有大部分，统一「空态 = 说明 + 下一步动作」模式，补漏。
2. **加载态**：各视图 onEnter 异步首装必有 loading 指示（loadingHTML 复用）；二次刷新不闪空（缓存先行渲染再更新）——盘点补漏。
3. **错误态**：401（api.js 统一 → toast + 打开连接设置）/403（toast detail + 视图内降级面）/404（视图内空态）/网络异常——盘点各视图错误路径呈现一致。
4. **条数与分页**：审计 limit=50 → 表头/脚注标注「最近 50 条」+「加载更多」（limit 递增 50→100→200，api.js audit 已有 limit 参数）；sync-runs limit=50 同款；任务列表全量（无分页参数——注记）；docs be-① 未定不处理。
5. **长文截断**：实体名/brief/title/别名等列表位文本 CSS 截断（沿原型 text-overflow/字数截断惯例——.t-title/.crumbs 已有部分）；详情位全文。盘点补漏（如审计 detail_json 160 字符截断已有——title 加「展开全文」或保留截断约定）。
6. **UTC 时间显示**：统一约定——显示 `MM-DD HH:mm`（short()）+ hover title 完整 UTC 原文；时间列/pane 时间行标注 UTC（一处全局约定文案，如表头「更新(UTC)」或脚注）。盘点所有时间显示位统一。

### C. 功能小件（既有端点 + 既有 UI 模式，薄加法）

1. **质检抽查入口**（org_admin）：docs 视图工具栏「质检抽查」按钮 → 面板（sample flags 表：flag_id/doc_id/reason〔中文化〕/mean_sim/avg_idf）+ 行内补标（keywords/tags 输入 + 解决/忽略）→ `GET /api/quality-flags/sample` + `PATCH /api/quality-flags/{flag_id}`（api.js 已有 sampleQualityFlags/patchQualityFlag，挂载即可）。
2. **覆盖上传入口**：doc 详情 pane「上传新版本」按钮（owner/org_admin）→ 打开上传抽屉且锁定该 doc（提交时 FormData 带 doc_id——uploadMultipart 已支持 docId 参数）→ 202 → 轮询；pending 期间 409 如实；版本原子切换口径注记（到 searchable_full 才切换在用）。

### D. docs/TEST-CASES.md 回写（活文档、非决策变更）

1. **TC-UI 组重写**（§二 TC-UI 节）：
   - **TC-UI-01 语言切换与持久化**：机制步骤平移（顶栏「中 | EN」新位置），断言不变 + 全视图重渲染即时生效。
   - **TC-UI-02 双语完整性**：按新六视图 + 顶栏/连接弹层/toast/空态/占位重写步骤；排除项口径保留（状态枚举/API 路径/工具名/文档锚点/业务数据）。
   - **TC-UI-03 业务数据与行为不随语言变化**：新交互路径（检索 hit 卡对照 / 授权格点格 PUT 两语言各一次对照 export 一致）。
   - **TC-UI-04 服务端不感知语言**：新路径（检索 + 授权格 PUT 抓包对照）。
   - **新增 TC-UI-05 原型 1:1 对照走查**【手动｜ui-3】：逐视图（文档/检索/权限〔授权格/维度/成员/矩阵占位〕/运维/语义/组织/顶栏与侧栏）与 prototype v0.6 并排对照——同一设计系统类名、布局结构、交互口径；诚实差异清单（facet 无计数/成员 role 缺位/aliases 无徽标/矩阵占位等——以 ui-2 检查点落档清单为基线）为已知豁免项。
   - **B① 逐行过期编辑新路径注记**：原 4/4 走查基于旧薄壳形态作废；新路径 = 权限·授权格 → 成员「详细」抽屉内逐行 expires（预填/行内/保存全量替换）。步骤并入 TC-UI-03 或单列 TC-UI-06，二选一（实现时按清单篇幅定）。
   - 节首口径注记：**本组随 ui-3 重写为新 UI 原型对照走查口径；旧走查状态（含 m2-5 B① 4/4）作废**——M1+M2 里程碑达成宣告的唯一待勾项按新形态重新执行。
2. **TC-E2E-07 条目更新**：预期句改新壳口径（应用框架 + 六视图 + api.js 契约收口 + 前两用例 ui-1/2 随壳重写注记；第三用例 API 侧不变）。
3. **版本行**：v1.9.14（2026-11-04 随 ui-3 交付——非决策变更、冻结结论不动、CI 用例数不变：TC-UI 手动组重写不进门禁）。§六对照表如有 TC-UI 引用行同步注记。

### E. 走查清单（benchmarks/report-ui3-tc-ui-walkthrough.md 新增）

沿 report-m1-5-tc-ui-walkthrough.md 先例形态：TC-UI-01~05（+B① 新路径）逐用例步骤/预期/勾验栏；附录：六类真实数据形态约定（B 项盘点结论）+ 诚实差异豁免清单 + 走查环境指引（/tmp 造数 + uvicorn + token 双模式）。

### F. 门禁

- `uv run pytest -q` 全绿 0 skipped，用例数不增（TC-E2E-07 若仅机制断言微调则数量不变）。

## 端到端验证（子代理必做）

- 沿 /tmp/ui2_seed.py 环境（或增补：几份无 quality flag 的空态样例不必强求——空态用无 flag 文档验）；浏览器走查：B 项六类形态逐类触发（含「加载更多」翻页、长文截断 hover、UTC title、EN 态全视图）；C 两小件闭环（抽查补标 PATCH 生效 / 覆盖上传新版本号 + 原子切换注记 + pending 409 路径）；console 零 JS 错误。
- i18n 扫描脚本输出零缺键零硬编码（排除口径内）。

## 验收标准（自检后才算完成）

1. git 白名单外零触及、零 commit。
2. i18n：键对账零缺键 + 硬编码扫描零命中（排除口径内）+ EN 全视图无混语言。
3. 六类形态盘点表 + 补漏实现逐项过；两小件闭环实测。
4. TEST-CASES 回写：TC-UI 组新形态（01 平移/02-04 新路径/05 对照走查/B① 新路径注记/作废声明）、TC-E2E-07 更新、版本行非决策变更声明——**diff 不触碰正文冻结区**（仅活文档相关节）。
5. 走查清单文件就位（结构同先例）。
6. `uv run pytest -q` 全绿 0 skipped 用例数不增。

## 交付报告格式

文件清单与行数 / 六类形态盘点表（现状→补漏→约定）/ i18n 扫描结果 / TEST-CASES diff 摘要 / 自检 6 项勾验 / 遗留清单。

---

## 交付记录（2026-11-04，主会话验收后回填）

- **开发**：subagent（general-purpose）；**验收**：主会话独立复核。
- **交付物**：web/ 十文件收口（i18n 640=640 键 +28/修 1 重复键、tsHTML UTC 悬停、审计/同步历史「最近 N 条」+加载更多 50→100→200 阶梯、六类形态补漏〔空态下一步/二次刷新不闪空/假空表修正/CSS 截断〕、**质检抽查面板**〔sample+行内补标+换 seed 重抽〕、**覆盖上传**〔锁定横幅+doc_id+pending 409 专属 toast〕）+ docs/TEST-CASES.md 4 hunk（版本行 v1.9.14 非决策声明 / TC-E2E-07 新壳口径 / **TC-UI 组重写**〔01 平移·02-04 新路径·05 新增原型对照走查·B① 并入 03·旧状态作废声明含 m2-5 B① 4/4〕/ §六 M1 行注记）+ benchmarks/report-ui3-tc-ui-walkthrough.md（129 行，沿 m1-5 先例 + 六类形态约定附录 + 豁免清单）。
- **主会话独立验收**：
  - ✅ git 白名单（web/** + TEST-CASES 指定节 + benchmarks 新清单；api.js/test_e2e_07 零改动）；TEST-CASES diff **恰 4 hunk 全在活文档区**、版本行非决策声明在位。
  - ✅ **门禁独立复跑 GATE PASS**：1715+1 deselected、0 skipped、双后端双模式——用例数不增。
  - ✅ 浏览器实测（重建 /tmp/ui2-data 环境）：质检抽查面板（本种子无 flag → 空态如实；机制与 ui-3 子代理 DB 级复验一致）；**覆盖上传全链**（上传 v1 → 「↥ 上传新版本」→ 锁定横幅+库锁 → 传 v2 → pending v2 / 在用 v1 不动——原子切换语义可视）；审计「加载更多」脚注与 50 起点；UTC 悬停 title（`…UTC` 全文）；任务全量注记；console 零 JS 错误。
  - ✅ i18n 独立复跑：zh=en=640 零缺键。
- **遗留**：走查清单待用户人工执行回填（TC-UI-01~05——**M1+M2 里程碑达成宣告唯一待勾项按新形态执行**）；组织到期 (UTC) 悬停视觉位需带 expires 视角复验（机制同源已验）；be-①/m3-1/m3-2 contract-first 降级维持（后端轮次清偿）。
- **状态**：**done**——开发+主会话独立验收+用户视觉验收通过（TC-UI-05 对照走查，2026-11-04）→ M3-UI 四段收官。

---

## R2 修复轮规格（2026-11-05，外部复审 NEEDS_CHANGES——P0×1 + P1×5 + P2 择要）

> 复审结论经主会话逐条对码核实**全部属实**。本轮文件白名单：`src/knowledge_lattice/web/**`、`benchmarks/report-ui3-tc-ui-walkthrough.md`、`docs/TEST-CASES.md`（仅 TC-UI-02 排除项一处）、本检查点。零 commit（验收后主会话提交）。

### P0-1 存储型 XSS（access.js govConfirmHTML）
- t() 是纯插值器不转义——**契约固化**：凡 t(key, params) 的参数值渲染进 HTML，调用点必须 esc()。修复 govConfirmHTML 的 disable.ask/retire.ask 两处（value/key 参数 esc）。
- **全库扫描**：全部 t(..., {...}) 调用点 + 全部 innerHTML 模板裸 `${}` 插值（非 esc/t/数值/常量）逐点审计，产出对账表；发现即修。

### P1-1 删除误报成功
- api.js 的 deleteDocument/deleteDataset/deleteMember 改为 apiJson 同款 !ok 抛 ApiError 语义（204 空 body → 正常返回）；docs.js delDocOk / access.js memDelOk / docs.js dsDelOk 相应简化为 catch 分径（403/404/409/500 各自如实 toast，失败不删行）。删除三路径口径统一。

### P1-2 同步统计恒空
- 后端 stats_json 已解析为对象（`_sem_run_dict`）——semRunStatsSummary 兼容双形态（typeof string 才 parse）；同款审计 builds/stats_json 消费位。

### P1-3 零授权新成员不可见
- 会话成员注册表 `state.mem.known`（username → {role?, expiresAt?}）：add-member 201、PATCH 响应、DELETE 移除时维护；latticeMembers() = export 用户名 ∪ known；app.js 身份菜单（loadUsernames）同源合并。加成员后立即可在授权格/详细抽屉分配首个授权。

### P1-4 成员编辑静默改权限
- 改角色：select 默认 = 会话已知 role（known 有则预选）；未知则空选项 + 确认禁用直至显式选择；确认行明示「role := X」。
- 改到期：显式二选一（设时点 / 改永久），禁用隐式空串=永久；known 有值则预填。
- PATCH 仍单字段发送（键缺失=不变语义不受影响）。

### P1-5 跨身份/组织 stale async
- `state.epoch` 计数器：resetOrgState / reloadAfterIdentityChange 时自增；全部异步装载（loadMeta/loadGrantsTable/loadUsernames/onEnterDocs/onEnterSemantic·probe/semLoadEntity/semSearch/ops 四装载/doSearch/pollDocTask）启动时捕获、写状态与 render 前比对，不等即弃。pollTask 感知 epoch 变化即停轮询。

### P2 择要
1. i18n：补动态缺键 st.degraded/sem.st.done/sem.st.disabled；删 9 死键（报告列明清单）；键数变化在对账报告声明。
2. 服务端中文 detail 混入 EN：不改后端（FR-8 服务端不感知语言的自然结果）——TC-UI-02 排除项补一句 + 走查清单附录 B 补注。
3. loading/error 补漏：orgs/ops/grants 装载失败显错误态（非空态）；语义详情错误停止转圈；quality undefined 防御。
4. importGrants 修正 Content-Type（apiFetch 支持 contentType 覆盖，CSV 走 text/plain）。
5. split("=") 截断含 = 取值：gSave/gCell 等 key 解析改首个 = 分割（indexOf）。
6. 复审列出的原型保真表外列差异：补入 report-ui3 附录 B（分类「实装按真实契约列集」）。
7. ui-0 检查点措辞勘误：「style 零改动」→「CSS 规则零改动（仅头注释版本行 +15 字节）」。

### 验证要求（子代理自检）
- P0 回归：POST 值含 `<img src=x onerror=…>` → 停用确认条渲染为文本不执行（断言无活节点/onerror 串以文本呈现）；同款抽测 t() 全调用点。
- P1 逐项实测（403 删除不删行 / stats 显示 / 加成员即见 / 改角色确认行 / 快速切换身份旧响应不落新视图）。
- 门禁 GATE PASS 1715+1 不增不减；i18n 键对账零缺键（新键数声明）；第三用例不动。

---

## R2 交付记录（2026-11-05，开发子代理自检后回填——主会话验收后提交）

- **改动**：web/ 九文件（api.js / app.js / i18n.js / views/access·docs·ops·orgs·search·semantic.js）+ docs/TEST-CASES.md 一处（TC-UI-02 排除项补句）+ benchmarks/report-ui3-tc-ui-walkthrough.md（附录 B 补第 10 项 + B-2 表列差异节）。零 commit / push / add。
- **P0-1 XSS**：govConfirmHTML disable.ask/retire.ask 参数 esc 修复；**t() 安全契约固化**于 i18n.js JSDoc（纯插值不转义——参数调用点 esc，或整结果在唯一插值点整串 esc，二取一；textContent 消费点豁免）。**全库对账**：t(key,{…}) 调用点 101 处逐点审计——①参数已 esc ~45 处；②数值/布尔参数 ~40 处；③受信 t() 返回值参数（common.loading what=）5 处；④textContent sink 1 处（settings.status.on）；⑤外层整串 esc（参数原文+唯一插值点 esc）~10 处（detailTitle/empty.ds/del.confirm×2/needDims/picked/uploading/identity×2/moreTitle/denied×3）；⑥**本轮修复 3 处**——govConfirmHTML ×2 + rail.connected（参数 esc 化归一，移除外层避免双重转义）。innerHTML `${}` 裸插值全库扫描**另发现 1 处**：semGraphSVG `var(--t-${tp})` style 属性插值（实体 type 为后端存储值，可属性逃逸）——esc 修复。成员用户名/审计 detail/语义 name 等注入面全数 esc 覆盖（实测 + 代码审计双确认）。
- **P1-1 删除误报成功**：deleteDocument/deleteDataset/deleteMember 收口 apiJson（!ok 抛 ApiError；204 空 body → {} 正常返回——_parseBody 已容错）；delDocOk（原已 catch 分径，维持）/dsDelOk（重写：409 RESTRICT 专属 toast + 其余 errToast）/memDelOk（重写：409 最后管理员/404 专属、失败不删行不收确认条）三路径口径统一；errToast 补跳过 401（与 403 同为 api 层统一 toast）。
- **P1-2 同步统计恒空**：semRunStatsSummary 兼容对象/字符串双形态（后端 `_sem_run_dict` 已解析直出——sqlite/pg 双方言核对一致）；builds 侧前端无 stats_json 直消费（build report 为服务端聚合 counts/ac_automaton 面），核对无同款问题。
- **P1-3 零授权新成员不可见**：`state.mem.known` 会话注册表（username → {role, expiresAt}）——POST 201 响应 {user_id, role, expires_at}（实测定）/PATCH 响应（回整行）/DELETE 成功维护，resetOrgState 清空；latticeMembers() = export 用户名 ∪ known；loadUsernames 与 loadGrantsTable 的 usernames 同源合并；null 透传语义修正（expires_at null=永久为合法值，仅 undefined 回退——`??` 误回退已改 `!== undefined` 判定）。access.mem.empty/footNote 文案同步改写。
- **P1-4 成员编辑静默改权限**：改角色——known 有 role 预选、未知空选项 + 保存禁用 + 「当前角色未知」提示，确认行明示「确认变更：role := X」随选择即时更新；改到期——显式二选一 select（设时点/改永久），known 值预填 + 确认行「expires_at := v / null」，设时点空值禁用保存（禁绝隐式空串=永久）；PATCH 仍单字段发送。编辑态输入框即时重渲染（确认行动态）。
- **P1-5 跨身份 stale async**：`state.epoch` 计数器（resetOrgState 与 reloadAfterIdentityChange 自增；resetOrgState 一并清零 state.loading 防旧标志卡死新装载）。**落位清单 23 处**：loadUsernames / loadMeta / resetOrgState / reloadAfterIdentityChange（app.js 4）；loadGrantsTable / loadGovernanceDims（access.js 2）；onEnterDocs / refreshSelectedDoc / loadQuality / loadQs / pollDocTask（docs.js 5）；onEnterOps + loadTasks·loadCoverage·loadAudit·loadStats（ops.js 5）；onEnterOrgs（orgs.js 1）；doSearch（search.js 1）；probeSemantic / semLoadSyncTab / semLoadEntity / semSearch / semSyncFilterRun / semDescribe / semAnnotate（semantic.js 7）——全部「启动捕获、写 state 与 render 前比对、不等即弃（含 finally 的 loading 标志）」；api.js pollTask 增 shouldStop 回调（感知即停返回 null，pollDocTask 静默弃）。
- **P2**：①i18n +15 新键 −9 死键 = **640 → 646（zh=en，零缺键零死键）**——新键：st.degraded / sem.st.done / sem.st.disabled（动态缺键 3）+ common.retry + access.grants.loadErr / ops.tasks.loadErr / orgs.loadErr / sem.ent.loadErr（错误态 5）+ access.mem.rolePick / roleConfirm / roleUnknown / expMode.set / expMode.perm / expEditPh / expConfirm（成员编辑 7）；死键 9：common.loadMore / access.member / access.grants.none / ops.audit.full / ops.audit.empty / ops.audit.col.time·actor·action·detail。②TC-UI-02 排除项补「服务端回显 detail」一句（**TEST-CASES 恰此一处改动**）+ 走查清单附录 B 第 10 项。③错误态补漏：grants/members（共用 g.error + grantsRetry）、ops tasks（tasksErr）、orgs（loadErr + orgsRetry）失败显错误卡非空态；语义详情 detailErr 错误卡 + 返回/重试（停转圈）；quality 防御（docId null 不取、畸形体回退、reason 缺失回退 —、qualResolve/qualIgnore selDoc 空守卫）。④importGrants contentType: "text/plain"（apiFetch 支持 opts.contentType 覆盖）。⑤gSave key 解析改首个 = 分割（indexOf）——全库唯一 split("=") 位点，gCell 整键透传不分割、构造端 join 天然安全（semOpenTab split(":") 已是首冒栏口径）。⑥走查清单附录 B 新增 B-2 节「实装按真实契约列集」九表逐列归档。⑦**申报未做**：ui-0 检查点 L106 勘误（「`<style>` 零改动」→「CSS 规则零改动（仅头注释版本行 +15 字节）」）——task-knowledge-lattice-ui-0.md 不在本轮白名单（R2 规格与任务书文件清单均未含），留主会话一行 Edit 清偿。
- **自检实测**（/tmp/ui2_seed.py 重建 + uvicorn :8960 + dev token 双模式，测毕杀净）：
  - ✅ **P0 回归**：POST values 造 `<img src=x onerror=window.__xss=1>` 取值（label 另含 `<script>`）→ 停用确认条 title **文本呈现**（innerHTML 实体形态 `&lt;img …&gt;`）、`window.__xss` undefined、`#main img` 活节点 0；XSS 用户名成员（DB 直插 `<b onmouseover=alert(9)>x`）成员表/授权格 roster 文本呈现零执行。
  - ✅ P1-1：staff_wang 删他人文档——API 403 复核 + UI 删除确认 → 403 detail toast、表格行与 state.docs.list 保留；dsDel 409 RESTRICT toast + 库保留；memDel 全生命周期（删 → known 移除 → roster 移除）。
  - ✅ P1-2：同步五源表与运行历史统计列显示「新增 21 · 更新 0 · 消失 0 · 退役 0」（种子 template_center run）。
  - ✅ P1-3：POST members（root0，org_admin + 2031 到期）→ 成员子标签与授权格 roster **立即**出现；身份菜单 usernames ∪ known 同源。
  - ✅ P1-4：改角色 known 预选 + 「确认变更：role := org_admin」；unknown（staff_wang）空选项 + 保存禁用 + 提示，显式选择后确认行更新；改到期预填 2031-06-30 + 确认行、空值禁用、改永久显式「expires_at := null」；**null 透传**实测（改永久后 known.expiresAt=null 不回退）；EN 文案同验（"Will set role := org_admin" 等）。
  - ✅ P1-5：fetch 人为延迟 4s + 快速切组织（epoch 0→2）→ 旧 grants 响应被弃（org:fin 视图 rows 0、无 org:tax 行泄漏、loading 不卡）；UI 上传后 700ms 切组织 → pollTask 停（session 行 0、无 stale mergeDocRow、切换后零 stage/done toast）。
  - ✅ P2-3：export 网络失败 → 「授权导出装载失败」错误卡 + 重试 → 恢复 rows=8、错误清除。
  - ✅ i18n：zh=en=646 零缺键零死键（引用收集含动态族展开：st.*/sem.type.*/sem.st.*/sem.via.*/docs.qual.*/sem.sync.ad.*/role.*/nav.*）；EN 全视图抽测无混语言。
  - ✅ 门禁：`uv run pytest -q tests/test_e2e_07_shell.py` 3 passed；**GATE PASS 1715+1 双后端双模式 0 skipped**（pg 臂 633 全实跑）——用例数不增不减；第三用例未动。
  - ✅ console 零 JS 错误（仅负向测试的 403/404/409 HTTP 资源日志）。
- **遗留**：①known 注册表为会话态——切换组织/重连后零授权成员仍不可见（名单源结构性限制，待 m3-1 #13 GET members）；②P2-7 ui-0 勘误待主会话清偿（见上）；③be-①/m3-1/m3-2 contract-first 降级维持（后端轮次清偿）；④TC-UI-01~05 人工走查待用户回填（R2 未改走查步骤，仅附录 B 扩充）。
- **状态**：**done（子代理自检）**——待主会话独立验收后提交。

### R2 交付记录（2026-11-05，主会话验收后回填）

- **复审结论核实**：外部复审（用户委托独立 agent）NEEDS_CHANGES——P0×1 + P1×5 + P2 若干；主会话逐条对码**全部属实**后立 R2 规格（上文）并委派 subagent 修复。
- **修复交付**：web/ 九文件（api.js DELETE 三函数收口 apiJson !ok 抛错 / epoch 23 处落位 / mem.known 会话注册表〔含 null 透传修正〕/ memRole·memExp 显式化确认行 / semRunStatsSummary 双形态 / govConfirmHTML+semGraphSVG style 插值转义 / t() 安全契约 JSDoc 固化 / i18n 640→646〔+15 −9 死键〕/ 错误态补漏+重试 / importGrants text/plain / gSave 首 = 分割）+ TEST-CASES 恰 1 hunk（TC-UI-02 排除项补服务端 detail 句）+ 走查清单附录 B 第 10 项与 B-2 九表列差异归档。
- **P0 全库审计**：t(key,{…}) 101 处 + innerHTML 裸插值全量对账（表见子代理报告）——本轮修 3 + 另发现 semGraphSVG `var(--t-${tp})` 属性插值 1 处。
- **主会话独立验收**：
  - ✅ **P0 XSS 回归独立复现验证**：注入 `<img src=x onerror=window.__xss=1>` 维度值（API 201）→ 停用确认条 payload **纯文本呈现**（payloadAsText=true / xssExecuted=false / 活 img 节点 0）。
  - ✅ P1-1 完整链：唯一管理员自删 → API 409 → UI toast「409：唯一管理员自删守卫」+ 行保留 + 确认条不关（单 eval 窗口内验证——首次量不到 toast 系 CLI 往返延迟吃掉 4.2s 窗口，测量方法问题非缺陷）。
  - ✅ epoch/known/stats/role·exp 代码位抽核 + deleteMember 直调 throw 断言（status=409 + 服务端 detail）。
  - ✅ **门禁独立复跑 GATE PASS**：1715+1 deselected、0 skipped、双后端双模式——用例数不变、第三用例未动。
  - ✅ i18n 独立复跑：zh=en=646 零缺键，动态缺键 3 个（st.degraded/sem.st.done/sem.st.disabled）全部补齐。
  - ✅ TEST-CASES diff 恰 1 hunk（529 行 TC-UI-02 排除项）；P2-7 勘误由主会话清偿（ui-0 检查点「style 零改动」→「CSS 规则零改动〔仅头注释 +15 字节〕」）。
- **遗留**：mem.known 会话态（刷新后零授权成员仍不可见——待 m3-1 #13 GET members 后端清偿）；服务端 detail 语言混入 EN 态已按口径豁免（TC-UI-02 排除项）；be-①/m3-1/m3-2 contract-first 降级维持。
- **状态**：**done**——R2 修复轮验收通过，随本检查点提交（M3-UI 终态：ui-0/1/2/3 + R2）。
