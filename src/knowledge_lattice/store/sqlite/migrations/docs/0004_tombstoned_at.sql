-- 0004 schema v1.3（sqlite）：chunks.tombstoned_at——tombstone 90 天物理清理的时点基准
-- （M2.1 maintenance 任务体「tombstone 90 天物理清理」依赖，design §4 chunks 行注释
-- 「旧版本标记：保留 90 天后物理删除」；此前切换事务只打 tombstone=1 无时点记录，
-- 清理任务无从起算。）
-- ADD COLUMN 走单语句（无外键/无表重建——#33 P1-1「建新表→拷数据→删旧表」仅适用于
-- 触碰列约束/外键的改表）；存量 tombstone 行回填迁移时点（保守：从此起算 90 天窗口）。

ALTER TABLE chunks ADD COLUMN tombstoned_at TIMESTAMP;
UPDATE chunks SET tombstoned_at = CURRENT_TIMESTAMP
 WHERE tombstone = 1 AND tombstoned_at IS NULL;
CREATE INDEX idx_chunks_tombstone_purge ON chunks(tombstoned_at) WHERE tombstone = 1;
