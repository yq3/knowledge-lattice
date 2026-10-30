"""m2-3 R2 P2-4：4 个新 store 读方法的 pg 臂覆盖（matrix 参数化——双后端）。

- list_grants_for_export（CSV 导出/差异计算数据源）；
- find_user_by_username（CSV 导入解析）；
- read_pending_outbox_events（审计分级查询未搬运部分）；
- read_last_maintenance_stats（B4 stats——P3-1：outbox 多条取最近 + 月库兜底
  取**最后一条**）。
"""

from __future__ import annotations

import json

from conftest import ORG


def test_list_grants_for_export_shape_and_sync_tag(matrix) -> None:
    """导出数据源：username/dim_key/value/expires_at/source 列齐、sync 行标注、
    username→key→value 稳定序。"""
    backend = matrix.make_backend()
    rows = backend.list_grants_for_export(ORG)
    assert rows, "matrix 造数（u_full/u_cn/…）应有授权行"
    assert all(
        set(r) == {"username", "user_id", "dim_key", "value", "expires_at", "source"}
        for r in rows
    )
    by_user = {(r["user_id"], r["dim_key"], r["value"]): r for r in rows}
    assert ("u_full", "region", "CN") in by_user
    assert by_user[("u_full", "region", "CN")]["source"] == "local"
    assert by_user[("u_full", "region", "CN")]["username"] == "u_full"
    # expires_at 造数行回读（pg TIMESTAMP / sqlite TEXT 双臂各自原生形态）
    exp = by_user.get(("u_expired_grant", "region", "CN"))
    assert exp is not None and exp["expires_at"] is not None
    # sync 标注（造一行）
    matrix.execute(
        "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id, source)"
        " VALUES('u_cn', 'dim:org:tax:tax_type', 'val:dim:org:tax:tax_type:VAT',"
        " 'sync:hr')"
    )
    rows2 = backend.list_grants_for_export(ORG)
    sync = [r for r in rows2 if r["source"] == "sync:hr"]
    assert len(sync) == 1 and sync[0]["value"] == "VAT"
    # 稳定序（username, key, value）
    keys = [(r["username"], r["dim_key"], r["value"]) for r in rows2]
    assert keys == sorted(keys)


def test_find_user_by_username(matrix) -> None:
    """username 解析：命中返 id/系统管理员位；未命中 None。"""
    backend = matrix.make_backend()
    found = backend.find_user_by_username("u_full")
    assert found is not None and found["id"] == "u_full"
    assert found["is_system_admin"] in (0, 1, False, True)
    sysadmin = backend.find_user_by_username("sysadmin")
    assert sysadmin is not None and sysadmin["id"] == "sysadmin"
    assert sysadmin["is_system_admin"]
    assert backend.find_user_by_username("no_such_user") is None


def test_read_pending_outbox_events_and_ship_drain(matrix) -> None:
    """未搬运行读取：行在场（created_at,id 序）；搬运后清空。"""
    backend = matrix.make_backend()
    backend.append_outbox("document.upload", json.dumps({"org_id": ORG}))
    backend.append_outbox("document.delete", json.dumps({"org_id": ORG}))
    pending = backend.read_pending_outbox_events()
    assert len(pending) == 2
    # 次序契约=（created_at, id）双键——同秒 ULID 并列下不作跨行次序断言
    assert {p["event_type"] for p in pending} == {"document.upload", "document.delete"}
    assert all(p["payload_json"] for p in pending)

    backend.ship_outbox()
    assert backend.read_pending_outbox_events() == []


def test_read_last_maintenance_stats_latest_wins(matrix) -> None:
    """B4 stats：outbox 多条取**最近一条**（P3-1——created_at 双键；造数显式
    不同秒，同秒 ULID 并列不判跨行次序）；月库兜底同样取最后一条（链序末行）。"""
    backend = matrix.make_backend()
    # outbox 三条（直插不同 created_at——append_outbox 不接受时间参数）
    for i, trimmed in enumerate((1, 2, 3)):
        matrix.execute(
            "INSERT INTO audit_outbox(id, event_type, payload_json, created_at)"
            " VALUES(?, 'maintenance.run', ?, ?)",
            (f"evt-maint-{i}",
             json.dumps({"task_id": f"t{i}",
                         "stats": {"audit_outbox_trimmed": trimmed}}),
             f"2026-10-{10 + i:02d} 00:00:00"),
        )
    stats = backend.read_last_maintenance_stats()
    assert stats is not None and stats["audit_outbox_trimmed"] == 3, "最近一条胜出"

    # 月库兜底：搬运后 outbox 清空 → 从当月月库读（仍取最后一条=链序末行）
    backend.ship_outbox()
    assert backend.read_pending_outbox_events() == []
    stats2 = backend.read_last_maintenance_stats()
    assert stats2 is not None and stats2["audit_outbox_trimmed"] == 3, (
        "月库兜底取最后一条（链序末行）"
    )


def test_read_last_maintenance_stats_none_when_absent(matrix) -> None:
    """无任何 maintenance.run 事件 → None（面板空态）。"""
    backend = matrix.make_backend()
    assert backend.read_last_maintenance_stats() is None
