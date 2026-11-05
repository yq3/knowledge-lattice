# task-knowledge-lattice-ui-0 · 原型 v0.5.1 → v0.6 补画（issue #20 C 项）

> 段位：M3-UI 第 1 段（共 4 段：ui-0/1/2/3）。本段**只改 `prototype/index.html` 单文件**。
> 依据：issue #20（yq3/knowledge-lattice）C 项「后端有、原型未画」+ B① 任务面口径吸收。
> 性质：原型微调 = **非决策变更**（AGENTS.md §2——D 编号与冻结结论不动）。

## 硬约束

1. **唯一可改文件：`prototype/index.html`**。禁改 `src/**`、`tests/**`、`docs/**`、其余一切文件。完成后 `git status` 必须只显示该文件。
2. **不执行 git commit / push**。
3. 不引入新 CSS 设计语言——全部复用原型既有类（.ledger/.pill/.confirm/.upload/.drawer/.menu/.note/.chip/.vchip/.tag/.seg 等），少量内联 style 沿原型既有惯例。
4. 代码风格沿原型：模板字符串渲染、`esc()` 转义、`toast()`、`permEvent()`/`queryEvent()` 审计 mock、`state` 单对象 + `data-act`/`actions` 分发 + `data-in`/`onInput` 输入。所有新交互动作必须注册进 `actions` 表（渲染后绑定零额外代码）。
5. 中文文案沿原型「教学式 + 口径注记」风格（如「库不设权限，可见性由文档维度决定（D15）」）。

## 背景（子代理先读）

- `prototype/index.html`：2048 行单文件原型，mock 数据驱动（ORGS 两组织：01JORGTAX 税务事业部含语义层 / 01JORGFIN 财务共享中心无语义层）。导航组：知识（semantic/docs/search）/ 管理（access）/ 运维（ops）。
- 真实系统（`src/knowledge_lattice/api/`）已有而原型未画的管理面 = 本段补画对象。以下契约事实已核实，mock 按此对齐：
  - `GET /api/orgs`：系统管理员=全部组织；普通用户=本人 membership 组织（TC-AZ-02 存在性不泄露）。`POST /api/orgs`（sysadmin 专属）：id/name/**org_admin 三必填**（org_admin 必填=防无人可管的死组织；用户不存在 404——管理员不建账号 D16；重复 409）。组织**只停用不删除**（#14：status 列 active/disabled，停用后成员认证/检索/任务/webhook/语义面全拒）。
  - 成员三方法：`POST members`（user_id 须既有用户·JIT 建档，role=member|org_admin，expires_at 可空；已存在含过期行 409）/ `PATCH members/{uid}`（role/expires_at 键缺失=不变、显式 null=改永久；**已过期行 409**——删行重加是唯一恢复路径 T23；唯一管理员自锁/自删 409 守卫）/ `DELETE members/{uid}`（级联清本组织授权）。软停用=expires 置过去时点，零新列。授权格 = `PUT members/{uid}/grants` 全量替换（已有）。
  - 维度/取值：`POST dimensions`（新维度对存量文档=空值→放行）、`POST dimensions/{id}/values`（retired 维度 409 不扩值）、`PATCH values/{id}`（disabled 收紧 / **active=重新启用**——D19 恢复路径，dry_run 先给影响面）、`POST dimensions/{id}/retire`（已有确认条）。`DELETE datasets/{id}`：非空库 409 RESTRICT（先删文档再删库）。
  - 语义同步五适配器（枚举固定）：`template_center / metadata / scenario_config / report_center / yaml`。前四个可 `POST /semantic/sync/{adapter}` 手动触发；**yaml 无手动触发**——经 Git webhook 签名回调（HMAC-SHA256 over raw body，`POST /semantic/yaml/webhook`）。错峰窗口：夜间 02:00 档顺序执行；每日兜底 = maintenance `semantic_daily_sync`（G-19：无 webhook/无手动也有兜底轮）。删除保护：消失比例 >20% 整轮中止不落库（aborted_guard——原型 mock 已有样例，保留）。
  - `GET /api/orgs/{org}/embedding-coverage` 响应字段：`embed_model` / `dim` / `totals{done,total}` / 每知识库 `coverage[]{dataset_name,done,total}` / `reembed{status,done,total}`（重嵌入蓝绿窗口）。
  - `GET /api/orgs/{org}/stats`：`{maintenance: {…}}`——11 个注册表键（最近一次运行计数）：`credentials_purged / memberships_purged / tombstones_purged / task_rows_trimmed / audit_shipped / audit_months_sealed / audit_months_pruned / backup_snapshot / audit_outbox_trimmed / semantic_daily_sync / semantic_reconcile`（org_admin、只读）。
  - MCP：单 server 挂 `/mcp`，**8 工具**：`search / fetch / upload / list_documents / annotate / get_entity / search_entities / describe_table`。委托 token 口径：sub=用户、act=agent、org 单值 claim、**禁止 token 原样透传（D18）**。API 参考 = FastAPI OpenAPI `/docs`。
  - 任务：worker 子进程自动认领（心跳 15s / 租约 60s / attempts 上限 3），**无手动推进**；取消 = `POST tasks/{id}/cancel`（非终态→failed+'cancelled: by user request'，已终态幂等返现态）。

## 工作项

### C-1a 新「组织」管理视图（nav 运维组加「组织」项，icon 沿 ICONS 风格自配）

- **mock**：两组织各加 `status: "active"`；新增第三个样例组织 `01JORGHK 香港分所`（`status: "disabled"`、最小数据：2 维度、1 dataset、1 成员、0 文档、`semantic: null`、agent `hk-assistant`、`disabledAt: "2026-10-01 00:00:00"`）——演示停用态。`USERS` 加 `u0: "系统管理员"`。
- **系统管理员档（lens 菜单）**：每个组织的 lens 菜单顶部加固定项「系统管理员 · 跨组织」（uid=u0）。选中时：`lens()` 对 u0 返回 `{uid:"u0", role:"sysadmin", expires:null, perms:[], grants:{}}`（非成员的特殊档）；`memberValid`/`canSee` 对 u0 放行（mock 演示口径，页面注记「系统管理员视角 · 跨组织（mock 演示：组织内数据全显）」）；组织视图的管理动作（建组织/停用）**仅 u0 视角可用**，其他视角禁用 + title「系统管理员专属」。
- **组织 ledger**：列 = 组织（name + id mono）/状态（pill：active=ok 生效 / disabled=idle 已停用）/成员数/文档数/语义接入（`rev N` 或「未接入」）/agent/操作。
  - 停用/恢复：active 行出「停用…」→ 行内 `.confirm` 确认条（复用 dims 退役样式）：文案含「停用后成员认证 / 检索 / 任务 / webhook / 语义面全部拒绝；组织只停用不删除（#14）；审计同事务」→ 确认置 disabled + permEvent；disabled 行出「恢复」按钮（mock 直接恢复 + 注记）。
- **建组织抽屉**（复用 `.drawer` + `.upload` 表单栅格，head-act「＋ 新建组织」仅 u0 视角可用）：id（mono 提示如 01JORGTAX）/显示名/org_admin 用户 ID 三必填；脚注口径：org_admin 必填=防死组织；用户不存在 404（管理员不建账号，建档走 SSO JIT——D16）；重复 409；`POST /api/orgs` · 系统管理员专属。创建成功 → toast + 新组织入 ORGS（status active、空 dims/datasets/members、semantic null）。
- **视图头注记**：`GET /api/orgs`——系统管理员=全部；普通用户=本人 membership（跨组织存在性不泄露）。

### C-1b access 视图加「成员」子标签（sub-tabs 变四项：授权格/维度/成员/可见性矩阵）

- **成员 ledger**：成员（avatar+名+uid mono）/角色（org_admin|member pill；u0 不出现在此表）/成员关系（长期 / 至 {expires} / **已过期**置灰行）/语义权限（perms chips：semantic:read / semantic:admin / semantic:restricted）/操作。
- **操作**（org_admin 视角可用，非 admin 视角禁用+注记「组织管理员」）：
  - 改角色：行内 seg 或按钮切换 member↔org_admin（permEvent `member.update`；唯一管理员降级 → toast 409 守卫提示）。
  - 改过期：行内输入（`YYYY-MM-DD HH:MM:SS` 或空=永久；键缺失=不变、显式空=改永久 口径注记）。**已过期行改过期 → toast 409**：「已过期行不可续期——DELETE 后重加 + PUT grants 补授权（T23 三步）」。
  - 移除：`.confirm` 确认条（级联清本组织授权；唯一管理员自删 409 守卫注记）→ mock 移除 + permEvent `member.remove`。
  - 加成员（表头上方抽屉/内联表单）：用户 select（USERS 中非本组织成员）+ role + expires；口径注记：user_id 须既有用户（JIT 建档，D16 管理员不建账号）；已存在（含过期行）409。mock 加入 + permEvent `member.add`。
- **表下 note（T23 约束口径）**：软停用=置过期时点（零新列）；过期行 PATCH 409 → 删行重加三步恢复；移除级联清本组织授权（不破坏他组织）；`POST/PATCH/DELETE /api/orgs/{org}/members` + `PUT …/grants`（授权格子标签）。
- u0 视角在本子标签：只读 + 注记「系统管理员不做组织内成员管理（组织自治）」。

### C-1c 维度/取值 CRUD 补画 + docs 删知识库

- **维度子标签**：
  - 「＋ 新建维度」stub 按钮 → 真表单（`.confirm` 或内联行）：key（mono）/显示名/必选 checkbox；注记「新维度对存量文档=空值→放行，不会让任何人突然看不到；`POST /api/orgs/{org}/dimensions` · 组织管理员」。创建 → `dims.push({key,label,required,status:"active",source:"local",values:[]})` + permEvent `dimension.create`。
  - 取值形态升级：values 元组 [v,l] 扩为 [v,l,st?]（st 缺省=active；channel 维度给一个 disabled 样例值如 ["ONLINE","线上","disabled"]——演示停用态）。渲染：disabled 值加 `.v-off`（删除线）+「恢复」按钮；active 值加「停用」小按钮（title：`PATCH values/{id}` · dry_run 先给影响面 · 收紧进计算）；每维度 values 尾「＋ 取值」→ 内联输入（value+label）→ 加入（retired 维度禁用 + title 409 不扩值）。
  - 恢复口径注记：D19——重新启用恢复路径（停用可逆、退役不可逆）。
- **docs 视图知识库 seg**：当前选中库且为空（0 文档）且 org_admin 视角 → seg 尾「删除知识库」小按钮 → `.confirm`：非空库 409 RESTRICT（先删文档再删库；`DELETE /api/orgs/{org}/datasets/{id}`）；mock 删除 + permEvent `dataset.delete` + 回到「所有知识库」。

### C-2 语义同步面板五源形态（syncHTML 重构）

- 「源端事实同步」节改为**五适配器固定行总览 ledger**：适配器（mono）/最近运行（时间 + stPill）/新增/更新/消失/触发/说明（最近 note 截断）。
  - 前四行：手动「↻」按钮（沿现有 sync 动作行为：unshift run + tasks + permEvent）。
  - **yaml 行无手动按钮**——触发列显示「webhook」tag，说明列：「YAML 覆盖层经 Git 合并回调触发（HMAC-SHA256 签名验签，`POST /semantic/yaml/webhook`）；无签名 401」。
  - 总览下方保留既有「运行历史」表（现 syncRuns 表改名/加小节标题），aborted_guard 样例保留。
- **节脚注三条口径**：① 错峰窗口——每日 02:00 档顺序执行（防源端峰值）；② 每日兜底——maintenance `semantic_daily_sync`（G-19：无 webhook / 无手动触发也有兜底轮）；③ 删除保护——消失比例 >20% 整轮中止不落库并告警（aborted_guard）。

### C-3/C-4 ops 面板对齐真实响应

- **嵌入面板**（「嵌入与存储」节）：kv 改真实字段形态——`embed_model`（如 `qwen3-embedding-4b:2560`）/`dim`（2560）/`totals`（done/total + 百分比）/`reembed` 窗口（`running · 8/12` 蓝绿相位②口径注记：换模型=重嵌入流程，窗口期间新旧标签并存）；各库 coverage 条形保留；存储后端注记保留。头部注明 `GET /api/orgs/{org}/embedding-coverage`。
- **新「maintenance 计数」面板**（「嵌入与存储」节下方独立 section，同款卡片样式）：11 键 kv 两列排布（键 mono、值按 mock 形态：计数/日期串/状态串），头部「最近一次运行 {时间}」+ 注记 `GET /api/orgs/{org}/stats` · org_admin · 只读；`audit_outbox_trimmed`=已搬运 outbox 行保留期清理 的脚注。

### C-5 顶栏两 stub 真实化

- 「API 参考」按钮：`data-act="apiDocs"` → `window.open("/docs","_blank")` + toast「OpenAPI · `/docs`（与 design §6.2 REST 对齐）」。
- 「MCP 接入」按钮：`data-act="mcpMenu"` → 按钮下方弹 `.menu`（需在 topbar 容器内绝对定位，参考 lensPicker 的 menu 定位方式）：标题行「MCP 工具 · 单 server 挂载 `/mcp`」+ 8 工具列表（工具名 mono + 一句话中文：search=权限内检索 / fetch=取块原文 / upload=凭证三步上传 / list_documents=文档列表 / annotate=术语识别 / get_entity=实体与关系展开 / search_entities=实体检索 / describe_table=表列透传）+ menu-note：委托 token——sub=用户、act=agent、org 单值 claim；禁止 token 原样透传（D18）。

### B① 任务面口径吸收

- ops 任务表：running/leased/pending 行加「取消」按钮 → mock 置 `st:"cancelled"` + toast「`POST …/tasks/{id}/cancel` · 非终态→failed+'cancelled: by user request'；已终态幂等返现态」。
- 「推进任务」按钮（ops 头部保留）：改标签「模拟推进 · mock」+ title「实装=worker 自动认领（心跳 15s / 租约 60s / attempts≤3）+ 状态轮询，无手动推进」；**docs 头部的推进按钮移除**（只留「＋ 上传文档」）。
- ops lede 补一句：任务由 worker 子进程自动认领推进，本页只读 + 取消。

### 版本行与声明

- `<title>` 与 CSS 头注释、rail-foot：v0.5.1 → **v0.6**；rail-foot 的「信息结构对齐 design.md v0.8」改「对齐 design v0.9.9 + issue #20 C 项补画」；「原型 v0.5.1 · Mock 数据」→「原型 v0.6 · Mock 数据」。
- 文件 `<head>` 后加一行 HTML 注释声明：「v0.6（2026-11-03）：非决策变更——C 项补画（组织管理/成员/维度取值 CRUD/五源同步/运维面板/MCP 接入）+ 任务面口径，D 编号与冻结结论不动（issue #20）」。

## 验收标准（子代理自检后才算完成）

1. `git status`：仅 `prototype/index.html` 改动；无 commit。
2. 所有新 `data-act` 均已注册进 `actions`；逐项点检：组织视图（建/停/恢复/切 u0 视角）、成员子标签（加/改角色/改过期含 409 提示/移除）、维度（新建/加取值/停用/恢复）、删空库、五源总览手动触发、任务取消、MCP 弹层、API 参考。
3. 既有交互零回归：上传/检索/授权格/可见性矩阵/语义实体图/术语识别等原有 data-act 全部仍工作。
4. 浏览器实开验证零控制台报错（`python3 -m http.server` 起静态服务 + 截图走查；无浏览器条件时至少抽取全部 `<script>` 块做 `node --check` 语法校验 + grep 审计 data-act↔actions 对账）。
5. 视觉：未改动区域与 v0.5.1 像素级不变（全部复用既有类）。

## 交付报告格式

- 改动摘要（按工作项分条：新增函数/mock 字段/actions 清单）
- 自检结果（上述 5 项逐条勾验）
- 遗留/取舍点（如实现中发现的口径冲突——记录不要擅自扩大范围）

---

## 交付记录（2026-11-03，主会话验收后回填）

- **开发**：subagent（general-purpose，规格书驱动）；**验收**：主会话独立复核。
- **改动**：`prototype/index.html` 单文件 2048 → 2500 行（+495/−43）；**CSS 规则零改动**（仅 `<style>` 头注释版本行 +15 字节——R2 复审勘误：原表述「style 零改动」不精确）。
- **主会话独立验收**（不采信子代理自检）：
  - ✅ git status 白名单（仅 prototype/index.html + 本规格书未跟踪）；零 commit。
  - ✅ diff 全量审读：守卫忠实（T23 三步 409 / 唯一管理员自锁 409 / D16 404 / RESTRICT 409 / retired 不扩值 409）、actions 返回语义正确（不可变动作 return false 防重渲染）、resetOrgState 收纳新交互态。
  - ✅ 浏览器实测（http.server + playwright）：建组织流端到端（表单校验→创建→toast）；组织/成员/维度/五源同步/运维面板/MCP 弹层（恰 8 工具）逐面 DOM 断言；任务取消 running→cancelled；权限门卫（u0 系统管理员：建组织可用、组织内管理面只读、语义面无 semantic:read 拒入——语义面按真实口径未对 u0 放行，属忠实行为）。
  - ✅ console 零 JS 错误（仅 favicon 404 环境噪音）。
- **子代理报告的遗留/取舍点**（逐条落档）：
  1. **#14 组织停用端点未实装**（属 m3-1 段，src 无对应路由）——confirm 条以「组织停用 · #14（status: active → disabled）」表述，不编造具体路由。
  2. **yaml 行「最近运行」列**显示「—（见下方词典构建）」——yaml 变更走 builds 历史（rev 42 building by webhook），syncRuns 无 yaml 行；规格书只规定触发/说明两列，时间列以指引文案处理。
  3. **新建组织 mock 成员表为空**（按规格书字面「空 dims/datasets/members」）；实装中 POST /api/orgs 是否自动挂首任 org_admin membership 未在核实范围，toast 注明「mock 演示」——**主会话核实：是，create_org 即挂 org_admin membership（admin.py m2-5 实装），ui-1/2 实装时对齐**。
  4. **测试中自愈一处自身引入的缺陷**：MCP 弹层（顶栏静态菜单不经 render 重建）在点击其它动作后不收起、浮层拦截内容点击——已在通用 click 分发加一行「非菜单内、非自身切换的动作点击统一收起弹层」，lens/org picker 的 toggle 行为不受影响（复验 open→nav→closed、二次点击 toggle 正常）。
  5. **建组织抽屉「取消」与头部按钮共用 `data-act=orgNew`**——沿原型 newDs 抽屉既有 toggle 双按钮模式，自动化选择器需限定作用域，人工使用无影响。
- **主会话补充口径注记**：
  1. 语义面对 u0（系统管理员档）未放行——semAccess 校验 semantic:read/admin，SYSADMIN.perms=[] → noperm 空态。属真实权限口径的忠实行为（sysadmin 不自动拥有组织内语义权限），非缺陷。
  2. be-① 列表/be-② explain 契约冻结评论未发（用户裁定 2026-11-03 本会话不涉及后端范畴）。
- **状态**：**done**——开发+主会话独立验收+用户走查通过（2026-11-03）→ 进 ui-1。
