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

import psycopg

from knowledge_lattice.store.backend import AclPlan, VersionConflictError
from knowledge_lattice.store.postgres.audit import ensure_month_partition
from knowledge_lattice.store.postgres.vec import format_vector

__all__ = ["PgBackend"]


class PgBackend:
    """持有单个主库连接的 PostgreSQL 后端（测试/单进程形态；池化随 M1）。"""

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
        raise → 整事务回滚）与 SqliteBackend 逐条同源。
        """
        conn = self._conn
        conn.execute("BEGIN")
        try:
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
                " FOR UPDATE",
                {"doc": doc_id, "expected": expected_pending},
            ).fetchone()
            if row is None:
                raise VersionConflictError(
                    f"switch rejected: doc={doc_id!r} pending_version"
                    f" != {expected_pending}（并发切换/取消？——乐观校验，P0-2.3）"
                )
            old_version = row[0]
            conn.execute(
                "DELETE FROM chunk_vectors"
                " WHERE rid IN (SELECT rid FROM chunks"
                "                WHERE doc_id = %(doc)s AND version = %(old)s)",
                {"doc": doc_id, "old": old_version},
            )
            conn.execute(
                "UPDATE chunks SET tombstone = 1,"
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
                " WHERE id = %(doc)s AND pending_version = %(expected)s",
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
        pending_version: int,
        content_hash: str,
        mime_type: str,
        raw_object_key: str,
        pending_dims_json: str | None,
    ) -> None:
        """覆盖上传开新 pending 版本（写入级防并发——同 sqlite 口径）。"""
        cur = self._conn.execute(
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

    def set_doc_pending_failed(self, doc_id: str, version: int, error: str) -> None:
        """pending 版本失败：failed + pending_error + 立即物理删块——同一事务。"""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            conn.execute(
                "UPDATE documents SET pending_status = 'failed', pending_error = %(err)s,"
                " updated_at = CURRENT_TIMESTAMP"
                " WHERE id = %(doc)s AND pending_version = %(v)s",
                {"err": error, "doc": doc_id, "v": version},
            )
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

    def delete_document(self, doc_id: str) -> None:
        """删除文档（同事务：非终态任务取消 → 级联删文档——TC-VER-07/T19①）。"""
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
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except psycopg.Error:
                pass
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

    def set_document_dims(self, doc_id: str, dims: dict[str, list[str]]) -> None:
        """按 key 全量替换文档维度行（PATCH 落点——与 sqlite 同构）。"""
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
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except psycopg.Error:
                pass
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

    # ============ Admin 域（任务状态机 / 文档状态 / 指纹 / 只读维度取值） ============

    def create_task(self, doc_id: str, *, task_type: str = "ingest") -> str:
        task_id = f"tsk_{uuid.uuid4()}"
        self._conn.execute(
            "INSERT INTO tasks(id, doc_id, type, status)"
            " VALUES(%(id)s, %(doc)s, %(type)s, 'pending')",
            {"id": task_id, "doc": doc_id, "type": task_type},
        )
        return task_id

    def get_task(self, task_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, doc_id, type, status, attempts, error, created_at, updated_at"
            " FROM tasks WHERE id = %(id)s",
            {"id": task_id},
        ).fetchone()
        if row is None:
            return None
        cols = ("id", "doc_id", "type", "status", "attempts", "error", "created_at", "updated_at")
        return dict(zip(cols, row))

    def list_tasks(self, org_id: str, *, doc_id: str | None = None) -> list[dict]:
        sql = (
            "SELECT t.id, t.doc_id, t.type, t.status, t.attempts, t.error,"
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
        cols = ("id", "doc_id", "type", "status", "attempts", "error", "created_at", "updated_at")
        return [dict(zip(cols, r)) for r in rows]

    def update_task(
        self, task_id: str, *, status: str | None = None, error: str | None = None
    ) -> None:
        """状态机推进：pending→leased→running→done|failed（§5.3）；attempts 随 running 递增。"""
        if status == "running":
            self._conn.execute(
                "UPDATE tasks SET status = %(s)s, attempts = attempts + 1,"
                " heartbeat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP"
                " WHERE id = %(id)s",
                {"s": status, "id": task_id},
            )
        elif error is not None or status is not None:
            self._conn.execute(
                "UPDATE tasks SET status = COALESCE(%(s)s, status), error = %(err)s,"
                " updated_at = CURRENT_TIMESTAMP WHERE id = %(id)s",
                {"s": status, "err": error, "id": task_id},
            )

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
    ) -> None:
        """首次上传的文档行（pending_version=1、pending_status='parsing'——§5.3 阶段编排）。"""
        self._conn.execute(
            "INSERT INTO documents(id, org_id, dataset_id, title, source_uri, content_hash,"
            " mime_type, parser, active_version, pending_version, pending_status,"
            " pending_dims_json, owner_user_id, raw_object_key)"
            " VALUES(%(id)s, %(org)s, %(ds)s, %(title)s, %(src)s, %(hash)s, %(mime)s,"
            " %(parser)s, 0, 1, 'parsing', %(dims)s, %(owner)s, %(obj)s)",
            {
                "id": doc_id, "org": org_id, "ds": dataset_id, "title": title, "src": source_uri,
                "hash": content_hash, "mime": mime_type, "parser": parser, "dims": pending_dims_json,
                "owner": owner_user_id, "obj": raw_object_key,
            },
        )

    def set_doc_pending_status(self, doc_id: str, version: int, status: str) -> None:
        self._conn.execute(
            "UPDATE documents SET pending_status = %(s)s, updated_at = CURRENT_TIMESTAMP"
            " WHERE id = %(doc)s AND pending_version = %(v)s",
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
