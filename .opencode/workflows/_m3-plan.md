# M3 阶段任务分块总览与进度档案（supervised-coding 维护）

> **本文件不是任务检查点**——是 M3 阶段的段序总览/进度/挂账档案，供新会话恢复上下文用。
> 任务检查点仍按 `task-knowledge-lattice-m3-N` 命名，协议 0a 扫描时与此文件互参。
> 拆分方案经用户确认（2026-11-02「同意」——5 段：管理面 1 + 语义 2 + 评测 2）；**跨检查点会话隔离**（2026-10-29 裁定）沿用：每检查点 Coder/Tester/Committer 全新会话，检查点内多轮才续接。

## 一、M3 段序总表（用户确认 2026-11-02）

> 基线：origin/develop = `8b35153`（PR #17〔m2-5〕合入后，2026-11-02）；门禁基线 **1715+1** 双后端双模式 0 skipped（pg 臂 guard 633=599 参数化+34 专用，正则 `\[pg[^]]*\]` 口径）。
> 段序依据：backlog 清偿（纯代码零依赖）→ 评测主线（M3 里程碑验收）；m3-2/m3-3 均无硬依赖可互换，m3-3 全登记级 P3 可再后移。

| # | 检查点 | 任务范围（一句话） | 依赖 | 状态 |
|---|---|---|---|---|
| 1 | task-knowledge-lattice-m3-1 | **管理面补强批（含 be-1 并入）**：#13 §6.2 五方法组合（GET members、POST/PATCH datasets、POST/PATCH dimensions、GET values）+ GET 单维度/单取值端点 + #14 orgs.status 列停用载体+停用语义 + G-24① sem_restricted 管理面授予入口 + **issue #20 be-①②（D-① GET documents 列表 + D-② explain——契约形状以 issue #20 冻结评论为准；用户拍板并入 2026-11-05）**；交付后触发 ui-be 前端对账轮（见 §二 M3-UI 遗留挂账） | ~~前置~~ ✅ 契约冻结评论已发布（2026-11-05，issuecomment-6649900631） | ✅ **done（2026-11-08，round=1 双通过——SHA 33fb815，门禁 1715+1→1791+1，TC-OPS-10 组 76 用例；#13/#14 清偿、G-24① 划销、#20 be-①② 实现面交付〔issue 待 m3-2 收尾〕；边界裁定：explain membership deny 保展开+detail 口径 m3-2 落笔、停用维护链豁免；详见检查点）** |
| 2 | task-knowledge-lattice-m3-2 | **查询级审计批（含 ui-be 并入——用户裁定 2026-11-08 取消独立轮）**：G-22 查询级异步审计子系统（docs/semantic 两侧、月库共用）+ T-S9⑥ 真断言 + m2s-6「显式断言三补」依赖闭环 + G-24② 持权审计两漏记 + ⑧ 审计常量入 domain/audit_events 登记处（顺手）+ **ui-be 前端对账**（api.js contract-first 单函数对齐真契约〔createDataset/createDimension/PATCH orgs 头一致性〕+ be-①②/m3-1 降级横幅撤除 + docs 视图 visible 徽标列+explain 卡+可见性矩阵实装 + mem.known→GET members 真源化 + GET members 替换 export-CSV 名单源；#20 issue 收尾）+ **后端小修**（P3-1 pg list_members·list_orgs_for_user expires_at to_char 归一+双后端断言、P3-3 未用导入、边界① explain membership deny detail 文案「成员关系无效，维度行仅供参考」；顺手 P3-2/5/6/7/8） | 无 | ✅ **done（2026-11-08，round=1 双通过——SHA 995d6fd，门禁 1791+1→1842+1，TC-OPS-11 组；G-22/G-24②⑧ 划销、T-S9⑥+A-16 收口、三补收官、#20 收尾、G-28 新增〔P2-1 用户裁定 m3-3 修复〕；详见检查点）** |
| 3 | task-knowledge-lattice-m3-3 | **语义 hardening 批（含 G-28③⑤ 承接——用户裁定 2026-11-08）**：#15/G-24⑨ 语义查询面随 probe gate 关闭 + annotate fuzzy vec 有界/熔断/降级审计 + G-24⑥ 超长降级/⑦ L1 disambiguation + G-23 残余（模糊层最终一致性修复路径）+ 构建产物 code versioning + R1 P3 残留 + **G-28③：P2-1 pg 单连接共享修复（backend_factory 独立连接/串行化+pg 臂双连接）** + **G-28⑤：链互斥并发测试收编（首轮必做）+qa1b 隔离+refused 分支断言补** + 文案 4 键清扫（i18n access.mem.empty 等「待 m3-1/无 GET members」矛盾文案+注释/CSS）+ 未用导入清扫（顺手：audit 取数包裹/flush existed 按批查询/G-28⑦ 观测面〔④⑦扩容并入——裁定③〕） | 无 | ✅ **done（2026-11-08，round=1 双通过——SHA 3a0a214，门禁 1842+1→1880+1，TC-OPS-12 组 38 用例；G-23 划销/G-24 全项清/G-28④⑤⑦ 划销+③机制与测试已交付〔残余=生产 lifespan 接线部署期〕；#15 随 PR 关闭；口径裁定①补字段〔design §6.3② 自然落位〕②内容哈希③④⑦并入；详见检查点）** |
| 4 | task-knowledge-lattice-m3-4 | **评测框架批**：TC-EVAL-02 黄金集合成扩容（中/纯英/混排三态）+ 双后端完整集基线（G-6 重开条件复测载体）+ TC-EVAL-04 deepeval 门禁挂 test_gate.sh + 预注入回归验证 + ragas 选型接入 + #16 conftest teardown DROP 吞错（顺手）+ 门禁 172 条 warnings 治理（m3-1 Tester P3② 存量——dev JWT 弱密钥/docling·pydantic Deprecation） | 无（合成扩容先行；真实语料受阻申报维持——待决-1） | ✅ **done（2026-11-09，round=1 双通过——SHA 007196c，门禁 1880+1→1898+1，+18=pg_teardown 3+complete_set 4+eval_gate 3+gate_e2e 8；TC-EVAL-02 三态覆盖 ◐〔60q/73docs 全机检，真实端点配额受阻 offline+人工修正——LLM 占比收口 m3-5〕+TC-EVAL-04 ✅〔exact 冻结 60×2+聚合余量双层，注入实证双源含 -O〕+双后端基线〔sqlite 0.9167/0.8031、pg 0.8333/0.7213〕+ragas 接入〔G-29 登记〕+#16 关闭+warnings 171→0+m3-3 移交 P3-2/P3-6/P3-10 清偿；口径裁定：合成端点沿百炼先例、三态覆盖≠完整收口、冻结表更新=有意变更显式动作；详见检查点）** |
| 5 | task-knowledge-lattice-m3-5 | **评测收口批**：TC-EVAL-03 judge 双语校准（框架 + ~50 条人工双评材料——人工部分用户侧协同）+ 响应层指标固化 + TC-EVAL-05 在线引用锚点抽样 + MRL 截断判据正式落笔（G-8 依赖完整集）+ §六 M3 行总勾验 + 待决-1 受阻申报更新 | ~~judge 端点裁定~~ ✅ 用户裁定 2026-11-10 沿百炼先例 | ✅ **done（2026-11-10，round=2 双通过——SHA a96e606，门禁 1898+1→1918+1→1921+1；TC-EVAL-03 框架 ✅/真实校准 ◐〔chat 配额受阻申报+A-6 待数〕+TC-EVAL-05 观察项 ✅〔构造会话记录级——N-1 裁定 search 返回面+G-30 登记〕+响应层固化 ✅/真实基线 ◐+G-8① MRL 判据收口〔512/256 全 0.00pp〕+TC-EVAL-04 增补〔RR exact=G-29③ 关闭〕+m3-4 移交 11 项全清+answersheet 保护〔R2〕；**M3 达成宣告（N-4 受限句式）：除 TC-EVAL-03 真实校准+A-6 定数、TC-EVAL-02 LLM 占比〔同因受阻〕、TC-UI 走查外全部完成**；详见检查点）** |

## 二、挂账清单（新会话必读）

**M3 backlog 池（m2-5 移交 + issue 登记）**：
- issue #13 §6.2 五方法组合 → ~~m3-1~~ ✅；#14 组织停用 → ~~m3-1~~ ✅；#15 语义 gate（G-24⑨）→ ~~m3-3~~ ✅（随 PR 关闭）；#16 conftest teardown → ~~m3-4~~ ✅（重试+schema 名告警+3 用例——随 PR 关闭）
- G-22 查询级审计 → ~~m3-2~~ ✅；G-23 残余 → ~~m3-3~~ ✅ 划销；G-24 余项①→~~m3-1~~✅、②⑧→~~m3-2~~✅、⑥⑦⑨→~~m3-3~~✅（G-24 全项清）
- m2s-6 followups 四项：显式断言三补 → ~~m3-2~~ ✅；G-23 残余/code versioning/R1 P3 残留 → ~~m3-3~~ ✅
- 待决-1 真实语料：**维持未决**——m3-4 合成扩容已交付（三态 60q 全机检）；**m3-5 LLM 候选复跑仍受阻**（chat 配额维持耗尽——m3-5-blocked-claims.md §E，补位不替换）；TC-EVAL-02 LLM 占比/TC-EVAL-03 真实校准+A-6 定数/响应层真实基线 → **配额恢复补跑小批**（不新开里程碑）；真实语料部署复标（G-8① 判据 M3 完整集口径已落笔）
- **m3-3 移交（m3-3 检查点遗留节）**：m3-4 顺手批——~~Committer P3-2（test_query_audit_m33 import time）+P3-6（test_r3_p2_2 函数名更名）+建议项 P3-10（gate 四接线点端点级 e2e 用例）~~ ✅ m3-4 清偿（2026-11-09）；后续 web/语义批——P3-1/3/4/7/8/9 顺手级；PG 接线部署期——P3-5/11+死锁复现注记（RUNBOOK §1.z 已记）；G-28③ 生产 lifespan 接线残余（RUNBOOK §1.z 已记接线点）
- **m3-4 移交（m3-4 检查点遗留节——Committer P3×11 处置）**：~~m3-5 顺手批候选——P3-2（floor=None fail-open）+P3-7（聚合下限显式 raise 使 -O 等强）+P3-8（per-query RR exact 收紧——G-29③）+P3-9（冻结表 vs 基线 JSON 自动同源校验）+P3-6（ragas_bridge docstring 与实现不符——m3-5 接入时修）~~ ✅ **m3-5 全清（2026-11-10）**；~~docs 已落——G-29 新增（①钉版②lock 副作用④分组口径）、RUNBOOK §1.aa~~ ✅；~~登记后续——P3-3（eval_baseline 头部用法/默认 label）+P3-4（eval_corpus 脚本与数据不同源）+P3-10（harness/eval_baseline 自称 M1、.env.example 补 LATTICE_EVAL_LLM_* 等卫生）~~ ✅ m3-5 清偿；P3-1 裁定=维持主依赖（用户 2026-11-10）；P3-5（lock 副作用注记）已落 G-29②/RUNBOOK。
- **m3-5 登记（m3-5 检查点遗留节）**：配额恢复补跑小批（judge 真实校准+A-6 定数+响应层真实基线+LLM 候选增补——不新开里程碑）；部署期 G-30 四项（真实 agent 部署时——应答引用采集入口/agent 标识/sampler actor 配置/TC-EVAL-05 复标）+G-28③ 生产接线维持；后续顺手批（Committer R1 P3×9 去除已闭合 P3-9 + R2-P3×3——calibrate item_id join/守卫 fail-safe 边角/卫生 bundle，M4 或独立 touch 批）；G-29⑤ judge 判读词表残余（真实联调时记录）。

**M3-UI 遗留挂账（issue #20 · 2026-11-05 编排；M3-UI 终态 2d1ea4e = ui-0/1/2/3 + R2）**：
- ① #13 五方法（GET members / POST·PATCH datasets·dimensions / GET values）→ **m3-1 已清偿 ✅（2026-11-08）**。UI 联动（后端落地后前端小改）：建库/建维度 contract-first 降级撤除、`mem.known` 会话注册表退化以 GET members 为真源（零授权成员持久可见 + 成员行 role/到期补全）——**并入 m3-2（用户裁定 2026-11-08）**
- ② #14 组织停用（orgs.status）→ **m3-1 已清偿 ✅（2026-11-08）**。UI 联动：PATCH orgs contract-first 降级撤除 + GET /api/orgs 补 status 列渲染——**并入 m3-2**
- ③ be-① 文档列表（D-①）+ be-② explain（D-②，issue #20 后端轮次）→ **m3-1 已清偿 ✅（2026-11-08，契约冻结评论逐条+test_d11 矩阵红线）**。UI 联动：docs 视图 be-① 降级横幅撤除 + visible 视角徽标列、doc pane explain 卡与可见性矩阵子标签实装——**并入 m3-2**
- ④ m3-2 G-22 查询级审计 → **既有 m3-2 范围**。UI 已预留审计双泳道分流（查询道空态注记「待 m3-2」），落地即有数据，**无需前端改动**
- ~~**ui-be 前端对账轮（be 交付后的小轮，不新增段序占位）**~~ → **取消独立轮次、范围并入 m3-2（用户裁定 2026-11-08「没有专门的UI轮次了，并入M3-2吧」）**：api.js 各 contract-first 单函数对齐真契约 + 上述降级撤除/矩阵·explain 实装/mem.known 退化 + 后端小修（m3-1 Committer P3-1 expires_at 归一/P3-3 未用导入/边界① explain detail 文案；顺手 P3-2/5/6/7/8）——本质 issue #20 收尾，沿本会话「规格+委派+验收」轻流程（m3-2 检查点内）
- 用户侧（不阻塞）：TC-UI-01~05 人工走查回填（`benchmarks/report-ui3-tc-ui-walkthrough.md`——M1+M2 达成宣告唯一待勾）；组织到期 (UTC) 悬停视觉位需带 expires 视角复验（机制同源已验）
- 检查点档案：`task-knowledge-lattice-ui-{0,1,2,3}.md`（各段规格/验收/遗留全录）；AGENTS §1 状态行 M3-UI 句随下段 chore 归档批补记

**部署期（非开发段，不进检查点）**：真实 IdP/SSO 联调（待决-2/3 未决——验签器协议中立口子已留）；rerank 公司 Cohere 网关（DashScope 档已可用）；G-6 全链 SLO 生产首部署复测（1361.6 vs 2443.2 两数据并列定论）+ 双路召回缺口（recall 段 464.3ms>300ms）+ 真实向量 halfvec 10 万档评估。

**用户侧（不阻塞开发）**：TC-UI-01~04 手动走查（**M1+M2 里程碑达成宣告唯一待勾**——清单 `benchmarks/report-m1-5-tc-ui-walkthrough.md`，含 m2-5 B① 逐行过期编辑新形态〔管理面 grants 视图〕）。

**工作区未入库（随 m3-1 chore 归档批入库）**：~~`task-knowledge-lattice-m2-5.md`（PR #17 合入条目——d683da3 之后的工作区改动，沿先例）；本文件与 AGENTS.md 状态行改动同批~~ → **已清偿**：实际随 PR #21（cb340f5，2026-11-05 前置编排批 507b017）提前入库；m3-1 检查点随 m3-1 chore 归档批入库。

**开工时口径裁定预告（任务确认时定，避免 spec_confirm 往返）**：
- m3-1：#14 停用语义（停用后成员认证/检索/任务/webhook/语义面行为——若动 requirements/design 冻结结论走 issue+D 编号）；POST datasets/dimensions 行为细节（新建库/维度初始状态、必选维度、可见性）；**若并入 be-①②（见 §二 M3-UI 遗留挂载③）——开工前须先在 issue #20 冻结 D-①② 契约形状评论**（列表分页/visible 语义/explain 行结构），§6.2 回写与双后端参数化用例随段交付
- m3-2：查询级审计口径（异步形态/采样率/月库共用载体/保留期——design §6.3⑥「共用月库」为既有锚点）
- m3-4/5：judge 端点开发态形态（内部网关未就绪时沿 m2-5 百炼先例？联调用例不进门禁口径沿用）
- TC-UI 走查若发现缺陷：登记 issue 按段收编，不阻塞 M3 段序

## 三、下一段开工指引

**M3 终态（2026-11-10）**——5/5 段全部交付；达成宣告（N-4 受限句式）：除 ①TC-EVAL-03 真实校准+A-6 定数、②TC-EVAL-02 LLM 占比（同因 chat 配额受阻——配额恢复补跑小批）、③TC-UI 人工走查（用户侧）外全部完成。**M3 无下一段**；后续动作：

1. **配额恢复补跑小批**（不新开里程碑，沿受阻申报复跑路径）：A 组 judge 真实联调+校准+A-6 定数、B 组响应层真实基线、E 组 LLM 候选增补（补位不替换）——`eval/reports/m3-5-blocked-claims.md` 各组复跑命令在位。
2. **部署期清单**：真实 IdP/SSO 联调（待决-2/3）+rerank 公司 Cohere 网关+G-28③ 生产 lifespan 接线+G-28①②⑥⑧ 触发时处置+G-30 四项（真实 agent 部署时）+G-6 真实语料复标（v1.5 偏差 3.33pp 维持观察）。
3. **后续顺手批候选**（M4 或独立 touch 批）：m3-5 Committer R1 P3×9（已闭合 P3-9 除外）+R2-P3×3+G-29⑤ judge 判读词表（真实联调时）；m3-3 移交「后续 web/语义批」P3-1/3/4/7/8/9 维持。
4. **用户侧**：TC-UI-01~05 人工走查（`benchmarks/report-ui3-tc-ui-walkthrough.md`——M1+M2+M3 达成宣告唯一共同待勾）。
5. 交付基线：origin/develop = `8bed157`（PR #26 合入后，2026-11-09）→ m3-5 PR 合入后前进；门禁终态 **1921+1**（pg 臂 724=687+37）。

## 四、维护规则

- 每段 done 后：更新 §一 状态列 + §二 挂账勾选（含来源检查点/issue 回写）；本文件随下段 chore 归档批入库
- 段序调整须用户确认后落本表
- 本文件与检查点冲突时以检查点为权威（本文件是导航层）
