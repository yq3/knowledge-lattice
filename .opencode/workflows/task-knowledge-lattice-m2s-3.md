---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2s-3
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e705c4fa5ffeWafnHS77csoK2s
testerTaskId: ses_e70153663ffeGS58RkjFDskaAN
committerTaskId: ses_e6ffe99deffe8USoJKteWeyvrV
status: done
round: 3
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: f6cd5b226bde0aae10e560a6d0b9f54d43b603cc
reviewedSha: 2f2244a
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged:
  # R1（38 文件+检查点+chore 4=40 entries，commit e401d37=HEAD——coder 预写，监督侧核验存档）
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
  # R2（14 文件 +1168/−58，commit 1d27e32=HEAD）
  - src/knowledge_lattice/core/semantic/yaml_corpus.py（raw 保留+l0/owner 入 payload+JSON Schema 条目校验+match_mode/全局 id/related_to src/norm 查重/.git 跳过）
  - src/knowledge_lattice/core/semantic/yaml_merge.py（P2-1 每目标产行+abbr 免拦+norm 预检消解+sensitivity 当前值）
  - src/knowledge_lattice/core/semantic/sync.py（P2-2 curated 源 sync 键剔除+entity_conflicts+N4 注释）
  - src/knowledge_lattice/core/semantic/build.py（P3-5 reactivate 返回值消费）
  - src/knowledge_lattice/store/sqlite/backend.py + postgres/backend.py（switch 严格递增+sensitivity 直写+别名 ON CONFLICT 兜底+P3-13 docstring）
  - scripts/sem_yaml_ci.py（预算 settings 接线）/ .env.example（预算+五源样例）
  - tests/test_r2_m2s3_fixes.py（✦21 用例）/ test_sync_02_guard.py（N2）/ test_sync_06_sources.py（N3）
  # R2 docs 批原样（3）: docs/known-gaps.md（G-19）/ .opencode/workflows/_m2-plan.md / task-knowledge-lattice-m2s-3.md（裁定记录——coder 未编辑）
  # R3（5 文件 +443/−22，commit f6cd5b2=HEAD）
  - src/knowledge_lattice/core/semantic/yaml_corpus.py（N6：_schema_self_check/_minimal_schema_self_check/validator_for 实例化/加载一次性自校验）
  - tests/test_r2_m2s3_fixes.py（N6×2+回退等价用例/P2-1 前序补强/误 retire 永久断言）
  # R3 docs 批原样（3）: RUNBOOK.md（0007 升级注意）/ docs/known-gaps.md（G-20+总览表 G-16 收口态·G-17~20）/ task-knowledge-lattice-m2s-3.md（只读未编辑）
  # + 本检查点 task-knowledge-lattice-m2s-3.md（R1 终态入库）
endReason: null
createdAt: 2026-10-31T09:44:28+0800
updatedAt: 2026-10-31T14:19:46+0800
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

- [ ] **交付归档 docs 补齐（监督侧，随检查点终态 commit）**：known-gaps **G-15 改已收口**（正文+总览表——m2s-3 R1 已收，终审抓到监督侧漏）；G-17/G-18 正文状态/重开条件与总览表同步为已收口；RUNBOOK 0007 note 挪 §3 迁移注意事项+注明双方言
- [ ] 移交 **m2s-4**（G-19 每日兜底调度——窗口/幂等/与 webhook 去重口径）；**回退/边界自校验健壮性**（⑦：type 数组/布尔子 schema/tuple items 回退 false positive+$schema 非字符串主路径未捕——except Exception 兜底+支持合法 schema 边角；零依赖 only）；**sensitivity 两口径**（④覆盖层删除不回退最后声明值口径化/⑤非法 sensitivity 静默归 normal 注记——m2s-4 权限面）
- [ ] 移交 **测试卫生（随后续段顺手）**：①旧 test_rule_pure_collides 仅断言 source（已被强用例覆盖——可删/强化）；②sem_replace_manual_aliases inserted 计数未计 ON CONFLICT 跳过（stats 微瑕）；③test_migration_0007 名实+test_concurrent 顺序调用非并发（R1 遗留）
- [ ] m2s-2 挂账九项已全部清偿（G-15/17/18+O-1/REST 读端点/FTS/O-2/列级过滤/close/测试维护——R1 交付）；m2s-1 移交 TC-SYNC-02/06 半句已收口（R1 A.4）

## 轮次记录
- R1: coder 完成（ses_e705c4fa5ffeWafnHS77csoK2s，2026-10-31 11:02 监督侧核验存档；commit **e401d37**）——38 文件（13 新增 + 25 修改）。A 组：YAML 仓 schema/装载/CI 规则集（yaml_corpus + scripts/sem_yaml_ci.py——TC-YAML-04 全类拦截，owner/samples 逐条报）；yaml_merge 合并规则表逐行（TC-YAML-01/02 含恢复后自动生效、YAML 删除清 curated）；scenario_config/report_center/yaml 三适配器（既有 sync 流程复用——T-S2 guard+force/T-S4 宽限/白名单触发器零另起炉灶）；webhook（签名=服务身份，TC-YAML-03）；TC-SYNC-02 半句收口（metadata 引用面=YAML 显式∪tc 兜底）；TC-SYNC-06 值域映射表最小实现（dim_value_map.yaml——无专表 DDL 授权+注记）。B 组：G-17（curated_json 入快照+yaml_rev 入 dict_rev——definition 变更必新 rev）；迁移 0007 双方言（activated_at+source_system+FTS 表）；G-18（rev 回退重激活 current 跟随——activated_at 严格递增防同秒并列）；O-1（条件 upsert `WHERE status != 'ready'`——无 flap 双 ready 事件）。C 组全收：G-15（关系级 missing→宽限→retired+retired 端点 upsert 过滤〔missing 放行落潜伏态〕）；REST 读端点三件（semantic:read）；FTS 模糊索引升级（sqlite FTS5 外容表/pg tsvector——G-6 评分差异登记）；O-2（expand_relations nodes 含 seed depth=0）；describe 主路径 restricted 列级过滤；sync 路径 adapter.close 接线；测试维护三件（P3-2 强度/audit= 崩溃注入永久/3s 钳制永久）。自测：**门禁 GATE PASS 1169+1 双模式 0 skipped（pg 臂 413=380+33；1076+1→1169+1 零回归 +93）**；TDD 红灯先行（52 failed 首败 ModuleNotFoundError yaml_corpus）。design 出入注记 6 条见输出（webhook 服务身份 vs 任务书 semantic:admin 措辞/owner 全条目必填 vs 样例缺项/yaml rev=内容哈希本地形态/每日兜底未接调度/T-S4 关系中间态随 G-15 调整/映射表无专表 DDL）。

- R1: tester 完成（ses_e70153663ffeGS58RkjFDskaAN，2026-10-31 11:28）——**testVerdict=PASS**（testedSha=e401d37=HEAD）。独立复跑门禁 1169+1 双模式 0 skipped（pg 臂 413；+93 逐文件对账；**零删除零弱化**——def 删空集/水位顺延五文件收集数不变/'name'→'fts' 排序链强度等价/T-S4 潜伏态语义更新+恢复断言在）。**判定表全过**：TC-YAML-04 CI 规则逐条证伪（owner 逐条报/短词「税」context 放行「抵」拦/引用分级 error·warning）+CLI 直跑 exit 0/1；TC-YAML-02 规则表 10 行逐行（含恢复自动生效 TPL_GHOST 补断言）；T-S1 YAML 场景（abbr 跨源 resync/definition 修订原样探针证实）；webhook 三态+org 头 400+secret 零落日志双通道；G-15 全链（潜伏/不复活/恢复/级联覆盖+retired 端点双防线）；G-17 构造性成立；G-18 同秒严格递增（P7 注入 +2s）+O-1 真并发单 ready 事件 pg 臂实跑；REST 三件存在性零泄露；FTS 三层序双方言+refresh 三面时效+注入 8 形态；O-2/列级过滤/close 两路径/测试维护三件。独立探针 probe/probe2（47 断言）+pg 定向 49 passed。**观察项**：N1 webhook 无重放防护（design 未要求——同请求重放由幂等兜底）；N2 T-S4 恢复步关系断言建议；N3 report_center 分页对称覆盖；N4 sync.py 注释补句；**N5 五源均未接每日兜底调度（design §5.8「每天一次兜底」半句——m2s-1 起形态，需登记）**。design 出入 6 条逐条属实。报告全文见「最新验证意见原文」details 块（R1 Tester）。

- R1: committer 完成（ses_e6ffe99deffe8USoJKteWeyvrV，2026-10-31 11:40）——**reviewVerdict=NEEDS_CHANGES**（reviewedSha 不置位；HEAD=e401d37 不通过）。**P2×2**：P2-1 合并面跳过「仅别名」条目+替换语义不完整（alias-only 条目 manual/abbr 完全不写/删空别名旧别名残留/删空 definition 旧 curated 残留——违反规则表第 1 行无 payload 前置；修复=corpus 每个 active 目标产一行〔payload 空写 {}〕+3 回归）；P2-2 同键冲突同步实体先被 YAML 覆盖（run_sync upsert 先于冲突判定——name/attrs/parent/source_system/status/三类别名被改+移出原源基数→后续删除误 missing；测试仅断言 source 列=走过场；修复=curated 源实体写入前剔除既有 sync 键+记 conflict+补断言）。**P3×13**：①abbr 短词口径不一致（CI 不拦合并拦）②别名 UNIQUE 冲突整个 run 失败③sensitivity 只增不减（COALESCE）④activated_at 未来时间戳+同秒窗口（switch 未严格递增）⑤sem_reactivate_build 返回值未消费⑥0007 未回填 sem_search_texts⑦_content_rev 含 .git 抖动⑧CI 三缺口（全局 id 唯一/match_mode 枚举/related_to src）⑨L0/owner 未持久化（=边界 4）⑩永久测试缺口 5 处⑪.env.example+semantic_l0_token_budget 死配置⑫webhook body 无上限⑬O-2 seed 未滤 status/sensitivity。**边界 4 条上报**：①_schema JSON Schema 条目级校验是否本段（TC-YAML-04 字面）②webhook admin vs 服务身份（按 design 维持注记）③N5 每日兜底登记归属④L0 持久化归属（本段 vs m2s-4 回读）。**N 裁定**：N1 信息项不补/N2·N3·N4 R2 顺手/N5 登记 known-gaps+段挂账。关键面：G-17/18+O-1/G-15/webhook/FTS/REST/分层/水位全 PASS；Tester「仅 curated_rev 变不新 rev」表述有误（yaml_rev 已入 dict_rev——宁多勿漏非缺陷）。检查点元数据注：R1「38 文件」叙述与实际 35 非 chore+4 chore+1 检查点=40 不符（归档时更正）。报告全文见「最新验证意见原文」details 块（R1 Committer）。

**spec_confirm 裁定**（2026-10-31 11:42 用户拍板「按建议执行」）：边界 1=**(a) 升 P2 本轮补 JSON Schema 条目级校验**（TC-YAML-04 字面优先）；边界 2=维持 webhook 注记不改码（design 服务身份权威）；边界 3=**登记 G-19**（五源每日兜底调度——m2s-4 承接，known-gaps 已落笔+_m2-plan 挂账）；边界 4=**(a) 本段补 L0/owner 入 curated_json**（=P3-9 升格 R2）。**P3 裁量**：R2 顺手=P3-1/2/3/4·5/7/8/11+P3-10 部分（G-15 store 直调用例+yaml 生产路径用例）；登记=P3-6（FTS 升级回填口径 RUNBOOK 一句）/P3-12（webhook body 上限）/P3-13（O-2 seed 过滤 docstring 责任）。**R2 范围**：P2-1/P2-2+边界 1〔JSON Schema〕+边界 4〔L0/owner〕+N2/N3/N4+P3 顺手 8 项。status=implementing（round=2 不清零）。

- R2: coder 完成（ses_e705c4fa5ffeWafnHS77csoK2s 续接，2026-10-31 12:01）——commit `1d27e32`（14 文件 +1168/−58，docs 批 G-19/_m2-plan/检查点裁定记录原样入库——**检查点未编辑**只读纪律遵守）。**P2-1** 合并面完整语义（删两前置跳过——每个 active 目标产一行 payload 空写 {}、别名空产出行先删后插清空；stale 仍条目级；4 回归）；**P2-2** curated 源写入前预读 sem_entity_states 剔除既有 sync 键+entity_conflicts 留痕（**替换走过场断言**——name/attrs/source_system/status/三类别名逐列不变）；**边界 1** JSON Schema 条目级校验（entry.schema.json 驱动——jsonschema 库优先+手写子集回退零依赖可跑；CI 同步）；**边界 4** l0/owner 入 curated_payload；N2 关系回 active 断言/N3 report_center 分页对称/N4 注释；**P3 八项**：abbr 免拦/别名 UNIQUE 双防线（预检+ON CONFLICT+CI 查重）/sensitivity 直写当前值（含 normal·缺省 normal）/switch 严格递增+reactivate 返回值消费（False→skipped·RuntimeError 不虚报）/.git 跳过/CI 三缺口（全局 id/match_mode/related_to src）/.env.example+预算 settings 接线/store 直调用例+yaml 生产路径全链用例（含 FTS 时效）；P3-13 顺手补 docstring。**登记项不做**（P3-6/12 已落 docs）。自测：门禁 GATE PASS 1206+1 双模式 0 skipped（pg 臂 428=395+33；1169+1→1206+1 零回归 +37）；TDD 红灯 18 failed（3 即绿=覆盖缺口补用例——与 Committer「探针已证」定性一致）。verdict 双置空待 R2 重验（R1 历史：testVerdict=PASS/testedSha=e401d37/reviewVerdict=NEEDS_CHANGES/reviewedSha 不置位——见上）。

- R2: tester 完成（ses_e70153663ffeGS58RkjFDskaAN 续接，2026-10-31 12:46）——**testVerdict=PASS**（testedSha=1d27e32=HEAD）。独立复跑门禁 1206+1 双模式 0 skipped（pg 臂 428；+37 逐文件对账；零删除零弱化——走过场断言由 test_r2_m2s3_fixes 逐列强化）。**修复项逐条全过**：P2-1 四回归+极端形态证伪（仅 name+owner 8 断言）；P2-2 全链证伪（**误 retire 链实证断裂**——YAML 删冲突条目实体仍 active missing==0/原源 resync 不污染/FTS 零残留）；边界 1 双路径（jsonschema 4.26 在场+ImportError 强制回退——定位等价；**schema 坏 JSON fail-closed**）；边界 4（非 L0 条目键缺席非 False）；P3 八项全过（**P3-4 三重切换链严格递增零并列**/P3-2 残余竞态注入/P3-3 双方言+泄漏联动四断言/P3-8 双文件定位/预算三态/store 直调+生产全链）。R1 观察项 N1~N5 对账无遗漏（G-19 docs diff 实证）；接受 Committer 指正 R1「仅 curated_rev 变不新 rev」表述误差。独立 probe_r2×3（48 断言+定向 72 passed）。**新观察 N6**（P3 级）：entry.schema.json 语义非法（有效 JSON 但 type 非法）——jsonschema 路径 check_schema 崩溃 traceback vs 回退路径优雅通过（双路径不对称；fail-closed 方向成立不破）+stats 计数微瑕（无行为影响）——建议 R3 顺手或下段收编。报告全文见「最新验证意见原文」details 块（R2 Tester）。

- R2: committer 完成（ses_e6ffe99deffe8USoJKteWeyvrV 续接，2026-10-31 12:55）——**reviewVerdict=NEEDS_CHANGES（P3 收尾级 R3；无 P1/P2 代码缺陷）**（reviewedSha 不置位）。P2-1 功能 ✅（**回归 1/4 空转**——删空别名用例未先做带别名 merge，R1 缺陷下同样通过）；P2-2 ✅（core 预读剔除方案合理/误 retire 链代码面独立核实断裂/旧弱用例残留登记）；边界 1 ✅ 主体（**N6**：schema 语义非法 jsonschema 路径 SchemaError 崩溃 vs 回退静默通过双路径不对称+validator_for/Draft202012 错配+回退无永久用例）；边界 4 ✅（l0_extra 文本未持久化——spec 只裁 payload 面，登记）；N2/N3/N4+P3 八项+P3-13 全 ✅；G-19 ✅。**监督侧落笔遗漏被抓**（P3-6/P3-12 docs 未落但检查点/Tester 称已落——**已补**：RUNBOOK 0007 升级注意+known-gaps G-20+总览表补 G-16 收口态/G-17~20）。**R3 最小范围**（Committer 建议·N6 裁定=值得 R3）：①N6 修复（entry.schema.json 加载一次性自校验 try check_schema→Issue+置 None；回退补最小合法性检查；validator_cls 使用）②P2-1 空转测试补前序 merge ③误 retire 链永久断言 ④回退路径永久用例。登记级六项观察（旧弱用例强化/inserted 计数/两测试名实/覆盖层删除 sensitivity 不回退口径化/非法 sensitivity 静默 normal 注记/总览表——⑥已清偿）。**备选**：不跑 R3 条件性 APPROVED（N6 等登记下段+docs chore 补齐）——按建议走 R3。报告全文见「最新验证意见原文」details 块（R2 Committer）。

- R3: coder 完成（ses_e705c4fa5ffeWafnHS77csoK2s 续接，2026-10-31 13:06）——commit `f6cd5b2`（5 文件 +443/−22，docs 批 RUNBOOK 0007 注意/G-20/总览表原样入库——检查点只读未编辑）。**N6 修复**：entry.schema.json 加载一次性自校验（jsonschema 在场 `validator_for().check_schema` try 捕→可定位 Issue+置 None 回落手写面/回退路径 `_minimal_schema_self_check` 对称〔type 七值/required 数组/enum·properties·items 递归〕/`_schema_errors` 改 validator_for 实例化删 Draft202012 硬编码/非对象 schema error）；**三测试补强**：P2-1 删空别名补前序 merge（带前置在场断言——R1 缺陷下双失败）/误 retire 链永久断言（删冲突条目再 sync→missing==0+实体 active 进门禁）/回退路径永久用例（monkeypatch jsonschema=None 强制回退——双路径定位等价+字段级命中）。登记级六项不做（按裁定）。自测：门禁 GATE PASS 1209+1 双模式 0 skipped（pg 臂 428；1206+1→1209+1 零回归 +3=N6 三用例）；TDD 红灯（SchemaError 未捕获崩溃实证/非对象零 error/回退不对称）。verdict 双置空待 R3 终验（R2 历史：testVerdict=PASS/testedSha=1d27e32/reviewVerdict=NEEDS_CHANGES〔P3 收尾级〕——见上）。

- R3: tester 完成（ses_e70153663ffeGS58RkjFDskaAN 续接，2026-10-31 13:18）——**testVerdict=PASS（收敛）**（testedSha=f6cd5b2=HEAD）。独立复跑门禁 1209+1 双模式 0 skipped（pg 臂 428；+3 恰三个 N6 用例；零删除零弱化）。**N6 四子面闭合**：原崩溃场景重跑（SchemaError 消除→可定位 Issue+entry_schema=None 回落手写面 owner 仍拦）/原不对称场景重跑（回退侧同报可定位 error）/validator_for 实例化（draft-07 合法 schema 不误抛+校验仍生效）/非对象 error；合法仓零误伤+CI exit 1 可定位无 traceback。**三测试补强变异真红核验**（probe_r3_mutation 9 断言）：P2-1 R1 缺陷模拟下清空断言真失败；误 retire 缺陷态〔5 filler 17% 越 guard〕下永久断言真红——**误 retire 防护纵深三层**（core 预读剔除+guard 比例+FTS/展开无泄漏）。回退永久用例双路径独立比对非 mock 自证。**docs 三件落笔核实**（RUNBOOK 0007/G-20/总览表）。probe_r3×2（22 断言）+pg 定向 39 passed。零 FAIL 零新增观察。报告全文见「最新验证意见原文」details 块（R3 Tester）。

- R3: committer 终审完成（ses_e6ffe99deffe8USoJKteWeyvrV 续接，2026-10-31 13:44）——**reviewVerdict=APPROVED**（reviewedSha=f6cd5b2=testedSha=HEAD 三一致；P1/P2 无，P3×4 全登记级**不值得突破轮上限**）。N6 四子面方案成立（加载一次性自校验合理/entry_schema=None 回落非静默/回退对称/validator_for 修复）；三测试补强真红采信（变异核验+代码独立确认——误 retire 防护纵深三层成立）；docs 三件 ✓；门禁 +3 对账/零删除零弱化/检查点只读纪律合规。**P3 登记级**：①回退/边界自校验健壮性（type 数组/布尔子 schema 回退 false positive——零依赖 only 主路径不受影响→下段）；②known-gaps 状态回写未完整（**G-15 应改已收口**〔m2s-3 R1 已收——监督侧漏〕/G-17·18 正文状态与总览表不一致——归档补）；③RUNBOOK 0007 note 落点建议挪 §3+注双方言（nit）；④登记级 ①~⑤+⑦ 未落盘（终态归档写入）。**交付前置（监督侧）**：检查点终态+遗留事项①~⑤+⑦入库/known-gaps 补齐/_m2-plan m2s-3 done+语义 3/6/PR+manifest（rounds=3）/留痕+用户合入。**双通过达成（round=3 收敛）**。

**交付链**（2026-10-31 13:55 用户确认交付）：① 监督侧 docs 补齐（G-15 改已收口〔正文+总览表〕/G-17·18 正文状态同步已收口/RUNBOOK 0007 note 挪 §3+注双方言）+ 检查点归档 docs-only commit（reviewedSha 按 m2s-2/m2-3 先例更新为归档 HEAD、testedSha 保持 f6cd5b2）→ ② Coder push+PR → ③ Committer 留痕 → ④ manifest → ⑤ 待用户合入。

**交付链执行**（2026-10-31 13:59 三步完毕）：① 监督侧 docs 补齐+归档 commit **`2f2244a`**（docs-only——reviewedSha 按先例更新、testedSha 保持 f6cd5b2；push f7b7201..2f2244a）；② **PR #7**（base=develop，4 commits，OPEN）；③ Committer 评审留痕 **PRR_kwDOVZ9dhM8AAAABVQfx5w**（2026-10-31T05:58:45Z，COMMENTED 载体正文首行 APPROVED）；④ evidence manifest 入 PR description（16 键——双 SHA/门禁四段基线/rounds=3/specRulings×4/gapClosures×4/handover，远端回读校验通过）。**待用户合入指令**（不自动合入）。

**合入完成**（2026-10-31 14:06 用户指令「合入」）：`gh pr merge 7 --merge` → **MERGED**，mergeCommit **`e870fd1ce4a60c614977f1b56385d289bb9486f3`**；origin/develop f4d1b74→e870fd1，本地 develop_opencode 已 ff 同步。**PR 标题修正**（14:05 用户指出 ".S2a" 混乱——两套编号澄清后修正：#7「M2-S2 基础段（m2s-3）：…」/#6「M2-S1 面上段（m2s-2）：…」；_m2-plan 段表加编号口径注记）。收尾：检查点 status=done；TEST-CASES v1.9.7（§六 M2-S2 行 m2s-3 段完成态——工作区随下段 chore 批）；_m2-plan/AGENTS.md 进度更新（语义轨道 3/6、下一段 m2-4）。任务闭环（3 轮，1076+1→1209+1）。报告全文见「最新验证意见原文」details 块（R3 Committer）。

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

<details>
<summary>R1 Tester 报告全文（2026-10-31 11:28，testVerdict=PASS）</summary>

# task-knowledge-lattice-m2s-3 R1 独立验证报告（Tester）

**testVerdict: PASS**
**testedSha: e401d371124188918e151eb050a6c371a6915393**（git rev-parse 实测，验证前后一致；工作区仅监督侧 supervised-coding.md + 检查点两文件既有改动，被测代码面零变动）

## 1. 门禁真实输出（必跑项——独立复跑，不采信 coder 自测）

```
pg 臂用例收集数：413（[pg] 参数化 380 + PG 专用 33，> 0 ✓）
==== [pytest] uv run pytest -m 'not manual' -q ====
[pytest] OK：1169 passed, 1 deselected, 2 warnings in 176.66s
==== [pytest-O] uv run python -O -m pytest -m 'not manual' -q ====
[pytest-O] OK：1169 passed, 1 deselected, 3 warnings in 223.43s
GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
（pg 臂 413 条用例全实跑：[pg] 参数化 380 + PG 专用 33）
```

- **skip 核对**：双模式 **0 skipped**（门禁脚本 skip=失败语义兜底）；`1 deselected` = `tests/test_ui_01_manual.py::test_ui_01_manual_walkthrough`（TC-UI 人工走查常驻 manual 标记，m1-5 起既定口径，非本段范围）——**任务范围内零 skip**。
- **+93 逐文件对账**（基线 1076+1 → 1169+1，与 coder 申报一致）：

| 文件 | 收集数增量 | 依据 |
|---|---|---|
| test_yaml_01_corpus_ci（新） | +14 | 14 用例 |
| test_yaml_02_merge（新，双臂） | +20 | 10 用例 ×2 |
| test_yaml_03_webhook（新） | +5 | 5 用例 |
| test_sync_06_sources（新，G-15 双臂） | +19 | 部分双臂 |
| test_build_04_current_ptr（新，双臂） | +10 | 5 用例 ×2 |
| test_sem_rest_read（新） | +6 | 6 用例 |
| test_sem_fts_search（新，部分双臂） | +15 | — |
| **新文件小计** | **+89** | |
| test_build_01_rev_switch | +2 | 崩溃注入 1 函数 ×双臂 |
| test_sem_expand_search_backend | +2 | 双向同层去重 1 函数 ×双臂（O-2 为既有用例断言强化） |
| 其余 9 个修改文件 | 0 | 迁移水位顺延/mcp 'name'→'fts'/T-S4 全为断言适配 |
| **合计** | **+93** ✓ | |

- **零删除零弱化核验**：`git diff f4d1b74..HEAD -- tests/ | grep "^-.*def test_"` **空**（零测试函数删除）。既有测试适配逐项核验为**非弱化**：①mcp ranking `'name'→'fts'`——排序链断言保持（`alias-prefix` 先于 `fts`，强度等价）；②T-S4 中间态 `active→missing`——系 G-15 关系级消失语义更新，③超期 retired 双断言（实体+关系）原样保留、恢复→active 断言在（关系侧恢复断言见观察项 N2，已由探针独立补证）；③迁移水位五文件（scaf_03/v11/sem_01/pg_scaff/regress）全部为断言顺延（`user_version 6→7`、`[2..6]→[2..7]`、`[6]→[6,7]`、乱序探针 0008→0009），测试函数零增减、收集数不变。

## 2. 分用例判定表

| 用例/项 | 判定 | 关键证据 |
|---|---|---|
| **TC-YAML-04** CI 校验全集 | ✅ PASS | 14 用例全绿；owner 逐条报（concepts/vat.yaml 定位）、samples>3 逐条、L0 预算、短词（「税」标 context 放行/「抵」拦）、常用词（fuzzy_only 放行）、歧义别名需消歧或 context（正反两向）、引用可解析（concept/system 仓内必须存在=error、同步类型缺=warning 分级）、纯人工仅 concept/system、sensitivity 合法；`scripts/sem_yaml_ci.py` CLI 独立直跑：干净仓 exit 0 / owner 缺失 exit 1 逐条报（探针实测） |
| **TC-YAML-01** 合并正路 | ✅ PASS | curated_json+curated_rev=rev、manual/abbr 别名落库（kind 区分）、字段覆盖层同落、纯人工实体 source='curated'、refers_to 关系写入、stats.curated 留痕 |
| **TC-YAML-02** 合并规则表逐行 | ✅ PASS | 对照 design §5.9 表（L939-952）10 行逐一：同键冲突（source='sync' 不动）/合并侧 fail-closed（短词不写入）/与同步重复提示可删（duplicate of sync relation (can delete)）/白名单冲突/YAML 删除清 curated+manual（事实列 name 原样断言）/未同步记冲突+**恢复后自动生效**（补一条 TPL_GHOST 恢复断言）——逐行一致 |
| **T-S1** YAML 场景验收句 | ✅ PASS | 事实列 name 更新/curated_json 原样/manual 别名原样；name·code·sync 重建不动 manual/abbr 由 store DELETE kind IN('name','code','sync') 构造性保证+探针 Q2c/Q2e 独立证实（abbr MMK 跨源 resync 与 definition 修订后均原样） |
| **TC-YAML-03** webhook | ✅ PASS | 三态（正确签名 202+yaml_merge 事件同事务+任务行；错签名 401 零任务；缺签名/Bearer 替代均拒）+org 头不一致 400；secret 零落日志（caplog 用例+探针 root DEBUG 捕获双通道） |
| **TC-SYNC-02** 半句 | ✅ PASS | metadata 引用面 = YAML 显式（t2 表级+t3 列引用父表）∪ tc 推导兜底（t1）——并集断言；tc 未配置时 warning 降级路径在码 |
| **TC-SYNC-06** 半句 | ✅ PASS | 映射生效（CN-SH→CN）/未映射原样（UNKNOWN）+探针 P6 部分映射混合（未覆盖 dim biz 原样、双值映射、US-TX 原样） |
| **G-15** 关系级消失 | ✅ PASS | 删边→missing（relations_missing=1，不参与展开）→超期 retired（relations_retired_standalone）；指向 retired 端点不回 active（core 冲突过滤+store CASE 双防线）；missing 端点放行落潜伏（探针 P4c-A：边首见+端点 missing → INSERT 落 missing；P4c-B：vanish 后边回归+端点 missing → 保持 missing 不复活）；级联 retired 覆盖（探针 P4g） |
| **G-17** | ✅ PASS | YAML 改 definition → dict_rev 必变（curated_json 入快照元组+yaml_rev=max(curated_rev) 入 dict_rev 与 build 行）；边界「仅 curated_rev 变不改 curated 不新 rev」由 rev=内容哈希+快照输入面构造性成立 |
| **G-18/O-1** | ✅ PASS | 0007 迁移双方言（activated_at 回填/source_system 回填/FTS 表 sqlite fts5 外容+pg tsv GENERATED+GIN 逐列核对）；rev 回退重激活 current 跟随（UNIQUE 行复用+activated_at 顶置）；**同秒防并列**：`MAX(CURRENT_TIMESTAMP, max+1s)` 严格递增（探针 P7 同秒注入后重激活 activated_at=+2s）；**同 rev 竞态条件 upsert**（`DO UPDATE … WHERE status != 'ready'` 返回 (existing, True)）；真并发双方言：`test_concurrent_same_rev_single_ready_event[pg]` 于门禁 pg 臂实跑 + 定向复跑 49 passed |
| **迁移框架** | ✅ PASS | 水位顺延四套框架测试全绿（含 user_version 7+测试迁移 0008/0009 乱序拒绝 fail-fast）；0007 幂等（schema_migrations 记录语义）双方言落库 |
| **REST 读端点** | ✅ PASS | 列表/详情（expand/depth）/describe 三件；成员 200·非成员 403·无 token 401·restricted 404（存在性零泄露：999999 与 restricted 同 404）·参数越界 400·未登记表 403 防枚举 |
| **FTS** | ✅ PASS | 三层序（alias-exact 1.0 > alias-prefix 0.8 > fts 0.5）双方言；bm25/ts_rank 方向差异按 G-6 已吸收为名次（断言排序不追平分数）；score 双方言 float JSON 可序列化；符号 token 滤除/纯符号跳层零误配；refresh 三面（别名重建/名称变更/curated 替换+清除）各接 sem_refresh_search_texts + 探针 Q3 合并后立即可搜/删除后不再命中 |
| **O-2** | ✅ PASS | expand_relations nodes 含 seed（depth=0）+双向同层去重样本 |
| **describe 列级过滤** | ✅ PASS | restricted 列 key/name 不出现在主透传（c_sec 滤除断言）+3s 钳制永久断言（timeout_s=99 → clamped 3.0） |
| **close 接线** | ✅ PASS | 正常路径（closed==1）+异常路径（探针 Q1：fetch 抛错 → finally close 仍执行、run 落 failed、异常上抛）——finally 结构 + runner L296-298 任务行收尾分工核清 |
| **测试维护三件** | ✅ PASS | 环 len==3 恰 3 边+双向同层去重样本 / 构建侧 audit= 崩溃注入永久用例（行+事件双回滚）/ 3s 钳制永久断言——三者均在库且双臂实跑 |

## 3. 独立脚本清单与结果（不依赖 coder 测试文件的直接驱动）

| 脚本 | 内容 | 结果 |
|---|---|---|
| probe_m2s3.py | P1 webhook 签名四变体（空/错密钥/**重放签名串+篡改体**/缺头）全 401+零任务行零 outbox；P2 secret+签名串零落日志（root DEBUG 全量捕获，拒绝+合法双路径）；P3 rev 回退三面一致（sem_current_build / get_entity 锚点 / builds 列表两 ready 并存）；P4 G-15 全链（INSERT 潜伏/不复活/恢复回 active/删边 vanish/级联 retired）；P5 FTS 注入 8 形态；P6 值域部分映射；P7 同秒并列+严格递增+非 ready 零生效 | **37 PASS / 0 FAIL** |
| probe2_m2s3.py | Q1 close 异常路径；Q2 abbr 跨源 resync/definition 修订原样+sync 别名重建；Q3 curated 别名 FTS 时效三态 | 10 PASS / 1 探针误设（Q1c：任务行 failed 落点在 worker runner 包装层 L296-298——直调面越权断言，非实现缺陷，已核码定性） |
| sem_yaml_ci.py CLI 直跑 | 干净仓/违规仓 | exit 0 / exit 1 逐条报 ✓ |
| pg 臂定向复跑 | test_build_04+test_sync_06+test_yaml_02 双臂 | 49 passed ✓ |

## 4. 缺陷清单

**FAIL（IMPL_BUG）：无。** 观察项（不阻塞，供监督侧裁量）：

- **N1（信息项）**：webhook 无重放防护（nonce/时间窗）——**design §6.2 未要求**（仅"校验签名；服务身份"）；篡改体重放已证 401（P1c）；完全同请求重放 = 重复触发 202，由 sync 幂等 + 同 rev 构建跳过兜底，无害。
- **N2（测试增强建议）**：T-S4 测试恢复步②只断言实体回 active，未补一行关系回 active 断言（潜伏→恢复链路由本报告探针 P4e/P4c-B2 独立证实，无行为缺陷）。
- **N3（覆盖对称性）**：report_center 分页循环有实现（fetch cursor loop 与 scenario_config 同构）但无专门分页测试（scenario_config 有）——建议后续补对称覆盖。
- **N4（文档措辞）**：sync.py 注释「store INSERT/**UPDATE** 的 CASE 守卫将其落为 missing 潜伏态」对 UPDATE 分支只覆盖"已 missing 行保持"语义；已 active 行在端点 missing 窗口保持 active（基线兼容中间态——展开侧按实体 active 过滤不可见、超期由级联 retired 收口，探针 P4c-0/P4g 实证）。行为无害，注释可补一句。
- **N5（出入④属实）**：五源**均**未接每日兜底调度（app.py 兜底循环只认领任务行）——非本段新增缺口（m2s-1 起形态如此），design §5.8 适配器表"每天一次兜底"半句的统一接线需后续段登记。

## 5. 与 coder 自测对账

门禁数字逐项一致（1169+1 双模式 0 skipped、pg 臂 413=380+33、+93 构成）；TDD 红灯先行（52 failed ModuleNotFoundError）属历史过程不可独立复现、不采信也不需要；全部交付声明（含六条出入注记）经独立执行与代码审读一一证实，无虚报。

## 6. design 出入 6 条核实（逐条）

1. **webhook 签名=服务身份 vs 任务书 semantic:admin 措辞** ✅ 注记成立——design §6.2 webhook 行权威文本为"校验签名；服务身份"，实现与 design 一致（无签名 401 fail-closed，secret 未配置一律拒绝）；
2. **owner 全条目必填 vs 样例缺项** ✅ 注记成立——design §5.8 覆盖层样例确无 owner 字段，规则文本"每条 YAML 必填 owner"+§10 为准，实现按全条目执行（yaml_corpus.py:339）；
3. **yaml rev=内容哈希本地形态** ✅ 注记成立——本地 checkout 目录无 .git，全仓内容哈希（排序遍历 sha256 前 12 hex）语义等价"内容变更必变"，test_corpus_rev_is_content_hash 证实；
4. **每日兜底未接调度** ✅ 注记属实（见 N5）；
5. **T-S4 关系中间态随 G-15 调整** ✅ 注记成立——断言 active→missing 为关系级消失语义的正确更新，终态口径不变，强度不减；
6. **映射表无专表 DDL** ✅ 注记成立——dim_value_map.yaml + attrs_json.dims 结构化承载，任务书 A.4 授权的最小实现已注记。

---

</details>

<details>
<summary>R1 Committer 报告全文（2026-10-31 11:40，reviewVerdict=NEEDS_CHANGES）</summary>

# m2s-3 R1 Committer 审查报告

**基线核对**：HEAD = `e401d37`（= testedSha = 检查点 R1 终态）；上一轮 `reviewedSha=null`（R1 首审），审查对象为 `git diff f4d1b74..e401d37`（stat 40 文件 +4282/−220，与检查点 filesChanged 条目数一致）。工作区仅 `.opencode/agent/supervised-coding.md` 与检查点两文件为监督侧改动，**代码面零变动**。E 组 chore 4 文件原样入库、`supervised-coding.md` 未入库 ✓。

**门禁证据**：采信 Tester（1169+1 双模式 0 skipped，pg 臂 413=380+33）。我用收集数构成独立核对：新文件 +89（14/20/5/19/10/6/15）+ 既有文件新增 4（build_01、expand 各 ×2）= **+93**，1076+93=1169 ✓；pg 参数化新增 32 = 413−381 ✓。本角色 shell 仅放行 git/gh 只读命令，未复跑 pytest（不采信/不虚报）。测试门禁审查：diff **无 skip/xfail 新增、无 `def test_` 删除**；mcp `'name'→'fts'`、T-S4 `active→missing` 属语义适配、强度等价；迁移水位五文件仅断言顺延。**任务范围内零 skip、零弱化**。

## 1. 问题清单

### P1
无。

### P2（需修；均属本段验收语义）

**P2-1 合并面跳过「仅别名」条目 + 替换语义不完整** — `core/semantic/yaml_merge.py:110-112、136-137、191`
- 现象：`if not payload: continue` 把「无 definition/why/caliber/examples/samples/disambiguation」的条目整条跳过。① 覆盖层/纯人工条目**只声明 aliases/abbr**（合法且自然：`concept` 仅 name+aliases 可过 CI）→ manual/abbr **完全不写入**；② 既有条目**删空别名**（保留 definition）→ `alias_rows` 无该实体 → `sem_replace_manual_aliases` 不替换 → **旧 manual/abbr 残留**；③ 删除 payload 字段但保留条目 → 该实体在 `keep` 集内，`sem_clear_stale_curated` 不清 → **旧 curated_json 残留**。
- 违反 §5.8 合并规则第 1 行「合并：写 curated_json、manual/abbr 别名」（无 payload 前置条件）；§5.8 三种内容分工表明确「别名、缩写…L0 标记」属人工内容。
- 修复建议：corpus 内每个 active 目标都产出一行（payload 空则写 `{}`；别名空则产出行以执行「先删后插」清空）；stale 清理仍只负责「条目整体消失」。补 3 个回归：alias-only 覆盖层、删空别名、删空 definition。

**P2-2 同键冲突：同步实体在冲突判定前已被 YAML 覆盖** — `core/semantic/sync.py:181-193`、`store/sqlite/backend.py:2192-2201`、`store/postgres/backend.py:1636-1646`、`yaml_merge.py:94-102`
- 现象：pure 条目走 `run_sync` 实体 upsert + 别名重建（先于 `post_run` 的 `_is_synced` 冲突判定）。`(type,key)` 与同步实体相同时，同步实体已被改写：`name`/`attrs_json`/`parent_id`/`source_system`（yaml）、`status='active'`、`name/code/sync` 三类别名被替换为 YAML 条目内容；随后 merge 才记 conflict。副作用：该实体移出原适配器 `sem_active_source_keys` 基数；YAML 纯条目后续删除会把**同步实体**标 missing（N5 无每日兜底时可能被误 retire）。
- 违反规则表第 3 行「纯人工实体与同步实体 `(type,key)` 相同 → 报错（同步实体不动）」；`tests/test_yaml_02_merge.py:161-174` 仅断言 `source == 'sync'`（该列 UPDATE 本就不动），未测实际破坏面——**走过场测试**。
- 修复建议：`run_sync` 对 `relation_source='curated'` 源在实体写入前预读既有状态，`existing.source='sync'` 的键从实体 upsert/别名重建中剔除并记入 stats conflict（或 store 层在 `row.source='curated'` 且既有 `source='sync'` 时跳过 UPDATE + 别名重建）；测试补 name/attrs/source_system 与 name/sync 别名不变的断言。

### P3（监督侧裁量：R2 顺手或登记）

1. **abbr 短词口径不一致**：`yaml_merge.py:129-134` 对 abbr 套 `_alias_blocked`（短词/常用词），而 `yaml_corpus.py:121-123` 声明「缩写天然短不参与短词拦截」、CI（`yaml_corpus.py:354-356`）确实不拦 abbr → 1 字缩写 CI 通过、合并静默跳过并记冲突。建议合并侧对 abbr 免短词检查（或 CI 同步执行），口径统一。
2. **别名 UNIQUE 冲突未消解**：`sem_replace_manual_aliases`（sqlite:2864-2898 / pg）无 ON CONFLICT；同一 YAML 条目内重复 `alias_norm`、或 manual 别名与既有 `name/code/sync` 别名同 norm → `UNIQUE(org,entity,alias_norm)` 违例使整个 yaml run 失败（非冲突记录）。建议逐条 skip + 冲突，或 `INSERT OR IGNORE` 语义 + CI 查重。
3. **sensitivity 只增不减**：`sem_write_curated_batch` 用 `COALESCE(:sensitivity, sensitivity)`（sqlite:2848-2857 / pg:2267-2282）；`sem_clear_stale_curated` 不清 sensitivity。YAML 移除 sensitivity 后实体永久 restricted（fail-closed 方向安全，但 YAML 不再是真源，且无冲突记录）。建议按 YAML 当前值回写（含显式 `normal`）或登记 fail-closed 口径。
4. **activated_at 时序窗口**（G-18 核对面）：重激活取 `max(now, max+1s)` 会写入**未来时间戳**（Tester P7 实证 +2s）；同秒内（或 T+1 前）新 rev 的 `sem_switch_build_ready` 写入 `CURRENT_TIMESTAMP` 会落后，current 不跟随最新 ready（≤1s 窗口，双方言同构）。另 `build.py:173-178` 为 check-then-act：并发新 rev 已完成时，旧 rev 重激活仍会覆盖。建议 switch 也走严格递增序列（或改单调序列 + 单事务内决策）。
5. **`sem_reactivate_build` 返回值未消费**：`build.py:177-190` 忽略 `False`（竞态下行已非 ready），仍报 `status=ready`、写「reactivated」日志。建议按返回值降级为 skipped/重读 current。
6. **0007 迁移未回填 `sem_search_texts`**：升级后既有 active 实体需等下一次对应源 sync 才进 FTS 第三层；叠加 N5（无每日调度）窗口可能很长。建议 app 侧一次性回填或登记升级口径。
7. **`_content_rev` 含 `.git`**：`yaml_corpus.py:206-214` 排序遍历全仓文件；适配器 docstring 把 endpoint 定义为「本地 Git checkout 目录」——真实 checkout 的 `.git` 变动（fetch/index/logs）会使 rev 抖动 → 每次 webhook 都换 dict_rev 强制重建。建议跳过点目录（至少 `.git`）或直接 `git rev-parse`。
8. **CI 规则缺口**（`yaml_corpus.py:290-420`）：① 全局 id 唯一未查（design 样例注释「全局唯一，CI 校验」；重复 id 在 merge 侧按文件序静默覆盖——`test_yaml_02:177-187` 正依赖该不确定行为）；② `match_mode` 枚举未查（非法值入库时 DB CHECK 失败 → run failed）；③ `related_to` 只查 dst=concept、未查 src（`system` 条目 related_to CI 通过、运行时白名单拒绝）。建议补三条最小校验。
9. **L0/owner 人工面未持久化**：`curated_payload`（yaml_corpus.py:125-138）不含 `l0`；`l0.yaml` 文本仅存内存 Corpus；覆盖层 owner 不落库。design §5.8 三种内容分工表把「L0 标记」列入 curated_json 面；m2s-4 L0 导出（`export_l0` 仍占位）与构建报告「无人维护/孤立条目」将无数据源。建议本段补入 curated_json 或显式段挂账由 m2s-4 回读 YAML 仓（二选一）。
10. **永久测试缺口**（Tester 探针已覆盖、但不在门禁常跑）：store CASE 第二道防线（直调 `upsert_relations_batch` 指向 retired/missing 端点——`test_g15_upsert_filters_retired_endpoints` 被 core 预过滤遮蔽，实际走 missing 路径）；`run_sync_task` 的 yaml 生产路径（post_run/dim_map/close 组合）；curated 别名替换后 FTS 时效（`test_yaml_02` 不查 FTS）；`test_migration_0007_backfills_activated_at` 名为回填实测排序兜底；`test_concurrent_same_rev_single_ready_event` 为顺序两次调用、非并发。
11. **配置面**：`.env.example` 未登记 `LATTICE_SEM_L0_TOKEN_BUDGET` 与 `semantic_sources[org].yaml.endpoint/webhook_secret` 样例（webhook 运维不可知）；且 `semantic_l0_token_budget` 配置**未接线**（CI 脚本 `--l0-budget` 硬编码 1500，`validate_corpus` 调用方不传 settings）→ 死配置。
12. **webhook body 无大小上限**（`api/semantic.py:336` `await request.body()` 先于验签）：公网入口可被打大 body 内存放大；design 未要求，可登记。
13. **O-2 seed 未过滤 status/sensitivity**：`_expand_relations_thin`（双方言）把 seed 实体原样注入 nodes（含 restricted/非 active），与 design §5.9 walk CTE 最终 SELECT 的 active/restricted 过滤不一致；当前无消费方（get_entity 走 `sem_expand_graph`），M2-S3 消费方须自滤。建议 seed 读取复用过滤语义或在协议 docstring 明确责任（已注记一半）。

## 2. 需求边界问题（交 supervised-coding / 用户确认，不写 coder 缺陷）

**有**，4 条：

1. **`_schema` JSON Schema 条目级校验是否本段范围**：TC-YAML-04 步骤字面列「JSON Schema」，design §8 M2-S2 列「CI 校验（schema/…）」；任务书 A.1 仅写「`_schema` 自描述+CI 校验脚本」。实现只校验 schema 文件可解析 + 手写结构规则，**未按 schema 校验条目**。若按 test-case 字面 → 应升 P2 补最小校验；若「自描述」即本意 → 请登记口径。
2. **任务书 A.2「webhook semantic:admin 门控」 vs design §6.2「校验签名；服务身份」**：实现按 design（无 Bearer/admin 门控，签名即服务身份），Tester 已核实 design 权威。建议检查点保留出入注记（已有），不再改码。
3. **N5 五源「每天一次兜底」未接调度**：design §5.8 适配器表半句 vs 任务书 A.3 未列调度面 → 见 N5 裁定（登记 + 段挂账）。
4. **L0 标记持久化归属**：design §5.8 分工表 vs 实现未入 curated_json（P3-9）——M2-S4 L0 导出的前置依赖，请裁定「本段补」或「m2s-4 回读 YAML 仓」。

## 3. Tester 观察项 N1~N5 裁定

- **N1（webhook 重放）→ 信息项，本段不补**。design §6.2 未要求 nonce/时间窗；错密钥/篡改体已 401；完全同请求重放 = 重复触发，经 run_sync 幂等 + 同 rev 构建跳过（`run_build` current 同 rev → skipped）兜底成立。可选加固（时间窗/nonce）登记即可。
- **N2（T-S4 恢复步关系断言）→ R2 顺手**（一行断言：恢复后关系回 active；探针已证，成本极低）。不阻塞。
- **N3（report_center 分页对称覆盖）→ R2 顺手**（实现与 scenario_config 同构，建议补对称用例；若不补则登记）。
- **N4（sync.py 注释补句）→ R2 顺手**（补「已 active 行在端点 missing 窗口保持 active，展开侧不可见、超期由级联 retired 收口」）。
- **N5（五源未接每日兜底调度）→ 登记，本段不补**。理由：任务书 A.3 未列调度面；m2s-1 起既有形态（非本段引入）；但 design 正文半句不能无家——要求 **known-gaps 新条目 + `_m2-plan` 段挂账**（建议归 m2s-4 或专门维护段，明确窗口/幂等/与 webhook 触发去重口径）。

## 4. 关键面显式结论

| 关键面 | 结论 |
|---|---|
| YAML corpus/rev/validate | 装载/内容哈希 rev/owner 全条目/samples≤3/L0 预算/短词常用词/别名消歧/引用分级/纯人工限定/sensitivity **逐项实现且测试证伪成立**；CI 脚本 exit 0/1 证据在 Tester 报告 ✓（边界 P3-8） |
| yaml_merge 10 行逐行 | 第 2/4/5/6/7/8/9/10 行 ✓；**第 1 行 P2-1**；**第 3 行 P2-2** |
| webhook 安全面 | HMAC-SHA256 + `compare_digest` 常量时间、secret/签名零落日志、无签名/错签名 401 fail-closed、Bearer 不替代、`create_task(audit=)` 同事务 ✓（N1 信息项） |
| G-17 | curated_json 入快照 + yaml_rev=max(curated_rev) 入 dict_rev 与 build 行 ✓；**Tester 报告「仅 curated_rev 变不新 rev」表述有误**（yaml_rev 已入 dict_rev，任何内容哈希变都会新 rev——属 design「YAML commit 入键」的宁多勿漏，非缺陷） |
| G-18/O-1/0007 | 双方言同构（activated_at 回填/source_system 回填/FTS 结构）；`MAX(now,max+1s)` 严格递增正确；条件 upsert 返回 `(id,was_ready)` 消费正确；rev 回退重激活+行复用+顶置 ✓（时序窗口见 P3-4/P3-5） |
| G-15 | 关系级 missing→宽限→`relations_retired_standalone` 状态机 ✓；retired 端点 core 冲突 + store CASE 双防线在码 ✓；missing 端点放行（INSERT 落 missing、UPDATE 不复活）✓；级联覆盖 active+missing ✓；与 T-S4 实体宽限一致（N4 注释） |
| FTS 升级 | 三层序（alias-exact 1.0 > prefix 0.8 > fts 0.5）保留；双方言评分差异按 G-6 名次断言；`word_tokens` 符号滤除；refresh 三面在码 ✓（永久测试缺口 P3-10） |
| REST 读端点 | semantic:read=成员门控 ✓；restricted/他组织/不存在同 404、未登记表 403 零泄露 ✓；参数越界/非法 types 400 ✓（`_require_semantic_read` 与 `org_scoped` 重复，无害） |
| T-S4 断言适配 | `active→missing` 为 G-15 正确语义更新，恢复/超期终态断言在，**非弱化**；N2 仅补恢复步关系断言 |
| 分层纪律 | `core/semantic` 零方言 SQL（grep 仅注释命中）✓；adapters 协议 ✓；`auto_entities` 未动（仍钉 api/mcp）✓ |
| 测试质量 | 新增 61 个测试函数/93 收集，抽查无显式恒真；但有 5 处名实/覆盖强度问题（P3-10）与 1 处走过场断言（P2-2 的 `source` 断言） |

## 5. 结论

**reviewVerdict: NEEDS_CHANGES**

- P2-1（别名面合并/清理不完整）与 P2-2（同键冲突下同步实体被覆盖且测试未测实）为阻塞项，修复期望见上；R2 验证需补对应回归（alias-only、删空别名、冲突实体 name/attrs/source_system/别名不变）。
- P3 由监督侧裁量：N2/N3/N4 顺手；P3-1/2/3/8/9/11 建议本轮或下段处理；P3-4/5/6/7/10/12/13 可登记。
- **交付就绪判定：不就绪（R1 首审未过）**。当前 `status=testing`、无 PR，交付门（PR + evidence manifest 双 SHA=最终 HEAD + `gh pr review` 留痕）尚未到执行点；修复后重审通过再进入交付链。
- **CASE_BUG 裁定请求：无**（本轮 Tester 未提交）。
- 检查点元数据小注（监督侧）：R1 叙述「38 文件（13 新增+25 修改）」与实际 35 个非 chore 文件（15 新增+20 修改）+4 chore+1 检查点=40 不符（38+1+4≠40），stat 与 filesChanged 条目本身一致，建议归档时更正叙述。

**元数据更正（监督侧采纳）**：R1 轮次记录文件数叙述以此为准——35 非 chore（15 新增+20 修改）+4 chore+1 检查点=40 stat 条目。

</details>

<details>
<summary>R2 Tester 报告全文（2026-10-31 12:46，testVerdict=PASS）</summary>

# task-knowledge-lattice-m2s-3 R2 独立复验报告（Tester）

**testVerdict: PASS**
**testedSha: 1d27e32a91441228dc2d794bf944c60602d6a2c6**（git rev-parse 实测，验证前后一致；工作区仅监督侧 supervised-coding.md + 检查点两文件既有改动，被测代码面零变动；检查点只读纪律遵守）

## 1. 门禁真实输出（独立复跑）

```
pg 臂用例收集数：428（[pg] 参数化 395 + PG 专用 33，> 0 ✓）
==== [pytest] uv run pytest -m 'not manual' -q ====
[pytest] OK：1206 passed, 1 deselected, 2 warnings in 149.78s
==== [pytest-O] uv run python -O -m pytest -m 'not manual' -q ====
[pytest-O] OK：1206 passed, 1 deselected, 3 warnings in 149.98s
GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
（pg 臂 428 条用例全实跑：[pg] 参数化 395 + PG 专用 33）
```

- **skip 核对**：双模式 **0 skipped**；`1 deselected` = TC-UI manual 走查（既定口径）——**任务范围内零 skip**。与 coder 申报（1206+1 / 428=395+33 / +37 零回归）逐项一致。
- **+37 逐文件对账**：`test_r2_m2s3_fixes.py`（新）36 收集（15 函数 ×双臂 + 6 单臂：test_b1/p3_2_ci/p3_8×3/p3_11 走 tmp_path 不参数化）+ `test_sync_06_sources.py` +1（test_report_center_paging，单臂）= **37** ✓。
- **零删除零弱化**：`git diff e401d37..HEAD -- tests/ | grep "^-.*def test_"` **空**；test_sync_02_guard 仅加 N2 断言（+5 行，无函数增减）；既有 P2-2 走过场断言已被**替换**（test_yaml_02 既有冲突用例经核未被删除，R2 新用例在 test_r2_m2s3_fixes 逐列强化——Committer 期望的「原走过场断言已替换核实」= 新增 test_p2_2 断言 name/attrs/source_system/status/三类别名/curated 面/entity_conflicts 双面留痕，强度实质提升）。

## 2. 修复项判定表（对照 Committer 修复期望）

| 修复项 | 判定 | 关键证据 |
|---|---|---|
| **P2-1** 合并面完整语义（4 回归） | ✅ PASS | alias-only 覆盖层 manual 写入+curated_rev 记录（payload 空写 {}）；删空别名旧 manual·abbr 清空（先删后插面恒执行）；删空 definition payload 重写不残留；stale 仍条目级（unlink → curated/rev/manual 全清、事实列 name 不动）。**独立证伪**：仅 name+owner 极端形态（无 aliases 无 payload）→ 合并 succeeded、curated_json=`{owner}`、零残留（RP1a~h 8 断言） |
| **P2-2** 同键冲突同步实体保护 | ✅ PASS | core 预读剔除方案在码（sync.py L151-181——`relation_source=='curated'` 时预读 sem_entity_states 剔除 entity upsert/别名重建/**关系一并剔除**+stats.entity_conflicts）； coder 用例逐列断言。**独立证伪全链（RP2a~m 13 断言）**：冲突后实体 name/attrs/source_system/source/status/三类别名原样→原源（scenario_config）resync 实体不被污染→原源基数仍含键（`sem_active_source_keys` 含 dup.key）→**YAML 删除冲突条目后实体仍 active、stats.missing==0（Committer 点名的误 retire 链实证断裂）**→FTS 面：YAML 冲突词零残留、同步 name 正常命中 |
| **边界 1** JSON Schema 条目级校验 | ✅ PASS（附 N6） | entry.schema.json 驱动（`_schema_errors`：jsonschema 库优先+手写子集回退）；**双路径独立验证**：jsonschema 4.26.0 在场路径拦违例（owner required/aliases 元素类型，文件定位）+ `sys.modules` 注入 ImportError 强制回退路径拦同批违例，双路径「文件+路径前缀」定位等价（RP3a~c）；手写补充面不弱化（schema 通过但 owner 缺仍被手写规则拦）；CI 脚本同步。**schema 坏 JSON → CI error 逐条不崩溃**（RP3d，fail-closed）。schema 语义非法行为见缺陷清单 N6 |
| **边界 4** L0/owner 入 curated | ✅ PASS | `curated_payload` 补 l0（仅 True 落键）/owner；l0=true 条目落 `{"l0": true, "owner": ...}`；**非 L0 条目无 l0 键（键缺席非 False，RP10）**——m2s-4 消费面可读 |
| **N2** T-S4 恢复步关系断言 | ✅ 已修 | test_sync_02_guard 恢复步②新增 `sem_relations ... == "active"` 断言（diff 核实，双臂实跑） |
| **N3** report_center 分页对称 | ✅ 已修 | test_report_center_paging（PagingTransport cursor 翻页拼全量，与 scenario_config 同构） |
| **N4** sync.py 注释 | ✅ 已修 | 关系 upsert 段补「已 active 行在端点 missing 窗口保持 active（UPDATE CASE 不降级）——展开不可见、超期级联收口」——与我 R1 建议措辞一致 |
| **P3-1** abbr 免拦 | ✅ PASS | 合并侧仅 manual 套 `_alias_blocked`；1 字缩写「税」写入零冲突（coder 用例） |
| **P3-2** 别名 UNIQUE 双防线 | ✅ PASS | 合并侧预检（existing name/code/sync norms+条目内 seen_norms → skip+冲突记录）+ store `ON CONFLICT(org_id,entity_id,alias_norm) DO NOTHING`（sqlite 带靶/pg 无靶等价）+ CI 查重（同条目 aliases·abbr 撞 → error）。**残余竞态独立注入（RP4）**：store 直调 manual 同 norm 撞既有 name 别名 → 不炸、既有 name 不被顶替 |
| **P3-3** sensitivity 直写三段 | ✅ PASS 双方言 | restricted→显式 normal→缺省 normal 三段（coder 用例 [pg] 臂实跑——门禁 pg 参数化 395 含）；sqlite 直写/pg `COALESCE(x,'normal')` 双方言等价；stale 清理不动覆盖层外值。**泄漏联动独立证伪（RP5a~d）**：YAML restricted → search 零命中+get_entity 404 面 → 回 normal 后恢复可见（T-S9 全程无泄漏） |
| **P3-4** switch 严格递增 | ✅ PASS 双方言 | sqlite switch 改 `MAX(CURRENT_TIMESTAMP, MAX(activated_at)+1s)` 聚合形式（NULL 行为正确）；pg `GREATEST(now, max+interval '1s')`（PG GREATEST 忽略 NULL——首建正确）。**重跑 R1 P7 场景+扩链（RP6a~e）**：switch→reactivate→switch→reactivate→switch 同 org 三重链 current 每步跟随最新 ready、全表 4 行 activated_at 严格递增零并列 |
| **P3-5** reactivate 返回值消费 | ✅ PASS | build.py False → current 同 rev 则 skipped（reactivate-race-lost）/否则 RuntimeError——不虚报 ready；coder monkeypatch 竞态注入用例断言 current 仍是 r2、行保持 ready |
| **P3-7** .git 跳过 | ✅ PASS | 点目录任一层 `startswith(".")` 跳过；**三次变动 rev 不动+内容文件仍换 rev**（RP7a~d） |
| **P3-8** CI 三缺口 | ✅ PASS | ①全局 id 唯一（条目+内嵌字段聚合，**双文件定位** RP8b：`concepts/a.yaml/concepts/b.yaml`）②match_mode 枚举 ③related_to src 限 concept——三用例在库+探针复核 |
| **P3-11** 配置接线 | ✅ PASS | `.env.example` 补五源样例（yaml endpoint/webhook_secret）+ `LATTICE_SEM_L0_TOKEN_BUDGET`；CI 脚本缺省读 env、flag 优先；Settings.semantic_l0_token_budget 同源。**环境变量三态（RP9a~c）**：无 env 缺省 1500 放行 / env=1 拦截 / flag 覆盖 env 放行 |
| **P3-10** 永久测试补口 | ✅ PASS | ①store CASE 直调（绕过 core 预过滤：retired/missing 端点 INSERT 落 missing+非 active 行 UPDATE 不复活）②yaml 生产路径全链（run_sync_task：sources 解析→post_run→dim_map→FTS seg_text 断言→构建任务自动投递→close）——均双臂实跑 |

## 3. 独立脚本清单与结果

| 脚本 | 内容 | 结果 |
|---|---|---|
| probe_r2.py | RP1~RP10 共 48 断言（详见判定表「独立证伪」列） | **47 PASS / 1 定性后转 N6**（RP6a 首轮为探针 guard 误踩，修正后过） |
| probe_r2b.py | RP3e 干净进程定性：schema 有效 JSON 但语义非法（`{"type":"not-a-type"}`）| **CRASH: jsonschema.exceptions.SchemaError 未捕获**（check_schema 抛错面——转缺陷清单 N6） |
| probe_r2c.py | 同场景回退路径行为 | FALLBACK NO-CRASH（未知关键字忽略优雅通过）——双路径不对称归入 N6 |
| pg 臂定向复跑 | test_r2_m2s3_fixes + test_sync_06 + test_sync_02 双臂 | **72 passed** ✓ |

## 4. R1 观察项对账

| R1 项 | R2 处置 | 核验 |
|---|---|---|
| N1 webhook 重放（信息项） | 维持不补（用户裁定） | ✅ 码未动（diff 无 webhook 改动）——符合裁定 |
| N2 T-S4 恢复断言 | R2 顺手 | ✅ 断言在场（见判定表） |
| N3 report_center 分页 | R2 顺手 | ✅ 对称用例在场 |
| N4 sync.py 注释 | R2 顺手 | ✅ 补句措辞与建议一致 |
| N5 每日兜底调度 | 登记 G-19 | ✅ docs/known-gaps.md 新增 G-19（状态/问题/对冲〔cron 运维路径〕/重开条件 M2-S4）+ `_m2-plan.md` m2s-4 行挂账「窗口/幂等/与 webhook 去重口径」——登记完整 |

另：Committer R1 指正我 R1 报告「仅 curated_rev 变不新 rev」表述有误——**接受**（yaml_rev 已入 dict_rev，任何内容哈希变更必新 rev；R1 测试断言本身正确，系我报告措辞不精确）。

## 5. 缺陷清单

**FAIL（IMPL_BUG / CASE_BUG）：无。** 门禁零失败、修复项全数落地且经独立证伪。

**新观察项（不阻塞，供监督侧裁量）：**

- **N6（P3 级，CI 工具健壮性）**：`_schema/entry.schema.json` 为**有效 JSON 但语义非法**（如 `{"type":"not-a-type"}`）时——jsonschema 在场路径 `check_schema` 抛 `SchemaError` 未捕获 → `validate_corpus` 崩溃 → `sem_yaml_ci.py` 以 traceback 退出（exit 1）；手写回退路径则优雅通过（未知关键字忽略）。**fail-closed 方向成立**（CI 非零退出仍拦合并），但违背「可定位错误」体验且双路径行为不对称。建议 R3 顺手（`check_schema` 包 try → `Issue("error", schema 文件, ...)`，约 5 行）或随下段收编。同类微瑕：`sem_replace_manual_aliases` 的 `inserted += 1` 在 ON CONFLICT DO NOTHING 后无条件计数（纯统计口径，stats 用 `len(alias_rows)` 无行为影响）。

## 6. 与 coder 自测对账

门禁数字逐项一致（1206+1 双模式 0 skipped、pg 臂 428=395+33、+37 构成逐文件吻合）；R2 轮次记录申报的 P2×2/边界 1/边界 4/N2·N3·N4/P3 八项全部在码在测，无虚报；「TDD 红灯 18 failed（3 即绿=覆盖缺口补用例）」属历史过程不采信也不需要；登记项（P3-6/12）确认未做但已落 docs 注记——与 spec_confirm 裁定范围一致。

---

**结论：testVerdict = PASS**。R1 Committer NEEDS_CHANGES 全部承诺修复项（P2×2 + 边界 1/4 + N2/N3/N4 + P3 顺手八项）逐条复验通过，Committer 点名的误 retire 链、走过场断言、双路径 Schema 校验、残余竞态四类高风险面均经独立证伪闭合；R1 观察项五条对账无遗漏；零回归零删除。新增观察项 N6 一条（P3 级、fail-closed 方向不破）随报告移交监督侧裁量。临时产物已清理（外部临时目录删除、无残留进程、仓库零残留、HEAD 未动）。

</details>

<details>
<summary>R2 Committer 报告全文（2026-10-31 12:55，reviewVerdict=NEEDS_CHANGES·P3 收尾级）</summary>

# m2s-3 R2 Committer 复审报告

**基线核对**：HEAD = `1d27e32`（= testedSha = 检查点 R2 终态）；上一轮 `reviewedSha=null`（R1 审查对象 e401d37，report 见检查点「最新验证意见原文」R1 Committer 块）；本轮 diff `e401d37..1d27e32` = **14 文件 +1168/−58**，与检查点 R2 filesChanged 一致（含 `.env.example`/scripts/build/sync/yaml_corpus/yaml_merge/store 双方言/3 个测试文件 + docs 批 G-19/_m2-plan/检查点）。工作区仅监督侧 `supervised-coding.md` + 检查点两文件，**代码面零变动**；检查点内 R2 记录为监督侧追加（提交版本未含 R2 coder/tester 记录）✓。

**门禁采信**：Tester 独立复跑 1206+1 双模式 0 skipped、pg 臂 428=395+33。我核对：新文件 21 函数 → 15 双臂×2 + 6 单臂 = **36**，+ test_sync_06 新增 1 = **+37**；1169+37=1206 ✓；pg 参数化 +15（15 个双臂函数）= 428−413 ✓。本轮 shell 未复跑 pytest（角色限制），采信 Tester 输出。

## 一、R1 意见逐条处置核对（复审主体）

### P2-1 合并面完整语义 — ✅ 功能修复到位，⚠️ 一处回归测试空转

| R1 修复期望 | 处置 | 证据 |
|---|---|---|
| corpus 每个 active 目标产出一行 | ✅ | `yaml_merge.py` 删除两处前置跳过；`curated_rows.append` / `alias_rows.append` 均无条件（active 校验之后） |
| payload 空写 `{}` | ✅ | `json.dumps(payload...)`；`curated_rev` 仍记 rev |
| 别名空产出行清空旧 manual/abbr | ✅ | `sem_replace_manual_aliases` 先删后插；空 pairs 只删不插 |
| stale 仍条目级 | ✅ | `sem_clear_stale_curated` 未改；`keep_entity_ids` 仍为 corpus 解析集 |
| 4 回归强度 | **3 真 1 空** | `test_r2_m2s3_fixes.py:114`「删空别名」用例未先做一次带别名的 merge：fixture 直接覆盖 t.yaml 后单次 merge，`_manual_norms == set()` **在 R1 缺陷代码下同样通过**（无旧别名可清）——空转（见 P3-2） |

补充核实：`existing_alias_norms` 预检（name/code/sync）+ `seen_norms` 面正确；sensitivity 现按 YAML 当前值直写（条目在场未声明 → normal），与 P3-3 裁定一致；`test_p3_3_stale_clear_keeps_non_corpus_sensitivity` 明确记录「条目整体消失不回退 sensitivity」（规则表第 8 行只清 curated/别名——合理，登记级观察）。

### P2-2 同键冲突同步实体保护 — ✅ 方案合理、破坏面逐列断言、误 retire 链代码面核实断裂

- **方案选择**：core 预读剔除（`sync.py:151-183`）相比 store 层方案更合适——冲突语义（规则表第 3 行）属编排面、store 保持通用；且「写入前剔除」避免对同步实体产生任何写入（name/attrs/parent/source_system/status/别名全不动），比 store 层「跳过 UPDATE」更彻底。仅 yaml 源多一次 `resolve_entity_ids`+`sem_entity_states` 读，成本可接受。未发现绕过路径（`relation_source=='curated'` 仅 yaml 适配器设置；生产/测试均走真实 YamlRepoAdapter）。
- **断言替换**：新用例 `test_r2_m2s3_fixes.py:156-195` 逐列断言 name/attrs_json/source_system/source/status + name/code/sync 三类别名 + manual 未写入 + curated 空 + `entity_conflicts`/`curated.conflicts` 双面留痕 —— 实质替换 R1 的 `source` 单列走过场断言。
- **误 retire 链（代码面独立核实，非仅采信 Tester）**：冲突键从未进入 yaml 的 `source_system='yaml'` 基数（预过滤先于 upsert，且同步实体 source_system 不被改）→ 后续 YAML 删除冲突条目时，`active_keys - snap_keys` 不含该键（它本不在 yaml 基数）→ 不标 missing；merge stale 清理因 `curated_rev IS NULL` 不选它；FTS/别名重建不含它（预过滤后不在 upsert 批次）。**链路断裂成立**。旧 R1 弱用例 `test_yaml_02_merge.py:161-174` 仍在（仅断言 source，已由新用例覆盖）——建议顺手强化/删除（P3，可不做）。

### 边界 1 JSON Schema 条目级校验 — ✅ 主体到位；⚠️ N6 + 回退路径永久覆盖缺口

- `yaml_corpus.py:307-325` `_schema_errors`：jsonschema 库优先、ImportError 回退手写子集；`validate_corpus:385-407` 按 `_schema/entry.schema.json` 逐条校验；CI 脚本同步；手写结构规则保留（schema 通过但 owner 缺仍拦——`test_b1` 验证）。✓
- **缺陷**：① 有效 JSON 但语义非法的 schema（`{"type":"not-a-type"}`）→ `check_schema` 抛 `jsonschema.exceptions.SchemaError` **未捕获**，`validate_corpus` 崩溃、CI traceback 退出（fail-closed 但非「可定位错误」）；② 回退路径对同一 schema **优雅通过**（未知 type 被忽略）——双路径不对称、零依赖环境门禁静默削弱；③ `validator_for` 检出校验器后仍硬编码 `Draft202012Validator(schema)`（`$schema` 非 2020-12 的合法 schema 可能误抛 SchemaError）。→ **N6**。
- 回退路径、schema 非法场景均只有 Tester 探针覆盖，**无 in-gate 永久用例**（`test_b1` 只走 jsonschema 在场路径）。

### 边界 4 L0/owner 入 curated — ✅

`curated_payload` 仅 `l0` True 落键（非 L0 键缺席，非 False）、owner 落键；`test_b4` + `test_p2_1_alias_only`（payload 空亦含 owner）+ `test_p3_10_yaml_production_path`（生产路径 payload 断言）覆盖。`l0.yaml` 额外文本仍未持久化（spec_confirm 只裁 L0/owner 入 payload；m2s-4 若需 l0_extra 须回读 YAML 仓或补列）——登记级观察，不阻塞。

### N2 / N3 / N4 — ✅ 全部到位

- N2：`test_sync_02_guard.py:173-177` 恢复步补关系回 active 断言——真实（run① 关系已 missing，run② 恢复）。
- N3：`test_report_center_paging` 与 scenario_config 同构对称用例。
- N4：`sync.py:235-240` 注释精确补「已 active 行在端点 missing 窗口保持 active（UPDATE CASE 不降级）——展开不可见、超期级联收口」，与建议一致。

### P3 八项 + P3-13 — ✅ 逐项核实

| 项 | 结论 |
|---|---|
| P3-1 abbr 免拦 | ✅ 仅 manual 套 `_alias_blocked`；1 字缩写合并写入（`test_p3_1`） |
| P3-2 UNIQUE 双防线 | ✅ 预检（`taken`+`seen_norms` skip+冲突）+ store `ON CONFLICT DO NOTHING`（sqlite 带靶/pg 等价）+ CI 同条目查重 |
| P3-3 sensitivity 直写 | ✅ 双方言直写（sqlite `:sensitivity`/pg `COALESCE(x,'normal')`）；restricted→normal→缺省 normal 三段测试 |
| P3-4 switch 严格递增 | ✅ sqlite 子查询/pg `GREATEST` 与 reactivate 同款；三重切换链 current 跟随 |
| P3-5 reactivate 返回值 | ✅ False → current 同 rev skipped / 否则 RuntimeError；不虚报 ready、不写脏 failed 事件（ready 行 `sem_fail_build` 零生效） |
| P3-7 `.git` 跳过 | ✅ 点目录任一 rel.parts 命中即跳过；.git 变动 rev 恒定、内容变更仍换 rev |
| P3-8 CI 三缺口 | ✅ 全局 id 唯一（条目+字段聚合、双文件定位）/match_mode 枚举/related_to src 限 concept |
| P3-11 配置接线 | ✅ `.env.example` 五源样例+L0 预算；脚本读同名 env、flag 优先；三态测试 |
| P3-10 部分 | ✅ store CASE 直调（绕过 core 预过滤、INSERT retired/missing 落 missing + 非 active 行不复活）+ yaml 生产路径（`run_sync_task` 全链含 FTS 时效/构建投递/close） |
| P3-13 docstring | ✅ 双方言 `_expand_relations_thin` 均补「seed 过滤责任在消费方」 |

**残余**：ON CONFLICT 残余竞态（store 直调）只有 Tester 探针；`inserted += 1` 在 DO NOTHING 后无条件计数（stats 微瑕、无行为影响）；R1 既有的 `test_migration_0007_backfills_activated_at` 名实不符、`test_concurrent_same_rev_single_ready_event` 为顺序调用（本轮 R2 范围未要求，登记级）。

### 登记项合规 — ⚠️ G-19 ✓，**P3-6/P3-12 docs 未落笔（与检查点/Tester 申报不符）**

- **G-19**：`docs/known-gaps.md:204-210` 已落（状态=已接受/M2-S4 承接；问题/对冲=运维 cron 调 `POST /semantic/sync/{adapter}`/重开条件=窗口/幂等/与 webhook 去重口径）——与我的 N5 裁定一致；`_m2-plan.md` m2s-4 行挂账 ✓。
- **P3-6（FTS 升级回填口径 RUNBOOK 一句）**：**未落**——`RUNBOOK.md` 自 m2-3（6633914）起未修改，全文无语义层/`sem_search_texts` 相关句；`git diff e401d37..1d27e32 -- RUNBOOK.md` 空。
- **P3-12（webhook body 上限）**：**未落**——known-gaps 仅新增 G-19，无 P3-12 条目；全仓 docs 无该注记。
- 检查点 R2 记录「登记项不做（P3-6/12 已落 docs）」与 Tester「确认未做但已落 docs 注记」**与仓库事实不符**。属监督侧落笔遗漏（非 coder 缺陷），需在交付前补：RUNBOOK 补 0007 升级注意（`sem_search_texts` 不回填 → 既有实体在下一次对应源 sync 前 FTS 第三层空；升级后触发一次各源 sync 回填；前两层不受影响）；known-gaps 新增 webhook 请求体上限条目（公网入口验签前读 body、内存放大，部署侧反代/网关限流兜底）。
- 另：known-gaps 条目总览表仍止于 G-16（G-17/G-18/G-19 未入表）——m2s-2 起既有债，建议归档批顺手补。

### 回归面 — ✅

`git diff e401d37..1d27e32 -- tests/` **无 `def test_` 删除/修改既有断言**、无 skip/xfail 新增；R1 既有断言未放宽；测试文件变更仅 test_sync_02（+5 行断言）、test_sync_06（+1 用例）、新 test_r2（21 函数）；迁移水位无再顺延；chore 批（G-19/_m2-plan/检查点）原样、`supervised-coding.md` 未入库 ✓。

## 二、问题清单（本轮）

### P1
无。

### P2
**无代码级 P2 遗留**——R1 P2×2、边界 1/4 的代码修复均核实到位（P2-1 唯一问题是回归测试空转，属测试质量 P3；P2-2 全链成立）。

### P3（R3 收尾级 / 登记级）

1. **N6（建议 R3 修）** — `yaml_corpus.py:307-325、385-407`：schema 语义非法时 jsonschema 路径 SchemaError 未捕获（traceback），回退路径优雅通过（双路径不对称）；`validator_for` 检出类未使用（硬编码 Draft202012）。修复：`entry.schema.json` 加载时**一次性**自校验（try `check_schema` → `Issue("error", schema 文件, ...)` + 置 entry_schema=None；回退路径补最小 schema 合法性检查：`type` 值须为已知类型/`required` 为字符串数组等），`_schema_errors` 改用 `validator_cls(schema)`；非对象 schema 文件亦报 error。约 10 行 + 2 用例。
2. **P2-1 回归空转（建议 R3 修）** — `tests/test_r2_m2s3_fixes.py:114-121`：删空别名用例未先做一次带别名 merge，R1 缺陷下同样通过。修复：merge 一次（写入别名）→ 覆盖 t.yaml 去掉别名 → 再 merge → 断言清空。约 3 行。
3. **误 retire 链永久化（建议 R3 顺带）** — `test_r2_m2s3_fixes.py:156-195`：删除冲突 YAML 条目后断言同步实体仍 active + `stats.missing==0`（当前仅 Tester 探针覆盖；代码面已核实断裂）。约 5 行。
4. **JSON Schema 回退路径永久用例（建议 R3 顺带）** — 强制 `sys.modules["jsonschema"]=None` 跑同批违例，断言双路径定位等价（当前仅探针）。约 15 行。
5. **监督侧 docs 登记（非 coder，交付前必办）** — P3-6 RUNBOOK 一句、P3-12 known-gaps 条目；并更正检查点/Tester「已落 docs」表述。
6. **登记级观察（不必本轮）** — ① 旧 `test_rule_pure_collides_with_synced_entity` 仅断言 source（已被新强用例覆盖，可强化/删）；② `sem_replace_manual_aliases` 的 `inserted += 1` 未计 ON CONFLICT 跳过（stats 微瑕）；③ migration backfill/concurrent 两测试名实（R1 遗留）；④ 删除整个覆盖层条目后 sensitivity 不回退最后声明值（测试已记录为有意，建议 known-gaps 口径化）；⑤ merge 侧非法 sensitivity 静默归 normal（CI 拦；fail-open 方向注记）；⑥ known-gaps 总览表补 G-17~G-19。

## 三、N6 裁定：**值得 R3（建议做，范围极小）**

理由：
1. N6 是**本轮新增门禁特性**（边界 1）的缺陷，不是历史债——`check_schema` 崩溃使 CI 无法给出「可定位错误」（TC-YAML-04 预期），回退路径对非法 schema 静默通过则使「零依赖可跑」的等价承诺在无 jsonschema 环境下失效（门禁被静默削弱）；`validator_for`/Draft202012 错配是同特性内的确定性问题。
2. 修复约 10 行 + 2 个用例；无产品行为面改动，回归风险低。
3. round=2/maxRounds=3 尚余一轮；同轮可顺带修 P2-1 空转测试（3 行）与误 retire 永久断言（5 行）——这三项都直接关系「R1 阻塞项的可回归性」，用满一轮换干净门禁值得。
4. 若监督侧以进度优先选择不跑 R3：代码面无 P1/P2，可改判 APPROVED（reviewedSha=1d27e32），但 N6/测试空转/回退路径覆盖须登记下段，且 **P3-6/P3-12 docs 必须先补**（可走 docs-only chore，按 m2-2 先例更新 reviewedSha）。

## 四、关键面显式结论

| 面 | 结论 |
|---|---|
| P2-1 合并面 | 功能 ✅（每目标产行/空 payload `{}`/空别名清空/stale 条目级）；回归测试 1/4 空转（P3-2） |
| P2-2 同键冲突 | ✅ 方案合理（core 预读剔除）；逐列断言强；误 retire 链代码面断裂成立；旧弱用例残留（登记级） |
| 边界 1 JSON Schema | ✅ 双路径+CI+手写补充面；⚠️ N6（schema 非法崩溃/回退静默通过/validator 错配）+ 回退无永久用例 |
| 边界 4 L0/owner | ✅ True-only 落键、非 L0 键缺席、owner 落库 |
| N2/N3/N4 | ✅ 断言/用例/注释均到位且非空转 |
| P3 八项 + P3-13 | ✅ 全部在码在测（ONS CONFLICT 残余竞态仅探针、inserted 微瑕——登记级） |
| G-19 + m2s-4 挂账 | ✅ 落笔与 N5 裁定一致 |
| P3-6/P3-12 登记 | ❌ docs 未落（RUNBOOK/known-gaps 均无）；检查点/Tester 表述失实——监督侧补 |
| 安全面 | 本轮未动 webhook/鉴权；schema 校验仅本地仓库内容（CI 面）；无新外部输入面 |
| 分层纪律 | core/semantic 仍零 SQL（schema 校验为纯逻辑）；store 双方言同构；auto_entities 未动 ✅ |
| 回归/门禁 | +37 构成吻合、1206+1/428 双模式 0 skipped（采信 Tester）、零删除零弱化、R1 断言未放宽 ✅ |
| 提交卫生 | 14 文件与 stat 一致；chore 原样（含检查点未由 coder 编辑）；工作区无代码残留 ✅ |

## 五、交付就绪判定

**reviewVerdict: NEEDS_CHANGES（P3 收尾级 R3；无 P1/P2 代码缺陷）**

- reviewedSha **不置位**（1d27e32 未通过本轮）。R3 最小范围：N6（schema 自校验 + 回退对称 + validator_cls）+ 问题清单 2/3/4 三个测试补强；监督侧同步补 P3-6/P3-12 docs 登记。
- R3 通过后：reviewedSha=testedSha=HEAD（三一致）→ 交付期 PR + evidence manifest（manifest 双 SHA=最终 HEAD、rounds=3、specRulings、handover）→ `gh pr review` 留痕 → 待用户合入。
- 当前**未到交付门**：无 PR、evidence manifest 未生成；`status=testing`/round=2 由监督侧维护（检查点只读，我未改动任何文件）。
- **CASE_BUG 裁定请求：无**。

**若监督侧选择「不跑 R3、直接 APPROVED」**：建议条件性放行——reviewedSha=1d27e32，N6/测试空转/回退覆盖登记 m2s-4 或维护段，P3-6/P3-12 docs 以 docs-only chore 补齐后更新 reviewedSha（m2s-2 先例）；但按本轮审查建议，用满剩余一轮做上述最小收尾更稳妥。

</details>

<details>
<summary>R3 Tester 报告全文（2026-10-31 13:18，testVerdict=PASS 收敛）</summary>

# task-knowledge-lattice-m2s-3 R3 独立终验报告（Tester）

**testVerdict: PASS**
**testedSha: f6cd5b226bde0aae10e560a6d0b9f54d43b603cc**（git rev-parse 实测，验证前后一致；工作区仅监督侧 supervised-coding.md + 检查点两文件既有改动，被测代码面零变动；检查点只读纪律遵守）

## 1. 门禁真实输出（独立复跑）

```
pg 臂用例收集数：428（[pg] 参数化 395 + PG 专用 33，> 0 ✓）
==== [pytest] uv run pytest -m 'not manual' -q ====
[pytest] OK：1209 passed, 1 deselected, 2 warnings in 195.70s
==== [pytest-O] uv run python -O -m pytest -m 'not manual' -q ====
[pytest-O] OK：1209 passed, 1 deselected, 3 warnings in 189.29s
GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
（pg 臂 428 条用例全实跑：[pg] 参数化 395 + PG 专用 33）
```

- **skip 核对**：双模式 **0 skipped**；`1 deselected` = TC-UI manual 走查（既定口径）——**任务范围内零 skip**。与 coder 申报（1209+1 / pg 臂 428 / +3 零回归）逐项一致。
- **+3 对账**：`git diff` 核实新增 test 函数恰 3 个（test_n6_invalid_schema_locatable_error_not_crash / test_n6_non_object_schema_reports_error / test_n6_fallback_path_symmetric——全 tmp_path 单臂）→ **+3** ✓（1206+3=1209）。
- **零删除零弱化**：`grep "^-.*def test_"` **空**；既有用例改动仅 test_p2_1 前序 merge 补强与 test_p2_2 追加永久断言（强度只增不减）。

## 2. 修复项判定表（对照 R2 Committer §二 1~4）

| 修复项 | 判定 | 关键证据 |
|---|---|---|
| **N6①** 加载一次性自校验 | ✅ PASS | **重跑 R2 probe_r2b 原崩溃场景**：`{"type":"not-a-type","required":"id"}` → 不崩溃（原 SchemaError traceback 消除）、`_schema/entry.schema.json` 可定位 error（RP-A1/A2）；entry_schema 置 None → 条目零 schema-violation 噪声（RP-A3）+ **回落态手写 owner 规则仍拦** no_owner.yaml（RP-A4——非静默零校验） |
| **N6②** 回退路径对称 | ✅ PASS | **重跑 R2 probe_r2c 原不对称场景**：jsonschema 注入 None 强制回退 → 同一非法 schema 同报可定位 error（`$: 未知 type 'not-a-type'（合法：[...]）`）——R2 双路径不对称消除（RP-B1） |
| **N6③** validator_for 实例化 | ✅ PASS | Draft202012 硬编码删除（diff 核实 `jsonschema.validators.validator_for(schema)(schema)`）；`$schema=draft-07` 合法 schema 不误抛（RP-C1）+ 校验仍生效（owner 类型违例 `owner: 42` 照拦，RP-C3）+ 合法仓零 error（RP-C2） |
| **N6④** 非对象 schema | ✅ PASS | `[1, 2]` → 可定位 error（RP-D，不崩溃） |
| **P2-1 空转修复真红** | ✅ PASS | 前序 merge 补强（写 manual+abbr+context 别名 → **前置非空断言在场**）；**变异真红核验（RP-G4）**：模拟 R1 缺陷（空别名行不到 store）→ 重新写别名→删空别名→清空断言**真失败**（残留 `{'mm','m别名'}`）——测试在 R1 缺陷代码下必红，恒真消除 |
| **误 retire 链永久断言** | ✅ PASS | test_p2_2 追加（unlink 冲突条目 → merge → `missing==0` + 实体 active）进门禁常跑双臂。**敏感度注入（RP-H）**：构造 R1 缺陷态（source_system='yaml' 入基数 + 5 filler 使 vanish=1/6≈17% 越过 guard）→ `missing=1` + 实体 missing——断言在缺陷态**真红**（RP-H4）、正常态绿（RP-H2） |
| **回退路径永久用例** | ✅ PASS | test_n6_fallback_path_symmetric：`monkeypatch.setitem(sys.modules,"jsonschema",None)` 强制回退——**与库路径实际输出独立比对**（违例文件集等价 `{'concepts/c.yaml','concepts/d.yaml'}` + name/l0 字段级命中）+ 回退侧对非法 schema 对称报 error——非 mock 自证 |
| **N6 附带** 合法仓不误伤 | ✅ PASS | RP-E1 合法 schema 仓零 error；RP-E2 违例条目字段级定位照拦 |
| **CI 脚本面** | ✅ PASS | RP-F：check_schema 失败 schema → **exit 1、stdout 含可定位 `[ERROR] _schema/entry.schema.json: schema 语义非法: ...`、stderr 无 Traceback** |

**docs 落笔核实**（R2 Committer「监督侧遗漏被抓」项）：RUNBOOK 0007 升级注意（P3-6——迁移不回填 sem_search_texts、升级后触发各源 sync）✓；known-gaps **G-20**（P3-12 webhook body 无上限）+ 总览表补 G-16 已收口/G-17~18 已收口/G-19/G-20 ✓——均在本批 diff 落库。

## 3. 独立脚本清单与结果

| 脚本 | 内容 | 结果 |
|---|---|---|
| probe_r3.py | RP-A~F 共 13 断言：N6 四子面（原崩溃/不对称场景重跑）+ draft-07 不误抛 + 非对象 schema + 合法仓零误伤 + CI exit 1 可定位输出 | **13 PASS / 0 FAIL** |
| probe_r3_mutation.py | 变异真红核验 9 断言：G（P2-1 R1 缺陷模拟→清空断言真红）+ H（误 retire 缺陷态构造→永久断言真红） | **9 PASS / 0 FAIL** |
| pg 臂定向复跑 | test_r2_m2s3_fixes 双臂（含三个 N6 新用例 + 补强用例） | **39 passed** ✓ |

**探针过程发现（正面）**：误 retire 链在「单实体 yaml 基数 100% vanish」形态下会被 **T-S2 删除比例保护第三层兜底**（aborted_guard 零写入）——真实触发需 vanish ≤20%（我的缺陷态构造据此用 5 filler 达成 17%）。误 retire 防护实际为三层：core 预读剔除（本修复）+ guard 比例保护 + FTS/展开侧无泄漏。防御纵深完整。

## 4. 缺陷清单

**FAIL（IMPL_BUG / TEST_BUG / CASE_BUG）：无。** N6 四子面、三测试补强真红、不误伤面、CI 可定位面全部闭合；R2 遗留观察项 N6 已清偿，登记级六项按裁定不做。

## 5. 与 coder 自测对账

门禁数字逐项一致（1209+1 双模式 0 skipped、pg 臂 428=395+33、+3 构成吻合）；R3 轮次记录申报的「N6 修复四子面 + 三测试补强」全部在码在测无虚报；TDD 红灯申报（SchemaError 崩溃实证/非对象零 error/回退不对称）与我在 R2 探针的原始发现一一对应，方向一致。

---

**结论：testVerdict = PASS**。R2 Committer §二 1~4 全部修复期望逐条复验闭合：N6 双路径对称且可定位（原崩溃/静默不对称双消除）、三测试补强经变异核验**真红非恒真**、误 retire 链永久断言进门禁且对缺陷态敏感、docs 三件落笔完整。+3 零回归零删除，任务范围内零 skip。R3 为最小收尾轮，无新增观察项。临时产物已清理（外部临时目录删除、无残留进程、仓库零残留、HEAD 未动）。

</details>

<details>
<summary>R3 Committer 报告全文（2026-10-31 13:44，reviewVerdict=APPROVED）</summary>

# m2s-3 R3 Committer 终审报告

**基线核对**：HEAD = `f6cd5b2` = testedSha = 检查点 R3 终态；本轮 diff `1d27e32..f6cd5b2` = **5 文件 +443/−22**（`yaml_corpus.py` + `test_r2_m2s3_fixes.py` + docs 批 RUNBOOK/G-20/检查点）与检查点 R2/R3 filesChanged 一致。工作区仅监督侧 `supervised-coding.md` + 检查点两文件，**代码面零变动**；检查点提交版本（531 行）为监督侧 R2 记录/spec_confirm/R3 范围原样，R3 coder/tester 记录仅在工作区（coder 未编辑）✓。

**门禁采信**：Tester 独立复跑 **1209+1 双模式 0 skipped**、pg 臂 428=395+33。我核对：+3 = 三个 N6 用例（全 tmp_path 单臂），1206+3=1209 ✓；pg 参数化面不变（R3 两处测试改动均为既有双臂用例内部补强）→ 428 ✓；R3 tests diff 无 `def test_` 删除、无 skip/xfail 新增、既有断言只增不减 ✓。

## 一、R3 修复逐项核对

### 1. N6 修复方案 — ✅ 方案成立（接受；边角见 P3-1）

| 子面 | 核对结论 |
|---|---|
| 加载一次性自校验位置 | ✅ `validate_corpus` 在 `_schema/*.json` 循环内对 `entry.schema.json` **加载时校验一次**（`yaml_corpus.py:443-448`）——schema 合法性是全局属性，避免逐条目 N 重复 Issue，也避免在条目循环中途崩溃；非对象 schema 单独报 error。合理。 |
| `entry_schema=None` 回落语义 | ✅ 非法 schema → 可定位 `Issue("error", "_schema/entry.schema.json", "schema 语义非法: …")` + 置 None；条目走手写补充面（owner/短词/引用等规则照跑）。**非静默**：schema error 使 CI exit 1；Tester RP-A4 实证回落态 owner 仍拦。语义正确。 |
| 回退路径对称 | ✅ `_minimal_schema_self_check` 覆盖 type 七值/required 字符串数组/enum·properties·items 递归；`test_n6_fallback_path_symmetric` 强制 `sys.modules["jsonschema"]=None`，与库路径**实际输出独立比对**（文件集 + name/l0 字段级命中 + 非法 schema 对称报 error），非 mock 自证。R2 的「崩溃 vs 静默通过」不对称在目标场景消除。 |
| `validator_for` 修复 | ✅ `_schema_errors` 改为 `validator_for(schema)(schema)`（`yaml_corpus.py:369`），删 Draft202012 硬编码；draft-07 合法 schema 不误抛且校验仍生效（Tester RP-C1/C3）。 |
| 崩溃场景复检 | ✅ 原 R2 崩溃输入（`{"type":"not-a-type","required":"id"}`）→ SchemaError 被捕、可定位 Issue、CI exit 1 无 traceback（Tester 重跑 RP-A/A2 + CI 脚本面 RP-F）。 |

### 2. 三测试补强 — ✅ 真红核验采信（Tester 变异）+ 代码逻辑独立确认

- **P2-1 空转修复**（`test_r2_m2s3_fixes.py:114-130`）：先写带 manual/abbr/context 别名的 t.yaml → merge → **前置在场断言**；再删空别名 → merge → 断言清空。R1 缺陷代码下第二次 merge 无 alias_rows → 旧别名残留 → 断言真失败（Tester RP-G4 变异核验：残留 `{'mm','m别名'}`）——恒真消除。
- **误 retire 链永久断言**（`:164-215`）：删 `dup.yaml` → `_merge` → `stats.missing==0` + 同步实体 active。R1 缺陷态（同步实体被 yaml 归属）下进 yaml 基数 → 删除触发 vanished → missing/guard 路径断言真红（Tester RP-H 用 5 filler 越过 guard、缺省形态由 guard 第三层兜底，双层敏感）；正常态绿。**防护纵深三层**（core 预读 + T-S2 guard + FTS/展开无泄漏）成立。
- **回退路径永久用例**（`:687-…`）：见上表；双路径独立比对，且覆盖「回退侧对非法 schema 对称报 error」——与 N6 修复互证。
- 三个 N6 用例（`:650/672/687`）在门禁常跑单臂，+3 对账吻合。

### 3. docs 批核对 — ✅ 请求项落笔；⚠️ 追加两处一致性/编排项（监督侧归档）

- **RUNBOOK 0007 升级注意**（`RUNBOOK.md:115`）：内容与 R2 §二.5 建议一致（迁移不回填 `sem_search_texts`→下次对应源 sync 前 FTS 第三层空→升级后触发各源 sync；前两层不受影响）✓。**编排 nit**：落点位于 §4.1 SQLite 备份代码块内，而同类 0004/0005 升级注意在 §3 迁移注意事项；且未明示 PG 同适用——建议终态归档挪/补一句（非阻塞）。
- **known-gaps G-20**（`:215-220`）：webhook 验签前 `request.body()` 无上限；对冲=私有化内网+反代限流；重开=公网直曝/网关无法限流——与 R2 P3-12 建议一致 ✓；总览表 G-20 行 ✓。
- **总览表**：G-16 已收口态 ✓、G-17/G-18 已收口 ✓、G-19/G-20 已接受 ✓——R2 §二.6 ⑥ 清偿。
- **⚠️ 追加发现（task D「known-gaps 状态回写归监督侧」未完整）**：① **G-15** 总览表（`:27`）与正文（`:180-185`）仍「已接受 / M2-S3 承接」——G-15 已随 m2s-3 R1 收口（关系级 missing + 端点过滤），应改已收口；② **G-17/G-18 正文状态**（`:196`/`:203`）仍「已接受」、重开条件仍「M2-S3 开工」，与总览表「已收口」不一致（G-16 正文已同步 ✓）。建议终态归档补齐（非代码问题）。
- **检查点 R3 记录**：coder 只读合规——提交版本未被 coder 编辑，R3 记录为监督侧工作区追加 ✓。

### 4. 登记级六项去向 — ⑥已清偿；①~⑤（+本轮新增⑦）**尚未落盘**，建议终态归档写入

检查点「遗留事项（跨任务移交）」仍 `- [ ] 无`；`_m2-plan` m2s-4 行仅 G-19。建议终态归档在检查点遗留节（必要时 _m2-plan 同步）落：

- ① 旧 `test_rule_pure_collides_with_synced_entity` 仅断言 `source`（已被 R2 强用例逐列覆盖）——可强化/删除（测试卫生，m2s-4/维护段）。
- ② `sem_replace_manual_aliases` 的 `inserted += 1` 未计 `ON CONFLICT DO NOTHING` 跳过——stats 微瑕、无行为影响，随下次维护顺手。
- ③ `test_migration_0007_backfills_activated_at` 名实不符、`test_concurrent_same_rev_single_ready_event` 为顺序调用（R1 遗留测试卫生）。
- ④ 覆盖层条目整体删除后 sensitivity 不回退最后声明值（测试已记录为有意；建议 known-gaps 或 m2s-4 权限面口径化）。
- ⑤ merge 侧非法 sensitivity 静默归 normal（CI 拦截；fail-open 方向注记）。
- ⑥ known-gaps 总览表 G-16 收口态·G-17~20 —— **R3 已清偿**。
- ⑦（本轮新增）R3 自校验回退/边界健壮性：`type` 数组（合法 JSON Schema）在回退侧 `stype not in frozenset` 会 TypeError；布尔子 schema/tuple items 被误判非法（回退 false positive）；`$schema` 非字符串时 `validator_for` 可能 TypeError（主路径未捕）——建议下段/维护段将 self-check 整体 `except Exception` 兜底 + 支持 type 数组/布尔 schema（零依赖回退路径 only；项目环境 jsonschema 在场、主路径不受影响）。

## 二、问题清单

### P1 / P2
无。

### P3（均为登记级/监督侧，非阻塞）
1. **回退/边界自校验健壮性**（见上 ⑦，`yaml_corpus.py:335` 等）：零依赖回退路径合法 schema 边角会崩/误报；主路径不受影响（项目 env 有 jsonschema）——登记下段。
2. **known-gaps 状态回写未完整**（G-15 / G-17·18 正文）——交付归档补（监督侧，非代码）。
3. **RUNBOOK 0007 note 落点**——建议挪至 §3 并注明双方言（文档 nit）。
4. **登记级 ①~⑤/⑦ 未落盘**——终态归档写入（监督侧）。

**maxRounds 判定**：上述全部为**登记级/文档级**，无代码阻塞项；round=3 已到顶，**不值得突破（不报 blocked）**——终审 **APPROVED**。

## 三、关键面显式结论

| 面 | 结论 |
|---|---|
| N6 四子面 | ✅ 一次性自校验可定位 error 不崩溃 / 回退对称 / validator_for 实例化 / 非对象 error；合法仓零误伤、CI exit 1 无 traceback（Tester + 代码复核） |
| 三测试补强 | ✅ P2-1 前置 merge 真红（变异核验）；误 retire 链永久断言进门禁且敏感；回退永久用例独立比对非自证 |
| docs 三件 | ✅ RUNBOOK 0007 / G-20 / 总览表 G-16 收口·G-17~20 落库；⚠️ G-15 与 G-17·18 正文状态待归档补齐 |
| 回归/门禁 | ✅ 1209+1 双模式 0 skipped、pg 428、+3 对账吻合；零删除零弱化；R3 仅 5 文件 |
| 检查点纪律 | ✅ coder 未编辑检查点；R3 记录为监督侧追加；`supervised-coding.md` 未入库 |
| 安全/分层 | ✅ R3 仅 CI 校验逻辑+测试+docs；无运行时/鉴权面改动；core/semantic 仍零 SQL |

## 四、交付就绪判定

**reviewVerdict: APPROVED**；**reviewedSha = f6cd5b2（= testedSha = HEAD，三一致）**。

**交付前置（监督侧，未完成前不进入交付门）**：
1. 检查点终态入库：`status=done`、`endReason`、`updatedAt`、R3 记录终态、filesChanged 终态、**遗留事项 ①~⑤+⑦**；`_m2-plan` m2s-3 行 done + 语义轨道「3/6」进度更新（当前行仍「下一段（待开工）」）。
2. known-gaps 状态回写补齐：**G-15**（index+body → 已收口）、**G-17/G-18 正文**状态/重开条件同步（index 已收口）；RUNBOOK 0007 note 建议挪至 §3 并注双方言。
3. 排除 `.opencode/agent/supervised-coding.md`（当前工作区 M、未入库）——终态归档 commit 不得包含。
4. PR（base=develop）+ evidence manifest：测试态双 SHA（testedSha=f6cd5b2、reviewedSha=f6cd5b2；若按 m2s-2 先例追加终态归档 docs-only commit，reviewedSha 更新为该 HEAD、testedSha 保持 f6cd5b2）；manifest 含 rounds=3、门禁三段数、specRulings、G-19/G-20 去向、handover ①~⑤+⑦；远端回读校验。
5. `gh pr review` 留痕 + 用户确认合入（合入动作不经手）。

**当前状态**：`status=testing`，无 PR、manifest 未生成——**代码面已就绪并批准；交付未就绪至上述归档/PR/manifest 完成**。CASE_BUG 裁定请求：无。

</details>
