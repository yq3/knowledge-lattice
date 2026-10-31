"""schema v1.1 迁移与蓝绿形态【单测｜M0b-3——TC-E2E-05 / TC-SCAF-03 v1.1 复跑】。

三项拍板落库（2026-10-24 用户确认"按建议执行"，报告 §0/§2.6/§3.5）：

- 拍板 1：删 chunks.dims_json——visible_docs+MATERIALIZED 唯一路径（json_each
  模板随删；本文件断言列删除与 CTE 竞态口径）；
- 拍板 2：分表 chunk_vectors(rid, embed_model, embedding) PK(rid, embed_model)
  + 删 chunks.embedding（存量向量 INSERT..SELECT 搬运——空库/有库两形态）
  + chunks.embed_model 保留为摄取状态标签；
- 拍板 3：重嵌入方案二（分表蓝绿）——同 rid 多标签并存可插、新标签谓词只命中
  新标签、块删级联清（完整流程 M2；runbook 见 RUNBOOK.md 引用报告 §3.5）。
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import psycopg
import pytest

from helpers import (
    NOW_TS,
    insert_chunk,
    seed_dataset,
    seed_dim_value,
    seed_dimension,
    seed_doc_dims,
    seed_document,
    seed_grant,
    seed_membership,
    seed_org,
    seed_searchable_doc,
    seed_user,
)


# ============ v1 旧形态库构造（只应用 0001 → 造数 → 应用 0002） ============


def _v1_dirs(tmp_path: Path) -> list[Path]:
    """只含 0001 的迁移目录（v1 旧形态库——存量搬运测试的前置）。"""
    from knowledge_lattice.store.sqlite.migrate import BUILTIN_DIRS

    v1 = tmp_path / "v1only"
    v1.mkdir(parents=True)
    (v1 / "0001_schema_v1.sql").write_text(
        (BUILTIN_DIRS["docs"] / "0001_schema_v1.sql").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return [v1]


def test_sqlite_0002_migrates_legacy_vectors_and_drops_columns(tmp_path: Path) -> None:
    """有库形态：v1 库存量向量 INSERT..SELECT 搬运到 chunk_vectors 后删列
    （dims_json/embedding 双删、embed_model 标签保留、待嵌行不搬运）。"""
    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.vec import pack_f32, unpack_f32

    conn = connect(tmp_path / "legacy.db")
    try:
        assert migrate_db(conn, dirs=_v1_dirs(tmp_path)) == [1]  # v1 旧形态
        seed_org(conn)
        seed_dataset(conn)
        seed_user(conn, "u0")
        seed_document(conn, doc_id="d1", owner_user_id="u0")
        # 两行带向量（不同标签载荷）+ 一行钉标签待嵌（无向量）+ 一行完全未嵌
        vec_a, vec_b = [0.5, -0.5, 1.0], [1.0, 0.0]
        insert_chunk(
            conn, doc_id="d1", seq=1, version=1, chunk_id="chk:a",
            dims_json='{"region": ["CN"]}', embed_model="m:old", embedding=pack_f32(vec_a),
        )
        insert_chunk(
            conn, doc_id="d1", seq=2, version=1, chunk_id="chk:b",
            dims_json='{"region": ["CN"]}', embed_model="m:old", embedding=pack_f32(vec_b),
        )
        insert_chunk(
            conn, doc_id="d1", seq=3, version=1, chunk_id="chk:pending",
            dims_json='{}', embed_model="m:old",  # 钉标签未回写——不搬运
        )
        insert_chunk(
            conn, doc_id="d1", seq=4, version=1, chunk_id="chk:raw", dims_json='{}'
        )
        # 孤立行（embedding 非空、embed_model NULL——非法态）：迁移显式丢弃（P3-5）
        insert_chunk(
            conn, doc_id="d1", seq=5, version=1, chunk_id="chk:orphan", dims_json='{}',
            embedding=pack_f32([9.0, 9.0]),
        )

        applied = migrate_db(conn)  # 默认目录 → 0002~0007（v1.1 搬运 + M1-3 uploads + M2.1×2 + M2-S1 semantic_v1 + m2s-3 semantic_yaml）
        assert applied == [2, 3, 4, 5, 6, 7]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        # 列删除：dims_json/embedding 双删；embed_model 保留为摄取状态标签
        cols = {r[1] for r in conn.execute("PRAGMA table_info(chunks)")}
        assert "dims_json" not in cols and "embedding" not in cols
        assert "embed_model" in cols

        # 存量搬运正确：chunk_vectors 行数 = 原合法成对行数（2），载荷逐字节保真
        rows = conn.execute(
            "SELECT c.id, cv.embed_model, cv.embedding FROM chunk_vectors cv"
            " JOIN chunks c ON c.rid = cv.rid ORDER BY c.seq"
        ).fetchall()
        assert [(r[0], r[1]) for r in rows] == [("chk:a", "m:old"), ("chk:b", "m:old")]
        assert unpack_f32(rows[0][2]) == pytest.approx(vec_a)
        assert unpack_f32(rows[1][2]) == pytest.approx(vec_b)

        # P3-5：孤立行（embedding 非空、embed_model NULL）被迁移丢弃——不进
        # chunk_vectors（非法态无从归属模型；0002 双守关显式声明）
        assert conn.execute(
            "SELECT count(*) FROM chunk_vectors cv JOIN chunks c ON c.rid = cv.rid"
            " WHERE c.id = 'chk:orphan'"
        ).fetchone()[0] == 0

        # 待嵌行不搬运、标签保留（断点续跑清单仍可按标签清点）
        assert conn.execute(
            "SELECT embed_model FROM chunks WHERE id = 'chk:pending'"
        ).fetchone()[0] == "m:old"
        assert conn.execute(
            "SELECT count(*) FROM chunk_vectors cv JOIN chunks c ON c.rid = cv.rid"
            " WHERE c.id IN ('chk:pending', 'chk:raw')"
        ).fetchone()[0] == 0

        # 幂等重放：再跑无新版本应用、数据不动
        assert migrate_db(conn) == []
        assert conn.execute("SELECT count(*) FROM chunk_vectors").fetchone()[0] == 2
    finally:
        conn.close()


def test_sqlite_0002_fresh_empty_db(tmp_path: Path) -> None:
    """空库形态：全新库直接迁移到 v1.1（INSERT..SELECT 空集零行、DDL 全过）。"""
    from knowledge_lattice.store.sqlite import connect, migrate_db

    conn = connect(tmp_path / "fresh.db")
    try:
        assert migrate_db(conn) == [1, 2, 3, 4, 5, 6, 7]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT count(*) FROM chunk_vectors").fetchone()[0] == 0
        cols = {r[1] for r in conn.execute("PRAGMA table_info(chunks)")}
        assert "dims_json" not in cols and "embedding" not in cols
        # 版本只前进：v1 目录重放不回退（user_version 只前进语义）
        assert migrate_db(conn, dirs=_v1_dirs(tmp_path / "again")) == []
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    finally:
        conn.close()


def test_pg_0002_migrates_legacy_vectors_and_drops_columns(tmp_path: Path) -> None:
    """PG 有库形态：v1 库搬运 + 删列 + 幂等 + 版本记录（sqlite 同构）。"""
    import os

    dsn = os.environ.get("LATTICE_PG_DSN")
    if not dsn:
        pytest.skip("LATTICE_PG_DSN 未设置（门禁将 skip 视为失败）")
    from knowledge_lattice.store.postgres import migrate_db as pg_migrate_db
    from knowledge_lattice.store.postgres import setup_connection
    from knowledge_lattice.store.postgres.migrate import BUILTIN_DIRS as PG_DIRS

    v1 = tmp_path / "pg_v1only"
    v1.mkdir()
    (v1 / "0001_schema_v1.sql").write_text(
        (PG_DIRS["docs"] / "0001_schema_v1.sql").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    schema = f"lattice_v11_{uuid.uuid4().hex[:10]}"
    raw = psycopg.connect(dsn, autocommit=True)
    try:
        raw.execute(f'CREATE SCHEMA "{schema}"')
        raw.execute(f'SET search_path TO "{schema}", public')
        setup_connection(raw)
        assert pg_migrate_db(raw, dirs=[v1]) == [1]
        raw.execute("INSERT INTO orgs(id, name) VALUES('org:tax', 't')")
        raw.execute("INSERT INTO users(id, username) VALUES('u1', 'u1')")
        raw.execute("INSERT INTO datasets(id, org_id, name) VALUES('ds:vat', 'org:tax', 'n')")
        raw.execute("INSERT INTO users(id, username) VALUES('u0', 'u0')")
        raw.execute(
            "INSERT INTO documents(id, org_id, dataset_id, title, content_hash, mime_type,"
            " parser, owner_user_id, raw_object_key)"
            " VALUES('d1', 'org:tax', 'ds:vat', 't', 'sha256:x', 'text/plain', 'docling', 'u0', 'o/x')"
        )
        for seq, (cid, vec) in enumerate((("chk:a", "[0.5,-0.5,1.0]"), ("chk:b", "[1.0,0.0]")), 1):
            raw.execute(
                "INSERT INTO chunks(id, doc_id, seq, version, content, dims_json,"
                " embed_model, embedding)"
                " VALUES(%(id)s, 'd1', %(seq)s, 1, 'x', '{\"region\": [\"CN\"]}'::jsonb,"
                " 'm:old', %(vec)s::vector)",
                {"id": cid, "seq": seq, "vec": vec},
            )
        raw.execute(
            "INSERT INTO chunks(id, doc_id, seq, version, content, dims_json, embed_model)"
            " VALUES('chk:pending', 'd1', 3, 1, 'x', '{}'::jsonb, 'm:old')"
        )

        assert pg_migrate_db(raw) == [2, 3, 4, 5, 6, 7]  # 默认目录 → 0002~0007（… + M2-S1 semantic_v1 + m2s-3 semantic_yaml）
        versions = [r[0] for r in raw.execute("SELECT version FROM schema_migrations ORDER BY version")]
        assert versions == [1, 2, 3, 4, 5, 6, 7]

        cols = {
            r[0]
            for r in raw.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = current_schema() AND table_name = 'chunks'"
            )
        }
        assert "dims_json" not in cols and "embedding" not in cols
        assert "embed_model" in cols

        rows = raw.execute(
            "SELECT c.id, cv.embed_model, cv.embedding::text FROM chunk_vectors cv"
            " JOIN chunks c ON c.rid = cv.rid ORDER BY c.seq"
        ).fetchall()
        assert [(r[0], r[1]) for r in rows] == [("chk:a", "m:old"), ("chk:b", "m:old")]
        assert raw.execute(
            "SELECT cv.embedding <=> '[0.5,-0.5,1.0]'::vector FROM chunk_vectors cv"
            " JOIN chunks c ON c.rid = cv.rid WHERE c.id = 'chk:a'"
        ).fetchone()[0] < 1e-6  # 搬运载荷距离保真

        # 幂等重放：无新版本、数据不动
        assert pg_migrate_db(raw) == []
        assert raw.execute("SELECT count(*) FROM chunk_vectors").fetchone()[0] == 2
    finally:
        try:
            raw.execute("SET search_path TO public")
            raw.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except psycopg.Error:
            pass
        finally:
            raw.close()


# ============ 蓝绿形态（拍板 3——schema 就位即可插并存，完整流程 M2） ============


def _seed_one_doc(db) -> tuple:
    """单文档单块（在用 v1）——蓝绿/级联测试共用；返回 (backend, rid)。"""
    seed_org(db)
    seed_dataset(db)
    seed_user(db, "u0")
    seed_document(db, doc_id="d_bg", owner_user_id="u0")
    insert_chunk(db, doc_id="d_bg", seq=1, version=1, chunk_id="chk:bg")
    db.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_bg'")
    rid = db.execute("SELECT rid FROM chunks WHERE id = 'chk:bg'").fetchone()[0]
    return db.make_backend(), rid


def test_blue_green_dual_label_coexist_and_insertable(backend) -> None:
    """同 rid 双 embed_model 并存可插（PK(rid, embed_model)——蓝绿物理前提）：
    标签 A 回写后标签 B 仍可认领+回写同 rid；断点清单按标签互不串扰。"""
    be, rid = _seed_one_doc(backend)

    assert be.mark_embedding_batch("d_bg", 1, "m:a") == [{"rid": rid, "content": "一般纳税人销售自产货物并提供安装服务的，应分别核算。"}]
    assert be.write_embeddings("m:a", [(rid, [1.0, 0.0])]) == 1
    # 新标签蓝绿认领：同 rid 无 m:b 向量行 → 再次认领成功、回写并存
    assert len(be.mark_embedding_batch("d_bg", 1, "m:b")) == 1
    assert be.write_embeddings("m:b", [(rid, [0.0, 1.0])]) == 1

    rows = backend.execute(
        "SELECT embed_model FROM chunk_vectors WHERE rid = ? ORDER BY embed_model", (rid,)
    ).fetchall()
    assert {r[0] for r in rows} == {"m:a", "m:b"}  # 并存可插

    # 防护零触碰（P3-9 注释校准）：mark_embedding_batch("m:b") 已把 chunks.embed_model
    # 改为 m:b——两条断言命中的都是**标签不符**分支（chunks.embed_model=:label 不匹配
    # → INSERT..SELECT 选 0 行）；同 (rid,label) 的 PK 冲突吞掉路径由
    # test_pg_backend.py::test_embedding_batch_roundtrip_and_exact_scan_distance 覆盖
    assert be.write_embeddings("m:a", [(rid, [0.5, 0.5])]) == 0
    assert be.write_embeddings("m:c", [(rid, [0.5, 0.5])]) == 0
    # 断点续跑清单：两标签均已回写 → 空；失败中断标签（钉标签未回写）→ 可清点
    assert be.pending_embeddings("m:a") == []
    insert_chunk(backend, doc_id="d_bg", seq=2, version=1, chunk_id="chk:bg2")
    rid2 = backend.execute("SELECT rid FROM chunks WHERE id = 'chk:bg2'").fetchone()[0]
    backend.execute("UPDATE chunks SET embed_model = 'm:b' WHERE rid = ?", (rid2,))
    assert [p["rid"] for p in be.pending_embeddings("m:b")] == [rid2]


def test_blue_green_new_label_predicate_hits_only_new(backend) -> None:
    """新标签谓词只命中新标签：cv JOIN 按 embed_model 过滤（TC-EMB-02 迁移后
    语义——PG 走 render_vec_recall_select 真实执行；sqlite 侧谓词路径已随
    M1-1 实装（recall_vec/render_vec_recall_select），本用例双臂断言 cv 表数据面
    + PG 真实执行）。"""
    import os

    be, rid = _seed_one_doc(backend)
    be.mark_embedding_batch("d_bg", 1, "m:a")
    be.write_embeddings("m:a", [(rid, [1.0, 0.0])])
    be.mark_embedding_batch("d_bg", 1, "m:b")
    be.write_embeddings("m:b", [(rid, [0.0, 1.0])])

    hit = backend.execute(
        "SELECT count(*) FROM chunk_vectors WHERE rid = ? AND embed_model = 'm:b'", (rid,)
    ).fetchone()[0]
    assert hit == 1

    if backend.is_pg and os.environ.get("LATTICE_PG_DSN"):
        from knowledge_lattice.store.postgres.acl_render import render_vec_recall_select
        from knowledge_lattice.store.postgres.vec import format_vector

        seed_membership(backend, "u0", "org:tax")  # compile_acl 前置
        plan = backend.compile_acl("u0", "org:tax", now=NOW_TS, embed_model="m:b")
        sql, params = render_vec_recall_select(plan, format_vector([0.0, 1.0]), top_k=5)
        rows = backend.execute(sql, params).fetchall()
        assert len(rows) == 1 and rows[0][1] == "chk:bg"
        # dist 列位随 M1-1 溯源列扩展后移（SELECT 见 render_vec_recall_select：
        # rid, chunk_id, doc_id, title, page_no, sheet_name, source_uri, dataset_id,
        # dataset_name, content, dist——索引 10）
        assert abs(rows[0][10]) < 1e-6  # 新标签向量 → 距离 0（谓词只命中 m:b 行）
        # 换查旧标签向量（正交）→ 同块但距离 1：谓词确实切到了 m:a 行
        sql_a, params_a = render_vec_recall_select(
            backend.compile_acl("u0", "org:tax", now=NOW_TS, embed_model="m:a"),
            format_vector([0.0, 1.0]), top_k=5,
        )
        rows_a = backend.execute(sql_a, params_a).fetchall()
        assert len(rows_a) == 1 and abs(rows_a[0][10] - 1.0) < 1e-6


def test_chunk_delete_cascades_chunk_vectors(backend) -> None:
    """块删 → chunk_vectors 级联清（rid 外键 ON DELETE CASCADE——版本切换/删除
    清理联动）。"""
    be, rid = _seed_one_doc(backend)
    be.mark_embedding_batch("d_bg", 1, "m:a")
    be.write_embeddings("m:a", [(rid, [1.0, 0.0])])
    assert backend.execute(
        "SELECT count(*) FROM chunk_vectors WHERE rid = ?", (rid,)
    ).fetchone()[0] == 1

    backend.execute("DELETE FROM chunks WHERE rid = ?", (rid,))
    assert backend.execute(
        "SELECT count(*) FROM chunk_vectors WHERE rid = ?", (rid,)
    ).fetchone()[0] == 0
    # store 路径同款级联（delete_by_doc → FK CASCADE 清 chunk_vectors）
    seed_document(backend, doc_id="d_bg2", owner_user_id="u0")
    insert_chunk(backend, doc_id="d_bg2", seq=1, version=1, chunk_id="chk:bg2")
    rid2 = backend.execute("SELECT rid FROM chunks WHERE id = 'chk:bg2'").fetchone()[0]
    be.mark_embedding_batch("d_bg2", 1, "m:a")
    be.write_embeddings("m:a", [(rid2, [1.0, 0.0])])
    assert be.delete_by_doc("d_bg2", 1) == 1
    assert backend.execute(
        "SELECT count(*) FROM chunk_vectors WHERE rid = ?", (rid2,)
    ).fetchone()[0] == 0


def test_pk_rid_only_conflict_probe(backend) -> None:
    """PK(rid) 冲突探针（验收 #5 保留）：仅 PRIMARY KEY(rid) 的分表在新标签写入
    即唯一冲突——v1.1 键形 (rid, embed_model) 的依据（bench2 probe 的门禁内等价）。"""
    int_type = "INTEGER" if backend.is_sqlite else "BIGINT"
    backend.execute(
        f"CREATE TEMP TABLE cv_probe(rid {int_type} NOT NULL, embed_model TEXT NOT NULL,"
        " PRIMARY KEY(rid))"
    )
    try:
        backend.execute("INSERT INTO cv_probe(rid, embed_model) VALUES(1, 'old:2560')")
        with pytest.raises(backend.integrity_error):
            backend.execute("INSERT INTO cv_probe(rid, embed_model) VALUES(1, 'new:2560')")
    finally:
        backend.execute("DROP TABLE cv_probe")


def test_chunk_vectors_pk_rejects_duplicate_pair(backend) -> None:
    """PK(rid, embed_model)：同 (rid, label) 重复直插被拒（并存的是不同标签）。"""
    be, rid = _seed_one_doc(backend)
    be.mark_embedding_batch("d_bg", 1, "m:a")
    be.write_embeddings("m:a", [(rid, [1.0, 0.0])])
    if backend.is_sqlite:
        with pytest.raises(sqlite3.IntegrityError):
            backend.execute(
                "INSERT INTO chunk_vectors(rid, embed_model, embedding) VALUES(?, 'm:a', x'00')",
                (rid,),
            )
    else:
        with pytest.raises(backend.integrity_error):
            backend.execute(
                "INSERT INTO chunk_vectors(rid, embed_model, embedding)"
                " VALUES(%(rid)s, 'm:a', '[1.0]'::vector)",
                {"rid": rid},
            )


# ============ CTE 竞态口径（M0a 顺手项 ①②——编译后退役/停用同一 Plan 等价） ============


def test_plan_snapshot_stable_across_value_disable(matrix) -> None:
    """①口径回归：编译后取值停用（v.status='disabled'）——同一 Plan 重执行结果
    不变（CTE 不读 v.status，快照语义；停用收紧经**下次编译**的授权展开生效）。"""
    plan = matrix.compile_acl("u_full", "org:tax", now=NOW_TS)
    sql, params = matrix.render_select(plan)
    before = sorted(matrix.execute(sql, params))
    assert {r[2] for r in before} == {"d_cn", "d_multi", "d_empty_region", "d_os"}

    matrix.execute(
        "UPDATE dimension_values SET status = 'disabled'"
        " WHERE value = 'OS' AND dimension_id = (SELECT id FROM dimensions"
        "   WHERE org_id = 'org:tax' AND key = 'region')"
    )
    # 同一 Plan 重执行：快照语义——d_os 仍可见（编译时点授权集含 OS）
    assert sorted(matrix.execute(sql, params)) == before

    # 重新编译：停用收紧生效（OS 出授权集 → d_os 不可见——T3 经编译路径）
    plan2 = matrix.compile_acl("u_full", "org:tax", now=NOW_TS)
    sql2, params2 = matrix.render_select(plan2)
    assert {r[2] for r in matrix.execute(sql2, params2)} == {
        "d_cn", "d_multi", "d_empty_region",
    }


def test_plan_snapshot_stable_across_dimension_retire(matrix) -> None:
    """②竞态回归：编译后维度退役——同一 Plan 重执行结果不变（CTE 不读 dim.status，
    M0a-2 P3-1 口径的测试锁定）；退役放宽经下次编译生效。"""
    plan = matrix.compile_acl("u_cn", "org:tax", now=NOW_TS)
    sql, params = matrix.render_select(plan)
    before = sorted(matrix.execute(sql, params))

    matrix.execute(
        "UPDATE dimensions SET status = 'retired' WHERE org_id = 'org:tax' AND key = 'region'"
    )
    assert sorted(matrix.execute(sql, params)) == before  # 同一 Plan——快照

    plan2 = matrix.compile_acl("u_cn", "org:tax", now=NOW_TS)
    sql2, params2 = matrix.render_select(plan2)
    assert {r[2] for r in matrix.execute(sql2, params2)} == {
        "d_multi", "d_empty_region", "d_os",
    }  # 重新编译：region 退役放宽（d_os 可见）


# ============ CTE 过滤下推（M0a 顺手项 ⑥）与 dot-key（P3-5 消解佐证） ============


def test_dataset_doc_filters_pushed_into_cte(matrix) -> None:
    """⑥下推（AST 结构断言——R2 P2-2 收口）：dataset/doc 过滤节点
    `InValue(ColumnRef("d","dataset_id"))` / `InValue(ColumnRef("d","id"))`
    分别出现在 CTE WHERE（build_visible_docs_cte_where.parts——下推）与外层
    WHERE（build_visible_docs_outer_where.parts——双保险），**两处分开断言**
    （R1 的 SQL 字符串切分分隔符不命中、cte_part 实为整段 SQL，断言恒真——
    若实现移除下推测试仍绿，属空转）；行为半句：过滤收窄正确。"""
    from knowledge_lattice.store.acl_ast import ColumnRef, InValue

    plan = matrix.compile_acl(
        "u_full", "org:tax", now=NOW_TS, dataset_ids=("ds:vat_lib",), doc_ids=("d_cn",)
    )
    cte = matrix.build_cte_where(plan)
    outer = matrix.build_outer_where(plan)
    expected_ds = InValue(ColumnRef("d", "dataset_id"), "ds", ("ds:vat_lib",))
    expected_doc = InValue(ColumnRef("d", "id"), "doc", ("d_cn",))
    # CTE 下推：过滤节点在 CTE WHERE 的 parts 中（节点树级断言——移除下推即红）
    assert expected_ds in cte.parts, "dataset 过滤未下推进 CTE"
    assert expected_doc in cte.parts, "doc 过滤未下推进 CTE"
    # 外层双保险：同条件（等值节点）在外层 WHERE 的 parts 中——分开断言
    assert expected_ds in outer.parts and expected_doc in outer.parts
    # 行为：过滤收窄正确
    sql, params = matrix.render_select(plan)
    assert {r[2] for r in matrix.execute(sql, params)} == {"d_cn"}


def test_dot_key_dimension_executes_via_cte(matrix) -> None:
    """dot-key 维度（P3-5 随 json_each 删除消解）：key 仅以引号字面量进 CTE
    （dim.key = 'a.b'），无 JSON path 语义——真实执行过滤正确。"""
    from helpers import dim_id_for

    seed_dimension(matrix, "org:tax", "a.b")
    seed_dim_value(matrix, dim_id_for("org:tax", "a.b"), "V")
    seed_grant(
        matrix,
        user_id="u_full",
        dim_id=dim_id_for("org:tax", "a.b"),
        val_id=f"val:{dim_id_for('org:tax', 'a.b')}:V",
    )
    seed_document(
        matrix, doc_id="d_dot", dataset_id="ds:vat_lib", owner_user_id="u_owner"
    )
    insert_chunk(
        matrix, doc_id="d_dot", seq=1, version=1, chunk_id="chk:d_dot:v1:1",
        content_seg="common sample", title_seg="common sample",
    )
    matrix.execute("UPDATE documents SET active_version = 1 WHERE id = 'd_dot'")
    seed_doc_dims(matrix, "d_dot", {"a.b": ["V"]})

    plan = matrix.compile_acl("u_full", "org:tax", now=NOW_TS)
    sql, params = matrix.render_select(plan)
    assert "dim.key = 'a.b'" in sql  # key 只以转义字面量出现（无 '$.a.b' JSON path）
    visible = {r[2] for r in matrix.execute(sql, params)}
    assert "d_dot" in visible  # 有值交集 → 可见


def test_sqlite_0004_backfills_existing_tombstones(tmp_path: Path) -> None:
    """P3-1（M2.1 R2 / Tester P3-a）：0004 存量回填直接断言——构造 0004 前形态库
    （仅应用 0001~0003）+ 造 tombstone=1 行（无 tombstoned_at 列）→ 应用 0004
    → 回填非 NULL（自迁移时点起算 90 天保守窗口——RUNBOOK 升级注记的用例化）。"""
    import shutil

    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.migrate import BUILTIN_DIRS

    subset = tmp_path / "upto_0003"
    subset.mkdir()
    for name in ("0001_schema_v1.sql", "0002_schema_v1_1.sql", "0003_uploads.sql"):
        shutil.copy(BUILTIN_DIRS["docs"] / name, subset / name)

    conn = connect(tmp_path / "legacy.db")
    try:
        assert migrate_db(conn, dirs=[subset]) == [1, 2, 3]
        # 造数：org/dataset/doc + v1 块（tombstone=1——0004 前无时点列）
        conn.execute(
            "INSERT INTO orgs(id, name) VALUES('org:tax', 't')"
        )
        conn.execute("INSERT INTO users(id, username) VALUES('u1', 'u1')")
        conn.execute(
            "INSERT INTO datasets(id, org_id, name) VALUES('ds:vat', 'org:tax', 'v')"
        )
        conn.execute(
            "INSERT INTO documents(id, org_id, dataset_id, title, content_hash,"
            " mime_type, parser, active_version, active_status, owner_user_id,"
            " raw_object_key)"
            " VALUES('d1', 'org:tax', 'ds:vat', 't', 'sha256:x', 'text/html',"
            " 'docling', 2, 'searchable_full', 'u1', 'objects/x')"
        )
        conn.execute(
            "INSERT INTO chunks(id, doc_id, seq, version, tombstone, content)"
            " VALUES('chk_legacy', 'd1', 1, 1, 1, '旧版本块')"
        )
        conn.commit()

        applied = migrate_db(conn)  # builtin 全量 → 0004（回填）+ 0005
        assert 4 in applied and 5 in applied
        row = conn.execute(
            "SELECT tombstoned_at FROM chunks WHERE id = 'chk_legacy'"
        ).fetchone()
        assert row is not None and row[0] is not None, "0004 存量回填缺失（P3-1）"
    finally:
        conn.close()
