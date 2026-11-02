---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2s-1
target: knowledge-lattice
coderTaskId: ses_e7976667effehA1CY3ifgt1m3Q
testerTaskId: ses_e792d4720ffe9GSt0LfsJLs30o
committerTaskId: ses_e79119475ffe7rTHJALgfmxSxW
status: done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: b82a7239c981296e31a2e4ea597a11a569b68d85
reviewedSha: b82a7239c981296e31a2e4ea597a11a569b68d85
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [store/sqlite/migrations/semantic/0006_semantic_v1.sql, store/postgres/migrations/semantic/0006_semantic_v1.sql, core/semantic/constants.py, core/semantic/records.py, core/semantic/norm.py, core/semantic/__init__.py, core/semantic/adapters/__init__.py, core/semantic/adapters/template_center.py, core/semantic/adapters/metadata.py, core/semantic/sync.py, store/backend.py, store/sqlite/backend.py, store/postgres/backend.py, store/postgres/__init__.py, config.py, worker/runner.py, api/semantic.py, app.py, domain/audit_events.py, .env.example, tests/fake_semantic.py, tests/test_sem_00_layering.py, tests/test_sem_01_migrations.py, tests/test_sync_02_guard.py, tests/test_sync_03_flow.py, tests/test_sync_04_adapters.py, tests/test_sync_05_api_worker.py, tests/test_r2_m2s1_fixes.py, tests/test_r2_p2_fixes.py, tests/test_scaf_03_migrations.py, tests/test_v11_schema.py, tests/test_pg_scaff.py, tests/test_regress_m0a1_followups.py, docs/TEST-CASES.md, docs/known-gaps.md]
endReason: null
createdAt: 2026-10-29T15:16:09+0800
updatedAt: 2026-10-30T10:08:35+0800
---

# task-knowledge-lattice-m2s-1: M2-S1 基础段——sem_* 迁移落库 + SourceAdapter 协议与 template_center/metadata 适配器 + 同步流程（语义轨道首段）

## 任务原文

**需求**（design.md §8 M2-S1 第 1~2 项 + §4 sem_* DDL〔L510-637〕+ §5.8 同步流程与白名单表〔L834-859〕+ §3 core/semantic 结构；requirements FR-S1〔源端事实同步〕；D23 语义轨道——**与主线并行、延期不阻塞主线验收**。前置 m2-1 worker 任务框架与迁移框架已交付〔PR #2〕，m2-2 删除级联挂接点已就绪〔PR #3〕）：

**A. `migrations/semantic/` 双方言落库**（design §3 边界规则 3——`store/<dialect>/migrations/semantic/` 目录已建空，双方言各一份；迁移号接 docs 侧水位〔当前 0005〕按既有框架惯例取下一号）：

1. `sem_*` 全部六表 DDL：`sem_entities`（事实列/人工列分列——attrs_json vs curated_json；UNIQUE(org_id,type,key)；status active/missing/retired；sensitivity normal/restricted）/ `sem_aliases`（alias_norm 规范化列；kind 六值；UNIQUE(org_id,entity_id,alias_norm)——同别名指向多实体不加唯一）/ `sem_relations`（UNIQUE(org_id,src_id,rel_type,dst_id)）/ `sem_chunk_entities`（**刻意不加外键到 chunks**——T-S10 挂接点）/ `sem_builds`（dict_rev 含 embed_model 标签——#42 P1-2）/ `sem_sync_runs`（status 含 aborted_guard）
2. 触发器：`trg_sem_rel_check`（组织一致性 + 白名单端点类型双校验）/ `trg_sem_rel_noupdate`（端点不可原地改）
3. `sem_rel_types` 白名单种子：十种 rel_type × 端点类型组合**逐行按 §5.8 白名单表**（uses/has_field/backed_by/maps_to/has_item/child_of/derived_from/has_column/refers_to/related_to）；**三处一致**（代码常量 + 种子 + 触发器——TC-SYNC-09）
4. **org 作用域六表带 org_id、sem_rel_types 全局表无 org_id**（v0.6.1 口径）；pg 方言等价转换（IDENTITY/SERIAL 或序列、CHECK/触发器 plpgsql 同款语义、消息逐字同源沿既有惯例）

**B. SourceAdapter 协议 + 首批两适配器**（design §3 `core/semantic/adapters/`）：

1. **SourceAdapter 协议**：`fetch()` 只要求吐出全量快照记录（传输方式无关——列表接口分页拼装或导出文件）；**只读、幂等、不做增量**（全量快照语义是删除比例保护与 missing 检测前提，不可退让——#37 前置条件①）
2. **template_center 适配器**：模板/模板字段实体 + has_field/backed_by/maps_to 关系（快照形态由协议测试替身承载——真实源系统不可达，与 rerank 联调同性质环境依赖申报）
3. **metadata 适配器**：**只拉被 `backed_by`/`maps_to` 引用到的表与列**（+YAML 显式列出的——本段 YAML 未接入则仅引用面）+ table/column 节点 + has_column 关系；**不做全量镜像**（TC-SYNC-02）
4. **per-org 连接解析**：源系统连接配置（endpoint/凭证/超时）进 config.py per-org 结构（org→源系统实例，`fetch(org)` 据此解析——#37 前置条件③）；未配置 org 报配置错误不静默跳过（TC-SYNC-01）；MCP 传输形态为允许选项之一（FR-S1 v0.7——**本段不实现，协议传输无关**）

**C. 同步流程编排**（design §3 `core/semantic/sync.py`——§5.8 全流程）：

1. **删除比例保护**：快照相对**库内该来源 active 实体**（`source='sync' AND source_system=本适配器 AND status='active'`）消失比例 > 阈值（默认 20%，可配）→ run 置 `aborted_guard`、**零写入**、告警（T-S2——基数口径 #38 P2）
2. **分批 upsert**：每批 ≤1000 行提交（NFR-11 写锁治理）；批间失败重跑幂等（TC-SYNC-03）；**只写事实列**（name/attrs_json/parent_id/status/synced_at——从不写 curated_json 与 manual/abbr 别名，T-S1 列级分工机制互证）
3. **missing 宽限期状态机**：源端消失先标 `missing`（默认 7 天可配）→ 超期转 `retired` 且关系一并 retired；宽限期内恢复回 active（T-S4 机制面——S2 验收）
4. **别名三 kind 重建**：name/code/sync 先删后插（按新快照）；manual/abbr 原样不动（TC-SYNC-05）
5. **关系端点冲突不写入**：src/dst 端点库内不存在的关系跳过、`stats_json.conflicts` 含明细（src/dst/rel_type/原因——字段结构为测试约定 #40 P2）、整批其余不受阻断（TC-SYNC-04）
6. **run 记录与审计**：`sem_sync_runs` 落 running→终态与 stats_json（inserted/updated/missing/retired/conflicts）；`semantic.sync` 事件入 audit_outbox（事件常量已预留 domain/audit_events.py——TC-SYNC-07）
7. **维度属性可选携带**（对冲项 TC-SYNC-06）：快照携带的维度属性（如模板 region）落库、值域走显式映射表；**可见性不受影响**（实体维度 ACL 为 NFR-5 演进缝触发前不启用——载体形态：design §4 无 sem_entity_dims 专表 DDL，由 coder 按最小实现定（建议 attrs_json 内结构化承载或轻量绑定表），**口径注记 + TEST-CASES 回写归 supervised-coding**；填充率骤降告警（②形态）

**D. semantic_sync 任务类型接入**（m2-1 预留 executor 分发位兑现）：

1. `semantic_sync` 任务类型接入 worker executor 分发字典（错峰限速口径：分批即天然限速；夜间窗口配置项本段仅登记不强制）
2. **同步侧 REST 端点**（api/semantic.py 或既有文件归位——§6.2）：`POST /api/orgs/{org}/semantic/sync/{adapter}`（手动触发——semantic:admin 权限 + outbox）+ `GET /semantic/sync-runs` + `GET /semantic/builds`（查询端点——builds 本段可能恒空，m2s-2 接构建；TC-SYNC-08）
3. `semantic:admin` 权限角色（org_admin 兼任——§6.3 语义层权限：组织成员默认 semantic:read 本段查询端点可先用，admin 门控 sync 触发）

**E. chore 归档批**（独立 commit，沿 m2-2 `91b5804` 先例——消息 `[task-knowledge-lattice-m2s-1] chore: 流程归档`）：工作区监督侧文件原样入库——`docs/TEST-CASES.md`（v1.9）+ `AGENTS.md`（M2 进度行）+ `.opencode/workflows/_m2-plan.md`（新）+ `task-knowledge-lattice-m2-1.md`/`m2-2.md` 终态更新；**不含 `.opencode/agent/supervised-coding.md`**

**R2 范围增补**（2026-10-30 用户拍板 B1/B2/B3 后落笔）：

- **必修（Committer P2×2 + P3-1）**：P2-1 跨批次 parent_id 解析丢失（父行在前批已提交→本批子行 parent_id 写/覆写 NULL——修复=父键解析回查库内〔org 作用域〕或 sync 侧跨批 id 映射、父存在不得写 NULL；回归=600 templates+600 fields 跨 1000 边界断言 field.parent_id==template.id、二跑 updated=0、双后端）；P2-2 inline 兜底循环不认领 semantic_sync（修复=app.py `_loop` 增 run_once(task_types=("semantic_sync",))+预置 pending→兜底一轮→done 测试+两处 docstring 修正）；P3-1 `_worker_env` 补映射 LATTICE_SEM_DIM_ALERT_BASELINE/DROP 两键（N1 合并）+roundtrip 断言覆盖全部 LATTICE_SEM_*
- **B2 force 放行（用户拍板落实现）**：`POST sync/{adapter}?force=true`（semantic:admin+outbox 事件注记 forced）——run_sync 增 force 参数跳过删除比例保护、stats_json 注记 forced、gate 恢复路径（引用面合法收缩>阈值的运维路径）；TEST-CASES T-S2 v1.9.1 已回写口径——补 force 用例（force 放行 aborted_guard 场景生效、stats.forced=true、outbox 记录）
- **随 R2 择机收（Committer 建议，coder 自行判断纳入）**：P3-2 finished_at 取实际完成时刻（保留可注入 finish_now）；P3-3 关系/别名批边界补 should_continue 存活检查（m2-1 阶段边界口径）；P3-5 阈值校验（dim_alert_baseline/drop ∈[0,1]、batch_rows 上界或显式允许覆盖）；P3-6 测试加固（curated_json/sensitivity/curated_rev 同步前后逐字节回归、test_metadata_adapter_http_shape 改名、build_adapter 默认分支+N4 场景、顺序偏差防回退用例、TC-TASK-06① 故障隔离断言、SEM_ENTITY_TYPES==DDL CHECK 九值自动化断言）；P3-4 协议 create_task 签名补 payload docstring；P3-7 触发端点 resolve_source_config fail-fast 4xx（与 B2 force 端点同文件顺手）；P3-8 advance_status 跨源推进口径 docstring 显式声明
- **登记不修（已落 known-gaps）**：G-15 关系级消失（B1——M2-S3 承接）；G-16 触发侧两事务（N2——M2-S2/S3 承接）；N3 半句归 m2s-3（TEST-CASES v1.9.1 已注）
- **docs 批随 R2 commit 入库（coder 原样 commit）**：docs/TEST-CASES.md（v1.9.1）、docs/known-gaps.md（G-15/G-16）

**口径与边界**：

- **语义层用例自本段起双后端参数化**（TEST-CASES v1.3.2 拍板③——T-S2/T-S3/TC-SYNC 组 [pg] 参数化；pg 臂计入收集数）
- **分层纪律**：core/semantic 与 core/docs 包级互斥（import-linter 执法）；SQL 全部下沉 store/<dialect>（SemanticBackend 协议既有种子：upsert_entities_batch/advance_status/save_build 等——m0b-1 落的 5 方法签名按需扩展，双方言实装）；**auto_entities 识别钉 api/mcp 层**（本段无识别面）
- design/requirements 正文**禁改**（sem_* DDL 以 §4 为准——实现问题走测试用例与 issue）；TEST-CASES/known-gaps 回写由 supervised-coding 落笔
- scenario_config/report_center 适配器与 YAML 链**不在本段**（m2s-3）；AC 自动机/构建/三工具**不在本段**（m2s-2）；打标/untag 对账**不在本段**（m2s-5）
- 真实源系统不可达：适配器以协议测试替身验收（fixtures fake——沿 fake_providers 惯例），HTTP/MCP 真实联调环境依赖申报（同 rerank 联调先例）
- commit 格式 `[task-knowledge-lattice-m2s-1] R<n>`，develop_opencode 分支（先 ff 至 origin/develop=27d2a17），commit 前同步 origin/develop，不 push
- 新测试文件模块前缀命名（sem_/sync_/s2e_ 等），新建前 `git ls-files tests/` 查同名
- 门禁基线 **825+1 双后端双模式 0 skipped**（m2-2 终态）——零回归硬约束

**验收标准**：

- **T-S2 删除比例保护**：空快照/少 30% → aborted_guard 零写入（逐行 diff 为空）+ 告警；少 10% → 正常执行、消失实体转 missing（双后端）
- **T-S3 同步幂等**：同快照二跑 inserted/updated/missing 均 0（synced_at 刷新不计入）
- **TC-SYNC-01~09 全组**：per-org 解析 / metadata 只拉被引用 / 分批单事务 / 冲突不写入 / 别名三 kind / 维度携带对冲 / run+outbox 审计 / 手动触发权限矩阵（admin 200+普通成员 403+查询可见性）/ 迁移落库与白名单三处一致（双后端）
- T-S4 机制面（missing 标记/宽限恢复/超期 retired 关系联动——机制单测；S2 验收句不收口）
- semantic_sync 任务类型端到端（手动触发 → worker 执行 → sync-runs 可查）
- chore 归档批入库
- 门禁 825+1 起、双后端双模式全绿 0 skipped（新增用例计入、pg 臂含语义参数化）

## 需求确认

- [x] 用户已确认（2026-10-29 15:20 确认开工，status=implementing）
- 历史遗留事项清单：本段无强制承接（m2-2 移交 B1~B6 归 m2-3；C 组记录项按所属段）；G-2（模糊兜底触发者——M2-S3 前澄清）/G-4（L0 陈旧性——M2-S3）不涉本段；工作区 docs 批（TEST-CASES v1.9/AGENTS.md/_m2-plan.md/两检查点更新）以 chore 归档批承载（E 组）

## 遗留事项（跨任务移交）

- [ ] 移交 **m2s-2**（R2 Committer P3 登记项）：P3-r1 force 失败路径 run 侧审计 forced 语义（并入 G-16 create_task audit= 收口一并落）；P3-r2 force 覆盖 guard 时 stats 补 guard 明细（active/vanished/ratio/threshold）；P3-r3 跨批回归测试加固（JOIN 捕非 template 指向+父转 missing/悬挂父场景固化）；P3-r4 fail-fast API 覆盖面（畸形 JSON 400/成员+force 403/admin+force+未配置 400 固化+工厂 docstring）；P3-r5 config 校验错误前缀文案
- [ ] 移交 **m2s-2 docs 批**：P3-r6 TEST-CASES v1.9.1 版本行日期笔误（2026-10-29→2026-10-30——监督侧笔误）
- [ ] 移交 **m2s-3**（已在 known-gaps/TEST-CASES 登记）：G-15 关系级消失（scenario_config 接入时补）；N3 半句（YAML 显式引用面+值域映射表）
- [ ] 移交 **m2s-2/m2s-3**：G-16 触发侧两事务（create_task audit= 同事务参数统一收口）
- [ ] 无其他新增移交项

## 轮次记录

- **R1**（coder ses_e7976667effehA1CY3ifgt1m3Q，2026-10-29 16:34）：R1 commit `d4919d2` + chore `38d22e0`（HEAD=38d22e0）。自测证据：门禁 `GATE PASS: sqlite+pg 双后端双模式全绿 0 skipped`（常规/python -O 各 886 passed 1 deselected——基线 825+1 → **886+1（+61 新增零回归）**，pg 臂 321 全实跑：[pg] 参数化 288 + PG 专用 33）；TDD 红灯证据（ModuleNotFoundError 预期失败）。**实现决策注记**（待 Tester/Committer 关注）：① refers_to 任意型以种子 `dst_type='*'` 两行表达+触发器放行（三处一致断言+行为互证）；② 维度载体=attrs_json.dims 键（无 sem_entity_dims 专表）；填充率告警阈值=库内基线 ≥0.8 且快照携带率 < 基线×0.5 → WARNING + stats.dims_fill.alert；③ **流程顺序偏差**：宽限期推进移到关系 upsert 之后（防悬挂 active 关系——T-S4 断言语义不变）；④ 查询端点权限按 design §6.2 L1143/TC-SYNC-08③ 落 semantic:admin（检查点任务书「semantic:read 可先用」措辞与之冲突——**正文/用例优先，coder 处理正确**，监督侧确认此口径）；⑤ metadata 引用面从本次 template_center 快照推导（冷启动接力已测）；⑥ tasks.payload 列随 0006 落（semantic_sync 携带 {org,adapter}）；⑦ 既有测试水位断言 5→6 与四处测试迁移让位重编号（非放宽）；⑧ export_l0 空串占位（m2s-2）；⑨ 真实源系统不可达——协议测试替身验收+环境依赖申报。

**R1 Tester**（ses_e792d4720ffe9GSt0LfsJLs30o，2026-10-29 17:06）：**testVerdict=PASS**（testedSha=38d22e0）。独立复跑门禁 886+1 双模式 0 skipped（pg 臂 321 全实跑，825+61 逐条对上零回归）；12 验收面全过 + 31 项独立脚本交叉验证；重点审查面①~⑨逐项核实成立（顺序偏差③实测「强化 T-S4 语义」——悬挂场景对冲成立；⑦ 既有测试更新逐 diff 审毕非放宽）。**观察项**（无 FAIL 级）：N1(P3) `_worker_env` 漏映射 LATTICE_SEM_DIM_ALERT_* 两键——subprocess 模式程序化 Settings 漂移默认值（建议下轮补两行，P3-N5 同族）；N2(P3) semantic.sync outbox 事件在 run 提交后独立写（design 字面如此，崩溃窗口丢事件登记备查）；N3(范围跟踪) TC-SYNC-02「YAML 显式列出」半句+TC-SYNC-06「值域显式映射表」归 m2s-3——**TEST-CASES 口径回写归监督侧**；N4(观察) tc 未配置 org 引用面空+WARNING 继续跑（下游删除保护兜底，口径登记备查）。报告全文见「最新验证意见原文」。

**R1 Committer**（ses_e79119475ffe7rTHJALgfmxSxW，2026-10-29 17:27）：**reviewVerdict=NEEDS_CHANGES**（reviewedSha=38d22e0）。无 P1；**P2×2**：P2-1 跨批次 parent_id 解析丢失（父行在前批已提交→本批子行 parent_id 写 NULL/覆写 NULL——快照 >1000 实体必然触发，字段约占实体 97%；修复=回查库内或跨批 id 映射+600+600 跨界回归）；P2-2 inline 兜底循环不认领 semantic_sync（kick 唤醒丢失时任务永久 pending——修复=`_loop` 增 run_once(task_types=("semantic_sync",))+测试+docstring 修正）。**P3×8 建议**：P3-1=_worker_env 漏映射两键（N1 合并修）、P3-2 finished_at 恒为开始时间、P3-3 关系/别名批缺存活检查、P3-4 协议 create_task 未同步 payload 签名、P3-5 阈值校验缺口（batch_rows 上界/维度阈值 [0,1]）、P3-6 测试覆盖缺口（curated_json 逐字节回归/测试名实不符/build_adapter 默认分支/顺序偏差防回退/TC-TASK-06①）、P3-7 适配器构造失败在 run 记录前不可见于 sync-runs、P3-8 advance_status 按 org 全量推进归属不准。**三个关键面 PASS**：三处一致/列级分工/双方言等价。**N1~N4 裁定**：N1→修（并 P3-1）、N2→登记（API 触发侧两事务 m2s-2/3 收）、N3→移交 m2s-3、N4→登记+并入 B2/B3 口径确认。**需求边界问题 B1/B2/B3 上报用户**（spec_confirm）。检查点 filesChanged 笔误更正：`tests/test_regress_m0a1.py` 实为 `tests/test_regress_m0a1_followups.py`。报告全文见「最新验证意见原文」details 块（R1 Committer）。

**spec_confirm 裁定**（2026-10-30 09:13 用户拍板「按建议执行」）：B1=(a) 登记 known-gaps G-15、M2-S3 承接；B2=(a) R2 落 force 放行（POST sync/{adapter}?force=true——semantic:admin+outbox 注记 forced）；B3=(a) TEST-CASES T-S2 措辞回写（v1.9.1——空快照前置=库内有 active 基线；空库+空快照=succeeded 0 条冷启动合法态）。监督侧已落笔：TEST-CASES v1.9.1（T-S2 回写+TC-SYNC-02/06 口径注记+B2 口径登记）、known-gaps G-15/G-16（N2 一并登记）。R2 范围增补已写入任务原文（必修 P2-1/P2-2/P3-1 + B2 force + 择机 P3 清单）。status=implementing（round=2 不清零）。

**R2**（coder ses_e7976667effehA1CY3ifgt1m3Q 续接，2026-10-30 09:36）：commit `b82a723`（单 commit 含 docs 批——TEST-CASES v1.9.1+known-gaps G-15/G-16 原样入库；15 文件 +795/−72，HEAD=b82a723）。**逐条修复对照**：P2-1 双方言 `_sem_parent_id` 三级解析（批内映射→批间缓存→库内回查+悬挂父 None 缓存；600+600 跨界回归 NULL 父=0、二跑 updated=0，红灯先行）；P2-2 `_loop` 增 run_once(task_types=("semantic_sync",))+预置 pending→兜底→done 测试+两处 docstring 修正（e2e/b2 轮询终态顺手加固连跑 3 轮稳）；P3-1 env 映射补两键+7 个 LATTICE_SEM_* roundtrip；B2 force（run_sync(force=) guard 告警不 abort+stats.forced / payload {org,adapter,force} / REST ?force=true / outbox 事件顶层 forced——aborted_guard 场景 force 二跑 succeeded 全链测试）；P3-2 finish_now 参数（成功/失败两处，COALESCE 恢复生效）；P3-3 三边界存活检查（实体批首/别名重建前/关系批首——第 6 次调用精确中断测试）；P3-4 协议 create_task 补 payload 签名；P3-5 校验收口（batch_rows ≤1000 硬约束/≥1、dim 阈值 ∈[0,1]——1000 边界合法 1001 拒）；P3-6①~⑥ 全收（curated 逐字节回归/测试改名/build_adapter 默认分支×3 含 N4 固化/顺序偏差防回退/TC-TASK-06① 故障隔离〔ExplodingAdapter→docs 检索仍 200〕/DDL CHECK==常量双方言断言）；P3-7 触发端点 fail-fast（未配置/畸形→400+零任务行零 outbox，注册工厂覆盖跳过）；P3-8 advance_status 跨源推进 docstring 双方言显式声明。**自测**：门禁 `GATE PASS` 911+1 双模式 0 skipped（pg 臂 329=296 参数化+33 专用；886+1→911+1 零回归 +25：r2_m2s1_fixes 14+guard force 2+r2_p2 sem 2+adapters 3+api/worker 4）；TDD 红灯证据（P2-1/P3-2/P3-3/B2）。verdict 双置空待 R2 重验（R1 历史：testVerdict=PASS/testedSha=38d22e0/reviewVerdict=NEEDS_CHANGES/reviewedSha=38d22e0——见上）。

**R2 Tester**（ses_e792d4720ffe9GSt0LfsJLs30o 续接，2026-10-30 09:53）：**testVerdict=PASS**（testedSha=b82a723）。独立复跑门禁 911+1 双模式 0 skipped（pg 臂 329=296+33；825→886→911 零回归，+25 逐文件对账）；修复项 14 项逐条 PASS——**P2-1 独立补充验证**（父行转 missing 不在快照→子行 parent_id 保持指向且三跑幂等；悬挂父 GHOST→NULL 且父出现时接上、updated=1 诚实计数）；**B2 权限边界独立验证**（成员+force→403 零任务行零 outbox；admin+force+未配置→400——force 不绕过配置校验）；P3-3 第 6 次调用精确中断非恒真。R1 观察项 N1~N4 全闭环（N1 修/N2 G-16 在库/N3 v1.9.1 注记在库/N4 P3-6③ 固化）。新 25 用例无恒真/mock 自证；既有改动均为加法。**新观察项（备注非缺陷）**：O1 `_validate` 只挂 get_settings 入口（Settings 直构不校验——仓内惯例，登记防误读）；O2 force 覆写时消失实体照常转 missing（快照全量语义不被 force 破坏+三面留痕——B2 口径完整落地）。报告全文见「最新验证意见原文」details 块（R2 Tester）。

**R2 Committer**（ses_e79119475ffe7rTHJALgfmxSxW 续接，2026-10-30 10:01）：**reviewVerdict=APPROVED**（reviewedSha=b82a723=testedSha=HEAD 三 SHA 一致）。无 P1/P2；**关键复审面全 PASS**：①P2-1 三级解析闭环（UPDATE 覆写路径闭合、父存在不写 NULL 含 missing/retired 态、parent_cache 每批新建无跨批陈旧；_order_entities 两级排序当前一层父子够用——深树形留拓扑序注记）；②P2-2 兜底+轮询化合理适配（终态断言未放宽）；③B2 force 语义边界完整（只跳 guard、全量快照语义/missing 推进/审计三面留痕、403/400 边界正确）；④校验收口与正文一致；⑤注册工厂豁免刻意设计（docstring 待补）；⑥新测试无恒真；⑦docs 批与裁定一致；⑧零回归（改动全加法）。**剩余 P3 登记项（不值得开 R3）**：P3-r1 force 运行失败时 run 侧审计丢 forced 语义（建议并入 G-16 收口 m2s-2/3）；P3-r2 force 覆盖 guard 的 stats 未留 guard 明细（active/vanished/ratio——实现增强）；P3-r3 回归测试两小缺口（JOIN 不捕非 template 指向/父转 missing+悬挂父两场景未固化）；P3-r4 fail-fast 覆盖面补 API 用例+工厂 docstring；P3-r5 config 校验错误前缀文案；P3-r6 **TEST-CASES v1.9.1 版本行日期笔误（2026-10-29 应为 10-30——监督侧笔误，归下批 docs 顺手）**。**双通过达成（round=2）**。报告全文见「最新验证意见原文」details 块（R2 Committer）。

**交付链**（2026-10-30 10:07 用户确认交付，链内三步执行完毕）：① Coder push develop_opencode（27d2a17 后 origin/develop 未变，直接推 6d223c0..b82a723）+ 开 **PR #4**（base=develop，head=b82a723 三处一致）；② Committer 评审留痕（PRR_kwDOVZ9dhM8AAAABVC4gQA，2026-10-30T02:05:16Z，COMMENTED 载体正文首行 APPROVED——self-approve 平台限制沿 #2/#3 先例）；③ evidence manifest JSON 写入 PR description（三 SHA/门禁 911+1/rounds=2/B1~B3 裁定/G-15·16/handover——校验通过，其余段未覆盖）。**待用户合入指令**（不自动合入）。

**合入完成**（2026-10-30 10:08 用户指令「合入」）：`gh pr merge 4 --merge` → **MERGED**，mergeCommit **`428c67f97baf5d961f12746943a7d8dfaba6fd42`**；origin/develop 27d2a17→428c67f，本地 develop_opencode 已 ff 同步。收尾：检查点 status=done；TEST-CASES v1.9.2（§六 M2-S1 行 m2s-1 段完成态+P3-r6 两处日期勘误——工作区，随 m2-3 chore 批入库）；_m2-plan.md/AGENTS.md 进度更新。任务闭环（2 轮，825+1→911+1）。

## 最新验证意见原文

- （待填）

<details>
<summary>R1 Committer 报告全文（2026-10-29 17:27，reviewVerdict=NEEDS_CHANGES）</summary>

# m2s-1 R1 交付审查报告（Committer）

**审查基线**：HEAD=`38d22e0`（develop_opencode）= R1 `d4919d2`（31 文件 +3266/−101）+ chore `38d22e0`（5 文件）；审查对象为 `27d2a17..HEAD` 全量 36 文件（检查点 reviewedSha=null，无上一轮已审差异可跳过）。`testedSha=38d22e0=HEAD` 一致。门禁按分工未复跑，采信 Tester 独立复跑（886+1 双后端双模式 0 skipped，pg 臂 321）；本审完成了静态全量抽查与逐项语义核对。

## 1. 问题清单

**P1：无。**

**[P2-1] 跨批次 parent_id 解析丢失（双方言同构，现有测试未覆盖）**
- 位置：`src/knowledge_lattice/store/sqlite/backend.py:1881-1884、1922-1927、1929-1943`；`src/knowledge_lattice/store/postgres/backend.py:1590-1593、1633-1637、1639-1654`；触发面 `src/knowledge_lattice/core/semantic/sync.py:141`。
- 问题：`_sem_read_existing` 只预读**当前批次**的 (type,key)，`id_map` = 当前批次既有行 + 本批新插行；`_sem_parent_id` 只查该 map。父行若在前一批已提交，本批子行解析不到 → INSERT 写 `parent_id=NULL`；已有子行 UPDATE 还会把原本正确的 `parent_id` 覆写为 NULL。`_order_entities` 仅保证**同批内**父先子后。
- 影响：快照实体数 > `semantic_batch_rows`（默认 1000）时，边界之后的所有 `template_field` / `column` 父链静默丢失（真实模板中心字段约占实体 97%，该场景必然发生）。违反 design §4「parent_id 冗余的直接父节点」及 §5.8 设计说明⑤「同步时两者同事务写入」。现有 batching 用例 2500 条均为无父模板，全部 flow 用例 <1000 条，未覆盖此路径。
- 修复期望：父键解析必须回查库内（org 作用域）或由 sync 侧持有跨批 id 映射；父存在时不得写 NULL。补回归：600 templates + 600 fields（跨 1000 边界）断言每个 field.parent_id == 对应 template.id，二跑 `updated=0`，双后端。

**[P2-2] inline 兜底循环不认领 semantic_sync，pending 任务可永久滞留**
- 位置：`src/knowledge_lattice/app.py:128-139`（`_loop`）；`src/knowledge_lattice/worker/runner.py:35-37、59`。
- 问题：`semantic_sync` 已加入 `CLAIMABLE_TASK_TYPES`，kick 的 `run_once()`（全类型）与 subprocess 主循环（runner.py:552）均可执行；但 inline 模式兜底 `_loop` 仍只认领 maintenance + 陈旧 ingest，与 `app.py:88` / `runner.py:37` 自述「兜底循环全类型认领」矛盾。POST 触发路径为「create_task 提交 → append_outbox → background kick」：若 append_outbox 抛错、进程在两者之间崩溃或唤醒丢失，inline 模式下该任务无人认领。
- 影响：inline（测试/最小部署）模式下任务永久 pending；subprocess 主循环不受影响。
- 修复期望：`_loop` 增加 `run_once(task_types=("semantic_sync",))`（或抽取 drain-all-claimable 并保持新鲜 ingest 仍由 kick 先抢）；补测试：预置 pending semantic_sync → 跑一轮兜底循环 → done；同步修正两处 docstring。

**[P3-1] N1 同族：`_worker_env` 漏映射两个维度阈值**
- 位置：`src/knowledge_lattice/worker/runner.py:440-447`。
- 建议：补 `LATTICE_SEM_DIM_ALERT_BASELINE` / `LATTICE_SEM_DIM_ALERT_DROP`，并扩展 `tests/test_r2_p2_fixes.py:306` 的 roundtrip 断言覆盖全部 `LATTICE_SEM_*`。本案已需 R2，顺手修（沿 m2-1 P3-N5 先例）。

**[P3-2] `finished_at` 实为 run 开始时间**
- 位置：`src/knowledge_lattice/core/semantic/sync.py:93-96` 将 `now`（开始时间）传给 `sem_finish_run`；`store/sqlite/backend.py:2137-2147` / `store/postgres/backend.py:1849-1860` 的 `COALESCE(?, CURRENT_TIMESTAMP)` 因恒传 now 永不生效。
- 建议：终态时间取实际完成时刻（保留测试可注入的 `finish_now` 可选参数）；补一条 `finished_at >= started_at`/耗时非零断言。

**[P3-3] 关系/别名批循环缺 `should_continue`**
- 位置：`src/knowledge_lattice/core/semantic/sync.py:187-190`（关系批）、`141-152`（别名重建）。
- 建议：在关系批与别名批边界同样做存活检查，避免取消/失租约需等整轮结束；符合 m2-1 阶段边界停止口径。

**[P3-4] 协议未同步 `create_task(payload=...)`**
- 位置：`src/knowledge_lattice/store/backend.py:269-282`。
- 建议：`AdminBackend.create_task` 签名与 docstring 补 `payload: str | None = None`（双方言实装已有），避免协议契约与实现漂移（当前无 typecheck 兜底）。

**[P3-5] 语义阈值校验缺口**
- 位置：`src/knowledge_lattice/config.py:243-256`。
- 建议：`semantic_dim_alert_baseline/drop` 补 ∈[0,1]；`semantic_batch_rows` 补上界（design 硬约束 ≤1000）或明确允许覆盖；可选：启动时校验 `semantic_sources` 嵌套结构形状（当前仅首次 sync 时抛）。

**[P3-6] 测试覆盖缺口（非走过场，但关键面可再加固）**
- `tests/test_sync_03_flow.py` 只验证 manual/abbr 别名不受同步影响，未断言 `curated_json` / `sensitivity` / `curated_rev` 在同步前后逐字节不变（T-S1 列级分工的永久回归证据）；建议补一条。
- `tests/test_sync_04_adapters.py:202` `test_metadata_adapter_http_shape` 名实不符（测的是 template_center 分页）；建议改名。
- `build_adapter` 默认分支（template_center 的 per-org 解析、metadata 从 template_center 快照推导 refs、tc 未配置 WARNING）无套件级测试；建议补（N4 场景可随之固化）。
- 注记③的顺序偏差（快照关系指向超期 missing 端点先落库后联动 retired）无永久回归用例；建议补一条防回退。
- TC-TASK-06①（semantic_sync 适配器超时/抛错时 docs 检索可用）未见测试；可补故障隔离断言（记录级或集成级）。

**[P3-7] 适配器构造失败发生在 run 记录之前，失败不可见于 sync-runs**
- 位置：`src/knowledge_lattice/core/semantic/sync.py:240-244`（先 `build_adapter` 再 `run_sync`）；`src/knowledge_lattice/api/semantic.py:60-74`；`adapters/__init__.py:117-133`（metadata 构造时即 fetch template_center）。
- 问题：请求的适配器未配置、JSON 畸形或 metadata 引用面抓取失败时，异常发生在 `sem_start_run` 之前——不产生 `sem_sync_runs` 行/outbox；且该任务 `doc_id=NULL`，`GET /tasks`（JOIN documents）与 `GET /tasks/{id}` 均不可见，POST 仍返回 202。排查只能看日志。
- 建议：触发端点先做 `resolve_source_config` fail-fast（4xx），或把适配器构造纳入 run 生命周期（start run 后再构造/记录 failed），至少让 sync-runs 可见 failed 记录。

**[P3-8] `advance_status` 按 org 全量推进，非按来源**
- 位置：`core/semantic/sync.py:193`；`store/sqlite/backend.py:2084` 起 / `store/postgres/backend.py:1797` 起。
- 问题：Adapter A 的 run 会连带 retired 其他来源超期 missing 实体，`stats.retired` / `relations_retired` 与 outbox 事件却记在 A 名下。时序上无害（宽限期按时间），但归属与可观测性不准。
- 建议：按 `source_system` 收口，或在 docstring/统计口径中显式声明跨源推进语义。

## 2. 需求边界问题（不计 P 分级，交 supervised-coding 回 spec 确认）

- **B1 关系级消失未定义**：design §4 `sem_relations` 有 missing/retired 状态，但 §5.8 流程只定义实体消失（T-S4 也只写实体）；实现只做「端点 retired 时关系联动」，源端删除一条边而两端仍在时旧关系永久 active。后续 scenario_config/report_center 跨源场景还可能把指向已 retired 端点的关系再次 upsert 为 active。是否本段接受为演进缝（登记 known-gaps），还是需补关系级 missing/端点状态过滤？
- **B2 metadata 引用面 × 删除比例保护**：metadata 快照由 template_center 引用面推导，引用面合法收缩 >20% 时 guard 会**永久** aborted_guard（库内 active 不减少、无强制放行路径）；首轮空引用面则 succeeded 0 条。design 未给操作路径（force/豁免/人工清理）——需确认预期运维口径。
- **B3 空快照 vs 空基线**：T-S2 验收字面为「空快照 → aborted_guard」，实现仅在 `active_keys` 非空时按比例判定，空库 + 空快照 = succeeded（比例无定义）。属验收措辞与合理实现的字面冲突，需回写口径确认。

## 3. 结论

**reviewVerdict: NEEDS_CHANGES**

- 无 P1；P2-1（跨批 parent_id 丢失）与 P2-2（inline 兜底不认领）语义明确、修复成本低，建议 R2 一并修，同时顺手 P3-1，并择机收 P3-2/3/5/6。
- 核心验收面（DDL/三处一致/同步主流程/T-S2~T4/TC-SYNC-01~09/权限/端到端）实现与测试成立，P2 修复后预期可 APPROVED。
- **CASE_BUG 裁定请求：未收到**（Tester 仅提交 N1~N4 观察项）。

## 4. Tester 观察项 N1~N4 裁定

- **N1（P3）→ 修**：R2 补 `LATTICE_SEM_DIM_ALERT_BASELINE/DROP` 两行 + 扩展 roundtrip 测试，与 P3-1 合并。
- **N2（P3）→ 登记**：design §5.8 第 5→6 步字面即独立步骤，run 行可追溯；m2-2 的同事务口径针对治理/权限事件，不直接约束 run 事件。但 **API 触发侧** `create_task` + `append_outbox` 确为两事务（崩溃丢触发审计），建议 m2s-2/m2s-3 给 `create_task` 加 `audit=` 同事务参数时一并收，本段不阻塞。
- **N3（范围跟踪）→ 移交 m2s-3**：TC-SYNC-02「YAML 显式列出」半句、TC-SYNC-06「值域显式映射表」由 m2s-3 承接；本段任务书 B.3/C.7 已明示，TEST-CASES 口径回写归 supervised-coding。
- **N4（观察）→ 登记+口径确认**：tc 未配置时 refs 空 + WARNING 继续跑，下游 guard 兜底；注意首次运行会静默 succeeded 0 条，与 B2/B3 一并由 spec 确认；m2s-3 接入 YAML 引用面后可收窄。

## 5. 三个关键面显式结论

- **三处一致：PASS**。`constants.SEM_REL_TYPES` 12 行 ↔ sqlite/pg 种子 12 行逐行相同；两侧触发器均以 `t.dst_type='*'` 放行任意型，且 `'*'` 仅出现在 `refers_to` 两行；`sem_entities.type` CHECK 九值封死，实体类型不可为 `'*'`，边界守住。行为面由种子/常量断言 + 触发器放行/拒绝用例互证。唯一建议：补一条 `SEM_ENTITY_TYPES == DDL CHECK 九值` 的自动化断言（现仅行为面）。
- **列级分工：PASS**。双方言 upsert UPDATE 仅写 `name/attrs_json/parent_id/source_system/status/synced_at/updated_at`，INSERT 置 `source='sync'`；`curated_json/sensitivity/curated_rev` 不在任何同步写路径；别名重建只删插 `name/code/sync`，`manual/abbr` 由测试证明原样。残留仅 P3-6 的 `curated_json` 永久回归断言缺口。
- **双方言等价：PASS**。列/约束/索引/默认值逐项同构；PG `BIGINT IDENTITY` / `IS JSON` / plpgsql `RAISE EXCEPTION` / `BEFORE UPDATE OF` 与 SQLite `INTEGER PK` / `json_valid` / `RAISE(ABORT)` 语义等价，触发器消息逐字同源；store 的 upsert/计数/事务边界/missing-retired 计数在双方言同构（sqlite `BEGIN IMMEDIATE` vs pg `BEGIN` 为既有方言口径）。未发现方言分叉。

## 6. 门禁、chore、证据与交付把关

- **测试门禁**：diff 内新测试无 skip/skipif/xfail/删断言；既有 4 文件为水位数 5→6 与测试迁移 0006→0007/0008 的机械顺延，`fresh-migrate` 对 `sem_*` 的预期由「不在」改为「七表在场」是正确的交付后新预期，非放宽。1 deselected = 既有 `manual` 政策。新增 61 条（36 sqlite + 25 [pg]）与 Tester 复跑 886+1 对账一致。
- **chore commit**：`38d22e0` 仅含监督侧文件（TEST-CASES v1.9 / AGENTS.md / _m2-plan.md / m2-1、m2-2 检查点），**不含** `.opencode/agent/supervised-coding.md`（该文件仍为工作区未提交修改）——通过。
- **证据**：检查点 `filesChanged` 有一处笔误（`tests/test_regress_m0a1.py` 实为 `tests/test_regress_m0a1_followups.py`）；evidence manifest 属交付阶段产物，当前未生成正常。R2 后交付前必须：`testedSha=reviewedSha=最终 HEAD`，manifest 双 SHA 对齐并在 PR description 落地。
- 本轮不执行 `gh pr review` 留痕（未通过、未进入用户确认交付阶段）；合入动作不经手。

**最终判定：NEEDS_CHANGES（P2×2 修复后复审）。**

</details>

<details>
<summary>R1 Tester 报告全文（2026-10-29 17:06，testVerdict=PASS）</summary>

# m2s-1 R1 独立验证报告（Tester）

**testedSha: `38d22e02ddd2df989535159ece082bc88617c12c`**（develop_opencode；R1=d4919d2 + chore=38d22e0；工作区仅有 2 个流程文档未入库变更，不涉代码）

## 一、门禁独立复跑（不采信 coder 自测）

```
$ docker start lattice-pg && export LATTICE_PG_DSN=... && scripts/test_gate.sh
[pytest]    886 passed, 1 deselected, 0 skipped（132s）
[pytest-O]  886 passed, 1 deselected, 0 skipped（132s）
GATE PASS: sqlite+pg 双后端、双模式全绿 0 skipped（pg 臂 321 全实跑：[pg] 参数化 288 + PG 专用 33）
```
- **skip 逐个核对**：门禁 0 skipped；1 deselected = `manual` 标记（TC-UI 浏览器人工走查组，既有政策）。任务范围内用例零 skip。
- **回归核对**：对照 825+1 基线——既有测试**零删除零弱化**（详见三-⑦）；新增 6 个测试文件收集 61 条（36 sqlite + 25 [pg]），`825+61=886` 逐条对上。
- 另跑 sqlite 单臂（无 DSN）：547 passed / 339 [pg] skip（符合门禁前置语义）。

## 二、分用例判定表

| 用例 | 判定 | 证据摘要 |
|---|---|---|
| **TC-SYNC-01** per-org 解析 | PASS | 套件双 org 各自 endpoint/凭证/timeout 解析（FakeTransport 按 URL 前缀断言请求落点）；未配置 org/适配器 → `SemanticSourceNotConfigured` fail-closed；畸形 JSON → ValueError。独立复核 `resolve_source_config` 无静默分支 |
| **TC-SYNC-02** 只拉被引用 | PASS✝ | t1 落库（table+2 列+has_column×2）、t2/t3 零行零请求；引用面从本次 template_center 快照 RelationRecord 推导（`derive_refs` 只收 backed_by/maps_to）；冷启动接力已测（首轮 backed_by/maps_to 端点冲突 → metadata 落库后二跑冲突清零）。✝「YAML 显式 t2」半句归 m2s-3（任务书 B.3 明示本段仅引用面）——见缺陷清单 N3 |
| **TC-SYNC-03** 分批单事务 | PASS | 2500 实体 spy 断言 `[1000,1000,500]`；第二批注入失败 → run failed、首批 1000 行保留；重跑 inserted=500/updated=0、再跑 (0,0)。`upsert_entities_batch` 单批 `BEGIN IMMEDIATE`/`BEGIN…COMMIT` 短事务（双方言） |
| **TC-SYNC-04** 冲突不写入 | PASS | src/dst 缺失 + 白名单外 3 类冲突，明细 `{src,dst,rel_type,reason}`（type:key 形态）；合法关系不受阻断；stats_json.conflicts 持久化进 run 行 |
| **TC-SYNC-05** 别名三 kind | PASS | name/code/sync 先删后插（旧 name/sync 已删非累积）、manual/abbr 原样；alias_norm NFKC/小写/去空白与 annotate 同源（norm.py 独立函数比对 design §4 口径） |
| **TC-SYNC-06** 维度携带对冲 | PASS✝ | ① dims 落 `attrs_json.dims`（含本地无的码 MARS 原样落）；可见性不受影响（全库无按 dims 过滤路径）；报告面 `stats.dims_fill.{carried,library,snapshot}`；② 骤降告警 WARNING + `alert=true`。✝「值域显式映射表」m2s-3（design §4 无专表 DDL，任务书授权最小实现）——N3 |
| **TC-SYNC-07** run 记录与审计 | PASS | running→终态+stats_json+finished_at；**独立验证扩展到 failed 路径**：succeeded/aborted_guard/failed 三终态各产 `semantic.sync` outbox 事件且 run_id 一一对应（我的脚本 E3/E4/E4b） |
| **TC-SYNC-08** 触发与权限矩阵 | PASS | org_admin POST→202+任务行 payload `{org,adapter}`+outbox(triggered)；普通成员 403 且零任务行；未知适配器 404；GET sync-runs/builds admin 200 / 成员 403（design §6.2 L1143 口径，监督侧已确认） |
| **TC-SYNC-09** 迁移与白名单 | PASS | 七表+两触发器落库（双方言）；`tasks.payload` 列在 0006；种子 12 行=常量 12 行=§5.8 表（我逐行人工比对）；**独立行为面**：12 行逐行 INSERT 放行（'*' 加探 column/concept 两端共 14 组合）、未登记组合全拒**含 template→template 的 uses**（脚本 A1-A4）；docs 迁移 0001-0005 零 `CREATE TABLE sem_`（grep 实证「M0a/M1 库不含 sem_*」结构保证）；升级路径 legacy→0002..0006 由 test_v11_schema 双方言覆盖 |
| **T-S2** 删除比例保护 | PASS | 空快照/少 30% → aborted_guard + **实体/关系/别名三表逐行 diff 为空** + WARNING 告警 + outbox 事件；少 10% → 正常+missing=1；基数口径 per-source（`source='sync' AND source_system AND status='active'`）独立用例验证他源不稀释；边界 20% 恰等不触发（严格 >） |
| **T-S3** 同步幂等 | PASS | 二跑 inserted/updated/missing 全 0，synced_at 刷新不计入（backend updated 计数只看 name/attrs/parent/status 四项——代码+测试+我的独立复验三重确认） |
| **T-S4** 宽限期状态机 | PASS | ① missing 且关系保持 active；② 次日恢复回 active；③ 超期 retired 且关系联动 retired；6 天边界仍在宽限。**顺序偏差（注记③）独立对冲场景**：快照仍产出指向超期 missing 端点的 uses 关系 → 关系先落库后随端点联动 retired（`relations_retired=1`、active 悬挂=0）——重排序实际**强化**了 T-S4 语义（消除了按 design 字面顺序会产生的「active 关系指向 retired 端点」悬挂），断言语义全部成立 |
| **semantic_sync 端到端** | PASS | POST→任务行 done（inline worker）→ GET sync-runs 见 succeeded run + stats + 实体/别名落库 + run 侧 outbox 事件 |

## 三、重点审查面逐项结论

**① refers_to 任意型（注记①）**：✅ 成立。三处一致 = `SEM_REL_TYPES` 常量 12 行 ↔ 双方言种子 12 行 ↔ 触发器 `t.dst_type='*' OR t.dst_type=实际类型`。'*' 只挂在 refers_to 两行，不会放行其他 rel_type；实体类型 CHECK 九值封死「任意」的边界。未登记组合（含点名的 template→template uses）实测被 ABORT。

**② 填充率告警（注记②）**：✅ 可配 + 行为正确。`semantic_dim_alert_baseline/drop` Settings 字段 + `LATTICE_SEM_DIM_ALERT_*` env 读取 + `_validate` 未做范围校验（不影响行为）。独立验证：同库况下自定义阈值 (1.0/0.9) 触发、默认 (0.8/0.5) 不触发（8/10 携带场景，边界 0.8 ≥ 0.8×0.5）。**残留观察 N1**：`_worker_env` 映射漏掉这两个键（其余 5 个 `LATTICE_SEM_*` 都映射了）。

**③ 宽限推进顺序偏差（注记③）**：✅ 语义等效且更优（见 T-S4 行——悬挂场景实测对冲成立）。

**④ 查询端点 semantic:admin（注记④）**：✅ 与 design §6.2 L1143 及 TC-SYNC-08③ 逐字一致；任务书「semantic:read 可先用」措辞冲突由监督侧确认按正文——处理正确。

**⑤ metadata 引用面接力（注记⑤）**：✅ 等效对冲本段口径差。测试覆盖「冷启动冲突 → metadata 落库 → 二跑消解」完整接力链 + t2/t3 零镜像。残留：YAML 显式引用面待 m2s-3（N3 跟踪）。

**⑥ tasks.payload 随 0006（注记⑥）**：✅ 迁移框架完整。`test_migration_0006_next_after_docs_watermark` 断言双方言 discover() 版本单调、5/6 在场、semantic 域恰 [6]；幂等重放/乱序拒绝/advisory lock 并发/违例回滚四套迁移框架测试随水位顺延后全绿；payload 列双方言在场、create_task/get_task 读写贯通（端到端测试断言任务行 payload JSON）。

**⑦ 既有测试更新非放宽（注记⑦）**：✅ 逐 diff 审毕。四处改动（test_scaf_03 / test_pg_scaff / test_v11_schema / test_regress_m0a1）= 水位数 5→6、测试迁移文件 0006→0007/0008 机械顺延；唯一「语义性」改动是 fresh-migrate 断言 `sem_* 不在` → `七表在场`——这是 M2-S1 交付后的**正确新预期**而非放宽（旧断言的历史语义「M0a/M1 库不含 sem_*」由 docs 迁移零 sem_ DDL + 迁移域边界测试保持）。

**分层纪律**：✅ core/semantic 全程零 SQL（sync.py 只调 backend 方法）；`test_sem_00_layering` 双向 import 互斥执法（文本级扫描）+ 我通读两包无交叉；core/ 无 auto_entities 引用（grep 实证）。SemanticBackend 协议 12 方法双方言实装。

**安全面**：✅ 同步 UPDATE/INSERT 列清单只含事实列（name/attrs_json/parent_id/source_system/status/synced_at），curated_json/sensitivity/curated_rev 不在列——我的独立 B 组实测 curated_json 与 manual/abbr 在同步后逐字节原样。本段 api/semantic.py 仅 3 端点、无 restricted 查询面（不测，符合约定）。

## 四、与 coder 自测对账

| 项 | coder 自报 | 我实测 | 差异 |
|---|---|---|---|
| 门禁 | 886+1 双模式 0 skipped | 886+1 双模式 0 skipped | 无 |
| pg 臂 | 321（288 参数化+33 专用） | 321（288+33，gate 输出） | 无 |
| 新增 | +61 | 收集 61（36+25[pg]） | 无 |
| TDD 红灯 | ModuleNotFoundError | 未复演（不影响判定） | — |

## 五、缺陷清单

**无 FAIL 级缺陷。** 观察项与跟踪项：

| 编号 | 级别 | 内容 |
|---|---|---|
| N1 | P3 观察 | `worker/runner.py _worker_env` 漏映射 `LATTICE_SEM_DIM_ALERT_BASELINE/DROP`（其余 5 个 LATTICE_SEM_* 已映射）。部署走真实 env 时 `dict(os.environ)` 继承兜住（实测 D3）；仅「程序化构造 Settings + subprocess 模式」漂移到默认 0.8/0.5。建议下轮补两行映射（P3-N5 同族） |
| N2 | P3 观察 | `run_sync` 的 `semantic.sync` outbox 事件在 `sem_finish_run` 提交**之后**独立写入（api 触发事件同理）——崩溃窗口丢事件。design §5.8 第 6 步字面即独立步骤、run 行本身可查可追溯，不构成用例违背；登记备查 |
| N3 | 范围跟踪 | TC-SYNC-02「YAML 显式列出」半句 + TC-SYNC-06「值域显式映射表」——归 m2s-3（任务书 B.3/C.7 明示、TEST-CASES 口径回写归 supervised-coding）。当前实现与测试对本段可交付面覆盖完整 |
| N4 | 观察 | metadata 适配器在 template_center 未配置的 org：引用面空 + WARNING（非 raise）继续跑空快照——下游有删除比例保护兜底，非静默；口径未见于用例文档，登记备查 |

**验证过程中我自己的测试缺陷**（已修）：独立脚本 E4 首版断言 3 事件实为 4（4 run 4 事件）——TEST_BUG，修正后 31/31 全过，与本仓库套件无关。

## 六、结论

**testVerdict: PASS**

- 门禁真实执行：双后端双模式 886+1 全绿 0 skipped，pg 臂 321 全实跑，零回归
- 12 项验收面（TC-SYNC-01~09、T-S2/T-S3/T-S4、端到端）全部有套件断言 + 我的 31 项独立脚本交叉验证，零 FAIL
- 三处一致、顺序偏差、per-org fail-closed、列级分工（T-S1 机制）等 coder 决策注记①~⑨逐项核实成立（N1/N2 为非阻断观察项）
- testedSha: `38d22e02ddd2df989535159ece082bc88617c12c`

</details>

<details>
<summary>R2 Tester 报告全文（2026-10-30 09:53，testVerdict=PASS）</summary>

# m2s-1 R2 修复轮独立验证报告（Tester）

**testedSha: `b82a7239c981296e31a2e4ea597a11a569b68d85`**（develop_opencode；`git diff 38d22e0..b82a723` = 15 文件 +795/−72，与声称一致）

## 一、门禁独立复跑

```
$ docker start lattice-pg && export LATTICE_PG_DSN=... && scripts/test_gate.sh
pg 臂用例收集数：329（[pg] 参数化 296 + PG 专用 33）
[pytest]    911 passed, 1 deselected, 0 skipped（142s）
[pytest-O]  911 passed, 1 deselected, 0 skipped（133s）
GATE PASS: 双后端双模式全绿 0 skipped
```
- **计数对账**：825 → 886 → 911（+25 ✓）。逐文件核对：r2_m2s1_fixes 7×双臂=14 + guard force 1×双臂=2 + r2_p2 增 2（env roundtrip/bounds，非参数化）+ adapters +3 + api/worker +4 = **25**；[pg] 288→296（+8 = 7+1 双臂）✓；PG 专用 33 不变 ✓。门禁 0 skipped，1 deselected=manual（政策内）。

## 二、修复项逐条判定表

| 项 | 判定 | 证据 |
|---|---|---|
| **P2-1** 跨批 parent_id | **PASS** | 实现：三级解析（批内 id_map → 批间缓存 → 库内回查），**parent_cache 每批新建**（防跨批陈旧）。回归测试双臂过：1200 实体 batches==2、NULL 父=0、**逐行 JOIN（父指错模板也算败）**、二跑 updated=0（可捕获「曾写 NULL 后修正」）。**独立补充验证（我 R1 点名的误覆写面）**：①父行转 missing 不在本轮快照、子行仍在 → 子行 parent_id 保持指向（R1 代码此处写 NULL）且三跑幂等；②悬挂父（GHOST 从未存在）→ NULL 且后续 run 父出现时子行接上、updated=1 诚实计数。库内回查 SQL 与 sqlite 同语义（逐行比对双方言 diff） |
| **P2-2** inline 兜底 | **PASS** | `_loop` 增 `run_once(task_types=("semantic_sync",))`（无陈旧过滤——即时领）；测试为**真实 worker 循环认领**（预置 pending 不经 POST/kick → wake → 轮询至 done + run succeeded），非 mock 自证。kick 先抢语义不破坏：ingest 的 `created_before` 陈旧过滤保留（③分支原样）、claim 原子性防双领（m2-1 机制，全套 TC-TASK/E2E 门禁内绿）。副作用：e2e 断言从「响应即终态」改为轮询——合理适配（P2-2 引入并发认领者），终态断言不变 |
| **P3-1** env 映射 | **PASS** | `_worker_env` 补齐两阈值键（现 7 键全映射）；`test_get_settings_reads_semantic_env_roundtrip` 双向断言（get_settings 读取 + 映射往返）。**我 R1 的 N1 关闭** |
| **B2** force 放行 | **PASS** | 链路五层全断言：core（少 30% 无 force → aborted_guard + `forced:False`；force=True → succeeded + missing=3 写入发生 + "OVERRIDDEN by force" WARNING 告警仍发 + outbox 顶层 `forced:true`）〔双臂〕→ REST e2e（`?force=true` → 202 body.forced / 任务 payload force:true / run stats_json.forced:true / 触发事件 forced）。**独立验证**：成员+force=true → **403 且零任务行零 outbox**（admin 门控先于 force）；admin+force+未配置源 → **400**（force 不绕过配置校验）；无 force 默认路径与 R1 行为一致（guard 统计仅新增键） |
| **P3-2** finish_now | **PASS** | 成功/失败两处均传 `finish_now`；`finished == LATER`（≠ started）；缺省路径 `COALESCE(NULL→CURRENT_TIMESTAMP)` ≥ started（started 造数为 2020）；defaults 用例在场 |
| **P3-3** 三边界存活检查 | **PASS** | 实体批首/别名重建前/关系批首三处 `_check_alive`；测试以**第 6 次调用精确中断**（①实体批1 ②批1别名 ③实体批2 ④批2别名 ⑤关系批1 ⑥关系批2）——若关系边界缺失则全轮仅 4 次调用、`pytest.raises` 必败，非恒真；run 落 failed |
| **P3-4** 协议 create_task | **PASS** | `store/backend.py` 协议签名补 `payload: str \| None`，docstring 记 {org, adapter, force?}；双方言实装 R1 已有 |
| **P3-5** 校验收口 | **PASS** | batch_rows ∈[1,1000]（1000 合法/1001 拒绝）、dim 阈值 ∈[0,1]（1.5/-0.1 拒绝）——我独立走 `get_settings()` env 路径复验四处全 fail-closed。**口径注记**：`Settings(...)` 直构不经 `_validate`——与 R1 以来全部字段的 P3-N10 惯例一致（部署唯一入口是 get_settings，app 与 worker 子进程同），非缺陷 |
| **P3-6①** 人工列逐字节 | **PASS** | curated_json/sensitivity/curated_rev 三列同步前后逐字节相等（我 R1 未断言的 sensitivity/curated_rev 面补齐），事实列 name 照常更新 |
| **P3-6②** 改名 | **PASS** | `test_metadata_adapter_http_shape` → `test_template_center_adapter_paging`（测的就是 tc 分页——名实对齐，断言体未动） |
| **P3-6③** build_adapter 默认分支 | **PASS** | ×3：tc per-org 解析（双 endpoint 断言请求落点）/ metadata 引用面推导（t9 引用面外零请求）/**N4 场景固化**（tc 未配置 → WARNING + 空引用面 + md 零请求） |
| **P3-6④** 顺序偏差防回退 | **PASS** | 我 R1 的 T-S4 独立对冲场景转正式用例（双臂）：快照关系指向超期 missing 端点 → 端点 retired + 关系 retired——终态断言可区分顺序（若倒置，关系 upsert 会留 active → 断言败） |
| **P3-6⑤** 故障隔离 | **PASS** | 爆炸适配器 → 任务 failed + error 留痕 + ≥1 failed run 行；**docs 检索端点仍 200**（TC-TASK-06①） |
| **P3-6⑥** CHECK==常量 | **PASS** | 双方言解析 DDL CHECK 九值 == SEM_ENTITY_TYPES（三处一致第四面，Committer 建议兑现） |
| **P3-7** 触发 fail-fast | **PASS** | 无工厂覆盖 + 未配置 → **400**（畸形 JSON 同 400）；**零任务行 + 零 outbox** 断言；注册工厂（测试 fake）路径豁免——既有 fake 注入用例不受影响（门禁全绿实证） |
| **P3-8** advance_status 口径 | **PASS** | docstring 声明 org 全量推进、不按 source_system 收口（多适配器共享时间窗）——诚实披露，本段接受口径 |

## 三、R1 观察项对账

| R1 编号 | 处置 | 状态 |
|---|---|---|
| N1 worker env 缺两阈值映射 | P3-1 补齐 + 7 键 roundtrip 测试 | ✅ 已修 |
| N2 outbox 两事务崩溃丢触发审计 | **known-gaps G-16**（在库，M2-S2/S3 承接，修复口径=create_task audit= 同事务参数） | ✅ 登记落笔 |
| N3 TC-SYNC-02 YAML 半句 / TC-SYNC-06 映射表归 M2-S3 | **TEST-CASES v1.9.1** 两处口径注记（在库） | ✅ 落笔 |
| N4 tc 未配置空引用面 | P3-6③ 第三用例固化 + TC-SYNC-02 注记（「冷启动合法态」B3 口径） | ✅ 固化 |

## 四、新增 25 用例强度抽查结论

**未发现恒真/mock 自证。** 抽查亮点：P2-1 逐行 JOIN 连「父指错行」都捕获、二跑 updated=0 构成闭环；P3-3 精确调用计数证明特定边界在场；B2 e2e 纵贯 REST→payload→run stats→outbox 四层且默认路径对照；P3-7 双零残留断言；故障隔离同时断言失败面与不外溢面。既有测试改动均为**加法**（force 用例、payload 键断言更新、e2e 轮询化），无删除无弱化——886 存量语义全数保留于 911。

## 五、与 coder 自测对账

| 项 | coder 声称 | 我实测 | 差异 |
|---|---|---|---|
| 门禁 | 911+1 双模式 0 skipped | 911+1 双模式 0 skipped | 无 |
| pg 臂 | 329（296+33） | 329（296+33） | 无 |
| 增量 | +25（14+2+2+3+4） | +25（同拆分） | 无 |

## 六、缺陷清单

**无 FAIL 级缺陷。** 本轮新增观察项：

| 编号 | 级别 | 内容 |
|---|---|---|
| O1 | 备注（非缺陷） | `_validate` 只挂 `get_settings()` 入口、`Settings(...)` 直构不校验——与仓内 R1 起全部配置字段同惯例（部署读配置唯一入口），P3-5 按惯例收口正确；登记防误读 |
| O2 | 备注 | force 语义边界：guard 覆写时消失实体照常转 missing（快照全量语义不被 force 破坏）+ 告警/审计/统计三面留痕——B2 拍板口径的完整落地，无残留 |

## 七、结论

**testVerdict: PASS**

- 门禁真实复跑：双后端双模式 **911+1 全绿 0 skipped**，pg 臂 329 全实跑，825→886→911 零回归
- 必修 P2-1/P2-2/P3-1、B2 force、择机 P3-2~P3-8 共 14 项**逐条 PASS**；P2-1 的跨 run 误覆写面与 B2 的权限边界经我独立构造场景额外验证
- R1 观察项 N1~N4 全部闭环（修复/登记/落笔/固化）
- testedSha: `b82a7239c981296e31a2e4ea597a11a569b68d85`

</details>

<details>
<summary>R2 Committer 报告全文（2026-10-30 10:01，reviewVerdict=APPROVED）</summary>

# m2s-1 R2 修复复审报告（Committer 续接）

**审查基线**：HEAD=`b82a7239c981296e31a2e4ea597a11a569b68d85`（develop_opencode）；审查对象 `git diff 38d22e0..b82a723`，15 文件 +795/−72，与检查点自报一致；R1 全部意见（P2×2+P3×8、B1/B2/B3、N1~N4）逐条对照。上一轮 reviewedSha=`38d22e0`，本轮 reviewedSha=`b82a723`；testedSha=`b82a723` 与 HEAD 一致。
门禁按分工未复跑，采信 Tester 独立复跑（911+1 双模式 0 skipped，pg 臂 329=296 参数化+33 专用；886+1→911+1，+25 逐文件对账）；本审完成增量源码、测试、docs 的静态语义核对。

## 1. 问题清单

**P1：无。P2：无。**

以下均为 P3（均不阻塞交付，建议登记/下批顺手，不建议为此开 R3）：

**[P3-1] force 运行**失败**时 run 侧审计丢失 forced 语义**
- 位置：`src/knowledge_lattice/core/semantic/sync.py:95-96`（失败路径 `_audit_sync(..., {"error": ...})`）、`:282`（`forced` 仅从 stats 派生）。
- 问题：`force=true` 运行若在 guard 之后抛错落 failed，`sem_finish_run` 的 stats 为 `{}`，run 侧 `semantic.sync` 事件 `forced=false`；触发侧事件仍正确记 forced=true，任务 payload 也有 force，但 run 事件的事实陈述不准确。成功/aborted 路径不受影响（B2 验收场景已覆盖）。
- 建议：失败路径把 `force` 一并放入 stats 或直接传 `force` 给 `_audit_sync`（如 `{"error": ..., "forced": bool(force)}`）；可顺带在 failed stats 记 `{"forced": ...}`。属审计完整性小修，登记至 m2s-2/m2s-3 与 G-16 一起收。

**[P3-2] force 覆盖 guard 的 run stats 未保留 guard 明细**
- 位置：`src/knowledge_lattice/core/semantic/sync.py:136-152`（guard 明细只在非 force 的 aborted 分支写入）、`:232`。
- 问题：force 放行后 stats 只有 `forced:true`，没有 `active/vanished/ratio/threshold`；运维在 `GET sync-runs` 只能看到"被 force 过"，看不到覆盖的具体比例（日志有，但非结构化）。
- 建议：force 分支同时写入 `stats["guard"]`（或 `guard_overridden`），v1.9.1 只要求注记 forced，此为实现增强；不阻塞。

**[P3-3] P2-1 永久回归测试的两个小缺口**
- 位置：`tests/test_r2_m2s1_fixes.py:52-72`。
- 问题：①"逐行 JOIN"以 `t.type='template'` 参与 JOIN，若 field.parent_id 错误指向**非 template 行**（同 key 不同 type），该行不会进入 bad 计数，测试仍绿；建议改 LEFT JOIN + `t.id IS NULL OR t.key != ...` 或 `parent_id IN (SELECT id ... WHERE type='template')`。②父行转 missing / 悬挂父 GHOST 后续接上两个场景目前只在 Tester 独立脚本验证，永久套件只有跨批 600+600；建议把这两个场景固化进本文件，防未来回归。代码本身正确（见复审面①），仅测试加固。

**[P3-4] P3-7 永久测试覆盖面可由独立验证补入**
- 位置：`tests/test_sync_05_api_worker.py:260-290`；`src/knowledge_lattice/core/semantic/adapters/__init__.py:101`。
- 问题：永久套件只测"未配置→400"，Tester 独立验证的「畸形 JSON→400」「成员+force→403 零任务行」「admin+force+未配置→400」未固化；另 `register_adapter_factory` 的豁免面本身可接受（代码级扩展点、生产默认空），但应在其 docstring 明示"注册工厂自担配置解析，P3-7 fail-fast 对其跳过"。
- 建议：补上述 2~3 条 API 用例 + 一行 docstring；测试/文档级，不阻塞。

**[P3-5] 配置校验错误前缀与新语义不符（文案级）**
- 位置：`src/knowledge_lattice/config.py:264`。
- 问题：`semantic_batch_rows` 上界与 `[0,1]` 区间校验加入后，汇总前缀仍为 `invalid config values (must be >= 0)`，语义不完整。
- 建议：改为 `invalid config values (range/negative checks)` 或按字段消息已足够；纯文案，可下批顺手。

**[P3-6] docs 版本行日期 nit（监督侧文档，非 coder 代码问题）**
- 位置：`docs/TEST-CASES.md:1`。
- 问题：v1.9.1 版本行写"2026-10-29 随 m2s-1 R2 批入库"，而 user 拍板/R2 commit 为 2026-10-30；内容（T-S2 前置、force、TC-SYNC-02/06 注记）与裁定一致。
- 建议：归 supervised-coding 下批 docs 顺手，不计代码问题。

## 2. 关键复审面显式结论

**① P2-1（跨批次 parent_id）：PASS——问题闭环。**
- 双方言 `_sem_parent_id` 改为三级解析：批内 `id_map` → 本批 `parent_cache` → **org 作用域库内回查**；`parent_cache` 在 `upsert_entities_batch` 内每批新建，无跨批陈旧。
- UPDATE 覆写路径已闭合：父行在前批已提交时，库内回查返回真实 id；父存在（active/missing/retired 均不过滤 status）不会写/覆写 NULL。Tester 独立验证的「父转 missing 不在快照→子 parent_id 保持」「悬挂父→NULL，父后续出现→updated=1 接上」与代码语义一致。
- 600 templates + 600 fields 跨 1000 批界回归：`batches==2`、NULL 父=0、逐行 JOIN、二跑 `updated=0`，双方言；这正是 R1 点的 UPDATE 覆写面。
- 说明：`_order_entities` 仍是两级排序，当前 template_field/column 一层父子完全够用；若未来引入更深树形 parent_key，需拓扑序（本次不做，非本段缺陷）。

**② P2-2（inline 兜底认领 semantic_sync）：PASS。**
- `app.py:_loop` 增加 `run_once(task_types=("semantic_sync",))`，maintenance / semantic_sync / 陈旧 ingest 三分支；subprocess 主循环与 kick 本就是全类型，双认领者由 m2-1 claim 原子性保证唯一执行。
- e2e 从"响应即终态"改为轮询是**合理适配**（新增第二认领者后毫秒级窗口真实存在），终态断言仍为 `done`，未放宽为"任意终态"；`test_p2_2` 用真实循环 + 预置 pending 验证兜底通道，非 mock 自证。
- 两处 docstring（app.py / runner.py）已改为与实现一致。

**③ B2 force：PASS。**
- force 只跳过删除比例保护：`_sync_records` 仍全量计算 `vanished`、`mark_entities_missing`、`advance_status`、别名重建与关系 upsert；O2「force 覆写时消失实体照常转 missing」成立。
- 权限/配置边界正确：admin 门控先于 force（成员+force→403 零任务行）；trigger fail-fast 在 admin 之后、任务创建之前（未配置/畸形→400，零任务行零 outbox）；force 不绕过 `resolve_source_config`。
- 留痕：guard 告警恒发（OVERRIDDEN by force）、`stats.forced`、触发 outbox `forced`、run 侧 outbox `forced`；成功/覆盖场景完整。仅 P3-1/P3-2 两处审计增强。

**④ P3-5 校验收口：PASS 且与正文一致。**
`semantic_batch_rows` 硬约束 `[1,1000]` 与 design §5.8「每批 ≤1000 行提交」/NFR-11 一致（1000 合法、1001 拒）；维度告警两阈值 `[0,1]`。Settings 直构不校验属仓内既有惯例（O1 接受），部署唯一入口 `get_settings` 已覆盖。

**⑤ P3-7 注册工厂豁免：不过宽，但需文档化。**
`ADAPTER_FACTORIES` 是代码级扩展点（测试 fake/部署自定义 provider），默认空；豁免是刻意设计，不是外部输入可控面。唯一残留：自定义工厂若自身依赖配置，仍会 202 后任务失败且无 run 行——建议在注册表 docstring 声明"工厂自担配置解析"，与本条 P3-4 合并处理。

**⑥ P3-6 新测试强度：整体 PASS，无恒真/mock 自证。**
逐行 JOIN、精确第 6 次中断、跨层 force e2e（REST→payload→run stats→outbox）、双零残留、故障隔离 200 断言均有效；仅 P3-3/P3-4 的测试加固 nit。

**⑦ docs 批：内容 PASS。**
G-15（关系级消失、M2-S3）、G-16（触发侧两事务、M2-S2/S3）、T-S2 force 口径与 B3 前置、TC-SYNC-02/06 的 N3/N4 注记均与 R1 报告/用户裁定一致；无越权改动。仅版本行日期 nit（P3-6）。

**⑧ 零回归：PASS。**
既有测试改动为：`test_sync_02` helper 加 `**kw`；`test_sync_05` fixture 增 0.2s poll、payload 精确断言更新为含 `force:false`、e2e 轮询化；`test_sync_04` 改名；`test_r2_p2` 纯新增。无 skip/skipif/xfail，无删除断言/弱化断言；911=886+25、pg 329 与 Tester 逐文件对账一致，e2e 终态断言不变。

## 3. Tester 观察项/N 项与 O1/O2

- **N1（原 R1）→ 已修**：`_worker_env` 补齐两阈值；7 个 `LATTICE_SEM_*` roundtrip 测试通过。
- **N2 → 已登记 G-16**：触发侧 `create_task`+`append_outbox` 两事务，与 G-16 一致；建议随 m2s-2/m2s-3 的 `create_task(audit=)` 统一收口。
- **N3 → 已落 v1.9.1**：TC-SYNC-02/06 注记归 M2-S3。
- **N4 → 已固化**：tc 未配置 WARN + 空引用面 + 首轮冷启动合法态用例在库。
- **O1/O2**：均接受为备注（Settings 直构不校验为仓内惯例；force 不破坏全量快照语义属预期），无需动作。

**CASE_BUG 裁定请求：未收到。**

## 4. 结论与交付判定

**reviewVerdict: APPROVED**

- **reviewedSha = `b82a7239c981296e31a2e4ea597a11a569b68d85`**
- **testedSha = reviewedSha = HEAD**，三 SHA 一致；R1 的 P2×2+P3×8 全部闭环，B1/B2/B3 按用户拍板落地，docs 批与裁定一致。
- 剩余仅 P3 级观察项：**不值得再开一轮 R3**；建议登记/随 m2s-2/m2s-3 顺手（P3-1 建议并入 G-16 收口；P3-2~P3-5 作为测试/文档加固；P3-6 归 supervised-coding 下批 docs）。
- 交付就绪：代码与测试已具备交付条件；**evidence manifest 仍属交付阶段产物，当前尚未生成**——待用户确认交付后按流程 push/开 PR，将 `testedSha=reviewedSha=b82a723`、门禁 911+1/0 skipped、pg 329 写入 PR description，再执行 `gh pr review` 留痕；合入动作不经手。检查点 `reviewVerdict`/`reviewedSha` 字段由 supervised-coding 按本结论回填。

</details>
