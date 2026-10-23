"""store——唯一碰 SQL 的层（design §3；D24 双方言包各自拥有 DDL/迁移/FTS/向量/ACL 渲染/审计/备份）。

全部连接经各方言连接工厂（SQLite：store/sqlite/——禁止绕过直连，issue #32 P0-B）；
不引入 ORM（SQL 收口 store 层手写）。
"""
