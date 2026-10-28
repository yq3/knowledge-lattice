# AGENTS.md — knowledge-lattice 工作规范

> 企业知识层服务（通用平台，领域无关——首个落地场景为税务）：**文档知识**（制度/口径/手册的权限内检索）+ **业务语义**（术语识别、业务对象类型化对象图，M2-S 起），以单一服务 + 单一 MCP server 供数给 Agent（供数为主、人工检索页面为辅）。私有化部署：单进程、零中间件，存储后端双实现（SQLite 默认 / PostgreSQL+pgvector——D24），嵌入/重排经 OpenAI 兼容 API 外置（D12 修订），无 GPU 可跑。
>
> 本文档是 agent 进仓第一读：文档地图、冻结纪律、分层纪律、工具链与提交约定。完整叙事不在此重复——`docs/` 两正文是唯一权威，本文件只留规则与指针。

## 1. 项目状态与边界

- POC 阶段，2026-10-28 自 lab 仓拆仓独立演进（拆仓前的 issue 评审 #31~#42 指向 lab 仓；仓内携带的历史 PR #47~#55 为迁移前合并记录）。
- M0a / M0b / M1 已交付（M1 收尾归档见检查点 m1-5，TC-UI 手动走查待用户执行）；业务语义按 M2 并行轨道推进，M2 之前 agent 侧以「同 schema 的 Git YAML + 本地 AC 自动机」过渡。
- 文档版本随实现高频勘误（多数批次为非决策变更）——引用时以各文档头部版本行为准，不要背版本号。
- 明确不做：GraphRAG / 图数据库（业务语义 = 类型化对象图，关系展开 SQL 可达）；ES 召回引擎、指标栈监控等只登记为演进缝（NFR-5）；不绑云厂（模型端点中立）。

## 2. 文档地图与设计冻结纪律（最重要）

| 文档 | 角色 |
|---|---|
| [docs/requirements.md](docs/requirements.md) | 需求正文（FR / NFR / D 编号源头——先读这份） |
| [docs/design.md](docs/design.md) | 方案设计（架构 / DDL / ACL 编译 / MCP 契约 / §8 里程碑分解——任务拆段的依据） |
| [docs/TEST-CASES.md](docs/TEST-CASES.md) | 验收用例展开层：design §9 冻结 T / T-S 编号的展开 + 模块 TC-* 用例 + 里程碑验收对照表；**活文档** |
| [docs/known-gaps.md](docs/known-gaps.md) | 已预见问题登记（G-n，对策之后仍残留的缺口与开放点）；**活文档** |
| [prototype/index.html](prototype/index.html) | 交互原型（mock 数据）：信息结构与 UI 风格**双基准**（含语义层视图） |
| [RUNBOOK.md](RUNBOOK.md) | 运维手册（重嵌入蓝绿 / 审计分区回溯 / 双方言迁移注意）——运行侧活文档 |
| `benchmarks/` | 实验 / 压测脚本与报告（report-*.md 归档，结论回写 known-gaps 或正文） |
| `eval/` | 评测语料（corpus.jsonl）与黄金集（golden.jsonl） |

**设计冻结纪律**：

- `docs/` 下 requirements / design 两正文**仅在决策变化时修改**——决策变更走 issue + D 编号（先例：#35→D23 语义层并入、#41→D12 修订 + D24 双后端）；实现问题走测试用例与 issue，不动正文。措辞勘误、随实现回写口径的批次须在版本行声明「非决策变更，D 编号与冻结结论不动」。
- 活文档（TEST-CASES / known-gaps / RUNBOOK）不受冻结约束、随实现回写；TEST-CASES 与正文冲突时以正文为准并开 issue。
- 原型微调属非决策变更、不动 D 编号决策。
- 编号体系沿用既有口径，不新造体系：D-n 决策 / FR·NFR 需求 / T·T-S 冻结测试（design §9）/ TC-\* 模块用例 / G-n 已预见缺口 / 待决-n 待选型 / A-n 用例附录待澄清口径。

## 3. 代码结构与分层纪律

```
src/knowledge_lattice/
├── app.py            # FastAPI 装配（api 各 router + MCP mount + 静态页壳）
├── config.py / log.py
├── core/docs/        # 文档域业务（ingest / chunking / retrieve / acl / quality / credentials…）
├── core/semantic/    # 业务语义域（D23 并入）——与 core/docs 包级互斥
├── store/            # StorageBackend 协议 + sqlite/ postgres/ 双方言包（migrations / fts / vec / acl_render / audit）
├── adapters/         # 外置依赖适配（embedder / reranker / parser_docling / tokenizer / breaker…）
├── api/              # REST 端点（upload / documents / tasks / search / quality / admin）
├── mcp/              # MCP server（docs + semantic 两组工具）
├── web/              # 前端薄壳（原生 HTML/JS/CSS + i18n.js 中英双语——FR-8，服务端不感知语言）
└── worker/           # 任务子进程（ingest / reindex / reembed / delete + maintenance）
```

- **core 不写方言 SQL**——所有 SQL 下沉 `store/<dialect>`（backend.py 协议按域分节组合）；core 是纯业务编排。
- `auto_entities` 识别钉在 api / mcp 层——core 两包不交叉；分层与边界规则的权威定义在 design §3，重构或加模块前先对照。
- 测试 `tests/` 按模块前缀命名（acl_ / ing_ / fts_ / emb_ / e2e_ / pg_…），双后端参数化（`[pg]` 条目）；fixtures / fake_providers.py 提供协议级测试替身，验收离线确定。

## 4. 工具链与常用命令

- **uv 项目**：`uv sync` / `uv run pytest`；`uv.lock` 必须提交。requires-python >=3.11（docling / FastMCP 硬性下限）；`.python-version` = 3.12.10（开发 = 部署同版本，G-11——部署带 uv 托管 CPython 3.12，目标机系统 Python 3.9.9 不作为依赖）。
- **测试门禁**（本地承接 CI 职责——不建 GitHub Actions，项目将移公司内网继续开发）：
  ```bash
  docker start lattice-pg
  export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
  scripts/test_gate.sh
  ```
  语义（fail-closed）：未设 DSN 直接失败，绝不静默绿；pg 臂收集数 >0（防参数化被删的假绿）；常规 + `python -O` 双模式全量；**skip = 失败**。
- 日常单测 `uv run pytest`（sqlite 默认后端，无需容器）；筛选用 `-m "not manual"`（manual = TC-UI 浏览器人工走查，不进门禁；`pdf_models` = 需 docling 模型权重，首次运行联网下载）。
- 无独立 lint / typecheck 工具链（未配置）——质量门禁 = pytest 门禁 + review。
- 配置走环境变量（`LATTICE_*`，模板见 .env.example）；`.env`、`data/` 不入库，密钥只走 .env / 环境变量。

## 5. Git 与多 Agent 工作流

- **默认开发分支 `develop`**（不是 main）；多 Agent 流程的开发 / 提交固定在 `develop_opencode`，PR base = `develop`（合并后远端保留不删）。
- 多 Agent 开发流程（supervised-coding 编排 + coder / tester / committer + reviewer / vision）的权威设计与决策记录（D1~D44）在 [.opencode/README.md](.opencode/README.md)——用该流程前必读；检查点存档 `.opencode/workflows/<task-id>.md`（任务按 design §8 里程碑拆段命名，如 task-knowledge-lattice-m1-5），**新任务开工必扫历史检查点遗留事项**。
- skills 布局：`.agents/skills/`（playwright-cli、frontend-design——跨工具中立路径）；`.opencode/skills/`（impeccable——带 provider 构建，不可与 `.agents/` 同名并存）。
- **除非用户明确要求，开发完成后不要提交到 GitHub**（不要 commit / push）。
- **Git 推送必须走 SSH**：remote 已配 `git@github.com:yq3/knowledge-lattice.git`；本机 keychain 无 GitHub HTTPS 凭据，HTTPS push 会认证失败，勿改回 HTTPS。推送报错先 `ssh -T git@github.com` 排查（首次可能需 `ssh-add ~/.ssh/id_ed25519`）。

## 6. GitHub CLI（gh）

- 已安装（v2.97.0）但**不在默认 shell PATH**：二进制在 `$HOME/install/gh_2.97.0_macOS_arm64/bin/gh`；非交互 shell 先 `export PATH="$HOME/install/gh_2.97.0_macOS_arm64/bin:$PATH"` 或用全路径。已登录 `yq3`（凭据在 keyring）。
- **网络约束**：`api.github.com` 稳定；`github.com` 网页与 raw.githubusercontent.com **间歇性超时**（波动不是永久墙）。查仓库 / README / 文件内容优先 `gh api`（如 `gh api repos/{owner}/{repo}/contents/{path}?ref=<commit>`）；webfetch / curl 卡住时换 `gh api` 或 `git clone --depth 1 git@github.com:{owner}/{repo}` 到临时目录细读，不死磕。
- issue 惯例：设计评审、决策变更、缺陷登记开 issue（拆仓前 #31~#42 在 lab 仓；独立后开在本仓）。

## 7. PlantUML 渲染（流程图）

仓库内文档（如 `.opencode/README.md`）用 ```puml 代码块嵌图。已验证可用的本地渲染流程（在线服务不可用，别用）：

- **下载 jar**（本机有 java，无需 brew/graphviz；api.github.com 下载会超时，用阿里云 maven 镜像）：
  ```bash
  curl -sL -o plantuml.jar https://maven.aliyun.com/repository/central/net/sourceforge/plantuml/plantuml/1.2026.6/plantuml-1.2026.6.jar
  ```
- **语法验证**（改完 puml 必跑，exit 0 = 通过）：`java -jar plantuml.jar -checkonly file.puml`
- **渲染 SVG**（输出文件名取自 `@startuml <name>`，不是输入文件名）：`java -jar plantuml.jar -tsvg -o out/ file.puml`

踩坑（均实测过）：plantuml.com 匿名请求被拒、kroki.io 同样报错，且在线错误页是 HTTP 200（只判 200 会误判成功）；activity 简单语法不支持 `note bottom`（报 syntax error，用 `:文本;` 活动节点替代）；SVG 里中文以 HTML 实体存储（如 `&#21542;` = 否），验证渲染内容时 grep 实体而非中文字面。
