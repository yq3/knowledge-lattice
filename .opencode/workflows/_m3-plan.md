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
| 3 | task-knowledge-lattice-m3-3 | **语义 hardening 批（含 G-28③⑤ 承接——用户裁定 2026-11-08）**：#15/G-24⑨ 语义查询面随 probe gate 关闭 + annotate fuzzy vec 有界/熔断/降级审计 + G-24⑥ 超长降级/⑦ L1 disambiguation + G-23 残余（模糊层最终一致性修复路径）+ 构建产物 code versioning + R1 P3 残留 + **G-28③：P2-1 pg 单连接共享修复（backend_factory 独立连接/串行化+pg 臂双连接）** + **G-28⑤：链互斥并发测试收编（首轮必做）+qa1b 隔离+refused 分支断言补** + 文案 4 键清扫（i18n access.mem.empty 等「待 m3-1/无 GET members」矛盾文案+注释/CSS）+ 未用导入清扫（顺手：audit 取数包裹/flush existed 按批查询/G-28⑦ 观测面） | 无 | ⬜ 未开工 |
| 4 | task-knowledge-lattice-m3-4 | **评测框架批**：TC-EVAL-02 黄金集合成扩容（中/纯英/混排三态）+ 双后端完整集基线（G-6 重开条件复测载体）+ TC-EVAL-04 deepeval 门禁挂 test_gate.sh + 预注入回归验证 + ragas 选型接入 + #16 conftest teardown DROP 吞错（顺手）+ 门禁 172 条 warnings 治理（m3-1 Tester P3② 存量——dev JWT 弱密钥/docling·pydantic Deprecation） | 无（合成扩容先行；真实语料受阻申报维持——待决-1） | ⬜ 未开工 |
| 5 | task-knowledge-lattice-m3-5 | **评测收口批**：TC-EVAL-03 judge 双语校准（框架 + ~50 条人工双评材料——人工部分用户侧协同）+ 响应层指标固化 + TC-EVAL-05 在线引用锚点抽样 + MRL 截断判据正式落笔（G-8 依赖完整集）+ §六 M3 行总勾验 + 待决-1 受阻申报更新 | judge 端点裁定（design §7「judge 走内部网关」——开发态网关未就绪时是否沿 m2-5 百炼先例转 qwen） | ⬜ 未开工 |

## 二、挂账清单（新会话必读）

**M3 backlog 池（m2-5 移交 + issue 登记）**：
- issue #13 §6.2 五方法组合 → m3-1；#14 组织停用 → m3-1；#15 语义 gate（G-24⑨）→ m3-3；#16 conftest teardown → m3-4（顺手）
- G-22 查询级审计 → m3-2；G-23 残余 → m3-3；G-24 余项①→m3-1、②⑧→m3-2、⑥⑦⑨→m3-3
- m2s-6 followups 四项：显式断言三补（T-S9⑥ 依赖 G-22）→ m3-2；G-23 残余/code versioning/R1 P3 残留 → m3-3
- 待决-1 真实语料：**维持未决**——m3-4 合成扩容先行、真实语料部分受阻申报；TC-EVAL-06 完整收口 + MRL 判据正式落笔依赖（m3-5 出数）

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

1. **推荐下段 m3-2（查询级审计批·含 ui-be 并入——用户裁定 2026-11-08）**——G-22 查询级异步审计（docs/semantic 两侧、月库共用——design §6.3⑥「共用月库」锚点）+ T-S9⑥ 真断言 + G-24②⑧ + 前端对账（api.js 对齐/降级撤除/矩阵·explain 实装/mem.known 真源化）+ 后端小修（P3-1 expires_at 归一/P3-3/边界① detail 文案；顺手 P3-2/5/6/7/8）+ #20 issue 收尾；按协议 0：扫历史检查点（**m3-1 遗留节为最新权威**）+ 建检查点 + 用户确认
2. 硬约束：门禁 **1791+1 起零回归**（双后端双模式 0 skipped、pg 臂收集数 >0）；coder 禁改 docs/ 与 prototype/（ui-be 前端改动属 web/ 不属 prototype/）；分层纪律（core 无方言 SQL、auto_entities 钉 api/mcp 层）
3. 开发/提交固定 develop_opencode、PR base=develop、commit `[task-knowledge-lattice-m3-2] R<n>`；每段 chore 归档批带上工作区遗留流程文档（若有）
4. M3 里程碑验收句（design §8）：门禁能卡住一次人为注入的检索层回归（TC-EVAL-04）；judge-人一致性达标（TC-EVAL-03）；黄金集覆盖中英三态（TC-EVAL-02）；在线锚点（TC-EVAL-05）——m3-5 收口段勾验
5. m3-1 交付基线：origin/develop 前进至 m3-1 PR 合入点（合入后回填）；门禁基线 **1791+1**（pg 臂 671=637+34）

## 四、维护规则

- 每段 done 后：更新 §一 状态列 + §二 挂账勾选（含来源检查点/issue 回写）；本文件随下段 chore 归档批入库
- 段序调整须用户确认后落本表
- 本文件与检查点冲突时以检查点为权威（本文件是导航层）
