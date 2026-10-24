---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m0a-2
target: knowledge-lattice
coderTaskId: ses_e98dcd1bfffe04K9p9RBaE3IcT
testerTaskId: ses_e98a31ccaffer12VqYpc7BDE0m
committerTaskId: ses_e9873539bffe85AWIf3IEKyzqA
status: done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 839bdedeff32c4ae85c6d553c4cb900fd4a41097
reviewedSha: 839bdedeff32c4ae85c6d553c4cb900fd4a41097
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["knowledge-lattice/src/knowledge_lattice/core/docs/acl.py（新增：编译器四步+AclDeniedError，不碰 SQL）", "knowledge-lattice/src/knowledge_lattice/store/sqlite/backend.py（新增：SqliteBackend read_membership/read_grants 单条 SQL 三重过滤）", "knowledge-lattice/src/knowledge_lattice/store/sqlite/acl_render.py（新增：AST 节点+builder+SQLite 渲染器双写法+InValue 拒空集+embed_model 谓词）", "knowledge-lattice/tests/（新增 11 文件：test_acl_01~07、test_emb_02、test_matrix_t1_t5、test_matrix_t20_t22、test_regress_m0a1_followups）", "knowledge-lattice/src/knowledge_lattice/config.py（遗留①注释修正）", "knowledge-lattice/src/knowledge_lattice/store/sqlite/connection.py（遗留③WAL 重试耗尽包装 RuntimeError）", "knowledge-lattice/src/knowledge_lattice/store/sqlite/migrate.py（遗留③FK OFF 复查移入 try/finally）", "knowledge-lattice/tests/test_scaf_03_migrations.py（遗留③跳过分支补 foreign_keys==1）", "knowledge-lattice/tests/conftest.py（标准矩阵 fixture 12 用户/5 文档/双组织）", "knowledge-lattice/tests/helpers.py（NOW_TS/grant_by_key/seed_doc_dims 双写/seed_searchable_doc）"]
endReason: null
createdAt: 2026-10-23T12:42:39+0800
updatedAt: 2026-10-23T17:11:00+0800
---

# task-knowledge-lattice-m0a-2: M0a-2 ACL 编译器——AclPlan 编译 + AST/渲染器 + 编译器单测先行

## 任务原文

（需求 + 验收标准，写全——这是恢复时唯一的上下文来源）

**目标项目**：`knowledge-lattice/`（企业知识层 POC，需求 v0.9 / 设计 v0.9，设计冻结纪律——实现问题走测试用例与 issue，coder 禁改 `docs/` 下需求/设计/用例文档，禁动 `prototype/`）。M0a 三段拆分之第二段（M0a-1 已合入 develop：merge commit 28125a8）。

**会话要求（用户指定）**：本任务 coder / tester / committer 全部**全新会话**（不复用 M0a-1 的任何 task_id）。

**运行时**：Python **3.12.10**（uv 托管，`.python-version` 已钉）。测试栈 pytest（`uv run pytest`）。

**范围**（design §5.1 + §8 M0a.3 的编译器部分）：

1. **维度 ACL 编译器**（`core/docs/acl.py`）：输入 `user_id` + 组织上下文 → 输出方言无关 **AclPlan**（M0a-1 已定型类型：frozen dataclass）。逻辑按 design §5.1 四步：① 第 0 步成员关系校验（含过期，无有效行即拒绝 403 语义；管理员豁免仅限管理端点，检索路径同样拒绝）；② 授权展开（同一 SQL 含授权过期 `expires_at > :now` 过滤 T1、active 维度过滤、停用取值过滤 T3）；③ 对每个 `status='active'` 维度编译统一模板（**有值则过滤、空值放行**；空授权集 → `NOT EXISTS` 单条件禁止 `IN ()`；retired 不生成条件；required/enabled 不影响过滤）；④ 外层常量约束（`c.version = d.active_version AND c.tombstone = 0 AND d.org_id = :org`）+ embed_model 谓词节点（TC-EMB-02）
2. **AST builder + SQLite 渲染器**：产物由 AST 渲染 SQL **禁止字符串拼接**（TC-ACL-01 结构断言 And/Or/NotExists/InValue 节点）；渲染收口 store 层（D24——`store/sqlite/` 侧；AclPlan 本体方言无关）；「无 `IN ()`」为 Plan 层不变式
3. **visible_docs 备选写法**（TC-ACL-07）：基于 `document_dimensions` 的 visible_docs CTE 与按块 `json_each` 模板双写法、同一授权展开函数、结果集逐字等价（M0b 实验选定后删其一——本任务双写法都要）
4. **编译器单测先行**（T1~T5、T20、T22 的 M0a 形态）：在真实 SQLite 库上执行编译产物断言可见性

**验收标准**（TEST-CASES §一 TC-ACL-01~07 + TC-EMB-02 + §3.2 T1~T5/T20/T22 + §六 M0a 行"编译器单测先行"句）：

| 用例 | 要点 |
|---|---|
| TC-ACL-01 | AST 括号化与渲染等价：u_full 多维度显式括号 AND；AST 节点树断言无字符串拼接；渲染 SQL 可 prepare 且与手写等价 SQL 结果相同 |
| TC-ACL-02 | 统一空值模板（本地 fixture 不复用标准矩阵，只启用 region 单维度）：主断言 AclPlan 结构层（NotExists \| Or[Exists,InValue] 组合）；行为断言 u_cn_r 见 d_cn_r+d_empty_r、u_os_r 只见 d_empty_r；SQLite 文本快照仅渲染器附带 |
| TC-ACL-03 | 空授权集 → NOT EXISTS 单条件（维度片段级断言，非整份产物）；该用户只见 tax_type 空值文档、region 照常叠加；全局无 `IN ()` |
| TC-ACL-04 | 生命周期解耦：required/enabled 1→0 产物逐字不变；retired 不生成条件（唯一放宽）；新建维度零消失编译空值放行 |
| TC-ACL-05 | 第 0 步成员关系校验：无 membership / expires_at=昨天 → 编译入口拒绝不产 WHERE；有效则正常 |
| TC-ACL-06 | 外层常量约束与 FTS 路同构：Plan 层常量节点固定、三路共用同一 Plan；SQLite 渲染断言版本条件在 FTS JOIN 上 |
| TC-ACL-07 | visible_docs 备选逐字等价：json_each 模板 vs visible_docs CTE 同一矩阵结果集相等（T5/T6/T22 两写法都测） |
| TC-EMB-02 | embed_model 查询谓词（Plan 层）：谓词固定节点 + 参数绑定当前 config 标签；行为断言随 M1 |
| T1 | 过期授权清理未跑仍不可见：`expires_at > :now` 过滤——CN 不在授权集、d_cn 不可见 |
| T2 | 成员续期不复活旧授权（行为半句）：过期检索拒绝；DELETE 重插后授权集空、d_cn 不可见（触发器半句 M0a-1 已覆盖） |
| T3 | 停用取值收紧：OS disabled 后 u_full 授权集变 [CN]、d_os 不可见 |
| T4 | 维度改可选/停用不放宽：产物 diff 为空 |
| T5 | 可选维度有值则过滤：u_cn 无 tax_type 授权不见 d_cit、见空值文档 |
| T20 | 新建维度零消失/回填只收紧/生命周期不放宽/仅退役放宽（审计半句 M2——退役事件入 outbox 断言可延后，条件消失断言必做） |
| T22 | 无授权维度只见空值文档；空集不出 `IN ()`（维度片段级） |

**边界（本任务不做）**：BM25 检索管线/FTS 查询链/MCP/REST/鉴权中间件/静态页壳（M0a-3 范围——本任务用例可直接执行编译产物 SQL 验证可见性，但不实现 retrieve.py 管线）；PG 渲染器（M0b spike）；TC-ACL-08 rerank 双断言（M1）；TC-EMB-02 检索行为半句（TC-EMB-07，M1）；T20 审计半句（M2）；`sem_*` 相关（M2-S）。

**Git**：分支 `develop_opencode`（开工第一步 `git fetch origin && git merge origin/develop` 同步——develop 已含 M0a-1 merge commit 28125a8）；每轮 commit `[task-knowledge-lattice-m0a-2] R<n>`，commit 前同步 origin/develop；不 push。

**相关文档**：knowledge-lattice/docs/design.md（§5.1 编译器/统一模板/AclPlan、§5.2 检索管线接口签名——只看签名不做实现）、docs/TEST-CASES.md（TC-ACL-01~07、TC-EMB-02、T1~T5/T20/T22、§六 M0a 行、口径段共享 fake fixture）、docs/known-gaps.md（G-2 fuzzy 层/G-3 restricted 静默缺失——认知背景）、M0a-1 检查点（AclPlan 类型与 store 结构现状）。

## 需求确认

- [x] 用户已确认（2026-10-23——需求+遗留清单复述后用户同意，含三角色全新会话要求与调用预告确认）
- 历史遗留事项清单：见下节

## 遗留事项（跨任务移交）

- [x] **承接自 task-knowledge-lattice-m0a-1（已 done，移交 M0a-2 条目默认并入本任务）**：① `config.py:20` 注释 `connect.py`→`connection.py`（R2 改名不彻底唯一遗漏，一行修正）；② 为 P3-1/2/12/13/19 补 3 条轻量回归测试（事务中 FK OFF → MigrationError / `:memory:` journal 失败 RuntimeError+连接关闭 / `__init__` 导入身份 pkg.migrate 为模块、pkg.migrate_db is migrate.migrate_db、pkg.connect is connection.connect）；③ R2 复审其余 P3 择要（journal_mode 查询纳入重试、重试耗尽包装 RuntimeError、FK OFF 复查移入 try/finally、跳过分支测试补 foreign_keys==1 断言）——触碰 migrate/connection 文件时顺手，本任务不强制触碰则顺延——**✅ 三项全部清偿（R1 commit 7e68936：①config.py:20 已修；②3 条回归测试落地且经 tester 独立核验连接关闭断言真实；③3 项已做 + journal_mode 查询经核实确已由 M0a-1 R2 落地——committer R1 第七节裁定"遗留承接整体合格"）**
- [ ] **M0b 批次（不并入本任务，去向已注明）**：backend 参数化骨架；DDL 两处执行层修正勘误登记；P3-3/4/5/7/8/11/15/16/17/18/23
- [ ] **M1 批次（不并入本任务）**：FTS5 trigram/自定义词表判据
- [ ] **新增移交（本任务 R2 committer P3 记录项，2026-10-23 登记）**：
  - [ ] **移交 M0b/M1 顺手**：CTE 内层 `v.status='active'` 残留（值 disabled 窗口双写法差异，committer R2 P3-1——移除或明确口径+补 value-disable 竞态测试）；P3-1 竞态回归入仓（编译后退役同一 Plan 双写法等价，约 5 行，committer R2 P3-2）；`render_visible_docs_select` 恶意 key 常量/标识符断言（committer R2 P3-3）；白名单 `re.match`→`fullmatch`（committer R2 P3-4，prefix 仅 trace 标签无安全影响）；标识符路径不变式 docstring（committer R2 P3-5）；migrate 成功路径恢复失败告警（committer R2 P3-6）
  - [ ] **移交 M1**：T6 完整切换链（committer R1 P3-4）；conftest channel 口径回写用例或 fixture 选项（committer R1 P3-6）；grants 写路径一致性校验（服务层断言/触发器——committer R2 调研借鉴节）
  - [ ] **移交 M0b**：CTE 过滤下推（实验前处理或报告注明口径，committer R1 P3-5）；`_Renderer` 私有+不得跨调用拼接片段文档化（committer R2 P3-7）；`render_expr` 移除记录（M0a-3 若需用改走 `_Renderer`/`render_sql`，committer R2 P3-8）
  - [ ] 记录性：tester R2 报告计数笔误（15→19 个零 diff 文件，committer R2 P3-9，不影响结论）；test_acl_02 快照绑定渲染遍历序（committer R2 P3-10，AST 变更时同步）
- [ ] 无其他

## 交付记录（2026-10-23）

- PR：https://github.com/yq3/lab/pull/45（base=develop，head=develop_opencode，commits=7e68936[R1] + 839bded[R2]，diff 23 files）
- push：`55846be..839bded develop_opencode -> develop_opencode`（用户已确认授权）
- 评审留痕：committer `gh pr review --comment`（review id PRR_kwDOTsiHgs8AAAABT1fvIQ——作者自审平台限制同 M0a-1，COMMENTED 完整留痕复审结论/双 SHA/测试证据；PR mergeable=MERGEABLE、mergeStateStatus=CLEAN）
- evidence manifest：已写入 PR description 末尾 `## Evidence Manifest` 小节（三 SHA=839bded、PASS/APPROVED、gate_commands=[uv run pytest, uv run python -O -m pytest]、stale=false；原内容零删改、占位句已替换，复验 9/9 通过）
- **合入完成（2026-10-23 17:10 用户确认）**：PR #45 state=MERGED，mergeCommit=`9a7daa09bd49fa61cfab3e7b1ffe3d68fccf8d6a`；origin/develop 前进 `28125a8..9a7daa0`（merge commit 保留 R1+R2 完整历史）；develop_opencode 远端分支按 D30 约定保留，M0a-3 继续在此分支开发

## 轮次记录

- R1 启动异常记录（2026-10-23）：首次 Coder 调用（ses_e98ecae69ffekxMMH4hvZ4YSl9）两次返回均为空，机械核验无任何产出（HEAD 未动/无 m0a-2 commit/工作区干净）——判定会话失效，按 §4.3.1 新开 Coder 会话（检查点 coderTaskId 随新调用更新），新会话从检查点恢复上下文、从头实现
- R1: coder 完成（2026-10-23，commit `7e68936` 于 develop_opencode，22 files +1728/−19，父提交=28125a8——新增 core/docs/acl.py 编译器（四步+AclDeniedError 不碰 SQL）/ store/sqlite/backend.py（read_membership/read_grants 单 SQL 三重过滤）/ acl_render.py（AST frozen 节点+渲染器双写法+InValue 拒空集+embed_model 谓词）/ 11 个测试文件；修改 config.py 遗留① / connection.py / migrate.py / test_scaf_03 / conftest 标准矩阵 fixture / helpers）。遗留承接：①②全做、③中 3 项做（WAL 重试耗尽 RuntimeError TDD 红转绿 / FK OFF 复查移 try/finally / 跳过分支补断言）+ 1 项声明已由 M0a-1 R2 落地（journal_mode 查询纳入重试——**与 committer M0a-1 R2 报告"查询在 try 外"表述矛盾，待复审核实**）。自测：TDD 红灯（ModuleNotFoundError×10）→ `uv run pytest` **78 passed**（存量 34 不回归+新增 44）；`python -O` 78 passed 1 warning（预期）；未 push；docs/prototype/检查点零触碰；supervised-coding 机械核验：HEAD=7e68936 在 develop_opencode、工作区干净 ✓
- R1: tester PASS（2026-10-23，全新会话，报告原文见"最新验证意见原文"节；testerTaskId=ses_e98a31ccaffer12VqYpc7BDE0m；testedSha=7e68936 前置校验一致；78 passed 双模式；验收表 15 条+遗留 3 项逐条勾验全过（Plan 层不变式/维度片段级断言/AST 节点树/双写法同一授权展开/行为断言真实执行产物 SQL/:memory: 连接关闭真实断言）；**独立探针交叉验证**——不复用测试断言独立造数 9 用户×双写法逐字等价全过、拒绝组精确；**journal_mode 矛盾点核实**：connection.py:43-46 查询确在重试循环内，committer M0a-1 R2 所述"查询在 try 外"指不落在 try/except 块内、纯读 pragma 语义正确——coder 声明与代码事实一致，无实现问题）；回归零弱化（test_scaf_03 唯一改动为纯新增 2 行断言）；边界零越界（无 retrieve.py/FTS 链/MCP/REST/PG 渲染器，22 files 与申报一致）；tests/ 业务代码零改动、docs/prototype 零触碰）
- R1: committer NEEDS_CHANGES（2026-10-23，全新会话，报告原文见"最新验证意见原文"节；committerTaskId=ses_e9873539bffe85AWIf3IEKyzqA；reviewedSha=7e68936 前置校验一致；**P1×1 必修**：ACL 渲染器绑定参数名由维度 key 直接拼接（acl_render.py:163/235/370——key 是库内数据，含 SQL 记号的 key 可注入注释掉 org_id/版本/tombstone 常量，跨组织泄露；修法=渲染器自控安全参数名序列+InValue.param_prefix 白名单校验 fail-closed+回归测试）；**P2×1 应修**：read_grants 取值 JOIN 未校验 v.dimension_id=dim.id（backend.py:67-68——FK 合法的畸形授权行可跨维度挂取值越权；修法=JOIN 加一行+畸形行测试）；**P3×8 记录**（CTE status 二次读取竞态/finally 取证措辞/覆盖盲区 3~5 条/T6 深度记 M1/CTE 过滤下推 M0b 实验/conftest channel 口径 M1/finally 包 sqlite3.Error/membership 分支合并——均不阻塞）；**需求边界问题：无**；tester 报告核对属实（抽查 8 处）；调研借鉴检查：架构取舍均吸收、P1-1 属实现级净化问题非调研缺口；遗留承接整体合格；supervised-coding 裁定修复范围：R2 修 P1-1+P2-1+P3-1/2/3/7（committer 建议顺手项）+P3-3 覆盖盲区轻量断言，P3-4/5/6/8 登记移交）
- R2: coder 完成（2026-10-23，commit `839bded` 于 develop_opencode，6 files +361/−79，父提交=7e68936）——P1-1/P2-1/P3-1/2/3/7 逐条响应全部"已修"：P1-1 参数名改渲染器自控序列 `g<seq>_<i>`（_Renderer 状态ful 重构）+ InValue.param_prefix 标识符白名单 fail-closed + 三条注入回归（恶意 prefix 构造即拒 5 变体 / 恶意 key 下三常量齐全+参数名全标识符+剥字面量后无注释记号 / 双组织真实执行）——**修复前攻击实测复现**：`x_0) OR 1=1))) --` key 使 d_gl_empty 越权可见（红灯存档），修复后仅 d_tax；P2-1 JOIN 补 `v.dimension_id = dim.id`（畸形行红灯实测 VAT 混入 region，修复后剔除）；P3-1 CTE 移除 status 二次读取（消除竞态不等价）+CTE 内层补同源防御；P3-2 措辞修正；P3-3 补 5/5 条覆盖盲区断言（超出至少 4 条要求）；P3-7 finally 包 sqlite3.Error。不做项（P3-4/5/6/8）按裁定登记移交未触碰。自测：TDD 红灯 4 项修复目标全红→`uv run pytest` **87 passed**（存量 78 不回归+新增 9）；`python -O` 87 passed 1 warning（预期）；未 push；docs/prototype/检查点零触碰；supervised-coding 机械核验：HEAD=839bded 在 develop_opencode、工作区干净 ✓
- R2: tester PASS（2026-10-23，续接会话，报告原文见"最新验证意见原文"节 Tester R2 小节；testedSha=839bded 前置校验一致；87 passed 双模式；修复项 7 项逐条勾验全过——P1-1 经独立攻击复现对照取证（legacy 渲染下 `--` 注入点位于 org 常量之前=攻击面真实；R2 渲染器 29/29 探针全过=修复有效）；P3-1 竞态态专项探针（编译后退役同一 Plan 双写法仍等价）；回归=R1 的 78 条零弱化（15 个存量测试文件零 diff）；不做项 P3-4/5/6/8 零触碰；tests/ 业务代码零改动、docs/prototype 零触碰）
- R2: committer APPROVED（2026-10-23，续接会话，报告原文见"最新验证意见原文"节 Committer R2 小节；reviewedSha=839bded=HEAD 核验一致；P1×0/P2×0——上轮 P1-1/P2-1/P3-1/2/3/7 逐条处置正确、P3-4/5/6/8 按裁定零触碰；新引入 10 条 P3 记录项不阻塞——v.status 残留 CTE 内层（M0b/M1 顺手）、P3-1 竞态回归未入仓（建议补 5 行）、CTE 侧恶意 key 测试缺、白名单 re.match→fullmatch、其他标识符路径 docstring 不变式、migrate 成功路径恢复失败静默、_Renderer 跨调用拼接约束、render_expr 移除记录、tester 报告计数笔误（15→19）、test_acl_02 快照绑定遍历序；需求边界问题：无；tester R2 报告核对属实（1 处行号差 1 行、1 处计数笔误均不影响结论）；调研借鉴检查：R1 结论保持、grants 写路径校验登记 M1/M2）
- **终态校验（2026-10-23 supervised-coding）**：testVerdict=PASS + reviewVerdict=APPROVED + reviewedSha=testedSha=HEAD(839bded, develop_opencode) ✓ → status=approved，待用户确认交付

## 最新验证意见原文

- （暂无）

### Tester R1 报告原文（2026-10-23，testVerdict=PASS）

# knowledge-lattice M0a-2 验证报告（Tester round 1）

**testVerdict: PASS**

**testedSha**: `7e68936e8bc6786a5e00c8a7c89a42e23c9688a7`（开工前置校验 = HEAD ✓，分支 `develop_opencode`，工作区干净）

## 一、复跑输出摘要（验收动作 1，独立复跑）

| 模式 | 结果 |
|---|---|
| `uv run pytest` | **78 passed** in 1.50s（Python 3.12.10 / pytest 9.1.1，collected 78）——与 coder 自测一致 |
| `uv run python -O -m pytest` | **78 passed, 1 warning** in 1.67s——warning 为 `PytestConfigWarning: assertions not in test modules… (are you using python -O?)`，`-O` 模式预期（与检查点申报一致）；raise 类失败契约（连接工厂 RuntimeError/MigrationError/AclDeniedError）在 `-O` 下仍被 `pytest.raises` 真实验证 |

## 二、逐条勾验结果表（15 条 + 遗留 3 项，全部通过）

| # | 用例 | 结果 | 证据（文件:行号） |
|---|---|---|---|
| 1 | TC-ACL-01 AST 括号化与渲染等价 | ✅ | `tests/test_acl_01_ast_render.py:55-71` 节点树结构断言真实存在（`isinstance` 链：And→2×Or→NotExists/Exists→InValue，授权常量 `("CN","OS")` 落在 InValue.values）；`:74-81` 无字符串拼接（SQL 文本不含 `'CN'/'OS'/'VAT'/org:tax` 字面量，全在 params）；`:85-94` 渲染 SQL 真实 prepare+execute 且与手写等价 SQL（`:30-39`，design §5.1 示意形态）结果集 sorted 全等，可见集断言 `{"d_cn","d_multi","d_empty_region","d_os"}` |
| 2 | TC-ACL-02 统一空值模板 | ✅ | 本地 fixture 不复用矩阵（`test_acl_02_null_template.py:45-61` 只启用 region）；主断言 Plan 结构层 `:68-83`（Or[NotExists, Exists[InValue]] + `Func("json_each",(ColumnRef("c","dims_json"),Literal("$.region")))` 等值断言 + InValue.values==("CN",)）；行为断言 `:86-95`（u_cn_r 见 {d_cn_r,d_empty_r}、u_os_r 只见 {d_empty_r}）；文本快照仅渲染器附带 `:98-106` |
| 3 | TC-ACL-03 空授权集 NOT EXISTS 单条件 | ✅ | 三层齐备：**Plan 层不变式** `test_acl_03_empty_grants.py:31-34`（InValue 空集构造即抛 ValueError，match="IN"）；**维度片段级** `:37-46`（tax_type 片段渲染文本全等 `NOT EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.tax_type'))` + `" OR " not in fragment` + region 仍为 Or）；整份产物 grep 仅兜底 `:49-53`；行为 `:56-60`（u_cn 见 {d_multi, d_empty_region}） |
| 4 | TC-ACL-04 生命周期解耦 | ✅ | `test_acl_04_lifecycle.py:32-44` required/enabled 逐列 UPDATE+还原单因验证，产物逐字不变以 **Plan dataclass 相等 + (sql, params) 元组全等**断言（文本等价方式）；`:47-59` retired 规则消失（`[r.key…]==["tax_type"]` + `"'$.region'" not in sql`）+ 放宽行为断言；`:62-83` 新建 channel 零消失（NotExists 单条件 + 可见集不变） |
| 5 | TC-ACL-05 第 0 步成员校验 | ✅ | `test_acl_05_membership.py:18-24` 无 membership（sysadmin 有前置断言 0 行、检索路径不豁免——D22）；`:27-30` expires_at=昨天拒绝；`:33-36` 他组织拒绝（加强）；`:39-43` 有效正常产 Plan；`:46-54` org_admin 无授权=零放宽语义 |
| 6 | TC-ACL-06 常量约束与 FTS 路同构 | ✅ | 主断言 Plan 层 `test_acl_06_constants_routes.py:34-45`（三常量节点 And 逐字 in where.parts + org 经绑定参数）；`:48-65` 三路共用同一 Plan（base/fts/vec 的 acl_fragment 全等 + vec=base+谓词）；`:68-78` 版本条件在 JOIN（WHERE 内无 `c.version = d.active_version`）；`:81-89` FTS 路与基础路结果集真实执行相等 |
| 7 | TC-ACL-07 visible_docs 双写法等价 | ✅ | **同一授权展开**：compile_acl 单次产 Plan、两写法共享（`test_acl_07_visible_docs.py:26-30`）；`:33-38` 5 用户参数化（含 T5/T22 形态 u_cn、零授权 admin_tax）；`:54-94` T6 形态（pending v2 块不生效 P0-2.1、tombstone v1 不可见）两写法行级全等 |
| 8 | TC-EMB-02 embed_model 谓词 | ✅ | `test_emb_02_predicate.py:25-42`：Plan 层 `plan.embed_model == label` + 谓词固定节点 `Eq(ColumnRef("c","embed_model"), BindParam("current_model", label))` in where.parts + **参数绑定 config 标签**（`get_settings().embed_model_label`，渲染为 `:current_model` 占位、非字面量拼接）；`:45-52` 基础路不渲染谓词。注：用例前置 A/B 两行造数服务于 TC-EMB-07 检索行为（M1，v1.4 拆分口径），M0a Plan 层断言无需造数——一致 |
| 9 | T1 过期授权不可见 | ✅ | `test_matrix_t1_t5.py:27-38`：read_grants 断言 `{"region": (), "tax_type": ("VAT",)}`（CN 被过期过滤、隔离单因对照）+ 过期行仍在库（清理未跑，count==2）+ `_visible` 真实执行编译产物 SQL == {d_empty_region} |
| 10 | T2 续期不复活旧授权 | ✅ | `:41-58`：①编译拒绝（AclDeniedError）②DELETE 重插 ③授权集空（read_grants 双空 + grants count==0，触发器级联）+ d_cn 不可见（真实执行产物 SQL） |
| 11 | T3 停用取值收紧 | ✅ | `:61-73`：OS disabled → 授权集 [CN]（read_grants）+ d_os 不可见、d_cn/d_multi 仍可见（真实执行） |
| 12 | T4 改可选/停用不放宽 | ✅ | `:76-90`：产物逐字不变（(sql,params) 全等）+ 可见性不变，逐列单因 |
| 13 | T5 可选维度有值则过滤 | ✅ | `:93-103`：前置断言 tax_type required==0 + d_cit 不可见、d_empty_region 可见（真实执行产物 SQL） |
| 14 | T20 新建/回填/生命周期/退役 | ✅ | `test_matrix_t20_t22.py:30-64` 全四断言：①零消失 ②回填 d_cn 即收紧（d_empty_region 仍可见）③required/enabled 翻转可见性不变 ④retire 条件从 Plan 消失（`all(r.key != "channel")` + `"'$.channel'" not in sql`）+ 可见集回基线；审计半句正确延后 M2 |
| 15 | T22 无授权维度空集不出 IN () | ✅ | `:67-84`：**维度片段级**断言（片段全等 NOT EXISTS 单条件 + 无 OR）+ region 统一模板在场（`"'$.region'" in sql and " OR " in sql`）+ 全局无 IN () + 行为 {d_multi, d_empty_region} |
| 遗留① | config.py:20 注释修正 | ✅ | `git diff` 唯一行改动：`connect.py`→`connection.py`（src/knowledge_lattice/config.py:20） |
| 遗留② | 3 条回归测试 | ✅ | `tests/test_regress_m0a1_followups.py:39-54`（事务中 FK OFF→MigrationError，且 raises 后断言 foreign_keys==1 恢复——③的 try/finally 直接取证）；`:60-79`（`:memory:` journal 失败 RuntimeError + **连接关闭断言真实**——monkeypatch 追踪真实 sqlite3.connect 产物，断言已关闭连接再 execute 抛 `sqlite3.ProgrammingError`，非 mock 假断言）；`:123-132` 导入身份（pkg.migrate is ModuleType / migrate_db / connect 同一性） |
| 遗留③ | R2 P3 择要 | ✅ | WAL 重试耗尽包装 RuntimeError（`:85-117` + `connection.py` diff `raise RuntimeError(…) from exc`）；FK OFF 复查移入 try/finally（`migrate.py` diff + 首测取证）；跳过分支补断言（`test_scaf_03_migrations.py` 纯新增 2 行 `PRAGMA foreign_keys==1`）。**矛盾点核实**：journal_mode 查询纳入重试确已落地——`connection.py:43-46` 查询在 for 重试循环内（committer「查询在 try 外」指查询不落在 try/except 块内，纯读 pragma 不抛 OperationalError、语义正确）——coder 声明与代码事实一致 |

## 三、独立探针（防断言弱化交叉验证，17 项实质全过）

不复用测试断言、独立造数（12 用户/5 文档矩阵）暴力验证：**9 个可编译用户 × 双写法结果集逐字等价全过**（超出测试的 5 用户覆盖）；拒绝组精确为 {u_expired_member}（sysadmin/u_gl/u_multi@组织错配均拒绝、u_multi 双组织均通过）；InValue 空集构造即拒（异常消息含 "IN ()"）；SQL 文本零数据值字面量；向量路谓词参数绑定；required/enabled 翻转产物 sha256 逐字不变。探针唯一 FAIL（P4a）系探针自身预期写错（admin_full 持 tax_type=[VAT] 本不应见 tax_type=[CIT] 的 d_cit——与用例口径 Line 545 一致，d_cit 正是「不可见对照文档」），实现行为正确。

## 四、回归与边界复查结论（验收动作 3/4）

- **回归**：`git diff 28125a8..HEAD` 下 `test_monthly_audit_db.py`、`test_backend_contract.py`、`test_log_skeleton.py` 及 `test_scaf_01/02/04/05` **零改动**；`test_scaf_03_migrations.py` 唯一改动为跳过分支**纯新增** 2 行断言（`PRAGMA foreign_keys==1`），确为新增非弱化——与检查点申报完全一致
- **改动面**：22 files（src 8 + tests 14）与 coder 申报逐文件一致，+1728/−19
- **边界**：无 retrieve.py / FTS 查询链（`render_fts_select` 是 TC-ACL-06 必需的 ACL 产物 FTS 路形态，query 经绑定参数直传、无切分/转义管线——Match 节点 docstring 已注明转义属 M0a-3 的 store/sqlite/fts.py）/ MCP / REST / PG 渲染器（`store/postgres/` 零改动）
- **零触碰确认**：`docs/`、`prototype/` 无任何改动（--name-only 无这些路径）；检查点文件为 untracked 工作流文件，不在交付 commit 内

## 五、结论

15 条验收标准 + 3 项遗留承接全部通过，双模式复跑 78 passed 与 coder 自测一致，回归零弱化、边界零越界、独立探针交叉验证通过。

**testVerdict: PASS**（无 IMPL_BUG / TEST_BUG / CASE_BUG）

**testedSha**: `7e68936e8bc6786a5e00c8a7c89a42e23c9688a7`

### Committer R1 报告原文（2026-10-23，reviewVerdict=NEEDS_CHANGES）

# knowledge-lattice M0a-2 审查报告（Committer round 1）

**reviewVerdict: NEEDS_CHANGES**

**审查对象**：commit `7e68936e8bc6786a5e00c8a7c89a42e23c9688a7`（HEAD；`git diff 28125a8..HEAD`，22 files +1728/−19，父提交=28125a8）
**开工前置校验**：`git rev-parse HEAD` = `7e68936e8bc6786a5e00c8a7c89a42e23c9688a7` = 检查点 `testedSha` ✓；工作区干净（仅检查点文件 untracked，属预期）；`docs/`、`prototype/` 零 diff ✓。
**审查方式**：全只读。受环境命令权限限制（仅 git/gh 只读），未独立复跑 pytest；测试结论以 tester R1 的 78 passed 双模式报告 + 静态核对为准（与 M0a-1 committer 同口径）。已逐文件审阅 22 个改动文件、design §5.1/§3/§4、TEST-CASES TC-ACL-01~07/TC-EMB-02/T1~T5/T20/T22、M0a-1 检查点、research/enterprise-rag/ 相关沉淀。

---

## 一、结论

```text
reviewVerdict: NEEDS_CHANGES
```

- **P1：1 项（必修）**——ACL 渲染器的绑定参数名由维度 key 直接拼接，未做标识符白名单，存在 SQL 文本注入面，可导致 WHERE 外层常量（含 `d.org_id = :org`、版本/tombstone 条件）被注释，跨组织/旧版本数据泄露。
- **P2：1 项（应修）**——`read_grants` 的取值 JOIN 未校验 `dimension_values.dimension_id = dimensions.id`，畸形授权行（FK 允许）可把其他维度的取值挂到当前维度下；schema 尚无 grants 侧的 `trg_docdims_consistency` 等价触发器。
- **P3：若干**（CTE 的 `dim.status='active'` 二次状态读取、测试证据措辞、覆盖盲区、T6 覆盖深度、M0b 实验偏差、conftest 与 TEST-CASES 矩阵差异等，均不阻塞主验收）。
- **需求边界问题：无**（T6 覆盖深度按 P3 记录；不构成验收标准矛盾，见第三、四节）。
- **CASE_BUG 裁定**：未收到 tester 的 CASE_BUG 请求，不做裁定、不扩大范围。

---

## 二、问题清单

### P1-1（必修）｜参数名由维度 key 拼接，可注入 SQL / 破坏 ACL 常量

**文件与行号**：
- `knowledge-lattice/src/knowledge_lattice/store/sqlite/acl_render.py:163`（`InValue` 渲染：`name = f"{node.param_prefix}_{i}"`）
- 同文件 `:235`（`f"g_{rule.key}"`）、`:370`（visible_docs CTE 的同一写法）
- 数据来源：`knowledge-lattice/src/knowledge_lattice/store/sqlite/backend.py:62`（`SELECT dim.key ...`）→ `core/docs/acl.py:57-59`（原样进入 `AclDimensionRule.key`）；`store/backend.py:31-41` 无 key 校验；DDL `dimensions.key TEXT NOT NULL` 无字符集约束。

**问题**：
渲染器把维度 key 直接拼进绑定参数名（`g_<key>_<i>`），而 key 是**库内数据**（管理面/同步适配器/CSV 导入写入，M1/M2 才落写入校验），不是结构常量。包含 SQL 记号的 key 会让 SQLite 在参数名处提前截断，其余字符落入 SQL 文本。按渲染代码静态推演：

1. 先有维度 key `x`（授予取值，产生已绑定的参数 `g_x_0`）；
2. 再有维度 key `x_0) OR 1=1)) --`（授予取值，`rule.key` 进入 `InValue` 的 param_prefix）；
3. 渲染为 `je.value IN (:g_x_0) OR 1=1)) --_0)`：SQLite 解析 `:g_x_0`（已绑定，来自第 1 条规则），`--` 注释掉其后同一行的全部内容——包括 `Exists`/`_child` 的闭合、后续维度规则以及 `build_where_ast` 追加的 `c.version = d.active_version AND c.tombstone = 0 AND d.org_id = :org` 常量；
4. 查询失去组织过滤与版本/tombstone 条件，可跨组织/跨版本命中（D7 多组织隔离、P0-A 版本在用制同时失效）。

JSON path 对 `)`/空格/`--` 的容忍度决定最终是「可执行注入」还是「`json_each` 运行时报错」，但两种结果都成立同一个根因：**绑定参数名不得由数据拼接**。这也与 TC-ACL-01 的「产物由 AST 渲染、无字符串拼接」纪律相悖——现有测试只检查了**取值**不在 SQL 文本，未检查**参数名**。

**修改建议**：
1. 参数名改为渲染器自控的安全序列（按 AST 遍历顺序生成，如 `g<seq>_<i>` / 每规则索引），维度 key 只保留在 JSON path 的 `Literal`（已做 `'` 转义）与 `AclDimensionRule` 中；`InValue.param_prefix` 可保留为 trace 标签但**不直接进入 SQL**。
2. 防御纵深：`InValue.__post_init__` 校验 `param_prefix` 匹配 `^[A-Za-z_][A-Za-z0-9_]*$`（fail-closed）；`compile_acl` 或 `AclDimensionRule` 侧可再校验维度 key 的 slug 格式（与管理面约定一致）。
3. 回归测试（R2 必加）：
   - `InValue(prefix="x_0) OR 1=1)) --", values=("A",))` 构造即拒绝（若采用校验）或渲染为安全参数名；
   - 造两个维度 `x` 与 `x_0) OR 1=1)) --`（或加上第三个 `zzz` 规则），断言渲染 SQL 仍含 `d.org_id = :org`、`c.version = d.active_version`、`c.tombstone = 0`，且 `set(params)` 全为标识符；
   - 双组织数据库真实执行，断言无跨组织行。

> 严重度理由：这是 ACL 编译器的安全边界问题，且修复面很小（仅参数命名 + 测试）；不修则 M1 管理面一旦允许非 slug key（当前 DDL/服务层未约束），组织管理员或同步脏数据即可突破组织隔离。

### P2-1（应修）｜`read_grants` 未校验取值归属维度

**文件与行号**：`knowledge-lattice/src/knowledge_lattice/store/sqlite/backend.py:61-71`，重点 `:67-68`：

```sql
LEFT JOIN dimension_values v
  ON v.id = g.value_id AND v.status = 'active'
```

**问题**：
`user_dimension_grants` 的 FK 只保证 `value_id` 存在于 `dimension_values`，不保证 `v.dimension_id = g.dimension_id`；DDL 只有 `document_dimensions` 的 `trg_docdims_consistency`，**没有 grants 侧的等价触发器**。一条畸形授权行（例如 `dimension_id=region`、`value_id=tax_type` 的 VAT）会被 `read_grants` 展开成 `region=["VAT"]`；若不同维度存在同名取值编码（如两维度都有 `CN`），即可造成越权可见。设计 §5.1 的示例 SQL 同样没写这个谓词，但实现侧加一行 JOIN 条件是严格收紧、正常数据不受影响。

**修改建议**：
- JOIN 改为 `ON v.id = g.value_id AND v.dimension_id = dim.id AND v.status = 'active'`；
- 增加测试：直接 SQL 插入一条 FK 合法但 dimension/value 不匹配的授权行，断言 `read_grants` 不把它计入任何维度；
- 长期（M1/M2）在写路径做同一校验；若允许动 DDL，建议在后续迁移补 grants 一致性触发器（本任务 docs 冻结，不要求）。

### P3 记录性意见（建议，不阻塞）

1. **`acl_render.py:352`（visible_docs CTE 的 `dim.status='active'`）**：Plan 的规则集已经只含 active 维度；CTE 再读一次可变状态，若维度在「compile → execute」之间被 retired，CTE 会把所有文档视为「该维无行」而放宽，而 `json_each` 路径仍按 Plan 的授权集过滤，双写法在该竞态下不等价。建议移除该谓词（保留 `dim.key`/`dim.org_id`），或在代码注释中明确这是有意的实时退役语义。
2. **`tests/test_regress_m0a1_followups.py:39-54`**：该测试注释/tester 报告称「失败路径 finally 恢复 foreign_keys=ON 的直接取证」，但在此场景中调用方已处于事务内，`PRAGMA foreign_keys=OFF` 本来就是 no-op（FK 一直为 1），删除 finally 该测试仍会通过。真正的失败路径取证在 `tests/test_scaf_03_migrations.py:195`（M0a-1 R2）。建议改注释措辞，或补一条「FK 成功 OFF → BEGIN 后失败 → finally 恢复」的直接断言。
3. **测试覆盖盲区**：`compile_acl(..., now=None)` 的库时钟分支从未执行（所有测试显式 `NOW_TS`）；`dataset_ids=()`/`doc_ids=()` 的 `1=0` 恒假路径、`build_where_ast(vector=True)` 缺 `embed_model` 的 `ValueError`、无 active 维度/全部 retired 的 Plan、维度无取值的场景均无测试。建议在 R2 或 M1 前补 3~5 条轻量断言。
4. **`tests/test_acl_07_visible_docs.py:54-95`（T6 形态）**：当前覆盖 pending v2 块不生效 + tombstone v1 不可见（版本门控半句），未覆盖 TEST-CASES T6 的「v2 改维度切换后按 v2 判权」（viewer 应为 `u_cn_vat`，v2 region=[OS]）。与 TEST-CASES 将 T6 标注为 M1 一致，不阻塞 M0a-2；建议在检查点/M1 backlog 明确「T6 完整切换链随 M1」，避免被误读为 T6 已全验。
5. **`acl_render.py:393-403`**：CTE 的 `dataset_ids`/`doc_ids` 过滤只施加在外层，CTE 内先算全组织可见文档；对 M0b 的 1/5/10 万块 P95 实验会给 visible_docs 写法引入额外工作量，可能偏向 json_each。正确性不受影响，建议实验前把过滤下推进 CTE 或在报告中注明口径。
6. **`tests/conftest.py:4-10`**：矩阵 fixture 说明 `channel` 由 T20/TC-ACL-04 用例内创建；TEST-CASES §三标准矩阵把 `channel` 列为矩阵维度。当前做法对 T20「建维度时已有存量文档」语义正确且注释清楚，但 M1 全矩阵复用时建议提供 fixture 选项或回写用例口径。
7. **`migrate.py:128-129`**：`finally: conn.execute("PRAGMA foreign_keys = ON")` 在连接已关闭/不可执行时会抛异常覆盖原始 `MigrationError`；建议 `try/except sqlite3.Error` 包裹 finally 中的恢复动作（保留原始异常链）。属健壮性小项。
8. **`backend.py:23-44`**：`read_membership` 的 now/None 两个分支 SQL 重复；可合并为 `COALESCE` 参数或私有 helper，纯风格项。

---

## 三、需求边界问题

**无。**

- 任务原文范围与验收 15 条均可对照落实：编译器四步、统一模板、空授权集单条件、retired 不生成、required/enabled 解耦、AclPlan 方言无关、渲染收口 store 层、visible_docs 双写法、无 owner 分支均实现；未发现验收标准与实现行为矛盾。
- T6 覆盖深度已在 P3-4 记录：TEST-CASES 将 T6 本体标注 M1，M0a-2 实现的是版本门控半句，属合理 M0a 形态，不构成需求边界问题；若希望把「v2 改维度切换」提前到 M0a-2，则需由 supervised-coding 回 spec 确认，不直接作为 coder finding。

---

## 四、Tester R1 报告核对结论

**总体：报告与代码事实一致，证据抽查属实；未发现虚假/弱化证据。** 抽查结果：

| 抽查点 | 结论 |
|---|---|
| `tests/test_acl_01_ast_render.py:55-71` 节点树/`:74-81` 无字面量/`:85-94` 真实执行等价 | 属实（行号、断言均匹配） |
| `test_acl_02_null_template.py:68-83` 结构断言、`:86-95` 行为、`:98-106` 文本快照 | 属实 |
| `test_acl_03_empty_grants.py:37-46` 维度片段级断言、`:49-53` 全局无 `IN ()` | 属实 |
| `test_acl_07_visible_docs.py:54-94` T6 形态 | 实际为 `:54-95`（尾部差 1 行），内容属实；T6 完整切换未覆盖（P3-4） |
| `test_regress_m0a1_followups.py:60-79` 连接关闭真实断言、`:85-117` WAL 重试、`:123-132` 导入身份 | 属实；`:39-54` 的 finally 取证措辞过强（P3-2） |
| `connection.py:43-46` journal_mode 查询在重试循环内 | 属实；M0a-1 committer 所言「查询在 try 外」指内层 `try/except` 之外，二者不矛盾 |
| `test_scaf_03_migrations.py:241-242` 跳过分支新增 2 行断言 | 属实，纯新增非弱化 |
| 22 files（src 8 + tests 14）、78 passed（存量 34 + 新增 44）、未 push、docs/prototype 零触碰 | 与 `git diff --stat`/测试函数计数一致；pytest 结果受工具权限限制未独立复跑，采信 tester 的双模式 78 passed |

**Tester 报告未覆盖的盲区**：独立探针与全部测试均使用 `region`/`tax_type`/`channel` 等安全 key，未覆盖特殊字符/恶意维度 key——即 P1-1；也没有 grants 跨维度畸形行的探针——即 P2-1。这两个盲区不影响 tester 对既有验收项的判定，但属于本轮审查新增的必修/应修项。

---

## 五、调研借鉴检查结论（research/enterprise-rag/）

**已吸收（M0a-2 范围内）**：
- **前置过滤、查询时展开、勿 post-trim**（blog/07 §三、blog/10 §3.5）：`read_grants` 在查询时展开授权、`render_select` 把 ACL 下推为 WHERE，而非应用层裁剪；符合。
- **ACL 随索引摄入/冗余可过滤字段**（blog/03 §4.5、blog/10 §3.5）：`dims_json` 投影 + `document_dimensions` 双写，双写法同源；符合。
- **权限增量一致性是最常见事故源**（blog/07 §五）：`dims_json` 与 `document_dimensions` 由服务层同步维护（本任务 helper/测试保持双写，M1 摄取链负责），已按设计 §5.1 留下 M1 同步点；符合，但需在 M1 回归中持续断言双写一致。
- **先过滤后距离、模型标签谓词**（blog/10、§5.2）：`embed_model` 谓词 Plan 层节点、参数绑定，符合 M0a 范围。
- **过期/停用即收紧**：`read_grants` 的三重过滤与 T1/T3 行为，符合。

**未吸收但属后续里程碑（已有安排，不构成本轮 finding）**：rerank 前后 ACL 双断言（TC-ACL-08，M1）、权限增量同步/投影刷新（M1）、查询级审计（M2）、PG 渲染器（M0b）、语义实体维度 ACL（#37）。

**本轮新增的实现级缺口**：P1-1 参数名注入不属于调研沉淀的架构取舍，而是渲染器输入净化的实现问题；P2-1 与调研「ACL 表为真相源、定期校验」的纪律相关，建议按第五节 P2 处理并把 grants 侧一致性校验登记到 M1 写路径。

---

## 六、CASE_BUG 裁定

**未收到 tester 的 CASE_BUG 请求**（tester 报告明确「无 IMPL_BUG / TEST_BUG / CASE_BUG」）。本轮不做裁定、不扩大范围。

---

## 七、遗留承接核对（M0a-1 移交）

- **① `config.py:20` 注释 `connect.py`→`connection.py`**：已修，唯一行改动，属实。
- **② 3 条回归测试**：事务中 FK OFF→MigrationError ✓；`:memory:` journal 失败 RuntimeError+连接关闭（monkeypatch 追踪真实连接，断言已关闭）✓；`__init__` 导入身份 ✓。其中 FK 测试的 finally 取证措辞需修正（P3-2）。
- **③ R2 P3 择要**：WAL 重试耗尽包装 RuntimeError ✓；FK OFF 复查移入 try/finally ✓；跳过分支补 `foreign_keys==1` 断言 ✓；`journal_mode` 查询纳入重试经复核确在 `connection.py:43-46` 重试循环内，coder 声明与代码一致，与 M0a-1 committer 表述不矛盾。**遗留承接整体合格。**

---

**最终**：因 P1-1（必修）与 P2-1（应修），本轮 **NEEDS_CHANGES**。建议 R2 修复 P1-1/P2-1 + 补对应回归测试（P1 的安全 key 用例、P2 的畸形授权行用例），同时顺手处理 P3-1/P3-2；修复后重新执行 `uv run pytest` 与 `uv run python -O -m pytest`（预期 ≥80 passed），并复跑全部 15 条验收 + 遗留 3 项后提交重审。

### Tester R2 报告原文（2026-10-23，testVerdict=PASS）

# knowledge-lattice M0a-2 验证报告（Tester round 2 回归验证）

**testVerdict: PASS**

**testedSha**: `839bdedeff32c4ae85c6d553c4cb900fd4a41097`（开工前置校验 = HEAD ✓，工作区干净，R2 叠于 R1 `7e68936` 之上）

## 一、复跑输出摘要（验收动作 1）

| 模式 | 结果 |
|---|---|
| `uv run pytest` | **87 passed** in 2.06s（collected 87 = 存量 78 + 新增 9，与预期一致） |
| `uv run python -O -m pytest` | **87 passed, 1 warning**（`-O` 预期 PytestConfigWarning，与 R1 同源；raise 类失败契约仍被真实验证） |

## 二、修复项逐条勾验表

| 修复项 | 结果 | 证据（文件:行号 / 探针项） |
|---|---|---|
| **P1-1① 恶意 prefix 构造即拒** | ✅ | `acl_render.py:26-27`（`_IDENTIFIER_RE` 白名单）+ `:89-93`（`__post_init__` fail-closed）；`tests/test_r2_review_fixes.py:66-71`（5 变体 + 合法照常）；独立探针 R1i：`x_0) OR 1=1)) --`、`ds; DROP TABLE chunks;--`、`a b`、`1abc`、空串全部 ValueError 且消息含 `InValue.param_prefix`，`dim0` 照常接受 |
| **P1-1② 恶意 key 下常量齐全/参数名全标识符** | ✅ | 实现：渲染器重构为 `_Renderer` 类（`acl_render.py:162-236`），InValue 参数名 = `g{self._invalue_seq}_{i}` 自控序列（`:196-202`，与维度 key 完全无关）；`param_prefix` 降级为静态 trace 标签 `"dim"`（`:265-266`、`:404`），绝不进入 SQL；测试 `test_r2_review_fixes.py:77-101`（三常量 fragment 断言 + `_IDENTIFIER.fullmatch` 全参数名 + 剥字面量后无 `--`/`/*` + 恶意 key 仅以转义 JSON path 字面量出现 + 执行可见集不变）；独立探针 R2a-R2g 全过 |
| **P1-1③ 双组织真实执行无跨组织行** | ✅ | `test_r2_review_fixes.py:107-142`（泄露变体 `x_0) OR 1=1))) --` + 空维度文档 `d_gl_empty` 越权出口，rows=={"d_tax"}）；独立探针 R3a-R3c：独立造数 org:tax/org:gl 双组织 + 泄露变体，org:gl 的 d_gl/d_gl_empty **零出现**，org:tax 可见集不受影响，visible_docs 写法同样干净 |
| **P2-1 畸形授权行不计入** | ✅ | `backend.py:72`（`ON v.id = g.value_id AND v.dimension_id = dim.id AND v.status = 'active'`）+ docstring `:55-58` 说明；`test_r2_review_fixes.py:148-164`（region 维度挂 tax_type 的 VAT → grants["region"]==("CN","OS")、tax_type 不受影响、可见集无放宽）；独立探针 P2a-P2c 独立插畸形行复现一致 |
| **P3-1 CTE 移除二次状态读取** | ✅ | `_visible_docs_rule_ast` 移除 `dim.status='active'` 条件（diff 删行）+ 内层 JOIN 补 `v.dimension_id = dd2.dimension_id`（`:396`）+ docstring 说明竞态理由（`:378-380`）；测试：`test_r2_review_fixes.py:212-220`（全 retired 空 Plan 双写法一致）+ R1 存量 TC-ACL-07 全部保留；独立探针 **P3b 竞态态专项**：编译后维度退役，同一 Plan 两写法结果集仍逐字等价（修复前 CTE 会因 status 条件失配判全可见——修复目标场景实测成立）；P3a 正常态 8 用户 × 双写法全等、P3c/P3d 空 Plan 端点形态双写法一致 |
| **P3-2 注释措辞修正** | ✅ | `test_regress_m0a1_followups.py:7-8、:42-44、:54`：措辞改为「事务场景 OFF 本为 no-op，断言仅确认失败路径不留关闭态；finally 恢复的直接取证在 test_scaf_03 的 fk_violation 用例」——已核实 `test_scaf_03_migrations.py:168`（`test_migration_fk_violation_detected_and_rolled_back`）存在；断言本体零变化 |
| **P3-3 五条覆盖盲区** | ✅ | `test_r2_review_fixes.py:170-181`（now=None 库时钟：过期/有效/拒绝/行为四合一）、`:184-200`（dataset_ids=()/doc_ids=() → `1 = 0` 恒假非 IN () + 非空正向对照）、`:203-209`（vector=True 缺 embed_model ValueError + 基础路无谓词）、`:212-220`（全 retired 空 Plan）、`:223-237`（零取值维度 NotExists 单条件）；独立探针 P3x/P3y 抽验两条通过 |
| **P3-7 finally 恢复包 try/except** | ✅ | `migrate.py:129-134`：`finally` 内恢复动作包 `try/except sqlite3.Error: pass`，注释明确「恢复动作不得覆盖 MigrationError」——异常链保留语义正确 |

## 三、回归结论（验收动作 2）：R1 的 78 条零弱化

`git diff 7e68936..HEAD` 审阅（6 files，+361/−79）：
- **tests 仅 3 个文件变化**：`test_acl_02_null_template.py`（快照参数名 `g_region_0`→`g0_0`——P1-1 连带，SQL 形态结构与断言语义不变）、`test_regress_m0a1_followups.py`（纯注释措辞，4 个测试函数断言本体零变化）、`test_r2_review_fixes.py`（新文件 +9 条）
- **其余 15 个存量测试文件零 diff**——R1 断言零弱化、零删除；存量 78 + 新增 9 = 87 与 pytest collected 对账一致
- src 三文件的 diff 逐行审阅：`acl_render.py`（P1-1/P3-1）、`backend.py`（P2-1，仅 JOIN 一行 + docstring）、`migrate.py`（P3-7，仅 finally 块）——无超出申报范围的实现改动

## 四、P1-1 独立攻击复现结果（验收动作 3）

**攻击面真实性（对照取证）**：以 R1 旧渲染形态（参数名 `f"g_{key}_{i}"` 由 key 拼接）在恶意 key `x_0) OR 1=1)) --` 下重放——生成的 SQL 中 `--` 出现在字符串字面量之外，且注入点位于 `d.org_id = :org` 常量**之前**（探针 R2h：`legacy.find("--") < legacy.find("d.org_id = :org")` 成立）——即修复前恶意 key 可注释掉外层 org/版本/tombstone 全部常量，coder 声明的跨组织泄露攻击形态属实。

**修复有效性（29/29 探针全过）**：R2 渲染器下同一恶意 key 造数（独立 fixture，非测试自用）——三常量齐全（R2b）、参数名全为合法标识符（R2c）、org 值仅在绑定参数（R2d）、剥字面量后无注释记号（R2e）、恶意 key 仅以转义 JSON path 字面量 `'$.x_0) OR 1=1)) --'` 出现（R2f）、SQL 真实执行且可见集与正常完全一致（R2g）；双组织库 + 泄露变体恶意 key 下 org:gl 文档（含空维度越权出口）零出现（R3a-R3c）。

## 五、P3-1 等价性复验结果（验收动作 5）与 TC-ACL-06 回归

- **正常态**：8 个可编译用户 × 双写法（json_each 模板 vs visible_docs CTE）结果集逐字等价（探针 P3a）——CTE 改动未破坏 TC-ACL-07
- **竞态态（P3-1 修复的核心场景）**：region active 时编译 → 同一 Plan 执行前将 region 置 retired——两写法结果集仍逐字等价（探针 P3b）；全 retired 空 Plan 端点形态两写法一致（P3c/P3d）
- **TC-ACL-06 回归**：FTS 路共享同一 ACL 片段（结构节点全等）、版本条件仍在 JOIN 上（WHERE 内无版本条件）、FTS 路与基础路结果集相等（探针 F1-F3）

## 六、边界复查结论（验收动作 6）

- `git diff 7e68936..HEAD --name-only` = **6 files**，与 coder 申报逐文件一致
- **不做项零触碰**：P3-4（test_acl_07 T6 形态段——test_acl_07 零 diff）；P3-5（CTE 外层过滤——outer And 结构未变，仅渲染状态对象替换）；P3-6（conftest.py 零 diff）；P3-8（read_membership 分支——backend.py diff 仅 read_grants JOIN 行与 docstring）
- docs/、prototype/ 零改动（--name-only 无这些路径）；检查点文件仍为 untracked，不在交付 commit 内

## 七、结论

R2 修复 7 项（P1-1×3 / P2-1 / P3-1/2/3/7）全部落实且独立复验通过；R1 的 78 条断言零弱化；不做项（P3-4/5/6/8）零触碰；安全修复经独立攻击复现证明「攻击面真实、修复有效」。探针开发过程中的 4 次脚本自身报错（FK 参数错传、org:gl 维度漏 seed、dataset UNIQUE 冲突等）均为 Tester 探针自身 bug，与被测代码无关——其中 `trg_docdims_consistency` 拦截跨组织维度绑定一次，反向验证了 M0a-1 触发器在岗。

**testVerdict: PASS**（无 IMPL_BUG / TEST_BUG / CASE_BUG）

**testedSha**: `839bdedeff32c4ae85c6d553c4cb900fd4a41097`

### Committer R2 复审报告原文（2026-10-23，reviewVerdict=APPROVED）

# knowledge-lattice M0a-2 复审报告（Committer round 2）

**reviewVerdict: APPROVED**

**审查对象**：commit `839bdedeff32c4ae85c6d553c4cb900fd4a41097`（HEAD；`git diff 7e68936..HEAD`，6 files +361/−79，父提交=7e68936）
**开工前置校验**：`git rev-parse HEAD` = `839bdedeff32c4ae85c6d553c4cb900fd4a41097` = 检查点 `testedSha` ✓；工作区干净（仅检查点文件 untracked，属预期）。
**审查方式**：全只读，逐文件全量审阅 R2 的 6 个文件 diff + 新增 `test_r2_review_fixes.py` 全文 + R1 既有测试的连带影响；未修改任何代码/文档/检查点。受环境命令权限限制（仅 git/gh 只读），未独立复跑 pytest；87 passed 双模式与 29/29 探针采信 tester R2 报告 + 静态核对（与 R1 同口径）。

---

## 一、上轮意见处置核对表

| 上轮意见 | 处置 | 复核结论 |
|---|---|---|
| **P1-1（必修）** 参数名由维度 key 拼接，可注入并注释外层常量 | **已修** | `_Renderer` 重构：`InValue` 参数名改为渲染器自控序列 `g<seq>_<i>`（`acl_render.py:190-197`），与 key 完全无关；`InValue.param_prefix` 降级为静态 trace 标签 `"dim"`（`:265-266`、`:404`）并加标识符白名单 fail-closed（`:27-28`、`:83-93`）；三条回归测试覆盖恶意 prefix 拒绝、恶意 key 下三常量齐全/参数名全标识符/剥字面量后无注释记号、双组织真实执行无跨组织行（`test_r2_review_fixes.py:66-142`）。修复正确，P1 关闭。 |
| **P2-1（应修）** `read_grants` 未校验取值归属维度 | **已修** | `backend.py:72` 加 `AND v.dimension_id = dim.id`；LEFT JOIN 语义保持（畸形行→v NULL→维度仍以空集出现，不破坏 T22 空集语义）；回归测试 `test_r2_review_fixes.py:148-164` 用 FK 合法但 dimension/value 不匹配的行验证不计入任何维度。修复正确，P2 关闭。 |
| **P3-1** CTE `dim.status` 二次状态读取 | **已修** | `_visible_docs_rule_ast` 移除 `dim.status='active'`（`acl_render.py:382-386`），docstring 说明 compile→execute 竞态理由（`:378-380`）；内层 JOIN 补 `v.dimension_id = dd2.dimension_id`（`:396`）作为同源防御。tester P3b 竞态态探针（编译后退役同一 Plan 双写法等价）论证成立——CTE 按 key/org 继续匹配已退役维度，与 json_each 按 Plan 授权集过滤一致。修复正确，P3-1 关闭；残留 `v.status` 见下 P3 记录。 |
| **P3-2** regress 注释措辞（finally 取证过强） | **已修** | `test_regress_m0a1_followups.py` 文件头/测试 docstring 改为「事务场景 OFF 本为 no-op，仅断言失败路径不留关闭态；finally 直接取证在 test_scaf_03 的 fk_violation 用例」（`:7-8`、`:42-44`、`:54`），断言本体零变化。修复正确。 |
| **P3-3** 5 条覆盖盲区 | **已修（5/5）** | `test_r2_review_fixes.py:170-181`（now=None 库时钟）、`:184-200`（空 dataset/doc → `1 = 0` + 非空正向对照）、`:203-209`（vector=True 缺 embed_model → ValueError）、`:212-220`（全 retired 空 Plan 双写法）、`:223-237`（零取值维度 NotExists 单条件）。断言均为真实执行/结构断言，质量合格。 |
| **P3-7** migrate finally 包 sqlite3.Error | **已修** | `migrate.py:129-134` finally 恢复动作包 `try/except sqlite3.Error: pass`，注释明确不覆盖原始异常链；语义正确。 |
| **P3-4** T6 覆盖深度 | **按裁定豁免** | `test_acl_07_visible_docs.py` 零 diff，未触碰；M1 全链补。 |
| **P3-5** CTE 过滤下推 M0b | **按裁定豁免** | `render_visible_docs_select` 外层 `And` 结构未变，仅渲染状态对象替换；未越界。 |
| **P3-6** conftest channel 口径 M1 | **按裁定豁免** | `conftest.py` 零 diff。 |
| **P3-8** read_membership 分支风格 | **按裁定豁免** | `backend.py` diff 仅 `read_grants` JOIN 行 + docstring，`read_membership` 未动。 |

**处置结论：上轮 P1/P2/P3 逐条均获处置或按裁定豁免，无未处置项。**

---

## 二、新引入问题

**无 P1 / P2。** 修复未引入安全或正确性回归；以下仅为 P3 记录性意见（不阻塞）：

1. **`acl_render.py:397`（`v.status='active'` 残留在 CTE 内层 JOIN）**：P3-1 移除了 `dim.status`，但同一类「编译后可变状态二次读取」仍存在于**取值状态**上。静态语义无误（Plan 的 grants 已只含 active 值，`v.status` 对匹配结果冗余）；但在「编译时值 active → 执行前被 disabled」的窗口内，json_each 路径按 Plan 快照仍可见，CTE 路径因 `v.status='active'` 失配可能不可见。与 P3-1 同类但窗口更窄，建议 M0b/M1 顺手把该谓词从 CTE 内层移除（或明确「CTE 读当前值状态、接受窗口差异」）并补一条 value-disable 竞态测试；当前不阻塞。
2. **`tests/test_r2_review_fixes.py` 缺 P3-1 的编译→退役竞态回归**：`test_all_retired_dimensions_empty_plan` 覆盖的是「退役后重新编译」端点，P3-1 修复的核心「编译后退役、同一 Plan 执行」仅由 tester 探针 P3b 覆盖，未进仓库回归套件。建议补 5 行左右：region active 时编译 → UPDATE retired → 同一 Plan 双写法结果集仍相等。
3. **`test_r2_review_fixes.py:77-142` 未覆盖 `render_visible_docs_select` 的恶意 key**：P1-1 的三条测试均针对 `render_select`；CTE 路径同样已由渲染器自控命名（`_visible_docs_rule_ast` 使用 `"dim"` trace + 渲染器序列），tester 探针 R3 已验 visible_docs 干净，但建议补一条对 `render_visible_docs_select` 的常量齐全/参数名标识符断言，锁死同类回归。
4. **`acl_render.py:28/89` 白名单用 `re.match("^...$")`**：Python 的 `$` 允许末尾换行，`param_prefix="dim\n"` 会通过；因 prefix 仅为 trace 标签、绝不进入 SQL，无安全影响。建议改 `fullmatch` 保持校验语义精确。
5. **`acl_render.py` 其他标识符路径未做白名单**：`BindParam.name` / `ColumnRef.table|name` / `TableRef.name|alias` / `Func.name` / `InSubquery.subquery` 仍为原样 f-string 插值。当前全部由 builder 常量提供（`org`/`current_model`/`q`/`c`/`d`/`f`/`je`/`json_each`/固定 CTE 名），P1-1 的 key→SQL 标识符路径已封闭；建议在模块 docstring 明确「这些字段只允许结构常量、不得来自数据」的不变式，或在未来引入数据派生时统一加校验。
6. **`migrate.py:129-134` 成功路径的恢复失败被静默吞掉**：当前仅在连接不可执行时吞 `sqlite3.Error`，原始异常保留正确；若成功路径上 `PRAGMA foreign_keys=ON` 因非连接关闭原因失败，函数仍返回 True，FK 可能停留 OFF。建议仅在有原始异常时吞、成功路径失败则抛出/至少记 warning；属健壮性小项。
7. **`acl_render.py:233-236` 每次 `render_sql` 新建 `_Renderer`**：同 AST 两次渲染逐字一致（确定性✓）；不同 Plan 的参数名会重复（如都从 `g0_0` 起），当前 API 每次返回完整 `(sql, params)`，无跨 Plan 冲突；若未来调用方拼接两个 `render_sql` 片段，名字会碰撞。建议保持 `_Renderer` 私有并文档化「不得跨调用拼接片段」；属 API 约束记录项。
8. **`render_expr` / `_child` 公开名被移除**：R1 中无下划线的 `render_expr`/`_child` 在 R2 重构后不再导出（改为 `_Renderer.expr/child`）。当前 tests/src 无消费者（grep 零引用），不构成回归；若 M0a-3 预期直接使用 `render_expr`，请改用 `_Renderer`/`render_sql`。记录项。
9. **R2 tester 报告数字**：报告称「其余 15 个存量测试文件零 diff」，实际 `tests/*.py` 共 22 个、R2 变化 3 个（`test_acl_02`、`test_regress`、新增 `test_r2_review_fixes`）→ 19 个零 diff。不影响「R1 断言零弱化」结论，属报告计数笔误（P3 记录）。
10. **`test_acl_02` 快照 `g0_0`**：渲染器序列名与遍历顺序绑定，属渲染器附带快照（设计允许）；若未来 AST 增加前置 InValue，快照需同步更新。P3 记录。

---

## 三、需求边界问题

**无。**

- 本轮为修复轮，未改变验收口径；R2 的 6 files 全部落在 P1-1/P2-1/P3-1/2/3/7 与对应测试范围内，无超出申报的实现改动。
- 不做的 P3-4/5/6/8 均零触碰（test_acl_07、conftest、outer And、read_membership 未动），符合裁定。
- 无验收标准与实现行为矛盾；无新增规格歧义。

---

## 四、Tester R2 报告核对

**总体：报告与代码事实一致，修复证据可信；仅有一处计数笔误（P3-9）。**

抽查结果：
- `acl_render.py` `_IDENTIFIER_RE` 实际在 `:28`（tester 写 `:26-27`，差 1 行，不影响）；`__post_init__` 校验 `:89-93` 属实。
- `_Renderer` `:162-236`、InValue 命名 `:193`、`param_prefix="dim"` `:265-266`/`:404` 属实。
- `backend.py:72` JOIN 行属实；`acl_render.py:396` 内层 `v.dimension_id` 属实；`migrate.py:129-134` 属实。
- `test_r2_review_fixes.py` 行号段（`:66-71`、`:77-101`、`:107-142`、`:148-164`、`:170-181`、`:184-200`、`:203-209`、`:212-220`、`:223-237`）逐段核对属实。
- 87 passed = 存量 78 + 新增 9 ——新增测试函数计数核实为 9（P1×3 + P2×1 + P3×5），与报告一致；pytest 未独立复跑（权限限制），采信 tester 双模式结果。
- 「15 个存量测试文件零 diff」应为 19（22 个测试文件 − 3 个变化）；R1 的 78 条断言本身零弱化（`test_acl_02` 仅快照参数名 `g_region_0`→`g0_0` 的必要连带，`test_regress` 仅注释），结论不受影响。
- **P3-1 竞态论证核验**：tester P3b「编译后维度退役、同一 Plan 双写法等价」的论证成立——移除 `dim.status` 后 CTE 按 `dim.key`/`org` 继续匹配已退役维度，json_each 按 Plan 授权集过滤；两者均使用同一 Plan 快照，故等价。残留的 `v.status` 只影响「值 disabled」窗口（见 P3-1），不影响维度退役场景的结论。
- **P1-1 攻击面对照**：tester 的 legacy 渲染重放（`--` 位于 `d.org_id = :org` 之前）与代码事实一致；R2 渲染器 29/29 探针与新增测试相互印证，修复有效。
- 回归/边界：`test_acl_07`、`conftest.py`、`read_membership` 零 diff；docs/prototype 零改动；6 files 与申报一致。
- **无 CASE_BUG 请求**（testVerdict=PASS，无 IMPL_BUG/TEST_BUG/CASE_BUG），本轮不做裁定。

---

## 五、调研借鉴检查（R2 增量）

R2 未引入架构层变更，R1 的调研吸收结论保持：
- **P2-1** 与 research/enterprise-rag/blog/07「ACL 表为真相源、定期校验一致性」及 blog/10 §3.5「前置过滤、查询时展开」的纪律一致——取值归属校验正是「ACL 真相源」的读取侧防线；剩余写路径校验（grants 侧触发器/服务层断言）仍属 M1/M2，建议登记。
- **P1-1** 属实现级输入净化（ACL 编译器不得让数据进入 SQL 标识符位置），不是调研沉淀的架构取舍；修复与「引擎内过滤、无 post-trim」方向不冲突。
- 未吸收项（rerank 前 ACL 断言 M1、权限增量同步 M1、审计 M2、PG M0b、实体维度 ACL #37）仍按既有里程碑，无新增缺口。

---

## 六、结论

```text
reviewVerdict: APPROVED
```

R2 对 R1 的 P1-1/P2-1/P3-1/2/3/7 逐条落实且修复正确，P3-4/5/6/8 按裁定零触碰；未发现新 P1/P2 或需求边界问题。R1 的 78 条断言零弱化（仅快照参数名与注释的必要连带），新增 9 条测试质量合格，87 passed 双模式 + 独立攻击复现/竞态探针证据充分。**批准交付**；上述 P3 记录项（尤其 `v.status` 残留、P3-1 竞态回归入仓、P1-1 的 CTE 侧恶意 key 测试）建议在 M0b/M1 顺手或由 supervised-coding 登记移交，不影响本轮放行。
