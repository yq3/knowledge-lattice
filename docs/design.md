# knowledge-lattice 方案设计

> 版本：v0.1（对应需求文档 v0.1）
> 日期：2026-10-16
> 前置阅读：[requirements.md](./requirements.md)（本文所有 FR/NFR/D 编号均指向需求文档）
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

**部署形态（NFR-1）**：`knowledge-lattice` 主进程 ×1（内含 worker 子进程）+ `lattice.db` ×1 + `data/objects/` 目录 ×1。无消息队列、无独立向量库、无嵌入服务容器——它们分别是 tasks 表轮询、sqlite-vec 虚表、进程内 bge-m3。worker 经 IPC 被唤醒 + 兜底轮询（anything-llm 的最小进程隔离样板：OOM 只杀 worker）。

**并发模型**：SQLite WAL 模式（多读单写）。检索（读）不受摄取（写）阻塞；写串行由 tasks 表单消费者保证。数百用户的检索并发 = 只读连接池，瓶颈预估在 rerank 计算（§5.2 缓解）。

**升级缝（NFR-5 落点）**：存储（repository 接口后换 pgvector/milvus）、嵌入与重排（进程内 → TEI 容器，接口不变）、解析（docling → MinerU api_server，路由表驱动）、多组织（org_id 已贯穿全部表，默认常量 `org:default`）。

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
  id          TEXT PRIMARY KEY,      -- ULID
  org_id      TEXT NOT NULL REFERENCES orgs(id),
  key         TEXT NOT NULL,         -- region / tax_type
  name        TEXT NOT NULL,         -- 作业区域 / 税种
  required    INTEGER NOT NULL DEFAULT 1,  -- 必选：上传时强制选值（D5）
  enabled     INTEGER NOT NULL DEFAULT 1,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP,
  UNIQUE(org_id, key)
);

CREATE TABLE dimension_values (      -- 维度取值枚举
  id           TEXT PRIMARY KEY,
  dimension_id TEXT NOT NULL REFERENCES dimensions(id) ON DELETE CASCADE,
  value        TEXT NOT NULL,        -- CN / OVERSEAS / VAT / CIT
  label        TEXT NOT NULL,        -- 中国区 / 海外区 / 增值税 / 企业所得税
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

CREATE TABLE user_dimension_grants ( -- 授权作用域 = 用户 × 组织（D7）：经 dimension 隐式挂组织
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dimension_id TEXT NOT NULL REFERENCES dimensions(id) ON DELETE CASCADE,
  value        TEXT NOT NULL,        -- 同一用户在不同组织（不同维度体系）的授权互不相干
  granted_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, dimension_id, value)
);

-- ============ 文档（FR-1） ============
CREATE TABLE documents (
  id             TEXT PRIMARY KEY,   -- ULID
  org_id         TEXT NOT NULL REFERENCES orgs(id),
  dataset_id     TEXT NOT NULL REFERENCES datasets(id),  -- 归属知识库（D15）
  title          TEXT NOT NULL,
  source_uri     TEXT,               -- 上传来源（user:<id> / agent:<name>）
  content_hash   TEXT NOT NULL,      -- 内容哈希去重 + 更新识别
  mime_type      TEXT NOT NULL,
  page_count     INTEGER,
  parser         TEXT NOT NULL,      -- docling | mineru
  status         TEXT NOT NULL,      -- uploaded|parsing|chunked|embedded|indexed|failed
  owner_user_id  TEXT NOT NULL REFERENCES users(id),  -- owner 恒可见（FR-4 兜底）
  raw_object_key TEXT NOT NULL,      -- 对象目录键（canonical 真相锚点）
  error          TEXT,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     TIMESTAMP
);
CREATE INDEX idx_documents_hash ON documents(org_id, content_hash);

CREATE TABLE document_dimensions (   -- 文档维度（单值 per dimension，D4/D5）
  doc_id       TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  dimension_id TEXT NOT NULL REFERENCES dimensions(id) ON DELETE CASCADE,
  value        TEXT NOT NULL,
  PRIMARY KEY (doc_id, dimension_id)
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

-- ============ 块与索引（FR-1/2/3） ============
CREATE TABLE chunks (
  id            TEXT PRIMARY KEY,    -- ULID（引用溯源的确定性锚点）
  doc_id        TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,    -- 文档内序号
  content       TEXT NOT NULL,       -- 正文原文（rerank 输入口径）
  token_count   INTEGER,
  heading_path  TEXT,                -- 结构感知切分的标题层级
  page_no       INTEGER,
  sheet_name    TEXT,                -- Excel 切分专用
  bbox_json     TEXT,
  keywords      TEXT NOT NULL DEFAULT '',  -- jieba 预分词 + 标注词（空格连接，进 FTS5）
  tags          TEXT NOT NULL DEFAULT '',  -- 人工/LLM 标注标签（加权更高）
  embed_model   TEXT NOT NULL,       -- 钉版本：bge-m3@<rev>（D12）
  dims_json     TEXT NOT NULL,       -- 文档维度冗余投影 {"region":"CN","tax_type":"VAT"}
  content_sha   TEXT,                -- 区分度检测缓存（内容指纹，重检跳过）
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_chunks_doc ON chunks(doc_id, seq);

-- FTS5：列权重体现 keywords/tags 的检索加权（FR-2/3）
--   bm25() 权重：content 1.0 / keywords 5.0 / tags 8.0（ragflow important_kwd×5 模式）
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  content, keywords, tags,
  content='chunks', content_rowid='rowid', tokenize='unicode61'
);
-- 注：写入前由 tokenizer.py 以 jieba 预分词生成 keywords（ES 无服务端中文分词的同构方案）

-- sqlite-vec 虚表（暴力扫描，十万级边界由 NFR-2 风险项跟踪）
CREATE VIRTUAL TABLE vec_chunks USING vec0(
  chunk_id TEXT PRIMARY KEY,
  embedding float[1024]              -- bge-m3 输出维度
);

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
-- append-only 触发器（禁 UPDATE/DELETE/TRUNCATE）与定长清理，上线时补齐
```

设计说明：

- **组织与库的隔离纪律**：一切检索/列表 SQL 的第一条件是 `org_id = :user_org`（跨组织零可见），库过滤（`dataset_id IN (...)`）是组织内的可选收窄；维度授权与维度定义都在组织作用域内解析。
- **维度冗余的取舍**：`chunks.dims_json` 是 `document_dimensions` 的投影，检索 SQL 先按 JSON 解析编译成常量条件（§5.1），避免热路径多表 JOIN；文档维度变更时由服务层同步刷投影（UPDATE，不重嵌——D6）。
- **FTS5 中文**：`unicode61` 分词器只做兜底，真正的中文匹配依赖写入时的 jieba 预分词进 `keywords` 列（中英混排词以空格连接，英文词原样保留——M1 实测验证）。
- **无独立 vector 表外键**：`vec_chunks.chunk_id` 与 `chunks.id` 逻辑关联，删除文档时由 repo 层两段式清理（先 chunks 后 vec，同事务）。

## 5. 关键设计

### 5.1 维度 ACL 编译器（core/acl.py）

输入：`user_id` + 请求携带的组织上下文 `org_id`；输出：可下推进召回 SQL 的 WHERE 片段。逻辑：

1. **成员关系校验**（第 0 步）：查 `user_org_memberships`——非本组织成员（且非系统管理员）直接拒绝请求，不存在"默认可见"；
2. 组织隔离：`d.org_id = :org_id`（跨组织零可见，含 owner 判定）；
3. 查该用户**在本组织**的 `user_dimension_grants`（join `dimensions` 按 org 过滤）得 `{dim_key: [values...]}`（查询时实时读取——人员变更即时生效，D6）；维度 key 集合取自该组织 `dimensions`（各组织维度体系不同，D7）；
4. 对每个 `enabled` 维度编译一个「文档该维度值 ∈ 用户授权集」的条件；**无授权值的维度 → 整体不可见**（AND 语义的严格实现，D5）；
5. owner 兜底以 `OR d.owner_user_id = :uid` 合并（owner 判定同样限定本组织）。

编译产物（示意，语句由 repo 层拼进召回 SQL，不是应用层 post-trim）：

```sql
-- 组织 org:tax 内，用户仅有 region=[CN, OVERSEAS]、tax_type=[VAT]；两维度均必选
SELECT c.* FROM chunks c JOIN documents d ON d.id = c.doc_id
WHERE d.org_id = 'org:tax'
  AND (
    json_extract(c.dims_json, '$.region') IN ('CN', 'OVERSEAS')
    AND json_extract(c.dims_json, '$.tax_type') IN ('VAT')
  ) OR (d.org_id = 'org:tax' AND d.owner_user_id = :uid)
-- 可选的库过滤（D15）：AND d.dataset_id IN ('ds:vat', 'ds:intl')
-- 无授权维度（如 tax_type=[]）编译为 FALSE，整个 AND 链短路 → 全库不可见
```

性能注：`dims_json` 的 `json_extract` 在百万 chunk 下不可接受时，升级为按维度生成物化列（`dim_region TEXT` 等）+ 索引——迁移已预留（schema 版本 +1），M1 实测后决定。rerank 前兜底断言照抄需求红线：进 prompt 的每个 chunk 二次校验（防御纵深第二层）。

### 5.2 检索管线（core/retrieve.py）

```
query ─→ LLM 关键词增强（内部网关，中英混排漏召回的补词）
     ├─→ FTS5 BM25 路：bm25(chunks_fts, query_kw, weights=[1.0, 5.0, 8.0]) + ACL WHERE
     ├─→ 向量路：query embed(bge-m3) → vec_chunks kNN（k=1024）+ ACL WHERE
     ─→ RRF 融合（k=60，默认；0.7/0.3 加权留作配置旋钮但需同尺度校准）
     ─→ 取 top-64 → rerank（bge-reranker-v2-m3，喂 content 原文）
     ─→ 分数归一 [0,1]（min-max/clamp 双分支，ragflow NormalizeRerankScores 模式）
     ─→ ACL 兜底断言 → 返回 top-k（含 chunk_id/doc_id/title/page_no/score/dims）
```

要点：召回期不做用户阈值过滤（dify #35233 教训）；阈值只作用于归一后的最终分；`useful-early` 降级——`vec_chunks` 中该文档无向量时自动退化为 BM25 单路（摄取进行中的文档即刻可搜，FR-1）；rerank 是同步路径最重的一段，进程内 batch 推理 + 结果 LRU 无意义（查询各异），并发上限用信号量保护（NFR-2 数百用户并发的实际瓶颈位）。

### 5.3 摄取管线与 worker（core/ingest.py + worker/runner.py）

任务状态机：`pending → leased → running → (done | failed)`；worker 心跳 5s、租约 60s，租约过期任务可被重认领；`attempts ≥ 3` 进 failed 留人工。断点粒度 = 阶段（parse/chunk/embed/index 各自幂等，重跑从上一完成阶段续）。

阶段编排：

```
parse（docling→统一块结构；PDF 扫描件特征路由 MinerU） 
→ chunk（结构感知切分 256–512 / Excel 按 sheet 行块）
→ embed（bge-m3 进程内，分批 64；每 chunk 记 embed_model）
→ index（chunks + FTS5（jieba 预分词）+ vec 同事务写入；文档状态 indexed）
→ quality（区分度检测 → quality_flags → LLM 关键词 → 回写 auto_keywords/keywords）
```

quality 在 index **之后**异步执行：不阻塞「可搜」时间点（useful-early 语义延伸）。文档更新（重传覆盖）：content_hash 变更 → 创建 reindex 任务 → 新 chunk 全部就绪后单事务原子替换（旧 chunks/vec/fts 同事务删除）。

### 5.4 区分度检测（core/quality.py）

- **向量拥挤度**：新 chunk 向量在库内取 top-8 近邻，`mean(sim) > 0.82`（初值）判拥挤——它与太多不相关内容相似，缺乏辨识度；
- **词面通用度**：jieba 分词后计算 chunk 内 token 的库级 IDF 均值，低于语料 P25 分位判通用——BM25 路也拉不开；
- 两信号任一触发 → `quality_flags`（reason 记录）→ LLM（内部网关）生成 3–5 关键词 + 一句定位语回写；上传完成页聚合展示（FR-3 的质量报告）；
- 阈值是初值，M1 用真实语料校准（表格/目录段天然低区分，容错靠「可忽略」交互不靠阈值完美）；
- OneRAG 借鉴项落地处：解析阶段的 **mojibake 质量门**（正常字符比 <0.55 → 告警/重试/失败三档）加在 parse 之后，与区分度检测互不影响。

### 5.5 鉴权、身份与组织上下文（domain/auth.py + mcp/server.py）

- **登录：企业 SSO（D16）**——token 验签（OIDC 优先，协议待需求待决-2 确认）→ 解析全局用户；**首次登录 JIT 建档**（`users` 表自动落库：id/username/display_name），管理员不建账号只配授权。静态 token（`users.token_hash`）降级为开发/测试模式与 agent 服务场景的鉴权方式。
- **组织上下文**：token 解析出全局用户后，请求须携带目标组织——REST 用 `X-Org-Id` 请求头（缺省取用户首个 membership），MCP 在连接配置/工具调用中携带；服务端逐请求校验 `user_org_memberships`，非成员拒绝（§5.1 第 0 步）；用户可属多组织，**角色与维度授权按组织独立**（D7）。
- agent 代人检索（D8）：deepagents 侧配置用户 token（或 agent 网关签发的代理 token——**形态待与 agent 服务约定，需求待决-3**），本系统只做 `token → user → membership → 维度展开`，不感知 agent 逻辑。
- MCP server 挂 60s 超时中间件（ragflow 同款纪律）。

### 5.7 权限管理：自建授权表的维护闭环（D16）

维度授权是知识库本地资产（不联邦业务系统），维护闭环四件套：

1. **管理页单点配置**：组织管理员在授权面板逐用户调整（查询时实时展开，改即生效——D6）；
2. **批量导入/导出（主通道）**：CSV 模式 `username, org, dim_key, values...`；初次授权与季度调整经此完成；导入走"全量替换该用户×组织"语义（幂等），差异预览后确认；
3. **对账（漂移治理）**：季度导出授权表 ↔ 业务系统岗位表按映射规则人工比对；审计回放（谁在何时看过什么）作为事后兜底；
4. **同步适配器（演进缝，默认禁用）**：`adapters/grant_sync.py` 预留——拉取源接口 + 显式映射表（如"申报系统·VAT 申报岗 → tax_type=[VAT]"）+ 定时任务，写同一张 `user_dimension_grants`；未来企业出现权限中心时启用，核心零改动。

### 5.6 前端薄壳（web/）

三个页面（上传与任务 / 检索测试 / 管理），由 FastAPI 托管静态文件，无构建工具（原生 HTML/JS + 少量 fetch），**UI 永远是薄壳**——所有能力先有 API 契约（§6）再有页面。交互原型见 `prototype/index.html`（本次同步产出，mock 数据、浏览器直接打开），实现时以原型为信息结构基准逐页对接 REST。

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
  "input":  { "filename": "string", "content_b64": "string", "dataset": "ds:vat",
              "dimensions": { "region": "CN", "tax_type": "VAT" },
              "title": "string?" },
  "output": { "doc_id": "01J…", "task_id": "01J…", "status": "queued" }
}

// list_documents —— "列出权限内可见的知识库与文档及处理状态。先了解库里有什么，再决定搜什么。"
{
  "name": "list_documents",
  "input":  { "datasets": "string[]?", "status": "string?", "limit": "int=50" },
  "output": { "datasets": [{ "id": "ds:vat", "name": "VAT 实务库", "doc_count": 12 }],
              "documents": [{ "doc_id": "01J…", "dataset": "ds:vat", "title": "…",
               "status": "indexed", "dims": {…}, "chunk_count": 143, "updated_at": "…" }] }
}
```

纪律：检索参数（权重/阈值/召回窗口）服务端固定，不暴露给 LLM（ragflow 反面教训）；工具描述动态注入文档集概况（库内按维度统计）。

### 6.2 REST 端点（api/）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/documents | 上传（multipart；服务端校验目标库存在 + 必选维度齐全，D5/D15） |
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

## 7. 技术选型与依赖清单

| 依赖 | 用途 | 备注 |
|---|---|---|
| Python 3.11+ / uv | 运行时与包管理 | |
| fastapi + uvicorn | 控制面 REST | |
| fastmcp | MCP server | OneRAG 模块结构参考 |
| docling | 解析（docx/pptx/xlsx/html/pdf 原生） | 进程内库；MIT 代码 + 模型权重 license 风险标注（NFR-7） |
| jieba | 中文预分词 | 中英混排效果 M1 实测（风险登记） |
| FlagEmbedding（或 sentence-transformers） | bge-m3 嵌入 + bge-reranker-v2-m3 重排，进程内 | **钉版本**记录进 chunk.embed_model；CPU 分批推理 |
| sqlite-vec | 向量虚表 | 无 ANN，暴力扫描边界 M1 实测 |
| pydantic v2 | 实体与配置 | |
| python-ulid | 主键 | 时间有序，利于排序与溯源可读 |
| httpx | 内部网关客户端 | OpenAI 兼容 |
|（M3）ragas + deepeval + pytest | 评测与门禁 | judge 走内部网关 |

排除项（明确不引入）：消息队列（tasks 表轮询 + IPC 唤醒足够）、ORM（SQL 收口在 store 层手写，DDL 即文档）、前端构建链（静态页）。

## 8. 里程碑任务分解

**M0（第 1 周）——骨架端到端 + schema 全量落**
1. 项目脚手架（uv、config、db 迁移框架，§4 全部 DDL 一次性落——含 orgs/datasets 启用）
2. 摄取最小链：docling 解析 → 结构切分 → bge-m3 嵌入（同步占位，M2 再异步化）→ chunks/fts/vec 入库（上传入指定库）
3. 检索最小链：向量单路 + ACL WHERE（组织隔离 + 维度编译器 v1）
4. FastMCP `search` + REST `POST /api/search` + 静态页壳
5. 验收：deepagents 经 MCP 一次带 chunk_id 的检索；mock 用户维度过滤生效

**M1（第 2~3 周）——完整配方 + 维度权限全链 + 区分度环**
1. jieba 预分词 + FTS5 双路 + RRF + rerank + 分数归一
2. LLM 关键词增强（内部网关）接入检索前端
3. 维度 ACL：上传页选维度（必选校验）、授权数据、编译器完整（owner 兜底/无授权短路）
4. 区分度检测 + LLM 兜底 + 质量报告页 + 人工标注回写（FR-3 完整闭环）
5. 真实文档批量上线（依赖待决-1；先用合成样例）
6. 验收：越权三面全绿；20~50 条真实中英 query 人工标注；区分度误报抽查

**M2（第 4~6 周）——生产化**
1. worker 子进程化（心跳/租约/重试/断点续跑）+ IPC 唤醒
2. 管理面：组织管理（系统管理员）、知识库管理、维度配置页、用户授权页、任务页、审计查询
3. agent 代人身份：token 约定落地（待决-2）、MCP 鉴权中间件、审计覆盖查询级
4. 文档更新覆盖重索引（原子替换）+ 删除级联
5. 分批摄取 + useful-early 降级实测（无 GPU 嵌入吞吐曲线）
6. 验收：杀 worker 不丢任务；审计回放完整检索；更新原子性

**M3（第 7~8 周）——评测防线**
1. 黄金集构建器（ragas 合成 + 人工修正流）
2. 检索层 Recall@k/MRR（ID-based 集合运算）+ 响应层 faithfulness/answer_relevancy
3. judge 双语 prompt + ~50 条人工双评校准
4. deepeval pytest 门禁进 CI（预人为注入回归验证门禁有效性）
5. 在线引用锚点抽样脚本

依赖关系：M1.3 依赖 M0.3；M1.4 依赖 M1.1（检测需要双路就位才有意义）；M2.5 依赖 M2.1；M3 全部依赖待决-1（真实语料）。

## 9. 测试策略

- **单元**：ACL 编译器（AND/短路/owner 合并/投影一致性）、RRF 与归一、切分边界（表格整块/超长段落）、维度校验；
- **集成**：摄取→检索端到端（SQLite 临时库）、更新原子替换、任务租约重认领；
- **越权用例集（M1/M2 核心资产）**：矩阵化构造「用户授权组合 × 文档维度组合」+ **跨组织用例**（A 组织用户/agent 对 B 组织库与文档零可见），断言检索结果/MCP 返回/引用三个面均无越权——进 CI 常跑；
- **评测**：M3 门禁（§8）；
- **性能抽测**：百万 chunk 模拟数据下的检索延迟、sqlite-vec 扫描边界、rerank 并发（M1/M2 各一次，结论驱动升级缝是否触发）。

## 10. 风险的工程对策（对应需求 §9 风险登记）

| 风险 | 工程对策 | 触发点 |
|---|---|---|
| 无 GPU 嵌入吞吐 | 分批 64 + useful-early；`config.py` 预留 embedding_model 配置位（e5-small 384 维备选，注意维度不兼容需全量重嵌决策） | M2.5 实测吞吐曲线后决策 |
| jieba 中英混排 | 检索层 tokenizer 独立模块（可换 trigram/自定义词表）；M1 真实 query 标注集是判据 | M1 验收 |
| sqlite-vec 边界 | repo 接口已隔离向量路；pgvector 适配器为升级缝首个目标 | 检索延迟 P95 不可接受时 |
| dims_json json_extract 性能 | 物化列迁移预案（schema v2，§5.1） | 百万 chunk 实测 |
| 区分度误报 | 阈值进 config 可调；ignored 状态沉淀负样本供校准 | M1 抽查 |
| 权限漂移（自建授权表 vs 业务实际，D16） | 季度批量对账 + 审计回放；grant_sync 适配器留缝（权限中心出现时启用） | 季度对账流程；高敏文档从严选维度 |
| 模型权重 license | embed/parser 模型清单进 `config.py` 单一登记处，商用核查逐卡打勾 | 商用前（NFR-7） |
