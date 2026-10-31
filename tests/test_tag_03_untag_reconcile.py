"""M2-S3/m2s-5 untag 同事务 + 定时对账（T-S10 / TC-TAG-03 + A5）。

- T-S10①：覆盖上传版本切换 → 旧版本块的 sem_chunk_entities 行**切换事务内**
  清除（新版本块照常打标）；
- T-S10②：删除文档 → 同事务清除（删后零残留）；
- TC-TAG-03：对账任务独立造数残留行（块已删/实体 retired）验证清理能力
  （兜底路径自身可测）——悬挂行物理清理 + dict_rev 落后**只计数补投**
  （不直接改标——幂等收敛靠 retag）；
- 失败版本删块（T8）同事务 untag。
"""

from __future__ import annotations

import json

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"


@pytest.fixture()
def env(backend, tmp_path):
    from types import SimpleNamespace

    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    b = backend.make_backend()
    recs = [EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣"),
            EntityRecord(type="concept", key="vat.other", name="历史口径概念")]
    run_sync(b, ORG, FakeSourceAdapter("template_center", recs),
             settings=settings, snapshot=list(recs), now=NOW)
    clear_annotator_cache()
    result = run_build(b, ORG, settings=settings)
    assert result["status"] == "ready"

    # 矩阵上传前提（维度/授权）
    from helpers import (dim_id_for, seed_dataset, seed_dimension, seed_dim_value,
                         seed_grant, seed_membership, seed_user, val_id_for)

    seed_dataset(backend, ORG, "ds:vat_lib")
    seed_dimension(backend, ORG, "region")
    seed_dim_value(backend, dim_id_for(ORG, "region"), "CN")
    seed_dim_value(backend, dim_id_for(ORG, "region"), "OS")
    seed_user(backend, "u_full")
    seed_membership(backend, "u_full", ORG)
    for v in ("CN", "OS"):
        seed_grant(backend, user_id="u_full", dim_id=dim_id_for(ORG, "region"),
                   val_id=val_id_for(ORG, "region", v))
    return SimpleNamespace(db=backend, backend=b, settings=settings,
                           build=result, tmp=tmp_path)


def _service(env):
    from fake_providers import FakeEmbedder
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.semantic.tagging import make_ingest_tagger

    return IngestService(
        env.backend, FakeEmbedder(dim=8, model_name="fake-embed"),
        env.settings, EmbeddingGate(), env.tmp / "objects",
        tagger=make_ingest_tagger(env.backend, env.settings),
    )


def _ingest(env, content: str, *, doc_id=None):
    service = _service(env)
    return service.create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="t",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=content.encode("utf-8"), mime_type="text/plain",
        filename="doc.txt", doc_id=doc_id,
    )


def _tags(env, doc_id, version=None):
    sql = ("SELECT chunk_rid, version, entity_id, dict_rev FROM"
           " sem_chunk_entities WHERE doc_id = ?")
    args: tuple = (doc_id,)
    if version is not None:
        sql += " AND version = ?"
        args = (doc_id, version)
    return env.db.execute(sql + " ORDER BY chunk_rid", args).fetchall()


def _active_tags(env, doc_id):
    return _tags(env, doc_id, version=env.backend.get_document(doc_id)["active_version"])


# ---- T-S10①：版本切换同事务 untag ----


def test_t_s10_version_switch_untags_old_blocks(env) -> None:
    """覆盖上传切换：旧版本块的 tag 行在**切换事务内**清除、新版本块照常打标。"""
    doc_id, t1 = _ingest(env, "本月进项税额抵扣的口径说明。")
    _service(env).run_task(t1)
    assert _tags(env, doc_id), "v1 打标就位（前置）"

    # 覆盖上传 v2（不同内容——同内容 hash 会 409？覆盖上传不查 hash——同 hash 合法）
    _, t2 = _ingest(env, "次月口径：进项税额抵扣继续生效。", doc_id=doc_id)
    _service(env).run_task(t2)

    doc = env.backend.get_document(doc_id)
    assert doc["active_version"] == 2, "覆盖上传应切换到 v2"
    # 旧版本块标行随切换清除（T-S10①）
    assert _tags(env, doc_id, version=1) == [], "旧版本 tag 行须切换事务内清除"
    # 新版本块照常打标
    v2 = _active_tags(env, doc_id)
    assert v2 and all(r[1] == 2 for r in v2), "新版本块打标就位"


def test_t8_pending_failed_untags(env, monkeypatch) -> None:
    """pending 失败（T8 物理删块）的语义标同事务清除。"""
    doc_id, t1 = _ingest(env, "本月进项税额抵扣的口径说明。")
    _service(env).run_task(t1)
    assert _tags(env, doc_id)

    _, t2 = _ingest(env, "次月口径：进项税额抵扣继续生效。", doc_id=doc_id)
    service = _service(env)
    # embed 阶段注入失败 → pending failed + T8 物理删块（v2 块+标同事务清除）
    from fake_providers import FakeEmbedder

    class _BoomEmbed(FakeEmbedder):
        def embed(self, texts):
            raise RuntimeError("injected embed failure")

    svc = _service(env)
    svc._embedder = _BoomEmbed(dim=8, model_name="fake-embed")
    with pytest.raises(RuntimeError):
        svc.run_task(t2)

    doc = env.backend.get_document(doc_id)
    assert doc["pending_status"] == "failed", "pending v2 失败（T8 删块）"
    assert _tags(env, doc_id, version=2) == [], "失败版本 tag 行随删块清除"
    assert _active_tags(env, doc_id), "在用版本 v1 的标不受影响"


# ---- T-S10②：删文档同事务 untag ----


def test_t_s10_delete_document_untags(env) -> None:
    """删除文档 → sem_chunk_entities 同事务清除（删后零残留）。"""
    doc_id, t1 = _ingest(env, "本月进项税额抵扣的口径说明。")
    _service(env).run_task(t1)
    assert _tags(env, doc_id)

    svc = _service(env)
    svc.delete_document(org_id=ORG, doc_id=doc_id, actor_user_id="u_full")
    assert _tags(env, doc_id) == [], "删文档后 tag 零残留（T-S10②）"


# ---- TC-TAG-03 / A5：对账扫描（悬挂清理 + 落后补投） ----


def test_tc_tag_03_reconcile_clears_orphans_and_reports(env) -> None:
    """独立造数残留行验证清理能力：① 悬挂行（块已删/不存在）② 实体 retired
    行 → 物理清理 + 计数报告；③ dict_rev 落后**只计数不动行**（补投 retag
    幂等收敛——不直接改标）。"""
    doc_id, t1 = _ingest(env, "本月进项税额抵扣的口径说明。")
    _service(env).run_task(t1)
    eid = env.backend.resolve_entity_ids(
        ORG, [("concept", "vat.input_credit")])[("concept", "vat.input_credit")]

    # ① 悬挂行：chunk_rid 指向不存在的块
    env.db.execute(
        "INSERT INTO sem_chunk_entities(org_id, chunk_rid, doc_id, version,"
        " entity_id, hits, dict_rev) VALUES(?, 999999, ?, 1, ?, 1, 'deadbeef')",
        (ORG, doc_id, eid))
    # ② 实体已亡行：独立实体 vat.other 置 retired（其标行挂在活跃块上——
    # 历史标残留形态；re-sync 不含该实体→missing，直改 retired 等价终态）
    eid_other = env.backend.resolve_entity_ids(
        ORG, [("concept", "vat.other")])[("concept", "vat.other")]
    rid = env.db.execute(
        "SELECT rid FROM chunks WHERE doc_id = ? AND version = 1", (doc_id,)
    ).fetchone()[0]
    env.db.execute(
        "INSERT INTO sem_chunk_entities(org_id, chunk_rid, doc_id, version,"
        " entity_id, hits, dict_rev) VALUES(?, ?, ?, 1, ?, 1, ?)",
        (ORG, rid, doc_id, eid_other, env.build["dict_rev"]))
    env.db.execute(
        "UPDATE sem_entities SET status = 'retired' WHERE org_id = ? AND id = ?",
        (ORG, eid_other))

    # ③ dict_rev 落后行：重新同步实体（带新别名——dict_rev 前进）+ 新 build
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync

    back = EntityRecord(type="concept", key="vat.input_credit",
                        name="进项税额抵扣", aliases=("进项面",))
    run_sync(env.backend, ORG,
             FakeSourceAdapter("template_center", [back]),
             settings=env.settings, snapshot=[back], now=NOW)
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build

    clear_annotator_cache()
    r2 = run_build(env.backend, ORG, settings=env.settings)
    assert r2["status"] == "ready" and r2["dict_rev"] != env.build["dict_rev"]

    report = env.backend.sem_reconcile_chunk_tags()
    ours = next(r for r in report if r["org_id"] == ORG)
    assert ours["stale_chunks_removed"] >= 1, "悬挂行（块不存在）须清理"
    assert ours["retired_entities_removed"] >= 1, "实体已亡行须清理"
    assert ours["lagging_chunks"] >= 1, "dict_rev 落后块须计数（只报告）"

    # 落后行未被对账直接改写（活跃实体的标行 dict_rev 仍旧值——补投 retag 收敛）
    remaining = env.db.execute(
        "SELECT dict_rev FROM sem_chunk_entities WHERE org_id = ?"
        " AND chunk_rid = ? AND entity_id = ?", (ORG, rid, eid)).fetchall()
    assert remaining and remaining[0][0] == env.build["dict_rev"], \
        "对账不得直接改标（落后行交 retag 幂等收敛）"
    # 悬挂/retired 行已物理清除
    assert env.db.execute(
        "SELECT COUNT(*) FROM sem_chunk_entities WHERE org_id = ?"
        " AND (chunk_rid = 999999 OR entity_id = ?)", (ORG, eid_other)
    ).fetchone()[0] == 0


def test_a5_maintenance_reconcile_body_enqueues_retag(env) -> None:
    """maintenance 对账任务体：报告进 stats + dict_rev 落后 org 补投
    semantic_retag（不直接改标）；在队去重 + done 后 24h 节流双防线。"""
    from knowledge_lattice.worker.maintenance import MAINTENANCE_BODIES

    doc_id, t1 = _ingest(env, "本月进项税额抵扣的口径说明。")
    _service(env).run_task(t1)

    # 落后构造：新构建（别名增删 → dict_rev 前进，块 dict_rev 落后）
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync

    recs = [EntityRecord(type="concept", key="vat.input_credit",
                         name="进项税额抵扣", aliases=("进项面",)),
            EntityRecord(type="concept", key="vat.other", name="历史口径概念")]
    run_sync(env.backend, ORG, FakeSourceAdapter("template_center", recs),
             settings=env.settings, snapshot=list(recs), now=NOW)
    clear_annotator_cache()
    r2 = run_build(env.backend, ORG, settings=env.settings)
    assert r2["status"] == "ready"
    # 清队（fixture 首建/本次构建投递的 retag）——隔离验证 body 自身投递面
    env.db.execute("DELETE FROM tasks WHERE type = 'semantic_retag'")

    body = MAINTENANCE_BODIES["semantic_reconcile"]
    stats = body(env.backend, None, env.settings, NOW)
    ours = next(r for r in stats["orgs"] if r["org_id"] == ORG)
    assert ours["lagging_chunks"] >= 1
    assert stats["retag_enqueued"] == [ORG], "落后 org 须补投 semantic_retag"
    pending = env.db.execute(
        "SELECT type, payload, status FROM tasks WHERE type = 'semantic_retag'"
    ).fetchall()
    assert any(json.loads(p[1])["org"] == ORG and p[2] == "pending"
               for p in pending), "semantic_retag 任务行在队"

    # 防线一：在队不重复投递（pending 去重）
    stats2 = body(env.backend, None, env.settings, NOW)
    assert stats2["retag_enqueued"] == [], "在队不重复投递（幂等半句）"

    # 防线二：retag done 收敛（lagging 清零）→ 无投递理由
    from knowledge_lattice.core.semantic.tagging import run_retag_task

    task_id = env.db.execute(
        "SELECT id FROM tasks WHERE type = 'semantic_retag' AND status = 'pending'"
    ).fetchall()[0][0]
    run_retag_task(env.backend, env.settings, task_id)
    stats3 = body(env.backend, None, env.settings, NOW)
    assert stats3["retag_enqueued"] == [], "收敛（lagging=0）后无投递理由"
    ours3 = next(r for r in stats3["orgs"] if r["org_id"] == ORG)
    assert ours3["lagging_chunks"] == 0


def test_a5_reconcile_throttle_after_done_retag(env) -> None:
    """节流防线：无行块（untagged——重标不消候选）+ 该 org 近期已有 done
    retag → 窗口内不重复投（24h——G-19 每日兜底同款节奏；防无行块反复
    全扫投递风暴）。"""
    from knowledge_lattice.core.semantic.tagging import enqueue_retag, \
        run_retag_task
    from knowledge_lattice.worker.maintenance import MAINTENANCE_BODIES

    # 无 tagger 摄取一块（无行——untagged 面）
    from fake_providers import FakeEmbedder
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.ingest import IngestService

    doc, t1 = _ingest(env, "与词典完全无关的日常内容。")
    IngestService(
        env.backend, FakeEmbedder(dim=8, model_name="fake-embed"),
        env.settings, EmbeddingGate(), env.tmp / "objects").run_task(t1)
    env.db.execute("DELETE FROM tasks WHERE type = 'semantic_retag'")

    # 近期 done 的 retag（节流锚——dict_rev 用 current ready rev）
    current = env.backend.sem_current_build(ORG)
    assert current is not None
    tid = env.backend.create_task(
        None, task_type="semantic_retag",
        payload=json.dumps({"org": ORG, "dict_rev": current["dict_rev"]}))
    run_retag_task(env.backend, env.settings, tid)

    body = MAINTENANCE_BODIES["semantic_reconcile"]
    stats = body(env.backend, None, env.settings, NOW)
    ours = next(r for r in stats["orgs"] if r["org_id"] == ORG)
    assert ours["untagged_chunks"] >= 1
    assert stats["retag_enqueued"] == [] and ORG in stats["retag_throttled"], \
        "done retag 后节流窗口内不因无行块重复投（防风暴）"
