"""实验 2（TC-PERF-02）：chunks.embedding 同表 vs chunk_vectors 分表
——回表耗时 + WAL 放大（5 万块档、双后端、2560 维 float32 合成向量 ~10KB/块），
附模型迁移蓝绿判据（D12/#41，G-8）实测。

口径（design §4 向量注 / §5.3 蓝绿 / TEST-CASES TC-PERF-02）：
- 规模：50_000 块（5_000 文档 × 10 块/文档），双后端各一套独立库
  （sqlite 文件库 / pg 独立 schema），两形态同库先后度量（同一份块行）；
- 向量：合成 2560 维 unit float32（bench_common.synth_vectors——确定性，
  零真实嵌入 API 调用），sqlite=vec_f32 BLOB（store 层 pack_f32 语义）、
  pg=pgvector 文本（store 层 format_vector 语义）；
- 写路径（生产形态对称）：同表=UPDATE chunks SET embedding/embed_model（块先落
  库后回写——M0a-3 生产链形态）；分表=INSERT INTO chunk_vectors(rid, embed_model,
  embedding)。两者同为客户端逐批（2000 行/批）显式事务、executemany——客户端
  开销对称，差异即布局差异；
- 查询形态（隔离布局变量——固定谓词，不叠 ACL 编译产物）：
  · 向量路精确扫描（G-6 起步口径）：org/version/tombstone + embed_model 谓词 +
    距离排序 top-20（sqlite=vec_distance_cosine / pg=<=>）；
  · 元数据扫描（非向量路拖累度量）：SELECT rid,id,doc_id 固定谓词——同表形态
    （chunks 含 10KB 向量行）vs 分表形态（chunks_narrow——同列集去掉
    embedding/embed_model 的对照表）；
  · 点查：rid IN (20 个定距 rid)；
- WAL 放大：sqlite 显式关闭 wal_autocheckpoint 后 -wal 文件高水位 = 该相精确
  日志字节；pg 用 pg_current_wal_lsn/pg_wal_lsn_diff；
- 蓝绿判据实测：方案一（同表置空重建：UPDATE embedding=NULL/embed_model=NULL
  全量 + 空间回收观察）vs 方案二（分表蓝绿：新标签 INSERT 并存 → 覆盖率 100% →
  current_model 原子切（config 翻转，零 SQL）→ 旧标签延后 DELETE + 回收）。

复跑：LATTICE_PG_DSN=... uv run python benchmarks/bench2_vector_layout.py
输出：stdout markdown 表 + data/bench-results/bench2.json
"""

from __future__ import annotations

import time
from typing import Any

from bench_common import (
    BENCH_ORG,
    MODEL_LABEL,
    VEC_DIM,
    md_table,
    machine_profile,
    open_bench_db,
    print_header,
    sample_timings,
    save_result,
    seed_corpus,
    synth_vectors,
)

N_CHUNKS = 50_000
CHUNKS_PER_DOC = 10
BATCH = 2_000
MODEL_NEW = "synth-embed-v2:2560"

# P3-7：全部计时相 n≥20——nearest-rank P95 在 n<20 时≈max（单一离群敏感），
# 提样本量使 P95 脱离 "=max"区；报告 §1/§5 披露该口径
_SCAN_WARMUP, SCAN_N = 2, 20
_RECALL_WARMUP, RECALL_N = 1, 20
_POINT_WARMUP, POINT_N = 2, 20

CHUNK_COLS_NARROW = (
    "rid, id, doc_id, seq, version, tombstone, content, title_seg, content_seg,"
    " token_count, heading_path, page_no, sheet_name, bbox_json, keywords,"
    " llm_keywords, tags, dims_json, detected_at_scale, content_sha, created_at"
)
# PG 侧 v1.1 真实窄 chunks 形态**保留 tsvector 五列 GENERATED**（只去掉
# embedding/embed_model）——CTAS 丢列会使 heap 变小、跌出并行扫描阈值，
# 得到"串行 vs 并行"的计划伪差异（实测 216 vs 117ms 系并行所致，非布局）
CHUNK_COLS_NARROW_PG = CHUNK_COLS_NARROW + (
    ", title_tsv, content_tsv, keywords_tsv, llm_keywords_tsv, tags_tsv"
)


# ============ 布局基建（chunk_vectors 分表 + chunks_narrow 对照表） ============


def create_layout_tables(db: Any) -> None:
    """分表 DDL：主键 (rid, embed_model)——蓝绿并存（§5.3：新旧模型标签同表
    共存、覆盖率 100% 原子切、旧向量延后清理）要求键含 embed_model；仅
    PRIMARY KEY(rid) 时新标签行无法与旧行并存（probe_pk_rid_conflict 实测
    IntegrityError——v1.1 分表建议的键形结论之一）。"""
    if db.is_sqlite:
        db.execute(
            "CREATE TABLE chunk_vectors ("
            " rid INTEGER NOT NULL REFERENCES chunks(rid) ON DELETE CASCADE,"
            " embed_model TEXT NOT NULL, embedding BLOB,"
            " PRIMARY KEY(rid, embed_model))"
        )
        db.execute(f"CREATE TABLE chunks_narrow AS SELECT {CHUNK_COLS_NARROW} FROM chunks")
        db.execute("CREATE UNIQUE INDEX idx_narrow_rid ON chunks_narrow(rid)")
        db.execute("CREATE UNIQUE INDEX idx_narrow_docver ON chunks_narrow(doc_id, version, seq)")
        db.execute("ANALYZE chunks_narrow")  # CTAS 无统计——planner 会选坏计划（P3-10 实测教训）
    else:
        db.execute(
            "CREATE TABLE chunk_vectors ("
            " rid BIGINT NOT NULL REFERENCES chunks(rid) ON DELETE CASCADE,"
            " embed_model TEXT NOT NULL, embedding vector,"
            " PRIMARY KEY(rid, embed_model))"
        )
        db.execute(f"CREATE TABLE chunks_narrow AS SELECT {CHUNK_COLS_NARROW_PG} FROM chunks")
        db.execute("CREATE UNIQUE INDEX idx_narrow_rid ON chunks_narrow(rid)")
        db.execute("CREATE UNIQUE INDEX idx_narrow_docver ON chunks_narrow(doc_id, version, seq)")
        db.execute("ANALYZE chunks_narrow")  # 同上：CTAS 无统计——补齐后近似真实分表布局的 chunks


# ============ 计时相（写路径 / 查询形态） ============


def probe_pk_rid_conflict(db: Any) -> dict[str, str]:
    """P2-5 证据脚本化：PRIMARY KEY(rid)（不含 embed_model）的分表在新标签行
    写入时即唯一冲突——蓝绿并存的物理前提是键含 embed_model。双后端各跑，
    catch 唯一冲突异常并报告；若未冲突则报 FAIL（结论失效，报告须改）。"""
    if db.is_sqlite:
        import sqlite3

        uniq = (sqlite3.IntegrityError,)
    else:
        from psycopg import errors as pg_errors

        uniq = (pg_errors.UniqueViolation,)
    db.execute(
        "CREATE TEMP TABLE cv_pkrid (rid INTEGER NOT NULL, embed_model TEXT NOT NULL,"
        " PRIMARY KEY(rid))"
    )
    outcome: dict[str, str] = {}
    try:
        db.execute("INSERT INTO cv_pkrid(rid, embed_model) VALUES(1, 'old:2560')")
        try:
            db.execute("INSERT INTO cv_pkrid(rid, embed_model) VALUES(1, 'new:2560')")
            outcome["result"] = "NO-CONFLICT（PK(rid) 允许并存——结论失效，需上报）"
        except uniq as exc:
            outcome["result"] = "IntegrityError（新标签行被拒）"
            outcome["exception"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}"
    finally:
        db.execute("DROP TABLE cv_pkrid")
    return outcome


def write_phase(db: Any, layout: str, vectors: Any, rids: list[int]) -> dict[str, float]:
    """同表 UPDATE vs 分表 INSERT——对称批量显式事务（2000 行/批 executemany）。

    rid 连续性断言：双方言块表均为全新自增主键（sqlite INTEGER PK / PG identity，
    自 1 起连续）——`vectors[i]` 与 rid=i+1 一一对应。"""
    assert rids == list(range(1, len(rids) + 1)), "rid 非连续——向量映射将错位"
    n_batches = (len(rids) + BATCH - 1) // BATCH
    if db.is_sqlite:
        if layout == "same":
            sql = "UPDATE chunks SET embedding = ?, embed_model = ? WHERE rid = ?"
        else:
            sql = "INSERT INTO chunk_vectors(rid, embed_model, embedding) VALUES(?, ?, ?)"
        begin, commit = "BEGIN IMMEDIATE", "COMMIT"
    else:
        if layout == "same":
            sql = "UPDATE chunks SET embedding = %(v)s::vector, embed_model = %(m)s WHERE rid = %(rid)s"
        else:
            sql = (
                "INSERT INTO chunk_vectors(rid, embed_model, embedding)"
                " VALUES(%(rid)s, %(m)s, %(v)s::vector)"
            )
        begin, commit = "BEGIN", "COMMIT"

    # 序列化口径校准：首行与 store 层 pack_f32/format_vector 逐字节等价（快路径 numpy）
    if db.is_sqlite:
        from knowledge_lattice.store.sqlite.vec import pack_f32

        assert vectors[0].astype("<f4").tobytes() == pack_f32([float(x) for x in vectors[0]])

    db.wal_checkpoint_truncate() if db.is_sqlite else None
    wal_lo = db.wal_lsn() if db.is_pg else None
    sqlite_autockpt = None
    if db.is_sqlite:  # 关闭自动 checkpoint：-wal 高水位 = 本相精确日志字节
        sqlite_autockpt = db.raw.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
        db.raw.execute("PRAGMA wal_autocheckpoint = 0")

    t0 = time.perf_counter()
    for bi in range(n_batches):
        lo = bi * BATCH
        batch_rids = rids[lo : lo + BATCH]
        db.execute(begin)
        if db.is_sqlite:
            params_seq = [
                (
                    (
                        vectors[r - 1].astype("<f4").tobytes(),  # = pack_f32（上方已校准）
                        MODEL_LABEL,
                        int(r),
                    )
                    if layout == "same"
                    else (
                        int(r),
                        MODEL_LABEL,
                        vectors[r - 1].astype("<f4").tobytes(),
                    )
                )
                for r in batch_rids
            ]
            db.raw.executemany(sql, params_seq)
        else:
            from knowledge_lattice.store.postgres.vec import format_vector

            params_seq = [
                {
                    "rid": int(r),
                    "m": MODEL_LABEL,
                    "v": format_vector(vectors[r - 1]),
                }
                for r in batch_rids
            ]
            db.raw.cursor().executemany(sql, params_seq)  # psycopg3 executemany 在 Cursor
        db.execute(commit)
    wall_s = time.perf_counter() - t0

    if db.is_sqlite:
        db.raw.execute(f"PRAGMA wal_autocheckpoint = {sqlite_autockpt}")
    wal_bytes = db.wal_diff_bytes(wal_lo, db.wal_lsn()) if db.is_pg else None
    sizes = db.db_bytes()
    if db.is_sqlite:
        wal_bytes = sizes["wal_file_bytes"]
        db.wal_checkpoint_truncate()  # 相末收敛（下相从干净 wal 起算）
    return {
        "wall_s": round(wall_s, 2),
        "wal_mb": round((wal_bytes or 0) / 1e6, 1),
        "throughput_rows_s": round(len(rids) / wall_s, 1),
        "payload_mb": round(len(rids) * VEC_DIM * 4 / 1e6, 1),
        **{k: v for k, v in sizes.items()},
    }


def _mark(db: Any) -> Any:
    """参数记号工厂：sqlite `:name` / pg `%(name)s`（pyformat）。"""
    if db.is_sqlite:
        return lambda n: f":{n}"
    return lambda n: f"%({n})s"


def recall_sql(
    db: Any, layout: str, table: str, *, model: str = MODEL_LABEL
) -> tuple[str, dict[str, Any]]:
    """向量路精确扫描 top-20（固定谓词隔离布局变量；G-6 起步口径）。

    - layout="same"：向量在 chunks.embedding（同表形态）；
    - layout="sep"：向量在 chunk_vectors（分表形态，JOIN 回块表）——**基表 table
      可选 chunks（宽行·上界口径）或 chunks_narrow（窄行·真实分表布局的干净
      口径，P2-1）**；model 用于蓝绿共存期以新标签谓词计时（P2-4）。
    """
    mk = _mark(db)
    if layout == "same":
        vec_pred = f"c.embedding IS NOT NULL AND c.embed_model = {mk('m')}"
        order = (
            f"vec_distance_cosine(c.embedding, {mk('q')})"
            if db.is_sqlite
            else f"c.embedding <=> {mk('q')}::vector"
        )
        join = ""
    else:
        vec_pred = f"cv.embed_model = {mk('m')}"
        order = (
            f"vec_distance_cosine(cv.embedding, {mk('q')})"
            if db.is_sqlite
            else f"cv.embedding <=> {mk('q')}::vector"
        )
        join = " JOIN chunk_vectors cv ON cv.rid = c.rid"
    base = (
        f"SELECT c.rid FROM {table} c JOIN documents d ON d.id = c.doc_id{join}"
        f" WHERE c.version = d.active_version AND c.tombstone = 0 AND d.org_id = {mk('org')}"
        f" AND {vec_pred} ORDER BY {order} LIMIT 20"
    )
    if db.is_sqlite:
        from knowledge_lattice.store.sqlite.vec import pack_f32

        return base, {"org": BENCH_ORG, "m": model, "q": pack_f32([float(x) for x in _QUERY_VEC])}
    from knowledge_lattice.store.postgres.vec import format_vector

    return base, {
        "org": BENCH_ORG,
        "m": model,
        "q": format_vector(_QUERY_VEC),
    }


def meta_scan_sql(table: str, db: Any) -> tuple[str, dict[str, Any]]:
    mk = _mark(db)
    sql = (
        f"SELECT c.rid, c.id, c.doc_id FROM {table} c JOIN documents d ON d.id = c.doc_id"
        f" WHERE c.version = d.active_version AND c.tombstone = 0 AND d.org_id = {mk('org')}"
    )
    return sql, {"org": BENCH_ORG}


def point_lookup_sql(table: str, db: Any, rids: list[int]) -> tuple[str, dict[str, Any]]:
    """rid IN (…) 点查（小列投影，不含 embedding 载荷——行定位 + 标量列读）。

    chunk_vectors 无 id/doc_id 列，取 (rid, embed_model) 保持同形态。"""
    cols = "rid, embed_model" if table == "chunk_vectors" else "rid, id, doc_id"
    if db.is_sqlite:
        marks = ",".join(f":r{i}" for i in range(len(rids)))
        return (
            f"SELECT {cols} FROM {table} WHERE rid IN ({marks})",
            {f"r{i}": int(r) for i, r in enumerate(rids)},
        )
    marks = ",".join(f"%(r{i})s" for i in range(len(rids)))
    return (
        f"SELECT {cols} FROM {table} WHERE rid IN ({marks})",
        {f"r{i}": int(r) for i, r in enumerate(rids)},
    )


_QUERY_VEC: Any = None  # main() 里取 synth_vectors 首行


def phase_blue_green(db: Any, results: list[dict]) -> None:
    """蓝绿判据实测：方案一（同表置空）vs 方案二（分表蓝绿）——耗时/WAL/空间回收。"""
    # ---- 方案一：同表置空重建（迁移期向量路降级——旧向量清空，BM25 单路） ----
    db.wal_checkpoint_truncate() if db.is_sqlite else None
    lo = db.wal_lsn() if db.is_pg else None
    ac = db.raw.execute("PRAGMA wal_autocheckpoint").fetchone()[0] if db.is_sqlite else None
    if db.is_sqlite:
        db.raw.execute("PRAGMA wal_autocheckpoint = 0")
    t0 = time.perf_counter()
    if db.is_sqlite:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE chunks SET embedding = NULL, embed_model = NULL WHERE embed_model = ?",
            (MODEL_LABEL,),
        )
        db.execute("COMMIT")
    else:
        db.execute("BEGIN")
        db.execute(
            "UPDATE chunks SET embedding = NULL, embed_model = NULL WHERE embed_model = %(m)s",
            {"m": MODEL_LABEL},
        )
        db.execute("COMMIT")
    p1_s = time.perf_counter() - t0
    wal_p1 = db.wal_diff_bytes(lo, db.wal_lsn()) if db.is_pg else None
    sizes_p1 = db.db_bytes()
    if db.is_sqlite:
        db.raw.execute(f"PRAGMA wal_autocheckpoint = {ac}")
        wal_p1 = sizes_p1["wal_file_bytes"]
        db.wal_checkpoint_truncate()
    results.append(
        {
            "phase": "方案一:置空(同表)",
            "wall_s": round(p1_s, 2),
            "wal_mb": round((wal_p1 or 0) / 1e6, 1),
            "note": "向量路即时降级（NULL 防护谓词落空）",
            **{k: v for k, v in sizes_p1.items() if k.startswith(("pg_chunks", "pages", "db_file"))},
        }
    )
    # 空间回收观察：sqlite VACUUM 重写库文件 / pg VACUUM 标记可复用
    t0 = time.perf_counter()
    if db.is_sqlite:
        db.raw.execute("VACUUM")
        reclaim_s = time.perf_counter() - t0
    else:
        db.execute("VACUUM ANALYZE chunks")
        reclaim_s = time.perf_counter() - t0
    sizes_p1r = db.db_bytes()
    results.append(
        {
            "phase": "方案一:空间回收",
            "wall_s": round(reclaim_s, 2),
            "wal_mb": 0.0,
            "note": "sqlite VACUUM 重写库文件 / pg VACUUM ANALYZE",
            **{k: v for k, v in sizes_p1r.items() if k.startswith(("pg_chunks", "pages", "db_file"))},
        }
    )

    # ---- 方案二：分表蓝绿（新旧并存 → 原子切 → 延后清理） ----
    lo = db.wal_lsn() if db.is_pg else None
    if db.is_sqlite:
        db.wal_checkpoint_truncate()
        db.raw.execute("PRAGMA wal_autocheckpoint = 0")
    t0 = time.perf_counter()
    # 新标签行落地（服务端 INSERT..SELECT 复制 = 「重嵌入完成载荷落地」的布局代价；
    # 嵌入 API 耗时不在本实验量程——零真实调用口径）
    if db.is_sqlite:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO chunk_vectors(rid, embed_model, embedding)"
            " SELECT rid, ?, embedding FROM chunk_vectors WHERE embed_model = ?",
            (MODEL_NEW, MODEL_LABEL),
        )
        db.execute("COMMIT")
    else:
        db.execute("BEGIN")
        db.execute(
            "INSERT INTO chunk_vectors(rid, embed_model, embedding)"
            " SELECT rid, %(new)s, embedding FROM chunk_vectors WHERE embed_model = %(old)s",
            {"new": MODEL_NEW, "old": MODEL_LABEL},
        )
        db.execute("COMMIT")
    p2a_s = time.perf_counter() - t0

    def _count_label(model: str) -> int:
        if db.is_sqlite:
            return db.execute(
                "SELECT count(*) FROM chunk_vectors WHERE embed_model = ?", (model,)
            )[0][0]
        return db.execute(
            "SELECT count(*) FROM chunk_vectors WHERE embed_model = %(m)s", {"m": model}
        )[0][0]

    cov = {m: _count_label(m) for m in (MODEL_LABEL, MODEL_NEW)}
    wal_p2a = (
        db.wal_diff_bytes(lo, db.wal_lsn())
        if db.is_pg
        else db.db_bytes()["wal_file_bytes"]
    )
    results.append(
        {
            "phase": "方案二:新标签并存写入",
            "wall_s": round(p2a_s, 2),
            "wal_mb": round(wal_p2a / 1e6, 1),
            "note": f"覆盖率 old={cov[MODEL_LABEL]} new={cov[MODEL_NEW]}；current_model 原子切=配置翻转（零 SQL、瞬时）",
        }
    )

    # ---- P2-4：共存期读路径——新旧标签并存（各 50K 行）时按 current（新标签）
    # 谓词的向量召回（窄基表——真实分表布局）。"功能零降级"≠"性能零降级"，
    # 此处量化共存窗口的向量路代价（扫描需先过滤掉另一半旧行）。
    # （只读相位；checkpoint TRUNCATE 对齐其他读相位的干净起点，autocheckpoint
    # 保持 0——下方 DELETE 相位的 WAL 计量窗口与 R1 同款）
    if db.is_sqlite:
        db.wal_checkpoint_truncate()
    co_sql, co_params = recall_sql(db, "sep", "chunks_narrow", model=MODEL_NEW)
    co_t = sample_timings(lambda: db.execute(co_sql, co_params), warmup=_RECALL_WARMUP, n=RECALL_N)
    co_rows = [r[0] for r in db.execute(co_sql, co_params)]
    results.append(
        {
            "phase": "方案二:共存期向量召回(窄基表)",
            "p50_ms": co_t["p50_ms"],
            "p95_ms": co_t["p95_ms"],
            "wall_s": 0.0,
            "wal_mb": 0.0,
            "note": f"新旧各 50K 行并存、按新标签谓词 top-20（n={RECALL_N}）；对照 §3.2 单标签分表窄基表行",
        }
    )

    # 旧向量延后清理
    lo2 = db.wal_lsn() if db.is_pg else None
    if db.is_sqlite:
        db.wal_checkpoint_truncate()
    t0 = time.perf_counter()
    if db.is_sqlite:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM chunk_vectors WHERE embed_model = ?", (MODEL_LABEL,))
        db.execute("COMMIT")
    else:
        db.execute("BEGIN")
        db.execute("DELETE FROM chunk_vectors WHERE embed_model = %(m)s", {"m": MODEL_LABEL})
        db.execute("COMMIT")
    p2b_s = time.perf_counter() - t0
    wal_p2b = db.wal_diff_bytes(lo2, db.wal_lsn()) if db.is_pg else None
    sizes_p2 = db.db_bytes()
    if db.is_sqlite:
        wal_p2b = sizes_p2["wal_file_bytes"]
        db.raw.execute(f"PRAGMA wal_autocheckpoint = {ac}")
        db.wal_checkpoint_truncate()
    results.append(
        {
            "phase": "方案二:旧标签延后清理",
            "wall_s": round(p2b_s, 2),
            "wal_mb": round((wal_p2b or 0) / 1e6, 1),
            "note": "清理窗口自主选择（低峰）；期间向量路按 current_model 谓词不受影响",
            **{k: v for k, v in sizes_p2.items() if k.startswith(("pg_chunk_vectors", "pages", "db_file"))},
        }
    )
    t0 = time.perf_counter()
    if db.is_sqlite:
        db.raw.execute("VACUUM")
    else:
        db.execute("VACUUM ANALYZE chunk_vectors")
    sizes_p2r = db.db_bytes()
    results.append(
        {
            "phase": "方案二:空间回收",
            "wall_s": round(time.perf_counter() - t0, 2),
            "wal_mb": 0.0,
            "note": "",
            **{k: v for k, v in sizes_p2r.items() if k.startswith(("pg_chunk_vectors", "pages", "db_file"))},
        }
    )


# ============ 主流程 ============


def run_dialect(dialect: str, vectors: Any) -> tuple[dict[str, Any], list[dict]]:
    tag = f"bench2_{dialect}"
    with open_bench_db(dialect, tag=tag) as db:
        t0 = time.perf_counter()
        seed_corpus(db, n_docs=N_CHUNKS // CHUNKS_PER_DOC, chunks_per_doc=CHUNKS_PER_DOC)
        seed_s = time.perf_counter() - t0
        create_layout_tables(db)

        min_rid = db.execute("SELECT min(rid) FROM chunks")[0][0]
        max_rid = db.execute("SELECT max(rid) FROM chunks")[0][0]
        all_rids = [r[0] for r in db.execute("SELECT rid FROM chunks ORDER BY rid")]
        probe_rids = [all_rids[i * (len(all_rids) // 20)] for i in range(20)]

        out: dict[str, Any] = {"dialect": dialect, "seed_s": round(seed_s, 1)}
        out["sizes_seed"] = db.db_bytes()

        if db.is_pg:
            # 计划伪差异消除（P2-1 附带发现）：PG 并行计划按 heap 页数阈值翻转——
            # 同表 chunks（42MB，含 UPDATE 死元组膨胀）走 3-worker 并行（实测
            # 117ms），CTAS 窄表（22MB）走串行（216ms），差异系并行而非布局；
            # 且阈值随 vacuum 状态漂移。会话级禁用并行统一串行口径（可复现、
            # 布局可比），报告注明。
            db.execute("SET max_parallel_workers_per_gather = 0")
            out["pg_parallelism"] = "disabled(max_parallel_workers_per_gather=0)"

        # ---- P2-5：PK(rid)（不含 embed_model）分表新标签写入即唯一冲突——脚本化证据 ----
        out["pk_rid_conflict_probe"] = probe_pk_rid_conflict(db)

        # ---- 元数据/点查基线（两表此时同构：chunks.embedding 全 NULL vs narrow） ----
        for table, label in (("chunks", "同表(NULL向量)"), ("chunks_narrow", "分表对照(narrow)")):
            sql, p = meta_scan_sql(table, db)
            t = sample_timings(lambda: db.execute(sql, p), warmup=_SCAN_WARMUP, n=SCAN_N)
            out[f"meta_scan_base_{label}"] = t
            sql2, p2 = point_lookup_sql(table, db, probe_rids)
            t2 = sample_timings(lambda: db.execute(sql2, p2), warmup=_POINT_WARMUP, n=POINT_N)
            out[f"point_lookup_base_{label}"] = t2

        # ---- Phase A：同表写入（UPDATE 回写——生产链形态） ----
        out["write_same"] = write_phase(db, "same", vectors, all_rids)
        sql, p = meta_scan_sql("chunks", db)
        out["meta_scan_same"] = sample_timings(
            lambda: db.execute(sql, p), warmup=_SCAN_WARMUP, n=SCAN_N
        )
        sql2, p2 = point_lookup_sql("chunks", db, probe_rids)
        out["point_lookup_same"] = sample_timings(
            lambda: db.execute(sql2, p2), warmup=_POINT_WARMUP, n=POINT_N
        )
        rsql, rp = recall_sql(db, "same", "chunks")
        out["recall_same"] = sample_timings(
            lambda: db.execute(rsql, rp), warmup=_RECALL_WARMUP, n=RECALL_N
        )
        out["recall_same_rows"] = [r[0] for r in db.execute(rsql, rp)]

        # ---- Phase B：分表写入（INSERT——对称批量） ----
        out["write_sep"] = write_phase(db, "sep", vectors, all_rids)
        # P2-1：分表向量路两种基表口径——宽 chunks（R1 口径·上界：基表仍带 10KB
        # 向量行）与 chunks_narrow（真实分表布局的窄基表·干净口径）
        rsql_w, rp_w = recall_sql(db, "sep", "chunks")
        out["recall_sep_wide"] = sample_timings(
            lambda: db.execute(rsql_w, rp_w), warmup=_RECALL_WARMUP, n=RECALL_N
        )
        rsql2, rp2 = recall_sql(db, "sep", "chunks_narrow")
        out["recall_sep"] = sample_timings(
            lambda: db.execute(rsql2, rp2), warmup=_RECALL_WARMUP, n=RECALL_N
        )
        top_sep = [r[0] for r in db.execute(rsql2, rp2)]
        out["recall_sep_rows"] = top_sep
        if set(top_sep) != set(out["recall_same_rows"]):
            print(
                f"WARN [{dialect}] 两布局 top-20 rid 集不一致——距离并列所致？"
                f"same={sorted(out['recall_same_rows'])} sep={sorted(top_sep)}"
            )
        # P3-6：分表侧点查补 chunk_vectors（此前只测 chunks/narrow 两对照）
        sql3, p3 = point_lookup_sql("chunk_vectors", db, probe_rids)
        out["point_lookup_chunk_vectors"] = sample_timings(
            lambda: db.execute(sql3, p3), warmup=_POINT_WARMUP, n=POINT_N
        )

        # ---- 蓝绿判据 ----
        bg: list[dict] = []
        phase_blue_green(db, bg)
        out["blue_green"] = bg

        # 相位后校验：向量数 / 标签
        n_vec = db.execute(
            "SELECT count(*) FROM chunks WHERE embedding IS NOT NULL"
        )[0][0]
        out["post_check_chunks_with_vec"] = n_vec
        return out, bg


def main() -> None:
    global _QUERY_VEC
    vectors = synth_vectors(N_CHUNKS)
    _QUERY_VEC = vectors[0]

    results: dict[str, Any] = {}
    bg_all: list[dict] = []
    for dialect in ("sqlite", "pg"):
        print(f"[{dialect}] 运行中（造数+写相位+查询+蓝绿）……", flush=True)
        results[dialect], bg = run_dialect(dialect, vectors)
        for row in bg:
            row["dialect"] = dialect
        bg_all.extend(bg)
        print(f"[{dialect}] 完成", flush=True)

    print_header("实验 2（TC-PERF-02）写入相位（50K 块 × 2560 维 float32 ≈ 512MB 载荷）")
    rows = []
    for d in ("sqlite", "pg"):
        for layout, key in (("同表(UPDATE)", "write_same"), ("分表(INSERT)", "write_sep")):
            w = results[d][key]
            rows.append([d, layout, w["wall_s"], w["throughput_rows_s"], w["wal_mb"], w["payload_mb"]])
    print(md_table(["后端", "布局", "写入耗时 s", "吞吐 行/s", "WAL MB", "载荷 MB"], rows))

    print_header("P2-5 证据：PK(rid) 分表（不含 embed_model）新标签写入即唯一冲突")
    for d in ("sqlite", "pg"):
        probe = results[d]["pk_rid_conflict_probe"]
        print(f"- {d}: {probe['result']}｜{probe.get('exception', '')}")

    print_header("查询形态：向量路精确扫描 top-20 / 元数据扫描 / 点查（P50/P95 ms）")
    rows = []
    for d in ("sqlite", "pg"):
        r = results[d]
        for label, key in (
            ("向量召回 top-20（同表）", "recall_same"),
            ("向量召回 top-20（分表·宽基表=上界口径）", "recall_sep_wide"),
            ("向量召回 top-20（分表·窄基表=干净口径）", "recall_sep"),
        ):
            t = r[key]
            rows.append([d, label, t["p50_ms"], t["p95_ms"]])
        for label, key in (
            ("元数据扫描(基线 NULL)", "meta_scan_base_同表(NULL向量)"),
            ("元数据扫描(同表 10KB 行)", "meta_scan_same"),
            ("元数据扫描(分表对照 narrow)", "meta_scan_base_分表对照(narrow)"),
        ):
            t = r[key]
            rows.append([d, label, t["p50_ms"], t["p95_ms"]])
        for label, key in (
            ("点查×20(chunks 基线 NULL)", "point_lookup_base_同表(NULL向量)"),
            ("点查×20(chunks 同表 10KB 行)", "point_lookup_same"),
            ("点查×20(chunk_vectors 分表)", "point_lookup_chunk_vectors"),
        ):
            t = r[key]
            rows.append([d, label, t["p50_ms"], t["p95_ms"]])
    print(md_table(["后端", "形态", "P50 ms", "P95 ms"], rows))

    print_header("WAL 放大与库尺寸")
    print(
        "（sqlite 行：整库页量 / WAL / 库文件；pg 行：chunks 表(含 toast+索引) / WAL / chunk_vectors）"
    )
    rows = []
    for d in ("sqlite", "pg"):
        for layout, key in (("同表", "write_same"), ("分表", "write_sep")):
            w = results[d][key]
            if results[d]["dialect"] == "sqlite":
                rows.append([d, layout, w.get("pages_bytes", 0) / 1e6, w["wal_mb"], w.get("db_file_bytes", 0) / 1e6])
            else:
                rows.append(
                    [d, layout, w.get("pg_chunks_bytes", 0) / 1e6, w["wal_mb"], w.get("pg_chunk_vectors_bytes", 0) / 1e6]
                )
    print(md_table(["后端", "布局", "库尺寸A MB", "WAL MB", "库尺寸B MB"], rows))

    print_header("蓝绿判据实测（方案一 vs 方案二；含共存期读路径 P2-4）")
    print(
        md_table(
            ["后端", "相位", "耗时 s", "WAL MB", "P50/P95 ms", "说明"],
            [
                [
                    b["dialect"],
                    b["phase"],
                    b["wall_s"],
                    b.get("wal_mb", ""),
                    f"{b['p50_ms']:.1f}/{b['p95_ms']:.1f}" if "p50_ms" in b else "",
                    b["note"],
                ]
                for b in bg_all
            ],
        )
    )

    profile = machine_profile()
    print_header("机器口径")
    for k, v in profile.items():
        print(f"- {k}: {v}")

    path = save_result("bench2", {"profile": profile, "results": results, "blue_green": bg_all})
    print(f"\n结果工件：{path}")


if __name__ == "__main__":
    main()
