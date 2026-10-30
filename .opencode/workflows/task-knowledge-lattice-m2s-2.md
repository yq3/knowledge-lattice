---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2s-2
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: null
testerTaskId: null
committerTaskId: null
status: implementing
round: 1
maxRounds: 3
testVerdict: null
reviewVerdict: null
testedSha: null
reviewedSha: null
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: []
endReason: null
createdAt: 2026-10-30T15:23:04+0800
updatedAt: 2026-10-30T15:25:26+0800
---

# task-knowledge-lattice-m2s-2: M2-S1 面上段——semantic_build 骨架 + 首批语义工具 + REST 管理完善

## 任务原文

**基线**：origin/develop=ad5ab2a（PR #5 合入后）；门禁基线 1000+1 双后端双模式 0 skipped（pg 臂 353）。分支 develop_opencode 先 ff 同步。

### A. semantic_build 构建骨架（design §5.10 构建流程 / §8 M2-S1 第 3 项）

1. **build 任务体**：worker 新增 semantic_build 任务类型（CLAIMABLE_TASK_TYPES 扩展——含 inline 兜底 `_loop` 认领，m2s-1 P2-2 教训）；流程=快照读取（sem_entities active + sem_relations active + 别名）→ 产出 built 快照（dict_rev 计算——**embed_model 标签必须进入 dict_rev 输入**，防换模型不重建）→ **原子切换** sem_builds 当前指针（新行 active、旧行 superseded，单事务）→ outbox 事件 semantic.build。
2. **sem_builds 表**（若 0006 迁移未含则新迁移 0007 双方言——含 dict_rev/manifest_json/status/created_at；「当前」由 status 或 is_current 语义决定，按 design §4 DDL 为准）。
3. **REST 管理端点**（semantic:admin 门控）：POST /semantic/builds（触发构建任务）、GET /semantic/builds（列表+当前）、GET /semantic/builds/{id}（manifest 明细）；m2s-1 已有 sync/sync-runs 端点补全管理语义（分页/过滤按 design §6.2）。
4. **失败语义**：构建任务 failed 不切换指针（旧 active 保留）；run/build 记录可追溯。

### B. 首批 MCP 三工具（design §6.3 语义工具组 / TEST-CASES T-S5/T-S6/T-S11、TC-SEM-05/10）

1. **get_entity**（T-S5）：按 type+key 取实体——**递归 CTE 关系展开**（design §4：关系展开 SQL 可达，不用图数据库）：给定实体返回属性+别名+关系邻接表（rel_type 分组、depth=1；多跳由 Agent 迭代调用，不做单次深展开——按 design §6.3 契约）；权限面：ACL 过滤按 docs 检索同口径（org 作用域内、restricted 实体按 sem_credentials/可见性规则——按 §6.3 工具契约与 ACL 编译口径）。
2. **search_entities**（T-S6）：alias_norm 前缀/精确匹配 + label 模糊（SQLite FTS5 / pg tsvector 双方言——若 sem 别名表无 FTS 索引则新迁移补）；返回 type/key/name/score + 分页。
3. **describe_table**（T-S11）：透传 sem_dim_lib 维度库表结构（表名/列名/维度码/值域元数据）——只读、无权限面（库本身全局只读）。
4. **MCP server 挂载**：mcp/ semantic 工具组注册（FastMCP——沿 m2-1 docs 工具组先例）；REST /mcp 单一端点不变。
5. **模板链路端到端**（TC-SEM-10）：template_center 同步 → build → get_entity(type=template, key=…) 返回 fields（via has_column 关系展开）——**模板落在哪张表哪个字段**可答；TC-SEM-05（search_entities/get_entity 结构契约）。

### C. m2s-1 移交收编（P3-r1~r5——其检查点遗留节为权威）

1. **P3-r1**：force 运行失败时 run 侧审计丢 forced 语义——失败路径 stats 补 `forced` 键（并入 G-16 收口机会：create_task 增 `audit=` 同事务参数，**若本段动 create_task 签名则一并收 G-16 触发侧两事务**；若不动则 G-16 继续 M2-S3 承接、只修 P3-r1 小面）。
2. **P3-r2**：force 覆盖 guard 的 stats 补 guard 明细（active/vanished/ratio/threshold → stats.guard）。
3. **P3-r3**：回归测试两缺口——JOIN 捕非 template 指向 + 父转 missing/悬挂父两场景固化进永久套件。
4. **P3-r4**：fail-fast API 覆盖面（畸形 JSON→400、成员+force→403 零任务行、admin+force+未配置→400 永久用例）+ register_adapter_factory docstring（工厂自担配置解析）。
5. **P3-r5**：config 校验错误前缀文案（"must be >= 0" → 范围语义）。

### D. 验收标准

- 门禁 1000+1 起零回归（新增用例全绿、0 skipped、pg 臂全实跑）；
- T-S5/T-S6/T-S11 + TC-SEM-05/TC-SEM-10 + TC-BUILD 组（若 TEST-CASES 已展开则逐条对齐；未展开面由 tester 按设计验收口径出判定表）；
- 双方言等价（迁移 0007〔若有〕+ 递归 CTE 双实现语义等价）；
- MCP 工具组挂载 + e2e（同步→构建→三工具查询闭环）；
- docs 冻结纪律：coder 禁改 docs/（指定 docs 批原样 commit 例外）；TEST-CASES 口径回写归监督侧。

### E. chore 归档批（随 R1 commit 或交付归档）

- 工作区未入库 docs：TEST-CASES v1.9.4、AGENTS.md（主线 3/5+语义 1/6）、_m2-plan.md（m2-3 ✅/m2s-2 开工）、task-knowledge-lattice-m2-3.md 终态回写——coder 原样 commit（不含 .opencode/agent/supervised-coding.md）。

## 需求确认
- [x] 用户已确认（2026-10-30 15:25「同意」——status=implementing）
- 历史遗留事项清单：（supervised-coding 扫描历史检查点汇总，默认并入本任务，见 README §4.6）
  - **m2s-1 移交 P3-r1~r5**（→ 本任务 C 组，见上）
  - m2s-1 移交 m2s-3：TC-SYNC-02「YAML 显式列出」半句 + TC-SYNC-06「值域显式映射表」（**去向 m2s-3 不变**——语义源 YAML 接入段）
  - m2-3 移交 m2-6：P3×10 + 蓝绿执行体 + members/values CRUD（**去向 m2-6 不变**——管理面补全段）
  - m2-3 移交 m2-4：无
  - G-15（关系级消失）/G-16（触发侧两事务）继续在库：G-16 本段有机会点收口（C.1），G-15 维持 M2-S3
  - m1-5 TC-UI 手动走查：待用户（与本任务无关，维持）

## 遗留事项（跨任务移交）
- [ ] 无（本段新增移交项随轮次记录登记）

## 轮次记录
- （待填）

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）
