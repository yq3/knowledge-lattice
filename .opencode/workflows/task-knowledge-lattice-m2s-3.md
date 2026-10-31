---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2s-3
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e705c4fa5ffeWafnHS77csoK2s
testerTaskId: ses_e70153663ffeGS58RkjFDskaAN
committerTaskId: ses_e6ffe99deffe8USoJKteWeyvrV
status: implementing
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: NEEDS_CHANGES
testedSha: e401d371124188918e151eb050a6c371a6915393
reviewedSha: null
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
  # + 本检查点 task-knowledge-lattice-m2s-3.md（R1 终态入库）
endReason: null
createdAt: 2026-10-31T09:44:28+0800
updatedAt: 2026-10-31T11:42:27+0800
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
- R1: coder 完成（ses_e705c4fa5ffeWafnHS77csoK2s，2026-10-31 11:02 监督侧核验存档；commit **e401d37**）——38 文件（13 新增 + 25 修改）。A 组：YAML 仓 schema/装载/CI 规则集（yaml_corpus + scripts/sem_yaml_ci.py——TC-YAML-04 全类拦截，owner/samples 逐条报）；yaml_merge 合并规则表逐行（TC-YAML-01/02 含恢复后自动生效、YAML 删除清 curated）；scenario_config/report_center/yaml 三适配器（既有 sync 流程复用——T-S2 guard+force/T-S4 宽限/白名单触发器零另起炉灶）；webhook（签名=服务身份，TC-YAML-03）；TC-SYNC-02 半句收口（metadata 引用面=YAML 显式∪tc 兜底）；TC-SYNC-06 值域映射表最小实现（dim_value_map.yaml——无专表 DDL 授权+注记）。B 组：G-17（curated_json 入快照+yaml_rev 入 dict_rev——definition 变更必新 rev）；迁移 0007 双方言（activated_at+source_system+FTS 表）；G-18（rev 回退重激活 current 跟随——activated_at 严格递增防同秒并列）；O-1（条件 upsert `WHERE status != 'ready'`——无 flap 双 ready 事件）。C 组全收：G-15（关系级 missing→宽限→retired+retired 端点 upsert 过滤〔missing 放行落潜伏态〕）；REST 读端点三件（semantic:read）；FTS 模糊索引升级（sqlite FTS5 外容表/pg tsvector——G-6 评分差异登记）；O-2（expand_relations nodes 含 seed depth=0）；describe 主路径 restricted 列级过滤；sync 路径 adapter.close 接线；测试维护三件（P3-2 强度/audit= 崩溃注入永久/3s 钳制永久）。自测：**门禁 GATE PASS 1169+1 双模式 0 skipped（pg 臂 413=380+33；1076+1→1169+1 零回归 +93）**；TDD 红灯先行（52 failed 首败 ModuleNotFoundError yaml_corpus）。design 出入注记 6 条见输出（webhook 服务身份 vs 任务书 semantic:admin 措辞/owner 全条目必填 vs 样例缺项/yaml rev=内容哈希本地形态/每日兜底未接调度/T-S4 关系中间态随 G-15 调整/映射表无专表 DDL）。

- R1: tester 完成（ses_e70153663ffeGS58RkjFDskaAN，2026-10-31 11:28）——**testVerdict=PASS**（testedSha=e401d37=HEAD）。独立复跑门禁 1169+1 双模式 0 skipped（pg 臂 413；+93 逐文件对账；**零删除零弱化**——def 删空集/水位顺延五文件收集数不变/'name'→'fts' 排序链强度等价/T-S4 潜伏态语义更新+恢复断言在）。**判定表全过**：TC-YAML-04 CI 规则逐条证伪（owner 逐条报/短词「税」context 放行「抵」拦/引用分级 error·warning）+CLI 直跑 exit 0/1；TC-YAML-02 规则表 10 行逐行（含恢复自动生效 TPL_GHOST 补断言）；T-S1 YAML 场景（abbr 跨源 resync/definition 修订原样探针证实）；webhook 三态+org 头 400+secret 零落日志双通道；G-15 全链（潜伏/不复活/恢复/级联覆盖+retired 端点双防线）；G-17 构造性成立；G-18 同秒严格递增（P7 注入 +2s）+O-1 真并发单 ready 事件 pg 臂实跑；REST 三件存在性零泄露；FTS 三层序双方言+refresh 三面时效+注入 8 形态；O-2/列级过滤/close 两路径/测试维护三件。独立探针 probe/probe2（47 断言）+pg 定向 49 passed。**观察项**：N1 webhook 无重放防护（design 未要求——同请求重放由幂等兜底）；N2 T-S4 恢复步关系断言建议；N3 report_center 分页对称覆盖；N4 sync.py 注释补句；**N5 五源均未接每日兜底调度（design §5.8「每天一次兜底」半句——m2s-1 起形态，需登记）**。design 出入 6 条逐条属实。报告全文见「最新验证意见原文」details 块（R1 Tester）。

- R1: committer 完成（ses_e6ffe99deffe8USoJKteWeyvrV，2026-10-31 11:40）——**reviewVerdict=NEEDS_CHANGES**（reviewedSha 不置位；HEAD=e401d37 不通过）。**P2×2**：P2-1 合并面跳过「仅别名」条目+替换语义不完整（alias-only 条目 manual/abbr 完全不写/删空别名旧别名残留/删空 definition 旧 curated 残留——违反规则表第 1 行无 payload 前置；修复=corpus 每个 active 目标产一行〔payload 空写 {}〕+3 回归）；P2-2 同键冲突同步实体先被 YAML 覆盖（run_sync upsert 先于冲突判定——name/attrs/parent/source_system/status/三类别名被改+移出原源基数→后续删除误 missing；测试仅断言 source 列=走过场；修复=curated 源实体写入前剔除既有 sync 键+记 conflict+补断言）。**P3×13**：①abbr 短词口径不一致（CI 不拦合并拦）②别名 UNIQUE 冲突整个 run 失败③sensitivity 只增不减（COALESCE）④activated_at 未来时间戳+同秒窗口（switch 未严格递增）⑤sem_reactivate_build 返回值未消费⑥0007 未回填 sem_search_texts⑦_content_rev 含 .git 抖动⑧CI 三缺口（全局 id 唯一/match_mode 枚举/related_to src）⑨L0/owner 未持久化（=边界 4）⑩永久测试缺口 5 处⑪.env.example+semantic_l0_token_budget 死配置⑫webhook body 无上限⑬O-2 seed 未滤 status/sensitivity。**边界 4 条上报**：①_schema JSON Schema 条目级校验是否本段（TC-YAML-04 字面）②webhook admin vs 服务身份（按 design 维持注记）③N5 每日兜底登记归属④L0 持久化归属（本段 vs m2s-4 回读）。**N 裁定**：N1 信息项不补/N2·N3·N4 R2 顺手/N5 登记 known-gaps+段挂账。关键面：G-17/18+O-1/G-15/webhook/FTS/REST/分层/水位全 PASS；Tester「仅 curated_rev 变不新 rev」表述有误（yaml_rev 已入 dict_rev——宁多勿漏非缺陷）。检查点元数据注：R1「38 文件」叙述与实际 35 非 chore+4 chore+1 检查点=40 不符（归档时更正）。报告全文见「最新验证意见原文」details 块（R1 Committer）。

**spec_confirm 裁定**（2026-10-31 11:42 用户拍板「按建议执行」）：边界 1=**(a) 升 P2 本轮补 JSON Schema 条目级校验**（TC-YAML-04 字面优先）；边界 2=维持 webhook 注记不改码（design 服务身份权威）；边界 3=**登记 G-19**（五源每日兜底调度——m2s-4 承接，known-gaps 已落笔+_m2-plan 挂账）；边界 4=**(a) 本段补 L0/owner 入 curated_json**（=P3-9 升格 R2）。**P3 裁量**：R2 顺手=P3-1/2/3/4·5/7/8/11+P3-10 部分（G-15 store 直调用例+yaml 生产路径用例）；登记=P3-6（FTS 升级回填口径 RUNBOOK 一句）/P3-12（webhook body 上限）/P3-13（O-2 seed 过滤 docstring 责任）。**R2 范围**：P2-1/P2-2+边界 1〔JSON Schema〕+边界 4〔L0/owner〕+N2/N3/N4+P3 顺手 8 项。status=implementing（round=2 不清零）。

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

</details>
