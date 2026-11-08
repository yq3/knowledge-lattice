---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m3-3
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e45c7729dffetMpK9VQEVo53v6
testerTaskId: ses_e459b63b8ffeUA4Ij22x3p70V1
committerTaskId: ses_e458e8eb7ffevlru71H1KOOvQ2
status: approved
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 3a0a214aff9074997caec298d40c7723d8b739a8
reviewedSha: 3a0a214aff9074997caec298d40c7723d8b739a8
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged:
  - src/knowledge_lattice/api/admin.py
  - src/knowledge_lattice/api/semantic.py
  - src/knowledge_lattice/core/semantic/annotator.py
  - src/knowledge_lattice/core/semantic/build.py
  - src/knowledge_lattice/core/semantic/fuzzy.py
  - src/knowledge_lattice/core/semantic/lookup.py
  - src/knowledge_lattice/core/semantic/middleware.py
  - src/knowledge_lattice/core/semantic/recall.py
  - src/knowledge_lattice/mcp/server.py
  - src/knowledge_lattice/query_audit.py
  - src/knowledge_lattice/store/postgres/__init__.py
  - src/knowledge_lattice/store/postgres/audit_factory.py
  - src/knowledge_lattice/store/postgres/backend.py
  - src/knowledge_lattice/store/sqlite/backend.py
  - src/knowledge_lattice/web/api.js
  - src/knowledge_lattice/web/i18n.js
  - src/knowledge_lattice/web/style.css
  - src/knowledge_lattice/web/views/access.js
  - tests/test_audit_query_g22.py
  - tests/test_qa_ts7_ts8_m32.py
  - tests/test_query_audit_m33.py
  - tests/test_r2_m2s6_fixes.py
  - tests/test_sem_audit_g24b.py
  - tests/test_sem_g24_m33.py
endReason: null
createdAt: 2026-11-08T16:08:18+0800
updatedAt: 2026-11-08T18:10:04+0800
---

# task-knowledge-lattice-m3-3: 语义 hardening 批（含 G-28③⑤ 承接）

## 任务原文

**M3 第 3 段（语义 hardening 批）**——来源：_m3-plan row3（用户确认的段序）+ m3-2 检查点移交（含用户裁定 2026-11-08：P2-1 上调 m3-3 段内修复）+ m3-1 移交（G-24⑥⑦⑨/G-23 残余/code versioning）+ m2s-6 followups（G-23 残余/code versioning/R1 P3 残留）+ issue #15。

### A 组：语义查询面 hardening（本段主线）

1. **#15 / G-24⑨ 语义查询面随指纹探针 gate 关闭**：docs 检索在探针拒绝时关查询侧向量路（api/search 传 service.gate），而 search_entities / annotate 的 fuzzy vec 层不看 gate——探针拒绝后仍用跨底模向量计算语义近邻，与 NFR-8/design §5.2「查询侧向量路关闭」跨切面不一致。修法：语义查询面（search_entities / annotate fuzzy vec 层）接线 probe gate。
2. **G-24⑨ 后半：annotate fuzzy vec 有界/熔断/降级审计**：annotate fuzzy vec 走 embed_timeout_s=30s 同步嵌入、无 breaker、无降级审计（G-24③ 只覆盖 search_entities）——补 query_embed_timeout_s 有界等待+共享熔断（service.breakers["embed"]）+降级审计（沿 search_entities 既有形态）。
3. **G-24⑥ auto_entities 超长降级**：query >4000 字时 annotate ValueError 上抛 400 整次检索（与增益路失败不阻断相悖）——修法=auto 分支返回 None（超长不阻断检索）。
4. **G-24⑦ 中间件 L1 概念行缺 disambiguation**：mention 契约未携带该字段（design §6.3② 字面含）——**裁定①（2026-11-08）：补字段**（mention 行加可选 disambiguation 字段，向后兼容非决策变更）；锚点=coder 先核 design §6.3② 原文字面——字段语义有自然落位（L1 行多候选歧义信息可携带）则补，发现无自然数据来源则申报转监督侧注记（spec_confirm）。

### B 组：G-23 残余收口（模糊层最终一致性修复路径）

m2s-6 R3 登记的收窄动作合并修法（known-gaps G-23）：
1. **embed_model 入内容集合**（①）+模型迁移崩溃窗口回归用例+「再次 skipped 不重触」断言——embed_model 入集合后标记触发面即冗余可整体移除。
2. **标记清除**（②）：修复成功清 current 行 index_write_failed/vec_skipped（标记粘滞消除）。
3. **per-skip 全量重算收窄**（③）：**裁定②（2026-11-08）：内容哈希方向**——build stats 存内容集合哈希，skipped 构建先比哈希再全量（与①标记面移除收敛自洽）；具体形态 coder 择型申报。
4. **fuzzy_repaired 观测语义**（④）：审计事件落库/被修复 build 行标记清理（与②同面）。
5. **构建产物 code versioning 入 dict_rev**（⑤）：pinyin/编辑距离算法或规范化代码变更触发重建（code version 常量入 dict_rev 参与 G-23① 内容集合对账）。

### C 组：G-28③⑤ 承接（m3-2 移交，用户裁定 2026-11-08）

1. **G-28③ / P2-1 pg 单连接共享修复（必做）**：QueryAuditQueue 改收 backend_factory（pg 形态独立连接/连接池单连）或 PgBackend._conn 连接级串行化+pg 臂测试双连接形态——消除 flush 线程与请求线程共享单连接的协议错乱风险。
2. **G-28⑤ 链互斥并发测试收编（首轮必做）**：收编 m3-2 Tester 注入脚本为正式用例（ThreadLocalBackend+barrier+ship_outbox×append_query_events 双线程+walk_chain 断言；pg 随 P2-1 双连接补）+ P3-3 qa1b 隔离 stop() flush + P3-4 refused 分支断言补（MCP 停用/REST·MCP annotate·get_entity 拒绝面）。

### D 组：文案与卫生清扫 + G-28④⑦（m3-2 移交顺手批；④⑦ 扩容并入——裁定③ 2026-11-08）

1. **文案残留 4 键+注释/CSS 清扫**（m3-2 Committer P3-1）：i18n :131/:323/:387/:388（access.mem.empty/footNote 等「无 GET members」矛盾文案——GET members 已在 m3-1 落地、m3-2 已真源化）+access.js:7/api.js:9-10/338 注释+style.css:568-573。
2. **未用导入清扫**（m3-2 Committer P3-8）：新测试 uuid/RelationRecord/七 helper 等。
3. **G-28④ flush existed 按批 id 查询（本段交付项，与 C-1/P2-1 同批经济）**：existed 从「查整月 id 集合」改「按本批 id 查询」（消 O(当月行数)/次、月度 O(N²) 扫描）。
4. **G-28⑦ 溢出/丢弃观测面 /stats 暴露（默认做，可申报后移）**：dropped/pending 计数进 /stats+断言，顺带销 G-28⑦ 开放点。
5. **顺路**：audit 取数 try/except 包裹（api/semantic.py:540-553/mcp/server.py:620-630——500 风险）。

### 验收标准

1. **门禁零回归**：基线 **1842+1**（m3-2 交付后）双后端双模式 0 skipped、pg 臂收集数 >0；新增用例计入对账。
2. **TDD**：A/B/C 组新行为均有红→绿证据；C-1 链互斥并发用例须能捕获互斥回归（注入摘除互斥后用例变红——沿 m3-2 注入实证口径）。
3. **分层纪律**：core 无方言 SQL（G-28③ 若动 store 连接形态属 store 层合法）；auto_entities 识别钉 api/mcp 层。
4. **coder 禁改** docs/requirements.md、docs/design.md 冻结正文与 prototype/（验收口径变化走 supervised-coding）；活文档（TEST-CASES/known-gaps/RUNBOOK）由监督侧 docs 批处理。
5. 分支纪律：develop_opencode 本地 commit `[task-knowledge-lattice-m3-3] R<n>`，commit 前同步 origin/develop（当前=2fcf280）。
6. 交付形态沿先例：双通过→监督侧 docs 批（known-gaps G-23/G-24⑥⑦⑨ 划销+G-28③⑤ 划销、TEST-CASES 登记、_m3-plan row3 done、issue #15 关闭材料）→coder chore 归档批（含 m3-2 终态后工作区改动）→push+PR base=develop→committer PR review→manifest→用户合入。

## 需求确认
- [x] 用户已确认（2026-11-08 16:12「同意，本会话内subagent的调用无须询问我」——status=implementing；**会话级授权：本会话内 Task 调用免逐一预告确认**）
- 历史遗留事项清单：（supervised-coding 扫描历史检查点汇总，默认并入新任务，见 README §4.6）
  - **并入本任务**：m3-2 移交 m3-3 全部（①P2-1 pg 单连接共享修复〔用户裁定段内修复〕②链互斥并发测试收编〔首轮必做〕+qa1b 隔离+refused 分支断言补 ③文案 4 键+注释/CSS 清扫 ④未用导入清扫 ⑤顺路 audit 取数包裹——m3-2 检查点遗留节〔未勾选〕）；m3-1 移交 m3-3（G-24⑥⑦⑨/G-23 残余/code versioning）；m2s-6 followups 残项（G-23 残余①~⑤/code versioning——m2s-6 检查点遗留节〔未勾选〕，其中显式断言三补已随 m3-2 清偿、R1 P3 残留中 G-24①②③④⑤⑧ 已划销，余⑥⑦即本段 A-3/A-4）；issue #15（G-24⑨——本段 A-1/A-2，交付后随 PR 关闭）
  - **不并入（去向已登记）**：G-28①②⑥⑧（开放点，触发时处置——①需扩覆盖面属口径决定、②大组织部署触发、⑥G-26 延伸部署侧、⑧理论硬化；**④⑦ 已扩容并入本段 D 组**——裁定③）；#16 conftest teardown+warnings 治理→m3-4；m3-4/m3-5 既有范围不变；部署期三件+TC-UI 走查（用户侧）不阻塞
  - **开工前口径裁定（2026-11-08 用户确认）**：①G-24⑦=补字段（锚点：design §6.3② 字面有自然落位则补、无自然数据来源申报转注记）；②G-23③=内容哈希方向（具体形态 coder 择型申报）；③G-28④⑦=并入本段（④交付项与 P2-1 同批、⑦默认做可申报后移）
（开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 遗留事项（跨任务移交）
- [x] **本轮清偿**（2026-11-08 双通过，SHA 3a0a214）：m3-2 移交①P2-1 pg 单连接共享修复〔机制+测试：backend_factory+audit_factory 惰性单连接+pg 臂 pid 断言〕②链互斥并发测试收编+qa1b 隔离+refused 断言补③文案 4 键+注释/CSS④未用导入⑤audit 取数包裹+G-28④ existed 按批+G-28⑦ /stats；m3-1 移交 G-24⑥⑦⑨；m2s-6 移交 G-23 残余①~⑤+code versioning；issue #15（G-24⑨）交付材料齐。
- [ ] **登记部署期（不阻塞——Committer 边界①）**：G-28③ 生产接线残余——app lifespan 工厂注入+audit_backend_factory close() 关停+pg 工厂 broken 连接重连路径（本轮仅机制+测试，生产恒 sqlite 无暴露；RUNBOOK PG 接线段随 docs 批记录）。
- [ ] **移交 m3-4（顺手批）**：Committer P3-2（test_query_audit_m33 import time）+P3-6（test_r3_p2_2 函数名更名）；建议项 P3-10（A-1 gate 四接线点端点级 e2e 用例——与 TC-EVAL 批同段顺手）。
- [ ] **移交后续 web/语义批（顺手级）**：P3-1（_default_embed_batch 死代码删除）+P3-3（style.css:550 段头注释）+P3-4（sqlite 臂 ThreadLocal 循环外复用）+P3-7（畸形 stats_json 跳过持久化）+P3-8（audit 载荷共用）+P3-9（append_query_events 批上限声明）。
- [ ] **PG 接线部署期复验**：P3-5（工厂 close/重连）+P3-11（pg 臂链互斥注入实测）+Tester P3-2（DeadlockDetected 复现注记）。
- [ ] **文档面纪律（随监督侧 docs 批落笔）**：FUZZY_CODE_REV bump 纪律+升级一次性全量重建提示（known-gaps G-23 划销注记/RUNBOOK）。
- [ ] **用户侧（不阻塞）**：TC-UI-01~05 人工走查维持（本段无 UI 形态变化，无需新增走查步骤）。
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1: coder 完成（2026-11-08 16:59 报告，**全新会话**，coderTaskId=ses_e45c7729dffetMpK9VQEVo53v6，commit `3a0a214` 于 develop_opencode，24 files +1555/−188，父提交=2fcf280（origin/develop 同步确认无前进），未 push；监督侧机械核验 ✓ HEAD/父提交/文件数/docs+prototype+.opencode diff=0）——**A** ✅ #15/G-24⑨ gate 接线（search_entities+annotate fuzzy vec 探针拒绝关向量路+probe_reject 降级审计，REST/MCP 四接线点）+annotate fuzzy vec 有界/共享熔断/降级审计（embed_query_bounded 公共化 scope=annotate——沿 m2-5 形态）+G-24⑥ auto 超长 auto 分支返 None+G-24⑦ mention 补可选 disambiguation（**裁定①核读结论=有自然落位**：design §6.3② 字面「概念/系统：name+brief+disambiguation」+YAML curated_json.disambiguation {not,hint} 数据源——无数据不出现键向后兼容）+中间件概念行消费；**B** ✅ G-23 残余（①embed_model 入对账集合+模型迁移崩溃窗口回归+**标记触发面整体移除**②修复清 current 行标记③内容集合哈希快速通过〔裁定②——content_hash 带 embed_model 维、健康索引零 build_fuzzy_terms〕④repaired 注记入被修复行⑤FUZZY_CODE_REV 入 dict_rev）；**C** ✅ G-28③/P2-1 QueryAuditQueue backend_factory+pg audit_factory 惰性单连接（独立于请求连接——pg 臂 pid 断言）+G-28⑤ 并发用例收编（barrier 双线程 120 轮+walk_chain——注入摘互斥红实证）+qa1b 隔离 stop flush+refused 断言补；**D** ✅ 文案 4 键（i18n 658=658 零键增删）+注释/banner 死 CSS+未用导入+G-28④ existed 按批 id（双方言）+G-28⑦ dropped/pending 进 /stats+audit 取数包裹不 500。择型申报 9 条（公共嵌入函数/惰性单连接工厂〔每轮开连触发 setup DDL 死锁实测收敛〕/标记保留写入凡修复即清/哈希含 embed_model 维·向量覆盖不进哈希/旧用例 test_r3_p2_2 按新裁定更新/existed 等价重构不造空转断言/stats 键位形态 query_audit{dropped,pending}/评测注入面不走熔断但 gate 照拦/i18n 键数口径 658——m3-2 报告 660 系工具口径差异）。自测：TDD 红→绿（A+B 12 failed→绿、C/D 4 failed→绿）；**注入 2 组**（①摘链互斥→sqlite 并发用例红〔database is locked〕②摘 gate→双用例红〔embedder.calls≠0/probe_reject 缺失〕）均恢复 src 零残留；**GATE PASS 1880+1**（基线 1842+38：sem_g24_m33 22+query_audit_m33 16；pg 臂 696+18=714 全实跑）。

- R1: tester **PASS**（2026-11-08 17:14，**全新会话**，testerTaskId=ses_e459b63b8ffeUA4Ij22x3p70V1，testedSha=3a0a214aff9074997caec298d40c7723d8b739a8 复核一致）——门禁独立复跑 **GATE PASS 1880+1 双后端双模式 0 skipped**（pg 臂 714=680 参数化+34 专用；对账独立核算闭合：sem_g24_m33 22=10 双臂×2+2 单臂、query_audit_m33 16=8 双臂×2、pg 臂 696+18=714）。逐项勾验 A/B/C/D 全 ✅（A gate 四接线点实核与 docs 检索同源+embed_query_bounded 与 m2-5 逐字同构〔git show 2fcf280 对照〕+A-4 design.md:1221/526/921 核读属实自然落位成立；B 完备性论证核验成立+哈希「可补齐态非内容态」论证正确+快速分支保留覆盖检查语义闭环；C pg 臂 pid 断言真实核验两条连接确实不同+择型⑤行为更新非放宽〔docstring 口径来源+test_b2 等价覆盖+覆盖面更宽〕；D 文案 4 键全清+键数独立双口径复核 **660=660** added=removed=∅+existed 双方言对称幂等不变+/stats 形态防御+audit 包裹双分支真实触达〔calls>=2〕）。**择型 9 条全 ACCEPT**（⑨附数字勘误——准确数字 660，coder 申报 658 系其本轮工具口径偏差、归因反向；②附 P3-2 注记）。**注入 3/3 有效**（①摘 gate→A-1 双臂 4 failed；②摘链互斥→C-2 sqlite 红〔database is locked〕；③摘 embed_model 对账维→B-1 双臂 2 failed——G-23① 回归捕获）均恢复 src 零残留。**回归零弱化**（0 函数删除〔基线 32→52，removed=NONE，added=20〕、0 新增 skip、qa1b=强化、test_r3_p2_2=按裁定行为更新、g24b/ts7ts8 仅未用导入清理）。分层 ✓（core 六文件方言 SQL 零命中+audit_factory 落 store/postgres+core 两包零 import 交叉+auto_entities 钉 api/mcp）；docs/prototype/.opencode 零 diff ✓、.env 未读 ✓。**P1 无；P2 无；P3×3**（①择型⑨数字申报失真 658≠660 归因反向——实质主张零键增删成立；②择型② DeadlockDetected 收敛过程无留档——论证链成立，建议部署期 PG 接线段补 RUNBOOK §1.z 复现注记；③audit_backend_factory 生产 close() 接线点随 PG 接线部署期落地——测试臂进程退出兜底无碍）。临时产物清理 ✓。报告全文见「最新验证意见原文」（R1 Tester）。

- R1: committer **APPROVED**（2026-11-08 17:25，**全新会话**，committerTaskId=ses_e458e8eb7ffevlru71H1KOOvQ2，reviewedSha=3a0a214aff9074997caec298d40c7723d8b739a8=testedSha=HEAD 三一致；diff 2fcf280..3a0a214 24 files 逐文件核对；门禁采信 Tester 独立复跑+静态计数独立复算一致〔38=22+16、pg 696+18=714〕；docs/prototype/.opencode 零 diff ✓；分层 ✓）——**P1 无；P2 无；P3×11**（①_default_embed_batch 死代码②test_query_audit_m33 import time 未用③style.css:550 段头注释残留④sqlite 臂每轮新建 ThreadLocal 无谓抖动⑤pg 工厂无重连路径〔broken 连接丢弃循环——部署期登记〕⑥test_r3_p2_2 函数名与断言语义相反⑦_updated_fuzzy_stats 畸形 stats_json 整行覆写空壳风险⑧_audit_annotate_vec_degraded 载荷重复维护⑨append_query_events 无批上限声明⑩A-1 四接线点无端点级用例〔建议 m3-4 e2e 批〕⑪C-2 pg 臂注入未实测〔逻辑推演，PG 接线部署期复验〕）。**需求边界×4（供上报不交 coder）**：①G-28③ 生产接线面——本轮交付=机制+测试，app.py:332 仍无工厂注入（生产恒 sqlite 无暴露），**docs 批 G-28③ 不整条划销**改写「残余=生产 lifespan 工厂注入+close()——PG 接线部署期」；②mention 契约可选字段走 design「非决策变更」声明；③FUZZY_CODE_REV bump 纪律注记落 TEST-CASES/RUNBOOK；④fuzzy_code_rev 入 dict_rev 升级后一次性全量重建提示（沿 yaml_rev 先例）。**Tester 意见裁定**：P3-1 确认（660 为准）/P3-2 确认（RUNBOOK 复现注记）/P3-3 确认并扩展为边界①。择型 9 条复核全 ACCEPT 维持。**docs 批建议清单**（known-gaps G-23 划销+G-24⑥⑦⑨ 划销+G-28④⑤⑦ 划销/③改写/①②⑥⑧维持、TEST-CASES m3-3 组 38 条登记+两条纪律注记、design 非决策注记〔§6.3② mention/§5.8 模糊对账〕、RUNBOOK PG 接线三件〔工厂接线+死锁复现+bump 纪律〕、#15 关闭材料、AGENTS/_m3-plan row3 done、manifest 要点已给〔双 SHA+deliveryHead+caveats〕）。报告全文见「最新验证意见原文」（R1 Committer）。

- **双通过达成（2026-11-08 17:25，round=1 收敛）**：testVerdict=PASS + reviewVerdict=APPROVED，testedSha=reviewedSha=3a0a214aff9074997caec298d40c7723d8b739a8=当前 HEAD——status=approved，待用户确认交付（交付序列：监督侧 docs 批→coder chore 归档批→push+PR base=develop→committer PR review→manifest→用户合入；#15 随 PR closing 关闭）。
- **交付裁定（2026-11-08 17:30，用户「同意」——status=approved→归档中）**：范围口径确认——P2-1 代码面已修完（机制+测试），G-28③ docs 批按「机制+测试已交付，残余=生产 lifespan 接线（PG 接线部署期）」改写不整条划销；fuzzy_code_rev 升级一次性重建提示落 RUNBOOK。交付序列启动。
- **交付执行①：监督侧 docs 批完成（2026-11-08 18:10）**——design **v0.9.12**（版本行非决策声明+§5.8 模糊对账收口注记〔四元组+哈希锚+标记面移除+FUZZY_CODE_REV〕+§6.3② mention disambiguation 实装注记+日期行）；known-gaps **G-23 划销**（概览+条目收口块）、**G-24 v5 注记⑥⑦⑨ 划销（全项清）**、**G-28 v2 注记④⑤⑦ 划销+③机制与测试已交付（残余=生产 lifespan 接线）**；TEST-CASES **v1.9.17**（TC-OPS-12 新组〔38 收集+注入 3 组+两条纪律注记〕+§六 M3 行 m3-3 段）；RUNBOOK **§1.z 扩容**（/stats 暴露+PG 接线四件〔工厂接线点+close()/死锁复现注记/broken 重连评估/DDL 缓存〕+模糊 code versioning 运维纪律+bump 一次性重建）；AGENTS §1 M3 进度更新（m3-3 交付+剩余 2 段）；_m3-plan row3 done+§二 backlog 全勾+§三下段指引 m3-4（基线 1880+1+m3-3 移交顺手批）。工作区 8 文件（7 改+m3-3 检查点新入库）待 coder chore 归档批。issue #15 随 PR closing 关闭。

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

<details>
<summary>R1 Tester 报告（2026-11-08 17:14，testVerdict=PASS）</summary>

# task-knowledge-lattice-m3-3 R1 Tester 验证报告

**testVerdict: PASS** ｜ **testedSha: `3a0a214aff9074997caec298d40c7723d8b739a8`**（开工复核 develop_opencode HEAD 一致，父提交 `2fcf280`=origin/develop 同步确认；注入验证后 HEAD 未动）

## 一、门禁独立复跑（tester 自跑，非采信 coder 自测）

```
pg 臂用例收集数：714（[pg] 参数化 680 + PG 专用 34，> 0 ✓）
[pytest]   OK：1880 passed, 1 deselected, 0 skipped（241.69s）
[pytest-O] OK：1880 passed, 1 deselected, 0 skipped（243.10s）
GATE PASS: sqlite+pg 双后端、双模式全绿，0 skipped（pg 臂 714 全实跑）
```

**对账独立核算闭合**：
- 基线 1842 + 新增 38 = 1880 ✓
- `test_sem_g24_m33.py` collect 独立数 = 22 条（12 函数中 10 双臂×2 + 2 单臂〔middleware 消费/b5 bump——纯内存无 backend fixture〕）✓ 与 coder 申报一致
- `test_query_audit_m33.py` collect 独立数 = 16 条（8 函数全双臂，qa_env 经 backend fixture 参数化）✓
- pg 臂新增 18（sem 10 + audit 8），696 + 18 = **714** ✓ 与门禁实报闭合
- deselected 1 = manual 口径维持 ✓；0 skipped ✓

## 二、逐项勾验

### A 组（语义查询面 hardening）✅

- **A-1 #15/G-24⑨ gate 接线**：`lookup.search_entities`（gate_rejected → probe_reject 降级审计 + 不进 embed_query_bounded——零嵌入调用）+ `annotator.annotate_text`（gate_rejected → probe_reject 审计 + vec_lookup 不构造）。四接线点实核：REST `api/semantic.py:356`（search_entities）/`:492`（annotate）、MCP `server.py:689`（search_entities）/`:558`（annotate）；与 docs 检索 `server.py:381`（run_search gate=service.gate）同源形态对齐 ✓。test_a1×2 双臂断言 `embedder.calls==0` + `probe_reject` + scope ✓
- **A-2 有界/熔断/降级审计**：embed_query_bounded（lookup.py:70-106）scope=annotate；test_a2×2（bounded: `breaker._streak>=1` + embed_unreachable + org/user 断言；breaker_open: calls==0）✓。**择型①逐字同构核验**（git show 2fcf280 对照）：m2-5 基线 `_embed_query_bounded` 与公共化版本 breaker 开路/成功/异常三路、审计事件名/reason/载荷结构/写失败告警**逐字同构**，差异仅 scope 参数化+去下划线+日志带 scope ✓
- **A-3 G-24⑥**：recall.py:61-69 auto 分支 ValueError→None；**对照断言在**（test_a3 内 `pytest.raises(ValueError)` 锁显式 entities >20 seeds 契约上抛）✓
- **A-4 G-24⑦（裁定①）**：**coder 核读结论属实**——design.md:1221 字面「概念/系统：`name + brief + disambiguation`」+ design.md:526/921 YAML `disambiguation` 人工属性（{not, hint}）数据源在，自然落位成立。`_mention/_disambiguation` 补可选键、无数据不出现键（向后兼容）；`middleware._concept_line` 真消费（hint →「注意区分：…」，无字段行内容与旧形态一致）。test_a4×2 正反对照齐 ✓

### B 组（G-23 残余）✅

- **B①**：expect_set/have_set 四元组含 embed_model（build.py:731-736）；test_b1 模型迁移崩溃窗口（旧标签行内容恰等 → 必须触发整替）双臂 ✓；「再次 skipped 不重触」双轮在 test_b3（两轮 skipped 零修复）✓；**择型③完备性论证核验成立**——凡真需修复的场景（内容漂移/旧标签/向量不足且有 embedder）均被内容集合或覆盖对账捕获，「健康索引+仅标记」是唯一不再触发的形态且该形态下整替本属幂等无害冗余；标记保留写入（观测面）+凡修复即清除
- **B②**：`_updated_fuzzy_stats` 清 index_write_failed/vec_skipped（build.py:648-649），test_b2 锁定 ✓
- **B③（裁定②）**：快速通过分支（:716-724）哈希+标签+覆盖三查一致 → return None **零 build_fuzzy_terms**；test_b3 monkeypatch 计数==0 断言（build.py 侧函数内 import，monkeypatch 路径生效——核验无误）✓；**择型④核验**：向量覆盖不进哈希正确——覆盖是「可补齐态」非「内容态」，进哈希则补齐动作自毁锚点；且快速分支保留覆盖检查（embedder 在场时 vec_embedded≥expect_saved 才通过），语义闭环
- **B④**：repaired={reasons, terms, vec_embedded} 入被修复行；非修复路径 pop ✓
- **B⑤**：FUZZY_CODE_REV=1 入 `_rev_payload`+`dict_rev_components`；test_b5×2（bump→dict_rev 变化；分量暴露）✓

### C 组（G-28③⑤）✅

- **C-1/P2-1**：QueryAuditQueue 收 backend_factory（ContextManager 契约，flush 全程 `_flush_lock`）；`store/postgres/audit_factory.py` 惰性单连接（首建锁双保险 + close swap 后关 + no-op 安全）。**pg 臂 pid 断言真实核验**（test_c1_pg：工厂连接 `pg_backend_pid()` ≠ 请求连接——两条连接确实不同）✓。flush_lock 下复用安全成立：单消费线程 + stop() 先 join 后 flush、显式 flush 与后台 flush 互斥等待——同一连接无并发使用窗
- **C-2/G-28⑤**：并发用例收编（sqlite 双 ThreadLocal / pg 搬运共享+查询道工厂双连接 + barrier + 120 轮×3 + errors 汇聚 + read_monthly_events walk_chain fail-closed + 行数对账断言）✓；qa1b 隔离改造（不 start 后台线程 + 新增前置「入队不落库」断言——**强化非弱化**：落库只可能出自 stop()）✓；refused 三补实核（REST annotate/get_entity 停用 + MCP search/annotate/get_entity 三工具停用 + REST/MCP 无成员面，reason 断言齐）✓
- **择型⑤重点核验：test_r3_p2_2_persisted_marker_triggers_repair 是按新裁定的行为更新、非放宽**——断言翻转（get→not get fuzzy_repaired）对应任务原文 B①「标记触发面整体移除」的直接要求；docstring 详注口径来源（m3-3 G-23① 裁定+旧口径作废依据+清面语义去向）；旧行为的等价覆盖在新用例 test_b2 ①分支锁定（健康+仅标记→不触发），且新覆盖面更宽（+清标记+注记）。m2s-6 原担忧「崩溃场景落库标记是唯一线索」已被 embed_model 入集合+内容/覆盖对账完备替代（B① 论证）

### D 组 ✅

- **文案 4 键**：i18n 8 行 diff = 4 键×2 语言（docs.upload.noDs/access.dims.new.foot/access.mem.empty/access.mem.footNote），「无 GET members」矛盾文案全清；api.js/access.js 注释更新、style.css banner 死 CSS 删除（web/ 内零 banner 引用核验）✓
- **键数口径独立复核（择型⑨）**：regex 双侧对比 + node 权威解析（leaf keys）双口径 = **660=660，added=removed=∅ 双语言**——零键增删属实；但 **660 才是准确数字（与 m3-2 报告一致），coder 申报的 658 系 coder 本轮工具口径偏差，归因方向反了**（实质主张成立、数字勘误→P3-1）
- **未用导入**：七 helper/uuid/RelationRecord 删除后 grep 零引用 ✓
- **G-28④**：双方言对称（sqlite IN 占位符 / pg `= ANY(...)`），幂等语义不变（批内已存跳过不推进 prev），batch 200 ≪ sqlite 变量上限；**择型⑥ ACCEPT**——等价重构，行为面由 qa9（链交错）+c2（并发对账，双方言 120 轮全走新 SQL）承载；existed 命中分支的直接断言缺口系 m3-2 既有状态、非本轮弱化
- **G-28⑦**：/stats query_audit{dropped,pending}，qa 缺位→null、取数异常→null 不 500；test_d4 溢出造数（dropped==2/pending 对账）✓ **择型⑦ ACCEPT**（形态合理：None 语义清晰+观测面自防御）
- **audit 取数包裹**：REST get_entity 404 reason 回查 try/except 保守 not_found（api/semantic.py 实见）+ MCP annotate restricted_ids 失败跳过（server.py 实见）+ test_d5 双分支（404 面 boom 不升级 500——`calls>=2` 证明 boom 分支真实触达；200 面 boom 事件跳过；_PatchedBackendProxy 每属性动态解析不跨线程固定连接——ThreadLocal 语义正确）✓

## 三、择型 9 条裁定

| # | 择型 | 裁定 | 理由 |
|---|---|---|---|
| ① | embed_query_bounded 公共化共用 | **ACCEPT** | 与 m2-5 逐字同构核验通过（仅 scope 参数化），审计口径不变 |
| ② | 惰性单连接工厂（每轮开连 DDL 死锁实测收敛） | **ACCEPT**（附 P3-2） | 论证成立：connect 工厂带审计分区滚动 setup DDL，每轮开连与并发写事务在 pg catalog 锁交叉是已知死锁形态；m3-2 检查点 P3-5「ensure 分区每轮 DDL」佐证；惰性形态在 _flush_lock 串行下复用安全 + pid 断言实证。**实测 DeadlockDetected 过程无日志/复现留档**→P3-2 注记 |
| ③ | 标记保留写入+凡修复即清（触发面整体移除） | **ACCEPT** | 完备性论证通过（见 B①）——凡真需修复场景均被内容/覆盖对账捕获 |
| ④ | 哈希含 embed_model 维、向量覆盖不进哈希 | **ACCEPT** | 「可补齐态非内容态」论证正确，快速分支保留覆盖检查语义闭环 |
| ⑤ | 旧用例 test_r3_p2_2 按新裁定更新 | **ACCEPT** | 行为更新非放宽：docstring 口径来源+test_b2 等价覆盖（见 C 组择型⑤核验） |
| ⑥ | existed 等价重构不造空转断言 | **ACCEPT** | 语义等价+行为面 qa9/c2 承载；existed 命中分支断言缺口系 m3-2 既有（备注不阻塞） |
| ⑦ | /stats 键位 query_audit{dropped,pending}、未装配→null | **ACCEPT** | 形态合理（防御旧壳+不 500+None 语义清晰） |
| ⑧ | embed_batch 评测注入面不走熔断但 gate 照拦 | **ACCEPT** | annotator.py:800 `if fuzzy and not gate_rejected` 在 embed_batch 分支之前——正确性约束（探针拒绝）拦住一切嵌入通道，确定性注入面豁免有界/breaker 合理 |
| ⑨ | i18n 键数 658、m3-2 报告 660 系工具口径差异 | **ACCEPT（实质）/数字勘误（P3-1）** | 零增删为真（双口径复核 added=removed=∅）；但准确数字是 660（m3-2 报告无误），coder 本轮 658 才有口径偏差——归因方向说反了 |

## 四、注入验证（3 组，红→恢复→绿，git diff src/ 零残留）

| # | 注入 | 结果 |
|---|---|---|
| ① | 摘 gate 接线（lookup.py+annotator.py `gate_rejected` 恒 False） | **A-1 双臂 4 failed**（calls=3≠0 + probe_reject 缺失）→ 恢复 → 4 passed ✓ |
| ② | 摘链互斥（sqlite/backend.py 两处 BEGIN IMMEDIATE→BEGIN，:2144/:2224） | **C-2 sqlite 臂 failed**（`OperationalError('database is locked')`）→ 恢复 → 双臂 2 passed ✓ |
| ③ | 摘 embed_model 对账维（build.py expect_set/have_set 退三元组） | **B-1 双臂 2 failed**（旧标签行不再触发修复——G-23① 回归捕获）→ 恢复 → 2 passed ✓ |

恢复方式注记：git checkout 被权限拦（写 git deny），经 python 反向字符串替换恢复，逐次 `git diff src/` = 0 行核验。TDD 红绿证据与 coder 自测申报相符。

## 五、回归零弱化核查

- **0 测试函数删除**：changed-files 内测试函数集合比对（基线 32 → HEAD 52，removed=NONE，added=20）✓
- **0 新增 skip**：门禁双模式 summary 0 skipped ✓；deselected 1=manual 维持 ✓
- **qa1b 更新=强化**（新增前置断言）；**test_r3_p2_2=按裁定行为更新**（等价覆盖在 test_b2）；**test_sem_audit_g24b/test_qa_ts7_ts8_m32 仅未用导入清理**（零断言变更面）✓

## 六、分层纪律与禁改面

- core/semantic 六文件 grep 方言 SQL 关键字（SELECT/INSERT/UPDATE/DELETE/execute）零命中；`audit_factory` 落 store/postgres 合法；core/docs↔core/semantic 零 import 交叉（仅注释提及）；auto_entities 识别钉 api/mcp（recall.resolve_query_entities 仅 api/search+mcp search 消费）✓
- commit 内 docs/ prototype/ .opencode/ **零 diff** ✓；web 4 文件白名单合法 ✓；工作区 tracked 改动仅监督侧检查点文件（开工前既有）✓；**.env 未读** ✓

## 七、问题清单

**P1：无。P2：无。**

**P3×3**（均不阻塞，随单转交）：
1. **择型⑨数字申报失真**：658≠660（独立复核），「m3-2 报告 660 系工具口径差异」归因反向——m3-2 的 660 是准数，coder 本轮 658 才有偏差。实质主张（零键增删）成立，无代码影响；后续申报数字以本轮双口径（regex 对比 + node 解析）为参照。
2. **择型②实测证据未归档**：DeadlockDetected 收敛过程无日志/复现脚本留痕。论证链技术上成立（connect 工厂审计分区滚动 setup DDL + pg catalog 锁死锁已知形态 + m3-2 P3-5 佐证），裁定 ACCEPT；建议部署期 PG 接线段补一条复现注记归档（RUNBOOK §1.z checklist 面）。
3. **audit_backend_factory 生产 close() 接线点尚未存在**：app lifespan 的 PG 审计工厂关停调用点随 PG 接线落地（部署期既有挂账、非本轮缺口）；测试臂 factory 未显式 close 由进程退出兜底，无碍。生产接线时在 lifespan 关停处调 `factory.close()`。

## 八、临时产物清理

✓ 已清：gate 日志、基线测试快照目录、i18n 基线文件（均在系统临时目录）；src/ 零残留；被测工作区仅监督侧检查点文件（非 tester 产物）。

---

**结论**：门禁 1880+1 双后端双模式 0 skipped 独立复跑通过、A/B/C/D 四组逐项勾验全 ✅、择型 9 条全 ACCEPT（⑨附数字勘误）、注入 3/3 有效零残留、回归零弱化、分层与禁改面合规、P1/P2 无。

**testVerdict = PASS ｜ testedSha = 3a0a214aff9074997caec298d40c7723d8b739a8**

</details>

<details>
<summary>R1 Committer 报告（2026-11-08 17:25，reviewVerdict=APPROVED）</summary>

**审查对象核验完成。** 以下是 task-knowledge-lattice-m3-3 R1 的 Committer 语义审查报告（只读，未修改任何文件）。

# task-knowledge-lattice-m3-3 R1 Committer 审查报告

**reviewVerdict: APPROVED** ｜ **reviewedSha: `3a0a214aff9074997caec298d40c7723d8b739a8`**

## 〇、基线与三一致核验（机械面，独立复核）

| 项 | 结果 |
|---|---|
| HEAD | `3a0a214aff9074997caec298d40c7723d8b739a8` ✓ |
| testedSha（检查点） | 同上 ✓ |
| 父提交 / origin/develop | `2fcf280e950eacd83b978e31fb87565385214a01` = `origin/develop` ✓ |
| diff 规模 | 24 files +1555/−188；与检查点 filesChanged 完全一致 ✓ |
| docs/ prototype/ .opencode/ | commit 内 **零 diff** ✓（`git diff --stat 2fcf280..3a0a214 -- docs prototype .opencode` 空） |
| 工作区 | 仅监督侧检查点文件（`task-m3-2.md` M / `task-m3-3.md` 新），无 src 残留 ✓ |
| 分支/提交 | `develop_opencode`，`[task-knowledge-lattice-m3-3] R1`，未 push（ahead 2）✓ |
| 上一轮意见处置 | 本轮为 R1 首轮 committer，无上一轮意见；tester P3×3 见第六节裁定 |
| 测试删/跳/弱化 | 0 新增 skip（全仓 grep 仅 conftest 既有 DSN skip）；0 测试函数删除（diff 仅 4 文件：未用导入清理 + 1 处按裁定翻转）；门禁计数申报闭合（见第四节）✓ |
| 禁改面 | `.env` 未读；gate 脚本未改；依赖面零变更 ✓ |

> 方法限制声明：committer 角色 bash 仅放行只读 git/gh，无法自行执行 pytest/门禁。本报告对门禁的采信依据 = 检查点 R1 Tester 独立复跑记录（双模式 `1880 passed, 1 deselected, 0 skipped`、pg 臂 714 全实跑），并对可静态核对的计数做独立复算（见第四节）；语义面逐 hunk 独立复核（非仅采信）。

## 一、逐组语义审查（独立复核结论）

### A 组 ✅

- **A-1 gate 接线四接线点实核**：REST `api/semantic.py:356`（annotate）/:492（search_entities）、MCP `server.py:558`（annotate）/:689（search_entities）均传 `gate=getattr(service,"gate",None)`；`lookup.search_entities` 对 `gate.rejected` 先行分流——`embed_query_bounded` 零调用 + `search.degraded`（reason=`probe_reject`，scope=`search_entities`）；`annotator.annotate_text` 同款（scope=`annotate`，vec_lookup 不构造）。与 docs 检索 `retrieve.py:285` 同源语义。缺省 `gate=None` 向后兼容（core 直调/旧测试零行为变化）。
- **`embed_query_bounded` 公共化回归风险**：与 2fcf280 基线逐行对照（git show 核对）——熔断开路/成功/异常三路、审计事件名/载荷键/写失败告警**逐字同构**，差异仅 ①`scope` 参数化 ②去下划线 ③日志文案；全仓 `_embed_query_bounded` 零残留引用。无回归风险。
- **A-2 有界/熔断/审计**：annotate fuzzy vec 改经 `embed_query_bounded`（`settings.query_embed_timeout_s` 默认 0.5s，而非旧 30s 同步面）+ `breakers["embed"]` 三路 + scope=annotate 审计；`embed_batch` 注入面（评测确定性）豁免有界/熔断但 **gate 判定在 `embed_batch` 分支之前**（annotator.py:795-800）——择型⑧正确性成立。逐片段调用与熔断计数交互（3 次失败即开路）使最坏延迟有界，无放大面。
- **A-3**：`recall.py:61-69` auto 分支 ValueError→None（日志注明超长）；auto 路径传入参数仅 text 长度可能产生 ValueError（核读 annotator.py:276-284，query 非空已前置），窄捕获安全；显式 entities 分支的 `>20 seeds` ValueError 仍在 `recall.py:50` 上抛 400——契约保留（test_a3 正反对照）。
- **A-4（裁定①）**：coder 核读结论属实——design.md:1221 字面「概念/系统：name + brief + disambiguation」，YAML `curated_json.disambiguation`（{not,hint}——yaml_corpus.py:142/192）为自然数据来源；`_disambiguation` 畸形行防御，无数据不出现键（向后兼容）；`middleware._concept_line` 消费 hint（≤3 条，「注意区分：…」），无字段行与旧形态逐字一致。**安全面复核**：`not` 键引用他实体 key 不构成新增泄露类——同数据已随 get_entity `include=curated`（默认 include）对 semantic:read 全量可见（m2s-5 既有面），mention 携带只是同源字段的第二出口。
- 既有 m2s-6 面回归：`embed_batch` 注入路径行为等价（`_vec_hits` 提取逻辑与旧内联逐句同构）；`_default_embed_batch` 成为死代码（P3-2）。

### B 组 ✅（完备性论证独立复核 = 成立）

- **B③ fast path 正确性**：哈希输入 `{(entity_id, kind, text_norm, embed_model)}` 排序序列 sha——写路径（term_rows）与对账路径（`sem_fuzzy_terms_all` 行）字段口径一致（`sem_fuzzy_replace` 落库 embed_model=label，fuzzy.py:174）；`content_model` 同面校验。快速通过**保留向量覆盖检查**（`vec_embedded >= vec_expected`），覆盖是「可补齐态」故不入哈希——若入哈希则补齐动作本身会自毁锚点，coder 论证正确。
- **完备性三路捕获复核**（对抗推演）：内容漂移（含词典收缩/等行数改名）→ 集合不等；旧标签行（模型迁移崩溃窗）→ 集合 embed_model 维不等 **且** content_model 不等；向量不足（vec_skipped/部分失败）→ 覆盖对账（embedder 在场）。**真需修复场景无遗漏**：写失败=replace 事务性回滚→旧内容必与期望不等或恰好相等（相等即无需修复）；replace 成功但 stats 未落→下次对账 reasons 空分支回写锚点，收敛闭环。「健康索引+仅标记」是唯一不再触发形态，幂等整替本属无害冗余——**标记触发面整体移除有任务原文 B① 明示授权**（「标记触发面即冗余可整体移除」），非私自放宽。
- **哈希锚自毁风险**：锚点只在 ①写库成功（hash 取自实际写入 rows）或 ②对账 reasons 空（have_set==expect_set）时回写，不存在「以错误期望写锚」窗；崩溃窗口（replace 与 persist 之间）由下轮全量对账收敛。无自毁路径。
- **B②④**：`_updated_fuzzy_stats` 修面即清 `index_write_failed`/`vec_skipped` + `repaired` 注记入被修复行 + 非修复路径 pop 旧注记；skipped 返回/审计携带 `fuzzy_repaired`（既有）。
- **B⑤ 版本纪律**：`FUZZY_CODE_REV=1` 入 `_rev_payload` + `dict_rev_components` 暴露分量；常量 docstring 明列 bump 触发面（pinyin/编辑距离/term 构造/规范化行为变更），函数内 import 使 monkeypatch/测试可锁（test_b5）。**代价如实**：该输入新增会使存量组织升级后 dict_rev 全变→一次性全量重建（与 yaml_rev 引入同款先例，非缺陷；见第七节部署注记）。

### C 组 ✅

- **C-1/P2-1**：`QueryAuditQueue` 收 `backend_factory`（ContextManager 契约），flush 每批经工厂取独立 backend；缺省行为不变（sqlite 生产形态共享安全）。`AuditBackendFactory` 惰性单连接：首建双保险锁（`_lock` + `_flush_lock` 串行兜底）、`close()` swap 后关（未开为 no-op）、连接失败重试由 queue 既有回队/防毒丸路径处置（connect 失败时 `_conn` 保持 None → 下次 flush 重连，核验成立）。pg 臂 pid 断言（test_c1_pg:109-116）真实证明两连接不同。
- **flush 串行化**：单消费线程 + `_flush_lock` 全程（后台 thread / 显式 flush / stop 三面互斥）；`stop()` 先 join 后 flush，工厂连接同一时刻至多一个使用者——**论证成立**。
- **C-2**：并发用例收编形态真实（barrier 对齐、双线程、errors 汇聚、walk_chain fail-closed、行数对账）；sqlite 臂双 ThreadLocal 独立连接 + 月库 BEGIN IMMEDIATE，pg 臂搬运共享连接 + 查询道工厂独立连接（=P2-1 生产形态）。注入证据：摘互斥→sqlite 臂红（`database is locked`）实证捕获力（pg 臂同构逻辑上可捕获咨询锁摘除，未单独注入——P3-11 注记）。120 轮非 flaky（barrier 对齐 + 短事务 + busy_timeout 5s；tester 双模式复跑全绿）。
- **测试形态真实性**：pg 工厂连接与请求连接 pid 不同（真断言非旁证）；sqlite 臂工厂「不同对象」语义诚实（同月库目录）。

### D 组 ✅

- **D-1 文案**：i18n 8 行 diff = 4 键×2 语言（docs.upload.noDs / access.dims.new.foot / access.mem.empty / access.mem.footNote）；「无 GET members/m3-1 后端轮次」矛盾文案全清；api.js/access.js 注释与身份说明更新；banner 死 CSS 删除（web/ 内零 `.banner` 引用）。残留仅 style.css:550 段头注释仍列「降级横幅」（P3-3）。
- **键数复核（择型⑨）**：独立口径 `git show HEAD:i18n.js | grep -c '^    "'` = **1320 = 660 键×2 语言**；结合 diff 的 added=removed=∅（4 行替换×2 语言）——**零键增删实质成立，准确数字 660，coder 的 658 有误（tester P3-1 裁定正确）**。
- **G-28④ 双方言等价性**：sqlite 月库文件天然只含当月行，`id IN (…)` 与旧全扫同义；pg 新查询跨分区按 id（PK=(id,created_at) 前导 id 走索引），事件 id 唯一且月分区由 created_at 派生 → 「批内已存 id 跳过不推进 prev」语义等价（无跨月同 id 合法路径）；批 ≤200 ≪ sqlite 999 变量上限（协议面无 batch 上限文档——P3-9）。
- **G-28⑦ /stats**：`query_audit{dropped,pending}` 形状；未装配/取数异常 → null 不 500（防御旧壳）；端点仍 org_admin 门控（既有矩阵测试覆盖）。
- **D-5 audit 包裹**：REST annotate / get_entity（404 reason 回查 + 200 restricted_ids）、MCP annotate / get_entity（404 + 200）五处包裹范围正确——try 只包「为审计而做的取数」，主响应语义先定；空 ids 时既有 `_audit_restricted*` 早退 = 真「事件跳过」，注释与实现一致；test_d5 boom 分支真实触达（calls>=2）且 200/404 两种主语义保持。

## 二、测试质量审查

- **新用例断言强度**：A-1 断言 `embedder.calls==0`+审计 reasons/scope（非旁证）；A-2 `breaker._streak`+审计载荷 org/user（沿 m2-5 口径）；B-1 旧标签行「内容恰等」构造真实（UPDATE embed_model 后整替并断言全行新标签）；B-3 monkeypatch 计数==0（函数内 import 路径生效，核验无误）；C-1 pg pid 真断言；C-2 行数对账+walk_chain；D-4 溢出造数 dropped/pending 对账；D-5 双分支 boom 触达。**无走过场测试**。
- **test_r3_p2_2 断言翻转口径正当**：翻转对 B①「标记触发面整体移除」的直接映射（任务原文授权），docstring 详注口径来源；旧行为等价覆盖在新 test_b2 ①（健康+仅标记→不触发）且新覆盖面更宽（清标记+注记）；m2s-6 旧担忧（崩溃落库标记是唯一线索）已被 embed_model 入集合+内容/覆盖对账完备替代。**非放宽**。
- **计数对账（独立复算）**：`test_sem_g24_m33.py` 12 函数 → 22 条（10 双臂×2 + 2 单臂）；`test_query_audit_m33.py` 8 函数全双臂 → 16；合计 38 = 1880−1842 ✓；pg 臂新增 18 → 696+18=714 ✓；`1 deselected`=manual 维持 ✓。与 tester 报告字字闭合。
- **测试卫生**：见 P3-2/4/5/6/11。

## 三、分层与禁改面

- core/semantic 六文件 diff 内方言 SQL 关键字/`execute(` **零命中**；`audit_factory` 落 store/postgres（合法）；core 两包零 import 交叉；auto_entities 识别仍钉 api/mcp（recall 未被端点外调用面引入）。
- docs/ prototype/ .opencode commit 内零 diff ✓；web 4 文件白名单 ✓；冻结正文未动 ✓。

## 四、问题清单

**P1：无。P2：无。**

**P3（均不阻塞，附去向）**

1. **[P3] `src/knowledge_lattice/core/semantic/annotator.py:866-884`**：`_default_embed_batch` 已成**完全死代码**（全仓零调用），且 docstring 声称「仅供未接 … 的旧调用面兼容」——该「旧调用面」本轮已被删除，描述失真。建议后续 chore 批删除函数（或保留则改注「历史兼容，当前零调用——待清理」）。
2. **[P3] `tests/test_query_audit_m33.py:26`**：`import time` 未使用（D 组「未用导入清扫」批内新文件自引入）。顺手删。
3. **[P3] `src/knowledge_lattice/web/style.css:550`**：ui-1 段头注释仍列「降级横幅」为 ui-1 增补项，但 banner CSS 已删、web 内零 banner 引用。注释残留，建议下次 web 批删词或改为历史说明。
4. **[P3] `tests/test_query_audit_m33.py:211-216`**：sqlite 臂每轮新建 `ThreadLocalBackend(db_path)`（同一线程内每轮新建连接对象，收益为零）；功能性无碍（GC 即关），但属无谓连接抖动。建议循环外建一个实例复用（等价语义）。
5. **[P3] `tests/test_query_audit_m33.py:111,167`（+ `src/knowledge_lattice/store/postgres/audit_factory.py:37-48`）**：pg 臂工厂未显式 `close()`（进程退出兜底，tester P3-3 同源）；且工厂对「连接已损坏（PG 重启）」无重连路径——broken 连接会进入 flush 失败→3 次丢弃循环直至进程重启。当前生产恒 sqlite 无暴露，登记部署期（见第七节 RUNBOOK 建议）。
6. **[P3] `tests/test_r2_m2s6_fixes.py:316`**：函数名 `test_r3_p2_2_persisted_marker_triggers_repair` 与现断言（**不**触发）语义相反，docstring 已解释但名字易误读。建议更名（如 `…_marker_no_longer_triggers_repair`）。
7. **[P3] `src/knowledge_lattice/core/semantic/build.py:622-660`**：`_updated_fuzzy_stats` 对畸形 `stats_json` 回退 `{}` 后整行覆写——会把该 build 行的 eval/其他分量清成空壳（虽 stats 由自身序列化、损坏概率极低，且 `_prev_eval_metrics` 的回归基线依赖 eval）。建议：解析失败时**跳过持久化**（返回 None 或仅日志），防御面更保守。
8. **[P3] `src/knowledge_lattice/core/semantic/annotator.py:848-863`**：`_audit_annotate_vec_degraded` 与 `lookup._audit_sem_vec_degraded` 载荷结构重复（后者本轮已 scope 参数化，可直接复用）。载荷形状改动时双处维护风险，建议共用。
9. **[P3] `src/knowledge_lattice/store/sqlite/backend.py:2230-2233`**：`id IN (?,…)` 占位符数随事件数线性——当前唯一调用面 queue batch=200 安全，但协议方法无批上限声明；未来调用方若传 >999 会踩 SQLite 变量上限。建议协议 docstring 注明「≤batch 上限」或分片。
10. **[P3] A-1 四接线点无端点级用例**：新测试均直调 core（`search_entities`/`annotate_text`），REST/MCP 传参正确性仅靠代码审查（tester「四接线点实核」同款）。若后续 handoff 删参无测试兜底——建议 m3-4/后续 e2e 批补一条「gate 拒绝 → REST/MCP annotate 零 embed + probe_reject」端到端断言（不阻塞本轮）。
11. **[P3] C-2 捕获力仅 sqlite 注入实证**：pg 臂（咨询锁摘除→同 prev 分叉→walk_chain 红）为逻辑推演未实测注入；tester 3/3 注入已覆盖必修红线，pg 侧留待 PG 接线部署期复验即可。

## 五、需求边界问题（有——供上报，不交 coder）

1. **G-28③ 的生产接线面**：本轮交付 = `QueryAuditQueue.backend_factory` 能力 + `audit_backend_factory` 惰性单连接 + pg 双臂测试。**但 `app.py:332` 仍构造 `QueryAuditQueue(backend)`（无工厂）**，且 app 当前无 PG 后端装配路径（PG 仅测试注入）——即「flush 线程共享单连接」风险在**生产 PG 形态落地时仍需 lifespan 接线 + `close()` 关停调用**。此与 G-28③「PG 接线三件」的部署期属性一致，不属本轮缺陷；但**docs 批不可把 G-28③ 整条划销**，应改写为「机制+测试已交付，残余=生产 lifespan 工厂注入与关停 close（PG 接线部署期）」。建议请在回用户汇报中带出该口径（用户裁定 P2-1「段内修复」的范围解释）。
2. **mention 契约加可选字段**：裁定①已明确「有自然落位则补、无则转注记」——本实现判定有落位并在测试锁定；design §6.3② 属冻结正文，补记应走「非决策变更」声明（第七节 docs 批），不需回 spec 改需求。
3. **FUZZY_CODE_REV 的 bump 纪律**：运行时无强制（代码变更靠人守 docstring）——建议在 TEST-CASES m3-3 组/RUNBOOK 落一条纪律注记（「模糊算法/规范化行为变更必须 bump，否则 skipped 快速通过会保留陈旧产物」）；属文档面要求，不改代码。
4. **一次性重建提示**：`fuzzy_code_rev` 入 dict_rev 会使升级后首次构建全量重建（含评测门）——部署注记（非缺陷，沿 yaml_rev 先例）。

## 六、Tester 意见裁定

**CASE_BUG 裁定请求：无**（tester 未提交 CASE_BUG；无用例预期争议需裁）。

**Tester P3×3 处置**：

| # | tester 意见 | 裁定 |
|---|---|---|
| P3-1 | 择型⑨数字失真 658≠660、归因反向 | **确认**（独立复核 660=660）。无代码影响；以 660 为准确数；归档 manifest/docs 引 660。commit message 内的 658 为历史记录不改写。 |
| P3-2 | 择型② DeadlockDetected 收敛过程无留档 | **确认**。论证链成立，裁定 ACCEPT 维持；**去向=RUNBOOK §PG 接线/§1.z 复现注记**（监督侧 docs 批）。 |
| P3-3 | audit_backend_factory 生产 close() 接线点未存在 | **确认**，且**扩展为需求边界第 1 条**：G-28③ 不整条划销，留部署期残余；RUNBOOK 记录接线点。 |

**择型 9 条复核**：①ACCEPT（逐字同构已核）②ACCEPT（附 P3-2 留档）③ACCEPT（完备性独立复核成立，标记移除有任务授权）④ACCEPT（可补齐态非内容态，fast path 保留覆盖检查）⑤ACCEPT（行为更新非放宽，等价覆盖在 test_b2 且覆盖更宽）⑥ACCEPT（双方言对称等价，行为面 qa9/c2 承载）⑦ACCEPT（形状/None 语义/防御合理）⑧ACCEPT（gate 先于 embed_batch 分支，确定性注入面豁免合理）⑨ACCEPT（实质成立，数字勘误 660）。

## 七、docs 批建议清单（监督侧执行）

1. **known-gaps.md**
   - G-23：**划销**——收口措辞含：①embed_model 入内容集合（含迁移崩溃窗回归）；②修复清标记+repaired 注记；③内容哈希锚（带模型维，健康 skipped 零 pypinyin）；④观测语义入行；⑤FUZZY_CODE_REV 入 dict_rev；附「标记触发面整体移除（任务 B① 授权）+三路对账完备性」一句。
   - G-24：⑥⑦⑨ 划销（⑦ 注「非决策变更：mention 可选字段，design §6.3② 自然落位」；⑨ 注 gate 四接线点+scope=annotate 有界/熔断/审计）。
   - G-28：④⑤⑦ 划销（④ existed 按批 id 双方言；⑤ 并发用例入正式门禁；⑦ /stats）；**③ 改写为「机制+测试已交付（m3-3），残余=生产 lifespan 工厂注入+close()——PG 接线部署期」**（不整条销）；①②⑥⑧ 维持。
2. **TEST-CASES.md**：登记 m3-3 组（A-1~A-4 / B-1~B-5 / C-1~C-2 / D-4~D-5，38 条=双臂 22+16）；A-4 mention 契约可选字段注记；FUZZY_CODE_REV bump 纪律注记。
3. **design.md**（非决策变更声明，不动 D 编号）：若需注记——§6.3② mention 实装携带 disambiguation（向后兼容）；§5.8 模糊对账内容哈希/标记面口径（与 m3-2 A-16 注记同栏）。
4. **requirements.md**：无需改动。
5. **RUNBOOK.md**：PG 接线段补 ①audit_backend_factory 使用面+`app` lifespan 接线点与 `close()` 关停（tester P3-3）②DeadlockDetected 复现注记（惰性单连接择型依据：每轮开连 × 分区滚动 DDL × 并发写事务 catalog 锁——tester P3-2）③FUZZY_CODE_REV bump 运维纪律 + 升级一次性重建提示。
6. **issue #15 关闭材料**：A-1/A-2 交付（gate 四接线点 + scope=annotate 有界/熔断/审计 + 测试名清单）→ 随 PR 关闭 comment（附 SHA 3a0a214）。
7. **AGENTS.md / _m3-plan.md**：row3 状态 done；门禁 1842+1→**1880+1**；m3-3 检查点终态归档（含本报告裁定与被采信 tester 结论）。
8. **交付 PR description / evidence manifest**（见第八节）。

## 八、遗留去向与 manifest 要点

**本轮清偿（可勾销）**：m3-2 移交 P2-1（机制+测试）、G-28⑤、文案 4 键、未用导入（除 P3-2）、audit 取数包裹；m3-1 移交 G-24⑥⑦⑨、G-23 残余①~⑤、code versioning；issue #15 材料齐。
**移交/登记**：G-28③ 生产接线残余（部署期）；FUZZY_CODE_REV 纪律（文档面）；P3-1/2/3/4/5/6/7/8/9/10/11 随单转交（顺手/后续批，不阻塞）。

**manifest 要点（交付阶段写 PR description）**：
```json
{
  "head": "<交付时最终 HEAD>",
  "codeSha": "3a0a214aff9074997caec298d40c7723d8b739a8",
  "testedSha": "3a0a214aff9074997caec298d40c7723d8b739a8",
  "reviewedSha": "3a0a214aff9074997caec298d40c7723d8b739a8",
  "deliveryHead": "<docs 批+chore 归档批后的 HEAD——与 codeSha 区分记录>",
  "testVerdict": "PASS",
  "reviewVerdict": "APPROVED",
  "gate": "scripts/test_gate.sh → 1880 passed, 1 deselected, 0 skipped（双后端双模式；pg 臂 714）",
  "selectionAdjudication": "择型 9/9 ACCEPT（⑨数字勘误→660）",
  "caveats": [
    "G-28③ 生产 lifespan 工厂注入+close() 随 PG 接线部署期落地（本批仅机制+测试）",
    "fuzzy_code_rev 入 dict_rev → 升级后首次构建一次性全量重建",
    "docs/chore 后若 src/tests 有变更须 tester 回归+committer 复审增量；纯文档批则 manifest 双 SHA 以 codeSha 为准并核对终态 HEAD"
  ],
  "stale": false
}
```

## 九、结论

**reviewVerdict: APPROVED ｜ reviewedSha: `3a0a214aff9074997caec298d40c7723d8b739a8`**

P1/P2 无；P3×11 均不阻塞且去向明确；tester P3×3 予以确认（P3-3 扩展为需求边界残余项）；择型 9 条复核维持 ACCEPT；四组实现与任务原文（含裁定①②③）语义一致，完备性/并发/边界论证成立；分层与禁改面合规；门禁计数与申报闭合（以 tester 独立复跑为证据，静态计数独立复算一致）。可进入 docs 批 → chore 归档 → push/PR → 交付阶段 PR review 留痕。本会话不 push/不合入/不开 PR。

</details>
