# TC-OPS-05 备份快照与恢复演练报告（m2-2 / M2.5 / NFR-10）

> 演练脚本：`benchmarks/dr_ops05_drill.py`（双臂可复跑）；测试门禁内回归：
> `tests/test_ops_05_backup.py`（快照/恢复/前进/节流双后端参数化）。
> 执行环境：macOS（开发机）+ docker `lattice-pg`（PG 16 + pgvector 0.8）；
> pg 备份工具走容器形态（`docker exec lattice-pg pg_dump`——本机无 PATH pg_dump，
> `LATTICE_PG_DUMP_CMD` 注入口径，.env.example 已登记）。

## 一、演练链路与结果（2026-10-29）

### sqlite 臂（VACUUM INTO）

| 步骤 | 耗时 | 结果 |
|---|---|---|
| 造环境（迁移 + 矩阵造数 + 真实上传摄取至 searchable_full） | 3.674s | ✓（active_status=searchable_full） |
| 快照（VACUUM INTO 主库 + objects tar.gz） | 0.016s | ✓ `lattice-*.db` + `objects-*.tar.gz` |
| 新环境恢复（快照文件拷贝为库 + tar 解包对象目录） | 0.001s | ✓ 对象字节一致 |
| 跑迁移（幂等重放）+ user_version | 0.014s | ✓ applied=[]（无待应用）、user_version=5 保持 |
| 抽查检索（FTS 召回「土地/增值税」命中）+ 矩阵子集（u_cn 维度 ACL 可见集 = {d_multi, drill 文档}，v1.1 有值交集口径）+ 数据对账（docs=6 / tasks=1） | 0.019s | ✓ |

### pg 臂（pg_dump -Fc / pg_restore）

| 步骤 | 耗时 | 结果 |
|---|---|---|
| 造环境（独立 schema + 迁移 + 矩阵造数） | 0.035s | ✓ |
| 快照（pg_dump --format=custom --schema=<drill>) | 0.138s | ✓ custom format dump |
| 新环境恢复（CREATE DATABASE + **CREATE EXTENSION vector（恢复环境前置）** + pg_restore stdin 流） | 0.214s | ✓ |
| 跑迁移（幂等）+ schema_migrations | 0.012s | ✓ applied=[]、版本记录 5 条齐备 |
| 抽查检索（tsvector 五列 GENERATED 随 dump 恢复，FTS 召回命中 4 条）+ 矩阵子集（u_cn 可见集 = {d_multi}） | 0.008s | ✓ |

### 「user_version / schema_migrations 前进」半句

门禁用例 `test_sqlite_restore_advances_user_version`：构造停在 0004 的旧版本库
→ 快照 → 恢复 → `migrate_db` 实际应用 0005（applied=[5]）、`user_version` 前进
到最新、`tasks.target_version` 列在场——「旧版本快照恢复 + 迁移前进」语义闭环。

## 二、结论

- **恢复后数据完整**：文档/块/任务/维度全量随快照恢复，对象目录字节一致；
- **检索正常**：双方言 FTS 召回命中（sqlite FTS5 / PG tsvector GENERATED 均随
  快照恢复，无需重建）；
- **迁移幂等 + 版本前进**：已最新库恢复后零待应用；旧版本库恢复后前进到最新。

## 三、RPO / RTO 口径记录（POC 目标：RPO ≤ 24h / RTO ≤ 4h）

- **RPO ≤ 24h**：快照任务挂 maintenance 任务族（`backup_snapshot` body），
  `LATTICE_BACKUP_INTERVAL_S` 默认 86400s（=24h）节流——每日至少一份快照，
  最坏丢失窗口 ≤ 24h；目标如需更小 RPO，调小该值（受快照耗时与存储约束）。
- **RTO ≤ 4h**：演练实测恢复动作（拷贝/restore + 迁移 + 校验）秒级（POC 量级
  数据）；RTO 预算的绝大部分是**人工流程**（取快照、起服务、验证）——运维手册
  （RUNBOOK 备份恢复节，supervised-coding 落笔）承载操作序列，本报告供演练数据。
- **快照目的地缺口（G-5）**：POC 快照落 `data_dir/backups`（与数据同盘——
  **单盘故障同灭**）；异机/对象存储目的地维持 known-gaps G-5 登记待后续段收口。

## 四、pg 恢复环境前置条件（部署口径）

1. 目标库预装 pgvector（`CREATE EXTENSION vector`——dump 的
   `chunk_vectors.embedding` 依赖 vector 类型，恢复第一步）；
2. 备份工具经 `LATTICE_PG_DUMP_CMD` / `LATTICE_PG_RESTORE_CMD` 注入（容器形态
   `docker exec [-i] lattice-pg pg_dump|pg_restore`；本机安装则 PATH 直取）；
3. pg_dump 走 stdout 流、pg_restore 走 stdin 流——不经容器文件系统（跨部署
   形态统一）。
