---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2s-4
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e6f5be028ffe5bMFEHHmfwOCDu
testerTaskId: ses_e6f196342ffe3ySUnVnz3XPtNM
committerTaskId: ses_e6eec3950ffenSwI5aZRZxh10g
status: approved
round: 3
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 8d32750de7225afb822286751fb3e0e2e99bae49
reviewedSha: 8d32750de7225afb822286751fb3e0e2e99bae49
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["src/knowledge_lattice/core/semantic/annotator.py", "src/knowledge_lattice/core/semantic/evalrun.py", "src/knowledge_lattice/core/semantic/build.py", "src/knowledge_lattice/core/semantic/yaml_corpus.py", "src/knowledge_lattice/core/semantic/yaml_merge.py", "src/knowledge_lattice/api/semantic.py", "src/knowledge_lattice/mcp/server.py", "src/knowledge_lattice/config.py", "src/knowledge_lattice/store/backend.py", "src/knowledge_lattice/store/sqlite/*", "src/knowledge_lattice/store/postgres/*", "src/knowledge_lattice/worker/maintenance.py", "eval/semantic_seed.py", "eval/semantic_golden.jsonl", "eval/semantic_golden.README.md", "tests/test_sem_02_annotate.py", "tests/test_sem_04_api.py", "tests/test_build_05_report_eval.py", "tests/test_sem_eval_golden.py", "tests/test_g19_daily_fallback.py", "tests/test_m2s4_followups.py", "tests/test_yaml_02_merge.py", "tests/test_build_04_current_ptr.py", "pyproject.toml", "uv.lock", ".env.example", "docs/TEST-CASES.md(v1.9.7 批)", "AGENTS.md(批)", ".opencode/workflows/_m2-plan.md(批)", ".opencode/workflows/task-knowledge-lattice-m2s-3.md(终态批)", "tests/test_r2_m2s4_fixes.py(R2 新增)", "docs/known-gaps.md(R2 批——G-19 收口回写)", "R3 增量: worker/runner.py、tests/test_r3_m2s4_fixes.py、docs 批 v1.9.8（TEST-CASES/known-gaps G-21/AGENTS.md/_m2-plan——annotator/evalrun/build/api·semantic/yaml_corpus 已在列、semantic_golden.README 同批）"]
endReason: null
createdAt: 2026-10-31T14:26:07+0800          # 创建时间（30 天清理审计用，见 README §4.5）
updatedAt: 2026-10-31T17:20:16+0800          # 每次写检查点必更新为当前时间（ISO 8601 含时区），不得沿用旧值
---

# task-knowledge-lattice-m2s-4: M2-S2 面上段——AC 自动机 + annotate 四步消歧 + 识别评测集与门槛 + G-19 收口

## 任务原文

（依据 design §7·§8 M2-S2 面上段 + TEST-CASES §六 M2-S2 行剩余条目 + _m2-plan 段表第 8 行；**段序调整**：2026-10-31 用户确认——语义轨道优先做完（m2s-4 → m2s-5 → m2s-6 → m2-4 → m2-6 → m2-5 收口），m2-4 SSO 顺延、无依赖阻塞）

**A. 核心功能（语义识别面）**：
1. **AC 自动机**（pyahocorasick）构建于 semantic build 产物——active 实体 alias+name 全量入自动机；随 build 生命周期（build ready 后可用、构建中沿用旧实例）；内存占用与构建耗时纳入构建报告。
2. **annotate 工具**（MCP `semantic_annotate` + REST 对应端点）：输入自然语言文本 → 输出识别出的业务对象类型化实体标注（span/实体键/匹配路径）；**四步消歧**：精确全词 → 别名（区分大小写/词边界）→ 上下文（短别名需上下文词佐证）→ L0 片段兜底；overlap 择优规则（最长匹配优先）；负样本文本零标注。
3. **L0 片段召回**：curated_json L0 definition 片段作为 annotate 兜底与 expand 的引用面（m2s-3 已入快照——本段消费）。
4. **构建报告**（`GET /semantic/builds/{id}/report` 或等价面）：实体/别名计数、AC 自动机规模与构建耗时、dict_rev 各分量、缺源警告——运维可观测。
5. **识别评测集与门槛**：eval/ 语义黄金集（target 150~200 条——正样本含精确/别名/歧义/短别名上下文，负样本无实体文本）；指标 precision≥0.95 / recall≥0.80 / 歧义处理≥0.85 / 负样本误报≤0.05；评测脚本进门禁或独立 scripts/ 命令（口径：非 Flaky、双后端一致）。

**B. 挂账收编（m2s-3 移交——其检查点遗留事项节为权威）**：
1. **G-19 五源每日兜底调度**（known-gaps 在库）：五源各一次/日兜底 sync 接线——窗口口径（worker maintenance 挂载或独立循环）、幂等（同 rev no-op）、与 webhook 触发去重；收口后 known-gaps G-19 状态回写（docs 批监督侧落笔、coder 原样 commit）。
2. **自校验回退健壮性⑦**：JSON Schema 校验回退路径对 type 数组/布尔子 schema/tuple items 的 false positive（except Exception 兜底，零依赖 only）——修正或注记。
3. **sensitivity 两口径**：④覆盖层删除不回退最后声明值（口径化+用例）；⑤非法 sensitivity 静默归 normal（注记或收紧）。
4. **测试卫生 3 项**：旧 test_rule_pure 弱断言可删/inserted 计数微瑕/两测试名实不符——顺手清理。

**C. 验收**：T-S4（annotate 四步消歧+门槛）/ T-S12（构建报告）+ TC-SEM-01~04·06·07、TC-BUILD-02·04·05、TC-SEV-01/02（TEST-CASES §六 M2-S2 行剩余全清——完成后 M2-S2 行整行 ✅）；门禁基线 1209+1 单调不减、双后端双模式 0 skipped。

**D. docs/约束**：docs 批（工作区 TEST-CASES v1.9.7/AGENTS.md/_m2-plan 含段序调整注记/m2s-3 检查点终态 + 本段 G-19 收口回写）由监督侧落笔、coder 原样 commit 入库；core/semantic 零方言 SQL；pyahocorasick 入依赖（uv.lock 同步提交）；禁改 requirements/design 正文（决策变更走 issue）。

## 需求确认
- [x] 用户已确认（2026-10-31 14:26 确认任务书——status=implementing）
- 历史遗留事项清单：17 个历史检查点全部 done 无未了结任务级遗留；m2s-3 移交四项（G-19/⑦/sensitivity 两口径/测试卫生）已并入本任务 B 节；TC-UI-01~04 手动走查为用户侧待办（不并入）。

## 遗留事项（跨任务移交）
- [x] 交付归档批（2026-10-31 17:20）：P3 补登记 r5/r6/r8/r9 落 known-gaps G-21「R3 终审补登记」段（ambiguity 分子收紧 M2-S3/ambiguous_aliases 注释出入/无 build L0 返回空/precision 分母/mixed-mode 门槛/double_build 名实/maintenance 四项/重复 import/用例空转两项）；AGENTS.md+/_m2-plan ✅ 终态（语义 4/6、下一段 m2s-5、基线 1323+1）
- [x] 移交 m2s-5（_m2-plan row 9 挂账权威）：G-21 方案 A（build 快照附表）/歧义缺省读法显式化+ambiguity 分子收紧/TC-BUILD-05（已移入 M2-S3 行）/错别字正样本/TC-PERF-05/R3 用例空转两项补强
- [x] TC-UI-01~04 手动走查：用户侧待办（M1 遗留——不并入，持续挂账）

## 轮次记录
（待 R1）

R1: coder 完成（2026-10-31 15:39，commit `2c798bf1c1464e1e785b8b196c9f075969d395c0`，30 文件 +3277/−114；基线 e870fd1 无分叉）：A1 AC 自动机（pyahocorasick 入 lock；只收 exact/context、restricted 不入机；随 build 生命周期 ready 切换/构建中沿用）✅；A2 annotate（MCP `annotate`〔design §6.3 契约名——任务书 semantic_annotate 出入①〕+REST POST /semantic/annotate；四步消歧 exact→alias→context→消歧四级 cooccurrence>focus>prior>L0 兜底>ambiguous；最长优先+拉丁词边界）✅；A3 L0 片段（消歧④步消费 curated l0+GET /semantic/l0）✅；A4 构建报告（GET builds/{id}/report：计数/自动机规模耗时/rev 分量/缺源/断链/歧义别名/孤立/冲突/评测指标）✅；A5 评测集 172 条（exact 52/alias 36/abbr 15/ambig 20/context 14/neg 35）+四门槛+>2pp 回归双门内联 run_build（eval_blocked 置 failed 可定位——出入③）✅；B1 G-19 兜底调度（maintenance 挂载/窗口跨零点/pending 幂等/sem_sync_runs 去重；**known-gaps 回写留 R2——出入⑨**）✅；B2⑦ 回退误拦修正 ✅；B3④⑤ 口径化+收紧 ✅；B4①②③ 测试卫生 ✅。自测：TDD 红灯（首败 ModuleNotFoundError annotator）；门禁 commit 后 HEAD 复验 **GATE PASS 1294+1**（pg 臂 450=417+33，双模式 0 skipped，1209+1→1294+1 +85）；评测实测 precision/recall/ambiguity/neg_fp=1.0/1.0/1.0/0.0（items 172、neg 占 20.3%、确定性双跑一致）。docs 批 v1.9.7/AGENTS.md/_m2-plan/m2s-3 终态已随 commit 入库（supervised-coding.md 排除）。**口径出入 10 条**已列（MCP 工具名/L0 落位消歧④步/门槛拦截形态/评测适用面 ≥20 条且 80%/歧义缺省读法/TC-BUILD-04 数值构造/TC-BUILD-05 归属 M2-S3 待裁定/T-S4·T-S12 括注错位/G-19 docs 留 R2/pyahocorasick 镜像回滚）——待 Tester/Committer 验证后随边界意见报用户裁定。

R1: tester **FAIL**（2026-10-31 16:05，testedSha=2c798bf）：**1 IMPL_BUG 阻断**——annotate 空可用别名词典运行期崩溃（annotator.py L361-374 build_automaton 空 trie 上 make_automaton 不生效〔pyahocorasick 行为〕，iter() 抛 AttributeError→REST/MCP 500；三触发面实测全崩：全 restricted/全 fuzzy_only/零别名——违背 T-S9 restricted 表现为不存在+负样本零标注语义；修复面小：空自动机防御+永久用例）。SPEC_GAP 1：TC-BUILD-05 归属（tester 独立核实支持 coder 判断——semantic_retag 仅 worker 预留分发位，消费面 TC-TAG-01/02 整个在 M2-S3，本段做只能产空壳→随 committer 裁定落 docs）。OBSERVATION 6：O1 门禁对账微差（+86 实算 vs +85 申报——上轮工作区收集项推测，本轮 1294 硬数字）/O2 G-19 docs 留 R2/O3 跨零点窗口无永久用例/O4 评测适用面豁免为 coder 自加口径（登记备忘）/O5 黄金集全 zh（M3 双语 TC-EVAL-02）/O6 recall 分母口径。**其余全过**：验收逐条（TC-SEM-01~04·06·07/BUILD-02·04/SEV-01/02、T-S4 由 test_sync_02_guard 承载核实成立、T-S12 生命周期双臂）、门禁 1294+1 双模式 0 skipped 属实（pg 臂 450 全实跑）、G-19 专项全过（五源/幂等/webhook 去重/窗口跨零点探针）、评测防自证深挖全过（seed 真实管线 51 实体非旁路造数/tester 自写计算器逐位一致/变异测试证指标敏感：删别名 recall→0.9272、去关系+L0 ambiguity→0.64/出入⑤歧义缺省 80% 靠真实消解）、交叉面（MCP=design §6.3 契约名核实/pg 定向抽核/lock 四平台完整/并发 8×30 一致）、零弱化实证（1 真删有逐列强断言覆盖、3 改名）。**R2 修复清单**：①空自动机防御+永久用例；②O3 跨零点永久用例；③G-19 known-gaps 回写；④TC-BUILD-05 归属随裁定落 docs。

R2: coder 完成（2026-10-31 16:18，commit `9100bfb`，父 2c798bf；annotator.py `_scan` 空自动机防御+tests/test_r2_m2s4_fixes.py 13 条+docs 批 G-19 收口回写原样入库）：①IMPL_BUG 修复——`len(self.automaton)==0` 短路零命中（三触发面 core 面零标注+dict_rev 锚点/REST 面 200+mentions==[]，双后端实跑）；②O3 跨零点窗口永久用例（_in_window 单元面 23:30/02:00/端点/窗外/非法 fail-open+body 面窗内外投递，双后端）；③G-19 known-gaps 收口回写（监督侧落笔 R2 原样入库——出入⑨清偿）；④TC-BUILD-05 不处理（待裁定）。自测：TDD 红灯（新用例首跑 6 failed 首败同源 AttributeError；修复后 sqlite 9 passed/DSN 后 13 全实跑）；门禁 **GATE PASS 1307+1**（pg 臂 454=421+33，双模式 0 skipped，1294+1→1307+1 +13）。已过面零触碰（diff 仅 _scan+新测试+docs）。

R2: tester **PASS**（2026-10-31 16:27，testedSha=9100bfb）：IMPL_BUG 修复彻底——探针 T1~T3 三触发面独立复现（core 零标注+dict_rev 在场/REST 200 修复前 500，[pg] 实跑 5 条）；实现审查式验证（iter 全文件唯一调用点在 _scan 短路无旁路/len==0 两态安全/零词与从未构建不可达区分）；边界 T4~T5（空文本/超长契约不变/正常词典无副作用）。O3 永久用例逐条对照 D1~D7 口径覆盖+扩展（端点/负例/同日窗/body 落库断言）——非数数。G-19 docs 批核验（总览+正文与 R1 交付口径逐项一致/O2 关闭）。门禁 **GATE PASS 1307+1**（pg 臂 454=421+33，双模式 0 skipped；+13 对账吻合：core 3 函数双臂 6+REST 3+O3 纯函数 2+body 双臂 2；tests/ 零删除零改动，R2 diff 仅 3 文件）。回归抽核 25 passed+门禁全量兜底。SPEC_GAP 仅剩 TC-BUILD-05 归属（待 committer 裁定）；OBSERVATION O1/O4/O5/O6 维持登记级。

R2: committer **NEEDS_CHANGES**（2026-10-31 16:41，首次审查落 R2 轮——R1 Tester FAIL 未走审查）：**P1×1**——render_l0 无 restricted 过滤（restricted+l0 合法 YAML 形态经 /semantic/l0 向任何 org 成员泄露名称/brief/definition——识别面均 fail-closed 而 L0 导出面破口；修法一行过滤+永久用例，或用户显式接受+known-gaps 登记）；**P2×4**——P2-1 annotate/L0 读 live 快照非 build 产物（冷缓存/重启窗口 dict_rev 锚点失真+**评测门禁拦下的词典重启后仍被服务**——failed build 治理仅进程生命周期内；方案 A=sem_builds 增快照列/附表〔符合冻结设计〕/方案 B=POC 取舍+known-gaps 登记+永久用例钉死——**需用户裁定**）/P2-2 ambiguity 分母混入伴随标注稀释门槛（25 分母 vs 20——答错 3 条仍 0.88 放行；Tester 计算器同口径未察）/P2-3 A1「内存占用」未进报告（get_stats() 有 size 未透传）/P2-4 docs 段序自相矛盾（AGENTS.md 仍「下一段 m2-4」+ _m2-plan 段序调整注记缺失——监督侧修）/P2-5=⑦ TC-BUILD-05 行移动；**P3×16**（_cand_ids 泄露/裸 JSON 500/precision 分母口径/L0 单 bigram 过松/context 门槛交互/全角永久用例/double_build 名实/缺省读法稳定性/maintenance 四项/worker env 两键/items 布尔/l0_extra 未消费/拉丁粘接/alias confidence 0.95/TC-PERF-05 无归属/重复 import）。测试质量：真实在测无走过场，4 覆盖缺口（restricted+l0 不可见/冷缓存 T-S12/ambiguity 分母/全角永久）。**边界裁定**：①annotate=design 契约（笔误）②L0 消歧第四级接受（TEST-CASES 注记+P3-4 收紧建议）③eval_blocked failed 接受（「需人工确认」无入口须登记）④适用面豁免接受（须 TEST-CASES/known-gaps 登记）⑤缺省读法接受（M2-S3 前改显式）⑥分离构造正确（改用例文档示例数值）**⑦TC-BUILD-05 移 M2-S3 行（明确裁定——四依据；docs 未移前不得宣称 M2-S2 行整行 ✅）**⑧任务书括注写反（监督侧注记）⑨G-19 docs 接受 O2 关闭⑩lock 干净；**新增边界 ⑪~⑭**：⑪大小写按 design 折叠（任务书「区分大小写」笔误）+「全量」读作「全量可用面」⑫TC-SEV-01 错别字正样本随 M2-S3 模糊层（注记）⑬TC-PERF-05 无归属（建议随 m2s-5/m2-5 或本段补）⑭docs 段序=监督侧修。R3 修复面小（round=3 内可收敛）；本轮不置 reviewedSha。

**R2 用户裁定**（2026-10-31 16:44「按建议执行」）：P1-1 照修（render_l0 跳 restricted+用例）；**P2-1 取方案 B**（报告无单一倾向，按「R3 内收敛」语境——best-effort 保留+known-gaps 登记〔监督侧落〕+永久用例钉死冷缓存行为+/semantic/l0 与 annotate 同锚点；方案 A〔sem_builds 快照附表〕登记为 M2-S3/收口段演进缝）；P2-2/P2-3 纯代码 R3 修；⑦ TC-BUILD-05 移 M2-S3 行（监督侧落 TEST-CASES）；⑪ 按 design 不改码；⑫⑬ 注记落 TEST-CASES（TC-PERF-05 → m2s-5/m2-5）；⑭ 监督侧修 docs 段序；③④⑤⑥⑧⑨⑩ 按裁定登记。P3 顺手项（P3-1/P3-2/P3-10/P3-11）随 R3，其余登记级。**round=3（maxRounds）——R3 必须收敛**。

R3: coder 完成（2026-10-31 16:59，commit `8d32750`，12 文件 +565/−25；父链 8d32750←9100bfb←2c798bf←e870fd1）：**P1-1 修**（render_l0 跳 restricted+_build_stats ambiguous_aliases 改识别可用面口径；YAML 覆盖层 restricted+l0 → l0 无片段/报告无其 alias_norm/annotate 零命中——双后端）；**P2-1 方案 B**（l0 端点改走 get_annotator 同锚点同 rev；冷缓存永久用例钉死：构建中单例+live 可命中+旧 ready rev；**评测拦下后清缓存=重启形态服务被拦词典+旧 rev**——G-21 显式钉死，双后端）；**P2-2 修**（歧义 span 词典侧判定〔与识别可用面同口径〕，label surface ∈ 歧义 norm 集才计分子分母；用例 20 歧义+5 伴随答错 3 → 0.85 卡边不稀释〔旧口径 0.87 放行实证〕；黄金集重算分母 25→20 四指标 1.0/1.0/1.0/0.0；README 同步）；**P2-3 修**（memory_bytes/edges/words 透传+七字段在场断言）；**全角永久用例**（ＪＸＤＫ/XJXDKX 词边界/JXDK+jxdk）；**P3 顺手 4 项**（_cand_ids pop+断言/裸 JSON 400/_worker_env 两键/items is True/False 显式）；docs 批 v1.9.8+G-21+AGENTS+_m2-plan 原样入库。自测：TDD 红灯（7 failed 逐项预期）；门禁 **GATE PASS 1323+1**（pg 臂 459=426+33，双模式 0 skipped，1307+1→1323+1 +16）。其余 P3 零触碰/评测集 jsonl 零改动/无重构。

R3: tester **PASS+收敛判定**（2026-10-31 17:10，testedSha=8d32750）：独立探针 32 断言全过——P1-1 四面封堵（REST 直打 restricted+l0：片段/报告/annotate 零出现+不误伤正常实体）；P2-1 同锚点实证（单例/sync→build 窗口双面 rev 逐位一致/冷缓存钉死用例与 G-21 逐句对照/G-21 docs 在库）；P2-2 独立重算（自写计算器分母 20 逐位一致/答错 3=0.85 卡线·4=0.80 拦/旧口径 0.88 放行算术实证/README 伴随 qid 明细）；P2-3 七字段（memory_bytes=28472/edges≥keys≥words）；全角三条+P3×4 全过；docs 批六注记+整行收口+移行+段序与裁定逐项一致。门禁 **GATE PASS 1323+1**（pg 臂 459=426+33，双模式 0 skipped；+16 对账吻合；tests/ 零删除零改动）。回归抽核 30 passed（P2-2 口径变更后既有评测用例仍真在测——新口径更严断言仍有效）。SPEC_GAP 闭环（TC-BUILD-05 已移行）；O4/O5/O6 随 v1.9.8 注记闭环；无新增观察。**「修复面已收敛，无新阻断——round=3 收敛，建议 Committer 终审 APPROVED」**。

R3: committer **APPROVED**（2026-10-31 17:16 终审，reviewedSha=8d32750 三一致）：P1/P2 六项逐条闭环核验全闭合（P1-1 与建议一致+_build_stats 加固正确；P2-1 方案 B 同锚点+冷缓存钉死+G-21 逐句一致+方案 A 挂 m2s-5；P2-2 词典侧判定=首选建议+卡边算术实证；P2-3 实测 28472；P2-4/P2-5 docs 与裁定逐项一致——本轮再核通过）；P3 顺手 4 项质量过（P3-1 用例未覆盖非歧义分支→P3-r2 登记）；新引入面审查无新 P1/P2（render_l0 无副作用/l0 无 build 返回空=合理收敛 P3-r8/evalrun 歧义段无新崩溃）；边界⑦~⑭ 落实核对一致。**P3 残留 r1~r10 登记放行**（r1 报告面断言空转/r2 P3-1 用例歧义分支/r3 同锚内容断言弱/r4 stub 注释口径/r5 ambiguity 分子主候选口径 M2-S3 收紧/r6 ambiguous_aliases 未滤 fuzzy_only 注释出入/r7 README qid 明细/r8 TC-SEM-06 无 build 注句/r9 五项 R2 P3 补登记/r10 filesChanged 增补+归档终态——随交付归档 docs 批补登记）。三面评价：Coder 修复小而准/Tester 证据链扎实（未识别两空转用例与 P3 登记缺口）/监督侧 docs 一致（剩归档终态）。**交付归档清单建议**：reviewedSha=归档 docs-only HEAD（沿先例）、检查点终态+filesChanged 增补 R3 12 文件、G-21/_m2-plan 补登 r5/r6/r9、AGENTS/_m2-plan ✅ 终态、PR+manifest（双 SHA/1323+1/rounds=3/specRulings 全量/gapClosures G-19·G-21·TC-BUILD-05·TC-PERF-05·O4~O6/handover m2s-5 五项+P3 残留）。**双通过达成（round=3 收敛）**。

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

<details><summary>R1 Tester 报告全文（2026-10-31 16:05，testVerdict=FAIL）</summary>

**testedSha: `2c798bf1c1464e1e785b8b196c9f075969d395c0`**（git log 核验一致）
**testVerdict: FAIL**（1 × IMPL_BUG 阻断——其余验收面全过，详见 §三）

## 一、跑了什么（数字原样引用）

**1. TDD 独立复跑**（6 新测试文件，sqlite 单跑形态）：
```
collected 87 items … 64 passed, 23 skipped in 2.28s
```
23 个 skip 逐个核对：**全部为 `[pg]` 参数化条目**（无 DSN 时设计行为）——门禁设 DSN 后已全实跑，**任务范围内零异常 skip**。

**2. 门禁全量**（`docker start lattice-pg` + DSN + `scripts/test_gate.sh`）：
```
1294 passed, 1 deselected, 2 warnings in 224.45s   [pytest]
1294 passed, 1 deselected, 3 warnings in 204.25s   [pytest-O]
GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
（pg 臂 450 条用例全实跑：[pg] 参数化 417 + PG 专用 33）
```
与基线声明 **1294+1** 一致；**skip=0，双模式**。

**3. 独立探针**（tester 自写 38 断言，`tests/probe_m2s4.py` 已删——仓库零残留）：**37 passed / 1 failed**。

## 二、验收用例逐条

| 用例 | 结果 | 证据 |
|---|---|---|
| TC-SEM-01 规范化同函数 | ✅ | 3 用例：全半角/空白等价形命中+span 回映原文（`span==[0,13]` 含空白切片）、与 `normalize_alias` 同函数 |
| TC-SEM-02 最长匹配/权重 | ✅ | 「留抵」vs「留抵税额」留长 span；等长取 weight 高者（3.0 胜 1.0） |
| TC-SEM-03 消歧四级 | ✅ | 共现→focus→prior→全部候选 `ambiguous=true` 且 `confidence<1.0`；**L0 兜底第四级独立用例**（resolved_by='l0'） |
| TC-SEM-04 context 短别名 | ✅ | 三态：有关系保留/无关系丢弃/单独出现丢弃（mentions==[]） |
| TC-SEM-06 L0 导出 | ✅ | REST `GET /semantic/l0` 片段+dict_rev+token_estimate+403；超预算 CI 拦截半句由 m2s-3 `test_yaml_01_corpus_ci.py::test_ci_l0_budget_blocks` 承载（在位核实） |
| TC-SEM-07 契约与限流 | ✅ | 结构齐 via='ac'/mentions 有序；>4000 字 core ValueError+REST 400 双面；context_entities>20 拒绝 |
| TC-BUILD-02 产物三件套 | ✅ | `skipped_fuzzy_only==1` + 语义面复核（fuzzy_only 永不命中）；报告字段齐（counts/ac_automaton/dict_rev_components/missing_sources/eval） |
| TC-BUILD-04 回归门槛 | ✅ | **出入⑥核实成立**：0.98→0.955（双双过绝对门，只触回归门）failed+`regression:true`+current 不动；0.99→0.94 触绝对门 `below_threshold:true`；0.97→0.955（1.5pp≤2pp）放行——两门分离验证构造正当（用例文档示例 0.96→0.93 双门同触，无法分离归因） |
| TC-BUILD-05 重标投递 | ⛔ 未实现 | **出入⑦独立核实：coder 归属判断成立**——`semantic_retag` 仅是 `worker/__init__.py` 预留分发位，消费面（TC-TAG-01 ingest 打标/TC-TAG-02 retag）整个在 M2-S3；本段做只能产空壳。SPEC_GAP 报 committer 裁定（用例 M2-S2 行含 05 与里程碑依赖矛盾） |
| TC-SEV-01 评测集规格 | ✅ | 172 条（150~200 内）、六类齐、负样本 35 条（20.3%）、qid 唯一/span 越界·重叠·空切片逐条断言、README 规范随集、key 全部可解析参考词典+70% 覆盖 |
| TC-SEV-02 回归门槛 | ✅ | 参考词典 run_build 自动评测→四指标进报告（双后端 33 条含 pg 臂实跑）；确定性双跑断言 |
| T-S4 宽限期状态机 | ✅ | 承载核实成立：`test_sync_02_guard.py::test_t_s4_missing_then_recover_then_retire`（①missing 关系保持②恢复回 active〔关系一并〕③8 天前→retired 且关系一并 retired）+ 6 天/7 天边界用例 |
| T-S12 构建原子切换 | ✅ | 骨架面 `test_build_01_rev_switch`（失败旧 ready 保留）+ 本段懒加载半句：构建中 `ann1b is ann1` 同实例、`sem_switch_build_ready` 注入失败→failed 行+仍 r1 服务、重建后新实例切换（双臂） |

## 三、发现问题分级

### 🔴 IMPL_BUG（阻断，1 项）——testVerdict=FAIL 依据

**空可用别名词典 annotate 运行期崩溃**：`src/knowledge_lattice/core/semantic/annotator.py` L361-374 `build_automaton` 在 entries 空时（restricted 全跳过 / fuzzy_only 全跳过 / 零别名），`auto.make_automaton()`（L374）在空 trie 上**不生效**（pyahocorasick 库行为），运行期 `self.automaton.iter(norm)`（L203）抛：
```
AttributeError: Not an Aho-Corasick automaton yet: call add_word to add some keys
and call make_automaton to convert the trie to an automaton.
```
三种触发面探针实测全崩：**全 restricted / 全 fuzzy_only / 零别名**——该 org 下任何文本 REST/MCP annotate **500**，而非零标注。直接违背 T-S9「restricted 表现为不存在」（fail-closed 变 crash）与负样本零标注语义。现有测试只测混合词典（自动机非空），未覆盖此合法极端形态。**修复归 coder**（空自动机防御+永久用例，修复面很小）。

### 🟡 SPEC_GAP（需裁定，1 项）
- TC-BUILD-05 归属（出入⑦）：核实结论支持 coder——依赖 M2-S3 打标面。需 committer 裁定完成态移行。

### ⚪ OBSERVATION（登记，6 项）
- **O1 门禁对账微差**：diff 实算净增 +86 条目（87 新 − 1 真删）vs 申报 +85——推算 merge 基线（e870fd1）not-manual=1208，上一轮申报 1209 含当时工作区 1 条未提交收集项（推测上轮 tester 探针残留；文件级 diff 已证提交树**零删除零弱化**）。本轮实测 1294 为硬数字，不受影响。
- **O2** G-19 known-gaps 状态回写留 R2（出入⑨）——R2 必须携带。
- **O3** 跨零点窗口（`_in_window` 23:00-05:00 形态）实现正确（探针 D1~D7 全过）但**无永久用例**——建议 coder 补。
- **O4** 评测适用面豁免（≥20 条且 80% 可解析才评测，否则 skipped 不拦构建）为 coder 自加口径——语义合理（半套词典指标无意义），但弱化门槛刚性，登记备忘。
- **O5** 黄金集 lang 全 zh（README 已注记双语 M3 承接，TC-EVAL-02）。
- **O6** recall 分母口径：不可解析 label 不进 gold 分母（条目级适用面 ≥80% 缓解，参考词典部署下影响趋零）。

## 四、G-19 专项（全过）
五源各一次/日（enqueued==5）、pending 同参去重（二次 tick==0）、与 webhook 去重（sem_sync_runs 成功 run 24h 内跳过）、失败 run 不作锚、interval=0 disabled、未配置源静默跳过、run_maintenance 注册表全链；**窗口含跨零点**探针补验（23:30/02:00/12:00/05:00 边界/非法窗口 fail-open）+ body 窗内投 5/窗外零投递。

## 五、评测面深挖（防自证——全过）
- **多样性**：172 条零重复文本、唯一 6 字前缀 157/172、50 唯一 key、工单/群聊口语质感（抽样目验）；
- **seed_reference_org 真实管线**：探针实测四源 run_sync+YAML run_yaml_sync 全 succeeded——51 active 实体（metadata 14/template_center 11/report_center 9/scenario_config 3/yaml 14）、别名四 kind（name 51/code 51/manual 23/abbr 4/sync 1）、43 关系、19 条 curated——**非旁路造数**；
- **四指标独立抽验**：tester 自写计算器（不 import evalrun 公式）与 evalrun **逐位一致**：P=1.0/R=1.0/amb=1.0/neg_fp=0.0（matched=151/pred=151/lab=151、amb 25/25、negfp 0/35、items=172）；
- **变异测试证指标敏感**：删「留抵退税」全部别名 → recall 1.0→0.9272、precision→0.9524；去关系+L0 → ambiguity 1.0→0.64——**指标真实在测，非形同虚设**；
- **出入⑤歧义缺省读法**：20 条歧义样本 resolved_by 分布 l0=14/cooccurrence=4/single=5/ambiguous=2——80% 靠真实消解机制；仅 2 条无佐证条目靠「缺省主读=实现第一候选」（README 显式登记口径）——带轻微自证色彩但已披露+占比小，接受并登记。

## 六、交叉面与边界（全过）
- MCP/REST 一致性：同走 `annotate_text` 编排+双面测试；工具名 `annotate`=design §6.3 契约（L1156/1160/1170），**出入①成立**（任务书 semantic_annotate 为笔误）；
- pg 臂定向抽核 33 passed（新测试 pg 条目 3 个 + 既有 `test_mcp_semantic_tools` + `test_build_01_rev_switch`）——**既有语义工具/构建面零回归**；
- worker maintenance 既有任务零回归（门禁全量绿）；pyahocorasick 2.3.1 lock 完整（macosx arm64/universal2、manylinux x86_64/aarch64、musllinux、win wheels + sdist）；.env.example 三新配置登记；
- 边界防御探针：拉丁词边界（xxjdkxx/XJXDKX 不命中、独立 JXDK/fppt 命中）、全角ＪＸＤＫ、内嵌空白 span 回映、emoji 混合、末尾 span 闭合、空文本拒绝、纯符号零标注、**并发缓存 8 线程×30 无异常结果一致**——除 A4 外全部通过。

## 七、回归核对（零弱化实证）
4 个删除 def 中 3 个为**改名**（test_build_04_current_ptr，断言保留+注释名实相符化）、1 个真删（`test_rule_pure_collides_with_synced_entity`）已被 `test_r2_m2s3_fixes.py::test_p2_2_colliding_pure_entry_leaves_sync_entity_untouched` **逐列强断言覆盖**（name/attrs/source_system/status/三类别名原样——已读源码核实，强度严格高于被删用例的仅 source 列断言）。文件级 diff：tests/ 零删除文件、6 新增。

---
**结论**：testVerdict=**FAIL**（唯一阻断 = annotate 空可用别名词典 500 崩溃，IMPL_BUG 归 coder 修+补永久用例；其余全验收面、G-19、挂账、评测面、交叉面、边界防御全过，门禁 1294+1 双模式 0 skipped 属实）。R2 修复清单建议：①空自动机防御+永久用例；②跨零点窗口永久用例（O3）；③G-19 known-gaps 回写（出入⑨）；④TC-BUILD-05 归属随 committer 裁定落 docs。

</details>

<details><summary>R2 Tester 报告全文（2026-10-31 16:27，testVerdict=PASS）</summary>

**testedSha: `9100bfb0638840681f228d923f687be130e1f5b7`**（git log 核验一致，父=`2c798bf` ✓）
**testVerdict: PASS**

## 一、执行概况（数字原样引用）

**门禁全量**（`docker start lattice-pg` + DSN + `scripts/test_gate.sh`）：
```
1307 passed, 1 deselected, 3 warnings in 191.20s   [pytest]
1307 passed, 1 deselected, 3 warnings in 191.20s   [pytest-O]
GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
（pg 臂 454 条用例全实跑：[pg] 参数化 421 + PG 专用 33）
```
基线 **1307+1** 达成；**skip=0，双模式**。

**+13 对账**：R2 新增 `test_r2_m2s4_fixes.py` 9 函数 = core 3 函数双臂（6 条目）+ REST 3 条目 + O3 纯函数 2 条目 + body 1 函数双臂（2 条目）= **13 条目** ✓；pg 参数化 417→421 = +4（3 双臂 core + 1 双臂 body）✓。**tests/ 零删除零改动**（git diff 面仅 3 文件：annotator.py +10 行、known-gaps.md ±8 行、新测试 +276 行）——回归零弱化。

**独立复验探针**（tester 自写 23 断言，`tests/probe_r2_verify.py` 已删——仓库零残留）：**23 passed / 0 failed**。

## 二、分项复验

### 1. IMPL_BUG 修复复验（R1 阻断项）✅

**①三触发面独立复现**（探针 T1~T3，core+REST 双面，与 coder 永久用例互相独立）：
- 全 restricted：`annotate_text` 零标注+`dict_rev` 在场、REST **200**（修复前 500）、mentions==[]（T1a~T1d）
- 全 fuzzy_only：构造同 norm 先删 name/code 后插 fuzzy_only——build ready、core 零标注、REST 200（T2a~T2c）
- 零实体：空 org build ready、零标注不崩、REST 200、org 隔离仍在（T3a~T3d）

**②实现审查式验证**（探针 T6~T7 静态+动态实证）：
- `automaton.iter` 全文件**唯一调用点在 `_scan`**（count=1）——短路位置覆盖全部路径，无旁路；
- `if not len(self.automaton):` 在场且先于 iter（源码位置核验）；
- `len(automaton)==0` 判据两态安全：零词自动机 len==0 → annotate 安全零标注；「从未构建」态在 `build_automaton` 恒调 `make_automaton()` 下不可达（构造期行为不变，meta 观测面 keys==0 正常）；
- 附带确认：修复后 `_scan` 文档化注释准确（fail-closed 不变 crash 口径）。

**③边界补充**（探针 T4~T5）：空词典+空文本仍拒（ValueError→REST 400 契约不变）、+超长仍拒、纯符号/emoji 零标注行为一致；**正常词典无副作用**（命中/via='ac'/REST 命中全回归）。

**coder 永久用例独立复跑**：`tests/test_r2_m2s4_fixes.py` **13 passed**（含 **[pg] 实跑 5 条**：core 三触发面双臂 + body 双臂——修复在 PG 后端下同样成立）。用例质量核验：core 面走 `run_build`→`annotate_text` 服务编排（REST/MCP 同路径）、REST 面断言 `status_code == 200, resp.text`（修复前 500 形态直接钉死）、`dict_rev` 在场断言防「短路误伤 rev 锚点」。

### 2. O3 永久用例核验 ✅（逐条对照 R1 探针 D1~D7）

| R1 探针 | R2 永久用例 | 断言 |
|---|---|---|
| D1 23:30 窗内 | `test_o3_in_window_overnight_wrap` L221 | `is True` |
| D2 02:00 窗内 | L222 | `is True` |
| D3 12:00 窗外 | L225 | `is False` |
| D4 05:00 边界含端 | L224 | `is True` |
| D5 非法 fail-open | `test_o3_in_window_same_day...` L240-242 | bogus/中文/缺半边三形态全 `True` |
| D6 跨零点窗内投递 | `test_o3_daily_body_window_no_dispatch_outside[sqlite/pg]` 23:30 → enqueued==1 + tasks 表 pending 落库 | ✓ |
| D7 窗外零投递 | 同用例 12:00 → enqueued==0 + tasks 表零行 | ✓ |

**超出探针口径的扩展**：23:00 lo 端 / 05:01 / 22:59 负例、同日窗口（01:00-05:00）端点含端语义（01:00/05:00 True、00:59 False）、body 面 tasks 表落库断言。**非数用例数——口径逐条覆盖成立**。

### 3. G-19 docs 批核验 ✅
- 总览表（L31）：「已接受（M2-S4 承接）」→「**已收口**（m2s-4 R1——maintenance 挂载 semantic_daily_sync：五源/日·窗口跨零点·pending 幂等·sem_sync_runs 24h 与 webhook 去重）」；
- 正文（L209-211）：状态=已收口+交付口径（interval 可配 0=关/pending_task_exists/失败 run 不作锚/Tester 专项全过含跨零点探针 D1~D7）、对冲标历史、重开条件=无——**与 R1 代码交付口径逐项一致**；
- R2 diff 面核验：docs 仅 `known-gaps.md` 一个文件（8 行），无其他 docs 混入；检查点文件未动（只读纪律合规）。**O2 关闭**。

### 4. 回归确认 ✅
- R1 验收面抽核 **25 passed**：消歧四级①（cooccurrence）+L0 兜底消歧+最长匹配、G-19 全部 20 条（含 pg 臂 10 条实跑）、评测四指标达标+进报告（sqlite+pg 双臂）；
- 门禁 1307 全量兜底（1294 存量 + 13 新增全绿双模式）；
- R2 diff 面（annotator 仅 `_scan` 入口一处）无副作用——探针 T5 正常词典行为回归实证。

## 三、问题分级

- **IMPL_BUG**：无（R1 阻断项已修复并双通道实证）；
- **SPEC_GAP**：无新增。TC-BUILD-05 维持 R1 裁定（SPEC_GAP 待 committer——本轮按指令不验）；
- **OBSERVATION**：R1 遗留 O2（G-19 回写）、O3（跨零点永久用例）**本轮双收口关闭**；O1（基线对账微差，上轮工作区残留所致）、O4（评测适用面豁免口径）、O5（黄金集全 zh，README 已注记 M3 承接）、O6（recall 分母口径）维持登记级，均不影响判定。

---
**结论**：testVerdict=**PASS**（testedSha=`9100bfb0638840681f228d923f687be130e1f5b7`）。IMPL_BUG 修复彻底（短路无旁路、两态安全、三触发面 core+REST+[pg] 双后端全零标注）、O3 永久用例超探针口径覆盖、G-19 docs 收口一致、门禁 1307+1 双模式 0 skipped 对账吻合、零回归零弱化。剩余待办归监督侧/committer：TC-BUILD-05 归属裁定（R1 SPEC_GAP）。

</details>

<details><summary>R2 Committer 报告全文（2026-10-31 16:41，reviewVerdict=NEEDS_CHANGES——首次审查落 R2 轮）</summary>

## 0. 基线与轮次核验

- `git log --oneline`：`9100bfb`（R2）← `2c798bf`（R1）← `e870fd1`（m2s-3 merge）。审查对象 `git diff e870fd1..9100bfb`（32 文件，+3565/−118）；R2 面 `git diff 2c798bf..9100bfb` 仅 3 文件（annotator +10 行、known-gaps ±8、tests 新增 276），与检查点 R2 声明一致。
- 检查点 `testedSha=9100bfb=HEAD` ✓；`reviewedSha=null`（首次审查）✓；我未改动检查点（工作区仅有监督侧未提交的 `supervised-coding.md` 与未跟踪检查点，均不在 HEAD）。
- 门禁证据：采信 R2 Tester 实测 `1307 passed / 1 deselected / 0 skipped`（双模式、pg 臂 454=421+33）。我未复跑（本审查环境 shell 仅放行 git/gh）；从测试清单复核 +13 对账成立（3 core 函数×2 + REST 3 + O3 纯函数 2 + body×2 = 13），R2 `tests/` 零删除零改动属实。
- R1→R2 处置核对：空自动机 IMPL_BUG 已修（`_scan` L208 短路，`automaton.iter` 全仓唯一调用点在短路之后，三触发面 + REST 200 + [pg] 实跑永久用例在位）；O3 跨零点永久用例（D1~D7 逐条覆盖并扩展端点/负例/同日窗/落库）；G-19 known-gaps 回写（总览+正文与实现口径逐项一致，O2 关闭）。R2 修复质量：**成立**，无新回归面（已过面零触碰）。

---

## 1. 问题清单

### P1（阻断）

**P1-1 `render_l0` 未做 restricted 过滤——L0 导出向全体 org 成员泄露敏感实体定义（鉴权 fail-closed 破口）**
- 位置：`src/knowledge_lattice/core/semantic/annotator.py:448-471`（`render_l0` 仅判 `curated.get("l0")`，无 sensitivity 判定）；暴露面 `src/knowledge_lattice/api/semantic.py:294-311`（`semantic:read` = 任何 org 成员）；数据源 `store/{sqlite,postgres}/backend.py` 的 `sem_active_snapshot` 取全部 active 实体、不过滤 sensitivity。
- 问题：`sensitivity='restricted' + l0: true` 是合法 YAML 形态（`yaml_corpus.validate_corpus` 只校验 l0 预算与 sensitivity 枚举，不禁止组合）。该实体的**名称/brief/definition** 会原样进 `/semantic/l0`，而本段其余识别面（annotate 不入机、expand 404、search_entities 过滤）全部按 T-S9/§6.3③ 采取了「M2-S3 权限面交付前一律不可见」的 fail-closed 口径。L0 是 agent system prompt 的输入面，正文泄露比 alias 命中更严重（`semantic:restricted` 未交付前，任何成员可读）。
- 修改建议：`render_l0` 跳过 `sensitivity == 'restricted'`（fail-closed；M2-S3 权限面交付后再按 `semantic:restricted` 放行）；补永久用例（YAML 覆盖层造 restricted+l0 实体 → `/semantic/l0` 无该片段；`GET /semantic/builds/{id}/report` 不含其 alias_norm）。若认为此面随 M2-S3 处理，需用户显式接受并在 known-gaps 登记，不能静默。

### P2（应修）

**P2-1 annotate / L0 读 live 快照而非 build 产物：`dict_rev` 锚点失真 + 评测门禁在冷缓存/重启后失效**
- 位置：`annotator.py:404-433`（`get_annotator` 缓存 miss 时用 `sem_active_snapshot` 按当前 ready rev 标注服务，仅告警）；`api/semantic.py:306-309`（L0 恒读 live，`dict_rev` 取 current ready）；`build.py:304-342`（eval 拦截后 live 已被 sync 写入，build 行 failed）。
- 问题：进程内热缓存路径符合任务 A1「构建中沿用旧实例」，T-S12 双臂用例也只覆盖热缓存。但：
  1. **冷缓存/重启窗口**（进程启动、缓存被清）在构建中或构建失败后，`live_rev != current_rev` 时实现把 live 字典当旧 rev 服务（日志 warning），违反 design §5.8「构建中请求始终用旧 `dict_rev`」与 T-S12 的字面；`sem_builds` 无快照列/表，无法按 rev 重建旧产物。
  2. **评测门禁不可持久**：回归/绝对门槛拦下的词典已写入 live 表，只是不切 ready；进程重启后 annotate 会直接服务被拦词典，且响应 `dict_rev` 仍是旧 ready rev——「failed build 不切 ready」的治理语义仅存在于进程生命周期内。这正是用户问的「failed build 的自动机/查询面行为」。
  3. `/semantic/l0` 即使无重启也在 sync→build 窗口内出现「内容新、dict_rev 旧」的不一致（agent 侧按 rev 缓存 system prompt 会误判）。
- 修改建议（二选一，需用户裁定）：
  - **方案 A（符合冻结设计）**：`sem_builds` 增建快照列/附表（如 `sem_build_snapshots(build_id, snapshot_json)`，实体+别名+curated 的最小 JSON），`get_annotator`/`render_l0` 按 current build id 取快照；无快照才回退 live（回退需登记）。比只在缓存里放实例更符合「按 (org, dict_rev) 懒加载」。
  - **方案 B（POC 取舍）**：保留 best-effort，但必须在 known-gaps 登记「构建中/拦下后的词典在冷缓存或重启后会被服务，评测门禁非持久」，并补永久用例显式钉死该行为（否则 T-S12 验收证据不完整）；同时 `/semantic/l0` 与 annotate 采用同一锚点，避免 rev/内容错配。
  至少需在交付前明确落 A 或 B，不能停留在代码注释。

**P2-2 ambiguity 指标分母口径混入非歧义标注，稀释 ≥0.85 门槛**
- 位置：`src/knowledge_lattice/core/semantic/evalrun.py:113-117`。
- 问题：`ambiguity` 对 `kind=pos_ambiguous` 条目的**全部 labels** 计数。黄金集 s104~s123 共 20 条、25 个 label——s106/s107/s108/s110/s111 各多一个「确定性实体」标注（留抵退税/场景/报表项/小规模/一般纳税人）；实现口径为 25 分母而非 20。后果：歧义消解实际答错 3 条时指标仍为 22/25=0.88（放行），真实口径 17/20=0.85（卡边）；且长定义/容易命中的伴随标注系统性抬高指标。Tester 自写计算器沿用了同一口径（报告 `amb 25/25`），未发现此稀释。
- 修改建议：只统计「表面是歧义别名（同一 alias_norm 多实体共享）」的 span 标注；或在黄金集 label 增可选 `ambiguous: true` 标记；或（若接受条目级口径）在 `semantic_golden.README.md` 与 TEST-CASES TC-SEV-02 显式登记「条目级、含伴随标注」并补一条口径用例。当前指标意义与文档「歧义消解率」不一致，属应修。

**P2-3 任务 A1 的「内存占用」未进构建报告（仅有 keys/nodes/build_ms）**
- 位置：`src/knowledge_lattice/core/semantic/build.py:115-171`（`_build_stats`/`ac_automaton` meta 只 `keys/nodes/build_ms/skipped_*`）；`annotator.py:384-390`。
- 问题：任务 A1 明写「内存占用与构建耗时纳入构建报告」；`nodes` 只是规模代理，不是内存。`pyahocorasick.get_stats()` 若提供 `size`/`edges_count`/`words_count`（实现已调用 `get_stats()`，只取了 `nodes_count`），直接透传 `memory_bytes`/`edges`/`words` 即可闭环；若坚持 nodes 作代理，需在报告/checkpoint 显式申报「内存口径=节点数」。
- 建议：补 `size` 字段（并转 `automaton_meta`），测试断言字段在场；或用户确认以节点数代替代。

**P2-4 docs 批段序自相矛盾（AGENTS.md / _m2-plan）——监督侧修**
- 位置：`AGENTS.md:10`「下一段 m2-4（SSO/JIT 对接）」；`.opencode/workflows/_m2-plan.md:21`（m2-4 标「下一段（待开工）」）、`:23`（m2s-4 仍 ⬜）。
- 问题：任务书 2026-10-31 用户确认段序为「语义轨道优先：m2s-4 → m2s-5 → m2s-6 → m2-4 → m2-6 → m2-5」；m2s-3 完成后下一段是 **m2s-4（本任务）**，不是 m2-4。任务书 D 还要求 `_m2-plan` 含**段序调整注记**，本批只加了「任务 ID ≠ 里程碑段号」的编号口径注记，未落段序调整。新会话按 AGENTS 开工会被引到 m2-4，属高影响文档错误。RT（本段）交付批须改：AGENTS「下一段 = m2s-5（语义 S3 基础）」；_m2-plan row 7 去掉「下一段」、row 8 标「◐/✅」并补段序调整注记。
- 注：docs 批按任务书由监督侧落笔、coder 原样 commit——**不是 coder 代码问题**。

**P2-5 TC-BUILD-05 归属（出入⑦，见边界裁定）——docs 行必须移动**
- 位置：`docs/TEST-CASES.md:892-895`、`:1068`（M2-S2 行含 05）、`:1069`（M2-S3 行缺 05）；任务书 C 节亦列 05。
- 裁定见 §3：**移 M2-S3 行**。在 TEST-CASES 未移动前，M2-S2 行不能宣称「整行 ✅」。

### P3（建议）

1. `annotator.py:297`：非歧义 mention 未 `pop("_cand_ids")`，JSON 输出带内部字段（值为 `[winner]`）；API/MCP 每个 mention 都多一个下划线字段。建议统一 pop，或仅在 ambiguous 时保留；`tests/test_sem_02_annotate.py:228-239` 用 `keys <= set(m)` 放过了它，建议加「无下划线私有键」断言。
2. `api/semantic.py:269`：`await request.json()` 非法 JSON 会抛未处理 `JSONDecodeError` → 500；建议 try/except 转 400（其他端点用 pydantic/Form，本端点是新裸 JSON 面）。
3. `evalrun.py:96-119`：precision 分母 `predicted_total` 不含 neg 条目的预测（neg 在 `continue` 前未累计），负样本 FP 只进 `neg_fp`；两门都在，风险低，但「precision=匹配/预测总数」的 docstring 与实现有偏差，建议口径化。
4. `annotator.py:262-273`：L0 兜底 `best > 0` 即定案（单个 bigram 重叠即可消歧），且分数未按定义长度归一——长 definition 更易胜；建议 ≥2 重叠或归一化，并在 TEST-CASES 注记（属边界②的一个加固面，不是阻断）。
5. `annotator.py:224-225`：`is_context = all(r["match_mode"]=="context")`。同一 alias_norm 同时有 exact（实体 A）与 context（实体 B）时（种子中的「留抵」正是此形态），整条命中按非 context 处理，B 的 context 短别名门槛（同句确定命中+有关系）被绕过，改由 L0/共现定案；语义上可接受但建议按候选逐个套 context 门槛，或在 TEST-CASES/README 登记该规则交互。
6. 永久测试补强：`test_tc_sem_01_norm_nfkc_fullwidth_and_spaces`（`tests/test_sem_02_annotate.py:97`）名含 fullwidth 但只测空白；全角输入经 annotate（如 `ＪＸＤＫ`）仅 Tester 探针覆盖，探针已删。建议补 `ann` fixture 拉丁别名并永久断言全角/大小写/词边界三条（黄金集间接覆盖了拉丁边界，但仍建议直测）。
7. `tests/test_sem_eval_golden.py:137-150`：`test_..._double_build` 实际在同一 Annotator 上跑两遍 `run_recognition_eval`，并未「double build」；建议改为两次独立构建（或改名），否则「非 Flaky」证据名实不符。
8. 歧义缺省读法 = 实现第一候选（候选按 `(-weight, entity_id)` 排序），取决于插入序/实体 ID；README 已登记，但换库/换同步顺序可能翻转 s109/s117/s122 类样本。建议改为 YAML 显式缺省主读或按稳定业务键排序，并把两个无佐证条目在 README 按 qid 列出。
9. `worker/maintenance.py`：①模块 docstring 任务清单 1~9 未加入 semantic_daily_sync；②非法 `semantic_night_window` fail-open 会在每轮 maintenance（默认 300s）打 warning，属日志噪音；③daily 投递未写触发审计事件（run 级 `semantic.sync` 仍有，POC 可接受，但 G-16 口径下建议登记）；④`pending_task_exists` 按 payload 字符串精确匹配，而手动触发 payload 含 `"force": false`、兜底不含，二者不能互相去重（sync 幂等兜底，风险低）——建议按 (type, org, adapter) 规范化去重。
10. `worker/runner.py:429-462`：`_worker_env` 注释称「全 LATTICE_SEM_* 往返闭合」，但新增的 `LATTICE_SEM_DAILY_SYNC_INTERVAL_S`、`LATTICE_SEM_EVAL_GOLDEN_PATH` 未映射；经 os.environ 继承的生产形态不受影响，程序化 Settings（测试/嵌入调用）会子进程漂移。建议补齐两个键。
11. `yaml_corpus.py:365`：`items not in (True, False)` 因 `1 == True` 会把 `items: 1` 当布尔子 schema 放行；`_minimal_schema_errors`（L461-467）对 `items: true/false` 不校验，`items: false` 回退路径静默放行任意元素。建议 `items is True/False` 显式判断并在 errors 里处理 boolean items。
12. `l0.yaml` 额外文本（`Corpus.l0_extra`）仍未被 `render_l0` 消费（m2s-3 已登记观察，TC-SEM-06 未要求）；建议在 README/known-gaps 继续挂账，避免 M3 误以为已导出。
13. `annotator.py:82-91`：去空白后拉丁词与相邻词粘接（"abc def" → "abcdef"），别名 "abc" 因边界判定不命中——保守方向（无 FP），但属可解释性缺口；`_normalize_with_map` 逐字符 NFKC 与 `normalize_alias` 整串 NFKC 对组合字符不等价（docstring 已披露）。建议登记。
14. `_TIER_CONFIDENCE` alias=0.95：§6.3 中间件只自动注入 `confidence=1.0` 命中，意味着别名档永不自动注入（M2-S3 中间件需确认这是设计意图）。
15. TC-PERF-05 无归属行：TEST-CASES M2-S1 行「剩余 TC-PERF-05 → M2-S2」，但 M2-S2 行未列它、本段任务书也未列，annotate P99 无测量/无归属；建议在 `_m2-plan`/TEST-CASES 明确「随 m2s-5/m2-5」或补本段 perf 用例。
16. `build.py:174-184` 顶部已 import `EVENT_SEMANTIC_BUILD`，`_audit_build` 内重复 import；`api/semantic.py` 的 annotate 只捕获 ValueError（其他实现异常 500）——低价值清理。

---

## 2. 测试质量评价

**结论：总体真实、无走过场、无 skip/弱化；但存在 4 个应补的覆盖缺口。**

- **门禁面**：R1 6 个新文件 + R2 1 个新文件，无 `skip/skipif/xfail`；diff 中 5 个删除 def = 4 个改名（名实相符化，断言保留）+ 1 个真删（`test_rule_pure_collides_with_synced_entity`），后者由 `test_r2_m2s3_fixes.py::test_p2_2_...` 逐列强断言（name/attrs/source_system/status/三类别名）覆盖，强度高于原用例，**不构成弱化**。R2 +13 条目对账与测试清单吻合；测试计数本审查环境未复跑（见 §0）。
- **真实在测**：空自动机三触发面同时钉 core 集成 + REST 200（`assert resp.status_code == 200, resp.text` 会直接暴露修复前 500）；`dict_rev` 在场断言防短路误伤；T-S12 双臂用 `sem_switch_build_ready` 注入异常验证旧实例继续服务；G-19 全链（五源/pending 去重/成功 run 24h/失败 run 不作锚/窗口跨零点/注册表全链）；评测面用真实 `seed_reference_org`（四 sync+YAML 合并）跑黄金集并断言四指标+报告，非旁路造数；变异证据（删别名 recall→0.9272、去关系+L0 ambiguity→0.64）证明指标敏感。
- **覆盖缺口（应补）**：
  1. **restricted+l0 → `/semantic/l0` 不可见**（对应 P1；现有用例只测 restricted 的 annotate 面）。
  2. **T-S12 冷缓存/重启窗口**（对应 P2-1；现有 `test_t_s12` 只测 `ann1b is ann1` 热缓存）。
  3. **ambiguity 分母**（对应 P2-2；Tester 计算器与实现同口径，未独立于公式）。
  4. **全角输入经 annotate 命中**（TC-SEM-01 的永久证据缺；现仅 `normalize_alias` 单测 + Tester 探针）。
- **弱断言/名实**：`test_tc_sem_07_output_structure` 的 `keys <= set(m)` 掩盖 `_cand_ids` 泄露；`test_tc_sev_02_eval_deterministic_double_build` 不是双构建；`test_tc_sev_01` 的 neg 占比带宽 10%~30% 较松（可接受）。均为 P3。
- **评测资产自证风险**：172 条四指标恰为 1.0/1.0/1.0/0.0，标签与参考词典同作者、同批交付；虽然变异测试与「80% 真实消解」做了对冲，仍建议在交付说明中标注该集合为「实现协同设计基线」，M3 前请用户侧/独立标注抽样复核（尤其 s109/s117/s122 三条缺省读法）。

---

## 3. 需求边界问题（有）

以下不是代码缺陷、交监督侧回 spec/文档确认；其中 ⑦ 为必须落地的裁定。

### 对 Tester/Coder 出入 ①~⑩ 的裁定

| # | 事项 | 裁定 |
|---|---|---|
| ① | MCP 工具名 | **按 design §6.3 `annotate`**；任务书 `semantic_annotate` 为笔误。**成立**，不改。 |
| ② | L0 兜底落位消歧第四级 | **接受**（任务书 A2/A3 明写「L0 片段兜底」，design §5.9 未列不等于禁止；有 `test_tc_sem_03_l0_...` 用例）。但须在 **TEST-CASES TC-SEM-03 注记**「四级消歧后增 L0 证据级，ambiguity 才算 ambiguous」；并建议按 P3-4 收紧证据阈值（单 bigram 过松）。**P3 加固，不阻断**。 |
| ③ | 门槛拦截形态 eval_blocked→failed | **接受**（`sem_builds.status` 冻结枚举无 blocked；failed 是唯一不切 ready 的终态，任务级 done 正确；报告/审计可定位）。但须登记：**「需人工确认」当前无确认/强制放行入口**——误拦时只能修词典或改黄金集重建；建议 known-gaps/RUNBOOK 记一句，并考虑在 stats.eval 增加顶层 `gate:"blocked"` 便于运维过滤（P3）。注意 P2-1 使该「拦截」在重启后失效，需一并处理。 |
| ④ | 评测适用面豁免（≥20 且 ≥80%） | **接受为口径**：半套词典的指标无意义；但当前只写在 `evalrun.py` docstring/配置注释，须在 TEST-CASES TC-SEV-02（版本注记）或 known-gaps 登记，并写明「门槛仅对参考词典部署生效，非参考 org 构建不做识别评测」。 |
| ⑤ | 歧义缺省读法 | **接受（README 已显式登记）**，但该读法=实现第一候选（按 weight+eid），换库/换插入序可能翻转（P3-8）；建议 M2-S3 前改为 YAML 显式缺省主读。 |
| ⑥ | TC-BUILD-04 示例数值双门同触 | **coder 分离构造正确**（回归门 0.98→0.955、绝对门 0.99→0.94、放行 0.97→0.955）；需改的是 **TEST-CASES 示例**（0.96→0.93 改为单门可归因的数值或注明「双门同触、验证需分离构造」）。 |
| ⑦ | **TC-BUILD-05 归属** | **裁定：移 M2-S3 行（明确）。**理由：①`semantic_retag` 在 `worker/runner.py:61` 的 `CLAIMABLE_TASK_TYPES` 中不可认领、`worker/__init__` 明示「预留分发位」——本段若投递只会产生永久 pending 任务；②消费面 TC-TAG-01/02（ingest 打标/retag）整体在 M2-S3；③design §8 M2-S3 第 2 项明确把 `semantic_retag` 列入 M2-S3，M2-S2 第 3 项只列「构建产物+报告+原子切换+评测回归」；④「别名增删 diff」判定本身依赖打标面设计。**执行动作（监督侧 docs）**：`docs/TEST-CASES.md` §4.4 TC-BUILD-05 标题/§六 M2-S2 行移除 05、M2-S3 行加入「TC-BUILD-05（依赖 semantic_retag 消费面）」，并注明「M2-S2 行其余条目全 ✅ 后可整行收口」；任务书 C 节与检查点同步注记。在 docs 未改之前，**不得宣称 M2-S2 行整行 ✅**。 |
| ⑧ | T-S4/T-S12 括注错位 | **任务书 C 节括注写反**：T-S4 = 宽限期状态机（m2s-3 已交付）、T-S12 = 构建原子切换（本段）。验收按编号而非括注；监督侧在检查点/任务书注记修正，不改码。 |
| ⑨ | G-19 docs 已随 R2 入库 | **接受，O2 关闭**：known-gaps 总览+正文与 R1 实现逐项一致，R2 diff 面仅 known-gaps 8 行，检查点未被 coder 改动（只读纪律 OK）。 |
| ⑩ | pyahocorasick 镜像事件 | **接受，lock 干净**：`pyproject.toml` `pyahocorasick>=2.0`；`uv.lock` 2.3.1，pypi 源、macos arm64/universal2、manylinux x86_64/aarch64、musllinux、win 轮子+sdist 齐；无镜像 URL 残留。 |

### 本次新增边界（需 supervision/spec 确认）

| # | 事项 | 建议裁定 |
|---|---|---|
| ⑪ | 任务书 A2「别名（**区分大小写**/词边界）」vs design §5.9「NFKC→小写」 | **按 design/TC-SEM-01：大小写折叠（不区分）**；任务书措辞为笔误。同理 A1「alias+name **全量**入自动机」应读作「全量可用面」——fuzzy_only（TC-BUILD-02）与 restricted（T-S9）必须排除，代码正确。 |
| ⑫ | TC-SEV-01 要求覆盖「**错别字**」，黄金集无错别字正样本（仅 s150/s151 边界负例） | AC 层无法消解错别字，正样本属 M2-S3 模糊层（TC-SEM-09/TC-SEV-03）。**建议在 TC-SEV-01 与 README 注记「错别字正样本随 M2-S3 模糊兜底补入」**，否则 TC-SEV-01 覆盖声明不完整。**不阻断本段代码**。 |
| ⑬ | TC-PERF-05 在段表中**无归属**（M2-S1 说 → M2-S2，M2-S2 行未列，本任务书未列） | 建议明确「TC-PERF-05 随 m2s-5/m2-5 承接」或补本段 annotate P99 用例；否则 annotate 的 P99<5ms/20ms（§6.3/NFR-11）无验收归属。 |
| ⑭ | docs 批段序错误（P2-4）与 `_m2-plan` 段序调整注记缺失 | 监督侧修正（AGENTS.md/_m2-plan/TEST-CASES/checkpoint 注记），与 ⑦ 同批落。 |

---

## 4. 交付把关

- **依赖**：`pyahocorasick` 入 pyproject + uv.lock 规范（四平台轮子完整），未引入镜像地址；`requires-python` 未变。
- **配置**：`.env.example` 三新配置（`LATTICE_SEM_NIGHT_WINDOW` 语义更新、`LATTICE_SEM_DAILY_SYNC_INTERVAL_S`、`LATTICE_SEM_EVAL_GOLDEN_PATH`）在位；`config._validate` 补非负校验；注意 golden path 相对 CWD、文件缺失 → 评测 skipped（fail-open），部署侧应配绝对路径并在上线检查（P3）。
- **分层**：`core/semantic`（annotator/evalrun/build）零方言 SQL；api/mcp 为薄壳共用 `annotate_text`/`build_report`；store 双方言 `pending_task_exists`/`source_system`/`rowcount` 对称（sqlite/pg diff 已核）。
- **docs 批**：G-19 回写一致（⑨）；但 P2-4 的段序错误与 `_m2-plan` 注记缺失必须在交付归档批修正；TEST-CASES 的 05 行随 ⑦ 移动。
- **交付 manifest**：尚未创建（当前 reviewedSha=null；testedSha=HEAD 一致）。本轮 **NEEDS_CHANGES**，不置 reviewedSha、不生成 manifest；R3 修复后按流程补双 SHA/门禁/rounds 证据并留 PR 痕。

---

## 5. 结论

**reviewVerdict: NEEDS_CHANGES**

- **P1×1**：L0 导出 restricted 泄露（必须修或用户显式接受并登记）。
- **P2×4（代码/口径）**：冷缓存/重启下的 rev 锚点与评测门禁失效（需明确 A/B 方案）；ambiguity 分母稀释；A1 内存字段缺失；P2-4 docs 段序（监督侧）；P2-5 即 ⑦（docs 行移动）。
- **P3×16**：见 §1（不阻断，建议 R3 顺手或登记级下段）。
- 修复面整体很小（P1 一行过滤+测试；P2-2 小口径修正；P2-3 透传 `get_stats()` 的 size；P2-1 需先由用户裁定 A/B；docs 由监督侧落笔），round=3 内可收敛。
- **CASE_BUG 裁定请求：未收到**（R1 Tester 的 IMPL_BUG 为代码缺陷，非用例预期错误；无其他 CASE_BUG 提交）。
- 本轮不设置 `reviewedSha`；R3 修复后以新 HEAD 复审，P1/P2 关闭后再走交付留痕与 manifest。

</details>

<details><summary>R3 Tester 报告全文（2026-10-31 17:10，testVerdict=PASS+收敛判定）</summary>

**testedSha: `8d32750de7225afb822286751fb3e0e2e99bae49`**（git log 核验一致，父=`9100bfb` ✓）
**testVerdict: PASS** —— **收敛判定：修复面已收敛，无新阻断；round=3 达成收敛，建议 APPROVED**

## 一、执行概况（数字原样引用）

**门禁全量**（`docker start lattice-pg` + DSN + `scripts/test_gate.sh`）：
```
1323 passed, 1 deselected, 3 warnings in 189.79s   [pytest]
1323 passed, 1 deselected, 3 warnings in 189.79s   [pytest-O]
GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped
（pg 臂 459 条用例全实跑：[pg] 参数化 426 + PG 专用 33）
```
基线 **1323+1** 达成；**skip=0，双模式**。

**+16 对账**：R3 新增 `test_r3_m2s4_fixes.py` 11 函数 = 5 双臂（10 条目：P1-1/P2-1×2/P2-2 golden/P2-3）+ 6 单臂（6 条目：P2-2 stub/全角/P3-1/P3-2/P3-10/P3-11）= **16 条目** ✓；pg 参数化 421→426 = +5 ✓。**tests/ 零删除零改动**（diff 面 12 文件与检查点申报一致，评测集 jsonl 零改动）。

**独立复验探针**（tester 自写 32 断言，`tests/probe_r3_verify.py` 已删——仓库零残留）：**32 passed / 0 failed**。

## 二、分项复验

### 1. P1-1（L0 restricted 泄露）✅
独立构造 YAML 覆盖层 restricted+l0（不走 coder fixture 路径，REST 直打）——四面：
- **片段面**：`GET /semantic/l0` 200，restricted 实体片段零出现（`机密测算模板`/`限制口径正文` 全文不含）；
- **报告面**：`build_report.ambiguous_aliases` 不含 restricted 侧 alias_norm（识别可用面口径——列表为空实证）；
- **annotate 面**：含 restricted 别名文本零命中；**不误伤**：正常 l0 实体片段仍在、正常实体 annotate 命中（P1-1b~f 全过）。
- coder 永久用例（`test_p1_1`，双臂）覆盖 core 面+报告+annotate；**REST `/semantic/l0` 端点面由我的探针补验**（coder 用例未直打该端点的 restricted 形态——现已实证）。

### 2. P2-1（方案 B 同锚点+G-21）✅
- **同锚点**：探针实证 `get_annotator` 单例（`a1 is a2`）；**sync→build 窗口 REST 双面**——l0 与 annotate `dict_rev` 逐位一致、annotate 命中 live（窗口新概念可服务）、rev=旧 ready 锚；
- **冷缓存钉死用例核验**（逐句对照 G-21 登记口径）：构建中冷缓存=服务 live+响应旧 rev（`test_p2_1_l0_same_anchor...`）；评测拦下后清缓存=**服务被拦词典+旧 rev**（`test_p2_1_eval_blocked_cold_cache_serves_gated_dict_g21`）——我的探针 REST 面复核同形态（mentions 非空+`dict_rev==current`）；
- **G-21 在库**：known-gaps 总览表行+正文四段（状态=已接受方案 B/问题三面/对冲/收口方向=方案 A M2-S3·m2-5 承接+同批 P3 六项登记+重开条件）与用户裁定逐句一致。

### 3. P2-2（ambiguity 分母稀释）✅
- **独立重算**（自写计算器，歧义 span 判定与实现独立实现——label surface norm ∈ 多实体共享 alias_norm 集才计）：黄金集分母 **20 = 实现 20**（25 标注去 5 伴随）、分子 20、四指标 **1.0/1.0/1.0/0.0** 逐位一致；
- **稀释场景独立构造**（不沿用 coder stub 形态）：20 歧义 span + 5 伴随确定性标注——新口径分母 20 不稀释；**答错 3 → 17/20=0.85 恰卡线**（≥0.85 通过）、**答错 4 → 16/20=0.80 被拦**；**旧口径 22/25=0.88 会放行**（算术实证）——Committer 指证的稀释缺陷修复成立且卡边语义精确；
- **黄金集 README 同步**：分母 20+5 条伴随 qid 明细（s106/s107/s108/s110/s111）落笔。

### 4. P2-3 + 全角 + P3×4 ✅
- **报告七字段**（真实参考词典探针）：keys/nodes/build_ms/**memory_bytes=28472>0**/edges=711/words=128/skipped_restricted 齐；edges≥keys≥words 链成立；
- **全角三条**（coder 永久用例+我 R1/R2 探针历史口径）：ＪＸＤＫ 折叠命中/XJXDKX 词边界不命中/jxdk 小写命中；
- **P3-1**：`_cand_ids` 统一 pop——歧义与非歧义 mention 均无下划线键（探针歧义形态+coder 用例）；
- **P3-2**：裸 JSON → 400（`try request.json() except ValueError → HTTPException 400`，diff 审查+用例 `content="{not-json"` 断言 400）；
- **P3-10**：`_worker_env` 两键映射（探针 7200.0//x/g.jsonl 往返）；
- **P3-11**：`items:1` 拦截（`1 == True` 误放行修复）/`items:true` 放行任意元素/`items:false` 非空不通过·空数组通过——六断言全过。

### 5. docs 批核验 ✅（与裁定逐项一致）
- **TEST-CASES v1.9.8**：六注记全落（TC-BUILD-04 双门同触分离构造+无确认入口+适用面豁免；TC-SEM-03 L0 证据级注记；TC-SEV-01 错别字随 M2-S3+协同基线；TC-SEV-02 歧义分母口径；TC-BUILD-05 移行依据四条；M2-S1 行 TC-PERF-05 → m2s-5/m2-5〔裁定⑬〕）；**§六 M2-S2 行 m2s-4 段完成态+整行 ✅ 收口（05 已移出）**；M2-S3 行 TC-BUILD-05 移入——裁定⑦落实；
- **known-gaps G-21** 在库（见 §2）；G-19 收口行保持；
- **AGENTS.md**：段序自相矛盾修正（m2s-4 进行中、下一段 m2s-5、段序调整注记）——P2-4 落实；
- **_m2-plan**：段序调整注记（m2s-4→m2s-5→m2s-6→m2-4→m2-6→m2-5）+m2-4 顺延+m2s-4 行 ◐ R3+m2s-5 挂账五项（TC-PERF-05/G-21 方案 A/歧义缺省读法显式化/TC-BUILD-05/错别字正样本）。

### 6. 回归 ✅
- 抽核 **30 passed**：消歧④全部候选/最长匹配/负样本零标注、评测黄金集全文件（**P2-2 口径变更后既有用例仍真在测**——新口径更严、断言不变仍有效）、R2 修复三触发面、G-19 五源、R3 全部 16 条（含 pg 臂）；
- 门禁 1323 全量兜底；`automaton.iter` 短路（R2 修复）未触碰；evalrun 改动仅歧义分母段（P/R/neg_fp 路径未动——探针四指标双算一致实证）。

## 三、问题分级

- **IMPL_BUG**：无；
- **SPEC_GAP**：无（TC-BUILD-05 已随裁定⑦移行落 docs——R1 遗留 SPEC_GAP 闭环）；
- **OBSERVATION**：R1 遗留 O4（适用面豁免）/O5（错别字正样本）/O6（分母口径）均已随 v1.9.8 注记落 TEST-CASES 闭环；G-21 同批 P3 六项（缺省读法稳定性/单 bigram 宽松档/l0_extra 未消费/拉丁粘接/alias confidence 交互/无确认入口）已在 known-gaps 显式登记且挂账 m2s-5——登记级闭环，无新增观察。

---
**结论**：testVerdict=**PASS**（testedSha=`8d32750de7225afb822286751fb3e0e2e99bae49`）。P1-1 四面封堵、P2-1 方案 B 同锚点+冷缓存钉死+G-21 登记、P2-2 分母修正独立实证（20 分母/0.85 卡边/0.80 拦/旧口径 0.88 放行）、P2-3 七字段、P3×4 全过；docs 批与 Committed 裁定逐项一致；门禁 1323+1 双模式 0 skipped 对账吻合、零回归零弱化。**修复面已收敛，无新阻断——round=3 收敛，建议 Committer 终审 APPROVED**。

</details>

<details><summary>R3 Committer 终审报告全文（2026-10-31 17:16，reviewVerdict=APPROVED）</summary>

## 终审结论：**APPROVED**（round=3 收敛；无 P1/P2；P3 残留登记放行，附交付归档条件）

- 基线核验：`HEAD=8d32750` ✓，父 `9100bfb` ✓，R3 diff 12 文件 +565/−25 与检查点申报一致；`testedSha=8d32750=HEAD` ✓；检查点只读未动（工作区仅监督侧未提交的 `supervised-coding.md` 与未跟踪检查点）。
- 门禁采信：R3 Tester 实测 `1323+1` / 双模式 0 skipped / pg 459=426+33。我复核测试清单：`test_r3_m2s4_fixes.py` 11 函数 = 5 个 `backend` 双臂（10 条目）+ 6 单臂（6 条目）= **+16 对账成立**；`tests/` 零删除、零 skip/xfail。本审查环境未复跑（延续 R2 口径）。

---

## 一、P1/P2 逐项闭环核验

| 项 | 核验结果 | 说明 |
|---|---|---|
| **P1-1** `render_l0` restricted 过滤 | ✅ **闭合** | `annotator.py:475` 在 curated 判定前跳过 restricted，与我的建议一致；`test_p1_1` 核心面（公开 l0 在、机密 l0 不在、annotate 零命中）双后端成立；REST `/semantic/l0` 面 Tester 探针直打实证。`_build_stats` 额外把 restricted 从 `ambiguous_aliases` 排除（`build.py:136-144`）——**正确**：识别面 restricted 不入机，报告不应暴露其 alias 面；与 evalrun 歧义判定同向。**注意**见 P3-r1（该报告过滤的永久用例是空转）。 |
| **P2-1 方案 B 同锚点 + G-21** | ✅ **闭合（按用户裁定 B）** | `/semantic/l0` 改走 `get_annotator`（`api/semantic.py:306-320`），与 annotate 同实例同 rev；`get_annotator` 文档明确 G-21（`annotator.py:414-430`）。冷缓存钉死用例覆盖构建中（`test_p2_1_l0_same_anchor...`）与评测拦下后（`test_p2_1_eval_blocked_cold_cache...`）两形态；G-21 正文/总览内容与我的裁定逐句一致（含「门禁仅进程生命周期」「方案 A → M2-S3/m2-5」）；`_m2-plan` row 9 已挂方案 A。**注意**见 P3-r3（同锚点用例的 L0 内容断言偏弱）与 P3-r8（无 build 时 L0 返回空为行为变化）。 |
| **P2-2 ambiguity 分母** | ✅ **闭合** | 词典侧「多实体共享 alias_norm + exact/context + 非 restricted」判定（`evalrun.py:101-111`），只对 label surface 命中共享集才计分子分母（`:134-138`），与我 R2 首选建议一致。参考集 25→20、四指标 1.0/1.0/1.0/0.0 成立；Tester 独立重算 20 分母 + 0.85 卡边 / 0.80 拦 / 旧口径 22/25=0.88 放行；既有 `test_tc_sev_02_metrics...` 在新口径下仍真在测（分母更严、断言不变）。**分子侧的 `ambiguous=true` 命中口径**见 P3-r5（参考集严格口径 18/20=0.90 仍过门，不阻断）。 |
| **P2-3 内存指标** | ✅ **闭合** | `annotator.py:388-400` 透传 `total_size/links_count/words_count`；R3 `test_p2_3` 七字段 + `edges≥keys` + `memory_bytes>0`；Tester 真实参考词典实测 `memory_bytes=28472`。 |
| **P2-4 docs 段序** | ✅ **闭合** | `AGENTS.md:10` 改为「m2s-4 进行中、下一段 m2s-5、段序调整注记」；`_m2-plan` 增段序调整注记、row 7 m2-4 顺延、row 8 ◐、row 9 下一段 m2s-5+挂账五项。 |
| **P2-5=⑦ TC-BUILD-05** | ✅ **闭合** | `docs/TEST-CASES.md`：§4.4 标题改「M2-S3」（含移行四依据）；M2-S2 行移除 05 并注「整行收口」；M2-S3 行加入「TC-BUILD-05（依赖 semantic_retag 消费面）」。裁定落地。 |

**P3 顺手 4 项**：
- P3-2（裸 JSON→400）：`api/semantic.py:269-275` + `test_p3_2` 真实（修复前 500 形态钉死）✅。
- P3-10（`_worker_env` 两键）：`worker/runner.py:463-466` + `test_p3_10` 往返断言 ✅。
- P3-11（`items is True/False`）：`yaml_corpus.py:362-370`/`:462-475` + `test_p3_11` 六断言（`items:1` 拦、true 放行、false 非空拦/空数组过）✅。
- P3-1（`_cand_ids` pop）：`annotator.py:192-199` 代码正确；**但 `test_p3_1` 用的是歧义 mention**（旧代码对歧义 mention 本来就 pop），用例未真正覆盖非歧义分支——见 P3-r2（测试质量，非代码缺陷）。
- P3-6 全角永久用例：`test_fullwidth_and_case_boundary_permanent`（ＪＸＤＫ/XJXDKX/JXDK/jxdk 四断言）✅，补齐 R2 覆盖缺口④。

**其余 R2 P3 登记核对**：G-21 的「同批登记（P3 级）」六项（无确认入口/缺省读法/单 bigram/l0_extra/拉丁粘接/alias confidence）已落；TC-PERF-05 已落 TEST-CASES M2-S1 行 + `_m2-plan` m2s-5 挂账（⑬）。**但 P3-3（precision 分母排除 neg 预测）、P3-5（mixed-mode context 候选级门槛）、P3-7（double_build 名实）、P3-9（maintenance 四项）、P3-16（重复 import/annotate 仅捕 ValueError）未见登记**——见 P3-r9，归档时补登记即可，不阻断。

---

## 二、新引入面审查（R3 diff）

- **`render_l0` 对正常 l0 的影响**：无副作用——正常条目仍按原序渲染；`test_sem_04_api.test_l0_export_fragments_with_dict_rev` 在 R3 后仍过；`test_p1_1` 断言「公开模板」在、「机密」不在。restricted 过滤只减少条目，不影响 token 估算逻辑。
- **`/semantic/l0` 改单例后的行为面**：正常有 build 时 `dict_rev`/片段与 annotate 同实例同锚（Tester REST 探针双面 rev 逐位一致）；构建中/拦下后冷缓存按 G-21 钉死；**无 build 时返回空片段 + `token_estimate:0`**（原实现返回 live 片段）——与 annotate「无 build 不服务」一致，属合理收敛，建议 TC-SEM-06 注一句（P3-r8）。
- **`evalrun` 歧义段**：P/R/neg_fp 路径未动（Tester 四指标双算一致）；新分母对参考集 20 成立；无新崩溃路径（`snapshot["aliases"]` 全在场、`normalize_alias` 对空/标点安全）。**分子把 `ambiguous=true` 的主候选命中计为正确**是既有语义，不是 R3 引入；参考集严格口径仍 0.90≥0.85（P3-r5）。
- **`_build_stats` 报告过滤**：只滤 restricted、未滤 fuzzy_only，而注释称「识别可用面」——口径注释与实现略有出入（fuzzy_only 歧义对 M2-S3 模糊层仍有报告价值）；非功能缺陷（P3-r6）。
- **其余源文件**：`yaml_corpus` items 布尔修复正确；`worker/runner` 两键映射正确；`api/semantic` JSON 400 正确。无新 P1/P2。

---

## 三、P3 残留（登记放行，不突破轮上限）

> 以下均为 P3（代码修复本身正确；多为测试强度/口径登记/归档元数据），按 m2-3 R3 先例登记放行；建议随交付归档 docs-only 批补一条 G-21/`_m2-plan`「R3 终审 P3 登记」即可。

- **r1（测试质量）** `tests/test_r3_m2s4_fixes.py:120-125`：P1-1 报告面断言空转——fixture 中「共享面」只挂 TPL_SECRET，未与正常实体构成跨实体共享 alias，`ambiguous_aliases` 本就不会含它；旧代码也会通过。建议补一个正常实体同 alias（或真实歧义 norm）再断言。
- **r2（测试质量）** `tests/test_r3_m2s4_fixes.py:365-376`：P3-1 用例的 mention 是 **ambiguous**（「甲」双候选），旧代码对歧义 mention 已 pop；未覆盖「非歧义仍带 `_cand_ids`」的修复分支。建议改单候选/已消歧文本。
- **r3（测试质量）** `tests/test_r3_m2s4_fixes.py:159-161`：`l0["fragments"] or token_estimate >= 0` 恒真；未真正断言 L0 同锚点内容。建议造一条 curated l0，断言片段来自 `ann_a.snapshot` 且与端点返回一致（REST 面 Tester 探针已补，永久用例可更实）。
- **r4（注释口径）** `tests/test_r3_m2s4_fixes.py:248-280`：stub 旧口径写成 22/25，实际该 stub 旧分母 23（20 甲+3 乙）；黄金集才是 25。注释口径不一致，非断言失败。
- **r5（指标语义）** `evalrun.py:124-138`：ambiguity 分子把 `ambiguous=true` 的主候选命中计为「正确」——参考集严格口径 18/20=0.90 仍过 0.85，不改变本段门槛结论；建议 M2-S3 收紧分子并同步 `test_p2_2_golden`（当前断言 1.0 依赖该口径）。
- **r6（口径注释）** `build.py:136-146`：`ambiguous_aliases` 只滤 restricted、未滤 fuzzy_only，注释称「识别可用面」；建议对齐注释或同时滤 fuzzy_only（报告面非门槛）。
- **r7（文档）** `semantic_golden.README.md`：两缺省读法（s109/s117 类）未按 qid 列出（边界⑤建议）；错别字正样本 M2-S3 注记已在 TEST-CASES，README 可选。
- **r8（文档）** `api/semantic.py:306-320`：无 build 时 `/semantic/l0` 由「live 片段」改为「空片段」——建议 TC-SEM-06 注一句「L0 为构建产物，无 build 返回空」。
- **r9（登记缺口）** R2 P3 未入 G-21/挂账：P3-3 precision 分母排除 neg 预测（`evalrun.py:119-124` docstring 口径）；P3-5 mixed-mode context 候选级门槛（`annotator.py:224-225`）；P3-7 `double_build` 名实（`tests/test_sem_eval_golden.py:137-150`）；P3-9 maintenance 四项（docstring/非法窗口日志噪音/daily 触发审计/pending payload 与 `force` 精确匹配）；P3-16 `_audit_build` 重复 import / annotate 仅捕 ValueError。
- **r10（归档元数据）** 检查点 `filesChanged` 未列 R3 12 文件（R3 记录段落有描述，字段陈旧）；AGENTS/`_m2-plan` row 8 仍「进行中/◐ R3 修复中」——归档 commit 更新为 ✅/下一段 m2s-5。

**不构成 P1/P2 的判定理由**：P1/P2 的代码修复均已落地且有真实回归证据（P1-1 核心面双后端、P2-1 冷缓存双形态、P2-2 独立计算器+卡边算术、P2-3 实测）；上述多为测试强度、口径注释、归档登记项。

---

## 四、需求边界与裁定落实

- ⑦ TC-BUILD-05 移 M2-S3：**已落实**（TEST-CASES 行移动+四依据+整行收口）——M2-S2 行现可宣称整行 ✅。
- ② L0 四级证据级、③ eval_blocked 无确认入口、④ 适用面豁免、⑤ 缺省读法、⑥ 双门同触示例、⑬ TC-PERF-05、⑫ 错别字正样本：**均已在 TEST-CASES v1.9.8/G-21/`_m2-plan` 注记**（逐句核对一致）。
- ⑧ T-S4/T-S12 括注：验收按编号（T-S4=m2s-3 宽限状态机、T-S12=本段原子切换）；docs 注记已随 v1.9.8 落笔（历史任务书原文未改，属冻结文档纪律）。
- ⑨ G-19 收口、⑩ lock 干净：维持通过。
- ⑪ 大小写折叠/「全量可用面」、⑭ 段序：按 design/裁定落实，无新歧义。

---

## 五、三面评价（交付留痕用）

- **Coder（R3）**：修复面小而准，P1/P2 全部按裁定闭环、无回归；有两处新用例断言弱于其 docstring 覆盖意图（报告过滤/P3-1），且 5 项 R2 P3 未登记——但代码正确、不影响验收。
- **Tester（R3）**：独立探针 32 断言覆盖 REST 端点、稀释算术与冷缓存形态，证据链扎实；未识别 coder 两处空转用例与 P3 登记缺口，建议归档时一并登记。
- **监督侧（docs 批）**：v1.9.8/G-21/AGENTS/`_m2-plan`/TC-BUILD-05 移行/TC-PERF-05 归属与我的裁定逐项一致，仅剩归档终态与 P3 补登记。

---

## 六、交付归档清单建议（APPROVED 后）

1. **reviewedSha 建议：等 docs-only 归档 HEAD（沿 m2s-3 先例）**——`testedSha` 保持 **8d32750**，`reviewedSha` 设为监督侧 docs-only 归档 commit（检查点终态 + AGENTS/`_m2-plan` 状态 + P3 补登记；若监督侧不另做 docs-only commit，则 reviewedSha=8d32750，但检查点尚未入库，仍需归档 commit）。
2. 检查点终态：`status=done`、`round=3`、`testVerdict=PASS`、`reviewVerdict=APPROVED`、`testedSha=8d32750`、`reviewedSha=<归档 HEAD>`、`filesChanged` 增补 R3 12 文件、`updatedAt`/`endReason` 按规范。
3. docs-only 归档补丁：G-21 或 `_m2-plan` m2s-5 挂账补登 §三 r5/r6/r9（其余 P3 已登记）；AGENTS 改 m2s-4 ✅/语义 4/6/下一段 m2s-5；`_m2-plan` row 8 ✅、row 9 current；TEST-CASES v1.9.8/G-21 已在 R3，无需重写。
4. PR（base=develop）+ evidence manifest：双 SHA（testedSha=8d32750 / reviewedSha=归档 HEAD）、门禁 1323+1（pg 459=426+33）、rounds=3、specRulings（①~⑭ + R2 P1/P2 + 用户方案 B）、gapClosures（G-19/G-21/TC-BUILD-05/TC-PERF-05/O4·O5·O6/P3 登记）、handover（m2s-5：G-21 方案 A、缺省读法显式化、TC-BUILD-05、错别字正样本、TC-PERF-05、P3 残留）。manifest 必须完整且双 SHA 与最终 HEAD 一致，否则不放行。
5. 用户确认交付后：我执行 `gh pr review` 落 APPROVED 留痕（不 merge）；合入动作归用户，committer 不经手。

**CASE_BUG 裁定请求：无**（本轮无 tester 提交的用例预期争议；R1 IMPL_BUG 已在 R2 关闭）。

**reviewVerdict: APPROVED**（round=3 收敛；无 P1/P2；§三 P3 随归档登记放行）。

</details>
