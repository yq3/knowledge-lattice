---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2s-3
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
filesChanged:
  # R1（38 文件，commit 见轮次记录）
  - src/knowledge_lattice/core/semantic/yaml_corpus.py（✦新：YAML 仓装载/Issue 模型/rev=内容哈希/validate_corpus——TC-YAML-04 CI 规则集〔owner 逐条/samples≤3/L0 预算/短词常用词/别名冲突消歧/引用可解析/纯人工仅 concept·system/sensitivity〕+ dim_value_map.yaml 装载〔TC-SYNC-06 值域显式映射表最小实现——design §4 无专表 DDL 任务书授权〕）
  - src/knowledge_lattice/core/semantic/yaml_merge.py（✦新：合并规则表逐行——run_yaml_sync 沿 run_sync post_run 挂钩同 run 留痕〔stats.curated〕；curated_json/manual·abbr 别名/curated 关系/冲突面/规则表第 8 行清 stale）
  - src/knowledge_lattice/core/semantic/adapters/yaml_repo.py（✦新：YamlRepoAdapter——本地 checkout 目录形态〔endpoint=路径〕，纯人工实体+refers_to/related_to 走既有 sync 流程，relation_source='curated'）
  - src/knowledge_lattice/core/semantic/adapters/scenario_config.py + report_center.py（✦新：两适配器——快照/分页/refs 形态沿 m2s-1 先例）
  - src/knowledge_lattice/core/semantic/adapters/__init__.py（build_adapter 五源分发；metadata 引用面=YAML 显式 ∪ tc 推导兜底〔TC-SYNC-02 半句收口〕；close_adapter/yaml_reference_refs/load_dim_value_map；refs 接力临时适配器即建即关）
  - src/knowledge_lattice/core/semantic/sync.py（post_run 挂钩+dim_value_map 入 _entity_row〔TC-SYNC-06〕；G-15 关系级 missing〔在场键集∪hook relation_keys〕+retired 端点冲突过滤〔missing 放行落潜伏态〕；run_sync_task finally close〔C.6〕+yaml 钩子/映射装载）
  - src/knowledge_lattice/core/semantic/build.py（G-17：curated_json 入快照元组+yaml_rev=max(curated_rev) 入 dict_rev 与 build 行；G-18：was_ready 分支重激活/让位；O-1 条件 upsert 消费）
  - src/knowledge_lattice/core/semantic/constants.py（SYNC_ADAPTERS 五源+PURE_YAML_ENTITY_TYPES+YAML_DIR_TYPE_DOMAINS）
  - src/knowledge_lattice/core/semantic/lookup.py（C.5 主路径 restricted 列级过滤〔sem_restricted_column_keys〕；clamped_timeout_s 外显〔3s 钳制永久断言锚〕）
  - src/knowledge_lattice/adapters/tokenizer.py（word_tokens——符号 token 滤除，语义 FTS 索引/查询两侧共用）
  - src/knowledge_lattice/config.py（semantic_l0_token_budget=1500+非负校验）
  - src/knowledge_lattice/store/backend.py（SemanticBackend 协议扩充：sem_entity_states/sem_entities_by_ids/sem_active_source_relation_keys/sem_mark_relations_missing/sem_relations_lookup/sem_write_curated_batch/sem_replace_manual_aliases/sem_clear_stale_curated/sem_refresh_search_texts/sem_restricted_column_keys/sem_reactivate_build；sem_insert_build 返回 (id, was_ready)；advance_status 增 relations_retired_standalone）
  - src/knowledge_lattice/store/sqlite/backend.py + store/postgres/backend.py（双方言全量实现；upsert 端点 CASE 守卫〔G-15〕；级联 retired 覆盖 missing 关系；sem_builds activated_at〔切换顶置+重激活 max(now,max+1s) 严格递增防同秒并列〕；快照含 curated_json/curated_rev；search 第三层 FTS〔sqlite FTS5 外容表 delete 命令/pg tsvector GENERATED〕；expand_relations 薄适配 nodes 含 seed〔O-2 depth=0〕；别名重建/名称变更/curated 替换后 refresh）
  - src/knowledge_lattice/store/{sqlite,postgres}/migrations/semantic/0007_semantic_yaml.sql（✦新：activated_at+回填/sem_relations.source_system+回填/idx_sem_rel_srcsys/sem_search_texts+FTS〔sqlite fts5 外容/pg tsv GENERATED+GIN〕）
  - src/knowledge_lattice/api/semantic.py（C.2 读端点三件：entities 列表·{id} 详情·tables/{key}/describe〔semantic:read=成员门控〕；YAML webhook：签名=服务身份〔HMAC-SHA256 常量时间比对〕、无/错签名 401、Bearer 不替代、secret 不落日志、EVENT_SEMANTIC_YAML_MERGE 同事务〔G-16 口径〕）
  - scripts/sem_yaml_ci.py（✦新：CI 校验脚本——exit 1 逐条报〔TC-YAML-04〕）
  - tests/test_yaml_01_corpus_ci.py（✦14：corpus 装载/rev/CI 逐类拦截+脚本 exit code）
  - tests/test_yaml_02_merge.py（✦10 双臂：TC-YAML-01 正路/TC-YAML-02 规则表逐行〔含恢复后自动生效〕/T-S1 YAML 场景/G-17 definition 变更必新 rev）
  - tests/test_yaml_03_webhook.py（✦5：TC-YAML-03 三态+org 头一致性+secret 零日志）
  - tests/test_sync_06_sources.py（✦14：scenario/report 适配器/yaml 源走 sync 流程〔T-S2 guard+force/T-S4 宽限〕/TC-SYNC-02 YAML 显式∪tc 兜底/TC-SYNC-06 值域映射/C.6 close/G-15 关系级 missing+retired 端点过滤）
  - tests/test_build_04_current_ptr.py（✦5 双臂：迁移 0007 落库/水位〔6,7〕/G-18 rev 回退重激活 current 跟随/O-1 条件 upsert 无 flap/并发单 ready 事件）
  - tests/test_sem_rest_read.py（✦6：C.2 读端点矩阵〔成员 200·非成员 403·restricted 404·参数 400·未登记表 403〕）
  - tests/test_sem_fts_search.py（✦9：C.3 FTS 层双臂〔名称/别名命中·refresh·specials 零误配·三层序·score float 序列化·restricted 排除〕+C.5 主路径 restricted 列过滤+describe 3s 钳制永久断言）
  - tests/test_build_01_rev_switch.py（+1：C.7② 构建侧 audit= 崩溃注入永久用例〔_conn 代理注入，行+事件双回滚〕；sem_insert_build 元组解包适配）
  - tests/test_sem_expand_search_backend.py（+2：C.7① P3-2 强度〔len==3 环恰 3 边+双向同层去重〕；O-2 seed depth=0 入 nodes；like_escape 适配 FTS 语义）
  - tests/test_mcp_semantic_tools.py（ranking via 'name'→'fts'——C.3 升级口径）
  - tests/test_sync_02_guard.py（T-S4 中间态：实体 missing 关系随潜伏 missing〔G-15——终态口径不变〕）
  - 迁移水位顺延：tests/test_scaf_03_migrations.py〔user_version 7+测试迁移 0008〕/test_v11_schema.py〔[2..7]〕/test_sem_01_migrations.py〔semantic [6,7]〕/test_pg_scaff.py〔同构顺延 8/9〕/test_regress_m0a1_followups.py〔探针 0008〕
  # E 组 chore 原样入库（4）: docs/TEST-CASES.md（v1.9.6）/ AGENTS.md / .opencode/workflows/_m2-plan.md / task-knowledge-lattice-m2s-2.md（不含 .opencode/agent/supervised-coding.md）
  # + 本检查点 task-knowledge-lattice-m2s-3.md（R1 终态入库）
endReason: null
createdAt: 2026-10-31T09:44:28+0800
updatedAt: 2026-10-31T21:30:00+0800
---

# task-knowledge-lattice-m2s-3: M2-S2 基础段——语义源 YAML 接入 + 挂账九项收编

## 任务原文

**基线**：origin/develop=f4d1b74（PR #6 合入后）；门禁基线 1076+1 双后端双模式 0 skipped（pg 臂 381）。分支 develop_opencode 先 ff 同步。

### A. Git YAML 仓库接入（design §5.9 YAML 覆盖层 / §8 M2-S2 第 1 项）

1. **YAML 仓库 schema**（design §5.9——开工先读正文，DDL/目录结构/字段以 design 为准）：scenario_config/report_center 两适配器的源仓库布局（definitions/cariber/别名 manual 面）；`_schema` 自描述+CI 校验脚本（TC-YAML-04 样本值 ≤3）；**yaml_merge.py 合并规则**（多仓/多文件——design §5.9 权威）。
2. **两适配器**：scenario_config、report_center——沿 m2s-1 SourceAdapter 协议（快照形态/refs 引用面）；per-org 解析 fail-closed；webhook 端点（POST 触发同步——design §6.2，semantic:admin 门控+签名/凭证明文不落日志）。
3. **YAML → 同步链**：yaml 源走既有 sync 流程（T-S2 保护/force/T-S4 宽限/白名单触发器复用）；**TC-YAML-01~04**（结构校验/CI/合并冲突——按 TEST-CASES 展开逐条对齐）。
4. **TC-SYNC-02「YAML 显式列出」半句 + TC-SYNC-06「值域显式映射表」**（v1.9.1 注记归本段）：引用面从 YAML 显式声明收窄（template_center 推导兜底保留）；值域映射表按 design §4（若无专表 DDL 则任务书授权最小实现+登记）。

### B. G-17 前置收口（dict_rev 输入扩展——与 YAML 同批，用户拍板 2026-10-30）

1. **yaml_rev 入 dict_rev**：compute_dict_rev 的 yaml_rev 参数接线（YAML 仓库 commit/内容 rev）+ curated_json 纳入快照输入（design §5.8 口径）——YAML 改 definition 必触发重建。
2. **G-18+O-1 同批**：sem_builds current 指针收口（activated_at 或独立指针——迁移 0007 双方言）+ sqlite 同 rev 竞态条件 upsert（`DO UPDATE … WHERE status != 'ready'` 或同 rev ready 直接返回 existing id）。

### C. 挂账收编（m2s-2 遗留——其检查点遗留节为权威）

1. **G-15 关系级消失**：源端删边而两端实体仍在——关系级 missing 流程（§5.8 扩展）+ upsert 前端点状态过滤（指向 retired 端点的关系不再 upsert 回 active）。
2. **REST 读端点**（v1.9.5 拍板⑤）：GET /semantic/entities/{id}（+列表）·/tables/{key}/describe——semantic:read 门控。
3. **FTS 模糊索引**（拍板②）：search_entities LIKE 骨架升级（sqlite FTS5/pg tsvector 双方言——迁移按需）。
4. **O-2 薄适配契约**：expand_relations 返回 nodes 含 seed（design §5.9 walk depth=0 口径）——M2-S3 消费方确认后落。
5. **describe_table 主路径 restricted 列级过滤**（M2-S3 权限面：表级白名单之外补列级 sensitivity——口径按 design §6.3/T-S11 落）。
6. **sync 路径 adapter.close 接线**（m2s-1 既有泄漏——build_adapter/run_sync finally close）。
7. **测试维护顺手**：P3-2 去重断言强度（环 len==3/双向同层样本）；构建侧 audit= 永久崩溃注入用例；describe 3s 钳制永久断言。

### D. 验收标准

- 门禁 1076+1 起零回归（新增全绿、0 skipped、pg 臂全实跑）；
- **T-S1**（同步不覆盖人工字段——YAML 场景验收句：curated_json/manual 别名原样、事实列更新）；TC-YAML-01~04；TC-SYNC-02/06 半句收口；
- 双方言等价（迁移 0007〔若有〕+ FTS 双方言行为等价——评分差异按 G-6 口径）；
- G-15/G-17/G-18+O-1 全收口（known-gaps 状态回写归监督侧）；O-2 契约落地；
- docs 冻结纪律：coder 禁改 docs/（指定 docs 批原样 commit 例外）；TEST-CASES 口径回写归监督侧。

### E. chore 归档批（随 R1 commit）

- 工作区未入库 docs：TEST-CASES v1.9.6、AGENTS.md（语义轨道 2/6）、_m2-plan.md（m2s-2 ✅/m2s-3 开工）、task-knowledge-lattice-m2s-2.md 终态回写——coder 原样 commit（不含 .opencode/agent/supervised-coding.md）。

## 需求确认
- [x] 用户已确认（2026-10-31 09:46「同意」——status=implementing）
- 历史遗留事项清单：（supervised-coding 扫描历史检查点汇总，默认并入本任务，见 README §4.6）
  - **m2s-2 移交挂账九项**（→ 本任务 B/C 组，见上——其检查点遗留节为权威）
  - **m2s-1 移交**：TC-SYNC-02「YAML 显式列出」半句 + TC-SYNC-06「值域显式映射表」（→ 本任务 A.4）
  - m2-3 移交 m2-6：P3×10 + 蓝绿执行体 + members/values CRUD（**去向 m2-6 不变**）
  - m2-3 移交 m2-4：无
  - G-14（pg seq rewrite 运维窗口）：登记在库（重开条件未触发——PG app 接线段）
  - m1-5 TC-UI 手动走查：待用户（与本任务无关，维持）

## 遗留事项（跨任务移交）
- [ ] 无（本段新增移交项随轮次记录登记）

## 轮次记录
- R1: coder 完成（2026-10-31）——38 文件（13 新增 + 25 修改）。A 组：YAML 仓 schema/装载/CI 规则集（yaml_corpus + scripts/sem_yaml_ci.py——TC-YAML-04 全类拦截，owner/samples 逐条报）；yaml_merge 合并规则表逐行（TC-YAML-01/02 含恢复后自动生效、YAML 删除清 curated）；scenario_config/report_center/yaml 三适配器（既有 sync 流程复用——T-S2 guard+force/T-S4 宽限/白名单触发器零另起炉灶）；webhook（签名=服务身份，TC-YAML-03）；TC-SYNC-02 半句收口（metadata 引用面=YAML 显式∪tc 兜底）；TC-SYNC-06 值域映射表最小实现（dim_value_map.yaml——无专表 DDL 授权+注记）。B 组：G-17（curated_json 入快照+yaml_rev 入 dict_rev——definition 变更必新 rev）；迁移 0007 双方言（activated_at+source_system+FTS 表）；G-18（rev 回退重激活 current 跟随——activated_at 严格递增防同秒并列）；O-1（条件 upsert `WHERE status != 'ready'`——无 flap 双 ready 事件）。C 组全收：G-15（关系级 missing→宽限→retired+retired 端点 upsert 过滤〔missing 放行落潜伏态〕）；REST 读端点三件（semantic:read）；FTS 模糊索引升级（sqlite FTS5 外容表/pg tsvector——G-6 评分差异登记）；O-2（expand_relations nodes 含 seed depth=0）；describe 主路径 restricted 列级过滤；sync 路径 adapter.close 接线；测试维护三件（P3-2 强度/audit= 崩溃注入永久/3s 钳制永久）。自测：**门禁 GATE PASS 1169+1 双模式 0 skipped（pg 臂 413=380+33；1076+1→1169+1 零回归 +93）**；TDD 红灯先行（52 failed 首败 ModuleNotFoundError yaml_corpus）。design 出入注记 6 条见输出（webhook 服务身份 vs 任务书 semantic:admin 措辞/owner 全条目必填 vs 样例缺项/yaml rev=内容哈希本地形态/每日兜底未接调度/T-S4 关系中间态随 G-15 调整/映射表无专表 DDL）。

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）
