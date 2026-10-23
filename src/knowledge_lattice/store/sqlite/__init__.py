"""SQLite 方言包（design §3 store/sqlite/）。

M0a-1 已落：连接工厂 connection.py（唯一连接入口——WAL/busy_timeout/foreign_keys=ON+
断言/sqlite-vec 扩展加载/月库滚动）、migrate.py（迁移框架——公开入口 `migrate_db`）、
audit.py（审计月库滚动建表）、migrations/{docs,semantic}/（二维迁移目录）。
M0a-2 已落：backend.py（StorageBackend 的 SQLite 实现——Acl 域 read_membership/
read_grants 读取收口）、acl_render.py（AclPlan → SQL 的 AST builder + 渲染器，
含 visible_docs CTE 备选双写法）。随 M0a-3+ 再落：fts.py / vec.py / backup.py。

命名注：re-export 的 `connect`/`migrate_db` 与子模块名错开（connection/migrate），
避免函数属性覆盖同名子模块的 footgun。
"""

from .connection import connect
from .migrate import migrate_db

__all__ = ["connect", "migrate_db"]
