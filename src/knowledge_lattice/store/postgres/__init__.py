"""PostgreSQL 方言包（design §3 store/postgres/——D24 正式备选，PG 16 + pgvector 0.8.x 已确认）。

连接工厂（psycopg + 连接池）、migrations/{docs,semantic}/、DDL/触发器等价、
fts/vec/acl_render/audit/backup 随 **M0b PG spike** 落（known-gaps G-6 差异口径）；
M0a 期间仅 SQLite 后端验收（本地无 DSN 可 skip、CI 必跑 PG 自 M0b job 起生效）。
"""
