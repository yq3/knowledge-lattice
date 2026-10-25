"""SQLite 后端——StorageBackend 协议的 SQLite 实现（方法随 M0a-2+ 摄取/检索链逐个实装）。

M0a-2 落 Acl 域（store/backend.py AclBackend）：read_membership / read_grants——
§5.1 第 0/2 步的读取收口（「core 不碰 SQL」，v0.8.3）。授权展开为**单条 SQL**
（同一条语句含三重过滤：active 维度 / active 取值 / 未过期），LEFT JOIN 形态使
无授权的 active 维度也以空集出现在结果里——空授权集 → NotExists 单条件（T22）
依赖此语义。

M0a-3 落：Search.recall_fts（BM25 五列加权 + 完整 ACL 下推）、Ingest.insert
（chunks+FTS+阶段状态+首次上传 D20 切换单事务）、write_embeddings / pending_embeddings
（批次钉标签防护）、Admin（任务状态机 / 文档状态 / 指纹基线 / 维度取值只读）、
Audit.append_outbox。事务纪律：写路径 BEGIN IMMEDIATE 单步短事务（NFR-9）。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Sequence

from knowledge_lattice.store.backend import AclPlan, VersionConflictError
from knowledge_lattice.store.sqlite.fts import build_match_expr
from knowledge_lattice.store.sqlite.vec import pack_f32, unpack_f32

__all__ = ["SqliteBackend", "pack_f32", "unpack_f32"]


class SqliteBackend:
    """持有单个主库连接的 SQLite 后端（线程模型：每线程一连接——design §2）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ============ Acl 域（§5.1 第 0/2 步读取收口） ============

    def read_membership(
        self, user_id: str, org_id: str, *, now: str | None = None
    ) -> dict | None:
        """有效成员关系行（含 `expires_at IS NULL OR expires_at > now` 过滤——第 0 步）。

        无有效行 → None（编译入口拒绝，403 语义）。
        """
        if now is None:
            row = self._conn.execute(
                "SELECT role, expires_at FROM user_org_memberships"
                " WHERE user_id = :uid AND org_id = :org"
                "   AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
                {"uid": user_id, "org": org_id},
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT role, expires_at FROM user_org_memberships"
                " WHERE user_id = :uid AND org_id = :org"
                "   AND (expires_at IS NULL OR expires_at > :now)",
                {"uid": user_id, "org": org_id, "now": now},
            ).fetchone()
        return None if row is None else {"role": row[0], "expires_at": row[1]}

    def read_grants(
        self, user_id: str, org_id: str, *, now: str | None = None
    ) -> dict[str, tuple[str, ...]]:
        """授权展开（第 2 步，单条 SQL）：org 的全部 active 维度 → 有效授权取值集。

        三重过滤（#34 必修 1 / T1 / T3）：dim.status='active'（retired 维度不出现）、
        v.status='active'（停用取值=收紧——视为存在但无人被授予）、
        g.expires_at 过滤（过期即失效，不等清理任务）。无授权的 active 维度以
        空元组出现（→ 渲染为 NotExists 单条件——T22）。

        取值 JOIN 校验 `v.dimension_id = dim.id`（Committer R1 P2-1）：grants 侧无
        trg_docdims_consistency 等价触发器，FK 只保证 value_id 存在——不校验归属时
        畸形授权行（dimension=region、value=tax_type 的 VAT）会跨维度挂取值越权。
        """
        # 仅方言关键字选择（CURRENT_TIMESTAMP / :now），无数据值插值
        now_filter = "CURRENT_TIMESTAMP" if now is None else ":now"
        params: dict[str, object] = {"uid": user_id, "org": org_id}
        if now is not None:
            params["now"] = now
        sql = (
            "SELECT dim.key, v.value"
            " FROM dimensions dim"
            " LEFT JOIN user_dimension_grants g"
            "   ON g.dimension_id = dim.id AND g.user_id = :uid"
            f"  AND (g.expires_at IS NULL OR g.expires_at > {now_filter})"
            " LEFT JOIN dimension_values v"
            "   ON v.id = g.value_id AND v.dimension_id = dim.id AND v.status = 'active'"
            " WHERE dim.org_id = :org AND dim.status = 'active'"
            " ORDER BY dim.key, v.value"
        )
        grants: dict[str, set[str]] = {}
        for dim_key, value in self._conn.execute(sql, params):
            bucket = grants.setdefault(dim_key, set())
            if value is not None:  # 停用取值/无授权 → NULL 行（收紧）
                bucket.add(value)
        return {key: tuple(sorted(values)) for key, values in grants.items()}

    # ============ Search 域（M0a-3：BM25 单路召回；M1-1：向量路 + 名次协议 + 双断言源） ============

    def recall_fts(
        self, tokens: list[str], plan: AclPlan, *, top_k: int = 20
    ) -> list[dict]:
        """BM25 召回：tokens → 方言转义（双引号包裹 + 内部转义 + OR）→ MATCH + 完整 ACL 下推。

        bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0) 越小越相关（ASC）——方向差异在
        本层吸收为名次：行含 rank（1 起，M1-1 名次协议）；score_raw 仅供观察。
        空表达式（tokens 全被过滤）返回 []（空短语部分版本 malformed——TC-FTS-01）。
        dims 溯源字段（§6.1 契约）：v1.1 起 chunks 无 dims_json 投影——召回后按
        doc_id 从 document_dimensions 聚合回填（拍板 3，D22 真相源；SQL 收口本层）。
        """
        from knowledge_lattice.store.sqlite.acl_render import render_fts_recall_select

        match_expr = build_match_expr(tokens)
        if not match_expr:
            return []
        sql, params = render_fts_recall_select(plan, match_expr, top_k=top_k)
        cursor = self._conn.execute(sql, params)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        self._attach_dims(rows)
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank  # 名次协议（v0.8 #42 P1-8）——RRF/归一只消费名次
        return rows

    def recall_vec(
        self, query_vec: list[float], plan: AclPlan, *, top_k: int = 20
    ) -> list[dict]:
        """向量召回（M1-1）：先 ACL 过滤后距离——JOIN chunk_vectors cv（v1.1 谓词：
        cv.embed_model = plan.embed_model，非当前标签行不进距离计算 TC-EMB-02/07）；
        距离 vec_distance_cosine 升序，行含 rank（1 起）与 dist。

        序列化收口本方言侧（pack_f32 BLOB——core 传浮点向量，P2-3 同款纪律）。
        """
        from knowledge_lattice.store.sqlite.acl_render import render_vec_recall_select

        sql, params = render_vec_recall_select(plan, pack_f32(query_vec), top_k=top_k)
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

        rids 非 None 时按给定块集收窄（AND c.rid IN (…)——双断言传候选/top-k 集，
        防宽权限全量扫描；独立 SQL 路径性质不变）。
        """
        from knowledge_lattice.store.sqlite.acl_render import render_select

        sql, params = render_select(plan)
        if rids:
            marks = ", ".join(f":vr{i}" for i in range(len(rids)))
            sql += f" AND c.rid IN ({marks})"
            params.update({f"vr{i}": rid for i, rid in enumerate(rids)})
        return {r[0] for r in self._conn.execute(sql, params)}

    def rids_without_vector(
        self, rids: list[int], embed_model: str
    ) -> set[int]:
        """给定 rid 中无 (rid, embed_model) cv 行的子集（vector_pending 块级判定——
        TC-RET-02「本结果缺向量路＝未就绪或降级」）。空集输入返回空集。"""
        if not rids:
            return set()
        marks = ", ".join(f":r{i}" for i in range(len(rids)))
        params: dict[str, object] = {f"r{i}": rid for i, rid in enumerate(rids)}
        params["label"] = embed_model
        rows = self._conn.execute(
            "SELECT c.rid FROM chunks c"
            f" WHERE c.rid IN ({marks})"
            "   AND NOT EXISTS (SELECT 1 FROM chunk_vectors cv"
            "     WHERE cv.rid = c.rid AND cv.embed_model = :label)",
            params,
        ).fetchall()
        return {r[0] for r in rows}

    def _attach_dims(self, rows: list[dict]) -> None:
        """按 doc_id 聚合 document_dimensions → rows[i]["dims"]（dict[key, list[value]]）。

        单条 IN 查询取回命中文档的全部维度行（top_k ≤20 → doc 数有限）；无维度行
        的文档落 {}（空值放行口径的输出面）。键序按 dim.key 稳定、值序按 v.value。
        """
        doc_ids = sorted({r["doc_id"] for r in rows})
        if not doc_ids:
            return
        marks = ", ".join(f":d{i}" for i in range(len(doc_ids)))
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

    # ============ Ingest 域（M0a-3：chunks+FTS 同事务 / 嵌入回写——v1.1 分表） ============

    _CHUNK_COLS = (
        "id, doc_id, seq, version, content, title_seg, content_seg, token_count,"
        " heading_path, page_no, sheet_name, bbox_json, keywords, llm_keywords, tags"
    )

    def insert(self, doc_id: str, version: int, chunks: list[dict]) -> None:
        """chunks + FTS（触发器同步）+ 阶段状态 + 首次上传 D20 切换——同一事务。

        幂等（TC-ING-07）：同 (doc_id, version) 先删后插（uq_chunks_docver 兜底）；
        pending_dims_json 同事务落 document_dimensions（首次上传切换即生效——设计 §5.3）。
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "DELETE FROM chunks WHERE doc_id = :doc AND version = :v",
                {"doc": doc_id, "v": version},
            )
            for ch in chunks:
                conn.execute(
                    f"INSERT INTO chunks({self._CHUNK_COLS}) VALUES"
                    " (:id, :doc_id, :seq, :version, :content, :title_seg, :content_seg,"
                    " :token_count, :heading_path, :page_no, :sheet_name, :bbox_json,"
                    " :keywords, :llm_keywords, :tags)",
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
                " WHERE id = :doc AND pending_version = :v",
                {"doc": doc_id, "v": version},
            )
            # pending_dims_json → document_dimensions：**仅首次上传**（本次事务
            # 随 D20 切换一并生效）；覆盖上传不在此解析——v2 新维度切换前不生效
            # （P0-2.1/T6），落地收口 switch_active_version 切换事务
            active_row = conn.execute(
                "SELECT active_version FROM documents WHERE id = :doc", {"doc": doc_id}
            ).fetchone()
            if active_row is not None and active_row[0] == 0:
                self._resolve_pending_dims(conn, doc_id)
            # D20 首次上传切换：active_version=0 → 在 searchable_lexical 即刻切在用
            conn.execute(
                "UPDATE documents SET"
                " active_version = pending_version, active_status = 'searchable_lexical',"
                " pending_version = NULL, pending_status = NULL, pending_error = NULL,"
                " page_count = COALESCE(page_count, :page_count), updated_at = CURRENT_TIMESTAMP"
                " WHERE id = :doc AND active_version = 0 AND pending_version = :v",
                {"doc": doc_id, "v": version, "page_count": len({c.get("page_no") for c in chunks})},
            )
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    @staticmethod
    def _resolve_pending_dims(conn, doc_id: str) -> None:
        """pending_dims_json → document_dimensions（同事务；P3-7 逐值命中校验——
        不符 raise 整事务回滚、pending_dims_json 保留供重试）。"""
        dims_json = conn.execute(
            "SELECT pending_dims_json FROM documents WHERE id = :doc", {"doc": doc_id}
        ).fetchone()[0]
        if not dims_json:
            return
        expected = {
            (key, value)
            for key, values in json.loads(dims_json).items()
            for value in values
        }
        inserted = 0
        conn.execute(
            "DELETE FROM document_dimensions WHERE doc_id = :doc", {"doc": doc_id}
        )
        for dim_key, value in expected:
            cur = conn.execute(
                "INSERT INTO document_dimensions(doc_id, dimension_id, value_id)"
                " SELECT :doc, dim.id, v.id FROM dimensions dim"
                " JOIN dimension_values v ON v.dimension_id = dim.id AND v.value = :value"
                " WHERE dim.org_id = (SELECT org_id FROM documents WHERE id = :doc)"
                "   AND dim.key = :key",
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
            "UPDATE documents SET pending_dims_json = NULL WHERE id = :doc",
            {"doc": doc_id},
        )

    def mark_embedding_batch(self, doc_id: str, version: int, batch_label: str) -> list[dict]:
        """批次启动时钉死标签（§5.3）：待嵌块打 embed_model=batch_label 并返回清单。

        v1.1 分表口径（拍板 2）：认领 = 在处理块（tombstone=0）且 chunk_vectors 无
        该 (rid, label) 行（含上次失败中断、已带旧标签的块——重试重钉同标签续跑；
        重嵌入新标签=蓝绿认领同 rid）；已回写/已切换的零触碰。
        """
        rows = self._conn.execute(
            "UPDATE chunks SET embed_model = :label"
            " WHERE doc_id = :doc AND version = :v AND tombstone = 0"
            "   AND NOT EXISTS (SELECT 1 FROM chunk_vectors cv"
            "     WHERE cv.rid = chunks.rid AND cv.embed_model = :label)"
            " RETURNING rid, content",
            {"doc": doc_id, "v": version, "label": batch_label},
        ).fetchall()
        return [{"rid": r[0], "content": r[1]} for r in rows]

    def write_embeddings(
        self, batch_label: str, rows: list[tuple[int, list[float]]]
    ) -> int:
        """逐批回写向量入 chunk_vectors（防护：rid 在批 + tombstone=0 + 标签匹配
        + (rid, label) 无行——PK 冲突即零触碰；同 rid 异标签照常写入=蓝绿并存）。

        P2-3：接收浮点向量、vec_f32 BLOB 序列化收口本方言侧（core 不碰方言）。
        M0a 基础版：版本 IN (:active,:pending) 防护随 M1 版本切换全链（TC-VER-06）——
        首次上传场景 tombstone 防护已足够（无并发切换）。
        """
        written = 0
        for rid, vector in rows:
            cur = self._conn.execute(
                "INSERT INTO chunk_vectors(rid, embed_model, embedding)"
                " SELECT :rid, :label, :vec FROM chunks c"
                " WHERE c.rid = :rid AND c.tombstone = 0 AND c.embed_model = :label"
                " ON CONFLICT(rid, embed_model) DO NOTHING",
                {"vec": pack_f32(vector), "label": batch_label, "rid": rid},
            )
            written += cur.rowcount
        self._conn.commit()
        return written

    def pending_embeddings(self, batch_label: str) -> list[dict]:
        """已钉标签未回写的待嵌入块（断点续跑清单——TC-ING-06 断言细则 M1）。

        v1.1：无行判定 = chunk_vectors 无该 (rid, label) 向量行。"""
        rows = self._conn.execute(
            "SELECT c.rid, c.content FROM chunks c"
            " WHERE c.embed_model = :label AND c.tombstone = 0"
            "   AND NOT EXISTS (SELECT 1 FROM chunk_vectors cv"
            "     WHERE cv.rid = c.rid AND cv.embed_model = :label)"
            " ORDER BY c.rid",
            {"label": batch_label},
        ).fetchall()
        return [{"rid": r[0], "content": r[1]} for r in rows]

    def delete_by_doc(self, doc_id: str, version: int) -> int:
        cur = self._conn.execute(
            "DELETE FROM chunks WHERE doc_id = :doc AND version = :v",
            {"doc": doc_id, "v": version},
        )
        self._conn.commit()
        return cur.rowcount

    def switch_active_version(self, doc_id: str, expected_pending: int) -> None:
        """覆盖上传切换单事务（design §5.3 切换 SQL 逐项——v1.1 拍板②形态）：

        DELETE chunk_vectors 旧行 → 旧块 tombstone=1 + 五列清空（au 触发器清 FTS）
        → documents 五字段更新（WHERE pending_version=:expected 乐观校验，不符
        raise VersionConflictError）→ pending_dims_json 落 document_dimensions。
        中途失败全回滚（TC-VER-04 原子性）。
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT active_version FROM documents"
                " WHERE id = :doc AND pending_version = :expected"
                "   AND pending_status = 'searchable_full'",
                {"doc": doc_id, "expected": expected_pending},
            ).fetchone()
            if row is None:
                raise VersionConflictError(
                    f"switch rejected: doc={doc_id!r} pending_version"
                    f" != {expected_pending} 或未达 searchable_full"
                    "（并发切换/取消？——乐观校验，P0-2.3）"
                )
            old_version = row[0]
            # v1.1 拍板②：删 chunk_vectors 向量行（原 embedding=NULL 的等价迁移）——
            # 显式分表级联兜底，不得回退为置空形态
            conn.execute(
                "DELETE FROM chunk_vectors"
                " WHERE rid IN (SELECT rid FROM chunks"
                "                WHERE doc_id = :doc AND version = :old)",
                {"doc": doc_id, "old": old_version},
            )
            # 旧块标记 + 五列 FTS 内容清空（清空后 au 触发器执行 FTS 'delete' 再插
            # 空行——UPDATE 不触发 ad；FTS 残留空 rowid 不影响 MATCH，#33 P0-2.4/T9）
            conn.execute(
                "UPDATE chunks SET tombstone = 1,"
                " title_seg = '', content_seg = '', keywords = '',"
                " llm_keywords = '', tags = ''"
                " WHERE doc_id = :doc AND version = :old",
                {"doc": doc_id, "old": old_version},
            )
            cur = conn.execute(
                "UPDATE documents SET"
                " active_version = pending_version, active_status = pending_status,"
                # R2 P2-1：成功切换清空 active_error——与 set_doc_active_status
                #（首传路径）同款；成功在用版本不得残留旧版本错误（状态互斥）。
                # design §5.3 切换 SQL 未列该列属设计缺项（口径申报，不写 docs）
                " active_error = NULL,"
                " pending_version = NULL, pending_status = NULL, pending_error = NULL,"
                " updated_at = CURRENT_TIMESTAMP"
                " WHERE id = :doc AND pending_version = :expected"
                "   AND pending_status = 'searchable_full'",
                {"doc": doc_id, "expected": expected_pending},
            )
            if cur.rowcount == 0:  # 事务内二次校验（防御：行在读取后被并发改写）
                raise VersionConflictError(
                    f"switch rejected: doc={doc_id!r} pending_version changed"
                    " mid-transaction（乐观校验零行）"
                )
            # 同事务：v2 新维度落地（P0-2.1——切换前不生效、切换即生效，T6）
            self._resolve_pending_dims(conn, doc_id)
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def max_document_version(self, doc_id: str) -> int:
        """历史最大版本号（active/pending/chunks 三源 max——失败版本号不复用基线）。"""
        row = self._conn.execute(
            "SELECT MAX(m) FROM ("
            "  SELECT active_version AS m FROM documents WHERE id = :doc"
            "  UNION ALL SELECT pending_version FROM documents WHERE id = :doc"
            "  UNION ALL SELECT MAX(version) FROM chunks WHERE doc_id = :doc)",
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
        """覆盖上传开新 pending 版本（不动 active_*——v1 全程服务到切换，D20）。

        WHERE 限定「无在途 pending 或 pending 已 failed」：写入级防并发（服务层
        409 校验已前置，此处为库级兜底——同刻另一 pending 在途时零行 raise）。
        """
        cur = self._conn.execute(
            "UPDATE documents SET"
            " pending_version = :v, pending_status = 'parsing', pending_error = NULL,"
            " pending_dims_json = :dims, content_hash = :hash, mime_type = :mime,"
            " raw_object_key = :obj, updated_at = CURRENT_TIMESTAMP"
            " WHERE id = :doc"
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
        self._conn.commit()

    def set_doc_pending_failed(self, doc_id: str, version: int, error: str) -> None:
        """pending 版本失败：failed + pending_error + 立即物理删除该版本全部块
        （T8——失败不留检索残留）——同一事务。"""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE documents SET pending_status = 'failed', pending_error = :err,"
                " updated_at = CURRENT_TIMESTAMP"
                " WHERE id = :doc AND pending_version = :v",
                {"err": error, "doc": doc_id, "v": version},
            )
            conn.execute(
                "DELETE FROM chunks WHERE doc_id = :doc AND version = :v",
                {"doc": doc_id, "v": version},
            )
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def delete_document(self, doc_id: str) -> None:
        """删除文档（同事务：非终态任务取消 → 级联删文档——TC-VER-07/T19①）。"""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE tasks SET status = 'failed',"
                " error = 'cancelled: document deleted', updated_at = CURRENT_TIMESTAMP"
                " WHERE doc_id = :doc AND status IN ('pending', 'leased', 'running')",
                {"doc": doc_id},
            )
            conn.execute("DELETE FROM documents WHERE id = :doc", {"doc": doc_id})
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def get_document_dims(self, doc_id: str) -> dict[str, list[str]]:
        rows = self._conn.execute(
            "SELECT dim.key, v.value FROM document_dimensions dd"
            " JOIN dimensions dim ON dim.id = dd.dimension_id"
            " JOIN dimension_values v ON v.id = dd.value_id"
            " WHERE dd.doc_id = :doc ORDER BY dim.key, v.value",
            {"doc": doc_id},
        ).fetchall()
        dims: dict[str, list[str]] = {}
        for key, value in rows:
            dims.setdefault(key, []).append(value)
        return dims

    def set_document_dims(self, doc_id: str, dims: dict[str, list[str]]) -> None:
        """按 key 全量替换文档维度行（PATCH 落点——D6 刷维度不重嵌；逐值命中校验
        同 pending_dims 口径，不符 raise 回滚）。"""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            for dim_key, values in dims.items():
                conn.execute(
                    "DELETE FROM document_dimensions WHERE doc_id = :doc"
                    "   AND dimension_id IN (SELECT id FROM dimensions"
                    "       WHERE org_id = (SELECT org_id FROM documents WHERE id = :doc)"
                    "         AND key = :key)",
                    {"doc": doc_id, "key": dim_key},
                )
                for value in values:
                    cur = conn.execute(
                        "INSERT INTO document_dimensions(doc_id, dimension_id, value_id)"
                        " SELECT :doc, dim.id, v.id FROM dimensions dim"
                        " JOIN dimension_values v ON v.dimension_id = dim.id AND v.value = :value"
                        " WHERE dim.org_id = (SELECT org_id FROM documents WHERE id = :doc)"
                        "   AND dim.key = :key",
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
            except sqlite3.Error:
                pass
            raise

    def get_chunk(self, chunk_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT rid, id, doc_id, seq, version, tombstone FROM chunks WHERE id = :id",
            {"id": chunk_id},
        ).fetchone()
        if row is None:
            return None
        return dict(zip(("rid", "id", "doc_id", "seq", "version", "tombstone"), row))

    def fetch_window(self, doc_id: str, version: int, seq_lo: int, seq_hi: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, seq, content, page_no FROM chunks"
            " WHERE doc_id = :doc AND version = :v AND tombstone = 0"
            "   AND seq BETWEEN :lo AND :hi ORDER BY seq",
            {"doc": doc_id, "v": version, "lo": seq_lo, "hi": seq_hi},
        ).fetchall()
        return [
            {"chunk_id": r[0], "seq": r[1], "content": r[2], "page_no": r[3]} for r in rows
        ]

    def visible_doc_ids(self, plan: AclPlan, doc_ids: list[str]) -> set[str]:
        """文档级可见集（visible_docs CTE——fetch 替代提示的文档可见性判定）。"""
        from knowledge_lattice.store.sqlite.acl_render import render_visible_doc_ids

        sql, params = render_visible_doc_ids(plan)
        visible = {r[0] for r in self._conn.execute(sql, params)}
        return visible & set(doc_ids)

    # ============ Quality 域（design §5.4 / FR-3——M1-4） ============
    # 近邻范围铁律：组织内 + 仅在用版本（#33 P1-10）——下方 SQL 的
    # c2.version = d2.active_version AND c2.tombstone = 0 三处一致。

    _ACTIVE_CHUNK_JOIN = (
        " FROM chunks c JOIN documents d ON d.id = c.doc_id"
        " WHERE d.org_id = :org AND c.tombstone = 0"
        "   AND c.version = d.active_version AND d.active_version > 0"
    )

    def neighbor_sims(
        self, rid: int, embed_model: str, *, top_k: int = 8
    ) -> list[dict]:
        """SQL 暴力扫描 top-k 近邻（入库单块路径——§5.4「量小」）：
        自身块定位（含组织归属）→ 同组织在用块同标签距离升序取 k，sim = 1 - 距离。"""
        row = self._conn.execute(
            "SELECT d.org_id FROM chunks c1"
            " JOIN documents d ON d.id = c1.doc_id"
            " JOIN chunk_vectors cv1 ON cv1.rid = c1.rid AND cv1.embed_model = :label"
            " WHERE c1.rid = :rid",
            {"rid": rid, "label": embed_model},
        ).fetchone()
        if row is None:
            return []  # 自身无向量（未嵌入/标签不符）——无近邻语义
        sql = (
            "SELECT c2.rid, c2.id, c2.doc_id,"
            " 1 - vec_distance_cosine(cv2.embedding, :qv) AS sim"
            " FROM chunks c2"
            " JOIN documents d2 ON d2.id = c2.doc_id"
            " JOIN chunk_vectors cv2 ON cv2.rid = c2.rid AND cv2.embed_model = :label"
            " WHERE d2.org_id = :org AND c2.tombstone = 0"
            "   AND c2.version = d2.active_version AND c2.rid != :rid"
            " ORDER BY vec_distance_cosine(cv2.embedding, :qv) ASC"
            " LIMIT :k"
        )
        qv = self._conn.execute(
            "SELECT cv.embedding FROM chunk_vectors cv WHERE cv.rid = :rid"
            " AND cv.embed_model = :label",
            {"rid": rid, "label": embed_model},
        ).fetchone()[0]
        rows = self._conn.execute(
            sql, {"org": row[0], "rid": rid, "label": embed_model, "qv": qv, "k": top_k}
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
        """df：' '||content_seg||' ' 包含 ' '+token+' '（分词以空格连接——边界精确）。"""
        scope = (
            self._ACTIVE_CHUNK_JOIN + " AND instr(' ' || c.content_seg || ' ', ' ' || :tok || ' ') > 0"
            if org_id is not None
            else " FROM chunks c JOIN documents d ON d.id = c.doc_id"
            " WHERE c.tombstone = 0 AND c.version = d.active_version"
            " AND d.active_version > 0"
            " AND instr(' ' || c.content_seg || ' ', ' ' || :tok || ' ') > 0"
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
    ) -> list[tuple[int, list[float]]]:
        rows = self._conn.execute(
            "SELECT c.rid, cv.embedding FROM chunks c"
            " JOIN documents d ON d.id = c.doc_id"
            " JOIN chunk_vectors cv ON cv.rid = c.rid AND cv.embed_model = :label"
            " WHERE d.org_id = :org AND c.tombstone = 0"
            "   AND c.version = d.active_version AND d.active_version > 0",
            {"org": org_id, "label": embed_model},
        ).fetchall()
        return [(r[0], unpack_f32(r[1])) for r in rows]

    def org_active_chunk_segs(self, org_id: str) -> list[str]:
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
        """候选 = 规模比例（detected_at_scale IS NULL 或 < 当前×比例）∪ 确定性抽样
        （(rid×2654435761) % 100 < sample_percent——Knuth 乘法散列，双后端整数
        溢出语义一致：sqlite int64 回绕、pg bigint 回绕，结果同）。"""
        floor = int(current_scale * rescale_ratio)
        sql = (
            "SELECT c.rid, c.id, c.doc_id, c.content, c.content_seg, c.detected_at_scale"
            + self._ACTIVE_CHUNK_JOIN
            + "   AND (c.detected_at_scale IS NULL OR c.detected_at_scale < :floor"
            f"        OR (c.rid * 2654435761) % 100 < {int(sample_percent)})"
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
        conn.execute("BEGIN IMMEDIATE")
        try:
            for rid, sha in marks:
                conn.execute(
                    "UPDATE chunks SET detected_at_scale = :scale,"
                    " content_sha = COALESCE(:sha, content_sha) WHERE rid = :rid",
                    {"scale": scale, "sha": sha, "rid": rid},
                )
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def set_chunk_llm_keywords(self, rid: int, llm_keywords: str) -> None:
        self._conn.execute(
            "UPDATE chunks SET llm_keywords = :kw WHERE rid = :rid",
            {"kw": llm_keywords, "rid": rid},
        )
        self._conn.commit()  # au 触发器同步 FTS（keywords 五列之一）

    def append_chunk_manual_terms(
        self, rid: int, *, keywords: str, tags: str
    ) -> dict:
        """人工词原样追加（空格连接——不进 jieba，TC-FTS-04 纯净性）。"""
        row = self._conn.execute(
            "SELECT keywords, tags FROM chunks WHERE rid = :rid", {"rid": rid}
        ).fetchone()
        if row is None:
            raise KeyError(f"chunk rid not found: {rid}")
        new_kw = (row[0] + " " + keywords).strip() if row[0] else keywords
        new_tags = (row[1] + " " + tags).strip() if row[1] else tags
        self._conn.execute(
            "UPDATE chunks SET keywords = :kw, tags = :tg WHERE rid = :rid",
            {"kw": new_kw, "tg": new_tags, "rid": rid},
        )
        self._conn.commit()  # au 触发器同步 FTS
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
        conn.execute("BEGIN IMMEDIATE")
        try:
            # 重算覆盖语义：同块既有 open flag 一律由本次检测结果替换
            conn.execute(
                "DELETE FROM quality_flags WHERE chunk_id = :chk AND state = 'open'",
                {"chk": chunk_id},
            )
            conn.execute(
                "INSERT INTO quality_flags(id, chunk_id, doc_id, reason, detail_json)"
                " VALUES(:id, :chk, :doc, :reason, :detail)",
                {
                    "id": flag_id, "chk": chunk_id, "doc": doc_id,
                    "reason": reason, "detail": detail_json,
                },
            )
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        return flag_id

    def delete_open_flags(self, rids: Sequence[int], reasons: Sequence[str]) -> int:
        if not rids or not reasons:
            return 0
        rmarks = ", ".join(f":r{i}" for i in range(len(rids)))
        vmarks = ", ".join(f":v{i}" for i in range(len(reasons)))
        params: dict[str, object] = {f"r{i}": rid for i, rid in enumerate(rids)}
        params.update({f"v{i}": reason for i, reason in enumerate(reasons)})
        cur = self._conn.execute(
            f"DELETE FROM quality_flags WHERE state = 'open'"
            f" AND reason IN ({vmarks})"
            f" AND chunk_id IN (SELECT id FROM chunks WHERE rid IN ({rmarks}))",
            params,
        )
        self._conn.commit()
        return cur.rowcount

    def get_quality_flag(self, flag_id: str) -> dict | None:
        row = self._conn.execute(
            f"SELECT {self._QFLAG_COLS} FROM quality_flags WHERE id = :id",
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
            conds.append("doc_id = :doc")
            params["doc"] = doc_id
        if org_id is not None:
            conds.append(
                "doc_id IN (SELECT id FROM documents WHERE org_id = :org)"
            )
            params["org"] = org_id
        if state is not None:
            conds.append("state = :state")
            params["state"] = state
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY created_at, id"
        rows = self._conn.execute(sql, params).fetchall()
        cols = self._QFLAG_COLS.split(", ")
        return [dict(zip(cols, r)) for r in rows]

    def set_quality_auto_keywords(self, flag_id: str, auto_keywords: str) -> None:
        """LLM 兜底一句定位语写 auto_keywords（TC-QUAL-03——与 llm_keywords 同批）。"""
        self._conn.execute(
            "UPDATE quality_flags SET auto_keywords = :ak WHERE id = :id",
            {"ak": auto_keywords, "id": flag_id},
        )
        self._conn.commit()

    def set_quality_flag_state(self, flag_id: str, state: str) -> bool:
        resolved_at = "CURRENT_TIMESTAMP" if state in ("resolved", "ignored") else "NULL"
        cur = self._conn.execute(
            f"UPDATE quality_flags SET state = :s, resolved_at = {resolved_at}"
            " WHERE id = :id",
            {"s": state, "id": flag_id},
        )
        self._conn.commit()
        return cur.rowcount > 0

    def append_quality_manual_tags(self, flag_id: str, manual_json: str) -> None:
        row = self._conn.execute(
            "SELECT manual_tags FROM quality_flags WHERE id = :id", {"id": flag_id}
        ).fetchone()
        if row is None:
            raise KeyError(f"quality flag not found: {flag_id}")
        lines = [x for x in ((row[0] or "").splitlines() + [manual_json]) if x]
        self._conn.execute(
            "UPDATE quality_flags SET manual_tags = :m WHERE id = :id",
            {"m": "\n".join(lines), "id": flag_id},
        )
        self._conn.commit()

    def chunks_by_rids(self, rids: Sequence[int]) -> list[dict]:
        if not rids:
            return []
        marks = ", ".join(f":r{i}" for i in range(len(rids)))
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


    # ============ Admin 域（M0a-3：任务状态机 / 文档状态 / 指纹 / 只读维度取值） ============

    def create_task(self, doc_id: str, *, task_type: str = "ingest") -> str:
        task_id = f"tsk_{uuid.uuid4()}"
        self._conn.execute(
            "INSERT INTO tasks(id, doc_id, type, status) VALUES(:id, :doc, :type, 'pending')",
            {"id": task_id, "doc": doc_id, "type": task_type},
        )
        self._conn.commit()
        return task_id

    def get_task(self, task_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, doc_id, type, status, attempts, error, created_at, updated_at"
            " FROM tasks WHERE id = :id",
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
            " WHERE d.org_id = :org"
        )
        params: dict[str, object] = {"org": org_id}
        if doc_id is not None:
            sql += " AND t.doc_id = :doc"
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
                "UPDATE tasks SET status = :s, attempts = attempts + 1,"
                " heartbeat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP"
                " WHERE id = :id",
                {"s": status, "id": task_id},
            )
        elif error is not None or status is not None:
            self._conn.execute(
                "UPDATE tasks SET status = COALESCE(:s, status), error = :err,"
                " updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                {"s": status, "err": error, "id": task_id},
            )
        self._conn.commit()

    def get_document(self, doc_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, dataset_id, title, source_uri, content_hash, mime_type,"
            " page_count, parser, active_version, active_status, active_error,"
            " pending_version, pending_status, pending_error, pending_dims_json,"
            " owner_user_id, raw_object_key, created_at, updated_at FROM documents WHERE id = :id",
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
            " VALUES(:id, :org, :ds, :title, :src, :hash, :mime, :parser, 0, 1, 'parsing',"
            " :dims, :owner, :obj)",
            {
                "id": doc_id, "org": org_id, "ds": dataset_id, "title": title, "src": source_uri,
                "hash": content_hash, "mime": mime_type, "parser": parser, "dims": pending_dims_json,
                "owner": owner_user_id, "obj": raw_object_key,
            },
        )
        self._conn.commit()

    def set_doc_pending_status(self, doc_id: str, version: int, status: str) -> None:
        self._conn.execute(
            "UPDATE documents SET pending_status = :s, updated_at = CURRENT_TIMESTAMP"
            " WHERE id = :doc AND pending_version = :v",
            {"s": status, "doc": doc_id, "v": version},
        )
        self._conn.commit()

    def set_doc_active_status(self, doc_id: str, version: int, status: str) -> None:
        """推进在用版本状态（embed 完成 → searchable_full）；成功态顺带清 active_error。"""
        self._conn.execute(
            "UPDATE documents SET active_status = :s, active_error = NULL,"
            " updated_at = CURRENT_TIMESTAMP"
            " WHERE id = :doc AND active_version = :v",
            {"s": status, "doc": doc_id, "v": version},
        )
        self._conn.commit()

    def set_doc_active_error(self, doc_id: str, version: int, error: str) -> None:
        self._conn.execute(
            "UPDATE documents SET active_error = :err, updated_at = CURRENT_TIMESTAMP"
            " WHERE id = :doc AND active_version = :v",
            {"err": error, "doc": doc_id, "v": version},
        )
        self._conn.commit()

    def read_fingerprint(self, embed_model: str) -> str | None:
        row = self._conn.execute(
            "SELECT baseline FROM embedding_fingerprints WHERE embed_model = :m",
            {"m": embed_model},
        ).fetchone()
        return None if row is None else row[0]

    def save_fingerprint(self, embed_model: str, baseline_json: str) -> None:
        self._conn.execute(
            "INSERT INTO embedding_fingerprints(embed_model, baseline) VALUES(:m, :b)"
            " ON CONFLICT(embed_model) DO UPDATE SET baseline = :b,"
            " updated_at = CURRENT_TIMESTAMP",
            {"m": embed_model, "b": baseline_json},
        )
        self._conn.commit()

    def list_dimensions(self, org_id: str) -> list[dict]:
        dims = self._conn.execute(
            "SELECT id, key, name, required, enabled FROM dimensions"
            " WHERE org_id = :org AND status = 'active' ORDER BY key",
            {"org": org_id},
        ).fetchall()
        out: list[dict] = []
        for dim_id, key, name, required, enabled in dims:
            values = self._conn.execute(
                "SELECT value, label FROM dimension_values"
                " WHERE dimension_id = :d AND status = 'active' ORDER BY sort_order, value",
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
            "SELECT id, name, description FROM datasets WHERE org_id = :org ORDER BY id",
            {"org": org_id},
        ).fetchall()
        return [{"id": r[0], "name": r[1], "description": r[2]} for r in rows]

    def find_user_by_token_hash(self, token_hash: str) -> dict | None:
        """静态 token 查 user（sha256 形态直查——D18 仅 dev/test）。"""
        row = self._conn.execute(
            "SELECT id, is_system_admin FROM users WHERE token_hash = :h", {"h": token_hash}
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "is_system_admin": bool(row[1])}

    def get_user_auth(self, user_id: str) -> dict | None:
        """认证侧用户态（是否存在 / 是否禁用 / 是否系统管理员）。"""
        row = self._conn.execute(
            "SELECT is_system_admin, disabled_at FROM users WHERE id = :id", {"id": user_id}
        ).fetchone()
        if row is None:
            return None
        return {"is_system_admin": bool(row[0]), "disabled_at": row[1]}

    # ============ 上传凭证（M1-3 三步式——design §6.1/§6.2/§6.3） ============

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
    ) -> None:
        self._conn.execute(
            "INSERT INTO uploads(id, org_id, user_id, service_id, filename, size,"
            " sha256, content_type, status, expires_at)"
            " VALUES(:id, :org, :uid, :svc, :fn, :size, :sha, :ct, 'issued', :exp)",
            {
                "id": upload_id, "org": org_id, "uid": user_id, "svc": service_id,
                "fn": filename, "size": size, "sha": sha256, "ct": content_type,
                "exp": expires_at,
            },
        )
        self._conn.commit()

    def get_upload_credential(self, upload_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, user_id, service_id, filename, size, sha256, content_type,"
            " status, object_key, doc_id, task_id, expires_at, created_at, updated_at"
            " FROM uploads WHERE id = :id",
            {"id": upload_id},
        ).fetchone()
        return None if row is None else dict(zip(self._UPLOAD_COLS, row))

    def mark_upload_uploaded(self, upload_id: str, *, object_key: str) -> bool:
        cur = self._conn.execute(
            "UPDATE uploads SET status='uploaded', object_key=:obj,"
            " updated_at=CURRENT_TIMESTAMP"
            " WHERE id=:id AND status IN ('issued','uploaded')",
            {"id": upload_id, "obj": object_key},
        )
        self._conn.commit()
        return cur.rowcount > 0

    def mark_upload_consumed(self, upload_id: str, *, doc_id: str, task_id: str) -> bool:
        cur = self._conn.execute(
            "UPDATE uploads SET status='consumed', doc_id=:doc, task_id=:task,"
            " updated_at=CURRENT_TIMESTAMP"
            " WHERE id=:id AND status='uploaded'",
            {"id": upload_id, "doc": doc_id, "task": task_id},
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_expired_upload_credentials(self, now: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, object_key FROM uploads"
            " WHERE status IN ('issued','uploaded') AND expires_at <= :now",
            {"now": now},
        ).fetchall()
        return [{"id": r[0], "object_key": r[1]} for r in rows]

    def delete_upload_credential(self, upload_id: str) -> None:
        self._conn.execute("DELETE FROM uploads WHERE id = :id", {"id": upload_id})
        self._conn.commit()

    # ============ Audit 域（M0a-3：outbox 写入实装） ============

    def append_outbox(self, event_type: str, payload_json: str) -> None:
        self._conn.execute(
            "INSERT INTO audit_outbox(id, event_type, payload_json)"
            " VALUES(:id, :t, :p)",
            {"id": f"aud_{uuid.uuid4()}", "t": event_type, "p": payload_json},
        )
        self._conn.commit()
