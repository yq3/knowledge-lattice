-- 0002 schema v1.1（M0b-3 三项拍板落库——2026-10-24 用户确认"按建议执行"，
-- 依据 benchmarks/report-m0b-2.md §2.5/§2.6/§3.4/§3.5）：
--   ① 删 chunks.dims_json：ACL 计算选定 visible_docs CTE 唯一路径（按文档、
--      document_dimensions 规范化真相源），json_each 按块模板随渲染器一并删除；
--      "维度变更刷投影"的一致性维护点整体消除（design §4 取舍注）。
--   ② 删 chunks.embedding、建分表 chunk_vectors(rid, embed_model, embedding)
--      PK(rid, embed_model)：蓝绿并存物理要求键含 embed_model（PK(rid) 新标签
--      写入即 IntegrityError——报告 §3.4 依据④）；存量向量 INSERT..SELECT 搬运
--      （空库=零行搬运，同跑通）；rid 外键 ON DELETE CASCADE（块删/版本切换
--      清理联动）。
--   ③ chunks.embed_model 保留，语义收窄为摄取/重嵌入状态标签（批次钉标签→
--      回写→断点续跑机制：mark_embedding_batch / pending_embeddings /
--      write_embeddings——向量查询谓词迁 chunk_vectors，检索侧不再读该列）。
-- 蓝绿 runbook：RUNBOOK.md（引用报告 §3.5/§3.3——完整重嵌入流程与管理面入口 M2）。

CREATE TABLE chunk_vectors (            -- 分表（拍板 2）：向量载荷集中一张表，chunks 窄表整体留驻页缓存
  rid         INTEGER NOT NULL REFERENCES chunks(rid) ON DELETE CASCADE,  -- 块删→级联清
  embed_model TEXT    NOT NULL,         -- 模型标签 model:dim（蓝绿新旧标签并存）
  embedding   BLOB    NOT NULL,         -- vec_f32 小端 float32 连续存储（store/sqlite/vec.py）
  PRIMARY KEY (rid, embed_model)        -- 蓝绿物理前提（报告 §3.4 依据④）
);

-- 存量搬运：v1 库已回写向量迁入分表（钉标签未回写的行不搬运——标签留在 chunks
-- 供断点续跑清点）；`embedding IS NOT NULL AND embed_model IS NOT NULL` 双守卫：
-- 写路径恒成对写入，**embedding 非空而 embed_model NULL 的行属非法孤立态**
-- （有向量无标签——无从归属模型），迁移中**显式丢弃**、不进 chunk_vectors
-- （验收 #1 计数口径"原 embedding 非空行数"按合法成对行计——test_v11_schema
-- 孤立行丢弃断言在案）。
INSERT INTO chunk_vectors(rid, embed_model, embedding)
  SELECT rid, embed_model, embedding FROM chunks
  WHERE embedding IS NOT NULL AND embed_model IS NOT NULL;

-- 删列前置：部分索引 idx_chunks_vec_pending 谓词引用 embedding（SQLite 拒绝
-- DROP 被索引引用的列——先删后重建谓词不含向量列的等价索引）
DROP INDEX idx_chunks_vec_pending;
ALTER TABLE chunks DROP COLUMN dims_json;    -- 拍板 1：投影删除（真相源 document_dimensions）
ALTER TABLE chunks DROP COLUMN embedding;    -- 拍板 2：载荷迁分表（宽行问题根源——报告 §3.2 sqlite 2.0× 拖慢）

-- 待嵌清点替代索引：原部分索引（doc_id WHERE embedding IS NULL AND tombstone=0）
-- 随列删除失效。真实查询面：mark_embedding_batch(doc_id, version, label) 走
-- (doc_id, embed_model) 的 doc_id 前缀 + tombstone 过滤；pending_embeddings(label)
-- 为 embed_model 等值 + NOT EXISTS chunk_vectors（不走本索引——label 清点为低频
-- 断点续跑路径，当前数据量无需为其单建 (embed_model) 索引，M1 量级后再评估）
CREATE INDEX idx_chunks_vec_pending ON chunks(doc_id, embed_model) WHERE tombstone = 0;
