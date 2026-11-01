-- 0010（PG）：任务队列同秒单调键——B②（m2-3 R3 Committer P3 登记收口，m2-6）：
-- tasks.id 为 uuid4 前缀串（tsk_<uuid4>）随机非单调、created_at 秒级并列——
-- 认领（claim_next_task）与清单（list_tasks）的次级排序键受 id 字典序摆布，
-- 同秒多任务（如连续投递的 reembed）认领序 ≠ 投递序。
-- 本迁移加 IDENTITY 单调列 seq（存量行按表扫描序回填序号、新行自动递增）；
-- claim/list_tasks 次级键已改用 seq（sqlite 侧对偶为 rowid，无列）。

ALTER TABLE tasks ADD COLUMN seq BIGINT GENERATED ALWAYS AS IDENTITY;
