"""PostgreSQL 方言包（design §3 store/postgres/——D24 正式备选，PG 16 + pgvector 0.8.x 已确认）。

M0b-1 已落（PG spike）：
- connection.py：连接工厂（psycopg3 连接 + ConnectionPool 连接池 + PG 等价断言
  〔server_version ≥16 / pgvector `<=>` 可调用〕+ str→unknown dumper + 审计分区
  滚动；TC-SCAF-02 后端行 v1.4/#42 必修4）；
- migrate.py：迁移框架 PG 版（`schema_migrations` 表 + 事务级 advisory lock 并发
  序列化 + 原生约束即时校验〔违例整事务回滚〕+ dollar-quoting 感知切分）；
- migrations/{docs,semantic}/：二维迁移目录（0001_schema_v1.sql = §4 文档侧全量
  DDL 的 PG 等价——tsvector 五列 GENERATED / vector 列 / 9 个 plpgsql 触发器；
  0002_schema_v1_1.sql = 三项拍板落库〔删 dims_json/embedding、chunk_vectors
  分表 PK(rid, embed_model)〕；semantic/0006 = M2-S1 语义七表 + 白名单种子 +
  trg_sem_rel_check/noupdate plpgsql 等价）；
- acl_render.py：AclPlan PG 渲染器（同一方言无关 AST〔store/acl_ast.py〕；
  M0b-3 起 visible_docs CTE + AS MATERIALIZED **唯一路径**——jsonb 按块路径谓词
  已随拍板 1 删除，向量谓词迁 chunk_vectors JOIN；M1-1 起含 FTS 路——Match
  节点渲染五列 @@ OR + 加权 ts_rank 求和；M0a-2 R2 安全纪律沿用）；
- backend.py：PgBackend（Acl/Ingest/Admin/Audit 实作 + Search 域——M1-1 起
  recall_fts/recall_vec 实装、检索配方双后端等价）；
- audit.py（审计按月分区表 + append-only 触发器）/ vec.py（pgvector 文本序列化）/
  fts.py（to_tsquery 构造 + 五列 ts_rank 权重——M1-1 落）。

随 M1-2+/M2 再落：backup.py（pg_dump runbook——M2 备份演练）。
"""

from .connection import connect, connect_pool, setup_connection
from .migrate import migrate_db

__all__ = ["connect", "connect_pool", "setup_connection", "migrate_db"]
