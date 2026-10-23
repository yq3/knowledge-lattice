-- 0001 schema v1：design §4 文档侧全量 DDL 与触发器（M0a.1 一次性落）。
-- 范围外（另行落库）：
--   · sem_* 语义表——M2-S1 经 store/<dialect>/migrations/semantic/ 落库（§3 边界规则 3）；
--   · audit_events + append-only 触发器——属月库 audit_YYYYMM.db，由连接工厂滚动创建（§4 注）；
--   · PRAGMA——连接级设置（journal_mode/busy_timeout/foreign_keys/synchronous），见 §3 连接工厂。

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
  required      INTEGER NOT NULL DEFAULT 1,  -- 仅控制上传校验（强制选值），不影响过滤
  enabled       INTEGER NOT NULL DEFAULT 1,  -- 仅控制上传页是否展示/选值，不影响过滤
  grant_source  TEXT NOT NULL DEFAULT 'local',  -- 授权真值源：local | sync:<system>（D16）
  value_source  TEXT NOT NULL DEFAULT 'local',  -- 取值枚举是否来自企业主数据
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP,
  UNIQUE(org_id, key)
);

CREATE TABLE dimension_values (      -- 维度取值枚举（value 即稳定编码——企业主数据码，label 可改不影响引用）
  id           TEXT PRIMARY KEY,
  dimension_id TEXT NOT NULL REFERENCES dimensions(id) ON DELETE RESTRICT,  -- P0-C：禁止级联绕过权限事件
  value        TEXT NOT NULL,        -- CN / OVERSEAS / VAT / CIT（ISO 国家码/税种码，不用中文名）
  label        TEXT NOT NULL,        -- 中国区 / 海外区（显示名，可改）
  status       TEXT NOT NULL DEFAULT 'active',   -- active / disabled（软停用=收紧，D19；物理删除仅无引用时）
  sort_order   INTEGER NOT NULL DEFAULT 0,
  UNIQUE(dimension_id, value)
);
-- 取值字面量不可变：改名走"新建值 + 迁移 + 停用旧值"事件流程（P0-C）
CREATE TRIGGER trg_dimval_immutable BEFORE UPDATE OF value, dimension_id ON dimension_values
BEGIN
  SELECT RAISE(ABORT, 'dimension value is immutable; create a new value and migrate');
END;

-- ============ 用户与组织归属（D7：全局账号 + 多组织成员关系） ============
CREATE TABLE users (                -- 全局账号（跨组织唯一）
  id            TEXT PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  display_name  TEXT,
  token_hash    TEXT,               -- 静态 token（sha256），仅开发/测试与 CI（D18）；生产走 SSO/委托 token
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
-- 续期禁令（T2/T23）：已过期成员关系不得原地续期（删除后重加走权限事件 + cleanup 级联）
CREATE TRIGGER trg_membership_no_extend
BEFORE UPDATE OF expires_at ON user_org_memberships
WHEN OLD.expires_at IS NOT NULL AND OLD.expires_at <= CURRENT_TIMESTAMP
BEGIN SELECT RAISE(ABORT, 'expired membership: delete then re-add'); END;

CREATE TABLE user_dimension_grants ( -- 授权作用域 = 用户 × 组织（经 dimension 隐式挂组织，D7）
  user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dimension_id  TEXT NOT NULL REFERENCES dimensions(id) ON DELETE RESTRICT,   -- P0-C
  value_id      TEXT NOT NULL REFERENCES dimension_values(id) ON DELETE RESTRICT,  -- P0-C
  source        TEXT NOT NULL DEFAULT 'local',   -- local | sync:<system>（D16 真值源标记）
  synced_at     TIMESTAMP,                        -- 同步维度最近刷新时间；失败保留旧快照并告警
  expires_at    TIMESTAMP,                        -- 临时授权（P1-7）：权限计算过滤过期，定时清理+审计
  granted_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, dimension_id, value_id)
);
CREATE INDEX idx_grants_dim ON user_dimension_grants(dimension_id);
-- 移出组织/成员关系过期清理 → 级联删该组织维度下该用户授权（P1-3；含 sync 来源授权——预期行为：
-- 同步适配器写入前须校验目标用户在本组织有有效成员关系，否则会生成孤儿授权——#33 P0-1⑥，§5.6）
CREATE TRIGGER trg_membership_delete_cleanup AFTER DELETE ON user_org_memberships
BEGIN
  DELETE FROM user_dimension_grants
  WHERE user_id = OLD.user_id
    AND dimension_id IN (SELECT id FROM dimensions WHERE org_id = OLD.org_id);
END;
-- 注：「文档 org = 库 org = 维度 org」一致性由服务层写入校验 + 触发器断言；授权行不含 org 列
-- （org 经 dimension_id 唯一归属推得，服务层断言）。

-- ============ 文档（FR-1，v0.3：版本在用制——P0-A） ============
CREATE TABLE documents (
  id              TEXT PRIMARY KEY,   -- ULID（覆盖更新显式携带——文档身份唯一锚点）
  org_id          TEXT NOT NULL REFERENCES orgs(id),   -- 组织不可删只能停用（#33 P1-1）；org_id 不可变（下方触发器）
  dataset_id      TEXT NOT NULL REFERENCES datasets(id),  -- 归属知识库（D15）；删库走服务层流程（先删文档再删库，§6.2）
  title           TEXT NOT NULL,
  source_uri      TEXT,               -- 上传来源（user:<id> / agent:<id>——agent 代传内容标来源，随检索返回）
  content_hash    TEXT NOT NULL,      -- 内容哈希（重复提示，不强制拦截——P0-5）
  mime_type       TEXT NOT NULL,
  page_count      INTEGER,
  parser          TEXT NOT NULL,      -- docling | mineru
  active_version  INTEGER NOT NULL DEFAULT 0,  -- 在用版本（0=尚无在用版本）；检索只见该版本
  active_status   TEXT,               -- 在用版本状态：searchable_lexical | searchable_full | degraded（#33 P0-2.2）
  active_error    TEXT,               -- 在用版本嵌入/质量阶段失败写这里
  pending_version INTEGER,            -- 处理中版本（NULL=无进行中摄取）；= max(历史版本)+1，失败不复用（P0-2.3）
  pending_status  TEXT,               -- parsing|chunked|searchable_lexical|searchable_full|failed
  pending_error   TEXT,
  pending_dims_json TEXT,             -- pending 版本的新维度（P0-2.1）：pending 期间不生效，切换事务落入 document_dimensions
  owner_user_id   TEXT NOT NULL REFERENCES users(id),  -- 文档所有者（管理面操作权限与来源展示；检索路径无 owner 分支——D22③）
  raw_object_key  TEXT NOT NULL,      -- 对象目录键（canonical 真相锚点）
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP
);
-- org 一致性 + 不可变触发器（#33 P2-8/9：防"搬组织/搬库"绕过权限事件；一致性由 BEFORE 触发器断言）
CREATE TRIGGER trg_documents_org_immutable BEFORE UPDATE OF org_id ON documents
BEGIN SELECT RAISE(ABORT, 'documents.org_id is immutable'); END;
CREATE TRIGGER trg_datasets_org_immutable  BEFORE UPDATE OF org_id  ON datasets
BEGIN SELECT RAISE(ABORT, 'datasets.org_id is immutable'); END;
CREATE TRIGGER trg_dimensions_org_immutable BEFORE UPDATE OF org_id ON dimensions
BEGIN SELECT RAISE(ABORT, 'dimensions.org_id is immutable'); END;
CREATE TRIGGER trg_documents_ds_org_check BEFORE INSERT ON documents
WHEN (SELECT org_id FROM datasets WHERE id = NEW.dataset_id) != NEW.org_id
BEGIN SELECT RAISE(ABORT, 'dataset org mismatch'); END;
-- #34 4.6（M0a 随 schema 落地）：搬库与脏维度双重防护——
CREATE TRIGGER trg_documents_ds_immutable BEFORE UPDATE OF dataset_id ON documents
WHEN (SELECT org_id FROM datasets WHERE id = NEW.dataset_id) != OLD.org_id
BEGIN SELECT RAISE(ABORT, 'dataset move across org is forbidden'); END;
-- #34 4.6（M0a 随 schema 落地）：脏维度双重防护——trg_docdims_consistency 见 document_dimensions 建表后
--（CREATE TRIGGER 要求目标表已存在，执行顺序与 §4 文档排版不同、语义一致）。
-- 重复检测：索引按 (dataset_id, content_hash) 粗筛；维度一致性由服务层比对 document_dimensions
CREATE INDEX idx_documents_hash ON documents(dataset_id, content_hash);

CREATE TABLE document_dimensions (   -- 文档维度（多值，D19：通用文档可挂 region∈{CN,OS}；内容混杂仍拆分上传 D4）
  doc_id       TEXT NOT NULL REFERENCES documents(id)        ON DELETE CASCADE,   -- 删文档可级联
  dimension_id TEXT NOT NULL REFERENCES dimensions(id)       ON DELETE RESTRICT,  -- P0-C
  value_id     TEXT NOT NULL REFERENCES dimension_values(id) ON DELETE RESTRICT,  -- P0-C
  PRIMARY KEY (doc_id, dimension_id, value_id)
);
CREATE TRIGGER trg_docdims_consistency BEFORE INSERT ON document_dimensions
WHEN (SELECT dimension_id FROM dimension_values WHERE id = NEW.value_id) != NEW.dimension_id
  OR (SELECT org_id FROM dimensions WHERE id = NEW.dimension_id)
    != (SELECT org_id FROM documents WHERE id = NEW.doc_id)
BEGIN SELECT RAISE(ABORT, 'document_dimensions consistency violation'); END;

-- 预留不启用（D 决策：user 级临时共享，与维度过滤 OR 合并）
CREATE TABLE acl_entries (
  id             TEXT PRIMARY KEY,
  doc_id         TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  principal_type TEXT NOT NULL,      -- user（group 暂无必要，维度模型已覆盖）
  principal_id   TEXT NOT NULL,
  permission     TEXT NOT NULL DEFAULT 'read',
  granted_by     TEXT,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(doc_id, principal_type, principal_id, permission)
);

-- ============ 块与索引（FR-1/2/3，P0-1/P0-3/P1-1/P1-3 重做） ============
CREATE TABLE chunks (
  rid           INTEGER PRIMARY KEY, -- 显式整数主键（外部内容 FTS 以它关联，VACUUM 后稳定——P0-3a）
  id            TEXT NOT NULL UNIQUE, -- ULID（引用溯源锚点）
  doc_id        TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,    -- 文档内序号
  version       INTEGER NOT NULL,    -- 所属文档版本（=documents.active_version 或 pending_version）
  tombstone     INTEGER NOT NULL DEFAULT 0,      -- 旧版本标记：不进召回、fetch 返回替代提示；保留 90 天后物理删除
  content       TEXT NOT NULL,       -- 正文原文（不进 FTS——rerank 专用输入口径）
  title_seg     TEXT NOT NULL DEFAULT '',  -- 标题+heading_path 分词（FTS 权重 3——P1-3）
  content_seg   TEXT NOT NULL DEFAULT '',  -- jieba 分词后的正文（FTS 权重 1）
  token_count   INTEGER,
  heading_path  TEXT,                -- 结构感知切分的标题层级
  page_no       INTEGER,
  sheet_name    TEXT,                -- Excel 切分专用（行块 chunk 重复表头）
  bbox_json     TEXT,
  keywords      TEXT NOT NULL DEFAULT '',  -- 仅人工维护关键词（FTS 权重 5）
  llm_keywords  TEXT NOT NULL DEFAULT '',  -- LLM 生成（FTS 权重 0.5~1，独立低权列，P1-1）
  tags          TEXT NOT NULL DEFAULT '',  -- 人工标签（FTS 权重 8）
  embedding     BLOB,                -- 向量 BLOB（P0-1：ACL 过滤后算距离；NULL=未就绪走 BM25 单路）
  embed_model   TEXT,                -- 模型标签 model:dim（D12 修订）；兼作向量召回查询谓词（防混模型向量）
  dims_json     TEXT NOT NULL,       -- 文档维度冗余投影（多值数组）——M0 实验候选去除项（P1-2）
  detected_at_scale INTEGER,         -- 检测时语料规模（区分度重算策略——P1-8）
  content_sha   TEXT,                -- 区分度检测缓存（缓存键 = (content_sha, embed_model)——#42 P1-3）
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX uq_chunks_docver ON chunks(doc_id, version, seq);  -- v0.4：fetch 窗口与"按文档计算"共用（含 version——#34 4.4）
CREATE INDEX idx_chunks_vec_pending ON chunks(doc_id) WHERE embedding IS NULL AND tombstone = 0;  -- 谓词含 tombstone（P1-2）

-- FTS5（P0-3 + P1-1/P1-3 重做）：
--   · 五列分权：title_seg 3 / content_seg 1 / keywords 5 / llm_keywords 0.5~1 / tags 8
--     （bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)——参数按列顺序）
--   · 外部内容表 + 三个同步触发器（列清单与 FTS 列一致；插入目标列名为 rowid——
--     §4 文档示意写作 rid，FTS5 虚表侧实装必须用 rowid，值仍为 new/old.rid，语义一致）
--   · 查询侧转义（token 双引号包裹、内部 " 转义为 ""）随 M0a-2 检索链（store/sqlite/fts.py）
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  title_seg, content_seg, keywords, llm_keywords, tags,
  content='chunks', content_rowid='rid', tokenize='unicode61'
);
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES (new.rid, new.title_seg, new.content_seg, new.keywords, new.llm_keywords, new.tags);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES ('delete', old.rid, old.title_seg, old.content_seg, old.keywords, old.llm_keywords, old.tags);
END;
CREATE TRIGGER chunks_au AFTER UPDATE OF title_seg, content_seg, keywords, llm_keywords, tags ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES ('delete', old.rid, old.title_seg, old.content_seg, old.keywords, old.llm_keywords, old.tags);
  INSERT INTO chunks_fts(rowid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES (new.rid, new.title_seg, new.content_seg, new.keywords, new.llm_keywords, new.tags);
END;

-- ============ 质量反馈环（FR-3） ============
CREATE TABLE quality_flags (
  id            TEXT PRIMARY KEY,
  chunk_id      TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  doc_id        TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,  -- v0.4 补外键（#33 P1-1）
  reason        TEXT NOT NULL,       -- vector_crowding | low_idf | both
  detail_json   TEXT,                -- 近邻相似度分布 / IDF 统计（展示须过同一套 ACL 或只显示数值——#33 P1-10）
  auto_keywords TEXT,                -- LLM 生成（内部网关）
  manual_tags   TEXT,                -- 人工补充
  state         TEXT NOT NULL DEFAULT 'open',  -- open|resolved|ignored
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at   TIMESTAMP
);
CREATE INDEX idx_qflags_doc ON quality_flags(doc_id, state);

-- ============ 任务（FR-1，ragflow 样板最小化） ============
CREATE TABLE tasks (
  id           TEXT PRIMARY KEY,
  doc_id       TEXT REFERENCES documents(id) ON DELETE SET NULL,  -- 保留任务历史（#33 P1-1）
  type         TEXT NOT NULL,        -- ingest | reindex | reembed | delete | semantic_sync | semantic_build | semantic_retag | maintenance（M2 起）
  status       TEXT NOT NULL,        -- pending|leased|running|done|failed
  lease_owner  TEXT,
  lease_until  TIMESTAMP,            -- worker 崩溃后任务可被重新认领
  heartbeat_at TIMESTAMP,
  attempts     INTEGER NOT NULL DEFAULT 0,
  error        TEXT,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP
);
CREATE INDEX idx_tasks_status ON tasks(status, created_at);

-- ============ 嵌入指纹基线（D12/#42 P1-1——探针存档，见 §5.3） ============
CREATE TABLE embedding_fingerprints (
  id           INTEGER PRIMARY KEY,
  embed_model  TEXT    NOT NULL UNIQUE,        -- config 标签（model:dim）
  baseline     TEXT    NOT NULL,               -- JSON：[{sentinel, vector}]，哨兵 ≥3 条（多哨兵取最小余弦）
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP                      -- 管理面重置基线时更新（重置入审计）
);

-- ============ 审计 outbox（主库，v0.4 #34 4.5） ============
-- 权限事件与业务写同事务入队，后台搬运到月库 audit_YYYYMM.db——"业务改了就一定有审计"；
-- audit_events 表与 append-only 触发器属月库、由连接工厂滚动创建（不在本 schema 内）。
CREATE TABLE audit_outbox (
  id          TEXT PRIMARY KEY,
  event_type  TEXT NOT NULL,         -- grant|revoke|dimension_change|retire|membership|...
  payload_json TEXT NOT NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  shipped_at  TIMESTAMP              -- NULL=待搬运；后台任务搬至月库 audit_events 后回填
);
