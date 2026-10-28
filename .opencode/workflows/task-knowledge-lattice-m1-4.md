---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m1-4
target: knowledge-lattice
coderTaskId: ses_e8cea469effeDgSeDLzAGgETlK
testerTaskId: ses_e8c9f2db2ffepj2rUFKm40NHm8
committerTaskId: ses_e8c8795b7ffeZP5VDd9hMxLd9k
status: done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 912ddd52ba5c6ebdfb46cfaa26af34a230869784
reviewedSha: b2e36c09b657173c6742e0c53b28c8e969c94ccc
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["R1 48 files +4292/−112：新增 core/docs/quality.py（§5.4 权威实现：两路信号/LLM 兜底/numpy 批量重算/ACL 过滤报告/人工补标/误报抽查 + mojibake 三档门）+ api/quality.py（GET 报告近邻过 ACL/PATCH quality-flags/GET 抽样）", "新增 eval/{metrics,harness}.py（Recall@k/MRR 纯函数 + 批量上线→检索→标注对齐 harness）+ eval/corpus.jsonl（39 docs）+ eval/golden.jsonl（28 queries 全 multi-token）+ eval/reports/（双后端基线 + 标注记录）+ scripts/eval_baseline.py·quality_sample.py", "改 store 双后端 Quality 域 15 方法 + backend.py 协议 + pg/vec.py", "改 adapters/parser_docling.py（TXT 编码探测+老格式拒收）+ ingest.py（拒收/质量门/quality 挂接/P3-9 补偿）+ retrieve.py（P3-12/P3-13）+ config.py quality_* + app.py 装配 + acl.py·upload.py·credentials.py·mcp/server.py（403 机器码/文案）+ enhancer.py KeywordGenerator + pyproject numpy + fake_providers TokenBagEmbedder + conftest qual_env", "tests 新增 10 文件（qual 26/ing 12/eval 双后端/p3_followups 11）+ 改 7 文件（fts_04 REST 面/cred/pg_scaff/scaf_03/ver_01/conftest）", "R2 14 files +578/−57：quality.py P1-1(chunks_by_rids 取 content+空跳过+空 terms 防护)+P2-1(org_active_chunk_segs(None) 冷启动)+P3 顺手集（见后）、ingest.py P2-2(兜底接入 quality 阶段)+P2-3(补偿收窄)、adapters/textutil.py 新增(判分原语下沉)、parser_docling CRLF、tests qual_02+06b/qual_03+4/qual_06 新 3 用例/p3+2（顺手清偿集：sqlite create_task 注解/quality_sample docstring/sample 端点直测/eval docstring/labeling-notes/textutil 分层/403 文案/CRLF/PG 写路径——编号对照见 R2 coder 报告）", "docs 勘误批 b2e36c0 3 files +4/−4：TEST-CASES A-13 回写+design/requirements 日期行欠账+§5.1 笔误（supervised-coding 落笔）"]
endReason: null
createdAt: 2026-10-25T20:33:00+0800
updatedAt: 2026-10-26T21:21:00+0800
---

# task-knowledge-lattice-m1-4: M1-4 区分度环 + 语料批量上线 + 黄金集/评测基建 + 摄取补全（M1 开发收尾段）

## 任务原文

**需求**（design.md §8 M1.5+M1.6 开发部分，v0.9.4；与 requirements §8 M1 行对齐；前置 M1-1/2/3 已全部合入，origin/develop = 2da63ec。**范围注记：用户 2026-10-25 拍板拆分——性能/校准实验与越权矩阵收口移出至 M1-5（实验校准与 M1 验收收官段）；本段为 M1 开发收尾**）：

**A. 区分度反馈环**（design §8 M1.5；实现依据 §5.4 区分度检测 core/docs/quality.py）：

1. 绝对阈值判定 + **numpy 批量重算**（全库向量拥挤度/词面通用度批量计算）
2. LLM 兜底写独立列（keywords 补充——TC-QUAL-03）
3. 报告页近邻查询**过 ACL**（近邻防旁路——TC-QUAL-05）
4. 规模比例 + 抽样重算机制（TC-QUAL-04）
5. **PATCH /api/quality-flags/{id} 端点**（区分度标记写入口——TC-FTS-04 REST 面硬条件依赖此端点）

**B. 语料批量上线 + 小型黄金集 + 评测基建**（design §8 M1.6）：

1. **真实文档批量上线**（待决-1 真实语料未到位则**合成样例先行**——design 既有注记；批量走 M1-3 凭证制或 multipart 均可，验证批量摄取链）
2. **小型黄金集**（几十条真实/合成 query + 标注命中 chunk——issue #31 P2-3；**双后端各一份校准基线**——G-6；**覆盖多 token 场景**——m1-1 Tester 观察项）
3. **Recall@k / MRR 检索层指标**（TC-EVAL-01；M1 检索调参的度量依据——评测 harness 最小实现，响应层指标与 judge 属 M3 不做）
4. 区分度误报抽查机制（M1.7 验收句——抽查记录形态，阈值校准实验属 M1-5 不在本段）

**C. 摄取补全**（TEST-CASES §六 M1 行摄取补全组——批量上线前置）：

- TC-ING-04（编码与老格式策略：TXT 非 UTF-8 探测转换、.doc/.xls/.ppt 拒收提示转存）
- TC-ING-05（mojibake 质量门三档）
- TC-ING-06（嵌入分批与钉标签——v1.6 迁 chunk_vectors 写路径口径）

**D. docs 批——✅ 已由 supervised-coding commit b2e36c0（doc-only 放行）：①TEST-CASES A-13 回写（已闭环——v0.9.4 定拒绝无残留待办）；②design 日期行补 v0.9.1~v0.9.4 + requirements 日期行补 v0.9.2~v0.9.4；③design §5.1 笔误「MCP token org claim」→「token org claim」。原条目：**

1. TEST-CASES 附录 A-13 回写（「截断/拒绝二义待回写」→ 已定拒绝——m1-3 doc-only 复核要求独立登记项）
2. design/requirements「日期」历史行补 v0.9.2/v0.9.3/v0.9.4 欠账
3. design §5.1 一字笔误（「MCP token org claim」→「token org claim」——m1-3 committer R2 P3-1）

**口径与边界**：

- **待决-1 真实语料**未到位时合成样例先行，依赖真实数据的验收顺延并登记（design 既有注记）。
- **本段不做**（已移出至 M1-5）：TC-PERF-03/04 SLO 标定、G-8 MRL/指纹阈值校准、G-6 双后端偏差评估与 halfvec 对比、蓝绿复测、越权矩阵全量收口、TC-UI 走查、§六 M1 行总勾验、误报抽查实验、A-8 核销。
- **响应层指标与 judge/deepeval 门禁属 M3**；管理面全端点、90 天清理、备份恢复属 M2。
- 设计冻结纪律：docs/ 的 D 组勘误由 supervised-coding 落笔，coder 禁改；实现问题走测试用例与 issue。
- commit 格式 `[task-knowledge-lattice-m1-4] R<n>`，develop_opencode 分支，commit 前同步 origin/develop，不 push。

**流程纪律（M1 系列延续，用户 2026-10-25 拍板）**：

- **跨检查点会话隔离**：本检查点对应全新 Coder/Tester/Committer 会话（不复用 m1-1/2/3 的 task_id）；检查点内多轮续接复用各自会话。
- **执行模式 A 串行紧衔接**：M1-4 完成后接 M1-5（实验校准与 M1 验收收官段），M1-5 完成合入即 **M1 里程碑整体达成**。

**承接遗留事项**（本段"触及即顺手"清偿，处理完回写勾选并注来源；三组管理）：

**组 1：测试卫生批**（m1-3 committer R2 §8 P3 残项 + 各轮积累）：

- [x] P3-1 残——✅ R1 清偿（文案去内部号、docstring 保留出处）
- [x] P3-5 残——✅ R1 清偿（test_scaf_03 补 5 项断言）
- [x] P3-17 残——✅ R1 清偿（_write_pg_v3→_write_extra_v4 名实对齐；cred_04 改 env[backend]；「注释 0003→0005」项不适用——本段无新增内置迁移，注释按实际水位 0003 表述）
- [x] P3-19 残——✅ R1 清偿（协议+双方言 str | None）
- [x] P3-8/12/13 无直测——✅ R1 清偿（竞态清 final/purge 越界纵深/双正则尾换行拒绝）
- [x] finalize None/consumed——✅ R1 清偿（None→410、consumed→409，无孤儿断言）
- [x] 403 机器码+文案泛化——✅ R1 清偿（AclDeniedError 带 code、REST body.code=membership_denied、MCP 同步；不回显绑定侧取值）
- [x] P2-1 stale 镜像阈值——✅ R1 清偿（独立常量 900+边界双点 899/901）
- [x] P3-9（m1-2）孤儿对象——✅ R1 清偿（DB 失败 unlink 补偿+直测）
- [x] docstring 旧口径——✅ R1 清偿（resolve_org 新口径）

**组 2：硬条件项**（前段验收的未闭环承诺）：

- [x] **TC-FTS-04 REST 面断言补验（硬条件）**——✅ R1 闭环（PATCH 端点实装+端到端断言：keywords 字面等值不进 jieba/llm_keywords 不触碰/×5 命中/落库/ACL）
- [x] **P3-18 REST PG 参数化**——⏸ R1 登记 M2 待 supervised-coding 认可（create_app 硬绑 sqlite：ThreadLocalBackend+迁移引导；PG 版需池化 backend+全 REST 套件 PG 化，非低成本；降缺口：本段业务逻辑 quality/ing/eval 双后端参数化实跑，REST 仅方言无关壳）

**组 3：收口项（开发类，M1-4 内做）**：

- [x] P3-7 加固——✅ R1 清偿（双方言 UPDATE+SELECT 双守卫；lexical 态拒绝直测；TC-VER-04 按 D20 时点适配；真并发留 M2）
- [x] P3-13 耗时四段——✅ R1 清偿（embed/recall/fuse/rerank 增量时长直测；M1-5 标定数据源就位）
- [x] P3-12 空 query——✅ R1 清偿（search 层早返回 []，置于 compile_acl 后 403 不被绕过；API min_length 未采用避免双面各写）


**顺延补登（m1-4 committer R2 §5，去向明示——触及即顺手、未触及保留去向）**：

- [ ] content_sha 未含 embed_model → **M2 reembed 实作前必补**（缓存键与 §4 L401 一致，换模型时旧 vector_crowding 清理）
- [ ] 耗时 fuse 段含增强等待双计 → **M1-5 开增强路前修**（否则污染 NFR-8 分解）
- [ ] quality_* env 覆盖 → 部署前
- [ ] 旧版本/墓碑 flag 进自动 LLM 批（按新 detect flags 或 active version 过滤）→ M2
- [ ] 「重跑可补」docstring 不成立（full 早返回）→ 改文案或加重试标记 → M2
- [ ] LLM 钩子无时间预算 → M1-5/M2 开 provider 前评估
- [ ] create_task 失败残留 parsing 无任务文档 → M2 维护
**验收标准**（双后端参数化各跑；门禁 scripts/test_gate.sh skip≠pass）：

- TC-QUAL-01~05（区分度环全条）
- TC-ING-04~06（摄取补全）
- TC-EVAL-01（黄金集 Recall@k/MRR——双后端基线，**多 token 场景覆盖**）
- TC-FTS-04 REST 面补验（硬条件闭环）
- TC-E2E 族存量复跑不回退；SQLite 臂全量绿；基线对账自洽（当前 523+1）
- 黄金集标注记录归档（M1-5 校准实验的输入）

## 需求确认

- [x] 用户已确认（2026-10-25 拍板拆分方案即范围确认——M1-4=开发收尾段、M1-5=实验校准与 M1 验收收官段；status=implementing）
- 历史遗留事项清单：knowledge-lattice 9 检查点全 done（m1-3 于 2026-10-25 合入 PR #52）；M1-4 段承接三组 14 条如上；校准/矩阵/性能组 8+ 条移交 M1-5（见 task-knowledge-lattice-m1-5.md）

## 遗留事项（跨任务移交）

- [ ] 无（本段新增移交项随轮次记录登记）

## 轮次记录

- R1: coder 完成（2026-10-25，**全新会话**，coderTaskId=ses_e8cea469effeDgSeDLzAGgETlK，commit `7567508d5ad638d6decdfcb12c6e59bd887b7efa` 于 develop_opencode，48 files +4292/−112，父提交=2da63ec 同步后）——A 区分度环（quality.py §5.4 权威实现+api/quality.py 三端点+双方言 Quality 域 15 方法）；B 评测基建（eval/metrics+harness+corpus 39 docs+golden 28 queries 全 multi-token+双后端基线归档）；C 摄取补全（TXT 编码探测+老格式拒收+mojibake 三档+ING-06 分批钉标签）；遗留 13/14 清偿（P3-18 登记 M2 待认可）。自测：GATE PASS **586+1 双后端双模式 0 skipped**（pg 臂 212；+63 对账）；TC-EVAL-01 双后端基线 sqlite r@10=0.8929/MRR=0.8345、pg 0.7857/0.7277；万级块重算 sqlite 4.6s/pg 9.9s。机械核验：HEAD/格式/docs 零 diff/origin 同步/未 push 全过。**口径申报 9 条**：①区分度阈值初值（拥挤 0.92/词面 IDF<3.0/冷启动<10 块全局 IDF——真实语料重标定随 M1-5）②numpy 重算触发（候选=未测或规模×0.5 ∪ 10% 抽样；worker 周期随 M2）③黄金集构成（zh12/en8/mix8；跨语言不可达标注按可检索性约束修订）④harness 形态（TokenBagEmbedder(32) 稠密代理——FakeEmbedder 纯噪声压过 BM25；代理口径入基线报告）⑤PATCH 契约（keywords/tags 追加写人工列不进 jieba；state 三态；owner/org_admin）⑥空 query 择型 search 层早返回 ⑦mojibake 重试=解码候选择优 ⑧quality 阶段 best-effort 不回退 searchable_full ⑨LLM 兜底缺省 none。**边界申报 4 条**：①P3-18→M2 待认可 ②mcp/server.py 注释「list_documents 随 M1-4」但本段范围无此工具——归属待裁（supervised-coding 交 Tester 查证 design §6.1 里程碑标注）③PG 黄金集召回差异（0.7857 vs 0.8929）根因=to_tsquery & AND 语义（G-6 已登记），未擅自改 OR——M1-5 决策（停用词滤除或口径变更流程）④无其他冲突、零回退
- R1: tester **PASS**（2026-10-25，全新会话，testerTaskId=ses_e8c9f2db2ffepj2rUFKm40NHm8，testedSha=7567508 复核一致）——门禁独立复跑 586+1 双模式 0 skipped（与 coder 一致）、pg 臂 212 全实跑、+63 对账精确吻合。TC-QUAL-01~05 逐条强断言（拥挤度 tombstone/跨组织排除、IDF 边界对照、LLM 兜底 keywords/embedding 逐字节不动、万级重算 10000 flagged 精确、近邻过 ACL + detail_json 原始保留）；TC-ING-04~06 全过（拒收先于落盘无孤儿/三档边界精确点/断点续跑恰 6 块）；**TC-EVAL-01 双后端基线**（复跑与归档逐 query 全等；标注 fail-fast 实证；28/28 multi-token）；**TC-FTS-04 REST 硬条件闭环**（PATCH 端到端：keywords 字面等值/×5 命中/ACL 面——m1-1/m1-2 移交硬条件解除）。**PG 召回差异根因专节**：逐 query 归因实证——5 个掉分 query 全部 AND 全词交集不可达（q01/q10 疑问词 0 命中、q19/q20 措辞跨语言错位、q21 双语块可救半）+ q24 反超（AND 收窄提升 title 精确率）——**口径性差异非缺陷非标注错误**；M1-5 路径意见：偏差 10.7pp>2pp 已触发 G-6 收窄②钩子必须出决策；停用词只能救 +7.1pp；PG 切 OR 属口径变更不建议实验顺手做；**建议先接真实嵌入模型重测基线再决策**（TokenBag 代理对跨语言 query 系统性低估）。**边界 4 条裁定**：①P3-18→M2 认可（业务逻辑双后端实跑充分、REST 方言无关壳）；②**list_documents 归属建议 M1-5 补**（design §6.1 有完整 schema 无里程碑标注；TEST-CASES T17/TC-AZ-02 以其为执行主体且属 M1 矩阵验收——依赖缺口；工作量小复用 visible_docs；mcp 注释「随 M1-4」陈旧需同步修正）；③PG 差异路径 ACCEPT；④零回退 ACCEPT。回归零弱化零删除（8 存量文件逐一审 + VER/ACL/CRED 129 passed 抽复）。口径 9 条全 ACCEPT。新观察 4 条（quality_sample.py docstring --backend 失实/rest sample 端点零直测/**P3-11 掉落登记断裂**——m1-1 R2 顺延 M1-4 的 PG to_tsquery 负向用例未进 m1-4 承接清单/eval docstring 微瑕两处）


- R1: committer **NEEDS_CHANGES**（2026-10-25，全新会话，committerTaskId=ses_e8c8795b7ffeZP5VDd9hMxLd9k，reviewedSha=7567508 静态全量 diff 审查；bash 只读白名单未复跑采信 Tester + 静态对账 +63 吻合）——核验通过 12 维（§5.4 detect 路径双方言 ACL 约束/LLM 写入面/批量候选与 10k/ACL 防旁路/best-effort/PATCH 契约/store 17 方法/TC-ING/harness 手算核对/回归零弱化/PG 根因 ftv.py 确认 AND/OR/口径②⑤⑥ 抽查合规）。**P1-1（阻塞）：LLM 兜底 provider 实际收到空内容**——run_llm_keywords 的 flag.get("content") 永远 None（_QFLAG_COLS 与 get_chunk 均无 content）；quality_llm!=none 时送空片段；FakeKeywordClient 只断言 calls 未断言入参——修法：chunks_by_rids 取 content/空内容跳过/仅 terms 非空时写/TC-QUAL-03 增入参断言。**P2-1：重算缺冷启动全局 IDF**（recompute 用 org df + idf_scope 固定 org）——修法：org_active_chunk_segs 扩 None + 冷启动全局 + 对照用例。**P2-2：LLM 兜底无调用点**（FR-3 自动兜底不成立，默认 none 掩盖）——修法：detect 后调用 noop 零成本 + 端到端用例。**P2-3：P3-9 补偿过宽**（try 包 create_task——失败 unlink 对象但文档行不回滚）——修法：收窄 + create_task 失败保留对象 + monkeypatch 用例。**P2-4（登记 M1-5）：100k 内存与 PG 65535 参数上限**——TC-PERF-03 前必须解决。**P3-1~P3-14（原报告 14 项，下为归类摘要非逐项）**：sqlite create_task 注解/quality_sample docstring/sample 端点零直测/eval docstring 35→39/labeling-notes 漏 4 篇/q27 lang→M1-5 黄金集修订/mcp 注释随归属裁定/docs 对齐 4 处（supervised-coding 批次）/decode_txt_bytes 分层倒置/content_sha 未含 embed_model（M2 reembed 前）/fuse 双计（M1-5 开增强路前）/CRLF/403 FR-4 残/PG 写路径缺口 R2 补/tombstone flags（M2）/quality_* env（部署前）。**需求边界 3 条**：B-1（重要）M1-5「双后端各跑」vs create_app 硬绑 sqlite 冲突；B-2（低）「分位下限」口径统一；B-3（重要）M1-5 G-6「ts_rank_cd」不能解 AND 零召回——建议真实模型重测→停用词→OR 决策流程写入任务。**处置**：B-1/B-3 找用户、B-2 登记；P1/P2-1~3 + P3 → R2（P2-4 → M1-5 顺延）
- R2: spec_confirm 处置（2026-10-26 19:41）——**B-1 用户拍板「按建议来」= 选项①**：M1 验收「双后端各跑」限定 DB/服务/MCP 层，REST-PG 留 M2 写入 M1-5 验收对照残项（m1-5 检查点已同步）。**B-3 用户同意**：M1-5 G-6 决策路径改写「真实嵌入模型重测→停用词评估（+7.1pp）→OR 口径走决策变更流程；ts_rank_cd 仅排序对照」（m1-5 已同步 + known-gaps M1-5 校准时回写）。B-2 按登记（M1-5 docs 批统一口径）。R2 范围下达 coder（复用会话）：必修 P1-1/P2-1/P2-2/P2-3；顺手 sqlite create_task 注解/quality_sample docstring/sample 端点 2 断言/eval docstring/labeling-notes/decode_txt_bytes 分层/403 文案/CRLF/PG 写路径缺口；登记顺延 5 项；docs 对齐 4 处 supervised-coding 落笔
- R2: coder 完成（2026-10-26，**续接会话**，coderTaskId 同 R1，commit `912ddd52ba5c6ebdfb46cfaa26af34a230869784` 于 develop_opencode，14 files +578/−57，父=7567508，origin/develop 2da63ec 同步确认，未 push）——**P1-1 已修（红灯实录）**：修前 3 failed（test_qual_03 单文件子集口径；Tester 全文件双后端口径 6 failed——同一缺陷两面，scope 差异非矛盾）（provider 收空内容 ['',''] 精确暴露）→ chunks_by_rids 取 content+空跳过+空 terms 防护+07/07b/07c 三态断言 → 8 passed 双后端；**P2-1 已修**：org_active_chunk_segs(None) 双方言+冷启动全局 df+idf_scope=global+06b 对照（global/org 双点）；**P2-2 已修（接入不登记 M2）**：_quality_stage 检测后 run_llm_keywords（noop 早返回；检测失败不发起兜底——择型②）+08b 端到端+08c noop；**P2-3 已修**：unlink 仅包 create_document/_start_overwrite、create_task 失败保留对象+monkeypatch 用例；**顺手 9 项**：sqlite create_task 注解/quality_sample docstring sqlite-only/sample 端点 403+clamp+seed 三面（超建议范围）/eval docstring 39+labeling-notes 补 4 篇/textutil 下沉（择型③：adapters/textutil.py+re-export 保 import 面）/403 文案/CRLF/PG 写路径 test_qual_06 新文件 3 用例双后端（追加语义+FTS 同步+manual_tags 轨迹+org_admin 放行+跨 org 404 三 actor）；顺延 5 项零触碰（content_sha+embed_model→M2/fuse 双计→M1-5/tombstone flags→M2/env 覆盖→部署前/q27→M1-5）；docs 禁改遵守（对齐 4 处归 supervised-coding）。自测：GATE PASS **604+1 双后端双模式 0 skipped**（pg 臂 220；+18 对账 qual_02+2/qual_03+8/qual_06+6/p3+2）；重申零 skip/xfail/删除/放宽。**择型 3 条**：①半产出写面（terms/locator 独立判定）②检测失败不发起兜底③textutil 归属。机械核验：HEAD/格式/docs 零 diff/origin 同步/未 push 全过
- R2: tester **PASS**（2026-10-26，续接会话，testerTaskId=ses_e8c9f2db2ffepj2rUFKm40NHm8，testedSha=912ddd5 复核一致）——门禁独立复跑 604+1 双模式 0 skipped（与 coder 一致）、pg 臂 220 全实跑、+18 逐文件精确吻合（pg 212→220 交叉自洽）。**P1-1 注入实证**：sed 置换空内容→恰 6 failed 零附带伤害（07/07c/08b 全部双后端红——正文获取与空跳过两面同验）→恢复→12 passed；07/07b/07c 三态断言全钉。P2-1 06b 双点+双方言 SQL 逐行 diff 同构；P2-2 08b 端到端+08c noop+检测失败不发起兜底静态核；P2-3 monkeypatch 双断言+与 P3-9 双分支互补；P3×9 全落地（qual_06 闭环 R1 PG PATCH 缺口；sample 三面直测超建议范围）。回归零弱化（R2 diff 存量纯增+抽复 102 passed）。择型 3 条全 ACCEPT（①记录级注记 auto_keywords 对称防护可选 ②分支零直测→观察 O1 ③风格注记 re-export 位置）。新增观察 5 条不阻塞（O1 检测失败分支零直测建议下轮补/O2 get_chunk+chunks_by_rids 双查询冗余记录级/O3 06b 编号观感/**O4 P3-11 移交断裂——已裁定 M1-5 补登（m1-5 line 69）**/O5 q27 留 M1-5 标注批）。R1 意见清偿对账 8 项全 ✅
- R2: committer **APPROVED**（2026-10-26，续接会话，reviewedSha=912ddd5=testedSha=HEAD 双 SHA 一致；静态对账 +18 吻合；bash 只读白名单未复跑采信 Tester）——**R1 P1/P2-1~3 项全闭环（P2-4 顺延 M1-5；P3 项按分级 8✅/1◐/5⏸）**：P1-1（chunks_by_rids 双方言 SELECT content/空串跳过/半产出不破坏；08b 覆盖完整；无空内容面残留）/P2-1/P2-2/P2-3 ✅；P3-1/2/3/7/10/12/13/14 ✅、P3-4 ◐ 部分（q27 归 M1-5）、P3-5/6/8/9/11 ⏸ 登记态（编号分组依 committer R2 复审 §1 表；明细见本检查点「顺延补登」块与 M1-5 承接清单——此前转写误植入 m1-3 的 P3 项描述，已剔除）；P2-4 顺延成立（M1-5 line 67）。**P1-1 深层：真正闭环无空内容面残留；非 P1**。残余 P3：①旧版本/墓碑 flag 进自动 LLM 批（建议按新 detect flags 或 active version 过滤）②「重跑可补」不成立（_run_stages full 早返回——改文案或加重试标记）③LLM 钩子无时间预算（M1-5/M2 开 provider 前评估）④create_task 失败残留 parsing 无任务文档（M2）⑤qual_16 owner 分支命名 ⑥sample clamp 断言宽松 ⑦06b 注释 N=21 实际 26 ⑧顺延登记可见性（P3-8/P3-9 fuse/P3-11 env 三项需补）⑨**本检查点 R2 记录缺失**（审查时读取状态——supervisor 已确认事故并补录）⑩M1-5 line 77/87 限定同步 ⑪textutil 入 §3 模块图（可选）⑫qual_06 未用 import。**MCP search/fetch/upload 写路径成员校验全覆盖确认**（search/fetch 走 compile_acl、upload 走 _require_usable）。**择型 3 条最终把关全 ACCEPT**（②认可为防御性择型登记不阻塞、O1 不建议为此开 R3）。**B-1/B-3/B-2 已用户拍板并在 M1-5 登记；O4/O5 闭环**。**结论 APPROVED——代码可交付；evidence manifest/检查点 R2 记录与 docs D 组完成前不正式放行交付**（supervisor 收口：本轮已补录 R2 四条记录 + reviewedSha 回填 + M1-5 line 77/87 同步 + 顺延三项补登）
- 检查点完整性专项修正（2026-10-26 20:59，supervised-coding，响应 committer 专项审查 B-1~B-8）：**B-1** status delivering→approved（delivering 非状态机值——事故根因之一）+ reviewedSha 回填 b2e36c0（doc-only 放行值，沿 m1-3 cd915f8 先例；testedSha 保持 912ddd5 代码测试 SHA——双 SHA 口径：HEAD=reviewedSha=b2e36c0 含 docs 批、testedSha=代码级）+ updatedAt 刷新 + filesChanged 补 R2/docs 两段；**B-2** R2 committer 记录 P3 分类修正（P3-8 从 ✅ 改 ⏸ 组——原转写与顺延块 L97 自相矛盾；分级改为 8✅/1◐/5⏸；「全闭环」改「P1/P2-1~3 项全闭环（P2-4 顺延 M1-5）」）；**B-3** R1 committer 记录「P3×14」改「P3-1~P3-14 归类摘要非逐项」（原报告 14 项——首轮转写误写 20 项，本轮统一为 14）；**B-4** R2 coder 红灯计数注明 scope（3 failed=qual_03 单文件子集；Tester 6 failed=全文件双后端——同一缺陷两面）；**B-5 结构**：「## 最新验证意见原文」标题从 R1 tester 后移至 R2 committer 后（R1 committer+R2 四条回归轮次记录节）；**B-6** D 组说明更新（b2e36c0 已 commit）；**B-8** O4 措辞回写（已裁定 M1-5）；P2-4 排除句核实为未改——本项修正 R1 committer 处置句（见下）；**B-7** m1-5 承接清单补 fuse 双计/LLM 钩子两行。全部修正经 grep 计数核验（七条记录各 1、P3-8 ⏸ 组 1 处、m1-5 承接 2 行）

- 残项复核修正（2026-10-26 21:09，supervised-coding，响应 committer 第二轮专项残项清单）：残项 1（⏸ 组 m1-3 描述误植入剔除）/2（P1/P2-1~3+P2-4 排除三处+自证句如实化）/4（D 组矛盾短语删除）/5（统一 P3-1~P3-14 十四项口径）已修；残项 3（filesChanged 旧编号串错误引用→实际修正集（quality_sample docstring 修/sample 端点直测/eval docstring/labeling-notes 补录/textutil 分层/403 文案/CRLF/create_task 注解）已修；L133 B-2/B-3 摘要同步最终口径。核验：旧编号串（P3-斜杠-8-12-13-20 形态，不再复写字面）在 filesChanged R2 段已替换为实际修正集描述
- 交付完成（2026-10-26）：①Coder 同步 origin/develop（Already up to date）+ push develop_opencode `cd915f8..b2e36c0`（SSH；3 commits——coder 纠正 supervised-coding 前置描述的「4 commit」计数错误）；②**PR #53** 开立（base=develop，MERGEABLE/CLEAN，52 唯一文件无流程文件混入），description 含 evidence manifest（testedSha=912ddd5 代码级 / reviewedSha=b2e36c0=交付 HEAD 含 docs 批 / GATE 604+1 双后端双模式 0 skipped / pg 臂 220 / boundaryNote 四条边界裁定 / carriedOver M1-5+M2 两组）；③Committer 正式评审留痕 review id `PRR_kwDOTsiHgs8AAAABUOtCvA`（COMMENTED @2026-10-26T13:17:02Z，首行「评审结论=APPROVED（可交用户合入）」——单账号留痕标准）。**待用户合入 PR #53；合入即 M1-4 里程碑达成，下一段 M1-5（实验校准与 M1 验收收官段——M1 最后一段）新检查点新会话**
- **合入完成（2026-10-26 21:21 用户指令"合入"）**：PR #53 state=MERGED，mergedAt=2026-10-26T13:20:30Z，mergeCommit=`befff9e884d541d1780ea80556fa097b31ae09cb`；origin/develop 前进 `2da63ec..befff9e`（含交付 3 commits + 检查点归档 commit 共 4 个）；develop_opencode 远端按 D30 保留——**M1-4 正式完成（done），M1-4 里程碑达成**（区分度环 + 评测基建 + 摄取补全 + TC-FTS-04 硬条件闭环 + 边界四条裁定落地）。下一步 M1-5（实验校准与 M1 验收收官段——M1 最后一段）：新检查点 + 全新 Coder/Tester/Committer 会话；**M1-5 完成合入即 M1 里程碑整体达成**
- **检查点归档（2026-10-26 21:20 用户指令「检查点文件也都要一并提交推送」——历轮「流程文件不入 commit」惯例自此废止）**：commit `649d8322e4e399e26d7ea614b731800bfd1d0899`（6 files +1011/−2：m0b-3 done 记录 + m1-1~m1-5 全量检查点）+ push `b2e36c0..649d832`——PR #53 现含 4 commits（交付 3 + 检查点归档 1），合入 #53 时一并入库。本条记录与后续 updatedAt 更新将随 M1-5 交付批或下次归档入库（活文档特性）
## 最新验证意见原文
- R1 Tester 报告关键细节补充（2026-10-25，逐字级——PG 召回差异逐 query 归因表，**M1-5 校准实验输入**）：

| qid | query | sqlite r@10→pg | FTS(AND)路 | 根因（实证数据） |
|---|---|---|---|---|
| q01 | 留抵退税的申请条件是什么 | 1.0→**0.0** | **0 召回** | 疑问词「什么」全库 content_tsv **0 命中**→全词交集必空；标注块对齐 5/7（缺 什么/是，OR 下可召回——sqlite FTS 名次 1→RRF 第 2）；向量路标注第 12 名挤不进 top10 |
| q10 | 消费税的征收范围包括哪些 | 1.0→**0.0** | **0 召回** | 疑问词「哪些」**0 命中**→同上；标注块 gk-enc-01（GBK 文档）对齐 5/6；向量路第 22 名 |
| q19 | simplified taxation method small-scale taxpayer | 1.0→**0.5** | 0 召回 | 复合词切分+措辞错位：gk-vat-04 对齐 3/6（缺 small/scale/taxpayer）、gk-vat-07 对齐 5/6（缺 taxation）→AND 不可达；向量路 5/13 名→仅 gk-vat-07 进 top10（rr 1.0→0.2） |
| q20 | stamp duty loan contract rate | 1.0→**0.0** | 0 召回 | 「loan」**0 命中**（英文 query 措辞 vs 中文语料「借款合同」跨语言 token 错位）；标注块对齐 3/5；向量路第 11 名差一位 |
| q21 | VAT 留抵退税 excess input VAT refund 申请 | 1.0→**0.5** | 1 召回 | 双语标注块 gk-mix-01 全词 7/7 命中（RRF 第 1）；纯中文 gk-vat-01 对齐 3/7 不可达、向量第 14 名→recall 0.5 |
| q24（反超） | 个税 individual income tax 年终奖计税 | 0.0→**1.0** | 1 召回 | jieba 把「个税」切「个」+「税」→gk-mix-07 **title_seg 7/7 全命中**独占 FTS 头名进 RRF 第 1；sqlite OR 下 18 块召回名次稀释被双路块挤出 top10——**AND 收窄在 title 同源分词场景反而提升精确率**（差异非单边变坏） |

**根因裁定**：Coder 申报的「to_tsquery & AND 语义」实证成立。五个掉分 query 全部是 AND 全词交集不可达（2 个纯疑问词案例 + 3 个措辞/跨语言 token 错位案例），向量代理路救不回（第 11~22 名）；q24 反超亦同源。**属口径性差异（G-6 已登记 + §5.2 钉死），非实现缺陷、非标注错误。**

**M1-5 决策路径意见（边界③）**：①G-6 收窄动作②的既定钩子已触发——偏差 10.7pp > 2pp 阈值，M1-5 必须按 G-6 记录并出决策；②**停用词滤除只能救 q01/q10（+2/28≈+7.1pp→0.857）**：q19/q20/q21 的缺口是措辞/跨语言 token 错位（taxpayer/small-scale/loan 等**实词**缺失），非停用词可解；③PG 切 OR 是 §5.2 口径变更、须走决策变更流程，**不建议由校准实验顺手做**；④q20/q21 类跨语言缺口在 TokenBag 代理下必然存在，真实嵌入模型（M1-5 接入）有跨语言泛化，**建议先接真实模型重测基线再决定是否动 FTS 口径**——避免按代理口径失真数据做口径变更。

**边界② list_documents 归属查证全文**：design §6.1（L1093-1103）有完整工具 schema、FR-5 列 docs 组四工具、**无里程碑后缀**（对比 semantic 组明确标「M2-S」）；§8 M1 行未点名该工具、M2 行亦未点名。但 **TEST-CASES T17（L660）与 TC-AZ-02（L708-714）以 MCP list_documents 为执行主体，且二者属 §六 M1 行「越权矩阵全绿」验收范围**；requirements L122/143 的 owner 兜底（#34 必修 2）也以它为载体。m1-5 检查点 C 组收口矩阵 T1~T23+TC-AZ 但未列工具开发——**存在依赖缺口**。归属建议：**M1-5 补**（最晚点——M1-5 是 M1 验收收官段，矩阵 TC-AZ-02 无此工具无法真协议执行；工作量小——复用 visible_docs 统计口径 + 四字段状态，非新域；不建议 M2——会把 M1 验收硬行悬空；本段 R2 补亦可但会扩大本段范围）。同时 mcp/server.py L22/L97「随 M1-4」注释为陈旧预告，归属裁定后应同步修正。

**新观察项 4 条原文**：①P3-新-1 `scripts/quality_sample.py` docstring 用法失实（IMPL_BUG·轻微）——docstring 给 `--backend pg` 但 argparse 无此参数，实跑 unrecognized arguments；建议 R2 顺手 argparse 补 pg 分支或删 docstring 行。②P3-新-2 REST `GET /api/quality-flags/sample` 端点零直测——服务层有测试但 REST 入口 org_admin 403 门与 n clamp（1~100）无用例；建议 R2 顺手补 2 断言。③**移交断裂登记（supervisor 层）**：m1-1 R2 登记顺延 M1-4 的 **P3-11（PG to_tsquery 负向用例：畸形参数 + 语法错误降级评估）未进入 M1-4 检查点承接清单**，本段未落；建议 committer 登记去向（M1-5 或 M2），避免二次断裂。④测试 docstring 微瑕：test_eval_01_golden.py L4「35 docs」与实际 39 不符；golden q27 query 纯中文标 lang=mix（仅影响报告分组）。
