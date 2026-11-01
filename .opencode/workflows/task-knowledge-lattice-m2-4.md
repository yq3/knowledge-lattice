---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m2-4
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: ses_e6af9e2fbffe8jYdL2AMbMkP5m
testerTaskId: ses_e6a989552ffeC2McLt2BxO5ye2
committerTaskId: ses_e6ac6e05fffeaTfE069ljMpJpz
status: approved
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: b24896e300c2b03f4c8d143d0ec1119e7d059906
reviewedSha: b24896e300c2b03f4c8d143d0ec1119e7d059906
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [".env.example", "src/knowledge_lattice/adapters/auth_sso.py(新)", "src/knowledge_lattice/api/search.py", "src/knowledge_lattice/api/upload.py", "src/knowledge_lattice/app.py", "src/knowledge_lattice/config.py", "src/knowledge_lattice/domain/audit_events.py", "src/knowledge_lattice/domain/auth.py", "src/knowledge_lattice/mcp/server.py", "src/knowledge_lattice/store/backend.py", "src/knowledge_lattice/store/postgres/backend.py", "src/knowledge_lattice/store/sqlite/backend.py", "tests/test_auth_03_sso_jit.py(新)", "tests/test_auth_04_delegated.py(新)", "tests/test_auth_05_trusted.py(新)", "R2 增量(12 files +562/−118): adapters/auth_sso.py, api/search.py, api/upload.py, config.py, domain/auth.py, mcp/server.py, store/backend.py, store/sqlite/backend.py, store/postgres/backend.py, tests/test_auth_03_sso_jit.py, tests/test_auth_04_delegated.py, tests/test_auth_05_trusted.py"]
endReason: null
createdAt: 2026-11-01T10:41:52+0800          # 创建时间（30 天清理审计用，见 README §4.5）
updatedAt: 2026-11-01T13:10:13+0800          # 每次写检查点必更新为当前时间（ISO 8601 含时区），不得沿用旧值
---

# task-knowledge-lattice-m2-4: M2.2 生产化认证段——SSO/JIT 对接+委托 token/可信子系统（RFC 8693 act 对象形态收口）

## 任务原文

**段定义**（design §8 M2 第 2 项 L1269；_m2-plan row 7）：**SSO/JIT 对接（M0a 已敲定协议）；委托 token / 可信子系统落地（三约束 + 期限）**。验收：TC-AUTH-03/04/05 全绿 + T13 生产形态收口 + T16 生产形态复核（§六 M2 行）。

**A 主线**：
- **A1 SSO 验签与 JIT 建档**（design §2 L806·D16；§3 `adapters/auth_sso.py`+`domain/auth.py`）：企业 SSO token 验签（OIDC 优先——协议按**待决-2**，POC 以 mock IdP/自签 JWT 形态适配器交付）→ 解析全局用户；**首次登录 JIT 建档**（users 表自动落库 id/username/display_name，管理员不建账号只配授权——D16）；二次登录复用既有行。**用户裁定（2026-11-01）——适配器留口子**：当前外部环境开发、真实企业 IdP 信息不可得，验签器按**协议中立可插拔接口**交付（配置化注入、mock 实现不侵入业务层），企业内基于开源版继续开发时替换真实 IdP 适配器即可。**TC-AUTH-03**
- **A2 委托 token 语义**（D18 主方案·RFC 8693 Token Exchange；TC-AUTH-04）：`aud=knowledge-lattice`、`sub`=用户、`act`=agent 标识、`org` claim 单值的委托 token——验签后**按 sub 计权、act 进审计**（双身份审计事件）；**透传用户原始 token → 拒绝**（MCP 规范明令）；**请求体权限字段 → 忽略并记审计、请求正常处理**（FR-4/D18 v0.6.1 统一口径，附录 A-9 已闭环）。组织上下文沿 D18 统一规则（claim 优先/X-Org-Id 兜底/不一致 400/缺失报错——与既有 dev JWT 路径 resolve_org 行为对齐）
- **A3 RFC 8693 act 对象形态兼容**（**m1-3 移交必须项**——其检查点 L82：M2 SSO/JIT 落地必须项；m1-3 Committer 口径 12 条之③「M2 需纳 RFC 8693 act 对象形态，现仅 str」）：act claim 同时接受 **string**（agent 标识）与 **object 形态** `{"sub": "<agent-client-id>", ...}`（RFC 8693 §2.1——act 值可为 JSON 对象含 sub；链式委托取**最外层** act 的 sub = current actor——**用户裁定（2026-11-01）按 RFC 8693 §4.1 MUST 口径**：outermost act=current actor、nested prior actors 仅信息性；完整委托链进审计 act_chain 保留追溯；原稿「取最内层」系笔误），两种形态均进审计；非法形态拒绝并审计
- **A4 可信子系统降级三约束**（design §2 L810·#33 P1-5；TC-AUTH-05/T13）：服务凭证（mTLS/服务 token）+ 白名单（条目带 **allowed_orgs**+按服务限流）+ `X-On-Behalf-Of: <user_id>`——①白名单内+allowed_orgs 匹配+**用户在场证据**（请求附用户 SSO id_token/短期断言，校验 `sub` 与 `X-On-Behalf-Of` 一致——防服务凭证冒充离线用户）→ 按声明用户计权、双身份进审计；②org 越界 ③sub 不符（冒充）④白名单外——**拒绝且 `outcome=refused` 进审计**。**T13 生产形态收口**（M1 为 dev 白名单模拟——本段落真实白名单载体+三约束生产形态）。**期限注记**（design 原文）：「上生产前必须切 Token Exchange 或落实②」——本段交付后②即落实，期限满足
- **A5 生产形态收口**（T16/静态 token 边界）：`POST /api/dev/token` 生产配置 404（M1 已交付——本段复核随生产 auth 开关形态）；**静态 token 仅开发/测试与 CI**（LATTICE_* 环境开关——生产模式下 dev JWT/静态 token 全拒绝）；auth 装配分层（sso 适配器可配置注入，缺省 dev 形态保持现有门禁/测试兼容）

**B 顺手**（按 Committer 惯例核销或再挂）：m1-3 检查点 L82 移交项余量（multipart/upload_id 顺延确认、NFR-6 shared-storage 已登记 G-12 不动）；m2-3「token 交叉项」——委托 token org claim 与 m2-3 管理面鉴权路径的兼容回归；**m1-3 L81 尾项——api/search.py 与 domain/auth.py resolve_org docstring 旧口径注释顺修**（2026-11-01 用户裁定并入：触及 auth 链路时顺手，若核验已修则回写闭环）。

**不做**：真实 IdP/SSO 服务联调（**待决-2〔企业 SSO 协议〕/待决-3〔agent 侧 token 换取能力〕仍未决**——POC 以 mock IdP/自签形态交付并验收，真实联调登记挂账至环境就绪，与 rerank 真实网关联调同批归 m2-5/部署期）；SSO 组织/成员关系从 IdP/HR 同步（NFR-5 演进缝——不实现）；Token Exchange 服务端代理（agent 侧换取住 IdP——本系统只做验签方）；TC-AUTH-01/02（M1 已交付——仅回归）。

**验收标准**：TC-AUTH-03（SSO JIT 建档）/TC-AUTH-04（委托 token 语义+act 对象形态）/TC-AUTH-05（可信子系统三约束）全绿（双后端）；T13 生产形态收口（refused 审计双身份）；T16 生产配置复核；RFC 8693 act 对象形态用例（m1-3 移交闭环）；门禁双后端双模式 0 skipped、基线 **1479+1** 只增不减。

## 需求确认
- [x] 用户已确认（2026-11-01——①任务范围 A1~A5+不做边界认可；②L81 docstring 顺修按建议并入 B；③待决-2/3 维持未决，用户口径：当前外部环境开发、真实企业信息不可得，适配器**留口子**——协议中立可插拔/配置化，企业内基于开源版继续开发时替换真实 IdP 适配器）
- 历史遗留事项清单（supervised-coding 扫描汇总）：
  - **m1-3 移交必须项**：RFC 8693 act 对象形态兼容（其检查点 L82——「M2 需纳 RFC 8693 act 对象形态，现仅 str」）✅ 已入任务书 A3
  - m1-3 其余移交（multipart/upload_id 顺延、G-12 登记、P3-9→M1-4、P3-19✅m2-1 清偿）——均已闭环或已登记，无未了结项并入
  - m2-3 移交 m2-4：无（token 交叉项原定范围不变——B 项做兼容回归）
  - m2s-6 遗留：全部去向 m2-5/下批 followups/known-gap/用户侧——**无归 m2-4 项**
  - TC-PERF-05 → m2-5、TC-UI-01~04 → 用户侧（去向不变）
- **开工前置待决（须用户在确认时一并表态）**：**待决-2**（企业 SSO 协议——OIDC/CAS/自研？token 除 userId 外还带什么）与**待决-3**（agent 侧能否按用户换取委托 token——决定 D18 主方案与降级的生产启用顺序）——**不阻塞本段 POC 交付**（mock IdP/自签形态），但影响适配器形态预留与 m2-5 真实联调挂账口径；若用户本轮能给出倾向，任务书 A1 适配器形态按其细化。**表态结果（2026-11-01）**：两者维持未决——外部环境开发、真实企业信息不可得；A1 按协议中立可插拔接口+mock 实现交付（留口子），真实联调维持挂账 m2-5/部署期。

## 遗留事项（跨任务移交）
- [x] **本轮清偿**：m1-3 L82「RFC 8693 act 对象形态兼容——M2 SSO/JIT 落地必须项」✅ 本段 A3 交付闭环（act string/object/链式三形态+审计；链式取最外层=current actor 用户裁定按 RFC 8693 §4.1——来源 task-knowledge-lattice-m2-4，2026-11-01）；m2-3 token 交叉项 ✅ 兼容回归清偿；m1-3 L81 尾项 docstring ✅ 核验历史批次已修（B 项闭环零改动）
- [x] **移交 m2-6**：N-1（JIT 建档后 API 面成员开通缺口——用户裁定选 a：members 增/改/删入 m2-6 范围，_m2-plan row 7.5 已落）
- [x] **移交 m2-5/部署期**：真实 IdP/SSO 联调（待决-2/3 维持未决——SSO 验签器已留协议中立可插拔口子，与 rerank 真实网关联调同批）
- [x] **移交 known-gaps**：G-25（可信子系统限流器进程内态——线程锁已加，重开=多实例部署）、G-26（认证拒绝路径审计写放大——部署侧准入兜底）
- [x] **移交 followups（下批/m2-5 测试补强批）**：①P3-11 固化用例（org 解析顺序——行为已探针实证正确）②gate pg 正则 `\[pg[^]]*\]` 少计 [pg-*] 组合 id（口径已注 TEST-CASES v1.9.11）③test_auth_05 `_call` settings 形参残留（R2 签名调整机械残留）④`_outbox_insert` 完整性错误掩码（理论面）⑤MCP 面忽略审计先于 resolve_org 窄面（未来统一时移块——既定修法内生形态）
- [x] m1-3 L82 余量处置：multipart/upload_id 顺延确认（不做——任务书「不做」边界）、NFR-6 shared-storage 已登记 G-12 不动
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1: coder 完成（2026-11-01，**全新会话**，coderTaskId=ses_e6af9e2fbffe8jYdL2AMbMkP5m，commit `21778cd6c1294fd0361a44d84eaef4ce5e724ee0` 于 develop_opencode，15 files +1873/−32，父提交=eef7acf 同步确认）——A1 SSO 验签协议中立可插拔接口（SsoTokenVerifier Protocol + MockIdpVerifier 自签 JWT + build_sso_verifier 配置化工厂——**留口子裁定兑现**，LATTICE_SSO_PROVIDER none=缺省 dev/未知名 fail-closed）+ JIT 建档（store 双方言 upsert_user_jit：id 复用零更新/username 冲突 401 fail-closed/pg ON CONFLICT 回读定性；二次登录复用不覆盖——D16）；A2 委托 token（aud=knowledge-lattice 透传拒绝+auth.delegated 双身份审计+请求体权限字段忽略审计〔A-9——REST extra="allow"+MCP deprecated permissions 双面〕+org 沿 D18 resolve_org 对齐）；A3 act 对象形态（string/object{"sub"}/链式嵌套——**按 RFC 8693 §4.1 MUST 取最外层 sub=current actor、完整委托链进审计 act_chain**，非法形态 401+refused 审计）；A4 可信子系统三约束（LATTICE_TRUSTED_SERVICES_JSON 白名单真实载体〔sha256 不落明文/畸形构造即 raise fail-closed〕+allowed_orgs+按服务限流**共享态**〔曾修每请求新建限流器缺陷〕+X-On-Behalf-Of+X-User-Assertion 在场证据 sub 一致；拒绝路径全 outcome=refused 审计——T13 生产形态收口、期限②落实）；A5 T16 prod 复核（prod 域 SSO✓/dev JWT 401/静态 401 三断言+create_app(sso_verifier=) 装配分层，缺省 none 门禁零感知）；B：L81 核验两处 docstring 历史批次已修**闭环零改动**+m2-3 token 交叉项兼容回归（委托 token 过管理面鉴权链）。自测：GATE PASS **1556+1 双后端双模式 0 skipped**（pg 臂 556=523 参数化+33 专用；+77 逐文件对账 21+19+37）；TC-AUTH-03/04/05、T13、T16、act 对象形态用例全绿。机械核验（supervised-coding）：HEAD=21778cd 在 develop_opencode ✓、commit 格式 [taskId] R1 ✓、docs/prototype/检查点零改动 ✓、未 push ✓、工作区仅监督侧 3 流程文档 ✓。**择型申报 9 条**：①适配器接口 verify→SsoClaims（claims 归一在 adapter、aud/act/JIT 业务语义在 domain）②act 链式取最外层 sub（见边界①）③在场证据头名 X-User-Assertion（不做 aud 校验——身份断言签给 agent client）④白名单=env JSON+sha256 比对（mTLS 归真实部署期）⑤限流固定 60s 窗口 rpm 进程内、被拒不占合法配额 ⑥判定序白名单→协议件→sub→用户态→org→限流（最便宜拒绝优先）⑦可信声明用户不 JIT（须已建档，未建档 403）⑧权限字段识别键集 {permissions,roles,acl,grants,scopes} ⑨认证审计写失败即传播（AuthError.code 扩 429，MCP ToolError code 驱动）。**边界申报 4 条**：①**A3「最内层」字面 vs RFC 8693 §4.1 明文（最外层 act=current actor、嵌套仅信息性）张力——按 RFC MUST 实现且完整链保留进审计，若裁定按字面改动点仅 resolve_act_claim 一处**；②design §3 L150 注释「auth_sso.py：JIT 建档」为简写——JIT/降级判定实际落 domain/auth.py（分层纪律权威）；③透传拒绝机制=aud 校验（受众不含本服务即拒）；④B-L81 历史批次已修（api/search.py L9-11/resolve_org docstring 均已 v0.9.4 口径）。
- R1: tester **PASS**（2026-11-01，**全新会话**，testerTaskId=ses_e6d71dbaffeRGkGN6ujzH9Dx4，testedSha=21778cd 复核一致）——门禁独立复跑 **1556+1 双后端双模式 0 skipped**（pg 臂 556=523+33 与申报一致；+77 逐文件归因 21/19/37 ✓；1 deselected=manual TC-UI 门禁设计口径非 skip）；TC-AUTH-03/04/05、T13、T16、act 对象形态、B m2-3 交叉逐条勾验全 ✅（双后端 [pg] 实跑>0）；**重点面深查 10 项**：act 链式语义（RFC 8693 §4.1 原文实证——outermost act=current actor、MUST only consider、prior actors informational only；**验证口径意见：支持按 RFC MUST 实现**，任务书「最内层」字面属笔误性质，建议按 RFC 裁定并回写口径）/JIT 建档断言真实（首建三字段直查+复用 created_at 冻结+display_name 管理员优先+username 冲突 401 零落库）/upsert_user_jit 双方言行为同构（SQL 审读+[pg] 21 用例实跑）/透传拒绝边界正向实证（aud 缺失 401/数组多值含本服务接受/不含 401/非串 401——全 fail-closed）/A-9 双面+dev JWT 同款/可信子系统四拒绝+扩展路径全 refused reason 级断言+限流共享态 REST 真实+sha256 不落明文三面实证+被拒不占配额实证/fail-closed 面（未知名 provider/畸形白名单 7 形态/伪造 OBO 不降级/prod 验签失败不落静态分支）/装配分层缺省 none 门禁零感知/分层纪律（adapter 仅验签+归一、本轮零触及 core、auto_entities 钉层未破坏）/B-L81 属实。**注入验证 4 组**（act 取最内层/限流恒新建/aud 校验短路/复用分支覆盖——全红→恢复→绿，业务代码零残留）。**择型 9 条全 ACCEPT；边界 4 条全属实**（①建议按 RFC 裁定回写任务书口径）。**P1/P2 无；P3×3**（MCP 可信接线层无专项用例/aud 边界未固化 parametrize/被拒不占配额断言可加强）；观察 3 条（限流进程内不跨进程——候选 known-gaps 登记/REST 可信面 org 缺失断言/仅 X-User-Assertion 401 fail-closed 正确）。临时产物清理：pg 遗留 schema=0、临时库/注入备份/日志全删。报告全文见「最新验证意见原文」details 块（R1 Tester）。
- R1: committer **NEEDS_CHANGES**（2026-11-01，**全新会话**，committerTaskId=ses_e6ac6e05fffeaTfE069ljMpJpz，reviewedSha=21778cd=testedSha=HEAD 三一致；R1 首审 diff=eef7acf..21778cd 全量 15 files 逐文件核对；门禁采信 Tester 独立复跑+静态计数对账自洽——沿先例）——A1~A5+B 逐项语义审查全 ✅（分层纪律/双方言等价/越权绕过面无新 P1）；安全性深审 7 面全 ✅（算法钉死 HS256/prod 无静态 token 逃生/aud 完备/sha256 时序不可行/审计不吞异常链路完整/信息泄露两处 P3）。**择型 9 条全 ACCEPT；边界 4 条全 CONFIRMED**（①act 按 RFC 用户已裁定无需改码，docs 批补注记；②design §3 L150 登记非决策勘误；③④属实）。**P1 无；P2×2**：**P2-1** mcp/server.py 可信子系统分支提前 return 跳过 param_org（mcp.org_param_ignored）与 param_permissions（auth.request_permissions_ignored）忽略审计——违反 D18/§5.5「工具参数 org 一律忽略并记审计」与 FR-4/A-9（对一切认证形态），且正是 Tester P3-1「MCP 可信接线无专项用例」掩盖的缺陷（修法=忽略审计抽公共块上提至认证成功后分支返回前；REST 面不受影响）；**P2-2** build_sso_verifier mock-idp 无环境护栏——sso_mock_secret 缺省 "dev-mock-idp-secret" 公开常量，prod 误开+缺省密钥=任何人可签任意 sub 含既有管理员 id 全身份伪造（修法=prod+公开缺省密钥组合构造即 raise，只拦缺省值不拦 mock 形态；或登记 G-27 需显式裁定不静默）。**P3×12**（P3-1 畸形白名单 from_json 缺 service_id 分支消息含 token 明文/P3-2 claims 类型归一不全 sub 非 str 透传+org 等非 str 落 500/P3-3 Bearer 前缀大小写敏感/P3-4 未强制 exp·iss 存在与 iss 校验/P3-5 JIT 建档与审计非同事务窄窗/P3-6 missing sub·user disabled 无拒绝审计事件/P3-7 username 冲突消息回显他用户 id/P3-8 限流器无锁+进程内→G-25/P3-9 unknown_service 拒绝审计可无界写放大→G-26/P3-10 卫生×3/P3-11 权限忽略审计先于 org 解析/P3-12 IntegrityError 递归无上限理论面）。**Tester P3×3/观察 3 条处置裁定**：P3-1→R2 必须修（与 P2-1 同批补 MCP 可信专项用例）；P3-2 aud 边界 parametrize→R2 顺手；P3-3 第 4 次仍 429 断言→R2 顺手；观察1 限流进程内→登记 **G-25**；观察2 org 缺失断言→R2 顺手；观察3→不动。**需求边界 N-1 上报**（JIT 建档后 API 面无法把新用户加入组织——PUT grants/CSV 均要求既有 membership〔admin.py:234、416〕、m2-6 计划仅 members GET/values CRUD 无成员增改，D16「管理员不建账号只配授权」API 面不闭环——建议 m2-6 扩 members 增改删或 known-gaps 登记「POC 成员关系经 DB/seed 开通」+runbook，**待用户裁定**）；**N-2 文档空白**（X-User-Assertion 头名/白名单载体/act 链式口径/JIT 复用语义四处+MCP permissions 参数载体——随 docs 批非决策回写固化，无需裁定）。**docs 批建议**：TEST-CASES v1.9.11 完成态注记+known-gaps G-25/G-26（视 P2-2 裁定 G-27）+design v0.9.7 §3 L150 勘误+§5.5 实现口径注记+AGENTS/_m2-plan 终态。**遗留事项去向建议**：m1-3 L82 act 移交→本段闭环回写；真实 IdP 联调→维持 m2-5/部署期；P3-2~12 余项→known-gaps/下批；N-1→m2-6 或 known-gaps 待裁定。**R2 建议范围**：P2-1（含 MCP 可信专项用例+观察2 补强）+P2-2 护栏+P3-1~P3-4 顺手+Tester P3-2/P3-3 断言强化；门禁重跑申报（预期 1556+1+N）。报告全文见「最新验证意见原文」details 块（R1 Committer）。
- **R1→R2 边界裁定（2026-11-01 用户，fixing→implementing，round 1→2，reviewedSha 置空）**：**N-1 选 a**——m2-6 任务范围扩为 members 增/改/删（JIT 建档后 API 面开通链路闭环；_m2-plan row 7.5 同步补记）；**P2-2 直接修**（不登记 G-27）；**应修尽修口径**——R2 范围：P2-1（含 MCP 可信专项用例+观察2 org 缺除断言）+P2-2 护栏+P3-1/2/3/4/5/6/7/10/11/12 全修+P3-8 线程锁可修部分（进程内态登记 G-25——单进程 NFR 约束下架构项非缺陷）+Tester P3-2（aud 边界 parametrize）/P3-3（第 4 次仍 429）；**P3-9 登记 G-26 不修**（unknown_service 拒绝审计无界写 vs 设计强制 refused 审计——代码无正解的架构权衡，部署侧准入兜底，随 docs 批登记）；G-25/G-26 登记随 docs 批（监督侧落笔）。N-2 文档空白四处随 docs 批非决策回写。
- R2: coder 完成（2026-11-01，**续接会话**，coderTaskId=ses_e6af9e2fbffe8jYdL2AMbMkP5m，commit `b24896e` 于 develop_opencode，12 files +562/−118，父提交=21778cd，origin/develop=eef7acf 无前进确认，未 push）——**P2-1** ✅ `_auth_and_org` 重构：trusted 分支提前 return 与 _org_from_header 删除，org/permissions 忽略审计抽公共块置于认证成功后、统一 resolve_org 前（一切认证形态生效）+OrgContextError 统一 400；MCP 可信专项用例×2（trusted+search(org+permissions) 双事件 200 / MCP 冒充 403+refused）+观察2（REST trusted 无 X-Org-Id → 400）。**P2-2** ✅ DEFAULT_SSO_MOCK_SECRET 模块常量+prod+mock-idp+公开缺省密钥 → ValueError fail-closed（三态用例：prod+缺省拒/prod+显式放/test+缺省放）。**P3 全修**：P3-1 from_json 消息只带键名（leak-me-secret 不进异常 7 参断言）/P3-2 _opt_str 归一（实证 pyjwt 库层已强制 sub str——int sub 验签即拒，_opt_str 为适配器层双保险）/P3-3 Bearer 前缀大小写不敏感/P3-4 require exp·iss+真实适配器 TODO/P3-5 **JIT 建档与审计同事务**（按 create_upload_credential audit= 先例真同事务：BEGIN IMMEDIATE/BEGIN+_outbox_insert+COMMIT/rollback，仅实际插入写 outbox；崩溃注入 _outbox_insert raise → users 零残留行）/P3-6 missing_sub+user_disabled 补 auth.sso_refused（SSO 语义拒绝四类齐）/P3-7 双方言冲突消息泛化不回显他用户 id/P3-8 ServiceRateLimiter 加 threading.Lock（Barrier(4)×300 并发放行恰=limit——进程内态不改，G-25 申报）/P3-10 卫生×3（authenticate_trusted 删 settings 参/F401 删/docstring 更新）/P3-11 org 解析成功后再记 ignored_fields（400 请求不混入忽略事件）/P3-12 递归上限 3+RuntimeError。**断言强化**：aud 四参 parametrize×双后端（pg 组合 id [pg-missing] 全实跑）/rate_limited 第 4 次仍 429。**不修确认**：P3-9（G-26 申报）/N-1（membership 零触碰）/观察3 未动。自测：TDD 红→绿逐项（P2-1 org_events 0==1 红/P2-2/P3-5 残留行/P3-6/P3-4/P3-1 红）；GATE PASS **1580+1 双后端双模式 0 skipped**（pg 臂 561=528+33；+24 对账 9+8+7=auth_03 21→30/auth_04 19→27/auth_05 37→44）。机械核验（supervised-coding）：HEAD=b24896e ✓、commit 格式 R2 ✓、docs/prototype/检查点零改动 ✓、未 push ✓、工作区仅监督侧 3 文档 ✓。**择型申报 4 条**：①P3-5 真同事务（audit= 先例，并发复用不重复写审计由 INSERT 成功路径承载）②P3-2 防线归属（pyjwt 层强制 sub str=_opt_str 双保险，未为凑审计口径弱化验签）③P3-6 审计面边界（SSO 事件覆盖语义拒绝四类；验签失败不记身份事件——与 trusted refused 审计〔T13 设计明令〕不矛盾）④限流测试 Barrier(4)×300 整除对齐（曾因 Barrier(8) 非整除挂起修正；断言恰=limit 同时覆盖超发与误拒两向）。
- R2: tester **PASS**（2026-11-01，**新会话**〔R1 Tester 会话 ses_e6d71dbaffeRGkGN6ujzH9Dx4 过期续接失败——监督侧重开并指示从检查点恢复上下文，testerTaskId 已更新为 ses_e6a989552ffeC2McLt2BxO5ye2〕，testedSha=b24896e 全 SHA 复核一致）——门禁独立复跑 **1580+1 双后端双模式 0 skipped**（pg 臂 561=528+33 一致；+24 逐文件对账 30/27/44 ✓；aud 四参 pg 组合 id [pg-*] 形态确认全实跑；1 deselected=manual 非跳过）。**修复闭环逐项勾验**：P2-1（公共块单一直线路径四形态全生效+双事件精确计数非恒真+OrgContextError/AuthError 独立无吞噬）/P2-2（三态+只拦缺省组合+P2-5 口径对齐）/P3×10 逐项 ✅（P3-5 双方言同事务审读：sqlite 事务内重查〔clash 预查移入事务消除 TOCTOU 顺带增强〕与 pg ON CONFLICT RETURNING 等价、递归参数不对称语义正确；P3-8 锁不损语义第 3/4 次 429 同绿）；断言强化×2 ✅；**不修项×3 零触碰确认**（P3-9 diff 零改动/N-1 无 admin.py/观察3 未动）。回归零弱化（无删测试/断言；2 既有函数纯增强；R1 77 条全在 1580 内绿）。**注入验证 2 组**（①恢复 R1 trusted 提前 return→双事件用例红；②sqlite COMMIT 提前到 outbox 前→崩溃注入用例红〔users 残留被捕获〕——全红→byte-identical 恢复→绿，备份已删）。**择型 4 条全 ACCEPT**（①audit= 先例同生共死实证 ②pyjwt InvalidSubjectError 本机实证〔2.15.1〕③四类 reason grep 核对齐+验签失败无身份可记口径不冲突 ④Barrier 无死锁 1.75s 通过+sum==200 两向锁死）。**P1/P2 无；P3×1**（P3-11 固化用例缺——本机探针已证行为正确〔400×2→0 事件/200→恰 1〕，建议下批补防回归）；**观察 1**（MCP 面忽略审计先于 resolve_org 的窄面——既定修法内生形态非缺陷，trusted 不受影响，未来统一时移块即可）。临时产物清理：pg 遗留 schema=0、注入备份×2+probe 目录已删。报告全文见「最新验证意见原文」details 块（R2 Tester）。
- R2: committer **APPROVED**（2026-11-01，**续接会话**，committerTaskId=ses_e6ac6e05fffeaTfE069ljMpJpz，reviewedSha=b24896e=testedSha=HEAD 三一致；R2 diff=21778cd..b24896e 12 files 逐文件核对；门禁采信 R2 Tester 独立复跑+静态计数对账自洽）——**R1 意见闭环核验**：P2-1 真闭环（单一直线路径无分叉、无 early return、auth 双分支均赋值、AuthError/OrgContextError 互不吞噬；注入①转红实证）/P2-2 闭环且无绕过（**值相等判定**——env 显式设同值同样被拒，比「是否显式配置」更强口径；三态用例齐）；P3×10 全修逐条 ✅（P3-5 与 create_upload_credential 先例**逐字同形**、双后端崩溃注入实证、sqlite TOCTOU 顺带消除）；不修项 P3-9/N-1/观察3 零触碰确认；N-1 已按用户裁定 a 归 m2-6（plan 预落）。**未弱化确认**：零 def 删除/零断言删除、2 既有函数纯增强、无 skip/xfail。**计数对账**：+24 逐文件精确（9/8/7）；**pg 臂口径说明**（gate 561=528+33 的 grep '\[pg\]' 少计 [pg-*] 组合 4 条——真实 pg 实例 565，总数与 0 skipped 不受影响；建议 manifest 注明口径+可选正则改 \[pg[^]]*\]）。**语义安全复审**：P2-1 四形态控制流无新绕过；P2-2 启动即 raise fail-closed；P3-5 双方言事务同构（pg 先例逐字同形/inserted None 先 COMMIT 再递归 audit=None）；P3-8 单锁无嵌套无死锁；安全面回归全绿（P2-2 反而加严/P3-1 反向收口）。**R2 择型 4 条全 ACCEPT**；R1 择型 9/边界 4 结论继续有效。**P1/P2 无；P3×5 登记级**（P3-11 固化用例缺〔Tester P3-1〕→followups 不开 R3/MCP 审计顺序窄面〔既定修法内生〕→不动/gate pg 正则少计→manifest 注明+可选 followup/test _call settings 形参残留/理论面 _outbox_insert 完整性错误掩码→登记）。**需求边界无新增**（N-1 裁定归 m2-6 确认/N-2 维持 docs 批）。**交付把关建议**：docs 批终版清单（TEST-CASES v1.9.9→v1.9.11 完成态注记+known-gaps G-25〔线程锁已加+进程内态〕/G-26+design v0.9.7 §3 L150 勘误+§5.5 实现口径+AGENTS/_m2-plan row7 终态）+遗留回写（m1-3 L82 act 闭环/真实 IdP→m2-5/N-1→m2-6/followups 五项）+manifest 要点（双 SHA 对齐/docs-only 归档 commit 需 doc-only 复核/门禁原始输出+pg 口径双注/rounds=2/specRulings 三批/gapClosures/handover/stale=false）。报告全文见「最新验证意见原文」details 块（R2 Committer）。
- **双通过达成（2026-11-01 13:05，round=2 收敛）**：testVerdict=PASS + reviewVerdict=APPROVED，testedSha=reviewedSha=b24896e=当前 HEAD——status=approved，待用户确认交付。

## 最新验证意见原文

<details>
<summary>R1 Tester 报告（ses_e6d71dbaffeRGkGN6ujzH9Dx4，2026-11-01）</summary>

# task-knowledge-lattice-m2-4 R1 验证报告

## 1. 验证环境与前置校验

| 项 | 结果 |
|---|---|
| HEAD | `21778cd6c1294fd0361a44d84eaef4ce5e724ee0` ✓ |
| 父提交 | `eef7acf1412c90f1e97f3993d129423fd215a319` ✓（与申报一致） |
| 分支 | develop_opencode ✓ |
| push 状态 | ahead of origin/develop_opencode by 2（未 push）✓ |
| 工作区 | 仅监督侧 3 流程文档（_m2-plan.md、task-knowledge-lattice-m2s-6.md 改 + task-knowledge-lattice-m2-4.md 未跟踪）——豁免面 ✓ |
| docs/prototype/ | 零改动（diff 全量 15 files +1873/−32 清单内核验）✓ |
| 验证期间 git 写操作 | 零（一次 `git checkout` 尝试被权限系统 deny，改用 python 反向替换恢复） |

## 2. 门禁独立复跑结果与计数对账

```
docker start lattice-pg && export LATTICE_PG_DSN=... && scripts/test_gate.sh
[pytest]    OK：1556 passed, 1 deselected, 122 warnings
[pytest-O]  OK：1556 passed, 1 deselected, 123 warnings
GATE PASS: sqlite+pg 双后端、双模式全绿，0 skipped（pg 臂 556 = [pg] 参数化 523 + PG 专用 33）
```

- **计数对账**：1556+1 与 coder 申报完全一致；pg 臂 556=523+33 一致
- **+77 逐文件归因**：test_auth_03=21 / test_auth_04=19 / test_auth_05=37（pytest --collect-only 逐文件实数）= 77 ✓
- **skip 核对**：0 skipped（1 deselected = manual 标记 TC-UI，门禁设计排除口径，非 skip）
- **回归零弱化**：基线 1479+1 → 1556+1，差恰为 +77 纯新增；`git diff eef7acf..21778cd` 测试目录仅 3 个新文件、**存量测试文件零改动零删除** ✓；python -O 双模式全量 ✓

## 3. TC-AUTH-03/04/05、T13、T16 逐条勾验表

| 用例 | 用例定义（TEST-CASES） | 实现 | 断言强度 | 判定 |
|---|---|---|---|---|
| TC-AUTH-03 ① | mock SSO 首验通过→users 落库 id/username/display_name | upsert_user_jit 双方言+EVENT_AUTH_USER_JIT | 直查 users 行三字段+JIT 事件=1 | ✅ 绿（双后端） |
| TC-AUTH-03 ② | 二次登录复用 | existing 分支零更新 | created_at 不变+管理员改动不被覆盖+行数=1+JIT 事件仍=1 | ✅ 绿（双后端） |
| TC-AUTH-03 扩展 | — | username 冲突 fail-closed | 401+users 零落库（不静默顶替） | ✅ 绿 |
| TC-AUTH-04 主 | aud/sub/act/org 委托 token 按 sub 计权+act 审计 | _authenticate_sso_claims+EVENT_AUTH_DELEGATED | user_id=sub、act 双身份事件三字段断言 | ✅ 绿（双后端） |
| TC-AUTH-04 透传 | 用户原始 token→拒绝 | aud 校验 audience_mismatch | 401+auth.sso_refused 事件 reason 断言 | ✅ 绿（双后端） |
| TC-AUTH-04 A-9 | 请求体权限字段→忽略+审计+正常处理 | SearchRequest extra="allow"+五键集+MCP deprecated permissions | REST 200+ignored_fields≥{permissions,roles,acl}+事件=1；MCP 同；dev JWT 路径同款 | ✅ 绿（双后端） |
| TC-AUTH-05 ① | 三约束齐备→按声明用户计权、双身份审计 | authenticate_trusted accepted | via=trusted+act=service_id+事件(service_id,user_id,org) | ✅ 绿（双后端） |
| TC-AUTH-05 ② | org 越界→拒绝并审计 | org_not_allowed 403 | refused 事件 reason+service_id | ✅ 绿（双后端） |
| TC-AUTH-05 ③ | sub 不符（冒充）→拒绝并审计 | subject_mismatch 403 | refused 事件+user_id=u_victim | ✅ 绿（双后端） |
| TC-AUTH-05 ④ | 白名单外→拒绝并审计 | unknown_service 401 | refused 事件 service_id=None | ✅ 绿（双后端） |
| T13 生产形态 | 真实白名单载体+refused 审计 | LATTICE_TRUSTED_SERVICES_JSON+全拒绝路径 outcome=refused | 扩展路径（无白名单/缺断言/坏断言/未建档/禁用/限流）全有 reason 级断言；REST 集成 3 条含伪造 OBO 不降级 | ✅ 绿（双后端） |
| T16 | prod token 端点 404+生产 auth 形态 | 既有 test_dev_token_prod_404（test_auth_01:71）+本轮 test_prod_sso_accepted_dev_forms_rejected | prod 三断言：SSO✓/dev JWT 401/静态 401 | ✅ 绿（双后端） |
| act 对象形态（m1-3 移交） | string/object/链式+非法拒绝审计 | resolve_act_claim | 对象 sub/链式最外层/尾端 string 宽容/6 非法形态 401+invalid_act | ✅ 绿（双后端） |
| B m2-3 交叉 | 委托 token 过管理面鉴权链 | get_auth→org_scoped | 403（非 admin）→升 admin 200 | ✅ 绿 |

## 4. 重点面深查

1. **act 链式语义（边界①）**：已拉取 RFC 8693 §4.1 原文实证——"The **outermost** act claim represents the **current actor**…For the purpose of applying access control policy, the consumer of a token **MUST only consider**…the current actor. Prior actors…are **informational only**." 任务书 A3 字面「`act.sub` 取最内层」与 RFC MUST 相反。coder 按 RFC 实现（最外层 sub=ctx.act+审计主标识、act_chain=["svc-16","svc-77"] 全链进审计）+ 用例 docstring 明示口径。**验证口径意见：支持按 RFC MUST 实现**——RFC 是规范强制级、任务书字面属笔误性质；完整链进审计已保留任务书想要的追溯能力，无信息损失。建议监督侧按 RFC 裁定并向任务书回写口径（「最外层=current actor」）。
2. **JIT 建档**：首次落库三字段直查、二次复用 created_at 冻结+display_name 管理员优先、username 冲突 401 且零落库、username 缺失回退 sub——断言均真实（注入④证明）。
3. **upsert_user_jit 双方言等价**：SQL 审读——sqlite（显式 clash 预查 + IntegrityError 并发兜底回读递归）与 pg（`ON CONFLICT (id) DO NOTHING RETURNING` + UniqueViolation 时回读定性 + inserted None 并发窗口递归复用）行为同构；[pg] 臂 21 用例门禁实跑全绿。
4. **透传拒绝边界（本机正向实证）**：aud 缺失（claim 不存在）→401；aud 数组多值含本服务→接受（RFC 受众语义正确）；多值不含→401；aud 非串（数字）→归一空元组→401。全 fail-closed ✓。
5. **A-9 双面**：REST 五键集识别（model_extra）+审计+200 正常处理；MCP deprecated permissions 参数同；dev JWT 路径同款口径（FR-4 对一切认证形态生效）。
6. **可信子系统**：四拒绝路径+no_whitelist+unknown_user+disabled_user+rate_limited 全部 outcome=refused 断言（reason 级）；accepted 双身份（service_id+user_id）；限流共享态 REST 真实（3 请求第 3 次 429，注入②证明断言绑定共享态）；**sha256 不落明文本机实证**（registry 内存序列化无明文、畸形配置异常消息无明文、条目仅存 hash）；**被拒不占配额实证**（拒绝后窗口不重置不回退，60s 后新窗口放行）。
7. **fail-closed 面**：未知名 sso provider 构造即 ValueError；畸形白名单 7 形态 parametrize 构造即 raise；伪造 X-On-Behalf-Of 不降级（unknown_service 401）；prod 下 SSO 验签失败落回后 prod 直接 raise（不进静态分支）。
8. **装配分层**：create_app(sso_verifier=) 显式注入优先/缺省 build_sso_verifier(none)=None——门禁 1556 全绿即存量测试零感知实证 ✓。
9. **分层纪律**：adapters/auth_sso.py 仅验签+claims 归一（aud tuple 归一）+工厂——aud 校验/act 解析/JIT/审计全在 domain/auth.py ✓；本轮 diff 零触及 core/ 包（无方言 SQL 风险）；auto_entities 识别钉 api/mcp 未破坏（core/docs/retrieve.py:236 不识别注释仍在、resolve_query_entities 由调用方注入）✓。
10. **B-L81**：api/search.py 与 resolve_org docstring 均为新口径、本轮对该两处零改动——「已修闭环零改动」申报属实 ✓。

## 5. 注入验证证据（4 组，全部 红→恢复→绿）

| # | 注入点 | 期望红 | 实测 |
|---|---|---|---|
| ① | resolve_act_claim `chain[0]`→`chain[-1]`（取最内层） | test_delegated_act_nested_chain | **FAILED** ✓ → 恢复后 2 passed |
| ② | limiter 解析绕过 registry 共享态（恒新建） | test_trusted_rest_rate_limited | **FAILED** ✓ → 恢复后 1 passed |
| ③ | aud 校验 `if False and ...` | test_passthrough_user_token_rejected_and_audited | **FAILED** ✓ → 恢复后 1 passed |
| ④ | sqlite upsert_user_jit 复用分支加 UPDATE 覆盖 | test_sso_second_login_reuses_row | **FAILED** ✓ → 恢复后 1 passed |

恢复后 `git diff --stat` 业务代码零残留（工作区仅监督侧流程文档）。四处断言均真实绑定防线，无 mock 假断言/恒真断言。

## 6. 择型/边界裁定建议

**择型 9 条：全部 ACCEPT**
① adapter 归一/domain 语义分层清晰 ✓；② RFC MUST（原文已核）+全链保留 ✓；③ 断言非访问 token 不做 aud 校验、exp 照常有专项用例 ✓；④ sha256 比对+不落明文三面实证，mTLS 归部署期合理 ✓；⑤ 60s 固定窗口+被拒不重置实证、进程内共享态 REST 实证 ✓；⑥ 判定序最便宜拒绝优先（sha256 查找→协议件→验签→sub→用户态→org→限流）合理 ✓；⑦ unknown_user 403 与 JIT 语义区分正确（防白名单服务无断言扫库建号）✓；⑧ 五键集常见命名收敛合理、其余未知字段本不进模型 ✓；⑨ _audit 不吞异常+AuthError.code=429+app handler `status_code=exc.code`+MCP ToolError code 驱动，链路完整 ✓。

**边界 4 条：全部核验属实**。①属实（RFC 原文矛盾实证，建议按 RFC 裁定并回写任务书口径）；②属实（design §3 L150 为简写，实落 domain 更符合分层权威）；③属实（audience_mismatch 机制实证）；④属实（两处 docstring 已是新口径、零改动）。

## 7. 新发现问题分级

**P1（阻塞）**：无。 **P2（应修）**：无。

**P3（建议，不阻塞）**：
1. **MCP 可信子系统接线层无专项用例**：mcp/server.py `_auth_and_org` 的 on_behalf_of/user_assertion 分支仅靠域函数测试间接覆盖（REST 面有 app 级全链用例、MCP 面只有 permissions 参数用例）——建议补 1 条 MCP 形态可信路径用例。
2. **aud 边界无固化用例**：缺失/数组多值/非串行为已正确（本机实证），建议 parametrize 固化，防回归。
3. **限流「被拒不占配额」断言可加强**：现用例止于第 3 次拒绝，未断言第 4 次仍拒（窗口不重置）——行为已实证正确。

**观察项**：
1. ServiceRateLimiter 为进程内存态——未来多进程/多实例部署时限流不跨进程共享（单进程零中间件 NFR 下合理，候选 known-gaps 登记）。
2. 可信路径 REST 面未测「org 缺失（无 X-Org-Id）」断言（域函数已测 400）。
3. 仅带 X-User-Assertion 不带 X-On-Behalf-Of → missing_on_behalf_of 401+refused（域测试 obo=None 覆盖，fail-closed 正确）。

## 8. 结论

- **testVerdict: PASS**
- testedSha = `21778cd6c1294fd0361a44d84eaef4ce5e724ee0`（HEAD 复核一致，验证期间零 git 写操作）
- 门禁独立复跑 GATE PASS：1556+1 双后端双模式 0 skipped，与申报逐项对账一致
- TC-AUTH-03/04/05、T13、T16、act 对象形态用例全绿（双后端 [pg] 实跑数 >0）
- 4 组注入实证断言真实、业务代码零残留
- 临时产物清理声明：pg 遗留 schema=0（psql 直查 pg_namespace=0）；aud-probe 临时库×2、inject-bak、gate log 已删；测试数据零落仓库

P3 三条建议随下轮或 followups 批次处理即可，不阻塞本段收口。

</details>

<details>
<summary>R2 Tester 报告（ses_e6a989552ffeC2McLt2BxO5ye2〔新会话——R1 会话过期〕，2026-11-01，testVerdict=PASS）</summary>

# task-knowledge-lattice-m2-4 R2 验证报告

## 1. 前置校验

| 项 | 结果 |
|---|---|
| HEAD | `b24896e300c2b03f4c8d143d0ec1119e7d059906` ✓（= testedSha 申报） |
| 父提交 | `21778cd`（R1 SHA）✓ |
| 分支 | develop_opencode；ahead of origin/develop_opencode by 3（R1×2 + R2×1）——**未 push** ✓ |
| R2 diff | `21778cd..b24896e` = 12 files +562/−118，与申报逐文件一致 ✓ |
| 工作区 | 仅监督侧 3 流程文档（_m2-plan.md、task-m2s-6.md 改 + task-m2-4.md 未跟踪）——豁免面 ✓ |
| docs/prototype/检查点 | 提交内零改动（12 files 清单内核验 + name-only 无 docs/prototype 匹配）✓ |
| 验证期间 git 写操作 | 零（业务文件注入用 python 替换+备份恢复，恢复后 `git status src/` 零输出证明 byte-identical） |

## 2. 门禁独立复跑与计数对账

```
docker start lattice-pg && export LATTICE_PG_DSN=... && scripts/test_gate.sh
[pytest]    OK：1580 passed, 1 deselected, 165 warnings
[pytest-O]  OK：1580 passed, 1 deselected, 165 warnings
GATE PASS: sqlite+pg 双后端、双模式全绿，0 skipped（pg 臂 561 条全实跑：[pg] 参数化 528 + PG 专用 33）
```

- **与申报对账**：1580+1 与 coder 申报一致；pg 臂 561=528+33 一致
- **+24 逐文件归因（--collect-only 实数）**：auth_03 21→**30**（+9 = 4 新参数化函数×2 后端 + 1 非参数化）/ auth_04 19→**27**（+8 = aud 四参×2 后端）/ auth_05 37→**44**（+7 = bearer×2 + malformed 扩 1 条 + 4 新非参数化）✓
- **pg 臂 aud 四参核实**：`[pg-missing]/[pg-multi-contains]/[pg-multi-excludes]/[pg-non-string]` 组合 id 形态确认（grep `\[pg\]` 不计但全实跑），8 条单跑全绿 ✓
- **skip 核对**：0 skipped；1 deselected = manual 标记 TC-UI（门禁设计排除口径，非 skip）
- **回归零弱化**：`git diff tests/` 无任何 `-def test_`、无删除断言行——存量测试零删除零放宽；2 个既有函数获**纯增强**断言（missing_sub 补 refused 审计 / username 冲突补不回显）；`authenticate_trusted` 签名删 settings 的机械适配不涉语义。R1 已验 77 条全在 1580 内全绿

## 3. 修复闭环逐项勾验表

| 项 | 代码落点 | 测试断言 | 实证 | 判定 |
|---|---|---|---|---|
| **P2-1** MCP 可信审计公共块 | mcp/server.py `_auth_and_org`：trusted 提前 return 与 `_org_from_header` 删除；param_org/param_permissions 审计公共块置于认证成功后（try/except 之外）、统一 resolve_org 前——四种认证形态单一路径全生效 | `test_mcp_trusted_search_param_ignore_audited`（org_events==**1** ∧ perm_events==**1** 精确计数非恒真）+ `test_mcp_trusted_impersonation_403`（ToolError 403 + refused reason=subject_mismatch）| **注入①红**（恢复提前 return → 双事件用例 FAILED）→ 恢复绿；OrgContextError 独立于 AuthError（均直接继承 Exception），统一 400 映射正确 | ✅ |
| **P2-2** mock 密钥 prod 护栏 | config.py `DEFAULT_SSO_MOCK_SECRET` 模块常量（dataclass 缺省+get_settings 均引用）；build_sso_verifier：prod+mock-idp+缺省值 → ValueError | 三态用例：prod+缺省拒（断言消息含 LATTICE_SSO_MOCK_SECRET）/ prod+显式密钥放（isinstance MockIdpVerifier）/ test+缺省放 | 门禁绿；护栏只拦「公开缺省值+prod」组合，mock 形态本身与 dev JWT P2-5 口径对齐 | ✅ |
| P3-1 | from_json 缺 service_id 分支消息改 `条目键：{sorted(item)}`；顺带「条目须为对象」改报类型名 | malformed parametrize 7→8 条（新增条目非对象）+ `leak-me-secret not in str(exc)` 逐条断言 | 门禁绿 | ✅ |
| P3-2 | `_opt_str`（非 str→None）：sub 归一后空→missing_sub；org/username/display_name 降级 | `test_sso_nonstring_claims_normalized`（int sub 401+零建档；org=99/username list/display_name dict 降级 None 建档成功 username 回退 sub） | **择型②本机实证**：pyjwt 2.15.1 `jwt.decode` 对 int sub 即抛 `InvalidSubjectError: Subject must be a string` ✓ | ✅ |
| P3-3 | `removeprefix("Bearer ")` → `lower().startswith("bearer ")` 裁剪 | `test_trusted_assertion_bearer_prefix_case_insensitive`（"bearer " 小写接受）双臂绿 | 门禁绿 | ✅ |
| P3-4 | `options={"require": ["exp","iss"]}` + verify docstring 真实适配器 TODO（iss 白名单+JWKS） | `test_sso_token_without_exp_rejected`（手工无 exp token → 401）双臂绿 | 门禁绿 | ✅ |
| **P3-5** JIT 同事务 | 双方言 `upsert_user_jit(audit=)`：sqlite BEGIN IMMEDIATE→事务内重查→INSERT→`_outbox_insert`→COMMIT；pg BEGIN→INSERT ON CONFLICT RETURNING→`_outbox_insert`→COMMIT；`except BaseException: _rollback()+raise`；协议 docstring 沿 create_upload_credential audit= 先例 | `test_jit_user_row_and_audit_atomic` 双臂：monkeypatch `_outbox_insert` raise → 断言 users **零残留行** | **注入②红**（COMMIT 提前到 outbox 前 → sqlite 臂 FAILED）→ 恢复绿；「仅实际插入写 outbox」：sqlite existing 复用分支/事务内重查命中均不写，pg inserted=None 复用传 audit=None | ✅ |
| P3-6 | missing_sub / user_disabled 补 `auth.sso_refused`（reason 级） | 两专项用例（events==1 + reason 过滤断言）双臂绿 | SSO 语义拒绝四类齐：audience_mismatch（auth_04:151）/ missing_sub（auth_03:204）/ invalid_act（auth_04:167）/ user_disabled（auth_03:278）——grep 逐一核对 ✓ | ✅ |
| P3-7 | 双方言冲突消息泛化「已被其他账号占用（不回显占用者）」 | 既有用例补 `assert "u_existing" not in str(exc)` 双臂绿 | 门禁绿 | ✅ |
| P3-8 | ServiceRateLimiter `threading.Lock` 全程持锁；进程内态不改（G-25 申报） | `test_rate_limiter_thread_safe`：Barrier(4) 对齐 ×300 任务（300%4==0 无死锁）→ `sum(results)==200` 恰=limit（超发/误拒两向覆盖） | 门禁绿（无挂起）；`test_trusted_rest_rate_limited` 既有共享态用例同绿 | ✅ |
| P3-10 卫生×3 | `authenticate_trusted` 删 settings 参（upload.py/mcp/server.py/tests 3 处调用同步）；`SsoClaims` F401 导入删；upload.py docstring 更新（401/403/429/400） | —（机械卫生） | 门禁绿 | ✅ |
| P3-11 | api/search.py `resolve_org` 提前到权限忽略审计之前 | coder 未加固化用例（见 §7 P3-1） | **本机探针 PASS**：org 不一致 400→ignored 事件 0；org 全缺 400→0；org 正常 200→恰 1 | ✅ |
| P3-12 | 双方言 `_depth>=3 → RuntimeError` | —（防御性收口，理论不可达路径） | 代码审读：IntegrityError/inserted=None 递归均传 _depth+1 ✓ | ✅ |
| 断言强化① | — | aud 四参 parametrize（missing/multi-contains/multi-excludes/non-string）×双后端 | 8 条单跑全绿（含 pg 组合形态 4 条） | ✅ |
| 断言强化② | — | `test_trusted_rest_rate_limited` 补第 4 次仍 429（窗口不重置） | 门禁绿 | ✅ |
| 不修：P3-9 | domain/auth.py diff 中 unknown_service/_refuse 代码行**零改动**（唯一匹配为 P3-6 docstring 文字） | — | diff 审读 ✓ | ✅ 零触碰 |
| 不修：N-1 membership | diff 无 admin.py、无 membership 写路径 | — | name-only 核对 ✓ | ✅ 零触碰 |
| 不修：观察3 | 无相关改动 | — | diff 审读 ✓ | ✅ 零触碰 |

## 4. 重点面深查

1. **P2-1 四种认证形态全路径**：重构后认证 try/except → 审计公共块 → resolve_org 单一直线路径，trusted/dev JWT/SSO/委托不再有分叉——R1 缺陷面（trusted 跳过）经注入实证确已消除；既有 `test_mcp_search_permissions_param_ignored_and_audited` + org 三档用例重构后仍绿（兼容性）。
2. **P2-2 与 P2-5 口径对齐**：只拦「公开缺省值 + prod」三元组合；test 环境缺省密钥放行保证本地零配置与门禁零感知（1580 全绿即证）。
3. **P3-5 双方言行为等价**：sqlite 事务内重查（BEGIN IMMEDIATE 串行化后复用语义）与 pg ON CONFLICT RETURNING 判定等价；递归参数不对称（sqlite 传 audit=audit / pg 复用传 audit=None）语义均正确——sqlite IntegrityError 后重入可能是复用（existing 分支先 return 不写审计）或新建（写审计），pg inserted=None 确定为复用不写。clash 预查移入事务内消除 R1 的 TOCTOU 窗口（顺带增强）。
4. **P3-8 锁不损语义**：allow 全程持锁，窗口滚动/被拒不重置逻辑原样保留（REST 限流用例第 3/4 次 429 同绿）；Barrier 为可重用形态，300 任务 4 workers 整除对齐无死锁。
5. **异常顺序正确性**：OrgContextError 与 AuthError 无继承关系，mcp/server.py 双 except 互不吞噬，400/4xx 前缀各自正确。

## 5. 注入验证证据（2 组，红→恢复→绿）

| # | 注入点 | 期望红 | 实测 |
|---|---|---|---|
| ① | mcp/server.py 恢复 R1 trusted 提前 return 形态 | test_mcp_trusted_search_param_ignore_audited | **FAILED** ✓ → 备份恢复后 2 passed |
| ② | sqlite upsert_user_jit COMMIT 提到 `_outbox_insert` 之前（审计移出事务） | test_jit_user_row_and_audit_atomic[sqlite] | **FAILED** ✓（users 残留行被断言捕获；pg 臂不受影响属预期）→ 恢复后 2 passed |

恢复后 `git status src/` 零输出（byte-identical 恢复）、备份文件已删。断言均真实绑定防线，无恒真/mock 假断言。

## 6. 择型 4 条裁定

| # | 申报 | 裁定 |
|---|---|---|
| ① | P3-5 真同事务（audit= 先例，并发复用不重复写审计由 INSERT 成功路径承载） | **ACCEPT**——store 层 audit= 参数为既有先例形态（create_upload_credential 等十余处）；同生共死经注入②实证；复用路径不写审计双方言审读确认 |
| ② | P3-2 防线归属：pyjwt 层强制 sub str + _opt_str 双保险，未为凑审计口径弱化验签 | **ACCEPT**——本机实证 pyjwt 2.15.1 decode 即抛 `InvalidSubjectError`；_opt_str 覆盖 org/username/display_name（pyjwt 不管制）；验签强度未放松（require 反而增强） |
| ③ | P3-6 审计面边界：SSO 事件覆盖语义拒绝四类；验签失败不记身份事件——与 trusted refused 审计（T13）不矛盾 | **ACCEPT**——四类 reason 断言 grep 核对齐备；验签失败（签名/过期/缺 exp）时身份未确立、无 user_id 可记（missing_sub 记 user_id=None 除外）；trusted 面 refused 审计对象是服务侧已声明实体，两者口径不冲突 |
| ④ | 限流测试 Barrier(4)×300 整除对齐（曾因 Barrier(8) 非整除挂起修正）；断言恰=limit 覆盖超发与误拒两向 | **ACCEPT**——300%4==0 cyclic barrier 无死锁（实测 1.75s 内通过）；sum==200 同时锁死「丢计数超发」与「误拒少放」两向 |

## 7. 新发现问题分级

**P1/P2：无。**

**P3（建议，不阻塞）**：
1. **P3-11 无固化用例**——coder 只改 api/search.py 顺序未加断言（申报未含用例）；本机探针已实证行为正确（400×2→0 事件、200→恰 1），建议下批补一条固化用例防回归。

**观察项**：
1. **MCP 面忽略审计先于 resolve_org 的窄面**——mcp/server.py 审计公共块按 P2-1 申报修法置于 resolve_org 前（任务书认可的形态）：非 trusted 形态下 org_claim≠X-Org-Id 的 400 请求仍会先落 ignored 事件（与 REST 面 P3-11 语义不完全统一）。trusted 路径不受影响（org 校验在认证阶段，OrgContextError 先抛）。属既定修法内生形态而非缺陷；若未来统一，将审计块移至 resolve_org 后即可（不影响 P2-1 达成）。

## 8. 结论

- **testVerdict: PASS**
- testedSha = `b24896e300c2b03f4c8d143d0ec1119e7d059906`（HEAD 复核一致；验证期间零 git 写操作）
- 门禁独立复跑 GATE PASS：**1580+1 双后端双模式 0 skipped**，+24 逐文件对账一致（30/27/44），pg 臂 561=528+33 全实跑（aud 四参 pg 组合形态确认实跑）
- R2 修复范围逐项闭环：P2×2 + P3×10 + 断言强化×2 全 ✅；不修项×3 零触碰 ✓；回归零弱化 ✓
- 注入验证 2 组红→恢复→绿，业务代码零残留
- 临时产物清理声明：**pg 遗留 schema=0**（psql 直查 `pg_namespace LIKE 'lattice_test_%'` = 0）；注入备份×2、p311-probe 目录已删；测试数据零落仓库

P3-11 固化用例与 MCP 面审计顺序观察项建议随 followups 处理，不阻塞本段收口。

</details>

<details>
<summary>R1 Committer 报告（ses_e6ac6e05fffeaTfE069ljMpJpz，2026-11-01，reviewVerdict=NEEDS_CHANGES）</summary>

# task-knowledge-lattice-m2-4 R1 Committer 审查报告

## 1. 前置校验

| 项 | 结果 |
|---|---|
| HEAD | `21778cd6c1294fd0361a44d84eaef4ce5e724ee0` ✓ |
| 父提交 | `eef7acf1412c90f1e97f3993d129423fd215a319` ✓（与申报一致） |
| 分支 | `develop_opencode` ✓；`origin/develop_opencode..HEAD` = 2 commits（未 push）✓ |
| 审查基线 | **R1 首审，无上一轮 reviewedSha** → 本轮 diff = `eef7acf..21778cd` 全量（15 files +1873/−32，与申报逐文件一致）✓ |
| 工作区 | 仅监督侧 3 流程文档（_m2-plan/task-m2s-6 改 + task-m2-4 未跟踪）——豁免面 ✓ |
| docs/ prototype/ .opencode/ | 提交内零改动 ✓（name-status 全量核对） |
| 测试门禁面 | tests/ 仅 3 个新文件、**存量测试零改动/零删除/零 skip/xfail**（grep 核对）✓；+77 逐文件 21/19/37 与收集数口径吻合（21=9×2+1+2，19=7×2+5，37=12×2+7+1+5）✓；1556 = 1479+77、pg 556 = 494+29+33 ✓ |
| 门禁复跑 | 本轮 bash 只读白名单（pytest 不在放行面），**采信 Tester 独立复跑证据**（1556+1 双后端双模式 0 skipped）+ 静态计数对账自洽——沿本项目先例 |

## 2. A1~A5 + B 逐项语义审查

| 项 | 验收对照 | 审查结论 |
|---|---|---|
| **A1 SSO/JIT** | TC-AUTH-03 / D16 / design §2 L806 | ✅ 语义正确：`MockIdpVerifier`（HS256 钉死算法、`verify_aud=False` 交 domain）+ `upsert_user_jit` 双方言（id 复用零更新 / username 冲突 ValueError→401 零落库 / pg ON CONFLICT 回读）+ JIT 审计。首建/复用/冲突/回退 sub 用例断言真实（created_at 冻结、display_name 管理员优先）。**唯一运营闭环缺口见需求边界 N-1** |
| **A2 委托 token** | TC-AUTH-04 / D18 | ✅ aud=配置值（缺省 knowledge-lattice）`in claims.aud` 校验 fail-closed（缺 aud/多值不含/非串全拒）；sub 计权、act 双身份审计（`auth.delegated` user+act+chain+org）；透传拒绝=aud 机制成立；A-9 REST body 五键集识别+审计+200 正常（`extra="allow"`）+ dev JWT 同款；org 沿 `resolve_org` D18（claim 优先/头一致/不一致 400 用例三档） |
| **A3 act 形态** | m1-3 移交 / RFC 8693 §4.1（用户裁定口径） | ✅ `resolve_act_claim` 迭代解析：string / object{"sub"} / 链式取 **chain[0]=最外层=current actor**，全链进 `act_chain`；尾端 string 宽容；6 非法形态 401+`invalid_act` 审计。与用户 2026-11-01 裁定一致，**移交必须项闭环** |
| **A4 可信子系统** | TC-AUTH-05 / T13 / design §2 L810 | ✅ 三约束齐备：白名单真实载体（env JSON、条目录 sha256、畸形 7 形态构造即 raise）+ allowed_orgs + 按服务限流（registry 自带共享态——W1 曾修「每请求新建」缺陷并有用例锁死）+ X-On-Behalf-Of + `X-User-Assertion` 在场证据 sub 一致。四拒绝（②③④+在场证据缺失/无效/未建档/禁用/限流/无白名单）**全部 outcome=refused + reason 级断言**；accepted 双身份审计；REST 全链集成 3 条含伪造 OBO 不降级。**期限②落实成立**。**扣分项：MCP 可信路径参数审计缺口（P2-1）** |
| **A5 生产形态** | T16 / 静态 token 边界 | ✅ prod+SSO 可用 / dev JWT 401 / 静态 401 三断言；`create_app(sso_verifier=)` 显式注入优先 + 工厂配置化；缺省 `none`→None，存量 1556 全绿即零感知。dev token 路由 prod 404 既有用例复核。**P2-2：mock 缺省密钥 prod 无护栏** |
| **B 顺手** | m1-3 L82 余量 / m2-3 交叉 / L81 docstring | ✅ **m1-3 act 对象形态移交闭环**；m2-3 管理面交叉（委托 token→`get_auth`→`org_scoped`→org_admin 门控：非 admin 403→升 admin 200）用例成立；**L81 两处 docstring 核验属实已修（本轮零改动，闭环）** |
| **分层纪律** | design §3 | ✅ adapter 仅验签+claims 归一（无 SQL/无计权/JIT/审计）；domain 承载业务语义；store 协议新增 `AdminBackend.upsert_user_jit` 双方言实现；本轮零触及 core/（auto_entities 钉层未破坏）；domain 未写方言 SQL ✓ |
| **双方言等价** | D24 | ✅ SQL 审读同构（sqlite 预查+IntegrityError 兜底 / pg ON CONFLICT+UniqueViolation 回读）；autocommit 语义下异常不污染事务；[pg] 臂 29 实例实跑 ✓ |

## 3. 安全性深审

| 面 | 结论 |
|---|---|
| 验签/算法混淆 | ✅ `algorithms=["HS256"]` 钉死，拒 `none`/RS 混淆；密钥走 settings；`SsoVerificationError` 转 domain 落回分支在 **prod 被 `environment != "prod"` 二次兜底**（dev JWT 分支不进、随后 prod raise 直接 401——无静态 token 逃生） |
| aud 校验完备性 | ✅ 缺失/空/多值不含/非串全拒；多值含本服务放行（受众语义正确）；断言（在场证据）不做 aud 校验=已申报择型③（id_token 属身份断言，exp 照验） |
| 白名单 sha256 | ✅ 明文不落 registry/审计/异常（除 P3-1 一处畸形配置消息）；哈希比对时序攻击不可行（需 sha256 原像前缀碰撞） |
| 限流器 | ✅ 固定 60s 窗口、monotonic、被拒不重置不占配额、registry 共享态（REST 实证第 3 次 429）；⚠️ 进程内 + 无线程锁（线程池并发可轻微超发）→ P3-8/known-gaps |
| 审计不吞异常 | ✅ `_audit` 无 try/except，写失败即传播（AuthError.code 429 链路 REST=status_code / MCP=ToolError code 完整）；JIT 事件与建档非同事务为窄窗（P3-5） |
| 信息泄露 | ✅ 无 token 明文进日志/审计 detail（payload 仅 user/act/act_chain/org/service/ignored_fields）；AuthError 不含 token；**P3-1 畸形白名单消息含 token 明文**；P3-7 username 冲突消息泄露他用户 id |
| 越权/绕过 | ✅ 无新 P1 绕过面：伪造 X-On-Behalf-Of 不降级（unknown_service 401）；服务凭证缺失/白名单外/无 registry 全 fail-closed；可信路径 org 仅 header 且受 allowed_orgs+path 一致性双约束；受限用户/未建档用户拒绝；JIT 不覆盖既有档案 |

## 4. 择型 9 条 + 边界 4 条终审

**择型 9 条：全部 ACCEPT**（①adapter/domain 分层正确，附 P3-2 类型归一补强建议；②RFC MUST + 全链保留——用户已裁定，无改码；③断言头名+不校 aud 合理，需 docs 固化契约；④sha256 载体+mTLS 归部署期合理；⑤固定窗口/被拒不计合理，进程内登记；⑥判定序最便宜优先合理；⑦可信声明用户不 JIT 正确（防扫库建号）；⑧五键集收敛合理；⑨审计失败即传播链路完整）。

**边界 4 条：全部 CONFIRMED（裁定如下）**
- ① **按 RFC 8693 §4.1 MUST 实现无需改码**——用户已裁定并回写任务书 A3；docs 批补 TEST-CASES 注记即可。
- ② design §3 L150「auth_sso.py：JIT 建档」为简写——**登记非决策勘误**（落 domain/auth.py 是分层权威），本轮不改码。
- ③ 透传拒绝机制=aud 校验属实（缺失/不含均拒）。
- ④ B-L81 两处 docstring 已修、本轮零改动属实。

## 5. Tester P3×3 / 观察 3 条处置裁定

| 项 | 裁定 |
|---|---|
| P3-1 MCP 可信接线层无专项用例 | **R2 顺手修（必须）**——与 P2-1 修复同批补：trusted 头 + `search(org+permissions)` → 断言 `mcp.org_param_ignored` + `auth.request_permissions_ignored` 双事件且 200；可加 MCP 冒充 403 一条 |
| P3-2 aud 边界未 parametrize | **R2 顺手修**（廉价：缺失/多值含/多值不含/非串四参，防回归） |
| P3-3 「被拒不占配额」断言可加强 | **R2 顺手修**（第 4 次仍 429 一行） |
| 观察1 限流进程内 | **登记 known-gaps（G-25）**：多进程/多实例限流不共享 + 无线程锁；POC 单进程 NFR 接受，重开条件=多实例部署 |
| 观察2 REST 可信面 org 缺失无断言 | **R2 顺手修**（trusted 头 + 无 X-Org-Id → 400 一条） |
| 观察3 仅 X-User-Assertion → 401 | **不动**（行为正确 fail-closed；可并入 P3-1 新用例矩阵） |

## 6. 新发现问题分级

### P1（阻断）：无

### P2（应修）
- **[P2-1] `src/knowledge_lattice/mcp/server.py:197-216`（跳过点）vs `:223-236`（审计块）**——可信子系统分支 `return auth, _org_from_header(...)` **提前返回，跳过 `param_org`（mcp.org_param_ignored）与 `param_permissions`（auth.request_permissions_ignored）两处「忽略并记审计」**。违反 D18/§5.5「工具参数中的 org 一律忽略并记审计」与 FR-4/A-9「权限字段忽略并记审计」（对一切认证形态），也与本函数自身 docstring ③ 矛盾；REST 面不受影响（审计在端点层）。**且该缺口正是 Tester P3-1「MCP 可信接线无专项用例」掩盖的缺陷**。
  **建议修法**：把 org/permissions 忽略审计抽成公共块，在 trusted 分支 `return` 前执行（或把两段审计上提到认证成功之后、分支返回之前）；同批补 R2 用例（见 §5 P3-1）。
- **[P2-2] `src/knowledge_lattice/adapters/auth_sso.py:145-152` + `config.py:102`**——`build_sso_verifier` 对 `mock-idp` **无任何环境护栏**；`sso_mock_secret` 缺省 `"dev-mock-idp-secret"` 为仓库公开常量。prod 误开 `LATTICE_SSO_PROVIDER=mock-idp` 且忘改密钥 = 任何人可签任意 `sub`（含既有管理员 id，JIT 复用返回其 is_system_admin）→ 全身份伪造。同类风险在 dev JWT 已按 P2-5 明令 prod 拒绝（公开默认密钥可伪造），SSO 侧应同口径。
  **建议修法**：`if provider == "mock-idp" and settings.environment == "prod" and settings.sso_mock_secret == "dev-mock-idp-secret": raise ValueError(...请显式配置 LATTICE_SSO_MOCK_SECRET)`（只拦公开缺省值，不拦 mock 形态本身；现有用例均显式传密钥/显式注入 verifier，不受影响）。若监督侧决定以 known-gaps + 部署纪律替代，需显式裁定登记（不静默）。

### P3（记录/顺手，不阻断）
- **[P3-1] `domain/auth.py:325-326`**——`from_json`「缺 service_id」分支把 `{item!r}` 放进异常消息，条目里含 `token` 字段 → **畸形配置时 token 明文进启动日志**（与「不落明文」口径冲突；Tester「畸形配置消息无明文」实证未覆盖此分支）。建议消息只带 `list(item)` 键名或 `token: <hash>`。
- **[P3-2] `adapters/auth_sso.py:134-142`**——claims 类型归一不全：`sub` 可能非 str（真值 int 直接作为 user_id 透传）、`org/username/display_name` 非 str 时落入 sqlite 绑定异常→500（非 401）。建议 verify 内做 `isinstance(..., str)` 校验/降级，真实 IdP 适配器须同契约。
- **[P3-3] `domain/auth.py:438`**——`removeprefix("Bearer ")` 大小写敏感；`bearer xxx` 会落 invalid_user_assertion（fail-closed 但契约不友好）。建议大小写不敏感裁前缀。
- **[P3-4] `adapters/auth_sso.py:127-133`**——未强制 `exp`/`iss` 存在与 `iss` 值校验（mock 依赖共享密钥，真适配器必须补）；建议 `options={"require": ["exp","iss"]}` + 真实适配器 TODO 注释。
- **[P3-5] `domain/auth.py:186-200`**——JIT 建档（独立语句）与 JIT 审计非同事务：outbox 写失败时用户已建但永久缺 JIT 事件（重试 created=False）。建议评估是否并入同事务（append_outbox 已有 audit= 同事务先例）。
- **[P3-6] `domain/auth.py:174-175 / 201-202`**——SSO 拒绝面审计不全：`missing sub`、`user disabled` 无事件（仅 audience/invalid_act 有）。口径一致性建议补 `reason` 事件。
- **[P3-7] `store/sqlite/backend.py:1630-1633 / store/postgres/backend.py:1674-1677`**——冲突消息回显他用户 id（经 401 body 外泄）。建议泛化为「username 已被其他账号占用」。
- **[P3-8] `domain/auth.py:353-370`**——限流器无锁（同步依赖走线程池，read-modify-write 可丢计数轻微超发）+ 进程内态；→ **known-gaps G-25**（观察1）。
- **[P3-9] `domain/auth.py:426-427`**——`unknown_service` 拒绝审计由**未认证调用方**触发，可无界写 audit_outbox（写放大/存储增长；设计强制 refused 审计）；建议部署侧准入限流兜底或登记 known-gap（G-26）。
- **[P3-10] 卫生**——`authenticate_trusted(settings)` 未使用；`_authenticate_sso_claims` 的 `SsoClaims` 导入 F401；`api/upload.py:52` docstring 仍写「401 → 401」（实际可 403/429/400）。
- **[P3-11] `api/search.py:53-56`**——权限忽略审计先于 org 解析：org 缺失/不一致的 400 请求也会留「ignored_fields」事件（事实成立但语义顺序可优化）。
- **[P3-12] `store/sqlite/backend.py:1648-1650`**——IntegrityError 兜底递归无上限（当前 schema 仅 id/username 唯一约束可达，属理论面）。

### 需求边界问题（上报监督侧/用户，非 coder 修）
- **N-1（运营闭环缺口，建议裁定去向）**：JIT 首次登录建档后，**API 面无法把新用户加入组织**——`PUT /api/orgs/{org}/members/{uid}/grants` 与 CSV 导入均要求**既有 membership**（admin.py:234、416），而 m2-6 计划只写「members GET / values CRUD」（无成员增改）。D16「管理员不建账号只配授权」在 API 面实际不闭环（POC 需 DB/seed 开通）。建议：m2-6 扩为 members 增/改/删，或在 known-gaps 登记「POC 成员关系经 DB/seed 开通」并纳入部署 runbook——**请用户/监督侧裁定，勿让 coder 猜**。
- **N-2（文档空白，非决策回写即可）**：design §5.5 未落字的三处实现契约——在场证据头名 `X-User-Assertion`、白名单真实载体（env JSON + sha256 存储 + 60s 窗口 rpm）、act 链式「最外层=current actor + act_chain 进审计」、JIT「复用不覆盖/username 冲突 fail-closed」；以及 MCP 面权限字段载体=`search` 工具 deprecated `permissions` 参数（字面「请求体」之外的实现口径扩充）。建议随 TEST-CASES 完成态注记+design 非决策注记固化（不改 D 编号）。

## 7. docs 批 / 遗留事项 / manifest 建议

**docs 批（监督侧落笔）**
1. TEST-CASES v1.9.11（非决策、用例数不变）：TC-AUTH-03/04/05 完成态注记（JIT 复用不覆盖/username 冲突 fail-closed；act RFC 口径；白名单 JSON 载体+allowed_orgs+限流+`X-User-Assertion`）；T13「生产形态收口」；T16 复核；A-9 完成态（REST body + MCP permissions 双面）；§六 M2 行 m2-4 段完成态 + 剩余段去向（m2-6→m2-5）；门禁 1556+1。
2. known-gaps：**G-25**（限流进程内/无线程锁，重开=多实例部署）、**G-26**（认证拒绝路径审计放大，P3 接受）、（若 P2-2 选择登记而非修）**G-27** mock-idp 生产缺省密钥。
3. design v0.9.7（非决策、D 不动）：§3 L150 注释勘误（验签适配器 / JIT 与降级判定落 domain/auth.py）+ §5.5 实现口径注记（N-2 四项）。
4. AGENTS.md §1 + _m2-plan row7：m2-4 完成态（待合入）、基线 1556+1、下一段 m2-6。
5. 检查点：frontmatter（reviewVerdict/committerTaskId/R1 Committer 报告入库）、filesChanged 核对准确（15 files 一致）。

**遗留事项去向**
- m1-3 检查点 L82「act 对象形态」→ **本段闭环，回写 m1-3 已清偿**（监督侧）。
- 真实 IdP/SSO 联调（待决-2/3）→ 维持 m2-5/部署期挂账（任务书已定）。
- P3-2~P3-12 → 除 P3-1~P3-4 建议 R2 顺手外，余登记 known-gaps/下批。
- N-1 成员关系开通 → m2-6 或 known-gaps（待裁定）。

**evidence manifest 要点（交付阶段）**
`testedSha=reviewedSha=最终 HEAD`（若追加 docs-only 归档 commit，按先例 reviewedSha=归档 HEAD、testedSha 保持代码 SHA）；门禁**原始输出**（`scripts/test_gate.sh`：1556+1、pg 556=523+33、双模式 0 skipped）；rounds；`specRulings`（9 择型 + 4 边界 + P3 处置 + N-1 裁定）；`gapClosures`（TC-AUTH-03/04/05、T13、T16、A-9、m1-3 act 移交、B-L81）；`handover`（真实 IdP→m2-5、known-gaps G-25/G-26、P3 残留、N-1）。**双 SHA 与最终 HEAD 不一致不放行。**

## 8. 结论

- **reviewVerdict: NEEDS_CHANGES**
- **reviewedSha = `21778cd6c1294fd0361a44d84eaef4ce5e724ee0`（= testedSha = HEAD，三一致；R2 修复 commit 后按纪律置空重审）**
- 阻断原因：**P2-1（MCP 可信路径跳过工具参数忽略审计——违反 D18/FR-4/A-9 明文口径）**、**P2-2（mock-idp 在生产环境使用公开缺省密钥，身份伪造风险）**。其余为 P3 登记级与 1 项需求边界（N-1）上报。
- R2 建议范围：P2-1（含 MCP 可信专项用例 + Tester P3-1/观察2 测试补强）、P2-2（护栏或显式裁定）、P3-1~P3-4 顺手、Tester P3-2/P3-3 断言强化；完成后重跑 `scripts/test_gate.sh` 双后端双模式并重新申报计数（预期 1556+1+N，0 skipped、pg 臂 >0）。
- **未收到 CASE_BUG 裁定请求**（Tester 仅提交 P3/观察，无需裁定）。本轮为只读审查：零文件修改、零 git 写、未执行 `gh pr review`（待用户确认交付后对最终 HEAD 留痕）。

</details>

<details>
<summary>R2 Committer 报告（ses_e6ac6e05fffeaTfE069ljMpJpz 续接，2026-11-01，reviewVerdict=APPROVED）</summary>

# task-knowledge-lattice-m2-4 R2 Committer 审查报告

## 1. 前置校验

| 项 | 结果 |
|---|---|
| HEAD | `b24896e300c2b03f4c8d143d0ec1119e7d059906` ✓ |
| 父提交 | `21778cd6c1294fd0361a44d84eaef4ce5e724ee0` ✓（与申报一致） |
| 分支 / push | `develop_opencode`，ahead of origin/develop_opencode by 3，**未 push** ✓；origin/develop=`eef7acf`（未前进）✓ |
| 审查基线 | **R2 diff = `21778cd..b24896e`**（12 files +562/−118，与申报逐文件一致）✓ |
| 工作区 | 仅监督侧 3 流程文档（_m2-plan / task-m2s-6 改 + task-m2-4 未跟踪）——豁免面 ✓ |
| 提交内 docs/prototype/.opencode/scripts/.env.example | 零改动 ✓（name-status + 空 diff 双核） |
| 门禁面 | 无 skip/skipif/xfail；**无 `-def test_`**、无断言行删除；测试变更全为新增/纯增强（详 §2）✓；`git diff --check` 干净 ✓ |
| 门禁复跑 | 本轮 bash 只读白名单（pytest 不在放行面），**采信 R2 Tester 独立复跑**（1580+1 双后端双模式 0 skipped）+ 静态计数对账自洽（见 §2.4 口径说明） |

---

## 2. R1 意见闭环核验（逐条对照 R2 diff，非表面应付）

### 2.1 P2（阻断项）

| 项 | 修复落点 | 审查判定 |
|---|---|---|
| **P2-1** MCP 可信路径跳过 org/permissions 忽略审计 | `mcp/server.py:198-242`：trusted 分支提前 return 与 `_org_from_header` **删除**；if/else 统一赋值 `auth` 后**单一直线路径** → 审计公共块（:221-235）→ `resolve_org`（:236-242）；`OrgContextError` 上提统一 400（:219-220） | ✅ **真闭环**。控制流无分叉、无 early return；`auth` 两条分支均赋值（无未绑定面）；`AuthError`/`OrgContextError` 无继承关系、互不吞噬；审计块对 trusted/dev JWT/SSO/委托四形态一致生效。用例 `test_mcp_trusted_search_param_ignore_audited`（org_events==1 ∧ perm_events==1 精确计数）+ `test_mcp_trusted_impersonation_403`（403+refused subject_mismatch）；Tester 注入①（恢复 R1 提前 return）转红实证断言绑定防线 |
| **P2-2** mock-idp prod 无护栏 | `config.py:22` `DEFAULT_SSO_MOCK_SECRET` 常量（dataclass 缺省 + `get_settings` 均引用）；`adapters/auth_sso.py:170-186` prod+mock-idp+**值等于公开缺省** → ValueError | ✅ **闭环且无绕过**：判定按**值相等**（env 显式设同值同样被拒——比"是否显式配置"更强的口径）；只拦「公开缺省值+prod」组合，mock 形态与 dev/test 缺省零感知；与 P2-5（dev JWT prod 禁用）同口径；`sso_verifier=` 显式注入路径为程序化 API 非配置面，保留 T16 测试形态。三态用例齐（prod+缺省拒/prod+显式放/test+缺省放） |

### 2.2 P3×12（用户裁定"应修尽修"，逐条）

| 项 | 落点 | 判定 |
|---|---|---|
| P3-1 异常消息泄 token | `domain/auth.py:330-345` 只带**键名**（`sorted(item)`）与非对象**类型名** | ✅ 三处含 token 的分支 + 非对象分支全不泄；用例 `leak-me-secret not in str(exc)` 逐条断言（7→8 参） |
| P3-2 claims 类型归一 | `adapters/auth_sso.py:80-84 _opt_str` + verify | ✅ sub/org/username/display_name 非 str 降级；用例覆盖 int sub（401+零建档）与 org/username/display 非 str（降级后 username 回退 sub）；择型②（pyjwt 强制 sub str + 双保险）成立 |
| P3-3 Bearer 前缀大小写 | `domain/auth.py:459-467` | ✅ `lower().startswith("bearer ")` + 二次 strip；`test_trusted_assertion_bearer_prefix_case_insensitive` 双后端 |
| P3-4 强制 exp/iss | `adapters/auth_sso.py:144-147` `require` + TODO 真实适配器 iss 值/JWKS | ✅ 无 exp 拒（用例）；docstring 写明真实适配器契约 |
| P3-5 JIT 建档与审计同事务 | `store/sqlite/backend.py:1612-1682`（BEGIN IMMEDIATE→事务内重查→clash 预查→INSERT→`_outbox_insert`→COMMIT）；`store/postgres/backend.py:1645-1700`（BEGIN→ON CONFLICT RETURNING→outbox→COMMIT）；`except BaseException: _rollback()+raise` | ✅ **真同事务**（沿 `create_upload_credential` audit= 先例）；**仅实际插入写审计**（sqlite 事务内重查命中/pg `inserted is None` 均不写）；崩溃注入用例（monkeypatch `_outbox_insert` raise → users 零残留）**双后端**实跑；Tester 注入②（COMMIT 提前）转红；sqlite clash 预查移入事务消除 TOCTOU（顺带增强） |
| P3-6 拒绝面审计不全 | `domain/auth.py:177-181 / 210-214` missing_sub + user_disabled 补 `auth.sso_refused` | ✅ 语义拒绝四类齐（audience_mismatch/missing_sub/invalid_act/user_disabled），两专项用例 reason 精确断言 |
| P3-7 冲突消息回显他用户 | 双方言泛化「已被其他账号占用（不回显）」 | ✅ 用例补 `"u_existing" not in str(exc)` |
| P3-8 限流器无锁 | `domain/auth.py:353-394` `threading.Lock` 全程持锁；进程内态不改 | ✅ 单锁无嵌套（无死锁面）；Barrier(4)×300 恰=limit（超发/误拒两向锁死）；既有共享态/第 3·4 次 429 用例同绿；进程内架构项→G-25 申报 |
| P3-9 拒绝审计写放大 | **零改动**（diff 审读确认 `_refuse`/`unknown_service` 无变化） | ✅ 按用户裁定不修，G-26 随 docs 批 |
| P3-10 卫生×3 | settings 参删（3 处调用同步）/F401 删/docstring 更新 | ✅ 全仓库无残留调用 |
| P3-11 审计顺序 | `api/search.py:51-59` resolve_org 提前 | ✅ 语义正确（400 请求不落 ignored 事件，本机探针实证）；**缺固化用例**→新 P3-1（见 §4） |
| P3-12 递归无上限 | 双方言 `_depth>=3 → RuntimeError`，递归均传 +1 | ✅ 防御性收口正确 |

**Tester R1 P3×3 / 观察 3 条（裁定后）**：P3-1（MCP 可信专项）✅ 已补 2 条；P3-2（aud 四参）✅ 8 实例双后端；P3-3（第 4 次仍 429）✅；观察1（限流进程内）✅ 锁已加+G-25 申报；观察2（REST org 缺失）✅ `test_trusted_rest_missing_org_400`；观察3 ✅ 未动（行为正确）。

**不修项零触碰确认**：P3-9 ✅（domain/auth.py 对应代码行零变）；N-1 ✅（无 admin.py）；观察3 ✅（dispatch 逻辑未动）。

### 2.3 未弱化确认（测试门禁审查）

- 删除行仅：2 处 docstring、1 处 import 合并、2 处 `_call/authenticate_trusted` **签名机械适配**、3 条 malformed 参数值（替换为更强含 `leak-me-secret` 版本 + 新增 1 条）、1 处 `pytest.raises` 改为捕获 excinfo **加断言**。**零 `def test_` 删除、零断言行删除**。
- `test_sso_username_conflict_rejected` / `test_sso_token_missing_sub_rejected` 为**纯增强**（补消息不泄 + 补 refused 审计）。
- 无 skip/xfail 新增。

### 2.4 计数对账（含一处口径说明）

- **+24 逐文件精确核对**：auth_03 21→30（+4 backend 参×2 + 1 非参 = 9）、auth_04 19→27（aud 4 参×2 = 8）、auth_05 37→44（+1 REST + 2 bearer + 1 线程 + 1 MCP 双事件 + 1 MCP 冒充 + malformed +1 = 7）→ 合计 24 ✓，1580 = 1556+24 ✓。
- **pg 臂口径说明（非缺陷）**：gate 输出 `561 = 528 + 33` 是 `scripts/test_gate.sh:37` 的 `grep '\[pg\]'` 计数——aud 四参的 pg 实例 id 形如 `[pg-missing]`，**未被该 grep 计入**（4 条）；**真实 pg 实例 = 565**（Tester 已显式披露并单跑 8 条确认全实跑）。总数 1580（精确）与 0 skipped（精确）不受影响；建议 manifest 措辞注明口径（见 §7）。

---

## 3. 语义与安全复审（R2 新改动面）

| 面 | 结论 |
|---|---|
| **P2-1 控制流** | 四认证形态 → 审计 → resolve_org 单一直线；trusted 的 org 已在认证阶段 fail-closed（缺失/越界），此处 `resolve_org(claim=header, header)` 直通；非 trusted 语义与 R1 完全一致（审计仍在 resolve_org 前——Tester 观察1，见 §5）；无新绕过面 |
| **P2-2 护栏完备性** | 值相等判定（env 同值仍拒）✓；仅 prod 生效（dev/test 零配置零感知，1580 全绿即证）✓；失败方式=启动即 raise（fail-closed）✓；注释/任务书口径一致 |
| **P3-5 双方言事务** | sqlite：`isolation_level=None`（autocommit）+ 显式 BEGIN IMMEDIATE/COMMIT；异常统一 `_rollback`（失败不覆盖原异常）；事务内重查消除 TOCTOU；IntegrityError 重试带 audit（新建路径）且复用路径不写。pg：autocommit + 显式 BEGIN/COMMIT（**与 `create_upload_credential` 先例逐字同形**）；`inserted is None` 先 COMMIT 再递归复用（audit=None），UniqueViolation→rollback→ValueError；`except BaseException` 兜底 rollback。**两臂语义同构、崩溃注入双后端实证** |
| **P3-8 锁** | 锁粒度=单次 allow 的 read-modify-write；无嵌套获取（无死锁）；窗口滚动/被拒不重置语义原样；`now` 注入测试形态不受影响 |
| **P3-11 顺序** | REST：org 解析成功后才落 ignored 事件（拒绝语义与忽略语义不叠加）；trusted 路径 org 在认证阶段已校验，不受影响；A-9 正常路径事件数不变（既有用例绿） |
| **安全面回归** | 验签算法仍钉 HS256；prod 无静态/dev JWT 逃生（P2-2 反而加严）；审计失败仍传播（P3-5 更早失败且不建号）；无新增 token/claim 明文进日志/审计/异常（P3-1 反向收口）；`_opt_str` 不放松验签（require 增强） |

---

## 4. 新发现问题分级

### P1（阻断）：无
### P2（应修）：无

### P3（记录/顺手，不阻断）
- **[P3-1] `api/search.py:51-59`**（Tester P3-1）：P3-11 顺序修复**无固化用例**——若未来把审计块移回 resolve_org 之前，现无测试会红。行为已由独立探针实证（400×2→0 事件、200→恰 1）。**建议下批补一条（约 10 行）**，不为此开 R3。
- **[P3-2] `mcp/server.py:221-242`**（Tester 观察1）：MCP 面忽略审计**先于** `resolve_org`，与 REST（P3-11 后审计在后）口径不一致——非 trusted 形态下 org claim/头不一致的 400 请求仍会先落 ignored 事件。属 R1 P2-1 既定修法内生形态（trusted 不受影响，行为非缺陷）。**不动**；如未来统一，把审计块移至 `resolve_org` 之后即可。
- **[P3-3] `scripts/test_gate.sh:37`**：`grep -c '\[pg\]'` 对 `[pg-*]` 组合 id（fixture+parametrize 嵌套）少计（本段 4 条）。总数 passed 精确、pg>0 断言语义不受影响。**建议 manifest 注明口径**；可选 followup：正则改 `\[pg[^]]*\]`。
- **[P3-4] `tests/test_auth_05_trusted.py:83`**：`_call(backend, settings, ...)` 的 `settings` 形参在 R2 签名调整后已无用（机械残留）——测试卫生，随 followups。
- **[P3-5] `store/sqlite/backend.py:1668` / `store/postgres/backend.py:1687`**：`_outbox_insert` 自身若抛完整性错误（uuid 碰撞/审计表约束，实际不可达）会被归类为「建档冲突」重试/包装（sqlite 重试 3 次后 RuntimeError；pg 直接 ValueError）——错误原因被掩码，但**仍 fail-closed、无残留行**；理论面，登记即可。

---

## 5. R2 择型 4 条终审

| # | 申报 | 裁定 |
|---|---|---|
| ① | P3-5 真同事务（audit= 先例；复用不重复写审计由 INSERT 成功路径承载） | **ACCEPT**——与 `create_upload_credential` 等既有 audit= 形态逐字同构，同生共死经注入实证；双后端行为等价 |
| ② | P3-2 防线归属（pyjwt 层强制 sub str + `_opt_str` 双保险，未弱化验签） | **ACCEPT**——require 反而增强；`_opt_str` 覆盖 pyjwt 不管制的 org/username/display_name |
| ③ | P3-6 审计面边界（SSO 语义拒绝四类；验签失败不记身份事件） | **ACCEPT**——验签失败时身份未确立、无可记 user_id，与 T13 trusted refused（已声明服务/用户实体）口径不冲突 |
| ④ | 限流测试 Barrier(4)×300 整除对齐 | **ACCEPT**——无死锁、两向锁死 |

**R1 择型 9 条 / 边界 4 条**：R2 未触碰其语义面，R1 结论（全 ACCEPT / 全 CONFIRMED，act 最外层=用户裁定 RFC 口径）继续有效。

---

## 6. Tester P3×1 / 观察1 处置

| 项 | 裁定 |
|---|---|
| Tester P3-1（P3-11 无固化用例） | **登记 followups**（下批/m2-5 测试补强批补一条；行为已独立探针实证、修复面小，不为此消耗 R3 轮次） |
| Tester 观察1（MCP 审计先于 resolve_org） | **不动**（既定修法内生形态、非缺陷；trusted 路径不受影响；统一口径列入 followups 可选注记） |

---

## 7. 需求边界问题

**无新增。** 既有两项处置确认：
- **N-1**（JIT 建档后 API 面成员开通缺口）：用户裁定 **选 a → 归 m2-6**；监督侧已在工作区 `_m2-plan` row 7.5 预落「members 增/改/删」范围（本任务代码零触碰，符合裁定）。
- **N-2**（文档空白四处 + MCP permissions 载体）：维持随 docs 批非决策回写固化，不涉 coder。

---

## 8. 交付把关建议（APPROVED 后）

**docs 批清单（终版，监督侧落笔）**
1. **TEST-CASES v1.9.11**（非决策、用例数不变）：TC-AUTH-03/04/05 完成态注记——JIT 首建/复用不覆盖/username 冲突 fail-closed（消息不回显）/JIT 审计与建档同事务；act RFC 8693 §4.1 最外层+act_chain；aud 四形态；白名单真实载体（env JSON+sha256+allowed_orgs+60s 窗口 rpm）+`X-User-Assertion` 在场证据（Bearer 不敏、不校 aud、exp/iss 必须）；拒绝面四类 reason；**T13 生产形态收口**；**T16 复核**（prod+SSO 通过 / dev JWT·静态 401 / prod+mock-idp 公开缺省密钥启动即拒）；A-9 双面（REST body + MCP `permissions`）；§六 M2 行 m2-4 段完成态（门禁 **1580+1**；pg gate 口径 561=528+33，`[pg-*]` 组合 4 条未计、实跑 pg 实例 565）+ 剩余段去向（m2-6 → m2-5）。
2. **known-gaps**：**G-25**（限流进程内态——线程锁已加，多实例不共享；重开=多进程/多实例部署）、**G-26**（认证拒绝路径审计放大，部署侧准入限流兜底）。
3. **design v0.9.7**（非决策、D 不动）：§3 L150 注释勘误（auth_sso.py=验签适配器；JIT/降级判定落 domain/auth.py）+ §5.5 实现口径注记（N-2 四项 + mock-idp prod 缺省密钥 fail-closed）。
4. **AGENTS.md §1 + _m2-plan row7/7.5**：m2-4 完成态、基线 1580+1、下一段 m2-6（已含 N-1）；合入后分支基线更新。
5. **检查点终态**：reviewVerdict=APPROVED、committerTaskId、reviewedSha（按交付 HEAD）、R2 Committer 报告入库、status 状态机流转。

**遗留事项回写**
- m1-3 L82「act 对象形态」→ **本段闭环，回写 m1-3 已清偿**。
- 真实 IdP/SSO 联调（待决-2/3）→ 维持 m2-5/部署期挂账。
- N-1 → m2-6（已落 plan）；P3-9 → G-26；P3-8 进程内态 → G-25。
- followups：§4 P3-1/P3-3/P3-4/P3-5 + 观察1 可选统一。

**evidence manifest 要点（必须完整、双 SHA 与最终 HEAD 一致，否则不放行）**
`testedSha=b24896e`；`reviewedSha`=最终 HEAD（若按先例追加 **docs-only 归档 commit**，reviewedSha=该 HEAD、testedSha 保持 b24896e，并对归档 commit 做 doc-only 复核——不得只改 frontmatter 不核 diff）；门禁**原始输出**（`scripts/test_gate.sh`：1580 passed + 1 deselected/manual、0 skipped、双模式）+ pg 口径双注（gate 561=528+33 / 实跑 565）；`rounds=2`；`verdicts` PASS/APPROVED；`specRulings`（R1 9 择型+4 边界；用户 R1→R2 裁定 N-1=a/P2-2 修/P3-9→G-26/G-25 架构项不改；R2 4 择型 + 本报告 P3 处置）；`gapClosures`（TC-AUTH-03/04/05、T13、T16、A-9、m1-3 act 移交、B-L81）；`handover`（真实 IdP→m2-5、G-25/G-26、N-1→m2-6、followups 五项）；`stale=false`。

**交付链**：用户确认交付 → coder 同步 origin/develop + push develop_opencode + 开 PR（base=develop）→ 我执行 `gh pr review` 留痕（APPROVED，self-approve 限制按惯例 COMMENTED 载体首行）→ manifest 入 PR description 并远端回读校验 → **合入动作不经手**。本轮为只读审查：零文件修改、零 git 写、未执行 `gh pr review`。

---

## 9. 结论

- **reviewVerdict: APPROVED**
- **reviewedSha = `b24896e300c2b03f4c8d143d0ec1119e7d059906`（= testedSha = HEAD，三一致）**
- R1 阻断项 P2-1/P2-2 **实质闭环**（非表面应付：控制流重构 + 值相等护栏，均有注入/三态实证）；P3×10 全修且引入面复审无新风险；不修项（P3-9/N-1/观察3）**零触碰**确认；N-1 已按用户裁定 a 归 m2-6（plan 已预落）；门禁 1580+1 双后端双模式 0 skipped、零弱化、+24 逐文件对账精确。
- 无 P1/P2；P3×5 登记级（不阻塞，其中 P3-1 建议随 followups 补回归用例）。
- **未收到 CASE_BUG 裁定请求**；未发现需上报的新需求边界问题。可进入交付阶段（docs 批终态 + 归档 commit + manifest 双 SHA 对齐后放行）。

</details>
