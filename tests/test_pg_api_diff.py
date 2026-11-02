"""m2-6 B⑧：API 级 pg diff 断言（m2-3 R3 Committer P3 登记——现仅 store 级
+Tester 临时验证，CSV dry_run 差异的 **API 面**在 pg 臂缺永久用例）。

R2 P2-1 曾在 pg 上暴露「datetime 与归一化字符串比较恒报 changed/kept 丢失」
（store 已单点归一收口）；本组在 **API 层**（TestClient → POST /grants/import
dry_run）以 pg 后端复现同断言——create_app(backend=...) 注入（m2-6 基建：
显式注入优先，缺省仍走共享工厂 build_backend——P2-4 先例扩展）。

PG 专用文件（test_pg_* 惯例——gate 的 pg 臂收集断言面）；无 DSN skip
（门禁 skip=失败）。
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("LATTICE_PG_DSN"),
    reason="LATTICE_PG_DSN 未设置（pg 臂——门禁 skip=失败）",
)

from conftest import ORG  # noqa: E402

from helpers import (  # noqa: E402
    dim_id_for,
    seed_dataset,
    seed_dim_value,
    seed_dimension,
    seed_membership,
    seed_org,
    seed_user,
    val_id_for,
)


@pytest.fixture()
def pg_app_env(pg_db, tmp_path):
    """pg 库 + create_app(backend=注入) + TestClient + org:tax 造数（成员/
    维度/授权 + admin 静态 token）。"""
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.domain.auth import hash_token
    from fake_providers import FakeEmbedder

    db = pg_db
    seed_org(db, ORG)
    seed_dataset(db, ORG, "ds:vat_lib")
    seed_dimension(db, ORG, "region")
    seed_dim_value(db, dim_id_for(ORG, "region"), "CN")
    seed_dim_value(db, dim_id_for(ORG, "region"), "OS")
    for uid in ("u_full", "u_cn", "admin_tax"):
        seed_user(db, uid)
        seed_membership(db, uid, ORG)
    db.execute(
        "UPDATE user_org_memberships SET role = 'org_admin'"
        " WHERE user_id = ? AND org_id = ?", ("admin_tax", ORG),
    )
    db.execute(
        "UPDATE users SET token_hash = ? WHERE id = ?",
        (hash_token("dev-static-admin-tax"), "admin_tax"),
    )
    # 库内既有授权：u_full region=CN（带 expires）——diff 断言载体
    db.execute(
        "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id, source,"
        " expires_at) VALUES('u_full', ?, ?, 'local', '2027-06-30 12:00:00')",
        (dim_id_for(ORG, "region"), val_id_for(ORG, "region", "CN")),
    )

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        embed_model="fake-embed", probe_interval_s=0, worker_mode="inline",
    )
    app = create_app(
        settings, embedder=FakeEmbedder(dim=8), gate=EmbeddingGate(),
        run_startup_probe=False, backend=db.make_backend(),
    )
    with TestClient(app) as client:
        yield {"client": client, "db": db,
               "admin": {"Authorization": "Bearer dev-static-admin-tax"}}


def test_pg_csv_import_dry_run_diff_normalized(pg_app_env) -> None:
    """API 级 pg diff：dry_run 差异在 pg 上按**归一化字符串**比较——既有行
    expires（库 TIMESTAMP 读回已归一）与 CSV 目标值精确相等 → changed==[] /
    kept 含该键；方向性对照：目标值不同 → changed 恰含该键（值级比较非恒真）。"""
    client, db = pg_app_env["client"], pg_app_env["db"]

    csv_same = (
        "username,dim_key,value,expires_at\n"
        "u_full,region,CN,2027-06-30 12:00:00\n"
    )
    r = client.post(
        f"/api/orgs/{ORG}/grants/import?dry_run=true",
        headers=pg_app_env["admin"], content=csv_same.encode("utf-8"),
    )
    assert r.status_code == 200, r.text
    diff = r.json()["diff"]
    assert diff["changed"] == [], "pg 侧值相等不得恒报 changed（R2 P2-1 复现面）"
    assert diff["kept"] == 1

    # 方向性：目标 expires 不同 → changed 恰含该键
    csv_diff = (
        "username,dim_key,value,expires_at\n"
        "u_full,region,CN,2028-01-01 00:00:00\n"
    )
    r = client.post(
        f"/api/orgs/{ORG}/grants/import?dry_run=true",
        headers=pg_app_env["admin"], content=csv_diff.encode("utf-8"),
    )
    assert r.status_code == 200
    diff2 = r.json()["diff"]
    assert diff2["changed"] == [
        {"username": "u_full", "dim_key": "region", "value": "CN",
         "expires_at": "2028-01-01 00:00:00"},
    ], "值级比较的方向性断言（非恒真）"

    # 生效后二跑零差异（pg 幂等口径——API 级）
    r = client.post(
        f"/api/orgs/{ORG}/grants/import",
        headers=pg_app_env["admin"], content=csv_diff.encode("utf-8"),
    )
    assert r.status_code == 200 and r.json()["applied"]
    r = client.post(
        f"/api/orgs/{ORG}/grants/import?dry_run=true",
        headers=pg_app_env["admin"], content=csv_diff.encode("utf-8"),
    )
    assert r.json()["diff"]["changed"] == [] and r.json()["diff"]["removed"] == []
