-- 0013 agent 长寿命凭据（PG，D26 / issue #34——与 sqlite 同号语义等价，D24 双方言各一份）：
--   · 新表 agent_keys：org+user 绑定的 agent 长期凭据（key = lka_ + 32B 随机串，
--     明文只在创建响应返回一次）——库内**只存 sha256 摘要 token_hash + 展示前缀
--     prefix**，明文永不落库（与 0012 邀请 token 同口径）；
--   · token_hash 全库唯一（鉴权按摘要精确定位；撞库重新签发，不静默顶替）；
--   · created_by/revoked_by 为操作者 user_id，**不设 FK**（操作者停用/离职不连带
--     删 key——理由同 0012 invited_by「操作者停用/离职不连带删」）；
--   · expires_at 为 NULL = 永不过期（当前恒 NULL、字段预留未来过期/轮转；
--     判定归调用方，store 只存）；
--   · revoked_at 非空 = 软撤销（撤销即时生效；行保留供审计追溯，列表含撤销行）；
--   · idx_agent_keys_org 服务组织列表/管理面（org, revoked_at），
--     idx_agent_keys_user 服务按用户的清理/对账。
CREATE TABLE agent_keys (
  id           TEXT PRIMARY KEY,
  org_id       TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  label        TEXT NOT NULL,
  token_hash   TEXT NOT NULL UNIQUE,
  prefix       TEXT NOT NULL,
  created_by   TEXT NOT NULL,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_used_at TIMESTAMP,
  revoked_at   TIMESTAMP,
  revoked_by   TEXT,
  expires_at   TIMESTAMP
);
CREATE INDEX idx_agent_keys_org ON agent_keys(org_id, revoked_at);
CREATE INDEX idx_agent_keys_user ON agent_keys(user_id);
