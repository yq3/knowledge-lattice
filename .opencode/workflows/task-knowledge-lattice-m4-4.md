---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-knowledge-lattice-m4-4
target: /Users/youqi/develop/knowledge-lattice
coderTaskId: null
testerTaskId: null
committerTaskId: null
status: done
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: PASS
testedSha: null
reviewedSha: null
# 注意：本轮为**工作树未提交**交付（用户未授权 commit/push）——testedSha/reviewedSha 无 commit 可指，
# 一律 null；门禁与评审证据绑定当前工作树（分支 develop_opencode，HEAD=b73366d + 未提交改动）。
filesChanged:
  - .opencode/workflows/_m4-impl-contract.md
  - .opencode/workflows/_m4-plan.md
  - .opencode/workflows/task-knowledge-lattice-m4-4.md
  - AGENTS.md
  - RUNBOOK.md
  - docs/requirements.md
  - docs/design.md
  - docs/TEST-CASES.md
  - docs/known-gaps.md
  - scripts/reset_admin.py
  - tests/test_reset_admin_m4.py
  - src/knowledge_lattice/config.py
  - src/knowledge_lattice/domain/accounts.py
  - src/knowledge_lattice/domain/auth.py
  - src/knowledge_lattice/domain/audit_events.py
  - src/knowledge_lattice/api/auth.py
  - src/knowledge_lattice/api/users.py
  - src/knowledge_lattice/api/admin.py
  - src/knowledge_lattice/app.py
  - src/knowledge_lattice/mcp/server.py
  - src/knowledge_lattice/store/backend.py
  - src/knowledge_lattice/store/sqlite/backend.py
  - src/knowledge_lattice/store/postgres/backend.py
  - src/knowledge_lattice/store/sqlite/migrations/docs/0012_local_accounts.sql
  - src/knowledge_lattice/store/postgres/migrations/docs/0012_local_accounts.sql
  - src/knowledge_lattice/web/app.js
  - src/knowledge_lattice/web/api.js
  - src/knowledge_lattice/web/i18n.js
  - src/knowledge_lattice/web/index.html
  - src/knowledge_lattice/web/style.css
  - src/knowledge_lattice/web/views/login.js
  - src/knowledge_lattice/web/views/users.js
  - prototype/index.html
  - tests/conftest.py
  - tests/test_auth_06_local_setup_login.py
  - tests/test_auth_07_invitations.py
  - tests/test_auth_08_users_admin.py
  - tests/test_auth_domain_m4.py
  - tests/test_auth_store_m4.py
  - tests/test_backend_contract.py
  - tests/test_e2e_07_shell.py
  - tests/test_pg_backend.py
  - tests/test_pg_scaff.py
  - tests/test_regress_m0a1_followups.py
  - tests/test_scaf_03_migrations.py
  - tests/test_v11_schema.py
endReason: null
createdAt: 2026-11-20T21:56:45+0800
updatedAt: 2026-11-20T22:58:00+0800
---

# task-knowledge-lattice-m4-4: M4 收口段（break-glass CLI + 文档完成态回写 + 全量门禁）

## 任务原文

M4 第 4 段收口（`.opencode/workflows/_m4-plan.md` row4）：

- **A** `scripts/reset_admin.py`：break-glass（纯 store 层；`--username`/`--password-stdin`/`--generate`/交互式；`--create`/`--promote`；审计不含密码/hash；退出码 0/2/1）+ `tests/test_reset_admin_m4.py`。
- **B** 文档回写：requirements/design v0.10.1、TEST-CASES v1.11.0、known-gaps G-31~G-34 状态注记、RUNBOOK §1.ab 实操、AGENTS M4 状态、`_m4-plan` 完成态、本检查点。
- **C** 全量门禁：M4 定向用例 + `scripts/test_gate.sh`（双后端双模式、0 skipped），失败则修本段范围内代码/测试并复跑。
- **边界**：**不 commit / 不 push**（用户未授权；工作树保留全部改动）。

## 一、四段范围（M4 全量，m4-1~m4-4）

| 段 | 交付内容 | 状态 |
|---|---|---|
| m4-1 账号底座 | 迁移 0012 双方言（`users` 扩列 + `user_invitations` + `instance_setup`）；`AccountsBackend` 协议与双方言；`domain/accounts.py`（scrypt/session JWT/限流/tv/setup 守卫）；审计常量 | ✅ 2026-11-20 |
| m4-2 认证 API | `/api/setup`、`/api/auth/*`（config/status/login/me/password/logout/invitations lookup·accept）、`/api/users`、`/api/orgs/{org}/invitations`；错误码/审计/限流；app 装配与 prod 守卫；MCP 拒绝 `via=local` | ✅ 2026-11-20 |
| m4-3 Web | boot 门（auth_mode/setup_needed）+ Setup/登录/邀请接受三屏；用户/邀请管理页；组织切换；i18n zh/en；prototype 登录/邀请屏更新；壳用例更新 | ✅ 2026-11-20 |
| m4-4 收口 | `scripts/reset_admin.py` break-glass + 9 用例；RUNBOOK §1.ab 实操命令；docs 版本/完成态回写；全量 gate | ✅ 2026-11-20 |

## 二、本段（m4-4）文件清单

**新增**

- `scripts/reset_admin.py`——break-glass CLI（纯 store：`Settings` + `store.factory.build_backend` + `create_user`/`get_user_by_username`/`set_user_password`/`update_user_flags`；无裸 SQL）。
  - 用法：`--username` 必填；`--data-dir` 可选（缺省 `LATTICE_DATA_DIR`/`data`，目录不存在自动创建）；密码三选一 `--password-stdin`（推荐）/`--generate`（24 字符 `secrets.token_urlsafe(18)`，只打印一次）/无参数交互式 `getpass`（非 TTY 报错提示 stdin）；`--create`（不存在则建 active+sysadmin，否则退出 2 并提示）；`--promote`（授 sysadmin + 清 `disabled_at`；默认不动）；无 `--no-password`。
  - 审计：已有用户 `auth.password_reset`；`--promote` 按实际变化补 `user.enabled`/`user.sysadmin_changed`；新建 `user.created`——payload 仅 user_id/username/actor；密码/hash 不进 stdout/审计/错误消息。
  - 退出码：0 成功；2 用户不存在未 `--create` / 密码不合规 / 参数错误；1 配置或数据库错误。
  - 限制：`store.factory.build_backend` 当前恒 sqlite（与 app/worker 一致）；设置 `LATTICE_PG_DSN` 时工厂只告警并仍用 sqlite——PG 部署待 factory 接线（已在 RUNBOOK/脚本 docstring 写清）。
- `tests/test_reset_admin_m4.py`——9 用例（subprocess + 独立 `LATTICE_DATA_DIR`）：不存在未 `--create`、`--create --password-stdin`、`--promote`（tv++/sysadmin/清 disabled/审计）、`--generate` 只打印一次、弱口令建号/重置两路、非 TTY 提示、缺失多层目录自建、`--data-dir` 覆盖 env。
- `.opencode/workflows/task-knowledge-lattice-m4-4.md`（本文件）。

**文档回写**

- `docs/requirements.md` v0.10.1（非决策变更）：版本行/日期链；§8 M4 行完成态；§9 待决-2 维持未决（M4 不改变该状态）；D25 正文未动。
- `docs/design.md` v0.10.1（非决策变更）：版本行/日期链；§8 M4 行完成态；§5.5/§6.2 实现口径注记（`GET /api/users` 管理投影含 `disabled_at`/`created_by`；local 会话仅 Web/REST、MCP 拒绝；`POST /api/orgs` local `org_admin` 须 active；`users.last_login_at` 由 0012 补齐）。
- `docs/TEST-CASES.md` v1.11.0：TC-AUTH-06~10 摘「计划」→ 实现登记（tests/test_auth_06/07/08 + store/domain m4，双后端）；TC-UI-06·07 →「实现，待用户走查」；§六 M4 行完成态+门禁数；依据 requirements/design v0.10.1。
- `docs/known-gaps.md`：G-31~G-34 各补 m4 实现状态/残留，**不划销**。
- `RUNBOOK.md` §1.ab：首启 Web 流程、邀请链接复制（`#invite=<token>`）、break-glass 五种用法/密码来源/退出码/审计/sqlite 限制、gate 命令。
- `AGENTS.md`：M4 状态行改实现完成（工作树未提交）+ 模块/测试/门禁数；保留 sso 默认零变化口径。
- `.opencode/workflows/_m4-plan.md`：状态改实现完成（待提交）、段表四行完成态、实测 gate/用例数/残留、变更记录。

## 三、门禁结果（实测）

定向：

```text
LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice \
UV_CACHE_DIR="$PWD/.uv-cache" uv run --no-sync pytest \
  tests/test_reset_admin_m4.py tests/test_auth_06_local_setup_login.py \
  tests/test_auth_07_invitations.py tests/test_auth_08_users_admin.py \
  tests/test_e2e_07_shell.py -q
→ 54 passed in 15.75s（pg 臂 20 条实跑）
```

全量：

```text
docker start lattice-pg
export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
UV_CACHE_DIR="$PWD/.uv-cache" scripts/test_gate.sh
→ [pytest]   2088 passed, 1 deselected in 287.03s
→ [pytest-O] 2088 passed, 1 deselected, 1 warning in 281.52s
→ GATE PASS: sqlite+pg 双后端、双模式全绿，0 skipped（pg 臂 775：738 参数化 + 37 PG 专用）
```

- 基线 1921+1 → **2088+1**（+167）；M4 新增 **166** 用例（store 42/domain 73/API 42/CLI 9；store/API 双后端参数化，domain 以纯单测为主含 10 条 pg 臂）+ `test_backend_contract.py` 协议面 1 用例。
- 1 deselected = `-m "not manual"` 排除的 TC-UI 手动走查（沿既有门禁口径）；0 failed、0 skipped。

## 四、残留 / 偏差

- **TC-UI-06·07 待用户走查**（手动组不进门禁）——M4 的唯一未勾验收项；其余 TC-AUTH-06~10 已转实现登记。
- **工作树未 commit / 未 push**（用户未授权）——`testedSha`/`reviewedSha` 均 null，门禁/评审证据绑定工作树（HEAD=b73366d + 未提交改动）。
- **break-glass CLI 仅 sqlite**（`store.factory` 当前恒 sqlite；PG 接线属部署期）——已在脚本 docstring/RUNBOOK 写清；不影响双后端测试门禁。
- **真实 IdP / G-33**：sso 形态真实 IdP 联调仍挂部署期；local 无 SSO 时 MCP 不可用未改变；G-31~G-34 均不划销。
- 无决策变更：D25/FR-9 与冻结结论未动；`auth_mode` 默认仍 `sso`，TC-AUTH-01~05 回归全绿。

## 五、评审修正（2026-11-20 晚——工作树未提交）

- **发现**（用户实测账号 `y00668221`）：sysadmin 建组织填 username → 404「用户不存在」。根因：`POST /api/orgs` 沿 sso 语义只按 `users.id` 解析 `org_admin`；local 用户 ID 为不透明 `u_<hex>`，而 `/api/users`/邀请面的人类可读键是 username。附：local 的 409（invited/disabled）在 Web 被误报成「组织已存在」。
- **修正**：`api/admin.py` local 分支「ID → username」解析（先 ID、未命中再 username；membership/审计落规范 ID；响应附 `org_admin_username`；404 文案 local 化）；`web/views/orgs.js` local 占位/脚注/404/409 未激活提示；`web/i18n.js` +4 键/语言；契约/design/TEST-CASES 注记。
- **测试**：`tests/test_auth_08_users_admin.py::test_create_org_accepts_username_in_local_mode`（username 201 + membership + 审计落 ID + invited 409 + ghost 404 零残留）；双后端参数化（+2）。
- **门禁**：定向 `test_auth_06/07/08 + test_orgs_admin + test_e2e_07_shell` = **58 passed**（pg 实跑）；全量 gate **2090+1**（pg 臂 **776**：739 参数化 + 37）常规/`-O` 双模式 0 skipped；直播服务重启后实测 404 文案与零残留。
- **结论**：`reviewVerdict=PASS`；仍不 commit/push（用户未授权）。
