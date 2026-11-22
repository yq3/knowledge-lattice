"""m2-3 R2 P2-4：4 个新 store 读方法的 pg 臂覆盖（matrix 参数化——双后端）。

- list_grants_for_export（CSV 导出/差异计算数据源）；
- find_user_by_username（CSV 导入解析）；
- read_pending_outbox_events（审计分级查询未搬运部分）；
- read_last_maintenance_stats（B4 stats——P3-1：outbox 多条取最近 + 月库兜底
  取**最后一条**）。
"""

from __future__ import annotations

import json

import pytest

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
    # 次序契约=（created_at, id）双键——同秒 uuid4 随机 id 并列下不作跨行次序断言
    assert {p["event_type"] for p in pending} == {"document.upload", "document.delete"}
    assert all(p["payload_json"] for p in pending)

    backend.ship_outbox()
    assert backend.read_pending_outbox_events() == []


def test_read_last_maintenance_stats_latest_wins(matrix) -> None:
    """B4 stats：outbox 多条取**最近一条**（P3-1——created_at 双键；造数显式
    不同秒，同秒 uuid4 并列不判跨行次序）；月库兜底同样取最后一条（链序末行）。

    R3 P3-1 修复：①月库兜底**真覆盖**——ship 后显式清空 outbox（stats 查询
    不按 shipped_at 过滤，仅 ship 不清则恒走 outbox 分支、reversed() 未验证）；
    ②时间炸弹根除——造数日期由当月墙钟派生（硬编码 2026-10-1X 跨月即红）。

    m2-6 B⑩（R3 Committer P3 ④锁死）：**值序与时间序反向造数**——trimmed
    随日期递减（(3,2,1)），「取最近」的断言对「取值最大」的实现恒红（此前
    同向造数 (1,2,3) 下两种实现同绿——写法松）；双分支（outbox/月库兜底）
    同口径锁死。"""
    from knowledge_lattice.store.taskclock import utc_now_ts

    backend = matrix.make_backend()
    now = utc_now_ts()
    # outbox 三条（直插不同 created_at——当月内递增日，跨月安全；
    # trimmed 与日期**反向**：日期最大者 trimmed=1）
    for i, trimmed in enumerate((3, 2, 1)):
        matrix.execute(
            "INSERT INTO audit_outbox(id, event_type, payload_json, created_at)"
            " VALUES(?, 'maintenance.run', ?, ?)",
            (f"evt-maint-{i}",
             json.dumps({"task_id": f"t{i}",
                         "stats": {"audit_outbox_trimmed": trimmed}}),
             f"{now[:8]}{10 + i:02d} 00:00:00"),
        )
    stats = backend.read_last_maintenance_stats()
    assert stats is not None and stats["audit_outbox_trimmed"] == 1, (
        "最近一条胜出（日期最大——反向值序下取值最大实现恒红）"
    )

    # 月库兜底（真覆盖）：搬运 + 清空 outbox 行 → 只剩月库数据源
    backend.ship_outbox()
    matrix.execute("DELETE FROM audit_outbox WHERE event_type = 'maintenance.run'")
    assert backend.read_pending_outbox_events() == [] or not [
        r for r in backend.read_pending_outbox_events()
        if r["event_type"] == "maintenance.run"
    ]
    stats2 = backend.read_last_maintenance_stats()
    assert stats2 is not None and stats2["audit_outbox_trimmed"] == 1, (
        "月库兜底取最后一条（链序末行——reversed() 路径真实验证，反向值序锁死）"
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


# ============ m2-6 B④/B⑤：read_org_audit 下沉 + AuditChainError 机器码 ============


def test_read_org_audit_sink_filters_and_orders(matrix) -> None:
    """B④ 下沉：双源合并（outbox 未搬运行进结果）+ org 过滤 + action 前缀 +
    最近在前 + limit 截断——API 审计分级查询读路径的 store 级锚点
    （P3-6④/R2：排序断言补齐——created_at 降序=最近在前）。"""
    backend = matrix.make_backend()
    backend.append_outbox("member.add", json.dumps({"org_id": ORG, "actor": "a1"}))
    backend.append_outbox("member.remove", json.dumps({"org_id": ORG, "actor": "a2"}))
    backend.append_outbox("document.upload", json.dumps({"org_id": "org:gl"}))

    rows = backend.read_org_audit(ORG)
    actions = [r["action"] for r in rows]
    assert set(actions) == {"member.add", "member.remove"}, "org:gl 行被过滤"

    only_add = backend.read_org_audit(ORG, action="member.add")
    assert [r["action"] for r in only_add] == ["member.add"], "action 前缀过滤"

    limited = backend.read_org_audit(ORG, limit=1)
    assert len(limited) == 1

    # 排序（P3-6④）：最近在前（created_at 降序——同秒 id 兜底序）
    created = [r.get("created_at") or "" for r in rows]
    assert created == sorted(created, reverse=True), (
        f"面板序=最近在前: {created}"
    )


def test_audit_chain_error_codes() -> None:
    """B⑤：AuditChainError 携带分类机器码——**断言 3 码**
    （multi_heads/hash_mismatch/fork）；cycle/orphan_rows 为防御分支（在
    「append 前逐行 hash 校验」与链头判定语义下不可静态构造——见下方收窄
    注记，R2 P3-6③/R3 P3-5 如实声明），消费面按 code 分级处置不解析消息文本。"""
    from knowledge_lattice.store.audit_chain import (
        AuditChainError,
        compute_row_hash,
        walk_chain,
    )

    def _row(rid: str, prev: str, payload: str = "x") -> dict:
        row = {
            "id": rid, "org_id": "o", "actor": "a", "action": "document.upload",
            "target_type": None, "target_id": None, "outcome": "accepted",
            "request_id": None, "detail_json": payload, "created_at": "t",
            "prev_hash": prev,
        }
        row["row_hash"] = compute_row_hash(row, prev)
        return row

    # 正常链
    r1, r2 = _row("e1", ""), _row("e2", "")
    r2["prev_hash"] = r1["row_hash"]
    r2["row_hash"] = compute_row_hash(r2, r1["row_hash"])
    assert [r["id"] for r in walk_chain([r2, r1])] == ["e1", "e2"]

    # hash_mismatch：篡改行
    tampered = dict(r2)
    tampered["detail_json"] = "tampered"
    with pytest.raises(AuditChainError) as ei:
        walk_chain([r1, tampered])
    assert ei.value.code == "hash_mismatch"

    # multi_heads：两条不同链头的独立链（prev 均不在批内 hash 集）
    r3 = _row("e3", "sha256:external-prev")
    with pytest.raises(AuditChainError) as ei:
        walk_chain([r1, r3])
    assert ei.value.code == "multi_heads"

    # fork：同 prev 两行
    r2b = _row("e2b", r1["row_hash"])
    with pytest.raises(AuditChainError) as ei:
        walk_chain([r1, r2, r2b])
    assert ei.value.code == "fork"

    # orphan_rows / cycle 两个防御分支的**可达性收窄**（P3-6③/R2——补断言
    # 或收窄 docstring，选收窄）：
    # - orphan（prev 指向批外 hash）首先构成第二链头，被 multi_heads 拦截
    #   ——orphan_rows 是 len 兜底防御（单链头且遍历不达的构造在本算法
    #   prev/hash 语义下不可独立成立：prev 在批内 hash 集则必达，不在则成
    #   链头）；
    # - cycle（seen 命中）在「append 前逐行 hash 校验」约束下**不可静态构造**
    #   （闭环要求 row_hash 方程解——prev 依赖对端 hash 而 hash 依赖 prev），
    #   该分支防御动态损坏形态。两分支经 docstring 声明保留，不伪造断言。
    orphan = _row("orphan", "sha256:nowhere")
    with pytest.raises(AuditChainError) as ei:
        walk_chain([r1, r2, orphan])
    assert ei.value.code == "multi_heads", "孤儿实际触发路径=第二链头"


def test_list_members_and_orgs_expires_normalized_str(matrix) -> None:
    """P3-1（m3-1 Committer 移交——m3-2 修）：list_members /
    list_orgs_for_user 的 expires_at 双方言统一**库格式字符串**（pg to_char
    归一——psycopg datetime 不外泄，B⑦ 双方言 JSON 等价；仿
    test_list_grants_for_export_expires_normalized_str 先例）。"""
    import re

    backend = matrix.make_backend()
    members = backend.list_members(ORG)
    by_uid = {m["user_id"]: m for m in members}
    # matrix 造数：u_expired_member 带过期 membership、u_full 永久
    exp = by_uid["u_expired_member"]["expires_at"]
    assert isinstance(exp, str), (
        f"expires_at 必须为字符串（pg 臂修复前为 datetime）——got {type(exp)}")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", exp), exp
    assert by_uid["u_full"]["expires_at"] is None

    orgs = backend.list_orgs_for_user("u_expired_member")
    assert orgs and orgs[0]["org_id"] == ORG
    assert isinstance(orgs[0]["expires_at"], str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", orgs[0]["expires_at"])
    assert backend.list_orgs_for_user("u_full")[0]["expires_at"] is None
