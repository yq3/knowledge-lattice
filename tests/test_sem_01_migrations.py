"""TC-SYNC-09 迁移落库与白名单种子 + T-S5 关系触发器（双后端参数化）。

- 语义表 M2-S1 才落库：迁移 0006（docs 水位 0005 下一号）建 sem_* 七表
  （org 作用域六表 + 全局 sem_rel_types）+ 两触发器 + 白名单种子；
- 三处一致：代码常量（core/semantic/constants.py）vs sem_rel_types 种子 vs
  触发器行为（未登记组合拒绝、'*' 任意型放行）；
- T-S5：跨组织关系 / 白名单外组合 / 端点原地 UPDATE 均被触发器 ABORT。
"""

from __future__ import annotations

import pytest

from helpers import seed_org

ORG = "org:tax"
ORG_GL = "org:gl"

SEM_TABLES = (
    "sem_entities", "sem_aliases", "sem_relations", "sem_rel_types",
    "sem_chunk_entities", "sem_builds", "sem_sync_runs",
)
ORG_SCOPED_TABLES = SEM_TABLES[:3] + SEM_TABLES[4:]  # 除 sem_rel_types 外全带 org_id


@pytest.fixture()
def sem_db(backend):
    seed_org(backend, ORG)
    seed_org(backend, ORG_GL)
    return backend


def _columns(db, table: str) -> set[str]:
    if db.is_sqlite:
        return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
    rows = db.execute(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_name = ? AND table_schema = current_schema()",
        (table,),
    )
    return {r[0] for r in rows}


def _insert_entity(db, org: str, etype: str, key: str, name: str) -> int:
    db.execute(
        "INSERT INTO sem_entities(org_id, type, key, name, source)"
        " VALUES(?, ?, ?, ?, 'curated')",
        (org, etype, key, name),
    )
    return db.execute(
        "SELECT id FROM sem_entities WHERE org_id = ? AND type = ? AND key = ?",
        (org, etype, key),
    ).fetchone()[0]


def _insert_relation(db, org: str, src: int, rel: str, dst: int, *, source="sync") -> None:
    db.execute(
        "INSERT INTO sem_relations(org_id, src_id, rel_type, dst_id, source)"
        " VALUES(?, ?, ?, ?, ?)",
        (org, src, rel, dst, source),
    )


# ---- TC-SYNC-09①：迁移落库（表/触发器/迁移号接水位） ----


def test_migration_0006_next_after_docs_watermark() -> None:
    """迁移号全局唯一接 docs 水位 0005（双方言各一份、同号同语义）。"""
    from knowledge_lattice.store.postgres.migrate import discover as pg_discover
    from knowledge_lattice.store.sqlite.migrate import discover as sq_discover

    for discover in (sq_discover, pg_discover):
        ms = discover()
        versions = [m.version for m in ms]
        assert versions == sorted(versions)
        assert 6 in versions and 5 in versions
        semantic = [m for m in ms if m.domain == "semantic"]
        assert [m.version for m in semantic] == [6, 7]  # m2s-3 起 0007 semantic_yaml


def test_sem_tables_and_triggers_present(sem_db) -> None:
    tables = sem_db.table_names()
    for t in SEM_TABLES:
        assert t in tables, f"语义迁移应建表 {t}"
    triggers = sem_db.trigger_names()
    assert "trg_sem_rel_check" in triggers
    assert "trg_sem_rel_noupdate" in triggers


def test_tasks_payload_column_for_semantic_sync(sem_db) -> None:
    """semantic_sync 任务携带 {org, adapter}——tasks 表 0006 补 payload 列。"""
    assert "payload" in _columns(sem_db, "tasks")


def test_org_scoped_tables_carry_org_id(sem_db) -> None:
    """org 作用域六表带 org_id；sem_rel_types 全局白名单表无 org_id（v0.6.1 口径）。"""
    for t in ORG_SCOPED_TABLES:
        assert "org_id" in _columns(sem_db, t), f"{t} 应带 org_id"
    assert "org_id" not in _columns(sem_db, "sem_rel_types")


# ---- TC-SYNC-09②③：白名单种子逐行 + 与代码常量三处一致 ----


def test_rel_types_seed_matches_design_whitelist(sem_db) -> None:
    from knowledge_lattice.core.semantic.constants import SEM_REL_TYPES

    rows = sem_db.execute(
        "SELECT rel_type, src_type, dst_type FROM sem_rel_types"
    ).fetchall()
    assert set(rows) == set(SEM_REL_TYPES)
    # 十种 rel_type × 十二行端点组合（derived_from 两行、refers_to concept/system 两行）
    assert len(rows) == 12
    assert len({r[0] for r in rows}) == 10


def test_entity_type_check_constraint(sem_db) -> None:
    """sem_entities.type CHECK 九值白名单（与常量一致——未登记类型拒绝）。"""
    with pytest.raises(sem_db.integrity_error):
        sem_db.execute(
            "INSERT INTO sem_entities(org_id, type, key, name, source)"
            " VALUES(?, 'gadget', 'g1', '小玩意', 'curated')",
            (ORG,),
        )


# ---- T-S5：关系触发器（组织一致性 + 白名单 + 端点不可变） ----


def test_trg_rejects_cross_org_relation(sem_db) -> None:
    """T-S5①：src/dst 跨组织 → ABORT。"""
    tax_e = _insert_entity(sem_db, ORG, "concept", "c1", "概念一")
    gl_e = _insert_entity(sem_db, ORG_GL, "concept", "c2", "概念二")
    with pytest.raises(sem_db.integrity_error):
        _insert_relation(sem_db, ORG, tax_e, "related_to", gl_e)


def test_trg_rejects_non_whitelist_combination(sem_db) -> None:
    """T-S5②：concept→column 的 has_field 不在白名单 → ABORT。"""
    c = _insert_entity(sem_db, ORG, "concept", "c1", "概念一")
    col = _insert_entity(sem_db, ORG, "column", "db.t.x", "列x")
    with pytest.raises(sem_db.integrity_error):
        _insert_relation(sem_db, ORG, c, "has_field", col)


def test_trg_accepts_whitelisted_and_any_dst(sem_db) -> None:
    """白名单内组合放行；refers_to 的 '*' 任意型 dst（concept→column）放行。"""
    t = _insert_entity(sem_db, ORG, "template", "TPL_1", "模板一")
    f = _insert_entity(sem_db, ORG, "template_field", "TPL_1.F1", "字段一")
    _insert_relation(sem_db, ORG, t, "has_field", f)  # 不抛

    c = _insert_entity(sem_db, ORG, "concept", "c9", "概念九")
    col = _insert_entity(sem_db, ORG, "column", "db.t.y", "列y")
    _insert_relation(sem_db, ORG, c, "refers_to", col, source="curated")  # 任意型 dst
    assert sem_db.execute("SELECT count(*) FROM sem_relations").fetchone()[0] == 2


def test_trg_rejects_endpoint_update_in_place(sem_db) -> None:
    """T-S5③：src_id/dst_id/rel_type/org_id 原地 UPDATE → ABORT；status 更新放行。"""
    c1 = _insert_entity(sem_db, ORG, "concept", "a1", "甲")
    c2 = _insert_entity(sem_db, ORG, "concept", "a2", "乙")
    c3 = _insert_entity(sem_db, ORG, "concept", "a3", "丙")
    _insert_relation(sem_db, ORG, c1, "related_to", c2, source="curated")
    rel_id = sem_db.execute("SELECT id FROM sem_relations").fetchone()[0]

    with pytest.raises(sem_db.integrity_error):
        sem_db.execute("UPDATE sem_relations SET dst_id = ? WHERE id = ?", (c3, rel_id))
    with pytest.raises(sem_db.integrity_error):
        sem_db.execute("UPDATE sem_relations SET src_id = ? WHERE id = ?", (c3, rel_id))
    with pytest.raises(sem_db.integrity_error):
        sem_db.execute("UPDATE sem_relations SET rel_type = 'refers_to' WHERE id = ?", (rel_id,))
    with pytest.raises(sem_db.integrity_error):
        sem_db.execute("UPDATE sem_relations SET org_id = ? WHERE id = ?", (ORG_GL, rel_id))
    # status 推进不在 OF 列表——advance_status 依赖此口径
    sem_db.execute("UPDATE sem_relations SET status = 'retired' WHERE id = ?", (rel_id,))
    assert sem_db.execute(
        "SELECT status FROM sem_relations WHERE id = ?", (rel_id,)
    ).fetchone()[0] == "retired"
