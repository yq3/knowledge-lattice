-- 0002 schema v1.1 (PG)：三项拍板落库的 PostgreSQL 等价（D24/§4 PG 映射——
-- 与 sqlite 0002 同一迁移号同一语义；依据 benchmarks/report-m0b-2.md §2.5/§3.4/§3.5）。
--   ① 删 chunks.dims_json（JSONB 列）：visible_docs CTE 唯一路径（+ MATERIALIZED
--      ——PG 计划器内联病理一词修复，报告 §2.3）；
--   ② 删 chunks.embedding（vector 列）、建 chunk_vectors PK(rid, embed_model)：
--      存量向量 INSERT..SELECT 搬运；rid 外键 ON DELETE CASCADE；
--   ③ chunks.embed_model 保留为摄取/重嵌入状态标签（向量谓词迁 cv JOIN）。
-- 蓝绿 runbook：RUNBOOK.md（完整重嵌入流程与管理面入口 M2）。

CREATE TABLE chunk_vectors (
  rid         BIGINT NOT NULL REFERENCES chunks(rid) ON DELETE CASCADE,
  embed_model TEXT   NOT NULL,
  embedding   vector NOT NULL,          -- pgvector（G-6：精确扫描起步；halfvec/索引化随 M1）
  PRIMARY KEY (rid, embed_model)        -- 蓝绿并存物理前提（PK(rid) 即 IntegrityError）
);

-- 存量搬运：与 sqlite 同款双守卫——embedding 非空而 embed_model NULL 的行属
-- 非法孤立态（有向量无标签），迁移中显式丢弃、不进 chunk_vectors。
INSERT INTO chunk_vectors(rid, embed_model, embedding)
  SELECT rid, embed_model, embedding FROM chunks
  WHERE embedding IS NOT NULL AND embed_model IS NOT NULL;

DROP INDEX idx_chunks_vec_pending;          -- PG 随列自动清理；显式删保持双方言语句序一致
ALTER TABLE chunks DROP COLUMN dims_json;
ALTER TABLE chunks DROP COLUMN embedding;
-- 同 sqlite：mark_embedding_batch 走 doc_id 前缀；pending_embeddings(label) 为
-- embed_model 等值 + NOT EXISTS（不走本索引，量级后再评估）
CREATE INDEX idx_chunks_vec_pending ON chunks(doc_id, embed_model) WHERE tombstone = 0;
