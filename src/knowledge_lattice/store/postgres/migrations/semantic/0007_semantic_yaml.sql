-- 0007 semantic yaml（pg）：m2s-3——与 sqlite 0007 同号同语义（G-18 current
-- 指锚 / G-15 关系级 source_system / FTS 模糊索引——pg 形态为 tsvector
-- GENERATED + GIN，评分差异按 G-6 口径登记不追平）。

ALTER TABLE sem_builds ADD COLUMN activated_at TIMESTAMP;
UPDATE sem_builds SET activated_at = created_at
 WHERE status = 'ready' AND activated_at IS NULL;

ALTER TABLE sem_relations ADD COLUMN source_system TEXT;
UPDATE sem_relations
   SET source_system = e.source_system
  FROM sem_entities e
 WHERE e.id = sem_relations.src_id AND sem_relations.source_system IS NULL;
CREATE INDEX idx_sem_rel_srcsys ON sem_relations(org_id, source_system, status);

CREATE TABLE sem_search_texts (
  id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id    TEXT    NOT NULL,
  entity_id BIGINT NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  seg_text  TEXT    NOT NULL,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', seg_text)) STORED
);
CREATE INDEX idx_sem_search_texts_entity ON sem_search_texts(org_id, entity_id);
CREATE INDEX idx_sem_search_tsv ON sem_search_texts USING GIN (tsv);
