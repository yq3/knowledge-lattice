-- 0010（sqlite）：任务队列同秒单调键——B②（m2-3 R3 Committer P3 登记：
-- 任务 id 为 uuid4 随机非单调，created_at 秒级并列下认领/清单次级序受字典序
-- 摆布；reembed 执行体认领序=投递序的需求〔m2-6〕使其收口）。
-- sqlite **无需加列**：rowid 即插入序（天然单调）——claim/list_tasks 次级排序
-- 键已改用 rowid。本文件是与 pg 0010（tasks.seq IDENTITY 列）对偶的占位迁移，
-- 保持「同一迁移号双方言各一份」纪律（D24）；SELECT 1 为合法 no-op。

SELECT 1;
