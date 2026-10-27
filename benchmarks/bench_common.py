"""M0b-2 实验共享 harness（TC-PERF-01/02、TC-AUTH-04 附注——benchmarks/ 三脚本共用）。

隔离纪律（验收 5——门禁保持绿）：
- 本目录不进常规 pytest 收集：pyproject `testpaths = ["tests"]`，且本目录文件
  一律不以 test_ 开头（双重隔离）；入口 `uv run python benchmarks/<script>.py`。

公平性口径（计时口径——报告引用，2026-10-24）：
- SQLite：经 store/sqlite/connection.connect 工厂（WAL / synchronous=NORMAL /
  busy_timeout=5000 / foreign_keys=ON——与生产同款 PRAGMA 状态）；python sqlite3
  自带语句缓存（默认 128 条），同一条 SQL 重复执行走已编译 prepared statement；
- PG：psycopg3 单连接 autocommit（经 store/postgres 工厂纪律：str→unknown dumper、
  TimeZone=UTC、pgvector 断言），prepare_threshold 默认 5——预热轮后自动转服务端
  prepared statement；每次计时含全结果物化（fetchall），两写法同口径；
- 计时一律 time.perf_counter；P50/P95 取 nearest-rank（ceil(p·n)-1 下标）。

确定性造数：
- 全部随机源固定种子 SEED=20261024（python random.Random 与 numpy PCG64 各自
  独立子域，记录 numpy 版本——Generator 分布流跨 numpy 大版本理论可漂移，结论
  不依赖向量具体取值，详见 report-m0b-2.md 机器口径节）；
- 造数走生产写路径：backend.create_document + backend.insert（chunks+FTS 触发器
  / tsvector GENERATED + pending_dims 解析 + D20 首次切换全链真实执行）；
- 嵌入零真实 API 调用：向量合成（2560 维 unit float32，按 embed_model 标签写入）。
"""

from __future__ import annotations

import json
import math
import os
import re
import platform
import random
import sqlite3
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

SEED = 20261024

BENCH_ORG = "org:bench"
BENCH_DATASET = "ds:bench"
BENCH_DIMS: dict[str, tuple[str, ...]] = {
    "region": ("CN", "OS"),
    "tax_type": ("VAT", "CIT"),
}

# 三用户形态（授权分布——编译产物形态覆盖：常规双维授权 / 宽授权 / 空授权集
# 单条件 T22 形态；计时与等价性复核对三形态一致执行）
BENCH_USERS: dict[str, dict[str, tuple[str, ...]]] = {
    "u_narrow": {"region": ("CN",), "tax_type": ("VAT",)},
    "u_broad": {"region": ("CN", "OS"), "tax_type": ("VAT", "CIT")},
    "u_empty_tax": {"region": ("CN",), "tax_type": ()},
}

# 合成向量标签（model:dim——D12 形态；写入与查询谓词同源）
VEC_DIM = 2560
MODEL_LABEL = "synth-embed:2560"

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "bench"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "data" / "bench-results"

DSN_ENV = "LATTICE_PG_DSN"


def pg_dsn() -> str:
    dsn = os.environ.get(DSN_ENV)
    if not dsn:
        raise SystemExit(
            f"{DSN_ENV} 未设置——pg 臂无法运行（docker start lattice-pg 后 "
            f"export {DSN_ENV}=postgresql://postgres:lattice@localhost:5432/lattice）"
        )
    return dsn


# ============ 双后端最小执行包装（qmark → pg %s 翻译；渲染器按方言分派） ============


class BenchDb:
    """方言无关执行面 + 方言分派渲染（自包含，不依赖 tests/ 基建）。"""

    def __init__(self, dialect: str, conn: Any, *, sqlite_path: Path | None = None,
                 pg_schema: str | None = None, pg_dsn_value: str | None = None) -> None:
        self.dialect = dialect
        self.is_sqlite = dialect == "sqlite"
        self.is_pg = dialect == "pg"
        self._conn = conn
        self.sqlite_path = sqlite_path
        # M1-5 R3 P1-1：并发档每线程独立 PG 连接（search_path 复用）所需
        self.pg_schema = pg_schema
        self.pg_dsn_value = pg_dsn_value

    @property
    def raw(self) -> Any:
        return self._conn

    def execute(self, sql: str, params: Any = ()) -> list[tuple]:
        """qmark（?）SQL 单一写法；pg 臂把 ? 翻译为 %s（渲染器产物为字典参数、
        原样透传——与 tests/dbwrap 同约定）。"""
        if self.is_pg and not isinstance(params, dict):
            sql = sql.replace("?", "%s")
        cur = self._conn.execute(sql, params)
        if cur.description is None:
            return []
        return cur.fetchall()

    def make_backend(self):
        if self.is_sqlite:
            from knowledge_lattice.store.sqlite.backend import SqliteBackend

            return SqliteBackend(self._conn)
        from knowledge_lattice.store.postgres.backend import PgBackend

        return PgBackend(self._conn)

    # ---- ACL 双写法渲染分派（store 层公开产物——不为计时绕过编译器/渲染器） ----

    def compile_acl(self, user_id: str, org_id: str):
        from knowledge_lattice.core.docs.acl import compile_acl

        return compile_acl(self.make_backend(), user_id, org_id)

    def render_select(self, plan):
        if self.is_sqlite:
            from knowledge_lattice.store.sqlite.acl_render import render_select

            return render_select(plan)
        from knowledge_lattice.store.postgres.acl_render import render_select

        return render_select(plan)

    # M0b-3 注：render_visible_docs_select 已随拍板 1 删除（v1.1 起 render_select
    # 即 visible_docs+MATERIALIZED 唯一路径）——本实验 harness 同步收敛。

    # ---- 尺寸/WAL 快照（实验 2） ----

    def wal_checkpoint_truncate(self) -> None:
        if self.is_sqlite:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def db_bytes(self) -> dict[str, int]:
        if self.is_sqlite:
            page_size = self._conn.execute("PRAGMA page_size").fetchone()[0]
            page_count = self._conn.execute("PRAGMA page_count").fetchone()[0]
            assert self.sqlite_path is not None
            wal_path = Path(str(self.sqlite_path) + "-wal")
            return {
                "pages_bytes": page_size * page_count,
                "wal_file_bytes": wal_path.stat().st_size if wal_path.exists() else 0,
                "db_file_bytes": (
                    self.sqlite_path.stat().st_size if self.sqlite_path.exists() else 0
                ),
            }
        sizes = {}
        for table in ("chunks", "chunks_narrow", "chunk_vectors", "documents"):
            row = self._conn.execute(
                "SELECT pg_total_relation_size(%(t)s)", {"t": table}
            ).fetchone()
            sizes[f"pg_{table}_bytes"] = int(row[0]) if row and row[0] else 0
        return sizes

    def wal_lsn(self) -> str:
        return self._conn.execute("SELECT pg_current_wal_lsn()").fetchone()[0]

    def wal_diff_bytes(self, start: str, end: str) -> int:
        return int(
            self._conn.execute(
                "SELECT pg_wal_lsn_diff(%(e)s, %(s)s)", {"e": end, "s": start}
            ).fetchone()[0]
        )


_SQLITE_PATHS: dict[str, Path] = {}  # 保留占位（外部排查用；BenchDb.sqlite_path 为准）


@contextmanager
def open_bench_db(dialect: str, *, tag: str) -> Iterator[BenchDb]:
    """就位一个实验库：sqlite 文件库（data/bench/，已 gitignore）或 pg 独立 schema
    （lattice_bench_<hex>：CREATE → search_path → 工厂纪律 → 迁移 → … → DROP）。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if dialect == "sqlite":
        from knowledge_lattice.store.sqlite import connect, migrate_db

        db_path = DATA_DIR / f"{tag}.db"
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
        conn = connect(db_path)
        try:
            migrate_db(conn)
            yield BenchDb("sqlite", conn, sqlite_path=db_path)
        finally:
            conn.close()
        return

    import psycopg

    from knowledge_lattice.store.postgres import migrate_db, setup_connection

    # R3：tag 净化为合法 PG 标识符（工厂 _SCHEMA_ITEM_RE 校验拒连字符——
    # search_path 逐项校验的防御面在工厂侧，bench 侧按其口径命名）
    schema = f"lattice_bench_{re.sub(r'[^0-9a-zA-Z_]', '_', tag)}_{uuid.uuid4().hex[:8]}"
    raw = psycopg.connect(pg_dsn(), autocommit=True)
    try:
        raw.execute(f'CREATE SCHEMA "{schema}"')
        raw.execute(f'SET search_path TO "{schema}", public')
        setup_connection(raw)
        migrate_db(raw)
        yield BenchDb("pg", raw, pg_schema=schema, pg_dsn_value=pg_dsn())
    finally:
        try:
            raw.execute("SET search_path TO public")
            raw.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except psycopg.Error:
            pass
        finally:
            raw.close()


# ============ 确定性造数（生产写路径：create_document + insert 全链） ============


def _doc_dims(rng: random.Random, doc_index: int) -> dict[str, list[str]]:
    """文档维度确定性分布：region 15% 空 / 单值为主 / 10% 双值（D19 多值）；
    tax_type 20% 空。分布覆盖两写法的全部判定分支（空值放行/命中/不命中/多值）。"""
    dims: dict[str, list[str]] = {}
    r = rng.random()
    if r < 0.15:
        pass  # region 空（空值放行分支）
    elif r < 0.50:
        dims["region"] = ["CN"]
    elif r < 0.90:
        dims["region"] = ["OS"]
    else:
        dims["region"] = ["CN", "OS"]
    if (doc_index * 2654435761) % 5 == 0:  # ~20% tax_type 空（与 rng 独立的确定混合）
        pass
    elif rng.random() < 0.5:
        dims["tax_type"] = ["VAT"]
    else:
        dims["tax_type"] = ["CIT"]
    return dims


def seed_corpus(db: BenchDb, *, n_docs: int, chunks_per_doc: int, seed: int = SEED) -> None:
    """org/dataset/双维度/三用户 + n_docs 文档（每文档 chunks_per_doc 块）。

    走 backend.create_document + backend.insert 生产路径：pending_dims 解析、
    document_dimensions 落库、chunks.dims_json 冗余投影、FTS 触发器（sqlite）/
    tsvector GENERATED（pg）、D20 首次切换全部真实执行——两写法的数据源一致性
    （TC-ACL-07 前提）由生产写入链保证。
    """
    backend = db.make_backend()
    e = db.execute
    e("INSERT INTO orgs(id, name) VALUES(?, ?)", (BENCH_ORG, "bench 组织"))
    e("INSERT INTO datasets(id, org_id, name) VALUES(?, ?, ?)", (BENCH_DATASET, BENCH_ORG, "bench 库"))
    for key in sorted(BENCH_DIMS):
        dim_id = f"dim:{BENCH_ORG}:{key}"
        e(
            "INSERT INTO dimensions(id, org_id, key, name) VALUES(?, ?, ?, ?)",
            (dim_id, BENCH_ORG, key, key),
        )
        for value in BENCH_DIMS[key]:
            e(
                "INSERT INTO dimension_values(id, dimension_id, value, label)"
                " VALUES(?, ?, ?, ?)",
                (f"val:{dim_id}:{value}", dim_id, value, value),
            )
    for user_id, grants in BENCH_USERS.items():
        e("INSERT INTO users(id, username) VALUES(?, ?)", (user_id, user_id))
        e(
            "INSERT INTO user_org_memberships(user_id, org_id, role) VALUES(?, ?, 'member')",
            (user_id, BENCH_ORG),
        )
        for key, values in grants.items():
            for value in values:
                e(
                    "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id, source)"
                    " VALUES(?, ?, ?, 'local')",
                    (
                        user_id,
                        f"dim:{BENCH_ORG}:{key}",
                        f"val:dim:{BENCH_ORG}:{key}:{value}",
                    ),
                )
    if db.is_sqlite:
        db.raw.commit()

    rng = random.Random(seed)
    for i in range(n_docs):
        dims = _doc_dims(rng, i)
        doc_id = f"doc:{i:06d}"
        backend.create_document(
            doc_id=doc_id,
            org_id=BENCH_ORG,
            dataset_id=BENCH_DATASET,
            title=f"bench 文档 {i}",
            source_uri="user:u_narrow",
            content_hash=f"sha256:{i}",
            mime_type="text/plain",
            parser="docling",
            owner_user_id="u_narrow",
            raw_object_key=f"objects/{i}",
            pending_dims_json=json.dumps(dims) if dims else None,
        )
        chunks = [
            {
                "id": f"chk:{i:06d}:{j:03d}",
                "seq": j,
                "content": f"bench 文档 {i} 第 {j} 段 增值税 申报 指南",
                "title_seg": f"文档 {i}",
                "content_seg": f"bench 文档 {i} 第 {j} 段 增值税 申报 指南",
                "token_count": 12,
                "dims_json": json.dumps({k: dims[k] for k in sorted(dims)}),
            }
            for j in range(1, chunks_per_doc + 1)
        ]
        backend.insert(doc_id, 1, chunks)


# ============ 合成向量（零真实嵌入 API——确定性 unit float32[2560]） ============


def vector_cache_path(n: int) -> Path:
    return DATA_DIR / f"vectors-{n}-{VEC_DIM}-seed{SEED}.npy"


def synth_vectors(n: int) -> "Any":
    """n × 2560 单位向量（float32，PCG64 seed=SEED，norm=1）——首次生成落
    data/bench/*.npy 缓存，复跑直接 mmap（跨方言/跨轮取值一致）。"""
    import numpy as np

    cache = vector_cache_path(n)
    if cache.exists():
        return np.load(cache, mmap_mode="r")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    arr = np.empty((n, VEC_DIM), dtype=np.float32)
    step = 2000
    for lo in range(0, n, step):
        hi = min(lo + step, n)
        block = rng.standard_normal((hi - lo, VEC_DIM)).astype(np.float32)
        norms = np.linalg.norm(block, axis=1, keepdims=True)
        arr[lo:hi] = block / norms
    tmp = cache.with_suffix(".tmp.npy")
    np.save(tmp, arr)
    tmp.replace(cache)
    return np.load(cache, mmap_mode="r")


def vec_for_dialect(dialect: str, row: Any) -> Any:
    """合成向量 → 方言载荷：sqlite=vec_f32 BLOB（store/sqlite/vec.pack_f32）、
    pg=pgvector 文本（store/postgres/vec.format_vector）——序列化收口 store 层。"""
    if dialect == "sqlite":
        from knowledge_lattice.store.sqlite.vec import pack_f32

        return pack_f32([float(x) for x in row])
    from knowledge_lattice.store.postgres.vec import format_vector

    return format_vector([float(x) for x in row])


# ============ 计时采样（nearest-rank 分位） ============


def sample_timings(fn: Callable[[], Any], *, warmup: int, n: int) -> dict[str, float]:
    for _ in range(warmup):
        fn()
    xs: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        xs.append(time.perf_counter() - t0)
    xs.sort()
    return {
        "n": n,
        "min_ms": xs[0] * 1000,
        "p50_ms": xs[max(0, math.ceil(0.50 * n) - 1)] * 1000,
        "p95_ms": xs[max(0, math.ceil(0.95 * n) - 1)] * 1000,
        "max_ms": xs[-1] * 1000,
    }


# ============ 输出（stdout markdown + data/bench-results/*.json 工件） ============


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def save_result(tag: str, payload: dict[str, Any]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{tag}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def machine_profile(db: BenchDb | None = None) -> dict[str, str]:
    prof = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": str(os.cpu_count()),
        "sqlite_lib": sqlite3.sqlite_version,
        "seed": str(SEED),
        "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        import numpy

        prof["numpy"] = numpy.__version__
    except ImportError:  # pragma: no cover
        prof["numpy"] = "n/a"
    if db is not None and db.is_pg:
        prof["pg_server"] = db.execute("SELECT version()")[0][0].split(",")[0]
        import psycopg

        prof["psycopg"] = psycopg.__version__
    return prof


def print_header(title: str) -> None:
    print(f"\n## {title}\n", flush=True)
