"""m3-2 B 组：G-24②⑧——持权审计两漏记补齐 + 审计事件常量单一登记处。

②两漏记（known-gaps G-24②，m2s-6 R1 P3 残留）：
- get_entity include=['attrs']（curated 缺省不在 include）时 restricted 根实体
  访问不落审计——MCP 侧审计前提曾为「curated 非空」（REST 侧无此前提）；
- 经关系展开「看到」restricted 端点（非根）不审计——补 outbox 权限事件
  （entity_ids 含根+restricted 端点）。

⑧常量单一登记处：EVENT_SEMANTIC_RESTRICTED_ACCESS 从 core/semantic/constants
迁入 domain/audit_events（import 检查 + 全调用点更新）。
"""

from __future__ import annotations

import json

import pytest

from helpers import seed_membership, seed_org, seed_user

ORG = "org:tax"
NOW = "2026-11-08 09:00:00"


@pytest.fixture()
def g24_env(backend, tmp_path):
    """restricted R（root 候选）+ 邻居 N related_to + 普通实体 E；持权用户
    u_secret（role=sem_restricted）+ 普通成员 u_full。REST+MCP 双壳。"""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from fake_providers import FakeEmbedder
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.domain.auth import hash_token

    seed_org(backend, ORG)
    for uid in ("u_full", "u_secret", "u_owner"):
        seed_user(backend, uid)
    seed_membership(backend, "u_full", ORG)
    seed_membership(backend, "u_secret", ORG, role="sem_restricted")

    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        probe_interval_s=0, maintenance_interval_s=0.0,
                        worker_mode="inline", worker_poll_s=0.05)
    b = backend.make_backend()
    recs = [
        EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣"),
        EntityRecord(type="concept", key="tax.neighbor", name="邻接概念"),
    ]
    run_sync(b, ORG, FakeSourceAdapter("template_center", recs),
             settings=settings, snapshot=list(recs), now=NOW)
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    repo = tmp_path / "yamlrepo"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "secret.yaml").write_text(
        "- id: concept:tax.secret\n  owner: o\n"
        "  name: 内部税收筹划方案\n"
        "  aliases: [内部税收筹划方案]\n"
        "  sensitivity: restricted\n"
        "  related_to: [concept:tax.neighbor]\n",
        encoding="utf-8")
    run_yaml_sync(b, ORG, YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=settings, now=NOW)
    clear_annotator_cache()
    assert run_build(b, ORG, settings=settings)["status"] == "ready"

    def _eid(key: str) -> int:
        return backend.execute(
            "SELECT id FROM sem_entities WHERE org_id = ? AND key = ?",
            (ORG, key)).fetchone()[0]

    tokens = {uid: f"dev-static-{uid.replace('_', '-')}"
              for uid in ("u_full", "u_secret")}
    for uid, token in tokens.items():
        backend.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                        (hash_token(token), uid))
    backend.commit()

    kwargs = dict(embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
                  run_startup_probe=False)
    if backend.name == "pg":
        app = create_app(settings, backend=backend.make_backend(), **kwargs)
    else:
        app = create_app(settings, **kwargs)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, app=app, db=backend, backend=b,
            tokens=tokens, eid=_eid,
            secret_id=_eid("tax.secret"), neighbor_id=_eid("tax.neighbor"),
            hdr=lambda uid: {"Authorization": f"Bearer {tokens[uid]}"},
        )


def _restricted_outbox_rows(env) -> list[dict]:
    order = "rowid" if env.db.name == "sqlite" else "created_at"
    rows = env.db.execute(
        "SELECT payload_json FROM audit_outbox"
        " WHERE event_type = 'semantic.restricted_access'"
        f" ORDER BY {order}").fetchall()
    return [json.loads(r[0]) for r in rows]


def _mcp_call(env, token: str, tool: str, args: dict) -> dict:
    """MCP 工具调用（X-Org-Id 随静态 token 注入——无 org claim 的 dev 形态）。"""
    import asyncio

    import httpx
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    def factory(**kw):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=env.app), **kw)

    async def flow():
        async with Client(StreamableHttpTransport(
            url="http://testserver/mcp",
            headers={"Authorization": f"Bearer {token}", "X-Org-Id": ORG},
            httpx_client_factory=factory)) as client:
            result = await client.call_tool(tool, args)
            return json.loads(result.content[0].text)

    return asyncio.run(flow())


# ============ ② 漏记一：include=['attrs'] 的 restricted 根（MCP 面） ============


def test_g24b1_mcp_attrs_only_restricted_root_audited(g24_env) -> None:
    """MCP get_entity include=['attrs']（无 curated）持权访问 restricted 根 →
    权限事件必须落（审计前提不得依赖 curated 非空——G-24② 漏记①）。"""
    env = g24_env
    out = _mcp_call(env, env.tokens["u_secret"], "get_entity", {
        "id": env.secret_id, "include": ["attrs"],
    })
    assert out["entity"]["id"] == env.secret_id
    assert "curated" not in out["entity"] and "attrs" in out["entity"]
    events = _restricted_outbox_rows(env)
    assert events, "include=['attrs'] 的 restricted 根访问必须落权限事件（G-24②①）"
    assert env.secret_id in events[-1]["entity_ids"]


def test_g24b1b_rest_attrs_only_restricted_root_audited(g24_env) -> None:
    """REST get_entity include=attrs（无 curated）持权访问 restricted 根 →
    权限事件落（REST 面同口径回归）。"""
    env = g24_env
    r = env.client.get(f"/api/orgs/{ORG}/semantic/entities/{env.secret_id}",
                       headers=env.hdr("u_secret"),
                       params={"include": ["attrs"]})
    assert r.status_code == 200, r.text
    events = _restricted_outbox_rows(env)
    assert events and env.secret_id in events[-1]["entity_ids"]


# ============ ② 漏记二：展开「看到」restricted 端点（非根） ============


def test_g24b2_expansion_restricted_endpoint_audited(g24_env) -> None:
    """持权 get_entity(N)（根=普通实体）展开见 restricted R 端点 → R 入权限
    事件 entity_ids（G-24② 漏记②——REST 面）。"""
    env = g24_env
    r = env.client.get(f"/api/orgs/{ORG}/semantic/entities/{env.neighbor_id}",
                       headers=env.hdr("u_secret"),
                       params={"expand": ["related_to"]})
    assert r.status_code == 200, r.text
    assert any(n["id"] == env.secret_id for n in r.json()["nodes"])
    events = _restricted_outbox_rows(env)
    assert events, "展开见 restricted 端点必须落权限事件（G-24②②）"
    assert env.secret_id in events[-1]["entity_ids"]
    assert events[-1]["tool"] == "get_entity"


def test_g24b2b_mcp_expansion_restricted_endpoint_audited(g24_env) -> None:
    """MCP 面：持权展开见 restricted 端点 → 权限事件（含根+端点 id 并集）。"""
    env = g24_env
    _mcp_call(env, env.tokens["u_secret"], "get_entity", {
        "id": env.neighbor_id, "expand": ["related_to"],
    })
    events = _restricted_outbox_rows(env)
    assert events and env.secret_id in events[-1]["entity_ids"]


def test_g24b2c_no_restricted_seen_no_event(g24_env) -> None:
    """对照：展开未见 restricted 端点（普通图）→ 无权限事件（不虚报）。"""
    env = g24_env
    r = env.client.get(f"/api/orgs/{ORG}/semantic/entities/{env.neighbor_id}",
                       headers=env.hdr("u_full"),   # 无权：R 不出现
                       params={"expand": ["related_to"]})
    assert r.status_code == 200
    assert not _restricted_outbox_rows(env), "无权面 R 不出现——零权限事件"


# ============ ⑧ 常量单一登记处（import 检查） ============


def test_g24c_constants_single_registry() -> None:
    """EVENT_SEMANTIC_RESTRICTED_ACCESS 登记处迁入 domain/audit_events；
    core/semantic/constants 不再定义；全调用点从 domain 导入（G-24⑧）。"""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "src" / "knowledge_lattice"
    # ① domain 登记处在位
    from knowledge_lattice.domain import audit_events as dom

    assert dom.EVENT_SEMANTIC_RESTRICTED_ACCESS == "semantic.restricted_access"
    assert "EVENT_SEMANTIC_RESTRICTED_ACCESS" in dom.__all__
    # ② core/semantic/constants 不再定义
    const_text = (src / "core" / "semantic" / "constants.py").read_text(
        encoding="utf-8")
    assert "EVENT_SEMANTIC_RESTRICTED_ACCESS" not in const_text, (
        "常量已迁 domain——core/semantic/constants 不得残留定义（G-24⑧）")
    # ③ 全调用点（src 内）不得再从 core.semantic.constants 导入该常量
    offenders = []
    for py in src.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for m in re.finditer(
            r"from knowledge_lattice\.core\.semantic\.constants import[^\n]*"
            r"EVENT_SEMANTIC_RESTRICTED_ACCESS", text):
            offenders.append(f"{py}: {m.group(0)}")
    assert not offenders, f"调用点必须从 domain.audit_events 导入：{offenders}"
