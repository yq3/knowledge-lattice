# m2-5 §六 M2 行勾验材料（A9——供 supervised-coding docs 批落笔；coder 禁改 TEST-CASES）

> 核对对象：TEST-CASES §六 **M2 行**（含 M2-S1/S2/S3 行）完成态。本材料逐项
> 给出「验收句 → 证据指针」；完成态落笔归 supervised-coding。

## 一、本段（m2-5）清偿的 M2 行验收句

| §六 M2 行验收句 | 本段证据 | 建议落笔 |
|---|---|---|
| **「跨组织隔离全绿：TC-OPS-09、T15、TC-AZ-04（m2-5 收口段）」** | `tests/test_az_matrix_m25.py` 9 用例 × 双后端 = 18 实跑 + `tests/test_orgs_admin.py` 6 用例——**24 passed / 0 skipped**（2026-11-01，PG 16.15 容器）；矩阵报告 `benchmarks/report-m2-5-matrix.md`（扫描面 35 端点含 M2 新增全集 + 三组织行集边界 + TC-AZ-04①~④ 全链）。**附注**：TC-AZ-04② 载体端点 `GET/POST /api/orgs`（design §6.2 L1121）为本段实装（此前缺——新组织首任 org_admin 死锁） | ✅ 全绿（含 REST-PG 残项补齐声明——矩阵报告 §四口径申报） |
| M2-S1 行「剩余：TC-PERF-05 → m2-5 承接」 | `benchmarks/perf_m2_5.py` + `report-m2-5-perf05.md`：**全项达标**（annotate 整体 P99 0.048~0.063ms <20ms / AC 层 0.004~0.010ms <5ms / get_entity depth=2 0.034~0.041ms <50ms / 万级词典 10,312 实体+高扇出 / 懒加载同实例断言 true） | ✅（M2-S1 行剩余项清偿） |
| M2-S3 行「TC-PERF-05 → m2-5」 | 同上 | ✅（M2-S3 行剩余项清偿） |
| m2-6 移交「B① 3/4——逐行过期编辑→m2-5/TC-UI 批」 | web/ 逐行独立 expires_at 输入（`input.chip-exp` per-key——唯一真值源 `accessState.expires`；未编辑行沿用库内值〔R3 P2-2 语义由初始值承载〕；全局输入框降级为新选行预填源）+ playwright DOM 三断言（初始值=库内 expires / 逐行独立编辑互不影响+新选行预填 / 保存后读回逐行值正确）+ langchange preserve；**非门禁面**（TC-UI 手动走查批——m2-6 Committer 裁定口径维持） | ✅ 4/4（B① 收口；TC-UI-01~04 manual 走查仍待用户——维持） |

## 二、本段新增（M2 行可补注记的非决策变更材料）

| 项 | 证据 |
|---|---|
| G-6 halfvec 复测 + 真实模型基线 | `benchmarks/report-m2-5-g6-halfvec.md`（bench8 数据 + 真实 r@10 0.93/1.00 双后端）+ known-gaps G-6 回写材料 |
| G-8 MRL/阈值百炼实测 | `benchmarks/report-m2-5-g8-real-model.md`（截断零损失 + 60 样本抖动全 1.0 维持 0.99/0.95） |
| rerank 百炼联调 + 配置切换收口（P3-14 激活） | 同上 ③（gte-rerank-v2 契约实证+provider 入仓+top_n 差异登记）；`tests/test_emb_08_dashscope.py` 11 用例；`.env.example` rerank 段 |
| G-24③④⑤ 收口 | `report-m2-5-perf05.md`（③vec 档超时/熔断/审计 + ④懒构建/零复制〔万级 3.75s→AC 路径零〕 + ⑤vec_top 参数化）；`tests/test_sem_g24_hardening.py` 14 实跑 |
| P3-7 quality 两遍流 hardening | `tests/test_qual_07_hardening.py`（non-finite 防御 + 池缩水有效列均值——4 用例双后端） |
| m2-4 followups ④⑤ | ④`_outbox_integrity` 专用错误（`tests/test_auth_03_sso_jit.py` 增——双后端）⑤MCP 忽略审计移 resolve_org 后（`tests/test_auth_02_org.py` 增 2 用例） |
| 待决-1 / 真实 IdP 受阻申报更新 | `benchmarks/report-m2-5-blocked.md`（不虚造——known-gaps 回写材料） |

## 三、M2 行整体完成态核对（供落笔判断）

- M2 主线 6 段（m2-1~m2-6）+ 语义轨道 6 段（m2s-1~m2s-6）全部交付；
- 本段（m2-5）后 M2 行验收句**无未清偿项**（跨组织隔离全绿 ✓ / TC-PERF-05 ✓
  / B① ✓）；
- 残留（维持既有登记，非 M2 验收句）：TC-UI-01~04 manual 走查待用户执行
  （FR-8 手动走查类口径）；G-22 查询级审计（T-S9⑥）/G-23 残余/G-24 余项——
  均为 known-gaps 登记级（M3/独立批）；
- 门禁：本段基线 1651+1 → **1707+2**（双后端双模式 0 skipped；+56 = emb_08
  11 + sem_g24 7×2 + qual_07 4×2-2 单元 + auth_02 2 + auth_03 1×2 + orgs 6 +
  az_matrix 9×2 − 结构微调；最终以交付门禁输出为准）。
