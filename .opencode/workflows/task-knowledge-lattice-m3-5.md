---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m3-5
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e3ab96740ffeWJ5p76jK5CMOdO
testerTaskId: ses_e3a984a73ffeTlm7yFWdhD04zz
committerTaskId: ses_e3a5b5156ffeM62rCLNsDxIVtN
status: approved
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: a96e606776593b00eb3112d967ff75599cf22fcc
reviewedSha: a96e606776593b00eb3112d967ff75599cf22fcc
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged:
  - .env.example
  - benchmarks/report-m3-5-g8-mrl-fullset.md
  - eval/reports/judge-human-answersheet-m35.jsonl
  - eval/reports/judge-materials-m35.jsonl
  - eval/reports/labeling-notes.md
  - eval/reports/m3-5-anchor-sampling-pg.json
  - eval/reports/m3-5-anchor-sampling-pg.md
  - eval/reports/m3-5-anchor-sampling-sqlite.json
  - eval/reports/m3-5-anchor-sampling-sqlite.md
  - eval/reports/m3-5-blocked-claims.md
  - scripts/eval_anchor_m35.py
  - scripts/eval_baseline.py
  - scripts/eval_corpus_m34.py
  - scripts/eval_judge_m35.py
  - scripts/eval_synth_m34.py
  - src/knowledge_lattice/eval/anchor_sampling.py
  - src/knowledge_lattice/eval/harness.py
  - src/knowledge_lattice/eval/judge.py
  - src/knowledge_lattice/eval/ragas_bridge.py
  - tests/eval_seed.py
  - tests/test_auth_03_sso_jit.py
  - tests/test_eval_anchor_m35.py
  - tests/test_eval_gate_m34.py
  - tests/test_eval_judge_m35.py
  - tests/test_eval_response_m35.py
endReason: null
createdAt: 2026-11-10T19:41:51+0800
updatedAt: 2026-11-10T22:29:58+0800
---

# task-knowledge-lattice-m3-5: 评测收口批（M3 末段）

## 任务原文

**M3 第 5 段（评测收口批——M3 末段）**——来源：_m3-plan row5（用户确认的段序 2026-11-02）+ m3-4 检查点移交（Committer P3×11 处置顺手批）+ design §8 M3 分解（judge 校准 / 在线锚点 / MRL 判据收口项）。

### A 组：TC-EVAL-03 judge 双语校准（主线）

用例原文（TEST-CASES）：~50 条人工双评 vs judge（内部网关）；一致率 / κ；**预期**：达阈值（阈值数值 M3 校准后定——附录 A-6）；judge prompt 双语。

1. judge 校准框架：双语（zh/en/mix 三态）judge prompt + 一致率/κ 计算管道；ragas_bridge 的 `build_openai_compat_ragas_llm` judge 接口已就位（m3-4 D 组），本段接通并出校准数据。
2. ~50 条人工双评材料：**人工双评部分用户侧协同**——coder 产出抽样/打标材料与格式（沿 m3-4 labeling-notes 先例），用户侧人工标注后回流入库；若用户侧协同受阻，先以框架+代行小样申报（沿 m2-5/m3-4 受阻先例，如实登记不冒充）。
3. 阈值数值：附录 A-6（judge 一致性阈值 M3 校准数据出来后定数并回写）——校准数据出来后由监督侧 docs 批落笔。

### B 组：响应层指标固化

faithfulness / answer_relevancy（ragas 响应层指标——ragas_bridge 已就位）：接入形态固化 + 响应层基线出数（可离线确定性部分进测试；真实 LLM judge 部分不进门禁）。

### C 组：TC-EVAL-05 在线引用锚点抽样

用例原文（TEST-CASES）：agent 会话引用 chunk_id 存在性抽样打标（引用不存在 ID = 幻觉证据）；**预期**：抽样管道出数、比例记录（记录级）。

1. 抽样管道：从查询审计（query_audit 月库——m3-2 交付）取 agent 会话引用 chunk_id → 存在性校验 → 打标出数。
2. 记录级交付：管道可运行 + 抽样报告归档（eval/reports/ 或 benchmarks/）；无真实 agent 会话则以构造会话/受阻申报形态如实登记（沿先例）。

### D 组：MRL 截断判据正式落笔（G-8 收口——m3-4 基线已出数）

m2-5 已有首次真实模型数据（百炼 text-embedding-v4：512/256 两档×双后端 28 query 本集分辨率内未观测到损失，分辨率 ≈3.57pp）；**「截断开放为可选配置」判据落笔归 M3 完整集**（60 query，分辨率 ≈1.67pp）——本段在 m3-4 双后端完整集基线（sqlite r@10 0.9167/MRR 0.8031、pg 0.8333/0.7213）载体上复测 MRL 截断对比并出判据材料；判据正式落笔（G-8 收口/known-gaps 回写）由监督侧 docs 批处理。

### E 组：待决-1 受阻申报更新 + TC-EVAL-02 LLM 占比收口

真实端点配额若恢复：LLM 候选复跑/增补（**补位不替换**——用户裁定口径 2026-11-09：三态覆盖达标 ≠ TC-EVAL-02 全部收口，真实 query/LLM 候选占比收口待 m3-5）；配额仍受阻则受阻申报更新（沿 m3-4 先例）。附录 A-6 待决-1 状态同步更新（监督侧 docs 批）。

### F 组：m3-4 移交顺手批（Committer P3×11 处置——m3-4 检查点遗留节权威）

1. **顺手批候选（本批处理）**：P3-2（eval_gate floor=None fail-open→完整性断言，删 `== floor` 冗余）；P3-7（聚合下限显式 raise/pytest.fail 使 -O 等强）；P3-8（per-query RR exact 冻结收紧——G-29③，确定性系统零成本）；P3-9（冻结表 vs 基线 JSON 自动同源校验轻量测试）；P3-6（ragas_bridge `retrieval_report_to_samples` docstring 与实现不符——本段接入时修，或改签名接收 golden 填 reference/user_input）。
2. **卫生登记（顺手/docs 批）**：P3-3（eval_baseline 头部用法/默认 label=m1 覆盖风险——改 usage/显式 label）；P3-4（eval_corpus_m34 脚本与数据不同源+「幂等」docstring+import sys）；P3-10（harness/eval_baseline 自称 M1、.env.example 补 LATTICE_EVAL_LLM_*、eval_synth field 未用、test_auth_03 硬编码密钥改引用常量）。
3. **裁定项 P3-1**（deepeval 分组 dev 组建议——维持现择型已注记 RUNBOOK §1.aa/G-29④，本段开工时裁定）。

### G 组：§六 M3 行总勾验 + M3 里程碑达成宣告（TC-UI 走查除外）

验收材料由 A~F 组产出；§六 M3 行总勾验、design §8 M3 完成态、AGENTS 状态行、_m3-plan 终态——**全部由监督侧 docs 批落笔**（coder 禁改 docs）；本组是交付时监督侧动作清单，不是 coder 任务。

### 开工时口径裁定预告（_m3-plan §二——任务确认时定，避免 spec_confirm 往返）

**judge 端点开发态形态**：design §7 L1250「judge 走内部网关」——开发态内部网关未就绪，是否沿 m2-5 百炼先例（DashScope OpenAI 兼容端点 qwen，`LATTICE_EVAL_LLM_*` env 零代码切换）？m3-4 时用户已裁定合成端点沿百炼先例，judge 端点同口径待确认；judge 联调/真实端点动作不进门禁口径沿用。

### 验收标准

1. **门禁零回归**：基线 **1898+1**（m3-4 交付后）双后端双模式 0 skipped、pg 臂收集数 >0；新增用例计入对账（judge 校准框架确定性用例/锚点抽样管道用例/F 组用例等）。
2. **TDD**：新行为红→绿证据；judge/锚点等 LLM 依赖面确定性可离线跑（不依赖真实端点——真实端点联调不进门禁，沿 m2-5/m3-4 先例）。
3. **分层纪律**：core 无方言 SQL；评测代码落 `src/knowledge_lattice/eval` + `scripts/` + `eval/`（沿 M1-4/m3-4 先例）；锚点抽样读审计月库走 store 层。
4. **coder 禁改** docs/requirements.md、docs/design.md 冻结正文与 prototype/；活文档（TEST-CASES/known-gaps/RUNBOOK——含 A-6 阈值定数、G-8 判据落笔、待决-1 状态）由监督侧 docs 批处理。
5. **分支纪律**：develop_opencode 本地 commit `[task-knowledge-lattice-m3-5] R<n>`，commit 前同步 origin/develop（当前=8bed157）。
6. **交付形态沿先例**：双通过→监督侧 docs 批（TC-EVAL-03/05 登记注记、A-6 阈值定数、G-8 判据落笔、待决-1 更新、§六 M3 行总勾验+达成宣告）→coder chore 归档批（含 m3-4 检查点交付条目后工作区改动）→push+PR base=develop→committer PR review→manifest→用户合入。
7. **依赖管理**：新增依赖走 uv；引入前确认 requires-python >=3.11 兼容；门禁不依赖外网。

## 需求确认
- [x] 用户已确认（2026-11-10 19:45「同意，本会话内subagent的调用无须询问我」——status=implementing；**会话级授权：本会话内 Task 调用免逐一预告确认**，沿 m3-4 先例）
- **开工时口径裁定（2026-11-10 用户确认）**：①judge 端点开发态形态=**沿 m2-5 百炼先例**（DashScope OpenAI 兼容端点 qwen，`LATTICE_EVAL_LLM_*` env 零代码切换；judge 联调/真实端点动作不进门禁口径沿用）；②人工双评协同=**双轨**（coder 产出 ~50 条双评材料与格式供用户侧标注回流为主；用户侧协同受阻时以框架+代行小样如实申报——沿 m2-5/m3-4 受阻先例，不冒充）；③P3-1 deepeval 分组=**维持主依赖择型**（RUNBOOK §1.aa/G-29④ 注记已落，无代码变更）
- 历史遗留事项清单：（supervised-coding 扫描历史检查点汇总，默认并入新任务，见 README §4.6）
  - **并入本任务**：m3-4 移交 m3-5（Committer P3×11 处置——顺手批候选 P3-2/P3-7/P3-8/P3-9/P3-6 + 卫生登记 P3-3/P3-4/P3-10 + 裁定项 P3-1，m3-4 检查点遗留节）→ 本任务 F 组；待决-1 LLM 候选复跑/增补（m3-4 检查点遗留节登记）→ 本任务 E 组
  - **不并入（去向已登记）**：G-28③ 生产 lifespan 接线残余 + PG 接线部署期复验（P3-5/P3-11+Tester P3-2）+ G-28①②⑥⑧ 开放点 → 部署期/触发时处置（m3-3 检查点遗留节维持）；m3-3 移交「后续 web/语义批」P3-1/3/4/7/8/9 → 后续批顺手级（非本段主题）；m3-4 移交「登记后续」P3-10 部分卫生项 → 本段顺手或 docs 批；TC-UI-01~05 人工走查 → 用户侧（不阻塞，M3 达成宣告唯一待勾——TC-UI 走查除外口径）
  - **m3-4 检查点遗留节回写待办**：「docs 已落」条目（G-29/G-6 v1.4/RUNBOOK §1.aa+§1.x——docs 批实际已完成）本任务收尾时 supervised-coding 补勾选

## 遗留事项（跨任务移交）
- [x] **本轮清偿（2026-11-10 双通过，SHA a96e606）**：m3-4 移交 P3×11 全清（P3-2/7/8/9/6/3/4/10 代码面+P3-1 维持主依赖〔用户裁定〕+P3-5/P3-11 docs 登记）；待决-1 LLM 候选复跑受阻申报更新（§E）。
- [ ] **配额恢复补跑小批（不新开里程碑——沿 m3-5-blocked-claims.md 复跑路径）**：A 组 judge 真实联调+校准+A-6 定数（用户侧人工标注回流后）；B 组响应层真实基线（应答来源口径 N-2=增强器主/构造辅）；E 组 LLM 候选增补（补位不替换）。
- [ ] **部署期登记（不阻塞）**：G-30 四项（真实 agent 部署时——应答引用采集入口/agent 标识·session/sampler actor_prefix 配置/TC-EVAL-05 复标——N-1 用户裁定 2026-11-10）；G-28③ 生产 lifespan 接线+PG 复验+G-28①②⑥⑧ 沿 m3-3 登记维持；G-6 真实语料复标（v1.5 偏差 3.33pp 维持观察）。
- [ ] **后续顺手批候选（M4 或独立 touch 批）**：Committer R1 P3×9（已闭合 P3-9 除外——anchor 口径注记/--db actor 硬编码〔G-30③ 承接〕/--pg flag/key_to_chunk 死代码/ragas_bridge 两处 docstring/test 未用导入/eval_seed 消费方计数）+R2-P3×3（calibrate 行序配对改 item_id join/守卫 fail-safe 边角/卫生 bundle）；G-29⑤ judge 判读词表残余（真实联调时记录解析误判率）；m3-3 移交「后续 web/语义批」P3-1/3/4/7/8/9 维持。
- [ ] **用户侧（不阻塞）**：TC-UI-01~05 人工走查（M1+M2+M3 达成宣告唯一共同待勾——N-4 受限宣告③项）；A 组人工双评标注回流（50 条 answersheet——材料与模板已入库，配额恢复后 --run-judge 出数）。
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1: coder 完成（2026-11-10 20:15 报告，全新会话，coderTaskId=ses_e3ab96740ffeWJ5p76jK5CMOdO，commit `05116a4` 于 develop_opencode，25 files +1968/−106，父提交=8bed157〔origin/develop 同步确认无前进〕，未 push；监督侧机械核验 ✓ HEAD/父提交/25 files/docs+prototype+.opencode diff=0）——**A** ✅ TC-EVAL-03 judge 双语校准框架（eval/judge.py 三态双语 prompt+两级判读词表解析+一致率/Cohen's κ+混淆矩阵；50 条材料+标注回流模板入库 judge-materials/answersheet〔三态 20/15/15、faithful/unfaithful 25/25、seed=20261110〕；门禁 10 用例〔κ 手算例 1/6 精确/退化约定/判读词表抗自由文本误命中〕）；**真实 judge 联调受阻申报**（chat 全档 403/429/404——m3-5-blocked-claims.md；无代行小样〔chat 受阻下 judge 无对照面〕）；**B** ✅ 响应层固化（ragas_bridge response_layer_rows→rows_to_ragas_samples：user_input=query/reference=黄金标注语料/response=被评应答+悬空键 fail-fast；60 条全链转换+offline self-check 实跑；真实 LLM 基线受阻申报）；**C** ✅ TC-EVAL-05 锚点抽样（eval/anchor_sampling.py：store 层 read_monthly_events 读月库+get_chunk 存在性校验；--demo 构造会话双后端出数归档〔sqlite 60 会话/312 引用/缺失 2=注入伪造 ID 如实登记〕；门禁 6 用例含 QueryAuditQueue→月库→抽样全链 e2e）；**D** ✅ MRL 复测真实调用（60q 双后端：512/256 两档 r@10 全 0.00pp〔分辨率 1.67pp〕、sqlite 256 档 MRR +0.84pp 正向波动；判据材料 benchmarks/report-m3-5-g8-mrl-fullset.md——判据正式落笔归监督侧 docs 批）；**E** ✅ 受阻申报更新（chat 配额维持耗尽，复跑路径补位不替换）；**F** ✅ 全清（P3-2 完整性断言删 fail-open+==冗余/P3-7 聚合下限显式 raise -O 等强/P3-8 per-query RR exact 冻结 60×2+tests/eval_seed.py 单一来源〔**择型：暴露并消除门禁 vs 基线环境名次面漂移——同环境化非例外清单**〕/P3-9 冻结表 vs 基线 JSON 自动同源校验/P3-6 retrieval_report_to_samples 改签名收 golden 清偿/P3-3 m1 档只读保护 --allow-m1-overwrite/P3-4 语料脚本与数据同源 34 篇机检 0 mismatch+一次性 docstring/P3-10 四项卫生/P3-1 维持主依赖无代码变更）。自测：TDD 红→绿（ModuleNotFoundError 预期红+两处迭代红）；**GATE PASS 1918+1**（基线 1898+20=judge 10+response 3+anchor 6+gate 同源 1；pg 臂 724=687 参数化+37 专用；双模式 0 skipped）；uv lock --locked 通过；4 条 warnings 为既有冷缓存现象（基线复现同款非回归）。**择型申报 6 条**（eval_seed 同环境化代价〔eval_gate 不再覆盖语料外命中面——仍由 test_eval_01_golden 覆盖〕/判读两级词表/材料构造三态等比+交替/demo 注入密度 1/5/P3-3 显式保护形态/受阻申报单文件）。**需求边界问题 3 条（报监督侧）**：①TC-EVAL-05「引用」数据源口径（审计月库现只采 search 返回 chunk_id〔系统返回必真〕——agent 最终应答中引用的 chunk_id 无独立采集入口，现以 agent actor 的 search 引用为锚点面；若需「应答引用」面需新增采集入口）；②B 组真实基线应答来源口径（增强器/agent 应答/构造应答未定——复跑时须标注）；③「人工双评」语义（现按 judge vs 人工对照〔answersheet rater 字段可容纳多位标注者〕；若验收口径要求「两位人工标注者互评 κ」为主指标需明示）。

- R1: tester **PASS**（2026-11-10 21:20 报告，全新会话，testerTaskId=ses_e3a984a73ffeTlm7yFWdhD04zz，testedSha=05116a4 复核一致）——门禁独立复跑 **GATE PASS 1918+1 双后端双模式 0 skipped**（pg 臂 724=687 参数化+37 专用 --collect-only 独立复核；+20 逐文件精确对账 judge 10+response 3+anchor 6+gate 同源 1；基线 8bed157 同条件 -O 实跑 1898+1 侧证）。逐组勾验 60+ 独立断言全过：A（材料 50 三态 20/15/15 等比+25/25 交替、build_materials 复跑逐条相等、κ=1/6 Fraction 精确复算+独立实现 200 随机例交叉、判读词表 16 应判+6 必 ValueError 对抗面全过含子串陷阱、受阻申报材料完整）B（response_layer_rows 60 条逐行核对、双 fail-fast 实证、offline_self_check 复跑、rows_to_ragas_samples 全链+P3-6 新签合同链 PASS）C（全链 e2e 双后端、demo 双后端 in-process 复跑 REPRO_MATCH=True、数字自洽 60×5+12 注入=312、伪造 ID 三处登记一致）D（工件与报告逐数字一致、Δ 全 0.00pp、1/60=1.67pp 复算、embeddings-cache 真实 API 产物在位）E（复跑路径在位）F 逐项（P3-2 形态三要素/P3-7 纯 python -O 绕 pytest 重写实证 RAISED+负向对照确认风险消除/P3-8 120/120 双表独立同源+eval_seed 三处消费+test_eval_01_golden 仍覆盖代价面/P3-9 注入实证 3/3 红→恢复绿→复账零残留/P3-6 docstring 一致/P3-3 拒绝路径 exit=1 实证/P3-4 34 篇 0 mismatch/P3-10 四项+test_auth_03 等值引用化非弱化/P3-1 pyproject 零改动=裁定一致）。回归零弱化（skip/xfail 新增 0、删除函数 0〔唯一 − 为签名改造重加〕、断言改动逐处核为增强）；分层（core diff=0、eval 零 SQL、store 协议方法）；禁区（docs/prototype/.opencode 0 字节、.env mtime 不变、25 files 零偏差、零残留）。warnings 4 条基线同条件复现同款——非回归 ✓。择型 6 条全同意。**需求边界 3 条独立意见**（①建议 known-gaps 登记「真实 agent 部署时新增应答引用采集入口+复标」用例正文暂不动②建议复跑路径定死主来源〔如增强器应答〕③answersheet rater 形态兼容两读、建议明示主指标口径）。**P1 无；P2 无；P3×4 登记**（①parse_judge_verdict 前缀表不含「答案」形态——重试兜底、真实联调留意解析失败率②eval_anchor run_demo mkdtemp 临时目录未清理〔卫生级〕③聚合前置 sanity bare -O 场景失效〔非门禁路径无动作〕④3× SyntaxWarning 基线既有后续顺手批）。报告全文见「最新验证意见原文」details 块（R1 Tester）。

- R1: committer **APPROVED**（2026-11-10 21:32 报告，全新会话，committerTaskId=ses_e3a5b5156ffeM62rCLNsDxIVtN，reviewedSha=05116a4=testedSha=HEAD 三一致；diff 8bed157..05116a4 25 files 逐文件核对与检查点 filesChanged 零偏差；门禁采信 Tester 独立复跑+静态对账独立复算〔冻结表↔基线 JSON 抽检/聚合下限推导复算/工件↔报告逐数字对读/+20 节点逐文件手工清点〕；docs/prototype/.opencode/pyproject/uv.lock diff=0 ✓；core diff=0 ✓；分支纪律 ✓）——F 组 11 项逐条核对全清（P3-2/7/8/9/6/3/4/10 已修、P3-1 维持裁定一致、P3-6 留 1 处措辞残留→P3-5）；A~E 组语义全 PASS（A 材料构造应答如实登记不冒充、受阻申报合规沿先例；B 悬空键 fail-fast+惰性导入；C 分层正确+注入伪造 ID 三处登记一致；**D 材料足以支撑 G-8① 收口落笔**〔「M3 完整集分辨率内成立」口径、未见夸大〕；E 复跑路径在位）；测试质量判别力确认（κ 手算精确/对抗面/全链 e2e/注入 3/3 采信）；回归零弱化独立核对（skip/删除=0、4 assert 删全换显式 raise=增强、test_auth_03 等值引用化已核 config.py:24）；warnings 非回归 ✓。**P1 无；P2 无；P3×10 登记**（①anchor「sessions」实为事件数/比例分母口径〔docs 注明〕②eval_anchor --db 硬编码 actor_prefix="agent:" 而现网审计 actor=裸 user_id——生产抽样会静默 0 会话〔**docs 批必登记**，与 N-1 同源〕③--pg flag 缺失〔部署期〕④key_to_chunk 死代码〔顺手〕⑤ragas_bridge docstring responses 措辞残留〔顺手〕⑥build_openai_compat_ragas_llm docstring「归 m3-5」过时〔顺手〕⑦test_eval_judge 未用导入/常量〔顺手〕⑧eval_seed docstring 消费方 2→3 处〔顺手〕⑨**--materials 无条件覆写 answersheet——用户标注后复跑会静默清空人工标签**〔双轨主路径数据丢失风险，建议顺手加非空拒写/--force 或 RUNBOOK 明示〕⑩判读长词表 faithful 任意位置命中——「not fully faithful」否定变体静默误判〔比解析失败危险，真实联调记录误判率/改 JSON 约束输出，A-6 复跑注记〕）。**Tester P3×4 裁定**（①并入 P3-10 复跑注记不动作②登记后续顺手批③不动作④登记）。**择型 6 条全同意**（附注：①代价面措辞「标准矩阵路径保留+聚合指标间接回归」勿写「直接覆盖」）。**需求边界问题 N×4（供上报不交 coder）**：N-1 TC-EVAL-05 数据源与 agent 身份口径（引用=返回面非应答面+actor 裸 user_id 无 agent 标识/session——建议接受返回面为 M3 锚点面+known-gaps 新 G-30+部署期 backlog，**需用户裁定**）；N-2 B 组应答来源口径（docs 批定死主来源=增强器应答+辅助构造应答）；N-3 人工双评语义（docs 明示主指标=judge vs 人工 κ、互评 κ 辅助——两标签文件可算）；N-4 **交付关键**：M3 达成宣告 vs TC-EVAL-03 真实校准受阻（A-6 待数）——建议按 m3-4 ◐ 先例受限句式宣告「M3 除 TC-EVAL-03 真实校准+A-6 定数、TC-EVAL-02 LLM 占比〔同因〕、TC-UI 走查外全部完成；受阻登记配额恢复补跑」，**若用户不接受受阻登记作完成态则 M3 保持未达成——需用户裁定**。**docs 批建议清单**（TEST-CASES v1.9.19 TC-EVAL-03/05/04/01 注记+known-gaps G-8① 收口/G-29③ 划销+④ 维持/G-6 v1.5 注记不关闭/新 G-30+A-6 待数+待决-1 更新+§六 M3 行〔N-4 句式待确认〕+RUNBOOK eval 脚本用法/MRL 复跑/data 工件不入库）；遗留去向（配额恢复补跑小批/部署期 G-30+TC-EVAL-05 生产面/后续顺手批 P3-1~10〔docs 必登记 P3-2、建议顺手 P3-9〕/用户侧 TC-UI）；manifest 要点（codeSha=05116a4、门禁 1918+1/+20 分解、rounds=1、caveats×5——真实 LLM 三组受阻+A-6 未定数/C 构造会话边界/D 工件 gitignored 不可从仓库复现/N-4 受限句式/TC-UI 未执行）。报告全文见「最新验证意见原文」details 块（R1 Committer）。

- **双通过达成（2026-11-10 21:32，round=1 收敛）**：testVerdict=PASS + reviewVerdict=APPROVED，testedSha=reviewedSha=05116a4c33e89de3fa006a4fc662f6b135d161b5=当前 HEAD——status=approved，待用户确认交付（交付序列：用户裁定 N-1/N-4 → 监督侧 docs 批 → coder chore 归档批 → push+PR base=develop → committer PR review → manifest → 用户合入）。**上报裁定点**：①N-4（交付关键）M3 达成宣告句式——受限句式〔受阻登记作完成态〕vs 维持未达成；②N-1 TC-EVAL-05 锚点面口径——接受「search 返回面」+G-30 登记 vs 其他；③Committer P3-9（answersheet 覆写风险）是否本轮 R2 顺手修 vs 顺手批/登记。
- **交付裁定（2026-11-10 21:45 用户「同意」）**：①N-4=**受限宣告**（「M3 除 TC-EVAL-03 真实校准+A-6 定数、TC-EVAL-02 LLM 占比〔同因配额受阻〕、TC-UI 人工走查外全部完成；①②受阻登记、配额恢复补跑」——沿 m3-4 TC-EVAL-02 ◐ 先例）；②N-1=**接受「search 返回面」为 M3 锚点面**+known-gaps 新增 G-30（应答引用采集入口+agent 标识/session 粒度——重开条件=真实 agent 部署）；③P3-9=**本轮 R2 顺手修**（answersheet 非空拒写保护）——round=2 修复轮启动，R2 双通过后进交付序列；N-2/N-3 由监督侧 docs 批定口径（N-2 主来源=增强器应答+辅助构造应答；N-3 主指标=judge vs 人工 κ、互评 κ 辅助）。

- R2: coder 完成（2026-11-10 22:00 报告，续接会话 ses_e3ab96740ffeWJ5p76jK5CMOdO，commit `a96e606` 于 develop_opencode〔父=05116a4=R1；origin/develop fetch 确认仍=8bed157 无前进〕，2 files +129/−6，未 push；监督侧机械核验 ✓ HEAD/父提交/2 files/docs+prototype+.opencode diff=0）——**P3-9 顺手修**：eval_judge_m35 `cmd_materials` 非空拒写守卫（answersheet 含人工标注〔label/rater 任一非空〕→ 拒写 rc=1+报错含标注行数+--force 提示+备份建议；--force 显式覆盖；**拒写原子化=materials 亦不写**〔防 --n 变更场景新旧 item_id 集合错位致 calibrate 对齐失真——择型申报 1 条：保护语义最小闭合〕；空模板/文件缺席路径不破坏；修掉首版 --force 误入 mutually-exclusive group bug——CLI e2e 抓出）+3 门禁用例（空模板可生成/非空拒写含标注原样保留+materials 不写原子断言/force 覆盖）。自测：TDD 红→绿（3 failed〔unexpected keyword 'force'〕→13 passed）；CLI 三路径端到端实证（rc 0/1/0）+git status eval/reports/ 零残留；**GATE PASS 1921+1**（基线 1918+3；pg 臂 724；双模式 0 skipped）。改动文件：scripts/eval_judge_m35.py、tests/test_eval_judge_m35.py（均已在 filesChanged）。

- R2: tester **PASS**（2026-11-10 22:15 报告，续接会话 ses_e3a984a73ffeTlm7yFWdhD04zz，testedSha=a96e606 复核一致，父链线性 8bed157→05116a4→a96e606）——门禁独立复跑 **GATE PASS 1921+1 双后端双模式 0 skipped**（pg 臂 724；1918+3 精确对账 judge 模块 --collect-only 13 tests；-O warnings 4→1 反向实证 R1 冷缓存暂态申报）。**P3-9 三路径 CLI/subprocess 级实证 15/15**（P0 缺席首跑双生成/P1 空模板 rc=0/P2 含标注拒写 rc=1+报错含 3 行计数+--force 提示+标注字节级原样保留+materials 原子不存在/P3 --force 覆盖 rc=0/E1 --materials --force 合法——首版互斥组 bug 修复实证/E2 互斥组仍生效；检测面「label/rater 任一非空」语义如实〔仅 rater 非空计入、纯空白不计〕；用例判别力内容级〔全量比对+原子断言非仅退出码〕；真实仓 Path A 附加实证 MD5 前后一致+git 残留 0 行）。**原子化择型同意**（守卫先于任何写盘→同代配对无错位中间态、--force 同步重建、最小闭合无过度保护）。回归面（增量恰 2 files、R1 25 files 零触碰、skip/删除=0、禁区 0 字节、未 push）。**P1/P2/P3 无新增**（R1 登记 4 条维持）。报告全文见「最新验证意见原文」details 块（R2 Tester）。

- R2: committer **APPROVED**（2026-11-10 22:20 报告，续接会话 ses_e3a5b5156ffeM62rCLNsDxIVtN，reviewedSha=a96e606=testedSha=HEAD 三一致，父链线性 8bed157→05116a4→a96e606；门禁采信 Tester R2 独立复跑+增量 diff 逐行静态审查）——**P3-9 闭环确认已闭合**（六要素逐项核验：检测面 label/rater 任一非空语义如实/报错含行数+--force+备份建议/--force 独立旗标不在互斥组+接线/拒写原子化守卫先于任何写盘/空模板缺席不破坏/--n 变更场景语义闭合——「R1 P3-9 数据丢失风险（含 --n 错位场景）完整关闭」）。**择型（原子化）同意**（唯一静默错位形态=materials 换新 item_id 集+sheet 旧集——守卫消除该中间态；最小闭合非过度保护）。范围纪律全过（增量恰 2 files、R1 25 files 中其余 23 零触碰 --name-only 核验、既有 10 用例零改动仅末尾追加、禁区 0 字节、skip/删除=0、+3 对账 1918→1921、pg 724 不变）；warnings 4→1 缓存暂态非回归（manifest 记 caveat）。**R2 新登记 P3×3（不阻断）**：R2-P3-1 cmd_calibrate _read_labels 按行序配对非 item_id join（等长不同序静默错配——R1 存量，下一顺手批改 join+集合校验）；R2-P3-2 守卫对解析失败行不计（非 JSONL/全损坏=fail-open 边角——next touch 改 fail-safe）；R2-P3-3 卫生 bundle（--force 与非 --materials 同用静默忽略/:52 局部 import json 重复/test 1/3 capsys 未用）。**终态 manifest 要点更新**：codeSha/testedSha=a96e606、rounds=2（全程无 FAIL）、门禁 1921+1（+3）、reviewedSha=交付 PR HEAD（须核 git diff a96e606..HEAD 仅 docs/检查点/监督侧文件）；caveats 增补（R2-P3-2 fail-open 边角+R2-P3-1 行序/--force 静默忽略+main() 接线由 CLI 实证覆盖/-O warnings 缓存波动/R1 全部 caveat 维持〔A/B/E 受阻+A-6 待数/C 构造会话+G-30/D 工件 gitignored/N-4 受限宣告/TC-UI 待用户〕）；specRulings 补录（N-4 受限宣告/N-1 返回面+G-30/P3-9 R2 顺手修/N-2 N-3 docs 批口径）；**docs 批增量**：RUNBOOK eval 用法补 answersheet 保护语义+labeling-notes 注 R2 保护一句；R1 docs 批其余项维持；R1 P3 残留清单剔除 P3-9（其余 P3×9+R2-P3×3 登记备查）。**放行：R2 双通过达成（round=2），可启动交付序列（用户裁定已齐 N-4/N-1/P3-9）**。报告全文见「最新验证意见原文」details 块（R2 Committer）。

- **R2 双通过达成（2026-11-10 22:20，round=2）**：testVerdict=PASS + reviewVerdict=APPROVED，testedSha=reviewedSha=a96e606776593b00eb3112d967ff75599cf22fcc=当前 HEAD——status=approved；交付序列启动（用户 2026-11-10 21:45 已预先确认「R2 双通过后进交付序列」）：①监督侧 docs 批（R1 §八清单+R2 §四增量）→②coder chore 归档批→③push+PR base=develop→④committer PR review 留痕→⑤coder manifest 入 PR→⑥用户合入。
- **交付执行①：监督侧 docs 批完成（2026-11-10 22:30）**——TEST-CASES **v1.9.19**（TC-EVAL-03 框架✅/真实校准◐ 受阻注记+TC-EVAL-05 观察项✅〔N-1 返回面口径+G-30〕+TC-EVAL-04 m3-5 增补〔RR exact/同源校验/clean env/fail-open 删除/显式 raise〕+TC-EVAL-01 clean env 澄清+m1 只读保护+TC-EVAL-02 仍受阻注记+A-6 待数〔受阻〕+§六 M3 行 m3-5 段+**M3 达成受限宣告〔N-4 句式〕**+依据行 G-1~G-30）；known-gaps **G-8 v3**（①收口——MRL 判据落笔 512/256 全 0.00pp/②维持）+**G-29 更新**（③划销+④裁定维持主依赖+⑤ judge 判读残余新增）+**G-30 新增**（TC-EVAL-05 数据面四缺口——N-1 裁定载体）+**G-6 v1.5**（真实模型 60q 偏差 3.33pp 维持不关闭）+总览表四行；RUNBOOK **§1.aa 扩充**（judge 三形态+answersheet 保护语义〔R2〕+响应层用法+anchor demo/db+MRL 复跑+data/ 工件不入库）；AGENTS §1 M3 全部交付✅+达成宣告句；_m3-plan row5 done+§二挂账终态+§三 M3 终态指引（配额恢复补跑小批/部署期/顺手批/用户侧四去向）；m3-4 检查点遗留节回写两条勾选（m3-5 P3×11 清偿+docs 已落核验）；labeling-notes R2 保护一句。工作区待 coder chore 归档批：docs 3 文件+AGENTS+RUNBOOK+_m3-plan+m3-4 检查点（回写）+本检查点（含交付条目）+labeling-notes。

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

<details>
<summary>R1 Tester 报告（2026-11-10 21:20，testVerdict=PASS）</summary>

# m3-5 R1 独立验证报告

## 结论

**testVerdict: PASS** —— 门禁独立复跑全绿、+20 逐文件精确对账、A~F 组逐项勾验通过、注入实证（P3-9 杀伤力 3/3 红+恢复绿）、-O 等强实证、基线同条件复现证实 warnings 非回归、回归零弱化/分层/禁区全核对通过。无 P1/P2 问题。

**testedSha: `05116a4c33e89de3fa006a4fc662f6b135d161b5`**（HEAD 复核一致，父=8bed157=origin/develop ✓；全程未 commit/push、未改仓库文件、注入实证零残留）

## 一、门禁独立复跑（不采信 coder 自报）

| 项 | 结果 |
|---|---|
| pg 臂收集数 | **724（[pg] 参数化 687 + PG 专用 37）> 0 ✓**（PG 专用 37 经 `--collect-only` 独立复核） |
| `[pytest]` 常规模式 | **1918 passed, 1 deselected, 0 warnings**（248.22s） |
| `[pytest-O]` | **1918 passed, 1 deselected, 4 warnings**（258.42s） |
| skipped | 双模式 **0 skipped**（gate 脚本 skip=失败拦截在位） |
| 基线对账 | **1898+1 → 1918+1 = +20 精确**：judge 10（8 函数，prompt 参数化×3）+ response 3 + anchor 6（2 个 matrix 双臂 + 2 纯函数）+ gate 模块 3→4（+1 同源新用例）——逐文件 `--collect-only` 独立清点 ✓ |
| 基线独立复测 | 8bed157 同条件 -O 模式实测 **1898 passed, 1 deselected**（基线树经 25 文件精确回退重建、PYTHONPATH 遮蔽验证基线代码生效）✓ |
| uv lock | `uv lock --locked` exit 0 ✓ |

## 二、逐组勾验（独立复跑/独立复算，共 60+ 项独立断言全过）

**A 组 ✓** 材料 50 条、三态 **20/15/15**（恰为黄金集 24/18/18 等比）、faithful/unfaithful **25/25** 交替构造；25 条 faithful 逐条 response⊂reference、25 条 unfaithful 干扰句形态逐条核实；`build_materials(seed=20261110)` 复跑与归档文件**逐条相等**；answersheet 50 行字段形态 `{item_id,qid,lang,label="",rater=""}` 且与材料三键对账；κ 手算独立复算（Fraction 精确：po=3/5、pe=13/25 → **κ=1/6**）+ 独立实现 200 随机例交叉一致 + 退化约定在测；判读词表对抗面 **16 例应判 + 6 例必须 ValueError（含 coder 迭代红的「自由文本含是」面）全过**，`unfaithful⊃faithful` 子串陷阱否定形优先实证；双语 prompt 三态注入实证。blocked-claims 申报材料与复跑路径完整在位（受阻本身按口径不复验、端点未触碰；无代行小样如实申报）。

**B 组 ✓** `response_layer_rows` **60 条逐行独立核对**（user_input=query 文本/reference=黄金标注语料拼接/contexts=命中序文本/lang/qid）；response 注入+缺省 None；悬空命中键与 qid 不在 golden 双 fail-fast 实证；ragas `offline_self_check` 复跑 exit 0（1.0/0.0 确定性断言）；`rows_to_ragas_samples` 60 SingleTurnSample 全链转换 + P3-6 新签名同链 PASS（eval 依赖组实跑）。

**C 组 ✓** 过滤口径（action/outcome/actor_prefix）+ store 层 `get_chunk` 存在性 + `read_monthly_events`（backend.py:1441）读月库全链 e2e（6 门禁用例双后端绿）；**demo 报告双后端 in-process 复跑 REPRO_MATCH=True**（sqlite 60/312/73/71/2/0.0274、pg 60/312/74/72/2/0.027）；数字自洽（60×5+12 注入=312；distinct=existing+missing 双后端吻合）；伪造 ID（`chk_agent_demo_fabricated_01/02`）与注入数 12 **如实登记**（常量+JSON 字段+md 清单三处一致）。

**D 组 ✓** 工件 `m2-5-calib-mrl-{sqlite,pg}.json`（mtime 11-10 20:06=交付时段）与报告表格**逐数字一致**；512/256×双后端 r@10 Δ 全 0.00pp、sqlite 256 档 MRR +0.84pp（=1/120，工件 deltas 字段吻合）；分辨率 1/60=**1.67pp** 复算 ✓；真实调用证据：embeddings-cache 三档文件（dimdefault=1024 维 float 向量×139 条）真实 API 产物在位；「真实模型 vs TokenBag 代理不可比」口径申报在场。

**E 组 ✓** blocked-claims §E 更新在位（补位不替换复跑路径写明）。

**F 组逐项 ✓**
- **P3-2**：完整性断言（冻结表 qid 集==golden，双表）替代 floor=None fail-open ✓、`== floor` 冗余删除 ✓、显式 raise ✓
- **P3-7**：**纯 `python -O`（绕开 pytest 重写）聚合下限失败路径实证 RAISED「MRR 聚合回退：0.0 < 0.75」**；负向对照：-O 下 assert 确被剥离（静默 exit 0）——风险面确认被显式 raise 消除
- **P3-8**：`_RR_FLOORS` exact 冻结 60×2 与基线 JSON **120/120 独立同源核对**；`_R10_FLOORS` 120/120；`_AGG_FLOORS`==round(基线−0.05,2) 双后端；`eval_seed.py` 单一来源（gate/baseline/anchor 三处消费核实）；**test_eval_01_golden 零改动仍覆盖语料外命中面**（L111 排除面机制核实）
- **P3-9 注入实证**：in-process 改冻结值 **3/3 变红**（rr q02/r10 q03/agg mrr 均出正确归因消息）→恢复→**GREEN**→字典↔JSON 复账零残留（全程零仓库文件改动）
- **P3-6**：新签名 `(report, golden, texts)` + docstring 与实现一致，ragas 全链功能 PASS
- **P3-3**：`--label m1` 无保护旗标 → **exit=1 + 提示文案**；历史档 mtime 未动；`--allow-m1-overwrite` 旗标在位；缺省 label=m3
- **P3-4**：`NEW_DOCS` 34 篇 ↔ corpus.jsonl **全字段同源 0 mismatch**；gk-en-m05 人工修正在库；「一次性」docstring 勘正；`import sys` 已删
- **P3-10 四项**：harness/eval_baseline 自称 M1 更正 ✓、.env.example 补 `LATTICE_EVAL_LLM_*` ✓、eval_synth 未用 `field` 删除（dataclass 仍用）✓、test_auth_03 密钥改 `DEFAULT_SSO_MOCK_SECRET` 引用（值与原字面量相同——非弱化）✓
- **P3-1**：pyproject 零改动=维持主依赖择型，与裁定一致 ✓

## 三、回归零弱化 / 分层 / 禁区

- **skip/xfail 新增 = 0**（grep diff 核实）；门禁双模式 0 skipped（脚本强制拦截）
- **删除测试函数 = 0**（唯一 `−` 为 test_tc_eval_04 签名改造，同名以 backend 形态重加）；断言改动逐处核：test_eval_gate_m34 为 P3-2/7/8 **增强**（fail-open 删除/exact 冻结新增/完整性断言新增），test_auth_03 等值引用化——**零弱化**
- **分层**：core diff = 0 行（core 零方言 SQL by construction）；eval 层三模块零 SQL；锚点读取走 store 协议方法 ✓
- **禁区**：`git diff 8bed157..05116a4 -- docs/ prototype/ .opencode/` = **0 字节** ✓；.env 未读未碰（不在 diff、gitignored、mtime 10-28 不变）✓；filesChanged 声明 25 = 实际 25 零偏差 ✓；工作区零残留（git status 与会话开始一致）

## 四、warnings 4 条既有现象核实

4 条 warnings **仅出现在 -O 模式**（常规模式 0）：PytestConfigWarning（-O 断言剥离告警）+ SyntaxWarning `\Z`×2（test_p3_followups_m1_4.py）+ `\ `×1（test_sem_expand_search_backend.py）——来源均为本 commit **未触碰**的 m1-4/m2s-3 时代文件。**基线 8bed157 同条件 -O 实跑复现完全同款 4 条**（1898 passed 侧证）→ coder 申报属实、非回归 ✓。

## 五、择型 6 条独立意见（均同意）

| # | 择型 | 意见 |
|---|---|---|
| 1 | eval_seed 同环境化 | 同意——RR 名次面漂移案例（q11 0.3333≠0.25）证明必要；代价面已核实由 test_eval_01_golden 覆盖 |
| 2 | 判读两级词表 | 同意——对抗面实测通过；残留「答案：是」形态走 ValueError→重试兜底（P3 登记） |
| 3 | 材料三态等比+交替 | 同意——20/15/15 恰等比、构造 25/25 实测 |
| 4 | demo 注入密度 1/5 | 同意——12/60 如实登记、比例非零非失真 |
| 5 | P3-3 显式保护 | 同意——拒绝路径实证 |
| 6 | 受阻申报单文件 | 同意——沿先例、三组汇总+复跑路径完整 |

## 六、需求边界 3 条独立意见（供监督侧裁定，不拍板）

1. **TC-EVAL-05「引用」数据源口径**：用例原文「agent 会话引用 chunk_id 存在性抽样」未指明采集入口——coder 申报属实（query_audit 现只采 search 返回 chunk_ids，应答侧引用无采集入口）。现交付语义偏「引用完整性/悬空检测」，「应答幻觉」证明力受限；与受阻形态（构造会话）组合下自洽不冒充。建议：known-gaps 登记「真实 agent 部署时新增应答引用采集入口+复标」，用例正文暂不动。
2. **B 组应答来源口径**：确属未定（申报已如实标注）。建议 committer 在复跑路径定死主来源（如增强器应答）+辅助（judge 材料构造应答），避免复跑时口径漂移。
3. **「人工双评」语义**：TC-EVAL-03 原文两读（judge vs 人工 / 两位人工互评 κ）。coder 按前者；answersheet 的 rater 字段形态**兼容两读**（两位标注者各标一列即可补算互评 κ，无返工风险）。建议监督侧明示主指标口径。

## 七、问题清单

- **P1（验收阻断）**：无
- **P2（应修）**：无
- **P3（登记）**：
  1. `parse_judge_verdict` 标签前缀表不含「答案」等常见 LLM 输出形态（ValueError→重试兜底；真实联调时留意解析失败率，按需增补前缀）
  2. `scripts/eval_anchor_m35.py run_demo` 的 mkdtemp 临时目录未清理（/var/folders 卫生级残留）
  3. test_eval_gate_m34 聚合前置 sanity（queries==60/corpus_docs==73）仍为 assert——pytest 重写下照常执行，仅 bare -O 直调场景失效；非门禁判定路径，无需动作
  4. 3× SyntaxWarning（`\Z`/`\ `）基线既有，可后续顺手批清理（非本段范围）

**verdict: PASS** · testedSha: `05116a4c33e89de3fa006a4fc662f6b135d161b5`

</details>

<details>
<summary>R2 Tester 报告（2026-11-10 22:15，testVerdict=PASS）</summary>

# m3-5 R2 独立验证报告

## 结论

**verdict: PASS** —— 增量聚焦验证全部通过：门禁 **1921+1** 双模式全绿 0 skipped、P3-9 三路径 CLI 级实证 15/15、拒写原子化择型成立、R1 25 files 面零触碰、禁区/父链/未 push 全核对通过。无新增 P1/P2/P3。

**testedSha: `a96e606776593b00eb3112d967ff75599cf22fcc`**（HEAD 复核一致，父=05116a4=R1；父链线性 8bed157→05116a4→a96e606；origin/develop 仍=8bed157，未 push ✓）。全程只读、仓库零残留（`git status` 与会话前一致——CLI 实证触及的 eval/reports/ 两文件 MD5 前后相同）。

## 一、门禁全量复跑

| 项 | 结果 | 预期 |
|---|---|---|
| pg 臂收集数 | **724（687 参数化 + 37 PG 专用）** | 724 ✓ |
| `[pytest]` 常规 | **1921 passed, 1 deselected, 0 warnings**（232.67s） | 1921+1 ✓ |
| `[pytest-O]` | **1921 passed, 1 deselected, 1 warning**（230.58s） | ✓ |
| skipped | 双模式 **0** | ✓ |
| GATE | **PASS** | ✓ |

**1921 = 1918+3 精确对账**：judge 模块 `--collect-only` 独立清点 **13 tests**（10 旧 + 3 新 P3-9 用例）✓。warnings 变化说明：-O 模式从 R1 的 4 条降为 1 条（仅 PytestConfigWarning）——R1 的 3 条 SyntaxWarning 因字节码缓存转热不再触发，**反向实证 R1「冷缓存现象」申报**（同代码热缓存下消失=缓存暂态而非代码回归；基线 -O 复现块中同样含该 PytestConfigWarning，非新增）。

## 二、P3-9 三路径实证（CLI/subprocess 级独立复跑，不经 coder 自报）

以 subprocess 真实走 `argparse`/`main()` 面（REPORTS 重定向外部临时目录，零仓库接触），**15/15 PASS**：

| 路径 | 实证 |
|---|---|
| P0 缺席路径首跑 | rc=0，materials+answersheet 双生成 ✓ |
| P1 空模板可生成 | rc=0；重建 6 行全空模板 + materials 同写 ✓ |
| P2 **含标注拒写** | **rc=1**；报错原文「已含人工标注 3 行（label/rater 任一非空）——拒写防静默清空；确认放弃标注请加 --force」；**标注文件字节级原样保留**；**materials 原子不写（不存在）** ✓ |
| P3 `--force` 覆盖 | rc=0；标注在档仍重建为 6 行空模板 + materials 写出 ✓ |
| E1 边界 | `--materials --force` 合用合法——**coder 自报的「首版 --force 误入互斥组」bug 修复实证**（当前 diff 中 --force 确为独立 add_argument）✓ |
| E2 边界 | `--materials --run-judge` 互斥组仍生效 rc=2 ✓ |

检测面细节核实：仅 rater 非空行（bob）计入、纯空白 label 行不计（探测 4 行计 3 正确）——「label/rater 任一非空」语义如实。**用例判别力核对**：仓库新增测试的拒写路径断言为**内容级**（`_sheet_rows(...) == annotated` 全量比对 + `materials 不存在` 原子断言），非仅退出码 ✓。

**真实仓 Path A 附加实证**：真 CLI 对真实 `eval/reports/` 执行 `--materials`（现库 answersheet=空模板）→ rc=0，两文件 **MD5 前后一致**（seed 确定性顺带再证）→ git 残留 **0 行** ✓。

## 三、原子化择型独立意见

**同意，语义正确闭合**：守卫位于任何写盘动作之前 → 拒写时旧 materials+旧 sheet 保持**同代配对**（不存在「sheet 被清、materials 仍旧」的错位中间态）；`--force` 场景两文件同步重建（含 `--n` 变更时 item_id 集合一致）；calibrate 按行数对齐的前提取回依赖 item_id 配对——本择型把「部分写入」这个唯一会造成静默错位的面关死了，是最小闭合实现，无过度保护（空模板/缺席路径不受影响，P0/P1 实证）。

## 四、回归面

- 增量 diff 恰 **2 files +129/−6**（scripts/eval_judge_m35.py、tests/test_eval_judge_m35.py），均已在检查点 filesChanged；R1 已验 25 files 面零触碰 ✓
- skip/xfail 新增 = **0**；删除测试函数 = **0** ✓
- docs/ prototype/ .opencode diff = **0 字节** ✓；未 push、origin/develop 无前进 ✓

## 五、P1/P2/P3（本轮增量）

- **P1**：无　**P2**：无　**P3**：无新增（R1 登记 4 条维持）

**verdict: PASS** · testedSha: `a96e606776593b00eb3112d967ff75599cf22fcc`

</details>

<details>
<summary>R1 Committer 报告（2026-11-10 21:32，reviewVerdict=APPROVED）</summary>

# task-knowledge-lattice-m3-5 · R1 Committer 审查报告

**reviewVerdict: APPROVED**
**reviewedSha: `05116a4c33e89de3fa006a4fc662f6b135d161b5`**（= testedSha = HEAD；父 = `8bed157` = origin/develop，未 push，本地 branch=develop_opencode）
**CASE_BUG 裁定请求：未收到**

> 执行环境说明：本会话 bash 仅 git 白名单（diff/status/log/show/rev-parse），无法独立复跑 pytest。门禁数值采信 Tester 独立复跑（1918+1 双后端双模式 0 skipped、pg 724=687+37），并以静态对账 + 独立抽查交叉验证（冻结表↔基线 JSON 抽检、聚合下限推导复算、基线树回退侧证采信 Tester、工件↔报告逐数字对读、+20 节点逐文件手工清点、skip/删除/断言放宽 grep、禁区/分层/分支核验）。交付阶段仍需复核 evidence manifest 双 SHA 与最终 HEAD 一致（见 §八）。

---

## 一、基线核对与上轮意见处置

- 首轮审查（reviewedSha 原为 null），审查对象 = `git diff 8bed157..05116a4`，25 files +1968/−106，与检查点 filesChanged 逐条一致（零偏差）。
- **m3-4 移交 F 组 11 项逐条核对（不因上轮已看过而跳过）**：
  - P3-2 完整性断言替代 floor=None fail-open + 删 `== floor` 冗余 → **已修**（test_eval_gate_m34.py:176-189，qid 集对称差显式 raise）。
  - P3-7 聚合下限显式 raise → **已修**（:208-216；Tester 以 bare `python -O` 绕 pytest 重写实证 RAISED，负向对照确认 assert 被剥离 → 风险消除）。
  - P3-8 per-query RR exact 冻结 → **已修**（`_RR_FLOORS` 60×2，对照基线 JSON；同环境化用 eval_seed 单一来源）。
  - P3-9 冻结表↔基线 JSON 自动同源校验 → **已修**（新用例 4 条：r10/rr 逐 qid + `round(基线−0.05,2)` 推导机检；注入实证 3/3 红采信）。
  - P3-6 改签名清偿 → **已修但留 1 处措辞残留**（见 P3-5）。
  - P3-3 m1 档保护 / P3-4 语料脚本同源 / P3-10 四项卫生 / P3-1 维持主依赖 → **已修/已裁定**（P3-1 pyproject 零改动，与用户裁定一致）。
- **禁区/纪律**：`docs/ prototype/ .opencode/ pyproject.toml uv.lock` diff = 0 字节 ✓；core diff = 0 行、新增 eval 层三模块零 SQL ✓；无新依赖、无 skip/xfail 新增 ✓；`.env` 不入 diff（gitignored）✓；分支/父提交/未 push ✓。

---

## 二、逐组语义审查结论

**A 组（TC-EVAL-03 judge 双语校准）— PASS（框架面）**
- `eval/judge.py`：三态双语 prompt（zh/en/mix 注入 + 中英双语指令）、两级判读（长词全文/短词末行，否定形先于肯定形——`unfaithful⊃faithful`、`不忠实⊃忠实` 子串陷阱处理正确）、一致率/Cohen's κ/混淆矩阵（空集与长度不齐显式拒；退化 pe=1 约定合理；κ=1/6 手算值正确）。
- 材料 50 条：三态 20/15/15（恰为黄金集 24/18/18 等比）、faithful/unfaithful 25/25 交替、seed 固定逐条可复现；answersheet 与材料三键对账、标签空位待人工（已核 answersheet 50 行 + 三态分布）。材料为**构造应答**（faithful=reference 连续句片段；unfaithful=语料内其他文档句）——已在 labeling-notes/blocked-claims 如实登记，不冒充真实应答。
- 真实 judge 联调受阻申报（chat 全档 403/429/404）**合规沿先例（m2-5/m3-4）**：材料与复跑路径写明、无代行小样（并说明「chat 受阻下 judge 无对照面」的诚实理由）、阈值归 A-6 未预设——不冒充 ✓。

**B 组（响应层指标固化）— PASS**
- `response_layer_rows`（user_input=query 文本 / reference=黄金标注语料文本 / contexts=命中序文本 / response 注入缺省 None）+ 悬空语料键双 fail-fast；`rows_to_ragas_samples` 惰性 ragas 导入（默认环境零 ragas 可导入）；60 条全链转换与 offline self-check 由 Tester 复跑通过。真实 LLM judge 基线受阻申报合规。
- P3-6 语义已由新测试真锁（user_input 不再是 qid、reference 非 None）——原陷阱面已消除。

**C 组（TC-EVAL-05 在线引用锚点抽样）— PASS（记录级/构造会话形态）**
- 分层正确：`read_monthly_events`（store 协议、月库链遍历）+ `get_chunk` 存在性 → 报告；core 零方言 SQL ✓。
- 构造会话链路 = 真实检索配方 + QueryAuditQueue 直写月库 + 读回抽样（6 门禁用例含双后端 e2e，QueryAuditQueue→月库→打标全链）；demo 出数 sqlite 60/312/73/71/2/0.0274、pg 60/312/74/72/2/0.027，数字自洽（60×5+12 注入=312；distinct=existing+missing 双后端吻合）。
- **注入伪造 ID 登记诚实**：常量 `FABRICATED_IDS`、JSON `fabricated_injected:12`、md「注入 12 会话」、missing=2 三处一致；`form=constructed_sessions` 明示非真实 agent 会话 ✓。

**D 组（G-8① MRL 判据材料）— PASS**
- `data/bench-results/m2-5-calib-mrl-{sqlite,pg}.json`（本机在位、真实 API 产物；embeddings-cache 三档文件在场）与 `benchmarks/report-m3-5-g8-mrl-fullset.md` **逐数字一致**：512/256 × 双后端 r@10 Δ 全 0.00pp；sqlite 256 MRR +0.84pp（=1/120 正向波动）；分辨率 1/60=1.67pp 复算成立；服务端原生 dimensions 截断（非客户端前缀代理面），口径申报「真实模型 vs TokenBag 不可比、合成语料未决」完整。
- **材料足以支撑监督侧落笔**：可在「M3 完整集分辨率内成立」口径下写 G-8① 收口 + 可选配置开放 + 真实语料部署复标；判据未见夸大（未宣称任意维度/真实语料零损失）。m2-5 28q 旧档数字仍保留在 `report-m2-5-g8-real-model.md`（同名 JSON 被覆盖，历史未丢）。

**E 组（LLM 候选复跑受阻更新）— PASS**：`m3-5-blocked-claims.md §E` 在位，补位不替换口径与复跑路径写明。

**F 组 — PASS**：11 项逐条处置正确；P3-8 的「门禁环境 vs 基线环境名次面漂移」暴露与消除（eval_seed clean env 单一来源）属正确工程判断；P3-9 同源校验用例判别力强（Tester 3/3 注入红采信）；P3-8 代价面（gate 不再覆盖语料外命中）**承接成立**——test_eval_01_golden 仍用标准矩阵（含 5 篇杂文档），若 harness 语料外命中过滤回归，聚合下限会红，属间接但有效的回归面；建议 docs 措辞不要写成「直接覆盖」，写「标准矩阵路径保留 + 聚合指标间接回归」。

**G 组**：属监督侧 docs 批动作，见 §八。

---

## 三、测试质量评估

- **+20 节点对账成立**：judge 8 函数（prompt 参数化 ×3 → 10 节点）+ response 3 + anchor 4 函数（2 个 matrix 双臂 → 6 节点）+ gate +1 = 20；pg 臂 +2（anchor 两个 matrix 测试的 pg 节点）→ 724 = 722+2，与申报一致。
- **判别力（非形式主义）**：judge 测试含 κ 手算精确值、退化约定、判读词表对抗面（自由文本含「是」必 ValueError、否定形优先）；anchor 测试含过滤三面 + 伪造 ID 缺失 + per-session 定位 + 真实审计链路 e2e；response 测试锁 P3-6 陷阱面与悬空键；gate 同源用例覆盖 120/120 + 聚合推导。**未见走过场**。
- **P3-9 杀伤力**：Tester in-process 改三处冻结值 → 3/3 红（含正确归因消息）→ 恢复绿 → 字典↔JSON 复账零残留，采信。
- **门禁审查**：diff 内新增 skip/xfail = 0；删除测试函数 = 0（唯一 `−` 为同名签名改造）；被删的 4 条 assert 全部替换为显式 raise（增强非放宽）；test_auth_03 仅等值引用化（`DEFAULT_SSO_MOCK_SECRET` 值与旧字面量相同，已核 config.py:24）。
- **4 条 warnings**：仅 -O 模式、来源为未触碰的 m1-4/m2s-3 文件，基线同条件同款——非回归 ✓。

---

## 四、问题清单

**P1：无 · P2：无**

**P3（登记，不阻断；标注意向处置）**

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| P3-1 | `src/knowledge_lattice/eval/anchor_sampling.py:26,87,92` | 「sessions」实为 accepted search **事件数**（审计无 session_id）；md「缺失比例（记录级）」实为**去重 ID 分母**（2/73），注入面按引用次数为 12/312=3.85% | docs 批注明口径（事件粒度/去重分母）；known-gaps 新条与 P3-2 合并登记 |
| P3-2 | `scripts/eval_anchor_m35.py:195`（另 :156） | `--db` 生产模式硬编码 `actor_prefix="agent:"`；而现网审计 actor 实为 `auth.user_id` 裸 id（api/search.py:135、mcp/server.py:397），无 `agent:` 前缀/session 标识（design §4 L484 注释形态未落地）→ 生产抽样会静默 0 会话 | **docs 批必登记**（否则 C 组生产面过度宣称）；后续顺手加 `--actor-prefix/--all-actors`；与需求边界 N-1 同源 |
| P3-3 | `scripts/eval_anchor_m35.py:15` | docstring 称 pg 生产月库经 `LATTICE_PG_DSN + --pg`，argparse 无 `--pg`；生产 pg 抽样无入口（--demo pg 是临时 schema） | 部署期补 flag 或改文档 |
| P3-4 | `scripts/eval_anchor_m35.py:116,126` | `key_to_chunk` 构建后未使用（死代码） | 后续顺手删 |
| P3-5 | `src/knowledge_lattice/eval/ragas_bridge.py:193` | 新 docstring 称「response 由调用方经 `responses` 注入」，但 `retrieval_report_to_samples` 无 `responses` 参数（P3-6 清偿后残留误导；实际入口是 response_layer_rows） | 下一顺手批改措辞或加参数 |
| P3-6 | `src/knowledge_lattice/eval/ragas_bridge.py:45` | `build_openai_compat_ragas_llm` docstring 仍写「接口先行……归 m3-5」（本段已接通） | 顺手改 |
| P3-7 | `tests/test_eval_judge_m35.py:20,30-31` | `GoldenCase` 未用导入、`EVAL_DIR_CORPUS/GOLDEN` 未用常量（与本段 P3-10 卫生纪律同族） | 顺手删 |
| P3-8 | `tests/eval_seed.py:9` | docstring 称消费方 2 处，实际 3 处（另有 scripts/eval_anchor_m35.py） | 顺手改 |
| P3-9 | `scripts/eval_judge_m35.py:49-63` | `--materials` 无条件覆写 answersheet；**用户标注后复跑会静默清空人工标签**（双轨主路径的数据丢失风险） | 建议顺手加「目标非空拒写 / --force」，或 RUNBOOK 明示标注前复制到 `data/eval-judge/` |
| P3-10 | `src/knowledge_lattice/eval/judge.py:47-49,91-94` | 判读长词表把 `faithful` 任意位置命中即正判：`not fully faithful` 这类否定变体会**静默判 faithful**（解析成功→不触发重试，比解析失败更危险） | 真实联调恢复时记录解析/误判率；建议改 JSON 约束输出或末行 exact；登记到 A-6 复跑注记 |

（Tester P3×4 的处置见 §六。其余观察：D 组工件在 `data/`（gitignored，不入 PR）——报告可持久、工件本地在位，manifest 需注明；m2-5 同名 MRL JSON 被 m3-5 覆盖，历史数字已由 report-m2-5-g8-real-model.md 保留，可接受。）

---

## 五、择型裁定（6 条）

与 Tester 一致，**全部同意（附注）**：
1. **eval_seed 同环境化**：同意——q11 RR 0.3333≠0.25 实证必要；代价面由 test_eval_01_golden 标准矩阵+聚合下限间接承接（docs 措辞避免「直接覆盖」）。
2. **判读两级词表**：同意——对抗面实测；残留见 P3-10/Tester P3-1。
3. **材料三态等比+交替**：同意——20/15/15 恰等比、25/25；docs 需写明材料为构造应答。
4. **demo 注入密度 1/5**：同意——12/60 如实登记；建议 docs 写清「缺失比例=去重分母」。
5. **P3-3 显式保护**：同意——拒绝路径实证（`--out` 可绕属显式操作，可接受）。
6. **受阻申报单文件**：同意——沿 m2-5/m3-4 先例，三组汇总+复跑路径完整。

---

## 六、Tester P3×4 裁定

| Tester P3 | 裁定 |
|---|---|
| ① `parse_judge_verdict` 前缀表缺「答案」→ ValueError→重试兜底 | **登记，不动作本轮**——真实联调时按解析失败率增补；并把 P3-10（静默误判变体）并入同一条复跑注记 |
| ② `run_demo` mkdtemp 未清理 | **登记**——后续顺手批（与 P3-4 等同批） |
| ③ 聚合前置 sanity bare -O 失效（非门禁判定路径） | **不动作**——pytest 重写覆盖，同意 Tester |
| ④ 3× SyntaxWarning 基线既有 | **登记**——后续顺手批，非本段范围 |

---

## 七、需求边界问题清单（供上报，不交 coder 修）

**N-1（需用户裁定，低争议，建议默认项）TC-EVAL-05「引用/在线」数据源与 agent 身份口径**
用例原文「agent 会话引用 chunk_id 存在性抽样」未定义采集入口。事实：查询审计现只采 search **返回** chunk_ids（系统返回即真，仅删除漂移会悬空），agent 最终应答引用无采集入口；且审计 actor = 裸 user_id，**agent 标识/session id 均未落地**（coder① 只说了引用面，未覆盖 actor 面）。现交付以构造会话 + 注入伪造 ID 演示判定面，自洽不冒充。**建议**：接受「search 返回面」为 M3 锚点面 + 用例正文暂不动；新增「应答引用采集入口 + agent 标识/session 粒度」入 known-gaps（新 G-30）与部署期 backlog；用户确认后 docs 批落笔。

**N-2（docs 批可自行裁定）B 组真实基线应答来源口径**
未定属申报如实。**建议**：docs/RUNBOOK 定死复跑主来源=增强器应答（被评对象），辅助=构造应答（judge 材料，如实标注）；不阻塞 M3。

**N-3（docs 批可自行裁定）「人工双评」语义与主指标**
两读（judge vs 人工 / 两位人工互评 κ）。answersheet 单行 rater 形态实际以「两标签文件」补算互评 κ（可行但非「两列」）。**建议**：docs 明示主指标=judge vs 人工 κ（用户侧标注回流），互评 κ 为可靠性辅助；A-6 阈值待数。

**N-4（需用户裁定——**交付关键**）M3 达成宣告 vs TC-EVAL-03 未验**
§六 M3 行含「judge 一致性达标：TC-EVAL-03」，而真实 judge/κ/阈值因 chat 配额受阻无法出数（A-6 待数）。**建议**：按 m3-4 TC-EVAL-02 的 ◐ 先例，宣告「M3 除 ①TC-EVAL-03 真实校准数据+A-6 定数、②TC-EVAL-02 LLM 候选占比（同因）、③TC-UI 人工走查外全部完成；①②受阻登记、配额恢复补跑」；**若用户不接受以受阻登记作为完成态，则 M3 保持未达成**——请监督侧原样上报裁定。

---

## 八、交付前置清单（给监督侧）

### docs 批建议清单
1. **TEST-CASES v1.9.19**：
   - TC-EVAL-03：新增「框架 ✅ / 真实校准数据受阻 ◐」注记——judge.py 三件套/判读/κ、材料 50（20/15/15、25/25、seed=20261110）、answersheet 模板、脚本三形态、10 门禁用例；chat 受阻（A/B/E 同源）；**A-6 留「待数」不预填**；口径：人工双评=用户侧回流、主指标 judge vs 人工 κ（互评 κ 两标签文件可算）、材料为构造应答（faithful=标注语料连续句、unfaithful=语料内他文档句）。
   - TC-EVAL-05：新增「观察项 ✅（记录级，构造会话形态）」注记——管道 + 6 双后端用例 + 归档 60/312/73|74/2/0.0274|0.027（12 会话注入、2 伪造 ID、form=constructed_sessions）；**数据源边界**（返回面非应答面；actor 无 agent 标识/session id；比例=去重分母；生产 `--db` 待部署配置 actor 形态）；「在线」按构造会话+受阻登记口径。
   - TC-EVAL-04：注记 m3-5 增补——RR exact 60×2（G-29③ 收口）、P3-9 同源校验用例（载体 3→4）、clean env（eval_seed 单一来源，门禁与基线同源）、fail-open 删除、显式 raise；维护口径不变（有意变更=重测同步冻结表与 JSON）。
   - TC-EVAL-01：补一句「m3-5 clean env 仅用于 TC-EVAL-04 门禁；TC-EVAL-01 标准矩阵不变；m1 历史档只读保护（`--allow-m1-overwrite`）」。
   - TC-EVAL-02/E 组：LLM 候选占比仍受阻（补位不替换）。
2. **known-gaps**：
   - G-8：① **收口**（M3 60q/73docs、512/256×双后端 r@10 0.00pp、MRR +0.84pp 正向波动、分辨率 1.67pp；可选配置开放，env `LATTICE_EMBED_MODEL/DIM` 零代码、标签 `model:dim` 区分；真实语料待决-1 部署复标；判据材料 report-m3-5-g8-mrl-fullset.md，工件 data/ 未入库）；② 0.99/0.95 维持（真实抖动未校准）；③ 已定。
   - G-29：③ **收紧/划销**（RR exact + P3-9 同源校验 + clean env；漏检面关闭）；④ 维持主依赖（用户裁定 2026-11-10）；可加⑤ judge 判读词表残余（真实联调记录解析/误判率）。
   - **新 G-30**：TC-EVAL-05 数据面（应答引用采集入口、agent 标识/session 片段、去重分母口径、生产 sampler CLI 待配置）——重开条件=真实 agent 部署。
   - G-6：建议补 v1.5 注记——D 组 full 档顺带给出真实模型 60q（sqlite 0.9667/pg 1.0，偏差 3.33pp>2pp），**不关闭** G-6；真实模型与代理口径不可比、分辨率 1.67pp。
3. **A-6**：状态改「待数（受阻）」；出数后由监督侧定数回写。
4. **待决-1**：m3-5 E 组受阻更新（LLM 候选/真实 query 占比顺延；真实语料未决）。
5. **§六 M3 行 + AGENTS/_m3-plan row5**：登记 m3-5（TC-EVAL-03 ◐、TC-EVAL-05 ✅、TC-EVAL-04 收紧、G-8① 收口、G-29③ 收口、门禁 1918+1）；达成宣告按 §七 N-4 的受限句式落笔（**待用户确认**）。
6. **RUNBOOK**：补 eval 脚本用法（judge materials/run-judge/calibrate、response_layer_rows+ragas evaluate、anchor --demo/--db）、m1 档保护、MRL 复跑命令与工件路径、data/ 工件不入库说明、受阻复跑路径。
7. **可选**：把 P3-9/RR 注入实证补记入 m3-4-injection-evidence.md 或 m3-5 附记（当前仅 Tester 报告记录）。

### 遗留事项去向
- **配额恢复后补跑小批**（不新开里程碑）：A 组真实 judge 联调+校准+A-6 定数；B 组响应层真实基线；E 组 LLM 候选增补（补位不替换）。
- **部署期**：TC-EVAL-05 生产面（actor/应答引用采集入口 + G-30）、真实 agent 会话抽样；（G-28③ PG 接线维持既有部署期项）。
- **后续顺手批**：P3-1~P3-10 中代码/文档项（建议合并为 m3-5 followup touch 或 M4 卫生批）；G-6 维持。
- **用户侧**：TC-UI 人工走查（M3 宣告唯一人工待勾）。

### manifest 要点
- codeSha=`05116a4c33e89de3fa006a4fc662f6b135d161b5`；testedSha=reviewedSha=同 SHA；base=`8bed157`；deliveryHead=docs 批后的 coder chore commit（须复核与最终 HEAD 一致）；docsCommit 单列。
- 门禁：**1918 passed + 1 deselected、0 skipped、双模式（常规/-O）**；pg 收集 724=687+37；基线 1898+1；+20 分解（judge 10/response 3/anchor 6/gate 同源 1）；`uv lock --locked` exit 0；-O 模式 4 warnings 与基线同款（非回归）。
- rounds=1；testVerdict=PASS；reviewVerdict=APPROVED；specRulings：judge 端点沿百炼先例、人工双评双轨、P3-1 维持主依赖、P3-8 clean env、6 择型全 ACCEPT。
- **caveats（必须如实）**：①真实 LLM 面三组受阻（A judge/B 响应层/E 候选），A-6 未定数；②C 组为构造会话 + 数据源/agent 标识边界（G-30）；③D 组工件在 gitignored `data/bench-results`（本机在位、Tester 核验，不可从仓库复现，需真实 API key+配额）；m2-5 28q MRL JSON 已覆盖、历史数字在报告；④M3 宣告范围为 N-4 受限句式；⑤TC-UI 人工走查未执行。
- 交付留痕：用户确认交付后，`export PATH="$HOME/install/gh_2.97.0_macOS_arm64/bin:$PATH"`，以 `gh pr review` 落审查结论（PR base=develop），只做留痕与放行确认，不经手合入。

**结论：APPROVED**——本轮 diff 无 P1/P2；F 组移交全清、A~E 组交付与受阻申报合规、D 组判据材料充分、回归零弱化/分层/禁区/分支纪律全过。P3×10 均登记级（其中 P3-2/docs 必登记、P3-9 建议顺手修）；需求边界 N-1/N-4 需用户裁定，N-2/N-3 由 docs 批定口径。

</details>

<details>
<summary>R2 Committer 报告（2026-11-10 22:20，reviewVerdict=APPROVED）</summary>

# task-knowledge-lattice-m3-5 · R2 Committer 复审报告

**reviewVerdict: APPROVED**
**reviewedSha: `a96e606776593b00eb3112d967ff75599cf22fcc`**（= testedSha = HEAD；父=`05116a4`=R1；父链线性 `8bed157→05116a4→a96e606`；origin/develop 仍=8bed157，未 push）
**CASE_BUG 裁定请求：未收到**

> 环境说明：bash 仅 git 白名单，未独立复跑 pytest；门禁采信 Tester R2 独立复跑（1921+1 双后端双模式 0 skipped、pg 724），并以增量 diff 逐行静态审查 + 测试判别力核对 + 禁区/父链/零残留独立核验交叉验证。

---

## 一、P3-9 闭环确认：**已闭合**

| R1 P3-9 要求 | R2 实现 | 核验 |
|---|---|---|
| 目标非空拒写 | `scripts/eval_judge_m35.py:49-66` `_annotated_sheet_rows`：label/rater **任一非空**（`strip()` 后）计数；`:77` `if annotated and not force` → rc=1 | ✓ 语义如实（仅 rater 非空计入、纯空白不计——Tester 探测 4 行计 3 实证） |
| 报错可行动 | `:79-83` 含已检测标注行数「N 行（label/rater 任一非空）」+ `--force` 提示 + 备份到 `data/eval-judge/` 建议 | ✓ 文案完整、stderr、rc=1 |
| --force 显式覆盖 | `:202-204` 独立 `add_argument("--force")`（**不在互斥组**——首版 bug 已修，Tester E1/E2 双向实证）；`:210` 传入 `cmd_materials(force=…)` | ✓ 覆盖路径重建双文件为全空模板 |
| 拒写原子化 | 守卫位于 `_load_inputs()`/`mkdir`/任何写盘之前 → 拒写时 materials 与 sheet **均不写**（旧对仍同代配对） | ✓ 代码顺序静态核验 + 测试 `not (tmp/材料).exists()` 内容级断言 |
| 空模板/缺席不破坏 | `annotated=0` 时照常生成；文件缺席 `is_file()` 返回 0 | ✓ +3 用例之 test 1 + Tester P0/P1 |
| `--n` 变更场景 | 有标注则拒写（两文件都不变，无 item_id 集合错位中间态）；`--force` 时两文件同步以新 n 重建 | ✓ **语义闭合** |

**边界补充核验**：守卫只拦「写」不拦「读」；真实仓当前 answersheet 仍为空模板（R2 diff 未触碰 `eval/reports/`，git status 零残留，Tester Path A MD5 前后一致）→ 首次正常使用不受影响。**结论：R1 P3-9 数据丢失风险（含 `--n` 错位场景）完整关闭。**

**R2 新观察（P3 登记，不阻断）**
- **R2-P3-1（潜在对齐风险，R1 存量）**：`cmd_calibrate` 的 `_read_labels` 只取 label 列表、按**行序**配对（长度相等即通过），并非按 item_id join；若用户另行输出的标签文件行序不同（等长）会静默错配校准数据。本轮原子化恰好堵住「材料/sheet 错位」这一路径，但 calibrate 输入契约仍建议下一顺手批改 item_id join + 集合相等校验。
- **R2-P3-2（R2 守卫的 fail-open 边角）**：`_annotated_sheet_rows` 对解析失败行「不计」——若 answersheet 被非 JSONL 保存（如表格软件转 CSV）或全部标注行损坏，会判 0 并覆写。建议 next touch 改 fail-safe（任一行解析失败即拒写，或计入 annotated）。
- **R2-P3-3（卫生 bundle）**：`--force` 与 `--run-judge/--calibrate` 同用会被静默忽略（help 已写「与 --materials 连用」，无害；可在 main 加 parser.error）；`:52` 局部 `import json as _json` 与模块级 `json`（:26）重复；test 1/3 的 `capsys` 未使用。

---

## 二、择型裁定（拒写原子化）：**同意**

- 语义正确且是**最小闭合**：唯一会造成静默错位的形态是「materials 已换新 item_id 集、sheet 仍是旧集」；守卫先于任何写盘 → 不存在该中间态；`--force` 时配对重建。
- 非过度保护：空模板/缺席路径零影响（P0/P1 实证）；用户若想保留旧标注，报错文案已给出备份路径，语义自洽。
- 与 calibrate 的行序契约互补（见 R2-P3-1），本轮无需扩大。

---

## 三、范围 / 纪律核对：**全过**

- **增量恰 2 files +129/−6**（`scripts/eval_judge_m35.py` +43/−6、`tests/test_eval_judge_m35.py` +86/−0），无其他散布；R1 25 files 中除这两项修复靶点外**其余 23 文件零触碰**（`--name-only` 独立核验）。
- **R1 APPROVED 面零回归**：脚本 diff 仅 `cmd_materials`/`main`/help 段；测试 diff 仅**末尾追加**（既有 10 用例零改动）；`eval/reports/judge-*` 数据文件未改（seed 确定性复跑 MD5 一致）。
- **禁区**：`docs/ prototype/ .opencode/ pyproject.toml uv.lock .env.example` diff = **0 字节** ✓；无新依赖。
- **测试门禁审查**：新增 skip/xfail = 0；删除测试函数 = 0；+3 节点（judge 模块 10→13，`--collect-only` 由 Tester 独立清点）→ 1918+1→1921+1 对账成立，pg 臂仍 724（新用例无 backend fixture）✓。
- **测试质量**：3 用例为**内容级**判别——test 2 断言「标注行数 3 + --force 提示 + sheet 全量相等 + materials 原子不存在」，非仅退出码；test 1/3 覆盖空模板与 force 覆盖。Tester 另以 subprocess 真实走 argparse/main 面 15/15（含 P0~P3/E1/E2），采信；`main()` 的 `args.force` 接线本身无门禁用例，由 CLI 实证覆盖（可接受）。
- **分支/提交**：`[task-knowledge-lattice-m3-5] R2: …`，父=05116a4，未 push，工作区仅监督侧检查点改动（与 R2 无关）✓。
- **warnings**：-O 4→1 为字节码缓存转热的暂态（R1 已申报冷缓存现象，来源文件本轮未触碰），非回归——采信 Tester 反向实证；manifest 记 caveat。

**P1：无 · P2：无**（P3 见 §一 R2-P3-1~3，均登记不阻断）

---

## 四、终态 manifest 要点更新（R2 后，交付阶段用）

| 项 | R1 值 | **R2 终态值** |
|---|---|---|
| codeSha / testedSha | 05116a4 | **`a96e606776593b00eb3112d967ff75599cf22fcc`**（R2 = 最后代码 commit） |
| reviewedSha | 05116a4 | 交付阶段 PR HEAD（docs 批 + chore 后；须核 `git diff a96e606..HEAD` 仅含 docs/检查点/监督侧文件，**src/scripts/tests/eval/benchmarks 零改动**） |
| rounds | 1 | **2** |
| 门禁 | 1918+1 | **1921+1**（1921=1918+3；双后端双模式 0 skipped；pg 724=687+37；-O warnings 4→1 缓存暂态） |
| 对账 | +20 | **+3（judge 10→13 tests）** |
| verdicts | PASS/APPROVED | R2：testVerdict=PASS + reviewVerdict=APPROVED（R1 亦双通过，rounds=2 全程无 FAIL） |

**caveats 增补（在 R1 清单上）**
1. R2-P3-2 守卫仅覆盖**可解析**的已标注行（解析失败行不计——非 JSONL/全损坏文件为 fail-open 边角）；R2-P3-1 calibrate 按行序配对（R1 存量）。
2. `--force` 与非 `--materials` 模式同用被静默忽略（无害）；新用例未覆盖 `main()` 接线（CLI 由 Tester subprocess 实证）。
3. -O warnings 计数随字节码缓存状态波动（4→1），非代码回归。
4. R1 全部 caveat 维持：A/B/E 真实 LLM 受阻、A-6 待数；C 构造会话 + G-30（N-1 用户裁定接受返回面）；D 工件 gitignored；**N-4 受限宣告句式**（用户裁定 2026-11-10）；TC-UI 人工走查待用户。

**specRulings 补录**：用户 2026-11-10「同意」——N-4 受限宣告 / N-1 接受「search 返回面」+ known-gaps G-30 / **P3-9 本轮 R2 顺手修**；N-2（应答主来源=增强器应答+辅助构造应答）/ N-3（主指标=judge vs 人工 κ、互评 κ 辅助）由 docs 批定口径。

**evidence manifest 附项**：R2 Tester 报告（检查点 details 块）+ coder R2 commit message + Tester CLI 15/15 实证（随报告，无独立归档文件）；checkpoint 需由 supervised-coding 落 `round=2 / reviewedSha=a96e606 / reviewVerdict=APPROVED / status=approved`。

**docs 批增量（在 R1 清单上追加）**：RUNBOOK eval 用法补 answersheet 保护语义（`--materials` 遇已标注 sheet 默认拒写 rc=1；`--force` 显式覆盖；标注建议备份到 `data/eval-judge/`）；labeling-notes m3-5 节可注一句 R2 保护与 `--force`。R1 docs 批其余项（TC-EVAL-03/05/04/01 注记、G-8① 收口、G-29③ 划销/④ 维持、G-6 v1.5、G-30、A-6 待数、待决-1、§六受限宣告、RUNBOOK 脚本用法）维持不变；R1 P3 残留清单剔除 P3-9（已闭合），其余 P3×9 + R2-P3-1~3 登记备查。

---

**放行结论：APPROVED**——P3-9 修复语义正确且原子化择型成立，`--n` 错位场景闭合；增量恰 2 files、R1 已验面零回归、禁区/父链/未 push 全合规；+3 用例判别力成立、门禁 1921+1 采信 Tester 独立复跑。R2 双通过达成（round=2），可启动交付序列（用户裁定已齐：N-4/N-1/P3-9）。

</details>
