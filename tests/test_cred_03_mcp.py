"""TC-CRED-03 MCP 协议面 + TC-CRED-04 file_ref 防线【单测｜M1】（MCP 面）。

- MCP `upload` 工具契约（§6.1）：inputSchema 只收不透明 upload_id + dataset/
  dimensions/doc_id?/title?；output {doc_id, task_id, status: queued, pending_version}；
- TC-CRED-04：`file_ref` 只收不透明 upload_id——路径穿越（../../）、绝对路径、
  file:///http:// URL、白名单根外引用一律拒绝（SSRF/任意读取/穿越三防线，NFR-6）；
- T7 MCP 面（m1-2 Tester 观察④顺延项）：pending 期间同文档再上传 → 409（ToolError）。
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

PAYLOAD = (
    "<html><body><h1>土地增值税清算实务</h1>"
    "<p>纳税人转让旧房及建筑物，可凭购房发票差额计征土地增值税。</p></body></html>"
).encode()
SHA_HEX = hashlib.sha256(PAYLOAD).hexdigest()


def _client(app, headers: dict) -> Client:
    def factory(**kw):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)

    return Client(
        StreamableHttpTransport(
            url="http://testserver/mcp", headers=headers, httpx_client_factory=factory
        )
    )


def _issue_and_put(env, *, act="agent-copilot", user="u_full", payload=PAYLOAD) -> str:
    token = env["jwt"](user, org="org:tax", act=act)
    client = env["client"]
    resp = client.post(
        "/api/uploads",
        json={
            "filename": "doc.html", "size": len(payload), "sha256": SHA_HEX,
            "content_type": "text/html",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    upload_id = resp.json()["upload_id"]
    put = client.put(
        f"/api/uploads/{upload_id}", content=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert put.status_code == 200, put.text
    return upload_id


def _call_upload(env, token: str, upload_id: str, *,
                  dims: dict[str, list[str]] | None = None,
                  doc_id: str | None = None):
    async def flow():
        async with _client(env["app"], {"Authorization": f"Bearer {token}"}) as client:
            result = await client.call_tool(
                "upload",
                {
                    "upload_id": upload_id,
                    "dataset": "ds:vat_lib",
                    "dimensions": dims or {"region": ["CN"]},
                    **({"doc_id": doc_id} if doc_id else {}),
                },
            )
            return json.loads(result.content[0].text)

    return asyncio.run(flow())


def _await_task_done(env, task_id: str, timeout_s: float = 10.0) -> None:
    """MCP upload 工具投递的摄取线程完成轮询（进程内执行器——M0a 口径）。"""
    backend = env["app"].state.service.backend
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        task = backend.get_task(task_id)
        if task is not None and task["status"] in ("done", "failed"):
            assert task["status"] == "done", task
            return
        time.sleep(0.02)
    raise AssertionError(f"task {task_id} not done within {timeout_s}s")


# ============ MCP upload 工具契约 ============


def test_mcp_upload_happy_path_returns_contract_fields(app_env) -> None:
    """同 sub+org+服务身份 → 进摄取；output 契约四字段（§6.1）。"""
    env = app_env
    upload_id = _issue_and_put(env)
    token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")

    payload = _call_upload(env, token, upload_id)

    assert payload["doc_id"].startswith("doc_")
    assert payload["task_id"].startswith("tsk_")
    assert payload["status"] == "queued"
    assert payload["pending_version"] == 1
    _await_task_done(env, payload["task_id"])
    doc = env["app"].state.service.backend.get_document(payload["doc_id"])
    assert doc["active_version"] == 1 and doc["active_status"] == "searchable_full"
    # 凭证置已用并绑定追溯（摄取成功入队——v1.4 口径）
    row = env["conn"].execute(
        "SELECT status, doc_id, task_id FROM uploads WHERE id = ?", (upload_id,)
    ).fetchone()
    assert row == ("consumed", payload["doc_id"], payload["task_id"])


def test_mcp_upload_binding_mismatch_403(app_env) -> None:
    """换服务身份消费（MCP 面）→ ToolError 403 binding_mismatch（T11）。"""
    env = app_env
    upload_id = _issue_and_put(env, act="agent-copilot")
    rogue = env["jwt"]("u_full", org="org:tax", act="agent-rogue")

    with pytest.raises(ToolError) as exc_info:
        _call_upload(env, rogue, upload_id)
    assert "403" in str(exc_info.value) and "binding_mismatch" in str(exc_info.value)


def test_mcp_upload_consumed_409(app_env) -> None:
    """已用凭证再消费 → ToolError 409 upload_consumed。"""
    env = app_env
    upload_id = _issue_and_put(env)
    token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")
    first = _call_upload(env, token, upload_id)
    _await_task_done(env, first["task_id"])

    with pytest.raises(ToolError) as exc_info:
        _call_upload(env, token, upload_id)
    assert "409" in str(exc_info.value) and "upload_consumed" in str(exc_info.value)


def test_mcp_upload_not_ready_400(app_env) -> None:
    """乱序（未 PUT 先 upload）→ ToolError 400 upload_not_ready。"""
    env = app_env
    token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")
    resp = env["client"].post(
        "/api/uploads",
        json={
            "filename": "doc.html", "size": len(PAYLOAD), "sha256": SHA_HEX,
            "content_type": "text/html",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    upload_id = resp.json()["upload_id"]

    with pytest.raises(ToolError) as exc_info:
        _call_upload(env, token, upload_id)
    assert "400" in str(exc_info.value) and "upload_not_ready" in str(exc_info.value)


def test_mcp_upload_dims_acl_same_code_path(app_env) -> None:
    """B 组：agent 上传同样受维度写校验（同一 code path 不旁路）——u_cn 无 OS 授权
    → ToolError 403（helper 同款错误语义）。"""
    env = app_env
    token_cn = env["jwt"]("u_cn", org="org:tax", act="agent-copilot")
    resp = env["client"].post(
        "/api/uploads",
        json={
            "filename": "doc.html", "size": len(PAYLOAD), "sha256": SHA_HEX,
            "content_type": "text/html",
        },
        headers={"Authorization": f"Bearer {token_cn}"},
    )
    upload_id = resp.json()["upload_id"]
    put = env["client"].put(
        f"/api/uploads/{upload_id}", content=PAYLOAD,
        headers={"Authorization": f"Bearer {token_cn}"},
    )
    assert put.status_code == 200

    with pytest.raises(ToolError) as exc_info:
        _call_upload(env, token_cn, upload_id, dims={"region": ["OS"]})
    assert "403" in str(exc_info.value) and "actor grants" in str(exc_info.value)


def test_mcp_upload_pending_409_t7_face(app_env) -> None:
    """T7 MCP 面：pending 期间同文档再上传 → 409；且第二张凭证不置已用。"""
    env = app_env
    service = env["app"].state.service
    release = threading.Event()

    def _blocked_run(task_id, **kw):  # 摄取线程暂停在入口——pending 窗口确定性保持
        release.wait(timeout=10)

    original = service.ingest.run_task
    service.ingest.run_task = _blocked_run  # type: ignore[assignment]
    try:
        token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")
        first = _call_upload(env, token, _issue_and_put(env))

        second_id = _issue_and_put(env)
        with pytest.raises(ToolError) as exc_info:
            _call_upload(env, token, second_id, doc_id=first["doc_id"])
        assert "409" in str(exc_info.value)
        row = env["conn"].execute(
            "SELECT status FROM uploads WHERE id = ?", (second_id,)
        ).fetchone()
        assert row[0] == "uploaded"  # 冲突不置已用（可重传）
    finally:
        service.ingest.run_task = original  # type: ignore[assignment]
        release.set()


# ============ TC-CRED-04 file_ref 防线 ============


@pytest.mark.parametrize(
    "bad_id",
    [
        "../../etc/passwd",                       # 路径穿越
        "/etc/passwd",                            # 绝对路径
        "file:///etc/passwd",                     # file:// URL
        "http://evil.example.com/f.bin",          # http URL（SSRF 面）
        "https://evil.example.com/f.bin",         # https URL
        "upl_../../escape",                       # 前缀合法但带穿越段
        "UPPERCASE_NOT_A_ULID",                   # 非法形态
        "",                                       # 空串
        "doc_xss0000000000000000000000",          # 他域 id 形态
    ],
)
def test_mcp_upload_fileref_only_opaque_ids(app_env, bad_id) -> None:
    """TC-CRED-04：非不透明 upload_id（穿越/绝对路径/URL/异形）一律 400 拒绝。"""
    env = app_env
    token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")

    with pytest.raises(ToolError) as exc_info:
        _call_upload(env, token, bad_id)
    assert "400" in str(exc_info.value) and "invalid_upload_id" in str(exc_info.value)


def test_object_ref_containment_defense(cred_env) -> None:
    """三防线纵深（NFR-6）：白名单根目录 + 前缀字符串拒绝——直插含 `..` 的
    object_key 凭证行（绕过签发面）→ 消费侧拒绝 invalid_object_ref。
    （realpath 分支的符号链接形态见 test_p3_3_object_ref_symlink_realpath_branch。）"""
    from knowledge_lattice.core.docs.credentials import ObjectRefError

    upload_id = _seed_uploaded_credential(cred_env)
    cred_env["db"].execute(
        "UPDATE uploads SET object_key = '../../escape.bin' WHERE id = ?", (upload_id,)
    )
    with pytest.raises(ObjectRefError) as exc_info:
        _consume_via_service(cred_env, upload_id)
    assert exc_info.value.code == "invalid_object_ref"


def _seed_uploaded_credential(cred_env) -> str:
    creds = cred_env["creds"]
    issued = creds.issue(
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        filename="doc.html", size=len(PAYLOAD), sha256=SHA_HEX, content_type="text/html",
    )
    creds.put_bytes(
        issued["upload_id"], org_id="org:tax", user_id="u_full",
        service_id="agent-copilot", chunks=[PAYLOAD],
    )
    return issued["upload_id"]


def _consume_via_service(cred_env, upload_id: str):
    creds, ingest = cred_env["creds"], cred_env["ingest"]
    return creds.consume(
        upload_id,
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        dataset_id="ds:vat_lib", dims={"region": ["CN"]},
        create_document=ingest.create_document,
    )


# ============ R2 修复：P1-1 MCP upload 逐请求成员关系校验（Committer R1） ============


def test_p1_1_mcp_upload_expired_membership_403(app_env) -> None:
    """P1-1（MCP 面）：凭证 TTL 内成员关系过期 → upload ToolError 403；凭证仍
    uploaded、无文档产生；恢复正常成员后同凭证消费成功。"""
    env = app_env
    upload_id = _issue_and_put(env)
    token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")

    env["conn"].execute(
        "UPDATE user_org_memberships SET expires_at = '2020-01-01 00:00:00'"
        " WHERE user_id = 'u_full' AND org_id = 'org:tax'"
    )
    env["conn"].commit()
    docs_before = env["conn"].execute("SELECT count(*) FROM documents").fetchone()[0]

    with pytest.raises(ToolError) as exc_info:
        _call_upload(env, token, upload_id)
    assert "403" in str(exc_info.value) and "membership" in str(exc_info.value)

    row = env["conn"].execute(
        "SELECT status, doc_id FROM uploads WHERE id = ?", (upload_id,)
    ).fetchone()
    assert row == ("uploaded", None)  # 未消费、未绑文档
    assert env["conn"].execute("SELECT count(*) FROM documents").fetchone()[0] == docs_before

    # 恢复正常成员（删过期行→重加——trg_membership_no_extend 拒 UPDATE 复活；
    # 删行级联清授权，补回 region CN/OS）→ 同凭证消费成功（回归绿）
    env["conn"].execute(
        "DELETE FROM user_org_memberships WHERE user_id = 'u_full' AND org_id = 'org:tax'"
    )
    env["conn"].execute(
        "INSERT INTO user_org_memberships(user_id, org_id) VALUES('u_full', 'org:tax')"
    )
    for value in ("CN", "OS"):
        env["conn"].execute(
            "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id, source)"
            " VALUES('u_full', 'dim:org:tax:region', ?, 'local')",
            (f"val:dim:org:tax:region:{value}",),
        )
    env["conn"].commit()
    payload = _call_upload(env, token, upload_id)
    assert payload["status"] == "queued"
    _await_task_done(env, payload["task_id"])
