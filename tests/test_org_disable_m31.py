"""m3-1 B 组（issue #14）：组织停用载体 + 停用语义——双方言迁移 + PATCH
/api/orgs/{org}（sysadmin 专属）+ fail-closed 访问面 403 + 任务语义。

- orgs.status 列（active/disabled，默认 active）——迁移 0011 双方言；
- PATCH /api/orgs/{org} {status}：**sysadmin 专属**（org_admin 不能停自己的
  组织——防误操作锁死；与 POST /api/orgs 同门控）；org.disabled/org.enabled
  审计同事务入 outbox（幂等零新审计）；
- 停用语义（fail-closed，已裁定）：停用组织所有 /api/orgs/{org}/... 端点一律
  403（token 仍有效但组织上下文拒绝）；MCP 会话同 403；webhook 拒绝；**进行中
  任务让跑完**（不中断——执行体不检查组织状态），新任务投递拒绝（入口拦截
  承载）；恢复 = PATCH status=active（幂等）；
- GET /api/orgs 响应补 status 列（sysadmin 全量 / 普通用户 membership；停用
  组织仍列出、成员关系保留——仅访问面 403）。
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_mod
import json

import pytest

from conftest import ORG, ORG_GL

pytestmark = pytest.mark.usefixtures("rest_env")


def _hdr(env, uid: str) -> dict:
    return {"Authorization": f"Bearer {env['tokens'][uid]}"}


def _outbox_types(env, prefix: str) -> list[dict]:
    order = "rowid" if env["db"].name == "sqlite" else "created_at"
    rows = env["db"].execute(
        "SELECT event_type, payload_json FROM audit_outbox"
        f" WHERE event_type LIKE ? ORDER BY {order}",
        (f"{prefix}%",),
    ).fetchall()
    return [{"event_type": r[0], "payload": json.loads(r[1])} for r in rows]


def _disable(env, org: str, status: str = "disabled"):
    return env["client"].patch(
        f"/api/orgs/{org}", headers=_hdr(env, "sysadmin"),
        json={"status": status},
    )


# ============ B1：迁移——orgs.status 列默认 active ============


def test_b1_org_status_column_default_active(rest_env) -> None:
    """0011 迁移双方言：orgs.status 列在场、默认 'active'（既有行回填 active）。"""
    rows = rest_env["db"].execute(
        "SELECT id, status FROM orgs ORDER BY id"
    ).fetchall()
    assert rows, "矩阵造数应有两组织"
    assert all(r[1] == "active" for r in rows), rows


# ============ B2：PATCH /api/orgs/{org} 门控 + 审计 ============


def test_b2_patch_org_status_gate_and_audit(rest_env) -> None:
    """PATCH orgs：sysadmin 200（status 载体）；org_admin/member 403（sysadmin
    专属——org_admin 不能停自己的组织）；不存在 404；非法 status 400；
    org.disabled 审计同事务。"""
    client, env = rest_env["client"], rest_env
    # 门控：org_admin 403 / member 403 / sysadmin 200
    assert client.patch(
        f"/api/orgs/{ORG_GL}", headers=_hdr(env, "u_gl"),
        json={"status": "disabled"},
    ).status_code == 403
    # u_gl 是 org:gl 的 org_admin——仍 403（sysadmin 专属）
    assert client.patch(
        f"/api/orgs/{ORG}", headers=_hdr(env, "u_full"),
        json={"status": "disabled"},
    ).status_code == 403
    r = _disable(env, ORG_GL)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "disabled"
    # 不存在 404 / 非法 status 400 / 缺 status 422（pydantic 必填校验）
    assert client.patch(
        "/api/orgs/org:none", headers=_hdr(env, "sysadmin"),
        json={"status": "disabled"},
    ).status_code == 404
    assert client.patch(
        f"/api/orgs/{ORG}", headers=_hdr(env, "sysadmin"),
        json={"status": "paused"},
    ).status_code == 400
    assert client.patch(
        f"/api/orgs/{ORG}", headers=_hdr(env, "sysadmin"), json={}
    ).status_code == 422
    # 审计 org.disabled（payload 带 org_id + actor）
    events = _outbox_types(env, "org.disabled")
    assert events and events[-1]["payload"].get("org_id") == ORG_GL


# ============ B3：停用后访问面全端点 403（fail-closed） ============


def test_b3_disabled_org_all_endpoints_403(rest_env) -> None:
    """停用后该组织全部 /api/orgs/{org}/... 端点 403（token 仍有效——认证层
    通过、组织上下文拒绝）；无 org 路径端点（/api/search、/api/uploads）以
    X-Org-Id 解析到停用组织同 403；GET /api/orgs 不受影响（仍列出）。"""
    client, env = rest_env["client"], rest_env
    assert _disable(env, ORG_GL).status_code == 200
    gl = _hdr(env, "u_gl")  # u_gl token 仍有效（认证层不受组织停用影响）

    scan = [
        ("get", f"/api/orgs/{ORG_GL}/dimensions"),
        ("get", f"/api/orgs/{ORG_GL}/datasets"),
        ("get", f"/api/orgs/{ORG_GL}/documents"),
        ("get", f"/api/orgs/{ORG_GL}/members"),
        ("get", f"/api/orgs/{ORG_GL}/tasks"),
        ("get", f"/api/orgs/{ORG_GL}/audit"),
        ("get", f"/api/orgs/{ORG_GL}/stats"),
        ("get", f"/api/orgs/{ORG_GL}/embedding-coverage"),
        ("post", f"/api/orgs/{ORG_GL}/members"),
        ("post", f"/api/orgs/{ORG_GL}/datasets"),
        ("post", f"/api/orgs/{ORG_GL}/dimensions"),
        # 跨面照常（未停用组织不受影响——隔离对照在 B5 恢复后）
    ]
    for method, path in scan:
        kwargs: dict = {}
        if method == "post":
            if path.endswith("/members"):
                kwargs["json"] = {"user_id": "u_full", "role": "member"}
            elif path.endswith("/datasets"):
                kwargs["json"] = {"key": "ds:x"}
            elif path.endswith("/dimensions"):
                kwargs["json"] = {"key": "d", "label": "x"}
        r = getattr(client, method)(path, headers=gl, **kwargs)
        assert r.status_code == 403, (
            f"停用组织端点须 403：{method.upper()} {path} → {r.status_code}"
            f"（{r.text[:100]}）"
        )

    # 无 org 路径：/api/search、/api/uploads 以 X-Org-Id 解析停用组织 → 403
    hdr_org = {**gl, "X-Org-Id": ORG_GL}
    assert client.post(
        "/api/search", headers=hdr_org, json={"query": "x"},
    ).status_code == 403
    assert client.post(
        "/api/uploads", headers=hdr_org,
        json={"filename": "a.txt", "size": 1, "sha256": "0" * 64,
              "content_type": "text/plain"},
    ).status_code == 403

    # GET /api/orgs 列表不受影响：停用组织仍列出（带 status——u_gl 为
    # membership 面，只含本人组织；org:tax 不在其列属预期）
    r = client.get("/api/orgs", headers=gl)
    assert r.status_code == 200
    by_id = {o["org_id"]: o for o in r.json()["orgs"]}
    assert by_id[ORG_GL]["status"] == "disabled"
    assert set(by_id) == {ORG_GL}


def test_b3b_mcp_session_disabled_org_403(rest_env) -> None:
    """MCP 会话同 403：停用组织的成员调 docs/semantic 工具 → ToolError 403
    （组织上下文拒绝——与 REST 面同口径）。"""
    client, env = rest_env["client"], rest_env
    assert _disable(env, ORG_GL).status_code == 200

    import httpx
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    def factory(**kw):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=env["app"]), **kw)

    mcp_client = Client(
        StreamableHttpTransport(
            url="http://testserver/mcp",
            headers={
                "Authorization": f"Bearer {env['tokens']['u_gl']}",
                "X-Org-Id": ORG_GL,
            },
            httpx_client_factory=factory,
        )
    )
    from fastmcp.exceptions import ToolError

    async def _call():
        async with mcp_client:
            return await mcp_client.call_tool(
                "search", {"query": "增值税", "top_k": 1})

    with pytest.raises(ToolError) as exc_info:
        asyncio.run(_call())
    assert "403" in str(exc_info.value), (
        f"MCP 会话对停用组织须 403（got {exc_info.value}）"
    )


def test_b3c_webhook_disabled_org_rejected(rest_env, tmp_path) -> None:
    """webhook 拒绝：签名有效但组织停用 → 403（验签先行的顺序保持——
    无签名仍 401）。"""
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from fake_providers import FakeEmbedder

    secret = "whsec-test"
    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        probe_interval_s=0, worker_mode="inline",
        semantic_sources_json=json.dumps(
            {ORG_GL: {"yaml": {"webhook_secret": secret}}}),
    )
    kwargs = dict(
        embedder=FakeEmbedder(dim=8), gate=EmbeddingGate(),
        run_startup_probe=False,
    )
    if rest_env["db"].name == "pg":  # pg 臂注入同 schema backend（az_env 同款分支）
        app = create_app(settings, backend=rest_env["backend"], **kwargs)
    else:  # sqlite 臂默认工厂——同 tmp_path db 文件
        app = create_app(settings, **kwargs)
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        body = b'{"commit": "abc"}'
        sig = "sha256=" + hmac_mod.new(
            secret.encode(), body, hashlib.sha256).hexdigest()
        # 停用 org:gl（经新 PATCH 端点——sysadmin token）
        from knowledge_lattice.domain.auth import hash_token

        rest_env["db"].execute(  # 造数：org:gl + sysadmin token（独立 app 同库）
            "UPDATE users SET token_hash = ? WHERE id = 'sysadmin'",
            (hash_token("wh-sysadmin"),),
        )
        rest_env["db"].commit()
        r = client.patch(
            f"/api/orgs/{ORG_GL}",
            headers={"Authorization": "Bearer wh-sysadmin"},
            json={"status": "disabled"},
        )
        assert r.status_code == 200, r.text
        # 无签名 → 401（验签先行，与停用无关）
        r1 = client.post(
            f"/api/orgs/{ORG_GL}/semantic/yaml/webhook", content=body)
        assert r1.status_code == 401
        # 有效签名 + 停用组织 → 403
        r2 = client.post(
            f"/api/orgs/{ORG_GL}/semantic/yaml/webhook", content=body,
            headers={"X-Lattice-Signature": sig})
        assert r2.status_code == 403, (
            f"停用组织 webhook 须 403（got {r2.status_code}）"
        )


# ============ B4：进行中任务让跑完（不中断） + 新任务投递拒绝 ============


def test_b4_inflight_task_completes_and_new_submission_denied(rest_env) -> None:
    """进行中任务让跑完：停用后既有 pending 任务被 worker 正常认领执行
    （到达终态——执行体不检查组织状态；inline 兜底循环即时认领 reindex
    组，异步消化→轮询等待终态）；新任务投递拒绝（上传入口 403 承载——
    无新任务行产生）。"""
    import time

    client, env = rest_env["client"], rest_env
    # 造一个 pending reindex 任务（对既有文档 d_cn）
    backend = env["backend"]
    task_id = backend.create_task(
        "d_cn", task_type="reindex", target_version=1,
        payload=json.dumps({"org": ORG}),
    )
    assert _disable(env, ORG).status_code == 200
    # 停用后 kick（REST 壳 inline worker）——任务照常执行（执行体不检查
    # 组织状态；重试预算内三轮消化后到终态）
    worker = env["app"].state.worker
    deadline = time.monotonic() + 30.0
    while True:
        worker.kick()
        task = backend.get_task(task_id)
        if task is not None and task["status"] in ("done", "failed"):
            break
        assert time.monotonic() < deadline, (
            f"进行中任务须让跑完（停在 {task and task['status']}——执行体"
            "不得因组织停用而滞留）"
        )
        time.sleep(0.2)
    # 新任务投递拒绝：上传入口 403（org_scoped 停用拦截）
    r = client.post(
        f"/api/orgs/{ORG}/documents", headers=_hdr(env, "u_full"),
        files={"file": ("a.html", b"<html><body>x</body></html>",
                        "text/html")},
        data={"dataset": "ds:vat_lib", "dims": "{}"},
    )
    assert r.status_code == 403, f"停用组织新上传须 403（got {r.status_code}）"


# ============ B5：恢复（幂等） + 审计 ============


def test_b5_reenable_idempotent_and_audit(rest_env) -> None:
    """恢复 = PATCH status=active 幂等：重复同值 200 零新审计；状态翻转各
    一次审计（org.enabled 恰 1 条）；恢复后端点 200。"""
    client, env = rest_env["client"], rest_env
    assert _disable(env, ORG_GL).status_code == 200
    # 重复 disabled（同值幂等）→ 200 零新审计
    assert _disable(env, ORG_GL).status_code == 200
    assert len(_outbox_types(env, "org.disabled")) == 1
    # 恢复 → 200 + org.enabled 审计 1 条
    r = client.patch(
        f"/api/orgs/{ORG_GL}", headers=_hdr(env, "sysadmin"),
        json={"status": "active"},
    )
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert client.patch(
        f"/api/orgs/{ORG_GL}", headers=_hdr(env, "sysadmin"),
        json={"status": "active"},
    ).status_code == 200  # 幂等
    enabled_events = _outbox_types(env, "org.enabled")
    assert len(enabled_events) == 1
    # 恢复后端点 200（访问面回通）
    r2 = client.get(f"/api/orgs/{ORG_GL}/dimensions", headers=_hdr(env, "u_gl"))
    assert r2.status_code == 200, r2.text


# ============ B6：GET /api/orgs status 列（双面） ============


def test_b6_orgs_list_status_column(rest_env) -> None:
    """GET /api/orgs：sysadmin 全量行带 status；普通用户 membership 行带
    status；停用组织仍列出、成员关系保留。"""
    client, env = rest_env["client"], rest_env
    assert _disable(env, ORG_GL).status_code == 200
    # sysadmin 面
    rows = client.get("/api/orgs", headers=_hdr(env, "sysadmin")).json()["orgs"]
    by_id = {o["org_id"]: o for o in rows}
    assert by_id[ORG_GL]["status"] == "disabled"
    assert by_id[ORG]["status"] == "active"
    # 普通用户面（u_multi 是 org:tax + org:gl 双成员——停用组织仍列出）
    rows2 = client.get("/api/orgs", headers=_hdr(env, "u_multi")).json()["orgs"]
    by_id2 = {o["org_id"]: o for o in rows2}
    assert ORG_GL in by_id2 and by_id2[ORG_GL]["status"] == "disabled"
    assert set(by_id2) == {ORG, ORG_GL}, by_id2  # membership 面（成员关系保留）
