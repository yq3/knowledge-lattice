---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m3-4
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e44b99653ffelr9DJyJkxuRDPi
testerTaskId: ses_e416cf4bbffeXfKLKQXWnjXgrY
committerTaskId: ses_e414bce1fffec7il2ErfxdKXr8
status: done
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 007196c996c759359508d7ba34e0840fdcd678ba
reviewedSha: 007196c996c759359508d7ba34e0840fdcd678ba
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged:
  - benchmarks/report-m2s-6-sev03.md
  - eval/corpus.jsonl
  - eval/golden.jsonl
  - eval/reports/labeling-notes.md
  - eval/reports/m3-4-injection-evidence.md
  - eval/reports/m3-baseline-pg.json
  - eval/reports/m3-baseline-pg.md
  - eval/reports/m3-baseline-sqlite.json
  - eval/reports/m3-baseline-sqlite.md
  - pyproject.toml
  - scripts/eval_baseline.py
  - scripts/eval_corpus_m34.py
  - scripts/eval_golden_m34.py
  - scripts/eval_synth_m34.py
  - src/knowledge_lattice/config.py
  - src/knowledge_lattice/eval/harness.py
  - src/knowledge_lattice/eval/ragas_bridge.py
  - tests/conftest.py
  - tests/test_admin_members.py
  - tests/test_auth_03_sso_jit.py
  - tests/test_auth_04_delegated.py
  - tests/test_auth_05_trusted.py
  - tests/test_eval_01_golden.py
  - tests/test_eval_gate_m34.py
  - tests/test_eval_m34_complete_set.py
  - tests/test_gate_e2e_m34.py
  - tests/test_pg_teardown_m34.py
  - tests/test_query_audit_m33.py
  - tests/test_r2_m2s6_fixes.py
  - tests/test_sev_03_entity_route_eval.py
  - uv.lock
endReason: null
createdAt: 2026-11-08T18:40:40+0800
updatedAt: 2026-11-09T14:37:56+0800
---

# task-knowledge-lattice-m3-4: 评测框架批

## 任务原文

**M3 第 4 段（评测框架批）**——来源：_m3-plan row4（用户确认的段序 2026-11-02）+ m3-1 检查点移交（#16 conftest teardown + warnings 治理 Tester P3②）+ m3-3 检查点移交顺手批（Committer P3-2/P3-6/建议项 P3-10）+ design §8 M3 分解第 1/3 项（完整黄金集扩容 / deepeval 门禁进 CI）。

### A 组：TC-EVAL-02 黄金集合成扩容（主线）

M1 小型黄金集（`eval/golden.jsonl`，28 query 纯中）扩容为 M3 完整集——**覆盖纯中 / 纯英 / 中英混排三态**（TC-EVAL-02 验收句：黄金集覆盖三态断言）：

1. 合成候选生成（评测框架选型 ragas——design §7 M3 依赖清单，#38 P2 标注为选型）双语 + 人工抽检修正口径。
2. 语料侧（`eval/corpus.jsonl`）相应扩容支撑三态 query（纯英/混排文档与查询成对）。
3. 三态覆盖断言进测试（语言标签 × 三态计数断言——「覆盖」可机检）。
4. 真实语料受阻申报维持（待决-1）：合成扩容先行，TC-EVAL-02 完整收口（真实 query 占比）待 m3-5/真实语料到位。

### B 组：双后端完整集基线（G-6 重开条件复测载体）

完整集在 sqlite/pg 双后端跑基线报告（沿 M1-5 eval/harness 形态，`eval/reports/` 归档）——产出完整集 recall@k / MRR 双后端基线，作为 G-6 重开条件的复测载体与 m3-5 MRL 判据的底数。

### C 组：TC-EVAL-04 deepeval 门禁 + 预注入回归验证

1. deepeval 门禁挂 `scripts/test_gate.sh`（design §8 M3 第 3 项「deepeval 门禁进 CI」——本项目 CI=本地 test_gate.sh 承接）。
2. **预注入回归验证**（TC-EVAL-04 步骤与预期原句）：人为注入一次检索层回归（如调坏权重）→ 门禁**卡住**（红）；正常变更不误报。注入实证沿 m3-2/m3-3 口径（恢复 src 零残留）。
3. 门禁口径：评测门禁用例确定性可离线跑（不依赖真实 LLM 端点——检索层指标零 LLM，沿 eval/ 既有口径；LLM 依赖面若 deepeval 框架需要，用其离线/确定性模式或 mock，真实端点联调不进门禁——沿 m2-5 百炼联调不进门禁先例）。

### D 组：ragas 选型接入

ragas 接入并给**选型结论**（#38 P2 标注为选型——接入后回写选型注记进 known-gaps/TEST-CASES 由监督侧 docs 批处理）：检索层已有自算指标（Recall@k/MRR），ragas 面向响应层（faithfulness/answer_relevancy）——本段完成依赖引入、接入形态与可运行验证（离线确定性口径或记录受阻）；响应层指标固化与 judge 校准归 m3-5，本段不要求出响应层基线数。

### E 组：测试基建顺手批（m3-1/m3-3 移交）

1. **issue #16**：`tests/conftest.py` `_pg_db` teardown 的 `except psycopg.Error: pass` 静默吞 DROP 失败——修法：DROP 重试/告警，或失败时打印 schema 名（issue 处置建议二选一或更优）。
2. **warnings 治理**（m3-1 Tester P3② 存量 172 条）：dev JWT 弱密钥 InsecureKeyLengthWarning + docling/pydantic DeprecationWarning——分类治理（测试侧 dev 密钥升位/过滤第三方 Deprecation 噪音），目标：门禁 warnings 显著收敛且不掩盖真实问题（治理口径：本项目代码产生的 warning 清零，第三方库 Deprecation 过滤声明）。
3. **m3-3 移交顺手批**：Committer P3-2（test_query_audit_m33 import time 未用）+ P3-6（test_r3_p2_2 函数名与断言语义相反——更名）+ 建议项 P3-10（A-1 gate 四接线点端点级 e2e 用例——与 TC-EVAL 批同段顺手，REST/MCP 四接线点探针拒绝零嵌入+probe_reject 审计的端点级断言）。

### 开工时口径裁定预告（m3-plan §二——任务确认时定，避免 spec_confirm 往返）

1. **合成候选生成 LLM 端点开发态形态**：ragas TestsetGenerator 类生成需 LLM——开发态内部网关未就绪，是否沿 m2-5 百炼先例（DashScope OpenAI 兼容端点，LATTICE_* env 零代码切换）？合成生成为一次性离线动作、生成物入库不依赖端点；联调/生成动作不进门禁口径沿用。
2. **judge 端点**（TC-EVAL-03 主面在 m3-5）：本段 ragas 接入若触及 judge 依赖，仅留接口不实现校准。

### 验收标准

1. **门禁零回归**：基线 **1880+1**（m3-3 交付后）双后端双模式 0 skipped、pg 臂收集数 >0；新增用例计入对账（TC-EVAL 三态断言/E 组用例等）。
2. **TDD**：A/C 组新行为红→绿证据；TC-EVAL-04 预注入回归验证实证（注入→门禁红→恢复→绿，恢复 src 零残留）。
3. **分层纪律**：core 无方言 SQL；评测代码落 eval 或 src/knowledge_lattice/eval（沿 M1-4 先例）。
4. **coder 禁改** docs/requirements.md、docs/design.md 冻结正文与 prototype/；活文档（TEST-CASES/known-gaps/RUNBOOK）由监督侧 docs 批处理（验收口径变化经用户确认后 supervised-coding 落笔）。
5. **分支纪律**：develop_opencode 本地 commit `[task-knowledge-lattice-m3-4] R<n>`，commit 前同步 origin/develop（当前=cd6d7a3）。
6. **交付形态沿先例**：双通过→监督侧 docs 批（TC-EVAL-02/04 登记注记、ragas 选型结论、issue #16 关闭材料）→coder chore 归档批（含 m3-3 终态条目后工作区改动：_m3-plan.md + m3-3 检查点）→push+PR base=develop→committer PR review→manifest→用户合入。
7. **依赖管理**：新增依赖（ragas/deepeval 等）走 uv（`uv add` 进 pyproject.toml + uv.lock 提交）；引入前确认与 requires-python >=3.11 兼容、无重冲突；离线可跑（门禁不依赖外网）。

## 需求确认
- [x] 用户已确认（2026-11-08 21:07「同意，本会话内subagent的调用无须问我」——status=implementing；**会话级授权：本会话内 Task 调用免逐一预告确认**）
- 历史遗留事项清单：（supervised-coding 扫描历史检查点汇总，默认并入新任务，见 README §4.6）
  - **并入本任务**：m3-1 移交 m3-4（#16 conftest teardown DROP 吞错 + warnings 治理〔Tester P3② 172 条存量——dev JWT 弱密钥/docling·pydantic Deprecation〕——m3-1 检查点遗留节）；m3-3 移交顺手批（Committer P3-2 test_query_audit_m33 import time 未用 + P3-6 test_r3_p2_2 函数名更名 + 建议项 P3-10 gate 四接线点端点级 e2e 用例——m3-3 检查点遗留节）——即本任务 E 组
  - **不并入（去向已登记）**：G-28③ 生产 lifespan 接线残余 + PG 接线部署期复验（P3-5/P3-11+Tester P3-2）+ G-28①②⑥⑧ 开放点 → 部署期/触发时处置；m3-3 移交「后续 web/语义批」P3-1/3/4/7/8/9 → 后续批顺手级；TC-UI-01~05 人工走查 → 用户侧（不阻塞）
  - **回写待办**：m3-3 检查点遗留节「文档面纪律」条目实际已随 m3-3 监督侧 docs 批完成（RUNBOOK §1.z 扩容+TEST-CASES 两条纪律注记），本任务收尾时 supervised-coding 回写勾选
- **开工时口径裁定（2026-11-08 21:07 用户确认）**：合成候选生成 LLM 端点开发态形态=**沿 m2-5 百炼先例**（DashScope OpenAI 兼容端点，LATTICE_* env 零代码切换）；合成生成一次性离线动作（生成物入库、复跑不依赖端点），生成/联调动作不进门禁口径沿用；judge 端点（m3-5 主面）本段只留接口不实现校准

## 遗留事项（跨任务移交）
- [x] **本轮清偿**（2026-11-09 双通过，SHA 007196c）：m3-1 移交 #16 conftest teardown〔重试+schema 名告警+3 用例——随 PR 关闭〕+warnings 治理〔171→0〕；m3-3 移交顺手批 P3-2/P3-6/P3-10〔端点级 e2e 8 用例〕；E 组全清。
- [x] **移交 m3-5（Committer P3×11 处置——见 _m3-plan §二 m3-4 移交）**：~~顺手批候选 P3-2（floor=None fail-open）+P3-7（聚合下限显式 raise 使 -O 等强）+P3-8（per-query RR exact 收紧——G-29③）+P3-9（冻结表 vs 基线 JSON 自动同源校验）+P3-6（ragas_bridge docstring 与实现不符——m3-5 接入时修）；卫生登记 P3-3（eval_baseline 头部用法/默认 label——旧命令覆盖 m1 档风险）+P3-4（eval_corpus 脚本与数据不同源+「幂等」docstring）+P3-10（harness/eval_baseline 自称 M1、.env.example 补 LATTICE_EVAL_LLM_*、eval_synth field 未用、test_auth_03 硬编码密钥）；裁定项 P3-1（deepeval 分组 dev 组建议——维持现择型已注记 RUNBOOK §1.aa/G-29④，m3-5 可裁定）~~ **已清偿：来源 task-knowledge-lattice-m3-5（2026-11-10 双通过，PR 待开）——P3-2/7/8/9/6/3/4/10 代码面全清+P3-1 用户裁定维持主依赖（2026-11-10）+P3-5/P3-11 docs 登记（G-29②/RUNBOOK §1.aa）**。
- [x] **docs 已落（本轮监督侧 docs 批）**：~~G-29 新增（①ragas 钉版②统一 lock docling 共享依赖降级③RR exact 缺位④deepeval 分组口径）；G-6 v1.4（M3 基线出数+复测载体就位）；RUNBOOK §1.aa（uv sync --frozen/eval 组/冻结表维护口径/基线复跑）+§1.x（LATTICE_EVAL_LLM_*）~~ 已落笔核验（m3-5 开工时监督侧复核；m3-5 追加 G-6 v1.5/G-29 更新/G-30 新增/RUNBOOK §1.aa 扩充）。
- [ ] **登记部署期/用户侧（不阻塞）**：G-28③ 生产接线+PG 复验+G-28①②⑥⑧ 沿 m3-3 登记维持；TC-UI-01~05 人工走查维持（本段无 UI 形态变化）；待决-1 真实语料维持未决（~~LLM 候选复跑/增补 m3-5~~ → m3-5 复跑仍受阻——配额恢复补跑小批，见 m3-5 检查点遗留节）。
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1: coder 完成（2026-11-09 12:29 报告，**全新会话**，coderTaskId=ses_e44b99653ffelr9DJyJkxuRDPi，commit `007196c` 于 develop_opencode，31 files +12859/−2821，父提交=cd6d7a3（origin/develop 同步确认无前进），未 push；监督侧机械核验 ✓ HEAD/父提交/31 files/docs+prototype+.opencode diff=0）——**A** ✅ TC-EVAL-02 黄金集 28→60 query（zh 12→24/en 8→18/mix 8→18）+语料 39→73 docs 成对扩容（纯中 9/纯英 12/混排 13）+三态规模分布/lang 标签×文本一致性/标注可达性机检进测试+q27 legacy 勘误 mix→zh；合成脚本 BaseRagasLLM×DashScope compatible（LATTICE_EVAL_LLM_* env）——**真实端点当日配额受阻申报①**（qwen 系 403/429/404 全档），offline 确定性兜底+人工抽检修正入库（沿 m2-5 受阻先例）；**B** ✅ 双后端基线 m3-baseline-{sqlite,pg}.md/json（sqlite r@10=0.9167/MRR=0.8031、pg 0.8333/0.7213，60q/73docs 含逐 query hits）；**C** ✅ deepeval>=4.3.3 主依赖+自定义 GoldenRecallMetric（BaseMetric 零 LLM，同步 measure+async 包装）+assert_test 逐 query recall@10 exact 冻结下限（60×2 后端）+聚合 0.05 余量双层卡门；离线确定性（插件 -p no:deepeval 禁用+DOTENV/TELEMETRY 禁用）；**注入实证**：retrieve.py RRF 反序注入→eval_gate 双臂红（q01 recall@10=0.0<1.0）→恢复零残留→绿（m3-4-injection-evidence.md 归档）+-O 失败路径显式 raise 实证；**D** ✅ ragas 0.2.15×langchain 0.3 era 钉版进 eval 依赖组（**上游 vertexai import 断裂规避申报②**）+ragas_bridge（judge 接口留 m3-5/非 LLM 指标离线自检通过）；**E** ✅ #16 _drop_pg_schema 抽出（3 次指数退避重试+持续失败 warnings.warn 含 schema 名+末次错误）+test_pg_teardown_m34 3 用例；warnings 171→0（mock SSO 弱密钥 8/14/15B→≥32B 升位+docling×2/deepeval×1 窄过滤登记；-O 残 1 条 PytestConfigWarning 保留信号——申报⑤）；P3-2 import time 删+P3-6 函数名更名 …_no_longer_triggers_repair+P3-10 gate 四接线点端点级 e2e（REST search/semantic entities/annotate+MCP search_entities/annotate：零嵌入计数+probe_reject 审计经 GET /audit 断言）；**SEV-03 互锁**：黄金集扩容致 TC-SEV-03 数字漂移被门禁抓红→报告随 M3 集重测回填（sqlite 0.7/0.2627→on 0.75/0.2917、pg 0.475/0.4854→on 0.55/0.5026，不回退判定全维通过——申报③）；test_eval_01_golden 计数/下限随 M3 集重定（0.05 余量同纪律）。自测：TDD 红→绿（A 组 2 failed→4 passed、E-1 ImportError→3 passed）；**GATE PASS 1898+1**（基线 1880+18：pg_teardown 3+complete_set 4+eval_gate 3+gate_e2e 8；pg 臂 722=685 参数化+37 专用全实跑）；ragas offline self-check 通过；uv lock --locked 通过。**择型申报 11 条**（deepeval 主依赖/ragas eval 组、插件禁用三因、async 包装〔4.x 恒走 a_measure 实测〕、exact+余量双层卡门〔弃 per-query RR 下限〕、BaseRagasLLM 直连弃 TestsetGenerator〔(doc,lang) 定向+标签锚点〕、offline 兜底如实登记、疑问词停用口径、E-1 重试+warnings、窄匹配过滤、uv 镜像解析+lock URL 回写 pypi 规范〔字节一致 sha256 不变〕、SEV-03 重测回填非放宽）。**边界申报 5 条**（①端点配额受阻处置待裁定 ②ragas 断裂钉版+选型结论回写归监督侧 ③eval_01 下限重定语义等价 ④q27 勘误 ⑤-O 残 1 条）。commit SHA=007196c996c759359508d7ba34e0840fdcd678ba。

- R1: tester **PASS**（2026-11-09 13:05，**全新会话**，testerTaskId=ses_e416cf4bbffeXfKLKQXWnjXgrY，testedSha=007196c996c759359508d7ba34e0840fdcd678ba 复核一致）——门禁独立复跑 **GATE PASS 1898+1 双后端双模式 0 skipped**（pg 臂 722=685 参数化+37 专用；+18 对账逐文件独立收集核对 3+4+3+8 严丝合缝）。逐项勾验 A/B/C/D/E+联动全 ✅（A 独立计数 60/73 零悬空引用+lang×文本一致性独立分类器零不一致+q27 勘误复现+offline 兜底不冒充；B 基线 json+md 双产物+随机 8 query×双后端 hits 自洽+跨后端诚实零如实；C **冻结下限 vs 基线 JSON 程序化逐条对照零漂移**+离线确定性+误报面「确定性系统冻结值即可复现值」；D 默认环境零 ragas 铁证〔uv tree/uv sync ImportError〕+offline_self_check 复跑通过；E #16 重试+告警断言强度齐+warnings 171→0〔弱密钥升位仅 mock 常量、prod 守卫按值相等不受影响〕+P3-10 真端点级非重复单测；联动 eval_01 下限上调非放宽+SEV-03 动态数字互锁）。**独立注入实证**（与 coder 不同源：`_rids_by_rank` 名次序反转）→ eval_gate 双臂红（sqlite q01 0.0<1.0/pg q03 0.0<1.0）+ **-O 模式同红**（assert_test 显式 raise）→恢复零残留→3 passed。**择型 11 条全 ACCEPT**（④附 P3 注记）。**边界申报 5 条全 ACCEPT**（①沿 m2-5 先例合规·生成物质量独立机检兜住 ②钉版理由 lock 元数据+实测可导入成立 ③严格强于旧形态 ④可复现 ⑤保留信号合理）。**P1 无；P2 无；P3×3**（①聚合下限 assert 关键字 -O 剥离休眠〔常规模式兜住〕②弃 per-query RR 下限残余漏检面〔取舍已明示〕③uv inexact sync 环境卫生注记〔部署镜像用 uv sync〕）。回归零弱化 ✓（函数删除=1 即更名/skip 新增 0/uv.lock 无夹带）；分层 ✓；禁区 ✓（docs/prototype/.opencode 空 diff、.env 未读）。报告全文见「最新验证意见原文」（R1 Tester）。

- R1: committer **APPROVED**（2026-11-09 13:21，**全新会话**，committerTaskId=ses_e414bce1fffec7il2ErfxdKXr8，reviewedSha=007196c996c759359508d7ba34e0840fdcd678ba=testedSha=HEAD 三一致；diff cd6d7a3..007196c 31 files 逐文件核对；门禁采信 Tester 独立复跑+静态对账独立复算〔冻结表 vs 基线 JSON/md 60 条逐行对读零漂移、golden 60 条逐条人工核对、uv.lock source 全 pypi〕；docs/prototype/.opencode 零 diff ✓；分层 ✓）——**P1 无；P2 无；P3×11**（①deepeval 主依赖 vs dev 组分组建议〔uv run 默认含 dev——不阻断，若维持择型需 RUNBOOK 注记〕②eval_gate floor=None 静默以实测为下限 fail-open+==冗余③eval_baseline.py 头部用法/默认 label 仍 M1——旧命令会覆盖 m1 历史档④eval_corpus_m34.py gk-en-m05 正文与入库数据不同源+「幂等」docstring 不实+import sys 未用⑤统一 lock 将 transformers 5.20→5.17/hub 1.33→1.16（docling 共享依赖降级副作用——门禁全绿证明兼容，需注记）⑥ragas_bridge retrieval_report_to_samples docstring 与实现不符〔user_input=qid 非 query、reference=None——m3-5 误导陷阱〕⑦聚合下限 assert -O 剥离〔=Tester P3-1〕⑧弃 per-query RR 残余漏检面〔=Tester P3-2，建议 m3-5 RR exact 冻结或登记 known-gaps〕⑨冻结表 vs 基线 JSON 无自动同源校验〔建议 m3-5 轻量测试〕⑩harness/eval_baseline 自称 M1 小型集、.env.example 未登记 LATTICE_EVAL_LLM_*、eval_synth field 未用、test_auth_03 硬编码密钥非引用常量⑪新 A/E 组测试纯 assert -O 剥离〔既有全局口径非新增风险〕）。**Tester P3×3 裁定全 ACCEPT**（⑦→m3-5 显式 raise；⑧→known-gaps 登记+m3-5 收紧；③uv 卫生→RUNBOOK 部署注记 uv sync --frozen）。**择型 11 条复核全 ACCEPT**（与 Tester 一致——①附分组建议、④附 RR 注记、⑤LLM 路径配额未实测边界①承接）。**边界申报 5 条复核全 ACCEPT**（①附裁定点：TC-EVAL-02「完整收口」是否接受 template+人工修正集为正式集或要求配额恢复补跑 LLM 候选〔补位不替换〕——建议 docs 批明示「三态覆盖已完成、真实 query/LLM 占比待 m3-5」）。**需求边界问题×3（供上报不交 coder）**：N-1 TC-EVAL-02 名号口径（三态覆盖达标≠完整收口——真实 query 待 m3-5，docs 需明示防误读）；N-2 TC-EVAL-04「正常变更不误报」维护口径（有意配方变更会红=显式重测更新冻结表——TEST-CASES 需注记）；N-3 依赖分组实际落位注记（design §7 并列 vs 实际主依赖/dev/eval 三处——非决策变更注记）。**docs 批建议清单**（TEST-CASES TC-EVAL-01/02/04 注记+TC-SEV-03 数字更新、known-gaps ragas 选型+G-6 基线+可选 P3-8/P3-5 登记、RUNBOOK uv sync/eval 组/env 用法、issue #16 关闭材料、AGENTS/_m3-plan row4 done、manifest 要点已给〔双 SHA+deliveryHead+7 caveats〕）。报告全文见「最新验证意见原文」（R1 Committer）。

- **双通过达成（2026-11-09 13:21，round=1 收敛）**：testVerdict=PASS + reviewVerdict=APPROVED，testedSha=reviewedSha=007196c996c759359508d7ba34e0840fdcd678ba=当前 HEAD——status=approved，待用户确认交付（交付序列：监督侧 docs 批→coder chore 归档批→push+PR base=develop→committer PR review→manifest→用户合入）。**上报裁定点**：①coder 申报①/边界①——TC-EVAL-02 完整收口口径（建议 docs 批明示「三态覆盖已机检达标、真实 query/LLM 占比待 m3-5」）；②Committer 需求边界 N-1/N-2/N-3（docs 批注记项）；③Committer P3-1 deepeval 分组建议（维持主依赖+RUNBOOK 注记 vs 移 dev 组——本轮不改，docs 批注记去向待定）；④P3×11 去向（m3-5 顺手批为主，docs 批登记项：P3-5 lock 副作用/P3-8 known-gaps）。
- **交付裁定（2026-11-09 13:30 用户「同意」——status=approved→交付中）**：范围口径确认——TC-EVAL-02 收口口径=「三态覆盖达标≠完整收口，LLM 占比待 m3-5」（N-1 落笔）；TC-EVAL-04 维护口径=「有意配方变更=显式重测更新冻结表」（N-2 落笔）；依赖分组注记（N-3 落笔）；P3×11 移交 m3-5 顺手批为主。交付序列启动。
- **交付执行①：监督侧 docs 批完成（2026-11-09 14:13）**——TEST-CASES **v1.9.18**（TC-EVAL-02 完成态注记〔三态覆盖 ✅+收口口径〕+TC-EVAL-04 完成态注记〔双层卡门+注入双源+维护口径〕+TC-EVAL-01 下限重定注记+TC-SEV-03 v1.9.18 重测注记+§六 M3 行 m3-4 段）；known-gaps **G-29 新增**（ragas 钉版+lock 副作用+RR exact 缺位+deepeval 分位）+**G-6 v1.4 注记**（M3 基线 sqlite 0.9167/0.8031、pg 0.8333/0.7213——重开条件复测载体就位）；RUNBOOK **§1.aa 新增**（uv sync --frozen/eval 组残留/共享依赖锁副作用/冻结表维护口径/基线复跑 m1 档只读）+**§1.x 评测 LLM 段**（LATTICE_EVAL_LLM_*）；AGENTS §1 M3 进度更新（m3-4 交付+剩余 1 段 m3-5）；_m3-plan row4 done+§二挂账更新（#16 划销+m3-3 移交清偿+m3-4 移交登记）+§三下段指引 m3-5（基线 1898+1）；**m3-3 检查点遗留节回写两条勾选**（m3-4 顺手批清偿+文档面纪律滞后勾选）。工作区待 coder chore 归档批：上述 docs 8 文件+m3-3 检查点（回写）+本检查点（新入库）。issue #16 随 PR closing（合入后未自动关则监督侧手动关——沿 #15 先例）。
- **交付执行②：Coder chore 归档批完成（2026-11-09 14:20 报告，续接会话 ses_e44b99653ffelr9DJyJkxuRDPi）**——前置核验 ✓（HEAD=007196c、origin/develop=cd6d7a3 无前进）；**chore `d6d1618`**（7 files +434/−17 doc-only，git diff src/tests/scripts/prototype=0；工作区净）；**push 成功 eb0eb71..d6d1618**（R1 007196c+chore d6d1618 两提交）；**PR #26 已开**（base=develop，https://github.com/yq3/knowledge-lattice/pull/26 ，--body-file 正确使用——body 3975 chars 回读双校验通过、`Closes #16` 独占行在位、EVIDENCE-MANIFEST 锚点在位、MERGEABLE）。待办：Committer PR review 留痕 → Coder manifest → 用户合入。
- **交付执行③：Committer PR 审查留痕完成（2026-11-09 14:22 报告，续接会话 ses_e414bce1fffec7il2ErfxdKXr8）**——`--approve` 自审限制失败（沿 #2~#25 先例），回退 **COMMENTED review 完整留痕**（review id `PRR_kwDOVZ9dhM8AAAABWwkuEw`，anchor d6d1618，body 3297 chars——APPROVED 结论/R1 继承〔code 007196c·delivery d6d1618·base cd6d7a3〕/门禁采信 Tester 1898+1〔committer 未独立复跑注明〕+静态对账〔+18=3+4+3+8、冻结表零漂移〕/择型 11 条+P3×3 裁定+边界 5 条复核/P3×11 去向/manifest 放行条件）；**chore `d6d1618` doc-only 复核通过**（7 文件清单+src/tests/scripts/prototype 空 diff+冻结正文零触碰；full diff 38 files +13293/−2838 对账闭合）；**docs 批抽核全落笔**（R1 建议清单逐项 ✅——3 条偏差注记不阻断：①PR body caveat 6 transformers 归因以 G-29② docs 为准②冻结表「同源」当前为人工纪律、自动校验 P3-9 归 m3-5〔前瞻措辞〕③工作区检查点交付条目系后续归档产物不在 PR diff）。PR #26 终态：OPEN/MERGEABLE/CLEAN，commits=[007196c（R1）, d6d1618（chore）]，base=develop。
- **交付执行④：Coder manifest 入 PR 完成（2026-11-09 14:25 报告，续接会话）**——manifest 15 键替换占位（head=deliveryHead=d6d1618c089e77fd1e00364e18736282bb8f713e、codeSha=testedSha=reviewedSha=007196c、rounds=1、双 verdict、gate{1898+1/基线 1880+1/+18/pg 臂 722/warnings 口径}、reviewRecord{PRR_kwDOVZ9dhM8AAAABWwkuEw}、selectionAdjudication{11/11+P3 3/3+边界 5}、specRulings×4、caveats×7、stale=false）；回读双校验 16 项 ALL PASS（json 可解析/15 键齐全/Closes #16 在位/commits 表/验证节/摘要零丢失/占位消失）。**PR #26 终态：OPEN/MERGEABLE——待用户合入**（`Closes #16` 合并时生效；若 body 经 `gh pr edit` 重写后合并不自动关闭，沿 #15 先例监督侧手动关）。合入后补记 mergeCommit/origin develop 前进条目；该条目之后的工作区改动（检查点交付条目）随 m3-5 chore 归档批入库。

- **交付完成（终态）（2026-11-09 14:37，用户确认「合入」，status=done）**：**PR #26 MERGED**——mergeCommit `8bed157a5dde7111cd3a0e2ea2d8f49696e6dd29`（mergedAt 2026-11-09T06:32:36Z，merge 形态沿 #24/#25 先例、远端分支保留）；origin/develop 前进至 8bed157，本地 develop/develop_opencode 均 ff 同步（develop_opencode 本地含 merge commit 领先远端 1 提交——沿先例不强推）。**issue #16 手动关闭**（PR body 含 `Closes #16` 但 merge 未自动关闭——body 曾经 `gh pr edit` 重写 manifest，GitHub 不重新解析 closing keywords〔已知行为，#13/#14/#15 同因〕；监督侧关闭并留交付评论：_drop_pg_schema 重试+告警+3 用例+SHA 007196c+门禁 1898+1）。**m3-4 段收官：round=1 一轮收敛（coder→tester PASS→committer APPROVED），门禁 1880+1→1898+1，TC-EVAL-02 三态覆盖 ◐（LLM 占比收口 m3-5）/TC-EVAL-04 ✅、双后端完整集基线出数、ragas 接入（G-29 登记）、issue #16 关闭、warnings 171→0、m3-3 移交顺手批清偿。M3 进度 4/5（m3-5 评测收口批——下一段，含 m3-4 移交 P3×11 顺手处置）；本条目之后的工作区改动（检查点交付条目）随 m3-5 chore 归档批入库。**

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

<details>
<summary>R1 Tester 报告（2026-11-09 13:05，testVerdict=PASS）</summary>

# M3-4 评测框架批 R1 Tester 验证报告

## 1. verdict

**testVerdict: PASS** ✅（门禁全量绿 + 验收标准 1/2/3/4 实证 + 独立注入卡门有效 + 无 P1）

## 2. 门禁独立复跑输出摘要（计数对账）

| 模式 | 结果 | 与申报对账 |
|---|---|---|
| pg 臂收集断言 | 722（[pg] 参数化 685 + PG 专用 37） | ✓ 与申报一致 |
| 常规 `uv run pytest` | **1898 passed, 1 deselected**（240.7s，**0 warnings**，0 skipped） | ✓ 1898+1 |
| `python -O -m pytest` | **1898 passed, 1 deselected, 1 warning**（232.4s，0 skipped） | ✓ 唯 1 warning=pytest 自身 PytestConfigWarning（申报⑤，见下） |
| 终局 | `GATE PASS: sqlite+pg 双后端、双模式全绿，0 skipped` | ✓ |

**+18 对账逐文件独立收集核对**：test_pg_teardown_m34=3、test_eval_m34_complete_set=4、test_eval_gate_m34=3（matrix×2+纯语义 1）、test_gate_e2e_m34=8（4×matrix）→ **18=3+4+3+8 严丝合缝**；基线 1880+18=1898 ✓。

## 3. 逐组勾验结果

**A 组 ✅**（TC-EVAL-02）
- 独立计数（python3 直数，不经项目代码）：golden **60** 条（zh 24/en 18/mix 18）✓；corpus **73** docs、doc_id 全唯一 ✓；标注 66 条**零悬空引用** ✓；q27 勘误复现（文本「增值税发票开具规范 发票栏次」无 ASCII 字母→zh，与申报④一致）。
- **lang×文本一致性可机检防伪**：我的独立脚本分类器与测试内 `_lang_state` 同口径（CJK×ASCII 字母、数字标点豁免），60 条零不一致；测试断言错标即红（不是贴标签）。
- 抽检：随机 8 query 标注 doc 全部在场且可达（见 B 组 hits 抽查）。
- 合成脚本审读：`--offline` 模板候选输出文件名带 offline 标记、落 `data/eval-synth/`（不入库）、labeling-notes 如实登记「人工抽检修正是标注流程一部分」——**不冒充 LLM 生成** ✓；端点 `LATTICE_EVAL_LLM_*` env 零代码切换 ✓。

**B 组 ✅**
- 基线数字与申报一致：sqlite r@10=0.9167/MRR=0.8031、pg 0.8333/0.7213（json+md 双产物齐全，md 含逐 query 表）。
- 随机 8 query×双后端 hits 序抽查：**全部与标注/召回值自洽**（如 q18 sqlite rr=0.1=标注 doc 在第 10 位；pg q02 r@10=0.0 inter=∅=G-6 AND 语义诚实零）。
- 跨后端差异如实登记（G-6 形态诚实零逐条点名于 labeling-notes）。

**C 组 ✅（重点）**
- GoldenRecallMetric：BaseMetric 子类、集合运算零 LLM、measure/a_measure 双实现（async 包装安全）✓。
- **冻结下限 vs 基线 JSON 同源性（防两处漂移）**：程序化逐条对照 `_R10_FLOORS` 60×2 vs `m3-baseline-*.json per_query.recall@10` → **零漂移** ✓；聚合下限余量实测 0.047~0.053（≈0.05 纪律）✓。
- 离线确定性：`-p no:deepeval`（pyproject addopts）+ 模块导入前 `DEEPEVAL_DISABLE_DOTENV/TELEMETRY_OPT_OUT` setdefault ✓。
- 0.0 冻结值的误报面：诚实零由聚合下限兜底（代码注释+labeling-notes 双处登记），非静默放宽。

**D 组 ✅**
- **默认环境零 ragas 铁证**：`uv tree` 默认树只有 deepeval；`uv sync` 后 `import ragas`/`import langchain_core` 均 ImportError ✓（venv 中先前可导入是 `--group eval` inexact sync 残留，非声明面问题）。
- `offline_self_check` 复跑通过：`{'non_llm_string_similarity': [1.0, 0.0], 'string_present': [1.0, 0.0]}`——ragas.evaluate 全链确定性 ✓。
- `uv lock --locked` 通过 ✓；judge 接口只留 `build_openai_compat_ragas_llm`（接口先行，无校准无端点依赖）✓；顶层零 ragas import（惰性导入）✓。

**E 组 ✅**
- #16 `_drop_pg_schema`：3 次指数退避重试 + 持续失败 `warnings.warn` 含 **schema 名+重试次数+末次错误**、不抛异常（保住「teardown 不覆盖用例原始异常」纪律）✓；3 用例断言强度齐（恒失败→告警+重试满额 / 瞬时→自愈零告警 / 正常→零告警）✓。
- warnings 171→**0**（常规模式门禁输出无 warnings summary）✓；弱密钥升位仅 mock 常量（`DEFAULT_SSO_MOCK_SECRET`），prod 守卫按**值相等**判定不受影响（env 设同值仍拒）✓；3 条 filterwarnings 全部窄匹配（消息前缀+来源模块，无 blanket ignore）✓。
- P3-2：`import time` 删除，纯卫生 ✓。P3-6：更名+docstring，断言未动 ✓。
- P3-10：**真端点级**（TestClient REST + MCP `_call` 工具调用 + `GET /audit` 审计端点断言），非 m3-3 core 层单测的重复；计数 Embedder 零嵌入断言、probe_reject reasons/scope 负载形态断言齐 ✓。

**联动 ✅**
- test_eval_01_golden：计数 73/60、三态 exact 分布断言；下限重定为 M3 集**同纪律**（~0.05 余量维持；r@10 下限 0.84→0.87 / 0.73→0.78 上调——非放宽）；M1 归档 m1-baseline-*.md 不动（docstring 注明「随数据扩容不再复现」）✓。
- SEV-03 互锁：测试**动态实测数字与报告文本逐字符断言**（漂移即红）——门禁绿即「sqlite on 0.75/0.2917、pg on 0.55/0.5026、全维不回退」成立；旧数字保留历史档 ✓。

## 4. 注入实证记录（独立注入，与 coder 不同源）

| 步骤 | 内容 | 证据 |
|---|---|---|
| 注入点 | `retrieve.py::_rids_by_rank` 名次序反转 `r["rank"]`→`-r["rank"]`（攻击名次协议 P3-2 防御面——coder 注入的是无 rerank 档最终序反转，不同函数不同机制） | git diff --stat: 1 file changed |
| 红（常规） | `pytest tests/test_eval_gate_m34.py` | **[sqlite] FAILED**: `q01 recall@10 实测 0.0 低于冻结下限 1.0`；带 DSN 复跑 **[pg] 亦红**（q03 0.0<1.0）→ **2 failed, 1 passed** |
| 红（-O） | `python -O -m pytest` 同命令 | 双臂同样 2 failed——`assert_test` 显式 `raise AssertionError`（源码核验）+ pytest 测试模块断言重写，-O 失败路径实证成立 |
| 恢复 | cp 备份回写（不用 git 写操作） | `git status src/` 空、`git diff src/` 0 行、备份清理 |
| 绿 | 同命令复跑 | **3 passed** |

误报面结论：全链确定性（TokenBagEmbedder/jieba/FTS/RRF）下冻结值即可复现值——无「正常波动」可触红；注入的两臂红均为真实回归击穿，无误报。

## 5. 择型 11 条裁定表 + 边界申报 5 条独立意见

| # | 申报 | 裁定 | 依据 |
|---|---|---|---|
| 1 | deepeval 主依赖 / ragas eval 组 | **ACCEPT** | 门禁默认安装可跑（全量绿实证）；uv tree/uv sync 证明默认环境零 langchain 全家桶（D2 纪律） |
| 2 | 插件禁用三因（-p no:deepeval） | **ACCEPT** | assert_test 不依赖插件（注入实验中失败路径照常 raise）；遥测/落盘噪声消除 |
| 3 | async 包装（4.x 恒走 a_measure） | **ACCEPT** | measure/a_measure 双实现同一路径，两种调用形态行为一致 |
| 4 | exact+余量双层卡门（弃 per-query RR 下限） | **ACCEPT（附 P3 注记）** | 逐 query 成员集 exact 是主回归向量；聚合余量担排序质量——单 query 纯排序小回退（MRR 位移 <0.05）存在残余漏检面，见 P3-2 |
| 5 | BaseRagasLLM 直连弃 TestsetGenerator | **ACCEPT** | (doc,lang) 定向+标签锚点生成映射直接；与 m3-5 judge 同一抽象面 |
| 6 | offline 兜底如实登记 | **ACCEPT** | 文件名/文档/标注记录三处登记，人工修正显式入流程 |
| 7 | 疑问词停用口径（可达性机检豁免） | **ACCEPT** | 疑问功能词是检索噪音；PG AND 不可达是 G-6 已登记差异，豁免面窄且口径明示 |
| 8 | E-1 重试+warnings | **ACCEPT** | 实现与 3 用例全审读通过 |
| 9 | 窄匹配 filterwarnings | **ACCEPT** | 3 条全带消息前缀+来源模块；本项目代码 warning 修源头清零（0 warnings 实证） |
| 10 | uv 镜像解析+lock URL 回写 pypi | **ACCEPT** | lock 内 ragas 条目 source=pypi.org/files.pythonhosted.org；`uv lock --locked` 通过=完整性成立 |
| 11 | SEV-03 重测回填非放宽 | **ACCEPT** | 断言形态不变+动态数字互锁；新集全维不回退；旧数字历史档保留 |

**边界申报 5 条独立意见**：
- **①端点受阻处置**：ACCEPT——沿 m2-5 先例合规（脚本+证据保留、offline 确定性兜底如实登记、人工修正入库、复跑路径写明）。配额受阻本身不可独立复验（瞬时计费态），但生成物质量已由独立机检兜住（可达性 0 悬空、基线 r@10=0.9167 证明 query 实际命中标注面——候选非垃圾）。
- **②钉版理由**：ACCEPT——lock 元数据实证 ragas 上游对 langchain 系全未钉；钉版组合（langchain-community 0.3.26）下 `chat_models.vertexai` 模块**实测可导入**；选型回写归监督侧 docs 批（coder 未碰 docs，纪律正确）。
- **③语义等价**：ACCEPT——同 ~0.05 余量纪律平移至新集、r@10 下限实际上调；且新增逐 query exact 下限使回归检测**严格强于**旧聚合-only 形态。
- **④q27 勘误**：ACCEPT——可独立复现（文本无 ASCII 字母），机检断言使同类错标今后必红。
- **⑤-O 残 1 条**：ACCEPT——pytest 自身关于「-O 忽略测试模块外断言」的 PytestConfigWarning，是**保留的运行形态信号**而非项目噪音；常规模式 0 warnings。

## 6. P1/P2/P3 分级问题清单

**P1：无。P2：无。**

- **P3-1**：`test_eval_gate_m34.py` 聚合下限用 `assert` 关键字写——-O 模式下被剥离休眠（-O 只剩逐 query assert_test 显式 raise）。双模式组合门禁下由常规模式兜住，不阻断；后续可用显式 raise 或将聚合判定并入 metric 使 -O 等强。
- **P3-2**：弃 per-query RR 下限（申报④）的残余漏检面：单 query 纯排序回退（recall@10 成员不变、RR 降但聚合 MRR 位移 <0.05）不被卡。申报已明示取舍，TC-EVAL-04 验收句（卡「调坏权重」类回归）已实证覆盖；如需收紧可把 RR 也 exact 冻结（确定性系统零成本）。
- **P3-3**：环境卫生注记——`uv run --group eval` 后切回默认 `uv run` 不清除 eval 组包（uv inexact sync 残留）；声明边界无问题（uv sync 即还原），仅提示部署镜像构建用 `uv sync`（精确）而非累积 `uv run`。

## 7. 回归零弱化 / 分层 / 禁区核对结论

- **零弱化**：存量测试函数删除=1（即 P3-6 更名，断言未动）；skip 新增=0（双模式 0 skipped）；`-m manual` deselect=1 与基线一致；uv.lock 新增包全部落在 deepeval/ragas/langchain 依赖树（pytest-asyncio/repeat/rerunfailures/xdist=posthog/pyfiglet=deepeval 传递依赖；datasets/pyarrow/langchain 系/rapidfuzz/sqlalchemy/tiktoken=ragas 传递依赖），**无夹带无关包**。
- **分层**：diff 内 core/ 零方言 SQL（grep 实证）；评测代码落 `src/knowledge_lattice/eval/` + `scripts/`（沿 M1-4 先例）✓。
- **禁区**：`git diff cd6d7a3..007196c -- docs/ prototype/ .opencode/` = **空** ✓；`.env` 未读未碰；注入后 `git status src/` 干净、临时产物已清理。

**testedSha**: `007196c996c759359508d7ba34e0840fdcd678ba`（develop_opencode HEAD，父提交 cd6d7a3=origin/develop，复核一致；验证全程未 commit/push、未改任何仓库文件）

</details>

<details>
<summary>R1 Committer 报告（2026-11-09 13:21，reviewVerdict=APPROVED）</summary>

# M3-4 评测框架批 R1 Committer 审查报告

**reviewedSha: `007196c996c759359508d7ba34e0840fdcd678ba`**（=当前 develop_opencode HEAD；父提交 `cd6d7a3`=origin/develop，`git rev-parse`/`git log -2` 复核一致；31 files +12859/−2821 与申报一致）
**审查基线**：diff `cd6d7a3..007196c` 全量；docs/、prototype/、.opencode/ **空 diff** ✓。门禁实跑**采信 Tester 独立复跑**（本会话 bash 仅开放 git/gh 只读面，未能独立跑 pytest），静态对账独立复算。

---

## 1. verdict

**reviewVerdict: APPROVED** ✅（round=1 收敛；P1 无 / P2 无 / P3×十余条，均不阻断；需求五组覆盖完整、测试质量达标、无纪律违反）

---

## 2. 逐组/逐文件审查结论

### A 组：TC-EVAL-02 黄金集扩容 ✅
- **golden.jsonl**：独立清点 **60 条**（zh 24 / en 18 / mix 18，逐条人工核对三态分布与 q27 勘误）；q29–q60 标注全部指向 corpus 在场 doc、无悬空引用；q27 `mix→zh` 与文本无 ASCII 字母的事实一致（machine-check 口径正确，不是贴标签）。**lang×文本一致性断言**为独立测试侧分类器（非复用数据生成函数），具备真实杀伤力——q27 即由该口径暴露。三态**精确计数**断言（24/18/18）比旧「≥ 下限」强，防静默漂移。✅
- **corpus.jsonl**：**73 docs**、doc_id 唯一；独立核验 `gk-en-m*` 无 CJK（18 篇纯英 = 12 新 + 6 旧 exp），`mix≥27` 成立；标注锚点、dims 值域（CN/OS、VAT）齐。✅
- **test_eval_m34_complete_set.py**（4 用例）：规模/分布/标签一致性/静态可解析/multi-token/纯函数边界齐全，非走过场；用例对语料前缀组、维度越界也有断言。✅
- **eval_golden_m34.py / eval_corpus_m34.py / eval_synth_m34.py**：合成候选为「offline 确定性模板 + 人工改写」如实登记（labeling-notes 明示「不冒充 LLM 生成」），端点 `LATTICE_EVAL_LLM_*` 零代码切换；可达性机检为构造期检查（脚本内，不进测试）——见 P3-4。
- **真实端点配额受阻申报①**：沿 m2-5 先例成立（脚本+证据保留、offline 兜底、人工修正入流程、复跑路径写明）；不可独立复验端点受阻本身，但生成物质量由基线 r@10=0.9167/0.8333 与可达性抽检兜住。

### B 组：双后端完整集基线 ✅
- **m3-baseline-{sqlite,pg}.md/.json**：60q/73docs；sqlite r@10=0.9167/MRR=0.8031、pg=0.8333/0.7213；md 逐 query 值与测试冻结表**逐条一致**（我按 60 条逐行对读：sqlite q24/q50/q57 与 pg q01/q02/q10/q11/q20/q30/q36 的诚实零、q06–09 的 0.5、其余 1.0 全部吻合）；json 含 per_query.hits（m3-4 harness 新增），与 md 同源。✅
- **eval_baseline.py**：`--label` + JSON 双产物合理；但默认 `--label=m1` 且头部用法/产物说明仍是 M1——见 P3-3。
- **labeling-notes.md**：m3-4 节完整（规模、端点受阻、人工修正、q27 勘误、跨后端诚实零、冻结口径）；M1 历史节保留。✅

### C 组：TC-EVAL-04 deepeval 门禁 ✅
- **GoldenRecallMetric**：BaseMetric 子类、零 LLM 集合运算、measure/a_measure 双实现；输入为 harness 真实命中序（hits），非伪造。✅
- **逐 query exact 冻结 + 聚合 0.05 余量双层**：冻结表 60×2 与基线 JSON/ md 零漂移（Tester 程序化 + 我逐行复核）；聚合余量实测 0.047~0.053，符合「~0.05」纪律；r@10 下限相对 M1 实际上调（非放宽）。✅
- **注入实证**：coder（RRF 最终序反转）与 Tester（`_rids_by_rank` 名次序反转）**不同源**分别使双臂红、-O 同红、恢复零残留；`m3-4-injection-evidence.md` 归档完整。**TC-EVAL-04 验收句「卡住注入回归」成立**；「正常变更不误报」在确定性全链口径下成立（有意配方变更走重测更新冻结表，见需求边界 N-2）。✅
- **离线确定性**：`-p no:deepeval` + DOTENV/TELEMETRY 关闭；门禁不依赖外网。✅
- **harness.py**：仅 +per_query.hits（3 行），无行为破坏；下游 `test_eval_01` 报错信息复用无碍。✅
- **P3 见下**（聚合 assert -O 剥离、floor=None fail-open、无 per-query RR）。

### D 组：ragas 选型接入 ✅
- **eval 依赖组**：ragas 0.2.15 × langchain 0.3 era 钉版理由成立（上游 `vertexai` import 断裂；lock 元数据与实测可导入佐证）；**默认环境零 ragas/langchain 铁证**（uv tree/uv sync ImportError）符合「服务端默认不背 langchain 全家桶」。✅
- **ragas_bridge**：顶层惰性 import；`build_openai_compat_ragas_llm` judge 接口先行、key 只走 env/.env 不打印（沿 calib_m2_5 先例）；`offline_self_check` 用非 LLM 指标跑通 `ragas.evaluate` 全链，验证充分。**选型结论承载**：模块 docstring 已含「检索层自算、ragas 面向响应层、judge 留 m3-5、钉版理由」四要点，代码侧足够；正式回写 known-gaps/TEST-CASES 归 docs 批。✅
- **P3-2**：`retrieval_report_to_samples` docstring 与实现不符（见问题清单）。

### E 组：测试基建顺手批 ✅
- **issue #16**：`_drop_pg_schema` 3 次指数退避 + 持续失败 `warnings.warn`（含 schema 名/重试次数/末次错误）+ 返回 False，**不抛不吞**；`test_pg_teardown_m34` 3 用例（恒失败/瞬时自愈/正常）断言强度足，且不依赖真实 PG。✅
- **warnings 治理**：171→0（常规）；弱密钥升位仅改 mock/测试常量，prod 守卫按**值相等**判定不受影响（auth_sso.py 引用 config 常量）；3 条 filterwarnings 均窄匹配（消息前缀+来源模块），未 blanket ignore；-O 仅剩 PytestConfigWarning 信号（申报⑤）。✅
- **P3-2/P3-6/P3-10**：import 清理、函数更名（断言未动）、四接线点 REST/MCP **真端点级** e2e（TestClient + `_call` + `GET /audit`，含零嵌入计数与 probe_reject scope/负载形态），非 core 单测重复。✅
- **config.py**：`DEFAULT_SSO_MOCK_SECRET` 升 36B；全仓无旧值残留（除历史检查点；无需改 docs）。✅

### 联动 ✅
- **test_eval_01_golden**：计数 73/60、三态 24/18/18、下限上调（r@10 0.84→0.87 / 0.73→0.78，MRR 0.78→0.75 / 0.67→0.67，均高于新基线且 ~0.05 余量），**非放宽**；M1 历史档不动。✅
- **test_sev_03 + report-m2s-6-sev03.md**：60q 重测数字**动态互锁**（测试逐字符断言报告文本，漂移即红）；旧 28q 数字历史档保留；不回退判定全维成立。✅
- **回归零弱化**：`skip/xfail` 新增 **0**；删除 test 函数仅 1 个（P3-6 更名，断言未动）；既有断言改动仅 secret 升位、计数上调、docstring/import 卫生。✅
- **分层/禁区**：src 仅 config/eval（无 core 方言 SQL）；评测代码落 `src/knowledge_lattice/eval` + `scripts/`；docs/prototype/.opencode 零 diff；.env 未读。✅
- **依赖/lock**：`uv.lock` source 全 pypi（0 aliyun），`--locked` 通过；新增包全部落在 deepeval/ragas/langchain 树，无夹带。⚠️ 但注意统一解析副作用（P3-5）。

---

## 3. 问题清单（P1/P2/P3）

**P1：无。P2：无。**
（说明：以下 P3 均不阻断；如监督侧决定本轮不出 R2，可整体登记到下批/m3-5 处置。）

| # | 严重度 | 位置 | 问题 | 改法/去向 |
|---|---|---|---|---|
| P3-1 | P3 | `pyproject.toml:9` | 择型①「deepeval 主依赖」理由不充分：`uv run pytest` **默认就安装 dev 组**，deepeval 放 dev 组同样「默认安装可跑」；放主依赖会让服务端运行时闭包新增 pytest/pytest-asyncio/xdist/rerun 等测试栈（以及 opentelemetry-sdk/posthog），与 design §7「服务端清单保持最小（D2）」精神不符。deepeval **不**依赖 transformers（transformers/huggingface-hub 的降级是统一 lock 与 eval 组解析的副作用，见 P3-5，勿混淆）。 | 建议移至 `[dependency-groups].dev` 后 `uv lock`（门禁零影响）；若监督侧维持现择型，请把理由与「uv run 默认含 dev」口径写入 RUNBOOK/docs 注记。**不阻断**（从源码 `uv run` 部署实际无差异）。 |
| P3-2 | P3 | `tests/test_eval_gate_m34.py:141-146` | `floor is None` 时**静默以当次实测为下限**（注释说「提示冻结」但无任何提示）——若将来 golden 替换 query（条数不变），新 qid 无冻结值将**静默通过**，是 exact 冻结面的 fail-open。另 `:143` `== floor or >= floor` 冗余。 | 改为完整性断言：`assert set(floors) == {c.qid for c in golden}`（或 `pytest.fail` 明确要求冻结），删除 fallback；`==` 可删。建议随本批/m3-5 顺手修。 |
| P3-3 | P3 | `scripts/eval_baseline.py:2-11,73-75` | 新 `--label` 已支持 m3，但**头部用法与产物说明仍是 M1**，默认 `--label=m1`；现在数据已是 73/60，若按旧文档命令 `--backend sqlite` 不带 label 运行，会用 M3 数据**覆盖 m1-baseline-sqlite.md 历史档**。 | 更新 usage 为 `--label m3` 示例；缺省 label 改为按数据或要求显式传；至少加「m1 档只读/不覆盖」保护或恢复命令注记。 |
| P3-4 | P3 | `scripts/eval_corpus_m34.py`（gk-en-m05）vs `eval/corpus.jsonl` | 生成脚本里 `gk-en-m05` 正文仍含「免抵退/免退」中文，而入库 corpus 已人工改为 `exemption-credit-refund`/`exemption-refund`——**脚本与数据不同源**；若在 39-doc 基线上重跑脚本，会生成混排「纯英」doc，`test_eval_02_corpus_paired_expansion` 的 `en_docs>=18` 将变 17 而红。另脚本 docstring 称「幂等」，但 `assert doc_id not in rows` 在现有数据上重跑会直接失败；`import sys` 未用。 | 把脚本正文改成与入库数据一致（或显式登记该人工修正）；docstring 改为「一次性、重复运行会拒绝」；删未用 import。 |
| P3-5 | P3 | `uv.lock`（统一解析副作用） | 加入 eval 组后 lock 将 **transformers 5.20.2→5.17.0、huggingface-hub 1.33.0→1.16.1**（docling 系共享依赖），默认环境（不装 eval 组）同样受影响；门禁全绿证明兼容，但该副作用未在申报/注记中体现。 | 在 known-gaps 或 RUNBOOK 部署注记：锁为统一解析，eval 组会影响 docling 共享依赖版本；ragas 解除钉版/上游修复后重评；升级 docling 时回归。 |
| P3-6 | P3 | `src/knowledge_lattice/eval/ragas_bridge.py:126-136` | `retrieval_report_to_samples` docstring 写「user_input=query、reference=黄金标注键集」，实现却是 `user_input=q["qid"]`、`reference=None`（且 per_query 无 query/labels 字段，函数**无法**兑现文档）。这是 m3-5 响应层输入形态的误导陷阱。 | 修正 docstring（如实说明 report 只有 qid/hits，query/labels 需由调用方合并），或改签名接收 golden 并填 `reference`/`user_input`；归 m3-5 接入时修。不阻断本轮。 |
| P3-7 | P3 | `tests/test_eval_gate_m34.py:157-164` | 聚合下限用 `assert` 关键字，`-O` 下被剥离（常规模式兜住）；-O 只剩 deepeval `assert_test`（逐 query）。 | Tester P3-1，见 §4 裁定；建议 m3-5 改显式 `raise AssertionError`/`pytest.fail` 使双模式等强。 |
| P3-8 | P3 | `tests/test_eval_gate_m34.py` | 弃 per-query RR 下限（申报④）的残余漏检面：单 query 纯排序回退（top-10 成员不变、RR 降、聚合 MRR 位移 <0.05）不卡。 | Tester P3-2，见 §4；建议 m3-5 把 RR 也 exact 冻结（确定性系统零成本）或登记 known-gaps。 |
| P3-9 | P3 | 冻结表维护 | `_R10_FLOORS`/`_AGG_FLOORS` 与 `eval/reports/m3-baseline-*.json` **无自动同源校验**；目前靠人工复核与门禁现况（Tester 已验零漂移）。 | 加一条轻量测试/脚本，逐 qid 对比冻结表 vs 基线 JSON（或生成冻结表），防未来「重测只更新一处」。建议 m3-5。 |
| P3-10 | P3 | 文档/卫生 | `src/knowledge_lattice/eval/harness.py:1`、`scripts/eval_baseline.py` 仍自称「M1 小型黄金集」；`.env.example` 未登记 `LATTICE_EVAL_LLM_*`；`scripts/eval_synth_m34.py` `field` 未用；`tests/test_auth_03_sso_jit.py:343` 硬编码新默认密钥而非引用 config 常量。 | 归 m3-5/后续卫生批或 docs 批注记；不阻断。 |
| P3-11 | P3 | 测试形态观察 | 新 A/E 组测试为纯 `assert`，在 `-O` 模式被解释器剥离（项目既有全局口径：-O 依赖常规模式 + 显式 raise 路径）；本轮非新增风险。 | 无需改；如追求 -O 等强，可对关键断言用显式 raise（m3-5 统一治理）。 |

---

## 4. Tester P3×3 裁定

| Tester | 裁定 | 处置去向 |
|---|---|---|
| P3-1 聚合下限 `assert` -O 剥离 | **ACCEPT**（不阻断） | 常规模式兜住；建议 m3-5 改显式 `raise`；若本轮有其它 R2 顺手修亦可。 |
| P3-2 弃 per-query RR 残余漏检面 | **ACCEPT**（取舍已明示） | TC-EVAL-04 验收句已实证满足；建议 known-gaps 登记 + m3-5 收紧为 per-query RR exact（确定性系统零成本）。 |
| P3-3 uv inexact sync 环境卫生 | **ACCEPT** | docs 批 RUNBOOK 部署注记：部署/门禁环境用 `uv sync --frozen`（精确）而非累积 `uv run --group eval`；eval 组不默认安装。 |

**择型 11 条复核**：全部 **ACCEPT**（与 Tester 一致）——①附 P3-1 建议；④附 P3-2 注记；⑤ LLM 路径因配额未实测，边界①承接；⑧/⑨/⑩（重试告警/窄过滤/lock pypi URL）均成立；⑪ SEV-03 重测非放宽成立。

---

## 5. 边界申报 5 条复核（供上报，不交 coder）

| # | 结论 | 说明 |
|---|---|---|
| ① 端点受阻处置 | **ACCEPT（附用户/监督侧裁定点）** | 沿 m2-5 先例合规：脚本、offline 兜底、人工修正、复跑路径齐全，生成物质量由可达性/基线兜住。**待裁定**：TC-EVAL-02「完整收口」是否接受当前 template+人工修正集为正式集，或要求配额恢复后补跑 LLM 候选（补位不替换）再收口——建议 docs 批明示「三态覆盖已完成、真实 query/LLM 占比待 m3-5」。 |
| ② ragas 钉版 | **ACCEPT** | 选择合理；docs 批（known-gaps/TEST-CASES）落选型结论 + 钉版期限与复评条件；不要求 coder 改。 |
| ③ eval_01 下限重定 | **ACCEPT** | 同 ~0.05 余量纪律平移，r@10 下限上调；严格强于旧聚合-only。docs 批 TC-EVAL-01 注记新下限与「M1 归档不再复现」。 |
| ④ q27 勘误 | **ACCEPT** | 可独立复现（无 ASCII 字母），机检断言使同类错标今后必红；labeling-notes 记录足够，m1-baseline 历史档保留。 |
| ⑤ -O 残 1 条警告 | **ACCEPT** | pytest 自身运行形态信号，保留合理；常规模式 0 warnings。 |

---

## 6. 需求边界问题（供上报，不交 coder）

- **N-1（TC-EVAL-02 名号口径）**：当前 60 query 全部为合成/离线模板+人工修正，真实 query 占比按任务 A4 明确待 m3-5/待决-1。建议 TEST-CASES/known-gaps 明示「三态覆盖已机检达标；完整集真实 query 收口未完成」，避免把 m3-4 读成 TC-EVAL-02 全部收口。
- **N-2（TC-EVAL-04「正常变更不误报」）**：exact/lower-bound 冻结下限下，**有意配方变更**会红，需人工「重测并更新冻结表」——建议 TEST-CASES 注记该维护口径（冻结表更新=有意变更的显式动作），否则字面「正常变更不误报」易被误读为自动不误报。
- **N-3（依赖分组口径）**：design §7 M3 行把 ragas+deepeval+pytest 并列；实际落位为主依赖/deveval 组/dev 三处。建议 docs 批在 §7 行或 known-gaps 注记实际分组（非决策变更），避免后续误解与重复讨论。

---

## 7. docs 批建议清单（监督侧）

1. **TEST-CASES 下一版**：
   - TC-EVAL-02 登记注记：60q/73docs、三态 24/18/18、lang 一致性/可达性/标注可解析机检、q27 勘误、合成+人工修正、真实 query 收口 m3-5；
   - TC-EVAL-04 登记注记：deepeval 门禁（exact 逐 query + 聚合 0.05 双后端）、注入实证（双臂红/-O 红/恢复绿）、「有意配方变更=更新冻结表」维护口径；
   - TC-EVAL-01：下限重定注记（M3 集，~0.05 余量，r@10 上调）；
   - TC-SEV-03：数字更新（m3-4 60q：sqlite off 0.7/0.2627、on 0.75/0.2917；pg off 0.475/0.4854、on 0.55/0.5026；73/60 规模），历史档保留。
2. **known-gaps**：ragas 选型结论与钉版期限/复评条件；G-6 双后端基线更新（M3 集 m3-baseline-*.md/json）；可选登记「无 per-query RR exact 的残余漏检面」（P3-8）、统一 lock 的 transformers/hub 降级副作用（P3-5）。
3. **RUNBOOK**：部署/门禁环境用 `uv sync --frozen`（精确同步）；eval 组不默认安装、`uv run --group eval` 会残留；`LATTICE_EVAL_LLM_*` 端点 env 用法；如采纳 P3-5 注记共享依赖锁定副作用。
4. **issue #16**：关闭材料（`_drop_pg_schema` 重重试+告警 + 3 用例 + 门禁证据）。
5. **AGENTS/_m3-plan row4 done**：m3-4 门禁 1880+1→1898+1，A/B/C/D/E 完成，下一段 m3-5。
6. **manifest 要点**：见 §8。

---

## 8. manifest 要点（交付时）

- **codeSha = testedSha = reviewedSha = `007196c996c759359508d7ba34e0840fdcd678ba`**；base=`cd6d7a3`；deliveryHead=后续 chore 归档 commit（docs 批+检查点入库后）。
- **rounds=1**；**testVerdict=PASS**；**reviewVerdict=APPROVED**；stale=false（终态 HEAD 复核后）。
- **gate**：1898+1 双后端双模式 0 skipped（pg 臂 722=685 参数化+37 专用）；baseline 1880+1；常规 0 warnings、-O 1 warning（PytestConfigWarning，保留信号）。
- **selectionAdjudication**：择型 11 条全 ACCEPT（①附 P3-1 建议；④附 P3-2 注记）。
- **caveats**：① 合成 LLM 端点配额受阻→offline 候选+人工修正（m3-5 复跑/增补）；② ragas 0.2.15×langchain 0.3 钉版（上游 vertexai 断裂）；③ eval_01 下限随 M3 麻重定（上调非放宽）；④ q27 勘误（mix→zh）；⑤ -O 残 1 条 PytestConfigWarning；⑥ deepeval 主依赖分组建议（P3-1）；⑦ 统一 lock 的 transformers/hub 降级副作用（P3-5）。

**CASE_BUG 裁定**：本轮无 tester 提交的 CASE_BUG。

**放行建议**：reviewVerdict=APPROVED，可进入交付序列（监督侧 docs 批 → coder chore 归档批 → push+PR base=develop → committer PR 留痕 → manifest → 用户合入）；合入动作不经手。P3 项不阻断交付，建议在下批/m3-5 顺手清偿。
</details>

