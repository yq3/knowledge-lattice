"""D26 agent key store 层（issue #34——迁移 0013 + AgentKeyBackend 双方言）。

覆盖（`backend` fixture 双后端参数化，sqlite + PG 同一代码）：

- 迁移 0013：agent_keys 表/索引/FK 级联/token_hash UNIQUE/水位 13；
- create → get_by_hash 往返（字段口径、expires_at NULL 与显式值归一、created_at
  由 DB 默认 CURRENT_TIMESTAMP 写）；
- list：仅本 org、**含已撤销行**、created_at DESC；
- revoke：幂等（二次撤销原样返回且零新审计）、跨 org/不存在 → None、实际撤销
  才写审计；
- touch：last_used_at 早于 cutoff 才回写（窗口内/等于 cutoff 跳过；行不存在
  → False）；
- token_hash 唯一冲突：ValueError、失败写零残留（行与审计都不落）；
- 审计与业务写同事务：成功时行与 outbox 各一行且 payload 原样；outbox 注入
  失败 → create/revoke 的业务写一并回滚（TC-OPS-01 同生共死口径）。

口径：审计 payload 不含明文 key（store 只收 sha256；调用方构造 payload）；
now/expires_at 一律 taskclock UTC 库格式字符串。
"""

from __future__ import annotations

import json

import pytest

from helpers import FUTURE_TS, NOW_TS, PAST_TS, seed_org, seed_user

ORG = "org:agent-keys"
ORG_OTHER = "org:agent-keys-other"


def _seed_principals(backend) -> None:
    seed_org(backend, ORG, "Agent Key 组织")
    seed_org(backend, ORG_OTHER, "另一组织")
    seed_user(backend, "u_owner", "owner")
    seed_user(backend, "u_admin", "admin")


def _create(b, **overrides):
    params = {
        "key_id": "ak:1",
        "org_id": ORG,
        "user_id": "u_owner",
        "label": "ci-agent",
        "token_hash": "sha256:aaa",
        "prefix": "lka_aaaa",
        "created_by": "u_admin",
        "expires_at": None,
        "audit": None,
    }
    params.update(overrides)
    return b.create_agent_key(**params)


def _audit_rows(backend) -> list[tuple]:
    return backend.execute(
        "SELECT event_type, payload_json FROM audit_outbox"
    ).fetchall()


# ============ 迁移 0013 ============


def test_migration_0013_agent_keys_schema(backend) -> None:
    """表/索引/水位 + FK 级联 + token_hash UNIQUE（sqlite/PG 各自入口）。"""
    expected_cols = {
        "id", "org_id", "user_id", "label", "token_hash", "prefix", "created_by",
        "created_at", "last_used_at", "revoked_at", "revoked_by", "expires_at",
    }
    if backend.is_sqlite:
        cols = {r[1] for r in backend.execute("PRAGMA table_info(agent_keys)")}
        assert expected_cols <= cols
        assert backend.execute("PRAGMA user_version").fetchone()[0] == 13
        for idx in ("idx_agent_keys_org", "idx_agent_keys_user"):
            assert backend.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
                (idx,),
            ).fetchone() is not None
        ddl = " ".join(
            backend.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'agent_keys'"
            ).fetchone()[0].split()
        )
        assert "ON DELETE CASCADE" in ddl
        assert "token_hash TEXT NOT NULL UNIQUE" in ddl
    else:
        cols = {
            r[0]
            for r in backend.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = current_schema() AND table_name = 'agent_keys'"
            )
        }
        assert expected_cols <= cols
        from knowledge_lattice.store.postgres.migrate import applied_versions

        assert applied_versions(backend.raw)[-1] == 13
        assert backend.execute(
            "SELECT name FROM schema_migrations WHERE version = ?", (13,)
        ).fetchone() == ("agent_keys",)
        for idx in ("idx_agent_keys_org", "idx_agent_keys_user"):
            assert backend.execute(
                "SELECT 1 FROM pg_indexes WHERE schemaname = current_schema()"
                " AND indexname = ?",
                (idx,),
            ).fetchone() is not None

    _seed_principals(backend)
    b = backend.make_backend()
    _create(b)

    # token_hash 全库唯一（绕过 store 直插重复摘要 → 约束拒绝）
    with pytest.raises(backend.integrity_error):
        backend.execute(
            "INSERT INTO agent_keys(id, org_id, user_id, label, token_hash, prefix,"
            " created_by) VALUES(?, ?, ?, ?, ?, ?, ?)",
            ("ak:dup", ORG, "u_owner", "dup", "sha256:aaa", "lka_dup", "u_admin"),
        )

    # FK：user 删除级联清 key（org 同理 0013 DDL ON DELETE CASCADE）
    backend.execute("DELETE FROM users WHERE id = ?", ("u_owner",))
    assert backend.execute("SELECT count(*) FROM agent_keys").fetchone()[0] == 0

    # FK：未知 user 拒绝（孤儿 key 不得落库）
    with pytest.raises(backend.fk_error):
        backend.execute(
            "INSERT INTO agent_keys(id, org_id, user_id, label, token_hash, prefix,"
            " created_by) VALUES(?, ?, ?, ?, ?, ?, ?)",
            ("ak:ghost", ORG, "u_ghost", "ghost", "sha256:ghost", "lka_ghost",
             "u_admin"),
        )


# ============ create / get_by_hash ============


def test_create_and_get_by_hash_roundtrip(backend) -> None:
    _seed_principals(backend)
    b = backend.make_backend()
    payload = json.dumps(
        {"actor": "u_admin", "key_id": "ak:1", "user_id": "u_owner",
         "org_id": ORG, "label": "ci-agent"},
        ensure_ascii=False,
    )
    out = _create(
        b, expires_at="2099-01-01T00:00:00Z",
        audit=("agent_key.created", payload),
    )

    assert set(out) == {
        "id", "org_id", "user_id", "label", "token_hash", "prefix", "created_by",
        "created_at", "last_used_at", "revoked_at", "revoked_by", "expires_at",
    }
    assert out["id"] == "ak:1"
    assert (out["org_id"], out["user_id"]) == (ORG, "u_owner")
    assert (out["label"], out["token_hash"], out["prefix"]) == (
        "ci-agent", "sha256:aaa", "lka_aaaa",
    )
    assert out["created_by"] == "u_admin"
    assert out["created_at"]  # DB 默认 CURRENT_TIMESTAMP
    assert out["last_used_at"] is None
    assert (out["revoked_at"], out["revoked_by"]) == (None, None)
    assert out["expires_at"] == FUTURE_TS  # ISO 8601 → 库格式归一

    assert b.get_agent_key_by_hash("sha256:aaa") == out
    assert b.get_agent_key_by_hash("sha256:missing") is None

    # 永不过期（NULL）+ 不传审计：行写入、outbox 不新增
    out2 = _create(b, key_id="ak:2", token_hash="sha256:bbb", prefix="lka_bbbb",
                   expires_at=None)
    assert out2["expires_at"] is None
    assert _audit_rows(backend) == [("agent_key.created", payload)]


# ============ list ============


def test_list_agent_keys_org_scoped_includes_revoked(backend) -> None:
    _seed_principals(backend)
    b = backend.make_backend()
    for key_id, ts in (
        ("ak:past", PAST_TS), ("ak:mid", NOW_TS), ("ak:future", FUTURE_TS),
    ):
        _create(b, key_id=key_id, token_hash=f"sha256:{key_id}")
        # created_at 造数（同秒创建时 id DESC 兜底——本用例钉 created_at 序）
        backend.execute(
            "UPDATE agent_keys SET created_at = ? WHERE id = ?", (ts, key_id)
        )
    _create(b, key_id="ak:other", org_id=ORG_OTHER, token_hash="sha256:other")
    b.revoke_agent_key(
        key_id="ak:mid", org_id=ORG, revoked_by="u_admin",
        audit=("agent_key.revoked", json.dumps({"actor": "u_admin"})),
    )

    rows = b.list_agent_keys(ORG)
    assert [r["id"] for r in rows] == ["ak:future", "ak:mid", "ak:past"]
    assert rows[1]["revoked_at"] is not None  # 含已撤销行（管理面对账）
    assert rows[0]["revoked_at"] is None
    assert [r["id"] for r in b.list_agent_keys(ORG_OTHER)] == ["ak:other"]
    assert [r["org_id"] for r in rows] == [ORG, ORG, ORG]


# ============ revoke ============


def test_revoke_idempotent_and_org_scoped(backend) -> None:
    _seed_principals(backend)
    b = backend.make_backend()
    _create(b, audit=("agent_key.created", "{}"))
    first = b.revoke_agent_key(
        key_id="ak:1", org_id=ORG, revoked_by="u_admin",
        audit=("agent_key.revoked", json.dumps({"actor": "u_admin"})),
    )
    assert first is not None
    assert first["revoked_at"] is not None
    assert first["revoked_by"] == "u_admin"

    # 幂等：已撤销 → 原样返回（revoked_at/revoked_by 保持首次值）+ 零新审计
    second = b.revoke_agent_key(
        key_id="ak:1", org_id=ORG, revoked_by="u_owner",
        audit=("agent_key.revoked", json.dumps({"actor": "u_owner"})),
    )
    assert second == first
    assert _audit_rows(backend) == [
        ("agent_key.created", "{}"),
        ("agent_key.revoked", json.dumps({"actor": "u_admin"})),
    ]

    # 跨 org / 不存在 → None（不泄露他组织 key、不写审计）
    _create(b, key_id="ak:2", token_hash="sha256:bbb")
    assert b.revoke_agent_key(
        key_id="ak:2", org_id=ORG_OTHER, revoked_by="u_admin",
        audit=("agent_key.revoked", "{}"),
    ) is None
    assert b.revoke_agent_key(
        key_id="ak:missing", org_id=ORG, revoked_by="u_admin",
        audit=("agent_key.revoked", "{}"),
    ) is None
    assert b.get_agent_key_by_hash("sha256:bbb")["revoked_at"] is None
    assert len(_audit_rows(backend)) == 2


# ============ touch（last_used_at 节流） ============


def test_touch_last_used_throttle(backend) -> None:
    """last_used_at 早于 cutoff 才回写；等于/晚于 cutoff 跳过；行不存在 False。"""
    _seed_principals(backend)
    b = backend.make_backend()
    _create(b)

    # NULL（首次使用）→ 写
    assert b.touch_agent_key_last_used(
        "ak:1", now=NOW_TS, cutoff=PAST_TS
    ) is True
    assert b.get_agent_key_by_hash("sha256:aaa")["last_used_at"] == NOW_TS

    # last_used_at == cutoff → 节流跳过（严格 <）
    assert b.touch_agent_key_last_used(
        "ak:1", now=FUTURE_TS, cutoff=NOW_TS
    ) is False
    assert b.get_agent_key_by_hash("sha256:aaa")["last_used_at"] == NOW_TS

    # last_used_at < cutoff → 写 now
    late_cutoff = "2099-01-02 00:00:00"
    assert b.touch_agent_key_last_used(
        "ak:1", now=FUTURE_TS, cutoff=late_cutoff
    ) is True
    assert b.get_agent_key_by_hash("sha256:aaa")["last_used_at"] == FUTURE_TS

    # 行不存在 → False
    assert b.touch_agent_key_last_used(
        "ak:missing", now=FUTURE_TS, cutoff=late_cutoff
    ) is False


# ============ token_hash 唯一冲突 ============


def test_token_hash_unique_conflict(backend) -> None:
    _seed_principals(backend)
    b = backend.make_backend()
    _create(b, audit=("agent_key.created", "{}"))

    with pytest.raises(ValueError, match="摘要冲突"):
        _create(
            b, key_id="ak:dup", token_hash="sha256:aaa",
            audit=("agent_key.created", "{}"),
        )

    assert backend.execute("SELECT count(*) FROM agent_keys").fetchone()[0] == 1
    # 失败写整体回滚：审计行零残留（同生共死）
    assert _audit_rows(backend) == [("agent_key.created", "{}")]


# ============ 审计同事务 / 失败回滚 ============


def test_create_audit_failure_rolls_back_row(backend, monkeypatch) -> None:
    _seed_principals(backend)
    b = backend.make_backend()

    def _boom(self, conn, event_type: str, payload_json: str) -> None:
        raise RuntimeError("injected outbox failure")

    monkeypatch.setattr(type(b), "_outbox_insert", _boom)
    with pytest.raises(RuntimeError, match="injected outbox failure"):
        _create(b, audit=("agent_key.created", "{}"))

    assert backend.execute("SELECT count(*) FROM agent_keys").fetchone()[0] == 0
    assert _audit_rows(backend) == []


def test_revoke_audit_failure_leaves_key_unrevoked(backend, monkeypatch) -> None:
    _seed_principals(backend)
    b = backend.make_backend()
    _create(b)

    def _boom(self, conn, event_type: str, payload_json: str) -> None:
        raise RuntimeError("injected outbox failure")

    monkeypatch.setattr(type(b), "_outbox_insert", _boom)
    with pytest.raises(RuntimeError, match="injected outbox failure"):
        b.revoke_agent_key(
            key_id="ak:1", org_id=ORG, revoked_by="u_admin",
            audit=("agent_key.revoked", "{}"),
        )

    row = b.get_agent_key_by_hash("sha256:aaa")
    assert row["revoked_at"] is None  # 撤销随审计失败一并回滚
    assert row["revoked_by"] is None
    assert _audit_rows(backend) == []


# ============ 协议面 ============


def test_agent_key_protocol_surface() -> None:
    from knowledge_lattice.store.backend import (
        AgentKeyBackend,
        StorageBackend,
    )

    methods = (
        "create_agent_key", "get_agent_key_by_hash", "list_agent_keys",
        "revoke_agent_key", "touch_agent_key_last_used",
    )
    assert issubclass(StorageBackend, AgentKeyBackend)
    for method in methods:
        assert hasattr(AgentKeyBackend, method)
        assert hasattr(StorageBackend, method)
