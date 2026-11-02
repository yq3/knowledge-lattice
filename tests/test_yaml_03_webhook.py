"""TC-YAML-03 webhook（design §6.2 L1142）：Git 合并回调——签名=服务身份，
仅签名持有方可触发；yaml 合并事件入 audit_outbox；凭证明文不落日志。"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

import pytest

from helpers import seed_membership, seed_org, seed_user

ORG = "org:tax"
SECRET = "whsec-顶顶大名的秘密"

WEBHOOK_BODY = json.dumps({"ref": "refs/heads/main", "commit": "abc1234"}).encode()


@pytest.fixture()
def wh_app(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.store.sqlite import connect

    settings = Settings(
        environment="test", data_dir=tmp_path, embed_dim=8,
        probe_interval_s=0, maintenance_interval_s=0.0, worker_mode="inline",
        semantic_sources_json=json.dumps({
            ORG: {"yaml": {"endpoint": str(tmp_path / "yamlrepo"), "webhook_secret": SECRET}},
        }),
    )
    app = create_app(settings, gate=EmbeddingGate(), run_startup_probe=False)
    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    seed_user(conn, "u1")
    seed_membership(conn, "u1", ORG)
    with TestClient(app) as client:
        yield {"client": client, "conn": conn, "settings": settings}
    conn.close()


def _sig(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _events(conn, event_type: str) -> list:
    return conn.execute(
        "SELECT payload_json FROM audit_outbox WHERE event_type = ?",
        (event_type,),
    ).fetchall()


# ---- ① 正确签名 → 触发 yaml 合并 + 构建 + 事件 ----


def test_webhook_valid_signature_triggers_yaml_sync(wh_app) -> None:
    resp = wh_app["client"].post(
        f"/api/orgs/{ORG}/semantic/yaml/webhook",
        content=WEBHOOK_BODY,
        headers={"X-Lattice-Signature": _sig(WEBHOOK_BODY), "X-Org-Id": ORG},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["adapter"] == "yaml" and body["task_id"]

    # yaml 合并事件入 audit_outbox（FR-6 语义层事件——#38 P1-7）
    events = _events(wh_app["conn"], "semantic.yaml_merge")
    assert events and "task_id" in events[-1][0]
    # 任务行入队（semantic_sync {org, adapter: yaml}）
    row = wh_app["conn"].execute(
        "SELECT payload FROM tasks WHERE id = ?", (body["task_id"],)).fetchone()
    assert row and json.loads(row[0])["adapter"] == "yaml"


# ---- ②③ 错误签名 / 服务身份缺失 → 拒绝 ----


def test_webhook_invalid_signature_rejected(wh_app) -> None:
    bad = _sig(WEBHOOK_BODY, secret="wrong-secret")
    resp = wh_app["client"].post(
        f"/api/orgs/{ORG}/semantic/yaml/webhook",
        content=WEBHOOK_BODY,
        headers={"X-Lattice-Signature": bad, "X-Org-Id": ORG},
    )
    assert resp.status_code in (401, 403)
    assert wh_app["conn"].execute("SELECT count(*) FROM tasks").fetchone()[0] == 0


def test_webhook_missing_signature_rejected(wh_app) -> None:
    resp = wh_app["client"].post(
        f"/api/orgs/{ORG}/semantic/yaml/webhook",
        content=WEBHOOK_BODY, headers={"X-Org-Id": ORG},
    )
    assert resp.status_code in (401, 403)
    # 即使带用户 Bearer（成员身份）也无签名即拒——Git 回调入口仅服务身份
    resp2 = wh_app["client"].post(
        f"/api/orgs/{ORG}/semantic/yaml/webhook",
        content=WEBHOOK_BODY,
        headers={"X-Org-Id": ORG, "Authorization": "Bearer whatever"},
    )
    assert resp2.status_code in (401, 403)


def test_webhook_org_header_mismatch_400(wh_app) -> None:
    resp = wh_app["client"].post(
        f"/api/orgs/{ORG}/semantic/yaml/webhook",
        content=WEBHOOK_BODY,
        headers={"X-Lattice-Signature": _sig(WEBHOOK_BODY), "X-Org-Id": "org:gl"},
    )
    assert resp.status_code == 400


# ---- 凭证明文不落日志 ----


def test_webhook_secret_never_logged(wh_app, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        wh_app["client"].post(
            f"/api/orgs/{ORG}/semantic/yaml/webhook",
            content=WEBHOOK_BODY,
            headers={"X-Lattice-Signature": _sig(WEBHOOK_BODY, "wrong"), "X-Org-Id": ORG},
        )
        wh_app["client"].post(
            f"/api/orgs/{ORG}/semantic/yaml/webhook",
            content=WEBHOOK_BODY,
            headers={"X-Lattice-Signature": _sig(WEBHOOK_BODY), "X-Org-Id": ORG},
        )
    for record in caplog.records:
        assert SECRET not in record.getMessage()
