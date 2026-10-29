# knowledge-lattice 测试用例

> 版本：**v1.8.3（2026-10-29 随 M2-2 交付回写——非决策变更、用例数不变**：①**TC-OPS-01 预期补搬运侧方言口径**（Committer R2 偏差①终态裁定——写侧同事务双方言成立；搬运侧 sqlite 为**两步幂等**〔WAL 无跨文件原子事务的物理约束——at-least-once + 月库 PK 去重 + 崩溃注入实证不丢不重〕、pg 为单事务）；②TC-OPS-02 预期补链序口径（哈希链按**插入序**——sqlite rowid / pg seq，同秒并列下排序序≠插入序的缺陷已修）；③TC-OPS-05 预期补 sqlite 月库备份范围口径（快照=主库+objects，**审计月库文件备份方式见 RUNBOOK §4**——恢复完整性验收以主库+objects 为准）。三处均随 task-knowledge-lattice-m2-2（PR 待开）入库）。v1.8.2（2026-10-29 随 M2-1 合入——非决策变更、用例数不变**：**§六 M2 行 m2-1 段完成态注记**（PR #2 mergeCommit 739bbf3；TC-TASK-01~04 ✅ / TC-E2E-03 杀进程演练半句 ✅ / TC-VER-08 ✅ tombstoned_at 基准；剩余条目标注段去向 m2-2/m2-3/M2-S1）。v1.8.1（2026-10-28 随 M2-1 R1 回写——非决策变更、用例数不变**：①**TC-VER-08 造数口径回写**：清理时点基准由「`created_at`=91 天前」改 **`tombstoned_at`（0004 迁移新增列）**——切换事务写 tombstoned_at、清理按其起算 90 天，与 design §4「旧版本保留 90 天」语义一致（Committer R1 P3-11/C 项裁定：实现正确、文档滞后）；②**TC-VER-05 补 fetch window 钳制口径**：`FETCH_WINDOW_MAX=10`，超限/负值静默钳制（m1-2 P3-8 承接、M2-1 R1 实现登记——design §6.1 仅给默认 window=2 无上限，此处补 API 口径防误判契约变更）；③**TC-ING-07 补中断模式条件**：worker 双模式（`LATTICE_WORKER_MODE`）下中断语义分叉——subprocess=杀 worker 子进程（TC-TASK-04/E2E-03 形态）、inline=进程内重启执行器（测试捷径口径）。三处均随 task-knowledge-lattice-m2-1 R2 批入库）。v1.8（2026-10-28 随 M1 收口——非决策变更、用例数不变**：**§六 M1 行完成态落笔**（M1-1~M1-5 五段 PR #50~#54 全部合入；逐组证据指针入表：矩阵 348/348〔B-1① 限定层注记〕/门禁 663+1/TC-PERF-03 裁定②基线口径/G-6 校准/TC-EVAL-06 ◐ 申报/TC-UI ◐ 待用户走查——M1 里程碑达成宣告待 TC-UI 走查完成）。v1.7（2026-10-27 随 M1-5 R2——非决策变更、用例数不变**：**T17 载体澄清**（用户 2026-10-27 裁定 A=②）：步骤原「调 `list_documents` 与文档详情」→ 文档详情（管理面端点）为 owner 元数据兜底唯一载体——`list_documents` 是 §6.1 ACL 视角工具（权限内可见，撤销授权后 owner 不可见自己文档，与 owner 兜底语义无关），与 TC-AZ-03「两个端点两个口径」一致；预期同步措辞。同批矩阵报告/勾验材料 T17 证据指针改详情端点测试（coder R2 执行）。v1.6.3（2026-10-25 随 M1-2 交付回写批——非决策变更、用例数不变（176+M1-2 新增段）**：①**B-1① 覆盖上传旧维度值校验口径登记**（用户 2026-10-25 拍板 FR-4 严格口径——覆盖上传校验文档当前全部维度值 ∈ 操作者 grants，与 PATCH 共用 `_require_values_in_grants` 防漂移；T7 前置句 L607 的「新旧取值均须校验」从此与实现一致、措辞维持；锁死面注记：文档含已停用取值或 retired 维度时 PATCH 与覆盖上传同锁，恢复路径=重新启用取值——M2 停用取值 dry_run 影响面须含"维度写锁"项）；②新增用例口径登记（M1-2 R2 实现）：`fetch` 对 pending 块与 tombstone 块同返 `replaced_by`（首上传 pending 期 `active_version=0`）；覆盖上传 pending 态含 failed 时 PATCH 一律 409（上传侧 failed 放行重传——从严差异）；切换事务补清 `active_error`（design v0.9.3 §5.3 SQL 缺项补全）；③R2 测试计数口径：门禁 436+1（R1 +68 / R2 +13 逐文件对账，见 task-knowledge-lattice-m1-2 检查点）。v1.6.2（2026-10-25 随 M1-1 交付回写批——非决策变更、用例数不变（176）**：TC-ACL-08「前置」句措辞修正——「mock ACL 编译器漏生成维度条件」改「注入召回面放宽」，消除与 v1.6.1 口径登记行（非 mock 编译器形态）的字面冲突；用例断言本体不变。v1.6.1（2026-10-25 随 M1-1 R1 勘误——非决策变更、用例数不变（176）**：①TC-EMB-05 预期补「none 为配置态、`notice.degraded==[]`、不发 `search.degraded` 审计」（随 design v0.9.2「或 none」措辞勘误——M1-1 实现口径经 Tester/Committer 独立复核双 ACCEPT、用户 2026-10-25 确认）；②TC-ACL-08 补口径登记行：`search.acl_intercept` 事件名 + payload 形态 + 独立重编译断言口径（非 mock 编译器——独立性来自 SQL 路径而非编译次数）。v1.6（2026-10-25 随 M0b-3 收官回写——三项拍板落库后的用例口径同步，design v0.9.1 联动）**：①TC-ACL-06 补 CTE 三路同构断言（visible_docs AS MATERIALIZED——M0b-2 计划病理修复）；②**TC-ACL-07 收敛为 visible_docs 唯一路径**（M0a 双写法等价验证使命完成，json_each 模板已删；断言改精确期望文档集 + CTE 快照口径竞态回归）；③TC-EMB-02/07 谓词迁 `cv.embed_model` JOIN（拍板②分表）；④**TC-EMB-06 重写为方案二蓝绿**（拍板③——功能零降级，原方案一置空重建作废）；⑤TC-ING-06 写路径迁 chunk_vectors + 索引查询面口径；⑥TC-SCAF-03 v1.1 基线（user_version=2、schema_migrations=[1,2]）+ 锁外建表竞态双捕获形态（23505 主/42P07 间或，引用 migrate docstring 与 RUNBOOK）；⑦TC-SCAF-02 补 standard_conforming_strings=on 连接纪律 + public_audit_guard **DSN 必须指向专用测试库**约定（§6.1 public 清理破坏性）；⑧**存量向量搬运计数口径 = 合法成对行（embedding 非空且 embed_model 非空），孤立行显式丢弃并断言**（test_v11_schema）；⑨TC-E2E-04/TC-AZ 补 dims 来源改 document_dimensions 聚合（dims_json 投影刷新条款失效——附录 A-3 注记）；⑩**TC-FTS-01 口径勘误落笔（M0a-3 移交）+ M0a-1 两处 DDL 执行层修正勘误登记**（trg_docdims_consistency 建表顺序后移 / FTS 触发器列名 rowid——历史注记见 0001，语义等价）；⑪§六 M0b 行完成态。requirements/design 正文「M0b 压测/三档」字样勘误已随 design v0.9.1/requirements §8 落笔。用例数不变（176）。v1.5.2（2026-10-24 随 M0b-2 开工口径修订——2026-10-24 用户拍板「不压测、不搞大数据量」：①TC-PERF-01 档位 1/5/10 万三档 → **1/5 万两档**（10 万档取消）；②**TC-PERF-03 SLO 压测 M0b 标定取消**，NFR-8 正式标定顺延 M1 基线轮（与 TC-PERF-04 同轮）——§六 M0b 行同步移除该用例并注记 PG spike 已随 M0b-1 交付（PR #47）；③requirements/design 正文的「M0b 压测」字样勘误登记归 M0b-3 勘误批次（正文冻结纪律）。用例数不变（176）。v1.5.1（2026-10-24 随 M0b-1 PG spike 合入回写——**TC-SCAF-02~05 后端行 sqlite-only → both**（PG 等价断言已落地，#42 必修4 兑现）：02＝连接池参数 + server_version≥16 + pgvector 距离函数可用 + session TimeZone 钉 UTC；03＝`schema_migrations` 表 + 原生约束校验（违例整事务回滚）+ advisory lock 并发序列化 + 版本只前进（MAX 水位 fail-fast）；04＝plpgsql 触发器全集（消息与 SQLite 逐字同源）+ ai/ad/au 由 tsvector 五列 GENERATED（regconfig 双参）天然等价替代；05＝同款级联触发器双臂断言。**执行层落点注记**：PG 断言按方言形态落 `tests/test_pg_scaff.py` 等价文件（非原 TC-SCAF-02/03 用例文件内），SQLite 臂保留原位、双臂经 conftest `backend` fixture 参数化。用例数不变（176）；M0a 期间「仅 SQLite 验收、PG 臂为 M0b 激活项」口径自此关闭）。v1.5（2026-10-22 随正文 v0.9 新增 **TC-UI 界面国际化组**（FR-8——对话决策轻量决策变更：TC-UI-01 语言切换与持久化 / 02 双语完整性 / 03 业务数据与行为不随语言变化 / 04 服务端不感知语言，共 4 条**手动走查用例**——薄壳无测试框架不进 CI，M0a 机制 + M1 起页面）；依据区版本引用同步 v0.9（**顺带清 v0.8.3~v0.8.5 欠账**：§3 结构澄清 / core 对称分包 / 运行日志落点均无用例影响，未另出版本段）；复审 P2 顺手项：编号约定表 TC-UI 行移至 TC-OPS 后与正文组顺序对齐、口径段补「手动走查类」类目、TC-UI-02 排除项措辞改「章节引用」；用例 172→**176** 条。v1.4.2（2026-10-22 依据区版本引用同步 v0.8.2 与 known-gaps 范围 G-1~G-11——正文运行时口径登记（目标机系统 Python 3.9.9 → uv 托管 CPython 3.12，G-11），**无用例变更**、用例数不变。v1.4.1（2026-10-22 依据区版本引用同步 v0.8.1——正文待决-6 关闭（公司 PG 16 + pgvector 0.8.x，G-6 收窄①闭环），**无用例变更**、用例数不变。v1.4（2026-10-22 吸收 [issue #42](https://github.com/yq3/lab/issues/42) 必修 2/3/4 与 P1/P2 用例项——①必修2：TC-EMB-06 重造（reembed 任务类型 + **竞态子句**——孤儿向量断言）；②必修3：T7 操作者改 `admin_full`（u_owner 授权不符会先 403）、T11 重造（新增双组织用户 `u_multi` + 凭证绑定专属错误码）；③必修4：TC-SCAF-01~05 逐条标 `both / sqlite-only`、TC-EMB-02 拆分（M0a＝Plan 层谓词单测 + 新增 TC-EMB-07 M1 检索行为）、TC-EMB-03 补全（首部署建档 / 两档阈值 0.99·0.95 / 周期探测 / 拒后状态）、共享 fake provider fixture 入口径段；④P1：新增 **TC-ACL-08**（rerank 前后 ACL 双断言）、TC-ACL-02/06 与 TC-FTS-02 主断言上移 AclPlan 层（「无 `IN ()`」升为 Plan 不变式）、TC-CRED-02/03 凭证语义统一（「用掉」＝摄取成功入队）、TC-YAML-04 补样本值 ≤3（DataAgent 借鉴②）；⑤P2：fixture 补 `u_multi` / `u_gl` 角色 / channel 值 A、时间戳造数格式钉死 UTC `YYYY-MM-DD HH:MM:SS`；用例 170→**172** 条。v1.3.2（2026-10-22 随正文 v0.7.2 / [#42](https://github.com/yq3/lab/issues/42) 三项拍板——①TC-EMB-03 断言改：探针拒绝档同步关查询侧向量路（降级 BM25 单路 + notice——跨底模距离无意义，拍板2）；②口径段 PG skip 政策：本地可 skip、CI 必跑 PG job 且 skip 视为失败（拍板1：PG 正式备选）；③语义层用例（T-S6/T-S8/TC-SEM-09）自 M2-S 起双后端参数化（拍板3：expand_relations / recall_by_entities 收口 backend）；用例数不变。v1.3.1（2026-10-22 随正文 v0.7.1 / [#42](https://github.com/yq3/lab/issues/42) 必修1 回写——①TC-EMB-05 前置口径：rerank 端点已确认（网关提供 Cohere 风格 `/rerank`，待决-5 关闭），`none` 从「缺省兜底」改述为「显式降级路径」；②依据区版本引用同步 v0.7.1、known-gaps 范围补 G-9/G-10；用例数不变。v1.3（2026-10-21 随正文 v0.7 / [#41](https://github.com/yq3/lab/issues/41) 决策变更增补——①新增 **TC-EMB 组**（嵌入服务与模型治理：维度校验 / `embed_model` 查询谓词 / 指纹探针 / 查询侧降级链 / Reranker none / 换模型重嵌入迁移，D12）；②TC-ING-06 钉版本改 `model:dim` 标签、TC-RET-04 rerank 改 API 口径；③口径补**测试按存储后端参数化**（D24——`backend ∈ {sqlite, pg}`，PG 无 DSN 自动 skip，越权矩阵与编译器单测双后端各跑）；④附录 A 补 A-17（PG 后端 FTS 评分差异→known-gaps G-6）；用例 164→170 条。v1.2.1（2026-10-20 复审二轮——①T6 上传者 `u_full`→`admin_full`：u_full 是普通成员，按 FR-4 操作矩阵（覆盖上传=owner/org_admin）会先 403，用例不可执行；admin_full 兼具操作权限与 region=[CN,OS] 授权，双前提成立；②TC-AZ-01 的 d_cn_own 置空 tax_type——防实现按「结果集全维度」校验时拒绝原因来自 tax_type、掩盖 region 取值越权；③design 前置阅读版本引用同步 v0.6.1。v1.2（2026-10-20 吸收 [issue #40](https://github.com/yq3/lab/issues/40) 复审——P0-R1：T6 重造（查看者改 `u_cn_vat`、v2 明确上传者——复审二轮修正为 `admin_full`）；P1-R1~R3：TC-AZ-04 临时授权补双维度、TC-AZ-01 改用 u_cn 自有文档并区分操作权限/取值越权（fixture 补 `admin_full`）、TC-ACL-02 声明本地单维 fixture 并统一命名；P2×7 全量回写（`d_empty_region` 改名×3、TC-BUILD-02 标题、fanout_limit 超限并入 A-11、conflicts 字段标注测试约定、T-S9 月库侧异步断言、附录 A 补 #39 链接、T7 补操作者）。v1.1：2026-10-20 吸收 #38 评审——P0×2 / P1×11 / P2 全量；新增 TC-TASK-06 / TC-SEM-10 / TC-SYNC-09；附录 A 扩至 A-16。v1.0：2026-10-20 初版，M0a 开工前）
> 依据：[design.md](./design.md) v0.9.3——**§9 测试策略是冻结用例清单，本文是其展开层：T1~T23 / T-S1~T-S12 编号沿用、不另起**；§8 里程碑验收、§4 DDL 与触发器、§5 关键设计、§6 接口契约为断言细节来源。[requirements.md](./requirements.md) v0.9.3（FR/NFR/D 验收口径；FR-8 界面国际化→TC-UI 组）；[known-gaps.md](./known-gaps.md)（G-1~G-11——涉及其中的用例已标注）；评审依据 [issue #38](https://github.com/yq3/lab/issues/38)（P0×2 / P1×11 / P2 若干，行号以 b75e91a 为准）与 [#41](https://github.com/yq3/lab/issues/41)（v1.3 增补依据）与 [#42](https://github.com/yq3/lab/issues/42)（v1.3.1~v1.4 增补与拍板依据）。沿 lab 仓库 pulse-pet 先例（docs/v1/TEST-CASES.md + 评审回写）。
> 用途：M0a~M3 与 M2-S1~S3 各里程碑验收依据，里程碑收尾按 §六对照表逐条勾验。
> 口径：**单测类**用例「预期」即 pytest 断言（CI 跑）；**矩阵/接口类**经 MCP/REST 真实调用断言（M1 起矩阵进 CI 常跑）；**契约/观察项**为记录级（验收不判失败）；**手动走查类**为浏览器人工执行、不进 CI（TC-UI——v1.5 新增类目）；**性能类**给阈值与测量口径。时间依赖（过期/宽限期/租约）一律**造数**——直接写过去时间戳，不推进系统时钟。**存储后端参数化（v1.3，D24；v1.3.2 修订——#42 拍板1：PG 正式备选）**：涉及持久化与召回 SQL 的用例按 `backend ∈ {sqlite, pg}` 参数化双跑（越权矩阵与编译器单测必跑双后端；本地无 DSN 可 skip、不阻塞纯 SQLite 环境，**CI 设必跑 PG job（docker postgres+pgvector）——CI 内 skip 视为失败**；语义层展开/召回类用例（T-S6/T-S8/TC-SEM-09）自 M2-S 起同样双后端参数化——#42 拍板3）；两后端 FTS 评分函数差异为已登记口径（A-17 / G-6），排序类断言按「名次集等价」而非逐分相等。**fake provider fixture（v1.4，#42 必修4——TC-EMB 组 / TC-RET 降级 / TC-ACL-08 共享）**：Embedder/Reranker 假实现统一 fixture——①确定性向量（按文本 hash 种子，同文本同向量）；②可注入延迟与失败（超时 / 不可达）；③换底模模式（`drift`：哨兵文本返回偏移向量——探针用例专用）；④Reranker `none` 实现。
> 演进纪律：本文为活文档（同 known-gaps，不受设计冻结纪律约束），随实现回写口径；**与 requirements/design 正文冲突时以正文为准并开 issue**。编写中发现的规格含糊点登记于附录 A（展开即压测——pulse-pet 用例评审先例）。

## 编号约定

| 前缀 | 模块 | 对应里程碑 |
|---|---|---|
| TC-SCAF | 脚手架 / 连接工厂 / 迁移 / DDL 触发器 | M0a |
| TC-ACL | ACL 编译器单测（结构层——语义场景见 T 编号） | M0a |
| TC-FTS | FTS5 转义 / 五列加权 / 同步触发器 | M0a / M1 |
| TC-ING | 解析 / 切分 / 编码 / 质量门 / 嵌入 | M0a / M1 |
| TC-EMB | 嵌入服务与模型治理（维度校验 / `embed_model` 谓词 / 指纹探针 / 降级链 / none / 重嵌入迁移——D12，v1.3） | M0a / M1 / M2 |
| TC-RET | 检索配方（RRF / 归一 / rerank / 降级 / 增强） | M1 |
| TC-VER | 版本在用制（D20 时机 / 切换事务 / fetch / 回写防护） | M1（90 天清理 M2） |
| TC-CRED | 上传凭证流（三步式 / file_ref 防线） | M1 |
| TC-QUAL | 区分度反馈环 | M1 |
| TC-AUTH | 鉴权 / 组织上下文 / 身份降级 | M0a / M1 / M2 |
| TC-E2E | 摄取→检索端到端集成 | M0a / M0b / M1 |
| TC-TASK | 任务与 worker 机制 | M2 |
| TC-OPS | 生产化（审计 / 备份 / 清理 / 管理面 / CSV） | M2 |
| TC-UI | 界面国际化（前端薄壳中/英双语——FR-8，v1.5 新增；手动走查、不进 CI） | M0a（机制）/ M1 起页面 |
| T1~T23 / T-CSV / TC-AZ | **越权矩阵**（§9 冻结编号 + 验收引用的补充行） | M0a / M1 / M2 |
| T-S1~T-S12 | **语义层功能与不变式**（§9 冻结编号） | M2-S1~S3 |
| TC-SYNC | 语义同步流程（适配器 / 保护 / 审计） | M2-S1 / S2 |
| TC-YAML | Git YAML 覆盖层与 CI 校验 | M2-S2（TC-YAML-05 过渡期一致性为 M2-S3） |
| TC-BUILD | 构建产物与原子切换 | M2-S2 |
| TC-SEM | 语义工具契约（annotate / search_entities / get_entity / describe_table / L0） | M2-S1~S3 |
| TC-TAG | 打标 / 重标 / untag / 实体召回路 | M2-S3 |
| TC-PERF | 性能抽测（M0b 四实验 / SLO / 语义 P99） | M0b / M1 / M2-S |
| TC-EVAL | 评测与门禁（黄金集 / judge / deepeval） | M1 / M3 |
| TC-SEV | 语义识别评测集与检索增益 | M2-S2 / S3 |

里程碑标签写法：`【单测｜M0a】`＝类型｜首次全绿里程碑；矩阵类用例在更早里程碑以单测形态先行（如 T1~T5 于 M0a 编译器单测先行、M1 矩阵复跑——design §8 M0a.5）。

---

## 一、单元用例（docs 侧）

### TC-SCAF 脚手架与连接工厂

#### TC-SCAF-01 foreign_keys 每连接生效 + 孤儿行拒绝【单测｜M0a】

- **前置**：全新 `lattice.db`，经 store 连接工厂（SQLite 后端——D24）取连接，schema v1 已落。
- **步骤**：① 查询 `PRAGMA foreign_keys`；② 向 `user_dimension_grants` 插入引用不存在 user 的孤儿行；③ 向 `document_dimensions` 插入引用不存在 doc 的孤儿行。
- **预期**：① 返回 1；②③ 抛 `sqlite3.IntegrityError`（FOREIGN KEY 约束）——M0a 验收原句「插孤儿行断言 IntegrityError」。工厂对 pragma 失败显式 `raise RuntimeError`（非 assert——`python -O` 剥离，design §3）。
- **后端**：both——PG 侧外键违例同断言（异常类型按后端适配：psycopg 外键错误码，断言语义不变——v1.4 标注，#42 必修4）。

#### TC-SCAF-02 连接 PRAGMA 全集【单测｜M0a】（v1.6 补 PG 连接纪律与 DSN 约定）

- **前置**：连接工厂取连接。
- **步骤**：依次查询 `journal_mode` / `busy_timeout` / `synchronous` / `foreign_keys`。
- **预期**：`wal` / `5000` / `NORMAL`（1）/ `1`——与 design §3 连接工厂逐项一致；sqlite-vec 扩展加载成功（`SELECT vec_distance_cosine(...)` 可调用）。**PG 工厂纪律（v1.6，M0b-1/3 交付）**：session TimeZone=UTC + `standard_conforming_strings=on`（Literal 转义前提）+ server_version≥16 + pgvector `<=>` 可用（断言落 `tests/test_pg_scaff.py`）。**DSN 约定**：`LATTICE_PG_DSN` 必须指向**专用测试库**（本仓 lattice 容器库）——public_audit_guard fixture 对 public schema 做 audit 对象清理（破坏性动作）。
- **后端**：both（v1.5.1 回写——PG 等价已随 M0b spike 落地：连接池参数 + server_version≥16 + pgvector 距离函数可用性 + session TimeZone 钉 UTC；断言落点 `tests/test_pg_scaff.py`——PG 断言按方言形态独立成文件，SQLite 臂仍在原 TC-SCAF-02 用例）。

#### TC-SCAF-03 迁移框架：改表流程与 foreign_key_check【单测｜M0a，M0b v1.1 迁移复跑】（v1.6 补 v1.1 基线与竞态口径）

- **前置**：迁移框架就绪；构造一份「建新表→拷数据→删旧表」的测试迁移。
- **步骤**：① 正常跑迁移后执行 `PRAGMA foreign_key_check`；② setup：经迁移窗口内临时关闭外键的写入路径注入一行违反外键的数据，再跑同迁移。
- **预期**：① 迁移期间临时关闭外键、结束恢复，`foreign_key_check` 返回空；② 检出违例即回滚，库内状态与迁移前一致（#33 P1-1）；③ `user_version` 只前进、重复运行迁移幂等（无重放副作用）。**v1.1 基线（M0b-3）**：全量迁移后 `user_version=2` / `schema_migrations=[1,2]`；0002 存量搬运计数=**合法成对行**（embedding 非空且 embed_model 非空），孤立行显式丢弃并断言（test_v11_schema）。**PG 锁外建表竞态口径（M0b-3）**：真实形态 = `UniqueViolation`（pg_type_typname_nsp_index，23505——主形态）/ `DuplicateTable`（42P07——间或），处置 = 双捕获 + `to_regclass` 复核（在场则干净继续、不在则原异常照抛 fail-closed）——引用 store/postgres/migrate.py docstring 与 RUNBOOK §3；竞态回归 test_pg_scaff 双异常类参数化（红灯实证 23505 穿透单捕获）。
- **后端**：both（v1.5.1 回写——PG 等价已落地：`schema_migrations` 表 + 原生约束校验（违例整事务回滚）+ advisory lock 并发序列化 + 版本只前进（MAX 水位 fail-fast）；断言落点 `tests/test_pg_scaff.py`）。

#### TC-SCAF-04 DDL 防护触发器全集【单测｜M0a】

- **前置**：schema v1 落库完成。
- **步骤**：① 断言 design §4 文档侧全部触发器存在（`trg_dimval_immutable`、`trg_membership_delete_cleanup`、`trg_membership_no_extend`、`trg_documents_org_immutable`、`trg_datasets_org_immutable`、`trg_dimensions_org_immutable`、`trg_documents_ds_org_check`、`trg_documents_ds_immutable`、`trg_docdims_consistency`、`chunks_ai/ad/au`；`sem_*` 触发器除外——M2-S1 才落库，见 TC-SYNC-09；**audit append-only 触发器属月库**、由连接工厂滚动创建（design §4 注）——断言见 TC-OPS-02，不在主库 schema v1 内）；② 逐个行为断言：UPDATE `dimension_values.value` → ABORT；UPDATE `documents/datasets/dimensions.org_id` → ABORT；插入 dataset 与 documents org 不符 → ABORT；跨组织搬库（UPDATE dataset_id 至他组织库）→ ABORT；插入 value 与 dimension 不匹配或维度 org ≠ 文档 org 的 `document_dimensions` 行 → ABORT。
- **预期**：全部触发器存在且各自 ABORT；`uq_chunks_docver(doc_id, version, seq)` 唯一索引：同文档同版本 seq 重复被拒、不同版本同 seq 合法（含 version——#34 4.4）。
- **后端**：both（v1.5.1 回写——PG plpgsql 触发器已落地、消息与 SQLite 逐字同源；ai/ad/au 三触发器由 tsvector 五列 GENERATED（regconfig 双参）天然等价替代——INSERT 自动计算 / 依赖列 UPDATE 重算（版本切换清列→空 tsvector→零命中）/ DELETE 行级消失；断言落点 `test_scaf_04_triggers.py` 双臂参数化 + `tests/test_pg_scaff.py` GENERATED 同步断言）。

#### TC-SCAF-05 成员关系删除级联清授权【单测｜M0a】

- **前置**：u1 属 org:tax（region=[CN]）与 org:gl（gl 维度授权若干）。
- **步骤**：DELETE u1 在 org:tax 的 membership 行。
- **预期**：org:tax 维度下 u1 的授权全部删除（含 `source='sync:…'`——预期行为，#33 P0-1⑥）；org:gl 的授权不受影响（触发器按 `dimensions.org_id` 收敛，design §4）。
- **后端**：both（v1.5.1 回写——PG 同款级联触发器已落地，断言双臂参数化）。

### TC-ACL ACL 编译器（结构层）

#### TC-ACL-01 AST builder 括号化与渲染等价【单测｜M0a】

- **前置**：编译器输入 u_full（region=[CN,OS]、tax_type=[VAT]）。
- **步骤**：编译产出 WHERE 片段；与 design §5.1 示意 SQL 逐段对比。
- **预期**：多维度条件以显式括号 AND 连接（无优先级歧义）；产物由 AST 渲染（结构断言：节点树含 And/Or/NotExists/InValue 节点），**无字符串拼接**；渲染 SQL 可被 sqlite 直接 prepare 且执行结果与手写等价 SQL 相同。

#### TC-ACL-02 统一空值模板（有值交集 / 无值放行）【单测｜M0a】

- **前置**（本地 fixture，**不复用标准矩阵**——#40 P1-R3：只启用 region 单个维度，消除多维度混淆）：文档 `d_cn_r`（region=[CN]）与 `d_empty_r`（region 无值）；用户 `u_cn_r`（region=[CN]）、`u_os_r`（region=[OS]）。
- **步骤**：对 u_cn_r 与 u_os_r 分别编译并执行召回。
- **预期**：**主断言在 AclPlan 结构层**（v1.4 上移，#42 P1-10）：每维 Plan 含 `(NotExists | Or[Exists, InValue])` 组合、空值模板与授权常量落在结构节点上（**「无 `IN ()`」为 Plan 层不变式**——空授权集只产 NotExists 单条件节点）；行为断言：u_cn_r 可见 d_cn_r 与 d_empty_r；u_os_r 可见 d_empty_r 而**不见 d_cn_r**——维度间 AND、维度内 OR（D5）；SQLite 渲染 SQL 文本快照仅作渲染器附带断言（sqlite-only，不锁 PG 实现）。

#### TC-ACL-03 空授权集 → NOT EXISTS 单条件【单测｜M0a】

- **前置**：用户在某 active 维度（tax_type）无任何有效授权。
- **步骤**：编译产物文本断言 + 行为断言（对 d_cit(tax_type=[CIT]) 与 d_empty_region 检索）。
- **预期**：**tax_type 维度对应的产物片段**为 `NOT EXISTS(…'$.tax_type')` 单条件（无 OR EXISTS 分支），其余 active 维度（region）仍按统一模板生成；全局**不出现 `IN ()`**（#34 必修 3 / T22——#38 P0-2 修订：断言落在维度片段级，非整份产物）；该用户只见 tax_type 为空的文档（region 约束照常叠加），非整体不可见。

#### TC-ACL-04 生命周期与过滤解耦【单测｜M0a】

- **步骤**：① 将 region 的 `required` 1→0、`enabled` 1→0 分别 UPDATE 后重新编译；② 将某维度 `status` 置 `retired` 后重新编译；③ 新建维度 channel（无任何文档回填）后重新编译。
- **预期**：① 产物与改动前**逐字相同**（required/enabled 不影响过滤——T4/T20）；② retired 维度不生成任何条件（唯一放宽路径）；③ channel 编译出空值放行条件，存量文档零消失（T20①——回填后才逐篇收紧）。

#### TC-ACL-05 第 0 步成员关系校验【单测｜M0a】

- **步骤**：对无 membership、membership `expires_at`=昨天、membership 有效三种用户触发检索。
- **预期**：前两者在编译入口即拒绝（无有效成员关系——403 语义），不产出 WHERE；第三者正常。系统管理员豁免仅限管理端点（检索路径同样拒绝——D22）。

#### TC-ACL-06 外层常量约束与 FTS 路同构【单测｜M0a，v1.6 补 CTE 同构断言（M0b-3）】

- **步骤**：断言产物外层恒含 `c.version = d.active_version AND c.tombstone = 0 AND d.org_id = :org`；FTS 路产物为 `chunks_fts MATCH` + 同一 ACL 片段 + 版本条件在 JOIN 上；**v1.6 增补（M0b-3）**：基础/FTS/向量三路共用同一 `visible_docs AS MATERIALIZED` CTE（PG 渲染显式 MATERIALIZED——M0b-2 计划病理修复），断言 `vec_cte == base_cte`、FTS SQL 内嵌同 CTE 前缀（双方言）。
- **预期**：三路共用同一授权展开与同一 Plan（#34 必修 1）；组织限定是一切检索 SQL 第一条件（design §4 设计说明）；**主断言在 Plan 层**（常量约束为固定节点、FTS/向量/实体三路共用同一 Plan——v1.4 上移，#42 P1-10）+ **v1.6 CTE 文本级同构断言**（双方言归一化参数记号后逐字相同——D24 可移植性实证）。

#### TC-ACL-07 ACL 渲染路径（v1.6 收敛为 visible_docs 唯一路径）【单测｜M0a→M0b 选型收敛】

- **步骤**：~~对同一用户/文档矩阵，分别用「按块 json_each 模板」与「按文档 visible_docs CTE（基于 document_dimensions）」执行召回，断言可见集相等~~（M0a 双写法等价验证已完成、json_each 模板已随 M0b-2 拍板①删除）；**v1.6 起断言**：visible_docs CTE（基于 document_dimensions）对标准矩阵产出**精确期望文档集**（T5/T6/T22 场景——按用户可见集断言），并锁 CTE 快照口径（不读 status 列；维度停用/退役经下次编译生效——竞态回归双用例双后端锁定）。
- **预期**：检索结果与「文档在维度 k 无任何行，或有一行 value ∈ 授权集」语义逐字一致（#34 必修 3 语义保持，等价性由 M0a 双写法阶段背书 + M0b-2 实验 12 组复核背书）；恶意 key / dot-key 场景按引号字面量字面匹配（无 JSON path 语义）。

#### TC-ACL-08 rerank 前后 ACL 双断言（防御纵深）【单测｜M1】

- **前置**：v1.4 新增（#42 P1-5——FR-4 红线「rerank 前断言、返回前再断言」此前无用例；rerank 为外部 API 后候选列表即外发，双断言更重要）；**注入召回面放宽**（v1.6.2 措辞修正——原「mock ACL 编译器漏生成一个维度条件」与下方口径登记行的非 mock 编译器形态字面冲突；实现等价注入形态 = 召回结果混入越权块，断言层独立拦截，M1-1 R1 Tester/Committer 双 ACCEPT）。
- **步骤**：① 断言 Reranker provider（fake——见口径段共享 fixture）收到的候选全部 ⊆ 该用户可见块集合；② 构造 rerank 返回序列混入越权块，断言返回前二次断言将其拦下。
- **预期**：① 越权块在 rerank 前（外发前）被兜底断言剔除并记拦截审计事件；② 最终 top-k 无越权块——两次断言各自独立生效（单独移除任一断言时用例失败——防御纵深可测）；正常路径双断言零剔除通过。
- **口径登记（v1.6.1，随 M1-1 实现）**：拦截审计事件名 = `search.acl_intercept`（实现自定、设计未枚举名），payload 含 phase ∈ {pre_rerank, pre_return} 与被剔除 rids[]；断言数据源 = 独立重编译可见集 + 基础路 SQL（与召回 SQL 不同执行路径——非 mock 编译器形态，M1-1 R1 Tester/Committer 双 ACCEPT；独立性来自 SQL 路径而非编译次数）。

### TC-FTS FTS5

#### TC-FTS-01 MATCH 转义【单测｜M0a】（v1.6 口径勘误——M0a-3 移交，M0b-3 落笔）

- **步骤**：构造 query 含 `"`、`*`、`NEAR`、`AND`、`-`、空格、`（` 全角字符；经 jieba 切分后拼查询串执行 MATCH。
- **预期**：每个 token 以双引号包裹、内部 `"` 转义为 `""`，token 间以 `OR` 拼接；无 malformed 异常、操作符不被激活（`AND`/`NEAR` 作字面量可命中含该字面量的块——design §4 查询侧口径）。**勘误（v1.6——M0a-3 实测与 FTS5 unicode61 行为不自洽，committer 裁定等价处置）**：**纯标点 token（如 `*`/`-`）不进入 MATCH 表达式**（FTS5 unicode61 不索引纯标点——原子句「`*` 作字面量可命中」不可满足，实现滤除为等价且更稳处置）。

#### TC-FTS-02 五列加权【单测｜M0a】

- **前置**：五个 chunk 分别只在 tags / keywords / title_seg / content_seg / llm_keywords 含目标词。
- **步骤**：`bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)` 排序。
- **预期**：排序 tags(8) > keywords(5) > title_seg(3) > content_seg(1) > llm_keywords(0.5)。
- **后端**：sqlite-only（`bm25()` 为 SQLite FTS5 评分）；PG 等价＝加权 `ts_rank` 求和，排序断言按**名次集等价**（A-17——两后端评分方向差异在 backend 内吸收为名次，design §5.2 v0.8），随 M1 PG 全矩阵补（v1.4）。

#### TC-FTS-03 同步触发器与切换清列【单测｜M0a】

- **步骤**：① INSERT/DELETE chunk 后核对 FTS 行；② UPDATE 五列之一后核对；③ 模拟版本切换的 UPDATE（五列清空、tombstone=1）后以旧内容 MATCH。
- **预期**：①② FTS 与 chunks 一致（au 触发器先 'delete' 后插入）；③ MATCH 旧内容零命中——FTS 层无 tombstone 内容（机制层；矩阵层见 T9）。

#### TC-FTS-04 keywords 列人工词纯净性【单测｜M1】

- **步骤**：人工补标走 `PATCH /api/quality-flags/{id}` 写入 `keywords`；jieba 分词只产 `content_seg/title_seg`。
- **预期**：`keywords` 仅含人工提交词，jieba 高频词不混入（#32 P1-3——重复会被 ×5 加权放大）；`llm_keywords` 仅由质量环 LLM 写入（来源分层可断言：内容不交叉）。

### TC-ING 摄取链

#### TC-ING-01 docling 解析→统一块结构【单测｜M0a】

- **步骤**：解析 docx（含多级标题+表格）、pptx、xlsx、HTML、原生 PDF 样例。
- **预期**：输出统一块结构（content / heading_path / page_no / bbox_json / sheet_name）；标题层级与页码保真；表格边界保留供切分。

#### TC-ING-02 结构感知切分【单测｜M0a】

- **步骤**：对带层级的文档切分；统计块 token 数。
- **预期**：递归 token 256–512 打底、结构边界优先；`heading_path` 记录层级路径；表格整块不拆散（§9 切分边界口径）。

#### TC-ING-03 Excel 行块切分【单测｜M0a】

- **步骤**：多 sheet Excel 切分。
- **预期**：按 sheet/行块切分；**每个行块 chunk 重复表头**（保留列语义）；`sheet_name` 记录（FR-1）。

#### TC-ING-04 编码与老格式策略【单测｜M1】

- **步骤**：① 上传 GBK 编码 TXT；② 上传 `.doc/.xls/.ppt`。
- **预期**：① 编码探测并转 UTF-8 后正常摄取；② 明确拒收并提示转存新格式（不引入 LibreOffice——零中间件纪律）。

#### TC-ING-05 mojibake 质量门三档【单测｜M1】

- **步骤**：构造正常字符比 >0.55 / 0.40~0.55 / <0.40 三档解析产物。
- **预期**：分别正常通过 / 告警（重试）/ 失败（OneRAG 借鉴项，design §5.4）。

#### TC-ING-06 嵌入分批与钉标签【单测｜M1】（v1.6 随 v1.1 更新写路径）

- **步骤**：摄取 >64 块文档（Embedder 以 OpenAI 兼容端点 mock——D12 修订，进程内推理取消）；断言逐批写入 `chunk_vectors(rid, embed_model, embedding)`（v1.1 分表——INSERT 新表，PK 含 embed_model 支撑蓝绿并存）；待嵌清点谓词 = `chunks` 无 (rid, :label) cv 行（原 embedding IS NULL 语义的 v1.1 等价——**索引面注记（v1.6 与 0002 注释同步）**：idx_chunks_vec_pending(doc_id, embed_model) WHERE tombstone=0 服务 mark_embedding_batch 的 doc_id 前缀；pending_embeddings 的 embed_model 等值+NOT EXISTS **不走本索引**，量级后再评估专用索引）。
- **预期**：分批 64；每向量行 `embed_model = '<model>:<dim>'`（如 `qwen3-embedding-4b:2560`——标签兼作向量路 JOIN 谓词，见 TC-EMB-02）；批次间任务可断点续跑。

#### TC-ING-07 阶段幂等续跑【单测｜M0a】

- **步骤**：在 index_fts 完成后中断任务执行（M0a/M1 阶段=重启进程内执行器；M2 子进程化后=杀 worker，TC-TASK-04 复跑；**v1.8.1 模式条件**：worker 双模式下 `subprocess`=杀 worker 子进程、`inline`=进程内重启——中断缝语义随模式分叉，断言形态按所配模式取），重跑同任务。
- **预期**：从 embed 阶段续跑，index_fts 不重复写块（uq_chunks_docver + 阶段状态判定）；文档状态沿 `parsing→chunked→searchable_lexical→searchable_full` 前进。

### TC-EMB 嵌入服务与模型治理（v1.3 新增，D12/D24——#41）

#### TC-EMB-01 嵌入维度校验【单测｜M0a】（v1.6 载荷口径迁 chunk_vectors）

- **前置**：config 钉 `dim=2560`；Embedder mock 返回 1024 维向量。
- **步骤**：摄取触发 embed 阶段。
- **预期**：写入前校验 `len != dim` → **raise，不写库**（design §5.3）；库内 `chunk_vectors` 无残缺向量行；任务 failed 可重试（无半写状态）。

#### TC-EMB-02 embed_model 查询谓词（编译/Plan 层）【单测｜M0a】（v1.6 随 v1.1 迁 cv JOIN）

- **前置**：造数——同组织可命中域两块：A 行向量 `embed_model='qwen3-embedding-4b:2560'`（= 当前 config 标签，写 chunk_vectors），B 行向量写旧标签（如 `bge-m3:1024`，向量合法）。
- **步骤**：断言向量路编译产物含 `embed_model = :current_model` 谓词——**断言落在 AclPlan 结构层**（谓词为固定节点，v1.4 上移/#42 P1-10）；**v1.6 渲染层**：谓词列引用迁 `cv.embed_model`（JOIN chunk_vectors ON rid + 标签——M0b-2 拍板②分表），Plan 节点形态不变、仅列引用 c→cv。
- **预期**：Plan 含谓词节点且参数绑定当前 config 标签；**检索行为断言（B 只走 BM25、不进向量路 top-k）拆至 TC-EMB-07 随 M1**（v1.4 拆分——M0a 只有 BM25 单路、行为不可测，#42 必修4）。

#### TC-EMB-03 指纹探针（建档 / 两档拒绝 / 周期探测）【单测｜M0a】

- **前置**：fake Embedder（共享 fixture，见口径段——`drift` 模式使哨兵文本返回偏移向量）；config 四件套生效；**首部署分支**：`embedding_fingerprints` 基线清空。
- **步骤**：① 首部署启动探针（无基线）；② 建档后以 drift 模式重启（与存档最小余弦 < 0.95——G-8 拒绝档）；③ drift 至 (0.95, 0.99) 区间重启（告警档）；④ 拒绝档下 mock 时钟推进一个周期（默认 10 分钟）触发周期探测；⑤ 拒绝档下发起摄取与检索。
- **预期**：① 探测建档（≥3 条哨兵、基线入主库元数据表）并放行（design §5.3 探针细节——v0.8）；② 拒绝以同一 `embed_model` 标签写入 + 告警审计；摄取 embed 阶段失败**可重试**、文档停 `searchable_lexical`（不 500）；**查询侧向量路同步关闭——检索降级 BM25 单路、`notice.degraded` 含 `probe_reject`、不 500**（跨底模距离无意义——拍板2；G-8 两档：**阈值 0.99 告警 / 0.95 拒绝**为临时值，M1 校准）；③ 告警档仅告警、向量路保持；④ 周期探测同样走两档判定（运行中换底模可发现）；⑤ 换标签（重嵌入流程）后放行并恢复向量路。**里程碑口径（复审修）**：M0a 断言落 ①②的写入拒绝/告警/建档与 `notice.degraded` 标注（M0a 检索本就 BM25 单路）；②⑤的**向量路开闭行为**断言随 M1 复验（TC-EMB-07 同款理由）、⑤的换标签重嵌入随 M2（TC-EMB-06）。

#### TC-EMB-04 查询侧降级链【单测｜M1】

- **步骤**：① mock 嵌入端点不可达，发起 search；② mock rerank 端点不可达，发起 search。
- **预期**：① 请求成功、仅 BM25 路、**无 500**、记降级审计事件（FR-2 降级分支 / design §5.2）；② 跳过重排、按 RRF 序返回、记审计；两者响应 `notice.degraded` 含对应枚举（`embed_unreachable` / `rerank_skipped`——v0.8 notice 对象契约，design §5.2；与 TC-RET-02 的 `vector_pending` 同款可观测约定）。

#### TC-EMB-05 Reranker none 实现【单测｜M1】

- **前置**：config `reranker=none`（显式降级路径——网关已确认提供 Cohere 风格 `/rerank` 端点【待决-5 关闭，2026-10-22】，none 为运维/降级选项必测）。
- **步骤**：跑完整检索配方。
- **预期**：管线照常返回（RRF 序、无重排阶段）；分数归一分支对「无 rerank 分」不崩溃（退化为 RRF 归一，FR-2）；**none 为配置态——`notice.degraded==[]`、不发 `search.degraded` 审计**（v1.6.1 勘误随 design v0.9.2——none 非「降级」，M1-1 实现口径经独立验证双 ACCEPT、用户确认）。

#### TC-EMB-06 换模型重嵌入迁移（reembed 任务）【单测｜M2】（v1.6 随拍板③改方案二蓝绿）

- **前置**：库内已有旧标签向量（chunk_vectors，造数）；config 切新标签（`model:dim` 变化）。
- **步骤**：① 触发手动重索引 → 投递 `reembed` 任务（v1.4：驱动为独立任务类型——#42 必修2）；② 迁移期间多次 search；③ **竞态**：切换 config 瞬间构造一个旧模型在途批次（fake Embedder 慢返回），待其回写；④ 全库完成后核对。
- **预期**（**v1.6 按拍板③方案二蓝绿重写**——原方案一置空重建作废，对照数据留实验报告 §3.3）：① 新标签向量**并行写入** `chunk_vectors`（新旧并存——PK(rid, embed_model) 物理支撑），扫描谓词 = 在用块中无 (rid, :new) cv 行；**旧标签持续服务**（`功能零降级`——检索行为不变，M0b-2 实测共存窗口 sqlite 零放大/pg 有读代价风险幅度跑间波动）；② 覆盖率 100%（分子/分母闭合 SQL 见 RUNBOOK——限 tombstone=0 且 version=active_version）后**原子切 config 标签**（零 SQL）；③ 旧模型在途批次回写防护（ON CONFLICT (rid,label) DO NOTHING + 回写防护谓词）——库内不出现孤儿行；④ 旧标签延后清理（`DELETE chunk_vectors WHERE embed_model=:old`——**sqlite 实测 WAL ≈4MB 极廉价；PG 为满量死元组 ≈552MB 量级、页内复用消化**）后全库单标签一致；quality 重跑（缓存键 = (content_sha, embed_model)、旧 `vector_crowding` 已清）且阈值随新模型重标定；`semantic_build` 强制重跑（`dict_rev` 含嵌入标签——design §5.8）；管理面可见嵌入覆盖率（design §8 M2.3）；PG 空间回收窗口（高水位页内复用，需归还 OS 时 VACUUM FULL/pg_repack——RUNBOOK 注记）。

#### TC-EMB-07 混模型向量零距离计算（检索行为）【单测｜M1】（v1.6 口径迁 cv）

- **前置**：同 TC-EMB-02 造数（A=当前标签向量、B=旧标签向量，两块 FTS 均可命中）。
- **步骤**：search 该命中域（向量路开启）。
- **预期**：B 只经 BM25 路出现、**绝不进向量路 top-k**（非当前标签行被 `cv.embed_model = :current` JOIN 谓词排除——design §5.2 v1.1 形态）；A 正常参与双路（TC-RET-02 的推广：从「无 cv 行」扩到「标签不符」）。（v1.4 自 TC-EMB-02 拆出——#42 必修4）

### TC-RET 检索配方

#### TC-RET-01 RRF 融合【单测｜M1】

- **步骤**：构造 FTS 路/向量路已知排名（含仅单路命中的 chunk），手算 RRF(k=60) 期望序列。
- **预期**：融合排序与手算一致；单路 chunk 按该路 RRF 分自然保留（退化兼容）。

#### TC-RET-02 向量缺失退化【单测｜M1】

- **前置**：文档处于 searchable_lexical（embedding 全 NULL）。
- **步骤**：search 该文档命中域。
- **预期**：BM25 单路可搜；返回 `notice.vector_pending=true`；无异常、无空结果误判。

#### TC-RET-03 分数归一【单测｜M1】

- **步骤**：构造 rerank 分数集中与含离群两种分布。
- **预期**：min-max 与 clamp 双分支各自正确把最终分归一到 [0,1]（ragflow 模式）；阈值只作用于归一后分数。

#### TC-RET-04 rerank 输入与候选【单测｜M1】

- **步骤**：断言 rerank 输入为 `content` 原文（非分词文本）与候选数 32；并发请求下信号量生效。
- **预期**：喂原文（FR-2）；候选截断 32（NFR-8）；rerank 经 Reranker provider **API 调用**、异步/线程池执行不阻塞事件循环（D12 修订——可观测：事件循环无长阻塞）。

#### TC-RET-05 LLM 增强 800ms 并行【单测｜M1】

- **步骤**：① mock 网关 500ms 返回；② mock 900ms（超预算）。
- **预期**：① 增强词作为**第三路 BM25 查询**参与 RRF，不重做向量召回；② 超时丢弃、原始两路结果不变，总延迟不受影响（并行——关键路径 = max(原始召回, 增强+BM25) + rerank）。

#### TC-RET-06 双降级开关【单测｜M1】

- **步骤**：分别打开「rerank 输入截断 256 token」与「候选 32→16」配置。
- **预期**：开关生效（输入长度/候选数断言）；结果仍正确只是召回宽度变化（NFR-8 降级路径）。

#### TC-RET-07 参数红线【单测｜M0a/M1】

- **步骤**：① MCP search 传 `top_k=100`；② 传权重/阈值类参数；③ 传 `datasets` 过滤。
- **预期**：① 返回 ≤20（服务端硬上限）；② 不可调参数被忽略（服务端固定，不暴露噪音旋钮）；③ datasets/doc_filter 作为组织内可选收窄正确下推（基线因子「库过滤」单测形态）。

### TC-VER 版本在用制

#### TC-VER-01 首次上传切换时机（D20）【单测｜M1】

- **步骤**：新上传走管线至 searchable_lexical。
- **预期**：`active_version` 0→1 即刻切换，BM25 可搜；此后嵌入进度写 `active_status`、嵌入/质量失败写 `active_error`（#33 P0-2.2）；pending 字段清空。

#### TC-VER-02 覆盖上传切换时机（D20）【单测｜M1】

- **步骤**：对已有 active v1 的文档覆盖上传 v2，分别观察 v2 处于 searchable_lexical / searchable_full 两时点。
- **预期**：lexcial 时点**不切换**（检索仍只见 v1）；full 时点单事务切换；全程旧版本服务、绝无两版本同见（矩阵层 T6/T21）。

#### TC-VER-03 版本号不复用【单测｜M1】

- **步骤**：v2 失败后再发起覆盖上传。
- **预期**：新 pending_version = max(历史)+1（=3，失败版本号不复用）；历史版本可追溯（tombstone 保留 90 天）。

#### TC-VER-04 切换事务内容【单测｜M1】

- **步骤**：触发 v1→v2 切换，事务内逐项断言。
- **预期**：旧块 `tombstone=1` + **`chunk_vectors` 对应向量行删除（v1.6——原 embedding=NULL 的等价迁移，拍板②）**、五列 FTS 内容清空（au 触发器清 FTS）；documents 在用/处理中五字段更新（active_version / active_status / pending_version / pending_status / pending_error——design §5.3，#38 P2 修正「四字段」）带 `WHERE pending_version=:expected` 乐观校验；`pending_dims_json` 解析落入 `document_dimensions`（v2 维度切换前不生效）；（M2-S3 起）同事务 `semantic.untag(doc, old_version)`——事务原子：中途失败全部回滚。

#### TC-VER-05 fetch 旧块替代提示【单测｜M1】

- **步骤**：对已切换文档的 v1 chunk_id 调 MCP `fetch`。
- **预期**：返回 `replaced_by: {doc_id, active_version}` 对象（**不承诺块级映射**）；不返回旧内容、不报"不存在"（agent 引用不失效为幻觉误判——FR-1）。**window 钳制口径（v1.8.1，M2-1 R1 实现）**：`window ∈ [0,10]`（`FETCH_WINDOW_MAX=10`），超限/负值静默钳制不报错（m1-2 P3-8 承接清偿）。

#### TC-VER-06 embed 批次回写防护【单测｜M1】（v1.6 随 v1.1 迁 chunk_vectors）

- **步骤**：embed 进行中并发触发版本切换/删除，随后批次回写。
- **预期**：回写 SQL（v1.1 写 chunk_vectors——INSERT 新标签行 + ON CONFLICT (rid,label) DO NOTHING 防护组）带在用版本/tombstone 防护——已切换/已删块的回写零行生效（P0-2.3；防护语义与 v1.0 等价，载体从 chunks UPDATE 迁 chunk_vectors INSERT）。

#### TC-VER-07 删除与任务取消联动【单测｜M1】

- **步骤**：摄取进行中 DELETE 文档。
- **预期**：其任务被取消；worker 每阶段开始前检查文档存在与版本归属——已删文档不再写块（P0-2.3）。

#### TC-VER-08 tombstone 90 天物理清理【单测｜M2】

- **步骤**：造数 `tombstoned_at`=91 天前的 tombstone 块（**v1.8.1 口径回写**：时点基准由原「created_at=91 天前」改为 **`tombstoned_at`**——0004 迁移新增列，切换事务写入、存量行回填=迁移时点；实现按 design §4「旧版本保留 90 天」语义以 tombstoned_at 起算，Committer R1 裁定实现正确、文档滞后），跑清理任务。
- **预期**：物理删除；90 天内不删；审计留痕（M2.4）。

### TC-CRED 上传凭证流

#### TC-CRED-01 凭证签发与绑定【单测｜M1】

- **步骤**：agent 运行时持委托 token 调 `POST /api/uploads` 声明 `{filename,size,sha256,content_type}`。
- **预期**：返回 `{upload_id, upload_url, expires_at}`；凭证记录绑定 sub+org+服务身份（签发方）三要素（#33 P1-3）。

#### TC-CRED-02 PUT 字节校验【单测｜M1】

- **步骤**：对 upload_url 依次：① 超声明 size 上传；② sha256 不符；③ 同一 upload_id：失败 PUT（超量）→ 修正重传，再于摄取成功消费后 PUT；④ 过期后 PUT；⑤ >200MB。
- **预期**：① 超出声明 size 即拒绝（413，不静默截断——design「截断/拒绝」二义口径本文定为拒绝，附录 A-13）；② 拒绝；③ **失败 PUT 不计消费、修正重传放行；成功消费后任何 PUT 拒绝**（v1.4 统一：凭证「用掉」＝摄取成功入队——与 T12 一口径，#42 P1-12）；④ 拒绝（过期）；⑤ 拒绝（全局上限）——全部带明确错误码（T12 展开）。

#### TC-CRED-03 MCP upload 三一致校验【单测｜M1】

- **步骤**：LLM 调 `upload(upload_id,…)`：① 同 sub+org+服务；② 换组织；③ 换用户；④ 换服务身份；⑤ 哈希不符。
- **预期**：① 进摄取；②~⑤ 拒绝（T11：凭证跨组织/跨身份无效）；凭证在**摄取成功入队后**置已用（失败不置、可重传——v1.4 与 T12 统一，#42 P1-12）。

#### TC-CRED-04 file_ref 防线【单测｜M1】

- **步骤**：构造携带 `../../etc/passwd`、绝对路径、`file://`/`http://` URL、指向白名单根外符号链接的引用。
- **预期**：一律拒绝——`file_ref` 只收不透明 upload_id；共享存储场景白名单根目录 + realpath 规范化 + 前缀校验 + 只读 + 大小/扩展名限制（SSRF/任意读取/穿越三防线，NFR-6）。

#### TC-CRED-05 未消费凭证回收【单测｜M1】

- **步骤**：签发后不消费，跑清理任务。
- **预期**：过期未消费凭证回收（对象目录临时文件同清——design §6.3 时序）。

### TC-QUAL 区分度反馈环

#### TC-QUAL-01 向量拥挤度口径【单测｜M1】

- **步骤**：① 构造与库内 8 个近邻高相似的 chunk；② 构造仅与 **tombstone 旧版本块**或**他组织块**高相似的 chunk。
- **预期**：① 判拥挤（top-8 近邻 mean(sim) > 绝对阈值）写 `quality_flags`；② **不**判拥挤——近邻限定「组织内 + 仅在用版本」（#33 P1-10）；入库单块走 SQL 暴力扫描。

#### TC-QUAL-02 词面通用度【单测｜M1】

- **步骤**：构造 token 平均 IDF 低于绝对阈值的 chunk；对新组织（冷启动）重复。
- **预期**：判通用度低写 flags；冷启动引用全局语料 IDF（不因组织语料为空而误判）。

#### TC-QUAL-03 LLM 兜底写独立列【单测｜M1】

- **步骤**：对 flags 中 open 状态 chunk 触发 LLM 关键词生成。
- **预期**：写入 `llm_keywords`（×0.5~1 低权列）+ 一句定位语进 `auto_keywords`；**不动** `keywords`（人工列）与 embedding（非 Contextual Retrieval——口径如实）。

#### TC-QUAL-04 规模比例 + 抽样重算【单测｜M1】

- **步骤**：造数 `detected_at_scale`=100（当前语料 10000）的块与近期块，跑重算任务。
- **预期**：仅「检测时规模 < 当前一定比例」的块与抽样命中块重算；批量走 numpy 矩阵乘（非 SQL 逐行——性能断言：万级块分钟级内完成）。

#### TC-QUAL-05 报告页近邻防旁路【单测｜M1】

- **步骤**：u_cn（region=[CN]）查看某 flags 明细，其近邻含 OS-only 块。
- **预期**：近邻内容展示**过同一套 ACL**（OS-only 块不出现）或仅显示相似度数值（T18 单测形态；`detail_json` 原始数据不因报告页而泄漏）。

### TC-AUTH 鉴权与组织上下文

#### TC-AUTH-01 静态 token 边界【接口｜M0a】

- **步骤**：① dev 配置下 u1 调 `POST /api/dev/token`；② u1 给 u2 签发；③ 系统管理员给他人签发；④ 生产配置下调该端点。
- **预期**：① 成功（仅开发/测试/CI——D18）；② 403（只能给自己签）；③ 成功；④ **404**（生产环境不注册路由——P1-7 / T16）。

#### TC-AUTH-02 组织上下文统一规则【接口｜M0a/M1】

- **步骤**：MCP 调用分别构造：① token 有 org claim + 注入头一致；② claim 与头不一致；③ 无 claim 无头；④ 工具参数携带 org；⑤ REST 路径 org 与 `X-Org-Id` 并存且不一致。
- **预期**：① 正常（claim 优先）；② 400；③ 400（缺失即报错，无隐式默认）；④ 参数 org **忽略并记审计**；⑤ 400（D18 统一规则 / T14 展开）。

#### TC-AUTH-03 SSO JIT 建档【单测｜M2】

- **步骤**：mock SSO 首次验签通过的用户请求。
- **预期**：users 表自动落库（id/username/display_name）；二次登录复用（D16——管理员不建账号只配授权）。

#### TC-AUTH-04 委托 token 语义【单测｜M2（M0b 先实测客户端形态）】

- **步骤**：构造 `aud=knowledge-lattice`、`sub`=用户、`act`=agent、`org` claim 单值的委托 token 调用；再分别构造：透传用户原始 token；有效 token 下请求体夹带权限字段——两种请求。
- **预期**：委托 token 按 sub 计权、act 进审计；**透传原始 token → 拒绝**（MCP 规范明令）；**请求体权限字段 → 忽略并记审计、请求正常处理**（requirements FR-4/D18 与 design §5.5 已于 v0.6.1 统一为该口径——原措辞不一致登记见附录 A-9，随 #39 闭环）。M0b 实测项：`langchain-mcp-adapters` 按用户切换 token 的客户端形态与刷新（TC-PERF 关联）。

#### TC-AUTH-05 可信子系统三约束【单测｜M2】

- **步骤**：服务凭证调用分别构造：① 白名单内 + `allowed_orgs` 匹配 + 用户在场证据一致；② org 越界；③ `X-On-Behalf-Of` 的 sub 与在场证据不符（冒充离线用户）；④ 白名单外服务。
- **预期**：① 按声明用户计权、双身份进审计；②③④ 拒绝并审计（#33 P1-5 三约束 / T13 展开）。

---

## 二、集成与生产化用例

### TC-E2E 端到端集成

#### TC-E2E-01 摄取→检索全链【集成｜M0a（BM25 单路）/ M1（全配方）】

- **前置**：dev token 用户 u_full，dataset=vat_lib。
- **步骤**：REST multipart 上传 docx（region=[CN]）→ 轮询文档状态 → 各时点检索。
- **预期**：`searchable_lexical` 时点 BM25 命中（中间态可搜）；`searchable_full` 后双路+rerank 命中；结果带 chunk_id/doc_id/title/page_no/score/dims/source 溯源字段（MCP 契约 §6.1）；`datasets` 过滤与 `doc_filter` 正确收窄。

#### TC-E2E-02 版本切换原子性【集成｜M1】

- **步骤**：覆盖上传进行中并发发起检索循环；切换瞬间（乐观校验窗口）并发第二个覆盖上传。
- **预期**：任意时刻检索只见 v1 或 v2 之一（无中间态混见）；第二个覆盖上传得 409（T7 集成复跑）；切换失败（注入异常）回滚后 v1 继续服务、pending 块零残留（T8）。

#### TC-E2E-03 任务租约重认领【集成｜M1（机制）/ M2（杀进程演练）】

- **步骤**：造数 `lease_until`=过去的 running 任务；M2 再真实 kill -9 worker。
- **预期**：任务被其他/重启 worker 重认领续跑，attempts 递增；「杀 worker 不丢任务」验收的测试化（M2.6）。

#### TC-E2E-04 维度变更即时生效【集成｜M1】

- **步骤**：u_full 可见 d_os(region=[OS])；撤掉其 OS 授权（或 PATCH d_os 维度收紧）后立即检索。
- **预期**：下一次查询即不可见（查询时实时展开——D6）；**v1.6：dims_json 投影已随拍板①删除**——PATCH 直接写 `document_dimensions`，检索输出 dims 经 store 聚合回填（D6「维度变更即时生效」语义保持，UPDATE 不重嵌）；文档维度多值其余值不受影响。

#### TC-E2E-05 schema v1.1 迁移【集成｜M0b】（✅ 已完成——M0b-3 兑现）

- **步骤**：在 M0b 结论（**已拍板：删 dims_json + 分表 chunk_vectors**——2026-10-24 用户确认）下执行 v1.1 迁移（0002 双方言）。
- **预期**：迁移完成 + `PRAGMA foreign_key_check` 空（M0b 验收——**已兑现**：存量搬运载荷逐字节保真、幂等重放、版本只前进、孤立行显式丢弃）；迁移后 **M0a 可达矩阵子集**复跑绿（T1~T5 / T20 / T22 + TC-SCAF / TC-ACL / TC-FTS 相关——版本链、凭证等 M1 能力尚未实现不在此列，#38 P1-5 修订；**M0b-3 实测：全量 271 双后端双模式绿**）；**全量矩阵复跑在 M1 收口**（§六 M1 行）。

#### TC-E2E-06 MCP 端到端（M0a 验收原句）【集成｜M0a】

- **步骤**：deepagents（或 langchain-mcp-adapters 测试客户端）经 MCP 以**开发 JWT** 调 `search`。
- **预期**：返回带 chunk_id 的命中（M0a 验收）；60s 超时中间件挂载（超时请求不悬挂）。

#### TC-E2E-07 REST 上传 + 静态页壳【集成｜M0a】

- **步骤**：浏览器打开静态页；经 REST multipart 上传并查看任务状态与检索测试页。
- **预期**：薄壳可用（上传/检索两视图最小闭环）；API 契约先行（UI 只是壳）。

### TC-TASK 任务与 worker

#### TC-TASK-01 心跳与租约【单测｜M2】

- **步骤**：running 任务每 5s 更新 `heartbeat_at`；造数心跳停更 + `lease_until` 过期。
- **预期**：租约 60s；过期任务可被重认领（design §5.3 状态机：pending→leased→running→done|failed）。

#### TC-TASK-02 重试上限【单测｜M2】

- **步骤**：持续失败的任务重跑。
- **预期**：`attempts ≥ 3` 转 failed 留人工（error 字段落原因）。

#### TC-TASK-03 任务取消【集成｜M2】

- **步骤**：对 running 任务 `POST /api/orgs/{org}/tasks/{id}/cancel`。
- **预期**：任务在**阶段边界**停止（幂等续跑不复活）；取消后文档状态一致（不滞留 parsing）。

#### TC-TASK-04 子进程隔离【集成｜M2】

- **步骤**：注入使 worker OOM 的解析任务。
- **预期**：仅 worker 子进程死亡，主进程检索可用（anything-llm 样板——OOM 只杀 worker）；worker 自动拉起。

#### TC-TASK-05 语义任务错峰限速【观察｜M2-S1】

- **步骤**：观察 semantic_sync / semantic_retag 调度窗口与批速。
- **预期**：分批 ≤1000 行/批、夜间窗口、重标最低优先级（NFR-11——记录级验收：语义任务运行期间 docs 检索 P95 无劣化）。

#### TC-TASK-06 语义故障不波及 docs（NFR-11 故障隔离）【集成｜M2-S1~S3（各任务类型落地时逐步覆盖）】

- **步骤**：分别注入 ① semantic_sync 适配器超时/抛错；② semantic_build 构建异常；③ semantic_retag 失败——各故障进行中持续调用 docs search 并上传普通文档。
- **预期**：docs 检索全程可用（P95 无劣化、无 5xx）、ingest 任务正常推进不被阻塞；语义任务落 failed 带错误原因；告警与审计可见（NFR-11「语义同步/构建/重标故障不影响 docs 检索可用性」——#38 P1-6 补）。

### TC-OPS 生产化

#### TC-OPS-01 审计 outbox 一致性【集成｜M2】

- **步骤**：触发授权替换 / 取值停用 / 维度退役 / 成员变更 / 语义同步 / 语义构建 / YAML 合并 / restricted 实体持权访问八类权限事件（含其中一类在业务提交后立即崩溃的注入场景——语义侧三类为 #38 P1-7 补，断言同样落在对应用例 TC-BUILD-03 / TC-YAML-03 / T-S9）。
- **预期**：业务库同事务写入 `audit_outbox`（崩溃注入下业务与 outbox 同生共死——「业务改了就一定有审计」）；后台任务搬至月库 `audit_events` 后回填 `shipped_at`（M2.6 验收）。**v1.8.3 搬运侧方言口径（M2-2 偏差①终态裁定）**：写侧同事务双方言成立；搬运侧 **sqlite 为两步幂等**（WAL 无跨文件原子事务——月库 `INSERT OR IGNORE` → 回填 shipped_at，at-least-once + 月库 PK 去重，崩溃注入实证不丢不重、链完整）、**pg 为单事务**（BEGIN…COMMIT 内含回填）。

#### TC-OPS-02 审计月库滚动【集成｜M2】

- **步骤**：① 跨月边界写入（造数 202610→202611）；② UPDATE/DELETE 当月与已封存月库的 audit_events；③ 造数 13 个月前的月库文件。
- **预期**：① 新月库由连接工厂建表+触发器，旧月库封存只读；② 全部 ABORT（append-only）；③ 整文件删除（保留期 12 个月）；哈希链每月首条引用上月末哈希、封存记末哈希（requirements FR-6 口径——#38 P2 核对：与 design §4 注不冲突）。**v1.8.3 链序口径（M2-2）**：哈希链按**插入序**（sqlite rowid / pg `seq` 序列列——同秒并列下 `(created_at,id)` 排序序≠插入序，M2-2 R2 已修并带「同秒 + id 逆序 + 跨两轮搬运」回归）；canonical 字段集冻结于 `store/audit_chain._CHAIN_FIELDS`、不含排序键。

#### TC-OPS-03 审计访问分级【集成｜M2】

- **步骤**：① org_admin 查本组织审计；② 系统管理员查询；③ org_admin 查他组织。
- **预期**：① 全量（含查询词与命中）；② **仅元数据**（查询词与命中详情不含——确需内容走审批+临时授权）；③ 拒绝（FR-6 分级）。

#### TC-OPS-04 删除级联与删库流程【集成｜M2】

- **步骤**：① DELETE 文档；② 对仍有文档的库发删除；③ 先删文档后删库。
- **预期**：① chunks / document_dimensions / quality_flags 级联删除、任务取消、（M2-S3）untag 同事务；② 明确报错（RESTRICT——非裸外键异常，T19 半句）；③ 成功；90 天 tombstone 物理清理独立运行（TC-VER-08）。

#### TC-OPS-05 备份快照与恢复演练【集成｜M2】

- **步骤**：`VACUUM INTO`/online backup 快照（含 `data/objects/`）→ 新环境恢复 → 跑迁移 → 抽查检索与矩阵子集。
- **预期**：恢复后数据完整、检索正常、`user_version` 前进；RPO ≤24h / RTO ≤4h 口径记录（M2.6 验收「恢复演练通过」；G-5 快照目的地缺口见 known-gaps）。**v1.8.3 备份范围口径（M2-2）**：sqlite 快照 = 主库（VACUUM INTO）+ `data/objects/`（tar）；**审计月库 `audit_*.db` 文件备份方式见 RUNBOOK §4**（自动快照纳入随 m2-3）——恢复完整性验收以主库+objects 为准；pg `pg_dump -Fc`（分区同库天然含审计）。

#### TC-OPS-06 CSV 授权批量导入【集成｜M2】

- **步骤**：① 导入 500 行 CSV（username, dim_key, values…, expires_at）；② CSV 含 org 列且与路径不一致；②' CSV 含 org 列且与路径**一致**（附录 A-12 口径：一律拒绝——CSV 不带 org 列）；③ CSV 混入 sync 维度行；④ 目标用户无有效成员关系；⑤ 重复导入同文件。
- **预期**：① 幂等全量替换、差异预览后生效（M2.6 验收「批量导入 500 行正确」）；② 与 ②' 均整批拒绝（org 一律以路径为准）；③ sync 授权不动（T-CSV 主断言）；④ 拒绝该用户行（防孤儿授权）；⑤ 二跑零差异（幂等）。

#### TC-OPS-07 维度退役与取值停用治理【集成｜M2】

- **步骤**：① `PATCH values/{id} status=disabled` 带 dry_run；② `POST dimensions/{id}/retire`。
- **预期**：① dry_run 返回影响面预估（受影响文档/用户数）、确认后停用=收紧进计算（T3 联动）+ 审计；② 退役带影响面预估 + 二次确认 + 审计，退役后编译产物不再含该维度条件（T20 退役半句——唯一放宽路径必有审计）。

#### TC-OPS-08 members grants 全量替换【集成｜M2】

- **步骤**：`PUT /api/orgs/{org}/members/{id}/grants` 替换 u1 的 local 授权，u1 另有 sync 授权。
- **预期**：仅 local 授权被替换，sync 不动（§6.2 端点语义）；支持 expires_at；审计入 outbox。

#### TC-OPS-09 跨组织隔离汇总【矩阵｜M2】

- **步骤**：u_gl（仅 org:gl）对 org:tax 的检索 / 文档详情 / 任务 / 审计 / 语义端点全量扫描。
- **预期**：全部拒绝或空集——`org_id = :org` 第一条件 + 成员关系校验（M2.6 验收「跨组织隔离全绿」；T15 / T-S7 汇总）。

### TC-UI 界面国际化（FR-8，v1.5 新增——需求 v0.9 对话决策）

> 口径：本组为**手动走查用例**——前端薄壳无构建链/测试框架（FR-5 薄壳纪律），不进 CI 自动化；随各视图页面落地时执行并在 §六 对照表勾验。断言对象为浏览器实际渲染；后端行为不为本组断言对象（语言仅为前端状态——FR-8「服务端不感知语言」）。

#### TC-UI-01 语言切换与持久化【手动｜M0a 机制就位，M1 随检索页复验】

- **步骤**：①清 `localStorage` 后打开页面（默认态）；②点头部「中 | EN」切英文、再切回中文；③英文态刷新页面、重开浏览器。
- **预期**：①默认中文、`<html lang="zh-CN">`；②切换后全页 UI 文案即时切换，`<html lang>`（zh-CN / en）与 `<title>` 同步更新；③语言选择保持（localStorage 持久化）。

#### TC-UI-02 双语完整性——无混语言 UI 文案【手动｜M1 检索页起，各视图落地时扩展】

- **步骤**：EN 态逐视图走查导航 / 按钮 / 表头 / 状态标签旁注 / 空态 / 教学说明 / placeholder / 提示语；zh 态反向抽查。
- **预期**：EN 下无裸中文 UI 文案、zh 下无裸英文 UI 文案；**排除项按口径原样保留**——状态枚举（`searchable_full` 等）、API 路径、工具名（`annotate` 等）、章节引用（§5.1 等文档内锚点）、业务数据（不译——FR-8）。

#### TC-UI-03 业务数据与行为不随语言变化【手动｜M1】

- **步骤**：同一 query 分别在 zh / EN 界面语言下检索并对照命中列表；抽一条越权拒绝用例（如 T1 过期授权）在两语言下各执行。
- **预期**：命中集合、排序、score、dims 展示两语言一致；文档标题 / 实体名 / 维度取值标签保持数据本身语言；越权用例两语言下均拒绝且拒绝语义不变。

#### TC-UI-04 服务端不感知语言【手动｜M1】

- **步骤**：切换界面语言前后，对同一操作（一次检索 + 一次管理操作）抓取 API 请求与响应。
- **预期**：请求不带语言参数、报文无语言差异；审计事件字段与错误码不随界面语言变化。

---

## 三、越权矩阵（T1~T23 + T-CSV + 补充行——CI 常跑）

> 覆盖口径（design §9）：原矩阵七因子 + v0.3 四组 + T1~T19（#33）+ T20~T23（#34）。**标准矩阵 fixture**（pytest fixture 工厂，本节全部用例复用）：
>
> - **组织**：`org:tax`（主）、`org:gl`（隔离对照）。
> - **维度（org:tax）**：`region`（required=1, active；值 CN/OS）、`tax_type`（required=0, active；值 VAT/CIT）、`channel`（新增维度演练——建维度时库内已有存量文档，零回填；**取值 A**——T20 回填用，v1.4 补）。
> - **用户**：`u_full`（region=[CN,OS]，tax_type=[VAT]）；`u_cn`（region=[CN]，tax_type 无授权）；`u_cn_vat`（region=[CN]+tax_type=[VAT]——T6 查看者，#40 P0-R1 补）；`u_os`（region=[OS]）；`u_expired_grant`（region=[CN] 授权行 expires_at=昨天、tax_type=[VAT] 作对照）；`u_expired_member`（成员关系 expires_at=昨天、授权行未过期）；`u_owner`（d_cn 的 owner，region=[OS]+tax_type=[VAT]——T17 授权与 owner 错位锚点；**T21 另行造数 u_owner'**：初始 region=[CN]+tax_type=[VAT]，步骤中撤销 region）；`admin_tax`（org_admin，无维度授权）；`admin_full`（org_admin，region=[CN,OS]+tax_type=[VAT]——TC-AZ-01③ 代标用，#40 P1-R2 补）；`sysadmin`；`u_gl`（仅属 org:gl，**org_admin**——T15 口径，v1.4 补）；`u_multi`（**org:tax 与 org:gl 双组织成员**——T11 用：持合法 org:gl 委托 token，v1.4 补，#42 必修3）。
> - **维度缺省约定（#38 P1-1）**：文档**未显式列出取值的 active 维度一律无值**（空值放行）——单因用例不引入第二维度混淆变量；需对照时按用例内造数补授权（如 T1/T2/T17 以 tax_type=[VAT] 隔离 region 单因）。
> - **文档（org:tax / vat_lib）**：`d_cn`（region=[CN]，tax_type=[VAT]）、`d_multi`（region=[CN,OS]）、`d_empty_region`（region 无值）、`d_cit`（tax_type=[CIT]）、`d_os`（region=[OS]）；版本用例另造 pending/切换序列。
> - 时间类一律造数（直接写过期时间戳）；**格式统一 UTC `YYYY-MM-DD HH:MM:SS`（与 SQLite `CURRENT_TIMESTAMP` 同款）**——触发器（`CURRENT_TIMESTAMP`）与编译器入参 `:now` 的字符串比较同格式，防格式不一致错判（v1.4 钉死，#42 P2）。

### 3.1 基线因子 → 用例映射

| §9 基线因子 | 落点 |
|---|---|
| 用户授权基本过滤 | T1 / T3 / T22、TC-ACL-02 |
| 文档维度多值（维度内 OR） | T5（d_multi）、TC-ACL-02 |
| 库过滤（datasets/doc_filter） | TC-RET-07、TC-E2E-01 |
| 可选维度空值放行 | T5 / T22（d_empty_region） |
| 新增必选维度未回填 | T20①②（channel） |
| 移出组织重加 | TC-SCAF-05（级联）+ T2/T23（不复活） |
| 跨组织 | T15、TC-OPS-09、T-S7（语义） |
| MCP 统计不泄露 | TC-AZ-02 |
| v0.3 版本中间态组 | T6 / T8 / T9 / T21 |
| v0.3 删维度取值组 | T3 / T19 |
| v0.3 PATCH 越权组 | TC-AZ-01 |
| v0.3 CSV 组 | T-CSV |

### 3.2 T1~T23 逐条展开

#### T1 过期授权：清理任务未跑仍不可见【矩阵｜M0a 单测先行→M1】

- **前置**：u_expired_grant 对 region=[CN] 的授权行 expires_at=昨天、tax_type=[VAT] 有效（隔离单因）；定时清理任务**从未运行**。
- **步骤**：编译 u_expired_grant 的授权展开并检索 d_cn。
- **预期**：展开 SQL 以 `expires_at > :now` 过滤该行——CN 不在授权集；d_cn 不可见、d_empty_region 可见（#33 P0-1①：过期即失效，不等清理）。

#### T2 成员续期不复活旧授权【矩阵｜M0a→M1】

- **前置**：u_x 曾属 org:tax（region=[CN]、tax_type=[VAT]），成员关系已过期。
- **步骤**：① 过期期间检索；② 恢复访问：先 DELETE membership 再重插（续期禁令下的唯一路径——触发器见 T23）；③ 重插后检索 d_cn 并查其授权行。
- **预期**：① 第 0 步拒绝（无有效成员关系）；②③ DELETE 触发级联清授权——重插后授权集为空，d_cn 不可见（旧授权不复活——#33 P0-1）。

#### T3 停用取值收紧【矩阵｜M0a→M1】

- **前置**：u_full（region=[CN,OS]）可见 d_os（region=[OS]）。
- **步骤**：PATCH 取值 OS `status=disabled`（经 dry_run+确认）后立即检索。
- **预期**：OS 视为「存在但无人被授予」——u_full 授权集变 [CN]，d_os 不可见、d_cn/d_multi 仍可见（D19 停用=收紧，非放宽）。

#### T4 维度改可选/停用不放宽【单测｜M0a】

- **步骤**：对 region 分别 UPDATE `required` 1→0、`enabled` 1→0，重新编译同用户产物并 diff。
- **预期**：产物逐字不变（生命周期与过滤解耦——D5 v0.4；TC-ACL-04 的矩阵断言形态）。

#### T5 可选维度有值则过滤【矩阵｜M0a→M1】

- **前置**：tax_type 为可选（required=0）；u_cn 无 tax_type 授权。
- **步骤**：u_cn 检索 d_cit（tax_type=[CIT]）与 d_empty_region。
- **预期**：d_cit 不可见（有值→需交集，空交集=不可见）；d_empty_region 可见（无值放行）——可选性不影响过滤语义。

#### T6 v2 改维度：切换前后无双方可见【矩阵｜M1】

- **前置**（#40 P0-R1 重造；复审二轮修正上传者）：查看者 `u_cn_vat`（region=[CN]+tax_type=[VAT]——可见 d_cn v1 的双维度前提）；覆盖上传由 `admin_full` 发起——**操作权限**（org_admin——FR-4 操作矩阵：覆盖上传 = owner 与 org_admin；u_full 是普通成员会先 403）与**写权限**（region=[CN,OS]+tax_type=[VAT]，v2 取值 region=[OS] 在其授权内）双前提成立，v2 带 region=[OS]（pending_dims_json）。
- **步骤**：pending 期间以 u_cn_vat 检索；切换事务后再检索；全程以 TC-ACL-07 两种 ACL 写法各跑一遍。
- **预期**：pending 期间按 v1 维度判权（v2 新维度不生效——P0-2.1），u_cn_vat 可见 v1；切换后按 v2 判权（region=[OS] 与其 [CN] 无交集），u_cn_vat 不可见；**任一时刻两版本块不同时出现**；两写法结论一致。

#### T7 并发覆盖 409【矩阵｜M1】

- **步骤**：d_cn 存在 pending v2 时，再次发起覆盖上传（操作者 `admin_full`——**v1.4 改**：fixture 的 `u_owner` 仅 region=[OS]，d_cn region=[CN]，FR-4 要求覆盖上传「新旧取值均须校验」会先在取值校验处 403、走不到被测 409；admin_full 兼具 org_admin 操作权限与 region=[CN,OS] 授权，双前提成立——#42 必修3；REST 与 MCP 两条路径——#40 P2 补操作者）。
- **预期**：409（同一时刻只有一个 pending——P0-2.3）；不产生第三个版本号。

#### T8 失败版本无 FTS 残留【矩阵｜M1】

- **步骤**：使 d_cn 的 pending v2 在 embed 阶段失败；以 v2 独有关键词 MATCH 检索。
- **预期**：pending_status=failed；v2 块**立即物理删除**（经 ad 触发器移出 FTS）——MATCH 零命中；v1 继续服务不受影响。

#### T9 切换后 FTS 层无旧版本命中【矩阵｜M1】

- **步骤**：d_cn v1→v2 切换后，以仅 v1 内容含有的关键词 MATCH（绕过服务层直接查 FTS 也测）。
- **预期**：零命中——版本条件在 FTS 路 JOIN 上（§5.1）；tombstone 行五列已清空（切换事务）。

#### T10 待嵌入清单不含 tombstone【单测｜M1】

- **步骤**：切换后查询待嵌入清单（`idx_chunks_vec_pending` 谓词：`embedding IS NULL AND tombstone=0`）。
- **预期**：旧版本块不在清单（P1-2——否则切换后旧块重回待嵌入队列、回写复活）；**v1.6 口径**：M2 起 reembed 扫描谓词 = 在用块中无 (rid, :new_label) chunk_vectors 行（`embedding IS NULL OR embed_model != :current` 的 v1.1 等价形态，见 TC-EMB-06；本条 M1 口径不变）。

#### T11 凭证跨组织/跨身份无效【矩阵｜M1】

- **前置**：agent A 持 u_full@org:tax 委托 token 签发的 upload_id；`u_multi`（v1.4 补——org:tax 与 org:gl 双组织成员，持**合法** org:gl 委托 token；防「换组织」用例先撞成员关系 403 或 D18 claim 不一致 400、测不到凭证绑定层——#42 必修3）。
- **步骤**：分别以 ① u_multi 的 org:gl 上下文（token 与成员关系均合法）；② 其他用户；③ 其他服务身份消费该凭证。
- **预期**：全部拒绝且为**凭证绑定专属错误码**（upload_id 绑定 sub+org+服务身份三一致——#33 P1-3；① 中成员关系与 claim 校验均不成立，拒绝只能来自绑定校验本身）；TC-CRED-03 矩阵形态。

#### T12 PUT 超量/哈希不符拒绝【矩阵｜M1】

- **步骤**：PUT 超声明 size 字节；PUT 内容 sha256 与声明不符。
- **预期**：均拒绝且凭证不标记已用（可重新正确上传）；200MB 全局上限独立生效（TC-CRED-02 矩阵形态）。

#### T13 可信子系统越界/冒充拒绝并审计【矩阵｜M1（dev 白名单模拟）→M2（生产形态收口）】

- **前置**：白名单服务 S（allowed_orgs=[org:tax]）。
- **步骤**：S 声明 `X-On-Behalf-Of`=u_gl（非本组织用户）调用；S 带 org:gl 上下文调用；白名单外服务 S2 冒充 S 调用；无用户在场证据调用。
- **预期**：全部拒绝且 `outcome=refused` 进审计（#33 P1-5；三约束展开见 TC-AUTH-05）。里程碑口径见附录 A-1。

#### T14 org claim 与头不一致 400【矩阵｜M1】

- **步骤**：① token org claim=org:tax，注入头 X-Org-Id=org:gl；② 两者皆缺；③ 工具参数带 org=org:gl；④ REST 路径 org 与头不一致。
- **预期**：①400 ②400（无隐式默认）③ 参数忽略+审计 ④400（D18 统一规则；TC-AUTH-02 矩阵形态）。

#### T15 他组织维度 id 403/404【矩阵｜M1】

- **步骤**：u_gl（org:gl 管理员）对 org:tax 的 dimension id / value id / document id / grant 端点逐个调用。
- **预期**：全部 404（存在性敏感端点）或 403（明确越权端点）——按端点固定并在 API 文档落字（口径见附录 A-2）；绝不返回他组织资源内容；跨组织检索空集。

#### T16 生产配置 token 端点 404【矩阵｜M1】

- **步骤**：以生产配置启动服务，调 `POST /api/dev/token`。
- **预期**：404（路由未注册——P1-7；TC-AUTH-01 矩阵形态）。

#### T17 授权撤销后 owner 不再见在用文档【矩阵｜M1】

- **前置**：u_owner 是 d_cn 的 owner，region=[OS]+tax_type=[VAT]（d_cn region=[CN]——仅 region 单因不可见）。
- **步骤**：u_owner 检索 d_cn；调文档详情（管理面端点）。（v1.7 载体澄清：原「调 `list_documents` 与文档详情」——`list_documents` 为 §6.1 ACL 视角工具（权限内可见，与 T17 owner 兜底语义无关），owner 元数据兜底载体 = **文档详情端点（org 域管理面）**，与 TC-AZ-03「两个端点两个口径」一致——M1-5 R2 用户裁定 A=② 落笔。）
- **预期**：检索/召回零命中——**检索路径无 owner 分支**（#34 必修 2）；**文档详情**可见自己文档的**元数据与状态**（不返回块内容）——owner 兜底走管理面。

#### T18 报告页近邻不泄露无权内容【矩阵｜M1】

- **前置**：u_cn 的质量报告某 flag 的 detail_json 近邻含 OS-only 块。
- **步骤**：u_cn 查看质量报告明细。
- **预期**：近邻展示过同一套 ACL 或仅数值——OS-only 块内容/标题不出现（#33 P1-10）。

#### T19 删文档/删库：按定义成功或明确报错【矩阵｜M1（删文档）/ M2（删库）】

- **步骤**：① 删除无任务运行的文档；② 删除摄取中的文档；③ 对仍有文档的库删除。
- **预期**：① 成功（级联+取消任务）；② 成功（任务取消在阶段边界生效）；③ 明确业务报错——**非裸外键异常**（RESTRICT 之上服务层先校验）。

#### T20 新建维度零消失 / 回填只收紧 / 生命周期不放宽 / 仅退役放宽且有审计【单测｜M0a（审计半句 M2）】

- **步骤**：① 新建 active 必选维度 channel（存量文档零回填）→ 全用户检索；② 回填 d_cn channel=[A]（u_full 无 channel 授权）→ 检索；③ channel `required` 1→0、`enabled` 1→0 → 检索；④ channel `retire`（dry_run+确认+审计）→ 检索。
- **预期**：① 存量文档零消失（空值放行）；② d_cn 对 u_full 不可见（回填即收紧）、d_empty_region 仍可见；③ 可见性不变（不放宽）；④ channel 条件从产物消失=唯一放宽路径，且退役事件已入 outbox 审计（#34 必修 1 全四断言）。

#### T21 授权撤销后 owner 覆盖上传：处理窗口检索不到任何版本【矩阵｜M1】

- **前置**（#38 P0-1 重造，时序符合 FR-4）：u_owner' 是 d_cn（region=[CN]，在用 v1）的 owner，**初始持 region=[CN]+tax_type=[VAT]**。
- **步骤**：① u_owner' 发起覆盖上传 v2（region=[CN]——写权限校验在 upload 时点通过，FR-4/design §5.3）；② pending 期间**撤销** u_owner' 的 region 授权；③ v2 处理中窗口（未切换）检索 d_cn；④ v2 完成、单事务切换后再检索。
- **预期**：③ 撤销即时生效（查询时展开）——v1、v2 均**零命中**（v1 按维度判权不可见；pending 块本不可见），owner 身份不产生任何放宽；④ 切换后仍不可见——彻底消除「授权撤销后 owner 借覆盖上传处理中窗口重新看到在用全文」的越权路径（#34 必修 2 验收句）。上传时点校验通过、撤销发生在其后，全程不违反 FR-4；设计**无 owner 写权限例外**——若未来要例外属决策变更，须先改 FR-4（不可只在用例放行）。

#### T22 无授权维度只见空值文档；空集不出 `IN ()`【单测｜M0a】

- **步骤**：u_cn（tax_type 零授权）检索全库；断言编译产物文本。
- **预期**：只见 tax_type 为空的文档（d_empty_region 等——region 约束照常叠加）；**tax_type 维度对应的产物片段**为 `NOT EXISTS(…)` 单条件（无 OR EXISTS 分支），完整产物仍含 region 的统一模板，全局**无 `IN ()`**（#34 必修 3；SQL 语法非法兜底——#38 P0-2 修订：断言落在维度片段级，非整份产物）。

#### T23 过期成员关系续期被拒；先删再加旧授权不复活【单测｜M0a（触发器）/ 矩阵｜M1（行为）】

- **步骤**：① 对 expires_at=昨天的 membership 行 UPDATE expires_at=未来；② DELETE 后重插同用户 membership；③ 查其旧授权。
- **预期**：① 触发器 ABORT（`expired membership: delete then re-add`）；②③ 级联清理已发生——旧授权不存在（与 T2 行为半句互证）。

### 3.3 补充矩阵行（§9 未编号、验收引用）

#### T-CSV CSV 导入只替换 local 授权【矩阵｜M2】

- 完整展开见 TC-OPS-06（M2.6 验收引用名——本行为其别名行，#38 P2 补最小断言）：CSV 全量替换后 `source='sync:…'` 授权行**逐行原样保留**、local 授权按 CSV 替换、幂等二跑零差异。

#### TC-AZ-01 上传/PATCH 取值限操作者授权内【矩阵｜M1】

- **步骤**：① u_cn（region=[CN]）上传 region=[OS] 文档；② u_cn PATCH **d_cn_own**（owner=u_cn、region=[CN]、**tax_type 无值**——本用例造数；#40 P1-R2 用自有文档避免先撞操作权限 403；复审二轮置空 tax_type：防实现按「结果集全维度」校验时拒绝原因来自 tax_type、掩盖 region 取值越权）维度：[CN]→[OS]（新值越权）；再造数 [CN,OS] 后 [CN,OS]→[CN]（旧值越权——OS 不在 u_cn 授权内）；③ `admin_full`（org_admin，region=[CN,OS]+tax_type=[VAT]）对 d_cn_own 代标 region=[OS]；④ `admin_tax`（org_admin、无维度授权）同操作。
- **预期**：①② 拒绝——**新旧取值均须在操作者授权集合内**（#31 P1-1/#32 P1-4：防把文档推向无权范围或打自己看不见的值）；③ 代标成功且管理动作进审计（org_admin 以自身授权内取值代标——附录 A-15 口径）；④ 操作权限放行但取值越权仍拒并审计——管理权与写权限分离（与 TC-AZ-03 呼应）。

#### TC-AZ-02 统计与概况不泄露【矩阵｜M1】

- **步骤**：u_cn 调 `list_documents` 与读 MCP 工具描述注入的组织/维度概况；对照 u_full 结果。
- **预期**：`doc_count/chunk_count` 等一切统计按调用者权限计算——不可见文档的存在与数量不泄露（#31 P1-8）。

#### TC-AZ-03 org_admin 管理权与可见权分离【矩阵｜M1/M2】

- **步骤**：admin_tax（无 region 授权）：① 检索；② 文档管理列表；③ 改维度/授权管理端点。
- **预期**：① 与普通成员同口径（不绕过维度可见性）；② 管理列表只列**自己维度可见**的文档（#32 P1-4 方案 A）——与 MCP `list_documents`（TC-AZ-02，按调用者权限统计）为**两个端点两个口径**、与 T17 的 owner 元数据兜底（管理面）不冲突（#38 P2 澄清）；③ 管理端点可用（管理权独立）。

#### TC-AZ-04 系统管理员仅管理权 + 临时授权【矩阵｜M2】

- **步骤**：① sysadmin 跨组织检索；② sysadmin 建组织/指定 org_admin；③ 临时授权**完整构造**（#38 P2 补、#40 P1-R1 修正）：挂 org:tax 临时成员关系（expires_at 短期）**并授 region=[CN]+tax_type=[VAT] 双维度授权**（d_cn 双维度均有值——缺一仍不可见），访问 d_cn；④ 造数过期后（成员关系或授权任一到期）再访问。
- **预期**：① 拒绝——无跨组织数据可见权；② 成功；③ 生效期内可见 d_cn、全流程审计留痕（成员关系与授权行均带 expires_at——#31 P1-2/P1-7）；④ 到期即不可见（权限计算过滤过期、不等清理——与 T1 同构）。

#### TC-AZ-05 库过滤与 doc_filter 收窄【矩阵｜M1】

- **步骤**：u_full 持多库文档，分别带/不带 `datasets`、`doc_filter` 检索。
- **预期**：过滤为组织内可选收窄（交集语义）；不带过滤=权限内全部；库不承担权限（D15——无库级放宽路径）。

---

## 四、语义层用例（D23，M2-S1~S3）

> 语义 fixture（叠加在标准矩阵 fixture 上）：`org:tax` 内——template `TPL_VAT_INPUT`（字段 `TAX_AMT`）、table `ods.vat_input_invoice`（列 `tax_amt`）、scenario `SC_GENERAL`（uses 模板）、report `VAT_MAIN`（项 `L12`）、concept `vat.input_credit`（YAML 纯人工、含别名「进项抵扣/抵进项」）；`org:gl` 内同名 key 的另一套实体（隔离对照）；restricted 实体 `concept:tax.scheme.internal`（sensitivity=restricted）；环图样本（A→B→C→A）与高扇出样本（一表 300 列、一模板被 10 场景 uses）。词典 `dict_rev` 造数两版 r1/r2。

### 4.1 T-S1~T-S12 逐条展开（§9 冻结编号）

#### T-S1 同步不覆盖人工字段【矩阵｜M2-S2】

- **前置**：YAML 已为 `template:TPL_VAT_INPUT` 写入 definition/caliber 与 manual 别名「进项模板」（curated_rev=r1）。
- **步骤**：源端（mock 适配器）改模板 name 后跑同步；查 `sem_entities` 行。
- **预期**：`name` 更新（事实列）；`curated_json` 原样；`kind IN ('manual','abbr')` 别名原样；`kind IN ('name','code','sync')` 别名按新 name 重建——「同步不覆盖人工」由列级分工保证（#35 §13.1；TC-SYNC-05 机制互证）。

#### T-S2 删除比例保护【集成｜M2-S1】

- **步骤**：mock 源端分别返回 ① 空快照；② 相对**库内该来源 active 实体**（`source='sync' AND source_system=本适配器 AND status='active'`）少 30% 的快照（阈值默认 20%）；③ 少 10% 的快照，各跑一次 run（基数口径 #38 P2 补）。
- **预期**：①② run 置 `aborted_guard`、**零写入**（库内实体/关系/别名逐行 diff 为空）、产生告警；③ 正常执行、消失实体转 missing——全量快照语义是保护前提（FR-S1）。

#### T-S3 同步幂等【单测｜M2-S1】

- **步骤**：同一快照连续跑两次，读第二次 run 的 `stats_json`。
- **预期**：inserted / updated / missing 均为 0（M2-S1 验收句）；`synced_at` 刷新属预期、不计入 updated。

#### T-S4 宽限期状态机【集成｜M2-S1 机制 / M2-S2 验收】

- **步骤**：① 源端快照移除实体 X 后同步（造数 X 的 `synced_at`=今天）→ X 状态？② 次日快照恢复 X 再同步；③ 造数 `synced_at`=8 天前且快照仍无 X 再同步。
- **预期**：① X 置 `missing`（关系保持）；② X 回 `active`；③ X 置 `retired` 且其关系一并 `retired`（默认 7 天——防源端偶发空返回清空图的双保险之二）。

#### T-S5 关系白名单与组织一致性触发器【单测｜M2-S1】

- **步骤**：向 `sem_relations` 依次插入：① src 属 org:gl、dst 属 org:tax 的跨组织关系；② `rel_type`/端点类型组合不在 `sem_rel_types` 白名单（如 concept→column 的 has_field）；③ UPDATE 已有关系的 src_id/dst_id/rel_type/org_id。
- **预期**：①② INSERT 被 `trg_sem_rel_check` ABORT；③ 被 `trg_sem_rel_noupdate` ABORT——要改先删再插（#35 §13.1）。

#### T-S6 递归展开防环/深度/截断【单测｜M2-S1】

- **步骤**：对环图样本（A→B→C→A）`get_entity(A, expand, depth=2)`；请求 depth=3（处置口径附录 A-11：本文按拒绝断言）；对高扇出节点（表 300 列）展开（fanout_limit 默认 50）；请求 fanout_limit=500。
- **预期**：环图正常返回不死循环（path 防环）；depth=3 拒绝（400——服务端强制 ≤2）；300 列按 50 截断且 `truncated=true`；fanout_limit=500 超上限拒绝（400——与 depth 同口径，附录 A-11，#40 P2 补）；节点上限 500（默认 200）。

#### T-S7 语义组织隔离【矩阵｜M2-S3】

- **步骤**：u_gl（org:gl）调 annotate / search_entities / get_entity / describe_table / `GET /semantic/l0` 五端点，目标均为 org:tax 的同名 key 实体。
- **预期**：不返回 org:tax 任何实体（annotate 无 span、search 无命中、get_entity 404、describe_table 403/404、l0 为 gl 自己的片段）；两组织 `dict_rev` 互相独立（gl 构建不触达 tax 词典）；**org 作用域 `sem_*` 表**（sem_entities / sem_aliases / sem_relations / sem_chunk_entities / sem_builds / sem_sync_runs）全带 org_id 且查询第一条件同 docs——`sem_rel_types` 为全局白名单配置表（无 org_id，design §4 DDL），不在隔离断言内（design §4 设计说明⑥ 原表述不准确，已随 v0.6.1 修正——附录 A-7 闭环；#38 P1-2）。

#### T-S8 实体召回不放宽 ACL【矩阵｜M2-S3】

- **前置**：块 b1 属 d_os（region=[OS]，u_cn 不可见）；b1 被 AC 打标命中实体 E（concept，u_cn 可见 E 本身）。
- **步骤**：u_cn 调 `search(query, entities=[E])`（实体召回路启用）；断言三路（FTS/向量/实体）结果并集 ⊆ u_cn 可见块集合。
- **预期**：b1 不出现在任何一路——实体路 SQL 复用 §5.1 同一编译产物（同一编译器、同一产物）；三路并集断言逐块成立（#35 §13.1 核心 ACL 不变式）。

#### T-S9 restricted 实体静默不可见【矩阵｜M2-S3（annotate 侧 M2-S2 可先行）】

- **前置**：restricted 实体 R（别名「内部税收筹划方案」）。
- **步骤**：无 `semantic:restricted` 权限的成员：① annotate 含 R 别名的文本；② get_entity(R)；③ 从 R 的邻居实体展开关系；④ search_entities 搜 R 别名；⑤ 持 `semantic:restricted` 权限成员访问 R（annotate/get_entity）后查 `audit_outbox`（近实时）；月库侧待后台搬运回填 `shipped_at` 后再断言 `audit_events`（搬运异步——#40 P2）；⑥ 无权成员重复①②后查审计（#38 P1-11 补）。
- **预期**：① 无 span（表现为不存在）；② 404；③ R 节点不出现；④ 无命中——存在性零泄露（G-3 已接受其静默性衍生效应）；⑤ **持权访问产生权限事件入 outbox**（restricted 实体访问——FR-6 语义层事件），月库 `shipped_at` 回填后事件可查；⑥ 无权尝试不产生 outbox 权限事件、走查询级异步审计（refused 可回溯）——口径见附录 A-16。

#### T-S10 版本切换/删块 untag 同事务【集成｜M2-S3】

- **步骤**：① 已打标文档覆盖上传并切换版本；② 删除已打标文档；随后查 `sem_chunk_entities` 与对账任务日志。
- **预期**：① 旧版本块的 tag 行在**切换事务内**清除；② 删除同事务清除；定时对账任务兜底运行后断言零残留（刻意的无外键设计靠纪律+对账——design §4 设计说明②）。

#### T-S11 describe_table 白名单与降级【集成｜M2-S1】

- **步骤**：① 对已登记 table 实体调 describe_table；② 对未登记的表名调用；③ mock 元数据系统超时（>3s）；④ 5 分钟内重复调用①。
- **预期**：① 透传列类型/样例/分区/血缘；② 403（防借此枚举整个数仓）；③ 返回轻量节点信息 + `degraded=true`；④ 命中缓存（mock 二次未被请求——缓存 5min）。

#### T-S12 构建原子切换【集成｜M2-S2】

- **步骤**：新词典构建进行中（building）并发 annotate 请求；再注入构建失败。
- **预期**：构建期间请求全部用旧 `dict_rev`（r1）服务；失败后 r1 继续服务、r2 置 failed 不切 ready（懒加载按 (org, dict_rev) 切换——#35 §13.1）。

### 4.2 TC-SYNC 同步流程

#### TC-SYNC-01 per-org 连接解析【单测｜M2-S1】

- **步骤**：config 配 org:tax / org:gl 两套 endpoint；`fetch(org)` 分别调用。
- **预期**：各 org 解析各自实例（per-org 结构，重启生效——#37 前置条件③）；未配置 org 报配置错误（不静默跳过）。

#### TC-SYNC-02 metadata 适配器只拉被引用【单测｜M2-S1】

- **步骤**：构造 `backed_by`/`maps_to` 引用表 t1 + YAML 显式列出 t2 + 未引用 t3 的源端。
- **预期**：只拉 t1、t2 的 table/column 节点，t3 不落库——不做全量镜像（FR-S1）。

#### TC-SYNC-03 分批与单事务【单测｜M2-S1】

- **步骤**：快照含 2500 实体，观察写入批次。
- **预期**：每批 ≤1000 行提交（写锁治理——NFR-11）；批间失败重跑幂等（upsert）。

#### TC-SYNC-04 关系端点冲突不写入【单测｜M2-S1】

- **步骤**：快照含 src 端点在库内不存在的 RelationRecord。
- **预期**：该关系跳过不写入；`GET /api/orgs/{org}/semantic/sync-runs` 该 run 可查，`stats_json.conflicts` 含跳过明细（src/dst/rel_type/原因——字段结构为**测试约定**，design 未定义明细格式，#40 P2 标注）；整批其余写入不受阻断。

#### TC-SYNC-05 别名三 kind 重建【单测｜M2-S1】

- **步骤**：同步前库内已有 manual/abbr 别名；同步后查别名表。
- **预期**：`name/code/sync` 三 kind 先删后插（按新快照）；`manual/abbr` 行原样——与 T-S1 列级分工互证。

#### TC-SYNC-06 维度属性可选携带与填充率告警【单测｜M2-S1（对冲项）】

- **步骤**：① mock 源快照携带模板 region 字段（值域含本地无的码）同步；② 平时携带率的源突然大面积缺值。
- **预期**：① 维度绑定数据落库、值域走显式映射表；**可见性不受影响**（实体维度 ACL 为 NFR-5 演进缝，触发前不启用——#37）；② 触发填充率骤降告警；同步报告展示 per-source 是否携带与填充率。

#### TC-SYNC-07 run 记录与审计【单测｜M2-S1】

- **步骤**：任一适配器跑一次 run（成功与 aborted_guard 各一）。
- **预期**：`sem_sync_runs` 落 running→终态与 stats_json；`semantic.sync` 事件入 audit_outbox（权限事件走 outbox——FR-6 语义层事件）。

#### TC-SYNC-08 手动触发与权限【矩阵｜M2-S1】

- **步骤**：① org_admin 调 `POST /semantic/sync/{adapter}`；② 普通成员调用；③ 查 `GET /semantic/builds · sync-runs`。
- **预期**：① 成功（semantic:admin）并写 outbox；② 403；③ org_admin 可见、普通成员 403（§6.2 端点权限）。

#### TC-SYNC-09 `migrations/semantic/` 落库与白名单种子【单测｜M2-S1】

- **步骤**：跑语义迁移后断言：① `sem_*` 全部 DDL 与触发器（`trg_sem_rel_check` / `trg_sem_rel_noupdate`）落库；② `sem_rel_types` 种子与 design §5.8 白名单表逐行一致（十种 rel_type × 端点类型组合）；③ 与代码常量（实体/关系类型白名单）三处一致（代码常量 + 种子 + 触发器——§5.8「三处一致」）。
- **预期**：语义表 M2-S1 才落库、M0a/M1 库不含 `sem_*`（§3 边界规则 3）；未登记组合被触发器拒绝（与 T-S5 互证）；新增关系类型必须走迁移（#38 覆盖缺口补——sem_* 迁移/seed 无显式用例）。

### 4.3 TC-YAML 覆盖层与 CI 校验

#### TC-YAML-01 合并正路【单测｜M2-S2】

- **步骤**：YAML 覆盖层引用已同步 id（definition/别名/extra_relations），跑 yaml_merge。
- **预期**：写 `curated_json`、manual/abbr 别名、`source='curated'` 关系；`curated_rev` 记 commit SHA；纯人工实体仅 concept/system 可建（其余 type 报错）。

#### TC-YAML-02 冲突与拦截规则（合并规则表逐行）【单测｜M2-S2】

- **步骤**：依次构造 §5.8 合并规则表右侧各行场景：引用未同步/已 retired id、纯人工与同步实体 (type,key) 同键、同别名指向多实体且无消歧、短于 2 字/常用词别名（无 context/fuzzy_only 标注）、extra_relations 与同步重复、端点类型不在白名单、YAML 删除覆盖项、L0 超预算（>1500 token）。
- **预期**：与规则表逐行一致——未同步不写入记冲突（实体恢复后自动生效：补一条恢复后生效断言）；同键报错；歧义别名要求 disambiguation 或 context；短词拦截；重复以同步为准提示可删；端点拦截；删除清 curated/manual 不动事实列；L0 超预算 CI 拦截。

#### TC-YAML-03 webhook【集成｜M2-S2】

- **步骤**：① 带正确签名调 `POST /semantic/yaml/webhook`；② 错误签名；③ 服务身份缺失。
- **预期**：① 触发 yaml 合并 + 构建（§6.2），**yaml 合并事件入 audit_outbox**（FR-6 语义层事件——#38 P1-7）；②③ 拒绝——Git 回调入口仅服务身份。

#### TC-YAML-04 CI 校验全集【单测｜M2-S2】

- **步骤**：对含各类违规的 YAML 仓跑 CI（JSON Schema、别名冲突、短词/常用词、L0 预算、owner 必填、引用可解析、**样本值 >3 条**——v1.4 补，DataAgent 调研借鉴②）。
- **预期**：逐类拦截并给出可定位错误（owner 缺失逐条报——「每条 YAML 必填 owner」；**样本值超限逐条报——每实体 samples ≤3**）。

#### TC-YAML-05 过渡期两端一致【契约｜M2-S3】

- **步骤**：同一份 YAML + 同一文本分别过本地 AC（过渡期 package）与服务端 annotate。
- **预期**：mentions 完全一致（规范化函数与 schema 抽小 package 两端共用——迁移零改动承诺的验证；切换灰度时用评测集对比）。

### 4.4 TC-BUILD 构建产物

#### TC-BUILD-01 dict_rev 与跳过【单测｜M2-S2】

- **步骤**：同一 (active 实体+别名+yaml commit) 组合构建两次；改一条别名再构建。
- **预期**：dict_rev 相同则第二次跳过（不产新 build）；变更后新 rev 构建。

#### TC-BUILD-02 产物三件套（模糊索引 M2-S3，见 TC-SEM-09）【单测｜M2-S2】

- **步骤**：构建后断言：AC 自动机仅收 `match_mode IN ('exact','context')` 别名（fuzzy_only 不进——防误报）；L0 片段渲染（l0: true 条目）；构建报告含冲突/歧义别名/孤立节点/断链关系/评测指标。
- **预期**：三件齐备、报告字段齐；**模糊索引（sem_vec / 拼音 / 编辑距离辅助表）M2-S3 才构建**（design §5.8/§8——#38 P1-3 修正），其产物断言移至 TC-SEM-09。

#### TC-BUILD-03 原子切换与懒加载【单测｜M2-S2】

- 见 T-S12 展开；补充断言：旧版本产物保留到无请求使用（引用计数语义），服务按 (org, dict_rev) 取用；**构建完成/失败事件入 audit_outbox**（FR-6 语义层事件——#38 P1-7）。

#### TC-BUILD-04 评测回归门槛【单测｜M2-S2】

- **步骤**：mock 评测指标较上一版下降 >2 个百分点（如 precision 0.96→0.93）构建。
- **预期**：不切 ready、需人工确认（TC-SEV-02 联动）。

#### TC-BUILD-05 重标投递【单测｜M2-S2】

- **步骤**：构建涉及别名增删 vs 仅改 definition 两种 diff。
- **预期**：前者投递 `semantic_retag`（dict_rev 落后块重标）；后者不投递（避免无谓重标风暴）。

### 4.5 TC-SEM 语义工具契约

#### TC-SEM-01 规范化同函数【单测｜M2-S2】

- **步骤**：全角/半角/NFKC 等价形（「进项抵扣」全半角、大小写混排）annotate。
- **预期**：与 `alias_norm` 同一规范化（NFKC/全半角/小写/去空白）后命中——抽取的小 package 单测复用。

#### TC-SEM-02 最长匹配与权重【单测｜M2-S2】

- **步骤**：构造重叠别名「进项」「进项抵扣」与等长不同 weight 别名。
- **预期**：重叠留长 span；等长取 weight 高者。

#### TC-SEM-03 消歧四级顺序【单测｜M2-S2】

- **步骤**：歧义别名命中多实体，分别构造：① 同句有与候选之一 1 跳关系的其他命中实体；② 无①但传 `context_entities`；③ 无②但传 `prefer_types`；④ 三者皆无。
- **预期**：按序消解——①共现定案 > ②会话焦点 > ③类型先验 > ④返回全部候选 `ambiguous=true`（confidence 不标 1.0——中间件不自动注入）。

#### TC-SEM-04 context 短别名条件保留【单测｜M2-S2】

- **步骤**：`match_mode='context'` 短别名分别在：① 同句有其他确定命中且两者有关系；② 同句有命中但无关系；③ 无其他命中的文本中出现。
- **预期**：①保留；②③丢弃（短词防误报机制——FR-S3）。

#### TC-SEM-05 search_entities / get_entity 契约【单测｜M2-S1（S3 补拼音/向量）】

- **步骤**：search_entities：别名精确命中、前缀命中、拼音、向量各构造一例，断言排序与 `top_k ≤50`、`q ≤200`；get_entity：key/id 二选一、`include` 各参数、expand 带方向后缀（`uses>` / `derived_from<`）。
- **预期**：排序链「别名精确 > 前缀 > 拼音 > 向量」（拼音/向量 M2-S3 交付——G-1 收窄选项可前移，届时本用例前置）；get_entity 返回 entity/nodes/edges/truncated/dict_rev 结构齐。

#### TC-SEM-06 L0 导出【单测｜M2-S2】

- **步骤**：`GET /api/orgs/{org}/semantic/l0`；构造 l0 条目超预算的 YAML。
- **预期**：返回片段 + `dict_rev`；超预算被 CI 拦截（TC-YAML-02 联动）；刷新机制随 G-4 于 M2-S3 定（附录 A-5）。

#### TC-SEM-07 annotate 契约与限流【单测｜M2-S2】

- **步骤**：① 正常 annotate（≤4000 字）断言输出结构（dict_rev/mentions[span,surface,entity_id,type,name,confidence,via,ambiguous,brief]/candidates）；② >4000 字；③ `context_entities` >20。
- **预期**：① 结构齐、via='ac'；② 拒绝（400——超长文本不静默截断，口径附录 A-10）；③ 拒绝。AC 层 P99 <5ms、整体 P99 <20ms 见 TC-PERF-05。

#### TC-SEM-08 agent 中间件契约【契约/观察｜M2-S3】

- **步骤**：过渡期本地 AC 与服务端 annotate 灰度开关切换；观察中间件行为。
- **预期**：注入规则——confidence=1.0 非歧义命中按类型注入 L1（概念带 brief/消歧、对象只一行 name+type+id）；歧义只注候选提示；本轮注入 ≤600 token 超出按 confidence 与出现顺序截断；annotate 超时 200ms 本轮跳过（NFR-11 降级）——中间件住 agent 侧，本侧验收为接口契约与灰度对比记录。

#### TC-SEM-09 模糊兜底三层【单测｜M2-S3（依赖 G-2 澄清）】

- **步骤**：构造同音错字（「留底」→「留抵」）、编辑距离 1（长度 ≥4 别名）、语义近邻（阈值 0.75）三例，`fuzzy=true` annotate。
- **预期**：分别经拼音完全匹配 / 编辑距离 / 向量近邻 top-3 命中；结果 `via='fuzzy'`、confidence 低于第 1 层、落 candidates；jieba 词性筛选只对名词片段跑——**触发者/消费者口径按 G-2 澄清后修订**（附录 A-4）；前置构建断言：M2-S3 构建产出模糊索引（名称/别名/一句话定义的向量经 Embedder provider 生成存 sem_vec——D12 修订——+ 拼音与编辑距离辅助表——design §5.8；#38 P1-3 自 TC-BUILD-02 移入）。

#### TC-SEM-10 模板链路端到端（M2-S1 验收句）【集成｜M2-S1】

- **前置**：语义 fixture 关系链已同步——`TPL_VAT_INPUT --backed_by--> ods.vat_input_invoice --has_column--> tax_amt`、`TPL_VAT_INPUT.TAX_AMT --maps_to--> tax_amt`。
- **步骤**：① `get_entity(key='template:TPL_VAT_INPUT', expand=['backed_by>','has_column>'], depth=2)`；② `get_entity(key='template_field:TPL_VAT_INPUT.TAX_AMT', expand=['maps_to>'], depth=1)`。
- **预期**：① nodes 含目标表与列、edges 含 backed_by / has_column（含 truncated 标志）；② 返回对应列节点——「这个模板落在哪张表、哪个字段」类问题可答（M2-S1 验收句的显式端到端用例——#38 P1-8 补）。

### 4.6 TC-TAG 打标与实体召回

#### TC-TAG-01 ingest 同事务打标【集成｜M2-S3】

- **步骤**：① 正常摄取含「进项抵扣」的文档，查 `sem_chunk_entities` 与 chunks 事务性（造中途失败断言同回滚）；② mock AC 自动机抛错再摄取。
- **预期**：① tag 行与块写入同事务（index_fts 阶段）；② 摄取**不阻断**——记 warning，该文档块进入 retag 候选集（按 dict_rev 落后比对——「待重标」标记机制 design 未定义，附录 A-14 口径），交 semantic_retag 补做。

#### TC-TAG-02 semantic_retag【集成｜M2-S3】

- **步骤**：词典 r1→r2（别名增删）后跑 retag；观察优先级与限速。
- **预期**：仅 `dict_rev` 落后的块分批重标；任务优先级最低（不与 ingest 抢资源——写锁治理）；retag 后 dict_rev 字段更新。

#### TC-TAG-03 untag 与对账【集成｜M2-S3】

- 见 T-S10 展开；补充：对账任务独立造数残留行验证清理能力（兜底路径自身可测）。

#### TC-TAG-04 expand 召回关系集【单测｜M2-S3】

- **步骤**：`semantic.expand(ids, ENTITY_RECALL_RELS, depth=1)`——种子含被 10 场景 uses 的模板。
- **预期**：只沿 `refers_to/has_field/maps_to/related_to` 低扇出关系（**不沿 uses**——防召回发散）；结果 ≤50；1 跳。

#### TC-TAG-05 实体路 SQL 与 matched_entities【单测｜M2-S3】

- **步骤**：`search(entities=[E])`；构造种子命中与扩展命中两类块。
- **预期**：得分 = Σhits×（种子 1.0 / 扩展 0.5）；`k_entity` 默认 30；返回块附 `matched_entities`（agent 解释召回原因）；三路 RRF 融合进 rerank（§5.10 顺序不变）。

---

## 五、性能与评测

### TC-PERF 性能抽测

#### TC-PERF-01 按块 vs 按文档 ACL 计算【性能｜M0b】

- **口径**：同一授权展开函数两种写法（json_each 每块 / visible_docs CTE 按文档），**1/5 万块两档 P95（v1.5.2 修订——原 1/5/10 万三档，2026-10-24 用户拍板缩档：不搞大数据量；10 万档取消）**。
- **预期**：产出实验报告并选定路线（结论回写 schema v1.1——dims_json 去留在此定，design M0b.1）。

#### TC-PERF-02 向量同表 vs 分表【性能｜M0b】

- **口径**：chunks.embedding 同表 vs chunk_vectors 分表的回表耗时与 WAL 放大（~10KB/块——2560 维 float32，D12 修订）。
- **预期**：结论随 v1.1 迁移落（M0b.2）。

#### TC-PERF-03 SLO 压测【性能｜M1 标定+基线（v1.5.2——原 M0b 标定取消）】

- **口径**：N=5 并发、~10 万块，search P95 ≤2s（NFR-8）；预算表逐项：query 嵌入 ≤150ms / 双路召回 ≤300ms / rerank ≤1000ms / 其余 ≤200ms / LLM 增强 800ms 并行不计关键路径。
- **预期**：分项延迟埋点出数；超标触发双降级开关验证（TC-RET-06）。
- **修订（v1.5.2，2026-10-24 用户拍板：M0b 不压测、不搞大数据量）**：M0b 标定取消，NFR-8 正式标定随 M1 基线轮一并（与 TC-PERF-04 同轮执行）；本用例自 §六 M0b 验收对照行移除。requirements/design 正文的「M0b 压测」字样勘误登记归 M0b-3 勘误批次（正文冻结纪律）。

#### TC-PERF-04 rerank 并发与嵌入吞吐【性能｜M1】

- **口径**：rerank 并发信号量上限下的吞吐曲线；CPU 嵌入分批吞吐（块/分钟）。
- **预期**：出吞吐曲线支撑 M2 生产化容量规划（NFR-3 风险标定）。

#### TC-PERF-05 语义 P99【性能｜M2-S】

- **口径**：annotate 整体 P99 <20ms（AC 层 P99 <5ms）；get_entity depth=2 P99 <50ms（NFR-11）。
- **预期**：万级词典 + 高扇出图样本下达标；AC 自动机按 (org, dict_rev) 懒加载不重复构建。

### TC-EVAL 评测与门禁（docs）

#### TC-EVAL-01 M1 小型黄金集【评测｜M1】

- **口径**：20~50 条真实中英 query（待决-1 未到位前以合成/公开样例先行、验收顺延），人工标注 top-10；Recall@k / MRR 自算（集合运算、零 LLM）。
- **预期**：M1 检索调参（分词/权重/阈值）有度量依据——出基线报告（M1 验收）。

#### TC-EVAL-02 M3 完整黄金集【评测｜M3】

- **口径**：合成候选生成（评测框架选型 ragas——design §7 M3 依赖清单，#38 P2 标注为选型）双语 + 人工抽检修正；覆盖纯中/纯英/中英混排三态。
- **预期**：黄金集覆盖三态断言（M3 验收）。

#### TC-EVAL-03 judge 双语校准【评测｜M3】

- **口径**：~50 条人工双评 vs judge（内部网关）；一致率 / κ。
- **预期**：达阈值（阈值数值 M3 校准后定——附录 A-6）；judge prompt 双语。

#### TC-EVAL-04 deepeval 门禁【评测｜M3】

- **步骤**：人为注入一次检索层回归（如调坏权重）推 CI。
- **预期**：门禁**卡住**该回归（M3 验收原句）；正常变更不误报。

#### TC-EVAL-05 在线引用锚点抽样【观察｜M3】

- **口径**：agent 会话引用 chunk_id 存在性抽样打标（引用不存在 ID = 幻觉证据）。
- **预期**：抽样管道出数、比例记录（记录级）。

#### TC-EVAL-06 区分度误报抽查【评测｜M1】

- **口径**：flags 抽样人工复核误报率（M1 验收「区分度误报抽查」）。
- **预期**：绝对阈值经真实语料重标定后误报可控（记录结论支撑阈值调整）。

### TC-SEV 语义识别评测

#### TC-SEV-01 评测集构建规格【评测｜M2-S2】

- **口径**：150~200 条真实问法（工单/群聊/agent 日志），人工标注 span 与 entity_id；覆盖四类黑话、缩写、错别字、歧义词、负样本 ~20%。
- **预期**：集合格式与标注规范落仓库（每次构建自动运行的输入）。

#### TC-SEV-02 构建回归门槛【评测｜M2-S2】

- **口径**：每次 semantic_build 自动跑评测集；门槛：AC 层 precision ≥0.95 / recall ≥0.80；歧义消解 ≥0.85（只统计歧义样本）；负样本误报 ≤0.05。
- **预期**：指标进构建报告；较上版降 >2pp 不切 ready（TC-BUILD-04 联动；M2-S2 验收句）。

#### TC-SEV-03 检索增益评测【评测｜M2-S3】

- **口径**：docs 黄金集上开/关实体召回路对比 recall@10 与 MRR。
- **预期**：**不回退才允许 `auto_entities` 默认开启**，否则保持显式参数（M2-S3 验收句）；AC+模糊 recall@3 ≥0.92 一并断言。

---

## 六、里程碑验收对照（收尾逐条勾验）

| 里程碑 | 验收用例集（design §8 验收句 → 本文编号） |
|---|---|
| **M0a** | 孤儿行 IntegrityError：TC-SCAF-01（both）；MCP 带 chunk_id 检索（开发 JWT）：TC-E2E-06；编译器单测先行：T1~T5、T20、T22（+T23 触发器半）＋TC-ACL-01~07、TC-SCAF-02~05（后端行 v1.5.1 已回写 both——PG 等价随 M0b-1 spike 落地：断言落点 tests/test_pg_scaff.py、双臂参数化激活）；摄取/检索最小链：TC-ING-01~03/07、TC-FTS-01~03、TC-E2E-07、**TC-EMB-01~03（02 为 Plan 层谓词单测——检索行为随 M1 的 TC-EMB-07）**；鉴权骨架：TC-AUTH-01/02（组织上下文规则随待决-2/3 并行敲定——#38 P1-10 补）；**i18n 机制就位：TC-UI-01（切换/持久化/默认中文——静态页壳，v1.5/FR-8）** |
| **M0b** | **✅ 已完成（M0b-1/2/3 三段：PR #47/#48 及 v1.1 迁移 PR）**：TC-PERF-01（1/5 万两档）、TC-PERF-02、TC-E2E-05 + TC-SCAF-03（**v1.1 迁移跑通：0002 双方言 + foreign_key_check 空 + 存量向量搬运载荷保真 + M0a 可达矩阵子集复跑绿——test_v11_schema 21 用例**）；~~TC-PERF-03~~（v1.5.2 取消顺延 M1）；委托 token 客户端实测（TC-AUTH-04 附注）；PG spike 部分（M0b-1：编译器单测双后端绿 + backend 参数化 + TC-SCAF 后端行 both）；实验报告 benchmarks/report-m0b-2.md（三项拍板依据） | ~~实验报告 + v1.1 迁移跑通~~ **全部兑现** |
| **M1** | **✅ 已完成（M1-1~M1-5 五段：PR #50/#51/#52/#53/#54，mergeCommit fc1bcc8/aa19ea5/2da63ec/befff9e/87347c3——2026-10-28 收口；门禁 271→663+1 双后端双模式全程 0 skipped）**：**越权矩阵全绿 ✅**：T1~T23 全量 + TC-AZ-01/02/03/05 **双后端 348/348**（T13 以 dev 白名单模拟 ✅；**T19 删库半句、T20 退役审计半句随 M2 收口**——申报属实未跑，A-8 限定口径；矩阵报告 benchmarks/report-m1-5-matrix.md——v1.8 注：B-1① 裁定「双后端各跑」限定 DB/服务/MCP 层，REST-PG 留 M2〔P3-18 顺延口径〕）；版本链 ✅：T6~T10、T21、TC-VER-01~07、TC-E2E-02（M1-2）；**全量矩阵复跑 ✅**：TC-E2E-05 收口（test_v11_schema 21 用例双后端 + 门禁全量）；凭证 ✅：T11/T12、TC-CRED-01~05（M1-3）；检索配方 ✅：TC-RET-01~07、TC-E2E-01/04、TC-FTS-04（**REST 硬条件闭环——m1-1/m1-2 移交解除，M1-4**）、TC-ACL-08/TC-EMB-07；摄取补全 ✅：TC-ING-04~06、TC-EMB-04/05（M1-4）；鉴权 ✅：TC-AUTH-01/02 复跑；区分度 ✅：TC-QUAL-01~05（M1-4 区分度环，近邻查询过 ACL 防旁路）、TC-EVAL-06 ◐（机制面用例 ✅ + B② 合成语料抽样记录 benchmarks/report-m1-5-fp-review.md——coder 代行复核 12/41：词面路误报 11~12（同域小语料 IDF 稀释）/拥挤路零误报；真实语料人工复核待决-1 顺延 M2）；真实 query 标定 ✅：TC-EVAL-01 双后端基线（sqlite r@10=0.8929 / pg=0.7857——G-6 校准输入，M1-4 归档）；性能 ✅：TC-PERF-03 **SLO 基线出数（2026-10-27 裁定②口径）**——单请求四组合全达标（474~1191ms ≤2s）、PG 5万 N=5 并发 2443.2ms 超标**登记 known-gaps G-6 v1.2（M2 halfvec 索引化复测）**+ 双路召回预算缺口一并登记；TC-PERF-04 rerank 吞吐/嵌入吞吐曲线（benchmarks/report-m1-5.md）；**界面国际化走查 ◐ TC-UI-01~04——清单已备（benchmarks/report-m1-5-tc-ui-walkthrough.md），手动走查由用户执行（唯一待勾项，不阻塞 M1 完成态落笔——FR-8 手动走查类口径）**。勾验材料全链：benchmarks/report-m1-5-m1-checklist.md |
| **M2** | **◐ 进行中（m2-1 段已交付 2026-10-29：PR #2，mergeCommit `739bbf3`；门禁 663+1→753+1 双后端双模式全程 0 skipped，+90 用例）**：**杀 worker 不丢任务 ✅（m2-1）**：TC-TASK-01（心跳 5s/租约 60s/过期重认领 + 真实并发窗口——两执行器 barrier 竞争恰一人认领双臂）、TC-TASK-02（attempts≥3 failed 留原因 + 崩溃耗尽清扫）、TC-TASK-03（取消阶段边界停止/幂等不复活/按任务 target_version 落失败）、TC-TASK-04（OOM 只杀 worker/自动拉起——真实 subprocess）、TC-E2E-03（**杀进程演练半句 ✅ m2-1**：kill -9 → 租约重认领 → searchable_full；TC-VER-08 ✅ m2-1：tombstoned_at 基准〔0004 迁移〕+ 双臂回填断言）；另：m2-1 落地 maintenance 框架与三任务体（凭证回收/过期成员清理/tombstone 90 天清理）、tasks.target_version 列（0005）、worker 默认 subprocess（A 裁定全路径）。outbox 一致性：TC-OPS-01（m2-2）；恢复演练：TC-OPS-05（**双后端各一份——D24**）（m2-2）；跨组织隔离全绿：TC-OPS-09、T15、TC-AZ-04；批量导入 500 行（sync 不动）：TC-OPS-06 / T-CSV；生产化收口：TC-AUTH-03~05、T13/T16 生产形态、T19 删库 / T20 退役审计半句（m2-2）、TC-AZ-03 管理端点半（m2-3）、TC-OPS-02~04/07/08（m2-2/m2-3）、TC-TASK-05（M2-S1）、**TC-EMB-06（换模型重嵌入）（m2-3 管理面入口）**；TC-UI-02 管理面视图扩展（v1.5）（m2-3） |
| **M2-S1** | T-S2 / T-S3 / T-S5 / T-S6 / T-S11（describe_table）；「模板落在哪张表哪个字段」端到端：**TC-SEM-10**（模板链路）+ TC-SEM-05（search_entities / get_entity 结构契约）；同步流程：TC-SYNC-01~09（含 `sem_*` 迁移与种子）、T-S4（机制）；性能：TC-PERF-05（部分） |
| **M2-S2** | T-S1 / T-S4（验收）/ T-S12；AC precision ≥0.95 / recall ≥0.80、歧义 ≥0.85、负样本 ≤0.05：TC-SEV-01/02；构建回归 >2pp 不切 ready：TC-BUILD-04；YAML 与 CI：TC-YAML-01~04；annotate：TC-SEM-01~04/06/07、TC-BUILD-01~03/05 |
| **M2-S3** | 越权矩阵 T-S7 / T-S8 / T-S9 / T-S10 全绿；AC+模糊 recall@3 ≥0.92：TC-SEV-03、TC-SEM-09（含模糊索引产物）；检索增益不回退方可默认开启：TC-SEV-03；打标/召回：TC-TAG-01~05；故障隔离：TC-TASK-06 收口；中间件切换：TC-SEM-08、TC-YAML-05 |
| **M3** | 门禁卡住注入回归：TC-EVAL-04；judge 一致性达标：TC-EVAL-03；黄金集覆盖三态：TC-EVAL-02；在线锚点：TC-EVAL-05 |

---

## 附录 A：编写中发现的待澄清口径（建议走 issue / known-gaps 收口后再实现）

> 本附录是展开用例时对规格做「可操作性压测」的产物（pulse-pet TEST-CASES 评审先例）。不构成决策变更，均为口径补写级；其中 A-4/A-5 已有 known-gaps 条目（G-2/G-4）；A-7~A-16 为 #38 评审（v1.1）新增——**A-7/A-8/A-9 涉及正文回写，已开 [#39](https://github.com/yq3/lab/issues/39) 跟踪并随正文 v0.6.1 闭环**；A-17 为 #41 回写（v1.3）新增（→ G-6）。

- **A-1 T13 的 M1 可行性**：M1 验收要求矩阵 T1~T23 全绿，但可信子系统与 SSO 对接落地在 M2.2——本文按「M1 以 dev 白名单/静态 token 模拟跑通 T13、M2 生产形态收口」标注；T16 仅依赖配置开关（生产环境不注册路由），M1 直接可测、与 SSO 无关（#38 修订原「T13/T16」归类）；若排期口径不同需回写 design §8。
- **A-2 T15 的 403/404 分端点规则**：§9 只写「403/404」。本文按「404=存在性敏感读端点、403=明确越权写/管理端点」断言，实现时需把每个端点的选择固化进 API 文档。
- **A-3 dims_json 投影刷新范围（v1.6 注记——条款失效）**：~~PATCH 文档维度后刷投影的作用域……~~ **M0b-2 拍板①已删 dims_json（v1.1/0002）**——PATCH 直接写 `document_dimensions`（D6 语义不变），检索时聚合回填，投影刷新条款不复存在；本条留档勘误。
- **A-4 fuzzy 层触发者/消费者（= G-2）**：TC-SEM-09 按 FR-S3 现文写（`fuzzy=true` 才跑、结果只作候选）；M2-S3 实现前随 G-2 澄清修订（中间件注入一行低信任提示 or 工具描述引导 agent 自调）。
- **A-5 L0 dict_rev 刷新机制（= G-4）**：TC-SEM-06 只断言返回 dict_rev；刷新（轮询比对）机制随 M2-S3 定。
- **A-6 judge 一致性阈值数值**：需求只写「一致率/κ 过阈值」；TC-EVAL-03 待 M3 校准数据出来后定数并回写。

以下为 #38 评审（v1.1）新增：

- **A-7 `sem_rel_types` 的 org 语义（#38 P1-2）——已闭环（design v0.6.1 §4 设计说明⑥，#39）**：design §4 DDL 中 `sem_rel_types` 无 org_id（全局白名单配置表），与 §4 设计说明⑥「全部 `sem_*` 表带 org_id」表述冲突——T-S7 按「org 作用域表断言、排除 sem_rel_types」执行；正文已修正为「org 作用域六表带 org_id、`sem_rel_types` 除外」。
- **A-8 M1「T1~T23 全量」与半句里程碑冲突（#38 P1-4）——已闭环（design §8 / requirements §8 M1 验收句，v0.6.1，#39）**：design §8 / requirements §8 的 M1 验收写全量，但 T19 删库半句、T20 退役审计半句按里程碑属 M2——§六 M1 行按「除两半句（M2 收口）」标注；两处正文已补同款限定。
- **A-9 请求体权限字段：忽略 vs 拒绝（#38 P1-9）——已闭环（design §5.5 + requirements FR-4/D18 措辞统一，v0.6.1，#39）**：原 requirements「任何权限声明一律忽略」vs design「拒绝…请求体权限字段」并存——TC-AUTH-04 断言口径「**透传原始 token 拒绝；请求体权限字段忽略并记审计、请求正常处理**」已回写两份正文（含 requirements D18 决策行）。
- **A-10 annotate 入参超限处置（#38 P2）**：text >4000 字、context_entities >20 的「拒绝 vs 截断」未定——TC-SEM-07 暂按拒绝（400）断言，待实现固定后回写。
- **A-11 get_entity 超限处置（#38 P2；#40 P2 扩至 fanout_limit）**：design「服务端强制 ≤2」「fanout_limit ≤200」未定 clamp 还是拒绝——T-S6 暂按拒绝（400）断言（depth>2 与 fanout_limit>200 同口径），待实现固定后回写。
- **A-12 CSV 含 org 列且与路径一致（#38 P2）**：design 只写「列与路径不一致整批拒绝」，一致时未定——TC-OPS-06 暂按一律拒绝（CSV 不带 org 列）断言，待实现固定后回写。
- **A-13 PUT 超声明 size：截断 vs 拒绝（#38 P2）——✅ 已闭环（v0.9.4 回写，M1-3 实现固定为拒绝）**：design「按声明 size 截断/拒绝」二义已定**拒绝**（超声明 413、不足声明 400、不静默截断——design §6.2 v0.9.4 / FR-1 v0.9.4 已同步）；TC-CRED-02 拒绝断言即最终口径，无残留待办。
- **A-14 文档「待重标」标记机制（#38 P2）**：design 未定义字段/口径——TC-TAG-01 暂以「warning + 按 dict_rev 落后比对进入 retag 候选集」断言，待实现定义后回写。
- **A-15 org_admin 越权标注处置（#38 P2）**：§6.2 无审批端点——TC-AZ-01 暂按「org_admin 以自身授权内取值代标 + 审计」断言；若要走审批流属端点新增，需先补 §6.2。
- **A-16 restricted 无权尝试的审计口径（#38 P1-11）**：design §6.3⑥ 未细分——T-S9 暂按「持权访问入 outbox 权限事件；无权尝试走查询级异步审计（refused 可回溯）」断言，待实现确认。

以下为 #41 回写（v1.3）新增：

- **A-17 PG 后端 FTS 评分差异（→ known-gaps G-6）**：SQLite `bm25()` 与 PG `ts_rank` 评分函数不同，两后端 BM25 路排序**不逐字一致**——排序类断言按「名次集等价 / RRF 融合后 top-k 集合等价」口径执行（本文「口径」段已注）；黄金集分后端校准随 M1/M3 评测推进；若要求逐分一致属决策变更须先改 D24。

