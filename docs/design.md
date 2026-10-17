# knowledge-lattice 方案设计

> 版本：v0.2（2026-10-17 评审修订：吸收 [issue #31](https://github.com/yq3/lab/issues/31)——P0×5 实现缺陷修复【向量下推/ACL 括号化/FTS5 重做/摄取阶段拆分/维度多值】+ P1 权限安全与性能运维 + P2 一致性修正）
> 日期：2026-10-16 初稿，2026-10-17 修订
> 前置阅读：[requirements.md](./requirements.md)（本文所有 FR/NFR/D 编号均指向需求文档 v0.2）
> 调研依据：[enterprise-rag 调研](../../research/enterprise-rag/)，参考架构基线 `blog/10-build-kb-for-agent.md`

---

## 1. 设计总览：需求 → 方案的映射

| 需求 | 方案落点 | 本文章节 |
|---|---|---|
| FR-1 摄取 | 单进程 + worker 子进程 + 任务表；docling 进程内解析 | §2 / §5.3 |
| FR-2 检索 | SQLite 内双路（FTS5 + sqlite-vec）→ RRF → 进程内 rerank | §5.2 |
| FR-3 区分度反馈环 | 摄取管线尾部 quality 阶段 + 质量报告接口 | §5.4 |
| FR-4 维度权限 | 维度模型五表 + ACL 编译器（查询时展开，引擎内下推） | §4 / §5.1 |
| FR-5 接口面 | FastMCP 三工具 + REST + 静态薄壳前端 | §6 |
| FR-6/7 治理与评测 | audit_events 触发器；评测脚本集（黄金集 + 门禁） | §4 / §9 |
| NFR-1 零中间件 | 全部组件进程内/文件级，无外部常驻服务 | §2 |
| NFR-5 演进缝 | repository 接口 + 配置级切换点清单 | §7 |
| **issue #31 评审修订（v0.2）** | P0 五项修复 + 权限安全 + 性能运维 | §4 / §5.1~5.3 / §5.6 / §8~10 |

## 2. 进程与部署架构

```
 ┌─────────────────────┐        ┌──────────────────────────┐
 │ 前端薄壳（静态页）    │        │ deepagents（企业内服务）    │
 │ 上传/检索/管理        │        │ agent 循环住在这里          │
 └─────────┬───────────┘        └────────────┬─────────────┘
           │ REST                             │ MCP（HTTP，带用户 token）
           ▼                                  ▼
 ┌───────────────────────────────────────────────────────────┐
 │ knowledge-lattice 主进程（FastAPI，单进程）                    │
 │  · REST 控制面：upload / tasks / search / admin              │
 │  · FastMCP server：search / upload / list_documents         │
 │  · 检索管线（同步）：双路召回→RRF→rerank→维度 ACL 过滤→溯源返回  │
 │  · 维度 ACL 编译器：用户 token → 维度授权 → SQL WHERE          │
 │  · 任务调度：写 tasks 表 + 唤醒 worker；审计写入                │
 └────────┬────────────────────────────────────┬──────────────┘
          │ 子进程 IPC（unix socket / stdin）    │ 读写
 ┌────────▼──────────────┐          ┌───────────▼──────────────┐
 │ 摄取 worker 子进程      │          │ SQLite（data/lattice.db）  │
 │ 解析→切分→嵌入→入库      │          │ 元数据 + FTS5 + sqlite-vec │
 │ →区分度检测→LLM 关键词   │          │ WAL 模式（多读单写）        │
 │ 心跳/租约/断点续跑       │          └──────────────────────────┘
 └────────┬───────┬──────┘
          │       │                ┌──────────────────────────┐
 ┌────────▼──┐ ┌──▼─────────┐      │ data/objects/ 对象目录     │
 │ docling    │ │ 内部 LLM    │      │ 原始文件+解析产物           │
 │ （进程内库）│ │ 网关客户端   │      │ （canonical 真相，可重建）   │
 │ MinerU 懒载│ │ (关键词增强/ │      └──────────────────────────┘
 │ （可选服务）│ │  区分度兜底) │
 └───────────┘ └────────────┘
```

**部署形态（NFR-1/9）**：`knowledge-lattice` 主进程 ×1（内含 worker 子进程）+ `lattice.db` ×1 + `data/objects/` 目录 ×1。无消息队列、无独立向量库、无嵌入服务容器——它们分别是 tasks 表轮询、**chunks.embedding BLOB 列 + sqlite-vec 距离函数**、进程内 bge-m3。worker 经 IPC 被唤醒 + 兜底轮询（anything-llm 的最小进程隔离样板：OOM 只杀 worker）。**资源预算**：主进程与 worker 各加载一份模型（嵌入+reranker+docling），峰值 6~8 GB——最低规格 16 GB RAM / 8 核；**CPU 推理全部进线程/进程池**，不阻塞事件循环。

**并发模型（NFR-9）**：SQLite WAL 模式（多读单写）。检索（读）不受摄取（写）阻塞；写竞争治理：`busy_timeout` + worker 短事务分批提交 + 审计异步批量写（竞争激烈时拆独立 `audit.db`）。数百用户检索并发的实际瓶颈在 rerank 计算（§5.2 缓解：候选 32 / ONNX int8 / 信号量）。

**备份恢复（NFR-10）**：SQLite `VACUUM INTO` / online backup 定时快照 + `data/objects/` 一并备份；RPO ≤ 24h / RTO ≤ 4h（POC 目标）；恢复演练进 runbook。

**升级缝（NFR-5 落点）**：存储（repository 接口后换 pgvector/milvus，触发阈值为 100 万 chunk 或 P95 超标——NFR-2）、嵌入与重排（进程内 → TEI 容器，接口不变）、解析（docling → MinerU api_server，路由表驱动）、授权同步（grant_sync 适配器启用只读同步维度——D16）。

## 3. 代码模块划分

```
knowledge_lattice/
├── app.py                  # FastAPI 入口：装配路由/MCP/DB/worker
├── config.py               # 全部配置（模型版本、阈值、路径、网关地址）
├── api/
│   ├── upload.py           # POST /api/documents（校验目标库 + 必选维度齐全，D5/D15）
│   ├── datasets.py         # 知识库 CRUD（组织内，D15）
│   ├── orgs.py             # 组织 CRUD 与成员管理（系统管理员，D7）
│   ├── tasks.py            # GET /api/tasks、文档状态
│   ├── search.py           # POST /api/search（检索测试页用，支持库过滤）
│   └── admin.py            # 维度/取值/用户/授权 CRUD
├── mcp/
│   └── server.py           # FastMCP：三工具 + 鉴权中间件（60s 超时）
├── core/
│   ├── ingest.py           # 摄取管线编排：parse→chunk→embed→index→quality
│   ├── chunking.py         # 结构感知切分（docling 结构树 + 递归 token）
│   ├── excel_chunking.py   # Excel 表格型切分（sheet/行块）
│   ├── retrieve.py         # 检索管线编排：召回→融合→重排→过滤→溯源
│   ├── acl.py              # 维度 ACL 编译器（§5.1）
│   └── quality.py          # 区分度检测 + LLM 关键词增强（§5.4）
├── adapters/
│   ├── parser_docling.py   # docling 封装（DoclingDocument→统一块结构）
│   ├── parser_mineru.py    # MinerU 懒加载路由（可选，按配置启用）
│   ├── embedder.py         # bge-m3 进程内（钉版本）
│   ├── reranker.py         # bge-reranker-v2-m3 进程内（归一 [0,1]）
│   ├── llm.py              # 内部网关客户端（OpenAI 兼容）
│   ├── auth_sso.py         # SSO 验签（OIDC/CAS 适配，协议待定；JIT 建档）
│   ├── grant_sync.py       # 授权同步适配器（D16 演进缝，默认禁用）
│   └── tokenizer.py        # jieba 预分词（keywords 生成）
├── store/
│   ├── db.py               # 连接、迁移（PRAGMA user_version 管理 schema 版本）
│   ├── repo.py             # repository 接口：hybrid_search/insert/delete_by_doc
│   ├── fts.py              # FTS5 建表/查询（列权重）
│   └── vec.py              # sqlite-vec 虚表读写
├── domain/
│   ├── models.py           # pydantic 实体
│   └── auth.py             # token→user 解析（初版静态 token 表，预留网关 JWT）
├── worker/
│   ├── runner.py           # 子进程入口：任务循环（租约认领/心跳/重试）
│   └── ipc.py              # 与主进程的唤醒协议
├── eval/                   # M3：黄金集运行器 + Recall@k/MRR + ragas 接入
└── web/                    # 前端薄壳（§5.6，原型见 prototype/）
```

分层纪律：`api/mcp` 只做协议转换；`core` 是纯业务编排（不碰 SQL 细节）；`store` 是唯一碰 SQL 的层；`adapters` 是全部外部依赖的收口（docling/模型/网关），每个 adapter 可独立替换——这是「可二改」（NFR-4）的结构保证。

## 4. 数据模型（SQLite DDL v1）

```sql
PRAGMA journal_mode = WAL;

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

CREATE TABLE dimensions (            -- 维度定义（配置页 CRUD 对象，D9）
  id            TEXT PRIMARY KEY,    -- ULID
  org_id        TEXT NOT NULL REFERENCES orgs(id),
  key           TEXT NOT NULL,       -- region / tax_type
  name          TEXT NOT NULL,       -- 作业区域 / 税种
  required      INTEGER NOT NULL DEFAULT 1,  -- 必选：上传时强制选值（D5）；编译器只对「启用+必选」生成条件
  enabled       INTEGER NOT NULL DEFAULT 1,
  grant_source  TEXT NOT NULL DEFAULT 'local',  -- 授权真值源：local | sync:<system>（D16——同步维度管理页只读）
  value_source  TEXT NOT NULL DEFAULT 'local',  -- 取值枚举是否来自企业主数据
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP,
  UNIQUE(org_id, key)
);

CREATE TABLE dimension_values (      -- 维度取值枚举（value 即稳定编码——企业主数据码，label 可改不影响引用）
  id           TEXT PRIMARY KEY,
  dimension_id TEXT NOT NULL REFERENCES dimensions(id) ON DELETE CASCADE,
  value        TEXT NOT NULL,        -- CN / OVERSEAS / VAT / CIT（ISO 国家码/税种码，不用中文名）
  label        TEXT NOT NULL,        -- 中国区 / 海外区（显示名，可改）
  sort_order   INTEGER NOT NULL DEFAULT 0,
  UNIQUE(dimension_id, value)
);

-- ============ 用户与组织归属（D7：全局账号 + 多组织成员关系） ============
CREATE TABLE users (                -- 全局账号（跨组织唯一）
  id            TEXT PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  display_name  TEXT,
  token_hash    TEXT,               -- 初版静态 token（sha256）；预留网关 JWT 校验
  is_system_admin INTEGER NOT NULL DEFAULT 0,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_org_memberships ( -- 用户 × 组织 多对多，角色按组织独立（D7）
  user_id  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_id   TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  role     TEXT NOT NULL DEFAULT 'member',   -- org_admin | member
  PRIMARY KEY (user_id, org_id)
);

CREATE TABLE user_dimension_grants ( -- 授权作用域 = 用户 × 组织（经 dimension 隐式挂组织，D7）
  user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dimension_id  TEXT NOT NULL REFERENCES dimensions(id) ON DELETE CASCADE,
  value_id      TEXT NOT NULL REFERENCES dimension_values(id) ON DELETE CASCADE,  -- 引用值 id，改名/删除不悬空（issue #31 P1-4）
  source        TEXT NOT NULL DEFAULT 'local',   -- local | sync:<system>（D16 真值源标记）
  synced_at     TIMESTAMP,                        -- 同步维度最近刷新时间；失败保留旧快照并告警
  granted_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, dimension_id, value_id)
);
CREATE INDEX idx_grants_dim ON user_dimension_grants(dimension_id);
-- 注：移出组织的级联由服务层执行（删除 memberships 时同步删除该组织全部维度下的该用户授权——issue #31 P1-3）；
-- 「文档 org = 库 org = 维度 org」一致性由服务层写入校验 + 触发器断言。

-- ============ 文档（FR-1） ============
CREATE TABLE documents (
  id             TEXT PRIMARY KEY,   -- ULID（覆盖更新显式携带——文档身份唯一锚点，issue #31 P2-6）
  org_id         TEXT NOT NULL REFERENCES orgs(id),
  dataset_id     TEXT NOT NULL REFERENCES datasets(id),  -- 归属知识库（D15）；org 一致性由触发器断言
  title          TEXT NOT NULL,
  source_uri     TEXT,               -- 上传来源（user:<id> / agent:<id>——agent 代传内容标来源，随检索返回）
  content_hash   TEXT NOT NULL,      -- 内容哈希（重复**提示**，不强制拦截——P0-5）
  mime_type      TEXT NOT NULL,
  page_count     INTEGER,
  parser         TEXT NOT NULL,      -- docling | mineru
  version        INTEGER NOT NULL DEFAULT 1,  -- 覆盖更新递增；旧版本 chunk 置 tombstone（P1-9）
  status         TEXT NOT NULL,      -- uploaded|parsing|chunked|searchable_lexical|searchable_full|failed
  owner_user_id  TEXT NOT NULL REFERENCES users(id),  -- owner 恒可见（FR-4 兜底，限本组织）
  raw_object_key TEXT NOT NULL,      -- 对象目录键（canonical 真相锚点）
  error          TEXT,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     TIMESTAMP
);
-- 重复检测键：同库同维度下同内容提示（含维度规范化串——P0-5，通用文档多值挂载见 document_dimensions）
CREATE INDEX idx_documents_hash ON documents(dataset_id, content_hash);

CREATE TABLE document_dimensions (   -- 文档维度（**多值**，D19：通用文档可挂 region∈{CN,OS}；内容混杂仍拆分上传 D4）
  doc_id       TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  dimension_id TEXT NOT NULL REFERENCES dimensions(id) ON DELETE CASCADE,
  value_id     TEXT NOT NULL REFERENCES dimension_values(id) ON DELETE CASCADE,
  PRIMARY KEY (doc_id, dimension_id, value_id)
);

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

-- ============ 块与索引（FR-1/2/3，P0-1/P0-3 重做） ============
CREATE TABLE chunks (
  rid           INTEGER PRIMARY KEY, -- 显式整数主键（外部内容 FTS 以它关联，VACUUM 后稳定——P0-3a）
  id            TEXT NOT NULL UNIQUE, -- ULID（引用溯源锚点；确定性 ID 方案评估中：hash(doc,version,seq)——P1-9）
  doc_id        TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,    -- 文档内序号
  version       INTEGER NOT NULL DEFAULT 1,      -- 所属文档版本（覆盖更新新版本原子替换，旧版本置 tombstone）
  tombstone     INTEGER NOT NULL DEFAULT 0,      -- 旧版本标记：可查、fetch 返回"已被新版本替代"
  content       TEXT NOT NULL,       -- 正文原文（**不进 FTS**——rerank 专用输入口径）
  content_seg   TEXT NOT NULL DEFAULT '',  -- jieba 分词后的正文（空格连接，进 FTS 权重 1——P0-3b）
  token_count   INTEGER,
  heading_path  TEXT,                -- 结构感知切分的标题层级
  page_no       INTEGER,
  sheet_name    TEXT,                -- Excel 切分专用（行块 chunk 重复表头）
  bbox_json     TEXT,
  keywords      TEXT NOT NULL DEFAULT '',  -- jieba 高频词 + 人工标注（FTS 权重 5）
  llm_keywords  TEXT NOT NULL DEFAULT '',  -- LLM 生成的定位语关键词（独立低权重列，标来源——issue #31 P2）
  tags          TEXT NOT NULL DEFAULT '',  -- 人工标签（FTS 权重 8）
  embedding     BLOB,                -- 向量直接存 BLOB 列（P0-1：不做 vec0 虚表 KNN——在 ACL 过滤后的行集上用
                                     --   vec_distance_cosine() 算距离；NULL = 嵌入未就绪，检索退化 BM25 单路）
  embed_model   TEXT,                -- 钉版本：bge-m3@<rev>（D12）；NULL 表示未嵌入
  dims_json     TEXT NOT NULL,       -- 文档维度冗余投影（多值数组化）{"region":["CN","OS"],"tax_type":["VAT"]}
  content_sha   TEXT,                -- 区分度检测缓存（内容指纹，重检跳过）
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_chunks_doc ON chunks(doc_id, seq);
CREATE INDEX idx_chunks_vec_pending ON chunks(doc_id) WHERE embedding IS NULL;  -- useful-early：待嵌入清单

-- FTS5（P0-3 重做）：
--   · 列分权：content_seg 1.0 / keywords 5.0 / tags 8.0（bm25() 列权重）；llm_keywords 不进 FTS 索引或权重 0.5
--   · 外部内容表 + 三个同步触发器（INSERT/UPDATE/DELETE），覆盖替换后无幽灵命中——P0-3c
--   · 查询侧：query 先 jieba 切分，每 token 双引号转义后拼 "tok1" OR "tok2"——防 FTS5 语法注入——P0-3c
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  content_seg, keywords, tags,
  content='chunks', content_rowid='rid', tokenize='unicode61'
);
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rid, content_seg, keywords, tags)
  VALUES (new.rid, new.content_seg, new.keywords, new.tags);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rid, content_seg, keywords, tags)
  VALUES ('delete', old.rid, old.content_seg, old.keywords, old.tags);
END;
CREATE TRIGGER chunks_au AFTER UPDATE OF content_seg, keywords, tags ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rid, content_seg, keywords, tags)
  VALUES ('delete', old.rid, old.content_seg, old.keywords, old.tags);
  INSERT INTO chunks_fts(rid, content_seg, keywords, tags)
  VALUES (new.rid, new.content_seg, new.keywords, new.tags);
END;
-- 注：无 vec0 虚表——向量即 chunks.embedding BLOB；容量与量化（int8/bit）见 NFR-2/3，升级缝见 §7。

-- ============ 质量反馈环（FR-3） ============
CREATE TABLE quality_flags (
  id            TEXT PRIMARY KEY,
  chunk_id      TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  doc_id        TEXT NOT NULL,
  reason        TEXT NOT NULL,       -- vector_crowding | low_idf | both
  detail_json   TEXT,                -- 近邻相似度分布 / IDF 统计
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
  doc_id       TEXT REFERENCES documents(id),
  type         TEXT NOT NULL,        -- ingest | reindex | delete
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

-- ============ 审计（FR-6，quivr 触发器防篡改模式） ============
CREATE TABLE audit_events (
  id          TEXT PRIMARY KEY,
  org_id      TEXT NOT NULL,
  actor       TEXT NOT NULL,         -- user:<id> / agent:<name>:user:<id>
  action      TEXT NOT NULL,         -- search|upload|grant|revoke|dimension_change|...
  target_type TEXT,
  target_id   TEXT,
  outcome     TEXT NOT NULL,         -- accepted | refused
  request_id  TEXT,
  detail_json TEXT,                  -- 查询词、返回的 chunk_id 列表（查询级审计）
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- append-only 触发器（禁 UPDATE/DELETE/TRUNCATE）随 M0 schema 一并落地；防篡改升级 = 哈希链（每条含上一条哈希，链头定期锚定外部——issue #31 P1-10，M2 按需）
```

设计说明（v0.2 修订）：

- **组织与库的隔离纪律**：一切检索/列表 SQL 的第一条件是 `org_id = :org`（跨组织零可见，owner 判定同样限本组织）；库过滤（`dataset_id IN (...)`）是组织内的可选收窄；维度授权与维度定义都在组织作用域内解析。
- **维度冗余的取舍**：`chunks.dims_json` 是 `document_dimensions` 的投影（多值数组），检索 SQL 按 JSON 解析编译成常量条件（§5.1），避免热路径多表 JOIN；文档维度变更时由服务层同步刷投影（UPDATE，不重嵌——D6）。
- **向量存 BLOB 不用 vec0**（P0-1）：vec0 的 KNN 在虚拟表内部取 top-k 后才能 JOIN 过滤，等于 post-trim（授权窄的用户召回塌陷）；BLOB + `vec_distance_cosine()` 在 ACL 过滤后的行集上算距离，"先过滤后扫描"反而更快（扫描量 = 用户可见量）。
- **FTS5 中文**：`unicode61` 只做兜底分词；正文经 jieba 预分词进 `content_seg`（权重 1），人工词 `keywords`（5）/`tags`（8）独立成列保持加权语义不失真；查询侧同词典切分 + token 双引号转义。

## 5. 关键设计

### 5.1 维度 ACL 编译器（core/acl.py）

输入：`user_id` + 请求显式携带的组织上下文 `org_id`；输出：可下推进召回 SQL 的 WHERE 片段（**结构化 builder 生成 AST 再渲染 SQL，禁止字符串拼接**——issue #31 P0-2）。逻辑：

1. **成员关系校验**（第 0 步）：查 `user_org_memberships`——非本组织成员（且非系统管理员）直接拒绝请求，不存在"默认可见"；
2. 查该用户**在本组织**的 `user_dimension_grants`（join `dimensions` 按 org 过滤）得 `{dim_key: [values...]}`（查询时实时读取——人员变更即时生效，D6）；维度 key 集合取自该组织 `dimensions`（各组织维度体系不同，D7）；
3. 对每个「**enabled 且 required**」的维度编译一个「文档取值集合 ∩ 用户授权集 ≠ ∅」条件（维度内 OR、维度间 AND，D19）；**无授权值的必选维度 → 整体不可见**（严格实现，D5）；可选维度不生成条件（空值即不过滤）；
4. owner 兜底分支（owner 判定同样限本组织）。

编译产物（示意——**ACL 表达式整体加括号后，org / dataset / doc_filter 等外层约束一律置于最外层 AND**，P0-2）：

```sql
-- 组织 org:tax 内，用户 region=[CN, OVERSEAS]、tax_type=[VAT]；两维度均必选；文档维度多值（D19）
SELECT c.* FROM chunks c JOIN documents d ON d.id = c.doc_id
WHERE (                                          -- ← 整个 ACL 表达式一组括号
        ( EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.region')   je WHERE je.value IN ('CN','OVERSEAS'))
      AND EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.tax_type') je WHERE je.value IN ('VAT')) )
      OR d.owner_user_id = :uid                   -- owner 兜底（限本组织，由下方 org 条件约束）
      )
  AND d.org_id = 'org:tax'                       -- ← 外层约束在括号外，作用于全部分支
  AND d.dataset_id IN ('ds:vat','ds:intl')        -- ← 库过滤同样作用于维度分支与 owner 分支
  AND d.id IN (:doc_filter)                       --（可选）
-- 无授权必选维度编译为 FALSE 短路 → 全库不可见；可选维度不生成条件
```

性能注：`dims_json` 的 `json_each` 在十万级 chunk 下不可接受时，升级为维度物化列 + 索引（schema 版本 +1 迁移预留），M1 实测后决定。**rerank 前兜底断言**（进模型的候选先过 ACL 复核）+ 返回前二次断言（防御纵深）。

### 5.2 检索管线（core/retrieve.py）

```
query ─→ LLM 关键词增强（**条件触发**：query 过短或中英混排才调，网关超时即降级跳过——NFR-8）
     ├─→ FTS5 BM25 路：query 经 jieba 切分 + token 双引号转义 →
     │    bm25(chunks_fts, query_kw, weights=[1.0, 5.0, 8.0]) + ACL WHERE
     ├─→ 向量路（P0-1 写法）：query embed(bge-m3) →
     │    SELECT ..., vec_distance_cosine(c.embedding, :q) AS dist
     │    FROM chunks c JOIN documents d ... WHERE <完整 ACL 条件>      -- ← 先过滤
     │    AND c.embedding IS NOT NULL
     │    ORDER BY dist LIMIT :k                                        -- ← 后排序取 top-k
     ─→ RRF 融合（k=60；向量缺失的 chunk 只在 BM25 路，自然退化单路）
     ─→ ACL 兜底断言（rerank 前：不该进模型的内容不进模型——P2-4 统一）
     ─→ 取 top-32 → rerank（bge-reranker-v2-m3，ONNX int8，喂 content 原文）
     ─→ 分数归一 [0,1]（min-max/clamp 双分支，ragflow 模式）
     ─→ 返回前二次 ACL 断言 → top-k（≤20，含 chunk_id/doc_id/title/page_no/score/dims/source）
```

要点：召回期不做用户阈值过滤（dify #35233 教训）；阈值只作用于归一后的最终分；**useful-early 语义**由"向量 BLOB 可空 + 先过滤后距离"自然成立——`embedding IS NULL` 的 chunk 只走 BM25 路，摄取中的文档即刻可搜（FR-1 阶段拆分）；**CPU 推理（query 嵌入 + rerank）放线程/进程池，绝不阻塞事件循环**；rerank 并发上限信号量保护；`top_k` 服务端硬上限 20。性能预算与 SLO（P95 ≤ 2s）见需求 NFR-8，M1 实测校准。

### 5.3 摄取管线与 worker（core/ingest.py + worker/runner.py）

任务状态机：`pending → leased → running → (done | failed)`；worker 心跳 5s、租约 60s，租约过期任务可被重认领；`attempts ≥ 3` 进 failed 留人工。断点粒度 = 阶段（各阶段幂等，重跑从上一完成阶段续）。SQLite 写竞争治理（NFR-9）：`busy_timeout` + worker 短事务分批提交 + 审计异步批量写。

阶段编排（**P0-4 拆分：index_fts 先于 embed，BM25 即刻可搜**）：

```
parse（docling→统一块结构；扫描件路由 MinerU；mojibake 质量门；TXT 编码探测）
→ chunk（结构感知切分 256–512 / Excel 按 sheet 行块（重复表头）；jieba 生成 content_seg）
→ index_fts（chunks + FTS 同一事务；文档状态 → searchable_lexical）
→ embed（bge-m3 分批 64，CPU 线程池；逐批 UPDATE embedding/embed_model）
→ index_vec（逐批就位；全部完成 → searchable_full）
→ quality（区分度检测 → quality_flags → LLM 关键词 → 回写 llm_keywords）
```

文档更新（覆盖，显式 doc_id）：新 version 重新走管线 → 新版本 chunk 就绪后单事务原子替换（旧版本 chunk 置 **tombstone** 保留可查，非物理删除——P1-9）；`fetch` 旧 chunk_id 返回"已被 v<N> 替代"提示。

### 5.4 区分度检测（core/quality.py，v0.2 修订）

- **向量拥挤度**：新 chunk 向量取**组织内** top-8 近邻，`mean(sim) > 阈值` 判拥挤——阈值用**绝对值 + 分位下限组合**（相对分位按定义恒标 ~25%，不可用；bge-m3 相似度分布偏高，初值 M1 真实语料重标定）；
- **词面通用度**：token 平均 IDF 低于**绝对阈值**（同上组合式）；新组织冷启动引用全局语料 IDF；
- **顺序依赖治理**：近邻结果依赖摄取顺序（先入库的无近邻）——**每周（或每 N 文档）全量重算** open 状态 flags；
- 触发 → `quality_flags` → LLM 生成关键词写 **`llm_keywords` 独立低权重列**（标来源，不与人工 `keywords`×5 混列）；
- **口径如实**：本机制只补 BM25 词面信号，**不是** Contextual Retrieval（后者改写后重新嵌入）——对外描述不得混淆；
- OneRAG 借鉴项落地处：parse 后 **mojibake 质量门**（正常字符比 <0.55 → 告警/重试/失败三档）。

### 5.5 鉴权、身份与组织上下文（domain/auth.py + mcp/server.py）

- **登录：企业 SSO（D16）**——token 验签（OIDC 优先，协议待需求待决-2 确认）→ 解析全局用户；**首次登录 JIT 建档**（`users` 表自动落库：id/username/display_name），管理员不建账号只配授权。
- **agent 代人检索（D8+D18）：委托 token（Token Exchange）**——agent 以用户 token 向 IdP 换取 `aud=knowledge-lattice` 的短期委托 token（`sub`=用户、`act`=agent 标识）；本系统验签后按 `sub` 过滤、`act` 写进审计；**拒绝 token 原样透传（MCP 规范禁止）与请求体权限字段**（一律忽略）。静态 token 仅限开发/测试（含 CI）。
- **组织上下文显式传递（P1-6）**：REST 用 `X-Org-Id` 请求头、MCP 在连接配置/工具调用中携带——**缺失即 400 报错，无隐式默认**（不取"第一个 membership"）；页面可记住上次选择，API 层不做默认；逐请求校验 `user_org_memberships`，非成员拒绝（§5.1 第 0 步）。
- MCP server 挂 60s 超时中间件（ragflow 同款纪律）。

### 5.6 权限管理：授权维护与真值源闭环（D16 v0.2）

维度授权按维度声明真值源（`grant_source`），维护闭环四件套：

1. **管理页单点配置**：组织管理员逐用户调整（查询时实时展开，改即生效——D6）；**同步维度（`sync:<system>`）管理页只读**、CSV 批量导入时跳过，防人工覆盖真值；
2. **批量导入/导出（主通道）**：CSV `username, org, dim_key, values...`；导入按「用户×组织」幂等全量替换、差异预览后确认；
3. **同步适配器（`adapters/grant_sync.py`）**：拉取源接口 + 显式映射表（"申报系统·VAT 申报岗 → tax_type=[VAT]"）+ 定时任务；**幂等全量替换、失败保留旧快照并告警**（不清空不放开）；写 `source='sync:...'` 与 `synced_at`；生产前把语义匹配维度（法人主体/国家）切只读同步；
4. **对账（漂移治理）**：季度导出 ↔ 业务岗位表映射比对 + 审计回放兜底；离职调岗经 HR/SSO 事件即时撤销（演进项）。

### 5.7 前端薄壳（web/）

三个页面（上传与任务 / 检索测试 / 管理），由 FastAPI 托管静态文件，无构建工具（原生 HTML/JS + 少量 fetch），**UI 永远是薄壳**——所有能力先有 API 契约（§6）再有页面；M2 管理面**先 API + 最小 UI**（完整页面后置，issue #31 P2）。交互原型见 `prototype/index.html`（mock 数据、浏览器直接打开），实现时以原型为信息结构基准逐页对接 REST。

## 6. 接口契约

### 6.1 MCP 工具（mcp/server.py，FastMCP）

```jsonc
// search —— 工具描述（写给 LLM）："检索企业知识库。缺私有信息（制度/手册/申报口径）时调用；
// query 越具体越好（含税种、区域、文档关键词）；返回结果自带 chunk_id 溯源，回答时请引用。"
{
  "name": "search",
  "input":  { "query": "string", "top_k": "int=8",
              "datasets": "string[]? = 限定知识库 id（缺省搜全部权限内文档）",
              "doc_filter": "string[]? = 文档 id 过滤" },
  "output": {
    "results": [{
      "chunk_id": "01J…", "doc_id": "01J…", "dataset": "VAT 实务库",
      "title": "2026 Q3 中国区 VAT 申报指南",
      "page_no": 12, "score": 0.87,
      "dims": { "region": "CN", "tax_type": "VAT" },
      "snippet": "…一般纳税人销售自产货物并提供安装服务的，应分别核算…"
    }],
    "notice": "vector_pending=false"   // useful-early：向量未就绪时 true，提示结果仅 BM25
  }
}

// upload —— "向知识库上传文档（agent 采集到的文件）。必须指定知识库与维度元数据，否则会被拒绝。"
{
  "name": "upload",
  "input":  { "file_ref": "string",           // 文件引用（agent 侧文件 ID/共享存储路径）或预签名上传 URL——不走 base64（P1-8）
              "filename": "string", "dataset": "ds:vat",
              "dimensions": { "region": ["CN"], "tax_type": ["VAT"] },   // 多值数组（D19）；值须在调用者授权内（P1-1）
              "doc_id": "string?",             // 覆盖更新显式携带（文档身份，P2-6）
              "title": "string?" },
  "output": { "doc_id": "01J…", "task_id": "01J…", "status": "queued", "version": 2 }
}

// fetch —— "按 chunk_id 取该块前后相邻的内容窗口（先搜后读）。旧版本块返回替代提示。"
{
  "name": "fetch",
  "input":  { "chunk_id": "01J…", "window": "int=2" },   // 前后各 N 块
  "output": { "chunks": [{ "chunk_id": "…", "seq": 41, "content": "…", "page_no": 12 }],
              "replaced_by": "chunk_id?（tombstone 时非空，指向新版本对应块）" }
}

// list_documents —— "列出权限内可见的知识库与文档及处理状态。先了解库里有什么，再决定搜什么。"
{
  "name": "list_documents",
  "input":  { "datasets": "string[]?", "status": "string?", "limit": "int=50" },
  "output": { "datasets": [{ "id": "ds:vat", "name": "VAT 实务库", "doc_count": 12 }],   // ← 全部统计按调用者权限计算（P1-8）
              "documents": [{ "doc_id": "01J…", "dataset": "ds:vat", "title": "…",
               "status": "searchable_full", "version": 1, "dims": {…}, "chunk_count": 143,
               "source": "user:u1 | agent:tax-copilot", "updated_at": "…" }] }
}
```

纪律：检索参数（权重/阈值/召回窗口）服务端固定，不暴露给 LLM（ragflow 反面教训）；`top_k ≤ 20` 服务端硬上限；工具描述动态注入的库/维度概况与一切统计**按调用者权限计算**（不可见文档的存在与数量不泄露）；`search` 返回块带 `source` 字段（agent 代传内容可识别——prompt injection 防御前置）。

### 6.2 REST 端点（api/）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/documents | 上传（multipart；校验目标库存在 + 必选维度齐全 + **可选值在本人授权内**，D5/D15/P1-1）；覆盖更新带 `doc_id` |
| DELETE | /api/documents/{id} | 删除文档（owner / org_admin，P2-6 补） |
| PATCH | /api/documents/{id}/dimensions | 修改文档维度（owner / org_admin；刷冗余投影，P2-6 补） |
| GET | /api/orgs | 当前用户可见的组织列表（系统管理员=全部；普通用户=其 membership） |
| POST | /api/orgs | 创建组织（系统管理员） |
| GET/PUT | /api/orgs/{id}/memberships | 组织成员列表 / 成员与角色管理（组织管理员） |
| GET | /api/orgs/{id}/grants/export | 导出该组织全部维度授权（CSV，对账与季度调整用） |
| POST | /api/orgs/{id}/grants/import | 批量导入授权（CSV；`dry_run` 参数返回差异预览；全量替换 语义，D16） |
| GET/POST | /api/datasets | 当前组织的知识库列表 / 新建（组织管理员） |
| PATCH/DELETE | /api/datasets/{id} | 库修改 / 删除（级联下线该库文档） |
| GET | /api/documents/{id} | 文档详情 + 状态 + quality_flags 概要 |
| GET | /api/documents/{id}/quality | 质量报告明细（低区分 chunk + 标注状态） |
| PATCH | /api/quality-flags/{id} | 人工补充 tags / 标记 ignored/resolved |
| POST | /api/search | 检索（检索测试页；参数同 MCP search，支持库过滤） |
| GET | /api/tasks | 任务列表（状态/进度/错误） |
| GET/POST | /api/dimensions | 维度列表 / 新建维度 |
| PATCH/DELETE | /api/dimensions/{id} | 维度修改（required/enabled）/ 删除 |
| GET/POST | /api/dimensions/{id}/values | 取值枚举 CRUD |
| GET | /api/users | 用户列表 |
| PUT | /api/users/{id}/grants | 授权全量替换（用户 × 维度 → 取值集合） |
| POST | /api/users/{id}/token | 签发/轮换静态 token |

所有端点（除登录）要求 Bearer token；写操作落 audit_events。

### 6.3 与术语层（glossary-agent）的工具组集成（D17）

- **消费侧形态**：deepagents 并挂两个 MCP server——本系统 `search` / `upload` / `list_documents` + glossary-agent 的 `lookup_terms`（与数据字典活查询）。职责边界：本系统只管文档知识，术语归一与黑话定义不在检索范围（agent 侧前置识别/lookup 处理后再调本系统检索）。
- **演进缝（不进 MVP）**：如需单端点，本系统可加载术语库**运行时投影**（Git YAML → AC 自动机 + FTS 内存索引），以 `lookup_terms` 工具统一暴露——真值源与 PR 治理仍在术语库 Git 仓，本系统只持可刷新投影（`adapters/` 预留 `glossary_loader.py` 位）。
- **明确不做**：表名字段名/数据字典类查询（真值在源系统、高频变）由术语侧 MCP 活查询直连，本系统不镜像这类数据；L0 常驻核心术语表是术语库构建期导出物（进 agent system prompt），与本系统无关。

## 7. 技术选型与依赖清单

| 依赖 | 用途 | 备注 |
|---|---|---|
| Python 3.11+ / uv | 运行时与包管理 | |
| fastapi + uvicorn | 控制面 REST | |
| fastmcp | MCP server | OneRAG 模块结构参考 |
| docling | 解析（docx/pptx/xlsx/html/pdf 原生） | 进程内库；MIT 代码 + 模型权重 license 风险标注（NFR-7） |
| jieba | 中文预分词 | 中英混排效果 M1 实测（风险登记） |
| FlagEmbedding（或 sentence-transformers）+ onnxruntime | bge-m3 嵌入 + bge-reranker-v2-m3 重排，进程内 | **钉版本**记录进 chunk.embed_model；CPU 分批推理 + **int8 量化**（NFR-8） |
| sqlite-vec | **距离函数**（`vec_distance_cosine` 等标量函数作用于 BLOB 列，P0-1；非 vec0 虚表 KNN） | 一期 ~10 万 chunk 实测（NFR-2） |
| pydantic v2 | 实体与配置 | |
| python-ulid | 主键 | 时间有序，利于排序与溯源可读 |
| httpx | 内部网关客户端 | OpenAI 兼容 |
|（M3）ragas + deepeval + pytest | 评测与门禁 | judge 走内部网关 |

排除项（明确不引入）：消息队列（tasks 表轮询 + IPC 唤醒足够）、ORM（SQL 收口在 store 层手写，DDL 即文档）、前端构建链（静态页）。

## 8. 里程碑任务分解

**M0（第 1 周）——骨架端到端 + schema 全量落**
1. 项目脚手架（uv、config、db 迁移框架，§4 全部 DDL 一次性落——含整数主键/分列 FTS/触发器/审计触发器）
2. 摄取最小链：docling 解析 → 结构切分（含 content_seg 分词）→ **index_fts 入库（BM25 即刻可搜）** → 嵌入分批补齐（P0-4 阶段拆分从 M0 起就是结构）
3. 检索最小链：**BM25 单路 + 完整 ACL WHERE**（组织隔离 + 维度编译器 v1——括号化 builder 从第一天就是 AST）
4. FastMCP `search` + REST `POST /api/search` + 静态页壳
5. 验收：deepagents 经 MCP 一次带 chunk_id 的检索（**委托 token 链路**）；mock 用户维度过滤生效
6. **并行推进（阻塞项前置，issue #31 P1-7）**：待决-2（SSO 协议确认）与待决-3（agent 委托 token——Token Exchange 方案验证：`aud` 绑定/短 TTL/`act`）在 M0 期间敲定，不再压 M2

**M1（第 2~3 周）——完整配方 + 维度权限全链 + 区分度环 + 度量前移**
1. jieba 分列 FTS（content_seg/keywords/tags + 触发器 + MATCH 转义）+ 双路（先过滤后距离）+ RRF + rerank（候选 32，ONNX int8）+ 分数归一
2. LLM 关键词增强**条件触发**接入（短 query/中英混排；网关超时降级）
3. 维度 ACL：上传页选维度（必选校验 + **可选值限定本人授权内**）、授权数据、编译器完整（括号化 builder/owner 兜底/无授权短路/**多值语义**）
4. 区分度检测（绝对阈值 + 定期重算）+ LLM 兜底（独立 llm_keywords 列）+ 质量报告页 + 人工标注回写
5. 真实文档批量上线（依赖待决-1；先用合成样例）+ **小型黄金集（几十条）+ Recall@k/MRR 前移** + P95 延迟基线
6. 验收：**越权矩阵全绿**（§9 扩充版）；20~50 条真实中英 query 人工标注；区分度误报抽查

**M2（第 4~6 周）——生产化（减负版）**
1. worker 子进程化（心跳/租约/重试/断点续跑）+ IPC 唤醒 + SQLite 写竞争治理（busy_timeout/短事务/审计异步）
2. SSO/JIT 建档对接（协议已在 M0 敲定）+ 委托 token 全面落地（act 进审计）
3. 管理面**先 API + 最小 UI**（组织/知识库/维度/授权含批量导入；完整页面后置）
4. 文档版本化覆盖重索引（tombstone + fetch 替代提示）+ 删除级联
5. 备份快照 + 恢复演练；哈希链审计（按需）
6. 验收：杀 worker 不丢任务；审计回放（含 act）；tombstone fetch；恢复演练通过；跨组织隔离全绿

**M3（第 7~8 周）——评测防线**
1. 完整黄金集（ragas 合成 + 人工修正流；M1 小型集扩容）
2. 响应层 faithfulness/answer_relevancy + 检索层指标固化
3. judge 双语 prompt + ~50 条人工双评校准
4. deepeval pytest 门禁进 CI（预人为注入回归验证门禁有效性）
5. 在线引用锚点抽样脚本

依赖关系：M1.3 依赖 M0.3；M1.4 依赖 M1.1；M0.6（SSO/token 确认）阻塞 M0.5 验收的完整形态；M2 依赖 M0.6 结论；M3 扩量依赖待决-1（真实语料）。

## 9. 测试策略

- **单元**：ACL 编译器（**括号化结构**/多值语义/短路/owner 受外层约束/**可选维度不生成条件**/投影一致性——**AST 断言而非字符串比对**）、RRF 与归一、切分边界（表格整块/超长段落/**Excel 行块含表头**）、维度校验、FTS5 MATCH 转义（注入用例）、Tombstone fetch；
- **集成**：摄取→检索端到端（SQLite 临时库，含 searchable_lexical 中间态检索）、版本化替换原子性、任务租约重认领、触发器同步（删改无幽灵命中）；
- **越权用例集（M1/M2 核心资产，issue #31 §3.7 扩充）**：矩阵化构造——用户授权组合 × 文档维度组合（含**多值文档维度**）× **库过滤（dataset 限定下 owner 分支不得漏出他库文档——P0-2 回归）** × **可选维度空值** × **新增必选维度未回填/停用维度放宽** × **移出组织后重加（授权不复活）** × **跨组织** × **MCP 统计信息（doc_count 不泄露不可见文档）**——断言检索结果/MCP 返回/引用/统计四个面均无越权，进 CI 常跑；
- **评测**：M1 小型黄金集（Recall@k/MRR）→ M3 完整门禁（§8）；
- **性能抽测**：~10 万 chunk 模拟数据下的检索延迟 P95（含 ACL 过滤后距离扫描）、rerank 并发、无 GPU 嵌入吞吐曲线（M1/M2 各一次，结论驱动升级缝是否触发——NFR-2/8）。

## 10. 风险的工程对策（对应需求 §9 风险登记）

| 风险 | 工程对策 | 触发点 |
|---|---|---|
| 无 GPU 嵌入吞吐 | 阶段拆分（index_fts 先行）+ 分批 64 + int8 量化；`config.py` 预留 embedding_model 配置位（e5-small 384 维备选，注意维度不兼容需全量重嵌决策） | M2 实测吞吐曲线后决策 |
| jieba 中英混排 | 检索层 tokenizer 独立模块（可换 trigram/自定义词表）；M1 真实 query 标注集是判据 | M1 验收 |
| sqlite-vec BLOB 扫描边界 | repo 接口已隔离向量路；pgvector 适配器为升级缝首个目标 | 一期 10 万 chunk P95 超标时（NFR-2/8） |
| dims_json json_each 性能 | 维度物化列迁移预案（schema v2，§5.1） | 十万级实测 |
| P95 延迟超标 | NFR-8 全套（候选 32/ONNX int8/条件增强/线程池）；逐项降级预案 | M1 基线 |
| 区分度失真 | 绝对阈值 + 分位下限；定期全量重算；组织内近邻；ignored 沉淀负样本 | M1 抽查 + 周期重算 |
| 权限漂移（自建授权表 vs 业务实际，D16） | 季度批量对账 + 审计回放；grant_sync 适配器；生产前语义匹配维度切只读同步 | 季度对账；高敏文档从严 |
| 模型权重 license | embed/parser 模型清单进 `config.py` 单一登记处，商用核查逐卡打勾 | 商用前（NFR-7） |
