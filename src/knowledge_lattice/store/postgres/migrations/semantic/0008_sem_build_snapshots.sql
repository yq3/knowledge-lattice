-- 0008 semantic build 快照附表（pg）：G-21 方案 A（m2s-5）——与 sqlite 版
-- 同构（snapshot_json 为 TEXT——与 sem_builds.stats_json 同风格，PG 侧无
-- json_valid CHECK，内容合法性由写入方〔store 事务内序列化〕保证）。

CREATE TABLE sem_build_snapshots (
  build_id      BIGINT PRIMARY KEY REFERENCES sem_builds(id) ON DELETE CASCADE,
  org_id        TEXT   NOT NULL,
  snapshot_json TEXT   NOT NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_sem_bsnap_org ON sem_build_snapshots(org_id);
