# task-knowledge-lattice-ui-2 · 授权格/可见性矩阵/任务审计/语义视图/组织视图全保真（issue #20 ui-2 段）

> 段位：M3-UI 第 3 段。ui-1 已交付应用框架 + docs/search + access/ops 功能平移；本段把 access/ops 升级为原型 v0.6 全保真形态，新增**业务语义视图**与**组织管理视图**。视觉与信息结构基准 = `prototype/index.html` v0.6（已提交 93adebd）。
> 基线：门禁 1715+1 双后端双模式 0 skipped（e71c849 后工作区）。

## 硬约束（沿 ui-1，不变）

1. **文件白名单**：`src/knowledge_lattice/web/**`、`tests/test_e2e_07_shell.py`（仅当视图注册/资产清单断言需扩——新增 views/semantic.js、views/orgs.js 时同步）；其余一切禁改（prototype/ 只读）。零 commit / push / add。
2. 无构建链；i18n 全文案走 t()（zh/en 双字典同步扩）；前端不演算 ACL（B5）；contract-first 降级诚实。
3. 沿 ui-1 既有代码约定：VIEWS/INPUTS/actions 注册表、api.js 每端点一函数、异步动作自管渲染、errToast 不重复 403。

## 契约事实（已核实主干 + 待核实清单）

### 已核实（直接用）
- `GET /api/orgs/{org}/semantic/entities?q=&types=&top_k=(1..50)`（semantic:read；q 1..MAX）→ `{entities: [{id, type, key, name, brief, score, via}]}`——排序链 别名精确 1.0>前缀 0.8>拼音 0.7>FTS 0.5>向量（via='vec'）；**restricted 实体不出现**（T-S9）。类型枚举 = concept/system/scenario/template/template_field/report/report_item/table/column。
- `GET /api/orgs/{org}/semantic/entities/{entity_id}?expand=&depth=(1..2)&fanout_limit=(1..200)&include=`（include ⊆ curated/attrs/aliases，缺省 ['curated']）→ `{entity: {id,type,key,name,status, curated?, attrs?, aliases?}, nodes, edges, truncated, dict_rev}`。**id 与 key 二选一**（key 形如 `type:name` 可走 `?key=`? ——REST 路径只有 {entity_id}，用 int id）；不存在/restricted 无权/非 active 一律 **404 存在性零泄露**；expand 形如 `uses>`/`uses<`/裸 rel 双向；include=curated,attrs,aliases 取全。
- `POST /api/orgs/{org}/semantic/annotate` body `{text(≤4000 字，超长 400), context_entities?≤20, prefer_types?, fuzzy?=false}`（semantic:read）→ 识别结果（**hits/candidates 字段形态自查** `core/semantic/` annotate 实现——含 surface/entity/layer/锚点语义）。
- `GET /api/orgs/{org}/semantic/sync-runs?limit=&adapter=&status=`（**semantic:admin**）→ 运行记录；`POST /api/orgs/{org}/semantic/sync/{adapter}` → 202（semantic:admin；adapter 枚举 template_center/metadata/scenario_config/report_center——yaml 不走此端点）。
- `GET/POST /api/orgs/{org}/semantic/builds`（admin）、`GET .../builds/{build_id}/report`（admin）、`GET /api/orgs/{org}/semantic/l0`（read——返回 markdown 片段 + dict_rev；**字段自查**）、`GET /api/orgs/{org}/semantic/tables/{table_key}/describe?columns=`（read——未登记表 403）。
- 成员三方法（**全部已实装 m2-6 A3**）：`POST /api/orgs/{org}/members` {user_id, role=member|org_admin, expires_at?} 201（用户不存在 404·D16；已存在含过期行 409）；`PATCH .../members/{user_id}` {role?, expires_at?}（**键缺失=不变、显式 null=改永久；已过期行 409**；唯一管理员自锁 409）；`DELETE .../members/{user_id}` 204（级联清本组织授权；唯一管理员自删 409）。**无 GET members**（m3-1）——名单源 = grants/export 用户名。
- `GET /api/orgs` → `{orgs: [{org_id, name, role?, expires_at?}]}`；`POST /api/orgs` {id, name, org_admin} 201 → `{org_id, name, org_admin}`（**sysadmin 专属 403**；org_admin 必填防死组织；用户不存在 404；重复 409）。**组织停用 #14 未实装（m3-1）**——contract-first：`PATCH /api/orgs/{org}` body `{status: "disabled"|"active"}` 自然契约，404/405 → 降级 toast「待 m3-1」。
- 维度授权数据口径：`grants/export` CSV = **local 授权真相源**（sync 行不导出）；`PUT grants` 只替换 local。**API 无维度 source 字段**——原型「sync 维度只读格」不可复刻，授权格不标 sync 态（以 export=local 为口径，诚实差异）。

### 待核实（子代理读源确认字段，报告落档）
- nodes/edges 元素字段：`store/sqlite/backend.py` `sem_expand_graph`（nodes 应含 id/key/type/name/status；edges 应含 src/rel/dst/source——以实读为准）。
- annotate 结果字段：`core/semantic/`（annotate 函数）+ tests（m2s 断言）。
- l0 / builds / build report / describe_table 响应字段：对应 core 函数与 tests。
- quality_report（docs 视图已有——本段不动）。

## 工作项

### A. access 视图升级为原型全保真（四子标签）

1. **授权格**（默认子标签，替换现 chips 编辑器为格矩阵）：
   - 结构沿原型 `.lattice-wrap/.lattice/.cellbtn`：行=成员（export 用户名 + role/expires 徽标；role 从**何处**得？GET /api/orgs 普通用户面带 role——org_admin 视角下其他成员 role 拿不到 → 行头只显用户名 + 库内 expires（export 第 4 列），role 留空或「成员」默认——诚实差异注记）；列=各维度取值（listDimensions）。
   - 格状态 = export 行 (username,dim_key,value,expires)；点击格 = 该维度授权集增删后 **PUT 全量替换**（只动该成员全部 local 行——体量注意：一次 PUT 提交该成员全部 picked 行，expires 沿库内值、新授权 null 永久）；带 expires 的格虚线徽标；空授权集维度 → 注记「= NOT EXISTS 只放行空值」。
   - 图例 + 底注沿原型（全量替换语义/NOT EXISTS/退役维度不出现）。
   - **B① 行级到期编辑保留**：成员行尾「详细」按钮 → 抽屉内沿用 ui-1 chips 编辑器（逐行 expires 输入、prefill 语义不变）+ CSV 导入导出迁入抽屉。
2. **成员子标签**（新，真端点）：成员 ledger（用户/角色/成员关系/操作）+ 加成员表单（user_id 手输或 select 非既有用户占位——**无用户目录端点，手输为主** + role + expires）+ 改角色（PATCH；唯一管理员守卫 403/409 如实回显）+ 改过期（PATCH；过期行 409 提示删行重加三步）+ 移除（DELETE 确认条：级联清本组织授权注记）。T23 约束底注沿原型。
3. **维度子标签**：保留 ui-1 既有（停用/恢复/新增取值/退役/新建维度†）——补「新建维度」表单的字段名与原型对齐（key/label/必选）。
4. **可见性矩阵子标签**（占位）：空态卡片「待 be-① 文档列表 + be-② explain 端点（issue #20 D-①②）落地后开放——前端不演算可见性（B5）」+ 说明成员×文档矩阵将展示什么。**不实装矩阵**。

### B. ops 视图升级

- 任务 ledger 保留；**审计区改双泳道**（原型 .lanes）：查询类事件 vs 治理类事件——按 `action` 前缀分流（自查 audit 事件名规律：`domain/audit_events.py`——如 search/annotate 类 vs grant./member./dimension./document. 类；两泳道各自空态；scope=metadata 时不渲染 detail 只显元数据行）。
- 覆盖率/maintenance 面板保留（ui-1 形态已对齐原型）。

### C. 业务语义视图（新 views/semantic.js，nav 知识组第一项「业务语义」）

- **进入探针**：`GET l0` → 403 = 无 semantic:read 空态；200 且 dict_rev 空/0 = 未接入空态（原型同款文案：只有词法+向量两路）；正常 → 记 dict_rev 展示（head tag「在用 dict_rev N」）。
- **实体与关系子标签**：
  - 工具栏：搜索框（q → search_entities top_k=20）+ 类型 facet chips（单选，types 参数——**计数无契约**：原型 facet 计数是全图口径，真实无 counts 端点 → facet 不带计数，诚实差异）。
  - 无搜索时落地页 = 类型总览 tiles（无计数——显示类型名+英文枚举，「按类型搜索」入口）。
  - 结果表：名称/类型/键/brief/score/via → 行点击进详情。
  - 详情（独立页态）：entity header（类型色 tag/name/key/status/curated 定义·口径·消歧/attrs 摘要/aliases chips）+ **对象图 SVG**（nodes/edges → 按关系×方向分组、每组显示前 3 + 「+N」占位（truncated 或组内超 3）、点节点切换焦点=重新 get_entity、深度 1/2 seg 切换 refetch）+ 关系列表（rel/dir/端点/来源 curated|sync）+ `describe_table` 透传面板（type=table 时：表元数据+列清单+每列语义实体标注——列名与 column 实体 name 对齐）。
  - 404 → 「不存在或无权或非 active（存在性零泄露）」空态。
- **术语识别子标签**：textarea + fuzzy 开关 → POST annotate → 标注渲染（mark 下划线 + 实体名浮标，颜色按类型）+ hits 表（原文/实体/类型/层/依据）+ candidates（低信任候选，fuzzy 开启时）——沿原型 .ann-in/.ann-out/.annot 结构。
- **同步与构建子标签**（semantic:admin 门槛：非 admin → 只读注记 + 数据面探针 403 降级）：
  - 五源同步总览（四可手动 POST sync/{adapter} → 202 toast「已投递任务」；yaml 行 webhook 注记——签名口径）；运行历史表（sync-runs limit=50，adapter 过滤 select）。
  - 词典构建表（GET builds：rev/状态/时间/触发/说明）+「触发构建」按钮（POST builds → 202）+ 构建报告链接（GET report → 展开面板：计数/规模/耗时/冲突面——字段按实返回渲染）+ 构建中 tag。
  - L0 片段面板（GET l0：dict_rev + 片段条目 chips/markdown 预览）。

### D. 组织管理视图（新 views/orgs.js，nav 运维组「组织」项）

- ledger：org_id/name/当前 token 可见性标注（GET /api/orgs 结果）；`POST /api/orgs` 建组织表单（三必填 + 404/409/403 守卫如实）——**仅当基 token 为 sysadmin**（如何判？GET /api/orgs 返回全部组织数 > 本人 membership 数不可判…… 用 decodeJwt(baseToken) 无 role 信息 → 以「尝试 + 403 如实回显」为口径，按钮常显、提交后 403 toast「系统管理员专属」）。
- 停用/恢复：contract-first PATCH /api/orgs/{org} {status}（†收口单函数注释 `// m3-1 contract-first`）→ 404/405 降级 toast；确认条文案沿原型（#14 全员拒绝/只停不删/审计同事务）。

### E. api.js 扩展（沿既有模式）

searchSemanticEntities / getSemanticEntity(id, {expand,depth,fanout_limit,include}) / annotateText / listSyncRuns / triggerSync / listBuilds / triggerBuild / buildReport / getL0 / describeTable / addMember / patchMember / deleteMember / createOrg / setOrgStatus†。全 i18n 键补 zh/en。

### F. 测试更新（最小面）

- 资产清单断言补 `/static/views/semantic.js`、`/static/views/orgs.js`；视图注册断言补 semantic/orgs 两项。第三用例仍不动。门禁 `uv run pytest -q` 全绿 0 skipped（用例数不增）。

## 端到端验证（子代理必做，沿 ui-1 方法）

- 造数扩展（/tmp/ui1_seed.py 增补或新脚本 /tmp/ui2_seed.py，不入仓）：语义面造数参照 tests 中 m2s 语义用例（sem_entities/sem_relations/sem_aliases/构建词典——直接读 conftest 或 test_sem_* 的造数 SQL/fixture；至少：8-10 实体跨 4 类型、若干关系、1 次 build 使 dict_rev 就绪、别名几条含精确/上下文）。成员面：再加 1 成员供改角色/移除。
- 浏览器走查清单：语义三子标签全流程（搜索→facet→详情→图 SVG 点节点→深度切换→describe_table→annotate 标注→sync 总览手动触发 202→builds 表→L0）；授权格点格→PUT 生效（export 复验）→详细抽屉 B① 到期编辑；成员加/改角色/改过期 409 路径/移除；审计双泳道；组织视图建组织（sysadmin 基 token）+ 停用降级 toast；中英切换；console 零 JS 错误。

## 验收标准（自检后才算完成）

1. git 白名单外零触及、零 commit。
2. i18n 对账（含新增全部键）zh=en 零缺键。
3. 端到端清单逐项过、console 零 JS 错误。
4. `uv run pytest -q` 全绿 0 skipped（用例数不增）。
5. 视觉：access 授权格/ops 泳道/语义视图结构与原型 v0.6 对照（同套类名）；诚实差异清单（facet 计数/成员 role 缺位/sync 只读格/可见性矩阵占位）逐条在报告列明。
6. contract-first 仅组织停用一处（†）+ 既有 be-①/m3-1 三处维持。

## 交付报告格式

文件清单与行数 / 契约适配点（含待核实项的实读结论）/ 自检 6 项勾验 / 诚实差异与遗留清单。

---

## 交付记录（2026-11-04，主会话验收后回填）

- **开发**：subagent（general-purpose）；**验收**：主会话独立复核。
- **交付物**：2 新视图（semantic.js 729 / orgs.js 152）+ access.js 重写 685（授权格矩阵+成员子标签+可见性占位）+ ops.js 双泳道 218 + api.js +14 函数（320）+ i18n zh=en=612 键 + app.js/index.html 接线 + 测试断言扩两视图；style.css 零改动（原型类名 ui-1 已全携带）。
- **主会话独立验收**：
  - ✅ git 白名单（web/** + 壳测试）；style.css 零改动核实；零 commit。
  - ✅ 代码审读：测试 diff（第三用例未动）/ 授权格渲染与 **latCell ±点格全量替换语义**（expires 沿库内、新授权 null、pop 动画）/ B① 详细抽屉（ui-1 chips 编辑器保留）/ semantic.js 骨架（探针三态/404 零泄露/搜索 facet）。
  - ✅ **门禁独立复跑 GATE PASS**：1715+1 deselected、0 skipped、双后端双模式——与基线严格一致。
  - ✅ 浏览器实测（重建 /tmp/ui2-data 环境 + 铸新 token）：boss_admin 直连 → 语义探针 ok（dict_rev 就绪）→ 搜索「留抵」3 命中 → 实体详情（nodes/edges/SVG/关系行）→ annotate 3 mentions 带 mark 渲染 → 授权格点 OS → **export 复验 PUT 生效**（CN+OS→仅 CN，回点恢复）→ 组织视图 2 行 + 建组织抽屉三必填；console 零 JS 错误（仅预期资源级 4xx）。
  - ✅ i18n 独立对账：557 引用键 vs zh=en=612，零缺键。
  - 🔧 **主会话小修一处（app.js 两行）**：连接成功（模式 A/B）后 conn 弹层不收起——浮层遮挡页面元素（elementFromPoint 命中菜单 label、点格被拦）——成功路径补 `closeMenus()`；实测修复后点格链路通。子代理走查未暴露此问题系其点击均落在菜单覆盖区外。
- **环境注记**：走查中 l0 返回旧 dict_rev 为孤儿 uvicorn 进程持有已删 DB 文件 fd 所致（环境假象非产品缺陷），清进程后正常。
- **诚实差异**（子代理清单，验收认可）：facet 无计数、成员行 role 不可得（无 GET members）、授权格不标 sync 只读格（无 source 字段）、可见性矩阵占位（be-①②）、aliases 无 kind/mode 徽标、组织停用 contract-first（m3-1）、查询审计道空态注记（m3-2 G-22）、L0 联动走 entity_key 搜索。
- **状态**：**done**——开发+主会话独立验收+用户走查通过（2026-11-04）→ 进 ui-3。
