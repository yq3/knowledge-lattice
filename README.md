# knowledge-lattice

企业知识层（通用平台，领域无关——首个落地场景为税务）：提供两类能力——**文档知识**（制度、口径、手册的权限内检索）和**业务语义**（术语识别、业务对象及其关联）。以单一服务、单一 MCP server 的形式提供给 Agent，供数为主、人工检索为辅。

> 名字释义：lattice（晶格）——知识单元（chunk）按结构有序排列成格；**格子是本体，检索是在格上寻位**。文档上架是晶体生长，索引是晶格结构，可重建、可演化。并入业务语义层后，"lattice"同时描述**文档知识 + 业务对象关系图**这种有结构的知识网络，名字比以前更贴切（#35 §4.1）。
>
> **知识层定位（2026-10-18 D23 修订，取代 2026-10-16「双层分立」口径）**：文档知识层与业务语义层（术语 + 业务对象的类型化对象图）**同服务归一**——术语层原定的独立 glossary-agent MCP server 部署形态取消，并入本系统 `core/semantic/` 模块（[requirements.md D17/D23](docs/requirements.md)）；[glossary-agent（lab 仓）](https://github.com/yq3/lab/tree/main/glossary-agent) 转为调研与设计沉淀，其结论是 semantic 模块的设计输入。

## 文档地图

| 文档 / 目录 | 角色 |
|---|---|
| [docs/requirements.md](docs/requirements.md) | 需求正文（FR / NFR / D 编号源头——**先读这份**） |
| [docs/design.md](docs/design.md) | 方案设计（架构 / DDL / ACL 编译 / MCP 契约 / §8 里程碑分解） |
| [docs/TEST-CASES.md](docs/TEST-CASES.md) | 验收用例展开层：design §9 冻结 T / T-S 编号展开 + 模块 TC-\* 用例 + §六里程碑验收对照表；活文档 |
| [docs/known-gaps.md](docs/known-gaps.md) | 已预见问题登记（G-n）：对策之后仍残留的缺口与规格开放点；活文档 |
| [prototype/index.html](prototype/index.html) | 交互原型（浏览器直接打开、mock 数据）：信息结构与 UI 风格**双基准** |
| [RUNBOOK.md](RUNBOOK.md) | 运维手册（重嵌入蓝绿与供应商切换 / 组织停用 / 查询审计 / 评测 / 内置账号 / 审计分区 / 迁移 / 备份恢复）；运行侧活文档 |
| [AGENTS.md](AGENTS.md) | 工作规范（冻结纪律 / 分层纪律 / 工具链 / 多 Agent 工作流与提交约定） |
| `benchmarks/` | 实验 / 压测脚本与报告归档（report-\*.md，结论回写 known-gaps 或正文） |
| `eval/` | 评测语料（corpus.jsonl / semantic_golden.jsonl）、黄金集（golden.jsonl）与报告归档（reports/） |
| lab 仓 | 调研基础：[enterprise-rag 调研](https://github.com/yq3/lab/tree/main/research/enterprise-rag/)（22 仓源码级调研 + 四厂商第一方实践）、[glossary-agent](https://github.com/yq3/lab/tree/main/glossary-agent)（术语层调研沉淀） |

**版本口径**：需求 / 设计两正文随实现勘误高频升版，**具体版本号与变更史以各文档头部为准**，本 README 不复述；里程碑完成态以 [TEST-CASES §六对照表](docs/TEST-CASES.md) 为准。**设计冻结纪律**：`docs/` 需求与设计正文仅在决策变化时修改（决策变更走 issue + D 编号），实现问题走测试用例与 issue；TEST-CASES / known-gaps / RUNBOOK 为活文档、随实现回写。拆仓前的设计评审 issue（#31~#42）均在 lab 仓，本文链接为绝对地址。

## 一句话定位

私有化部署的轻量知识层服务：单进程 + 存储后端双实现（SQLite 默认，零中间件 / PostgreSQL+pgvector 可选——D24），嵌入与重排经 OpenAI 兼容 API（D12 修订）、无 GPU 可跑；**文档知识**——**多组织 → 多知识库 → 文档（维度 ACL）** 三层结构；**业务语义**（D23，M2-S 起）——概念/系统名词/场景/模板/模板字段/报表项/表/列组成的类型化对象图（源端事实每日从业务系统同步——REST 或 MCP 传输均可，人工内容 Git YAML 覆盖层，不做 GraphRAG、不引入图数据库）。两者通过同一个 MCP server（docs 组 + semantic 组工具）给 deepagents 供数（代人检索、按数据维度过滤权限、术语识别与对象关系展开），并提供上传、检索与管理页面（原型级实装）。

## 项目状态

POC 阶段，独立仓库演进——2026-10-28 自 lab 仓拆仓。

- **M0a / M0b / M1 / M2 / M3 / M4 均已交付**（M4 于 2026-11-21 经 PR #29 合入 `develop`；M3 按用户裁定 N-4 受限句式宣告）。逐段证据与完成态见 [TEST-CASES §六对照表](docs/TEST-CASES.md)；段序档案见 `.opencode/workflows/_m2-plan.md`、`_m3-plan.md`、`_m4-plan.md`。
- **仍未勾的验收项**（用户侧 / 部署期，不阻塞已交付代码）：
  - TC-UI 人工走查：M1 / M2 / M3 达成宣告共同待勾 + M4 TC-UI-06·07（`manual` 组不进门禁）。
  - 评测真实数据（chat 端点配额受阻）：TC-EVAL-02 LLM 候选占比、TC-EVAL-03 真实校准与 A-6 阈值、响应层真实基线——配额恢复后补跑。
  - 部署期：真实 IdP / rerank 网关联调、G-28③ 生产 PG 接线、G-30（真实 agent 部署时）。
- **待决项**（[requirements §9](docs/requirements.md)）：待决-1（真实样例语料与业务问题）、待决-2（企业 SSO 协议与 token 属性）、待决-3（agent 侧 token 换取 / 可信子系统）未决；待决-4/5/6 已关闭。

## 仓库结构

```
src/knowledge_lattice/
├── app.py            # FastAPI 入口（create_app 工厂：路由 + MCP 挂载 + 静态页壳 + 指纹探针）
├── config.py / log.py
├── query_audit.py    # 查询级审计异步队列（m3-2）
├── core/docs/        # 文档域业务（ingest / chunking / retrieve / acl / quality / credentials…）
├── core/semantic/    # 业务语义域（D23 并入）——与 core/docs 包级互斥
├── domain/           # 身份 / 账号 / 审计事件域模型（auth / accounts / audit_events / models）
├── store/            # StorageBackend 协议 + sqlite/ postgres/ 双方言包（迁移 / FTS / 向量 / ACL 渲染 / 审计）
├── adapters/         # 外置依赖适配（embedder / reranker / auth_sso / parser_docling / tokenizer / breaker…）
├── api/              # REST 端点（upload / documents / tasks / search / quality / admin / auth / users）
├── mcp/              # MCP server（docs + semantic 两组工具）
├── web/              # 前端薄壳（原生 HTML/JS/CSS + i18n.js 中英双语——FR-8，无构建链）
└── worker/           # 任务子进程（ingest / reindex / reembed / semantic_sync·build·retag + maintenance；delete 预留）
scripts/              # 门禁与评测脚本（test_gate.sh / eval_*.py / reset_admin.py）
tests/                # 按模块前缀命名（acl_/ing_/fts_/emb_/e2e_/pg_…），双后端参数化（[pg] 条目）
```

分层纪律（core 不写方言 SQL、core 两包互斥）与模块边界的权威定义见 design §3，速览见 [AGENTS.md](AGENTS.md)。

## 快速开始

前置：Python 3.11+（`.python-version` 钉 3.12.10，uv 按需自动拉取——开发 = 部署同版本，G-11）与 [uv](https://docs.astral.sh/uv/)。

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
# → http://127.0.0.1:8000/：空库首屏为 Setup，建首个 sysadmin（可同事务建首组织）
```

- 页面壳：Setup / 登录 + 检索与上传 + 组织·成员·授权 + 用户/邀请 + 运维视图（中/英双语切换）
- REST API 文档 `http://127.0.0.1:8000/docs`；MCP 端点 `/mcp`（MCP 只走 D18 委托/可信 token，本地会话不可用——需 agent 供数时切 `sso` 形态）
- 认证模式切换、邀请 / 重置 / break-glass 细节见 [RUNBOOK §1.ab](RUNBOOK.md)
- 开发 JWT：dev/test 下 `POST /api/dev/token` 以现有 Bearer 重签或代签（生产 404）

测试：

```bash
uv run pytest                    # sqlite 默认后端，无需容器（TC-UI 手动走查组带 manual 标记、默认跳过）
# 全量门禁（双后端 + 常规/python -O 双模式，skip=失败——不建 CI，本地承接）：
docker start lattice-pg
export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
scripts/test_gate.sh
```

TC-UI 手动走查步骤见 [TEST-CASES §二 TC-UI 组](docs/TEST-CASES.md)；新壳六视图 + 原型对照的详细清单见 [report-ui3-tc-ui-walkthrough.md](benchmarks/report-ui3-tc-ui-walkthrough.md)（其造数脚本为开发期 `/tmp` 形态、未入库，执行前需自备样例数据）；M4 登录/邀请页见 TC-UI-06·07。

## License

[MIT](LICENSE)
