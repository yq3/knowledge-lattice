"""MCP semantic 组三工具（design §6.3——M2-S1 面上首批）：

- get_entity（T-S5 结构契约 / T-S6 防环·深度·截断 / TC-SEM-10 模板链路）；
- search_entities（TC-SEM-05 前半——别名精确>前缀>label 模糊；拼音/向量 M2-S3）；
- describe_table（T-S11 白名单 / 降级 / 5min 缓存）；
- 权限面：组织隔离（T-S7 工具面半句）+ 成员关系（semantic:read=组织成员默认）
  + restricted 实体 fail-closed 静默（T-S9 get_entity 404/search 无命中——
  持权路径 M2-S3，本段无权限面一律不可见）。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from helpers import seed_membership, seed_org, seed_user

ORG = "org:tax"
ORG_GL = "org:gl"

NOW = "2026-10-30 12:00:00"


# ---- 语义 fixture（TEST-CASES §四口径段裁剪——模板链 + 环 + 高扇出 + restricted） ----


def _sem_snapshot() -> list:
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

    out: list = []
    out.append(EntityRecord(
        type="template", key="TPL_VAT_INPUT", name="进项采集模板",
        aliases=("进项模板",)))
    out.append(EntityRecord(
        type="template_field", key="TPL_VAT_INPUT.TAX_AMT", name="税额字段",
        parent_key="template:TPL_VAT_INPUT"))
    out.append(EntityRecord(type="table", key="ods.vat_input_invoice", name="进项发票表"))
    for ck, cn in (("tax_amt", "税额"), ("inv_no", "发票号"), ("seller", "销方")):
        out.append(EntityRecord(
            type="column", key=f"ods.vat_input_invoice.{ck}", name=cn,
            parent_key="table:ods.vat_input_invoice"))
    # 高扇出：大表 300 列（fanout/节点上限用例）
    out.append(EntityRecord(type="table", key="ods.big_table", name="进项模板归集表"))
    for i in range(300):
        out.append(EntityRecord(
            type="column", key=f"ods.big_table.col_{i:03d}", name=f"列{i}",
            parent_key="table:ods.big_table"))
    # 概念（search 排序链 + 环图样本 related_to A→B→C→A）
    out.append(EntityRecord(
        type="concept", key="vat.input_credit", name="进项税额抵扣",
        aliases=("进项抵扣",)))
    # name 模糊档专属样本（名字中含查询词但非前缀——不进 alias 前缀档）
    out.append(EntityRecord(type="concept", key="c_note", name="详解进项模板"))
    for ck in ("cA", "cB", "cC"):
        out.append(EntityRecord(type="concept", key=ck, name=f"环样本{ck}"))
    out.append(EntityRecord(
        type="concept", key="tax.scheme.internal", name="内部筹划",
        aliases=("内部税收筹划方案",)))

    rel = [
        (("template", "TPL_VAT_INPUT"), "has_field",
         ("template_field", "TPL_VAT_INPUT.TAX_AMT")),
        (("template", "TPL_VAT_INPUT"), "backed_by", ("table", "ods.vat_input_invoice")),
        (("template", "TPL_VAT_INPUT"), "backed_by", ("table", "ods.big_table")),
        (("template_field", "TPL_VAT_INPUT.TAX_AMT"), "maps_to",
         ("column", "ods.vat_input_invoice.tax_amt")),
        (("concept", "cA"), "related_to", ("concept", "cB")),
        (("concept", "cB"), "related_to", ("concept", "cC")),
        (("concept", "cC"), "related_to", ("concept", "cA")),
    ]
    for i in range(300):
        rel.append((("table", "ods.big_table"), "has_column",
                    ("column", f"ods.big_table.col_{i:03d}")))
    for ck in ("tax_amt", "inv_no", "seller"):
        rel.append((("table", "ods.vat_input_invoice"), "has_column",
                    ("column", f"ods.vat_input_invoice.{ck}")))
    out.extend(RelationRecord(src=s, rel_type=r, dst=d) for s, r, d in rel)
    return out


SNAPSHOT = _sem_snapshot()

MD_CANNED = {
    "ods.vat_input_invoice": {
        "name": "进项发票表",
        "columns": [
            {"name": "tax_amt", "type": "DECIMAL", "comment": "税额", "sample": "100.00"},
            {"name": "inv_no", "type": "TEXT", "comment": "发票号"},
            {"name": "seller", "type": "TEXT", "comment": "销方名称"},
        ],
    },
}


class FakeDescribeAdapter:
    """metadata 适配器替身：describe_table 记录调用（缓存断言数据源）。"""

    name = "metadata"

    def __init__(self, *, explode: bool = False) -> None:
        self.calls: list[str] = []
        self._explode = explode

    def fetch(self, org):
        return iter([])

    def describe_table(self, table_key: str) -> dict:
        self.calls.append(table_key)
        if self._explode:
            raise TimeoutError("metadata system timeout (simulated >3s)")
        canned = MD_CANNED.get(table_key)
        if canned is None:
            raise LookupError(f"unknown table {table_key!r}")
        return dict(canned)


@pytest.fixture()
def sem_app(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.adapters import ADAPTER_FACTORIES
    from knowledge_lattice.domain.auth import hash_token, issue_dev_jwt
    from knowledge_lattice.store.sqlite import connect
    from fake_providers import FakeEmbedder
    from fake_semantic import FakeSourceAdapter

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=2560,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
        worker_poll_s=0.05,
    )
    app = create_app(settings, embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
                     run_startup_probe=False)
    monkeypatch.setitem(
        ADAPTER_FACTORIES, "template_center",
        lambda org, cfg: FakeSourceAdapter("template_center", SNAPSHOT),
    )
    describe = FakeDescribeAdapter()
    monkeypatch.setitem(
        ADAPTER_FACTORIES, "metadata", lambda org, cfg: describe)

    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    seed_org(conn, ORG_GL)
    seed_user(conn, "u_full")
    seed_membership(conn, "u_full", ORG)
    seed_user(conn, "admin_tax")
    seed_membership(conn, "admin_tax", ORG, role="org_admin")
    seed_user(conn, "u_gl")
    seed_membership(conn, "u_gl", ORG_GL)
    seed_user(conn, "u_nomem")  # 无成员关系（semantic:read 门控对照）
    for uid, token in (("u_full", "dev-static-u-full"), ("admin_tax", "dev-static-admin-tax")):
        conn.execute("UPDATE users SET token_hash = ? WHERE id = ?",
                     (hash_token(token), uid))
    conn.commit()

    with TestClient(app) as client:
        # 库内落语义图 + restricted 造数 + 构建（dict_rev 就位）
        from knowledge_lattice.core.semantic.build import run_build
        from knowledge_lattice.core.semantic.lookup import clear_describe_cache
        from knowledge_lattice.core.semantic.sync import run_sync
        from fake_semantic import FakeSourceAdapter as FSA

        clear_describe_cache()  # 模块级透传缓存测试隔离（前序用例不留残温）
        service = client.app.state.service
        run_sync(service.backend, ORG, FSA("template_center", SNAPSHOT),
                 settings=settings, snapshot=SNAPSHOT, now=NOW)
        conn.execute(
            "UPDATE sem_entities SET sensitivity = 'restricted'"
            " WHERE org_id = ? AND key = 'tax.scheme.internal'", (ORG,))
        conn.commit()
        build = run_build(service.backend, ORG, settings=settings)
        yield {
            "app": app, "client": client, "conn": conn, "settings": settings,
            "static": {"u_full": "dev-static-u-full", "admin_tax": "dev-static-admin-tax"},
            "jwt": lambda uid, org=None: issue_dev_jwt(settings, user_id=uid, org=org),
            "describe": describe, "dict_rev": build["dict_rev"],
        }
    conn.close()


def _mcp(app, token: str) -> Client:
    def factory(**kw):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)

    return Client(StreamableHttpTransport(
        url="http://testserver/mcp", headers={"Authorization": f"Bearer {token}"},
        httpx_client_factory=factory))


def _call(app, token: str, tool: str, args: dict) -> dict:
    async def flow():
        async with _mcp(app, token) as client:
            result = await client.call_tool(tool, args)
            return json.loads(result.content[0].text)

    return asyncio.run(flow())


def _call_err(app, token: str, tool: str, args: dict) -> ToolError:
    async def flow():
        async with _mcp(app, token) as client:
            await client.call_tool(tool, args)

    with pytest.raises(ToolError) as exc_info:
        asyncio.run(flow())
    return exc_info.value


# ---- TC-SEM-10 模板链路端到端（M2-S1 验收句） ----


def test_tc_sem_10_template_chain(sem_app) -> None:
    token = sem_app["jwt"]("u_full", org=ORG)
    payload = _call(sem_app["app"], token, "get_entity", {
        "key": "template:TPL_VAT_INPUT",
        "expand": ["backed_by>", "has_column>"], "depth": 2,
    })
    keys = {n["key"] for n in payload["nodes"]}
    assert "ods.vat_input_invoice" in keys, "目标表未出现（TC-SEM-10①）"
    assert "ods.vat_input_invoice.tax_amt" in keys, "目标列未出现（TC-SEM-10①）"
    rels = {(e["src"], e["rel"], e["dst"]) for e in payload["edges"]}
    assert any(r == "backed_by" for (_, r, _) in rels)
    assert any(r == "has_column" for (_, r, _) in rels)
    assert payload["truncated"] is True  # 300 列大表 → fanout 截断标志（TC-SEM-10①）
    assert payload["dict_rev"] == sem_app["dict_rev"]
    # 「模板落在哪张表、哪个字段」可答：字段侧 maps_to 展开
    p2 = _call(sem_app["app"], token, "get_entity", {
        "key": "template_field:TPL_VAT_INPUT.TAX_AMT",
        "expand": ["maps_to>"], "depth": 1,
    })
    assert {n["key"] for n in p2["nodes"]} == {"ods.vat_input_invoice.tax_amt"}
    # has_field 展开同样可达（模板的字段清单）
    p3 = _call(sem_app["app"], token, "get_entity", {
        "key": "template:TPL_VAT_INPUT", "expand": ["has_field>"], "depth": 1,
    })
    assert {n["key"] for n in p3["nodes"]} == {"TPL_VAT_INPUT.TAX_AMT"}


def test_get_entity_structure_contract(sem_app) -> None:
    """TC-SEM-05 get_entity 半句：entity/nodes/edges/truncated/dict_rev 结构齐；
    include 各参数；key/id 二选一。"""
    token = sem_app["jwt"]("u_full", org=ORG)
    payload = _call(sem_app["app"], token, "get_entity", {"key": "template:TPL_VAT_INPUT"})
    assert set(payload) >= {"entity", "nodes", "edges", "truncated", "dict_rev"}
    ent = payload["entity"]
    assert ent["type"] == "template" and ent["key"] == "TPL_VAT_INPUT"
    assert ent["status"] == "active" and "curated" in ent
    # include=aliases / attrs
    p2 = _call(sem_app["app"], token, "get_entity", {
        "key": "template:TPL_VAT_INPUT", "include": ["aliases", "attrs"]})
    assert "进项模板" in p2["entity"]["aliases"]
    assert isinstance(p2["entity"]["attrs"], dict)
    assert "curated" not in p2["entity"] or p2["entity"].get("curated") is None
    # id 定位（key/id 二选一——id 也可）
    eid = sem_app["conn"].execute(
        "SELECT id FROM sem_entities WHERE key = 'TPL_VAT_INPUT'").fetchone()[0]
    p3 = _call(sem_app["app"], token, "get_entity", {"id": eid})
    assert p3["entity"]["key"] == "TPL_VAT_INPUT"
    # 两者皆无 / 皆有 → 400
    assert "400" in str(_call_err(sem_app["app"], token, "get_entity", {}))
    assert "400" in str(_call_err(sem_app["app"], token, "get_entity", {
        "id": eid, "key": "template:TPL_VAT_INPUT"}))
    # expand 带方向后缀 derived_from<（入向）
    p4 = _call(sem_app["app"], token, "get_entity", {
        "key": "column:ods.vat_input_invoice.tax_amt", "expand": ["has_column<"],
        "depth": 1})
    assert {n["key"] for n in p4["nodes"]} == {"ods.vat_input_invoice"}


# ---- T-S6 递归展开防环/深度/截断 ----


def test_t_s6_cycle_depth_fanout_truncation(sem_app) -> None:
    token = sem_app["jwt"]("u_full", org=ORG)
    # 环图 depth=2 正常返回不死循环（A→B→C→A）
    payload = _call(sem_app["app"], token, "get_entity", {
        "key": "concept:cA", "expand": ["related_to>"], "depth": 2})
    keys = {n["key"] for n in payload["nodes"]}
    assert keys == {"cB", "cC"}
    assert payload["truncated"] is False
    # depth=3 拒绝（服务端强制 ≤2——附录 A-11）
    assert "400" in str(_call_err(sem_app["app"], token, "get_entity", {
        "key": "concept:cA", "depth": 3}))
    # fanout_limit=500 超上限拒绝
    assert "400" in str(_call_err(sem_app["app"], token, "get_entity", {
        "key": "table:ods.big_table", "fanout_limit": 500}))
    # 高扇出：300 列默认 fanout=50 → 截断
    p50 = _call(sem_app["app"], token, "get_entity", {
        "key": "table:ods.big_table", "expand": ["has_column>"]})
    assert len(p50["nodes"]) == 50 and p50["truncated"] is True
    p200 = _call(sem_app["app"], token, "get_entity", {
        "key": "table:ods.big_table", "expand": ["has_column>"], "fanout_limit": 200})
    assert len(p200["nodes"]) == 200 and p200["truncated"] is True
    # 节点上限默认 200：模板 → 2 表 → 303 列，节点封顶且 truncated
    pnodes = _call(sem_app["app"], token, "get_entity", {
        "key": "template:TPL_VAT_INPUT",
        "expand": ["backed_by>", "has_column>"], "depth": 2, "fanout_limit": 200})
    assert len(pnodes["nodes"]) <= 200 and pnodes["truncated"] is True


# ---- search_entities（TC-SEM-05 前半——排序链 alias 精确 > 前缀 > label 模糊） ----


def test_search_entities_ranking_and_limits(sem_app) -> None:
    token = sem_app["jwt"]("u_full", org=ORG)
    payload = _call(sem_app["app"], token, "search_entities",
                    {"q": "进项模板", "top_k": 10})
    ents = payload["entities"]
    assert ents, "别名精确命中必须在场"
    assert ents[0]["key"] == "TPL_VAT_INPUT" and ents[0]["via"] == "alias-exact"
    assert ents[0]["score"] == 1.0
    vias = [e["via"] for e in ents]
    # 排序链：所有 alias 前缀命中先于 FTS 模糊命中（C.3/m2s-3：name LIKE 层
    # 升级为 FTS——via 'name' → 'fts'，三层序不变）
    assert "alias-prefix" in vias and "fts" in vias
    assert vias.index("alias-prefix") < vias.index("fts")
    assert {e["type"] for e in ents} <= {"template", "concept", "table"}
    # brief/score/via 结构键齐
    assert all({"id", "type", "key", "name", "score", "via"} <= set(e) for e in ents)

    # 前缀单独命中：q=进项抵扣（concept 别名）
    p2 = _call(sem_app["app"], token, "search_entities", {"q": "进项抵扣"})
    assert p2["entities"][0]["key"] == "vat.input_credit"

    # types 过滤收窄
    p3 = _call(sem_app["app"], token, "search_entities",
               {"q": "进项", "types": ["concept"]})
    assert p3["entities"] and all(e["type"] == "concept" for e in p3["entities"])

    # 参数上限：top_k ≤50、q ≤200、types 合法值（400——防 LLM 塞超限）
    assert "400" in str(_call_err(sem_app["app"], token, "search_entities",
                                  {"q": "x", "top_k": 51}))
    assert "400" in str(_call_err(sem_app["app"], token, "search_entities",
                                  {"q": "字" * 201}))
    assert "400" in str(_call_err(sem_app["app"], token, "search_entities",
                                  {"q": "x", "types": ["nope"]}))


def test_search_entities_restricted_and_org_isolation(sem_app) -> None:
    token = sem_app["jwt"]("u_full", org=ORG)
    # restricted 实体：search 无命中、get_entity 404（fail-closed——持权路径 M2-S3）
    payload = _call(sem_app["app"], token, "search_entities",
                    {"q": "内部税收筹划方案"})
    assert payload["entities"] == []
    err = _call_err(sem_app["app"], token, "get_entity",
                    {"key": "concept:tax.scheme.internal"})
    assert "404" in str(err)
    # T-S7 工具面：org:gl 调用方对 org:tax 实体 get_entity 404、search 零命中
    gl = sem_app["jwt"]("u_gl", org=ORG_GL)
    err2 = _call_err(sem_app["app"], gl, "get_entity",
                     {"key": "template:TPL_VAT_INPUT"})
    assert "404" in str(err2)
    p3 = _call(sem_app["app"], gl, "search_entities", {"q": "进项模板"})
    assert p3["entities"] == []
    # 无成员关系 → semantic:read 拒绝（403）
    nomem = sem_app["jwt"]("u_nomem", org=ORG)
    err3 = _call_err(sem_app["app"], nomem, "search_entities", {"q": "进项"})
    assert "403" in str(err3)


# ---- describe_table（T-S11） ----


def test_t_s11_describe_table_pass_through_and_cache(sem_app) -> None:
    token = sem_app["jwt"]("u_full", org=ORG)
    payload = _call(sem_app["app"], token, "describe_table",
                    {"table": "ods.vat_input_invoice"})
    assert payload["degraded"] is False
    assert payload["table"] == "ods.vat_input_invoice"
    cols = {c["name"]: c for c in payload["columns"]}
    assert cols["tax_amt"]["type"] == "DECIMAL" and cols["tax_amt"]["comment"] == "税额"
    # 5 分钟内重复调用命中缓存（透传客户端只被请求一次——T-S11④）
    _call(sem_app["app"], token, "describe_table", {"table": "ods.vat_input_invoice"})
    assert sem_app["describe"].calls == ["ods.vat_input_invoice"]
    # columns 过滤参数（design §6.3 input）
    p2 = _call(sem_app["app"], token, "describe_table",
               {"table": "ods.vat_input_invoice", "columns": ["tax_amt"]})
    assert [c["name"] for c in p2["columns"]] == ["tax_amt"]


def test_t_s11_describe_table_unregistered_403(sem_app) -> None:
    """未登记表名 → 403（防借此枚举整个数仓——T-S11②）。"""
    err = _call_err(sem_app["app"], sem_app["jwt"]("u_full", org=ORG), "describe_table",
                    {"table": "ods.not_registered"})
    assert "403" in str(err)


def test_t_s11_describe_table_degraded(sem_app, monkeypatch) -> None:
    """元数据系统超时 → 轻量节点信息 + degraded=true（T-S11③）。"""
    from knowledge_lattice.core.semantic.adapters import ADAPTER_FACTORIES

    exploding = FakeDescribeAdapter(explode=True)
    monkeypatch.setitem(ADAPTER_FACTORIES, "metadata", lambda org, cfg: exploding)
    payload = _call(sem_app["app"], sem_app["jwt"]("u_full", org=ORG), "describe_table",
                    {"table": "ods.vat_input_invoice"})
    assert payload["degraded"] is True
    assert payload["table"] == "ods.vat_input_invoice"
    col_names = {c["name"] for c in payload["columns"]}
    assert col_names == {"tax_amt", "inv_no", "seller"}  # 本地轻量列节点


def test_t_s11_describe_table_unexpected_500(sem_app, monkeypatch) -> None:
    """P1-1⑤/R2：core 意外异常不裸露内部栈——统一 ToolError 500（透传/构造
    失败已在 core 降级，此处仅 MCP 层兜底映射的契约锁定）。"""
    from knowledge_lattice.mcp import server as mcp_server

    def boom(*a, **kw):
        raise RuntimeError("unexpected core bug")

    monkeypatch.setattr(mcp_server, "describe_table", boom)
    err = _call_err(sem_app["app"], sem_app["jwt"]("u_full", org=ORG),
                    "describe_table", {"table": "ods.vat_input_invoice"})
    assert "500" in str(err) and "unexpected core bug" not in str(err)


# ---- P3-6/R2：get_entity 非 active 实体 404（与 describe_table 口径对齐） ----


def test_p3_6_get_entity_non_active_404(sem_app) -> None:
    conn = sem_app["conn"]
    conn.execute(
        "UPDATE sem_entities SET status = 'missing'"
        " WHERE org_id = ? AND key = 'TPL_VAT_INPUT'", (ORG,))
    conn.commit()
    err = _call_err(sem_app["app"], sem_app["jwt"]("u_full", org=ORG),
                    "get_entity", {"key": "template:TPL_VAT_INPUT"})
    assert "404" in str(err)
