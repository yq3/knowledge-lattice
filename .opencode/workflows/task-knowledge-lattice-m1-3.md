---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m1-3
target: knowledge-lattice
coderTaskId: ses_e8dee2f5effebMdpPUA7CbhRXI
testerTaskId: ses_e8dca243affe65fN2sjh2VkI0R
committerTaskId: ses_e8d3d79b6ffehNknukpoJd0vIK
status: done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 2ee21181d60d78657c2588a1c5ca52f4337e7758
reviewedSha: cd915f828d58e377ec0a6709e0321966415f7fca
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["R1 24 files +2477/−91：新增 core/docs/credentials.py（issue/put_bytes 流式 staging/consume 三一致+哈希复验/purge_expired + T12 错误码体系 + to_utc_iso）", "新增 store/{sqlite,postgres}/migrations/docs/0003_uploads.sql（三要素绑定+状态机+expires_at+doc/task 追溯）", "api/upload.py POST /api/uploads 签发 + PUT 流式接收+补偿清理", "mcp/server.py upload 工具 + _auth_and_org 改 AuthContext(act)", "app.py ServiceContext.credentials 装配 + CredentialError 映射 + maintenance 调度器", "config.py 三项（ttl 900s/max 200MB/interval 300s env 可覆盖）", "domain/auth.py AuthContext.act + issue_dev_jwt(act) + P3-R2-3 文案清理", "api/admin.py dev-token act", "ingest.py P3-C 收敛 + source_uri 参数", "store/backend.py+双后端 Admin 域凭证六方法（PG 时间列 UTC 归一）", "tests 新增 6 文件 71 用例（cred_01 15/cred_02 28/cred_03 17/cred_04 5/cred_05 e2e 1/p3_followups 5）+ 基线同步 4 文件（user_version 2→3、本地测试迁移号 0003→0004 避让、PG 乱序 4/5）+ conftest cred_env + app_env jwt act【P3-16 更正：cred_03 实际 17 非 18，总 71】", "R2 11 files +404/−55：credentials.py P1-1（_require_usable 补 read_membership 逐请求校验·consume+begin_put 共用单点）+ P2-1（finalize 重读 410/409 + 清扫年龄阈值 max(ttl,2×interval)）+ P3-1/8/12/13/20", "mcp/server.py P1-1 AclDeniedError→ToolError 403", "api/upload.py P3-20 注释", ".env.example P3-14 三 env", "tests cred_02 +7 defs（P1-1×2/P2-1×3/P3-15/P3-3）+ cred_01 +1（P3-2）+ cred_03 +1（P1-1 MCP）+ P3-17 卫生 + scaf/pg_scaff P3-5 expected 补 uploads+docstring 16"]
endReason: null
createdAt: 2026-10-25T15:55:48+0800
updatedAt: 2026-10-25T20:33:00+0800
---

# task-knowledge-lattice-m1-3: M1-3 上传凭证制（三步式）+ deepagents 集成

## 任务原文

**需求**（design.md §8 M1.4，v0.9.3；与 requirements §8 M1 行对齐；前置 M1-2 已合入 PR #51，origin/develop = aa19ea5；依赖的版本在用制已就位）：

**A. 上传凭证制（三步式，P0-D）**（design §3 api/upload.py、§6.1 upload 工具契约 line 1071-1078、§6.2 line 1140；实现依据 §5.5 鉴权与身份）：

1. **凭证签发**：`POST /api/uploads`（{filename, size, sha256, content_type} → {upload_id, upload_url, expires_at}）；**凭证记录绑定 sub+org+服务身份三要素**（#33 P1-3）；过期时间（expires_at）生效。
2. **PUT 字节校验**：`PUT /api/uploads/{id}`——超声明 size 拒绝（413 不静默截断，附录 A-13）、sha256 不符拒绝、**失败 PUT 不计消费、修正重传放行、成功消费后任何 PUT 拒绝**（「用掉」＝摄取成功入队——v1.4 与 T12 统一）、过期后拒绝、**>200MB 全局上限拒绝（413）**——全部带明确错误码。
3. **MCP upload 三一致校验**：`upload(upload_id, …)` 工具（§6.1 契约）——同 sub+org+服务身份进摄取；换组织/换用户/换服务身份/哈希不符一律拒绝（T11：凭证跨组织/跨身份无效）；凭证在**摄取成功入队后**置已用（失败不置、可重传）。
4. **file_ref 防线**：只收不透明 upload_id——路径穿越（../../）、绝对路径、file:///http:// URL、白名单根外符号链接一律拒绝；共享存储场景白名单根目录 + realpath 规范化 + 前缀校验 + 只读 + 大小/扩展名限制（SSRF/任意读取/穿越三防线，NFR-6）。
5. **未消费凭证回收**：清理任务（maintenance 任务类型——design §3，app.py 调度器周期投递）回收过期未消费凭证；未消费凭证可重复 PUT 直至成功消费或过期。
6. **摄取衔接**：upload 工具消费凭证后走既有摄取链（M1-2 版本制：pending → 切换）；凭证与文档/任务关联可追溯。

**B. deepagents 集成**（design §6.3 时序；§5.5 身份）：

1. agent 运行时时序：委托 token（M0b 实验③已实测 langchain-mcp-adapters——依赖互斥发现：实验客户端独立 env）→ MCP upload 工具 → PUT 端点 → 摄取；运行时以 deepagents 或等价 MCP 客户端跑通**端到端上传一次**（开发 JWT/可信子系统头均可——SSO/JIT 属 M2）。
2. 上传链路与 M1-2 版本制/ACL 写链贯通：agent 上传的文档同样受 pending 409、维度写校验、B-1① 旧值校验约束（同一 code path，不旁路）。

**验收标准**（TEST-CASES §六 M1 行凭证组，双后端参数化各跑；门禁 scripts/test_gate.sh skip≠pass）：

- **凭证**：T11（凭证跨组织/跨身份无效）、T12（凭证错误码展开）、TC-CRED-01~05 全条
- **鉴权复跑**：TC-AUTH-01/02（M1 行鉴权组——凭证三要素与组织上下文交互）
- **deepagents 集成**：端到端上传一次（MCP 客户端 → 签发 → PUT → upload 消费 → 摄取完成 → 文档可搜），含版本制联动验证（上传文档走 pending→active 全链）
- TC-E2E 族存量复跑不回退

**口径与边界**：

- **SSO/JIT 对接、委托 token 生产落地属 M2**（M0a 已敲定协议）——本段用开发 JWT / 可信子系统头（含 X-On-Behalf-Of 用户在场证据形态如适用）。
- **管理面凭证查询端点属 M2**——本段落清理任务与回收行为即可。
- 设计冻结纪律：docs/ 禁改（口径问题申报回 supervised-coding）；commit 格式 `[task-knowledge-lattice-m1-3] R<n>`，develop_opencode 分支，commit 前同步 origin/develop，不 push。

**流程纪律（M1 系列延续，用户 2026-10-25 拍板）**：

- **跨检查点会话隔离**：本检查点对应全新 Coder/Tester/Committer 会话（不复用 m1-1/m1-2 的 task_id）；检查点内多轮续接复用各自会话。
- **执行模式 A 串行紧衔接**：M1-3 完成后接 M1-4。

**承接遗留事项**（本段"触及即顺手"清偿，处理完回写勾选并注来源）：

- [x] **P3-13 上传大小上限 413（200MB）**——✅ R1 清偿（默认 200MB 锁定+配置化+签发/PUT 双面独立 413）（来源 task-knowledge-lattice-m0a-3）——TC-CRED-02⑤ 即本段主题
- [x] **P3-21 上传三步补偿**——✅ R1 清偿（PutSink.abort 幂等 unlink+各失败用例 staging 空断言+purge 兜底）（来源 task-knowledge-lattice-m0a-3：PUT 失败/取消路径的存储补偿清理）
- [x] **P3-10 datetime 序列化契约统一 UTC ISO**——✅ R1 清偿（凭证 API 面：expires_at 库内 UTC 秒级/API ISO Z 单点 to_utc_iso；全 API 面推广随后续端点）（来源 task-knowledge-lattice-m0b-1：「API 接入时统一」——expires_at 等凭证字段即 API 面）
- [x] **P3-16 60s 中间件绑定断言**——✅ R1 清偿（非默认值 7.5 注入绑定断言）（来源 task-knowledge-lattice-m0a-3）
- [x] **P3-R2-3 prod 401 响应清理内部审查号"P2-5"**——✅ R1 清偿（文案去除+absence 测试锁定）（来源 task-knowledge-lattice-m0a-3：401 响应体残留内部标记）
- [x] **P3-5（m1-2）先写盘后校验留孤儿文件**——✅ R1 清偿（前置校验先行+Content-Length 预检+失败 unlink，无孤儿）（来源 task-knowledge-lattice-m1-2 committer：「M1-3 凭证制重做写盘流程时一并收口」——凭证制 PUT 落盘流程重设计时前置校验先行或失败 unlink）
- [x] **P3-C（m1-2 R2）upload 侧 new 值校验内联与 helper 两份**——✅ R1 清偿（内联副本删除，三处共用 _require_values_in_grants+双向交叉锚定+文案测试）（来源 task-knowledge-lattice-m1-2 committer R2：加交叉注释锚定等价性——防本段改造 upload 链时漂移）
- [x] **T7 MCP upload 面**——✅ R1 清偿（pending 窗口→409→凭证不置已用用例）（来源 task-knowledge-lattice-m1-2 Tester 观察④：「MCP upload 未落——与凭证制顺延 M1-3 的里程碑口径一致」——TC-CRED-03 即本段主题）

（其余 M1 批次遗留去向不变：区分度/校准/池化/G-6/G-8 组与摄取补全 TC-ING-04~06→M1-4；并发面收口 P3-7/P3-B→M1-4/M2；grants 写路径、P3-4 title/dataset→M2。）

## 需求确认

- [x] 用户已确认（2026-10-25 确认 M1-3 任务原文；status=implementing）
- 历史遗留事项清单：knowledge-lattice 8 检查点全 done（m1-2 于 2026-10-25 合入 PR #51）；M1-3 组遗留 8 条如上承接

## 遗留事项（跨任务移交）

- [x] **移交 M1-4 docs 批——✅ 2026-10-25T20:03 已落笔（supervised-coding 执笔，工作区未 commit，待 coder 纳入交付批）**：L1080「单次使用」→「成功消费后单次；失败 PUT 可修正重传直至消费/过期」（design §6.1）+ requirements FR-1 同源措辞 + design/requirements 联动升 **v0.9.4**；uploads DDL 登记口径「实现细节不入 §4、以迁移 0003 为准」（design §6.2）+ PUT「截断/拒绝」二义定拒绝（附录 A-13）；D18 claim-first 澄清（design §6.2 非 org 路径 resolve_org 口径）；NFR-6 shared-storage 登记 **known-gaps G-12**（活文档，不受冻结纪律约束）
- [ ] **移交 M1-4 docs 批（doc-only 复核 P3 + A-13 独立登记，2026-10-25T20:15 补录）**：TEST-CASES 附录 A-13 旧措辞「design『按声明 size 截断/拒绝』二义……待实现固定后回写」→ M1-4 docs 批回写为已定拒绝（本批 3 文件范围外未动）；design/requirements「日期」历史行欠账（design 止 v0.9、requirements 止 v0.9.1——v0.9.2/3/4 未列入）；api/search.py docstring 与 domain/auth.py resolve_org docstring 仍写「X-Org-Id 例外/MCP/检索端点」旧口径（M1-4/M2 代码注释顺修）
- [ ] **移交 M1-4/M2 登记（committer R1 §5 边界 6 条中 3 条 + P3 顺延）**：§6.2 line 1122「multipart 或携带 upload_id」实现仅 multipart——确认顺延后续段；NFR-6 shared-storage「只读/扩展名限制」未实现——登记 known-gap（本段只有不透明 upload_id 无共享存储分支）；RFC 8693 act 对象形态兼容——M2 SSO/JIT 落地必须项；P3-6/P3-10/P3-11（并发 PUT .part 共用/整体读内存/极窗口文档保留）→M2 并发与资源面收口（与 P3-7/P3-B 合并）；P3-9（create_document 先写对象，M1-2 既有）→M1-4；P3-19 maintenance 任务行无保留策略→M2 任务清理

## 轮次记录

- R1: coder 完成（2026-10-25，**全新会话**，coderTaskId=ses_e8dee2f5effebMdpPUA7CbhRXI，commit `aea936c8f1b98261dfd8f20848e7b2cb56aa509b` 于 develop_opencode，24 files +2477/−91，父提交=aa19ea5 同步后）——A 组：0003 uploads 迁移双方言（三要素+状态机+expires_at+追溯列）+ Admin 域六方法 + credentials.py 核心（流式 staging 前置校验/失败 unlink 补偿/consume 三一致 T11+哈希复验 TOCTOU/成功入队置已用 v1.4 口径/purge 回收）+ REST 签发与 PUT（413/400/409/410 错误码 T12）+ MCP upload 工具（file_ref 三防线+act claim 服务身份）+ maintenance 调度器；B 组：fastmcp Client 端到端三步上传一次（签发→PUT→消费→摄取→lexical 可搜→full 切换→覆盖 v2 全链+409 联动+T9+凭证-doc-task 追溯）；遗留 8/8 全清偿。自测：GATE PASS 507+1 双后端双模式 0 skipped（pg 臂 179；+71 逐文件对账）；TC-AUTH-01/02 复跑 9/9；TC-E2E 族 27 条复跑绿。机械核验：HEAD/格式/docs 零 diff/origin 同步/未 push 全过。口径申报 12 条（upload_url 同源相对路径 / TTL 900s+410 / 三列直存 service_id=act claim NULL=直连 / 200MB 配置化双保险 / 清理 300s 已消费不回收 / PUT 不足声明 400 对称面 / resolve_org 统一规则 / consume 并发原子占位极窗口 409 已建文档保留 POC 取舍 / 摄取 daemon 线程 M0a 口径 / **基线测试同步 user_version 2→3+迁移号避让**〔非断言放宽〕/ source_uri=agent:<act> / T13 完整形态顺延 M2）；边界申报 1 条：design §6.1「upload_url 单次使用」vs TEST-CASES v1.4「失败可重传」字面张力——按验收用例实现（单次消费、PUT 可重复直至消费/过期），未改 docs
- R2: coder 完成（2026-10-25，**续接会话**，coderTaskId 同 R1，commit `2ee21181d60d78657c2588a1c5ca52f4337e7758` 于 develop_opencode，11 files +404/−55，父=aea936c，origin/develop aa19ea5 同步确认，未 push）——**P1-1 已修**：_require_usable（consume+begin_put 共用单点，绑定校验后 read_membership，AclDeniedError 403 管理员不豁免；未进 create_document 通用路径）+ MCP ToolError 403 映射 + 3 用例双后端（过期成员 consume/PUT 403 凭证仍 uploaded 无 doc/task；恢复造数走删行重加+补授权——trg_membership_no_extend T23 语义注记）+ **注入自证**（移除 read_membership→3 failed 恰为新用例→恢复绿）；**P2-1 已修**：清扫年龄阈值方案（max(ttl, 2×interval)——较注册制无注销遗漏风险零状态，择型申报 2）+ finalize 转正前重读凭证（过期/回收 410、并发消费 409——择型申报 3）+ 3 用例（in-flight 存活/陈旧清扫/过期 410 无孤儿）；**P3 顺手 12 项**：文案去内部号 9 处/size_mismatch 用例/symlink realpath 分支用例/expected 补 uploads+docstring 16/mark 失败清 final/purge unlink 纵深/正则 \Z/.env.example 三 env/outbox 双事件断言/测试卫生 6 处/注解/注释；P3-6/9/10/11 顺延 M2 并发资源面、P3-18 登记顺延（PG 版 create_app 非低成本→M1-4/M2）。自测：GATE PASS **523+1 双后端双模式 0 skipped**（pg 臂 186；+16 逐文件对账：cred_02+14/cred_01+1/cred_03+1；pg 179→186=+7）；重申零 skip/xfail/删除/放宽。**择型申报 4 条**：①P1-1 落点 _require_usable 共用单点（PUT/消费统一逐请求，REST 面已有 _org_context，服务层单点双面语义一致）②P2-1 年龄阈值方案 ③finalize 重读语义（None→410 因回收根因即过期/并发 409；重读在 replace 前配合 P3-8 消除孤儿）④恢复成员造数形态（T23 触发器约束下的删行重加）。机械核验：HEAD/格式/docs 零 diff/origin 同步/未 push 全过
- R2: tester **PASS**（2026-10-25，续接会话，testedSha=2ee2118 复核一致）——门禁独立复跑 523+1 双模式 0 skipped（与 coder 一致）、pg 臂 186 全实跑、+16 对账精确吻合（cred_01 16/cred_02 42/cred_03 18）。**P1-1 复验达标**：静态核五点全过（read_membership 绑定后/consume+begin_put 共用单点/未进 create_document（ingest 零 diff，L236 为 M1-2 既有 _require_write_permission）/ToolError 映射/文案同 REST）；**本机注入恰 5 failed 零附带伤害**（3 新 defs 全部双后端展开）→ 恢复 git 干净 → 15 passed；过期成员断言强度（凭证仍 uploaded/documents 计数不变/MCP 面恢复后真协议消费成功）；恢复造数形态合规（T23 语义注记如实）。**P2-1 已修**：三用例双后端绿（in-flight 存活 finalize 200/途中过期 410 无孤儿双断言/utime 回拨陈旧清+新鲜保留）+ 静态核阈值与 finalize 重读（replace 前，except BaseException→abort 配合 P3-8 闭环）。**P3×12 逐条核 ✅**（P3-3 symlink 真触达 realpath/前缀分支——R1 观察项真正闭环；P3-13 本机注入实证 \Z 真修）。回归零弱化零删除（R1 507 条存量改动仅收窄/卫生/增项；M1-1/M1-2 族抽复 91 passed）。择型 4 条全 ACCEPT。新增观察 3 条不阻塞（P1-1 逐请求拦截非凭证吊销——M2 若引入吊销语义需复核断言方向/stale 用例镜像实现弱自参照可接受/顺延登记与 Committer 清单一致）
- R2: committer **APPROVED**（2026-10-25，续接会话，reviewedSha=2ee2118=testedSha=HEAD 双 SHA 对账一致；静态对账 523/186 吻合；bash 只读白名单未复跑采信 Tester）——**R1 清单闭环**：P1-1/P2-1 已闭环（数学论证：age≥threshold≥ttl ⇒ sweep 不删未过期凭证 .part）；P3 12 项闭环 + 残项单列（P3-1 残：_require_usable 403 文案含 FR-4 与既有 helper 同源 / P3-5 残：CHECK/索引/FK 断言未补 / P3-17 残：pg_scaff 注释 0003→0005 命名未改 / P3-19 残：create_task 注解未改口径偏移 / P3-8/12/13 无直测 / finalize None·consumed 无直测 / 403 无机器码）。**P1-1 深层审查：MCP 全部写路径遍历无绕过**（search/fetch 走 compile_acl、upload 走 _require_usable；REST 双重；create_document 不暴露外部；绑定先于成员校验 T11 专属码不被遮蔽；REST/MCP 鉴权语义一致；无新 P1/P2）。**择型 4 条全 ACCEPT**（②数学证明 / ③None→410 语义）。Tester 观察 3 条：①凭证吊销归 M2 复核；②镜像阈值 M1-4 卫生批改独立常量；③**发现 P3-18 登记缺口**（遗留清单未登记）+ P3 残项清单。**放行：approved，可交用户**；P3 残项随 M1-4 卫生/收口批
- M1-3 交付批流程（2026-10-25）：①docs 勘误批 9943360（design v0.9.4 四处 + requirements 联动 + known-gaps G-12）——doc-only 复核 **不放行**（P2-1 requirements L82 同句「截断/拒绝」残留 + P2-2 D18 澄清段与标题/表行矛盾）；②补正 a5c587a（P2-1 修 + P2-2 第一轮 + G-12 模板字段）——复核 **仍不放行**（P2-2 残留：标题「仅 MCP 用」自相矛盾 + D18/§5.5/§5.1/L128 五处旧「REST=X-Org-Id」未同步 + A-13 登记缺失）；③补正二 cd915f8（X-Org-Id 语义 6 处统一：无 org 路径 REST=claim 优先/头兜底、org 路径段=路径+头一致性、MCP=claim 优先）——复核 **放行**（P2-2 闭环；A-13 独立登记已于检查点补录；P3 残项：§5.1 一字笔误「MCP token」→M1-4 docs 批、日期历史行、代码注释两处旧口径→M1-4/M2 顺修）；reviewedSha 回写 cd915f8（最终 docs HEAD）。待 push + PR + gh pr review 留痕
- 交付完成（2026-10-25）：①Coder 同步 origin/develop（Already up to date）+ push develop_opencode `f281e44..cd915f8`（SSH fast-forward）；②**PR #52** 开立（base=develop，MERGEABLE/CLEAN，5 commits，28 唯一文件无流程文件混入——committer 核对含 .env.example），description 含 evidence manifest（testedSha=reviewedSha=2ee21181 代码级 / cd915f8 交付 HEAD 零代码差异 / GATE 523+1 双后端双模式 0 skipped / pg 臂 186 / boundaryNote L1080+X-Org-Id+G-12 / carriedOver 四组）；③Committer 正式评审留痕 review id `PRR_kwDOTsiHgs8AAAABUFwuWw`（COMMENTED @2026-10-25T12:23:53Z，首行「评审结论=APPROVED（可交用户合入）」——单账号留痕标准形态）。A-13 独立登记已在检查点遗留事项（2026-10-25T20:15 补录行——committer 留痕时快照未含，非缺失）。**待用户合入 PR #52；合入即 M1-3 里程碑达成，下一段 M1-4（区分度环 + 语料批量上线 + 黄金集/评测基线 + SLO 标定 + 越权矩阵收口）新检查点新会话——M1 收官段**
- **合入完成（2026-10-25 20:33 用户指令"合入"）**：PR #52 state=MERGED，mergedAt=2026-10-25T12:33:05Z，mergeCommit=`2da63ec99211bcfd768330acdc7ccff3c95c8510`；origin/develop 前进 `aa19ea5..2da63ec`；develop_opencode 远端按 D30 保留——**M1-3 正式完成（done），M1-3 里程碑达成**（三步式凭证制 + deepagents 集成 + P1-1 安全修复；TEST-CASES §六 M1 行凭证组全绿）。下一步 M1-4（M1 收官段）：新检查点 + 全新 Coder/Tester/Committer 会话

- R1: tester **PASS**（2026-10-25，全新会话，testerTaskId=ses_e8dca243affe65fN2sjh2VkI0R，testedSha=aea936c 复核一致）——门禁独立复跑 507+1 双模式 0 skipped（与 coder 一致）、pg 臂 179 全实跑、+71 逐文件对账精确吻合（**纠正申报笔误：cred_03 实际 17 非 18，coder 申报自身 72 与总数 71 矛盾；总数正确无缺失**）。**②基线同步专项审查：合规非断言放宽**（4 文件逐处 diff——基线前进与 0003 一致/乱序用例语义等价平移断言集逐条对应/conftest 只增不删；0003 迁移本体双方言同语义人工比对 + 内存库注入实证 CHECK 拒非法 status）。③~⑦：TC-CRED-01~05 全绿断言强（01 DB 行逐列绑定/02 五拒独立生效含 200MB 严格独立证明/03 **真 MCP 协议非直调**（fastmcp Client+StreamableHttpTransport 挂真实 FastAPI /mcp）+TOCTOU 篡改复验/04 九形态+纵深/05 双态回收+对象同清+已消费保留+审计/调度器真 lifespan 断言）；T12 双面（REST body.code 6 处+MCP ToolError）；TC-AUTH 9/9；e2e 五点全核实（真协议/lexical 窗口 vector_pending/409 不旁路/agent:act 标注/3 凭证追溯）；遗留 8 条全清偿质量达标。⑧口径 12 条+边界 1 条全 ACCEPT（⑧并发极窗口注记移交 M2 并发收口；**边界裁定 ACCEPT 并建议 committer 开 issue 登记 design L1080 措辞勘误**——「单次使用」应精确读作「成功消费后单次」）。回归零弱化零删除（M1-1/M1-2 不变式原样、E2E 18+VER 47+ACL 43 独立复跑绿、B-1① 不旁路佐证）。观察项 5 条不阻塞（新鲜迁移表清单子集形态/symlink 形态未显式构造但同代码路径/staging .part 兜底无直测/dev-token act 任意字符串 M2 收口/申报笔误注意）

## 最新验证意见原文（R1 Tester 报告全文续——逐字原文见本节，testVerdict=PASS）

- R1 Committer 报告（2026-10-25，逐字原文，reviewVerdict=NEEDS_CHANGES）：

**P1-1 MCP upload 消费路径缺 §5.5/FR-4 逐请求成员关系校验**（REST _org_context 调 read_membership 而 MCP _auth_and_org 只认证+org 解析；_require_usable 只绑定校验；upload 是唯一漏网写路径。风险：过期成员（expires_at 到点未删行）凭证 TTL 内签发可经 MCP 消费建文档，维度空可绕 grants。修法：consume（及可选 begin_put）绑定校验后调 backend.read_membership(user_id, org_id)，无有效行抛 AclDeniedError 403（管理员不豁免 D22），MCP 捕获映射 ToolError("403: …")；补测试：u_full 签发/PUT 后将 user_org_memberships.expires_at 置 PAST_TS → MCP upload/服务层 consume 403、凭证仍 uploaded、无 doc/task；正常成员回归。**不要把校验加进 create_document 通用路径**（会误伤 tests/ 中大量非矩阵 owner 造数）。

**P2-1 maintenance staging 清扫删进行中 .part**（purge_expired 对 staging_dir.iterdir() 无条件 unlink 全部；begin_put 任何 PUT 期间写 objects/staging/<id>.part。长 PUT（200MB）与 300s 清扫窗口重叠 → .part 被删 → finalize replace 抛 FileNotFoundError → 非 CredentialError → 500；若凭证恰过期 purge 先删行 → mark 返回 False → 409 语义错 + 已 replace 对象孤儿。修法：清扫加活动/年龄判定（mtime 早于 max(ttl, 2×interval) 才清）或 active staging 集合注册制；finalize 前重读凭证过期按 410 拒；补两测试：in-flight sink 期间 purge → finalize 仍 200；陈旧 .part 被 purge 清理。）

**口径 12 条全 ACCEPT**（③注记：M2 需纳 RFC 8693 act 对象形态，现仅 str；⑧注记：极窗口与 P2-1 过期行窗口是不同窗口，建议一起收口）。**边界 1 ACCEPT**：L1080 按用例实现正确，不改代码；落笔归 M1-4 docs 批，同时覆盖 design L1080 与 requirements FR-1 line 82 同源措辞——不建议只改 design 留第二处同义矛盾。

**Tester 观察 5 条处置**：①→P3-5 补 uploads 入 expected+docstring 16；②→修正表述后补 symlink 用例（P3-3：现有用例只走 .. 前置分支未触 realpath/前缀分支）；③→**升级为 P2-1**（不仅无直测，是行为缺陷）；④→归 M2 SSO/JIT + 登记对象形态兼容；⑤→纠正正确，检查点 frontmatter 交付/收口时回写 17/71。

**需求边界 6 条（登记性质）**：L1080/FR-1 措辞（归 M1-4 docs 批）；design §4 无 uploads DDL（M1-4 批补或登记口径）；§6.2 L1122「multipart 或携带 upload_id」实现仅 multipart（确认顺延）；NFR-6 shared-storage 只读+扩展名限制（登记 known-gap）；RFC 8693 act 对象形态（M2）；D18 claim-first vs X-Org-Id（docs 批澄清）。

关键裁定与证据已全文收录于上方 R1 tester 轮次记录；以下补充报告原文中未入轮次记录的细节：

- 门禁 fail-closed 语义在场（0 skipped）；无 DSN 环境直跑 test_cred_03_mcp.py 会现 1 skip（object_ref[pg] 臂）——conftest 预期防护，非违规。
- TC-CRED-02⑤ 严格独立证明细节：声明 128 > 上限 64、PUT 100（≤声明、>上限）→ 413——若走声明分支不会触发，上限独立性为真。
- TC-CRED-03 真协议细节：fastmcp Client + StreamableHttpTransport 挂真实 FastAPI /mcp（ASGITransport 全 HTTP 栈）+ call_tool；T11 binding_mismatch 专属错误码经 ToolError 透出断言。
- e2e 细节：BlockingEmbedder 造 lexical 窗口（BM25 可搜 + vector_pending=true）→ 放行 → searchable_full + vector_pending=false；3 凭证追溯（2 consumed 绑 doc/task、1 uploaded 未消费）。
- 基线审查细节：test_pg_scaff 乱序用例语义等价平移（水位单调、fail-fast、乱序 DDL 零执行、已应用不重放——断言集逐条对应 col3/col4→col4/col5、(1,2,4)→(1,2,3,5)，意图零改变）。
- 移交建议 2 条：⑧并发极窗口登记 M2 并发收口（P3-7/P3-B 顺延面）；design L1080「单次使用」措辞 issue（应精确读作「成功消费后单次」，用例文档不动）。

## 最新验证意见原文

- （待填）
