-- 0006 semantic v1（sqlite）：sem_* 六表 + sem_rel_types 白名单种子 + 触发器
-- （design §4 L510-637 DDL 原文 / §5.8 L834-847 白名单表——M2-S1 语义轨道首段）。
-- · org 作用域六表全带 org_id；sem_rel_types 为全局白名单配置表、无 org_id
--   （v0.6.1 口径——design §4 设计说明⑥）。
-- · dst_type='*' 为任意型端点（§5.8 refers_to：concept / system → 任意实体）——
--   trg_sem_rel_check 白名单校验对 '*' 放行（design L584-595 触发器原文的
--   最小扩展，语义按 §5.8 白名单表「任意」列落——与代码常量三处一致）。
-- · 附带 tasks.payload 列：semantic_sync 任务携带 {org, adapter}（tasks 表
--   0001 无 payload 列；迁移号 docs/semantic 共用单水位，语义段所需列随本迁移落）。

CREATE TABLE sem_entities (
  id            INTEGER PRIMARY KEY,
  org_id        TEXT    NOT NULL REFERENCES orgs(id) ON DELETE RESTRICT,
  type          TEXT    NOT NULL CHECK (type IN ('concept','system','scenario','template',
                         'template_field','report','report_item','table','column')),
  key           TEXT    NOT NULL,
  name          TEXT    NOT NULL,
  parent_id     INTEGER REFERENCES sem_entities(id) ON DELETE CASCADE,
  attrs_json    TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(attrs_json)),
  curated_json  TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(curated_json)),
  source        TEXT    NOT NULL CHECK (source IN ('sync','curated')),
  source_system TEXT,
  status        TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active','missing','retired')),
  sensitivity   TEXT    NOT NULL DEFAULT 'normal' CHECK (sensitivity IN ('normal','restricted')),
  synced_at     TIMESTAMP,
  curated_rev   TEXT,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (org_id, type, key)
);
CREATE INDEX idx_sem_entities_org_type ON sem_entities(org_id, type, status);
CREATE INDEX idx_sem_entities_parent   ON sem_entities(parent_id);

CREATE TABLE sem_aliases (
  id          INTEGER PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  entity_id   INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  alias       TEXT    NOT NULL,
  alias_norm  TEXT    NOT NULL,
  kind        TEXT    NOT NULL CHECK (kind IN ('name','code','manual','abbr','pinyin','sync')),
  match_mode  TEXT    NOT NULL DEFAULT 'exact' CHECK (match_mode IN ('exact','fuzzy_only','context')),
  weight      REAL    NOT NULL DEFAULT 1.0,
  UNIQUE (org_id, entity_id, alias_norm)
);
CREATE INDEX idx_sem_aliases_norm ON sem_aliases(org_id, alias_norm);

CREATE TABLE sem_relations (
  id          INTEGER PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  src_id      INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  rel_type    TEXT    NOT NULL,
  dst_id      INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  attrs_json  TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(attrs_json)),
  source      TEXT    NOT NULL CHECK (source IN ('sync','curated')),
  status      TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active','missing','retired')),
  synced_at   TIMESTAMP,
  UNIQUE (org_id, src_id, rel_type, dst_id)
);
CREATE INDEX idx_sem_rel_out ON sem_relations(org_id, src_id, rel_type, status);
CREATE INDEX idx_sem_rel_in  ON sem_relations(org_id, dst_id, rel_type, status);

-- 关系类型白名单（全局配置表——新增关系类型 = schema 变更走迁移）
CREATE TABLE sem_rel_types (
  rel_type   TEXT NOT NULL,
  src_type   TEXT NOT NULL,
  dst_type   TEXT NOT NULL,
  PRIMARY KEY (rel_type, src_type, dst_type)
);
INSERT INTO sem_rel_types(rel_type, src_type, dst_type) VALUES
  ('uses',         'scenario',      'template'),
  ('has_field',    'template',      'template_field'),
  ('backed_by',    'template',      'table'),
  ('maps_to',      'template_field','column'),
  ('has_item',     'report',        'report_item'),
  ('child_of',     'report_item',   'report_item'),
  ('derived_from', 'report_item',   'template_field'),
  ('derived_from', 'report_item',   'column'),
  ('has_column',   'table',         'column'),
  ('refers_to',    'concept',       '*'),
  ('refers_to',    'system',        '*'),
  ('related_to',   'concept',       'concept');

-- 组织一致性 + 白名单端点类型双校验（design L584-595 原文 + '*' 任意型放行）
CREATE TRIGGER trg_sem_rel_check BEFORE INSERT ON sem_relations
BEGIN
  SELECT RAISE(ABORT, 'relation endpoints must belong to the same org')
   WHERE (SELECT org_id FROM sem_entities WHERE id = NEW.src_id) <> NEW.org_id
      OR (SELECT org_id FROM sem_entities WHERE id = NEW.dst_id) <> NEW.org_id;
  SELECT RAISE(ABORT, 'rel_type/endpoint types not in whitelist')
   WHERE NOT EXISTS (
     SELECT 1 FROM sem_rel_types t
      WHERE t.rel_type = NEW.rel_type
        AND t.src_type = (SELECT type FROM sem_entities WHERE id = NEW.src_id)
        AND (t.dst_type = '*' OR
             t.dst_type = (SELECT type FROM sem_entities WHERE id = NEW.dst_id)));
END;

-- 关系行不允许原地改端点：要改就先删再插（T-S5——保证上方触发器始终生效）
CREATE TRIGGER trg_sem_rel_noupdate BEFORE UPDATE OF src_id, dst_id, rel_type, org_id ON sem_relations
BEGIN SELECT RAISE(ABORT, 'relation endpoints are immutable: delete then insert'); END;

-- 文档块 ↔ 实体（AC 自动机写入——刻意不加外键到 chunks，design §4 设计说明②）
CREATE TABLE sem_chunk_entities (
  org_id      TEXT    NOT NULL,
  chunk_rid   INTEGER NOT NULL,
  doc_id      TEXT    NOT NULL,
  version     INTEGER NOT NULL,
  entity_id   INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  hits        INTEGER NOT NULL DEFAULT 1,
  dict_rev    TEXT    NOT NULL,
  PRIMARY KEY (chunk_rid, entity_id)
);
CREATE INDEX idx_sem_ce_entity ON sem_chunk_entities(org_id, entity_id);
CREATE INDEX idx_sem_ce_doc    ON sem_chunk_entities(doc_id, version);

CREATE TABLE sem_builds (
  id          INTEGER PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  dict_rev    TEXT    NOT NULL,
  yaml_rev    TEXT,
  sync_run_id INTEGER,
  status      TEXT    NOT NULL CHECK (status IN ('building','ready','failed')),
  stats_json  TEXT    NOT NULL DEFAULT '{}',
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (org_id, dict_rev)
);

CREATE TABLE sem_sync_runs (
  id            INTEGER PRIMARY KEY,
  org_id        TEXT    NOT NULL,
  adapter       TEXT    NOT NULL,
  started_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at   TIMESTAMP,
  status        TEXT    NOT NULL CHECK (status IN ('running','succeeded','failed','aborted_guard')),
  stats_json    TEXT    NOT NULL DEFAULT '{}',
  error         TEXT
);

ALTER TABLE tasks ADD COLUMN payload TEXT;
