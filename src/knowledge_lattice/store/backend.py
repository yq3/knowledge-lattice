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

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class VersionConflictError(Exception):
    """版本切换乐观校验失败（WHERE pending_version=:expected 零行——并发切换/取消
    竞态；409 语义，P0-2.3/T7）。"""


class DatasetNotEmptyError(Exception):
    """删库被拒：库内仍有文档（RESTRICT 明确语义——非裸外键异常，T19 半句收口/
    TC-OPS-04②；「先删文档再删库」服务层流程，§6.2）。"""

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
        """语义关系递归展开（#42 拍板3——M2-S3 实体召回路口径）。m2s-2 R2 起为
        ``sem_expand_graph`` 的薄适配（多 seed 归并、rels 双向、fanout/node 上限
        取 store 侧缺省 50/200——语义与 core/semantic/expand.py 常量一致）。"""
        ...


@runtime_checkable
class IngestBackend(Protocol):
    def insert(
        self, doc_id: str, version: int, chunks: Sequence[dict], *,
        sem_tags: dict | None = None,
    ) -> None:
        """chunks + FTS 同一事务写入（幂等：同 (doc_id, version) 先删后插）+ 阶段状态推进
        （pending_status→searchable_lexical + 首次上传 D20 切换）。

        sem_tags（M2-S3/m2s-5 同事务打标——TC-TAG-01）：``{"dict_rev": str,
        "rows": [(seq, entity_id, hits), ...]}``——语义命中行随块写入**同一事务**
        落 sem_chunk_entities（rows 的 seq 定位本批 chunks 行；org_id 事务内查
        documents）。None = 不打标（无构建/打标失败不阻断——retag 补做）。"""
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
        content_hash: str,
        mime_type: str,
        raw_object_key: str,
        pending_dims_json: str | None,
        pending_version: int | None = None,
        audit: tuple[str, str] | None = None,
    ) -> int:
        """覆盖上传的文档行更新：开新 pending 版本（parsing）——不动 active_* 五字段
        （v1 继续服务到 searchable_full 切换，D20）。

        pending_version=None = 事务内自算 max(历史)+1（P3-N5）；返回实际版本号；
        audit=(event_type, payload_json) 与版本开启**同一事务**（TC-OPS-01）。"""
        ...

    def set_doc_pending_failed(self, doc_id: str, version: int, error: str) -> None:
        """pending 版本失败：pending_status='failed' + pending_error + **立即物理删除
        该版本全部块**（ad 触发器移出 FTS——失败不留检索残留，T8）——同一事务。"""
        ...

    def delete_document(
        self, doc_id: str, audit: tuple[str, str] | None = None
    ) -> None:
        """删除文档（同事务：非终态任务置 failed(error='cancelled: document deleted')
        ——任务取消联动 TC-VER-07；级联 chunks/document_dimensions/chunk_vectors；
        tasks.doc_id ON DELETE SET NULL 保留历史；audit 治理事件同事务——TC-OPS-01）。"""
        ...

    def get_document_dims(self, doc_id: str) -> dict[str, list[str]]:
        """文档当前维度（document_dimensions 按 key 聚合——PATCH 旧值校验数据源）。"""
        ...

    def set_document_dims(
        self, doc_id: str, dims: dict[str, list[str]],
        audit: tuple[str, str] | None = None,
    ) -> None:
        """按 key 全量替换文档维度行（PATCH /dimensions 落点——D6 刷维度不重嵌；
        解析 (key,value)→(dimension_id,value_id) 同 pending_dims 逻辑；
        audit 治理事件同事务——TC-OPS-01）。"""
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

    def visible_documents(
        self,
        plan: AclPlan,
        *,
        dataset_ids: Sequence[str] | None = None,
        active_status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """按调用者权限的文档清单（M1-5 MCP list_documents 数据源——§6.1 docs
        组）：行集经 visible_docs CTE（一切统计按调用者权限——TC-AZ-02）；
        行含 doc_id/dataset_id/dataset_name/title/active·pending 双态四字段/
        source_uri/updated_at/chunk_count（在用块计数）/dims（document_dimensions
        聚合——D22）。"""
        ...

    def visible_dataset_counts(
        self, plan: AclPlan, *, dataset_ids: Sequence[str] | None = None
    ) -> list[dict]:
        """datasets 统计（§6.1：组织内全部库列出（库元数据非 ACL 客体），
        doc_count 按 visible_docs CTE 权限计数——不可见文档计入 0 不泄露）。"""
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

    def create_task(
        self, doc_id: str | None, *, task_type: str = "ingest",
        target_version: int | None = None, task_id: str | None = None,
        payload: str | None = None,
        audit: tuple[str, str] | None = None,
    ) -> str:
        """新建任务行（maintenance 等无文档任务 doc_id=None——P3-19 注解口径；
        tasks.doc_id ON DELETE SET NULL 允许 NULL）。

        target_version（0005/M2.1 R2 边界裁定 B(a)）：ingest 任务的目标文档版本
        ——取消与崩溃耗尽清扫按该版本落 pending failed（P2-3）；NULL=无版本任务。

        task_id：预生成 id 显式携带（治理 outbox 事件与任务行同源关联——M2.4）。

        payload（0006/M2-S1）：任务参数 JSON 文本（semantic_sync 携带
        {org, adapter, force?}——executor 分发面读取；NULL=无参数任务）。

        audit（m2s-2，G-16 收口）：``(event_type, payload_json)``——治理事件与
        任务行**同一事务**写入（沿 m2-2 outbox 先例；触发侧 create_task 与
        append_outbox 两事务的崩溃丢审计窗口就此闭合）。None=无审计任务行。
        """
        ...

    def get_task(self, task_id: str) -> dict | None:
        ...

    def pending_task_exists(self, task_type: str, payload: str) -> bool:
        """同型同参 pending 任务在队判定（G-19 每日兜底投递去重——防任务堆积）。"""
        ...

    def list_tasks(self, org_id: str, *, doc_id: str | None = None) -> list[dict]:
        ...

    def update_task(
        self, task_id: str, *, status: str | None = None, error: str | None = None
    ) -> None:
        """任务状态机推进（leased/running 由执行器调用；attempts 随 claim 认领递增）。

        P2-1 守卫（M2.1 R2）：done 仅非终态（pending/leased/running）可入——
        已终态零行生效（防在途执行器覆盖取消 failed / 新持有者终态）。"""
        ...

    # ---- 任务队列（租约·心跳·认领——M2.1 worker 框架，design §5.3） ----

    def claim_next_task(
        self,
        worker_id: str,
        *,
        lease_s: float,
        task_types: Sequence[str] = ("ingest", "maintenance"),
        max_attempts: int = 3,
        now: str | None = None,
        created_before: str | None = None,
    ) -> dict | None:
        """原子认领一个任务（pending，或租约过期的 leased/running——worker 崩溃后
        重认领，TC-TASK-01/TC-E2E-03）：status→leased + lease_owner/lease_until/
        heartbeat_at 落位；无可认领任务 → None。

        并发语义（真实并发窗口——两执行器竞争同任务恰好一人认领）：单语句
        UPDATE…WHERE id=(SELECT …)（sqlite 单写序列化）/ FOR UPDATE SKIP LOCKED
        （PG）——第二个认领者的候选子查询在首者提交后重估、不再命中。
        **attempts 随认领递增**（一次认领 = 一次执行尝试——认领后即崩也计数，
        防无限崩溃循环）；attempts ≥ max_attempts 的行不认领（重试上限，
        TC-TASK-02）。created_before 非 None 时仅认领 created_at <= 该时点的
        任务（inline 兜底循环的「陈旧任务」口径，P2-7）。"""

    def fail_exhausted_tasks(
        self, *, max_attempts: int, now: str | None = None
    ) -> list[dict]:
        """崩溃耗尽清扫（P2-2，M2.1 R2）：租约已过期且 attempts ≥ max 的
        leased/running 任务 → failed + error 原因（worker 反复崩溃后不滞留
        leased——「attempts ≥ 3 转 failed 留人工」的崩溃侧收口）。返回被清扫
        任务行（含 target_version——调用方按该版本落文档侧 pending failed）。"""
        ...

    def heartbeat_task(
        self, task_id: str, worker_id: str, *, lease_s: float, now: str | None = None
    ) -> bool:
        """心跳（每 worker_heartbeat_s）：刷新 heartbeat_at + lease_until。

        仅当 lease_owner=worker_id 且 status IN (leased, running) 时生效（租约
        被重认领/任务被取消/已终态 → False——执行器在阶段边界据此停止，
        TC-TASK-03）。"""

    def cancel_task(
        self, task_id: str, *, reason: str, now: str | None = None,
        audit: tuple[str, str] | None = None,
    ) -> dict | None:
        """任务取消（TC-TASK-03）：非终态（pending/leased/running）→ failed +
        error=reason + 清租约，返回取消后的任务行；已终态 → None（幂等不复活）。
        audit 治理事件与取消**同一事务**（仅取消实际生效时记——TC-OPS-01）。

        文档侧一致性（不滞留 parsing）由调用方（core 摄取消编排）在同一时刻
        落 pending 版本失败。"""

    def delete_expired_memberships(self, *, now: str | None = None) -> int:
        """过期成员关系物理清理（maintenance 任务体——design §3/§5.1：读路径只
        过滤不删除，物理删除交定时任务，触发 trg_membership_delete_cleanup 级联
        清授权）。返回删除行数。"""

    def delete_aged_tombstones(self, *, before_ts: str) -> int:
        """tombstone 块到期物理清理（maintenance 任务体——design §4「保留 90 天后
        物理删除」；时点基准 = chunks.tombstoned_at〔0004 迁移新增，切换事务写入〕
        <= before_ts；chunk_vectors 经 FK CASCADE 同步消失）。返回删除行数。"""

    def trim_finished_tasks(
        self, *, keep_days: int, keep_count: int, task_type: str = "maintenance",
        now: str | None = None,
    ) -> int:
        """maintenance 任务行保留策略（m1-3 P3-19）：done/failed 行先按天数截尾、
        再按条数上限保留最新 keep_count 行。返回删除行数。"""

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
        audit: tuple[str, str] | None = None,
    ) -> None:
        """首次上传的文档行（pending_version=1、pending_status='parsing'）；
        audit 治理事件与文档行**同一事务**（TC-OPS-01）。"""
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

    def delete_dataset(
        self, org_id: str, dataset_id: str,
        audit: tuple[str, str] | None = None,
    ) -> None:
        """删除知识库（§6.2 服务层流程——T19 半句收口/TC-OPS-04②③）：
        仍有文档 → DatasetNotEmptyError（RESTRICT 明确报错——非裸外键异常）；
        不存在/跨组织 → KeyError（404）；audit 治理事件与删行同事务。"""

    # ---- 维度治理（m2-3——TC-OPS-07：取值停用 dry_run / 维度退役） ----

    def dimension_value_impact(
        self, org_id: str, dim_id: str, value_id: str,
    ) -> dict | None:
        """取值停用影响面预估（dry_run 数据源——FR-4）：{docs, grants, users,
        locked_docs} = 引用该值的文档数 / 授权行数 / 持有者数 / **维度写锁
        文档数**（R2 边界3——v1.6.3「维度写锁项」显式化：组织内引用了非 active
        取值〔dry_run 视本值 disabled〕或 retired 维度取值的文档数——这些文档
        的 PATCH/覆盖上传将被锁；org 归属校验——不存在或跨组织 → None）。
        只读零副作用。"""

    def disable_dimension_value(
        self, org_id: str, dim_id: str, value_id: str, *,
        dry_run: bool = False,
        audit: tuple[str, str] | None = None,
    ) -> dict | None:
        """取值停用（TC-OPS-07①）：status→disabled（幂等——重复停用零新审计）；
        **T3 联动**：停用取值从授权展开消失（read_grants 的 v.status='active'
        三重过滤既有机制——收紧进计算）。dry_run=True 只返回预估（含
        locked_docs——见 dimension_value_impact）不落库；audit 治理事件与停行
        **同一事务**（仅实际执行时记）。返回 {docs, grants, users,
        locked_docs, applied}。"""

    def dimension_retire_impact(self, org_id: str, dim_id: str) -> dict | None:
        """维度退役影响面预估（二次确认数据源）：{docs, grants, values} =
        该维度有值文档数 / 授权行数 / 取值数。只读零副作用。"""

    def get_dimension_status(self, org_id: str, dim_id: str) -> str | None:
        """维度生命周期状态（'active'|'retired'——退役端点幂等 409 判据；
        不存在/跨组织 → None）。"""

    def retire_dimension(
        self, org_id: str, dim_id: str, *,
        audit: tuple[str, str] | None = None,
    ) -> dict | None:
        """维度退役（TC-OPS-07②——**T20 半句：唯一放宽路径**）：status→retired
        （幂等——重复退役零新审计）；退役后 read_grants 不再含该维度（dim
        .status='active' 过滤——编译产物不再生成该维度条件）。audit 治理事件
        与退役**同一事务**。返回 {docs, grants, values}；不存在 → None。"""

    # ---- 授权写路径（m2-3——TC-OPS-08 / TC-OPS-06 CSV 载体） ----

    def replace_local_grants(
        self, org_id: str, user_id: str,
        rows: Sequence[tuple[str, str, str | None]], *,
        audit: tuple[str, str] | None = None,
    ) -> dict:
        """用户 local 授权全量替换（TC-OPS-08——**只动 source='local' 行，
        sync 授权不动**；CSV 导入同载体）。rows=(dim_key, value, expires_at)
        目标全量态：先删该用户在本组织的全部 local 行再插入新行（幂等）；
        dim/value 不存在或不属本组织 → KeyError（400 语义）。audit 治理事件
        与替换**同一事务**。返回 {removed, inserted}。"""

    def list_grants_for_export(self, org_id: str) -> list[dict]:
        """组织全部授权行（CSV 导出 / 导入差异计算数据源）：[{username,
        user_id, dim_key, value, expires_at, source}]——含 sync 行（导出 CSV
        只取 local；UI 标注 sync 只读）。"""

    def find_user_by_username(self, username: str) -> dict | None:
        """username → 用户行（CSV 导入 username 列解析；无 → None）。"""

    # ---- 嵌入覆盖率（m2-3——TC-EMB-06 管理面只读面板） ----

    def embedding_coverage(
        self, org_id: str, embed_model: str,
    ) -> list[dict]:
        """各知识库嵌入覆盖率（RUNBOOK §1 闭合口径：分子/分母都限**在用块**
        ——tombstone=0 且 version=documents.active_version）：[{dataset_id,
        dataset_name, done, total}]——done=已有 (rid, embed_model) cv 行的在用
        块数。"""

    def read_pending_outbox_events(self) -> list[dict]:
        """未搬运 outbox 行（审计分级查询的当月未落库部分——created_at,id 序）。"""

    def trim_shipped_outbox(self, *, before_ts: str) -> int:
        """已搬运 outbox 行保留期清理（R2 P3-1——只删 shipped_at 非 NULL 且早于
        before_ts 的行；未搬运行永不删）。返回删除行数。"""

    def backup_snapshot(
        self, backup_dir, objects_dir=None, *, when=None, dsn: str | None = None,
    ) -> dict:
        """备份快照（NFR-10 / TC-OPS-05——挂 maintenance 任务族）：SQLite
        `VACUUM INTO` / PG `pg_dump -Fc`（部署工具链，不违 D2）+ objects 目录
        tar 一并备份 + **审计月库 tar**（m2-3 B3——sqlite `audit_*.db` 月库
        文件与 seal sidecar；pg 恒 None：月分区在库内、pg_dump 天然含）；
        返回 {database, objects, audit_months, created_at}。

        语义归属（P3-3/R2）：运维管理面操作（与审计月库滚动无关）——Admin 域；
        异常两态见 store/backup_common.py（工具缺失≠真实失败）。"""

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
        audit: tuple[str, str] | None = None,
    ) -> None:
        """凭证行落库（status='issued'——绑定 sub+org+服务身份三要素，#33 P1-3）；
        audit 治理事件同事务（TC-OPS-01）。"""
        ...

    def get_upload_credential(self, upload_id: str) -> dict | None:
        """凭证行（含 status/object_key/doc_id/task_id/expires_at 等全列）。"""
        ...

    def mark_upload_uploaded(self, upload_id: str, *, object_key: str) -> bool:
        """PUT 成功：status→uploaded + 对象键（WHERE status IN ('issued','uploaded')
        ——re-PUT 覆盖放行；并发已消费 → False＝409 语义）。"""
        ...

    def mark_upload_consumed(
        self, upload_id: str, *, doc_id: str, task_id: str,
        audit: tuple[str, str] | None = None,
    ) -> bool:
        """消费：status→consumed + 文档/任务关联回填（WHERE status='uploaded'——
        单次使用；竞态零行 → False＝409 语义）；audit 治理事件同事务（TC-OPS-01）。"""
        ...

    def list_expired_upload_credentials(self, now: str) -> list[dict]:
        """过期未消费凭证（status IN ('issued','uploaded') AND expires_at<=now）——
        maintenance 清理任务扫描面（TC-CRED-05）。"""
        ...

    def delete_upload_credential(self, upload_id: str) -> None:
        """凭证行删除（清理任务回收——已消费凭证保留供追溯，不进本方法）。"""
        ...


@runtime_checkable
class QualityBackend(Protocol):
    """区分度反馈环（design §5.4 / FR-3——M1-4）：近邻扫描 / 词频统计 / flags CRUD。

    近邻范围铁律（#33 P1-10）：**组织内 + 仅在用版本**（tombstone=0 AND
    version=documents.active_version）——tombstone 旧版本与他组织块不得互为
    拥挤近邻（否则换版窗口必然误报）。
    """

    def neighbor_sims(
        self, rid: int, embed_model: str, *, top_k: int = 8
    ) -> list[dict]:
        """给定块在组织内在用块中的 top-k 余弦近邻（SQL 暴力扫描——入库单块路径，
        §5.4「量小」）。行含 rid/chunk_id/doc_id/sim，按 sim 降序；排除自身；
        无向量块（无该标签 cv 行）返回 []。"""
        ...

    def org_active_chunk_count(self, org_id: str | None) -> int:
        """组织内在用块数（detected_at_scale 的「当前语料规模」与冷启动判定）；
        org_id=None = 全局语料（冷启动 IDF 兜底——TC-QUAL-02）。"""
        ...

    def token_doc_frequency(
        self, tokens: Sequence[str], org_id: str | None
    ) -> dict[str, int]:
        """token → 含该 token 的在用块数（df）。org_id=None 为全局语料（冷启动
        兜底——TC-QUAL-02）；范围 = 在用块（tombstone=0 AND version=active）。"""
        ...

    def org_active_chunk_vectors(
        self, org_id: str, embed_model: str
    ) -> Iterator[tuple[int, bytes]]:
        """组织内全部在用块的 (rid, **packed float32 bytes**)——numpy 批量重算的
        流式数据源（§5.4「分块载入 numpy」；M1-4 P2-4 / M1-5 改造：**惰性迭代
        器**、不物化全量行——100k×2560 档 Python float 对象 >1GB 根因消除；
        序列化收口各方言侧：sqlite=vec_f32 BLOB 原样 bytes / pg=vector 文本
        parse_vector_bytes 直转 packed）。"""
        ...

    def org_active_chunk_segs(self, org_id: str | None) -> list[str]:
        """组织内全部在用块的 content_seg（批量词面通用度重算的 df 流式统计源）；
        org_id=None = 全局语料（冷启动兜底——P2-1：小组织 IDF 缺失语义）。"""
        ...

    def chunks_for_quality_recompute(
        self,
        org_id: str,
        *,
        current_scale: int,
        rescale_ratio: float,
        sample_percent: int,
    ) -> list[dict]:
        """重算候选（TC-QUAL-04）：`detected_at_scale IS NULL OR < 当前规模×比例`
        的在用块 ∪ 确定性抽样（rid 散列 %100 < sample_percent）命中的块。
        行含 rid/chunk_id/doc_id/content/content_seg/detected_at_scale。"""
        ...

    def set_chunk_quality_marks(
        self, marks: Sequence[tuple[int, str | None]], *, scale: int
    ) -> None:
        """检测后批量回写 chunks.detected_at_scale / content_sha（marks=[(rid, sha)]；
        sha=None 保留原值——缓存键随 embed_model 语义由调用方保证，#42 P1-3）。"""
        ...

    def set_chunk_llm_keywords(self, rid: int, llm_keywords: str) -> None:
        """LLM 兜底词写 llm_keywords 独立列（§5.4——不动 keywords 人工列；
        sqlite au 触发器 / PG GENERATED 同步 FTS）。"""
        ...

    def append_chunk_manual_terms(
        self, rid: int, *, keywords: str, tags: str
    ) -> dict:
        """人工补标追加 chunks.keywords / chunks.tags（PATCH 落点——仅人工词、
        原样写入不进 jieba，TC-FTS-04）；返回追加后的两列值。"""
        ...

    def insert_quality_flag(
        self,
        *,
        chunk_id: str,
        doc_id: str,
        reason: str,
        detail_json: str,
    ) -> str:
        """写 open flag（同 chunk 同 reason 的既有 open flag 先删——重算覆盖语义）；
        返回 flag id。"""
        ...

    def delete_open_flags(self, rids: Sequence[int], reasons: Sequence[str]) -> int:
        """删除给定块的 open flags（reason 限定）——重算前清旧标记（§5.3 换模型
        重嵌入同款语义）。返回删除行数。"""
        ...

    def get_quality_flag(self, flag_id: str) -> dict | None:
        ...

    def list_quality_flags(
        self, doc_id: str | None = None, *, org_id: str | None = None,
        state: str | None = None,
    ) -> list[dict]:
        ...

    def set_quality_auto_keywords(self, flag_id: str, auto_keywords: str) -> None:
        """LLM 兜底一句定位语写 auto_keywords（TC-QUAL-03——报告页展示）。"""
        ...

    def set_quality_flag_state(self, flag_id: str, state: str) -> bool:
        """state 迁移（open|resolved|ignored）——resolved/ignored 落 resolved_at。"""
        ...

    def append_quality_manual_tags(self, flag_id: str, manual_json: str) -> None:
        """manual_tags 追加记录（人工补标审计轨迹——JSON 行累积）。"""
        ...

    def chunks_by_rids(self, rids: Sequence[int]) -> list[dict]:
        """按 rid 批量取块（detect_chunk 读取面 + 报告页可见近邻内容回填——
        content 过 ACL 后才调用；含 content_seg 供词面路取 token）。"""
        ...


@runtime_checkable
class SemanticBackend(Protocol):
    """M2-S：sync 分批 upsert / missing·retired 推进 / 构建产物与 sem_vec 读写 / L0 导出。

    种子方法签名（P3-17——M0b-1 随 PG backend 实作补齐）；m2s-1 扩充同步编排
    所需读写面（run 记录 / 引用面解析 / 别名重建 / 填充率统计）——SQL 全部
    下沉双方言实现（D24/v0.7.2 拍板3）。
    """

    def upsert_entities_batch(self, org_id: str, rows: Sequence[dict]) -> dict:
        """同步分批 upsert（只写事实列 name/attrs_json/parent_id/status/synced_at，
        分批 ≤1000 行/批——NFR-11 写锁治理；单批单事务）。

        rows 按父先子后有序；row = {type, key, name, attrs_json, parent_key,
        source_system, synced_at}（parent_key="type:key"——方法内解析 id，批内
        父行先落建 id 映射）。返回 {"inserted": n, "updated": n}——**事实列变更**
        计数（synced_at 刷新不计入——T-S3）。"""
        ...

    def resolve_entity_ids(
        self, org_id: str, keys: Sequence[tuple[str, str]]
    ) -> dict[tuple[str, str], int]:
        """(type, key) → 实体 id 解析（关系端点/missing 标记的读取面）。"""
        ...

    def sem_active_source_keys(
        self, org_id: str, source_system: str
    ) -> set[tuple[str, str]]:
        """库内该来源 active 实体键集（source_system=本适配器 AND
        status='active'——m2s-3 起 per-source_system 收口，yaml 纯人工实体
        source='curated' 同入基数；删除比例保护基数口径 #38 P2/T-S2）。"""
        ...

    def sem_source_fill_stats(self, org_id: str, source_system: str) -> dict:
        """该来源 active 实体的维度携带统计（attrs_json.dims 非空 = filled）——
        填充率骤降告警的库内基线（TC-SYNC-06②）。返回 {total, filled}。"""
        ...

    def sem_entity_states(
        self, org_id: str, entity_ids: Sequence[int]
    ) -> dict[int, dict]:
        """批量实体态 {id: {status, source}}——G-15 关系 upsert 前端点状态
        过滤与 yaml 合并冲突判定（m2s-3）共用读取面。"""
        ...

    def sem_entities_by_ids(
        self, org_id: str, entity_ids: Sequence[int]
    ) -> list[dict]:
        """批量实体行（O-2/m2s-3：expand_relations seed 节点信息面）。"""
        ...

    def mark_entities_missing(self, org_id: str, entity_ids: Sequence[int]) -> int:
        """快照消失实体 → status='missing'（宽限期状态机入口——T-S4①）。返回行数。"""
        ...

    def upsert_relations_batch(self, org_id: str, rows: Sequence[dict]) -> dict:
        """关系分批 upsert（端点不可变由 trg_sem_rel_noupdate 保证）。row =
        {src_id, rel_type, dst_id, attrs_json, synced_at, source?,
        source_system?}（source 缺省 'sync'——yaml 人工补关系 'curated'；
        G-15：端点非 active 不置回 active——CASE 守卫）。返回 inserted/updated。"""
        ...

    def sem_active_source_relation_keys(
        self, org_id: str, source_system: str
    ) -> set[tuple[int, str, int]]:
        """本源 active 关系键集（G-15 关系级消失检测——m2s-3）。"""
        ...

    def sem_mark_relations_missing(
        self, org_id: str, keys: Sequence[tuple[int, str, int]]
    ) -> int:
        """快照消失的关系 → status='missing'（G-15——源端独立删边、两端实体
        仍在；synced_at 保留为宽限起算锚）。返回行数。"""
        ...

    def sem_relations_lookup(
        self, org_id: str, keys: Sequence[tuple[int, str, int]]
    ) -> dict[tuple[int, str, int], dict]:
        """关系行批查 {key: {source, status}}——yaml 合并「与同步关系重复」
        判定面（§5.8 合并规则表第 6 行）。"""
        ...

    def rebuild_sync_aliases(self, org_id: str, rows: Sequence[dict]) -> int:
        """别名三 kind 重建（单事务先删后插——只动 kind IN ('name','code','sync')，
        manual/abbr 原样——T-S1 列级分工/TC-SYNC-05）。row = {type, key,
        aliases: [(alias, alias_norm, kind)]}。返回插入行数。"""
        ...

    def advance_status(self, org_id: str, *, missing_before: str) -> dict:
        """missing 宽限期推进（超期 missing → retired，关系一并 retired——T-S4；
        G-15：关系级 missing 同口推进）。返回 {missing, retired, relations_retired,
        relations_retired_standalone} 计数。"""
        ...

    def sem_start_run(self, org_id: str, adapter: str, *, now: str) -> int:
        """sem_sync_runs 插入 running 记录（§5.8 流程第 1 步）。返回 run id。"""
        ...

    def sem_finish_run(
        self, org_id: str, run_id: int, *, status: str, stats_json: str,
        error: str | None = None, now: str | None = None,
    ) -> None:
        """run 终态落库（succeeded / failed / aborted_guard + stats_json）。"""
        ...

    def sem_list_sync_runs(
        self, org_id: str, *, limit: int = 50,
        adapter: str | None = None, status: str | None = None,
    ) -> list[dict]:
        """同步记录与冲突报告（GET /semantic/sync-runs——stats_json 已解析；
        m2s-2 管理语义：limit 分页 + adapter/status 过滤——design §6.2）。"""
        ...

    def sem_list_builds(
        self, org_id: str, *, limit: int = 200, status: str | None = None,
    ) -> list[dict]:
        """构建记录（GET /semantic/builds——stats_json 已解析；m2s-2 管理语义：
        limit + status 过滤）。"""
        ...

    def sem_get_build(self, org_id: str, build_id: int) -> dict | None:
        """单条构建记录（GET /semantic/builds/{id}——他组织/未知 → None=404）。"""
        ...

    def sem_current_build(self, org_id: str) -> dict | None:
        """当前构建 = 最新 status='ready' 行（design §5.8：旧 ready 保留、服务按
        (org, dict_rev) 懒加载取用——无 ready → None）。"""
        ...

    def sem_active_snapshot(self, org_id: str) -> dict:
        """构建输入快照：active 实体 + 其全部别名（manual/abbr 含——dict_rev 覆盖
        人工别名变更）+ active 关系（§5.8 构建流程第 1 步）。行按稳定序返回。"""
        ...

    def sem_insert_build(
        self, org_id: str, dict_rev: str, stats_json: str, *,
        yaml_rev: str | None = None, sync_run_id: int | None = None,
    ) -> tuple[int, bool]:
        """building 行 upsert（UNIQUE(org,dict_rev)——失败行同 rev 重试复用行）。
        O-1/m2s-3 条件 upsert（DO UPDATE … WHERE status != 'ready'）：同 rev 行
        已 ready 时不重断 building（无 flap/双 ready 事件）——返回
        ``(existing_id, True)`` 交调用方走重激活/让位路径；正常路径
        ``(build_id, False)``。"""
        ...

    def sem_switch_build_ready(
        self, org_id: str, build_id: int, stats_json: str, *,
        audit: tuple[str, str] | None = None,
        snapshot_json: str | None = None,
    ) -> bool:
        """原子切换：building → ready 单语句单事务（design §5.8 第 3 步——旧 ready
        行不动、新行就位即当前；非 building 态零行生效返回 False——并发输者
        语义见 core/semantic/build.py，P2-2/R2）。

        audit（P3-5/R2，沿 create_task 先例）：ready 事件与切换**同一事务**且
        **仅切换真生效时写**（rowcount==1）——构建终态审计不丢（G-16 构建侧）。

        snapshot_json（G-21 方案 A/m2s-5）：构建快照附表同事务写入——ready
        可见时快照必已在位（冷缓存/重启服务 build 产物的数据基础）。"""
        ...

    def sem_fail_build(
        self, org_id: str, build_id: int, stats_json: str, *,
        audit: tuple[str, str] | None = None,
    ) -> bool:
        """构建失败收尾：building → failed + stats（error 载 stats_json.error——
        失败不切指针，旧 ready 继续为当前——T-S12 骨架）。**返回是否真生效**
        （rowcount==1——已终态行幂等零生效，P2-2/R2：调用方仅真生效时认失败，
        不因并发输者/迟到异常写脏审计）；audit 同事务同条件。"""
        ...

    def sem_reactivate_build(
        self, org_id: str, build_id: int, stats_json: str, *,
        audit: tuple[str, str] | None = None,
        snapshot_json: str | None = None,
    ) -> bool:
        """G-18/m2s-3：rev 回退重激活——ready 行顶置 activated_at 成为 current
        （+ ready 事件同事务）；仅 status='ready' 行生效（幂等防线）。
        snapshot_json（m2s-5/G-21 方案 A）：快照附表同事务 upsert（同 rev 内容
        一致——重写幂等；0008 前存量行此时补齐快照）。"""
        ...

    def sem_save_build_snapshot(
        self, org_id: str, build_id: int, snapshot_json: str,
    ) -> None:
        """快照附表 upsert（独立事务形态——switch/reactivate 事务内写入之外的
        显式入口；G-21 方案 A/m2s-5）。"""
        ...

    def sem_load_build_snapshot(
        self, org_id: str, build_id: int,
    ) -> str | None:
        """按 build id 读快照 JSON（无行 → None——get_annotator 回退 live 判据；
        G-21 方案 A/m2s-5）。"""
        ...

    def sem_retag_candidates(
        self, org_id: str, dict_rev: str, *, limit: int, after_rid: int = 0,
    ) -> list[dict]:
        """retag 候选块清单（TC-TAG-02）：该 org 活跃版本块（tombstone=0 且
        version=active_version）中 sem_chunk_entities 最大 dict_rev != 目标 rev
        **或无行**（从未打标/打标失败——TC-TAG-01 预期②的补做面）的块，
        [{rid, content}] 按 rid 稳定序、limit 截断（分批 ≤1000——NFR-11）；
        after_rid 游标分页（无命中块无行可写、不消候选——靠游标推进防死循环）。"""
        ...

    def sem_last_retag_done_at(self, org_id: str) -> str | None:
        """该 org 最近一次 done 的 semantic_retag 任务时点（对账投递节流锚
        ——m2s-5：无行块重标不消候选，节流窗口防重复投递风暴）。"""
        ...

    def sem_replace_chunk_tags(self, org_id: str, rows: Sequence[dict]) -> int:
        """块级标签整替（同事务）：rows 涉及的 chunk_rid 集 DELETE 旧行 +
        INSERT 新行（retag 重算面——幂等收敛；块已删/版本已切时由 untag/
        对账负责，本方法不做存活过滤——调用方只投活跃块）。返回插入行数。"""
        ...

    def sem_reconcile_chunk_tags(self) -> list[dict]:
        """打标对账扫描（T-S10/TC-TAG-03 兜底——maintenance 挂载）：
        ① 悬挂行清理（chunk 不在/非活跃版本块——物理 DELETE，计数报告）；
        ② 实体已亡行清理（entity status != 'active'——同 DELETE 面）；
        ③ dict_rev 落后计数（活跃块有行且 dict_rev != current，**只报告不
        改动**——补投 retag 幂等收敛，调用方按报告投递）+ 无行活跃块单列
        untagged_chunks（retag 补做面——无行不消候选，投递按节流防风暴）。
        返回 per-org 报告 [{org_id, stale_chunks_removed, retired_entities_
        removed, lagging_chunks, untagged_chunks}]（无 sem_chunk_entities 行
        的 org 不出现）。"""
        ...

    def save_build(self, org_id: str, dict_rev: str, stats_json: str) -> int:
        """构建产物登记（sem_builds——dict_rev = f(active 快照, YAML commit, embed_model)）。"""
        ...

    def load_build(self, org_id: str, dict_rev: str) -> dict | None:
        """按 (org, dict_rev) 读构建产物（AC 自动机/模糊索引/L0 懒加载入口）。"""
        ...

    def export_l0(self, org_id: str) -> str:
        """L0 术语片段导出（1500 token 预算——§6.3/agent 中间件注入源；
        构建产物落地归 m2s-2——本段返回空串占位）。"""
        ...

    # ---- m2s-2 首批语义工具读取面（get_entity / search_entities / describe_table
    #      ——SQL 全部下沉本域，core 只做编排与校验；design §5.9/§6.3） ----

    def sem_entity_by_id(self, org_id: str, entity_id: int) -> dict | None:
        """按 id 取实体行（含 attrs_json/curated_json/sensitivity——T-S7 组织隔离
        第一条件 org_id）。"""
        ...

    def sem_entity_by_key(self, org_id: str, type_: str, key: str) -> dict | None:
        """按 (type, key) 取实体行（get_entity 的 key 定位路径——"type:key"）。"""
        ...

    def sem_entity_aliases(
        self, org_id: str, entity_ids: Sequence[int]
    ) -> list[dict]:
        """实体别名行（include=['aliases'] 数据源——全部 kind，alias_norm 含）。"""
        ...

    def sem_expand_graph(
        self, org_id: str, root_id: int, *,
        outgoing: Sequence[str], incoming: Sequence[str],
        depth: int, fanout_limit: int, node_limit: int,
    ) -> dict:
        """关系展开（design §5.9 递归展开的等价 SQL 实现——BFS 逐层批量查询，
        语义与递归 CTE 等价；双方言同实现策略）：

        - 只走 status='active' 关系与 active 端点；restricted 实体不出现
          （fail-closed——T-S9，持权路径 M2-S3）；
        - outgoing/incoming：rel_type 集合（方向后缀已在 core 解析）；
        - fanout_limit：单节点每层出边截断；node_limit：总节点数截断——命中
          任一 → truncated=True（T-S6）；
        - 防环：visited 集合（节点只入一次——环图正常返回不死循环）。

        返回 {"nodes": [{id,type,key,name,depth}], "edges": [{src,rel,dst,source}],
        "truncated": bool}（nodes 不含 root）。"""
        ...

    def sem_search_entities(
        self, org_id: str, q_norm: str, q_raw: str, *,
        types: Sequence[str] | None, top_k: int,
    ) -> list[dict]:
        """实体检索（TC-SEM-05 前半——排序链「别名精确 > 别名前缀 > label 模糊」；
        拼音/向量归 M2-S3）：三层 UNION（score 1.0/0.8/0.5）+ 实体去重保最优，
        返回 [{id,type,key,name,attrs_json,curated_json,score,via}]。"""
        ...

    def sem_table_columns(self, org_id: str, table_id: int) -> list[dict]:
        """表实体的本地轻量列节点（describe_table 降级路径——T-S11③：
        元数据系统不可用时返回 [{key,name}]）。"""
        ...

    # ---- m2s-3：YAML curated 合并面 + FTS 索引面（SQL 下沉双方言——D24） ----

    def sem_write_curated_batch(self, org_id: str, rows: Sequence[dict]) -> int:
        """curated_json 批写（§5.8 合并规则表第 1 行）。row = {type, key,
        curated_json, curated_rev, sensitivity?}——仅 active 实体生效。"""
        ...

    def sem_replace_manual_aliases(self, org_id: str, rows: Sequence[dict]) -> int:
        """manual/abbr 别名整替（先删后插只动这两类——T-S1 分工）。row = {type,
        key, aliases: [(alias, alias_norm, kind, match_mode)]}。"""
        ...

    def sem_clear_stale_curated(
        self, org_id: str, keep_entity_ids: Sequence[int]
    ) -> int:
        """YAML 删除覆盖项（规则表第 8 行）：source='sync' 且 curated_rev 非空、
        不在 keep 集 → 清 curated_json/curated_rev + 删 manual/abbr 别名（事实列
        不动）。返回清理行数。"""
        ...

    def sem_refresh_search_texts(self, org_id: str, entity_ids: Sequence[int]) -> None:
        """实体 FTS 文本行重建（C.3——名称+别名分词进 sem_search_texts；sqlite
        外容表 FTS5 / pg tsvector GENERATED 双方言内部消化）。"""
        ...

    def sem_restricted_column_keys(self, org_id: str, table_id: int) -> set[str]:
        """C.5：表下 restricted 列键集（describe_table 主路径列级过滤面）。"""
        ...


@runtime_checkable
class AuditBackend(Protocol):
    def append_outbox(self, event_type: str, payload_json: str) -> None:
        """outbox 写入（与业务写同事务——「业务改了就一定有审计」；M0a-3 起实装：
        探针两档告警 / 工具参数 org 忽略等事件）。

        M2.4 m2-2 起治理动作（上传/覆盖/删除/取消/维度 PATCH/凭证签发与消费）
        不再走本方法，而是经各 Admin/Ingest 域方法的 ``audit=(event_type,
        payload_json)`` 参数**同事务**写入（TC-OPS-01）；本方法保留给查询级
        审计等独立事件（检索/maintenance.run 沿用）。
        """

    def ship_outbox(self, *, now: str | None = None, batch: int = 500) -> dict:
        """搬运 shipped_at IS NULL 的 outbox 行 → 月库 audit_events（哈希链逐行
        计算——FR-6）+ 回填 shipped_at（A2/TC-OPS-01；挂 maintenance executor）。

        方言形态：pg 同库真同事务（BEGIN…COMMIT）；sqlite 跨文件两步幂等
        （月库 INSERT OR IGNORE → 回填）——不丢不重语义等价。
        """

    def read_monthly_events(self, *, when: str) -> list[dict]:
        """读指定时点所在月的 audit_events 行（m2-3 B2 起为**链遍历序**——
        walk_chain 按链重排与逐行哈希验证，不依赖 rowid/seq 读序〔G-13 对冲〕；
        R1 期行语义列 detail_json 兜底〔B5〕；破链 raise AuditChainError。
        sqlite 封存月库只读打开 / pg 分区查询）。"""

    def read_last_maintenance_stats(self) -> dict | None:
        """最近一次 maintenance.run 的 stats（m2-3 B4——运维面板 GET stats 端点
        数据源，含 audit_outbox_trimmed 等新键）：outbox 最近行优先、无则当月
        月库（链遍历读序）最近行；无 → None。"""

    def seal_audit_months(self, *, now: str | None = None) -> dict:
        """封存过月月库（sqlite：末哈希 sidecar + 0444 只读；pg：分区 sealed
        触发器 + REVOKE + audit_month_seals 记录）——B 组/TC-OPS-02①。"""

    def prune_audit_months(self, *, keep_months: int, now: str | None = None) -> dict:
        """保留期整文件/分区删除（默认 12 个月——TC-OPS-02③）。"""

    def roll_monthly(self, when: object | None = None) -> object:
        """月库/分区滚动（方言差异在包内吸收——SQLite 月库文件 / PG 按月分区）。"""


@runtime_checkable
class StorageBackend(
    SearchBackend,
    IngestBackend,
    AclBackend,
    AdminBackend,
    QualityBackend,
    SemanticBackend,
    AuditBackend,
    Protocol,
):
    """组合协议——存储后端唯一接口（D24：SQLite 默认 / PG+pgvector 可选，配置级切换）。"""
