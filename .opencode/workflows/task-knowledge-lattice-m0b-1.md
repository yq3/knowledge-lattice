---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m0b-1
target: knowledge-lattice
coderTaskId: ses_e930327d1ffe9fSAg1I6rY9j0m
testerTaskId: ses_e92d1941cffeWpc7n5BksVKcM6
committerTaskId: ses_e92baec26ffei96IVlqwCSR700
status: approved
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 53acea6a77227554fd39d087b4748dbc920ef79d
reviewedSha: 53acea6a77227554fd39d087b4748dbc920ef79d
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["R1（37 files）：knowledge-lattice/src/knowledge_lattice/store/acl_ast.py（新增：方言无关 AST 上提，双方言共享）", "R1：knowledge-lattice/src/knowledge_lattice/store/postgres/（新增方言包：connection.py psycopg3 工厂 / migrate.py schema_migrations+advisory lock / migrations/docs/0001_schema_v1.sql PG 版全量 DDL / audit.py 按月分区表 / acl_render.py jsonb 渲染器 / backend.py PgBackend 六域 / vec.py 文本序列化 / __init__.py）", "R1：knowledge-lattice/src/knowledge_lattice/store/sqlite/acl_render.py（AST 引用改自 acl_ast 并 re-export，渲染产物不变）", "R1：knowledge-lattice/src/knowledge_lattice/store/backend.py（P3-17：SemanticBackend 5 种子方法签名）", "R1：knowledge-lattice/pyproject.toml + uv.lock（psycopg[binary,pool]>=3.2）", "R1：knowledge-lattice/tests/（新增 dbwrap.py 双后端包装器 / test_pg_scaff.py / test_pg_backend.py；修改 conftest.py backend 参数化骨架、test_scaf_01/04/05、test_matrix_t1_t5、test_matrix_t20_t22、test_acl_01~07、test_emb_02_predicate 参数化改写，test_fts_01~03 与 test_r2_review_fixes 切 sqlite_matrix、helpers.py docstring）", "R1：knowledge-lattice/scripts/test_gate.sh（新增：本地门禁——无 DSN 报错非零退出、任何 skipped 非零退出）", "R1：knowledge-lattice/.gitignore（.env 忽略条目随 commit 入库——supervised-coding 开工前防护）", "R2（8 files，+495/−38）：store/postgres/connection.py（P2-1 SET TIME ZONE 'UTC' 单连接+pool configure 同入口）", "R2：store/postgres/migrate.py（P2-3 MAX(applied) 水位 fail-fast+锁内复核）", "R2：store/postgres/audit.py（P2-4 BEFORE TRUNCATE 触发器父表+分区双落——PG 16 父表 statement 触发器不克隆不拦分区直 TRUNCATE，分区须显式落、已注记）", "R2：tests/test_pg_scaff.py（P2-1 回归×4 含 ALTER DATABASE 造非 UTC 库对照+P2-2 search_path 补齐+public 三面零残留断言+P2-3 乱序拒绝回归+P2-4 TRUNCATE 父表/分区回归+P3-3 恶意 key 安全回归×2）", "R2：tests/test_pg_backend.py（P3-1 弱断言收紧 len==2+rid 集合）", "R2：tests/test_scaf_04_triggers.py（P3-2 双臂版本切换五列全清→重算→零命中）", "R2：tests/conftest.py（P3-9 sqlite 分支 try/finally）", "R2：scripts/test_gate.sh（P3-8 mktemp GNU/BSD 通用+summary 完整匹配+无 summary 拦截+pg 臂收集>0 断言；顺修 bash 3.2 unbound 变量坑）"]
endReason: null
createdAt: 2026-10-24T15:53:30+0800
updatedAt: 2026-10-24T19:43:26+0800
---

# task-knowledge-lattice-m0b-1: M0b-1 PG 后端 spike——store/postgres 方言包 + 双后端测试基建 + 本地测试门禁

## 任务原文

（需求 + 验收标准，写全——这是恢复时唯一的上下文来源）

**目标项目**：`knowledge-lattice/`（企业知识层 POC，需求 v0.9 / 设计 v0.9，设计冻结纪律——实现问题走测试用例与 issue，coder 禁改 `docs/` 下需求/设计/用例文档，禁动 `prototype/`）。M0b 三段拆分之第一段（M0a 已全部合入：PR#44/#45/#46，develop HEAD=f1beed5）。

**M0b 拆解总纲（2026-10-24 用户确认）**：M0b 拆 3 段串行——①本段（M0b-1）：PG 后端 spike + 双后端测试基建 + PG CI job；②M0b-2：五实验（**口径修订：TC-PERF-03 SLO 压测取消**——用户拍板不做压测/不搞大数据量，NFR-8 正式标定顺延 M1 基线；TC-PERF-01 档位缩为 1 万/5 万块两档双后端；TC-PERF-02 取 5 万档；TC-AUTH-04 附注 langchain-mcp-adapters 委托 token 实测保留；嵌入 API 用阿里百炼 OpenAI 兼容端点——文档向量合成、真实 API 仅小量调用；用例文档口径回写由 supervised-coding 在 M0b-2 开工前用 edit 落笔）；③M0b-3：结论回写 schema v1.1 迁移（dims_json 去留、分表与否在此定）+ 勘误批次落笔 + P3 遗留批次清偿收口。

**会话要求（用户常设约定，2026-10-24 拍板）**：**每份检查点文件对应的三角色 subagent（coder/tester/committer）全部全新会话，不跨检查点复用任何 task_id**——本任务三角色均全新，与 M0a 各检查点彻底隔离（此约定跨任务沿用，后续检查点照此办理）。

**运行时**：Python **3.12.10**（uv 托管，`.python-version` 已钉）。测试栈 pytest（`uv run pytest`）。依赖新增对照 design §7 选型清单最小化引入（psycopg（v3）/pgvector Python 绑定等按 §7；M0a-1 检查点 TC-SCAF-01 后端行已注明 PG 臂断言用 psycopg 外键错误码）。

**环境约定（2026-10-24 supervised-coding 已定并就绪）**：

- PG 容器已启动：`lattice-pg`（镜像 `pgvector/pgvector:pg16`，端口 5432，`POSTGRES_PASSWORD=lattice`，`POSTGRES_DB=lattice`，随用随起/`docker start lattice-pg`）
- 实例版本已核对（G-6 收窄口径吻合）：**PostgreSQL 16.15 + pgvector 0.8.7**（0.8.x 最新小版本；`vector` 扩展已在 lattice 库 CREATE EXTENSION）
- **DSN 约定**：环境变量 `LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice`（psycopg3 可直连）；conftest 据此判断 pg 臂实跑或 skip
- Docker Desktop 资源：4 CPU / ~3.83GB 内存（已按"不搞大数据量"口径确认够用）

**范围**（design §8 M0b.5 + §4 PG 映射 + D24 + #42 必修4 + 检查点移交项）：

1. **`store/postgres/` 方言包**：
   - 连接工厂：psycopg3 连接池；PG 等价断言（连接池参数 + pgvector 距离函数可用性——TC-SCAF-02 后端行 v1.4/#42 必修4）
   - 迁移框架 PG 版：`schema_migrations` 表（取代 `user_version`）+ 约束校验（TC-SCAF-03 后端行口径）；DDL 落 `store/postgres/migrations/docs/0001_schema_v1.sql`——§4 PG 映射逐项：`RAISE(ABORT)` 触发器 → plpgsql `EXCEPTION`（12 触发器 + 月库 append-only 触发器等价落地，语义同源）；审计按月分库 → **按月分区表**（连接工厂滚动建分区，接口不变）；FTS5 五列 + ai/ad/au 触发器 → **tsvector 五列 GENERATED**（显式 regconfig 双参 `to_tsvector('simple', …)`）+ 应用层分词列重算迁移预留（G-6：jieba 词典升级须触发全量重算）；原生外键约束（无需 PRAGMA）；`BEGIN IMMEDIATE` → 普通事务（MVCC）
   - **AclPlan PG 渲染器**（`store/postgres/acl_render.py`）：同一方言无关 AST，PG 方言渲染（json_each → jsonb 等价路径谓词；visible_docs 双写法同构渲染）；沿用 M0a-2 R2 后的安全纪律——渲染器自控参数名序列 + `InValue.param_prefix` 白名单 fail-closed，`_Renderer` 不得跨调用拼接片段
   - backend PG 实现：当前协议种子范围内六域（Search/Ingest/Acl 实作 + Admin/Semantic 种子——P3-17 顺手：种子方法签名补齐）；可见性产物 SQL 可在 PG 真实执行验证（对齐 M0a-2 形态）；完整检索管线（PG 版 recall_fts/ts_rank 加权）**不属本段**——M0b-2 按实验需要补、M1 追平全矩阵
2. **conftest backend 参数化骨架**（M0a-1 R1 边界拍板选项 A 的 M0b 激活项）：`backend` fixture——sqlite 臂实跑 + pg 臂有 `LATTICE_PG_DSN` 实跑、无 DSN `pytest.skip`；M0a 存量测试按后端参数化改造（TC-SCAF-01 PG 臂激活——孤儿行 psycopg 外键错误码断言、语义不变）
3. **编译器单测双后端绿**：T1~T5/T20/T22 同一测试代码参数化跑 sqlite + pg；TC-ACL-01~07 + TC-EMB-02 双后端绿
4. **本地测试门禁脚本**（2026-10-24 用户拍板：**不建 GitHub Actions CI**——项目后续将移入公司内网继续开发，GitHub 不可依赖；design v1.3.2"CI 必跑 PG、CI 内 skip 视为失败"的意图由本地门禁承接）：提供门禁脚本（如 `knowledge-lattice/scripts/test_gate.sh`，命名落点 coder 定）——跑 sqlite+pg 双后端全量 pytest，**pg 臂出现 skip 即非零退出**（无 DSN 时报错提示 `docker start lattice-pg`，而非静默绿）；交付与回归一律经门禁脚本验证。配套：coder/tester/committer 提示词已同步写入测试门禁纪律（2026-10-24 supervised-coding 落笔 `.opencode/agent/*.md`——coder 禁 skip/弱化断言、tester 独立复跑+skip 逐个核对、committer 门禁审查）
5. **遗留承接（本段相关）**：backend 参数化骨架（本段主体，勾 M0a-1/M0a-2/M0a-3 检查点对应移交项）；P3-17 空 Protocol 种子（随 backend PG 实作顺手）；其余 P3 批次（迁移框架健壮性 P3-3/4/5/7/8/11、月库 P3-14/15/16/18、config P3-23、CTE 类 P3 项）去向 M0b-3 v1.1 迁移实作与 M0b-2 实验脚本，本段不做硬性要求

**验收标准**：

| # | 验收项 | 判据 |
|---|---|---|
| 1 | 双后端全量测试绿 | 本地 `uv run pytest`：sqlite 臂 + pg 臂全实跑（容器在跑、DSN 在场）双模式（`python -O` 同绿）；0 failed，pg 臂 0 skipped |
| 2 | 编译器单测双后端绿 | T1~T5/T20/T22 + TC-ACL-01~07 + TC-EMB-02 同一测试参数化双后端通过 |
| 3 | TC-SCAF-01~05 PG 臂激活 | 01 孤儿行 psycopg 错误码；02 连接池参数 + pgvector 距离函数可用；03 schema_migrations + 约束校验（违例回滚、幂等重放）；04 plpgsql 触发器全集语义同源（逐个 ABORT 行为）；05 membership 删除级联清授权（分区/触发器等价） |
| 4 | PG DDL 与 §4 映射逐项对照 | 16 表等价 + 触发器全集 + tsvector GENERATED 五列 + 月度分区表滚动 + `vector` 列（pgvector `<=>` 可用、精确扫描起步——G-6） |
| 5 | 本地门禁脚本可用且 skip=失败 | 门禁脚本实跑通过且 pg 臂 0 skipped；人为制造无 DSN 场景（如清空 env 单跑）时脚本**非零退出**（防静默绿实证）；门禁脚本纳入交付验证步骤 |
| 6 | 遗留勾选 | backend 参数化骨架移交项在 M0a-1/2/3 检查点勾选回写（supervised-coding 执行） |

**边界（本段不做）**：实验与压测（M0b-2——TC-PERF-01/02、langchain-mcp-adapters 实测；SLO 压测已取消）；v1.1 迁移与 dims_json/分表结论（M0b-3）；PG 检索管线全矩阵追平、ts_rank 加权、HNSW/halfvec 索引化（M1——本段精确扫描起步，G-6）；语义层 `sem_*`（M2-S1）；向量路检索（M1）；`sem` 迁移目录保持空占位。

**Git**：分支 `develop_opencode`（开工第一步 `git fetch origin && git merge origin/develop` 同步——develop HEAD=f1beed5）；每轮 commit `[task-knowledge-lattice-m0b-1] R<n>`，commit 前同步 origin/develop；不 push。

**相关文档**：knowledge-lattice/docs/design.md（§2 并发模型 PG 分区表口径 / §3 分层纪律与结构 / §4 DDL 与 PG 映射段 / §5.1 编译器与双写法 / §7 技术选型 / §8 M0b.5）、docs/TEST-CASES.md（TC-SCAF-01~05 后端行 v1.4 口径、TC-ACL-01~07、TC-EMB-02、T1~T5/T20/T22、§六 M0b 行、口径段 v1.3.2/v1.4）、docs/known-gaps.md（G-6 PG 后端差异与 0.8.x 能力核对、G-11）、M0a-1/2/3 检查点（AclPlan 类型、渲染器安全纪律、协议种子现状）。

## 需求确认

- [x] 用户已确认（2026-10-24——对复述确认并附三项拍板：①**测试门禁放本地脚本、不建 GitHub Actions**（项目将移公司内网，GitHub 不可依赖），"防 AI 跳过测试"写入 subagent 提示词（已落实 `.opencode/agent/*.md`）；②**每份检查点对应三角色 subagent 全部全新会话**为常设约定（已写入任务原文会话要求段）；③百炼 API key 已提供，由 supervised-coding 落 `.env`（不入库）。修改指示已更新任务原文范围 4/验收 5）
- 历史遗留事项清单：M0a-1/2/3 检查点移交 M0b 批次已并入（backend 参数化骨架=本段主体；勘误批次与 P3 批次去向 M0b-2/M0b-3；TC-FTS-01 口径回写由 supervised-coding 在 M0b-2 开工前落笔）；pulsepet 系列 17 检查点经 2026-10-23 用户裁定豁免不并入

## 遗留事项（跨任务移交）

- [ ] **移交 M0b-3 批次**（v1.1 迁移实作与收口时顺手）：P3-4 jsonb 标量守卫（`jsonb_typeof='array'` 或注记）；P3-5 sqlite dot-key 维度 key 校验（R1 遗留，M1 维度创建校验亦可）；P3-6 schema_migrations 锁外竞态（移入锁内或 duplicate_key 重试）；P3-11 未使用项清理（connection.py Path/vec.py parse_vector/sqlite _DOCS/_JE）；R2-P3-1 ALTER DATABASE 测试可移植性（current_database()+保存原库默认）；R2-P3-2 门禁 no-summary `|| true`（友好文案可达）；R2-P3-4 public audit 对象清理 fixture（幂等自清理）；R2-P3-7 门禁 PG_COLLECTED 范围（PG 专用 pg_db 测试计数+`${PG_COLLECTED:-0}` 防空）；R2-P3-8 历史审计分区 TRUNCATE 触发器回溯（deploy 场景 ensure_month_partition 全月回填登记）；tester 观察项与 R2-P3-2 同源；门禁"pg_db 专用测试计数"与 R2-P3-7 同源
- [ ] **移交 M1 批次**：P3-7 ensure_audit 静态化（池化时；**R2-P3-6 加注：P2-4 新增 truncate function/trigger DDL 使每连接 DDL 负担略增**）；P3-10 datetime 序列化契约（API 接入时统一 UTC ISO）；PG 臂 malformed-grant 回归（R1 记录：read_grants 维度归属校验 PG 侧无用例）
- [ ] **口径确认（2026-10-24 supervised-coding 裁定，R2-P3-3 关闭）**：TRUNCATE 异常消息"同源"口径=**同源词根**（含 `append-only`；测试 match="append-only" 已锁核心语义）——不要求逐字同文案，SQLite DELETE 版的 retention 后缀属 SQLite 月库机制描述、PG 分区机制不同不必复制；随勘误批次一并登记
- [ ] **supervised-coding 交付动作（非移交）**：TEST-CASES TC-SCAF-02~05 后端行回写 both+断言落点 test_pg_scaff.py 注记（收口落笔）；M0a-1/2/3 检查点 backend 参数化骨架移交项勾选（验收 6）；勘误批次登记（PG 分区表 PK、TC-SCAF PG 断言落点、.env.example 留 P3-11、TRUNCATE 消息口径、分区触发器不克隆）
- [ ] 无其他

## 轮次记录

- 开工前准备（2026-10-24 supervised-coding，需求确认阶段环境与配套动作）：①PG 容器 `lattice-pg` 启动并核对 **PostgreSQL 16.15 + pgvector 0.8.7**（G-6 口径吻合）；②百炼 API key 落 `knowledge-lattice/.env`（untracked）+ `knowledge-lattice/.gitignore` 补 `.env` 忽略条目（**安全防护例外动作**——先于 coder commit 落地防 key 意外入库；`git check-ignore` 验证 IGNORED-OK；`.env.example` 模板属入库文件，留给 coder 随 P3-11 env 覆盖一并）；③测试门禁纪律写入 `.opencode/agent/{coder,tester,committer}.md`（用户拍板——本地无 CI 兜底，三角色分别加"禁 skip/弱化断言""独立复跑+skip 逐个核对+零弱化核验""门禁审查"条款；**提示词文件属 config-time 加载，需重启 opencode 生效，Task 调用 prompt 内同步强调作双保险**）；④范围 4 由 GitHub Actions CI 改为本地门禁脚本（用户拍板，见任务原文）
- R1: coder 完成（2026-10-24，**全新会话**，coderTaskId=ses_e930327d1ffe9fSAg1I6rY9j0m，commit `329a09937666dc1f7f575eb66d90c8c490674a52` 于 develop_opencode，37 files，父提交=f1beed5）——范围 5 块全交付：①store/postgres 方言包：psycopg3 连接工厂（单连接+ConnectionPool configure 逐连接施纪、server_version≥16 与 pgvector `<=>` 断言显式 raise）／migrate.py（schema_migrations + 事务级 advisory lock 并发序列化、锁内重读干净跳过、dollar-quoting 感知切分）／0001_schema_v1.sql PG 版（15 主表 + tsvector 五列 GENERATED regconfig 双参 + vector 列精确扫描起步 + 9 个 plpgsql 触发器 RAISE EXCEPTION 消息与 sqlite 逐字同源）／audit.py 按月分区表（PARTITION BY RANGE + ensure_month_partition 幂等滚动；**PK=(id,created_at) 为 PG 分区表必要偏差、已注记**）／acl_render.py（`%(name)s` 参数 + jsonb_array_elements_text 等价路径谓词 + visible_docs CTE 同构 + render_vec_recall_select 起步；Match 节点显式 NotImplementedError；M0a-2 R2 安全纪律沿用）／PgBackend 六域（Acl/Ingest/Admin/Audit 实作 + Search 5 方法种子显式 NotImplementedError 防静默假实现 + Semantic 5 桩）；②store/acl_ast.py AST 上提双方言共享（sqlite 渲染产物字节级不变、导入路径兼容）；③conftest backend 参数化骨架（pg 臂独立 schema 生命周期、无 DSN pytest.skip）+ 存量参数化改写（test_scaf_01/04/05、test_matrix_t1_t5、test_matrix_t20_t22、test_acl_01~07、test_emb_02_predicate；test_fts_01~03 与 test_r2_review_fixes 按 v1.4 后端行切 sqlite_matrix、**申报零断言改动**）+ 新增 test_pg_scaff/test_pg_backend/dbwrap；④门禁脚本（无 DSN 报错提示 + 任何 failed/skipped 非零退出）；⑤遗留承接：backend 参数化骨架落地、P3-17 SemanticBackend 种子补齐。新增依赖 psycopg[binary,pool]>=3.2（§7；pgvector Python 绑定未引入——文本形态+转型覆盖）。自测：`uv run pytest` → **239 passed, 1 skipped**（TC-UI-01 manual；参数化 44 组×双臂 + PG 专用 23 条；**pg 臂 0 skipped**）+ `python -O` 同绿；门禁 GATE PASS + 无 DSN 场景 exit=1 实证；TDD 过程在案（conftest 参数化先行、pg 臂 ImportError 红灯转绿）。supervised-coding 机械核验：HEAD=329a099 在 develop_opencode ✓ commit 格式 ✓ docs/prototype 零 diff ✓ .env check-ignore IGNORED-OK ✓ origin/develop(f1beed5) 为 HEAD 祖先 ✓ 工作区仅 supervised-coding 的 agent 文件改动与检查点 untracked ✓ 未 push ✓。口径注记移交（交勘误参考）：①PG 分区表 PK 含分区键；②TC-SCAF-02/03 PG 断言落点=新文件 test_pg_scaff.py；③.env.example 随 P3-11 留 M0b-3
- R1: tester PASS（2026-10-24，**全新会话**，testerTaskId=ses_e92d1941cffeWpc7n5BksVKcM6；testedSha=329a099 前置校验一致；报告原文见"最新验证意见原文"节）——独立复跑 239 passed+1 skipped 双模式（pg 臂 0 skipped；唯一 skip=TC-UI-01 manual 合规；无 DSN 直跑 168 passed+71 skipped 实证门禁捕获对象）；验收 6 项逐条勾验全过（第 6 项勾选回写属 supervised-coding 动作待执行）；**重点核对全过**——test_fts_01~03/test_r2_review_fixes 逐行 diff 仅 fixture 机械改名、断言零弱化；conftest 存量 fixture 全保留、pg 臂每用例独立 schema `lattice_test_<hex12>` 且多轮全量后残留 0 rows 实测；acl_ast 上提"字节级不变"经 108 用例渲染电池新旧 cmp 实测成立（含恶意 key 场景）；GENERATED 替代 ai/ad/au 推导核实成立（版本切换清列→GENERATED 重算→零命中，DELETE 行级消失严格更强）+ 触发器消息 8/8 逐字同源；10 处 NotImplementedError 防静默假实现（"Search 5 方法"计数实为 Search 4+Ingest switch_active_version，表述口径注记）；门禁双场景独立复跑过；**回归 item 级对账**：基线重建 166 passed+1 skipped 与 M0a-3 终态逐数吻合、167/167 item 零删除、240=167+73 算术闭合；边界全过（37 files 一致、docs/prototype 零 diff、.env 未入库、semantic 空占位、无 HNSW/向量索引越界、临时产物零残留）。移交注记 2 条非阻塞：①Search 计数表述口径；②验收 6 勾选待 supervised-coding 执行
- R1 异常澄清（2026-10-24 supervised-coding git 事实核查）：直接父提交 `236ff92` 系**用户 2026-10-24 15:25 主动归档提交**（docs(opencode)：M0a 三检查点入库，1543 行 docs-only）——非 coder 动作、非违规；coder 申报"父提交=f1beed5"指同步链基线（236ff92 之父=f1beed5），表述不准、无实质问题；**检查点文件自此纳入 git 跟踪（用户新惯例），后续检查点照此归档**
- R1: committer NEEDS_CHANGES（2026-10-24，**全新会话**，committerTaskId=ses_e92baec26ffei96IVlqwCSR700；reviewedSha=329a099 前置校验一致；报告原文见"最新验证意见原文"节）——**P1×0 / P2×4**：P2-1 时区未钉 UTC（PG CURRENT_TIMESTAMP 按 session TimeZone 转换写入 TIMESTAMP 列，非 UTC 目标环境致授权过期比较 8h 偏移+审计分区月界 00:00-08:00 写入落不到分区丢窗口；现容器 UTC 故测试全绿）／P2-2 test_pg_scaff 两处工厂调用未传 search_path，audit 对象逃逸到 public（schema 生命周期覆盖缺口）／P2-3 PG 迁移未实现版本只前进（乱序补入小编号迁移会乱序应用，SQLite user_version 语义不等价）／P2-4 append-only 未覆盖 TRUNCATE（PG TRUNCATE 不触发行级触发器，可静默清空审计行，SQLite 无此缺口）；**P3×12**（弱断言/PG 臂五列清空未测/PG 恶意 key 回归缺/jsonb 标量不等价/sqlite json_each dot-key 遗留/schema_migrations 锁外竞态/ensure_audit 每连接 DDL/**test_gate.sh mktemp BSD 形态 GNU 不兼容（公司内网 Linux 必踩）**/conftest sqlite 分支无 finally/datetime 序列化契约/未使用项/检查点父提交表述）；**需求边界问题×2**：①TEST-CASES TC-SCAF-02~05 后端行滞后（仍标 sqlite-only/PG 随 M0b 补——本任务已激活，需回写 both+断言落点 test_pg_scaff.py 注记，文档动作归勘误批次）②时区/TRUNCATE 规格空白（design 未定 PG session TimeZone 契约与 append-only TRUNCATE 等价要求——需用户拍板修复方向）；历史意见处置核对全过（M0a-2 P1-1/P2-1 纪律无回退、M0a-3 P2-3/P3-7 同源落地、M0a-1 选项 A 骨架激活、P3-17 落地）；Tester 报告核对属实（4 处过强表述已记录不推翻 PASS）；调研借鉴无缺口（精确扫描/不引 zhparser/审计分区均与 research 一致）
- R1 committer NEEDS_CHANGES → **spec 确认（2026-10-24 用户拍板）**：①时区契约选**选项 A**——连接工厂统一 `SET TIME ZONE 'UTC'`，存储 UTC（SQLite 既有语义对齐）；**展示分工=后端 API/MCP 吐 UTC ISO 8601 不转换、前端按浏览器时区渲染北京时间**（与 FR-8"服务端不感知、前端本地化"同构；真正前端转换代码随 M2 有界面功能落地）；②TRUNCATE 选**选项 A**——补 `BEFORE TRUNCATE` statement 级触发器（父表+分区形态），消息同源；③修复计划认可：R2 = P2×4 全修（各配回归）+ P3 顺手 5 条（P3-1 弱断言/P3-2 PG 臂五列清空断言/P3-3 PG 恶意 key 安全回归/P3-8 mktemp GNU 兼容——公司内网 Linux 必修/P3-9 conftest sqlite 分支 finally）；P3 登记 7 条移交（P3-4 jsonb 标量守卫、P3-5 sqlite dot-key、P3-6 schema_migrations 锁外竞态→M0b-3 v1.1 迁移实作顺手；P3-7 ensure_audit 每连接 DDL→M1 池化；P3-10 datetime 序列化契约→M1 API；P3-11 未使用清理→M0b-3 收口；P3-12 检查点措辞——已由 supervised-coding 当轮修正）；TEST-CASES TC-SCAF-02~05 后端行回写（both+断言落点 test_pg_scaff.py 注记）随本任务收口由 supervised-coding edit 落笔（coder 禁改）
- R2: 修复轮启动（fixing→implementing；round=2；reviewedSha 置空；修复范围=P2×4 + P3×5，续接 Coder 会话 ses_e930327d1ffe9fSAg1I6rY9j0m）
- R2: coder 完成（2026-10-24，续接会话，commit `53acea6a77227554fd39d087b4748dbc920ef79d` 于 develop_opencode，8 files +495/−38）——P2×4 全修+P3×5 顺手逐条响应全部"已修"：P2-1 `SET TIME ZONE 'UTC'`（单连接+pool configure 同入口）+回归 4 条（含 ALTER DATABASE 造非 UTC 库的目标环境级对照、提前 8h 误杀对照——**实测精化 committer 表述：naive 按上海解释＝绝对时刻更早，实际危害是有效授权被误杀而非过期复活，与 committer"授权提前失效"原文一致**）；P2-2 两处调用补 search_path+public 三面零残留断言+**R1 遗留 public 污染一次性清理复验 0 残留**；P2-3 MAX 水位 fail-fast+锁内复核+"先 0003 后补 0002"回归（0002 DDL 零执行）；P2-4 TRUNCATE 触发器父表+分区双落（PG 16 实测父表 statement 触发器不克隆不拦分区直 TRUNCATE——分区必须显式落，已注记移交勘误参考）+两形态回归；P3-1 len==2+rid 集合；P3-2 双臂五列清空零命中；P3-3 恶意 key 配方对齐 test_r2_review_fixes；P3-8 mktemp X 模板+summary 完整匹配+pg 臂收集>0+顺修 bash 3.2 unbound 坑，三形态分支实证；P3-9 try/finally。不做项（P3-4/5/6/7/10/11/12、docs 回写）零触碰。自测：TDD 红灯 4 项逐一对号（TimeZone≠UTC/乱序静默应用/TRUNCATE 未拦）→ `uv run pytest` **249 passed, 1 skipped**（239+10 新增；pg 臂 0 skipped；唯一 skip=TC-UI-01 manual）+ `python -O` 同绿；门禁 GATE PASS（pg 臂 45 组收集）+ 无 DSN exit=1 + skip 分支 BLOCKED 三形态实证；环境终态复验 public 0 对象/无库级时区 override/lattice_test% 残留 0。supervised-coding 机械核验：HEAD=53acea6 在 develop_opencode ✓ commit 格式 ✓ docs/prototype 零 diff ✓ origin/develop 已同步 ✓ 未 push ✓ 工作区仅工作流文件 ✓
- R2: tester PASS（2026-10-24，续接会话，报告原文见"最新验证意见原文"节 Tester R2 小节；testedSha=53acea6 前置校验一致）——独立复跑 249 passed+1 skipped 双模式（pg 臂 0 skipped）+门禁双场景；P2×4 逐条勾验全过且每条配真场景回归+独立旁证复证（时区双入口钉死、4 回归非恒真含装置有效性对照；public 三面 psql 直查 0 rows；水位 fail-fast 锁内重读；TRUNCATE 双形态手动拦截实测）；P3×5 逐条落地（P3-8 三故障分支临时副本注入实证 exit=1）；**时区语义独立探针**实证 coder 精化方向正确（上海 session 下 +1h 有效授权被误杀——P2-1 危害方向锁定）；回归 250=240+10 零删除零弱化（新增 10 条归属闭合）；不做项零越界（8 files 与申报一致、P3-4/5/6/7/10/11 对应文件零 diff）；环境终态复验零残留（probe_r2% 自清、ALTER DATABASE 已还原）；**观察项非阻塞**：门禁"无 summary"分支实际经 set -e 静默退出（安全无缺口、友好文案不可达），建议 M0b-3 顺手 `|| true`；R1 报告遗留"过强表述②"本轮已补实证

- R2: committer APPROVED（2026-10-24，续接会话，报告原文见"最新验证意见原文"节 Committer R2 小节；reviewedSha=53acea6=HEAD 核验一致）——P1×0/P2×0；R1 意见处置核对表全过（P2×4 已修正确、P3×5 落地、P3-4/5/6/7/10/11 按拍板零夹带、P3-12 已澄清）；历史意见防回归全过（M0a-2 P1-1/P2-1 纪律无回退、acl_ast/postgres acl_render/backend 零 diff、PG 恶意 key 回归反而加固）；新发现 8 条 P3 记录级不阻塞（R2-P3-1~8：ALTER DATABASE 测试可移植性/no-summary 文案不可达/TRUNCATE 消息口径/public 断言非自清理/锁内分支无独立用例/P3-7 负担略增与"零 diff"表述更正/门禁 PG_COLLECTED 范围/历史分区回溯）；**拍板符合性✅**（时区 A 未夹带 TIMESTAMPTZ、TRUNCATE A 落地、无未拍板方案）；需求边界问题无新的实质矛盾（TRUNCATE 消息"同源词根 vs 逐字"口径待确认——已由 supervised-coding 裁定"同源词根"并登记遗留节）；Tester R2 报告核对属实（6 处表述需注意已列明，不推翻 PASS）；TEST-CASES 回写与 M0a 勾选为 supervised-coding 交付前动作
- **终态校验（2026-10-24 supervised-coding）**：testVerdict=PASS + reviewVerdict=APPROVED + reviewedSha=testedSha=HEAD(53acea6, develop_opencode) ✓ → status=approved，待用户确认交付

## 最新验证意见原文

- （暂无）

### Tester R1 报告原文（2026-10-24，testVerdict=PASS）

# 验证执行报告：task-knowledge-lattice-m0b-1（M0b-1 PG 后端 spike）R1

## 1. 开工前置校验

| 项 | 结果 |
|---|---|
| HEAD = testedSha | ✅ `329a09937666dc1f7f575eb66d90c8c490674a52`（develop_opencode，父提交 f1beed5 与申报一致） |
| 工作区 | ✅ 仅 supervised-coding 工作流文件（agent 3 个 modified + 检查点 untracked），交付 commit 内无残留 |
| PG 容器 | ✅ lattice-pg 运行中，PostgreSQL 16.15 + pgvector 0.8.7（G-6 口径吻合） |

## 2. 独立复跑摘要（全部自行执行，未采信 coder 自测）

| 场景 | 结果 |
|---|---|
| `LATTICE_PG_DSN=… uv run pytest -v` | **239 passed, 1 skipped, 0 failed**（14.37s） |
| `LATTICE_PG_DSN=… uv run python -O -m pytest` | **239 passed, 1 skipped**（12.27s，-O 同绿） |
| 双臂计数 | sqlite 臂 **44** + pg 臂 **44**（88 参数化项）+ 151 非参数化 = 239；**pg 臂 0 skipped** |
| `scripts/test_gate.sh`（有 DSN） | **GATE PASS**，双模式各 `239 passed, 1 deselected`——TC-UI-01 在门禁口径下为 deselected 非 skipped ✅ |
| `env -u LATTICE_PG_DSN scripts/test_gate.sh` | **exit=1**，报错提示 `docker start lattice-pg` + 导出 DSN（拒绝静默绿实证）✅ |
| 补充：无 DSN 直跑 pytest | 168 passed, **71 skipped**（pg 臂整体走 conftest skip 路径）——门禁 skip 检测分支的捕获对象实证 ✅ |

## 3. 验收表 6 项逐条勾验

| # | 验收项 | 判定 | 证据 |
|---|---|---|---|
| 1 | 双后端全量绿、双模式、pg 臂 0 skipped | ✅ PASS | 见 §2；唯一 skipped=TC-UI-01（manual，非 pg 臂） |
| 2 | T1~T5/T20/T22 + TC-ACL-01~07 + TC-EMB-02 双后端绿 | ✅ PASS | 实跑计数：t1_t5 5+5、t20_t22 2+2、acl_01 4+4、acl_02 3+3、acl_03 3+3、acl_04 3+3、acl_05 5+5、acl_06 2+2、acl_07 2+2、emb_02 2+2，全 PASSED |
| 3 | TC-SCAF-01~05 PG 臂激活 | ✅ PASS | 01：`test_scaf_01_foreign_keys.py:37-39,52-53`（`excinfo.value.sqlstate == "23503"` 逐值断言，dbwrap:204-206 口径）；02：`test_pg_scaff.py:22-37`（池 min/max 参数 + `<=>` 距离）+ `:40-55`（server≥16 + pgvector 0.8.x）；03：schema_migrations（`test_pg_scaff.py:61-108`）+ 幂等（:111-124）+ **违例整事务回滚**（:171-207，FK 违例后版本不前进、DDL 撤销、修复后同号可应用）+ advisory lock 并发干净跳过（:210-244，双线程 barrier、恰应用一次）；04：`test_scaf_04_triggers.py` 全集双臂化（9 参数化函数，逐触发器 `pytest.raises(integrity_error, match=同源消息)`）+ GENERATED 等价（`test_chunk_fts_columns_sync` 双臂）；05：`test_scaf_05_membership_cleanup.py` 双臂（级联清 sync 来源授权、他人授权保留） |
| 4 | PG DDL 与 §4 映射逐项对照 | ✅ PASS | 16 表等价：15 主表 + 工厂滚动 `audit_events` 分区表（`test_pg_scaff.py:73-81` 断言，sem_* 不在、无 chunks_fts）；触发器 12→9 plpgsql + 审计 2（append-only 消息与 sqlite 逐字同源，`audit.py:39-64`）；tsvector 五列 GENERATED（DDL:260-269，`attgenerated='s'` 断言 ：86-95）；月度分区滚动幂等（:250-287）；`vector` 列 + `<=>`（DDL:254、`test_pg_backend.py:147-150` 精确扫描距离实证） |
| 5 | 门禁脚本可用且 skip=失败 | ✅ PASS | GATE PASS + 无 DSN exit=1 实证；脚本逻辑 `test_gate.sh:21-27`（无 DSN 立即拒绝）、`:39-43`（任何 skipped 非零退出） |
| 6 | 遗留勾选回写（M0a-1/2/3 检查点） | ⏳ 非本交付范围 | 属 supervised-coding 动作（勾选回写由编排执行），代码侧承接已落地（backend 参数化骨架 + P3-17），待编排回写 |

## 4. 重点核对项逐项结论

1. **test_fts_01~03 / test_r2_review_fixes 逐行 diff**：✅ 申报属实。逐行核对全部为 `matrix` → `sqlite_matrix` 机械改名（fixture 形态），所有断言语句逐字保留——含 `pytest.raises(AclDeniedError)`、`raises(ValueError, match="embed_model")`、可见集全等断言、`"1 = 0" in sql and "IN ()" not in sql` 等，**零弱化零删除**。
2. **conftest 大改兼容性 + pg schema 隔离**：✅ 旧 `conn`/`db_path`/`sqlite_matrix`/`ingest_env`/`app_env` fixture 全保留（conftest.py:77-91,237-241,247-363），sqlite-only 存量用例（scaf_02 PRAGMA 等）未受影响；pg 臂每用例独立 schema `lattice_test_<hex12>`（CREATE → search_path → 工厂纪律 → 迁移 → 用例 → DROP CASCADE，:119-140），**多轮全量跑后 `lattice_test%` 残留 0 rows**（psql 直查），防污染实证。
3. **acl_ast.py AST 上提“字节级不变”**：✅ 实证成立。将 `329a099~1` 旧包提取至临时目录，同造数、108 用例渲染电池（12+2 用户组 × sel/vis/ast/where/rule 全渲染面 + filter 4 变体 + vector 2 + now=None + retired 2 + FTS 三函数 + denial 路径），新旧渲染产物 JSON **`cmp` 字节级零差异**。含恶意 key（`x_0) OR 1=1)) --`）与向量路标签场景。
4. **PG DDL 映射与 GENERATED 替代推导**：✅ 推导成立。sqlite ai（INSERT 同步）/ad（DELETE 移除）/au（五列 UPDATE 旧词归零重算）与 PG `GENERATED ALWAYS AS to_tsvector('simple', …) STORED` 语义逐一对应：INSERT 自动计算、依赖列 UPDATE 重算（清列→空 tsvector→`@@` 零命中，版本切换清列语义在 PG 侧落为 GENERATED 重算）、DELETE 行级消失（无 sqlite 残留空行问题，严格更强）；pg 臂 `fts_word_count`（dbwrap:310-322）+ `test_chunk_fts_columns_sync` 双臂实证。显式 regconfig 双参为 GENERATED immutable 要求所必需。触发器消息 **sqlite `RAISE(ABORT,…)` ↔ PG `RAISE EXCEPTION` 8/8 逐字同源**（immovable/org 三表/ds_org_check/ds_immutable/consistency/expired membership）。已知差异均有注记：分区表 PK=(id,created_at)（audit.py:12-14）、rid→IDENTITY（DDL:235,237）、embed 写入侧校验维度（DDL:233-234）。
5. **PgBackend Search 种子 + P3-17**：✅ Search 协议 4 方法（recall_fts/recall_vec/recall_by_entities/expand_relations）+ Ingest `switch_active_version` + Semantic 5 桩 = 10 处显式 `NotImplementedError`，无静默假实现（checkpoint 申报“Search 5 方法”计数含 switch_active_version，属表述口径非缺陷）；`test_pg_backend.py:252-265` 逐个 raises 断言 + `:268-272` StorageBackend runtime 协议一致性 + `:275-282` P3-17 五签名。PG 渲染器 Match 节点显式拒绝（acl_render.py:92-93），param_prefix 白名单收口共享 acl_ast，M0a-2 R2 安全纪律沿用。
6. **门禁脚本双场景**：✅ 见 §2。
7. **回归核对**：✅ 见 §6。

## 5. skip 清单

| skip | 归属 | 理由 | 判定 |
|---|---|---|---|
| `test_ui_01_manual_walkthrough`（唯一，全量 1 skipped） | TC-UI-01 | `pytest.mark.manual + pytest.mark.skip(reason="TC-UI-01 为手动走查用例（浏览器人工执行、不进 CI）")`（test_ui_01_manual.py:37-38），M0a 起常设口径 | ✅ 合规；门禁 `-m "not manual"` 下为 deselected，不属任务范围用例 skip |

任务范围用例 **0 skip**；pg 臂 **0 skip**。无异常。

## 6. 回归与边界复查

- **基线重建实跑**：以 `329a099~1` 旧 src + 旧版 19 个改写文件重组旧套件于临时目录独立运行，得 **166 passed + 1 skipped——与 M0a-3 检查点终态基线逐数吻合**。
- **item 级零丢失**：旧 167 item ↔ 新 240 item 全量对账——118 逐字同名 + 43 扩为双臂 + 1 改名扩双臂（`test_chunks_fts_sync_triggers`→`test_chunk_fts_columns_sync`，断言场景逐一保留并强化为 GENERATED 等价实证）+ 5 复合参数扩双臂（`[u_cn]`→`[sqlite-u_cn]`/`[pg-u_cn]`）= **167/167，零删除**；240 = 167 + 73 增量算术闭合（23 条 PG 专用 + 1 条 sqlite 触发器点名双保险 + 49 双臂第二份）。
- **边界**：37 files 与申报一致；docs/ 与 prototype/ 零 diff ✅；`.env` check-ignore IGNORED-OK、未入库 ✅；`migrations/semantic/.gitkeep` 空占位保持 ✅；唯一新依赖 `psycopg[binary,pool]>=3.2`（pyproject.toml，pgvector Python 绑定未引入与申报一致）✅；ts_rank/to_tsquery/HNSW/ivfflat **零实现代码**（仅文档性提及并指向 M0b-2/M1）、DDL 无向量索引（精确扫描起步）✅；临时验证产物全部位于系统临时目录、已清理，仓库零残留（终态 git status 与开工一致）。

## 7. 结论

全部验收项与重点核对项通过，失败 0、任务范围 skip 0、回归零弱化零删除。

**testVerdict: PASS**
**testedSha: `329a09937666dc1f7f575eb66d90c8c490674a52`**

移交注记（非阻塞）：①“Search 5 方法”计数实为 Search 4 + Ingest switch_active_version，属申报表述口径；②验收 6 的 M0a-1/2/3 检查点勾选回写待 supervised-coding 执行。

### Committer R1 报告原文（2026-10-24，reviewVerdict=NEEDS_CHANGES）

# Committer 审查报告：task-knowledge-lattice-m0b-1（M0b-1 PG 后端 spike）R1

## 1. 开工前置校验

| 项 | 结果 |
|---|---|
| HEAD = reviewedSha | ✅ `329a09937666dc1f7f575eb66d90c8c490674a52`（`develop_opencode`；工作区 HEAD 一致） |
| 检查点 testedSha | ✅ 与 HEAD 相同；`origin/develop`=f1beed5，为 HEAD 祖先 |
| 直接父提交 | ⚠️ 实际直接父提交为 `236ff92`（检查点 docs 提交，其父才是 f1beed5）。检查点写「父提交=f1beed5」是同步基线口径，不是直接 parent；**不影响 diff 审查**（`329a099~1..329a099` 恰为 37 files，且父提交只含 `.opencode/workflows` 文档） |
| 工作区 | ✅ 仅 `.opencode/agent/{coder,committer,tester}.md` modified + 本检查点 untracked；无代码脏改 |
| 37 files | ✅ `git diff --name-only 329a099~1..329a099` 逐项与申报一致 |
| docs/prototype 零 diff | ✅ 两条路径零改动 |
| 密钥/边界 | ✅ `.env` 未入库、`.gitignore` 含 `.env`；无 HNSW/ivfflat/向量索引；semantic 迁移目录空占位 |
| 测试复跑 | 未独立复跑（工具权限，与 M0a 同口径）；以 Tester R1 报告 + 静态审阅为准 |
| evidence manifest | ✅ 检查点已含 taskId / coderTaskId / testerTaskId / testedSha / testVerdict / Tester 报告原文；无独立 manifest 文件（按本工作流以检查点为 manifest）；双 SHA 与 HEAD 一致 |

## 2. 结论

**reviewVerdict: NEEDS_CHANGES**

无 P1；存在 4 项 P2（PG 等价语义/隔离问题，未被当前验收用例覆盖）。P2 未修不 APPROVED；P3 可与 P2 同批或记录后移。

## 3. 问题清单

### P1（必修）— 无

未发现越权、数据损坏、门禁失守类必修问题。SQLite 侧 AST 上提的字节级不变申报经静态比对成立（`build_dimension_rule_ast` / `build_acl_ast` / `build_where_ast` / `filter_nodes` / `visible_docs` 均逐字等价迁移，仅注释与 import 形态变化）。

### P2（应修）

**P2-1｜时区未钉 UTC，PG/SQLite 时间语义不等价（隐性，目标环境非 UTC 时触发）**
- 文件：`knowledge-lattice/src/knowledge_lattice/store/postgres/connection.py:58-79`（`setup_connection` 未 `SET TIME ZONE`）、`store/postgres/migrations/docs/0001_schema_v1.sql`（全部 `TIMESTAMP` + `CURRENT_TIMESTAMP`）、`store/postgres/audit.py:80-89`（分区边界按 `datetime.now(UTC)`）、`store/postgres/backend.py:53-66`（`CURRENT_TIMESTAMP` 与 `expires_at` 比较）。
- 问题：SQLite `CURRENT_TIMESTAMP` 是 UTC；PG `CURRENT_TIMESTAMP` 是 `timestamptz`，写入 `TIMESTAMP`（无时区）列时按 **session TimeZone** 转换。当前 `lattice-pg` 容器为 UTC 所以测试全绿；公司内网 PG 若为 `Asia/Shanghai`：
  - `expires_at > CURRENT_TIMESTAMP` / `OLD.expires_at <= CURRENT_TIMESTAMP` 产生 8 小时偏移（授权提前失效、成员续期触发器语义偏移）；
  - 审计分区按 UTC 月名创建，而 `audit_events.created_at` 存 session 本地时间——**每月 1 日 00:00–08:00（本地）写入会落不到已建分区**，报 `no partition of relation "audit_events" found for row`（审计写入丢窗口）。
- 建议：`setup_connection`（连接与 pool configure 同入口）加 `SET TIME ZONE 'UTC'`；或统一改 `TIMESTAMPTZ`。补回归：断言工厂后 `SHOW TimeZone` 为 UTC；用 `now=None` 的过期/有效授权对照；审计在月中边界（如 `2026-10-31T16:30Z`）可写入当月分区。

**P2-2｜PG 专用测试绕过 schema 生命周期，污染 `public`**
- 文件：`knowledge-lattice/tests/test_pg_scaff.py:26`（`connect_pool(pg_db.dsn, ...)` 未传 `search_path`）、`:44`（`connect(pg_db.dsn)` 未传）；`tests/conftest.py:119-140` 的 `_pg_db` 契约；`store/postgres/connection.py:79`（`ensure_audit`）。
- 问题：两处工厂调用使用默认 `search_path`（`"$user", public`），`setup_connection → ensure_audit` 在 **public** 创建 `audit_events`、两个 append-only 函数与触发器，逃出 `lattice_test_<hex>` 的 `DROP SCHEMA ... CASCADE`。Tester「schema 隔离残留 0 rows」实测只覆盖 `lattice_test%` 命名 schema，未覆盖 public 对象——重复跑/其他任务会看到这些公共对象。
- 建议：两处调用传 `search_path=pg_db.schema`（`connect_pool` 的 `options` 路径已支持）；或在该用例 finally 中清理 public；并给 Tester 的隔离断言补一条「public 无 audit 对象」。

**P2-3｜PG 迁移未实现「版本只前进」**
- 文件：`knowledge-lattice/src/knowledge_lattice/store/postgres/migrate.py:76-86`（`current` 集合 + 任意缺失版本即应用）、`:116-121`（锁内只做等值重读）。
- 问题：SQLite 以 `PRAGMA user_version` 全局单调前进；PG 侧若后续补入一个编号更小的迁移文件（如 docs 0003 已应用后再补 semantic 0002），当前实现会**乱序应用**，与模块 docstring/design「版本号只前进、重复运行幂等」不符。现有测试只覆盖同集合重放幂等。
- 建议：以 `MAX(applied)` 为水位，未应用的 `m.version <= max` 直接 `MigrationError` fail-fast（或在锁内以 `MAX(version)` 复核）；补「先应用 0003、后加入 0002」回归。

**P2-4｜PG append-only 未覆盖 TRUNCATE，审计语义不等价**
- 文件：`knowledge-lattice/src/knowledge_lattice/store/postgres/audit.py:57-64`（仅 `audit_no_update` / `audit_no_delete` 行级触发器）；测试 `tests/test_pg_scaff.py:290-302` 也只测 UPDATE/DELETE。
- 问题：PG 的 `TRUNCATE` **不触发行级 UPDATE/DELETE 触发器**；SQLite 无 TRUNCATE，DELETE 均被 `audit_no_delete` 拦截。当前 PG 上 `TRUNCATE audit_events`（或某一分区）可静默清空审计行，违背「append-only 等价落地、语义同源」（#33 P2-10 / FR-6）。未修前该审计不变量在 PG 正式备选下是缺口的；若按审计合规红线可升 P1，但本段尚无 truncate 调用路径，故列 P2。
- 建议：增加 `BEFORE TRUNCATE` statement 级触发器（父表，并覆盖各分区直接 TRUNCATE 的形态），消息沿用同源文案；补 `pytest.raises(..., match="append-only")` 回归。

### P3（记录 / 可顺手）

1. `tests/test_pg_backend.py:137`：`assert [c["seq"] ... for c in claimed] or len(claimed) == 2` 左操作数非空列表恒真，实际只断言「非空」；应改为 `assert len(claimed) == 2`（或对 rid 集合断言）。
2. `tests/test_scaf_04_triggers.py`（PG 臂）：`test_chunk_fts_columns_sync` 只 UPDATE `keywords` 一列，未覆盖设计 §5.3 版本切换「五列全清→GENERATED 重算→零命中」的完整形态；建议在 PG 臂补清空五列的断言（SQLite 侧 `test_fts_03` 已有，但 sqlite-only）。
3. `tests/test_r2_review_fixes.py` 全量切 `sqlite_matrix` 后，新增 PG 渲染器未获得恶意 key / param_prefix 安全回归。代码静态检查无回退（`postgres/acl_render.py:82-89` 自控 `g<seq>_<i>`、`acl_ast.py:91-101` 白名单、`:140-146` key 走 SQL 字面量转义），但建议加一条 PG 臂恶意 key 用例锁死该纪律。
4. `postgres/acl_render.py:140-146`：`jsonb_array_elements_text(jsonb_extract_path(...))` 遇 **标量** 值会抛错（`cannot extract elements from a scalar`）；SQLite `json_each` 对标量返回一行、对 JSON `null` 返回一行 NULL——两方言在畸形 `dims_json` 上不等价。应用侧 `ingest.py:220-221` 只写数组，但 DDL 无约束；建议文档注记或加 `jsonb_typeof(...)='array'` 守卫。
5. `sqlite/acl_render.py:151`（**遗留，非本段引入**）：`json_each(c.dims_json, '$.{dim_key}')` 对含 `.` 的维度 key 会按嵌套路径解释，可能把「有值」文档误判为空值放行（越权方向）；PG 用 `jsonb_extract_path` 反而按字面 key，安全。建议在维度创建侧加 key 字符集校验，或 SQLite 路径改为引号形式。
6. `postgres/migrate.py:78`：`_ensure_schema_migrations` 在 advisory lock 之外执行；并发首次启动的 `CREATE TABLE IF NOT EXISTS` 仍存在 PG 的 pg_type 唯一键竞态（测试因 `_pg_db` 预先建表未暴露）。建议移入锁内或捕获 `duplicate_key` 重试。
7. `postgres/connection.py:79` / `audit.py:92-98`：`ensure_audit` 在**每个连接/pool configure** 上执行完整 DDL（`CREATE OR REPLACE FUNCTION` + `DROP/CREATE TRIGGER`），带来每次建连的写锁与权限要求；建议静态对象只建一次，每连接仅 `ensure_month_partition`。
8. `scripts/test_gate.sh:33`：`mktemp -t lattice-gate-${label}.log` 是 BSD/macOS 形态；GNU `mktemp` 要求模板含 `X`。项目将移公司内网（Linux 概率高），门禁会直接失败。建议 `mktemp "${TMPDIR:-/tmp}/lattice-gate-${label}.XXXXXX.log"`；`:39` 的 `tail -5` skip 检测建议改为匹配完整 summary（或直接解析 `-q` 汇总行），并考虑断言 pg 臂用例数 > 0（防「没收集到」而非 skip）。
9. `tests/conftest.py:98-106`：`backend` sqlite 分支在 `migrate_db` 抛错时不会关闭连接（pool/pg 分支有 finally）；建议 try/finally 包住 setup。
10. `postgres/backend.py`：PG 返回的 `expires_at`/`created_at`/`updated_at`/`disabled_at` 是 `datetime` 对象，SQLite 返回字符串；M1 接入 `api/documents.py`、`api/tasks.py` 后 JSON 序列化形态会不同（ISO vs `YYYY-MM-DD HH:MM:SS`）。建议在 backend 边界统一归一或显式声明契约。
11. 未使用项：`postgres/connection.py:25` `Path`、`postgres/vec.py:18 parse_vector`、`sqlite/acl_render.py:28-29` `_DOCS/_JE`（当前无引用）；可清理。
12. 检查点元数据：`R1` 记录「父提交=f1beed5」与 git 直接 parent `236ff92` 不一致；属检查点措辞问题，非代码问题，建议 supervised-coding 改为「同步基线」表述。

## 4. 需求边界问题

**有（2 条口径问题，均不写给 coder 修代码，交 supervised-coding 回写/确认）：**

1. **TEST-CASES 后端行与验收 #3 的文档滞后**：TEST-CASES v1.5 的 TC-SCAF-02~05 仍标 `sqlite-only / PG 等价随 M0b 补`，而任务验收 #3 要求 PG 臂激活；实现将 PG 断言落在新文件 `tests/test_pg_scaff.py`（而非原 TC-SCAF-02/03 文件）。TEST-CASES 是活文档、coder 受冻结纪律禁改 `docs/`，需 supervised-coding 在 M0b 收口回写为 `both` 并注明断言落点（检查点注记②已申报，属文档动作）。
2. **时区/审计 TRUNCATE 的规格空白**：design §4 PG 映射与 TEST-CASES 只规定 UTC 造数格式，未明确 PG **session TimeZone** 契约；design 对 append-only 只注「SQLite 无 TRUNCATE」，未给 PG 的 TRUNCATE 等价要求。建议回 spec 确认「PG 连接统一 UTC」与「append-only 是否覆盖 TRUNCATE/分区 drop 保留策略」，再由实现落代码（P2-1/P2-4）。

其余无实质矛盾：`PgBackend` 单连接、池化随 M1 属检查点已申报的 deferral；`.env.example` 留 P3-11 同理；PG 分区表 PK 含分区键属已注记的等价偏差，语义可接受。

## 5. 上轮/历史意见处置核对

| 历史项 | 本段处置 | 结论 |
|---|---|---|
| M0a-2 R2 P1-1：渲染器自控参数名 + param_prefix 白名单 | `acl_ast.InValue` 上提后双方言共用；PG `_Renderer` 用 `g<seq>_<i>`，不跨调用拼接；`postgres/acl_render.py:82-89`、`acl_ast.py:91-101` | ✅ 无回退；PG 恶意 key 回归缺（P3-3） |
| M0a-2 R2 P2-1：read_grants 校验 `v.dimension_id` | `postgres/backend.py:88` 与 SQLite 同款 | ✅ 无回退；PG 臂无对应回归用例（P3 记录） |
| M0a-2 R2 P3-1：visible_docs CTE 不二次读 dim.status | `acl_ast.build_visible_docs_rule_ast` 共享，PG 直接消费 | ✅ |
| M0a-2 R2 P3-7：migrate finally 恢复 | PG `_apply_one` 异常 ROLLBACK；失败不覆盖原异常 | ✅ |
| M0a-3 P2-3：write_embeddings 收浮点向量、方言序列化 | `postgres/backend.py:242-259` + `vec.format_vector`；core 不碰方言 | ✅ |
| M0a-3 P3-7：pending_dims 解析失败整事务回滚 | `postgres/backend.py:173-208` 与 SQLite 同源，测试覆盖 | ✅ |
| M0a-1 边界拍板选项 A：backend 参数化骨架 | `backend` / `matrix` / `sqlite_matrix` + dbwrap；44 组双臂 | ✅ 激活 |
| P3-17：SemanticBackend 种子签名 | `store/backend.py:205-233` 5 方法 + PgBackend stubs + 测试 | ✅ |
| M0a-1/2/3 检查点勾选回写 | 非代码动作 | ⏳ supervised-coding |
| 本任务上轮意见 | R1 首轮，无 | — |

## 6. Tester R1 报告核对结论（抽查属实性）

**属实/可信：**
- 37 files、docs/prototype 零 diff、`.env` 未入库、无 HNSW/向量索引、semantic 空占位、psycopg 唯一新依赖 — 逐项核对成立。
- `test_fts_01~03` / `test_r2_review_fixes` 逐行 diff：仅 `matrix → sqlite_matrix` 机械改名，断言逐字保留，零弱化。
- 参数化组数 44、PG 专用函数数 23、239=167+72/88+151 的算术均可由测试文件静态复算成立；`pytest.mark.skip` 全库仅 TC-UI-01 一处。
- 10 处 `NotImplementedError`、9 个 plpgsql 触发器、5 列 `attgenerated='s'`、触发器消息 8/8 同源、GENERATED 取代 ai/ad/au 的推导 — 静态核对成立。
- 门禁脚本逻辑：无 DSN 立即 exit 1；任何 skip 非零退出；双模式均带 `-m "not manual"` — 逻辑成立。
- 回归「零删除」：diff 未见测试删除，`test_chunks_fts_sync_triggers → test_chunk_fts_columns_sync` 改名保留场景；167 项对账未独立复核，但可信。

**报告中的过强表述/未覆盖点（不推翻 PASS，但需记录）：**
1. **「pg schema 每用例独立 + 残留 0 rows」不完整**：`lattice_test%` 隔离成立，但 `test_pg_scaff` 两处工厂测试未传 `search_path`，public 会残留 audit 对象（P2-2）；报告未覆盖。
2. **「门禁 skip 检测分支的捕获对象实证」**：无 DSN 直跑 168 passed + 71 skipped 是在**脚本提前 exit** 之后另行直跑 pytest 的结果，并未执行 `test_gate.sh:39` 的 skip 检测分支；该分支仍缺一次「DSN 在但有用例 skip」的实证。
3. **「版本切换清列→GENERATED 重算→零命中」** 是推导 + 单列 UPDATE 实证；未在 PG 臂清空五列实测（P3-2）。
4. 「Search 5 方法」计数口径：同意 Tester 的更正——实为 Search 4 + Ingest `switch_active_version`，仅表述问题。
5. `test_pg_backend.py:137` 的弱断言未被报告点名（P3-1）。

## 7. 调研借鉴检查（research/enterprise-rag）

- 对照 `dimensions/03-index-vector-store.md`（pgvector 0.8.7：`vector` 索引上限 2000 / `halfvec` 4000、精确扫描、`hnsw.iterative_scan`、过滤靠 SQL WHERE、混合检索需自组装）与 `blog/04-vector-stores.md`：
  - ✅ 本段采用 `vector` 列 + `<=>` **精确扫描起步**、不建 HNSW/IVFFlat、不引 halfvec——与 G-6「精确扫描起步」及 research「filtered ANN 有欠召回风险、pgvector 全 DIY」一致；
  - ✅ 中文 FTS 走应用层 jieba + `to_tsvector('simple', …)`，不引 zhparser/ParadeDB——与 design §7 选择及 research「PG 需外挂分词」判断一致；
  - ✅ 审计按月分区、ACL 走 SQL WHERE、连接池用 psycopg——与 research 的「已有 PG、规模有限时 pgvector + SQL 过滤」路线一致；
  - 待 M0b-2/M1：halfvec/迭代扫描实验、加权 `ts_rank`、混合检索 RRF——本段边界正确，无越界实现。
- 未发现与本任务冲突的调研结论；timezone/TRUNCATE 属 PG 运维与审计语义，research 未覆盖。

## 8. reviewedSha

```
reviewedSha: 329a09937666dc1f7f575eb66d90c8c490674a52
```

**CASE_BUG 裁定**：本轮未收到 tester 的 CASE_BUG 裁定请求，无裁定。

**放行说明**：本轮不执行 `gh pr review`（未到用户确认交付阶段）；P2-1~P2-4 修复并重跑门禁后可转下一轮复核。

### Tester R2 报告原文（2026-10-24，testVerdict=PASS）

# 验证执行报告：task-knowledge-lattice-m0b-1 R2（修复轮复验）

## 1. 前置校验

| 项 | 结果 |
|---|---|
| HEAD = testedSha | ✅ `53acea6a77227554fd39d087b4748dbc920ef79d`（develop_opencode，父提交=R1 329a099，commit message `[task-knowledge-lattice-m0b-1] R2: …` 格式合规） |
| 工作区 | ✅ 仅 supervised-coding 工作流文件（agent 3 modified + 检查点 tracked-unmodified 场景下的 workflow untracked 状态与开工一致） |
| 变更规模 | ✅ 8 files，+495/−38，与申报逐字一致 |
| 环境终态（复验后） | ✅ public 三面（audit 表/触发器/函数）0 对象、`lattice_test%` 残留 0、`probe_r2%` 探针残留 0、库级 TimeZone=Etc/UTC（测试用 ALTER DATABASE 已还原） |

## 2. 独立复跑摘要（全部自行执行）

| 场景 | 结果 |
|---|---|
| `uv run pytest -v` | **249 passed, 1 skipped, 0 failed**（13.85s） |
| `uv run python -O -m pytest` | **249 passed, 1 skipped**（-O 同绿） |
| 双臂 | sqlite **45** + pg **45** = 90 参数化 + 159 非参数化；**pg 臂 0 skipped**；唯一 skip=TC-UI-01 manual |
| `scripts/test_gate.sh` | **GATE PASS**（双模式 249 passed, 1 deselected；输出含“pg 臂 45 组参数化全实跑”） |
| `env -u LATTICE_PG_DSN scripts/test_gate.sh` | **exit=1** + 启动容器提示 ✅ |

## 3. 修复项逐条勾验（对照 Committer R1 意见原文）

| 项 | 判定 | 证据 |
|---|---|---|
| **P2-1 时区钉 UTC** | ✅ 修复 | `SET TIME ZONE 'UTC'` 落 `setup_connection`（connection.py:77）——单连接 `connect` 与 pool `configure` **同一入口**（:105），双入口同源成立。回归×4 均含**装置有效性/对照臂、非恒真**：①SHOW TimeZone==UTC + 先 SET Asia/Shanghai 证明偏移真实、工厂重入恢复（test_pg_scaff:117-140）；②DEFAULT CURRENT_TIMESTAMP 写入值 vs UTC 墙上钟 <2min + 上海对照 +8h（7h55m~8h5m 窗口断言，:142-167）；③UTC 语义过期判定（-1h 滤除/+1h 保留）+ 上海对照 +1h **有效授权被误杀→()**（:169-207，真实走 `backend.read_grants` 库时钟路径）；④ALTER DATABASE 造非 UTC 库默认下 raw 新连接拿到 Asia/Shanghai（装置有效）、池/单连接仍钉 UTC、finally RESET（:209-244） |
| **P2-2 public 污染** | ✅ 修复 | 两处工厂调用补 `search_path=f"{pg_db.schema},public"`（pool :58-61 / 单连接 :86）+ `current_schema()==schema` 断言 + `_assert_public_free_of_audit_objects` 三面断言（表/触发器/函数，:29-51）在两用例末尾各执行；**独立旁证**：psql 直查 public 三面全部 0 rows（R1 遗留污染已清） |
| **P2-3 版本只前进** | ✅ 修复 | `MAX(applied)` 水位 + `_assert_forward_only` fail-fast（migrate.py:96-104,116-118）；`_apply_one` **锁内重读全量 applied 集合 + 同款校验**（:135-146）防并发推进竞态。回归：先 0003 后补 0002 → MigrationError、**0002 DDL 零执行**（col2 not in cols）、0003 不重放、水位仍 [(1,),(3,)]（test_pg_scaff:384-427）——真实目标场景非恒真 |
| **P2-4 TRUNCATE 防护** | ✅ 修复 | `BEFORE TRUNCATE FOR EACH STATEMENT` 触发器父表 + `ensure_month_partition` **每分区显式落同款**（audit.py:66-79,113-117,126-131；PG 16 父表 statement 触发器不克隆分区已注记）。回归：父表/分区双形态 TRUNCATE 均 raises(match="append-only")、审计行完好（test_pg_scaff:271-296）。**独立旁证**：生产 `ensure_audit` 重建对象后 psql 语义手动 `TRUNCATE audit_events` 与 `TRUNCATE audit_events_202610` 均被拦（消息 `audit_events is append-only; TRUNCATE is forbidden`，含 append-only 同源词根），行完好 |
| **P3-1 弱断言** | ✅ 收紧 | 恒真 `or` 删、`len(claimed)==2` + rid 排序集合（test_pg_backend.py:137-140） |
| **P3-2 五列清空** | ✅ 补齐 | 新增双臂函数 `test_version_switch_clear_all_five_columns_zero_hits`（test_scaf_04:215-240）：五列各词先证在场→全清→四词零命中，sqlite=au 重写/pg=GENERATED 空向量同断言 |
| **P3-3 恶意 key 回归** | ✅ 补齐 | ×2：param_prefix 白名单 5 恶意值构造即拒（test_pg_scaff:580-588）+ 完整攻击配方（常量齐全/参数名全标识符/注释记号不入字面量外/恶意 key 仅转义字面量/双组织真实执行含空维度文档越权出口，:591-657） |
| **P3-8 门禁脚本** | ✅ 修复 | mktemp 模板以 X 结尾（GNU/BSD 通用，test_gate.sh:47）/ skip 检测完整 summary 行（:53-60）/ 无 summary 拦截（:61-64）/ pg 臂收集>0（:34-40）/ bash 3.2 local 声明分离 ✅。**三故障分支独立实证（临时副本注入，仓库文件未动）**：skip>0 → `GATE FAIL: summary 含 skipped` exit=1；pg 收集 0 → `GATE FAIL: 收集期未发现 [pg]` exit=1；无 summary → exit=1（见下观察项） |
| **P3-9 conftest finally** | ✅ 修复 | sqlite 分支 setup 包 try/finally（conftest.py:102-107），与 pg 分支同款纪律 |

## 4. 独立探针结果（不经测试代码，psycopg 直连生产代码 + 独立造数）

| 探针 | 结果 |
|---|---|
| **时区语义** | UTC session：-1h 过期滤除、+1h/NULL 保留（`('NA','OS')`）；Asia/Shanghai session：**+1h 有效授权被误杀**（`('NA',)`）——**P2-1 危害方向实证**，coder“提前 8h 误杀（非过期复活）”的精化推导正确：naive TIMESTAMP 按 session TZ 提升，上海解释=绝对时刻提前 8h |
| **public 对象** | psql 直查：audit 表/`lattice_audit%` 函数/`audit%` 触发器全部 **0 rows** |
| **分区 TRUNCATE** | `audit_no_truncate` 触发器在父表+当月分区两处在场；手动 TRUNCATE 双形态被拦、消息同源、行完好；探针 schema 自清零残留 |

## 5. 回归与边界复查

- **240→250 item 对账**：新增 10 条归属闭合 = P2-1×4 + P2-3×1 + P2-4×1 + P3-3×2（test_pg_scaff 8 函数）+ P3-2 双臂×2（test_scaf_04）；R1 的 239 passed 构成零触碰（pg_scaff 既有 10 函数只增不改断言面、pg_backend 仅 P3-1 收紧、scaf_04 纯新增）——**250 = 240 + 10，零删除零弱化**。
- **不做项零触碰**：P3-4/5/6/7/10/11 对应文件（postgres/acl_render.py、sqlite/acl_render.py、vec.py、connection.py 的 ensure_audit 静态化、datetime 契约）零 diff；docs/ 与 prototype/ 零 diff；`.env` 未入库（commit stat 无）；改动面恰为申报 8 files。
- **观察项（非阻塞，移交参考）**：门禁“无 summary”分支经临时副本实证 **exit=1 fail-closed 成立**，但实际退出路径是 `set -euo pipefail` 在 `summary=$(grep|tail)` 无匹配时的静默退出——`:61-64` 的 `GATE FAIL: 未解析到 pytest summary 行` 友好文案分支**不可达**（grep 无匹配→管道非零→赋值语句先触发 set -e）。安全性无缺口（绝不静默绿），仅诊断信息缺失；建议 M0b-3 顺手改为 `summary="$(grep … || true)"`。此观察不改判 P3-8 修复结论（申报的四种拒绝行为全部实测 exit=1）。
- R1 tester 报告遗留“过强表述②”（skip 检测分支缺实证）本轮已补：分支 1 即“DSN 语义在场但用例 skip”形态（旁路副本 DSN 检查 = 模拟该场景），GATE FAIL 文案 + exit=1 实证。
- 临时验证产物全部位于系统临时目录并已清理，仓库零残留。

## 6. 结论

P2×4 全部真实修复（双入口时区钉死/schema 生命周期闭合/水位 fail-fast/TRUNCATE 等价补齐），每条配真场景回归且经独立旁证复证；P3×5 逐条落地；R1 基线零弱化零删除；不做项零越界。

**testVerdict: PASS**
**testedSha: `53acea6a77227554fd39d087b4748dbc920ef79d`**

### Committer R2 复审报告原文（2026-10-24，reviewVerdict=APPROVED）

# Committer R2 复审报告：task-knowledge-lattice-m0b-1（M0b-1 PG 后端 spike）

## 1. 前置校验

| 项 | 结果 |
|---|---|
| HEAD = reviewedSha | ✅ `53acea6a77227554fd39d087b4748dbc920ef79d`（`develop_opencode`） |
| 父提交 | ✅ `329a099`（R1），与申报一致；`origin/develop`=f1beed5 为祖先 |
| diff 范围 | ✅ `git diff 329a099..HEAD` = 8 files / +495 / −38，与 R2 申报逐字一致 |
| 文件面 | ✅ `connection.py` / `migrate.py` / `audit.py` + 4 个测试文件 + `test_gate.sh`；无未申报文件 |
| docs/prototype | ✅ 零 diff；`.env` 未入库；无新增依赖；未 push |
| 工作区 | ✅ 仅 `.opencode/agent/*` modified + 检查点 untracked（工作流文件） |
| 测试复跑 | 未独立复跑（工具权限）；以 Tester R2 报告 + 静态审阅为准 |
| evidence manifest | ✅ `testedSha=53acea6`、R2 Tester 报告、R2 coder 记录齐备；`reviewedSha` 本轮置 53acea6；检查点 `reviewVerdict` 字段仍为 R1 的 NEEDS_CHANGES（待 supervised-coding 回写） |

R1 的「父提交表述」问题已由检查点 R1 异常澄清行（`236ff92` 为用户归档提交、`f1beed5` 为同步链基线）说明，不影响本次审查。

## 2. 结论

**reviewVerdict: APPROVED**

R1 的 P2×4 全部真实修复（连接工厂双入口钉 UTC / schema 生命周期闭合 / 迁徙水位 fail-fast / TRUNCATE 父子双落），P3×5 顺手项落地；未发现新 P1/P2；新发现均为 P3（测试可移植性/门禁文案/口径登记/覆盖补强）。用户拍板选项 A（连接工厂 `SET TIME ZONE 'UTC'`、`BEFORE TRUNCATE` 触发器）严格落地，未夹带未拍板方案（未改 TIMESTAMPTZ、未动 P3-4/5/6/7/10/11 对应实现）。

## 3. R1 意见处置核对表

| R1 项 | 处置 | 核对结论 |
|---|---|---|
| **P2-1 时区钉 UTC** | 已修正确 | `connection.py:74` `SET TIME ZONE 'UTC'` 落 `setup_connection`；`connect`（`:41-55`）与 `connect_pool` 的 `configure`（`:104-105`）同一入口。4 条回归（`test_pg_scaff.py:104-244`）：工厂重入、审计 DEFAULT 写入、`read_grants(now=None)` 过期判定、`ALTER DATABASE` 非 UTC 默认下池/单连接仍 UTC。Tester 独立探针实证「上海 session 下 +1h 有效授权被误杀」，危害方向与 R1 表述一致。拍板 A 命中，未改 TIMESTAMPTZ。**残留 P3**：`ALTER DATABASE` 测试硬编码库名/未保存原库默认（见 R2-P3-1）。 |
| **P2-2 public 生命周期** | 已修正确 | 两处工厂调用均传 `search_path=f"{pg_db.schema},public"`（`test_pg_scaff.py:57-61`、`:85`），并加 `current_schema()` 断言 + `_assert_public_free_of_audit_objects` 三面（表/触发器/函数）断言（`:27-47`、`:76`、`:98`）。R1 遗留 public 污染已由 coder 一次性清理，Tester psql 直查 0。**残留 P3**：该断言对「R1 遗留对象」非自清理，换环境跑前需保证 public 干净（见 R2-P3-4）。 |
| **P2-3 版本只前进** | 已修正确 | `migrate.py:79-104`：`MAX(applied)` 水位 + `_assert_forward_only` fail-fast；`_apply_one` `:135-146` 锁内重读全量 applied 集合同款校验。回归 `test_pg_scaff.py:384-427`：先 0003 后补 0002 → `MigrationError`、0002 DDL 零执行、水位仍 `[(1,),(3,)]`。**残留 P3**：锁内复核分支未被独立用例覆盖（外层 fail-fast 先命中），代码静态审阅正确（见 R2-P3-5）。 |
| **P2-4 TRUNCATE 等价** | 已修正确 | `audit.py:66-79` 新增 `lattice_audit_append_only_truncate` + `audit_no_truncate`；`:113-117` 父表显式落，`:126-131` **每个分区**经 `ensure_month_partition` 显式落。PG 16「父表 statement 触发器不克隆、不拦分区直 TRUNCATE」的声明与 PG 行为一致；`test_pg_scaff.py:247-268` 父表/分区双形态 raises、行完好。**残留 P3**：消息为「audit_events is append-only; TRUNCATE is forbidden」，与 SQLite 既有文案非逐字（Tester 按「同源词根」验收）；R2 新增的分区触发器未回溯 R2 之前已存在的分区（见 R2-P3-3/8）。 |
| **P3-1 弱断言** | 已修正确 | `test_pg_backend.py:137-140`：`len(claimed)==2` + `rids=sorted(...)`，原恒真 `or` 删除，pending 对照仍成立。 |
| **P3-2 PG 五列清空** | 已修正确 | `test_scaf_04_triggers.py:215-240` 新增双臂 `test_version_switch_clear_all_five_columns_zero_hits`：五词先在场 → 五列全清 → 四词零命中；sqlite=au 重写 / PG=GENERATED 空向量。 |
| **P3-3 PG 恶意 key** | 已修正确 | `test_pg_scaff.py:581-589`（共享 `InValue` 白名单 5 恶意值构造即拒）+ `:592-659`（完整攻击配方：常量齐全/参数名全标识符/注释记号不入字面量外/恶意 key 仅转义字面量/双组织真实执行仅 `d_tax`）。PG 侧安全纪律锁死。 |
| **P3-8 mktemp/summary/pg 收集** | 已修（带 P3 观察） | `test_gate.sh:47` `mktemp` 模板以 `XXXXXX` 结尾（GNU/BSD 通用）；`:53-60` 完整 summary 匹配；`:34-40` `[pg]` 收集 >0；`:55`/`:61` 无 summary 分支。Tester/观察：`:55` 的 `summary=$(grep|tail)` 在 `set -euo pipefail` 下无匹配即 exit 1，**fail-closed 成立但 `:61-64` 友好文案不可达**（建议 M0b-3 `|| true`）；另 `PG_COLLECTED` 仅计 `[pg]` 参数化，PG 专用 `pg_db` 测试未计入（见 R2-P3-7）。 |
| **P3-9 conftest finally** | 已修正确 | `conftest.py:102-107` sqlite 分支 `try/finally` 关闭连接，与 pg 分支同纪律。 |
| **P3-4/5/6/7/10/11** | 未修（按拍板移交） | 与用户 spec 一致：P3-4/5/6 → M0b-3，P3-7 → M1 池化，P3-10 → M1 API，P3-11 → M0b-3 收口。**登记注意**：R2 为 P2-4 在 `ensure_audit`/`ensure_month_partition` 增加了 truncate function/trigger DDL，P3-7 的每连接 DDL 负担略增（仍按 M1 移交）；R2/Tester「P3-7 对应文件零 diff」表述不准确（`connection.py`/`audit.py` 因 P2-1/P2-4 有 diff，只是特定静态化未做）。 |
| **P3-12 检查点措辞** | 已修（澄清） | 检查点 R1 异常澄清行（`236ff92` 为归档提交、`f1beed5` 为同步基线）已说明；R1 记录正文仍保留「父提交=f1beed5」原文——属历史记录，不影响审查；若要求逐字修正可后续归档回写。 |

**历史意见防回归（R1 报告第五节结论仍成立）：**
- **M0a-2 P1-1（渲染器自控参数名/白名单）**：`acl_ast.py`/`postgres/acl_render.py` 本轮零 diff；新增 PG 恶意 key 测试反而加固。✅
- **M0a-2 P2-1（read_grants 维度归属校验）**：`postgres/backend.py` 零 diff；PG 臂 malformed-grant 回归仍缺（R1 已记录，非本轮范围）。✅ 无回退
- **M0a-2 P3-1（visible_docs 不读 dim.status）**：`acl_ast.py` 零 diff。✅
- **M0a-2 P3-7（migrate finally）**：`_apply_one` 异常 ROLLBACK 路径未改；P2-3 仅新增水位校验。✅
- **M0a-3 P2-3/P3-7（write_embeddings/pending_dims）**：`postgres/backend.py` 零 diff。✅
- **M0a-1 选项 A 骨架**：`backend`/`matrix` fixture 行为未改，仅 sqlite 分支加 finally。✅
- **P3-17**：`store/backend.py` 零 diff。✅

## 4. 新发现（P1 / P2 / P3）

### P1（必修）— 无

### P2（应修）— 无

### P3（记录 / 可移交）

**R2-P3-1｜`ALTER DATABASE` 测试硬编码库名且不保存原库默认**
- 文件：`tests/test_pg_scaff.py:217-236`
- 问题：`ALTER DATABASE lattice SET timezone TO 'Asia/Shanghai'` 硬编码 `lattice`（DSN 指向其他库时改错库/探针失败）；finally 用 `RESET timezone` 回到**服务器默认**而非**原库默认**（若目标环境本就配置了非 UTC 库默认，会被测试改掉）；该语句还需库 owner 权限。当前任务 DSN 固定 `/lattice`、容器默认 UTC，故测试通过。
- 建议：用 `SELECT current_database()` 构造 `ALTER DATABASE <ident>`（标识符引用）；先 `SELECT setting FROM pg_db_settings...` 或 `pg_database.datconfig` 保存原 `timezone`，finally 恢复原值；owner 前置失败时 skip 或明确错误。测试-only，不阻塞本轮。

**R2-P3-2｜门禁「无 summary」友好文案不可达**
- 文件：`scripts/test_gate.sh:55-64`
- 问题：`summary="$(grep … | tail -1)"` 在 `set -euo pipefail` 下无匹配即 exit 1，`if [[ -z "$summary" ]]` 的 `GATE FAIL: … 未解析到 pytest summary 行` 永不执行。**fail-closed 成立（不会静默绿）**，仅诊断信息缺失。
- 建议：M0b-3 改 `summary="$(grep … | tail -1 || true)"`，让友好分支可达；同时可把 `summary` 解析限定在 pytest 末尾汇总段。Tester 已记录，非本轮阻塞。

**R2-P3-3｜TRUNCATE 异常消息「同源」口径**
- 文件：`src/.../store/postgres/audit.py:66-79`
- 问题：新消息为 `audit_events is append-only; TRUNCATE is forbidden`，与 SQLite `audit_events is append-only`（UPDATE）/`…; retention via monthly file rotation`（DELETE）非逐字；用户拍板要求「消息同源」，Tester 按「含 append-only 同源词根」验收。功能无差异（测试 `match="append-only"`）。
- 建议：由 supervised-coding 在勘误/口径回写中确认「同源词根」口径；若要求逐字，改为与 SQLite DELETE 版同文案或统一前缀。记录项，不阻塞。

**R2-P3-4｜public-free 断言对 R1 遗留对象非自清理**
- 文件：`tests/test_pg_scaff.py:27-47`、`:76`、`:98`
- 问题：断言检查 `public` 全部 `audit%` 表/触发器/`lattice_audit%` 函数；R1 遗留的 public 污染已由 coder 一次性 psql 清理，但测试自身不清理。换环境/R1 污染库上跑会失败（且失败原因不是本轮代码泄漏）。
- 建议：在 `_pg_db` 或 session fixture 增加 public audit 对象清理（幂等），或检测到 R1 遗留时先清理再断言；测试-only，P3。

**R2-P3-5｜锁内 `_assert_forward_only` 分支无独立用例**
- 文件：`src/.../postgres/migrate.py:135-146`
- 问题：`test_pg_migration_out_of_order_rejected` 在**外层** `_assert_forward_only` 就抛错，`_apply_one` 锁内重读后的乱序校验分支未被真实触发；并发测试（`test_pg_concurrent`）走正常 v2。代码静态审阅正确，但该分支属 P2-3 的核心并发防线，建议补：先让外层检查通过、再由并发连接在锁内看到更高水位 → 触发锁内 fail-fast（可在测试内直接调用 `_apply_one` + 预置更高 version 模拟）。
- P3 覆盖补强。

**R2-P3-6｜P3-7 每连接 DDL 负担略增，R2/Tester「零 diff」表述不准确**
- 文件：`src/.../postgres/connection.py:79`（`ensure_audit` 入口）、`audit.py:92-…`（新增 function/triggers）
- 问题：R2 为 P2-4 在 `ensure_audit`/`ensure_month_partition` 增加了 truncate function/trigger 的 `CREATE OR REPLACE`/`DROP`+`CREATE`，每次建连/滚动执行；P3-7（ensure_audit 静态化到 M1）未做，但**负担比 R1 略增**。R2 记录/Tester「P3-7 对应文件零 diff」不准确——`connection.py`/`audit.py` 因 P2-1/P2-4 有 diff，只是 P3-7 的特定静态化未做。
- 建议：移交 M1 池化时把「P3-7 含新增 truncate DDL」写清楚；M0b-3 可评估把静态对象（function/row/truncate triggers）与月分区分离。记录项。

**R2-P3-7｜门禁 `PG_COLLECTED` 只计 `[pg]` 参数化，PG 专用测试未计入**
- 文件：`scripts/test_gate.sh:35`
- 问题：`grep -c '\[pg\]'` 只覆盖 `backend` 参数化的 45 组；R1 的 23 条 + R2 的 8 条 `pg_db` 专用测试（时区/TRUNCATE/迁移/安全）不在计数内。若这些测试被删/未被收集，门禁不报；skip 检测仍能拦住「未跑而 skip」，但删测试漏检。
- 建议：再断言「PG 专用测试收集数 ≥ 预期」或总计 item 数（与 250 对账）；或至少把 `pg_db` 用例的 node id 计数纳入。另：`PG_COLLECTED` 在 `uv`/`grep` 异常时可能为空，`[[ "" -eq 0 ]]` 建议改 `${PG_COLLECTED:-0}`。P3。

**R2-P3-8｜R2 之前已存在的审计分区无 TRUNCATE 触发器回溯**
- 文件：`src/.../postgres/audit.py:101-117`
- 问题：`ensure_audit` 只为「当月」分区落触发器；R2 之前已存在的其他月份分区（若有）不会被回溯补齐，旧分区直 TRUNCATE 仍不拦。当前 R1 是 spike、无生产分区，测试每 schema 新建，故无实际触发；但升级/deploy 场景需一次 `ensure_month_partition` 全月回填或迁移。
- 建议：M0b-3/M2 迁移说明中登记「对历史分区执行一次 ensure_month_partition（或 `ALTER TABLE … ENABLE TRIGGER` 批量补）」；P3。

**其余记录：** `test_pg_timezone_audit_default_now_writes_utc` 的 session 恢复未放 `finally`（函数级 fixture，不跨测例）；`test_pg_invalue...` 无 `pg_db` 却放 PG 文件（组织性）；`_assert_public_free...` 的 `LIKE 'audit%%'` 依赖 psycopg 的 `%%` 处理（当前行为正确）——均 P3/记录级，不逐条展开。

## 5. 拍板符合性与需求边界问题

**拍板符合性：✅ 全部落在用户确认范围内**
- **时区选项 A**：`SET TIME ZONE 'UTC'` 落连接工厂（单连接 + pool configure 同入口），未改 `TIMESTAMPTZ`；展示分工「后端 UTC ISO / 前端本地化」仅注释登记（真正前端代码随 M2 界面）。✅
- **TRUNCATE 选项 A**：补 `BEFORE TRUNCATE FOR EACH STATEMENT`，父表 + 每分区显式落；PG 16 不克隆的声明经 Tester 手动旁证。消息「同源」存在 R2-P3-3 的口径细节，功能与测试匹配 `append-only`。✅（口径待 supervised-coding 确认）
- **P3 分配**：P3-1/2/3/8/9 已修；P3-4/5/6/7/10/11 未触碰；无 P3-4/5/6/7/10/11 夹带。✅
- **无未拍板方案**：未引入 TIMESTAMPTZ、未改 HNSW/halfvec、未动 ACL 渲染/backend、未动 docs。✅

**需求边界问题：无新的实质规格矛盾。**
- 仅 1 条**口径待确认**（非代码缺陷）：TRUNCATE 异常消息的「同源」是「同源词根」还是「逐字同文案」——Tester 按前者验收；若用户要求逐字，需 supervised-coding 在勘误回写中明确（P3）。
- TEST-CASES TC-SCAF-02~05 后端行回写、验收 6 的 M0a-1/2/3 勾选回写仍属 supervised-coding 动作（检查点 line 88 已登记 TEST-CASES；M0a 勾选本轮未见执行记录，交付前需补）。
- 「无 summary 分支」属工具打磨（fail-closed，非规格缺口）；`ALTER DATABASE` 测试属测试可移植性，均 P3。
- 调研借鉴无新增结论：R2 改动（时区/迁移水位/TRUNCATE）不触及 research 的 pgvector 精确扫描、应用层 jieba、审计分区、不引 zhparser 等选型结论，无新缺口。

## 6. Tester R2 报告核对

**属实/可信：**
- 8 files / +495/−38；`249 passed + 1 skipped`（pg 臂 0 skipped）；`250 = 240 + 10`：新增 8 个 `test_pg_scaff` 函数 + `test_scaf_04` 双臂 = 10；参数化 45+45=90、非参数化 159 — 静态复算成立。
- P2×4 每条均有真场景回归：时区 4 条（含 `ALTER DATABASE` 非 UTC 默认对照）、public 三面、0003→0002 乱序、TRUNCATE 父表/分区；P3-1/2/3/8/9 逐条落地。
- 独立旁证（时区上海 session +1h 有效授权误杀、public psql 0、分区 TRUNCATE 手拦）与代码一致；「R1 过强表述②」（skip 分支）已由临时副本注入补实证。
- 环境终态（public/lattice_test%/probe 0、库级 TimeZone 还原）与检查点一致。
- Tester 的「无 summary 分支经 set -e 静默退出、fail-closed、友好文案不可达」观察**定性正确**（`test_gate.sh:55` 的赋值在 `set -e` 下先退出；`:61-64` 不可达）。

**需修正/注意（不推翻 PASS）：**
1. **「不做项零 diff / P3-7 对应文件零 diff」表述过强**：`connection.py`/`audit.py`/`migrate.py` 因 P2-1/P2-4/P2-3 有 diff；P3-6/P3-7/P3-11 的**特定改动**未做属实，但不能说对应文件零 diff；且 P3-7 的每连接 DDL 因 truncate 新增而略增（见 R2-P3-6）。
2. **「P2-3 锁内重读」**：代码在，但测试只覆盖外层 `_assert_forward_only`；锁内分支是静态审阅通过，非实跑覆盖（R2-P3-5）。
3. **「PG 臂 45 组」**：仅 `[pg]` 参数化；PG 专用 `pg_db` 测试（R1 23 + R2 8）不在门禁计数（R2-P3-7）。
4. **「ALTER DATABASE 已还原」**：在容器默认 Etc/UTC 下成立；测试用 RESET 到服务器默认、硬编码 `lattice`，不是保存/恢复原库默认（R2-P3-1）。
5. **TRUNCATE 消息「同源」**：Tester 按「同源词根」验收；与 SQLite 非逐字（R2-P3-3）。
6. `test_pg_invalue...` 放 `test_pg_scaff.py` 但无 `pg_db`（组织性，非缺陷）。

## 7. 移交项登记核对

| 项 | 登记情况 | 结论 |
|---|---|---|
| P3-4 jsonb 标量守卫 | 检查点 line 88 → M0b-3 | ✅ 已登记；`postgres/acl_render.py` 零 diff |
| P3-5 sqlite dot-key | line 88 → M0b-3 | ✅ 已登记；`sqlite/acl_render.py` 零 diff |
| P3-6 schema_migrations 锁外竞态 | line 88 → M0b-3 v1.1 | ✅ 已登记；`migrate.py` 因 P2-3 有 diff，但 `_ensure_schema_migrations` 位置未动 |
| P3-7 ensure_audit 每连接 DDL | line 88 → M1 池化 | ✅ 已登记；R2 新增 truncate DDL 使负担略增，建议在交接中补一句（R2-P3-6） |
| P3-10 datetime 序列化契约 | line 88 → M1 API | ✅ 已登记；`postgres/backend.py` 零 diff |
| P3-11 未使用清理 | line 88 → M0b-3 收口 | ✅ 已登记；`connection.py` 因 P2-1 有 diff，但未使用项未动 |
| P3-12 检查点措辞 | R1 异常澄清行 | ✅ 已澄清；R1 记录正文仍留原文（历史记录） |
| TEST-CASES TC-SCAF-02~05 后端行 | line 88 → supervised-coding 收口回写 | ✅ 已登记；docs 零 diff |
| M0a-1/2/3 勾选回写（验收 6） | 检查点未见执行记录 | ⏳ supervised-coding 交付前动作；非本轮代码问题 |
| **R2 新 P3（建议补登记）** | 本报告 R2-P3-1~8 | 建议 supervised-coding 将 **R2-P3-1（ALTER DATABASE 测试）、R2-P3-2（no-summary `|| true`）、R2-P3-3（TRUNCATE 消息口径）、R2-P3-4（public 清理）、R2-P3-7（PG_COLLECTED 范围）、R2-P3-8（历史分区回溯）** 补入 M0b-3/M1 移交清单；R2-P3-5（锁内覆盖）按测试补强；R2-P3-6 在 P3-7 条目加注。 |

## 8. reviewedSha

```
reviewedSha: 53acea6a77227554fd39d087b4748dbc920ef79d
```

**CASE_BUG 裁定**：未收到 tester 的 CASE_BUG 裁定请求，无裁定。

**放行说明**：R2 复审 APPROVED；不执行 `gh pr review`/push（未到用户确认交付阶段）。P3 为记录/移交项，不阻塞交付；建议 supervised-coding 在收口时把 R2 新 P3 补入移交清单，并完成 TEST-CASES 回写与 M0a-1/2/3 勾选回写（验收 6）。
