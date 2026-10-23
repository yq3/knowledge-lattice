"""共享 fixtures。

- `conn`：全新 lattice.db → 连接工厂 → 迁移到 schema v1（TC-SCAF 前置，M0a-1）。
- `matrix`：标准矩阵 fixture（TEST-CASES §三口径段——越权矩阵/编译器用例复用）：
  组织 `org:tax`（主）/ `org:gl`（隔离对照）；维度 `region`（required=1 active，
  CN/OS）+ `tax_type`（required=0 active，VAT/CIT）；用户 12 人（口径段清单）；
  文档 5 篇（org:tax / ds:vat_lib，未显式列出取值的 active 维度一律无值——#38 P1-1）。
  `channel` 维度由 T20/TC-ACL-04 用例内创建（建维度时库内已有存量文档——零回填前提）。
  时间一律造数：PAST_TS/NOW_TS/FUTURE_TS（UTC `YYYY-MM-DD HH:MM:SS`，与
  CURRENT_TIMESTAMP 同格式——v1.4 钉死）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from helpers import (
    PAST_TS,
    dim_id_for,
    seed_dataset,
    seed_dim_value,
    seed_dimension,
    seed_grant,
    seed_membership,
    seed_org,
    seed_searchable_doc,
    seed_user,
    val_id_for,
)

ORG = "org:tax"
ORG_GL = "org:gl"
DATASET = "ds:vat_lib"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "lattice.db"


@pytest.fixture()
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    from knowledge_lattice.store.sqlite import connect, migrate_db

    c = connect(db_path)
    migrate_db(c)
    yield c
    c.close()


@pytest.fixture()
def matrix(conn: sqlite3.Connection) -> sqlite3.Connection:
    """标准矩阵造数（返回已造数的连接——编译器用例在其上编译并直接执行产物 SQL）。"""
    seed_org(conn, ORG)
    seed_org(conn, ORG_GL, "隔离组织")
    seed_dataset(conn, ORG, DATASET)

    # 维度：region required=1 active（CN/OS）；tax_type required=0 active（VAT/CIT）
    seed_dimension(conn, ORG, "region")
    seed_dim_value(conn, dim_id_for(ORG, "region"), "CN")
    seed_dim_value(conn, dim_id_for(ORG, "region"), "OS")
    seed_dimension(conn, ORG, "tax_type")
    conn.execute(
        "UPDATE dimensions SET required = 0 WHERE org_id = ? AND key = 'tax_type'", (ORG,)
    )
    seed_dim_value(conn, dim_id_for(ORG, "tax_type"), "VAT")
    seed_dim_value(conn, dim_id_for(ORG, "tax_type"), "CIT")

    def grant(user_id: str, key: str, value: str, *, expires_at: str | None = None) -> None:
        seed_grant(
            conn,
            user_id=user_id,
            dim_id=dim_id_for(ORG, key),
            val_id=val_id_for(ORG, key, value),
            expires_at=expires_at,
        )

    # 用户（§三口径段清单）
    for uid in (
        "u_full", "u_cn", "u_cn_vat", "u_os", "u_expired_grant", "u_expired_member",
        "u_owner", "admin_tax", "admin_full", "sysadmin", "u_gl", "u_multi",
    ):
        seed_user(conn, uid)
    conn.execute("UPDATE users SET is_system_admin = 1 WHERE id = 'sysadmin'")

    # 成员关系（org:tax；u_expired_member 过期造数；sysadmin 无行——TC-ACL-05）
    for uid in (
        "u_full", "u_cn", "u_cn_vat", "u_os", "u_expired_grant", "u_owner", "u_multi",
    ):
        seed_membership(conn, uid, ORG)
    seed_membership(conn, "u_expired_member", ORG, expires_at=PAST_TS)
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    seed_membership(conn, "admin_full", ORG, role="org_admin")
    seed_membership(conn, "u_gl", ORG_GL, role="org_admin")
    seed_membership(conn, "u_multi", ORG_GL)

    # 授权（§三口径段清单；admin_tax 无维度授权）
    for value in ("CN", "OS"):
        grant("u_full", "region", value)
    grant("u_full", "tax_type", "VAT")
    grant("u_cn", "region", "CN")
    grant("u_cn_vat", "region", "CN")
    grant("u_cn_vat", "tax_type", "VAT")
    grant("u_os", "region", "OS")
    grant("u_expired_grant", "region", "CN", expires_at=PAST_TS)
    grant("u_expired_grant", "tax_type", "VAT")
    grant("u_expired_member", "region", "CN")
    grant("u_expired_member", "tax_type", "VAT")
    grant("u_owner", "region", "OS")
    grant("u_owner", "tax_type", "VAT")
    for value in ("CN", "OS"):
        grant("admin_full", "region", value)
    grant("admin_full", "tax_type", "VAT")

    # 文档（org:tax / ds:vat_lib；owner=u_owner；单 chunk v1 在用）
    seed_searchable_doc(conn, "d_cn", dims={"region": ["CN"], "tax_type": ["VAT"]})
    seed_searchable_doc(conn, "d_multi", dims={"region": ["CN", "OS"]})
    seed_searchable_doc(conn, "d_empty_region")
    seed_searchable_doc(conn, "d_cit", dims={"tax_type": ["CIT"]})
    seed_searchable_doc(conn, "d_os", dims={"region": ["OS"]})
    return conn
