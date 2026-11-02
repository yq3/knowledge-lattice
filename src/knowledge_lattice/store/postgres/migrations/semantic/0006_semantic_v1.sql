-- 0006 semantic v1（PG）：与 sqlite 0006 同一迁移号同一语义（design §4 L510-637 +
-- §5.8 白名单表；§4 PG 映射——INTEGER PRIMARY KEY → BIGINT GENERATED ALWAYS AS
-- IDENTITY、json_valid CHECK → IS JSON（PG16+）、RAISE(ABORT) → plpgsql RAISE
-- EXCEPTION 错误消息逐字同源）。
-- · org 作用域六表全带 org_id；sem_rel_types 全局白名单表无 org_id（v0.6.1 口径）。
-- · dst_type='*' 任意型端点（§5.8 refers_to concept/system → 任意实体）——
--   trg_sem_rel_check 对 '*' 放行（与代码常量三处一致）。
-- · 附带 tasks.payload（semantic_sync 任务 {org, adapter}）。

CREATE TABLE sem_entities (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id        TEXT    NOT NULL REFERENCES orgs(id) ON DELETE RESTRICT,
  type          TEXT    NOT NULL CHECK (type IN ('concept','system','scenario','template',
                         'template_field','report','report_item','table','column')),
  key           TEXT    NOT NULL,
  name          TEXT    NOT NULL,
  parent_id     BIGINT  REFERENCES sem_entities(id) ON DELETE CASCADE,
  attrs_json    TEXT    NOT NULL DEFAULT '{}' CHECK (attrs_json IS JSON),
  curated_json  TEXT    NOT NULL DEFAULT '{}' CHECK (curated_json IS JSON),
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
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  entity_id   BIGINT  NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  alias       TEXT    NOT NULL,
  alias_norm  TEXT    NOT NULL,
  kind        TEXT    NOT NULL CHECK (kind IN ('name','code','manual','abbr','pinyin','sync')),
  match_mode  TEXT    NOT NULL DEFAULT 'exact' CHECK (match_mode IN ('exact','fuzzy_only','context')),
  weight      REAL    NOT NULL DEFAULT 1.0,
  UNIQUE (org_id, entity_id, alias_norm)
);
CREATE INDEX idx_sem_aliases_norm ON sem_aliases(org_id, alias_norm);

CREATE TABLE sem_relations (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  src_id      BIGINT  NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  rel_type    TEXT    NOT NULL,
  dst_id      BIGINT  NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  attrs_json  TEXT    NOT NULL DEFAULT '{}' CHECK (attrs_json IS JSON),
  source      TEXT    NOT NULL CHECK (source IN ('sync','curated')),
  status      TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active','missing','retired')),
  synced_at   TIMESTAMP,
  UNIQUE (org_id, src_id, rel_type, dst_id)
);
CREATE INDEX idx_sem_rel_out ON sem_relations(org_id, src_id, rel_type, status);
CREATE INDEX idx_sem_rel_in  ON sem_relations(org_id, dst_id, rel_type, status);

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

CREATE FUNCTION trg_sem_rel_check_fn() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT org_id FROM sem_entities WHERE id = NEW.src_id) <> NEW.org_id
     OR (SELECT org_id FROM sem_entities WHERE id = NEW.dst_id) <> NEW.org_id THEN
    RAISE EXCEPTION 'relation endpoints must belong to the same org';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM sem_rel_types t
     WHERE t.rel_type = NEW.rel_type
       AND t.src_type = (SELECT type FROM sem_entities WHERE id = NEW.src_id)
       AND (t.dst_type = '*' OR
            t.dst_type = (SELECT type FROM sem_entities WHERE id = NEW.dst_id))
  ) THEN
    RAISE EXCEPTION 'rel_type/endpoint types not in whitelist';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER trg_sem_rel_check BEFORE INSERT ON sem_relations
  FOR EACH ROW EXECUTE FUNCTION trg_sem_rel_check_fn();

CREATE FUNCTION trg_sem_rel_noupdate_fn() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'relation endpoints are immutable: delete then insert';
  RETURN NEW;
END
$$;
CREATE TRIGGER trg_sem_rel_noupdate BEFORE UPDATE OF src_id, dst_id, rel_type, org_id
  ON sem_relations
  FOR EACH ROW EXECUTE FUNCTION trg_sem_rel_noupdate_fn();

CREATE TABLE sem_chunk_entities (
  org_id      TEXT    NOT NULL,
  chunk_rid   BIGINT  NOT NULL,
  doc_id      TEXT    NOT NULL,
  version     INTEGER NOT NULL,
  entity_id   BIGINT  NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  hits        INTEGER NOT NULL DEFAULT 1,
  dict_rev    TEXT    NOT NULL,
  PRIMARY KEY (chunk_rid, entity_id)
);
CREATE INDEX idx_sem_ce_entity ON sem_chunk_entities(org_id, entity_id);
CREATE INDEX idx_sem_ce_doc    ON sem_chunk_entities(doc_id, version);

CREATE TABLE sem_builds (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  dict_rev    TEXT    NOT NULL,
  yaml_rev    TEXT,
  sync_run_id BIGINT,
  status      TEXT    NOT NULL CHECK (status IN ('building','ready','failed')),
  stats_json  TEXT    NOT NULL DEFAULT '{}',
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (org_id, dict_rev)
);

CREATE TABLE sem_sync_runs (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id        TEXT    NOT NULL,
  adapter       TEXT    NOT NULL,
  started_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at   TIMESTAMP,
  status        TEXT    NOT NULL CHECK (status IN ('running','succeeded','failed','aborted_guard')),
  stats_json    TEXT    NOT NULL DEFAULT '{}',
  error         TEXT
);

ALTER TABLE tasks ADD COLUMN payload TEXT;
