---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m1-1
target: knowledge-lattice
coderTaskId: ses_e8f6e3b22ffeFjqXFsYGV7uyp0
testerTaskId: ses_e8f313ea4ffe5rm7Th5L9qYxC5
committerTaskId: ses_e8f1b5210ffemAf2R47vW6wdlX
status: done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: f741f31770f910628c3ea443275e2eeb4534dbb2
reviewedSha: 9565193d5ec8e90feef10eb86d624407ba393af2
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["【P3-1 计数更正：R1 新用例 71 条（非 76）——门禁 +71/tester 复跑 71 三向吻合】R1 28 files +2660/−104：src/knowledge_lattice/core/docs/retrieve.py 重写(+493 完整配方编排：双路+RRF+增强窗口+rerank 降级链+归一+ACL 双断言+degraded 审计+名次协议)", "src/knowledge_lattice/adapters/reranker.py Cohere /rerank httpx 客户端(超时 1000ms)", "adapters/enhancer.py 新增(Enhancer 协议+Noop+chat completions ≤8 词条)", "adapters/breaker.py 新增(NFR-8 熔断 3 次/60s 半开)", "adapters/tokenizer.py 判据函数 token_alignment/cjk_fallback_verdict(遗留①)", "store/backend.py Search 协议 rank 名次协议+visible_chunk_ids/rids_without_vector", "store/postgres/fts.py 新增(to_tsquery 引号字面量+& 连接+五列 ts_rank 权重)", "store/postgres/acl_render.py Match 节点渲染+render_fts_recall_select", "store/postgres/backend.py recall_fts/recall_vec 实装(追平全矩阵)+_attach_dims", "store/sqlite/acl_render.py render_vec_recall_select(vec_distance_cosine+cv JOIN)", "store/sqlite/backend.py recall_fts 名次化+recall_vec 实装", "config.py 检索配方配置 18 项+env 覆盖", "app.py/api/search.py/mcp/server.py providers 组装注入+REST asyncio.to_thread", "tests 新建 6 验收文件(test_ret_01_recipe 609 行/test_emb_04_05_07/test_acl_08/test_fts_04/test_fts_05_cjk_judge/test_e2e_04)+基建(conftest ret_stack/fake_providers 三假实现/dbwrap insert_vector)+存量校准 4 文件", "【R2 勘误批(supervised-coding 落笔，未 commit)：docs/design.md v0.9.2 三处 + docs/TEST-CASES.md v1.6.1 四处——见 R2 轮次记录】"]
endReason: null
createdAt: 2026-10-25T08:56:09+0800
updatedAt: 2026-10-25T13:04:00+0800-10-25T12:10:00+0800-10-25T12:01:00+0800-10-25T11:56:34+0800
---

# task-knowledge-lattice-m1-1: M1-1 完整检索配方（双路 + RRF + rerank + 增强 + 归一）+ PG 后端追平全矩阵

## 任务原文

**需求**（design.md §8 M1.1，v0.9.1；与 requirements §8 M1 行对齐）：

在 M0a/M0b 既有基础上实现完整检索配方，并让 PostgreSQL 后端追平全功能矩阵：

1. **五列 FTS 加权检索**：五列（title/keywords/headings/body_text 等既有列）加权 bm25，中文分词沿用 M0a jieba 预分词方案。
2. **双路召回**：BM25 路 + 向量路（先 ACL 过滤后距离计算；向量路含 `embed_model` 谓词——经 `chunk_vectors` JOIN，M0b 拍板②分表形态）。
3. **RRF 融合**：双路倒数排名融合；LLM 增强第三路以 800ms 并行增强窗口并入（超时降级为双路）。
4. **rerank**：候选 32；Reranker provider 按网关 Cohere 风格 `/rerank` 契约实现（G-7 已闭环——端点已确认，model/字段细节按实际响应核对）；**必带 `none` 实现 + 失败/超时降级链**（降级用 RRF 序）。
5. **分数归一**：多路融合后归一输出（与 M0a 的 BM25 单路 min-max 显示归一口径区分——M0a-3 交付注记已有声明）。
6. **PG 后端追平全矩阵（D24）**：全部检索配方在 SQLite / PostgreSQL 双后端等价可用；FTS 评分差异按「名次集等价」断言口径（A-17/G-6）；PG 向量路精确扫描起步（2560 维超 vector 索引 2000 上限，halfvec/表达式索引评估登记进 M1-4 的 TC-PERF，不在本段实作）。

**验收标准**（TEST-CASES §六 M1 行检索配方组，双后端参数化各跑）：

- TC-RET-01~07（RRF 融合 / 向量缺失退化 / 分数归一 / rerank 输入与候选 / 800ms 并行 / 双降级开关 / 参数红线）
- TC-EMB-04（查询侧降级链）、TC-EMB-05（Reranker none 实现）、TC-EMB-07（混模型向量零距离——`cv.embed_model` JOIN 口径）
- TC-ACL-08（rerank 前后 ACL 双断言——防御纵深）
- TC-FTS-04（keywords 列人工词纯净性）
- TC-E2E-01（摄取→检索全链全配方）、TC-E2E-04（按口径落 M1 集成）——检索侧断言
- 执行纪律：PG 臂经本地门禁 `scripts/test_gate.sh` 必跑（M0b 拍板：不建 GitHub Actions、项目将移公司内网），**skip≠pass**；SQLite 臂全量绿。

**口径与边界**：

- rerank 真实联调：网关可达时按实际响应核对字段并跑通；**网关不可达时按 `none` 档验收（TC-EMB-05 口径）**，Reranker API 真实联调留待环境可用时补验（登记遗留）。
- M0b 拍板口径已落 v1.1 schema：`chunk_vectors` PK(rid, embed_model) 分表、`visible_docs AS MATERIALIZED` 唯一路径、向量谓词迁 `cv` JOIN——本段不得回退。
- M0a 已有基础不得重做：BM25 单路、ACL 编译器、嵌入 provider 接口与指纹探针、multipart 上传链。
- 设计冻结纪律：docs/ 下需求与设计文档 coder 禁改；实现问题走测试用例与 issue；`docs/TEST-CASES.md` 为活文档、由 supervised-coding 回写口径。
- commit 纪律：`[task-knowledge-lattice-m1-1] R<n>` 格式，develop_opencode 分支本地 commit，commit 前同步 origin/develop。

**流程纪律（M1 系列新增，用户 2026-10-25 拍板）**：

- **跨检查点会话隔离**：每个检查点文件对应全新 Coder/Tester/Committer 会话（task_id 不得跨检查点复用）；同一检查点内多轮续接复用各自会话。
- **执行模式 A 串行紧衔接**：M1 四段严格串行（M1-1→M1-2→M1-3→M1-4），每段双通过收口后立即启动下一段，不并行。

**承接遗留事项**（本段"触及即顺手"清偿，处理完回写勾选并注来源）：

- [x] FTS5 trigram/自定义词表判据落地（来源 task-knowledge-lattice-m0a-1）——✅ R1 清偿（token_alignment/cjk_fallback_verdict 判据 + 6 用例双后端小型验证；黄金集全量校准留 M1-4，用例注释已注明）
- [x] P3-23 `search.degraded` 审计与 rank 协议（来源 task-knowledge-lattice-m0a-3 committer P3）——✅ R1 清偿（backend 名次协议 + notice.degraded + search.degraded outbox 审计，reason 同源一请求一条聚合）
- [x] P3-R2-1 test_e2e_01 注释指错文件修正（来源 task-knowledge-lattice-m0a-3 committer R2）——✅ R1 清偿（改指 test_r2_committer_fixes.py）
- [x] P3-R2-2 ticker 测试改时间断言或修正"实证"表述（来源 task-knowledge-lattice-m0a-3 committer R2）——✅ R1 清偿（相邻 tick 间隙时间断言，阈值 0.2s）

（其余 M1 批次遗留按分摊表归 M1-2 / M1-3 / M1-4，去向不变：版本/ACL 组→M1-2；凭证/中间件/401 清理组→M1-3；区分度/校准/池化/G-6/G-8 组与摄取补全 TC-ING-04~06→M1-4。）

## 需求确认

- [x] 用户已确认（2026-10-25：拆分方案 + 串行模式 + 会话隔离纪律三轮确认；确认后 status=implementing）
- 历史遗留事项清单：knowledge-lattice 6 检查点全 done 无未了结遗留；pulsepet 17 检查点经用户 2026-10-23 裁定豁免；21+ 条跨任务移交项已按子系统分摊到 M1-1~M1-4（用户 2026-10-25 确认分摊口径）

## 遗留事项（跨任务移交）

- [ ] **移交 M1-2 顺手（committer R2 P2-新，一行修）**：半开探测令牌泄漏——`embed_breaker_open = not _breaker_allows(...)` 提到了探针 gate 判断之前，「探针拒绝档 + 嵌入熔断半开」叠加时 `_probing` 置位后无 success/failure 回写、永不复位（向量路不自愈需重启 + 每请求误写 search.degraded）；修法=allow 调用移入「确实会发起调用」分支（或 _probing 加探测租约超时）；rerank 侧同形但 none 档不可达
- [ ] **移交下段顺手（P3-新-1）**：retrieve.py 分数收集循环在 try/except 之外（provider 异常型返回→500）——包回 try 走 rerank_skipped 保持防御边界
- [ ] **移交 M1-4/下段（P3-新-2）**：rerank「部分响应缺项」用例（部分 index 有效部分越界 → 断言缺项 -inf 垫底 + final_score==0.0）
- [ ] **移交 M1-4**：P3-11 PG to_tsquery 负向用例（畸形参数 + 语法错误降级评估）；P3-12 空 query 早返回口径（行为未改、待定口径后落）；P3-13 耗时日志四段对齐（embed 单段拆分——NFR-8 标定前）；Tester R1 观察项多 token 黄金集覆盖；halfvec/表达式索引评估（G-6②，随 TC-PERF）；TC-FTS-04 REST 面断言补验（**硬条件：不补则 TC-FTS-04 视为未完全验收**）；P3-新-2（若未提前清）
- [ ] **移交部署前（P3-14）**：config env 覆盖缺口（LATTICE_RERANK_TRUNCATE_TOKENS / LATTICE_RECALL_WINDOW / breaker_* / rerank·enhance base-key-model——部署态降级开关与配置切换）
- [ ] **移交（跨段，环境依赖）**：rerank 真实网关联调（公司内网网关不可达——R1 按 none 档验收 TC-EMB-05；CohereCompatReranker 已就位，环境可用时按实际响应核对 model/字段并补联调用例）
- [x] **交付 docs 回写批（P3-新-5）——✅ 2026-10-25T11:53 已落笔（supervised-coding 执笔，工作区未 commit）：①requirements.md 联动升 v0.9.2（正文无变更注记）；②TC-ACL-08 前置句改「注入召回面放宽」（v1.6.2 注记）+ TEST-CASES 依据区 requirements 引用同步 v0.9.2。待 coder 小 commit 纳入：**：①requirements.md 联动升 v0.9.2（design 已 v0.9.2，两文档版本统一纪律；正文无变更）；②TC-ACL-08「前置」句「mock ACL 编译器漏生成维度条件」改为「召回面放宽注入」消除与口径登记行的字面冲突
- [ ] **M1-4 NFR-8 标定时评估（Tester R2 观察 1）**：P2-2 信号量语义（约束「活跃请求」非「在飞调用」，超时窗口瞬时并发可超上限）——若需严格在飞上限改 `add_done_callback` release

## 已清偿（本轮）

- [x] FTS5 trigram/自定义词表判据落地（来源 m0a-1）——✅ R1（判据 + 小型验证；全量校准 M1-4）
- [x] P3-23 search.degraded 审计与 rank 协议（来源 m0a-3）——✅ R1
- [x] P3-R2-1 注释指错（来源 m0a-3）——✅ R1
- [x] P3-R2-2 ticker 时间断言（来源 m0a-3）——✅ R1（加强非弱化）
- [x] R1 Committer 全部问题项（P0-1/P1×2/P2×4/P3 顺手×9）——✅ R2 修复、Tester 注入实证、Committer 复审 APPROVED
- [x] B-1 需求边界（design §5.2「或 none」）——✅ 用户确认勘误 v0.9.2/v1.6.1 已 commit（2d45af9）
- [x] rerank none 档验收口径——✅ none 档双后端验证通过；真实联调留移交项

## 轮次记录

- R1: coder 完成（2026-10-25，**全新会话**，coderTaskId=ses_e8f6e3b22ffeFjqXFsYGV7uyp0，commit `3bba1bf3a1202ef198037c87c28891afb2474860` 于 develop_opencode，28 files +2660/−104，父提交=1d37713 同步 origin/develop 后）——①完整配方编排（retrieve.py 重写）：双路召回（sqlite `vec_distance_cosine` / PG `<=>` 均实装、`cv.embed_model` JOIN 谓词）+ RRF(k=60) + LLM 增强 800ms 并行窗口（第三路 BM25、超时/失败丢弃不标 degraded）+ rerank（Cohere /rerank 客户端 + none 档 + 失败/超时降级 RRF 序 + 信号量 4 + 截断 256 token/候选 32→16 双降级开关）+ min-max/clamp(IQR×1.5) 归一双分支 + ACL rerank 前后双断言（独立重编译可见集 + `search.acl_intercept` 审计）+ 名次协议（backend 吸收评分方向差异返回 rank——P3-23 清偿）+ 熔断器；②PG recall_fts 追平（五列 tsvector 加权 ts_rank 求和 + to_tsquery `&` 连接）；③新用例 76 条双后端参数化（TC-RET-01~07/TC-EMB-04/05/07/TC-ACL-08/TC-FTS-04/TC-E2E-01/04 检索侧/熔断）；④遗留 4 条全部清偿。**自测证据**：门禁 GATE PASS——342 passed + 1 deselected 双后端双模式（常规/-O）0 skipped，pg 臂 117 条全实跑，基线 271→342；关键用例逐条 PASSED（RRF 手算核对/归一 clamp 数值断言/增强 0.9s 超预算丢弃/混模型零距离/ACL-08 双面失败面）。**supervised-coding 机械核验**：HEAD=3bba1bf ✓ 格式 `[task-knowledge-lattice-m1-1] R1` ✓ docs/prototype 零 diff ✓ origin/develop 已同步（祖先）✓ 未 push ✓；残留清理——会话中途落错路径的 retrieve.py 中间副本（仓库根 `knowledge_lattice/`，409 行未跟踪）已删除。**口径申报 11 条**（clamp IQR 系数 1.5 待 M1-4 校准 / 增强路权重 1.0 / `search.acl_intercept` 事件名自定 / rerank 信号量默认 4 / rerank 响应缺项防御（越界丢弃+缺失 0 分垫底）/ 增强超时不标 degraded / none 档不标降级（配置态非故障）/ vector_pending 判定=结果块无 (rid,当前标签) cv 行或向量路关且有 BM25 结果 / **TC-ACL-08 注入口径=独立重编译可见集而非 mock compile_acl**（理由：编译器是 ACL 语义唯一实现处 §5.1，文件头已申报待裁定）/ _MODEL_POOL 进程级 8 线程 / TC-FTS-04 按人工词写入 keywords 同源语义造数）；**移交登记**：rerank 真实网关联调（内网不可达→none 档已验收）+ halfvec 评估→M1-4 + TC-FTS-04 REST 面断言→M1-4
- R1: tester **PASS**（2026-10-25，全新会话，testerTaskId=ses_e8f313ea4ffe5rm7Th5L9qYxC5，testedSha=3bba1bf 复核一致）——门禁独立复跑：342 passed + 1 deselected 双模式 0 skipped（与 coder 声称一致），pg 臂 117 全实跑（lattice-pg 容器 PG 16.15 + pgvector 0.8.x，schema 残留 0）；1 deselected=TC-UI manual 标记口径内；不带 DSN 时 pg 臂 31 skip 证实门禁有效性。验收用例 14 号族单独复跑 71 条全绿双后端，断言强度逐条评语（12 强 / 2 中强 / 1 中——TC-RET-06 一处恒真倾向弱断言 `len(docs_got[0])>0` 主断言已覆盖）。三条口径裁定：**①TC-ACL-08 独立重编译口径 ACCEPT**（防线数据源与召回 SQL 两条路径、非自我循环、mock 形态反而有逻辑坑；编译器自身漏条件风险由矩阵覆盖备案）；**②TC-FTS-04 造数载体 ACCEPT 附硬条件**（M1-4 REST 面补验不可缺，不补则视为未完全验收）；**③none 档/增强超时不标 degraded ACCEPT 附文档勘误建议**（design §5.2「或 none」措辞与实现张力——建议 committer 开 issue 登记活文档勘误，非决策变更）。回归面：4 个被改存量文件零弱化零删除（e2e_01 增强 / pg_backend 合理翻转 / v11_schema 适配 / r2_committer_fixes 加强）；top_k=100→20 强断言在场。观察项 7 条登记（多 token 双后端匹配语义差异——M1-4 黄金集必须覆盖多 token 场景 / 800ms 默认值无锁定断言低风险 / probe_reject or 形态断言可接受等）。PG 测试残留 0，测试卫生合规
- R1: committer **NEEDS_CHANGES**（2026-10-25，全新会话，committerTaskId=ses_e8f1b5210ffemAf2R47vW6wdlX，reviewedSha=3bba1bf 静态全量 diff 审查）——**P0×1**：PG FTS 召回 SQL 缺 `c.version = d.active_version`（render_fts_recall_select JOIN 无版本条件，两后端不等价、pending 块可混入 BM25 路、ACL 拦截审计系统性误报——SQLite 臂带该条件，PG 新写路径漏；无任何用例在 PG 上跑 recall_fts 层断言，兜底断言掩盖缺陷）；**P1×2**：①vector_pending 未覆盖「降级」面（嵌入运行时失败时误报 false，违反 §6.1「未就绪或降级」）；②熔断开路期降级不标注不审计（违反 §5.2「任何降级统一发 search.degraded」——注意与 B-1 的 none 配置态不同）；**P2×4**：截断 "".join 吞空白改写英文原文 / 模型池排队时间计入单次调用超时且共享池致误降级误熔断 / ACL 双断言每请求两次全量可见集扫描（10 万块宽权限 O(N)×2）/ 分词判据把「部分对齐」误判「召回为空」（SQLite OR 语义下不成立——遗留①判据需修）；**P3×15**（含：用例计数申报 76 实为 71〔与门禁 +71、tester 复跑 71 三向吻合〕/ 空响应当成功 / 缺项 0 分垫底遇负分失效 / breaker 时钟注入失效+半开不限次 / 6 处失效注释 / e2e_04 空转测试 / RET-06 恒真断言建议本轮顺手改 / PG to_tsquery 无负向用例 / 空 query 行为变化未定口径 / env 覆盖缺失等）；**11 条口径申报复核**：8 合规、2 部分合规（→P2-2/P3）、1 不合规（申报 8→P1-1）、1 需求边界（申报 7→B-1）；**B-1 需求边界问题（非代码，不发给 coder）**：design §5.2 line 728/733「或 none」字面把 none 列入降级，实现+用例取「none=配置态不标注」（tester/committer 双 ACCEPT 实现侧，§6.1 枚举自洽）——需用户确认后由 supervised-coding 勘误 design 正文 + TEST-CASES TC-EMB-05 补句 + TC-ACL-08 事件名登记（committer 已给 issue 草案）；Tester 理由⑤修正：routes 字段是召回路数不含 rerank 阶段，不可作 none 可观测依据。**核验通过项**：数值口径逐项对齐 / 流程编排顺序逐节点一致 / ACL 纪律唯一违约=版本条件(P0-1) / 名次协议 / 降级链主体 / 遗留 4 条清偿质量（遗留①判据见 P2-4）/ 零新增 skip / 未 push / docs 零 diff。**执行环境限制**：committer bash 白名单只读 git，未独立复跑门禁（采信 tester 复跑值 + 收集计数三向交叉验证）。**处置**：B-1 → spec_confirm 找用户；P0/P1/P2+顺手 P3 → round+1 发回 coder（复用会话）
- R2: spec_confirm 处置（2026-10-25）——B-1 经用户确认「同意」按实现侧口径勘误；supervised-coding 已落笔 7 处（**coder 禁改区，由 supervised-coding 执笔**）：①design.md 版本段升 v0.9.2（勘误注记：非决策变更、D1~D24 不动）；②design §5.2 line 728「不可达→跳过重排用 RRF 序并记审计；none 实现→跳过重排（配置态，不标降级——v0.9.2 勘误）」；③design §5.2 line 733 降级枚举移出「或 none」+ none 可观测口径注记（routes 字段不可作依据）；④TEST-CASES 版本段升 v1.6.1（两条勘误注记）；⑤TC-EMB-05 预期补「none 为配置态、`notice.degraded==[]`、不发 `search.degraded` 审计」；⑥TC-ACL-08 补口径登记行（search.acl_intercept 事件名 + payload phase ∈ {pre_rerank,pre_return} + 独立重编译断言口径）；⑦TEST-CASES 依据区 design 版本引用刷新 v0.9→v0.9.2。**git diff 校验：design.md 6 行、TEST-CASES.md 6 行，均为勘误内容**。R2 修复范围下达 coder（复用会话 ses_e8f6e3b22ffeFjqXFsYGV7uyp0）：**P0-1 必修 + P1-1/P1-2 必修 + P2-1/2/3/4 应修 + 顺手 P3-2/3/4/5/6/7/8/9/10（committer 建议 P3-1/6/7/8 随批清，P3-8 经 tester/committer 双建议升为本轮必修）；P3-11/12/13/14/15 登记顺延（P3-12 空 query 口径、P3-13 耗时四段、P3-14 env 口→M1-4/部署前；P3-11 PG to_tsquery 负向→M1-4；P3-15 三次编译——先注释说明）**；同时 commit 需把 docs 勘误（本轮 supervised-coding 落笔的 design/TEST-CASES 改动）一并纳入或 coder 单独告知——由 coder 决定合并进 R2 commit 或分离 docs commit，commit 格式不变
- R2: coder 完成（2026-10-25，**续接会话**，coderTaskId 同 R1，**两个 commit**：`2d45af9`（docs 勘误批原样纳入 +7/−6，零改动）+ `f741f31`（代码修复批 18 files +533/−132，HEAD），父提交=1d37713 无需同步、未 push、工作区干净）——①**P0-1 已修**：PG render_fts_recall_select JOIN 补 `c.version=d.active_version`（pg:225 与 sqlite 逐字同构）+ 双后端召回层断言（test_acl_07 recall_fts 直断言 pending/tombstone 不进 BM25 路 + test_acl_06 版本条件渲染断言扩双方言 + 三路同构 FTS 段扩双方言）+ **红灯自证闭环**（临时 revert 注入缺陷 → 两断言必红 → 恢复全绿——断言能真正拦截缺陷）；②**P1-1 已修**：vec_closed 并入本次嵌入失败面 + 用例（块已有当前标签向量+嵌入失败→vector_pending=True）；③**P1-2 已修**：熔断开路 embed/rerank 双面补 degraded 标注 + search.degraded 审计（集成用例：3 失败开熔断→provider 零调用+枚举+outbox）；**none 配置态优先**（rerank 熔断标注带 `reranker != "none"` 前置——Tester ACCEPT 口径不破坏，择型申报 3）；④**P2×4 已修**：截断空格 join 保英文词边界（混排用例）/ rerank 分池 `_RERANK_POOL` + 调用线程信号量（池内不排队、超时≈实际调用，择型申报 1）/ visible_chunk_ids 可选 rids 收窄（双断言传候选/top-k 集、独立 SQL 路径不变，双面失败面复跑绿）/ 判据零交集定 zero-recall + partial 档 + 双后端 OR/& 对照实证；⑤**P3×9 顺手清**：P3-2 rank 显式排序 / P3-3 空响应当失败 / P3-4 -inf 排序键+缺项归一 0.0（择型申报 2）/ P3-5 state(now) 注入+半开单次探测+Lock / P3-6 六处注释清理 / P3-7 compile_now 真断言（NOW/FUTURE 双锚点）/ **P3-8 恒真断言改真断言（分数降序+∈[0,1]+rank 连续）** / P3-9 docstring 修正+越界 index（含负）降级用例 / P3-10 阈值 0.6；⑥P3-11/12/13/14 顺延登记、P3-15 注释已加（复用未做）。**自测证据**：门禁 GATE PASS **355 passed + 1 deselected 双后端双模式 0 skipped**（R1 基线 342→355 =+13 对账自洽：6 新用例函数×双后端 + test_acl_06 臂迁移；pg 臂 124 条全实跑）；26+5 关键用例 -v 全 PASSED。**supervised-coding 机械核验**：HEAD=f741f31 ✓ 双 commit 结构（2d45af9 docs 纯勘误 + f741f31 零 docs 改动）✓ origin 同步 ✓ 未 push ✓ 工作区干净（仅流程文件）✓ docs 内容与 supervised-coding 落笔一致（工作区=HEAD 且关键句 grep 在位）
- R2: tester **PASS**（2026-10-25，续接会话，testedSha=f741f31 复核一致）——门禁独立复跑：355 passed + 1 deselected 双模式 0 skipped（与 coder 一致）、pg 臂 124 全实跑、基线对账 +13 自洽。**复验重点 8 项全过**：①P0-1 拦截力——本机缺陷注入实证（备份→sed 移除 JOIN 版本条件→两断言必红〔召回层直断言 pending v2 混入 + 渲染层 JOIN 文本缺失〕→恢复→git status 零输出→全绿 21 passed；sqlite 臂 19 条不受影响=缺陷精确定位 PG 路径）；R1 教训（兜底断言掩盖召回层缺陷）已制度化封堵；②P1-1 造数精准（两块先写满当前标签向量再注入嵌入失败——排除 R1 掩盖点）双后端绿；③P1-2 双面集成三断言齐全（零调用+枚举+outbox）+ none 配置态未破坏（`!= "none"` 前置 + TC-EMB-05 复跑绿）；④P2-3 收窄后 SQL 仍走 render_select 基础路（绑定参数占位符）+ TC-ACL-08 四测含 monkeypatch 双面自证 [pg] 全绿；⑤P2-1/2/4 断言强度达标（混排无黏连 / 分池后峰值 ==2 复跑绿 / partial 档 0.5 精确断言+双后端 OR/& 对照锁进同一用例）；⑥docs 勘误批与代码逐项 grep 吻合（事件名/payload/口径登记，含 Committer 对 Tester R1 裁定理由⑤修正的吸收）；⑦回归零弱化（dbwrap PG 侧 NotImplementedError→双方言属 P0-1 必要翻转 / test_acl_06 sqlite-only→matrix 双后端=正中 R1 测试缺口本体）；⑧R1 观察项清偿核对（P3-8/P3-10/P3-7/P3-9 全清）。新增观察项 3 条不阻塞（P2-2 信号量语义微松动——约束「活跃请求」非「在飞调用」，M1-4 标定时可再收紧 / test_acl_08 调用序假设可维护性 / test_ret_04 阈值与串行下限相切）。PG 测试残留 0，工作区干净
- R2: committer **APPROVED**（2026-10-25，续接会话，reviewedSha=f741f31 复核一致；区间 3bba1bf..f741f31）——**R1 问题清单全闭环**：P0-1 已修（强）：JOIN 与 sqlite 逐字同构 + 召回层断言直调 backend.recall_fts（先自证造数前提）+ 渲染层查实装路径 render_fts_recall_select + Tester 注入实证（红→恢复→绿）+ committer 复核断言逻辑非形式主义；P1-1 已修（vec_closed 两面俱全、逐路径核过）；P1-2 已修（`!= "none"` 前置与 B-1 勘误自洽、TC-EMB-05 复跑绿）；P2×4 已修（P2-2 择型 ACCEPT 附登记；P2-1 判别力集中于英文独立词形断言够用；P2-3 独立 SQL 路径性质不变；P2-4 双后端对照锁进同一用例）；P3 顺手 9 条全清（P3-1 +13 三向对账自洽 / P3-10 判别力核过 / P3-15 注释与 docs 口径一致）。**docs 勘误批逐处核对零走样零超范围**（7 处与草案一致；§6.1 枚举未动正确；known-gaps 未动符合草案；与代码 grep 逐项吻合）。**断言零弱化净加强**（移除断言逐条核为上移加强/方言分支/必要放宽；零新增 skip、零测试删除；4 存量文件均为必要翻转；改动半径小：api/mcp/app/config/ingest/迁移零改动；未声明行为变更=无）。**择型 3 条全 ACCEPT**（分池形态附登记——超调 ≤1 timeout+连续 3 超时熔断+不可兼得取舍；缺项 0.0 排序语义干净；none 优先=精确区分配置态 vs 故障态）。**新增不阻塞项**：P2-新 半开探测令牌泄漏窄窗口（探针拒绝+熔断半开叠加时 _probing 永不清零→向量路不自愈需重启——R1 后 P3-5 引入的边缘回归，一行修法已给，建议 M1-2 顺手）；P3-新-1 分数收集循环移出 try（provider 异常型返回会 500，真实适配器已校验风险低→下段顺手包回 try）；P3-新-2 部分缺项用例缺失→M1-4/下段；P3-新-3 visible_chunk_ids docstring「rids 非空时」措辞；P3-新-4 检查点遗留事项结构化补全（本轮已做）；P3-新-5 requirements 未随 design 升 v0.9.2 + TC-ACL-08 前置句「mock 编译器」与口径登记行字面冲突（→交付 docs 回写批）；P3-新-6 阈值相切维持现状。**执行环境限制同 R1**（bash 只读 git 白名单，未独立复跑门禁——采信 Tester 复跑 + 收集计数三向对账 + 断言可达性静态验证）。**放行：approved，可交用户**
- **合入完成（2026-10-25 13:02 用户指令"合入"）**：PR #50 state=MERGED，mergedAt=2026-10-25T05:02:09Z，mergeCommit=`fc1bcc839d36a4ae6ecf459ad933f041872f2a03`；origin/develop 前进 `1d37713..fc1bcc8`（merge commit 保留 R1+R2+docs 两批完整历史）；develop_opencode 远端分支按 D30 约定保留——**M1-1 正式完成（done），M1-1 里程碑达成**（完整检索配方 + PG 追平全矩阵 + 版本/凭证前置基础；验收对照 TEST-CASES §六 M1 行检索配方组全绿；遗留移交四组去向不变）。下一步 M1-2（版本在用制全链 + 维度 ACL 写链）：新检查点 + 全新 Coder/Tester/Committer 会话（跨检查点会话隔离纪律），开工前承接 P2-新（半开探测令牌一行修）等 M1-2 顺手组遗留
- 交付完成（2026-10-25）：①Coder 同步 origin/develop（Already up to date）+ push develop_opencode `10d8d72..9565193`（SSH）；②PR #50 开立（base=develop，MERGEABLE/CLEAN，4 commits 齐全，35 files +3113/−155 无流程文件混入），description 含 evidence manifest（testedSha=f741f31 代码级 / reviewedSha=9565193 交付批 doc-only 值 / GATE PASS 355+1 双后端双模式 0 skipped / pg 臂 124 全实跑 / 双验收 verdict / 移交四组）；③Committer 正式评审留痕 review id `PRR_kwDOTsiHgs8AAAABUEKbsw`（2026-10-25T04:32:35Z）——**GitHub 平台限制"不能 approve 自己的 PR"（单账号 yq3 自审，reviewDecision 结构性为空），降级 COMMENTED 留痕、正文首行标注「评审结论=APPROVED（可交用户合入）」**——与 M0b 系列留痕形态一致，登记为本项目留痕标准；manifest SHA 口径与检查点一致（frontmatter reviewedSha 已更新为 9565193=最终交付 HEAD）。**待用户合入 PR #50；合入即 M1-1 里程碑达成，下一段 M1-2 新检查点新会话（跨检查点会话隔离纪律）**
- 交付批 doc-only 复核（2026-10-25，续接会话）：commit `9565193`（docs 回写批：requirements v0.9.2 联动 + TEST-CASES v1.6.2 前置句措辞 + 依据区引用）——**放行**（4 处零超范围/版本链无断档/与 f741f31 注入形态一致/B-1 勘误不冲突；代码零变更、APPROVED 顺延有效）；manifest 口径建议：testedSha=f741f31（Tester 复验值）+ reviewedSha=9565193（交付批 doc-only 复审值）+ 代码差异为空说明；非阻塞 cosmetic 3 条（N-1 requirements 日期链止 v0.9.1 / N-2 design 前置阅读仍写需求 v0.9 / N-3 版本行加粗样式——下次回写批顺手）

## 最新验证意见原文

- R1 Tester 报告（2026-10-25，逐字原文）：

# M1-1 段 C（R1）独立验证报告

**testedSha**：`3bba1bf3a1202ef198037c87c28891afb2474860`（`[task-knowledge-lattice-m1-1] R1`，develop_opencode）= 检查点申报值 ✓；commit 格式 ✓；`knowledge-lattice/` 工作区干净（仅流程文件属检查点本身）✓

## 1. testVerdict: **PASS**

## 2. 门禁独立复跑（本机实际计数）

| 项 | 我的复跑结果 | Coder 声称 | 一致 |
|---|---|---|---|
| 常规模式 | **342 passed, 1 deselected, 0 skipped**（22.3s） | 342 passed + 1 deselected | ✓ |
| `python -O` 模式 | **342 passed, 1 deselected, 0 skipped**（19.4s） | 同上双模式 | ✓ |
| pg 臂 | **117 条全实跑**（[pg] 参数化 85 + PG 专用 32，`>0` ✓） | 117 | ✓ |
| GATE | **GATE PASS** | GATE PASS | ✓ |

- 1 deselected = `test_ui_01_manual_walkthrough`（manual 标记，TC-UI 口径不进门禁）——口径内，非 skip。
- PG 环境：`lattice-pg` 容器 PG 16.15 + pgvector 0.8.x，DSN `postgresql://postgres:lattice@localhost:5432/lattice`，测试残留 schema = 0（每用例独立 schema 用后 DROP CASCADE，测试卫生良好）。
- 验收用例族单独复跑（带 DSN）：**71 条全绿、0 skipped**；不带 DSN 时 pg 臂 31 条被 skip——证实门禁「skip≠pass」拦的是真实风险，门禁口径有效。

## 3. 验收用例逐条核验表（双后端 × 断言强度）

| 用例 | [sqlite] | [pg] | 断言强度评语 |
|---|---|---|---|
| TC-RET-01 RRF | ✅ | ✅ | **强**。四块已知名次造数（五列权重钉死 BM25 名次 + 手工距离序向量），精确期望序 `Y>X>Z`… 手算断言（含 1/62+1/61 数值容差）+ 单路 Z 自然保留 + rank 协议 1 起连续 + 归一分值域；另有 `rrf_fuse` 纯函数单测含并列 tie-break。**双后端同序 = 名次集等价（A-17）的最强实证** |
| TC-RET-02 向量缺失 | ✅ | ✅ | **强**。vector_pending true/false 双态 + `degraded==[]`（块未就绪≠服务降级的语义区分）+ 无空结果误判 |
| TC-RET-03 归一 | ✅ | ✅ | **强**。分支名显式断言（minmax/clamp）+ 保序数值精确断言（0.625）+ clamp 主体区分度 >0.1 + 阈值只作用归一后分（0.0 块被 0.55 阈值滤除） |
| TC-RET-04 rerank 输入 | ✅ | ✅ | **强**。原文形态负向断言（分词形态「空格连接」不得入输入）+ 候选恰 32 + **并发峰值 `==2` 精确断言**（信号量过松=4、过紧=1 都会红）+ 4 请求总耗时 <0.5s（阻塞即退化为串行 0.6s+）+ REST 层全 200。信号量测试 sqlite-only 可接受（逻辑在 retrieve 层、与后端无关） |
| TC-RET-05 增强 800ms | ✅ | ✅ | **强**。预算内第三路 BM25 入融合（增强词命中块出现在结果）+ 超时丢弃（结果不变 + 总延迟 <0.45s 并行实证）+ 失败丢弃；config 默认 `enhance_budget_s=0.8` 已核对在场 |
| TC-RET-06 双降级开关 | ✅ | ✅ | **中强**。候选 16 + 截断 ≤256 token（jieba 边界，造数前提先自断言 >256）+ 长文在场 + 结果仍正确；一处弱断言 `len(docs_got[0])>0`（恒真倾向，主断言已覆盖，见观察项） |
| TC-RET-07 参数红线 | ✅ | ✅ | **强**。5 种噪音参数（rrf_k/weights/threshold/candidates/bm25_args）与 plain 请求结果**逐字节相等**；① top_k=100→恰 20 由存量 `test_p3_15_top_k_hard_limit_with_enough_hits`（25 块实断言）承载、未被削弱；③ datasets/doc_filter 收窄在 TC-E2E-01 断言 |
| TC-EMB-04 降级链 | ✅ | ✅ | **强**。embed 不可达/rerank 不可达/双降级/probe_reject 四测；**直接查 `audit_outbox` 表内容**（非 mock），`search.degraded` 事件 payload 含 reason、双降级聚合单条；probe_reject 断言查询嵌入零发起（跨底模距离无意义） |
| TC-EMB-05 none 档 | ✅ | ✅ | **强**。**provider 零调用**（误传 FakeReranker 实例也不得被调用——比「不传」更严）+ `degraded==[]` + 归一退化不崩溃顶格 1.0 + none 与显式 NoopReranker 序一致 |
| TC-EMB-07 混模型 | ✅ | ✅ | **强**。造数设计刁钻且正确：旧标签向量与查询**同向（dist=0）**——若 `cv.embed_model` JOIN 谓词失效，旧标签块必以第一名进向量路、测试必红。三面断言：recall_vec 层集合 + 集成 search 层 + 渲染层 SQL 谓词文本（双方言参数形态） |
| TC-ACL-08 双断言 | ✅ | ✅ | **强**。见口径裁定 1。双注入面 + **双面失败面在测试内机械化自证**（`test_acl_08_defense_in_depth_each_guard_independent`：monkeypatch 掉前断言→断言越权块直达 rerank 输入；掉后断言→断言前断言独立剔除）+ 零剔除正常路径无审计 + `pre_rerank`/`pre_return` 审计相位断言 |
| TC-FTS-04 keywords 纯净 | ✅ | ✅ | **中**（载体替代，见口径裁定 2）。列间零渗透 + jieba 产物零交集 + ×5 加权名次断言（keywords 命中 rank1 > content_seg 命中 rank2，双后端一致）有实证力；纯净性断言有「造数即断言对象」的自证成分 |
| TC-E2E-01 全链全配方 | ✅ | ✅ | **强**。7 项溯源字段逐一在场 + dims 值/source 精确断言 + datasets 收窄/doc_filter 下推 + 全配方无降级；摄取侧（multipart→轮询→两时点）由存量 `test_e2e_01_chain` 承载且该文件本轮已加 M1 全配方断言（degraded/vector_pending） |
| TC-E2E-04 权限即时生效 | ✅ | ✅ | **强**。撤授权/收紧文档维度/成员过期三形态均「下一次查询」级断言 + **负向断言**（其余授权不受影响、多值其余取值不受影响）+ dims 聚合回填反映收紧后真源（v1.6 口径）+ 时间全造数不推进系统时钟 |

**skip 核对**：全量门禁 0 skipped；无任何用例以 skip 交付 ✓。

## 4. 三条口径申报裁定

### 裁定 1：TC-ACL-08 注入口径（独立重编译可见集，非 mock compile_acl）—— **ACCEPT**

理由：①防御纵深本意保住了——防线数据源 = 独立重编译 `guard_plan` + `visible_chunk_ids` 独立查询，与召回 SQL 是两条不同执行路径，测试①③实证召回面放宽混入的越权块在 rerank 外发前被独立可见集拦下，正是 FR-4「rerank 前断言、返回前再断言」的验收语义；②不构成自我循环——被验证对象是 retrieve 的两道防线（含其独立数据源），编译器纯逻辑由 T1~T22 矩阵独立背书，「ACL 语义唯一实现处」（§5.1）是冻结设计纪律，为测试再造第二套编译器才是反模式；③原文 mock 形态反而有逻辑坑——mock 编译器后断言层的「可见块集合真值」从何而来？若断言层也用 mock 产物，越权块会被认定为「可见」，双断言形同虚设。wrap 召回结果 + 真编译器作真值源是语义上更严谨的等价形态。残留缺口（Coder 已申报、可接受）：编译器自身漏条件时防线两面同错拦不住——由编译器矩阵覆盖，设计接受的纪律代价，随 round 记录备案。

### 裁定 2：TC-FTS-04 造数载体（人工词直写 keywords 列，PATCH 端点 M1-4 补）—— **ACCEPT（附硬条件）**

理由：端点属 M1-4 是客观约束；替代保住两个有验证力的面——①列间零渗透（jieba 产物与 keywords/llm_keywords 零交集）+ 实现侧依据已核（摄取管线确实只写 seg 列，keywords 仅解析源透传）；②×5 加权名次放大实证（keywords 命中 rank1 > content 命中 rank2，双后端一致）。损失的是「PATCH 写入路径不污染 keywords」的服务端行为断言。**硬条件**：M1-4 REST 面补验不可缺（检查点已登记移交），届时若不补，TC-FTS-04 应视为未完全验收。

### 裁定 3：none 档不标 degraded / 增强超时不标 degraded —— **ACCEPT（附一项文档勘误建议）**

理由：①与验收用例自洽（TC-EMB-05/TC-RET-05 断言 degraded==[]，实现与断言一致）；②§6.1 契约 degraded 枚举仅三项，none 无对应枚举，硬标只会破坏契约；③none 是显式运维配置态，每次搜索都发 search.degraded 审计会造成告警疲劳；④增强超时丢弃是 §5.2 明文设计行为，非故障；⑤「无 rerank」可观测性已由 timing 日志 routes 字段承载。**附**：design §5.2 降级可观测句原文「任何降级（嵌入不可达 / rerank 不可达**或 none** / 探针拒绝档）」字面把 none 列入降级——实现与该句措辞有张力。属活文档勘误级（「或 none」改注「none 为配置态不标注」），建议 committer 开 issue 登记，非决策变更、不阻塞本段。

## 5. 回归面抽查结论：**零弱化、零删除**

基线 271→342（+71 净增）自洽。4 个被改存量文件逐一核对：test_e2e_01_chain.py **增强**（+M1 全配方断言 + P3-R2-1 清偿）✓；test_pg_backend.py **合理翻转**（NotImplementedError 断言→方法在场断言，被删断言行为面由 pg 臂 117 条实跑覆盖）✓；test_v11_schema.py **适配**（dist 列位 3→10，数值断言语义不变）✓；test_r2_committer_fixes.py **加强**（ticker 恒真计数→时间断言 + P3-R2-2 清偿）✓。`top_k=100→20` 硬上限存量强断言在场未动 ✓。

## 6. 其他观察项（不阻塞，登记备案）

1. TC-RET-06 一处弱断言 `len(docs_got[0]) > 0`（恒真倾向）——主断言已覆盖；下轮顺手收紧。
2. probe_reject 零调用断言为 or 形态——为容 fixture 噪音，稍宽；可接受。
3. 800ms 默认值无锁定断言——机制已验证 + config 默认在场；低风险。
4. 多 token 查询双后端匹配语义差异（SQLite OR / PG &）——design §5.2 已钉死为已登记差异、本轮造数均为单 token 规避；**M1-4 黄金集校准必须覆盖多 token 场景**，否则该差异面无数据。
5. `_MODEL_POOL` 进程级 8 线程——并发语义真实。
6. 测试卫生：PG 每用例独立 schema 无残留（实测 0）；fake provider 合规；时间依赖全造数。
7. rerank 真实网关联调与 halfvec 评估移交项已在检查点登记，去向明确。

**结论**：R1 交付通过独立验证。门禁双后端双模式全绿 0 skipped、14 个验收用例号双后端全数实跑通过且断言强度核验无恒真/无弱化、三条口径裁定全部 ACCEPT（一条附文档勘误建议、一条附 M1-4 补验硬条件）、回归面零弱化。testVerdict: PASS / testedSha: 3bba1bf

- R1 Committer 报告（2026-10-25，逐字原文）：

## 审查结论

**reviewVerdict: NEEDS_CHANGES**

- 审查基线：`1d37713..3bba1bf`（28 files，+2660/−104）；`git rev-parse origin/develop == 1d37713`（父提交即远端，**未 push** ✓）；`knowledge-lattice/docs`、`prototype` 零 diff ✓。
- 拦截主因：**PG FTS 召回 SQL 缺 `c.version = d.active_version`（P0）**——「只召回在用版本」是 design §5.1 的 P0-A 红线，SQLite 渲染器在 JOIN 上带该条件，PG 新写路径没有；两后端在这一面不等价，M1.1「PG 追平全矩阵」的核心主张不成立。
- 另有 2 条 P1（`vector_pending` 缺「降级」面、熔断开路期降级不标注不审计）均为 design §6.1/§5.2 明文契约违背，且测试恰好掩盖了二者。

> 说明：本轮执行环境的 bash 被限定为只读 git 白名单，`pytest`/`docker` 调用被拒绝，**未能独立复跑门禁**；结论基于全量 diff 静态审查 + 计数交叉核对（§7）。P0 为 SQL 文本级缺陷，静态审查即可判定，不依赖复跑。

## 1. 问题清单

### P0（阻塞，必须本轮修）

**[P0-1] PG FTS 召回缺在用版本条件——两后端不等价、可致召回面混入 pending/失败版本块**
- 位置：`store/postgres/acl_render.py:222`（`render_fts_recall_select`）：`JOIN documents d ON d.id = c.doc_id` **没有** `AND c.version = d.active_version`；对照 SQLite `store/sqlite/acl_render.py:213` 是带的；`store/acl_ast.py:285-295` 按契约把版本条件**故意不放进 WHERE**（「版本条件在 JOIN 上——T9 机制前提」），PG 的 WHERE 里也没有（`tombstone_eq + org_eq + filters`）——即 PG 的 FTS 路**版本条件整体缺失**。
- 违反：design §5.1 line 693/695-696（只召回在用版本 P0-A/P0-2、版本条件必须在 FTS 路 JOIN 上）；TC-VER-02「lexical 时点不切换，检索仍只见 v1」。
- 实际后果：①覆盖上传窗口内 pending v2 块会进 PG BM25 路，**只有 `_drop_invisible_pre_rerank` 兜底才被剔除**——红线全押第二道（防御纵深变单保险）；②每命中一个 pending 块写一条 `search.acl_intercept`（pre_rerank）审计——**ACL 拦截审计系统性误报**；③pending 块挤占 recall_window 名额抬高 RRF 名次，大文档摄取窗口内可把在用版本结果挤出召回窗口甚至空结果（向量路不可用时必现）。
- 测试缺口：`test_acl_07_visible_docs.py:62 test_version_pair_scenario` 已构造 pending 块但只跑 `render_select` 基础路，**无用例在 PG 上跑 recall_fts**；`test_acl_06_constants_routes.py:79 test_fts_route_version_condition_on_join` 是 sqlite-only，docstring 写「PG FTS 路随 M1」却未随 M1 补齐。
- 修法：①JOIN 补 `AND c.version = d.active_version`（与 sqlite 逐字同构）；②补用例（双后端）：recall_fts 层断言 pending v2/失败版本块不出现（扩 test_acl_07 的 version_pair_scenario + test_three_routes_share_same_plan 的 FTS 段扩双方言）；③**只断言最终 search() 结果不够**——兜底断言会掩盖该缺陷（本轮 pg 臂 117 全绿仍漏掉它的原因）；M1-2 的 TC-VER-02 需在召回层补断言。

### P1（必须修）

**[P1-1] `notice.vector_pending` 未覆盖「降级」面——嵌入运行时失败时误报 false**
- 位置：`core/docs/retrieve.py:249-259`（`vec_skipped` 在嵌入调用**之前**算定）、`:365-369`（`vector_pending = missing or (vec_closed and has_results)`）。embedder 非空、探针放行、熔断放行 → `vec_skipped=False`；随后 `_embed_query` 失败 → `degraded=["embed_unreachable"]`、`vec_rows=[]`，但 `vec_closed` 仍 False → 若结果块都已嵌入（最常见网关宕机场景），`vector_pending=false`。
- 违反：design §6.1 line 1061「vector_pending＝本结果缺向量路（**未就绪或降级**）」；`store/backend.py:95-100` 自己的 docstring 落空。
- 测试恰好掩盖：`test_emb_04_05_07.py:67` 造数是「两块都没向量」（`missing` 命中通过）——**不是**在测「降级」面。
- 修法：`vec_closed = vec_skipped or (embedder is not None and query_vec is None)`；补用例：块已有当前标签向量 + `FakeEmbedder(fail=True)` → `vector_pending is True`。

**[P1-2] 熔断开路期间的降级不标注、不审计——「任何降级统一发 search.degraded」落空**
- 位置：`core/docs/retrieve.py:246-253`（embed 分支）、`:309-316`（rerank 分支）：`_breaker_allows(...)` False 时直接跳路，**没有** `degraded.append(...)`、无审计。embed 熔断开 → 向量路关、`vector_pending=True` 但 `notice.degraded==[]`；rerank 熔断开 → 静默跳过。
- 违反：design §5.2 line 733；NFR-8「熔断＝连续 3 次失败即断开 60s（期间直接降级不等超时）」——熔断开路是「已确认不可达」的降级态，不是 none 配置态（Tester 裁定 3 只覆盖 none，不覆盖本条）。
- 测试缺口：`test_emb_04_05_07.py:225-251` 只有熔断器单体单测，无「熔断开路 + search()」集成用例。
- 修法：两处补 reason（embed→`embed_unreachable`、rerank→`rerank_skipped`）；补集成用例（制造 3 次失败开熔断 → 断言 degraded 含对应枚举 + outbox 有事件 + provider 零调用）。

### P2（应修）

**[P2-1] `_truncate_content` 用 `"".join` 拼接 token——空白被吞，英文/中英混排原文被改写**
- 位置：`core/docs/retrieve.py:476-485`；根因 `adapters/tokenizer.py:30`（`segment` 过滤空白 token）。`hello world` → `helloworld`、`VAT 申报` → `VAT申报`——rerank 输入截断（NFR-8 明列降级开关）喂给跨编码器的原文被破坏；docstring「保留原文字面」不成立。测试缺口：`test_ret_01_recipe.py:483-516` 只用纯中文长文。
- 修法：`" ".join(tokens[:limit])`（中文多空格对 cross-encoder 无影响、英文安全），或按 jieba 原始 offset 截字符区间。

**[P2-2] 模型池排队时间计入「单次调用超时」，且共享 8 线程池 → 目标并发下误降级/误开熔断**
- 位置：`core/docs/retrieve.py:452-460`（信号量在池内 `_call` acquire、`future.result(timeout)` 从**提交**开始计时）、`:422-424`（embed 同理）、`:49`（共享池）。机理：NFR-8 目标 N=5 > `rerank_max_concurrency=4` → 1 个 rerank 排队等信号量、1000ms 预算从排队起算 → 接近上限即超时 → `record_failure()` → 连 3 次**误开熔断**；共享池让 rerank 等待者占满 worker → embed 排队超 500ms 误报 `embed_unreachable`——与 NFR-8「『慢』与『不可达』由熔断区分」立意相反（排队既不是慢也不是不可达）。
- 修法：信号量在**调用线程** acquire（管线已在线程池里，阻塞安全），超时预算从实际发起调用起算；或 embed/rerank/enhance 分池。备注：非「默认值待 M1-4 标定」能解决——是计时口径问题，任何 < 并发的值都会复现。

**[P2-3] ACL 双断言每请求两次全量可见集扫描（O(可见块数)）**
- 位置：`core/docs/retrieve.py:296`、`:335` → `visible_chunk_ids` 走无 LIMIT 的 `render_select`。10 万块宽权限用户每 search 拉两遍全量 rid——「其余 ≤200ms」预算无对价的大头 + N=5 并发内存放大点。
- 修法：`visible_chunk_ids` 加可选 `rids` 参数（`AND c.rid IN (...)`），前断言传候选集、后断言传 top-k 集——「独立 SQL 路径」性质不变（同 CTE + 基础路形态，仅范围收窄）。

**[P2-4] `token_alignment`/`cjk_fallback_verdict` 把「部分对齐」判成「召回为空」——判据站不住（遗留①质量）**
- 位置：`adapters/tokenizer.py:57-86`。`alignment == 1.0` 才 ok、任意 <1.0 判 dict/trigram；但「对齐率 <1.0 ⇒ 召回为空」只在**零交集**且 PG（`&` 全 token AND）成立；SQLite 是各 token OR，部分对齐照样召回。多 token query（"增值税 申报"、语料只有"增值税"）在 SQLite 会被误判需要 trigram 兜底 → M1-4 黄金集校准系统性误报，可能推动不必要的 schema 变更。
- 修法：判据按「交集是否为空」定 zero-recall（`alignment == 0.0` → 兜底），(0,1) 单列「部分对齐」档并注明 OR/AND 后端差异；docstring「错位则召回为空」改「零交集则召回为空（SQLite OR 语义下部分对齐仍可召回）」。

### P3（建议 / 可登记顺延）

| # | 位置 | 说明 | 建议 |
|---|---|---|---|
| P3-1 | 检查点 filesChanged + R1 记录 | 「新用例 76 条」与实际不符：新增收集 **71** 条（26+18+8+4+7+8=71，与 tester 复跑 71、门禁 +71 三向吻合） | 更正计数（检查点回写，非代码） |
| P3-2 | retrieve.py:70-82,264-266 | 名次协议 `rank` 字段被声明但 RRF 实际消费列表顺序（enumerate）；后端将来乱序会静默错 | docstring 明确「按 rank 升序返回」或 rrf_fuse 按 rank 排序 |
| P3-3 | retrieve.py:461-467 | rerank 返回**空列表**被当成功：全部 0 分 → 归一顶格 1.0、degraded=[]（无效响应伪装「全相关」） | 空响应视同失败走 rerank_skipped |
| P3-4 | retrieve.py:322-325 | 「缺项 0 分垫底」只在分数非负时成立；网关可能返回负分，缺失项会排到负分项之上 | 缺失项用 -inf/独立排序键显式垫底 |
| P3-5 | adapters/breaker.py:26-34,44-53 | `state` 用真实 `time.monotonic()` 忽略注入 now（与 docstring 不一致）；无锁；半开放行不限次数 | 半开只放一个探测（_probing 标志）；state 接受 now |
| P3-6 | 文档卫生 | 失效注释/说明 5 处（acl_ast.py:122-124 / postgres/__init__.py:20 / postgres/backend.py:15-17 / dbwrap.py:284-285 / test_acl_06:48-52 / test_v11_schema:284-286；acl_render.py:209「WHERE 与 ORDER BY 共用 tq」不实） | 顺手清理（防下一段误读） |
| P3-7 | test_e2e_04_dims_immediate.py:87-90 | `test_e2e_04_compile_now_snapshot` 空转测试：只断言 plan.org_id 与 dimension_rules 非空（fixture 自检） | 删除或补真断言（过期/未过期两态 + now 与 DB 时钟差异面） |
| P3-8 | test_ret_01_recipe.py:516 | `len(docs_got[0])>0` 恒真（Tester 也提了） | 顺手改真断言（scores 降序且 ∈[0,1]）——成本一行，**随本轮 P0/P1 一起改** |
| P3-9 | test_acl_08_rerank_guard.py:117-122 | docstring 提到不存在的 InjectingReranker/「越界 index 指向候选外越权 rid」；「响应 index 越界丢弃」防御面无用例 | 改 docstring；越界丢弃补一行用例（或并入 P3-3） |
| P3-10 | test_ret_01_recipe.py:379,456 | 时间阈值紧：0.5s（最坏 0.3s）、0.45s（0.25+开销）——负载机有翻红风险 | 放宽 0.6/0.6 或改「并行 < 串行」相对断言 |
| P3-11 | store/postgres/fts.py | PG 侧 to_tsquery 转义**无负向用例**（TC-FTS-01 畸形 query 全 sqlite） | M1-4 补 PG 参数化（引号/:/*/括号/&）+ 评估语法错误降级而非 500 |
| P3-12 | retrieve.py:239-259 | 空 query 现在走向量路返回最近邻（M0a 是空结果） | API 层 min_length 或 search 早返回 []，并写入口径 |
| P3-13 | retrieve.py:395-401 | 耗时日志四段与 design §3「嵌入/召回/融合/rerank」不对齐（recall 累计含 embed）；routes 不含 rerank 阶段 | M1-4 NFR-8 标定前补 embed 单段 |
| P3-14 | config.py:106-114 | recall_window/rerank_truncate_tokens/breaker_*/rerank·enhance base-key-model 无 env 覆盖（部署态无法切配置/开降级开关） | 至少 LATTICE_RERANK_TRUNCATE_TOKENS/LATTICE_RECALL_WINDOW 给 env 口 |
| P3-15 | 双后端 compile | search 里 plan/vec_plan/guard_plan 编译三次参数全同 → 每请求多 4 次库读 | 复用 plan 给 guard（独立性在 SQL 路径非编译次数）；或加注释 |

## 2. 11 条口径申报逐条复核

| # | 申报 | 复核结论 |
|---|---|---|
| 1 | clamp IQR 系数 1.5 | **合规**（Tukey 1.5×IQR 标准围栏，与 ragflow 形态一致；数值归 M1-4 已申报） |
| 2 | 增强路权重 1.0 | **合规**（§5.2 只对实体路要求权重可配，增强路等权无冲突） |
| 3 | search.acl_intercept 事件名自定 | **合规**（设计未枚举事件名；payload 足够定位；建议 M1-4 登记进 TEST-CASES 备注） |
| 4 | rerank 信号量默认 4 | **部分合规 → P2-2**（排队时间计入超时并喂熔断） |
| 5 | rerank 缺项防御 | **部分合规**（P3-3/P3-4：空响应当成功、0 分垫底遇负分失效） |
| 6 | 增强超时不标 degraded | **合规**（§5.2「超时丢弃」明文、增益路非可用性前提、TC-RET-05 自洽） |
| 7 | none 档不标降级 | **需求边界**（§3 B-1，回 spec 确认 + 勘误；代码不动） |
| 8 | vector_pending 判定 | **不合规 → P1-1**（「向量路关」不含本次嵌入失败） |
| 9 | TC-ACL-08 独立重编译口径 | **合规 ACCEPT**（同意 Tester；补充：独立性来自 SQL 路径而非编译次数，建议注释写明） |
| 10 | _MODEL_POOL 8 线程 | **部分合规 → P2-2**（共享池 + 池内信号量致排队计入超时） |
| 11 | TC-FTS-04 造数载体 | **合规 ACCEPT 附 M1-4 硬条件** |

## 3. 需求边界问题：**有（1 条，非代码）**

**B-1：design §5.2「或 none」与实现/用例的张力——回 supervised-coding 找用户确认（不发给 Coder 修）**
- 原文（design.md:728「不可达或 none 实现→跳过重排用 RRF 序并记审计」；design.md:733「任何降级（嵌入不可达 / rerank 不可达或 none / 探针拒绝档）统一发 search.degraded…」）。
- 实现 + 新用例（test_emb_04_05_07.py:135）取「none=配置态，degraded==[]」。我的独立判断：**实现侧口径更自洽**（§6.1 枚举无 none、告警疲劳、none 是运维显式选择）——但这是**设计正文**与实现的冲突，须回 spec 修订（活文档/非决策变更）。
- **Tester 裁定 3 理由⑤修正**：「routes 字段承载可观测性」不成立——routes 是召回路数不含 rerank 阶段；none 档真正可观测信号只有「config + degraded 为空」，勘误时如实写明。
- 处置：判据 ACCEPT（代码不动），须开勘误 issue（草案 §6）由 supervised-coding 写回。

## 4. Tester 三条裁定复核 + 转交登记项处置

- 裁定 1（TC-ACL-08）：同意 ACCEPT；双面失败面机械化自证逐行核过，两断言各自独立生效、非形式主义。
- 裁定 2（TC-FTS-04）：同意 ACCEPT 附硬条件；真正有验证力的是 ×5 加权名次断言，M1-4 补 PATCH 端到端时把「写入路径不污染 keywords」补上即闭环。
- 裁定 3：ACCEPT 实现侧附勘误（理由修正见 B-1）。
- 登记项处置：①design §5.2 勘误 → 采纳（草案 §6，supervised-coding 写回，不阻塞代码）；②TC-RET-06 弱断言 → **建议本轮顺手收紧**（P2-1 修复必动同文件同族用例，一行改真断言；顺延只保留恒真断言过门禁）；③新增登记：用例计数 76→71 更正（P3-1）、search.acl_intercept 事件名进 TEST-CASES 备注。

## 5. 核验通过项（明确结论）

- **数值口径**：RRF k=60/候选 32/截断 256/增强 800ms/rerank 1000ms/嵌入 500ms/熔断 3×60s/top_k 硬上限 20/recall_window 1024 逐项对齐。
- **流程编排顺序**：与 §5.2 图逐节点一致；阈值位置在两道断言之后。
- **ACL 纪律**：语义规则只实现一次 ✓；两方言渲染器守 v1.1 拍板（chunk_vectors 分表 + cv JOIN + MATERIALIZED + CTE 同文）；**唯一违约=版本条件（P0-1）**。
- **名次协议 / 降级链主体**：方向差异 backend 吸收；降级链 embed/rerank/探针三态完整（reason 与 notice 同源、一请求一条聚合）。
- **遗留 4 条**：rank 协议 ✓、degraded 审计 ✓、P3-R2-1 ✓、P3-R2-2 **加强**非弱化 ✓；遗留①判据见 P2-4（部分不成立）。
- **测试门禁**：零新增 skip/xfail/deselect；无测试文件删除；4 个存量改动文件逐一核对（e2e_01 增强 / pg_backend 合理翻转 / v11_schema 列位 3→10 正确 / r2_committer_fixes 加强）；top_k=100→20 强断言未动。
- **断言真实性第二双眼睛**：RRF 手算序 ✓、候选恰 32+原文负向 ✓、并发峰值 ==2（无信号量=4、信号量=1 都会红）✓、TC-EMB-07 同向 dist=0 谓词失效必红 ✓、TC-ACL-08 双面自证 ✓、熔断注入时钟不推进系统时钟 ✓。
- **边界与卫生**：M0a 基础零改动 ✓；docs/prototype 零 diff ✓；未 push ✓；无中间副本残留 ✓。

## 6. 勘误 issue 草案

> **标题**：[knowledge-lattice] design §5.2 勘误：rerank `none` 档是配置态，不属「降级」标注口径（措辞修正，非决策变更）
> **正文要点**：①现状（line 728/733 原文）；②实现与验收口径（none 不标注、TC-EMB-05 断言 degraded==[]、§6.1 枚举自洽、M1-1 R1 独立验证 ACCEPT）；③理由（运维显式配置/告警疲劳/枚举自洽）；④建议改法（line 728「不可达→跳过重排并记审计；none 实现→跳过重排（配置态，不记降级）」；line 733 移出「或 none」+加注「none 可观测信号=配置档位+degraded 为空，routes 字段是召回路数不可作依据」）；⑤同步面（TEST-CASES TC-EMB-05 补句「none 为配置态、degraded==[]」；known-gaps 不变）；⑥一并登记 search.acl_intercept 事件名与 payload 形态（phase ∈ pre_rerank|pre_return, rids[]）进 TC-ACL-08 备注。

## 7. 实际复跑证据摘要

**做了什么**：全量 1d37713..3bba1bf 28 文件 diff 逐文件通读（含 6 个新测试文件全文）；HEAD/testedSha/未 push/docs 零 diff/工作区仅流程文件 全核 ✓；收集计数交叉核对（逐 fixture 核算 71，与门禁 +71、tester 复跑 71 三向吻合 → 反证「76 条」计数错误）；skip/删除扫描（零新增 skip、无弱化删除）。
**未能做**：pytest/uv run/docker 被 bash 白名单拒绝，**未独立复跑门禁**——采用 Tester 独立复跑值 + 收集计数结构交叉验证（自洽）。P0 为 SQL 文本级缺条件，不依赖运行即可判定。
**交付把关状态**：本轮不放行，原因 P0-1（以及 P1-1/P1-2 契约违背）。P3 可登记顺延，但 P3-1/P3-6/P3-7/P3-8 建议随本轮整改批次顺手清（同文件、零风险）。

- R2 Tester 报告（2026-10-25，逐字原文）：

# M1-1 R2 独立复验报告

**testedSha**：`f741f31770f910628c3ea443275e2eeb4534dbb2`（HEAD）+ docs 勘误批 `2d45af9` + R1 `3bba1bf`——`git log -3` 与申报一致 ✓；双 commit 结构（2d45af9 纯 docs 12 行 / f741f31 零 docs 改动）✓；未 push ✓

## 1. testVerdict: **PASS**

## 2. 门禁复跑（本机实际计数 vs Coder 声称）

| 项 | 我的复跑 | Coder 声称 | 一致 |
|---|---|---|---|
| 常规模式 | **355 passed, 1 deselected, 0 skipped**（22.3s） | 355 + 1 | ✓ |
| `-O` 模式 | **355 passed, 1 deselected, 0 skipped**（20.5s） | 同 | ✓ |
| pg 臂 | **124 条全实跑**（[pg] 92 + PG 专用 32） | 124 | ✓ |
| 基线对账 | 342→355 = **+13**（6 新函数×双后端 + test_acl_06 臂迁移 +1） | +13 | ✓ 自洽 |

## 3. 复验重点逐项结论

| # | 重点 | 核验方式 | 结果 |
|---|---|---|---|
| 1 | 门禁独立复跑 | 双模式全量 + 收集计数对账 | ✅ 见上表 |
| 2 | **P0-1 拦截力** | **本机缺陷注入**（见 §4 完整证据） | ✅ 修复在场（`acl_render.py:225` 与 sqlite 逐字同构）；注入后**两条断言必红**、恢复全绿；断言真在 recall_fts **召回层**（直调 `backend.recall_fts` 断言 pending/tombstone 块不进 BM25 路）+ 渲染层（JOIN 文本），非只断 search() 最终结果 |
| 3 | P1-1 vector_pending 降级面 | 审读造数 + 双后端跑 | ✅ 新用例造数精准：两块**先写满当前标签向量**（排除 R1 掩盖点「块没向量」）再注入嵌入失败 → `vector_pending is True`；实现 `vec_closed = vec_skipped or (embedder and query_vec is None)` 两面俱全。[pg] PASSED |
| 4 | P1-2 熔断降级标注 + none 不破坏 | 双面集成用例 + none 复跑 | ✅ embed/rerank 两面：3 次失败开熔断 → **provider 零调用**（calls 计数冻结）+ degraded 枚举 + outbox `search.degraded` 三断言齐全；rerank 面额外断言 `vector_pending is False`（交叉语义正确）。none 配置态：实现带 `reranker != "none"` 前置，TC-EMB-05（`degraded==[]`）复跑绿 |
| 5 | P2-3 收窄不破坏纵深 | 审读实现 + 双面失败面复跑 | ✅ `visible_chunk_ids(plan, rids=…)` 双后端均以**绑定参数占位符**收窄、SQL 仍走 `render_select` 基础路（同 CTE——独立路径性质不变）；TC-ACL-08 四测（含 monkeypatch 双面自证）[pg] 全绿，fake 适配新签名 `(plan, rids=None)` |
| 6 | P2-1/P2-2/P2-4 | 逐个跑 + 断言强度抽查 | ✅ P2-1 空格 join + 混排强断言（无黏连 split 校验 / `invoice`·`VAT`·`taxpayer` 独立词形 / token≤32）；P2-2 分池 `_RERANK_POOL` + 调用线程 `sem.acquire()`（池内不排队——峰值 `==2` 与耗时断言复跑绿，阈值放宽 0.6 注释写明串行下限）；P2-4 `partial` 档（对齐率 0.5 精确断言）+ **双后端 OR/& 对照实证锁进同一用例**（SQLite 部分对齐可召回 / PG 不召回）——Committer 要求的对照面成立 |
| 7 | docs 勘误一致性 | git show 2d45af9 + grep 代码 | ✅ design v0.9.2 三处（line 728「none 实现→跳过重排（配置态，不标降级）」/ line 733 移出「或 none」+「routes 字段不可作依据」/ 版本段注记）+ TEST-CASES v1.6.1（TC-EMB-05 补句 218 行 + TC-ACL-08 口径登记行 126 行 + 依据区 v0.9.2）。**与代码实际一致**：`search.acl_intercept` 事件名、payload `phase ∈ {pre_rerank, pre_return}` + rids[]、独立重编译口径——逐项 grep 吻合；勘误正文吸收了 Committer 对我 R1 裁定 3 理由⑤的修正（如实写明） |
| 8 | 回归面 + R1 观察项清偿 | diff 逐文件 | ✅ 零弱化：dbwrap（`build_fts_where_ast` PG 侧 NotImplementedError → 双方言——P0-1 用例双后端化的必要翻转）/ test_v11_schema（仅 docstring）/ test_acl_06（sqlite-only → `matrix` 双后端参数化 + FTS 段双方言同构 + 直查**实装路径** `render_fts_recall_select`——正是 R1 测试缺口本体）/ test_acl_07（+召回层负向断言）。P3-8 恒真断言已改真断言（分数降序 + ∈[0,1] + rank 连续）；P3-10 阈值放宽。P3-7 空转测试改真断言（同一过期授权行 now 前后 grants 集合 {VAT,CIT}→{VAT} 精确断言）；P3-9 越界（含负 index）响应降级用例 |

## 4. P0-1 注入验证完整证据（本机操作）

**操作序列**：备份 `acl_render.py` → sed 移除 JOIN 版本条件（line 225）→ 跑用例 → 恢复备份 → `git status --porcelain` 零输出（干净）→ 重跑全绿。

**注入后（缺陷态）**：
```
tests/test_acl_07_visible_docs.py::test_version_pair_scenario[pg] FAILED
tests/test_acl_06_constants_routes.py::test_fts_route_version_condition_on_join[pg] FAILED
========================= 2 failed, 19 passed in 1.08s ==========================
```
失败断言原文（红在正确的位置）：
```
E  AssertionError: pending v2 块不得进 BM25 路（P0-1）
E  assert 'chk:d_cn:v2:1' not in {'chk:d_cn:v1:1', 'chk:d_cn:v2:1', ...}
   （召回层直断言——越权/pending 块确实混入了 FTS 命中集）

E  AssertionError: FTS 路版本条件必须在 JOIN 上
E  assert 'c.version = d.active_version' in "…JOIN documents d ON d.id = c.doc_id JOIN datasets…"
   （渲染层文本断言——JOIN 部分确实缺版本条件）
```
sqlite 臂 19 条不受影响（有自己的版本条件）——**缺陷被精确隔离定位在 PG 路径**。

**恢复后**：`test_acl_06 + test_acl_07` → **21 passed**；全仓 `src/tests/docs` 零 diff。

**结论**：R1 的核心教训（「兜底断言掩盖召回层缺陷」）已被制度化封堵——同类缺陷（PG 召回 SQL 缺红线条件）现在必然触发召回层 + 渲染层双重红灯，不可能再被 355 全绿掩盖。

## 5. 新增观察项（不阻塞，登记）

1. **P2-2 信号量语义微松动**：`sem` 改在调用线程 acquire、`future.result` 超时后 finally 立即 release——但实际 rerank 调用可能仍在 `_RERANK_POOL` 中执行。信号量从此约束的是「活跃请求」而非「在飞调用」，超时场景下瞬时真实并发可超上限。这是「排队不计入调用超时」修复目标的必然权衡（原实现约束到调用结束但排队计超时），可接受；M1-4 NFR-8 标定时如需严格在飞上限再收紧。
2. **test_acl_08 ②的调用序假设仍在**：`two_phase_visible` 以调用计数区分前/后断言（第 1 次=前、第 2 次=返回前），依赖 retrieve 实现顺序——与 R1 相同的可维护性观察项，实现改动调用序时该测试会以误导性方式红，不阻塞。
3. test_ret_04 阈值 0.6s 与串行下限（4×0.15=0.6）相切——串行退化时 `0.6+开销 > 0.6` 仍必红，区分力保留；极慢负载机有贴线风险，P3-10 口径内。

**R1 遗留观察项清偿核对**：P3-8 ✅（真断言）、P3-10 ✅、其余（多 token 黄金集覆盖、TC-FTS-04 REST 面、rerank 真实联调、halfvec）维持登记去向不变。

---

**结论**：R2 修复全部落实且经独立注入验证证明有效——P0-1 拦截力实证闭环，P1×2 契约违背修复且 none 配置态未被误伤，P2×4 修复断言强度达标，docs 勘误与代码一致，回归零弱化。门禁 355+1 双后端双模式 0 skipped、pg 臂 124 全实跑。

- **testVerdict: PASS**
- **testedSha**: `f741f31770f910628c3ea443275e2eeb4534dbb2`

- R2 Committer 报告（2026-10-25，逐字原文）：

## 复审结论

**reviewVerdict: APPROVED**（可以交付用户；1 条 P2 为窄窗口缺陷，已登记、不阻塞本段放行）

- 审查区间：`3bba1bf..f741f31`（`2d45af9` docs 勘误 +7/−6 仅 2 文件；`f741f31` 代码 18 files +533/−132）。HEAD = `f741f31770f910628c3ea443275e2eeb4534dbb2` = 检查点 `testedSha` ✓；origin/develop = `1d37713`（未 push）✓；工作区仅流程文件 ✓；代码 commit 零 docs 改动 ✓。
- R1 的 **P0×1 / P1×2 / P2×4 全部闭环**，P3 顺手项 9 条按期清掉；docs 勘误与 R1 草案**逐处一致、零走样、零超范围**。
- 新增 1 条 P2（半开探测令牌泄漏的窄窗口）+ 6 条 P3，均不触及验收面。

## 1. R1 问题清单逐条闭环判定

- **P0-1 已修（强）**：①`store/postgres/acl_render.py:225` JOIN 与 sqlite 逐字同构，WHERE 内不重复（T9 契约保持）；②断言落在**召回层**（`test_acl_07:113-132` 双后端直调 `backend.recall_fts`，断言 pending v2 与 tombstone 块不进 BM25 路，且先自证「在用版本块正常召回」造数前提）——正是 R1 指出的盲区；③渲染层断言扩双方言且改查**实装路径**（`test_acl_06:84-115`，`matrix` 参数化）；④Tester 本机缺陷注入证明断言能拦；⑤复核断言逻辑：移除条件后 `chk:d_cn:v2:1` 必进命中集 → `not in` 必红——非形式主义。
- **P1-1 已修**：`vec_closed = vec_skipped or (embedder is not None and query_vec is None)` 两面俱全，逐路径核过；新用例造数精准（先写满当前标签向量再注入 fail）。
- **P1-2 已修**：embed/rerank 两面标注+审计+集成用例齐全；**与 B-1 勘误不冲突**（`settings.reranker != "none"` 前置，TC-EMB-05 复跑绿）。
- **P2×4 已修**：P2-1（空格 join + 混排强断言判别力集中够用）；P2-2（分池 + 调用线程信号量——择型 ACCEPT）；P2-3（`visible_chunk_ids(plan, rids)` 双后端实装、独立 SQL 路径不变、TC-ACL-08 四测复跑绿）；P2-4（零交集判据 + partial 档 + 双后端对照锁进同一用例）。
- **P3×9 已清**：P3-1（+13 三向对账自洽；历史 R1 记录行 76 作为历史日志保留可接受）/ P3-2 rank 显式排序 / P3-3 空响应降级 / P3-4（择型 ACCEPT）/ P3-5（衍生 1 条 P2 见 §5）/ P3-6 六处清理 / P3-7 真断言 / P3-8 三条真断言 / P3-9 docstring+越界用例 / P3-10（判别力核过：串行退化仍必红）/ P3-15 注释与 docs 口径一致。

## 2. docs 勘误批核对（`2d45af9`，逐处）

7 处全部**一致**（版本段 v0.9.2 注记含 Tester 理由⑤修正如实写入 / line 728 / line 733 / TEST-CASES 版本段 v1.6.1 / TC-EMB-05 补句 / TC-ACL-08 口径登记行 / 依据区引用）。**零走样、零超范围**：diff 恰为 design 3 行 + TEST-CASES 4 行；known-gaps 未动（符合草案）；§6.1 degraded 三枚举未动（正确）。与代码逐项 grep 吻合。

**（非阻塞，docs 归属 supervised-coding）** 两处建议下次回写顺手处理：① requirements.md 仍 v0.9.1 而设计已 v0.9.2——两文档版本统一纪律，建议补 requirements v0.9.2「联动升版、正文无变更」；② TC-ACL-08「前置」句仍写「mock ACL 编译器」，与同节「非 mock 编译器形态」口径登记字面冲突，建议改「召回面放宽注入」。

## 3. 回归与卫生

零新增 skip/xfail/deselect；零测试文件删除（唯一 `^-def` 为签名迁移非删除）；**断言零弱化净加强**（移除断言逐条核为上移加强/方言分支/必要放宽）；4 个被改存量文件均为必要翻转；改动半径小（api/mcp/app/config/ingest/迁移零改动）；**未声明行为变更：无**（P3-12 空 query 未改 / P3-13 日志未动 / P3-14 config 未动 / P3-15 仅注释）。

## 4. 三条择型申报复核

① **P2-2 分池形态 ACCEPT（附登记）**：修复目标达成；Tester 观察的「活跃请求 vs 在飞调用」语义微松动确实存在且可接受（超调时长 ≤1 timeout + 连续 3 超时熔断限堆积 + 二者不可兼得时先修排队计超时正确）；无死锁风险（sem 持有期 ≤1s、池 8 ≥ 上限 4）。若 M1-4 需严格在飞上限可改 `add_done_callback` release。
② **P3-4 缺项归一 0.0 ACCEPT**：排序语义干净（`-inf` 垫底对负分网关也成立）；全有效响应下归一结果与 R1 完全一致；唯一缺口=部分缺项路径无用例（列 P3-新-2）。
③ **P1-2 none 优先于熔断标注 ACCEPT**：none 下无调用无失败、熔断不可能开路，「none 优先」是精确区分配置态 vs 故障态，非吞信息；与 B-1 勘误完全自洽。

## 5. 新增问题清单（P0/P1 无；以下均不阻塞放行）

**[P2-新] 半开探测令牌泄漏：可在「探针拒绝档 + 熔断半开」叠加下把熔断永久卡在 half_open**
- 位置：`retrieve.py:263`（embed；rerank 同形但 none 档不可达）。机理：`allow()` 半开态消费探测令牌（`_probing=True`），但 `embed_breaker_open = not _breaker_allows(...)` 提到 gate 判断之前——探针拒绝 + 半开叠加时：allow 置位 → gate 分支 vec_skipped → `_embed_query` 不执行 → 无 success/failure 回写 → `_probing` 永不清零 → 向量路不自愈（需重启）+ 每请求误写 search.degraded。可达性窄（需底模漂移拒绝与嵌入熔断半开叠加），影响有界（该场景本应关向量路）。R1 前无此问题，属 P3-5 引入的边缘回归。修法（一行）：allow 调用移入「确实会发起调用」分支，或 `_probing` 加探测租约超时。建议 M1-2 顺手。

**P3（登记）**：P3-新-1 分数收集循环移到了 try 外（provider 异常型返回→500；真实适配器已校验风险低→下段包回 try）；P3-新-2 部分缺项用例缺失（→M1-4/下段）；P3-新-3 `visible_chunk_ids` docstring「rids 非空时」措辞（`if rids:` 实现下 `[]` 不收窄——无实际影响，改文档防误读）；P3-新-4 检查点遗留事项结构化补全（P3-11/12/13/14 带去向进结构化清单 + filesChanged「未 commit」过时更正——supervised-coding 回写）；P3-新-5 docs 两处（见 §2 末尾，supervised-coding 回写批顺带）；P3-新-6 test_ret_04 阈值相切（维持现状可接受）。

## 6. 遗留项登记确认

确认无未声明行为变更；P3-11/12/13/14 去向明确（建议进结构化清单）；原有移交项维持（halfvec→M1-4、TC-FTS-04 REST 面硬条件不变、rerank 真实联调→环境可用时）；R1 观察项核对：TC-RET-06 弱断言已改真、多 token 差异已锁进用例+判据 docstring、M1-4 黄金集分后端校准要求不变。

## 7. 实际复跑证据摘要

只读全量：两 commit 结构与内容、未 push、工作区干净、f741f31 零 docs、2d45af9 仅 2 文件 +7/−6；18 个代码文件 diff 逐行通读；**收集计数三向对账**（+13 = 6 新函数×双后端 + 臂迁移；342+13=355 与 Coder/Tester 吻合）；skip/删除/弱化扫描净加强；docs 7 处逐字比对 + grep 代码一致、无第 8 处改动。**未能做**：bash 白名单拒绝 pytest/docker，未独立复跑门禁——采信 Tester 独立复跑 + 收集计数与断言可达性静态交叉验证。P0-1 拦截力由 Tester 本机注入实验实证，复核失败点语义正确。

**交付把关状态**：testedSha=HEAD ✓；双 commit 结构 ✓；docs 与用户确认勘误稿一致 ✓；未 push ✓。待 supervised-coding 回填 reviewedSha/报告入档/轮次记录 R2 APPROVED；P2-新 / P3-新-1 / P3-新-4 / P3-新-5 登记（P2-新 不阻塞，建议随 M1-2 顺手修）。**放行：approved，可交用户。**
