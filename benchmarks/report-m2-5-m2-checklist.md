# m2-5 §六 M2 行勾验材料（A9——供 supervised-coding docs 批落笔；coder 禁改 TEST-CASES）

> 核对对象：TEST-CASES §六 **M2 行**（含 M2-S1/S2/S3 行）完成态。本材料逐项
> 给出「验收句 → 证据指针」；完成态落笔归 supervised-coding。

## 一、本段（m2-5）清偿的 M2 行验收句

| §六 M2 行验收句 | 本段证据 | 建议落笔 |
|---|---|---|
| **「跨组织隔离全绿：TC-OPS-09、T15、TC-AZ-04（m2-5 收口段）」** | `tests/test_az_matrix_m25.py`（R2：9 用例 × 双后端）+ `tests/test_orgs_admin.py`（R2：11 用例，store 级含 pg 专项）——**29 passed / 0 skipped**（R2 2026-11-02 口径；R1 为 9 用例 24 passed/35 端点——已按 P2-3/P2-4 修订）；矩阵报告 `benchmarks/report-m2-5-matrix.md`（扫描面 **37 端点**〔非实现全集，未扫 4 条注记〕= 34×403+1×401+2×403 + 三组织行集边界 + TC-AZ-04①~④ 全链 + T15 真实路由 404）。**附注**：TC-AZ-04② 载体端点 `GET/POST /api/orgs`（design §6.2 L1121）为本段实装（此前缺——新组织首任 org_admin 死锁） | ✅ 全绿（含 REST-PG 残项补齐声明——矩阵报告 §四口径申报） |
| M2-S1 行「剩余：TC-PERF-05 → m2-5 承接」 | `benchmarks/perf_m2_5.py` + `report-m2-5-perf05.md`（**R2 修订——真实边图**）：**全项达标**（annotate 整体 P99 0.029~0.054ms <20ms / AC 层 0.004~0.011ms <5ms / get_entity depth=2 **表扇出 300 列@200 截断 16.301ms**〔truncated=True〕/ 模板 uses< 入向 0.574ms <50ms / 万级词典 10,312 实体+25,624 别名 + 关系 310 条真实入图 / 懒加载同实例断言 true；P99 稳态口径、fuzzy 懒构建首调 3742ms 单列〔边界②裁定 docs 批注记〕） | ✅（M2-S1 行剩余项清偿） |
| M2-S3 行「TC-PERF-05 → m2-5」 | 同上 | ✅（M2-S3 行剩余项清偿） |
| m2-6 移交「B① 3/4——逐行过期编辑→m2-5/TC-UI 批」 | web/ 逐行独立 expires_at 输入（`input.chip-exp` per-key——唯一真值源 `accessState.expires`；未编辑行沿用库内值〔R3 P2-2 语义由初始值承载〕；全局输入框降级为新选行预填源）+ playwright DOM 三断言（初始值=库内 expires / 逐行独立编辑互不影响+新选行预填 / 保存后读回逐行值正确）+ langchange preserve；**非门禁面**（TC-UI 手动走查批——m2-6 Committer 裁定口径维持） | ✅ 4/4（B① 收口；TC-UI-01~04 manual 走查仍待用户——维持） |

## 二、本段新增（M2 行可补注记的非决策变更材料）

| 项 | 证据 |
|---|---|
| G-6 halfvec 复测 + 真实模型基线 | `benchmarks/report-m2-5-g6-halfvec.md`（**R2 修订**：①bench5 形态全链 search N=5 P95 **1361.6ms PASS**——与 M1-5 真值 2443.2ms 同口径对照未复现〔-44%，两数据并列保留〕；②bench8 召回段 halfvec 不引入建议〔LIMIT64 overlap 0.12~0.56——合成向量局限申报；全链 halfvec 档未测〕；③真实 r@10 0.93/1.00 双后端〔28-query 分辨率限定——不关闭 G-6 重开条件〕）+ known-gaps G-6 回写材料 |
| G-8 MRL/阈值百炼实测 | `benchmarks/report-m2-5-g8-real-model.md`（截断**本集分辨率内未观测到损失**〔28 query ≈3.57pp 分辨率——M3 完整集复标〕 + 60 样本抖动全 1.0 维持 0.99/0.95） |
| rerank 百炼联调 + 配置切换收口（P3-14 激活） | 同上 ③（gte-rerank-v2 契约实证+provider 入仓+**top_n parameters 放置修正**〔R2/P3-7——探测生效+provider 修正+live 复跑 respected=True〕）；`tests/test_emb_08_dashscope.py` 11 用例；`.env.example` rerank 段 |
| G-24③④⑤ 收口 | `report-m2-5-perf05.md`（③vec 档超时/熔断/审计 + ④懒构建/零复制〔万级 3.75s→AC 路径零；R2 补并发时序 Lock+哨兵赋值序——8 线程首建恰 1 次〕 + ⑤vec_top 参数化〔R2 用例改实参捕获——恒真根除〕）；`tests/test_sem_g24_hardening.py` 16 实跑 |
| P3-7 quality 两遍流 hardening | `tests/test_qual_07_hardening.py`（non-finite 防御 + 池缩水有效列均值——4 用例双后端） |
| m2-4 followups ④⑤ | ④`_outbox_integrity` 专用错误（`tests/test_auth_03_sso_jit.py` 增——双后端）⑤MCP 忽略审计移 resolve_org 后（`tests/test_auth_02_org.py` 增 2 用例） |
| 待决-1 / 真实 IdP 受阻申报更新 | `benchmarks/report-m2-5-blocked.md`（不虚造——known-gaps 回写材料） |

## 三、M2 行整体完成态核对（供落笔判断——R2 按 P2-5 改口径）

- M2 主线 6 段（m2-1~m2-6）+ 语义轨道 6 段（m2s-1~m2s-6）全部交付；
- 本段（m2-5）后 M2 行**验收句已全部清偿**（跨组织隔离全绿 ✓ / TC-PERF-05 ✓
  / B① ✓）——**但 ≠ 端点全集实现**：design §6.2 表列明而实现缺失的
  **5 个方法组合 backlog**（GET /members、POST /datasets、PATCH
  /datasets/{id}、POST /dimensions、PATCH /dimensions/{id}——历史缺口非
  本段引入；R1→R2 边界裁定①a：不实装、issue 登记 + docs 批实现状态注记、
  M3 管理面补强批处置）；另 design 无 GET 单维度/GET 单取值端点
  （T15 载体相关——同 backlog）；
- 残留（维持既有登记，非 M2 验收句）：TC-UI-01~04 manual 走查待用户执行
  （FR-8 手动走查类口径）；G-22 查询级审计（T-S9⑥）/G-23 残余/G-24 余项——
  均为 known-gaps 登记级（M3/独立批）；
- 门禁：R1 基线 1651+1 → R1 **1708+1**（+57 = az_matrix 18 + orgs 6 +
  emb_08 11 + sem_g24 14 + qual_07 4 + auth_02 +2 + auth_03 +2）→ R2
  **1715+1**（+7 = orgs_admin 5〔必填 1+空值 3+pg store 竞态 1〕+
  sem_g24 thread_safe 2〔双后端〕）；双后端双模式 0 skipped，pg 臂 guard 633
  （[pg] 参数化 599 + PG 专用 34）全实跑（注：test_orgs_admin 的 pg_db 专项
  不在 guard 计数内但实际执行计入 1715——pg-only 全实跑）。
