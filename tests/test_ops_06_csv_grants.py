"""TC-OPS-06 CSV 授权批量导入【集成｜M2】（m2-3 A 组——§6.2 GET/POST
/api/orgs/{org}/grants/export · import）。

原文（TEST-CASES L494-497）：
- ① 导入 500 行 CSV（username, dim_key, values…, expires_at）→ 幂等全量替换、
  差异预览后生效（M2.6 验收「批量导入 500 行正确」——本段提前收口）；
- ② CSV 含 org 列且与路径不一致 / ②' 一致（附录 A-12：**一律拒绝**——CSV
  不带 org 列）；
- ③ CSV 混入 sync 维度行 → sync 授权不动（T-CSV 主断言）；
- ④ 目标用户无有效成员关系 → 拒绝该用户行（防孤儿授权）；
- ⑤ 重复导入同文件 → 二跑零差异（幂等）。

REST 端点为 sqlite（app_env 惯例）；diff 语义断言双后端经 store 方法承载。
"""

from __future__ import annotations

import csv
import io

import pytest

from conftest import ORG

CSV_HEADER = "username,dim_key,value,expires_at\n"


def _make_csv(rows: list[tuple[str, str, str, str]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["username", "dim_key", "value", "expires_at"])
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


@pytest.fixture()
def _csv_env(app_env):
    """app_env + org_admin + 500 用户造数（500 行批量载体）。"""
    from helpers import seed_membership, seed_user
    from knowledge_lattice.domain.auth import hash_token

    conn = app_env["conn"]
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    conn.execute(
        "UPDATE users SET token_hash = ? WHERE id = 'admin_tax'",
        (hash_token("dev-static-admin-tax"),),
    )
    # 500 用户 × 1 行（region=OS）——M2.6「批量导入 500 行正确」载体
    for i in range(500):
        uid = f"u_bulk_{i:03d}"
        seed_user(conn, uid)
        seed_membership(conn, uid, ORG)
    conn.commit()
    return {**app_env, "admin_headers": {"Authorization": "Bearer dev-static-admin-tax"}}


def test_csv_import_500_rows_dry_run_then_apply(_csv_env) -> None:
    """① 500 行：dry_run 差异预览（500 added）→ 生效（幂等全量替换）→ 授权
    落库可展开。"""
    client = _csv_env["client"]
    csv_text = _make_csv(
        [(f"u_bulk_{i:03d}", "region", "OS", "") for i in range(500)]
    )

    # dry_run：预览不生效
    r = client.post(
        f"/api/orgs/{ORG}/grants/import", params={"dry_run": "1"},
        headers=_csv_env["admin_headers"], content=csv_text,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True and body["applied"] is False
    assert len(body["diff"]["added"]) == 500
    assert not body["rejected"]

    # 生效：500 用户全部替换
    r = client.post(
        f"/api/orgs/{ORG}/grants/import",
        headers=_csv_env["admin_headers"], content=csv_text,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] is True and body["applied_users"] == 500
    assert not body["rejected"]
    conn = _csv_env["conn"]
    assert conn.execute(
        "SELECT count(*) FROM user_dimension_grants g JOIN dimensions d"
        " ON d.id = g.dimension_id JOIN dimension_values v ON v.id = g.value_id"
        " WHERE d.org_id = ? AND d.key = 'region' AND v.value = 'OS'"
        "   AND g.user_id LIKE 'u_bulk_%'",
        (ORG,),
    ).fetchone()[0] == 500


def test_csv_import_org_column_rejected_both_ways(_csv_env) -> None:
    """② 含 org 列且与路径不一致 → 整批拒绝；②' 一致 → 同样整批拒绝
    （A-12：org 一律以路径为准，CSV 不带 org 列）。"""
    client = _csv_env["client"]
    # 不一致
    csv_bad = "username,org,dim_key,value,expires_at\nu_bulk_000,org:gl,region,OS,\n"
    r = client.post(
        f"/api/orgs/{ORG}/grants/import",
        headers=_csv_env["admin_headers"], content=csv_bad,
    )
    assert r.status_code == 400 and "org" in r.json()["detail"]
    # 一致——仍拒绝（A-12 无差别）
    csv_same = f"username,org,dim_key,value,expires_at\nu_bulk_000,{ORG},region,OS,\n"
    r = client.post(
        f"/api/orgs/{ORG}/grants/import",
        headers=_csv_env["admin_headers"], content=csv_same,
    )
    assert r.status_code == 400 and "org" in r.json()["detail"]
    # 整批拒绝 = 零写入
    conn = _csv_env["conn"]
    assert conn.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'u_bulk_000'"
    ).fetchone()[0] == 0


def test_csv_import_sync_grants_untouched(_csv_env) -> None:
    """③ T-CSV 主断言：CSV 目标态不含 sync 值 → sync 授权不动。"""
    client, conn = _csv_env["client"], _csv_env["conn"]
    # u_cn 既有 local region=CN，再造 sync region=OS（app_env 仅 region 维度）
    conn.execute(
        "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id, source)"
        " VALUES('u_cn', 'dim:org:tax:region', 'val:dim:org:tax:region:OS',"
        " 'sync:hr')"
    )
    conn.commit()
    # CSV 目标态：u_cn → region=CN（不含 sync 的 OS 行）
    csv_text = _make_csv([("u_cn", "region", "CN", "")])
    r = client.post(
        f"/api/orgs/{ORG}/grants/import",
        headers=_csv_env["admin_headers"], content=csv_text,
    )
    assert r.status_code == 200 and r.json()["applied"] is True
    rows = conn.execute(
        "SELECT d.key, v.value, g.source FROM user_dimension_grants g"
        " JOIN dimensions d ON d.id = g.dimension_id"
        " JOIN dimension_values v ON v.id = g.value_id"
        " WHERE g.user_id = 'u_cn' ORDER BY d.key, v.value"
    ).fetchall()
    assert rows == [
        ("region", "CN", "local"),        # local 被替换（保持 CN）
        ("region", "OS", "sync:hr"),      # sync 不动（主断言）
    ]


def test_csv_import_user_without_membership_rejected(_csv_env) -> None:
    """④ 目标用户无有效成员关系 → 拒绝该用户行（防孤儿授权）；其余用户照常。"""
    client, conn = _csv_env["client"], _csv_env["conn"]
    from helpers import seed_user

    seed_user(conn, "u_orphan")  # 用户在、无本组织成员关系
    seed_user(conn, "u_missing")  # 用户根本不存在
    conn.commit()
    csv_text = _make_csv([
        ("u_orphan", "region", "OS", ""),
        ("u_missing", "region", "OS", ""),
        ("u_bulk_000", "region", "OS", ""),
    ])
    r = client.post(
        f"/api/orgs/{ORG}/grants/import",
        headers=_csv_env["admin_headers"], content=csv_text,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["applied_users"] == 1  # 仅 u_bulk_000 生效
    rejected_names = {item["username"] for item in body["rejected"]}
    assert rejected_names == {"u_orphan", "u_missing"}
    assert conn.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id IN"
        " ('u_orphan', 'u_missing')"
    ).fetchone()[0] == 0  # 零孤儿授权


def test_csv_import_same_file_twice_zero_diff(_csv_env) -> None:
    """⑤ 同文件二跑 → 零差异（幂等）：第一跑生效后，第二跑 dry_run 的
    added/removed/changed 全空。"""
    client = _csv_env["client"]
    csv_text = _make_csv([
        ("u_bulk_000", "region", "OS", ""),
        ("u_bulk_001", "region", "CN", "2027-12-31 00:00:00"),
    ])
    r = client.post(
        f"/api/orgs/{ORG}/grants/import",
        headers=_csv_env["admin_headers"], content=csv_text,
    )
    assert r.status_code == 200 and r.json()["applied"] is True

    # 二跑（dry_run 预览差异）：全空
    r = client.post(
        f"/api/orgs/{ORG}/grants/import", params={"dry_run": "1"},
        headers=_csv_env["admin_headers"], content=csv_text,
    )
    body = r.json()
    assert body["diff"]["added"] == []
    assert body["diff"]["removed"] == []
    assert body["diff"]["changed"] == []
    assert body["diff"]["kept"] == 2
    # 二跑生效态也不变（幂等全量替换——数据恒定）
    r = client.post(
        f"/api/orgs/{ORG}/grants/import",
        headers=_csv_env["admin_headers"], content=csv_text,
    )
    assert r.status_code == 200 and r.json()["applied"] is True
    conn = _csv_env["conn"]
    assert conn.execute(
        "SELECT count(*) FROM user_dimension_grants WHERE user_id = 'u_bulk_000'"
    ).fetchone()[0] == 1


def test_csv_import_removal_semantics(_csv_env) -> None:
    """全量替换的删除语义：首跑授予两值、二跑 CSV 只剩一值 → 差一值被删
    （removed 进预览）。"""
    client = _csv_env["client"]
    first = _make_csv([
        ("u_bulk_000", "region", "CN", ""),
        ("u_bulk_000", "region", "OS", ""),
    ])
    client.post(
        f"/api/orgs/{ORG}/grants/import",
        headers=_csv_env["admin_headers"], content=first,
    )
    second = _make_csv([("u_bulk_000", "region", "CN", "")])
    r = client.post(
        f"/api/orgs/{ORG}/grants/import", params={"dry_run": "1"},
        headers=_csv_env["admin_headers"], content=second,
    )
    body = r.json()
    assert body["diff"]["added"] == []
    assert body["diff"]["removed"] == [
        {"username": "u_bulk_000", "dim_key": "region", "value": "OS"}
    ]
    assert body["diff"]["kept"] == 1


def test_csv_export_local_only_and_roundtrip(_csv_env) -> None:
    """导出：无 org 列、仅 local 行（sync 不导出）；导入导出往返（export →
    import 同文件零差异）。"""
    client, conn = _csv_env["client"], _csv_env["conn"]
    conn.execute(
        "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id, source)"
        " VALUES('u_cn', 'dim:org:tax:region', 'val:dim:org:tax:region:OS',"
        " 'sync:hr')"
    )
    conn.commit()
    r = client.get(
        f"/api/orgs/{ORG}/grants/export", headers=_csv_env["admin_headers"]
    )
    assert r.status_code == 200
    text = r.text
    header = text.splitlines()[0]
    assert header == "username,dim_key,value,expires_at", "CSV 无 org 列（A-12）"
    lines = list(csv.DictReader(io.StringIO(text)))
    # local 行 = u_full（CN+OS）+ u_cn（CN）+ admin_tax（无）；sync 的 u_cn OS 不导出
    assert all(
        not (row["username"] == "u_cn" and row["value"] == "OS")
        for row in lines
    ), "sync 行不导出"
    assert any(row["username"] == "u_full" for row in lines)

    # 往返：export 产物 import（dry_run）→ 零差异
    r = client.post(
        f"/api/orgs/{ORG}/grants/import", params={"dry_run": "1"},
        headers=_csv_env["admin_headers"], content=text,
    )
    body = r.json()
    assert body["diff"]["added"] == [] and body["diff"]["removed"] == []
    assert body["diff"]["changed"] == []


def test_csv_import_permission_and_org_scope(_csv_env) -> None:
    """权限：非 org_admin → 403；他组织路径 → 403（org_scoped 成员校验）。"""
    client = _csv_env["client"]
    member = {"Authorization": f"Bearer {_csv_env['static']['u_full']}"}
    r = client.post(
        f"/api/orgs/{ORG}/grants/import", headers=member, content=CSV_HEADER
    )
    assert r.status_code == 403
    r = client.get(f"/api/orgs/{ORG}/grants/export", headers=member)
    assert r.status_code == 403
