# knowledge-lattice

企业内部知识库系统：以知识库为本体，RAG 为能力面，给 Agent 供数为主、人工检索为辅。

> 名字释义：lattice（晶格）——知识单元（chunk）按结构有序排列成格；**格子是本体，检索是在格上寻位**。文档上架是晶体生长，索引是晶格结构，可重建、可演化。
>
> **在双层知识供给中的位置**：本系统承载**文档知识层**（政策/指南等非结构化内容的语义检索与维度权限）；术语理解层（黑话/名词/表字段映射）由姊妹项目 [glossary-agent](../glossary-agent/) 承载，两线并行、MCP 并挂集成（[requirements.md D17](docs/requirements.md)）。

- 需求文档：[docs/requirements.md](docs/requirements.md)（先读这份）
- 方案设计：[docs/design.md](docs/design.md)（架构 / 数据模型 DDL / ACL 编译 / MCP 契约 / 里程碑分解）
- 交互原型：[prototype/index.html](prototype/index.html)（浏览器直接打开；mock 数据，信息结构为实现基准）
- 调研基础：[../research/enterprise-rag/](../research/enterprise-rag/)（22 仓源码级调研 + 四厂商第一方实践）

## 一句话定位

私有化部署的轻量知识库服务：单进程 + SQLite，零中间件、无 GPU 可跑；**多组织 → 多知识库 → 文档（维度 ACL）** 三层结构，通过 MCP 工具面给 deepagents 供数（代人检索、按数据维度过滤权限），并提供上传与检索测试页面。

## 项目状态

POC 阶段（lab 仓库先行，验证后拆仓演进）。当前：需求澄清完成，需求文档待评审。
