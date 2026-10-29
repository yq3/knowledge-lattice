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
- **Semantic**：协议种子签名见 store/backend.py（M2-S1 实装）。

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
        raise NotImplementedError("语义关系递归展开随 M2-S1（#42 拍板3）")

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
    ) -> str:
        """target_version（0005/M2.1 R2 边界裁定 B(a)）：ingest 任务的目标文档
        版本——取消与崩溃耗尽清扫按该版本落 pending failed（P2-3）；NULL=无版本
        任务。task_id：预生成 id 显式携带（治理 outbox 事件同源关联——M2.4）。"""
        task_id = task_id or f"tsk_{uuid.uuid4()}"
        self._conn.execute(
            "INSERT INTO tasks(id, doc_id, type, status, target_version)"
            " VALUES(%(id)s, %(doc)s, %(type)s, 'pending', %(tv)s)",
            {"id": task_id, "doc": doc_id, "type": task_type, "tv": target_version},
        )
        return task_id

    def get_task(self, task_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, doc_id, type, status, attempts, error, target_version,"
            " lease_owner, lease_until, heartbeat_at, created_at, updated_at"
            " FROM tasks WHERE id = %(id)s",
            {"id": task_id},
        ).fetchone()
        if row is None:
            return None
        cols = (
            "id", "doc_id", "type", "status", "attempts", "error", "target_version",
            "lease_owner", "lease_until", "heartbeat_at", "created_at", "updated_at",
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
        sql += " ORDER BY t.created_at DESC"
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
            self._conn.execute(
                "UPDATE tasks SET status = %(s)s,"
                " heartbeat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP"
                " WHERE id = %(id)s",
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
                "SELECT value, label FROM dimension_values"
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
                    "values": [{"value": v, "label": l} for v, l in values],
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

    # ============ Semantic 域种子签名（P3-17——实现随 M2-S1 经 semantic/ 迁移落库） ============

    def upsert_entities_batch(self, org_id: str, rows: list[dict]) -> int:
        raise NotImplementedError("semantic 同步分批 upsert 随 M2-S1（D23/§5.8）")

    def advance_status(self, org_id: str, *, missing_before: str) -> dict:
        raise NotImplementedError("semantic missing/retired 推进随 M2-S1（T-S4）")

    def save_build(self, org_id: str, dict_rev: str, stats_json: str) -> int:
        raise NotImplementedError("semantic 构建产物登记随 M2-S1（§5.8）")

    def load_build(self, org_id: str, dict_rev: str) -> dict | None:
        raise NotImplementedError("semantic 构建产物读取随 M2-S1（§5.8）")

    def export_l0(self, org_id: str) -> str:
        raise NotImplementedError("semantic L0 导出随 M2-S1（§6.3）")

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
        """读指定时点所在月的 audit_events（分区范围查询——(created_at,id) 序）。"""
        from .audit import month_bounds, partition_name

        month = when[:4] + when[5:7]
        start, end = month_bounds(month)
        rows = self._conn.execute(
            "SELECT id, org_id, actor, action, target_type, target_id, outcome,"
            " request_id, detail_json, prev_hash, row_hash, created_at"
            " FROM audit_events WHERE created_at >= %(s)s AND created_at < %(e)s"
            " ORDER BY created_at, id",
            {"s": start, "e": end},
        ).fetchall()
        cols = (
            "id", "org_id", "actor", "action", "target_type", "target_id", "outcome",
            "request_id", "detail_json", "prev_hash", "row_hash", "created_at",
        )
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            if d.get("created_at") is not None:
                d["created_at"] = d["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            out.append(d)
        return out

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

