---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2-5
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e68aad188ffe4PQPO0YyX50g2G
testerTaskId: ses_e686349f3ffel5L77mqunMleuO
committerTaskId: ses_e6852a652ffe0LMwyPw9XbOUzd
status: done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: d0d8bbe1cdef1778198ea7bf609dbee7a00679f0
reviewedSha: d0d8bbe1cdef1778198ea7bf609dbee7a00679f0
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [".env.example", "benchmarks/bench8_g6_halfvec_50k.py", "benchmarks/calib_m2_5.py", "benchmarks/perf_m2_5.py", "benchmarks/rerank_dashscope_live.py", "benchmarks/report-m2-5-blocked.md", "benchmarks/report-m2-5-g6-halfvec.md", "benchmarks/report-m2-5-g8-real-model.md", "benchmarks/report-m2-5-m2-checklist.md", "benchmarks/report-m2-5-matrix.md", "benchmarks/report-m2-5-perf05.md", "src/knowledge_lattice/adapters/reranker.py", "src/knowledge_lattice/api/admin.py", "src/knowledge_lattice/api/semantic.py", "src/knowledge_lattice/app.py", "src/knowledge_lattice/config.py", "src/knowledge_lattice/core/docs/quality.py", "src/knowledge_lattice/core/semantic/annotator.py", "src/knowledge_lattice/core/semantic/lookup.py", "src/knowledge_lattice/domain/audit_events.py", "src/knowledge_lattice/mcp/server.py", "src/knowledge_lattice/store/backend.py", "src/knowledge_lattice/store/postgres/backend.py", "src/knowledge_lattice/store/sqlite/backend.py", "src/knowledge_lattice/web/app.js", "src/knowledge_lattice/web/i18n.js", "src/knowledge_lattice/web/index.html", "src/knowledge_lattice/web/style.css", "src/knowledge_lattice/worker/rebuild.py", "tests/test_admin_members.py", "tests/test_auth_02_org.py", "tests/test_auth_03_sso_jit.py", "tests/test_az_matrix_m25.py", "tests/test_emb_08_dashscope.py", "tests/test_orgs_admin.py", "tests/test_qual_07_hardening.py", "tests/test_sem_g24_hardening.py"]
endReason: null
createdAt: 2026-11-01T20:53:52+0800
updatedAt: 2026-11-02T11:24:26+0800
---

# task-knowledge-lattice-m2-5: M2 验收收口段

## 任务原文

**段位**：M2 收口段（_m2-plan row 11，主线 6/6 最后一段；M1-5 形态——验收勾验为主 + 移交项收编）。基线：origin/develop = `d3dfdc0`（PR #12〔m2-6〕合入后，2026-11-01）；门禁基线 **1651+1** 双后端双模式 0 skipped。开工时 develop_opencode 先 ff 至 `d3dfdc0`（已确认一致）。

**A. M2 验收收口主线（_m2-plan row 11）**：

1. **跨组织隔离全绿**（M2.6 验收句）：TC-OPS-09（u_gl 仅 org:gl 对 org:tax 的检索/文档详情/任务/审计/**语义端点全量扫描**——全部拒绝或空集）、T15（u_gl 对 org:tax 的 dimension id/value id/document id/grant 端点逐个调用——404/403 按端点固定、绝不返回他组织资源）、TC-AZ-04（sysadmin 跨组织检索拒绝/建组织指定 org_admin/临时授权完整构造〔挂临时成员+双维度授权〕生效期内可见+审计、过期即不可见）。**扫描面必须覆盖 M2 新增端点全集**：管理面 §6.2（维度治理/grants/CSV/任务取消/reindex·reembed 投递/coverage 面板/审计分级/members 增改删/values CRUD/stats）+ 语义端点（sync/builds/sync-runs/entities/tables describe）——m2-6 R3 P1-1（coverage 泄露）教训：全库化/org-scoped 消费面的行集边界须独立验证。
2. **REST-PG 残项**（M1 B-1① 顺延口径 P3-18）：M1 越权矩阵 REST 面跑 pg 后端的残项补齐（M1 时 REST/MCP/shell 120 项跑 sqlite 臂、REST-PG 留 M2）。
3. **G-6 halfvec 索引化复测 + 真实模型重测双后端基线**（known-gaps G-6 收窄③+M1-5 B-3 决策路径①，**2026-11-01 用户同意纳入**）：①bench7 脚本已入库（`benchmarks/`）——halfvec(2560) 表达式索引 vs `<=>` 精确扫描对比 + 5 万档 N=5 并发 P95 复测（M1-5 真值 2443.2ms > 2s SLO，索引化后复测是否达标）+ 双路召回预算缺口复测（5 万档 recall 段 >300ms）——本地 docker PG 执行；②**真实模型重测双后端黄金集基线**（百炼 embedding 下重跑 recall@10/MRR——验证 TokenBag 代理结论是否成立：偏差 10.72pp 构成、停用词 +7.14pp 假设、m1-4 Tester 警告的跨语言系统性低估）——**只出数据与决策建议**（停用词滤除实施/OR 口径变更走决策变更流程，均不在本段）。结论回写 known-gaps G-6。
4. **G-8 真实模型 MRL 截断 + 指纹阈值复验**（**2026-11-01 用户裁定转百炼实测**——.env 已配 DASHSCOPE_API_KEY、.env.example 百炼 compatible-mode 嵌入路径 M0b-3 P3-11 预留）：①MRL 截断——百炼真实调用（dimensions 截断档 vs 全量档），黄金集 recall@10/MRR 对比，**「截断开放为可选配置」判据落笔材料**（M1-5 TokenBag 代理面结论 r@10 0.00pp/MRR −1.63~−2.38pp 待真实模型验证）；②指纹阈值——百炼真实响应抖动分布采样（哨兵文本多次采样的余弦偏差分布），对 0.99/0.95 保守临时值给出校准建议或维持依据（M1-5 校准执行建议 3 步已附）。实测受阻形态（限流等）→ 该子项受阻申报，不虚造。**依据与去向记录入 known-gaps G-8 回写（docs 批，supervised-coding 落笔）**。**环境探测结论（监督侧 2026-11-01 21:3x 实测，coder 实测输入）**：①`text-embedding-v4` compatible-mode 调用**成功**（账户可用无需充值，计费按 token、校准量级成本可忽略）；②config 默认模型名 `qwen3-embedding-4b` 百炼 **404 model_not_found**——开发态百炼用 `text-embedding-v4`（模型名/维度经 env 配置，仓库默认值中立不动，二开者自选）；③**dimensions 为枚举非连续**：`[64,128,256,512,768,1024,1536,2048,3072]`——**2560 不支持**（项目默认 LATTICE_EMBED_DIM=2560 按 qwen3-embedding-4b 设计，百炼档须 env 改维如 2048/1024；MRL 对比口径=全量 vs 枚举截断档）；④rerank `gte-rerank-v2` DashScope 原生端点**成功**（`/api/v1/services/rerank/text-rerank/text-rerank`，响应 `output.results[{index,relevance_score}]`、请求体 `input.{query,documents}` 嵌套——**与 Cohere 契约不同，确认需 DashScopeReranker provider**）。
5. **P3-7 quality 两遍流 hardening**（m1-5 Committer R3 接受为 M2 hardening）：quality 两遍流（区分度重算）边界 hardening。
6. **真实语料人工复核**（待决-1，**受阻申报顺延——2026-11-01 用户裁定**）：真实样例语料未提供；M1-5 合成语料代行结论维持（词面路误报 11~12/12 同域小语料 IDF 稀释、拥挤路零误报、漏报不可评申报），known-gaps 待决-1 顺延注记更新（不虚造复核记录）。
7. **rerank 真实网关联调（百炼实测）+ 配置切换便利性收口 + 真实 IdP/SSO 联调（受阻申报顺延）**：①rerank——**2026-11-01 用户裁定实际联调**（「开发环境用阿里的 API，APIKEY 已给」=.env DASHSCOPE_API_KEY）：百炼 rerank 为 DashScope 原生形态（text-rerank 服务），与 Cohere 风格 `/rerank` 契约不同——**联调内容=按实际请求/响应核对 model/字段/错误形态**；形态不匹配则新增 DashScope 风格 Reranker provider（adapters 层加实现、Reranker 协议不变——G-7「接口不变按形态实现对应 provider」既定口径，LATTICE_RERANKER 增档位），**联调用例网络依赖形态不进门禁**（skip-if-no-key 或同等 fail-safe 口径，先例 TC-EMB-05 none 档）；②**配置切换便利性（用户 2026-11-01 诉求：「二开/其他用户使用时能方便修改 embedding 和 rerank 配置换用其他供应商」）**——**m1-1 P3-14 rerank 部分激活**：补 `LATTICE_RERANK_API_BASE/API_KEY/MODEL`（+`LATTICE_RERANK_TRUNCATE_TOKENS` 顺手）env 覆盖（现 Settings 字段在、env 键缺）；`.env.example` 补 rerank 段完整示例（含百炼/DashScope 档位与 Cohere 风格对照）；embedding 侧 env 已全覆盖+百炼 compatible-mode OpenAI 兼容零代码改动（核对即可）；验收口径=**供应商切换仅经 LATTICE_* env、零代码改动**，仓库默认值保持中立（本地端点/none——不绑云厂，密钥只走 .env 不入库）；③真实 IdP/SSO——**受阻申报顺延**（待决-2/3 IdP 选型/协议未决，结构上不可执行；验签器协议中立可插拔口子已留 m2-4，适配器同形替换路径登记 known-gaps/申报材料）。
8. **TC-PERF-05 语义 P99**（m2s-6 移交性能兜底轮）：annotate 整体 P99 <20ms（AC 层 <5ms）、get_entity depth=2 P99 <50ms、万级词典+高扇出图样本下达标、AC 自动机 (org, dict_rev) 懒加载不重复构建；**含 m2s-6 新增面**：`_repair` per-skip 全量重算 pypinyin 开销、search_entities vec 档超时/熔断/降级审计（G-24③）、模糊内存面 dict 全量复制（G-24④）、vec top-3 硬编码 LATTICE_SEM_FUZZY_VEC_TOP 未消费（G-24⑤）。
9. **§六 M2 行总勾验**：TEST-CASES §六 M2 行（含 M2-S1/S2/S3 行）完成态核对——落笔归 supervised-coding docs 批（coder 供勾验材料）。

**B. 移交项收编（历史检查点遗留，默认并入）**：

- **m2-6 → m2-5**：B①「逐行过期编辑」（UI grants 逐行独立 expires_at 输入——Committer R1 裁定登记，非门禁面，随 TC-UI 批）；R3 Committer P3×3 文案/注释（pg 并发用例 docstring 旧称 FOR UPDATE／fail-closed 注释+错误文案旧称「自动重试」／coverage 端点 docstring 旧称「全局口径」——无功能影响）。
- **m2-4 → m2-5 followups（测试补强批）**：④`_outbox_insert` 完整性错误掩码（理论面）；⑤MCP 面忽略审计先于 resolve_org 窄面（未来统一时移块——本批评估是否可收）。①②③已随 m2-6 清偿。
- **m2s-6 → m2-5**：TC-PERF-05 性能兜底（见 A8）。m2s-6「下批语义 followups」四项（G-23 残余收口/显式断言三补/R1 P3 残留/构建产物 code versioning）——**用户裁定 2026-11-01 后移 M3/独立语义补强批，不并入本任务**（交付批回写 m2s-6 检查点去向）。

**C. 监督侧事项（supervised-coding 执行，不入 coder 范围）**：

- pg 存量 7 个 bench/eval 残留 schema（`lattice_eval_*`×5 + `lattice_bench_g6hv_*`×2——历史会话产物）核对后 `DROP SCHEMA ... CASCADE` 清理（m2-6 移交监督侧待办）。
- 工作区未入库 2 文件（`_m2-plan.md`/`task-knowledge-lattice-m2-6.md`——PR #12 合入后终态回写）随本段 chore 归档批入库。

**硬约束**：

- 门禁 1651+1 起零回归（双后端双模式 0 skipped，pg 臂收集数 >0——新正则 `\[pg[^]]*\]` 口径）。
- **coder 禁改 docs/**（requirements/design/TEST-CASES/known-gaps/RUNBOOK）与 prototype/——验收口径变化经用户确认后由 supervised-coding 落笔。
- 分层纪律：core 不写方言 SQL；auto_entities 钉 api/mcp 层（AGENTS §3/design §3）。
- 测试按模块前缀命名、双后端参数化；bench/eval 产物归 benchmarks/（报告 report-*.md）。
- 开发/提交固定 develop_opencode，PR base=develop；commit 格式 `[task-knowledge-lattice-m2-5] R<n>`，commit 前确认 origin/develop 无前进。

**验收标准**：

1. TC-OPS-09/T15/TC-AZ-04 全绿（含 M2 新增端点全集扫描；REST-PG 残项补齐）——矩阵报告落 benchmarks/。
2. G-6 复测出数（halfvec vs 精确扫描、5 万 N=5 P95、双路召回预算、**真实模型双后端基线**）+ 结论回写材料；G-8 百炼实测出数（探测已通——见 A4 环境探测结论）。
3. TC-PERF-05 达标出数（含 m2s-6 新增面；不达标则按 M1-5 先例如实申报+登记）。
4. P3-7 hardening + B 组移交项（B①/P3×3/followups ④⑤）交付。
5. 环境依赖项按 2026-11-01 裁定：**rerank 百炼联调记录+用例（网络依赖不进门禁）、G-8 百炼实测出数**；待决-1/真实 IdP 受阻申报材料更新（不虚造）；全部结论回写 known-gaps（docs 批落笔）。
6. **配置切换便利性（用户 2026-11-01 诉求）**：embedding/rerank 供应商切换仅经 LATTICE_* env 零代码改动；rerank env 覆盖补齐（P3-14 激活）+ `.env.example` 完整示例（rerank 段新增）+ 用例锁定（env 覆盖生效断言）。
7. §六 M2 行勾验材料就绪（supervised-coding 落笔）。
8. 门禁 1651+1 起零回归（允许净增）。

## 需求确认
- [x] 用户已确认（2026-11-01 21:22「其他内容按建议执行，做好文档记录」——status=implementing）
- 历史遗留事项清单：（supervised-coding 扫描历史检查点汇总，默认并入本任务，见 README §4.6）
  - m2-6 移交：B① 逐行过期编辑（→TC-UI 批）、R3 P3×3 文案卫生、pg 残留 schema 清理（监督侧）——**并入本任务**
  - m2-4 移交：followups ④⑤——**并入本任务**；真实 IdP/SSO 联调——**受阻申报顺延**（待决-2/3 未决）
  - m2s-6 移交：TC-PERF-05 性能兜底（含 G-24③④⑤）——**并入本任务**
  - m2s-6「下批语义 followups」四项（G-23 残余收口/显式断言三补/R1 P3 残留/构建产物 code versioning）——**用户裁定 2026-11-01 后移 M3/独立语义补强批**（T-S9⑥ 依赖 G-22 独立任务；交付批回写 m2s-6 检查点去向）
  - m1-1 移交：rerank 真实网关联调——**并入本任务转百炼实测**（用户 2026-11-01：开发环境用阿里 API、DASHSCOPE_API_KEY 已配 .env）
  - m1-5 遗留：G-6 halfvec 复测（本地执行）+ G-8 真实模型复验（**转百炼实测**——key 已配、嵌入百炼路径 M0b-3 预留；依据记录入 G-8 回写）+ 真实语料人工复核（待决-1 受阻申报顺延）+ P3-7 quality 两遍流 hardening + REST-PG 残项——**并入本任务**
  - 工作区 2 未入库流程文档——**随本段 chore 归档批**
- **裁定记录（2026-11-01）**：①环境依赖四项处置——rerank 转百炼实测、G-8 转百炼实测（监督侧依据 DASHSCOPE_API_KEY+百炼嵌入预留路径推断，预告时已明示可否决）、待决-1/真实 IdP 受阻申报顺延；②m2s-6 语义 followups 四项后移 M3/独立批；③A+B 范围与验收标准确认。「做好文档记录」=受阻申报材料/联调记录/G-6·G-8 结论回写 known-gaps 均须落笔完整（docs 批 supervised-coding 执笔，coder 供材料）。**④补充澄清（21:28）**：用户确认开发态统一用其提供的阿里 APIKEY（embedding+rerank 两模型）；核心诉求=二开/其他用户须能**方便地经配置切换供应商**——与 D12「模型端点中立、不绑云厂」完全一致，无设计冲突；落地缺口两处纳入 A7②（DashScope rerank provider + P3-14 rerank env 覆盖激活）；仓库默认值维持中立、百炼配置走 .env（不入库）。**⑤百炼环境探测（21:36，用户同意纳入 G-6 真实重测后先试 API）**：embeddings（text-embedding-v4）+ rerank（gte-rerank-v2）双端点实测**均通**——账户可用**无需充值**（按 token 计费、校准量级成本可忽略）；发现两项事实入 A4 探测结论（默认模型名 404→百炼档用 text-embedding-v4；dimensions 枚举无 2560→env 改维）；rerank 确认 DashScope 原生格式需新 provider。开发全程（M0b 起）嵌入/rerank **零真实调用**的欠账（TokenBag 代理面数据）自本段起以真实数据回填（G-6 基线/G-8 MRL+阈值/rerank 联调）。

## 遗留事项（跨任务移交）
- [x] **本轮清偿**（2026-11-02 交付，双 SHA=d0d8bbe）：m2-6 移交 B① 逐行过期编辑（✅ 4/4）+P3×3 文案+pg 残留 schema（监督侧 DROP）；m2-4 followups ④⑤+真实 IdP（受阻申报顺延部署期）；m2s-6 TC-PERF-05+G-24③④⑤（语义 followups 四项用户裁定后移 M3）；m1-1 rerank 联调（百炼收口）；m1-5 G-6/G-8/P3-7/REST-PG（待决-1 受阻申报顺延）。
- [ ] **移交 M3 backlog**（本段交付时登记——R1 Committer 边界裁定+R2 复审登记，issue 链接见交付条目）：①§6.2 五方法组合未实现+GET 单维度/单取值端点（M3 管理面补强批）②组织停用无载体（orgs 无 status 列）③语义查询面不随 probe gate 关闭+annotate fuzzy vec 无界/无 breaker/审计（known-gaps G-24⑨——M3 语义补强批）④m2s-6 语义 followups 四项（G-23 残余/显式断言三补/R1 P3 残留/code versioning——用户裁定 2026-11-01 后移）。
- [ ] **移交部署期**：真实 IdP/SSO 联调（待决-2/3）；rerank 公司 Cohere 网关（DashScope 档已可用）；G-6 全链 SLO 生产首部署复测（1361.6 vs 2443.2 两数据并列定论）+真实向量 halfvec 10 万档评估。
- [ ] **移交 test-infra**：conftest teardown 吞 DROP 失败（低优先 issue——下次测试基建批）。
- [ ] **用户侧**：TC-UI-01~04 manual 走查（M1+M2 里程碑达成宣告唯一待勾——含本段 B① 逐行过期编辑新形态，清单 benchmarks/report-m1-5-tc-ui-walkthrough.md）。
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1: coder 完成（2026-11-01 22:52 报告，**全新会话**，coderTaskId=ses_e68aad188ffe4PQPO0YyX50g2G，commit `db520097ac62fb53461733b4b6b322fccbada486` 于 develop_opencode，37 files +3245/−68，父提交=d3dfdc0 同步确认 origin/develop 无前进，未 push）——**A1** ✅ 跨组织隔离矩阵全绿（TC-OPS-09 u_gl 35 端点全扫/T15 资源 id 404·400·403 按端点固定/TC-AZ-04①~④ 全链+三组织行集边界〔org:ops 第三组织——m2-6 P1-1 同型面〕，test_az_matrix_m25 9 用例×双后端 REST 参数化=**A2 REST-PG 残项补齐载体**；**择型申报：GET/POST /api/orgs 实装**〔design §6.2 L1121 表列明 API 缺失——TC-AZ-04② 载体，store list_all_orgs/list_orgs_for_user/create_org 双方言+建组织指定首任 org_admin 同事务审计〕）。**A7** ✅ DashScopeReranker provider（gte-rerank-v2 原生契约 input.{query,documents}/output.results；离线 MockTransport 11 用例；真实联调报告——top_n 忽略差异登记）+P3-14 激活（LATTICE_RERANK_API_BASE/KEY/MODEL/TRUNCATE_TOKENS env 覆盖+.env.example rerank 段百炼/Cohere 对照+未知档位 fail-closed）。**A8** ✅ TC-PERF-05 全达标（万级词典 10312 实体：annotate 整体 P99 0.063ms/AC 0.010ms/get_entity depth2 0.041ms/懒加载同实例；G-24③④⑤ 收口——vec 档 query_embed_timeout_s 有界+共享熔断+search.degraded 审计〔scope=search_entities〕/模糊面懒构建〔万级 3.75s→AC 路径零〕去 dict() 复制/vec_top 参数化 LATTICE_SEM_FUZZY_VEC_TOP 端到端）。**A5** ✅ P3-7 两遍流 hardening（non-finite 防御+池缩水窗口有效列均值〔哨兵统一 -2.0〕）。**B 组** ✅ B① UI 逐行过期编辑（playwright DOM 三断言：初始=库内值/独立编辑+新选行预填/保存读回逐行正确——accessState.expires 逐行唯一真值源）+followup ④（_outbox_insert 完整性错误专用上抛不掩码双方言）/⑤（MCP 忽略审计移 resolve_org 后）+m2-6 P3×3 文案卫生。**A3/A4** ✅ 实验出数：bench8 5 万档精确扫描 N=5 并发 P95 **400~590ms 达标（M1-5 真值 2443.2 未复现——环境差异如实申报，两数据并存）**+halfvec 索引化**不引入建议**（LIMIT64 overlap 0.12~0.56 欠召回实证、1024 档零收益——合成向量最坏情形口径局限已注）+双路召回 264~289ms 达标；真实模型 text-embedding-v4 黄金集双后端 r@10 **sqlite 0.9286/pg 1.0000**（TokenBag 对照 +3.57/+21.43pp 代理低估验证）+**MRL dimensions 截断 512/256 双后端 0.00pp 零损失**（服务端原生 MRL）+指纹阈值 60 样本余弦全 1.0→**维持 0.99/0.95**；rerank gte-rerank-v2 联调契约一致（top_n 忽略差异登记消费面零影响论证）。报告×6 落 benchmarks/（matrix/g6-halfvec/g8-real-model/perf05/m2-checklist/blocked〔A6 待决-1+真实 IdP 受阻申报〕）。自测：TDD 红→绿逐项（ImportError/events 空/calls==1/NaN 传染/池缩水 flagged=0/掩码证伪/路由 404 等）+playwright DOM；GATE PASS **1708+1 双后端双模式 0 skipped**（基线 1651+1，+57；pg 臂 632=598 参数化+34 专用全实跑）。机械核验（supervised-coding 22:54）：HEAD=db52009 ✓、commit 格式 R1 ✓、37 files 全在 src/tests/benchmarks/.env.example ✓、docs/（文档目录）/prototype/检查点零改动 ✓（core/docs/ 系代码包）、未 push ✓、工作区仅监督侧 3 文件 ✓、data/bench-results 工件未入库 ✓。verdict 双 null 待 Tester/Committer。**择型 8 条**：①/api/orgs 实装（§6.2 表载体）②G-24③ 复用 search.degraded+scope 区分/熔断共享 service.breakers["embed"] ③P3-7 有效列 >-1.5 判据+NaN 钉 numpy 边界 ④followup④ 转 RuntimeError 最小侵入 ⑤矩阵 fixture sqlite 默认工厂/pg 注入 make_backend（B⑧ 先例）⑥B① accessState.expires 唯一真值源+#gExpires 降级预填源 ⑦T15 grants 端点断言 400（实现固定口径——404/403 字面偏离申报）⑧真实档 text-embedding-v4 默认 1024。**边界申报 5 条**：①A2 以矩阵 9 用例双后端为载体，未逐一翻写 M1 全部 122 条 REST 用例（重叠+门禁翻倍成本不成比例）②M1-5 真值 2443.2 未复现（3 轮稳定 400~590，差异 4~6× 超容器方差——两数据并存不单方采信）③halfvec 结论合成向量口径局限（10 万档须真实向量复测）④1708+1 的 1 deselected=manual 同基线口径 ⑤TC-OPS-09 语义隔离 l0 断言放宽「他组织 key 零出现」（fake 源无 curated l0 条目）。

- R1: tester **PASS**（2026-11-01 23:13，**全新会话**，testerTaskId=ses_e686349f3ffel5L77mqunMleuO，testedSha=db520097ac62fb53461733b4b6b322fccbada486 复核一致）——门禁独立复跑 **GATE PASS 1708+1 双后端双模式 0 skipped**（pg 臂 632=598+34 全实跑；+57 逐文件归因 collect-only 实测闭合：az_matrix 18+orgs 6+emb_08 11+sem_g24 14+qual_07 4+auth_02 +2+auth_03 +2）。逐项勾验 A1~A9+B 全 ✅（A1 扫描面 35 端点字面属实〔P2① 注记〕/A2 裁剪 ACCEPT——store/core 双后端参数化历史事实+az matrix [pg] 18 条 REST×pg 端到端载体+「pg 专属方言进 REST handler 时须补」注记/A3·A4 报告↔JSON 工件逐值对账一致〔r@10 0.9286/1.0000、MRL 0.00pp、指纹 60 全 1.0、P95 588.9、overlap 0.1152~0.5586、10312 实体 build_stats 全谱〕+2443.2 两数据并存处理得当/A7 MockTransport 契约与监督侧探测逐字段一致+联调脚本形态不收集不进门禁〔比 skip-if-no-key 更强〕/A8 数据合理+G-24③④⑤ 代码用例双核实/A5 缺陷形态真实构造〔NaN 直注 numpy 边界+池缩水 monkeypatch〕/B① playwright 脚本未入库代码级核验三断言全支撑〔m2-3 先例同形态〕）。**择型 8 条：7 ACCEPT+⑦有保留 ACCEPT——T15 grants 400 为 CASE_BUG 候选上报**（实现满足实质约束但与用例正文「404 或 403」及附录 A-2 二分法字面矛盾——**需 committer 裁定改用例落字**，非实现缺陷）。**边界 5 条全 ACCEPT**。**注入验证 4/4 红→恢复**（①/api/orgs 摘成员行集过滤红②懒构建回归红③池缩水旧口径漏标复现红④降级审计摘除红——双臂全过；业务代码 git diff db52009 -- src/ 零改动）。**回归零弱化**（8 测试文件=6 新增+2 增补+1 docstring；1708−57=1651 旧用例全在且绿）。**P1 无；P2×2**（①A1「35 端点=全集」申报口径——实现 ~43 条用户面路由 scan 外 6 条〔values POST/quality-flags×2/documents POST/webhook/uploads PUT〕均共享守卫或独立身份防线实质风险低——建议下轮补扫 2~3 条或修订措辞；②design §6.2 列明实现缺失 5 个方法组合〔GET /members、POST /datasets、PATCH /datasets/{id}、POST /dimensions、PATCH /dimensions/{id}〕——历史缺口非 R1 引入，建议 issue 登记或 docs 批标注）；**P3×5**（①m2-checklist 笔误 1707+2/+56→实为 1708+1/+57②rerank 延迟口径 470ms 报告 vs 工件 196.6ms③bench8 3 轮仅末轮 JSON 工件④lookup.py except (FutureTimeoutError, Exception) 冗余⑤create_org store 级 POST×pg 专项缺——并入 P2① 补扫）。临时产物清理 ✅（注入文件删/gate.log 删/pg 零新增残留〔存量 7 历史未动〕/.env 未读取）。报告全文见「最新验证意见原文」details 块（R1 Tester）。

- R1: committer **NEEDS_CHANGES**（2026-11-01 23:26，**全新会话**，committerTaskId=ses_e6852a652ffe0LMwyPw9XbOUzd，reviewedSha=db52009=testedSha=HEAD 三一致；R1 首审 diff=d3dfdc0..db52009 37 files 逐文件核对；门禁采信 Tester 独立复跑+静态对账自洽；docs/prototype 零触碰核实 ✓、零弱化 ✓、分层纪律 ✓、安全面深审无 P1——/api/orgs 越权/审计同事务/D16/双方言等价全过、DashScope provider 失败形态、G-24③④⑤、P3-7、followup④⑤、B①、env 覆盖均代码级核对通过）——**P1 无；P2×5**：**P2-1** TC-PERF-05「高扇出图」证据整体失效——perf_m2_5.py:89-100 的 310 条 rels 构造后**从未传入 run_sync/FakeSourceAdapter**（JSON 工件 relations=0/orphan_nodes=10312 实证），且关系类型 `used_by` 不在白名单（应为 scenario→template `uses`）、模板根展开 expand 方向错——get_entity depth2 是**零边图空展开**，「高扇出/全项达标」不成立（修法=rels 接入+uses 方向+图形态断言 nodes/edges/truncated〔fanout_limit=200 应 truncated〕+重跑更新报告与 m2-checklist）；**P2-2** A3「5 万 N=5 并发 P95」口径错配——bench8 只跑 render_vec_recall_select 的**召回 SQL 片段**，M1-5 真值 2443.2 来自 bench5 形态的**全链 search()**（embed+召回+fuse+rerank），「同容器同口径/未复现/SLO 达标」表述不成立（修法=bench5 形态 pg 5 万 N=5 full search P95 复跑同口径对照；halfvec 若仅召回段则明示「索引仅影响召回段、全链 SLO 未测」撤回达标结论）；**P2-3** A1 扫描面漏 M2 新增端点且报告宣称「全集」——values POST（任务书点名项）与 webhook 未扫（修法=补 POST values 403+webhook 401〔无签名 fail-closed〕；documents POST/quality-flags/uploads PUT 可按共享守卫论证保留注记但报告须列明未扫项）；**P2-4** T15 的 dimension/value id 404 断言**伪绿**——被测 GET 路由不存在（404 来自 MCP mount 兜底非存在性判断）（修法=改用真实端点 PATCH values/POST retire/POST values→404+docstring 注明 design 无 GET 单维度端点缺口）；**P2-5** design §6.2 列明 5 方法组合未实现（GET /members、POST/PATCH /datasets、POST/PATCH /dimensions、GET values——历史缺口非 R1 引入）而 m2-checklist「M2 行无未清偿项」过度（处置=issue 登记+docs 批实现状态注记+m2-checklist 改「实现范围+backlog」，**不在 R2 实装**——Committee 建议，待用户确认）。**P3×13**（文档数字笔误/MRR 脚注与 metrics.py 算法不符/rerank 脚本 docstring 陈旧/别名数错/except 冗余/**annotator 懒构建赋值顺序并发时序**〔fuzzy_terms 先于索引赋值——并发首建窗口 fuzzy 候选静默缺失+无锁重复构建，建议最后赋 fuzzy_terms 作哨兵或加 Lock〕/DashScope top_n 可能应放 parameters 下〔live 探测后修 provider 或明示 no-op〕/**create_org 边界**〔id/name 无校验+org_admin 可缺省→死组织+pg UniqueViolation 竞态 500〕/**semantic 查询面绕过指纹探针 gate**〔api/search 传 gate 而 search_entities/annotate fuzzy vec 不看——历史缺口建议 known-gaps 登记〕/fresh 死状态/测试质量小项×4〔vec_top 恒真风险/breaker 复位未断言/矩阵 docstring 名实/fresh 措辞〕/test_orgs_admin 仅 sqlite 臂/create_org POST×pg 专项缺/admin docstring 未登记新端点）。**需求边界×4 上报**：①§6.2 端点表 vs 实现 5 方法组合（建议 backlog 登记+docs 批标注，不阻塞收口）②TC-PERF-05 P99 是否含 fuzzy 懒构建首调（建议 docs 批补「稳态口径、首调单列」注记）③「组织不可删只能停用」无载体（orgs 无 status 列无停用端点——建议 issue/known-gaps 登记）④语义向量路不随 probe gate 关闭+annotate fuzzy vec 无界无 breaker（建议 known-gaps 登记 M3 处置）。**择型 8 条全 ACCEPT**（⑦裁定**非 CASE_BUG 无需改 TEST-CASES/A-2**——400 属 m2-3 既有「同组织非成员目标」语义非跨组织口径，R2 仅改 docstring/报告措辞为「T15 延伸面」）。**边界 5 条：4 ACCEPT+②PARTIAL**（2443.2 并列数据正确但口径表述不成立——随 P2-2 修）。**实验报告方向审查**：G-6 halfvec 召回段结论成立但全链 SLO 未测；真实基线 pg 1.0000 系 28 query 饱和态——docs 批不得以此关闭「>2pp 重开条件」；MRL「零损失」应写「本集分辨率内未观测到」并保留 M3 复标；指纹维持成立。**R2 范围建议（优先级）**：①P2-2 重做 A3 SLO（bench5 形态全链复跑+口径重写）②P2-1 修 perf05（关系接入+图断言+重跑）③P2-3/P2-4 修 A1/T15（补扫+真实 404 路径+报告措辞）④P3 批量（含懒构建顺序/fresh 清理/create_org 边界）⑤门禁重跑预期只增不减。报告全文见「最新验证意见原文」details 块（R1 Committer）。
- **R1 需求边界上报（status=spec_confirm，2026-11-01 23:26）**：supervised-coding 按协议置 spec_confirm——NEEDS_CHANGES 含 4 条需求边界问题（①§6.2 五方法组合 backlog vs 实装②TC-PERF-05 P99 稳态口径③组织停用无载体④语义 vec gate 缺口）不直接发 coder；复述给用户裁定后 round 1→2 调 coder R2（P2×5+P3 应修尽修）。
- **R1→R2 边界裁定（2026-11-02 10:03 用户「按建议执行」，spec_confirm→implementing，round 1→2，reviewedSha 置空）**：**边界①选 a**——§6.2 五方法组合（GET /members、POST/PATCH /datasets、POST/PATCH /dimensions、GET values）**不实装**，issue 登记 backlog + docs 批实现状态注记，m2-checklist 改「实现范围+backlog」口径（M3 管理面补强批处置）；**边界②**——TC-PERF-05 P99 稳态口径、fuzzy 懒构建首调单列（docs 批注记，supervised-coding 落笔）；**边界③**——组织停用无载体 issue/known-gaps 登记（M3 处置）；**边界④**——语义 vec 不随 probe gate 关闭+annotate fuzzy vec 无界（known-gaps G-24 扩展或新条目，M3 语义补强批）。**R2 范围（Committer §八+裁定）**：P2-2 重做 A3 SLO（bench5 形态 pg 5 万 N=5 全链 search P95 同口径对照；halfvec 仅召回段则明示）+P2-1 修 perf05（关系造数接入+uses 方向/类型+图形态断言+重跑）+P2-3/P2-4 修 A1/T15（补扫 POST values 403+webhook 401+真实 404 路径+报告措辞）+P2-5 按边界①a 处置（勾验材料改口径，不实装）+P3 应修尽修（Tester ①~⑤+Committer P3-1~13：文档数字/MRR 脚注/docstring/except 懒构建顺序/top_n parameters 探测/create_org 边界/fresh 死状态/测试质量小项×4/orgs pg 专项）；门禁重跑预期只增不减。

- R2: coder 完成（2026-11-02 10:36 报告，**续接会话**，coderTaskId=ses_e68aad188ffe4PQPO0YyX50g2G，commit `d0d8bbe` 于 develop_opencode，17 files +540/−202，父提交=db52009，origin/develop=d3dfdc0 无前进确认，未 push；filesChanged 并集不变 37——R2 全部文件已在清单内）——**P2-1** ✅ TC-PERF-05 真实边图重做（rels 混入 records 传入 run_sync——R1 版 310 条关系从未入图；uses 方向按白名单 scenario→template 修正+expand=["uses<"] 入向；图形态断言固化〔表根 300 列@fanout_limit=200→nodes=200/edges=200/truncated=True〕；**重跑：表扇出 depth2 P99 16.301ms<50ms 真实达标**〔R1 零边图 0.041ms 作废〕、relations=310 build_stats 实证）。**P2-2** ✅ A3 全链 SLO 同口径重做（**复用 bench5 脚本** --scales 50000 --backends pg——M1-5 真值产生器同口径：seed_corpus 双维度 ACL+全配方 search+N=5 12s；**P95 1361.6ms PASS vs M1-5 真值 2443.2ms 未复现**〔-44% 环境负载差异、两数据并列保留、**不关闭 G-6 重开条件**〕；撤回 R1「召回段=SLO 达标/同容器同口径」错误表述——g6 报告重写三层口径〔全链/召回段 ACL 简化申报/真实基线〕；单请求 C_full 911.4ms〔recall 段 464.3ms 双路召回缺口维持〕；halfvec 全链档未测如实申报）。**P2-3** ✅ A1 补扫（+POST values 403+webhook 401=**37 端点**；未扫 6 条共享守卫注记+矩阵报告列明原因；「全集」措辞修正）。**P2-4** ✅ T15 伪绿根除（PATCH values/POST retire/POST values 真实路由全 404；docstring 注明 design 无 GET 单维度端点缺口〔裁定①a backlog〕；grants 400 改称「T15 延伸面」）。**P2-5** ✅ backlog 口径（m2-checklist 改「验收句已清偿+§6.2 backlog」，不实装——裁定①a）。**P3 应修尽修**：annotator 懒构建并发时序（Lock+双重检查+哨兵赋值序 fuzzy_terms 最后——8 线程 Barrier 首建恰 1 次+中间态零可见）/create_org 边界（org_admin 必填+id/name 空白 400+pg UniqueViolation→OrgExistsError 409〔越过预查直撞 UNIQUE 用例〕）/DashScope top_n **parameters 修正**（实测顶层不被识别、parameters.top_n 生效恰截断——provider 修+MockTransport 断言 body.parameters+live 复跑 respected=True）/vec_top 恒真根除（monkeypatch 捕获实参双向断言）/breaker 复位断言/stats·audit·grants export 行集断言补齐/lookup except 清理/web fresh 死状态移除/admin docstring/mcp_semantic_tools 名实/_pg_db import/**MRR 脚注按 eval/metrics.py 改正**（含全部 28 query、差异来自 6 条双 label 分母）/MRL 改「本集分辨率内未观测到」/延迟以工件为准（196.6/360.3ms 轮次注明）/perf05 别名 25624/bench8 仅末轮落盘注记。自测：TDD 红→绿（并发懒构建 calls==8 红/create_org 未拒红/pg 裸 UniqueViolation 红/parameters 断言红）；GATE PASS **1715+1 双后端双模式 0 skipped**（R1 1708+1 → +7=orgs 5+thread_safe×2 对账闭合；pg 臂 633=599+34 全实跑）。机械核验（supervised-coding 10:36）：HEAD=d0d8bbe ✓、commit 格式 R2 ✓、17 files 全在 R1 清单内 ✓、禁改区零触碰 ✓、未 push ✓、工作区仅监督侧 3 文件 ✓。**择型 4 条**：①P2-2 复用 bench5 脚本（比新写 harness 更强同口径性）②org_admin 必填选 pydantic+strip 校验（422/400）③pg 竞态用例 monkeypatch execute 等效时序（非真双连接）④图断言容差 195..202（BFS 物化边界）。**边界申报 4 条**：①「不做」项确认（五方法组合/稳态注记/组织停用/语义 gate——归监督侧）②bench5 复跑覆写 R1 的 m1-5-tc-perf-03-pg-50000.json 同 tag（M1-5 原值在 git 历史+汇总 JSON；报告已注轮次）③bench8 仅末轮 JSON 维持+四轮数字注记（未改历史脚本）④rerank live 两轮工件值并列（网关 RTT 波动 1.8×）。

- R2: tester **PASS**（2026-11-02 10:49，**续接 R1 会话**，testerTaskId=ses_e686349f3ffel5L77mqunMleuO，testedSha=d0d8bbe1cdef1778198ea7bf609dbee7a00679f0 全 SHA 复核一致）——门禁独立复跑 **GATE PASS 1715+1 双后端双模式 0 skipped**（pg 臂 633=599+34；+7 归因实测闭合：orgs 6→11〔必填 1+空值参数化 3+pg 竞态 1〕+sem_g24 14→16〔thread_safe×2〕；1715=1651+57+7 链式对账）。**P2×5 修复闭环逐条勾验全 ✅**：P2-1（rels 混入+uses 方向+expand 入向+图断言固化；工件 relations=310/nodes=200/edges=200/truncated=true/orphan=10000 全连图自洽；**表扇出 depth2 P99 16.301ms<50ms 真实边图达标**；annotate 持平佐证）；P2-2（**真复用 bench5 历史脚本零改动**；工件 C_full_n5 P95 **1361.6ms**/P50 1074.6/rps 3.54/notice 全净；分段和 913.7≈911.4 自洽；seed 67s 全量造数；g6 三层口径重写+R1 错误表述显式撤回+两数据并列不关 G-6+双路召回缺口维持〔464.3ms〕+halfvec 全链未测如实申报）；P2-3（37 端点+未扫 6 条注记列明+措辞修正）；P2-4（三条真实路由对照 admin.py L216/L269/L885 **确认存在**全 404；retire 零副作用；伪绿根因 docstring 记录；「T15 延伸面」按 R1 Committer 裁定收口）；P2-5（backlog 口径）。**P3 闭环全 ✅**（R1 自身 5 条+Committer 13 条：annotator Lock 单锁无嵌套无死锁/AC 主路径不过锁零退化/首建持锁阻塞=语义正确；create_org BEGIN IMMEDIATE 锁内预查 sqlite 竞态不存在——pg-only 映射合理完备；top_n parameters provider+MockTransport+live respected=True+Cohere 零影响；vec_top 双向捕获；MRR 脚注与 eval/metrics.py 数学自洽〔(22+6×0.5)/28=0.8929 与 recall@1 一致〕；fresh/docstring/名实/import/MRL 分辨率限定全落实）。**注入 2/2 红→恢复**（A 摘 Lock→calls==8 红；B 摘 UniqueViolation 捕获→裸异常逃逸红——业务代码零残留）。**回归零弱化**（2 def 改名/重写同断言体、2 assert 升级；57+1651 全在绿）。**P1 无；P2 无；P3×6 文档级**（①m2-checklist L10 残留 R1 快照旧值〔35 端点/24 passed〕与 L40-43 并存矛盾——docs 批勿以旧行为准②L20 G-8 摘要未同步「分辨率内未观测到」口径③矩阵报告 34×403+1×401 混述④矩阵报告用例名未同步⑤annotator 返回值未使用无害冗余⑥计数边界含糊）。**观察**：conftest teardown 吞 DROP 失败致测试 schema 残留（Tester 已清 3 个；存量 7 历史未动；建议未来 teardown 重试/告警）。临时产物清理 ✅。报告全文见「最新验证意见原文」details 块（R2 Tester）。

- R2: committer **APPROVED**（2026-11-02 10:56，**续接 R1 会话**，committerTaskId=ses_e6852a652ffe0LMwyPw9XbOUzd，reviewedSha=d0d8bbe1cdef1778198ea7bf609dbee7a00679f0=testedSha=HEAD 三一致；R2 diff=db52009..d0d8bbe 17 files 逐文件核对；门禁采信 Tester R2 独立复跑 1715+1；docs/prototype 零触碰 ✓、零弱化〔2 def 改名/重写同断言体、2 assert 升级〕✓）——**R1 P2×5 全部闭环**：P2-1（records=recs+rels+uses 白名单方向+expand 入向+图断言；工件 relations=310/表 200/200/truncated/模板 10/10；depth2 P99 **16.301ms** 真实边图达标）✓、P2-2（bench5 零改动真复用+工件 1361.6/1074.6/1545.5+分段和自洽+三层口径重写+两数据并列不关 G-6 ✓）✓、P2-3（37 端点=34×403+webhook 401+search/uploads 403+未扫注记 ✓）✓、P2-4（三条真实路由 L216/L269/L885 全 404+「T15 延伸面」按 R1 裁定收口 ✓）✓、P2-5（backlog 口径 ✓——**issue 未实际创建，监督侧待办**）。**R2 三处代码级修复语义正确**：annotator Lock+哨兵序（单锁无嵌套无死锁/异常释放锁哨兵保持 None 可重试/AC 主路径零退化/持锁 3.75s 一次性成本语义正确）；create_org 必填+校验+pg 竞态映射（sqlite BEGIN IMMEDIATE 锁内预查竞态不存在论证成立；**P3 边界**：宽捕 UniqueViolation 含 audit_outbox PK 理论碰撞误报/org_admin 未校验 disabled_at——均 P3）；DashScope parameters.top_n（协议契约正确+live respected=true+Cohere 零影响）。**Tester R2 P3×6 裁定**：①m2-checklist:10 R1 快照旧值→修（docs 批覆盖 29 passed/37 端点/backlog）②G-8「零损失」→修（本集分辨率内未观测到）③④⑥矩阵报告 403/401 混述+旧名+计数边界→修⑤annotator 返回值冗余→可留。**补充新增 P3（报告勘误清单）**：perf05:25（0.048→工件 0.029）/g6:39（rps 3.62 无工件来源→按工件 4.61 或删）/matrix:16,23-27,47,49,53,62,65（全集标题/35 全 403/旧名/org_admin?/6 用例）/g8:30-33（零损失→严格口径）/test_az_matrix:202 docstring/matrix 行集 audit·grants 断言强度登记。**观察①裁定**：conftest teardown 吞错→test-infra 低优先 issue（下次测试基建批，不阻塞）。**docs 批终版清单**（A docs/：design §6.2 orgs 实装+dashscope 档+五方法 backlog 注记+停用缺口/TEST-CASES T15·TC-OPS-09·TC-AZ-04·TC-PERF-05 注记+§六 M2 行 m2-5 段〔验收句已清偿≠端点全集〕/known-gaps G-6〔1361.6 vs 2443.2 并列不关重开+召回段 halfvec 不引入+缺口维持+28-query 饱和态〕G-8〔分辨率限定+指纹维持〕G-7〔provider 入仓+top_n 生效〕G-24〔③④⑤划销+语义 gate 新条目〕/RUNBOOK 可选/AGENTS·_m2-plan 终态 M2 6/6）；B issue×4（§6.2 五方法/组织停用/语义 gate+annotate fuzzy 无界/conftest teardown）；C 报告勘误批（doc-only——**建议并入 docs 归档批**）。**manifest 要点**：双 SHA=d0d8bbe/rounds=2/verdicts/specRulings〔边界①a②③④+T15 非 CASE_BUG〕/gapClosures/handover/工件覆写注明〔m1-5-tc-perf-03 与 m2-5-rerank-live 两 JSON 为 R2 覆写〕。**结论**：APPROVED 无 R3 代码范围——残余全为文档级，随 docs 批/报告勘误落笔（doc-only commit 或随 docs 批，交付前最终 HEAD 复核）。报告全文见「最新验证意见原文」details 块（R2 Committer）。
- **双通过达成（2026-11-02 10:56，round=2 收敛）**：testVerdict=PASS + reviewVerdict=APPROVED，testedSha=reviewedSha=d0d8bbe1cdef1778198ea7bf609dbee7a00679f0=当前 HEAD——status=approved，待用户确认交付（交付序列：监督侧 docs 批+issue×4+报告勘误→coder chore 归档批〔含工作区 2 流程文件〕→push+PR→committer gh pr review→coder manifest 入 PR description→用户合入）。

- **交付执行（2026-11-02 11:09，用户确认交付「同意」，status 维持 approved→归档中）**：① 监督侧 docs 批落笔完成——design **v0.9.9**（§6.2 orgs 实装注记+实现状态注记块〔五方法 backlog #13/停用 #14/dashscope 档〕）；TEST-CASES **v1.9.13**（TC-OPS-09/T15/TC-AZ-04/TC-PERF-05 四用例完成态+版本行+§六 M2 行 m2-5 段——验收句已清偿≠端点全集）；known-gaps **G-6 v1.3/G-7 v2/G-8 v2/G-24 v2（③④⑤ 划销+新⑨语义 gate）**；RUNBOOK **§1.x 供应商切换**（百炼/env 示例/复跑命令）；AGENTS §1 M2 全部交付+M3 backlog；_m2-plan row 11 done+§二/§三/§五（M3 指引）；遗留事项节终态登记+原检查点回写（m2-6 三条勾选/m2-4 ④⑤+IdP/m2s-6 TC-PERF-05 勾选+followups 去向 M3/m1-1 rerank 勾选/m1-5 总注记）；报告勘误 14 处（matrix 6/checklist 4/perf05 1/g6 1/g8 1——按 R2 Committer §四 C 清单）；② **issue×4 创建**：#13 §6.2 五方法、#14 组织停用、#15 语义 gate（G-24⑨）、#16 conftest teardown；③ **pg 存量 7 schema 监督侧 DROP CASCADE 清理完成**（核对一致→残留 0）；④ Coder chore 归档批完成（11:13 报告，续接会话）：**`faead74`**（18 files +720/−59——docs 批+报告勘误+检查点×7〔m2-5 新入库+m1-1/m1-5/m2-4/m2-6/m2s-6/_m2-plan/m2-6 清偿回写〕+tests docstring 一行〔matrix:202 措辞〕）；doc-only 复核 ✓（git diff d0d8bbe -- src/ 为空）；origin/develop=d3dfdc0 无前进确认；**push 成功 1076f93..faead74**（三 commits：db52009/d0d8bbe/faead74）；**PR #17 已开**（base=develop，https://github.com/yq3/knowledge-lattice/pull/17 ，body 含交付摘要+Evidence Manifest 占位）。待办：Committer gh pr review 留痕 + Coder manifest JSON 入 PR description + 用户合入。
⑤ Committer PR 审查留痕完成（11:2x，续接会话）：`--approve` 因 GitHub 自审限制失败（PR 作者=gh 账号 yq3——沿 #2~#12 先例），回退 **COMMENTED 形态完整留痕**（review id `PRR_kwDOVZ9dhM8AAAABVaNMhw`，body 含 APPROVED 结论/R2 审查要点/faead74 doc-only 复核无夹带/残余登记/合人留给所有者）；**faead74 doc-only 复核通过**（src/ diff 为空、docs 批与 §四 A 清单一致）；留痕发现 3 处文档计数残留（az_matrix 11→9 用例/matrix GET 3→2+store 1/未扫 6→4）。⑥ Coder 交付收尾完成（11:22，续接会话）：监督侧修 2 处（TEST-CASES TC-OPS-09 注记+m2-checklist L10「9 用例×双后端」）+coder 修 2 处（tests docstring 未扫 4 条/matrix GET 2+store 1）→**勘误批 `d683da3`**（5 files +6/−6 doc-only，push 成功 faead74..d683da3）；**Evidence Manifest JSON 入 PR #17 description**（18 顶层键：双 SHA=d0d8bbe/deliveryHead 链 faead74→d683da3/gate 1715+1 明细/rounds=2 四轮 verdicts/specRulings 6 条/gapClosures/artifacts 覆写注记/sessions/issues #13~#16/handover/stale=false——回读双校验通过：原摘要零丢失+json.loads 可解析）。
- **交付完成（终态）（2026-11-02 11:22，status=done）**：PR #17 OPEN/**MERGEABLE**/CLEAN，4 commits=[db52009（R1）, d0d8bbe（R2）, faead74（chore 归档）, d683da3（交付勘误）]，base=develop——https://github.com/yq3/knowledge-lattice/pull/17 。**待用户合入**；合入后 M2 主线 6/6+语义轨道 6/6 全部收官（M2 里程碑达成宣告同候 TC-UI-01~04 手动走查——用户侧，含本段 B① 新形态）。本合入后续条目（mergeCommit/origin develop 前进）待合入后补记。
- **合入（2026-11-02 11:24，用户确认「合入」）**：**PR #17 MERGED**——mergeCommit `8b3515314edc8194249b891df19f3047a934bf38`（mergedAt 2026-11-02T03:24:04Z，merge 形态沿 #2~#12 先例、远端分支保留）。origin/develop 前进至 8b35153；develop_opencode 已 ff 同步。**M2 里程碑正式收官——主线 6/6（m2-1~m2-6+m2-5）+ 语义轨道 6/6（m2s-1~m2s-6），门禁 663→1715+1。**M2 达成宣告待 TC-UI-01~04 手动走查（用户侧唯一待勾，含 B① 新形态）；下一段 M3（backlog 池见 _m2-plan §三/§五）。本合入条目为勘误批 d683da3 之后的工作区改动（随下段 chore 归档批入库——沿先例）。

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

<details>
<summary>R1 Tester 报告全文（2026-11-01 23:13，ses_e686349f3ffel5L77mqunMleuO）</summary>

临时产物已清理，工作区只剩监督侧既有 3 文件（与开工时机械核验记录一致，非我引入）。以下为最终验证报告。

---

# task-knowledge-lattice-m2-5 · Tester R1 验证报告

**testedSha**: `db520097ac62fb53461733b4b6b322fccbada486`（= 待核验 SHA ✓，父 `d3dfdc0`，develop_opencode，未 push）
**testVerdict: PASS**（附 2 项 P2 申报口径发现，需 committer 裁定处置）

---

## 一、门禁独立复跑（不采信 coder 输出，本机全量重跑）

```
docker start lattice-pg; export LATTICE_PG_DSN=...; scripts/test_gate.sh
==== [pytest]   1708 passed, 1 deselected, 0 skipped (191s)
==== [pytest-O] 1708 passed, 1 deselected, 0 skipped (202s)
GATE PASS: pg 臂 632 全实跑（[pg] 参数化 598 + PG 专用 34）
```

- **申报值对账 ✓**：1708+1 双后端双模式 0 skipped，与申报逐字一致；收集期独立核数 `[pg]=598 + pg_* =34 = 632` ✓；1 deselected=manual 同基线口径 ✓（边界④成立）
- **+57 逐文件归因（实测 collect-only）**：test_az_matrix_m25 **18**（9×2）+ test_orgs_admin **6** + test_emb_08_dashscope **11**（6 provider+4 env 参数化+1 端到端）+ test_sem_g24_hardening **14**（7×2）+ test_qual_07_hardening **4**（2 单元单臂+1×2）+ test_auth_02 **+2** + test_auth_03 **+1×2=2** → **57 ✓ 对账闭合**
- **skip 核对**：0 skipped，无 skip 异常

## 二、逐项勾验

| 项 | 结论 | 证据 |
|---|---|---|
| **A1** | ✅ 全绿，扫描面申报字面属实但**非实现全集**（P2①） | SCAN_ENDPOINTS 实数 **33 条 org 路径 + search + uploads = 35** ✓；TC-OPS-09/T15/TC-AZ-04①③④ 断言与用例正文一致（含「权限校验先行 403 不泄露存在性」「双维度授权缺一不可」「过期即刻 403 不等清理」）；三组织行集边界真实（org:ops 独立造数+coverage/dims/datasets/语义面逐项断言互斥） |
| **A2** | ✅ 裁剪合理（裁定 ACCEPT） | M1 REST 面 122 条 app_env 系 sqlite 单臂为**历史事实**；store/core 层自 M0b 双后端参数化（test_matrix_* / test_pg_backend）；本段 az matrix `[pg]` 臂 18 条 = REST×pg 端到端载体（403 全扫+404 资源 id+400 grants+行集边界）。**注记**：此为抽样载体非全量等价——未来 pg 专属方言路径进入 REST handler 层时须补 pg 臂用例 |
| **A3/A4** | ✅ 报告↔JSON 工件逐值对账一致 | r@10 0.9286/1.0000、MRL 512/256 双后端 Δ=0.00pp、指纹 60 样本（3×20）全 1.0、bench8 并发 P95 588.9ms（申报带上限）、overlap 0.1152~0.5586（≈申报 0.12~0.56）、index 391MB ✓；10312 实体构造真实性（build_stats 全谱：concept 10000+column 300+scenario 10+aliases 25624+AC keys 25624）✓；**M1-5 真值 2443.2 未复现的处理得当**——两数据并存+差异超容器方差申报+建议维持现状口径留生产复测注记（边界② ACCEPT） |
| **A7** | ✅ | MockTransport 契约与监督侧探测结论**逐字段一致**（`input.{query,documents}` 嵌套 L73-74、端点 `/services/rerank/text-rerank/text-rerank` L68-70、`output.results[{index,relevance_score}]` L55-66）；env 覆盖 4 键参数化+端到端换供应商全链；未知档位 `raise ValueError` fail-closed（app.py else 分支）；联调=**脚本形态**（benchmarks/rerank_dashscope_live.py）不收集不进门禁——比 skip-if-no-key 更强的 fail-safe，满足任务原文「同等口径」；.env.example 三档位对照完整、默认值中立 ✓ |
| **A8** | ✅ | perf05 JSON 与报告逐值一致（0.063/0.010/0.041ms、fuzzy 首调 3752.4ms→稳态 0.307ms、same_instance=true）；10312 实体万级词典+300 列/10 场景高扇出真实构造；G-24③ 实现（`_embed_query_bounded`：query_embed_timeout_s 有界+breaker allow/record+`search.degraded` scope=search_entities，REST L448+MCP 双接线）④（懒构建+索引直读）⑤（vec_top 参数化端到端）代码与用例双核实 |
| **A5** | ✅ 缺陷形态真实构造 | NaN 经 `_VecStreamBackend` packed bytes 直注 numpy 边界（绕过 sqlite NULL 天然排除——docstring 说明 pg REAL NaN 真实存在）；池缩水 monkeypatch 第一遍 10 行/第二遍 3 行（注入③反向证实：换回旧口径→flagged 漏标红） |
| **B①** | ✅ 代码级核验通过 | playwright 脚本**未入库**（会话内自测——m2-3 TC-UI-02 先例同形态）；app.js 三断言语义在代码层全支撑：`expires={...existing}` 初始=库内值 / `_rowExpiresInput` 逐行独立输入框+oninput 写 `expires[key]` / 保存 `expires[k] ?? existing[k] ?? ""` 逐行读回；#gExpires 降级为新选行预填源 ✓；非门禁面（TC-UI 批）口径维持 |
| **B 其余** | ✅ | followup④ 双方言注入 poisoned `_outbox_insert` → RuntimeError 含 outbox+users 零残留；⑤ 两用例锁 MCP 忽略审计移 resolve_org 后（org 400 零混入）；P3×3 纯文案 diff 核实 |
| **A6/A9** | ✅ | blocked 报告诚实（待决-1/IdP 均「无记录不虚造」+结构就绪面指针）；m2-checklist 逐项给验收句→证据映射 ✓（数字笔误见 P3①） |

## 三、择型 8 条 / 边界 5 条裁定

**择型**：① /api/orgs 实装 **ACCEPT**（§6.2 L1121 表内载体、TC-AZ-04② 首任 org_admin 死锁解除端到端；安全性独立验证=成员行集过滤注入证伪红+404 同生共死零残留+审计同事务 org.created 入单一登记处+D16 不建账号；**注记**：POST 面 store 层 pg 臂无专项用例——GET 面 pg 臂经 az matrix 覆盖，P3⑥）② search.degraded+scope 复用 **ACCEPT**（§5.2 同源口径）③ >-1.5 有效列+NaN 钉 numpy **ACCEPT** ④ RuntimeError 最小侵入 **ACCEPT** ⑤ fixture sqlite 默认工厂/pg 注入 **ACCEPT** ⑥ accessState.expires 唯一真值源 **ACCEPT** ⑦ T15 grants **400** **有保留 ACCEPT——CASE_BUG 候选上报**：实现固定口径满足 T15 实质约束（绝不返回他组织资源、按端点固定、防孤儿授权语义更精确），但与用例正文「404 或 403」及附录 A-2 二分法字面矛盾——**需 committer 裁定改用例落字（含 A-2 附录第三分支）**，非实现缺陷 ⑧ text-embedding-v4:1024 **ACCEPT**（枚举内+仓库默认未动保持中立）

**边界**：① A2 裁剪 **ACCEPT**（理由见上）② 2443.2 两数据并存 **ACCEPT** ③ 合成向量口径局限 **ACCEPT** ④ 1 deselected=manual **ACCEPT**（实测同口径）⑤ l0 断言放宽 **ACCEPT**（他组织零泄露负向断言保持；正向面由 entities 端点断言+既有 TC-SEM l0 curated 用例覆盖——fake 同步源无 curated 条目技术上成立）

## 四、注入验证（4 组，全红→恢复，业务代码零接触）

edit 权限边界限定 tests/——注入以**测试侧 monkeypatch 构造缺陷形态 + 直接调用 coder 原用例函数**完成（临时文件跑完即删）：

| 注入 | 缺陷形态 | coder 用例反应 |
|---|---|---|
| ① GET /api/orgs 摘掉成员行集过滤 | `list_orgs_for_user`→委托 `list_all_orgs` | `test_get_orgs_member_sees_only_own_memberships` **AssertionError 红** ✓ |
| ② G-24④ 懒构建回归 | `__init__` 恢复无条件 `_ensure_fuzzy_built` | `test_annotator_fuzzy_lazy_build` **红** ✓ |
| ③ A5 池缩水换回修复前口径 | 旧版 `_crowding_means`（-1.0 哨兵+全列 mean+无 NaN 防御，diff 精确重建） | `test_recompute_pool_shrink...` **红**（漏标复现）✓ |
| ④ G-24③ 降级审计摘除 | `_audit_sem_vec_degraded`→no-op | `test_vec_layer_timeout...` **红** ✓ |

sqlite+pg 双臂注入全过（14 passed）。验证后业务代码 `git diff db52009 -- src/` **零改动** ✓，pg schema 无新增残留（存量 7 个历史 schema 未动）✓，gate.log 等临时产物已清理 ✓。

## 五、回归零弱化核验

- tests/ diff：8 文件 = 6 纯新增 + 2 增补用例 + test_admin_members.py 仅 docstring（-2 行无断言）——**零删除测试、零断言弱化、零 skip 新增**；1651 条旧用例全在且绿（1708−57=1651）✓

## 六、分级发现

**P1**：无

**P2**（需 committer 裁定，非功能/安全缺陷）：
1. **A1 扫描面申报口径**：「35 端点=M2 新增端点全集」字面不成立——实现共 ~43 条用户面路由，scan 外 6 条：**values POST**（m2-6 A4 新增面、任务原文「values CRUD」之 C——风险已由 test_admin_values 普通成员 403 同守卫缓解）、PATCH/GET quality-flags、documents POST（multipart 上传）、webhook（服务身份签名独立防线）、uploads PUT（凭证绑定独立防线）。全部与已扫端点共享 `_require_org_admin`/`resolve_org` 守卫或独立身份防线，实质风险低——建议下轮补扫 2~3 条或修订申报措辞。
2. **design §6.2 列明而实现缺失的 5 个方法组合**（历史缺口非 R1 引入，R1 仅申报了 /api/orgs 一处）：GET /members（成员列表）、POST /datasets、PATCH /datasets/{id}、POST /dimensions、PATCH /dimensions/{id}——与 §6.2 表及 B① UI 语义存在偏离面，建议开 issue 登记或 docs 批标注实现口径。

**P3**（记录级）：① report-m2-5-m2-checklist.md 数字笔误「1707+2 / +56」——实测 **1708+1 / +57**（交付申报与门禁实测均正确，仅报告行笔误）② rerank 联调延迟口径：报告 ~470ms vs 工件 `latency_ms_basic=196.6ms`（均在 timeout 1.0s 内，契约结论不受影响）③ bench8 并发 3 轮（399.7/587.2/588.9）仅末轮有 JSON 工件 ④ lookup.py `except (FutureTimeoutError, Exception)` 冗余（前者 ⊂ 后者，行为正确）⑤ store `create_org` 无 store 级双方言专项用例（POST×pg 组合未端到端——并入 P2① 补扫建议）

## 七、结论

**testVerdict: PASS**。门禁 1651+1→1708+1 独立复跑零回归、0 skipped；A1~A9+B 逐项勾验通过；择型 8 条 7 ACCEPT+1 有保留 ACCEPT（择型⑦ CASE_BUG 候选报 supervised-coding）、边界 5 条全 ACCEPT；注入证伪 4/4 红（守卫与修复真实有效）；回归零弱化。P2 两项与择型⑦需 committer 裁定后决定是否进 R2（均为文档/申报口径层，不动代码逻辑）。

**testedSha**: `db520097ac62fb53461733b4b6b322fccbada486`

**临时产物清理声明**：注入测试文件已删除、gate.log 目录已删、pg 无本轮 schema 残留、.env key 全程未读取/打印；工作区仅剩开工前既有监督侧 3 文件。

</details>

<details>
<summary>R1 Committer 报告全文（2026-11-01 23:26，ses_e6852a652ffe0LMwyPw9XbOUzd）</summary>

## 审查对象与基线核对

- **HEAD / testedSha**：`db520097ac62fb53461733b4b6b322fccbada486`（= `develop_opencode` HEAD，父提交 `d3dfdc0`，双 SHA 一致；无新增未提交代码）
- **本轮 diff**：`git diff d3dfdc0..db52009` 37 files +3245/−68，逐文件核对完毕
- **docs/ prototype 零触碰**：`git diff d3dfdc0 db52009 -- docs prototype` 为空 ✓
- **测试零弱化**：tests diff 8 文件 = 6 纯新增 + 2 增补 + 1 docstring；无 skip/xfail/删除用例/放宽断言 ✓
- **门禁**：采信 Tester 独立复跑 `1708 passed / 1 deselected / 0 skipped`（双模式），pg 臂 632=598+34；+57 逐文件归因与实测一致（18+6+11+14+4+2+2），不重复跑门禁
- **分层纪律**：core/semantic 与 core/docs 无新增方言 SQL；DashScope provider 落 adapters；auto_entities 仍钉 api/mcp ✓
- **交付证据**：`data/bench-results/*.json` 与本轮报告对账基本一致（下详）；reports ×6 入库 ✓

---

## 一、问题清单

### P1（阻塞）：无

安全面深审未发现 P1：`POST /api/orgs` sysadmin 门槛在 handler 首行、`GET /api/orgs` 普通用户走 `list_orgs_for_user`（成员行集注入证伪已红）、建组织 + 首任 admin + `org.created` 审计同事务、D16 不建账号（404 零残留）、store 双方言等价、审计 org_id/actor 经 payload 正确投影。

### P2（需 R2 修复）

**P2-1｜TC-PERF-05「高扇出图」证据整体失效（bench/report 双重错误）**
- `benchmarks/perf_m2_5.py:89-100`：`rels`（300 条 `has_column` + 10 条模板-场景关系）构造后**从未传入** `run_sync` / `FakeSourceAdapter`——`run_sync(..., FakeSourceAdapter("tc", recs), snapshot=list(recs))` 只传实体。实证：`data/bench-results/m2-5-perf05.json:20-25` `build_stats.relations=0`、`relations_by_type={}`、`orphan_nodes=10312`。
- 连带第二处错误：`perf_m2_5.py:91-96` 关系类型写成 `used_by`（白名单不存在，`constants.py:22` 为 `scenario→template "uses"`）；`:182-183` 模板根展开用 `expand=["uses"]` 方向也不对（模板根应走 `uses<` 入向或裸 `uses` 双向）。
- 因此 `get_entity depth=2` 的 0.041/0.034ms 是在**零边图**上测的空展开；`report-m2-5-perf05.md:8-10,20-22,25` 的「高扇出图/表扇出 300 列/模板 10 场景」与「全项达标」均不成立；m2-checklist `:11,22` 同样继承。
- **修法**：`FakeSourceAdapter("tc", recs + rels)`（并把 `snapshot` 同步为含关系）；模板关系改为 `scenario→template "uses"`；`get_entity(tpl, expand=["uses<"])`；重跑后断言 `nodes/edges/truncated`（300 列、fanout_limit=200 应 `truncated=True` 且 nodes≈200），再更新报告与 m2-checklist 数字。属 A8 验收证据缺项。

**P2-2｜A3「5 万档 N=5 并发 P95」口径错误——bench8 测的是 recall SQL 片段，不是 M1-5 的全链 search SLO**
- `benchmarks/bench8_g6_halfvec_50k.py:187-231`（`_q_exact`/`conc_bench`）只跑 `render_vec_recall_select` 的向量 SQL；而 M1-5 真值 2443.2ms 来自 `benchmarks/bench5_slo_perf03.py:256-269` 的 **`core.docs.retrieve.search()` 全配方**（embed 150ms + FTS/向量召回 + fuse + rerank 200ms，5 线程 12s）。
- `report-m2-5-g6-halfvec.md:20-28,37-43` 把两者称「同容器同口径」「M1-5 真值未复现」「SLO 2s 达标」——**不成立**。且 bench8 的 ACL 造数（`:139-140`，无维度/无 grants）比 M1-5 `bench_common.seed_corpus` 的双维度 ACL 简单，`recall_segments_exact` 的 264~289ms 与 M1-5 的 440/640ms 不是同一 workload，「双路召回预算达标」同样不能直接对照 M1-5。
- **修法**：R2 用 bench5 形态（或等价全链 harness）在 pg 5 万复跑 **N=5 full search P95**，与 2443.2 同口径对照；halfvec 档若无法在 backend 全链接入，就明确写「索引仅影响召回段、全链 SLO 未测/无收益」，撤回「达标/未复现」结论。报告/commit 消息/m2-checklist/检查点申报同步改口径。

**P2-3｜A1 扫描面漏 M2 新增端点，且报告宣称「M2 新增端点全集」**
- `tests/test_az_matrix_m25.py:149-186` `SCAN_ENDPOINTS` 33 条 org 路径 + search/uploads = 35，但任务 A1 明确要求的 **values CRUD 的 POST**（§6.2:1131，m2-6 A4 新增）未扫；语义面 `POST /semantic/yaml/webhook`（§6.2:1147，M2-S3）未扫。
- `benchmarks/report-m2-5-matrix.md:15-29` 标题/表头写「M2 新增端点全集」，与实际不符（Tester P2① 属实，不能仅靠修订措辞放过，因为 values POST 是任务书点名项）。
- **修法**：R2 至少补 `POST /dimensions/{dim}/values`（u_gl→org:tax 期望 403）与 webhook（期望 401——无签名 fail-closed）；`POST /orgs/{org}/documents`、`PATCH/GET quality-flags`、`PUT uploads` 可保留为「共享守卫/独立身份防线」注记（Tester 风险论证成立），但报告须列明未扫项与原因。

**P2-4｜T15 的 dimension id / value id 404 断言是「伪绿」——被测路由不存在**
- `tests/test_az_matrix_m25.py:258-268` 用 `GET /api/orgs/{org}/dimensions/{dim}/values/{val}` 断言 404；但该 GET 路由**不存在**（`api/admin.py` 只有 PATCH values），404 实际来自 `app.py:427` `app.mount("/", mcp_app)` 对未匹配方法的兜底，并非资源存在性判断。`dimension id` 同样无 GET/PATCH 单维度路由。
- 这直接削弱 T15「dimension id / value id 逐个调用」的验收证据（document id 三例是真实路由，成立）。
- **修法**：改用真实端点：`PATCH .../dimensions/{tax_dim}/values/{tax_val}` → 404（`admin.py:263-264` 真实路径）；`POST .../dimensions/{tax_dim}/retire` → 404（`admin.py:280-282`，无 confirm 只做 impact 查询、无副作用）；`POST .../dimensions/{tax_dim}/values` → 404（`create_dimension_value`）。并在 docstring 注明「design 无 GET 单维度/GET 单取值端点」的缺口。

**P2-5｜§6.2 列明的 5 个方法组合未实现，A9 勾验材料「M2 行无未清偿项」过度**
- `docs/design.md:1122,1126-1129,1131` 列出 `GET /members`、`POST/PATCH /datasets`、`POST/PATCH /dimensions`、`GET /dimensions/{id}/values`，实现均无（`api/` 路由全集实测仅 42 条）。Tester P2② 属实，且是**历史缺口非 R1 引入**。
- `benchmarks/report-m2-5-m2-checklist.md:30` 写「本段后 M2 行验收句无未清偿项」，与上述缺口矛盾；m2-checklist 是 A9 docs 批的直接输入，不能以该口径落笔。
- **处置**：本仓 issue 登记（建议标题「design §6.2 端点表与实现差异：5 个方法组合未实现」）+ docs 批在 design §6.2 增加实现状态注记、m2-checklist 改为「实现范围清单 + 未实现项 backlog」；**不在 R2 实装**（超出 A/B 范围，属新增管理面功能，需用户裁定）。

### P3（记录级，随 R2 顺手修）

1. **`benchmarks/report-m2-5-m2-checklist.md:35-37` 数字笔误**：1707+2/+56 与实测 1708+1/+57 不一致，且明细 11+14+6+2+2+6+18=59 自相矛盾（Tester P3① 属实）。
2. **`benchmarks/report-m2-5-g8-real-model.md:68` 延迟 470ms 与工件 196.6ms 不一致**（Tester P3②）；`:79-80` MRR 脚注「3/28 零召回 query 不计入 MRR 分母」与 `eval/metrics.py:31-37` 实际算法不符（MRR 含全部 28 query；真实差异来自 6 条双 label query 的 recall 分母，MRR=1.0 说明全部 query 首命中 rank1），会影响 docs 批口径，必须改。
3. **`benchmarks/rerank_dashscope_live.py:14-15` docstring 陈旧**：写「top_n 截断：服务端尊重」「错误模型名 404」，实测为 **忽略 top_n / 400**，与报告结论自相矛盾。
4. **`benchmarks/perf_m2_5.py` / report**：报告「别名 5,000」与 build_stats aliases=25,624 不符；`data/bench-results/m2-5-g6-halfvec-50k.json` 仅末轮工件而报告称「4 轮复测形态一致」（Tester P3③）——R2 保留多轮工件或在报告注明「仅末轮落盘」。
5. **`src/knowledge_lattice/core/semantic/lookup.py:91`** `except (FutureTimeoutError, Exception)` 冗余（Tester P3④）；无功能影响，可顺手简化为 `except Exception`。
6. **`src/knowledge_lattice/core/semantic/annotator.py:214-232` 懒构建并发时序**：`self.fuzzy_terms = term_rows` 先于 `_fuzzy_pinyin/_fuzzy_dels` 赋值；`get_annotator` 的实例被并发请求共享，另一线程在首次构建窗口内可看到「terms 已非空、索引仍为空」→ 该次 fuzzy 候选静默缺失；且无锁会重复构建（浪费 3.75s）。建议：先构建本地索引、先赋 `_fuzzy_pinyin/_fuzzy_dels`、**最后**把 `fuzzy_terms` 作构建完成哨兵（或加简单 Lock）。属时序/性能 hygiene，非数据损坏。
7. **`src/knowledge_lattice/adapters/reranker.py:128-129` top_n 放置**：DashScope 官方 text-rerank 的 `top_n` 通常在 `parameters` 下；实测「传 2 回全量 4」可能不是服务端忽略，而是位置不被识别。当前消费面 `retrieve._run_rerank` 请求全量，故无实际影响，但 Reranker 协议 `top_n` 对 dashscope 档可能恒无效。建议 live 脚本加 `parameters: {top_n: 2}` 探测；若生效则修 provider + MockTransport 用例，否则删除「未来网关支持时自然生效」表述并明示 no-op。
8. **`src/knowledge_lattice/api/admin.py:107-158` create_org 边界**：(a) `id/name` 无空值/格式校验；(b) `org_admin` 可缺省 → 产生**无任何管理路径的新组织**（sysadmin 无 membership，members POST 又要求本组织 org_admin，形成不可恢复死组织）；(c) pg 并发同 id 建组织：`BEGIN` 预查后 INSERT 的 UniqueViolation 未映射为 409，理论竞态会 500。建议 R2 将 `org_admin` 设为必填（或显式 400 拒绝缺省）、校验 id/name 非空、pg 捕获 UniqueViolation→OrgExistsError。
9. **semantic 查询面绕过指纹探针 gate（历史缺口）**：docs 检索在 `api/search.py:98` 传 `service.gate`，probe reject 时关向量路；`api/semantic.py:420-450` 的 `search_entities` 与 `annotator.py:774-786` 的 fuzzy vec 层均不看 gate，探针拒绝后仍用跨底模向量计算语义近邻，与 NFR-8/§5.2「查询侧向量路关闭」不一致。另 annotate fuzzy vec 仍走 `embed_timeout_s=30s` 同步嵌入、无 breaker/降级审计（G-24③ 只覆盖 search_entities）。建议登记 known-gaps（G-24 扩展或新 G-28），本段不实装。
10. **`src/knowledge_lattice/web/app.js:173,227,254,259` `accessState.fresh` 已成死状态**：B① 改为 `expires` 后 fresh 只写不读，注释仍描述旧语义；R2 删除或更新注释（避免后续维护误读）。
11. **测试质量小项**：
    - `tests/test_sem_g24_hardening.py:276-303` vec_top 端到端只断言 `<=1`，随机向量下 0 条也通过（恒真风险）；建议 monkeypatch `Annotator.annotate` 捕获 `vec_top` 或注入确定性 `vec_lookup`。
    - `:141-156` 成功路径未断言 `breaker._streak == 0`（record_success 复位未被验证）。
    - `tests/test_az_matrix_m25.py:387-422` docstring 宣称 stats/audit/grants export 行集，但实际只断言 coverage/dimensions/datasets/语义实体；建议补 stats/audit 断言或收窄措辞。
    - `:224-242` 测试名含「mcp_semantic_tools」但载体是 REST；`:320-321` 未使用 `_pg_db` import；`:270-275` grants 400 断言应标注为「T15 延伸面」而非「T15 按端点固定」（见裁定）。
12. **`tests/test_orgs_admin.py` 仅 sqlite 臂**：store `create_org` 的 pg 路径（BEGIN/rollback/audit 同事务）无直接用例（Tester P3⑤）；建议 R2 在 `tests/test_admin_members.py` 或独立 store 测试加 `[pg]` 一条（同时可覆盖 KeyError/OrgExistsError 回滚）。
13. **`src/knowledge_lattice/api/admin.py:1-27` 模块 docstring 未登记 GET/POST /api/orgs**；`benchmarks/report-m2-5-matrix.md:38` 把 grants 400 写成 T15 固定口径（见裁定）；`benchmarks/report-m2-5-perf05.md:8` 别名数错误。均属文档卫生。

---

## 二、需求边界问题（供上报，不交 coder 修）

1. **§6.2 端点表 vs 实现（P2-5）**：5 个方法组合未实现，而 M2 行已把管理面标 ✅；这是规格与实现的历史口径差，须用户/监督侧决定「issue 登记 backlog」或「补实装」。**建议登记 backlog，不阻塞 m2-5 收口，但 docs 批必须写明实现范围。**
2. **TC-PERF-05「annotate 整体 P99」是否含 fuzzy 向量层**：`perf_m2_5.py:165-177` 的 fuzzy 首调 3.75s 明确为一次性懒构建；若验收句把 fuzzy=true 的首次请求计入 P99，则 20ms 门不成立；若按热态/懒加载口径排除，则需在 TEST-CASES 注记。建议 docs 批补「P99 为稳态、懒构建首调单列」口径（与 AC 自动机 8.82ms 构建费同口径）。
3. **「组织不可删只能停用」无载体（P1-1）**：`orgs` 表无 status 列（`0001_schema_v1.sql:8-12`），也无停用端点；新 `create_org` docstring 引用该口径，但实际只能靠无 admin 组织「事实上废弃」。建议 issue/known-gaps 登记。
4. **语义向量路与指纹 gate 的 NFR-8 缺口（P3-9）**：docs 检索关向量路、语义面不关，属跨切面口径不一致；建议 known-gaps 登记，M3/独立补强批处置。

---

## 三、Tester 意见逐条裁定

### P2①（扫描面 35/43）——**采纳，必须 R2 补扫**
不是「仅修订措辞」可过：任务 A1 点名 values CRUD，`POST values` 必须在 scan 表内；`webhook` 因报告宣称「语义端点全集」也应补（期望 401，不是 403）。其余 quality-flags/documents POST/uploads PUT 可按 Tester 的共享守卫论证保留注记。

### P2②（design §6.2 列明 5 方法组合缺失）——**历史缺口，issue 登记 + docs 批标注，不实装**
- 本仓开 issue（建议：「§6.2 端点表与实现差异：GET /members、POST/PATCH /datasets、POST/PATCH /dimensions、GET values」）；
- docs 批在 design §6.2 加实现状态列/注记、TEST-CASES §六 M2 行与 m2-checklist 同步「实现范围 + 缺口登记」；
- m2-checklist `:30` 的「无未清偿项」必须改为「验收句已清偿 + §6.2 未实现项 backlog」。
- 不作为 R2 阻塞代码项（超出 A/B 范围）。

### 择型⑦ CASE_BUG 候选（T15 grants 400 vs 「404 或 403」）——**裁定：不是 CASE_BUG，无需改实现、无需改 TEST-CASES/A-2**
理由：
- T15 字面对象是「u_gl 对 **org:tax** 的 grant 端点」→ `/api/orgs/org:tax/members/.../grants`，`org_scoped` 成员校验先行 → **403**，已在 `SCAN_ENDPOINTS`（`tests/test_az_matrix_m25.py:156-158`）覆盖；
- coder 的 400 场景是「org:gl 路径 + org:tax 用户 id」，属 **m2-3 既有语义**「目标用户在本组织无有效成员关系 → 400 防孤儿授权」，不是跨组织资源口径，且 `replace_member_grants` 非本轮 diff 引入；
- 400 响应不含他组织资源内容，不违反 T15 实质约束。
建议 R2 仅把测试 docstring/矩阵报告 `:38` 改称「T15 延伸面（同组织非成员目标）」；**不建议**给附录 A-2 加第三分支（会把一个非跨组织场景写进 T15 的 403/404 二分规则，反而扩大混淆）。若 supervised-coding 认为需要，可作「口径补写」记在 T15 注记，但非必需。

### P3×5 逐条
| 项 | 裁定 | R2 处置 |
|---|---|---|
| ① m2-checklist 数字笔误 | 属实 | 改为 1708+1/+57，明细与 Tester 归因一致 |
| ② rerank 延迟 470 vs 196.6 | 属实 | 以工件为准改写（或补充轮次/时间戳；不得留两值无说明） |
| ③ bench8 仅末轮 JSON | 属实 | 报告注明「仅末轮落盘」，或循环保存 3 轮 |
| ④ `except (FutureTimeoutError, Exception)` 冗余 | 属实（无功能影响） | 顺手清理（P3） |
| ⑤ create_org 无 POST×pg 专项 | 属实 | R2 加 store 级 `[pg]` 用例（并入 P0/P2-1 修复批） |

---

## 四、择型 / 边界终裁（8 + 5）

**择型**：① `/api/orgs` 实装 **ACCEPT**（安全性复核通过；P3 边界见上）；② `search.degraded` + scope 复用 **ACCEPT**；③ `>-1.5` 有效列 + NaN 钉 numpy **ACCEPT**（哨兵 -2.0 与余弦下界论证成立）；④ RuntimeError 最小侵入 **ACCEPT**（P3-5 回滚语义不变，双后端用例成立）；⑤ fixture sqlite 默认工厂/pg 注入 **ACCEPT**；⑥ `accessState.expires` 唯一真值源 **ACCEPT**（`fresh` 死状态为 P3）；⑦ **非 CASE_BUG / ACCEPT 实现**（裁定见上，仅需措辞）；⑧ text-embedding-v4:1024 **ACCEPT**（枚举内、仓库默认未动）。

**边界**：① A2 裁剪 **ACCEPT**（抽样载体 + 双后端 store/core 历史事实；报告已申报「非全量翻写」）；② 2443.2 两数据并存——**PARTIAL ACCEPT**：如实并列数据正确，但「同容器同口径/未复现/SLO 达标」表述不成立（P2-2），R2 必须改口径或补全链复跑；③ 合成向量口径局限 **ACCEPT**（且须补 P2-1 的关系造数缺陷）；④ 1 deselected=manual **ACCEPT**（实测同口径）；⑤ l0 断言放宽 **ACCEPT**（负向零泄露保持，正向由 entities 端点 + 既有 TC-SEM l0 用例覆盖）。

---

## 五、实验报告结论审查（G-6/G-8 方向）

- **G-6 halfvec 不引入**：**召回段结论成立**（LIMIT1024 零收益、LIMIT64 overlap 0.12~0.56 欠召回；合成均匀向量最坏情形已申报；1024/64 索引耗时/体积齐全）。但「5 万 N=5 SLO 达标 / M1-5 2443.2 未复现」**不成立**（P2-2）——召回 SQL 片段 ≠ 全链 search SLO；halfvec 索引对全链 SLO 的影响未测。docs 批应写成「5 万档召回段数据 + 全链 SLO 未复测/待 R2」，不要把 G-6 重开条件直接关闭。
- **G-6 真实模型基线**：r@10 0.9286/1.0000 与工件一致；pg 1.0000 是 28 query 小集的**饱和态**，结论只能作「本轮初步证据」；docs 批不要以 28 query 关闭「双后端偏差 >2pp」重开条件（应写「本轮不成立，保留重开」）。MRR 脚注须先修（P3-2），否则 docs 批会抄错口径。
- **G-8 MRL**：服务端原生 dimensions 截断 512/256 双后端 0.00pp，方向成立；但 28 query 的分辨率约 3.57pp，「零损失」应写「本集分辨率内未观测到损失」，并保留 TC-EVAL-02（M3 完整集）复标——报告 `:39-40` 已自我声明，docs 批保留该限定。
- **G-8 指纹阈值**：60 样本全 1.0、维持 0.99/0.95 的依据成立；注明「同模型同端点确定性、跨版本漂移未建模」即可。
- **G-7 / rerank**：DashScope provider 契约实证与消费面零影响论证基本成立；需修 `top_n` 放置探测与脚本 docstring（P3-7/P3-3）。
- **§六勾验材料一致性**：m2-checklist 的 M2-S1/S3 TC-PERF-05 映射、M2 行跨组织映射正确；但 `:30` 的「无未清偿项」与 `:10/:11` 的高扇出表述须随 P2-1/P2-5 修正。

---

## 六、docs 批建议清单（supervised-coding 落笔）

1. **design §6.2**：`GET/POST /api/orgs` m2-5 实装注记（含 `org_admin` 参数与 sysadmin 专属）；DashScope provider 档位（`LATTICE_RERANKER=dashscope` + 原生 text-rerank 契约 + top_n 差异）；§6.2 五方法组合「未实现/backlog」状态注记（P2-5）；`orgs` 无 status 列的停用口径缺口（或以 known-gaps 登记）。
2. **TEST-CASES**：T15 注记（grants 400 为延伸面，非 403/404 二分规则变更）；TC-OPS-09/T15/TC-AZ-04 m2-5 完成态；TC-PERF-05 注记（G-24③④⑤ 收口 + 高扇出修复后数据 + 懒构建首调单列口径）；§六 M2 行 m2-5 段（含 B① 4/4、G-6/G-8 实测、rerank 百炼联调、配置切换）。
3. **known-gaps**：G-6（halfvec 不引入、召回段数据、全链 SLO 口径修正、真实模型基线 28-query 局限、M1-5 真值并列）；G-8（MRL 真实模型零损失 + 分辨率限定、指纹阈值维持 + 抖动底）；G-7（DashScope provider 入仓、top_n 差异、Cohere 重开条件仍有效）；G-24（③④⑤ 划销，登记 annotate fuzzy vec 无界/无 gate 的剩余面）；新增 §6.2 五方法组合与 org 停用缺口条目（或 issue 链接）。
4. **RUNBOOK**：可选补 rerank 供应商切换（dashscope/cohere env 示例）与 m2-5 实验复跑命令；不阻塞。
5. 建议 **issue**：§6.2 端点表差异（P2-5）、语义 vec 不随 probe gate 关闭 + annotate fuzzy 无界（P3-9）、组织停用无载体。

---

## 七、遗留事项去向建议

| 事项 | 去向 |
|---|---|
| §6.2 5 方法组合（历史） | 本仓 issue + docs 批注记；不并入 m2-5 R2 代码 |
| org 不可删只能停用无载体 | issue/known-gaps；M3 或管理面补强 |
| semantic vec 不随 gate 关闭 / annotate fuzzy 无界 | known-gaps（G-24 扩展或新条目）；M3 语义补强 |
| m2-5 P2/P3 修复 | R2（见下） |
| TC-UI-01~04 manual 走查 | 维持用户手动执行（不阻塞本段） |
| pg 存量 7 schema / 2 未入库流程文档 | supervised 侧既有待办（C 项） |

---

## 八、R2 范围建议（按优先级）

1. **P2-2 重做 A3 SLO**：pg 5 万 N=5 **全链 search** P95（bench5 形态）与 2443.2 同口径对照；halfvec 仅召回段则明确标注；重写报告 §① 结论、commit 消息口径、m2-checklist。
2. **P2-1 修 perf05**：关系造数接入 + `uses` 方向/类型修正 + 图形态断言（nodes/edges/truncated），重跑并更新报告。
3. **P2-3/P2-4 修 A1/T15**：scan 补 `POST values` + `webhook`（必要时 documents POST）；T15 dim/value 改用 `PATCH values` / `POST retire` / `POST values` 真实 404 路径；矩阵报告「全集」措辞与 T15 400 注记修正。
4. **P3 批量**：Tester ①~⑤ + 本报告 P3-1~13 中的文档/数字/测试小项；`annotator` 懒构建赋值顺序（最低风险代码改动）；`fresh` 死状态清理；create_org 空值/必填/pg 竞态（若时间允许）。
5. R2 后重跑门禁（预期只增不减、0 skipped），Tester 复验 P2 闭环后再交付。

---

## 九、结论

**reviewVerdict: NEEDS_CHANGES**

未发现 P1 与安全回归；`/api/orgs` 越权/审计/D16/双方言、DashScope provider 失败形态、G-24③④⑤、P3-7、followup④⑤、B①、env 覆盖、分层纪律均通过代码级核对。阻塞点集中在**验收证据口径**：TC-PERF-05 高扇出造数失效、5 万 N=5 SLO 口径错配、A1 扫描缺 M2 端点、T15 两个 404 断言伪绿，另 §6.2 历史缺口需 issue/ docs 批处理。上述 P2 修完后可预计 R2 收敛。CASE_BUG 裁定：**不是用例/实现缺陷，无需改 TEST-CASES/A-2**。

</details>

<details>
<summary>R2 Tester 报告全文（2026-11-02 10:49，ses_e686349f3ffel5L77mqunMleuO）</summary>

清理完成（3 个测试残留 DROP，存量 7 个 bench/eval 未动，与 R1 基线一致）。全部复验项完成，出最终报告。

---

# task-knowledge-lattice-m2-5 · Tester R2 复验报告

**testedSha**: `d0d8bbe1cdef1778198ea7bf609dbee7a00679f0`（= 待核验 ✓，父 `db52009`，17 files +540/−202 与申报一致）
**testVerdict: PASS**（P1 无、P2 无、P3×6 文档级残留）

---

## 一、门禁独立复跑

```
==== [pytest]   1715 passed, 1 deselected, 0 skipped (211s)
==== [pytest-O] 1715 passed, 1 deselected, 0 skipped (210s)
GATE PASS: pg 臂 633 全实跑（[pg] 参数化 599 + PG 专用 34）
```

- **申报对账 ✓**：1715+1 双后端双模式 0 skipped 与申报逐字一致；**+7 归因实测闭合**：test_orgs_admin 6→**11**（必填 1+空值参数化 3+pg store 竞态 1）+ test_sem_g24_hardening 14→**16**（thread_safe ×2）= **7** ✓；1715=1651+57+7 链式对账闭合；pg 参数化 598→599（+1=pg 竞态 store 级）✓；1 deselected=manual 同口径 ✓；0 skipped ✓

## 二、R1 Committer P2×5 修复闭环逐条勾验——全部 ✅

| 项 | 结论 | 关键证据 |
|---|---|---|
| **P2-1** | ✅ | perf_m2_5.py `records = recs + rels` 混入 run_sync ✓；uses 方向按白名单 scenario→template ✓；模板根 `expand=["uses<"]` 入向 ✓；图断言固化（表根 truncated=True + nodes 195..202 容差 + edges≥190；模板 ≥10/truncated=False——零边图回归守卫）；**工件实证**：build_stats relations=310（has_column 300+uses 10）、graph_shape nodes=200/edges=200/truncated=true、orphan_nodes 10000（表/列/模板/场景全部连图——语义自洽）、**表扇出 P99 16.301ms<50ms 真实达标**（R1 零边图 0.041ms 标作废）、模板 0.574ms、annotate 0.054/0.011 持平（词典识别与图无关佐证）；m2-checklist/perf05 报告同步 ✓ |
| **P2-2** | ✅ | **真复用 bench5**（`bench5_slo_perf03.py` 不在 R2 diff——历史脚本零改动 ✓）；工件 `m1-5-tc-perf-03-pg-50000.json`（Nov 2 10:20 复跑）：**C_full_n5 P95 1361.6ms / P50 1074.6 / P99 1545.5、rps 3.54、N=5 12s、pg-per-thread-conn(R3)、notice_assert 全净** ✓；单请求 C_full 911.4 + 分段 embed 160.9/recall 464.3/fuse 78.2/rerank 210.3——**分段和 913.7≈911.4 自洽** ✓；seed_elapsed 67s（seed_corpus 全量造数非 shortcut）✓；**g6 报告三层口径重写**（①bench5 全链 ②bench8 召回段 ACL 简化申报 ③真实基线）+ R1 错误表述显式撤回 ✓；**两数据并列+不关闭 G-6 重开条件** ✓；双路召回缺口维持（464.3ms 超 300ms 预算）✓；halfvec 全链档未测如实申报 ✓ |
| **P2-3** | ✅ | SCAN_ENDPOINTS **37**（+POST values 403〔任务书 A1 点名项〕+webhook 401 无签名 fail-closed 先行）；未扫注记+原因逐条列明（documents POST/quality-flags×2/uploads PUT——共享守卫/独立身份防线）；「非实现全集」措辞修正 ✓ |
| **P2-4** | ✅ | T15 三条**真实路由** 404（PATCH values/{val}/POST retire/POST values——对照 api/admin.py L216/L269/L885 路由注册**确认存在**；retire 无 confirm 只做 impact 查询零副作用）；R1 伪绿根因（GET 路由不存在→MCP mount 兜底 404）在 docstring 记录 ✓；design 无 GET 单维度/GET 单取值端点缺口按裁定①a 登记 backlog ✓；grants 400 改称「T15 延伸面」（R1 Committer 裁定非跨组织口径、不改 TEST-CASES/A-2——我的 R1 CASE_BUG 候选按此口径收口）✓ |
| **P2-5** | ✅ | m2-checklist 改「**验收句已全部清偿 ≠ 端点全集实现**——5 个方法组合 backlog（GET /members、POST/PATCH datasets、POST/PATCH dimensions；裁定①a 不实装、M3 管理面补强批）」✓ |

## 三、P3 闭环 + 新增代码审查——全部闭环

**我 R1 的 P3×5**：①m2-checklist 笔误 ✓（L40-43 改正 1708+1/+57→1715+1/+7 链）②rerank 延迟 ✓（以工件为准 196.6/360.3 双轮注明、~470ms 口头估计显式撤回）③bench8 末轮工件注记 ✓ ④lookup except 冗余 ✓（清理+注释留义）⑤create_org pg 专项 ✓（`test_store_create_org_concurrent_duplicate_pg`）

**Committer P3×13 重点核验**：
- **annotator Lock**（P3-6）✅：`threading.Lock`+双重检查+**哨兵赋值序**（fuzzy_terms 最后赋值——观察者见非 None 时索引必就绪）；**死锁审查**：单锁无嵌套、构建完成后哨兵快速路径不碰锁；**性能回归审查**：AC 主路径（fuzzy=False）不经过锁——R2 数据 0.054ms 持平佐证零退化；万级首建 3.75s 持锁期间并发 fuzzy 请求阻塞等待=语义正确（等首次构建完成、仅等一次）；8 线程 Barrier+0.15s 慢构建放大窗口+calls==1+哨兵异常双断言，用例形态真实
- **create_org**（P3-8）✅：org_admin pydantic 必填（422）+strip 空白 400+pg `UniqueViolation→OrgExistsError`（409）+rollback；**R1 用例兼容**：403/409 用例已同步补 org_admin 字段 ✓；**sqlite 竞态面评估**：sqlite create_org `BEGIN IMMEDIATE`（L2682）——事务开始即取写锁、预查在锁内，竞态窗口不存在，pg-only 映射**合理且完备** ✓
- **top_n parameters**（P3-7）✅：provider 改 `body["parameters"]={"top_n": top_n}`；MockTransport 断言 `body.parameters=={top_n:2}` ✓；live 复跑工件 **requested=2/returned=2/server_respects_top_n=True** ✓；**Cohere 档零影响**（仅 DashScopeReranker 请求构造，响应解析与 CohereCompatReranker 未触碰）✓
- **vec_top 捕获**（P3-11a）✅：monkeypatch spy 捕获 annotate 实参 vec_top==1/缺省==3 双向——恒真根除；**breaker 复位**（P3-11b）✅：_streak 预置 1→成功后==0
- **MRR 脚注**（P3-2）✅：对照 `src/knowledge_lattice/eval/metrics.py`——MRR=mean(RR) 含全部 query（零召回 RR=0 入分母）✓、recall@k=|top-k∩labels|/|labels| ✓；**数学自洽**：22 单 label 满命中+6 双 label top1 命中其一 → (22×1+6×0.5)/28=25/28=**0.8929** 与 recall@1 一致、MRR=1.0 ✓
- 其余：fresh 全引用清理（P3-10）✓、admin 文件头 docstring 登记（P3-12）✓、mcp_semantic_tools→semantic_entities_isolated_rest 名实（P3-11c）✓、_pg_db/sqlite3 死 import ✓、MRL「本集分辨率内未观测到损失」（+3.57pp 分辨率限定+28-query 饱和态+不关闭重开条件）✓、rerank live 脚本 docstring 400 修正 ✓
- 边界④（semantic 查询面绕过指纹探针 gate）= known-gaps 登记归监督侧 docs 批，R2 coder 无动作义务 ✓

## 四、注入验证（2 组，双后端，业务代码零接触）

| 注入 | 缺陷形态 | 结果 |
|---|---|---|
| **A：懒构建 Lock 摘除** | `_ensure_fuzzy_built` 替换为 R1 无锁+terms 先赋值序（slow_build 放大窗口） | thread_safe 用例 **红**（calls==8 重复构建）✓ |
| **B：pg UniqueViolation 捕获摘除** | monkeypatch `psycopg.errors.UniqueViolation` 为不匹配的 Exception 子类——except 跳过、BaseException 分支裸 re-raise | 竞态段**裸 `UniqueViolation: duplicate key value violates unique constraint "orgs_pkey"` 逃逸**（修复前 500 面）→ pg 竞态用例红 ✓ |

（注入 B 首版假类未继承 BaseException 触发 TypeError 干扰——修正后失败模式精确命中修复点。）验证后注入文件已删、`git status` 仅监督侧既有 3 文件、**业务代码零残留** ✓。

## 五、回归零弱化

- 「删除」的 2 个 def 均为**改名/重写**（`mcp_semantic_tools_isolated`→`semantic_entities_isolated_rest` 同断言体；`annotate_text_passes_settings_vec_top` 恒真断言→实参捕获强化）；被替换的 2 条 assert 均为**升级**非弱化 ✓
- R1 的 57 条新增用例 + R1 前 1651 条全在且绿 ✓；0 skipped ✓

## 六、分级发现（R2 轮）

**P1**：无　**P2**：无

**P3×6**（文档/卫生级，不阻塞）：
1. m2-checklist **L10** TC-OPS-09 行残留 R1 快照（「24 passed…35 端点含 M2 新增全集」）未随 R2 修订——与本文件 L40-43 及矩阵报告 R2 数据并存矛盾，**docs 批落笔时勿以此行旧值为准**
2. m2-checklist L20 G-8 摘要「截断零损失」未同步 g8 报告 R2 口径「本集分辨率内未观测到损失」
3. 矩阵报告 L23-24/L47「org 路径 35 条全部 403」与 webhook 401 混述（实际 34×403+1×401）
4. 矩阵报告 L49 用例名未同步 R2 改名（仍写旧名）
5. annotator `_ensure_fuzzy_built` 返回值赋本地变量未使用（无害冗余）
6. 矩阵报告「~43 条中已扫 37+未扫注记 6」计数边界含糊（枚举 4 个方法组合+sample GET；/api/orgs 专项是否计入未明）——数量级无误

**观察**：① conftest teardown `except psycopg.Error: pass` 静默吞 DROP 失败——本轮验证运行产生 3 个 `lattice_test_*` schema 残留（已由我按 conftest 同款 DROP CASCADE 清理，终态=存量 7 个 bench/eval 历史残留，与 R1 验收基线一致）；既有测试基建行为非 R2 引入，若常态化残留可考虑 teardown 重试/告警。② R1 时我上报的择型⑦（T15 grants 400）由 R1 Committer 裁定「非 CASE_BUG、不改 TEST-CASES/A-2，改称 T15 延伸面」——R2 已按裁定落实，口径闭环。

## 七、结论

**testVerdict: PASS**。P2×5 全部闭环（含两处 R1 证据失效的实质性重做——真实边图 16.301ms 与 bench5 全链 1361.6ms 同口径复跑，均以工件+形态断言实证）；P3 应修尽修闭环（含并发懒构建 Lock、create_org 竞态映射、top_n parameters 三处代码级修复，注入证伪 2/2 红）；4 条边界裁定按「登记/注记不实装」落实，归监督侧事项清晰；门禁 1715+1 双后端双模式 0 skipped 独立复跑一致；回归零弱化。剩余 P3×6 均为 benchmarks 报告文档措辞级，可随 docs 批或 r3 微调，不构成回退依据。

**testedSha**: `d0d8bbe1cdef1778198ea7bf609dbee7a00679f0`

**临时产物清理声明**：R2 注入测试文件已删除、gate.log 临时目录已删、本轮验证产生的 3 个 pg 测试 schema 已 DROP（存量 7 个历史 bench/eval schema 未动）、.env key 全程未读取/打印、工作区仅剩开工前既有监督侧 3 文件。

</details>

<details>
<summary>R2 Committer 报告全文（2026-11-02 10:56，ses_e6852a652ffe0LMwyPw9XbOUzd）</summary>

## reviewVerdict: **APPROVED**

R2 代码与验收证据面放行；剩余均为 **P3 文档级**（Tester R2 P3×6 + 本次复审补出的报告↔工件数字/措辞残留），不构成 R3 代码轮，随 docs 批 / 文档勘误落笔。

审查对象：`d0d8bbe`（HEAD = testedSha = reviewedSha 待审；父 `db52009`，`develop_opencode`，diff 17 files +540/−202）。已逐文件核对 R2 diff、更新后 5 份报告与 `data/bench-results` 工件、R2 新增用例；docs/prototype 零触碰（`git diff db52009..d0d8bbe -- docs prototype` 为空）；tests 无 skip/xfail/删除断言（2 个 def 为改名/重写、2 条 assert 升级）；门禁采信 Tester R2 独立复跑 `1715+1 / 0 skipped`，不重跑。

---

## 一、R1 意见闭环核验（P2×5 + P3×13）

### P2-1 高扇出造数失效 —— **闭环**
- `benchmarks/perf_m2_5.py:94-100`：`records = recs + rels` 传入 `FakeSourceAdapter`/`run_sync`；`:94-99` `uses` 方向改为白名单 `scenario→template`（R1 `used_by` 不在白名单）；`:183` 模板根 `expand=["uses<"]`；`:186-219` 图形态断言（表根 truncated=True、nodes 195..202、edges≥190；模板 ≥10、truncated=False）。
- 工件实证 `data/bench-results/m2-5-perf05.json:8,21-25,27,109-120`：`relations=310`（has_column 300 + uses 10）、表 nodes=200/edges=200/truncated=true、模板 nodes=10/edges=10/truncated=false；P99 表扇出 **16.301ms**、模板 0.574ms（R1 零边图 0.041/0.034 已标作废）。
- `report-m2-5-perf05.md`、`report-m2-5-m2-checklist.md:11` 已同步真实边图口径。
- **残留 P3**：`report-m2-5-perf05.md:25` 与 `m2-checklist:11` 的「零命中态 annotate P99 0.048ms」是 R1 旧值——工件 `m2-5-perf05.json:97-100` 为 **0.029ms**（仍远低于 20ms，不影响达标结论）；docs 批/勘误须以 0.029 为准。

### P2-2 SLO 口径错配 —— **闭环（口径语义正确）**
- `benchmarks/bench5_slo_perf03.py` **确实零改动**（R2 diff 无该文件）；工件 `data/bench-results/m1-5-tc-perf-03-pg-50000.json:61-102`：`C_full_n5` N=5/12s/pg-per-thread、**P95 1361.6ms / P50 1074.6 / P99 1545.5**、notice 全净；单请求 C_full 911.4ms、recall 464.3ms（双路召回缺口维持）。
- `report-m2-5-g6-halfvec.md:3-7,26-54` 已重写三层口径（① bench5 全链；② bench8 召回段 ACL 简化申报；③ 真实基线），显式撤回 R1「召回段=SLO/同容器同口径」；「1361.6 vs 2443.2 两数据并列、不关闭 G-6 重开条件、生产首部署复测」表述正确；halfvec 全链档未测如实申报。
- **残留 P3**：同报告 `:39` 写「rps 3.54（一致性校验 3.62 ✓）」，工件 `m1-5-tc-perf-03-pg-50000.json:95-97` 为 `rps=3.54`、`rps_consistency_check=4.61`——3.62 无工件来源，须按工件/实测 elapsed 解释（M1-5 报告同款错峰建连口径）或删除该括号校验值。

### P2-3 扫描面/「全集」措辞 —— **功能闭环，报告残留 P3**
- `tests/test_az_matrix_m25.py:161-163,196` 已补 `POST /dimensions/{dim}/values`（403）与 `POST /semantic/yaml/webhook`（**401** 无签名先行），scan 实为 **37 条**（35 条 org 路径 = 34×403 + webhook 401；search/uploads 403）。
- 未扫 6 条注记在测试注释与 `report-m2-5-matrix.md:29-34` 列明，测试 docstring 已写「非实现全集」。
- **残留 P3**：`report-m2-5-matrix.md:16` 标题仍写「M2 新增端点全集」；`:23-27` 与 `:47` 仍写「35 条 org 路径全部 403」（实际 34×403+1×401）；`:34`「已扫 37+未扫注记 6」与枚举 4 条不闭合；`tests/test_az_matrix_m25.py:202` 同样写「35 条 org 路径全部 403」。均为文档事实错误，修法见 §四 报告勘误。

### P2-4 T15 伪绿 —— **闭环**
- `tests/test_az_matrix_m25.py:271-286` 改用真实路由：`PATCH values/{val}`、`POST retire`（无 confirm 只做 impact）、`POST values`——三条在 `api/admin.py:216/269/885` 真实注册，均 404；document id 三例保持；`grants 400` 按 R1 裁定改称「T15 延伸面」（`:296-302`）。
- `report-m2-5-matrix.md:50` 已同步；无 CASE_BUG、无 TEST-CASES/A-2 改动。

### P2-5 §6.2 五方法组合 backlog —— **口径闭环（issue/落笔待 docs 批）**
- `report-m2-5-m2-checklist.md:29-36` 已改「验收句已全部清偿 ≠ 端点全集实现」并列出 5 个方法组合 backlog（GET /members、POST/PATCH datasets、POST/PATCH dimensions；裁定①a 不实装、M3 处置）。
- **残留 P3**：同文件 `:10` 仍是 R1 快照（「24 passed / 35 端点 / M2 新增全集 / 6 用例」），与 `:29-36` 矛盾——docs 批不得采用 L10，须覆盖为 **29 passed/37 端点/backlog**（Tester R2 P3①）。issue 尚未实际创建（supervised 侧待办）。

### P3×13 闭环情况
- 已闭环：m2-checklist §三数字（1708+1/+57→1715+1/+7）、MRR 脚注（`report-m2-5-g6-halfvec.md:101-105` 与 `eval/metrics.py` 算法一致：MRR 含全部 28 query、差异来自 6 条双 label 分母）、rerank 延迟（196.6/360.3 双轮工件、~470ms 撤回）、bench8 仅末轮落盘注记、lookup except 清理、`fresh` 死状态移除、admin docstring、`mcp_semantic_tools` 名实、`_pg_db` 清理、vec_top 实参捕获、breaker 复位断言、create_org pg 专项。
- **未完全闭环 / 新增 P3**：见 §三、§四（报告数字/措辞残留、annotator 未用返回值、create_org 宽捕 UniqueViolation、rowset 断言强度等）。

**P2×5 结论：全部闭环，无功能/证据面 P2 残留。**

---

## 二、R2 新增代码语义复审

### 1. annotator 懒构建 Lock + 哨兵赋值序（`annotator.py:205-250`）
- **正确性**：单锁无嵌套；`fuzzy_terms` 最后赋值——观察者见非 None 时 `_fuzzy_pinyin/_fuzzy_dels/fuzzy_stats` 必已就绪；双重检查防重复构建；构建异常释放锁且哨兵保持 None（下次重试）。**无死锁路径**；AC-only 主路径不经过锁，`perf05` annotate 0.054/0.011ms 持平佐证零退化。
- **持锁 3.75s 阻塞**：仅影响并发首次 fuzzy=true 请求，属一次性构建成本、语义正确（其余等待者等一次后复用）；P99 稳态口径之外单列已在报告注明——可接受。
- **P3**：`_build_fuzzy_locked` 返回 `(pinyin, dels, stats, term_rows)` 但调用方 `:230` 赋给未使用本地变量（Tester P3⑤）——无害冗余，可改为 `-> None` 或直接调用；并发用例的「中间态零可见」检查窗口较小（真正的 order 保护靠哨兵序本身），但 `calls==1` + 终态断言足以守住锁回归。

### 2. create_org 必填 + 空值 + pg 竞态（`admin.py:107-158`、`postgres/backend.py:3958-3996`）
- `org_admin: str` 必填（缺省 422）+ handler `strip` + id/name/org_admin 非空校验 400；R1 用例已同步（403/409 用例补 org_admin），TC-AZ-04 端到端仍绿；**API 兼容性**：POC 无既有客户端，设计/TC 未约定 optional，可接受，docs 批须落字「必填」。
- **pg UniqueViolation 映射**：`orgs_pkey` 竞态映射 `OrgExistsError→409` 正确；`user_org_memberships` PK 在新 org 下不可能撞；**唯一残余**：`audit_outbox` PK（uuid4 理论碰撞）也会落进该宽 `except`，被误报「组织已存在」——数据仍回滚、无安全影响，建议把捕获限定在 orgs INSERT 或按约束名判定（P3）。
- **sqlite 竞态论证成立**：`BEGIN IMMEDIATE` 在事务开始即取写锁、预查在锁内，不存在同 id 并发窗口；pg-only 映射合理。
- **P3**：`org_admin` 只校验存在性，不校验 `users.disabled_at`——指定已禁用用户仍会建出「无人可管」组织（sysadmin 无成员关系无法补）；建议后续 create_org 拒绝 disabled 用户（R1 P3-8 的剩余边界）。

### 3. DashScope top_n parameters（`reranker.py:124-131`）
- 与探测结论一致：`parameters.top_n` 生效（live 工件 `m2-5-rerank-live.json:24-30` requested=2/returned=2/respected=true）；`tests/test_emb_08_dashscope.py:77` 断言 `body.parameters == {"top_n": 2}`，None 时不携带；Cohere 路径零影响。**协议契约正确**，MockTransport 强度足够（请求体逐字段）。
- **P3**：R1 的 196.6ms 工件已被 R2 360.3ms 覆写（`data/bench-results/m2-5-rerank-live.json`）；报告 `report-m2-5-g8-real-model.md:69` 已记录两轮值，manifest 需注明工件覆写事实。

### 4. 矩阵/report 措辞
- 功能面正确；报告残留见 §四「报告勘误」——含 `org_admin?`（应为必填）、「6 用例锁定」（R2 为 11）、旧测试名、35/37 与 403/401 混述。均为 P3。

---

## 三、Tester R2 意见裁定

### P3×6
| # | 项 | 裁定 |
|---|---|---|
| ① | `m2-checklist:10` 残留 R1 快照（24 passed/35 端点/全集） | **修（文档勘误）**：覆盖为 R2 的 29 passed/37 端点/backlog；docs 批不得使用 L10 旧值 |
| ② | `m2-checklist:20` G-8 摘要「截断零损失」 | **修**：改「本集分辨率内未观测到损失（28 query≈3.57pp）」；`report-m2-5-g8-real-model.md:30-33` item 1 的「零损失」也建议同步为严格口径（item 3 已有定义） |
| ③ | 矩阵报告 34×403+1×401 混述 | **修**：`report-m2-5-matrix.md:16,23-27,47` 改「37 端点 = 34×403（org 路径）+1×401（webhook）+2×403（search/uploads）」；标题去「全集」 |
| ④ | 矩阵报告 L49 旧测试名 | **修**：改 `test_tc_ops09_semantic_entities_isolated_rest` |
| ⑤ | annotator `_build_fuzzy_locked` 未用返回值 | **可留**（无害冗余）或 hygiene 清理；不阻塞 |
| ⑥ | 矩阵报告计数边界含糊 | **修**：`~43 已扫 37+未扫 6` 改为枚举式「未扫 4（documents POST/quality-flags×2/uploads PUT）+ /api/orgs 专项另计」，不写不可闭合算术 |

**补充裁定（本次复审新增 P3，随同一文档勘误批）**：
- `report-m2-5-perf05.md:25`（0.048→工件 0.029）与 `m2-checklist:11` 的 0.048~0.054 范围；
- `report-m2-5-g6-halfvec.md:39` rps 3.62 无工件来源（工件 4.61/3.54）；
- `report-m2-5-matrix.md:53,62,65`（「+5 辅助用例」/「6 用例锁定」/`org_admin?`）按 R2 的 11 用例与必填字段更新；
- `tests/test_az_matrix_m25.py:202` 的「35 条 org 路径全部 403」表述；
- 三组织行集新增 stats/audit/grants export 断言方向正确但强度一般（audit 可为空、org:ops 无授权时 grants export 空也可通过；建议补 org:ops 授权造数或断言 events 非空/来源 org）——非阻塞，登记测试质量项。

### 观察①（conftest teardown 吞错）
- 属实：`tests/conftest.py:137-139` 的 `except psycopg.Error: pass` 会静默吞 DROP 失败，Tester 本轮清理 3 个残留 schema（存量 7 历史未动）。
- **处置建议**：不作为产品 known-gaps；开一条 **test-infra 低优先 issue**（teardown DROP 重试/告警，或失败时打印 schema 名），下次测试基建批处理；本轮不阻塞。

### 观察②（择型⑦ CASE_BUG 收口）
- Tester 确认按 R1 裁定「非 CASE_BUG、不改 TEST-CASES/A-2、改称 T15 延伸面」落实；**同意收口**。

---

## 四、docs 批终版清单（R1 §六修订版，supervised-coding 落笔）

### A. docs/
1. **design §6.2**：`GET/POST /api/orgs` m2-5 实装注记（POST sysadmin 专属、`org_admin` **必填**、D16 404/409、审计同事务）；DashScope provider 档位（`LATTICE_RERANKER=dashscope` + 原生 text-rerank + **`parameters.top_n`**）；§6.2 五方法组合「未实现/backlog」状态注记（GET /members、POST/PATCH datasets、POST/PATCH dimensions、GET values；M3 处置）；`orgs` 无 status 列的「停用」口径缺口（issue/known-gaps 指针）。
2. **TEST-CASES**：
   - T15 注记：grants 400 为「同组织非成员目标」延伸面，非 403/404 二分规则；dimension/value id 真实路由为 PATCH values/POST retire/POST values；design 无 GET 单维度/GET 单取值端点（backlog）。
   - TC-OPS-09：37 端点口径（34×403 + webhook 401 + search/uploads 403）；未扫 4 条共享守卫/独立防线注记；**不写「实现全集」**。
   - TC-AZ-04②：建组织 `org_admin` 必填；新 org_admin 端到端 201。
   - TC-PERF-05：真实边图（relations 310；表 200/200/truncated、模板 10/10；16.301/0.574ms）；P99 稳态口径、fuzzy 懒构建首调 3742ms 单列；annotate 命中态 0.054、零命中 0.029、AC 0.011/0.0。
   - §六 M2 行 m2-5 段：跨组织隔离全绿（TC-OPS-09/T15/TC-AZ-04）、TC-PERF-05、B① 4/4、G-6/G-8 数据、rerank DashScope/top_n、配置切换；**M2 行验收句已清偿 ≠ §6.2 端点全集**，五方法 backlog 注记。
3. **known-gaps**：
   - **G-6**：① bench5 全链 N=5 P95 1361.6ms（PASS）与 M1-5 2443.2ms **两数据并列、环境差异申报、不关闭重开条件**；② bench8 召回段 halfvec 不引入（LIMIT1024 零收益、LIMIT64 overlap 0.12~0.56、合成向量最坏情形局限、全链 halfvec 未测）；③ 双路召回缺口 464.3ms 维持；④ 真实基线 28-query 饱和态（3.57pp 分辨率，保留重开）。**报告 rps 3.62 须先按工件修正/删除后再落笔。**
   - **G-8**：MRL 真实模型「本集分辨率内未观测到损失」+ 3.57pp 分辨率 + TC-EVAL-02（M3）复标；指纹阈值维持 0.99/0.95（同模型确定性、跨版本漂移未建模）。
   - **G-7**：DashScope provider 入仓、`parameters.top_n` 实测生效、Cohere 重开条件仍有效；live 脚本不进门禁口径维持。
   - **G-24**：③④⑤ 划销；① ② ⑥ ⑦ ⑧ 余项保留；新增「语义查询面不随 probe gate 关闭 + annotate fuzzy vec 无界/无审计」条目（或 G-24 扩展），M3 语义补强。
   - **新增 issue/known-gaps**：§6.2 五方法组合 backlog；组织停用无载体；语义 gate/annotate fuzzy 无界。
4. **RUNBOOK**：可选补 rerank 供应商切换（dashscope/cohere env 示例）与 m2-5 复跑命令；fuzzy 懒构建首调 3742ms 的运行提示（可选）。
5. **AGENTS/_m2-plan**：M2 6/6 + 语义 6/6 完成态、m2-5 收口（门禁 1715+1）、下一段 M3；M2 行管理面「已交付 vs §6.2 backlog」注记。

### B. issue 清单（supervised 创建）
1. §6.2 端点表与实现差异：5 个方法组合（+ GET 单维度/单取值缺失）——M3 管理面补强批。
2. 组织不可删只能停用：`orgs` 无 status 列/停用端点——M3。
3. 语义 vec 不随 EmbeddingGate 探针关闭 + annotate fuzzy vec 无界/无 breaker/审计——M3 语义补强。
4.（低优先，test-infra）`tests/conftest.py` `_pg_db` teardown DROP 静默吞错。

### C. 报告勘误（benchmarks/，doc-only commit 或随 docs 批；不构成代码轮）
- `report-m2-5-m2-checklist.md:10`（R1 快照）、`:20`（G-8 零损失）、`:11`（0.048 范围）、`:43`（pg 臂计数口径）；
- `report-m2-5-matrix.md:16`（全集标题）、`:23-27,47`（403/401/35/37）、`:49`（旧测试名）、`:53,62,65`（org_admin?/6 用例）；
- `report-m2-5-perf05.md:25`（0.048→0.029）；
- `report-m2-5-g6-halfvec.md:39`（rps 3.62→工件 4.61 并解释错峰/删除校验值）；
- `report-m2-5-g8-real-model.md:30-33`（「零损失」→严格口径，与 item 3 一致）；
- `tests/test_az_matrix_m25.py:202` docstring（35 条全部 403）；
- 可选：`annotator._build_fuzzy_locked` 未用返回值清理；matrix 行集 audit/grants 断言加造数。

---

## 五、遗留事项去向

| 事项 | 去向 |
|---|---|
| §6.2 五方法组合 backlog | issue + docs 批 design/TEST-CASES 注记；M3 管理面补强批 |
| 组织停用无载体 | issue + known-gaps；M3 |
| 语义 gate / annotate fuzzy 无界 | known-gaps（G-24 扩展/新条目）；M3 语义补强 |
| Tester R2 P3×6 + 本次 P3 报告残留 | docs 批/文档勘误（C 节）；不阻塞交付 |
| conftest teardown 吞错 | test-infra 低优先 issue；下次测试基建批 |
| M1-5/R2 工件覆写（`m1-5-tc-perf-03-pg-50000.json`、`m2-5-rerank-live.json`） | 报告已记录两轮值；manifest 注明覆写事实；可选在新文件名下保留 R2 工件 |
| pg 存量 7 schema / 2 未入库流程文档 | supervised C 项既有待办 |
| TC-UI-01~04 manual 走查 | 用户手动执行（不阻塞本段） |
| `_m2-plan`/AGENTS 终态 | docs 批 |

---

## 六、evidence manifest 要点建议

- **SHA/分支**：`testedSha = reviewedSha = d0d8bbe1cdef1778198ea7bf609dbee7a00679f0` = HEAD；父 `db52009`；`develop_opencode`；`rounds=2 / maxRounds=3`；`testVerdict=PASS`；**`reviewVerdict=APPROVED`（R2 代码/验收面）**；docs 批后最终 HEAD 复核再执行 PR 留痕。
- **filesChanged**：并集 37（R2 17 文件均在 R1 清单内）；docs/prototype 零触碰；tests 零 skip/弱化（2 改名/重写、2 assert 升级）。
- **门禁**：`1715+1 / 0 skipped` 双模式；+7 = orgs 5（必填 1 + 空值参数化 3 + pg race 1）+ sem_g24 thread_safe 2（双后端）；链式 1651+57+7；pg 臂 guard `633=599+34`（**注**：`test_orgs_admin.py` 的 pg `pg_db` 用例不在该 guard 计数内，但实际执行且计入 1715；如需严格口径可写「pg-only tests all ran，guard 633」）。
- **specRulings**：边界①a（五方法 backlog 不实装）、②（P99 稳态 + fuzzy 首调单列）、③（组织停用 issue/known-gaps）、④（语义 gate known-gaps）；T15 grants 400 非 CASE_BUG、不改 TEST-CASES/A-2；R2 P3 处置表。
- **gapClosures**：P2-1~P2-5；A1 37 端点/A2 REST-PG 抽样载体/A3 全链 SLO/A4 G-6 三层/A5 P3-7/A6 受阻/A7 rerank+env/A8 TC-PERF-05 真实边图/A9 勾验材料；B① 4/4、followup④⑤、m2-6 P3×3；G-24③④⑤、G-6/G-8/G-7 材料。
- **关键工件**：`m2-5-perf05.json`（relations 310；graph 200/200/true、10/10/false；16.301/0.574；fuzzy 3742.4/0.303）、`m1-5-tc-perf-03-pg-50000.json`（1361.6/1074.6/1545.5，**R2 覆写**）、`m2-5-rerank-live.json`（top_n 2/2 respected、360.3，**覆写**）、`m2-5-g6-halfvec-50k.json`（末轮）、`m2-5-calib-{real,mrl,threshold}-*.json`；报告×6。
- **handover**：§四 docs 批 + issue 清单 + 报告勘误 + M3 backlog + test-infra + TC-UI。
- **交付前**：docs 批/勘误完成后，最终 HEAD 与 manifest 双 SHA 复核；再执行 `gh pr review` 留痕（合入动作不经手）。

---

## 七、结论

**reviewVerdict: APPROVED**

- R1 P2×5 全部闭环（P2-1 真实边图、P2-2 全链同口径 1361.6ms、P2-3 37 端点、P2-4 真实路由、P2-5 backlog 口径）；
- R2 三处代码级修复（annotator Lock+哨兵序、create_org 必填/校验/竞态映射、DashScope `parameters.top_n`）语义正确、用例与 live 证据到位；create_org 宽捕 UniqueViolation 与 disabled org_admin 为 P3 边界；
- 门禁 1715+1 双后端双模式 0 skipped 独立复跑一致；无 P1/P2 残留；
- Tester R2 P3×6 与本次复审补出的报告↔工件数字/措辞残留均为文档级，**不构成 R3 代码轮**：由 docs 批/文档勘误落笔（§四 B/C），交付前最终 HEAD 复核即可。

**无 R3 代码范围**；若用户希望任务 commit 本身零残留，可加一个 doc-only 勘误 commit（不含代码、不重跑门禁），否则随 docs 批处理。

</details>
