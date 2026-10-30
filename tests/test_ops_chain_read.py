"""m2-3 C 组收编：B1/B2/B5/B6 审计读路径与事件常量（m2-2 移交项）。

- **B1**：upload.reclaim 等字面量事件名常量化（domain/audit_events.py 单一登记
  处——调用面不再散落字符串）；
- **B2**：审计读路径改 **prev_hash 链遍历**（G-13 对冲——不依赖 rowid/seq 读序；
  月库侧读取按链验证：乱序容忍 + 破链可发现 fail-closed）；
- **B5**：R1 期行语义列 detail_json 兜底（早期搬运行 org_id/actor/target 为缺省
  时，读路径从 detail_json〔payload 原文〕重投影——与 B2 链遍历一并处理）；
- **B6**：pg last_row_hash NULLS 防御分支修正（WHERE seq IS NOT NULL——显式
  NULL seq 造数不误取）+ 显式 NULL seq 探针。

双后端参数化（[sqlite]/[pg]）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ============ B1：事件名常量化（单一登记处闭环） ============


def test_b1_upload_reclaim_event_constant() -> None:
    """EVENT_UPLOAD_RECLAIM 常量登记 + credentials 调用面零字面量（源码级断言
    ——m2-2 R2 P3-12 余量收编）。"""
    from knowledge_lattice.domain import audit_events

    assert audit_events.EVENT_UPLOAD_RECLAIM == "upload.reclaim"
    assert "EVENT_UPLOAD_RECLAIM" in audit_events.__all__
    # 调用面（core/docs/credentials.py）不得再出现事件名字面量
    src = Path(audit_events.__file__).resolve().parents[1] / "core" / "docs" / "credentials.py"
    text = src.read_text(encoding="utf-8")
    assert '"upload.reclaim"' not in text and "'upload.reclaim'" not in text, (
        "credentials.py 仍使用 upload.reclaim 字面量——须改用 EVENT_UPLOAD_RECLAIM 常量"
    )


def test_b1_reclaim_outbox_uses_constant(cred_env) -> None:
    """凭证回收事件落 outbox 且 event_type == 常量（功能侧闭环——沿 TC-CRED-05
    造数口径：过期未消费凭证 → purge_expired → outbox 行）。"""
    from knowledge_lattice.domain.audit_events import EVENT_UPLOAD_RECLAIM

    db = cred_env["db"]
    creds = cred_env["creds"]
    issued = creds.issue(
        org_id="org:tax", user_id="u_full", service_id=None,
        filename="x.html", size=10, sha256="0" * 64, content_type="text/html",
    )
    # 造过期：expires_at 回拨到过去
    db.execute(
        "UPDATE uploads SET expires_at = '2020-01-01 00:00:00' WHERE id = ?",
        (issued["upload_id"],),
    )
    result = creds.purge_expired()
    assert result["reclaimed"] == 1
    row = db.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = ?",
        (EVENT_UPLOAD_RECLAIM,),
    ).fetchone()
    assert row[0] == 1


# ============ B2：读路径 prev_hash 链遍历（G-13 对冲） ============


def _db_dir_of(matrix) -> Path:
    """sqlite 臂主库目录（月库与主库同目录——PRAGMA database_list main 行）。"""
    for _seq, name, file in matrix.execute("PRAGMA database_list").fetchall():
        if name == "main" and file:
            return Path(file).parent
    raise AssertionError("main database has no file path")


def _insert_monthly_row(matrix, row: dict) -> None:
    """直插月库/分区一行（绕 outbox——坏链/legacy 造数；qmark 双方言）。"""
    if matrix.is_sqlite:
        from knowledge_lattice.store.sqlite.audit import month_path

        import sqlite3

        from knowledge_lattice.store.audit_chain import month_of

        db_dir = _db_dir_of(matrix)
        mconn = sqlite3.connect(month_path(db_dir, month_of(row["created_at"])))
        try:
            mconn.execute(
                "INSERT INTO audit_events(id, org_id, actor, action, target_type,"
                " target_id, outcome, request_id, detail_json, prev_hash, row_hash,"
                " created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row["id"], row["org_id"], row["actor"], row["action"],
                 row["target_type"], row["target_id"], row["outcome"],
                 row["request_id"], row["detail_json"], row["prev_hash"],
                 row["row_hash"], row["created_at"]),
            )
            mconn.commit()
        finally:
            mconn.close()
    else:
        cols = ("id", "org_id", "actor", "action", "target_type", "target_id",
                "outcome", "request_id", "detail_json", "prev_hash", "row_hash",
                "created_at")
        marks = ", ".join("?" for _ in cols)
        matrix.execute(
            f"INSERT INTO audit_events({', '.join(cols)}) VALUES({marks})",
            tuple(row[c] for c in cols),
        )


def _seed_outbox_events(matrix, n: int = 5, org: str = "org:tax") -> list[str]:
    """造 n 条 outbox 事件并搬运（可控 id 直插——ship 按 (created_at,id) 序成链；
    返回事件 id 列表=插入序）。"""
    from knowledge_lattice.store.taskclock import utc_now_ts

    backend = matrix.make_backend()
    ids = []
    for i in range(n):
        eid = f"evt-chain-{i:03d}"
        matrix.execute(
            "INSERT INTO audit_outbox(id, event_type, payload_json, created_at)"
            " VALUES(?, ?, ?, ?)",
            (eid, "document.upload",
             json.dumps({"org_id": org, "user_id": "u_full", "doc_id": f"d{i}",
                         "seq": i}, ensure_ascii=False),
             utc_now_ts()),
        )
        ids.append(eid)
    backend.ship_outbox()
    return ids


def test_b2_read_order_independent_and_chain_verified(matrix) -> None:
    """搬运后 read_monthly_events 返回**链序**且 row_hash 验证通过；乱序容忍
    （walk_chain 对 shuffle/逆序输入恢复同一序——不依赖 rowid/seq 读序，G-13）。
    """
    import random

    from knowledge_lattice.store.audit_chain import walk_chain
    from knowledge_lattice.store.taskclock import utc_now_ts

    backend = matrix.make_backend()
    ids = _seed_outbox_events(matrix, 5)
    assert len(ids) == 5

    events = backend.read_monthly_events(when=utc_now_ts())
    assert [e["id"] for e in events] == ids, "链序应等于插入序"

    # 乱序容忍：shuffle 后 walk_chain 恢复同一序 + 哈希重算全过
    shuffled = list(events)
    random.Random(42).shuffle(shuffled)
    reordered = walk_chain(shuffled)
    assert [e["id"] for e in reordered] == ids
    # 逆序同理
    reordered2 = walk_chain(list(reversed(events)))
    assert [e["id"] for e in reordered2] == ids


def test_b2_broken_chain_detected(matrix) -> None:
    """破链可发现（fail-closed）：手工插坏哈希行 → read_monthly_events 抛
    AuditChainError（读路径按链验证——行内容被篡改即断）。"""
    from knowledge_lattice.store.audit_chain import AuditChainError
    from knowledge_lattice.store.taskclock import utc_now_ts

    backend = matrix.make_backend()
    _seed_outbox_events(matrix, 2)
    now_ts = utc_now_ts()
    # 坏行：prev 指向真实末行，row_hash 与 canonical 计算不一致（模拟内容篡改）
    tail = backend.read_monthly_events(when=now_ts)[-1]
    bad = {
        "id": "evt-tampered", "org_id": "org:tax", "actor": "u_evil",
        "action": "document.delete", "target_type": "document",
        "target_id": "d0", "outcome": "accepted", "request_id": None,
        "detail_json": "{}",
        "prev_hash": tail["row_hash"],
        "row_hash": "sha256:" + "0" * 64,  # 与 canonical 不符
        "created_at": now_ts,
    }
    _insert_monthly_row(matrix, bad)
    with pytest.raises(AuditChainError):
        backend.read_monthly_events(when=now_ts)


# ============ B5：R1 期行语义列兜底 ============


def test_b5_r1_rows_semantic_backfill(matrix) -> None:
    """R1 期搬运行（语义列缺省：org_id=''/actor='system'/target 空）读路径从
    detail_json（payload 原文）兜底重投影；已投影行不被覆盖。"""
    from knowledge_lattice.store.audit_chain import compute_row_hash
    from knowledge_lattice.store.taskclock import utc_now_ts

    backend = matrix.make_backend()
    _seed_outbox_events(matrix, 1)  # 已投影行（对照组）
    now_ts = utc_now_ts()
    tail = backend.read_monthly_events(when=now_ts)[-1]

    # R1 形态行：语义列全缺省、detail_json 为 payload 原文（含 org_id/user_id/doc_id）
    payload = {"org_id": "org:tax", "user_id": "u_cn", "doc_id": "d_cn"}
    r1 = {
        "id": "evt-r1-legacy", "org_id": "", "actor": "system",
        "action": "document.upload", "target_type": None,
        "target_id": None, "outcome": "accepted", "request_id": None,
        "detail_json": json.dumps(payload, ensure_ascii=False),
        "prev_hash": tail["row_hash"],
        "row_hash": None,  # 占位——按 canonical 计算
        "created_at": now_ts,
    }
    r1["row_hash"] = compute_row_hash(r1, r1["prev_hash"])
    _insert_monthly_row(matrix, r1)

    events = backend.read_monthly_events(when=now_ts)
    assert len(events) == 2
    by_id = {e["id"]: e for e in events}
    legacy = by_id["evt-r1-legacy"]
    # B5 兜底：语义列从 detail_json 重投影
    assert legacy["org_id"] == "org:tax"
    assert legacy["actor"] == "u_cn"
    assert legacy["target_type"] == "document" and legacy["target_id"] == "d_cn"
    # 对照组（已投影行）不被覆盖
    normal = by_id["evt-chain-000"]
    assert normal["actor"] == "u_full" and normal["org_id"] == "org:tax"


# ============ B6：pg last_row_hash NULL seq 防御分支 + 探针 ============


def test_b6_last_row_hash_null_seq_probe(matrix) -> None:
    """显式 NULL seq 造数探针：pg last_row_hash 不误取 NULL 行（取非 NULL 最大
    seq 的 row_hash）；sqlite 臂 rowid 序回归。"""
    from knowledge_lattice.store.audit_chain import compute_row_hash, month_of
    from knowledge_lattice.store.taskclock import utc_now_ts

    backend = matrix.make_backend()
    _seed_outbox_events(matrix, 3)
    now_ts = utc_now_ts()
    month = month_of(now_ts)
    events = backend.read_monthly_events(when=now_ts)
    assert len(events) == 3

    if matrix.is_sqlite:
        from knowledge_lattice.store.sqlite.audit import last_row_hash as lrh

        assert lrh(_db_dir_of(matrix), month) == events[-1]["row_hash"]
        return

    # pg 臂：显式插 NULL seq 行（防御分支唯一可达形态——正常路径 DEFAULT nextval）
    from knowledge_lattice.store.postgres.audit import last_row_hash as pg_lrh

    tail = events[-1]
    null_row = {
        "id": "evt-null-seq", "org_id": "org:tax", "actor": "system",
        "action": "maintenance.run", "target_type": None, "target_id": None,
        "outcome": "accepted", "request_id": None, "detail_json": "{}",
        "prev_hash": tail["row_hash"], "row_hash": None,
        "created_at": now_ts,
    }
    null_row["row_hash"] = compute_row_hash(null_row, null_row["prev_hash"])
    matrix.execute(
        "INSERT INTO audit_events(id, org_id, actor, action, target_type, target_id,"
        " outcome, request_id, detail_json, prev_hash, row_hash, created_at, seq)"
        " VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
        (null_row["id"], null_row["org_id"], null_row["actor"], null_row["action"],
         null_row["target_type"], null_row["target_id"], null_row["outcome"],
         null_row["request_id"], null_row["detail_json"], null_row["prev_hash"],
         null_row["row_hash"], null_row["created_at"]),
    )
    # 末哈希 = 非 NULL 最大 seq 行（显式 NULL 行被 WHERE seq IS NOT NULL 排除）
    assert pg_lrh(matrix.raw, month) == tail["row_hash"]
    # 读路径仍全量（NULL seq 行不丢）且链序正确（链遍历与 seq 无关）
    events2 = backend.read_monthly_events(when=now_ts)
    assert [e["id"] for e in events2] == [
        "evt-chain-000", "evt-chain-001", "evt-chain-002", "evt-null-seq",
    ]


# ============ R2 P3-4：dimension.* 审计事件 target 投影对齐 ============


def test_dimension_events_target_projection(matrix) -> None:
    """P3-4：dimension.value_disable / dimension.retire 的 target 投影对齐写入
    payload 键（dimension_id/value_id）——搬运后 target_type/target_id 不再空。"""
    from knowledge_lattice.store.taskclock import utc_now_ts

    backend = matrix.make_backend()
    backend.append_outbox(
        "dimension.retire",
        json.dumps({"org_id": "org:tax", "dimension_id": "dim:org:tax:channel",
                    "actor": "admin_tax"}, ensure_ascii=False),
    )
    backend.append_outbox(
        "dimension.value_disable",
        json.dumps({"org_id": "org:tax", "dimension_id": "dim:org:tax:region",
                    "value_id": "val:dim:org:tax:region:CN",
                    "actor": "admin_tax"}, ensure_ascii=False),
    )
    backend.ship_outbox()
    events = backend.read_monthly_events(when=utc_now_ts())
    by_action = {e["action"]: e for e in events}
    retire = by_action["dimension.retire"]
    assert retire["target_type"] == "dimension"
    assert retire["target_id"] == "dim:org:tax:channel"
    disable = by_action["dimension.value_disable"]
    assert disable["target_type"] == "dimension"
    assert disable["target_id"] == "dim:org:tax:region", (
        "value_disable 主 target=维度（value_id 在 detail_json 保真）"
    )


# ============ R2 P3-5：walk_chain 破链边界永久回归（Tester 临时脚本转正式） ============


def _evt(eid: str, prev: str, *, tamper: bool = False) -> dict:
    from knowledge_lattice.store.audit_chain import compute_row_hash

    row = {
        "id": eid, "org_id": "org:tax", "actor": "u", "action": "x",
        "target_type": None, "target_id": None, "outcome": "accepted",
        "request_id": None, "detail_json": "{}", "prev_hash": prev,
        "row_hash": None, "created_at": "2026-10-30 00:00:00",
    }
    row["row_hash"] = "sha256:" + "0" * 64 if tamper else compute_row_hash(row, prev)
    return row


def test_walk_chain_fork_detected() -> None:
    """分叉：两行 prev 同指一行 → AuditChainError。"""
    from knowledge_lattice.store.audit_chain import AuditChainError, walk_chain

    a = _evt("a", "")
    b = _evt("b", a["row_hash"])
    c = _evt("c", a["row_hash"])  # 分叉
    with pytest.raises(AuditChainError, match="fork"):
        walk_chain([a, b, c])


def test_walk_chain_multi_head_detected() -> None:
    """多链头：两行 prev 均不在集合内 → AuditChainError。"""
    from knowledge_lattice.store.audit_chain import AuditChainError, walk_chain

    a = _evt("a", "")
    b = _evt("b", "sha256:foreign")  # 另一链头（孤立前向引用）
    with pytest.raises(AuditChainError, match="chain head"):
        walk_chain([a, b])


def test_walk_chain_orphan_rows_detected() -> None:
    """孤儿行（R3 P3-6 改名+补真 orphan）：现指 multi-head 形态（孤立前向
    引用构成第二链头——heads>1 路径）；**真 orphan**（主链外不相交环：环行
    prev 均在批内 hash 集、不构成链头但不可达）见下方
    test_walk_chain_unreachable_orphan_segment_detected。"""
    from knowledge_lattice.store.audit_chain import AuditChainError, walk_chain

    a = _evt("a", "")
    b = _evt("b", a["row_hash"])
    x = _evt("x", "sha256:orphan")  # 孤立前向引用——第二链头（multi-head）
    with pytest.raises(AuditChainError):
        walk_chain([a, b, x])


def test_walk_chain_unreachable_orphan_segment_detected() -> None:
    """真 orphan（R3 P3-6）：主链 a→b + 不相交环 x↔y——环行 prev 互指批内
    hash（不构成链头）、主链 walk 到尾后 ordered<len(rows) → orphan 分支。"""
    from knowledge_lattice.store.audit_chain import AuditChainError, walk_chain

    a = _evt("a", "")
    b = _evt("b", a["row_hash"])

    def _raw(eid: str, prev: str) -> dict:
        return {
            "id": eid, "org_id": "org:tax", "actor": "u", "action": "x",
            "target_type": None, "target_id": None, "outcome": "accepted",
            "request_id": None, "detail_json": "{}", "prev_hash": prev,
            "row_hash": f"sha256:{eid}", "created_at": "2026-10-30 00:00:00",
        }

    x = _raw("x", "sha256:y")
    y = _raw("y", "sha256:x")  # 互指成环——prev 均在批内 hash 集、不可达
    with pytest.raises(AuditChainError, match="orphan"):
        walk_chain([a, b, x, y])


def test_walk_chain_cycle_detected() -> None:
    """环：节点 prev 互指成环（无任何链头——heads=0）→ AuditChainError。
    （真数据形态下环必然伴随哈希不衔接：结构拦截先行，hash 验证兜底。）"""
    from knowledge_lattice.store.audit_chain import AuditChainError, walk_chain

    def _raw(eid: str, prev: str) -> dict:
        return {
            "id": eid, "org_id": "org:tax", "actor": "u", "action": "x",
            "target_type": None, "target_id": None, "outcome": "accepted",
            "request_id": None, "detail_json": "{}", "prev_hash": prev,
            "row_hash": f"sha256:{eid}", "created_at": "2026-10-30 00:00:00",
        }

    p = _raw("p", "sha256:q")
    q = _raw("q", "sha256:p")  # 互指成环——零链头
    with pytest.raises(AuditChainError, match="chain head"):
        walk_chain([p, q])


def test_walk_chain_tampered_hash_detected() -> None:
    """哈希篡改：row_hash 与 canonical 不符 → AuditChainError。"""
    from knowledge_lattice.store.audit_chain import AuditChainError, walk_chain

    a = _evt("a", "")
    bad = _evt("bad", a["row_hash"], tamper=True)
    with pytest.raises(AuditChainError, match="hash mismatch"):
        walk_chain([a, bad])
