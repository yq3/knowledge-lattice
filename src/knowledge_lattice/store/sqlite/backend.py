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

from knowledge_lattice.store.backend import AclPlan
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

    # ============ Search 域（M0a-3：BM25 单路召回） ============

    def recall_fts(
        self, tokens: list[str], plan: AclPlan, *, top_k: int = 20
    ) -> list[dict]:
        """BM25 召回：tokens → 方言转义（双引号包裹 + 内部转义 + OR）→ MATCH + 完整 ACL 下推。

        bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0) 越小越相关（ASC）；溯源列一次取齐。
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
        return rows

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
            # pending_dims_json → document_dimensions（切换事务内容——首次上传随本事务生效）
            # P3-7：逐值解析须逐行命中——upload 后维度/取值被停用/删除的竞态会令
            # INSERT..SELECT 零行，若不校验即留下「无维度行」文档（空值放行=可见面
            # 扩大）；不符 raise → 整事务回滚（pending_dims_json 保留供重试）
            dims_json = conn.execute(
                "SELECT pending_dims_json FROM documents WHERE id = :doc", {"doc": doc_id}
            ).fetchone()[0]
            if dims_json:
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
        """覆盖上传切换单事务——M1 实装（M0a 首次上传切换在 insert 事务内）。"""
        raise NotImplementedError("覆盖上传版本切换随 M1（TC-VER-04）")

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

    # ============ Audit 域（M0a-3：outbox 写入实装） ============

    def append_outbox(self, event_type: str, payload_json: str) -> None:
        self._conn.execute(
            "INSERT INTO audit_outbox(id, event_type, payload_json)"
            " VALUES(:id, :t, :p)",
            {"id": f"aud_{uuid.uuid4()}", "t": event_type, "p": payload_json},
        )
        self._conn.commit()
