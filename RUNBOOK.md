# knowledge-lattice 运维 Runbook（M0b-3 起）

> 代码仓内的运维手册（docs/ 属设计冻结区——本文件为运行侧活文档）。
> 依据：`benchmarks/report-m0b-2.md`（三项拍板实验报告）、`docs/design.md` §5.3、
> schema v1.1 迁移（`store/<dialect>/migrations/docs/0002_schema_v1_1.sql`）。

## 1. 重嵌入蓝绿 Runbook（拍板 3——方案二：分表蓝绿，功能零降级）

> 形态依据报告 §3.5（v1.1 分表建议表）+ §3.3（蓝绿四相位实测）；完整流程与管理面
> 入口归 M2——本节登记 schema 就位后的手工操作序列。核心物理前提：
> `chunk_vectors(rid, embed_model, embedding)` **PK(rid, embed_model)**——同 rid
> 多标签并存可插（仅 PK(rid) 的新标签写入即 IntegrityError，bench2
> `probe_pk_rid_conflict` 双后端实测；门禁内等价探针见
> `tests/test_v11_schema.py::test_pk_rid_only_conflict_probe`）。

相位序列（每相位 SQL 仅为示意，标签 `model:dim` 形态——D12）：

1. **新标签写入（并存期开始）**：以新标签 `new:2560` 走摄取同款路径
   （`mark_embedding_batch(doc, ver, "new:2560")` → 嵌入 → `write_embeddings`）——
   INSERT `chunk_vectors`，旧标签行零触碰、持续服务（功能零降级）。
   - 存量文档批量：管理面入口随 M2（M0b-3 手工形态=逐文档重摄取或批量任务脚本）。
2. **覆盖率观测**（分子/分母口径闭合——都限定在用块）：
   ```sql
   -- 分子：新标签已回写的在用块数
   SELECT count(*) FROM chunk_vectors cv
   JOIN chunks c ON c.rid = cv.rid
   WHERE cv.embed_model = 'new:2560'
     AND c.tombstone = 0
     AND c.version = (SELECT d.active_version FROM documents d WHERE d.id = c.doc_id);
   -- 分母：在用块总数（同一限定口径）
   SELECT count(*) FROM chunks c
   WHERE c.tombstone = 0
     AND c.version = (SELECT d.active_version FROM documents d WHERE d.id = c.doc_id);
   ```
   两值相等即覆盖率 100%（**不要**用裸 `SELECT embed_model, count(DISTINCT rid)
   FROM chunk_vectors GROUP BY embed_model` 对比——分母含 tombstone/旧版本块，
   会把覆盖率低估、误判未到 100%；重嵌入任务按 pending 维度认领，不含旧版本块）。
   - 共存窗口读代价（知情申报，报告 §3.3）：sqlite 零放大；pg 精确扫描需过双倍行页
     （P50 +6% / P95 +18% 量级，跑间波动带 -3%~+52%）。
3. **原子切 current_model**：配置标签翻转（`LATTICE_EMBED_MODEL` / config）——
   零 SQL、瞬时生效（§5.8 dict_rev 同款模式）；向量路谓词
   `cv.embed_model = :current_model` 只命中新标签（TC-EMB-02）。
4. **旧标签延后清理（低峰）**：`DELETE FROM chunk_vectors WHERE embed_model = 'old:2560'`
   ——窗口自主；实测（5 万块档）：sqlite 清理 WAL 仅 ~4.3MB；pg DELETE 记满量死元组
   （~552MB WAL 量级）。
5. **空间回收（仅 pg 需要）**：`VACUUM chunk_vectors`——**plain VACUUM 不归还 OS**
   （空页在文件前段、页内复用消化；实测高水位 1257.8MB 不降）。需归还 OS 时
   `VACUUM FULL`（锁表）或 pg_repack；存储不紧则跳过（后续写入复用空页）。

回退：切换点前后任一时刻可把 config 标签翻回 `old:2560`（旧标签行仍在）——
蓝绿双向可退。若已执行相位 4 清理则不可退（重嵌入重来）。

sqlite 侧 `chunks.embed_model` 为摄取状态标签：重嵌入批次结束、覆盖率 100% 后，
新批次标签即当前 config 标签（`mark_embedding_batch` 钉标签机制不变）；旧标签
残留行不影响检索（谓词在 `chunk_vectors` 侧）。

## 2. 审计分区回溯（R2-P3-8——deploy 场景注记）

`ensure_month_partition`（`store/postgres/audit.py`）只滚**当月/调用时点月份**分区。
deploy 场景注意：

- **月中上线**的存量部署：上线前的历史月份分区未建——历史 `audit_events` 行不存在
  （新库无回溯需求）；若需要为**历史月份预建分区**（合规导出/对账），须显式按月调用：
  ```python
  from datetime import UTC, datetime
  from knowledge_lattice.store.postgres.audit import ensure_month_partition
  ensure_month_partition(conn, when=datetime(2026, 9, 1, tzinfo=UTC))  # 逐月回填
  ```
- 回填的每个分区都会显式落 `BEFORE TRUNCATE` 触发器（PG 16 父表 statement 触发器
  **不克隆分区**——分区必须逐个落，M0b-1 R2 P2-4 实测注记）：TRUNCATE 任何分区
  都会被拦（append-only 红线）。
- **不要**以 TRUNCATE + 重导的方式"修正"审计分区数据——append-only 触发器会拒绝
  （设计即如此；数据修正走追加补偿事件）。

## 3. 迁移注意事项（migrate）

- 双方言迁移框架：sqlite `user_version` / PG `schema_migrations`——版本只前进、
  幂等重放无副作用、失败整事务回滚（含 DDL）；乱序补入小编号迁移 fail-fast。
- **PG 并发启动**：`schema_migrations` 建表在 advisory lock 之外，并发 fresh 连接
  同跑的 CREATE TABLE IF NOT EXISTS 非原子——**真实竞态为 pg_type 唯一键冲突
  （UniqueViolation 23505，主形态）间或 DuplicateTable（42P07）**，由
  DuplicateTable/UniqueViolation 双捕获 + 复核在场分支兜底（M0b-3 P3-6，R2 收口）；
  迁移应用本身经事务级 advisory lock 序列化——双进程并发迁移一者应用、另一者
  锁内重读后干净跳过。
- **sqlite 迁移窗口**：`PRAGMA foreign_keys=OFF` + 事务末 `foreign_key_check`
  ——结束（含失败路径）恢复 `foreign_keys=ON`；**成功路径下恢复失败会记
  WARNING 日志**（`knowledge_lattice.store.sqlite.migrate` logger——连接已坏等
  场景，需人工核对连接态）。
- v1.1（0002）迁移内做了存量向量搬运（`INSERT..SELECT` chunks→chunk_vectors），
  空库/有库两形态均可跑；搬运幂等性由版本记录保证（已应用不重放）。
- **0004（tombstoned_at）升级注意（M2.1，2026-10-28）**：新增列回填取
  **迁移执行时点**为存量 `tombstone=1` 行的 90 天清理起点（保守窗口——存量
  tombstone 实际延后清理，无提前删除风险）；升级后首 90 天内清理量低于理论值
  属预期。新切换事务即时写入 `tombstoned_at` 不受影响。
- **0005（target_version）存量行为注记（M2.4 m2-2，2026-10-29）**：迁移前的
  存量任务行 `target_version=NULL`——取消（cancel）与崩溃耗尽清扫
  （fail_exhausted_tasks → fail_document_version）对 NULL 行**只落任务行
  failed、文档侧不触碰**（可能残留 `pending_status='parsing'` 文档——需人工
  核对或重传新版本）；执行侧 `run_task` 对 NULL 行回退 `_effective_version`
  （文档当前有效版本——M1 口径）。新任务（0005 后创建）恒写目标版本，无此窗口。

## 4. 备份恢复 Runbook（M2-2 起，D24 双后端各一份）

> 依据：design §2 NFR-10（RPO ≤24h / RTO ≤4h——POC 目标）、TC-OPS-05、
> `benchmarks/report-m2-2-ops05.md`（恢复演练实测）、known-gaps G-5/G-13/G-14。
> 自动化形态：maintenance 任务族 `backup_snapshot` 任务体（节流
> `LATTICE_BACKUP_INTERVAL_S` 默认 86400s = RPO 口径）。

### 4.1 SQLite 后端（VACUUM INTO）

```bash
# 快照（主库 + objects + 审计月库 一并）——maintenance backup_snapshot 任务体周期执行
#   产物目录：data/backups/（固定路径，无独立配置项；G-5 快照目的地缺口维持登记）
#   产物清单（m2-3 B3 起）：lattice-snap-<ts>.db + objects-<ts>.tar + audit-months-<ts>.tar.gz
#   产物：lattice-snap-<ts>.db（主库 VACUUM INTO）+ objects-<ts>.tar
# 手动等价（脚本 benchmarks/dr_ops05_drill.py 演练同款路径）
#   sqlite3 data/lattice.db "VACUUM INTO 'data/backups/lattice-snap.db'"
#   tar -cf data/backups/objects.tar -C data objects

# 恢复（新环境）
#   1) 释放快照与 tar 至目标 data/ 目录
#   2) 启动服务（迁移框架自动对齐——user_version 只前进，快照已含则幂等跳过）
#   3) 抽查：检索一组关键词 + 越权矩阵子集（演练脚本内建）
```

- **审计月库 `audit_YYYYMM.db` 备份口径（G-13 关联；v2 随 m2-3 B3 更新）**：自动快照
  **已含月库**——sqlite 备份产物为 `audit-months-<ts>.tar.gz`（全部 `audit_*.db`
  + `-wal/-shm` + `*.seal.json` sidecar；月库 append-only 独立文件、tar 安全），
  恢复时解包回 data/ 后按 prev_hash 链遍历读路径自动纳管。pg 侧月库分区随
  pg_dump 全量覆盖。~~自动快照不含月库文件~~（m2-2 遗留 B3 已于 m2-3 收编）。
- 恢复产物上做**链验证须按 prev_hash 链遍历**，不要依赖 rowid 读序
  （G-13：rowid 跨 VACUUM 不保证保留）。

### 4.2 PostgreSQL 后端（pg_dump）

```bash
# 快照（自定义格式 -Fc；容器形态经 LATTICE_PG_DUMP_CMD 注入）
LATTICE_PG_DUMP_CMD="docker exec lattice-pg pg_dump"   # .env 注入示例
#   实现形态：pg_dump --format=custom --no-owner --no-privileges [-d DSN]
#             经 stdout 流写 data/backups/lattice-pg-<ts>.dump（-f 直写非实现路径）
#   objects 目录同 sqlite（tar）

# 恢复（新库——需 pgvector 预装）
#   1) CREATE EXTENSION vector;                    -- 前置（镜像需含 pgvector 0.8.x）
#   2) pg_restore -d $NEW_DSN /backup/lattice-<ts>.dump
#   3) 启动服务（schema_migrations 框架幂等对齐）+ 检索/矩阵抽查
```

- 分区审计表与主库同库——dump 天然包含；`--no-privileges` 使封存分区的
  REVOKE 不随恢复迁移（sealed 触发器仍在，纵深少一层——恢复后如需收紧
  手动补 REVOKE）。
- **seq 列首次部署窗口（G-14）**：升级到 M2-2+ 版本后，**先单独跑一次连接
  工厂初始化（或任意单连接启动）再放开并发服务**——`audit_events` 分区的
  seq 列首次 ensure 触发全表 rewrite（ACCESS EXCLUSIVE，POC 量级亚秒级）。
- DSN 含密码经 argv 传递对 `ps` 可见（m2-2 遗留 P3-14，记录）——高安全
  环境可用 `.pgpass`/`PGPASSWORD` 环境变量方式部署。

### 4.3 备份失败可发现性

- 工具**缺失**（pg_dump 不在 PATH/容器）→ maintenance stats 记
  `backup_snapshot: "unavailable: …"` + WARNING 日志、任务 done（部署面
  显式状态）。
- 工具**在但失败**（DSN 错/磁盘满）→ 任务 **failed**（error 前缀
  `backup_snapshot`）——任务列表/日志可发现，`data/backups/` 快照产物异常
  应纳入例行巡检。
