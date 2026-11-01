# m2-5 跨组织隔离矩阵报告（TC-OPS-09 / T15 / TC-AZ-04——M2.6 验收句 + REST-PG 残项补齐）

> **执行口径（2026-11-01，Apple M4 / PG 16.15 容器 lattice-pg）**：
> ```bash
> docker start lattice-pg
> export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
> uv run pytest tests/test_az_matrix_m25.py tests/test_orgs_admin.py -v --tb=no
> ```
> **结果：24 passed / 0 failed / 0 skipped**——`tests/test_az_matrix_m25.py`
> 9 用例 × 双后端（sqlite+pg）= 18；`tests/test_orgs_admin.py` 6 用例（sqlite；
> app_env 系——TC-AZ-04② 载体端点行为面）。**REST-PG 残项（P3-18）补齐载体**
> = test_az_matrix_m25.py 的 `[pg]` 臂（9 用例全实跑，M1 时 REST 面 sqlite-only
> 的越权矩阵在 pg 后端复现）。

## 一、扫描面覆盖（M2 新增端点全集）

fixture `az_env`：标准矩阵（org:tax/org:gl 12 用户 5 文档）+ **第三组织
org:ops**（独立 dataset/维度/文档/语义实体——m2-6 R3 P1-1「全库化/org-scoped
消费面行集边界须独立多组织验证」教训的落实）+ 语义三组织 ready 构建 +
`create_app` REST 壳（pg 臂经 `backend=` 注入——m2-6 B⑧ 基建）。

`SCAN_ENDPOINTS` 表驱动扫描 **35 端点**（u_gl → org:tax 全部 403）：

| 面 | 端点（tail 于 /api/orgs/org:tax 下） |
|---|---|
| 管理面 §6.2 | dimensions / datasets（GET）/ datasets DELETE / values PATCH / retire / grants PUT·export·import / reindex / embedding-coverage / audit / stats / members POST·PATCH·DELETE |
| 文档/任务/质量 | documents GET·PATCH·DELETE / documents/{id}/quality / tasks GET·{id}·cancel |
| 语义端点全集 | sync / sync-runs / builds POST·GET·{id}·{id}/report / annotate / l0 / entities?q= / entities/{id} / tables/{key}/describe |
| 无 org 路径 | /api/search（X-Org-Id）/ /api/uploads（X-Org-Id） |

## 二、逐用例收口

| 用例 | 覆盖测试 | sqlite | pg | 备注 |
|---|---|---|---|---|
| **TC-OPS-09** u_gl 全端点扫描 | `test_tc_ops09_u_gl_scan_org_tax_all_denied`（35 端点表驱动） | ✅ | ✅ | 全部 403（成员校验先行——org_id 第一条件） |
| TC-OPS-09 无 org 路径 | `test_tc_ops09_u_gl_search_and_uploads_denied` | ✅ | ✅ | resolve_org → membership 403（无隐式默认） |
| TC-OPS-09 语义隔离对照（T-S7 面） | `test_tc_ops09_u_gl_mcp_semantic_tools_isolated` | ✅ | ✅ | org:gl 面只见本组织实体/l0 片段（同名 key 三组织隔离） |
| **T15** 他组织资源 id（org:gl 路径 + org:tax id） | `test_t15_cross_org_resource_ids_404_in_own_org` | ✅ | ✅ | dimension/value/document id → **404**（存在性敏感）；grants 端点固定 **400**（防孤儿授权——实现固定口径，实质=不返回他组织资源） |
| T15 明确越权固定 | `test_t15_cross_org_path_denied_fixed` | ✅ | ✅ | org:tax 路径 → 403 |
| **TC-AZ-04①** sysadmin 仅管理权 | `test_tc_az04_sysadmin_cross_org_denied_then_manage_only` | ✅ | ✅ | 跨组织检索/语义读 403；GET /api/orgs 管理面照常（sysadmin=全部组织） |
| **TC-AZ-04②** 建组织指定 org_admin | `tests/test_orgs_admin.py::test_create_org_with_org_admin_tc_az04`（+5 辅助用例） | ✅ | —（app_env 系） | **实现缺口补齐**：design §6.2 L1121 `GET/POST /api/orgs` 端点本段实装（此前未实现——新组织首任 org_admin 无法经 API 建立：members POST 要求操作者已是本组织 org_admin、sysadmin 无成员关系 403 死锁）；建组织+指定 org_admin+审计同事务，新 admin 随即 POST members 201（死锁解除端到端） |
| **TC-AZ-04③④** 临时授权完整构造 | `test_tc_az04_temp_grant_full_construction` | ✅ | ✅ | admin_tax 挂 u_temp 临时成员（FUTURE_TS）+ region=CN+tax_type=VAT **双维度**授权 → 生效期检索 d_cn 可见 + members/grants 审计留痕；造数过期（PAST_TS）→ 403 即刻不可见（不等清理——与 T1 同构） |
| **三组织行集边界**（m2-6 P1-1 同型面） | `test_three_org_rowset_boundaries` | ✅ | ✅ | org:ops coverage=[ds:ops_lib] / dimensions=[region] / datasets / 语义实体——org:tax 与 org:ops 互不出现（全库化消费面的 org-scoped 过滤实证） |
| 隔离面泛化（任意非本组织） | `test_gl_admin_cannot_touch_ops` | ✅ | ✅ | u_gl 对第三组织 org:ops 同全拒（不止 tax/gl 双组织） |

## 三、GET/POST /api/orgs 实装说明（TC-AZ-04② 载体）

- `GET /api/orgs`：sysadmin=全部（`list_all_orgs`）；普通用户=本人 membership
  （`list_orgs_for_user`——TC-AZ-02 口径不泄露非本人组织）；双后端 store 方法；
- `POST /api/orgs`：sysadmin 专属 403 拒非 sysadmin；`{id, name, org_admin?}`——
  org_admin 指定即建首任 membership（同事务：组织+membership+`org.created` 审计
  同生共死；用户不存在 404 组织零残留——D16；重复 409——组织不可删只能停用
  P1-1）；6 用例锁定（member 面/sysadmin 面/403/404 零残留/409/端到端死锁解除）。

## 四、REST-PG 残项口径申报（A2——P3-18）

M1 越权矩阵 REST/MCP/shell 面跑 sqlite 臂（122 条，B-1① 限定）；本段补齐
形态 = **A1 矩阵文件直接双后端参数化**（`[pg]` 臂 9 用例全实跑）——M1 核心
越权行（T14 resolve_org/T15/T17 载体/T11 凭证绑定/T13 可信子系统）的 REST
面在既有文件已有 sqlite 用例、其 core/store 逻辑自 M0b 起双后端参数化；
**不逐一翻写 M1 全部 122 条 REST 用例为 pg 参数化**（与 A1 扫描面重叠、
门禁翻倍成本不成比例）——边界申报，tester/committer 核验口径。
