"""同步快照记录（design §5.8 SourceAdapter 契约的数据面——传输方式无关）。

EntityRecord.dims：维度属性可选携带（#37 评论决策——不强制；实体维度 ACL 为
NFR-5 演进缝、触发前不启用过滤）。**载体口径（本段实现决策）**：design §4 无
sem_entity_dims 专表 DDL，维度随事实属性落 `attrs_json` 的结构化键 `dims`
（如 {"region": "CN"}）——最小实现、同步可见性不受影响；值域与本地维度不一致
的显式映射表归 m2s-3 YAML 链；演进缝触发时再议升级专表（届时迁移承载）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EntityRecord:
    """快照实体（源端事实行）。"""

    type: str                       # SEM_ENTITY_TYPES 九值之一
    key: str                        # 业务主键（组织内按类型唯一）
    name: str                       # 规范名
    parent_key: str | None = None   # 父节点 "type:key"（字段→模板、列→表、项→报表）
    attrs: dict = field(default_factory=dict)   # 编码、注释、源端状态等事实属性
    aliases: tuple[str, ...] = ()   # 源系统自带别名 → kind='sync'
    dims: dict[str, str] | None = None          # 维度属性可选携带（见模块 docstring）


@dataclass
class RelationRecord:
    """快照关系（端点以 (type, key) 引用——落库时解析为实体 id）。"""

    src: tuple[str, str]
    rel_type: str                   # SEM_REL_TYPE_NAMES 十值之一
    dst: tuple[str, str]
    attrs: dict | None = None       # 如 maps_to 转换规则、derived_from 取数口径


__all__ = ["EntityRecord", "RelationRecord"]
