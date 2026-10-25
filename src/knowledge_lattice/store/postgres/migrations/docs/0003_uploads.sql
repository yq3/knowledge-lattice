-- 0003 schema v1.2（PG）：上传凭证表——与 sqlite 0003 同一迁移号同一语义（D24/§4 PG 映射；
-- M1-3 三步凭证式，design §6.1/§6.2/§6.3）。列与 CHECK/索引完全对齐 sqlite 渲染，
-- 时间戳为 TIMESTAMP（无时区）——连接工厂 SET TIME ZONE 'UTC' 下 CURRENT_TIMESTAMP
-- 与 sqlite 的 UTC 语义对齐（M0b-1 R2 拍板）。

CREATE TABLE uploads (
  id           TEXT PRIMARY KEY,    -- upl_<ulid>（不透明凭证 id——路径/URL 一律拒绝 P0-D）
  org_id       TEXT NOT NULL REFERENCES orgs(id),
  user_id      TEXT NOT NULL REFERENCES users(id),
  service_id   TEXT,                -- 绑定服务身份（NULL=直连/无 act claim）
  filename     TEXT NOT NULL,
  size         BIGINT NOT NULL,     -- 声明大小（字节）
  sha256       TEXT NOT NULL,
  content_type TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'issued'
               CHECK (status IN ('issued','uploaded','consumed')),
  object_key   TEXT,
  doc_id       TEXT REFERENCES documents(id) ON DELETE SET NULL,
  task_id      TEXT,
  expires_at   TIMESTAMP NOT NULL,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP
);
CREATE INDEX idx_uploads_reclaim ON uploads(status, expires_at);
