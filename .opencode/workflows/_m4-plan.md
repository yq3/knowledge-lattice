# M4 段计划：内置账号与邀请制登录（D25 / issue #28）

> **状态**：已立项（2026-11-19，用户裁定按 V2 完整版）；**文档已落，代码未开工**。
> **决策**：D25（requirements v0.10）——`LATTICE_AUTH_MODE=local/sso` 双形态，默认 `sso` 零变化；local = 内置账号 + 邀请制 + 首启 setup + 本地会话（Web/REST only）。
> **评估依据**：`.opencode/workflows/_auth-local-login-proposal.md`（含 Dify 源码索引、方案对比、冲击/工作量）。
> **问题单**：https://github.com/yq3/knowledge-lattice/issues/28

---

## 一、范围（V2 完整）

1. **决策/文档**：D25 + FR-9 + requirements/design/TEST-CASES/known-gaps/RUNBOOK/AGENTS（本批已落）。
2. **账号底座**：迁移 0012 双方言（`users` 扩列 + `user_invitations` + `instance_setup`）+ store 协议与双方言 + `domain/accounts.py`。
3. **认证 API**：`/api/setup` + `/api/auth/*` + `/api/users` + `/api/orgs/{org}/invitations`；错误码/审计/限流。
4. **Web**：boot 门 + setup/login/invite 三屏 + 用户/邀请管理页 + 组织切换 + i18n（zh/en 键集相等）。
5. **收口**：break-glass CLI、RUNBOOK/.env、双后端双模式 gate、文档回写（完成态/门禁数）。

**非目标（phase 1）**：同一实例 local+SSO 同时登录/账号绑定（hybrid）；邮箱登录；SMTP 发信；refresh token；MFA；多实例限流；本地 token 进 MCP。

---

## 二、段序总表

| 段 | 范围 | 验收 | 预估 |
|---|---|---|---|
| **m4-1** 账号底座 | 0012 迁移双方言（users 扩列/邀请表/setup 单例）；store 协议 + 双方言实现（create_user/find/list/status/token_version/invitation CRUD/setup 单例/count_sysadmins）；`domain/accounts.py`（scrypt/session JWT/JIT gate/限流/tv）；audit 常量；store/domain 级双后端用例 | 迁移水位 11→12；约束/并发 setup 单例；scrypt/session 单测；现有门禁不降 | 3~4 人日 |
| **m4-2** 认证 API | `/api/setup`、`/api/auth/login|me|password|logout|invitations lookup·accept`、`/api/users`、`/api/orgs/{org}/invitations`；错误码/审计/限流；app 装配；prod 守卫 | 双后端 API 用例；setup 二次/并发 409；邀请单次/过期/撤销/重发；登录/锁定/`tv` 撤销；末位 sysadmin 409 | 3~4 人日 |
| **m4-3** Web | boot 门（auth_mode/setup_needed）；Setup/登录/邀请接受三屏；用户/邀请管理页；组织切换改 header；隐藏 dev lens；i18n；prototype 登录/邀请屏更新（UI 双基准） | 壳资产/键集；手动走查 TC-UI-06·07；local e2e REST 闭环 | 3~4 人日 |
| **m4-4** 收口 | `scripts/reset_admin.py`（break-glass）；RUNBOOK §1.ab 实操复核；`.env.example`；requirements/design/TEST-CASES 完成态回写；全量 gate + 复审 | 双后端双模式 0 skipped；文档版本/检查点闭合；issue #28 验收评论 | 2~3 人日 |

> 总计约 **13~17 人日**；按本仓多 Agent 段节奏约 **9~13 个工作日**。各段可独立评审/合入，PR base `develop`。

---

## 三、关键默认口径（已写入 D25/FR-9；有异议走 issue 评论）

| 项 | 口径 |
|---|---|
| 模式 | `LATTICE_AUTH_MODE=local/sso`，默认 `sso`；同实例二选一 |
| 登录键 | `username`；email 可选、不作登录键（lower-case + 部分唯一） |
| 首启 | `POST /api/setup` 零用户时建首 sysadmin（可同事务建首组织并任 org_admin）；`LATTICE_INIT_PASSWORD` 门禁；`instance_setup` 单例；sso 模式 404 |
| 邀请 | `org_admin` 邀本组织（member/org_admin）；`sysadmin` 全局建号/停用/重置；token 32B urlsafe、只存 sha256、单次、72h、可撤销/重发；无 SMTP，管理员复制链接线下交付 |
| 会话 | HS256 JWT（独立 `LATTICE_SESSION_SECRET`、`aud=knowledge-lattice-web`、`typ=session`、`tv`）；TTL 12h；localStorage Bearer |
| 撤销 | 改密/重置 `tv++`；停用即时 401；登出仅清客户端 |
| 限流 | 进程内 username+IP：5 次/15min 锁 10min（可配） |
| 重置 | 一次性 `purpose=reset` 链接 + break-glass CLI；org_admin 不能重置他人 |
| MCP | 本地 token 只 Web/REST；MCP 拒绝 `via=local`，仍走 D18 委托/可信；local 无 SSO 时 MCP 不可用 |

---

## 四、文档落点（本批已完成）

| 文档 | 落点 |
|---|---|
| `docs/requirements.md` | v0.10：D25 行、FR-9、§8 M4、§9 待决-2 注/风险行 |
| `docs/design.md` | v0.10：§3 模块、§4 DDL、§5.5 local 块、§6.2 端点、§8 M4、§9 测试策略、§10 风险 |
| `docs/TEST-CASES.md` | v1.10.0：TC-AUTH-06~10、TC-UI-06·07（计划）、§六 M4 行 |
| `docs/known-gaps.md` | G-31 邀请无 SMTP；G-32 本地口令残余；G-33 无 hybrid；G-34 localStorage/撤销窗口 |
| `RUNBOOK.md` | §1.ab 内置账号与邀请（首启/邀请/重置/撤销/MCP 边界） |
| `AGENTS.md` | M4 立项状态 + 模块清单 |
| `.env.example` | AUTH_MODE / SESSION_SECRET / INIT_PASSWORD / TTL / 限流 |
| `prototype/index.html` | **待 m4-3 更新**（登录/setup/邀请屏）——本批不改 |

---

## 五、测试与门禁

- 基线 1921+1（pg 臂 724）；M4 预计 +60~90 用例（pg 臂 +30~50）。
- 新增用例必须双后端参数化；`skip = 失败`、`-O` 双模式全量。
- **迁移水位断言是确定性改动**：`tests/test_scaf_03_migrations.py:100`、`tests/test_regress_m0a1_followups.py:58`、`tests/test_pg_scaff.py:435` 的 11→12 与自制迁移号顺延，同段更新。
- 现有 `auth_01~05` 在默认 sso 模式下必须全绿（回归红线）；local 模式新增独立 fixture，不污染 `app_env`。
- 壳用例 `tests/test_e2e_07_shell.py` 资产/视图清单随 m4-3 更新；TC-UI 手动走查不进门禁。

---

## 六、风险 / 挂账

- **G-31** 邀请/重置链接只能线下交付（无 SMTP）——泄露/运维成本；接 notifier 留缝。
- **G-32** 无 MFA/泄露库校验/共享限流；登录失败审计写放大；初始密码兜底需强制改密。
- **G-33** local 与 sso 同实例二选一；存量 JIT 用户无本地密码；local 无 SSO 时 MCP 不可用。
- **G-34** session 存 localStorage（XSS）；无 refresh；登出不撤销服务端；被盗 token 12h 内有效。
- **决策风险**：D25 修订 D16 的 local 适用性——实现中不得改动 sso 形态既有语义；`auth_mode` 默认必须保持 `sso`，避免现有部署/门禁行为漂移。
- **部署风险**：`LATTICE_SESSION_SECRET` 缺失/公开值必须启动即拒（与 dev JWT/mock IdP 同口径）；`LATTICE_INIT_PASSWORD` 在 prod+local 建议必填，防“谁先访问谁当管理员”。
- **反模式红线**：本地 session token 不进 MCP（D18 禁止 token 原样透传）；不做按 email 自动合并 SSO 账号（账号劫持）。

---

## 七、开工前检查

- [ ] issue #28 评论确认 §三 默认口径（尤其 4 个待拍板项）。
- [ ] 扫历史检查点遗留（m3-5 / m2-4 的认证面 followups）与 `known-gaps` G-25/G-26 口径。
- [ ] 确认测试门禁环境（`docker start lattice-pg` + `LATTICE_PG_DSN`）。
- [ ] 确认 `.env` 不含真实密钥；session secret 用强随机（≥32B）。
- [ ] 确认不提交/推送（除非用户明确要求）；分支 `develop_opencode`，PR base `develop`。

---

## 八、变更记录

| 日期 | 事项 |
|---|---|
| 2026-11-19 | 立项：用户裁定 V2 完整版；issue #28；requirements v0.10 / design v0.10 / TEST-CASES v1.10.0 / known-gaps G-31~G-34 / RUNBOOK §1.ab / AGENTS / `.env.example` 落笔（doc-only） |
