"""审计哈希链计算（FR-6——每月首条引用上月末哈希、封存记末哈希；TC-OPS-02）。

双方言公共的纯计算（无 SQL）：audit_events 行的 row_hash 与 canonical 拼接、
outbox 行 → audit_events 行的字段映射。SQLite 月库与 PG 分区共用同一哈希口径
（跨方言迁移时链可延续——恢复演练断言按此验证）。

canonical 拼接用 \\x1f（单元分隔符）join 全字段：列内不可含 \\x1f（写入侧
payload 为 JSON 文本/ULID，天然满足）；prev_hash 缺省（创世月）为空串。
"""

from __future__ import annotations

import hashlib
import json


class AuditChainError(Exception):
    """审计哈希链验证失败（m2-3 B2——读路径按链遍历后的 fail-closed 信号：
    破链（哈希不符/分叉/孤儿行）即审计完整性异常，读路径上抛不静默）。"""


# audit_events 行字段序（canonical 拼接序——冻结：改序即断链，迁移期不动）
_CHAIN_FIELDS = (
    "id", "org_id", "actor", "action", "target_type", "target_id",
    "outcome", "request_id", "detail_json", "created_at",
)

_US = "\x1f"


def compute_row_hash(record: dict, prev_hash: str | None) -> str:
    """本行哈希：sha256(prev_hash + US + 各字段 US 拼接)。"""
    parts = [(prev_hash or "")]
    for field in _CHAIN_FIELDS:
        parts.append(str(record.get(field) or ""))
    canonical = _US.join(parts)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def outbox_row_to_event(row: dict) -> dict:
    """outbox 行 → audit_events 行（字段映射——搬运侧共用）。

    outbox 行：id / event_type / payload_json / created_at；audit_events 语义列
    从 payload 提取，缺省口径：actor='system'、outcome='accepted'（治理动作落
    outbox 时都已生效；拒绝类事件由写入方在 payload 显式携带 outcome=refused）。
    detail_json 存 payload 原文（不丢信息）。

    语义列补齐（P3-2/R2——m2-3 审计访问分级按 actor/target 查询的前置）：
    - actor：payload.actor → payload.user_id（凭证/上传事件用 user_id）→ 'system'；
    - target_type/target_id：按事件类型从 payload 的 ``*_id`` 键映射
      （document.*→doc_id / task.cancel→task_id / upload.*→upload_id /
      dataset.delete→dataset_id / maintenance.run→无 target）；未匹配类型以
      detail_json（payload 原文）为准——语义列是**投影**非真相源。
    """
    try:
        payload = json.loads(row["payload_json"])
        if not isinstance(payload, dict):
            payload = {"_payload": payload}
    except (json.JSONDecodeError, TypeError):
        payload = {"_payload": row["payload_json"]}
    action = row["event_type"]
    target_type, target_id = _target_of(action, payload)
    return {
        "id": row["id"],
        "org_id": payload.get("org_id") or "",
        "actor": payload.get("actor") or payload.get("user_id") or "system",
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "outcome": payload.get("outcome") or "accepted",
        "request_id": payload.get("request_id"),
        "detail_json": row["payload_json"],
        "created_at": row["created_at"],
    }


def _target_of(action: str, payload: dict) -> tuple[str | None, str | None]:
    """事件类型 → (target_type, target_id) 投影（payload 的 *_id 键映射）。

    dimension.* 映射 dimension_id（R2 P3-4——api/admin.py 写入 payload 用
    dimension_id/value_id 键；value_id 保真在 detail_json，主 target=维度）。"""
    for prefix, target_type, key in (
        ("document.", "document", "doc_id"),
        ("task.", "task", "task_id"),
        ("upload.", "upload", "upload_id"),
        ("dataset.", "dataset", "dataset_id"),
        ("grants.", "grants", "user_id"),
        ("dimension.", "dimension", "dimension_id"),
    ):
        if action.startswith(prefix):
            value = payload.get(key)
            return (target_type, str(value) if value is not None else None)
    # 未知类型（semantic.* 预留等）：以 detail_json 为准，语义列留空
    return None, None


def month_of(ts: str) -> str:
    """'YYYY-MM-DD HH:MM:SS' → 'YYYYMM'（搬运按事件原时刻路由月库/分区）。"""
    return ts[:4] + ts[5:7]


def walk_chain(rows: list[dict]) -> list[dict]:
    """**链遍历读序**（m2-3 B2——G-13 对冲：不依赖 rowid/seq 读序）。

    输入任意顺序的 audit_events 行（含 prev_hash/row_hash），输出按链衔接的
    插入序并逐行验证 row_hash；破链（哈希不符 / 分叉 / 孤儿行 / 多链头）raise
    AuditChainError（fail-closed——审计完整性异常不可静默）。

    链头判定：prev_hash 不在本批 row_hash 集合中的行（月首条 prev=上月末哈希
    或创世空串——均不在本月集合内）；正常数据恰一个链头；空集 → []。
    """
    if not rows:
        return []
    hashes = {r.get("row_hash") for r in rows if r.get("row_hash")}
    by_prev: dict[str, list[dict]] = {}
    for r in rows:
        by_prev.setdefault(r.get("prev_hash") or "", []).append(r)
    heads = [p for p in by_prev if p not in hashes]
    if len(heads) != 1:
        raise AuditChainError(
            f"audit chain broken: expected 1 chain head, got {len(heads)}"
            f" ({len(rows)} rows)"
        )
    ordered: list[dict] = []
    cur = heads[0]
    seen: set[str] = set()
    while True:
        nxt = by_prev.get(cur)
        if not nxt:
            break  # 链尾
        if len(nxt) != 1:
            raise AuditChainError(f"audit chain fork at prev={cur[:16]}…")
        row = nxt[0]
        expected = compute_row_hash(row, row.get("prev_hash"))
        if row.get("row_hash") != expected:
            raise AuditChainError(
                f"audit row hash mismatch: id={row.get('id')!r}"
                f" (stored={str(row.get('row_hash'))[:16]}… expected={expected[:16]}…)"
            )
        if row["id"] in seen:
            raise AuditChainError(f"audit chain cycle at id={row['id']!r}")
        seen.add(row["id"])
        ordered.append(row)
        cur = row["row_hash"]
    if len(ordered) != len(rows):
        raise AuditChainError(
            f"audit chain has orphan rows: {len(rows) - len(ordered)} not on chain"
        )
    return ordered


def backfill_semantic_cols(event: dict) -> dict:
    """R1 期行语义列兜底（m2-3 B5——早期搬运行 org_id=''/actor='system'/
    target 空时，从 detail_json〔payload 原文〕重投影；已投影行不被覆盖——
    仅填空值，幂等）。

    投影逻辑与 outbox_row_to_event 同源（actor 回退链 + target 按事件类型映射）
    ——语义列是投影非真相源，detail_json 才是。
    """
    out = dict(event)
    if not out.get("detail_json"):
        return out
    try:
        payload = json.loads(out["detail_json"])
        if not isinstance(payload, dict):
            return out
    except (json.JSONDecodeError, TypeError):
        return out
    if not out.get("org_id"):
        out["org_id"] = payload.get("org_id") or ""
    if not out.get("actor") or out.get("actor") == "system":
        out["actor"] = payload.get("actor") or payload.get("user_id") or "system"
    if not out.get("target_type"):
        target_type, target_id = _target_of(out.get("action") or "", payload)
        out["target_type"], out["target_id"] = target_type, target_id
    return out


def prev_month(month: str) -> str:
    """'YYYYMM' → 上一个月（哈希链向前找最近有行月份用）。"""
    year, mon = int(month[:4]), int(month[4:6])
    if mon == 1:
        return f"{year - 1:04d}12"
    return f"{year:04d}{mon - 1:02d}"


def month_shift(month: str, delta: int) -> str:
    """月份平移（delta 可负）——保留期 cutoff / 封存月枚举共用。"""
    year, mon = int(month[:4]), int(month[4:6])
    idx = year * 12 + (mon - 1) + delta
    return f"{idx // 12:04d}{idx % 12 + 1:02d}"
