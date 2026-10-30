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
    不同秒，同秒 ULID 并列不判跨行次序）；月库兜底同样取最后一条（链序末行）。

    R3 P3-1 修复：①月库兜底**真覆盖**——ship 后显式清空 outbox（stats 查询
    不按 shipped_at 过滤，仅 ship 不清则恒走 outbox 分支、reversed() 未验证）；
    ②时间炸弹根除——造数日期由当月墙钟派生（硬编码 2026-10-1X 跨月即红）。"""
    from knowledge_lattice.store.taskclock import utc_now_ts

    backend = matrix.make_backend()
    now = utc_now_ts()
    # outbox 三条（直插不同 created_at——当月内递增日，跨月安全）
    for i, trimmed in enumerate((1, 2, 3)):
        matrix.execute(
            "INSERT INTO audit_outbox(id, event_type, payload_json, created_at)"
            " VALUES(?, 'maintenance.run', ?, ?)",
            (f"evt-maint-{i}",
             json.dumps({"task_id": f"t{i}",
                         "stats": {"audit_outbox_trimmed": trimmed}}),
             f"{now[:8]}{10 + i:02d} 00:00:00"),
        )
    stats = backend.read_last_maintenance_stats()
    assert stats is not None and stats["audit_outbox_trimmed"] == 3, "最近一条胜出"

    # 月库兜底（真覆盖）：搬运 + 清空 outbox 行 → 只剩月库数据源
    backend.ship_outbox()
    matrix.execute("DELETE FROM audit_outbox WHERE event_type = 'maintenance.run'")
    assert backend.read_pending_outbox_events() == [] or not [
        r for r in backend.read_pending_outbox_events()
        if r["event_type"] == "maintenance.run"
    ]
    stats2 = backend.read_last_maintenance_stats()
    assert stats2 is not None and stats2["audit_outbox_trimmed"] == 3, (
        "月库兜底取最后一条（链序末行——reversed() 路径真实验证）"
    )


def test_read_last_maintenance_stats_none_when_absent(matrix) -> None:
    """无任何 maintenance.run 事件 → None（面板空态）。"""
    backend = matrix.make_backend()
    assert backend.read_last_maintenance_stats() is None


def test_list_grants_for_export_expires_normalized_str(matrix) -> None:
    """R3 P2-1：expires_at 双方言统一返回**库格式字符串**（pg TIMESTAMP 不外泄
    datetime——CSV diff 与导出同源比较，"二跑零差异"在 pg 成立的前提）；
    R3 P3-10：导出归一化同口径（store 单点收口）。"""
    backend = matrix.make_backend()
    backend.replace_local_grants(
        ORG, "u_full",
        [("region", "CN", "2027-06-30 00:00:00"), ("region", "OS", None)],
    )
    rows = backend.list_grants_for_export(ORG)
    by_val = {r["value"]: r for r in rows if r["user_id"] == "u_full"}
    # pg 臂修复前此处为 datetime.datetime —— 断言字符串即证伪
    assert by_val["CN"]["expires_at"] == "2027-06-30 00:00:00"
    assert isinstance(by_val["CN"]["expires_at"], str)
    assert by_val["OS"]["expires_at"] is None


def test_grants_diff_idempotent_after_replace(matrix) -> None:
    """R3 P2-1 集成面：replace 带非空 expires → 再读 export 数据源 → 同键
    expires_at 逐值相等（diff changed/kept 判定的方言无关前提——pg 修复前
    datetime != str 恒 changed）。"""
    backend = matrix.make_backend()
    target = [("region", "CN", "2027-06-30 00:00:00")]
    backend.replace_local_grants(ORG, "u_full", target)
    current = {
        (r["username"], r["dim_key"], r["value"]): r["expires_at"]
        for r in backend.list_grants_for_export(ORG)
        if r["source"] == "local" and r["username"] == "u_full"
    }
    assert current[("u_full", "region", "CN")] == target[0][2], (
        "store 读回值须与写入目标串相等（pg datetime 形态即恒不等）"
    )
