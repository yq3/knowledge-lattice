# knowledge-lattice · 企业知识层

> 给 Agent 供数的企业知识层（通用平台、领域无关；首个落地场景为税务）：**文档知识**（制度/口径/手册的权限内检索）+ **业务语义**（术语与业务对象关系），一个服务、一个 MCP server。私有化部署，SQLite 开箱即用，PostgreSQL+pgvector 可选，无 GPU 可跑。

**一句话判断**：如果你要的是「按组织 / 知识库 / 数据维度授权、能被 agent 稳定调用的内网知识层」，而不是又一套聊天式 RAG 产品，这个仓就是为此写的。

`POC · 单服务 · 2 种存储后端 · 8 个 MCP 工具 · 2 种认证形态 · SQLite 形态零中间件`

> 名字释义：lattice（晶格）——知识单元（chunk）按结构有序排列成格；**格子是本体，检索是在格上寻位**。文档上架是晶体生长，索引是晶格结构，可重建、可演化。并入业务语义层后，"lattice"同时描述**文档知识 + 业务对象关系图**这种有结构的知识网络，名字比以前更贴切（#35 §4.1）。

## 快速开始：先把控制台跑起来

前置：Python 3.11+（`.python-version` 钉 3.12.10，uv 按需自动拉取——开发 = 部署同版本）与 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync                                                       # 安装依赖（uv.lock 锁定、必须提交）
[ -f .env ] || cp .env.example .env                            # 环境变量模板（已有则保留；经 --env-file 注入，不自动读取）

# 无 IdP 的开箱形态（local：内置账号 + 邀请制）；默认是 sso，行为零变化
# 写入 .env（密钥只生成一次，重启不失效；生产请用部署侧密钥管理）
cat >> .env <<EOF
# 开箱形态：内置账号（local）——覆盖模板中的 sso 缺省
LATTICE_AUTH_MODE=local
LATTICE_SESSION_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
EOF

uv run uvicorn "knowledge_lattice.app:create_app" --factory --env-file .env
```

**成功标志**：终端出现 `Uvicorn running on http://127.0.0.1:8000`；打开 <http://127.0.0.1:8000/> 看到 **Setup 屏**（空库），建首个 `sysadmin`（可同事务建首组织并任 `org_admin`）。

无浏览器时也可以确认进程已就绪：

```bash
curl -s http://127.0.0.1:8000/api/auth/config
# 空库应看到：{"auth_mode":"local","setup_needed":true,...}
```

建好管理员后 `setup_needed` 变为 `false`。无浏览器建号的 REST 示例见 [RUNBOOK §1.ab](RUNBOOK.md)。

### 让 Agent 连上（可选）

`local` 形态用 Agent 密钥；`sso` 形态走 D18 委托/可信 token。

1. 登录控制台 → 左栏「Agent 密钥」→ 为 agent 绑定成员签发 key（`lka_...` 明文只显示一次）；
2. 左栏「运维 → MCP 接入」复制客户端配置。

然后在仓库根目录自检：

```bash
export LATTICE_MCP_KEY="lka_..."
uv run python scripts/mcp_smoke.py --url http://127.0.0.1:8000/mcp
# tools: search, fetch, upload, list_documents, annotate, get_entity, search_entities, describe_table
```

接入细节（客户端配置、工具清单、上传三步、排错）见 [docs/MCP-INTEGRATION.md](docs/MCP-INTEGRATION.md)。

> 没有模型端点也能启动（启动时会有一条探针失败 ERROR 日志，属预期）；向量检索需要 OpenAI 兼容的嵌入端点，不可达时检索降级 BM25 单路（`notice.degraded` 可见）。

### 接口与认证

- REST API 文档 `http://127.0.0.1:8000/docs`；MCP 端点 `/mcp`（Streamable HTTP）。
- 认证模式切换、邀请 / 重置 / break-glass 见 [RUNBOOK §1.ab](RUNBOOK.md)；Agent 密钥运维见 [§1.ac](RUNBOOK.md)；控制台时区见 [§1.ad](RUNBOOK.md)。
- 开发 JWT：dev/test 下 `POST /api/dev/token` 以现有 Bearer 重签或代签（生产 404）。

## 它解决什么问题

三件事，通用 RAG 方案通常只覆盖其中一段：

1. **文档级权限缺位**：调研的开源五平台（ragflow / dify / anything-llm / quivr / kotaemon）文档级权限全部缺位。企业要的是「组织 × 知识库 × 数据维度」组合授权，不是目录权限。
2. **术语与口径对不齐**：同一业务术语在不同系统可能有不同叫法、编码与层级；光有文档检索，agent 仍然会在术语和对象关系上猜。
3. **agent 要的是工具面，不是聊天框**：agent 住在客户端，知识层应该提供可信任的检索、溯源与鉴权工具，而不是再做一个聊天 UI。

knowledge-lattice 把这三件事收进同一个服务：文档与语义同库、同一套认证与审计、同一个 MCP server。

## 适合谁 / 不适合谁

**适合**：

- 要在内网私有化部署知识层，给 Agent（deepagents 等任意 MCP 客户端）供数的团队；
- 需要按组织 / 知识库 / 数据维度做权限，而不是目录级权限；
- 已有 OpenAI 兼容的嵌入端点（重排可选），或能接受 BM25 降级；
- 想同时管文档知识与业务术语 / 对象关系，但不想引入图数据库、ES 或 GPU。

**不适合（诚实声明）**：

- 想要开箱即用的 SaaS 知识库或聊天产品——本仓是服务端，控制台只做管理与检索测试；
- 需要 GraphRAG 多跳推理或图数据库——业务语义是类型化对象图，关系展开 SQL 可达；
- 没有内网模型端点，且不能接受 BM25 降级；
- 需要公开注册、计费或多租户运营面板的 SaaS 形态——POC 是单实例部署（local 为邀请制）。

## 能力一览

| 层 | 现在能做什么 | 入口 |
|---|---|---|
| **文档知识** | 多组织 → 知识库 → 文档三层；维度 ACL 编译进检索；BM25 + 向量 + RRF + rerank；上传 / 版本 / 删除 / 重索引；引用溯源 | MCP `search` / `fetch` / `upload` / `list_documents`，REST（管理面 / 上传 / 检索） |
| **业务语义** | 概念 / 系统 / 场景 / 模板 / 模板字段 / 报表 / 报表项 / 表 / 列九类实体的类型化对象图；源端事实每日从业务系统同步（REST / MCP），人工别名 / 口径走 Git YAML 覆盖层；术语识别、实体检索、关系展开 | MCP `annotate` / `search_entities` / `get_entity` / `describe_table` |
| **治理与运维** | local / sso 双认证形态；Agent 密钥；查询级审计；备份恢复；重嵌入蓝绿；评测框架 | 控制台「任务与审计」「Agent 密钥」「MCP 接入」；[RUNBOOK.md](RUNBOOK.md) |

> 控制台页面：业务语义（默认落地）/ 文档知识 / 检索测试 / 维度与权限 / 用户与邀请（local）/ Agent 密钥（local）/ 组织 / 任务与审计 / MCP 接入；中 / 英双语。

## 三个设计硬选择

1. **权限先于召回**：ACL 编译成可见文档集，查询时在引擎内先过滤后距离；不信任 agent 传来的权限字段，也不做「先召回再过滤」。
2. **语义与文档同服务**：文档块与实体同库、同 MCP、同审计；术语 / 口径的人工内容走 Git YAML 覆盖层。不做 GraphRAG、不引入图数据库。
3. **索引是投影**：向量索引可重建；换嵌入模型走蓝绿（新旧标签并存 → 覆盖率 100% → 原子切 → 旧标签清理），BM25 全程可用。

设计推导与取舍见 [docs/design.md](docs/design.md)；决策编号（D1~D26）与需求条目见 [docs/requirements.md](docs/requirements.md)。

## 按角色进入

- **平台 / 运维**：先看 [RUNBOOK.md](RUNBOOK.md)——重嵌入蓝绿、备份恢复、组织停用、查询审计、内置账号、Agent 密钥、控制台时区。
- **Agent 开发**：看 [docs/MCP-INTEGRATION.md](docs/MCP-INTEGRATION.md)；控制台「运维 → MCP 接入」是同一内容的实例化向导。
- **设计 / 评审**：按 [requirements](docs/requirements.md) → [design](docs/design.md) → [TEST-CASES](docs/TEST-CASES.md) 的顺序；完成态看 TEST-CASES §六，开放缺口看 [known-gaps](docs/known-gaps.md)。

## 现在到什么程度

POC 阶段，2026-10-28 自 lab 仓拆仓；M0a / M0b / M1 / M2 / M3 / M4 均已交付；D26 local 形态 Agent 密钥已合入。当前门禁 **2190+1** 用例（+1 = `manual` 组 deselected），sqlite + pg 双后端 × 常规 / `python -O` 双模式 0 skipped（pg 臂 809；数字随批次变化，以最近检查点为准）。

尚未完成的主要是用户侧人工走查（TC-UI / TC-KEY）、评测真实数据补跑（chat 端点配额）与部署期联调（真实 IdP / rerank 网关 / 生产 PG）。逐项状态以 [TEST-CASES §六](docs/TEST-CASES.md) 与 [AGENTS.md](AGENTS.md) §1 为准；M3 按用户裁定的受限句式宣告。开放待决项（真实样例语料 / 企业 SSO 协议 / agent 侧 token 换取）见 [requirements §9](docs/requirements.md)。

交付记录：M4 PR #29；D26 PR #35；2026-11-22 用户走查批 PR #36/#37。

## 深入阅读

| 文档 / 目录 | 角色 |
|---|---|
| [docs/requirements.md](docs/requirements.md) | 需求正文（FR / NFR / D 编号源头） |
| [docs/design.md](docs/design.md) | 方案设计（架构 / DDL / ACL 编译 / MCP 契约 / 里程碑分解） |
| [docs/TEST-CASES.md](docs/TEST-CASES.md) | 验收用例展开层 + §六里程碑对照表；活文档 |
| [docs/known-gaps.md](docs/known-gaps.md) | 已预见问题登记（G-n）；活文档 |
| [RUNBOOK.md](RUNBOOK.md) | 运维手册（重嵌入 / 备份恢复 / 审计 / 账号 / Agent 密钥 / 控制台时区） |
| [docs/MCP-INTEGRATION.md](docs/MCP-INTEGRATION.md) | Agent 侧 MCP 接入指南（端点 / 认证 / 客户端配置 / 工具清单 / 上传 / 排错） |
| [prototype/index.html](prototype/index.html) | 交互原型（mock 数据）：信息结构与 UI 风格双基准 |
| [AGENTS.md](AGENTS.md) | 工作规范（冻结纪律 / 分层纪律 / 工具链 / 提交约定） |
| `benchmarks/` | 实验 / 压测脚本与报告归档（结论回写 known-gaps 或正文） |
| `eval/` | 评测语料、黄金集与报告归档 |
| lab 仓 | 调研基础：[enterprise-rag](https://github.com/yq3/lab/tree/main/research/enterprise-rag/)、[glossary-agent](https://github.com/yq3/lab/tree/main/glossary-agent) |

需求 / 设计正文的版本号与冻结纪律见 [AGENTS.md](AGENTS.md) §2；版本号以各文档头部为准，里程碑完成态以 [TEST-CASES §六](docs/TEST-CASES.md) 为准。

## 本地开发

```text
src/knowledge_lattice/
├── app.py            # FastAPI 入口（create_app 工厂：路由 + MCP 挂载 + 静态页壳 + 指纹探针）
├── config.py / log.py
├── tzdisplay.py      # 控制台显示时区解析（存储/接口恒 UTC，仅展示换算）
├── query_audit.py    # 查询级审计异步队列（m3-2）
├── core/docs/        # 文档域业务（ingest / chunking / retrieve / acl / quality / credentials…）
├── core/semantic/    # 业务语义域（D23 并入）——与 core/docs 包级互斥
├── domain/           # 身份 / 账号 / agent key / 审计事件域模型（auth / accounts / agent_keys / audit_events / models）
├── store/            # StorageBackend 协议 + sqlite/ postgres/ 双方言包（迁移 / FTS / 向量 / ACL 渲染 / 审计）
├── adapters/         # 外置依赖适配（embedder / reranker / auth_sso / parser_docling / tokenizer / breaker…）
├── api/              # REST 端点（upload / documents / tasks / search / semantic / quality / admin / auth / users / agent_keys）
├── mcp/              # MCP server（docs + semantic 两组工具）
├── web/              # 前端薄壳（原生 HTML/JS/CSS + i18n.js 中英双语——FR-8，无构建链；含 Agent 密钥 / MCP 接入视图）
└── worker/           # 任务子进程（ingest / reindex / reembed / semantic_sync·build·retag + maintenance；delete 预留）
scripts/              # 门禁与评测脚本（test_gate.sh / eval_*.py / reset_admin.py / mcp_smoke.py）
tests/                # 按模块前缀命名（acl_/ing_/fts_/emb_/e2e_/pg_…），双后端参数化（[pg] 条目）
```

分层纪律（core 不写方言 SQL、core 两包互斥）与模块边界的权威定义见 design §3，速览见 [AGENTS.md](AGENTS.md)。

测试：

```bash
uv run pytest                    # sqlite 默认后端，无需容器（TC-UI 手动走查组带 manual 标记、默认跳过）
# 全量门禁（双后端 + 常规/python -O 双模式，skip=失败——不建 CI，本地承接）：
docker start lattice-pg
export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
scripts/test_gate.sh
```

TC-UI 手动走查步骤见 [TEST-CASES §二 TC-UI 组](docs/TEST-CASES.md)；新壳视图 + 原型对照的详细清单见 [report-ui3-tc-ui-walkthrough.md](benchmarks/report-ui3-tc-ui-walkthrough.md)（其造数脚本为开发期 `/tmp` 形态、未入库，执行前需自备样例数据）；M4 登录/邀请页见 TC-UI-06·07，时间显示见 TC-UI-08，Agent 密钥 / MCP 接入页见 TC-KEY-08·09。

## License

[MIT](LICENSE)
