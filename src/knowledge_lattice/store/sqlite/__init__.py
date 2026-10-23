"""SQLite 方言包（design §3 store/sqlite/）。

M0a-1 已落：连接工厂 connect.py（唯一连接入口——WAL/busy_timeout/foreign_keys=ON+
断言/sqlite-vec 扩展加载/月库滚动）、migrate.py（迁移框架）、audit.py（审计月库滚动
建表）、migrations/{docs,semantic}/（二维迁移目录）。随 M0a-2+ 再落：fts.py /
vec.py / acl_render.py / backup.py。
"""

from .connect import connect
from .migrate import migrate

__all__ = ["connect", "migrate"]
