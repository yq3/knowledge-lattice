"""M2-S3/m2s-5 semantic_retag（TC-TAG-02 + TC-BUILD-05 + worker 接线）。

- TC-BUILD-05（消费面收口）：构建涉及**别名增删** → 投递 semantic_retag
  （dict_rev 落后块重标）；仅改 definition → 不投递（避免无谓重标风暴）；
- TC-TAG-02：词典 r1→r2（别名增删）后跑 retag——仅 dict_rev 落后的块分批
  重标；retag 后 dict_rev 字段更新；任务优先级最低（认领排序尾部——不与
  ingest 抢资源）；打标失败遗留的无行块（retag 候选集）一并补标。
"""

from __future__ import annotations

import json

import pytest

from helpers import (dim_id_for, seed_dataset, seed_dimension, seed_dim_value,
                     seed_grant, seed_membership, seed_org, seed_user,
                     val_id_for)

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

    def sync(records, **kw):
        return run_sync(b, ORG, FakeSourceAdapter("template_center", records),
                        settings=settings, snapshot=list(records), now=NOW, **kw)

    def build(**kw):
        clear_annotator_cache()
        return run_build(b, ORG, settings=settings, **kw)

    recs = [EntityRecord(type="concept", key="vat.input_credit",
                         name="进项税额抵扣")]
    sync(recs)
    r1 = build()
    assert r1["status"] == "ready"

    # 矩阵上传前提
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
                           sync=sync, build=build, r1=r1, tmp=tmp_path)


def _make_service(env):
    """带 tagger 的 IngestService（P2-3/R2：retag 测试栈打标链真实触达）。"""
    from fake_providers import FakeEmbedder
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.core.semantic.tagging import make_ingest_tagger

    return IngestService(
        env.backend, FakeEmbedder(dim=8, model_name="fake-embed"),
        env.settings, EmbeddingGate(), env.tmp / "objects",
        tagger=make_ingest_tagger(env.backend, env.settings))


def _ingest_doc(env, content: str, *, doc_id=None):
    service = _make_service(env)
    return service.create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="t",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=content.encode("utf-8"), mime_type="text/plain",
        filename="doc.txt", doc_id=doc_id)


def _run_task(env, task_id):
    """带 tagger 的执行（P2-3/R2：复用 _make_service——打标链真实触达；
    「无行块」形态由用例显式构造无 tagger service，不在本 helper 隐含）。"""
    _make_service(env).run_task(task_id)


def _retag_tasks(env):
    return env.db.execute(
        "SELECT id, payload, status FROM tasks WHERE type = 'semantic_retag'"
        " ORDER BY created_at, id").fetchall()


# ---- TC-BUILD-05：别名增删 diff 才投递（构建面判定——消费面收口） ----


def test_tc_build_05_alias_diff_enqueues_retag(env) -> None:
    """① 别名增删构建 → 投递 semantic_retag（payload 携 dict_rev=新 rev）；
    ② 仅改 definition（YAML 覆盖层）构建 → 不投递（无别名面变化）。"""
    from knowledge_lattice.core.semantic.records import EntityRecord

    # ① 别名增删（sync 源新增 aliases）
    env.sync([EntityRecord(type="concept", key="vat.input_credit",
                           name="进项税额抵扣", aliases=("进项面",))])
    r2 = env.build()
    assert r2["status"] == "ready"
    tasks = _retag_tasks(env)
    assert len(tasks) == 2, "首建 + 别名增删各投一条 semantic_retag（TC-BUILD-05）"
    # tasks.id 为 uuid 文本（created_at 同秒并列序不可依赖）——按 payload 定位
    r2_task = next(t for t in tasks
                   if json.loads(t[1])["dict_rev"] == r2["dict_rev"])
    payload = json.loads(r2_task[1])
    assert payload["org"] == ORG and payload["dict_rev"] == r2["dict_rev"]
    assert r2_task[2] == "pending"

    # ② 仅改 definition（纯人工条目——curated 面变化、别名面不动）→ 不投递
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    repo = env.tmp / "yamlrepo"
    (repo / "concepts").mkdir(parents=True, exist_ok=True)
    (repo / "concepts" / "c.yaml").write_text(
        "- id: concept:vat.pure_def\n  name: 定义变化条目\n"
        "  definition: 初版口径定义正文。\n  owner: tax-domain\n",
        encoding="utf-8")
    run_yaml_sync(env.backend, ORG,
                  YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=env.settings, now=NOW, force=True)
    r_mid = env.build()
    assert r_mid["status"] == "ready" and r_mid["dict_rev"] != r2["dict_rev"]
    baseline = len(_retag_tasks(env))       # ②前的投递基数

    (repo / "concepts" / "c.yaml").write_text(
        "- id: concept:vat.pure_def\n  name: 定义变化条目\n"
        "  definition: 新版口径定义正文（仅 definition 变化）。\n"
        "  owner: tax-domain\n",
        encoding="utf-8")
    run_yaml_sync(env.backend, ORG,
                  YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=env.settings, now=NOW, force=True)
    r3 = env.build()
    assert r3["status"] == "ready" and r3["dict_rev"] != r_mid["dict_rev"]
    assert len(_retag_tasks(env)) == baseline, \
        "仅改 definition 不得投递 retag（防风暴——TC-BUILD-05②）"


def test_tc_build_05_first_build_enqueues_for_legacy_blocks(env) -> None:
    """首建（无 prev）投递面：宁投勿漏——首建前摄取的块（无 ready build 期
    的无行块）由首建投递的 retag 补标；无块时零候选幂等（无风暴——任务
    一次 done 收尾）。"""
    tasks = _retag_tasks(env)
    assert tasks, "首建（r1）即投递（prev 缺省视为变化——补标存量无行块）"
    assert json.loads(tasks[0][1])["dict_rev"] == env.r1["dict_rev"]


# ---- TC-TAG-02：retag 执行体 ----


def test_tc_tag_02_retag_retags_only_lagging_blocks(env) -> None:
    """词典 r1→r2（别名增删）后跑 retag：仅 dict_rev 落后块重标（已同 rev 的
    块不动——零候选收敛）；retag 后 dict_rev 字段更新为新 rev。

    P2-3/R2：栈接 tagger——r1 已打标为**真实前置**（断言 tag 行非空，
    非无行块补标形态）。"""
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.tagging import run_retag_task

    doc1, t1 = _ingest_doc(env, "本月进项税额抵扣的口径说明。")
    _run_task(env, t1)
    doc2, t2 = _ingest_doc(env, "完全无关的日常内容记录。")
    _run_task(env, t2)
    # r1 已打标（前置——P2-3：真实「落后块」而非无行块）
    r1_rows = env.db.execute(
        "SELECT chunk_rid FROM sem_chunk_entities WHERE doc_id = ?", (doc1,)
    ).fetchall()
    assert r1_rows, "前置：r1 词典下 doc1 已打标（tagger 接线）"

    # r2：别名增删（进项面——新识别面）+ 投递
    env.sync([EntityRecord(type="concept", key="vat.input_credit",
                           name="进项税额抵扣", aliases=("进项面",))])
    r2 = env.build()
    assert r2["status"] == "ready"
    task_rows = _retag_tasks(env)
    assert task_rows, "别名增删构建须投递 retag"
    r2_task = next(t for t in task_rows
                   if json.loads(t[1])["dict_rev"] == r2["dict_rev"])

    result = run_retag_task(env.backend, env.settings, r2_task[0])
    assert result["chunks_retagged"] >= 1
    # retag 后 dict_rev 字段更新（TC-TAG-02 预期半句）
    revs = env.db.execute(
        "SELECT DISTINCT dict_rev FROM sem_chunk_entities WHERE org_id = ?",
        (ORG,)).fetchall()
    assert revs and all(r[0] == r2["dict_rev"] for r in revs), \
        "落后块重标后 dict_rev 更新为新 rev"
    assert env.backend.get_task(r2_task[0])["status"] == "done"

    # 新识别面生效：全部**有行**块 dict_rev 追平 r2（无行块〔无命中〕不消
    # 候选——恒为 retag 候选，防风暴靠对账节流，见 test_tag_03）
    lagging_rows = env.db.execute(
        "SELECT COUNT(*) FROM sem_chunk_entities WHERE org_id = ?"
        " AND dict_rev != ?", (ORG, r2["dict_rev"])).fetchone()[0]
    assert lagging_rows == 0, "落后块重标后 dict_rev 全部追平（幂等收敛）"


def test_tc_tag_02_retag_picks_up_untagged_blocks(env) -> None:
    """打标失败/无构建期遗留的**无行块**（retag 候选集——附录 A-14 口径）
    由 retag 补标。"""
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.tagging import run_retag_task

    # 无 tagger 摄取（旧构造形态）→ 块无标行
    doc, t1 = _ingest_doc(env, "本月进项税额抵扣的口径说明。")
    from fake_providers import FakeEmbedder
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.ingest import IngestService

    plain = IngestService(
        env.backend, FakeEmbedder(dim=8, model_name="fake-embed"),
        env.settings, EmbeddingGate(), env.tmp / "objects")
    plain.run_task(t1)
    assert env.db.execute(
        "SELECT COUNT(*) FROM sem_chunk_entities WHERE doc_id = ?",
        (doc,)).fetchone()[0] == 0

    # r2 + retag → 无行块补标
    env.sync([EntityRecord(type="concept", key="vat.input_credit",
                           name="进项税额抵扣", aliases=("进项面",))])
    r2 = env.build()
    task_rows = _retag_tasks(env)
    r2_task = next(t for t in task_rows
                   if json.loads(t[1])["dict_rev"] == r2["dict_rev"])
    run_retag_task(env.backend, env.settings, r2_task[0])
    rows = env.db.execute(
        "SELECT dict_rev FROM sem_chunk_entities WHERE doc_id = ?", (doc,)
    ).fetchall()
    assert rows and all(r[0] == r2["dict_rev"] for r in rows), \
        "无行块（打标失败/无构建期）由 retag 补标"


# ---- P1（R1 Committer）：零命中候选块的旧标清理（别名删除/restricted 化） ----


def test_p1_alias_deleted_retag_clears_stale_tags(env) -> None:
    """P1 回归（删侧）：r1 借别名 A 打标 → r2 **删除**别名 A（别名面收缩）
    → retag 重标该块零命中 → 旧 tag 行必须清零（整替语义；lagging 收敛，
    不残留已删别名的召回证据）。"""
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.tagging import run_retag_task

    # r1：带别名「进项面」（块内容只含别名面——规范名不在块内，保证 r2 删
    # 别名后 annotate 零命中）
    env.sync([EntityRecord(type="concept", key="vat.input_credit",
                           name="进项税额抵扣", aliases=("进项面",))])
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build

    clear_annotator_cache()
    r1 = env.build()
    assert r1["status"] == "ready"

    doc, t1 = _ingest_doc(env, "进项面的业务口径说明。")
    _run_task(env, t1)
    rows = env.db.execute(
        "SELECT chunk_rid, dict_rev FROM sem_chunk_entities WHERE doc_id = ?",
        (doc,)).fetchall()
    assert rows, "前置：r1 借别名「进项面」打标成功"
    assert rows[0][1] == r1["dict_rev"]

    # r2：别名删除（sync 不带「进项面」——别名面收缩）
    env.sync([EntityRecord(type="concept", key="vat.input_credit",
                           name="进项税额抵扣")])
    r2 = env.build()
    assert r2["status"] == "ready" and r2["dict_rev"] != r1["dict_rev"]
    r2_task = next(t for t in _retag_tasks(env)
                   if json.loads(t[1])["dict_rev"] == r2["dict_rev"])

    result = run_retag_task(env.backend, env.settings, r2_task[0])
    assert result["chunks_retagged"] >= 1
    # P1 断言：零命中块旧标清零（修复前残留 r1 行——整替语义不成立）
    assert env.db.execute(
        "SELECT COUNT(*) FROM sem_chunk_entities WHERE doc_id = ?",
        (doc,)).fetchone()[0] == 0, "别名删除后 retag 须清旧标（P1）"
    # lagging 收敛（残留行会使 lagging 永不归零）
    report = env.backend.sem_reconcile_chunk_tags()
    ours = next(r for r in report if r["org_id"] == ORG)
    assert ours["lagging_chunks"] == 0


def test_p1_restricted_migration_retag_clears_stale_tags(env) -> None:
    """P1 对称面：r1 实体 normal 打标 → r2 sensitivity 改 restricted（自动机
    不收——T-S9 识别面收缩）→ retag 零命中 → 旧标清零（防 restricted 实体
    经存量 tag 行残留召回证据）。实体走**纯人工** YAML（concepts/ 覆盖层
    撞同步实体会被规则表第 3 行剔除——restricted 只能 YAML 声明）。"""
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.tagging import run_retag_task
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    repo = env.tmp / "yamlrepo_r"
    (repo / "concepts").mkdir(parents=True)
    # r1：纯人工实体（未声明 sensitivity → normal——B3④ 口径）
    (repo / "concepts" / "secret.yaml").write_text(
        "- id: concept:vat.secret\n  name: 内部税收筹划方案\n  owner: o\n"
        "  aliases: [内部税收筹划方案]\n",
        encoding="utf-8")
    run_yaml_sync(env.backend, ORG,
                  YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=env.settings, now=NOW)
    clear_annotator_cache()
    r1 = env.build()
    assert r1["status"] == "ready", r1

    doc, t1 = _ingest_doc(env, "内部税收筹划方案的执行细则。")
    _run_task(env, t1)
    assert env.db.execute(
        "SELECT COUNT(*) FROM sem_chunk_entities WHERE doc_id = ?",
        (doc,)).fetchone()[0] == 1, "前置：r1（normal）打标成功"

    # r2：同条目改 restricted（覆盖层在场声明——sensitivity 回写生效）
    (repo / "concepts" / "secret.yaml").write_text(
        "- id: concept:vat.secret\n  name: 内部税收筹划方案\n  owner: o\n"
        "  aliases: [内部税收筹划方案]\n  sensitivity: restricted\n",
        encoding="utf-8")
    run_yaml_sync(env.backend, ORG,
                  YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=env.settings, now=NOW)
    clear_annotator_cache()
    r2 = env.build()
    assert r2["status"] == "ready" and r2["dict_rev"] != r1["dict_rev"]
    # sensitivity 变化不动别名面——构建面不投（TC-BUILD-05）；补投走**对账
    # 兜底**（裁定③双层口径：构建侧防风暴、对账保证最终收敛）
    env.db.execute("DELETE FROM tasks WHERE type = 'semantic_retag'")
    from knowledge_lattice.worker.maintenance import MAINTENANCE_BODIES

    stats = MAINTENANCE_BODIES["semantic_reconcile"](
        env.backend, None, env.settings, NOW)
    assert stats["retag_enqueued"] == [ORG], "sensitivity 收缩经对账补投 retag"
    task_id = env.db.execute(
        "SELECT id FROM tasks WHERE type = 'semantic_retag'"
        " AND status = 'pending'").fetchall()[0][0]

    run_retag_task(env.backend, env.settings, task_id)
    assert env.db.execute(
        "SELECT COUNT(*) FROM sem_chunk_entities WHERE doc_id = ?",
        (doc,)).fetchone()[0] == 0, \
        "restricted 化后 retag 须清旧标（T-S9 存量残留面）"


# ---- worker 接线：认领类型 + 分发 + 最低优先级 ----

def test_runner_claimable_and_dispatches_semantic_retag(env) -> None:
    """CLAIMABLE_TASK_TYPES 含 semantic_retag；TaskRunner 认领并执行到终态。"""
    from knowledge_lattice.core.semantic.tagging import run_retag_task
    from knowledge_lattice.worker.runner import CLAIMABLE_TASK_TYPES, TaskRunner

    assert "semantic_retag" in CLAIMABLE_TASK_TYPES

    doc, t1 = _ingest_doc(env, "本月进项税额抵扣的口径说明。")
    from fake_providers import FakeEmbedder
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.core.docs.ingest import IngestService

    IngestService(
        env.backend, FakeEmbedder(dim=8, model_name="fake-embed"),
        env.settings, EmbeddingGate(), env.tmp / "objects").run_task(t1)
    from knowledge_lattice.core.semantic.records import EntityRecord

    env.sync([EntityRecord(type="concept", key="vat.input_credit",
                           name="进项税额抵扣", aliases=("进项面",))])
    env.build()
    task_row = _retag_tasks(env)[0]

    runner = TaskRunner(env.backend, env.settings)
    assert runner.run_once(), "retag 任务应被认领执行"
    assert env.backend.get_task(task_row[0])["status"] == "done", \
        "runner 分发 semantic_retag 到执行体（TC-TAG-02 联动）"


def test_retag_priority_lowest_behind_ingest(env) -> None:
    """最低优先级：ingest 与 retag 同时在队（retag 更早投递）→ 先认领 ingest
    （claim ORDER BY 尾部——不与 ingest 抢资源，design §5.3/D23）。"""
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.worker.runner import TaskRunner

    # retag 在队（先投递）
    env.sync([EntityRecord(type="concept", key="vat.input_credit",
                           name="进项税额抵扣", aliases=("进项面",))])
    env.build()
    retag_ids = {t[0] for t in _retag_tasks(env)}
    assert retag_ids

    # ingest 后投递（executors 覆盖为 no-op——认领序为断言面，执行面无关）
    _ingest_doc(env, "本月进项税额抵扣的口径说明。")
    ingest_row = env.db.execute(
        "SELECT id FROM tasks WHERE type = 'ingest' ORDER BY created_at"
    ).fetchall()[-1]

    runner = TaskRunner(env.backend, env.settings,
                        executors={"ingest": lambda task, claim: None})
    claimed = runner.run_once()
    assert claimed
    # 被认领的是 ingest（retag 排队尾）——认领证据：ingest 行离开 pending
    ingest_status = env.backend.get_task(ingest_row[0])["status"]
    retag_pending = [env.backend.get_task(t)["status"]
                     for t in retag_ids]
    assert ingest_status != "pending", "ingest 应先被认领"
    assert all(s == "pending" for s in retag_pending), \
        "retag 最低优先级（认领排序尾部）"
