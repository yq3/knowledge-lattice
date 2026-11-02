"""M2-S3/m2s-5 ingest 同事务打标（TC-TAG-01 + A1 纯人工实体命中）。

- ① tag 行与块写入**同一事务**（index_fts 阶段——sem_tags 经 backend.insert
  事务内落 sem_chunk_entities；造中途失败断言同回滚）；
- ② 打标失败**不阻断 ingest**（捕获 + warning + `semantic.tag_failed` 审计
  ——文档先可用，标后补：块进入 retag 候选集〔无行=dict_rev 落后比对面，
  附录 A-14 口径〕交 semantic_retag 补做）；
- restricted 实体不落标（T-S9 一致——Annotator 不入机，tag 行零出现）；
- A1：YAML 纯人工 concept 实体（无系统源）入快照/build 产物、annotate 与
  打标双面可命中（corpus 校验面 m2s-3 已交付——TC-YAML-01 纯人工行）。
"""

from __future__ import annotations

import json

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"


@pytest.fixture()
def tag_env(backend, tmp_path):
    """打标链测试栈：matrix 造数 + 真 backend + FakeEmbedder + 语义词典
    （sync+build 就位）+ tagger 注入的 IngestService 工厂。"""
    from types import SimpleNamespace

    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.core.semantic.tagging import make_ingest_tagger

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    b = backend.make_backend()

    recs = [
        EntityRecord(type="concept", key="vat.input_credit", name="进项税额抵扣"),
    ]
    run_sync(b, ORG, FakeSourceAdapter("template_center", recs),
             settings=settings, snapshot=list(recs), now=NOW)
    # restricted 面（覆盖层 sensitivity: restricted——打标不落标的 T-S9 面）
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    repo = tmp_path / "yamlrepo"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "secret.yaml").write_text(
        "- id: concept:vat.secret\n  owner: o\n"
        "  aliases: [内部税收筹划方案]\n  sensitivity: restricted\n",
        encoding="utf-8")
    run_yaml_sync(b, ORG, YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=settings, now=NOW)

    clear_annotator_cache()
    result = run_build(b, ORG, settings=settings)
    assert result["status"] == "ready", result

    return SimpleNamespace(db=backend, backend=b, settings=settings,
                           build=result, repo=tmp_path)


def _make_service(env):
    from fake_providers import FakeEmbedder
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.semantic.tagging import make_ingest_tagger

    return IngestService(
        env.backend, FakeEmbedder(dim=8, model_name="fake-embed"),
        env.settings, EmbeddingGate(), env.settings.data_dir / "objects",
        tagger=make_ingest_tagger(env.backend, env.settings),
    )


def _upload_and_ingest(env, *, content: bytes, title="打标文档",
                       doc_id=None, owner="u_full"):
    """矩阵造数（上传校验前提）+ 上传 + 执行任务——返回 (doc_id, task_id)。"""
    from helpers import (dim_id_for, seed_dataset, seed_dimension, seed_dim_value,
                         seed_grant, seed_membership, seed_user, val_id_for)

    db = env.db
    if not db.execute("SELECT 1 FROM dimensions WHERE org_id = ? AND key = 'region'",
                      (ORG,)).fetchone():
        seed_dataset(db, ORG, "ds:vat_lib")
        seed_dimension(db, ORG, "region")
        seed_dim_value(db, dim_id_for(ORG, "region"), "CN")
        seed_dim_value(db, dim_id_for(ORG, "region"), "OS")
        seed_user(db, owner)
        seed_membership(db, owner, ORG)
        for v in ("CN", "OS"):
            seed_grant(db, user_id=owner, dim_id=dim_id_for(ORG, "region"),
                       val_id=val_id_for(ORG, "region", v))
    service = _make_service(env)
    return service.create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title=title,
        dims={"region": ["CN"]}, owner_user_id=owner,
        file_bytes=content, mime_type="text/plain",
        filename="doc.txt", doc_id=doc_id,
    )


def _tag_rows(env, doc_id):
    return env.db.execute(
        "SELECT chunk_rid, entity_id, hits, dict_rev FROM sem_chunk_entities"
        " WHERE doc_id = ? ORDER BY chunk_rid, entity_id",
        (doc_id,),
    ).fetchall()


# ---- TC-TAG-01①：tag 行与块写入同事务 ----


def test_tc_tag_01_ingest_tags_in_index_fts_transaction(tag_env) -> None:
    """正常摄取含命中词文档：sem_chunk_entities 行随 index_fts 事务落库
    （chunk_rid 对应真实块行、dict_rev=打标时 current build rev、hits 计数）。"""
    content = "本月进项税额抵扣的口径说明。".encode("utf-8")
    doc_id, task_id = _upload_and_ingest(tag_env, content=content)
    _make_service(tag_env).run_task(task_id)

    rows = _tag_rows(tag_env, doc_id)
    assert rows, "摄取后应落语义标行（TC-TAG-01①）"
    eid = tag_env.backend.resolve_entity_ids(
        ORG, [("concept", "vat.input_credit")])[("concept", "vat.input_credit")]
    assert [(r[1], r[2]) for r in rows] == [(eid, 1)]
    assert rows[0][3] == tag_env.build["dict_rev"]
    # chunk_rid 对应真实活跃块
    rid = rows[0][0]
    chunk = tag_env.db.execute(
        "SELECT doc_id, version, tombstone FROM chunks WHERE rid = ?", (rid,)
    ).fetchone()
    assert chunk and chunk[0] == doc_id and chunk[1] == 1 and chunk[2] == 0


def test_tc_tag_01_restricted_entity_not_tagged(tag_env) -> None:
    """restricted 实体别名出现在块中亦不落标（T-S9——打标面与 annotate 同口径）。"""
    content = "内部税收筹划方案的执行细则。".encode("utf-8")
    doc_id, task_id = _upload_and_ingest(tag_env, content=content,
                                         title="机密文档")
    _make_service(tag_env).run_task(task_id)
    assert _tag_rows(tag_env, doc_id) == [], "restricted 实体不得落标（T-S9）"


def test_tc_tag_01_rollback_blocks_and_tags_together(tag_env,
                                                     monkeypatch) -> None:
    """同事务回滚证据：事务中途失败（标签行 FK 违例——entity_id 指向不存在实体）
    → 块与 tag 行**同回滚**（chunks 零行、sem_chunk_entities 零行）。"""
    content = "本月进项税额抵扣的口径说明。".encode("utf-8")
    doc_id, task_id = _upload_and_ingest(tag_env, content=content)
    service = _make_service(tag_env)

    real_insert = tag_env.backend.insert

    def _insert_with_bad_tag(doc, version, chunks, *, sem_tags=None, **kw):
        assert sem_tags and sem_tags["rows"], "打标行应在事务前算好传入"
        bad = {"dict_rev": sem_tags["dict_rev"],
               "rows": [(sem_tags["rows"][0][0], 999999999, 1)]}
        return real_insert(doc, version, chunks, sem_tags=bad, **kw)

    monkeypatch.setattr(tag_env.backend, "insert", _insert_with_bad_tag)
    with pytest.raises(Exception):   # FK/约束违例——事务回滚
        service.run_task(task_id)
    monkeypatch.undo()

    # 块与标同生共死（任务 failed、版本块已按 T8 物理删——零残留）
    assert tag_env.db.execute(
        "SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)).fetchone()[0] == 0
    assert _tag_rows(tag_env, doc_id) == []


def test_tc_tag_01_tagging_failure_does_not_block_ingest(tag_env,
                                                         monkeypatch) -> None:
    """打标面抛错（mock AC 自动机）：摄取**不阻断**——文档照常 searchable、
    零 tag 行（dict_rev 落后面 = retag 候选集）、`semantic.tag_failed` 入
    audit_outbox（warning + 审计——TC-TAG-01②）。"""
    from knowledge_lattice.core.semantic import tagging

    def _boom(*a, **kw):
        raise RuntimeError("injected automaton failure")

    monkeypatch.setattr(tagging, "get_annotator", _boom)
    content = "本月进项税额抵扣的口径说明。".encode("utf-8")
    doc_id, task_id = _upload_and_ingest(tag_env, content=content)
    _make_service(tag_env).run_task(task_id)      # 不 raise——失败不阻断

    task = tag_env.backend.get_task(task_id)
    assert task["status"] == "done", "打标失败不得阻断 ingest（TC-TAG-01②）"
    doc = tag_env.backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_full"
    assert _tag_rows(tag_env, doc_id) == []
    events = tag_env.db.execute(
        "SELECT event_type, payload_json FROM audit_outbox"
        " WHERE event_type = 'semantic.tag_failed'").fetchall()
    assert events, "打标失败须落 semantic.tag_failed 审计"
    payload = json.loads(events[0][1])
    assert payload["doc_id"] == doc_id


def test_tc_tag_01_no_build_tags_skipped_silently(tag_env) -> None:
    """无构建（org 无 ready build）→ 打标静默跳过（不告警——「先构建再识别」
    操作序为部署形态而非失败；块无行，后续构建+retag 补做）。"""
    content = "本月进项税额抵扣的口径说明。".encode("utf-8")
    # 另一 org：无语义构建
    from helpers import (dim_id_for, seed_dataset, seed_dimension, seed_dim_value,
                         seed_grant, seed_membership, seed_user, val_id_for)

    from fake_providers import FakeEmbedder
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.semantic.tagging import make_ingest_tagger

    seed_org(tag_env.db, "org:gl2")
    seed_dataset(tag_env.db, "org:gl2", "ds:gl2")
    seed_dimension(tag_env.db, "org:gl2", "region")
    seed_dim_value(tag_env.db, dim_id_for("org:gl2", "region"), "CN")
    seed_user(tag_env.db, "u_gl2")
    seed_membership(tag_env.db, "u_gl2", "org:gl2")
    seed_grant(tag_env.db, user_id="u_gl2", dim_id=dim_id_for("org:gl2", "region"),
               val_id=val_id_for("org:gl2", "region", "CN"))
    service = IngestService(
        tag_env.backend, FakeEmbedder(dim=8, model_name="fake-embed"),
        tag_env.settings, EmbeddingGate(),
        tag_env.settings.data_dir / "objects",
        tagger=make_ingest_tagger(tag_env.backend, tag_env.settings),
    )
    doc_id, task_id = service.create_document(
        org_id="org:gl2", dataset_id="ds:gl2", title="gl2",
        dims={"region": ["CN"]}, owner_user_id="u_gl2",
        file_bytes=content, mime_type="text/plain", filename="d.txt")
    service.run_task(task_id)
    assert tag_env.backend.get_task(task_id)["status"] == "done"
    assert _tag_rows(tag_env, doc_id) == []
    assert tag_env.db.execute(
        "SELECT COUNT(*) FROM audit_outbox WHERE event_type = 'semantic.tag_failed'"
    ).fetchone()[0] == 0, "无构建是操作序形态——不告警不审计"


# ---- A1：YAML 纯人工 concept 实体（无系统源）打标/识别双面命中 ----


def test_a1_pure_concept_entity_in_snapshot_and_tagging(tag_env) -> None:
    """concepts/ 纯人工 concept（无系统源）：入快照/build 产物、annotate 命中、
    ingest 打标落行（A1——m2s-3 管线已就位，本段验收打标面收口）。"""
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.annotator import (
        annotate_text, clear_annotator_cache,
    )
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    repo = tag_env.repo / "repo2"
    (repo / "concepts").mkdir(parents=True)
    (repo / "concepts" / "pure.yaml").write_text(
        "- id: concept:vat.pure_manual\n  name: 纯人工业务概念\n"
        "  aliases: [人工概念面]\n  definition: 无系统源的人工概念。\n"
        "  owner: tax-domain\n",
        encoding="utf-8")
    run_yaml_sync(tag_env.backend, ORG,
                  YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=tag_env.settings, now=NOW, force=True)
    clear_annotator_cache()
    r2 = run_build(tag_env.backend, ORG, settings=tag_env.settings)
    assert r2["status"] == "ready"

    # 快照/build 产物包含纯人工实体（source='curated'）
    snap = tag_env.backend.sem_active_snapshot(ORG)
    pure = [e for e in snap["entities"] if e["key"] == "vat.pure_manual"]
    assert pure, "纯人工 concept 须入快照"
    # annotate 可命中（concept 类）
    out = annotate_text(tag_env.backend, tag_env.settings, ORG, "人工概念面的说明")
    assert out["mentions"] and out["mentions"][0]["type"] == "concept"
    # ingest 打标落行
    doc_id, task_id = _upload_and_ingest(
        tag_env, content="人工概念面的业务口径说明。".encode("utf-8"),
        title="纯人工概念文档")
    _make_service(tag_env).run_task(task_id)
    rows = _tag_rows(tag_env, doc_id)
    eid = tag_env.backend.resolve_entity_ids(
        ORG, [("concept", "vat.pure_manual")])[("concept", "vat.pure_manual")]
    assert (eid, 1) in [(r[1], r[2]) for r in rows]


# ---- 用户裁定①（2026-10-31）：歧义 mention 打标 skip（fail-closed） ----


def test_ruling_1_ambiguous_mentions_skipped_when_tagging(tag_env) -> None:
    """裁定①：`ambiguous=true` 的 mention **不落标**（消歧未定案不贴——
    fail-closed；防未来实体召回用未定案证据）；消歧定案（共现①/default⑤）
    的对照命中照常落标。"""
    from fake_semantic import FakeSourceAdapter
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync

    # 共享别名「歧面」双实体（无 default 声明、无关系——无佐证必歧义）；
    # 既有实体随快照保留（删除比例保护——per-source active 基数）
    base = EntityRecord(type="concept", key="vat.input_credit",
                        name="进项税额抵扣")
    recs = [
        base,
        EntityRecord(type="concept", key="amb.a", name="歧义甲",
                     aliases=("歧面",)),
        EntityRecord(type="concept", key="amb.b", name="歧义乙",
                     aliases=("歧面",)),
    ]
    run_sync(tag_env.backend, ORG, FakeSourceAdapter("template_center", recs),
             settings=tag_env.settings, snapshot=list(recs), now=NOW)

    from knowledge_lattice.core.semantic.annotator import (
        clear_annotator_cache, get_annotator,
    )
    from knowledge_lattice.core.semantic.build import run_build

    clear_annotator_cache()
    r = run_build(tag_env.backend, ORG, settings=tag_env.settings)
    assert r["status"] == "ready"

    # ① 无佐证文本：annotate 返回 ambiguous=true → 打标 skip（零行）
    ann, rev = get_annotator(tag_env.backend, ORG, tag_env.settings)
    mentions = ann.annotate("歧面的说明")["mentions"]
    assert mentions and mentions[0]["ambiguous"] is True, "前置：无佐证歧义"
    doc1, t1 = _upload_and_ingest(tag_env, content="歧面的说明。".encode(),
                                  title="歧义文档")
    _make_service(tag_env).run_task(t1)
    assert _tag_rows(tag_env, doc1) == [], \
        "ambiguous=true 不得落标（裁定① skip——消歧未定不贴）"

    # ② 对照：同句关系佐证（甲乙 related）消歧定案 → 落标
    from knowledge_lattice.core.semantic.records import RelationRecord

    recs2 = [
        base,
        EntityRecord(type="concept", key="amb.a", name="歧义甲",
                     aliases=("歧面",)),
        EntityRecord(type="concept", key="amb.b", name="歧义乙",
                     aliases=("歧面",)),
        RelationRecord(src=("concept", "amb.a"), rel_type="related_to",
                       dst=("concept", "amb.b")),
    ]
    run_sync(tag_env.backend, ORG, FakeSourceAdapter("template_center", recs2),
             settings=tag_env.settings, snapshot=list(recs2), now=NOW)
    clear_annotator_cache()
    r2 = run_build(tag_env.backend, ORG, settings=tag_env.settings)
    assert r2["status"] == "ready"
    ann2, _ = get_annotator(tag_env.backend, ORG, tag_env.settings)
    # 同句含确定命中「歧义乙」（规范名）→ 共现①把「歧面」定到 amb.a
    out = ann2.annotate("歧面与歧义乙的关系")
    face = next(m for m in out["mentions"] if m["surface"] == "歧面")
    assert face["resolved_by"] == "cooccurrence" and not face["ambiguous"]
    doc2, t2 = _upload_and_ingest(
        tag_env, content="歧面与歧义乙的关系说明。".encode(), title="消歧文档")
    _make_service(tag_env).run_task(t2)
    rows = _tag_rows(tag_env, doc2)
    eid_a = tag_env.backend.resolve_entity_ids(
        ORG, [("concept", "amb.a")])[("concept", "amb.a")]
    assert (eid_a, 1) in [(r[1], r[2]) for r in rows], \
        "消歧定案（cooccurrence）的命中照常落标（对照）"
