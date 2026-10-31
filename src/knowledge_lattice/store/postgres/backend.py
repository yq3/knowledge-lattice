"""PostgreSQL 后端——StorageBackend 协议的 PG 实现（D24——M0b-1 PG spike）。

域覆盖（当前协议种子范围内六域）：

- **Acl**：read_membership / read_grants——§5.1 第 0/2 步读取收口，SQL 与
  SqliteBackend 同构（仅参数语法与 CURRENT_TIMESTAMP/:now 选择不同），三重
  过滤（active 维度 / active 取值 / 未过期）+ LEFT JOIN 空集语义一致；
- **Ingest**：insert（chunks+阶段状态+首次上传 D20 切换单事务——普通 BEGIN/
  COMMIT，MVCC 等价 §4 PG 映射）/ write_embeddings（浮点向量 → pgvector 文本
  形态 + ::vector 转型，序列化收口本方言侧——P2-3/D24）/ pending_embeddings /
  mark_embedding_batch / delete_by_doc；switch_active_version 随 M1（与 sqlite 同）；
- **Admin**：任务状态机 / 文档状态 / 指纹基线 / 维度取值与库只读 / 静态 token；
- **Audit**：append_outbox + roll_monthly（按月分区滚动——接口与 sqlite 月库
  滚动不变，design §4 PG 映射）；
- **Search**：recall_fts（五列 tsvector 加权 ts_rank 求和）+ recall_vec（`<=>`
  精确扫描起步——G-6）+ visible_chunk_ids / rids_without_vector（ACL 双断言源
  与 vector_pending 判定）——**M1-1 实装**，检索配方双后端等价（design §8 M1.1）；
  render_vec_recall_select 供向量列 `<=>` 断言与实验起步；
- **Semantic**：M2-S1 实装——sync 分批 upsert / missing·retired 推进 / run 记录 /
  build 读写（L0 导出占位归 m2s-2），与 sqlite 同语义同消息源。

连接模型：持有单个 psycopg Connection（autocommit——显式 BEGIN/COMMIT 由写路径
自管）；池化形态经 connection.connect_pool + ThreadLocal 代理随 M1 服务化落地。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from knowledge_lattice.store.backend import AclPlan, VersionConflictError
from knowledge_lattice.store.postgres.audit import ensure_month_partition
from knowledge_lattice.store.postgres.vec import format_vector

__all__ = ["PgBackend"]


class PgBackend:
    """持有单个主库连接的 PostgreSQL 后端（测试/单进程形态；池化随 M1）。"""

    # delete_open_flags 的 rid 分批上限（M1-5：PG 单语句绑定参数上限 65535——
    # 预留 reasons 位后 32000 安全；sqlite 侧同款数值）
    _DELETE_FLAG_BATCH = 32_000

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    # ============ Acl 域（§5.1 第 0/2 步读取收口——与 SqliteBackend 同构） ============

    def read_membership(
        self, user_id: str, org_id: str, *, now: str | None = None
    ) -> dict | None:
        """有效成员关系行（含 `expires_at IS NULL OR expires_at > now` 过滤——第 0 步）。

        无有效行 → None（编译入口拒绝，403 语义）。
        """
        if now is None:
            row = self._conn.execute(
                "SELECT role, expires_at FROM user_org_memberships"
                " WHERE user_id = %(uid)s AND org_id = %(org)s"
                "   AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
                {"uid": user_id, "org": org_id},
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT role, expires_at FROM user_org_memberships"
                " WHERE user_id = %(uid)s AND org_id = %(org)s"
                "   AND (expires_at IS NULL OR expires_at > %(now)s)",
                {"uid": user_id, "org": org_id, "now": now},
            ).fetchone()
        return None if row is None else {"role": row[0], "expires_at": row[1]}

    def read_grants(
        self, user_id: str, org_id: str, *, now: str | None = None
    ) -> dict[str, tuple[str, ...]]:
        """授权展开（第 2 步，单条 SQL）：org 的全部 active 维度 → 有效授权取值集。

        三重过滤（#34 必修 1 / T1 / T3）+ 取值归属校验（M0a-2 Committer R1 P2-1
        同款：`v.dimension_id = dim.id`，畸形授权行不计入任何维度）。
        """
        now_filter = "CURRENT_TIMESTAMP" if now is None else "%(now)s"
        params: dict[str, object] = {"uid": user_id, "org": org_id}
        if now is not None:
            params["now"] = now
        sql = (
            "SELECT dim.key, v.value"
            " FROM dimensions dim"
            " LEFT JOIN user_dimension_grants g"
            "   ON g.dimension_id = dim.id AND g.user_id = %(uid)s"
            f"  AND (g.expires_at IS NULL OR g.expires_at > {now_filter})"
            " LEFT JOIN dimension_values v"
            "   ON v.id = g.value_id AND v.dimension_id = dim.id AND v.status = 'active'"
            " WHERE dim.org_id = %(org)s AND dim.status = 'active'"
            " ORDER BY dim.key, v.value"
        )
        grants: dict[str, set[str]] = {}
        for dim_key, value in self._conn.execute(sql, params):
            bucket = grants.setdefault(dim_key, set())
            if value is not None:  # 停用取值/无授权 → NULL 行（收紧）
                bucket.add(value)
        return {key: tuple(sorted(values)) for key, values in grants.items()}

    # ============ Search 域（M1-1 实装：FTS/向量召回 + 名次协议 + 双断言源） ============

    def recall_fts(
        self, tokens: list[str], plan: AclPlan, *, top_k: int = 20
    ) -> list[dict]:
        """FTS 召回（M1-1）：tokens → to_tsquery 'simple'（`&` 连接、引号字面量）
        + 五列 tsvector GENERATED @@ 匹配 + 加权 ts_rank 求和（§4 PG 映射）。

        ts_rank 越大越相关（DESC）——方向差异在本层吸收为名次：行含 rank（1 起，
        M1-1 名次协议 #42 P1-8）；score_raw 仅供观察（不跨后端比对——A-17/G-6）。
        空查询串（tokens 全滤）返回 []。dims 聚合回填与 sqlite 同源（D22）。
        """
        from knowledge_lattice.store.postgres.acl_render import render_fts_recall_select
        from knowledge_lattice.store.postgres.fts import build_tsquery

        tsquery = build_tsquery(tokens)
        if not tsquery:
            return []
        sql, params = render_fts_recall_select(plan, tsquery, top_k=top_k)
        cursor = self._conn.execute(sql, params)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        self._attach_dims(rows)
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        return rows

    def recall_vec(
        self, query_vec: list[float], plan: AclPlan, *, top_k: int = 20
    ) -> list[dict]:
        """向量召回（M1-1）：先 ACL 过滤后距离——`<=>` 精确扫描起步（G-6：2560 维
        超 vector 索引 2000 上限，halfvec/表达式索引评估留 M1-4 TC-PERF）；
        JOIN chunk_vectors cv（cv.embed_model = plan.embed_model 谓词——TC-EMB-02/07）。
        序列化收口本方言侧（pgvector 文本形态 ::vector——core 传浮点向量，P2-3）。
        """
        from knowledge_lattice.store.postgres.acl_render import render_vec_recall_select

        sql, params = render_vec_recall_select(plan, format_vector(query_vec), top_k=top_k)
        cursor = self._conn.execute(sql, params)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        self._attach_dims(rows)
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        return rows

    def visible_chunk_ids(
        self, plan: AclPlan, rids: list[int] | None = None
    ) -> set[int]:
        """可见块 rid 集合（基础路 SQL——rerank 前/返回前 ACL 双断言数据源，TC-ACL-08）。

        rids 非 None 时按给定块集收窄（AND c.rid IN (…)——同 sqlite 口径）。
        """
        from knowledge_lattice.store.postgres.acl_render import render_select

        sql, params = render_select(plan)
        if rids:
            marks = ", ".join(f"%(vr{i})s" for i in range(len(rids)))
            sql += f" AND c.rid IN ({marks})"
            params.update({f"vr{i}": rid for i, rid in enumerate(rids)})
        return {r[0] for r in self._conn.execute(sql, params)}

    def rids_without_vector(
        self, rids: list[int], embed_model: str
    ) -> set[int]:
        """给定 rid 中无 (rid, embed_model) cv 行的子集（vector_pending 块级判定）。"""
        if not rids:
            return set()
        marks = ", ".join(f"%(r{i})s" for i in range(len(rids)))
        params: dict[str, object] = {f"r{i}": rid for i, rid in enumerate(rids)}
        params["label"] = embed_model
        rows = self._conn.execute(
            "SELECT c.rid FROM chunks c"
            f" WHERE c.rid IN ({marks})"
            "   AND NOT EXISTS (SELECT 1 FROM chunk_vectors cv"
            "     WHERE cv.rid = c.rid AND cv.embed_model = %(label)s)",
            params,
        ).fetchall()
        return {r[0] for r in rows}

    def _attach_dims(self, rows: list[dict]) -> None:
        """按 doc_id 聚合 document_dimensions → rows[i]["dims"]（与 sqlite 同源，D22）。"""
        doc_ids = sorted({r["doc_id"] for r in rows})
        if not doc_ids:
            return
        marks = ", ".join(f"%(d{i})s" for i in range(len(doc_ids)))
        params = {f"d{i}": doc for i, doc in enumerate(doc_ids)}
        dims: dict[str, dict[str, list[str]]] = {doc: {} for doc in doc_ids}
        for doc_id, key, value in self._conn.execute(
            "SELECT dd.doc_id, dim.key, v.value"
            " FROM document_dimensions dd"
            " JOIN dimensions dim ON dim.id = dd.dimension_id"
            " JOIN dimension_values v ON v.id = dd.value_id"
            f" WHERE dd.doc_id IN ({marks})"
            " ORDER BY dim.key, v.value",
            params,
        ):
            dims[doc_id].setdefault(key, []).append(value)
        for r in rows:
            r["dims"] = dims.get(r["doc_id"], {})

    def recall_by_entities(self, entity_ids, plan: AclPlan, *, top_k: int = 30) -> list[dict]:
        raise NotImplementedError("实体召回路随 M2-S3（D23 §5.10）")

    def expand_relations(self, org_id: str, seed_ids, rels, *, depth: int = 1) -> dict:
        """薄适配实现见 Semantic 域（P3-3/R2——NotImplementedError 占位已删）。"""
        return _expand_relations_thin(self, org_id, seed_ids, rels, depth=depth)

    # ============ Ingest 域（chunks+状态同事务 / 嵌入回写——MVCC 普通事务） ============

    _CHUNK_COLS = (
        "id, doc_id, seq, version, content, title_seg, content_seg, token_count,"
        " heading_path, page_no, sheet_name, bbox_json, keywords, llm_keywords, tags"
    )

    def insert(self, doc_id: str, version: int, chunks: list[dict]) -> None:
        """chunks + 阶段状态 + 首次上传 D20 切换——同一事务（BEGIN … COMMIT）。

        幂等（TC-ING-07）与 pending_dims 解析防护（P3-7：逐值命中校验，不符
        raise → 整事务回滚）与 SqliteBackend 逐条同源。M2.1 并发面收口：事务内
        pending 存活复核（pending_status='failed' → raise，防取消窗口复活——
        FOR UPDATE 行锁与 set_doc_pending_failed 串行化，sqlite 同构）。
        """
        conn = self._conn
        conn.execute("BEGIN")
        try:
            pending_row = conn.execute(
                "SELECT pending_status FROM documents"
                " WHERE id = %(doc)s AND pending_version = %(v)s FOR UPDATE",
                {"doc": doc_id, "v": version},
            ).fetchone()
            if pending_row is not None and pending_row[0] == "failed":
                conn.execute("ROLLBACK")
                raise VersionConflictError(
                    f"insert rejected: doc={doc_id!r} v{version} pending 已 failed"
                    "（取消/并发失败先落账——版本亡故不复活，P0-2.3/TC-TASK-03）"
                )
            conn.execute(
                "DELETE FROM chunks WHERE doc_id = %(doc)s AND version = %(v)s",
                {"doc": doc_id, "v": version},
            )
            for ch in chunks:
                conn.execute(
                    f"INSERT INTO chunks({self._CHUNK_COLS}) VALUES"
                    " (%(id)s, %(doc_id)s, %(seq)s, %(version)s, %(content)s,"
                    " %(title_seg)s, %(content_seg)s, %(token_count)s, %(heading_path)s,"
                    " %(page_no)s, %(sheet_name)s, %(bbox_json)s, %(keywords)s,"
                    " %(llm_keywords)s, %(tags)s)",
                    {
                        "id": ch["id"],
                        "doc_id": doc_id,
                        "seq": ch["seq"],
                        "version": version,
                        "content": ch["content"],
                        "title_seg": ch.get("title_seg", ""),
                        "content_seg": ch.get("content_seg", ""),
                        "token_count": ch.get("token_count"),
                        "heading_path": ch.get("heading_path"),
                        "page_no": ch.get("page_no"),
                        "sheet_name": ch.get("sheet_name"),
                        "bbox_json": ch.get("bbox_json"),
                        "keywords": ch.get("keywords", ""),
                        "llm_keywords": ch.get("llm_keywords", ""),
                        "tags": ch.get("tags", ""),
                    },
                )
            conn.execute(
                "UPDATE documents SET pending_status = 'searchable_lexical',"
                " updated_at = CURRENT_TIMESTAMP"
                " WHERE id = %(doc)s AND pending_version = %(v)s",
                {"doc": doc_id, "v": version},
            )
            # pending_dims_json → document_dimensions：**仅首次上传**（本次事务
            # 随 D20 切换一并生效）；覆盖上传不在此解析——P0-2.1/T6，落地收口
            # switch_active_version 切换事务（与 sqlite 同构）
            active_row = conn.execute(
                "SELECT active_version FROM documents WHERE id = %(doc)s", {"doc": doc_id}
            ).fetchone()
            if active_row is not None and active_row[0] == 0:
                self._resolve_pending_dims(conn, doc_id)
            # D20 首次上传切换：active_version=0 → 在 searchable_lexical 即刻切在用
            conn.execute(
                "UPDATE documents SET"
                " active_version = pending_version, active_status = 'searchable_lexical',"
                " pending_version = NULL, pending_status = NULL, pending_error = NULL,"
                " page_count = COALESCE(page_count, %(page_count)s),"
                " updated_at = CURRENT_TIMESTAMP"
                " WHERE id = %(doc)s AND active_version = 0 AND pending_version = %(v)s",
                {
                    "doc": doc_id,
                    "v": version,
                    "page_count": len({c.get("page_no") for c in chunks}),
                },
            )
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except psycopg.Error:
                pass
            raise

    @staticmethod
    def _resolve_pending_dims(conn, doc_id: str) -> None:
        """pending_dims_json → document_dimensions（同事务；与 SqliteBackend 逐条同源）。"""
        row = conn.execute(
            "SELECT pending_dims_json FROM documents WHERE id = %(doc)s", {"doc": doc_id}
        ).fetchone()
        dims_json = row[0] if row else None
        if not dims_json:
            return
        expected = {
            (key, value)
            for key, values in json.loads(dims_json).items()
            for value in values
        }
        inserted = 0
        conn.execute(
            "DELETE FROM document_dimensions WHERE doc_id = %(doc)s", {"doc": doc_id}
        )
        for dim_key, value in expected:
            cur = conn.execute(
                "INSERT INTO document_dimensions(doc_id, dimension_id, value_id)"
                " SELECT %(doc)s, dim.id, v.id FROM dimensions dim"
                " JOIN dimension_values v ON v.dimension_id = dim.id"
                "   AND v.value = %(value)s"
                " WHERE dim.org_id = (SELECT org_id FROM documents WHERE id = %(doc)s)"
                "   AND dim.key = %(key)s",
                {"doc": doc_id, "key": dim_key, "value": value},
            )
            inserted += cur.rowcount
        if inserted != len(expected):
            raise RuntimeError(
                f"pending_dims resolution mismatch: inserted {inserted}"
                f" != expected {len(expected)}（维度/取值已被停用或删除？）"
                "——事务回滚、pending_dims_json 保留"
            )
        conn.execute(
            "UPDATE documents SET pending_dims_json = NULL WHERE id = %(doc)s",
            {"doc": doc_id},
        )

    def mark_embedding_batch(self, doc_id: str, version: int, batch_label: str) -> list[dict]:
        """批次启动时钉死标签（§5.3）——认领在处理块且 chunk_vectors 无该 (rid, label)
        行（v1.1 分表口径，与 SqliteBackend 同构）。"""
        rows = self._conn.execute(
            "UPDATE chunks SET embed_model = %(label)s"
            " WHERE doc_id = %(doc)s AND version = %(v)s AND tombstone = 0"
            "   AND NOT EXISTS (SELECT 1 FROM chunk_vectors cv"
            "     WHERE cv.rid = chunks.rid AND cv.embed_model = %(label)s)"
            " RETURNING rid, content",
            {"doc": doc_id, "v": version, "label": batch_label},
        ).fetchall()
        return [{"rid": r[0], "content": r[1]} for r in rows]

    def write_embeddings(
        self, batch_label: str, rows: list[tuple[int, list[float]]]
    ) -> int:
        """逐批回写向量入 chunk_vectors（防护：rid 在批 + tombstone=0 + 标签匹配
        + (rid, label) 无行——PK 冲突零触碰；同 rid 异标签照常写入=蓝绿并存）。

        P2-3/D24：接收浮点向量、pgvector 文本序列化收口本方言侧
        （`%(vec)s::vector` 显式转型——core 不碰方言）。
        """
        written = 0
        for rid, vector in rows:
            cur = self._conn.execute(
                "INSERT INTO chunk_vectors(rid, embed_model, embedding)"
                " SELECT %(rid)s, %(label)s, %(vec)s::vector FROM chunks c"
                " WHERE c.rid = %(rid)s AND c.tombstone = 0 AND c.embed_model = %(label)s"
                " ON CONFLICT (rid, embed_model) DO NOTHING",
                {"vec": format_vector(vector), "label": batch_label, "rid": rid},
            )
            written += cur.rowcount
        return written

    def pending_embeddings(self, batch_label: str) -> list[dict]:
        """已钉标签未回写的待嵌入块（v1.1：无行判定 = chunk_vectors 无该 (rid, label)）。"""
        rows = self._conn.execute(
            "SELECT c.rid, c.content FROM chunks c"
            " WHERE c.embed_model = %(label)s AND c.tombstone = 0"
            "   AND NOT EXISTS (SELECT 1 FROM chunk_vectors cv"
            "     WHERE cv.rid = c.rid AND cv.embed_model = %(label)s)"
            " ORDER BY c.rid",
            {"label": batch_label},
        ).fetchall()
        return [{"rid": r[0], "content": r[1]} for r in rows]

    def delete_by_doc(self, doc_id: str, version: int) -> int:
        cur = self._conn.execute(
            "DELETE FROM chunks WHERE doc_id = %(doc)s AND version = %(v)s",
            {"doc": doc_id, "v": version},
        )
        return cur.rowcount

    def switch_active_version(self, doc_id: str, expected_pending: int) -> None:
        """覆盖上传切换单事务（design §5.3 切换 SQL 逐项——与 SqliteBackend 同构，
        普通 BEGIN/COMMIT（MVCC）+ 行级乐观校验）。"""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            row = conn.execute(
                "SELECT active_version FROM documents"
                " WHERE id = %(doc)s AND pending_version = %(expected)s"
                "   AND pending_status = 'searchable_full'"
                " FOR UPDATE",
                {"doc": doc_id, "expected": expected_pending},
            ).fetchone()
            if row is None:
                raise VersionConflictError(
                    f"switch rejected: doc={doc_id!r} pending_version"
                    f" != {expected_pending} 或未达 searchable_full"
                    "（并发切换/取消？——乐观校验，P0-2.3）"
                )
            old_version = row[0]
            conn.execute(
                "DELETE FROM chunk_vectors"
                " WHERE rid IN (SELECT rid FROM chunks"
                "                WHERE doc_id = %(doc)s AND version = %(old)s)",
                {"doc": doc_id, "old": old_version},
            )
            conn.execute(
                "UPDATE chunks SET tombstone = 1, tombstoned_at = CURRENT_TIMESTAMP,"
                " title_seg = '', content_seg = '', keywords = '',"
                " llm_keywords = '', tags = ''"
                " WHERE doc_id = %(doc)s AND version = %(old)s",
                {"doc": doc_id, "old": old_version},
            )
            cur = conn.execute(
                "UPDATE documents SET"
                " active_version = pending_version, active_status = pending_status,"
                # R2 P2-1：成功切换清空 active_error（与 sqlite 同构——状态互斥）
                " active_error = NULL,"
                " pending_version = NULL, pending_status = NULL, pending_error = NULL,"
                " updated_at = CURRENT_TIMESTAMP"
                " WHERE id = %(doc)s AND pending_version = %(expected)s"
                "   AND pending_status = 'searchable_full'",
                {"doc": doc_id, "expected": expected_pending},
            )
            if cur.rowcount == 0:
                raise VersionConflictError(
                    f"switch rejected: doc={doc_id!r} pending_version changed"
                    " mid-transaction（乐观校验零行）"
                )
            self._resolve_pending_dims(conn, doc_id)
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except psycopg.Error:
                pass
            raise

    def max_document_version(self, doc_id: str) -> int:
        """历史最大版本号（active/pending/chunks 三源 max——与 sqlite 同构）。"""
        row = self._conn.execute(
            "SELECT MAX(m) FROM ("
            "  SELECT active_version AS m FROM documents WHERE id = %(doc)s"
            "  UNION ALL SELECT pending_version FROM documents WHERE id = %(doc)s"
            "  UNION ALL SELECT MAX(version) FROM chunks WHERE doc_id = %(doc)s)"
            " AS v(m)",
            {"doc": doc_id},
        ).fetchone()
        return row[0] or 0

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
        """覆盖上传开新 pending 版本（写入级防并发——同 sqlite 口径）。

        pending_version=None = 事务内自算 max(历史)+1（P3-N5——读写同一事务，
        MVCC 下并发窗口由 WHERE 零行兜底）；返回实际版本号。audit 同事务。
        """
        conn = self._conn
        conn.execute("BEGIN")
        try:
            if pending_version is None:
                pending_version = self._max_document_version_locked(conn, doc_id) + 1
            cur = conn.execute(
                "UPDATE documents SET"
                " pending_version = %(v)s, pending_status = 'parsing', pending_error = NULL,"
                " pending_dims_json = %(dims)s, content_hash = %(hash)s, mime_type = %(mime)s,"
                " raw_object_key = %(obj)s, updated_at = CURRENT_TIMESTAMP"
                " WHERE id = %(doc)s"
                "   AND (pending_version IS NULL OR pending_status = 'failed')",
                {
                    "doc": doc_id, "v": pending_version, "dims": pending_dims_json,
                    "hash": content_hash, "mime": mime_type, "obj": raw_object_key,
                },
            )
            if cur.rowcount == 0:
                raise VersionConflictError(
                    f"overwrite rejected: doc={doc_id!r} 已有进行中 pending 版本"
                    "（同一时刻只有一个 pending——P0-2.3/T7）"
                )
            if audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
            return pending_version
        except BaseException:
            self._rollback()
            raise

    def _max_document_version_locked(self, conn, doc_id: str) -> int:
        row = conn.execute(
            "SELECT MAX(m) FROM ("
            "  SELECT active_version AS m FROM documents WHERE id = %(doc)s"
            "  UNION ALL SELECT pending_version FROM documents WHERE id = %(doc)s"
            "  UNION ALL SELECT MAX(version) FROM chunks WHERE doc_id = %(doc)s)"
            " AS v(m)",
            {"doc": doc_id},
        ).fetchone()
        return row[0] or 0

    def set_doc_pending_failed(self, doc_id: str, version: int, error: str) -> None:
        """pending 版本失败：failed + pending_error + 立即物理删块——同一事务。

        P1-1 守卫（M2.1 R2，与 sqlite 同构）：UPDATE 零行（版本已被切换收编/
        清空/取代——调用方事务外 stale read）时不删块直接提交返回，防取消×切换
        竞态删掉在用版本全部 chunks。
        """
        conn = self._conn
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "UPDATE documents SET pending_status = 'failed', pending_error = %(err)s,"
                " updated_at = CURRENT_TIMESTAMP"
                " WHERE id = %(doc)s AND pending_version = %(v)s",
                {"err": error, "doc": doc_id, "v": version},
            )
            if cur.rowcount == 0:
                conn.execute("COMMIT")
                return
            conn.execute(
                "DELETE FROM chunks WHERE doc_id = %(doc)s AND version = %(v)s",
                {"doc": doc_id, "v": version},
            )
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except psycopg.Error:
                pass
            raise

    def delete_document(
        self, doc_id: str, audit: tuple[str, str] | None = None
    ) -> None:
        """删除文档（同事务：任务取消 → 级联删 → outbox 治理事件——M2.4 收口）。"""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            conn.execute(
                "UPDATE tasks SET status = 'failed',"
                " error = 'cancelled: document deleted', updated_at = CURRENT_TIMESTAMP"
                " WHERE doc_id = %(doc)s AND status IN ('pending', 'leased', 'running')",
                {"doc": doc_id},
            )
            conn.execute("DELETE FROM documents WHERE id = %(doc)s", {"doc": doc_id})
            # M2-S3：sem_chunk_entities 随删清挂此事务位（untag——语义轨道段补齐）
            if audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def get_document_dims(self, doc_id: str) -> dict[str, list[str]]:
        rows = self._conn.execute(
            "SELECT dim.key, v.value FROM document_dimensions dd"
            " JOIN dimensions dim ON dim.id = dd.dimension_id"
            " JOIN dimension_values v ON v.id = dd.value_id"
            " WHERE dd.doc_id = %(doc)s ORDER BY dim.key, v.value",
            {"doc": doc_id},
        ).fetchall()
        dims: dict[str, list[str]] = {}
        for key, value in rows:
            dims.setdefault(key, []).append(value)
        return dims

    def set_document_dims(
        self, doc_id: str, dims: dict[str, list[str]],
        audit: tuple[str, str] | None = None,
    ) -> None:
        """按 key 全量替换文档维度行（PATCH 落点——与 sqlite 同构；audit 同事务）。"""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            for dim_key, values in dims.items():
                conn.execute(
                    "DELETE FROM document_dimensions WHERE doc_id = %(doc)s"
                    "   AND dimension_id IN (SELECT id FROM dimensions"
                    "       WHERE org_id = (SELECT org_id FROM documents WHERE id = %(doc)s)"
                    "         AND key = %(key)s)",
                    {"doc": doc_id, "key": dim_key},
                )
                for value in values:
                    cur = conn.execute(
                        "INSERT INTO document_dimensions(doc_id, dimension_id, value_id)"
                        " SELECT %(doc)s, dim.id, v.id FROM dimensions dim"
                        " JOIN dimension_values v ON v.dimension_id = dim.id"
                        "   AND v.value = %(value)s"
                        " WHERE dim.org_id = (SELECT org_id FROM documents WHERE id = %(doc)s)"
                        "   AND dim.key = %(key)s",
                        {"doc": doc_id, "key": dim_key, "value": value},
                    )
                    if cur.rowcount != 1:
                        raise RuntimeError(
                            f"document dims resolution failed: ({dim_key!r}, {value!r})"
                            "（维度/取值不存在？）——事务回滚"
                        )
            if audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def get_chunk(self, chunk_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT rid, id, doc_id, seq, version, tombstone FROM chunks WHERE id = %(id)s",
            {"id": chunk_id},
        ).fetchone()
        if row is None:
            return None
        return dict(zip(("rid", "id", "doc_id", "seq", "version", "tombstone"), row))

    def fetch_window(self, doc_id: str, version: int, seq_lo: int, seq_hi: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, seq, content, page_no FROM chunks"
            " WHERE doc_id = %(doc)s AND version = %(v)s AND tombstone = 0"
            "   AND seq BETWEEN %(lo)s AND %(hi)s ORDER BY seq",
            {"doc": doc_id, "v": version, "lo": seq_lo, "hi": seq_hi},
        ).fetchall()
        return [
            {"chunk_id": r[0], "seq": r[1], "content": r[2], "page_no": r[3]} for r in rows
        ]

    def visible_doc_ids(self, plan: AclPlan, doc_ids: list[str]) -> set[str]:
        """文档级可见集（visible_docs CTE MATERIALIZED——与 sqlite 同构）。"""
        from knowledge_lattice.store.postgres.acl_render import render_visible_doc_ids

        sql, params = render_visible_doc_ids(plan)
        visible = {r[0] for r in self._conn.execute(sql, params)}
        return visible & set(doc_ids)

    def visible_documents(
        self,
        plan: AclPlan,
        *,
        dataset_ids: list[str] | None = None,
        active_status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """按调用者权限的文档清单（M1-5 MCP list_documents 数据源——与 sqlite
        同构；dims 经 _attach_dims 聚合回填）。"""
        from knowledge_lattice.store.postgres.acl_render import render_documents_select

        sql, params = render_documents_select(
            plan, dataset_ids=dataset_ids, active_status=active_status, limit=limit
        )
        cursor = self._conn.execute(sql, params)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        self._attach_dims(rows)
        return rows

    def visible_dataset_counts(
        self, plan: AclPlan, *, dataset_ids: list[str] | None = None
    ) -> list[dict]:
        """datasets 统计（§6.1：doc_count 按调用者权限计算——与 sqlite 同构）。"""
        from knowledge_lattice.store.postgres.acl_render import render_dataset_counts_select

        sql, params = render_dataset_counts_select(plan, dataset_ids=dataset_ids)
        return [
            {"id": r[0], "name": r[1], "doc_count": r[2]}
            for r in self._conn.execute(sql, params)
        ]

    # ============ Quality 域（design §5.4 / FR-3——M1-4，与 SqliteBackend 同构） ============

    _ACTIVE_CHUNK_JOIN = (
        " FROM chunks c JOIN documents d ON d.id = c.doc_id"
        " WHERE d.org_id = %(org)s AND c.tombstone = 0"
        "   AND c.version = d.active_version AND d.active_version > 0"
    )

    def neighbor_sims(
        self, rid: int, embed_model: str, *, top_k: int = 8
    ) -> list[dict]:
        """SQL 精确扫描 top-k 近邻（`<=>` 余弦距离升序——G-6 起步口径）。"""
        row = self._conn.execute(
            "SELECT d.org_id, cv1.embedding::text FROM chunks c1"
            " JOIN documents d ON d.id = c1.doc_id"
            " JOIN chunk_vectors cv1 ON cv1.rid = c1.rid AND cv1.embed_model = %(label)s"
            " WHERE c1.rid = %(rid)s",
            {"rid": rid, "label": embed_model},
        ).fetchone()
        if row is None:
            return []
        qv_text = row[1]
        sql = (
            "SELECT c2.rid, c2.id, c2.doc_id,"
            " 1 - (cv2.embedding <=> %(qv)s::vector) AS sim"
            " FROM chunks c2"
            " JOIN documents d2 ON d2.id = c2.doc_id"
            " JOIN chunk_vectors cv2 ON cv2.rid = c2.rid AND cv2.embed_model = %(label)s"
            " WHERE d2.org_id = %(org)s AND c2.tombstone = 0"
            "   AND c2.version = d2.active_version AND c2.rid != %(rid)s"
            " ORDER BY cv2.embedding <=> %(qv)s::vector ASC"
            " LIMIT %(k)s"
        )
        rows = self._conn.execute(
            sql,
            {"org": row[0], "rid": rid, "label": embed_model, "qv": qv_text, "k": top_k},
        ).fetchall()
        return [
            {"rid": r[0], "chunk_id": r[1], "doc_id": r[2], "sim": r[3]} for r in rows
        ]

    def org_active_chunk_count(self, org_id: str | None) -> int:
        """组织内在用块数；org_id=None 为全局语料（冷启动 IDF 兜底口径）。"""
        if org_id is None:
            return self._conn.execute(
                "SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.doc_id"
                " WHERE c.tombstone = 0 AND c.version = d.active_version"
                "   AND d.active_version > 0"
            ).fetchone()[0]
        return self._conn.execute(
            "SELECT count(*)" + self._ACTIVE_CHUNK_JOIN, {"org": org_id}
        ).fetchone()[0]

    def token_doc_frequency(
        self, tokens: Sequence[str], org_id: str | None
    ) -> dict[str, int]:
        """df：' '||content_seg||' ' 含 ' '+token+' '（strpos 边界精确）。"""
        if org_id is not None:
            scope = (
                self._ACTIVE_CHUNK_JOIN
                + " AND strpos(' ' || c.content_seg || ' ', ' ' || %(tok)s || ' ') > 0"
            )
        else:
            scope = (
                " FROM chunks c JOIN documents d ON d.id = c.doc_id"
                " WHERE c.tombstone = 0 AND c.version = d.active_version"
                "   AND d.active_version > 0"
                "   AND strpos(' ' || c.content_seg || ' ', ' ' || %(tok)s || ' ') > 0"
            )
        out: dict[str, int] = {}
        for tok in dict.fromkeys(tokens):
            params: dict[str, object] = {"tok": tok}
            if org_id is not None:
                params["org"] = org_id
            out[tok] = self._conn.execute(
                "SELECT count(*)" + scope, params
            ).fetchone()[0]
        return out

    def org_active_chunk_vectors(
        self, org_id: str, embed_model: str
    ) -> Iterator[tuple[int, bytes]]:
        """组织内全部在用块的 (rid, packed float32 bytes)——**服务端游标惰性流**
        （M1-4 P2-4 / M1-5 改造：named cursor itersize 分批取行、不物化全量
        （普通游标 libpq 一次收全量行——100k×2560 文本 ~5GB 客户端内存）；
        文本 → parse_vector_bytes 直转 packed bytes。named cursor 须在事务内
        DECLARE——conn.transaction() 包裹（autocommit 下显式开合，流式期间
        连接单线程独占、无 interleaving）。"""
        from knowledge_lattice.store.postgres.vec import parse_vector_bytes

        sql = (
            "SELECT c.rid, cv.embedding::text FROM chunks c"
            " JOIN documents d ON d.id = c.doc_id"
            " JOIN chunk_vectors cv ON cv.rid = c.rid AND cv.embed_model = %(label)s"
            " WHERE d.org_id = %(org)s AND c.tombstone = 0"
            "   AND c.version = d.active_version AND d.active_version > 0"
        )
        params = {"org": org_id, "label": embed_model}

        def _stream() -> Iterator[tuple[int, bytes]]:
            with self._conn.transaction():
                with self._conn.cursor(name="lattice_quality_vec_stream") as cur:
                    cur.itersize = 512
                    cur.execute(sql, params)
                    for rid, text in cur:
                        yield rid, parse_vector_bytes(text)

        return _stream()

    def org_active_chunk_segs(self, org_id: str | None) -> list[str]:
        """org_id=None = 全局语料（冷启动重算兜底——P2-1，与 sqlite 同构）。"""
        if org_id is None:
            rows = self._conn.execute(
                "SELECT c.content_seg FROM chunks c"
                " JOIN documents d ON d.id = c.doc_id"
                " WHERE c.tombstone = 0 AND c.version = d.active_version"
                "   AND d.active_version > 0"
            ).fetchall()
            return [r[0] or "" for r in rows]
        rows = self._conn.execute(
            "SELECT c.content_seg" + self._ACTIVE_CHUNK_JOIN, {"org": org_id}
        ).fetchall()
        return [r[0] or "" for r in rows]

    def chunks_for_quality_recompute(
        self,
        org_id: str,
        *,
        current_scale: int,
        rescale_ratio: float,
        sample_percent: int,
    ) -> list[dict]:
        """候选选择与 sqlite 同构（Knuth 散列抽样；`%%`——psycopg 参数态字面转义）。"""
        floor = int(current_scale * rescale_ratio)
        sql = (
            "SELECT c.rid, c.id, c.doc_id, c.content, c.content_seg, c.detected_at_scale"
            + self._ACTIVE_CHUNK_JOIN
            + "   AND (c.detected_at_scale IS NULL OR c.detected_at_scale < %(floor)s"
            + f"        OR (c.rid * 2654435761) %% 100 < {int(sample_percent)})"
            " ORDER BY c.rid"
        )
        rows = self._conn.execute(sql, {"org": org_id, "floor": floor}).fetchall()
        return [
            {
                "rid": r[0], "chunk_id": r[1], "doc_id": r[2], "content": r[3],
                "content_seg": r[4], "detected_at_scale": r[5],
            }
            for r in rows
        ]

    def set_chunk_quality_marks(
        self, marks: Sequence[tuple[int, str | None]], *, scale: int
    ) -> None:
        """批量回写检测标记（marks=[(rid, content_sha)]——sha None 保留原值）。"""
        if not marks:
            return
        conn = self._conn
        conn.execute("BEGIN")
        try:
            for rid, sha in marks:
                conn.execute(
                    "UPDATE chunks SET detected_at_scale = %(scale)s,"
                    " content_sha = COALESCE(%(sha)s, content_sha) WHERE rid = %(rid)s",
                    {"scale": scale, "sha": sha, "rid": rid},
                )
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except psycopg.Error:
                pass
            raise

    def set_chunk_llm_keywords(self, rid: int, llm_keywords: str) -> None:
        self._conn.execute(
            "UPDATE chunks SET llm_keywords = %(kw)s WHERE rid = %(rid)s",
            {"kw": llm_keywords, "rid": rid},
        )

    def append_chunk_manual_terms(
        self, rid: int, *, keywords: str, tags: str
    ) -> dict:
        row = self._conn.execute(
            "SELECT keywords, tags FROM chunks WHERE rid = %(rid)s", {"rid": rid}
        ).fetchone()
        if row is None:
            raise KeyError(f"chunk rid not found: {rid}")
        new_kw = (row[0] + " " + keywords).strip() if row[0] else keywords
        new_tags = (row[1] + " " + tags).strip() if row[1] else tags
        self._conn.execute(
            "UPDATE chunks SET keywords = %(kw)s, tags = %(tg)s WHERE rid = %(rid)s",
            {"kw": new_kw, "tg": new_tags, "rid": rid},
        )
        return {"keywords": new_kw, "tags": new_tags}

    _QFLAG_COLS = (
        "id, chunk_id, doc_id, reason, detail_json, auto_keywords, manual_tags,"
        " state, created_at, resolved_at"
    )

    def insert_quality_flag(
        self, *, chunk_id: str, doc_id: str, reason: str, detail_json: str
    ) -> str:
        flag_id = f"qfl_{uuid.uuid4()}"
        conn = self._conn
        conn.execute("BEGIN")
        try:
            conn.execute(
                "DELETE FROM quality_flags WHERE chunk_id = %(chk)s AND state = 'open'",
                {"chk": chunk_id},
            )
            conn.execute(
                "INSERT INTO quality_flags(id, chunk_id, doc_id, reason, detail_json)"
                " VALUES(%(id)s, %(chk)s, %(doc)s, %(reason)s, %(detail)s)",
                {
                    "id": flag_id, "chk": chunk_id, "doc": doc_id,
                    "reason": reason, "detail": detail_json,
                },
            )
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except psycopg.Error:
                pass
            raise
        return flag_id

    def delete_open_flags(self, rids: Sequence[int], reasons: Sequence[str]) -> int:
        """给定块的 open flags 删除（reason 限定）——**rid 分批**（M1-4 P2-4 /
        M1-5：PG 单语句绑定参数上限 65535，~6.5 万候选超限失败；每批
        ≤_DELETE_FLAG_BATCH 行参数化删除，计数累加）。"""
        if not rids or not reasons:
            return 0
        deleted = 0
        for start in range(0, len(rids), self._DELETE_FLAG_BATCH):
            batch = rids[start : start + self._DELETE_FLAG_BATCH]
            rmarks = ", ".join(f"%(r{start + i})s" for i in range(len(batch)))
            vmarks = ", ".join(f"%(v{i})s" for i in range(len(reasons)))
            params: dict[str, object] = {
                f"r{start + i}": rid for i, rid in enumerate(batch)
            }
            params.update({f"v{i}": reason for i, reason in enumerate(reasons)})
            cur = self._conn.execute(
                f"DELETE FROM quality_flags WHERE state = 'open'"
                f" AND reason IN ({vmarks})"
                f" AND chunk_id IN (SELECT id FROM chunks WHERE rid IN ({rmarks}))",
                params,
            )
            deleted += cur.rowcount
        return deleted

    def get_quality_flag(self, flag_id: str) -> dict | None:
        row = self._conn.execute(
            f"SELECT {self._QFLAG_COLS} FROM quality_flags WHERE id = %(id)s",
            {"id": flag_id},
        ).fetchone()
        return None if row is None else dict(zip(self._QFLAG_COLS.split(", "), row))

    def list_quality_flags(
        self, doc_id: str | None = None, *, org_id: str | None = None,
        state: str | None = None,
    ) -> list[dict]:
        sql = f"SELECT {self._QFLAG_COLS} FROM quality_flags"
        conds: list[str] = []
        params: dict[str, object] = {}
        if doc_id is not None:
            conds.append("doc_id = %(doc)s")
            params["doc"] = doc_id
        if org_id is not None:
            conds.append("doc_id IN (SELECT id FROM documents WHERE org_id = %(org)s)")
            params["org"] = org_id
        if state is not None:
            conds.append("state = %(state)s")
            params["state"] = state
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY created_at, id"
        rows = self._conn.execute(sql, params).fetchall()
        cols = self._QFLAG_COLS.split(", ")
        return [dict(zip(cols, r)) for r in rows]

    def set_quality_auto_keywords(self, flag_id: str, auto_keywords: str) -> None:
        """LLM 兜底一句定位语写 auto_keywords（与 sqlite 同构）。"""
        self._conn.execute(
            "UPDATE quality_flags SET auto_keywords = %(ak)s WHERE id = %(id)s",
            {"ak": auto_keywords, "id": flag_id},
        )

    def set_quality_flag_state(self, flag_id: str, state: str) -> bool:
        resolved_at = "CURRENT_TIMESTAMP" if state in ("resolved", "ignored") else "NULL"
        cur = self._conn.execute(
            f"UPDATE quality_flags SET state = %(s)s, resolved_at = {resolved_at}"
            " WHERE id = %(id)s",
            {"s": state, "id": flag_id},
        )
        return cur.rowcount > 0

    def append_quality_manual_tags(self, flag_id: str, manual_json: str) -> None:
        row = self._conn.execute(
            "SELECT manual_tags FROM quality_flags WHERE id = %(id)s", {"id": flag_id}
        ).fetchone()
        if row is None:
            raise KeyError(f"quality flag not found: {flag_id}")
        lines = [x for x in ((row[0] or "").splitlines() + [manual_json]) if x]
        self._conn.execute(
            "UPDATE quality_flags SET manual_tags = %(m)s WHERE id = %(id)s",
            {"m": "\n".join(lines), "id": flag_id},
        )

    def chunks_by_rids(self, rids: Sequence[int]) -> list[dict]:
        if not rids:
            return []
        marks = ", ".join(f"%(r{i})s" for i in range(len(rids)))
        params = {f"r{i}": rid for i, rid in enumerate(rids)}
        rows = self._conn.execute(
            f"SELECT rid, id, doc_id, content, content_seg FROM chunks"
            f" WHERE rid IN ({marks})",
            params,
        ).fetchall()
        return [
            {"rid": r[0], "chunk_id": r[1], "doc_id": r[2], "content": r[3],
             "content_seg": r[4]}
            for r in rows
        ]

    # ============ Admin 域（任务状态机 / 文档状态 / 指纹 / 只读维度取值） ============

    def create_task(
        self, doc_id: str | None, *, task_type: str = "ingest",
        target_version: int | None = None, task_id: str | None = None,
        payload: str | None = None,
        audit: tuple[str, str] | None = None,
    ) -> str:
        """target_version（0005/M2.1 R2 边界裁定 B(a)）：ingest 任务的目标文档
        版本——取消与崩溃耗尽清扫按该版本落 pending failed（P2-3）；NULL=无版本
        任务。task_id：预生成 id 显式携带（治理 outbox 事件同源关联——M2.4）。
        payload（0006/M2-S1）：任务参数 JSON（semantic_sync {org, adapter}）。
        audit（m2s-2，G-16 收口）：(event_type, payload_json) 与任务行同一事务
        （BEGIN…COMMIT——与 sqlite 同语义）。"""
        task_id = task_id or f"tsk_{uuid.uuid4()}"
        if audit is not None:
            conn = self._conn
            conn.execute("BEGIN")
            try:
                conn.execute(
                    "INSERT INTO tasks(id, doc_id, type, status, target_version,"
                    " payload) VALUES(%(id)s, %(doc)s, %(type)s, 'pending',"
                    " %(tv)s, %(payload)s)",
                    {"id": task_id, "doc": doc_id, "type": task_type,
                     "tv": target_version, "payload": payload},
                )
                conn.execute(
                    "INSERT INTO audit_outbox(id, event_type, payload_json)"
                    " VALUES(%(id)s, %(t)s, %(p)s)",
                    {"id": f"aud_{uuid.uuid4()}", "t": audit[0], "p": audit[1]},
                )
                conn.execute("COMMIT")
            except BaseException:
                self._rollback()
                raise
            return task_id
        self._conn.execute(
            "INSERT INTO tasks(id, doc_id, type, status, target_version, payload)"
            " VALUES(%(id)s, %(doc)s, %(type)s, 'pending', %(tv)s, %(payload)s)",
            {"id": task_id, "doc": doc_id, "type": task_type, "tv": target_version,
             "payload": payload},
        )
        return task_id

    def get_task(self, task_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, doc_id, type, status, attempts, error, target_version,"
            " lease_owner, lease_until, heartbeat_at, created_at, updated_at, payload"
            " FROM tasks WHERE id = %(id)s",
            {"id": task_id},
        ).fetchone()
        if row is None:
            return None
        cols = (
            "id", "doc_id", "type", "status", "attempts", "error", "target_version",
            "lease_owner", "lease_until", "heartbeat_at", "created_at", "updated_at",
            "payload",
        )
        return dict(zip(cols, row))

    def list_tasks(self, org_id: str, *, doc_id: str | None = None) -> list[dict]:
        sql = (
            "SELECT t.id, t.doc_id, t.type, t.status, t.attempts, t.error,"
            " t.target_version, t.lease_owner, t.lease_until, t.heartbeat_at,"
            " t.created_at, t.updated_at FROM tasks t"
            " JOIN documents d ON d.id = t.doc_id"
            " WHERE d.org_id = %(org)s"
        )
        params: dict[str, object] = {"org": org_id}
        if doc_id is not None:
            sql += " AND t.doc_id = %(doc)s"
            params["doc"] = doc_id
        # 次级排序键 id——created_at 并列下的确定性 tiebreak（id 为 ULID
        # 随机非单调、**不保证时间序**——只消除结果不确定性；并列内「最近」
        # 歧义本身登记 m2-6（任务 id 加序号列或单调源））
        sql += " ORDER BY t.created_at DESC, t.id DESC"
        rows = self._conn.execute(sql, params).fetchall()
        cols = (
            "id", "doc_id", "type", "status", "attempts", "error", "target_version",
            "lease_owner", "lease_until", "heartbeat_at", "created_at", "updated_at",
        )
        return [dict(zip(cols, r)) for r in rows]

    def update_task(
        self, task_id: str, *, status: str | None = None, error: str | None = None
    ) -> None:
        """状态机推进：pending→leased→running→done|failed（§5.3）。

        attempts 随 claim_next_task 认领递增（M2.1 口径——认领后即崩也计数）。
        P2-1 守卫（M2.1 R2）：done 仅非终态可入——已终态零行生效（sqlite 同构）。
        """
        if status == "running":
            # P2-3/R2：running 写入限非终态（取消不复活——sqlite 同构）
            self._conn.execute(
                "UPDATE tasks SET status = %(s)s,"
                " heartbeat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP"
                " WHERE id = %(id)s AND status IN ('pending','leased','running')",
                {"s": status, "id": task_id},
            )
        elif status == "done":
            self._conn.execute(
                "UPDATE tasks SET status = 'done', error = NULL,"
                " updated_at = CURRENT_TIMESTAMP"
                " WHERE id = %(id)s AND status IN ('pending','leased','running')",
                {"id": task_id},
            )
        elif error is not None or status is not None:
            # P3-R4-1：failed 写入不覆盖取消终态（µs 窗口守卫——sqlite 同构）
            self._conn.execute(
                "UPDATE tasks SET status = COALESCE(%(s)s, status), error = %(err)s,"
                " updated_at = CURRENT_TIMESTAMP WHERE id = %(id)s"
                "   AND NOT (status = 'failed' AND error LIKE %(pattern)s)",
                {"s": status, "err": error, "id": task_id,
                 "pattern": "cancelled:%"},
            )

    # ---- 任务队列（租约·心跳·认领——M2.1 worker 框架，design §5.3） ----

    def fail_exhausted_tasks(
        self, *, max_attempts: int, now: str | None = None
    ) -> list[dict]:
        """崩溃耗尽清扫（P2-2，M2.1 R2——与 sqlite 同构）：过期且 attempts ≥ max
        的 leased/running → failed + error 原因；返回被清扫行供文档侧收尾。"""
        from knowledge_lattice.store.taskclock import utc_now_ts

        now_ts = now or utc_now_ts()
        # P3-N7 节流（与 sqlite 同构）：常态零行时先读后写——不进 UPDATE 事务
        probe = self._conn.execute(
            "SELECT 1 FROM tasks WHERE status IN ('leased','running')"
            "   AND attempts >= %(max)s"
            "   AND lease_until IS NOT NULL AND lease_until <= %(now)s LIMIT 1",
            {"max": max_attempts, "now": now_ts},
        ).fetchone()
        if probe is None:
            return []
        rows = self._conn.execute(
            "UPDATE tasks SET status = 'failed', lease_owner = NULL, lease_until = NULL,"
            " error = 'attempt limit exceeded (lease expired after ' || attempts"
            "   || ' attempts — worker crash?)', updated_at = %(now)s"
            " WHERE status IN ('leased','running') AND attempts >= %(max)s"
            "   AND lease_until IS NOT NULL AND lease_until <= %(now)s"
            " RETURNING id, doc_id, type, status, attempts, error, target_version",
            {"max": max_attempts, "now": now_ts},
        ).fetchall()
        cols = ("id", "doc_id", "type", "status", "attempts", "error", "target_version")
        return [dict(zip(cols, r)) for r in rows]

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
        """原子认领（FOR UPDATE SKIP LOCKED——两执行器并发认领同一候选行时不
        互等不重叠，恰好一人得手；与 sqlite 单语句 UPDATE 子查询重估同语义）。
        created_before（P2-7）：仅认领 created_at <= 该时点的任务（陈旧任务口径，
        sqlite 同构——见 sqlite 侧 docstring）。"""
        from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

        now_ts = now or utc_now_ts()
        until = add_seconds(now_ts, lease_s)
        age_filter = " AND created_at <= %(cb)s" if created_before is not None else ""
        params: dict[str, object] = {
            "w": worker_id, "now": now_ts, "until": until, "max": max_attempts,
            "types": list(task_types),
        }
        if created_before is not None:
            params["cb"] = created_before
        rows = self._conn.execute(
            "WITH candidate AS ("
            "  SELECT id FROM tasks"
            "  WHERE type = ANY(%(types)s) AND attempts < %(max)s" + age_filter +
            "    AND (status = 'pending'"
            "         OR (status IN ('leased','running')"
            "             AND lease_until IS NOT NULL AND lease_until <= %(now)s))"
            "  ORDER BY created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED)"
            " UPDATE tasks t SET status = 'leased', attempts = attempts + 1,"
            " lease_owner = %(w)s,"
            " lease_until = %(until)s, heartbeat_at = %(now)s, updated_at = %(now)s"
            " FROM candidate c WHERE t.id = c.id"
            " RETURNING t.id, t.doc_id, t.type, t.status, t.attempts, t.error,"
            " t.target_version, t.lease_owner, t.lease_until, t.heartbeat_at,"
            " t.created_at, t.updated_at",
            params,
        ).fetchall()
        if not rows:
            return None
        cols = (
            "id", "doc_id", "type", "status", "attempts", "error", "target_version",
            "lease_owner", "lease_until", "heartbeat_at", "created_at", "updated_at",
        )
        return dict(zip(cols, rows[0]))

    def heartbeat_task(
        self, task_id: str, worker_id: str, *, lease_s: float, now: str | None = None
    ) -> bool:
        from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

        now_ts = now or utc_now_ts()
        cur = self._conn.execute(
            "UPDATE tasks SET heartbeat_at = %(now)s, lease_until = %(until)s,"
            " updated_at = %(now)s"
            " WHERE id = %(id)s AND lease_owner = %(w)s"
            "   AND status IN ('leased','running')",
            {"now": now_ts, "until": add_seconds(now_ts, lease_s), "id": task_id, "w": worker_id},
        )
        return cur.rowcount == 1

    def cancel_task(
        self, task_id: str, *, reason: str, now: str | None = None,
        audit: tuple[str, str] | None = None,
    ) -> dict | None:
        from knowledge_lattice.store.taskclock import utc_now_ts

        now_ts = now or utc_now_ts()
        conn = self._conn
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "UPDATE tasks SET status = 'failed', error = %(reason)s, lease_owner = NULL,"
                " lease_until = NULL, updated_at = %(now)s"
                " WHERE id = %(id)s AND status IN ('pending','leased','running')",
                {"reason": reason, "now": now_ts, "id": task_id},
            )
            cancelled = cur.rowcount > 0
            if cancelled and audit is not None:
                self._outbox_insert(conn, *audit)  # 取消生效才记（TC-OPS-01）
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        if not cancelled:
            return None  # 已终态（幂等不复活——TC-TASK-03）
        return self.get_task(task_id)

    def delete_expired_memberships(self, *, now: str | None = None) -> int:
        from knowledge_lattice.store.taskclock import utc_now_ts

        cur = self._conn.execute(
            "DELETE FROM user_org_memberships"
            " WHERE expires_at IS NOT NULL AND expires_at <= %(now)s",
            {"now": now or utc_now_ts()},
        )
        return cur.rowcount  # trg_membership_delete_cleanup 等价触发器级联清授权

    def delete_aged_tombstones(self, *, before_ts: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM chunks WHERE tombstone = 1 AND tombstoned_at IS NOT NULL"
            " AND tombstoned_at <= %(before)s",
            {"before": before_ts},
        )
        return cur.rowcount  # chunk_vectors FK CASCADE；FTS 列 GENERATED 随行消失

    def trim_finished_tasks(
        self, *, keep_days: int, keep_count: int, task_type: str = "maintenance",
        now: str | None = None,
    ) -> int:
        from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

        now_ts = now or utc_now_ts()
        cutoff = add_seconds(now_ts, -keep_days * 86400)
        terminal = "type = %(ty)s AND status IN ('done','failed')"
        cur = self._conn.execute(
            f"DELETE FROM tasks WHERE {terminal} AND updated_at < %(cutoff)s",
            {"ty": task_type, "cutoff": cutoff},
        )
        removed = cur.rowcount
        cur = self._conn.execute(
            f"DELETE FROM tasks WHERE {terminal} AND id NOT IN ("
            f"  SELECT id FROM tasks WHERE {terminal}"
            f"  ORDER BY updated_at DESC LIMIT %(keep)s)",
            {"ty": task_type, "keep": max(keep_count, 0)},
        )
        removed += cur.rowcount
        return removed

    def get_document(self, doc_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, dataset_id, title, source_uri, content_hash, mime_type,"
            " page_count, parser, active_version, active_status, active_error,"
            " pending_version, pending_status, pending_error, pending_dims_json,"
            " owner_user_id, raw_object_key, created_at, updated_at"
            " FROM documents WHERE id = %(id)s",
            {"id": doc_id},
        ).fetchone()
        if row is None:
            return None
        cols = (
            "id", "org_id", "dataset_id", "title", "source_uri", "content_hash", "mime_type",
            "page_count", "parser", "active_version", "active_status", "active_error",
            "pending_version", "pending_status", "pending_error", "pending_dims_json",
            "owner_user_id", "raw_object_key", "created_at", "updated_at",
        )
        return dict(zip(cols, row))

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
        """首次上传的文档行（audit 同事务——M2.4 m2-2，sqlite 同构）。"""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            conn.execute(
                "INSERT INTO documents(id, org_id, dataset_id, title, source_uri, content_hash,"
                " mime_type, parser, active_version, pending_version, pending_status,"
                " pending_dims_json, owner_user_id, raw_object_key)"
                " VALUES(%(id)s, %(org)s, %(ds)s, %(title)s, %(src)s, %(hash)s, %(mime)s,"
                " %(parser)s, 0, 1, 'parsing', %(dims)s, %(owner)s, %(obj)s)",
                {
                    "id": doc_id, "org": org_id, "ds": dataset_id, "title": title,
                    "src": source_uri, "hash": content_hash, "mime": mime_type,
                    "parser": parser, "dims": pending_dims_json,
                    "owner": owner_user_id, "obj": raw_object_key,
                },
            )
            if audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def set_doc_pending_status(self, doc_id: str, version: int, status: str) -> None:
        # M2.1 并发面收口：failed 是 pending 版本的吸收态（P0-2.3 版本亡故）——
        # 取消/失败先行落账后，在途执行器的状态推进零行生效（防复活，sqlite 同构）
        self._conn.execute(
            "UPDATE documents SET pending_status = %(s)s, updated_at = CURRENT_TIMESTAMP"
            " WHERE id = %(doc)s AND pending_version = %(v)s"
            "   AND (pending_status IS NULL OR pending_status != 'failed')",
            {"s": status, "doc": doc_id, "v": version},
        )

    def set_doc_active_status(self, doc_id: str, version: int, status: str) -> None:
        """推进在用版本状态（embed 完成 → searchable_full）；成功态顺带清 active_error。"""
        self._conn.execute(
            "UPDATE documents SET active_status = %(s)s, active_error = NULL,"
            " updated_at = CURRENT_TIMESTAMP"
            " WHERE id = %(doc)s AND active_version = %(v)s",
            {"s": status, "doc": doc_id, "v": version},
        )

    def set_doc_active_error(self, doc_id: str, version: int, error: str) -> None:
        self._conn.execute(
            "UPDATE documents SET active_error = %(err)s, updated_at = CURRENT_TIMESTAMP"
            " WHERE id = %(doc)s AND active_version = %(v)s",
            {"err": error, "doc": doc_id, "v": version},
        )

    def read_fingerprint(self, embed_model: str) -> str | None:
        row = self._conn.execute(
            "SELECT baseline FROM embedding_fingerprints WHERE embed_model = %(m)s",
            {"m": embed_model},
        ).fetchone()
        return None if row is None else row[0]

    def save_fingerprint(self, embed_model: str, baseline_json: str) -> None:
        self._conn.execute(
            "INSERT INTO embedding_fingerprints(embed_model, baseline) VALUES(%(m)s, %(b)s)"
            " ON CONFLICT(embed_model) DO UPDATE SET baseline = %(b)s,"
            " updated_at = CURRENT_TIMESTAMP",
            {"m": embed_model, "b": baseline_json},
        )

    def list_dimensions(self, org_id: str) -> list[dict]:
        dims = self._conn.execute(
            "SELECT id, key, name, required, enabled FROM dimensions"
            " WHERE org_id = %(org)s AND status = 'active' ORDER BY key",
            {"org": org_id},
        ).fetchall()
        out: list[dict] = []
        for dim_id, key, name, required, enabled in dims:
            values = self._conn.execute(
                "SELECT id, value, label FROM dimension_values"
                " WHERE dimension_id = %(d)s AND status = 'active'"
                " ORDER BY sort_order, value",
                {"d": dim_id},
            ).fetchall()
            out.append(
                {
                    "id": dim_id,
                    "key": key,
                    "name": name,
                    "required": bool(required),
                    "enabled": bool(enabled),
                    "values": [{"id": i, "value": v, "label": l} for i, v, l in values],
                }
            )
        return out

    def list_datasets(self, org_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, description FROM datasets WHERE org_id = %(org)s ORDER BY id",
            {"org": org_id},
        ).fetchall()
        return [{"id": r[0], "name": r[1], "description": r[2]} for r in rows]

    def find_user_by_token_hash(self, token_hash: str) -> dict | None:
        """静态 token 查 user（sha256 形态直查——D18 仅 dev/test）。"""
        row = self._conn.execute(
            "SELECT id, is_system_admin FROM users WHERE token_hash = %(h)s", {"h": token_hash}
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "is_system_admin": bool(row[1])}

    def get_user_auth(self, user_id: str) -> dict | None:
        """认证侧用户态（是否存在 / 是否禁用 / 是否系统管理员）。"""
        row = self._conn.execute(
            "SELECT is_system_admin, disabled_at FROM users WHERE id = %(id)s", {"id": user_id}
        ).fetchone()
        if row is None:
            return None
        return {"is_system_admin": bool(row[0]), "disabled_at": row[1]}

    # ============ 上传凭证（M1-3 三步式——与 sqlite 实现同构，仅参数标记方言差异） ============

    _UPLOAD_COLS = (
        "id", "org_id", "user_id", "service_id", "filename", "size", "sha256",
        "content_type", "status", "object_key", "doc_id", "task_id",
        "expires_at", "created_at", "updated_at",
    )

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
        conn = self._conn
        conn.execute("BEGIN")
        try:
            conn.execute(
                "INSERT INTO uploads(id, org_id, user_id, service_id, filename, size,"
                " sha256, content_type, status, expires_at)"
                " VALUES(%(id)s, %(org)s, %(uid)s, %(svc)s, %(fn)s, %(size)s, %(sha)s,"
                " %(ct)s, 'issued', %(exp)s)",
                {
                    "id": upload_id, "org": org_id, "uid": user_id, "svc": service_id,
                    "fn": filename, "size": size, "sha": sha256, "ct": content_type,
                    "exp": expires_at,
                },
            )
            if audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def get_upload_credential(self, upload_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, user_id, service_id, filename, size, sha256, content_type,"
            " status, object_key, doc_id, task_id, expires_at, created_at, updated_at"
            " FROM uploads WHERE id = %(id)s",
            {"id": upload_id},
        ).fetchone()
        if row is None:
            return None
        row = list(row)
        # 时间列归一化：psycopg 解析 TIMESTAMP 为 datetime——统一为 sqlite 同款
        # UTC `YYYY-MM-DD HH:MM:SS` 字符串（连接工厂 SET TIME ZONE 'UTC'，无漂移）
        for idx in (12, 13, 14):
            if row[idx] is not None:
                row[idx] = row[idx].strftime("%Y-%m-%d %H:%M:%S")
        return dict(zip(self._UPLOAD_COLS, row))

    def mark_upload_uploaded(self, upload_id: str, *, object_key: str) -> bool:
        cur = self._conn.execute(
            "UPDATE uploads SET status='uploaded', object_key=%(obj)s,"
            " updated_at=CURRENT_TIMESTAMP"
            " WHERE id=%(id)s AND status IN ('issued','uploaded')",
            {"id": upload_id, "obj": object_key},
        )
        return cur.rowcount > 0

    def mark_upload_consumed(
        self, upload_id: str, *, doc_id: str, task_id: str,
        audit: tuple[str, str] | None = None,
    ) -> bool:
        conn = self._conn
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "UPDATE uploads SET status='consumed', doc_id=%(doc)s, task_id=%(task)s,"
                " updated_at=CURRENT_TIMESTAMP"
                " WHERE id=%(id)s AND status='uploaded'",
                {"id": upload_id, "doc": doc_id, "task": task_id},
            )
            consumed = cur.rowcount > 0
            if consumed and audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return consumed

    def list_expired_upload_credentials(self, now: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, object_key FROM uploads"
            " WHERE status IN ('issued','uploaded') AND expires_at <= %(now)s",
            {"now": now},
        ).fetchall()
        return [{"id": r[0], "object_key": r[1]} for r in rows]

    def delete_upload_credential(self, upload_id: str) -> None:
        self._conn.execute("DELETE FROM uploads WHERE id = %(id)s", {"id": upload_id})

    # ============ Audit 域（outbox 写入 + 月分区滚动——接口与 sqlite 月库不变） ============

    def append_outbox(self, event_type: str, payload_json: str) -> None:
        self._conn.execute(
            "INSERT INTO audit_outbox(id, event_type, payload_json)"
            " VALUES(%(id)s, %(t)s, %(p)s)",
            {"id": f"aud_{uuid.uuid4()}", "t": event_type, "p": payload_json},
        )

    def roll_monthly(self, when: object | None = None) -> object:
        """审计月分区滚动（方言差异在包内吸收——SQLite 月库文件 / PG 按月分区表）。"""
        return ensure_month_partition(self._conn, when)  # type: ignore[arg-type]

    # ---- 备份快照（D 组——NFR-10 / TC-OPS-05；pg_dump 属部署工具链不违 D2） ----

    def backup_snapshot(
        self, backup_dir, objects_dir=None, *, when=None, dsn: str | None = None,
    ) -> dict:
        """pg_dump -Fc 快照（+ objects tar）——dsn 缺省 env LATTICE_PG_DSN、
        schema 缺省 current_schema()（单 schema 部署口径）。"""
        import os as _os

        from .backup import snapshot as _snapshot

        if dsn is None:
            dsn = _os.environ.get("LATTICE_PG_DSN")
        if not dsn:
            params = self._conn.info.get_dsn_parameters()
            dsn = (
                f"postgresql://{params.get('user', 'postgres')}"
                f"@{params.get('host', 'localhost')}:{params.get('port', 5432)}"
                f"/{params.get('dbname', 'postgres')}"
            )
        schema = self._conn.execute("SELECT current_schema()").fetchone()[0]
        return _snapshot(
            dsn, Path(backup_dir),
            Path(objects_dir) if objects_dir is not None else None,
            schema=schema, when=when,
        )

    def trim_shipped_outbox(self, *, before_ts: str) -> int:
        """已搬运 outbox 行保留期清理（R2 P3-1——sqlite 同构，只删已搬运行）。"""
        cur = self._conn.execute(
            "DELETE FROM audit_outbox"
            " WHERE shipped_at IS NOT NULL AND shipped_at < %(before)s",
            {"before": before_ts},
        )
        return cur.rowcount

    # ============ Semantic 域（M2-S1——design §4/§5.8；与 sqlite 同语义，
    #              消息/行为等价、SQL 为 PG 方言渲染） ============

    _SEM_IN_CHUNK = 500  # ANY(%(keys)s) 数组分片上限（同 sqlite IN 分片口径）

    def upsert_entities_batch(self, org_id: str, rows: Sequence[dict]) -> dict:
        """同步实体分批 upsert——单批单事务（与 SqliteBackend 逐条同源：只写事实列、
        parent_id 三级解析〔批内 id 映射 / 批间缓存 / 库内回查——跨批父行 P2-1〕、
        updated 只计事实列变更——T-S1/T-S3；row.source 缺省 'sync'——yaml 纯人工
        实体 'curated'〔m2s-3〕；名称变更后刷新 FTS 文本行——C.3）。"""
        conn = self._conn
        existing = self._sem_read_existing(
            org_id, [(r["type"], r["key"]) for r in rows]
        )
        inserted = updated = 0
        touched: list[int] = []
        conn.execute("BEGIN")
        try:
            id_map = {k: v[0] for k, v in existing.items()}
            parent_cache: dict[tuple[str, str], int | None] = {}
            for row in rows:
                key = (row["type"], row["key"])
                parent_id = self._sem_parent_id(
                    org_id, row.get("parent_key"), id_map, parent_cache
                )
                row_source = row.get("source") or "sync"
                if key in existing:
                    _, old_name, old_attrs, old_parent, old_status = existing[key]
                    if (old_name != row["name"]
                            or old_attrs != row["attrs_json"]
                            or old_parent != parent_id
                            or old_status != "active"):
                        updated += 1
                    conn.execute(
                        "UPDATE sem_entities SET name = %(name)s,"
                        " attrs_json = %(attrs)s, parent_id = %(parent)s,"
                        " source_system = %(srcsys)s, status = 'active',"
                        " synced_at = %(ts)s, updated_at = CURRENT_TIMESTAMP"
                        " WHERE org_id = %(org)s AND type = %(type)s AND key = %(key)s",
                        {"name": row["name"], "attrs": row["attrs_json"],
                         "parent": parent_id, "srcsys": row["source_system"],
                         "ts": row["synced_at"], "org": org_id,
                         "type": row["type"], "key": row["key"]},
                    )
                    if old_name != row["name"]:
                        touched.append(id_map[key])
                else:
                    new_id = conn.execute(
                        "INSERT INTO sem_entities(org_id, type, key, name, parent_id,"
                        " attrs_json, source, source_system, status, synced_at)"
                        " VALUES(%(org)s, %(type)s, %(key)s, %(name)s, %(parent)s,"
                        " %(attrs)s, %(source)s, %(srcsys)s, 'active', %(ts)s)"
                        " RETURNING id",
                        {"org": org_id, "type": row["type"], "key": row["key"],
                         "name": row["name"], "parent": parent_id,
                         "attrs": row["attrs_json"], "source": row_source,
                         "srcsys": row["source_system"], "ts": row["synced_at"]},
                    ).fetchone()[0]
                    id_map[key] = new_id
                    touched.append(new_id)
                    inserted += 1
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        if touched:
            self.sem_refresh_search_texts(org_id, touched)
        return {"inserted": inserted, "updated": updated}

    def _sem_parent_id(self, org_id, parent_key, id_map: dict, parent_cache: dict):
        """parent_key "type:key" → id（P2-1 三级解析，与 sqlite 同语义）：批内
        id_map → 批间缓存 → 库内回查（跨批已提交父行）；悬挂父缓存 None。"""
        if not parent_key or ":" not in parent_key:
            return None
        ptype, _, pkey = parent_key.partition(":")
        pk = (ptype, pkey)
        if pk in id_map:
            return id_map[pk]
        if pk not in parent_cache:
            row = self._conn.execute(
                "SELECT id FROM sem_entities"
                " WHERE org_id = %(org)s AND type = %(type)s AND key = %(key)s",
                {"org": org_id, "type": pk[0], "key": pk[1]},
            ).fetchone()
            parent_cache[pk] = row[0] if row else None
        return parent_cache[pk]

    def _sem_read_existing(self, org_id: str, keys) -> dict:
        by_type: dict[str, list[str]] = {}
        for t, k in keys:
            by_type.setdefault(t, []).append(k)
        out: dict[tuple[str, str], tuple] = {}
        for t, ks in by_type.items():
            for chunk in _sem_chunks(ks, self._SEM_IN_CHUNK):
                rows = self._conn.execute(
                    "SELECT id, key, name, attrs_json, parent_id, status"
                    " FROM sem_entities WHERE org_id = %(org)s AND type = %(type)s"
                    "   AND key = ANY(%(keys)s)",
                    {"org": org_id, "type": t, "keys": chunk},
                ).fetchall()
                for r in rows:
                    out[(t, r[1])] = tuple(r[i] for i in (0, 2, 3, 4, 5))
        return out

    def resolve_entity_ids(
        self, org_id: str, keys: Sequence[tuple[str, str]]
    ) -> dict[tuple[str, str], int]:
        by_type: dict[str, list[str]] = {}
        for t, k in keys:
            by_type.setdefault(t, []).append(k)
        out: dict[tuple[str, str], int] = {}
        for t, ks in by_type.items():
            for chunk in _sem_chunks(ks, self._SEM_IN_CHUNK):
                rows = self._conn.execute(
                    "SELECT id, key FROM sem_entities"
                    " WHERE org_id = %(org)s AND type = %(type)s"
                    "   AND key = ANY(%(keys)s)",
                    {"org": org_id, "type": t, "keys": chunk},
                ).fetchall()
                for r in rows:
                    out[(t, r[1])] = r[0]
        return out

    def sem_active_source_keys(
        self, org_id: str, source_system: str
    ) -> set[tuple[str, str]]:
        """删除比例保护基数（m2s-3 起 per-source_system 收口——与 sqlite 同口径，
        yaml 纯人工实体 source='curated' 同入基数面）。"""
        rows = self._conn.execute(
            "SELECT type, key FROM sem_entities"
            " WHERE org_id = %(org)s AND source_system = %(srcsys)s"
            "   AND status = 'active'",
            {"org": org_id, "srcsys": source_system},
        ).fetchall()
        return {(r[0], r[1]) for r in rows}

    def sem_source_fill_stats(self, org_id: str, source_system: str) -> dict:
        row = self._conn.execute(
            "SELECT count(*), coalesce(sum("
            "  CASE WHEN (attrs_json::jsonb -> 'dims') IS NOT NULL THEN 1 ELSE 0 END"
            "), 0) FROM sem_entities"
            " WHERE org_id = %(org)s"
            "   AND source_system = %(srcsys)s AND status = 'active'",
            {"org": org_id, "srcsys": source_system},
        ).fetchone()
        return {"total": row[0], "filled": row[1]}

    def sem_entity_states(self, org_id: str, entity_ids: Sequence[int]) -> dict[int, dict]:
        """批量实体态（status/source——G-15 端点过滤与合并冲突判定共用）。"""
        out: dict[int, dict] = {}
        for chunk in _sem_chunks(list(entity_ids), self._SEM_IN_CHUNK):
            rows = self._conn.execute(
                "SELECT id, status, source FROM sem_entities"
                " WHERE org_id = %(org)s AND id = ANY(%(ids)s)",
                {"org": org_id, "ids": chunk},
            ).fetchall()
            for r in rows:
                out[r[0]] = {"status": r[1], "source": r[2]}
        return out

    def sem_entities_by_ids(self, org_id: str, entity_ids: Sequence[int]) -> list[dict]:
        """批量实体行（O-2 expand_relations seed 节点信息面）。"""
        out: list[dict] = []
        for chunk in _sem_chunks(list(entity_ids), self._SEM_IN_CHUNK):
            out.extend(
                self._sem_entity_row(r) for r in self._conn.execute(
                    "SELECT id, org_id, type, key, name, parent_id, attrs_json,"
                    " curated_json, source, source_system, status, sensitivity,"
                    " synced_at, curated_rev FROM sem_entities"
                    " WHERE org_id = %(org)s AND id = ANY(%(ids)s) ORDER BY id",
                    {"org": org_id, "ids": chunk},
                )
            )
        return out

    def mark_entities_missing(self, org_id: str, entity_ids: Sequence[int]) -> int:
        if not entity_ids:
            return 0
        n = 0
        conn = self._conn
        conn.execute("BEGIN")
        try:
            for chunk in _sem_chunks(list(entity_ids), self._SEM_IN_CHUNK):
                cur = conn.execute(
                    "UPDATE sem_entities SET status = 'missing',"
                    " updated_at = CURRENT_TIMESTAMP"
                    " WHERE org_id = %(org)s AND status = 'active'"
                    "   AND id = ANY(%(ids)s)",
                    {"org": org_id, "ids": chunk},
                )
                n += cur.rowcount
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return n

    def upsert_relations_batch(self, org_id: str, rows: Sequence[dict]) -> dict:
        """关系分批 upsert（单事务；端点不可变由 trg_sem_rel_noupdate 保证）。
        row.source/source_system（m2s-3）+ G-15 端点状态过滤（CASE 守卫——
        与 sqlite 同语义：指向非 active 端点的关系不置回 active）。"""
        conn = self._conn
        marks: dict[tuple, str] = {}
        conn.execute("BEGIN")
        try:
            for row in rows:
                k = (row["src_id"], row["rel_type"], row["dst_id"])
                old = conn.execute(
                    "SELECT attrs_json, status FROM sem_relations"
                    " WHERE org_id = %(org)s AND src_id = %(src)s"
                    "   AND rel_type = %(rel)s AND dst_id = %(dst)s",
                    {"org": org_id, "src": k[0], "rel": k[1], "dst": k[2]},
                ).fetchone()
                if old is None:
                    conn.execute(
                        "INSERT INTO sem_relations(org_id, src_id, rel_type, dst_id,"
                        " attrs_json, source, source_system, status, synced_at)"
                        " VALUES(%(org)s, %(src)s, %(rel)s, %(dst)s, %(attrs)s,"
                        " %(source)s, %(srcsys)s,"
                        " CASE WHEN EXISTS(SELECT 1 FROM sem_entities s"
                        "   WHERE s.id = %(src)s AND s.org_id = %(org)s"
                        "     AND s.status = 'active')"
                        "  AND EXISTS(SELECT 1 FROM sem_entities d"
                        "   WHERE d.id = %(dst)s AND d.org_id = %(org)s"
                        "     AND d.status = 'active')"
                        " THEN 'active' ELSE 'missing' END, %(ts)s)",
                        {"org": org_id, "src": k[0], "rel": k[1], "dst": k[2],
                         "attrs": row["attrs_json"],
                         "source": row.get("source") or "sync",
                         "srcsys": row.get("source_system"), "ts": row["synced_at"]},
                    )
                    marks[k] = "i"
                else:
                    if old[0] != row["attrs_json"] or old[1] != "active":
                        marks[k] = "u"
                    else:
                        marks[k] = "s"
                    conn.execute(
                        "UPDATE sem_relations SET attrs_json = %(attrs)s,"
                        " status = CASE WHEN"
                        "   EXISTS(SELECT 1 FROM sem_entities s"
                        "     WHERE s.id = %(src)s AND s.org_id = %(org)s"
                        "     AND s.status = 'active')"
                        "   AND EXISTS(SELECT 1 FROM sem_entities d"
                        "     WHERE d.id = %(dst)s AND d.org_id = %(org)s"
                        "     AND d.status = 'active')"
                        " THEN 'active' ELSE status END,"
                        " synced_at = %(ts)s"
                        " WHERE org_id = %(org)s AND src_id = %(src)s"
                        "   AND rel_type = %(rel)s AND dst_id = %(dst)s",
                        {"attrs": row["attrs_json"], "ts": row["synced_at"],
                         "org": org_id, "src": k[0], "rel": k[1], "dst": k[2]},
                    )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return {
            "inserted": sum(1 for v in marks.values() if v == "i"),
            "updated": sum(1 for v in marks.values() if v == "u"),
        }

    def sem_active_source_relation_keys(
        self, org_id: str, source_system: str
    ) -> set[tuple[int, str, int]]:
        """本源 active 关系键集（G-15 关系级消失检测——与 sqlite 同口径）。"""
        return {
            (r[0], r[1], r[2]) for r in self._conn.execute(
                "SELECT src_id, rel_type, dst_id FROM sem_relations"
                " WHERE org_id = %(org)s AND source_system = %(srcsys)s"
                "   AND status = 'active'",
                {"org": org_id, "srcsys": source_system},
            )
        }

    def sem_mark_relations_missing(
        self, org_id: str, keys: Sequence[tuple[int, str, int]]
    ) -> int:
        """快照消失的关系 → missing（G-15——synced_at 保留为宽限起算锚）。"""
        n = 0
        conn = self._conn
        conn.execute("BEGIN")
        try:
            for src_id, rel, dst_id in keys:
                cur = conn.execute(
                    "UPDATE sem_relations SET status = 'missing'"
                    " WHERE org_id = %(org)s AND src_id = %(src)s"
                    "   AND rel_type = %(rel)s AND dst_id = %(dst)s"
                    "   AND status = 'active'",
                    {"org": org_id, "src": src_id, "rel": rel, "dst": dst_id},
                )
                n += cur.rowcount
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return n

    def sem_relations_lookup(
        self, org_id: str, keys: Sequence[tuple[int, str, int]]
    ) -> dict[tuple[int, str, int], dict]:
        """关系行批查（合并规则表「与同步关系重复」判定面——yaml_merge）。"""
        out: dict[tuple[int, str, int], dict] = {}
        for src_id, rel, dst_id in keys:
            row = self._conn.execute(
                "SELECT source, status FROM sem_relations"
                " WHERE org_id = %(org)s AND src_id = %(src)s"
                "   AND rel_type = %(rel)s AND dst_id = %(dst)s",
                {"org": org_id, "src": src_id, "rel": rel, "dst": dst_id},
            ).fetchone()
            if row is not None:
                out[(src_id, rel, dst_id)] = {"source": row[0], "status": row[1]}
        return out

    def rebuild_sync_aliases(self, org_id: str, rows: Sequence[dict]) -> int:
        """别名三 kind 重建（单事务先删后插——manual/abbr 原样，TC-SYNC-05）；
        重建后刷新 FTS 文本行（C.3）。"""
        conn = self._conn
        ids = self.resolve_entity_ids(
            org_id, [(r["type"], r["key"]) for r in rows]
        )
        inserted = 0
        conn.execute("BEGIN")
        try:
            for row in rows:
                eid = ids.get((row["type"], row["key"]))
                if eid is None:
                    continue
                conn.execute(
                    "DELETE FROM sem_aliases WHERE org_id = %(org)s"
                    " AND entity_id = %(eid)s AND kind IN ('name', 'code', 'sync')",
                    {"org": org_id, "eid": eid},
                )
                for alias, alias_norm, kind in row["aliases"]:
                    conn.execute(
                        "INSERT INTO sem_aliases(org_id, entity_id, alias, alias_norm,"
                        " kind) VALUES(%(org)s, %(eid)s, %(alias)s, %(norm)s, %(kind)s)",
                        {"org": org_id, "eid": eid, "alias": alias,
                         "norm": alias_norm, "kind": kind},
                    )
                    inserted += 1
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        if ids:
            self.sem_refresh_search_texts(org_id, sorted(ids.values()))
        return inserted

    def advance_status(self, org_id: str, *, missing_before: str) -> dict:
        """missing 宽限期推进（超期 → retired + 关系一并 retired——T-S4；与
        sqlite 同语义同计数口径；G-15 关系级 missing 同口推进——
        relations_retired_standalone）。推进口径（P3-8）：org 全量推进、不按
        source_system 收口（多适配器共享同一时间窗——本段接受口径）。"""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            retired_ids = [
                r[0] for r in conn.execute(
                    "SELECT id FROM sem_entities"
                    " WHERE org_id = %(org)s AND status = 'missing'"
                    "   AND synced_at < %(before)s",
                    {"org": org_id, "before": missing_before},
                ).fetchall()
            ]
            relations_retired = 0
            for chunk in _sem_chunks(retired_ids, self._SEM_IN_CHUNK):
                conn.execute(
                    "UPDATE sem_entities SET status = 'retired',"
                    " updated_at = CURRENT_TIMESTAMP"
                    " WHERE org_id = %(org)s AND id = ANY(%(ids)s)",
                    {"org": org_id, "ids": chunk},
                )
                cur = conn.execute(
                    # 级联覆盖 active + missing（G-15——与 sqlite 同口径）
                    "UPDATE sem_relations SET status = 'retired'"
                    " WHERE org_id = %(org)s AND status IN ('active', 'missing')"
                    "   AND (src_id = ANY(%(ids)s) OR dst_id = ANY(%(ids)s))",
                    {"org": org_id, "ids": chunk},
                )
                relations_retired += cur.rowcount
            relations_retired_standalone = conn.execute(
                "UPDATE sem_relations SET status = 'retired'"
                " WHERE org_id = %(org)s AND status = 'missing'"
                "   AND synced_at < %(before)s",
                {"org": org_id, "before": missing_before},
            ).rowcount
            missing_now = conn.execute(
                "SELECT count(*) FROM sem_entities"
                " WHERE org_id = %(org)s AND status = 'missing'",
                {"org": org_id},
            ).fetchone()[0]
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return {
            "missing": missing_now,
            "retired": len(retired_ids),
            "relations_retired": relations_retired,
            "relations_retired_standalone": relations_retired_standalone,
        }

    def sem_start_run(self, org_id: str, adapter: str, *, now: str) -> int:
        new_id = self._conn.execute(
            "INSERT INTO sem_sync_runs(org_id, adapter, started_at, status)"
            " VALUES(%(org)s, %(adapter)s, %(now)s, 'running') RETURNING id",
            {"org": org_id, "adapter": adapter, "now": now},
        ).fetchone()[0]
        return new_id

    def sem_finish_run(
        self, org_id: str, run_id: int, *, status: str, stats_json: str,
        error: str | None = None, now: str | None = None,
    ) -> None:
        self._conn.execute(
            "UPDATE sem_sync_runs SET status = %(status)s, stats_json = %(stats)s,"
            " error = %(error)s, finished_at = COALESCE(%(now)s, CURRENT_TIMESTAMP)"
            " WHERE id = %(rid)s AND org_id = %(org)s",
            {"status": status, "stats": stats_json, "error": error,
             "now": now, "rid": run_id, "org": org_id},
        )

    def sem_list_sync_runs(
        self, org_id: str, *, limit: int = 50,
        adapter: str | None = None, status: str | None = None,
    ) -> list[dict]:
        cols = ("id", "org_id", "adapter", "started_at", "finished_at",
                "status", "stats_json", "error")
        sql = ("SELECT id, org_id, adapter, started_at, finished_at, status,"
               " stats_json, error FROM sem_sync_runs WHERE org_id = %(org)s")
        params: dict[str, object] = {"org": org_id}
        if adapter is not None:
            sql += " AND adapter = %(adapter)s"
            params["adapter"] = adapter
        if status is not None:
            sql += " AND status = %(status)s"
            params["status"] = status
        sql += " ORDER BY id DESC LIMIT %(limit)s"
        params["limit"] = limit
        rows = self._conn.execute(sql, params).fetchall()
        return [_sem_run_dict(cols, r) for r in rows]

    def sem_list_builds(
        self, org_id: str, *, limit: int = 200, status: str | None = None,
    ) -> list[dict]:
        cols = ("id", "org_id", "dict_rev", "yaml_rev", "sync_run_id",
                "status", "stats_json", "created_at")
        sql = ("SELECT id, org_id, dict_rev, yaml_rev, sync_run_id, status,"
               " stats_json, created_at FROM sem_builds WHERE org_id = %(org)s")
        params: dict[str, object] = {"org": org_id}
        if status is not None:
            sql += " AND status = %(status)s"
            params["status"] = status
        sql += " ORDER BY id DESC LIMIT %(limit)s"
        params["limit"] = limit
        rows = self._conn.execute(sql, params).fetchall()
        return [_sem_run_dict(cols, r) for r in rows]

    def sem_get_build(self, org_id: str, build_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, dict_rev, yaml_rev, sync_run_id, status, stats_json,"
            " created_at FROM sem_builds WHERE org_id = %(org)s AND id = %(bid)s",
            {"org": org_id, "bid": build_id},
        ).fetchone()
        if row is None:
            return None
        cols = ("id", "org_id", "dict_rev", "yaml_rev", "sync_run_id",
                "status", "stats_json", "created_at")
        return _sem_run_dict(cols, row)

    def sem_current_build(self, org_id: str) -> dict | None:
        """当前构建 = 最新 ready 行（G-18/m2s-3：按 (activated_at, id) DESC——
        与 sqlite 同口径；rev 回退重激活的行顶置 activated_at 成 current）。"""
        row = self._conn.execute(
            "SELECT id, org_id, dict_rev, yaml_rev, sync_run_id, status, stats_json,"
            " created_at, activated_at FROM sem_builds WHERE org_id = %(org)s"
            " AND status = 'ready'"
            " ORDER BY activated_at DESC NULLS LAST, id DESC LIMIT 1",
            {"org": org_id},
        ).fetchone()
        if row is None:
            return None
        cols = ("id", "org_id", "dict_rev", "yaml_rev", "sync_run_id",
                "status", "stats_json", "created_at", "activated_at")
        return _sem_run_dict(cols, row)

    def sem_active_snapshot(self, org_id: str) -> dict:
        """构建输入快照（§5.8 第 1 步——与 sqlite 同结构同稳定序；实体含
        curated_json/curated_rev——G-17/m2s-3：YAML 改 definition 必触发重建）。"""
        entities = [
            {"id": r[0], "type": r[1], "key": r[2], "name": r[3],
             "parent_id": r[4], "attrs_json": r[5], "sensitivity": r[6],
             "curated_json": r[7] or "{}", "curated_rev": r[8]}
            for r in self._conn.execute(
                "SELECT id, type, key, name, parent_id, attrs_json, sensitivity,"
                " curated_json, curated_rev"
                " FROM sem_entities WHERE org_id = %(org)s AND status = 'active'"
                " ORDER BY id", {"org": org_id},
            )
        ]
        aliases = [
            {"entity_id": r[0], "alias": r[1], "alias_norm": r[2], "kind": r[3],
             "match_mode": r[4], "weight": r[5]}
            for r in self._conn.execute(
                "SELECT a.entity_id, a.alias, a.alias_norm, a.kind, a.match_mode,"
                " a.weight FROM sem_aliases a"
                " JOIN sem_entities e ON e.id = a.entity_id"
                " WHERE a.org_id = %(org)s AND e.status = 'active'"
                " ORDER BY a.entity_id, a.alias_norm", {"org": org_id},
            )
        ]
        relations = [
            {"src_id": r[0], "rel_type": r[1], "dst_id": r[2],
             "attrs_json": r[3], "source": r[4]}
            for r in self._conn.execute(
                "SELECT src_id, rel_type, dst_id, attrs_json, source"
                " FROM sem_relations WHERE org_id = %(org)s AND status = 'active'"
                " ORDER BY src_id, rel_type, dst_id", {"org": org_id},
            )
        ]
        return {"entities": entities, "aliases": aliases, "relations": relations}

    def sem_insert_build(
        self, org_id: str, dict_rev: str, stats_json: str, *,
        yaml_rev: str | None = None, sync_run_id: int | None = None,
    ) -> tuple[int, bool]:
        """building 行 upsert（O-1/m2s-3 条件 upsert——``DO UPDATE … WHERE
        status != 'ready'``：同 rev 行已 ready 不重断 building，返回
        ``(existing_id, True)``；正常路径 ``(id, False)``——与 sqlite 同语义）。"""
        row = self._conn.execute(
            "INSERT INTO sem_builds(org_id, dict_rev, yaml_rev, sync_run_id,"
            " status, stats_json) VALUES(%(org)s, %(rev)s, %(yaml)s, %(run)s,"
            " 'building', %(stats)s)"
            " ON CONFLICT(org_id, dict_rev) DO UPDATE SET"
            "   status = 'building', stats_json = EXCLUDED.stats_json,"
            "   yaml_rev = EXCLUDED.yaml_rev, sync_run_id = EXCLUDED.sync_run_id,"
            "   activated_at = NULL"
            " WHERE sem_builds.status != 'ready'"
            " RETURNING id",
            {"org": org_id, "rev": dict_rev, "yaml": yaml_rev,
             "run": sync_run_id, "stats": stats_json},
        ).fetchone()
        if row is not None:
            return row[0], False
        existing = self._conn.execute(
            "SELECT id FROM sem_builds WHERE org_id = %(org)s AND dict_rev = %(rev)s",
            {"org": org_id, "rev": dict_rev},
        ).fetchone()
        return existing[0], True

    def sem_reactivate_build(
        self, org_id: str, build_id: int, stats_json: str, *,
        audit: tuple[str, str] | None = None,
    ) -> bool:
        """G-18 rev 回退重激活：ready 行顶置 activated_at（取 max(现在, 本 org
        既有最大 + 1s)——严格递增防同秒并列；+ready 事件同事务）；仅
        status='ready' 行生效——与 sqlite 同语义。"""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "UPDATE sem_builds SET activated_at = GREATEST(CURRENT_TIMESTAMP,"
                "  (SELECT MAX(b.activated_at) + interval '1 second'"
                "     FROM sem_builds b WHERE b.org_id = %(org)s)),"
                " stats_json = %(stats)s"
                " WHERE org_id = %(org)s AND id = %(bid)s AND status = 'ready'",
                {"stats": stats_json, "org": org_id, "bid": build_id},
            )
            effective = cur.rowcount == 1
            if effective and audit is not None:
                conn.execute(
                    "INSERT INTO audit_outbox(id, event_type, payload_json)"
                    " VALUES(%(id)s, %(t)s, %(p)s)",
                    {"id": f"aud_{uuid.uuid4()}", "t": audit[0], "p": audit[1]},
                )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return effective

    def sem_switch_build_ready(
        self, org_id: str, build_id: int, stats_json: str, *,
        audit: tuple[str, str] | None = None,
    ) -> bool:
        """原子切换 + ready 事件同一事务（P3-5/R2——audit 仅真生效写；并发输者
        rowcount=0 返回 False 零事件，P2-2；activated_at 顶置——G-18——与
        sqlite 同语义）。"""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "UPDATE sem_builds SET status = 'ready', stats_json = %(stats)s,"
                " activated_at = CURRENT_TIMESTAMP"
                " WHERE org_id = %(org)s AND id = %(bid)s AND status = 'building'",
                {"stats": stats_json, "org": org_id, "bid": build_id},
            )
            effective = cur.rowcount == 1
            if effective and audit is not None:
                conn.execute(
                    "INSERT INTO audit_outbox(id, event_type, payload_json)"
                    " VALUES(%(id)s, %(t)s, %(p)s)",
                    {"id": f"aud_{uuid.uuid4()}", "t": audit[0], "p": audit[1]},
                )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return effective

    def sem_fail_build(
        self, org_id: str, build_id: int, stats_json: str, *,
        audit: tuple[str, str] | None = None,
    ) -> bool:
        """失败收尾 + failed 事件同一事务；仅真生效返回 True（P2-2/R2——
        已终态行幂等零生效，不写脏 failed 审计）。"""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "UPDATE sem_builds SET status = 'failed', stats_json = %(stats)s"
                " WHERE org_id = %(org)s AND id = %(bid)s AND status = 'building'",
                {"stats": stats_json, "org": org_id, "bid": build_id},
            )
            effective = cur.rowcount == 1
            if effective and audit is not None:
                conn.execute(
                    "INSERT INTO audit_outbox(id, event_type, payload_json)"
                    " VALUES(%(id)s, %(t)s, %(p)s)",
                    {"id": f"aud_{uuid.uuid4()}", "t": audit[0], "p": audit[1]},
                )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return effective

    def save_build(self, org_id: str, dict_rev: str, stats_json: str) -> int:
        new_id = self._conn.execute(
            "INSERT INTO sem_builds(org_id, dict_rev, stats_json, status)"
            " VALUES(%(org)s, %(rev)s, %(stats)s, 'building') RETURNING id",
            {"org": org_id, "rev": dict_rev, "stats": stats_json},
        ).fetchone()[0]
        return new_id

    def load_build(self, org_id: str, dict_rev: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, dict_rev, yaml_rev, sync_run_id, status, stats_json,"
            " created_at FROM sem_builds WHERE org_id = %(org)s AND dict_rev = %(rev)s",
            {"org": org_id, "rev": dict_rev},
        ).fetchone()
        if row is None:
            return None
        cols = ("id", "org_id", "dict_rev", "yaml_rev", "sync_run_id",
                "status", "stats_json", "created_at")
        return _sem_run_dict(cols, row)

    def export_l0(self, org_id: str) -> str:
        """L0 术语片段导出——构建产物落地归 m2s-2（本段空串占位）。"""
        return ""

    # ---- m2s-3：YAML curated 合并面 + FTS 索引面（与 sqlite 同语义） ----

    def sem_write_curated_batch(self, org_id: str, rows: Sequence[dict]) -> int:
        """curated_json 批写（规则表第 1 行）+ 可选 sensitivity 覆盖。"""
        if not rows:
            return 0
        conn = self._conn
        conn.execute("BEGIN")
        try:
            for row in rows:
                conn.execute(
                    "UPDATE sem_entities SET curated_json = %(curated)s,"
                    " curated_rev = %(rev)s, updated_at = CURRENT_TIMESTAMP,"
                    " sensitivity = COALESCE(%(sensitivity)s, sensitivity)"
                    " WHERE org_id = %(org)s AND type = %(type)s AND key = %(key)s"
                    "   AND status = 'active'",
                    {"curated": row["curated_json"], "rev": row["curated_rev"],
                     "sensitivity": row.get("sensitivity"),
                     "org": org_id, "type": row["type"], "key": row["key"]},
                )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return len(rows)

    def sem_replace_manual_aliases(self, org_id: str, rows: Sequence[dict]) -> int:
        """manual/abbr 别名整替（先删后插，只动这两类——T-S1/TC-SYNC-05）。"""
        if not rows:
            return 0
        conn = self._conn
        ids = self.resolve_entity_ids(
            org_id, [(r["type"], r["key"]) for r in rows]
        )
        inserted = 0
        touched: list[int] = []
        conn.execute("BEGIN")
        try:
            for row in rows:
                eid = ids.get((row["type"], row["key"]))
                if eid is None:
                    continue
                conn.execute(
                    "DELETE FROM sem_aliases WHERE org_id = %(org)s"
                    " AND entity_id = %(eid)s AND kind IN ('manual', 'abbr')",
                    {"org": org_id, "eid": eid},
                )
                for alias, alias_norm, kind, match_mode in row["aliases"]:
                    conn.execute(
                        "INSERT INTO sem_aliases(org_id, entity_id, alias,"
                        " alias_norm, kind, match_mode)"
                        " VALUES(%(org)s, %(eid)s, %(alias)s, %(norm)s,"
                        " %(kind)s, %(mode)s)",
                        {"org": org_id, "eid": eid, "alias": alias,
                         "norm": alias_norm, "kind": kind, "mode": match_mode},
                    )
                    inserted += 1
                touched.append(eid)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        if touched:
            self.sem_refresh_search_texts(org_id, touched)
        return inserted

    def sem_clear_stale_curated(
        self, org_id: str, keep_entity_ids: Sequence[int]
    ) -> int:
        """YAML 删除覆盖项（规则表第 8 行）——与 sqlite 同语义（source='sync'
        且 curated_rev 非空、不在 keep 集 → 清 curated + 删 manual/abbr）。"""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            stale = [
                r[0] for r in conn.execute(
                    "SELECT id FROM sem_entities WHERE org_id = %(org)s"
                    " AND source = 'sync' AND status != 'retired'"
                    " AND curated_rev IS NOT NULL"
                    + (" AND id != ALL(%(keep)s)" if keep_entity_ids else ""),
                    {"org": org_id, "keep": list(keep_entity_ids)},
                ).fetchall()
            ]
            for chunk in _sem_chunks(stale, self._SEM_IN_CHUNK):
                conn.execute(
                    "UPDATE sem_entities SET curated_json = '{}',"
                    " curated_rev = NULL, updated_at = CURRENT_TIMESTAMP"
                    " WHERE org_id = %(org)s AND id = ANY(%(ids)s)",
                    {"org": org_id, "ids": chunk},
                )
                conn.execute(
                    "DELETE FROM sem_aliases WHERE org_id = %(org)s"
                    " AND entity_id = ANY(%(ids)s) AND kind IN ('manual', 'abbr')",
                    {"org": org_id, "ids": chunk},
                )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        if stale:
            self.sem_refresh_search_texts(org_id, stale)
        return len(stale)

    def sem_refresh_search_texts(self, org_id: str, entity_ids: Sequence[int]) -> None:
        """实体 FTS 文本行重建（名称 + 别名分词拼接——tsvector GENERATED 自动
        随行更新，无需 sqlite 的外容 delete 命令）。"""
        from knowledge_lattice.adapters.tokenizer import word_tokens

        conn = self._conn
        conn.execute("BEGIN")
        try:
            for chunk in _sem_chunks(list(entity_ids), self._SEM_IN_CHUNK):
                if not chunk:
                    continue
                conn.execute(
                    "DELETE FROM sem_search_texts WHERE org_id = %(org)s"
                    " AND entity_id = ANY(%(ids)s)",
                    {"org": org_id, "ids": chunk},
                )
                rows = conn.execute(
                    "SELECT e.id, e.name FROM sem_entities e"
                    " WHERE e.org_id = %(org)s AND e.id = ANY(%(ids)s)"
                    "   AND e.status = 'active'",
                    {"org": org_id, "ids": chunk},
                ).fetchall()
                for eid, name in rows:
                    aliases = conn.execute(
                        "SELECT alias FROM sem_aliases WHERE org_id = %(org)s"
                        " AND entity_id = %(eid)s",
                        {"org": org_id, "eid": eid},
                    ).fetchall()
                    texts = [name] + [a[0] for a in aliases]
                    seg = " ".join(tok for t in texts for tok in word_tokens(t))
                    if not seg:
                        continue
                    conn.execute(
                        "INSERT INTO sem_search_texts(org_id, entity_id, seg_text)"
                        " VALUES(%(org)s, %(eid)s, %(seg)s)",
                        {"org": org_id, "eid": eid, "seg": seg},
                    )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def sem_restricted_column_keys(self, org_id: str, table_id: int) -> set[str]:
        """C.5：表下 restricted 列键集（describe_table 主路径列级过滤面）。"""
        return {
            r[0] for r in self._conn.execute(
                "SELECT c.key FROM sem_relations r"
                " JOIN sem_entities c ON c.id = r.dst_id"
                " WHERE r.org_id = %(org)s AND r.src_id = %(tid)s"
                "   AND r.rel_type = 'has_column' AND r.status = 'active'"
                "   AND c.status = 'active' AND c.sensitivity = 'restricted'",
                {"org": org_id, "tid": table_id},
            )
        }

    # ---- m2s-2 首批语义工具读取面（与 sqlite 同语义——参数风格 %(name)s） ----

    _SEM_ENTITY_COLS = ("id", "org_id", "type", "key", "name", "parent_id",
                        "attrs_json", "curated_json", "source", "source_system",
                        "status", "sensitivity", "synced_at", "curated_rev")

    def _sem_entity_row(self, row) -> dict:
        return dict(zip(self._SEM_ENTITY_COLS, row))

    def sem_entity_by_id(self, org_id: str, entity_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, type, key, name, parent_id, attrs_json,"
            " curated_json, source, source_system, status, sensitivity,"
            " synced_at, curated_rev FROM sem_entities"
            " WHERE org_id = %(org)s AND id = %(eid)s",
            {"org": org_id, "eid": entity_id},
        ).fetchone()
        return self._sem_entity_row(row) if row is not None else None

    def sem_entity_by_key(self, org_id: str, type_: str, key: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, type, key, name, parent_id, attrs_json,"
            " curated_json, source, source_system, status, sensitivity,"
            " synced_at, curated_rev FROM sem_entities"
            " WHERE org_id = %(org)s AND type = %(type)s AND key = %(key)s",
            {"org": org_id, "type": type_, "key": key},
        ).fetchone()
        return self._sem_entity_row(row) if row is not None else None

    def sem_entity_aliases(
        self, org_id: str, entity_ids: Sequence[int]
    ) -> list[dict]:
        out: list[dict] = []
        for chunk in _sem_chunks(list(entity_ids), self._SEM_IN_CHUNK):
            if not chunk:
                continue
            rows = self._conn.execute(
                "SELECT entity_id, alias, alias_norm, kind, match_mode, weight"
                " FROM sem_aliases WHERE org_id = %(org)s"
                "   AND entity_id = ANY(%(ids)s)"
                " ORDER BY entity_id, alias_norm",
                {"org": org_id, "ids": chunk},
            ).fetchall()
            out.extend(
                {"entity_id": r[0], "alias": r[1], "alias_norm": r[2],
                 "kind": r[3], "match_mode": r[4], "weight": r[5]}
                for r in rows
            )
        return out

    def sem_expand_graph(
        self, org_id: str, root_id: int, *,
        outgoing: Sequence[str], incoming: Sequence[str],
        depth: int, fanout_limit: int, node_limit: int,
    ) -> dict:
        """BFS 逐层批量展开（递归 CTE 的等价 SQL——与 sqlite 同策略同语义：
        visited 防环 / fanout 每节点截断 / node_limit 总量截断 / restricted 与
        非 active 端点不出现；P3-2/R2：edges 去重且端点恒 ∈ {root} ∪ nodes）。"""
        nodes: dict[int, dict] = {}
        edges: list[dict] = []
        seen_edges: set[tuple[int, str, int]] = set()
        truncated = False
        visited = {root_id}
        frontier = [root_id]
        for _level in range(1, depth + 1):
            if not frontier:
                break
            next_frontier: list[int] = []
            for node in frontier:
                for rels, forward in ((outgoing, True), (incoming, False)):
                    if not rels:
                        continue
                    anchor = "r.src_id" if forward else "r.dst_id"
                    other = "r.dst_id" if forward else "r.src_id"
                    rows = self._conn.execute(
                        "SELECT r.src_id, r.rel_type, r.dst_id, r.source,"
                        " e.id, e.type, e.key, e.name"
                        " FROM sem_relations r JOIN sem_entities e"
                        f"   ON e.id = {other}"
                        " WHERE r.org_id = %(org)s AND r.status = 'active'"
                        "   AND e.status = 'active' AND e.sensitivity = 'normal'"
                        f"   AND {anchor} = %(node)s"
                        "   AND r.rel_type = ANY(%(rels)s)"
                        f" ORDER BY r.rel_type, {other}",
                        {"org": org_id, "node": node, "rels": list(rels)},
                    ).fetchall()
                    fan = 0
                    for src, rel, dst, rel_source, oid, otype, okey, oname in rows:
                        if fan >= fanout_limit:
                            truncated = True
                            break
                        edge_key = (src, rel, dst)
                        if edge_key in seen_edges:
                            continue  # P3-2/R2：同关系行双向只计一次
                        if oid not in visited and len(nodes) >= node_limit:
                            # P3-2/R2：节点截断后不产悬挂边
                            truncated = True
                            continue
                        fan += 1
                        seen_edges.add(edge_key)
                        edges.append({"src": src, "rel": rel, "dst": dst,
                                      "source": rel_source})
                        if oid not in visited:
                            visited.add(oid)
                            nodes[oid] = {"id": oid, "type": otype, "key": okey,
                                          "name": oname, "depth": _level}
                            next_frontier.append(oid)
            frontier = next_frontier
        return {"nodes": list(nodes.values()), "edges": edges, "truncated": truncated}

    def sem_search_entities(
        self, org_id: str, q_norm: str, q_raw: str, *,
        types: Sequence[str] | None, top_k: int,
    ) -> list[dict]:
        """三层（与 sqlite 同语义）：alias 精确 1.0 > 前缀 0.8 > FTS 模糊 0.5
        （C.3/m2s-3：LIKE 骨架升级为 tsvector @@ to_tsquery over
        sem_search_texts——评分差异与 sqlite bm25 按 G-6 口径登记不追平）；
        LIKE 前缀统一 LOWER + ESCAPE（pg LIKE 默认大小写敏感——显式 LOWER 拉平）。
        P2-1/R2：score 常量显式 ::float8——PG 裸字面量为 NUMERIC（psycopg 归
        Decimal），与 sqlite float 类型漂移会致 FastMCP 出参字符串化。"""
        esc_norm = _like_escape(q_norm)
        type_filter = ""
        params: dict[str, object] = {"org": org_id}
        if types:
            type_filter = " AND e.type = ANY(%(types)s)"
            params["types"] = list(types)
        base = (
            " FROM sem_aliases a JOIN sem_entities e ON e.id = a.entity_id"
            " WHERE a.org_id = %(org)s AND e.status = 'active'"
            " AND e.sensitivity = 'normal'" + type_filter
        )
        sql = (
            "SELECT * FROM ("
            "  SELECT e.id, e.type, e.key, e.name, e.attrs_json, e.curated_json,"
            "         CAST(1.0 AS double precision) AS score,"
            "         'alias-exact' AS via" + base
            + "   AND a.alias_norm = %(q_exact)s"
            "  UNION ALL"
            "  SELECT e.id, e.type, e.key, e.name, e.attrs_json, e.curated_json,"
            "         CAST(0.8 AS double precision) AS score,"
            "         'alias-prefix' AS via" + base
            + "   AND a.alias_norm LIKE %(q_prefix)s ESCAPE '\\'"
            ") ORDER BY score DESC, id ASC LIMIT %(lim)s"
        )
        query_params = dict(params)
        query_params.update({
            "q_exact": q_norm, "q_prefix": f"{esc_norm}%",
            "lim": max(top_k * 2, top_k),
        })
        rows = self._conn.execute(sql, query_params).fetchall()
        cols = ("id", "type", "key", "name", "attrs_json", "curated_json",
                "score", "via")
        out = [dict(zip(cols, r)) for r in rows]
        fts_rows = self._sem_fts_layer(
            org_id, q_norm, top_k=top_k, type_filter=type_filter, params=params)
        if fts_rows:
            out.extend(fts_rows)
        return out

    def _sem_fts_layer(self, org_id: str, q_norm: str, *, top_k: int,
                       type_filter: str, params: dict) -> list[dict] | None:
        """FTS 第三层（C.3）：查询分词 → ' & ' AND to_tsquery('simple')——贴近
        子串包含语义；无 token（纯符号）返回 None 跳层；ts_rank 排序（G-6 登记）。"""
        from knowledge_lattice.adapters.tokenizer import word_tokens

        tokens = word_tokens(q_norm)
        if not tokens:
            return None
        tsquery = " & ".join(
            t.replace("\\", "\\\\").replace("'", "''").replace(":", "\\:")
            for t in tokens)
        sql = (
            "SELECT e.id, e.type, e.key, e.name, e.attrs_json, e.curated_json,"
            " CAST(0.5 AS double precision) AS score, 'fts' AS via,"
            " ts_rank(t.tsv, q.query) AS rank"
            " FROM sem_search_texts t"
            " JOIN sem_entities e ON e.id = t.entity_id,"
            " to_tsquery('simple', %(tsq)s) AS q(query)"
            " WHERE t.org_id = %(org)s AND t.tsv @@ q.query"
            " AND e.org_id = %(org)s AND e.status = 'active'"
            " AND e.sensitivity = 'normal'" + type_filter +
            " ORDER BY rank DESC, e.id ASC LIMIT %(lim)s"
        )
        query_params = dict(params)
        query_params.update({"tsq": tsquery, "lim": top_k})
        rows = self._conn.execute(sql, query_params).fetchall()
        cols = ("id", "type", "key", "name", "attrs_json", "curated_json",
                "score", "via", "rank")
        out = [dict(zip(cols, r)) for r in rows]
        for r in out:
            if not isinstance(r["score"], float):
                r["score"] = float(r["score"])
            if not isinstance(r["rank"], float):
                r["rank"] = float(r["rank"])
        return out

    def sem_table_columns(self, org_id: str, table_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT c.key, c.name FROM sem_relations r"
            " JOIN sem_entities c ON c.id = r.dst_id"
            " WHERE r.org_id = %(org)s AND r.src_id = %(tid)s"
            "   AND r.rel_type = 'has_column' AND r.status = 'active'"
            "   AND c.status = 'active' AND c.sensitivity = 'normal'"
            " ORDER BY c.key",
            {"org": org_id, "tid": table_id},
        ).fetchall()
        return [{"key": r[0], "name": r[1]} for r in rows]

    # ============ Audit 域扩展（M2.4 m2-2：同事务接入 + 搬运/封存/保留） ============

    def _rollback(self) -> None:
        """事务回滚（连接可能已断——失败不得覆盖原始异常）。"""
        try:
            self._conn.execute("ROLLBACK")
        except psycopg.Error:
            pass

    def _outbox_insert(self, conn, event_type: str, payload_json: str) -> None:
        """outbox 行插入（**参与调用方事务**——TC-OPS-01 崩溃注入锚点）。"""
        conn.execute(
            "INSERT INTO audit_outbox(id, event_type, payload_json)"
            " VALUES(%(id)s, %(t)s, %(p)s)",
            {"id": f"aud_{uuid.uuid4()}", "t": event_type, "p": payload_json},
        )

    def ship_outbox(self, *, now: str | None = None, batch: int = 500) -> dict:
        """搬运 outbox → audit_events 分区表（按事件原时刻 created_at 路由）+
        回填 shipped_at——**同库单事务**（BEGIN…COMMIT：插入+回填原子，
        sqlite 跨文件两步形态的方言对照，接口语义一致：不丢不重）。"""
        from knowledge_lattice.store.audit_chain import (
            compute_row_hash,
            month_of,
            outbox_row_to_event,
        )
        from knowledge_lattice.store.taskclock import utc_now_ts

        from .audit import ensure_month_partition, last_row_hash, month_bounds

        now_ts = now or utc_now_ts()
        cols = ("id", "event_type", "payload_json", "created_at")
        total = 0
        while True:
            conn = self._conn
            conn.execute("BEGIN")
            try:
                rows = conn.execute(
                    "SELECT id, event_type, payload_json, created_at FROM audit_outbox"
                    " WHERE shipped_at IS NULL ORDER BY created_at, id LIMIT %(n)s",
                    {"n": batch},
                ).fetchall()
                if not rows:
                    conn.execute("COMMIT")
                    break
                by_month: dict[str, list[dict]] = {}
                for r in rows:
                    rec = dict(zip(cols, r))
                    # 时间列归一化：TIMESTAMP → 'YYYY-MM-DD HH:MM:SS'（UTC——连接工厂钉死）
                    rec["created_at"] = rec["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                    by_month.setdefault(month_of(rec["created_at"]), []).append(rec)
                for month, recs in by_month.items():
                    ensure_month_partition(
                        conn, datetime(int(month[:4]), int(month[4:6]), 1, tzinfo=UTC)
                    )
                    prev = last_row_hash(conn, month)
                    if prev is None and not _month_has_rows(conn, month):
                        prev = self._chain_start_hash(conn, month)
                    for rec in recs:
                        event = outbox_row_to_event(rec)
                        event["prev_hash"] = prev
                        event["row_hash"] = compute_row_hash(event, prev)
                        conn.execute(
                            "INSERT INTO audit_events(id, org_id, actor, action,"
                            " target_type, target_id, outcome, request_id, detail_json,"
                            " prev_hash, row_hash, created_at)"
                            " VALUES(%(id)s, %(org_id)s, %(actor)s, %(action)s,"
                            " %(target_type)s, %(target_id)s, %(outcome)s, %(request_id)s,"
                            " %(detail_json)s, %(prev_hash)s, %(row_hash)s, %(created_at)s)"
                            " ON CONFLICT (id, created_at) DO NOTHING",
                            event,
                        )
                        prev = event["row_hash"]
                self._mark_shipped(conn, [r[0] for r in rows], now_ts)
                conn.execute("COMMIT")
            except BaseException:
                self._rollback()
                raise
            total += len(rows)
            if len(rows) < batch:
                break
        return {"shipped": total}

    def _chain_start_hash(self, conn, month: str) -> str | None:
        """月首条 prev = 上月末哈希（向前找最近有行分区——FR-6，跨空月延续）。"""
        from knowledge_lattice.store.audit_chain import prev_month

        from .audit import last_row_hash

        m = prev_month(month)
        for _ in range(120):
            h = last_row_hash(conn, m)
            if h is not None:
                return h
            m = prev_month(m)
        return None

    def _mark_shipped(self, conn, ids: Sequence[str], now: str) -> None:
        """outbox 回填 shipped_at（同事务步——崩溃注入锚点）。"""
        conn.execute(
            "UPDATE audit_outbox SET shipped_at = %(now)s"
            " WHERE id = ANY(%(ids)s) AND shipped_at IS NULL",
            {"now": now, "ids": list(ids)},
        )

    def read_monthly_events(self, *, when: str) -> list[dict]:
        """读指定时点所在月的 audit_events（分区范围查询——m2-3 B2：**链遍历
        序**〔walk_chain 按链重排与逐行哈希验证——G-13 对冲，读序不依赖 seq〕；
        B5：语义列 detail_json 兜底。破链 raise AuditChainError——fail-closed）。"""
        from knowledge_lattice.store.audit_chain import (
            backfill_semantic_cols,
            walk_chain,
        )

        from .audit import month_bounds

        month = when[:4] + when[5:7]
        start, end = month_bounds(month)
        rows = self._conn.execute(
            "SELECT id, org_id, actor, action, target_type, target_id, outcome,"
            " request_id, detail_json, prev_hash, row_hash, created_at"
            " FROM audit_events WHERE created_at >= %(s)s AND created_at < %(e)s",
            {"s": start, "e": end},
        ).fetchall()  # 读序无关（B2——walk_chain 按链重排）
        cols = (
            "id", "org_id", "actor", "action", "target_type", "target_id", "outcome",
            "request_id", "detail_json", "prev_hash", "row_hash", "created_at",
        )
        events = []
        for r in rows:
            d = dict(zip(cols, r))
            if d.get("created_at") is not None:
                d["created_at"] = d["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            events.append(d)
        return [backfill_semantic_cols(e) for e in walk_chain(events)]

    def seal_audit_months(self, *, now: str | None = None) -> dict:
        """封存过月分区：sealed 触发器（拦 INSERT/UPDATE/DELETE——owner 亦拦）+
        记 audit_month_seals（month/last_hash/rows/sealed_at）；仍有未搬运行的
        月份跳过（防「先封存后搬运」写入已封存分区死锁）。"""
        from knowledge_lattice.store.audit_chain import month_of
        from knowledge_lattice.store.taskclock import utc_now_ts

        from .audit import seal_month_partition

        now_ts = now or utc_now_ts()
        from .audit import SEALS_TABLE_DDL

        self._conn.execute(SEALS_TABLE_DDL)  # 幂等——封存记录表（首封前 ensure）
        cur_month = month_of(now_ts)
        already_sealed = {
            r[0]
            for r in self._conn.execute(
                "SELECT month FROM audit_month_seals"
            ).fetchall()
        }
        months = [
            r[0]
            for r in self._conn.execute(
                "SELECT substring(c.relname from 'audit_events_([0-9]{6})$')"
                " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE c.relispartition AND n.nspname = current_schema()"
                "   AND c.relname LIKE 'audit_events_%'"
                " ORDER BY 1"
            ).fetchall()
            if r[0] and r[0] < cur_month and r[0] not in already_sealed
        ]
        sealed: list[str] = []
        skipped: list[str] = []
        for month in months:
            upper = _month_upper(month)
            pending = self._conn.execute(
                "SELECT count(*) FROM audit_outbox"
                " WHERE shipped_at IS NULL AND created_at < %(end)s",
                {"end": upper},
            ).fetchone()[0]
            if pending:
                skipped.append(month)
                continue
            seal_month_partition(self._conn, month)
            sealed.append(month)
        return {"sealed": sealed, "skipped_pending": skipped}

    def prune_audit_months(
        self, *, keep_months: int, now: str | None = None
    ) -> dict:
        """保留期分区删除（DROP 分区表——整文件删除的 PG 等价，TC-OPS-02③）。"""
        from knowledge_lattice.store.audit_chain import month_of, month_shift
        from knowledge_lattice.store.taskclock import utc_now_ts

        from .audit import SEALS_TABLE_DDL, partition_name

        self._conn.execute(SEALS_TABLE_DDL)  # 幂等——prune 清封存记录前 ensure
        now_ts = now or utc_now_ts()
        cutoff = month_shift(month_of(now_ts), -keep_months)
        months = [
            r[0]
            for r in self._conn.execute(
                "SELECT substring(c.relname from 'audit_events_([0-9]{6})$')"
                " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE c.relispartition AND n.nspname = current_schema()"
                "   AND c.relname LIKE 'audit_events_%'"
                " ORDER BY 1"
            ).fetchall()
            if r[0] and r[0] < cutoff
        ]
        for month in months:
            self._conn.execute(f'DROP TABLE IF EXISTS "{partition_name(month)}"')
            self._conn.execute(
                "DELETE FROM audit_month_seals WHERE month = %(m)s", {"m": month}
            )
        return {"pruned": months}

    # ---- 删库 RESTRICT（C 组——T19 半句收口，sqlite 同构） ----

    # ============ 维度治理 + 授权写路径 + 覆盖率（m2-3——TC-OPS-06/07/08/EMB-06） ============

    def _value_row(self, org_id: str, dim_id: str, value_id: str):
        return self._conn.execute(
            "SELECT v.status FROM dimension_values v"
            " JOIN dimensions d ON d.id = v.dimension_id"
            " WHERE v.id = %(vid)s AND d.id = %(dim)s AND d.org_id = %(org)s",
            {"vid": value_id, "dim": dim_id, "org": org_id},
        ).fetchone()

    def dimension_value_impact(
        self, org_id: str, dim_id: str, value_id: str,
    ) -> dict | None:
        """取值停用影响面预估（TC-OPS-07① dry_run 数据源）——只读。
        locked_docs 口径见 sqlite 版 docstring（R2 边界3）。"""
        if self._value_row(org_id, dim_id, value_id) is None:
            return None
        docs = self._conn.execute(
            "SELECT count(DISTINCT dd.doc_id) FROM document_dimensions dd"
            " WHERE dd.value_id = %(vid)s",
            {"vid": value_id},
        ).fetchone()[0]
        grants, users = self._conn.execute(
            "SELECT count(*), count(DISTINCT user_id)"
            " FROM user_dimension_grants WHERE value_id = %(vid)s",
            {"vid": value_id},
        ).fetchone()
        locked = self._conn.execute(
            "SELECT count(DISTINCT dd.doc_id) FROM document_dimensions dd"
            " JOIN dimension_values v ON v.id = dd.value_id"
            " JOIN dimensions d ON d.id = v.dimension_id AND d.org_id = %(org)s"
            " WHERE d.status != 'active' OR v.status != 'active' OR v.id = %(vid)s",
            {"org": org_id, "vid": value_id},
        ).fetchone()[0]
        return {"docs": docs, "grants": grants, "users": users, "locked_docs": locked}

    def disable_dimension_value(
        self, org_id: str, dim_id: str, value_id: str, *,
        dry_run: bool = False,
        audit: tuple[str, str] | None = None,
    ) -> dict | None:
        """取值停用（TC-OPS-07①）：dry_run 只预估；生效=status→disabled
        （幂等零新审计）+ T3 联动 + audit 同事务。"""
        impact = self.dimension_value_impact(org_id, dim_id, value_id)
        if impact is None:
            return None
        if dry_run:
            return {**impact, "applied": False}
        conn = self._conn
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "UPDATE dimension_values SET status = 'disabled'"
                " WHERE id = %(vid)s AND status = 'active'",
                {"vid": value_id},
            )
            if cur.rowcount and audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return {**impact, "applied": True}

    def dimension_retire_impact(self, org_id: str, dim_id: str) -> dict | None:
        """维度退役影响面预估（TC-OPS-07② 二次确认数据源）——只读。"""
        row = self._conn.execute(
            "SELECT status FROM dimensions WHERE id = %(dim)s AND org_id = %(org)s",
            {"dim": dim_id, "org": org_id},
        ).fetchone()
        if row is None:
            return None
        docs = self._conn.execute(
            "SELECT count(DISTINCT dd.doc_id) FROM document_dimensions dd"
            " WHERE dd.dimension_id = %(dim)s",
            {"dim": dim_id},
        ).fetchone()[0]
        grants, values = self._conn.execute(
            "SELECT (SELECT count(*) FROM user_dimension_grants"
            "         WHERE dimension_id = %(dim)s),"
            "       (SELECT count(*) FROM dimension_values"
            "         WHERE dimension_id = %(dim)s AND status = 'active')",
            {"dim": dim_id},
        ).fetchone()
        return {"docs": docs, "grants": grants, "values": values}

    def get_dimension_status(self, org_id: str, dim_id: str) -> str | None:
        """维度生命周期状态（退役端点幂等 409 判据）。"""
        row = self._conn.execute(
            "SELECT status FROM dimensions WHERE id = %(dim)s AND org_id = %(org)s",
            {"dim": dim_id, "org": org_id},
        ).fetchone()
        return row[0] if row else None

    def retire_dimension(
        self, org_id: str, dim_id: str, *,
        audit: tuple[str, str] | None = None,
    ) -> dict | None:
        """维度退役（T20 半句——唯一放宽路径必有审计）：status→retired
        （幂等零新审计）；audit 同事务。"""
        impact = self.dimension_retire_impact(org_id, dim_id)
        if impact is None:
            return None
        conn = self._conn
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "UPDATE dimensions SET status = 'retired', updated_at ="
                " CURRENT_TIMESTAMP WHERE id = %(dim)s AND org_id = %(org)s"
                " AND status = 'active'",
                {"dim": dim_id, "org": org_id},
            )
            if cur.rowcount and audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return impact

    def replace_local_grants(
        self, org_id: str, user_id: str,
        rows: Sequence[tuple[str, str, str | None]], *,
        audit: tuple[str, str] | None = None,
    ) -> dict:
        """用户 local 授权全量替换（TC-OPS-08——sync 行不动；幂等目标全量态）。"""
        conn = self._conn
        resolved: list[tuple[str, str, str | None]] = []
        for dim_key, value, expires_at in rows:
            r = conn.execute(
                "SELECT d.id, v.id FROM dimensions d"
                " JOIN dimension_values v ON v.dimension_id = d.id"
                " WHERE d.org_id = %(org)s AND d.key = %(k)s AND v.value = %(v)s",
                {"org": org_id, "k": dim_key, "v": value},
            ).fetchone()
            if r is None:
                raise KeyError(
                    f"grant target not found in org: {dim_key!r}={value!r}"
                )
            resolved.append((r[0], r[1], expires_at))
        conn.execute("BEGIN")
        try:
            removed = conn.execute(
                "DELETE FROM user_dimension_grants"
                " WHERE user_id = %(uid)s AND source = 'local'"
                "   AND dimension_id IN (SELECT id FROM dimensions"
                "                        WHERE org_id = %(org)s)",
                {"uid": user_id, "org": org_id},
            ).rowcount
            inserted = 0
            for dim_db, val_db, expires_at in resolved:
                conn.execute(
                    "INSERT INTO user_dimension_grants(user_id, dimension_id,"
                    " value_id, source, expires_at) VALUES(%(u)s, %(d)s, %(v)s,"
                    " 'local', %(e)s)",
                    {"u": user_id, "d": dim_db, "v": val_db, "e": expires_at},
                )
                inserted += 1
            if audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return {"removed": removed, "inserted": inserted}

    def list_grants_for_export(self, org_id: str) -> list[dict]:
        """组织全部授权行（CSV 导出 / 差异计算数据源——含 sync 标注）。

        R3 P2-1：expires_at 双方言统一返回**库格式字符串**（pg TIMESTAMP 在
        store 单点归一——diff/export/审计面同源比较，datetime 形态不外泄到
        api 层；created_at 归一先例同款）。"""
        rows = self._conn.execute(
            "SELECT u.username, g.user_id, d.key, v.value, g.expires_at, g.source"
            " FROM user_dimension_grants g"
            " JOIN dimensions d ON d.id = g.dimension_id AND d.org_id = %(org)s"
            " JOIN dimension_values v ON v.id = g.value_id"
            " JOIN users u ON u.id = g.user_id"
            " ORDER BY u.username, d.key, v.value",
            {"org": org_id},
        ).fetchall()
        out = []
        for r in rows:
            expires = r[4]
            if expires is not None and not isinstance(expires, str):
                expires = expires.strftime("%Y-%m-%d %H:%M:%S")  # TIMESTAMP→str
            out.append({
                "username": r[0], "user_id": r[1], "dim_key": r[2],
                "value": r[3], "expires_at": expires, "source": r[5],
            })
        return out

    def find_user_by_username(self, username: str) -> dict | None:
        """username → 用户行（CSV 导入解析）。"""
        row = self._conn.execute(
            "SELECT id, username, is_system_admin, disabled_at FROM users"
            " WHERE username = %(u)s",
            {"u": username},
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "username": row[1], "is_system_admin": row[2],
                "disabled_at": row[3]}

    def embedding_coverage(self, org_id: str, embed_model: str) -> list[dict]:
        """各知识库嵌入覆盖率（TC-EMB-06 只读面板——RUNBOOK §1 闭合口径）。"""
        rows = self._conn.execute(
            "SELECT ds.id, ds.name,"
            " (SELECT count(*) FROM chunks c"
            "   JOIN documents d ON d.id = c.doc_id AND d.active_version = c.version"
            "   WHERE d.dataset_id = ds.id AND d.org_id = %(org)s AND c.tombstone = 0),"
            " (SELECT count(*) FROM chunks c"
            "   JOIN documents d ON d.id = c.doc_id AND d.active_version = c.version"
            "   JOIN chunk_vectors cv ON cv.rid = c.rid AND cv.embed_model = %(model)s"
            "   WHERE d.dataset_id = ds.id AND d.org_id = %(org)s AND c.tombstone = 0)"
            " FROM datasets ds WHERE ds.org_id = %(org)s ORDER BY ds.id",
            {"org": org_id, "model": embed_model},
        ).fetchall()
        return [
            {"dataset_id": r[0], "dataset_name": r[1], "total": r[2], "done": r[3]}
            for r in rows
        ]

    def read_pending_outbox_events(self) -> list[dict]:
        """未搬运 outbox 行（审计分级查询当月未落库部分）。"""
        rows = self._conn.execute(
            "SELECT id, event_type, payload_json, created_at FROM audit_outbox"
            " WHERE shipped_at IS NULL ORDER BY created_at, id"
        ).fetchall()
        cols = ("id", "event_type", "payload_json", "created_at")
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            if d.get("created_at") is not None:
                d["created_at"] = d["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            out.append(d)
        return out

    def read_last_maintenance_stats(self) -> dict | None:
        """最近 maintenance.run 的 stats（B4——outbox 优先、月库兜底；P3-1/R2：
        月库兜底取链序**最后一条**；P3-12/R2：事件名常量）。"""
        import json as _json

        from knowledge_lattice.domain.audit_events import EVENT_MAINTENANCE_RUN

        row = self._conn.execute(
            "SELECT payload_json FROM audit_outbox"
            " WHERE event_type = %(evt)s"
            " ORDER BY created_at DESC, id DESC LIMIT 1",
            {"evt": EVENT_MAINTENANCE_RUN},
        ).fetchone()
        if row is not None:
            try:
                return _json.loads(row[0]).get("stats")
            except (ValueError, AttributeError):
                return None
        from knowledge_lattice.store.taskclock import utc_now_ts

        for event in reversed(self.read_monthly_events(when=utc_now_ts())):
            if event.get("action") == EVENT_MAINTENANCE_RUN and event.get("detail_json"):
                try:
                    return _json.loads(event["detail_json"]).get("stats")
                except (ValueError, AttributeError):
                    return None
        return None

    def delete_dataset(
        self, org_id: str, dataset_id: str,
        audit: tuple[str, str] | None = None,
    ) -> None:
        from knowledge_lattice.store.backend import DatasetNotEmptyError

        row = self._conn.execute(
            "SELECT org_id, (SELECT count(*) FROM documents WHERE dataset_id = %(ds)s)"
            " FROM datasets WHERE id = %(ds)s",
            {"ds": dataset_id},
        ).fetchone()
        if row is None or row[0] != org_id:
            raise KeyError(f"dataset not found in org: {dataset_id!r}")
        if row[1]:
            raise DatasetNotEmptyError(
                f"dataset {dataset_id!r} 仍有 {row[1]} 篇文档——先删文档再删库"
                "（RESTRICT，T19/TC-OPS-04②）"
            )
        conn = self._conn
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "DELETE FROM datasets WHERE id = %(ds)s AND org_id = %(org)s",
                {"ds": dataset_id, "org": org_id},
            )
            if cur.rowcount == 0:
                conn.execute("COMMIT")
                raise KeyError(f"dataset not found in org: {dataset_id!r}")
            if audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise


def _month_upper(month: str) -> str:
    """月排他上界（次月首日 0 点——'YYYY-MM-DD HH:MM:SS'）。"""
    from knowledge_lattice.store.audit_chain import month_shift

    nxt = month_shift(month, 1)
    return f"{nxt[:4]}-{nxt[4:6]}-01 00:00:00"


def _like_escape(text: str) -> str:
    """LIKE 通配转义（%/_/\——配合 ESCAPE '\\' 子句与 sqlite 同语义）。"""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _expand_relations_thin(backend, org_id, seed_ids, rels, *, depth: int) -> dict:
    """expand_relations 薄适配共用体（与 sqlite 同实现）：
    逐 seed 调 sem_expand_graph（rels 双向）后归并去重；truncated 任一命中即真。

    O-2/m2s-3：**nodes 含 seed 本身**（design §5.9 walk CTE depth=0 行——
    种子即第 0 层；M2-S3 实体召回消费方契约）。"""
    merged_nodes: dict[int, dict] = {}
    merged_edges: set[tuple[int, str, int]] = set()
    edge_rows: dict[tuple[int, str, int], dict] = {}
    truncated = False
    rel_list = list(rels)
    seed_rows = backend.sem_entities_by_ids(org_id, list(seed_ids))
    for row in seed_rows:
        merged_nodes[row["id"]] = {
            "id": row["id"], "type": row["type"], "key": row["key"],
            "name": row["name"], "depth": 0,
        }
    for seed in seed_ids:
        graph = backend.sem_expand_graph(
            org_id, seed, outgoing=rel_list, incoming=rel_list,
            depth=depth, fanout_limit=50, node_limit=200,
        )
        truncated = truncated or graph["truncated"]
        for node in graph["nodes"]:
            merged_nodes.setdefault(node["id"], node)
        for edge in graph["edges"]:
            key = (edge["src"], edge["rel"], edge["dst"])
            if key not in merged_edges:
                merged_edges.add(key)
                edge_rows[key] = edge
    return {
        "nodes": list(merged_nodes.values()),
        "edges": list(edge_rows.values()),
        "truncated": truncated,
    }


def _month_has_rows(conn, month: str) -> bool:
    """指定月（'YYYYMM'）分区是否已有 audit_events 行。"""
    from knowledge_lattice.store.postgres.audit import month_bounds

    start, end = month_bounds(month)
    return (
        conn.execute(
            "SELECT 1 FROM audit_events WHERE created_at >= %(s)s AND created_at < %(e)s"
            " LIMIT 1",
            {"s": start, "e": end},
        ).fetchone()
        is not None
    )


def _sem_chunks(seq, n: int):
    """序列定长分片（ANY(%(keys)s) 数组上限治理——语义域批量读写共用）。"""
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _sem_run_dict(cols, row) -> dict:
    """语义行 → dict（stats_json 解析为 dict——REST 查询端点直出）。"""
    d = dict(zip(cols, row))
    try:
        d["stats_json"] = json.loads(d["stats_json"] or "{}")
    except (TypeError, ValueError):
        d["stats_json"] = {}
    return d


