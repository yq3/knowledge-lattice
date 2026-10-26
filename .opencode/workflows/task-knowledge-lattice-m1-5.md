---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m1-5
target: knowledge-lattice
coderTaskId: null
testerTaskId: null
committerTaskId: null
status: spec_confirm
round: 1
maxRounds: 3
testVerdict: null
reviewVerdict: null
testedSha: null
reviewedSha: null
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: []
endReason: null
createdAt: 2026-10-25T20:39:56+0800
updatedAt: 2026-10-26T19:41:16+0800
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

- [ ] 用户已确认（确认后 status=implementing——**开工前置：M1-4 完成合入**）
- 历史遗留事项清单：本段承接 M1-4 移交的校准/矩阵/性能组 11 条（M1-4 检查点拆分时移出）；knowledge-lattice 各检查点移交项除 M2 去向与 M1-4 承接外均已归位

## 遗留事项（跨任务移交）

- [ ] 无（本段新增移交项随轮次记录登记；M1 收官后残留归 M2/M3 去向：并发真用例与租约、凭证吊销语义、RFC 8693 act 对象形态、grants 写路径、P3-4 title/dataset、管理面全端点、响应层指标与 judge→M3）

## 轮次记录

- （待 R1）

## 最新验证意见原文

- （待填）
