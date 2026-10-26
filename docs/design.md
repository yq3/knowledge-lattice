# knowledge-lattice 方案设计

> 版本：v0.9.4（2026-10-25 随 M1-3 交付勘误——**非决策变更**，D1~D24 与冻结结论不动：①§6.1 line 1080 与 requirements FR-1「短时单次有效」措辞勘误——精确为「**成功消费后单次**；失败 PUT 不计消费、可修正重传直至消费/过期」（TEST-CASES v1.4/#42 P1-12 后置拍板口径，M1-3 R1 实现即按此，Tester/Committer 双 ACCEPT）；②§6.2 uploads 行登记「uploads 表 DDL 以迁移 0003 为准、实现细节不入 §4」+ PUT 行「截断/拒绝」二义按附录 A-13 定拒绝（含不足声明 400 对称面）；③§6.2 补非 org 路径段 REST 端点组织上下文口径（resolve_org：claim 优先/X-Org-Id 兜底/不一致 400——D18 字面澄清）；④NFR-6 shared-storage 只读/扩展名限制未实现登记 known-gaps G-12；**补正（同批，doc-only P2-1/P2-2）**：requirements FR-1 L82 同句「截断/拒绝」一并定拒绝 + §6.2 标题与 /api/search 行按实现统一 resolve_org（原「X-Org-Id 仅 MCP/检索用」「本端点为例外」表述作废——api/search.py 自 M1-1 即 claim 优先/头兜底）。v0.9.3（2026-10-25 随 M1-2 交付勘误——**非决策变更**，D1~D24 与冻结结论不动：§5.3 覆盖上传切换事务 SQL 补 `active_error = NULL`（**设计缺项补全·Committer 裁定**——§4 line 324 既有列定义与 D22② 版本闭环语义已覆盖，切换路径漏列会使 searchable_full 与 active_error 非空并存；M1-2 R2 实现先于文档修正，Tester 注入实证 + 双 ACCEPT；另 B-1① 覆盖上传旧维度值校验经用户拍板按 FR-4 严格口径实现——TEST-CASES v1.6.3 同批登记）。v0.9.2（2026-10-25 随 M1-1 R1 勘误——**非决策变更**，D1~D24 与冻结结论不动：§5.2 rerank `none` 档措辞修正——原「不可达或 none」字面把 none 列入降级，与 §6.1 `notice.degraded` 三枚举（embed_unreachable/rerank_skipped/probe_reject，无 none）及 M1-1 实现、TC-EMB-05 断言（`degraded==[]`）冲突；实现侧口径（none=运维配置态、不标降级不发降级审计）经 Tester/Committer 独立复核双 ACCEPT、用户 2026-10-25 确认勘误——none 可观测信号=配置档位+`notice.degraded` 为空（检索耗时日志 routes 字段是召回路数、不含 rerank 阶段，不可作依据）；TEST-CASES v1.6.1 同批 TC-EMB-05 补句 + TC-ACL-08 登记 `search.acl_intercept` 事件名。v0.9.1（2026-10-25 随 M0b 实验结论回写——**M0b-2 三项拍板落库（用户 2026-10-24 确认"按建议执行"，实验报告 benchmarks/report-m0b-2.md 为依据；§8 M0b 预留决策点兑现）**：①**删 dims_json、选定 visible_docs（按文档）+ PG 渲染器 `AS MATERIALIZED` 唯一路径**（json_each 模板删除——§4 DDL/§5.1/§5.2 同步；CTE 快照口径：不读 `v.status/dim.status`，停用/退役经下次编译生效；过滤下推进 CTE+外层双保险）；②**向量分表** `chunk_vectors(rid, embed_model, embedding)` PK(rid, embed_model)+FK CASCADE——删 chunks.embedding、embed_model 收窄为摄取状态标签、向量谓词迁 `cv.embed_model` JOIN（§4/§5.2/§5.3 同步）；③**重嵌入选方案二（分表蓝绿，功能零降级）**（§5.3 同步——runbook 见仓库 RUNBOOK.md）。另登记：PG 连接工厂增 `SET standard_conforming_strings = on` 防御纵深与 `schema_migrations` 锁外建表竞态双捕获形态（UniqueViolation 23505 主/42P07 间或——§3/§4）；dims 输出契约来源改 `document_dimensions` 聚合（store 层 `_attach_dims` 第二条 IN 查询——§6.1）；§7 补实验客户端依赖归属口径；§8 M0b 完成态与 §10 风险表同步；**勘误登记两笔（M0a 移交）**：0001 的 `trg_docdims_consistency` 建表顺序后移（CREATE TRIGGER 要求目标表先在——排版顺序不可直接执行）与 FTS 触发器 INSERT 目标列用 `rowid`（FTS5 虚表列名约束，值仍 new/old.rid——content_rowid='rid' 映射不变），语义等价、0001 内已注释注明。实现证据：M0b-1/2/3 三 PR（#47/#48 及 v1.1 迁移 PR），测试 271+1 双后端双模式全绿。v0.9（2026-10-22 吸收需求 v0.9 **FR-8 界面国际化（对话决策——轻量决策变更，不开 D 号、D1~D24 与冻结结论不动）**：①§5.7 新增 i18n 口径——`web/i18n.js` 静态字典（zh/en + `t(key, params)` + `data-i18n`）+ 头部语言切换（localStorage 持久化、默认中文）+ `<html lang>`/`<title>` 同步；**只译 UI 文案、业务数据不译**（检索与权限行为不随语言变化）；**服务端不感知语言**（API/审计/日志/错误码单一口径）；②§3 web/ 补 i18n.js；③§8 M0a.4 静态页壳含 i18n 机制；④§1 映射表补行；用例 TC-UI-01~04 见 TEST-CASES v1.5；⑤复审补登记：指标栈监控演进缝入 §2 升级缝与需求 NFR-5（v0.8.5 提出、当时漏登记表——两处互指）。v0.8.5（2026-10-22 §3 补运行日志落点——**非决策变更**（可观测性第三类补全，D1~D24 与冻结结论不动：此前审计事件【store Audit 域/月库】与任务状态【tasks 表】有家，**运行日志无任何位置**——TEST-CASES T-S10 已引用「对账任务日志」而设计无模块产生日志）：①新增顶层 `log.py`——结构化 JSON→stdout（不落文件，容器/systemd 收集、本地可切人读格式——D2 零中间件）、request_id/task_id contextvars（贯穿主进程与 worker）、请求中间件一行日志、uvicorn access log 关闭防双打、docling/torch 降噪；worker 启动挂同套 handler、task_id 进上下文；②补横切面口径——各层直接标准库 logging+上下文、不构成分层纪律例外；**审计≠日志**（业务事实落库不可丢 vs 运行诊断 stdout 可丢）；③检索每请求一行耗时分解（嵌入/召回/融合/rerank）＝NFR-8 标定与 M0b 压测数据源，指标栈不引入、登记演进缝；config.py 补日志级别/格式。v0.8.4（2026-10-22 §3 core/ 对称分包——**非决策变更**（模块重组，职责与边界语义零变化，D1~D24 与冻结结论不动）：①文档域六模块（ingest/chunking/excel_chunking/retrieve/acl/quality）收进 `core/docs/`、与 `core/semantic/` 包级对等——消除「core/ 散文件默认属 docs 侧」的隐式归属（新模块必须选边），并与需求 D23 行既有 `core/docs/` 表述、MCP 工具组命名（docs / semantic）对齐；②边界规则 1 由点名文件清单升为**包级互斥** + import-linter 契约进 CI 机械执法（§9 单元补注、§10 风险表同步——「语义层职责膨胀」此前仅评审纪律防线）；③acl.py 归属 core/docs/ 不变（#37 实体维度 ACL 演进缝触发时再议是否升共享）；④连带 §5.1/§5.2/§5.3/§5.4/§5.10 标题与规则 2 路径引用更新。v0.8.3（2026-10-22 §3 代码模块划分结构澄清——**非决策变更**（结构补全与措辞自洽，不改任何分层方向与边界结论，D1~D24 与冻结结论不动）：①backend.py 协议**按域分节组合**（Search/Ingest/Acl/Admin/Semantic/Audit 各自独立 Protocol、本文件只做组合——防单一 God interface，清单为方法种子非穷举）+ 补 `read_membership`/`read_grants`（§5.1 第 0/2 步授权展开与成员校验的读取收口 store，「core 不碰 SQL」纪律由此闭合）；②迁移目录升**二维** `store/<dialect>/migrations/{docs,semantic}/`（D24 双方言后同一迁移号双方言各一份；§8 M2-S1.1 同步）；③worker 任务类型补 **maintenance**（过期成员物理清理/tombstone 90 天清理/未消费凭证回收/审计月库滚动/备份快照/sem_chunk_entities 对账兜底）+ app.py 内嵌调度器（周期投递；指纹探针周期档随主进程——结果直接开合查询侧向量路）——此前散落 §2/§5.1/§5.3/§6.1 各处无归属；④措辞与自洽：分层纪律「core 纯业务编排」改「业务逻辑层（编排/编译/分析/切分）」、上传校验归 core 摄取入口、api/ 补 documents.py（文档域端点）与 admin.py 审计查询/dev-token 落点、adapters/ 与 core/semantic/adapters/ 双义注记（grant_sync 属权限域置顶层）、方言包文件清单对称化（fts/vec/acl_render/audit/backup 双侧齐）、边界规则 1「反向禁止」加第 2 条例外限定、规则 2 钉死 `auto_entities` 识别在 api/mcp 层（交叉点保持两个）；⑤复审联动补写：§2 部署图（worker 框 + 主进程任务调度行）与 §4 `tasks.type` 枚举同步 maintenance。需求侧无正文变更（联动升版）。v0.8.2（2026-10-22 运行时口径登记——**非决策变更**，用户确认目标机系统 Python 3.9.9 / 开发机 3.12.10：§7 依赖表「Python 3.11+ / uv」行补目标机约束注记——docling / FastMCP 均硬性要求 ≥3.10（3.9 无降级出路、已 EOL），部署带 uv 托管独立 CPython 3.12、系统解释器不作为依赖（requirements NFR-1 v0.8.2 / known-gaps G-11）；D1~D24 与冻结结论不动。v0.8.1（2026-10-22 待决-6 关闭同步——**非决策变更**，用户确认公司 PostgreSQL 环境为 **PG 16 + pgvector 0.8.x**：①§7 依赖表 psycopg 行「扩展白名单前置确认（待决-6）」改已确认；②§8 M0b 实验5「公司 PG 环境待决-6」改已确认（requirements 待决-6 关闭、known-gaps G-6 收窄①闭环）；D1~D24 与冻结结论不动。v0.8（2026-10-22 吸收 [issue #42](https://github.com/yq3/lab/issues/42) **必修 2/3/4 与 P1/P2 全量回写——非决策变更**，D1~D24 结论不动：①**必修2**：重嵌入驱动定为 `reembed` 任务类型（扫描谓词含标签不等）、embed 批次回写防护补 `AND embedding IS NULL AND embed_model=:batch_label`（防孤儿向量）、窗口内 `active_status` 回退 `searchable_lexical` + 进度；**§5.3 探针细节**（≥3 哨兵取最小余弦 / 基线存 `embedding_fingerprints` / 首部署建档 / 管理面重置+审计 / 启动+周期探测——P1-1）；②**P1-2/3**：`dict_rev` 并入嵌入标签（换模型强制重跑 `semantic_build`）、quality 缓存键 = (content_sha, embed_model) 且重跑前清旧 `vector_crowding`；③**P1-4**：`notice` 统一为对象（vector_pending + degraded∈{embed_unreachable, rerank_skipped, probe_reject}）+ `search.degraded` 审计事件 + NFR-8 补超时/熔断数值；④**P1-7/8**：§4 标「SQLite 渲染」+ 设计说明末条补 **PG 映射**（触发器/月分区/备份/事务/迁移/FTS——含 regconfig 双参 immutable）；backend 评分方向差异吸收为**名次**（协议返回 rank）+ PG tsquery 转义口径；⑤**P1-11**：§6.3 权限口径②补「当前口径、演进缝触发以 NFR-5 为准」互指；⑥§8/§9/§10 标题版本号 v0.5→v0.7（P2）。v0.7.2（2026-10-22 吸收 [issue #42](https://github.com/yq3/lab/issues/42) **三项拍板落档——非决策变更**，D1~D24 结论不动：①**PG 升正式备选**——§2 升级缝与 §8 M0a/M0b/M1 修正（CI 必跑 docker postgres+pgvector、skip 视为失败；100 万 chunk/P95 仅为部署切换时机）；②**指纹探针拒绝档同步关查询侧向量路**（§5.3 两档阈值——余弦 < 0.99 仅告警、< 0.95 拒写并降级 BM25 单路；跨底模距离无意义）；③**语义层方言 SQL 下沉 StorageBackend**——§3 backend.py 协议补 `expand_relations`、§5.1/§5.9/§5.10 的 SQL 改述为「backend 渲染示例（SQLite 版，PG 方言随 M2-S）」，core 不写方言 SQL。v0.7.1（2026-10-22 吸收 [issue #42](https://github.com/yq3/lab/issues/42) **必修 1 回写——非决策变更**：①rerank 端点确认同步三处（§3 reranker.py 注释 / §5.2 rerank 段 / §7 依赖表——网关提供 Cohere 风格 `/rerank`，需求待决-5 关闭、known-gaps G-7 闭环）；②§5.2 补外发注记（chunk 原文/query 发往内网网关——同信任域口径详见需求 NFR-6 v0.7.1）；D1~D24 与冻结结论不动。v0.7（2026-10-21 吸收 [issue #41](https://github.com/yq3/lab/issues/41)：**决策变更**——v0.4 冻结后第二个（沿 #35/D23 先例）——①**D12 修订**：嵌入/重排外置为 OpenAI 兼容 API + provider 接口（§2 部署形态与资源预算重写、§3 adapters、§5.2/5.3/5.4、§7 依赖表；`embed_model` 升级为查询谓词 + 指纹探针 + 重嵌入流程）；②**新增 D24**：存储后端抽象双实现（SQLite 默认 / PostgreSQL+pgvector）——§3 store/ 重构为 StorageBackend 协议 + 方言包、§5.1 编译产物改为方言无关 AclPlan、§7/§8/§10 同步；③§5.8 补源系统 MCP 可选传输口径（FR-S1 本就传输方式无关，非决策变更）；④NFR-5 登记 ES 召回引擎演进缝；D1~D11、D13~D23 其余结论与 v0.4 冻结的必修 1~3 不动，冻结纪律延续。v0.6.1（2026-10-20 吸收 [issue #39](https://github.com/yq3/lab/issues/39)：**非决策变更**——#38 用例评审衍生的三处正文修正：①§4 设计说明⑥「全部 `sem_*` 表带 org_id」修正为「org 作用域六表带 org_id，`sem_rel_types` 为全局白名单配置表除外」（与 §4 DDL 一致）；②§5.5 请求体权限字段口径对齐需求 FR-4——**透传原始 token 拒绝；请求体权限字段一律忽略并记审计**；③§8 M1 验收句限定 T19 删库半句、T20 退役审计半句随 M2 收口；D1~D23 与 v0.4 冻结结论不动。v0.6（2026-10-20 吸收 [issue #37](https://github.com/yq3/lab/issues/37)：**非决策变更**——①§5.8 新增「源系统接入前置条件」小节（接口形态 / 维度属性可选携带 / 连接配置 per-org，两处按 #37 评论决策修正 issue 原文：不强制携带、缺维度值按空值放行）；②§2 升级缝与需求 NFR-5 同步登记「语义层实体维度 ACL」演进缝；③§1 映射表与 §10 风险表同步补行；D1~D23 与 v0.4 冻结结论不动；同日起需求与设计文档**版本号统一**（起点 v0.6）。v0.5.2（2026-10-19 术语修订：语义层内容层「骨架」统一改称「源端事实」，列级相应称「事实列」——旧词易被误读为抽象类别（实际是源系统已有对象与关系的具体同步记录），且与 M0a「骨架周」（工程脚手架）撞词；**非决策变更**，只改措辞不改任何结论。v0.5.1（2026-10-19 原型基线更新：吸收 [issue #36](https://github.com/yq3/lab/issues/36)——`prototype/index.html` 替换为 v0.5，五视图（文档 / 检索测试 / 权限 / 语义层 / 任务与审计），§5.7 前端薄壳以其为**信息结构与 UI 风格双基准**；语义层视图原型已含（实现仍可选，M2-S3 节奏不变）；**非决策变更**——D1~D23 与 v0.4 冻结结论均不受影响，冻结纪律延续）
> 日期：2026-10-16 初稿 → v0.2（#31）→ v0.3（#32）→ v0.4（#33+#34，冻结版）→ v0.5（#35，D23）→ v0.5.1（#36，原型基线更新）→ v0.5.2（术语修订：骨架→源端事实）→ v0.6（#37，非决策变更：源系统接入前置条件 + 实体维度 ACL 演进缝登记；版本号与需求文档统一）→ v0.6.1（#39，非决策变更：#38 评审衍生三处正文修正——sem_rel_types 全局表表述 / 请求体权限字段口径对齐 FR-4 / M1 验收 T19·T20 半句限定）→ v0.7（#41，决策变更：D12 嵌入/重排 API 化 + D24 存储后端双实现 + 源系统 MCP 口径 + ES 演进缝登记）→ v0.7.1（#42 必修1 回写，非决策变更：rerank 端点确认同步 + §5.2 外发注记）→ v0.7.2（#42 三项拍板落档，非决策变更：PG 正式备选（CI 必跑）+ 探针拒绝档关查询向量路 + 语义层 SQL 下沉 backend）→ v0.8（#42 必修2/3/4 与 P1/P2 全量回写，非决策变更：reembed 任务/回写防护/探针细节/notice 对象/PG 映射/名次统一等）→ v0.8.1（待决-6 关闭同步，非决策变更：公司 PG 16 + pgvector 0.8.x 确认——§7/§8 两处引用改已确认）→ v0.8.2（运行时口径登记，非决策变更：目标机系统 Python 3.9.9 与 3.11+ 口径冲突——uv 托管 CPython 3.12 对冲，§7 行补注记、known-gaps G-11）→ v0.8.3（§3 代码模块划分结构澄清，非决策变更：backend 协议按域组合 / 迁移目录二维 / maintenance 任务与调度器归属 / 分层纪律与边界规则措辞自洽）→ v0.8.4（core/ 对称分包 core/docs/ + core/semantic/，边界规则升包级互斥 + import-linter CI 执法——非决策变更）→ v0.8.5（§3 补运行日志落点 log.py + 审计/日志分工口径 + NFR-8 耗时分解数据源——非决策变更）→ v0.9（FR-8 界面国际化：§5.7 i18n 口径 + §3 web/i18n.js + M0a 落机制——轻量决策变更（对话决策）） → v0.9.1（M0b 结论回写联动）→ v0.9.2（M1-1 rerank none 措辞勘误）→ v0.9.3（M1-2 §5.3 SQL 补 active_error）→ v0.9.4（M1-3 L1080/DDL 登记/X-Org-Id 统一/G-12）
> 前置阅读：[requirements.md](./requirements.md)（本文所有 FR/NFR/D 编号均指向需求文档 v0.9.4）
> 调研依据：[enterprise-rag 调研](../../research/enterprise-rag/)，参考架构基线 `blog/10-build-kb-for-agent.md`

---

## 1. 设计总览：需求 → 方案的映射

| 需求 | 方案落点 | 本文章节 |
|---|---|---|
| FR-1 摄取 | 单进程 + worker 子进程 + 任务表；docling 进程内解析 | §2 / §5.3 |
| FR-2 检索 | 存储后端内双路（SQLite：FTS5 + sqlite-vec / PG：tsvector + `<=>`——D24）→ RRF → rerank API | §5.2 |
| FR-3 区分度反馈环 | 摄取管线尾部 quality 阶段 + 质量报告接口 | §5.4 |
| FR-4 维度权限 | 维度模型五表 + ACL 编译器（查询时展开，引擎内下推） | §4 / §5.1 |
| FR-5 接口面 | FastMCP 单一 server：docs 组四工具（search/upload/fetch/list_documents）+ semantic 组四工具（annotate/search_entities/get_entity/describe_table，M2-S——D23）+ REST + 静态薄壳前端 | §6 |
| FR-6/7 治理与评测 | audit_events 触发器；评测脚本集（黄金集 + 门禁） | §4 / §9 |
| NFR-1 部署形态 | SQLite 后端零中间件；PG 为可选外部后端（D24）；嵌入/重排为外部 API 依赖（D12 修订） | §2 |
| NFR-5 演进缝 | StorageBackend 协议 + 配置级切换点清单（存储已升格 D24 双实现；ES 召回引擎为登记缝） | §7 |
| **FR-S1~S6 业务语义（D23）** | `core/semantic/`：同步适配器（源端事实）+ Git YAML 覆盖层（人工内容）+ AC 自动机识别 + 递归 CTE 关系展开 + 实体召回路（**复用 §5.1 ACL 编译产物**）+ describe_table 透传；与 docs 同进程同库、单一 MCP server 分组注册 | §3 / §4（`sem_*`）/ §5.8~5.10 / §6.3 |
| **FR-8 界面国际化（2026-10-22 对话决策）** | `web/i18n.js` 静态字典（中/英）+ 头部语言切换：UI 文案双语、业务数据不译、服务端不感知语言 | §3（web/）/ §5.7 |
| **NFR-11 语义层性能与隔离（D23）** | 独立 worker 任务类型（semantic_sync/build/retag）限速错峰；删除比例保护 + 宽限期；构建产物原子切换；中间件降级 | §2 / §5.8 / §6.3 |
| **issue #31 评审修订（v0.2）** | P0 五项修复（检索侧）+ 权限真值源 + 性能运维 | §4 / §5.1~5.3 / §5.6 / §8~10 |
| **issue #32 评审修订（v0.3）** | 写路径安全 P0×4 + P1×9 | §4 / §5.1~5.3 / §5.6 / §8~10 |
| **issue #33 收口修订（v0.4，冻结）** | 权限状态进计算（P0-1）/ 版本在用制闭环（P0-2）/ 外键动作补齐 / 凭证流闭环 / 审计 outbox / 可信子系统约束 / REST 路径统一 / M0a-M0b 拆分 / T1~T19 | 全文（决策汇总见需求 D22） |
| **issue #35 决策修订（v0.5，D23）** | 业务语义层并入（取代 D17 部署形态）：类型化对象图 + SQLite 递归 CTE，**不做 GraphRAG / 图数据库**；源端事实同步 + YAML 覆盖层分层真相源；M2-S1~S3 并行轨道 | §2~§4 / §5.2~5.3 / §5.8~5.10 / §6 / §8~10（决策汇总见需求 D23） |
| **issue #37 吸收（v0.6，非决策变更）** | 源系统接入前置条件显式化（§5.8 新增小节）+ **语义层实体维度 ACL 登记为演进缝**（§2 升级缝，与需求 NFR-5 同步——延后决策，触发条件与已预评实施要点见 issue #37 及其评论） | §2 / §5.8 / §10 |
| **issue #39 吸收（v0.6.1，非决策变更——#38 用例评审衍生）** | 三处正文修正：§4 设计说明⑥ org 作用域表述（`sem_rel_types` 全局白名单表除外）/ §5.5 请求体权限字段「忽略并记审计」对齐需求 FR-4 / §8 M1 验收限定 T19 删库、T20 退役审计半句随 M2 收口 | §4 / §5.5 / §8 |
| **issue #41 吸收（v0.7，决策变更）** | **D12 修订**（嵌入/重排外置 OpenAI 兼容 API + provider 接口；`embed_model` 查询谓词 + 指纹探针 + 重嵌入流程）+ **D24 新增**（StorageBackend 双实现 SQLite/PG、AclPlan 方言无关计划）+ 源系统 MCP 可选传输 + ES 召回引擎演进缝登记 | §2 / §3 / §4 / §5.1~5.4 / §5.8 / §7 / §8 / §10 |

## 2. 进程与部署架构

```
 ┌─────────────────────┐        ┌──────────────────────────┐
 │ 前端薄壳（静态页）    │        │ deepagents（企业内服务）    │
 │ 上传/检索/管理        │        │ agent 循环住在这里          │
 │ （M2-S3 起含语义入口）│        │ + 术语注入薄中间件（D23）    │
 └─────────┬───────────┘        └────────────┬─────────────┘
           │ REST                             │ MCP（HTTP，委托 token / 可信子系统——D18）
           ▼                                  ▼
 ┌───────────────────────────────────────────────────────────┐
 │ knowledge-lattice 主进程（FastAPI，单进程）                    │
 │  · REST 控制面：upload / tasks / search / admin / semantic    │
 │  · FastMCP server（单一 server，两组工具——D23）：             │
 │     docs 组：search / upload / fetch / list_documents         │
 │     semantic 组（M2-S 起）：annotate / search_entities /      │
 │       get_entity / describe_table                            │
 │  · 检索管线（同步）：双路召回（ACL 引擎内下推）→RRF→ACL 断言      │
 │ │    →rerank→返回前二次断言→溯源返回（P2-4 顺序）              │
 │  · 维度 ACL 编译器：委托 token →（含过期/停用的）授权展开 → SQL WHERE   │
 │  · core/semantic（D23）：AC 自动机识别 / 关系展开（递归 CTE）/    │
 │    构建产物懒加载（按 org+dict_rev 原子切换）/ 同步适配器         │
 │  · 任务调度：写 tasks 表 + 唤醒 worker + 内嵌调度器（maintenance 周期投递/探针周期档——§3，v0.8.3）；审计写入                │
 └────────┬────────────────────────────────────┬──────────────┘
          │ 子进程 IPC（unix socket / stdin）    │ 读写
 ┌────────▼──────────────┐          ┌───────────▼──────────────┐
 │ worker 子进程           │          │ 存储后端（D24）：        │
 │ docs 任务：解析→切分→     │          │ SQLite 默认 / PG+pgvector │
 │   打标*(M2-S3)→index_fts │          │ 元数据+FTS+向量+sem_*    │
 │   →嵌入→index_vec→质量    │          │ SQLite=WAL；PG 无单写限制 │
 │ semantic 任务（D23）：    │          └──────────────────────────┘
 │   semantic_sync（每日/   │
 │   手动）· semantic_build │
 │   · semantic_retag      │
 │ maintenance（v0.8.3）：  │
 │   周期维护·调度器投递     │
 │ 心跳/租约/断点续跑       │
 └────────┬───────┬──────┘
          │       │                ┌──────────────────────────┐
 ┌────────▼──┐ ┌──▼─────────┐      │ data/objects/ 对象目录     │
 │ docling    │ │ 模型 API 客户│      │ 原始文件+解析产物           │
 │ （进程内库）│ │ 端（OpenAI 兼│      │ （canonical 真相，可重建）   │
 │ MinerU 懒载│ │ 容——D12 修订│      └──────────────────────────┘
 │ （可选服务）│ │ LLM/嵌入/rer.│
 └───────────┘ └────────────┘
```

**部署形态（NFR-1/9，v0.7 按 D12/D24 修订）**：`knowledge-lattice` 主进程 ×1（内含 worker 子进程）+ 所选存储后端 ×1（**SQLite `lattice.db` 默认 / PostgreSQL+pgvector 可选——D24，配置级切换**）+ `data/objects/` 目录 ×1。无消息队列、无独立向量库——分别是 tasks 表轮询、**`chunk_vectors` 分表（rid, embed_model, embedding——M0b-2 实验选定，v1.1/0002）+ sqlite-vec 距离函数**（PG 后端为 `vector` 列 + `<=>` 算子，精确扫描起步——G-6）；**嵌入与重排不在本机（D12 修订）**——经 OpenAI 兼容 API 调内部网关（不可达时检索降级 BM25 单路、摄取停在 `searchable_lexical`，服务不中断）。worker 经 IPC 被唤醒 + 兜底轮询（anything-llm 的最小进程隔离样板：OOM 只杀 worker）。**业务语义层并入后形态不变（D23）**：`core/semantic/` 与文档层同进程、同主库（`sem_*` 前缀表，迁移脚本分目录）、同一 MCP server——不新增独立服务、不引入图数据库（10⁴~10⁵ 节点、1~2 跳查询，递归 CTE 毫秒级）；同步适配器只读拉取源系统（模板中心/场景配置/报表中心/元数据系统）快照（**传输 REST 或 MCP 均可——§5.8 前置条件，v0.7 #41**），`describe_table` 实时透传元数据系统。**资源预算（v0.7 重写）**：模型外置后主进程轻量（无 torch——嵌入/重排经 API）；worker 仅 docling + torch，峰值 ~2~2.5 GB；服务侧合计 ~3~3.5 GB——最低规格 8 GB RAM / 4 核（网关与模型内存不在本预算；原「16 GB / 8 核、峰值 6~8 GB」口径作废）；**模型 API 调用全部异步/线程池**，不阻塞事件循环；AC 自动机与模糊索引按 `(org, dict_rev)` 懒加载（数千~数万条，内存开销 MB 级）。

**并发模型（NFR-9）**：SQLite WAL 模式（多读单写）。检索（读）不受摄取（写）阻塞；写竞争治理：`busy_timeout` + worker 短事务分批提交 + **审计按月分库后与业务写天然隔离**（FR-6）。数百用户检索并发的实际瓶颈在 rerank 调用（§5.2 缓解：候选 32 / rerank API 异步化与并发信号量 / 不可达跳过——D12 修订）。**语义任务的写锁治理（D23，NFR-11）**：`semantic_sync` / `semantic_retag` 与 ingest 抢 WAL 写锁——同步与重标为独立任务类型、分批 ≤1000 行/批、限速、默认夜间错峰；重标优先级最低不与 ingest 抢资源；语义任务失败不影响 docs 检索可用性；必要时把 `sem_*` 拆到 ATTACH 的独立库文件（repository 接口不变）。**v0.7（D24）**：本段写竞争治理为 SQLite 后端口径——PG 后端为 MVCC 多写、无 WAL 单写限制，`busy_timeout`/短事务错峰治理天然缓解；审计按月分库在 PG 上落地为按月分区表（连接工厂滚动建分区，接口不变）。

**备份恢复（NFR-10）**：SQLite `VACUUM INTO` / online backup 定时快照 + `data/objects/` 一并备份；RPO ≤ 24h / RTO ≤ 4h（POC 目标）；恢复演练进 runbook。

**升级缝（NFR-5 落点，v0.7 更新）**：存储（repository 接口后换 pgvector/milvus → **已升格为 D24 双实现**：SQLite↔PG 配置级切换，**PG 为正式备选（v0.7.2，#42 拍板1——CI 必跑、全矩阵双后端验证；100 万 chunk 或 P95 超标仅为部署切换时机——NFR-2）**；milvus 保留为缝；**ES 召回引擎为登记缝（#41，不实现）**——价值形态为 BM25+向量**同引擎**混合、届时抽走 recall_fts+recall_vec 两路而非向量-only，配方：AclPlan 第三渲染器 + 影子元数据同步 + 查询时以关系库真相二次断言 + 对账任务，触发条件见需求 NFR-5）、嵌入与重排（原「进程内 → TEI 容器」缝已由 D12 修订启用：provider 接口 + OpenAI 兼容客户端，换端点为配置级）、解析（docling → MinerU api_server，路由表驱动）、授权同步（grant_sync 适配器启用只读同步维度——D16）、**语义层实体维度 ACL（#37 登记为延后决策的演进缝）**：`sem_entity_dims` 绑定表 + §5.1 编译器**第二渲染目标**（同一套授权展开渲染到实体表——统一模板原样套用、无类型分支），读时过滤、AC 自动机与打标不动（纯加法）；触发条件与已预评实施要点见 #37 及其评论；过渡期按区域灰度同步范围、**禁用 `restricted` + `semantic:restricted` 充当区域控制**（二进制开关非分维授权）；触发时先做「第二区域实体是否必须进语义层」前置评估，不进 = 延续灰度零成本；**指标栈监控（v0.9 登记缝——v0.8.5 提出、当时漏登记表：现状以运行日志耗时分解为数据源（§3 横切面），Prometheus 等引入违反 D2 零中间件、届时须决策变更）**。

## 3. 代码模块划分

```
knowledge_lattice/
├── app.py                  # FastAPI 入口：装配路由/MCP/DB/worker + 内嵌调度器（周期投递 maintenance 任务、
│                            #   指纹探针周期档——§5.3，探针在主进程跑：其结果直接开合查询侧向量路，v0.8.3）
├── config.py               # 全部配置（模型版本、阈值、路径、网关地址；日志级别/格式——v0.8.5）
├── log.py                  # 运行日志装配（v0.8.5 补缺——可观测性第三类：审计/任务状态之外，运行日志此前无位置）：
│                            #   结构化 JSON→stdout（不落文件——容器/systemd 收集，本地开发可切人读格式，D2 零
│                            #   中间件口径）；request_id/task_id 走 contextvars（贯穿主进程与 worker）；请求
│                            #   中间件一行日志（method/path/status/耗时/user/org）；uvicorn access log 关闭防
│                            #   双打；docling/torch 等第三方降噪
├── api/
│   ├── upload.py           # POST /api/orgs/{org}/documents（上传入口）+ POST /api/uploads（凭证签发）+ PUT /api/uploads/{id}
│   │                        #   （库/维度/授权内校验在 core 摄取入口函数——api 只做协议转换，v0.8.3）
│   ├── documents.py        # 文档管理（v0.8.3 补缺——§6.2 文档域端点归此）：详情（active/pending 四字段）/
│   │                        #   PATCH dimensions / DELETE / reindex / quality 报告 + PATCH /api/quality-flags/{id}
│   ├── datasets.py         # 知识库 CRUD（组织内，D15）
│   ├── orgs.py             # 组织 CRUD 与成员管理（系统管理员，D7）
│   ├── tasks.py            # GET /api/orgs/{org}/tasks（+ cancel）
│   ├── search.py           # POST /api/search（检索测试页用，支持库过滤）
│   ├── admin.py            # 维度/取值/用户/授权 CRUD + GET /api/orgs/{org}/audit（审计查询）+
│   │                        #   POST /api/dev/token（仅 dev/test 配置注册——v0.8.3 补落点）
│   └── semantic.py         # ★D23 /api/orgs/{org}/semantic/...：annotate / entities / tables / l0 / sync / yaml webhook / builds（§6.2）
├── mcp/
│   └── server.py           # FastMCP 单一 server：docs 组（search/upload/fetch/list_documents）+ semantic 组（annotate/
│                           #   search_entities/get_entity/describe_table，M2-S——D23）分组注册 + 鉴权中间件（60s 超时）
├── core/
│   ├── docs/               # 文档域（v0.8.4 对称分包——散文件显式归域、消除「core/ 散文件默认属 docs 侧」的
│   │                        #   隐式归属，新模块必须选边；与 core/semantic/ 包级对等——需求 D23 行既有
│   │                        #   core/docs/ 表述、MCP 工具组命名（docs/semantic）由此与结构一致）
│   │   ├── ingest.py       #   摄取管线编排：parse→chunk→index_fts(+打标)→embed→index_vec→quality（D21：版本在用制切换；D23：tag/untag 显式调用）
│   │   ├── chunking.py     #   结构感知切分（docling 结构树 + 递归 token）
│   │   ├── excel_chunking.py # Excel 表格型切分（sheet/行块）
│   │   ├── retrieve.py     #   检索管线编排：召回（FTS/向量/实体路*）→融合→重排→过滤→溯源（*M2-S3，调 semantic.expand）
│   │   ├── acl.py          #   维度 ACL 编译器（§5.1）——产出方言无关 AclPlan（D24）；实体召回路复用其产物，语义层不另写
│   │   │                    #   （#37 实体维度 ACL 演进缝触发时再议是否升共享，v0.8.4 注）
│   │   └── quality.py      #   区分度检测 + LLM 关键词增强（§5.4）
│   └── semantic/           # ★D23 业务语义（M2-S1~S3）：与 docs 共基础设施（store/domain），不共享领域模型与 ACL 编译器
│       ├── annotator.py    #   AC 自动机识别 + 消歧（§5.9）；对外显式接口 tag(chunks, org) / untag(doc_id, version)（ingest 打标同源）
│       ├── expand.py       #   关系展开：递归 CTE、深度≤2、防环、高扇出截断（§5.9）；对外接口 expand(ids, rels, depth)
│       ├── build.py        #   semantic_build：AC 自动机 / 模糊索引 / L0 片段 / 构建报告 + 按 (org, dict_rev) 原子切换（§5.8）
│       ├── yaml_merge.py   #   Git YAML 覆盖层合并：curated_json / manual·abbr 别名 / curated 关系（§5.8 合并规则表）
│       ├── sync.py         #   同步流程编排：删除比例保护 → 分批 upsert → missing/retired → 别名重建 → 触发构建（§5.8）
│       └── adapters/       #   源系统同步适配器（SourceAdapter 协议，只读、幂等、输出当前快照）
│           ├── template_center.py   # template / template_field + has_field / backed_by / maps_to
│           ├── scenario_config.py   # scenario + uses
│           ├── report_center.py     # report / report_item + has_item / child_of / derived_from（源端有则同步）
│           └── metadata.py          # table / column 轻量节点 + has_column（只拉被引用到的）；describe_table 透传客户端
├── adapters/               # 第三方依赖与外部服务封装——进程内库（docling/jieba）与 HTTP 客户端同置；
│                            #   与 core/semantic/adapters/（源系统同步 SourceAdapter）语义不同（v0.8.3 注）；
│                            #   grant_sync 同为源系统同步、属权限域（D16 演进缝）故置顶层
│   ├── parser_docling.py   # docling 封装（DoclingDocument→统一块结构）
│   ├── parser_mineru.py    # MinerU 懒加载路由（可选，按配置启用）
│   ├── embedder.py         # Embedder provider 接口 + OpenAI 兼容客户端（D12 修订——进程内实现取消）；
│   │                        #   写入校验 len==config.dim + 启动指纹探针（防网关静默换底模）
│   ├── reranker.py         # Reranker provider 接口（D12 修订；**含 none 实现**——跳过重排用 RRF 序；
│   │                        #   端点已确认 Cohere 风格 /rerank——待决-5 关闭 2026-10-22）
│   ├── llm.py              # 内部网关客户端（OpenAI 兼容）
│   ├── auth_sso.py         # SSO 验签（OIDC/CAS 适配，协议待定；JIT 建档；可信子系统降级——D18）
│   ├── grant_sync.py       # 授权同步适配器（D16 演进缝，默认禁用）
│   └── tokenizer.py        # jieba 预分词（生成 content_seg / title_seg；人工词与 LLM 词分层——P1-3）
├── store/                  # ★D24（v0.7）：StorageBackend 协议 + 双方言包，各自拥有 DDL/迁移、FTS、向量、
│   │                        #   ACL 渲染（AclPlan→SQL）、审计 sink、备份钩子；**不引入 ORM**（方言差异集中
│   │                        #   在 FTS/向量/JSON 三处，查询构建器帮不上——维持「SQL 收口在 store 层手写」）
│   ├── backend.py          # StorageBackend 协议（原 repo.py 接口 hybrid_search/insert/delete_by_doc 为种子）。
│   │                        #   **按域分节组合、防单一 God interface（v0.8.3）**——各域独立 Protocol、本文件
│   │                        #   只做组合；以下列域与方法种子（非穷举，新增方法先进域再实现）：
│   │                        #   · Search：recall_fts / recall_vec / recall_by_entities（均收 AclPlan）+
│   │                        #     expand_relations（语义关系递归展开，M2-S1——方言渲染收口于此，v0.7.2/#42 拍板3）
│   │                        #   · Ingest：insert（chunks+FTS 同事务）/ write_embeddings / delete_by_doc /
│   │                        #     switch_active_version / pending_embeddings
│   │                        #   · Acl：read_membership / read_grants（§5.1 第 0/2 步的授权展开与成员校验
│   │                        #     读取收口于此，编译器只消费结果——「core 不碰 SQL」由此闭合，v0.8.3）
│   │                        #   · Admin：组织/维度/取值/授权/成员 CRUD + 任务队列（租约·心跳·认领）+
│   │                        #     上传凭证 + 审计查询
│   │                        #   · Semantic：sync 分批 upsert / missing·retired 推进 / 构建产物与 sem_vec
│   │                        #     读写 / L0 导出（M2-S 起）
│   │                        #   · Audit：outbox 写入 + 月库/分区滚动（方言差异在包内吸收）
│   ├── sqlite/             # 连接工厂（**唯一连接入口**：WAL/busy_timeout/foreign_keys=ON+断言/sqlite-vec
│   │                        #   扩展加载；禁止绕过直连——P0-B，NFR-4）+ migrations/{docs,semantic}/
│   │                        #   （user_version，二维分目录——见边界规则 3）+ fts.py（FTS5 五列/MATCH
│   │                        #   转义——P1-3）+ vec.py（BLOB 距离——P0-1）+ acl_render.py + audit.py
│   │                        #   （月库滚动）+ backup.py（VACUUM INTO）
│   └── postgres/           # 连接工厂（psycopg + 连接池）+ migrations/{docs,semantic}/ + DDL/触发器等价
│                            #   （tsvector 五列 GENERATED、`<=>` 距离、审计按月分区）+ fts.py（to_tsquery
│                            #   转义/加权 ts_rank）+ vec.py + acl_render.py + audit.py（月分区滚动）
│                            #   + backup.py（pg_dump）——差异口径见 known-gaps G-6
├── domain/
│   ├── models.py           # pydantic 实体
│   └── auth.py             # token→user 解析（SSO 验签 + JIT 建档；静态 token 仅开发/测试——D18；委托 token/可信子系统校验）
├── worker/
│   ├── runner.py           # 子进程入口：任务循环（租约认领/心跳/重试）；任务类型 ingest/reindex/reembed/delete + semantic_sync/semantic_build/semantic_retag（D23，限速错峰；reembed＝换模型重嵌入——§5.3，v0.8）
│   │                        #   + maintenance（v0.8.3——周期性维护的统一归属：过期成员物理清理/tombstone 90 天清理/
│   │                        #   未消费凭证回收/审计月库滚动/备份快照/sem_chunk_entities 对账兜底；由 app.py 调度器
│   │                        #   周期投递，低优先级错峰——此前散落 §5.1/§5.3/§6.1/§2 各处无模块落点；
│   │                        #   启动挂 log.py 同套 handler、task_id 进日志上下文（v0.8.5）
│   └── ipc.py              # 与主进程的唤醒协议
├── eval/                   # M3：黄金集运行器 + Recall@k/MRR + ragas 接入
└── web/                    # 前端薄壳（§5.7，原型见 prototype/）：i18n.js（中/英静态字典 + t(key, params) +
                             #   data-i18n——FR-8，v0.9；无 i18n 框架、无构建链，业务数据不译、服务端不感知语言）
```

分层纪律：`api/mcp` 只做协议转换（整理参数与鉴权/组织上下文后调 core，业务校验在 core——如上传的库/维度/授权内校验在摄取入口函数；auto_entities 的 annotate 预识别编排亦在此层——§3 规则 2）；`core` 是业务逻辑层——编排（ingest/retrieve）、编译（acl→AclPlan）、分析（quality）、切分（chunking）各居其位，共同约束是**不碰 SQL/方言**（acl 的授权展开与成员校验读取经 backend 协议 Acl 域，见 `store/backend.py`）；`store` 是唯一碰 SQL 的层——**全部连接经 store 层连接工厂（SQLite：`store/sqlite/`；PG：`store/postgres/`——D24；外键/PRAGMA/扩展加载/连接池一致性——issue #32 P0-B）**：

```python
def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=5.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")       # 必须每个连接设置，不持久化
    conn.execute("PRAGMA synchronous = NORMAL")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:   # 不用 assert（python -O 会剥离——#33 P1-1）
        raise RuntimeError("foreign_keys pragma failed")
    return conn   # sqlite-vec 扩展加载同在此处；审计月库建表/触发器也走本工厂；测试：插孤儿行断言 IntegrityError
```

**PG 连接纪律（v0.9.1 随 M0b-3 补）**：psycopg3 工厂（单连接 + ConnectionPool configure 同入口）逐连接执行——`SET TIME ZONE 'UTC'`（与 SQLite `CURRENT_TIMESTAMP` 的 UTC 语义对齐，M0b-1 R2 拍板）、`SET standard_conforming_strings = on`（Literal 单引号加倍转义以此语义为前提——防 off 配置下反斜杠逃逸，防御纵深）、server_version≥16 与 pgvector `<=>` 可用断言（显式 raise 非 assert——同 sqlite 纪律）。**迁移竞态口径（v1.1 实证）**：`schema_migrations` 锁外 `CREATE TABLE IF NOT EXISTS` 的并发首启竞态真实形态 = **`UniqueViolation`（pg_type_typname_nsp_index，23505——主形态）/ `DuplicateTable`（42P07——间或）**，处置 = 双捕获 + `to_regclass('schema_migrations')` 复核在场则干净继续、表确实不在则原异常照抛（fail-closed）——实现见 store/postgres/migrate.py，竞态回归 test_pg_scaff 双异常类参数化。

迁移约定（#33 P1-1）：SQLite 改表走"建新表→拷数据→删旧表"，期间**临时关闭外键**、结束后跑 `PRAGMA foreign_key_check`，有违例回滚——写进迁移框架，否则 schema v2 撞外键。**v1.1 实例（0002，M0b-3）**：存量向量 `INSERT..SELECT` 搬运入 chunk_vectors（合法成对行——embedding 非空且 embed_model 非空；孤立行显式丢弃并断言）后 DROP COLUMN，`foreign_key_check` 空为准。

横切面：**运行日志（v0.8.5）**——`log.py` 只做装配（JSON→stdout、上下文、中间件、降噪），各层直接用标准库 `logging` + contextvars 上下文（request_id/task_id），**不属于任何一层、不构成分层纪律的例外**；**审计 ≠ 日志**——业务/权限事实落库走 store 层 Audit 域（outbox 投递、不可丢、可查询——FR-6），运行诊断走 stdout（可丢、运维侧收集，TEST-CASES T-S10 的「对账任务日志」即出自此处）；检索每请求打一行耗时分解（嵌入/召回/融合/rerank）——NFR-8 标定与 M0b 压测的数据源；**指标栈（Prometheus 等）不引入**（违反 D2 零中间件，登记为演进缝）。

**语义模块边界规则（D23，#35 §4.4）**——防"服务职责变宽"演成大杂烩：

1. `core/docs/` 与 `core/semantic/` **互相不 import 对方内部实现**（除第 2 条两处显式接口外，双向禁止——v0.8.4 对称分包后升为**包级互斥**：import-linter 契约进 CI 机械执法，不再依赖点名清单与评审纪律，「语义层职责膨胀」风险由此有结构防线）；两者只共同依赖 `store/`（连接工厂、backend 协议）与 `domain/`（鉴权、组织上下文）——**基础设施共享，领域模型与维度 ACL 编译器不共享**。
2. 交叉点只有两个，都走显式接口：**ingest 标注**——摄取流水线在块写入同事务调 `semantic.annotator.tag(chunks, org)`，版本切换/删块同事务调 `semantic.untag(doc_id, version)`；**实体召回**——`core/docs/retrieve.py` 调 `semantic.expand(ids, rels, depth)` 只拿到实体 id 集合，召回 SQL 仍由 docs 侧编译（带 §5.1 完整 ACL 产物）。`search` 的 `auto_entities=true` 识别由 **api/mcp 层**在调 `core/docs/retrieve` 前执行（annotate 结果作 `entities` 参数传入）——`core/docs/retrieve` 不 import `semantic.annotator`，交叉点保持两个（v0.8.3 钉死）。
3. `sem_*` 表与 docs 表同主库、前缀区分；迁移脚本按 **docs/semantic × sqlite/pg 二维分目录**（`store/<dialect>/migrations/{docs,semantic}/`——方言包各自拥有 DDL，同一迁移号双方言各一份；v0.8.3 随 D24 明确物理位置），语义表 M2-S1 才落库（M0a/M1 的 schema 不含）。
4. 新增实体类型或关系类型 = schema 变更（CHECK 约束 + `sem_rel_types` 种子），走迁移脚本与评审，不允许运行时自由扩展。

## 4. 数据模型（SQLite DDL v1——本节为 **SQLite 渲染**，PG 等价映射见设计说明末条，D24/v0.8）

```sql
PRAGMA journal_mode = WAL;   -- 其余 PRAGMA 是连接级设置（busy_timeout/foreign_keys/synchronous），见 §3 连接工厂

-- ============ 组织与知识库（D7/D15：多组织 + 多知识库） ============
CREATE TABLE orgs (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE datasets (             -- 知识库：组织内的业务分组/管理单元，不承担权限（D15）
  id          TEXT PRIMARY KEY,
  org_id      TEXT NOT NULL REFERENCES orgs(id),
  name        TEXT NOT NULL,        -- VAT 实务库 / 费用制度库
  description TEXT,
  created_by  TEXT,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(org_id, name)
);

CREATE TABLE dimensions (            -- 维度定义（配置页 CRUD 对象，D9；v0.4 冻结复审：生命周期与过滤彻底解耦——#34 必修 1 方案 A）
  id            TEXT PRIMARY KEY,    -- ULID
  org_id        TEXT NOT NULL REFERENCES orgs(id),
  key           TEXT NOT NULL,       -- region / tax_type
  name          TEXT NOT NULL,       -- 作业区域 / 税种
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),  -- 生命周期：编译器只对 active 生成条件；retired=唯一放宽路径（退役权限事件，§6.2）
  required      INTEGER NOT NULL DEFAULT 1,  -- 仅控制上传校验（强制选值），不影响过滤
  enabled       INTEGER NOT NULL DEFAULT 1,  -- 仅控制上传页是否展示/选值（停用=收紧的上传体验），不影响过滤
  grant_source  TEXT NOT NULL DEFAULT 'local',  -- 授权真值源：local | sync:<system>（D16——同步维度管理页只读）
  value_source  TEXT NOT NULL DEFAULT 'local',  -- 取值枚举是否来自企业主数据
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP,
  UNIQUE(org_id, key)
);

CREATE TABLE dimension_values (      -- 维度取值枚举（value 即稳定编码——企业主数据码，label 可改不影响引用）
  id           TEXT PRIMARY KEY,
  dimension_id TEXT NOT NULL REFERENCES dimensions(id) ON DELETE RESTRICT,  -- P0-C：禁止级联绕过权限事件
  value        TEXT NOT NULL,        -- CN / OVERSEAS / VAT / CIT（ISO 国家码/税种码，不用中文名）
  label        TEXT NOT NULL,        -- 中国区 / 海外区（显示名，可改）
  status       TEXT NOT NULL DEFAULT 'active',   -- active / disabled（软停用=收紧，D19；物理删除仅无引用时）
  sort_order   INTEGER NOT NULL DEFAULT 0,
  UNIQUE(dimension_id, value)
);
-- 取值字面量不可变：改名走"新建值 + 迁移 + 停用旧值"事件流程（P0-C）
CREATE TRIGGER trg_dimval_immutable BEFORE UPDATE OF value, dimension_id ON dimension_values
BEGIN
  SELECT RAISE(ABORT, 'dimension value is immutable; create a new value and migrate');
END;

-- ============ 用户与组织归属（D7：全局账号 + 多组织成员关系） ============
CREATE TABLE users (                -- 全局账号（跨组织唯一）
  id            TEXT PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  display_name  TEXT,
  token_hash    TEXT,               -- 静态 token（sha256），仅开发/测试与 CI（D18）；生产走 SSO/委托 token
  is_system_admin INTEGER NOT NULL DEFAULT 0,
  disabled_at   TIMESTAMP,          -- 用户软删（离职）——物理删除被 documents.owner 外键挡住（#33 P1-1）
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_org_memberships ( -- 用户 × 组织 多对多，角色按组织独立（D7）
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_id     TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  role       TEXT NOT NULL DEFAULT 'member',   -- org_admin | member
  expires_at TIMESTAMP,                        -- 临时成员关系（P1-7，与授权行 expires_at 同语义）
  PRIMARY KEY (user_id, org_id)
);

CREATE TABLE user_dimension_grants ( -- 授权作用域 = 用户 × 组织（经 dimension 隐式挂组织，D7）
  user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dimension_id  TEXT NOT NULL REFERENCES dimensions(id) ON DELETE RESTRICT,   -- P0-C
  value_id      TEXT NOT NULL REFERENCES dimension_values(id) ON DELETE RESTRICT,  -- P0-C
  source        TEXT NOT NULL DEFAULT 'local',   -- local | sync:<system>（D16 真值源标记）
  synced_at     TIMESTAMP,                        -- 同步维度最近刷新时间；失败保留旧快照并告警
  expires_at    TIMESTAMP,                        -- 临时授权（P1-7）：权限计算过滤过期，定时清理+审计
  granted_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, dimension_id, value_id)
);
CREATE INDEX idx_grants_dim ON user_dimension_grants(dimension_id);
-- 移出组织/成员关系过期清理 → 级联删该组织维度下该用户授权（P1-3；**含 sync 来源授权——预期行为**：
-- 同步适配器写入前须校验目标用户在本组织有有效成员关系，否则会生成孤儿授权——#33 P0-1⑥，§5.6）
CREATE TRIGGER trg_membership_delete_cleanup AFTER DELETE ON user_org_memberships
BEGIN
  DELETE FROM user_dimension_grants
  WHERE user_id = OLD.user_id
    AND dimension_id IN (SELECT id FROM dimensions WHERE org_id = OLD.org_id);
END;
-- 注：「文档 org = 库 org = 维度 org」一致性由服务层写入校验 + 触发器断言；授权行不含 org 列
-- （org 经 dimension_id 唯一归属推得，服务层断言），如 M0 实验证明按文档计算需要 org 冗余再加列。

-- ============ 文档（FR-1，v0.3：版本在用制——P0-A） ============
CREATE TABLE documents (
  id              TEXT PRIMARY KEY,   -- ULID（覆盖更新显式携带——文档身份唯一锚点）
  org_id          TEXT NOT NULL REFERENCES orgs(id),   -- 组织不可删只能停用（#33 P1-1）；org_id 不可变（下方触发器）
  dataset_id      TEXT NOT NULL REFERENCES datasets(id),  -- 归属知识库（D15）；删库走服务层流程（先删文档再删库，§6.2）
  title           TEXT NOT NULL,
  source_uri      TEXT,               -- 上传来源（user:<id> / agent:<id>——agent 代传内容标来源，随检索返回）
  content_hash    TEXT NOT NULL,      -- 内容哈希（重复**提示**，不强制拦截——P0-5）
  mime_type       TEXT NOT NULL,
  page_count      INTEGER,
  parser          TEXT NOT NULL,      -- docling | mineru
  active_version  INTEGER NOT NULL DEFAULT 0,  -- 在用版本（0=尚无在用版本）；检索只见该版本
  active_status   TEXT,               -- 在用版本状态：searchable_lexical | searchable_full | degraded（#33 P0-2.2）
  active_error    TEXT,               -- 在用版本嵌入/质量阶段失败写这里（lexical 切换后 pending 已清空）
  pending_version INTEGER,            -- 处理中版本（NULL=无进行中摄取）；= max(历史版本)+1，失败不复用（P0-2.3）
  pending_status  TEXT,               -- parsing|chunked|searchable_lexical|searchable_full|failed
  pending_error   TEXT,
  pending_dims_json TEXT,             -- pending 版本的新维度（P0-2.1）：pending 期间不生效，切换事务落入 document_dimensions
  owner_user_id   TEXT NOT NULL REFERENCES users(id),  -- 文档所有者（管理面操作权限与来源展示；检索路径无 owner 分支——D22③/#34 必修 2）
  raw_object_key  TEXT NOT NULL,      -- 对象目录键（canonical 真相锚点）
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP
);
-- org 一致性 + 不可变触发器（#33 P2-8/9：防"搬组织/搬库"绕过权限事件；一致性由 BEFORE 触发器断言）
CREATE TRIGGER trg_documents_org_immutable BEFORE UPDATE OF org_id ON documents
BEGIN SELECT RAISE(ABORT, 'documents.org_id is immutable'); END;
CREATE TRIGGER trg_datasets_org_immutable  BEFORE UPDATE OF org_id  ON datasets
BEGIN SELECT RAISE(ABORT, 'datasets.org_id is immutable'); END;
CREATE TRIGGER trg_dimensions_org_immutable BEFORE UPDATE OF org_id ON dimensions
BEGIN SELECT RAISE(ABORT, 'dimensions.org_id is immutable'); END;   -- #33 P2-9：三表齐全
CREATE TRIGGER trg_documents_ds_org_check BEFORE INSERT ON documents
WHEN (SELECT org_id FROM datasets WHERE id = NEW.dataset_id) != NEW.org_id
BEGIN SELECT RAISE(ABORT, 'dataset org mismatch'); END;
-- #34 4.6（M0a 随 schema 落地）：搬库与脏维度双重防护——
CREATE TRIGGER trg_documents_ds_immutable BEFORE UPDATE OF dataset_id ON documents
WHEN (SELECT org_id FROM datasets WHERE id = NEW.dataset_id) != OLD.org_id
BEGIN SELECT RAISE(ABORT, 'dataset move across org is forbidden'); END;
CREATE TRIGGER trg_docdims_consistency BEFORE INSERT ON document_dimensions
WHEN (SELECT dimension_id FROM dimension_values WHERE id = NEW.value_id) != NEW.dimension_id
  OR (SELECT org_id FROM dimensions WHERE id = NEW.dimension_id)
    != (SELECT org_id FROM documents WHERE id = NEW.doc_id)
BEGIN SELECT RAISE(ABORT, 'document_dimensions consistency violation'); END;
-- 重复检测：索引按 (dataset_id, content_hash) 粗筛；维度一致性由服务层比对 document_dimensions
-- 后提示重复（不强制拦截——P0-5；通用文档多值挂载见 document_dimensions）
CREATE INDEX idx_documents_hash ON documents(dataset_id, content_hash);

CREATE TABLE document_dimensions (   -- 文档维度（**多值**，D19：通用文档可挂 region∈{CN,OS}；内容混杂仍拆分上传 D4）
  doc_id       TEXT NOT NULL REFERENCES documents(id)        ON DELETE CASCADE,   -- 删文档可级联
  dimension_id TEXT NOT NULL REFERENCES dimensions(id)       ON DELETE RESTRICT,  -- P0-C
  value_id     TEXT NOT NULL REFERENCES dimension_values(id) ON DELETE RESTRICT,  -- P0-C
  PRIMARY KEY (doc_id, dimension_id, value_id)
);

-- 预留不启用（D 决策：user 级临时共享，与维度过滤 OR 合并）
CREATE TABLE acl_entries (
  id             TEXT PRIMARY KEY,
  doc_id         TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  principal_type TEXT NOT NULL,      -- user（group 暂无必要，维度模型已覆盖）
  principal_id   TEXT NOT NULL,
  permission     TEXT NOT NULL DEFAULT 'read',
  granted_by     TEXT,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(doc_id, principal_type, principal_id, permission)
);

-- ============ 块与索引（FR-1/2/3，P0-1/P0-3/P1-1/P1-3 重做） ============
CREATE TABLE chunks (
  rid           INTEGER PRIMARY KEY, -- 显式整数主键（外部内容 FTS 以它关联，VACUUM 后稳定——P0-3a）
  id            TEXT NOT NULL UNIQUE, -- ULID（引用溯源锚点）
  doc_id        TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,    -- 文档内序号
  version       INTEGER NOT NULL,    -- 所属文档版本（=documents.active_version 或 pending_version）
  tombstone     INTEGER NOT NULL DEFAULT 0,      -- 旧版本标记：不进召回、fetch 返回替代提示；保留 90 天后物理删除
  content       TEXT NOT NULL,       -- 正文原文（**不进 FTS**——rerank 专用输入口径）
  title_seg     TEXT NOT NULL DEFAULT '',  -- 标题+heading_path 分词（FTS 权重 3——P1-3：税务文档定位价值高）
  content_seg   TEXT NOT NULL DEFAULT '',  -- jieba 分词后的正文（FTS 权重 1）
  token_count   INTEGER,
  heading_path  TEXT,                -- 结构感知切分的标题层级
  page_no       INTEGER,
  sheet_name    TEXT,                -- Excel 切分专用（行块 chunk 重复表头）
  bbox_json     TEXT,
  keywords      TEXT NOT NULL DEFAULT '',  -- **仅人工维护**关键词（FTS 权重 5——jieba 高频词不混入，P1-3）
  llm_keywords  TEXT NOT NULL DEFAULT '',  -- LLM 生成（FTS 权重 0.5~1，独立低权列，P1-1）
  tags          TEXT NOT NULL DEFAULT '',  -- 人工标签（FTS 权重 8）
  embedding     BLOB,                -- 向量 BLOB（P0-1：ACL 过滤后算距离；NULL=未就绪走 BM25 单路）。
                                     --   M0 实验对比拆 chunk_vectors 分表（P1-2）——~10KB/块（2560 维 float32，D12 修订）拖慢回表与放大 WAL
  embed_model   TEXT,                -- 模型标签 model:dim（D12 修订：如 qwen3-embedding-4b:2560）；NULL=未嵌入；
                                     -- v0.7 起兼作向量召回查询谓词（=当前 config 标签才参与距离计算，防混模型向量）
  dims_json     TEXT NOT NULL,       -- 文档维度冗余投影（多值数组）——M0b 实验候选去除项（P1-2）；**已于 v1.1（0002）删除**（M0b-2 拍板①：visible_docs 胜出，本列仅存于 0001 历史 DDL——迁移链必经，v1.1 终态 schema 无此列）
  detected_at_scale INTEGER,         -- 检测时语料规模（区分度重算策略——P1-8）
  content_sha   TEXT,                -- 区分度检测缓存（重检跳过；v0.8：缓存键 = (content_sha, embed_model)——换模型不因内容相同跳过，重检前清旧 vector_crowding 标记——#42 P1-3）
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX uq_chunks_docver ON chunks(doc_id, version, seq);  -- v0.4：fetch 窗口与"按文档计算"共用（含 version——同文档多版本 seq 不唯一）；替代原 idx_chunks_doc（列相同，去重——#34 4.4）
CREATE INDEX idx_chunks_vec_pending ON chunks(doc_id, embed_model) WHERE tombstone = 0;  -- v1.1（0002）重建：mark_embedding_batch(doc_id,…) 走 doc_id 前缀；pending_embeddings 为 embed_model 等值+NOT EXISTS 不走本索引（0002 注释）

-- FTS5（P0-3 + P1-1/P1-3 重做）：
--   · 五列分权：title_seg 3 / content_seg 1 / keywords 5 / llm_keywords 0.5~1 / tags 8
--     （bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)——参数按列顺序；LLM 词低权防幻觉词压过正文）
--   · 外部内容表 + 三个同步触发器（列清单与 FTS 列一致，否则 'delete' 报 malformed——P1-1）
--   · 查询侧：query 先 jieba 切分，token 双引号包裹且内部 " 转义为 ""，拼 "tok1" OR "tok2"——防语法注入
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  title_seg, content_seg, keywords, llm_keywords, tags,
  content='chunks', content_rowid='rid', tokenize='unicode61'
);
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES (new.rid, new.title_seg, new.content_seg, new.keywords, new.llm_keywords, new.tags);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES ('delete', old.rid, old.title_seg, old.content_seg, old.keywords, old.llm_keywords, old.tags);
END;
CREATE TRIGGER chunks_au AFTER UPDATE OF title_seg, content_seg, keywords, llm_keywords, tags ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES ('delete', old.rid, old.title_seg, old.content_seg, old.keywords, old.llm_keywords, old.tags);
  INSERT INTO chunks_fts(rid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES (new.rid, new.title_seg, new.content_seg, new.keywords, new.llm_keywords, new.tags);
END;
-- 注：无 vec0 虚表——**向量已落 `chunk_vectors(rid, embed_model, embedding)` 分表（M0b-2 拍板②，v1.1/0002）**：
--   PK(rid, embed_model) 支撑蓝绿并存（同 rid 多标签）、rid FK ON DELETE CASCADE 随块清理；
--   chunks.embedding 列已删（存量经 0002 INSERT..SELECT 搬运）；chunks.embed_model 收窄为摄取状态标签
--   （容量与量化见 NFR-2/3——2560 维 float32 ≈10KB/块，M0b-2 实测布局代价见实验报告）
--   PG 后端（D24）：向量列 + `<=>` 精确扫描起步，索引化与 2000 维上限见 known-gaps G-6。

-- ============ 质量反馈环（FR-3） ============
CREATE TABLE quality_flags (
  id            TEXT PRIMARY KEY,
  chunk_id      TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  doc_id        TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,  -- v0.4 补外键（#33 P1-1，防删文档残留孤儿）
  reason        TEXT NOT NULL,       -- vector_crowding | low_idf | both
  detail_json   TEXT,                -- 近邻相似度分布 / IDF 统计（**报告页展示近邻须过同一套 ACL 或只显示数值**——#33 P1-10）
  auto_keywords TEXT,                -- LLM 生成（内部网关）
  manual_tags   TEXT,                -- 人工补充
  state         TEXT NOT NULL DEFAULT 'open',  -- open|resolved|ignored
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at   TIMESTAMP
);
CREATE INDEX idx_qflags_doc ON quality_flags(doc_id, state);

-- ============ 任务（FR-1，ragflow 样板最小化） ============
CREATE TABLE tasks (
  id           TEXT PRIMARY KEY,
  doc_id       TEXT REFERENCES documents(id) ON DELETE SET NULL,  -- 保留任务历史（#33 P1-1）
  type         TEXT NOT NULL,        -- ingest | reindex | reembed | delete | semantic_sync | semantic_build | semantic_retag | maintenance（周期维护——§3，v0.8.3）（reembed＝换模型重嵌入全库扫描——§5.3，v0.8；后三者 M2-S——D23；语义任务限速错峰、重标最低优先级）
  status       TEXT NOT NULL,        -- pending|leased|running|done|failed
  lease_owner  TEXT,
  lease_until  TIMESTAMP,            -- worker 崩溃后任务可被重新认领
  heartbeat_at TIMESTAMP,
  attempts     INTEGER NOT NULL DEFAULT 0,
  error        TEXT,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP
);
CREATE INDEX idx_tasks_status ON tasks(status, created_at);

-- ============ 嵌入指纹基线（D12/#42 P1-1，v0.8——探针存档，见 §5.3） ============
CREATE TABLE embedding_fingerprints (
  id           INTEGER PRIMARY KEY,
  embed_model  TEXT    NOT NULL UNIQUE,        -- config 标签（model:dim）
  baseline     TEXT    NOT NULL,               -- JSON：[{sentinel, vector}]，哨兵 ≥3 条（多哨兵取最小余弦）
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP                      -- 管理面重置基线时更新（重置入审计）
);

-- ============ 审计（FR-6；v0.4：audit_events 属**月库** audit_YYYYMM.db，由连接工厂在月库滚动时创建本表与触发器） ============
CREATE TABLE audit_events (
  id          TEXT PRIMARY KEY,
  org_id      TEXT NOT NULL,
  actor       TEXT NOT NULL,         -- user:<id> / agent:<name>:user:<id>
  action      TEXT NOT NULL,         -- search|upload|grant|revoke|dimension_change|...
  target_type TEXT,
  target_id   TEXT,
  outcome     TEXT NOT NULL,         -- accepted | refused
  request_id  TEXT,
  detail_json TEXT,                  -- 查询词、返回的 chunk_id 列表（查询级审计）
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- append-only 触发器（v0.4 直接给出 DDL；SQLite 无 TRUNCATE，DELETE 均触发下方触发器——#33 P2-10）
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only; retention via monthly file rotation'); END;

-- outbox（主库，v0.4 #34 4.5）：权限事件与业务写同事务入队，后台搬运到月库——"业务改了就一定有审计"
CREATE TABLE audit_outbox (
  id           TEXT PRIMARY KEY,
  event_type   TEXT NOT NULL,        -- grant|revoke|dimension_change|retire|membership|...
  payload_json TEXT NOT NULL,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  shipped_at   TIMESTAMP             -- NULL=待搬运；后台任务搬至月库 audit_events 后回填
);
-- v0.3（issue #32 P1-7）+ v0.4（#33 P1-4）：审计按月分库 audit_YYYYMM.db——当月可追加、过月封存只读
--   （只读打开 + 文件权限 + 封存记末哈希）、到期整文件删除；月库建表与上述触发器由连接工厂在滚动时创建；
--   **权限事件走 outbox**：业务库同事务写 audit_outbox 表，后台搬运保证"业务改了就一定有审计"

-- ============ 业务语义 sem_*（D23，#35 §6.2；M2-S1 经 store/<dialect>/migrations/semantic/ 落库，M0a/M1 不含） ============
-- 类型对齐主库约定：org_id 为 TEXT（orgs.id 是 ULID）、时间列用 TIMESTAMP；实体主键用 INTEGER（AC 自动机值与图遍历友好）
-- 实体：事实列与人工列分列存放——同步只写事实列（name/attrs_json/parent_id/status/synced_at），从不写 curated_json
CREATE TABLE sem_entities (
  id            INTEGER PRIMARY KEY,
  org_id        TEXT    NOT NULL REFERENCES orgs(id) ON DELETE RESTRICT,
  type          TEXT    NOT NULL CHECK (type IN ('concept','system','scenario','template',
                         'template_field','report','report_item','table','column')),
  key           TEXT    NOT NULL,               -- 业务主键，组织内按类型唯一；YAML 用 type:key 引用
  name          TEXT    NOT NULL,               -- 规范名
  parent_id     INTEGER REFERENCES sem_entities(id) ON DELETE CASCADE,
                                                -- 冗余的直接父节点（字段→模板、列→表、项→报表），便于展示；真相以关系为准
  attrs_json    TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(attrs_json)),
                                                -- 事实属性：编码、注释、源系统状态等，同步写入
  curated_json  TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(curated_json)),
                                                -- 人工属性：definition / why / examples / disambiguation / caliber（YAML 合并写入）
  source        TEXT    NOT NULL CHECK (source IN ('sync','curated')),
                                                -- sync：事实来自源系统；curated：纯 YAML 实体（只允许 concept/system）
  source_system TEXT,                           -- template_center / report_center / metadata / scenario_config
  status        TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active','missing','retired')),
                                                -- missing：最近一次同步源端已不存在（宽限期内，默认 7 天）；retired：已下线
  sensitivity   TEXT    NOT NULL DEFAULT 'normal' CHECK (sensitivity IN ('normal','restricted')),
                                                -- restricted：仅持 semantic:restricted 权限可见（annotate 表现为不存在——§6.3）
  synced_at     TIMESTAMP,                      -- 最近一次被同步看到的时间
  curated_rev   TEXT,                           -- 最近一次合并的 YAML commit SHA
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (org_id, type, key)
);
CREATE INDEX idx_sem_entities_org_type ON sem_entities(org_id, type, status);
CREATE INDEX idx_sem_entities_parent   ON sem_entities(parent_id);

-- 别名：AC 自动机与模糊索引都从这里构建
CREATE TABLE sem_aliases (
  id          INTEGER PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  entity_id   INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  alias       TEXT    NOT NULL,                 -- 原文
  alias_norm  TEXT    NOT NULL,                 -- 规范化后：NFKC、全角转半角、小写、去空白（与 annotate 的文本规范化同一函数）
  kind        TEXT    NOT NULL CHECK (kind IN ('name','code','manual','abbr','pinyin','sync')),
                                                -- name/code：由规范名与编码自动生成；manual/abbr：来自 YAML（同步不动）；
                                                -- pinyin：构建时生成，只进模糊索引；sync：源系统自带的别名
  match_mode  TEXT    NOT NULL DEFAULT 'exact' CHECK (match_mode IN ('exact','fuzzy_only','context')),
                                                -- context：歧义短词，只有在同句其他命中有关系时才生效（§5.9）
  weight      REAL    NOT NULL DEFAULT 1.0,
  UNIQUE (org_id, entity_id, alias_norm)
);
CREATE INDEX idx_sem_aliases_norm ON sem_aliases(org_id, alias_norm);
-- 同一个 alias_norm 允许指向多个实体（歧义），由消歧规则处理，不在这里加唯一约束

-- 关系（类型白名单见 sem_rel_types + 触发器）
CREATE TABLE sem_relations (
  id          INTEGER PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  src_id      INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  rel_type    TEXT    NOT NULL,
  dst_id      INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  attrs_json  TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(attrs_json)),
                                                -- 例如 maps_to 的转换规则、derived_from 的取数口径
  source      TEXT    NOT NULL CHECK (source IN ('sync','curated')),
  status      TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active','missing','retired')),
  synced_at   TIMESTAMP,
  UNIQUE (org_id, src_id, rel_type, dst_id)
);
CREATE INDEX idx_sem_rel_out ON sem_relations(org_id, src_id, rel_type, status);
CREATE INDEX idx_sem_rel_in  ON sem_relations(org_id, dst_id, rel_type, status);

-- 关系类型白名单与端点类型约束（迁移脚本按 §5.8 白名单灌入种子数据；新增关系类型 = schema 变更走迁移）
CREATE TABLE sem_rel_types (
  rel_type   TEXT NOT NULL,
  src_type   TEXT NOT NULL,
  dst_type   TEXT NOT NULL,
  PRIMARY KEY (rel_type, src_type, dst_type)
);
CREATE TRIGGER trg_sem_rel_check BEFORE INSERT ON sem_relations
BEGIN
  SELECT RAISE(ABORT, 'relation endpoints must belong to the same org')
   WHERE (SELECT org_id FROM sem_entities WHERE id = NEW.src_id) <> NEW.org_id
      OR (SELECT org_id FROM sem_entities WHERE id = NEW.dst_id) <> NEW.org_id;
  SELECT RAISE(ABORT, 'rel_type/endpoint types not in whitelist')
   WHERE NOT EXISTS (
     SELECT 1 FROM sem_rel_types t
      WHERE t.rel_type = NEW.rel_type
        AND t.src_type = (SELECT type FROM sem_entities WHERE id = NEW.src_id)
        AND t.dst_type = (SELECT type FROM sem_entities WHERE id = NEW.dst_id));
END;
-- 关系行不允许原地改端点：要改就先删再插，保证上面的触发器始终生效（T-S5）
CREATE TRIGGER trg_sem_rel_noupdate BEFORE UPDATE OF src_id, dst_id, rel_type, org_id ON sem_relations
BEGIN SELECT RAISE(ABORT, 'relation endpoints are immutable: delete then insert'); END;

-- 文档块 ↔ 实体：ingest 与重标注时由 AC 自动机写入（**刻意不加外键到 chunks**——理由见下方设计说明）
CREATE TABLE sem_chunk_entities (
  org_id      TEXT    NOT NULL,
  chunk_rid   INTEGER NOT NULL,                 -- = chunks.rid
  doc_id      TEXT    NOT NULL,                 -- 冗余字段，便于按文档整体删除与重标
  version     INTEGER NOT NULL,                 -- = chunks.version
  entity_id   INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  hits        INTEGER NOT NULL DEFAULT 1,       -- 块内命中次数
  dict_rev    TEXT    NOT NULL,                 -- 打标时使用的词典版本，用于判断是否需要重标
  PRIMARY KEY (chunk_rid, entity_id)
);
CREATE INDEX idx_sem_ce_entity ON sem_chunk_entities(org_id, entity_id);
CREATE INDEX idx_sem_ce_doc    ON sem_chunk_entities(doc_id, version);

-- 构建产物登记：AC 自动机、模糊索引（sem_vec BLOB 复用 sqlite-vec）、L0 片段；服务进程按 (org, dict_rev) 懒加载
CREATE TABLE sem_builds (
  id          INTEGER PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  dict_rev    TEXT    NOT NULL,                 -- = hash(active 实体快照 + 别名快照 + YAML commit + embed_model 标签)（v0.8：换模型 → dict_rev 变 → 「相同跳过」失效、强制重建——#42 P1-2）
  yaml_rev    TEXT,
  sync_run_id INTEGER,
  status      TEXT    NOT NULL CHECK (status IN ('building','ready','failed')),
  stats_json  TEXT    NOT NULL DEFAULT '{}',    -- 评测指标、冲突、歧义别名、孤立节点、断链关系
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (org_id, dict_rev)
);

-- 同步运行记录
CREATE TABLE sem_sync_runs (
  id            INTEGER PRIMARY KEY,
  org_id        TEXT    NOT NULL,
  adapter       TEXT    NOT NULL,               -- template_center / report_center / metadata / scenario_config / yaml
  started_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at   TIMESTAMP,
  status        TEXT    NOT NULL CHECK (status IN ('running','succeeded','failed','aborted_guard')),
                                                -- aborted_guard：触发删除比例保护后中止、零写入（§5.8）
  stats_json    TEXT    NOT NULL DEFAULT '{}',  -- inserted / updated / missing / retired / conflicts
  error         TEXT
);
```

设计说明（v0.4）：

- **组织与库的隔离纪律**：一切检索/列表 SQL 的第一条件是 `org_id = :org`（跨组织零可见；检索路径无 owner 分支——D22③/#34 必修 2，owner 经管理面看元数据）；库过滤（`dataset_id IN (...)`）是组织内的可选收窄；维度授权与维度定义都在组织作用域内解析。
- **维度冗余的取舍（M0b-2 已拍板①）**：`chunks.dims_json` 曾是 `document_dimensions` 的投影（多值数组），检索 SQL 按 JSON 解析编译成常量条件（§5.1）；**M0b-2 实验选定"按文档计算"（visible_docs+MATERIALIZED），dims_json 已于 v1.1（0002）整体删除**——一致性维护点消除，维度真源= `document_dimensions`（检索输出 dims 经 store 层聚合回填，§6.1）。
- **向量存 BLOB 不用 vec0**（P0-1）：vec0 的 KNN 在虚拟表内部取 top-k 后才能 JOIN 过滤，等于 post-trim；BLOB + `vec_distance_cosine()` 在 ACL 过滤后的行集上算距离，"先过滤后扫描"（扫描量 = 用户可见量）。M0b 实验对比 `chunk_vectors` 分表（~10KB/块——2560 维 float32，D12 修订——拖慢回表与放大 WAL）。
- **FTS5 五列**（v0.4）：`unicode61` 只做兜底分词；`title_seg`（3）/`content_seg`（1）/`keywords` 仅人工词（5）/`llm_keywords`（0.5~1）/`tags`（8）分列加权；查询侧同词典切分 + token 双引号包裹且内部 `"` 转义为 `""`。
- **语义表设计要点（D23，#35 §6.3）**：①**事实列与人工列分开**——同步只写 `name` / `attrs_json` / `parent_id` / `status` / `synced_at`，**从不写** `curated_json`，也不动 `kind IN ('manual','abbr')` 的别名："同步不覆盖人工内容"由列级分工保证，不依赖代码自觉（T-S1）；②**`sem_chunk_entities` 不加外键到 `chunks`**——`chunks` 走版本在用制与墓碑机制，清理由 docs 在删块/版本切换时**同事务**调 `semantic.untag(doc_id, version)`，另有定时对账任务兜底（T-S10），避免语义表反向约束文档核心表；③**`missing` 宽限期**（默认 7 天后转 `retired`）与同步侧**删除比例保护**（§5.8）双保险，防源系统接口偶发空返回把图清空；④`sensitivity='restricted'` 实体只有持 `semantic:restricted` 权限的调用方可见（annotate 不返回 span、get_entity 404、展开不出现——T-S9）；⑤`parent_id` 只是展示用冗余，真相以 `has_field` / `has_column` / `has_item` 关系为准，同步时两者同事务写入；⑥组织隔离硬约束：**org 作用域 `sem_*` 表**（sem_entities / sem_aliases / sem_relations / sem_chunk_entities / sem_builds / sem_sync_runs）全带 `org_id`、关系端点同组织由触发器校验（T-S5/T-S7）——`sem_rel_types` 为**全局白名单配置表、无 org_id**，不在此列（v0.6.1 修正表述，#38 P1-2/#39：原「全部 `sem_*` 表」与 §4 DDL 不符）。
- **PG 映射（v0.8，#42 P1-7——本节 SQLite 专有机制的 PostgreSQL 等价，PG 方言包已随 M0b-1 spike 交付）**：`RAISE(ABORT)` 触发器 → plpgsql `EXCEPTION`（错误码沿用 abort 语义）；审计**按月分库文件** → 按月**分区表**（连接工厂滚动建分区，接口不变——§2）；`VACUUM INTO` 备份 → `pg_dump` / 基础备份（NFR-10）；`BEGIN IMMEDIATE` → 普通事务（MVCC 无单写限制）+ 必要处 `SELECT … FOR UPDATE`；`user_version` 迁移 → `schema_migrations` 表（**锁外建表竞态双捕获口径见 §3——v1.1 实证**）；`PRAGMA foreign_keys=ON` → 原生外键约束；sqlite-vec `vec_distance_cosine` → pgvector `<=>`（精确扫描起步——G-6）；FTS5 五列 + au/ad/ai 触发器 → **tsvector 五列 GENERATED**（显式 regconfig 双参 `to_tsvector('simple', …)`——GENERATED 列要求表达式 immutable）+ 加权 `ts_rank` 求和（方向差异按 §5.2 名次约定吸收）；jieba 词典升级 → 分词列重算迁移（GENERATED 依赖应用层分词结果，词典变更须触发全量重算——known-gaps G-6）。**审计 append-only 的 TRUNCATE 防护（v1.1 补，M0b-1 R2）**：PG `TRUNCATE` 不触发行级触发器——父表+每分区显式落 `BEFORE TRUNCATE` statement 触发器（PG 16 父表 statement 触发器不克隆到分区）；消息与 SQLite 同源词根（append-only）。

## 5. 关键设计

### 5.1 维度 ACL 编译器（core/docs/acl.py）

输入：`user_id` + 组织上下文（无 org 路径 REST=token org claim 优先、`X-Org-Id` 头兜底 / org 路径段 REST=路径 + 头一致性——D18 统一规则，v0.9.4 按实现细化）；输出：可下推进召回 SQL 的 WHERE 片段（**结构化 builder 生成 AST 再渲染 SQL，禁止字符串拼接**）。逻辑（v0.4：**全部状态字段进入计算——P0-1**）：

1. **成员关系校验**（第 0 步，含过期）：`(SELECT role FROM user_org_memberships WHERE user_id=:uid AND org_id=:org AND (expires_at IS NULL OR expires_at > :now))`——无有效行即拒绝（系统管理员豁免仅限管理端点，D22）。**读路径只过滤、不删除**（避免检索请求抢 WAL 写锁并连带写 outbox——#34 4.2）；过期行的物理删除交**定时任务**（触发 cleanup 级联清授权 + 审计）。**续期禁令由触发器从机制上保证**（T2/T23）：

```sql
CREATE TRIGGER trg_membership_no_extend
BEFORE UPDATE OF expires_at ON user_org_memberships
WHEN OLD.expires_at IS NOT NULL AND OLD.expires_at <= CURRENT_TIMESTAMP
BEGIN SELECT RAISE(ABORT, 'expired membership: delete then re-add'); END;
```
2. **授权展开**（含过期与停用，同一条 SQL）：

```sql
SELECT dim.key, v.value
FROM user_dimension_grants g
JOIN dimensions       dim ON dim.id = g.dimension_id AND dim.org_id = :org AND dim.status = 'active'  -- 只展开 active 维度（#34 必修 1）
JOIN dimension_values v   ON v.id   = g.value_id     AND v.status = 'active'   -- 停用取值=收紧（T3）
WHERE g.user_id = :uid
  AND (g.expires_at IS NULL OR g.expires_at > :now)                            -- 过期授权即失效（T1）
```

3. 对每个 **`status='active'`** 的维度编译统一模板（#34 必修 1 方案 A + 必修 3——**v0.9.1 注：M0b-2 已选定 visible_docs 路径，下方 json_each 模板 SQL 保留为编译产物语义说明**（统一模板的「有值过滤/空值放行」语义以 AclPlan 结构为准）；**渲染层自 v1.1 起统一 `WITH visible_docs(doc_id) AS MATERIALIZED` CTE 形态**——json_each 渲染模板已删除，语义等价由 M0a 双写法验证 + M0b-2 12 组复核背书；**v0.7.2 注：编译器产出方言无关 AclPlan，渲染收口 store 层（D24/#42 拍板3）**）：

```sql
( NOT EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.k'))          -- 维度空值 → 不过滤（放行）
  OR EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.k') je
             WHERE je.value IN (:grants_k)) )                        -- 有值 → 需与授权集有交集
```

**全部 active 维度统一"有值则过滤、空值不过滤"**（必选/可选、启用/停用无差别——required/enabled 不影响过滤，只管上传）；**用户在维度 k 无授权（:grants_k 为空集）→ 编译器直接生成 `NOT EXISTS(...)` 单条件**（该用户只能看到 k 为空的文档，非"整体不可见"——#34 必修 3；空集**禁止**生成 `IN ()` 语法）；`retired` 维度不生成条件（唯一放宽路径，走退役权限事件）；**新增维度时零存量文档消失**（全空值放行），回填即逐篇收紧（上传页与管理页对空值文档提示"待补维度"）；必选改可选、停用均不放宽（T4/T20）。
4. **无 owner 分支**（#34 必修 2 推荐方案）：检索路径只有维度 ACL 一种语义；owner 查看自己处理中/在用文档走 `list_documents` 与文档详情接口（管理面，只返回元数据与状态，不返回块内容）——彻底消除"覆盖上传处理中窗口重新看到在用全文"的 T17/T21 越权路径。

编译产物（**v0.7 起为方言无关结构化计划 AclPlan**——org / 各维度规则（key + 授权集）/ dataset / doc 过滤；空授权集单条件、统一空值模板、retired 不生成等语义规则**只在编译器实现一次**，由所选后端渲染为对应 SQL（D24）；下例为 **SQLite 渲染**示意——统一模板 + 外层约束 + 版本限定，#34 必修 1/2/3）：

```sql
-- 组织 org:tax 内，用户 region=[CN, OVERSEAS]、tax_type=[VAT]；两维度均 active；文档维度多值（D19）
SELECT c.* FROM chunks c JOIN documents d ON d.id = c.doc_id
WHERE ( ( NOT EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.region'))            -- region 空值放行
          OR EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.region') je WHERE je.value IN ('CN','OVERSEAS')) )
      AND ( NOT EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.tax_type'))
          OR EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.tax_type') je WHERE je.value IN ('VAT')) ) )
      -- 无 owner 分支（必修 2）；无授权维度编译为 NOT EXISTS(...) 单条件（必修 3）
  AND c.version = d.active_version AND c.tombstone = 0     -- 只召回在用版本（P0-A/P0-2）
  AND d.org_id = 'org:tax' AND d.dataset_id IN (...) AND d.id IN (:doc_filter)
-- FTS 路同构：FROM chunks_fts f JOIN chunks c ON c.rid = f.rowid JOIN documents d ... WHERE f.chunks_fts MATCH :q
--   AND <同上全部条件>（版本条件必须出现在 FTS 路的 JOIN 上——T9 断言 FTS 层无 tombstone 命中）
```

性能注（v0.4）：
- **按文档计算（M0b-2 已选定，v1.1 唯一路径）**：`visible_docs` CTE 用**同一个授权展开函数**（第 2 步 SQL）先求可见文档集合，再 `WHERE c.doc_id IN (visible_docs)` 走 `uq_chunks_docver`——**基于 `document_dimensions` 写出等价语义**（文档在维度 k 无任何行，或有一行 value ∈ 授权集——与统一模板逐字等价，T5/T6/T22 已验）；**v1.1 起 json_each 按块模板已删除，visible_docs 为唯一渲染路径，PG 渲染器 CTE 显式 `AS MATERIALIZED`**（M0b-2 发现 PG 内联计划病理+双峰摇摆——实验报告 §2.3；sqlite ≥3.35 同语法统一）；**CTE 快照口径**：CTE 不读 `v.status/dim.status`（编译时点授权集快照——停用/退役的收紧与放宽经**下次编译**生效，同 Plan 重执行结果稳定，竞态回归 test_v11_schema 双后端锁定）；**dataset/doc 过滤下推进 CTE**（外层保留双保险）；dims_json 去除后「无 IN ()」不变式保持（Plan 层）。
- `json_each` 不接受时备选维度物化列 + 索引（schema v2 预留）；
- **rerank 前兜底断言 + 返回前二次断言**（防御纵深）。

### 5.2 检索管线（core/docs/retrieve.py）

```
query ─→ LLM 关键词增强（**800ms 硬预算、与原始召回并行**；结果作为 RRF 的**第三路 BM25 查询**——不重做
     │   向量召回；超时丢弃。关键路径 = max(原始召回, 增强+BM25) + rerank，计入 NFR-8 预算表——#33 P1-9）
     ├─→ FTS5 BM25 路：query 经 jieba 切分 + token 双引号转义（内部 " → ""）→
     │    bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)   -- 五列按序：title/content/keywords/llm/tags
     │    （PG 后端渲染：tsvector 五列 GENERATED + 加权 ts_rank 求和——D24；评分函数差异见 known-gaps G-6）
     │    + 版本条件（JOIN chunks/documents）+ ACL WHERE
     ├─→ 向量路（P0-1 写法）：query embed（Embedder provider——OpenAI 兼容 API，D12 修订；
     │    **服务不可达→本路跳过，降级 BM25 单路并记审计；探针拒绝档（换底模）→ 同款降级（v0.8，
     │    §5.3/NFR-8——跨底模距离无意义）**）→
     │    SELECT ..., vec_distance_cosine(cv.embedding, :q) AS dist       -- PG：<=> 算子（D24）
     │    FROM chunks c JOIN documents d ... JOIN chunk_vectors cv        -- v1.1：向量分表（M0b-2 拍板②）
     │      ON cv.rid = c.rid AND cv.embed_model = :current_model         -- ← D12：模型标签谓词迁 cv，
     │    WHERE <完整 ACL 条件>                                          --   非当前标签行不进距离计算
     │    ORDER BY dist LIMIT :k                                        --   （蓝绿并存期按谓词天然隔离）
     │   （待嵌块无 cv 行只走 BM25 路；旧标签清理见 §5.3 重嵌入流程——方案二蓝绿已选定）
     ├─→ 实体召回路（**M2-S3 可选，D23**——调用方传 entities 或 auto_entities=true 才启用；§5.10）：
     │    semantic.expand(seed, ENTITY_RECALL_RELS, depth=1) → 实体集合 E（≤50）→
     │    SELECT c.rid, SUM(ce.hits × 权重) FROM sem_chunk_entities ce JOIN chunks c JOIN documents d
     │    WHERE ce.entity_id IN E AND <与上两路**完全相同**的 ACL 编译产物 + 版本条件>   -- ← 不另写 ACL
     ─→ RRF 融合（k=60；向量缺失的 chunk 只在 BM25 路，自然退化单路；实体路 k 相同、权重可配默认 1.0）
     ─→ ACL 兜底断言（rerank 前：不该进模型的内容不进模型——P2-4 统一）
     ─→ 取 top-32 → rerank（Reranker provider——API 调用，Cohere 风格 /rerank【待决-5 已确认 2026-10-22】；**不可达→跳过重排用 RRF 序并记审计；none 实现→跳过重排（配置态，不标降级——v0.9.2 勘误）**，喂 content 原文——原文与 query 发往内网网关，同信任域口径见需求 NFR-6）
     ─→ 分数归一 [0,1]（min-max/clamp 双分支，ragflow 模式）
     ─→ 返回前二次 ACL 断言 → top-k（≤20，含 chunk_id/doc_id/title/page_no/score/dims/source；M2-S3 起附 matched_entities）
```

要点：召回期不做用户阈值过滤（dify #35233 教训）；阈值只作用于归一后的最终分；**useful-early 语义**由"向量分表行可缺 + 先过滤后距离"自然成立——无 `chunk_vectors` 行（待嵌）的 chunk 只走 BM25 路，摄取中的文档即刻可搜（FR-1 阶段拆分）；**CPU 推理改为模型 API 调用（v0.7——本机不再有模型推理）：query 嵌入 + rerank + LLM 增强的 HTTP 调用全部异步/线程池，绝不阻塞事件循环**；rerank 并发上限信号量保护；`top_k` 服务端硬上限 20。性能预算与 SLO（P95 ≤ 2s）见需求 NFR-8，M1 实测校准。**实体召回路（D23）**：三路（FTS/向量/实体）必须使用**同一个** ACL 编译产物（T-S8 断言三路并集 ⊆ 用户可见块集合）；M2-S3 在 docs 黄金集上做开/关对比，recall@10 与 MRR **不回退**才允许 `auto_entities` 默认开启，否则保持显式参数。**降级可观测（v0.8，#42 P1-4；v0.9.2 勘误——「或 none」移出降级枚举）**：任何降级（嵌入不可达 / rerank 不可达 / 探针拒绝档）统一发 `search.degraded` 审计事件（reason 与响应 `notice.degraded` 同源）并在响应 notice 标注；rerank `none` 为运维配置态、**不标降级不发该审计**（可观测信号 = 配置档位 + `notice.degraded` 为空——检索耗时日志的 routes 字段是召回路数、不含 rerank 阶段，不可用作 none 的可观测依据）。**后端评分方向统一（v0.8，#42 P1-8）**：SQLite `bm25()` 越小越相关（负值）、PG `ts_rank` 越大越相关——方向差异在 backend 内吸收，**StorageBackend 协议一律返回名次（rank，1 起）**，RRF 与归一只消费名次（排序断言按名次集等价——A-17）；PG 侧 query 经应用层 jieba 分词后以 `&` 连接拼 `to_tsquery('simple', …)`——同一分词器产出 token、各自按目标语法转义（SQLite 双引号包裹 / PG to_tsquery 特殊字符转义——复审修订）。**v1.1 后三路 ACL 统一 visible_docs CTE**（拍板①——基础/FTS/向量共用同一 CTE 文本，双方言归一化参数记号后逐字相同，TC-ACL-06 断言锁定）。

### 5.3 摄取管线与 worker（core/docs/ingest.py + worker/runner.py）

任务状态机：`pending → leased → running → (done | failed)`；worker 心跳 5s、租约 60s，租约过期任务可被重认领；`attempts ≥ 3` 进 failed 留人工。断点粒度 = 阶段（各阶段幂等，重跑从上一完成阶段续）。SQLite 写竞争治理（NFR-9）：`busy_timeout` + worker 短事务分批提交 + **查询级审计异步写、权限事件走 outbox**（月库与业务写天然隔离——#34 4.5）。

阶段编排（**P0-4 拆分：index_fts 先于 embed，BM25 即刻可搜**；upload 时新维度写 `pending_dims_json`、写权限校验在 upload 即做——P0-2.1）：

```
parse（docling→统一块结构；扫描件路由 MinerU；mojibake 质量门；TXT 编码探测）
→ chunk（结构感知切分 256–512 / Excel 按 sheet 行块（重复表头）；jieba 生成 content_seg）
→ index_fts（chunks + FTS 同一事务；**M2-S3 起同事务追加语义打标**：`semantic.annotator.tag(chunks, org)` 用当前 ready 的
     AC 自动机只做第 1 层识别写 sem_chunk_entities（不跑模糊兜底）；打标失败不阻断——记 warning、标记文档待重标，
     交 semantic_retag 补做——D23/#35 §8.4；文档状态 → searchable_lexical）
→ embed（Embedder provider 分批 64（OpenAI 兼容 API——D12 修订）；每批**写入前校验 len==config.dim**
     （不符 raise，不写库）；逐批 UPDATE embedding/embed_model=model:dim；服务启动时**指纹探针**——
     对固定哨兵文本取向量与首部署存档比对余弦，防网关静默换底模；两档阈值（G-8 临时值）：
     余弦 < 0.99 仅告警；< 0.95 拒绝以同标签写入 + 告警，并同步关闭查询侧向量路——检索降级
     BM25 单路 + notice（跨底模距离无意义，v0.7.2/#42 拍板2；换标签重嵌入完成后恢复）。
     探针细节（v0.8，#42 P1-1）：哨兵 ≥3 条、取最小余弦判定（容忍 fp16/批次抖动）；基线存主库
     元数据表 embedding_fingerprints（按 config 标签存档，schema 随 M0a 迁移落）；首部署无基线 →
     探测建档并放行；管理面 API 重置基线（入审计）；启动 + 周期探测（默认 10 分钟、可配——运行中
     换底模可发现，周期档同样走两档阈值））
→ index_vec（逐批就位；全部完成 → searchable_full）
→ quality（区分度检测 → quality_flags → LLM 关键词 → 回写 llm_keywords）
```

文档更新（覆盖，显式 doc_id）：新版本以 `pending_version` 走完管线 → 按 D20 切换时机**单事务原子切换**（P0-A）：

```sql
BEGIN IMMEDIATE;
-- 旧块：标记 + **删 chunk_vectors 向量行（v1.1——原 embedding=NULL 语义的等价迁移）** + **清五列 FTS 内容**（清空后 au 触发器执行 FTS 'delete' 再插入空行——
-- UPDATE 不触发 ad、旧注释有误；FTS 里残留空 rowid 不影响 MATCH，#33 P0-2.4/T9）
DELETE FROM chunk_vectors
 WHERE rid IN (SELECT rid FROM chunks
                WHERE doc_id = :doc AND version = :old_version);   -- v1.1 分表级联兜底显式化
UPDATE chunks
   SET tombstone = 1,
       title_seg = '', content_seg = '', keywords = '', llm_keywords = '', tags = ''
 WHERE doc_id = :doc AND version = :old_version;
UPDATE documents
   SET active_version = pending_version,
       active_status  = pending_status,               -- 首次切换=searchable_lexical；覆盖切换=searchable_full（#34 4.1）
       active_error   = NULL,                         -- v0.9.3 设计缺项补全（Committer 裁定，M1-2 R2 实现）：成功切换清旧版本残留错误——
                                                      -- 否则 active_status=searchable_full 与 active_error 非空并存（状态互斥破坏）；与首传路径 set_doc_active_status 同款
       pending_version = NULL, pending_status = NULL, pending_error = NULL
 WHERE id = :doc AND pending_version = :expected_pending;   -- 乐观校验，防并发（P0-2.3/T7）
-- 同事务：pending_dims_json 解析写入 document_dimensions（P0-2.1——v2 维度切换前不生效，T6）
-- 同事务（M2-S3 起，D23）：semantic.untag(:doc, :old_version) 清旧版本块的 sem_chunk_entities 行（T-S10）；
--   删除文档 / 失败版本删块同样同事务 untag；另有定时对账任务兜底（sem_chunk_entities 刻意不加外键到 chunks——§4 设计说明）
COMMIT;
```

**并发与失败（v0.4，P0-2.3）**：pending 期间再来的覆盖上传 → **409**（同一时刻只有一个 pending）；pending 失败 → `pending_status=failed` 且**立即 DELETE 该版本全部块**（经 ad 触发器移出 FTS——失败不留检索残留，T8），重试用新版本号（`pending_version = max+1` 不复用）；删除文档即取消其任务，worker 每阶段开始前检查文档存在与版本归属；embed 批次回写带防护 `WHERE rid=:rid AND tombstone=0 AND version IN (:active,:pending) AND embedding IS NULL AND embed_model = :batch_label`（批次启动时钉死标签——切模型窗口内旧模型在途批次回写被拒；不拒则成**孤儿向量**：向量非 NULL 进不了 pending、旧标签被查询谓词排除，永久不召回也不重嵌——v0.8，#42 必修2）。

**切换时机（D20）**：首次上传（active_version=0）在 `searchable_lexical` 即切换在用（保留先可搜收益；此后嵌入进度写 `active_status`、失败写 `active_error`——P0-2.2）；覆盖上传等新版本 `searchable_full` 再切换（旧版本全程服务）；新版本失败旧版本不受影响。tombstone 块保留 90 天（审计回溯）后物理删除；`fetch` 旧块返回 `{doc_id, active_version}` 对象替代提示（**不承诺块级映射**——重切分后无对应）。

**换模型重嵌入（v0.7 新增，D12/#41；v0.8 修补驱动与孤儿向量——#42 必修2；**v0.9.1 定案方案二蓝绿——M0b-2 拍板③**）**：换嵌入模型（或网关换底模被指纹探针拦下）→ ①改 config 四件套（provider/model/dim/度量）；②**投递 `reembed` 任务类型**（M2 管理面「手动重索引」入口；扫描谓词 = **`chunks` 中无对应 (rid, :new) cv 行的在用块**——v1.1 后等价于旧「embedding IS NULL OR embed_model != :new」语义）：**方案二蓝绿（已选定）**：新标签向量并行写入 `chunk_vectors`（PK(rid, embed_model) 支撑新旧并存）→ 覆盖率 100%（分子/分母闭合 SQL 见仓库 RUNBOOK.md，限 tombstone=0 且 version=active_version）→ **原子切 `current_model` 配置标签**（零 SQL，同 dict_rev 切换模式 §5.8）→ 旧标签行延后清理（DELETE chunk_vectors WHERE embed_model=:old——**sqlite WAL ≈4MB 极廉价；PG 为满量死元组（≈552MB 量级 WAL）靠页内复用消化、需归还 OS 时 VACUUM FULL/pg_repack**——实测）；**全程向量路功能零降级**（M0b-2 实测：共存窗口 sqlite 零放大、pg 有读代价风险幅度跑间波动，见实验报告 §3.3/§5.5）。~~方案一（置空重建、迁移期 BM25 降级）~~已弃用（对照数据留实验报告 §3.3）。重嵌入窗口内任务行记 done/total 进度（管理面嵌入覆盖率面板数据源）；③quality 随之重跑——**缓存键 = (content_sha, embed_model)**（换模型不因内容相同被跳过）、重跑前清旧 `vector_crowding` 标记、区分度拥挤度绝对阈值按新模型余弦分布**重标定**（rerank/RRF 不受影响）；④**语义层强制重建**：`dict_rev` 已并入嵌入标签（§5.8），换模型 → 「相同则跳过」失效 → `semantic_build` 重跑、`sem_vec` 模糊向量按新模型重算；MRL 截断时标签带 `:trunc` 后缀区分。**流程挂 M2 管理面「手动重索引」（runbook 见仓库 RUNBOOK.md §1——引用实验报告 §3.5/§3.3）**。

### 5.4 区分度检测（core/docs/quality.py，v0.3 P1-8 + v0.4 P1-10 更正）

- **向量拥挤度**：新 chunk 向量取**组织内且仅在用版本**（`tombstone=0 AND version=active_version`——否则新旧版本互为拥挤近邻制造误报，#33 P1-10）的 top-8 近邻，`mean(sim) > 绝对阈值` 判拥挤（初值 M1 真实语料重标定；**换嵌入模型须重标**——阈值按模型余弦分布，v0.7 D12）；入库单块检测走 SQL 暴力扫描（量小）；
- **批量重算路径（v0.4 更正；v0.7 维度按现网模型更新）**：10 万 × 2560 维（qwen3-embedding-4b，D12 修订——原 1024 维假设）全量矩阵乘约 2.5×10¹³ flops，numpy/BLAS 分块矩阵乘 CPU **分钟级可行**（v0.3"不可行"论断有误——真正慢的是 SQL 标量函数逐行）；重算（`detected_at_scale` 比例 + 每周抽样）在 worker 低峰期把组织内在用块向量分块载入 numpy（float16 或流式，~1GB@10 万块，纳入内存预算 NFR-9）批处理；
- **词面通用度**：token 平均 IDF 低于**绝对阈值**；新组织冷启动引用全局语料 IDF；
- **报告页防旁路（#33 P1-10）**：`quality_flags.detail_json` 的近邻信息展示时**过同一套 ACL**，或只显示相似度数值不展示近邻内容（T18）；
- 触发 → LLM 生成关键词写 **`llm_keywords` 独立低权重列**（标来源，不与人工 `keywords`×5 混列）；**口径如实**（非 Contextual Retrieval）；
- OneRAG 借鉴项落地处：parse 后 **mojibake 质量门**（正常字符比 <0.55 → 告警/重试/失败三档）。

### 5.5 鉴权、身份与组织上下文（domain/auth.py + mcp/server.py）

- **登录：企业 SSO（D16）**——token 验签（OIDC 优先，协议待需求待决-2 确认）→ 解析全局用户；**首次登录 JIT 建档**（`users` 表自动落库：id/username/display_name），管理员不建账号只配授权。
- **agent 代人检索（D18）**：**委托 token（Token Exchange）**——`aud=knowledge-lattice`、短 TTL、`sub`=用户、`act`=agent 标识进审计；**拒绝 token 原样透传**（MCP 规范明令）；**请求体权限字段一律忽略并记审计、请求正常处理**（对齐 requirements FR-4/D18——v0.6.1 措辞对齐，#38 P1-9/#39）。**降级（v0.3）**：IdP 不支持时走**可信子系统**——agent 服务自身凭证（mTLS/服务 token）须在服务白名单，请求头 `X-On-Behalf-Of: <user_id>` 声明用户，知识库校验白名单后按声明用户计权、双身份（服务+用户）进审计；数据模型与 D18 一致（弱化 act/sub）。静态 token 仅开发/测试（含 CI）。
- **M0b 实测项（issue #32 P1-6）——✅ 已完成（M0b-2，PR #48）**：`langchain-mcp-adapters` 按用户切换委托 token 的客户端形态（每用户会话一个 client vs 自定义 transport 每请求注入头）、连接开销与 token 过期刷新——**结论**：会话建立 ~10ms/持有会话热调用 ~2.2ms，adapters 默认 tool 路径每调用 ~15.6ms（7× 热调用），两形态均可行、推荐按形态 B（transport 注入）做长会话低成本刷新；**依赖互斥发现**：adapters（mcp 1.x）与 fastmcp 4.1.3（mcp 2.x）同进程不共存——实验客户端走独立 env，服务端依赖清单零引入（§7 口径）；token 过期=认证在工具层（会话不断、调用 401），形态 A 刷新=弃会话重建。详见 benchmarks/report-m0b-2.md §4。
- **组织上下文统一规则（v0.4，D18；v0.9.4 按实现细化）**：REST 无 org 路径段端点=token org claim 优先、`X-Org-Id` 请求头兜底（org 路径段端点由路径 + 头一致性承载）；MCP 以委托 token 的 `org` claim 优先（按组织签发、单值）、无 claim 时读运行时在连接/传输层注入的 `X-Org-Id` 头；两者并存且不一致 → 400；**工具参数中的 org 一律忽略并记审计**；缺失即 400，无隐式默认。逐请求按 §5.1 第 0 步（含过期）校验成员关系。
- **可信子系统降级三条约束（v0.4，#33 P1-5）**：①白名单条目带 `allowed_orgs` + 按服务限流；②**用户在场证据**——请求附用户 SSO id_token/短期断言，校验 `sub` 与 `X-On-Behalf-Of` 一致（防服务凭证冒充离线用户）；③`X-Org-Id` 由运行时按用户会话注入。**有期限：上生产前必须切 Token Exchange 或落实②**（D18）。
- MCP server 挂 60s 超时中间件（ragflow 同款纪律）。

### 5.6 权限管理：授权维护与真值源闭环（D16 v0.2）

维度授权按维度声明真值源（`grant_source`），维护闭环四件套：

1. **管理页单点配置**：组织管理员逐用户调整（查询时实时展开，改即生效——D6）；**同步维度（`sync:<system>`）管理页只读**、CSV 批量导入时跳过，防人工覆盖真值；
2. **批量导入/导出（主通道）**：CSV `username, dim_key, values...`（**不带 org 列**——路径已含组织，列与路径不一致整批拒绝，#33 P2-19）；导入按「用户×组织」幂等全量替换、**仅替换 grant_source='local' 的授权**（sync 不动）、差异预览后确认；**写入前校验目标用户在本组织有有效成员关系**（防孤儿授权，#33 P0-1⑥）；支持 `expires_at` 列；
3. **同步适配器（`adapters/grant_sync.py`）**：拉取源接口 + 显式映射表（"申报系统·VAT 申报岗 → tax_type=[VAT]"）+ 定时任务；**幂等全量替换、失败保留旧快照并告警**（不清空不放开）；写 `source='sync:...'` 与 `synced_at`；生产前把语义匹配维度（法人主体/国家）切只读同步；
4. **对账（漂移治理）**：季度导出 ↔ 业务岗位表映射比对 + 审计回放兜底；离职调岗经 HR/SSO 事件即时撤销（演进项）。

### 5.7 前端薄壳（web/）

五个视图（文档 / 检索测试 / 权限 / 语义层 / 任务与审计——原型 v0.5），由 FastAPI 托管静态文件，无构建工具（原生 HTML/JS + 少量 fetch），**UI 永远是薄壳**——所有能力先有 API 契约（§6）再有页面；M2 管理面（权限 / 语义层视图）**先 API + 最小 UI**（完整页面后置，issue #31 P2）。交互原型见 `prototype/index.html`（v0.5，issue #36；mock 数据、浏览器直接打开），**信息结构与 UI 风格均为实现基准**，逐视图对接 REST。语义层视图（同步记录、冲突报告、实体浏览）原型已含，实现仍为可选项（D23，非必需，随 M2-S3）。

**界面国际化（FR-8，v0.9——2026-10-22 对话决策）**：五视图**中 / 英双语**——机制为 `web/i18n.js` 静态字典（zh/en 键值表 + `t(key, params)` 占位符替换 + `data-i18n` 属性承接静态文案）与头部语言切换（「中 | EN」，`localStorage` 持久化、**默认中文**——企业中文用户为主，浏览器 locale 不作强制）；切换后 `<html lang>`（zh-CN/en）与 `<title>` 同步更新并整页重渲染。**翻译范围红线：只译 UI 文案**（导航/按钮/表头/状态标签旁注/空态/教学说明/placeholder/提示），**业务数据不译**——文档标题、实体名与定义、维度取值标签、用户与组织名等随数据本身语言，检索命中集合与权限行为不随界面语言变化；状态枚举（`searchable_full` 等）、API 路径、工具名（`annotate` 等）、章节引用（§5.1 等文档内锚点）保持原样。**服务端不感知语言**：API 契约、审计事件、运行日志、错误码单一口径，i18n 仅限展示层（请求不带语言参数、行为无语言分支）。机制随 M0a 静态页壳落地、新增页面文案进字典；原型（prototype/）后续按同款机制补双语作 UI 基准（时机随实现，不阻塞 M0a）。

**实体浏览按规模设计**（§5.8 口径：10⁴~10⁵ 节点，模板字段 / 报表项 / 列等叶子约占 97%），**不做常驻的全量实体列表**（侧栏窄列塞不下 486 个模板，任何竖列都不行）：①默认落地为**类型总览**——九类卡片携全图计数（根类型可浏览，叶子标注「经父节点 / 搜索直达」）+ 需要关注项（missing / 冲突 / 受限）；②**搜索为主入口**——对应 `search_entities` / `GET /semantic/entities?q=&types=`，命中以**全宽结果表**呈现（名称 / 类型 / 键 / 别名 / 关系数 / 状态 / 来源，类型内按名称排序），只显示 top-N 并在截断时明示（服务端 top_k ≤ 50）；③**类型 facet 单选**（对应 `types=` 参数取一——九类是互斥主轴而非可叠加标签，跨类型发现走「全部 + 搜索」；总览卡片与筛选胶囊同一状态，再点一次取消）；④**实体详情独立成页**——返回按钮 + 父级面包屑 + 关系列表 + 关系图；⑤**关系图与关系列表同口径：按（关系类型 × 方向）分组、每组最多 3 个端点**——连线颜色区分关系类型，组内超出以「+N 更多」计数占位（点击即在列表展开该实体全量关系），分组 × 封顶天然限定图的规模：模板被上百个场景使用时呈现「3 个代表 + 计数」而非不可读的毛球，因此无需另设聚合降级模式；深度 2 只沿已展示端点扩展、每点同样封顶 3；整页受 depth ≤ 2 / fanout_limit ≤ 200 / `truncated` 语义约束。原型 mock 渲染 42 个实体（含「10 个场景共用同一模板」「12 列宽表」两个高扇出样本），计数与截断提示按真实规模口径展示。

### 5.8 语义层：同步、YAML 覆盖层与构建（core/semantic/，D23——#35 §6.1/§7）

**定位**：业务语义 = 术语 + 业务对象关联，建模为**类型化对象图**（属性图：实体 + 有类型的关系）。关系本来就写在业务系统配置里，**直接同步，不用 LLM 从文本抽取**（不做 GraphRAG）；规模 10⁴~10⁵ 节点、边为节点 1~3 倍、查询为 1~3 跳有起点的局部遍历——SQLite + 递归 CTE 毫秒级，**不引入图数据库**（同时出现节点 >10⁶、常需 4 跳以上、需全图算法时再评估 openCypher 嵌入式方案；数据模型按属性图设计，迁移不改模型）。局部借鉴 GraphRAG 的一点：文档块 ↔ 实体关联（`sem_chunk_entities`），但由 AC 自动机确定性打标、不调 LLM。

**实体类型与关系类型白名单**（代码常量 + `sem_rel_types` 种子 + 触发器三处一致）：

| type | 含义 | 事实来源 | 典型 key |  | rel_type | src → dst | 基数 | 来源 |
|---|---|---|---|---|---|---|---|---|
| `concept` | 业务概念 | YAML | `vat.input_credit` |  | `uses` | scenario → template | N:M | 场景配置 |
| `system` | 系统/平台名词 | YAML | `sys.tax_hub` |  | `has_field` | template → template_field | 1:N | 模板中心 |
| `scenario` | 作业场景 | 场景配置中心 | 场景编码 |  | `backed_by` | template → table | N:1（允许 N:M） | 模板中心 |
| `template` | 模板 | 模板中心 | 模板编码 |  | `maps_to` | template_field → column | N:1 | 模板中心 |
| `template_field` | 模板字段 | 模板中心 | `模板编码.字段编码` |  | `has_item` | report → report_item | 1:N | 报表中心 |
| `report` | 报表 | 报表中心 | 报表编码 |  | `child_of` | report_item → report_item | N:1 | 报表中心 |
| `report_item` | 报表项（树） | 报表中心 | `报表编码.项编码` |  | `derived_from` | report_item → template_field / column | N:M | 报表中心或 YAML |
| `table` | 业务表（轻量节点） | 元数据系统 | `db.table` |  | `has_column` | table → column | 1:N | 元数据系统 |
| `column` | 列（轻量节点） | 元数据系统 | `db.table.column` |  | `refers_to` | concept / system → 任意实体 | N:M | YAML |
|  |  |  |  |  | `related_to` | concept → concept | N:M | YAML |

**三种内容的分工**（「源端事实」＝源系统已有的具体对象与关系——名称、编码、层级、关系边；旧称「骨架」，2026-10-19 改称，[#35](https://github.com/yq3/lab/issues/35) 原文仍用旧称）：

| 内容 | 示例 | 谁维护 | 存在哪 | agent 怎么用 |
|---|---|---|---|---|
| 源端事实 | 模板编码与名称、字段列表、模板→表、字段→列、场景→模板、报表项树 | 同步适配器（自动，每日） | `sem_entities` / `sem_relations` 事实列 | `get_entity` 展开关系 |
| 人工内容 | 别名、缩写、定义、口径、消歧、示例、L0 标记 | 业务/数据同学，Git PR 评审 | Git YAML → `curated_json` / `sem_aliases(manual,abbr)` / curated 关系 | `annotate` 识别、`get_entity` 读说明 |
| 详情 | 列类型、样例值、分区、血缘 | 元数据系统 | **不落库** | `describe_table` 实时透传 |

**源系统接入前置条件（#37，2026-10-20 成文——既有隐含口径的显式化）**：

1. **接口形态**：每个源系统提供能枚举「当前完整状态」的**只读查询面**——可以是多个列表接口由适配器分页拼装，也可以是约定的导出文件（`SourceAdapter.fetch()` 只要求吐出全量快照记录，传输方式无关）；不要求单一大接口，**不做增量**（增量同步是 NFR-5 已登记演进缝）。**全量快照语义是删除比例保护与 missing 检测的前提，不可退让**。
2. **维度属性（可选携带，不强制——#37 评论决策）**：快照可携带实体的维度属性（如模板的 region/国家字段）；是否携带由各业务系统按自身业务自定——需要维度隔离的源系统在接口/导出中携带并写入实体维度绑定，维度值域与本地维度不一致走**显式映射表**（grant_sync 同款模式，映射关系进 YAML / 配置维护）。实体维度 ACL 为 NFR-5 登记的演进缝（#37），触发前不启用；届时缺维度值的实体按统一模板**空值放行**（与文档侧 D5 同构，编译器无类型分支），「应带而未带」**记冲突**（数据质量事件，管理面提示补齐，不是权限事件）。配套对冲：适配器对平时携带维度属性的源做**填充率骤降告警**（参照删除比例保护，防缺值静默变宽）；管理面/同步报告展示**每个源是否携带维度属性与填充率**（维度覆盖是 per-source 属性，防误判区域隔离已全局生效）。
3. **连接配置（per-org）**：源系统连接参数（endpoint / 凭证 / 超时）进 `config.py` 的 **per-org 结构**（org → 源系统实例），部署时配置、重启生效；`fetch(org)` 据此解析目标实例，多组织多实例场景由该配置承载。**不引入管理页 CRUD 与 `sem_sources` 注册表**（POC 取舍：源系统种类封闭、适配器本质是代码）。
4. **MCP 为允许的传输形态之一（v0.7 #41 确认，非决策变更——本节本就「传输方式无关」）**：源业务系统可自建 MCP 服务、同步适配器作 MCP client（复用 fastmcp 的 client 能力，无新依赖类型）。给源系统团队的工具契约四条：①**全量快照语义不可退让**（不做增量、不做按需查询——第 1 条不变）；②可翻页拼全量（`list_xxx(cursor, limit) → {records, next_cursor}` 契约，10⁴~10⁵ 实体每晚几十至几百次调用可承受）；③只读 + 服务身份认证 + per-org 实例路由（第 3 条同款）；④**`describe_table` 透传必须留在本服务内部**（「只对已登记 table 实体开放」的防枚举门 + 3s 超时 + degraded——§6.3），**不允许 agent 直连源系统 MCP**。组织成本权衡：源系统本就计划自建 MCP（供其 AI 场景）时复用一份省一套 REST 快照接口，否则 REST 分页更成熟。

**同步适配器接口**（`core/semantic/adapters/`，只读拉取、幂等、输出始终是"当前快照"）：

```python
class SourceAdapter(Protocol):
    name: str                       # template_center / scenario_config / report_center / metadata
    def fetch(self, org: str) -> Iterable[EntityRecord | RelationRecord]: ...

@dataclass
class EntityRecord:
    type: str; key: str; name: str
    parent_key: str | None          # 例如 template_field 的父节点是 template:TPL_xxx
    attrs: dict                     # 编码、注释、源端状态等
    aliases: list[str] = ()         # 源系统自带的别名 → kind='sync'

@dataclass
class RelationRecord:
    src: tuple[str, str]            # (type, key)
    rel_type: str
    dst: tuple[str, str]
    attrs: dict = None
```

| 适配器 | 产出实体 | 产出关系 | 频率 |
|---|---|---|---|
| `template_center` | template、template_field | has_field、backed_by、maps_to | 每天 + 手动触发 |
| `scenario_config` | scenario | uses | 每天 |
| `report_center` | report、report_item | has_item、child_of、derived_from（如源端有） | 每天 |
| `metadata` | table、column（**只拉被 backed_by/maps_to 引用到的** + YAML 显式列出的，不全量镜像） | has_column | 每天 |
| `yaml` | concept、system；其他类型的覆盖层 | refers_to、related_to、人工补的 derived_from | Git 合并后 webhook 触发 + 每天一次兜底 |

**同步流程（每个适配器一次 run，`core/semantic/sync.py`）**：

1. `sem_sync_runs` 插入 `running` 记录；
2. `fetch()` 拿快照，构建 `(type, key)` 集合；
3. **删除比例保护**：快照相对库内该来源（`source='sync' AND source_system=本适配器 AND status='active'`）的消失比例超阈值（默认 20%）→ run 置 `aborted_guard`、发告警、**不做任何写入**（T-S2）；
4. 单个写事务内（必要时分批，每批 ≤1000 行）：①实体 `ON CONFLICT(org_id,type,key) DO UPDATE` **只更新事实列** + `status='active'`、`synced_at=now`；②快照里没有但库里该来源 active 的实体 → `missing`；③`missing` 超宽限期（默认 7 天）→ `retired`，其关系一并 `retired`（T-S4）；④关系 upsert，端点解析不到的记冲突不写入；⑤重建 `kind IN ('name','code','sync')` 别名（先删后插，**只动这三种 kind**）；
5. 更新 run 状态与 `stats_json`，投递 `semantic_build`；
6. 写审计 outbox 事件 `semantic.sync`（run id + 统计）。

**幂等性**：同一份快照连续跑两次，第二次 inserted / updated / missing 均为 0（T-S3）。

**YAML 规范**（`semantic/` 独立 Git 仓或 lab 子目录：`_schema/*.schema.json` + `concepts/` + `templates/` + `report_items/` + `scenarios/` + `l0.yaml`；过渡期即按此 schema 建仓，迁移零改动）：

```yaml
# concepts/vat.yaml —— 纯人工实体（只允许 concept / system）
- id: concept:vat.input_credit          # type:key，全局唯一，CI 校验
  name: 进项税额抵扣
  aliases: [进项抵扣, 抵进项, 认证抵扣]
  abbr: [JXDK]
  definition: >
    一般纳税人购进货物、服务等取得合规扣税凭证后，按规定从销项税额中抵减的进项税额。
  why: 影响当期应纳税额，是增值税申报的核心环节。
  examples: [本月进项抵扣怎么算, 抵进项的发票有哪些要求]
  disambiguation:
    - not: concept:vat.input_transfer_out
      hint: 进项转出是抵扣后因用途改变需要转回，方向相反
  refers_to: [template:TPL_VAT_INPUT, report_item:VAT_MAIN.L12]
  l0: true                               # 进 system prompt（受 L0 预算约束，默认 1500 token）
  sensitivity: normal
  owner: tax-domain                      # CI 必填

# templates/TPL_VAT_INPUT.yaml —— 覆盖层：按 id 挂到同步来的实体上（未同步到的 CI 只警告）
- id: template:TPL_VAT_INPUT
  aliases: [进项采集模板, 进项模板]
  definition: 月度进项发票采集模板，按发票逐行采集。
  caliber: 只采集当期勾选认证的发票，不含海关缴款书。
  fields:
    - id: template_field:TPL_VAT_INPUT.TAX_AMT
      aliases: [税额, 进项税额]
      definition: 发票票面税额
  extra_relations:                       # 源系统缺失的关系，人工补充
    - { rel: derived_from, from: report_item:VAT_MAIN.L12, to: template_field:TPL_VAT_INPUT.TAX_AMT,
        note: 报表中心暂未配置取数关系，按业务口径人工补充 }
```

**合并规则与冲突处理**（`yaml_merge.py`；CI 在合并前拦截，入库时触发器兜底）：

| 情形 | 处理 |
|---|---|
| 覆盖层引用的 id 已同步 | 合并：写 `curated_json`、`manual`/`abbr` 别名、`source='curated'` 关系，记 `curated_rev` |
| 覆盖层引用的 id 未同步或已 retired | 不写入，记冲突，CI 与构建报告给警告；实体恢复后自动生效 |
| 纯人工实体与同步实体 `(type,key)` 相同 | 报错，CI 拦截（纯人工实体只能是 concept/system） |
| 同一别名指向多个实体 | 允许，但 CI 要求至少一方 `disambiguation` 说明，或别名标 `match_mode: context` |
| 别名短于 2 字或是常用词 | CI 拦截，除非显式标 `context` 或 `fuzzy_only` |
| `extra_relations` 与同步关系重复 | 以同步为准，人工条忽略并提示"可删除" |
| `extra_relations` 端点类型不在白名单 | CI 拦截；入库时触发器兜底（T-S5） |
| YAML 删除某覆盖项 | 清空对应实体 `curated_json` 与 manual 别名；事实列不受影响 |
| L0 总 token 超预算（默认 1500） | CI 拦截 |
| 样本值（samples）超过 3 条 | CI 拦截（v0.8——DataAgent 调研借鉴②，#42 P2） |

**构建产物（`semantic_build`，同步或 YAML 合并后触发）**：

1. `dict_rev = hash(active 实体 + 别名 + yaml commit + embed_model 标签)`，与当前 ready 版本相同则跳过（嵌入标签入键——换模型必然重建，v0.8/#42 P1-2）；
2. 产物：**AC 自动机**（`pyahocorasick`，键 `alias_norm`、值 `entity_id` 列表，只收 `match_mode IN ('exact','context')`）；**模糊索引**（名称/别名/一句话定义的向量存 `sem_vec` BLOB 复用 sqlite-vec——向量经 **Embedder provider** 生成、标签随 config 钉死**且入 dict_rev**（换模型强制重算——§5.3 重嵌入④，v0.8），D12 修订；外加拼音与编辑距离辅助表——M2-S3）；**L0 片段**（`l0: true` 条目渲染 markdown，`GET /semantic/l0` 导出）；**构建报告**（冲突、歧义别名、孤立节点、断链关系、评测指标）；
3. **原子切换**：`sem_builds` 新版本置 `ready`；服务进程按 `(org, dict_rev)` 懒加载，旧版本保留到无请求使用（构建中请求始终用旧 `dict_rev`，构建失败旧版本继续服务——T-S12）；**评测回归**：构建报告指标较上一版下降 >2 个百分点则不切 ready，需人工确认；
4. **重标判断**：词典变更涉及别名增删即投递 `semantic_retag`，对 `dict_rev` 落后的文档块分批重新打标——最低优先级、限速，不与 ingest 抢资源。

### 5.9 识别（annotate）与关系展开（get_entity）（core/semantic/annotator.py · expand.py）

**总体时序**：

```
用户问题
  ├─① annotate(text)        AC 自动机确定性匹配 → 歧义消解 → [模糊兜底]
  │       └→ mentions: [{span, entity_id, type, confidence, via, ambiguous, brief}]
  ├─② agent 中间件按类型注入 L1：概念的定义与消歧提示、对象的规范名一行（§6.3）
  ├─③ agent 自主调用 L2：get_entity(id, expand, depth≤2) → 结构化子图；
  │                       search(q, entities=[...]) → 文档证据（带 ACL，§5.10）；
  │                       describe_table(table) → 列详情（实时透传）
  └─④ 组装回答：结构化子图（对象及关联）+ 文档证据（制度、口径）
```

**annotate 三层识别**：

- **第 1 层 AC 自动机（确定性、必跑，P99 < 5ms）**：①文本规范化与 `alias_norm` 同一函数（NFKC、全半角统一、小写——抽成小 package 与过渡期本地版共用）；②最长匹配：重叠保留更长 span，等长按 `weight` 取高；③一个 span 对应多个实体时按序消歧：**上下文共现**（同句其他命中实体与候选有 1 跳关系）→ **会话焦点**（调用方传 `context_entities`，最近几轮已确认的实体）→ **类型先验**（`prefer_types`）→ 仍不定则返回全部候选并标 `ambiguous=true`，交 agent 追问或自判；④`match_mode='context'` 短别名：仅当同句有其他确定命中且两者有关系时保留，否则丢弃；⑤`restricted` 实体对无权调用方表现为不存在（不返回 span）。
- **第 2 层 agentic**：第 1 层未命中但 agent 判断有业务对象 → 自主调 `search_entities(q, types?)`（排序：别名精确 > 前缀 > 拼音 > 向量）；**不在 annotate 内部执行**。
- **第 3 层模糊兜底（`fuzzy=true` 才跑，M2-S3）**：对未被第 1 层覆盖、长度 ≥2 的名词性片段（jieba 词性筛选）依次：拼音完全匹配（同音错字，"留底"→"留抵"）→ 编辑距离 ≤1（仅长度 ≥4 别名）→ 向量近邻 top-3（阈值 0.75）。结果 `confidence` 一律低于第 1 层、`via='fuzzy'`，**中间件不自动注入**，只作候选提示。

**关系展开：类型化 2 跳（core/semantic/`expand.py` 编排——depth ≤ 2、防环、fanout_limit 规则在 core；SQL 经 StorageBackend.`expand_relations` 渲染，下为 SQLite 递归 CTE 实现、PG 方言随 M2-S1——v0.7.2/#42 拍板3，core 不写方言 SQL）**：

```sql
-- :org、:start_ids（json 数组）、:rels（允许的 rel_type，json 数组）、:max_depth（≤ 2，服务端强制）
WITH RECURSIVE walk(entity_id, depth, path, via) AS (
  SELECT je.value, 0, ',' || je.value || ',', NULL
    FROM json_each(:start_ids) je
  UNION ALL
  SELECT CASE WHEN r.src_id = w.entity_id THEN r.dst_id ELSE r.src_id END,
         w.depth + 1,
         w.path || (CASE WHEN r.src_id = w.entity_id THEN r.dst_id ELSE r.src_id END) || ',',
         r.rel_type || CASE WHEN r.src_id = w.entity_id THEN '>' ELSE '<' END
    FROM walk w
    JOIN sem_relations r
      ON r.org_id = :org AND r.status = 'active'
     AND (r.src_id = w.entity_id OR r.dst_id = w.entity_id)
     AND r.rel_type IN (SELECT value FROM json_each(:rels))
   WHERE w.depth < :max_depth
     -- 防环：路径里已出现过的节点不再访问（T-S6）
     AND instr(w.path, ',' || (CASE WHEN r.src_id = w.entity_id THEN r.dst_id ELSE r.src_id END) || ',') = 0
)
SELECT e.id, e.type, e.key, e.name, MIN(w.depth) AS depth, GROUP_CONCAT(DISTINCT w.via) AS via
  FROM walk w JOIN sem_entities e ON e.id = w.entity_id
 WHERE e.org_id = :org AND e.status = 'active'
   AND (e.sensitivity = 'normal' OR :can_restricted = 1)         -- restricted 过滤（T-S9）
 GROUP BY e.id
 ORDER BY depth, e.type
 LIMIT :limit;                                                    -- 默认 200，服务端上限 500
```

说明：①实现时把出边/入边拆成两个 UNION 分支分别走 `idx_sem_rel_out` / `idx_sem_rel_in`（上面为可读写成 OR）；②**高扇出截断**：如一个表下几百列，每节点最多保留 `fanout_limit`（默认 50、上限 200）条并在结果标 `truncated=true`；③典型路径——"场景 X 用到哪些表"：`uses>` + `backed_by>` 深度 2；"字段 F 对应哪个列、哪些报表项从它取数"：`maps_to>` + `derived_from<` 深度 1；④`get_entity` 的 `expand` 参数即 `:rels`（可带方向后缀 `>`/`<`）。

### 5.10 实体召回路：与文档检索的融合（core/docs/retrieve.py ↔ semantic.expand，M2-S3）

1. 调用方传 `entities=[id...]`（≤20）；或 `auto_entities=true` 由服务端（**api/mcp 层——§3 规则 2**）对 query 先执行一遍第 1 层识别；
2. `semantic.expand(ids, rels=ENTITY_RECALL_RELS, depth=1)` 得实体集合 E，**限制 ≤50**；`ENTITY_RECALL_RELS` 默认 `refers_to` / `has_field` / `maps_to` / `related_to`——**不沿 `uses` 这类高扇出关系展开**，避免召回发散；
3. 在 FTS 路与向量路之外新增**实体召回路**（`docs` 侧编译，语义层只提供 E；调分 SQL 经 StorageBackend.`recall_by_entities` 渲染——下为 SQLite 版，PG 方言随 M2-S3，v0.7.2/#42 拍板3）：

   ```sql
   SELECT c.rid, SUM(ce.hits * CASE WHEN ce.entity_id IN (SELECT value FROM json_each(:seed_ids))
                                    THEN 1.0 ELSE 0.5 END) AS s        -- 种子实体 1.0、扩展实体 0.5
     FROM sem_chunk_entities ce
     JOIN chunks c    ON c.rid = ce.chunk_rid
     JOIN documents d ON d.id = c.doc_id
    WHERE ce.org_id = :org
      AND ce.entity_id IN (SELECT value FROM json_each(:entity_ids))
      AND <与 §5.1 完全相同的维度 ACL 编译产物>       -- 复用 docs 编译器产物，不另写
      AND c.version = d.active_version AND c.tombstone = 0
    GROUP BY c.rid
    ORDER BY s DESC
    LIMIT :k_entity;                                    -- 默认 30
   ```

4. 三路 RRF 融合（实体路 k 与其他路相同，权重可配默认 1.0）→ ACL 兜底断言 → reranker（§5.2 顺序不变）；
5. **ACL 不变式**：实体召回路必须走与 FTS 路、向量路**同一个**维度 ACL 编译产物——**T-S8 断言**：同一用户、同一查询下三路结果的并集 ⊆ 其可见块集合；对无权文档里命中实体的块，实体路也召回不到。语义层只提供实体 ID，**不能给文档可见性开任何后门**；
6. 返回的每个块附 `matched_entities`，供 agent 解释"为什么召回了这段"。

## 6. 接口契约

### 6.1 MCP 工具（mcp/server.py，FastMCP——单一 server 分 docs / semantic 两组注册，D23；本节为 docs 组，semantic 组见 §6.3）

```jsonc
// search —— 工具描述（写给 LLM）："检索企业知识库。缺私有信息（制度/手册/申报口径）时调用；
// query 越具体越好（含税种、区域、文档关键词）；返回结果自带 chunk_id 溯源，回答时请引用。"
{
  "name": "search",
  "input":  { "query": "string", "top_k": "int=8",
              "datasets": "string[]? = 限定知识库 id（缺省搜全部权限内文档）",
              "doc_filter": "string[]? = 文档 id 过滤",
              "entities": "int[]? ≤20 = 实体 id，启用实体召回路（M2-S3，D23——§5.10）",
              "auto_entities": "bool=false = 服务端（api/mcp 层——§3 规则 2）先对 query 跑一遍 AC 识别再实体召回（M2-S3）" },
  "output": {
    "results": [{
      "chunk_id": "01J…", "doc_id": "01J…", "dataset": "VAT 实务库",
      "title": "2026 Q3 中国区 VAT 申报指南",
      "page_no": 12, "score": 0.87,
      "dims": { "region": ["CN"], "tax_type": ["VAT"] },   // ← 多值数组（D19）——v1.1 起来源= document_dimensions
                                                           //   聚合回填（store 层 _attach_dims 第二条 IN
                                                           //   查询；dims_json 投影已随拍板①删除——§5.1）
      "source": "user:u1 | agent:tax-copilot",              // ← 来源随结果返回（agent 代传可识别）
      "snippet": "…一般纳税人销售自产货物并提供安装服务的，应分别核算…",
      "matched_entities": [101, 305]                        // ← 实体召回路命中（M2-S3；未启用时省略）
    }],
    "notice": {"vector_pending": false, "degraded": []}
    // useful-early：vector_pending＝本结果缺向量路（未就绪或降级）；degraded ∈ embed_unreachable |
    // rerank_skipped | probe_reject（本请求发生的降级——v0.8 统一为对象，#42 P1-4；TC-RET-02/TC-EMB-04 同口径）
  }
}

// upload —— "向知识库上传文档（agent 采集到的文件）。必须指定知识库与维度元数据，否则会被拒绝。"
{
  "name": "upload",
  "input":  { "upload_id": "upl_xxx",           // 不透明凭证——由 POST /api/uploads 签发（见下）；路径/URL 一律拒绝（P0-D）
              "dataset": "ds:vat",
              "dimensions": { "region": ["CN"], "tax_type": ["VAT"] },   // 多值数组（D19）；值须在调用者授权内（P1-1）
              "doc_id": "string?",             // 覆盖更新显式携带（文档身份）
              "title": "string?" },
  "output": { "doc_id": "01J…", "task_id": "01J…", "status": "queued", "pending_version": 2 }
}
// upload 三步凭证流（P0-D）：
//   ① agent 运行时（非 LLM）POST /api/uploads {filename,size,sha256,content_type} → {upload_id, upload_url, expires_at}
//      （upload_url 短时有效——**成功消费后单次**；失败 PUT 不计消费、可修正重传直至消费/过期——v0.9.4 勘误对齐 TEST-CASES v1.4/#42 P1-12；过期 PUT 410、已消费 PUT 409）
//   ② 运行时 PUT 文件字节到 upload_url
//   ③ LLM 调 upload(upload_id, ...)——校验 sub、org、服务身份三者一致，且未过期、未使用、哈希匹配后进摄取（T11）
//   共享存储场景：白名单根目录 + realpath 规范化 + 前缀校验 + 只读 + 大小/扩展名限制；不支持任意 URL 拉取

// fetch —— "按 chunk_id 取该块前后相邻的内容窗口（先搜后读）。旧版本块返回替代提示。"
{
  "name": "fetch",
  "input":  { "chunk_id": "01J…", "window": "int=2" },   // 前后各 N 块
  "output": { "chunks": [{ "chunk_id": "…", "seq": 41, "content": "…", "page_no": 12 }],
              "replaced_by": { "doc_id": "01J…", "active_version": 3 }?（tombstone 时非空——对象；不承诺块级映射，P0-A/P0-2.5） }
}

// list_documents —— "列出权限内可见的知识库与文档及处理状态。先了解库里有什么，再决定搜什么。"
{
  "name": "list_documents",
  "input":  { "datasets": "string[]?", "active_status": "string?", "limit": "int=50" },
  "output": { "datasets": [{ "id": "ds:vat", "name": "VAT 实务库", "doc_count": 12 }],   // ← 全部统计按调用者权限计算（P1-8）
              "documents": [{ "doc_id": "01J…", "dataset": "ds:vat", "title": "…",
               "active_version": 2, "active_status": "searchable_full",                    // ← 在用/处理中双态四字段（P0-2.2）
               "pending_version": 3, "pending_status": "searchable_lexical",
               "dims": { "region": ["CN"] }, "chunk_count": 143,
               "source": "user:u1 | agent:tax-copilot", "updated_at": "…" }] }
}
```

纪律：检索参数（权重/阈值/召回窗口）服务端固定，不暴露给 LLM（ragflow 反面教训）；`top_k ≤ 20` 服务端硬上限；工具描述动态注入的库/维度概况与一切统计**按调用者权限计算**（不可见文档的存在与数量不泄露）；`search` 返回块带 `source` 字段（agent 代传内容可识别——prompt injection 防御前置）。

### 6.2 REST 端点（api/，v0.4 路径统一：**组织作用域资源一律 `/api/orgs/{org}/...`**；`X-Org-Id` 头用于 MCP 与无 org 路径 REST 的兜底（v0.9.4 按实现登记——见下方 resolve_org 块）；org 路径段 REST 由路径 + 头一致性判定；不一致 → 400——#33 P1-7）

> **非 `/api/orgs/{org}` 路径的组织上下文（v0.9.4 澄清，M1-3 实现口径）**：**全部无 org 路径段的 REST 端点**（`/api/uploads`、`/api/search` 等）走 resolve_org 统一规则——token claim 优先、`X-Org-Id` 头兜底、两者并存不一致 → 400、缺失 → 400，随后按所解析组织校验成员关系（无有效行 403）——D18 v0.4 的「REST=`X-Org-Id` 头」字面在无 org 路径端点按实现细化为 claim 优先/头兜底（`/api/search` 原「X-Org-Id 例外」为 v0.4 表述，实现自 M1-1 起即此形态，v0.9.4 按实现登记）；org 路径段端点仍由路径 + 头一致性承载。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | /api/orgs | 组织列表（系统管理员=全部；普通用户=membership）/ 创建组织（系统管理员）。**组织不可删只能停用**（P1-1） |
| GET / PUT | /api/orgs/{org}/members | 成员列表（含 expires_at）/ 成员与角色管理（组织管理员；**合并原 memberships+users 两端点**——P1-7） |
| PUT | /api/orgs/{org}/members/{id}/grants | 授权全量替换（**只替换 local 授权，sync 不动**；支持 expires_at） |
| GET / POST | /api/orgs/{org}/grants/export · import | 授权导出 / 批量导入（CSV 无 org 列；dry_run 差异预览；幂等全量替换） |
| GET/POST | /api/orgs/{org}/datasets | 知识库列表 / 新建（组织管理员） |
| PATCH | /api/orgs/{org}/datasets/{id} | 库修改；**删除走服务层流程**（先删文档再删库——P1-1） |
| GET/POST | /api/orgs/{org}/dimensions | 维度列表 / 新建 |
| PATCH | /api/orgs/{org}/dimensions/{id} | 维度修改（enabled/required 仅影响上传，**不影响过滤**——D5 v0.4；生命周期 status 由退役端点管理） |
| POST | /api/orgs/{org}/dimensions/{id}/retire | 退役维度（撤过滤的权限事件：影响面预估 + 二次确认 + 审计） |
| GET/POST | /api/orgs/{org}/dimensions/{id}/values | 取值 CRUD；**停用走 PATCH status=disabled**（`dry_run` 返回影响面预估——FR-4） |
| POST / DELETE | /api/orgs/{org}/documents | 上传（multipart 或携带 upload_id；校验库 + 必选维度 + 取值在本人授权内；覆盖带 doc_id）/ |
| DELETE | /api/orgs/{org}/documents/{id} | 删除文档（owner/org_admin；取消其任务） |
| PATCH | /api/orgs/{org}/documents/{id}/dimensions | 修改维度（**pending 期间 409**——P0-2.1；新旧取值均在操作者授权内） |
| GET | /api/orgs/{org}/documents/{id} | 详情（active/pending 四字段 + quality_flags 概要） |
| GET | /api/orgs/{org}/documents/{id}/quality | 质量报告明细（近邻展示过 ACL——§5.4） |
| PATCH | /api/quality-flags/{id} | 人工补充 tags / ignored/resolved |
| GET | /api/orgs/{org}/tasks | 任务列表（状态/进度/错误） |
| POST | /api/orgs/{org}/tasks/{id}/cancel | 任务取消（M2） |
| POST | /api/orgs/{org}/documents/{id}/reindex | 手动重索引（M2） |
| POST | /api/orgs/{org}/semantic/annotate | **语义层（D23，M2-S）**：术语识别，同 MCP `annotate`（`semantic:read`） |
| GET | /api/orgs/{org}/semantic/entities?q=&types= | 实体检索，同 `search_entities`（`semantic:read`） |
| GET | /api/orgs/{org}/semantic/entities/{id}?expand=&depth= | 实体详情与关系展开，同 `get_entity`（`semantic:read`） |
| GET | /api/orgs/{org}/semantic/tables/{key}/describe | 表/列详情透传元数据系统，同 `describe_table`（`semantic:read`；仅已登记 table） |
| GET | /api/orgs/{org}/semantic/l0 | 导出 L0 片段（agent 构建期拉取进 system prompt，返回 `dict_rev`；`semantic:read`） |
| POST | /api/orgs/{org}/semantic/sync/{adapter} | 手动触发同步（`semantic:admin`；写 outbox） |
| POST | /api/orgs/{org}/semantic/yaml/webhook | Git 合并后的回调（校验签名；服务身份）→ 投递 yaml 合并 + 构建 |
| GET | /api/orgs/{org}/semantic/builds · sync-runs | 构建记录 / 同步记录与冲突报告（`semantic:admin`） |
| POST | /api/search | 检索（检索测试页；参数同 MCP search；组织经 resolve_org——claim 优先/`X-Org-Id` 兜底/不一致 400，v0.9.4 按实现登记，原「X-Org-Id 例外」表述作废） |
| POST | /api/uploads | **上传凭证签发**（{filename,size,sha256,content_type} → {upload_id, upload_url, expires_at}；**绑定 sub+org+服务身份**，#33 P1-3）。uploads 表 DDL 以迁移 0003 为准（**实现细节不入 §4——v0.9.4 登记**：三要素列/issued→uploaded→consumed 状态机/expires_at/doc_id·task_id 追溯列） |
| PUT | /api/uploads/{upload_id} | **接收文件字节**（v0.4 补——Bearer 鉴权 + **校验 sub、org、服务身份三者一致且未过期、未使用**（与签发绑定，T11）；按声明 size 拒绝（v0.9.4 勘误——原「截断/拒绝」二义，TEST-CASES 附录 A-13 定拒绝；含不足声明 400 对称面）、写盘后校验 sha256、全局上限 200MB；**M1 集成期实现**，人工 multipart 不依赖） |
| GET | /api/orgs/{org}/audit | 审计查询（org_admin 全量 / 系统管理员仅元数据——FR-6 分级） |
| POST | /api/dev/token | 签发静态 token（**仅 dev/test 配置注册该路由，生产环境 404**——P1-7；只能给自己签或系统管理员签发） |

鉴权：所有端点要求 Bearer token（委托 token 或 SSO）；**可信子系统走服务凭证（mTLS/服务 token 白名单）+ `X-On-Behalf-Of` + 用户在场证据（D18）**；写操作经 outbox 落审计。**语义层权限（D23）**：`semantic:read`（组织成员默认具备——业务对象组织内默认可见）/ `semantic:admin`（org_admin：同步触发、构建与冲突报告）/ `semantic:restricted`（极少数敏感实体的可见权，访问进权限审计）；组织上下文规则与 §5.5 完全一致（`/api/orgs/{org}` 路径 / token org claim），语义层**不复用维度 ACL 编译器**（见 §6.3 权限口径）。

### 6.3 semantic 工具组与 agent 中间件（D23，M2-S1~S3——取代 v0.4「与术语层 glossary-agent 的工具组集成」）

**形态变化**：v0.4 的 D17 让 deepagents 并挂两个 MCP server（本系统 + glossary-agent 的 `lookup_terms`），运行时投影只列为演进点。D23 改为**单一 MCP server 按 docs / semantic 两组注册工具**——glossary-agent 不再独立部署，其调研结论（AC 自动机精确匹配、三层渐进披露、Git YAML/PR 治理、四类黑话分治）成为 `core/semantic/` 的设计输入；v0.4 预留的 `adapters/glossary_loader.py` 位取消。**职责边界不变的部分**：表/列详情真相在元数据系统（本系统只存轻量节点，`describe_table` 实时透传）；L0 核心术语是构建产物（经 `GET /semantic/l0` 导出进 agent system prompt）。

**semantic 组工具清单**（与 docs 组同 server；M2-S1 先交付 `get_entity` / `search_entities` / `describe_table`，M2-S2 交付 `annotate`，M2-S3 交付 `search` 的实体参数与模糊兜底）：

| 工具 | 用途 | 关键限制 |
|---|---|---|
| `annotate` | 识别文本中的业务术语与业务对象（概念、系统、场景、模板、模板字段、报表项、表、列），返回实体 ID 与位置；每轮对话前由中间件调用 | 文本 ≤ 4000 字；AC 层 P99 < 5ms、整体 P99 < 20ms（NFR-11） |
| `search_entities` | 按名称、别名、描述查实体（agentic 第 2 层） | `top_k ≤ 50`；排序：别名精确 > 前缀 > 拼音 > 向量 |
| `get_entity` | 读取实体详情并展开类型化关系 | `depth ≤ 2`、节点 ≤ 500、`fanout_limit ≤ 200` |
| `describe_table` | 透传元数据系统查询表与列详情 | 只对已登记的 `table` 实体开放；超时 3s + 缓存 5min；不可用返回轻量节点 + `degraded=true` |
| `search`（docs 组，参数扩展） | 新增 `entities` / `auto_entities`；返回块附 `matched_entities` | 实体召回路复用 §5.1 ACL 编译产物（T-S8） |

**工具 schema（摘要——完整 JSON Schema 随实现交付；工具描述同样按「写给 LLM 看」纪律撰写）**：

```jsonc
// annotate —— "识别文本中的业务术语与业务对象（概念、系统、场景、模板、模板字段、报表项、表、列），返回实体 ID 与位置。每轮对话前调用。"
{ "name": "annotate",
  "input":  { "text": "string ≤4000",
              "context_entities": "int[]? ≤20 = 会话中已确认的实体，用于消歧",
              "prefer_types": "string[]?", "fuzzy": "bool=false" },
  "output": { "dict_rev": "a1b2c3",
              "mentions": [{ "span": [3, 7], "surface": "进项抵扣", "entity_id": 101, "type": "concept",
                             "name": "进项税额抵扣", "confidence": 1.0, "via": "ac", "ambiguous": false,
                             "brief": "一般纳税人取得合规扣税凭证后从销项税额中抵减的进项税额。" }],
              "candidates": [ /* ambiguous / fuzzy 候选，via='fuzzy' 的中间件不自动注入 */ ] } }

// search_entities
{ "name": "search_entities",
  "input":  { "q": "string ≤200", "types": "string[]?", "top_k": "int=10 ≤50" },
  "output": { "entities": [{ "id": 201, "type": "template", "key": "TPL_VAT_INPUT", "name": "…", "brief": "…", "score": 0.93, "via": "alias" }] } }

// get_entity
{ "name": "get_entity",
  "input":  { "id": "int?", "key": "string? = type:key（与 id 二选一）",
              "expand": "string[]? = 关系类型，可带方向后缀 > 或 <（如 'uses>' 'derived_from<'）",
              "depth": "int=1 ≤2", "fanout_limit": "int=50 ≤200",
              "include": "('curated'|'attrs'|'aliases')[] = ['curated']" },
  "output": { "entity": { "id": 201, "type": "template", "key": "TPL_VAT_INPUT", "name": "…",
                          "curated": { "definition": "…", "caliber": "…" }, "status": "active" },
              "nodes":  [{ "id": 305, "type": "table", "name": "ods.vat_input_invoice", "depth": 1 }],
              "edges":  [{ "src": 201, "rel": "backed_by", "dst": 305, "source": "sync" }],
              "truncated": false, "dict_rev": "a1b2c3" } }

// describe_table —— 透传元数据系统，只对已登记的 table 实体开放（未登记 → 403）
{ "name": "describe_table",
  "input":  { "table": "string = table 实体的 key 或 id", "columns": "string[]?" },
  "output": { "table": "…", "columns": [{ "name": "…", "type": "…", "comment": "…", "sample": "…" }],
              "degraded": false } }   // 元数据系统不可用：返回轻量节点信息 + degraded=true（T-S11）
```

**agent 侧接入（deepagents 薄中间件，#35 §9.4）**：

1. **构建时**：调 `GET /api/orgs/{org}/semantic/l0` 把核心术语写进 system prompt，并记录 `dict_rev`；
2. **每轮 before_model**：①对用户最新一条消息调 `annotate`，传会话已确认实体作 `context_entities`；②对 `confidence=1.0` 且非 ambiguous 的命中按类型注入 L1——概念/系统：`name + brief + disambiguation`；对象（模板、字段、报表项等）：只注入 `name + type + id` 一行，详情留给 agent 经 `get_entity` 获取；③有歧义的命中只注入候选列表并提示 agent"必要时向用户确认"；④**本轮注入总量 ≤ 600 token**，超出按 confidence 与出现顺序截断；
3. **工具**：`search_entities` / `get_entity` / `describe_table` 与带 `entities` 参数的 `search` 交给 agent 自主调用；
4. **降级**：annotate 超时（默认 200ms）或失败 → 本轮跳过注入，不阻塞对话（NFR-11）。

**过渡期（现在~M2，#35 §12.3）**：agent 侧用「同 schema 的 Git YAML + 本地 AC 自动机（pyahocorasick）」只覆盖 concept/system 与 L0；YAML schema 与规范化函数抽成小 package 两端共用（本地版与服务端行为一致，迁移零改动）；中间件接口保持不变（输入文本、输出 mentions），本地 AC ↔ 服务端 annotate 经开关切换并支持灰度，切换时用评测集对比。过渡期 concept 的 `refers_to` 可指向尚未同步的实体，CI 只警告，M2-S1/S2 完成后自然生效。

**权限口径（semantic，#35 §10）**：①**组织隔离是硬约束**——org 作用域 `sem_*` 表全带 `org_id`（`sem_rel_types` 为全局白名单配置表、无 org_id，除外——v0.6.1 修正，#39），查询一律从 `/api/orgs/{org}` 或 MCP 会话组织上下文取 org（规则同 §5.5），关系端点同组织由触发器校验（T-S7）；②**语义层不复用维度 ACL 编译器**——业务对象（模板名/字段名/表名）组织内默认对所有成员可见，可见性要求与文档内容不在一个级别，对实体套维度 ACL 会把必修 1~3 的复杂度再来一遍（**当前口径**；#37 登记的「实体维度 ACL」演进缝触发时以 NFR-5 为准——编译器第二渲染目标，两处互指——v0.8，#42 P1-11）；③**`restricted` 实体**：极少数敏感对象只有持 `semantic:restricted` 权限的调用方可见其实体、别名命中与关系展开，无权时 annotate 中表现为不存在（T-S9）；④**文档证据的 ACL 不变**——凡涉及文档块（`search` 的实体召回路）一律走 docs 的维度 ACL 编译产物（§5.10），语义层只提供实体 ID，**不能给文档可见性开任何后门**（T-S8）；⑤`describe_table` 用服务身份调元数据系统、只允许已登记 table 实体（防借此枚举整个数仓）；元数据系统本身有表级权限则改用委托 token（RFC 8693）透传用户身份，与 D18 一致；⑥**审计**：同步、构建、YAML 合并、restricted 实体访问走审计 outbox（权限类事件）；annotate / get_entity 普通查询走查询级异步审计，与 docs 查询审计共用月库。

**上传凭证的 agent 侧时序（v0.4，#33 P1-3——M1 集成项，与 D23 无关、保留）**：deepagents 侧需要一个**运行时工具/中间件**（非 LLM 直接参与）——LLM 决定"上传某文件"→ 运行时①持委托 token 调 `POST /api/uploads`（声明 filename/size/sha256）→ ②PUT 字节到 upload_url → ③把 `upload_id` 交回对话，LLM 再调 MCP `upload(upload_id, dims, ...)`。凭证绑定 sub+org+服务身份（跨组织无效——T11）；未消费凭证由清理任务回收。

## 7. 技术选型与依赖清单

| 依赖 | 用途 | 备注 |
|---|---|---|
| Python 3.11+ / uv | 运行时与包管理 | 目标机系统 Python 3.9.9 不满足（docling / FastMCP 均硬性要求 ≥3.10，3.9 无降级出路且已 EOL——2026-10-22 用户确认环境并核实下限）；**部署带 uv 托管独立 CPython 3.12、系统解释器不作为依赖**（开发机 3.12.10 与部署同版本；NFR-1 v0.8.2 / known-gaps G-11）；附带：独立构建自带新版 SQLite 且开启扩展加载——sqlite-vec `load_extension` 路径更稳（连接工厂「扩展加载一致性」断言随 M0a 落） |
| fastapi + uvicorn | 控制面 REST | |
| fastmcp | MCP server（**+ 语义同步适配器的 MCP client**——源系统可选 MCP 传输，v0.7 #41） | OneRAG 模块结构参考 |
| docling | 解析（docx/pptx/xlsx/html/pdf 原生） | 进程内库；MIT 代码 + 模型权重 license 风险标注（NFR-7） |
| jieba | 中文预分词 | 中英混排效果 M1 实测（风险登记）；PG 后端预分词结果直接进 `to_tsvector('simple')`，**无需 zhparser**（D24） |
| **httpx（v0.7 扩用途——D12 修订）** | **模型 API 客户端：嵌入（Embedder）/ 重排（Reranker）/ LLM 增强 + 内部网关** | OpenAI 兼容（进程内推理路线取消）；语义同步适配器与 describe_table 透传同用 |
| ~~FlagEmbedding + onnxruntime~~（**v0.7 删除**） | ~~bge-m3 嵌入 + bge-reranker-v2-m3 重排，进程内~~ | 取消（D12/#41）；钉版本纪律保留——标签 `model:dim` 记录进 `chunks.embed_model` 兼作查询谓词；**Reranker 接口必带 none 实现**（端点已确认 Cohere 风格 /rerank——待决-5 关闭 2026-10-22，G-7 闭环） |
| sqlite-vec | **距离函数**（`vec_distance_cosine` 等标量函数作用于 BLOB 列，P0-1；非 vec0 虚表 KNN）——**SQLite 后端** | 一期 ~10 万 chunk 实测（NFR-2，**真实 2560 维**） |
| **psycopg（v0.7 新增，D24）** | **PG 后端**：连接 + pgvector（`<=>` 距离，精确扫描起步） | 扩展白名单已确认——公司 PG 16 + pgvector 0.8.x（2026-10-22，待决-6 关闭、G-6 收窄①闭环）；FTS 用 tsvector 五列 GENERATED——**显式 regconfig 双参 `to_tsvector('simple', …)`**（GENERATED 要求 immutable，v0.8）+ 加权 ts_rank（不依赖 ParadeDB）；差异口径见 known-gaps G-6 |
| **实验客户端依赖归属口径（v0.9.1，M0b-2 实测）** | `langchain-mcp-adapters` 为 **deepagents 调用方侧**接入件（§6.3——agent 侧依赖），**不进服务端依赖清单**：其 mcp 1.x 系依赖与 fastmcp 4.1.3（服务端，钉 mcp 2.x）同进程互斥——实验以 uv 独立 env 隔离实测（M0b-2 实验 3），服务端零引入 | design §8 M0b.3 实测项的依赖归属澄清——服务端 §7 清单保持最小（D2） |
| pydantic v2 | 实体与配置 | |
| python-ulid | 主键 | 时间有序，利于排序与溯源可读 |
| pyahocorasick（M2-S2） | AC 自动机多模式精确匹配——`annotate` 第 1 层、ingest 打标、过渡期 agent 本地版共用（D23） | C 扩展；数万别名构建秒级、匹配 P99 < 5ms；按 (org, dict_rev) 懒加载 |
| pypinyin（M2-S3，可选） | 模糊兜底：拼音完全匹配（同音错字） | 与 jieba 词性筛选、编辑距离、sqlite-vec 向量近邻组成第 3 层 |
|（M3）ragas + deepeval + pytest | 评测与门禁 | judge 走内部网关 |

排除项（明确不引入）：消息队列（tasks 表轮询 + IPC 唤醒足够）、ORM（SQL 收口在 store 层手写，DDL 即文档——**双后端方言包各自渲染 AclPlan，不引入 SQLAlchemy**：方言差异集中在 FTS/向量/JSON 三处，查询构建器帮不上，D24）、前端构建链（静态页）、**图数据库与 GraphRAG 框架**（D23：关系来自确定性配置、规模 10⁴~10⁵ 节点，SQLite 递归 CTE 足够；再评估条件见 §5.8）。**v0.7（D12）另排除**：进程内嵌入/重排推理库（FlagEmbedding / sentence-transformers / onnxruntime）——模型统一走 OpenAI 兼容 API，本地 ollama `/v1` 仅作开发/测试端点。

## 8. 里程碑任务分解（v0.7，与需求 §8 逐条对齐——#33 P1-11/P1-12；M2-S1~S3 语义并行轨道——D23）

**M0a（第 1 周）——骨架 + schema 全量落**
1. 脚手架（uv/config/**StorageBackend 协议 + AclPlan 结构化产物 + 嵌入/重排 provider 接口（D12/D24——SQLite 实现先行，测试自 M0a 起按后端参数化，本地无 DSN 可 skip、CI 必跑 PG（自 M0b job 建立起生效）——v0.7.2/#42）**/迁移框架含外键处理约定，§4 **文档侧**全部 DDL 与触发器一次性落——**`sem_*` 除外**，语义表 M2-S1 经 `store/<dialect>/migrations/semantic/` 落库，见 §3 边界规则 3 / §4 注）；连接工厂（foreign_keys=ON + 显式 raise + 月库滚动建表）
2. 摄取最小链：docling 解析 → 结构切分（五列分词）→ index_fts 入库（BM25 即刻可搜）→ 嵌入分批补齐（Embedder API + dim 校验 + 指纹探针——D12）
3. 检索最小链：BM25 单路 + **完整 ACL 编译器（含状态过滤与统一空值模板——D22①，#34 必修 1/3）**
4. FastMCP `search` + REST multipart 上传 + 静态页壳（含 i18n 机制：`web/i18n.js` 字典 + 语言切换——FR-8，v0.9）
5. 验收：deepagents 经 MCP 一次带 chunk_id 的检索（**开发 JWT 即可**）；插孤儿行 IntegrityError；T1~T5 + T20/T22 在编译器单测先行
6. 并行：待决-2/3（SSO 协议、token 方案）

**M0b（第 2 周前半）——实验（v0.7 扩：五实验 + 结论回写）——✅ 已完成（M0b-1/2/3 三段交付：PR #47/#48 及 v1.1 迁移 PR；实验报告 benchmarks/report-m0b-2.md；以下为原计划与结论对照）**
1. 按块 json_each vs 按文档 visible_docs（同一授权展开函数，~~1/5/10 万块~~ **1/5 万两档——用户 2026-10-24 拍板缩档**；双后端各跑 + 可移植性判据——D24）——**结论：visible_docs+MATERIALIZED 胜出（拍板①），dims_json 删除**
2. 向量同表 vs chunk_vectors 分表回表耗时（模型迁移蓝绿判据——D12/#41）——**结论：分表选定（拍板②）+ 重嵌入方案二蓝绿（拍板③）**
3. langchain-mcp-adapters 按用户委托 token 实测——**已完成（§6.3 实测项注记）**
4. ~~SLO 压测（NFR-8 预算表分项标定，真实 2560 维）~~——**取消（用户 2026-10-24 拍板不压测；NFR-8 标定顺延 M1 基线——TEST-CASES v1.5.2）**
5. PG 后端 spike（D24）：DDL + AclPlan 渲染器；编译器单测 T1~T5/T20/T22 双后端绿（公司 PG 环境已确认：PG 16 + pgvector 0.8.x——待决-6 关闭；~~CI 以 docker postgres+pgvector 必跑~~ **本地门禁脚本 test_gate.sh（用户拍板不建 GitHub Actions——项目将移公司内网）**）——**已完成（M0b-1）**
6. 结论回写 **schema v1.1 迁移**（含 foreign_key_check；dims_json 去留、分表与否在此定）——**已完成（M0b-3：0002 双方言 + 渲染器收敛 + 全量 271 双后端零回归）**

**M1（第 2 周后半~第 3 周）——完整配方 + 版本在用制全链（前移）+ 权限全链 + 凭证集成**
1. 五列 FTS + 双路（先过滤后距离，向量路含 `embed_model` 谓词）+ RRF（增强第三路）+ rerank 32（**Reranker API + none/失败降级——D12**）+ 归一；**PG 后端追平全矩阵（D24；v0.7.2 升正式备选——CI 必跑、skip≠pass，#42 拍板1）**
2. **版本在用制全链**：active/pending 状态机、切换事务（清 FTS 列）、tombstone、并发 409、失败删块、fetch 替代提示（**前移自 M2——M1 越权验收依赖**）
3. 维度 ACL 全链：多值、上传/PATCH 值限授权内、统一空值模板、维度停用/改可选不影响过滤（D5 v0.4）
4. **上传凭证制 + deepagents 集成**（§6.3 时序：运行时工具 + PUT 端点 + 绑定 sub+org+服务 + 清理任务）
5. 区分度环（绝对阈值 + numpy 批量重算 + 报告页近邻过 ACL）
6. 真实文档批量上线（待决-1，合成样例先行）+ 小型黄金集 + Recall@k/MRR + P95 基线
7. 验收：**越权矩阵全绿（双后端参数化各跑——D24；§9 含 T1~T23——T19 删库半句、T20 退役审计半句随 M2 收口，v0.6.1 限定 #38 P1-4/#39）**；真实 query 标注；区分度误报抽查

**M2（第 4~6 周）——生产化**
1. worker 子进程化（心跳/租约/重试）+ 写竞争治理 + embed 回写防护
2. SSO/JIT 对接（M0a 已敲定协议）；委托 token / 可信子系统落地（三约束 + 期限）
3. 管理面 API + 最小 UI（§6.2 全端点：维度停用 dry_run/退役/授权 expires_at/任务取消/重索引（**含换模型重嵌入入口——D12/#41；嵌入面板只读展示当前模型/维度/各库嵌入覆盖率，不做可改参数——改模型=走重嵌入流程**）/审计分级查询）
4. 审计 outbox + 月库滚动 + 封存；删除级联与 90 天物理清理
5. 备份快照 + 恢复演练（**双后端各一份 runbook——D24：SQLite `VACUUM INTO` / PG pg_dump**）
6. 验收：**杀 worker 不丢任务**（任务租约重认领）；outbox 一致性（权限事件必有审计）；恢复演练通过；跨组织隔离全绿；批量导入 500 行正确（sync 不动——T-CSV）

**M2-S1~S3（M2 并行轨道，D23 业务语义——与 M2 生产化并行；M0a/M0b/M1 不含语义层，只在 worker 任务类型与组织上下文上预留扩展点）**

*M2-S1 模板链路（模板 → 模板字段 → 表 → 列）*
1. `migrations/semantic/`（`store/<dialect>/migrations/semantic/` 双方言各一份——§3 边界规则 3）：`sem_*` 全部 DDL + 触发器 + `sem_rel_types` 白名单种子（§4）
2. `template_center` + `metadata` 适配器（SourceAdapter 协议）；同步流程（删除比例保护 / missing 宽限期 / 分批 upsert / 只写事实列 / 别名三 kind 重建 / outbox 事件）
3. 构建任务框架（`semantic_build` 骨架：dict_rev 计算 + 原子切换；AC 自动机留到 S2 接入）
4. semantic 组首批工具：`get_entity`（递归 CTE + 截断）/ `search_entities`（别名精确 > 前缀）/ `describe_table`（白名单 + 超时缓存 + 降级）；REST 对应端点与 `sync` / `builds` / `sync-runs` 管理端点
5. 验收：T-S2 / T-S3 / T-S5 / T-S6 / T-S11；"这个模板落在哪张表、哪个字段"类问题可答

*M2-S2 场景 / 报表项 + YAML 覆盖层*
1. `scenario_config` + `report_center` 适配器
2. YAML 仓库 schema（`_schema/*.schema.json`）与 CI 校验（schema / 别名冲突 / 短词常用词 / L0 预算 / owner / 引用可解析）；`yaml_merge.py` 合并规则表全量实现；`yaml/webhook` 端点
3. 构建产物：AC 自动机（pyahocorasick）/ L0 片段 / 构建报告 + 原子切换 + 评测回归（降 >2pp 不切 ready）
4. `annotate`（AC 层 + 四步消歧 + context 短别名规则 + restricted 过滤）；`GET /semantic/l0`
5. 识别评测集：150~200 条真实问法（工单/群聊/agent 日志）人工标注 span 与 entity_id，覆盖四类黑话、缩写、错别字、歧义词、负样本 ~20%；每次构建自动运行
6. 验收：T-S1 / T-S4 / T-S12；AC precision ≥ 0.95 / recall ≥ 0.80 / 歧义消解 ≥ 0.85 / 负样本误报 ≤ 0.05

*M2-S3 概念 / 文档打标 / 实体召回（M2 末或 M2.5）*
1. `concept` / `system` 纯人工实体全量接入；过渡期 YAML 仓库直接复用
2. ingest 打标（index_fts 同事务 tag；失败不阻断）+ `semantic_retag`（最低优先级、限速）+ 版本切换 / 删块同事务 untag + 定时对账
3. `search(entities / auto_entities)` 实体召回路（`semantic.expand` + docs 侧编译 SQL **复用 §5.1 ACL 产物**）+ 三路 RRF 融合 + `matched_entities`
4. 模糊兜底（拼音 / 编辑距离 / sqlite-vec 向量近邻，`sem_vec`）；`search_entities` 排序补齐拼音与向量
5. agent 中间件从本地 AC 切到服务端 annotate（开关 + 灰度 + 评测集对比）
6. （可选）语义层视图（原型 v0.5 已含）：同步记录、冲突报告、实体浏览
7. 验收：越权矩阵 T-S7 / T-S8 / T-S9 / T-S10 全绿；AC+模糊 recall@3 ≥ 0.92；**检索增益评测**（docs 黄金集开/关实体路 recall@10、MRR）不回退方可默认开启

**M3（第 7~8 周）——评测防线**
1. 完整黄金集（M1 小型集扩容）+ 响应层指标固化
2. judge 双语校准（~50 条人工双评）
3. deepeval 门禁进 CI（预注入回归验证）
4. 在线引用锚点抽样
5. 验收：门禁能卡住一次人为注入的检索层回归；judge-人一致性达标；黄金集覆盖中英三态 query

依赖：M1.2/1.3 依赖 M0a.3；M1.4 依赖 M1.2；M0b 结论回写后方可进 M1；M3 扩量依赖待决-1。**语义轨道（D23）**：M2-S1 依赖 M2.1 的 worker 子进程化与迁移框架就位；M2-S2 依赖 M2-S1 的模板/字段节点作关系端点；M2-S3 依赖 M2-S2 词典质量稳定（否则重标风暴扩散到 docs 检索）与 M2.4 的删除级联（untag 挂接点）；语义轨道任何一步延期**不阻塞 M2 / M3 主线验收**。

## 9. 测试策略（v0.7：含 issue #33 T1~T19、#34 T20~T23、#35 T-S1~T-S12 全量）

- **单元**：ACL 编译器（括号化 AST 断言/多值/状态过滤【过期/停用/成员关系过期】/统一空值模板（空值放行/空集单条件））；**连接工厂外键断言（插孤儿行抛 IntegrityError）**；FTS5 MATCH 转义（`"`→`""`/`*`/`NEAR`/`AND`/`-`）；RRF 与归一；切分边界（表格整块/Excel 行块含表头）；**切换 SQL 后 FTS 无 tombstone 内容**；凭证流（size 截断/sha256 校验/过期/绑定）；**包边界 import-linter（core/docs ↔ core/semantic 互斥——§3 规则 1，v0.8.4）**；
- **集成**：摄取→检索端到端（searchable_lexical 中间态）、版本切换原子性（并发 409/失败删块/回写防护）、任务租约重认领、触发器同步无幽灵命中、迁移 foreign_key_check；
- **越权用例集（CI 常跑）**：原矩阵（用户授权 × 文档维度多值 × 库过滤 × 可选维度空值 × 新增必选未回填 × 移出重加 × 跨组织 × MCP 统计）+ v0.3 四组（版本中间态/删维度取值/PATCH 越权/CSV）+ **T1~T19（#33 §6，逐条对应修复项）**：T1 过期授权清理未跑仍不可见；T2 成员续期不复活旧授权；T3 停用取值收紧；T4 维度改可选/停用不放宽（D5 v0.4——#34 方案 A）；T5 可选维度有值则过滤；T6 v2 改维度切换前后无双方可见（两种 ACL 写法都测）；T7 并发覆盖 409；T8 失败版本无 FTS 残留；T9 切换后 FTS 层面无旧版本命中；T10 待嵌入清单不含 tombstone；T11 凭证跨组织无效；T12 PUT 超量/哈希不符拒绝；T13 可信子系统越界/冒充拒绝并审计；T14 org claim 与头不一致 400；T15 他组织维度 id 403/404；T16 生产配置 token 端点 404；T17 授权撤销后 owner 不再见在用文档（**检索路径无 owner 分支——#34 必修 2**）；T18 报告页近邻不泄露无权内容；T19 删文档/删库按定义成功或明确报错（非裸外键异常）；**T20~T23（#34 §5）**：T20 新建维度零文档消失、回填只收紧、必选改可选/停用不放宽、仅退役放宽且必有审计（**M0a 编译器单测**）；T21 授权已撤销的 owner 发起覆盖上传，处理中窗口检索不到该文档任何版本（**M1 越权矩阵**）；T22 用户在某维度无授权 → 只见该维度为空的文档；授权集为空时编译产物不出现 `IN ()`（**M0a 编译器单测**）；T23 对已过期成员关系 UPDATE expires_at 被触发器拒绝；先删再加后旧授权不复活（M1 越权矩阵）；
- **评测**：M1 小型黄金集 → M3 门禁；
- **语义层功能与不变式（D23，T-S1~T-S12——#35 §13.1；M2-S1~S3 分批落地）**：
  - 单测：**T-S1** 同步不覆盖人工字段（YAML 写入 definition 与 manual 别名后，源端改 name 再同步——`curated_json` 与 manual 别名不变、name 更新）；**T-S2** 删除比例保护（mock 源端返回空快照或少 30% → run 为 `aborted_guard`、库内零写入、产生告警）；**T-S3** 同步幂等（同一快照连续跑两次，第二次 inserted / updated / missing 均为 0）；**T-S4** 宽限期（对象消失先 `missing`，宽限期内恢复回 `active`，超期 `retired` 且关系一并 retired）；**T-S5** 关系白名单与组织一致性（插入跨组织关系、非白名单端点类型、UPDATE 端点均被触发器拒绝）；**T-S6** 递归展开（有环图不死循环；depth > 2 服务端拒绝；高扇出节点截断并返回 `truncated=true`）；
  - 越权矩阵（CI 常跑，并入 §9 越权用例集）：**T-S7** 组织隔离（A 组织的 annotate / get_entity / search_entities 不返回 B 组织任何实体，`dict_rev` 互相独立）；**T-S8** 实体召回不放宽 ACL（同一用户、同一查询下 FTS / 向量 / 实体三路并集 ⊆ 该用户可见块集合；无权文档里命中实体的块，实体路也召回不到）；**T-S9** restricted 实体（无权调用方 annotate 拿不到 span、get_entity 404、关系展开不出现该节点）；
  - 集成：**T-S10** 版本切换 / 删块 untag（覆盖上传切换后旧版本块的 `sem_chunk_entities` 同事务清除；删文档后无残留——对账任务断言）；**T-S11** describe_table 白名单（未登记表 403；元数据系统超时返回 `degraded=true` + 轻量节点信息）；**T-S12** 构建原子切换（构建过程中请求始终用旧 `dict_rev`；构建失败旧版本继续服务）；
- **语义识别评测（M2-S2 起每次构建自动运行——#35 §13.2）**：评测集 150~200 条真实问法（工单/群聊/agent 日志），人工标注 span 与 entity_id，覆盖四类黑话、缩写、错别字、歧义词、负样本 ~20%；门槛：AC 层 precision ≥ 0.95、recall ≥ 0.80，AC + 模糊 recall@3 ≥ 0.92，歧义消解准确率 ≥ 0.85（只统计歧义样本），负样本误报率 ≤ 0.05；构建报告指标较上一版下降 >2 个百分点则不切 ready；**检索增益评测（M2-S3）**：docs 黄金集上对比开/关实体召回路的 recall@10 与 MRR——不回退才允许默认开启，否则保持可选参数；
- **性能抽测**：~10 万块 P95（按块 vs 按文档、同表 vs 分表）、rerank 并发、嵌入吞吐（M0b/M1 各一轮，驱动 schema v1.1 与 NFR-8 标定）。

## 10. 风险的工程对策（对应需求 §9 风险登记，v0.7：含 D23 语义层风险——#35 §14）

| 风险 | 工程对策 | 触发点 |
|---|---|---|
| 嵌入吞吐受网关限速（v0.7 模型外置后） | 阶段拆分（index_fts 先行）+ 分批 64 + useful-early；换模型重嵌入流程挂手动重索引（§5.3）；评估 MRL 截断（known-gaps G-8） | M2 实测吞吐曲线后决策 |
| **网关静默换底模 / 嵌入服务不可用**（v0.7，#41） | 启动指纹探针（哨兵文本余弦偏差超阈 → 拒绝同标签写入 + 告警）；`embed_model` 查询谓词隔离旧向量；查询侧不可达降级 BM25 单路、摄取停 `searchable_lexical`、rerank 不可达跳过（§5.2） | 探针偏差告警 / 网关故障时 |
| jieba 中英混排 | tokenizer 独立模块（可换 trigram/自定义词表）；M1 真实 query 标注集是判据 | M1 验收 |
| SQLite BLOB 扫描边界（2560 维为原 1024 假设的 2.5×） | StorageBackend 已隔离向量路（D24）；超标**切 PG 后端**（正式实现、配置级切换）而非再评估 | 一期 10 万块 P95 超标（NFR-2/8，真实维度） |
| **PG 后端差异**（FTS 评分函数 / 索引维度上限，D24） | ts_rank vs bm25：RRF 只看名次抹掉大部分差异、黄金集分后端校准；pgvector 索引 2000 维上限 → `halfvec(2560)` 或精确扫描起步、HNSW 启用需 ≥0.8 迭代扫描并重跑矩阵（known-gaps G-6） | PG spike（M0b）/ PG 全矩阵（M1） |
| dims_json json_each 性能 | ~~M0b 按文档计算实验~~ **✅ 已定（M0b-2 拍板①）：visible_docs+MATERIALIZED 胜出、dims_json 已删（v1.1/0002）**——sqlite 2.3~4.8× 优、pg MATERIALIZED 后反超、双方言 CTE 逐字相同（D24 判据达成）；维度物化列备选（schema v2）不再需要 | ~~M0b~~ 已闭环 / 十万级外推归 M1 实测 |
| P95 延迟超标 | NFR-8 预算表 + **降级链**（嵌入不可达 BM25 单路 / rerank 不可达跳过 / rerank 截断 256 / 候选 32→16） | M0b 压测（真实维度）、M1 基线 |
| 区分度失真 | 绝对阈值 + 分位下限；**规模比例 + 抽样重算（numpy 批量）**；近邻限在用版本；报告页近邻过 ACL | M1 抽查 + 周期重算 |
| 权限漂移（D16） | 季度对账 + 审计回放；grant_sync 适配器；生产前语义匹配维度切只读同步 | 季度对账；高敏文档从严 |
| 模型权重 license | docling 权重清单进 `config.py` 单一登记处，商用核查逐卡打勾；嵌入/重排模型在网关侧（D12 修订）——license 责任随 API 转移，本侧只钉标签 | 商用前（NFR-7） |
| **语义层职责膨胀**（D23） | §3 模块边界规则（**core/docs ↔ core/semantic 包级互斥 + import-linter CI 执法——v0.8.4**；交叉点仅 tag/untag 与 expand 两处显式接口）；新增实体/关系类型 = 迁移 + 评审；非目标明确（GraphRAG / 图数据库 / 全量元数据镜像） | 新增实体或关系类型提案时 |
| **语义同步故障波及服务**（源系统抖动清空图 / 写锁拖慢检索） | 删除比例保护（20% 中止零写入）+ missing 宽限期（7 天）；独立任务类型、分批 ≤1000 行、夜间错峰限速；语义失败不影响 docs 可用性（NFR-11）；必要时 `sem_*` 拆 ATTACH 独立库（repo 接口不变） | 源系统接口异常；M2-S 并行期压测 |
| **源系统无快照接口**（#37） | 接入前置条件 day-one 成文（§5.8）；推动源系统排期开发；确无法满足则该源不接入（灰度），不降低全量快照语义 | 对应源系统接入排期时 |
| **需维度隔离的源接口未暴露维度字段**（#37 评论） | **宁可延迟第二区域实体接入、不可无维度字段裸同步**（裸同步 = 整区域实体空值放行）；触发时先做「是否必须进语义层」前置评估（不进 = 延续灰度零成本）；填充率骤降告警 + 管理面 per-source 维度覆盖可见（§5.8） | 实体维度 ACL 演进缝触发时（#37） |
| **SQLite 写锁竞争**（同步 / 重标与 ingest 抢 WAL 写锁） | 同步与重标限速分批并错峰；重标优先级最低；§2 并发模型 | M2-S3 打标全量启用时 |
| **词典质量差**（短词 / 常用词误报，注入噪声） | CI 拦截短词与常用词；`context` 匹配模式；AC precision 门槛 ≥ 0.95；中间件只注入 confidence=1.0 非歧义命中；构建回归 >2pp 不切 ready | 每次构建报告 |
| **人工内容无人维护**（YAML 过期、别名覆盖率低） | 每条 YAML 必填 `owner`；构建报告列出无人维护与孤立条目；agent 日志高频未识别词定期回流成待补别名 | 季度运营回顾 |
| **源系统缺关系**（报表项取数关系未配置） | `extra_relations` 人工补；与同步重复时自动提示删除；推动源系统补齐 | M2-S2 报表项接入 |
| **实体召回 ACL 后门** | 实体召回路强制复用 §5.1 编译产物（同一编译器、同一产物，§5.10）；T-S8 越权矩阵必测 | M2-S3 验收 |
| **过渡期与正式版分叉**（本地 AC 与服务端行为不一致） | YAML schema 与规范化函数抽成小 package 两端引用；切换时评测集对比；开关灰度 | M2-S3 中间件切换 |
