"""测试造数 helpers（TC-SCAF 组 + M0a-2 ACL 编译器组共享）。

时间造数纪律（TEST-CASES 口径段）：时间依赖一律直接写过去时间戳（UTC
`YYYY-MM-DD HH:MM:SS` 字符串，与 SQLite CURRENT_TIMESTAMP 同格式），不推进系统时钟。
"""

from __future__ import annotations

import json
import sqlite3

# 过去时间戳（早于任何 CURRENT_TIMESTAMP 比较场景）
PAST_TS = "2020-01-01 00:00:00"
FUTURE_TS = "2099-01-01 00:00:00"
# 编译器 :now 造数锚点（晚于全部 PAST_TS、早于 FUTURE_TS——过期/有效判定基准）
NOW_TS = "2026-06-01 12:00:00"


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
        "dims_json": "[]",  # 文档维度冗余投影为多值数组（D19）——json_each 逐元素展开
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


# ============ M0a-2 ACL 编译器组（标准矩阵 fixture 造数，TEST-CASES §三口径段） ============


def dim_id_for(org_id: str, key: str) -> str:
    """矩阵造数 id 约定（与 seed_dimension/seed_dim_value 的默认 id 生成一致）。"""
    return f"dim:{org_id}:{key}"


def val_id_for(org_id: str, key: str, value: str) -> str:
    return f"val:{dim_id_for(org_id, key)}:{value}"


def grant_by_key(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    org_id: str = "org:tax",
    key: str = "region",
    value: str = "CN",
    expires_at: str | None = None,
) -> None:
    """按 (org, 维度 key, 取值) 种授权行（id 走默认约定）。"""
    seed_grant(
        conn,
        user_id=user_id,
        dim_id=dim_id_for(org_id, key),
        val_id=val_id_for(org_id, key, value),
        expires_at=expires_at,
    )


def seed_doc_dims(
    conn: sqlite3.Connection,
    doc_id: str,
    dims: dict[str, list[str]],
    *,
    org_id: str = "org:tax",
) -> None:
    """文档维度造数（**合并**语义——回填场景保留既有维度行）：document_dimensions
    追加新行 + chunks.dims_json 冗余投影按全量重投影。

    按块 json_each 模板（读 dims_json）与按文档 visible_docs CTE（读
    document_dimensions）两写法逐字等价的前提——两处数据源必须一致（TC-ACL-07）。
    未列出的维度一律无值（口径段缺省约定——#38 P1-1）。
    """
    projection: dict[str, list[str]] = {}
    for dim_key, value in conn.execute(
        "SELECT dim.key, v.value FROM document_dimensions dd"
        " JOIN dimensions dim ON dim.id = dd.dimension_id"
        " JOIN dimension_values v ON v.id = dd.value_id"
        " WHERE dd.doc_id = ? ORDER BY dim.key, v.value",
        (doc_id,),
    ):
        projection.setdefault(dim_key, []).append(value)
    for key, values in dims.items():
        for value in values:
            conn.execute(
                "INSERT INTO document_dimensions(doc_id, dimension_id, value_id)"
                " VALUES(?, ?, ?)",
                (doc_id, dim_id_for(org_id, key), val_id_for(org_id, key, value)),
            )
        projection.setdefault(key, []).extend(values)
    conn.execute(
        "UPDATE chunks SET dims_json = ? WHERE doc_id = ?",
        (json.dumps(projection), doc_id),
    )


def seed_searchable_doc(
    conn: sqlite3.Connection,
    doc_id: str,
    *,
    org_id: str = "org:tax",
    dataset_id: str = "ds:vat_lib",
    owner_user_id: str = "u_owner",
    dims: dict[str, list[str]] | None = None,
    content_seg: str = "common sample",
    version: int = 1,
) -> str:
    """可检索文档：单 chunk 在用版本（active_version=version、tombstone=0）+ 维度双写。"""
    seed_document(
        conn, doc_id=doc_id, org_id=org_id, dataset_id=dataset_id, owner_user_id=owner_user_id
    )
    insert_chunk(
        conn, doc_id=doc_id, seq=1, version=version, content_seg=content_seg, title_seg=content_seg
    )
    conn.execute("UPDATE documents SET active_version = ? WHERE id = ?", (version, doc_id))
    if dims:
        seed_doc_dims(conn, doc_id, dims, org_id=org_id)
    return doc_id
