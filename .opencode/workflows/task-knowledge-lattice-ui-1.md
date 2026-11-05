# task-knowledge-lattice-ui-1 · web/ 重建：设计系统 + 应用框架 + 文档 + 检索（issue #20 ui-1 段）

> 段位：M3-UI 第 2 段（ui-0 已完成——原型 v0.6 为视觉与信息结构基准）。本段把 `src/knowledge_lattice/web/` 从功能薄壳重建为原型级 UI：**应用框架（顶栏/导航/组织与身份切换/连接设置）+ 文档知识 + 检索测试**，并**平移既有管理面功能**（权限/维度治理/任务审计——能力零回退，新设计系统样式；授权格/可见性矩阵/语义视图/组织管理视图留 ui-2 全保真）。
> 依据：issue #20 正文 + 裁定评论（文件拆分口径）+ 测试回归清单评论。

## 硬约束

1. **文件白名单（git status 硬验收）**：
   - 可改/新增：`src/knowledge_lattice/web/**`（index.html / style.css / i18n.js / api.js / app.js / views/*.js，删除旧 app.js 内容重写）
   - 可改：`tests/test_e2e_07_shell.py`（仅前两用例重写，第三用例 `test_rest_upload_task_status_and_search_loop` **一字不动**）
   - **禁区**：`src/knowledge_lattice/**` 其余一切（api/ core/ store/ adapters/ mcp/ worker/）、`prototype/`（只读基准！）、`docs/`、其余 tests
2. **零 commit / push / add**。
3. **无构建链**：原生 HTML/JS/CSS + 按序 `<script>` 经典脚本（无 ES modules、无 npm、无打包）。`/static` 挂载整个 web/ 目录，`views/*.js` 自动可达。
4. i18n（FR-8 冻结）：全部用户可见文案走 `t()` 键（zh/en 双字典）——动态渲染的模板字符串同样如此；服务端不感知语言。
5. 视觉基准 = `prototype/index.html` **v0.6**（git HEAD 工作区现状）：同套 CSS 变量与组件类、同 DOM 结构习惯。未画的真实数据形态（加载/错误/空态）按同一设计语言补。
6. 前端不演算 ACL 裁定（issue B5）：不做可见性演算/解释卡演算；服务端 400/403 回显。

## 契约事实（已核实——规格内嵌，勿再摸索；字段以本清单为准）

### 认证与身份
- 请求头：`Authorization: Bearer <token>` + `X-Org-Id: <org>`。org 解析：token org claim 优先 / X-Org-Id 兜底 / 不一致或缺失 400。**UI 约定：token 与 X-Org-Id 保持一致**。
- `POST /api/dev/token` body `{user_id?, org?, act?}` → `{token, token_type, user_id, org, act}`。给自己签（无 user_id 或 =自己）任意 token 可；给他人签须**系统管理员** token，否则 403。**仅 dev/test 环境注册**（生产 404——UI 需优雅降级：提示 dev-only）。
- `GET /api/orgs` → `{orgs: [{org_id, name}]}`（sysadmin=全部；普通用户=本人 membership 组织，另带 role/expires_at 字段——按 org_id/name 用即可）。
- 成员名单**无 GET members 端点**（m3-1 #13）：身份菜单数据源 = `GET /api/orgs/{org}/grants/export`（org_admin-only，CSV 首列 username）∪ 自己 + 手动输入 user_id 兜底。

### 元数据
- `GET /api/orgs/{org}/datasets` → `{datasets: [{id, name, description}]}`
- `GET /api/orgs/{org}/dimensions` → `{dimensions: [{id, key, name, required, enabled, values: [{id, value, label}]}]}`（仅 status=active 维度与 active 取值；disabled 取值不出现在列表）
- `POST /api/orgs/{org}/datasets`（新建库）与 `POST /api/orgs/{org}/dimensions`（新建维度）**未实装**（m3-1 #13）——按自然契约先行实装（POST JSON），404 → 降级提示「待 m3-1 后端轮次」；调用收口在 api.js 单函数并注释 `// m3-1 contract-first`
- `DELETE /api/orgs/{org}/datasets/{id}` → 204；非空 409（RESTRICT）

### 文档与上传
- **人工上传 = multipart 直传**：`POST /api/orgs/{org}/documents`，FormData 字段 `file`（文件）、`dataset`（id）、`title?`、`dims`（JSON 字符串 `{dim_key: [value,…]}`，按 key）、`doc_id?`（覆盖上传显式携带）→ 202 `{doc_id, task_id, status:"queued", pending_version}`。错误：400 校验（维度取值不在授权内等）/ 403 / 409（pending 已存在）。凭证三步式（POST /api/uploads → PUT 字节 → MCP upload 消费）**仅 agent 面**，REST 无 consume 端点——页面脚注注记即可。
- **文档列表 `GET /api/orgs/{org}/documents` 未实装**（D-① be-1 轮补）。按提议契约先行：`?dataset=&limit=&offset=` → `{documents: [{doc_id, title, dataset, dims, active_version, active_status, active_error, pending_version, pending_status, chunk_count, quality_open, updated_at, visible}], total}`；404 → docs 视图降级横幅「列表端点待 be-1——上传与任务跟踪可用」+ 会话内已上传文档（内存缓存）列表。收口单函数注释 `// be-1 contract-first`。
- `GET /api/orgs/{org}/documents/{doc_id}` → `{doc_id, title, dataset, active_version, active_status, active_error, pending_version, pending_status, pending_error, source, updated_at}`（**无 dims 字段**——pane 维度区从列表行缓存取，无则显示「待 be-①」注记）
- `PATCH /api/orgs/{org}/documents/{doc_id}/dimensions` body `{dims: {key: [values]}}`（按 key 全量替换，未提及 key 不动）→ `{doc_id, dims}`；pending 中 409
- `DELETE /api/orgs/{org}/documents/{doc_id}` → 204（owner/org_admin）
- `GET /api/orgs/{org}/documents/{doc_id}/quality` → 质量报告（owner/org_admin/ACL 可见；字段读 `core/docs/quality.py` 的 `quality_report` 确认后适配）
- `GET /api/quality-flags/sample?n=&seed=` → `{org, flags: [{flag_id, chunk_id, doc_id, reason, mean_sim, avg_idf}]}`（org_admin；无 text/suggested 字段——补标走人工输入）
- `PATCH /api/quality-flags/{flag_id}` body `{keywords?, tags?, state?}`（至少一项；keywords/tags 空格分隔原样写入）→ 更新后 flag

### 任务
- `GET /api/orgs/{org}/tasks` → `{tasks: [{task_id, type, status, doc_id, error, attempts, heartbeat_at, lease_until, created_at, updated_at, target_version?}]}`
- `GET /api/orgs/{org}/tasks/{task_id}` → 同上单任务；`POST .../tasks/{task_id}/cancel` → 非终态转 failed+`cancelled: by user request`；已终态幂等返现态
- 状态流 pending→leased→running→done/failed；worker 自动推进，**无手动推进**

### 检索
- `POST /api/search` body `{query, top_k(1-100，默认8), datasets?, doc_filter?, entities?, auto_entities?}` → `{results: [{rank, chunk_id, doc_id, dataset(名), dataset_id, title, page_no, sheet_name, score, dims, source, snippet(120字), matched_entities?(int 实体 id 列表)}], notice: {vector_pending: bool, degraded: [str]}}`
- 实体路开关 → `auto_entities: true`；403 = 成员关系无效/无授权（denied 空态）
- **无逐块路归标记与过滤计数**——原型 hit 卡的 fts/vec/ent 徽标与右侧漏斗图不实装（ui-2 视契约再议）；matched_entities 显示计数徽标（名称联动留 ui-2 语义视图）

### 权限/治理（平移自现薄壳，逻辑不变）
- `GET /api/orgs/{org}/grants/export`（org_admin）→ CSV 文本 `username,dim_key,value,expires_at`（仅 local 行）；引号形态 CSV 需兼容（沿用现薄壳解析）
- `PUT /api/orgs/{org}/members/{user_id}/grants` body `{grants: [{dim_key, value, expires_at|null}]}` → `{removed, inserted}`（全量替换 local；目标无有效成员关系 400）
- `POST /api/orgs/{org}/grants/import`（body=CSV 文本，`?dry_run=1` 预览）→ `{diff: {added, removed, changed}, rejected, applied_users}`
- `PATCH /api/orgs/{org}/dimensions/{dim_id}/values/{value_id}` body `{status: "disabled"|"active", dry_run?}` → dry_run={impact…} / 执行结果
- `POST /api/orgs/{org}/dimensions/{dim_id}/values` body `{value, label?}` → 201（retired 维度 409）
- `POST /api/orgs/{org}/dimensions/{dim_id}/retire?confirm=1` → `{impact}` / 执行
- `POST /api/orgs/{org}/documents/{doc_id}/reindex?embed_model=` → `{type, task_id}`

### 运维
- `GET /api/orgs/{org}/embedding-coverage` → `{embed_model, dim, totals{done,total}, coverage[{dataset_name,done,total}], reembed{status,done,total}?}`
- `GET /api/orgs/{org}/audit?limit=` → `{scope: "full"|"metadata", events[{created_at, actor, action, detail_json}]}`（sysadmin=metadata 剥 detail）
- `GET /api/orgs/{org}/stats` → `{maintenance: {…11 键…}|null}`（org_admin）

### 通用
- 错误体两种形态：`{detail}`（HTTPException）或 `{error}`（JSONResponse 直返）——api.js 统一 `body.detail || body.error` 解析
- MCP：单 server 挂 `/mcp`，8 工具 search/fetch/upload/list_documents/annotate/get_entity/search_entities/describe_table；API 参考 = FastAPI OpenAPI `/docs`（新窗打开）

## 文件结构与职责（issue 裁定拆分——顺序即 `<script>` 引入序）

```
web/
├── index.html   # 静态壳：.app 骨架（topbar: brand/orgPicker/API 参考/MCP 弹层/语言切换/连接设置入口；rail: nav 挂载点 + rail-foot；#main 挂载点；#toasts）+ 按序 script
├── style.css    # 原型 v0.6 <style> 整体迁入（不拆）+ 末尾追加小节「ui-1 additions」（语言切换/连接弹层/加载态/禁用态等少量补充，注释标明）
├── i18n.js      # 机制保留（I18N/t/currentLang/setLang/applyI18n/TITLES），字典全量重写扩展；TITLES 更新为「Knowledge Lattice 控制台」
├── api.js       # REST 适配层（见下）
├── app.js       # 框架（见下）——DOM 在 DOMContentLoaded 才 boot（晚于全部 script 注册）
└── views/
    ├── docs.js    # 文档知识
    ├── search.js  # 检索测试
    ├── access.js  # 权限（授权 chips 编辑器 + CSV + 维度治理——功能平移）
    └── ops.js     # 任务与审计（任务/覆盖率/审计/stats/重嵌入——功能平移）
```

**脚本协同模式（经典脚本，无模块）**：i18n.js → api.js → app.js（定义 `state`/`$`/`esc`/`toast`/`actions` 基表/`render`/`VIEWS` 注册表空对象/boot 于 DOMContentLoaded）→ views/*.js（各自 `VIEWS.docs = {render, onEnter}` + `Object.assign(actions, {…})` 注册视图动作）。全部注册完成后 boot 渲染。

### api.js（REST 适配层——全部 fetch 收口）
- 连接状态：`cfg = {baseToken, activeToken, org, lensUserId}`，localStorage `lattice.cfg` 持久化；`apiFetch(path, opts)` 注入 Authorization/X-Org-Id/Content-Type，统一错误解析（detail||error）、401 →「认证失败——检查连接设置」toast + 打开连接设置、403 → toast detail、网络异常 → toast
- `reissue({org?, userId?})`：用 baseToken POST /api/dev/token 重签 activeToken（dev 形态身份/组织切换）；403 → 「代签须系统管理员基 token」；404 → 「dev 端点仅开发环境——可直接粘贴已签 token」
- 领域函数（每个端点一函数，be-1/m3-1 contract-first 三处单函数收口）：listOrgs / listDatasets / createDataset† / deleteDataset / listDimensions / createDimension† / listDocuments† / getDocument / patchDocumentDims / deleteDocument / uploadMultipart(FormData+进度 toast) / getDocumentQuality / sampleQualityFlags / patchQualityFlag / listTasks / getTask / cancelTask / pollTask(taskId,{interval=1.5s,until 终态,timeout=120s}) / search / exportGrants / importGrants / putGrants / patchValueStatus / createValue / retireDimension / reindex / embeddingCoverage / audit / stats（†=contract-first）
- 时间显示工具 `short(ts)`（UTC 字符串切 MM-DD HH:mm）沿原型

### app.js（框架）
- 状态：view 当前视图 / sub（access 子标签）/ 各视图数据缓存（dims/datasets/orgs/members估算/docs 会话缓存/lastSearch…）/ ui 状态（抽屉、确认条）
- 渲染循环沿原型模式：renderRail（组织 picker=GET /api/orgs 菜单 + lens picker=export 用户名∪self+手动输入行；nav 四项带计数）+ 当前视图 render 到 #main + data-act 全局委托分发 + data-in 输入（input/change/compositionend 语义沿原型）+ 焦点恢复
- 组织切换 = reissue({org}) + 重载元数据与视图数据 + 状态重置；身份切换 = reissue({userId, org}) + 同上（普通成员无法枚举他人——手动输入框常驻）
- 连接设置弹层（顶栏齿轮，.menu 表单）：baseToken / org / lens 输入 + 「重签并连接」+ 「直接使用已签 token」两模式 + 连接状态显示（当前身份/org/token 有效性）
- 语言切换（中|EN 沿现机制）→ langchange → 全视图重渲染（缓存数据复用，仅文案换）
- 顶栏：brand + orgPicker + API 参考（/docs 新窗）+ MCP 弹层（8 工具静态清单 + 委托 token 口径 D18）+ langSwitch + 连接设置

### views/docs.js（文档知识——真数据形态）
- head（标题/lede 沿原型文案 i18n 化）+「＋ 上传文档」抽屉
- 知识库 seg（所有知识库 + 各库计数 + org_admin「＋ 新建知识库」†表单 + 选中空库 org_admin「删除知识库」确认条 409 口径）
- 列表区：listDocuments† 可用 → ledger 表（文档/维度 chips/版本双态/分块/质检待处理/更新时间——**无视角列**，待 be-① visible）；404 → 降级横幅（D-① 说明 + 上传/跟踪照常）+ 会话内已上传文档行
- 上传抽屉：知识库 select + 文件 input（真实文件，非原型假文件名）+ 维度 chips（必选校验；**授权预判不做**——服务端 400/403 内联回显）+ multipart 提交 → 202 后：加入会话缓存 + 选中该文档 + 任务轮询（pollTask → 阶段推进 toast，终态停止）+ 脚注「agent 走凭证三步」
- 详情 pane：kv（库/文档 ID/更新时间/source）+ 版本双态与阶段进度条（stages 样式沿原型；首传到 lexical 切在用/覆盖到 full 原子切换口径注记）+ 维度 chips（列表行缓存或 PATCH 回显）+「修改维度」（内联编辑 → PATCH；pending → 409 提示）+ 质检区（getDocumentQuality org_admin/owner：flags 列表 reason 中文化 + mean_sim/avg_idf + 补标输入（keywords/tags）+ 忽略/解决按钮 → patchQualityFlag）+ 删除（确认条 → deleteDocument → 移出缓存）+ **可见性解释区 = 占位说明「待 be-② explain 端点」（不演算）**

### views/search.js（检索测试——真数据形态）
- qbar + qopts（知识库 select、auto_entities 开关 tag「M2-S3」）+ Enter/按钮触发
- 结果 hit 卡（沿原型 .hits/.hit 结构）：rank 徽标 / snippet / title·页·sheet·库 / dims chips / score bar+数值 / matched_entities 计数徽标 / source
- 空态（无结果/被过滤说明换成契约内文案——被过滤计数不在契约，不显示）、403 denied 空态、加载态
- 右 pane：notice 展示（vector_pending → 「N 份仍在嵌入只参与词法路」语义；degraded[] → 降级标签列表）+ 检索管线说明（多路→同一 ACL→融合重排，i18n）+ 当前连接身份提示

### views/access.js（功能平移——新样式）
- 子标签：授权 / 维度
- 授权子标签（**逻辑等价平移自现薄壳 app.js 的 loadGrants/renderGrantChips/_rowExpiresInput/saveGrants/downloadCsv/importCsv**）：成员 select（export 用户名）+ 维度 chips 编辑（选中态 + 逐行 expires 输入框，B① 逐行独立语义保留）+ 保存全量替换 + CSV 导入（dry_run diff 展示）/导出下载
- 维度子标签（**平移 loadGovernanceDims/askDisableValue/askRetireDim/runConfirmed**）：维度 ledger（key/name/必选/取值 chips）+ 取值停用（dry_run 影响面→确认）/恢复 + 取值新增（POST values 真实端点）+ 维度退役（影响面→确认）+ 新建维度†表单（404 降级）

### views/ops.js（功能平移——新样式）
- 任务 ledger（含行内「取消」按钮非终态）+ 类型/状态中文化 pill
- 嵌入覆盖率面板（embed_model/dim/totals/每库 bars/reembed 窗口）+ 重嵌入投递（doc_id + embed_model? → reindex）
- 审计表（scope 提示：metadata=系统管理员剥详情）+ stats maintenance kv 面板（11 键，maintenance null → 「尚无运行记录」）

## tests/test_e2e_07_shell.py 更新口径（前两用例，第三用例不动）

- `test_shell_served_with_two_views_and_i18n`（改名 `test_shell_served_with_app_frame_and_i18n` 或近似）：
  - GET / 200；html 含 `id="langSwitch"`、`data-i18n=`、`lang="zh-CN"`、app 骨架（`id="app"` 或 `.app`）
  - 资产清单（全 200）：/static/style.css、/static/i18n.js、/static/api.js、/static/app.js、/static/views/docs.js、/static/views/search.js、/static/views/access.js、/static/views/ops.js
  - i18n.js 含 `I18N`、`"zh"`、`"en"`、`localStorage`（机制断言平移——FR-8）
  - 视图注册断言：app.js 文本含 `VIEWS` 且四个视图文件各自含其注册（如 docs.js 含 `VIEWS.docs`）
- `test_shell_uses_api_contract`：端点断言对象改为 api.js + views/*（拼接读取），端点集合保持 {"/api/orgs/", "/documents", "/tasks", "/api/search", "/datasets", "/dimensions"} 不减
- docstring 更新为五视图新形态说明；模块 docstring 注明 ui-1 重写口径

## 本地端到端验证（子代理必做）

1. 造数脚本 `/tmp/ui1_seed.py`（**不入仓**）：参照 `tests/conftest.py` app_env 的 SQL 造数模式，直写 sqlite：建 2-3 用户（其一 `is_system_admin=1`）+ org:tax + memberships（org_admin/member）+ region/tax_type 维度与取值 + 1 dataset。DB 放 `/tmp/ui1-data/lattice.db`
2. 起服：`LATTICE_DATA_DIR=/tmp/ui1-data LATTICE_ENV=dev uv run uvicorn 'knowledge_lattice.app:create_app' --factory --port 8960`（无嵌入网关配置 → 词法路即可测：上传到 searchable_lexical、FTS 检索命中）
3. playwright 浏览器走查：连接设置贴 sysadmin token（POST /api/dev/token 自签）→ 组织/身份切换（含给他人代签）→ 上传→轮询→lexical 检索命中全链 → 授权格编辑保存 → 值停用 dry_run/确认 → 任务取消 → 审计/覆盖率/stats 面板 → 中英切换全页生效 → be-1/m3-1 三处降级横幅/toast → 401/403 路径（错 token、无权视角）
4. 门禁：`uv run pytest -q tests/test_e2e_07_shell.py` 迭代 → `uv run pytest -q`（sqlite 全量，期望 **1715+1 双模式 0 skipped 不减**，用例数不增）

## 验收标准（子代理自检后才算完成）

1. `git status` 白名单外零触及、零 commit。
2. i18n 对账：脚本抽取全部 `t("…")` 键，zh/en 双字典全存在、无缺键；抽查主要视图无硬编码中文（代码注释除外）。
3. 端到端走查（上述浏览器清单）逐项通过、console 零 JS 错误。
4. `uv run pytest -q` 全绿（0 skipped），test_e2e_07 前两用例按新壳断言、第三用例未动。
5. 视觉：docs/search 框架结构与原型 v0.6 对照（同套类名/布局）；access/ops 平移功能完整可用（样式新设计系统，授权格/矩阵不要求）。
6. 降级诚实：be-1 列表 / be-② explain / m3-1 建库建维度三处降级文案准确指向后端段，不假装可用。

## 交付报告格式

- 文件清单与行数；各文件职责要点
- 契约适配点（与规格清单不一致处——如响应字段出入，逐条记录）
- 自检 6 项逐条勾验（含命令与关键输出）
- 遗留/取舍点（发现的问题只记录不扩大范围）

---

## 交付记录（2026-11-03，主会话验收后回填）

- **开发**：subagent（general-purpose，规格书驱动）；**验收**：主会话独立复核。
- **交付物**：web/ 十文件（index.html 99 / style.css 605〔原型 v0.6 样式整体迁入 + ui-1 additions 59 行〕/ i18n.js 762〔zh=en=342 键〕/ api.js 251 / app.js 476 / views: docs 491 + search 106 + access 408 + ops 196）+ tests/test_e2e_07_shell.py 前两用例重写（第三用例零改动）。
- **主会话独立验收**：
  - ✅ git 白名单（web/** + 壳测试；prototype 改动为 ui-0 遗留未提交）；零 commit。
  - ✅ 代码审读：测试 diff / api.js 全文（双 token 模型、错误统一解析、28 领域函数、三处 contract-first 收口注释）/ app.js 全文（渲染循环·焦点恢复·VIEWS/INPUTS 注册表·异步动作自管渲染）/ docs.js 全文 / search.js 全文 / access.js B① 三态语义（picked/expires/existing + prefill 仅预填新选行）逐行核verified。
  - ✅ **门禁独立复跑 GATE PASS**：sqlite+pg 双后端、常规+python -O 双模式，1715 passed + 1 deselected(manual)，0 skipped——与基线 1715+1 严格一致。
  - ✅ 浏览器实测（重建环境：issue_dev_jwt 铸 token + uvicorn :8960）：root0 直连如实 403（sysadmin 无成员关系）→ 代签 boss_admin → 元数据装载（2 维度/2 库）→ be-① 降级横幅呈现 → 真实文件上传（选维度→multipart→pollTask→v1 searchable_lexical）→ 检索「留抵税额 退还」1 命中（title/snippet/dims/score 卡片）→ EN 切换（nav/Knowledge 生效）→ access（6 授权行/双子标签）→ ops（5 任务/coverage/20 审计/stats）；console 零 JS 运行时错误（仅预期资源级 403/404）。
  - ✅ i18n 独立对账：330 引用键 vs zh=en=342 字典，剔除正则误报后零缺键；动态拼接键（nav.*/st.*/docs.qual.*）全在场；唯一缺口 st.degraded 为不可达状态且 stLabel 有原始串回退——无害。
- **子代理报告的契约适配点**（逐条落档）：
  1. stats maintenance 实测 **12 键**（规格写 11）——面板按返回键全量渲染不写死。
  2. org_admin 无维度授权时上传同样 403（FR-4 新旧取值校验）——UI 不预判、detail 回显。
  3. 取消响应附 `cancelled` 布尔——终态判断用 status+error 前缀，未依赖。
  4. notice.degraded 实测含 `embed_unreachable`（无嵌入网关环境）——原样展示。
  5. listDimensions 仅返回 active 维度/取值——「恢复」按钮基于会话内停用动作记忆渲染，刷新后不可见（诚实限制）。
- **遗留/取舍点**：
  1. **覆盖上传（doc_id 显式携带）无 UI 入口**——契约函数已支持，表单留 ui-2。
  2. **sampleQualityFlags 收口未挂视图**（误报抽查 UI 留 ui-2）。
  3. sysadmin 基 token 直连组织时 meta 403 噪音——如实回显（真实语义），代签成员视角后全通。
  4. 上传默认库 = datasets[0]（按 id 字典序）——非 bug，可后续加「记住上次选择」。
  5. 走查中 playwright 双触发/竞态为工具行为——程序化精确操作复核通过。
- **状态**：ui-1 开发+验收完成，待用户浏览器走查 → 通过后进 ui-2。
