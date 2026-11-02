-- 0004 schema v1.3（PG）：chunks.tombstoned_at——与 sqlite 0004 同一迁移号同一语义
-- （D24/§4 PG 映射；M2.1 maintenance「tombstone 90 天物理清理」的时点基准）。
-- ADD COLUMN 无外键牵涉（原生约束即时校验，无需窗口性关外键）；存量回填保守起算。

ALTER TABLE chunks ADD COLUMN tombstoned_at TIMESTAMP;
UPDATE chunks SET tombstoned_at = CURRENT_TIMESTAMP
 WHERE tombstone = 1 AND tombstoned_at IS NULL;
CREATE INDEX idx_chunks_tombstone_purge ON chunks(tombstoned_at) WHERE tombstone = 1;
