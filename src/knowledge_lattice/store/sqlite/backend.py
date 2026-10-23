"""SQLite 后端——StorageBackend 协议的 SQLite 实现（方法随 M0a-2+ 摄取/检索链逐个实装）。

M0a-2 落 Acl 域（store/backend.py AclBackend）：read_membership / read_grants——
§5.1 第 0/2 步的读取收口（「core 不碰 SQL」，v0.8.3）。授权展开为**单条 SQL**
（同一条语句含三重过滤：active 维度 / active 取值 / 未过期），LEFT JOIN 形态使
无授权的 active 维度也以空集出现在结果里——空授权集 → NotExists 单条件（T22）
依赖此语义。
"""

from __future__ import annotations

import sqlite3


class SqliteBackend:
    """持有单个主库连接的 SQLite 后端（线程模型：每线程一连接——design §2）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ============ Acl 域（§5.1 第 0/2 步读取收口） ============

    def read_membership(
        self, user_id: str, org_id: str, *, now: str | None = None
    ) -> dict | None:
        """有效成员关系行（含 `expires_at IS NULL OR expires_at > now` 过滤——第 0 步）。

        无有效行 → None（编译入口拒绝，403 语义）。
        """
        if now is None:
            row = self._conn.execute(
                "SELECT role, expires_at FROM user_org_memberships"
                " WHERE user_id = :uid AND org_id = :org"
                "   AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
                {"uid": user_id, "org": org_id},
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT role, expires_at FROM user_org_memberships"
                " WHERE user_id = :uid AND org_id = :org"
                "   AND (expires_at IS NULL OR expires_at > :now)",
                {"uid": user_id, "org": org_id, "now": now},
            ).fetchone()
        return None if row is None else {"role": row[0], "expires_at": row[1]}

    def read_grants(
        self, user_id: str, org_id: str, *, now: str | None = None
    ) -> dict[str, tuple[str, ...]]:
        """授权展开（第 2 步，单条 SQL）：org 的全部 active 维度 → 有效授权取值集。

        三重过滤（#34 必修 1 / T1 / T3）：dim.status='active'（retired 维度不出现）、
        v.status='active'（停用取值=收紧——视为存在但无人被授予）、
        g.expires_at 过滤（过期即失效，不等清理任务）。无授权的 active 维度以
        空元组出现（→ 渲染为 NotExists 单条件——T22）。
        """
        # 仅方言关键字选择（CURRENT_TIMESTAMP / :now），无数据值插值
        now_filter = "CURRENT_TIMESTAMP" if now is None else ":now"
        params: dict[str, object] = {"uid": user_id, "org": org_id}
        if now is not None:
            params["now"] = now
        sql = (
            "SELECT dim.key, v.value"
            " FROM dimensions dim"
            " LEFT JOIN user_dimension_grants g"
            "   ON g.dimension_id = dim.id AND g.user_id = :uid"
            f"  AND (g.expires_at IS NULL OR g.expires_at > {now_filter})"
            " LEFT JOIN dimension_values v"
            "   ON v.id = g.value_id AND v.status = 'active'"
            " WHERE dim.org_id = :org AND dim.status = 'active'"
            " ORDER BY dim.key, v.value"
        )
        grants: dict[str, set[str]] = {}
        for dim_key, value in self._conn.execute(sql, params):
            bucket = grants.setdefault(dim_key, set())
            if value is not None:  # 停用取值/无授权 → NULL 行（收紧）
                bucket.add(value)
        return {key: tuple(sorted(values)) for key, values in grants.items()}
