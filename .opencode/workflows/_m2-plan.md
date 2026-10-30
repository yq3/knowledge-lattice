# M2 阶段任务分块总览与进度档案（supervised-coding 维护）

> **本文件不是任务检查点**——是 M2 阶段的段序总览/进度/挂账档案，供新会话恢复上下文用。
> 任务检查点仍按 `task-knowledge-lattice-m2*` 命名，本文件在协议 0a 扫描时与此文件互参。
> 拆分方案经用户确认（2026-10-28）；段序经用户确认（单会话串行）；**跨检查点会话隔离**经用户重申（2026-10-29：每检查点 Coder/Tester/Committer 全新会话，检查点内多轮才续接）。

## 一、M2 段序总表（用户确认的推荐段序）

主线 5 段（M2 生产化）+ 语义轨道 6 段（M2-S1~S3 各拆 2 段，D23 并行轨道——延期不阻塞主线）。

| # | 检查点 | 任务范围（一句话） | 依赖 | 状态 |
|---|---|---|---|---|
| 1 | task-knowledge-lattice-m2-1 | **M2.1** worker 子进程化（心跳/租约/重试/取消/子进程隔离/日志贯通）+ maintenance 调度框架与三任务体 + 写竞争治理 | 无（串行起点） | ✅ **done**（PR #2，mergeCommit `739bbf3`，2026-10-29 合入；门禁 663+1→753+1；4 轮） |
| 2 | task-knowledge-lattice-m2-2 | **M2.4+M2.5** 审计 outbox 一致性（同事务+崩溃注入+搬运）+ 月库滚动/封存/哈希链 + 删除级联（**T19 半句收口**）+ 备份恢复演练双后端 + outbox trim | m2-1 | ✅ **done**（PR #3，mergeCommit `27d2a17`，2026-10-29 合入；门禁 →825+1；3 轮） |
| 3 | task-knowledge-lattice-m2s-1 | **S1 基础**：`migrations/semantic/` 双方言 sem_* 全量 DDL + 触发器 + `sem_rel_types` 白名单种子 → SourceAdapter 协议 + template_center/metadata 适配器 → 同步流程（删除比例保护/missing 宽限期/分批 upsert/只写事实列/别名三 kind 重建/outbox 事件）。验收 **T-S2/T-S3** | m2-1（已满足） | ✅ **done**（PR #4，mergeCommit `428c67f`，2026-10-30 合入；门禁 →911+1；2 轮——B1/B2/B3 边界经用户拍板） |
| 4 | task-knowledge-lattice-m2-3 | **M2.3** 管理面 API + 最小 UI：§6.2 全端点（维度停用 dry_run/退役、授权 expires_at、任务取消、重索引含重嵌入入口〔TC-EMB-06〕、嵌入覆盖率面板、审计分级查询〔TC-OPS-03〕）+ grants 写路径 + CSV 批量导入〔TC-OPS-06〕+ 维度退役治理〔TC-OPS-07/T20 半句〕+ grants 替换〔TC-OPS-08〕+ 凭证吊销语义 + T17 owner 详情断言 | m2-1 | ⬜ **下一段（待开工）** |
| 5 | task-knowledge-lattice-m2s-2 | **S1 面上**：semantic_build 骨架（dict_rev 计算+原子切换）+ 首批三工具（get_entity 递归 CTE/search_entities/describe_table）+ REST 端点（sync/builds/sync-runs 管理）。验收 **T-S5/T-S6/T-S11** | m2s-1 | ⬜ |
| 6 | task-knowledge-lattice-m2s-3 | **S2 基础**：scenario_config/report_center 适配器 + YAML 仓库 schema/_schema/CI 校验/yaml_merge.py 合并规则/webhook 端点。验收 **T-S1** | m2s-1 | ⬜ |
| 7 | task-knowledge-lattice-m2-4 | **M2.2** SSO/JIT 对接（M0a 敲定协议）+ 委托 token/可信子系统（三约束+期限）+ RFC 8693 act 对象形态（m1-3 移交必须项） | 无硬前置（与 m2-3 有 token 交叉，顺序可调） | ⬜ |
| 7.5 | task-knowledge-lattice-m2-6 | **管理面补全与嵌入执行体**（2026-10-30 用户拍板新增——m2-3 R1 Committer 边界 1/2）：reindex/reembed **蓝绿执行体**（runner 认领、TC-EMB-06 越段项——原子切标签/旧标签清理/quality·semantic_build 重跑联动）+ members GET / values CRUD（含 D19 重新启用取值恢复路径）+ m2-3 P3 登记项（UI split 解析替换、read_org_audit 下沉、audit_chain 错误码等按需） | m2-3（已满足） | ⬜ |
| 8 | task-knowledge-lattice-m2s-4 | **S2 面上**：AC 自动机（pyahocorasick）+ L0 片段 + 构建报告 + annotate（四步消歧+context 短别名）+ 识别评测集 150~200 条与门槛。验收 **T-S4/T-S12** + precision≥0.95/recall≥0.80 | m2s-3 | ⬜ |
| 9 | task-knowledge-lattice-m2s-5 | **S3 基础**：concept/system 纯人工实体 + ingest 打标（同事务 tag/失败不阻断）+ semantic_retag（最低优先级）+ 版本切换/删块同事务 untag + 定时对账。验收 **T-S10** | m2s-4（词典质量稳定）+ m2-2（删除级联 untag 挂接点——已满足） | ⬜ |
| 10 | task-knowledge-lattice-m2s-6 | **S3 收口**：search(entities/auto_entities) 实体召回路（复用 §5.1 ACL 产物）+ 三路 RRF + matched_entities + 越权矩阵 T-S7/S8/S9 + 检索增益评测（不回退才默认开启）+ 模糊兜底（拼音/编辑距离/sem_vec）+ agent 中间件切换 +（可选）语义层视图。验收 **T-S7~S10 全 + AC+模糊 recall@3≥0.92** | m2s-5 | ⬜ |
| 11 | task-knowledge-lattice-m2-5 | **M2 验收收口段**（M1-5 形态）：跨组织隔离全绿（TC-OPS-09/T15/TC-AZ-04）、REST-PG 残项（P3-18 顺延）、**G-6 halfvec 索引化复测**（bench7 脚本已入库）、**G-8 真实模型 MRL+指纹阈值复验**、P3-7 quality 两遍流 hardening、真实语料人工复核（待决-1）、rerank 真实网关联调（环境依赖）、§六 M2 行总勾验 | 主线全部 + 语义轨道尽量 | ⬜ |

## 二、已完成段要点（新会话快速对齐）

- **m2-1**（worker 框架）：任务状态机 pending→leased→running→done|failed、心跳 5s/租约 60s/attempts≥3、取消按 `tasks.target_version`（0005 迁移）三处收口（cancel/耗尽清扫/失败路径 `_record_doc_error` 三分支守卫）、OOM 子进程隔离+自动拉起、`LATTICE_WORKER_MODE` 默认 subprocess（全路径）、maintenance 框架 + MAINTENANCE_BODIES 注册表、embed 回写防护确认。
- **m2-2**（审计/备份）：outbox 8 接入点同事务 + 崩溃注入同生共死；**搬运侧方言口径**（偏差①终态：写侧同事务双方言；搬运 sqlite 两步幂等/pg 单事务——TEST-CASES v1.8.3 已注）；哈希链**插入序**（sqlite rowid / pg seq 序列列）；封存 0444+sidecar / pg seals 表；12 月保留 + **outbox trim**（边界②用户拍板纳入）；T19 RESTRICT 收口（DatasetNotEmptyError→409）；备份双后端（`store/<dialect>/backup.py` + `data/backups/` 固定路径 + BackupToolUnavailable/Error 两态）+ 演练 `benchmarks/dr_ops05_drill.py`；RUNBOOK §4。
- **m2s-1**（语义轨道基础段，PR #4）：sem_* 七表+双触发器+白名单种子（三处一致=代码常量↔种子↔触发器+第四面 DDL CHECK==常量断言）；SourceAdapter 协议（fetch 全量快照、不做增量）+template_center/metadata 适配器（metadata 只拉被引用面、per-org fail-closed）；同步流程（删除比例保护 per-source active 基数+**force 放行**〔B2 拍板——?force=true+semantic:admin+outbox forced〕、分批 ≤1000、只写事实列、missing 宽限 7 天→retired 关系联动〔顺序：宽限推进在关系 upsert 后——防悬挂〕、别名三 kind、conflicts 明细、semantic.sync 入 outbox）；semantic_sync 任务类型（worker 分发+inline 兜底认领〔R2 P2-2〕）+REST 三端点；迁移 0006（含 tasks.payload）；跨批 parent_id 三级解析（R2 P2-1——批内映射→批间缓存→库内回查）。
- **门禁基线**：**911+1 双后端双模式 0 skipped**（pg 臂 329；825→886→911 两段累计 +86）。
- **分支基线**：origin/develop = `428c67f`（2026-10-30）。

## 三、挂账清单（新会话必读）

**工作区未入库（随下段 chore 归档批入库）**：
- `docs/TEST-CASES.md` v1.9.2（§六 M2-S1 行 m2s-1 段完成态+v1.9.1 两处日期勘误——supervised-coding 已落笔工作区）
- `AGENTS.md` 状态行更新 + 本文件 `_m2-plan.md` 进度更新 + `task-knowledge-lattice-m2s-1.md` 终态（若 M 未入库）

**用户侧待办（不阻塞开发）**：
- TC-UI-01~04 手动走查（M1 里程碑达成宣告唯一待勾——清单 `benchmarks/report-m1-5-tc-ui-walkthrough.md`）

**m2-2 移交 m2-3 收编（B1~B6，其检查点遗留事项节为权威）**：
- B1 upload.reclaim 等字面量事件常量；B2 审计读路径 prev_hash 链遍历；B3 审计月库纳入备份（sqlite snapshot 现仅主库+objects）；B4 stats 新键 audit_outbox_trimmed 同步运维面板；B5 R1 期行语义列 detail_json 兜底口径；B6 last_row_hash NULLS 防御分支修正（ASC 或 WHERE seq IS NOT NULL）+ 显式 NULL seq 探针
- C 组记录不修（P3-4/6/7/9/10/14/16 + P3-新④⑥——按所属段处理）

**known-gaps 本阶段新增**：G-15（关系级消失——M2-S3 承接）、G-16（触发侧两事务 create_task audit= 收口——M2-S2/S3）、G-13（m2-3 审计读路径对冲）、G-14（RUNBOOK §4.2 已注）、G-6 halfvec 复测 + G-8 真实模型复验（挂 m2-5）。

**m2s-1 移交 m2-2 收编**（其检查点遗留事项节为权威）：P3-r1 force 失败路径 run 侧审计 forced 语义（并入 G-16 收口）；P3-r2 force 覆盖 guard 时 stats 补 guard 明细；P3-r3 跨批回归测试加固（JOIN 捕非 template 指向+父转 missing/悬挂父场景固化）；P3-r4 fail-fast API 覆盖面+工厂 docstring；P3-r5 config 校验错误前缀文案。

**m2s-1 移交 m2-3 收编**：B 组（m2-2 移交的 B1~B6 审计/管理面项——其检查点遗留节为权威）+ P3-r6 已随 v1.9.2 勘误清偿。

## 四、AGENTS.md 状态行（已同步更新指针）

AGENTS.md §1 项目状态行已更新为「M2 进行中（m2-1/m2-2 已交付）+ 指向本文件」——新会话第一读即达。

## 五、下一段开工指引（m2-3）

1. 按协议 0 建检查点 `task-knowledge-lattice-m2-3`（模板 `_template.md`；createdAt 取真实时间）
2. 任务书要点：design §8 M2.3 + §6.2 管理面端点全集 + TEST-CASES TC-OPS-03/06/07/08、T20 半句、TC-EMB-06（重嵌入入口——m2-1 worker 已有任务类型，本段接 API 面）、T17 owner 详情断言、凭证吊销语义；最小 UI（web/ 薄壳——prototype 双基准）
3. 承接：**m2-2 移交 B1~B6**（其检查点遗留事项节为权威——upload.reclaim 常量/审计读 prev_hash 链遍历/审计月库纳入备份/stats 新键/R1 期行 detail_json 兜底/last_row_hash NULLS 防御）；C 组记录项按所属段处理；G-13 对冲（审计读路径按 prev_hash 遍历）随 B2 落
4. 会话隔离：全新 Coder/Tester/Committer 会话；分支先 ff 至 origin/develop=428c67f
5. 硬约束：门禁 911+1 起零回归；coder 禁改 docs/；chore 归档批带上 §三工作区 docs（TEST-CASES v1.9.2/AGENTS.md/_m2-plan.md/m2s-1 检查点）

## 六、维护规则

- 每段 done 后：更新 §一 状态列 + §二 要点 + §三 挂账（含来源检查点勾选回写）；本文件随下段 chore 归档批入库
- 段序调整须用户确认后落本表
- 本文件与检查点冲突时以检查点为权威（本文件是导航层）
