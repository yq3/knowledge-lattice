---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m1-2
target: knowledge-lattice
coderTaskId: ses_e8e8a9608ffejojICNVmkPJ370
testerTaskId: ses_e8e66db0cffe00QCVqT1QNNauG
committerTaskId: ses_e8e1c7484ffeYqIueaXr43w4sv
status: done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: afae23b06a3d9214b1fb833b140fdad96becb52a
reviewedSha: afae23b06a3d9214b1fb833b140fdad96becb52a
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["R1 17 files +2389/−145：core/docs/ingest.py 版本制主战场（覆盖上传入口/pending 409/版本号 max+1/阶段边界 guard/embed 完成分叉切换/pending 失败删块/delete_document/patch_document_dims/dot-key 拒绝）", "core/docs/fetch.py 新增（内容窗口/replaced_by/不可见 404 不泄漏）", "core/docs/retrieve.py P2-新 修复（熔断 allow 移入确实发起调用分支 embed+rerank 双侧）", "store/backend.py 协议扩展（VersionConflictError + switch/max_document_version/start_overwrite 等 9 方法）", "store/sqlite+postgres/backend.py 双后端实装（切换事务逐项 §5.3 SQL；_resolve_pending_dims 移出 insert 事务——P0-2.1）", "store/{sqlite,postgres}/acl_render.py render_visible_doc_ids（文档级 CTE）", "api/upload.py doc_id Form+409/404 映射", "api/documents.py PATCH dimensions 最小面+DELETE", "mcp/server.py fetch 工具注册", "tests 新增 6 文件 68 用例（ver_01 18/ver_02 17/ver_03 3/acl_09 22/r3_followups 8 + conftest ver_env+matrix_channel）", "R2 7 files +341/−27：sqlite+postgres backend 切换 UPDATE 补 active_error=NULL（P2-1 双后端同构）", "ingest.py _start_overwrite except VersionConflictError→UploadConflictError（P2-2）+ _require_values_in_grants 公共校验（B-1①：覆盖上传旧值∈操作者 grants，与 PATCH 共用防漂移；PATCH 校验链 400 先于 403 微调）", "api/documents.py P3-9 死代码", "tests 6 文件 +13 用例（p2_1×2/p3_3×2/p2_2×4/p2_3×1/b1×2/p3_2×2）+ P3-1 断言收窄 + P3-9 import 清理"]
endReason: null
createdAt: 2026-10-25T13:03:30+0800
updatedAt: 2026-10-25T15:57:00+0800
---

# task-knowledge-lattice-m1-2: M1-2 版本在用制全链（active/pending 状态机 + 切换事务 + tombstone）+ 维度 ACL 写链

## 任务原文

**需求**（design.md §8 M1.2 + M1.3，v0.9.2；与 requirements §8 M1 行对齐；前置 M1-1 已合入 PR #50，origin/develop = fc1bcc8）：

**A. 版本在用制全链**（design §8 M1.2——**前移自 M2，M1 越权验收依赖**；实现依据 §4 documents/chunks DDL 与 §5.3 阶段编排）：

1. **active/pending 状态机**：documents 五字段（active_version / active_error / pending_version / pending_status / pending_error）+ `pending_dims_json`（pending 期间不生效，切换事务落入 document_dimensions——P0-2.1）；pending_status 枚举 parsing|chunked|searchable_lexical|searchable_full|failed；**失败版本号不复用**（pending_version = max(历史版本)+1——P0-2.3）。
2. **D20 切换时机**：首次上传 `active_version` 0→1 在 searchable_lexical 即刻切换（BM25 即刻可搜，此后嵌入进度写 active_status、失败写 active_error）；**覆盖上传 lexical 时点不切换**（检索只见 v1）、searchable_full 时点单事务切换。
3. **单事务原子切换**（design §5.3 line 760+，事务内逐项）：旧块 `tombstone=1` + **`chunk_vectors` 对应向量行 DELETE（v1.1 拍板②形态——不得回退为 embedding=NULL 旧口径）** + 五列 FTS 内容清空（触发器）+ documents 五字段更新**带 `WHERE pending_version=:expected` 乐观校验** + `pending_dims_json` 解析落 `document_dimensions`；事务原子（中途失败全回滚）。
4. **tombstone 机制**：不进召回（FTS 路版本条件已在 M1-1 封堵 JOIN + 向量路 cv JOIN 谓词，本段验证闭环）、fetch 返回 `replaced_by: {doc_id, active_version}` 替代提示（不承诺块级映射、不返回旧内容、不报不存在——FR-1）；90 天物理清理属 M2（TC-VER-08 不在本段）。
5. **embed 批次回写防护**（TC-VER-06，v1.6 迁移形态）：回写 = `chunk_vectors` INSERT 新标签行 + `ON CONFLICT (rid, embed_model) DO NOTHING` 防护组，带在用版本/tombstone 防护——已切换/已删块的回写零行生效。
6. **删除与任务取消联动**（TC-VER-07）：摄取进行中 DELETE 文档 → 任务取消；worker 每阶段开始前检查文档存在与版本归属——已删文档不再写块。
7. **并发 409**：同文档并发覆盖上传/切换冲突返回 409（design §8 M1.2 验收句；§6.2 错误码口径）。

**B. 维度 ACL 写链**（design §8 M1.3；编译器读路径 M0a/M1-1 已落，本段为**写路径**）：

1. **多值维度**：文档维度值支持多值（document_dimensions 多行）；授权集与多值的包含语义与编译器既有口径一致。
2. **上传/PATCH 值限授权内**：upload 时新维度写 `pending_dims_json` 且**写权限校验在 upload 即做**（P0-2.1——操作者对该维度值必须有授权）；PATCH 文档维度同校验；越权值 4xx 拒绝（错误码按 §6.2）。
3. **统一空值模板**：无维度行 = 不受限（编译器既有语义，本段写路径不得破坏）。
4. **维度停用/改可选不影响过滤**（D5 v0.4）：维度配置变更（停用/必填改可选）后既有文档过滤行为不变（CTE 快照口径——停用/退役经下次编译生效）。

**验收标准**（TEST-CASES §六 M1 行版本链 + ACL 写路径组，双后端参数化各跑；门禁 scripts/test_gate.sh skip≠pass）：

- **版本链**：T6~T10、T21、TC-VER-01~07、TC-E2E-02（版本切换原子性——**召回层断言**，沿用 M1-1 教训：只断 API 结果不够，切换中途/并发窗口的召回面需在 recall 层断言）
- **ACL 写路径**：上传越权值拒绝、PATCH 越权值拒绝、多值含语义、维度停用后过滤不变（对应 T 组越权矩阵相关行 + TC-E2E-04 复跑不回退）
- 越权矩阵相关行（T6~T10/T21）在本段以单测/集成形态先行全绿；全量矩阵复跑留 M1-4 收口

**口径与边界**：

- **不得回退 M0b/M1-1 拍板**：chunk_vectors 分表 PK(rid, embed_model)、visible_docs AS MATERIALIZED 唯一路径、cv JOIN 谓词、FTS 路版本条件在 JOIN（M1-1 P0-1 修复成果）。
- **fetch 工具**：MCP `fetch`（§6.1）旧块替代提示——M0a 已有 fetch 基础则扩展，无则按 §6.1 契约落。
- **凭证制不在本段**（M1-3）：上传链路用 M0a 既有 multipart，凭证制三步式随 M1-3 改造。
- **90 天物理清理、管理面 PATCH 端点全集属 M2**——本段只落 ACL 写校验所需的最小 PATCH 面（若 §6.2 已有定义则按契约）。
- 设计冻结纪律：docs/ 禁改（口径问题申报回 supervised-coding）；commit 格式 `[task-knowledge-lattice-m1-2] R<n>`，develop_opencode 分支，commit 前同步 origin/develop，不 push。

**流程纪律（M1 系列延续，用户 2026-10-25 拍板）**：

- **跨检查点会话隔离**：本检查点对应全新 Coder/Tester/Committer 会话（不复用 m1-1 的 task_id）；检查点内多轮续接复用各自会话。
- **执行模式 A 串行紧衔接**：M1-2 完成后接 M1-3。

**承接遗留事项**（本段"触及即顺手"清偿，处理完回写勾选并注来源）：

- [x] **P2-新 半开探测令牌泄漏一行修**——✅ R1 清偿（allow 移入确实发起调用分支 embed/rerank 双侧 + 3 用例 + 缺陷态注入必红自证）（来源 task-knowledge-lattice-m1-1 committer R2）：`retrieve.py` embed 分支 `_breaker_allows` 调用提到探针 gate 判断之前，「探针拒绝 + 熔断半开」叠加时 `_probing` 置位后无 success/failure 回写、永不复位（向量路不自愈需重启 + 每请求误写 search.degraded）；修法 = allow 调用移入「确实会发起调用」分支（embedder 非空且 gate 未拒绝才调 allow），或 `_probing` 加探测租约超时；rerank 侧同形但 none 档不可达——顺手同款修
- [x] **T6 完整切换链补断言**——✅ R1 清偿（test_t6_full_switch_chain_dims_visibility：真实上传→pending→切换全链 + recall 层断言）（来源 task-knowledge-lattice-m0a-2 committer R1 P3-4）——本段版本链主题内闭环
- [x] **conftest channel 口径回写用例或 fixture 选项**——✅ R1 清偿（matrix_channel fixture + 口径注释）（来源 task-knowledge-lattice-m0a-2 committer R1 P3-6）
- [ ] **grants 写路径一致性校验**——⏭️ R1 顺延 M2 管理面（本段无 grants 写入口，PUT grants 端点属 M2 §6.2；读侧防护已双后端闭环 + 畸形行用例）（来源 task-knowledge-lattice-m0a-2 committer R2 调研借鉴节：服务层断言/触发器——grants 写入与维度定义一致性）
- [x] **dot-key 维度 key 校验（写路径侧）**——✅ R1 清偿（上传/PATCH _validate_dim_keys 一律 400，双后端用例）（来源 task-knowledge-lattice-m0b-1 P3-5：「M1 维度创建校验亦可」——上传/PATCH 维度 key 的 dot-key 拒绝）
- [x] **PG 臂 malformed-grant 回归**——✅ R1 清偿（test_r3_followups 双后端实跑）（来源 task-knowledge-lattice-m0b-1 移交：read_grants 维度归属校验 PG 侧无用例）

（其余 M1 批次遗留去向不变：凭证/中间件/401 清理组→M1-3；区分度/校准/池化/G-6/G-8 组与摄取补全 TC-ING-04~06→M1-4。）

## 需求确认

- [x] 用户已确认（2026-10-25 确认 M1-2 任务原文；status=implementing）
- 历史遗留事项清单：knowledge-lattice 7 检查点全 done（m1-1 于 2026-10-25 合入 PR #50）；移交项按 m1-1 检查点遗留事项小节四组分摊，本段承接上列 6 条

## 遗留事项（跨任务移交）

- [x] **交付 docs 勘误批——✅ 2026-10-25 已落笔（supervised-coding 执笔，工作区未 commit，已随 f281e44 入库）：design §5.3 SQL 补 active_error=NULL（v0.9.3 设计缺项补全·Committer 裁定）+ design/requirements 联动升 v0.9.3 + TEST-CASES v1.6.3（B-1① 旧值校验口径与锁死面注记 / 新增用例口径 / R2 计数 436）+ 依据区引用刷新。原登记：**①design §5.3 切换 SQL 增 `active_error = NULL`（标"设计缺项补全·Committer 裁定"——SQL 是逐字可执行示意，缺列会让后续实现者复刻状态互斥缺陷）；②B-1① 口径②锁死面更正：PATCH 同锁（Tester"需先 PATCH 清理"表述有误——恢复路径=重新启用取值）+ retired 维度同形 + M2 停用取值 dry_run 影响面须含"维度写锁"项 + M1-4 矩阵加固化用例；③新增用例口径登记（replaced_by.active_version=0 / failed pending PATCH 409 / B-1① 旧值校验）；④R2 测试计数口径（436，含 +13 对账）
- [ ] **移交 M1-2→M1-2 顺手组已完成/顺延汇总**：grants 写路径校验→M2 管理面（无写入口）；P3-4 覆盖上传静默忽略 title/dataset + page_count 不更新→M2 管理面；P3-5 先写盘后校验留孤儿→**M1-3 凭证制重做写盘流程时一并收口**（旧值 403 成常态拒绝路径后此面变宽）；P3-6 outbox 非同事务 + 上传无审计→M2（TC-OPS-01）；P3-7 切换 UPDATE 不校验 pending_status + P3-新-B 两处 TOCTOU + 真实并发窗口用例→**合并"并发面收口" M1-4/M2 租约落地后统一**；P3-8 fetch window clamp→M1-4/M2；P3-10 PATCH failed 从严口径保留（已申报登记）
- [ ] **移交 M1-4/M2 顺手（R2 新 P3-A~E）**：P3-A 口径②锁死面更正（与 docs 批②同源）+ M1-4 矩阵固化用例；P3-B 并发面收口（同上）；P3-C upload 侧 new 值校验内联与 helper 两份——加交叉注释锚定等价性（防 M1-3 改造 upload 链时漂移）；P3-D cosmetic（ver_02:338 注释与 payload 不符 / acl_09:238 错别字"攧行"→"放行" / acl_09 重复 import）；P3-E 403 文案泛化（去 current value 明文，与 P3-A 同批）
- [ ] **移交 M1-3+**：上一检查点（m1-1）移交项继续有效——TC-FTS-04 REST 面补验（硬条件）、rerank 真实联调（环境依赖）、halfvec 评估（M1-4 TC-PERF）；凭证/中间件/401 清理组随 M1-3 主题清偿
- [ ] 无其他（本段验收面内遗留全部闭环）

## 轮次记录

- R1: coder 完成（2026-10-25，**全新会话**，coderTaskId=ses_e8e8a9608ffejojICNVmkPJ370，commit `6c5752fa2dc4c93bd9db0ea8fbb09b70c5a1b710` 于 develop_opencode，17 files +2389/−145，父提交=fc1bcc8 同步后）——A 组：五字段状态机 + start_overwrite（max+1 不复用）+ D20 切换时机（首次 lexical 即切 / 覆盖 full 单事务 switch_active_version：DELETE chunk_vectors+tombstone+FTS 清空+乐观校验+dims 落地）+ dims 解析移出 insert 事务（P0-2.1）+ 回写防护（TC-VER-06 双向）+ 阶段 guard（TC-VER-07）+ delete_document 联动（T19）+ 409（T7/REST）+ MCP fetch replaced_by（TC-VER-05）+ visible_doc_ids CTE；B 组：PATCH dimensions 最小面（TC-AZ-01 四例+pending 409+dot-key+多值空值+outbox 审计）+ 维度停用不改过滤（B4）；遗留 5/6 清偿（grants 写侧顺延 M2——无写入口）。自测：GATE PASS 423+1 双后端双模式 0 skipped（pg 臂 156 全实跑；基线 355→423=+68 对账自洽）；P2-新 红灯自证（注入必红 3 failed→恢复 8 passed）。supervised-coding 机械核验：HEAD/格式/docs 零 diff/origin 同步/未 push 全过。口径申报 6 条：①409 触发（upload=pending 非 failed；PATCH=pending 含 failed；切换冲突=VersionConflictError 后台语义）②任务取消=failed+error 注记（不改 schema）③PATCH 按 key 部分替换+空列表清空+dims_change outbox ④fetch pending 块同样 replaced_by+不可见 404 不区分不存在（T21 不泄漏）⑤覆盖上传 owner/org_admin+org_admin 代传管理权分离 ⑥start_overwrite 库级 WHERE 兜底双保险
- R1: tester **PASS**（2026-10-25，全新会话，testerTaskId=ses_e8e66db0cffe00QCVqT1QNNauG，testedSha=6c5752fa 复核一致）——门禁独立复跑 423+1 双模式 0 skipped（与 coder 一致）、pg 臂 156 全实跑、+68 对账精确吻合（本机逐文件 collect 复核）。A 组：TC-VER-01~07 全绿（VER-04 最强：cv DELETE v1.1 形态+乐观校验错 expected 拒绝+NO_SUCH_VALUE 注入全回滚 v1 复服 recall 层断言，双后端与 §5.3 SQL 逐句同构）；TC-E2E-02 **召回层断言成立**（M1-1 教训已吸收：recall_fts 直查+recall_vec 专测+三时点循环+版本归属归因）；T6/T7×3/T8/T9（fts_word_count 双方言直查）/T10/T19/T21 全过。B 组 11 例×双后端全绿（旧值已失权场景拒、admin 代传+outbox、管理权分离、B4 CTE 快照）。P2-新 注入验证：revert → 6 failed（双后端）→ 恢复字节一致 → 81 passed——真缺陷检测器。口径 6 条全 ACCEPT。回归零弱化零删除（conftest 纯增量、存量 68 文件零触碰、M1-1 不变式原样+族抽复 81 passed）。观察项 4 条不阻塞（ver_01 L106 断言未钉死集合相等/patch failed 分支无用例直测/fetch pending 块分支无用例/MCP upload 面=M1-3 口径内）。PG 残留 0、注入后零残留
- R1: committer **NEEDS_CHANGES**（2026-10-25，全新会话，committerTaskId=ses_e8e1c7484ffeYqIueaXr43w4sv，reviewedSha=6c5752fa 静态全量 diff 审查；bash 只读白名单未复跑门禁，采信 Tester 复跑 + 静态逐文件对账 +68 精确吻合）——核验通过：切换事务 §5.3 逐句同构（sqlite BEGIN IMMEDIATE/PG FOR UPDATE + BaseException 回滚）/ P0-2.1 修复正确（T6 双向锁定）/ 并发语义自洽 / ACL 写链与 FR-4 一致 / fetch 契约对齐 / P2-新 修复质量逐行复原复核 / 门禁零弱化 +68 清点吻合 / 未越界 M1-3 未改 schema。**P2×3**：①切换 UPDATE 未清 active_error（成功切换后残留 v1 错误、状态互斥性破——补 active_error=NULL + 用例 + 口径申报〔design §5.3 SQL 未列该列属设计缺项〕）；②start_overwrite 库级兜底触发时 VersionConflictError 未映射 409（api 500 契约缺陷——3 行映射 + backend 直调用例）；③PATCH dimensions REST 端点整条零用例（Tester 观察②实际范围更大——补 200/403/404/409/400 五态用例）。顺手 P3：P3-1 L106 断言收窄 / P3-2 PATCH failed 分支用例 / P3-3 fetch pending 块用例+active_version=0 钉死 / P3-9 死代码清理；登记顺延 P3-4/5/6/7/8/10。**B-1 需求边界（不发给 coder，回用户）**：覆盖上传是否须校验旧维度值——requirements FR-4 line 124「新旧取值均须校验」+ TEST-CASES T7 前置 L607 断言 vs design §6.2 L1120 只写新值 + 任务原文 B2——实现只校验新值，可达偏差：u_cn 文档被 admin PATCH 成 [OS] 后 u_cn 覆盖上传写回 [CN] 成功（把文档拉回自己可见域而不曾看见现行状态）。Committer 建议①（按 FR-4 严格口径，R2 补旧值校验约 8 行——安全理由 + T7 既有假设 + M1-4 矩阵不会暴露）。**处置**：B-1 → spec_confirm 找用户；P2×3+顺手 P3 → R2 发回 coder（复用会话）
- R2: spec_confirm 处置（2026-10-25 15:18）——B-1 经用户拍板「按建议来」= **选项①（FR-4 严格口径）**：覆盖上传须校验文档当前（旧）维度值 ∈ 操作者 grants；R2 由 coder 落实（校验逻辑与 PATCH 同构 + 用例）；TEST-CASES L607 措辞维持不变（与实现从此一致，无需回写）。R2 修复范围下达 coder（复用会话 ses_e8e8a9608ffejojICNVmkPJ370）：**必修 P2-1（切换 UPDATE 补清 active_error=NULL 双后端同构 + 用例 + 口径申报不写 docs）/ P2-2（VersionConflictError → UploadConflictError 映射 + backend 直调用例）/ P2-3（PATCH 端点五态 app_env 用例 200/403/404/409/400）/ B-1①（覆盖上传旧值校验 + 用例，约 8 行与 PATCH 同构）**；**顺手 P3-1（ver_01:106 断言收窄集合相等）/ P3-2（PATCH failed 分支用例）/ P3-3（fetch pending 块用例 + active_version=0 预期钉死）/ P3-9（死代码清理）**；登记顺延 P3-4/5/6/7/8/10（去向 M2/M1-4，见 committer 报告 §2 P3 表）。R2 验收：门禁重跑 + 用例数重新申报（423→423+N 逐文件对账）+ 无 skip/删除/断言放宽重申
- R2: coder 完成（2026-10-25，**续接会话**，coderTaskId 同 R1，commit `afae23b06a3d9214b1fb833b140fdad96becb52a` 于 develop_opencode，7 files +341/−27，父=6c5752fa，origin/develop fc1bcc8 同步确认，未 push）——**P2-1 已修**：双后端切换 UPDATE 补 active_error=NULL（状态互斥修复，与 set_doc_active_status 首传路径同款）+ 用例先红后绿；**P2-2 已修**：_start_overwrite except 映射 409 + backend 直调用例 + monkeypatch 注入映射用例（修前冒泡必红）；**P2-3 已补**：PATCH 端点五态 app_env 用例（200 回显/403/404/409/400）+ 注入 500 映射必红自证；**B-1① 已修（用户拍板①）**：抽公共校验 _require_values_in_grants（what=new/current）与 PATCH 共用，覆盖上传校验文档当前全部维度值，Committer 场景用例 + admin_full 对照放行 + 部分越权对照拒；**P3-1/2/3/9 顺手全清**（断言收窄 hits⊆v1_ids / failed pending 409 直测 / fetch pending replaced_by + active_version=0 钉死 + 注入自证 / 死代码）；P3-4/5/6/7/8/10 顺延不动。**自测**：GATE PASS 436+1 双后端双模式 0 skipped（pg 臂 162；+13 逐文件对账 ver_01+4/ver_02+5/acl_09+4）；重申零 skip/xfail/删除/断言放宽。**口径申报 3 条**：P2-1 active_error 属 design §5.3 SQL 设计缺项的实现级修正（不构成口径变更，回写归 supervised-coding 裁定）；B-1① 旧值范围=文档当前全部维度 key（切换整体替换 document_dimensions 的必然推论；已停用取值文档任何覆盖上传均 403——FR-4 严格口径推论）；PATCH 校验链 400 先于 403 微调（仅错误报告顺序，不吞码）。机械核验：HEAD/格式/docs 零 diff/origin 同步/未 push 全过
- R2: committer **APPROVED**（2026-10-25，续接会话，reviewedSha=afae23b=testedSha=HEAD 双 SHA 对账一致；静态对账：diff 逐字一致/新用例逐函数清点 7 个→13 实例吻合/436=423+13/[pg] 130+32=162/skip 扫描零命中/删除行仅 3 处含一处断言增强/双后端切换 UPDATE 逐字比对同构含 active_error=NULL/R1 场景代码路径确认被拦/全仓写点扫描无未校验旁路；bash 白名单未复跑门禁采信 Tester）——**R1 清单全闭环**（P2-1/2/3 + B-1① + P3-1/2/3/9，逐条证据见报告）。**B-1① 深层审查四问**：①时点正确（入口校验符合 P0-2.1；pending 窗口双 409 冻结 document_dimensions → 旧值快照有效性成立；两处残余 TOCTOU 单进程不可达→归 P3-7 并发面收口）；②语义对称达成（current 共用同一函数；**附带：upload 侧 new 值校验仍内联一份——P3-C 加交叉注释**）；③严格口径副作用基本正确但 Tester 恢复路径表述有误（**PATCH 同锁非"可 PATCH 清理"；retired 维度同形**；M1-2 经 API 不可达仅造数可至→新 P3-A 登记）；④无绕过面（写点扫描、首传不经 _start_overwrite、跨组织先 404、MCP 无写维度工具）。**口径 3 条全 ACCEPT**（②附注记修正）。**P2-1 docs 回写裁定：归 M1-4 docs 勘误批，无需单独用户确认**（D22② 已覆盖语义；但必须落笔——§5.3 SQL 是逐字可执行示意，缺列会让后续实现者复刻同缺陷；落笔范围 4 项一并登记：§5.3 SQL 补列/口径②更正/新增用例口径/R2 计数口径）。Tester 观察 3 条：①不补登记；②合并并发面收口；③文案泛化 P3-E 与 P3-A 同批。**放行：approved，可交用户**；附登记新 P3-A/B/C/D/E（不阻塞）+ R1 遗留 P3-4~10 去向不变（P3-5 面略变宽：旧值 403 成常态拒绝路径之一，建议 M1-3 凭证制重做写盘流程时一并收口）
- 交付完成（2026-10-25）：①Coder 同步 origin/develop（Already up to date）+ push develop_opencode `9565193..f281e44`（SSH）；②**PR #51** 开立（base=develop，MERGEABLE/CLEAN，3 commits 齐全，20 唯一文件 +2709/−149 无流程文件混入——committer 核对纠正派工估算 24→20：R2 七文件均属 R1 既有文件零新增），description 含 evidence manifest（testedSha=reviewedSha=afae23b 代码级 / f281e44 交付 HEAD 零代码差异 / GATE 436+1 双后端双模式 0 skipped / pg 臂 162 / boundaryDecision B-1① / carriedOver 四组）；③Committer 正式评审留痕 review id `PRR_kwDOTsiHgs8AAAABUEw5kQ`（COMMENTED @2026-10-25T07:52:18Z，首行「评审结论=APPROVED（可交用户合入）」——单账号留痕标准形态），正文六节含派工文件数纠正与 docs-only 双 SHA 口径。**待用户合入 PR #51；合入即 M1-2 里程碑达成，下一段 M1-3（凭证制 + deepagents 集成）新检查点新会话**
- **合入完成（2026-10-25 15:55 用户指令"合入"）**：PR #51 state=MERGED，mergedAt=2026-10-25T07:55:05Z，mergeCommit=`aa19ea5b018654309aa061ff8418be76d4671a90`；origin/develop 前进 `fc1bcc8..aa19ea5`（merge commit 保留 R1+R2+docs 批完整历史）；develop_opencode 远端按 D30 保留——**M1-2 正式完成（done），M1-2 里程碑达成**（版本在用制全链 + 维度 ACL 写链 + B-1① 严格口径；TEST-CASES §六 M1 行版本链组全绿）。下一步 M1-3（上传凭证制 + deepagents 集成）：新检查点 + 全新 Coder/Tester/Committer 会话
- R2: tester **PASS**（2026-10-25，续接会话，testedSha=afae23b 复核一致）——门禁独立复跑 436+1 双模式 0 skipped（与 coder 一致）、pg 臂 162 全实跑、+13 逐文件对账精确吻合。复验 8 项全过：P2-1 双后端 active_error=NULL 静态核 + 用例（含与首传路径「同款」声明属实）；P2-2 直调+映射注入断言真实非恒真；P2-3 五态逐态过（403 场景响应体精确相等+落库复核）；**B-1① 共用实现核验达成**（_require_values_in_grants 被 PATCH×2+覆盖上传×3 调用同一函数；旧值=全部维度 key 逐 key 遍历与申报一致）；P3-1/2/3/9 全清。**本机注入 Batch A（ingest 三处同时）→ 6 failed 归因零串扰 + 对照组 3 例不受扰；Batch B（documents+fetch）→ 5 failed**；恢复字节一致复跑 78 passed。口径 3 条全 ACCEPT（②注记：含停用取值的存量文档任何人都无法覆盖上传——FR-4 严格口径诚实推论，建议 M1-4 矩阵留意）。回归零删除零弱化（ver_01 无删除、M1-1 族抽复 73 passed、M1-2 全量 78 passed、M1-1 三不变式静态原样）。新增观察 3 条不阻塞（403 单因组合未复测风险极低/真实并发窗口用例与 P3-7 同属并发面收口 M1-4 或 M2/403 文案含 current value 明文微泄漏面量级极低可留意泛化）




## 最新验证意见原文

- R1 Tester 报告（2026-10-25，逐字原文，testVerdict=PASS）：

**testedSha: `6c5752fa2dc4c93bd9db0ea8fbb09b70c5a1b710`**（develop_opencode，`[task-knowledge-lattice-m1-2] R1`，父=`fc1bcc8`，与检查点申报一致；验证全程只读+注入自恢复，结束时 git status/diff 对 knowledge-lattice 全空）

## 1. 门禁独立复跑（不采信 Coder 自测）

本机复跑 scripts/test_gate.sh（lattice-pg 容器实跑）：pytest 常规 **423 passed, 1 deselected, 0 skipped**（27.78s）；python -O **423 passed, 1 deselected, 0 skipped**（25.74s）；pg 臂收集 156 = [pg] 参数化 124 + PG 专用 32，**全实跑零 skip**。与 Coder 申报逐字一致。**+68 对账精确吻合**（本机逐文件 collect 复核）：ver_01×18 + ver_02×17 + ver_03×3 + acl_09×22 + r3×8 = 68。deselected=1 为 `-m "not manual"` 设计内排除（TC-UI 人工走查），非 skip。

## 2. 验证范围逐项结论

**② A 组版本制（断言强度抽查）**：TC-VER-01 ✅强（SQL 层断五字段+active_error+recall_fts 可搜）；VER-02 ✅强（lexical 时点五字段态+v2 零命中；full 后 tombstone=1+五列空+cv=0+dims 落地+乐观校验逐项 SQL 断言。弱项：L106 `any(startswith chk_)` 未钉死 hit∈v1_ids，见观察①）；VER-03 ✅强（v2 失败→v3、tombstone 可追溯、三源 max 实现核对一致）；**VER-04 ✅最强**（cv DELETE v1.1 形态非置空、`WHERE pending_version=:expected` 乐观校验错 expected 拒绝+零副作用、注入 NO_SUCH_VALUE → RuntimeError 全回滚 v1 复服+pending 零残留 recall 层断言、双后端与 §5.3 SQL 逐句同构、BaseException 回滚）；VER-05 ✅（core+MCP fastmcp 端到端双面：replaced_by 对象、chunks=[] 不返旧内容、不报不存在）；VER-06 ✅强（切换后零行+删除后零行+**对照组 v2 正常回写防误伤**；INSERT..SELECT(tombstone=0+标签匹配)+ON CONFLICT DO NOTHING）；VER-07 ✅强（删文档→任务 failed+cancelled、续跑不复活零写块、版本顶替 guard、failed 版本旧任务不取消例外）。**TC-E2E-02 ✅ 召回层断言成立（M1-1 教训已吸收）**：`_fts_hits`→`backend.recall_fts` 直查 + `recall_vec` 向量路专测（ver_02_vec）；parse/chunk/index_fts 三时点循环 + 版本归属集合归因（`version_hits ≤ {1}`）+ 切换窗口 409 + 注入回滚复服。

**T 组**：T6 ✅强（admin_full 双前提、pending 期 v1 判权可见+document_dimensions 仍 v1 值〔P0-2.1〕、切换后 u_cn_vat 不可见+u_os 对照可见——recall 层）；T7 ✅（service 409 + max_document_version==2 不产三号 + REST 202 携 pending_version + REST 409）；T8 ✅（物理删零行+FTS 直查零命中+v1 复服）；T9 ✅（fts_word_count 双方言直查 + recall 层双证）；T10 ✅（异标签造"已钉未回写"→清单排除+回写零行不复活）；T19 ✅（204+级联零行+任务取消注记+非 owner 403+404）；T21 ✅（四步全链 recall 层零命中三 token + 切换后仍不可见）。

**③ B 组 ACL 写路径（11 例×2）**：✅ 全绿断言到位——上传越权值拒（含不留文档行断言）/ PATCH 新值越权拒、**旧值已失权场景拒**（[CN,OS]→[CN] 匹配 current value）/ admin_full 代传成功+document.dims_change outbox 审计+dims 即时回填 / admin_tax 管理权放行但取值拒（分离）/ pending 409 / 多值包含语义 / 空列表清空→空值放行 / dot-key+未知 key/值 400 / B4 维度停用+改可选→同可见集（重编译后仍不变——CTE 快照口径）/ 操作矩阵 403·404。

## 3. ④ P2-新 注入验证证据

备份 retrieve.py → python3 精确替换（锚点 count==1）把 embed/rerank 两侧 allow 移回无条件调用（修前形态）→ `pytest tests/test_r3_followups.py` → **6 failed, 2 passed**（3 个 p2new 用例×双后端全红，失败机理与预测一致：`assert breaker.allow(now=1061.0) is True` → `assert False is True`——令牌被叠加请求消耗）；malformed_grant 2 例不受扰（对照有效）；cp 恢复 → git status/diff 空 + 与 HEAD 字节一致；复跑 r3+M1-1 族 **81 passed** 全绿。Coder 申报"3 failed"为单后端口径，本机双后端 6 failed——同一结论，用例是真缺陷检测器。

## 4. ⑤ 口径申报 6 条裁定（全部 ACCEPT）

①409 触发（upload=pending 非 failed / PATCH=pending 含 failed 从严）ACCEPT——ingest L228 vs L284 + test_t7_failed_pending_allows + test_patch_pending_409 双侧实证；②任务取消=failed+error 注记 ACCEPT——run_task L351/L366 + 三处测试断 cancelled in error；③PATCH 按 key 部分替换+dims_change outbox ACCEPT——set_document_dims 按 key DELETE+INSERT+逐值 rowcount 校验不符回滚+outbox 断言；④fetch pending 块同样 replaced_by+不可见 404 不区分 ACCEPT——fetch L63-69 非在用统一分支+同文案（观察④）；⑤覆盖上传 owner·org_admin+代传分离 ACCEPT——_require_write_permission+取值始终校验操作者自身 grants+三向实证；⑥start_overwrite 库级 WHERE 双保险 ACCEPT——双后端 rowcount==0 raise 真实在。

## 6. 回归面 + 观察项

**回归：零弱化零删除**——tests 仅 conftest +49/−0（纯增量）+5 全新文件；存量 68 测试文件零触碰；源码删除行均为实现改造。M1-1 不变式未回退（AS MATERIALIZED CTE、版本条件在 JOIN、cv.embed_model 谓词均原样）；M1-1 族本机抽复 81 passed。

**观察项（不构成 FAIL，供 committer 参考）**：①ver_01 L106 单条断言未钉死命中∈v1_ids（建议后续收窄为集合相等）；②PATCH 对 pending_status=failed 的 409 从严分支有实现（L284）但无用例直测（现测为非 failed pending）；③fetch 对 pending 版本块→replaced_by 分支代码在、无显式用例（现测为切换后 tombstone 块）；④T7 的 MCP upload 面未落——与凭证制顺延 M1-3 口径一致，非本段缺口。

**结论：testVerdict: PASS** — 门禁独立复跑全绿零 skip、68 新用例精确对账、A/B 组断言强度抽查达标（含召回层断言、双向防护、原子回滚）、P2-新 注入必红自证成功并恢复零残留、口径 6 条全 ACCEPT、回归零弱化。

- R2 Tester 报告（2026-10-25，逐字原文，testVerdict=PASS）：

testedSha=`afae23b06a3d9214b1fb833b140fdad96becb52a`（R2，父=6c5752fa，git log -2 核验一致；三处注入文件均与 HEAD 字节一致、git status 全空）

**1. 门禁**：pytest 常规 436 passed, 1 deselected, 0 skipped（26.91s）；python -O 436+1（25.74s）；pg 臂 162 = 参数化 130 + PG 专用 32 全实跑。+13 对账精确吻合（ver_01 18→22 / ver_02 17→22 / acl_09 22→26；423+13=436；[pg] 124→130 自洽）。零 skip/xfail/删除。

**2. 复验 8 项全过**：①门禁见上；②P2-1 新用例双后端过（v1 首传 embed 失败前置断言→覆盖 v2 切换→active_error is None）+ 静态核 sqlite:419+/pg:412+ 均补 NULL + set_doc_active_status 首传路径本就清——「同款」声明属实；③P2-2 直调用例（pending 非空非 failed→抛 VersionConflictError）+ 映射用例 monkeypatch 断言 UploadConflictError 且 not isinstance(VersionConflictError) finally 还原——真实非恒真；④P2-3 五态逐态过（200 响应体精确相等 {doc_id,dims}+落库复核 / 403 非 owner member / 404 / 400 dot-key+未知值且正确置于无 pending 时点 / 409 pending）；⑤**B-1① 关键验收点达成**：Committer 场景全过（u_cn 文档被 admin PATCH [OS]→u_cn 覆盖上传新值 [CN] 在授权内→403 "current value"；admin_full 对照放行 pending v2+active 仍 1+跑完切换；部分越权对照拒）+ **共用实现核验：_require_values_in_grants(what=new/current) 被 PATCH 两处与覆盖上传旧值校验三处调用同一函数——防漂移达成** + 旧值范围 get_document_dims 全部 key 与申报一致；⑥P3-1/2/3/9 全清（L106 收窄 hits<=v1_ids / failed pending 409 直测与上传侧放行对照 / pending v2 块 replaced_by={active_version:1}+首传 pending 直插钉死 active_version=0 / 死代码净）；⑦回归：R2 触碰仅 3 测试文件（ver_01 +79/−4 无删除、ver_02 +105/−0、acl_09 +84/−1 import 行）——零用例删除断言只强不弱；源码不触及 acl_render/retrieve/adapters，M1-1 三不变式静态原样；M1-1 族抽复 73 passed、M1-2 全量四文件 78 passed；⑧口径 3 条全 ACCEPT。

**3. 注入证据**：Batch A（ingest.py 三处同时注入）→ 6 failed 3 passed 归因零串扰（删旧值校验→b1×2 红；还原 P2-2 映射→p2_2 service×2 红；PATCH 409 放宽 failed→p3_2×2 红；对照组 p2_2 直调×2+p2_3×1 不受扰）。Batch B（api/documents.py + fetch.py）→ 5 failed（409 映射改 raise→p2_3 红；replaced_by 改指 pending_version→p3_3×2+ver_05×2 全红——active_version=0 钉死与既有断言构成真缺陷检测器）。恢复：cp 回→逐一 diff 与 HEAD 字节一致→git status 空→复跑 78 passed。

**4. 口径 3 条全 ACCEPT**：①P2-1 active_error 设计缺项实现级修正（§5.3 SQL 原文确无该列；与首传路径对齐；docs 回写归 supervised-coding 裁定）；②B-1① 旧值范围=全部维度 key（整体替换必然推论；read_grants 只含 active 维度×active 取值→停用取值必然 403——FR-4 严格口径诚实推论。**注记：含停用取值的存量文档任何人都无法覆盖上传（需先 PATCH 清理或恢复取值），属口径内行为，建议 M1-4 矩阵留意此形态**）；③400 先于 403 顺序微调（仅报告顺序无吞码）。

**5. 新增观察项（不阻塞）**：①P2-3 的 403 是「非 owner member」单因，owner+新值越权的 REST 面组合未在端点层复测（core 共用实现已覆盖，风险极低）；②P2-2 真实并发窗口无原生并发用例——与 P3-7 同属并发面收口，M1-4/M2 租约落地后补为宜；③B-1① 后 u_cn 对被 admin 改写的文档既不能覆盖上传也看不出现行值（403 文案含 current value 明文——存在性/取值微泄漏面，量级极低，可留意泛化文案）。

**结论：testVerdict: PASS** — 门禁双模式 436+1 全绿零 skip、+13 逐文件精确对账、P2×3/B-1①/P3×4 修复全部实证（含本机 5 处独立注入必红→恢复零残留）、口径 3 条全 ACCEPT、R1 的 423 条零删除零弱化、M1-1 不变式原样。

- R1 Committer 报告（2026-10-25，逐字原文，reviewVerdict=NEEDS_CHANGES）：

## 0. 基线核对
fc1bcc8..6c5752fa（17 files +2389/−145）与检查点一致；testedSha==HEAD；docs/scripts/migrations/adapters/domain diff 空；未 push；未越界 M1-3 凭证制、未改 schema。bash 只读白名单，未独立复跑 pytest——静态逐文件清点 + Tester 复跑证据对账。

## 1. 核验通过
①切换事务 §5.3 逐句同构（DELETE chunk_vectors 旧 rid 子查询 → tombstone+五列清空 → 五字段 WHERE pending_version=:expected → 同事务 _resolve_pending_dims；sqlite BEGIN IMMEDIATE / PG FOR UPDATE；BaseException ROLLBACK 覆盖注入路径）；四处拍板形态原样未回退。②P0-2.1 修复正确（insert 仅 active==0 解析、覆盖上传收口切换事务、T6 双向锁定；首传失败再覆盖走首切路径自洽）。③并发语义（409 差异口径①一致、start_overwrite 双保险真实、_finish_embed 幂等分支正确、四阶段边界 guard 重读文档）。④ACL 写链（编译器语义零改动、upload/PATCH 对称、admin 代传管理权/写权限分离与 FR-4 一致、跨组织 404）。⑤fetch 契约（四字段/replaced_by/同文案 404/同一 CTE 无 owner 分支）。⑥P2-新 修复（allow 与 success/failure 回写一一配对、不引入新问题、Tester 注入 6 failed 机理逐行复原成立）。⑦门禁零弱化（gate 零改动、新 6 文件零 skip、存量零触碰、+68 逐文件清点精确吻合）。

## 2. 问题清单
**P0：无。P1：无（唯一 P1 级风险 = B-1 需求边界，不计入 Coder 阻塞项）。**

**P2-1 切换事务未清 active_error → 成功切换后残留旧版本错误**（sqlite backend:419-426 / pg:412-419；触发路径 ingest:541-543）：可达序列 v1 首传 embed 失败（active_error 非空）→ 覆盖上传 v2 成功切换 → active_status=searchable_full 而 active_error 仍 v1 错误——GET documents 状态互斥破。set_doc_active_status（首传路径）已清、切换路径漏同款。修法：切换 UPDATE 增 active_error=NULL（双后端同构）+ 用例（首传 embed 失败 → 覆盖成功 → 断言 active_error is None）。design §5.3 SQL 未列该列属设计缺项——**R2 做口径申报，不写 docs**。

**P2-2 start_overwrite 库级兜底触发时 VersionConflictError 未映射 409（500）**（ingest:234-242 未包 + api/upload.py:96-106 映射缺）：backend.py:20-22 明写该异常"409 语义"，但保险触发时 REST 500 违 §6.2（当前单进程不可达，属潜在契约缺陷；M1-3 凭证制后可达）。修法：_start_overwrite 内 except VersionConflictError → raise UploadConflictError（3 行）或 api 层补映射；补 backend 直调用例（无需造并发）。

**P2-3 PATCH /documents/{id}/dimensions REST 端点整条零用例**（api/documents.py:56-87；grep 确认无任何 client.patch 调用——Tester 观察②实际范围更大）：200/403/404/409/400 映射无直测。修法：补 1 个 app_env 用例五态覆盖。

**P3（登记或顺手）**：P3-1 ver_01:106 断言收窄（Tester 观察①，1 行）；P3-2 PATCH failed 分支用例（观察②，5 行）；P3-3 fetch pending 块用例 + active_version=0 预期钉死（观察③）；P3-4 覆盖上传静默忽略 title/dataset_id、page_count 不更新（dataset 不一致建议 400）；P3-5 对象文件先写盘后校验留孤儿（前置校验移前或 unlink）；P3-6 上传/覆盖无 outbox + PATCH/DELETE outbox 非同事务（TC-OPS-01 属 M2 登记；事件名 M1-4 口径登记）；P3-7 切换 UPDATE 不校验 pending_status（建议加 AND pending_status='searchable_full'；租约落地后消失）；P3-8 fetch window 无上限（clamp ≤10）；P3-9 死代码（未用赋值/import）；P3-10 PATCH failed 从严口径保留或 M2 对齐（已申报，登记即可）。

## 3. 需求边界 B-1：覆盖上传是否须校验文档当前（旧）维度值——三处正文不自洽
- 要求侧：requirements:124 FR-4「上传与修改文档维度可打的取值都限定在操作者本人授权集合内（**新旧取值均须校验**）」+ TEST-CASES:607 T7 前置直接断言「FR-4 要求覆盖上传新旧取值均须校验会先在取值校验处 403」。
- 边界侧：design:1120 §6.2 POST documents 只写「校验库+必选维度+取值在本人授权内」**无旧值**；「新旧取值」只挂 PATCH 行 L1122；任务原文 B2 亦为新值。
- 实现行为：create_document/_start_overwrite 只校验新值；旧值校验只在 patch。可达偏差：u_cn（region=[CN] owner）文档被 admin PATCH 成 [OS] → u_cn 覆盖上传写回 [CN] 成功——把文档拉回自己可见域而不曾看见现行状态。
- 处置：**不发给 Coder**。二选一：①按 FR-4 严格口径 → R2 补「覆盖上传校验 get_document_dims 旧值 ∈ 操作者 grants」+ 用例（约 8 行与 PATCH 同构）；②按 design §6.2/B2 → M1-4 回写批修正 TEST-CASES L607 措辞。**Committer 建议①**（安全理由 + T7 既有假设 + M1-4 全量矩阵用 admin_full 两种口径都不会红，属潜在偏差）。
- 附带：design §8「切换冲突 409」本段无客户端可触发路径（无 reindex 端点），以任务 failed 落账符合口径①，无需动作。

## 4. Tester 观察项 4 条处置
①→P3-1 本轮顺手修（R2 已触碰该文件）；②→P3-2 本轮补（口径①从严差异的唯一实现证据）；③→P3-3 本轮补（顺带钉死 active_version=0 预期）；④→确认无动作。

## 5-6. 复跑证据与把关状态
静态对账：diff stat 逐字一致；conftest 纯增量；68 条逐文件清点吻合；gate/docs/migrations/adapters/domain 零 diff；未 push；双后端切换/pending/回写/守卫 SQL 逐句比对同构。P2-新 静态演练与 Tester 注入结果一致。
**reviewVerdict: NEEDS_CHANGES；reviewedSha=6c5752fa=testedSha=HEAD。阻断项 P2-1/2/3（+顺手 P3-1/2/3/9）。B-1 回用户确认前不派给 Coder。R2 后重跑门禁并重新申报用例数（423→423+N 逐文件对账）、reviewedSha 置空、重申无 skip/删除/断言放宽。未执行 gh pr review（交付阶段经用户确认后对最终 HEAD 留痕）。**
