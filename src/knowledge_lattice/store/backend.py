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


class VersionConflictError(Exception):
    """版本切换乐观校验失败（WHERE pending_version=:expected 零行——并发切换/取消
    竞态；409 语义，P0-2.3/T7）。"""

# ============ AclPlan：方言无关的维度 ACL 编译产物（D24） ============
#
# 由编译器（core/docs/acl.py，M0a-2）产出，各后端 acl_render.py 渲染为目标 SQL。
# 语义规则只在编译器实现一次（#34 必修 1/3——「无 IN ()」为 Plan 层不变式）：
#   · 每个规则对应一个 active 维度，统一「有值则过滤（与授权集有交集）、空值放行
#     （该维无 document_dimensions 行）」模板（v1.1：visible_docs CTE 唯一路径——
#     json_each 按块模板已删）；required/enabled 不参与过滤；
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
    def recall_fts(
        self, tokens: Sequence[str], plan: AclPlan, *, top_k: int = 20
    ) -> list[dict]:
        """FTS/BM25 召回（收 AclPlan——引擎内下推；tokens 为 jieba 切分产物，
        方言转义在本层完成——SQLite 双引号包裹 / PG to_tsquery `&` 连接，D24）。

        **名次协议（M1-1，v0.8 #42 P1-8）**：评分方向差异（SQLite bm25 越小越
        相关 / PG ts_rank 越大越相关）在 backend 内吸收——行含 `rank`（1 起，
        越小越相关）；score_raw/dist 仅供观察，RRF 与归一不消费。
        """
        ...

    def recall_vec(
        self, query_vec: Sequence[float], plan: AclPlan, *, top_k: int = 20
    ) -> list[dict]:
        """向量召回：先过滤后距离（v1.1 谓词迁 `JOIN chunk_vectors cv ON cv.rid = c.rid
        AND cv.embed_model = plan.embed_model`——cv 无行即未嵌入，TC-EMB-02）。
        序列化收口方言侧（sqlite=vec_f32 BLOB / pg=vector 文本——core 传浮点
        向量，P2-3 同款纪律）；行含 `rank`（1 起）与 `dist`（升序）。"""
        ...

    def visible_chunk_ids(self, plan: AclPlan, rids: Sequence[int] | None = None) -> set[int]:
        """可见块 rid 集合（rerank 前 / 返回前 ACL 双断言数据源——TC-ACL-08）。

        走基础路 SQL（visible_docs CTE + 外层常量）——与 FTS/向量召回路不同
        SQL 路径的防御纵深；plan 由 retrieve 内部独立重编译（同一编译器、
        不同调用实例）。rids 非 None 时按给定块集收窄扫描（`AND c.rid IN (…)`）
        ——双断言分别传候选集 / top-k 集，防 10 万块宽权限的全量 O(N) 扫描；
        「独立 SQL 路径」性质不变（同 CTE + 基础路形态，仅范围收窄）。
        """
        ...

    def rids_without_vector(
        self, rids: Sequence[int], embed_model: str
    ) -> set[int]:
        """给定 rid 中无 (rid, embed_model) cv 行的子集——notice.vector_pending
        的块级判定（TC-RET-02：本结果缺向量路＝未就绪或降级）。"""
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
        """chunks + FTS 同一事务写入（幂等：同 (doc_id, version) 先删后插）+ 阶段状态推进
        （pending_status→searchable_lexical + 首次上传 D20 切换）。"""
        ...

    def write_embeddings(
        self, batch_label: str, rows: Sequence[tuple[int, Sequence[float]]]
    ) -> int:
        """逐批回写向量入 chunk_vectors(rid, embed_model, embedding)——rows=(rid,
        float 向量)；**方向序列化收口实现侧**（SQLite=vec_f32 BLOB / PG=vector 列
        ——core 不碰方言，P2-3/D24）；防护：tombstone=0 + 标签匹配 + (rid,label)
        无行（PK 冲突零触碰；同 rid 异标签照常写入=蓝绿并存，v1.1）。"""
        ...

    def delete_by_doc(self, doc_id: str, version: int) -> int:
        ...

    def switch_active_version(self, doc_id: str, expected_pending: int) -> None:
        """版本切换单事务（design §5.3 切换 SQL——M1-2 实装）：

        事务内逐项：旧块 tombstone=1 + 五列 FTS 清空 + chunk_vectors 旧行 DELETE
        （v1.1 拍板②）+ documents 五字段更新（WHERE pending_version=:expected
        乐观校验——不符 raise VersionConflictError）+ pending_dims_json 落
        document_dimensions。中途失败全回滚。
        """
        ...

    def max_document_version(self, doc_id: str) -> int:
        """文档历史最大版本号（active/pending/chunks 三源 max——失败版本号不复用，
        pending_version = max(历史)+1，P0-2.3/TC-VER-03）。"""
        ...

    def start_overwrite(
        self,
        *,
        doc_id: str,
        pending_version: int,
        content_hash: str,
        mime_type: str,
        raw_object_key: str,
        pending_dims_json: str | None,
    ) -> None:
        """覆盖上传的文档行更新：开新 pending 版本（parsing）——不动 active_* 五字段
        （v1 继续服务到 searchable_full 切换，D20）。"""
        ...

    def set_doc_pending_failed(self, doc_id: str, version: int, error: str) -> None:
        """pending 版本失败：pending_status='failed' + pending_error + **立即物理删除
        该版本全部块**（ad 触发器移出 FTS——失败不留检索残留，T8）——同一事务。"""
        ...

    def delete_document(self, doc_id: str) -> None:
        """删除文档（同事务：非终态任务置 failed(error='cancelled: document deleted')
        ——任务取消联动 TC-VER-07；级联 chunks/document_dimensions/chunk_vectors；
        tasks.doc_id ON DELETE SET NULL 保留历史）。"""
        ...

    def get_document_dims(self, doc_id: str) -> dict[str, list[str]]:
        """文档当前维度（document_dimensions 按 key 聚合——PATCH 旧值校验数据源）。"""
        ...

    def set_document_dims(self, doc_id: str, dims: dict[str, list[str]]) -> None:
        """按 key 全量替换文档维度行（PATCH /dimensions 落点——D6 刷维度不重嵌；
        解析 (key,value)→(dimension_id,value_id) 同 pending_dims 逻辑）。"""
        ...

    def get_chunk(self, chunk_id: str) -> dict | None:
        """块定位（fetch 入口）：id/doc_id/seq/version/tombstone。"""
        ...

    def fetch_window(self, doc_id: str, version: int, seq_lo: int, seq_hi: int) -> list[dict]:
        """fetch 内容窗口：同文档同版本、tombstone=0、seq∈[lo,hi]（§6.1 fetch）。"""
        ...

    def visible_doc_ids(self, plan: AclPlan, doc_ids: Sequence[str]) -> set[str]:
        """文档级可见集（visible_docs CTE——fetch 替代提示的文档可见性判定：
        文档可见 ⇔ 在 CTE 内；块可 fetch ⇔ 文档可见 + version=active + tombstone=0）。"""
        ...

    def pending_embeddings(self, batch_label: str) -> list[dict]:
        """已钉标签未回写的待嵌入块（embed_model=:label AND chunk_vectors 无该
        (rid,label) 行 AND tombstone=0——v1.1 分表口径）。"""
        ...

    def mark_embedding_batch(self, doc_id: str, version: int, batch_label: str) -> list[dict]:
        """批次启动钉死标签（§5.3）：认领在处理块且 chunk_vectors 无该 (rid,label)
        行——chunks.embed_model 为摄取状态标签（v1.1，向量查询谓词已迁分表）。"""
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
    M0a-3 落：任务队列（状态机 pending→leased→running→done/failed）、文档状态读写、
    嵌入指纹基线（embedding_fingerprints）、维度/取值只读（页壳上传表单所需）。
    """

    def create_task(self, doc_id: str, *, task_type: str = "ingest") -> str:
        ...

    def get_task(self, task_id: str) -> dict | None:
        ...

    def list_tasks(self, org_id: str, *, doc_id: str | None = None) -> list[dict]:
        ...

    def update_task(
        self, task_id: str, *, status: str | None = None, error: str | None = None
    ) -> None:
        """任务状态机推进（leased/running 由执行器调用；attempts 随 running 递增）。"""
        ...

    def get_document(self, doc_id: str) -> dict | None:
        ...

    def create_document(
        self,
        *,
        doc_id: str,
        org_id: str,
        dataset_id: str,
        title: str,
        source_uri: str,
        content_hash: str,
        mime_type: str,
        parser: str,
        owner_user_id: str,
        raw_object_key: str,
        pending_dims_json: str | None,
    ) -> None:
        """首次上传的文档行（pending_version=1、pending_status='parsing'）。"""
        ...

    def set_doc_pending_status(self, doc_id: str, version: int, status: str) -> None:
        ...

    def set_doc_active_status(self, doc_id: str, version: int, status: str) -> None:
        ...

    def set_doc_active_error(self, doc_id: str, version: int, error: str) -> None:
        ...

    def read_fingerprint(self, embed_model: str) -> str | None:
        """指纹基线 JSON（无基线 → None——首部署建档判定）。"""
        ...

    def save_fingerprint(self, embed_model: str, baseline_json: str) -> None:
        ...

    def list_dimensions(self, org_id: str) -> list[dict]:
        """active 维度 + active 取值（上传表单/校验所需——M0a 只读）。"""
        ...

    def list_datasets(self, org_id: str) -> list[dict]:
        ...

    def find_user_by_token_hash(self, token_hash: str) -> dict | None:
        """静态 token 查 user（sha256——仅 dev/test，D18）。"""
        ...

    def get_user_auth(self, user_id: str) -> dict | None:
        """认证侧用户态（存在 / 禁用 / 系统管理员）。"""
        ...

    # ---- 上传凭证（M1-3 三步式——design §6.1/§6.2/§6.3；状态机
    #      issued→uploaded→consumed，「用掉」＝摄取成功入队——v1.4 口径） ----

    def create_upload_credential(
        self,
        *,
        upload_id: str,
        org_id: str,
        user_id: str,
        service_id: str | None,
        filename: str,
        size: int,
        sha256: str,
        content_type: str,
        expires_at: str,
    ) -> None:
        """凭证行落库（status='issued'——绑定 sub+org+服务身份三要素，#33 P1-3）。"""
        ...

    def get_upload_credential(self, upload_id: str) -> dict | None:
        """凭证行（含 status/object_key/doc_id/task_id/expires_at 等全列）。"""
        ...

    def mark_upload_uploaded(self, upload_id: str, *, object_key: str) -> bool:
        """PUT 成功：status→uploaded + 对象键（WHERE status IN ('issued','uploaded')
        ——re-PUT 覆盖放行；并发已消费 → False＝409 语义）。"""
        ...

    def mark_upload_consumed(self, upload_id: str, *, doc_id: str, task_id: str) -> bool:
        """消费：status→consumed + 文档/任务关联回填（WHERE status='uploaded'——
        单次使用；竞态零行 → False＝409 语义）。"""
        ...

    def list_expired_upload_credentials(self, now: str) -> list[dict]:
        """过期未消费凭证（status IN ('issued','uploaded') AND expires_at<=now）——
        maintenance 清理任务扫描面（TC-CRED-05）。"""
        ...

    def delete_upload_credential(self, upload_id: str) -> None:
        """凭证行删除（清理任务回收——已消费凭证保留供追溯，不进本方法）。"""
        ...


@runtime_checkable
class SemanticBackend(Protocol):
    """M2-S：sync 分批 upsert / missing·retired 推进 / 构建产物与 sem_vec 读写 / L0 导出。

    种子方法签名（P3-17——M0b-1 随 PG backend 实作补齐；实现随 M2-S1 经
    store/<dialect>/migrations/semantic/ 落库，D23/§5.8）。
    """

    def upsert_entities_batch(self, org_id: str, rows: Sequence[dict]) -> int:
        """同步分批 upsert（只写事实列 name/attrs_json/parent_id/status/synced_at，
        分批 ≤1000 行/批——NFR-11 写锁治理）；返回本批 inserted/updated 计数。"""
        ...

    def advance_status(self, org_id: str, *, missing_before: str) -> dict:
        """missing 宽限期推进（超期 missing → retired，关系一并 retired——T-S4）；
        返回 {missing, retired} 计数。"""
        ...

    def save_build(self, org_id: str, dict_rev: str, stats_json: str) -> int:
        """构建产物登记（sem_builds——dict_rev = f(active 快照, YAML commit, embed_model)）。"""
        ...

    def load_build(self, org_id: str, dict_rev: str) -> dict | None:
        """按 (org, dict_rev) 读构建产物（AC 自动机/模糊索引/L0 懒加载入口）。"""
        ...

    def export_l0(self, org_id: str) -> str:
        """L0 术语片段导出（1500 token 预算——§6.3/agent 中间件注入源）。"""
        ...


@runtime_checkable
class AuditBackend(Protocol):
    def append_outbox(self, event_type: str, payload_json: str) -> None:
        """outbox 写入（与业务写同事务——「业务改了就一定有审计」；M0a-3 起实装：
        探针两档告警 / 工具参数 org 忽略等事件）。"""
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
