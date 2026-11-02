"""C.2 REST 读端点（v1.9.5 拍板⑤ / design §6.2 L1137-1139）：

- GET /api/orgs/{org}/semantic/entities?q=&types=（同 search_entities）；
- GET /api/orgs/{org}/semantic/entities/{id}?expand=&depth=（同 get_entity）；
- GET /api/orgs/{org}/semantic/tables/{key}/describe（同 describe_table）；
- 门控 semantic:read = 组织成员（无成员关系 403——§6.3 权限口径）。
"""

from __future__ import annotations

import json

import pytest

from fake_semantic import FakeSourceAdapter, tpl_snapshot
from helpers import seed_membership, seed_org, seed_user

ORG = "org:tax"
ORG_GL = "org:gl"
NOW = "2026-10-31 09:00:00"
SNAPSHOT = tpl_snapshot(2, prefix="TPL")


@pytest.fixture()
def read_app(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic import adapters as adapters_mod
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
    )
    app = create_app(settings, gate=EmbeddingGate(), run_startup_probe=False)
    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    seed_org(conn, ORG_GL)
    for uid in ("u_full", "u_gl"):
        seed_user(conn, uid)
    seed_membership(conn, "u_full", ORG)
    seed_membership(conn, "u_gl", ORG_GL)
    for uid, token in (("u_full", "dev-static-u-full"), ("u_gl", "dev-static-u-gl")):
        conn.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                     (hash_token(token), uid))
    conn.commit()

    # 造语义数据：两模板 + restricted 一条 + 构建一次（dict_rev 锚点）
    from knowledge_lattice.core.semantic.records import EntityRecord

    restricted = EntityRecord(type="template", key="TPL_SECRET", name="机密模板")
    snapshot = [*SNAPSHOT, restricted]
    run_sync(_B(conn), ORG, FakeSourceAdapter("template_center", snapshot),
             settings=settings, snapshot=list(snapshot), now=NOW)
    conn.execute(
        "UPDATE sem_entities SET sensitivity = 'restricted'"
        " WHERE org_id = ? AND key = 'TPL_SECRET'", (ORG,))
    conn.commit()
    monkeypatch.setitem(adapters_mod.ADAPTER_FACTORIES, "__never__",
                        lambda org, cfg: None)  # 占位：确保注册表存在

    with TestClient(app) as client:
        yield {"client": client, "conn": conn, "settings": settings}
    conn.close()


def _B(conn):
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    return SqliteBackend(conn)


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- GET /semantic/entities（列表检索） ----


def test_entities_list_member_ok(read_app) -> None:
    resp = read_app["client"].get(
        f"/api/orgs/{ORG}/semantic/entities",
        params={"q": "模板tpl_0", "top_k": 5},
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entities"] and body["entities"][0]["type"] == "template"
    assert {"id", "type", "key", "name", "score", "via"} <= set(body["entities"][0])


def test_entities_list_validation_and_perms(read_app) -> None:
    client = read_app["client"]
    # 参数面：q 超长 → 400；types 非法 → 400
    assert client.get(
        f"/api/orgs/{ORG}/semantic/entities", params={"q": "x" * 201},
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG}).status_code == 400
    assert client.get(
        f"/api/orgs/{ORG}/semantic/entities",
        params={"q": "a", "types": "nonexistent"},
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG}).status_code == 400
    # 非成员 403（semantic:read 门控）
    assert client.get(
        f"/api/orgs/{ORG}/semantic/entities", params={"q": "a"},
        headers={**_h("dev-static-u-gl"), "X-Org-Id": ORG}).status_code == 403
    # 无 token 401
    assert client.get(
        f"/api/orgs/{ORG}/semantic/entities", params={"q": "a"},
        headers={"X-Org-Id": ORG}).status_code == 401


def test_entities_list_restricted_excluded(read_app) -> None:
    resp = read_app["client"].get(
        f"/api/orgs/{ORG}/semantic/entities", params={"q": "机密"},
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG})
    assert resp.status_code == 200
    assert resp.json()["entities"] == []  # restricted 对无权调用方不存在（T-S9）


# ---- GET /semantic/entities/{id}（详情与展开） ----


def test_entity_detail_expand(read_app) -> None:
    conn = read_app["conn"]
    row = conn.execute(
        "SELECT id FROM sem_entities WHERE org_id = ? AND key = 'TPL_0'",
        (ORG,)).fetchone()
    entity_id = row[0]
    resp = read_app["client"].get(
        f"/api/orgs/{ORG}/semantic/entities/{entity_id}",
        params={"expand": "has_field>", "depth": 1},
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity"]["id"] == entity_id
    assert body["nodes"] and body["edges"][0]["rel"] == "has_field"
    assert "dict_rev" in body


def test_entity_detail_not_found_and_restricted(read_app) -> None:
    conn = read_app["conn"]
    restricted_id = conn.execute(
        "SELECT id FROM sem_entities WHERE org_id = ? AND key = 'TPL_SECRET'",
        (ORG,)).fetchone()[0]
    client = read_app["client"]
    assert client.get(
        f"/api/orgs/{ORG}/semantic/entities/999999",
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG}).status_code == 404
    assert client.get(
        f"/api/orgs/{ORG}/semantic/entities/{restricted_id}",
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG}).status_code == 404
    # 参数越界 → 400
    assert client.get(
        f"/api/orgs/{ORG}/semantic/entities/1", params={"depth": 3},
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG}).status_code == 400
    # 非成员 403
    assert client.get(
        f"/api/orgs/{ORG}/semantic/entities/1",
        headers={**_h("dev-static-u-gl"), "X-Org-Id": ORG}).status_code == 403


# ---- GET /semantic/tables/{key}/describe ----


def test_table_describe_whitelist_and_member(read_app) -> None:
    client = read_app["client"]
    # 未登记表 → 403（防枚举——T-S11②；本仓无 metadata 源 → 已登记表走降级轻量节点）
    assert client.get(
        f"/api/orgs/{ORG}/semantic/tables/db.not_registered/describe",
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG}).status_code == 403
    # 非成员 403
    assert client.get(
        f"/api/orgs/{ORG}/semantic/tables/anything/describe",
        headers={**_h("dev-static-u-gl"), "X-Org-Id": ORG}).status_code == 403
