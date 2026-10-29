"""T-S2 删除比例保护 / T-S3 同步幂等 / T-S4 宽限期状态机（双后端参数化）。

run_sync 固定 now 造数（时间依赖不推进系统时钟——测试造数纪律）；快照经
snapshot= 注入（全量快照语义，fetch 语义由 TC-SYNC-01/02 覆盖）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fake_semantic import tpl_entity, tpl_snapshot
from helpers import seed_org

ORG = "org:tax"
ORG_GL = "org:gl"

NOW = "2026-10-29 12:00:00"


@pytest.fixture()
def sync_env(backend, tmp_path):
    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    return SimpleNamespace(db=backend, backend=backend.make_backend(), settings=settings)


def run(env, records, *, now=NOW):
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.core.semantic.sync import run_sync

    return run_sync(
        env.backend, ORG, FakeSourceAdapter("template_center", records),
        settings=env.settings, snapshot=list(records), now=now,
    )


def _dump(db) -> dict:
    """库内实体/关系/别名逐行快照（T-S2 零写入 diff 数据源——不含 run 记录）。"""
    return {
        "entities": db.execute(
            "SELECT id, org_id, type, key, name, parent_id, attrs_json, source,"
            " source_system, status, sensitivity, synced_at FROM sem_entities"
            " ORDER BY id"
        ).fetchall(),
        "relations": db.execute(
            "SELECT id, org_id, src_id, rel_type, dst_id, attrs_json, source,"
            " status, synced_at FROM sem_relations ORDER BY id"
        ).fetchall(),
        "aliases": db.execute(
            "SELECT id, org_id, entity_id, alias, alias_norm, kind, match_mode,"
            " weight FROM sem_aliases ORDER BY id"
        ).fetchall(),
    }


# ---- T-S2 删除比例保护（基数=库内该来源 active 实体） ----


def test_t_s2_empty_snapshot_aborts_guard_with_zero_writes(sync_env, caplog) -> None:
    r1 = run(sync_env, tpl_snapshot(10))
    assert r1["status"] == "succeeded"
    before = _dump(sync_env.db)

    with caplog.at_level("WARNING"):
        r2 = run(sync_env, [])
    assert r2["status"] == "aborted_guard"
    assert _dump(sync_env.db) == before  # 逐行 diff 为空——零写入
    assert any("delete-guard" in rec.message for rec in caplog.records)


def test_t_s2_30pct_vanished_aborts_guard(sync_env) -> None:
    snap = tpl_snapshot(10, with_fields=False)
    assert run(sync_env, snap)["status"] == "succeeded"
    before = _dump(sync_env.db)

    r2 = run(sync_env, snap[:7])  # 少 30% > 阈值 20%
    assert r2["status"] == "aborted_guard"
    assert _dump(sync_env.db) == before
    stats = r2["stats"]
    assert stats["guard"]["vanished"] == 3 and stats["guard"]["active"] == 10


def test_t_s2_10pct_vanished_proceeds_marks_missing(sync_env) -> None:
    snap = tpl_snapshot(10, with_fields=False)
    assert run(sync_env, snap)["status"] == "succeeded"

    r2 = run(sync_env, snap[:9])  # 少 10% ≤ 阈值 → 正常执行
    assert r2["status"] == "succeeded"
    assert r2["stats"]["missing"] == 1
    status = sync_env.db.execute(
        "SELECT status FROM sem_entities WHERE key = ?", (snap[-1].key,)
    ).fetchone()[0]
    assert status == "missing"


def test_t_s2_guard_scope_is_per_source(sync_env) -> None:
    """保护基数只算本适配器来源（source='sync' AND source_system=本适配器 active）。"""
    snap = tpl_snapshot(10, with_fields=False)
    assert run(sync_env, snap)["status"] == "succeeded"
    # 造数另一来源（metadata）的 active 实体——不应稀释/放大消失比例
    sync_env.db.execute(
        "UPDATE sem_entities SET source_system = 'metadata' WHERE key = ?", (snap[0].key,)
    )
    r2 = run(sync_env, snap[1:5])  # 本来源 10-1=9 内消失 5 → >20%
    assert r2["status"] == "aborted_guard"
    assert r2["stats"]["guard"]["active"] == 9


# ---- T-S3 同步幂等 ----


def test_t_s3_second_run_all_zero(sync_env) -> None:
    snap = tpl_snapshot(10)
    assert run(sync_env, snap)["status"] == "succeeded"
    r2 = run(sync_env, snap)
    assert r2["status"] == "succeeded"
    stats = r2["stats"]
    assert stats["inserted"] == 0
    assert stats["updated"] == 0
    assert stats["missing"] == 0
    # synced_at 刷新属预期（可见性：synced_at 已是 now）——不计入 updated
    #（pg 臂 TIMESTAMP 列回 datetime——str 归一双方言）
    assert str(sync_env.db.execute(
        "SELECT synced_at FROM sem_entities LIMIT 1"
    ).fetchone()[0]) == NOW


# ---- T-S4 宽限期状态机（missing 标记 / 宽限恢复 / 超期 retired 关系联动） ----


def _without(snap, tpl_key: str) -> list:
    """快照移除某模板及其字段/关联关系（源端消失造数）。"""
    out = []
    for r in snap:
        key = getattr(r, "key", None)
        if key == tpl_key or (key and key.startswith(tpl_key + ".")):
            continue
        src = getattr(r, "src", None)
        if src and (src[1] == tpl_key or src[1].startswith(tpl_key + ".")):
            continue
        out.append(r)
    return out


def test_t_s4_missing_then_recover_then_retire(sync_env) -> None:
    from knowledge_lattice.store.taskclock import add_seconds

    snap = tpl_snapshot(5)
    assert run(sync_env, snap)["status"] == "succeeded"

    # ① 源端移除 X（2/10=20% 不 > 阈值 → 正常执行）→ X 置 missing、关系保持
    r2 = run(sync_env, _without(snap, "TPL_0"))
    assert r2["status"] == "succeeded"
    row = sync_env.db.execute(
        "SELECT id, status FROM sem_entities WHERE key = 'TPL_0'"
    ).fetchone()
    tpl_id, status = row
    assert status == "missing"
    rel_status = sync_env.db.execute(
        "SELECT status FROM sem_relations WHERE src_id = ?", (tpl_id,)
    ).fetchone()[0]
    assert rel_status == "active"  # 关系保持

    # ② 次日快照恢复 X → 回 active
    r3 = run(sync_env, snap, now=add_seconds(NOW, 86400))
    assert r3["status"] == "succeeded"
    assert sync_env.db.execute(
        "SELECT status FROM sem_entities WHERE key = 'TPL_0'"
    ).fetchone()[0] == "active"

    # ③ 造数 synced_at=8 天前且快照仍无 X → retired 且关系一并 retired
    run(sync_env, _without(snap, "TPL_0"), now=add_seconds(NOW, 2 * 86400))
    sync_env.db.execute(
        "UPDATE sem_entities SET synced_at = ? WHERE key = 'TPL_0'",
        (add_seconds(NOW, -8 * 86400),),
    )
    r5 = run(sync_env, _without(snap, "TPL_0"), now=add_seconds(NOW, 3 * 86400))
    assert r5["status"] == "succeeded"
    assert r5["stats"]["retired"] == 1
    assert sync_env.db.execute(
        "SELECT status FROM sem_entities WHERE key = 'TPL_0'"
    ).fetchone()[0] == "retired"
    assert sync_env.db.execute(
        "SELECT status FROM sem_relations WHERE src_id = ?", (tpl_id,)
    ).fetchone()[0] == "retired"


def test_t_s4_grace_window_boundary(sync_env) -> None:
    """宽限期内（<7 天）不 retired；恰 7 天整未过界（严格 < 比较——第 7 天
    当日仍宽限，第 8 天转 retired 由上用例覆盖）。"""
    from knowledge_lattice.store.taskclock import add_seconds

    snap = [tpl_entity(f"TPL_{c}") for c in "ABCDE"]
    run(sync_env, snap)
    rest = [tpl_entity(f"TPL_{c}") for c in "BCDE"]
    run(sync_env, rest)  # A → missing（1/5=20% 不 > 阈值）
    sync_env.db.execute(
        "UPDATE sem_entities SET synced_at = ? WHERE key = 'TPL_A'",
        (add_seconds(NOW, -6 * 86400),),
    )
    r = run(sync_env, rest)
    assert r["status"] == "succeeded"
    assert sync_env.db.execute(
        "SELECT status FROM sem_entities WHERE key = 'TPL_A'"
    ).fetchone()[0] == "missing"  # 6 天 < 7 —— 仍在宽限期
