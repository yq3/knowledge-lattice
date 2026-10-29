---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m1-5
target: knowledge-lattice
coderTaskId: ses_e879ab06affeKF4rNHxMILEyek
testerTaskId: ses_e85866e97ffey1hdv5pqmrnTrB
committerTaskId: ses_e857b9a99ffeS7GpQFGKFmuQzh
status: done
round: 3
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: c8097254074e4e5bd528224675eeedb6fc327809
reviewedSha: b3df888
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: []
endReason: null
createdAt: 2026-10-25T20:39:56+0800
updatedAt: 2026-10-28T09:37:01+0800
---

# task-knowledge-lattice-m1-5: M1-5 性能/校准实验 + 越权矩阵全量收口 + M1 验收对照总勾验（M1 验收收官段）

## 任务原文

**需求**（design.md §8 M1.6 性能部分 + M1.7 验收，v0.9.4；与 requirements §8 M1 行对齐；前置 M1-4 开发收尾段完成——黄金集与批量语料就位是本段实验的输入。**段性质：实验报告段（M0b-2 形态）+ 收口验证——产出以 benchmark 报告/校准记录/勾验记录为主，新功能代码最少**）：

**A. 性能基线（SLO 标定）**（自 M0b 取消顺延——TEST-CASES v1.5.2 口径）：

1. **TC-PERF-03 SLO 标定**（NFR-8 正式基线：P95 ≤ 2s 分项标定——检索全配方、1/5 万两档；前置：M1-4 的耗时日志四段对齐已就位）
2. **TC-PERF-04**（配套性能抽测）
3. **G-6 halfvec/表达式索引评估**（2560 维 `<=>` 精确扫描 vs halfvec 表达式索引——TC-PERF 对比，10 万块 P95；known-gaps G-6 收窄③）

**B. G-8/G-6 校准实验**（known-gaps 移交，产出校准记录归档 benchmarks/）：

1. **G-8 MRL 截断质量对比**：2560 vs 1024 截断 recall@10/MRR（用 M1-4 黄金集；**损失 ≤1pp 则允许截断为可选配置**——G-8 收窄①）
2. **G-8 指纹阈值校准**：0.99/0.95 两档临时值用网关正常版本抖动数据校准（G-8 收窄②）
3. **G-6 双后端黄金集校准基线**：同一黄金集双后端 recall@10/MRR 偏差记录（排序断言按名次集等价——A-17）。**决策路径（用户 2026-10-26 拍板 B-3 改写——M1-4 实测偏差 10.7pp>2pp 已触发 G-6 收窄②钩子；原「ts_rank_cd 加权重调」不能解 AND 零召回问题）**：①先接真实嵌入模型重测双后端基线（TokenBag 代理对跨语言 query 系统性低估——q19/q20/q21 类缺口需真实模型泛化验证）；②停用词滤除评估（仅救 q01/q10 约 +7.1pp）；③OR 口径变更走**决策变更流程**（§5.2 钉死口径，不由校准实验顺手改）；④ts_rank_cd 仅作排序对照。校准结论回写 known-gaps G-6
4. **蓝绿共存窗口 PG 读代价复测**（M0b-2 移交，定性申报进报告）

**C. 越权矩阵全量收口**（design §8 M1.7——TEST-CASES §六 M1 行）：

1. **越权矩阵全绿**：T1~T23 全量 + TC-AZ-01/02/03/05（**双后端各跑限定 DB/服务/MCP 层**——用户 2026-10-26 拍板 B-1①：业务逻辑双后端实跑已充分，REST-PG 留 M2 写入验收对照残项〔P3-18 顺延口径〕；T13 以 dev 白名单模拟；**T19 删库半句、T20 退役审计半句随 M2 收口**——v0.6.1 限定 #38 P1-4/#39；「全量」措辞冲突见附录 A-8）
2. **TC-E2E-05 全量矩阵复跑收口**

**D. UI 走查与 M1 验收对照总勾验**：

1. **TC-UI 双语走查**：TC-UI-01 复验 + TC-UI-02（检索页）/ 03 / 04（FR-8——手动走查，不进 CI，走查记录归档）
2. **区分度误报抽查**（M1.7 验收句——基于 M1-4 区分度环产出）
3. **M1 验收对照表逐条勾验**（TEST-CASES §六 M1 行全组逐条——本段完成即 **M1 里程碑整体达成**；§六 M1 行更新完成态、A-8「全量」措辞核销核对）

**口径与边界**：

- 校准实验的**判据落笔**（MRL 截断是否开放为配置、指纹阈值数值、双后端偏差结论）经 supervised-coding 确认后由 supervised-coding 回写 known-gaps/TEST-CASES（coder 禁改 docs）；实验产出报告归 benchmarks/。
- **T19/T20 半句随 M2**；响应层指标与 judge/deepeval 属 M3；管理面属 M2。
- 手动走查（TC-UI）由用户/监督方执行，coder 提供走查清单。
- 设计冻结纪律：docs/ 的回写由 supervised-coding 落笔；实验代码与脚本照常 commit。
- commit 格式 `[task-knowledge-lattice-m1-5] R<n>`，develop_opencode 分支，commit 前同步 origin/develop，不 push。

**流程纪律（M1 系列延续，用户 2026-10-25 拍板）**：

- **跨检查点会话隔离**：本检查点对应全新 Coder/Tester/Committer 会话；检查点内多轮续接复用各自会话。
- **执行模式 A 串行紧衔接**：M1-5 完成合入即 **M1 里程碑整体达成**，下一段进入 M2（与 M2-S1 语义轨道并行——D23）。

**承接遗留事项**（本段承接项；**前置：M1-4 的黄金集/耗时四段日志/批量语料就位是本段输入**）：

- [ ] TC-PERF-03/04（自 M0b 取消顺延——TEST-CASES v1.5.2；**前置：M1-4 P2-4 100k 档批量重算内存/PG 参数上限改造**——100k×2560 物化 float 对象 >1GB、delete_open_flags 65535 参数上限约 6.5 万候选失败，M1-4 committer 裁定 M1-5 TC-PERF-03 前必须解决：packed bytes/流式/缩小 block/分批）
- [ ] **MCP list_documents 工具实装**（design §6.1 docs 组；T17/TC-AZ-02 执行主体）：input datasets/active_status/limit，output datasets（按调用者 ACL 统计 doc_count）+ documents（四字段 + dims + chunk_count + source + updated_at）；统计复用 visible_docs/_attach_dims；与 TC-AZ-03 管理列表"两个端点两个口径"；同步修正 mcp/server.py「随 M1-4」注释；来源 M1-4 边界②（Tester 查证依赖缺口）
- [ ] **P3-11（m1-1 R2 顺延）：PG to_tsquery 负向用例**——畸形参数（引号 / : / * / 括号 / &）与语法错误降级（400/空召回而非 500）双后端对照；来源 task-knowledge-lattice-m1-1 P3-11（M1-4 承接清单漏登，本段补登）
- [ ] **G-6 决策路径执行**（B-3 拍板）：真实嵌入模型重测双后端基线 → 停用词滤除评估 → OR 口径变更走决策流程（见 B 组 3）
- [ ] **耗时 fuse 段双计修正**（m1-4 顺延：fuse 含增强 800ms 等待双计——**开增强路/NFR-8 分解前必须修**，m1-4 顺延补登）
- [ ] **LLM 钩子时间预算评估**（m1-4 顺延：每 flag provider 超时 10s，大文档 flags 多时 quality 阶段占用——开 quality_llm provider 前评估，m1-4 顺延补登）
- [ ] **M1-4 docs 批（supervised-coding 落笔）**：§7 依赖表补 numpy、§3 quality 报告/PATCH 归 api/quality.py、详情端点 quality_flags 概要与 GET sample 登记、requirements 风险表「分位下限」口径统一（B-2）、q27 lang 修正+补 mix query（黄金集修订——counts["mix"]>=8 断言同步）
- [ ] G-8 MRL 截断对比（known-gaps G-8 收窄①）
- [ ] G-8 指纹阈值校准（known-gaps G-8 收窄②）
- [ ] G-6 双后端校准基线 + >2pp 评估（known-gaps G-6）
- [ ] G-6 halfvec/表达式索引评估（known-gaps G-6 收窄③）
- [ ] 蓝绿共存窗口 PG 读代价复测（M0b-2 移交）
- [ ] 越权矩阵全量收口 T1~T23 + TC-AZ（**双后端限定 DB/服务/MCP 层——REST-PG 留 M2 残项**，B-1①；T19/T20 半句随 M2）
- [ ] TC-E2E-05 收口
- [ ] TC-UI-01~04 走查
- [ ] 误报抽查
- [ ] §六 M1 行完成态 + A-8 核销

**验收标准**：

- TC-PERF-03/04 产出 SLO 标定数据（NFR-8 分项）
- 校准记录归档（MRL 对比数据 + 阈值实测值 + 双后端基线 + halfvec 对比 + 蓝绿复测）
- 越权矩阵全绿（T1~T23 + TC-AZ 双后端〔限定 DB/服务/MCP 层〕；T19/T20 限定项除外）
- TC-UI 走查记录归档
- §六 M1 行逐条勾验完成 → **M1 里程碑达成**

## 需求确认

- [x] 用户已确认（2026-10-26 21:23「同意」——M1-4 已合入 PR #53 前置满足；status=implementing）
- 历史遗留事项清单：本段承接 M1-4 移交的校准/矩阵/性能组 11 条（M1-4 检查点拆分时移出）；knowledge-lattice 各检查点移交项除 M2 去向与 M1-4 承接外均已归位

## 遗留事项（跨任务移交）

- [ ] 无（本段新增移交项随轮次记录登记；M1 收官后残留归 M2/M3 去向：并发真用例与租约〔✅ 已清偿：来源 task-knowledge-lattice-m2-1，PR #2 2026-10-29 合入——claim 原子/租约重认领/杀进程演练全链〕、凭证吊销语义〔→m2-3〕、RFC 8693 act 对象形态〔→m2-4〕、grants 写路径〔→m2-3〕、P3-4 title/dataset〔→m2-3〕、管理面全端点〔→m2-3〕、响应层指标与 judge→M3）

## 轮次记录

- **R1 进行中（2026-10-26）**：coderTaskId=ses_e879ab06affeKF4rNHxMILEyek（21:27 启动，53 分钟后调用方 abort——opencodedb 恢复续接）。断点前成果：开发项已 commit `992a0e2`（fuse 双计修正 + 100k 批量重算改造 + MCP list_documents 实装 + P3-11 畸形参数降级，门禁 604→661 全绿）；bench1~6 产出落盘 data/bench-results/（SLO 四组合 PASS + TC-PERF-04）；断在 bench7（G-6 halfvec 10 万块）中途。
- **用户裁定（2026-10-26 22:3x）**：bench7 G-6 halfvec 10 万块评估**本段跳过**（非 M1 验收硬门槛——TC-PERF-03/04 才是；G-6 收窄③顺延，跑不动的定性现象本身已可作输入记录）。coder 跳过 bench7 直接收尾：整理 bench1~6 报告 + 验证证据 + TC-UI 清单 + M1 勾验材料 + R1 commit。halfvec 评估去向：known-gaps G-6 回写时由 supervised-coding 注明顺延（判据落笔留 supervised-coding）。
- **R1 coder 返回（2026-10-26 22:5x，续接恢复后）**：commit `992a0e2`（开发批：fuse 双计修正+100k 重算改造+list_documents 实装+P3-11，门禁 604→661）+ `b9db4c0`（实验收尾批：quality.py 双流重构+bench1~6 脚本与报告+LLM 钩子评估+TC-UI 清单+M1 勾验材料，10 files +1435/−67）；门禁 GATE PASS 661+1 双后端双模式 0 skipped（pg 臂 225）；TC-PERF-03 四组合全 PASS（P95 最差 633ms ≤2000ms）；G-6 黄金集偏差 r@10 −10.72pp 逐 query 归档。**但顺延申报 5 项中 3 项不可接受**：G-8 MRL/指纹阈值（可本地做或出受阻申报材料）、蓝绿复测（PG 在本地必做）、**D 组越权矩阵 T1~T23+TC-AZ+TC-E2E-05 完全未做（M1 验收硬门槛）**——打回补齐（仍属 R1 范围，不加轮次）；B-3① 真实模型环境受阻属实→改为受阻申报材料（选型+接入点+验证步骤）。
- **R1 补齐返回（2026-10-27 07:08 落档——补齐跑于 26 日深夜至 27 日晨）**：commit `74892e7`（9 files：calib_m1_5.py 五子实验脚本 + 矩阵/五份实验报告新增 + 主报告勾验材料同步）。**矩阵 346/346 全绿**（双后端 28 文件：pg 113+sqlite 113+REST/MCP/shell 120，B-1① 口径，T19/T20 半句 M2 申报）；TC-E2E-05 收口（test_v11_schema 21 用例双后端）；门禁复跑 GATE PASS 661+1（pg 臂 225）。关键数据：停用词 PG r@10 0.7857→0.8571（+7.14pp 假设精确命中，sqlite 零变化）；ts_rank_cd 0.00pp（印证不能解 AND 零召回）；MRL 截断 r@10 0.00pp/MRR −1.63~−2.38pp（TokenBag 非 MRL 训练口径申报）；指纹阈值 min cosine=1.0/fp16 噪声底 1.0（真实网关抖动受阻申报）；蓝绿共存 +5.9% P95（缓存受控对照）；真实模型受阻申报材料（qwen3-embedding-0.6b 首选）。**R1 三 commit：992a0e2→b9db4c0→74892e7，待 Tester。**
- **Tester R1（2026-10-27，ses_e85866e97ffey1hdv5pqmrnTrB）：PASS**。独立复验：门禁 661+1 双模式 0 skipped（pg 臂 225，对账 604+57 恰合）；矩阵 28 文件全量独立复跑 346/346（T13/T17/TC-AZ-02/畸形参数留痕，T19/T20 半句确未跑属实）；新用例真实断言审查（畸形 44 条断 200/400+空召回非恒真；list_documents 验 ACL 统计不泄露 d_os）；数据一致性逐 JSON 对账全合（SLO 417/633/429/582ms、停用词 +7.14pp、蓝绿 +5.89%、MRL 0.00pp、G-6 10.72pp、重算 673MB/74.5s）；fuse 双计修正 diff+测试双实证；TC-UI 清单可操作（/api/dev/token 实存）；零回归零弱化。次要发现 2 处文档笔误（report §4 「3.0s vs 3.3s」「80KB vs 111.9KB」——非验收关键数字，转 coder 顺手勘误）。testedSha=74892e7ebe653df052309bac7666ddc759663324。意见原文存 Tester 会话末条报告。
- **Committer R1（2026-10-27，ses_e857b9a99ffeS7GpQFGKFmuQzh）：NEEDS_CHANGES**。审查基线 HEAD(74892e7) vs befff9e（27 files +3053/−95）；docs/ 零触碰核实✓；无 skip 弱化✓；代码侧 P3-11 生产层修复✓/fuse 修正✓/双流等价✓/list_documents CTE 同构✓。**P1-1（阻断）**：bench5_slo_perf03.py embedder 输入约定 `q:行号` 但传中文原句→每请求 IndexError 被吞→全部样本实为 FTS 单路降级态，TC-PERF-03「全配方分项标定」未交付（建议显式映射+notice 断言 fail-fast+重跑）。**P2×6**：P2-1 N=5 表 rps 与延迟算术矛盾；P2-2 分段统计混入预热样本；P2-3 active_status 枚举与 DDL 不一致（缺 degraded/误含 failed）；P2-4 list_documents 未映射 AclDeniedError→403；P2-5 bench4 全量候选档不可复现+头注外推不一致+内存口径混用；P2-6 T17 证据错配（见边界 A）。**P3×7**：quality.py 假防御/第二份矩阵峰值/Tester 2 笔误/阈值边界文字/wall P50 取整/12 vs 21 表述/bench4 口径注。**需求边界 A~D**：A T17 list_documents 半句载体裁定（①补 owner-union 升级 P1 代码项 or ②详情端点为载体改证据指针）；B 误报抽查记录（接受申报顺延 or 补合成语料抽样记录）；C M1-4 docs 批欠账 2 处（design §7 numpy+§3 归 api/quality.py——supervised-coding 落笔）；D enh_wait 四段口径登记（supervised-coding 落笔）。顺延合规核对无越界；17 项承接核对：TC-PERF-03 ⚠/list_documents ⚠/docs 批 ◐/误报抽查 ◐/§六归 supervised-coding，余 ✓。**status 回 spec_confirm 待边界裁定；裁定后 round→2 发 coder R2（P1-1+P2×6+P3×7 一批）。意见原文存 Committer 会话末条报告。**
- **边界裁定（2026-10-27 19:40 用户「按建议的来」）**：**A=②** 详情端点（org 域）为 T17「可见自己文档元数据」半句的载体——list_documents 保持纯 ACL 视角（与 TC-AZ-02/「两个端点两个口径」一致），T17 证据指针改详情端点测试、TEST-CASES T17 正文半句回写载体（supervised-coding）；**B=②** 补合成语料抽样人工复核记录（coder R2 顺手，归 benchmarks/）；**C/D** supervised-coding docs 批落笔（design §7 numpy + §3 归 api/quality.py + enh_wait 口径登记）。**round→2、status=implementing，coder R2 范围：P1-1+P2-1~6+P3-1~7+Tester 2 笔误+B② 抽样记录+T17 指针修正。**
- **R2 coder 返回（2026-10-27）**：commit `13450ea`（docs 批——supervised-coding 落笔的 design v0.9.5 + TEST-CASES v1.7 原样 commit）+ `0d1cee9`（修复批 11 files：mcp/server.py P2-3/4、quality.py P3-1/2、test_m1_5_dev.py +2 用例、bench4/5 重跑与口径、报告修订×4、B② fp-review 新增）。门禁 **663+1** 双后端双模式 0 skipped（pg 臂 225）；矩阵 **348**（346+2）。P1-1 修复实证：embedder 显式 dict 映射 fail-fast + 每请求 notice 断言入库；**真值暴露 pg-5万 N=5 并发 P95 3437.5ms > 2000ms SLO FAIL（如实申报——单请求 836ms 达标；5 路并发 <=> 精确扫描 3.8GB 容器线性劣化 mean≈5×单路；归因与 bench7 halfvec 顺延关联写入报告 §2）**；双路召回预算项两后端单请求档均超 300ms（R1 假值作废）。B② 抽样结论：词面路误报 11~12/12（同域小语料 IDF 稀释）、拥挤路零误报、漏报不可评申报。T17 缺口如实注记（owner 撤销后详情 200 无专属断言——M2 管理面补）。待 Tester R2。
- **Tester R2（2026-10-27，ses_e85866e97ffey1hdv5pqmrnTrB）：PASS**。门禁 663+1 双模式 0 skipped（pg 臂 225）；矩阵 348（+2 新用例留痕）；P1-1 三项核（fail-fast 代码属实三处生效/embed 列真值 160.5~160.9ms/notice_assert 在库）；**pg-5万 N=5 FAIL 独立复跑 2 次（3599.0/4116.5ms）确认稳定真值非偶发——申报准确（单请求三点 ≤2s 稳定达标）**；P2-3/4 product diff 恰两处语义变化、断言真实；quality.py 两遍同口径+原地除 diff 核对；docs 批 13450ea 原样性核实（2 files 无私改）；报告数字逐值对账全合。testedSha=0d1cee9596ce17efa0aad058e99031719b5297c1。次要观察：跑间方差 ~20%（不改变结论）。意见原文存 Tester 会话。
- **Committer R3 终审（2026-10-27，ses_e857b9a99ffeS7GpQFGKFmuQzh）：APPROVED**（maxRounds 收敛）。R2 清单终态全闭环（P1-1 池化真值/P1-2 矛盾消除/P2×3/P3×6；P3-7 两遍流边界接受为 M2 hardening）；**裁定②执行忠实度七项全核**（基线出数口径/超标准登记/NFR-8 不动/M2 衔接/预算缺口/10 万申报/判据权限）；边界无新增。交付前置（docs-only 不计轮次）：①known-gaps 工作区落笔提交 ②Tester 次要发现①勘误批（预算表 pg 列 R2→R3 值+轮次标注，3437.5 系已作废值引用属内部矛盾——建议采纳）③supervised-coding 已修 P3-5（known-gaps TC-PERF-03 口径句）/P3-6（requirements 版本记 R2→R3）。17 项终态：16 ✅ + 17 ◐（§六 落笔归 supervised-coding，材料就绪）。意见原文存 Committer 会话。
- **docs-only 勘误批（2026-10-27，交付前置清偿——不计轮次）**：commit `b3df888`（A1 预算表 pg 列 R3 真值+轮次标注〔3437.5 作废值引用矛盾消除〕/A2 方差带 ±30~50%/B bench5 docstring 池化口径/C 观测带来源如实化/D supervised-coding docs 落笔提交〔known-gaps G-6 v1.2+G-8 校准+requirements v0.9.5〕）；门禁 663+1 复跑零影响；工作区 knowledge-lattice/ 全净。**最终 HEAD=b3df888（代码 SHA c809725 Tester 结论有效 + docs 批 b3df888）。**
- **收敛确认（2026-10-27 21:5x）**：testVerdict=PASS（R3）+ reviewVerdict=APPROVED（R3 终审）+ 交付前置清偿 → **status=approved，待用户确认交付**（push/PR/gh pr review 留痕序列）。§六 M1 行完成态落笔与 TC-UI 手动走查归交付后用户环节。
- **交付完成（2026-10-27 22:0x 用户「同意」）**：①Coder 同步（Already up to date）+ push `649d832..b3df888`（SSH）+ **PR #54** 开立（base=develop，MERGEABLE/CLEAN，8 commits 逐一对应，34 唯一文件无流程文件混入），description 含 evidence manifest（testedSha=c809725 代码级 / reviewedSha=b3df888=交付 HEAD / GATE 663+1 / 矩阵 348 / boundaryNote 全裁定 / carriedOver M2 组）；②Committer 正式评审留痕 review id `PRR_kwDOTsiHgs8AAAABUdpP-w`（COMMENTED @2026-10-27T13:58:11Z，首行 APPROVED——含一条非阻塞小注：known-gaps v1.2 ±25% vs 主报告 ±30~50% 轮次口径，下次 docs 批统一）。**待用户合入 PR #54；合入后 supervised-coding 落 §六 M1 行完成态 + 用户执行 TC-UI 手动走查（清单 benchmarks/report-m1-5-tc-ui-walkthrough.md）→ M1 里程碑正式达成。**
- **合入完成（2026-10-28 09:36 用户指令"合入"）**：PR #54 state=MERGED，mergedAt=2026-10-28T01:35:36Z，mergeCommit=`87347c309affbddd241bcfc20097f2d6b8dc41bc`；origin/develop 前进 `befff9e..87347c3`（8 commits 全量入库）。**M1-5 正式完成（done）。**收尾两步：①supervised-coding 落 §六 M1 行完成态（勾验材料 benchmarks/report-m1-5-m1-checklist.md 为据）②用户执行 TC-UI-01~04 手动走查——完成后 **M1 里程碑整体达成**；下一段 M2（含 halfvec 索引化复测等移交项，检查点另建）。
- **§六 M1 行完成态落笔（2026-10-28 09:40，supervised-coding 执笔——工作区，随下次 docs 批或检查点归档入库）**：TEST-CASES v1.8——M1 行标 ✅ 已完成（五段 PR + 逐组证据指针：矩阵 348/348 B-1① 注记/TC-PERF-03 裁定②口径/G-6 校准/TC-EVAL-06 ◐/TC-UI ◐ 待走查）+ 版本头 v1.8。**M1 里程碑达成宣告待 TC-UI-01~04 手动走查完成（用户执行）。**
- **Committer R2（2026-10-27，ses_e857b9a99ffeS7GpQFGKFmuQzh）：NEEDS_CHANGES**。R1 清单大多闭环（P1-1 修法核过/P2-2~5/P3 多数/B②/docs 批 C+D 落笔准确）。**P1-1（新·阻塞）**：bench5 PG 并发臂复用单例连接（sqlite 臂却 ThreadLocalBackend 每线程一连接）——psycopg3 连接锁把 5 线程客户端串行化，「PG 5万 N=5 FAIL 3437.5ms」至少部分是测量口径产物（mean 2418≈串行排队形态；「≈5×单路」表述不成立）——须池化/每线程连接重跑才能作为 NFR-8 证据。**P1-2（阻塞）**：勾验材料 L70 仍写「N=5 全部 PASS」+ R1 旧值（663/348/684MB/87.68s 未同步）与主报告 FAIL 直接矛盾——若据此落笔会把未达标写成达成。P2-1 勾验材料 T17 指针未同步 v1.7；P2-2 FAIL 归因夹带未证判断（「生产规格更高」「非验收判」越界）；P2-3 346/661 陈旧三处；P3×7（含 P3-5 requirements 版本未联动 v0.9.5——supervised-coding 落笔）。**边界 A（用户裁定）**：NFR-8 原文=「N=5 并发、~10 万块」；M1 段交付物=「P95 基线」（design §8 M1.6/requirements §8 M1）——M1 完成=基线出数 vs NFR-8 达标须用户裁定；10 万档未测属 2026-10-24 缩档裁定不应悄悄改写。Committer 建议：R3 先池化重跑（真/假 FAIL 分明）→ 若仍 FAIL 走选项②（不改 NFR-8 文本、known-gaps 登记「5万 N=5 超标+10万未测」绑 G-6、M2 halfvec 复测、§六 落「基线已出+未达标已登记」需用户确认）；双路召回 440/406>300ms 预算缺口独立于并发、必须一并登记。17 项终态：2/3/5/6/8/9/10/12/14/15/16 ✅、13 ✅（勾验材料待同步）、11 ⏸ 合规、1/7/17 ◐。意见原文存 Committer 会话。
- **边界 A 裁定（2026-10-27 20:40 用户「按建议的来」= 选项② Committer 推荐）**：M1 完成 = **P95 基线出数**（非 NFR-8 并发达标）；池化重跑后若仍真 FAIL → 不改 NFR-8 文本、登记 known-gaps（「PG 5万 N=5 并发超标 + 10 万档未测（2026-10-24 缩档裁定）」绑 G-6）、M2 halfvec 索引化后复测；§六 M1 行如实落「基线已出 + PG 5万 N=5 未达标已登记」；**双路召回 440/406>300ms 预算缺口一并登记**（独立于并发）。10 万档缩档既有裁定不悄悄改写。**round→3（maxRounds=3，最终轮）、status=implementing。R3 范围：P1-1 池化重跑 + P1-2 勾验材料全量同步 + P2-1/2/3 + P3-1/2/3/6/7 + docs 批（P3-4 行号修正 + P3-5 requirements v0.9.5 联动——supervised-coding 已落笔）+ known-gaps 登记（supervised-coding 按 R3 结果落）。**
- **R3 coder 返回（2026-10-27 20:5x）**：commit `b32e4e4`（docs 批——P3-4 行号修正 + P3-5 requirements v0.9.5 联动，supervised-coding 落笔原样 commit）+ `c809725`（修复批 7 files：bench5 ThreadLocalPgBackend 每线程一连接+错峰 barrier、bench_common schema 标识符净化、report-m1-5/checklist/matrix/fp-review 全量同步、quality.py 仅注释）。**核心真值：pg-5万 N=5 池化后 P95 2443.2ms——仍 FAIL 但较串行化假象（3437.5，作废）改善 -29%**（余扫描级争用：5 路并发 <=> 精确扫描对容器资源竞争）；单请求四组合达标（本轮 1106.2ms，±25% 容器方差带申报，两轮结论对方差稳健）；门禁 663+1 双模式 0 skipped（pg 臂 225）/矩阵 348 复跑全绿；勾验材料 P1-2 全量同步（663/348/684/644MB/87.68s+全量 2990MB/T17 v1.7 详情端点/裁定②处置句）；rps 一致性披露（错峰建连窗）。产品代码零行为变更。
- **known-gaps 登记落笔（2026-10-27 21:0x，supervised-coding 执笔——裁定②判据）**：G-6 v1.2 注记（PG 5万 N=5 2443.2ms 超标 + 双路召回 440.4/405.6>300ms 预算缺口 + 10 万档未测〔缩档裁定申报〕——M2 halfvec 索引化复测）+ 收窄动作②闭环记录（校准四件套：偏差 10.72pp 归因/停用词 +7.14pp/ts_rank_cd 0.00pp/OR 决策材料齐备+真实模型受阻申报）+ 收窄③顺延记录（bench7 脚本入库）+ 重开条件 v1.2 补记；G-8 收窄①②代理面校准完成（截断 r@10 0.00pp/MRR −1.63~−2.38pp；fp16 噪声底 1.0/漂移剖面 >1% warn >5% reject——真实模型与真实抖动两维受阻申报 M2 复验）+ 概览表 G-6/G-8 两行状态更新。**known-gaps 改动在工作区，随 R3 终审链提交（coder doc-only commit 或交付批）。**
- **Tester R3（2026-10-27，ses_e85866e97ffey1hdv5pqmrnTrB）：PASS**。pg-5万 N=5 独立复跑 ×2（3090.9/2440.2——2443.2 精确复现差 0.1%，FAIL 稳固、池化 -29% 成立、backend_mode 字段在库）；门禁 663+1 双模式/矩阵 348 全绿；勾验材料终态核对（「全部 PASS」矛盾消除、裁定②处置句在位、计数/数字/T17 全同步）；known-gaps 一致性逐项核过（NFR-8 条文未改实证）；代码 diff 测试视角无回归（sqlite 臂零改动）；docs 批原样性 ✓。次要发现 2 项（非阻塞）：①主报告预算表 pg 列 R2 轮值未随 R3 同步（无结论翻转）；②known-gaps 区间/轮次标注——**②已由 supervised-coding 修正**（全组合观测带 474~1191ms + 双路召回两轮标注）。①转 Committer 定夺。testedSha=c8097254074e4e5bd528224675eeedb6fc327809。意见原文存 Tester 会话。

## 最新验证意见原文

- （待填）
