"""B 组 deepagents 集成端到端【集成｜M1-3】。

运行时以 fastmcp Client（**等价 MCP 客户端**——deepagents/langchain-mcp-adapters
同协议栈；M0b 实验③依赖互斥发现：实验客户端独立 env，故本仓不引 deepagents 依赖）
跑通**三步凭证式上传一次**（design §6.3 时序）：

  ① 运行时（非 LLM）持开发 JWT（act=服务身份——委托 token 开发形态）POST /api/uploads
  ② PUT 字节到 upload_url
  ③ MCP `upload(upload_id, ...)` 消费 → 摄取完成 → 文档可搜（pending→active 全链）

版本制联动（B-2）：agent 上传的文档同样受 pending 409、PATCH 维度 409（同一
code path 不旁路）；覆盖上传 v2 走 lexical→full 单事务切换（D20）、切换后 FTS
无旧版本命中（T9 口径）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from knowledge_lattice.adapters.embedder import EmbeddingGate
from knowledge_lattice.config import Settings

V1_HTML = (
    "<html><body><h1>阿尔法版出口退税申报指南</h1>"
    "<p>生产企业出口自产货物适用免抵退税办法，阿尔法版本第一期内容。</p></body></html>"
).encode()
V2_HTML = (
    "<html><body><h1>贝塔版出口退税申报指南</h1>"
    "<p>修订版适用免抵退税办法，贝塔版本第二期补充了备案单证要求。</p></body></html>"
).encode()


class BlockingEmbedder:
    """embed 阻塞在 Event 上的可控 Embedder（lexical→full 窗口确定性造数——D20）。"""

    def __init__(self, dim: int = 2560) -> None:
        from fake_providers import FakeEmbedder

        self._inner = FakeEmbedder(dim=dim)
        self.gate = threading.Event()

    @property
    def model_label(self) -> str:
        return self._inner.model_label

    def embed(self, texts):
        self.gate.wait(timeout=15)  # 窗口保持：index_fts 已提交、embed 暂停
        return self._inner.embed(texts)


def _mcp_client(app, token: str) -> Client:
    def factory(**kw):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)

    return Client(
        StreamableHttpTransport(
            url="http://testserver/mcp",
            headers={"Authorization": f"Bearer {token}"},
            httpx_client_factory=factory,
        )
    )


def _await_doc_status(conn, doc_id: str, *, field: str, value: object, timeout_s: float = 15.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        row = conn.execute(
            f"SELECT {field} FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        if row is not None and row[0] == value:
            return
        time.sleep(0.05)
    raise AssertionError(f"doc {doc_id} {field} 未到 {value}")


@pytest.fixture()
def agent_env(tmp_path):
    """自足栈：create_app + BlockingEmbedder + org:tax/ds:vat_lib/region 维度造数。"""
    from fastapi.testclient import TestClient

    from knowledge_lattice.app import create_app
    from knowledge_lattice.store.sqlite import connect

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=2560, probe_interval_s=0,
        worker_mode="inline",
    )
    embedder = BlockingEmbedder(dim=2560)
    app = create_app(
        settings, embedder=embedder, gate=EmbeddingGate(), run_startup_probe=False
    )

    conn = connect(settings.db_path)
    conn.execute("INSERT OR IGNORE INTO orgs(id, name) VALUES('org:tax', 't')")
    conn.execute(
        "INSERT OR IGNORE INTO datasets(id, org_id, name) VALUES('ds:vat_lib', 'org:tax', 'v')"
    )
    conn.execute("INSERT OR IGNORE INTO users(id, username) VALUES('u_full', 'u_full')")
    conn.execute(
        "INSERT OR IGNORE INTO user_org_memberships(user_id, org_id)"
        " VALUES('u_full', 'org:tax')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO dimensions(id, org_id, key, name, grant_source)"
        " VALUES('dim:org:tax:region', 'org:tax', 'region', 'region', 'local')"
    )
    for value in ("CN", "OS"):
        conn.execute(
            "INSERT OR IGNORE INTO dimension_values(id, dimension_id, value, label)"
            " VALUES(?, 'dim:org:tax:region', ?, ?)",
            (f"val:dim:org:tax:region:{value}", value, value),
        )
        conn.execute(
            "INSERT OR IGNORE INTO user_dimension_grants(user_id, dimension_id, value_id, source)"
            " VALUES('u_full', 'dim:org:tax:region', ?, 'local')",
            (f"val:dim:org:tax:region:{value}",),
        )
    conn.commit()

    from knowledge_lattice.domain.auth import issue_dev_jwt

    with TestClient(app) as client:
        yield {
            "app": app,
            "client": client,
            "conn": conn,
            "embedder": embedder,
            "token": issue_dev_jwt(
                settings, user_id="u_full", org="org:tax", act="agent-copilot"
            ),
        }
    conn.close()


def _runtime_issue_and_put(env, payload: bytes) -> str:
    """agent 运行时侧①②：签发 + PUT（非 LLM——直接 HTTP 调用）。"""
    resp = env["client"].post(
        "/api/uploads",
        json={
            "filename": "guide.html", "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(), "content_type": "text/html",
        },
        headers={"Authorization": f"Bearer {env['token']}"},
    )
    assert resp.status_code == 201, resp.text
    upload_id = resp.json()["upload_id"]
    put = env["client"].put(
        f"/api/uploads/{upload_id}", content=payload,
        headers={"Authorization": f"Bearer {env['token']}"},
    )
    assert put.status_code == 200, put.text
    return upload_id


def test_deepagents_end_to_end_upload_once(agent_env) -> None:
    """MCP 客户端 → 签发 → PUT → upload 消费 → 摄取完成 → 文档可搜
    （pending→active 全链 + 覆盖上传 v2 版本制联动）。"""
    env = agent_env

    # ---- 首传 v1：① 签发 ② PUT ③ LLM 调 upload ----
    upload_1 = _runtime_issue_and_put(env, V1_HTML)

    async def flow():
        async with _mcp_client(env["app"], env["token"]) as client:
            result = await client.call_tool(
                "upload",
                {
                    "upload_id": upload_1,
                    "dataset": "ds:vat_lib",
                    "dimensions": {"region": ["CN"]},
                    "title": "出口退税申报指南",
                },
            )
            return json.loads(result.content[0].text)

    payload = asyncio.run(flow())
    doc_id = payload["doc_id"]
    assert payload["status"] == "queued" and payload["pending_version"] == 1

    # pending→active 全链（D20 首传）：index_fts 先行——embed 阻塞窗口内 BM25 已可搜
    _await_doc_status(env["conn"], doc_id, field="active_status", value="searchable_lexical")

    async def search(q: str):
        async with _mcp_client(env["app"], env["token"]) as client:
            result = await client.call_tool("search", {"query": q, "top_k": 5})
            return json.loads(result.content[0].text)

    lexical = asyncio.run(search("阿尔法 免抵退税"))
    assert lexical["results"], "lexical 窗口（embed 未完成）BM25 应可搜"
    assert lexical["notice"]["vector_pending"] is True  # 向量路未就绪（v1.4 notice 口径）

    # ---- embed 放行 → searchable_full（active_version=1）----
    env["embedder"].gate.set()
    _await_doc_status(env["conn"], doc_id, field="active_status", value="searchable_full")
    full = asyncio.run(search("阿尔法 免抵退税"))
    assert full["results"] and full["notice"]["vector_pending"] is False
    assert full["results"][0]["source"] == "agent:agent-copilot"  # agent 代传标来源

    # ---- 覆盖上传 v2（版本制联动——同一 code path）----
    env["embedder"].gate.clear()  # v2 embed 阻塞 → pending v2 窗口
    upload_2 = _runtime_issue_and_put(env, V2_HTML)

    async def overwrite():
        async with _mcp_client(env["app"], env["token"]) as client:
            result = await client.call_tool(
                "upload",
                {
                    "upload_id": upload_2,
                    "dataset": "ds:vat_lib",
                    "dimensions": {"region": ["CN"]},
                    "doc_id": doc_id,
                    "title": "出口退税申报指南 v2",
                },
            )
            return json.loads(result.content[0].text)

    v2 = asyncio.run(overwrite())
    assert v2["pending_version"] == 2
    _await_doc_status(env["conn"], doc_id, field="pending_status", value="searchable_lexical")

    # pending 期间：同文档再上传 → 409（T7 MCP 面）；PATCH 维度 → 409（同 code path）
    upload_3 = _runtime_issue_and_put(env, V2_HTML)

    async def conflict():
        async with _mcp_client(env["app"], env["token"]) as client:
            await client.call_tool(
                "upload",
                {
                    "upload_id": upload_3, "dataset": "ds:vat_lib",
                    "dimensions": {"region": ["CN"]}, "doc_id": doc_id,
                },
            )

    with pytest.raises(ToolError, match="409"):
        asyncio.run(conflict())

    patch = env["client"].patch(
        f"/api/orgs/org:tax/documents/{doc_id}/dimensions",
        json={"dims": {"region": ["OS"]}},
        headers={"Authorization": f"Bearer {env['token']}"},
    )
    assert patch.status_code == 409  # pending 期间禁改维度（P0-2.1——同 code path）

    # 检索窗口期：仍只见 v1（lexical 时点不切换——D20）
    during = asyncio.run(search("阿尔法"))
    assert during["results"]
    v1_only = asyncio.run(search("贝塔 备案单证"))
    assert v1_only["results"] == []

    # ---- v2 完成 → 单事务切换（active_version=2）----
    env["embedder"].gate.set()
    _await_doc_status(env["conn"], doc_id, field="active_version", value=2)
    row = env["conn"].execute(
        "SELECT active_version, active_status, pending_version FROM documents WHERE id = ?",
        (doc_id,),
    ).fetchone()
    assert row[0] == 2 and row[1] == "searchable_full" and row[2] is None

    after_v2 = asyncio.run(search("贝塔 备案单证"))
    assert after_v2["results"], "切换后 v2 内容可搜"
    # T9 口径（FTS 层面无旧版本命中）：五列 MATCH 零命中 + 检索结果不含旧版本内容
    # （向量路最近邻与文本无关——单块语料必返回，故结果集断言只限内容归属）
    old_gone = asyncio.run(search("阿尔法"))
    assert all("阿尔法" not in (r.get("snippet") or "") for r in old_gone["results"]), (
        "旧版本内容泄漏到检索面（T9）"
    )
    from knowledge_lattice.store.sqlite.fts import escape_token

    assert env["conn"].execute(
        "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
        (escape_token("阿尔法"),),
    ).fetchone()[0] == 0
    old_rows = env["conn"].execute(
        "SELECT tombstone, title_seg, content_seg FROM chunks"
        " WHERE doc_id = ? AND version = 1",
        (doc_id,),
    ).fetchall()
    assert old_rows and all(r[0] == 1 and r[1] == "" and r[2] == "" for r in old_rows)

    # ---- 凭证与文档/任务关联可追溯（M1-3 A6）----
    rows = env["conn"].execute(
        "SELECT id, status, doc_id, task_id FROM uploads ORDER BY created_at"
    ).fetchall()
    assert len(rows) == 3
    consumed = [r for r in rows if r[2] == doc_id]
    assert len(consumed) == 2 and all(r[1] == "consumed" and r[3] for r in consumed)
    # upload_3 因 409 未消费——凭证保留 uploaded（失败不置、可重传）
    pending_cred = [r for r in rows if r[2] is None]
    assert len(pending_cred) == 1 and pending_cred[0][1] == "uploaded"
