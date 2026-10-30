"""R2 修复轮（m2s-1 Committer NEEDS_CHANGES）：

- P2-1 跨批次 parent_id 解析（600 模板 + 600 字段跨 1000 批界）；
- P3-2 finished_at 实际完成时刻（不再恒等于 started_at）；
- P3-3 关系批边界存活检查（取消/失租约不等整轮）；
- P3-6① curated_json/sensitivity/curated_rev 同步前后逐字节不变（T-S1 永久证据）；
- P3-6④ 顺序偏差防回退：快照关系指向超期 missing 端点 → 先落库后联动 retired；
- P3-6⑥ sem_entities.type CHECK 九值与 SEM_ENTITY_TYPES 常量自动化一致。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fake_semantic import FakeSourceAdapter, tpl_entity, tpl_snapshot
from helpers import seed_org

ORG = "org:tax"

NOW = "2026-10-29 12:00:00"
LATER = "2026-10-29 12:00:05"


@pytest.fixture()
def sync_env(backend, tmp_path):
    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    return SimpleNamespace(db=backend, backend=backend.make_backend(), settings=settings)


def run(env, records, *, now=NOW, adapter_name="template_center", **kw):
    from knowledge_lattice.core.semantic.sync import run_sync

    return run_sync(
        env.backend, ORG, FakeSourceAdapter(adapter_name, records),
        settings=env.settings, snapshot=list(records), now=now, **kw
    )


# ---- P2-1 跨批次 parent_id 解析（600+600 跨 1000 批界） ----


def test_p2_1_cross_batch_parent_resolution(sync_env) -> None:
    """快照 >semantic_batch_rows：批 2 的字段父行（模板）在批 1 已提交——
    parent_id 必须解析到真实 id，不得写 NULL / 覆写已有值为 NULL。"""
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

    records: list = []
    for i in range(600):
        records.append(tpl_entity(f"TPL_{i:04d}"))
        records.append(
            EntityRecord(type="template_field", key=f"TPL_{i:04d}.F1",
                         name=f"字段{i}", parent_key=f"template:TPL_{i:04d}")
        )
        records.append(
            RelationRecord(src=("template", f"TPL_{i:04d}"), rel_type="has_field",
                           dst=("template_field", f"TPL_{i:04d}.F1"))
        )
    r1 = run(sync_env, records)
    assert r1["status"] == "succeeded"
    assert r1["stats"]["batches"] == 2  # 1200 实体跨批（1000+200）——批界生效

    null_parents = sync_env.db.execute(
        "SELECT count(*) FROM sem_entities WHERE type = 'template_field'"
        "   AND parent_id IS NULL"
    ).fetchone()[0]
    assert null_parents == 0, "跨批字段的 parent_id 解析丢失（P2-1）"

    # 每个 field.parent_id == 对应 template.id（逐行核对，非仅计数）
    bad = sync_env.db.execute(
        "SELECT count(*) FROM sem_entities f JOIN sem_entities t"
        "   ON f.parent_id = t.id AND t.type = 'template'"
        " WHERE f.type = 'template_field'"
        "   AND t.key != substr(f.key, 1, length(f.key) - 3)"
    ).fetchone()[0]
    assert bad == 0  # substr(key) 去 ".F1" = 模板键——父指错也算失败

    # 二跑：parent 稳定不变（若首跑曾写 NULL、二跑修正会表现为 updated≠0）
    r2 = run(sync_env, records)
    assert r2["status"] == "succeeded"
    assert r2["stats"]["updated"] == 0
    assert sync_env.db.execute(
        "SELECT count(*) FROM sem_entities WHERE type = 'template_field'"
        "   AND parent_id IS NULL"
    ).fetchone()[0] == 0


# ---- P3-2 finished_at 实际完成时刻 ----


def test_p3_2_finished_at_uses_completion_time(sync_env) -> None:
    run(sync_env, [tpl_entity("TPL_A")], now=NOW, finish_now=LATER)
    finished = str(sync_env.db.execute(
        "SELECT finished_at FROM sem_sync_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()[0])
    assert finished == LATER  # 完成时刻 ≠ 开始时刻（P3-2：COALESCE 不再被开始时间顶替）


def test_p3_2_finished_at_defaults_to_now_and_not_before_start(sync_env) -> None:
    """缺省路径 finished_at 落库时钟且 ≥ started_at（开始时间造数为过去时刻）。"""
    past = "2020-01-01 00:00:00"
    run(sync_env, [tpl_entity("TPL_B")], now=past)
    started, finished = sync_env.db.execute(
        "SELECT started_at, finished_at FROM sem_sync_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert finished is not None and str(finished) >= str(started) >= past


# ---- P3-3 关系批边界存活检查 ----


def test_p3_3_relation_batch_alive_check(sync_env) -> None:
    """关系批间存活检查：失守即 SyncInterrupted（run 落 failed）——不等整轮。"""
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord
    from knowledge_lattice.core.semantic.sync import SyncInterrupted

    records = [tpl_entity("TPL_ROOT")]
    relations = [
        RelationRecord(src=("template", "TPL_ROOT"), rel_type="has_field",
                       dst=("template_field", f"TPL_ROOT.F{i:04d}"))
        for i in range(1500)  # 2 批关系（1000 + 500）
    ]
    fields = [
        EntityRecord(type="template_field", key=f"TPL_ROOT.F{i:04d}",
                     name=f"字段{i}", parent_key="template:TPL_ROOT")
        for i in range(1500)
    ]
    snapshot = records + fields + relations

    calls = {"n": 0}

    def flaky_alive() -> bool:
        calls["n"] += 1
        # 边界序：①实体批1 ②批1别名重建 ③实体批2 ④批2别名重建 ⑤关系批1（放行）
        # ⑥关系批2 → 失守——精确证明关系批边界在场（非仅实体批）
        return calls["n"] <= 5

    with pytest.raises(SyncInterrupted):
        run(sync_env, snapshot, should_continue=flaky_alive)
    status = sync_env.db.execute(
        "SELECT status FROM sem_sync_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert status == "failed"  # 中断落 run failed——非整轮静默跑完


# ---- P3-6① curated 列同步前后逐字节不变（T-S1 永久证据） ----


def test_p3_6_curated_columns_untouched_by_sync(sync_env) -> None:
    e = tpl_entity("TPL_C", name="原名")
    run(sync_env, [e])
    sync_env.db.execute(
        "UPDATE sem_entities SET curated_json = '{\"definition\": \"人工定义\","
        " \"why\": \"口径\"}', sensitivity = 'restricted', curated_rev = 'r1abc'"
        " WHERE key = 'TPL_C'"
    )
    before = sync_env.db.execute(
        "SELECT curated_json, sensitivity, curated_rev FROM sem_entities WHERE key = 'TPL_C'"
    ).fetchone()

    e2 = tpl_entity("TPL_C", name="新名")
    e2.attrs = {"note": "事实属性更新"}
    e2.aliases = ["新别名"]
    run(sync_env, [e2], now="2026-10-30 12:00:00")

    after = sync_env.db.execute(
        "SELECT curated_json, sensitivity, curated_rev FROM sem_entities WHERE key = 'TPL_C'"
    ).fetchone()
    assert after == before  # 人工三列逐字节不动（同步只写事实列——T-S1 列级分工）
    name = sync_env.db.execute(
        "SELECT name FROM sem_entities WHERE key = 'TPL_C'"
    ).fetchone()[0]
    assert name == "新名"  # 事实列照常更新


# ---- P3-6④ 顺序偏差防回退：关系先落库、随超期端点联动 retired ----


def test_p3_6_relation_to_overdue_missing_endpoint_retired(sync_env) -> None:
    """快照关系指向超期 missing 端点：关系先解析落库（active），advance 随端点
    一并 retired——若顺序倒置（先推进后写关系）会留悬挂 active 关系。此用例
    固化 R1 顺序偏差（宽限期推进必须后置于关系 upsert）防回退。"""
    from knowledge_lattice.store.taskclock import add_seconds

    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

    scenario = EntityRecord(type="scenario", key="SC_1", name="场景一")
    fillers = [tpl_entity(f"TPL_{i}") for i in range(8)]
    snap_full = [tpl_entity("TPL_X"), scenario] + fillers
    run(sync_env, snap_full)

    # X → missing（1/10=10% 不触保护）；造数超期（8 天前最后可见）
    run(sync_env, [scenario] + fillers)
    sync_env.db.execute(
        "UPDATE sem_entities SET synced_at = ? WHERE key = 'TPL_X'",
        (add_seconds(NOW, -8 * 86400),),
    )

    # 快照仍发 uses(SC_1→TPL_X)：dst 在库（missing 态可解析）→ 关系先落 active，
    # 随后 advance 随超期端点一并 retired——不留悬挂
    rel = RelationRecord(src=("scenario", "SC_1"), rel_type="uses",
                         dst=("template", "TPL_X"))
    r = run(sync_env, [scenario] + fillers + [rel])
    assert r["status"] == "succeeded"
    assert sync_env.db.execute(
        "SELECT status FROM sem_entities WHERE key = 'TPL_X'"
    ).fetchone()[0] == "retired"
    x_id = sync_env.db.execute(
        "SELECT id FROM sem_entities WHERE key = 'TPL_X'"
    ).fetchone()[0]
    assert sync_env.db.execute(
        "SELECT status FROM sem_relations WHERE dst_id = ?", (x_id,)
    ).fetchone()[0] == "retired"  # 指向超期端点的关系联动 retired（无悬挂 active）


# ---- P3-6⑥ sem_entities.type CHECK 九值与常量自动化一致 ----


def test_p3_6_entity_type_check_matches_constants(backend) -> None:
    """DDL CHECK 九值 == SEM_ENTITY_TYPES（三处一致的第四面——Committer 补充建议）。"""
    import re

    from knowledge_lattice.core.semantic.constants import SEM_ENTITY_TYPES

    if backend.is_sqlite:
        ddl = backend.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'sem_entities'"
        ).fetchone()[0]
        check = ddl.split("CHECK (type IN", 1)[1].split("))", 1)[0]
    else:
        defs = [
            r[0] for r in backend.execute(
                "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
                " JOIN pg_class t ON t.oid = c.conrelid"
                " WHERE t.relname = 'sem_entities' AND c.contype = 'c'"
            )
        ]
        check = next(d for d in defs if "type" in d.split("= ANY")[0])
    values = set(re.findall(r"'([a-z_]+)'", check))
    assert values == set(SEM_ENTITY_TYPES), (
        f"DDL CHECK {sorted(values)} ≠ 常量 {sorted(SEM_ENTITY_TYPES)}"
    )
