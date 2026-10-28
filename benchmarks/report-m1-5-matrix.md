# M1-5 越权矩阵收口报告（T1~T23 + TC-AZ-01/02/03/05 + TC-E2E-05——双后端实跑）

> 口径（用户 2026-10-26 拍板 B-1①）：矩阵复跑**限定 DB/服务/MCP 层双后端实跑**；
> REST/MCP 服务壳（app_env——create_app 硬绑 sqlite）为 sqlite 面，REST-PG 参数化
> 留 M2 写入验收对照（P3-18 顺延口径）。T13 以 dev 白名单模拟（生产形态随 M2）；
> **T19 删库半句、T20 退役审计半句随 M2 不跑**（v0.6.1 限定 #39）。
>
> 执行（2026-10-26，Apple M4 / PG 16.15 容器）：
> ```bash
> LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice uv run pytest \
>   <本文 28 个矩阵文件清单见附录> -v --tb=no
> ```
> **结果：348 passed / 0 failed / 0 skipped**（R2 复跑——R1 版 346 + P2-3/P2-4
> 新增 list_documents 状态值全集/非成员 403 两用例）——其中 `[pg]` 参数化 **113**
> 条、`[sqlite]` 参数化 **113** 条（同代码双后端各跑）、REST/MCP/shell 面
> （app_env 系，sqlite）122 条。逐用例 PASSED 留痕见执行输出（-v）。

## T1~T23 逐条收口表

| 用例 | 覆盖测试（证据指针） | sqlite | pg | 备注 |
|---|---|---|---|---|
| T1 过期授权未清理仍不可见 | `test_matrix_t1_t5.py::test_t1_expired_grant_invisible_without_cleanup` | ✅ | ✅ | 参数化双后端 |
| T2 成员续期不复活旧授权 | `test_matrix_t1_t5.py::test_t2_membership_renewal_does_not_revive_old_grants` | ✅ | ✅ | |
| T3 停用取值收紧 | `test_matrix_t1_t5.py::test_t3_disabled_value_tightens` | ✅ | ✅ | |
| T4 维度改可选/停用不放宽 | `test_matrix_t1_t5.py::test_t4_…` + `test_acl_01`（Plan 层） | ✅ | ✅ | |
| T5 可选维度有值则过滤 | `test_matrix_t1_t5.py::test_t5_…` | ✅ | ✅ | |
| T6 v2 改维度切换窗口无双可见 | `test_ver_01_version_chain.py::test_t6_full_switch_chain_dims_visibility` + `test_acl_07::test_version_pair_scenario` | ✅ | ✅ | |
| T7 并发覆盖 409 | `test_ver_02_guard_409.py`（服务层）+ `test_cred_03_mcp.py::test_mcp_upload_pending_409_t7_face`（MCP 面） | ✅ | ✅ | MCP 面=sqlite（B-1①） |
| T8 失败版本无 FTS 残留 | `test_ing_05_mojibake.py::test_ing_05b_fail_tier_rejects_ingest` + `test_fts_03_triggers.py` | ✅ | ✅ | |
| T9 切换后 FTS 无旧版本命中 | `test_fts_03_triggers.py::test_switch_clear_then_recall_fts_zero` + `test_acl_06::test_fts_route_version_condition_on_join`（SQL 层双方言） | ✅ | ✅ | |
| T10 待嵌入清单不含 tombstone | `test_ver_02_guard_409.py`（T10 段，行 367 起） | ✅ | ✅ | |
| T11 凭证跨组织/跨身份无效 | `test_cred_02_consume.py::test_t11…`（u_multi/org:gl 绑定专属）+ `test_cred_01/03` binding_mismatch（服务+MCP 面） | ✅ | ✅ | MCP 面=sqlite |
| T12 PUT 超量/哈希不符拒绝 | `test_cred_01_issue_put.py::test_cred_02_put_sha256_mismatch_400` 等 | ✅ | ✅ | |
| T13 可信子系统越界（**M1=dev 白名单模拟**） | dev JWT `act` claim 形态＝`test_cred_03_mcp.py::test_mcp_upload_binding_mismatch_403` + `test_cred_02_consume.py`（服务身份不一致拒绝并审计） | ✅ | ✅ | 生产白名单/X-On-Behalf-Of 全形态+`outcome=refused` 审计随 M2（附录 A-1） |
| T14 org claim 与头不一致 400 | `test_auth_02_org.py`（①~⑤ 全形态，T14 展开） | ✅ | ✅ | 接口面=sqlite；resolve_org 服务层经 app_env |
| T15 他组织维度 id 403/404 | DB/编译层＝`test_acl_05_membership.py::test_other_org_membership_rejected`；跨组织凭证＝T11（u_multi/org:gl）；文档详情跨组织 404＝`api/documents.py` org 判定（`test_e2e_01_chain.py` 检索空集面） | ✅ | ✅ | REST 端点全枚举（grants/values 逐端点）属 M2 管理面验收——B-1① 限定申报 |
| T16 生产配置 token 端点 404 | `test_auth_01_token.py::test_dev_token_prod_404` | ✅ | ✅ | |
| T17 授权撤销后 owner 不再见在用文档 | **载体=文档详情端点（TEST-CASES v1.7 裁定 A=②——org 域管理面）**：①检索零命中（无 owner 分支——#34 必修 2）＝`test_ver_01_version_chain.py` T21 段（owner 覆盖上传处理窗口检索不到任何版本）+ `test_acl_07`（按用户可见集——无 owner 特例）；②owner 元数据兜底＝GET `/api/orgs/{org}/documents/{id}`（org 匹配即返回元数据/状态、无块内容）＝`test_e2e_01_chain.py`（详情状态轮询）+ `test_ver_02_guard_409.py`（删除后 404） | ✅ | ✅ | **缺口注记**：无「owner 授权撤销后 GET 自己文档详情仍 200」专属断言（管理面语义——M2 管理面验收补）；`list_documents` 为 §6.1 ACL 视角工具，证据只挂 TC-AZ-02 |
| T18 报告页近邻不泄露无权内容 | `test_qual_05_report_acl.py`（双后端）+ `test_fts_04_keywords_purity.py`（u_cn 报告 OS-only 近邻不出现） | ✅ | ✅ | |
| T19 删文档（M1 半句） | `test_ver_02_guard_409.py`（T19：REST owner/org_admin、级联+取消任务、非 owner 403、摄取中 DELETE 取消） | ✅ | ✅ | **删库半句随 M2**（申报） |
| T20 生命周期（M1 面） | `test_matrix_t20_t22.py::test_t20_new_dimension_lifecycle` + `test_acl_04_lifecycle.py` | ✅ | ✅ | **退役审计半句随 M2**（申报） |
| T21 owner 覆盖上传处理窗口不可见 | `test_ver_01_version_chain.py`（T21 段，行 313~349） | ✅ | ✅ | |
| T22 空授权维度只见面空文档/无 `IN ()` | `test_matrix_t20_t22.py::test_t22_…` + `test_acl_03`（Plan 层） | ✅ | ✅ | |
| T23 过期成员续期拒/先删再加不复活 | 触发器＝`test_scaf_05_membership_cleanup.py`（双后端）；行为＝`test_cred_02_consume.py::test_p1_1_membership_expired_consume_rejected` | ✅ | ✅ | |

## TC-AZ 补充行

| 用例 | 覆盖测试 | sqlite | pg |
|---|---|---|---|
| TC-AZ-01 上传/PATCH 取值限授权内 | `test_acl_09_write_path.py`（四步全形态，双后端；B-1① 覆盖上传旧值校验） | ✅ | ✅ |
| TC-AZ-02 统计与概况不泄露 | **M1-5 实装支撑**（list_documents 证据唯一挂靠点——T17 另挂详情端点，v1.7 裁定 A=②）：`test_mcp_list_documents_stats_per_caller_acl`（u_cn doc_count=2 vs u_full=3、全 payload 无 d_os 泄露——MCP 面）+ `test_backend_list_documents_for_acl_dual_backend`（backend 层双后端）+ R2 增 `test_mcp_list_documents_active_status_accepts_documented_values` / `test_mcp_list_documents_non_member_403`（P2-3/P2-4：状态值 DDL 口径全集 + 非成员 403） | ✅ | ✅ |
| TC-AZ-03 管理权与可见权分离（M1/M2） | MCP 面=TC-AZ-02 同款按调用者 ACL；管理列表端点=M2 半句——「两个端点两个口径」边界注释见 `mcp/server.py` 工具 docstring | ✅ | —（M2 半句申报） |
| TC-AZ-05 库过滤与 doc_filter 收窄 | `test_e2e_01_chain.py`（datasets/doc_filter 交集语义）+ `test_ret_01_recipe.py` | ✅ | ✅ |

## TC-E2E-05 全量矩阵复跑收口

- 迁移本体：`test_v11_schema.py` **21 passed 双后端**（存量搬运逐字节保真/幂等重放/
  版本只前进/孤立行显式丢弃——上表执行内含）；
- 全量矩阵复跑 = 本文 348 条执行（R2 复跑口径）+ **门禁全量 R2/R3 复验 663 passed / 0 skipped**（双后端双
  模式，含矩阵外全部用例——TC-E2E-05「迁移后全量矩阵复跑在 M1 收口」验收句兑现）。

## 附录：执行文件清单（28 文件）

`test_matrix_t1_t5 / test_acl_01~09 / test_ver_01 / test_ver_02 / test_cred_01~05 /
test_auth_01 / test_auth_02 / test_fts_03 / test_fts_04 / test_qual_05 /
test_matrix_t20_t22 / test_scaf_05 / test_ing_05 / test_e2e_01 / test_m1_5_dev /
test_v11_schema`
