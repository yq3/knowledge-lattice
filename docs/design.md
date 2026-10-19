# knowledge-lattice 方案设计

> 版本：v0.5.2（2026-10-19 术语修订：语义层内容层「骨架」统一改称「源端事实」，列级相应称「事实列」——旧词易被误读为抽象类别（实际是源系统已有对象与关系的具体同步记录），且与 M0a「骨架周」（工程脚手架）撞词；**非决策变更**，只改措辞不改任何结论。v0.5.1（2026-10-19 原型基线更新：吸收 [issue #36](https://github.com/yq3/lab/issues/36)——`prototype/index.html` 替换为 v0.5，五视图（文档 / 检索测试 / 权限 / 语义层 / 任务与审计），§5.7 前端薄壳以其为**信息结构与 UI 风格双基准**；语义层视图原型已含（实现仍可选，M2-S3 节奏不变）；**非决策变更**——D1~D23 与 v0.4 冻结结论均不受影响，冻结纪律延续）
> 日期：2026-10-16 初稿 → v0.2（#31）→ v0.3（#32）→ v0.4（#33+#34，冻结版）→ v0.5（#35，D23）→ v0.5.1（#36，原型基线更新）→ v0.5.2（术语修订：骨架→源端事实）
> 前置阅读：[requirements.md](./requirements.md)（本文所有 FR/NFR/D 编号均指向需求文档 v0.5.1）
> 调研依据：[enterprise-rag 调研](../../research/enterprise-rag/)，参考架构基线 `blog/10-build-kb-for-agent.md`

---

## 1. 设计总览：需求 → 方案的映射

| 需求 | 方案落点 | 本文章节 |
|---|---|---|
| FR-1 摄取 | 单进程 + worker 子进程 + 任务表；docling 进程内解析 | §2 / §5.3 |
| FR-2 检索 | SQLite 内双路（FTS5 + sqlite-vec）→ RRF → 进程内 rerank | §5.2 |
| FR-3 区分度反馈环 | 摄取管线尾部 quality 阶段 + 质量报告接口 | §5.4 |
| FR-4 维度权限 | 维度模型五表 + ACL 编译器（查询时展开，引擎内下推） | §4 / §5.1 |
| FR-5 接口面 | FastMCP 单一 server：docs 组四工具（search/upload/fetch/list_documents）+ semantic 组四工具（annotate/search_entities/get_entity/describe_table，M2-S——D23）+ REST + 静态薄壳前端 | §6 |
| FR-6/7 治理与评测 | audit_events 触发器；评测脚本集（黄金集 + 门禁） | §4 / §9 |
| NFR-1 零中间件 | 全部组件进程内/文件级，无外部常驻服务 | §2 |
| NFR-5 演进缝 | repository 接口 + 配置级切换点清单 | §7 |
| **FR-S1~S6 业务语义（D23）** | `core/semantic/`：同步适配器（源端事实）+ Git YAML 覆盖层（人工内容）+ AC 自动机识别 + 递归 CTE 关系展开 + 实体召回路（**复用 §5.1 ACL 编译产物**）+ describe_table 透传；与 docs 同进程同库、单一 MCP server 分组注册 | §3 / §4（`sem_*`）/ §5.8~5.10 / §6.3 |
| **NFR-11 语义层性能与隔离（D23）** | 独立 worker 任务类型（semantic_sync/build/retag）限速错峰；删除比例保护 + 宽限期；构建产物原子切换；中间件降级 | §2 / §5.8 / §6.3 |
| **issue #31 评审修订（v0.2）** | P0 五项修复（检索侧）+ 权限真值源 + 性能运维 | §4 / §5.1~5.3 / §5.6 / §8~10 |
| **issue #32 评审修订（v0.3）** | 写路径安全 P0×4 + P1×9 | §4 / §5.1~5.3 / §5.6 / §8~10 |
| **issue #33 收口修订（v0.4，冻结）** | 权限状态进计算（P0-1）/ 版本在用制闭环（P0-2）/ 外键动作补齐 / 凭证流闭环 / 审计 outbox / 可信子系统约束 / REST 路径统一 / M0a-M0b 拆分 / T1~T19 | 全文（决策汇总见需求 D22） |
| **issue #35 决策修订（v0.5，D23）** | 业务语义层并入（取代 D17 部署形态）：类型化对象图 + SQLite 递归 CTE，**不做 GraphRAG / 图数据库**；源端事实同步 + YAML 覆盖层分层真相源；M2-S1~S3 并行轨道 | §2~§4 / §5.2~5.3 / §5.8~5.10 / §6 / §8~10（决策汇总见需求 D23） |

## 2. 进程与部署架构

```
 ┌─────────────────────┐        ┌──────────────────────────┐
 │ 前端薄壳（静态页）    │        │ deepagents（企业内服务）    │
 │ 上传/检索/管理        │        │ agent 循环住在这里          │
 │ （M2-S3 起含语义入口）│        │ + 术语注入薄中间件（D23）    │
 └─────────┬───────────┘        └────────────┬─────────────┘
           │ REST                             │ MCP（HTTP，委托 token / 可信子系统——D18）
           ▼                                  ▼
 ┌───────────────────────────────────────────────────────────┐
 │ knowledge-lattice 主进程（FastAPI，单进程）                    │
 │  · REST 控制面：upload / tasks / search / admin / semantic    │
 │  · FastMCP server（单一 server，两组工具——D23）：             │
 │     docs 组：search / upload / fetch / list_documents         │
 │     semantic 组（M2-S 起）：annotate / search_entities /      │
 │       get_entity / describe_table                            │
 │  · 检索管线（同步）：双路召回（ACL 引擎内下推）→RRF→ACL 断言      │
 │ │    →rerank→返回前二次断言→溯源返回（P2-4 顺序）              │
 │  · 维度 ACL 编译器：委托 token →（含过期/停用的）授权展开 → SQL WHERE   │
 │  · core/semantic（D23）：AC 自动机识别 / 关系展开（递归 CTE）/    │
 │    构建产物懒加载（按 org+dict_rev 原子切换）/ 同步适配器         │
 │  · 任务调度：写 tasks 表 + 唤醒 worker；审计写入                │
 └────────┬────────────────────────────────────┬──────────────┘
          │ 子进程 IPC（unix socket / stdin）    │ 读写
 ┌────────▼──────────────┐          ┌───────────▼──────────────┐
 │ worker 子进程           │          │ SQLite（data/lattice.db）  │
 │ docs 任务：解析→切分→     │          │ 元数据 + FTS5 + 向量BLOB   │
 │   打标*(M2-S3)→index_fts │          │ + sem_*（业务语义——D23）   │
 │   →嵌入→index_vec→质量    │          │ WAL 模式（多读单写）        │
 │ semantic 任务（D23）：    │          └──────────────────────────┘
 │   semantic_sync（每日/   │
 │   手动）· semantic_build │
 │   · semantic_retag      │
 │ 心跳/租约/断点续跑       │
 └────────┬───────┬──────┘
          │       │                ┌──────────────────────────┐
 ┌────────▼──┐ ┌──▼─────────┐      │ data/objects/ 对象目录     │
 │ docling    │ │ 内部 LLM    │      │ 原始文件+解析产物           │
 │ （进程内库）│ │ 网关客户端   │      │ （canonical 真相，可重建）   │
 │ MinerU 懒载│ │ (关键词增强/ │      └──────────────────────────┘
 │ （可选服务）│ │  区分度兜底) │
 └───────────┘ └────────────┘
```

**部署形态（NFR-1/9）**：`knowledge-lattice` 主进程 ×1（内含 worker 子进程）+ `lattice.db` ×1 + `data/objects/` 目录 ×1。无消息队列、无独立向量库、无嵌入服务容器——它们分别是 tasks 表轮询、**chunks.embedding BLOB 列 + sqlite-vec 距离函数**、进程内 bge-m3。worker 经 IPC 被唤醒 + 兜底轮询（anything-llm 的最小进程隔离样板：OOM 只杀 worker）。**业务语义层并入后形态不变（D23）**：`core/semantic/` 与文档层同进程、同主库（`sem_*` 前缀表，迁移脚本分目录）、同一 MCP server——不新增独立服务、不引入图数据库（10⁴~10⁵ 节点、1~2 跳查询，递归 CTE 毫秒级）；同步适配器只读拉取源系统（模板中心/场景配置/报表中心/元数据系统）快照，`describe_table` 实时透传元数据系统。**资源预算**：主进程与 worker 各加载一份模型（嵌入+reranker+docling），峰值 6~8 GB——最低规格 16 GB RAM / 8 核；**CPU 推理全部进线程/进程池**，不阻塞事件循环；AC 自动机与模糊索引按 `(org, dict_rev)` 懒加载（数千~数万条，内存开销 MB 级）。

**并发模型（NFR-9）**：SQLite WAL 模式（多读单写）。检索（读）不受摄取（写）阻塞；写竞争治理：`busy_timeout` + worker 短事务分批提交 + **审计按月分库后与业务写天然隔离**（FR-6）。数百用户检索并发的实际瓶颈在 rerank 计算（§5.2 缓解：候选 32 / ONNX int8 / 信号量）。**语义任务的写锁治理（D23，NFR-11）**：`semantic_sync` / `semantic_retag` 与 ingest 抢 WAL 写锁——同步与重标为独立任务类型、分批 ≤1000 行/批、限速、默认夜间错峰；重标优先级最低不与 ingest 抢资源；语义任务失败不影响 docs 检索可用性；必要时把 `sem_*` 拆到 ATTACH 的独立库文件（repository 接口不变）。

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
│   ├── admin.py            # 维度/取值/用户/授权 CRUD
│   └── semantic.py         # ★D23 /api/orgs/{org}/semantic/...：annotate / entities / tables / l0 / sync / yaml webhook / builds（§6.2）
├── mcp/
│   └── server.py           # FastMCP 单一 server：docs 组（search/upload/fetch/list_documents）+ semantic 组（annotate/
│                           #   search_entities/get_entity/describe_table，M2-S——D23）分组注册 + 鉴权中间件（60s 超时）
├── core/
│   ├── ingest.py           # 摄取管线编排：parse→chunk→index_fts(+打标)→embed→index_vec→quality（D21：版本在用制切换；D23：tag/untag 显式调用）
│   ├── chunking.py         # 结构感知切分（docling 结构树 + 递归 token）
│   ├── excel_chunking.py   # Excel 表格型切分（sheet/行块）
│   ├── retrieve.py         # 检索管线编排：召回（FTS/向量/实体路*）→融合→重排→过滤→溯源（*M2-S3，调 semantic.expand）
│   ├── acl.py              # 维度 ACL 编译器（§5.1）——实体召回路复用其产物，语义层不另写
│   ├── quality.py          # 区分度检测 + LLM 关键词增强（§5.4）
│   └── semantic/           # ★D23 业务语义（M2-S1~S3）：与 docs 共基础设施（store/domain），不共享领域模型与 ACL 编译器
│       ├── annotator.py    #   AC 自动机识别 + 消歧（§5.9）；对外显式接口 tag(chunks, org) / untag(doc_id, version)（ingest 打标同源）
│       ├── expand.py       #   关系展开：递归 CTE、深度≤2、防环、高扇出截断（§5.9）；对外接口 expand(ids, rels, depth)
│       ├── build.py        #   semantic_build：AC 自动机 / 模糊索引 / L0 片段 / 构建报告 + 按 (org, dict_rev) 原子切换（§5.8）
│       ├── yaml_merge.py   #   Git YAML 覆盖层合并：curated_json / manual·abbr 别名 / curated 关系（§5.8 合并规则表）
│       ├── sync.py         #   同步流程编排：删除比例保护 → 分批 upsert → missing/retired → 别名重建 → 触发构建（§5.8）
│       └── adapters/       #   源系统同步适配器（SourceAdapter 协议，只读、幂等、输出当前快照）
│           ├── template_center.py   # template / template_field + has_field / backed_by / maps_to
│           ├── scenario_config.py   # scenario + uses
│           ├── report_center.py     # report / report_item + has_item / child_of / derived_from（源端有则同步）
│           └── metadata.py          # table / column 轻量节点 + has_column（只拉被引用到的）；describe_table 透传客户端
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
│   ├── runner.py           # 子进程入口：任务循环（租约认领/心跳/重试）；任务类型 ingest/reindex/delete + semantic_sync/semantic_build/semantic_retag（D23，限速错峰）
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

**语义模块边界规则（D23，#35 §4.4）**——防"服务职责变宽"演成大杂烩：

1. `core/semantic/` **不 import** `core/` 文档侧（ingest/retrieve/acl/quality）的内部实现，反向同样禁止；两者只共同依赖 `store/`（连接工厂、repo）与 `domain/`（鉴权、组织上下文）——**基础设施共享，领域模型与维度 ACL 编译器不共享**。
2. 交叉点只有两个，都走显式接口：**ingest 标注**——摄取流水线在块写入同事务调 `semantic.annotator.tag(chunks, org)`，版本切换/删块同事务调 `semantic.untag(doc_id, version)`；**实体召回**——`core/retrieve.py` 调 `semantic.expand(ids, rels, depth)` 只拿到实体 id 集合，召回 SQL 仍由 docs 侧编译（带 §5.1 完整 ACL 产物）。
3. `sem_*` 表与 docs 表同主库、前缀区分；迁移脚本分目录（`migrations/docs/` 与 `migrations/semantic/`）管理，语义表 M2-S1 才落库（M0a/M1 的 schema 不含）。
4. 新增实体类型或关系类型 = schema 变更（CHECK 约束 + `sem_rel_types` 种子），走迁移脚本与评审，不允许运行时自由扩展。

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

CREATE TABLE dimensions (            -- 维度定义（配置页 CRUD 对象，D9；v0.4 冻结复审：生命周期与过滤彻底解耦——#34 必修 1 方案 A）
  id            TEXT PRIMARY KEY,    -- ULID
  org_id        TEXT NOT NULL REFERENCES orgs(id),
  key           TEXT NOT NULL,       -- region / tax_type
  name          TEXT NOT NULL,       -- 作业区域 / 税种
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),  -- 生命周期：编译器只对 active 生成条件；retired=唯一放宽路径（退役权限事件，§6.2）
  required      INTEGER NOT NULL DEFAULT 1,  -- 仅控制上传校验（强制选值），不影响过滤
  enabled       INTEGER NOT NULL DEFAULT 1,  -- 仅控制上传页是否展示/选值（停用=收紧的上传体验），不影响过滤
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
  owner_user_id   TEXT NOT NULL REFERENCES users(id),  -- 文档所有者（管理面操作权限与来源展示；检索路径无 owner 分支——D22③/#34 必修 2）
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
-- #34 4.6（M0a 随 schema 落地）：搬库与脏维度双重防护——
CREATE TRIGGER trg_documents_ds_immutable BEFORE UPDATE OF dataset_id ON documents
WHEN (SELECT org_id FROM datasets WHERE id = NEW.dataset_id) != OLD.org_id
BEGIN SELECT RAISE(ABORT, 'dataset move across org is forbidden'); END;
CREATE TRIGGER trg_docdims_consistency BEFORE INSERT ON document_dimensions
WHEN (SELECT dimension_id FROM dimension_values WHERE id = NEW.value_id) != NEW.dimension_id
  OR (SELECT org_id FROM dimensions WHERE id = NEW.dimension_id)
    != (SELECT org_id FROM documents WHERE id = NEW.doc_id)
BEGIN SELECT RAISE(ABORT, 'document_dimensions consistency violation'); END;
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
CREATE UNIQUE INDEX uq_chunks_docver ON chunks(doc_id, version, seq);  -- v0.4：fetch 窗口与"按文档计算"共用（含 version——同文档多版本 seq 不唯一）；替代原 idx_chunks_doc（列相同，去重——#34 4.4）
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
  type         TEXT NOT NULL,        -- ingest | reindex | delete | semantic_sync | semantic_build | semantic_retag（后三者 M2-S——D23；语义任务限速错峰、重标最低优先级）
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

-- ============ 审计（FR-6；v0.4：audit_events 属**月库** audit_YYYYMM.db，由连接工厂在月库滚动时创建本表与触发器） ============
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

-- outbox（主库，v0.4 #34 4.5）：权限事件与业务写同事务入队，后台搬运到月库——"业务改了就一定有审计"
CREATE TABLE audit_outbox (
  id           TEXT PRIMARY KEY,
  event_type   TEXT NOT NULL,        -- grant|revoke|dimension_change|retire|membership|...
  payload_json TEXT NOT NULL,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  shipped_at   TIMESTAMP             -- NULL=待搬运；后台任务搬至月库 audit_events 后回填
);
-- v0.3（issue #32 P1-7）+ v0.4（#33 P1-4）：审计按月分库 audit_YYYYMM.db——当月可追加、过月封存只读
--   （只读打开 + 文件权限 + 封存记末哈希）、到期整文件删除；月库建表与上述触发器由连接工厂在滚动时创建；
--   **权限事件走 outbox**：业务库同事务写 audit_outbox 表，后台搬运保证"业务改了就一定有审计"

-- ============ 业务语义 sem_*（D23，#35 §6.2；M2-S1 经 migrations/semantic/ 落库，M0a/M1 不含） ============
-- 类型对齐主库约定：org_id 为 TEXT（orgs.id 是 ULID）、时间列用 TIMESTAMP；实体主键用 INTEGER（AC 自动机值与图遍历友好）
-- 实体：事实列与人工列分列存放——同步只写事实列（name/attrs_json/parent_id/status/synced_at），从不写 curated_json
CREATE TABLE sem_entities (
  id            INTEGER PRIMARY KEY,
  org_id        TEXT    NOT NULL REFERENCES orgs(id) ON DELETE RESTRICT,
  type          TEXT    NOT NULL CHECK (type IN ('concept','system','scenario','template',
                         'template_field','report','report_item','table','column')),
  key           TEXT    NOT NULL,               -- 业务主键，组织内按类型唯一；YAML 用 type:key 引用
  name          TEXT    NOT NULL,               -- 规范名
  parent_id     INTEGER REFERENCES sem_entities(id) ON DELETE CASCADE,
                                                -- 冗余的直接父节点（字段→模板、列→表、项→报表），便于展示；真相以关系为准
  attrs_json    TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(attrs_json)),
                                                -- 事实属性：编码、注释、源系统状态等，同步写入
  curated_json  TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(curated_json)),
                                                -- 人工属性：definition / why / examples / disambiguation / caliber（YAML 合并写入）
  source        TEXT    NOT NULL CHECK (source IN ('sync','curated')),
                                                -- sync：事实来自源系统；curated：纯 YAML 实体（只允许 concept/system）
  source_system TEXT,                           -- template_center / report_center / metadata / scenario_config
  status        TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active','missing','retired')),
                                                -- missing：最近一次同步源端已不存在（宽限期内，默认 7 天）；retired：已下线
  sensitivity   TEXT    NOT NULL DEFAULT 'normal' CHECK (sensitivity IN ('normal','restricted')),
                                                -- restricted：仅持 semantic:restricted 权限可见（annotate 表现为不存在——§6.3）
  synced_at     TIMESTAMP,                      -- 最近一次被同步看到的时间
  curated_rev   TEXT,                           -- 最近一次合并的 YAML commit SHA
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (org_id, type, key)
);
CREATE INDEX idx_sem_entities_org_type ON sem_entities(org_id, type, status);
CREATE INDEX idx_sem_entities_parent   ON sem_entities(parent_id);

-- 别名：AC 自动机与模糊索引都从这里构建
CREATE TABLE sem_aliases (
  id          INTEGER PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  entity_id   INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  alias       TEXT    NOT NULL,                 -- 原文
  alias_norm  TEXT    NOT NULL,                 -- 规范化后：NFKC、全角转半角、小写、去空白（与 annotate 的文本规范化同一函数）
  kind        TEXT    NOT NULL CHECK (kind IN ('name','code','manual','abbr','pinyin','sync')),
                                                -- name/code：由规范名与编码自动生成；manual/abbr：来自 YAML（同步不动）；
                                                -- pinyin：构建时生成，只进模糊索引；sync：源系统自带的别名
  match_mode  TEXT    NOT NULL DEFAULT 'exact' CHECK (match_mode IN ('exact','fuzzy_only','context')),
                                                -- context：歧义短词，只有在同句其他命中有关系时才生效（§5.9）
  weight      REAL    NOT NULL DEFAULT 1.0,
  UNIQUE (org_id, entity_id, alias_norm)
);
CREATE INDEX idx_sem_aliases_norm ON sem_aliases(org_id, alias_norm);
-- 同一个 alias_norm 允许指向多个实体（歧义），由消歧规则处理，不在这里加唯一约束

-- 关系（类型白名单见 sem_rel_types + 触发器）
CREATE TABLE sem_relations (
  id          INTEGER PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  src_id      INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  rel_type    TEXT    NOT NULL,
  dst_id      INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  attrs_json  TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(attrs_json)),
                                                -- 例如 maps_to 的转换规则、derived_from 的取数口径
  source      TEXT    NOT NULL CHECK (source IN ('sync','curated')),
  status      TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active','missing','retired')),
  synced_at   TIMESTAMP,
  UNIQUE (org_id, src_id, rel_type, dst_id)
);
CREATE INDEX idx_sem_rel_out ON sem_relations(org_id, src_id, rel_type, status);
CREATE INDEX idx_sem_rel_in  ON sem_relations(org_id, dst_id, rel_type, status);

-- 关系类型白名单与端点类型约束（迁移脚本按 §5.8 白名单灌入种子数据；新增关系类型 = schema 变更走迁移）
CREATE TABLE sem_rel_types (
  rel_type   TEXT NOT NULL,
  src_type   TEXT NOT NULL,
  dst_type   TEXT NOT NULL,
  PRIMARY KEY (rel_type, src_type, dst_type)
);
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
        AND t.dst_type = (SELECT type FROM sem_entities WHERE id = NEW.dst_id));
END;
-- 关系行不允许原地改端点：要改就先删再插，保证上面的触发器始终生效（T-S5）
CREATE TRIGGER trg_sem_rel_noupdate BEFORE UPDATE OF src_id, dst_id, rel_type, org_id ON sem_relations
BEGIN SELECT RAISE(ABORT, 'relation endpoints are immutable: delete then insert'); END;

-- 文档块 ↔ 实体：ingest 与重标注时由 AC 自动机写入（**刻意不加外键到 chunks**——理由见下方设计说明）
CREATE TABLE sem_chunk_entities (
  org_id      TEXT    NOT NULL,
  chunk_rid   INTEGER NOT NULL,                 -- = chunks.rid
  doc_id      TEXT    NOT NULL,                 -- 冗余字段，便于按文档整体删除与重标
  version     INTEGER NOT NULL,                 -- = chunks.version
  entity_id   INTEGER NOT NULL REFERENCES sem_entities(id) ON DELETE CASCADE,
  hits        INTEGER NOT NULL DEFAULT 1,       -- 块内命中次数
  dict_rev    TEXT    NOT NULL,                 -- 打标时使用的词典版本，用于判断是否需要重标
  PRIMARY KEY (chunk_rid, entity_id)
);
CREATE INDEX idx_sem_ce_entity ON sem_chunk_entities(org_id, entity_id);
CREATE INDEX idx_sem_ce_doc    ON sem_chunk_entities(doc_id, version);

-- 构建产物登记：AC 自动机、模糊索引（sem_vec BLOB 复用 sqlite-vec）、L0 片段；服务进程按 (org, dict_rev) 懒加载
CREATE TABLE sem_builds (
  id          INTEGER PRIMARY KEY,
  org_id      TEXT    NOT NULL,
  dict_rev    TEXT    NOT NULL,                 -- = hash(active 实体快照 + 别名快照 + YAML commit)
  yaml_rev    TEXT,
  sync_run_id INTEGER,
  status      TEXT    NOT NULL CHECK (status IN ('building','ready','failed')),
  stats_json  TEXT    NOT NULL DEFAULT '{}',    -- 评测指标、冲突、歧义别名、孤立节点、断链关系
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (org_id, dict_rev)
);

-- 同步运行记录
CREATE TABLE sem_sync_runs (
  id            INTEGER PRIMARY KEY,
  org_id        TEXT    NOT NULL,
  adapter       TEXT    NOT NULL,               -- template_center / report_center / metadata / scenario_config / yaml
  started_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at   TIMESTAMP,
  status        TEXT    NOT NULL CHECK (status IN ('running','succeeded','failed','aborted_guard')),
                                                -- aborted_guard：触发删除比例保护后中止、零写入（§5.8）
  stats_json    TEXT    NOT NULL DEFAULT '{}',  -- inserted / updated / missing / retired / conflicts
  error         TEXT
);
```

设计说明（v0.4）：

- **组织与库的隔离纪律**：一切检索/列表 SQL 的第一条件是 `org_id = :org`（跨组织零可见；检索路径无 owner 分支——D22③/#34 必修 2，owner 经管理面看元数据）；库过滤（`dataset_id IN (...)`）是组织内的可选收窄；维度授权与维度定义都在组织作用域内解析。
- **维度冗余的取舍**：`chunks.dims_json` 是 `document_dimensions` 的投影（多值数组），检索 SQL 按 JSON 解析编译成常量条件（§5.1）；文档维度变更时由服务层同步刷投影（UPDATE，不重嵌——D6）。**M0b 实验若选定"按文档计算"（visible_docs），dims_json 整体删除**（消除一致性维护点，§5.1）。
- **向量存 BLOB 不用 vec0**（P0-1）：vec0 的 KNN 在虚拟表内部取 top-k 后才能 JOIN 过滤，等于 post-trim；BLOB + `vec_distance_cosine()` 在 ACL 过滤后的行集上算距离，"先过滤后扫描"（扫描量 = 用户可见量）。M0b 实验对比 `chunk_vectors` 分表（4KB/块拖慢回表与放大 WAL）。
- **FTS5 五列**（v0.4）：`unicode61` 只做兜底分词；`title_seg`（3）/`content_seg`（1）/`keywords` 仅人工词（5）/`llm_keywords`（0.5~1）/`tags`（8）分列加权；查询侧同词典切分 + token 双引号包裹且内部 `"` 转义为 `""`。
- **语义表设计要点（D23，#35 §6.3）**：①**事实列与人工列分开**——同步只写 `name` / `attrs_json` / `parent_id` / `status` / `synced_at`，**从不写** `curated_json`，也不动 `kind IN ('manual','abbr')` 的别名："同步不覆盖人工内容"由列级分工保证，不依赖代码自觉（T-S1）；②**`sem_chunk_entities` 不加外键到 `chunks`**——`chunks` 走版本在用制与墓碑机制，清理由 docs 在删块/版本切换时**同事务**调 `semantic.untag(doc_id, version)`，另有定时对账任务兜底（T-S10），避免语义表反向约束文档核心表；③**`missing` 宽限期**（默认 7 天后转 `retired`）与同步侧**删除比例保护**（§5.8）双保险，防源系统接口偶发空返回把图清空；④`sensitivity='restricted'` 实体只有持 `semantic:restricted` 权限的调用方可见（annotate 不返回 span、get_entity 404、展开不出现——T-S9）；⑤`parent_id` 只是展示用冗余，真相以 `has_field` / `has_column` / `has_item` 关系为准，同步时两者同事务写入；⑥组织隔离硬约束：全部 `sem_*` 表带 `org_id`、关系端点同组织由触发器校验（T-S5/T-S7）。

## 5. 关键设计

### 5.1 维度 ACL 编译器（core/acl.py）

输入：`user_id` + 组织上下文（REST=`X-Org-Id` 头 / MCP=token org claim 优先、运行时注入头兜底——D18 统一规则）；输出：可下推进召回 SQL 的 WHERE 片段（**结构化 builder 生成 AST 再渲染 SQL，禁止字符串拼接**）。逻辑（v0.4：**全部状态字段进入计算——P0-1**）：

1. **成员关系校验**（第 0 步，含过期）：`(SELECT role FROM user_org_memberships WHERE user_id=:uid AND org_id=:org AND (expires_at IS NULL OR expires_at > :now))`——无有效行即拒绝（系统管理员豁免仅限管理端点，D22）。**读路径只过滤、不删除**（避免检索请求抢 WAL 写锁并连带写 outbox——#34 4.2）；过期行的物理删除交**定时任务**（触发 cleanup 级联清授权 + 审计）。**续期禁令由触发器从机制上保证**（T2/T23）：

```sql
CREATE TRIGGER trg_membership_no_extend
BEFORE UPDATE OF expires_at ON user_org_memberships
WHEN OLD.expires_at IS NOT NULL AND OLD.expires_at <= CURRENT_TIMESTAMP
BEGIN SELECT RAISE(ABORT, 'expired membership: delete then re-add'); END;
```
2. **授权展开**（含过期与停用，同一条 SQL）：

```sql
SELECT dim.key, v.value
FROM user_dimension_grants g
JOIN dimensions       dim ON dim.id = g.dimension_id AND dim.org_id = :org AND dim.status = 'active'  -- 只展开 active 维度（#34 必修 1）
JOIN dimension_values v   ON v.id   = g.value_id     AND v.status = 'active'   -- 停用取值=收紧（T3）
WHERE g.user_id = :uid
  AND (g.expires_at IS NULL OR g.expires_at > :now)                            -- 过期授权即失效（T1）
```

3. 对每个 **`status='active'`** 的维度编译统一模板（#34 必修 1 方案 A + 必修 3——`json_each` 是表值函数不能 `IS NULL`）：

```sql
( NOT EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.k'))          -- 维度空值 → 不过滤（放行）
  OR EXISTS (SELECT 1 FROM json_each(c.dims_json, '$.k') je
             WHERE je.value IN (:grants_k)) )                        -- 有值 → 需与授权集有交集
```

**全部 active 维度统一"有值则过滤、空值不过滤"**（必选/可选、启用/停用无差别——required/enabled 不影响过滤，只管上传）；**用户在维度 k 无授权（:grants_k 为空集）→ 编译器直接生成 `NOT EXISTS(...)` 单条件**（该用户只能看到 k 为空的文档，非"整体不可见"——#34 必修 3；空集**禁止**生成 `IN ()` 语法）；`retired` 维度不生成条件（唯一放宽路径，走退役权限事件）；**新增维度时零存量文档消失**（全空值放行），回填即逐篇收紧（上传页与管理页对空值文档提示"待补维度"）；必选改可选、停用均不放宽（T4/T20）。
4. **无 owner 分支**（#34 必修 2 推荐方案）：检索路径只有维度 ACL 一种语义；owner 查看自己处理中/在用文档走 `list_documents` 与文档详情接口（管理面，只返回元数据与状态，不返回块内容）——彻底消除"覆盖上传处理中窗口重新看到在用全文"的 T17/T21 越权路径。

编译产物（示意——统一模板 + 外层约束 + 版本限定，#34 必修 1/2/3）：

```sql
-- 组织 org:tax 内，用户 region=[CN, OVERSEAS]、tax_type=[VAT]；两维度均 active；文档维度多值（D19）
SELECT c.* FROM chunks c JOIN documents d ON d.id = c.doc_id
WHERE ( ( NOT EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.region'))            -- region 空值放行
          OR EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.region') je WHERE je.value IN ('CN','OVERSEAS')) )
      AND ( NOT EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.tax_type'))
          OR EXISTS(SELECT 1 FROM json_each(c.dims_json,'$.tax_type') je WHERE je.value IN ('VAT')) ) )
      -- 无 owner 分支（必修 2）；无授权维度编译为 NOT EXISTS(...) 单条件（必修 3）
  AND c.version = d.active_version AND c.tombstone = 0     -- 只召回在用版本（P0-A/P0-2）
  AND d.org_id = 'org:tax' AND d.dataset_id IN (...) AND d.id IN (:doc_filter)
-- FTS 路同构：FROM chunks_fts f JOIN chunks c ON c.rid = f.rowid JOIN documents d ... WHERE f.chunks_fts MATCH :q
--   AND <同上全部条件>（版本条件必须出现在 FTS 路的 JOIN 上——T9 断言 FTS 层无 tombstone 命中）
```

性能注（v0.4）：
- **按文档计算备选（M0b 实验）**：`visible_docs` CTE 用**同一个授权展开函数**（第 2 步 SQL）先求可见文档集合，再 `WHERE c.doc_id IN (visible_docs)` 走 `uq_chunks_docver`——**基于 `document_dimensions` 写出等价语义**（文档在维度 k 无任何行，或有一行 value ∈ 授权集——与统一模板逐字等价，T5/T6/T22 两种写法都测，#34 必修 3）；胜出则删 dims_json；
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
     ├─→ 实体召回路（**M2-S3 可选，D23**——调用方传 entities 或 auto_entities=true 才启用；§5.10）：
     │    semantic.expand(seed, ENTITY_RECALL_RELS, depth=1) → 实体集合 E（≤50）→
     │    SELECT c.rid, SUM(ce.hits × 权重) FROM sem_chunk_entities ce JOIN chunks c JOIN documents d
     │    WHERE ce.entity_id IN E AND <与上两路**完全相同**的 ACL 编译产物 + 版本条件>   -- ← 不另写 ACL
     ─→ RRF 融合（k=60；向量缺失的 chunk 只在 BM25 路，自然退化单路；实体路 k 相同、权重可配默认 1.0）
     ─→ ACL 兜底断言（rerank 前：不该进模型的内容不进模型——P2-4 统一）
     ─→ 取 top-32 → rerank（bge-reranker-v2-m3，ONNX int8，喂 content 原文）
     ─→ 分数归一 [0,1]（min-max/clamp 双分支，ragflow 模式）
     ─→ 返回前二次 ACL 断言 → top-k（≤20，含 chunk_id/doc_id/title/page_no/score/dims/source；M2-S3 起附 matched_entities）
```

要点：召回期不做用户阈值过滤（dify #35233 教训）；阈值只作用于归一后的最终分；**useful-early 语义**由"向量 BLOB 可空 + 先过滤后距离"自然成立——`embedding IS NULL` 的 chunk 只走 BM25 路，摄取中的文档即刻可搜（FR-1 阶段拆分）；**CPU 推理（query 嵌入 + rerank）放线程/进程池，绝不阻塞事件循环**；rerank 并发上限信号量保护；`top_k` 服务端硬上限 20。性能预算与 SLO（P95 ≤ 2s）见需求 NFR-8，M1 实测校准。**实体召回路（D23）**：三路（FTS/向量/实体）必须使用**同一个** ACL 编译产物（T-S8 断言三路并集 ⊆ 用户可见块集合）；M2-S3 在 docs 黄金集上做开/关对比，recall@10 与 MRR **不回退**才允许 `auto_entities` 默认开启，否则保持显式参数。

### 5.3 摄取管线与 worker（core/ingest.py + worker/runner.py）

任务状态机：`pending → leased → running → (done | failed)`；worker 心跳 5s、租约 60s，租约过期任务可被重认领；`attempts ≥ 3` 进 failed 留人工。断点粒度 = 阶段（各阶段幂等，重跑从上一完成阶段续）。SQLite 写竞争治理（NFR-9）：`busy_timeout` + worker 短事务分批提交 + **查询级审计异步写、权限事件走 outbox**（月库与业务写天然隔离——#34 4.5）。

阶段编排（**P0-4 拆分：index_fts 先于 embed，BM25 即刻可搜**；upload 时新维度写 `pending_dims_json`、写权限校验在 upload 即做——P0-2.1）：

```
parse（docling→统一块结构；扫描件路由 MinerU；mojibake 质量门；TXT 编码探测）
→ chunk（结构感知切分 256–512 / Excel 按 sheet 行块（重复表头）；jieba 生成 content_seg）
→ index_fts（chunks + FTS 同一事务；**M2-S3 起同事务追加语义打标**：`semantic.annotator.tag(chunks, org)` 用当前 ready 的
     AC 自动机只做第 1 层识别写 sem_chunk_entities（不跑模糊兜底）；打标失败不阻断——记 warning、标记文档待重标，
     交 semantic_retag 补做——D23/#35 §8.4；文档状态 → searchable_lexical）
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
       active_status  = pending_status,               -- 首次切换=searchable_lexical；覆盖切换=searchable_full（#34 4.1）
       pending_version = NULL, pending_status = NULL, pending_error = NULL
 WHERE id = :doc AND pending_version = :expected_pending;   -- 乐观校验，防并发（P0-2.3/T7）
-- 同事务：pending_dims_json 解析写入 document_dimensions（P0-2.1——v2 维度切换前不生效，T6）
-- 同事务（M2-S3 起，D23）：semantic.untag(:doc, :old_version) 清旧版本块的 sem_chunk_entities 行（T-S10）；
--   删除文档 / 失败版本删块同样同事务 untag；另有定时对账任务兜底（sem_chunk_entities 刻意不加外键到 chunks——§4 设计说明）
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
- **agent 代人检索（D18）**：**委托 token（Token Exchange）**——`aud=knowledge-lattice`、短 TTL、`sub`=用户、`act`=agent 标识进审计；拒绝 token 原样透传与请求体权限字段。**降级（v0.3）**：IdP 不支持时走**可信子系统**——agent 服务自身凭证（mTLS/服务 token）须在服务白名单，请求头 `X-On-Behalf-Of: <user_id>` 声明用户，知识库校验白名单后按声明用户计权、双身份（服务+用户）进审计；数据模型与 D18 一致（弱化 act/sub）。静态 token 仅开发/测试（含 CI）。
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

五个视图（文档 / 检索测试 / 权限 / 语义层 / 任务与审计——原型 v0.5），由 FastAPI 托管静态文件，无构建工具（原生 HTML/JS + 少量 fetch），**UI 永远是薄壳**——所有能力先有 API 契约（§6）再有页面；M2 管理面（权限 / 语义层视图）**先 API + 最小 UI**（完整页面后置，issue #31 P2）。交互原型见 `prototype/index.html`（v0.5，issue #36；mock 数据、浏览器直接打开），**信息结构与 UI 风格均为实现基准**，逐视图对接 REST。语义层视图（同步记录、冲突报告、实体浏览）原型已含，实现仍为可选项（D23，非必需，随 M2-S3）。

**实体浏览按规模设计**（§5.8 口径：10⁴~10⁵ 节点，模板字段 / 报表项 / 列等叶子约占 97%），**不做常驻的全量实体列表**（侧栏窄列塞不下 486 个模板，任何竖列都不行）：①默认落地为**类型总览**——九类卡片携全图计数（根类型可浏览，叶子标注「经父节点 / 搜索直达」）+ 需要关注项（missing / 冲突 / 受限）；②**搜索为主入口**——对应 `search_entities` / `GET /semantic/entities?q=&types=`，命中以**全宽结果表**呈现（名称 / 类型 / 键 / 别名 / 关系数 / 状态 / 来源，类型内按名称排序），只显示 top-N 并在截断时明示（服务端 top_k ≤ 50）；③**类型 facet 单选**（对应 `types=` 参数取一——九类是互斥主轴而非可叠加标签，跨类型发现走「全部 + 搜索」；总览卡片与筛选胶囊同一状态，再点一次取消）；④**实体详情独立成页**——返回按钮 + 父级面包屑 + 关系列表 + 关系图；⑤**关系图与关系列表同口径：按（关系类型 × 方向）分组、每组最多 3 个端点**——连线颜色区分关系类型，组内超出以「+N 更多」计数占位（点击即在列表展开该实体全量关系），分组 × 封顶天然限定图的规模：模板被上百个场景使用时呈现「3 个代表 + 计数」而非不可读的毛球，因此无需另设聚合降级模式；深度 2 只沿已展示端点扩展、每点同样封顶 3；整页受 depth ≤ 2 / fanout_limit ≤ 200 / `truncated` 语义约束。原型 mock 渲染 42 个实体（含「10 个场景共用同一模板」「12 列宽表」两个高扇出样本），计数与截断提示按真实规模口径展示。

### 5.8 语义层：同步、YAML 覆盖层与构建（core/semantic/，D23——#35 §6.1/§7）

**定位**：业务语义 = 术语 + 业务对象关联，建模为**类型化对象图**（属性图：实体 + 有类型的关系）。关系本来就写在业务系统配置里，**直接同步，不用 LLM 从文本抽取**（不做 GraphRAG）；规模 10⁴~10⁵ 节点、边为节点 1~3 倍、查询为 1~3 跳有起点的局部遍历——SQLite + 递归 CTE 毫秒级，**不引入图数据库**（同时出现节点 >10⁶、常需 4 跳以上、需全图算法时再评估 openCypher 嵌入式方案；数据模型按属性图设计，迁移不改模型）。局部借鉴 GraphRAG 的一点：文档块 ↔ 实体关联（`sem_chunk_entities`），但由 AC 自动机确定性打标、不调 LLM。

**实体类型与关系类型白名单**（代码常量 + `sem_rel_types` 种子 + 触发器三处一致）：

| type | 含义 | 事实来源 | 典型 key |  | rel_type | src → dst | 基数 | 来源 |
|---|---|---|---|---|---|---|---|---|
| `concept` | 业务概念 | YAML | `vat.input_credit` |  | `uses` | scenario → template | N:M | 场景配置 |
| `system` | 系统/平台名词 | YAML | `sys.tax_hub` |  | `has_field` | template → template_field | 1:N | 模板中心 |
| `scenario` | 作业场景 | 场景配置中心 | 场景编码 |  | `backed_by` | template → table | N:1（允许 N:M） | 模板中心 |
| `template` | 模板 | 模板中心 | 模板编码 |  | `maps_to` | template_field → column | N:1 | 模板中心 |
| `template_field` | 模板字段 | 模板中心 | `模板编码.字段编码` |  | `has_item` | report → report_item | 1:N | 报表中心 |
| `report` | 报表 | 报表中心 | 报表编码 |  | `child_of` | report_item → report_item | N:1 | 报表中心 |
| `report_item` | 报表项（树） | 报表中心 | `报表编码.项编码` |  | `derived_from` | report_item → template_field / column | N:M | 报表中心或 YAML |
| `table` | 业务表（轻量节点） | 元数据系统 | `db.table` |  | `has_column` | table → column | 1:N | 元数据系统 |
| `column` | 列（轻量节点） | 元数据系统 | `db.table.column` |  | `refers_to` | concept / system → 任意实体 | N:M | YAML |
|  |  |  |  |  | `related_to` | concept → concept | N:M | YAML |

**三种内容的分工**（「源端事实」＝源系统已有的具体对象与关系——名称、编码、层级、关系边；旧称「骨架」，2026-10-19 改称，[#35](https://github.com/yq3/lab/issues/35) 原文仍用旧称）：

| 内容 | 示例 | 谁维护 | 存在哪 | agent 怎么用 |
|---|---|---|---|---|
| 源端事实 | 模板编码与名称、字段列表、模板→表、字段→列、场景→模板、报表项树 | 同步适配器（自动，每日） | `sem_entities` / `sem_relations` 事实列 | `get_entity` 展开关系 |
| 人工内容 | 别名、缩写、定义、口径、消歧、示例、L0 标记 | 业务/数据同学，Git PR 评审 | Git YAML → `curated_json` / `sem_aliases(manual,abbr)` / curated 关系 | `annotate` 识别、`get_entity` 读说明 |
| 详情 | 列类型、样例值、分区、血缘 | 元数据系统 | **不落库** | `describe_table` 实时透传 |

**同步适配器接口**（`core/semantic/adapters/`，只读拉取、幂等、输出始终是"当前快照"）：

```python
class SourceAdapter(Protocol):
    name: str                       # template_center / scenario_config / report_center / metadata
    def fetch(self, org: str) -> Iterable[EntityRecord | RelationRecord]: ...

@dataclass
class EntityRecord:
    type: str; key: str; name: str
    parent_key: str | None          # 例如 template_field 的父节点是 template:TPL_xxx
    attrs: dict                     # 编码、注释、源端状态等
    aliases: list[str] = ()         # 源系统自带的别名 → kind='sync'

@dataclass
class RelationRecord:
    src: tuple[str, str]            # (type, key)
    rel_type: str
    dst: tuple[str, str]
    attrs: dict = None
```

| 适配器 | 产出实体 | 产出关系 | 频率 |
|---|---|---|---|
| `template_center` | template、template_field | has_field、backed_by、maps_to | 每天 + 手动触发 |
| `scenario_config` | scenario | uses | 每天 |
| `report_center` | report、report_item | has_item、child_of、derived_from（如源端有） | 每天 |
| `metadata` | table、column（**只拉被 backed_by/maps_to 引用到的** + YAML 显式列出的，不全量镜像） | has_column | 每天 |
| `yaml` | concept、system；其他类型的覆盖层 | refers_to、related_to、人工补的 derived_from | Git 合并后 webhook 触发 + 每天一次兜底 |

**同步流程（每个适配器一次 run，`core/semantic/sync.py`）**：

1. `sem_sync_runs` 插入 `running` 记录；
2. `fetch()` 拿快照，构建 `(type, key)` 集合；
3. **删除比例保护**：快照相对库内该来源（`source='sync' AND source_system=本适配器 AND status='active'`）的消失比例超阈值（默认 20%）→ run 置 `aborted_guard`、发告警、**不做任何写入**（T-S2）；
4. 单个写事务内（必要时分批，每批 ≤1000 行）：①实体 `ON CONFLICT(org_id,type,key) DO UPDATE` **只更新事实列** + `status='active'`、`synced_at=now`；②快照里没有但库里该来源 active 的实体 → `missing`；③`missing` 超宽限期（默认 7 天）→ `retired`，其关系一并 `retired`（T-S4）；④关系 upsert，端点解析不到的记冲突不写入；⑤重建 `kind IN ('name','code','sync')` 别名（先删后插，**只动这三种 kind**）；
5. 更新 run 状态与 `stats_json`，投递 `semantic_build`；
6. 写审计 outbox 事件 `semantic.sync`（run id + 统计）。

**幂等性**：同一份快照连续跑两次，第二次 inserted / updated / missing 均为 0（T-S3）。

**YAML 规范**（`semantic/` 独立 Git 仓或 lab 子目录：`_schema/*.schema.json` + `concepts/` + `templates/` + `report_items/` + `scenarios/` + `l0.yaml`；过渡期即按此 schema 建仓，迁移零改动）：

```yaml
# concepts/vat.yaml —— 纯人工实体（只允许 concept / system）
- id: concept:vat.input_credit          # type:key，全局唯一，CI 校验
  name: 进项税额抵扣
  aliases: [进项抵扣, 抵进项, 认证抵扣]
  abbr: [JXDK]
  definition: >
    一般纳税人购进货物、服务等取得合规扣税凭证后，按规定从销项税额中抵减的进项税额。
  why: 影响当期应纳税额，是增值税申报的核心环节。
  examples: [本月进项抵扣怎么算, 抵进项的发票有哪些要求]
  disambiguation:
    - not: concept:vat.input_transfer_out
      hint: 进项转出是抵扣后因用途改变需要转回，方向相反
  refers_to: [template:TPL_VAT_INPUT, report_item:VAT_MAIN.L12]
  l0: true                               # 进 system prompt（受 L0 预算约束，默认 1500 token）
  sensitivity: normal
  owner: tax-domain                      # CI 必填

# templates/TPL_VAT_INPUT.yaml —— 覆盖层：按 id 挂到同步来的实体上（未同步到的 CI 只警告）
- id: template:TPL_VAT_INPUT
  aliases: [进项采集模板, 进项模板]
  definition: 月度进项发票采集模板，按发票逐行采集。
  caliber: 只采集当期勾选认证的发票，不含海关缴款书。
  fields:
    - id: template_field:TPL_VAT_INPUT.TAX_AMT
      aliases: [税额, 进项税额]
      definition: 发票票面税额
  extra_relations:                       # 源系统缺失的关系，人工补充
    - { rel: derived_from, from: report_item:VAT_MAIN.L12, to: template_field:TPL_VAT_INPUT.TAX_AMT,
        note: 报表中心暂未配置取数关系，按业务口径人工补充 }
```

**合并规则与冲突处理**（`yaml_merge.py`；CI 在合并前拦截，入库时触发器兜底）：

| 情形 | 处理 |
|---|---|
| 覆盖层引用的 id 已同步 | 合并：写 `curated_json`、`manual`/`abbr` 别名、`source='curated'` 关系，记 `curated_rev` |
| 覆盖层引用的 id 未同步或已 retired | 不写入，记冲突，CI 与构建报告给警告；实体恢复后自动生效 |
| 纯人工实体与同步实体 `(type,key)` 相同 | 报错，CI 拦截（纯人工实体只能是 concept/system） |
| 同一别名指向多个实体 | 允许，但 CI 要求至少一方 `disambiguation` 说明，或别名标 `match_mode: context` |
| 别名短于 2 字或是常用词 | CI 拦截，除非显式标 `context` 或 `fuzzy_only` |
| `extra_relations` 与同步关系重复 | 以同步为准，人工条忽略并提示"可删除" |
| `extra_relations` 端点类型不在白名单 | CI 拦截；入库时触发器兜底（T-S5） |
| YAML 删除某覆盖项 | 清空对应实体 `curated_json` 与 manual 别名；事实列不受影响 |
| L0 总 token 超预算（默认 1500） | CI 拦截 |

**构建产物（`semantic_build`，同步或 YAML 合并后触发）**：

1. `dict_rev = hash(active 实体 + 别名 + yaml commit)`，与当前 ready 版本相同则跳过；
2. 产物：**AC 自动机**（`pyahocorasick`，键 `alias_norm`、值 `entity_id` 列表，只收 `match_mode IN ('exact','context')`）；**模糊索引**（名称/别名/一句话定义的 bge-m3 向量存 `sem_vec` BLOB 复用 sqlite-vec，外加拼音与编辑距离辅助表——M2-S3）；**L0 片段**（`l0: true` 条目渲染 markdown，`GET /semantic/l0` 导出）；**构建报告**（冲突、歧义别名、孤立节点、断链关系、评测指标）；
3. **原子切换**：`sem_builds` 新版本置 `ready`；服务进程按 `(org, dict_rev)` 懒加载，旧版本保留到无请求使用（构建中请求始终用旧 `dict_rev`，构建失败旧版本继续服务——T-S12）；**评测回归**：构建报告指标较上一版下降 >2 个百分点则不切 ready，需人工确认；
4. **重标判断**：词典变更涉及别名增删即投递 `semantic_retag`，对 `dict_rev` 落后的文档块分批重新打标——最低优先级、限速，不与 ingest 抢资源。

### 5.9 识别（annotate）与关系展开（get_entity）（core/semantic/annotator.py · expand.py）

**总体时序**：

```
用户问题
  ├─① annotate(text)        AC 自动机确定性匹配 → 歧义消解 → [模糊兜底]
  │       └→ mentions: [{span, entity_id, type, confidence, via, ambiguous, brief}]
  ├─② agent 中间件按类型注入 L1：概念的定义与消歧提示、对象的规范名一行（§6.3）
  ├─③ agent 自主调用 L2：get_entity(id, expand, depth≤2) → 结构化子图；
  │                       search(q, entities=[...]) → 文档证据（带 ACL，§5.10）；
  │                       describe_table(table) → 列详情（实时透传）
  └─④ 组装回答：结构化子图（对象及关联）+ 文档证据（制度、口径）
```

**annotate 三层识别**：

- **第 1 层 AC 自动机（确定性、必跑，P99 < 5ms）**：①文本规范化与 `alias_norm` 同一函数（NFKC、全半角统一、小写——抽成小 package 与过渡期本地版共用）；②最长匹配：重叠保留更长 span，等长按 `weight` 取高；③一个 span 对应多个实体时按序消歧：**上下文共现**（同句其他命中实体与候选有 1 跳关系）→ **会话焦点**（调用方传 `context_entities`，最近几轮已确认的实体）→ **类型先验**（`prefer_types`）→ 仍不定则返回全部候选并标 `ambiguous=true`，交 agent 追问或自判；④`match_mode='context'` 短别名：仅当同句有其他确定命中且两者有关系时保留，否则丢弃；⑤`restricted` 实体对无权调用方表现为不存在（不返回 span）。
- **第 2 层 agentic**：第 1 层未命中但 agent 判断有业务对象 → 自主调 `search_entities(q, types?)`（排序：别名精确 > 前缀 > 拼音 > 向量）；**不在 annotate 内部执行**。
- **第 3 层模糊兜底（`fuzzy=true` 才跑，M2-S3）**：对未被第 1 层覆盖、长度 ≥2 的名词性片段（jieba 词性筛选）依次：拼音完全匹配（同音错字，"留底"→"留抵"）→ 编辑距离 ≤1（仅长度 ≥4 别名）→ 向量近邻 top-3（阈值 0.75）。结果 `confidence` 一律低于第 1 层、`via='fuzzy'`，**中间件不自动注入**，只作候选提示。

**关系展开：递归 CTE 类型化 2 跳（`expand.py`，服务端强制 depth ≤ 2）**：

```sql
-- :org、:start_ids（json 数组）、:rels（允许的 rel_type，json 数组）、:max_depth（≤ 2，服务端强制）
WITH RECURSIVE walk(entity_id, depth, path, via) AS (
  SELECT je.value, 0, ',' || je.value || ',', NULL
    FROM json_each(:start_ids) je
  UNION ALL
  SELECT CASE WHEN r.src_id = w.entity_id THEN r.dst_id ELSE r.src_id END,
         w.depth + 1,
         w.path || (CASE WHEN r.src_id = w.entity_id THEN r.dst_id ELSE r.src_id END) || ',',
         r.rel_type || CASE WHEN r.src_id = w.entity_id THEN '>' ELSE '<' END
    FROM walk w
    JOIN sem_relations r
      ON r.org_id = :org AND r.status = 'active'
     AND (r.src_id = w.entity_id OR r.dst_id = w.entity_id)
     AND r.rel_type IN (SELECT value FROM json_each(:rels))
   WHERE w.depth < :max_depth
     -- 防环：路径里已出现过的节点不再访问（T-S6）
     AND instr(w.path, ',' || (CASE WHEN r.src_id = w.entity_id THEN r.dst_id ELSE r.src_id END) || ',') = 0
)
SELECT e.id, e.type, e.key, e.name, MIN(w.depth) AS depth, GROUP_CONCAT(DISTINCT w.via) AS via
  FROM walk w JOIN sem_entities e ON e.id = w.entity_id
 WHERE e.org_id = :org AND e.status = 'active'
   AND (e.sensitivity = 'normal' OR :can_restricted = 1)         -- restricted 过滤（T-S9）
 GROUP BY e.id
 ORDER BY depth, e.type
 LIMIT :limit;                                                    -- 默认 200，服务端上限 500
```

说明：①实现时把出边/入边拆成两个 UNION 分支分别走 `idx_sem_rel_out` / `idx_sem_rel_in`（上面为可读写成 OR）；②**高扇出截断**：如一个表下几百列，每节点最多保留 `fanout_limit`（默认 50、上限 200）条并在结果标 `truncated=true`；③典型路径——"场景 X 用到哪些表"：`uses>` + `backed_by>` 深度 2；"字段 F 对应哪个列、哪些报表项从它取数"：`maps_to>` + `derived_from<` 深度 1；④`get_entity` 的 `expand` 参数即 `:rels`（可带方向后缀 `>`/`<`）。

### 5.10 实体召回路：与文档检索的融合（core/retrieve.py ↔ semantic.expand，M2-S3）

1. 调用方传 `entities=[id...]`（≤20）；或 `auto_entities=true` 由服务端对 query 先执行一遍第 1 层识别；
2. `semantic.expand(ids, rels=ENTITY_RECALL_RELS, depth=1)` 得实体集合 E，**限制 ≤50**；`ENTITY_RECALL_RELS` 默认 `refers_to` / `has_field` / `maps_to` / `related_to`——**不沿 `uses` 这类高扇出关系展开**，避免召回发散；
3. 在 FTS 路与向量路之外新增**实体召回路**（`docs` 侧编译，语义层只提供 E）：

   ```sql
   SELECT c.rid, SUM(ce.hits * CASE WHEN ce.entity_id IN (SELECT value FROM json_each(:seed_ids))
                                    THEN 1.0 ELSE 0.5 END) AS s        -- 种子实体 1.0、扩展实体 0.5
     FROM sem_chunk_entities ce
     JOIN chunks c    ON c.rid = ce.chunk_rid
     JOIN documents d ON d.id = c.doc_id
    WHERE ce.org_id = :org
      AND ce.entity_id IN (SELECT value FROM json_each(:entity_ids))
      AND <与 §5.1 完全相同的维度 ACL 编译产物>       -- 复用 docs 编译器产物，不另写
      AND c.version = d.active_version AND c.tombstone = 0
    GROUP BY c.rid
    ORDER BY s DESC
    LIMIT :k_entity;                                    -- 默认 30
   ```

4. 三路 RRF 融合（实体路 k 与其他路相同，权重可配默认 1.0）→ ACL 兜底断言 → reranker（§5.2 顺序不变）；
5. **ACL 不变式**：实体召回路必须走与 FTS 路、向量路**同一个**维度 ACL 编译产物——**T-S8 断言**：同一用户、同一查询下三路结果的并集 ⊆ 其可见块集合；对无权文档里命中实体的块，实体路也召回不到。语义层只提供实体 ID，**不能给文档可见性开任何后门**；
6. 返回的每个块附 `matched_entities`，供 agent 解释"为什么召回了这段"。

## 6. 接口契约

### 6.1 MCP 工具（mcp/server.py，FastMCP——单一 server 分 docs / semantic 两组注册，D23；本节为 docs 组，semantic 组见 §6.3）

```jsonc
// search —— 工具描述（写给 LLM）："检索企业知识库。缺私有信息（制度/手册/申报口径）时调用；
// query 越具体越好（含税种、区域、文档关键词）；返回结果自带 chunk_id 溯源，回答时请引用。"
{
  "name": "search",
  "input":  { "query": "string", "top_k": "int=8",
              "datasets": "string[]? = 限定知识库 id（缺省搜全部权限内文档）",
              "doc_filter": "string[]? = 文档 id 过滤",
              "entities": "int[]? ≤20 = 实体 id，启用实体召回路（M2-S3，D23——§5.10）",
              "auto_entities": "bool=false = 服务端先对 query 跑一遍 AC 识别再实体召回（M2-S3）" },
  "output": {
    "results": [{
      "chunk_id": "01J…", "doc_id": "01J…", "dataset": "VAT 实务库",
      "title": "2026 Q3 中国区 VAT 申报指南",
      "page_no": 12, "score": 0.87,
      "dims": { "region": ["CN"], "tax_type": ["VAT"] },   // ← 多值数组（D19）
      "source": "user:u1 | agent:tax-copilot",              // ← 来源随结果返回（agent 代传可识别）
      "snippet": "…一般纳税人销售自产货物并提供安装服务的，应分别核算…",
      "matched_entities": [101, 305]                        // ← 实体召回路命中（M2-S3；未启用时省略）
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
//   ③ LLM 调 upload(upload_id, ...)——校验 sub、org、服务身份三者一致，且未过期、未使用、哈希匹配后进摄取（T11）
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
| PATCH | /api/orgs/{org}/dimensions/{id} | 维度修改（enabled/required 仅影响上传，**不影响过滤**——D5 v0.4；生命周期 status 由退役端点管理） |
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
| POST | /api/orgs/{org}/semantic/annotate | **语义层（D23，M2-S）**：术语识别，同 MCP `annotate`（`semantic:read`） |
| GET | /api/orgs/{org}/semantic/entities?q=&types= | 实体检索，同 `search_entities`（`semantic:read`） |
| GET | /api/orgs/{org}/semantic/entities/{id}?expand=&depth= | 实体详情与关系展开，同 `get_entity`（`semantic:read`） |
| GET | /api/orgs/{org}/semantic/tables/{key}/describe | 表/列详情透传元数据系统，同 `describe_table`（`semantic:read`；仅已登记 table） |
| GET | /api/orgs/{org}/semantic/l0 | 导出 L0 片段（agent 构建期拉取进 system prompt，返回 `dict_rev`；`semantic:read`） |
| POST | /api/orgs/{org}/semantic/sync/{adapter} | 手动触发同步（`semantic:admin`；写 outbox） |
| POST | /api/orgs/{org}/semantic/yaml/webhook | Git 合并后的回调（校验签名；服务身份）→ 投递 yaml 合并 + 构建 |
| GET | /api/orgs/{org}/semantic/builds · sync-runs | 构建记录 / 同步记录与冲突报告（`semantic:admin`） |
| POST | /api/search | 检索（检索测试页；参数同 MCP search；组织经 `X-Org-Id`——本端点为例外，兼容检索页） |
| POST | /api/uploads | **上传凭证签发**（{filename,size,sha256,content_type} → {upload_id, upload_url, expires_at}；**绑定 sub+org+服务身份**，#33 P1-3） |
| PUT | /api/uploads/{upload_id} | **接收文件字节**（v0.4 补——Bearer 鉴权 + **校验 sub、org、服务身份三者一致且未过期、未使用**（与签发绑定，T11）；按声明 size 截断/拒绝、写盘后校验 sha256、全局上限 200MB；**M1 集成期实现**，人工 multipart 不依赖） |
| GET | /api/orgs/{org}/audit | 审计查询（org_admin 全量 / 系统管理员仅元数据——FR-6 分级） |
| POST | /api/dev/token | 签发静态 token（**仅 dev/test 配置注册该路由，生产环境 404**——P1-7；只能给自己签或系统管理员签发） |

鉴权：所有端点要求 Bearer token（委托 token 或 SSO）；**可信子系统走服务凭证（mTLS/服务 token 白名单）+ `X-On-Behalf-Of` + 用户在场证据（D18）**；写操作经 outbox 落审计。**语义层权限（D23）**：`semantic:read`（组织成员默认具备——业务对象组织内默认可见）/ `semantic:admin`（org_admin：同步触发、构建与冲突报告）/ `semantic:restricted`（极少数敏感实体的可见权，访问进权限审计）；组织上下文规则与 §5.5 完全一致（`/api/orgs/{org}` 路径 / token org claim），语义层**不复用维度 ACL 编译器**（见 §6.3 权限口径）。

### 6.3 semantic 工具组与 agent 中间件（D23，M2-S1~S3——取代 v0.4「与术语层 glossary-agent 的工具组集成」）

**形态变化**：v0.4 的 D17 让 deepagents 并挂两个 MCP server（本系统 + glossary-agent 的 `lookup_terms`），运行时投影只列为演进点。D23 改为**单一 MCP server 按 docs / semantic 两组注册工具**——glossary-agent 不再独立部署，其调研结论（AC 自动机精确匹配、三层渐进披露、Git YAML/PR 治理、四类黑话分治）成为 `core/semantic/` 的设计输入；v0.4 预留的 `adapters/glossary_loader.py` 位取消。**职责边界不变的部分**：表/列详情真相在元数据系统（本系统只存轻量节点，`describe_table` 实时透传）；L0 核心术语是构建产物（经 `GET /semantic/l0` 导出进 agent system prompt）。

**semantic 组工具清单**（与 docs 组同 server；M2-S1 先交付 `get_entity` / `search_entities` / `describe_table`，M2-S2 交付 `annotate`，M2-S3 交付 `search` 的实体参数与模糊兜底）：

| 工具 | 用途 | 关键限制 |
|---|---|---|
| `annotate` | 识别文本中的业务术语与业务对象（概念、系统、场景、模板、模板字段、报表项、表、列），返回实体 ID 与位置；每轮对话前由中间件调用 | 文本 ≤ 4000 字；AC 层 P99 < 5ms、整体 P99 < 20ms（NFR-11） |
| `search_entities` | 按名称、别名、描述查实体（agentic 第 2 层） | `top_k ≤ 50`；排序：别名精确 > 前缀 > 拼音 > 向量 |
| `get_entity` | 读取实体详情并展开类型化关系 | `depth ≤ 2`、节点 ≤ 500、`fanout_limit ≤ 200` |
| `describe_table` | 透传元数据系统查询表与列详情 | 只对已登记的 `table` 实体开放；超时 3s + 缓存 5min；不可用返回轻量节点 + `degraded=true` |
| `search`（docs 组，参数扩展） | 新增 `entities` / `auto_entities`；返回块附 `matched_entities` | 实体召回路复用 §5.1 ACL 编译产物（T-S8） |

**工具 schema（摘要——完整 JSON Schema 随实现交付；工具描述同样按「写给 LLM 看」纪律撰写）**：

```jsonc
// annotate —— "识别文本中的业务术语与业务对象（概念、系统、场景、模板、模板字段、报表项、表、列），返回实体 ID 与位置。每轮对话前调用。"
{ "name": "annotate",
  "input":  { "text": "string ≤4000",
              "context_entities": "int[]? ≤20 = 会话中已确认的实体，用于消歧",
              "prefer_types": "string[]?", "fuzzy": "bool=false" },
  "output": { "dict_rev": "a1b2c3",
              "mentions": [{ "span": [3, 7], "surface": "进项抵扣", "entity_id": 101, "type": "concept",
                             "name": "进项税额抵扣", "confidence": 1.0, "via": "ac", "ambiguous": false,
                             "brief": "一般纳税人取得合规扣税凭证后从销项税额中抵减的进项税额。" }],
              "candidates": [ /* ambiguous / fuzzy 候选，via='fuzzy' 的中间件不自动注入 */ ] } }

// search_entities
{ "name": "search_entities",
  "input":  { "q": "string ≤200", "types": "string[]?", "top_k": "int=10 ≤50" },
  "output": { "entities": [{ "id": 201, "type": "template", "key": "TPL_VAT_INPUT", "name": "…", "brief": "…", "score": 0.93, "via": "alias" }] } }

// get_entity
{ "name": "get_entity",
  "input":  { "id": "int?", "key": "string? = type:key（与 id 二选一）",
              "expand": "string[]? = 关系类型，可带方向后缀 > 或 <（如 'uses>' 'derived_from<'）",
              "depth": "int=1 ≤2", "fanout_limit": "int=50 ≤200",
              "include": "('curated'|'attrs'|'aliases')[] = ['curated']" },
  "output": { "entity": { "id": 201, "type": "template", "key": "TPL_VAT_INPUT", "name": "…",
                          "curated": { "definition": "…", "caliber": "…" }, "status": "active" },
              "nodes":  [{ "id": 305, "type": "table", "name": "ods.vat_input_invoice", "depth": 1 }],
              "edges":  [{ "src": 201, "rel": "backed_by", "dst": 305, "source": "sync" }],
              "truncated": false, "dict_rev": "a1b2c3" } }

// describe_table —— 透传元数据系统，只对已登记的 table 实体开放（未登记 → 403）
{ "name": "describe_table",
  "input":  { "table": "string = table 实体的 key 或 id", "columns": "string[]?" },
  "output": { "table": "…", "columns": [{ "name": "…", "type": "…", "comment": "…", "sample": "…" }],
              "degraded": false } }   // 元数据系统不可用：返回轻量节点信息 + degraded=true（T-S11）
```

**agent 侧接入（deepagents 薄中间件，#35 §9.4）**：

1. **构建时**：调 `GET /api/orgs/{org}/semantic/l0` 把核心术语写进 system prompt，并记录 `dict_rev`；
2. **每轮 before_model**：①对用户最新一条消息调 `annotate`，传会话已确认实体作 `context_entities`；②对 `confidence=1.0` 且非 ambiguous 的命中按类型注入 L1——概念/系统：`name + brief + disambiguation`；对象（模板、字段、报表项等）：只注入 `name + type + id` 一行，详情留给 agent 经 `get_entity` 获取；③有歧义的命中只注入候选列表并提示 agent"必要时向用户确认"；④**本轮注入总量 ≤ 600 token**，超出按 confidence 与出现顺序截断；
3. **工具**：`search_entities` / `get_entity` / `describe_table` 与带 `entities` 参数的 `search` 交给 agent 自主调用；
4. **降级**：annotate 超时（默认 200ms）或失败 → 本轮跳过注入，不阻塞对话（NFR-11）。

**过渡期（现在~M2，#35 §12.3）**：agent 侧用「同 schema 的 Git YAML + 本地 AC 自动机（pyahocorasick）」只覆盖 concept/system 与 L0；YAML schema 与规范化函数抽成小 package 两端共用（本地版与服务端行为一致，迁移零改动）；中间件接口保持不变（输入文本、输出 mentions），本地 AC ↔ 服务端 annotate 经开关切换并支持灰度，切换时用评测集对比。过渡期 concept 的 `refers_to` 可指向尚未同步的实体，CI 只警告，M2-S1/S2 完成后自然生效。

**权限口径（semantic，#35 §10）**：①**组织隔离是硬约束**——全部 `sem_*` 表带 `org_id`，查询一律从 `/api/orgs/{org}` 或 MCP 会话组织上下文取 org（规则同 §5.5），关系端点同组织由触发器校验（T-S7）；②**语义层不复用维度 ACL 编译器**——业务对象（模板名/字段名/表名）组织内默认对所有成员可见，可见性要求与文档内容不在一个级别，对实体套维度 ACL 会把必修 1~3 的复杂度再来一遍；③**`restricted` 实体**：极少数敏感对象只有持 `semantic:restricted` 权限的调用方可见其实体、别名命中与关系展开，无权时 annotate 中表现为不存在（T-S9）；④**文档证据的 ACL 不变**——凡涉及文档块（`search` 的实体召回路）一律走 docs 的维度 ACL 编译产物（§5.10），语义层只提供实体 ID，**不能给文档可见性开任何后门**（T-S8）；⑤`describe_table` 用服务身份调元数据系统、只允许已登记 table 实体（防借此枚举整个数仓）；元数据系统本身有表级权限则改用委托 token（RFC 8693）透传用户身份，与 D18 一致；⑥**审计**：同步、构建、YAML 合并、restricted 实体访问走审计 outbox（权限类事件）；annotate / get_entity 普通查询走查询级异步审计，与 docs 查询审计共用月库。

**上传凭证的 agent 侧时序（v0.4，#33 P1-3——M1 集成项，与 D23 无关、保留）**：deepagents 侧需要一个**运行时工具/中间件**（非 LLM 直接参与）——LLM 决定"上传某文件"→ 运行时①持委托 token 调 `POST /api/uploads`（声明 filename/size/sha256）→ ②PUT 字节到 upload_url → ③把 `upload_id` 交回对话，LLM 再调 MCP `upload(upload_id, dims, ...)`。凭证绑定 sub+org+服务身份（跨组织无效——T11）；未消费凭证由清理任务回收。

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
| httpx | 内部网关客户端 | OpenAI 兼容；语义同步适配器与 describe_table 透传同用 |
| pyahocorasick（M2-S2） | AC 自动机多模式精确匹配——`annotate` 第 1 层、ingest 打标、过渡期 agent 本地版共用（D23） | C 扩展；数万别名构建秒级、匹配 P99 < 5ms；按 (org, dict_rev) 懒加载 |
| pypinyin（M2-S3，可选） | 模糊兜底：拼音完全匹配（同音错字） | 与 jieba 词性筛选、编辑距离、sqlite-vec 向量近邻组成第 3 层 |
|（M3）ragas + deepeval + pytest | 评测与门禁 | judge 走内部网关 |

排除项（明确不引入）：消息队列（tasks 表轮询 + IPC 唤醒足够）、ORM（SQL 收口在 store 层手写，DDL 即文档）、前端构建链（静态页）、**图数据库与 GraphRAG 框架**（D23：关系来自确定性配置、规模 10⁴~10⁵ 节点，SQLite 递归 CTE 足够；再评估条件见 §5.8）。

## 8. 里程碑任务分解（v0.5，与需求 §8 逐条对齐——#33 P1-11/P1-12；M2-S1~S3 语义并行轨道——D23）

**M0a（第 1 周）——骨架 + schema 全量落**
1. 脚手架（uv/config/迁移框架含外键处理约定，§4 **文档侧**全部 DDL 与触发器一次性落——**`sem_*` 除外**，语义表 M2-S1 经 `migrations/semantic/` 落库，见 §3 边界规则 3 / §4 注）；连接工厂（foreign_keys=ON + 显式 raise + 月库滚动建表）
2. 摄取最小链：docling 解析 → 结构切分（五列分词）→ index_fts 入库（BM25 即刻可搜）→ 嵌入分批补齐
3. 检索最小链：BM25 单路 + **完整 ACL 编译器（含状态过滤与统一空值模板——D22①，#34 必修 1/3）**
4. FastMCP `search` + REST multipart 上传 + 静态页壳
5. 验收：deepagents 经 MCP 一次带 chunk_id 的检索（**开发 JWT 即可**）；插孤儿行 IntegrityError；T1~T5 + T20/T22 在编译器单测先行
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
3. 维度 ACL 全链：多值、上传/PATCH 值限授权内、统一空值模板、维度停用/改可选不影响过滤（D5 v0.4）
4. **上传凭证制 + deepagents 集成**（§6.3 时序：运行时工具 + PUT 端点 + 绑定 sub+org+服务 + 清理任务）
5. 区分度环（绝对阈值 + numpy 批量重算 + 报告页近邻过 ACL）
6. 真实文档批量上线（待决-1，合成样例先行）+ 小型黄金集 + Recall@k/MRR + P95 基线
7. 验收：**越权矩阵全绿（§9 含 T1~T23）**；真实 query 标注；区分度误报抽查

**M2（第 4~6 周）——生产化**
1. worker 子进程化（心跳/租约/重试）+ 写竞争治理 + embed 回写防护
2. SSO/JIT 对接（M0a 已敲定协议）；委托 token / 可信子系统落地（三约束 + 期限）
3. 管理面 API + 最小 UI（§6.2 全端点：维度停用 dry_run/退役/授权 expires_at/任务取消/重索引/审计分级查询）
4. 审计 outbox + 月库滚动 + 封存；删除级联与 90 天物理清理
5. 备份快照 + 恢复演练
6. 验收：**杀 worker 不丢任务**（任务租约重认领）；outbox 一致性（权限事件必有审计）；恢复演练通过；跨组织隔离全绿；批量导入 500 行正确（sync 不动——T-CSV）

**M2-S1~S3（M2 并行轨道，D23 业务语义——与 M2 生产化并行；M0a/M0b/M1 不含语义层，只在 worker 任务类型与组织上下文上预留扩展点）**

*M2-S1 模板链路（模板 → 模板字段 → 表 → 列）*
1. `migrations/semantic/`：`sem_*` 全部 DDL + 触发器 + `sem_rel_types` 白名单种子（§4）
2. `template_center` + `metadata` 适配器（SourceAdapter 协议）；同步流程（删除比例保护 / missing 宽限期 / 分批 upsert / 只写事实列 / 别名三 kind 重建 / outbox 事件）
3. 构建任务框架（`semantic_build` 骨架：dict_rev 计算 + 原子切换；AC 自动机留到 S2 接入）
4. semantic 组首批工具：`get_entity`（递归 CTE + 截断）/ `search_entities`（别名精确 > 前缀）/ `describe_table`（白名单 + 超时缓存 + 降级）；REST 对应端点与 `sync` / `builds` / `sync-runs` 管理端点
5. 验收：T-S2 / T-S3 / T-S5 / T-S6 / T-S11；"这个模板落在哪张表、哪个字段"类问题可答

*M2-S2 场景 / 报表项 + YAML 覆盖层*
1. `scenario_config` + `report_center` 适配器
2. YAML 仓库 schema（`_schema/*.schema.json`）与 CI 校验（schema / 别名冲突 / 短词常用词 / L0 预算 / owner / 引用可解析）；`yaml_merge.py` 合并规则表全量实现；`yaml/webhook` 端点
3. 构建产物：AC 自动机（pyahocorasick）/ L0 片段 / 构建报告 + 原子切换 + 评测回归（降 >2pp 不切 ready）
4. `annotate`（AC 层 + 四步消歧 + context 短别名规则 + restricted 过滤）；`GET /semantic/l0`
5. 识别评测集：150~200 条真实问法（工单/群聊/agent 日志）人工标注 span 与 entity_id，覆盖四类黑话、缩写、错别字、歧义词、负样本 ~20%；每次构建自动运行
6. 验收：T-S1 / T-S4 / T-S12；AC precision ≥ 0.95 / recall ≥ 0.80 / 歧义消解 ≥ 0.85 / 负样本误报 ≤ 0.05

*M2-S3 概念 / 文档打标 / 实体召回（M2 末或 M2.5）*
1. `concept` / `system` 纯人工实体全量接入；过渡期 YAML 仓库直接复用
2. ingest 打标（index_fts 同事务 tag；失败不阻断）+ `semantic_retag`（最低优先级、限速）+ 版本切换 / 删块同事务 untag + 定时对账
3. `search(entities / auto_entities)` 实体召回路（`semantic.expand` + docs 侧编译 SQL **复用 §5.1 ACL 产物**）+ 三路 RRF 融合 + `matched_entities`
4. 模糊兜底（拼音 / 编辑距离 / sqlite-vec 向量近邻，`sem_vec`）；`search_entities` 排序补齐拼音与向量
5. agent 中间件从本地 AC 切到服务端 annotate（开关 + 灰度 + 评测集对比）
6. （可选）语义层视图（原型 v0.5 已含）：同步记录、冲突报告、实体浏览
7. 验收：越权矩阵 T-S7 / T-S8 / T-S9 / T-S10 全绿；AC+模糊 recall@3 ≥ 0.92；**检索增益评测**（docs 黄金集开/关实体路 recall@10、MRR）不回退方可默认开启

**M3（第 7~8 周）——评测防线**
1. 完整黄金集（M1 小型集扩容）+ 响应层指标固化
2. judge 双语校准（~50 条人工双评）
3. deepeval 门禁进 CI（预注入回归验证）
4. 在线引用锚点抽样
5. 验收：门禁能卡住一次人为注入的检索层回归；judge-人一致性达标；黄金集覆盖中英三态 query

依赖：M1.2/1.3 依赖 M0a.3；M1.4 依赖 M1.2；M0b 结论回写后方可进 M1；M3 扩量依赖待决-1。**语义轨道（D23）**：M2-S1 依赖 M2.1 的 worker 子进程化与迁移框架就位；M2-S2 依赖 M2-S1 的模板/字段节点作关系端点；M2-S3 依赖 M2-S2 词典质量稳定（否则重标风暴扩散到 docs 检索）与 M2.4 的删除级联（untag 挂接点）；语义轨道任何一步延期**不阻塞 M2 / M3 主线验收**。

## 9. 测试策略（v0.5：含 issue #33 T1~T19、#34 T20~T23、#35 T-S1~T-S12 全量）

- **单元**：ACL 编译器（括号化 AST 断言/多值/状态过滤【过期/停用/成员关系过期】/统一空值模板（空值放行/空集单条件））；**连接工厂外键断言（插孤儿行抛 IntegrityError）**；FTS5 MATCH 转义（`"`→`""`/`*`/`NEAR`/`AND`/`-`）；RRF 与归一；切分边界（表格整块/Excel 行块含表头）；**切换 SQL 后 FTS 无 tombstone 内容**；凭证流（size 截断/sha256 校验/过期/绑定）；
- **集成**：摄取→检索端到端（searchable_lexical 中间态）、版本切换原子性（并发 409/失败删块/回写防护）、任务租约重认领、触发器同步无幽灵命中、迁移 foreign_key_check；
- **越权用例集（CI 常跑）**：原矩阵（用户授权 × 文档维度多值 × 库过滤 × 可选维度空值 × 新增必选未回填 × 移出重加 × 跨组织 × MCP 统计）+ v0.3 四组（版本中间态/删维度取值/PATCH 越权/CSV）+ **T1~T19（#33 §6，逐条对应修复项）**：T1 过期授权清理未跑仍不可见；T2 成员续期不复活旧授权；T3 停用取值收紧；T4 维度改可选/停用不放宽（D5 v0.4——#34 方案 A）；T5 可选维度有值则过滤；T6 v2 改维度切换前后无双方可见（两种 ACL 写法都测）；T7 并发覆盖 409；T8 失败版本无 FTS 残留；T9 切换后 FTS 层面无旧版本命中；T10 待嵌入清单不含 tombstone；T11 凭证跨组织无效；T12 PUT 超量/哈希不符拒绝；T13 可信子系统越界/冒充拒绝并审计；T14 org claim 与头不一致 400；T15 他组织维度 id 403/404；T16 生产配置 token 端点 404；T17 授权撤销后 owner 不再见在用文档（**检索路径无 owner 分支——#34 必修 2**）；T18 报告页近邻不泄露无权内容；T19 删文档/删库按定义成功或明确报错（非裸外键异常）；**T20~T23（#34 §5）**：T20 新建维度零文档消失、回填只收紧、必选改可选/停用不放宽、仅退役放宽且必有审计（**M0a 编译器单测**）；T21 授权已撤销的 owner 发起覆盖上传，处理中窗口检索不到该文档任何版本（**M1 越权矩阵**）；T22 用户在某维度无授权 → 只见该维度为空的文档；授权集为空时编译产物不出现 `IN ()`（**M0a 编译器单测**）；T23 对已过期成员关系 UPDATE expires_at 被触发器拒绝；先删再加后旧授权不复活（M1 越权矩阵）；
- **评测**：M1 小型黄金集 → M3 门禁；
- **语义层功能与不变式（D23，T-S1~T-S12——#35 §13.1；M2-S1~S3 分批落地）**：
  - 单测：**T-S1** 同步不覆盖人工字段（YAML 写入 definition 与 manual 别名后，源端改 name 再同步——`curated_json` 与 manual 别名不变、name 更新）；**T-S2** 删除比例保护（mock 源端返回空快照或少 30% → run 为 `aborted_guard`、库内零写入、产生告警）；**T-S3** 同步幂等（同一快照连续跑两次，第二次 inserted / updated / missing 均为 0）；**T-S4** 宽限期（对象消失先 `missing`，宽限期内恢复回 `active`，超期 `retired` 且关系一并 retired）；**T-S5** 关系白名单与组织一致性（插入跨组织关系、非白名单端点类型、UPDATE 端点均被触发器拒绝）；**T-S6** 递归展开（有环图不死循环；depth > 2 服务端拒绝；高扇出节点截断并返回 `truncated=true`）；
  - 越权矩阵（CI 常跑，并入 §9 越权用例集）：**T-S7** 组织隔离（A 组织的 annotate / get_entity / search_entities 不返回 B 组织任何实体，`dict_rev` 互相独立）；**T-S8** 实体召回不放宽 ACL（同一用户、同一查询下 FTS / 向量 / 实体三路并集 ⊆ 该用户可见块集合；无权文档里命中实体的块，实体路也召回不到）；**T-S9** restricted 实体（无权调用方 annotate 拿不到 span、get_entity 404、关系展开不出现该节点）；
  - 集成：**T-S10** 版本切换 / 删块 untag（覆盖上传切换后旧版本块的 `sem_chunk_entities` 同事务清除；删文档后无残留——对账任务断言）；**T-S11** describe_table 白名单（未登记表 403；元数据系统超时返回 `degraded=true` + 轻量节点信息）；**T-S12** 构建原子切换（构建过程中请求始终用旧 `dict_rev`；构建失败旧版本继续服务）；
- **语义识别评测（M2-S2 起每次构建自动运行——#35 §13.2）**：评测集 150~200 条真实问法（工单/群聊/agent 日志），人工标注 span 与 entity_id，覆盖四类黑话、缩写、错别字、歧义词、负样本 ~20%；门槛：AC 层 precision ≥ 0.95、recall ≥ 0.80，AC + 模糊 recall@3 ≥ 0.92，歧义消解准确率 ≥ 0.85（只统计歧义样本），负样本误报率 ≤ 0.05；构建报告指标较上一版下降 >2 个百分点则不切 ready；**检索增益评测（M2-S3）**：docs 黄金集上对比开/关实体召回路的 recall@10 与 MRR——不回退才允许默认开启，否则保持可选参数；
- **性能抽测**：~10 万块 P95（按块 vs 按文档、同表 vs 分表）、rerank 并发、嵌入吞吐（M0b/M1 各一轮，驱动 schema v1.1 与 NFR-8 标定）。

## 10. 风险的工程对策（对应需求 §9 风险登记，v0.5：含 D23 语义层风险——#35 §14）

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
| **语义层职责膨胀**（D23） | §3 模块边界规则（semantic 不 import docs 内部实现，交叉点仅 tag/untag 与 expand 两处显式接口）；新增实体/关系类型 = 迁移 + 评审；非目标明确（GraphRAG / 图数据库 / 全量元数据镜像） | 新增实体或关系类型提案时 |
| **语义同步故障波及服务**（源系统抖动清空图 / 写锁拖慢检索） | 删除比例保护（20% 中止零写入）+ missing 宽限期（7 天）；独立任务类型、分批 ≤1000 行、夜间错峰限速；语义失败不影响 docs 可用性（NFR-11）；必要时 `sem_*` 拆 ATTACH 独立库（repo 接口不变） | 源系统接口异常；M2-S 并行期压测 |
| **SQLite 写锁竞争**（同步 / 重标与 ingest 抢 WAL 写锁） | 同步与重标限速分批并错峰；重标优先级最低；§2 并发模型 | M2-S3 打标全量启用时 |
| **词典质量差**（短词 / 常用词误报，注入噪声） | CI 拦截短词与常用词；`context` 匹配模式；AC precision 门槛 ≥ 0.95；中间件只注入 confidence=1.0 非歧义命中；构建回归 >2pp 不切 ready | 每次构建报告 |
| **人工内容无人维护**（YAML 过期、别名覆盖率低） | 每条 YAML 必填 `owner`；构建报告列出无人维护与孤立条目；agent 日志高频未识别词定期回流成待补别名 | 季度运营回顾 |
| **源系统缺关系**（报表项取数关系未配置） | `extra_relations` 人工补；与同步重复时自动提示删除；推动源系统补齐 | M2-S2 报表项接入 |
| **实体召回 ACL 后门** | 实体召回路强制复用 §5.1 编译产物（同一编译器、同一产物，§5.10）；T-S8 越权矩阵必测 | M2-S3 验收 |
| **过渡期与正式版分叉**（本地 AC 与服务端行为不一致） | YAML schema 与规范化函数抽成小 package 两端引用；切换时评测集对比；开关灰度 | M2-S3 中间件切换 |
