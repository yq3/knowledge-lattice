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
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

from knowledge_lattice.store.backend import AclPlan, VersionConflictError
from knowledge_lattice.store.sqlite.fts import build_match_expr
from knowledge_lattice.store.sqlite.vec import pack_f32, unpack_f32

__all__ = ["SqliteBackend", "pack_f32", "unpack_f32"]


class SqliteBackend:
    """持有单个主库连接的 SQLite 后端（线程模型：每线程一连接——design §2）。"""

    # delete_open_flags 的 rid 分批上限（M1-5：sqlite SQL 参数上限 32766——
    # 预留 reasons 位后 32000 安全；PG 侧同款数值）
    _DELETE_FLAG_BATCH = 32_000

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

        M2.1 并发面收口（事务内 pending 存活复核）：事务开启后重读 pending 行，
        pending_status='failed'（取消/失败已落账）→ raise——防「worker 过边界守卫后、
        取消事务先行提交」窗口里把 failed 版本复活成 searchable_lexical（TC-TASK-03
        竞态半句；BEGIN IMMEDIATE 与 set_doc_pending_failed 串行化）。
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            pending_row = conn.execute(
                "SELECT pending_status FROM documents"
                " WHERE id = :doc AND pending_version = :v",
                {"doc": doc_id, "v": version},
            ).fetchone()
            if pending_row is not None and pending_row[0] == "failed":
                conn.execute("ROLLBACK")
                raise VersionConflictError(
                    f"insert rejected: doc={doc_id!r} v{version} pending 已 failed"
                    "（取消/并发失败先落账——版本亡故不复活，P0-2.3/TC-TASK-03）"
                )
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
            # 空行——UPDATE 不触发 ad；FTS 残留空 rowid 不影响 MATCH，#33 P0-2.4/T9）；
            # tombstoned_at = 90 天物理清理的时点基准（0004/M2.1）
            conn.execute(
                "UPDATE chunks SET tombstone = 1, tombstoned_at = CURRENT_TIMESTAMP,"
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
        content_hash: str,
        mime_type: str,
        raw_object_key: str,
        pending_dims_json: str | None,
        pending_version: int | None = None,
        audit: tuple[str, str] | None = None,
    ) -> int:
        """覆盖上传开新 pending 版本（不动 active_*——v1 全程服务到切换，D20）。

        WHERE 限定「无在途 pending 或 pending 已 failed」：写入级防并发（服务层
        409 校验已前置，此处为库级兜底——同刻另一 pending 在途时零行 raise）。

        pending_version（M2.4 P3-N5 清偿）：缺省 None = **事务内自算**
        max(历史)+1（BEGIN IMMEDIATE 写锁内计算——闭合「服务层 max 读取与写入
        之间」的理论碰撞窗口）；返回实际写入的版本号（调用方 create_task 的
        target_version 同源消费）。

        audit（M2.4 m2-2）：治理事件与版本开启**同一事务**（TC-OPS-01）。
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            if pending_version is None:
                pending_version = self._max_document_version_locked(conn, doc_id) + 1
            cur = conn.execute(
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
            if audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
            return pending_version
        except BaseException:
            self._rollback()
            raise

    def _max_document_version_locked(
        self, conn: sqlite3.Connection, doc_id: str
    ) -> int:
        """写锁内的版本号基线（P3-N5——与 max_document_version 同口径）。"""
        row = conn.execute(
            "SELECT MAX(m) FROM ("
            "  SELECT active_version AS m FROM documents WHERE id = :doc"
            "  UNION ALL SELECT pending_version FROM documents WHERE id = :doc"
            "  UNION ALL SELECT MAX(version) FROM chunks WHERE doc_id = :doc)",
            {"doc": doc_id},
        ).fetchone()
        return row[0] or 0

    def set_doc_pending_failed(self, doc_id: str, version: int, error: str) -> None:
        """pending 版本失败：failed + pending_error + 立即物理删除该版本全部块
        （T8——失败不留检索残留）——同一事务。

        P1-1 守卫（M2.1 R2）：UPDATE 零行（版本已被切换收编为在用 / 被清空 /
        被新版本取代——取消/失败路径在事务外读了 stale pending）时**不删块**直接
        提交返回——防「取消×切换竞态」删掉刚切为在用版本的全部 chunks
        （active_status=searchable_full 但全文零块的数据丢失）。
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE documents SET pending_status = 'failed', pending_error = :err,"
                " updated_at = CURRENT_TIMESTAMP"
                " WHERE id = :doc AND pending_version = :v",
                {"err": error, "doc": doc_id, "v": version},
            )
            if cur.rowcount == 0:
                # 版本已不在 pending 位（切换先行/已清空）——在用块不得触碰
                conn.execute("COMMIT")
                return
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

    def delete_document(
        self, doc_id: str, audit: tuple[str, str] | None = None
    ) -> None:
        """删除文档（同事务：非终态任务取消 → 级联删文档 → outbox 治理事件
        ——TC-VER-07/T19①；audit 同事务为 M2.4 m2-2 收口，原事务外写废除）。"""
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
            " WHERE dd.doc_id = :doc ORDER BY dim.key, v.value",
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
        """按 key 全量替换文档维度行（PATCH 落点——D6 刷维度不重嵌；逐值命中校验
        同 pending_dims 口径，不符 raise 回滚）。audit 同事务（M2.4 m2-2 收口）。"""
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
            if audit is not None:
                self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
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

    def visible_documents(
        self,
        plan: AclPlan,
        *,
        dataset_ids: list[str] | None = None,
        active_status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """按调用者权限的文档清单（M1-5 MCP list_documents 数据源——TC-AZ-02：
        行集经 visible_docs CTE；dims 经 _attach_dims 聚合回填（D22 同源））。"""
        from knowledge_lattice.store.sqlite.acl_render import render_documents_select

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
        """datasets 统计（§6.1：doc_count 按调用者权限计算——不可见文档计入 0）。"""
        from knowledge_lattice.store.sqlite.acl_render import render_dataset_counts_select

        sql, params = render_dataset_counts_select(plan, dataset_ids=dataset_ids)
        return [
            {"id": r[0], "name": r[1], "doc_count": r[2]}
            for r in self._conn.execute(sql, params)
        ]

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
    ) -> Iterator[tuple[int, bytes]]:
        """组织内全部在用块的 (rid, packed float32 bytes)——**惰性流**
        （M1-4 P2-4 / M1-5 改造：cursor 逐行产出、不物化全量行；vec_f32 BLOB
        本即小端 float32 packed 形态，bytes 原样透出——消费侧 np.frombuffer）。"""
        cursor = self._conn.execute(
            "SELECT c.rid, cv.embedding FROM chunks c"
            " JOIN documents d ON d.id = c.doc_id"
            " JOIN chunk_vectors cv ON cv.rid = c.rid AND cv.embed_model = :label"
            " WHERE d.org_id = :org AND c.tombstone = 0"
            "   AND c.version = d.active_version AND d.active_version > 0",
            {"org": org_id, "label": embed_model},
        )
        return ((r[0], bytes(r[1])) for r in cursor)

    def org_active_chunk_segs(self, org_id: str | None) -> list[str]:
        """org_id=None = 全局语料（冷启动重算兜底——P2-1，TC-QUAL-02 同构口径）。"""
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
        """给定块的 open flags 删除（reason 限定）——**rid 分批**（M1-4 P2-4 /
        M1-5：SQL 参数上限 sqlite 32766 / PG 65535，~6.5 万候选单语句超限失败；
        每批 ≤_DELETE_FLAG_BATCH 行参数化删除，计数累加）。"""
        if not rids or not reasons:
            return 0
        deleted = 0
        for start in range(0, len(rids), self._DELETE_FLAG_BATCH):
            batch = rids[start : start + self._DELETE_FLAG_BATCH]
            rmarks = ", ".join(f":r{start + i}" for i in range(len(batch)))
            vmarks = ", ".join(f":v{i}" for i in range(len(reasons)))
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
        self._conn.commit()
        return deleted

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

        task_id（M2.4 m2-2）：预生成 id 显式携带——治理事件的 outbox payload 与
        任务行同源关联（上传/覆盖事件先于 create_task 落 outbox，需预生成）。

        payload（0006/M2-S1）：任务参数 JSON 文本（semantic_sync 携带
        {org, adapter}——executor 分发面读取；NULL=无参数任务）。

        audit（m2s-2，G-16 收口）：(event_type, payload_json) 与任务行**同一
        事务**（BEGIN IMMEDIATE…COMMIT——触发侧两事务崩溃丢审计窗口闭合）。"""
        task_id = task_id or f"tsk_{uuid.uuid4()}"
        if audit is not None:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO tasks(id, doc_id, type, status, target_version,"
                    " payload) VALUES(:id, :doc, :type, 'pending', :tv, :payload)",
                    {"id": task_id, "doc": doc_id, "type": task_type,
                     "tv": target_version, "payload": payload},
                )
                conn.execute(
                    "INSERT INTO audit_outbox(id, event_type, payload_json)"
                    " VALUES(:id, :t, :p)",
                    {"id": f"aud_{uuid.uuid4()}", "t": audit[0], "p": audit[1]},
                )
                conn.execute("COMMIT")
            except BaseException:
                self._rollback()
                raise
            return task_id
        self._conn.execute(
            "INSERT INTO tasks(id, doc_id, type, status, target_version, payload)"
            " VALUES(:id, :doc, :type, 'pending', :tv, :payload)",
            {"id": task_id, "doc": doc_id, "type": task_type, "tv": target_version,
             "payload": payload},
        )
        self._conn.commit()
        return task_id

    def get_task(self, task_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, doc_id, type, status, attempts, error, target_version,"
            " lease_owner, lease_until, heartbeat_at, created_at, updated_at, payload"
            " FROM tasks WHERE id = :id",
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
            " WHERE d.org_id = :org"
        )
        params: dict[str, object] = {"org": org_id}
        if doc_id is not None:
            sql += " AND t.doc_id = :doc"
            params["doc"] = doc_id
        # 次级排序键 id——created_at 秒级并列下的确定性 tiebreak（id 为 ULID
        # 随机非单调、**不保证时间序**——只消除结果不确定性；同秒内「最近」
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

        attempts 随 **claim_next_task 认领**递增（M2.1 口径：一次认领 = 一次执行
        尝试——认领后即崩的窗口也计数，防无限崩溃循环；running 时不再重复计）。

        P2-1 守卫（M2.1 R2）：done 为终态吸收写——仅非终态（pending/leased/
        running）可入 done，已终态（取消 failed / 新持有者已完成）零行生效，
        防在途执行器覆盖取消/新持有者的终态。
        """
        if status == "running":
            # P2-3/R2：running 写入限非终态——取消落账（failed+'cancelled:'）后
            # 在途执行器的 running 写零行生效，防「取消被复活 → 永久滞留 running
            # / 直调跑完写 done」（TC-TASK-03；与 done/第三分支守卫三分支一致）
            self._conn.execute(
                "UPDATE tasks SET status = :s,"
                " heartbeat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP"
                " WHERE id = :id AND status IN ('pending','leased','running')",
                {"s": status, "id": task_id},
            )
        elif status == "done":
            self._conn.execute(
                "UPDATE tasks SET status = 'done', error = NULL,"
                " updated_at = CURRENT_TIMESTAMP"
                " WHERE id = :id AND status IN ('pending','leased','running')",
                {"id": task_id},
            )
        elif error is not None or status is not None:
            # P3-R4-1（m2-1 移交→m2-2）：failed 写入不覆盖取消终态——取消与失败
            # 落账的 µs 窗口里，迟来的执行器失败写不得抹掉 'cancelled:' 语义
            self._conn.execute(
                "UPDATE tasks SET status = COALESCE(:s, status), error = :err,"
                " updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                "   AND NOT (status = 'failed' AND error LIKE :pattern)",
                {"s": status, "err": error, "id": task_id,
                 "pattern": "cancelled:%"},
            )
        self._conn.commit()

    # ---- 任务队列（租约·心跳·认领——M2.1 worker 框架，design §5.3） ----

    def fail_exhausted_tasks(
        self, *, max_attempts: int, now: str | None = None
    ) -> list[dict]:
        """崩溃耗尽清扫（P2-2，M2.1 R2）：租约已过期且 attempts ≥ max 的
        leased/running 任务 → failed + error 原因（worker 反复崩溃后不再滞留
       leased、人工可见；「attempts ≥ 3 转 failed 留人工」的崩溃侧收口）。
        返回被清扫的任务行（含 doc_id/target_version——调用方按 target_version
        落文档侧 pending failed）。"""
        from knowledge_lattice.store.taskclock import utc_now_ts

        now_ts = now or utc_now_ts()
        # P3-N7 节流（m2-1 移交→m2-2）：常态零行时先读后写——不进 UPDATE 写事务
        #（BEGIN/COMMIT 拿写锁的空转开销），有候选才走原子 UPDATE…RETURNING
        probe = self._conn.execute(
            "SELECT 1 FROM tasks WHERE status IN ('leased','running')"
            "   AND attempts >= :max AND lease_until IS NOT NULL AND lease_until <= :now"
            " LIMIT 1",
            {"max": max_attempts, "now": now_ts},
        ).fetchone()
        if probe is None:
            return []
        rows = self._conn.execute(
            "UPDATE tasks SET status = 'failed', lease_owner = NULL, lease_until = NULL,"
            " error = 'attempt limit exceeded (lease expired after ' || attempts"
            "   || ' attempts — worker crash?)', updated_at = :now"
            " WHERE status IN ('leased','running') AND attempts >= :max"
            "   AND lease_until IS NOT NULL AND lease_until <= :now"
            " RETURNING id, doc_id, type, status, attempts, error, target_version",
            {"max": max_attempts, "now": now_ts},
        ).fetchall()
        self._conn.commit()
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
        """原子认领（单语句 UPDATE…WHERE id=(SELECT …)——sqlite 单写序列化下
        第二个并发认领者的子查询在首者提交后重估，不再命中同一行）。

        created_before（P2-7，M2.1 R2）：仅认领 created_at <= 该时点的任务——
        inline 兜底循环用「陈旧任务」口径认领 ingest（投递方 kick 的同步消化
        恒先于循环抢到新任务，保上传时序语义；重启遗留/超量滞留任务照常被领）。
        """
        from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

        now_ts = now or utc_now_ts()
        until = add_seconds(now_ts, lease_s)
        marks = ", ".join(f":t{i}" for i in range(len(task_types)))
        params: dict[str, object] = {
            "w": worker_id, "now": now_ts, "until": until,
            "max": max_attempts, **{f"t{i}": t for i, t in enumerate(task_types)},
        }
        age_filter = " AND created_at <= :cb" if created_before is not None else ""
        if created_before is not None:
            params["cb"] = created_before
        rows = self._conn.execute(
            "UPDATE tasks SET status = 'leased', attempts = attempts + 1,"
            " lease_owner = :w,"
            " lease_until = :until, heartbeat_at = :now, updated_at = :now"
            f" WHERE id = (SELECT id FROM tasks"
            f"   WHERE type IN ({marks}) AND attempts < :max{age_filter}"
            "     AND (status = 'pending'"
            "          OR (status IN ('leased','running')"
            "              AND lease_until IS NOT NULL AND lease_until <= :now))"
            "   ORDER BY created_at, id LIMIT 1)"
            " RETURNING id, doc_id, type, status, attempts, error, target_version,"
            " lease_owner, lease_until, heartbeat_at, created_at, updated_at",
            params,
        ).fetchall()
        self._conn.commit()
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
            "UPDATE tasks SET heartbeat_at = :now, lease_until = :until,"
            " updated_at = :now"
            " WHERE id = :id AND lease_owner = :w AND status IN ('leased','running')",
            {"now": now_ts, "until": add_seconds(now_ts, lease_s), "id": task_id, "w": worker_id},
        )
        self._conn.commit()
        return cur.rowcount == 1

    def cancel_task(
        self, task_id: str, *, reason: str, now: str | None = None,
        audit: tuple[str, str] | None = None,
    ) -> dict | None:
        from knowledge_lattice.store.taskclock import utc_now_ts

        now_ts = now or utc_now_ts()
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE tasks SET status = 'failed', error = :reason, lease_owner = NULL,"
                " lease_until = NULL, updated_at = :now"
                " WHERE id = :id AND status IN ('pending','leased','running')",
                {"reason": reason, "now": now_ts, "id": task_id},
            )
            cancelled = cur.rowcount > 0
            if cancelled and audit is not None:
                # 治理事件与取消**同一事务**（仅取消实际生效时记——TC-OPS-01）
                self._outbox_insert(conn, *audit)
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
            " WHERE expires_at IS NOT NULL AND expires_at <= :now",
            {"now": now or utc_now_ts()},
        )
        self._conn.commit()
        return cur.rowcount  # trg_membership_delete_cleanup 级联清授权（§5.1）

    def delete_aged_tombstones(self, *, before_ts: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM chunks WHERE tombstone = 1 AND tombstoned_at IS NOT NULL"
            " AND tombstoned_at <= :before",
            {"before": before_ts},
        )
        self._conn.commit()
        return cur.rowcount  # chunk_vectors FK CASCADE + chunks_ad 触发器清 FTS

    def trim_finished_tasks(
        self, *, keep_days: int, keep_count: int, task_type: str = "maintenance",
        now: str | None = None,
    ) -> int:
        from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

        now_ts = now or utc_now_ts()
        cutoff = add_seconds(now_ts, -keep_days * 86400)
        terminal = "type = :ty AND status IN ('done','failed')"
        cur = self._conn.execute(
            f"DELETE FROM tasks WHERE {terminal} AND updated_at < :cutoff",
            {"ty": task_type, "cutoff": cutoff},
        )
        removed = cur.rowcount
        cur = self._conn.execute(
            f"DELETE FROM tasks WHERE {terminal} AND id NOT IN ("
            f"  SELECT id FROM tasks WHERE {terminal}"
            f"  ORDER BY updated_at DESC LIMIT :keep)",
            {"ty": task_type, "keep": max(keep_count, 0)},
        )
        removed += cur.rowcount
        self._conn.commit()
        return removed

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
        audit: tuple[str, str] | None = None,
    ) -> None:
        """首次上传的文档行（pending_version=1、pending_status='parsing'——§5.3 阶段编排）。

        audit（M2.4 m2-2）：(event_type, payload_json)——治理事件与文档行
        **同一事务**写 audit_outbox（「业务改了就一定有审计」，TC-OPS-01）。
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO documents(id, org_id, dataset_id, title, source_uri, content_hash,"
                " mime_type, parser, active_version, pending_version, pending_status,"
                " pending_dims_json, owner_user_id, raw_object_key)"
                " VALUES(:id, :org, :ds, :title, :src, :hash, :mime, :parser, 0, 1, 'parsing',"
                " :dims, :owner, :obj)",
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
        # 取消/失败先行落账后，在途执行器的状态推进零行生效（防复活）
        self._conn.execute(
            "UPDATE documents SET pending_status = :s, updated_at = CURRENT_TIMESTAMP"
            " WHERE id = :doc AND pending_version = :v"
            "   AND (pending_status IS NULL OR pending_status != 'failed')",
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
                "SELECT id, value, label FROM dimension_values"
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
                    "values": [{"id": i, "value": v, "label": l} for i, v, l in values],
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
        audit: tuple[str, str] | None = None,
    ) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO uploads(id, org_id, user_id, service_id, filename, size,"
                " sha256, content_type, status, expires_at)"
                " VALUES(:id, :org, :uid, :svc, :fn, :size, :sha, :ct, 'issued', :exp)",
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

    def mark_upload_consumed(
        self, upload_id: str, *, doc_id: str, task_id: str,
        audit: tuple[str, str] | None = None,
    ) -> bool:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE uploads SET status='consumed', doc_id=:doc, task_id=:task,"
                " updated_at=CURRENT_TIMESTAMP"
                " WHERE id=:id AND status='uploaded'",
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
            " WHERE status IN ('issued','uploaded') AND expires_at <= :now",
            {"now": now},
        ).fetchall()
        return [{"id": r[0], "object_key": r[1]} for r in rows]

    def delete_upload_credential(self, upload_id: str) -> None:
        self._conn.execute("DELETE FROM uploads WHERE id = :id", {"id": upload_id})
        self._conn.commit()

    # ============ Audit 域（M0a-3：outbox 写入实装；M2.4 m2-2：同事务接入 + 搬运/封存/保留） ============

    def _rollback(self) -> None:
        """事务回滚（SQLite 可能已自动回滚——失败不得覆盖原始异常）。"""
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    def _outbox_insert(self, conn: sqlite3.Connection, event_type: str, payload_json: str) -> None:
        """outbox 行插入（**参与调用方事务**——不自行 commit；TC-OPS-01 崩溃
        注入测试的锚点方法：此步抛错 → 调用方业务写一并回滚）。"""
        conn.execute(
            "INSERT INTO audit_outbox(id, event_type, payload_json)"
            " VALUES(:id, :t, :p)",
            {"id": f"aud_{uuid.uuid4()}", "t": event_type, "p": payload_json},
        )

    def append_outbox(self, event_type: str, payload_json: str) -> None:
        self._conn.execute(
            "INSERT INTO audit_outbox(id, event_type, payload_json)"
            " VALUES(:id, :t, :p)",
            {"id": f"aud_{uuid.uuid4()}", "t": event_type, "p": payload_json},
        )
        self._conn.commit()

    def roll_monthly(self, when: object | None = None) -> object:
        """审计月库滚动（当月库 ensure——连接工厂同款幂等；方言差异包内吸收）。"""
        from datetime import UTC, datetime

        from .audit import ensure_monthly_audit

        when_dt = when if isinstance(when, datetime) else None
        return ensure_monthly_audit(self._db_dir(), when_dt)

    # ---- 备份快照（D 组——NFR-10 / TC-OPS-05；方言差异包内吸收） ----

    def backup_snapshot(
        self, backup_dir, objects_dir=None, *, when=None, dsn: str | None = None,
    ) -> dict:
        """VACUUM INTO 主库快照 + objects 目录 tar + 审计月库 tar（m2-3 B3——
        store/sqlite/backup.py）。"""
        from .backup import snapshot as _snapshot

        when_dt = when if isinstance(when, datetime) else None
        return _snapshot(
            self._conn, Path(backup_dir),
            Path(objects_dir) if objects_dir is not None else None, when=when_dt,
            db_dir=self._db_dir(),
        )

    def trim_shipped_outbox(self, *, before_ts: str) -> int:
        """已搬运 outbox 行保留期清理（R2 P3-1——只删 shipped_at 非 NULL 且
        早于 before_ts 的行；未搬运行永不删——「业务改了就一定有审计」的
        未落地承诺）。返回删除行数。"""
        cur = self._conn.execute(
            "DELETE FROM audit_outbox"
            " WHERE shipped_at IS NOT NULL AND shipped_at < :before",
            {"before": before_ts},
        )
        self._conn.commit()
        return cur.rowcount

    def _db_dir(self) -> Path:
        """主库目录（PRAGMA database_list 的主库文件路径——月库与主库同目录）。"""
        for _seq, name, file in self._conn.execute("PRAGMA database_list").fetchall():
            if name == "main" and file:
                return Path(file).parent
        raise RuntimeError("main database has no file path（:memory: 不支持月库）")

    # ---- 搬运（A2：outbox → 月库 audit_events + 回填 shipped_at——TC-OPS-01） ----

    def ship_outbox(self, *, now: str | None = None, batch: int = 500) -> dict:
        """搬运待搬运行到月库 audit_events（按事件原时刻 created_at 路由月份，
        含哈希链逐行计算——FR-6），并回填 shipped_at。

        SQLite 跨文件无原子多库事务（WAL 模式 super-journal 不可用）——两步
        崩溃安全形态：①月库 INSERT OR IGNORE（幂等）→ ②主库回填 shipped_at。
        中断重跑：月库去重 + 回填补齐（at-least-once + 幂等 = 不丢不重）。
        """
        from knowledge_lattice.store.audit_chain import (
            compute_row_hash,
            month_of,
            outbox_row_to_event,
        )
        from knowledge_lattice.store.taskclock import utc_now_ts

        from .audit import chain_start_hash, ensure_monthly_audit, last_row_hash

        now_ts = now or utc_now_ts()
        db_dir = self._db_dir()
        cols = ("id", "event_type", "payload_json", "created_at")
        total = 0
        while True:
            rows = self._conn.execute(
                "SELECT id, event_type, payload_json, created_at FROM audit_outbox"
                " WHERE shipped_at IS NULL ORDER BY created_at, id LIMIT :n",
                {"n": batch},
            ).fetchall()
            if not rows:
                break
            # 按事件月份分组插入（批内 (created_at,id) 序迭代——写入追加到月库
            # rowid 序尾部，链序=插入序自洽；P2-2/R2：**已落库行不重算不推进**
            # ——崩溃重试（月库已插、回填未做）时批内仍含已存行，对其重算会把
            # prev 污染成错误值，同月后续新事件必断链；已存行直接跳过、prev 保
            # 持月库真实末行（rowid 序）即可正确衔接）
            by_month: dict[str, list[dict]] = {}
            for r in rows:
                rec = dict(zip(cols, r))
                by_month.setdefault(month_of(rec["created_at"]), []).append(rec)
            for month, recs in by_month.items():
                when_dt = datetime(
                    int(month[:4]), int(month[4:6]), 1, tzinfo=UTC
                )
                mpath = ensure_monthly_audit(db_dir, when_dt)
                mconn = sqlite3.connect(mpath)
                try:
                    mconn.execute("PRAGMA busy_timeout = 5000")
                    # P2-2：搬运前取本月已存在 id→row_hash（重试路径跳过依据）
                    existed = {
                        x[0]: x[1]
                        for x in mconn.execute(
                            "SELECT id, row_hash FROM audit_events"
                        ).fetchall()
                    }
                    prev = last_row_hash(db_dir, month)
                    if prev is None and not existed:
                        # 月库空：首条 prev = 上月末哈希（FR-6——跨空月向前找）
                        prev = chain_start_hash(db_dir, month)
                    for rec in recs:
                        if rec["id"] in existed:
                            continue  # P2-2：已落库行——不重算不推进（防 prev 污染）
                        event = outbox_row_to_event(rec)
                        event["prev_hash"] = prev
                        event["row_hash"] = compute_row_hash(event, prev)
                        mconn.execute(
                            "INSERT OR IGNORE INTO audit_events(id, org_id, actor,"
                            " action, target_type, target_id, outcome, request_id,"
                            " detail_json, prev_hash, row_hash, created_at)"
                            " VALUES(:id, :org_id, :actor, :action, :target_type,"
                            " :target_id, :outcome, :request_id, :detail_json,"
                            " :prev_hash, :row_hash, :created_at)",
                            event,
                        )
                        prev = event["row_hash"]
                    mconn.commit()
                finally:
                    mconn.close()
            # ②主库回填（中断重跑由 shipped_at IS NULL + 月库 IGNORE 收敛）
            self._mark_shipped(self._conn, [r[0] for r in rows], now_ts)
            total += len(rows)
            if len(rows) < batch:
                break
        return {"shipped": total}

    def _mark_shipped(
        self, conn: sqlite3.Connection, ids: Sequence[str], now: str
    ) -> None:
        """outbox 回填 shipped_at（崩溃注入锚点——中断重跑幂等收敛的②步）。"""
        marks = ", ".join(f":i{n}" for n in range(len(ids)))
        conn.execute(
            f"UPDATE audit_outbox SET shipped_at = :now"
            f" WHERE id IN ({marks}) AND shipped_at IS NULL",
            {"now": now, **{f"i{n}": i for n, i in enumerate(ids)}},
        )
        conn.commit()

    def read_monthly_events(self, *, when: str) -> list[dict]:
        """读指定时点所在月的 audit_events（m2-3 B2：**链遍历序**——按
        prev_hash→row_hash 衔接与逐行哈希验证〔walk_chain——G-13 对冲，读序
        不依赖 rowid/seq〕；B5：语义列 detail_json 兜底。破链 raise
        AuditChainError——fail-closed）。月库不存在 → []（读路径不建库）。"""
        from knowledge_lattice.store.audit_chain import (
            backfill_semantic_cols,
            month_of,
            walk_chain,
        )

        from .audit import month_path, open_monthly_ro

        path = month_path(self._db_dir(), month_of(when))
        if not path.is_file():
            return []
        conn = open_monthly_ro(path)
        try:
            rows = conn.execute(
                "SELECT id, org_id, actor, action, target_type, target_id, outcome,"
                " request_id, detail_json, prev_hash, row_hash, created_at"
                " FROM audit_events"
            ).fetchall()  # 读序无关（B2——walk_chain 按链重排）
        finally:
            conn.close()
        cols = (
            "id", "org_id", "actor", "action", "target_type", "target_id", "outcome",
            "request_id", "detail_json", "prev_hash", "row_hash", "created_at",
        )
        events = [dict(zip(cols, r)) for r in rows]
        return [backfill_semantic_cols(e) for e in walk_chain(events)]

    # ---- 封存 / 保留期（B 组——TC-OPS-02） ----

    def seal_audit_months(self, *, now: str | None = None) -> dict:
        """封存所有已过月的未封存月库（记末哈希 + 0444 只读）；仍有未搬运行
        （事件 created_at 落该月且 shipped_at IS NULL）的月份跳过——留待下轮
        搬运后再封（防「先封存后搬运」写入已封存月库的死锁）。"""
        from knowledge_lattice.store.audit_chain import month_of
        from knowledge_lattice.store.taskclock import utc_now_ts

        from .audit import month_path, read_seal, seal_monthly_audit

        now_ts = now or utc_now_ts()
        cur_month = month_of(now_ts)
        sealed: list[str] = []
        skipped: list[str] = []
        for db_file in sorted(self._db_dir().glob("audit_*.db")):
            stem = db_file.stem
            month = stem[6:]
            if not stem.startswith("audit_") or not month.isdigit():
                continue
            if month >= cur_month or read_seal(self._db_dir(), month) is not None:
                continue  # 当月不封 / 已封存幂等跳过
            # 排他上界 = 次月首日（created_at < upper 即该月事件）
            upper = _month_upper(month)
            pending = self._conn.execute(
                "SELECT count(*) FROM audit_outbox"
                " WHERE shipped_at IS NULL AND created_at < :end",
                {"end": upper},
            ).fetchone()[0]
            if pending:
                skipped.append(month)
                continue
            seal_monthly_audit(self._db_dir(), month)
            sealed.append(month)
        return {"sealed": sealed, "skipped_pending": skipped}

    def prune_audit_months(
        self, *, keep_months: int, now: str | None = None
    ) -> dict:
        """保留期整文件删除（默认 12 个月——TC-OPS-02③）。"""
        from knowledge_lattice.store.audit_chain import month_of
        from knowledge_lattice.store.taskclock import utc_now_ts

        from .audit import prune_monthly_audit

        now_ts = now or utc_now_ts()
        removed = prune_monthly_audit(
            self._db_dir(), keep_months=keep_months, now_month=month_of(now_ts)
        )
        return {"pruned": removed}

    # ---- 删库 RESTRICT（C 组——T19 半句收口，TC-OPS-04②③） ----

    def delete_dataset(
        self, org_id: str, dataset_id: str,
        audit: tuple[str, str] | None = None,
    ) -> None:
        """删除知识库（§6.2 服务层流程）：**仍有文档 → DatasetNotEmptyError
        （RESTRICT 明确语义——非裸外键异常，T19 半句收口/TC-OPS-04②）**；
        无文档 → 删行（audit 治理事件同事务）；不存在/跨组织 → KeyError（404）。"""
        from knowledge_lattice.store.backend import DatasetNotEmptyError

        row = self._conn.execute(
            "SELECT org_id, (SELECT count(*) FROM documents WHERE dataset_id = :ds)"
            " FROM datasets WHERE id = :ds",
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
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "DELETE FROM datasets WHERE id = :ds AND org_id = :org",
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

    # ============ 维度治理 + 授权写路径 + 覆盖率（m2-3——TC-OPS-06/07/08/EMB-06） ============

    def _value_row(self, org_id: str, dim_id: str, value_id: str):
        """取值行定位（org 归属经 dimension 校验——跨组织/不存在 → None）。"""
        return self._conn.execute(
            "SELECT v.status FROM dimension_values v"
            " JOIN dimensions d ON d.id = v.dimension_id"
            " WHERE v.id = :vid AND d.id = :dim AND d.org_id = :org",
            {"vid": value_id, "dim": dim_id, "org": org_id},
        ).fetchone()

    def dimension_value_impact(
        self, org_id: str, dim_id: str, value_id: str,
    ) -> dict | None:
        """取值停用影响面预估（TC-OPS-07① dry_run 数据源）——只读。

        locked_docs（R2 边界3——v1.6.3「维度写锁项」显式化）：组织内引用了
        **非 active 取值（含本次将停用值——dry_run 预估确认后状态）或 retired
        维度取值**的文档数——这些文档的 PATCH/覆盖上传与 _require_values_in_grants
        同锁（文档级、跨维度；恢复路径=重新启用取值）。"""
        if self._value_row(org_id, dim_id, value_id) is None:
            return None
        docs = self._conn.execute(
            "SELECT count(DISTINCT dd.doc_id) FROM document_dimensions dd"
            " WHERE dd.value_id = :vid",
            {"vid": value_id},
        ).fetchone()[0]
        grants, users = self._conn.execute(
            "SELECT count(*), count(DISTINCT user_id)"
            " FROM user_dimension_grants WHERE value_id = :vid",
            {"vid": value_id},
        ).fetchone()
        locked = self._conn.execute(
            "SELECT count(DISTINCT dd.doc_id) FROM document_dimensions dd"
            " JOIN dimension_values v ON v.id = dd.value_id"
            " JOIN dimensions d ON d.id = v.dimension_id AND d.org_id = :org"
            " WHERE d.status != 'active' OR v.status != 'active' OR v.id = :vid",
            {"org": org_id, "vid": value_id},
        ).fetchone()[0]
        return {"docs": docs, "grants": grants, "users": users, "locked_docs": locked}

    def disable_dimension_value(
        self, org_id: str, dim_id: str, value_id: str, *,
        dry_run: bool = False,
        audit: tuple[str, str] | None = None,
    ) -> dict | None:
        """取值停用（TC-OPS-07①）：dry_run 只预估；生效=status→disabled
        （幂等）+ T3 联动（read_grants 既有过滤）+ audit 同事务。"""
        impact = self.dimension_value_impact(org_id, dim_id, value_id)
        if impact is None:
            return None
        if dry_run:
            return {**impact, "applied": False}
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE dimension_values SET status = 'disabled'"
                " WHERE id = :vid AND status = 'active'",
                {"vid": value_id},
            )
            # 幂等：已 disabled 零行——不重复审计（cur.rowcount==0 时仍可能首次
            # 生效路径外的重放，审计只随实际变更行走）
            if cur.rowcount:
                if audit is not None:
                    self._outbox_insert(conn, *audit)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return {**impact, "applied": True}

    def dimension_retire_impact(self, org_id: str, dim_id: str) -> dict | None:
        """维度退役影响面预估（TC-OPS-07② 二次确认数据源）——只读。"""
        row = self._conn.execute(
            "SELECT status FROM dimensions WHERE id = :dim AND org_id = :org",
            {"dim": dim_id, "org": org_id},
        ).fetchone()
        if row is None:
            return None
        docs = self._conn.execute(
            "SELECT count(DISTINCT dd.doc_id) FROM document_dimensions dd"
            " WHERE dd.dimension_id = :dim",
            {"dim": dim_id},
        ).fetchone()[0]
        grants, values = self._conn.execute(
            "SELECT (SELECT count(*) FROM user_dimension_grants"
            "         WHERE dimension_id = :dim),"
            "       (SELECT count(*) FROM dimension_values"
            "         WHERE dimension_id = :dim AND status = 'active')",
            {"dim": dim_id},
        ).fetchone()
        return {"docs": docs, "grants": grants, "values": values}

    def get_dimension_status(self, org_id: str, dim_id: str) -> str | None:
        """维度生命周期状态（退役端点幂等 409 判据）。"""
        row = self._conn.execute(
            "SELECT status FROM dimensions WHERE id = :dim AND org_id = :org",
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
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE dimensions SET status = 'retired', updated_at ="
                " CURRENT_TIMESTAMP WHERE id = :dim AND org_id = :org"
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
        """用户 local 授权全量替换（TC-OPS-08——sync 行不动；幂等目标全量态）。
        rows=(dim_key, value, expires_at)；解析失败 → KeyError（400 语义）。"""
        conn = self._conn
        resolved: list[tuple[str, str, str | None]] = []
        for dim_key, value, expires_at in rows:
            r = conn.execute(
                "SELECT d.id, v.id FROM dimensions d"
                " JOIN dimension_values v ON v.dimension_id = d.id"
                " WHERE d.org_id = :org AND d.key = :k AND v.value = :v",
                {"org": org_id, "k": dim_key, "v": value},
            ).fetchone()
            if r is None:
                raise KeyError(
                    f"grant target not found in org: {dim_key!r}={value!r}"
                )
            resolved.append((r[0], r[1], expires_at))
        conn.execute("BEGIN IMMEDIATE")
        try:
            removed = conn.execute(
                "DELETE FROM user_dimension_grants"
                " WHERE user_id = :uid AND source = 'local'"
                "   AND dimension_id IN (SELECT id FROM dimensions"
                "                        WHERE org_id = :org)",
                {"uid": user_id, "org": org_id},
            ).rowcount
            inserted = 0
            for dim_db, val_db, expires_at in resolved:
                conn.execute(
                    "INSERT INTO user_dimension_grants(user_id, dimension_id,"
                    " value_id, source, expires_at) VALUES(?, ?, ?, 'local', ?)",
                    (user_id, dim_db, val_db, expires_at),
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
        """组织全部授权行（CSV 导出 / 差异计算数据源——含 sync 标注）。"""
        rows = self._conn.execute(
            "SELECT u.username, g.user_id, d.key, v.value, g.expires_at, g.source"
            " FROM user_dimension_grants g"
            " JOIN dimensions d ON d.id = g.dimension_id AND d.org_id = :org"
            " JOIN dimension_values v ON v.id = g.value_id"
            " JOIN users u ON u.id = g.user_id"
            " ORDER BY u.username, d.key, v.value",
            {"org": org_id},
        ).fetchall()
        return [
            {"username": r[0], "user_id": r[1], "dim_key": r[2], "value": r[3],
             "expires_at": r[4], "source": r[5]}
            for r in rows
        ]

    def find_user_by_username(self, username: str) -> dict | None:
        """username → 用户行（CSV 导入解析）。"""
        row = self._conn.execute(
            "SELECT id, username, is_system_admin, disabled_at FROM users"
            " WHERE username = :u",
            {"u": username},
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "username": row[1], "is_system_admin": row[2],
                "disabled_at": row[3]}

    def embedding_coverage(self, org_id: str, embed_model: str) -> list[dict]:
        """各知识库嵌入覆盖率（TC-EMB-06 只读面板——RUNBOOK §1 闭合口径：
        分子/分母都限在用块 tombstone=0 且 version=active_version）。"""
        rows = self._conn.execute(
            "SELECT ds.id, ds.name,"
            " (SELECT count(*) FROM chunks c"
            "   JOIN documents d ON d.id = c.doc_id AND d.active_version = c.version"
            "   WHERE d.dataset_id = ds.id AND d.org_id = :org AND c.tombstone = 0),"
            " (SELECT count(*) FROM chunks c"
            "   JOIN documents d ON d.id = c.doc_id AND d.active_version = c.version"
            "   JOIN chunk_vectors cv ON cv.rid = c.rid AND cv.embed_model = :model"
            "   WHERE d.dataset_id = ds.id AND d.org_id = :org AND c.tombstone = 0)"
            " FROM datasets ds WHERE ds.org_id = :org ORDER BY ds.id",
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
        return [dict(zip(cols, r)) for r in rows]

    def read_last_maintenance_stats(self) -> dict | None:
        """最近 maintenance.run 的 stats（B4——outbox 优先、月库兜底；P3-1/R2：
        月库兜底取链序**最后一条**〔"最近一次"语义〕；P3-12/R2：事件名常量）。"""
        import json as _json

        from knowledge_lattice.domain.audit_events import EVENT_MAINTENANCE_RUN

        row = self._conn.execute(
            "SELECT payload_json FROM audit_outbox"
            " WHERE event_type = :evt"
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

    # ============ Semantic 域（M2-S1——design §4/§5.8；sync 分批 upsert / 状态推进 / run 记录） ============

    _SEM_IN_CHUNK = 500      # IN (...) 参数分片上限（预读/批量 UPDATE 用）

    def upsert_entities_batch(self, org_id: str, rows: Sequence[dict]) -> dict:
        """同步实体分批 upsert——单批单事务（BEGIN IMMEDIATE 短事务，NFR-9/11）。

        只写事实列（name/attrs_json/parent_id/status/synced_at——从不写
        curated_json，T-S1 列级分工）；rows 按父先子后有序；parent_id 解析三级——批内 id 映射 / 批间缓存 /
        库内回查（跨批已提交父行——P2-1 修复：快照超 batch_rows 不再丢父）。updated 计数只看事实列变更
        与状态回归 active（synced_at 刷新不计入——T-S3）。row 可带 ``source``
        （缺省 'sync'——yaml 纯人工实体 'curated'，§5.8；source 不随后续
        sync 源更新漂移）。名称变更后刷新 FTS 文本行（C.3）。
        """
        conn = self._conn
        existing = self._sem_read_existing(
            org_id, [(r["type"], r["key"]) for r in rows]
        )
        inserted = updated = 0
        touched: list[int] = []
        conn.execute("BEGIN IMMEDIATE")
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
                        "UPDATE sem_entities SET name = :name, attrs_json = :attrs,"
                        " parent_id = :parent, source_system = :srcsys,"
                        " status = 'active', synced_at = :ts, updated_at = CURRENT_TIMESTAMP"
                        " WHERE org_id = :org AND type = :type AND key = :key",
                        {"name": row["name"], "attrs": row["attrs_json"],
                         "parent": parent_id, "srcsys": row["source_system"],
                         "ts": row["synced_at"], "org": org_id,
                         "type": row["type"], "key": row["key"]},
                    )
                    if old_name != row["name"]:
                        touched.append(id_map[key])
                else:
                    cur = conn.execute(
                        "INSERT INTO sem_entities(org_id, type, key, name, parent_id,"
                        " attrs_json, source, source_system, status, synced_at)"
                        " VALUES(:org, :type, :key, :name, :parent, :attrs,"
                        " :source, :srcsys, 'active', :ts)",
                        {"org": org_id, "type": row["type"], "key": row["key"],
                         "name": row["name"], "parent": parent_id,
                         "attrs": row["attrs_json"], "source": row_source,
                         "srcsys": row["source_system"], "ts": row["synced_at"]},
                    )
                    id_map[key] = cur.lastrowid
                    touched.append(cur.lastrowid)
                    inserted += 1
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        if touched:
            self.sem_refresh_search_texts(org_id, touched)
        return {"inserted": inserted, "updated": updated}

    def _sem_parent_id(self, org_id, parent_key, id_map: dict, parent_cache: dict):
        """parent_key "type:key" → id（P2-1 三级解析）：批内已落父行（id_map，
        事务内本连接可见）→ 批间缓存 → **库内回查**（跨批已提交父行——快照超
        batch_rows 时父行在前批、子行在后批，只靠批内映射必丢）；悬挂父缓存
        None 防重复回查。"""
        if not parent_key or ":" not in parent_key:
            return None
        ptype, _, pkey = parent_key.partition(":")
        pk = (ptype, pkey)
        if pk in id_map:
            return id_map[pk]
        if pk not in parent_cache:
            row = self._conn.execute(
                "SELECT id FROM sem_entities"
                " WHERE org_id = :org AND type = :type AND key = :key",
                {"org": org_id, "type": pk[0], "key": pk[1]},
            ).fetchone()
            parent_cache[pk] = row[0] if row else None
        return parent_cache[pk]

    def _sem_read_existing(self, org_id: str, keys) -> dict:
        """批内 (type,key) 预读：{(type,key): (id, name, attrs_json, parent_id, status)}。"""
        by_type: dict[str, list[str]] = {}
        for t, k in keys:
            by_type.setdefault(t, []).append(k)
        out: dict[tuple[str, str], tuple] = {}
        for t, ks in by_type.items():
            for chunk in _sem_chunks(ks, self._SEM_IN_CHUNK):
                marks = ",".join("?" for _ in chunk)
                for r in self._conn.execute(
                    f"SELECT id, key, name, attrs_json, parent_id, status"
                    f" FROM sem_entities WHERE org_id = ? AND type = ? AND key IN ({marks})",
                    (org_id, t, *chunk),
                ):
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
                marks = ",".join("?" for _ in chunk)
                for r in self._conn.execute(
                    f"SELECT id, key FROM sem_entities"
                    f" WHERE org_id = ? AND type = ? AND key IN ({marks})",
                    (org_id, t, *chunk),
                ):
                    out[(t, r[1])] = r[0]
        return out

    def sem_active_source_keys(
        self, org_id: str, source_system: str
    ) -> set[tuple[str, str]]:
        """删除比例保护基数（m2s-3 起 per-source_system 收口——yaml 纯人工
        实体 source='curated' 同入基数面，T-S2 对 yaml 源同样成立）。"""
        rows = self._conn.execute(
            "SELECT type, key FROM sem_entities"
            " WHERE org_id = ? AND source_system = ?"
            "   AND status = 'active'",
            (org_id, source_system),
        )
        return {(r[0], r[1]) for r in rows}

    def sem_source_fill_stats(self, org_id: str, source_system: str) -> dict:
        """维度携带统计（attrs_json.dims 非空 = filled——骤降告警库内基线）。"""
        row = self._conn.execute(
            "SELECT count(*), coalesce(sum("
            "  CASE WHEN json_extract(attrs_json, '$.dims') IS NOT NULL THEN 1 ELSE 0 END"
            "), 0) FROM sem_entities"
            " WHERE org_id = ? AND source_system = ?"
            "   AND status = 'active'",
            (org_id, source_system),
        ).fetchone()
        return {"total": row[0], "filled": row[1]}

    def sem_entity_states(self, org_id: str, entity_ids: Sequence[int]) -> dict[int, dict]:
        """批量实体态（status/source——G-15 端点过滤与合并冲突判定共用）。"""
        out: dict[int, dict] = {}
        for chunk in _sem_chunks(list(entity_ids), self._SEM_IN_CHUNK):
            marks = ",".join("?" for _ in chunk)
            for r in self._conn.execute(
                f"SELECT id, status, source FROM sem_entities"
                f" WHERE org_id = ? AND id IN ({marks})",
                (org_id, *chunk),
            ):
                out[r[0]] = {"status": r[1], "source": r[2]}
        return out

    def sem_entities_by_ids(self, org_id: str, entity_ids: Sequence[int]) -> list[dict]:
        """批量实体行（O-2 expand_relations seed 节点信息面）。"""
        out: list[dict] = []
        for chunk in _sem_chunks(list(entity_ids), self._SEM_IN_CHUNK):
            marks = ",".join("?" for _ in chunk)
            out.extend(
                self._sem_entity_row(r) for r in self._conn.execute(
                    f"SELECT id, org_id, type, key, name, parent_id, attrs_json,"
                    f" curated_json, source, source_system, status, sensitivity,"
                    f" synced_at, curated_rev FROM sem_entities"
                    f" WHERE org_id = ? AND id IN ({marks}) ORDER BY id",
                    (org_id, *chunk),
                )
            )
        return out

    def mark_entities_missing(self, org_id: str, entity_ids: Sequence[int]) -> int:
        if not entity_ids:
            return 0
        n = 0
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            for chunk in _sem_chunks(list(entity_ids), self._SEM_IN_CHUNK):
                marks = ",".join("?" for _ in chunk)
                cur = conn.execute(
                    f"UPDATE sem_entities SET status = 'missing',"
                    f" updated_at = CURRENT_TIMESTAMP"
                    f" WHERE org_id = ? AND status = 'active' AND id IN ({marks})",
                    (org_id, *chunk),
                )
                n += cur.rowcount
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return n

    def upsert_relations_batch(self, org_id: str, rows: Sequence[dict]) -> dict:
        """关系分批 upsert（端点不可变——既有行只更新 attrs/status/synced_at）。

        row 可带 ``source``（'sync' 缺省 / 'curated'——yaml 人工补关系）与
        ``source_system``（G-15 关系级 per-adapter 作用域）。G-15 端点状态
        过滤（defense in depth——core 预过滤为主）：UPDATE 仅在两端点 active
        时置回 active；INSERT 端点非 active 时以 'missing' 落库（端点恢复后
        下轮 upsert 置回）——指向 retired 端点的关系不回 active。
        """
        conn = self._conn
        marks_counts: dict[tuple, str] = {}
        conn.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                k = (row["src_id"], row["rel_type"], row["dst_id"])
                old = conn.execute(
                    "SELECT attrs_json, status FROM sem_relations"
                    " WHERE org_id = ? AND src_id = ? AND rel_type = ? AND dst_id = ?",
                    (org_id, *k),
                ).fetchone()
                if old is None:
                    conn.execute(
                        "INSERT INTO sem_relations(org_id, src_id, rel_type, dst_id,"
                        " attrs_json, source, source_system, status, synced_at)"
                        " VALUES(:org, :src, :rel, :dst, :attrs, :source, :srcsys,"
                        "  CASE WHEN EXISTS(SELECT 1 FROM sem_entities s"
                        "       WHERE s.id = :src AND s.org_id = :org AND s.status = 'active')"
                        "        AND EXISTS(SELECT 1 FROM sem_entities d"
                        "       WHERE d.id = :dst AND d.org_id = :org AND d.status = 'active')"
                        "   THEN 'active' ELSE 'missing' END, :ts)",
                        {"org": org_id, "src": k[0], "rel": k[1], "dst": k[2],
                         "attrs": row["attrs_json"],
                         "source": row.get("source") or "sync",
                         "srcsys": row.get("source_system"),
                         "ts": row["synced_at"]},
                    )
                    marks_counts[k] = "i"
                else:
                    if old[0] != row["attrs_json"] or old[1] != "active":
                        marks_counts[k] = "u"
                    else:
                        marks_counts[k] = "s"
                    conn.execute(
                        "UPDATE sem_relations SET attrs_json = :attrs,"
                        " status = CASE WHEN"
                        "   EXISTS(SELECT 1 FROM sem_entities s"
                        "     WHERE s.id = :src AND s.org_id = :org AND s.status = 'active')"
                        "   AND EXISTS(SELECT 1 FROM sem_entities d"
                        "     WHERE d.id = :dst AND d.org_id = :org AND d.status = 'active')"
                        " THEN 'active' ELSE status END,"
                        " synced_at = :ts"
                        " WHERE org_id = :org AND src_id = :src AND rel_type = :rel"
                        "   AND dst_id = :dst",
                        {"attrs": row["attrs_json"], "ts": row["synced_at"],
                         "org": org_id, "src": k[0], "rel": k[1], "dst": k[2]},
                    )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return {
            "inserted": sum(1 for v in marks_counts.values() if v == "i"),
            "updated": sum(1 for v in marks_counts.values() if v == "u"),
        }

    def sem_active_source_relation_keys(
        self, org_id: str, source_system: str
    ) -> set[tuple[int, str, int]]:
        """本源 active 关系键集（G-15 关系级消失检测的库内侧）。"""
        return {
            (r[0], r[1], r[2]) for r in self._conn.execute(
                "SELECT src_id, rel_type, dst_id FROM sem_relations"
                " WHERE org_id = ? AND source_system = ? AND status = 'active'",
                (org_id, source_system),
            )
        }

    def sem_mark_relations_missing(
        self, org_id: str, keys: Sequence[tuple[int, str, int]]
    ) -> int:
        """快照消失的关系 → missing（G-15——synced_at 保留为宽限期起算锚）。"""
        n = 0
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            for chunk in _sem_chunks(list(keys), self._SEM_IN_CHUNK):
                for src_id, rel, dst_id in chunk:
                    cur = conn.execute(
                        "UPDATE sem_relations SET status = 'missing'"
                        " WHERE org_id = ? AND src_id = ? AND rel_type = ?"
                        "   AND dst_id = ? AND status = 'active'",
                        (org_id, src_id, rel, dst_id),
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
                " WHERE org_id = ? AND src_id = ? AND rel_type = ? AND dst_id = ?",
                (org_id, src_id, rel, dst_id),
            ).fetchone()
            if row is not None:
                out[(src_id, rel, dst_id)] = {"source": row[0], "status": row[1]}
        return out

    def rebuild_sync_aliases(self, org_id: str, rows: Sequence[dict]) -> int:
        """别名三 kind 重建：单事务先删后插（manual/abbr 原样——TC-SYNC-05）；
        重建后刷新 FTS 文本行（C.3——别名面即索引面）。"""
        conn = self._conn
        ids = self.resolve_entity_ids(
            org_id, [(r["type"], r["key"]) for r in rows]
        )
        inserted = 0
        conn.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                eid = ids.get((row["type"], row["key"]))
                if eid is None:
                    continue  # 实体不在库（理论上不可达——upsert 先行）
                conn.execute(
                    "DELETE FROM sem_aliases WHERE org_id = ? AND entity_id = ?"
                    "   AND kind IN ('name', 'code', 'sync')",
                    (org_id, eid),
                )
                for alias, alias_norm, kind in row["aliases"]:
                    conn.execute(
                        "INSERT INTO sem_aliases(org_id, entity_id, alias, alias_norm, kind)"
                        " VALUES(?, ?, ?, ?, ?)",
                        (org_id, eid, alias, alias_norm, kind),
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
        """宽限期推进：超期（synced_at < missing_before）missing 实体 → retired
        且其 active 关系一并 retired（T-S4③）；**关系级 missing 同口推进**
        （G-15——源端独立删边、两端实体仍在的关系超宽限 → retired，
        ``relations_retired_standalone`` 单列计数）。

        推进口径（P3-8）：**org 全量推进、不按 source_system 收口**——多适配器
        共享同一时间窗（任一 run 的 advance 均推进全 org 的超期 missing）；
        本段接受口径，按源收口待多适配器时间窗分叉需要时再议。"""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            retired_ids = [
                r[0] for r in conn.execute(
                    "SELECT id FROM sem_entities"
                    " WHERE org_id = ? AND status = 'missing' AND synced_at < ?",
                    (org_id, missing_before),
                )
            ]
            relations_retired = 0
            for chunk in _sem_chunks(retired_ids, self._SEM_IN_CHUNK):
                marks = ",".join("?" for _ in chunk)
                conn.execute(
                    f"UPDATE sem_entities SET status = 'retired',"
                    f" updated_at = CURRENT_TIMESTAMP"
                    f" WHERE org_id = ? AND id IN ({marks})",
                    (org_id, *chunk),
                )
                cur = conn.execute(
                    # 级联覆盖 active + missing（G-15：missing 潜伏关系随端点
                    # retired 一并收口，不留孤儿潜伏行）
                    f"UPDATE sem_relations SET status = 'retired'"
                    f" WHERE org_id = ? AND status IN ('active', 'missing')"
                    f"   AND (src_id IN ({marks}) OR dst_id IN ({marks}))",
                    (org_id, *chunk, *chunk),
                )
                relations_retired += cur.rowcount
            # G-15 关系级宽限推进：两端实体仍在、关系自身超宽限的 missing 行
            relations_retired_standalone = conn.execute(
                "UPDATE sem_relations SET status = 'retired'"
                " WHERE org_id = ? AND status = 'missing' AND synced_at < ?",
                (org_id, missing_before),
            ).rowcount
            missing_now = conn.execute(
                "SELECT count(*) FROM sem_entities"
                " WHERE org_id = ? AND status = 'missing'",
                (org_id,),
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
        cur = self._conn.execute(
            "INSERT INTO sem_sync_runs(org_id, adapter, started_at, status)"
            " VALUES(?, ?, ?, 'running')",
            (org_id, adapter, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def sem_finish_run(
        self, org_id: str, run_id: int, *, status: str, stats_json: str,
        error: str | None = None, now: str | None = None,
    ) -> None:
        self._conn.execute(
            "UPDATE sem_sync_runs SET status = ?, stats_json = ?, error = ?,"
            " finished_at = COALESCE(?, CURRENT_TIMESTAMP)"
            " WHERE id = ? AND org_id = ?",
            (status, stats_json, error, now, run_id, org_id),
        )
        self._conn.commit()

    def sem_list_sync_runs(
        self, org_id: str, *, limit: int = 50,
        adapter: str | None = None, status: str | None = None,
    ) -> list[dict]:
        cols = ("id", "org_id", "adapter", "started_at", "finished_at",
                "status", "stats_json", "error")
        sql = ("SELECT id, org_id, adapter, started_at, finished_at, status,"
               " stats_json, error FROM sem_sync_runs WHERE org_id = ?")
        params: list[object] = [org_id]
        if adapter is not None:
            sql += " AND adapter = ?"
            params.append(adapter)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [_sem_run_dict(cols, r) for r in rows]

    def sem_list_builds(
        self, org_id: str, *, limit: int = 200, status: str | None = None,
    ) -> list[dict]:
        cols = ("id", "org_id", "dict_rev", "yaml_rev", "sync_run_id",
                "status", "stats_json", "created_at")
        sql = ("SELECT id, org_id, dict_rev, yaml_rev, sync_run_id, status,"
               " stats_json, created_at FROM sem_builds WHERE org_id = ?")
        params: list[object] = [org_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [_sem_run_dict(cols, r) for r in rows]

    def sem_get_build(self, org_id: str, build_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, dict_rev, yaml_rev, sync_run_id, status, stats_json,"
            " created_at FROM sem_builds WHERE org_id = ? AND id = ?",
            (org_id, build_id),
        ).fetchone()
        if row is None:
            return None
        cols = ("id", "org_id", "dict_rev", "yaml_rev", "sync_run_id",
                "status", "stats_json", "created_at")
        return _sem_run_dict(cols, row)

    def sem_current_build(self, org_id: str) -> dict | None:
        """当前构建 = 最新 ready 行（G-18/m2s-3：按 (activated_at, id) DESC——
        rev 回退重激活的行 activated_at 被顶置、current 跟随不失真；design
        §4 CHECK 枚举无 superseded，旧 ready 保留服务〔§5.8 懒加载语义〕）。"""
        row = self._conn.execute(
            "SELECT id, org_id, dict_rev, yaml_rev, sync_run_id, status, stats_json,"
            " created_at, activated_at FROM sem_builds WHERE org_id = ?"
            " AND status = 'ready'"
            " ORDER BY (activated_at IS NULL), activated_at DESC, id DESC LIMIT 1",
            (org_id,),
        ).fetchone()
        if row is None:
            return None
        cols = ("id", "org_id", "dict_rev", "yaml_rev", "sync_run_id",
                "status", "stats_json", "created_at", "activated_at")
        return _sem_run_dict(cols, row)

    def sem_active_snapshot(self, org_id: str) -> dict:
        """构建输入快照（§5.8 第 1 步——active 实体（含 curated_json/curated_rev
        ——G-17：YAML 改 definition 必触发重建）+ 全部别名 + active 关系，
        稳定序输出供 dict_rev 哈希）。"""
        entities = [
            {"id": r[0], "type": r[1], "key": r[2], "name": r[3],
             "parent_id": r[4], "attrs_json": r[5], "sensitivity": r[6],
             "curated_json": r[7] or "{}", "curated_rev": r[8]}
            for r in self._conn.execute(
                "SELECT id, type, key, name, parent_id, attrs_json, sensitivity,"
                " curated_json, curated_rev"
                " FROM sem_entities WHERE org_id = ? AND status = 'active'"
                " ORDER BY id", (org_id,),
            )
        ]
        aliases = [
            {"entity_id": r[0], "alias": r[1], "alias_norm": r[2], "kind": r[3],
             "match_mode": r[4], "weight": r[5]}
            for r in self._conn.execute(
                "SELECT a.entity_id, a.alias, a.alias_norm, a.kind, a.match_mode,"
                " a.weight FROM sem_aliases a"
                " JOIN sem_entities e ON e.id = a.entity_id"
                " WHERE a.org_id = ? AND e.status = 'active'"
                " ORDER BY a.entity_id, a.alias_norm", (org_id,),
            )
        ]
        relations = [
            {"src_id": r[0], "rel_type": r[1], "dst_id": r[2],
             "attrs_json": r[3], "source": r[4]}
            for r in self._conn.execute(
                "SELECT src_id, rel_type, dst_id, attrs_json, source"
                " FROM sem_relations WHERE org_id = ? AND status = 'active'"
                " ORDER BY src_id, rel_type, dst_id", (org_id,),
            )
        ]
        return {"entities": entities, "aliases": aliases, "relations": relations}

    def sem_insert_build(
        self, org_id: str, dict_rev: str, stats_json: str, *,
        yaml_rev: str | None = None, sync_run_id: int | None = None,
    ) -> tuple[int, bool]:
        """building 行 upsert（UNIQUE(org,dict_rev)——失败行同 rev 重试复用行）。

        O-1/m2s-3 条件 upsert：``DO UPDATE … WHERE status != 'ready'``——同 rev
        行已 ready 时不重断 building（无 flap/双 ready 事件），返回
        ``(existing_id, True)`` 交由调用方走重激活/让位路径；正常路径返回
        ``(build_id, False)``。
        """
        cur = self._conn.execute(
            "INSERT INTO sem_builds(org_id, dict_rev, yaml_rev, sync_run_id,"
            " status, stats_json) VALUES(?, ?, ?, ?, 'building', ?)"
            " ON CONFLICT(org_id, dict_rev) DO UPDATE SET"
            "   status = 'building', stats_json = excluded.stats_json,"
            "   yaml_rev = excluded.yaml_rev, sync_run_id = excluded.sync_run_id,"
            "   activated_at = NULL"
            " WHERE sem_builds.status != 'ready'"
            " RETURNING id",
            (org_id, dict_rev, yaml_rev, sync_run_id, stats_json),
        )
        row = cur.fetchone()
        self._conn.commit()
        if row is not None:
            return row[0], False
        existing = self._conn.execute(
            "SELECT id FROM sem_builds WHERE org_id = ? AND dict_rev = ?",
            (org_id, dict_rev),
        ).fetchone()
        return existing[0], True

    def sem_reactivate_build(
        self, org_id: str, build_id: int, stats_json: str, *,
        audit: tuple[str, str] | None = None,
    ) -> bool:
        """G-18 rev 回退重激活：ready 行顶置 activated_at 成为 current（+ready
        事件同事务）；仅 status='ready' 行生效（幂等防线）。activated_at 取
        max(现在, 本 org 既有最大 + 1s)——TIMESTAMP 秒级精度下同秒切换/重激活
        的并列由严格递增保证 current 跟随重激活行（id 序在此场景与激活序相反）。"""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE sem_builds SET activated_at = ("
                "  SELECT MAX(v) FROM ("
                "    SELECT CURRENT_TIMESTAMP AS v"
                "    UNION ALL"
                "    SELECT datetime(MAX(b.activated_at), '+1 second') AS v"
                "      FROM sem_builds b WHERE b.org_id = :org"
                "  )"
                "), stats_json = :stats"
                " WHERE org_id = :org AND id = :bid AND status = 'ready'",
                {"stats": stats_json, "org": org_id, "bid": build_id},
            )
            effective = cur.rowcount == 1
            if effective and audit is not None:
                conn.execute(
                    "INSERT INTO audit_outbox(id, event_type, payload_json)"
                    " VALUES(:id, :t, :p)",
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
        """原子切换：building → ready（activated_at 顶置——G-18 current 锚；
        P3-4/R2：与重激活同款**严格递增** max(now, 本 org 最大+1s)——TIMESTAMP
        秒级精度下，重激活顶置的未来时间戳不得压住同秒窗口内后续 switch 的
        current 跟随）+ ready 事件同一事务（P3-5/R2——audit 仅 rowcount==1 真生效
        时写；并发输者零行生效零事件，P2-2）。"""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE sem_builds SET status = 'ready', stats_json = :stats,"
                " activated_at = ("
                "  SELECT MAX(v) FROM ("
                "    SELECT CURRENT_TIMESTAMP AS v"
                "    UNION ALL"
                "    SELECT datetime(MAX(b.activated_at), '+1 second') AS v"
                "      FROM sem_builds b WHERE b.org_id = :org"
                "  )"
                ")"
                " WHERE org_id = :org AND id = :bid AND status = 'building'",
                {"stats": stats_json, "org": org_id, "bid": build_id},
            )
            effective = cur.rowcount == 1
            if effective and audit is not None:
                conn.execute(
                    "INSERT INTO audit_outbox(id, event_type, payload_json)"
                    " VALUES(:id, :t, :p)",
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
        """失败收尾：building → failed + failed 事件同一事务；仅真生效返回 True
        （已终态行幂等零生效——P2-2/R2 防脏 failed 审计）。"""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE sem_builds SET status = 'failed', stats_json = ?"
                " WHERE org_id = ? AND id = ? AND status = 'building'",
                (stats_json, org_id, build_id),
            )
            effective = cur.rowcount == 1
            if effective and audit is not None:
                conn.execute(
                    "INSERT INTO audit_outbox(id, event_type, payload_json)"
                    " VALUES(:id, :t, :p)",
                    {"id": f"aud_{uuid.uuid4()}", "t": audit[0], "p": audit[1]},
                )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return effective

    def save_build(self, org_id: str, dict_rev: str, stats_json: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO sem_builds(org_id, dict_rev, stats_json, status)"
            " VALUES(?, ?, ?, 'building')",
            (org_id, dict_rev, stats_json),
        )
        self._conn.commit()
        return cur.lastrowid

    def load_build(self, org_id: str, dict_rev: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, dict_rev, yaml_rev, sync_run_id, status, stats_json,"
            " created_at FROM sem_builds WHERE org_id = ? AND dict_rev = ?",
            (org_id, dict_rev),
        ).fetchone()
        if row is None:
            return None
        cols = ("id", "org_id", "dict_rev", "yaml_rev", "sync_run_id",
                "status", "stats_json", "created_at")
        return _sem_run_dict(cols, row)

    def export_l0(self, org_id: str) -> str:
        """L0 术语片段导出——构建产物落地归 m2s-2（本段空串占位，语义轨道后段实装）。"""
        return ""

    # ---- m2s-3：YAML curated 合并面（yaml_merge 编排、SQL 收口本域） ----

    def sem_write_curated_batch(self, org_id: str, rows: Sequence[dict]) -> int:
        """curated_json 批写（规则表第 1 行）：active 实体 upsert curated 内容 +
        curated_rev；P3-3/R2：sensitivity **直写**（row.sensitivity 已由合并侧
        按 YAML 当前值解析——含显式 normal；不再 COALESCE 只增不减）。"""
        if not rows:
            return 0
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                conn.execute(
                    "UPDATE sem_entities SET curated_json = :curated,"
                    " curated_rev = :rev, sensitivity = :sensitivity,"
                    " updated_at = CURRENT_TIMESTAMP"
                    " WHERE org_id = :org AND type = :type AND key = :key"
                    "   AND status = 'active'",
                    {"curated": row["curated_json"], "rev": row["curated_rev"],
                     "sensitivity": row.get("sensitivity") or "normal",
                     "org": org_id, "type": row["type"], "key": row["key"]},
                )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return len(rows)

    def sem_replace_manual_aliases(self, org_id: str, rows: Sequence[dict]) -> int:
        """manual/abbr 别名整替（corpus 全量语义——先删后插，kind ∈
        {manual, abbr} 只动这两类；name/code/sync 原样——T-S1/TC-SYNC-05 分工）。"""
        if not rows:
            return 0
        conn = self._conn
        ids = self.resolve_entity_ids(
            org_id, [(r["type"], r["key"]) for r in rows]
        )
        inserted = 0
        touched: list[int] = []
        conn.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                eid = ids.get((row["type"], row["key"]))
                if eid is None:
                    continue
                conn.execute(
                    "DELETE FROM sem_aliases WHERE org_id = ? AND entity_id = ?"
                    "   AND kind IN ('manual', 'abbr')",
                    (org_id, eid),
                )
                for alias, alias_norm, kind, match_mode in row["aliases"]:
                    # P3-2/R2：UNIQUE(org,entity,alias_norm) 残余竞态兜底——
                    # 冲突行跳过不炸整 run（确定性冲突已由合并侧预检记录；
                    # 带 conflict target 防 OR IGNORE 误吞 CHECK 类失败）
                    conn.execute(
                        "INSERT INTO sem_aliases(org_id, entity_id, alias,"
                        " alias_norm, kind, match_mode)"
                        " VALUES(?, ?, ?, ?, ?, ?)"
                        " ON CONFLICT(org_id, entity_id, alias_norm) DO NOTHING",
                        (org_id, eid, alias, alias_norm, kind, match_mode),
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
        """YAML 删除覆盖项（规则表第 8 行）：本源 sync 实体中 curated_rev 非空
        且不在 keep 集 → 清 curated_json/curated_rev + 删 manual/abbr 别名；
        事实列（name/attrs/别名三 kind）不动；纯人工实体（source='curated'）
        的消失走实体级 missing/retired 流程，不在本面。"""
        conn = self._conn
        marks = ",".join("?" for _ in keep_entity_ids) if keep_entity_ids else None
        where_extra = f" AND id NOT IN ({marks})" if marks else ""
        conn.execute("BEGIN IMMEDIATE")
        try:
            stale = [
                r[0] for r in conn.execute(
                    f"SELECT id FROM sem_entities WHERE org_id = ?"
                    f" AND source = 'sync' AND status != 'retired'"
                    f" AND curated_rev IS NOT NULL{where_extra}",
                    (org_id, *keep_entity_ids),
                )
            ]
            for chunk in _sem_chunks(stale, self._SEM_IN_CHUNK):
                marks2 = ",".join("?" for _ in chunk)
                conn.execute(
                    f"UPDATE sem_entities SET curated_json = '{{}}',"
                    f" curated_rev = NULL, updated_at = CURRENT_TIMESTAMP"
                    f" WHERE org_id = ? AND id IN ({marks2})",
                    (org_id, *chunk),
                )
                conn.execute(
                    f"DELETE FROM sem_aliases WHERE org_id = ?"
                    f" AND entity_id IN ({marks2}) AND kind IN ('manual', 'abbr')",
                    (org_id, *chunk),
                )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        if stale:
            self.sem_refresh_search_texts(org_id, stale)
        return len(stale)

    # ---- C.3 FTS 模糊索引（search_entities 第三层——sqlite FTS5 外容表） ----

    def sem_refresh_search_texts(self, org_id: str, entity_ids: Sequence[int]) -> None:
        """实体 FTS 文本行重建：名称 + 全部别名（分词后空格拼接——docs FTS 同
        tokenizer 惯例）。外容表 delete 命令显式清理旧行（content 表 DELETE
        不自动维护索引）。"""
        from knowledge_lattice.adapters.tokenizer import word_tokens

        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            for chunk in _sem_chunks(list(entity_ids), self._SEM_IN_CHUNK):
                marks = ",".join("?" for _ in chunk)
                old = conn.execute(
                    f"SELECT id, seg_text FROM sem_search_texts"
                    f" WHERE org_id = ? AND entity_id IN ({marks})",
                    (org_id, *chunk),
                ).fetchall()
                for row_id, seg in old:
                    conn.execute(
                        "INSERT INTO sem_search_fts(sem_search_fts, rowid, seg_text)"
                        " VALUES('delete', ?, ?)",
                        (row_id, seg),
                    )
                conn.execute(
                    f"DELETE FROM sem_search_texts WHERE org_id = ?"
                    f" AND entity_id IN ({marks})",
                    (org_id, *chunk),
                )
                for r in conn.execute(
                    f"SELECT e.id, e.name, e.sensitivity FROM sem_entities e"
                    f" WHERE e.org_id = ? AND e.id IN ({marks}) AND e.status = 'active'",
                    (org_id, *chunk),
                ):
                    eid, name, _sensitivity = r
                    aliases = conn.execute(
                        "SELECT alias FROM sem_aliases WHERE org_id = ?"
                        " AND entity_id = ?",
                        (org_id, eid),
                    ).fetchall()
                    texts = [name] + [a[0] for a in aliases]
                    seg = " ".join(
                        tok for t in texts for tok in word_tokens(t)
                    )
                    if not seg:
                        continue
                    cur = conn.execute(
                        "INSERT INTO sem_search_texts(org_id, entity_id, seg_text)"
                        " VALUES(?, ?, ?)",
                        (org_id, eid, seg),
                    )
                    conn.execute(
                        "INSERT INTO sem_search_fts(rowid, seg_text)"
                        " VALUES(?, ?)",
                        (cur.lastrowid, seg),
                    )
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def _sem_fts_layer(self, org_id: str, q_norm: str, *, top_k: int,
                       type_filter: str, params: list) -> list[dict] | None:
        """FTS 第三层（C.3）：查询分词 → MATCH（**并列 AND**——贴近子串包含
        语义，避免单 token OR 噪声）；无 token（纯符号）返回 None（跳层）。
        评分差异按 G-6 登记。"""
        from knowledge_lattice.adapters.tokenizer import word_tokens

        tokens = word_tokens(q_norm)
        if not tokens:
            return None
        match = " ".join(f'"{t.replace(chr(34), chr(34) * 2)}"' for t in tokens)
        sql = (
            "SELECT e.id, e.type, e.key, e.name, e.attrs_json, e.curated_json,"
            " 0.5 AS score, 'fts' AS via, bm25(sem_search_fts) AS rank"
            " FROM sem_search_fts f"
            " JOIN sem_search_texts t ON t.id = f.rowid"
            " JOIN sem_entities e ON e.id = t.entity_id"
            " WHERE sem_search_fts MATCH ? AND t.org_id = ?"
            " AND e.org_id = ? AND e.status = 'active'"
            " AND e.sensitivity = 'normal'" + type_filter +
            " ORDER BY rank LIMIT ?"
        )
        query_params = [match, org_id, org_id, *params[1:], top_k]
        rows = self._conn.execute(sql, query_params).fetchall()
        cols = ("id", "type", "key", "name", "attrs_json", "curated_json",
                "score", "via", "rank")
        return [dict(zip(cols, r)) for r in rows]

    def sem_restricted_column_keys(self, org_id: str, table_id: int) -> set[str]:
        """C.5：表下 restricted 列键集（describe_table 主路径列级过滤面）。"""
        return {
            r[0] for r in self._conn.execute(
                "SELECT c.key FROM sem_relations r"
                " JOIN sem_entities c ON c.id = r.dst_id"
                " WHERE r.org_id = ? AND r.src_id = ? AND r.rel_type = 'has_column'"
                "   AND r.status = 'active' AND c.status = 'active'"
                "   AND c.sensitivity = 'restricted'",
                (org_id, table_id),
            )
        }

    # ---- m2s-2 首批语义工具读取面（get_entity / search_entities / describe_table） ----

    _SEM_ENTITY_COLS = ("id", "org_id", "type", "key", "name", "parent_id",
                        "attrs_json", "curated_json", "source", "source_system",
                        "status", "sensitivity", "synced_at", "curated_rev")

    def _sem_entity_row(self, row) -> dict:
        return dict(zip(self._SEM_ENTITY_COLS, row))

    def sem_entity_by_id(self, org_id: str, entity_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, type, key, name, parent_id, attrs_json,"
            " curated_json, source, source_system, status, sensitivity,"
            " synced_at, curated_rev FROM sem_entities WHERE org_id = ? AND id = ?",
            (org_id, entity_id),
        ).fetchone()
        return self._sem_entity_row(row) if row is not None else None

    def sem_entity_by_key(self, org_id: str, type_: str, key: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, org_id, type, key, name, parent_id, attrs_json,"
            " curated_json, source, source_system, status, sensitivity,"
            " synced_at, curated_rev FROM sem_entities"
            " WHERE org_id = ? AND type = ? AND key = ?",
            (org_id, type_, key),
        ).fetchone()
        return self._sem_entity_row(row) if row is not None else None

    def sem_entity_aliases(
        self, org_id: str, entity_ids: Sequence[int]
    ) -> list[dict]:
        out: list[dict] = []
        for chunk in _sem_chunks(list(entity_ids), self._SEM_IN_CHUNK):
            marks = ",".join("?" for _ in chunk)
            out.extend(
                {"entity_id": r[0], "alias": r[1], "alias_norm": r[2],
                 "kind": r[3], "match_mode": r[4], "weight": r[5]}
                for r in self._conn.execute(
                    f"SELECT entity_id, alias, alias_norm, kind, match_mode, weight"
                    f" FROM sem_aliases WHERE org_id = ? AND entity_id IN ({marks})"
                    f" ORDER BY entity_id, alias_norm",
                    (org_id, *chunk),
                )
            )
        return out

    def sem_expand_graph(
        self, org_id: str, root_id: int, *,
        outgoing: Sequence[str], incoming: Sequence[str],
        depth: int, fanout_limit: int, node_limit: int,
    ) -> dict:
        """BFS 逐层批量展开（递归 CTE 的等价 SQL——双方言同策略；防环=visited）。

        fanout_limit 按展开节点计（每节点每方向出边上限）；node_limit 为新增
        节点总量上限——命中任一截断 → truncated=True（T-S6）。restricted 端点
        与非 active 端点不出现（fail-closed——T-S9；active 关系才走）。
        P3-2/R2：edges 以 (src,rel,dst) 去重（双向查询同关系行不重复）且
        端点恒 ∈ {root} ∪ nodes（节点截断后不产悬挂边）。"""
        nodes: dict[int, dict] = {}
        edges: list[dict] = []
        seen_edges: set[tuple[int, str, int]] = set()
        truncated = False
        visited = {root_id}
        depth_of = {root_id: 0}
        frontier = [root_id]
        for _level in range(1, depth + 1):
            if not frontier:
                break
            next_frontier: list[int] = []
            for node in frontier:
                for rels, forward in ((outgoing, True), (incoming, False)):
                    if not rels:
                        continue
                    rows = self._conn.execute(
                        "SELECT r.src_id, r.rel_type, r.dst_id, r.source,"
                        " e.id, e.type, e.key, e.name"
                        " FROM sem_relations r JOIN sem_entities e"
                        f"   ON e.id = {'r.dst_id' if forward else 'r.src_id'}"
                        " WHERE r.org_id = ? AND r.status = 'active'"
                        "   AND e.status = 'active' AND e.sensitivity = 'normal'"
                        f"   AND {'r.src_id' if forward else 'r.dst_id'} = ?"
                        f"   AND r.rel_type IN ({','.join('?' for _ in rels)})"
                        " ORDER BY r.rel_type,"
                        f" {'r.dst_id' if forward else 'r.src_id'}",
                        (org_id, node, *rels),
                    ).fetchall()
                    fan = 0
                    for src, rel, dst, rel_source, oid, otype, okey, oname in rows:
                        if fan >= fanout_limit:
                            truncated = True
                            break
                        edge_key = (src, rel, dst)
                        if edge_key in seen_edges:
                            continue  # P3-2/R2：同一关系行双向查询只计一次
                        if oid not in visited and len(nodes) >= node_limit:
                            # P3-2/R2：节点截断后不再 append 悬挂边（边端点
                            # 必 ∈ {root} ∪ nodes——契约与 nodes 断言一致）
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
        """三层 UNION：alias_norm 精确(1.0) > alias_norm 前缀(0.8) > FTS 模糊
        （0.5——C.3/m2s-3：LIKE 骨架升级为 FTS5 MATCH over sem_search_texts，
        名称+别名分词索引；评分差异与 pg tsvector 按 G-6 口径登记不追平）
        ——实体去重保最优在 core 侧收口（此处拉 top_k×3 候选）。
        LIKE 前缀匹配统一 LOWER + ESCAPE（双方言语义一致：%/_ 通配转义）。"""
        esc_norm = _like_escape(q_norm)
        type_filter = ""
        params: list[object] = [org_id]
        if types:
            type_filter = f" AND e.type IN ({','.join('?' for _ in types)})"
            params.extend(types)
        base = (
            " FROM sem_aliases a JOIN sem_entities e ON e.id = a.entity_id"
            " WHERE a.org_id = ? AND e.status = 'active'"
            " AND e.sensitivity = 'normal'" + type_filter
        )
        sql = (
            "SELECT * FROM ("
            "  SELECT e.id, e.type, e.key, e.name, e.attrs_json, e.curated_json,"
            "         1.0 AS score, 'alias-exact' AS via" + base
            + "   AND a.alias_norm = ?"
            "  UNION ALL"
            "  SELECT e.id, e.type, e.key, e.name, e.attrs_json, e.curated_json,"
            "         0.8 AS score, 'alias-prefix' AS via" + base
            + "   AND a.alias_norm LIKE ? ESCAPE '\\'"
            ") ORDER BY score DESC, id ASC LIMIT ?"
        )
        query_params = (
            params + [q_norm]
            + params + [f"{esc_norm}%"]
            + [max(top_k * 2, top_k)]
        )
        rows = self._conn.execute(sql, query_params).fetchall()
        cols = ("id", "type", "key", "name", "attrs_json", "curated_json",
                "score", "via")
        out = [dict(zip(cols, r)) for r in rows]
        # 第三层 FTS：查询分词无 token（纯符号/空）时整层跳过（C.3 兼容面）
        fts_rows = self._sem_fts_layer(
            org_id, q_norm, top_k=top_k, type_filter=type_filter, params=params)
        if fts_rows:
            out.extend(fts_rows)
        return out

    def sem_table_columns(self, org_id: str, table_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT c.key, c.name FROM sem_relations r"
            " JOIN sem_entities c ON c.id = r.dst_id"
            " WHERE r.org_id = ? AND r.src_id = ? AND r.rel_type = 'has_column'"
            "   AND r.status = 'active' AND c.status = 'active'"
            "   AND c.sensitivity = 'normal'"
            " ORDER BY c.key",
            (org_id, table_id),
        ).fetchall()
        return [{"key": r[0], "name": r[1]} for r in rows]

    def expand_relations(self, org_id: str, seed_ids, rels, *, depth: int = 1) -> dict:
        """P3-3/R2 薄适配：sem_expand_graph 多 seed 归并（design §3/NFR-4 命名
        保留给 M2-S3 实体召回路；fanout/node 缺省与 core/expand.py 常量一致）。"""
        return _expand_relations_thin(self, org_id, seed_ids, rels, depth=depth)


def _month_upper(month: str) -> str:
    """月排他上界（次月首日 0 点——'YYYY-MM-DD HH:MM:SS'）。"""
    from knowledge_lattice.store.audit_chain import month_shift

    nxt = month_shift(month, 1)
    return f"{nxt[:4]}-{nxt[4:6]}-01 00:00:00"


def _like_escape(text: str) -> str:
    """LIKE 通配转义（%/_/\——配合 ESCAPE '\\' 子句双方言同语义）。"""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _expand_relations_thin(backend, org_id, seed_ids, rels, *, depth: int) -> dict:
    """expand_relations 薄适配共用体（双方言同实现——P3-3/R2）：
    逐 seed 调 sem_expand_graph（rels 双向）后归并去重；truncated 任一命中即真。

    O-2/m2s-3：**nodes 含 seed 本身**（design §5.9 walk CTE depth=0 行——
    `SELECT je.value, 0, ...` 种子即第 0 层；消费方〔M2-S3 实体召回〕确认契约）。
    **seed 过滤责任在消费方（P3-13）**：seed 行按 id 原样注入（未滤 status/
    sensitivity）——design §5.9 walk 最终 SELECT 的 active/restricted 过滤归
    消费面（get_entity 走 sem_expand_graph 自滤；召回路按调用者权限自筛）。
    seed 实体行批量读取后以 depth=0 注入；restricted/非 active seed 由
    sem_expand_graph 语义天然不展开（自身行信息仍注入——召回面自行过滤）。"""
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


def _sem_chunks(seq, n: int):
    """序列定长分片（IN (...) 参数上限治理——语义域批量读写共用）。"""
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


