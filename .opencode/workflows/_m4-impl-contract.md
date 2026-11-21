# M4 实施契约（m4-1~m4-4 冻结口径，2026-11-20）

> 本文件是段间**实现契约**（不是需求正文）——四个实施子任务的接口/命名/错误码以此为准；
> 与 `docs/design.md` §4/§5.5/§6.2、`docs/requirements.md` FR-9/D25 冲突时以正文为准并立即上报。
> 目的：避免四段各自发明方法名/响应字段导致返工。**不得提交/推送**（用户未授权）。

## 0. 通用纪律

- 工作分支 `develop_opencode`（已含 b73366d docs 批）；工作树直接改，不建 worktree。
- 仅改本段归属文件；跨段需要先改契约并告知 lead。
- 双后端参数化：store/API 新用例必须 sqlite + PG 双臂；`skip = 失败`。
- 测试命令（沙箱下 uv 缓存不可写）：
  - `LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice UV_CACHE_DIR="$PWD/.uv-cache" uv run --no-sync pytest <targets> -q`
  - 或 `.venv/bin/python -m pytest <targets> -q`（已建 venv；PG 需 DSN）。
- 密码/token/密文**永不**进审计 payload、日志、错误消息。
- 默认 `auth_mode="sso"` 行为零变化：现有 TC-AUTH-01~05、e2e 全绿。
- `sso` 形态既有语义（JIT/委托/可信）不动；local 只加分支。

## 1. 配置（`src/knowledge_lattice/config.py`）

新增字段（默认值）与 env：

| 字段 | 默认 | env |
|---|---|---|
| `auth_mode: str` | `"sso"` | `LATTICE_AUTH_MODE` |
| `session_secret: str` | `""` | `LATTICE_SESSION_SECRET` |
| `session_ttl_s: float` | `12*3600` | `LATTICE_SESSION_TTL_S` |
| `init_password: str` | `""` | `LATTICE_INIT_PASSWORD` |
| `invite_ttl_s: float` | `72*3600` | `LATTICE_INVITE_TTL_S` |
| `login_max_fails: int` | `5` | `LATTICE_LOGIN_MAX_FAILS` |
| `login_window_s: float` | `900` | `LATTICE_LOGIN_WINDOW_S` |
| `login_lock_s: float` | `600` | `LATTICE_LOGIN_LOCK_S` |
| `password_min_len: int` | `10` | `LATTICE_PASSWORD_MIN_LEN` |

- `_validate`：`auth_mode ∈ {local,sso}`；数值非负；`password_min_len >= 8`；`login_max_fails >= 1`。非法 fail-closed raise。
- `create_app` 局部守卫（Settings 直接构造也覆盖）：`auth_mode=="local"` 时
  `session_secret` 必须非空且 **≥32 字节**，否则 `ValueError` 启动即拒（消息提示
  `LATTICE_SESSION_SECRET`）。不要求 `init_password` 必填（prod 建议，风险已登记）。
- local 模式 `create_app` **不构造** SSO 验签器（`service.sso=None`）——SSO JIT 关闭、
  MCP 无 SSO 不可用（D25 口径）。

## 2. 迁移 0012（双方言）

文件：`store/sqlite/migrations/docs/0012_local_accounts.sql` 与
`store/postgres/migrations/docs/0012_local_accounts.sql`（同号、语义等价）。

`users` 扩列（SQLite/PG 同）：
- `email TEXT`
- `password_hash TEXT`
- `status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('invited','active'))`
- `token_version INTEGER NOT NULL DEFAULT 0`
- `created_by TEXT`
- `CREATE UNIQUE INDEX ux_users_email ON users(email) WHERE email IS NOT NULL`

新表（列名/约束按 design §4 L299-319 原样）：
- `user_invitations(id, user_id FK CASCADE, org_id FK CASCADE NULL, role NULL, purpose
  DEFAULT 'invite' CHECK IN ('invite','reset'), token_hash UNIQUE NOT NULL, invited_by
  NOT NULL, expires_at NOT NULL, consumed_at, revoked_at, created_at DEFAULT
  CURRENT_TIMESTAMP)` + `INDEX idx_user_invitations_user(user_id, org_id)`
- `instance_setup(id INTEGER PRIMARY KEY CHECK (id=1), completed_at NOT NULL,
  admin_user_id FK users(id) NOT NULL)`

迁移水位：内置 11→12。**同步修改以下测试中的水位/自制迁移号**（全仓 grep `001[12]`/`== 11`/`[1, 2, …, 11]`）：
- `tests/test_scaf_03_migrations.py`（自制迁移 0012→0013；所有 `[12]`/`12`/flatten 列表）
- `tests/test_pg_scaff.py`（自制 0012→0013、0013/0014→0014/0015；版本表补 12）
- `tests/test_v11_schema.py`（`[2..11]`→`[2..12]`、`versions` 列表、注释）
- `tests/test_regress_m0a1_followups.py`（11→12）
- 其他 grep 命中同段更新；不得只改 3 处。

## 3. Store 协议（`store/backend.py` 新 `AccountsBackend`，并入 `StorageBackend`）

异常（`store/backend.py`）：`UsernameTakenError`、`EmailTakenError`、
`SetupCompletedError`、`LastSysadminError`、`InvitationInvalidError(reason)`（reason ∈
`invalid|expired|consumed|revoked`；`__init__(message, *, reason)`）。

方法（sqlite/postgres 同签名；带 `audit=(event_type, payload_json)` 的写方法必须与业务写同事务）：

```python
count_users() -> int
get_instance_setup() -> dict | None            # {completed_at, admin_user_id}
setup_instance(*, admin_user_id, username, display_name, email, password_hash,
               org_id, org_name, audit) -> dict   # {user, org|None}
create_user(*, user_id, username, display_name, email, password_hash, status,
            is_system_admin, created_by, audit) -> dict
create_invited_user(*, user_id, username, display_name, email, invitation_id,
                    org_id, role, token_hash, invited_by, expires_at,
                    is_system_admin, audit) -> dict  # {user, invitation}
get_user(user_id) -> dict | None               # 全列含 password_hash
get_user_by_username(username) -> dict | None  # 全列含 password_hash
get_user_auth(user_id) -> dict | None          # 扩：+ status, token_version
list_users() -> list[dict]                     # 不含 password_hash
update_user_flags(*, user_id, disabled, is_system_admin, actor, audits) -> dict
    # disabled/is_system_admin 可为 None=不改；last sysadmin → LastSysadminError；
    # 停用置 disabled_at=now 且 tv++（重新启用旧会话不复活）；幂等无变化零审计
set_user_password(*, user_id, password_hash, bump_token_version, audit) -> dict
record_login(user_id) -> None                  # last_login_at=now
list_user_orgs(user_id) -> list[dict]          # {id,name,role,status} 仅有效成员
create_invitation(*, invitation_id, user_id, org_id, role, purpose, token_hash,
                  invited_by, expires_at, revoke_pending, audit) -> dict
find_invitation_by_token_hash(token_hash) -> dict | None  # join username/display_name/email/org_name
get_invitation(invitation_id) -> dict | None
list_invitations(org_id) -> list[dict]
revoke_invitation(*, invitation_id, org_id, actor, audit) -> bool
accept_invitation(*, token_hash, password_hash, display_name, audit_event,
                  actor_label) -> dict
    # 原子：校验 pending/未过期 → consumed_at=now → 设密码/status=active/tv++ →
    # invite 且 org/role 非空则补 membership（已存在不降级）→ 审计。
    # 失败抛 InvitationInvalidError；返回 {user, invitation}
```

- 所有写方法事务形态沿各自方言现有 `audit=` 先例（sqlite `BEGIN IMMEDIATE`；
  PG `BEGIN` + 唯一冲突映射）。唯一冲突按 username/email 分别映射异常（先事务内查，
  再捕获 UNIQUE 兜底）。
- `email` 统一 `strip().lower() or None`；`username` `strip()`，不 lower（登录键精确）。
- `create_user` 与 `create_invited_user` 的 `user_id` 为调用方生成（`u_<ulid/random>`）；
  store 不生成。
- `setup_instance`：事务内 `COUNT(users)==0` 且无 setup 行，否则 `SetupCompletedError`；
  用户 active+sysadmin；org 可选（给定则同事务建组织 + org_admin membership）；
  写 `instance_setup`，审计 `instance.setup`。并发唯一冲突 → `SetupCompletedError`。
- `accept_invitation` 的 `audit_event` 由 API 传（invite→`auth.invite_accepted`，
  reset→`auth.password_reset`），actor_label 为 user_id。

## 4. 领域层 `domain/accounts.py` + `domain/auth.py`

`domain/accounts.py` 导出：
- `hash_password(password) -> str`：stdlib `hashlib.scrypt`，n=16384,r=8,p=1,dklen=32,
  16B salt；编码 `scrypt$n=16384,r=8,p=1$<b64salt>$<b64hash>`；verify 解析参数并
  `hmac.compare_digest`；畸形/超界参数 fail-closed 返回 False。
- `validate_password(password, min_len)`：返回错误码/抛 `WeakPasswordError`（API 400）。
- `issue_session_token(settings, *, user_id, token_version) -> (token, expires_at_iso)`
- `decode_session_token(settings, token) -> dict`：校验 HS256/aud=`knowledge-lattice-web`/
  `typ=session`/`exp`/`iat`/`sub`/`tv`；失败 `AuthError`。
- `LoginRateLimiter(max_fails, window_s, lock_s)`：
  `check(key) -> retry_after_s|None`、`record_failure(key)`、`reset(key)`；
  进程内线程锁，`time.monotonic()`；成功登录 reset。
- `authenticate_session(backend, settings, token) -> AuthContext`（via=`local`）：
  decode → `get_user_auth` → 不存在/disabled/status!=active/tv 不等 → 401。
- `username_email_normalize` 辅助可选。

`domain/auth.py`：
- `AuthContext.via` 增加 `"local"`。
- `authenticate` 开头：`auth_mode=="local"` 时先尝试 `authenticate_session`（失败继续）；
  `sso` 分支仅在 `auth_mode!="local"` 执行；`_authenticate_sso_claims` 入口防御：
  local 模式一律拒绝（理论上不可达）。
- `get_user_auth` 扩列后，SSO 路径不回归。

审计常量（`domain/audit_events.py` 单一登记处 + `__all__`）：
`auth.login`、`auth.login_refused`、`auth.logout`、`auth.password_changed`、
`auth.password_reset`、`auth.invite_created`、`auth.invite_accepted`、
`auth.invite_revoked`、`user.created`、`user.disabled`、`user.enabled`、
`user.sysadmin_changed`、`instance.setup`。

## 5. API（m4-2）

新文件：`api/auth.py`（`public_router` + `local_router`）、`api/users.py`（local 专属）。
`app.py`：`public_router` 恒注册；`auth_mode=="local"` 时注册 `local_router` 与 `users.router`
（sso 下这些路径 404）。`ServiceContext` 增加 `login_limiter`（进程内单例）。

错误体统一 `{"error": str, "code": str}`（AuthError 全局 handler 目前只给 error——本段
在路由内 `HTTPException(detail=...)` 或扩展 handler？**约定**：新端点错误一律
`JSONResponse({"error": msg, "code": code}, status_code=...)`，不依赖全局 handler）。

端点/响应（冻结）：

| 端点 | 状态码与响应 |
|---|---|
| `GET /api/auth/config` | `{auth_mode, setup_needed, local_login_enabled}`（sso 下 setup_needed=false） |
| `GET /api/setup/status` | `{setup_needed, completed}` |
| `POST /api/setup` | 201 `{token, expires_at, user, orgs}`；二次/并发 409 `setup_completed`；init_password 不符 403 `invalid_init_password`；弱密码 400 `weak_password` |
| `POST /api/auth/login` | 200 `{token, expires_at, user, orgs}`；401 统一 `invalid_credentials`；停用/invited 同 401；锁定 429 `login_locked` + `Retry-After` |
| `GET /api/auth/me` | `{user, orgs}` |
| `POST /api/auth/password` | `{old_password,new_password}` → `{token, expires_at}`；旧密错 401；弱 400；改后旧 token 401 |
| `POST /api/auth/logout` | 204（无服务端撤销；审计 `auth.logout` 可选） |
| `POST /api/auth/invitations/lookup` | `{token}` → `{purpose, username, display_name, email, org_id, org_name, role, expires_at}`；无效 404 `invite_invalid|invite_expired|invite_consumed|invite_revoked` |
| `POST /api/auth/invitations/accept` | `{token,password,display_name?}` → 200 登录态同 login；错误同上/400 `weak_password` |
| `GET /api/users` | `{users:[{id,username,display_name,email,status,is_system_admin,disabled_at,last_login_at,created_at,created_by}]}` |
| `POST /api/users` | 201 `{user, invitation:{id,token,expires_at}|null}`；409 `username_taken/email_taken` |
| `PATCH /api/users/{id}` | `{disabled?,is_system_admin?}` → `{user}`；404；末位 sysadmin 409 `last_sysadmin` |
| `POST /api/users/{id}/reset` | `{invitation:{id,token,expires_at}}`；404；disabled 409 `user_disabled` |
| `GET /api/orgs/{org}/invitations` | `{invitations:[{id,user_id,username,role,purpose,created_at,expires_at,consumed_at,revoked_at,status,invited_by}]}`；status=pending/consumed/revoked/expired |
| `POST /api/orgs/{org}/invitations` | `{username,role,display_name?,email?}` → 201 `{user_id, membership_added, invitation|null}`；已存在 active 用户直接 `member.add`；已存在会员 409 `member_exists`；新用户 invited+invite |
| `DELETE /api/orgs/{org}/invitations/{id}` | 204；未知/非 pending 404 `invite_invalid` |

- 权限：`/api/users*` sysadmin；`/api/orgs/{org}/invitations*` org_admin + `org_scoped`；
  local 模式 `POST /api/orgs` 的 `org_admin` 须 `status='active'`（invited 409 / 不存在 404），
  且接受 **username 或用户 ID**（先按 ID、未命中再按 username 解析；membership/审计落规范 ID，
  响应附 `org_admin_username`——与 `/api/users`、邀请面的人类可读键一致）。
- 邀请 token：32B `secrets.token_urlsafe(32)`，库只存 sha256；响应明文 token 仅创建时一次；
  TTL `invite_ttl_s`；重发 `revoke_pending=True`（旧链接失效）。
- 登录限流键 `f"{username}|{client_ip}"`；`TestClient` 下 ip 取 `request.client.host` 兜底 `"testclient"`。
- `POST /api/setup` 可选首组织 `{org_id, org_name}` 必须成对（否则 400）。
- `POST /api/orgs` 的 active 校验：local 先 `get_user(org_admin)`、未命中再
  `get_user_by_username(org_admin)`；存在且 status=='active' 且 disabled_at 为空 → 以规范 ID
  建 membership，否则 404/409。`sso` 形态仍只按用户 ID（既有语义零变化）。

MCP 边界（`mcp/server.py::_auth_and_org`）：`authenticate` 返回后若 `auth.via=="local"`
→ `ToolError("401: local session token 不能用于 MCP（D25——MCP 仍走 D18 委托/可信）")`。
REST 不受影响。

## 6. Web（m4-3，详见该段提示）

归属：`web/api.js`、`web/app.js`、`web/index.html`、`web/i18n.js`、`web/style.css`、
`web/views/login.js`（新）、`web/views/users.js`（新）、`prototype/index.html`、
`tests/test_e2e_07_shell.py`（资产/视图/键集）。
不触碰后端；API 契约以 §5 为准。

## 7. 收口（m4-4）

- `scripts/reset_admin.py`：break-glass（sqlite；`--username`、`--password-stdin`、
  `--generate`、`--create`、`--promote`；走 store `create_user`/`set_user_password`，
  不得裸 SQL）；stdout 不打印 hash。
- RUNBOOK §1.ab 实操复核；`.env.example` 已就绪（核对键名）。
- docs 回写：requirements/design 版本行（完成态、非决策变更声明）、TEST-CASES
  TC-AUTH-06~10 与 TC-UI-06/07 状态、known-gaps G-31~G-34 残留、AGENTS M4 状态、
  `_m4-plan.md` 段进度。
- 全量 gate：`LATTICE_PG_DSN=... UV_CACHE_DIR="$PWD/.uv-cache" scripts/test_gate.sh`
  （或等价双模式命令）；0 skipped；记录新基线数。

## 8. 评审检查点（lead 用）

1. `git diff --stat` 只含本段归属文件。
2. 迁移 0012 双方言列/约束/索引逐项；水位与自制迁移号全更新。
3. 默认 sso 回归：`test_auth_01~05`、`test_e2e_*`、migration 全绿。
4. local 新用例双后端；无 skip。
5. 审计 payload 无密码/token；错误消息不回显密码。
6. 响应字段/错误码与 §5 完全一致。
