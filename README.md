# knowledge-lattice

企业知识层（通用平台，领域无关——首个落地场景为税务）：提供两类能力——**文档知识**（制度、口径、手册的权限内检索）和**业务语义**（术语识别、业务对象及其关联）。以单一服务、单一 MCP server 的形式提供给 Agent，供数为主、人工检索为辅。

> 名字释义：lattice（晶格）——知识单元（chunk）按结构有序排列成格；**格子是本体，检索是在格上寻位**。文档上架是晶体生长，索引是晶格结构，可重建、可演化。并入业务语义层后，"lattice"同时描述**文档知识 + 业务对象关系图**这种有结构的知识网络，名字比以前更贴切（#35 §4.1）。
>
> **知识层定位（2026-10-18 D23 修订，取代 2026-10-16「双层分立」口径）**：文档知识层与业务语义层（术语 + 业务对象的类型化对象图）**同服务归一**——术语层原定的独立 glossary-agent MCP server 部署形态取消，并入本系统 `core/semantic/` 模块（[requirements.md D17/D23](docs/requirements.md)）；[glossary-agent](../glossary-agent/) 转为调研与设计沉淀，其结论是 semantic 模块的设计输入。

- 需求文档：[docs/requirements.md](docs/requirements.md)（先读这份）
- 方案设计：[docs/design.md](docs/design.md)（架构 / 数据模型 DDL（含 `sem_*`）/ ACL 编译 / MCP 契约（docs + semantic 两组）/ 里程碑分解）
- 验收用例：[docs/TEST-CASES.md](docs/TEST-CASES.md)（v1.3，2026-10-21——design §9 冻结编号 T1~T23 / T-S1~T-S12 的展开层（编号沿用）+ 模块 TC-* 用例（含 TC-EMB 嵌入服务与模型治理组）+ 标准矩阵 fixture + 里程碑验收对照表；170 条覆盖 M0a~M3 与 M2-S1~S3；v1.1 吸收评审 [issue #38](https://github.com/yq3/lab/issues/38)、v1.2/v1.2.1 吸收复审 [issue #40](https://github.com/yq3/lab/issues/40)、v1.3 随正文 v0.7/ [#41](https://github.com/yq3/lab/issues/41) 增补；测试按存储后端参数化（D24）；活文档、随实现回写口径，附录 A（A-1~A-17，A-7~A-9 已随正文 v0.6.1 闭环）登记待澄清口径）
- 已预见问题登记：[docs/known-gaps.md](docs/known-gaps.md)（活文档——已接受缺口与规格开放点：语义层不可达窗口 G-1 / fuzzy 层闭环 G-2 / restricted 静默缺失 G-3 / L0 陈旧性 G-4 / 容器化易失 G-5 / PG 后端差异 G-6 / rerank 端点 G-7 / 嵌入模型治理 G-8；与需求 §9、设计 §10「有对策的风险」分工，不受设计冻结纪律约束）
- 交互原型：[prototype/index.html](prototype/index.html)（v0.5，issue [#36](https://github.com/yq3/lab/issues/36)；浏览器直接打开、mock 数据；**信息结构与 UI 风格均为前端实现基准**，含语义层视图——实体浏览按 10⁴~10⁵ 节点规模设计：类型总览落地 + 搜索优先 + 全宽结果表 top-N + 详情独立成页，无常驻实体列表；关系图 / 关系列表按（关系类型 × 方向）分组、每组最多 3 个端点，超出以 +N 计数占位——宽扇出不成毛球）
- 调研基础：[../research/enterprise-rag/](../research/enterprise-rag/)（22 仓源码级调研 + 四厂商第一方实践）；术语层调研沉淀见 [../glossary-agent/](../glossary-agent/)

## 一句话定位

私有化部署的轻量知识层服务：单进程 + 存储后端双实现（SQLite 默认，零中间件 / PostgreSQL+pgvector 可选——D24），嵌入与重排经 OpenAI 兼容 API（D12 修订）、无 GPU 可跑；**文档知识**——**多组织 → 多知识库 → 文档（维度 ACL）** 三层结构；**业务语义**（D23，M2-S 起）——概念/系统名词/场景/模板/模板字段/报表项/表/列组成的类型化对象图（源端事实每日从业务系统同步——REST 或 MCP 传输均可，人工内容 Git YAML 覆盖层，不做 GraphRAG、不引入图数据库）。两者通过同一个 MCP server（docs 组 + semantic 组工具）给 deepagents 供数（代人检索、按数据维度过滤权限、术语识别与对象关系展开），并提供上传与检索测试页面。

## 项目状态

POC 阶段（lab 仓库先行，验证后拆仓演进）。当前：需求 v0.7 / 设计 v0.7（两文档版本号自 v0.6 起统一）——v0.4 **冻结版**（历轮评审 [#31](https://github.com/yq3/lab/issues/31) → [#32](https://github.com/yq3/lab/issues/32) → [#33](https://github.com/yq3/lab/issues/33)（收口）→ [#34](https://github.com/yq3/lab/issues/34)（冻结复审）全部吸收，决策 D1~D22）+ **v0.4 冻结后决策变更 ×2**：D23 业务语义层并入（[#35](https://github.com/yq3/lab/issues/35)，2026-10-18——取代 D17 部署形态；新增 FR-S1~S6 / NFR-11 / M2-S1~S3 / T-S1~T-S12；不影响冻结的必修 1~3 任何结论）与 **D12 修订 + D24 存储后端双实现**（[#41](https://github.com/yq3/lab/issues/41)，2026-10-21——嵌入/重排外置 OpenAI 兼容 API（现网 qwen3-embedding-4b@2560）+ provider 接口、`embed_model` 查询谓词与指纹探针、StorageBackend（SQLite 默认 / PostgreSQL+pgvector）与 AclPlan 方言无关计划、源系统 MCP 可选传输、ES 召回引擎登记演进缝）+ v0.5.1 原型基线更新（[#36](https://github.com/yq3/lab/issues/36)，2026-10-19——非决策变更）+ 术语修订（2026-10-19，非决策变更）+ [#37](https://github.com/yq3/lab/issues/37) 吸收（2026-10-20，非决策变更）+ [#39](https://github.com/yq3/lab/issues/39) 吸收（2026-10-20，非决策变更；验收用例 [TEST-CASES.md](docs/TEST-CASES.md) v1.1~v1.2.1 经 [#38](https://github.com/yq3/lab/issues/38)→[#40](https://github.com/yq3/lab/issues/40) 评审、v1.3 随 #41 增补）。**设计冻结纪律不变：此后仅在决策变化时修改文档，实现问题走测试用例与 issue**；下一步 M0a（骨架周）开工（**M0a/M0b/M1 不含语义层**），待决-2（SSO 协议）与待决-3（委托 token / 可信子系统）随 M0a 并行敲定，待决-5（网关 rerank 能力）M1 前确认、待决-6（公司 PG 扩展）M0b 前确认；业务语义按 M2 并行轨道推进，M2 之前 agent 侧以「同 schema 的 Git YAML + 本地 AC 自动机」过渡。
