-- 0005 schema v1.4（PG）：tasks.target_version——与 sqlite 0005 同一迁移号同一语义
-- （M2.1 R2 / 边界裁定 B(a)：取消与崩溃耗尽清扫按任务目标版本落失败，
-- Committer R1 P2-2/P2-3 根治；存量行 NULL 走旧口径回退）。

ALTER TABLE tasks ADD COLUMN target_version INTEGER;
