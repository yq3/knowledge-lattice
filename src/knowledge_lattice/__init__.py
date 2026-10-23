"""knowledge-lattice——企业知识层服务（文档知识 + 业务语义）POC。

设计：docs/design.md（v0.9，冻结纪律）；里程碑：design §8。
M0a-1 范围：脚手架 + StorageBackend 协议/AclPlan 类型 + 迁移框架 +
文档侧全量 DDL/触发器（sem_* 除外——M2-S1）+ SQLite 连接工厂。
"""

__version__ = "0.1.0"
