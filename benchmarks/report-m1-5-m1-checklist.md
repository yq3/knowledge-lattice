# M1 验收对照勾验材料（M1-5 收口段产出——§六 M1 行逐条 → 证据指针）

> 用途：TEST-CASES §六 M1 行逐条勾验的**证据索引**（coder 产出；完成态落笔归
> supervised-coding）。证据形态三类：**T**＝门禁内测试（`scripts/test_gate.sh`
> 全量绿——本段最新一轮 661 passed / 1 deselected / 0 skipped，双后端双模式，
> pg 臂 225 实跑）；**R**＝实验报告/数据工件（benchmarks/、eval/reports/）；
> **M**＝手动走查材料（本段产出清单，用户执行）。
>
> 段交付指针：M1-1＝PR #50（R1 3bba1bf）；M1-2＝PR #51（R1/R2 afae23b/f281e44
> 批）；M1-3＝PR #52（R1 aea936c / R2 2ee2118）；M1-4＝PR #53（R1 7567508 /
> R2 912ddd5 + docs b2e36c0）；**M1-5＝本段**（R1 dev 批 992a0e2：门禁 604→661；
> R1 实验+收尾批 b9db4c0；R1 矩阵收口与校准补齐批：本 commit）。
> **矩阵收口专项证据**：`report-m1-5-matrix.md`（T1~T23+TC-AZ 双后端 346/346 全绿）。

## §六 M1 行逐条对照

### 1. 越权矩阵全绿：T1~T23 全量 + TC-AZ-01/02/03/05（双后端各跑——D24）

| 用例 | 证据（T＝测试 / 说明） |
|---|---|
| T1~T5（token 计权/组织/过期/成员关系） | T：`tests/test_matrix_t1_t5.py`（双后端参数化）+ `tests/test_acl_04_lifecycle.py`、`test_acl_05_membership.py` |
| T6~T10、T21（版本链矩阵） | T：`tests/test_ver_01_version_chain.py`、`test_ver_02_guard_409.py`、`test_e2e_04_dims_immediate.py`（双后端） |
| T11/T12（凭证三一致/错误码） | T：`tests/test_cred_02_consume.py`、`test_cred_03_mcp.py`（binding_mismatch 专项） |
| T13（可信子系统——**M1 以 dev 白名单模拟**） | T：dev JWT `act` claim 形态＝`test_cred_03_mcp.py::test_mcp_upload_binding_mismatch_403`（服务身份不一致拒绝）；生产白名单/X-On-Behalf-Of 全形态随 M2（附录 A-1 口径） |
| T14~T16、T18（org 上下文/审计分级/质量报告 ACL） | T：`test_auth_02_org.py`（claim/头不一致 400）、`test_acl_06_constants_routes.py`；T18＝`test_qual_05_report_acl.py`（近邻过同一套 ACL，双后端） |
| T17（授权撤销后 owner 不再见在用文档） | T：**M1-5 新支撑**——MCP `list_documents` 实装（`mcp/server.py` + `tests/test_m1_5_dev.py::test_mcp_list_documents_stats_per_caller_acl`，§6.1「owner 查处理中/在用文档走 list_documents」路径就位）＋ `test_acl_09_write_path.py` 撤销面 |
| T19（删文档＝M1 半句 ✓；删库半句→M2） | T：`api/documents.py` DELETE + `test_ver_02_guard_409.py`/`test_e2e_01_chain.py` 联动；删库随 M2（v0.6.1 限定） |
| T20（生命周期/退役——审计半句→M2） | T：`tests/test_matrix_t20_t22.py`（M1 面双后端）+ `test_acl_04_lifecycle.py`；退役审计半句随 M2 |
| T22/T23（触发器/成员清理） | T：`tests/test_scaf_04_triggers.py`、`test_scaf_05_membership_cleanup.py`（双后端 v1.5.1 起 both） |
| TC-AZ-01（上传/PATCH 取值限授权内） | T：`tests/test_acl_09_write_path.py`（双后端；B-1① 覆盖上传旧值校验 M1-2 R2） |
| TC-AZ-02（统计与概况不泄露） | T：**M1-5 实装支撑**——`tests/test_m1_5_dev.py::test_mcp_list_documents_stats_per_caller_acl`（u_cn doc_count 不含 d_os、全 payload 无泄露）+ backend 层双后端 `test_backend_list_documents_for_acl_dual_backend` |
| TC-AZ-03（管理权与可见权分离——M1/M2） | T：MCP 面＝TC-AZ-02 同款（按调用者 ACL）；管理列表端点（M2 半句）——两口径边界注释见 `mcp/server.py` 工具 docstring |
| TC-AZ-05（库过滤与 doc_filter 收窄） | T：`tests/test_e2e_01_chain.py`（datasets/doc_filter 交集语义，双后端）+ `test_ret_01_recipe.py` |
| **限定申报** | REST/MCP 面 PG 参数化（P3-18）留 M2 写入验收对照（B-1① 拍板）；DB/服务/MCP 层双后端实跑如上 |

### 2. 版本链：T6~T10、T21、TC-VER-01~07、TC-E2E-02

T：`tests/test_ver_01_version_chain.py`（TC-VER-01~05）、`test_ver_02_guard_409.py`（TC-VER-06/07）、`test_ver_03_fetch_mcp.py`（TC-VER-05 fetch 面）、`test_e2e_02`（并入 ver 组用例，双后端）。

### 3. 全量矩阵复跑：TC-E2E-05 收口

T：`tests/test_v11_schema.py`（v1.1 迁移 12 用例——存量搬运/幂等/版本只前进/孤立行丢弃）+ **本段门禁全量绿**（661/0 skipped，双后端双模式——schema v1.1 之上全矩阵复跑即 TC-E2E-05 收口形态；M0b-3 先例 271 → M1 收口 661）。

### 4. 凭证：T11/T12、TC-CRED-01~05

T：`test_cred_01_issue_put.py`（TC-CRED-01/02）、`test_cred_02_consume.py`（TC-CRED-03 服务层）、`test_cred_03_mcp.py`（TC-CRED-03 MCP 面 + TC-CRED-04 file_ref 防线）、`test_cred_04_reclaim.py`（TC-CRED-05）、`test_cred_05_e2e_agent.py`（agent 端到端三步）。

### 5. 检索配方：TC-RET-01~07、TC-E2E-01/04、TC-FTS-04、TC-ACL-08、TC-EMB-07

T：`test_ret_01_recipe.py`（TC-RET-01~07 + TC-E2E-01）、`test_e2e_01_chain.py`/`test_e2e_04_dims_immediate.py`（TC-E2E-01/04）、`test_fts_04_keywords_purity.py`（TC-FTS-04）、`test_acl_08_rerank_guard.py`（TC-ACL-08 双断言）、`test_emb_02_predicate.py`/`test_emb_04_05_07.py`（TC-EMB-07 混模型零距离）。**M1-5 附**：fuse 段双计修正（`test_m1_5_dev.py::test_fuse_excludes_enhance_wait`）+ P3-11 畸形参数降级（同文件 44 用例——PG to_tsquery `!():<>` 敌意字元剥离，修前 500 实证）。

### 6. 摄取补全：TC-ING-04~06、TC-EMB-04/05

T：`test_ing_04_encoding.py`（TC-ING-04）、`test_ing_05_mojibake.py`（TC-ING-05）、`test_ing_06_batches.py`（TC-ING-06）、`test_emb_04_05_07.py`（TC-EMB-04/05 降级链）。

### 7. 鉴权：TC-AUTH-01/02 复跑

T：`test_auth_01_token.py`、`test_auth_02_org.py`（双后端 + resolve_org 统一规则）。

### 8. 区分度：TC-QUAL-01~05、TC-EVAL-06

T：`test_qual_01_crowding.py` ~ `test_qual_05_report_acl.py`（TC-QUAL-01~05，双后端）+ `test_qual_06_patch_service.py`（M1-4 R2 PATCH 面）。TC-EVAL-06（误报抽查机制）：`scripts/quality_sample.py`（确定性抽样清单）+ `test_qual_05/06`（patch_flag 落 state 轨迹）——**记录级用例**；R2 补合成语料抽查人工复核记录 `report-m1-5-fp-review.md`（41 flags 抽 12：词面路误报 11~12/12——同域小语料 IDF 稀释、拥挤路零误报、漏报不可评无金标申报）；真实语料误报率待真实语料（待决-1）；阈值侧校准数据（G-8② 可构造面）见 `report-m1-5-g8-threshold.md`。

### 9. 真实 query 标注：TC-EVAL-01

R：`eval/golden.jsonl`（28 queries——zh/en/mix 全 multi-token）+ `eval/corpus.jsonl`（39 docs）+ `eval/reports/labeling-notes.md`（标注记录）+ 双后端基线 `eval/reports/m1-baseline-{sqlite,pg}.md`（sqlite r@10=0.8929 / pg=0.7857）——M1-4 交付（PR #53）；T：`test_eval_01_golden.py`。**口径申报**：语料为合成（待决-1 真实语料未到位先行——design 既有注记）；真实嵌入模型重测（B-3①）本段受阻未执行（见主报告）。

### 10. 性能：TC-PERF-03/04

R（本段）：`benchmarks/report-m1-5.md` §2（TC-PERF-03 SLO 分项标定——1 万/5 万 × sqlite/pg 四组合，N=5 并发档 P95 全部 ≤2000ms PASS；NFR-8 预算表对照）+ §3（TC-PERF-04 rerank 并发曲线 4.84→24.52 rps@信号量 1→8 + CPU 嵌入吞吐 20205 块/分）；数据工件 `data/bench-results/m1-5-tc-perf-03-*.json`、`m1-5-tc-perf-04.json`。**前置改造**（M1-4 P2-4）：100k 档批量重算内存/参数上限改造——报告 §4（旧形态 10k 行 1.09GB → 外推 10.67GB 不可行；新形态 100k 池实测峰值 673MB、全量候选 74.5s 分钟级）。

### 11. 界面国际化走查：TC-UI-01 复验 + TC-UI-02（检索页）/ 03 / 04

M：`benchmarks/report-m1-5-tc-ui-walkthrough.md`（本段产出——逐条步骤清单，**走查由用户/监督方执行**，记录归档后 §六 落笔）。机制面 T：`test_ui_01_manual.py`（manual 标记占位——门禁排除口径正确性）。

---

## 顺延/未执行申报（M1-5 段内，供 supervised-coding 裁定去向）

| 项 | 状态 | 原因 |
|---|---|---|
| G-6 收窄③ halfvec/表达式索引 10 万块对比（bench7） | **顺延**（用户 2026-10-26 裁定本段跳过——非 M1 验收硬门槛） | 断点现象：3.8GB 容器上 100k×2560 COPY+HNSW 构建预计 15~30 分钟，会话时间预算内不可并行完成；脚本已入库可复跑（`benchmarks/bench7_g6_halfvec.py` 头注顺延声明） |
| 越权矩阵收口（T1~T23 + TC-AZ + TC-E2E-05） | ✅ **已补齐**（打回后） | `report-m1-5-matrix.md`——28 文件双后端实跑 **346/346 全绿**（[pg] 113 + [sqlite] 113 参数化 + REST/MCP/shell 面 120）；TC-AZ-02 经 list_documents 实装验证；TC-E2E-05＝test_v11_schema 21 用例双后端 + 门禁 661 全量复跑 |
| B-3① 真实嵌入模型重测双后端基线 | **受阻——申报材料已产出** | 本地无 ollama/网关（实测核实）；选型/接入点/重测步骤/判据见 `report-m1-5-g6-real-model-deferred.md`。TokenBag 代理基线（M1-4）仍在档 |
| B-3② 停用词滤除评估 | ✅ 已补齐（打回后） | `report-m1-5-g6-variants.md`——PG **+7.14pp 假设精确命中**（q01/q10），sqlite 零变化；产品代码未动（实验 monkeypatch） |
| B-3③ OR 口径变更 | **未动（按拍板走决策流程）** | 决策材料齐备：偏差 10.72pp 分解 + 停用词可收回 7.14pp + ts_rank_cd 无效排除（`report-m1-5-g6-variants.md` 决策表） |
| B-3④ ts_rank_cd 排序对照 | ✅ 已补齐（打回后） | 同 variants 报告——**零差异**（0.00pp r@10/MRR），印证「不能解 AND 零召回」判定 |
| G-8 MRL 截断对比 | ✅ 已补齐（打回后·代理面） | `report-m1-5-g8-mrl.md`——双后端 r@10 截断损失 **0.00pp** / MRR −1.6~−2.4pp（TokenBag 非 MRL 训练口径申报）；真实模型验证随 B-3① 受阻 |
| G-8 指纹阈值校准 | ✅ 已补齐（打回后·可构造面） | `report-m1-5-g8-threshold.md`——同模型 1.0 / fp16 噪声底 1.0（无误报面）+ 漂移判定剖面（warn 1% / reject 5% 粒度）；真实网关抖动分布受阻申报 |
| 蓝绿共存窗口 PG 读代价复测（B4） | ✅ 已补齐（打回后） | `report-m1-5-bluegreen.md`——10k 档共存读代价轻度（~+6% P95，与相位噪声同量级；缓存受控对照）；M0b-2 高波动更可能为跑间环境 |
| 判据落笔（MRL 是否开放配置/阈值数值/双后端偏差结论回写 known-gaps） | 归 supervised-coding | docs/ 冻结纪律——coder 禁改 |

> 以上未执行项均为 M1-5 任务书 B 组实验；A 组（TC-PERF-03/04 + 改造前置）、
> C 组四项、D 组材料（本文件 + TC-UI 清单）已交付。§六 M1 行完成态与 A-8
> 「全量」措辞核销由 supervised-coding 落笔。
