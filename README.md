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
| [RUNBOOK.md](RUNBOOK.md) | 运维手册（重嵌入蓝绿 / 审计分区回溯 / 双方言迁移注意）；运行侧活文档 |
| [AGENTS.md](AGENTS.md) | 工作规范（冻结纪律 / 分层纪律 / 工具链 / 多 Agent 工作流与提交约定） |
| `benchmarks/` | 实验 / 压测脚本与报告归档（report-\*.md，结论回写 known-gaps 或正文） |
| `eval/` | 评测语料（corpus.jsonl）与黄金集（golden.jsonl） |
| lab 仓 | 调研基础：[enterprise-rag 调研](https://github.com/yq3/lab/tree/main/research/enterprise-rag/)（22 仓源码级调研 + 四厂商第一方实践）、[glossary-agent](https://github.com/yq3/lab/tree/main/glossary-agent)（术语层调研沉淀） |

**版本口径**：需求 / 设计两正文随实现勘误高频升版，**具体版本号与变更史以各文档头部为准**，本 README 不复述；里程碑完成态以 [TEST-CASES §六对照表](docs/TEST-CASES.md) 为准。**设计冻结纪律**：`docs/` 需求与设计正文仅在决策变化时修改（决策变更走 issue + D 编号），实现问题走测试用例与 issue；TEST-CASES / known-gaps / RUNBOOK 为活文档、随实现回写。拆仓前的设计评审 issue（#31~#42）均在 lab 仓，本文链接为绝对地址。

## 一句话定位

私有化部署的轻量知识层服务：单进程 + 存储后端双实现（SQLite 默认，零中间件 / PostgreSQL+pgvector 可选——D24），嵌入与重排经 OpenAI 兼容 API（D12 修订）、无 GPU 可跑；**文档知识**——**多组织 → 多知识库 → 文档（维度 ACL）** 三层结构；**业务语义**（D23，M2-S 起）——概念/系统名词/场景/模板/模板字段/报表项/表/列组成的类型化对象图（源端事实每日从业务系统同步——REST 或 MCP 传输均可，人工内容 Git YAML 覆盖层，不做 GraphRAG、不引入图数据库）。两者通过同一个 MCP server（docs 组 + semantic 组工具）给 deepagents 供数（代人检索、按数据维度过滤权限、术语识别与对象关系展开），并提供上传与检索测试页面。

## 项目状态

POC 阶段，独立仓库演进——2026-10-28 自 lab 仓拆仓。

- **M0a / M0b / M1 已交付**（完成态与证据指针见 [TEST-CASES §六对照表](docs/TEST-CASES.md)；M1 里程碑达成宣告待 TC-UI 手动走查执行）。
- **下一步 M2**：业务语义层并行轨道（M2-S1~S3）；M2 之前 agent 侧以「同 schema 的 Git YAML + 本地 AC 自动机」过渡。
- **仍开放的待决项**（[requirements §9](docs/requirements.md)）：待决-1（真实样例语料与业务问题）、待决-2（企业 SSO 协议与 token 属性）、待决-3（agent 侧 token 换取 / 可信子系统）；待决-5（网关 rerank 能力）与待决-6（公司 PG 16 + pgvector 0.8.x）已关闭。

## 仓库结构

```
src/knowledge_lattice/
├── app.py            # FastAPI 入口（create_app 工厂：路由 + MCP 挂载 + 静态页壳 + 指纹探针）
├── config.py / log.py
├── core/docs/        # 文档域业务（ingest / chunking / retrieve / acl / quality / credentials…）
├── core/semantic/    # 业务语义域（D23 并入，M2-S 起）——与 core/docs 包级互斥
├── store/            # StorageBackend 协议 + sqlite/ postgres/ 双方言包（迁移 / FTS / 向量 / ACL 渲染 / 审计）
├── adapters/         # 外置依赖适配（embedder / reranker / parser_docling / tokenizer / breaker…）
├── api/              # REST 端点（upload / documents / tasks / search / quality / admin）
├── mcp/              # MCP server（docs + semantic 两组工具）
├── web/              # 前端薄壳（原生 HTML/JS/CSS + i18n.js 中英双语——FR-8，无构建链）
└── worker/           # 任务子进程（任务循环 + IPC 唤醒；M2 子进程化，当前占位）
tests/                # 按模块前缀命名（acl_/ing_/fts_/emb_/e2e_/pg_…），双后端参数化（[pg] 条目）
```

分层纪律（core 不写方言 SQL、core 两包互斥）与模块边界的权威定义见 design §3，速览见 [AGENTS.md](AGENTS.md)。

## 快速开始

前置：Python 3.11+（本仓以 `.python-version` 钉版本，开发 = 部署同版本——G-11）与 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync                                                       # 安装依赖（uv.lock 锁定、必须提交）
cp .env.example .env                                          # 按需启用嵌入网关 / PG DSN（sqlite 默认无需设置）
uv run uvicorn "knowledge_lattice.app:create_app" --factory  # 起在 http://127.0.0.1:8000
```

- 页面壳 `http://127.0.0.1:8000/`：上传与检索测试页（中/英双语切换）
- REST API 文档 `http://127.0.0.1:8000/docs`；MCP 端点 `/mcp`
- 开发 JWT：dev 环境下 `POST /api/dev/token` 签发（生产 404）

测试：

```bash
uv run pytest                    # sqlite 默认后端，无需容器（TC-UI 手动走查组带 manual 标记、默认跳过）
# 全量门禁（双后端 + 常规/python -O 双模式，skip=失败——不建 CI，本地承接）：
docker start lattice-pg
export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
scripts/test_gate.sh
```

TC-UI 手动走查步骤见 [tests/test_ui_01_manual.py](tests/test_ui_01_manual.py) 文件头。

## License

[MIT](LICENSE)
