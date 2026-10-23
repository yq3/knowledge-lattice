"""测试造数 helpers（TC-SCAF 组共享）。

时间造数纪律（TEST-CASES 口径段）：时间依赖一律直接写过去时间戳（UTC
`YYYY-MM-DD HH:MM:SS` 字符串，与 SQLite CURRENT_TIMESTAMP 同格式），不推进系统时钟。
"""

from __future__ import annotations

import sqlite3

# 过去时间戳（早于任何 CURRENT_TIMESTAMP 比较场景）
PAST_TS = "2020-01-01 00:00:00"
FUTURE_TS = "2099-01-01 00:00:00"


def seed_org(conn: sqlite3.Connection, org_id: str = "org:tax", name: str = "税务组织") -> str:
    conn.execute("INSERT INTO orgs(id, name) VALUES(?, ?)", (org_id, name))
    return org_id


def seed_dataset(conn: sqlite3.Connection, org_id: str = "org:tax", ds_id: str = "ds:vat") -> str:
    conn.execute(
        "INSERT INTO datasets(id, org_id, name) VALUES(?, ?, ?)",
        (ds_id, org_id, f"库 {ds_id}"),  # name 随 id 唯一（UNIQUE(org_id, name)）
    )
    return ds_id


def seed_user(conn: sqlite3.Connection, user_id: str = "u1", username: str | None = None) -> str:
    conn.execute(
        "INSERT INTO users(id, username) VALUES(?, ?)",
        (user_id, username or user_id),
    )
    return user_id


def seed_membership(
    conn: sqlite3.Connection,
    user_id: str = "u1",
    org_id: str = "org:tax",
    role: str = "member",
    expires_at: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO user_org_memberships(user_id, org_id, role, expires_at) VALUES(?, ?, ?, ?)",
        (user_id, org_id, role, expires_at),
    )


def seed_dimension(
    conn: sqlite3.Connection,
    org_id: str = "org:tax",
    key: str = "region",
    dim_id: str | None = None,
    grant_source: str = "local",
) -> str:
    dim_id = dim_id or f"dim:{org_id}:{key}"
    conn.execute(
        "INSERT INTO dimensions(id, org_id, key, name, grant_source) VALUES(?, ?, ?, ?, ?)",
        (dim_id, org_id, key, key, grant_source),
    )
    return dim_id


def seed_dim_value(
    conn: sqlite3.Connection,
    dim_id: str,
    value: str = "CN",
    label: str = "中国区",
    val_id: str | None = None,
) -> str:
    val_id = val_id or f"val:{dim_id}:{value}"
    conn.execute(
        "INSERT INTO dimension_values(id, dimension_id, value, label) VALUES(?, ?, ?, ?)",
        (val_id, dim_id, value, label),
    )
    return val_id


def seed_grant(
    conn: sqlite3.Connection,
    user_id: str = "u1",
    dim_id: str = "dim:org:tax:region",
    val_id: str = "val:dim:org:tax:region:CN",
    source: str = "local",
    expires_at: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id, source, expires_at)"
        " VALUES(?, ?, ?, ?, ?)",
        (user_id, dim_id, val_id, source, expires_at),
    )


def seed_document(
    conn: sqlite3.Connection,
    doc_id: str = "doc:1",
    org_id: str = "org:tax",
    dataset_id: str = "ds:vat",
    owner_user_id: str = "u1",
    title: str = "2026 Q3 VAT 申报指南",
) -> str:
    conn.execute(
        "INSERT INTO documents(id, org_id, dataset_id, title, content_hash, mime_type, parser,"
        " owner_user_id, raw_object_key)"
        " VALUES(?, ?, ?, ?, 'sha256:x', 'application/pdf', 'docling', ?, 'objects/x')",
        (doc_id, org_id, dataset_id, title, owner_user_id),
    )
    return doc_id


def insert_chunk(
    conn: sqlite3.Connection,
    doc_id: str = "doc:1",
    seq: int = 1,
    version: int = 1,
    chunk_id: str | None = None,
    content: str = "一般纳税人销售自产货物并提供安装服务的，应分别核算。",
    **overrides: object,
) -> str:
    chunk_id = chunk_id or f"chk:{doc_id}:v{version}:{seq}"
    row: dict[str, object] = {
        "id": chunk_id,
        "doc_id": doc_id,
        "seq": seq,
        "version": version,
        "content": content,
        "dims_json": "{}",
        **overrides,
    }
    cols = ", ".join(row.keys())
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO chunks({cols}) VALUES({marks})", tuple(row.values()))
    return chunk_id


def table_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def trigger_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
