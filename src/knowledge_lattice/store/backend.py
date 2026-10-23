"""StorageBackend 协议（D24）+ AclPlan 结构化产物类型。

按域分节组合（v0.8.3）——Search/Ingest/Acl/Admin/Semantic/Audit 各自独立 Protocol、
本模块只做组合，防单一 God interface；方法清单为**种子非穷举**（新增方法先进域再实现）。
SQLite 实现先行（store/sqlite/——连接工厂与迁移已就位，backend 方法随 M0a-2 摄取/
检索链逐个实装）；PG 方言包（store/postgres/）随 M0b spike 落，PG 等价断言同源。

分层纪律：store 是唯一碰 SQL 的层；core 经本协议消费存储（「core 不碰 SQL」——
Acl 域的 read_membership / read_grants 把 §5.1 第 0/2 步的授权展开与成员校验读取
收口于此，编译器只消费结果，v0.8.3）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# ============ AclPlan：方言无关的维度 ACL 编译产物（D24） ============
#
# 由编译器（core/docs/acl.py，M0a-2）产出，各后端 acl_render.py 渲染为目标 SQL。
# 语义规则只在编译器实现一次（#34 必修 1/3——「无 IN ()」为 Plan 层不变式）：
#   · 每个规则对应一个 active 维度，统一「有值则过滤（与授权集有交集）、空值放行
#     （NOT EXISTS json_each …）」模板；required/enabled 不参与过滤；
#   · 空授权集（grants=()）→ 该维只渲染 NOT EXISTS 单条件节点——用户只见该维为空的
#     文档（T22），禁止生成 `IN ()` 语法错误；
#   · retired 维度不生成规则（唯一放宽路径——T20）；
#   · embed_model 谓词为固定节点（向量路：非当前标签视同未嵌入——TC-EMB-02）。


@dataclass(frozen=True)
class AclDimensionRule:
    """单个 active 维度的过滤规则：key + 授权取值集。"""

    key: str
    grants: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        """空授权集 → 渲染为 NOT EXISTS 单条件（无 OR/IN 分支）。"""
        return not self.grants


@dataclass(frozen=True)
class AclPlan:
    """一次检索的完整 ACL 计划（org / 各维度规则 / dataset / doc 过滤 + 向量路谓词）。

    外层常量约束（c.version = d.active_version AND c.tombstone = 0 AND d.org_id = :org）
    由渲染器作为固定节点追加，与 Plan 中 org_id 一致（TC-ACL-06）。
    """

    org_id: str
    dimension_rules: tuple[AclDimensionRule, ...] = ()
    dataset_ids: tuple[str, ...] | None = None  # None = 不过滤（搜全部权限内文档）
    doc_ids: tuple[str, ...] | None = None      # None = 不过滤
    embed_model: str | None = None              # 向量路查询谓词（model:dim——D12）


# ============ 域协议（方法种子非穷举） ============


@runtime_checkable
class SearchBackend(Protocol):
    def recall_fts(self, query: str, plan: AclPlan, *, top_k: int = 20) -> list[dict]:
        """FTS/BM25 召回（收 AclPlan——引擎内下推）。"""
        ...

    def recall_vec(self, query_vec: bytes, plan: AclPlan, *, top_k: int = 20) -> list[dict]:
        """向量召回：先过滤后距离（`embedding IS NOT NULL AND embed_model = plan.embed_model`）。"""
        ...

    def recall_by_entities(self, entity_ids: Sequence[int], plan: AclPlan, *, top_k: int = 30) -> list[dict]:
        """实体召回路（M2-S3——D23 §5.10；复用同一 Plan）。"""
        ...

    def expand_relations(
        self, org_id: str, seed_ids: Sequence[int], rels: Sequence[str], *, depth: int = 1
    ) -> dict:
        """语义关系递归展开（M2-S1——方言渲染收口于此，#42 拍板3）。"""
        ...


@runtime_checkable
class IngestBackend(Protocol):
    def insert(self, doc_id: str, version: int, chunks: Sequence[dict]) -> None:
        """chunks + FTS 同一事务写入。"""
        ...

    def write_embeddings(self, batch_label: str, rows: Sequence[tuple[int, bytes]]) -> int:
        """逐批回写 embedding/embed_model（带 tombstone/版本防护——P0-2.3，M1 实装）。"""
        ...

    def delete_by_doc(self, doc_id: str, version: int) -> int:
        ...

    def switch_active_version(self, doc_id: str, expected_pending: int) -> None:
        """版本切换单事务（乐观校验——M1 实装）。"""
        ...

    def pending_embeddings(self, batch_label: str) -> list[dict]:
        ...


@runtime_checkable
class AclBackend(Protocol):
    def read_membership(self, user_id: str, org_id: str, *, now: str | None = None) -> dict | None:
        """§5.1 第 0 步成员关系校验的读取收口（含过期）。"""
        ...

    def read_grants(self, user_id: str, org_id: str, *, now: str | None = None) -> dict[str, tuple[str, ...]]:
        """§5.1 第 2 步授权展开的读取收口（active 维度 × active 取值 × 未过期）。"""
        ...


@runtime_checkable
class AdminBackend(Protocol):
    """组织/维度/取值/授权/成员 CRUD + 任务队列（租约·心跳·认领）+ 上传凭证 + 审计查询。

    方法随 M1/M2 管理面 API 逐个进域（种子非穷举——v0.8.3）。
    """


@runtime_checkable
class SemanticBackend(Protocol):
    """M2-S：sync 分批 upsert / missing·retired 推进 / 构建产物与 sem_vec 读写 / L0 导出。"""


@runtime_checkable
class AuditBackend(Protocol):
    def append_outbox(self, event_type: str, payload_json: str) -> None:
        """outbox 写入（与业务写同事务——「业务改了就一定有审计」，M2 实装）。"""
        ...

    def roll_monthly(self, when: object | None = None) -> object:
        """月库/分区滚动（方言差异在包内吸收——SQLite 月库文件 / PG 按月分区）。"""
        ...


@runtime_checkable
class StorageBackend(
    SearchBackend,
    IngestBackend,
    AclBackend,
    AdminBackend,
    SemanticBackend,
    AuditBackend,
    Protocol,
):
    """组合协议——存储后端唯一接口（D24：SQLite 默认 / PG+pgvector 可选，配置级切换）。"""
