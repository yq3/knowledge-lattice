-- 0012 local 账号底座（D25 / m4-1——LATTICE_AUTH_MODE=local 的内置账号，design §4）：
--   · users 扩列 email/password_hash/status/token_version/created_by/last_login_at
--     + 部分唯一索引 ux_users_email（WHERE email IS NOT NULL——NULL 可共存；
--     email 只是可选联系/找回辅助，不作登录键）；
--   · 新表 user_invitations（邀请/重置 token：库内只存 sha256、单次、可撤销/重发，
--     D25 无 Redis 的载体）；
--   · 新表 instance_setup（首启单例 id=1——防并发 setup 的库级互斥点，与
--     COUNT(users)==0 同事务判定）。
-- 语义要点：
--   · status 只表达 invited/active；停用继续用既有 disabled_at（不引第二套停用语义）；
--   · token_version 为本地会话撤销版本（改密/重置/停用 tv++，旧 session 即失效）；
--   · last_login_at 是 design §4 users DDL 列（0001 实装遗漏——本迁移补齐，
--     record_login 依赖；契约 §2 的列清单未列，按「design 为准」补入并上报）；
--   · purpose=invite 时 role 由调用方保证（member/org_admin；reset 可空——
--     本表不加角色 CHECK，防止与既有 role 枚举演进耦合）。
-- 双方言同号等价：store/postgres/migrations/docs/0012_local_accounts.sql。
ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN password_hash TEXT;
ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
  CHECK (status IN ('invited','active'));
ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN created_by TEXT;
ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP;
CREATE UNIQUE INDEX ux_users_email ON users(email) WHERE email IS NOT NULL;

CREATE TABLE user_invitations (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_id      TEXT REFERENCES orgs(id) ON DELETE CASCADE,
  role        TEXT,                         -- invite 必填（member/org_admin）；reset 可空
  purpose     TEXT NOT NULL DEFAULT 'invite' CHECK (purpose IN ('invite','reset')),
  token_hash  TEXT NOT NULL UNIQUE,         -- 只存 sha256（明文 token 永不落库）
  invited_by  TEXT NOT NULL,                -- 操作者 user_id（不设 FK：操作者停用/离职不连带删邀请）
  expires_at  TIMESTAMP NOT NULL,
  consumed_at TIMESTAMP,
  revoked_at  TIMESTAMP,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_user_invitations_user ON user_invitations(user_id, org_id);

CREATE TABLE instance_setup (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  completed_at  TIMESTAMP NOT NULL,
  admin_user_id TEXT NOT NULL REFERENCES users(id)
);
