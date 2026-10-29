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
- **0004（tombstoned_at）升级注意（M2-1，2026-10-28）**：新增列回填取
  **迁移执行时点**为存量 `tombstone=1` 行的 90 天清理起点（保守窗口——存量
  tombstone 实际延后清理，无提前删除风险）；升级后首 90 天内清理量低于理论值
  属预期。新切换事务即时写入 `tombstoned_at` 不受影响。
