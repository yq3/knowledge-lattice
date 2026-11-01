-- 0009 semantic 模糊索引（m2s-6——M2-S3 第 3 层模糊兜底 / TC-SEM-09 构建产物）：
-- design §5.8 产物 2「模糊索引」= sem_fuzzy_terms（名称/别名/一句话定义——
-- 向量经 Embedder provider 生成、标签随 config 钉死且入 dict_rev）+
-- 拼音辅助列（pinyin）+ 编辑距离辅助表（sem_fuzzy_dels——deletion
-- neighborhood：两词编辑距离 ≤1 ⟺ 各自 deletion 键集合相交）。
-- 构建时按 org 整替（sem_fuzzy_replace——同 dict_rev 生命周期）；
-- search_entities 拼音/向量层与 annotate fuzzy 三层共用本索引。

CREATE TABLE sem_fuzzy_terms (
  id          INTEGER PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  entity_id   INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  kind        TEXT    NOT NULL CHECK (kind IN ('name','alias','definition')),
  text_norm   TEXT    NOT NULL,          -- normalize_alias 产物
  term_len    INTEGER NOT NULL,          -- text_norm 长度（编辑距离层 ≥4 门槛）
  pinyin      TEXT    NOT NULL DEFAULT '',  -- 无声调全拼小写（name/alias；definition 空）
  embed_model TEXT,                      -- 向量标签（NULL=本条未嵌入——构建降级态）
  embedding   BLOB                      -- sqlite-vec vec_f32；NULL=无向量（拼音/编辑距离层仍可用）
);
CREATE INDEX idx_sem_fuzzy_pin ON sem_fuzzy_terms(org_id, pinyin) WHERE pinyin != '';
CREATE INDEX idx_sem_fuzzy_model ON sem_fuzzy_terms(org_id, embed_model);

CREATE TABLE sem_fuzzy_dels (
  org_id  TEXT    NOT NULL,
  del_key TEXT    NOT NULL,              -- deletion 键（原词或去一位变体的 normalize 形态）
  term_id INTEGER NOT NULL REFERENCES sem_fuzzy_terms(id) ON DELETE CASCADE,
  PRIMARY KEY (org_id, del_key, term_id)
);
CREATE INDEX idx_sem_fuzzy_dels_key ON sem_fuzzy_dels(org_id, del_key);
