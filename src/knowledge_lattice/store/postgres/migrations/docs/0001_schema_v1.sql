-- 0001 schema v1 (PG)：design §4 文档侧全量 DDL——SQLite 渲染的 PostgreSQL 等价
-- （D24 / §4 PG 映射逐项，M0b-1 spike）。
-- 范围外（另行落库）：
--   · sem_* 语义表——M2-S1 经 store/postgres/migrations/semantic/ 落库（§3 边界规则 3）；
--   · audit_events 按月分区表 + append-only 触发器——连接工厂滚动创建
--     （§4 PG 映射「审计月库 → 按月分区表」；sqlite 侧属月库 audit_YYYYMM.db 同不在此）；
--   · PG 无连接级 PRAGMA——外键原生常开（§4 PG 映射「PRAGMA foreign_keys=ON →
--     原生外键约束」），无需触发器外的开关纪律。

-- ============ 组织与知识库（D7/D15：多组织 + 多知识库） ============
CREATE TABLE orgs (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE datasets (             -- 知识库：组织内的业务分组/管理单元，不承担权限（D15）
  id          TEXT PRIMARY KEY,
  org_id      TEXT NOT NULL REFERENCES orgs(id),
  name        TEXT NOT NULL,        -- VAT 实务库 / 费用制度库
  description TEXT,
  created_by  TEXT,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(org_id, name)
);

CREATE TABLE dimensions (            -- 维度定义（配置页 CRUD 对象，D9；生命周期与过滤彻底解耦——#34 必修 1 方案 A）
  id            TEXT PRIMARY KEY,    -- ULID
  org_id        TEXT NOT NULL REFERENCES orgs(id),
  key           TEXT NOT NULL,       -- region / tax_type
  name          TEXT NOT NULL,       -- 作业区域 / 税种
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
  required      INTEGER NOT NULL DEFAULT 1,  -- 仅控制上传校验；INTEGER 0/1 与 sqlite 同形
  enabled       INTEGER NOT NULL DEFAULT 1,  -- 仅控制上传页展示/选值；不影响过滤
  grant_source  TEXT NOT NULL DEFAULT 'local',  -- 授权真值源：local | sync:<system>（D16）
  value_source  TEXT NOT NULL DEFAULT 'local',  -- 取值枚举是否来自企业主数据
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP,
  UNIQUE(org_id, key)
);

CREATE TABLE dimension_values (      -- 维度取值枚举（value 即稳定编码——企业主数据码，label 可改不影响引用）
  id           TEXT PRIMARY KEY,
  dimension_id TEXT NOT NULL REFERENCES dimensions(id) ON DELETE RESTRICT,  -- P0-C：禁止级联绕过权限事件
  value        TEXT NOT NULL,        -- CN / OVERSEAS / VAT / CIT
  label        TEXT NOT NULL,        -- 中国区 / 海外区
  status       TEXT NOT NULL DEFAULT 'active',   -- active / disabled（软停用=收紧，D19）
  sort_order   INTEGER NOT NULL DEFAULT 0,
  UNIQUE(dimension_id, value)
);
-- 取值字面量不可变（P0-C）：RAISE(ABORT) → plpgsql RAISE EXCEPTION（§4 PG 映射）
CREATE FUNCTION trg_dimval_immutable_fn() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'dimension value is immutable; create a new value and migrate';
  RETURN NEW;
END
$$;
CREATE TRIGGER trg_dimval_immutable BEFORE UPDATE OF value, dimension_id ON dimension_values
  FOR EACH ROW EXECUTE FUNCTION trg_dimval_immutable_fn();

-- ============ 用户与组织归属（D7：全局账号 + 多组织成员关系） ============
CREATE TABLE users (                -- 全局账号（跨组织唯一）
  id            TEXT PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  display_name  TEXT,
  token_hash    TEXT,               -- 静态 token（sha256），仅开发/测试与 CI（D18）
  is_system_admin INTEGER NOT NULL DEFAULT 0,
  disabled_at   TIMESTAMP,          -- 用户软删（离职）——物理删除被 documents.owner 外键挡住（#33 P1-1）
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_org_memberships ( -- 用户 × 组织 多对多，角色按组织独立（D7）
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_id     TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  role       TEXT NOT NULL DEFAULT 'member',   -- org_admin | member
  expires_at TIMESTAMP,                        -- 临时成员关系（P1-7，与授权行 expires_at 同语义）
  PRIMARY KEY (user_id, org_id)
);
-- 续期禁令（T2/T23）：已过期成员关系不得原地续期
CREATE FUNCTION trg_membership_no_extend_fn() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'expired membership: delete then re-add';
  RETURN NEW;
END
$$;
CREATE TRIGGER trg_membership_no_extend
BEFORE UPDATE OF expires_at ON user_org_memberships
FOR EACH ROW
WHEN (OLD.expires_at IS NOT NULL AND OLD.expires_at <= CURRENT_TIMESTAMP)
EXECUTE FUNCTION trg_membership_no_extend_fn();

CREATE TABLE user_dimension_grants ( -- 授权作用域 = 用户 × 组织（经 dimension 隐式挂组织，D7）
  user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dimension_id  TEXT NOT NULL REFERENCES dimensions(id) ON DELETE RESTRICT,   -- P0-C
  value_id      TEXT NOT NULL REFERENCES dimension_values(id) ON DELETE RESTRICT,  -- P0-C
  source        TEXT NOT NULL DEFAULT 'local',   -- local | sync:<system>（D16 真值源标记）
  synced_at     TIMESTAMP,
  expires_at    TIMESTAMP,                        -- 临时授权（P1-7）
  granted_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, dimension_id, value_id)
);
CREATE INDEX idx_grants_dim ON user_dimension_grants(dimension_id);
-- 移出组织/成员关系过期清理 → 级联删该组织维度下该用户授权（P1-3；含 sync 来源——#33 P0-1⑥）
CREATE FUNCTION trg_membership_delete_cleanup_fn() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  DELETE FROM user_dimension_grants
  WHERE user_id = OLD.user_id
    AND dimension_id IN (SELECT id FROM dimensions WHERE org_id = OLD.org_id);
  RETURN OLD;
END
$$;
CREATE TRIGGER trg_membership_delete_cleanup AFTER DELETE ON user_org_memberships
  FOR EACH ROW EXECUTE FUNCTION trg_membership_delete_cleanup_fn();

-- ============ 文档（FR-1，v0.3：版本在用制——P0-A） ============
CREATE TABLE documents (
  id              TEXT PRIMARY KEY,   -- ULID（覆盖更新显式携带——文档身份唯一锚点）
  org_id          TEXT NOT NULL REFERENCES orgs(id),   -- 组织不可删只能停用（#33 P1-1）；org_id 不可变（下方触发器）
  dataset_id      TEXT NOT NULL REFERENCES datasets(id),
  title           TEXT NOT NULL,
  source_uri      TEXT,
  content_hash    TEXT NOT NULL,
  mime_type       TEXT NOT NULL,
  page_count      INTEGER,
  parser          TEXT NOT NULL,
  active_version  INTEGER NOT NULL DEFAULT 0,
  active_status   TEXT,
  active_error    TEXT,
  pending_version INTEGER,
  pending_status  TEXT,
  pending_error   TEXT,
  pending_dims_json TEXT,
  owner_user_id   TEXT NOT NULL REFERENCES users(id),  -- 检索路径无 owner 分支（D22③/#34 必修 2）
  raw_object_key  TEXT NOT NULL,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP
);
-- org 一致性 + 不可变触发器（#33 P2-8/9）+ 搬库双重防护（#34 4.6）——plpgsql 等价
CREATE FUNCTION trg_documents_org_immutable_fn() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'documents.org_id is immutable';
  RETURN NEW;
END
$$;
CREATE TRIGGER trg_documents_org_immutable BEFORE UPDATE OF org_id ON documents
  FOR EACH ROW EXECUTE FUNCTION trg_documents_org_immutable_fn();
CREATE FUNCTION trg_datasets_org_immutable_fn() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'datasets.org_id is immutable';
  RETURN NEW;
END
$$;
CREATE TRIGGER trg_datasets_org_immutable BEFORE UPDATE OF org_id ON datasets
  FOR EACH ROW EXECUTE FUNCTION trg_datasets_org_immutable_fn();
CREATE FUNCTION trg_dimensions_org_immutable_fn() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'dimensions.org_id is immutable';
  RETURN NEW;
END
$$;
CREATE TRIGGER trg_dimensions_org_immutable BEFORE UPDATE OF org_id ON dimensions
  FOR EACH ROW EXECUTE FUNCTION trg_dimensions_org_immutable_fn();
CREATE FUNCTION trg_documents_ds_org_check_fn() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT org_id FROM datasets WHERE id = NEW.dataset_id) <> NEW.org_id THEN
    RAISE EXCEPTION 'dataset org mismatch';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER trg_documents_ds_org_check BEFORE INSERT ON documents
  FOR EACH ROW EXECUTE FUNCTION trg_documents_ds_org_check_fn();
CREATE FUNCTION trg_documents_ds_immutable_fn() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT org_id FROM datasets WHERE id = NEW.dataset_id) <> OLD.org_id THEN
    RAISE EXCEPTION 'dataset move across org is forbidden';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER trg_documents_ds_immutable BEFORE UPDATE OF dataset_id ON documents
  FOR EACH ROW EXECUTE FUNCTION trg_documents_ds_immutable_fn();

CREATE INDEX idx_documents_hash ON documents(dataset_id, content_hash);

CREATE TABLE document_dimensions (   -- 文档维度（多值，D19）
  doc_id       TEXT NOT NULL REFERENCES documents(id)        ON DELETE CASCADE,
  dimension_id TEXT NOT NULL REFERENCES dimensions(id)       ON DELETE RESTRICT,  -- P0-C
  value_id     TEXT NOT NULL REFERENCES dimension_values(id) ON DELETE RESTRICT,  -- P0-C
  PRIMARY KEY (doc_id, dimension_id, value_id)
);
-- 脏维度双重防护（#34 4.6）：value/dimension 归属 + 维度 org = 文档 org
-- （`<>` 与 sqlite `!=` 同为 NULL 传播——引用缺失行交由外键捕获，语义同源）
CREATE FUNCTION trg_docdims_consistency_fn() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT dimension_id FROM dimension_values WHERE id = NEW.value_id) <> NEW.dimension_id
     OR (SELECT org_id FROM dimensions WHERE id = NEW.dimension_id)
        <> (SELECT org_id FROM documents WHERE id = NEW.doc_id) THEN
    RAISE EXCEPTION 'document_dimensions consistency violation';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER trg_docdims_consistency BEFORE INSERT ON document_dimensions
  FOR EACH ROW EXECUTE FUNCTION trg_docdims_consistency_fn();

-- 预留不启用（D 决策：user 级临时共享，与维度过滤 OR 合并）
CREATE TABLE acl_entries (
  id             TEXT PRIMARY KEY,
  doc_id         TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  principal_type TEXT NOT NULL,
  principal_id   TEXT NOT NULL,
  permission     TEXT NOT NULL DEFAULT 'read',
  granted_by     TEXT,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(doc_id, principal_type, principal_id, permission)
);

-- ============ 块与索引（FR-1/2/3） ============
-- §4 PG 映射逐项：
--   · FTS5 五列 + ai/ad/au 触发器 → **tsvector 五列 GENERATED**
--     （显式 regconfig 双参 to_tsvector('simple', …)——GENERATED 要求表达式
--     immutable；G-6：分词列依赖应用层 jieba 结果，词典升级须触发全量重算迁移）；
--   · chunks.embedding BLOB → **vector 列**（不锁维度——写入侧 Embedder 校验
--     len==config.dim；`<=>` 精确扫描起步，索引化/halfvec 随 M1——G-6）；
--   · rid INTEGER PRIMARY KEY → BIGINT GENERATED ALWAYS AS IDENTITY。
CREATE TABLE chunks (
  rid           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id            TEXT NOT NULL UNIQUE, -- ULID（引用溯源锚点）
  doc_id        TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  version       INTEGER NOT NULL,
  tombstone     INTEGER NOT NULL DEFAULT 0,
  content       TEXT NOT NULL,        -- 正文原文（不进索引——rerank 专用输入口径）
  title_seg     TEXT NOT NULL DEFAULT '',
  content_seg   TEXT NOT NULL DEFAULT '',
  token_count   INTEGER,
  heading_path  TEXT,
  page_no       INTEGER,
  sheet_name    TEXT,
  bbox_json     TEXT,
  keywords      TEXT NOT NULL DEFAULT '',
  llm_keywords  TEXT NOT NULL DEFAULT '',
  tags          TEXT NOT NULL DEFAULT '',
  embedding     vector,               -- pgvector（G-6：精确扫描起步；NULL=未就绪走 BM25 单路）
  embed_model   TEXT,                 -- 模型标签 model:dim（D12）；兼作向量召回查询谓词
  dims_json     JSONB NOT NULL DEFAULT '{}'::jsonb,  -- 文档维度冗余投影（M0b 实验候选去除项）
  detected_at_scale INTEGER,
  content_sha   TEXT,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  title_tsv        tsvector GENERATED ALWAYS AS
    (to_tsvector('simple', coalesce(title_seg, ''))) STORED,
  content_tsv      tsvector GENERATED ALWAYS AS
    (to_tsvector('simple', coalesce(content_seg, ''))) STORED,
  keywords_tsv     tsvector GENERATED ALWAYS AS
    (to_tsvector('simple', coalesce(keywords, ''))) STORED,
  llm_keywords_tsv tsvector GENERATED ALWAYS AS
    (to_tsvector('simple', coalesce(llm_keywords, ''))) STORED,
  tags_tsv         tsvector GENERATED ALWAYS AS
    (to_tsvector('simple', coalesce(tags, ''))) STORED
);
CREATE UNIQUE INDEX uq_chunks_docver ON chunks(doc_id, version, seq);  -- #34 4.4
CREATE INDEX idx_chunks_vec_pending ON chunks(doc_id) WHERE embedding IS NULL AND tombstone = 0;  -- P1-2

-- ============ 质量反馈环（FR-3） ============
CREATE TABLE quality_flags (
  id            TEXT PRIMARY KEY,
  chunk_id      TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  doc_id        TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  reason        TEXT NOT NULL,
  detail_json   TEXT,
  auto_keywords TEXT,
  manual_tags   TEXT,
  state         TEXT NOT NULL DEFAULT 'open',
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at   TIMESTAMP
);
CREATE INDEX idx_qflags_doc ON quality_flags(doc_id, state);

-- ============ 任务（FR-1，ragflow 样板最小化） ============
CREATE TABLE tasks (
  id           TEXT PRIMARY KEY,
  doc_id       TEXT REFERENCES documents(id) ON DELETE SET NULL,
  type         TEXT NOT NULL,
  status       TEXT NOT NULL,
  lease_owner  TEXT,
  lease_until  TIMESTAMP,
  heartbeat_at TIMESTAMP,
  attempts     INTEGER NOT NULL DEFAULT 0,
  error        TEXT,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP
);
CREATE INDEX idx_tasks_status ON tasks(status, created_at);

-- ============ 嵌入指纹基线（D12/#42 P1-1） ============
CREATE TABLE embedding_fingerprints (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  embed_model  TEXT    NOT NULL UNIQUE,
  baseline     TEXT    NOT NULL,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP
);

-- ============ 审计 outbox（主库，v0.4 #34 4.5） ============
-- 权限事件与业务写同事务入队，后台搬运到 audit_events 分区表——"业务改了就一定有审计"
CREATE TABLE audit_outbox (
  id          TEXT PRIMARY KEY,
  event_type  TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  shipped_at  TIMESTAMP
);
