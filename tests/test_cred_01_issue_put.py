"""TC-CRED-01 凭证签发与绑定 + TC-CRED-02 PUT 字节校验【单测｜M1】（REST 面）。

- TC-CRED-01：POST /api/uploads 声明 {filename,size,sha256,content_type} →
  {upload_id, upload_url, expires_at}；凭证记录绑定 sub+org+服务身份三要素
  （#33 P1-3；服务身份＝token act claim——开发 JWT 形态）。
- TC-CRED-02：PUT /api/uploads/{id}——① 超声明 size 413（不静默截断，附录 A-13）；
  ② sha256 不符 400；③ 失败 PUT 不计消费、修正重传放行、成功消费后任何 PUT 拒绝
  （「用掉」＝摄取成功入队——v1.4 与 T12 统一）；④ 过期 410；⑤ >200MB 全局上限 413
  （P3-13——独立于声明生效）。全部带明确错误码（body.code——T12 展开）。
- P3-5/P3-21：PUT 落盘流式进 staging、失败即 unlink（无孤儿 .part）；P3-10：
  expires_at 序列化统一 UTC ISO 8601（Z 后缀）。
"""

from __future__ import annotations

import hashlib
import re

from helpers import seed_user

PAYLOAD = (
    "<html><body><h1>消费税委托加工收回直接销售指引</h1>"
    "<p>委托方将收回的应税消费品直接销售的，不再缴纳消费税。</p></body></html>"
).encode()
SHA_HEX = hashlib.sha256(PAYLOAD).hexdigest()
ISO_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _issue(client, token, *, filename="doc.html", size=None, sha=None,
           content_type="text/html", org_header=None):
    body = {
        "filename": filename,
        "size": len(PAYLOAD) if size is None else size,
        "sha256": SHA_HEX if sha is None else sha,
        "content_type": content_type,
    }
    headers = {"Authorization": f"Bearer {token}"}
    if org_header is not None:
        headers["X-Org-Id"] = org_header
    return client.post("/api/uploads", json=body, headers=headers)


def _put(client, token, upload_id, body: bytes, *, org_header=None):
    headers = {"Authorization": f"Bearer {token}"}
    if org_header is not None:
        headers["X-Org-Id"] = org_header
    return client.put(f"/api/uploads/{upload_id}", content=body, headers=headers)


def _staging_files(app_env) -> list[str]:
    staging = app_env["settings"].data_dir / "objects" / "staging"
    if not staging.is_dir():
        return []
    return sorted(p.name for p in staging.iterdir())


def _row(app_env, upload_id):
    return app_env["conn"].execute(
        "SELECT id, org_id, user_id, service_id, filename, size, sha256, status,"
        " object_key, doc_id, task_id, expires_at FROM uploads WHERE id = ?",
        (upload_id,),
    ).fetchone()


# ============ TC-CRED-01 凭证签发与绑定 ============


def test_cred_01_issue_returns_credential_bound_to_three_factors(app_env) -> None:
    """签发 → {upload_id, upload_url, expires_at}；DB 行绑定 sub+org+服务身份。"""
    env = app_env
    token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")

    resp = _issue(env["client"], token)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["upload_id"].startswith("upl_")
    assert body["upload_url"] == f"/api/uploads/{body['upload_id']}"
    # P3-10：expires_at 统一 UTC ISO 8601（Z 后缀）
    assert ISO_Z_RE.match(body["expires_at"]), body["expires_at"]

    row = _row(env, body["upload_id"])
    assert row is not None, "凭证行未落库"
    assert row[1] == "org:tax"      # org 绑定
    assert row[2] == "u_full"       # sub 绑定
    assert row[3] == "agent-copilot"  # 服务身份绑定（act claim）
    assert row[4] == "doc.html" and row[5] == len(PAYLOAD)
    assert row[6] == SHA_HEX
    assert row[7] == "issued"       # 初始态：未 PUT
    assert row[8] is None and row[9] is None and row[10] is None
    # expires_at 生效：库内存储（UTC 秒级）与响应（ISO Z）同一时点、且在未来
    stored = row[11]
    assert stored is not None and stored > __import__("time").strftime(
        "%Y-%m-%d %H:%M:%S", __import__("time").gmtime()
    )
    assert body["expires_at"] == stored.replace(" ", "T") + "Z"


def test_cred_01_issue_without_org_context_400(app_env) -> None:
    """无 org claim 且无 X-Org-Id → 400（组织上下文统一规则，无隐式默认）。"""
    env = app_env
    token = env["jwt"]("u_full", org=None)  # 无 org claim
    resp = _issue(env["client"], token)
    assert resp.status_code == 400
    assert "org" in resp.json()["error"]


def test_cred_01_issue_claim_header_mismatch_400(app_env) -> None:
    """claim=org:tax + X-Org-Id=org:gl 并存不一致 → 400（D18 统一规则）。"""
    env = app_env
    token = env["jwt"]("u_full", org="org:tax")
    resp = _issue(env["client"], token, org_header="org:gl")
    assert resp.status_code == 400


def test_cred_01_issue_non_member_403(app_env) -> None:
    """非组织成员签发 → 403（成员关系校验先于签发）。"""
    env = app_env
    seed_user(env["conn"], "u_guest")
    env["conn"].commit()
    token = env["jwt"]("u_guest", org="org:tax")
    resp = _issue(env["client"], token)
    assert resp.status_code == 403


def test_cred_01_issue_declared_size_over_limit_413(app_env) -> None:
    """声明 size > 全局上限（默认 200MB，P3-13）→ 413 code=size_over_limit、不落库。"""
    env = app_env
    token = env["jwt"]("u_full", org="org:tax")
    resp = _issue(env["client"], token, size=200 * 1024 * 1024 + 1)
    assert resp.status_code == 413
    assert resp.json()["code"] == "size_over_limit"
    assert env["conn"].execute("SELECT count(*) FROM uploads").fetchone()[0] == 0


def test_cred_01_issue_invalid_sha256_400(app_env) -> None:
    """sha256 非 64 位 hex → 400 code=invalid_request。"""
    env = app_env
    token = env["jwt"]("u_full", org="org:tax")
    resp = _issue(env["client"], token, sha="not-a-hex")
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_request"


def test_cred_01_issue_unauthenticated_401(app_env) -> None:
    resp = app_env["client"].post(
        "/api/uploads",
        json={"filename": "a", "size": 1, "sha256": "0" * 64, "content_type": "x"},
    )
    assert resp.status_code == 401


# ============ TC-CRED-02 PUT 字节校验 ============


def test_cred_02_put_oversize_declared_413_no_truncation(app_env) -> None:
    """① 超声明 size → 413（不静默截断）；凭证不标记已用、无孤儿 staging 文件。"""
    env = app_env
    token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")
    upload_id = _issue(env["client"], token).json()["upload_id"]

    resp = _put(env["client"], token, upload_id, PAYLOAD + b"<extra/>")

    assert resp.status_code == 413, resp.text
    assert resp.json()["code"] == "size_exceeded"
    row = _row(env, upload_id)
    assert row[7] == "issued" and row[8] is None  # 未消费、无对象
    assert _staging_files(env) == []  # P3-5/P3-21：失败路径 staging 补偿清理


def test_cred_02_put_sha256_mismatch_400(app_env) -> None:
    """② sha256 不符 → 400 code=sha256_mismatch；凭证不标记已用（T12）。"""
    env = app_env
    token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")
    upload_id = _issue(env["client"], token).json()["upload_id"]

    tampered = bytearray(PAYLOAD)
    tampered[:4] = b"XXXX"  # 等长篡改——隔离 sha256 分支（不撞 size 校验）
    resp = _put(env["client"], token, upload_id, bytes(tampered))

    assert resp.status_code == 400
    assert resp.json()["code"] == "sha256_mismatch"
    row = _row(env, upload_id)
    assert row[7] == "issued" and row[8] is None
    assert _staging_files(env) == []


def test_cred_02_put_failed_then_corrected_then_consumed_then_rejected(app_env) -> None:
    """③ 失败 PUT（超量）→ 修正重传放行 → 摄取成功消费后任何 PUT 拒绝（409）。"""
    env = app_env
    service = env["app"].state.service
    token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")
    upload_id = _issue(env["client"], token).json()["upload_id"]

    # 失败 PUT：超声明量 → 413、不计消费
    assert _put(env["client"], token, upload_id, PAYLOAD + b"x").status_code == 413
    assert _row(env, upload_id)[7] == "issued"

    # 修正重传：字节与声明一致 → 200、对象就位
    ok = _put(env["client"], token, upload_id, PAYLOAD)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "uploaded"
    assert _row(env, upload_id)[7] == "uploaded"

    # 摄取成功入队（「用掉」＝摄取成功入队——v1.4 口径）→ 凭证置已用
    result = service.credentials.consume(
        upload_id,
        org_id="org:tax", user_id="u_full", service_id="agent-copilot",
        dataset_id="ds:vat_lib", dims={"region": ["CN"]},
        create_document=service.ingest.create_document,
    )
    assert result["doc_id"].startswith("doc_") and result["status"] == "queued"
    row = _row(env, upload_id)
    assert row[7] == "consumed" and row[9] == result["doc_id"] and row[10] == result["task_id"]

    # 成功消费后任何 PUT 拒绝
    resp = _put(env["client"], token, upload_id, PAYLOAD)
    assert resp.status_code == 409
    assert resp.json()["code"] == "upload_consumed"


def test_cred_02_put_expired_410(app_env) -> None:
    """④ 过期后 PUT → 410 code=upload_expired。"""
    env = app_env
    token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")
    upload_id = _issue(env["client"], token).json()["upload_id"]
    env["conn"].execute(
        "UPDATE uploads SET expires_at = '2020-01-01 00:00:00' WHERE id = ?", (upload_id,)
    )
    env["conn"].commit()

    resp = _put(env["client"], token, upload_id, PAYLOAD)
    assert resp.status_code == 410
    assert resp.json()["code"] == "upload_expired"


def test_cred_02_put_unknown_id_404(app_env) -> None:
    env = app_env
    token = env["jwt"]("u_full", org="org:tax")
    unknown = "upl_" + "0" * 26  # 形态合法但不在场——404（存在性敏感）
    resp = _put(env["client"], token, unknown, PAYLOAD)
    assert resp.status_code == 404
    assert resp.json()["code"] == "upload_not_found"


def test_cred_02_put_binding_mismatch_403(app_env) -> None:
    """T11 REST 面：换服务身份 / 换用户 → 403 code=binding_mismatch（凭证绑定专属错误码）。"""
    env = app_env
    issuer = env["jwt"]("u_full", org="org:tax", act="agent-copilot")
    upload_id = _issue(env["client"], issuer).json()["upload_id"]

    # 换服务身份（同 sub+org、不同 act）
    other_act = env["jwt"]("u_full", org="org:tax", act="agent-rogue")
    resp = _put(env["client"], other_act, upload_id, PAYLOAD)
    assert resp.status_code == 403
    assert resp.json()["code"] == "binding_mismatch"

    # 换用户（同 org、u_cn 是 org:tax 合法成员——拒绝只能来自绑定校验）
    other_user = env["jwt"]("u_cn", org="org:tax", act="agent-copilot")
    resp = _put(env["client"], other_user, upload_id, PAYLOAD)
    assert resp.status_code == 403
    assert resp.json()["code"] == "binding_mismatch"

    assert _row(env, upload_id)[7] == "issued"  # 凭证不标记已用（T12）


def test_cred_02_put_global_cap_independent_413(tmp_path) -> None:
    """⑤ >全局上限 → 413 code=size_over_limit——**独立于声明**生效（P3-13）：
    直插声明 size 大于小上限的凭证行（合法声明在签发面用默认上限放行——模拟
    上限收紧/存量行），PUT 面独立拦截。"""
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from fake_providers import FakeEmbedder

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        probe_interval_s=0, upload_max_bytes=64,  # 全局上限注入为 64 字节
    )
    app = create_app(
        settings, embedder=FakeEmbedder(dim=8), gate=EmbeddingGate(), run_startup_probe=False
    )
    from knowledge_lattice.store.sqlite import connect

    conn = connect(settings.db_path)
    conn.execute("INSERT OR IGNORE INTO orgs(id, name) VALUES('org:tax', 't')")
    conn.execute("INSERT OR IGNORE INTO users(id, username) VALUES('u_full', 'u_full')")
    conn.execute(
        "INSERT OR IGNORE INTO user_org_memberships(user_id, org_id)"
        " VALUES('u_full', 'org:tax')"
    )
    payload = b"x" * 100  # ≤ 声明（128）、> 全局上限（64）
    upload_id = "upl_" + "1" * 26
    conn.execute(
        "INSERT INTO uploads(id, org_id, user_id, service_id, filename, size, sha256,"
        " content_type, status, expires_at)"
        " VALUES(?, 'org:tax', 'u_full', NULL, 'a.bin', 128, ?, 'application/octet-stream',"
        " 'issued', '2099-01-01 00:00:00')",
        (upload_id, hashlib.sha256(payload).hexdigest()),
    )
    conn.commit()

    from knowledge_lattice.domain.auth import issue_dev_jwt

    token = issue_dev_jwt(settings, user_id="u_full", org="org:tax")
    with TestClient(app) as client:
        put = client.put(
            f"/api/uploads/{upload_id}", content=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    assert put.status_code == 413
    assert put.json()["code"] == "size_over_limit"
    assert conn.execute(
        "SELECT status FROM uploads WHERE id = ?", (upload_id,)
    ).fetchone()[0] == "issued"
    conn.close()


def test_cred_02_put_repeat_allowed_until_consumed(app_env) -> None:
    """未消费凭证可重复 PUT 直至成功消费或过期（M1-3 需求 A5）——第二次 PUT 覆盖对象。"""
    env = app_env
    token = env["jwt"]("u_full", org="org:tax", act="agent-copilot")
    upload_id = _issue(env["client"], token).json()["upload_id"]

    first = _put(env["client"], token, upload_id, PAYLOAD)
    second = _put(env["client"], token, upload_id, PAYLOAD)  # 同字节重传
    assert first.status_code == 200 and second.status_code == 200
    assert _row(env, upload_id)[7] == "uploaded"
