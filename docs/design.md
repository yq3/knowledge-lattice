# knowledge-lattice 方案设计

> 版本：v0.4（2026-10-17 冻结版：吸收 [issue #33](https://github.com/yq3/lab/issues/33) 全量评审——P0×2【权限状态进计算/版本在用制闭环】+ P1×12 + P2×50 + T1~T19；**冻结后设计仅在决策变化时修改**，实现问题走测试与 issue）
> 日期：2026-10-16 初稿 → v0.2（#31）→ v0.3（#32）→ v0.4（#33，冻结版）
> 前置阅读：[requirements.md](./requirements.md)（本文所有 FR/NFR/D 编号均指向需求文档 v0.4）
> 调研依据：[enterprise-rag 调研](../../research/enterprise-rag/)，参考架构基线 `blog/10-build-kb-for-agent.md`

---

## 1. 设计总览：需求 → 方案的映射

| 需求 | 方案落点 | 本文章节 |
|---|---|---|
| FR-1 摄取 | 单进程 + worker 子进程 + 任务表；docling 进程内解析 | §2 / §5.3 |
| FR-2 检索 | SQLite 内双路（FTS5 + sqlite-vec）→ RRF → 进程内 rerank | §5.2 |
| FR-3 区分度反馈环 | 摄取管线尾部 quality 阶段 + 质量报告接口 | §5.4 |
| FR-4 维度权限 | 维度模型五表 + ACL 编译器（查询时展开，引擎内下推） | §4 / §5.1 |
| FR-5 接口面 | FastMCP 四工具（search/upload/fetch/list_documents）+ REST + 静态薄壳前端 | §6 |
| FR-6/7 治理与评测 | audit_events 触发器；评测脚本集（黄金集 + 门禁） | §4 / §9 |
| NFR-1 零中间件 | 全部组件进程内/文件级，无外部常驻服务 | §2 |
| NFR-5 演进缝 | repository 接口 + 配置级切换点清单 | §7 |
| **issue #31 评审修订（v0.2）** | P0 五项修复（检索侧）+ 权限真值源 + 性能运维 | §4 / §5.1~5.3 / §5.6 / §8~10 |
| **issue #32 评审修订（v0.3）** | 写路径安全 P0×4 + P1×9 | §4 / §5.1~5.3 / §5.6 / §8~10 |
| **issue #33 收口修订（v0.4，冻结）** | 权限状态进计算（P0-1）/ 版本在用制闭环（P0-2）/ 外键动作补齐 / 凭证流闭环 / 审计 outbox / 可信子系统约束 / REST 路径统一 / M0a-M0b 拆分 / T1~T19 | 全文（决策汇总见需求 D22） |

## 2. 进程与部署架构

```
 ┌─────────────────────┐        ┌──────────────────────────┐
 │ 前端薄壳（静态页）    │        │ deepagents（企业内服务）    │
 │ 上传/检索/管理        │        │ agent 循环住在这里          │
 └─────────┬───────────┘        └────────────┬─────────────┘
           │ REST                             │ MCP（HTTP，委托 token / 可信子系统——D18）
           ▼                                  ▼
 ┌───────────────────────────────────────────────────────────┐
 │ knowledge-lattice 主进程（FastAPI，单进程）                    │
 │  · REST 控制面：upload / tasks / search / admin              │
 │  · FastMCP server：search / upload / fetch / list_documents │
 │  · 检索管线（同步）：双路召回（ACL 引擎内下推）→RRF→ACL 断言      │
 │ │    →rerank→返回前二次断言→溯源返回（P2-4 顺序）              │
 │  · 维度 ACL 编译器：委托 token →（含过期/停用的）授权展开 → SQL WHERE   │
 │  · 任务调度：写 tasks 表 + 唤醒 worker；审计写入                │
 └────────┬────────────────────────────────────┬──────────────┘
          │ 子进程 IPC（unix socket / stdin）    │ 读写
 ┌────────▼──────────────┐          ┌───────────▼──────────────┐
 │ 摄取 worker 子进程      │          │ SQLite（data/lattice.db）  │
 │ 解析→切分→index_fts→嵌入    │          │ 元数据 + FTS5 + 向量BLOB   │
 │ →index_vec→质量检测        │          │ WAL 模式（多读单写）        │
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

**并发模型（NFR-9）**：SQLite WAL 模式（多读单写）。检索（读）不受摄取（写）阻塞；写竞争治理：`busy_timeout` + worker 短事务分批提交 + **审计按月分库后与业务写天然隔离**（FR-6）。数百用户检索并发的实际瓶颈在 rerank 计算（§5.2 缓解：候选 32 / ONNX int8 / 信号量）。

**备份恢复（NFR-10）**：SQLite `VACUUM INTO` / online backup 定时快照 + `data/objects/` 一并备份；RPO ≤ 24h / RTO ≤ 4h（POC 目标）；恢复演练进 runbook。

**升级缝（NFR-5 落点）**：存储（repository 接口后换 pgvector/milvus，触发阈值为 100 万 chunk 或 P95 超标——NFR-2）、嵌入与重排（进程内 → TEI 容器，接口不变）、解析（docling → MinerU api_server，路由表驱动）、授权同步（grant_sync 适配器启用只读同步维度——D16）。

## 3. 代码模块划分

```
knowledge_lattice/
├── app.py                  # FastAPI 入口：装配路由/MCP/DB/worker
├── config.py               # 全部配置（模型版本、阈值、路径、网关地址）
├── api/
│   ├── upload.py           # POST /api/orgs/{org}/documents（校验库+维度+授权内）+ POST /api/uploads（凭证签发）+ PUT /api/uploads/{id}
│   ├── datasets.py         # 知识库 CRUD（组织内，D15）
│   ├── orgs.py             # 组织 CRUD 与成员管理（系统管理员，D7）
│   ├── tasks.py            # GET /api/orgs/{org}/tasks（+ cancel）、文档状态
│   ├── search.py           # POST /api/search（检索测试页用，支持库过滤）
│   └── admin.py            # 维度/取值/用户/授权 CRUD
├── mcp/
│   └── server.py           # FastMCP：四工具（search/upload/fetch/list_documents）+ 鉴权中间件（60s 超时）
├── core/
│   ├── ingest.py           # 摄取管线编排：parse→chunk→index_fts→embed→index_vec→quality（D21：版本在用制切换）
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
│   ├── auth_sso.py         # SSO 验签（OIDC/CAS 适配，协议待定；JIT 建档；可信子系统降级——D18）
│   ├── grant_sync.py       # 授权同步适配器（D16 演进缝，默认禁用）
│   └── tokenizer.py        # jieba 预分词（生成 content_seg / title_seg；人工词与 LLM 词分层——P1-3）
├── store/
│   ├── db.py               # 连接工厂（**唯一连接入口**：WAL/busy_timeout/foreign_keys=ON+断言/
│   │                        #   sqlite-vec 扩展加载；禁止绕过直连——P0-B，NFR-4）+ 迁移（user_version）
│   ├── repo.py             # repository 接口：hybrid_search/insert/delete_by_doc
│   ├── fts.py              # FTS5 建表/查询（五列权重）/MATCH 转义（含 " 的 "" 转义——P1-3）
│   └── vec.py              # 向量 BLOB 读写与距离计算（sqlite-vec 标量函数——P0-1）
├── domain/
│   ├── models.py           # pydantic 实体
│   └── auth.py             # token→user 解析（SSO 验签 + JIT 建档；静态 token 仅开发/测试——D18；委托 token/可信子系统校验）
├── worker/
│   ├── runner.py           # 子进程入口：任务循环（租约认领/心跳/重试）
│   └── ipc.py              # 与主进程的唤醒协议
├── eval/                   # M3：黄金集运行器 + Recall@k/MRR + ragas 接入
└── web/                    # 前端薄壳（§5.7，原型见 prototype/）
```

分层纪律：`api/mcp` 只做协议转换；`core` 是纯业务编排（不碰 SQL 细节）；`store` 是唯一碰 SQL 的层——**全部连接经 `store/db.py` 连接工厂**（外键 PRAGMA 每连接生效、扩展加载一致——issue #32 P0-B）：

```python
def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=5.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")       # 必须每个连接设置，不持久化
    conn.execute("PRAGMA synchronous = NORMAL")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:   # 不用 assert（python -O 会剥离——#33 P1-1）
        raise RuntimeError("foreign_keys pragma failed")
    return conn   # sqlite-vec 扩展加载同在此处；审计月库建表/触发器也走本工厂；测试：插孤儿行断言 IntegrityError
```

迁移约定（#33 P1-1）：SQLite 改表走"建新表→拷数据→删旧表"，期间**临时关闭外键**、结束后跑 `PRAGMA foreign_key_check`，有违例回滚——写进迁移框架，否则 schema v2 撞外键。

## 4. 数据模型（SQLite DDL v1）

```sql
PRAGMA journal_mode = WAL;   -- 其余 PRAGMA 是连接级设置（busy_timeout/foreign_keys/synchronous），见 §3 连接工厂

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
  required      INTEGER NOT NULL DEFAULT 1,  -- 必选：上传时强制选值（D5）；过滤条件只看 enabled（停用仍参与过滤=方案 a，§5.1）
  enabled       INTEGER NOT NULL DEFAULT 1,  -- 停用=收紧（免上传选值），撤过滤走"退役维度"事件（§6.2）
  grant_source  TEXT NOT NULL DEFAULT 'local',  -- 授权真值源：local | sync:<system>（D16——同步维度管理页只读）
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
-- 移出组织/成员关系过期清理 → 级联删该组织维度下该用户授权（P1-3；**含 sync 来源授权——预期行为**：
-- 同步适配器写入前须校验目标用户在本组织有有效成员关系，否则会生成孤儿授权——#33 P0-1⑥，§5.6）
CREATE TRIGGER trg_membership_delete_cleanup AFTER DELETE ON user_org_memberships
BEGIN
  DELETE FROM user_dimension_grants
  WHERE user_id = OLD.user_id
    AND dimension_id IN (SELECT id FROM dimensions WHERE org_id = OLD.org_id);
END;
-- 注：「文档 org = 库 org = 维度 org」一致性由服务层写入校验 + 触发器断言；授权行不含 org 列
-- （org 经 dimension_id 唯一归属推得，服务层断言），如 M0 实验证明按文档计算需要 org 冗余再加列。

-- ============ 文档（FR-1，v0.3：版本在用制——P0-A） ============
CREATE TABLE documents (
  id              TEXT PRIMARY KEY,   -- ULID（覆盖更新显式携带——文档身份唯一锚点）
  org_id          TEXT NOT NULL REFERENCES orgs(id),   -- 组织不可删只能停用（#33 P1-1）；org_id 不可变（下方触发器）
  dataset_id      TEXT NOT NULL REFERENCES datasets(id),  -- 归属知识库（D15）；删库走服务层流程（先删文档再删库，§6.2）
  title           TEXT NOT NULL,
  source_uri      TEXT,               -- 上传来源（user:<id> / agent:<id>——agent 代传内容标来源，随检索返回）
  content_hash    TEXT NOT NULL,      -- 内容哈希（重复**提示**，不强制拦截——P0-5）
  mime_type       TEXT NOT NULL,
  page_count      INTEGER,
  parser          TEXT NOT NULL,      -- docling | mineru
  active_version  INTEGER NOT NULL DEFAULT 0,  -- 在用版本（0=尚无在用版本）；检索只见该版本
  active_status   TEXT,               -- 在用版本状态：searchable_lexical | searchable_full | degraded（#33 P0-2.2）
  active_error    TEXT,               -- 在用版本嵌入/质量阶段失败写这里（lexical 切换后 pending 已清空）
  pending_version INTEGER,            -- 处理中版本（NULL=无进行中摄取）；= max(历史版本)+1，失败不复用（P0-2.3）
  pending_status  TEXT,               -- parsing|chunked|searchable_lexical|searchable_full|failed
  pending_error   TEXT,
  pending_dims_json TEXT,             -- pending 版本的新维度（P0-2.1）：pending 期间不生效，切换事务落入 document_dimensions
  owner_user_id   TEXT NOT NULL REFERENCES users(id),  -- owner 兜底仅限无在用版本/处理中文档（D22③，P1-8 方案 a）
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
BEGIN SELECT RAISE(ABORT, 'dimensions.org_id is immutable'); END;   -- #33 P2-9：三表齐全
CREATE TRIGGER trg_documents_ds_org_check BEFORE INSERT ON documents
WHEN (SELECT org_id FROM datasets WHERE id = NEW.dataset_id) != NEW.org_id
BEGIN SELECT RAISE(ABORT, 'dataset org mismatch'); END;
-- 重复检测：索引按 (dataset_id, content_hash) 粗筛；维度一致性由服务层比对 document_dimensions
-- 后提示重复（不强制拦截——P0-5；通用文档多值挂载见 document_dimensions）
CREATE INDEX idx_documents_hash ON documents(dataset_id, content_hash);

CREATE TABLE document_dimensions (   -- 文档维度（**多值**，D19：通用文档可挂 region∈{CN,OS}；内容混杂仍拆分上传 D4）
  doc_id       TEXT NOT NULL REFERENCES documents(id)        ON DELETE CASCADE,   -- 删文档可级联
  dimension_id TEXT NOT NULL REFERENCES dimensions(id)       ON DELETE RESTRICT,  -- P0-C
  value_id     TEXT NOT NULL REFERENCES dimension_values(id) ON DELETE RESTRICT,  -- P0-C
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

-- ============ 块与索引（FR-1/2/3，P0-1/P0-3/P1-1/P1-3 重做） ============
CREATE TABLE chunks (
  rid           INTEGER PRIMARY KEY, -- 显式整数主键（外部内容 FTS 以它关联，VACUUM 后稳定——P0-3a）
  id            TEXT NOT NULL UNIQUE, -- ULID（引用溯源锚点）
  doc_id        TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,    -- 文档内序号
  version       INTEGER NOT NULL,    -- 所属文档版本（=documents.active_version 或 pending_version）
  tombstone     INTEGER NOT NULL DEFAULT 0,      -- 旧版本标记：不进召回、fetch 返回替代提示；保留 90 天后物理删除
  content       TEXT NOT NULL,       -- 正文原文（**不进 FTS**——rerank 专用输入口径）
  title_seg     TEXT NOT NULL DEFAULT '',  -- 标题+heading_path 分词（FTS 权重 3——P1-3：税务文档定位价值高）
  content_seg   TEXT NOT NULL DEFAULT '',  -- jieba 分词后的正文（FTS 权重 1）
  token_count   INTEGER,
  heading_path  TEXT,                -- 结构感知切分的标题层级
  page_no       INTEGER,
  sheet_name    TEXT,                -- Excel 切分专用（行块 chunk 重复表头）
  bbox_json     TEXT,
  keywords      TEXT NOT NULL DEFAULT '',  -- **仅人工维护**关键词（FTS 权重 5——jieba 高频词不混入，P1-3）
  llm_keywords  TEXT NOT NULL DEFAULT '',  -- LLM 生成（FTS 权重 0.5~1，独立低权列，P1-1）
  tags          TEXT NOT NULL DEFAULT '',  -- 人工标签（FTS 权重 8）
  embedding     BLOB,                -- 向量 BLOB（P0-1：ACL 过滤后算距离；NULL=未就绪走 BM25 单路）。
                                     --   M0 实验对比拆 chunk_vectors 分表（P1-2）——4KB/块拖慢回表与放大 WAL
  embed_model   TEXT,                -- 钉版本：bge-m3@<rev>（D12）；NULL 表示未嵌入
  dims_json     TEXT NOT NULL,       -- 文档维度冗余投影（多值数组）——M0 实验候选去除项（P1-2 按文档计算后可删）
  detected_at_scale INTEGER,         -- 检测时语料规模（区分度重算策略——P1-8）
  content_sha   TEXT,                -- 区分度检测缓存（内容指纹，重检跳过）
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_chunks_doc ON chunks(doc_id, version, seq);   -- v0.4：含 version（P0-2.5——同文档多版本 seq 不唯一，fetch 窗口与按文档计算都走它）
CREATE UNIQUE INDEX uq_chunks_docver ON chunks(doc_id, version, seq);
CREATE INDEX idx_chunks_vec_pending ON chunks(doc_id) WHERE embedding IS NULL AND tombstone = 0;  -- 谓词含 tombstone（P1-2——否则切换后旧块重回待嵌入清单）

-- FTS5（P0-3 + P1-1/P1-3 重做）：
--   · 五列分权：title_seg 3 / content_seg 1 / keywords 5 / llm_keywords 0.5~1 / tags 8
--     （bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)——参数按列顺序；LLM 词低权防幻觉词压过正文）
--   · 外部内容表 + 三个同步触发器（列清单与 FTS 列一致，否则 'delete' 报 malformed——P1-1）
--   · 查询侧：query 先 jieba 切分，token 双引号包裹且内部 " 转义为 ""，拼 "tok1" OR "tok2"——防语法注入
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  title_seg, content_seg, keywords, llm_keywords, tags,
  content='chunks', content_rowid='rid', tokenize='unicode61'
);
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES (new.rid, new.title_seg, new.content_seg, new.keywords, new.llm_keywords, new.tags);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES ('delete', old.rid, old.title_seg, old.content_seg, old.keywords, old.llm_keywords, old.tags);
END;
CREATE TRIGGER chunks_au AFTER UPDATE OF title_seg, content_seg, keywords, llm_keywords, tags ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES ('delete', old.rid, old.title_seg, old.content_seg, old.keywords, old.llm_keywords, old.tags);
  INSERT INTO chunks_fts(rid, title_seg, content_seg, keywords, llm_keywords, tags)
  VALUES (new.rid, new.title_seg, new.content_seg, new.keywords, new.llm_keywords, new.tags);
END;
-- 注：无 vec0 虚表——向量即 chunks.embedding BLOB（或实验后的 chunk_vectors 分表）；容量与量化见 NFR-2/3。

-- ============ 质量反馈环（FR-3） ============
CREATE TABLE quality_flags (
  id            TEXT PRIMARY KEY,
  chunk_id      TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  doc_id        TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,  -- v0.4 补外键（#33 P1-1，防删文档残留孤儿）
  reason        TEXT NOT NULL,       -- vector_crowding | low_idf | both
  detail_json   TEXT,                -- 近邻相似度分布 / IDF 统计（**报告页展示近邻须过同一套 ACL 或只显示数值**——#33 P1-10）
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
-- append-only 触发器（v0.4 直接给出 DDL；SQLite 无 TRUNCATE，DELETE 均触发下方触发器——#33 P2-10）
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only; retention via monthly file rotation'); END;
-- v0.3（issue #32 P1-7）+ v0.4（#33 P1-4）：审计按月分库 audit_YYYYMM.db——当月可追加、过月封存只读
--   （只读打开 + 文件权限 + 封存记末哈希）、到期整文件删除；月库建表与上述触发器由连接工厂在滚动时创建；
--   **权限事件走 outbox**：业务库同事务写 audit_outbox 表，后台搬运保证"业务改了就一定有审计"
```

设计说明（v0.4）：

- **组织与库的隔离纪律**：一切检索/列表 SQL 的第一条件是 `org_id = :org`（跨组织零可见，owner 判定同样限本组织且仅限无在用版本文档——D22③）；库过滤（`dataset_id IN (...)`）是组织内的可选收窄；维度授权与维度定义都在组织作用域内解析。
- **维度冗余的取舍**：`chunks.dims_json` 是 `document_dimensions` 的投影（多值数组），检索 SQL 按 JSON 解析编译成常量条件（§5.1）；文档维度变更时由服务层同步刷投影（UPDATE，不重嵌——D6）。**M0b 实验若选定"按文档计算"（visible_docs），dims_json 整体删除**（消除一致性维护点，§5.1）。
- **向量存 BLOB 不用 vec0**（P0-1）：vec0 的 KNN 在虚拟表内部取 top-k 后才能 JOIN 过滤，等于 post-trim；BLOB + `vec_distance_cosine()` 在 ACL 过滤后的行集上算距离，"先过滤后扫描"（扫描量 = 用户可见量）。M0b 实验对比 `chunk_vectors` 分表（4KB/块拖慢回表与放大 WAL）。
- **FTS5 五列**（v0.4）：`unicode61` 只做兜底分词；`title_seg`（3）/`content_seg`（1）/`keywords` 仅人工词（5）/`llm_keywords`（0.5~1）/`tags`（8）分列加权；查询侧同词典切分 + token 双引号包裹且内部 `"` 转义为 `""`。

## 5. 关键设计

### 5.1 维度 ACL 编译器（core/acl.py）

输入：`user_id` + 组织上下文（REST=`X-Org-Id` 头 / MCP=token org claim 优先、运行时注入头兜底——D18 统一规则）；输出：可下推进召回 SQL 的 WHERE 片段（**结构化 builder 生成 AST 再渲染 SQL，禁止字符串拼接**）。逻辑（v0.4：**全部状态字段进入计算——P0-1**）：

1. **成员关系校验**（第 0 步，含过期）：`(SELECT role FROM user_org_memberships WHERE user_id=:uid AND org_id=:org AND (expires_at IS NULL OR expires_at > :now))`——无有效行即拒绝（系统管理员豁免仅限管理端点，D22）；**校验时发现已过期即当场物理删除该行**（触发 cleanup 级联清授权 + 审计；"续期"必须先删再加，防旧授权复活——T2）；
2. **授权展开**（含过期与停用，同一条 SQL）：

```sql
SELECT dim.key, v.value
FROM user_dimension_grants g
JOIN dimensions       dim ON dim.id = g.dimension_id AND dim.org_id = :org
JOIN dimension_values v   ON v.id   = g.value_id     AND v.status = 'active'   -- 停用取值=收紧（T3）
WHERE g.user_id = :uid
  AND (g.expires_at IS NULL OR g.expires_at > :now)                            -- 过期授权即失效（T1）
```

3. 对每个**已启用**的维度编译「文档取值集 ∩ 用户授权集 ≠ ∅」条件（维度间 AND、维度内 OR，D19）；**维度停用（enabled=0）仍参与过滤**（D5 方案 a——停用只免上传选值，撤过滤走"退役维度"权限事件）；**可选维度：有值则过滤、空值不过滤**（编译为 `json_each(...) IS NULL OR EXISTS(...)`——空值跳过、有值校验，T5）；无授权值的维度 → 整体不可见；
4. owner 兜底分支**仅对无在用版本或处理中文档生效**（`d.active_version = 0 OR d.pending_version IS NOT NULL`——D22③，T17）。

编译产物（示意——ACL 整体括号 + 外层约束 + **版本限定**，P0-2/P0-1）：

```sql
-- 组织 org:tax 内，用户 region=[CN, OVERSEAS]、tax_type=[VAT]；两维度均启用；文档维度多值（D19）
SELECT c.* FROM chunks c JOIN documents d ON d.id = c.doc_id
WHERE ( ( EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.region')   je WHERE je.value IN ('CN','OVERSEAS'))
      AND EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.tax_type') je WHERE je.value IN ('VAT')) )
      OR (d.owner_user_id = :uid AND (d.active_version = 0 OR d.pending_version IS NOT NULL)) )  -- owner 兜底（受限）
  AND c.version = d.active_version AND c.tombstone = 0     -- 只召回在用版本（P0-A/P0-2）
  AND d.org_id = 'org:tax' AND d.dataset_id IN (...) AND d.id IN (:doc_filter)
-- FTS 路同构：FROM chunks_fts f JOIN chunks c ON c.rid = f.rowid JOIN documents d ... WHERE f.chunks_fts MATCH :q
--   AND <同上全部条件>（版本条件必须出现在 FTS 路的 JOIN 上——T9 断言 FTS 层无 tombstone 命中）
```

性能注（v0.4）：
- **按文档计算备选（M0b 实验）**：`visible_docs` CTE 用**同一个授权展开函数**（第 2 步 SQL）先求可见文档集合，再 `WHERE c.doc_id IN (visible_docs)` 走 `uq_chunks_docver`——两条路径语义不漂移（#33 P0-1⑦）；胜出则删 dims_json；
- `json_each` 不接受时备选维度物化列 + 索引（schema v2 预留）；
- **rerank 前兜底断言 + 返回前二次断言**（防御纵深）。

### 5.2 检索管线（core/retrieve.py）

```
query ─→ LLM 关键词增强（**800ms 硬预算、与原始召回并行**；结果作为 RRF 的**第三路 BM25 查询**——不重做
     │   向量召回；超时丢弃。关键路径 = max(原始召回, 增强+BM25) + rerank，计入 NFR-8 预算表——#33 P1-9）
     ├─→ FTS5 BM25 路：query 经 jieba 切分 + token 双引号转义（内部 " → ""）→
     │    bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)   -- 五列按序：title/content/keywords/llm/tags
     │    + 版本条件（JOIN chunks/documents）+ ACL WHERE
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

阶段编排（**P0-4 拆分：index_fts 先于 embed，BM25 即刻可搜**；upload 时新维度写 `pending_dims_json`、写权限校验在 upload 即做——P0-2.1）：

```
parse（docling→统一块结构；扫描件路由 MinerU；mojibake 质量门；TXT 编码探测）
→ chunk（结构感知切分 256–512 / Excel 按 sheet 行块（重复表头）；jieba 生成 content_seg）
→ index_fts（chunks + FTS 同一事务；文档状态 → searchable_lexical）
→ embed（bge-m3 分批 64，CPU 线程池；逐批 UPDATE embedding/embed_model）
→ index_vec（逐批就位；全部完成 → searchable_full）
→ quality（区分度检测 → quality_flags → LLM 关键词 → 回写 llm_keywords）
```

文档更新（覆盖，显式 doc_id）：新版本以 `pending_version` 走完管线 → 按 D20 切换时机**单事务原子切换**（P0-A）：

```sql
BEGIN IMMEDIATE;
-- 旧块：标记 + 清向量 + **清五列 FTS 内容**（清空后 au 触发器执行 FTS 'delete' 再插入空行——
-- UPDATE 不触发 ad、旧注释有误；FTS 里残留空 rowid 不影响 MATCH，#33 P0-2.4/T9）
UPDATE chunks
   SET tombstone = 1, embedding = NULL,
       title_seg = '', content_seg = '', keywords = '', llm_keywords = '', tags = ''
 WHERE doc_id = :doc AND version = :old_version;
UPDATE documents
   SET active_version = pending_version,
       active_status  = pending_status,               -- searchable_full
       pending_version = NULL, pending_status = NULL, pending_error = NULL
 WHERE id = :doc AND pending_version = :expected_pending;   -- 乐观校验，防并发（P0-2.3/T7）
-- 同事务：pending_dims_json 解析写入 document_dimensions（P0-2.1——v2 维度切换前不生效，T6）
COMMIT;
```

**并发与失败（v0.4，P0-2.3）**：pending 期间再来的覆盖上传 → **409**（同一时刻只有一个 pending）；pending 失败 → `pending_status=failed` 且**立即 DELETE 该版本全部块**（经 ad 触发器移出 FTS——失败不留检索残留，T8），重试用新版本号（`pending_version = max+1` 不复用）；删除文档即取消其任务，worker 每阶段开始前检查文档存在与版本归属；embed 批次回写带防护 `WHERE rid=:rid AND tombstone=0 AND version IN (:active,:pending)`。

**切换时机（D20）**：首次上传（active_version=0）在 `searchable_lexical` 即切换在用（保留先可搜收益；此后嵌入进度写 `active_status`、失败写 `active_error`——P0-2.2）；覆盖上传等新版本 `searchable_full` 再切换（旧版本全程服务）；新版本失败旧版本不受影响。tombstone 块保留 90 天（审计回溯）后物理删除；`fetch` 旧块返回 `{doc_id, active_version}` 对象替代提示（**不承诺块级映射**——重切分后无对应）。

### 5.4 区分度检测（core/quality.py，v0.3 P1-8 + v0.4 P1-10 更正）

- **向量拥挤度**：新 chunk 向量取**组织内且仅在用版本**（`tombstone=0 AND version=active_version`——否则新旧版本互为拥挤近邻制造误报，#33 P1-10）的 top-8 近邻，`mean(sim) > 绝对阈值` 判拥挤（初值 M1 真实语料重标定）；入库单块检测走 SQL 暴力扫描（量小）；
- **批量重算路径（v0.4 更正）**：10 万 × 1024 维全量矩阵乘约 10¹³ flops，numpy/BLAS 分块矩阵乘 CPU **分钟级可行**（v0.3"不可行"论断有误——真正慢的是 SQL 标量函数逐行）；重算（`detected_at_scale` 比例 + 每周抽样）在 worker 低峰期把组织内在用块向量分块载入 numpy（float16 或流式，~400MB@10 万块，纳入内存预算 NFR-9）批处理；
- **词面通用度**：token 平均 IDF 低于**绝对阈值**；新组织冷启动引用全局语料 IDF；
- **报告页防旁路（#33 P1-10）**：`quality_flags.detail_json` 的近邻信息展示时**过同一套 ACL**，或只显示相似度数值不展示近邻内容（T18）；
- 触发 → LLM 生成关键词写 **`llm_keywords` 独立低权重列**（标来源，不与人工 `keywords`×5 混列）；**口径如实**（非 Contextual Retrieval）；
- OneRAG 借鉴项落地处：parse 后 **mojibake 质量门**（正常字符比 <0.55 → 告警/重试/失败三档）。

### 5.5 鉴权、身份与组织上下文（domain/auth.py + mcp/server.py）

- **登录：企业 SSO（D16）**——token 验签（OIDC 优先，协议待需求待决-2 确认）→ 解析全局用户；**首次登录 JIT 建档**（`users` 表自动落库：id/username/display_name），管理员不建账号只配授权。
- **agent 代人检索（D18）**：**委托 token（Token Exchange）**——`aud=knowledge-lattice`、短 TTL、`sub`=用户、`act`=agent 标识进审计；拒绝 token 原样透传与请求体权限字段。**降级（v0.3）**：IdP 不支持时走**可信子系统**——agent 服务自身凭证（mTLS/服务 token）须在服务白名单，请求头 `X-On-Behalf-Of: <user_id>` 声明用户，知识库校验白名单后按声明用户计权、双身份（服务+用户）进审计；数据模型与 D18 一致（弱化 act/sub）。**组织上下文来自 token claim / 请求头**——MCP 工具参数中的 org 一律忽略（LLM 可被诱导填他组织，issue #32 P1-6）。静态 token 仅开发/测试（含 CI）。
- **M0b 实测项（issue #32 P1-6）**：`langchain-mcp-adapters` 按用户切换委托 token 的客户端形态（每用户会话一个 client vs 自定义 transport 每请求注入头）、连接开销与 token 过期刷新。
- **组织上下文统一规则（v0.4，D18）**：REST 用 `X-Org-Id` 请求头；MCP 以委托 token 的 `org` claim 优先（按组织签发、单值）、无 claim 时读运行时在连接/传输层注入的 `X-Org-Id` 头；两者并存且不一致 → 400；**工具参数中的 org 一律忽略并记审计**；缺失即 400，无隐式默认。逐请求按 §5.1 第 0 步（含过期）校验成员关系。
- **可信子系统降级三条约束（v0.4，#33 P1-5）**：①白名单条目带 `allowed_orgs` + 按服务限流；②**用户在场证据**——请求附用户 SSO id_token/短期断言，校验 `sub` 与 `X-On-Behalf-Of` 一致（防服务凭证冒充离线用户）；③`X-Org-Id` 由运行时按用户会话注入。**有期限：上生产前必须切 Token Exchange 或落实②**（D18）。
- MCP server 挂 60s 超时中间件（ragflow 同款纪律）。

### 5.6 权限管理：授权维护与真值源闭环（D16 v0.2）

维度授权按维度声明真值源（`grant_source`），维护闭环四件套：

1. **管理页单点配置**：组织管理员逐用户调整（查询时实时展开，改即生效——D6）；**同步维度（`sync:<system>`）管理页只读**、CSV 批量导入时跳过，防人工覆盖真值；
2. **批量导入/导出（主通道）**：CSV `username, dim_key, values...`（**不带 org 列**——路径已含组织，列与路径不一致整批拒绝，#33 P2-19）；导入按「用户×组织」幂等全量替换、**仅替换 grant_source='local' 的授权**（sync 不动）、差异预览后确认；**写入前校验目标用户在本组织有有效成员关系**（防孤儿授权，#33 P0-1⑥）；支持 `expires_at` 列；
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
      "dims": { "region": ["CN"], "tax_type": ["VAT"] },   // ← 多值数组（D19）
      "source": "user:u1 | agent:tax-copilot",              // ← 来源随结果返回（agent 代传可识别）
      "snippet": "…一般纳税人销售自产货物并提供安装服务的，应分别核算…"
    }],
    "notice": "vector_pending=false"   // useful-early：向量未就绪时 true，提示结果仅 BM25
  }
}

// upload —— "向知识库上传文档（agent 采集到的文件）。必须指定知识库与维度元数据，否则会被拒绝。"
{
  "name": "upload",
  "input":  { "upload_id": "upl_xxx",           // 不透明凭证——由 POST /api/uploads 签发（见下）；路径/URL 一律拒绝（P0-D）
              "dataset": "ds:vat",
              "dimensions": { "region": ["CN"], "tax_type": ["VAT"] },   // 多值数组（D19）；值须在调用者授权内（P1-1）
              "doc_id": "string?",             // 覆盖更新显式携带（文档身份）
              "title": "string?" },
  "output": { "doc_id": "01J…", "task_id": "01J…", "status": "queued", "pending_version": 2 }
}
// upload 三步凭证流（P0-D）：
//   ① agent 运行时（非 LLM）POST /api/uploads {filename,size,sha256,content_type} → {upload_id, upload_url, expires_at}
//      （upload_url 短时有效、单次使用）
//   ② 运行时 PUT 文件字节到 upload_url
//   ③ LLM 调 upload(upload_id, ...)——校验属当前 sub、未过期、未使用、哈希匹配后进摄取
//   共享存储场景：白名单根目录 + realpath 规范化 + 前缀校验 + 只读 + 大小/扩展名限制；不支持任意 URL 拉取

// fetch —— "按 chunk_id 取该块前后相邻的内容窗口（先搜后读）。旧版本块返回替代提示。"
{
  "name": "fetch",
  "input":  { "chunk_id": "01J…", "window": "int=2" },   // 前后各 N 块
  "output": { "chunks": [{ "chunk_id": "…", "seq": 41, "content": "…", "page_no": 12 }],
              "replaced_by": { "doc_id": "01J…", "active_version": 3 }?（tombstone 时非空——对象；不承诺块级映射，P0-A/P0-2.5） }
}

// list_documents —— "列出权限内可见的知识库与文档及处理状态。先了解库里有什么，再决定搜什么。"
{
  "name": "list_documents",
  "input":  { "datasets": "string[]?", "active_status": "string?", "limit": "int=50" },
  "output": { "datasets": [{ "id": "ds:vat", "name": "VAT 实务库", "doc_count": 12 }],   // ← 全部统计按调用者权限计算（P1-8）
              "documents": [{ "doc_id": "01J…", "dataset": "ds:vat", "title": "…",
               "active_version": 2, "active_status": "searchable_full",                    // ← 在用/处理中双态四字段（P0-2.2）
               "pending_version": 3, "pending_status": "searchable_lexical",
               "dims": { "region": ["CN"] }, "chunk_count": 143,
               "source": "user:u1 | agent:tax-copilot", "updated_at": "…" }] }
}
```

纪律：检索参数（权重/阈值/召回窗口）服务端固定，不暴露给 LLM（ragflow 反面教训）；`top_k ≤ 20` 服务端硬上限；工具描述动态注入的库/维度概况与一切统计**按调用者权限计算**（不可见文档的存在与数量不泄露）；`search` 返回块带 `source` 字段（agent 代传内容可识别——prompt injection 防御前置）。

### 6.2 REST 端点（api/，v0.4 路径统一：**组织作用域资源一律 `/api/orgs/{org}/...`**，`X-Org-Id` 头仅 MCP/检索用；路径与头并存且不一致 → 400——#33 P1-7）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | /api/orgs | 组织列表（系统管理员=全部；普通用户=membership）/ 创建组织（系统管理员）。**组织不可删只能停用**（P1-1） |
| GET / PUT | /api/orgs/{org}/members | 成员列表（含 expires_at）/ 成员与角色管理（组织管理员；**合并原 memberships+users 两端点**——P1-7） |
| PUT | /api/orgs/{org}/members/{id}/grants | 授权全量替换（**只替换 local 授权，sync 不动**；支持 expires_at） |
| GET / POST | /api/orgs/{org}/grants/export · import | 授权导出 / 批量导入（CSV 无 org 列；dry_run 差异预览；幂等全量替换） |
| GET/POST | /api/orgs/{org}/datasets | 知识库列表 / 新建（组织管理员） |
| PATCH | /api/orgs/{org}/datasets/{id} | 库修改；**删除走服务层流程**（先删文档再删库——P1-1） |
| GET/POST | /api/orgs/{org}/dimensions | 维度列表 / 新建 |
| PATCH | /api/orgs/{org}/dimensions/{id} | 维度修改（enabled/required——降级语义见 D5 方案 a；**退役维度单独端点**） |
| POST | /api/orgs/{org}/dimensions/{id}/retire | 退役维度（撤过滤的权限事件：影响面预估 + 二次确认 + 审计） |
| GET/POST | /api/orgs/{org}/dimensions/{id}/values | 取值 CRUD；**停用走 PATCH status=disabled**（`dry_run` 返回影响面预估——FR-4） |
| POST / DELETE | /api/orgs/{org}/documents | 上传（multipart 或携带 upload_id；校验库 + 必选维度 + 取值在本人授权内；覆盖带 doc_id）/ |
| DELETE | /api/orgs/{org}/documents/{id} | 删除文档（owner/org_admin；取消其任务） |
| PATCH | /api/orgs/{org}/documents/{id}/dimensions | 修改维度（**pending 期间 409**——P0-2.1；新旧取值均在操作者授权内） |
| GET | /api/orgs/{org}/documents/{id} | 详情（active/pending 四字段 + quality_flags 概要） |
| GET | /api/orgs/{org}/documents/{id}/quality | 质量报告明细（近邻展示过 ACL——§5.4） |
| PATCH | /api/quality-flags/{id} | 人工补充 tags / ignored/resolved |
| GET | /api/orgs/{org}/tasks | 任务列表（状态/进度/错误） |
| POST | /api/orgs/{org}/tasks/{id}/cancel | 任务取消（M2） |
| POST | /api/orgs/{org}/documents/{id}/reindex | 手动重索引（M2） |
| POST | /api/search | 检索（检索测试页；参数同 MCP search；组织经 `X-Org-Id`——本端点为例外，兼容检索页） |
| POST | /api/uploads | **上传凭证签发**（{filename,size,sha256,content_type} → {upload_id, upload_url, expires_at}；**绑定 sub+org+服务身份**，#33 P1-3） |
| PUT | /api/uploads/{upload_id} | **接收文件字节**（v0.4 补——Bearer 鉴权 + sub 一致；按声明 size 截断/拒绝、写盘后校验 sha256、全局上限 200MB；**M1 集成期实现**，人工 multipart 不依赖） |
| GET | /api/orgs/{org}/audit | 审计查询（org_admin 全量 / 系统管理员仅元数据——FR-6 分级） |
| POST | /api/dev/token | 签发静态 token（**仅 dev/test 配置注册该路由，生产环境 404**——P1-7；只能给自己签或系统管理员签发） |

鉴权：所有端点要求 Bearer token（委托 token 或 SSO）；**可信子系统走服务凭证（mTLS/服务 token 白名单）+ `X-On-Behalf-Of` + 用户在场证据（D18）**；写操作经 outbox 落审计。

### 6.3 与术语层（glossary-agent）的工具组集成（D17）

- **消费侧形态**：deepagents 并挂两个 MCP server——本系统 `search` / `upload` / `fetch` / `list_documents` + glossary-agent 的 `lookup_terms`（与数据字典活查询）。职责边界：本系统只管文档知识，术语归一与黑话定义不在检索范围（agent 侧前置识别/lookup 处理后再调本系统检索）。
- **演进缝（不进 MVP）**：如需单端点，本系统可加载术语库**运行时投影**（Git YAML → AC 自动机 + FTS 内存索引），以 `lookup_terms` 工具统一暴露——真值源与 PR 治理仍在术语库 Git 仓，本系统只持可刷新投影（`adapters/` 预留 `glossary_loader.py` 位）。
- **明确不做**：表名字段名/数据字典类查询（真值在源系统、高频变）由术语侧 MCP 活查询直连，本系统不镜像这类数据；L0 常驻核心术语表是术语库构建期导出物（进 agent system prompt），与本系统无关。
- **上传凭证的 agent 侧时序（v0.4，#33 P1-3——M1 集成项）**：deepagents 侧需要一个**运行时工具/中间件**（非 LLM 直接参与）——LLM 决定"上传某文件"→ 运行时①持委托 token 调 `POST /api/uploads`（声明 filename/size/sha256）→ ②PUT 字节到 upload_url → ③把 `upload_id` 交回对话，LLM 再调 MCP `upload(upload_id, dims, ...)`。凭证绑定 sub+org+服务身份（跨组织无效——T11）；未消费凭证由清理任务回收。

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

## 8. 里程碑任务分解（v0.4，与需求 §8 逐条对齐——#33 P1-11/P1-12）

**M0a（第 1 周）——骨架 + schema 全量落**
1. 脚手架（uv/config/迁移框架含外键处理约定，§4 全部 DDL 与触发器一次性落）；连接工厂（foreign_keys=ON + 显式 raise + 月库滚动建表）
2. 摄取最小链：docling 解析 → 结构切分（五列分词）→ index_fts 入库（BM25 即刻可搜）→ 嵌入分批补齐
3. 检索最小链：BM25 单路 + **完整 ACL 编译器（含状态过滤：过期/停用/owner 受限——D22①）**
4. FastMCP `search` + REST multipart 上传 + 静态页壳
5. 验收：deepagents 经 MCP 一次带 chunk_id 的检索（**开发 JWT 即可**）；插孤儿行 IntegrityError；T1~T5 在编译器单测先行
6. 并行：待决-2/3（SSO 协议、token 方案）

**M0b（第 2 周前半）——实验**
1. 按块 json_each vs 按文档 visible_docs（同一授权展开函数，1/5/10 万块 P95）
2. 向量同表 vs chunk_vectors 分表回表耗时
3. langchain-mcp-adapters 按用户委托 token 实测
4. SLO 压测（NFR-8 预算表逐项标定）
5. 结论回写 **schema v1.1 迁移**（含 foreign_key_check；dims_json 去留、分表与否在此定）

**M1（第 2 周后半~第 3 周）——完整配方 + 版本在用制全链（前移）+ 权限全链 + 凭证集成**
1. 五列 FTS + 双路（先过滤后距离）+ RRF（增强第三路）+ rerank 32（ONNX int8）+ 归一
2. **版本在用制全链**：active/pending 状态机、切换事务（清 FTS 列）、tombstone、并发 409、失败删块、fetch 替代提示（**前移自 M2——M1 越权验收依赖**）
3. 维度 ACL 全链：多值、上传/PATCH 值限授权内、可选维度有值则过滤、维度停用仍过滤（方案 a）
4. **上传凭证制 + deepagents 集成**（§6.3 时序：运行时工具 + PUT 端点 + 绑定 sub+org+服务 + 清理任务）
5. 区分度环（绝对阈值 + numpy 批量重算 + 报告页近邻过 ACL）
6. 真实文档批量上线（待决-1，合成样例先行）+ 小型黄金集 + Recall@k/MRR + P95 基线
7. 验收：**越权矩阵全绿（§9 含 T1~T19）**；真实 query 标注；区分度误报抽查

**M2（第 4~6 周）——生产化**
1. worker 子进程化（心跳/租约/重试）+ 写竞争治理 + embed 回写防护
2. SSO/JIT 对接（M0a 已敲定协议）；委托 token / 可信子系统落地（三约束 + 期限）
3. 管理面 API + 最小 UI（§6.2 全端点：维度停用 dry_run/退役/授权 expires_at/任务取消/重索引/审计分级查询）
4. 审计 outbox + 月库滚动 + 封存；删除级联与 90 天物理清理
5. 备份快照 + 恢复演练
6. 验收：**杀 worker 不丢任务**（任务租约重认领）；outbox 一致性（权限事件必有审计）；恢复演练通过；跨组织隔离全绿；批量导入 500 行正确（sync 不动——T-CSV）

**M3（第 7~8 周）——评测防线**
1. 完整黄金集（M1 小型集扩容）+ 响应层指标固化
2. judge 双语校准（~50 条人工双评）
3. deepeval 门禁进 CI（预注入回归验证）
4. 在线引用锚点抽样
5. 验收：门禁能卡住一次人为注入的检索层回归；judge-人一致性达标；黄金集覆盖中英三态 query

依赖：M1.2/1.3 依赖 M0a.3；M1.4 依赖 M1.2；M0b 结论回写后方可进 M1；M3 扩量依赖待决-1。

## 9. 测试策略（v0.4：含 issue #33 T1~T19 全量）

- **单元**：ACL 编译器（括号化 AST 断言/多值/状态过滤【过期/停用/成员关系过期】/owner 受限/可选维度有值则过滤）；**连接工厂外键断言（插孤儿行抛 IntegrityError）**；FTS5 MATCH 转义（`"`→`""`/`*`/`NEAR`/`AND`/`-`）；RRF 与归一；切分边界（表格整块/Excel 行块含表头）；**切换 SQL 后 FTS 无 tombstone 内容**；凭证流（size 截断/sha256 校验/过期/绑定）；
- **集成**：摄取→检索端到端（searchable_lexical 中间态）、版本切换原子性（并发 409/失败删块/回写防护）、任务租约重认领、触发器同步无幽灵命中、迁移 foreign_key_check；
- **越权用例集（CI 常跑）**：原矩阵（用户授权 × 文档维度多值 × 库过滤 × 可选维度空值 × 新增必选未回填 × 移出重加 × 跨组织 × MCP 统计）+ v0.3 四组（版本中间态/删维度取值/PATCH 越权/CSV）+ **T1~T19（#33 §6，逐条对应修复项）**：T1 过期授权清理未跑仍不可见；T2 成员续期不复活旧授权；T3 停用取值收紧；T4 维度改可选/停用按 D5 方案 a 不放宽；T5 可选维度有值则过滤；T6 v2 改维度切换前后无双方可见（两种 ACL 写法都测）；T7 并发覆盖 409；T8 失败版本无 FTS 残留；T9 切换后 FTS 层面无旧版本命中；T10 待嵌入清单不含 tombstone；T11 凭证跨组织无效；T12 PUT 超量/哈希不符拒绝；T13 可信子系统越界/冒充拒绝并审计；T14 org claim 与头不一致 400；T15 他组织维度 id 403/404；T16 生产配置 token 端点 404；T17 授权撤销后 owner 不再见在用文档；T18 报告页近邻不泄露无权内容；T19 删文档/删库按定义成功或明确报错（非裸外键异常）；
- **评测**：M1 小型黄金集 → M3 门禁；
- **性能抽测**：~10 万块 P95（按块 vs 按文档、同表 vs 分表）、rerank 并发、嵌入吞吐（M0b/M1 各一轮，驱动 schema v1.1 与 NFR-8 标定）。

## 10. 风险的工程对策（对应需求 §9 风险登记，v0.4 清理）

| 风险 | 工程对策 | 触发点 |
|---|---|---|
| 无 GPU 嵌入吞吐 | 阶段拆分（index_fts 先行）+ 分批 64 + int8 量化；`config.py` 预留 embedding_model 配置位（e5-small 384 维备选，维度不兼容需全量重嵌决策） | M2 实测吞吐曲线后决策 |
| jieba 中英混排 | tokenizer 独立模块（可换 trigram/自定义词表）；M1 真实 query 标注集是判据 | M1 验收 |
| sqlite-vec BLOB 扫描边界 | repo 接口已隔离向量路；pgvector 适配器为升级缝首个目标 | 一期 10 万块 P95 超标（NFR-2/8） |
| dims_json json_each 性能 | **M0b 按文档计算实验**（胜出即删 dims_json）；备选维度物化列（schema v2） | M0b / 十万级实测 |
| P95 延迟超标 | NFR-8 预算表 + **双降级开关**（rerank 截断 256 / 候选 32→16） | M0b 压测、M1 基线 |
| 区分度失真 | 绝对阈值 + 分位下限；**规模比例 + 抽样重算（numpy 批量）**；近邻限在用版本；报告页近邻过 ACL | M1 抽查 + 周期重算 |
| 权限漂移（D16） | 季度对账 + 审计回放；grant_sync 适配器；生产前语义匹配维度切只读同步 | 季度对账；高敏文档从严 |
| 模型权重 license | 模型清单进 `config.py` 单一登记处，商用核查逐卡打勾 | 商用前（NFR-7） |
