-- 0009 semantic 模糊索引（pg）：与 sqlite 版同构（m2s-6——M2-S3 第 3 层模糊
-- 兜底 / TC-SEM-09 构建产物；design §5.8 产物 2）。embedding 为 pgvector
-- vector 列（不锁维度——与 chunk_vectors 同款，写入侧 Embedder 校验维度）。

CREATE TABLE sem_fuzzy_terms (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  entity_id   BIGINT  NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  kind        TEXT    NOT NULL CHECK (kind IN ('name','alias','definition')),
  text_norm   TEXT    NOT NULL,
  term_len    INTEGER NOT NULL,
  pinyin      TEXT    NOT NULL DEFAULT '',
  embed_model TEXT,
  embedding   vector
);
CREATE INDEX idx_sem_fuzzy_pin ON sem_fuzzy_terms(org_id, pinyin) WHERE pinyin != '';
CREATE INDEX idx_sem_fuzzy_model ON sem_fuzzy_terms(org_id, embed_model);

CREATE TABLE sem_fuzzy_dels (
  org_id  TEXT   NOT NULL,
  del_key TEXT   NOT NULL,
  term_id BIGINT NOT NULL REFERENCES sem_fuzzy_terms(id) ON DELETE CASCADE,
  PRIMARY KEY (org_id, del_key, term_id)
);
CREATE INDEX idx_sem_fuzzy_dels_key ON sem_fuzzy_dels(org_id, del_key);
