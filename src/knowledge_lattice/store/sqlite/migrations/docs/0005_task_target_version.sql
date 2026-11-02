-- 0005 schema v1.4（sqlite）：tasks.target_version——任务的目标文档版本关联
-- （M2.1 R2 / 边界裁定 B(a)：ingest 任务创建时写入 v1/vN；取消与崩溃耗尽清扫按
-- 该版本落 pending failed，根治「按文档当前 pending 落失败」误杀新版本上传
-- 〔Committer R1 P2-3〕与耗尽任务文档侧收尾〔P2-2〕。maintenance 等无版本任务
-- NULL——取消时不触碰文档。）
-- ADD COLUMN 走单语句（无外键牵涉，不触碰表约束——#33 P1-1 重建流程仅适用于
-- 改约束场景）；存量行 NULL = 按旧口径回退（取消/清扫经 _effective_version 兜底）。

ALTER TABLE tasks ADD COLUMN target_version INTEGER;
