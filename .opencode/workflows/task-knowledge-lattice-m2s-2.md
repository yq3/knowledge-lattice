---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2s-2
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e744c78c2ffem5uEVkA5f64JEx
testerTaskId: ses_e741f80b6ffepfdQv1lUxaaap1
committerTaskId: ses_e74006536ffeUiDlKWMPv8LYvJ
status: done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 573abfd13bd9d286fe56c4e4c860741591f49cf3
reviewedSha: f7b7201
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged:
  # R1（26 文件 +2795/−103，commit 3d9591e）
  - src/knowledge_lattice/core/semantic/build.py（✦新：快照→dict_rev〔embed_model 标签入输入〕→相同跳过→building→原子切换失败不切→semantic.build 全终态事件）
  - src/knowledge_lattice/core/semantic/expand.py（✦新：get_entity——key/id 二选一/方向后缀/depth≤2 fanout≤200/restricted fail-closed 404/dict_rev 锚点）
  - src/knowledge_lattice/core/semantic/lookup.py（✦新：search_entities 三层排序限额+describe_table 白名单 3s 超时 5min 缓存降级）
  - src/knowledge_lattice/core/semantic/sync.py（P3-r1 forced 键/P3-r2 guard 明细/run 成功后自动投递构建任务 §5.8）
  - src/knowledge_lattice/core/semantic/adapters/__init__.py（P3-r4 docstring）
  - src/knowledge_lattice/store/backend.py（协议：create_task audit=〔G-16〕+构建域 8 方法+读取面 7 方法）
  - src/knowledge_lattice/store/sqlite/backend.py + store/postgres/backend.py（双方言全量实现——expand BFS 等价 SQL/search 三层 UNION+ESCAPE/build upsert 切换失败）
  - src/knowledge_lattice/worker/runner.py + worker/__init__.py（CLAIMABLE+semantic_build/executor）
  - src/knowledge_lattice/app.py（inline 兜底 _loop 补 semantic_build——P2-2 教训）
  - src/knowledge_lattice/api/semantic.py（POST/GET/GET{id} /semantic/builds+sync-runs 分页过滤+两触发面 G-16 同事务）
  - src/knowledge_lattice/mcp/server.py + mcp/__init__.py（semantic 组三工具挂载+semantic:read 门控）
  - src/knowledge_lattice/config.py（semantic_describe_cache_s+P3-r5 范围前缀）
  - tests/test_build_01_rev_switch.py（✦TC-BUILD-01/03 双臂）/ test_build_02_task_rest.py（✦任务+REST+兜底+同步后自动构建）/ test_mcp_semantic_tools.py（✦TC-SEM-05/10/T-S6/T-S11/T-S7·S9 工具面）/ test_p3_followups_m2s_1.py（✦r1/r2/r4/r5）
  - tests/test_r2_m2s1_fixes.py（r3 LEFT JOIN+父 missing/悬挂父固化双臂）/ tests/test_sync_05_api_worker.py（builds 占位升级）
  # E 组 chore 原样入库（5）: docs/TEST-CASES.md（v1.9.4）/ AGENTS.md / .opencode/workflows/_m2-plan.md / task-knowledge-lattice-m2-3.md / task-knowledge-lattice-m2s-2.md
  # R2（21 文件 +1197/−102，commit 573abfd=HEAD）
  - src/knowledge_lattice/core/semantic/adapters/__init__.py（可关传输对象）/ adapters/metadata.py（describe_table+close）/ adapters/template_center.py（close）
  - src/knowledge_lattice/core/semantic/build.py（P2-2 输者路径+P3-5 audit= 同事务）/ expand.py（P3-6 非 active 404）/ lookup.py（P1-1 fetcher 入 try+传输关闭）
  - src/knowledge_lattice/mcp/server.py（P1-1 兜底 ToolError）/ store/backend.py（协议 switch/fail bool+audit=+expand_relations 薄适配注记）
  - src/knowledge_lattice/store/sqlite/backend.py + postgres/backend.py（audit= 同事务/seen_edges 去重+sensitivity 过滤/::float8/薄适配）
  - tests/test_sem_describe_default.py（✦4 双臂真实路径）/ test_sem_expand_search_backend.py（✦10 双臂）/ test_build_01_rev_switch.py（+2+failed 事件断言）/ test_mcp_semantic_tools.py（+2）/ test_p3_followups_m2s_1.py（+G-16 崩溃注入）/ test_sync_05_api_worker.py（+过滤）/ test_pg_backend.py（占位断言更新）
  # R2 docs 批原样（4）: docs/TEST-CASES.md（v1.9.5）/ docs/known-gaps.md（G-16 回写+G-17/G-18）/ .opencode/workflows/_m2-plan.md / task-knowledge-lattice-m2s-2.md
endReason: null
createdAt: 2026-10-30T15:23:04+0800
updatedAt: 2026-10-31T09:41:55+0800
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

- [ ] **交付归档 docs nit（监督侧，随检查点终态 commit）**：known-gaps G-16「重开条件」括号补「构建侧已随 R2 P3-5 收口」；G-18/O-1 补一行（sqlite flap 双 ready 事件——条件 upsert，M2-S3 收口）；_m2-plan m2s-3 挂账补 O-2（薄适配双向展开+nodes 不含 seed——M2-S3 消费方契约确认）与 describe 主路径 restricted 列级过滤（M2-S3 权限面）
- [ ] 移交 **m2s-3**（R2 Committer P3 登记+Tester O-1/O-2）：REST `/semantic/entities*`·`/tables/{key}/describe` 读端点（v1.9.5 拍板⑤）；FTS 模糊索引（LIKE 骨架升级）；G-15（关系级消失）；**G-17 前置**（yaml_rev/curated 入 dict_rev）；**G-18+O-1**（rev 回退 current 指针+sqlite flap 条件 upsert）；O-2 薄适配契约（双向展开+seed 入集确认）；describe 主路径 restricted 列级过滤；sync 路径 adapter.close 接线（维护面顺手）；TC-SYNC-02 半句+TC-SYNC-06 值域映射表（v1.9.1 注记）
- [ ] 移交 **测试维护**（不阻断，随后续段顺手）：P3-2 去重断言强度（环 len==3/双向同层样本）；构建侧 audit= 永久崩溃注入用例；describe 3s 钳制永久断言
- [ ] m2s-1 移交 P3-r1~r5 已全部清偿（R1 C 组）

## 轮次记录
- R1: coder 完成（ses_e744c78c2ffem5uEVkA5f64JEx，2026-10-30 16:12）——commit `3d9591e`（26 文件 +2795/−103，含 E 组 docs chore 批原样入库）。A 构建骨架（build.py 编排+worker 任务+inline 兜底+REST 三端点；**无 0007 迁移**——0006 已含 sem_builds 全列；**旧行保持 ready**——design status 枚举无 superseded，当前=最新 ready §5.8 懒加载）；B 三工具（expand.py get_entity depth≤2 fanout≤200 restricted 404；lookup.py search 三层排序+describe 实时透传白名单降级缓存——**design §6.3/T-S11 口径，仓内无 sem_dim_lib 表**；MCP 挂载+semantic:read 门控；TC-SEM-10 端到端）；C 全收（P3-r1 forced 键+r2 guard 明细+r3 LEFT JOIN+双场景固化+r4 fail-fast 用例+docstring+r5 前缀）；**G-16 收口**（create_task audit= 同事务——sync/build 两触发面）。自测：门禁 GATE PASS 1039+1 双模式 0 skipped（pg 臂 364=331+33；1000+1→1039+1 零回归 +39）；TDD 红灯先行（15 failed 首败 ModuleNotFoundError build 模块）。design 出入 7 条注记（无 0007/superseded→ready/透传按 design/平铺契约/§5.8 为构建正文/REST entities 读端点+TC-BUILD-02·04·05 归后续段/G-16 已收）。
- R1: tester 完成（ses_e741f80b6ffepfdQv1lUxaaap1，2026-10-30 16:45）——**testVerdict=PASS**（testedSha=3d9591e=HEAD）。独立复跑门禁 1039+1 双模式 0 skipped（pg 臂 364；+39 逐文件对账、零删除零弱化——builds 占位升级强度只升不降）；判定表全过：TC-BUILD-01/03（dict_rev 跨方言同值 83a4bd1b796f/换 embed 标签必重建/切换崩溃旧 ready 保留/并发同 rev 行零重复）、T-S5/T-S6/T-S11（环不死循环/depth·fanout 越界拒/TTL 注入过期重取/降级不进缓存/3s 钳制）、TC-SEM-05/10（三层排序/「模板落在哪张表哪个字段」depth2 可答）、P3-r1~r5 逐条、**G-16 崩溃注入双方言实证**（audit 写失败→任务行+审计零残留 rollback）；coder 7 条 design 注记逐条属实。独立脚本 v1~v6（双方言图遍历逐元素等价/竞态/分层 AST 执法/sync-runs 过滤）。**观察项**：N-1 pg sem_search score 返回 Decimal vs sqlite float（fallback=str 出参将字符串化——PG 未接线无运行时影响，报 committer 裁定）；N-2 pg 并发同 rev 竞态输者写脏 failed 审计事件（行态无损、仅审计语义矛盾，报 committer 裁定）；N-3 pg expand/search 零套件覆盖（tester 独立补验——建议 backend 参数化）；N-4 REST /semantic/entities·/tables/{key}/describe 读端点未做（design §6.2 有行、任务书 B 未列——建议监督侧登记去向）；N-5 sync-runs 过滤参数无永久用例（tester v6 补验 7/7）。报告全文见「最新验证意见原文」details 块（R1 Tester）。

- R1: committer 完成（ses_e74006536ffeUiDlKWMPv8LYvJ，2026-10-30 16:59）——**reviewVerdict=NEEDS_CHANGES**（reviewedSha 不置位保持 null；HEAD=3d9591e 不通过）。**P1×1**：P1-1 describe_table 默认透传通道不可用（MetadataAdapter 无 describe_table 方法——未注册工厂路径必 AttributeError；降级构造在 try 外——未配置/畸形不走 T-S11③ 降级；3 用例全走 fake 工厂注入=mock 自证）。**P2×3**：P2-1=N-1 pg score Decimal 漂移（裁定：修 R2——::float8 三处+类型断言）；P2-2=N-2 pg 同 rev 竞态输者脏 failed 审计事件（裁定：修 R2——sem_fail_build 返回生效+switch ineffective 同 rev 视 skipped+确定性用例）；P2-3=N-3 pg expand/search 零永久覆盖（裁定：修 R2——TEST-CASES 拍板3 硬性，新增 backend 参数化双臂用例顺带锁 P2-1）。**P3×6**：P3-1 sync-runs 过滤/G-16 崩溃注入/failed 事件永久用例补强（=N-5）；P3-2 edges 重复/悬挂（seen_edges 去重+截断后不 append）；P3-3 expand_relations 设计命名占位撞车（薄适配 sem_expand_graph）；P3-4 sem_table_columns 未滤 restricted 列；P3-5 构建终态与 outbox 非同事务（G-16 构建侧未收）；P3-6 get_entity 不校验实体 status。**边界问题 7 条上报用户**（spec_confirm）：①rev 回退时 current 指针失真（activated_at/独立指针 vs 接受登记）②B.2 LIKE 未申报偏离（FTS 归 M2-S3 vs 补迁移）③B.3 sem_dim_lib 措辞矛盾（任务书回写）④递归 CTE vs BFS 等价确认⑤N-4 REST entities/describe 端点去向⑥TC-BUILD 组段归属登记（本段 01/03，02/04/05 归 M2-S2）⑦yaml_rev/curated_json 未入 dict_rev 快照（M2-S3 前置登记）。**关键面**：构建域/三工具主体/G-16/P3-r1~r5/分层/既有零弱化均通过；N-4 裁定登记不修本段、N-5 R2 顺手。报告全文见「最新验证意见原文」details 块（R1 Committer）。

**spec_confirm 裁定**（2026-10-30 16:59 用户拍板「按建议执行」）：边界 1=(a) 登记 **G-18**（rev 回退 current 失真——M2-S3 与 G-17 同批）；边界 2=(a) LIKE 骨架确认、FTS 归 M2-S3；边界 3=任务书笔误注记（describe_table=元数据系统实时透传，以 design §6.3 为准）；边界 4=(a) BFS 等价确认登记；边界 5=N-4 REST 读端点 → m2s-3 挂账；边界 6=TC-BUILD 拆分（本段 01/03、02/04/05 维持 M2-S2）；边界 7=**G-17** 登记（M2-S3 前置）。监督侧已落笔：known-gaps **G-16 状态回写已收口**+G-17/G-18 新增；TEST-CASES **v1.9.5**（七项口径登记+M2-S2 行注记）；_m2-plan m2s-2 行 ◐ R2/m2s-3 行挂账补全。**R2 范围**：P1-1 必修+P2-1~3 必修+P3-1~6 顺手（P3-3 expand_relations 薄适配/P3-5 audit= 同事务沿 create_task 先例——若不修则登记）；N-1/N-2/N-3/N-5 已裁定修 R2。status=implementing（round=2 不清零）。

- R2: coder 完成（ses_e744c78c2ffem5uEVkA5f64JEx 续接，2026-10-30 17:27）——commit `573abfd`（21 文件 +1197/−102，docs 批 v1.9.5/G-16 回写·G-17·18 原样入库）。**P1-1 全修**（MetadataAdapter.describe_table 补齐/_default_fetcher 入 try 未配置·畸形降级 degraded/test_sem_describe_default 4 用例双臂真实路径 fake 只替传输层/可关传输对象 close 不泄漏/MCP 兜底 ToolError 500）；**P2-1** pg score ::float8 三处+isinstance(float)+json.dumps 断言；**P2-2** sem_fail_build 返回生效 bool+switch 无效同 rev 按 skipped（零 failed 事件）+确定性竞态用例（fake_current 模拟）；**P2-3** test_sem_expand_search_backend.py 双臂 10 用例（环/截断/去重/无悬挂边/ESCAPE/score 类型）；**P3×6 全收**（sync-runs 过滤+G-16 崩溃注入永久用例双臂+failed 事件断言/seen_edges 去重+悬挂边/expand_relations 薄适配删占位/sensitivity 过滤/构建终态 audit= 同事务〔G-16 构建侧收口〕/非 active 根 404）。自测：门禁 GATE PASS 1076+1 双模式 0 skipped（pg 臂 381=348+33；1039+1→1076+1 零回归 +37）；TDD 红灯（P1-1 AttributeError×3/P2-2 RuntimeError switch ineffective）。verdict 双置空待 R2 重验（R1 历史：testVerdict=PASS/testedSha=3d9591e/reviewVerdict=NEEDS_CHANGES/reviewedSha 不置位——见上）。

- R2: tester 完成（ses_e741f80b6ffepfdQv1lUxaaap1 续接，2026-10-30 17:44）——**testVerdict=PASS**（testedSha=573abfd=HEAD）。独立复跑门禁 1076+1 双模式 0 skipped（pg 臂 381=348+33；+37 实测收集数逐文件对账 pg17+sqlite20；零删除零弱化——test_pg_backend 13→13 占位更新核实为过期断言替换）。**修复项 13 项逐条全过**：P1-1 五子面（真实路径实测可达——不注册工厂真 httpx 四形态降级/传输 close is_closed/MCP 兜底不泄漏内部错误）；P2-1 float8+双臂断言+双方言复核等价；P2-2 真并发 ×3 轮双方言**零脏事件**（pg 输者 skipped 单 ready 事件——R1 N-2 消失）+确定性用例反向核真红；P2-3 双臂 10 用例进门禁常跑；P3×6 全收（G-16 构建侧崩溃注入双方言——行停 building 零终态零事件原子回滚；edges 无悬挂；薄适配双 seed 归并；sensitivity 滤；非 active 两态 404）。**R1 观察项 N-1~N-5 全闭环**（N-4 docs diff 实证合规）。独立脚本 r2v1~v3（48 项断言）。**新观察**：O-1 sqlite 同 rev 竞态 flap 双 ready 事件（at-least-once 可容纳——登记 M2-S3 审计面知悉）；O-2 expand_relations 双向展开注记（M2-S3 消费方注意 seed 父节点入向出现）。报告全文见「最新验证意见原文」details 块（R2 Tester）。

- R2: committer 完成（ses_e74006536ffeUiDlKWMPv8LYvJ 续接，2026-10-31 09:25）——**reviewVerdict=APPROVED**（reviewedSha=573abfd=testedSha=HEAD 三一致；**不要求 R3**）。P1-1 五子面/P2-1~3/P3×6 全闭环复判；R1 断言未放宽；docs 批与裁定一致。**P3 残余登记级**（开源自查清单）：①P3-2 去重断言强度（环测试补 len==3/双向同层样本）②构建侧 audit= 永久崩溃注入（现 tester 临时证）③sync 路径 adapter.close 未接线（m2s-1 既有——M2-S3/维护面）④**O-1 并入 G-18/M2-S3**（sqlite flap 双 ready 事件——条件 upsert 收口）⑤薄适配 nodes 不含 seed 本身（design §5.9 walk 含 depth=0——M2-S3 消费方确认）⑥describe 主路径 restricted 列级过滤（M2-S3 权限面）⑦G-16 重开条件括号补「构建侧已收口」⑧3s 钳制永久断言。**O-1=登记并入 G-18；O-2=注记**。**交付归档前置（监督侧）**：检查点终态入库（573abfd 内仍是 R1 值）+G-16 补句/O-1 挂账 docs nit+supervised-coding.md 排除。报告全文见「最新验证意见原文」details 块（R2 Committer）。**双通过达成（round=2 收敛）**。

**交付链**（2026-10-31 09:29 用户确认交付）：① 监督侧 docs nit 落笔（G-16 重开条件补「构建侧已收口」/G-18 补 O-1 关联/_m2-plan m2s-3 挂账补 O-2+describe 列级过滤+测试维护顺手）+ 检查点终态归档 docs-only commit（reviewedSha 按 m2-3 先例更新为归档 HEAD、testedSha 保持 573abfd）→ ② Coder push+PR → ③ Committer 留痕 → ④ manifest → ⑤ 待用户合入。

**交付链执行**（2026-10-31 09:35 三步完毕）：① 监督侧 docs nit+归档 commit **`f7b7201`**（docs-only——reviewedSha 按先例更新、testedSha 保持 573abfd；push 6633914..f7b7201）；② **PR #6**（base=develop，3 commits，OPEN）；③ Committer 评审留痕 **PRR_kwDOVZ9dhM8AAAABVPYBbg**（2026-10-31T01:32:50Z，COMMENTED 载体正文首行 APPROVED）；④ evidence manifest 入 PR description（16 键——双 SHA/门禁三段基线/rounds=2/specRulings×7/handover，远端回读校验 10/10）。**待用户合入指令**（不自动合入）。

**合入完成**（2026-10-31 09:41 用户指令「合入」）：`gh pr merge 6 --merge` → **MERGED**，mergeCommit **`f4d1b74ed6185247e3d374d4aaf62ebe28a79f57`**；origin/develop ad5ab2a→f4d1b74，本地 develop_opencode 已 ff 同步。收尾：检查点 status=done；TEST-CASES v1.9.6（§六 M2-S1 行 m2s-2 段完成态——工作区随下段 chore 批）；_m2-plan/AGENTS.md 进度更新（语义轨道 2/6、下一段 m2s-3）。任务闭环（2 轮，1000+1→1076+1）。

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

<details>
<summary>R1 Tester 报告全文（2026-10-30 16:45，testVerdict=PASS）</summary>

# task-knowledge-lattice-m2s-2 R1 独立验证报告（Tester）

**testVerdict: PASS**　**testedSha: `3d9591e6b9c3a43e232ed889da4b8136ef495953`**（develop_opencode，与任务书一致）
**缺陷清单：FAIL 级 0 项；观察项/建议修复 N-1~N-5（含 2 项报 committer 裁定的实现卫生面）**

## 1. 门禁（独立复跑，未采信 coder 自测）

```
docker start lattice-pg && export LATTICE_PG_DSN=… && scripts/test_gate.sh
==== [pytest]    uv run pytest -m 'not manual' -q ====
1039 passed, 1 deselected, 2 warnings in 148.05s   OK
==== [pytest-O]  uv run python -O -m pytest -m 'not manual' -q ====
1039 passed, 1 deselected, 3 warnings in 176.62s   OK
GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
（pg 臂 364 条用例全实跑：[pg] 参数化 331 + PG 专用 33）
```

- **+39 对账**（逐文件）：build_01 ×7 双臂=14，build_02=5，mcp_semantic=8，p3_followups(2 双臂+4 单臂)=8，r2 新增 2 双臂=4 → **39 ✓**；pg 臂增量 11（331←331+7+2+2 与 33 专用自洽）✓
- **skip 核对**：0 skipped；`1 deselected` = `test_ui_01_manual_walkthrough`（manual 标记口径，非 skip）
- **回归核对（零删除零弱化）**：`git diff ad5ab2a..3d9591e` 逐文件 def 计数——5 个新文件 0→N；test_r2 7→9（+2 固化）；test_sync_05 7→7，唯一改动=`builds 占位`断言从 `{"builds": []}` 升级为 `{"builds": [], "current": None}`——**强度只升不降** ✓

## 2. 分用例判定表

| 用例 | 判定 | 证据 |
|---|---|---|
| TC-BUILD-01（dict_rev 相同跳过/变更新 rev/embed 标签入输入） | ✅ PASS | 门禁 test_build_01_rev_switch（7 用例双臂：同 rev 不产新行、manual 别名变更→新 rev、**换 embed_model 标签→必重建**、同输入跨方言同 rev〔tester v1：sqlite=pg=`83a4bd1b796f`〕） |
| TC-BUILD-03（原子切换/失败不切/事件入 outbox） | ✅ PASS | 门禁用例 + tester v2 双方言：切换崩溃→旧 ready 仍 current、failed 行+failed 事件；同 rev 重试复用行不堆尸体 |
| T-S5（白名单与组织一致性触发器） | ✅ PASS | test_sem_01_migrations（m2s-1 交付、门禁常跑）：跨组织 ABORT/白名单外 ABORT/原地改端点 ABORT 三场景固化 |
| T-S6（防环/depth≤2/fanout≤200/拒绝口径） | ✅ PASS | 门禁 test_t_s6（环 A→B→C→A 不死循环、depth=3→400、fanout 50/200 截断、fanout_limit=500→400、节点上限）+ tester v1 双方言环 A→B→A depth2 逐节点等价（`{rB}`，visited 生效） |
| T-S11（describe_table 白名单/降级/缓存） | ✅ PASS | 门禁 3 用例 + tester v3：**TTL 缩短注入 0.4s→过期重取**、TTL=0 关缓存、降级结果**不进缓存**（恢复即透传）、未登记 403、3s 常量+`min(cfg,3)` 钳制实证 |
| TC-SEM-05（结构契约/三层排序/限额） | ✅ PASS | 门禁 test_get_entity_structure_contract + test_search_entities_ranking_and_limits（alias-exact>alias-prefix>name、top_k≤50/q≤200/types 校验 400、key/id 二选一、方向后缀、entity/nodes/edges/truncated/dict_rev 齐）；拼音/向量= M2-S3（用例自注） |
| TC-SEM-10（模板链路端到端） | ✅ PASS | 门禁 test_tc_sem_10：`backed_by>`+`has_column>` depth2 可答「模板落在哪张表哪个字段」、`maps_to>` 字段落列、dict_rev 锚点==构建 rev |
| P3-r1（force 失败 stats 补 forced） | ✅ PASS | 门禁 test_p3_r1（failed run stats.forced=true + 审计事件 forced 保留） |
| P3-r2（guard 明细 {active,vanished,ratio,threshold}） | ✅ PASS | 门禁 test_p3_r2（30% 收缩 force 放行明细 10/3/0.3/阈值 + 非 force aborted_guard 不回归） |
| P3-r3（LEFT JOIN 捕错指 + 父 missing/悬挂父固化） | ✅ PASS | test_r2 内 LEFT JOIN 断言（`t.id IS NULL OR t.type!='template' OR key 不匹配`——真捕错指，非 INNER JOIN 前置过滤掩盖）+ 双场景固化用例（父 missing 保指向/悬挂父 NULL→接上且 updated 诚实计数）双臂 |
| P3-r4（畸形 JSON 400/成员+force 403 零行/admin+force 未配置 400+docstring） | ✅ PASS | 门禁 test_p3_r4 三用例 + adapters/__init__ docstring（工厂自担配置解析）在场 |
| P3-r5（config 错误前缀范围语义） | ✅ PASS | 门禁 test_p3_r5（`out of allowed range` 在场、`must be >= 0` 零残留、字段定位保留） |
| **G-16（触发侧两事务收口）** | ✅ PASS | ①实现：`create_task(audit=)` sqlite BEGIN IMMEDIATE / pg BEGIN 双实现同事务（源码读证）；②**崩溃注入**（tester v4 双方言）：audit_outbox 写入失败→任务行**零残留**+审计**零残留**（rollback 实证）；③两触发面（sync/build POST）audit= 均在场（源码计数 + 门禁正路断言）。known-gaps 状态回写归监督侧 |

**coder 7 条 design 出入注记逐条核实：全部属实**——①无 0007：sqlite/pg 两份 0006 迁移均实证含 sem_builds 全列（含 `UNIQUE(org_id,dict_rev)`）；②design §4 CHECK 枚举确无 superseded（`('building','ready','failed')`），「当前=最新 ready」与 §5.8 懒加载语义一致；③describe_table 透传元数据系统=design §6.3/T-S11 口径（仓内无 sem_dim_lib——grep 0 次，任务书 B.3 该半句与正文矛盾，以正文为准正确）；④平铺 nodes/edges 契约=§6.3 output schema；⑤构建流程正文在 §5.8（L954-959）；⑥REST `/semantic/entities*` 读端点未做（任务书 B 未列——见观察 N-4）；⑦G-16 已收（上表）。

## 3. 独立证伪脚本清单（5 份，临时目录，已清理）

| 脚本 | 内容 | 结果 |
|---|---|---|
| v1_pg_sqlite_equiv | 同图灌双方言：dict_rev 跨方言相等；8 场景 expand（环×3/链×2/缺省双向/入向×2）nodes+edges+truncated **逐元素相等**；search 9 例 store 级等价（含 `%`/`_`/`\`/注入形态——ESCAPE 生效零误配）；restricted 根 404 + 邻居展开零泄漏（双方言） | ✅（详见缺陷 N-1） |
| v2_build_atomic_race | ①任务体崩溃（快照读取抛错）→任务 failed **不切指针**双方言；③切换阶段崩溃→旧 ready 保 current+failed 事件；②**并发同 rev 双 build**（sqlite 线程内双连接真并发 / pg MVCC）各 3 轮：行零重复 rev、current 稳定、每 rev 恰一 ready | ✅（详见缺陷 N-2） |
| v3（合并脚本） | describe_table TTL 注入/关闭/降级不缓存/403/3s 钳制 | ✅ 9/9 |
| v4（合并脚本） | G-16 崩溃注入双方言 + 正路同落 + 两触发面源码实证 | ✅ 9/9 |
| v5（合并脚本） | 分层执法：core/semantic 21 文件零 SQL 文本（剥注释/docstring 扫描）；auto_entities 零进 core；expand/lookup 的 backend 调用面 ⊆ 白名单（AST） | ✅ 4/4 |
| v6（合并脚本） | REST sync-runs `adapter`/`status`/`limit` 过滤 + 非法 status 400 + 成员 403 + 非成员他组织 403 + 兼任 org_admin 隔离（org:gl 空列表、org:tax 数据零串） | ✅ 7/7 |

## 4. 缺陷清单

**FAIL 级：无。**

| 编号 | 级别 | 内容 | 证据 |
|---|---|---|---|
| N-1 | 观察项（建议修，committer 裁定） | **pg 臂 `sem_search_entities` score 返回 `Decimal`（NUMERIC）vs sqlite `float`**——store 读方法双方言返回类型漂移；经 FastMCP `fallback=str` 序列化后 pg 部署下工具出参 score 将为字符串 `"1.0"`，与 design §6.3 output schema（`"score": 0.93` 数字）背离。**当前无运行时影响**（`store/factory.py` L22-26：app 恒 sqlite、PG 未接线、工具面 sqlite-only）。建议：pg SQL 常量 `::float8` 归一。tester v1 实证：`json.dumps(core 层结果)` 在 pg 臂抛 `TypeError: Object of type Decimal is not JSON serializable` | v1 脚本 search 比对输出 |
| N-2 | 观察项（建议修，committer 裁定） | **pg 并发同 rev 双 build 竞态输者路径写「脏 failed 审计事件」**：输者 upsert 复用行后 switch rowcount=0 → `build switch ineffective` → except 无条件写 `semantic.build status=failed`（build_id 指向**实际 ready 的当前构建**）；`sem_fail_build` 本身 rowcount=0 无害（行态/current 均无损）。竞态窗口窄、仅审计语义矛盾。建议：except 路径仅在 fail 真生效时写 failed 事件。sqlite 同场景结局不同（upsert 重断 building→ready flap、双 ready 事件、无脏事件）——双方言竞态结局不等价，行终态一致 | v2 干净场 dump：`ready 1 168eb2c4` + `failed 1 168eb2c4 "switch ineffective"` 并存 |
| N-3 | 观察项（登记） | **pg 方言 expand/search 零套件覆盖**：`sem_expand_graph`/`sem_search_entities` 全测试库零直接调用，唯一触达链（test_mcp_semantic_tools→create_app）sqlite-only；pg 实现与 sqlite 等价仅由本次 tester v1 独立补验。建议后续段将 store 级展开/检索用例 backend 参数化（TEST-CASES v1.3.2 拍板3 同方向） | grep + conftest 结构 |
| N-4 | 观察项（已在 coder 注记 6 申报） | design §8 M2-S1 第 4 项字面含「REST 对应端点」（§6.2 L1138-1139 `/semantic/entities/{id}`、`/tables/{key}/describe`）未做——任务书 B 未列，任务原文=验收权威，归后续段；建议监督侧在段序/TEST-CASES 登记去向 | design §6.2 vs 交付清单 |
| N-5 | 观察项（登记） | sync-runs `limit/adapter/status` 过滤参数已实现但**永久套件无用例触达**（仅 plain GET 与非法值 400）——本次 tester v6 独立补验 7/7 通过；建议补永久用例防回归 | tests/test_sync_05 grep |
| — | 已收口 | **G-16 触发侧两事务**：实现+崩溃注入双方言实证（见判定表）；known-gaps G-16「重开条件：M2-S2 开工（semantic_build 任务创建面）」条件已触发并已收——**状态回写归监督侧** | v4 |

## 5. 与 coder 自测对账

| 项 | coder 报告 | tester 独立结果 | 一致 |
|---|---|---|---|
| 门禁 | GATE PASS 1039+1 双模式 0 skipped，pg 臂 364=331+33 | 逐字一致（148s/177s 两模式） | ✅ |
| 新增 | +39 | 逐文件 14+5+8+8+4=39 ✓，pg 臂 +11 ✓ | ✅ |
| 零回归 | 基线 1000+1 零回归 | 存量清单零删除、占位升级无弱化 | ✅ |
| 无 0007 | 0006 已含 sem_builds 全列 | 两方言迁移文件读证 | ✅ |
| 旧行保持 ready | design 枚举无 superseded | §4 L621 + §5.8 L958 一致 | ✅ |
| design 出入 7 条 | 已注记 | 逐条核实属实 | ✅ |
| G-16 已收 | create_task audit= 两触发面 | 崩溃注入 rollback 双方言实证 | ✅ |

## 6. 结论

- **testVerdict: PASS**——任务书 A/B/C/D 验收标准逐项满足：门禁 1039+1 双模式零回归零 skip；构建骨架（dict_rev/embed 标签/原子切换/失败不切/inline 兜底/同步后自动投递/REST 三端点）双方言实证；三工具（get_entity/search_entities/describe_table）契约+双方言等价+防环/截断/白名单/降级/缓存全过；MCP 挂载+semantic:read 门控+TC-SEM-10/05 端到端；m2s-1 移交 r1~r5 全收；G-16 双方言崩溃注入收口。
- N-1/N-2 报 committer 裁定（建议 coder 顺手修，均不阻塞本段验收）；N-3~N-5 登记归后续段。
- testedSha=HEAD=`3d9591e6b9c3a43e232ed889da4b8136ef495953`；验证期间零 git 写操作；临时脚本//pg schema/临时目录全部清理（pg 遗留 schema=0、repo 无测试残留）。

</details>

<details>
<summary>R1 Committer 报告全文（2026-10-30 16:59，reviewVerdict=NEEDS_CHANGES）</summary>

## 0. 审查基线（本轮 diff 与上一轮意见核对）

- **审查对象**：`git diff ad5ab2a..3d9591e`（HEAD=`3d9591e`，26 文件 +2795/−103，与检查点 filesChanged 逐项一致；工作区仅 `.opencode/` 检查点/agent 文档未提交，无源码未提交改动）。
- **上一轮意见处置**：本条为首轮 Committer 审查（无上一轮 reviewedSha）；已对 **m2s-1 R2 Committer P3-r1~r5** 与 **Tester N-1~N-5** 逐条核对，并全量重读 26 文件 diff（未因「Tester 已看过」跳过构建域/三工具/G-16/测试）。
- **门禁采信**：Tester 独立复跑 1039 passed + 1 deselected（manual）/0 skipped，双模式，pg 臂 364（331 参数化 + 33 专用）；diff 内 0 skip/xfail、无删除用例，`test_sync_05` 占位断言只升不降、`test_r2` LEFT JOIN 加固——门禁计数与申报一致。
- **Tester 报告本身**证据链完整（判定表、5 份独立脚本、N-1~N-5）；但「门禁绿」不覆盖本文 P1（见下，测试以 fake 工厂绕过默认透传路径）。

## 1. 问题清单

### P1（阻塞交付）

**P1-1 `describe_table` 默认透传通道不可用，降级路径被绕过，且测试以 fake 自证**
- 位置：`src/knowledge_lattice/core/semantic/lookup.py:113`、`:175`；`src/knowledge_lattice/core/semantic/adapters/metadata.py`（全文无 `describe_table`）。
- 问题：
  1. `_default_fetcher` 默认分支 `return MetadataAdapter(config, refs=()).describe_table`，但 `MetadataAdapter` 根本没有 `describe_table` 方法（design §3 明确 metadata.py 应含「describe_table 透传客户端」，m2s-2 未补）。**未注册 `ADAPTER_FACTORIES["metadata"]` 的部署路径必抛 AttributeError**——三工具之一在真实路径不可用。
  2. `fetch = ... else _default_fetcher(settings, org_id)` 位于 `try` 之外（L113 vs L114）：metadata 未配置（`resolve_source_config` 抛 `SemanticSourceNotConfigured`）或 sources JSON 畸形时同样**不会走 degraded**，直接以内部错误出 MCP，违反 T-S11③「元数据系统不可用 → 轻量节点 + degraded=true」。
  3. 现有 3 个 describe 用例全部通过 `ADAPTER_FACTORIES["metadata"]` 注入 `FakeDescribeAdapter`（`tests/test_mcp_semantic_tools.py:147-149`），**测试测的是 fake，不是默认实现**——这正是「mock 自证」型覆盖漏洞，门禁无法发现。
- 修复期望：
  - 在 `MetadataAdapter` 实现 `describe_table(table_key)`（复用 `_transport` 的 `GET /tables/{key}`，返回 `{name, columns:[{name,type?,comment?,sample?}]}`）；
  - 把默认 fetcher 构造移入 `try`（或捕获配置异常后按 T-S11③ 降级；未配置源若定 4xx 需明确并测试）；
  - 补**不使用 ADAPTER_FACTORIES 覆盖**的永久用例：fake transport 成功/超时降级/未配置/缓存；顺带处理 `_default_transport` 每次调用新建 `httpx.Client` 未关闭的问题（describe 路径每 5min/表一次，长期泄漏）；
  - MCP 层目前只捕 `DescribeTableDenied`，默认路径异常会裸露为内部错误，同步收口。

### P2（R2 修复）

**P2-1（N-1）pg `sem_search_entities` 的 `score` 返回 Decimal，store 契约双方言类型漂移**
- 位置：`store/postgres/backend.py:2182/2186/2190`（`1.0/0.8/0.5 AS score`，PG 字面量为 NUMERIC）；对照 `store/sqlite/backend.py:2745-2753`。
- 影响：FastMCP `fallback=str` 下 pg 部署将输出 `"score": "1.0"`，违反 design §6.3 output schema（`score: 0.93` 数字）；`json.dumps` 会抛 `TypeError`。当前 app 恒 sqlite（PG 未接线）故无运行时影响，但「双方言等价」是本任务 D 的显式验收项，且 m2-3 P2-1（datetime/str）已有同类修复先例。
- 修复期望：pg SQL 统一 `CAST(1.0 AS double precision)`（或 `::float8`）三处；在 N-3 的 backend 参数化用例中断言 `isinstance(score, float)` 且 `json.dumps` 可序列化。

**P2-2（N-2）pg 同 rev 并发构建输者写「脏 failed 审计事件」**
- 位置：`core/semantic/build.py:159-176`（except 无条件写 failed 事件）；`store/postgres/backend.py:2026-2031` / `store/sqlite/backend.py:2588-2594`（`sem_fail_build` 不返回是否生效）。
- 场景：同 rev 双 build，输者 upsert 复用行后 `sem_switch_build_ready` 返回 False → `sem_fail_build` 因行已 ready 零行生效，但 `semantic.build status=failed` 事件仍写入且 build_id 指向**实际 ready 的构建**。行态无损，但审计事实自相矛盾；sqlite 同场景结局不同（flap/双 ready 事件），双方言竞态语义不等价。
- 修复期望（二选一，推荐前两项组合）：
  - `sem_fail_build` 返回 `bool`（`rowcount==1`），仅真正 building→failed 生效时写 failed 事件；
  - switch 返回 False 时先读 `sem_current_build`：若 current.dict_rev == 本 build dict_rev，按 `skipped` 返回（不抛错/不写 failed 事件/不触发任务重试）；否则才 failed；
  - 补确定性永久用例（monkeypatch switch 在行已 ready 后返回 False，断言无 failed 事件），不依赖真并发。

**P2-3（N-3）pg 方言 expand/search 零永久套件覆盖，违反 TEST-CASES 拍板3 与任务 D 双方言等价**
- 位置：`tests/test_mcp_semantic_tools.py`（MCP app 恒 sqlite）；`store/sqlite|postgres/backend.py` 的 `sem_expand_graph`/`sem_search_entities` 无 store 级参数化用例。
- 依据：TEST-CASES 口径段「语义层展开/召回类用例（T-S6/T-S8/TC-SEM-09）自 M2-S 起同样双后端参数化——#42 拍板3」；任务 D「双方言等价（递归 CTE 双实现语义等价）」。当前仅靠 Tester 临时脚本 v1/v2 证明，回归门禁不保护。
- 修复期望：新增 `tests/test_sem_expand_search_backend.py`（`backend` fixture 双臂）：
  - expand：环/双向/方向后缀、depth/fanout/node_limit 截断、restricted 根与邻居零泄漏、edges 断言（见 P3-2）；
  - search：三层排序、`%/_/\` ESCAPE、types/top_k、restricted 无命中、score 类型（接 P2-1）。
  - 该用例同时把 N-1 的修复钉在门禁里。

### P3（R2 顺手处理或登记）

- **P3-1（N-5 + 关键不变式永久用例补强）**：sync-runs `adapter/status/limit` 过滤无永久用例（tester v6 7/7 临时补验）；G-16 崩溃注入（双方言）与 TC-BUILD-03 failed 事件也只有 tester v2/v4 临时脚本，永久套件缺。建议在 R2 顺手补：`tests/test_sync_05_api_worker.py` 过滤用例、G-16 audit 写失败回滚用例（sqlite/pg 各一）、`test_build_01` 补 failed outbox 事件断言。均为 P3（实现经 Tester 实证正确，属回归保护缺口）。
- **P3-2 expand 输出 `edges` 可能重复/悬挂**：`store/sqlite/backend.py:2704-2719` / `store/postgres/backend.py:2142-2157`：双向查询时同一关系行可被 src 正向、dst 入向各 append 一次（自环必重复）；node_limit 命中后 `continue` 仍 append 边（脚本路径 `edges` 引用不在 `nodes` 的端点）。建议 `seen_edges` 去重 + 节点截断后不再 append 指向被省略节点的边（或明确契约并断言）；现有 TC-SEM-10/T-S6 用 set/仅 nodes 断言，未覆盖。
- **P3-3 `expand_relations` 设计命名方法仍是 NotImplementedError，且旧测试固化了「M2-S1 未实现」**：`store/backend.py:118`、`store/postgres/backend.py:212-213`、`tests/test_pg_backend.py:259-265`。本段新增 `sem_expand_graph` 与之平行重复；design §3 / NFR-4 明确 `expand_relations`，M2-S3 实体召回路会撞上。建议实现为 `sem_expand_graph` 的薄适配（或改名并更新设计/测试），删掉 `NotImplementedError("M2-S1")` 的过期断言。
- **P3-4 `sem_table_columns` 未过滤 restricted 列**：`store/sqlite/backend.py:2770-2779`、`store/postgres/backend.py:2206-2216` 只过滤 `c.status='active'`，未过滤 `c.sensitivity='normal'`；describe_table 降级路径会吐出 restricted 列 key/name，与 expand/search 的 fail-closed 口径不一致（T-S9 持权路径归 M2-S3，但当前无权限时也应静默）。建议补 sensitivity 条件 + restricted 列测试，或登记 M2-S3 权限面统一收口。
- **P3-5 构建终态行与 outbox 事件非同事务**：`core/semantic/build.py:148`（switch 提交）→ `:153`（写 ready 事件）；失败路径 `:163`（fail 提交）→ `:171`（写 failed 事件）。崩溃窗口会丢事件（G-16 同类问题在触发侧已收，构建侧未收）。行本身可从 sem_builds 追溯，事件缺失影响审计完整性；建议把 audit 并入 switch/fail 的 store 方法（`audit=` 同事务，沿 create_task 先例），或显式登记「构建事件允许 at-least-once 补齐」。
- **P3-6 `get_entity` 不校验实体 status**：`core/semantic/expand.py:74-76` 仅查 restricted，missing/retired 实体仍可 get_entity 并展开 active 邻接；`describe_table` 则要求 `status='active'`（`lookup.py:144`）。口径未在任务/设计钉死，建议明确（非 active 404 或保留 status 供管理面）并补用例。

## 2. 需求边界问题

**有**（以下不是 coder 单方面可修，需 supervised-coding 回 spec 确认/登记）：

1. **「当前构建指针」与 rev 回退**：任务 A.1 要求「原子切换 sem_builds 当前指针（新行 active、旧行 superseded）」，design §4 CHECK 枚举无 superseded/is_current，实现取「最新 ready by id + 旧 ready 保留」。正常单调序列成立，但 **rev 回退**（A ready id1 → B ready id2 → 源/YAML 回到 A）时 upsert 复用 id1 并置 ready，而 `sem_current_build` 仍取 id2(B)——新构建的 A 永远不会成为 current，`GET /semantic/builds` 的 current 与 get_entity 的 dict_rev 锚点失真。建议 supervision 确认语义：加 `activated_at`/独立指针（迁移 0007）或明确接受并登记；不要在未确认前让 coder 改。
2. **任务 B.2 的「label 模糊（SQLite FTS5 / pg tsvector 双方言，无索引则新迁移补）」与「分页」**：design §6.3 仅要求 label 模糊/`top_k`，无 FTS 机制与分页参数；实现用 `LIKE '%q%'` + top_k。功能近似但属未申报的任务书偏离（coder 7 条注记未列）。建议二选一：补 FTS/迁移，或经监督侧确认「LIKE 为骨架实现、FTS 归 M2-S3 模糊索引段」并登记。
3. **任务 B.3「透传 sem_dim_lib 维度库表结构」与 design §6.3/T-S11「元数据系统透传 + 白名单」矛盾**：coder 按 design 实现并已申报、Tester 已核（仓内无 sem_dim_lib）。建议 supervision 回写任务书/登记，避免下段误读。
4. **任务 B.1 / design §5.9 的「递归 CTE」与实际 BFS 等价 SQL**：实现为逐层批量查询（`sem_expand_graph`），Tester v1 已逐元素证双方言等价；但任务 D 字面写「递归 CTE 双实现语义等价」，且 BFS 与单条 CTE 在读快照一致性/查询次数上不同。建议确认「BFS 等价实现」可接受并登记，或后续段改 CTE。
5. **N-4（REST entities/describe 端点）**：design §8 M2-S1 第 4 项/§6.2 有 `GET /semantic/entities*`、`/tables/{key}/describe`，任务书 B 未列（任务书为验收权威）。建议监督侧在 `_m2-plan`/TEST-CASES 登记去向（建议随 M2-S3 越权/查询审计段，或 M2-S2 与 `semantic:read` 查询面一起验收），本段不阻塞。
6. **TC-BUILD 组段归属**：任务 D 要求「TC-BUILD 组逐条对齐」，但 TEST-CASES §六把 TC-BUILD-01~03/05 列在 **M2-S2** 行。本段交付 01/03、02/04/05 明确后移（coder 已注记，Tester 核实）——建议 supervision 登记「本段交付 01/03、02/04/05 归 M2-S2」，避免验收口径漂移。
7. **dict_rev 的 `yaml_rev`/curated 内容**：design §5.8 明确 dict_rev 含 YAML commit；`compute_dict_rev` 已留 `yaml_rev` 参数，但 `run_build` 未传，`sem_active_snapshot` 也未取 `curated_json`。当前 YAML 段未接入属可理解，但 M2-S3 接 YAML 时必须同时接 `yaml_rev`（或把 curated_json 纳入快照），否则 YAML 改 definition 不会触发重建（L0/模糊索引会陈旧）——建议登记为 M2-S3 前置。

## 3. 结论

**reviewVerdict: NEEDS_CHANGES**

- **reviewedSha：不置位（保持 null）**；本轮 HEAD=`3d9591e` 不通过。R2 修复后重新 commit、门禁重跑，再以新 HEAD 重审。
- 放行条件：**P1-1 必须修**；P2-1/P2-2/P2-3 修复或经监督侧明确裁定登记（N-1/N-2 若裁定「登记」，需在检查点写明理由并留 known-gaps/后续段指针；N-3 属 TEST-CASES 拍板3 硬性覆盖，建议修）；P3 至少完成 P3-1/P3-2/P3-3 或在检查点逐条登记去向。边界问题由 supervised-coding 回 spec/登记，不作为 coder 修复项。
- 不通过也不是否定整体质量：构建域、三工具主体、G-16、P3-r1~r5、分层与既有测试零弱化均达标；P1 是真实路径的契约缺口，P2 是契约类型/审计语义/双后端覆盖。

## 4. Tester 裁定请求（N-1~N-5）

| 编号 | 裁定 | 理由与期望 |
|---|---|---|
| **N-1** pg score Decimal | **修 R2（P2）** | store 契约双方言类型漂移 + design §6.3 output schema 数字，m2-3 P2-1 同类先例；pg SQL `::float8` 一行修复，配合 N-3 参数化用例断言 float/JSON 可序列化。 |
| **N-2** pg 竞态脏 failed 审计 | **修 R2（P2）** | 审计事件与行态自相矛盾（FR-6 合规面）；`sem_fail_build` 返回是否生效 + switch ineffective 时同 rev 视为 skipped，补确定性用例。不是纯登记项。 |
| **N-3** pg expand/search 零套件覆盖 | **修 R2（P2）** | TEST-CASES v1.3.2 拍板3 明确 T-S6 自 M2-S 起双后端参数化；任务 D 明确双方言等价。新增 store 级 `backend` 参数化用例即可（顺带锁 N-1），不能只靠 tester 临时脚本。 |
| **N-4** REST entities/describe 端点未做 | **登记（不修本段）** | 任务书 B 未列，任务原文=验收权威；但 design §8 M2-S1 第 4 项有字面要求。建议监督侧在 `_m2-plan`/TEST-CASES 登记去向（建议 M2-S3 或 M2-S2 与 `semantic:read` 查询面同段），本段不阻断。 |
| **N-5** sync-runs 过滤无永久用例 | **R2 顺手补（P3）/或登记** | tester v6 已 7/7 补验；建议随 R2 加进 `test_sync_05`（adapter/status/limit + 非法 status 400），不单独阻断。 |

**CASE_BUG：本轮未收到 tester 的 CASE_BUG 裁定请求**，无裁定。

## 5. 关键面显式结论

| 面 | 结论 |
|---|---|
| **构建域** | 通过（除 N-2 + 回退边界）：dict_rev 输入含 embed_model 标签/别名/快照内容，同 rev 跳过，building→ready/failed 单语句切换，失败旧 ready 保留，outbox ready/skipped/failed，worker+inline 兜底，REST 三端点 + sync 后自动投递；**无 0007 正确**（0006 双方言已含 sem_builds 全列/UNIQUE，design §4 枚举无 superseded）。回退指针语义见边界 1。 |
| **三工具** | get_entity/search_entities 通过（key/id 二选一、方向后缀、depth≤2/fanout≤200、防环、restricted fail-closed、三层排序/限额/ESCAPE）；describe_table 白名单/缓存/TTL/降级逻辑结构在，但**默认透传路径 P1-1 不可用**，且降级构造异常未覆盖。semantic:read 成员门控 + 组织隔离 + MCP 挂载通过。 |
| **G-16** | 实现通过：`create_task(audit=)` sqlite `BEGIN IMMEDIATE` / pg `BEGIN`，任务行+outbox 同事务；sync POST 与 build POST 两面均接入；tester v4 崩溃注入双方言实证零残留。永久回归用例缺失属 P3-1。 |
| **P3-r1~r5** | 全部收口：r1 failed stats.forced + 审计 forced；r2 force 覆盖 guard 的 stats.guard 四字段；r3 LEFT JOIN 捕非 template 指向 + 父 missing/悬挂父双场景永久用例；r4 畸形 JSON/成员+force/admin+force 未配置 + 工厂 docstring；r5 前缀改范围语义（旧文案零残留）。 |
| **分层纪律** | 通过：core/semantic 无 SQL 文本（build/expand/lookup/sync 均走 backend 协议）；`sem_*` SQL 全在 store 两方言；auto_entities 零进 core（仅 api 文档提及）。`expand_relations` 命名/占位属 P3-3，不是本次分层违规。 |
| **测试质量** | 主体较强（dict_rev 跨方言同值、换 embed 标签必重建、崩溃不切、并发同 rev 行零重复、ESCAPE/环/截断/降级/TTL 均有断言）；但 **P1 的 fake 自证**、N-3 pg 零覆盖、P3-1 关键不变式仅临时脚本，是真实缺口；未发现 skip/xfail/删除/断言放宽。 |
| **门禁** | 采信 Tester：1039+1 双模式、0 skipped、pg 364；计数与 coder 申报一致。因 P1 不在门禁覆盖内，绿门禁不能替代本次审查结论。 |
| **docs chore / filesChanged / commit** | 通过：E 组 5 文件（TEST-CASES v1.9.4、AGENTS.md、_m2-plan、m2-3/m2s-2 检查点）原样入库，**不含 supervised-coding.md**；26 文件 +2795/−103 与 `git diff --stat` 一致；commit message 符合 `[taskId] R1:` 约定；未改 requirements/design 正文。 |
| **交付就绪** | **未就绪**：P1 必须修；P2 修复或裁定登记；P3 至少登记。不置 reviewedSha、不进入交付留痕/PR review 阶段（用户尚未确认交付，且本轮为 R1 审查）。 |

</details>

<details>
<summary>R2 Tester 报告全文（2026-10-30 17:44，testVerdict=PASS）</summary>

# task-knowledge-lattice-m2s-2 R2 独立复验报告（Tester）

**testVerdict: PASS**　**testedSha: `573abfd13bd9d286fe56c4e4c860741591f49cf3`**（develop_opencode HEAD，与任务书一致）
**缺陷清单：FAIL 级 0 项；新观察项 O-1（sqlite 竞态 flap 双 ready 事件——at-least-once 语义，登记级）**

## 1. 门禁（独立复跑，未采信 coder 自测）

```
docker start lattice-pg && export LATTICE_PG_DSN=… && scripts/test_gate.sh
pg 臂用例收集数：381（[pg] 参数化 348 + PG 专用 33，> 0 ✓）
==== [pytest]    1076 passed, 1 deselected, 2 warnings in 186.08s (0:03:06)   OK
==== [pytest-O]  1076 passed, 1 deselected, 3 warnings in 160.51s (0:02:40)   OK
GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
（pg 臂 381 条用例全实跑：[pg] 参数化 348 + PG 专用 33）
```

- **+37 对账（实测收集数，非推算）**：pg 臂增量 = describe_default +4、expand_search +10、build_01 7→9 (+2)、p3_followups 2→3 (+1) = **17**（348=331+17 ✓）；sqlite 臂 = 参数化镜像 17 + 单臂 3（mcp_semantic 8→10、sync_05 7→8）= 20；**合计 37 ✓** 与 coder 申报逐位一致
- **skip 核对**：0 skipped；`1 deselected` = manual 走查用例（口径同 R1）
- **零删除零弱化（逐文件 def 对账）**：5 个存量文件全部只增不减（7→9/8→10/6→7/7→8）；`test_pg_backend.py` 13→13——**占位更新核实非弱化**：删的是 `expand_relations`「M2-S1 未实现」过期断言（该行为已被双臂新套件的实作断言替代），`callable` 六方法面与 `recall_by_entities` M2-S3 NotImplementedError 断言均保留 ✓

## 2. 修复项判定表（对照 R1 Committer 修复期望）

| 项 | 判定 | 证据 |
|---|---|---|
| **P1-1①** MetadataAdapter.describe_table 在场 | ✅ | `GET /tables/{key}` 契约实现（metadata.py R2 diff）+ **真实路径实测可达**（tester r2v1 不注册任何工厂直调默认通道成功透传） |
| **P1-1②** 未配置/畸形源降级不裸抛 | ✅ | `_default_fetcher` 构造移入 try（lookup.py R2 diff）+ 永久用例③ + **tester r2v1 真实路径四形态**：连接拒绝/不可路由超时（0.5s 钳制内降级）/未配置/畸形 JSON 全部 `degraded=true` 零裸抛；与 sync fail-fast 400 口径区分合理（查询面只读降级不阻断，永久用例 docstring 已注记） |
| **P1-1③** 4 用例真实路径非 mock 自证 | ✅ | `test_sem_describe_default.py`（双臂）：fixture 只 patch `_default_transport` 传输层，**真实链路** `resolve_source_config → MetadataAdapter.describe_table → 3s 钳制 → 缓存` 全走；`ADAPTER_FACTORIES` 零触碰（读证） |
| **P1-1④** 传输 close 成功/异常两路径 | ✅ | 永久用例①②（`close_calls==1` 双路径）+ **tester r2v1⑤ 真实 httpx.Client**：`adapter.close()` 后 `is_closed=True`；`_DefaultHttpTransport` 类持有 client 生命周期（读证） |
| **P1-1⑤** MCP 兜底 ToolError 不裸栈 | ✅ | `except Exception → ToolError 500`（mcp/server.py R2 diff）+ 永久用例断言 `"500" in str(err)` 且内部错误消息**不泄漏**（`"unexpected core bug" not in str(err)`） |
| **P2-1** pg score ::float8 三处 + 类型断言 | ✅ | pg SQL 三层 UNION 全部 `CAST(x AS double precision)`（diff 读证）+ 双臂断言 `isinstance(score, float)` + `json.dumps` 可序列化；**tester r2v3e 双方言复核**：两侧均 float、逐元素等价 |
| **P2-2** sem_fail_build bool 契约 + switch 同 rev skipped + 确定性用例 | ✅ | 永久用例：ready 行 fail→False / building→True / 已 failed 幂等→False（双臂）；switch→False 且 current 同 rev → `skipped` 返回（不抛错不触发重试、**零 failed 事件**、winner 的 ready 事件唯一）。**真红反向核**：旧代码该路径必 `raise RuntimeError` → 断言必红——用例非恒真 ✓。**tester 真并发 ×3 轮双方言**：pg 输者 `skipped`（事件仅 1 条 ready——R1 N-2 脏事件消失）；行零重复 rev、current 稳定 |
| **P2-3** 双臂 10 用例强度 | ✅ | `test_sem_expand_search_backend.py`（10 defs 全 `backend` fixture 双臂=20 收集）：环双向 depth2（3 边全集不重复）/方向过滤/链+restricted 零泄漏/fanout=3·node_limit=5 截断+**悬挂边断言**（端点 ⊆ {root}∪nodes）/edges 去重/薄适配/三层排序+types+top_k 上界/ESCAPE 字面（`%`/`_`/`t1.%` 零误配）/restricted 无命中+score 类型/sem_table_columns 滤 restricted——强度达标，pg 臂进入门禁常跑 |
| **P3-1** sync-runs 过滤 + G-16 崩溃注入 + failed 事件永久用例 | ✅ | ①`test_p3_1_sync_runs_filters_permanent`（成/败两 run → adapter 命中+空集/status 双态/limit 截断/非法 400）；②`test_p3_1_g16_crash_injection_rollback`——**真触发器注入双臂**（sqlite `RAISE ABORT` 触发器 / pg plpgsql 函数+触发器，DROP 方言各自正确），任务行+审计零残留；③test_build_01 补 failed 事件断言（build_id 指向 failed 行、error 载荷在场） |
| **P3-2** edges 去重 + 无悬挂 | ✅ | `seen_edges` 去重 + **节点截断先于边 append**（两方言 diff 同构）+ 双臂永久断言 + **tester r2v3b**：node_limit=1 → 恰 1 节点+边端点恒 ∈ {root}∪nodes（双方言）；R2 改动后环/链/缺省双向三场景双方言**逐元素等价回归** ✓ |
| **P3-3** expand_relations 薄适配 | ✅ | 两方言 `NotImplementedError` 删除 → `_expand_relations_thin`（多 seed 归并 + 跨 seed 边去重）；**tester r2v3c**：双 seed 归并 3 边去重、结果双方言逐元素相等；语义注记：rels **双向**展开（seed 的入向可扫到父节点——docstring 已声明，M2-S3 消费方按此契约）；test_pg_backend 占位更新（见 §1） |
| **P3-4** sem_table_columns 滤 restricted | ✅ | 两方言补 `c.sensitivity='normal'` + 双臂用例（t1.c3 不出现在轻量列节点——降级路径零泄漏） |
| **P3-5** 构建终态 audit= 同事务 | ✅ | `sem_switch_build_ready`/`sem_fail_build` 增 `audit=` 且**仅 rowcount==1 真生效时写**（BEGIN…COMMIT 单事务，两方言读证）+ **tester r2v3a 崩溃注入（真触发器，双方言）**：audit 写失败 → switch/fail 抛错、**行停 building 零终态、build 事件零残留**（与触发侧 G-16 同半态语义）；修复注入后重试 → ready + 事件恰一条；`audit=None` 纯切换路径正常 |
| **P3-6** 非 active 根 404 | ✅ | expand.py 根校验补 `status != 'active'` + MCP 永久用例（missing 态 404）；**tester r2v3d 补 retired 态**——missing/retired 两态双方言均 404 ✓ |

## 3. 独立脚本清单与结果（3 份，临时目录，已清理）

| 脚本 | 内容 | 结果 |
|---|---|---|
| r2v1 | P1-1 真实路径证伪：真实 httpx 传输（连接拒绝/不可路由超时/未配置/畸形 JSON → degraded 四形态）+ 真实 transport close（is_closed）+ 默认通道降级不进缓存（恢复即透传）+ close 双路径计数 | ✅ 9/9 |
| r2v2 | P2-2 真并发同 rev 双 build：双方言 ×3 轮——**事件零 failed、输者 skipped（pg）/等价收场（sqlite）、每 rev 恰一 ready 行、current 稳定** | ✅ 6/6 |
| r2v3 | P3-5 崩溃注入双方言（audit 失败→行停 building+零事件原子回滚；修复后 ready+恰一事件）+ P3-2 edges 契约/双方言等价回归 + P3-3 薄适配归并 + P3-6 两态 404 + P2-1 score float/等价 | ✅ 33/33 |

## 4. R1 观察项对账（N-1~N-5 全闭环）

| 编号 | R2 处置 | 复验结论 |
|---|---|---|
| N-1（pg score Decimal） | =P2-1 修 | ✅ 闭环（::float8 三处 + 双臂 float 断言 + tester 双方言复核） |
| N-2（pg 竞态脏 failed 事件） | =P2-2 修 | ✅ 闭环（真并发 ×3 轮双方言零脏事件 + 确定性用例真红锁定） |
| N-3（pg expand/search 零套件覆盖） | =P2-3 修 | ✅ 闭环（store 级 10 用例双臂进门禁常跑——pg 臂回归不再裸奔） |
| N-4（REST entities/describe 端点去向） | 监督侧登记 | ✅ 闭环（TEST-CASES v1.9.5 ⑤：归 m2s-3；_m2-plan 挂账——docs 批 diff 实证） |
| N-5（sync-runs 过滤无永久用例） | =P3-1 修 | ✅ 闭环（永久用例进 test_sync_05） |

另：边界 7 项 spec_confirm 裁定全部落笔（v1.9.5 版本行 + known-gaps **G-16 已收口回写/G-17/G-18 新增**——docs 批 diff 实证，coder 原样入库合规）。

## 5. 缺陷清单

**FAIL 级：无。**

| 编号 | 级别 | 内容 |
|---|---|---|
| O-1 | 登记级（非缺陷） | sqlite 同 rev 竞态 flap 路径：输者 upsert `DO UPDATE` 重断 `building` 后再切 ready → **同一 build_id 出现两条 ready 审计事件**（r2v2 sqlite race#1）。语义一致（均 ready、无矛盾）、行终态正确——at-least-once 审计口径可容纳；pg 无此形态（输者 skipped、单事件）。登记备 M2-S3 审计面知悉，不建议改 |
| O-2 | 注记 | expand_relations 薄适配按设计**双向**展开（docstring 已声明）——M2-S3 实体召回路消费时注意 seed 父节点会经入向出现；双方言行为一致，无行动项 |

## 6. 与 coder 自测对账

| 项 | coder 申报 | tester 独立结果 | 一致 |
|---|---|---|---|
| 门禁 | GATE PASS 1076+1 双模式 0 skipped，pg 381=348+33 | 逐字一致（186s/160s） | ✅ |
| 新增 | +37 | pg +17 + sqlite +20 = 37（实测收集数逐文件） | ✅ |
| TDD 红灯 | P1-1 AttributeError×3 / P2-2 switch ineffective | 与被删/被改代码路径吻合（P2-2 用例反向核真红） | ✅ |
| P1-1~P3-6 全修 | 13 项 | 逐项复验全过（含 5 项独立证伪） | ✅ |
| docs 批原样 | v1.9.5/G-16 回写/G-17·18 | diff 实证与 spec_confirm 裁定一致 | ✅ |

## 7. 结论

- **testVerdict: PASS**——Committer NEEDS_CHANGES 放行条件全部满足：P1-1 必修项五子面全修且**真实路径可达**（tester 真 httpx 证伪）；P2-1/2/3 修复且钉进门禁（pg 臂 348 参数化含全部新面）；P3-1~6 全收（含构建侧 G-16 收口与方言正确的双臂崩溃注入）；N-1~N-5 全闭环；存量零删除零弱化。
- O-1 登记级（sqlite flap 双 ready 事件，at-least-once 可容纳）；O-2 注记。
- testedSha=HEAD=`573abfd13bd9d286fe56c4e4c860741591f49cf3`；验证期间零 git 写操作；pg 遗留 schema=0、临时脚本与目录全清、repo 无测试残留。

</details>

<details>
<summary>R2 Committer 报告全文（2026-10-31 09:25，reviewVerdict=APPROVED）</summary>

## 0. 审查基线与门禁

- **审查对象**：`git diff 3d9591e..573abfd`（HEAD=`573abfd`，21 文件 +1197/−102；与检查点 filesChanged R2 段一致；工作区仅 `.opencode/` 检查点/agent 文档未提交，无源码未提交改动）。
- **上一轮基线**：逐条对照 R1 Committer 报告 P1-1/P2-1~3/P3-1~6 与 N-1~N-5；已全量重读 R2 diff（未因 Tester 报告 PASS 跳过）。
- **门禁采信**：Tester 独立复跑 1076+1（+1 manual deselected）双模式、0 skipped，pg 臂 381=348+33；+37 对账（pg +17 + sqlite +20）与新增文件逐项一致；diff 内 0 skip/xfail、无删除用例；`test_pg_backend` 13→13 为「过期 NotImplementedError 占位」替换（新双臂行为用例覆盖），不构成弱化。
- **docs 批**：`docs/TEST-CASES.md` v1.9.5 七项口径、`docs/known-gaps.md` G-16 收口+G-17/G-18、`_m2-plan` m2s-3 挂账均与 spec_confirm 裁定一致；R2 commit 不含 `.opencode/agent/supervised-coding.md`。

## 1. R1 修复项逐条闭环

### P1-1（describe_table 默认透传）—— **PASS**
| 子面 | 证据 | 结论 |
|---|---|---|
| ① MetadataAdapter.describe_table 契约 | `adapters/metadata.py` 新增 `GET /tables/{key}` 透传方法 | ✅ |
| ② 降级构造入 try | `lookup.py:113-119`：`_default_fetcher` 构造移入 try；未配置/畸形 JSON 均走 degraded | ✅ |
| ③ 真实路径非 mock 自证 | `tests/test_sem_describe_default.py` 4 用例双臂：只 patch `_default_transport` 传输层，`resolve_source_config → MetadataAdapter.describe_table → 缓存/降级` 全真实链路；`ADAPTER_FACTORIES` 零触碰 | ✅ |
| ④ 传输 close 生命周期 | `_DefaultHttpTransport.close` + `_fetch_once` finally 关闭；成功/超时两路径永久断言 `close_calls==1`；tester r2v1 真实 httpx `is_closed=True` | ✅ |
| ⑤ MCP 兜底 | `mcp/server.py` 兜底 `ToolError("500: …")`，不泄漏内部错误字符串；永久用例锁定 | ✅ |

**残余 P3（不阻断）**：3s 钳制未进永久断言（tester r2v1 临时证）；sync 适配器新增的 `close()` 在 `build_adapter`/`run_sync` 调用方未接线（describe 路径已闭环；sync 侧为 m2s-1 既有泄漏点，非本段回归）。

### P2-1（N-1 pg score Decimal）—— **PASS**
- `store/postgres/backend.py:2225-2240` 三层 UNION 全部 `CAST(x AS double precision)`；`test_sem_expand_search_backend.py` 双臂断言 `isinstance(score, float)` + `json.dumps` 可序列化；tester r2v3e 双方言复核 float 等价。

### P2-2（N-2 脏 failed 审计事件）—— **PASS**
- `sem_fail_build` 返回 bool（仅 `rowcount==1` 生效）；switch 无效且 current 同 rev → `skipped` 返回（不抛错/不写 failed）；确定性永久用例 + tester r2v2 真并发 ×3 轮双方言零脏事件（pg 输者 skipped、单 ready 事件）。
- 残余 **O-1**（sqlite flap）见下节。

### P2-3（N-3 pg expand/search 零覆盖）—— **PASS**
- 新增 `tests/test_sem_expand_search_backend.py` 10 defs × `backend` fixture 双臂＝20 收集：环/方向/链路/截断/无悬挂边/ESCAPE/types/restricted/score/薄适配/restricted 列；pg 臂进入门禁常跑，TEST-CASES 拍板3 兑现。

### P3-1~P3-6 —— **全部处置**
- **P3-1**：sync-runs 过滤永久用例（成/败双 run + adapter/status/limit/非法 400）；G-16 崩溃注入永久用例（sqlite 触发器/pg plpgsql 函数，双方言零残留）；`test_build_01` 补 failed 事件断言。✅
- **P3-2**：`seen_edges` 去重 + 节点截断先于边 append（双方言同构）；悬挂边双臂断言；tester r2v3b node_limit=1 实证。✅（测试强度见 P3 残余）
- **P3-3**：`expand_relations` 薄适配（多 seed 归并、跨 seed 边去重）；`NotImplementedError` 占位与 `test_pg_backend` 过期断言删除——旧断言被双臂行为用例替代，**非弱化**。✅
- **P3-4**：`sem_table_columns` 双方言补 `c.sensitivity='normal'` + 双臂用例（t1.c3 不泄漏）。✅
- **P3-5**：`sem_switch_build_ready`/`sem_fail_build` 增 `audit=` 同事务且仅真生效写事件；tester r2v3a 真触发器崩溃注入（audit 失败→行停 building、零事件）双方言实证。✅
- **P3-6**：非 active 根 404（missing 永久用例 + tester r2v3d retired 两态双方言）。✅

### N-1~N-5（R1 观察项）
- N-1/N-2/N-3 均随 P2-1~3 修复闭环；N-4 已按监督侧登记归 m2s-3（docs diff 实证）；N-5 随 P3-1 永久用例闭环。**无 CASE_BUG 裁定请求**。

## 2. 残余问题（仅 P3 / 登记级，开源记录）

| 级别 | 位置 | 问题 / 建议 |
|---|---|---|
| P3 | `tests/test_sem_expand_search_backend.py:116-120`、`:169-176` | **P3-2 去重断言强度不足**：环测试用集合断言（重复边不可见）；`test_expand_edges_no_duplicate` 用 t1（无双向重复来源），实际不触发 `seen_edges`。建议环测试补 `len(out["edges"]) == 3`，或造「同一关系两端都在同层 frontier」的双向样本。代码本身已由 tester r2v3b 实证正确，**不建议为该项单独开 R3**。 |
| P3 | `tests/test_build_01_rev_switch.py`（P3-5 段） | 构建侧 `audit=` 同事务目前只有 tester r2v3a 临时崩溃注入；永久套件未覆盖 switch/fail 的 audit 失败回滚（P3-1 的永久 G-16 用例只覆盖 `create_task`）。建议后续测试维护补一条，非本段阻塞。 |
| P3 | `core/semantic/adapters/__init__.py`（`build_adapter`/`run_sync`） | `TemplateCenterAdapter.close`/`MetadataAdapter.close` 已加，但 sync 路径无调用方；describe 默认路径已用 `_fetch_once` 关闭。属 m2s-1 既有连接池泄漏点，建议 M2-S3/维护面接线。 |
| P3 | `store/sqlite/backend.py:2558+` / `store/postgres/backend.py:1999+`（`sem_insert_build` upsert） | **O-1 登记**：sqlite 同 rev 竞态输者 upsert 可把已 ready 行重断 building→ready，产生同 `build_id` 双 ready 事件（pg 本次未复现）。行终态正确、事件均真实，at-least-once 审计可容纳；但存在瞬态 `current` 锚点缺失。建议 M2-S3/G-18 同批用 `DO UPDATE … WHERE status != 'ready'`（或同 rev ready 直接返回 existing id）收口。**登记，不修 R3**。 |
| P3 | `store/sqlite/backend.py`/pg `_expand_relations_thin` | 薄适配按设计双向展开，seed 父节点经入向出现（O-2）；且返回 nodes 不含 seed 本身（design §5.9 SQL 的 walk 含 depth=0 起始行）。M2-S3 消费方需确认是否要求 seed 入集；建议随 G-17/G-18 一并登记。 |
| P3 | `core/semantic/lookup.py` description 主路径 | P3-4 只修了 **降级轻量列** 的 restricted 过滤；元数据系统主透传路径仍会返回本地 restricted 列的详情。若 restricted 语义覆盖 column 实体，需在 M2-S3 权限面统一决定是否按列过滤（当前设计 T-S11 仅表级白名单）。 |
| P3 | `docs/known-gaps.md` G-16「重开条件」 | 文案仍写「构建终态事件非同事务面…P3-5——R2 顺手收口或另行登记」；R2 已实际收口构建侧 audit= 同事务，建议交付归档 docs 批补一句「构建侧已收口」。 |
| P3 | `tests/test_sem_describe_default.py` | 默认路径未永久断言 `min(cfg.timeout_s, 3)` 钳制（tester r2v1 临时证）；可补 fake transport 记录 cfg.timeout_s 的断言。 |

## 3. O-1 / O-2 处置

- **O-1（sqlite 同 rev 竞态 flap 双 ready 事件）**：**接受登记，不要求 R3**。理由：行终态正确、无脏 failed 事件、两条 ready 均对应真实 switch，at-least-once 审计口径可容纳；唯一残留是窄窗内 current 锚点缺失。建议并入 **M2-S3/G-18** 的 current 语义收口（条件 upsert），并在 known-gaps/_m2-plan 补登记一行。若后续因其他原因开 R3，可顺手改 `sem_insert_build` 条件更新 + 确定性竞态用例。
- **O-2（expand_relations 双向展开把 seed 父节点经入向带回）**：**注记，无行动项**。双方言一致、docstring 已声明；M2-S3 实体召回路消费方按此契约使用；是否把 seed 本身纳入返回集，随 P3-3/M2-S3 一并确认。

## 4. 需求边界与 docs 核对

- R1 上报的 7 条边界已按 **spec_confirm** 全部落笔：①rev 回退→G-18；②LIKE 骨架/FTS 归 M2-S3；③describe_table 任务书笔误注记；④BFS 等价确认；⑤REST entities/describe→m2s-3 挂账；⑥TC-BUILD 01/03 本段、02/04/05 M2-S2；⑦yaml_rev/curated→G-17。`TEST-CASES` v1.9.5、`known-gaps` G-17/G-18、`_m2-plan` m2s-3 挂账与上述一致。**无新增边界问题**。
- docs 批唯一 nit：`known-gaps` G-16「重开条件」括号仍按 R1 时点写「构建侧 P3-5 待收口/登记」，R2 已收口——属交付归档 docs 补句，不影响代码放行。

## 5. 关键面显式结论

| 面 | 结论 |
|---|---|
| **P1-1 五子面** | ✅ 全闭环；真实默认路径 4 用例双臂、传输 close、MCP 500 兜底均有永久证据。 |
| **P2-1/2/3** | ✅ 全闭环；pg score float、竞态脏审计消除、pg expand/search 双臂覆盖进门禁。 |
| **P3-1~6** | ✅ 全处置；P3-2 去重测试强度/P3-5 构建侧永久崩溃注入属 P3 残余，代码行为经 Tester 独立证伪正确。 |
| **构建域** | ✅ dict_rev/embed 标签/同 rev 跳过/原子切换失败不切/inline 兜底/REST 三端点/sync 后自动构建；无 0007 正确；G-18 回退语义已登记。 |
| **三工具** | ✅ get_entity（含非 active 404）、search_entities、describe_table（真实透传+降级+缓存+close）通过；semantic:read/组织隔离/restricted fail-closed 通过。 |
| **G-16** | ✅ 触发侧 create_task audit= + **构建侧 switch/fail audit= 同事务**；永久 create_task 崩溃注入 + tester 构建侧注入均零残留。 |
| **P3-r1~r5** | ✅ 全部收口（R1 已核，R2 未回归）。 |
| **分层** | ✅ core/semantic 无 SQL；expand/search 走 backend 协议；auto_entities 未进 core。 |
| **测试质量** | ✅ 1076+1、+37、零删除零弱化；R1 既有断言未放宽；新描述默认路径/expand-search/构建事件/过滤用例均非恒真。残余 P3 测试强度见上。 |
| **docs/filesChanged/commit** | ✅ R2 21 文件 +1197/−102 与 stat 一致；docs 批 v1.9.5/G-16 回写/G-17·18/_m2-plan 与裁定一致；不含 supervised-coding.md；commit message 合规。 |

## 6. 交付就绪判定

**reviewVerdict: APPROVED**（代码审查通过；P1-1 与 P2-1~3 全修并复验，P3 仅登记/维护级，**不要求 R3**）。
**reviewedSha: `573abfd13bd9d286fe56c4e4c860741591f49cf3`**（= testedSha = HEAD，按工作区检查点）。

**交付归档前置（监督侧动作，非代码阻塞）**：
- `573abfd` 内提交的 `.opencode/workflows/task-knowledge-lattice-m2s-2.md` front matter 仍是 R1 值（`testedSha: 3d9591e`、`reviewVerdict: NEEDS_CHANGES`），**R2 Tester 报告与 `reviewedSha=573abfd` 尚在工作区未入库**。PR/交付前须把检查点终态（`testVerdict: PASS`、`testedSha: 573abfd`、`reviewVerdict: APPROVED`、`reviewedSha: 573abfd` + R2 Tester 报告）提交入库，并排除 `.opencode/agent/supervised-coding.md`；否则 PR 上的 evidence manifest 会指向旧 SHA。
- 同批 docs 补：G-16「重开条件」括号注明构建侧已随 R2 P3-5 收口；O-1/M2-S3 挂账补一行（可并入 G-18）。
- 若归档采用 docs-only commit，按 m2-3 先例复核 reviewedSha/HEAD 关系（或 amend 代码 commit 之前先处理，避免出现 manifest 三 SHA 不一致）。

**最终判定**：代码交付 **APPROVED**；**strict 交付放行暂待归档前置完成**（检查点终态入库 + supervised-coding.md 排除）；归档完成后即可进入 PR/留痕与用户合入确认。

</details>
