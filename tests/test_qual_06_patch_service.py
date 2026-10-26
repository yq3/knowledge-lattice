"""PATCH /api/quality-flags/{id} 服务层双后端直测（Committer R1——PG 写路径缺口）。

R1 的 PATCH 断言全在 REST 面（sqlite app_env）——`append_chunk_manual_terms` /
`append_quality_manual_tags` 的 **PG 写路径零直测**。本文件经 `patch_flag`
服务层双后端参数化补齐：人工词追加写（chunks 人工列 + FTS 同步面）、manual_tags
轨迹累积、org_admin 放行分支、跨 org 404、权限拒绝。
"""

from __future__ import annotations

import pytest
from helpers import insert_chunk, seed_dataset, seed_doc_dims, seed_document

ORG = "org:tax"
ORG_GL = "org:gl"


def _rid(db, chunk_id: str) -> int:
    return db.execute("SELECT rid FROM chunks WHERE id = ?", (chunk_id,)).fetchone()[0]


def _seed_flag(qual_env, *, doc_id: str = "d_patch", org_id: str = ORG,
               owner: str = "u_owner") -> str:
    env = qual_env
    db = env["db"]
    if org_id == ORG_GL:
        seed_dataset(db, ORG_GL, "ds:gl")
    seed_document(
        db, doc_id=doc_id, org_id=org_id,
        dataset_id="ds:vat_lib" if org_id == ORG else "ds:gl",
        owner_user_id=owner,
    )
    if org_id == ORG:
        seed_doc_dims(db, doc_id, {"region": ["CN"]})
    chunk_id = insert_chunk(
        db, doc_id=doc_id, seq=1, content="补标服务层样例块",
        content_seg="补标 服务 层 样例 块",
    )
    db.execute(f"UPDATE documents SET active_version = 1 WHERE id = '{doc_id}'")
    db.commit()
    return env["backend"].insert_quality_flag(
        chunk_id=chunk_id, doc_id=doc_id, reason="low_idf", detail_json="{}"
    )


def test_qual_14_patch_manual_terms_service_dual_backend(qual_env) -> None:
    """人工词追加写（双后端写路径直测）：chunks.keywords/tags 追加 + FTS 可命中 +
    manual_tags 轨迹逐次累积（append_chunk_manual_terms / append_quality_manual_tags）。"""
    env = qual_env
    db, backend, quality = env["db"], env["backend"], env["quality"]
    flag_id = _seed_flag(env)
    chunk_id = "chk:d_patch:v1:1"

    # 第一次补标（owner）
    out = quality.patch_flag(
        flag_id, org_id=ORG, actor_user_id="u_owner",
        keywords="纳税信用等级", tags="人工标签甲",
    )
    assert out["keywords"] == "纳税信用等级"
    assert out["tags"] == "人工标签甲"
    row = db.execute(
        "SELECT keywords, tags FROM chunks WHERE id = ?", (chunk_id,)
    ).fetchone()
    assert row == ("纳税信用等级", "人工标签甲")

    # 追加语义：二次补标累积（不清列）
    quality.patch_flag(
        flag_id, org_id=ORG, actor_user_id="u_owner",
        keywords="专用发票校验", tags="人工标签乙",
    )
    row = db.execute(
        "SELECT keywords, tags FROM chunks WHERE id = ?", (chunk_id,)
    ).fetchone()
    assert row[0] == "纳税信用等级 专用发票校验"
    assert row[1] == "人工标签甲 人工标签乙"

    # FTS 写路径生效（au 触发器 / GENERATED 同步——人工词可命中）
    from knowledge_lattice.store.backend import AclPlan

    hits = backend.recall_fts(
        ["纳税信用等级"], AclPlan(org_id=ORG), top_k=5
    )
    assert any(h["chunk_id"] == chunk_id for h in hits), (
        "PG/SQLite 写路径同步 FTS——人工词应可命中"
    )

    # manual_tags 轨迹：逐次累积的 JSON 行（审计面）
    flag = backend.get_quality_flag(flag_id)
    lines = [ln for ln in (flag["manual_tags"] or "").splitlines() if ln]
    assert len(lines) == 2
    import json as _json

    records = [_json.loads(ln) for ln in lines]
    assert records[0]["keywords"] == "纳税信用等级"
    assert records[1]["tags"] == "人工标签乙"
    assert all(r["actor"] == "u_owner" for r in records)
    # outbox 审计事件（两次 PATCH）
    events = db.execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'quality_flag.patch'"
    ).fetchone()[0]
    assert events == 2


def test_qual_15_patch_org_admin_allowed_and_member_denied(qual_env) -> None:
    """权限分支：非 owner 的 org_admin 放行；普通成员拒绝（QualityPermissionError）。"""
    from knowledge_lattice.core.docs.quality import QualityPermissionError

    env = qual_env
    flag_id = _seed_flag(env, owner="u_owner")
    quality = env["quality"]

    # org_admin（admin_tax——matrix 造数、无维度授权不影响管理写）放行
    out = quality.patch_flag(
        flag_id, org_id=ORG, actor_user_id="admin_tax", state="resolved"
    )
    assert out["state"] == "resolved"

    # 普通成员（u_cn 非 owner 非 org_admin）拒绝
    flag_id2 = _seed_flag(env, doc_id="d_patch2")
    with pytest.raises(QualityPermissionError):
        quality.patch_flag(
            flag_id2, org_id=ORG, actor_user_id="u_cn", state="ignored"
        )


def test_qual_16_patch_cross_org_flag_404(qual_env) -> None:
    """跨 org 404：flag 属 org:gl——org:tax 的 owner/org_admin 一律 404
    （QualityFlagNotFoundError——存在性敏感）；org:gl 侧 org_admin 放行（对照）。"""
    from knowledge_lattice.core.docs.quality import QualityFlagNotFoundError
    from helpers import seed_membership

    env = qual_env
    db = env["db"]
    gl_flag = _seed_flag(env, doc_id="d_gl_patch", org_id=ORG_GL, owner="u_gl")
    # org:gl 管理员（u_gl 为 gl 的 org_admin——matrix 造数）

    # org:tax 侧系统管理员/owner 皆 404（跨组织存在性不泄露）
    for actor in ("u_owner", "admin_tax", "sysadmin"):
        with pytest.raises(QualityFlagNotFoundError):
            env["quality"].patch_flag(
                gl_flag, org_id=ORG, actor_user_id=actor, state="resolved"
            )

    # 对照：org:gl 侧 org_admin 放行
    out = env["quality"].patch_flag(
        gl_flag, org_id=ORG_GL, actor_user_id="u_gl", state="ignored"
    )
    assert out["state"] == "ignored"
