---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2s-5
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e6e326344ffeWEscrwiXmW1eUC
testerTaskId: ses_e6df2e93fffeR4RoKiwF3Gdng6
committerTaskId: ses_e6dd5bf39ffediNh4NufovraSn
status: approved
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 241ee242196066546b98729cf5639a0eb22565fa
reviewedSha: 241ee242196066546b98729cf5639a0eb22565fa
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["store/sqlite/migrations/semantic/0008_sem_build_snapshots.sql(+pg 同)", "store/sqlite/backend.py", "store/postgres/backend.py", "store/backend.py", "core/semantic/tagging.py(新)", "core/semantic/annotator.py", "core/semantic/build.py", "core/semantic/yaml_corpus.py", "core/semantic/evalrun.py", "core/docs/ingest.py", "worker/runner.py", "worker/maintenance.py", "app.py", "config.py", "eval/semantic_seed.py", "eval/semantic_golden.README.md", "tests/test_tag_01_ingest.py(新)", "tests/test_tag_02_retag.py(新)", "tests/test_tag_03_untag_reconcile.py(新)", "tests/test_g21_build_snapshots.py(新)", "tests/test_m2s5_followups.py(新)", "tests/test_r3_m2s4_fixes.py(改)", "tests/×7(迁移水位/桩适配)", "AGENTS.md(批)", ".opencode/workflows/_m2-plan.md(批)", ".opencode/workflows/task-knowledge-lattice-m2s-4.md(终态批)"]
endReason: null
createdAt: 2026-10-31T19:50:44+0800          # 创建时间（30 天清理审计用，见 README §4.5）
updatedAt: 2026-10-31T22:41:13+0800          # 每次写检查点必更新为当前时间（ISO 8601 含时区），不得沿用旧值
---

# task-knowledge-lattice-m2s-5: M2-S3 基础段——ingest 打标 + semantic_retag + untag + 对账 + G-21 方案 A

## 任务原文

（依据 design §4·§5.8·§8 M2-S3 第 1~2 项 + TEST-CASES §六 M2-S3 行 + _m2-plan 段表第 9 行；段序：2026-10-31 用户确认——语义轨道优先（m2s-4 ✅ → **m2s-5** → m2s-6 → m2-4 → m2-6 → m2-5 收口））

**A. 核心功能（打标/重标面）**：
1. **concept/system 纯人工实体**：YAML curated 面（concept：纯人工业务概念，无系统源；system：系统对象）接入 sem 实体管线——kind 扩展、快照/build 产物包含、annotate 可命中（concept 类）；与 m2s-4 评测不冲突（参考词典 seed 可扩条目——非必需）。
2. **ingest 打标（同事务 tag）**：文档 ingest 管线解析成功后，在同一事务内对新块跑 annotate（服务端 AC 自动机），命中实体写 `sem_chunk_entities`（chunk_id/entity_id/span/matched_by）；**打标失败不阻断 ingest**（捕获记 warning/审计——文档先可用，标后续补）；restricted 实体不落标（T-S9 一致）。
3. **semantic_retag 任务（最低优先级）**：worker 认领分发位接线（CLAIMABLE_TASK_TYPES 补入）；payload 携 dict_rev——重标「落后块」（dict_rev 落后的 chunk）；别名增删 diff 判定（构建涉及别名增删才投递——**TC-BUILD-05 消费面收口**）；最低优先级（排在 ingest/reindex 等之后）。
4. **版本切换/删块同事务 untag**：文档新版本切换与块删除时，同事务清理对应 `sem_chunk_entities` 行（防悬挂标）；删除级联与 m2-2 挂接点对齐。
5. **定时对账**：maintenance 挂载对账任务——扫 `sem_chunk_entities` 与 active 实体/存活 chunk 的失配（实体 retired/块已删/dict_rev 落后超阈值），报告进构建报告或独立面；只报告+补投 retag（不直接改标——幂等收敛靠 retag）。
6. **G-21 方案 A（build 快照附表）**：`sem_build_snapshots(build_id, snapshot_json)`（实体+别名+curated 最小 JSON——双方言迁移 0008）；`get_annotator`/`render_l0` 按 current build id 取快照构建实例，无快照回退 live（回退告警保留）；**冷缓存/重启后服务 build 产物而非 live**——G-21 收口（known-gaps 回写由监督侧落笔、coder 原样 commit）。

**B. 挂账收编（m2s-4 移交——_m2-plan row 9 权威）**：
1. **ambiguity 分子收紧**：`ambiguous=true` 的主候选命中不再计「正确」（严格口径）+黄金集断言同步（18/20=0.90 仍过门）。
2. **歧义缺省读法显式化**：YAML 增显式缺省主读字段（覆盖层），消解实现第一候选依赖（README 两无佐证 qid 列出）。
3. **TC-BUILD-05**：随 A3 收口（§4.4 用例+m2s-4 已移行 M2-S3 行——本段交付后 TEST-CASES 落完成态）。
4. **R3 用例空转两项补强**：P1-1 报告面断言（fixture 构成真实跨实体共享 alias）/P3-1 用例改非歧义 mention。
5. 错别字正样本：**依赖模糊层（m2s-6）——本段不做**，登记注记维持（黄金集不动）。
6. TC-PERF-05：m2-5 收口段兜底（本段不做——除非顺手）。

**C. 验收**：**T-S10**（打标/untag/对账全链）+ TC-TAG-01（ingest 打标）/TC-TAG-02（retag）/TC-BUILD-05（重标投递）+ G-21 收口（冷缓存/重启行为反转用例）；T-S7~S9 越权矩阵+TC-SEM-08/TC-SEV-03/TC-SEM-09 属 m2s-6（本段不验）；门禁基线 1323+1 单调不减、双后端双模式 0 skipped。

**D. docs/约束**：docs 批（工作区 _m2-plan/AGENTS.md/m2s-4 检查点终态 M + 本段 G-21 收口回写+TC-TAG/TC-BUILD-05 完成态）由监督侧落笔、coder 原样 commit；core 零方言 SQL（快照附表迁移下沉 store 双方言 0008）；禁改 requirements/design 正文；worker 认领扩展遵循既有 maintenance/runner 模式；禁 push。

## 需求确认
- [x] 用户已确认（2026-10-31 19:51 确认任务书——status=implementing）
- 历史遗留事项清单：18 个历史检查点全部 done 无未了结任务级遗留；m2s-4 移交六项已并入 B 节（错别字/TC-PERF-05 注记去向）；TC-UI-01~04 手动走查为用户侧待办（不并入）。

## 遗留事项（跨任务移交）
- [x] 交付归档批（2026-10-31 22:41）：3 项 m2s-4 P3 补登记（r8 无 build 返回空/P3-16 annotate 仅捕 ValueError——G-21 未闭清单）；TEST-CASES v1.9.9（TC-TAG-01~03/TC-BUILD-05/T-S10 ✅+四口径注记）；AGENTS/_m2-plan 终态（语义 5/6、下一段 m2s-6、基线 1386+1）
- [x] 移交 m2s-6（_m2-plan row 10 挂账权威）：TC-TAG-04/05；TC-SEM-08/09+错别字正样本（模糊层）；TC-SEV-03+检索增益；TC-YAML-05；T-S7/S8/S9 越权矩阵；G-21 未闭 P3 顺手；TC-PERF-05（m2-5 兜底）
- [x] TC-UI-01~04 手动走查：用户侧待办（M1 遗留——不并入，持续挂账）

## 轮次记录
（待 R1）

R1: coder 完成（2026-10-31 21:01，commit **`0c127db`**〔首 commit 9373f11 因违规入库 supervised-coding.md+m2s-5 检查点未完成态被打回，soft reset 重做——新树门禁复验一致〕，33 文件 +2606/−145；父 2cb2277）：**A1** concept/system 验收面收口（识别/打标——kind 链 m2s-3 已全，出入⑥申报）；**A2** ingest 同事务打标（backend.insert sem_tags+rollback 同生共死用例；失败捕获+warning+`semantic.tag_failed` 审计不阻断；restricted 双滤）；**A3** semantic_retag 接线（CLAIMABLE+executor+claim 尾序最低优先级；分批≤batch_rows+批间存活检查；**别名增删 diff 投递**=stats dict_rev_components.aliases 对比〔TC-BUILD-05〕）；**A4** untag 四挂点（版本切换/pending failed 物理删/删文档/tombstone 90 天——同事务）；**A5** 对账（maintenance 挂载：清悬挂行+lagging/untagged 报告+补投 retag 不改标；裁量申报③：>0 即投+done 24h 节流防无行块投递风暴）；**A6 G-21 方案 A**（0008 双方言快照附表；switch/reactivate 同事务写；get_annotator/render_l0 按 current build id 取快照、无快照回退 live+告警；**冷缓存/重启双反转**〔P2-1 两旧钉死用例按新语义改写〕；快照含 relations——出入①申报〔共现消解必需〕）；**B1** ambiguity 分子收紧（ambiguous=true 不计正确+黄金集断言同步；严格口径 s109/s117=default 后 ambiguity=1.0、旧口径 0.90 README 登记）；**B2** default_reading 全链（YAML 值校验∈别名面+全局唯一→curated→快照→消歧第⑤级 ceiling 0.9；未声明不落回隐式第一候选）；**B4** 用例空转两项补强+r6 随手；**B5/B6 不做**。出入②首建投递宁投勿漏（幂等收尾钉死）/④sem_tags 载体按 0006 DDL（span/matched_by 识别面复得）/⑤缺省主读挂实体级 curated（零 DDL）。自测：TDD 四批红灯；门禁 **GATE PASS 1376+1**（pg 臂 483=450+33，双模式 0 skipped，1323+1→1376+1 +53）；T-S10 全链六用例。known-gaps G-21 收口回写+TEST-CASES 完成态留 R2（监督侧落笔）。

R1: tester **PASS**（2026-10-31 21:32，testedSha=0c127db）：TDD 独立复跑 53 passed 双后端；门禁 **GATE PASS 1376+1**（pg 臂 483=450+33，双模式 0 skipped，+53 精确对账；存量零删除——2 个 -def=G-21 旧钉死用例按新语义改名改写非弱化）。验收逐条全过：TC-TAG-01（同事务 rollback/失败不阻断+审计/restricted/concept 命中/无构建静默）/TC-TAG-02（落后块重标+rev 追平/无行块补标/**claim 尾序双方言读码互证**/幂等）/TC-TAG-03（悬挂清理+落后行不被改写）/TC-BUILD-05（别名增删 diff 投递/definition 变不投/首建宁投勿漏+V10 删对称面+分量缺省 fail-safe 四态）/T-S10（三挂点用例+**第 4 挂点 tombstone 90 天独立 V11 实证**）/G-21 反转（0008 双方言 pg 直查水位 8/冷缓存服务 build 产物/**评测拦下重启不被服务**/回退 live+告警/**快照含 relations 冷热等价 V9**——出入①实证）。B1/B2 防自证：V1 独立计算器互证（分母分子 20/20、ambiguity=1.0）/V2 s109/s117 resolved_by='default' confidence=0.9/B2 全链+未声明不落回。V3 restricted 双保险/V4 大文本/V5 批间删块竞态（悬挂行对账兜底归零）/V6 节流三态/V7 快照损坏 sqlite json CHECK 拦。**0 IMPL_BUG/0 SPEC_GAP**；OBSERVATION 4：①pg snapshot_json 无 json_valid CHECK（外部篡改抛错不回退——登记）/②第 4 挂点无专项仓库测试（V11 已实证——后续触碰补）/③G-21 状态行待 R2 监督侧回写/④P1-1 用例断言语义按三方共享 fixture 重构（提请 review 关注）。4 次脚本级失败均 tester 自身构造问题。独立脚本 41+1 断言存档临时目录、仓库零残留。

R1: committer **NEEDS_CHANGES**（2026-10-31 21:48）：**P1×1**——retag 对零命中候选块不清理旧标（别名删除/restricted 化后旧 tag 永久残留：rows 只收命中行、if rows 才替换、空 rows 早退——块级整替语义不成立；lagging 永不收敛；m2s-6 实体召回将按已删别名/已 restricted 实体返回旧块证据〔T-S9 残留〕；修法：候选 rid 全量传替换方法先清后插+按 chunk/doc/version 收窄+回归用例〔删别名+restricted 化对称面〕——Tester V10 只验投递未验删除后清理）；**P2×4**——P2-1 对账把 pending 版本标行当悬挂行删（存活谓词仅 active_version——inline 并发窗口同事务打标承诺被静默撤销；修：谓词含 pending_version+防 rid 复用+用例）/P2-2 tombstone 第 4 挂点无仓库用例（V11 一次性实证不替代常驻回归）/P2-3 test_tag_02 测试栈未接 tagger「仅落后块重标」名实不符+别名删除零覆盖/P2-4 .env.example 未登记 LATTICE_SEM_RETAG_RECONCILE_INTERVAL_S；**P3×15**（pg json CHECK 接受登记/0008 前存量边缘崩溃/切换后 enqueue 失败误报/retag_enqueued 未持久化/失败不节流/replace 返回值/常量未用/快照体积+无 GC〔POC 接受登记〕/default_reading 声明在 fuzzy_only·restricted 上 inert/外部仓 schema 需同步 default_reading/测试卫生若干〔out2 空断言/固定 NOW 节流锚等〕/G-21 仓库覆盖缺口〔relations 冷热等价仅临时脚本+PG FK 仅直查〕/eval harness 无 tagger/对账报告字段名实/legacy activated_at NULL）；**边界 5 条**：①ambiguous=true mention 打标处置（现状第一候选落标——与 annotate 契约精神冲突；建议 skip fail-closed，与 P1 修复联动）②对账存活谓词含 pending？（建议按 P2 修）③构建侧防风暴+对账保证最终收敛口径（建议接受+登记）④span/matched_by 按冻结 DDL（已闭合）⑤YAML 外部仓 schema 同步 default_reading（登记/ops）。**六条出入全接受**（①relations 必需/②首建宁投勿漏/③>0+节流/④DDL 载体/⑤实体级 default_reading/⑥A1 验收面）；观察①接受登记/②要求补仓库用例/③ R2 docs/④接受。R2 docs 批清单八项已列（known-gaps G-21 收口+残留/TEST-CASES v1.9.9/AGENTS/_m2-plan/.env.example 等）。

**R1 用户裁定**（2026-10-31 21:57「按建议执行」——通俗复述后确认）：**①歧义打标=skip**（fail-closed——消歧未定不落标，与 T-S9 原则同向；与 P1 修复联动：零命中+歧义跳过都不留旧标）；**②对账存活谓词含 pending_version**（按 P2 修——保护同事务打标承诺+防 rid 复用+用例）；**③接受双层口径**（构建侧别名 diff 防风暴+对账 >0 即投 24h 节流保最终一致——known-gaps 登记）；④已闭合；⑤YAML 外部仓 schema 同步 default_reading 登记 ops 项。六条出入+观察①③④接受。R2 修复=P1+P2×4+①②代码+边界③⑤登记（known-gaps G-21 收口回写随 R2 docs 批——监督侧已落工作区）。

R2: coder 完成（2026-10-31 22:14，commit `241ee24`，10 文件 +434/−86；父 0c127db）：**P1 修**（sem_replace_chunk_tags 签名增 clear——先对全部候选三元组 DELETE 再插、rows 空也进事务；run_retag_task 传全批候选；用例：别名删→retag 旧 tag 清零+lagging 收敛=0/restricted 化→**对账补投**清零〔恰实证裁定③双层口径〕——双后端）；**P2-1 修**（对账 4 处存活谓词含 pending_version+三元组收窄；用例 stop_after='index_fts' 造态 v2 标行存活）；**P2-2** tombstone 第 4 挂点仓库用例（窗口内不删+到期同事务清零）；**P2-3** test_tag_02 栈接 tagger+前置断言 r1 已打标（名实相符）；**P2-4** .env.example 新键模板；**裁定①** compute_sem_tags 对 ambiguous=true skip 不落标+用例（无佐证零行〔红灯=落了第一候选〕/共现定案落标对照）；**P3-2/3 顺手**（无快照回退+warning/切换后投递 try/except）。不做 P3-1/4~15（登记）。自测：TDD 红灯逐项（P1 两用例/P2-1/P2-2/裁定①）；门禁 **GATE PASS 1386+1**（pg 臂 488=455+33，双模式 0 skipped，1376+1→1386+1 +10）；入库纪律自证（grep 计数=0）；docs 批 G-21 收口回写原样入库。

R2: tester **PASS+可收敛**（2026-10-31 22:30，testedSha=241ee24）：独立场景 W1~W8 全过——**P1**（W1 别名删→清零+lagging=0/W2 restricted 化走**对账补投**实证裁定③双层口径/W3 rid 复用防御三元组收窄双向/W4 混合批零命中块也清+rev 追平；读码互证 clear 先 DELETE·rows 空也进事务）；**P2-1**（W5 pending 保护+NULL 安全+双方言 4 处谓词对称）；P2-2/3/4（仓库用例/栈读码核实同 service+前置断言/模板行在场）；**裁定①**（W6a skip 零行/W6b·c 共现·default 定案照常落标/W6d 黄金集口径零冲突——评测面不经 compute_sem_tags）；P3-2/3（W7 回退 live+告警实证/W8 已 ready 不受投递失败影响）。门禁 **GATE PASS 1386+1**（pg 臂 488=455+33，双模式 0 skipped，+10=5 函数×双后端精确对账）。回归：R1 脚本 41 断言新 HEAD 重跑全绿+sem_replace 签名影响面读码（ingest 走 insert 内部独立 DELETE+INSERT 零影响）。0 IMPL_BUG/0 SPEC_GAP；OBSERVATION 2（P3 剩余项 manifest handover 核点/untagged 恒候选=A-14 已知形态）。**「可收敛——建议推进 Committer R2 复审并进入交付」**。

R2: committer **APPROVED**（2026-10-31 22:38 终审，reviewedSha=241ee24 二一致）：**P1 闭环**（clear 参数实现与建议一致——先 DELETE 后 INSERT 同事务/三元组收窄/rows 空早退废除/全仓唯一调用方+ingest 零影响；W1~W4 独立实证+仓库回归双后端；**TC-BUILD-05 删侧闭环**+restricted 化对账补投闭环）；P2-1~4 全闭环（4 处谓词×双方言+NULL 安全/常驻回归/名实相符+两形态显式分离/模板行）；裁定①闭环（skip fail-closed+W6a~d 零冲突）；P3-2/3 闭环；docs 批与 R1 建议清单一致——G-21 收口+残留 8 项+m2s-4 P3 核销段（**3 项 R3 终审补登记遗漏——归档批补**：r8 TC-SEM-06 无 build 注句/P3-16 annotate 仅捕 ValueError 等）。新引入面审查无新 P1/P2（clear 签名/测试栈/compute skip 影响面）。**无需 R3 代码轮**；建议交付归档批（docs-only，reviewedSha=归档 HEAD 沿先例）。**双通过达成（round=2 收敛）**。〔终审报告尾部被平台截断——结论与核验主体完整存档于下〕

**交付链**（2026-10-31 22:41 用户确认交付）：① 归档 docs-only commit（检查点终态+3 项 m2s-4 P3 补登记+TEST-CASES v1.9.9+AGENTS/_m2-plan 终态——reviewedSha 按先例更新为归档 HEAD、testedSha 保持 241ee24）→ ② Coder push+PR → ③ Committer 留痕 → ④ manifest → ⑤ 待用户合入。

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

<details><summary>R1 Tester 报告全文（2026-10-31 21:32，testVerdict=PASS）</summary>

**V11 PASS**——tombstone 90 天第 4 挂点同事务 untag 实证（purged=1、标行零残留）。全部验证面完成，输出最终报告。

---

# m2s-5 R1 验证报告（task-knowledge-lattice-m2s-5）

**testedSha**: `0c127db7fb4458de80cb61bfff5efb4db8b93ac5`（HEAD 核验 ✓，父=2cb2277 ✓）

## 一、跑了哪些用例

### 1. TDD 独立复跑（HEAD 直跑，不采信 coder 红灯/绿灯）
| 套件 | 双后端结果 |
|---|---|
| test_tag_01_ingest.py | 12 passed |
| test_tag_02_retag.py | 12 passed |
| test_tag_03_untag_reconcile.py | 12 passed |
| test_g21_build_snapshots.py | 8 passed |
| test_m2s5_followups.py | 9 passed |
| **合计** | **53 passed, 0 skipped**（无 DSN 首跑 29 passed + 24 skipped 全为 pg 臂形态，设 DSN 后清零） |

### 2. 门禁全量（`docker start lattice-pg` + DSN + scripts/test_gate.sh）
```
[pytest]   OK：1376 passed, 1 deselected, 3 warnings in 238.28s
[pytest-O] OK：1376 passed, 1 deselected, 3 warnings in 238.28s
GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
（pg 臂 483 条用例全实跑：[pg] 参数化 450 + PG 专用 33）
```
- **基线对账**：1323+1 → 1376+1，+53 与 5 新文件用例数**精确一致**；pg 臂 483=450+33 与申报一致；**skip 总数 0**
- **回归核对**：存量测试**零删除**（git diff 全 tests/ 仅 2 个 `-def` = G-21 两旧钉死用例按新语义**改名改写**——检查点申报内，断言由「服务 live」反转为「服务快照」，非弱化）

### 3. 验收用例逐条（对照 TEST-CASES 用例正文）
- **TC-TAG-01 ✅**：同事务 rollback（FK 违例注入→块+标同灭，L151）/失败不阻断（mock 抛错→task done+searchable_full+`semantic.tag_failed` 审计，L178）/restricted 不落标（L142）/concept 类可命中=A1（L248）；无构建静默跳过不误报（L206）
- **TC-TAG-02 ✅**：仅落后块重标+dict_rev 追平（L167）；无行块补标（L206）；**claim 尾序可观察**（行为断言 L272 + 双方言读码互证：sqlite L1309 / pg L1257 同 `ORDER BY CASE WHEN type='semantic_retag' THEN 1 ELSE 0 END`）；幂等重跑零候选收尾（独立 V5）
- **TC-TAG-03 ✅**：悬挂行/实体亡行物理清理+计数报告；**落后行不被对账改写**（只报告+补投，L217-222 断言 dict_rev 仍旧值）
- **TC-BUILD-05 ✅**：别名增→投递（payload 携 rev，L104）；仅 definition 变→不投（L151）；**首建投递宁投勿漏+无块幂等收尾**（L155 + 独立 V10 补别名「删」对称面与分量缺省 fail-safe 四态）
- **T-S10 ✅**：版本切换 untag（L103）/pending failed T8 untag（L122）/删文档 untag（L151）三用例；**第 4 挂点 tombstone 90 天**（test_tag_03 未覆盖）经本报告独立实证 V11 PASS（purged=1、标行零残留）——T-S10 用例正文仅要求前两点，全覆盖
- **G-21 反转 ✅**：0008 双方言（**pg 直查：水位 8、sem_build_snapshots 三列+FK CASCADE；sqlite PRAGMA user_version=8**）；ready 同事务写快照；**冷缓存服务 build 产物**（窗口新概念零命中，test_g21 L68 + r3 改写两用例）；**评测拦下词典重启不被服务**（L115）；无快照回退 live+告警（L152）；**快照含 relations 冷热等价**（独立 V9：共现消解 resolved_by='cooccurrence' 快照/同源冷实例逐字段一致——出入①实证）

### 4. B1/B2 深挖（防自证）
- **V1 独立计算器互证 ✅**：自写严格口径计算器（独立遍历黄金集）与 `run_recognition_eval` 分母=20/分子=20 双向吻合，ambiguity=1.000 ≥ 0.85 过门；B2 落地后黄金集全定案（宽松=严格=20）与 README「0.90→1.0」登记一致；收紧区分度由 test_b1 stub 对照承载（同数据 ambiguous=true 分子 0 / false 分子 20）
- **V2 s109/s117 ✅**：独立 seed 重建→annotate→`resolved_by='default'`、ambiguous=False、实体正确、confidence=0.9（ceiling 精确）
- **B2 全链 ✅**：YAML 校验（值∈别名面+全局唯一，实现 yaml_corpus L596-609）、第⑤级消解（annotator L289-294）、**未声明不落回隐式第一候选**（对照用例 L202 断言仍 ambiguous+candidates 照出）
- **V3 restricted compute 侧双保险 ✅**（手工快照绕过入机滤→compute 仍滤）；**V4 大文本 >4000 跳过 ✅**

### 5. 交叉面回归 + 6. 边界防御
- ingest 主管线零回归（门禁 1376 全绿含全部存量；tagger 依赖注入保分层——app.py 装配点、core/docs 零 semantic import）；worker 既有任务+maintenance 零干扰（claim 尾序仅 retag 排尾）；**迁移水位 7→8 断言**全线同步（test_scaf_03 + 回归探针让位 0009）
- **V5 retag 批间删块竞态 ✅**（batch_rows=1 强制分批、批间直删 5 块→任务 done 不炸、已删块不再处理；直删绕过 untag 挂点产生的悬挂行由对账兜底清理归零——design §4 预期形态）；**V6 对账节流三态 ✅**（interval=0 强制投/在队去重/24h 窗口内节流+窗外恢复）；**V7 快照损坏 JSON ✅**（sqlite json_valid CHECK 拦截 IntegrityError）

## 二、失败项
无 IMPL_BUG。验证过程中 4 次脚本级失败均为**我的验证脚本构造问题**（frozen dataclass 赋值/helpers 传参/节流锚误删/relations YAML 撞 pure 规则），修正后全绿，与被测实现无关。

## 三、问题分级
- **IMPL_BUG**：无
- **SPEC_GAP**：无
- **OBSERVATION**（4 项，均不阻塞）：
  1. pg 侧 `snapshot_json` 无 json_valid CHECK（sqlite 有）——迁移注释已申报由写入方保证；若 pg 侧快照被**外部篡改**为损坏 JSON，`get_annotator` 的 json.loads 会抛错而非回退 live。正常写入路径不受影响，登记观察。
  2. tombstone 90 天 untag（第 4 挂点）无专项仓库测试——test_tag_03 覆盖 3/4 挂点，第 4 挂点由本报告 V11 独立实证 PASS；后续触碰 `delete_aged_tombstones` 时可补一行断言。
  3. known-gaps G-21 状态行仍写「方案 B 已接受」——检查点 D 节 docs 批（含 G-21 收口回写）归监督侧 R2 落笔、coder 原样 commit，非本轮 coder 缺陷。
  4. R3 改写后 P1-1 用例的 `ann.annotate` 断言从「零 mention」改为「restricted 实体不出现」——共享别名下公开侧命中保留，符合 T-S9「存在性零泄露」口径，提请 review 关注该断言语义已按三方共享 fixture 重构。

## 四、结论

**testVerdict: PASS**

- 门禁数字原样引用：`1376 passed, 1 deselected` × 双模式，`0 skipped`，pg 臂 `483 = [pg] 参数化 450 + PG 专用 33`，GATE PASS
- testedSha：`0c127db7fb4458de80cb61bfff5efb4db8b93ac5`
- 独立验证脚本存档于 `/var/folders/9k/4ts9r9n92737zx0fjkqtrnym0000gn/T/opencode/m2s5_indep_verify.test.py`（41+1 项断言全绿，仓库零残留）

</details>

<details><summary>R2 Tester 报告全文（2026-10-31 22:30，testVerdict=PASS+可收敛）</summary>

**testedSha**: `241ee242196066546b98729cf5639a0eb22565fa`（HEAD 核验 ✓，父=0c127db ✓，10 文件 +434/−86 与申报一致）

## 一、逐项复验结果（独立构造场景，不用 coder fixture）

### 1. P1 复验（核心）✅
| 项 | 独立验证 | 证据 |
|---|---|---|
| ① 别名删→retag 清旧标 | **W1 PASS**：独立造态 r1 别名「甲面」打标→r2 删别名→构建→run_retag_task→**旧 tag 零残留（left=0）+对账 lagging=0** | `result={'chunks_retagged': 1}`、`lagging_chunks: 0` |
| ② restricted 化对称+裁定③ | **W2 PASS**：YAML 纯人工 r1 normal 打标→r2 改 restricted→**构建面不投（built_retag=[]——sensitivity 变化非别名 diff，TC-BUILD-05 语义保持）**→**对账补投（retag_enqueued=[org:tax]）**→retag 清零。双层口径实证：构建侧防风暴+对账保最终一致 | 三断言链全过 |
| ③ rid 复用防御 | **W3 PASS**：同 chunk_rid=424242、异 (doc,version,entity) 两行共存（模拟 rowid 复用），clear 指定旧三元组→仅旧行删、新行存活；反向 clear 新元组不误删旧行 | `left=[('d_new', 2)]` / `left=[('d_old',)]` |
| ④ rows 非空混合批 | **W4 PASS**：同批候选 doc1（命中「甲面」重标存活）+doc2（仅含已删「乙面」零命中）→**零命中块旧标清除（doc2_rows=0）**、全部存活行 rev 追平 r2 | `chunks_retagged: 2`（含零命中块） |

实现读码互证：`sem_replace_chunk_tags(org_id, rows, *, clear=None)` 双方言同构（sqlite L2976/pg L2394）——clear 全批候选三元组先 DELETE、rows 空也进事务（`if not clear_rows and not rows` 才早退）、DELETE 按 `(chunk_rid, doc_id, version)` 三元组收窄。

### 2. P2-1 复验 ✅
- **W5 PASS（独立 stop_after='index_fts' 造态）**：v2 pending_version=2、v2 标行已同事务写→对账 `stale_chunks_removed=0`、v2 pending 行存活、**v1 活跃行不受影响**；**NULL pending 安全**（无覆盖上传文档活跃行存活——`OR c.version = d.pending_version` 对 NULL 不误杀）。
- 实现核验：sqlite/pg 各 **4 处**谓词（悬挂 DELETE+计数、lagging、untagged）全部含 pending_version+三元组收窄，双方言对称。

### 3. P2-2/P2-3/P2-4 复验 ✅
- **P2-2**：仓库用例 `test_p2_2_tombstone_cleanup_untags_fourth_hook`（test_tag_03 L322+）——窗口内不删（before=92 天前→removed==0）+到期同事务清 tag（before=90 天前→removed==1+零残留），窗口边界逻辑验算正确；替代我 R1 的一次性 V11 成常驻回归。
- **P2-3**：读测试源码核实——`_run_task` 复用 `_make_service`（带 tagger），与 `_ingest_doc` 同 service；`test_tc_tag_02_retag_retags_only_lagging_blocks` 新增前置断言 `r1_rows 非空`（真「落后块」而非无行块，名实相符）。
- **P2-4**：`.env.example` L90-93 新键模板在场（含 0=每次投注释）。

### 4. 裁定① 复验 ✅
- **W6a**：独立构造无佐证共享别名「歧面」→annotate ambiguous=true→`compute_sem_tags` **零行**（fail-closed）。
- **W6b 对照**：共现定案（resolved_by='cooccurrence'）照常落标（rows 2 行）。
- **W6c 对照**：default_reading 第⑤级定案照常落标（rows 1 行）。
- **W6d 黄金集口径核实**：黄金集 20 个 pos_ambiguous 歧义 span 经 B2 全定案（annotate 面 skip 面恒空=0）——评测四指标在 evalrun 面计算不经 compute_sem_tags，**裁定①与黄金集/评测零冲突**。
- coder 对照用例 `test_ruling_1_ambiguous_mentions_skipped_when_tagging` 双面（skip+cooccurrence 落标）在门禁内。

### 5. 门禁全量 ✅
```
[pytest]   OK：1386 passed, 1 deselected, 3 warnings in 247.54s
[pytest-O] OK：1386 passed, 1 deselected, 3 warnings in 247.54s
GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
（pg 臂 488 条用例全实跑：[pg] 参数化 455 + PG 专用 33）
```
- **基线对账**：1376+1 → 1386+1 = **+10 = 5 新用例函数 × 双后端精确对账**；pg 臂 488=455+33 与申报一致；**skip=0**

### 6. 回归 ✅
- **R1 独立脚本（41 断言）在新 HEAD 重跑全绿**：同事务打标/restricted 双保险/大文本/retag 批间竞态/对账节流三态/快照损坏 CHECK/G-21 relations 冷热等价/B1 独立计算器/s109 s117/default_reading/迁移水位——零回归。
- **sem_replace_chunk_tags 签名变更影响面**：全仓 grep 唯一调用方=`tagging.py:197`（retag 执行体，带 clear）；**ingest 同事务打标走 `insert()` 内部独立 DELETE+INSERT（backend.py L240-243），不经此方法**——签名变更对 ingest 路径零影响（门禁 test_tag_01 全过佐证）。
- 入库纪律：HEAD 无 supervised-coding.md/检查点（grep 计数=0 ✓）；工作区监督侧文件未入库。
- docs 批：known-gaps G-21 状态改「**已收口**」+残留 8 项登记（含裁定③双层口径⑤/裁定①⑧/外部 schema⑦/GC③），与 Committer 建议清单一致——监督侧落笔范围。

### 7. P3-2/3 复验 ✅
- **P3-2（W7）**：强制触发 run_retag_task 快照重建分支+快照行已删→**回退 live 不炸（任务 done）+告警实证**（`"retag target build has no snapshot ... fallback to live snapshot"` 日志捕获）。
- **P3-3（W8）**：monkeypatch enqueue 抛错→**已 ready 构建终态不受影响**（status=ready、current=r2）。

## 二、失败项
无。验证过程 4 次脚本构造问题（实体 FK/UNIQUE 约束、W6c 同步实体撞 pure 键、W7 同 rev skip、import 路径）均为 tester 自身脚本修正，与被测实现无关。

## 三、问题分级
- **IMPL_BUG**：无
- **SPEC_GAP**：无
- **OBSERVATION**（2 项，不阻塞）：
  1. P3-4/5/6/7/9/11~15 未逐项落 known-gaps（残留登记收了 P3-1/2/8 + 边界③⑤ + 裁定①等主要项）——known-gaps 属监督侧 docs 批职责，剩余项多为测试卫生/可观测性/名实，不阻塞；建议监督侧在交付 manifest 的 handover 清单核点。
  2. W1 对账报告见 `untagged_chunks: 1`（别名删后零命中块无行→恒为 retag 候选）——A-14 已知面+裁定③节流覆盖，known-gaps 残留⑥已登记，符合预期形态。

## 四、结论

**testVerdict: PASS**

- 门禁数字原样引用：`1386 passed, 1 deselected` × 双模式（常规/python -O），`0 skipped`，pg 臂 `488 = [pg] 参数化 455 + PG 专用 33`，GATE PASS
- R2 修复六项（P1+P2×4+裁定①）+P3-2/3 顺手项**全部独立复验通过**；R1 面零回归；+10 精确对账；双方言对称；入库纪律合规
- **收敛判定建议**：**可收敛**——P1 阻塞项已修且独立实证（旧标清零+lagging 收敛+rid 防御+混合批），P2 四项全落，裁定①②③代码与登记面齐备；剩余 P3 均为登记类残留（known-gaps 已收主要项）。建议监督侧推进 Committer R2 复审并进入交付（PR/manifest）。
- testedSha：`241ee242196066546b98729cf5639a0eb22565fa`
- 复验脚本存档：`/var/folders/.../T/opencode/m2s5_r2_verify.test.py`（31 断言）+ R1 脚本重跑（41 断言），仓库零残留

</details>

<details><summary>R2 Committer 终审报告全文（2026-10-31 22:38，reviewVerdict=APPROVED——尾部平台截断，结论与核验主体完整）</summary>

## 0. 审查对象与门禁采信

- 审查对象：`HEAD = 241ee242196066546b98729cf5639a0eb22565fa`，父提交 `0c127db` ✓（`git log --oneline -1` 核验）；R2 diff 10 文件 +434/−86 ✓ 与申报一致。
- **diff 完整性**：R2 10 文件不含 `.opencode/agent/supervised-coding.md`、不含 m2s-5 检查点（工作区监督侧文件未入库）；R2 commit 树干净；R1 违规项未复发。
- **门禁采信**：R2 Tester 实测 `1386 passed, 1 deselected × 双模式`、`0 skipped`、pg 臂 `488 = [pg] 参数化 455 + PG 专用 33`；`1376+1 → 1386+1 = +10` 与 R2 新增 5 个测试函数 × 双后端精确对账；R1 独立脚本 41+1 断言在新 HEAD 重跑全绿。
- **测试门禁审查**：R2 diff 无新增 skip/xfail，无测试函数删除；`test_tc_tag_02_retag_retags_only_lagging_blocks` 为加强前置断言（新增 r1 已打标断言），非弱化。
- 本轮未重跑门禁（只读终审，以 Tester 独立复跑证据 + 计数对账为准）；交付 manifest 应附 `scripts/test_gate.sh` 原始输出。
- **CASE_BUG**：未收到裁定请求（R2 Tester 0 IMPL_BUG/0 SPEC_GAP，2 观察项）。

---

## 1. 终审结论

**reviewVerdict: APPROVED**

- R1 的 **P1 已修复并独立实证**；P2 四项全部落实；裁定①（歧义 skip）/②（pending 生存谓词）/③（双层口径）代码与登记齐备；P3-2/3 顺手项完成。
- 未发现新的 P1/P2 级问题；剩余均为 **P3 登记/归档类**（下方 §4），按先例可登记放行。
- **无需 R3 代码轮**；建议进入交付归档批（docs-only），归档后按先例 `reviewedSha=归档 HEAD`。

---

## 2. 逐项闭环核验

### P1（R1 阻塞项）—— 已闭环 ✅

- **实现质量**：
  - `run_retag_task` 现以**本批全部候选**构造 `clear`（含零命中候选），并调用 `sem_replace_chunk_tags(org_id, rows, clear=clear)`（`tagging.py:181-197`）；不再 `if rows:` 早退。
  - 双方言实现先 `DELETE` clear 集再 `INSERT` 命中行，同一事务；`clear` 空且 rows 空才早退；删除按 `(chunk_rid, doc_id, version)` 三元组收窄（sqlite `backend.py:2982-3018` / pg `2399-2436`）。
  - `clear` 缺省回退 `rows` 自身（无第三态调用方）；**全仓唯一调用方**= `tagging.py:197`，ingest 同事务打标仍走 `insert()` 内部独立 DELETE+INSERT，签名变更对 ingest 零影响（Tester 读码互证，门禁全过）。
- **独立证据**：
  - W1：别名删除 → retag → 旧 tag 零残留 + 对账 `lagging=0`。
  - W2：restricted 化 → 构建面不投（符合 TC-BUILD-05 别名 diff 语义）→ **对账补投** → retag 清零（裁定③双层口径实证）。
  - W3：同 rid 异 (doc,version) 两行共存——clear 旧三元组仅删旧行、新行存活；反向 clear 新三元组不误删旧行（rid 复用防御双向）。
  - W4：混合批——有命中块重标存活 + 零命中块旧标清除，rev 全追平。
  - 仓库回归：`test_p1_alias_deleted_retag_clears_stale_tags` / `test_p1_restricted_migration_retag_clears_stale_tags`（双后端，门禁内）。
- **R1「删侧」结论**：TC-BUILD-05 的**删**侧（别名删除触发投递 + retag 清旧标）现已闭环；restricted 化走对账补投也闭环。

### P2-1（pending 版本标行被对账误删）—— 已闭环 ✅

- 双方言 **4 处谓词**（悬挂计数、悬挂 DELETE、lagging、untagged）全部改为存活面 `(c.version = d.active_version OR c.version = d.pending_version)` + `(chunk_rid, doc_id, version)` 三元组匹配（sqlite `3019-3100` / pg `2438-2510`）。
- **NULL 安全**：`pending_version IS NULL` 时 `=` 为 false，OR 由 active 兜底；Tester W5 独立验证「无覆盖上传的活跃行存活」。
- 仓库回归：`test_p2_1_pending_version_tags_survive_reconcile`（`stop_after='index_fts'` 造 v2 pending 态；`stale_chunks_removed==0`、v2/v1 标行均存活；双后端）。
- 说明：R2 中 lagging/untagged **计数**也含 pending，但 `sem_retag_candidates` 仍仅 active；属 P3 观察（见 §4），不影响本段数据正确性。

### P2-2（tombstone 第 4 挂点无仓库用例）—— 已闭环 ✅

- `test_p2_2_tombstone_cleanup_untags_fourth_hook`：窗口内（before=92 天前，tombstoned_at=91 天前）`removed==0` 且 tag 保留；到期（before=90 天前）`removed==1` 且 tag 零残留；双后端。
- 替代 R1 一次性 V11，成为常驻回归。

### P2-3（retag 测试栈未接 tagger）—— 已闭环 ✅

- `_make_service` 带 tagger；`_ingest_doc`/`_run_task` 复用同一 service；`test_tc_tag_02_retag_retags_only_lagging_blocks` 新增 `r1_rows` 非空前置断言，r1 真实打标后 r2 重标，名实相符。
- 「无行块补标」形态仍由 `test_tc_tag_02_retag_picks_up_untagged_blocks` 用无 tagger service 显式构造——两种形态不再混淆。

### P2-4（`.env.example` 新键）—— 已闭环 ✅

- `.env.example:90-93` 已补 `LATTICE_SEM_RETAG_RECONCILE_INTERVAL_S=86400` 模板（含「0=每次投」注释）。

### 裁定①（歧义打标 skip）—— 已闭环 ✅

- `compute_sem_tags` 对 `m.get("ambiguous")` **跳过**，restricted 双滤保留；`test_ruling_1_ambiguous_mentions_skipped_when_tagging` 覆盖「无佐证歧义零行」+「共现定案对照落标」。
- Tester W6a-W6d：skip 零行 / 共现落标 / default⑤ 落标 / 黄金集零冲突（golden eval 走 `run_recognition_eval`，不经 `compute_sem_tags`）——与 B1/B2 无冲突。

### P3-2 / P3-3 顺手项 —— 已闭环 ✅

- P3-2：retag 目标无快照时回退 `sem_active_snapshot` + warning，消除 `json.loads(None)` 边缘崩溃（W7 实证，日志捕获）。
- P3-3：`_maybe_enqueue_retag` 全段 try/except，已 ready 构建不因投递失败转失败（W8 实证 status=ready、current 正确）。

### docs 批（known-gaps G-21 收口 + 残留 8 项 + m2s-4 P3 核销段）

- **G-21 状态**：已改为 **已收口**（m2s-5 方案 A：0008 双方言附表/switch·reactivate 同事务/get_annotator·render_l0 按 current build/冷缓存与重启服务 build 产物/无快照回退 live+告警）——与 R1 §5 建议一致。
- **残留 8 项**：①PG snapshot 无 json_valid CHECK；②0008 前存量 ready 无快照/同 rev skipped 不回填；③relations 快照体积大且无旧 build GC；④外部篡改快照抛错不回退；⑤对账双层口径（裁定③）；⑥无行块恒 retag 候选（A-14）；⑦YAML 外部仓 schema 需放开 default_reading；⑧歧义打标 skip（裁定①）——与 R1 建议 + 用户裁定一致。
- **m2s-4 P3 核销段**：已闭（B1、B2、fuzzy_only、`_audit_build`、R3 用例空转两项、latin 全角）/未闭（TC-BUILD-04、l0_extra、拉丁粘接、alias confidence、precision 分母、mixed-mode、double_build、maintenance 前代四项）——**与 R1 §5 显式清单一致**，但有 **3 项 R3 终审补登记遗漏**（见 §4 P3-docs），归档批需补。

---

## 3. 新引入面审查（R2 diff 10 文件）

- **`sem_replace_chunk_tags` 协议签名**：新增 `clear: Sequence[dict] | None`；全仓唯一调用方 `tagging.py:197`；ingest 路径不经该函数；无其他测试桩/实现受影响——**无新问题**。
- **测试栈改动**：`_run_task` 改带 tagger 后，依赖「无行块」的既有用例已显式改用 plain service；`test_runner`/`test_priority` 等仍过；门禁 1386 全绿——**无回归**。
- **`compute_sem_tags` skip**：仅在打标面生效，评测面 `evalrun` 不受影响；W6d 已证。
- **`P2-1 4 处谓词`**：双方言对称〔报告至此被平台截断——以下为检查点轮次记录中的核验摘要补全〕

**〔截断前已明确的结论〕**：§1 终审结论 APPROVED；无需 R3 代码轮；建议交付归档批（docs-only、reviewedSha=归档 HEAD）；P3-docs 3 项 m2s-4 R3 终审补登记遗漏归档批补（r8 TC-SEM-06「无 build 返回空」注句/P3-16 annotate 仅捕 ValueError/——核销段「未闭」清单与 G-21 残留对齐后差额项）；三面评价文本截断——以轮次记录摘要为准（Coder：P1/P2 修复小而准+入库纪律合规；Tester：W1~W8 独立实证+影响面读码互证证据链扎实；监督侧：docs 批与建议清单一致、3 项补登记归档批落）。

</details>

<details><summary>R1 Committer 报告全文（2026-10-31 21:48，reviewVerdict=NEEDS_CHANGES）</summary>

## 0. 审查对象与基线核对

- 审查对象：`HEAD = 0c127db7fb4458de80cb61bfff5efb4db8b93ac5`，父提交 `2cb2277` ✓，`git log` 核验一致。
- `git diff 2cb2277..0c127db`：33 文件 +2606/−145 ✓（与检查点申报一致）。
- **diff 完整性**：33 文件不含 `.opencode/agent/supervised-coding.md`、不含 m2s-5 检查点未完成态；违规首 commit `9373f11` 已不在任何 ref（soft reset 生效）。当前工作区仍有监督侧编辑（`M .opencode/agent/supervised-coding.md` + 未跟踪检查点），属监督侧文件，未入 HEAD。
- **门禁证据**（检查点 R1 + Tester 独立复跑）：`1376 passed, 1 deselected × 双模式`，`0 skipped`，pg 臂 `483 = [pg] 参数化 450 + PG 专用 33`；`1323+1 → 1376+1 = +53` 与 5 个新文件「29 个测试函数 × 后端参数化」精确对账（tag_01 12 + tag_02 12 + tag_03 12 + g21 8 + m2s5 9 = 53）。
- **测试门禁审查**：diff 中无新增 `skip/skipif/xfail`，无测试删除；2 个 `-def` 为 G-21 旧钉死用例按新语义改名改写（申报在案、断言方向反转为「服务 build 快照」而非弱化）；无断言放宽。
- 本次未重跑门禁（会话只读/门禁命令不在放行范围），以 Tester 独立复跑数字与用例计数对账为准；交付时 evidence manifest 需附原始门禁日志（见 §6）。
- **CASE_BUG**：未收到裁定请求（Tester 0 IMPL_BUG/0 SPEC_GAP，4 观察项）。

---

## 1. 问题清单

### P1（阻塞）

**[P1] retag 对「零命中候选块」不清理旧标——别名删除 / restricted 化后旧 tag 永久残留，且 lagging 永不收敛**

- 位置：
  - `src/knowledge_lattice/core/semantic/tagging.py:171-180`（`rows` 只收命中行；`if rows:` 才调用替换）
  - `src/knowledge_lattice/store/sqlite/backend.py:2982`（`rids = sorted({r["chunk_rid"] for r in rows})`）
  - `src/knowledge_lattice/store/postgres/backend.py:2399`（同构）
- 场景：r1 块经别名 A 打上实体 E 的 tag；r2 删除别名 A（或 E 的 sensitivity 改为 `restricted`）→ 构建 r2 → retag 选中该落后块 → 重新 annotate 后**零命中** → `rows` 为空（或只含同批其他块的行）→ 替换方法只按 `rows` 的 rid 集删除，**该块旧 tag 行不清除**。
- 后果：
  - 旧 tag 的 `dict_rev` 永远是 r1，`lagging_chunks` 永远 >0，每次 retag/对账都重复扫描；「块级标签整替」语义不成立。
  - 未来 m2s-6 实体召回会按已删除的别名/已 restricted 的实体返回旧块证据（错误召回；restricted 场景为潜在 T-S9 残留）。
  - 该缺陷正好落在 TC-BUILD-05 的**删**侧（别名删除 diff 投递后 retag 不清理），Tester 的 V10 只验证了「删」触发投递，未验证删除后的 tag 清理。
- 建议修复：
  1. retag 执行体把**本批全部候选 rid** 传给替换方法（不只是 `rows` 的 rid）；替换方法签名改为同时接收 `clear_rids`（或新增同一事务内的清理入口），先对全部候选 rid `DELETE`，再插入命中行；`rows` 为空时也必须进入事务清理，不能早退。
  2. 建议同时按 `(chunk_rid, doc_id, version)` 收窄删除/插入条件，避免批间版本切换或 SQLite rid 复用误删新块（现有 rid-only 删除在极端 rid 复用下会波及其他块）。
  3. 补回归用例：r1 有别名 A → 摄取打标 → r2 删 A → retag → 断言该块旧 tag 零残留（可同时补 sensitivity 改 restricted 的对称面）。
- 说明：此问题未被 Tester PASS 覆盖；`tests/test_tag_02_retag.py` 的「仅落后块重标」用例本身没有构造 r1 已打标块（见 P2-2），因此无法暴露。

### P2（交付前应修）

**[P2] 对账把「pending 版本」标行当悬挂行物理删除——inline 并发/崩溃窗口下同事务打标承诺被静默撤销**

- 位置：`src/knowledge_lattice/store/sqlite/backend.py:3016-3030`、`store/postgres/backend.py:2433-2446`（存活判定仅 `c.version = d.active_version`）。
- 场景：覆盖上传 v2 在 `index_fts` 已写 v2 tag，随后 embed 阶段；若 inline 模式 `kick()`（`app.py:106-115`）与兜底 loop 并发，maintenance 的 `semantic_reconcile` 可在 v2 尚未切换时运行，把 v2 的 tag 行当「非活跃版本」删掉。切换后 v2 无标，需等下一轮 retag（受 24h 节流，最长延迟一天）。
- 默认 `worker_mode=subprocess` 单 worker 串行下不可达；但 inline 是受支持模式，且该行为与「index_fts 同事务打标」设计直接矛盾。
- 建议：存活谓词改为 `c.version IN (d.active_version, d.pending_version)`（NULL 需处理），并加 `c.doc_id = ce.doc_id AND c.version = ce.version` 防 rid 复用；补「pending 版本 tag 不被对账清掉」的用例（可用 `IngestService.run_task(stop_after='index_fts')` 造态）。
- 若监督侧认定「非活跃版本 = 悬挂」是设计口径，请在 R2 文档显式登记该口径及与同事务打标的矛盾；否则按上修。

**[P2] T-S10 第 4 挂点（tombstone 90 天 untag）无仓库测试；现有 maintenance 用例也未断言 tag 行**

- 位置：`tests/test_wk_maintenance.py:85-140`（只断言 chunks/向量，无 `sem_chunk_entities`）；`tests/test_tag_03_untag_reconcile.py` 覆盖 3/4 挂点。
- `delete_aged_tombstones` 是本轮修改的生产路径（双方言），Tester V11 独立实证不能替代仓库常驻回归。
- 建议：在 `test_tag_03` 或 `test_wk_maintenance` 造一条 sem tag 行 + 过期 tombstone，调用 `delete_aged_tombstones` 后断言 tag 零残留；顺带覆盖「过期窗口内不删」的 tag 面。

**[P2] `test_tag_02` 的 retag 测试栈未真正接 tagger，「仅落后块重标」名实不符，且缺少别名删除回归**

- 位置：`tests/test_tag_02_retag.py:84-92`（`_run_task` 新建 `IngestService` **无 tagger**）；`_ingest_doc`（70-81）虽有 tagger，但只用于 `create_document`，实际 `run_task` 不走它。
- 后果：`test_tc_tag_02_retag_retags_only_lagging_blocks` 实际是「无行块补标」，没有构造 r1 已打标、r2 落后的真实场景；对 P1 的删除侧零覆盖。
- 建议：`_run_task` 复用 `_service(env)`（带 tagger）或在 `_ingest_doc` 返回的 service 上 `run_task`；断言前置 `_tag_rows` 非空（r1）；再加「r2 删别名 → retag → 旧 tag 清除」的 P1 回归。

**[P2] `.env.example` 未登记新键 `LATTICE_SEM_RETAG_RECONCILE_INTERVAL_S`**

- 位置：`src/knowledge_lattice/config.py:132` 已加字段；`.env.example` 末尾（87 行后）无对应模板行；`worker/runner.py` 的 `_worker_env` 已映射。
- 先例：m2s-4 批已把 `DAILY_SYNC_INTERVAL_S`/`EVAL_GOLDEN_PATH` 登记进 `.env.example`；本段新键应补一行注释模板（`# LATTICE_SEM_RETAG_RECONCILE_INTERVAL_S=86400`），并同步检查点 `filesChanged`。

### P3（建议/登记，不阻塞）

1. **PG `snapshot_json` 无 json_valid CHECK**（Tester 观察①）：`store/postgres/migrations/semantic/0008_sem_build_snapshots.sql:1-11` 注释已申报；与 `sem_builds.stats_json` PG 侧同风格，写入方受控。**裁定：接受登记，不要求本段补**；若追求双向言严格同构，可在 0008 加 `CHECK (snapshot_json IS JSON)`（迁移未发布，改动成本低），并在 known-gaps G-21 残留登记。
2. **retag 目标为 0008 前存量 build（无快照）时的边缘崩溃**：`tagging.py:152-155` 在 `rev != target_rev` 分支直接 `json.loads(sem_load_build_snapshot(...))`，若无快照会 `TypeError`（并发切 build + 升级存量行的极窄窗口）。建议该分支快照为 None 时回退 `sem_active_snapshot` + warning。
3. **切换已提交后 enqueue retag 失败会误报构建失败**：`build.py:464-468` 在 `sem_switch_build_ready` 成功后调 `_maybe_enqueue_retag`；若抛错，外层 except 对已 ready 行 `sem_fail_build` 零生效但任务重试，构建重跑会 skipped，retag 丢失到对账兜底。建议 try/except 记 warning，不让已成功切换的构建失败。
4. **`stats["retag_enqueued"]` 未持久化**：`build.py:433/467` 在 `stats_json` 序列化之后赋值，DB 构建报告看不到投递结果（仅任务返回值有）。不影响验收，建议补可观测性。
5. **失败 retag 不参与节流**：`maintenance.py:240-253` 只以 `done` 为节流锚；持久失败时每 300s maintenance 都会再投一条新 retag（pending 去重只在队期间生效），可能放大失败任务行。建议把最近一次 attempt/created_at 也纳入节流或登记。
6. **`sem_replace_chunk_tags` 返回 `len(rows)` 而非实际插入行数**（entity 非 active 时 `INSERT ... WHERE EXISTS` 跳过），与协议「返回插入行数」不符；建议返回真实 rowcount 或改注释。
7. **`TAG_EVENT_FAILED` 常量未被使用**（`tagging.py:40`），ingest 侧因分层用字面量 `semantic.tag_failed`（`ingest.py:904`）；可保留为文档，但存在漂移风险。
8. **快照体积/保留**：`_snapshot_json` 存整份 `sem_active_snapshot`（含 `source_system`/`curated_rev`/alias 原文/relation `source` 等 Annotator 不使用的字段）+ 全部 relations；10⁵ 节点/边量级下每 build 可能是数十 MB，且无旧 build 快照 GC。接受 POC 现状，建议 known-gaps 登记并考虑裁剪到 Annotator 最小字段/保留策略。
9. **`default_reading` 可声明在 fuzzy_only / restricted 别名上但实际 inert**：`yaml_corpus.py:596-609` 只校验「在别名面」，`build_automaton` 却不收 fuzzy_only/restricted；建议 CI 对这两类声明给 warning/error，避免配置错觉。
10. **YAML 外部仓 schema**：`default_reading` 已写入 curated_json，但 design §5.8 的 `_schema/entry.schema.json` 在外部语义仓；若该 schema `additionalProperties: false`，真实 CI 会拒绝新字段。R2 docs/ops 需登记「语义 YAML 仓需补 default_reading 属性」。
11. **测试卫生**：`test_m2s5_followups.py:197-199` `out2` 生成后无断言（注释声称共现优先于 default，但未验证）；`test_m2s5` 两处 `tempfile.mkdtemp()` 无清理；`test_tag_03.py:129` `service` 未用、`288-289` `enqueue_retag` 未用；`test_b1_golden` `backend=None` 未用；`test_tag_02:167-169` 文档声称「已同 rev 块不动/零候选」但未构造；`run_retag_task` docstring `重跑零候选` 与无行块恒候选（A-14）矛盾；`test_a5_reconcile_throttle_after_done_retag` 用固定 `NOW` 对比真实 `tasks.updated_at`，当前靠「last 在未来 → 负 age 保守节流」通过，未真正验证 24h 窗口（建议把 task.updated_at 置为 NOW 或使用真实 now）。
12. **G-21 仓库覆盖缺口**：`test_g21_build_snapshots.py:87` 只断言 `relations is not None`，relations 冷热等价（V9）仅在临时脚本；`test_migration_0008` 只查表存在，PG FK/CASCADE 仅 Tester 直查；建议补 relations 参与共现消解的冷/热一致性断言、PG FK/CASCADE 与 switch/reactivate 快照写入（含失败回滚）用例。
13. **`eval/harness.py:145`** 直接构造无 tagger 的 `IngestService`；若 m2s-6 用该 harness 做实体召回评测，文档将无 tag，建议接线或显式注明。
14. **`sem_reconcile_chunk_tags` 报告语义/文档**：协议说「无 sem_chunk_entities 行的 org 不出现」，实际会包含有 ready build 但无 tag 的 org（untagged>0）；`stale_chunks_removed` 实际计**行数**非块数；建议改字段名或改注释。
15. **对账 `lagging` 对 legacy ready 行（`activated_at IS NULL`）**：`MAX(activated_at)` 排除 NULL，升级存量 org 可能不产生 lagging 报告；已在 fallback live 面覆盖，建议登记。

---

## 2. 需求边界问题

**有**，建议回 spec/监督侧确认（不直接给 coder 猜改）：

1. **打标面对 `ambiguous=true` mention 的处置未定义**：`compute_sem_tags`（`tagging.py:56-64`）直接取 annotate 的 `mentions`，而 annotate 对未消解歧义返回 `pick[0]`（`annotator.py:323-335`，`ambiguous=true` + candidates）。因此当前会把「第一候选」写成确定命中；这与 annotate 契约「ambiguous 不自动注入、交 agent 追问」的精神可能冲突，且会在未来实体召回中产生错误证据。建议 spec 明确三选一：**skip（fail-closed，推荐）** / 全部候选落标 / 仅第一候选（现状，需接受）。若确认 skip，请与 P1 修复联动（零命中块旧标清理）。
2. **对账「存活 chunk」是否含 pending 版本**：A5 原文「active 实体/存活 chunk」与同事务打标（pending 版块也写 tag）存在解释张力；实现取 active-only 会删 pending tag（P2）。若监督侧确认 pending 属「非活跃 = 可清」，请在 R2 文档登记该口径；否则按 P2 修。
3. **TC-BUILD-05「仅 definition 不投递」与对账 lagging 全量补投的张力**：构建侧只看 aliases 分量（符合 TC-BUILD-05），但 definition/sensitivity/relation 变化使 `dict_rev` 前进，对账的 `lagging>0` 会在 24h 内再次投 retag；A5 原文写「落后超阈值」而实现是「>0」。coder ③ 已申报，建议监督侧明确接受「构建侧防风暴、对账保证最终收敛」的口径，并在 known-gaps/A-14 注记。
4. **任务原文 A2 的 span/matched_by 与 design §4 DDL**：见裁定④（以冻结 DDL 为准，不属边界缺陷）；span/matched_by 未落库，若未来实体召回需要 span 级证据，需另立 spec/迁移。
5. **YAML 外部仓 schema**：`default_reading` 需外部语义仓 schema 同步放开（见 P3-10）。

---

## 3. Coder 出入六条裁定

1. **①快照含 relations——接受**。`Annotator` 的共现消解与 L0 证据依赖 `adj`；不含 relations 则 G-21 冷/热等价不成立（V9 已实证）。体积：每 build 一份全量 relations，10⁵ 量级可能达数十 MB，且无旧 build 快照 GC；接受 POC 现状，登记残留（P3-8）。
2. **②首建「宁投勿漏」——接受**。首建前摄取的块无行，首建投递 retag 可补标；无块时零候选 done，幂等；代价仅一条空任务。TC-BUILD-05 的「别名增删」判定不受影响。注意：首建 retag 任务完成会成为 24h 节流锚，若首建后立刻有打标失败的文档，补标可能延迟至下一窗口（P3 残留，可接受）。
3. **③对账「>0 即投 + 24h 节流」——接受（附残留）**。符合「只报告+补投、不直接改标」；节流防无行块风暴。残留：无行块**永不消候选**（无标记字段，A-14 已知），每天会对有 no-hit 块的 org 全量扫描一次；失败 retag 不被节流（P3-5）；定义/敏感度变化经对账最终仍会 retag（见边界③）。
4. **④sem_tags 按 0006 DDL 载体（无 span/matched_by）——接受**。design §4 冻结 DDL 是权威（`chunk_rid/entity_id/hits/dict_rev`），任务书括号为描述性；新增列属设计变更，不应由 coder 自行加。若后续需要 span/matched_by，另立迁移/spec。
5. **⑤default_reading 挂实体级 curated（零 DDL）——接受**。入 `curated_json` → 入 `_rev_payload`/快照；YAML 校验值∈别名面+全局唯一；消解第⑤级 `resolved_by='default'`、ceiling 0.9；"未声明不落回"有对照用例（Tester V2 复证）。外部 schema 见 P3-10。
6. **⑥A1 kind 链 m2s-3 已全，本段只补验收——接受**。`test_a1_pure_concept_entity_in_snapshot_and_tagging` 覆盖 concept 纯人工实体入快照/annotate/打标；`system` 纯人工 kind 未单独用例（kind 链 m2s-3 已验），属可接受覆盖缺口（P3）。

---

## 4. 测试质量评价

**总体：高于走过场线，但存在与 P1/P2 直接相关的 holes，不能作为本段的充分回归保护。**

- **好的方面**：
  - +53 真实新增、双后端全实跑、0 skipped；测试计数与文件函数数精确对账；无 skip/删除/断言弱化。
  - Tester 独立脚本 41+1 断言覆盖 V1 独立计算器、V2 s109/s117、V3 restricted 双保险、V4 大文本、V5 批间删块、V6 节流三态、V7 损坏快照、V9 冷热等价、V11 tombstone 清理——证据链扎实。
  - G-21 反转用例设计正确：冷缓存不服务窗口新概念、评测被拦词典重启不服务、无快照回退 live+告警；旧钉死用例按新语义改写且申报。
  - T-S9 P1-1 断言语义重构（观察④）**接受**：新断言「restricted 实体不出现 + 公开侧共享别名命中保留」符合 T-S9「存在性零泄露」，不是弱化；旧「零 mention」在共享别名 fixture 下过严。
- **关键缺口**：
  - **P1 的别名删除/restricted 化 retag 清理零覆盖**；`test_tag_02` 的 retag 栈实际未接 tagger（P2-2），「仅落后块重标」名实不符。
  - **第 4 挂点 tombstone untag 无仓库用例**（P2-1 观察②）；Tester V11 只能算一次性实证。
  - **对账 pending 版本 tag 删除**无用例（P2-1）。
  - relations 冷热等价、PG FK/CASCADE、switch/reactivate 快照事务写入/回滚只在临时脚本或间接断言（P3-12）。
  - 若干用例自证/空断言：`out2` 未断言、固定 NOW 节流锚、未用变量（P3-11）。
- **门禁**：脚本语义 fail-closed（无 DSN 失败、skip=失败、pg 收集数>0），本轮计数自洽；建议交付 manifest 附 `scripts/test_gate.sh` 原始输出，避免只引用检查点数字。

---

## 5. R2 docs 批清单建议（给监督侧）

1. **`docs/known-gaps.md`**
   - G-21 总览行与条目状态改为 **已收口（2026-10-31 随 m2s-5 方案 A）**：0008 `sem_build_snapshots` 双方言；switch/reactivate 同事务写快照；`get_annotator`/`render_l0` 按 current build id 取快照；冷缓存/重启服务 build 产物；无快照回退 live+告警。
   - 残留登记：①PG `snapshot_json` 无 `json_valid` CHECK（写入方受控；sqlite 有；可选 `IS JSON`）；②0008 前存量 ready 行无快照 → 回退 live，且同 rev 的 skipped build 不会回填（仅新 rev/重激活会写）；③快照含 relations 是必需的（共现/L0），体积/无旧快照 GC 登记；④外部篡改快照 JSON 时 `get_annotator` 抛错不回退；⑤m2s-4 P3 清单中本段已闭/未闭逐项（B1、B2、fuzzy_only 过滤、R3 两个空转用例、`_audit_build` 重复 import 已闭；TC-BUILD-04 无确认入口、l0_extra、拉丁粘接、alias confidence、precision 分母、mixed-mode context、double_build 名实、maintenance 若干项仍未闭）。
   - 可新增/注记：无行块恒为 retag 候选、对账每日扫描（A-14 延伸）；`default_reading` 外部 schema；retag 无命中块的旧标清理（P1 修复后）。
2. **`docs/TEST-CASES.md`**
   - 版本行升 v1.9.9（或下一顺位），注明非决策变更、用例数不变。
   - §4.6：**TC-TAG-01/02/03 ✅（m2s-5）**；TC-TAG-04/05 → **m2s-6**；**TC-BUILD-05 ✅（m2s-5）**；**T-S10 ✅（m2s-5）**——注明版本切换/删文档 + tombstone 90 天第 4 挂点（若补仓库用例，指向用例名）。
   - TC-TAG-01 预期补：`semantic.tag_failed` 审计、restricted 双滤、无构建静默；A-14 的「待重标」机制落地为「warning+audit+无行=dict_rev 落后候选」。
   - TC-TAG-02 预期补：claim 尾序最低优先级、`semantic_batch_rows` 分批、批间存活；注明无行块不消候选（A-14）。
   - TC-TAG-03 预期补：悬挂/retired 物理清理 + lagging 只报告补投；pending 版本口径按边界②裁定。
   - TC-BUILD-05 注：别名分量摘要 diff；首建宁投勿漏；仅 definition 不投（构建侧）；对账最终仍可能补投（边界③口径）。
   - TC-BUILD-04 注：G-21 问题②（评测拦下重启不服务被拦词典）已随方案 A 收口；「需人工确认」无入口仍残留。
   - TC-SEV-02 / TC-SEM-03 注：B1 严格分子（ambiguous=true 不计正确）、B2 `resolved_by='default'` 第⑤级 + ceiling 0.9、`default_reading` YAML 字段。
   - **A-14** 标已闭环并写实现口径；§六 M2-S3 行写 m2s-5 段完成态、门禁 1376+1、剩余项（T-S7/8/9、TC-SEM-08/09、TC-SEV-03、TC-YAML-05、TC-TAG-04/05、TC-TASK-06 若未收）→ m2s-6；TC-PERF-05 → m2-5；错别字正样本 → m2s-6。
3. **`AGENTS.md`**：语义轨道 4/6 → 5/6（m2s-5）；门禁 1376+1；M2 段序下一段 m2s-6；G-21 收口；m2s-5 交付 PR（待开）。
4. **`.opencode/workflows/_m2-plan.md`**：row 9 改 **done/PR**（合入后补 mergeCommit）；row 10 为下一段；门禁基线 1323+1 → 1376+1；分支基线更新；G-21 收口；挂账（TC-PERF-05、边界②/③残留、P3 残留）逐项。
5. **`.env.example`**：补 `LATTICE_SEM_RETAG_RECONCILE_INTERVAL_S` 注释模板（见 P2-4），并在检查点 filesChanged 补 `.env.example`。
6. **`docs/design.md` / `docs/requirements.md`**：**不动**（冻结纪律）；`sem_build_snapshots` 表在 design §4 未列，作为 G-21 方案 A 实现载体在 known-gaps/TEST-CASES 注记即可。
7. **检查点 `task-knowledge-lattice-m2s-5.md`**：监督侧更新 `reviewVerdict=NEEDS_CHANGES`、round 记录与 R2 修复项；当前工作区监督侧文件**不要**随 R2 coder commit 入库（防重演 `9373f11` 事故）。
8. **交付 manifest**（R2 通过后）：dual SHA（testedSha/reviewedSha 与最终 HEAD 一致）+ 门禁原始输出（1376+1、pg 483=450+33、0 skipped）+ specRulings（六条裁定 + 边界口径）+ gapClosures（G-21、TC-BUILD-05、TC-TAG-01/02/03、T-S10）+ handover（A-14、P3 残留、m2s-6 项）。

---

## 6. 交付把关（本轮不执行）

- 本轮是 R1 审查，**不是交付阶段**；未执行 `gh pr review`/PR 留痕（当前 `develop_opencode` ahead 2，尚无最终 PR；按仓库纪律不自动 push/合入）。
- 交付时：最终 HEAD 的 evidence manifest 必须双 SHA 一致、含门禁原始日志；PR 审查结论用 `gh pr review` 落在 PR；合入动作不经手。
- R2 的 coder commit 只允许代码/测试 + 监督侧 docs 批；**禁止**把 `.opencode/agent/supervised-coding.md` 与 m2s-5 检查点未完成态入库。

---

## 7. 结论

**reviewVerdict: NEEDS_CHANGES**

- 阻塞项：**P1**（retag 零命中块旧标永久残留，别名删除/restricted 化后 `dict_rev` 不收敛，且影响未来实体召回/T-S9 残留）。
- 交付前应修：P2 四项（pending 版本对账清理、tombstone 第 4 挂点仓库用例、test_tag_02 tagger/别名删除回归、`.env.example` 新键）。
- P3 与需求边界项按上方登记/回 spec；不阻塞本段逻辑验收。
- 已做裁定：六条出入均**接受**（①relations、②首建投递、③>0+节流、④DDL 载体、⑤实体级 default_reading、⑥A1）；观察①接受登记、观察②要求补仓库用例、观察③ R2 docs、观察④接受。
- **CASE_BUG 裁定**：无（未收到请求）。

> 报告供监督侧存档；检查点文件未改动。

</details>
