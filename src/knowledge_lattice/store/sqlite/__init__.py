"""SQLite 方言包（design §3 store/sqlite/）。

M0a-1 已落：连接工厂 connection.py（唯一连接入口——WAL/busy_timeout/foreign_keys=ON+
断言/sqlite-vec 扩展加载/月库滚动）、migrate.py（迁移框架——公开入口 `migrate_db`）、
audit.py（审计月库滚动建表）、migrations/{docs,semantic}/（二维迁移目录）。
随 M0a-2+ 再落：fts.py / vec.py / acl_render.py / backup.py。

命名注：re-export 的 `connect`/`migrate_db` 与子模块名错开（connection/migrate），
避免函数属性覆盖同名子模块的 footgun。
"""

from .connection import connect
from .migrate import migrate_db

__all__ = ["connect", "migrate_db"]
