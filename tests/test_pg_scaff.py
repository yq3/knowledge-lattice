"""PG spike 专用断言（M0b-1）：TC-SCAF-02/03 后端行 v1.4 + 审计按月分区表。

- TC-SCAF-02 PG 等价：连接池参数（min/max）+ pgvector `<=>` 距离函数可用 +
  连接工厂版本断言（server_version ≥ 16——G-6 收窄口径）；
- TC-SCAF-03 PG 等价：`schema_migrations` 表 + 约束校验（违例整事务回滚——
  PG 原生约束即时校验，无外键窗口）+ 幂等重放 + 并发 advisory lock 干净跳过
  + **版本只前进**（乱序补入小编号迁移 fail-fast——R2 P2-3）；
- 审计月库 → 按月分区表（§4 PG 映射）：分区滚动幂等、按月建新分区、append-only
  触发器在分区父表生效、写入落对应分区（接口 roll_monthly 不变）+
  **TRUNCATE 防护**（statement 级触发器覆盖父表与分区直接 TRUNCATE——R2 P2-4）；
- **时区契约钉 UTC**（R2 P2-1，用户拍板选项 A）：连接工厂统一 `SET TIME ZONE
  'UTC'`、存储 UTC（SQLite 既有语义对齐）；展示分工=后端吐 UTC、前端本地化渲染。
"""

from __future__ import annotations

import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# ============ TC-SCAF-02 PG 等价：连接池参数 + pgvector 距离函数 ============


def _public_audit_objects(pg_db) -> tuple[list, list, list]:
    """public 内 audit 对象三面清单（表/触发器/函数）。"""
    tables = pg_db.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        " AND tablename LIKE 'audit%%'"
    ).fetchall()
    triggers = pg_db.execute(
        "SELECT t.tgname FROM pg_trigger t"
        " JOIN pg_class c ON c.oid = t.tgrelid"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'public' AND t.tgname LIKE 'audit%%'"
    ).fetchall()
    funcs = pg_db.execute(
        "SELECT p.proname FROM pg_proc p"
        " JOIN pg_namespace n ON n.oid = p.pronamespace"
        " WHERE n.nspname = 'public' AND p.proname LIKE 'lattice_audit%%'"
    ).fetchall()
    return tables, triggers, funcs


def _assert_public_free_of_audit_objects(pg_db) -> None:
    """P2-2：工厂调用不得把 audit 对象泄漏到 public（schema 生命周期外）。"""
    tables, triggers, funcs = _public_audit_objects(pg_db)
    assert not (tables or triggers or funcs), (
        f"public 被 audit 对象污染（越出 lattice_test schema 生命周期）: "
        f"tables={tables} triggers={triggers} funcs={funcs}"
    )


@pytest.fixture()
def public_audit_guard(pg_db):
    """R2-P3-4：public audit 对象**幂等自清理** fixture——先清历史残留（若上一次
    运行/其他任务留下），yield 后再清一次（即便用例中途失败也不留痕迹）+ 断言
    public 三面零对象。两个工厂用例改用本 fixture（原裸断言不自清理）。"""
    def _cleanup() -> None:
        import psycopg

        admin = psycopg.connect(pg_db.dsn, autocommit=True)
        try:
            for obj in _public_audit_objects(pg_db)[1]:
                admin.execute(f'DROP TRIGGER IF EXISTS {obj[0]} ON audit_events')
            for name in ("audit_no_delete", "audit_no_update", "audit_no_truncate"):
                admin.execute(f"DROP FUNCTION IF EXISTS {name}() CASCADE")
            admin.execute("DROP TABLE IF EXISTS audit_events CASCADE")
        finally:
            admin.close()

    _cleanup()  # 幂等：历史残留先清（DROP IF EXISTS）
    yield pg_db
    _cleanup()
    _assert_public_free_of_audit_objects(pg_db)


def test_pg_connect_pool_params_and_probe(pg_db, public_audit_guard) -> None:
    """连接池 min/max 参数生效 + 池连接可执行 + `<=>` 余弦距离可用（同向量距离 0）。

    P2-2：池连接走 search_path=pg_db.schema（audit 对象留在测试 schema 内，
    随 DROP SCHEMA CASCADE 清理——不逃逸到 public）。R2-P3-4：public_audit_guard
    fixture 自清理（进出各清一次 + 断言三面零对象）。"""
    from knowledge_lattice.store.postgres import connect_pool

    pool = connect_pool(
        pg_db.dsn, min_size=1, max_size=2, name="scaf02-pool",
        search_path=f"{pg_db.schema},public",
    )
    try:
        assert pool.min_size == 1  # 连接池参数断言（TC-SCAF-02 后端行 v1.4）
        assert pool.max_size == 2
        with pool.connection() as conn:
            assert conn.execute("SELECT 1").fetchone()[0] == 1
            dist = conn.execute(
                "SELECT '[1.0, 2.0]'::vector <=> '[1.0, 2.0]'::vector"
            ).fetchone()[0]
            assert dist is not None and abs(float(dist)) < 1e-6  # 同向量余弦距离为 0
            # 池连接的 audit 对象落在测试 schema（非 public）
            assert conn.execute(
                "SELECT current_schema()"
            ).fetchone()[0] == pg_db.schema
    finally:
        pool.close()
    _assert_public_free_of_audit_objects(pg_db)


def test_pg_connect_factory_server_version_assert(pg_db, public_audit_guard) -> None:
    """连接工厂版本断言（≥16——G-6）：setup 后连接可查版本；16.15 实测通过。

    P2-2：单连接工厂调用同样走 search_path=pg_db.schema——public 无 audit 对象。"""
    from knowledge_lattice.store.postgres import connect

    conn = connect(pg_db.dsn, search_path=f"{pg_db.schema},public")
    try:
        version_num = int(
            conn.execute("SELECT current_setting('server_version_num')").fetchone()[0]
        )
        assert version_num >= 160000
        ext = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        assert ext is not None and ext[0].startswith("0.8")  # pgvector 0.8.x（G-6）
        assert conn.execute("SELECT current_schema()").fetchone()[0] == pg_db.schema
    finally:
        conn.close()
    _assert_public_free_of_audit_objects(pg_db)


# ============ R2 P2-1：时区契约钉 UTC（连接工厂统一 SET TIME ZONE 'UTC'） ============


def test_pg_factory_pins_utc_timezone(pg_db) -> None:
    """工厂后 session TimeZone == UTC（选项 A）。装置有效性：session 可改为非 UTC
    （模拟目标环境 Asia/Shanghai，墙上钟偏移 +8h 实测在场），setup_connection
    重入后必须回到 UTC——证明是工厂的 SET 在起作用，而非容器默认恰好为 UTC。"""
    from knowledge_lattice.store.postgres import setup_connection

    assert pg_db.execute("SHOW TimeZone").fetchone()[0] == "UTC"

    conn = pg_db.raw
    conn.execute("SET TIME ZONE 'Asia/Shanghai'")  # 模拟非 UTC 目标环境
    assert pg_db.execute("SHOW TimeZone").fetchone()[0] == "Asia/Shanghai"
    # 装置有效性：北京墙上钟（now()::timestamp）≠ UTC 墙上钟——偏移真实存在
    assert pg_db.execute(
        "SELECT now()::timestamp <> (now() AT TIME ZONE 'utc')::timestamp"
    ).fetchone()[0]

    setup_connection(conn)  # 工厂入口重入：SET TIME ZONE 'UTC'
    assert pg_db.execute("SHOW TimeZone").fetchone()[0] == "UTC"
    # 钉 UTC 后 CURRENT_TIMESTAMP::timestamp 即 UTC 墙上钟（DEFAULT 写入语义）
    assert pg_db.execute(
        "SELECT now()::timestamp = (now() AT TIME ZONE 'utc')::timestamp"
    ).fetchone()[0]


def test_pg_timezone_audit_default_now_writes_utc(pg_db) -> None:
    """审计 DEFAULT CURRENT_TIMESTAMP 写入 UTC 值（P2-1 效果断言）：钉 UTC 后
    created_at 与 UTC 墙上钟一致（分钟级）；未钉时（Asia/Shanghai 对照）墙上钟
    +8h——跨月界（UTC 月末 16:00~24:00 = 北京次月 0:00~8:00）会写错月、
    落不到已建分区（审计丢窗口）。"""
    from knowledge_lattice.store.postgres import setup_connection

    pg_db.execute(
        "INSERT INTO audit_events(id, org_id, actor, action, outcome)"
        " VALUES('evt:tznow', 'org:tax', 'user:u1', 'search', 'accepted')"
    )  # created_at 走 DEFAULT CURRENT_TIMESTAMP
    row_ts = pg_db.execute(
        "SELECT created_at FROM audit_events WHERE id = 'evt:tznow'"
    ).fetchone()[0]
    utc_wall = pg_db.execute(
        "SELECT (now() AT TIME ZONE 'utc')::timestamp"
    ).fetchone()[0]
    assert abs(row_ts - utc_wall) < timedelta(minutes=2)  # DEFAULT 写的是 UTC 墙上钟

    # 对照：未钉 UTC 的 session（Asia/Shanghai）墙上钟 +8h——若 DEFAULT 用它写入，
    # UTC 月末 16:30Z 的事件会写成次月值（分区路由错月）
    conn = pg_db.raw
    conn.execute("SET TIME ZONE 'Asia/Shanghai'")
    shanghai_wall = pg_db.execute("SELECT now()::timestamp").fetchone()[0]
    assert timedelta(hours=7, minutes=55) < (shanghai_wall - utc_wall) < timedelta(hours=8, minutes=5)
    setup_connection(conn)  # 恢复工厂纪律（UTC）——不留脏 session


def test_pg_timezone_grant_expiry_comparison_uses_utc(pg_db) -> None:
    """过期/有效授权对照判定（P2-1）：`expires_at > CURRENT_TIMESTAMP` 比较中
    timestamp 列按 session TimeZone 提升解释——钉 UTC 后 = SQLite 语义（UTC vs
    UTC）。对照：Asia/Shanghai session 下 UTC-1h 的已过期授权被误判为有效。"""
    from knowledge_lattice.store.postgres import setup_connection

    from helpers import (
        dim_id_for,
        seed_dim_value,
        seed_dimension,
        seed_grant,
        seed_membership,
        seed_org,
        seed_user,
        val_id_for,
    )

    now_utc = datetime.now(UTC)
    seed_org(pg_db)
    seed_dimension(pg_db, "org:tax", "region")
    seed_dim_value(pg_db, dim_id_for("org:tax", "region"), "CN")
    seed_dim_value(pg_db, dim_id_for("org:tax", "region"), "OS")
    seed_user(pg_db, "u_tz")
    seed_membership(pg_db, "u_tz", "org:tax")
    # 已过期授权（UTC 语义：expires_at = 当前 UTC 时刻 - 1h；取 CN）
    seed_grant(
        pg_db, user_id="u_tz", dim_id=dim_id_for("org:tax", "region"),
        val_id=val_id_for("org:tax", "region", "CN"),
        expires_at=(now_utc - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    # 有效授权对照（+1h；取 OS——PK 不同行）
    seed_grant(
        pg_db, user_id="u_tz", dim_id=dim_id_for("org:tax", "region"),
        val_id=val_id_for("org:tax", "region", "OS"),
        expires_at=(now_utc + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    backend = pg_db.make_backend()
    grants = backend.read_grants("u_tz", "org:tax")  # now=None：库时钟（CURRENT_TIMESTAMP）
    assert grants["region"] == ("OS",)  # -1h 过期被滤、+1h 保留——UTC vs UTC（SQLite 语义）

    # 对照：Asia/Shanghai session（未钉 UTC）——naive expires_at 被按北京墙钟解释
    # （= 绝对时刻提前 8h）→ +1h 的**有效**授权被误判过期（提前失效——P2-1 偏移实证）
    conn = pg_db.raw
    conn.execute("SET TIME ZONE 'Asia/Shanghai'")
    try:
        grants_shifted = backend.read_grants("u_tz", "org:tax")
        assert grants_shifted["region"] == ()  # 有效授权被提前 8h 误杀
    finally:
        setup_connection(conn)  # 恢复工厂纪律（UTC）


def _db_level_timezone(admin) -> str | None:
    """读库级默认 timezone（pg_db_role_setting；无库级设置 → None=簇默认）。"""
    row = admin.execute(
        "SELECT s.setconfig FROM pg_db_role_setting s"
        " JOIN pg_database d ON d.oid = s.setdatabase"
        " WHERE d.datname = current_database()"
    ).fetchone()
    if not row or not row[0]:
        return None
    for item in row[0]:
        if item.startswith("timezone="):
            return item.split("=", 1)[1]
    return None


def test_pg_pool_connections_pinned_utc_against_non_utc_db_default(pg_db) -> None:
    """非 UTC 数据库默认（ALTER DATABASE timezone='Asia/Shanghai'——模拟公司
    内网 PG）下，**新建**工厂连接（池 configure / 单连接 setup）仍被钉 UTC：
    P2-1 的目标环境级对冲（容器默认恰为 UTC 时其余时区用例无区分力，本用例
    构造非 UTC 默认补齐）。

    R2-P3-1 可移植性：库名经 current_database() 推导（不硬编码 lattice——
    公司内网库名任意）；finally 按**原库级默认**还原（原无库级设置 → RESET 回
    簇默认；原有设置 → 恢复原值——不留测试痕迹）。"""
    import psycopg

    from knowledge_lattice.store.postgres import connect, connect_pool

    admin = psycopg.connect(pg_db.dsn, autocommit=True)
    original_tz = _db_level_timezone(admin)  # 保存原库级默认（R2-P3-1）
    admin.execute(
        f"ALTER DATABASE {admin.execute('SELECT current_database()').fetchone()[0]}"
        " SET timezone TO 'Asia/Shanghai'"
    )
    pool = None
    conn = None
    try:
        # 默认（未钉）行为的装置有效性：raw 新连接拿到的即 Asia/Shanghai
        probe = psycopg.connect(pg_db.dsn, autocommit=True)
        assert probe.execute("SHOW TimeZone").fetchone()[0] == "Asia/Shanghai"
        probe.close()

        pool = connect_pool(
            pg_db.dsn, min_size=1, max_size=1, name="tz-pool",
            search_path=f"{pg_db.schema},public",
        )
        with pool.connection() as pc:
            assert pc.execute("SHOW TimeZone").fetchone()[0] == "UTC"  # 池连接被钉 UTC
        conn = connect(pg_db.dsn, search_path=f"{pg_db.schema},public")
        assert conn.execute("SHOW TimeZone").fetchone()[0] == "UTC"  # 单连接同纪律
    finally:
        db_name = admin.execute("SELECT current_database()").fetchone()[0]
        if original_tz is None:
            admin.execute(f"ALTER DATABASE {db_name} RESET timezone")  # 还原簇默认
        else:
            admin.execute(
                f"ALTER DATABASE {db_name} SET timezone TO '{original_tz}'"
            )
        admin.close()
        if pool is not None:
            pool.close()
        if conn is not None:
            conn.close()


# ============ R2 P2-4：TRUNCATE 防护（statement 级触发器——父表 + 分区） ============


def test_pg_audit_truncate_blocked_parent_and_partition(pg_db) -> None:
    """TRUNCATE 不触发行级触发器（SQLite 无 TRUNCATE 无此缺口——#33 P2-10 等价
    要求）：父表与分区直接 TRUNCATE 均被 statement 级 BEFORE TRUNCATE 触发器
    拦截（消息同源 append-only 文案），审计行完好。"""
    from knowledge_lattice.store.postgres.audit import ensure_month_partition

    ensure_month_partition(pg_db.raw, when=datetime(2026, 10, 15, tzinfo=UTC))
    pg_db.execute(
        "INSERT INTO audit_events(id, org_id, actor, action, outcome, created_at)"
        " VALUES('evt:tr', 'org:tax', 'user:u1', 'search', 'accepted', '2026-10-05 00:00:00')"
    )
    assert pg_db.execute(
        "SELECT count(*) FROM audit_events_202610 WHERE id = 'evt:tr'"
    ).fetchone()[0] == 1

    with pytest.raises(pg_db.integrity_error, match="append-only"):
        pg_db.execute("TRUNCATE audit_events")  # 父表形态
    with pytest.raises(pg_db.integrity_error, match="append-only"):
        pg_db.execute("TRUNCATE audit_events_202610")  # 分区直接 TRUNCATE 形态
    assert pg_db.execute(
        "SELECT count(*) FROM audit_events_202610 WHERE id = 'evt:tr'"
    ).fetchone()[0] == 1  # 审计行完好


# ============ TC-SCAF-03 PG 等价：schema_migrations + 约束校验 + 幂等/并发 ============


def test_pg_fresh_migrate_schema_v1(pg_db) -> None:
    """全新 schema 迁移：schema_migrations 落 [1, 2]（v1 全量 + v1.1 分表——M0b-3）；
    表落库（15 主表 + chunk_vectors 分表 + 工厂滚动 audit_events 分区表——主库
    schema 不含）；sem_* 不在；chunks 五列 tsvector GENERATED 在场（FTS5 虚表 +
    ai/ad/au 的 PG 等价物）。"""
    from knowledge_lattice.store.postgres.migrate import BUILTIN_DIRS, discover

    rows = pg_db.execute(
        "SELECT version, name, domain FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert rows == [(1, "schema_v1", "docs"), (2, "schema_v1_1", "docs")]

    names = pg_db.table_names()
    expected = {
        "orgs", "datasets", "dimensions", "dimension_values", "users",
        "user_org_memberships", "user_dimension_grants", "documents",
        "document_dimensions", "acl_entries", "chunks", "chunk_vectors",
        "quality_flags", "tasks", "embedding_fingerprints", "audit_outbox",
    }
    assert expected <= names, f"missing tables: {expected - names}"
    assert "audit_events" in names  # 连接工厂滚动的分区父表（月库的 PG 等价）
    assert "audit_events_" in " ".join(names)  # 当月分区
    assert not {n for n in names if n.startswith("sem_")}
    assert "chunks_fts" not in names  # 无 FTS5 虚表——tsvector 五列 GENERATED 取代

    # 五列 GENERATED（attgenerated='s'）——ai/ad/au 触发器的等价形态
    generated = {
        r[0]
        for r in pg_db.execute(
            "SELECT a.attname FROM pg_attribute a"
            " WHERE a.attrelid = 'chunks'::regclass AND a.attgenerated = 's'"
        )
    }
    assert generated == {
        "title_tsv", "content_tsv", "keywords_tsv", "llm_keywords_tsv", "tags_tsv",
    }

    # v1.1（M0b-3）：chunks.embedding/dims_json 已删；向量列迁 chunk_vectors
    #（pgvector；`<=>` 可用已在工厂断言/距离测试覆盖——G-6 精确扫描起步）
    chunk_cols = {
        r[0]
        for r in pg_db.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'chunks'"
        )
    }
    assert "embedding" not in chunk_cols and "dims_json" not in chunk_cols
    cv_type = pg_db.execute(
        "SELECT udt_name FROM information_schema.columns"
        " WHERE table_schema = current_schema() AND table_name = 'chunk_vectors'"
        "   AND column_name = 'embedding'"
    ).fetchone()[0]
    assert cv_type == "vector"
    cv_pk = pg_db.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
        " WHERE conrelid = 'chunk_vectors'::regclass AND contype = 'p'"
    ).fetchone()[0]
    assert 'PRIMARY KEY (rid, embed_model)' in cv_pk  # 蓝绿键形（报告 §3.5）

    # 迁移目录二维结构 store/postgres/migrations/{docs,semantic}（semantic 空占位）
    assert (BUILTIN_DIRS["docs"] / "0001_schema_v1.sql").is_file()
    assert (BUILTIN_DIRS["docs"] / "0002_schema_v1_1.sql").is_file()
    assert BUILTIN_DIRS["semantic"].is_dir()
    assert [m.version for m in discover()] == [1, 2]


def test_pg_migrate_idempotent_rerun(pg_db, tmp_path: Path) -> None:
    """幂等重放：再跑迁移无新版本应用、数据不动。"""
    from knowledge_lattice.store.postgres import migrate_db

    from helpers import seed_dataset, seed_org

    seed_org(pg_db)
    seed_dataset(pg_db)
    before = pg_db.execute("SELECT count(*) FROM datasets").fetchone()[0]
    assert migrate_db(pg_db.raw) == []
    assert pg_db.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall() == [(1,), (2,)]
    assert pg_db.execute("SELECT count(*) FROM datasets").fetchone()[0] == before


def _write_pg_v3(tmp_path: Path, violation: bool) -> Path:
    """构造 v3 测试迁移（0002 已被 schema v1.1 占用——M0b-3）：加 remark 列；
    （violation=True 时）再插一行违反外键的数据——同事务内约束违例 → 整事务回滚
    （PG 原生约束即时校验，无外键窗口）。"""
    mig_dir = tmp_path / "pg_extra_migrations"
    mig_dir.mkdir(parents=True, exist_ok=True)
    sql = "-- 0003 测试迁移：dimensions 加 remark 列\nALTER TABLE dimensions ADD COLUMN remark TEXT;\n"
    if violation:
        sql += (
            "-- 违例行（引用不存在 user）：PG 原生外键即时拒绝 → 整事务回滚\n"
            "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id)"
            " SELECT 'ghost-user', id, id FROM dimensions LIMIT 1;\n"
        )
    (mig_dir / "0003_test_add_remark.sql").write_text(sql, encoding="utf-8")
    return mig_dir


def test_pg_migration_applies_and_tracks_schema_migrations(pg_db, tmp_path: Path) -> None:
    """正常迁移：v3 应用后 schema_migrations 前进到 3、DDL 生效、数据保真。"""
    from knowledge_lattice.store.postgres import migrate_db

    from helpers import seed_dimension, seed_org

    seed_org(pg_db)
    seed_dimension(pg_db)
    dirs = [_write_pg_v3(tmp_path, violation=False)]

    applied = migrate_db(pg_db.raw, dirs=dirs)
    assert applied == [3]
    assert pg_db.execute(
        "SELECT version, name FROM schema_migrations ORDER BY version"
    ).fetchall() == [
        (1, "schema_v1"), (2, "schema_v1_1"), (3, "test_add_remark"),
    ]
    cols = {
        r[0]
        for r in pg_db.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'dimensions'"
        )
    }
    assert "remark" in cols
    assert pg_db.execute("SELECT key FROM dimensions").fetchone()[0] == "region"
    # 幂等重放：再跑无新版本
    assert migrate_db(pg_db.raw, dirs=dirs) == []


def test_pg_migration_out_of_order_rejected(pg_db, tmp_path: Path) -> None:
    """R2 P2-3 版本只前进：先应用 0003、后补入 0002 → 未应用且 ≤ 已应用水位
    （MAX）→ MigrationError fail-fast，绝不乱序应用（SQLite user_version 单调
    语义等价）；0003 已应用不重放、库态不被乱序 DDL 触碰。"""
    from knowledge_lattice.store.postgres import migrate_db
    from knowledge_lattice.store.postgres.migrate import BUILTIN_DIRS, MigrationError

    d4 = tmp_path / "only_v4"
    d4.mkdir()
    (d4 / "0004_test_add_col4.sql").write_text(
        "-- 0004 测试迁移：dimensions 加 col4 列\nALTER TABLE dimensions ADD COLUMN col4 TEXT;\n",
        encoding="utf-8",
    )
    d34 = tmp_path / "v3_and_v4"
    d34.mkdir()
    (d34 / "0003_test_backfill.sql").write_text(
        "-- 0003 补入迁移（乱序场景：水位已到 4）\nALTER TABLE dimensions ADD COLUMN col3 TEXT;\n",
        encoding="utf-8",
    )
    (d34 / "0004_test_add_col4.sql").write_text(
        "-- 0004 测试迁移：dimensions 加 col4 列\nALTER TABLE dimensions ADD COLUMN col4 TEXT;\n",
        encoding="utf-8",
    )

    # 先应用 0004（跳过 0003 —— 目录里本来就没有；内置 0001+0002 已随 fixture 应用）
    assert migrate_db(pg_db.raw, dirs=[BUILTIN_DIRS["docs"], d4]) == [4]

    # 后补入 0003：未应用且 3 <= MAX(applied)=4 → fail-fast
    with pytest.raises(MigrationError, match="0003|只前进|out-of-order"):
        migrate_db(pg_db.raw, dirs=[BUILTIN_DIRS["docs"], d34])

    # 库态：0003 的 DDL 绝未执行、0004 不重放、版本水位不动
    cols = {
        r[0]
        for r in pg_db.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'dimensions'"
        )
    }
    assert "col3" not in cols
    assert "col4" in cols
    assert pg_db.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall() == [(1,), (2,), (4,)]


def test_pg_migration_violation_rolls_back_atomically(pg_db, tmp_path: Path) -> None:
    """违例回滚：v3 含外键违例 INSERT → 迁移失败、schema_migrations 不前进、
    已执行 DDL 一并回滚（库态与迁移前一致）——TC-SCAF-03 后端行「约束校验
    （违例回滚）」。"""
    import psycopg

    from knowledge_lattice.store.postgres import migrate_db
    from knowledge_lattice.store.postgres.migrate import BUILTIN_DIRS

    from helpers import seed_dimension, seed_org

    seed_org(pg_db)
    seed_dimension(pg_db)
    bad_dirs = [BUILTIN_DIRS["docs"], _write_pg_v3(tmp_path, violation=True)]

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrate_db(pg_db.raw, dirs=bad_dirs)

    # 回滚后库态与迁移前一致：版本未前进（停在 v1.1）、DDL 未生效
    assert pg_db.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall() == [(1,), (2,)]
    cols = {
        r[0]
        for r in pg_db.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'dimensions'"
        )
    }
    assert "remark" not in cols
    assert pg_db.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'ghost-user'"
    ).fetchone()[0] == 0

    # 修复后同号迁移可正常应用（无残留半成品）
    good_dirs = [BUILTIN_DIRS["docs"], _write_pg_v3(tmp_path / "good", violation=False)]
    assert migrate_db(pg_db.raw, dirs=good_dirs) == [3]


def test_pg_concurrent_migrate_advisory_lock_clean_skip(pg_db, tmp_path: Path) -> None:
    """并发语义：双连接 barrier 对齐跑迁移——advisory lock 序列化，一者应用、
    另一者在锁内重读已应用版本后干净跳过（不撞 already exists、恰应用一次）。"""
    import psycopg

    from knowledge_lattice.store.postgres import migrate_db
    from knowledge_lattice.store.postgres.migrate import BUILTIN_DIRS

    dirs = [BUILTIN_DIRS["docs"], _write_pg_v3(tmp_path, violation=False)]
    schema = pg_db.schema

    barrier = threading.Barrier(2)
    results: list[list[int] | BaseException] = []

    def run_migrate() -> None:
        c = psycopg.connect(pg_db.dsn, autocommit=True)
        try:
            c.execute(f'SET search_path TO "{schema}", public')
            barrier.wait(timeout=10)
            results.append(migrate_db(c, dirs=dirs))
        except BaseException as exc:  # noqa: BLE001——记录失败供断言
            results.append(exc)
        finally:
            c.close()

    t = threading.Thread(target=run_migrate)
    t.start()
    run_migrate()
    t.join(timeout=30)

    assert len(results) == 2
    failures = [r for r in results if isinstance(r, BaseException)]
    assert failures == [], f"concurrent migrate crashed: {failures!r}"
    flattened = sorted(v for r in results for v in r)  # type: ignore[union-attr]
    assert flattened == [3]  # 恰好应用一次，另一连接干净跳过


# ============ P3-6（M0b-1 移交，M0b-3 清偿）：schema_migrations 锁外竞态 ============


def test_pg_ensure_schema_migrations_survives_duplicate_table_race(pg_db) -> None:
    """P3-6：_ensure_schema_migrations 在 advisory lock 之外执行，并发 fresh 连接
    同跑 CREATE TABLE IF NOT EXISTS 可抛 42P07 DuplicateTable（PG 该语句对并发建表
    非原子）——确定性模拟：包装连接令首条 CREATE 语句抛 DuplicateTable 后表已在
    场，恢复分支复核存在即干净继续（不重抛、不崩溃）。"""
    from psycopg import errors as pg_errors

    from knowledge_lattice.store.postgres.migrate import _ensure_schema_migrations

    class _RaceConn:
        """并发竞态模拟：CREATE TABLE IF NOT EXISTS schema_migrations 首次调用
        抛 DuplicateTable（对端刚建好），其余语句透传真实连接。"""

        def __init__(self, real) -> None:
            self._real = real

        def execute(self, sql, params=None):
            if sql.strip().startswith("CREATE TABLE IF NOT EXISTS schema_migrations"):
                raise pg_errors.DuplicateTable(
                    'relation "schema_migrations" already exists'
                )
            return self._real.execute(sql, params)

    # ① 恢复分支：表已在场（对端已建好）→ 复核存在 → 干净返回、不重抛
    _ensure_schema_migrations(_RaceConn(pg_db.raw))
    assert pg_db.execute(
        "SELECT count(*) FROM schema_migrations"
    ).fetchone()[0] >= 1  # 表仍可用

    # ② fail-closed：表确实不在（DROP 后）→ 同款 42P07 照抛（不静默吞）
    pg_db.execute("DROP TABLE schema_migrations")
    with pytest.raises(pg_errors.DuplicateTable):
        _ensure_schema_migrations(_RaceConn(pg_db.raw))
    # 真实路径恢复：无注入时正常重建（独立于上面两条断言面）
    from knowledge_lattice.store.postgres.migrate import _ensure_schema_migrations as _ens

    _ens(pg_db.raw)


# ============ 审计月库 → 按月分区表（§4 PG 映射） ============


def test_pg_audit_partition_rolling_idempotent(pg_db) -> None:
    """分区滚动幂等：同月重复 ensure 不重复建、返回同名；跨月滚动建新分区。"""
    from knowledge_lattice.store.postgres.audit import ensure_month_partition

    conn = pg_db.raw
    oct_ = ensure_month_partition(conn, when=datetime(2026, 10, 15, tzinfo=UTC))
    oct_again = ensure_month_partition(conn, when=datetime(2026, 10, 31, tzinfo=UTC))
    nov = ensure_month_partition(conn, when=datetime(2026, 11, 1, tzinfo=UTC))
    assert oct_ == oct_again == "audit_events_202610"
    assert nov == "audit_events_202611"

    parts = {
        r[0]
        for r in pg_db.execute(
            "SELECT tablename FROM pg_tables"
            " WHERE schemaname = current_schema() AND tablename LIKE 'audit_events_%%'"
        )
    }
    assert {"audit_events_202610", "audit_events_202611"} <= parts

    # 写入落对应分区（RANGE 按 created_at）
    pg_db.execute(
        "INSERT INTO audit_events(id, org_id, actor, action, outcome, created_at)"
        " VALUES('evt:oct', 'org:tax', 'user:u1', 'search', 'accepted', '2026-10-15 00:00:00')"
    )
    pg_db.execute(
        "INSERT INTO audit_events(id, org_id, actor, action, outcome, created_at)"
        " VALUES('evt:nov', 'org:tax', 'user:u1', 'search', 'accepted', '2026-11-02 00:00:00')"
    )
    assert pg_db.execute(
        "SELECT count(*) FROM audit_events_202610"
    ).fetchone()[0] == 1
    assert pg_db.execute(
        "SELECT count(*) FROM audit_events_202611"
    ).fetchone()[0] == 1
    assert pg_db.execute(
        "SELECT count(*) FROM audit_events"
    ).fetchone()[0] == 2  # 父表全量可见


def test_pg_audit_append_only_triggers(pg_db) -> None:
    """append-only：UPDATE/DELETE 均被拒（分区父表上的行级触发器——消息与 sqlite
    月库版逐字同源；#33 P2-10）。"""
    pg_db.execute(
        "INSERT INTO audit_events(id, org_id, actor, action, outcome)"
        " VALUES('evt:1', 'org:tax', 'user:u1', 'search', 'accepted')"
    )
    for sql in (
        "UPDATE audit_events SET action='grant' WHERE id='evt:1'",
        "DELETE FROM audit_events WHERE id='evt:1'",
    ):
        with pytest.raises(pg_db.integrity_error, match="append-only"):
            pg_db.execute(sql)


def test_pg_factory_rolls_current_month_partition(pg_db) -> None:
    """连接工厂滚动当月分区（setup_connection 内 ensure_audit——与 sqlite 连接工厂
    滚动当月月库同语义）。"""
    month = datetime.now(UTC).strftime("%Y%m")
    assert f"audit_events_{month}" in pg_db.table_names()
    # roll_monthly 接口不变（AuditBackend 协议——月库/分区差异在包内吸收）
    backend = pg_db.make_backend()
    assert backend.roll_monthly(datetime(2026, 5, 1, tzinfo=UTC)) == "audit_events_202605"


# ============ R2 P3-3：PG 渲染器恶意 key 安全回归（M0a-2 R2 纪律双后端锁死） ============

_EVIL_KEY = "x_0) OR 1=1)) --"  # 与 sqlite 侧 test_r2_review_fixes 同款攻击配方
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_OUTSIDE_LITERALS = re.compile(r"'(?:[^']|'')*'")


def test_pg_invalue_rejects_non_identifier_param_prefix() -> None:
    """param_prefix 白名单 fail-closed（约束在共享 acl_ast.InValue——双方言同受）：
    恶意前缀构造即拒；合法标识符照常接受（trace 标签，不进入 SQL）。"""
    from knowledge_lattice.store.acl_ast import ColumnRef, InValue

    for evil in (_EVIL_KEY, "ds; DROP TABLE chunks;--", "a b", "1abc", ""):
        with pytest.raises(ValueError, match="InValue.param_prefix"):
            InValue(expr=ColumnRef("je", "value"), param_prefix=evil, values=("A",))
    InValue(expr=ColumnRef("je", "value"), param_prefix="dim0", values=("A",))


def test_pg_malicious_dimension_key_constants_intact_and_no_cross_org_leak(pg_db) -> None:
    """恶意维度 key（库内数据）下 PG 渲染产物：外层常量齐全（org/版本/tombstone）、
    参数名全为合法标识符（渲染器自控 g<seq>_<i> 序列）、注释记号不出现在字面量外、
    恶意 key 只以转义后的字面量出现（jsonb_extract_path 第二参）；双组织真实
    执行无跨组织行（org:gl 文档绝不出现——含空维度放行文档）。"""
    from knowledge_lattice.core.docs.acl import compile_acl

    from helpers import (
        dim_id_for,
        grant_by_key,
        seed_dataset,
        seed_dim_value,
        seed_dimension,
        seed_grant,
        seed_membership,
        seed_org,
        seed_searchable_doc,
        seed_user,
    )

    for org in ("org:tax", "org:gl"):
        seed_org(pg_db, org)
        seed_dataset(pg_db, org, f"ds:{org}")
        seed_dimension(pg_db, org, "region")
        seed_dim_value(pg_db, dim_id_for(org, "region"), "CN")
        seed_dim_value(pg_db, dim_id_for(org, "region"), "OS")
    seed_user(pg_db, "u_tax")
    seed_membership(pg_db, "u_tax", "org:tax")
    grant_by_key(pg_db, "u_tax", key="region", value="CN")
    # 攻击配方：先有维度 x（绑定 g0_0），再以恶意 key 维度试图截断参数名注入注释
    for key in ("x", _EVIL_KEY):
        dim_id = seed_dimension(pg_db, "org:tax", key)
        val_id = seed_dim_value(pg_db, dim_id, "A")
        seed_grant(pg_db, user_id="u_tax", dim_id=dim_id, val_id=val_id)
    seed_user(pg_db, "u_gl_owner")
    seed_membership(pg_db, "u_gl_owner", "org:gl")
    seed_searchable_doc(
        pg_db, "d_tax", org_id="org:tax", dataset_id="ds:org:tax",
        dims={"region": ["CN"]}, owner_user_id="u_tax",
    )
    seed_searchable_doc(
        pg_db, "d_gl", org_id="org:gl", dataset_id="ds:org:gl",
        dims={"region": ["OS"]}, owner_user_id="u_gl_owner",
    )
    seed_searchable_doc(  # 空维度文档——org 常量被注释时的越权出口
        pg_db, "d_gl_empty", org_id="org:gl", dataset_id="ds:org:gl",
        owner_user_id="u_gl_owner",
    )

    backend = pg_db.make_backend()
    plan = compile_acl(backend, "u_tax", "org:tax", now="2026-06-01 12:00:00")
    rules = {r.key: r for r in plan.dimension_rules}
    assert rules[_EVIL_KEY].grants == ("A",)  # 授权展开照常——key 作为数据参与

    sql, params = pg_db.render_select(plan)
    for fragment in (
        "d.org_id = %(org)s", "c.version = d.active_version", "c.tombstone = 0",
    ):
        assert fragment in sql, fragment  # 外层常量未被截断/注释
    assert params["org"] == "org:tax"
    for name in params:
        assert _IDENTIFIER.fullmatch(name), f"非法参数名: {name!r}"
    stripped = _OUTSIDE_LITERALS.sub("''", sql)
    assert "--" not in stripped and "/*" not in stripped  # 注释记号不出现在字面量外
    # 恶意 key 只以转义后的字面量出现（jsonb_extract_path 第二参——Literal 渲染）
    assert f"'{_EVIL_KEY}'" in sql
    # 行为：真实执行 org 隔离成立——org:gl 文档（含空维度文档）绝不出现
    assert {r[2] for r in pg_db.execute(sql, params)} == {"d_tax"}
