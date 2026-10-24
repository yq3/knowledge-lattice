---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m0a-3
target: knowledge-lattice
coderTaskId: ses_e97f3c845ffenEskpwz8i9bobj
testerTaskId: ses_e9733693effec6xdTp6RrzQLkb
committerTaskId: ses_e97289259ffeCORDfDSdSk1u45
status: done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: db26d5afde49133ffc92106987995658c8e5b5cc
reviewedSha: db26d5afde49133ffc92106987995658c8e5b5cc
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["knowledge-lattice/src/knowledge_lattice/adapters/parser_docling.py（新增：docling 统一块结构）", "knowledge-lattice/src/knowledge_lattice/adapters/tokenizer.py（新增：jieba 预分词）", "knowledge-lattice/src/knowledge_lattice/adapters/embedder.py（扩展：OpenAI 兼容客户端+维度校验+指纹探针+EmbeddingGate）", "knowledge-lattice/src/knowledge_lattice/core/docs/chunking.py（新增：结构感知切分）", "knowledge-lattice/src/knowledge_lattice/core/docs/excel_chunking.py（新增：Excel 行块）", "knowledge-lattice/src/knowledge_lattice/core/docs/ingest.py（新增：摄取编排+任务状态机+阶段幂等）", "knowledge-lattice/src/knowledge_lattice/core/docs/retrieve.py（新增：BM25 单路编排）", "knowledge-lattice/src/knowledge_lattice/store/sqlite/fts.py（新增：MATCH 转义+bm25 加权常量）", "knowledge-lattice/src/knowledge_lattice/store/sqlite/vec.py（新增：vec_f32 序列化）", "knowledge-lattice/src/knowledge_lattice/store/sqlite/threaded.py（新增：每线程一连接代理）", "knowledge-lattice/src/knowledge_lattice/domain/auth.py（新增：dev JWT+静态 token+组织上下文规则）", "knowledge-lattice/src/knowledge_lattice/mcp/server.py（新增：FastMCP search+60s 超时）", "knowledge-lattice/src/knowledge_lattice/api/（新增：upload/documents/tasks/search/admin 五端点）", "knowledge-lattice/src/knowledge_lattice/app.py（重写：create_app 装配）", "knowledge-lattice/web/（新增：index.html/i18n.js/app.js/style.css——两视图+i18n 机制）", "knowledge-lattice/src/knowledge_lattice/store/sqlite/backend.py（+384 行：recall_fts/insert 事务 D20/嵌入回写防护/任务状态机/指纹基线/outbox）", "knowledge-lattice/src/knowledge_lattice/store/sqlite/acl_render.py（+render_fts_recall_select）", "knowledge-lattice/src/knowledge_lattice/store/backend.py（协议种子扩充）", "knowledge-lattice/src/knowledge_lattice/config.py（+10 项配置）", "knowledge-lattice/tests/（新增 16 文件+fixtures：15 条验收用例+fake_providers）"]
endReason: null
createdAt: 2026-10-23T17:13:55+0800
updatedAt: 2026-10-24T15:23:00+0800
---

# task-knowledge-lattice-m0a-3: M0a-3 摄取与检索最小链——docling 摄取 + BM25 检索 + MCP search + REST 上传 + 静态页壳 i18n

## 任务原文

（需求 + 验收标准，写全——这是恢复时唯一的上下文来源）

**目标项目**：`knowledge-lattice/`（企业知识层 POC，需求 v0.9 / 设计 v0.9，设计冻结纪律——实现问题走测试用例与 issue，coder 禁改 `docs/` 下需求/设计/用例文档，禁动 `prototype/`）。M0a 三段拆分之收官段（M0a-1 已合入 PR#44 / M0a-2 已合入 PR#45，develop HEAD=9a7daa0）。

**会话要求（用户指定）**：本任务 coder / tester / committer 全部**全新会话**（不复用 M0a-1/M0a-2 的任何 task_id）。

**运行时**：Python **3.12.10**（uv 托管，`.python-version` 已钉）。测试栈 pytest（`uv run pytest`）。依赖新增按需最小化（docling/jieba/fastmcp 等按 design §7 选型引入）。

**范围**（design §8 M0a.2 摄取最小链 + M0a.3 检索最小链的 BM25 部分 + M0a.4 服务壳 + M0a.5 验收）：

1. **摄取最小链**（design §5.3 阶段编排的 M0a 子集）：`parse（docling→统一块结构）→ chunk（结构感知切分 256–512 / Excel 按 sheet 行块重复表头；jieba 生成 content_seg/title_seg）→ index_fts（chunks+FTS 同一事务，文档状态→searchable_lexical，**首次上传即切换 active_version=D20**）→ embed（Embedder provider 分批 64，写入前校验 len==config.dim 不符 raise；指纹探针：首部署建档放行 / drift<0.95 拒绝档同标签写入+告警+审计 / 0.95~0.99 告警档；基线存 embedding_fingerprints）`；任务状态机 pending→leased→running→done/failed、阶段幂等续跑（TC-ING-07）
2. **BM25 单路检索**（design §5.2 的 BM25 路 M0a 子集）：query 经 jieba 切分 + token 双引号转义（内部 " → ""）→ `bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)` + 版本条件 + 完整 ACL WHERE（复用 M0a-2 AclPlan/渲染器——**注意 render_expr 已移除，用 `_Renderer`/`render_sql`**；`_Renderer` 不得跨调用拼接片段）；`core/docs/retrieve.py` 最小实现（BM25 单路、top_k 服务端硬上限 20、返回 chunk_id/doc_id/title/page_no/score/dims/source 溯源字段）；向量路/rerank/RRF/LLM 增强/实体路均为 M1/M2 不做
3. **FastMCP `search` 工具** + 60s 超时中间件（ragflow 纪律）
4. **REST API**：multipart 上传 + 任务状态查询 + 检索端点 + `POST /api/dev/token`（仅 dev 配置注册、生产 404）；组织上下文统一规则（`X-Org-Id` 头、MCP org claim 优先、不一致 400、缺失 400、工具参数 org 忽略并记审计——D18 §5.5）
5. **静态页壳**（web/）：上传/检索两视图最小闭环（原型 v0.5 信息结构基准）+ **i18n 机制**（`web/i18n.js` 静态字典 zh/en + `t(key,params)` + `data-i18n` + 头部「中 | EN」切换 + localStorage 持久化默认中文 + `<html lang>`/`<title>` 同步——FR-8 §5.7）；FastAPI 托管静态文件、无构建工具

**验收标准**（TEST-CASES M0a 挂号 15 条 + §六 M0a 行）：

| 用例 | 要点 |
|---|---|
| TC-ING-01 | docling 解析 docx（多级标题+表格）/pptx/xlsx/HTML/PDF → 统一块结构（content/heading_path/page_no/bbox_json/sheet_name） |
| TC-ING-02 | 结构感知切分：递归 token 256–512、结构边界优先、heading_path、表格整块不拆 |
| TC-ING-03 | Excel 按 sheet/行块切分、每行块重复表头、sheet_name 记录 |
| TC-ING-07 | 阶段幂等续跑：index_fts 后中断重跑 → 从 embed 续、不重复写块（uq_chunks_docver）、状态沿 parsing→chunked→searchable_lexical→searchable_full 前进 |
| TC-FTS-01 | MATCH 转义：`"`/`*`/`NEAR`/`AND`/`-`/空格/全角 → token 双引号包裹+内部转义+OR 连接、无 malformed、操作符不激活 |
| TC-FTS-02 | 五列加权 bm25(3.0,1.0,5.0,0.5,8.0)：tags(8)>keywords(5)>title(3)>content(1)>llm(0.5) |
| TC-FTS-03 | 同步触发器与切换清列：INSERT/DELETE/UPDATE 后 FTS 一致；版本切换 UPDATE 五列清空+tombstone 后旧内容 MATCH 零命中 |
| TC-EMB-01 | 维度校验：mock 返回 1024 维 ≠ config 2560 → raise 不写库、无残缺行、任务 failed 可重试 |
| TC-EMB-03 | 指纹探针（M0a 断言范围）：首部署建档放行（≥3 哨兵）/ drift<0.95 拒绝档（同标签写入+告警审计+文档停 searchable_lexical 不 500+notice.degraded 含 probe_reject）/ 0.95~0.99 告警档 / 周期探测两档判定（向量路开闭行为断言随 M1、换标签重嵌入随 M2） |
| TC-E2E-01 | 摄取→检索全链（BM25 单路）：REST 上传 docx → searchable_lexical 时点 BM25 命中（中间态可搜）→ 结果带溯源字段、datasets/doc_filter 收窄 |
| TC-E2E-06 | **MCP 端到端（M0a 验收原句）**：测试客户端经 MCP 以开发 JWT 调 search → 返回带 chunk_id 命中；60s 超时中间件挂载（超时不悬挂） |
| TC-E2E-07 | REST 上传 + 静态页壳：薄壳可用（上传/检索两视图最小闭环）、API 契约先行 |
| TC-AUTH-01 | 静态 token 边界：dev 下签发自用成功/代签 403/管理员签发成功/生产配置 404（不注册路由） |
| TC-AUTH-02 | 组织上下文统一规则（M0a 范围）：REST `X-Org-Id`；MCP claim 优先/不一致 400/缺失 400/参数 org 忽略记审计；REST 路径 org 与头不一致 400 |
| TC-UI-01 | 语言切换与持久化（手动走查）：默认中文 zh-CN / 切换即时全页生效+lang+title 同步 / localStorage 持久化 |

**边界（本任务不做）**：覆盖上传版本切换全链/409/tombstone 90 天清理（M1 版本在用制）；向量路/rerank/RRF/LLM 增强/归一（M1）；quality 区分度环（M1）；TC-ING-04/05/06 断言细则（编码老格式/mojibake 三档/分批断点断言——M1，本任务 embed 分批基础实现即可）；TC-EMB-03 向量路开闭行为断言与换标签重嵌入（M1/M2）；管理面 API/UI（M2）；语义层 sem_*（M2-S）；扫描件 MinerU 路由（M1，docling 样例先行）；PG 后端（M0b）。

**Git**：分支 `develop_opencode`（开工第一步 `git fetch origin && git merge origin/develop` 同步——develop 已含 M0a-2 merge commit 9a7daa0）；每轮 commit `[task-knowledge-lattice-m0a-3] R<n>`，commit 前同步 origin/develop；不 push。

**注意事项（自 M0a-2 移交，非强制任务）**：`render_expr`/`_child` 公开名已移除——渲染一律走 `_Renderer`/`render_sql`；`_Renderer` 不得跨调用拼接片段（每次 render_sql 返回完整 (sql, params)）。

**相关文档**：knowledge-lattice/docs/design.md（§5.2 检索管线 BM25 路/§5.3 摄取管线与任务状态机/§5.5 鉴权与组织上下文/§5.7 前端薄壳与 i18n/§6 MCP 契约/§7 技术选型）、docs/TEST-CASES.md（上表 15 条 + 口径段共享 fake Embedder fixture）、docs/requirements.md（FR-1/FR-8、NFR-8 相关句）、prototype/index.html（信息结构与 UI 风格基准——只参考不改）。

## 需求确认

- [x] 用户已确认（2026-10-23——需求+遗留清单复述后用户同意，含三角色全新会话要求与调用预告确认）
- 历史遗留事项清单：见下节

## 遗留事项（跨任务移交）

- [x] **承接自 M0a-2（done）注意事项**：`render_expr`/`_child` 已移除——本任务渲染走 `_Renderer`/`render_sql`；`_Renderer` 不得跨调用拼接片段（注意事项性质，随实现自然遵守）——**✅ 已遵守并经核验（committer R1 基线核对：render_expr 零引用、_Renderer 均为单次 render_sql 调用、无跨调用拼接；render_fts_recall_select 单次产出完整 (sql, params)）**
- [ ] **M0b 批次（不并入本任务）**：~~backend 参数化骨架~~（✅ 已清偿：来源 task-knowledge-lattice-m0b-1 R1——backend fixture 双臂参数化 + 存量测试参数化改造）；DDL 勘误登记；M0a-1/M0a-2 的 M0b 顺手项（CTE v.status 残留、竞态回归入仓、CTE 恶意 key 断言、fullmatch、标识符 docstring、migrate 告警、CTE 过滤下推、_Renderer 拼接文档化——均→M0b-3）
- [ ] **M1 批次（不并入本任务）**：trigram 判据；T6 完整切换链；conftest channel 口径；grants 写路径校验；TC-ING-04/05/06 断言；TC-EMB-03 向量路开闭复验
- [ ] **移交 M0b 勘误批次（2026-10-24 R1 需求边界问题，用户拍板选项 A）**：TEST-CASES TC-FTS-01 预期句回写——"`*` 作字面量可命中"改为"纯标点 token 不进入 MATCH 表达式；无 malformed、操作符不激活；`AND`/`NEAR` 作字面量可命中"（FTS5 unicode61 不索引纯标点，原子句不可满足；实现等价处置经 committer 裁定）+ 版本段记录；与 M0a-1 的"DDL 两处执行层修正勘误"合并统一落笔（由 supervised-coding edit，coder 禁改）
- [ ] **新增移交（本任务 R1 committer P3 记录项，2026-10-24 登记）**：P3-6（page_count None 计入）、P3-9（嵌入回写防护谓词——TC-VER-06 同款，M1）、P3-10（静态 token disabled 检查）、P3-11（embed 四件套 env 覆盖）、P3-13（上传大小上限 413——M1 200MB）、P3-16（60s 中间件绑定断言）、P3-18（pdf_models skipif）、P3-20（threaded 连接清理钩子）、P3-21（上传三步补偿）、P3-22（可取消执行器评估）、P3-23（search.degraded 审计与 rank 协议——M1）、P3-24（tester 报告表述更正——已由本检查点轮次记录执行）；归一口径注记（BM25 单路 min-max 显示归一≠M1 融合归一——交付时写入验收注记，✅ 已写入 PR #46 交付注记段）
- [ ] **新增移交（本任务 R2 复审 committer P3-R2 记录项，2026-10-24 登记）**：
  - [ ] **M0a-3 交付注记（交付时写入 PR description）**：①"上限硬、下界打底"切分口径（100+450 场景首块 <256 为允许让步——结构边界/上限优先，committer R2 第三节口径注记）；②BM25 单路 min-max 显示归一≠M1 融合归一；③prod 401 响应含内部审查号"P2-5"（P2-5 修复已知残留，M1 清理——P3-R2-3）——**✅ 三项已写入 PR #46 description"交付注记"段（2026-10-24 交付）**
  - [ ] **M1/M0b 顺手批次**：P3-R2-1（test_e2e_01 注释指错文件 test_r2_review_fixes→test_r2_committer_fixes）、P3-R2-2（ticker 测试改时间断言或修正"实证"表述）、P3-R2-4（_hard_split 的 jieba 调用收口 adapters/tokenizer.tokenize_with_offsets）、P3-R2-5（删未使用 import seed_membership）、P3-R2-6（源级断言保持辅助定位）、P3-R2-7（手动走查命令补 LATTICE_PROBE_INTERVAL_S=0+文档注明启动探针耗时）
  - [ ] **流程改进登记（跨任务沿用）**：新建测试文件前应 `git ls-files tests/` 查同名，避免复用他任务通用名；新回归文件用任务前缀命名
- [ ] 无其他

## 交付记录（2026-10-24）

- PR：https://github.com/yq3/lab/pull/46（base=develop，head=develop_opencode，commits=85e5626[R1] + db26d5a[R2]，diff 56 files）
- push：`839bded..db26d5a develop_opencode -> develop_opencode`（用户已确认授权）
- 评审留痕：committer `gh pr review --comment`（review id PRR_kwDOTsiHgs8AAAABT--akg——作者自审平台限制同前两任务，COMMENTED 完整留痕复审结论/双 SHA/测试证据/覆盖文件事件裁定；PR mergeable=MERGEABLE、mergeStateStatus=CLEAN）
- evidence manifest：已写入 PR description 末尾 `## Evidence Manifest` 小节（三 SHA=db26d5a、PASS/APPROVED、gate_commands=[uv run pytest, uv run python -O -m pytest]、stale=false；原内容零删改、占位句已替换，复验 6/6 通过）
- **M0a 里程碑达成**：本 PR 合入即 M0a（骨架周）全部验收原句达成——deepagents 经 MCP 带 chunk_id 检索（开发 JWT）/ 插孤儿行 IntegrityError / 编译器单测先行（T1~T5、T20、T22）
- **合入完成（2026-10-24 09:20 用户确认）**：PR #46 state=MERGED，mergeCommit=`f1beed507ec012c50e5bfa8826b1f549811ab4bb`；origin/develop 前进 `9a7daa0..f1beed5`（merge commit 保留 R1+R2 完整历史）；develop_opencode 远端分支按 D30 约定保留，M0b 继续在此分支开发——**M0a 里程碑正式达成**

## 轮次记录

- R1 网络中断恢复记录（2026-10-23）：首次 Coder 调用 17:16 发起后网络中断、调用方侧显示 cancelled（Task 工具无返回）；经用户指示从 opencode.db 找回会话 `ses_e97f3c845ffenEskpwz8i9bobj`——113 条消息、活跃至 18:25，**Coder 实际工作约 70 分钟有实质产出**：工作区未提交改动（修改 pyproject/backend/conftest 等 6 文件 + 新增 parser_docling/tokenizer/chunking/excel_chunking/fts.py/vec.py/fixtures/test_fts_01/02 等），**尚未 commit**、ingest/retrieve/MCP/REST/web 等关键部分未见。处置：按 §4.3.1 续接该会话（coderTaskId 已更新），告知中断恢复、盘点工作区现状、继续完成剩余实现后 commit R1
- R1: coder 完成（2026-10-23，续接会话，commit `85e5626` 于 develop_opencode，55 files +9560/−63，父提交=9a7daa0）——范围 5 块全交付：摄取链（parser_docling 统一块结构/tokenizer jieba/chunking 256-512/excel 行块重复表头/ingest 编排+任务状态机+阶段幂等+D20 首次上传即切换/embed 分批 64+维度校验+指纹探针两档+EmbeddingGate）/ BM25 单路（fts.py MATCH 转义+acl_render +render_fts_recall_select bm25 五列加权+retrieve.py top_k≤20+溯源字段+notice.degraded）/ FastMCP search+60s 超时 / REST 五端点+dev token 生产 404+D18 组织上下文规则 / 静态页壳两视图+i18n（zh/en 字典+中|EN+localStorage+lang/title 同步）。新增依赖 7 个均有 §7 依据（docling/jieba/fastmcp/fastapi[standard]/httpx/python-ulid/pyjwt）。遗留注意事项遵守（_Renderer 单次 render_sql、无跨调用拼接、core 不碰 SQL）；边界红线自查通过（switch_active_version 显式 NotImplementedError 留 M1）。自测：`uv run pytest` → **149 passed, 1 skipped**（skip=TC-UI-01 manual；存量 87 不回归）；`python -O` 同绿；服务壳冒烟（uvicorn 启动 GET / 200、无 token 401）；未 push；docs/prototype/检查点零触碰。环境备注：docling PDF 模型权重一次性下载，conftest 已做 HF 镜像自适应；supervised-coding 机械核验：HEAD=85e5626 在 develop_opencode、工作区干净 ✓
- R1: tester PASS（2026-10-23，全新会话，报告原文见"最新验证意见原文"节；testerTaskId=ses_e9733693effec6xdTp6RrzQLkb；testedSha=85e5626 前置校验一致；149 passed + 1 manual skipped 双模式；验收 15 条逐条勾验全过——五格式真实 docling 解析无 mock、token 计量真实、幂等续跑真实中断、MCP chunk_id+超时不悬挂、dev token 生产 404、组织上下文五情形、TC-UI-01 manual 标注与走查步骤完备；存量 87 显式复跑零弱化（20 文件组 87 passed）、存量 src 扩展非破坏（backend.py 纯新增/acl_render 纯新增 render_fts_recall_select）；边界符合（switch_active_version NotImplementedError、无越界实现、55 files 申报一致、docs/prototype 零触碰、7 依赖一致）；备注 2 条非失败项：FTS-01 纯标点 token 滤除取舍等价更稳（FTS5 本不索引纯标点）、emb_03 私有状态注入为测试手法两档逻辑已独立覆盖）
- R1: committer NEEDS_CHANGES（2026-10-23，全新会话，报告原文见"最新验证意见原文"节；committerTaskId=ses_e97289259ffeCORDfDSdSk1u45；reviewedSha=85e5626 前置校验一致；**P1×0 / P2×6**：P2-1 首次上传同次执行 embed 失败 active_error 丢写（ingest.py:145-159 局部 doc 未刷新）／P2-2 切分可产 >512 token 非末块（chunking.py:159/170 的 min_tokens 条件）／P2-3 core 直接 import SQLite 方言 pack_f32 违反分层（ingest.py:232）／P2-4 admin router 整体 dev/test 门控致 prod 下 dimensions/datasets 404（app.py:127）／P2-5 prod 仍验签公开默认密钥 dev JWT 可伪造身份（auth.py:81-92+config.py:42）／P2-6 周期指纹探针同步阻塞事件循环最长 30s（app.py:78-95）；**P3×24 记录**；**需求边界问题 1 项**：TC-FTS-01「`*` 作字面量可命中」与 FTS5 unicode61 行为不自洽——建议回写用例口径（纯标点 token 不进 MATCH 表达式），非代码改动；tester 两条备注均裁定接受；tester 报告核对：主要事实属实但 5 处表述偏乐观需更正（store/backend.py 非 6 行、TC-UI-01 走查命令引用不存在入口、TC-ING-07 stop_after 后任务标 done 非 running、top_k 测试空转、TC-E2E-06 的 403 docstring 未实测）；调研借鉴：沉淀已吸收、无调研缺口；归一口径注记（BM25 单路 min-max 显示归一≠M1 融合归一，建议验收记录注明）；修复复核建议：优先 P2-1~6+至少 4 条回归（one-shot active_error/100+450 切分/prod metadata 可达/prod dev JWT 401））
- R1: committer NEEDS_CHANGES → **spec 确认（2026-10-24）**：需求边界问题（TC-FTS-01 `*` 字面量子句与 FTS5 unicode61 不自洽）用户拍板**选项 A**——登记移交 M0b 勘误批次，与 M0a-1 的 DDL 两处修正合并统一回写 TEST-CASES（拟改口径："纯标点 token 不进入 MATCH 表达式；无 malformed、操作符不激活；`AND`/`NEAR` 作字面量可命中"+版本段记录），任务中途不改验收文档基线；R2 修复范围裁定：P2-1~6 全修（含 4 条回归：one-shot active_error/100+450 切分 ≤512/prod metadata 可达/prod dev JWT 401）+ P3 顺手 12 项（committer 建议清单 P3-1/2/3/4/7/8/12/14/15/19 + supervised-coding 加 P3-5 英文硬切内容破坏、P3-17 403 docstring），其余 P3-6/9/10/11/13/16/18/20/21/22/23/24 登记移交 M1/M0b 批次
- R2: 修复轮启动（fixing→implementing；round=2；reviewedSha 置空；修复范围=P2×6 + P3×12 + TC-FTS-01 口径移交登记）
- R2: coder 完成（2026-10-24，续接会话，commit `db26d5a` 于 develop_opencode，19 files +570/−94，父提交=85e5626）——P2×6/P3×12 逐条响应全部"已修"（committer 建议 4 条回归全落地：one-shot active_error/100+450 ≤512/prod metadata 可达/prod dev-JWT 401）；**额外申报**：发现 R1 曾覆盖 M0a-2 存量 `tests/test_r2_review_fixes.py`（同名文件），本轮已恢复原样（与 85e5626 零差异）+ 本轮 17 条回归改名 `test_r2_committer_fixes.py`——即 R1 的 149 基线中 M0a-2 的 9 条 ACL 回归曾被覆盖丢失、R2 恢复后全量 166。自测：TDD 红绿 + `uv run pytest` **166 passed, 1 skipped**（TC-UI-01 manual）；`python -O` 同绿；未 push；docs/prototype/检查点零触碰；supervised-coding 机械核验：HEAD=db26d5a 在 develop_opencode、工作区干净 ✓
- R2: tester PASS（2026-10-24，续接会话，报告原文见"最新验证意见原文"节 Tester R2 小节；testedSha=db26d5a 前置校验一致；166 passed + 1 manual skipped 双模式；基线构成核验 150+17 成立；**特殊申报 3 项核验通过**——test_r2_review_fixes.py 与 85e5626 逐字节 IDENTICAL、M0a-2 的 9 条 ACL 回归生效（存量组 87 含此 9 条）、166=150+17；P2×6 逐条勾验全过（P2-1 one-shot 真实构造/P2-5 攻击语义修复/P2-6 ticker 实证）；P3×12 全过；验收 15 条抽查显式复跑 50 passed 全绿；回归——M0a-3 自有测试改动均为强化/校准（running 断言/403 实测/公共入口），M0a-1/M0a-2 存量文件零触碰、不做项零触碰、docs/prototype 零改动）
- R2: committer APPROVED（2026-10-24，续接会话，报告原文见"最新验证意见原文"节 Committer R2 小节；reviewedSha=db26d5a=HEAD 核验一致；P1×0/P2×0——P2×6 全部已修核对通过（P2-1 含 fresh is None 回退）、P3×12 全部已修、P3×12 项豁免零触碰、TC-FTS-01 按选项 A 移交；新引入 7 条 P3-R2 记录项不阻塞（注释指错文件/ticker 测试不构成非阻塞实证/prod 401 暴露内部审查号/_hard_split 直接 import jieba/未使用 import/源级断言偏脆/手动启动探针等待）；**需求边界口径注记 1 项**：P2-2 修复后 100+450 场景首块 <256——"上限硬、下界打底"口径，建议交付注记，不阻塞；**"覆盖存量文件"事件裁定（git 事实）**：test_r2_review_fixes.py 从未进入任何 commit diff（git log --all 仅 839bded、9a7daa0..85e5626 与 85e5626..HEAD 均 0 行差异）——R1 工作区疑似同名覆盖但未进 commit，恢复是 no-op，**"R1 基线丢失 9 条 ACL 回归"叙述与 git 不符**（R1 提交树 150 基线本就含原版 9 条），166=150+17 为新增而非恢复；流程改进登记：新建测试文件前应查同名文件；调研借鉴：R1 结论保持无缺口）
- **叙述更正（2026-10-24 supervised-coding，依 committer R2 第四节 git 事实裁定）**：本检查点 R2 coder 条目中"发现 R1 曾覆盖 M0a-2 存量 tests/test_r2_review_fixes.py…R1 的 149 基线中 M0a-2 的 9 条 ACL 回归曾被覆盖丢失"的表述**与 git 不符**——事实为 R1 工作区疑似同名覆盖、未进入 commit（85e5626 提交树含原版 9 条、R1 基线 150 完整）；R2 以独立文件名新增 17 条回归、原文件为 no-op。原始条目保留存档，以本更正为准
- **终态校验（2026-10-24 supervised-coding）**：testVerdict=PASS + reviewVerdict=APPROVED + reviewedSha=testedSha=HEAD(db26d5a, develop_opencode) ✓ → status=approved，待用户确认交付

## 最新验证意见原文

### Committer R1 报告原文（2026-10-23，reviewVerdict=NEEDS_CHANGES）

【存档说明】本报告经两次调用交付：主体（〇~五节+六节前半）首次返回，六节尾部+七/八节+最终结论续接补全。以下为合并全文。

# Committer R1 审查报告 — task-knowledge-lattice-m0a-3

## 〇、基线核对

- `git rev-parse HEAD` = `85e5626d63b24239e2cf722061bc9b269dc4269f` = 检查点 `testedSha` ✓；父提交 `9a7daa0`。
- 审查对象：`git diff 9a7daa0..HEAD`，55 files，+9560/−63；`docs/`、`prototype/` 零文件在 diff 清单。
- 工作区：除三个未跟踪检查点文件外干净，无未申报改动。
- 本轮为 R1（`reviewedSha` 原为 null），无上一轮 Committer 意见；已核对 M0a-2 移交事项：`render_expr` 零引用、`_Renderer` 均为单次 `render_sql` 调用、无跨调用拼接；M0a-2 P1-1 的「数据不得进 SQL 标识符位置」在本轮新增 SQL 路径中复查通过（`insert` 列名、`recall_fts`、`list_tasks`、`read_grants` 的 `now_filter` 均为结构常量，数据全部绑定参数；`render_fts_recall_select` 的 `match_expr` 经 `:q` 绑定，BM25 权重为常量）。

**说明**：本会话 bash 权限仅放行 git/gh 命令，未能独立执行 `uv run pytest`；以下以 tester R1 报告 + 全量静态审阅为准。

---

## 一、结论

- **reviewVerdict: NEEDS_CHANGES**
- **P1：0**
- **P2：6**（失败态落库 1 / 切分上限 1 / 分层纪律 1 / prod 路由 1 / prod JWT 1 / 事件循环阻塞 1）
- **P3：24 项记录性意见**（不阻塞）
- **需求边界问题：1 项**（TC-FTS-01 `*` 字面量子句——见第七节）

---

## 二、P2 findings（应修）

### P2-1｜首次上传「同一次执行内」embed 失败时，`active_error` 不落库（失败态丢失）

- **文件**：`src/knowledge_lattice/core/docs/ingest.py:145-159`（`run_task` 的 except → `_record_doc_error`）、`:182`（`_run_stages` 只刷新局部变量）。
- **问题**：`run_task` 在进入阶段前抓取 `doc`，`_run_stages` 在 `index_fts` 后把 **局部** `doc` 重新读取，但这个刷新没有回传给 `run_task` 的 `doc`。首次上传的正常路径是「一次 `run_task` 内走完 index_fts → embed」；`insert` 的 D20 切换已把 DB 中 `pending_version` 清空、`active_version=1`，而 `_record_doc_error` 收到的仍是切换前的 `doc`（`active_version=0`、`pending_version=1`）：走 `set_doc_pending_status(doc_id, 1, "failed")`，该 UPDATE 的 `WHERE pending_version = 1` 在切换后已无匹配行 → **既不写 `active_error`，也不写 `pending_status='failed'`**。文档只停在 `searchable_lexical`，`documents` 详情接口的 `active_error` 为 null，仅任务行带错误。
- **为什么测试没抓到**：`test_emb_01_dim.py` 与 `test_emb_03_probe.py` 均用 `stop_after="index_fts"` 先结束一次执行再**新起一次** `run_task`（此时 `doc` 是刷新后的）；`test_e2e_01_chain.py` 的「一次执行内 embed 失败」路径没有断言 `active_error`。这正是设计 §5.3 / P0-2.2「失败写 `active_error`」的缺口。
- **修改建议**：在 `run_task` 的 `except` 中重新取文档后再记录（`doc = self._backend.get_document(task["doc_id"]) or doc`），或让 `_record_doc_error` 内部按 `doc["id"]` 重新读取；补一条回归：一次 `create_document` + 一次 `run_task`（`embedder.fail=True`）后断言 `active_error` 非空、`active_status == "searchable_lexical"`、任务 `failed`。

### P2-2｜切分可产生 >512 token 的非末块，违反 TC-ING-02「256–512」

- **文件**：`src/knowledge_lattice/core/docs/chunking.py:159`、`:170`。
- **问题**：两处溢出判断都带有 `and buf_tokens >= min_tokens`。当当前 buffer 不足 256、下一段 `n <= 512` 且 `buf_tokens + n > 512` 时（如 100 + 450 = 550），条件不成立，直接并入 → **生成 550 token 的中间块**。超长段（`n > max`）走另一分支会先 `_flush()`，表现不一致。
- **修改建议**：溢出即 flush，去掉 `buf_tokens >= min_tokens` 条件，或在并入前把当前段落按剩余容量切分，保证非表格块 ≤512；补一条 100+450 token 的回归断言。

### P2-3｜core 直接 import SQLite 方言序列化 `pack_f32`，违反「core 不碰 SQL/方言」

- **文件**：`src/knowledge_lattice/core/docs/ingest.py:232`；关联 `store/backend.py:93-94`。
- **问题**：design §3「core 不碰 SQL/方言」、D24 要求方言差异收口 `store/<dialect>/`。`vec_f32` 是 SQLite/sqlite-vec 的 BLOB 形态，core 直接依赖 `store.sqlite.vec` 使 PG 后端无法复用同一编排。
- **修改建议**：把「向量 → BLOB」下移到 `SqliteBackend.write_embeddings`：协议改为接收 `Sequence[Sequence[float]]`（或增加方言无关的 `serialize_vectors` 方法），core 只传浮点向量；修订协议注释与调用点。

### P2-4｜整个 admin router 被 dev/test 门控，导致 prod 下 dimensions/datasets 端点 404

- **文件**：`src/knowledge_lattice/app.py:127-128`；`src/knowledge_lattice/api/admin.py:44-57`。
- **问题**：`if settings.environment in ("dev", "test"): app.include_router(admin.router)` 把 `POST /api/dev/token` **和** `GET /api/orgs/{org}/dimensions`、`GET /api/orgs/{org}/datasets` 一起门控。design §6.2 中 dimensions/datasets 是普通组织作用域端点，只有 `/api/dev/token` 才是 dev/test-only（TC-AUTH-01④ 也只要求该路由 prod 404）。prod 配置下静态页壳 `app.js:42-43` 的 `loadMeta()` 会 404，上传视图无法加载元数据，TC-E2E-07「薄壳可用」在 prod 不成立。
- **修改建议**：把 dev token 拆到独立 router，dimensions/datasets 不受环境门控；补一条 prod 配置下 metadata 端点可达的测试。

### P2-5｜prod 配置仍验签 dev JWT，且默认密钥是仓库公开常量（可伪造任意用户身份）

- **文件**：`src/knowledge_lattice/domain/auth.py:81-92`；`src/knowledge_lattice/config.py:42`。
- **问题**：`authenticate` 先无条件 `decode_jwt(settings, token)`；`dev_jwt_secret` 默认值 `dev-only-insecure-secret-0123456789ab` 硬编码在源码。prod 下攻击者可离线用该公开默认密钥签发 HS256 token（`sub=<已知用户>`）通过认证访问数据。
- **修改建议**：prod 下不进入 dev-JWT 验签分支（返回 401，待 M2 SSO），或要求 `LATTICE_DEV_JWT_SECRET` 显式配置且不等于默认值后仍仅限 dev/test；补一条「prod 下 dev 密钥签发的 JWT → 401」测试。若 M0a 明确不承诺可部署 prod，请在验收记录/known-gaps 明确登记并至少拒绝默认密钥。

### P2-6｜周期指纹探针在事件循环内同步调用 HTTP/DB，可阻塞全部 REST/MCP 请求最长 30s

- **文件**：`src/knowledge_lattice/app.py:78-84`（`_periodic_probe`）；`:89-95`（启动探针同样同步）。
- **问题**：`FingerprintProbe.probe()` 内部同步 `httpx.Client.post`（30s 超时）+ 同线程 SQLite 读写；`_periodic_probe` 是 `async def` 却直接同步调用，运行在事件循环线程上。违反 §2「模型 API 调用全部异步/线程池，不阻塞事件循环」。
- **修改建议**：改为 `await asyncio.to_thread(...)`；`ThreadLocalBackend` 与现有线程模型兼容。

---

## 三、P3 findings（记录性意见，不阻塞）

| ID | 文件:行号 | 问题 | 建议 |
|---|---|---|---|
| P3-1 | `core/docs/ingest.py:129-151`（`:146`） | `stop_after` 注释称「任务留在 running 态由重跑续上」，但 `run_task` 无论是否 `stop_after` 都会 `update_task(done)`；模拟中断时任务实际是 done，TC-ING-07 的「真实中断」证据弱化 | `stop_after` 分支直接 return、不写 done（留 running），或在测试中显式断言任务仍 running；注释同步修正 |
| P3-2 | `tests/test_ui_01_manual.py:9` | 手动走查命令 `uvicorn knowledge_lattice.app:create_app_or_none --factory` 引用了不存在的入口 | 改为 `uvicorn knowledge_lattice.app:create_app --factory` 并补全参数 |
| P3-3 | `core/docs/retrieve.py:75-76` | MCP 契约 §6.1 的 `dataset` 示例是知识库**名称**，实现返回 `dataset_id`，把名称放在额外 `dataset_name`；契约语义偏移 | 将 `dataset` 设为名称、增加 `dataset_id`（或回写设计说明 id 口径）；补一条输出契约断言 |
| P3-4 | `core/docs/retrieve.py:89` | `notice.vector_pending` 恒为 `False`；M0a 没有向量路，设计语义是「本结果缺向量路」，当前值有歧义 | 明确 M0a 口径（恒 false = 本里程碑无向量路）或注释固定；加断言防未来回归 |
| P3-5 | `core/docs/chunking.py:60-70` | 超长句硬切使用 `tokenizer.segment()`（已丢弃空白）后 `"".join(cur)`，英文会拼成 `Ageneraltaxpayer` | 硬切使用原文字符区间/句子片段，或对非 CJK 以空格连接；补英文硬切回归 |
| P3-6 | `store/sqlite/backend.py:194-196` | `page_count = len({page_no})` 把 `None` 计入，docx/html 会得到 1；`ParsedDocument.page_count` 未被 ingest 使用 | 优先使用解析阶段 `page_count`，或至少只统计非 `None` 页码 |
| P3-7 | `store/sqlite/backend.py:167-188` | `pending_dims_json` 中每个值靠 `INSERT ... SELECT` 解析，失败时零行且不报错，随后清空 `pending_dims_json`；维度/取值在 upload 后被停用/删除的竞态会留下「无维度行」文档（空值放行=可见面扩大） | 统计插入行数并与期望值集比较，不符则 raise/保留 pending_dims_json 供重试 |
| P3-8 | `core/docs/ingest.py:228-235` | `_embed_stage` 只做维度校验，不校验 `len(vectors) == len(batch)`；API 少返回向量时 `zip` 静默丢块，仍置 `searchable_full` | 增加数量断言并 raise；`FingerprintProbe` 同样可校验返回条数 |
| P3-9 | `store/sqlite/backend.py:206-236` | `mark_embedding_batch` / `write_embeddings` 未带 `version IN (:active,:pending)` 防护；docstring 已注明 M1（TC-VER-06） | 作为 M1 登记项保持；若修复成本低可在本轮补上 |
| P3-10 | `domain/auth.py:86-92` | 静态 token 路径未检查 `disabled_at`（JWT 路径检查了） | `find_user_by_token_hash` 返回/检查 disabled，保持一致 |
| P3-11 | `config.py:71-83` | `get_settings` 没有读取 `embed_model`/`embed_dim`/`embed_provider`/`embed_batch_size`；换模型四件套无法经环境变量配置 | 补齐 env 覆盖或明确 M0a 仅代码配置 |
| P3-12 | `api/upload.py:74-82` | `dims` 数组允许重复值；`insert` 会向 `document_dimensions` 插重复主键 → 任务失败重试仍失败 | `create_document` 对每个维度值去重，或 API 层 400 拒绝重复 |
| P3-13 | `api/upload.py:84-95` | 无上传大小上限/扩展名校验；设计 M1 有 200MB 上限 | M0a 可接受，建议加可配置上限并返回 413（至少记录 M1 兑现） |
| P3-14 | `web/app.js:102,133`；`web/index.html:58`；`web/i18n.js:28` | `"file?"`、`"attempts"`、`"degraded:"` 未进字典；`upload.dims.hint`「不选 = 空值放行」与必选维度 400 的行为矛盾 | 补字典键、修正文案为「必选维度必须选值；非必选可空」 |
| P3-15 | `tests/test_e2e_01_chain.py:101-107` | top_k 上限测试实际是空转：docx 样例只产生少量块，`len(results) <= 20` 必然成立 | 造 >20 个命中的块，或直接单测 `retrieve.search(top_k=100)` 断言 20 |
| P3-16 | `tests/test_e2e_06_mcp.py:150-152` | 「默认 60s」只断言 settings 值，不验证中间件绑定 | 断言中间件实例 timeout 或保留为配置 sanity（可接受） |
| P3-17 | `tests/test_e2e_06_mcp.py:76-77` | 测试名/docstring 称「无成员关系 → 403」，实际只断言零命中 | 补无成员关系 403 用例或修正 docstring |
| P3-18 | `tests/test_ing_01_parse.py:78-91` | `pdf_models` marker 无 skip 条件；无模型缓存环境会尝试下载而非 skip | 增加缓存/网络 skipif，或在 CI 文档固定权重缓存 |
| P3-19 | `tests/test_emb_03_probe.py:147` | 直接注入 `gate._status` 测 notice | 可改用 `gate.update(ProbeResult("reject", ...))` 公共入口 |
| P3-20 | `store/sqlite/threaded.py:25-30` | 每线程连接只建不关，依赖 GC 回收 | 提供 `close()`/lifespan 清理钩子；POC 可接受 |
| P3-21 | `core/docs/ingest.py:107-125`；`store/sqlite/backend.py:262-269` | 对象文件写入 → 文档行 → 任务行不在同一事务/无补偿 | 失败清理或登记 M1 管理面补偿；POC 可接受 |
| P3-22 | `mcp/server.py:46-52` | `asyncio.wait_for` 无法取消已在线程池执行的同步工具；客户端不悬挂但后台工作继续 | 接受当前语义；可在 M1 评估可取消执行器 |
| P3-23 | `core/docs/retrieve.py:55-57`；`store/backend.py:64-68` | 设计 §5.2 v0.8 要求降级统一发 `search.degraded` 审计，当前仅响应 notice；协议设计说 backend 返回 `rank`，实现返回 `score_raw` | 作为 M1 记录项；M0a 不阻塞 |
| P3-24 | `tests/` / 检查点 | tester 报告称 `store/backend.py`「仅 6 行 docstring/签名注释替换」，实际新增了 Admin/Ingest 协议方法（约 90 行，非破坏性）；「TC-UI-01 走查步骤完备」「TC-ING-07 真实中断」等表述偏乐观 | 归档时更正 tester 报告/检查点措辞，不影响 testVerdict=PASS 的结论 |

---

## 四、Tester 两条备注裁定

1. **TC-FTS-01 纯标点 token 滤除**：**裁定接受**，不构成 IMPL_BUG。FTS5 `unicode61` 不把 `*`/`-` 当作可索引 token，实现滤除后核心预期全部成立，比保留空/纯标点短语更稳。**但** TEST-CASES TC-FTS-01 原文与 FTS5 行为不自洽，属文档口径问题（见第七节），不应让 coder 改用例或改实现。
2. **`test_emb_03_probe.py:147` 私有状态注入**：**裁定接受**。单元测试注入手法，两档判定已独立覆盖；建议后续用 `gate.update(ProbeResult(...))` 公共入口（P3-19），非阻塞。

未收到正式 CASE_BUG 裁定请求，无 CASE_BUG 结论需附。

---

## 五、Tester R1 报告核对

**核对属实**：15 条用例均有对应用例文件与实现落点；真实 docling 解析、维度校验、指纹两档、BM25 加权与触发器、MCP chunk_id/超时、dev token 生产 404、组织上下文五情形、manual 标注等主要事实与代码一致；55 files、7 依赖、docs/prototype 零触碰、`switch_active_version` NotImplementedError 均复核属实。

**需更正/补充的 tester 表述（不影响 testVerdict，但影响证据强度）**：
- `store/backend.py` 不是「仅 6 行 docstring 替换」；新增了 `mark_embedding_batch` 及 Admin 域大量协议方法（约 90 行，纯新增非破坏）。
- TC-UI-01「走查步骤完备」不成立：入口 `create_app_or_none` 不存在（P3-2）。
- TC-ING-07「真实中断」：`stop_after` 后任务被标 done，不是 running 态中断（P3-1）；阶段幂等本身仍被有效覆盖。
- TC-E2E-01 top_k 硬上限测试是空转（P3-15）。
- TC-E2E-06 的 `test_mcp_acl_denied_403` docstring 声称的 403 分支并未实测（P3-17）。
- TC-EMB-01/03 的失败态测试均走「先 stop_after 再新起一次」路径，恰好绕过 P2-1 的 one-shot 失败态缺口。

---

## 六、调研借鉴检查（research/enterprise-rag）

**已吸收且落点正确**：切分（blog/03:165 递归 token+结构感知）、中文检索（jieba 预分词——OneRAG「中文 BM25 缺分词」规避）、BM25 配方（五列加权、召回期不过滤 dify #35233、top_k 硬上限、参数不暴露给 LLM）、服务化（ragflow 60s 超时中间件、工具描述写给 LLM）、ACL 引擎内下推（Azure/dify SQL 下推→AclPlan+完整 WHERE）、指纹探针（语义漂移防护）。

**按边界延后、无缺口**：rerank 真实调用（M1）、RRF/归一/top-32（M1）、向量路（M1）、LLM 增强（M1/M2）、实体路/语义层（M2-S）、quality 环与 mojibake 质量门（M1）、查询级审计/search.degraded（M1/M2，P3-23 已记录）、上传凭证流/worker 子进程/管理面/PG 后端（M1/M2/M0b）——均边界正确。

**总结论**：M0a-3 范围内可吸收的调研沉淀均已落在正确位置；未吸收项与 design 边界一致，**无调研借鉴缺口**。本轮与调研相关的缺陷均为实现级问题（P2-2/P2-1），P2-3 属 D24 分层纪律问题，不是选型或架构取舍问题。

**边界口径注记（非新增必修）**：任务边界把「归一（M1）」列为不做项，而 `retrieve.py:59-65` 对 BM25 单路结果做了 min-max 显示归一（满足 M0a 返回 `score` 契约）。这属于单路最小展示分，不是 §5.2 的「RRF/rerank 之后融合归一」；建议在验收记录注明该口径，M1 融合归一落地时替换。

---

## 七、需求边界问题

**有（1 项，非代码问题）**：

- **TC-FTS-01 中「`*` 作字面量可命中含该字面量的块」与 FTS5 unicode61 的行为不自洽**。`unicode61` 不把纯标点（`*`/`-`）作为可索引 token，该子句在现有 tokenizer 下不可满足。实现选择「纯标点 token 不进 MATCH 表达式」是等价且更稳的处置：核心预期全部成立。**建议 supervised-coding 回写 TEST-CASES（live doc）该子句**为「纯标点 token 不进入 MATCH 表达式；无 malformed、操作符不激活；`AND`/`NEAR` 作字面量可命中」，或登记到附录 A 口径；**不需要 coder 改代码，也不把 tester 备注 1 判为 IMPL_BUG/CASE_BUG**。
- 其余无需求边界问题：范围与验收的其余条款与实现行为一致；无 M1/M2 功能越界；docs/prototype 零改动；7 项新增依赖均有 §7 依据。

---

## 八、审查限制与交付说明

- 本会话 bash 权限仅放行 git/gh 命令，**未独立执行 `uv run pytest`**；以 tester R1 报告 + 全量静态审阅为证据基础。
- 审查对象 `85e5626`（= testedSha = HEAD）；修复轮产生新 commit 后 `reviewedSha` 重新置空并按新 HEAD 重审。
- 未到交付阶段，未执行 `gh pr review` 留痕。
- Tester R1 的 PASS 结论仅覆盖 15 条验收用例；本报告新增的是验收清单之外的失败态、边界、安全与分层问题，二者不矛盾。

---

## 最终结论

- **reviewVerdict: NEEDS_CHANGES**
- **reviewedSha**: `85e5626d63b24239e2cf722061bc9b269dc4269f`（= testedSha = HEAD）
- **P1：0**
- **P2：6**（P2-1 首次上传同次执行 embed 失败 active_error 丢写；P2-2 切分 >512 token 非末块；P2-3 core 直接 import SQLite 方言序列化；P2-4 admin router 整体 dev/test 门控；P2-5 prod 仍验签公开默认密钥 dev JWT；P2-6 周期指纹探针同步阻塞事件循环）
- **P3：24 项记录性意见**（建议本轮顺手 P3-1/2/3/4/7/8/12/14/15/19，其余登记移交 M1/M0b）
- **需求边界问题：1 项**（TC-FTS-01 `*` 字面量子句，回 live doc 修口径，非代码改动）
- **Tester 两条备注裁定**：均接受；无 CASE_BUG 请求。
- **调研借鉴检查**：无调研缺口。
- **修复轮复核建议**：优先修 P2-1～P2-6，至少补 4 条回归——① one-shot 上传 embed 失败断言 `active_error`；② 100+450 token 切分 ≤512；③ prod 配置下 metadata 端点可达；④ prod 下 dev 密钥 JWT 返回 401。修复后重跑双模式全量测试并重新提交审查。

### Tester R1 报告原文（2026-10-23，testVerdict=PASS）

# 验证报告 — task-knowledge-lattice-m0a-3（Tester R1）

**testVerdict: PASS**

**testedSha**: `85e5626d63b24239e2cf722061bc9b269dc4269f`（开工前置校验 HEAD=testedSha ✓；分支 develop_opencode，工作区干净）

## 一、复跑输出摘要（双模式）

| 模式 | 结果 | 耗时 |
|---|---|---|
| `uv run pytest` | **149 passed, 1 skipped**, 2 warnings | 9.39s |
| `uv run python -O -m pytest` | **149 passed, 1 skipped**, 3 warnings | 7.88s |

- skipped = `tests/test_ui_01_manual.py::test_ui_01_manual_walkthrough`（manual 标注，符合 TC-UI 手动走查组口径）。
- 环境备注：docling PDF 权重已入本地缓存，conftest `_tune_hf_env()` 自适应置 `HF_HUB_OFFLINE=1`，全程离线跑完、未触发 HF 下载超时。

## 二、逐条勾验结果表（15 条）

| # | 用例 | 结果 | 证据（文件：行号） |
|---|---|---|---|
| 1 | TC-ING-01 | ✅ 通过 | `tests/test_ing_01_parse.py:20-91`——五格式真实 fixtures（`tests/fixtures/sample.docx/pptx/xlsx/html/pdf`，自造非下载）；`src/knowledge_lattice/adapters/parser_docling.py:97-101` 直调 docling `DocumentConverter.convert`（**无 mock 解析器**）；统一块结构字段断言齐全：heading_path（L33-35）、page_no（L49）、bbox_json（L89，JSON 可解析）、sheet_name（L59）；docx 多级标题层级（L28-29）与表格 rows 边界（L37-40）保真 |
| 2 | TC-ING-02 | ✅ 通过 | `tests/test_ing_02_chunk.py`——token 计量真实：L93-97 断言 `token_count == tokenizer.token_count(content)`（实测一致）；非末块 ∈[256,512]（L35）、结构边界优先跨标题不并包（L33-39）、heading_path 多级（L45-51）、表格整块不拆（L66-78，超限表豁免上限仍单块）、超 512 递归按句拆（L54-63）、尾块 <256 允许（L81-90） |
| 3 | TC-ING-03 | ✅ 通过 | `tests/test_ing_03_excel.py:21-45`——22 行 → 20+2 两行块、每块首行重复表头（L36-37）、sheet_name 记录（L39）、sheet 名进 title_seg 高权列（L48-51） |
| 4 | TC-ING-07 | ✅ 通过 | `tests/test_ing_07_resume.py`——`stop_after="index_fts"` 真实中断（L73，M0a 进程内执行器重启形态）；重跑从 embed 续：块 id 前后一致（L74-80）、不重复解析；`uq_chunks_docver` 兜底：同 (doc,version,seq) 直插 IntegrityError（L111-125）；状态机逐阶段前进 parsing→chunked→searchable_lexical→searchable_full（L38-64，含 D20 首次上传 active_version 0→1 断言 L57）；done 任务重跑 no-op（L128-136） |
| 5 | TC-FTS-01 | ✅ 通过 | `tests/test_fts_01_match.py`——特殊字符集完整：`"`（L19、L25-26、L42）、`*`/`-`（L31、L40）、`NEAR`/`AND`（L39、L69-70）、空格+全角（L25、L41、L75-83）；转义断言 `'x"y' → '"x""y"'`（L19）、OR 拼接（L26）、5 组特殊 query 无 malformed（L35-56）、操作符作字面量真实命中（L59-72）；实现 `src/knowledge_lattice/store/sqlite/fts.py:26-38` |
| 6 | TC-FTS-02 | ✅ 通过 | `tests/test_fts_02_weights.py`——五 chunk 各只在一列含目标词（L18-27）；名次断言双通道：`recall_fts` 序 tags>keywords>title>content>llm（L30-38）+ raw SQL `bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)` ASC 同名次（L41-56）；实现常量 `fts.py:19` `BM25_WEIGHTS = "3.0, 1.0, 5.0, 0.5, 8.0"` 与用例一致 |
| 7 | TC-FTS-03 | ✅ 通过 | `tests/test_fts_03_triggers.py`——① INSERT/DELETE 后 FTS 一致（L46-52）② UPDATE content_seg 后旧词归零新词命中（L55-65）③ 五列清空+tombstone=1 后旧内容 MATCH 零命中（L68-80），并经 `recall_fts` 检索链复证（L83-95） |
| 8 | TC-EMB-01 | ✅ 通过 | `tests/test_emb_01_dim.py`——FakeEmbedder(return_dim=1024) ≠ config 2560 → `EmbeddingDimensionError` raise（L55-56）；库内 0 残缺向量行（L66-69）；任务 failed 带 error、文档停 searchable_lexical（L59-64）；修复后重跑 → done + 全块有向量（L72-84）；单元层 validate_dim（L22-25） |
| 9 | TC-EMB-03（M0a 范围） | ✅ 通过 | `tests/test_emb_03_probe.py`——① 首部署建档：≥3 哨兵且与 SENTINELS 全对齐、基线入 embedding_fingerprints、放行（L39-50）；② 拒绝档：drift<0.95 → 同标签写入拒绝 + `embedding.probe_reject` 告警审计（L53-65）+ 摄取 embed 失败可重试、文档停 searchable_lexical 不 500（L70-87）+ `notice.degraded` 含 `probe_reject`（L130-157）；③ 告警档 0.95~0.99：drift_cos=0.97 精确构造（Gram-Schmidt，fake_providers.py:61-73）、仅告警写入放行（L112-127）；④ 周期探测两档判定同路径生效（L97-109）。**断言严格落在 M0a 口径**：未做向量路开闭行为断言、未做换标签重嵌入（docstring L6-7 明示随 M1/M2）——无超界要求 |
| 10 | TC-E2E-01 | ✅ 通过 | `tests/test_e2e_01_chain.py`——REST multipart 上传**真实 sample.docx**（L22-31）；searchable_lexical 时点（embedder.fail=True 停 lexical）BM25 真实命中（L38-59，中间态可搜）；溯源字段七项逐一断言（L62-66）；datasets 收窄/排除（L82-93）、doc_filter 收窄（L94-99）；top_k 服务端硬上限 20（L101-107）；full 后照常命中（L68-79） |
| 11 | TC-E2E-06 | ✅ 通过 | `tests/test_e2e_06_mcp.py`——fastmcp Client（StreamableHttpTransport，与 langchain-mcp-adapters 同协议栈）+ **开发 JWT** 调 search → 命中带 `chunk_id`（`chk_` 前缀，L48-62）；60s 超时中间件：注入 0.2s 短超时 + 慢检索 → `timed out`、elapsed<2.0s **不悬挂**（L100-147，与生产同款中间件路径）、默认配置 60s 断言（L150-152）；实现 `mcp/server.py:39-52`（asyncio.wait_for→ToolError）+ `app.py` 挂载 |
| 12 | TC-E2E-07 | ✅ 通过 | `tests/test_e2e_07_shell.py`——GET / 两视图（view-upload/view-search）+ langSwitch + data-i18n + 默认 `lang="zh-CN"`（L17-31）；i18n/app/style 资产 200；页壳 fetch 端点与 §6.2 契约一致（L34-38，API 契约先行）；REST 上传→任务状态→检索命中闭环（L41-79）；i18n 机制实现核对 `web/i18n.js:106-146`（t()/setLang 同步 html.lang+title/localStorage/applyI18n） |
| 13 | TC-AUTH-01 | ✅ 通过 | `tests/test_auth_01_token.py`——① dev 自签 200 且签发 JWT 可直接调检索（L19-39）② 代签 403（L42-49）③ sysadmin 给他人签发 200 + token 可用（L52-68）④ 生产配置 404（路由未注册，L71-81）；实现 `app.py:127` 仅 dev/test 注册 admin router |
| 14 | TC-AUTH-02 | ✅ 通过 | `tests/test_auth_02_org.py`——① claim+头一致正常、claim 优先（L60-75）② 不一致 400（L78-91）③ 无 claim 无头 400（L94-104）④ 工具参数 org 忽略并记审计事件 `mcp.org_param_ignored`（L107-126，payload.ignored_org 断言）⑤ REST 路径 org 与头不一致 400 + 一致时放行（403 成员关系非 400，L129-148）；实现 `mcp/server.py:64-87` |
| 15 | TC-UI-01 | ✅ 通过（口径核对，不执行 CI 断言） | `tests/test_ui_01_manual.py:36-43`——`pytest.mark.manual` + skip 理由明确引用 TC-UI 口径段；模块 docstring 走查步骤与用例 ①②③ 一一对应：①清 localStorage 默认中文+`<html lang="zh-CN">`+title、②切 EN 即时全页生效+lang/title 同步+切回、③EN 态刷新/重开浏览器持久化；机制自动化部分由 TC-E2E-07 覆盖（两视图+i18n 资产+localStorage 机制代码在场）——**manual 标注与走查步骤完备性均符合** |

## 三、回归核对结论

- **存量测试文件零 diff**：`git diff 9a7daa0..HEAD --name-only` 下 `test_scaf_*` / `test_acl_*` / `test_matrix_*` / `test_regress_*` / `test_r2_review_fixes` / `test_emb_02_predicate` / `test_monthly_audit_db` / `test_log_skeleton` / `test_backend_contract` / `tests/helpers.py` 均不在改动清单——零改动。
- **conftest.py +150/−4**：删除 4 行仅为 import 区重排（HF 环境变量须先于 docling 导入，加 `noqa: E402`），matrix 等存量 fixture 主体未动、纯新增 M0a-3 fixtures（`ingest_env`/`app_env` 等）。
- **存量组显式复跑**：`uv run pytest tests/test_scaf_01… test_backend_contract.py`（20 文件）→ **87 passed in 2.25s**，与 M0a-2 交付基线 87 一致，零弱化。
- **存量 src 扩展非破坏**：`sqlite/backend.py` +384/−0 纯新增；`store/backend.py` 仅 6 行 docstring/签名注释替换（`recall_fts` 参数 `query→tokens` 协议种子扩充，M0a-2 时该方法无实现）；`acl_render.py` 纯新增 `render_fts_recall_select`（未动存量渲染器与 `_Renderer`）；`reranker.py` 0 行 diff。

## 四、边界符合性抽查结论

- **覆盖上传切换未实现**：`store/sqlite/backend.py:256-258` `switch_active_version` 显式 `raise NotImplementedError("覆盖上传版本切换随 M1（TC-VER-04）")`，无调用链绕过。
- **无越界代码**：rerank 客户端/RRF/向量路检索/quality 环/管理面/sem_* 均无本任务新增实现——grep 命中项均为 M0a-1 存量（`reranker.py` NoopReranker、schema `quality_flags` 表）或 docstring 未来事项注记；`retrieve.py` docstring 明示 M0a 仅 BM25 单路。
- **改动面**：55 files（53 改动 + 计入 conftest/fixtures），与申报一致；`docs/` 与 `prototype/` 零文件在 diff 清单——设计冻结纪律与原型零触碰 ✓。
- **依赖核验**：`pyproject.toml` diff 新增恰 7 项——docling / fastapi[standard] / fastmcp / httpx / jieba / pyjwt / python-ulid（sqlite-vec 为 M0a-1 既有），与申报一致；另加 pytest markers `pdf_models`/`manual`（测试配置，非运行时依赖）。

## 五、备注（非失败项，供 committer 参考）

1. **TC-FTS-01 `*` 字面量子句的实现口径**：用例原文含「`*` 作字面量可命中含该字面量的块」；实现把纯标点 token（`*`/`-`）滤除不进 MATCH 表达式（`fts.py:31-37`，测试注释 L29-30 说明理由）。该取舍等价且更稳：FTS5 unicode61 tokenizer 本就不索引纯标点，`*` 作字面量在任何块中都不可命中，滤除后「无 malformed、操作符不激活」核心预期全部达成。判定：不构成 IMPL_BUG，无需处置。
2. `test_emb_03_probe.py:147` 以 `gate._status = "reject"` 直注私有状态测 notice 标注——测试注入手法，探针两档判定逻辑已由同文件其他用例独立覆盖，可接受。

## 六、结论

- **testVerdict: PASS**（15/15 勾验通过，0 失败项；无 IMPL_BUG / TEST_BUG / CASE_BUG）
- 双模式 149 passed + 1 manual skipped；存量 87 零回归；边界红线（switch_active_version NotImplementedError、无 M1/M2 越界实现、docs/prototype 零触碰、7 依赖申报一致）全部符合。
- testedSha：`85e5626d63b24239e2cf722061bc9b269dc4269f`

### Tester R2 报告原文（2026-10-24，testVerdict=PASS）

# 验证报告 — task-knowledge-lattice-m0a-3（Tester R2 回归）

**testVerdict: PASS**

**testedSha**: `db26d5afde49133ffc92106987995658c8e5b5cc`（开工前置校验 HEAD=申报 commit ✓，develop_opencode）

## 一、复跑输出摘要（双模式）

| 模式 | 结果 | 耗时 |
|---|---|---|
| `uv run pytest` | **166 passed, 1 skipped**, 2 warnings | 10.28s |
| `uv run python -O -m pytest` | **166 passed, 1 skipped**, 3 warnings | 8.36s |

均与期望 166 passed, 1 skipped 一致；docling 权重本地缓存离线跑完，无 HF 超时。

## 二、基线构成核验（166）

- R1 基线全集 150（149 passed + 1 manual skipped）不变 → **+17**（`tests/test_r2_committer_fixes.py`，实测 17 个 test 函数）= 167 = 166 passed + 1 skipped ✓
- `git diff 85e5626..HEAD --name-only` = **19 files**，与申报一致（10 src + 3 web + 6 tests 修改/新增）；`test_r2_review_fixes.py` 不在清单。

## 三、特殊申报核验（重点项）

| 核验点 | 结果 | 证据 |
|---|---|---|
| ① 恢复情况 | ✅ | `git diff 85e5626..HEAD -- tests/test_r2_review_fixes.py` = **0 行**；工作区文件与 `git show 85e5626:…` **逐字节 IDENTICAL**；且该文件自 9a7daa0（M0a-2 合入）以来从未出现在任何 commit diff 中——当前即 M0a-2 原版 |
| ② M0a-2 ACL 回归生效 | ✅ | `pytest tests/test_r2_review_fixes.py --collect-only` = **9 tests**（原版 9 条，R1 覆盖版同为 9 条故总数不变）；存量组显式复跑 87 passed 全绿含此 9 条 |
| ③ 166 构成 | ✅ | 150（R1 基线）+ 17（R2 新增 `test_r2_committer_fixes.py`）= 167（166+1 skip）✓ |

## 四、P2×6 逐条勾验

| # | 结果 | 实现证据（文件：行号，均据 `git diff 85e5626..HEAD`） | 回归证据 |
|---|---|---|---|
| P2-1 | ✅ | `core/docs/ingest.py` `_record_doc_error` 开头 `fresh = self._backend.get_document(doc["id"])` 按 id 重读（修复 D20 切换后快照失效致 UPDATE 零行丢失败态） | `test_p2_1_one_shot_embed_failure_writes_active_error`——**one-shot 真实构造**：单次 `run_task`（fail=True Embedder 全程直跑，非 stop_after 两段式），断言 active_error 含 "unreachable" + 停 searchable_lexical + 任务 failed |
| P2-2 | ✅ | `core/docs/chunking.py:173-176/188-190`——两处去 `buf_tokens >= min_tokens` 前置，溢出即 flush | `test_p2_2`——100+450 token 相邻段（token_count 预算断言 100/450 精确）→ 2 块、全 ≤512、碎块 <256 允许 |
| P2-3 | ✅ | `store/backend.py:93-97` 协议改收 `Sequence[tuple[int, Sequence[float]]]`；`sqlite/backend.py:235-241` `pack_f32(vector)` 收口方言侧；`core/ingest.py` 删除 `store.sqlite.vec` import | `test_p2_3_core_has_no_dialect_import`（源级断言 core 无 "store.sqlite"、协议源含 Sequence[float]）+ `test_p2_3_write_embeddings_accepts_floats`（直收浮点、`unpack_f32(blob)` 回读一致） |
| P2-4 | ✅ | `api/admin.py:19` 独立 `dev_token_router` / `:27` 装饰器迁移；`app.py:131-133`——`admin.router` 无条件注册、`dev_token_router` 仅 dev/test | `test_p2_4_prod_metadata_reachable_not_404`（prod 下 dimensions/datasets → **401 非 404**、静态页 200）+ `test_p2_4_prod_dev_token_route_404`（dev token → 404） |
| P2-5 | ✅ | `domain/auth.py:84-86` `if settings.environment != "prod"` 才进 dev-JWT 验签；`:105-108` prod 直接 raise（错误文本含 P2-5 提示）——攻击语义修复（公开默认密钥在 prod 不再可伪造身份） | `test_p2_5_prod_rejects_dev_jwt_signed_with_default_secret`——默认密钥签发 JWT → 401 + 静态 token → 401 |
| P2-6 | ✅ | `app.py:82-85`（周期）/`:93-95`（启动）均 `await asyncio.to_thread(probe.probe)`——同步 httpx 30s + SQLite 不上事件循环 | `test_p2_6_probe_calls_go_through_to_thread`（源级 count==2）+ `test_p2_6_probe_in_thread_via_gate`（0.3s 慢探针下 60ms ticker 满 6 tick 不阻塞——实证） |

## 五、P3×12 逐条勾验

| # | 结果 | 证据 |
|---|---|---|
| P3-1 | ✅ | `ingest.py` `_run_stages` 返回 interrupted、调用方中断缝不写 done；`test_p3_1` + `test_ing_07_resume.py:74` 增补 running 断言（**断言强化**） |
| P3-2 | ✅ | `test_ui_01_manual.py` 走查命令 `create_app_ornone`（不存在的入口）→ `create_app --factory` + `LATTICE_DATA_DIR=/tmp/lattice-data` |
| P3-3 | ✅ | `retrieve.py` `dataset`=知识库**名称**、`dataset_id` 另出字段（§6.1 契约）；`test_p3_3` 断言 `dataset == "库 ds:vat_lib"` + `dataset_id == "ds:vat_lib"` |
| P3-4 | ✅ | `retrieve.py` vector_pending 恒 False 口径注释（M1 起按块级状态置位）；`test_p3_3` 内口径断言 |
| P3-5 | ✅ | `chunking.py` 新增 `_hard_split`——`jieba.tokenize` 带位置按**原文字符区间**切（不经 segment+join）；`test_p3_5` 断言无 `VATinvoice` 黏连、词间空格保留、token 总数无损 |
| P3-7 | ✅ | `sqlite/backend.py` insert 内 pending_dims 逐值 `rowcount` 累计、`inserted != len(expected)` → raise RuntimeError 整事务回滚；`test_p3_7` 断言块未写 + `pending_dims_json` 保留 + active_version=0 |
| P3-8 | ✅ | `ingest.py` 批次条数守卫 raise `EmbeddingResponseError`（防 zip 静默丢块）+ `embedder.py:131-134` 探针哨兵条数守卫；`test_p3_8_embedding_count_mismatch_raises`（0 半写、停 lexical、failed）+ `test_p3_8_probe_count_guard` |
| P3-12 | ✅ | `ingest.py` create_document `dict.fromkeys` 去重；`test_p3_12` 重复 ["CN"×3] → document_dimensions 恰 1 行、任务正常 searchable_full |
| P3-14 | ✅ | `i18n.js` 补 `upload.file.required` / `search.degraded` / `status.attempts`（zh+en 双字典）+ `upload.dims.hint` 文案修正（必选必选值/非必选可空语义清晰）；`app.js` 三处硬编码英文改 `t()`；`index.html` hint 同步 |
| P3-15 | ✅ | `test_p3_15`——25 个可命中块 + top_k=100 → **恰好 20**（真实截断，`== TOP_K_HARD_LIMIT == 20`）；`test_e2e_01` 原恒真 `<=20` 空转断言移除（指向 P3-15，**强化非弱化**） |
| P3-17 | ✅ | `test_e2e_06_mcp.py` 新增无成员关系用户 u_guest 经 MCP search → ToolError 含 "403"+"membership"（**实测**非注释） |
| P3-19 | ✅ | `test_emb_03_probe.py` `gate._status` 私有注入 → `gate.update(ProbeResult(status=…, min_cosine=…))` 公共入口（2 处） |

## 六、验收 15 条抽查复验（R2 触碰 ingest/chunking/retrieve/auth 核心）

抽查组显式复跑（`test_ing_02/test_ing_07/test_e2e_01/test_e2e_06/test_auth_01/test_auth_02/test_emb_03/test_r2_committer_fixes`）→ **50 passed**。逐条：

- **TC-ING-02** ✅：6 用例全绿——新切分逻辑（溢出即 flush）下 256–512 上限、结构边界、表格整块不拆全部保持；`test_tail_chunk_below_min_allowed` 参数 250→170 为新语义下「近上限欠 min」形态校准（断言 len==2/尾块<min/内容完整均保持，非弱化）。
- **TC-ING-07** ✅：4 用例全绿 + 新增中断缝 running 态断言——幂等续跑语义反而更强。
- **TC-E2E-01** ✅：全链绿——dataset 契约变化后原 7 项溯源字段断言（chunk_id/doc_id/title/page_no/score/dims/source）不受影响、BM25 命中/收窄/top_k 全保持。
- **TC-E2E-06** ✅：MCP chunk_id 命中 + 超时不悬挂 + 默认 60s + **新增无成员关系 403 实测**。
- **TC-AUTH-01/02** ✅：4+5 用例全绿——router 拆分后 dev token 四态（自签/代签 403/sysadmin/prod 404）与组织上下文五情形行为零变化。
- **TC-EMB-03** ✅（附加抽查）：7 用例全绿——gate 公共入口重构后两档判定/审计/notice 标注语义不变。

## 七、回归与边界复查结论

- **M0a-1/M0a-2 存量零弱化** ✅：85e5626..HEAD 改动的测试文件中，属 M0a-3 R1 自有测试的改动全部为强化/校准（test_ing_07 +1 断言、test_e2e_01 移除空转断言改真实断言、test_e2e_06 +15 行 403 实测、test_emb_03 私有注入→公共入口、test_ui_01 docstring 命令修正、test_ing_02 参数校准）；M0a-1/M0a-2 存量文件（test_scaf_*/test_acl_*/test_matrix_*/test_regress_*/test_r2_review_fixes/test_emb_02/test_monthly/test_log/test_backend_contract/helpers/conftest）**零触碰**；存量组显式复跑 **87 passed**。
- **不做项零触碰** ✅：P3-6/9/10/11/13/16/18/20/21/22/23/24 在 19-file diff 中无任何对应实现落点。
- **docs/ 与 prototype/ 零改动** ✅：diff 清单无任何 docs/、prototype/ 路径（TC-FTS-01 口径回写留待 supervised-coding，正确未越权）。

## 八、结论

- **testVerdict: PASS**（P2×6 + P3×12 + 特殊申报 3 项全部勾验通过；15 条验收抽查全绿；0 失败项，无 IMPL_BUG / TEST_BUG / CASE_BUG）
- 双模式 166 passed + 1 manual skipped；基线构成 150+17 核验成立；M0a-2 存量 `test_r2_review_fixes.py` 恢复原样（逐字节一致、9 条 ACL 回归生效）；边界红线（不做项/docs/prototype）零触碰。
- testedSha：`db26d5afde49133ffc92106987995658c8e5b5cc`
