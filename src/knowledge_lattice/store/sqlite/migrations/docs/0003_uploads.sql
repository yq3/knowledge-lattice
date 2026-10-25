-- 0003 schema v1.2（M1-3）：上传凭证表——三步凭证式落库（design §6.1 upload 契约 /
-- §6.2 POST /api/uploads + PUT /api/uploads/{id} / §6.3 agent 侧时序；#33 P1-3）。
--   · 凭证记录绑定 sub+org+服务身份三要素（T11：跨组织/跨身份无效）；
--   · status：issued（签发未 PUT）→ uploaded（字节就位）→ consumed（摄取成功入队
--     ——v1.4 口径「用掉」；失败 PUT / 校验失败不推进、可重传）；
--   · expires_at：UTC（CURRENT_TIMESTAMP 同格式）——过期即拒、未消费凭证由
--     maintenance 清理任务回收（design §3）；
--   · doc_id/task_id：消费后回填——凭证与文档/任务关联可追溯（M1-3 A6）。

CREATE TABLE uploads (
  id           TEXT PRIMARY KEY,    -- upl_<ulid>（不透明凭证 id——路径/URL 一律拒绝 P0-D）
  org_id       TEXT NOT NULL REFERENCES orgs(id),   -- 绑定 org（三要素之一）
  user_id      TEXT NOT NULL REFERENCES users(id),  -- 绑定 sub（三要素之一）
  service_id   TEXT,                -- 绑定服务身份（三要素之一；NULL=直连/无 act claim）
  filename     TEXT NOT NULL,
  size         INTEGER NOT NULL,    -- 声明大小（字节）——PUT 超声明 413 不静默截断（附录 A-13）
  sha256       TEXT NOT NULL,       -- 声明哈希（hex）——PUT 与消费双校验（TOCTOU 防线）
  content_type TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'issued'
               CHECK (status IN ('issued','uploaded','consumed')),
  object_key   TEXT,                -- PUT 成功后的对象键（objects/ 下相对路径——服务端生成）
  doc_id       TEXT REFERENCES documents(id) ON DELETE SET NULL,  -- 消费后关联（追溯）
  task_id      TEXT,                -- 消费后关联任务（追溯）
  expires_at   TIMESTAMP NOT NULL,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP
);
CREATE INDEX idx_uploads_reclaim ON uploads(status, expires_at);  -- 清理任务扫描面（未消费 + 过期）
