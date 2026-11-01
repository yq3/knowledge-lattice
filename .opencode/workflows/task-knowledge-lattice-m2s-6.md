---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2s-6
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e6d824166ffepujpoFdBzz1iAA
testerTaskId: ses_e6b8618b9ffeKphrtPNpwOsB3H
committerTaskId: ses_e6b7517f3ffeqOfvT2TYOYMKEk
status: done
round: 3
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 4057b40
reviewedSha: 4057b40
# 交付归档 docs-only HEAD=a1901f5（chore 批——reviewedSha 沿 m1-4 双 SHA 口径保持代码审查值 4057b40）
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [core/semantic/fuzzy.py(新), core/semantic/recall.py(新), core/semantic/middleware.py(新), core/semantic/localac.py(新), core/semantic/annotator.py, core/semantic/build.py, core/semantic/lookup.py, core/semantic/expand.py, core/semantic/evalrun.py, core/semantic/constants.py, core/docs/retrieve.py, store/sqlite/migrations/semantic/0009_semantic_fuzzy.sql(新), store/postgres/migrations/semantic/0009_semantic_fuzzy.sql(新), store/sqlite/acl_render.py, store/postgres/acl_render.py, store/sqlite/backend.py, store/postgres/backend.py, api/search.py, api/semantic.py, mcp/server.py, worker/runner.py, config.py, pyproject.toml, uv.lock, tests/test_tag_04_entity_recall.py(新), tests/test_matrix_ts7_ts9.py(新), tests/test_sem_09_fuzzy.py(新), tests/test_sem_05_pinyin_vec.py(新), tests/test_sem_08_middleware.py(新), tests/test_yaml_05_local_ac.py(新), tests/test_sev_03_entity_route_eval.py(新), tests/test_m2s6_followups.py(新), benchmarks/report-m2s-6-sev03.md(新), eval/semantic_golden.jsonl(172→180), eval/semantic_golden.README.md, tests/test_pg_backend.py, tests/test_sem_eval_golden.py, tests/test_ops_02_monthly.py(R1 修正——UTC 跨日 flaky 造数钉死 OCT), tests/迁移水位断言×7(scaf_03/v11/sem_01/regress/pg_scaff/build_04/test 迁移挪 0010/0012), **R2 增量**: app.py, core/semantic/build.py(+_repair_fuzzy_index_if_needed 对账修复), core/semantic/fuzzy.py(vec_skipped 修正+code/sync 键不嵌向量), core/semantic/localac.py(normalize_alias 显式导出), store/backend.py(+sem_fuzzy_index_stats/sem_update_build_stats), store/sqlite/backend.py, store/postgres/backend.py, api/semantic.py, mcp/server.py, .env.example(+4 配置), tests/test_r2_m2s6_fixes.py(新 9 条), tests/test_yaml_05_local_ac.py(恒真断言修正)], **R3 增量**(均在既有清单内: api/semantic.py to_thread, build.py 内容集合对账+标记触发, fuzzy.py 仅排除 code, lookup.py/worker·runner.py 注释, tests/test_r2_m2s6_fixes.py +2 用例——R3 实际 6 files +219/−44)]
endReason: null
createdAt: 2026-10-31T22:55:35+0800          # 创建时间（30 天清理审计用，见 README §4.5）
updatedAt: 2026-11-01T10:37:59+0800          # 每次写检查点必更新为当前时间（ISO 8601 含时区），不得沿用旧值
---

# task-knowledge-lattice-m2s-6: M2-S3 收口段——实体召回路+越权矩阵+模糊兜底+检索增益（语义轨道收官）

## 任务原文

**段定义**（design §8 M2-S3 第 3 项+验收句 L1299；_m2-plan row 10）：search 实体召回路（复用 §5.1 ACL 产物）+ 三路 RRF + matched_entities + 越权矩阵 T-S7/S8/S9 + 检索增益评测（不回退才默认开启）+ 模糊兜底三层 + agent 中间件切换；验收 **T-S7~S10 全**（T-S10 已随 m2s-5 交付）+ **AC+模糊 recall@3≥0.92**。

**A 主线**：
- **A1 实体召回路**（§5.10；TC-TAG-04/05；T-S8 面）：search（MCP+REST）新增 `entities`（≤20）/`auto_entities` 参数；auto_entities 识别钉 **api/mcp 层**（§3 规则 2——core 两包不交叉）；`semantic.expand(ids, ENTITY_RECALL_RELS=refers_to/has_field/maps_to/related_to, depth=1)` ≤50、**不沿 uses**；`recall_by_entities` 双方言 SQL（种子 1.0/扩展 0.5、k_entity=30、**复用 §5.1 visible_docs 同一 ACL 编译产物**——TC-ACL-06 CTE 同构断言扩展到实体路）；三路 RRF（实体路 k 相同、权重可配默认 1.0）→ ACL 兜底断言 → rerank（§5.2 顺序不变）；返回块附 `matched_entities`
- **A2 越权矩阵**（T-S7/S8/S9，双后端 CI 常跑、并入越权用例集）：**T-S7** 组织隔离（A 组织 annotate/get_entity/search_entities 不返回 B 组织任何实体、dict_rev 独立）；**T-S8** 实体召回不放宽 ACL（同一用户同一查询 FTS/向量/实体三路并集 ⊆ 可见块集合；无权文档里命中实体的块实体路也召回不到）；**T-S9** restricted（无权 annotate 无 span、get_entity 404、关系展开不出现）
- **A3 模糊兜底三层**（TC-SEM-09；§5.8 构建产物）：构建侧产出**模糊索引**（名称/别名/一句话定义向量经 Embedder provider 存 **sem_vec**（标签入 dict_rev——换模型强制重算）+**拼音辅助表**+**编辑距离辅助表**——迁移入 store/<dialect>/migrations/semantic/）；annotate `fuzzy=true`：同音错字（拼音完全匹配）→ 编辑距离 1（长度 ≥4 别名）→ 语义近邻（阈值 0.75 top-3）；结果 `via='fuzzy'`、confidence 低于第 1 层、落 candidates；jieba 词性筛选只对名词片段跑；G-2 触发者/消费者口径按用户拍板落地（见需求确认）
- **A4 检索增益评测**（TC-SEV-03）：docs 黄金集开/关实体召回路对比 **recall@10 与 MRR**——不回退才允许 `auto_entities` 默认开启、否则保持显式参数；**AC+模糊 recall@3≥0.92** 一并断言；**错别字正样本补入黄金集**（TC-SEV-01 v1.9.8 注记兑现）；评测报告落 benchmarks/
- **A5 中间件切换与过渡期一致**（TC-SEM-08/TC-YAML-05）：规范化函数与 schema 抽小 package 两端共用——同一 YAML+同一文本本地 AC（过渡期 package）vs 服务端 annotate **mentions 完全一致**；灰度对比记录（评测集载体）；中间件注入规则契约（confidence=1.0 非歧义注入 L1/歧义只注候选/≤600 token 截断/annotate 200ms 超时本轮跳过——中间件住 agent 侧，本侧验收为接口契约+灰度对比记录）

**B 顺手**（G-21 未闭 P3 按 Committer 登记逐项核销或再挂）：annotate 端点仅捕 ValueError/`/semantic/l0` 无 build 返回空片段（TC-SEM-06 注句）/latin 去空白粘接/alias confidence=0.95/mixed-mode 候选级门槛/double_build 名实/l0_extra 未消费/**search_entities label 模糊 LIKE 骨架 → 模糊索引升级**（v1.9.5 ②登记 M2-S3 项）

**不做**：语义层 web 视图（段定义可选项——默认不做）；TC-PERF-05（→m2-5 兜底）；TC-UI（用户侧）。

**验收标准**：T-S7/S8/S9 全绿（双后端）+ TC-TAG-04/05 + TC-SEM-08/09 + TC-SEV-03 + TC-YAML-05 + AC+模糊 recall@3≥0.92 + 检索增益不回退判定；门禁双后端双模式 0 skipped、基线 1386+1 只增不减。

## 需求确认
- [x] 用户已确认（2026-10-31 22:58——任务书 A1~A5/B 范围+G-2 裁定「并存（①中间件注入 candidates 提示+②工具描述引导 agent 自调）」；确认后 status=implementing）
- 历史遗留事项清单（supervised-coding 扫描汇总）：
  - m2s-5 检查点遗留节（3 项已闭）→ 移交清单并入本任务书：TC-TAG-04/05、TC-SEM-08/09+错别字正样本、TC-SEV-03+检索增益、TC-YAML-05、T-S7~S9 越权矩阵、G-21 未闭 P3 顺手（_m2-plan row 10 权威）✅ 已全部入任务书 A1~A5/B
  - TC-PERF-05 → m2-5 兜底（不并入本段——去向不变）
  - TC-UI-01~04 手动走查 → 用户侧待办（不并入——持续挂账）
- **G-2 澄清裁定（2026-10-31 用户拍板）**：**并存**——①中间件注入 fuzzy candidates 一行提示（低信任措辞、计入 600 token 预算）+②annotate 工具描述引导 agent「L1 无命中且判断有业务对象时自行调 annotate(fuzzy=true)」。design §6.3 中间件规则补写+TC-SEM-08/09 注记随本段 docs 批（监督侧交付归档落笔——非决策变更：规格空白补写）。
- **R1 边界 8 条裁定（2026-11-01 08:51 用户「按建议执行」——按 Committer 意见打包）**：
  1. T-S7 验收口径 → **按任务书三端点收口**（annotate/get_entity/search_entities）；describe_table+l0 显式断言 P3 登记下批补
  2. T-S9⑥ 查询级异步审计 → **登记 known-gaps**（FR-6 既有缺口+A-16 待实现确认，本段不补实现；T-S9 按①~⑤+持权路径验收）
  3. §6.3③ restricted 持权可见面 → **注记口径**：POC 阶段仅 annotate/get_entity 放行，search_entities/describe_table 持权保持 fail-closed（docs 批注记）
  4. sem_restricted 授予载体 → **注记口径**：membership role 承载、POC 仅 DB/dev 工具授予无管理面入口（docs 批落 design §6.3 注记+DDL role 注释+known-gaps）
  5. 模糊索引原子性 → **「最终一致+修复路径」为正式口径**，P2-1 修复须给出真实收敛路径（写库纳入 ready 切换同事务或 skipped 分支对账补写），docs 批写明
  6. §5.9 工程口径 → **docs 批注记**（实词族+编辑距离层含 name 偏差一并补登）
  7. 黄金集 172→180+pos_typo 排除分母 → **TEST-CASES 回写**（非决策注记）
  8. auto_entities 默认 false → **docs 登记**（§6.1 bool=false 既有契约，保守档理由随报告）
  - R2 修复范围=P2-1/P2-2/P2-3 + 顺手项（Tester P3-3 恒真断言一行改直接断言）；P3 其余登记下批/docs 批（监督侧落笔）

## 遗留事项（跨任务移交）
- [x] 无——m2s-5 移交清单全清偿（TC-TAG-04/05、TC-SEM-08/09+错别字正样本、TC-SEV-03+检索增益、TC-YAML-05、T-S7~S9、G-21 未闭 P3 顺手——来源 task-knowledge-lattice-m2s-5，随本段交付 ✅）
- [ ] → **m2-5**（性能兜底轮）：TC-PERF-05（含 m2s-6 新增面：`_repair` per-skip 全量重算 pypinyin 开销、search_entities vec 档超时/熔断/降级审计〔G-24③④〕、模糊内存面 dict 全量复制+vec top-3 硬编码〔G-24④⑤〕）
- [ ] → **下批语义 followups**（Committer R3 §6.2，来源本段 R3 登记）：①G-23 残余收口——`embed_model` 入内容集合+标记清除/移除+「模型迁移崩溃窗口」回归+「再次 skipped 不重触」断言；②显式断言三补——T-S7 describe_table/l0、T-S8 真随机向量三路、T-S9⑥（依赖 G-22 查询级审计落地）；③R1 P3 残留（G-24 清单：持权审计两漏记/auto_entities 超长降级/L1 disambiguation/审计常量登记处/评测报告 TokenBag 方法学/matched_entities 空数组形态——docs 口径已注记）；④构建产物 code versioning（G-23⑤）
- [ ] → **known-gap 挂账**（非任务）：G-22 查询级异步审计 FR-6 实现（T-S9⑥/A-16 挂起——建议独立任务/主线段）；G-24① sem_restricted 管理面授予入口（POC 仅 DB/dev）
- [ ] → **用户侧**：TC-UI-01~04 手动走查（M1 里程碑待勾——持续挂账）
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- **R1: coder 完成**（2026-11-01 08:02，ses_e6d824166ffepujpoFdBzz1iAA，commit `f5fe7c8`）：A1 实体召回路（recall.py resolve_query_entities 种子≤20+expand depth=1≤50 不沿 uses+recall_by_entities 双方言——**与基础/FTS/向量路同一 visible_docs CTE 同一 Plan**〔T-S8〕+retrieve.py 三路 RRF+matched_entities）+A2 越权矩阵 T-S7/S8/S9（test_matrix_ts7_ts9.py 双后端+sem_restricted role+权限审计）+A3 模糊兜底三层（fuzzy.py 拼音完全匹配/编辑距离 deletion neighborhood/向量经 Embedder+0009 双方言迁移 sem_fuzzy_terms·sem_fuzzy_dels+annotator fuzzy 面+lookup 拼音/向量层）+A4 检索增益评测（**不回退判定通过**：recall@10 sqlite +10.72pp/pg +12.50pp、MRR 均升；**auto_entities 默认 False 保守档**；AC+模糊 recall@3=1.0≥0.92；黄金集 172→180 +8 pos_typo；报告 benchmarks/report-m2s-6-sev03.md）+A5 中间件契约（middleware.py G-2 并存①②+localac.py 本端 AC 两端一致 14/14+test_yaml_05 灰度对比记录）+B G-21 核销 6 项/再挂 2 项（mixed-mode 候选级门槛、l0_extra 未消费——再挂论证在 test 注释）。自测：**门禁 GATE PASS 1460+1 双后端双模式 0 skipped**（基线 1386+1 → +74 只增不减）。规格登记 6 条（auto_entities 默认值裁量/sem_restricted 授予载体/pos_typo 口径+TEST-CASES「172 条」数字待回写/§5.9 实词族工程口径/模糊索引写库时机/G-2 落地形态）——待监督侧 docs 批落笔。
- **R1: 打回修正**（2026-11-01 08:05，supervised-coding——用户发现）：uv.lock 全量源污染——f5fe7c8 中 2946 处 aliyun 镜像 url（基线全为官方 files.pythonhosted.org，且官方源的 size/upload-time 字段丢失），根因推断为 coder 环境全局 uv 镜像配置在 `uv lock` 时全量重写；pyproject.toml 本身干净（仅 +pypinyin）。指令：官方源（UV_DEFAULT_INDEX=https://pypi.org/simple）重新 lock，diff 口径=基线 uv.lock 仅新增 pypinyin 相关条目、零 aliyun 字样；重跑门禁；amend 重做 R1 commit。round 不变（R1 范围内修正）。
- **R1: 打回修正完成**（2026-11-01 08:19，coder 续接会话——**新 commit `e5a70d6`**〔amend 重做，45 files +3549/−150〕）：uv.lock 修复=基线 checkout 后 `UV_DEFAULT_INDEX=https://pypi.org/simple uv lock`——diff **+11 行 0 删除**（全部 pypinyin 0.55.0 官方源条目、含 size/upload-time 元数据）、`grep aliyun =0`（原 2946）、其余 pin 逐字未动、`uv lock --check`/`uv sync --locked` 通过；门禁复验 **GATE PASS 1460+1** 持平。**附带修复**：test_ops_02_monthly.py::test_seal_skips_month_with_pending_outbox UTC 跨入 2026-11 后双臂转红（既有用例隐性依赖真实时钟当月落造数月——违反造数口径，与 R1 改动无关），修正为显式 ensure_monthly_audit/ensure_month_partition 钉死 OCT+docstring 注根因。原 f5fe7c8 作废（未推送无下游依赖）。
- **R1: tester PASS**（2026-11-01 08:33，ses_e6b8618b9ffeKphrtPNpwOsB3H，testedSha=e5a70d6）：**零 P1/P2、P3×3 建议**。门禁独立复跑 1460+1 双后端双模式 0 skipped（+74 逐一对上无隐藏删减）；验收用例 T-S7/S8/S9（10）、TC-TAG-04/05（16）、TC-SEM-09（20+拼音/向量层）、TC-SEM-08（7）、TC-YAML-05（6）、TC-SEV-03（5）全绿双后端且断言质量审查为实；评测数值独立复跑与申报互锁一致（recall@10 sqlite 0.8214→0.9286 / pg 0.5→0.625、AC+模糊 recall@3=1.0、不回退判定独立确认）；uv.lock +11/0 删除零 aliyun；分层纪律核实（识别钉 api/mcp 层、新 core/semantic 四文件零方言 SQL）；TC-SEV-02 门槛数值未动 pos_typo 整体排除（登记为规格变更）；存量 8 测试文件零弱化。**P3×3**：①T-S7 describe_table 未显式入矩阵+T-S9 步骤⑥ outbox 权限事件未断言（现由旁证覆盖，建议下批补 2 条显式断言）；②l0_extra 再挂论证未落 test 注释（仅 known-gaps 旧登记——与 coder 申报表述不符，归档 docs 批补正）；③test_yaml_05_local_ac.py:106 恒真断言（hasattr 缺失亦通过——建议改直接断言）。报告全文见「最新验证意见原文」details 块（R1 Tester）。
- **R1: committer NEEDS_CHANGES**（2026-11-01 08:47，ses_e6b7517f3ffeqOfvT2TYOYMKEk，审查对象 e5a70d6——NEEDS_CHANGES 惯例 reviewedSha 不置位保持 null）：**P1 无、P2×3、P3×13、需求边界 8 条**。P2-1 模糊索引向量链路 inline 断线（app.py 未传 _embedder）+写库在 ready 切换后失败不自愈（同 dict_rev skip 不补写）+embed_fn=None 时 vec_skipped=False 误报；P2-2 向量层生产链路双方言零测试+search_entities 端点（REST/MCP）未注入 settings/embedder 致 via='vec' 永远跳层+工具描述与实现矛盾；P2-3 .env.example 漏 4 新配置（K_ENTITY/ENTITY_ROUTE_WEIGHT/FUZZY_VEC_THRESHOLD/FUZZY_VEC_TOP——m2s-5 P2-4 先例）。P3 要点：审计常量未入 domain 登记处/持权审计两漏记（include=attrs 根实体+关系展开 restricted 端点）/编辑距离层含 name 与 §5.9 字面偏差/模糊内存面全量 dict 复制（NFR-11 风险）/top-3 硬编码/auto_entities 不降级（query>4000 字 400 整次检索）/协议签名陈旧×3/中间件 L1 缺 disambiguation/评测报告方法学不符（TokenBag vs FakeEmbedder）/测试覆盖缺口（cap50 未触发/T-S8 未启向量路三路只测两路/k_entity 未验路由消费/恒真断言）/LLM 工具描述未提 entities/matched_entities 口径/G-21 再挂未入库。**需求边界 8 条上报用户**（T-S7 五端点 vs 任务书三端点/T-S9⑥ 查询级审计全库未实现——Tester"旁证覆盖"结论被推翻/§6.3③ restricted 持权可见面字面含 search_entities·describe_table 实现仅 annotate·get_entity/sem_restricted 授予载体无管理入口/模糊索引原子性与 §5.8·T-S12 冲突——P2-1 修法依赖此口径/§5.9 实词族+name 入编辑距离层口径/黄金集 172→180 回写/auto_entities 默认 false 登记）。Tester P3×3 处置：①部分采纳（describe_table+l0 下批补显式断言；T-S9⑥ 不采纳旁证结论按边界上报）②采纳 docs 批补正③采纳 R2 顺手改。规格登记 6 条裁定：全部非决策可 docs 批（#5 须先修 P2-1 再登记）。报告全文见「最新验证意见原文」details 块（R1 Committer）。
- **R2: coder 完成**（2026-11-01 09:17，ses_e6d824166ffepujpoFdBzz1iAA 续接，commit `e7fac5c`，12 files +604/−31）：**P2-1** ✅ 四子项全修（inline WorkerServices 补 _embedder；收敛路径取裁定 5「skipped 对账补写」形态——_repair_fuzzy_index_if_needed 行缺失或向量覆盖<可嵌基准且有 embedder 时整替补写、只补缺不降级；index_write_failed 经 sem_update_build_stats 持久化 build_report 可见；embed_fn=None→vec_skipped=True；永久用例 5 条含写失败→skipped 修复/inline 有向量/一致态零空转）；**P2-2** ✅ 方案①（REST/MCP search_entities 注入 settings/embedder；工具描述三处对齐——SEARCH_ENTITIES 排序链/模块 docstring/SEARCH 补实体参数〔P3-11 顺手〕；via='vec'/阈值过滤/去重三断言+REST 真链路+A3 生产路径真链路〔annotate fuzzy→embed→sem_fuzzy_vec_search，零注入〕）；**附带发现并修复真实缺陷**：code/sync 类源系统键别名嵌向量与确定性 embedder default 向量碰撞（伪命中面）——改为不嵌（拼音/编辑距离面保留）+stats 增 vec_expected；**P2-3** ✅ .env.example 93→103 行；**顺手 P3-3** ✅ 恒真断言改直接断言+localac 模块级显式导出 normalize_alias。自测：**门禁 GATE PASS 1475+1 双后端双模式 0 skipped**（1460+1→+15 逐位对上）。P3 其余登记不动、docs/ 零改动、origin/develop 仍=60370d0。
- **R2: tester PASS**（2026-11-01 09:27，ses_e6b8618b9ffeKphrtPNpwOsB3H 续接，testedSha=e7fac5c）：**零 P1/P2、P3×2 建议**。门禁独立复跑 **1475+1** 双后端双模式 0 skipped（+15 构成可完全对账：6 双后端×2+3 sqlite 专有）；P2-1 四子项落地核实（inline 用例走真实 create_app+TestClient+inline worker 生产形态、收敛链完整〔写失败→持久化→skipped 补齐→fuzzy_repaired 注记〕、一致态零补写幂等断言、stats 从库内读断言）；P2-2 接线为真（app.py:74 依赖容器核实 self.embedder、A3 真链路零注入核实——无 vec_lookup 注入/链上无 monkeypatch、阴性对照先证）、三断言为实（_MappingEmbedder 排除 AC 层假阳性）；附带变更（code/sync 不嵌向量）口径溯源（sync.py:439-440 实证源系统键、name/YAML 别名/定义句向量保留、del 键独立于 embed 标志）+评测零劣化（数值与 R1 逐位一致双证）；R1 验收面 81 passed 零回归；R1 P3×3 处置核对（③已修、①②零触碰按裁定登记）。**P3×2**：①_repair docstring「只补缺不降级」在 embedder 故障边缘形态不严格成立（收敛性仍由裁定 5 机制保证——建议措辞收敛或注释登记）；②test_r2_m2s6_fixes.py docstring「sqlite 单后端」少报自述与实际不符（6/9 实为双后端参数化）。报告全文见「最新验证意见原文」details 块（R2 Tester）。
- **R2: committer NEEDS_CHANGES**（2026-11-01 09:35，ses_e6b7517f3ffeqOfvT2TYOYMKEk 续接，审查对象 e7fac5c——reviewedSha 保持 null）：**P1 无、P2×2、P3×9**。R1 P2×3 闭环结论：P2-1 基本闭环（残留见新 P2-2）、P2-2 本体闭环（但注入引入新 P2-1）、P2-3 闭环、P3-3/P3-11 闭环、范围纪律 ✓；附带变更（code/sync 不嵌向量）口径溯源属实+评测零劣化，但「真实缺陷」论证不成立/过度——碰撞仅在测试替身 default 向量下出现，code 排除可辩护、**sync 是源系统别名非键**排除使 §5.8 别名面向变窄（P3-1：建议仅排除 code 恢复 sync+去重断言改 manual/abbr+docstring 同步）。**新 P2-1（R2 引入回归）**：REST /semantic/entities 在 async handler 内同步调 embedder.embed（httpx 同步 Client 超时 30s）阻塞事件循环——违反 §5.2/NFR-8，端点其余语义读均走 asyncio.to_thread 此处唯一例外；修复=await asyncio.to_thread 包住 search_entities 调用。**新 P2-2（裁定 5 未完全兑现）**：skipped 对账条件纯计数/覆盖（terms 行数+vec 覆盖），无法发现「内容陈旧」（词典收缩/等行数改名）——写失败/崩溃后上一 rev 索引若行数不低则永不修复（静态词典=永久陈旧，正是 R1 指出形态）；修复=用 expected term_rows 集合与 sem_fuzzy_terms_all 内容对账（不等即整替）+index_write_failed 持久化标记作附加触发+补「词典收缩+写失败→skipped 修复」用例。P3：①code/sync 正当性（含 fuzzy 模块 docstring 未更新+去重断言空转）②_repair docstring 笔误（< terms 应为 < expect_vec）+边缘措辞③test_r2 docstring 少报④_repair 性能（每次 skipped 全量重算 pypinyin）⑤vec 档无有界超时/降级审计⑥fuzzy docstring⑦fuzzy_repaired 观测语义⑧陈旧注释×2（runner.py:72/lookup.py:78）⑨R1 P3 残留汇总。Tester R2 P3×2 处置：均转 R3 修（docstring 笔误+措辞/少报）。交付归档预备清单详见报告 §6。**round=3（maxRounds=3 最后一轮）**。报告全文见「最新验证意见原文」details 块（R2 Committer）。
- **R3: coder 完成**（2026-11-01 09:55，ses_e6d824166ffepujpoFdBzz1iAA 续接，commit `4057b40`，6 files +219/−44）：**P2-1** ✅ REST /semantic/entities 改 `await asyncio.to_thread(search_entities, …)`（ValueError 包 await，与 annotate/get_entity 形态对齐——30s 阻断面消除）；**P2-2** ✅ `_repair_fuzzy_index_if_needed` 重写为**内容集合对账**（期望 {(entity_id,kind,text_norm)} vs sem_fuzzy_terms_all，任何不等即整替——收缩/等行数改名盲区覆盖）+向量覆盖判定+**落库标记附加触发**（_fuzzy_failure_marker：current 行 stats.fuzzy 的 index_write_failed/vec_skipped——崩溃场景线索）；TDD 先红后绿（收缩+写失败/等行数改名/人工置标记三场景修复前红）；**P3-1** ✅ 仅排除 code、sync 恢复嵌向量（§5.8 别名面），去重断言不再空转（sync 别名「留抵税额」恢复真实双 term），fuzzy docstring term face 同步；**P3-2/P3-3/顺手 P3-8** ✅ docstring 笔误+边缘措辞/测试 docstring 少报/runner·lookup 两处陈旧注释。自测：**门禁 GATE PASS 1479+1 双后端双模式 0 skipped**（1475+1→+4=2 新用例×双臂）。P3-4/5/6/7/9 登记不动、docs/ 零改动、origin/develop 仍=60370d0。
- **R3: tester PASS**（2026-11-01 10:09，ses_e6b8618b9ffeKphrtPNpwOsB3H 续接，testedSha=4057b40）：**零 P1/P2、P3×1 建议**。门禁独立复跑 **1479+1** 双后端双模式 0 skipped（+4=2 新用例×双臂逐位对账）；P2-1 闭环（to_thread 下放+grep 无残留同步调用、端点行为不变、R2 修复面 19 跑全绿）；P2-2 闭环（**内容集合对账为真**——三元组集合比对非计数、向量覆盖 elif、_fuzzy_failure_marker 落库线索真实可达〔sem_current_build 双方言含 stats_json〕；**TDD 先红等价性实证**——脚本在 R2 旧对账条件 vs R3 新条件上求值：三场景旧条件 need=False/恒 False、新条件 True，先红申报属实；修复后 have==expected 逐位断言+幂等保留）；P3-1 闭环（sync 恢复嵌入、**去重断言由空转转实**——c.voucher 实测 3 向量 term、唯一 NULL=code 键恰为口径；评测三连轮数值逐位一致）；P3-2/3/8 落笔核实；P3-4/5/6/7/9 零触碰（annotator/recall/store·backend/middleware 不在 diff）；R1/R2 验收面 81 passed+修复面 19 passed 零回归；纪律面合规。**P3×1**：持久化标记粘滞（修复触发不清 index_write_failed/vec_skipped——静态词典下每次 skipped 重触整替，功能无害〔幂等收敛〕但与 P3-4/P3-7 同族放大；建议 docs 批裁定 5 注记一并写入或下批修复路径尾部清标记收口）。报告全文见「最新验证意见原文」details 块（R3 Tester）。
- **R3: committer APPROVED**（2026-11-01 10:15，ses_e6b7517f3ffeqOfvT2TYOYMKEk 续接，reviewedSha=4057b40=testedSha=HEAD 三一致）：**P1/P2 无，P3 登记级**。R2 P2×2 逐条闭环（P2-1 to_thread 下放+ThreadLocalBackend 跨线程保证；P2-2 两形态全闭——收缩/改名由内容集合覆盖、写失败由落库标记覆盖，TDD 先红经 Tester 实证）；P3-1 三子问题闭（§5.8 别名面恢复/去重转实/docstring 更新——test 内两处过期注释遗留 P3）；范围纪律合规；新引入面无新 P1/P2（内容对账性能=R2 P3-4 放大面非新增；_fuzzy_failure_marker 防御解析安全；to_thread 后 ValueError→400 映射保留）。**R3 新发现 P3 登记**：①embed_model 未入内容集合（模型迁移+崩溃窗口→向量层静默为空至下次 dict_rev——一行级修法入下批，与标记粘滞合并）；②标记粘滞（Tester R3 P3-1——登记下批+docs 批裁定 5 注记）；③docstring/注释陈旧×6（"崩溃场景落库线索"表述不准〔崩溃无标记，标记=已捕获写失败〕等）；④_repair per-skip 全量重算（→m2-5）；⑤vec 档无有界超时/降级审计（→m2-5）；⑥R1 P3 残留清单；⑦构建产物 code versioning 未入 dict_rev（known-gaps 登记）；⑧.env.example 行数 metadata nit（101 非 103）。交付归档建议全量清单见报告 §6（docs 批落笔/遗留事项去向/manifest 要点）。**双通过达成（round=3 收敛）：testVerdict=PASS + reviewVerdict=APPROVED，testedSha=reviewedSha=4057b40=当前 HEAD。**
- **交付执行**（2026-11-01 10:31，用户确认交付，coder 续接会话）：① 监督侧 docs 批落笔完成（design v0.9.6——§5.8 模糊索引最终一致/§5.9 工程口径/§6.3 G-2 并存+sem_restricted 载体+restricted 持权面+查询级审计缺口/§5.10 matched_entities；TEST-CASES v1.9.10——M2-S3 整行收口+8 用例完成态注记+A-16；known-gaps——G-2 闭环+G-21 核销 6 再挂 2+G-22~G-24 新增；AGENTS/`_m2-plan` 终态——语义轨道 6/6、下一段 m2-4、门禁 1479+1）；② chore 归档批 `a1901f5`（8 文件 docs-only：4 docs+检查点+_m2-plan+监督侧 2 配置/补记——零代码文件验证通过）；③ push 成功（c519abb..a1901f5，origin/develop 仍=60370d0）；④ **PR #10 已开**（base=develop，https://github.com/yq3/knowledge-lattice/pull/10，4 commits：e5a70d6/e7fac5c/4057b40/a1901f5，body 含摘要占位——manifest JSON 待补）。遗留事项小节已回写（m2s-5 移交全清偿+m2-5/下批/known-gap/用户侧去向）。待办：Committer gh pr review 留痕 + Coder manifest 入 PR description。
- **交付完成（终态）**（2026-11-01 10:35，status=done）：① Committer PR 审查留痕——`--approve` 因 GitHub 自审限制失败（PR 作者=gh 账号 yq3），**回退 COMMENTED 形态完整留痕**（reviewNode `PRR_kwDOVZ9dhM8AAAABVUz1jg`，body 含 APPROVED 结论/全闭环/门禁/残余登记/合人留给所有者——沿 #2~#9 先例）；② Coder manifest JSON 入 PR #10 description（摘要保留+Evidence Manifest 追加，沿 PR #9 schema：双 SHA 4057b40/headSha a1901f5+shaNote/gate 四轮计数/evalMetrics/specRulings/gapClosures·Registrations/handover/sessions/checkpoint——json.load 校验合法）；③ 未执行 merge（协议约定）。**PR #10 OPEN/MERGEABLE/CLEAN 待用户合入**：https://github.com/yq3/knowledge-lattice/pull/10。本终态条目为 chore 批 a1901f5 之后的工作区改动（随下段 chore 归档批入库——沿 m2s-3 先例）。
- **合入**（2026-11-01 10:37，用户确认）：**PR #10 MERGED**——mergeCommit `eef7acf1412c90f1e97f3993d129423fd215a319`（2026-11-01T02:37:52Z，merge 形态沿先例、远端分支保留）。origin/develop 前进至 eef7acf；下段（m2-4）开工时 develop_opencode 先 ff 至此基线。

## 最新验证意见原文

<details>
<summary>R1 Tester 报告（2026-11-01 08:33，ses_e6b8618b9ffeKphrtPNpwOsB3H，testVerdict=PASS）</summary>

持权审计已在 api/mcp 两层真实端点接线。全部核验完成，出具验证报告。

---

# 验证报告：task-knowledge-lattice-m2s-6 R1（Tester）

## 1. testVerdict: **PASS**（零 P1/P2，3 项 P3 建议）

## 2. testedSha: `e5a70d6acf69e1369462cb2080469408b35ca352`（HEAD，分支 develop_opencode）

## 3. 执行记录

### 3.1 门禁全量（独立复跑）
```
docker start lattice-pg && export LATTICE_PG_DSN=... && scripts/test_gate.sh
```
- **[pytest] OK：1460 passed, 1 deselected, 2 warnings**；**[pytest-O] OK：1460 passed, 1 deselected, 3 warnings** —— 双模式全绿
- **0 skipped**（1 deselected = manual 标记 TC-UI 组，属门禁排除口径非 skip）
- **pg 臂 519 条全实跑**（[pg] 参数化 486 + PG 专用 33）> 0 ✓
- 基线 1386+1 → **1460+1，+74 只增不减** ✓（与 coder 申报 1460+1 逐位一致）
- 新增 74 例 = 验收文件复跑合计（69+5）逐一对上，无隐藏删减

### 3.2 验收用例逐项（独立复跑 + 断言审查）
| 用例 | 文件 | 结果 | 断言质量 |
|---|---|---|---|
| T-S7/S8/S9 | test_matrix_ts7_ts9.py（5×2 后端=10） | 全绿 | 实：跨组织 entity_id 逐位比对、三路并集 ⊆ 可见集（独立重编译 plan + `recall_by_entities` 直查 d_os 排除）、restricted 四面静默 + 持权路径（role=sem_restricted 门 + org_admin 不兼任 + outbox 权限事件）|
| TC-TAG-04/05 | test_tag_04_entity_recall.py（8×2=16） | 全绿 | 实：uses 不进扩展集、≤50 保序、种子 2.0 vs 扩展 0.5 精确分值、`matched_entities`、RRF 权重可配；**TC-ACL-06 CTE 同构为真实同构**——核对 store 双方言 `render_entity_recall_select` 均复用 `_CTE_PREFIX`+`_build_cte_where_neutral(plan)`，与基础/向量路同一构造，归一化后逐字相等断言有效 |
| TC-SEM-09 | test_sem_09_fuzzy.py（10×2=20） | 全绿 | 实：三层逐层独立断言（pinyin 0.75/edit 0.65/vec 0.55 均低于第 1 层 0.9）、依次短路、构建产物（sem_fuzzy_terms 三 kind+dels≥4 门槛+vec_embedded>0）、embedder 失败降级不阻断、restricted 不进模糊索引、fuzzy 不进 mentions |
| TC-SEM-08 | test_sem_08_middleware.py（7） | 全绿 | 实：confidence=1.0 按类型注入/alias 0.95 不注入/歧义只注候选/fuzzy「疑似」低信任行+计 token/600 预算截断/常量 200ms·600/G-2② 工具描述引导句（MCP 常量断言）|
| TC-YAML-05 | test_yaml_05_local_ac.py（3×2=6） | 全绿 | 实：7 文本 mentions **逐字段相等**（span/entity/confidence/via/matched_by/resolved_by）；灰度对比 14 条本地 ⊆ 服务端 + ≥90% 一致（实测 100%，报告互证）；唯一瑕疵见 P3-3 |
| TC-SEV-03 | test_sev_03_entity_route_eval.py（5） | 全绿 | 实：不回退判定（on≥off−1e-9）+ **报告数字与实测互锁**（数字漂移即红）+ 默认 False 断言；黄金集校验测试含 pos_typo 入 KINDS |

**评测数值独立复跑**（临时脚本复现后即删，非采信申报）：
- sqlite：off recall@10=**0.8214**/MRR=0.3372 → on **0.9286**/MRR=0.4087 —— 与申报 0.8214→0.9286 一致 ✓
- pg：off **0.5**/MRR=0.4734 → on **0.625**/MRR=0.5142 —— 与申报一致 ✓
- **AC+模糊 recall@3 = 1.0**（适用面 145 条/159 标注）双后端一致 ≥0.92 ✓；MRR 双后端均升——**不回退判定独立确认** ✓

### 3.3 专项核验
- **uv.lock 源纯净**：`git diff 60370d0 HEAD -- uv.lock` = **+11 行 0 删除**，全部 pypinyin 0.55.0 官方源条目（registry=pypi.org、含 size/upload-time 元数据）；`grep -c mirrors.aliyun.com uv.lock` = **0**；pyproject 仅 +`pypinyin`；`uv lock --check` 通过 ✓
- **附带修复合规**：test_ops_02_monthly.py 显式 `ensure_monthly_audit/ensure_month_partition` 钉死 OCT + docstring 注明 UTC 跨日根因——符合「时间依赖一律造数」口径，与 R1 特性无关的既有 flaky 修复 ✓
- **G-21 核销**：任务书 8 项 = 核销 6（annotate 500 兜底/l0 空片段/latin 粘接行为锁定/alias 0.95 设计意图确认/double_build 名实改名/`search_entities` 拼音层升级）+ 再挂 2（mixed-mode——再挂论证在 test_sem_09_fuzzy.py:263 文档串；l0_extra——**test 注释未见，见 P3-2**）
- **分层纪律**：识别钉 api/mcp 层核实——api/search.py 与 mcp/server.py 调 `resolve_query_entities` 后以 `entity_ids/entity_seeds` 注入，core/docs/retrieve.py 不 import 语义识别；新 core/semantic 文件（recall/fuzzy/localac/middleware）**零方言 SQL**（SQL 全在 store 层，双方言 0009 迁移同构）✓
- **TC-SEV-02 口径**：门槛 precision 0.95/recall 0.80/歧义 0.85/neg 0.05 **数值未动**；pos_typo 从 AC 层评测整体排除（neg 独立计数、歧义 span 分母逻辑原样）——排除已登记为规格变更（m2s-6 六条规格登记之一），属「AC 设计面 miss 不稀释分母」方向，非稀释 ✓
- **存量测试零弱化**：8 个存量测试文件改动逐一核过——水位断言 [6,7,8]→[6,7,8,9]/探针 0009→0010（断言加强非削弱）、pg_backend NotImplementedError→实行为断言（方法已实装）、sem_eval_golden 改名（G-21 P3-7 名实，确定性断言保留）、ops_02 造数钉死。**无任何存量断言删除** ✓

## 4. 断言质量审查
- 未发现影响验收结论的空转断言；数值断言均为精确值（0.8214/0.9286/0.5/0.625/1.0），报告数字被测试互锁，无法漂移。
- 1 处恒真断言（P3-3，不影响结论）。
- sev_03 vec 层注入（pinyin 等价→sim 0.9）为测试脚手架确定性口径，注释有依据论证（TokenBag 噪声向量不可离线确定）；真实向量层另有 TC-SEM-05/TC-SEM-09 覆盖——可接受，非空转。

## 5. 问题清单
- **P1（阻塞）：无**
- **P2（应修）：无**
- **P3（建议）**：
  1. **T-S7 五端点中 describe_table 未在矩阵用例显式断言**、T-S9 步骤⑥「无权尝试不产生 outbox 权限事件、走查询级异步审计」未断言——现由成员关系 403（test_sem_rest_read）+ describe 白名单（T-S11）+ docs 查询审计通用套件间接覆盖；建议下批补 2 条显式断言收口 TEST-CASES 步骤全集。
  2. **l0_extra 再挂论证未落 test 注释**——检查点申报「再挂论证在 test 注释」仅 mixed-mode 成立；l0_extra 仅存 known-gaps 旧登记（未丢失但与申报表述不符）。归档 docs 批落笔时补正即可。
  3. test_yaml_05_local_ac.py:106 恒真断言（`assert localac.normalize_alias if hasattr(...) else True`——属性缺失时亦通过），建议改为直接 `assert localac.normalize_alias is norm.normalize_alias`。

**结论**：coder 申报四项（门禁 1460+1、recall@3=1.0、检索增益双后端数值、auto_entities 默认 False）经独立复跑全部属实，验收用例 T-S7/S8/S9、TC-TAG-04/05、TC-SEM-08/09、TC-SEV-03、TC-YAML-05 全绿双后端，uv.lock 修复合规，testVerdict=**PASS**。

</details>

<details>
<summary>R1 Committer 报告（2026-11-01 08:47，ses_e6b7517f3ffeqOfvT2TYOYMKEk，reviewVerdict=NEEDS_CHANGES）</summary>

# 审查报告：task-knowledge-lattice-m2s-6 R1（Committer）

## 1. reviewVerdict

**NEEDS_CHANGES**（P1 无；P2×3；进入 R2）

## 2. reviewedSha

`e5a70d6acf69e1369462cb2080469408b35ca352`（= testedSha = HEAD）
按惯例本轮 NEEDS_CHANGES **不置位**检查点 `reviewedSha`（由监督侧处理）；交付 manifest/双 SHA 留待 APPROVED 后。

## 3. 审查执行记录

**基线核对**
- `git diff 60370d0..e5a70d6` = 45 files +3549/−150，与申报一致；`docs/` 零改动（符合冻结纪律）；`scripts/` 零改动；工作区 4 个流程文档 + 未跟踪检查点为监督侧文件，未入 commit（不属审查对象）。
- 上一轮打回处置逐条核对：uv.lock 修复 = **+11/−0**，全为 pypinyin 0.55.0 官方源（含 size/upload-time），全仓 `mirrors.aliyun` 计数 0，pyproject 仅 +pypinyin —— **合规**；`test_ops_02_monthly.py` 显式 `ensure_monthly_audit/ensure_month_partition` 钉死 OCT，属时间造数口径修正，非弱化。
- 门禁：本会话为只读审查（无 pytest 执行权限），以 Tester 独立复跑原始输出为准：1460+1、双后端双模式 0 skipped、`1 deselected` 为 manual 组（口径正确）；代码侧未见与申报矛盾的 skip/删除/断言放宽。

**重点面逐项结论**

| 面 | 结论 |
|---|---|
| A1 实体召回路 | `recall_by_entities` 双方言均复用 `_CTE_PREFIX + _build_cte_where_neutral(plan)` 与外层同一 `_build_outer_where_neutral`（version/tombstone/org/过滤双保险），T-S8 无旁路；种子 1.0/扩展 0.5、`k_entity=30`、RRF k 同 60/权重可配默认 1.0、`matched_entities` 合并正确；识别钉 api/mcp 层、core/docs 不 import annotate —— **正确** |
| A2 越权矩阵 | T-S8 直查实体路 ⊆ 独立重编译可见集（强断言）；T-S7/S9 静默面成立；持权路径 role=`sem_restricted` + outbox 权限事件存在；缺 endpoint 级断言与 T-S9⑥（见 P3/边界） |
| A3 模糊兜底 | 0009 双方言等价（表/CHECK/FK/索引一致，无需触发器）；embed 标签入 dict_rev ✓；拼音/编辑距离算法正确（deletion 桶 + 逐词复核防假阳）；**向量生产链路存在断线/未测（P2-1/P2-3）**；实词族口径与 name 入编辑距离层属字面偏差（P3+登记） |
| A4 评测 | 数字与测试互锁、不回退判定成立、默认 false 与 §6.1 契约一致；报告方法学描述与实测栈不符（P3） |
| A5 中间件/本地 AC | localac 复用同一 `Annotator`/`norm`/**非复制** ✓；G-2 并存①②均落地 ✓；L1 缺 disambiguation 注入（P3） |
| 分层纪律 | 新 core/semantic 四文件零 SQL ✓；识别钉 api/mcp ✓；审计事件常量未入单一登记处（P3） |
| uv.lock | 官方源 + 最小 diff ✓ |

## 4. 问题清单

### P1（阻塞）
- 无。

### P2（应修）

**P2-1 模糊索引向量链路：inline 模式断线 + 失败/降级不可自愈**
- `src/knowledge_lattice/app.py:259-265`：inline 模式构造 `WorkerServices` **未传 `_embedder`** → `_exec_semantic_build`（`worker/runner.py:267-271`）取到 `None` → `run_build` 以空向量写 `sem_fuzzy_terms`（inline 是配置支持的"最小部署显式选项"，非纯测试）。
- `src/knowledge_lattice/core/semantic/build.py:489-493,541-553`：`_write_fuzzy_index` 在 ready 切换**之后**写库；写失败只捕异常记日志，并把 `index_write_failed` 写进**已序列化后的内存 stats**（不落库、`build_report` 看不到）。注释"下次构建整替收敛"**不成立**：同 dict_rev 的后续构建在 `build.py:337-345` 直接 skipped，不会补写 → 索引永久陈旧/空向量（embedder 失败同理：本次以 NULL 覆盖旧好向量，此后 skip 永不自愈）。
- `src/knowledge_lattice/core/semantic/fuzzy.py:165-179`：`embed_fn is None`（embedder 缺失）时 `vec_skipped` 仍为 `False`（仅 `vec_embedded=0`），构建报告误报"未降级"。
- 建议：① inline 装配补 `_embedder=embedder`（或复用 `build_default_services`）；② 写库纳入 ready 切换同事务（或 skipped 分支做索引存在性/向量覆盖率对账后补写，给出真实收敛路径）；③ 注入失败/写失败标记持久化进 build stats；④ `embed_fn is None` 时置 `vec_skipped=True`；⑤ 补"写失败 → 后续 skipped 构建修复"与"inline build 有向量"永久用例。

**P2-2 向量层生产链路零覆盖 + `search_entities` 端点未接线**
- TC-SEM-09 的向量层只有 `vec_lookup` 注入断言（`tests/test_sem_09_fuzzy.py:187,210`），**真正的生产路径**（`annotate_text(fuzzy=True)` → `embedder.embed` → `backend.sem_fuzzy_vec_search` → 阈值 0.75/去重/top-3）双方言**零测试**；`sem_fuzzy_vec_search` 两个方言实作均无直接用例。
- `src/knowledge_lattice/api/semantic.py:417-422` 与 `src/knowledge_lattice/mcp/server.py:489-505` 调 `search_entities` 时**未注入 settings/embedder** → `lookup.py:77-101` 的 `via='vec'` 档在 REST/MCP 永远跳层；`SEARCH_ENTITIES_TOOL_DESCRIPTION`（`mcp/server.py:111-114`）与 `mcp/server.py:36` 仍写"拼音/向量归后续段"，与 `lookup` 已声明排序链自相矛盾。`tests/test_sem_05_pinyin_vec.py:102-113` 未断言任何 `via='vec'`（实际只验证了精确档与"无 embedder 时无 vec"）。
- 建议：二选一并在检查点申报——①（推荐）两端点补 `settings=service.settings, embedder=getattr(service,"embedder",None)` + 更新工具描述；以确定性 embedder（如 `FixedVecEmbedder`）补 `via='vec'`、阈值以下过滤、实体去重三条断言；②若裁定归下批，登记 known-gaps/TEST-CASES 并把描述改回现状；无论哪种，**A3 向量层生产路径必须补一条至少单后端的真链路用例**。

**P2-3 `.env.example` 未登记 4 个新配置**
- `config.py:67-70,137-139` 新增 `LATTICE_K_ENTITY` / `LATTICE_ENTITY_ROUTE_WEIGHT` / `LATTICE_SEM_FUZZY_VEC_THRESHOLD` / `LATTICE_SEM_FUZZY_VEC_TOP`，`.env.example`（现 93 行）无对应行；m2s-5 R2 P2-4 同类问题已按 P2 处理（先例）。

### P3（建议/登记）

1. **审计事件常量未入单一登记处**：`core/semantic/constants.py:86-87` 定义 `EVENT_SEMANTIC_RESTRICTED_ACCESS`，而 `domain/audit_events.py` 自述为"事件类型单一登记处"（M2-2 B1 纪律）；建议迁入并补 `__all__`。
2. **持权审计两处漏记**：`mcp/server.py:484-486` 以 `result["entity"].get("curated") is not None` 为审计前提——`include=['attrs']` 时 restricted 根实体访问不落审计；另经关系展开"看到"restricted 端点（非根）也不审计（FR-6 "restricted 实体访问属权限事件"）。建议按 `_entity_is_restricted` 直接判定，展开面按 nodes 中 restricted 端点补记或登记口径。
3. **编辑距离层 term 含 name**：`fuzzy.py:182-188` 对 `kind in (name, alias)` 建删除键，design §5.9 字面为"仅长度 ≥4 别名"；与"实词族"一并 docs 登记，或收紧 kind=alias（需复核 recall@3 是否仍 ≥0.92）。
4. **模糊内存面性能**：`annotator.py:426-428` 每个片段 `dict(self._fuzzy_pinyin)`/`dict(self._fuzzy_dels)` 全量复制（10⁴~10⁵ 实体下 del 索引可达百万键，NFR-11 annotate P99 20ms 风险）；`annotator.py:203-216` 无条件构建模糊面并与 build 侧重复计算 pypinyin。建议直传映射、按需惰性构建。
5. **top-3 硬编码**：`annotator.py:447` 固定 `if len(seen) >= 3`，未消费 `settings.semantic_fuzzy_vec_top`（配置改大无效）。
6. **auto_entities 不降级**：`recall.py:59-63` 对 annotate 的 `ValueError` 原样上抛；query >4000 字时 `auto_entities=true` 会 400 整次检索，与"增益路失败不阻断检索"相悖。建议仅 `entities` 计数校验抛 400，auto 分支 ValueError 也返回 None。
7. **Protocol 签名/文档陈旧**：`store/backend.py:1005` `sem_expand_graph` 缺 `include_restricted`，`:1024` `sem_search_entities` 缺 `q_pinyin`；`sem_fuzzy_terms_all`（`:134`）文档称"annotate fuzzy 内存面装载"，实际生产未调用（仅测试用）——同步签名/文档或接线。
8. **中间件 L1 缺 disambiguation**：`middleware.py:50-55` 概念行只有 name+brief；design §6.3② 要求 name+brief+disambiguation（mention 契约未携带该字段）。建议 annotate 输出补字段或登记参考实现口径。
9. **评测报告方法学不符**：`benchmarks/report-m2s-6-sev03.md:7` 写 `TokenBagEmbedder(dim=32)`，实际 `tests/test_sev_03_entity_route_eval.py:91` 用 `FakeEmbedder(dim=32, model_name="tokbag-embed")`（哈希噪声向量，`TokenBagEmbedder` 仅 import 未用）。修正报告或换真 TokenBag 并更新互锁数字。
10. **测试覆盖缺口**（除 P2-2 外）：
    - `test_tag_04_entity_recall.py:131-167` "cap 50" 用例实际只有 20 seeds+20 扩展=40，未触发 50 截断；且未断言 2 跳字段（TPL…TAX_AMT）不在扩展集（depth=1 未钉死）。
    - `test_matrix_ts7_ts9.py:171-200` T-S8 未启向量路（无 embedder），"三路"只测两路；T-S7 缺 describe_table/l0；T-S9 缺步骤⑥。
    - `test_tag_04:210-212` k_entity 只断言常量，未验证路由消费。
    - `test_yaml_05_local_ac.py:106` 恒真断言（Tester P3-3）。
11. **LLM 面契约文案**：`mcp/server.py:81-85` `SEARCH_TOOL_DESCRIPTION` 未提 `entities`/`auto_entities`（§6.1 "写给 LLM 看"纪律）；与 P2-2 的 `SEARCH_ENTITIES_TOOL_DESCRIPTION` 一并更新。
12. **matched_entities 口径**：`core/docs/retrieve.py:513-517` 只在实体路命中的块出现；"启用实体路但仅 FTS/向量命中"的块无该字段，与 §5.10"返回的每个块附 matched_entities"字面有出入——建议契约注记（或启用时统一给空数组）。
13. **G-21 再挂未入库**：mixed-mode/l0_extra 两项"再挂"目前只在 test 注释/旧 known-gaps 行，需 docs 批回写（监督侧）。

## 5. 需求边界问题（交监督侧/spec 确认，不写 coder）

1. **T-S7 五端点 vs 任务书 A2 三端点**：TEST-CASES T-S7 含 describe_table / `/semantic/l0`，任务书 A2 只列 annotate/get_entity/search_entities；验收口径需统一（当前实现 coverage 按任务书）。
2. **T-S9 步骤⑥依赖的"查询级异步审计"全库未实现**：仓库只有 outbox 审计，`annotate/get_entity` 无查询级审计写入（docs 检索同样没有）。Tester 报告"现由 docs 查询审计通用套件间接覆盖"**不成立**（grep 无任何 query-audit 用例/实现）。这是 FR-6 既有缺口，不是本段引入；但 T-S9 无法按⑥全绿——需确认是登记 known-gaps（A-16 已"待实现确认"）还是补实现（工作量另估）。
3. **design §6.3③ restricted 持权可见面**："实体、别名命中与关系展开"字面含 search_entities/describe_table；实现仅 annotate/get_entity 放行（search_entities/describe_table 持权仍 fail-closed）。需口径确认（补或注记）。
4. **`sem_restricted` 授予载体**：以 membership role 承载（D7 DDL 注释枚举为 `org_admin | member`），且无任何管理入口/端点可授予。属规格空白+实现口径，但"谁能授予、是否需管理面"若超出 POC 约定需用户确认。
5. **模糊索引是否属"原子构建产物"**：§5.8 要求构建产物随 ready 原子切换、T-S12 要求构建失败旧版继续服务；当前"ready 后写"非原子（P2-1）。需明确"最终一致 + 修复路径"作为正式口径，否则与原子切换语义冲突。
6. **§5.9 字面 vs 工程口径**：实词族（非"名词性"）、编辑距离含 name（非"仅别名"）——属工程细化还是设计回写，需 docs 批明确。
7. **黄金集 172→180 与 pos_typo 排除 TC-SEV-02 分母**：v1.9.8 已预告、README 已更新，属非决策用例注记，TEST-CASES 待回写。
8. **auto_entities 默认 false**：§6.1 明写 `bool=false`、§5.2 为"允许默认开启"（非必须），不矛盾；报告已给保守档理由——docs 登记即可。

## 6. Tester P3×3 处置意见

1. **T-S7 describe_table / T-S9⑥**：**部分采纳**。describe_table+l0 显式断言 → 下批补（P3，登记）；**T-S9⑥ 不采纳"旁证覆盖"结论**——全库无查询级审计实现（见边界 2），按需求边界上报并登记 known-gaps，不在本段代码修。
2. **l0_extra 再挂论证未落 test 注释**：**采纳**。属 docs 批补正（known-gaps G-21 残留 + 检查点表述更正），代码不动。
3. **test_yaml_05_local_ac.py:106 恒真**：**采纳**。建议本轮 R2 顺手改直接断言（`localac.normalize_alias is norm.normalize_alias`），一行。

## 7. 规格登记 6 条裁定意见

| # | 登记项 | 裁定 |
|---|---|---|
| 1 | auto_entities 默认 False | **非决策变更**（§6.1 已定 `bool=false`，§5.2 为"允许"）→ docs 批登记结论+报告理由即可 |
| 2 | sem_restricted 授予载体 | **规格空白补写（非决策）**；须 docs 批落：design §6.3 权限口径注记 + DDL role 注释 + known-gaps（无管理入口，POC 仅 DB/dev 工具）。若要求管理面授予入口 → 交用户确认（不阻塞代码） |
| 3 | pos_typo 口径 + TEST-CASES「172 条」 | **非决策**（v1.9.8 已预告、README 已改）→ TEST-CASES v1.9.10 回写 TC-SEV-01 注记/TC-SEV-02 分母排除/§六 M2-S3 行 |
| 4 | §5.9 实词族工程口径 | **非决策工程口径**（错字常被 jieba 判 v/x；只进 candidates）→ docs 批注记；**同批须补登"编辑距离层含 name"偏差**（见 P3-3），否则与冻结正文不一致 |
| 5 | 模糊索引写库时机 | 登记本身合法（规格空白），但**先修 P2-1 再登记**；docs 需写明原子性/最终一致与修复路径，不能用"下次构建整替收敛"这一不成立的表述 |
| 6 | G-2 落地形态 | **非决策**（2026-10-31 用户已拍板并存）→ design §6.3 补写 + TC-SEM-08/09 注记（任务书已明确） |

**CASE_BUG 裁定请求**：无（本轮未收到）。

**放行结论**：P1 无；P2 三项（模糊索引向量链路 inline 断线/不可自愈、向量层生产链路零覆盖+search_entities 未接线、env 模板）修毕并复跑门禁后可进 R2 复审；其余 P3 可登记下批。

</details>

<details>
<summary>R2 Tester 报告（2026-11-01 09:27，ses_e6b8618b9ffeKphrtPNpwOsB3H 续接，testVerdict=PASS）</summary>

临时文件已删净、工作区纪律合规。全部核验完成，出具 R2 验证报告。

---

# 验证报告：task-knowledge-lattice-m2s-6 R2（Tester）

## 1. testVerdict: **PASS**（零 P1/P2，2 项 P3 建议）

## 2. testedSha: `e7fac5c4d16f2a275d8c160ebe702e75b786408f`（HEAD，develop_opencode）

## 3. 执行记录

### 3.1 门禁全量（独立复跑）
- **[pytest] OK：1475 passed, 1 deselected**；**[pytest-O] OK：1475 passed, 1 deselected** —— 双模式全绿，**0 skipped**（deselect = manual 组口径）
- **pg 臂 525 条全实跑**（[pg] 参数化 486→492 +6、PG 专用 33）> 0 ✓
- R1 基线 1460+1 → **1475+1，+15 只增不减**，与申报逐位一致；+15 构成可完全对账：9 条新用例 = 6 条双后端（12 跑）+ 3 条 sqlite 专有（inline/REST 端点/工具描述——create_app 直连 sqlite 形态）= 15 跑 ✓

### 3.2 P2 逐条闭环验证

**P2-1 模糊索引向量链路（4 子项全落地 + 5 条锁定用例）**
- ① **inline 断线修复**：app.py:264 `WorkerServices(_embedder=embedder)` ✓。锁定用例 `test_p2_1_inline_build_has_vectors` 走**真实生产形态**（create_app + TestClient + inline worker 轮询消化 sync 自动投递的 build）——非单元脚手架，`vec_embedded > 0` 断言在修复前恒 0，锁定有效
- ② **skipped 对账修复**（裁定 5 口径）：build.py 新增 `_repair_fuzzy_index_if_needed`，skipped 分支先对账（`terms < 期望` 或 `有 embedder 且 vec_embedded < vec_expected` → 整替补写）。收敛链用例完整：**写失败（monkeypatch 仅注入故障）→ index_write_failed 持久化 → 同 rev skipped → fuzzy_repaired 注记 → terms/vec 补齐到 `vec_expected` 基准**；降级自愈路径（embedder=None 建库 → 有 embedder 的 skipped 补齐）与**一致态零补写**（防空转——幂等断言）各一条
- ③ **失败标记持久化**：`_write_fuzzy_index` 两个调用点均传 `build_id`，写失败经 `sem_update_build_stats` 落 stats_json——用例从**库内读 build_report 断言** `index_write_failed is True`（非读内存返回值），持久化属实
- ④ **vec_skipped 误报修正**：fuzzy.py `embed_fn=None 且有 pending → vec_skipped=True` + 直接单元断言 ✓
- store 层：`sem_fuzzy_index_stats`/`sem_update_build_stats` 双方言实现 + Protocol 登记，语义同构 ✓

**P2-2 向量层生产链路（方案①全落地 + 4 条用例）**
- **端点接线为真**：REST `api/semantic.py:420` 与 MCP `server.py:504` 均注入 `settings=service.settings, embedder=getattr(service, "embedder", None)`——核实 app.py:74 依赖容器确有 `self.embedder`，接线非装饰性
- **工具描述三处对齐**：模块 docstring 排序链五档、SEARCH_ENTITIES 描述（拼音+向量+去「归后续段」矛盾句）、SEARCH 描述补 entities/auto_entities/matched_entities（P3-11 顺手）——均有字符串断言锁定
- **三断言为实**：`_MappingEmbedder` 精确控向量——查询词「完税证明」与词典零字面/拼音/编辑距离关系 → `via='vec'` 是唯一命中来源（排除 AC 层假阳性）；正交 embedder（sim=0 < 0.75）全过滤；同实体 name+alias 双 term 去重
- **A3 真链路零注入声明核实**：`test_p2_2_annotate_fuzzy_vec_production_chain` 调 `annotate_text(fuzzy=True, embedder=...)`，**无 vec_lookup 注入、链上无 monkeypatch**（仅改 embedder 映射数据本身，且先做阴性对照：未映射片段 → 阈值过滤零命中）——真实走 embed→`sem_fuzzy_vec_search`→阈值/top-3；`annotate_text` 的 embedder 链路在 R1 已存在（annotator.py:699-747，R2 未改 annotator），无掩盖断线。REST 端点用例同样走 TestClient+inline worker 真链路（query "zzz" 零词面关系 → via='vec' score=1.0）

**P2-3**：.env.example +8 行（K_ENTITY/ENTITY_ROUTE_WEIGHT/SEM_FUZZY_VEC_THRESHOLD/SEM_FUZZY_VEC_TOP，带注释与设计指针）✓

**顺手 P3-3**：恒真断言改 `assert localac.normalize_alias is norm.normalize_alias`——配套 localac 模块级显式导出（否则断言会 AttributeError 红），一行改动精确无扩大 ✓

### 3.3 附带行为变化（code/sync 不嵌向量）影响面
- **口径溯源**：sync.py:439-440 实证 kind='code'（实体 key）/kind='sync'（源系统自带别名）确为源系统键；fuzzy.py 仅对这两类置 `embed=False`——**实体显示名（name）、YAML 人工别名、定义句向量全保留**；拼音/编辑距离面不受 embed 标记影响（del 键构建独立于 embed 标志）
- **新增 `vec_expected` 统计**：区分「可嵌行 NULL=预期」与「降级」，同时作对账修复满覆盖基准——设计自洽
- **评测零劣化**（独立复跑非采信）：recall@10 sqlite **0.8214→0.9286**、pg **0.5→0.625**、MRR 0.3372/0.4734→0.4087/0.5142、AC+模糊 recall@3=**1.0**（145 条/159 标注）——与 R1 数值**逐位一致**（报告未改 + 测试互锁双证），TC-SEM-05 排序链用例全绿

### 3.4 回归确认
- R1 验收面复跑 **81 passed**（matrix_ts7_ts9 + tag_04 + sem_09 + sem_05 + sem_08 + yaml_05 + m2s6_followups + sev_03 + golden 校验）——越权矩阵/实体召回路/黄金集评测零回归
- **R1 P3×3 处置核对**：③恒真断言已修 ✓；①T-S7 describe_table/T-S9⑥ 与 ②l0_extra——`test_matrix_ts7_ts9.py`/`test_m2s6_followups.py` **R2 零触碰**（不在 diff），无顺手扩大改动，按裁定 1/2 登记下批 ✓
- **纪律面**：R2 diff 中 docs/、uv.lock、scripts/ 零改动 ✓；uv.lock aliyun 计数仍 0 ✓；工作区仅 4 个监督侧流程文档改动 + 未跟踪检查点，未混入 commit ✓；存量测试仅 yaml_05 一处 5 行改动（即 P3-3），零弱化 ✓

## 4. 问题清单
- **P1（阻塞）：无**
- **P2（应修）：无**
- **P3（建议）**：
  1. `_repair_fuzzy_index_if_needed` docstring「只补缺不降级——绝不把非空向量覆盖为空」在**修复触发时 embedder 存在但已故障**的边缘形态下不成立（terms 缺失触发的整替会以 NULL 向量覆盖旧好向量）。收敛性仍由裁定 5 机制保证（下次有可用 embedder 的 skipped 构建再补齐——降级自愈用例已证），且 `vec_skipped`/`index_write_failed` 标记可观测，故仅建议 docstring 措辞收敛或该边缘加注释登记。
  2. test_r2_m2s6_fixes.py 模块 docstring 自述「P2-1/P2-2 用例为 sqlite 单后端」与实际不符——6/9 用例经 `backend` fixture 双后端参数化（pg 臂的 `sem_fuzzy_index_stats`/`sem_update_build_stats`/修复链**已被实测覆盖**），属少报不多报的措辞瑕疵，归档时可顺手更正。

**结论**：Committer P2×3 全部真实闭环（修复在生产路径上生效、锁定用例防回退），附带缺陷修复（code/sync 不嵌向量）有用例锁定且评测零劣化，R1 验收面零回归，门禁 1475+1 独立复跑属实，testVerdict=**PASS**。

</details>

<details>
<summary>R2 Committer 报告（2026-11-01 09:35，ses_e6b7517f3ffeqOfvT2TYOYMKEk 续接，reviewVerdict=NEEDS_CHANGES）</summary>

# 审查报告：task-knowledge-lattice-m2s-6 R2（Committer 续接）

## 1. reviewVerdict

**NEEDS_CHANGES**（P1 无；**P2×2**；P3×若干；进入 R3）

## 2. reviewedSha

`e7fac5c4d16f2a275d8c160ebe702e75b786408f`（审查对象 = testedSha = HEAD）
按惯例 NEEDS_CHANGES **不置位**检查点 `reviewedSha`（保持 null，由监督侧处理）。

## 3. 审查执行记录

**基线核对**
- `git diff e5a70d6..e7fac5c` = **12 files +604/−31**，与申报一致：`app.py / build.py / fuzzy.py / localac.py / api/semantic.py / mcp/server.py / store/backend.py / store/{sqlite,postgres}/backend.py / .env.example / tests/test_r2_m2s6_fixes.py(新) / tests/test_yaml_05_local_ac.py`。
- **docs/、uv.lock、scripts/ 零改动**；工作区仅 4 个监督侧流程文档 + 未跟踪检查点，未混入 commit；HEAD = e7fac5c = testedSha。
- 门禁以 Tester 独立复跑为准：**1475+1 双后端双模式 0 skipped**；+15 构成（6 条 `backend` fixture 双后端=12 + 3 条 sqlite 专有）**逐位对账成立**；R1 验收面 81 passed 零回归。本会话为只读审查（无 pytest 执行权限），未发现与申报矛盾的 skip/删除/弱化。

**R1 P2×3 逐条闭环结论表**

| R1 P2 | R2 修复 | 闭环结论 |
|---|---|---|
| **P2-1** inline 断线 + 写失败不可自愈 + vec_skipped 误报 | `app.py:261-265` 补 `_embedder`；`build.py` 新增 `_repair_fuzzy_index_if_needed`（skipped 对账补写）；`_write_fuzzy_index` 经 `sem_update_build_stats` 持久化 `index_write_failed`；`fuzzy.py` `embed_fn=None` 时 `vec_skipped=True`；5 条永久用例 | **基本闭环**（inline 用例走真实 create_app+inline worker；写失败标记从库内 build_report 读断言；降级自愈与一致态零空转均有锁定）。**残留见 P2-2：对账条件只比行数/向量数，陈旧内容（写失败/崩溃 + 词典收缩或等行数改名）不触发修复** |
| **P2-2** 向量层生产链路零覆盖 + 端点未接线 | REST `api/semantic.py:420`、MCP `server.py:504` 注入 settings/embedder；三处描述对齐；`via='vec'`/阈值/去重三断言 + A3 真链路（零注入）+ REST 真端点用例 | **P2-2 本体闭环**；但注入后 **REST 端点新增同步 embed 调用阻塞事件循环**（新 P2-1） |
| **P2-3** `.env.example` 漏 4 配置 | 4 配置 + 注释（101 行，申报"93→103"为监督侧 metadata 小误） | **闭环** |
| R1 P3-3（恒真断言）/ P3-11（LLM 工具描述） | 直接断言 + `localac.normalize_alias` 显式导出；`SEARCH_TOOL_DESCRIPTION` 补 entities/auto_entities/matched_entities、`SEARCH_ENTITIES` 补拼音/向量 | **闭环** |
| R1 P3 其余 11 项 | 未触碰（按裁定登记 docs/下批） | **范围纪律 ✓** |

**附带变更审查（code/sync 不嵌向量）**
- **口径溯源属实**：`sync.py:436-445` 的 `kind='code'`=实体 key、`kind='sync'`=源系统自带别名；`fuzzy.py:130-140` 仅这两类 `embed=False`，name/YAML manual·abbr/definition 向量保留；del 键构建独立于 embed 标志（`fuzzy.py:186-196`）——Tester 的溯源结论成立。
- **评测零劣化得到独立验证**：recall@10 sqlite 0.8214→0.9286 / pg 0.5→0.625、MRR 双升、AC+模糊 recall@3=1.0（参考词典为 YAML 纯人工面，无 code/sync 别名参与），与 R1 逐位一致。
- **但"真实缺陷"的论证不成立/过度**：碰撞只在**确定性测试替身**（`_MappingEmbedder` 的同一个 default 向量）下出现；生产 embedder 对每个文本返回不同向量。`code`（业务键）排除可辩护（低语义价值、防噪声）；**`sync` 是源系统别名不是键**，排除它缩小了 §5.8「名称/别名/定义向量」的别名面（见 P3-1）。

**新引入面审查**
- `sem_update_build_stats`：单语句 `UPDATE sem_builds SET stats_json`（sqlite autocommit / pg autocommit=True），org+id 双条件，不动 status/时间戳——**事务/并发面可接受**（同 rev 并发写为 last-writer-wins，内容同 rev 等价；不参与 ACL/业务状态）。仅"修复后失败标记不清"的观测语义见 P3-7。
- `_repair_fuzzy_index_if_needed`：一致态零动作有幂等用例；但**触发条件不完整**（见 P2-2）。
- 工具描述字符串：与 `lookup` 实际排序链（exact>prefix>pinyin>FTS>vec）一致，字符串断言锁定；无契约冲突。
- **新 P1 无；新 P2×1（见下）**。

## 4. 问题清单

### P1（阻塞）
- 无。

### P2（应修）

**P2-1（R2 新引入回归）REST `/semantic/entities` 在事件循环内同步调用模型嵌入**
- `src/knowledge_lattice/api/semantic.py:407-428`：`async def list_semantic_entities` 直接调用同步 `search_entities(...)`；R2 注入 embedder 后，该调用内部 `lookup.py:79-84` 执行 `embedder.embed([q])`——`OpenAICompatEmbedder` 为同步 `httpx.Client`，超时 `embed_timeout_s=30s`（`adapters/embedder.py:70-80`）。**async handler 内阻塞事件循环，最长 30s**，违反 design §5.2 / NFR-8「模型 HTTP 调用全部异步/线程池，绝不阻塞事件循环」；端点其余语义读（annotate/get_entity）均走 `asyncio.to_thread`，此处为唯一例外。
- 影响：单次慢网关/不可达可挂起整个 REST 事件循环（并发请求全部排队）；Tester 测试为单请求 TestClient 形态，未覆盖并发面。
- 修复：`return await asyncio.to_thread(search_entities, service.backend, org, q, types=types, top_k=top_k, settings=service.settings, embedder=getattr(service, "embedder", None))`（`try/except ValueError` 包住 await）。建议同时为 vec 档设查询侧有界超时（如 `query_embed_timeout_s`）并在降级时记审计/notice——见 P3-5。

**P2-2（P2-1 收敛不完整，未完全兑现 R1 裁定 5「最终一致+修复路径」）**
- `src/knowledge_lattice/core/semantic/build.py:339-354, 577-624`：skipped 分支新增的 `_repair_fuzzy_index_if_needed` 对账条件为 `have["terms"] < expect_terms`（行缺失）或 `embedder 存在且 have["vec_embedded"] < expect_vec`（向量覆盖不足）。**这是纯计数/覆盖对账，无法发现"索引来自上一 rev、内容不同但行数与向量覆盖都不低"的陈旧**：
  - 写失败/ready 后崩溃 → 索引仍是上一 rev；同 rev 的 skipped 构建修复时，若上一 rev 的词条数 ≥ 当前 rev（词典收缩）或等行数但别名/定义改名 → `have >= expect` 且向量覆盖足够 → **不触发修复**，陈旧索引保持到下一次 dict_rev 变更（静态词典部署下即"永久陈旧"——正是 R1 P2-1 指出的形态）。
  - 崩溃场景下持久化的 `index_write_failed` 标记也不存在（`_write_fuzzy_index` 未执行），当前实现也未把已持久化的标记作为触发条件；`sem_fuzzy_terms_all`（R1 已有、可做内容对账）未被使用。
- 影响：`search_entities` 拼音层/`annotate` vec 层可能返回已删除别名/旧别名的候选；非 ACL/可用性问题，但"最终一致"的正式口径未达成。
- 修复建议（小）：`_repair` 已算出 `expected` 的 term_rows（当前 `_rows` 被丢弃）——用 `{(entity_id, kind, text_norm)}` 与 `backend.sem_fuzzy_terms_all(org_id)` 做集合对账，任何不等于即触发整替（embedder 缺失时可先重建行、向量留待下次有 embedder 的 skipped 补齐，或按策略暂缓并注明）；另将 `current["stats_json"].fuzzy.index_write_failed / vec_skipped` 作为附加触发条件；补一条"词典收缩 + 写失败 → skipped 修复"回归用例（现有用例只覆盖词典增长）。若监督侧认为计数对账已足够，应将该残余作为 known-gaps 登记并回落裁定 5 的"最终一致"表述（不建议：与正式口径冲突）。

### P3（建议/登记）

1. **code/sync 不嵌向量（附带变更）正当性/测试面**：`code` 排除可接受；**`sync` 是源系统别名（非键）**，排除使 §5.8「别名向量」面变窄，且"碰撞缺陷"仅由测试替身 default 向量证明；无专门用例锁定排除行为；`fuzzy.py` 模块 docstring 第 19-24 行仍写"alias：全部别名…向量"（未更新）；`tests/test_r2_m2s6_fixes.py:283-309` 的"同实体 name+alias 双 term 去重"因 alias 是 `kind='sync'` 被排除，现在实际只有 name 单 term——**去重断言空转**。建议：仅排除 `code`、恢复 `sync`（或登记 §5.8 偏差 + 补专门用例）；去重用 `manual`/`abbr` 别名；同步修正 docstring。
2. **Tester P3-1（`_repair` docstring）**：另发现 docstring 第 582-587 行写"vec_embedded < terms"而代码用 `expect_vec`；"只补缺不降级"在 embedder=None/故障但 terms 缺失触发整替时会以 NULL 覆盖旧非空向量（Tester 边缘）+ docstring 与代码不一致——措辞收敛/加注释登记（见 §5）。
3. **Tester P3-2（test_r2 模块 docstring）**：第 16-17 行"P2-1/P2-2 用例为 sqlite 单后端"与实际 6/9 双后端参数化不符（少报）；一并修正为"6 双后端 + 3 sqlite 专有；新 store 方法双方言由本套件覆盖"。
4. **`_repair` 性能**：每次 skipped 构建重新 `build_fuzzy_terms`（含全量 pypinyin）+ 触发时再 `_build_fuzzy_products`，10⁴~10⁵ 规模下为每日无变化同步的固定开销；建议优先用 `current.stats.fuzzy` 或内容集合做判定，仅在触发时重算。
5. **`lookup.search_entities` vec 档无有界超时/熔断/降级审计**：`embedder.embed([q])` 使用 `embed_timeout_s=30s`，未走 `query_embed_timeout_s=0.5s`/`breakers`；失败仅 warning、无 `search.degraded` 类事件（§5.2 降级可观测口径）。建议至少文档登记或复用查询侧预算。
6. **`fuzzy.py` 文档面**：`build_fuzzy_terms` docstring 未说明 `embed` 标志/`vec_expected`/code-sync 预期 NULL；模块 term face 与实现不一致（P3-1 同源）。
7. **修复观测语义**：`fuzzy_repaired` 只在 skipped 返回/审计事件，不落库；被修复的 build 行仍保留 `index_write_failed=True`（历史事实但易误读）；建议在 skipped 审计事件/日志足够的前提下登记说明，或在 current 行补修复注记。
8. **陈旧注释**：`worker/runner.py:72` WorkerServices docstring "inline 形态可不带 `_embedder`" 已不成立（inline 现携带）；`lookup.py:78` "MCP/REST 未注入时跳层" 的括号需更新（两端已注入）。
9. **R1 P3 残留**（按裁定未动，汇总去向）：审计常量登记处/持权审计两漏记/编辑距离含 name/内存 dict 复制/top-3 硬编码/auto_entities ValueError/Protocol 签名陈旧（`sem_expand_graph` 缺 `include_restricted`、`sem_search_entities` 缺 `q_pinyin`）/中间件 L1 缺 disambiguation/报告 TokenBag 描述/测试覆盖缺口/matched_entities 口径/G-21 再挂——docs 批或下批，见 §6。

## 5. Tester R2 P3×2 处置意见

1. **`_repair` docstring「只补缺不降级」边缘** → **修（R3）**：承认该边缘（embedder 存在但故障/缺失 + terms 缺失触发整替会短暂以 NULL 覆盖旧向量；收敛性依赖后续可用 embedder 的 skipped 构建）；同时修正 `< terms` → `< expect_vec` 的笔误，并写明 embedder 缺席时的实际策略。
2. **`test_r2` 模块 docstring 少报** → **修（R3）**：改为"6/9 双后端参数化（pg 臂覆盖 `sem_fuzzy_index_stats`/`sem_update_build_stats`/修复链）+ 3 条 sqlite 专有（inline/REST 端点/工具描述）"。

## 6. 交付归档建议（本轮未 APPROVED；以下为 R3 收敛后的预备清单）

**docs 批（监督侧）**
- **R1 边界 8 条裁定落笔**：①T-S7 三端点口径（describe_table/l0 显式断言下批）；②T-S9⑥ 查询级审计登记 known-gaps（全库无实现，A-16 待实现确认）；③§6.3③ restricted 持权面注记（POC 仅 annotate/get_entity）；④`sem_restricted` 载体（membership role、DDL role 注释、无管理入口 known-gaps）；⑤模糊索引「最终一致+修复路径」正式口径（**以 R3 修复后的真实对账谓词为准**，不得写"整替收敛"旧表述）；⑥§5.9 实词族 + 编辑距离含 name 偏差；⑦黄金集 172→180 + pos_typo 排除 TC-SEV-02 分母；⑧auto_entities 默认 false 保守档。
- **规格登记 6 条**：#1/#3/#4/#6 非决策 docs 批；#2 sem_restricted 授予载体（+ 无管理入口）；#5 模糊索引写库时机（先修 P2-2 再登记，写明收敛条件与残余）。
- **附带变更登记**：code/sync 不嵌向量（若保留 sync 排除须登记 §5.8 偏差；建议收窄为 code）；`vec_expected` 统计语义。
- **TEST-CASES v1.9.x**：T-S7/S8/S9 ✅（按三端点口径 + 备注）、TC-TAG-04/05 ✅、TC-SEM-08/09 ✅、TC-SEV-03 ✅、TC-YAML-05 ✅；TC-SEM-05 向量档（R2 接线）；§六 M2-S3 行收口（门禁 1475+1）；172→180/pos_typo；T-S9⑥ 口径；matched_entities 口径（R1 P3-12）。
- **known-gaps**：查询级审计缺口（FR-6）；G-21 再挂回写（mixed-mode/l0_extra）+ 本段核销；模糊索引对账残余（若 P2-2 不按内容对账修则必须登记）；sem_restricted 无授予入口；R1 P3 残留清单。
- **AGENTS.md / _m2-plan**：语义轨道 6/6、下一段 m2-4、门禁 1475+1、G-21/TC-PERF-05/TC-UI 去向；`.env.example` 行数（101 非 103）metadata 小误顺手校正。

**遗留事项去向**
- R1 P3 残留（除 P3-3/P3-11 已修）→ m2s-6 followups / m2-5 / docs 批，按 R1 清单逐项标注去向。
- T-S7 describe_table/l0 显式断言 → 下批；T-S9⑥ → 查询级审计缺口登记（非本段）。
- TC-PERF-05（含新增的 `_repair` pypinyin 开销、search_entities vec 超时面）→ m2-5 兜底。
- TC-UI-01~04 → 用户侧手动走查。
- code/sync 向量排除（若保留）→ docs 批 + 后续收窄/验证。

**manifest 要点（R3 通过后）**
- dual SHA：testedSha = reviewedSha = 最终 HEAD；轮次（R3 若收敛）。
- 门禁原始输出：1475+1（R3 可能再增）、pg 臂 525 实跑、双模式 0 skipped。
- specRulings：R1 边界 8 条 + 规格登记 6 条 + code/sync 附带变更。
- gapClosures：T-S7/S8/S9、TC-TAG-04/05、TC-SEM-08/09、TC-SEV-03、TC-YAML-05、G-21 核销项、P2×3。
- handover：R1 P3 残留、查询级审计缺口、TC-PERF-05、TC-UI、code/sync 向量面。
- 检查点终态 + docs 批 commit（含 TEST-CASES v1.9.x / known-gaps / AGENTS / _m2-plan）。

**CASE_BUG 裁定请求**：无（本轮未收到）。

**放行结论**：P1 无；P2 两项（REST 事件循环阻塞 = R2 新引入回归；skipped 对账内容盲区 = 裁定 5 未完全兑现）修毕并复跑门禁后进 R3 复审；P3 按上文修/登记。

</details>

<details>
<summary>R3 Tester 报告（2026-11-01 10:09，ses_e6b8618b9ffeKphrtPNpwOsB3H 续接，testVerdict=PASS）</summary>

全部核验完成，出具 R3 验证报告。

---

# 验证报告：task-knowledge-lattice-m2s-6 R3（Tester）

## 1. testVerdict: **PASS**（零 P1/P2，1 项 P3 建议）

## 2. testedSha: `4057b40a2a747d6d8eae23249bdfa2b8ac31a765`（HEAD，develop_opencode）

## 3. 执行记录

### 3.1 门禁全量（独立复跑）
- **[pytest] OK：1479 passed, 1 deselected**；**[pytest-O] OK：1479 passed, 1 deselected** —— 双模式全绿，**0 skipped**
- **pg 臂 527 条全实跑**（[pg] 参数化 492→494 +2、PG 专用 33）> 0 ✓
- R2 基线 1475+1 → **1479+1，+4 与申报逐位一致**（2 条新用例 × 双后端臂，构成完全对账）

### 3.2 P2 逐条闭环验证

**P2-1 REST /semantic/entities 事件循环阻塞（R2 引入回归）——已闭环**
- `api/semantic.py:425` 改 `return await asyncio.to_thread(search_entities, …)`，`except ValueError` 正确包裹 await（HTTP 400 语义保留）；端点内**唯一**模型调用（vec 档内嵌的 `embedder.embed`，同步 httpx Client 30s 超时面）已整体下放线程池——grep 核实该 handler 无其他同步调用残留；annotate(:343/:383)/get_entity(:453)/build_report(:398)/l0(:485) 本就走 to_thread，此处唯一例外已对齐形态
- 既有 REST 端点用例复跑零变化：`test_p2_2_search_entities_rest_endpoint_vec`（真实 TestClient+inline worker 链路）与 R2 修复面 19 跑全绿

**P2-2 skipped 对账内容盲区收口（裁定 5 最终口径兑现）——已闭环**
- **内容集合对账为真**：期望 `{(entity_id, kind, text_norm)}`（build_fuzzy_terms 纯计算）vs `sem_fuzzy_terms_all` 现存集合——**三元组集合真实比对**（非计数）；向量覆盖判定为 `elif`（内容不等即触发，内容相等才查覆盖）；`sem_fuzzy_index_stats` 对账数据源不变
- **落库标记附加触发**：`_fuzzy_failure_marker` 读 current build 行 `stats_json` 的 `index_write_failed`/`vec_skipped`——数据源核实：`sem_current_build` 双方言 SELECT 均含 `stats_json` 列，崩溃场景落库线索真实可达；防御性解析（非 str/非 dict/坏 JSON 全回退 None）
- **TDD「先红」等价性实证**（不改业务代码，脚本在新逻辑三场景状态上求值 R2 旧对账条件 vs R3 新条件）：
  - 场景 A（收缩+写失败）：**旧条件 need=False**（旧索引行数多于期望——计数对账盲区实证）、**新条件 need=True**
  - 场景 B（等行数改名+写失败）：**旧条件 need=False**（行数/覆盖全等）、**新条件 need=True**
  - 场景 C（持久化标记+内容一致）：旧代码**无标记触发面**（结构性恒 False）、新条件 marker 触发=True
  - 即三条新用例在 R2 代码上必红——「先红后绿」申报属实；脚本用后即删
- **修复后逐位断言**：两场景均断言 `have == expected` 三元组集合逐位相等（非仅 fuzzy_repaired 真值）；`test_p2_1_no_repair_when_consistent` 幂等断言原样保留（一致态零动作不回退）——双后端通过

**P3-1 code/sync 收窄——已闭环**
- fuzzy.py 嵌入条件收窄为 `a.get("kind") != "code"`，sync 恢复嵌入；模块 docstring term face 同步（唯一例外 kind='code'，向量列预期 NULL 非降级）
- **去重断言非空转实证**（R2 空转根因=sync 别名向量 NULL→`sem_fuzzy_vec_search` WHERE embedding IS NOT NULL 永远单 term 可命中）：现网状态实测 c.voucher 带 **3 个向量 term**（name + sync 别名「留抵税额」+ name 别名；唯一 NULL=code 键 `c.voucher`——恰为 R3 口径），同实体多 term 真实进入 lookup 去重路径，`test_p2_2_vec_via_threshold_and_dedup` 双后端通过
- **评测零劣化**（独立复跑非采信）：recall@10 sqlite **0.8214→0.9286** / pg **0.5→0.625**、MRR 0.3372/0.4734→0.4087/0.5142、AC+模糊 recall@3=**1.0**（145 条/159 标注）——与 R1/R2 **逐位一致**，TC-SEM-05/09 相关用例零回归

### 3.3 P3 处置与回归面
- **P3-2**：`_repair` docstring 笔误已修（向量判定现写 `vec_embedded < vec_expected`），Tester R2 P3-1 边缘注记（NULL 覆盖边缘+收敛依赖）已如实落入 docstring——措辞不再是过度声明 ✓
- **P3-3**：test_r2 docstring 少报已更正（现自述 8/11 双后端 + 3 sqlite 专有，与实际一致）✓
- **P3-8**：runner.py:72（`_embedder` 供 semantic_build——子进程形态 runner.py:535 实证同样携带）/lookup.py:78（端点注入现状）两处陈旧注释已更新 ✓
- **P3-4/5/6/7/9 登记不动核实**：annotator.py/recall.py/store/backend.py/middleware.py **均不在 R3 diff**——零顺手扩大 ✓
- **回归**：R1/R2 验收面复跑 **81 passed**（越权矩阵/实体召回路/黄金集/中间件/两端一致/followups/sev_03/golden 校验）+ R2/R3 修复文件 **19 passed**（8 双后端+3 sqlite 专有）——零回归
- **纪律面**：R3 diff 中 docs/、uv.lock、scripts/、.env.example 零改动 ✓；uv.lock aliyun 计数 0 ✓；工作区仅 4 个监督侧流程文档 + 未跟踪检查点，未入 commit ✓

## 4. 问题清单
- **P1（阻塞）：无**
- **P2（应修）：无**
- **P3（建议）**：
  1. **持久化标记粘滞**：修复触发不清除 current build 行 stats_json 内的 `index_write_failed`/`vec_skipped` 标记（`sem_update_build_stats` 仅在写失败路径调用）——静态词典（dict_rev 永不变）下每次 skipped 构建都会因标记重触整替（含全量 pypinyin 重算，`fuzzy_repaired` 恒真）。功能上无害（整替幂等、索引恒收敛到期望集合），且生产拓扑 inline/子进程 worker 均携带 embedder（runner.py:535/app.py:267 双实证），NULL 覆盖振荡仅理论存在；但与已登记 P3-4（每次 skipped 全量重算）/P3-7（fuzzy_repaired 观测语义）同族放大——建议 docs 批登记时把「标记触发后是否应清标记或计数去重」一并写入裁定 5 口径注记，或下批在修复路径尾部对 current 行标记做一次清除断言级收口。

**结论**：Committer R2 P2×2 全部真实闭环（阻塞面消除经 grep+用例复跑双证；内容集合对账三场景经实证「旧逻辑必红→新逻辑修复后逐位相等」），P3-1 收窄恢复后评测三连轮数值逐位一致、去重断言由空转转实，门禁 1479+1 独立复跑属实、零回归零扩大，testVerdict=**PASS**。

</details>

<details>
<summary>R3 Committer 报告（2026-11-01 10:15，ses_e6b7517f3ffeqOfvT2TYOYMKEk 续接，reviewVerdict=APPROVED）</summary>

# 审查报告：task-knowledge-lattice-m2s-6 R3 终审（Committer）

## 1. reviewVerdict

**APPROVED**（P1 无、P2 无；P3 登记级若干——含 2 项本轮新发现的残余，见 §4/§5）

## 2. reviewedSha

`4057b40a2a747d6d8eae23249bdfa2b8ac31a765`（= testedSha = HEAD；检查点 `reviewedSha` 应置此值）

## 3. 审查执行记录

**基线核对**
- `git diff e7fac5c..4057b40` = **6 files +219/−44**，与申报一致：`api/semantic.py`（to_thread）/`core/semantic/build.py`（内容集合对账+标记）/`core/semantic/fuzzy.py`（仅 code 排除）/`core/semantic/lookup.py`（注释）/`worker/runner.py`（注释）/`tests/test_r2_m2s6_fixes.py`（R3 两用例+docstring）。
- **docs/、uv.lock、scripts/、.env.example 零改动**；工作区仅 4 个监督侧流程文档 + 未跟踪检查点，未混入 commit。
- 门禁以 Tester 独立复跑为准：**1479+1 双后端双模式 0 skipped**；+4 = 2 新用例 × 双臂，逐位对账成立；pg 臂 527（494+33）；R1/R2 验收面 81 passed + R2/R3 修复面 19 passed 零回归。本会话只读（无 pytest 执行权限），未发现与申报矛盾的 skip/删除/弱化。

**R2 P2×2 / P3-1 逐条闭环结论**

| R2 项 | R3 修复 | 闭环结论 |
|---|---|---|
| **P2-1** REST `/semantic/entities` 事件循环阻塞 | `api/semantic.py:419-428` `await asyncio.to_thread(search_entities, …)`，`except ValueError` 包住 await；线程本地 backend（`ThreadLocalBackend`）保证跨线程连接 | **闭环**。端点内唯一模型调用（30s 同步 httpx）整体下放；与 annotate/get_entity/l0/build_report 的 to_thread 形态一致；R2 REST 用例零变化 |
| **P2-2** skipped 对账内容盲区 | `build.py:612-617` 期望集合 `{(entity_id, kind, text_norm)}` vs `sem_fuzzy_terms_all`；`elif` 向量覆盖；`_fuzzy_failure_marker`（`build.py:648-666`）读 current 行落库标记；TDD 收缩/改名/标记三场景（R2 旧逻辑必红→R3 绿） | **两形态闭环**：收缩（行数反多）与等行数改名由内容集合覆盖；写失败由落库标记覆盖；`test_r3_p2_2_shrink_and_rename…`/`…_persisted_marker…` 双后端逐位断言。**残留**：`embed_model` 未入内容集合（模型迁移+崩溃窗口）→ 见 P3-1 |
| **P3-1** code/sync 收窄 | `fuzzy.py:141` 仅 `kind != "code"` 排除；sync 恢复嵌入；模块 docstring term face 同步；去重断言由空转转实（c.voucher 多 term，唯一 NULL=code） | **闭环（行为面）**；§5.8 别名面恢复、去重路径真实。测试内两处 "code/sync 键不嵌" 注释已过期 → P3-3 |
| **P3-2/3/8** | `_repair` docstring 笔误/边缘措辞；test_r2 8/11 双后端 docstring；runner/lookup 注释 | **闭环**（`vec_embedded < vec_expected` 已修正；边缘注记如实；测试自述与实际一致） |
| **范围纪律** | R3 未触碰 P3-4/5/6/7/9（annotator/recall/store/backend/middleware 不在 diff）；P3-6 仅 P3-1 所需的 term face 更新 | **合规** |

**P3-1 收窄三子问题**：①§5.8 别名面——sync 恢复嵌入、仅 code 排除，模块 docstring 已写"唯一例外"→ **闭**；②去重断言空转——R3 后 sync 别名参与向量，`test_p2_2_vec_via…` 真实多 term 去重 → **闭**；③docstring——`fuzzy.py` 模块面已更新；**遗留**：`test_r2` 内 "code/sync 键不嵌" 注释与首段 "行数/向量覆盖率" 表述未同步 → P3-3。

**新引入面结论**
- **内容对账性能**：每次 skipped 构建现执行 `build_fuzzy_terms`（全量 pypinyin）+ `sem_fuzzy_terms_all`（全行读）+ `sem_fuzzy_index_stats`；触发时再算一次并全量 embed+replace。属 R2 已登记 **P3-4**（每次 skipped 全量重算）的放大面，**非新 P1/P2**；规模 10⁴~10⁵ 下建议下批用 build stats 内容哈希/仅在标记或覆盖异常时做全量读（见 §6 遗留）。
- **`_fuzzy_failure_marker` 防御性解析**：str/dict/坏 JSON/非 dict 全回退 None；`sem_current_build` 双方言经 `_sem_run_dict` 已把 stats_json 解析为 dict，数据源可达——**安全**。但 docstring/Tester 的"崩溃场景落库线索"表述不准确：崩溃（未执行 `except`）**不会**写标记；标记实际覆盖的是**已捕获写失败**，崩溃依赖内容集合对账——见 P3-3。
- **to_thread 后 ValueError 映射**：await 在 `try` 内，`search_entities` 的 q/types/top_k ValueError 仍映射 400；其余异常走 500；无新回归。低概率的 pgvector 维度类 ValueError 会被映射 400（可接受/登记）。
- **新 P1/P2**：无。

## 4. 问题清单

### P1（阻塞）
- 无。

### P2（应修）
- 无。

### P3（建议/登记）

1. **（R3 新发现，P2-2 残余）`embed_model` 未入内容集合——模型迁移+崩溃窗口**
   `build.py:612-617` 的 `expect_set/have_set` 只含 `(entity_id, kind, text_norm)`；`sem_fuzzy_terms_all`（`store/{sqlite,postgres}/backend.py`）已返回 `embed_model` 却未参与比对。场景：换嵌入模型（dict_rev 因标签变化而新建 rev）→ ready 切换后、`_write_fuzzy_index` 执行前崩溃 → 旧标签索引保留；后续同 rev skipped 构建：内容集合相同、`sem_fuzzy_index_stats` 计旧向量数 == `expect_vec`、无标记 → **不触发修复**，查询按新标签过滤 → 向量层静默为空直到下次 dict_rev 变更。修法（一行级）：期望/现存集合追加 `embed_model`（期望=settings.embed_model_label），并补"模型迁移+崩溃窗口→skipped 修复"回归；届时标记触发可删/可清（见 P3-2）。**若监督侧按"最终一致"绝对口径读裁定 5，此项应升 P2**；按当前异常窗口极窄（普通路径与写失败路径均已覆盖）判 P3 登记。
2. **（Tester R3 P3-1）持久化标记粘滞**：修复成功不清 current 行 `stats_json.fuzzy.index_write_failed/vec_skipped`；静态词典下每次 skipped 因标记重触整替（全量 pypinyin+embed+replace），与 P3-4/P3-7 同族放大。功能无害（整替幂等、索引收敛）；生产 inline/子进程均携带 embedder。处置见 §5：**登记 + 下批**；推荐与 P3-1 合并修法（label 入集合 + 清/去标记）。
3. **docstring/注释陈旧/不实**：①`build.py:595` "修面即清陈旧标记态"——代码并未清标记（P3-2）；②`build.py:322` 顶层 `run_build` docstring 仍写"行缺失/向量覆盖不全"（未含内容集合/标记）；③`_repair` docstring/tester 报告"崩溃场景落库线索"不准确（崩溃无标记；标记=已捕获写失败）；④`tests/test_r2_m2s6_fixes.py:6` 首段"行数/向量覆盖率"（R2 表述）、`:190` "code/sync 键不嵌"（R3 仅 code）；⑤`fuzzy.build_fuzzy_terms` 函数 docstring 未记 `vec_expected`/code 预期 NULL；⑥`sem_fuzzy_terms_all` docstring 仍写"annotate fuzzy 内存面装载"（实际已被 `_repair` 内容对账消费——R1 P3-7 死代码面因此收窄，文档需同步）。
4. **`_repair` 每次 skipped 全量重算/全行读**（R2 P3-4 延续 + 放大）：与 P3-1 合并优化；规模 10⁴~10⁵ 下建议 build stats 存内容哈希或先看标记/计数再全量读。去向：m2-5 / 下一批。
5. **`search_entities` vec 档无有界超时/熔断/降级审计**（R2 P3-5）：to_thread 已消除事件循环阻塞，但 `embedder.embed` 仍用 `embed_timeout_s=30s`、无 `query_embed_timeout_s`/breaker、失败仅 warning；agentic 工具延迟/可观测面。登记。
6. **R1 P3 残留**（按裁定未动）：审计事件常量登记处（`EVENT_SEMANTIC_RESTRICTED_ACCESS` 在 core/semantic/constants）、持权审计两漏记（include=attrs 根实体 / 展开 restricted 端点）、编辑距离层含 name（§5.9 口径）、模糊内存面 dict 全量复制、top-3 硬编码、auto_entities ValueError 不降级、Protocol 签名陈旧（`sem_expand_graph`/`sem_search_entities`）、中间件 L1 缺 disambiguation、评测报告方法学（TokenBag vs FakeEmbedder）、测试覆盖（cap50 未触发/T-S8 未启向量路/T-S7 describe·l0/k_entity 未验路由）、matched_entities 口径——docs/下批；见 §6。
7. **（登记）构建产物代码版本未入 dict_rev**：pinyin/编辑距离算法或规范化代码变更不改变 dict_rev，静态词典下 skipped 不重建模糊索引（与 AC/L0 同类的 POC 构建产物 versioning 缝隙）；非本段引入，建议 known-gaps 一行登记。
8. **（监督侧 metadata nit）** `.env.example` 实际 101 行，检查点 R2 条目写"93→103"；归档时校正。

## 5. Tester R3 P3×1 处置意见

**持久化标记粘滞 → 登记（下批）+ docs 批写入裁定 5 注记**。
- 理由：功能幂等无害、异常构型（写失败/降级构建）下才出现，生产拓扑均带 embedder；但会放大 P3-4 的 per-skip 全量重算成本。
- 去向：m2s-6 followups / m2-5；建议与 P3-1 合并修法——`embed_model` 入内容集合后，标记触发面即冗余，可整体移除（或修复成功时经 `sem_update_build_stats` 清除 current 行标记）+ 加"再次 skipped 不重触"断言。docs 批在裁定 5 口径中写明当前"标记触发→修复→标记仍粘滞"的实际行为与下一批收口。

## 6. 交付归档建议（APPROVED）

### 6.1 docs 批（监督侧）
**design.md**（非决策勘误/口径补写，版本行声明）：
- §5.8/§5.9 模糊索引最终一致+修复路径（R3 实际谓词）：内容集合 `(entity_id, kind, text_norm)` vs `sem_fuzzy_terms_all` + 向量覆盖 + 落库标记；写库时机 ready 后、写失败标记经 `sem_update_build_stats` 持久化；**残余**——标记粘滞、`embed_model` 未入集合的模型迁移崩溃窗口（下一批收口）；`vec_expected` 语义。
- §5.9 工程口径：实词族（n/v/a/eng/x/j + 相邻实词 bigram）、编辑距离层含 name（设计字面"仅别名"的偏差）、`kind='code'` 唯一不嵌向量（sync/name/manual/abbr/definition 全嵌）。
- §6.3：G-2 并存①②落地；semantic:restricted 载体（membership role `sem_restricted`、POC 仅 DB/dev、无管理入口）；restricted 持权面（POC 仅 annotate/get_entity，search_entities/describe_table fail-closed）；中间件 L1 disambiguation 缺口（R1 P3-8）——注记或登记。
- 查询级审计缺口（T-S9⑥/A-16）→ known-gaps（FR-6 既有，非本段）。
- 构建产物 code versioning（P3-7）——known-gaps 一行。

**TEST-CASES.md → v1.9.10**：
- **完成态 ✅**：T-S7/S8/S9（按用户裁定 1/2/3：T-S7 三端点、T-S9 ①~⑤+持权、T-S9⑥ 登记 known-gaps）、TC-TAG-04/05、TC-SEM-08/09、TC-SEV-03、TC-YAML-05；§六 M2-S3 行整行收口（门禁 1479+1、语义轨道 6/6）。
- **口径注记**：TC-SEV-01/02 172→180 + pos_typo 排除分母；TC-SEM-05 排序链五档（exact/prefix/pinyin/FTS/vec，端点注入）；TC-SEM-09 模糊索引产物（code 不嵌、sync/name/manual/abbr/definition 嵌、`vec_expected`、修复路径）；A-16 T-S9⑥；A-4 G-2 落地。
- **下批登记**：T-S7 describe_table/l0 显式断言（裁定 1）；T-S8 向量路三路显式断言；T-S9⑥；TC-PERF-05 → m2-5。

**known-gaps.md**：
- G-21：本段核销 6 项（annotate 500/l0 空/latin/alias 0.95/double_build/search_entities 升级）+ 再挂 2 项（mixed-mode/l0_extra）+ 本轮 R3 残余（标记粘滞、embed_model 崩溃窗口）。
- 新增/补登：查询级审计 FR-6 缺口（T-S9⑥）；code 不嵌向量（§5.8 例外）；`_repair` per-skip 全量重算（P3-4 放大）；search_entities vec 30s/无降级审计；`fuzzy_repaired` 观测语义；R1 P3 残留清单（审计常量/持权审计/编辑距离含 name/dict 复制/top-3/auto_entities ValueError/Protocol 签名/L1 disambiguation/报告 TokenBag 方法学/测试覆盖/matched_entities）；构建产物 code versioning。

**AGENTS.md / _m2-plan.md**：
- 语义轨道 **6/6 完成**、M2-S3 收口、下一段按用户段序 **m2-4**；门禁 1479+1；G-21/TC-PERF-05/TC-UI 去向；PR/merge 记录；`.env.example` 行数 metadata 校正（101）。

**检查点终态**：`status=delivered`、`testVerdict=PASS`、`reviewVerdict=APPROVED`、`testedSha=reviewedSha=4057b40`、`round=3`、`endReason`、R3 报告全文、filesChanged 增补 R3 6 文件、交付归档批（docs-only HEAD）随 chore 入库。

### 6.2 遗留事项（跨任务移交，建议写入检查点）
- **m2-5**：TC-PERF-05；`_repair` per-skip 性能（与 R3 标记粘滞合并）；search_entities vec 超时/熔断/降级审计；模糊内存面 dict 复制/top-3 硬编码（R1 P3-4/5）。
- **下批（m2s-6 followups / 语义收口后）**：①R3 P2-2 残余——`embed_model` 入内容集合 + 标记清除/移除 + "模型迁移崩溃窗口"回归；②T-S7 describe_table/l0、T-S8 向量路、T-S9⑥ 显式断言；③R1 P3 残留（审计常量/持权审计/编辑距离 name/auto_entities ValueError/Protocol 签名/L1 disambiguation/matched_entities/报告方法学/测试覆盖 cap50/k_entity）；④构建产物 code versioning。
- **用户侧**：TC-UI-01~04 手动走查（持续挂账）。
- **新任务/主线段**：查询级审计 FR-6 实现（T-S9⑥/审计覆盖查询级）——登记为 known-gap，非本段。

### 6.3 manifest 要点（交付）
- taskId `task-knowledge-lattice-m2s-6`；分支 `develop_opencode`；base `60370d0`；R1 `e5a70d6` / R2 `e7fac5c` / R3 `4057b40`；HEAD=`4057b40`；**testedSha=reviewedSha=4057b40**；rounds=3、maxRounds=3。
- 门禁原始输出：1479 passed / 1 deselected（双模式）、0 skipped、pg 臂 527（494+33）、+4（2 新用例×双臂）。
- specRulings：R1 边界 8 条 + 规格登记 6 条 + code 仅排除口径 + 模糊索引最终一致/修复路径（含残余）。
- gapClosures：T-S7/S8/S9、TC-TAG-04/05、TC-SEM-08/09、TC-SEV-03、TC-YAML-05、G-21 核销项、P2×3（R1）/P2×2（R2）。
- handover：§6.2 全量。
- 交付留痕：docs 批 commit（docs-only）→ 最终 HEAD；用户确认交付后 `gh pr review` 将 APPROVED 结论落在 PR（合入不经手，只做审查留痕与放行确认）；PR 不删源分支。
- CASE_BUG 裁定请求：无。

**放行结论**：P1/P2 无；R3 对 R2 P2×2 与 P3-1/2/3/8 的修复均为生产路径上生效且有锁定用例（TDD 先红等价性经 Tester 实证），门禁 1479+1 双后端双模式 0 skipped，范围纪律与 docs 冻结合规。P3 残余（内容集合标签订正、标记粘滞、per-skip 性能、R1 P3）按 §5/§6 登记下批，不阻塞本段交付。**APPROVED**。

</details>
