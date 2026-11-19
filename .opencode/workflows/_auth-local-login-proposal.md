# 用户登录改造评估：管理员预登记 / 邀请制（Dify 式）

> **性质**：评估稿，不是决策记录、不是实现。未改任何代码与 `docs/` 正文。
> **日期**：2026-11-19
> **依据**：本仓 `develop` @ `60a7121`；Dify 本机 checkout `79effdd498`（`~/develop/opensource/dify`）。
> **一句话结论**：方向可行，但这是**决策变更（建议 D25）**，不是重构；建议做「本地账号 + 邀请」的 POC 形态，保留 SSO 形态，**同实例二选一、不做混合账号绑定**；完整落地约 13~17 人日（本仓约 3~4 段），MVP 约 8~10 人日。

---

## 0. 结论摘要

| 问题 | 结论 |
|---|---|
| 现状有没有「用户登录」？ | **没有可用的人类登录**。只有 SSO 验签（真实 IdP 未接、待决-2 未决）、开发 JWT、静态 token；Web 是「粘贴 token」控制台，生产环境无路可走。 |
| Dify 到底是什么模型？ | 首次 `/setup` 建管理员 + 工作区；`ALLOW_REGISTER=False`（本机 checkout 默认）关闭公开注册；工作区管理员按邮箱邀请 → `PENDING` 账号 + Redis 邀请 token + 邮件/可复制链接 → 被邀请人设密码激活；登录邮箱+密码 → access/refresh/CSRF。 |
| 本仓能照抄吗？ | **不能照抄**：本仓没有 SMTP / Redis / Celery；账号是全局的、组织是多归属的；MCP/agent 走 D18 委托 token。要按本仓模型改造。 |
| 值不值得做？ | **作为 POC / 无 IdP 私有化部署：合理且必要**；**作为企业长期唯一身份源：不合理**（与 D16 冲突、口令面与身份漂移）。 |
| 是「简化」吗？ | **不是代码简化**。代码量净增（约 3.5k~4.5k 行 + 60~90 用例），简化的是**部署依赖与使用体验**。 |
| 最大风险 | 与 D16「不自建账号密码、管理员不建账号只配授权」正面冲突；必须走 issue + D25，不能当重构做。 |
| 工作量 | 完整 13~17 人日 / 4 段；若只做「POC 可用、无邀请」见 §10 的 V1（8~10 人日 / 3 段）；极简 V0 1~2 人日但违反 D18。 |

---

## 1. Dify 机制确认（源码实证）

### 1.1 首次启动：setup 建管理员 + 工作区

- `RegisterService.setup()`：创建 `Account` → `create_owner_tenant_if_not_exist()` → 落 `DifySetup` 记录（[account_service.py:1699](../opensource/dify/api/services/account_service.py#L1699)）。
- `POST /setup` 是**匿名**端点，仅自托管版本；`INIT_PASSWORD` 环境变量可作首启门禁（未设置则直接可 setup）（[setup.py](../opensource/dify/api/controllers/console/setup.py)、[init_validate.py](../opensource/dify/api/controllers/console/init_validate.py)）。
- 前端 `/install` → 初始化密码 → `/setup` 表单（[web/app/install](../opensource/dify/web/app/install)）。

### 1.2 公开注册默认关闭

- `ALLOW_REGISTER` 默认 `False`（[configs/feature/__init__.py:1595](../opensource/dify/api/configs/feature/__init__.py#L1595)）。
- 邮箱注册入口有 admission 装饰器：登录/注册开关任一关闭 → `403`（[flask_admission.py](../opensource/dify/api/controllers/console/flask_admission.py)）。
- 所以本机 checkout 的默认形态就是：**没有公开注册，只能被邀请**。

### 1.3 邀请流程

- 控制台 `POST /workspaces/current/members/invite-email`（[members.py:227](../opensource/dify/api/controllers/console/workspace/members.py#L227)）：
  - 按邮箱找账号；不存在 → 建 `PENDING` 账号（用户名取邮箱 @ 前段）+ 建 `TenantAccountJoin`（工作区成员关系）+ `requires_setup=True`；
  - 已存在且非 PENDING：非成员时按配置补成员关系/RBAC 角色；已是成员 → `AccountAlreadyInTenantError`；
  - 生成邀请 token（uuid4）存 Redis `member_invite:token:{token}`，TTL `INVITE_EXPIRY_HOURS`，内容 `{account_id, email, workspace_id, role, requires_setup}`（[account_service.py:1922](../opensource/dify/api/services/account_service.py#L1922)）；
  - 异步发邀请邮件（`send_invite_member_mail_task.delay`）；
  - **响应里同时返回 `url=/activate?email=...&token=...`**，前端邀请结果弹窗可复制链接（[invited-modal](../opensource/dify/web/app/components/header/account-setting/members-page/invited-modal)）。
- 被邀请人：`/activate` 校验 token → 设姓名/密码/语言/时区 → 账号 `ACTIVE`（[activate.py](../opensource/dify/api/controllers/console/auth/activate.py)、[invite-settings/page.tsx](../opensource/dify/web/app/signin/invite-settings/page.tsx)）。

### 1.4 登录与会话

- `POST /console/api/login`：邮箱 + 密码 → `access_token` / `refresh_token` / `csrf_token`；`libs/token.py` 同时支持 Authorization Bearer 与 HttpOnly cookie（[token.py](../opensource/dify/api/libs/token.py)）。
- JWT 用 `SECRET_KEY` HS256（[passport.py](../opensource/dify/api/libs/passport.py)）。
- 密码哈希是 **PBKDF2-HMAC-SHA256，10,000 次**（[password.py](../opensource/dify/api/libs/password.py)）——按 2026 年标准偏弱，**不要照抄**。
- 账号状态 `pending / uninitialized / active / banned / closed`（[models/account.py:81](../opensource/dify/api/models/account.py#L81)）。

### 1.5 角色与工作区

- 角色 `owner / admin / editor / normal / dataset_operator`；账号全局、工作区（tenant）隔离。
- 与 Dify 的差异：Dify 的「管理员」主要是**工作区管理员**；本仓有跨组织的 `sysadmin` 与组织内 `org_admin` 两层。

### 1.6 依赖差异（关键）

| Dify 依赖 | 本仓现状 | 影响 |
|---|---|---|
| SMTP / Celery 发邀请邮件 | 无邮件、无队列 | 邀请只能「管理员复制链接/码线下交付」 |
| Redis 存邀请 token | 无 Redis（D2 零中间件） | 邀请 token 落库（sha256 + TTL + 单次消费） |
| 邮箱作为账号唯一键 | `users.username` 是唯一键，无 email 列 | 需决定 username / email 谁是登录键 |
| 账号 + 工作区成员关系同建 | 账号全局、成员关系按组织 | 邀请 = 建 pending 账号 + 建 membership |
| access + refresh + CSRF | 现有 Web 是 localStorage Bearer | 可先单 session JWT，不做 refresh |

### 1.7 映射表

| Dify | 本仓建议 | 备注 |
|---|---|---|
| `Account` | `users` | 全局唯一 |
| `Tenant` / workspace | `orgs` | 多组织 |
| `TenantAccountJoin.role` | `user_org_memberships.role` | `org_admin` / `member` / `sem_restricted` |
| setup 管理员 + owner 工作区 | `sysadmin` + 首个组织 `org_admin` | setup 同事务 |
| member invitation | 新表 `user_invitations` | 新载体 |
| `PENDING` 账号 | `users.status='invited'` | 不能登录 |
| 邮箱+密码登录 | 用户名+密码（email 可选） | 无 SMTP |
| access/refresh/CSRF | 单 session JWT | phase 1 不做 refresh |
| `ALLOW_REGISTER=False` | 不提供公开注册端点 | 仅接受邀请 |

---

## 2. 本仓现状盘点

### 2.1 现有认证路径

`authenticate()`（[domain/auth.py:234](src/knowledge_lattice/domain/auth.py#L234)）按序：

1. **SSO 验签器**（`LATTICE_SSO_PROVIDER=mock-idp` 时）：验签 → `aud` 校验 → `act` 解析 → **JIT 建档**（[domain/auth.py:151](src/knowledge_lattice/domain/auth.py#L151)、[domain/auth.py:202](src/knowledge_lattice/domain/auth.py#L202)）；
2. **开发 JWT**：仅 `environment != prod`；
3. **静态 token**：`sha256(users.token_hash)` 直查，仅 dev/test；
4. 生产：只认 SSO/委托 token，dev JWT 与静态 token 一律拒绝。

其他：

- 委托 token / 可信子系统（D18）在 `authenticate_trusted()` / MCP `_auth_and_org` 中；
- 组织上下文 `resolve_org`：claim 优先、`X-Org-Id` 兜底、不一致/缺失 400（D18）；
- 组织成员校验在 `org_scoped`，角色 `org_admin` / `member` / `sem_restricted`。

### 2.2 缺失面（逐条）

| 缺失 | 证据 | 后果 |
|---|---|---|
| `users` 无密码、无 email、无 status | [0001_schema_v1.sql:55](src/knowledge_lattice/store/sqlite/migrations/docs/0001_schema_v1.sql#L55) | 无法本地登录 |
| 无登录/注册/邀请端点 | `api/admin.py` 只有 orgs/members/grants 等；无 `/api/auth/*`、无 `/api/users` | 无法预登记 |
| 无登录页 | `web/index.html` 是 token 粘贴控制台；`boot()` 未连接就打开「连接设置」（[app.js:551](src/knowledge_lattice/web/app.js#L551)） | 真人不可用 |
| 首个 sysadmin 无 bootstrap | RUNBOOK 无此节；无 CLI/端点；生产只能直接改库 | 部署死锁 |
| 成员必须先 SSO JIT | `POST /api/orgs` 用户不存在 404，文案「管理员不建账号——建档走 SSO JIT」（[admin.py:176](src/knowledge_lattice/api/admin.py#L176)）；`POST members` 同样 404 | 管理员无法先把人建好 |
| 真实 IdP 未接 | `build_sso_verifier` 只有 `none|mock-idp`；待决-2 仍开放（[requirements.md:248](docs/requirements.md#L248)） | 生产无人类登录 |
| SSO JIT 默认放行任何 IdP 用户 | `_authenticate_sso_claims` 首次登录即建档 | 无 allowlist（虽无成员关系仍 403） |
| Web 身份切换依赖 dev 重签 | `reissue()` 调 `/api/dev/token`（[api.js:96](src/knowledge_lattice/web/api.js#L96)）；`switchOrg` 依赖它（[app.js:281](src/knowledge_lattice/web/app.js#L281)） | 生产 Web 无法切组织 |

### 2.3 结论：把需求拆成两个独立诉求

用户这句话其实包含两件事：

1. **Allowlist（只有登记用户能登录）**——与密码无关。即使继续用 SSO，也应该关闭 JIT、改成管理员预登记。
2. **自包含凭据（不依赖 IdP 也能登录）**——必须引入本地密码/会话。

两者可以分开做：

- 只做 1 = 方案 A（保留 D16，但仍需真实 IdP，POC 仍不可用）；
- 1+2 = 方案 B/C（Dify 式，POC 可用，但需要 D25 决策）。

---

## 3. 方案选项

| 维度 | A 仅 allowlist（SSO） | B 本地账号 + 邀请（Dify 式） | C 双模式 local/sso（推荐目标） | D 一次性登录码（无密码） |
|---|---|---|---|---|
| 外部依赖 | 真实 IdP（待决-2） | 无 | local 无 / sso 有 | 无 |
| 人类登录 | SSO | 用户名 + 密码 | 密码（local）/ SSO（sso） | 管理员发码 |
| 公开注册 | 关闭 / JIT gate | 关闭（仅邀请） | 关闭 | 关闭 |
| 代码增量 | 小 | 大 | 大 + 模式分支 | 中 |
| 安全面 | 低（复用 IdP） | 高（口令/重置/爆破） | 高（同 B） | 中（码泄露/重放） |
| 与 D16 | 兼容（改 JIT 行为） | 冲突（需 D25） | 仅 local 形态冲突（D25） | 冲突较小（无密码） |
| POC 可用 | **否** | 是 | 是 | 是 |
| 工作量（人日） | 6~8 | 13~17 | 15~19 | 8~10 |

**推荐**：目标形态 C；第一期只做 B（local 模式），`sso` 模式保持现状；**不做混合账号绑定**（见 §5.2）。D 只适合「只想让演示能登录、不想维护密码」的最小诉求。

> 口径：§7 的 13~17 人日指 **B / local 形态**；C 的双模式配置分支约 +2 人日，归入 §7.3「企业共存」档。

---

## 4. 推荐方案设计（C，phase 1 = B）

### 4.1 身份与账号模型

- **账号注册表是唯一 allowlist**：`users` 行存在且 `status='active'` 才能登录；`invited`（待接受）不能登录；`disabled_at` 非空不能登录。本地密码登录额外要求 `password_hash` 非空；SSO 登录额外要求用户已登记（local 模式关闭 JIT）。
- 角色不变：`sysadmin`（全局）+ `org_admin` / `member` / `sem_restricted`（按组织）。
- **账号创建只有管理员入口**：无公开注册端点；SSO 在 local 模式下**关闭 JIT**（未知 sub → 401 + 审计）。
- 谁可建：
  - `sysadmin`：全局建号/停用/恢复/重置、授撤 sysadmin；**不是组织成员时不走 org 端点**（`org_scoped` 403）——组织归属由该组织 `org_admin` 完成；
  - `org_admin`：只能邀请进**本组织**（角色 `member` / `org_admin`），不能建 sysadmin、不能动其他组织；
  - 跨组织副作用：org_admin 邀请会在全局 `users` 建一行（Dify 同款），但只给本组织 membership；sysadmin 可见全部账号。**需在文档明确**。

### 4.2 首次 setup

- `GET /api/auth/config`（匿名）：`{auth_mode, setup_needed}`；
- `GET /api/setup/status`（匿名）：`setup_needed = (COUNT(users)==0)`；`instance_setup` 单例只作**一次性记录与并发保护**（升级库已有用户但无 setup 行时，setup 仍需 409，走 CLI 重置/补管理员，见 §6.2）；
- `POST /api/setup`（匿名、仅一次）：`{username, password, display_name?, org_id?, org_name?, init_password?}` →
  - 建 `sysadmin`；
  - 可选同事务建首个组织 + 该管理员为 `org_admin`（推荐默认建，减少首启摩擦）；
  - 写 `instance_setup` 单例行 + 审计；
  - 返回 session token（自动登录）或要求跳登录；
  - **并发保护**：`instance_setup(id=1)` 唯一 + 事务内 `COUNT(users)==0` 双保险；第二个请求 409。
- **首启门禁**：`LATTICE_INIT_PASSWORD` 设置时请求必须携带；生产 + local 模式建议强制设置（否则谁先访问谁当管理员——Dify 的已知风险，我们应更严）。
- **`auth_mode=sso` 时**：setup 端点 404（本地密码不可用）；首个 sysadmin 仍靠部署期指定/`scripts/reset_admin.py`——这是现有缺口，建议同批用 CLI 兜底并在 RUNBOOK 写清。

### 4.3 邀请 / 登记流程（无 SMTP）

```
org_admin（本组织；setup 管理员在首组织自动是 org_admin）
  POST /api/orgs/{org}/invitations  {username, email?, role}
    → 事务内：users(status='invited', password_hash=NULL)
             + user_org_memberships(role)
             + user_invitations(token_hash, expires_at, invited_by)
    → 只返回一次 {invite_url, token, expires_at}
  → 管理员复制链接/码，线下交付（企业微信/邮件/口头）
被邀请人
  POST /api/auth/invitations/lookup  {token}（token 走 body，不进 URL/日志）
    → {username, org_name, role, expires_at}
  POST /api/auth/invitations/accept {token, password, display_name?}
    → 校验 token 哈希/未过期/未消费/用户 invited/成员关系仍在
    → 设 password_hash、status='active'、consumed_at
    → 返回 session token（自动登录）+ 审计
```

要点：

- **token**：32 字节 urlsafe，库中只存 `sha256`；单次消费；TTL 默认 72h；可撤销/重发（重发使旧 token 失效）；链接用 URL fragment（`#/invite?token=...`）避免进访问日志/Referer，accept 时放 body。
- **已存在账号**：
  - 已有密码且 active → 只加 membership（不重置密码）；
  - 存在但无密码（SSO 账号）→ 生成「设本地密码」邀请；
  - disabled → 拒绝，先恢复；
  - 用户名被占用 → 409（不自动顶替）。
- **pending 用户**：`status='invited'`，用户名已占位；可预授 grants（成员关系已存在），但登录前不能访问；过期后可重发或由 sysadmin 删除（需无引用）。
- **pending 唯一性**：同一 `(user_id, org_id)` 只保留一条未消费邀请；重发先在事务内 revoke 旧行再插新行（避免多 token 并存）。
- **谁可重置**：重置链接由 sysadmin 生成；`org_admin` 只能对本组织成员发/重发邀请，不能重置密码（防账号接管）——重置走 sysadmin 或 break-glass CLI。
- **默认角色**：`member`；`org_admin` 邀请可授予；`sem_restricted` 是否可邀请 → 建议不在邀请入口开放（走成员 PATCH，避免邀请语义复杂化）。
- **“登记” vs “邀请”**：邀请是主路径；sysadmin 的 `POST /api/users` 直建账号（**不设密码、返回邀请/设密链接**；管理员设临时密码 + 强制改密列为 phase 2，需加 `must_change_password` 列）只作离线/无组织场景的兜底，不替代邀请。

### 4.4 登录与会话

- 登录键：**`username`**（兼容现有 CSV 授权导入/导出、JIT 用户名字段）；`email` 可选，仅作联系/找回辅助，不作为唯一登录键。若用户坚持 Dify 式邮箱登录，需把 email 设为唯一登录键并迁移 CSV 口径——**工作量 +1~2 人日**，建议 phase 1 不做。
- 密码哈希：**stdlib `hashlib.scrypt`**（n=2¹⁴, r=8, p=1，16 字节随机 salt），`hmac.compare_digest`；不引新依赖（符合零中间件/最小依赖）。未知用户也做一次 dummy 校验，避免时序枚举。
- 会话：**HS256 JWT**，独立 `LATTICE_SESSION_SECRET`；claims `{iss:"knowledge-lattice", aud:"knowledge-lattice-web", sub:user_id, iat, exp, tv:token_version, typ:"session"}`；TTL 默认 12h；`via="local"`；前端沿用现有 `Authorization: Bearer` + localStorage（不做 cookie/CSRF，phase 1）。**独立密钥 + `typ` 保证与 SSO/dev JWT 不交叉接受**。
- 分支顺序：local session 验签插在 **SSO 之后、`prod` 拒绝 dev JWT/静态 token 之前**（`authenticate` 现有顺序，[domain/auth.py:234](src/knowledge_lattice/domain/auth.py#L234)）；local 模式不进入 SSO JIT 分支。
- 撤销：`users.token_version` 递增（改密/重置时）→ 旧 token `tv` 不符 401；停用由每请求 `get_user_auth` 的 `disabled_at` 即时生效。
- 登录限流/锁定：进程内（沿用 `ServiceRateLimiter` 风格）按 `username` + `IP` 计数，5 次失败锁 10 分钟（可配），429 + 审计；**多实例不共享**（G-25 同类，登记 known-gaps）；IP 取连接地址，反代部署需可信 `X-Forwarded-For` 配置（RUNBOOK 注记）。
- 登出：无状态，客户端清 token；服务端 204（可选 `auth.logout` 审计）。
- 改密：`POST /api/auth/password` 旧密码 + 新密码；成功后 `tv++` 并返回新 token（当前会话续命，其他会话失效）。
- 管理员重置：**发一次性重置链接**（复用邀请表 `purpose='reset'`），不直接把新密码告诉管理员；接受后 `tv++`、所有旧会话失效。
- 审计写失败按现有 `_audit` 口径传播（审计完整性优先；登录路径的可用性代价登记 known-gaps）。
- 审计（新增常量，单一登记处）：`auth.login` / `auth.login_refused`（reason=bad_password/unknown_user/disabled/locked）/ `auth.logout` / `auth.password_changed` / `auth.password_reset` / `auth.invite_created` / `auth.invite_accepted` / `auth.invite_revoked` / `user.created` / `user.disabled` / `user.enabled` / `user.sysadmin_changed` / `instance.setup`。**密码/token 永不进审计**。

### 4.5 组织上下文与切换

- 本地 session token **不带 org claim**；Web 始终发 `X-Org-Id`（现有 `resolve_org` 已支持 claim 缺失/头兜底）。
- `switchOrg` 从「dev 重签」改为「设置 `cfg.org` + 重载」；`GET /api/orgs` 返回 memberships 供选择。
- 新管理员没有组织时：setup 建首组织；若未建，Web 显示「联系管理员/创建组织」空态（sysadmin 可建）。
- **隐藏「以此身份查看」lens**（它是 dev 代签调试功能，local 模式下不可用，留着会误导）。

### 4.6 MCP / agent 边界（关键决策）

- 本仓的核心供数链路是 MCP（D18：委托 token / 可信子系统）。本地账号**只解决人类控制台登录**，不应替代 D18。
- 建议 phase 1：**本地 session token 仅用于 Web/REST 人类会话**；MCP 的 `_auth_and_org` 拒绝 `via="local"`（401），MCP 仍要求 SSO/委托/可信 token。
  - 理由：若把用户 session token 交给 agent，就是 D18 明令禁止的「token 原样透传」；给 agent 发长期用户 token 更糟。
- local 模式下若 `sso_provider=none`，则 **MCP 不可用**（没有委托 token 来源）。这是 POC 的可接受限制，但必须在 RUNBOOK/设计写清。
- 若 POC 必须同时有本地登录 + MCP：两条路——
  (a) 切 `auth_mode=sso`（企业形态）；
  (b) phase 2 增加「预登记时填 `sso_sub`（IdP 的 sub）」→ 委托 token 的 `sub` 能匹配本地账号（管理员显式绑定，不做自动邮箱匹配）；工作量 +1~2 人日。
- **不建议**：本地 token 直接放行 MCP；按 email 自动合并 SSO 账号（账号劫持风险）。

### 4.7 API 草案

| 方法 | 路径 | 认证 | 用途 |
|---|---|---|---|
| GET | `/api/auth/config` | 匿名 | `auth_mode` / `setup_needed` / `local_login_enabled` |
| GET | `/api/setup/status` | 匿名 | 首启状态 |
| POST | `/api/setup` | 匿名一次 | 建首 sysadmin（+首组织） |
| POST | `/api/auth/login` | 匿名 | 用户名+密码 → session |
| GET | `/api/auth/me` | Bearer | 用户 + 组织/角色 |
| POST | `/api/auth/password` | Bearer | 改密（tv++） |
| POST | `/api/auth/logout` | Bearer | 204 |
| POST | `/api/auth/invitations/lookup` | 匿名 | 校验邀请/重置 token（body 传 token） |
| POST | `/api/auth/invitations/accept` | 匿名 | 设密码、激活、发 session |
| GET | `/api/users` | sysadmin | 账号列表（含 status/orgs） |
| POST | `/api/users` | sysadmin | 直建账号（兜底；不设密码，返回邀请/设密链接） |
| PATCH | `/api/users/{id}` | sysadmin | 停用/恢复/授撤 sysadmin（末位 sysadmin 守卫） |
| POST | `/api/users/{id}/reset` | sysadmin | 生成重置链接 |
| GET/POST | `/api/orgs/{org}/invitations` | org_admin | 列出/创建本组织邀请 |
| DELETE | `/api/orgs/{org}/invitations/{id}` | org_admin | 撤销 |

> MVP 可只做 setup/login/me/password + org invitations；`/api/users` 全局管理面归完整版（见 §7.3）。

错误码建议（`body.code`）：`invalid_credentials`、`account_disabled`、`not_registered`、`login_locked`、`setup_completed`、`invite_invalid`、`invite_expired`、`invite_consumed`、`username_taken`、`last_sysadmin`。

### 4.8 配置项（`.env.example`）

```bash
LATTICE_AUTH_MODE=sso            # sso（默认，兼容现状）| local（POC 内置账号）
LATTICE_SESSION_SECRET=          # local 模式必填；prod 无默认值，缺失/默认值启动即拒
LATTICE_SESSION_TTL_S=43200      # 12h
LATTICE_INIT_PASSWORD=           # setup 门禁；prod + local 建议必填
LATTICE_INVITE_TTL_S=259200      # 72h
LATTICE_LOGIN_MAX_FAILS=5
LATTICE_LOGIN_WINDOW_S=900
LATTICE_LOGIN_LOCK_S=600
LATTICE_PASSWORD_MIN_LEN=10
```

### 4.9 数据模型草案（迁移 0012，双方言，docs 域）

```sql
-- users 增列（均可空/有默认，存量行零影响）
ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN password_hash TEXT;       -- scrypt 编码串（含 salt/参数）
ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
  CHECK (status IN ('invited','active'));
ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP;
ALTER TABLE users ADD COLUMN created_by TEXT;
CREATE UNIQUE INDEX ux_users_email ON users(email) WHERE email IS NOT NULL;

-- 邀请/重置（单表两用途；token 只存 sha256）
CREATE TABLE user_invitations (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_id      TEXT REFERENCES orgs(id) ON DELETE CASCADE,
  role        TEXT,                              -- invite 必填；reset 可空
  purpose     TEXT NOT NULL DEFAULT 'invite'
    CHECK (purpose IN ('invite','reset')),
  token_hash  TEXT NOT NULL UNIQUE,
  invited_by  TEXT NOT NULL,
  expires_at  TIMESTAMP NOT NULL,
  consumed_at TIMESTAMP,
  revoked_at  TIMESTAMP,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 首启单例（防并发 setup）
CREATE TABLE instance_setup (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  completed_at  TIMESTAMP NOT NULL,
  admin_user_id TEXT NOT NULL REFERENCES users(id)
);
```

说明：

- `status` 只表达 `invited|active`；停用继续用既有 `disabled_at`（全仓已按它过滤），避免两套语义打架；登录判据 = `status='active' AND password_hash IS NOT NULL AND disabled_at IS NULL`。
- 存量 JIT/SSO 用户 status 默认 `active`、password NULL：sso 模式照常；local 模式下他们不能密码登录，由管理员发「设密码」邀请/重置链接（文档写清）。
- `POST /api/orgs` / `POST members` 选择 org_admin 时应拒绝 `status='invited'`（防“无 active 管理员的组织”），错误文案也要从「管理员不建账号」改为「先建用户/邀请」。

### 4.10 UI 草案（Web 薄壳）

- **boot 门**：`GET /api/auth/config` →
  - `auth_mode=sso` → **保持现状**（连接设置：粘贴 token / dev 重签），不显示登录屏；
  - `auth_mode=local` + `setup_needed` → **Setup 屏**（用户名/密码/显示名/首组织）；
  - `auth_mode=local` + 无有效 session → **登录屏**（用户名/密码，错误统一文案；开发环境保留「高级：粘贴 token」）；
  - 有 session → 现有应用；`/api/auth/me` 拉 orgs/角色。
- **邀请接受屏**：读 fragment token → 显示「{org} 邀请你以 {role} 身份加入」→ 设密码 → 自动登录。
- **用户与邀请页**（新 nav，或并入 orgs 视图）：
  - sysadmin：全部用户（搜索/状态/组织/sysadmin 开关/停用/重置链接）；
  - org_admin：本组织成员 + 邀请（角色/过期时间/撤销/重发）；
  - 邀请成功弹窗显示**可复制链接/码**（Dify 同款）。
- **顶栏**：用户名 + 角色徽标 + 改密 + 登出；组织 picker 改为 header 切换；隐藏 lens/代签。
- **i18n**：新增约 40~60 个 zh/en 键（登录/设置/邀请/用户管理/错误码），保持 `zh`/`en` 键集相等（现有 ui-be 有零缺零死检查惯例）。
- **保留**：「连接设置 → 直接粘贴已签 token」作为高级/MCP 调试入口；dev 模式仍可用 dev 重签。

---

## 5. 合理性评估

### 5.1 合理的一面

1. **解除交付阻塞**：真实 IdP 未接、待决-2 未决；现在生产环境没有人类登录路径，Web 只能粘 dev token。本地账号让 POC 可以独立演示/部署。
2. **闭合 bootstrap 缺口**：首个 sysadmin 无创建路径（只能改库）；setup 把它变成一个正常流程。
3. **allowlist 是真实收益**：SSO JIT 目前对任何 IdP 用户自动建档；预登记后「只有登记用户能登录」对敏感知识库更合适——**这一点即使不做密码也值得做**。
4. **管理闭环**：现在 `POST members` 对未 JIT 的用户 404，管理员不能先把人建好；邀请/预登记闭合了「建人 → 入组 → 授权 → 登录」。
5. **符合私有化部署**：无外部 IdP、无邮件、无 Redis，延续 D2 零中间件/NFR-1。
6. **Dify 模式经过验证**：setup + 邀请 + 登录的心智模型用户熟悉，UI 可参考。

### 5.2 风险 / 不合理的一面

1. **与 D16 正面冲突**：D16 明文「身份走 SSO 透传验签 + JIT 建档，**不自建账号密码**」，design §5.5「**管理员不建账号只配授权**」（[requirements.md:216](docs/requirements.md#L216)、[design.md:807](docs/design.md#L807)）。这不是实现细节，是决策变更；必须 issue + D25，否则违反冻结纪律。
2. **不是代码简化**：新增口令/邀请/会话/限流/重置/审计，代码量净增；安全面从「复用 IdP」变成「自己承担口令安全」。所谓简化只是**部署依赖与使用体验**。
3. **第二身份源/漂移**：企业最终上 SSO/HR 后，本地账号会变成 shadow identity；D16 的原始理由（权限漂移、离职撤销）依然成立。若做混合登录，还要处理账号绑定/合并，复杂度陡增。
4. **无 SMTP/MFA/自助重置**：邀请链接靠线下交付（泄露风险）；忘记密码只能管理员发链接或运维 CLI；无 MFA；这些都要登记 known-gaps，不能假装企业级。
5. **MCP/agent 主链路没解决**：本地登录只覆盖人类控制台；MCP 仍要 SSO/委托 token。若 POC 的核心演示是 agent 供数，本地账号的帮助有限。
6. **状态组合变多**：invited/active/disabled、多组织、org_admin 跨组织建号、末位 admin 守卫、pending 用户与 grants/CSV 的交互——测试矩阵显著变大。
7. **“一个管理员账号”与现有两层管理员不一致**：本仓是 sysadmin + org_admin；产品上要讲清两者的区别，否则用户会以为 org_admin 能建组织/建账号。

### 5.3 结论（条件性）

- **作为 POC / 无 IdP 私有化部署的登录方案：合理，建议做**；但按「部署形态」做，不按「替换 SSO」做。
- **作为企业长期唯一身份源：不建议**；企业形态仍应 SSO + HR 同步，本地账号只作过渡/离线兜底。
- **作为“简化现有模块”的说法：不成立**；应向决策者如实说明这是“用外部 IdP 依赖换内部口令安全面”。
- **落地方式**：D25 双模式（local/sso），默认 sso 保持兼容；phase 1 不做 hybrid、不做邮箱登录、不做 refresh token、不做 MFA。

---

## 6. 对现有实现的冲击影响

### 6.1 分层影响

| 层 | 影响 | 具体 |
|---|---|---|
| DB schema / migrations | **中** | 0012 双方言：`users` +6 列、`user_invitations`、`instance_setup`、部分唯一索引；迁移水位断言 3 文件 4~6 处（[test_scaf_03_migrations.py:100](tests/test_scaf_03_migrations.py#L100)、[test_regress_m0a1_followups.py:58](tests/test_regress_m0a1_followups.py#L58)、[test_pg_scaff.py:435](tests/test_pg_scaff.py#L435)） |
| Store 协议 + 双方言 | **高** | 新协议方法约 12~15 个 × 2 方言：create_user / find_by_username/email / set_password / get_auth（扩列）/ list_users / update_status / bump_token_version / create·get·consume·revoke invitation / setup 单例 / count_sysadmins；约 500~700 行 |
| domain/auth | **中高** | 新增 local 分支、session 签发/验签、scrypt、登录限流、JIT gate、tv 撤销；**不改** SSO/委托/可信语义；`AuthContext.via` 增 `local` |
| REST API | **中** | 新增 `api/auth.py`（~12 端点）+ users/invitations；`app.py` 装配；错误码/审计；`POST /api/orgs`/members 文案与 invited 校验 |
| Web | **高** | boot 门 + setup/login/invite 三屏 + 用户/邀请页 + 顶栏用户菜单 + 组织切换改造 + 隐藏 lens + i18n ~50 键；约 600~900 行 |
| MCP | **低~中** | 若 local token 仅 Web/REST：`_auth_and_org` 拒绝 `via="local"`（~10 行）；D18 委托/可信不变 |
| Tests | **中高** | 新 4~6 文件、60~90 用例、双后端；门禁 1921+1 → 约 2000+；迁移水位/壳资产/旧文案断言 |
| Docs/决策 | **高** | D25 + requirements/design §4/§5.5/§6.2/§8 + TEST-CASES + known-gaps + RUNBOOK + AGENTS + `.env.example` |
| Ops | **中** | 首启 setup、INIT_PASSWORD、session secret、重置/break-glass CLI、邀请线下交付、密钥轮换 |
| 安全 | **高** | 新增口令面；限流/锁定/撤销/审计；无 MFA/无邮件重置（known-gaps） |

### 6.2 兼容性与行为变化清单

**默认不变（重要）**：

- `LATTICE_AUTH_MODE` 默认 `sso` → 现有 SSO/JIT/委托/可信/dev JWT/静态 token 行为全部保留；现有 1921+1 的行为用例应零感知（迁移水位断言需随 0012 更新，属预期改动）。
- 新列 nullable/default、新表 → 现有 `seed_user`（`INSERT INTO users(id, username)`，[helpers.py:33](tests/helpers.py#L33)）与所有显式列查询不受影响。
- `users.status` 默认 `active` → 存量用户视为 active；`get_user_auth` 扩列后仍返回原字段。

**local 模式下的行为变化（需在 TEST-CASES 固化）**：

| 变化 | 之前 | local 模式 |
|---|---|---|
| 未知 SSO sub | JIT 建档 | **401 not_registered + 审计**（JIT 关闭） |
| 公开注册 | 无（本来就没有） | 仍无；只有邀请接受 |
| 首个 sysadmin | 无法创建 | setup 创建 |
| `POST /api/orgs` org_admin | 用户存在即可 | 用户存在且 `status='active'` |
| `POST members` 未登记用户 | 404 | 仍 404；改走邀请 |
| Web 连接 | 粘 token / dev 重签 | 登录；组织 = header；lens 隐藏 |
| 本地 token 用途 | — | Web/REST；MCP 拒绝（建议） |
| prod dev JWT/静态 token | 拒绝 | 仍拒绝 |

**结构兼容**：

- `POST /api/orgs` / members 的 404 文案「管理员不建账号——建档走 SSO JIT」需改；`test_orgs_admin`/`test_admin_members` 的 docstring 语义（JIT 后入组）在 sso 模式仍成立，但 local 模式需补“邀请后入组”。
- 迁移号 0011→0012；pg 测试自制迁移号（12/13/14）顺延。
- `test_e2e_07_shell.py` 资产清单/视图注册断言需加 login/users 脚本（若新增文件）。
- `test_v11_schema.py` 的 `INSERT INTO users(id, username)` 仍可用；无需改。
- `GET /api/orgs/{org}/members` 建议补 `status`（invited/active）与 `invited_at`/`expires_at` 展示字段（纯增量）；CSV 授权导入可继续按 username 命中 pending 用户（预授权）。
- email 统一小写存储（唯一索引前置归一），避免大小写重复账号。

### 6.3 文件级影响（预估）

**后端**

- `src/knowledge_lattice/config.py`：`auth_mode`、`session_secret`、`init_password`、TTL/限流 6~8 项 + `_validate` + prod 守卫。
- `src/knowledge_lattice/domain/auth.py`：local 分支、session、scrypt、限流、JIT gate；或拆 `domain/accounts.py`（建议拆，auth 已 559 行）。
- `src/knowledge_lattice/domain/audit_events.py`：+12 常量；`store/audit_chain.py` 的 `_target_of` 加 `user.`/`auth.` 映射。
- `src/knowledge_lattice/api/auth.py`（新）：setup/login/me/password/invitations；`api/users.py`（新）或并入 admin。
- `src/knowledge_lattice/api/admin.py`：org_admin 校验、members 文案、邀请入口（若不放 auth.py）。
- `src/knowledge_lattice/app.py`：注册路由、异常映射、启动守卫。
- `src/knowledge_lattice/store/backend.py` + `sqlite/backend.py` + `postgres/backend.py`：协议与实现。
- `store/{sqlite,postgres}/migrations/docs/0012_*.sql`（新）。
- `src/knowledge_lattice/mcp/server.py`：拒绝 local token（若选择）。
- `scripts/reset_admin.py`（新，break-glass）。

**前端**

- `web/api.js`：auth 函数、session 存取、`connected()` 改造、401 → 登录屏（替代 openConn）。
- `web/app.js`：boot 门、用户菜单、switchOrg、隐藏 lens。
- `web/views/login.js`（新）、`web/views/users.js`（新）。
- `web/index.html`、`web/style.css`、`web/i18n.js`。

**测试**（新增 4~6 文件 + 改 4~5 文件）

- `tests/test_auth_06_local_login.py`、`test_auth_07_setup.py`、`test_auth_08_invite.py`、`test_auth_09_users_admin.py`，或按域合并。
- `tests/conftest.py`：local-mode app fixture（不改变默认 app_env）。
- `tests/test_auth_03_sso_jit.py`：local 模式 JIT gate 用例（sso 模式原用例不动）。
- `tests/test_scaf_03_migrations.py`、`test_regress_m0a1_followups.py`、`test_pg_scaff.py`：水位 11→12、自制迁移号顺延。
- `tests/test_e2e_07_shell.py`：资产/视图清单。

**文档**

- `docs/requirements.md`：D25（或 D16 v2）+ 可能新增 FR-9「账号与登录」+ §8 M4 + §9 待决-2 口径更新（SSO 可后置）+ 风险表（本地口令）。
- `docs/design.md`：§3 模块（auth/accounts/api）、§4 DDL、§5.5 重写、§6.2 端点表、§8 M4、§10 风险。
- `docs/TEST-CASES.md`：TC-AUTH-06~09、TC-UI-05；TC-AUTH-03 补 JIT gate。
- `docs/known-gaps.md`：G-31 邀请无邮件交付；G-32 本地口令安全（无 MFA/无泄露库校验/进程内限流）；G-33 无 hybrid 账号绑定；G-34 session localStorage/撤销窗口（按实际取舍）。
- `RUNBOOK.md`：首启 setup、init password、邀请交付、管理员重置、break-glass CLI、session secret 轮换。
- `AGENTS.md`：M4 状态/门禁数；`.env.example`；`README.md` quickstart。
- `prototype/index.html`：登录/setup/邀请屏（UI 基准，可选但建议）。

### 6.4 测试/门禁影响

- 基线 1921+1（pg 臂 724）；预计 +60~90 用例 → 约 1990~2010；pg 臂约 +30~50。
- 新增用例必须双后端参数化；`skip = 失败` 语义不变。
- 迁移水位断言是**确定性会红**的已知改动（3 文件 4~6 处），要在同一段内更新，避免误判回归。
- 现有认证用例（auth_01~05）在默认 sso 模式下应全绿；local 模式新增独立 fixture，避免污染既有 `app_env`。
- Web 壳用例是字符串/DOM 资产断言，新增脚本/文案需同步更新；不做浏览器自动化（manual 标记不进门禁）。

### 6.5 文档/决策影响

- **这是决策变更，不是实现变更**：按 AGENTS §2，先 issue（设计评审）+ D 编号，再改 requirements/design；实现问题走 TEST-CASES/issue。
- 建议 **D25 新增**（保留 D16 历史与 sso 形态），不原地改写 D16；design §5.5 引用 D25；D16 在 sso 形态继续有效。
- 版本纪律：requirements/design 决策变更升版并写明 D25；TEST-CASES/known-gaps 随实现回写；RUNBOOK/AGENTS 联动。
- 流程：新里程碑 M4（或 M3.6），`_m4-plan.md` 段序；分支 `develop_opencode`，PR base `develop`；除非用户明确要求，不 commit/push。

---

## 7. 工作量估算

### 7.1 校准（用仓内同类段类比）

| 参照 | 规模 | 段数 |
|---|---|---|
| m3-1 R1（管理面补强） | 23 文件 / +3,042 行 / 76 用例 / 16 store 方法 / 4 测试文件 | 1 段 |
| ui-1（Web 原型级重建） | +2,046 行 / 六视图 | 1 段 |
| m2-4（SSO+委托+可信） | +77 用例 / 认证语义扩展 | 1 段 |
| 本需求 | 约 3.5k~4.5k 行 / 60~90 用例 / 3 个新屏 / 12~15 store 方法 | **约 2.5~3 个 m3-1 规模** |

### 7.2 分解（完整版）

| 工作包 | 内容 | 人日 |
|---|---|---|
| W1 决策与文档 | issue、D25、requirements/design §4/§5.5/§6.2/§8、版本行 | 2 |
| W2 schema + store | 0012 双方言、协议 12~15 方法 ×2、水位测试 | 3 |
| W3 domain auth | scrypt、session JWT、登录/限流/锁定、JIT gate、tv、审计常量 | 2 |
| W4 REST | setup/auth/me/password/invitations/users ~12 端点 + 错误面 | 2.5 |
| W5 Web | boot 门、setup/login/invite、用户/邀请页、组织切换、lens、i18n | 3 |
| W6 Tests | 4~6 文件、双后端、60~90 用例、门禁、迁移/壳断言 | 3 |
| W7 收口 | RUNBOOK/.env/README/AGENTS、break-glass、复审修复、gate | 1.5 |
| **合计** | | **17（低配 13~14——按 §7.5 裁剪）** |

> 人日是“人工等价”；本仓多 Agent 段节奏通常快于人工等价（m3-1 约 3 个日历日）。因此完整版约 **4 段 / 9~13 个工作日**。

### 7.3 三档

| 档 | 范围 | 人日 | 段数 / 工作日 |
|---|---|---|---|
| **MVP**（推荐先做） | setup + 本地登录 + 首组织 org_admin 邀请 + 登录/邀请 UI + 双后端测试 + 最小文档 | **8~10** | 3 段 / 6~8 天 |
| **完整**（Dify 等价核心） | + 全局用户管理/多组织邀请、改密/重置、锁定、tv 撤销、break-glass CLI、组织切换、完整审计/文档 | **13~17** | 4 段 / 9~13 天 |
| **企业共存** | + sso 模式双跑/账号绑定（sso_sub）、邮件 notifier、refresh、MFA/更严策略 | **+6~9** | 5~6 段 / +5~8 天 |

**最容易被低估的三块**：① store 双方言方法（机械但量大）；② Web 登录门 + 三个新屏 + i18n（现有壳 3.9k 行，风格/交互要一致）；③ 文档/决策 + 双后端门禁（本仓的“隐性成本”约占 20~25%）。

### 7.4 段计划（建议）

| 段 | 范围 | 验收 |
|---|---|---|
| **m4-1** 账号底座 | 0012 迁移 + store 协议/双方言 + domain（scrypt/session/JIT gate/tv）+ audit 常量；store/domain 级双后端用例 | 迁移水位/约束/并发 setup 单例；现有门禁不降 |
| **m4-2** 认证 API | setup/login/me/password/invitations + users/invitations 管理端点；错误码/审计/限流 | 双后端 API 用例；setup 二次 409；邀请单次/过期/撤销；登录/锁定/撤销 |
| **m4-3** Web | boot 门 + setup/login/invite 三屏 + 用户/邀请页 + 组织切换 + lens + i18n；壳测试 | 手工走查 + 壳资产/键集；e2e REST 闭环 |
| **m4-4** 收口 | break-glass CLI、RUNBOOK/.env/README/AGENTS、docs 回写、全量 gate、复审 | 双后端双模式 0 skipped；文档版本/决策记录闭合 |

MVP 可把 m4-1+m4-2 合并、m4-4 只做 RUNBOOK + gate；砍掉 org_admin 邀请/改密/CLI。

### 7.5 可裁剪项（按价值排序）

1. 不做全局用户管理面（只组织邀请 + setup）——省 ~1.5 人日，但多组织/离线场景退化。
2. 不做直建账号，只做邀请——省 ~1 人日，离线场景不便。
3. 不做改密/重置（只 break-glass CLI）——省 ~1.5 人日，安全性差。
4. 不做 users 管理页（只 API + 简单表格）——省 ~1.5 人日。
5. 不做 i18n 全量（只 zh）——违反 FR-8，不建议。
6. 不做 prototype 登录屏——省 ~1 人日，UI 基准不一致。

---

## 8. 风险与开放问题（需要拍板）

| # | 问题 | 选项 | 建议 |
|---|---|---|---|
| 1 | 邀请怎么交付？ | 复制链接/码线下发；接 SMTP；企业微信/钉钉 | **复制链接/码**（无中间件）；SMTP 留缝 |
| 2 | 登录键用 username 还是 email？ | username（兼容 CSV/JIT）；email（Dify 式） | **username**；email 可选，phase 2 再议 |
| 3 | org_admin 能否建账号/邀请？ | 仅 sysadmin；org_admin 可邀本组织 | **org_admin 可邀本组织**（Dify 式），sysadmin 保留全局 |
| 4 | local 模式下 MCP 怎么认证？ | 仅 Web/REST（MCP 需 sso）；本地 token 也放行 MCP；预登记 sso_sub | **仅 Web/REST**；需要时 phase 2 加 sso_sub |
| 5 | 是否保留 SSO 双模式？ | 双模式（默认 sso）；彻底替换 | **双模式**；默认 sso，POC 配 local |
| 6 | 会话放哪？ | localStorage Bearer（现状）；HttpOnly cookie + CSRF | **localStorage** phase 1；cookie 作为演进 |
| 7 | 首个组织？ | setup 自动建；登录后手动建 | **setup 自动建**（可留空则向导） |
| 8 | 管理员重置？ | 一次性重置链接；临时密码 + 强制改；仅 CLI | **重置链接** + CLI break-glass |
| 9 | 无 MFA/无邮件重置/多实例限流不共享，能接受吗？ | 接受并登记；补 MFA/SMTP | **接受并登记 known-gaps**（POC） |
| 10 | 是否更新 prototype？ | 更新；只改实现 | **更新**（UI 双基准纪律） |

---

## 9. 建议的下一步（不执行代码）

1. **先拍板 §8 的 1~5 项**（尤其 1/2/4/5），这四项决定数据模型与 API 形态。
2. 开 issue（设计评审）+ 起草 **D25**（见附录 C）；按冻结纪律更新 requirements/design（本评估不做）。
3. 写 `_m4-plan.md` 段序 + TEST-CASES 草案（TC-AUTH-06~09 / TC-UI-05），明确每段验收。
4. 按 m4-1 → m4-2 → m4-3 → m4-4 实施；每段跑双后端双模式 gate（0 skipped）。
5. 若最终决定不做本地密码：退回**方案 A**（allowlist + SSO）或**方案 D**（一次性码），但仍需解决首个 sysadmin bootstrap。

---

## 10. 裁剪版：如果目标是“先让 POC 能登录”

> 结论：**只去掉邀请，17→约 14 人日，仍然不小**；要降到 8~10，必须同时砍 setup 向导、用户管理页、重置/锁定，把管理员操作降到 CLI/env。代价是“POC 可用级”，不是“生产级”。

### 10.1 三项调整的实际节省

| 调整 | 节省 | 说明 |
|---|---|---|
| 去邀请 | **2~3 人日** | 去掉 `user_invitations`、token 生成/校验/撤销、accept 页、pending 状态；改为管理员设初始密码（仍需 `must_change_password` + 改密页，省不到 3） |
| username 登录 | **0.3~0.5 人日** | 原方案本来就是 username；只省 email 列/唯一索引/校验 |
| 保留 SSO 双模式 | **0（甚至 +0.5）** | 原方案已含；`auth_mode` 开关约 0.5 人日。去掉 SSO 才省 1~2，但破坏现有 1921+1 测试与企业路径，不建议 |

### 10.2 三档可选

| 档 | 范围 | 人日 | 段 |
|---|---|---|---|
| **V0 极简 token**（不推荐，仅救急） | 管理员 CLI 建用户 + 每用户静态 token；沿用现有「粘贴 token」UI；无密码、无登录页 | **1~2** | 1 |
| **V1 POC 可用**（建议先做） | env 首管 + CLI 建用户（初始密码）+ 登录页 + 改密 + 基础限流；无邀请、无 setup 向导、无用户管理页、无重置 | **8~10** | 3 |
| **V2 完整**（生产/企业） | 邀请 + setup 向导 + 用户页 + 重置 + org_admin + 完整审计/文档 | **13~17** | 4 |

### 10.3 V1 的最小范围（建议）

- **首管**：`LATTICE_BOOTSTRAP_ADMIN_USERNAME/PASSWORD` 启动时若零用户则建 sysadmin（幂等；不建 setup 端点/页面）；或 `scripts/create_admin.py`。
- **建用户**：`scripts/create_user.py --username --password [--must-change]`（sysadmin 执行）；管理员把临时密码线下交付；首登强制改密（可选）。
- **登录**：`POST /api/auth/login`（username+password → session JWT）、`/api/auth/me`、`/api/auth/password`、`/api/auth/logout`；登录页 + 改密弹层。
- **保留**：现有 SSO/委托/可信/dev JWT/静态 token 全部不动；加 `auth_mode=local|sso`（默认 sso）避免 local 登录在 sso 部署中暴露。
- **安全底线**：scrypt、基础限流（5 次/15min 锁 10min）、`tv` 撤销、审计 6~8 个事件；不做 MFA/自助重置/多实例限流。
- **测试/文档**：约 35~50 用例双后端；D25 + design §5.5/§4/§6.2 + TEST-CASES TC-AUTH-06 最小集 + RUNBOOK 首管/建用户/重置（CLI）。

### 10.4 代价（必须如实告知）

- 管理员知道用户初始密码；无自助重置（只能 CLI/管理员重设）；无 MFA；限流进程内；审计面小。
- V0 还违反 D18「静态 token 仅开发/测试」的生产口径——只适合临时演示，不能作为交付形态。
- V1 不是“生产级身份治理”：企业形态仍应回到 V2/SSO。

### 10.5 平台税（压不下去的部分）

| 项 | 人日 | 说明 |
|---|---|---|
| store 协议 + 双方言 | 2~3 | 即使只有 8~10 个方法，也要 SQLite/PG 双实现 |
| 双后端测试 + 门禁 | 2~3 | `skip = 失败`、`-O` 双模式 |
| 决策/文档 | 1.5~2 | D25 + requirements/design/TEST-CASES/RUNBOOK |
| **小计** | **5.5~8** | 低于这个数只能放弃本仓的工程/文档纪律 |

> 因此：**V1 的 8~10 人日是“还守纪律”的下限**；要 2~3 天，只能是 V0 或一次性脚本，不建议作为正式方案。


---

## 附录 A：Dify 证据索引

| 主题 | 文件 |
|---|---|
| setup 建 admin/workspace | [api/services/account_service.py:1699](../opensource/dify/api/services/account_service.py#L1699) |
| 注册/账号创建 | [api/services/account_service.py:1752](../opensource/dify/api/services/account_service.py#L1752) |
| 邀请成员 + PENDING + token | [api/services/account_service.py:1819](../opensource/dify/api/services/account_service.py#L1819) |
| 邀请 token 生成（Redis/TTL） | [api/services/account_service.py:1922](../opensource/dify/api/services/account_service.py#L1922) |
| 控制台邀请端点（返回 url） | [api/controllers/console/workspace/members.py:227](../opensource/dify/api/controllers/console/workspace/members.py#L227) |
| 激活 | [api/controllers/console/auth/activate.py](../opensource/dify/api/controllers/console/auth/activate.py) |
| setup/init password | [api/controllers/console/setup.py](../opensource/dify/api/controllers/console/setup.py)、[api/configs/deploy/__init__.py:33](../opensource/dify/api/configs/deploy/__init__.py#L33) |
| ALLOW_REGISTER 默认 False | [api/configs/feature/__init__.py:1595](../opensource/dify/api/configs/feature/__init__.py#L1595) |
| 邮箱注册 admission | [api/controllers/console/flask_admission.py](../opensource/dify/api/controllers/console/flask_admission.py) |
| 密码哈希（PBKDF2 10k） | [api/libs/password.py](../opensource/dify/api/libs/password.py) |
| 会话/CSRF cookie | [api/libs/token.py](../opensource/dify/api/libs/token.py) |
| 邀请设置前端 | [web/app/signin/invite-settings/page.tsx](../opensource/dify/web/app/signin/invite-settings/page.tsx) |
| 可复制邀请链接 | [web/app/components/header/account-setting/members-page/invited-modal](../opensource/dify/web/app/components/header/account-setting/members-page/invited-modal) |

## 附录 B：本仓证据索引

| 主题 | 文件/行 |
|---|---|
| 认证分支/JIT | [domain/auth.py:234](src/knowledge_lattice/domain/auth.py#L234)、[domain/auth.py:151](src/knowledge_lattice/domain/auth.py#L151) |
| `AuthContext.via` | [domain/auth.py:63](src/knowledge_lattice/domain/auth.py#L63) |
| `users` 表 | [0001_schema_v1.sql:55](src/knowledge_lattice/store/sqlite/migrations/docs/0001_schema_v1.sql#L55) |
| org_admin 用户不存在 404 文案 | [api/admin.py:176](src/knowledge_lattice/api/admin.py#L176) |
| members GET/POST | [api/admin.py:1096](src/knowledge_lattice/api/admin.py#L1096)、[api/admin.py:1124](src/knowledge_lattice/api/admin.py#L1124) |
| Web 连接/重签 | [api.js:43](src/knowledge_lattice/web/api.js#L43)、[api.js:96](src/knowledge_lattice/web/api.js#L96) |
| boot / switchOrg | [app.js:551](src/knowledge_lattice/web/app.js#L551)、[app.js:281](src/knowledge_lattice/web/app.js#L281) |
| 测试造数 | [conftest.py:419](tests/conftest.py#L419)、[helpers.py:33](tests/helpers.py#L33) |
| 迁移水位断言 | [test_scaf_03_migrations.py:100](tests/test_scaf_03_migrations.py#L100)、[test_regress_m0a1_followups.py:58](tests/test_regress_m0a1_followups.py#L58)、[test_pg_scaff.py:435](tests/test_pg_scaff.py#L435) |
| D16 | [requirements.md:216](docs/requirements.md#L216) |
| design §5.5 登录 | [design.md:807](docs/design.md#L807) |
| design §6.2 orgs/members | [design.md:1121](docs/design.md#L1121)、[design.md:1123](docs/design.md#L1123) |
| 认证事件常量 | [audit_events.py:80](src/knowledge_lattice/domain/audit_events.py#L80) |
| 限流/审计写放大 known-gaps | `docs/known-gaps.md` G-25/G-26 |
| 待决-2（SSO 协议） | [requirements.md:248](docs/requirements.md#L248) |

## 附录 C：D25 草案（供讨论，非最终）

> **D25 身份来源双形态与内置账号（拟）**
>
> POC/私有化部署可选择 `LATTICE_AUTH_MODE=local`：首个 `sysadmin` 由一次性 setup 创建；账号只能由管理员预登记/邀请创建（无公开注册）；`local` 模式下关闭 SSO JIT；本地会话仅用于 Web/REST 人类会话，**不替代 D18 委托 token** 与 MCP 供数链路。
>
> `LATTICE_AUTH_MODE=sso` 继续沿 D16/D18（SSO 验签 + JIT + 委托 token + 可信子系统）。同一实例 phase 1 **二选一**，不做兼容/账号绑定。
>
> 本决策修订 D16 中「不自建账号密码 / 管理员不建账号只配授权」在 `local` 形态下的适用性；D16 在 `sso` 形态继续有效。口令/邀请/会话安全基线（scrypt、单次邀请、限流、tv 撤销、审计）为本决策附件。
