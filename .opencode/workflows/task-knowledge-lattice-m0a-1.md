---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m0a-1
target: knowledge-lattice
coderTaskId: ses_e996e9414ffeqZuS0SYxev2r3j
testerTaskId: ses_e994da8beffe3tRhLvFd4azA6C
committerTaskId: ses_e9943b7edffe4rro3naUEJNxv4
status: done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 55846be0160ee1c0d7d4f6819254fe91e1e15eca
reviewedSha: 55846be0160ee1c0d7d4f6819254fe91e1e15eca
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["knowledge-lattice/pyproject.toml", "knowledge-lattice/.python-version", "knowledge-lattice/uv.lock", "knowledge-lattice/config.py", "knowledge-lattice/log.py", "knowledge-lattice/src/knowledge_lattice/（§3 顶层结构占位：app.py、api/、mcp/、core/docs/、core/semantic/、domain/、worker/、eval/、web/）", "knowledge-lattice/src/knowledge_lattice/store/backend.py", "knowledge-lattice/src/knowledge_lattice/adapters/embedder.py", "knowledge-lattice/src/knowledge_lattice/adapters/reranker.py", "knowledge-lattice/src/knowledge_lattice/store/sqlite/migrations/docs/0001_schema_v1.sql", "knowledge-lattice/src/knowledge_lattice/store/sqlite/migrate.py", "knowledge-lattice/src/knowledge_lattice/store/sqlite/connection.py（R2 由 connect.py 改名，git 识别 D+A）", "knowledge-lattice/src/knowledge_lattice/store/sqlite/audit.py", "knowledge-lattice/src/knowledge_lattice/store/postgres/（M0b 占位）", "knowledge-lattice/tests/（10 文件：8 个 test 模块 + conftest + helpers——TC-SCAF-01~05 全量 + 月库/协议契约/log 骨架 + 造数 helpers；v1 误记 9 文件已按 committer P3-24 修正）"]
endReason: null
createdAt: 2026-10-23T10:19:07+0800
updatedAt: 2026-10-24T15:23:00+0800
---

# task-knowledge-lattice-m0a-1: M0a-1 地基——脚手架 + 连接工厂 + 迁移框架 + 文档侧全量 DDL/触发器

## 任务原文

（需求 + 验收标准，写全——这是恢复时唯一的上下文来源）

**目标项目**：`knowledge-lattice/`（企业知识层 POC，需求 v0.9 / 设计 v0.9，设计冻结纪律——实现问题走测试用例与 issue，coder 禁改 `docs/` 下需求/设计/用例文档，禁动 `prototype/`）。

**运行时**：Python **3.12.10**（uv 托管；开发=部署同版本——G-11 口径：目标机系统 Python 3.9.9 不满足 docling/FastMCP 下限，部署带 uv 托管 CPython 3.12、系统解释器不作为依赖）。测试栈 pytest（`uv run pytest`）。

**范围**（design §8 M0a.1 原文——骨架 + schema 全量落）：

1. **uv 项目脚手架 + config.py** + §3 顶层结构占位（`core/docs/` 与 `core/semantic/` 对称分包、`store/<dialect>/migrations/{docs,semantic}/` 二维迁移目录、`web/` 占位、`log.py` 模块骨架——结构化日志充实与中间件挂接随 M0a-3 服务壳，本任务只落模块与 §3 归属）
2. **StorageBackend 协议 + AclPlan 结构化产物类型 + 嵌入/重排 provider 接口**（D12/D24——协议与数据结构定义 + SQLite 实现先行；AclPlan 编译器逻辑与渲染器属 M0a-2，本任务不实现；测试自 M0a 起按后端参数化，本地无 DSN 可 skip——CI 必跑 PG 自 M0b job 建立起生效，M0a 期间仅 SQLite 后端验收）
3. **迁移框架**（含外键处理约定：单步事务 BEGIN IMMEDIATE + `user_version` 同事务前进 + 迁移窗口临时关闭外键 + 结束 `PRAGMA foreign_key_check` + 幂等重放无副作用）
4. **文档侧全部 DDL 与触发器一次性落**（design §4 全量，**`sem_*` 除外**——语义表 M2-S1 经 `store/<dialect>/migrations/semantic/` 落库；audit append-only 触发器属月库、由连接工厂滚动创建，不在主库 schema v1 内）
5. **连接工厂**（`foreign_keys=ON` 每连接生效 + pragma 失败显式 `raise RuntimeError`（非 assert——`python -O` 剥离，design §3）+ `journal_mode=wal` / `busy_timeout=5000` / `synchronous=NORMAL` + 月库滚动建表 + sqlite-vec 扩展加载——`vec_distance_cosine` 可调用断言，known-gaps G-11 收窄动作①）

**验收标准**（TEST-CASES.md §一 TC-SCAF 组全 5 条 + §六 M0a 行"插孤儿行 IntegrityError"验收句）：

| 用例 | 要点 | 后端 |
|---|---|---|
| TC-SCAF-01 | `foreign_keys` 每连接生效返回 1；`user_dimension_grants` / `document_dimensions` 插孤儿行抛 `sqlite3.IntegrityError` | both（M0a 仅 SQLite） |
| TC-SCAF-02 | PRAGMA 全集 `wal`/`5000`/`NORMAL(1)`/`1` 逐项一致；sqlite-vec `vec_distance_cosine` 可调用 | sqlite-only |
| TC-SCAF-03 | 迁移窗口关外键、结束 `foreign_key_check` 空；违例检出即回滚、库态与迁移前一致；`user_version` 只前进、重复运行幂等 | sqlite-only |
| TC-SCAF-04 | design §4 文档侧全部触发器存在（`trg_dimval_immutable`、`trg_membership_delete_cleanup`、`trg_membership_no_extend`、`trg_documents_org_immutable`、`trg_datasets_org_immutable`、`trg_dimensions_org_immutable`、`trg_documents_ds_org_check`、`trg_documents_ds_immutable`、`trg_docdims_consistency`、`chunks_ai/ad/au`）且逐个 ABORT 行为断言；`uq_chunks_docver(doc_id, version, seq)` 唯一索引语义 | sqlite-only |
| TC-SCAF-05 | 删除 org:tax membership → 该组织维度授权全清（含 `source='sync:…'`）、org:gl 授权不受影响（触发器按 `dimensions.org_id` 收敛） | sqlite-only |

**边界（本任务不做）**：摄取链/检索/ACL 编译器逻辑/AclPlan 渲染器/MCP/REST/静态页壳（M0a-2、M0a-3 范围）；`sem_*` 表（M2-S1）；PG DDL 与 spike（M0b）；审计月库行为断言（TC-OPS-02，M2）。

**边界拍板补记（2026-10-23 R1 需求边界问题，用户裁定选项 A）**：M0a-1 仅要求 SQLite 后端验收；backend 参数化骨架（conftest `backend` fixture + PG 分支 skip）**延至 M0b PG spike 一并落地**，不属于 M0a-1 缺口；验收记录须注明"TC-SCAF-01 的 PG 臂为 M0b 激活项、R1 的 0 skipped 是里程碑范围而非静默 skip"。

**Git**：分支 `develop_opencode`（开工第一步 `git merge origin/develop` fast-forward 同步——当前落后 104 提交、领先 0）；每轮 commit `[task-knowledge-lattice-m0a-1] R<n>`，commit 前同步 origin/develop；不 push。

**相关文档**：knowledge-lattice/docs/requirements.md（§8 M0a 行）、docs/design.md（§3 结构 / §4 DDL 与触发器 / §8 M0a.1）、docs/TEST-CASES.md（TC-SCAF-01~05、§六 M0a 行）、docs/known-gaps.md（G-6/G-11）。

## 需求确认

- [x] 用户已确认（2026-10-23——用户确认三段拆分与串行、Python 3.12.10、开工指令"开始吧"；本检查点创建后经复述确认转 implementing）
- 历史遗留事项清单：17 个 pulsepet 检查点 status=approved 且遗留小节有未勾选项——**2026-10-23 用户裁定豁免**："不用管 pulse-pet"，不并入本任务、维持原检查点现状（knowledge-lattice 与 pulsepet 无依赖关系）

## 遗留事项（跨任务移交）

- [x] pulse-pet 系列历史检查点遗留事项豁免（2026-10-23 用户裁定"不用管"——去向：维持 task-pulsepet-* 各自检查点原状，不并入 knowledge-lattice 任务）
- [x] known-gaps G-11 收窄动作①"M0a 连接工厂断言补扩展加载可用"——**已清偿**（TC-SCAF-02 sqlite-vec `vec_distance_cosine` 可调用断言落地，R1 commit 2152c6c；来源任务 task-knowledge-lattice-m0a-1；known-gaps.md 侧登记按冻结纪律留待 M0b 勘误批次）
- [ ] **移交 M0b**：backend 参数化骨架（conftest `backend` fixture：sqlite 实跑 + pg 无 DSN `pytest.skip`）随 M0b PG spike 落地（2026-10-23 用户拍板选项 A，R1 需求边界问题）
- [ ] **移交 M0b**：两处 DDL 执行层修正（trg_docdims_consistency 建表顺序 / FTS 触发器 rowid 列名）在 known-gaps 或 design 勘误登记一笔（tester 提出并经 committer 裁定采纳，语义等价已验证）
- [ ] **移交 M0b**：committer P3 移交项——~~P3-14（:memory: 跳过月库）~~（**R2 复审改记 moot**：P3-13 全集 WAL 校验使 :memory: 在月库创建前已抛 RuntimeError，实质随 P3-13 关闭；committer 建议未来在 connect() docstring 注明 file-backed WAL-capable DB only，随 M0b 顺手）、P3-15（月库缓存 exists 检查）、P3-16（UTC 口径 docstring）、P3-17（Admin/Semantic 空 Protocol 方法种子）、P3-18（roll_monthly 类型收窄）、P3-23（config 轻量测试）；另 P3-3/4/5/7/8/11（迁移框架健壮性/测试强度小项，随 M0b v1.1 迁移实作时一并）
- [x] 验收记录注记——**已写入 PR #44 description"验收注记"段**（PG 臂 M0b 激活、0 skipped 非静默 skip；月库 append-only 断言为机制验证、不构成 TC-OPS-02 验收；2026-10-23 交付）
- [x] **移交 M0a-2**：R2 复审新增 P3 记录项择要——config.py:20 注释 connect.py→connection.py（改名不彻底唯一遗漏，approved 后不改代码避免 SHA 失效）；为 P3-1/2/12/13/19 补 3 条轻量回归测试（事务中 FK OFF / :memory: journal 失败 RuntimeError+连接关闭 / `__init__` 导入身份）；其余 R2 P3（journal_mode 查询纳入重试、重试耗尽包装 RuntimeError、FK OFF 复查移入 try/finally、跳过分支补 foreign_keys 断言等——见 R2 报告 4.2 节）随 M0a-2 触碰相应文件时顺手——**✅ 已清偿（来源任务 task-knowledge-lattice-m0a-2，R1 commit 7e68936：①config.py:20 已修；②3 条回归落地且经 tester 独立核验；③3 项已做 + journal_mode 查询经核实确已由 M0a-1 R2 落地——committer M0a-2 R1 第七节裁定"遗留承接整体合格"）**
- [ ] **移交 M1**：FTS5 trigram/自定义词表作为 M1 TC-FTS 判据落地（调研 blog/04、blog/10 沉淀，design §10 既有安排）

## 交付记录（2026-10-23）

- PR：https://github.com/yq3/lab/pull/44（base=develop，head=develop_opencode，commits=2152c6c[R1] + 55846be[R2]，最终 diff 43 唯一文件）
- push：`ea7fdcd..55846be develop_opencode -> develop_opencode`（用户已确认授权）
- 评审留痕：committer `gh pr review --comment`（review id PRR_kwDOTsiHgs8AAAABTzZ1dw——GitHub 禁止作者自 approve，COMMENTED 完整留痕复审结论/双 SHA/测试证据；PR mergeable=MERGEABLE、mergeStateStatus=CLEAN）
- evidence manifest：已写入 PR description 末尾 `## Evidence Manifest` 小节（head/testedSha/reviewedSha=55846be、PASS/APPROVED、gate_commands=[uv run pytest, uv run python -O -m pytest]、stale=false；原 description 26 行零删改）
- 状态：done（合入待用户确认后执行，不自动合入）
- **合入完成（2026-10-23 12:38 用户确认）**：PR #44 state=MERGED，mergeCommit=`28125a8741628c4fe0f211287233485c0c2e54e1`；origin/develop 前进 `93dcd6a..28125a8`（merge commit 保留 R1+R2 完整历史）；develop_opencode 远端分支按 D30 约定保留，M0a-2 继续在此分支开发

## 轮次记录

- R1: coder 完成（2026-10-23，commit `2152c6c` 于 develop_opencode，43 files +1983 行——uv 脚手架钉 3.12.10 / §3 结构占位 / StorageBackend 六域协议 + AclPlan frozen dataclass / Embedder+Reranker 接口含 NoopReranker / 0001_schema_v1.sql 全量 DDL（16 表+6 索引+12 触发器，sem_* 与 audit 月库除外）+ 两处执行层修正已注释注明（trg_docdims_consistency 移至目标表后 / FTS 虚表列名用 rowid）/ 迁移框架（BEGIN IMMEDIATE + user_version 同事务 + 窗口关外键 + foreign_key_check 回滚 + 幂等 + complete_statement 拆分）/ 连接工厂（四 PRAGMA + RuntimeError + sqlite-vec vec_distance_cosine 断言 + 月库滚动）；环境对齐 G-11：系统 python.org 3.12.10 无 enable_load_extension，已 uv python install 3.12.10（python-build-standalone，sqlite 3.47.1））。自测：`uv run pytest` → **32 passed in 0.16s**（TDD 流程：测试先行 14 failed+16 errors → 实现后全绿）；`uv run python -O -m pytest` → 32 passed（RuntimeError 不被 -O 剥离实证）；supervised-coding 机械核验：HEAD=2152c6c 在 develop_opencode、工作区干净、父提交=同步后 93dcd6a、未 push ✓
- R1: tester PASS（2026-10-23，报告原文见"最新验证意见原文"节；testerTaskId=ses_e994da8beffe3tRhLvFd4azA6C；testedSha=2152c6c 开工前置校验一致；`uv run pytest` 32 passed 0 skipped + `python -O` 32 passed（RuntimeError 非 assert 实证）；TC-SCAF-01~05 逐条勾验全过；边界抽查 5 项全过——sem_* 不在主库 / audit 月库边界 / DDL 触发器与 §4 逐字对照（两处执行层修正已注释注明语义一致）/ uq_chunks_docver 唯一索引语义 / 连接工厂纪律；0 skipped——PG 臂属 M0b 范围划分非静默 skip；tests/ 与业务代码零改动；tester 建议：两处执行层修正随 M0b 收口时在 known-gaps 或 design 勘误登记一笔，非阻塞）
- R1: committer NEEDS_CHANGES（2026-10-23，报告原文见"最新验证意见原文"节；committerTaskId=ses_e9943b7edffe4rro3naUEJNxv4——首次调用返回空、续接两次交付完整报告；reviewedSha=2152c6c 前置校验一致；**需求边界问题×1**：backend 参数化骨架口径歧义（任务原文"测试自 M0a 起按后端参数化" vs "M0a 期间仅 SQLite 后端验收"，选项 A=仅 SQLite 验收通过+M0b 落骨架 / B=参数化骨架是 M0a-1 硬要求转 P2 / C 已排除）；**P2×2**：迁移框架并发竞态（user_version 检查在 BEGIN IMMEDIATE 写锁外，并发第二进程崩溃）+ TC-SCAF-03 失败回滚测试"finally 恢复外键"证据不成立（测试手动 OFF/ON 掩盖 finally 失败路径）；**P3×25** 建议级（迁移健壮性/测试强度/连接工厂边界/协议接口/杂项）；tester 补充说明裁定：两处执行层修正采纳为移交事项（M0b 登记）、-O warning 认可无动作；**调研借鉴检查**：对照 research/enterprise-rag/ 已吸收主要实践（SQLite 一把梭/WAL/FTS5 五列+jieba 字段/BLOB+sqlite-vec/强类型 schema/append-only 审计/任务租约/六域协议），未吸收项均为后续里程碑既有安排、无新增决策变更；未独立复跑 pytest（工具权限），以 tester 报告+静态审阅为准）
- R1: committer NEEDS_CHANGES → **spec 确认（2026-10-23）**：需求边界问题用户拍板**选项 A**（仅 SQLite 验收、参数化骨架延 M0b、验收记录注记 PG 臂激活）；P3 处理用户授权按 supervised-coding 建议——R2 顺手修 11 条（P3-1/2 迁移 PRAGMA 校验与 ROLLBACK 防御、P3-6/9/10 测试强度、P3-12/13 连接工厂失败路径与 WAL 断言、P3-19 `__init__` footgun、P3-20/21/22 测试卫生），其余 13 条登记移交（见遗留事项小节）；P3-24（检查点元数据 9→10 文件）已由 supervised-coding 修正
- R2: 修复轮启动（fixing→implementing；round=2；reviewedSha 置空；修复范围=P2×2 + P3×11 + 任务原文边界拍板补记）
- R2: coder 完成（2026-10-23，commit `55846be` 于 develop_opencode，10 files +269/−110）——P2×2 + P3×11 逐条响应全部"已修"（逐条对照表见 coder 返回，响应协议合规无表演性同意）；两条合理连带：①`connect.py`→`connection.py` 模块改名（P3-19——`connect` 函数名为 design §3 钦定不可改，`__init__` re-export 与子模块名全部错开）；②P2-1 并发补偿测试暴露 connect 并发缺陷（WAL 切换 BUSY）连带修复（busy_timeout 前置 + journal_mode 先查后设 + 有限重试，:38-52）。自测：`uv run pytest` → **34 passed**（32+P2-1 补偿测试×2；并发测试连跑 8 次单测+5 轮全量稳定）；`uv run python -O -m pytest` → 34 passed 1 warning（预期）；commit 前同步 origin/develop ✓（Already up to date）；未 push ✓；docs/、prototype/、检查点零改动 ✓；supervised-coding 机械核验：HEAD=55846be 在 develop_opencode、commit 格式正确、工作区干净 ✓
- R2: tester PASS（2026-10-23，续接会话，报告原文见"最新验证意见原文"节；testedSha=55846be 前置校验一致；34 passed 双模式 + 全量加跑 2 轮（累计 4 轮全绿）+ 并发单测连跑 8/8；回归核对——R1 的 TC-SCAF-01~05 断言零弱化零删除（唯一删除段=被 P2-2 标记的手动 OFF/ON 清理段本身，替换为更强失败路径证据）；P2×2+P3×11+连带×2 逐条勾验全过（含 P3-13 真实 WAL 回退场景实测 RuntimeError、P3-19 import 实测模块/函数区分）；边界复查=恰好 10 files 与申报一致、docs/prototype/检查点零改动；testVerdict=PASS）
- R2: committer APPROVED（2026-10-23，续接会话，报告原文见"最新验证意见原文"节；reviewedSha=55846be=HEAD 核验一致；P1×0 / P2×0——R1 两项 P2 修复正确且未引入新 P2；上轮意见处置核对表全过（2×P2 + 11×P3 已修 + 需求边界按拍板选项 A 关闭 + 其余按拍板豁免/移交）；新增 14 条 P3 记录性意见不阻塞——交付前建议：config.py:20 注释 connect.py→connection.py（**登记移交，approved 后不再改代码避免 SHA 失效**）、P3-14 moot 改记（supervised-coding 已在检查点执行）、可选补 3 条轻量回归测试（**登记移交 M0a-2**）；P3-13 `:memory:`/非 WAL 显式失败是有意收紧不建议弱化；需求边界无新增；调研借鉴检查：R2 修复增强 WAL/迁移实践吸收、无新增缺口；改名彻底性核查：功能彻底、仅 config.py:20 注释遗漏（P3））
- **终态校验（2026-10-23 supervised-coding）**：testVerdict=PASS + reviewVerdict=APPROVED + reviewedSha=testedSha=HEAD(55846be, develop_opencode) ✓ → status=approved，待用户确认交付

## 最新验证意见原文

- （暂无）

### Tester R1 报告原文（2026-10-23，testVerdict=PASS）

# M0a-1 验证报告（Tester round 1）

**testedSha**：`2152c6c0f820554d55d05dfc4cd5eb7623abdbc4`（开工前置校验 `git rev-parse HEAD` = testedSha ✓；工作区干净，仅检查点文件 untracked 属预期；git 全程只读）

## 一、复跑结果（独立复跑，knowledge-lattice/ 下）

| 命令 | 结果 |
|---|---|
| `uv run pytest` | **32 passed in 0.17s**（0 failed / 0 error / 0 skipped；Python 3.12.10、pytest 9.1.1，uv 托管解释器与 `.python-version` 钉版一致） |
| `uv run python -O -m pytest` | **32 passed, 1 warning in 0.16s** |

`-O` 模式 warning 原文：`PytestConfigWarning: assertions not in test modules or plugins will be ignored … (are you using python -O?)`——证明 assert 剥离确实生效于被测代码，此时 `test_pragma_failure_raises_runtime_error`（mock pragma 返回 0）仍通过 ⇒ `connect.py:32-33` 的检查为显式 `raise RuntimeError` 而非 assert，**design §3「非 assert（`python -O` 剥离）」纪律实证通过**。

复跑输出尾部（两模式）：
```
tests/test_scaf_01_foreign_keys.py ....    [ 43%]
tests/test_scaf_02_pragmas.py ...          [ 53%]
tests/test_scaf_03_migrations.py ....      [ 65%]
tests/test_scaf_04_triggers.py .........   [ 93%]
tests/test_scaf_05_membership_cleanup.py .. [100%]
============================== 32 passed in 0.17s ==============================
======================== 32 passed, 1 warning in 0.16s =========================
```

## 二、逐条勾验结果表（TC-SCAF-01~05）

| 用例 | 判定 | 断言覆盖证据（测试文件:行号） | 独立旁证 |
|---|---|---|---|
| **TC-SCAF-01** foreign_keys 每连接生效 + 孤儿行拒绝 | **通过** | ① `PRAGMA foreign_keys==1`（test_scaf_01_foreign_keys.py:19-20）；② `user_dimension_grants` 孤儿行 `IntegrityError` match "FOREIGN KEY"（:23-32）；③ `document_dimensions` 孤儿行（:35-44）；④ 工厂 pragma 失败 → `RuntimeError` mock 断言（:47-73）。§六 M0a 验收句「插孤儿行断言 IntegrityError」覆盖 ✓。**PG 臂**：用例后端行标注「M0a 仅 SQLite」+ 口径段 v1.3.2（CI 必跑 PG 自 M0b 起）——M0b 范围，见第五节 skip 说明 | 直查 `PRAGMA foreign_keys` 返回 1；孤儿 INSERT 实测 IntegrityError |
| **TC-SCAF-02** PRAGMA 全集 + sqlite-vec | **通过** | `wal`/`5000`/`1(NORMAL)`/`1` 逐项断言（test_scaf_02_pragmas.py:13-17）；`vec_distance_cosine(vec_f32,vec_f32)` 可调用且同向量距离<1e-6（:20-25，known-gaps G-11 收窄动作①）；附带第二连接全集依旧＝每连接生效（:28-38） | connect.py:26-30 与 design §3 伪码（design.md:194-202）逐项一致 |
| **TC-SCAF-03** 迁移框架 | **通过** | ① 正常迁移后 `foreign_key_check` 空、user_version=1、16 表全落（test_scaf_03_migrations.py:82-105）；「建新表→拷数据→删旧表」v2 迁移跑通 + 结束 fk_check 空 + 外键恢复（孤儿行仍拒，:129-156——窗口关外键由「DROP 被引用表成功」机制性证明）；② 窗口注入脏行 → `MigrationError` match foreign_key_check → user_version 不前进 / DDL 未生效 / 数据不动 / finally 恢复外键 ON（:159-201）；③ 幂等重跑 `applied==[]` 无重放副作用（:108-126） | migrate.py:84-104——BEGIN IMMEDIATE + user_version 同事务前进 + 窗口在事务外关外键 + 违例 ROLLBACK + finally 恢复；独立建库 user_version=1、fk_check 空 |
| **TC-SCAF-04** DDL 防护触发器全集 | **通过** | ① 12 触发器存在性集合断言（test_scaf_04_triggers.py:27-44），用例清单逐名核对无缺（含 `trg_membership_no_extend`）；audit_no_update/delete **不在主库**边界断言（:46-47）；② 行为断言：dimval value+dimension_id 双字段 ABORT、label 可改（:50-59）；三表 org_id ABORT（:68-80）；ds_org_check ABORT（:83-93）；跨组织搬库 ABORT + 同组织换库合法（:96-108）；docdims_consistency value≠dimension / org≠doc / 反向三分支 ABORT + 一致行合法（:111-148）；`uq_chunks_docver` 同版本 seq 重复拒 + 跨版本同 seq 合法（:178-188）；chunks_ai/ad/au FTS 同步（:191-214）；附带 T23 触发器半句（:151-175，§六 M0a 行要求） | 独立 DB 旁证：12 触发器逐一实测 ABORT 且消息与 design §4 逐字一致；uq_chunks_docver 经 `PRAGMA index_info` 证实为 UNIQUE(doc_id,version,seq) |
| **TC-SCAF-05** membership 删除级联清授权 | **通过** | 删 org:tax membership → tax 授权全清**含 `source='sync:hr'`**（test_scaf_05_membership_cleanup.py:41-48）；org:gl 授权保留＝按 `dimensions.org_id` 收敛 ✓（:48）；附带按 OLD.user_id 收敛（u2 保留，:51-65） | 独立 DB 旁证：CLEANED + TAX-KEPT |

**通过 31/32 涉及 TC-SCAF 直接对应的 22 条用例断言全部通过；失败 0**（其余 10 条为月库/协议契约/log 骨架配套，均通过，其中月库断言支撑 TC-SCAF-04 的 audit 边界）。

## 三、边界符合性抽查结论

1. **sem_* 不在主库 schema v1** ✓：迁移后 `sqlite_master` 无任何 `sem_` 前缀表（独立旁证 `sem_tables_present: []`）；0001_schema_v1.sql 无 sem_* DDL；`migrations/semantic/` 目录空占位就绪（M2-S1 落库）。
2. **audit append-only 触发器不在主库（属月库）** ✓：主库无 `audit_events` 表、0 个 `audit_*` 触发器；月库 `audit_YYYYMM.db` 由连接工厂滚动创建（audit.py），含 `audit_events` + `audit_no_update`/`audit_no_delete`，UPDATE/DELETE 实测 ABORT、消息与 design §4（:486-489）逐字一致；滚动幂等（IF NOT EXISTS + 进程缓存）与跨月分文件（audit_202610.db/audit_202611.db）有测试且通过。
3. **DDL/触发器与 design §4 逐项对照** ✓：16 表（15 常规表 + `chunks_fts` FTS5 虚表，列级一致）、6 索引（idx_grants_dim / idx_documents_hash / uq_chunks_docver / idx_chunks_vec_pending（含 tombstone 谓词）/ idx_qflags_doc / idx_tasks_status）、12 触发器 SQL 文本与 design §4 / §5.1 逐字一致，仅两处**执行层修正且均注释注明、语义一致**：
   - `trg_docdims_consistency` 移至 `document_dimensions` 建表后（SQL:137-138 注释）——CREATE TRIGGER 要求目标表已存在，design §4 排版顺序不可直接执行；
   - FTS 触发器插入目标列 `rid`→`rowid`（SQL:198-199 注释，值仍为 new.rid/old.rid）——FTS5 虚表 INSERT 列名只认 rowid，实测 FTS 同步（ai/au/ad）正常。
   - `trg_membership_no_extend` 源自 design §5.1（design.md:652-655）逐字一致，属文档侧 DDL 范围，落位正确。
4. **`uq_chunks_docver` 唯一索引语义** ✓：UNIQUE(doc_id, version, seq)；同文档同版本 seq 重复被拒、**不同版本同 seq 合法**（含 version——#34 4.4）双臂断言 + 独立旁证。
5. **连接工厂纪律** ✓：四 PRAGMA + 显式 RuntimeError（非 assert，-O 实证）+ vec_distance_cosine 可调用断言（G-11 动作①）+ 月库滚动；连接失败路径无 assert 残留（代码审读）。

## 四、skip 数量与理由

**0 skipped**（32 条全部实跑）。TC-SCAF-01 用例后端标注 `both`，PG 臂未实现——依据用例文档后端行「both（M0a 仅 SQLite）」、口径段 v1.3.2（本地无 DSN 可 skip、CI 必跑 PG job 自 M0b 建立起生效）与任务边界（「PG DDL 与 spike——M0b」），属**里程碑范围划分而非用例级静默 skip**；`store/postgres/` 为显式 M0b 占位。M0b 起 PG 参数化落地时需回归本组。

## 五、结论

- 失败项：**无**（无 IMPL_BUG / TEST_BUG / CASE_BUG；未发生测试修复，tests/ 零改动，业务代码零改动，检查点文件零改动）
- **testVerdict: PASS**
- testedSha：`2152c6c0f820554d55d05dfc4cd5eb7623abdbc4`

---

报告完毕。补充说明两点供 supervised-coding 参考：

1. **两处执行层修正**（trg_docdims_consistency 位置、FTS 触发器 rowid 列名）已在 0001_schema_v1.sql 内注释注明并经实测验证语义等价——design §4 原文排版在这两点上不可直接执行，建议随 M0b 收口时在 known-gaps 或 design 勘误中登记一笔（非本验收阻塞项）。
2. `-O` 模式的 PytestConfigWarning 是预期现象（证明 assert 剥离生效），不构成失败。

### Committer R1 报告原文（2026-10-23，reviewVerdict=NEEDS_CHANGES）

# knowledge-lattice M0a-1 审查报告（Committer round 1）

**审查对象**：commit `2152c6c0f820554d55d05dfc4cd5eb7623abdbc4`（HEAD）
**审查基线**：`git diff origin/develop..HEAD`（43 files，+1983 行；commit 父提交 `93dcd6a`）
**审查方式**：全量只读审阅 43 个文件 + design §3/§4/§5.1/§7/§8 + TEST-CASES TC-SCAF-01~05 + known-gaps G-6/G-11 + `research/enterprise-rag/` 相关沉淀；未修改任何代码/文档/检查点。受环境命令权限限制，本轮未独立复跑 pytest，测试结论以 tester 的独立复跑报告 + 静态核对为准。

**开工前置校验**：`git rev-parse HEAD` = `2152c6c0f820554d55d05dfc4cd5eb7623abdbc4` = 检查点 `testedSha` ✓；工作区干净（仅检查点文件 untracked，属预期）；`docs/` 与 `prototype/` 零 diff ✓；未 push ✓。

---

## 一、结论

```text
reviewVerdict: NEEDS_CHANGES
```

- **P1：无。**
- **P2：2 项**（迁移框架并发正确性 1 项；测试失败路径证据不成立 1 项）。
- **P3：若干**（健壮性/边界/测试强度/记录性，均不阻塞主验收，建议随 R2 或移交事项处理）。
- **需求边界问题：有 1 项**（M0a-1 是否必须落 backend 参数化骨架——属规格口径歧义，非代码错误，交 supervised-coding 回 spec 确认）

---

## 二、需求边界问题（完整描述）

### 结论：有 1 项，属规格口径歧义，非代码错误

**涉及条目一（任务原文，检查点 `task-knowledge-lattice-m0a-1.md:35`）**：

> StorageBackend 协议 + AclPlan 结构化产物类型 + 嵌入/重排 provider 接口（D12/D24——协议与数据结构定义 + SQLite 实现先行；AclPlan 编译器逻辑与渲染器属 M0a-2，本任务不实现；**测试自 M0a 起按后端参数化，本地无 DSN 可 skip**——CI 必跑 PG 自 M0b job 建立起生效，**M0a 期间仅 SQLite 后端验收**）

**涉及条目二（同一检查点验收表 `:44`）**：

> TC-SCAF-01 …… **both（M0a 仅 SQLite）**

**涉及条目三（任务边界 `:50`）**：

> 边界（本任务不做）：…… **PG DDL 与 spike（M0b）**

**涉及条目四（`docs/TEST-CASES.md:6` 口径段）**：

> 存储后端参数化（v1.3，D24；v1.3.2 修订）：涉及持久化与召回 SQL 的用例按 `backend ∈ {sqlite, pg}` 参数化双跑……本地无 DSN 可 skip、不阻塞纯 SQLite 环境，**CI 设必跑 PG job（docker postgres+pgvector）——CI 内 skip 视为失败**

**涉及条目五（`docs/TEST-CASES.md:51`，TC-SCAF-01 后端行）**：

> 后端：both——PG 侧外键违例同断言（异常类型按后端适配：psycopg 外键错误码，断言语义不变——v1.4 标注，#42 必修4）。

### 实现现状

- `tests/conftest.py:21-28` 只提供 SQLite `conn` fixture（`connect(db_path)` + `migrate`），没有 `backend` fixture、没有 `pytest.mark.parametrize`、没有 PG 分支的 `pytest.skip`。
- TC-SCAF-01~05 全部直接使用 `sqlite3.Connection` / `helpers` 的 SQLite SQL；TC-SCAF-01 没有 PG 臂，也没有声明"本地无 DSN 时 skip"的骨架。
- tester R1 报告的判定是："0 skipped——PG 臂属 M0b 范围划分非静默 skip"；其依据是任务"M0a 期间仅 SQLite 后端验收"与 TC-SCAF-01 的"both（M0a 仅 SQLite）"。

### 为什么是歧义而不是直接的实现缺陷

两句话可以同时成立、但落点不同：

- **读法 A（tester 采用）**："both"是最终后端覆盖目标；"M0a 期间仅 SQLite 后端验收"意味着 M0a-1 不要求 PG 臂，参数化骨架也随 M0b PG spike 落地。按此读法，当前实现**通过**。
- **读法 B（严格读"测试自 M0a 起按后端参数化"）**：M0a-1 就应至少落 **backend 参数化骨架**（SQLite 参数实跑 + PG 分支无 DSN 时 `pytest.skip`），即使 PG 实现为空；CI 的 PG job 自 M0b 起生效，但"测试自 M0a 起按后端参数化"是独立要求。按此读法，当前 `tests/` **缺参数化骨架**，是 P2 实现缺口（不是当前 SQLite 验收失败）。
- **读法 C**：M0a-1 就要落 PG 等价断言——这与任务边界"PG DDL 与 spike（M0b）"直接冲突，应排除。

### 建议选项（交 supervised-coding 回 spec 确认，不直接要求 coder 修）

1. **选项 A（建议优先确认）**：明确 M0a-1 仅要求 SQLite 验收，backend 参数化骨架延至 M0b PG spike；则当前实现通过，但需在检查点验收记录/遗留事项写明"TC-SCAF-01 的 PG 臂为 M0b 激活项，R1 的 0 skipped 是里程碑范围而非静默 skip"，避免后续把"参数化"误读为已覆盖。
2. **选项 B**：确认"测试自 M0a 起按后端参数化"是 M0a-1 的硬要求；则转为 coder finding（P2）：在 `tests/conftest.py` 增加 `backend` fixture（`sqlite` 参数实跑，`pg` 参数在无 DSN 时 `pytest.skip`），TC-SCAF-01 增加 PG 分支/skip 骨架，并在验收记录注明 CI 的 PG job 自 M0b 起生效。
3. **选项 C**：要求 M0a-1 落 PG 等价断言——不建议，违反"PG DDL 与 spike（M0b）"边界。

### 其他边界口径（不构成需求边界问题）

- **审计月库行为**：任务边界写"审计月库行为断言（TC-OPS-02，M2）"。`tests/test_monthly_audit_db.py:31-45` 提前断言了月库 `audit_events` 的 UPDATE/DELETE ABORT；这是对**本轮 in-scope 月库 DDL**（`audit.py:14-32`）的机制验证，且测试 docstring 已排除封存/哈希链/保留期等 M2 行为，**不构成越界实现或验收矛盾**；建议验收记录标注"提前覆盖，不据此宣称 TC-OPS-02 已验收"。
- **检查点"9 个测试文件"**：实际 `knowledge-lattice/tests/` 为 **10 个文件**（8 个 `test_*.py` + `conftest.py` + `helpers.py`）；属检查点元数据笔误（P3 记录），不影响验收。
- **`requires-python >=3.11` vs 任务"Python 3.12.10"**：`.python-version:1` 已钉 3.12.10，且 G-11 明确要求 `requires-python` 钉 `>=3.11`、部署钉 3.12；**无矛盾**。

---

## 三、P2 × 2 逐条详情

### P2-1｜迁移框架并发竞态：`user_version` 检查在 `BEGIN IMMEDIATE` 之外

**文件:行号**：
- `knowledge-lattice/src/knowledge_lattice/store/sqlite/migrate.py:74`（`current = conn.execute("PRAGMA user_version").fetchone()[0]`）
- 同文件 `:84-104`（`_apply_one`，尤其 `:88` `BEGIN IMMEDIATE`、`:98` `PRAGMA user_version = ...`、`:99` `COMMIT`）

**问题**：

`migrate()` 在循环外读取一次 `user_version`，然后对每个 `m.version > current` 的迁移调用 `_apply_one()`；`_apply_one()` 才在 `:88` 取得 `BEGIN IMMEDIATE` 写锁。也就是说，**版本判定发生在写锁之外**。并发场景（设计 §2 的"主进程 ×1 + worker 子进程 ×1"、SQLite 单写者模型）下：

1. 进程 A、B 同时 `migrate()`，都读到 `user_version=0`；
2. A 取得 `BEGIN IMMEDIATE`，执行 `0001_schema_v1.sql`，`COMMIT`，`user_version=1`；
3. B 在 `BEGIN IMMEDIATE` 上等待（`busy_timeout=5000`），A 提交后 B 获得写锁；
4. B 仍按循环开始时的 `current=0` 执行 `0001`，第一条 `CREATE TABLE orgs` 就抛 `sqlite3.OperationalError: table orgs already exists`；`_apply_one` 回滚并原样抛出（未包装为 `MigrationError`），**B 启动失败**。

`BEGIN IMMEDIATE` 的意图是串行化写者，但当前只串行化了 DDL，**没有串行化"检查版本 + 应用迁移"这一整体**，所以 `user_version` 只前进/幂等的保证在并发下不成立。TC-SCAF-03 只测单连接，无法暴露该问题；tester 的 32 passed 也不覆盖并发。

**建议修法**（最小改动，保持"每迁移一个事务"）：

```python
def _apply_one(conn, m) -> bool:
    ...
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # 关键：在写锁内重读，防止并发进程已推进
            current = conn.execute("PRAGMA user_version").fetchone()[0]
            if current >= m.version:
                conn.execute("COMMIT")
                return False          # 已被其他进程应用，跳过
            for stmt in statements:
                conn.execute(stmt)
            ...
            conn.execute("COMMIT")
            return True
        except BaseException:
            ...
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
```

`migrate()` 改为仅当 `_apply_one()` 返回 `True` 时 `applied.append(m.version)`；循环外的 `current` 读取可保留为快速路径，但**不能作为唯一判定**。补偿测试建议：两条连接/两个线程在 `migrate()` 前用 barrier 对齐，或对 `_apply_one` 的重读分支做单测（已预先应用 v2 的库上再跑 v2，断言返回 `False` 且无 "table already exists"）；至少保证并发下第二个进程**干净跳过**而不是崩溃。

**严重度理由**：不是数据损坏（第二个进程回滚，库仍由第一个进程正确迁移），但会让多进程启动之一崩溃，且违反迁移框架本身"幂等/只前进"的核心承诺；属 P2（应修），不属 P1。

### P2-2｜TC-SCAF-03 失败回滚测试的"finally 恢复外键"证据不成立

**文件:行号**：
- `knowledge-lattice/tests/test_scaf_03_migrations.py:191-194`（注释"回滚后外键恢复 ON（finally 语义）"→ 手动 `PRAGMA foreign_keys = OFF` → `DELETE ...` → `PRAGMA foreign_keys = ON`）
- 同一测试 `:159-201`；对照成功路径 `:129-156`（`:149-155` 的孤儿行断言）

**问题**：

`test_migration_fk_violation_detected_and_rolled_back` 在 `pytest.raises(MigrationError, match="foreign_key_check")`（`:182-183`）之后，**先手动把外键关掉、删除注入行、再手动打开**，然后才做孤儿行插入断言（`:195-200`）。因此：

- 如果 `migrate.py:103-104` 的 `finally: PRAGMA foreign_keys = ON` 被删除，这个测试**仍然会通过**——因为测试自己最后执行了 `PRAGMA foreign_keys = ON`；
- 该测试的注释和 tester 报告中"finally 恢复外键 ON（:159-201）"的验收证据**不成立**；
- 成功路径测试 `:149-155` 确实覆盖了同一个 `finally`（成功迁移后的孤儿行被拒），所以**代码本身没有回归证据缺失**；缺的是**失败路径**的断言，以及报告对证据的准确描述。

**建议修法**：

1. 在 `pytest.raises` 之后、任何手动切换之前加：
   ```python
   assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
   ```
   这就是 failure-path `finally` 的直接证据。
2. 清理注入行时**不需要**关闭外键（删除 `user_dimension_grants` 的脏行本身不触发外键约束），直接 `conn.execute("DELETE FROM user_dimension_grants WHERE user_id='ghost-user'")`；若保留 OFF/ON，也必须放在上述断言之后。
3. 可选加强：用第二条连接查 `PRAGMA foreign_keys`，验证"每连接生效"在失败路径也成立。
4. 顺手补 P3：回滚后断言 `trg_membership_delete_cleanup` / `trg_docdims_consistency` 已恢复（见 P3 清单），使"库态与迁移前一致"覆盖触发器集合，而非仅 `user_version`/`remark`/行数。

**严重度理由**：代码的 `finally` 存在且成功路径已覆盖；但这是一个**测试证据 P2**——验收报告引用了不成立的断言，且该断言保护的正是"迁移失败后不能把外键留在 OFF"的安全属性。修法仅测试改动，建议 R2 一并完成；若团队认为 success-path 已足够覆盖同一行 `finally`，可降为 P3，但**必须更正注释/tester 报告的"finally 证据"表述**。

---

## 四、P3 清单（逐条，含文件:行号）

以下均为建议级；P2 修复后可一并处理，或登记为移交事项。

**迁移框架健壮性**
1. `migrate.py:86`：`PRAGMA foreign_keys = OFF` 未校验；若连接已在事务中，该 PRAGMA 静默无效，随后 `DROP TABLE` 可能撞外键。建议在 `:86` 前检查 `conn.in_transaction` 并抛 `MigrationError`，或在设置后查询 `PRAGMA foreign_keys` 确认已为 0。
2. `migrate.py:100-102`：`except BaseException: conn.execute("ROLLBACK")`——若 SQLite 已自动回滚（如某些 I/O/损坏错误），`ROLLBACK` 会抛"no transaction is active"，覆盖原始异常。建议 `try/except sqlite3.Error: pass` 包裹 ROLLBACK，保留原始异常链。
3. `migrate.py:85-97`：SQL 语法错误/`OperationalError` 直接原样抛出，未包装为 `MigrationError`（docstring 只列"版本冲突 / SQL 不完整 / foreign_key_check 违例"）。建议统一包装或至少补充 docstring；非阻塞。
4. `migrate.py:107-121`：`_split_statements` 依赖"一行一条语句 + 结尾分号"；同一行两条 SQL、或文件末尾无分号的合法语句会报 `incomplete SQL tail`。建议在模块 docstring/迁移文件规范中写明，或增强切分器；当前 0001/测试 v2 均满足。
5. `migrate.py:74` 的初始 `user_version` 读取与 P2-1 同一处；修复 P2-1 时保留快速路径即可。

**TC-SCAF-03 测试强度**
6. `tests/test_scaf_03_migrations.py:185-189`：回滚断言只覆盖 `user_version`、`remark` 列、行数；未断言被 v2 迁移 `DROP` 的 `trg_membership_delete_cleanup` / `trg_docdims_consistency` 已随事务回滚恢复。建议断言 `{"trg_membership_delete_cleanup","trg_docdims_consistency"} <= trigger_names(conn)`。
7. `tests/test_scaf_03_migrations.py:104`：`assert [m.version for m in discover()] == [1]` 与当前迁移集耦合；未来添加 v2 时需改测试。可接受，建议注释"M0a-1 基线"。
8. `tests/test_scaf_03_migrations.py:91-99`：`expected <= names` 允许额外表；对向前兼容是优点，但无法发现"多建表"。可接受，若需严格可另加精确计数。

**TC-SCAF-04 / FTS 测试**
9. `tests/test_scaf_04_triggers.py:206-211`：`chunks_au` 用例只在初始 `keywords` 为空的情况下更新为"留抵退税"，只断言新词命中，未断言旧词移除；无法证明"先 delete 旧值再插入"。建议初始 `keywords="旧词"`，更新后断言 `fts_count('"旧词"') == 0` 且新词为 1；TC-FTS-03 详测仍归 M0a-2/M1。
10. `tests/test_scaf_04_triggers.py:56-57`：`UPDATE dimension_values SET dimension_id=?` 传入的是同一个 `dim_id`；虽然能验证 `UPDATE OF dimension_id` 子句包含该列，但不是真正的"跨维度搬移"。建议再建一个维度并尝试改到该维度，ABORT 语义更实。
11. `tests/test_scaf_04_triggers.py:151-175`：T23 触发器半句覆盖过期/未过期/NULL 三种；与 TC-SCAF-04 要求一致，无问题（记录为已覆盖）。

**连接工厂边界/健壮性**
12. `connect.py:32-33`（及 `:36` `ensure_monthly_audit`、`:42-46` 扩展加载）：失败路径未关闭已打开的 `conn`；`sqlite_vec.load` / `ensure_monthly_audit` 抛错时连接泄漏。建议 `try/except` 中 `conn.close()` 后再抛，且把扩展加载失败包装成 `RuntimeError`。
13. `connect.py:27-30`：只对 `foreign_keys` 做了显式检查；`journal_mode` 在 `:memory:`/不支持 WAL 的文件系统上会静默回退（返回 `"memory"`/`"delete"`），而 WAL 是设计 §2 并发模型的前提。建议至少校验 `journal_mode == "wal"`、`busy_timeout == 5000`、`synchronous == 1`，失败抛 `RuntimeError`（与任务"pragma 失败显式 raise"口径一致）。
14. `connect.py:36`：`ensure_monthly_audit(Path(path).parent)` 对 `:memory:`/URI 路径会把 `audit_YYYYMM.db` 建到当前工作目录；建议对 `:memory:`/`file:...mode=memory` 跳过月库，或显式接受 `db_dir` 参数。
15. `audit.py:34,42-51`：`_ensured` 进程缓存不检查文件是否仍存在；月库被轮转/删除后同进程不会重建。建议 `if key in _ensured and path.exists(): return path`，或在 `executescript` 失败时移除缓存。
16. `audit.py:39`：月库按 UTC 月份命名；若业务/封存按本地月，跨月边界会不一致。建议在 docstring 明确 UTC 口径，或配置时区；TC-OPS-02（M2）确认。

**协议/模块接口**
17. `backend.py:116-126`：`AdminBackend` / `SemanticBackend` 为空 Protocol；设计 §3 的方法种子（Admin CRUD/任务队列/上传凭证/审计查询；Semantic sync/build/L0）未体现。建议至少加入种子方法签名（`...`）或明确注释"M1/M2 填充，当前为保留域"，否则 `isinstance` 对任意对象恒真、协议无约束力。
18. `backend.py:134`：`roll_monthly(self, when: object | None = None) -> object` 过宽；建议 `datetime | None` / `Path`（或定义返回类型）。
19. `store/sqlite/__init__.py:11`：`from .migrate import migrate` 用函数覆盖了同名子模块属性；`import knowledge_lattice.store.sqlite.migrate` 在某些写法下会得到函数而非模块（现有 `from ...migrate import ...` 测试可用）。建议函数改名 `migrate_db` 或模块改名，消除 footgun。

**测试/配置小项**
20. `tests/helpers.py:128`：`dims_json` 默认 `"{}"`（对象），设计与 ACL 模板期望多值数组；建议 `"[]"`，避免未来 `json_each` 用例误用。
21. `tests/test_log_skeleton.py:14,34`：`setup_logging` 直接替换 root handlers，测试结束后不恢复；会影响后续测试/顺序依赖。建议 fixture 保存并恢复 `root.handlers[:]` 与 level。
22. `tests/test_scaf_01_foreign_keys.py:53-69`：mock 的 `inner` 真实连接未关闭；建议 `finally: inner.close()`（或让 wrapper 在 `pytest.raises` 后关闭）。
23. `config.py:15-54`：`get_settings` / `embed_model_label` 无测试；可选补 2 条轻量断言（非关键路径）。
24. `.opencode/workflows/task-knowledge-lattice-m0a-1.md:16,69`：写"9 个测试文件"，实际 `tests/` 10 个文件（8 个 test 模块 + conftest + helpers）；建议修正检查点元数据。
25. `tests/test_monthly_audit_db.py:31-45`：月库 append-only 行为断言属提前覆盖（TC-OPS-02 的封存/哈希链/保留期仍 M2）；建议在验收记录标注"机制验证，不构成 TC-OPS-02 验收"。

---

## 五、对 tester 两条补充说明的裁定

### 补充说明 1：两处执行层修正登记建议（trg_docdims_consistency 位置、FTS 触发器 rowid）

**裁定：采纳为移交事项（非阻塞，不需本轮改代码/改 design）。**

核实结论：

- **`trg_docdims_consistency` 移至 `document_dimensions` 建表后**（`0001_schema_v1.sql:137-138` 注释、`:148-152` 触发器）：design §4 原文把 `CREATE TRIGGER ... ON document_dimensions` 放在 `CREATE TABLE document_dimensions` 之前；SQLite 在 `CREATE TRIGGER` 时要求目标表已存在，原文顺序不可直接执行。移动后触发器 SQL 文本未变，语义等价。**成立。**
- **FTS 触发器列名 `rid`→`rowid`**（`0001:198-199` 注释、`:205-218`）：`content_rowid='rid'` 是把 FTS 的 `rowid` 映射到内容表 `chunks.rid`，不会让 FTS 虚表拥有名为 `rid` 的列；FTS5 的 INSERT 目标列必须用 `rowid`，值仍为 `new.rid`/`old.rid`；`chunks_ad`/`chunks_au` 的 `'delete'` 命令同样用 `rowid`。语义等价。**成立。**
- 结论：两处都是**执行层必要修正**，不是偏离设计语义；`test_scaf_04:191-214` 的 FTS 同步测试与 tester 的独立验证支持该结论。建议按 tester 意见，在 **M0b 收口时** 于 `docs/known-gaps.md`（活文档）或 design 勘误中登记一笔；本任务不改 `docs/`（冻结纪律），检查点"遗留事项"可加一条"M0b 登记两处执行层修正"。**采纳，不阻塞。**

### 补充说明 2：`-O` 模式 PytestConfigWarning 是预期现象

**裁定：认可，无动作。**

`python -O` 下 pytest 的 `assert` 会被剥离，pytest 自身发出 `PytestConfigWarning` 是预期；`connect.py:32-33` 的检查是显式 `raise RuntimeError`，tester 的 `-O` 复跑 32 passed 已实证不是 assert。CI 不应日常以 `-O` 运行 pytest；该次运行是验收证据步骤。**不构成失败项。**

### CASE_BUG 裁定

**未收到 tester 的 CASE_BUG 请求**（tester 报告明确"无 IMPL_BUG / TEST_BUG / CASE_BUG；tests/ 零改动"）。本轮不做 CASE_BUG 裁定，不扩大范围。

---

## 六、调研借鉴检查结论（对照 `research/enterprise-rag/`）

**对照文档**：`blog/10-build-kb-for-agent.md`（§3.2 SQLite 一把梭/中文 FTS/repository；§3.5 ACL 与审计；§五 数据模型）、`blog/04-vector-stores.md:91`（SQLite+sqlite-vec/FTS5 中文、WAL 多读单写）、`blog/03-chunking-indexing.md:139-149`（双路字段/加权字段/ACL 字段）、`dimensions/12-onerag-assessment.md:21`（append-only SQLite WAL 审计）、`design.md:1310`（jieba/trigram 风险）、`known-gaps.md:69-76`（G-5 WAL 备份口径）。

### 已吸收（本轮范围内）

| 调研沉淀 | M0a-1 落点 | 判定 |
|---|---|---|
| **SQLite 一把梭**：元数据 + FTS5 + sqlite-vec 同库；零新增组件、事务一致 | `0001_schema_v1.sql` 主库全量 DDL；`connect.py:26-30` WAL/busy_timeout/synchronous | **吸收**；`synchronous=NORMAL` 的崩溃安全边界已由 known-gaps G-5 登记 |
| **WAL 多读单写 + busy_timeout** | `connect.py:27-30`；`PRAGMA busy_timeout=5000` | **吸收**；但只对 `foreign_keys` 做显式断言（P3-13） |
| **中文 BM25：应用层 jieba 预分词后写入**（ragflow/ES 路线） | `chunks.title_seg`/`content_seg`（`0001:175-176`）、FTS5 五列外部内容表（`:201-218`） | **吸收主路径**；`unicode61` 只做兜底，符合调研"FTS5 默认分词对中文无效"的判断 |
| **FTS5 五列加权**：title 3 / content 1 / keywords 5 / llm_keywords 0.5~1 / tags 8 | `0001:196-197` 注释 + `:201-204` 列序；`bm25()` 权重留 M1 | **吸收（schema 层预埋）**；权重调用属 M1 |
| **BLOB + sqlite-vec 距离，不用 vec0；先 ACL 过滤后距离** | `chunks.embedding` BLOB（`0001:185`）、`idx_chunks_vec_pending`（`:193`）、`connect.py:40-54` `vec_distance_cosine` 断言 | **吸收**；与 design §4 的 P0-1 一致 |
| **强类型 schema + 正文常驻 + 向量可外移** | `chunks` 全字段、`content` 不进 FTS、`embedding` 可空、`embed_model` 钉版本 | **吸收**；与调研 blog/03 的"schema 两流派选强类型"一致 |
| **模型版本钉在每个 chunk** | `chunks.embed_model` + `config.embed_model_label` + `AclPlan.embed_model` | **吸收**（D12） |
| **raw_object_key / content_hash 作为真相锚点** | `documents.raw_object_key`/`content_hash`（`0001:107,119`） | **吸收** |
| **append-only 审计 + DB 触发器** | `audit.py:14-32` `audit_no_update`/`audit_no_delete`；主库不含 `audit_events` | **吸收**（月库）；保留期/封存/哈希链 M2 |
| **任务租约/心跳表** | `tasks` 表 `lease_owner`/`lease_until`/`heartbeat_at`（`0001:236-249`） | **吸收** |
| **ACL 前置过滤（查询时引擎内过滤）** | `AclPlan` + `read_membership`/`read_grants`（`backend.py:19-56,104-112`） | **类型层就位**；编译/渲染 M0a-2 |
| **repository 接口收口存储** | `StorageBackend` 六域组合（`backend.py:62-149`） | **吸收且细化**：比调研的 3 方法 repository 更防 God interface（design §3 v0.8.3 明确）；Admin/Semantic 为空见 P3-17 |
| **迁移重建窗口 + foreign_key_check** | `migrate.py:84-104`；TC-SCAF-03 机制性验证 | **吸收**；并发版 P2-1 |
| **连接工厂集中 PRAGMA/扩展加载** | `connect.py:21-54`（WAL/busy_timeout/foreign_keys/synchronous/sqlite-vec/月库） | **吸收**；边界/错误路径 P3-12~14 |

### 未吸收但属后续里程碑（已登记，不构成本轮 finding）

| 调研沉淀 | 去向/依据 | 结论 |
|---|---|---|
| **FTS5 中文 trigram 兜底**（调研 blog/04:91、blog/10:87） | design §10 `:1310`"tokenizer 独立模块（可换 trigram/自定义词表）；M1 真实 query 标注集是判据"；M1 | **延后合理**；建议 M1 的 TC-FTS 用例把 trigram/自定义词表作为判据落地，M0a-1 无需改 DDL（P3 记录） |
| **备份 `VACUUM INTO` / 复制文件**（调研 blog/10:87） | design §3 `backup.py`；M2 TC-OPS-05；known-gaps G-5 已警告"只 cp 主库不拷 -wal 会丢最近事务" | **延后合理**；M0a-1 无 backup.py，非缺失 |
| **审计定长保留/封存/哈希链**（quivr 实践，`dimensions/12:21`） | design §4 注 + M2 TC-OPS-02；`audit.py` docstring 已声明 | **延后合理**；本轮只落表+触发器 |
| **RRF k=60 / BM25 权重调用 / rerank**（调研 blog/10:103） | M1 检索配方；`SearchBackend` 仅协议种子 | **不在本轮** |
| **ACL 随索引摄入、rerank 前兜底**（调研 blog/10:107-114） | M0a-2/M1；`AclPlan` 已定型 | **不在本轮** |
| **tokenizer.py（jieba 预分词器）** | M0a-2；`content_seg`/`title_seg` 列已就位 | **不在本轮** |
| **PG + pgvector + `schema_migrations`** | M0b；`store/postgres/` 占位；G-6 | **不在本轮** |
| **`acl_entries` 用户级临时共享** | design D22 预留；表已建、未启用 | **按设计** |

### 调研借鉴结论

M0a-1 在本轮范围内**吸收了调研沉淀的主要实践**：SQLite 一把梭 + WAL/busy_timeout、FTS5 五列 + jieba 预分词字段、BLOB+sqlite-vec、强类型 schema + 模型版本钉死 + raw_object_key/content_hash、append-only 审计触发器 + 月库、任务租约/心跳、AclPlan 前置过滤类型、六域 repository 协议（优于调研的 3 方法单接口）。**未吸收项均为 design/known-gaps/TC 已分配的后续里程碑，不是 M0a-1 的缺失或越界。**

调研对照**新增的唯一本轮相关弱项**是：调研强调 SQLite **单写者 + WAL**，而迁移框架的版本检查在写锁外（P2-1），在多进程启动时会破坏"幂等/只前进"；以及连接工厂只断言 `foreign_keys`（P3-13），WAL 静默回退会削弱调研所依赖的并发模型。**没有新的需求决策变更需求**；trigram/backup/audit retention 等按 design 既有里程碑推进即可。

---

## 七、证据与限制

- 前置：`HEAD=2152c6c...=testedSha`；工作区仅检查点 untracked；`git show --name-status 2152c6c` 43 文件全在 `knowledge-lattice/`；`git diff --stat origin/develop..HEAD -- knowledge-lattice/docs knowledge-lattice/prototype` 为空（零改动）；commit 父提交 `93dcd6a`；未 push。
- 测试：tester R1 独立复跑 `uv run pytest` **32 passed / 0 skipped**、`uv run python -O -m pytest` **32 passed, 1 warning**；本轮未独立复跑（工具权限仅允许 git/gh），以上述报告 + 静态审阅为准。
- 本轮 P2/P3 均位于 tester 32 条用例覆盖之外（并发、failure-path FK 断言、测试强度、连接工厂边界），不否定 tester 的复跑结果，但否定"证据已完整"的表述。
- 修复建议顺序：**P2-1（并发）→ P2-2（测试断言）→ 需求边界回 spec（A/B）→ P3 择要**。P2 修后请 tester 复跑并补并发/failure-path 断言；若需求边界选 B，则参数化骨架一并进 R2；若选 A，请把"PG 臂 M0b 激活、0 skipped 非静默 skip"写入验收记录。

**报告完毕。**

### Tester R2 报告原文（2026-10-23，testVerdict=PASS）

# M0a-1 验证报告（Tester round 2——回归验证）

**testedSha**：`55846be0160ee1c0d7d4f6819254fe91e1e15eca`（开工前置校验 `git rev-parse HEAD` = testedSha ✓；工作区干净，仅检查点文件 untracked 属预期；git 全程只读）

## 一、复跑结果与回归结论

| 命令 | 结果 |
|---|---|
| `uv run pytest` | **34 passed in 0.25s**（0 failed / 0 error / 0 skipped；= R1 的 32 + P2-1 补偿测试×2，与 coder 申报一致） |
| `uv run python -O -m pytest` | **34 passed, 1 warning in 0.18s**（warning 为预期 PytestConfigWarning——assert 剥离生效而 RuntimeError 检查仍全过） |
| 全量加跑 2 轮抖动复核 | 34 passed × 2（累计 4 轮全量全绿） |
| 并发单测连跑 8 轮 | `1 passed, 5 deselected` × **8/8**（test_scaf_03_migrations.py::test_concurrent_migrate_both_processes_survive） |

**回归核对（diff tests/ 全量审阅，`git diff 2152c6c..HEAD`）——R1 已勾验的 TC-SCAF-01~05 断言无弱化/删除**：
- `test_scaf_01`：仅 mock 包装加 try/except 关闭真实连接（P3-22），4 条断言原样保留；
- `test_scaf_02`、`test_scaf_05`、`test_monthly_audit_db`、`test_backend_contract`：**零改动**；
- `test_scaf_03`：4 个 R1 测试断言全部保留（user_version/fk_check/16 表/幂等/回滚四要素原样）；唯一删除段 = R1 被 committer P2-2 标记的「手动 OFF→DELETE→ON」清理（**修复对象本身，非断言弱化**），替换为更强的失败路径证据（见下）；新增 2 个并发补偿测试；
- `test_scaf_04`：dimval 用例由「同维度自赋值」升级为**真跨维度搬移**（P3-10，更强）；chunks_au 增加**旧词归零**断言（P3-9，更强）；其余 7 个测试零改动；
- `helpers.py`：`dims_json` 默认 `"{}"→"[]"`（P3-20）——无任何测试断言依赖旧值，与 D19 多值数组语义对齐，非弱化。

## 二、修复项逐条勾验表

| 修复项 | 判定 | 证据 |
|---|---|---|
| **P2-1** 迁移并发竞态 | **通过** | migrate.py:104-108——`_apply_one` 在 `BEGIN IMMEDIATE` **写锁内重读** user_version，`>=` 即 `COMMIT + return False` 干净跳过；`migrate_db`（:85-86，已改名）仅 True 记入 applied。**补偿测试①**（test_scaf_03:219-241）：第二条连接真实应用 v2 后，绕过快速路径直调 `_apply_one(conn, v2)` 断言 `is False` 且 user_version==2——若 DDL 被重放会抛 `OperationalError` 令测试失败，等价覆盖「无 table already exists」。**补偿测试②**（:244-272）：双连接 `threading.Barrier(2)` 对齐并发 `migrate_db`，断言 `failures == []`（双方存活）且 `flattened == [1, 2]`（每版本恰好应用一次）；实测连跑 **8/8 全过** |
| **P2-2** 失败路径外键证据 | **通过** | test_scaf_03:191-195——`pytest.raises(MigrationError, match="foreign_key_check")` 后**立即**断言 `PRAGMA foreign_keys == 1`，此前无任何手动 PRAGMA（R1 的手动 OFF/ON 清理段已整体删除，:206 清理 DELETE 直接执行且不触发外键）——`finally: PRAGMA foreign_keys = ON` 的失败路径证据成立 |
| 连带① connection.py 改名 | **通过** | git name-status：`D connect.py` + `A connection.py`（实质改名）；`connect` 函数名 design §3 钦定保留（connection.py:30）；docstring 注明改名缘由 |
| 连带② 连接工厂并发缺陷 | **通过** | connection.py:39 busy_timeout **最先**设置（纯连接级、永不遇库锁）；:43-52 journal_mode **先查后设**（已是 wal 跳过）+ `OperationalError` 时 5×渐进重试（`0.05s×(attempt+1)`）；补偿测试②的并发场景即其真实覆盖场景（8/8 稳定） |
| P3-1 外键 OFF 复核 | **通过** | migrate.py:95-100——OFF 设置后复查 `!= 0` 抛 `MigrationError`；**实测**：连接处于事务中（OFF 静默无效）→ `"migration 0001 (schema_v1): PRAGMA foreign_keys=OFF failed (connection in transa..."` |
| P3-2 ROLLBACK 防御 | **通过** | migrate.py:122-125——`try: ROLLBACK except sqlite3.Error: pass`，保留原始异常链 |
| P3-6 触发器恢复断言 | **通过** | test_scaf_03:197——回滚后 `{"trg_membership_delete_cleanup","trg_docdims_consistency"} <= trigger_names(conn)` |
| P3-9 chunks_au 旧词归零 | **通过** | test_scaf_04:206-215——INSERT 时带 `keywords="旧词"`（断言 FTS=1），UPDATE 后新词=1 且 **`fts_count('"旧词"')==0`**——证明 au 先 'delete' 旧值再插入 |
| P3-10 真跨维度搬移 | **通过** | test_scaf_04:52-59——新建 tax_type 维度，`UPDATE dimension_values SET dimension_id=<dim2>` 真实跨维度搬移 → ABORT |
| P3-12 失败关连接 + 扩展加载包装 | **通过** | connection.py:69-71——`except BaseException: conn.close(); raise`（任何失败路径不泄漏连接）；:83-84 扩展加载 `except Exception → RuntimeError` 包装；`:memory:` 场景实测 RuntimeError 路径真实走过 close |
| P3-13 PRAGMA 全集校验 | **通过** | connection.py:56-65——journal_mode/busy_timeout/synchronous/foreign_keys 逐项复查、失败显式 RuntimeError；**真实 WAL 回退场景实测**：`connect(":memory:")` → `RuntimeError: journal_mode pragma failed: 'memory' != 'wal'`（不再是静默回退） |
| P3-19 `__init__` footgun | **通过** | `__init__.py` re-export `connect`/`migrate_db` 与子模块名（connection/migrate）全部错开；**import 实测**：`pkg.migrate` 是 **module**、`pkg.connect` 是 **function**、`pkg.migrate_db is migrate.migrate_db`、`pkg.connect is connection.connect`——覆盖 footgun 消除 |
| P3-20 dims_json 数组 | **通过** | helpers.py:128 `"[]"` + 注释（D19 多值数组） |
| P3-21 log 测试恢复 | **通过** | test_log_skeleton.py `_root_logging_state` fixture——保存并恢复 `root.handlers[:]` 与 `root.level`，两个测试均挂载 |
| P3-22 mock 连接关闭 | **通过** | test_scaf_01:61-74——包装失败时 `inner.close()` 后 raise |

## 三、改名机制验证（验收动作 4）

`from knowledge_lattice.store.sqlite.connection import connect` ✓ 可导入；包级旧形态 `from knowledge_lattice.store.sqlite import connect, migrate_db` ✓ 可用（向后兼容）；`import knowledge_lattice.store.sqlite.migrate` 得到的是**模块**而非函数 ✓。tests/ 内全部调用点已随改名更新（conftest/test_scaf_01/03），`python -O` 模式 34 passed 证明 RuntimeError 断言不受改名影响。

## 四、边界复查（验收动作 5）

`git diff 2152c6c..HEAD --name-status` = **恰好 10 files**，与 coder 申报一致：`store/sqlite/{__init__.py, connect.py(D), connection.py(A), migrate.py}` + `tests/{conftest, helpers, test_log_skeleton, test_scaf_01, test_scaf_03, test_scaf_04}.py`——全部落在 `knowledge-lattice/src` 与 `tests/` 内。**docs/ 零改动、prototype/ 零改动、检查点文件零改动**（untracked 未入 commit）。未 push ✓。

## 五、结论

- 失败项：**无**（无 IMPL_BUG / TEST_BUG / CASE_BUG；本轮 tester 零文件改动）
- 回归结论：**R1 的 TC-SCAF-01~05 验收断言零回归**（全保留或加强），34 passed 双模式 + 并发 8/8 + 全量 4 轮稳定
- **testVerdict: PASS**
- testedSha：`55846be0160ee1c0d7d4f6819254fe91e1e15eca`

---

报告完毕。一条备注供 supervised-coding 参考：`git` 将 connect.py→connection.py 识别为 D+A 而非 R（rename）系内容改写超相似度阈值所致，实质为改名、不构成改动面超标；遗留事项清单中「验收记录注记（月库断言为机制验证非 TC-OPS-02 验收 / PG 臂为 M0b 激活项、0 skipped 属里程碑范围）」两项需在交付回写时落入检查点，本报告第五节口径与 R1 一致。

### Committer R2 复审报告原文（2026-10-23，reviewVerdict=APPROVED）

# knowledge-lattice M0a-1 R2 复审报告（Committer round 2）

**审查对象**：commit `55846be0160ee1c0d7d4f6819254fe91e1e15eca`（HEAD）
**审查基线**：`git diff 2152c6c..HEAD`（10 files，+269/−110）
**前置校验**：`git rev-parse HEAD` = `55846be...` = 检查点 `testedSha` ✓；工作区干净（仅检查点 untracked）；`docs/` 与 `prototype/` 零改动 ✓；未 push ✓；R2 只改 `knowledge-lattice/src` 与 `tests/` ✓。
**审查方式**：全量审阅 10 files 的 diff 与当前文件全文，逐条核对 R1 意见；对照 design §3/§4/§5.1/§8、TEST-CASES TC-SCAF-01~05、known-gaps G-6/G-11 及 `research/enterprise-rag/`；受环境命令权限限制，本轮未独立复跑 pytest，以 tester R2 报告 + 静态核对为准。

---

## 一、结论

```text
reviewVerdict: APPROVED
```

- **P1：0**
- **P2：0**（R1 两项 P2 均已修复，且修复未引入新的 P2）
- **P3：新增若干记录性意见**（不阻塞；见第四节）
- **需求边界问题：无新增**。R1 的 backend 参数化骨架歧义已按用户拍板**选项 A** 关闭（M0a-1 仅 SQLite 验收、参数化骨架移 M0b）；`connect()` 对 `:memory:`/非 WAL 文件系统的显式失败是 design §2/§3 既有 WAL 要求下的行为收紧，不构成需求边界矛盾（P3 记录，见 4.4）。

---

## 二、上轮意见处置核对表

| 上轮意见 | 处置 | 核对证据 |
|---|---|---|
| **P2-1** 迁移并发竞态（`user_version` 检查在 `BEGIN IMMEDIATE` 写锁外） | **已修** | `migrate.py:104-108` 写锁内重读 `locked_version`，`>=` 时 `COMMIT + return False`；`migrate_db:85-86` 仅实际应用才记入 `applied`；补偿测试 `test_scaf_03:219-241`（跳过分支）、`:244-272`（双连接 barrier 并发，8/8 稳定） |
| **P2-2** 失败路径"finally 恢复外键"证据不成立 | **已修** | `test_scaf_03:194-195` 在 `pytest.raises` 后、任何手动 PRAGMA 之前直接断言 `PRAGMA foreign_keys == 1`；R1 的手动 OFF/ON **清理段**已删除；`:206` 直接 DELETE 注入行（不需关外键） |
| **P3-1** 外键 OFF 复核 | **已修** | `migrate.py:95-100` 设置后复查 `!= 0` 抛 `MigrationError`；tester 实测"连接处于事务中"路径 |
| **P3-2** ROLLBACK 防御 | **已修** | `migrate.py:120-126` `try: ROLLBACK except sqlite3.Error: pass`，保留原始异常链 |
| **P3-6** 回滚后触发器集合断言 | **已修** | `test_scaf_03:196-197` 断言 `trg_membership_delete_cleanup`/`trg_docdims_consistency` 恢复 |
| **P3-9** `chunks_au` 旧词归零 | **已修** | `test_scaf_04:206-217` 初始 `keywords="旧词"`、断言旧词=1；UPDATE 后新词=1 且**旧词=0** |
| **P3-10** 真跨维度搬移 | **已修** | `test_scaf_04:52-59` 新建 `tax_type` 维度，`UPDATE dimension_values SET dimension_id=<dim2>` → ABORT |
| **P3-12** 连接工厂失败关连接 + 扩展加载包装 | **已修** | `connection.py:69-71` 外层 `except BaseException: conn.close(); raise`；`:75-84` 扩展加载 `except Exception → RuntimeError` |
| **P3-13** PRAGMA 全集校验 | **已修** | `connection.py:56-65` journal_mode/busy_timeout/synchronous/foreign_keys 逐项复查并抛出 `RuntimeError`；tester 实测 `:memory:` → journal_mode 回退 → RuntimeError |
| **P3-19** `__init__` 覆盖 footgun | **已修** | `__init__.py:13-15` re-export `connect`/`migrate_db`，子模块名为 `connection`/`migrate`；`pkg.migrate` 为模块、`pkg.migrate_db`/`pkg.connect` 为函数（tester import 实测） |
| **P3-20** `dims_json` 数组 | **已修** | `helpers.py:128` 默认 `"[]"` |
| **P3-21** log 测试恢复 | **已修** | `test_log_skeleton.py:10-21` `_root_logging_state` fixture 保存/恢复 root handlers 与 level |
| **P3-22** mock 连接关闭 | **已修** | `test_scaf_01:61-73` 包装失败 `inner.close()`；且 `connect()` 外层异常路径关闭 wrapper（MagicMock `wraps` 委托 `inner.close()`） |
| **P3-24** 检查点"9 文件" | **已修** | 检查点 `:16` 已改为 10 文件（8 test 模块 + conftest + helpers） |
| **需求边界问题（backend 参数化骨架）** | **按拍板豁免** | 用户拍板**选项 A**：M0a-1 仅 SQLite 验收，参数化骨架随 M0b PG spike（检查点 `:52`、`:67`）；验收记录注记 PG 臂为 M0b 激活项、0 skipped 属里程碑范围 |
| **P3-3/4/5/7/8/11/14/15/16/17/18/23/25** | **按拍板豁免/移交** | 检查点 `:69` 登记；其中 **P3-14**（`:memory:` 跳过月库）已被 P3-13 的全集 WAL 校验**实质取代**（`:memory:` 在 `ensure_monthly_audit` 之前就抛 RuntimeError），建议检查点将其改记为"moot/随 P3-13 关闭" |
| **未处置项** | **无** | 上轮 2×P2 + 11×P3 全部处置；其余按用户拍板移交 |

---

## 三、P2 修复质量复核（含边界）

### P2-1｜写锁内重读 + 干净跳过

**结论：修复正确，未引入 P2。**

- `migrate_db()` 循环外的 `user_version` 仅作快速路径（`migrate.py:80-84`）；最终判定在 `_apply_one()` 的 `BEGIN IMMEDIATE` 之后重读（`:104-108`），并发进程已应用则 `COMMIT + return False`，不重放 DDL。`applied` 仅在返回 `True` 时追加（`:85-86`），语义"本次实际应用"准确。
- **`BEGIN IMMEDIATE` + 空事务 `COMMIT` 合法性**：SQLite 允许只取写锁、不写任何页就 `COMMIT`；`test_apply_one_skips_when_version_already_applied`（`:219-241`）与双连接并发测试（`:244-272`，8/8）实际跑通，无 `cannot commit`/锁残留问题。
- **多迁移并发**：A 应用 v1、B 跳过 v1 后仍可在 v2 上竞争；`test_concurrent...` 的 `flattened == [1,2]` 覆盖"每个版本恰好应用一次"。
- **回归**：R1 的 `test_migrate_idempotent_rerun_no_side_effects`、`test_migration_rebuild_flow_with_fk_check`、`test_migration_fk_violation_detected_and_rolled_back` 的原有断言保留；`test_concurrent` 使用两个独立 `connect()` 连接，能触发连接工厂的 WAL 并发路径（连带的 connect 并发修复也因此被真实覆盖）。

### P2-2｜失败路径外键证据

**结论：修复正确，未引入 P2。**

- `:194-195` 的 `assert PRAGMA foreign_keys == 1` 位于 `pytest.raises` 之后、任何手动 PRAGMA 之前，直接证明 `migrate.py:127-128` 的 `finally` 在失败路径生效；R1 的"手动 OFF→DELETE→ON"清理段已删除，`:206` 的 DELETE 不需要关外键（删除引用行不触发外键检查）。
- **注意**：测试 `:181-188` 仍保留"手动 OFF→插入脏行→ON"的 **setup**，这是 TC-SCAF-03 步骤②要求的"经迁移窗口注入脏数据"，不是 R1 的问题段；该 setup 位于 `migrate_db` 调用之前，不会掩盖框架失败路径的 finally 断言。
- `:196-197` 的触发器集合断言把"库态与迁移前一致"扩展到被 v2 迁移 DROP 的两个触发器；`:199-203` 的 user_version/DDL/行数断言保留。

### P3-1/2/12/13/19 的修复质量

- **P3-1**：`migrate.py:95-100` 在 `PRAGMA foreign_keys=OFF` 后复查；若连接已在事务中会得到 1 并抛 `MigrationError`，避免了"静默无效 → DROP TABLE 撞外键"的误判。**边界**：该检查位于 `try/finally` 之前（见 4.2 第 5 条），但在有效连接上 `PRAGMA foreign_keys` 是连接级标志、不会因库锁失败；属防御性 P3，不是 P2。
- **P3-2**：`migrate.py:120-126` 的 ROLLBACK 保护正确；`raise` 保留原始异常，未被"no transaction is active"覆盖。
- **P3-12**：`connection.py:69-71` 覆盖 PRAGMA 失败、扩展加载失败、月库创建失败等所有路径；`test_pragma_failure` 的 MagicMock wrapper 也会经 `connect()` 外层 `conn.close()` 委托关闭真实 `inner`。
- **P3-13**：`connection.py:56-65` 的四项复查是**有意义的行为收紧**，不是误伤（详见 4.4）；`journal_mode` 先查后设 + 5×渐进重试是合理的并发启动修复。
- **P3-19**：`connection.py`/`__init__.py`/tests 三处命名自洽；`pkg.migrate` 为模块、`pkg.migrate_db` 为函数，旧 `migrate` 函数无残留调用点（grep 仅剩 `config.py:20` 的**注释**旧名，见 4.2）。

---

## 四、新引入问题

### 4.1 P1/P2

**无。** 未发现新的阻断项或应修项；R2 的改动集中在 P2/P3 修复与两处连带修复，未触碰 DDL/协议/配置语义。

### 4.2 P3（记录性，不阻塞）

1. **`knowledge-lattice/src/knowledge_lattice/config.py:20`**：注释仍写"值与 `store/sqlite/connect.py` 一致"，模块已改名为 `connection.py`。**改名不彻底（仅注释）**。建议改为 `connection.py`；无功能影响。这是本轮"改名彻底性"核查中唯一遗漏的引用点（其余调用点均在 tests/`__init__` 中，已更新）。
2. **`store/sqlite/connection.py:44`**：`journal_mode` 的**查询**在重试 try 之外（`try` 只包 `:48` 的设置）。若查询本身因独占/回滚日志模式锁抛 `OperationalError`，不会进入 5×重试而直接外层关闭。注释"查询不遇写锁"在 WAL 下成立，但首次 `delete→WAL` 切换窗口并非绝对；建议把查询+设置一起纳入重试，或至少捕获查询的 `OperationalError` 重试。属边界 P3（tester 8/8 未触发）。
3. **`connection.py:47-51`**：重试耗尽后 `raise` 的是 `sqlite3.OperationalError`，而 `:56-65` 的静默回退检查抛 `RuntimeError`。若严格按任务"pragma 失败显式 raise RuntimeError"的统一口径，建议把重试耗尽也包装为 `RuntimeError("journal_mode pragma failed: ...")`；当前调用方仍能感知失败，只是异常类型不一致。P3。
4. **`connection.py:7-9,56-65`（P3-13 误伤风险，重点回答）**：
   - **`:memory:`**：现在会在 `ensure_monthly_audit` 之前因 `journal_mode='memory' != 'wal'` 抛 `RuntimeError`。这是**有意收紧**——design §2/§3 与任务均要求 WAL；`:memory:` 不是生产主库形态。**生产/验收场景（文件型主库）不受误伤**，测试套件统一用 `tmp_path`，34 passed 证明 macOS APFS 的 WAL 可用。
   - **临时目录文件系统不支持 WAL**：会显式失败，这是设计要求的"不可静默回退"；若 CI 的临时目录是网络 FS/不支持 WAL 的文件系统，测试会失败——应把"CI 临时目录必须支持 WAL（本地盘）"写进测试环境要求，而不是放宽校验。**不建议为通过测试而弱化 P3-13**。
   - **只读库**：同样显式失败；连接工厂定位是主库读写入口，只读模式不在本轮范围。
   - **P3-14 已被取代**：检查点 `:69` 仍登记"`:memory:` 跳过月库"，但新校验在月库创建前就失败；建议把 P3-14 改记为"moot，随 P3-13 关闭"，并在 `connect()` docstring 明确"file-backed WAL-capable DB only"；若未来单测需要 `:memory:`，应使用裸 `sqlite3.connect` 或单独的测试工厂，而不是绕过工厂。
5. **`store/sqlite/migrate.py:95-100`**：`PRAGMA foreign_keys=OFF` 的复查位于 `try/finally` **之前**。若复查本身抛 sqlite 错误（有效连接上几乎不会，因该 PRAGMA 是连接级标志），FK 可能停在 OFF 且 `finally` 不执行。建议把"设置 OFF + 复查"一起移入 `try`（或包一层 `try/finally`），使"任何失败都恢复 ON"在代码结构上无条件成立。P3（防御性）。
6. **`migrate.py:127-128`**：`finally: PRAGMA foreign_keys=ON` 在连接仍处于**调用方事务**时是 no-op（如调用方先 `BEGIN` 再调 `migrate_db` 且 `BEGIN IMMEDIATE` 失败）。建议加 `if conn.in_transaction: ...` 的诊断/文档，或明确迁移框架要求"连接必须处于 autocommit"；当前正常路径（工厂 `isolation_level=None`）不受影响。P3。
7. **`tests/test_scaf_03_migrations.py:219-241`**：docstring 称"若 DDL 被重放会抛 `OperationalError`"并不准确——v2 测试迁移在已 v2 的库上重放时，`dimensions_new` 在首次迁移后已被 RENAME，重放会**重新创建** `dimensions_new` 并可能成功，不会必然抛 `table already exists`；真正能抓住缺少重读分支的是 `assert _apply_one(...) is False`。测试本身有效，建议更正 docstring，避免未来读者误以为靠异常兜底。P3（测试说明准确性）。
8. **`test_scaf_03_migrations.py:253-261`**：并发测试的 `c = connect(db_path)` 在 `try` **之外**；若 `connect()` 在并发 WAL 初始化中失败，异常不会被记录进 `results`，测试会以 `len(results)==2` 失败并打印线程异常，而不是清晰的"connect 失败"断言。建议把 `connect` 也放进 try 或单独记录。P3（测试卫生）。
9. **`test_scaf_03_migrations.py:219-241`**：跳过分支测试未断言 `_apply_one` 返回 False 后 `PRAGMA foreign_keys == 1`；建议补一行，覆盖 skip 路径的 finally。P3。
10. **P3-1/2/12/13/19 缺少**提交到仓库的回归测试**（tester 的 R2 报告是独立实测，非 test suite 内断言）：建议至少补 3 条轻量测试——①连接处于事务中时 `migrate_db` 抛 `MigrationError`（P3-1）；②`connect(":memory:")` 或 mock `journal_mode` 回退 → `RuntimeError` 且连接已关闭（P3-12/13）；③`pkg.migrate` 为模块、`pkg.migrate_db is migrate.migrate_db`、`pkg.connect is connection.connect`（P3-19）。P3（不阻塞本轮验收，但缺回归保护）。
11. **`.opencode/workflows/task-knowledge-lattice-m0a-1.md:16`**：`filesChanged` 仍列 `store/sqlite/connect.py`（已删除），未列 `connection.py`。交付证据 manifest 应与 HEAD 一致；建议改为 `connection.py`（R2 的 10-file diff 已由 tester 核对，但检查点字段仍是 R1 汇总）。P3 记录，交付前修正。
12. **`tests/test_scaf_03_migrations.py:268-271`**：`flattened` 假设所有 `results` 是 list；虽由 `failures` 先行断言保护，若未来把异常也放进同一容器需调整；当前安全。P3（可选）。
13. **`audit.py:34` 的 `_ensured` 缓存线程安全**：新的并发测试让两个线程同时 `connect()` → `ensure_monthly_audit`；`_ensured` 为普通 set、无锁，8/8 未触发问题，但属潜在竞态（重复 executescript 有 `IF NOT EXISTS` 兜底）。P3（可选，M0b 加锁/去重）。
14. **`connection.py:69-71`**：外层 `except BaseException: conn.close(); raise` 若 `close()` 自身抛错会覆盖原始异常；`connection.py:81-82` 的 `finally: enable_load_extension(False)` 同理。概率极低；可加 `try/except` 保护。P3（可选）。

### 4.3 需求边界问题

**无新增。** R1 唯一的需求边界问题（backend 参数化骨架）已按用户拍板**选项 A** 关闭：M0a-1 仅 SQLite 验收，`conftest` 的 `backend` fixture + PG skip 随 M0b PG spike；检查点 `:52`、`:67` 已记录"0 skipped 属里程碑范围、PG 臂 M0b 激活"。P3-13 的 `:memory:`/非 WAL 显式失败是 design §2/§3 的 WAL 前提，不是验收口径矛盾；建议按 4.2 第 4 条做 docstring/检查点注记，不需回到 spec。

### 4.4 改名彻底性核查

- **`connect.py` → `connection.py`**：`connection.py` 保留 design §3 钦定的 `connect()` 函数名；`__init__.py:13-15` re-export `connect`（函数）与 `migrate_db`（函数），子模块名为 `connection`/`migrate`，`pkg.migrate` 是模块、`pkg.migrate_db` 是函数——**自洽**；tester 的 import 实测通过。
- **调用点**：grep 仅 `config.py:20` 的注释仍写 `connect.py`（4.2 第 1 条）；tests 全部改为 `connect`/`migrate_db`；无 `from ...connect import connect` 残留。**功能上彻底，注释上有一处遗漏**。
- **`migrate` → `migrate_db`**：所有 tests 调用点已更新；R1 的 `migrate` 函数无生产调用方；任务/design 未冻结该函数名。可接受。
- **git D+A**：tester 备注的 `connect.py` 删除 + `connection.py` 新增是内容改写超相似度阈值，实质改名；不构成改动面超标。

---

## 五、调研借鉴检查（R2）

**对照文档**：`research/enterprise-rag/blog/10-build-kb-for-agent.md` §3.2/§3.5、`blog/04-vector-stores.md:91`、`blog/03-chunking-indexing.md:139-149`、`dimensions/12-onerag-assessment.md:21`、`design.md:1310`、`known-gaps.md:69-76`。

R2 的修复**增强了**（而非削弱）调研沉淀的吸收：

- **SQLite WAL 多读单写 / busy_timeout**：`connection.py:39-52` 先设 `busy_timeout`、`journal_mode` 先查后设 + 有限重试，正是对调研"WAL 模式下多读单写、并发受 SQLite 写锁约束"的工程化补强；P3-13 的全集校验让"WAL 静默回退"显式失败，符合调研把 WAL 作为单写者模型前提的判断。
- **迁移框架**：`migrate.py:104-108` 写锁内重读版本，符合调研/SQLite 单写者语义下"多进程启动不能重放 DDL"的实践；`foreign_key_check` + 重建窗口继续保留。
- **repository/协议分层**：本轮未改 `StorageBackend` 六域协议；与调研的 3 方法 repository 相比仍是"更细粒度、防 God interface"的改进（P3-17/P3-18 仍移交，不影响本轮）。
- **FTS5/中文**：本轮未改 DDL；调研的"jieba 预分词 + trigram 兜底"中，预分词字段已就位，trigram 仍按 design §10 的 M1 判据推进（检查点 `:70`），本轮无新缺口。
- **备份/审计保留/RRF**：仍按 M2/M1 既有安排；本轮无改动，不重复计为 finding。
- **`connect()` 对 `:memory:`/非 WAL 的显式失败**：与调研的"文件型 SQLite 一把梭 + WAL"边界一致；不是对调研实践的偏离，而是把"WAL 不可用"从静默降级改成显式失败。**不建议为兼容 `:memory:` 而弱化**；如未来单测需要内存库，另走裸 `sqlite3` 或测试工厂。

**调研借鉴结论**：R2 未引入新的调研相关缺口；WAL/迁移两项修复使实现更贴近 `research/enterprise-rag/` 的 SQLite 单写者与迁移实践。**无新增决策变更需求。**

---

## 六、Tester R2 报告核对与 CASE_BUG

- **testedSha**：`55846be...` 与 HEAD 一致 ✓。
- **复跑**：`uv run pytest` **34 passed / 0 skipped**；`uv run python -O -m pytest` **34 passed, 1 warning**（预期 PytestConfigWarning）；全量加跑 2 轮（累计 4 轮）全绿；并发单测 **8/8**。
- **回归**：R1 的 TC-SCAF-01~05 断言零弱化/零删除；唯一删除段正是 P2-2 标记的手动 OFF/ON 清理段，替换为更强断言；`test_scaf_04` 的 dimval/chunks_au 用例为加强；`helpers.dims_json` 改为 `"[]"` 无断言依赖旧值。
- **边界**：恰好 10 files；`docs/`、`prototype/`、检查点零改动；未 push。
- **R1 tester 两条补充说明**：①两处 DDL 执行层修正（`trg_docdims_consistency` 建表顺序 / FTS 触发器 `rowid`）已按 committer R1 裁定作为 **M0b 移交登记**（检查点 `:68`），本轮无需改 docs；②`-O` 的 PytestConfigWarning 为预期，`connect()` 的 `RuntimeError` 仍全过，**无动作**。
- **R2 tester 备注**：`connect.py`→`connection.py` 被 git 识别为 D+A 而非 rename，系内容改写超相似度阈值；实质改名、不构成改动面超标——**认可，无动作**。
- **CASE_BUG**：tester 未提交 CASE_BUG（"无 IMPL_BUG / TEST_BUG / CASE_BUG；tester 零文件改动"）；本轮无裁定。

---

## 七、证据与限制

- HEAD = `55846be...` = testedSha；`git diff --stat 2152c6c..HEAD` = 10 files +269/−110；`git diff --name-status` = 恰好 10 files（`__init__.py`、`migrate.py`、`connect.py` D、`connection.py` A + 6 tests/helpers）；`docs/`、`prototype/` 零 diff；工作区仅检查点 untracked；未 push。
- tester R2 独立复跑 34 passed 双模式 + 4 轮全量 + 并发 8/8；本轮未独立复跑（只读审查工具权限仅允许 git/gh），以上述报告 + 全量静态审阅 10 files 为准。
- 新引入问题均为 P3；**无 P1/P2**；R1 的 2×P2、11×P3 全部处置，其余按用户拍板豁免/移交。

---

## 八、放行建议

**APPROVED**，可进入交付阶段（用户确认后由 committer 在 PR 留痕；本轮不做写操作）。

交付前建议顺手处理（均 P3，不阻塞）：
1. `config.py:20` 注释 `connect.py` → `connection.py`；检查点 `filesChanged` 的 `connect.py` → `connection.py`，保证证据 manifest 与 HEAD 一致。
2. 将检查点 P3-14（`:memory:` 跳过月库）改记为"moot/随 P3-13 关闭"，并在 `connect()` docstring 明确"file-backed WAL-capable DB only"。
3. 可选：为 P3-1/2/12/13/19 补 3 条轻量回归测试（事务中 FK OFF、`:memory:`/journal 失败 RuntimeError + 连接关闭、`__init__` 导入身份），把 tester 的独立实测固化为 CI 断言。
4. 不建议为 `:memory:` 或非 WAL 文件系统弱化 P3-13 的全集校验——显式失败是 design §2/§3 的既定行为；如 CI 临时目录不支持 WAL，应调整测试环境（本地盘），而非放宽校验。

**报告完毕。**
