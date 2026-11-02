-- 0007 semantic yaml（sqlite）：m2s-3——G-18 current 指锚 / G-15 关系级
-- source_system / FTS 模糊索引（C.3 search_entities 第三层升级）。
-- · sem_builds.activated_at：G-18 rev 回退重激活的 current 锚（回填
--   created_at——既有 ready 行语义不漂移）；切换/重激活路径写本列，
--   sem_current_build 按 (activated_at, id) DESC 取当前。
-- · sem_relations.source_system：G-15 关系级 missing/retired 的 per-adapter
--   作用域（§4 DDL 无此列——关系级消失流程所需，回填取 src 实体的
--   source_system；跨源边（template_center 产 backed_by→metadata 表）按
--   产出方归属，src 实体即产出方实体，语义成立）。
-- · sem_search_texts + FTS5 外容表：search_entities 第三层（LIKE 骨架升级
--   ——sqlite FTS5 / pg tsvector 双方言，评分差异按 G-6 口径登记不追平）；
--   seg_text 为分词后空格拼接文本（与 docs FTS 同 tokenizer 惯例），由
--   store 侧 refresh 方法维护（别名重建/名称 upsert/curated 别名替换后）。

ALTER TABLE sem_builds ADD COLUMN activated_at TIMESTAMP;
UPDATE sem_builds SET activated_at = created_at
 WHERE status = 'ready' AND activated_at IS NULL;

ALTER TABLE sem_relations ADD COLUMN source_system TEXT;
UPDATE sem_relations
   SET source_system = (SELECT source_system FROM sem_entities WHERE id = sem_relations.src_id)
 WHERE source_system IS NULL;
CREATE INDEX idx_sem_rel_srcsys ON sem_relations(org_id, source_system, status);

CREATE TABLE sem_search_texts (
  id        INTEGER PRIMARY KEY,
  org_id    TEXT    NOT NULL,
  entity_id INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  seg_text  TEXT    NOT NULL
);
CREATE INDEX idx_sem_search_texts_entity ON sem_search_texts(org_id, entity_id);
CREATE VIRTUAL TABLE sem_search_fts USING fts5(
  seg_text, content='sem_search_texts', content_rowid='id'
);
