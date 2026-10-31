"""m2s-4 REST/MCP 面（design §6.2 L1136 + §6.3 annotate 契约）：

- POST /api/orgs/{org}/semantic/annotate（semantic:read——同 MCP annotate；
  >4000 字 400 / context_entities>20 400——TC-SEM-07）；
- GET /api/orgs/{org}/semantic/l0（TC-SEM-06：片段 + dict_rev）；
- GET /api/orgs/{org}/semantic/builds/{id}/report（semantic:admin——A4 构建
  报告：计数/自动机规模与耗时/dict_rev 分量/缺源警告/评测指标）；
- MCP `annotate` 工具（semantic 组第四工具——FR-5）。
"""

from __future__ import annotations

import json

import pytest

from fake_semantic import FakeSourceAdapter
from helpers import seed_membership, seed_org, seed_user

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.domain.auth import hash_token
    from knowledge_lattice.store.sqlite import connect

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
        semantic_eval_golden_path="",   # 关闭黄金集（本文件不评评测）
    )
    app = create_app(settings, gate=EmbeddingGate(), run_startup_probe=False)
    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    for uid in ("u_full", "u_admin", "u_out"):
        seed_user(conn, uid)
    seed_membership(conn, "u_full", ORG)
    seed_membership(conn, "u_admin", ORG, role="org_admin")
    for uid, token in (("u_full", "dev-static-u-full"),
                       ("u_admin", "dev-static-u-admin"),
                       ("u_out", "dev-static-u-out")):
        conn.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                     (hash_token(token), uid))
    conn.commit()

    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    b = SqliteBackend(conn)
    recs = [
        EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣",
                     aliases=("进项抵扣",)),
        EntityRecord(type="template", key="TPL_VAT_INPUT", name="进项采集模板"),
        EntityRecord(type="table", key="ods.vat_input_invoice", name="进项发票表"),
    ]
    run_sync(b, ORG, FakeSourceAdapter("template_center", recs),
             settings=settings, snapshot=list(recs), now=NOW)
    # L0 条目：curated definition + l0 标记（经合并面写入）
    row = b.sem_entity_by_key(ORG, "concept", "vat.input_credit")
    b.sem_write_curated_batch(ORG, [{
        "type": "concept", "key": "vat.input_credit",
        "curated_json": json.dumps(
            {"definition": "购进货物后从销项税额中抵减的进项税额。", "l0": True},
            ensure_ascii=False),
        "curated_rev": "r1", "sensitivity": "normal",
    }])
    del row
    build = run_build(b, ORG, settings=settings)

    with TestClient(app) as client:
        yield {"client": client, "conn": conn, "settings": settings,
               "backend": b, "build": build}
    conn.close()


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- POST /semantic/annotate ----


def test_annotate_member_ok(app_env) -> None:
    resp = app_env["client"].post(
        f"/api/orgs/{ORG}/semantic/annotate",
        json={"text": "本月的进项抵扣怎么算"},
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dict_rev"] == app_env["build"]["dict_rev"]
    assert body["mentions"], body
    m = body["mentions"][0]
    assert {"span", "surface", "entity_id", "type", "name", "confidence",
            "via", "ambiguous"} <= set(m)
    assert m["entity_key"] == "concept:vat.input_credit"
    assert m["via"] == "ac"
    assert "candidates" in body


def test_annotate_non_member_403(app_env) -> None:
    resp = app_env["client"].post(
        f"/api/orgs/{ORG}/semantic/annotate",
        json={"text": "进项抵扣"},
        headers=_h("dev-static-u-out"))
    assert resp.status_code == 403


def test_annotate_over_4000_chars_400(app_env) -> None:
    resp = app_env["client"].post(
        f"/api/orgs/{ORG}/semantic/annotate",
        json={"text": "进项抵扣" * 1200},
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG})
    assert resp.status_code == 400


def test_annotate_context_entities_over_20_400(app_env) -> None:
    resp = app_env["client"].post(
        f"/api/orgs/{ORG}/semantic/annotate",
        json={"text": "进项抵扣", "context_entities": list(range(1, 22))},
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG})
    assert resp.status_code == 400


def test_annotate_negative_text_zero_mentions(app_env) -> None:
    resp = app_env["client"].post(
        f"/api/orgs/{ORG}/semantic/annotate",
        json={"text": "今天天气不错，适合散步"},
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG})
    assert resp.status_code == 200
    assert resp.json()["mentions"] == []


# ---- GET /semantic/l0（TC-SEM-06） ----


def test_l0_export_fragments_with_dict_rev(app_env) -> None:
    resp = app_env["client"].get(
        f"/api/orgs/{ORG}/semantic/l0",
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dict_rev"] == app_env["build"]["dict_rev"]
    assert body["fragments"], body
    frag = body["fragments"][0]
    assert {"entity_key", "type", "name", "text"} <= set(frag)
    assert "进项税额抵扣" in frag["text"]
    assert "token_estimate" in body


def test_l0_non_member_403(app_env) -> None:
    resp = app_env["client"].get(
        f"/api/orgs/{ORG}/semantic/l0", headers=_h("dev-static-u-out"))
    assert resp.status_code == 403


# ---- GET /semantic/builds/{id}/report（A4） ----


def test_build_report_admin_ok(app_env) -> None:
    build_id = app_env["build"]["build_id"]
    resp = app_env["client"].get(
        f"/api/orgs/{ORG}/semantic/builds/{build_id}/report",
        headers={**_h("dev-static-u-admin"), "X-Org-Id": ORG})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["build_id"] == build_id
    assert body["dict_rev"] == app_env["build"]["dict_rev"]
    # 实体/别名计数
    assert body["counts"]["entities"] == 3
    assert body["counts"]["aliases"] >= 3
    # AC 自动机规模与构建耗时
    assert {"keys", "nodes", "build_ms"} <= set(body["ac_automaton"])
    assert body["ac_automaton"]["keys"] >= 1
    # dict_rev 各分量
    comps = body["dict_rev_components"]
    assert {"entities", "aliases", "relations", "yaml_rev",
            "embed_model"} <= set(comps)
    # 缺源警告（五源仅 template_center 有数据 → 其余四源警告）
    missing = {w["source"] for w in body["missing_sources"]}
    assert {"metadata", "scenario_config", "report_center",
            "yaml"} <= missing
    # 评测指标位（本环境关闭黄金集 → skipped 注记）
    assert "eval" in body and (
        body["eval"].get("skipped") or "metrics" in body["eval"])


def test_build_report_non_admin_403(app_env) -> None:
    build_id = app_env["build"]["build_id"]
    resp = app_env["client"].get(
        f"/api/orgs/{ORG}/semantic/builds/{build_id}/report",
        headers={**_h("dev-static-u-full"), "X-Org-Id": ORG})
    assert resp.status_code == 403


def test_build_report_unknown_404(app_env) -> None:
    resp = app_env["client"].get(
        f"/api/orgs/{ORG}/semantic/builds/999999/report",
        headers={**_h("dev-static-u-admin"), "X-Org-Id": ORG})
    assert resp.status_code == 404


# ---- MCP annotate 工具（沿用 test_mcp_semantic_tools 的 _mcp 模式） ----


def _mcp(app_env, user: str):
    import httpx
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    from knowledge_lattice.domain.auth import issue_dev_jwt

    app = app_env["client"].app
    token = issue_dev_jwt(app_env["settings"], user_id=user, org=ORG)

    def factory(**kw):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)

    return Client(StreamableHttpTransport(
        url="http://testserver/mcp", headers={"Authorization": f"Bearer {token}"},
        httpx_client_factory=factory))


def test_mcp_annotate_tool(app_env) -> None:
    import asyncio

    async def flow():
        async with _mcp(app_env, "u_full") as client:
            result = await client.call_tool(
                "annotate", {"text": "进项抵扣的口径是什么"})
            return json.loads(result.content[0].text)

    payload = asyncio.run(flow())
    assert payload["mentions"]
    assert payload["mentions"][0]["entity_key"] == "concept:vat.input_credit"
    assert payload["mentions"][0]["via"] == "ac"


def test_mcp_annotate_non_member_tool_error(app_env) -> None:
    import asyncio

    from fastmcp.exceptions import ToolError

    async def flow():
        async with _mcp(app_env, "u_out") as client:
            await client.call_tool("annotate", {"text": "进项抵扣"})

    with pytest.raises(ToolError):
        asyncio.run(flow())
