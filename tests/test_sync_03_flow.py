"""TC-SYNC-03 分批与重跑幂等 / 04 端点冲突 / 05 别名三 kind / 06 维度携带与
填充率告警 / 07 run 记录与审计（双后端参数化）。"""

from __future__ import annotations

import json
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


def run(env, records, *, now=NOW, adapter_name="template_center"):
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.core.semantic.sync import run_sync

    return run_sync(
        env.backend, ORG, FakeSourceAdapter(adapter_name, records),
        settings=env.settings, snapshot=list(records), now=now,
    )


# ---- TC-SYNC-03 分批（≤1000 行/批）与批间失败重跑幂等 ----


def test_tc_sync_03_batches_of_1000(sync_env, monkeypatch) -> None:
    snap = [tpl_entity(f"TPL_{i:04d}") for i in range(2500)]
    calls: list[int] = []
    orig = sync_env.backend.upsert_entities_batch

    def spy(org_id, rows):
        calls.append(len(rows))
        return orig(org_id, rows)

    monkeypatch.setattr(sync_env.backend, "upsert_entities_batch", spy)
    r = run(sync_env, snap)
    assert r["status"] == "succeeded"
    assert calls == [1000, 1000, 500]  # 每批 ≤1000 行提交（NFR-11）
    assert r["stats"]["batches"] == 3
    assert sync_env.db.execute("SELECT count(*) FROM sem_entities").fetchone()[0] == 2500


def test_tc_sync_03_mid_failure_rerun_idempotent(sync_env, monkeypatch) -> None:
    snap = [tpl_entity(f"TPL_{i:04d}") for i in range(1500)]
    orig = sync_env.backend.upsert_entities_batch
    # 第二批失败（第 1001 行起）——run 置 failed、首批写入保留（分批已提交语义）
    state = {"n": 0}

    def failing(org_id, rows):
        state["n"] += 1
        if state["n"] == 2:
            raise RuntimeError("batch 2 boom (simulated mid-run crash)")
        return orig(org_id, rows)

    monkeypatch.setattr(sync_env.backend, "upsert_entities_batch", failing)
    with pytest.raises(RuntimeError, match="batch 2 boom"):
        run(sync_env, snap)
    monkeypatch.setattr(sync_env.backend, "upsert_entities_batch", orig)
    assert sync_env.db.execute("SELECT count(*) FROM sem_entities").fetchone()[0] == 1000

    # 重跑同一快照 → succeeded（upsert 幂等续跑——已写入 1000 行按冲突无关路径并轨）
    r2 = run(sync_env, snap)
    assert r2["status"] == "succeeded"
    assert r2["stats"]["inserted"] == 500 and r2["stats"]["updated"] == 0
    # 再跑一次全量幂等
    r3 = run(sync_env, snap)
    assert (r3["stats"]["inserted"], r3["stats"]["updated"]) == (0, 0)


# ---- TC-SYNC-04 关系端点冲突不写入 ----


def test_tc_sync_04_conflict_skipped_not_blocking(sync_env) -> None:
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

    records = [
        tpl_entity("TPL_1"),
        EntityRecord(type="template_field", key="TPL_1.F1", name="字段一",
                     parent_key="template:TPL_1"),
        RelationRecord(src=("template", "TPL_1"), rel_type="has_field",
                       dst=("template_field", "TPL_1.F1")),
        # dst 端点库内（与快照均）不存在 → 跳过、记冲突
        RelationRecord(src=("template", "TPL_1"), rel_type="has_field",
                       dst=("template_field", "TPL_1.GONE")),
        # src 端点不存在 → 同上
        RelationRecord(src=("template", "TPL_NONE"), rel_type="backed_by",
                       dst=("table", "ods.t1")),
        # 白名单外组合 → 防御性冲突（适配器不该产出，触发器兜底）
        RelationRecord(src=("template", "TPL_1"), rel_type="child_of",
                       dst=("template_field", "TPL_1.F1")),
    ]
    r = run(sync_env, records)
    assert r["status"] == "succeeded"  # 整批其余不受阻断
    conflicts = r["stats"]["conflicts"]
    assert len(conflicts) == 3
    by_reason = {c["reason"]: c for c in conflicts}
    assert set(by_reason) == {
        "dst endpoint not found", "src endpoint not found",
        "endpoint types not in whitelist",
    }
    assert by_reason["dst endpoint not found"]["dst"] == "template_field:TPL_1.GONE"
    assert by_reason["dst endpoint not found"]["src"] == "template:TPL_1"
    assert by_reason["dst endpoint not found"]["rel_type"] == "has_field"
    # 合法关系已写入、冲突关系零行
    rels = sync_env.db.execute(
        "SELECT rel_type FROM sem_relations ORDER BY rel_type"
    ).fetchall()
    assert [x[0] for x in rels] == ["has_field"]
    assert sync_env.db.execute("SELECT count(*) FROM sem_relations").fetchone()[0] == 1
    # run 可查且 stats_json.conflicts 持久化（TC-SYNC-04 断言面）
    run_row = sync_env.db.execute(
        "SELECT stats_json FROM sem_sync_runs WHERE id = ?", (r["run_id"],)
    ).fetchone()[0]
    assert len(json.loads(run_row)["conflicts"]) == 3


# ---- TC-SYNC-05 别名三 kind 重建 ----


def test_tc_sync_05_alias_kinds_rebuild(sync_env) -> None:
    e = tpl_entity("TPL_1", name="进项采集模板")
    e.aliases = ["进项模板源别名"]
    run(sync_env, [e])

    eid = sync_env.db.execute(
        "SELECT id FROM sem_entities WHERE key = 'TPL_1'"
    ).fetchone()[0]
    # 人工内容造数：manual + abbr（同步不动——T-S1 列级分工互证）
    sync_env.db.execute(
        "INSERT INTO sem_aliases(org_id, entity_id, alias, alias_norm, kind)"
        " VALUES(?, ?, '人工别名', '人工别名', 'manual')", (ORG, eid))
    sync_env.db.execute(
        "INSERT INTO sem_aliases(org_id, entity_id, alias, alias_norm, kind)"
        " VALUES(?, ?, 'JXMK', 'jxmk', 'abbr')", (ORG, eid))
    kinds_before = sync_env.db.execute(
        "SELECT kind, alias FROM sem_aliases WHERE entity_id = ? ORDER BY kind", (eid,)
    ).fetchall()
    assert ("abbr", "JXMK") in kinds_before and ("manual", "人工别名") in kinds_before

    # 快照变更：规范名变 + 源端别名变 → name/code/sync 先删后插、manual/abbr 原样
    e2 = tpl_entity("TPL_1", name="进项采集模板V2")
    e2.aliases = ["新源端别名"]
    run(sync_env, [e2], now="2026-10-30 12:00:00")

    rows = sync_env.db.execute(
        "SELECT kind, alias, alias_norm FROM sem_aliases WHERE entity_id = ?"
        " ORDER BY kind, alias", (eid,)
    ).fetchall()
    kinds = {}
    for kind, alias, norm in rows:
        kinds.setdefault(kind, []).append((alias, norm))
    assert kinds["manual"] == [("人工别名", "人工别名")]      # 原样
    assert kinds["abbr"] == [("JXMK", "jxmk")]               # 原样
    assert kinds["name"] == [("进项采集模板V2", "进项采集模板v2")]  # 按新快照重建
    assert kinds["code"] == [("TPL_1", "tpl_1")]             # code = 业务键
    assert kinds["sync"] == [("新源端别名", "新源端别名")]     # 按新快照重建
    # 旧 name/sync 别名已删（先删后插，非累积）
    assert ("进项采集模板", "进项采集模板") not in kinds.get("name", [])
    assert ("进项模板源别名",) not in kinds.get("sync", [])


def test_alias_norm_normalization(sync_env) -> None:
    """alias_norm 规范化：NFKC 全角→半角、小写、去空白。"""
    e = tpl_entity("TPL_9", name="ＶＡＴ 模板　Ｘ")
    run(sync_env, [e])
    norms = {
        r[0] for r in sync_env.db.execute("SELECT alias_norm FROM sem_aliases").fetchall()
    }
    assert "vat模板x" in norms


# ---- TC-SYNC-06 维度属性可选携带与填充率骤降告警 ----


def test_tc_sync_06_dims_carried_with_unknown_value(sync_env) -> None:
    """维度落库（attrs_json.dims 载体）、值域含本地无的码也落（ACL 演进缝未启用
    ——可见性不受影响）；同步报告展示 per-source 携带与填充率。"""
    snap = [
        tpl_entity("TPL_A", dims={"region": "CN"}),
        tpl_entity("TPL_B", dims={"region": "MARS"}),  # 本地维度无的码
    ]
    r = run(sync_env, snap)
    assert r["status"] == "succeeded"
    attrs = sync_env.db.execute(
        "SELECT key, attrs_json FROM sem_entities ORDER BY key"
    ).fetchall()
    carried = {k: json.loads(a).get("dims") for k, a in attrs}
    assert carried["TPL_A"] == {"region": "CN"}
    assert carried["TPL_B"] == {"region": "MARS"}  # 不校验值域——映射表归 m2s-3
    assert r["stats"]["dims_fill"]["carried"] is True
    assert r["stats"]["dims_fill"]["snapshot"] == 1.0


def test_tc_sync_06_fill_rate_drop_alert(sync_env, caplog) -> None:
    """平时携带的源突然大面积缺值 → 填充率骤降告警（对冲——防缺值静默变宽）。"""
    assert run(sync_env, tpl_snapshot(10, with_fields=False, with_dims=True))[
        "status"
    ] == "succeeded"
    with caplog.at_level("WARNING"):
        r2 = run(sync_env, tpl_snapshot(10, with_fields=False, dims_filled=1))
    assert r2["status"] == "succeeded"
    assert r2["stats"]["dims_fill"]["alert"] is True
    assert r2["stats"]["dims_fill"]["snapshot"] == 0.1
    assert r2["stats"]["dims_fill"]["library"] == 1.0
    assert any("dim fill-rate" in rec.message for rec in caplog.records)


# ---- TC-SYNC-07 run 记录与审计 ----


def test_tc_sync_07_run_records_and_audit_outbox(sync_env) -> None:
    from knowledge_lattice.domain.audit_events import EVENT_SEMANTIC_SYNC

    snap = tpl_snapshot(5, with_fields=False)
    r1 = run(sync_env, snap)
    # 空快照 → aborted_guard（库内已有该来源实体）
    r2 = run(sync_env, [])

    def runs():
        return sync_env.db.execute(
            "SELECT id, org_id, adapter, status, finished_at, stats_json"
            " FROM sem_sync_runs ORDER BY id"
        ).fetchall()

    rows = runs()
    assert len(rows) == 2
    assert rows[0][3] == "succeeded" and rows[0][1] == ORG
    assert rows[0][2] == "template_center"
    assert rows[0][4] is not None  # finished_at
    stats = json.loads(rows[0][5])
    assert stats["inserted"] == 5 and "conflicts" in stats
    assert rows[1][3] == "aborted_guard"  # running→终态留痕

    events = sync_env.db.execute(
        "SELECT event_type, payload_json FROM audit_outbox WHERE event_type = ?"
        " ORDER BY created_at, id", (EVENT_SEMANTIC_SYNC,)
    ).fetchall()
    assert len(events) == 2
    statuses = sorted(json.loads(p)["status"] for _, p in events)
    assert statuses == ["aborted_guard", "succeeded"]  # 同秒 created_at——序不依赖
    assert all(json.loads(p)["run_id"] in (r1["run_id"], r2["run_id"]) for _, p in events)
