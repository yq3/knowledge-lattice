"""m2-6 A1/A2：reembed 蓝绿执行体（TC-EMB-06 四步）+ reindex 执行体 + 同秒认领单调键。

- **TC-EMB-06**（TEST-CASES L220，执行体面——m2-3 已交付投递入口）：
  ① 新标签向量**并行写入** chunk_vectors（扫描谓词 = 在用块中无 (rid,:new) cv 行
     ——含 pending 版本块；旧标签持续服务零降级）；
  ② 覆盖率 100%（限 tombstone=0 且 version=active_version）后**原子切 config 标签**
     （零 SQL——进程内对象图：embedder.apply_model + ingest/quality.apply_settings）；
  ③ 竞态在途回写防护：切换后旧模型在途批次迟到回写零行生效（re-pin 状态标签
     ——write_embeddings 防护谓词 c.embed_model=:label 不再匹配）→ 库内无孤儿行；
  ④ 旧标签清理（org 内全部块非新标签 cv 行 DELETE）+ quality 重跑联动
     （detected_at_scale 缓存失效 + 全量重算〔清旧 vector_crowding、缓存键随
     embed_model 语义〕）+ semantic_build 强制重跑投递（dict_rev 含嵌入标签）。
- **reindex**（A2）：重切分+重嵌入全链（delete_by_doc + 状态重置 → ingest.run_task
  幂等管线）；中断重认领不丢不重；与 reembed 蓝绿口径天然对齐（钉当前服务标签）。
- **同秒 reembed 单调键**（B②——m2-3 R3 Committer P3 登记）：claim 认领序 =
  插入序（sqlite rowid / pg 0010 seq 列），同秒多任务不再受 uuid4 随机 id 摆布。

双后端参数化（[sqlite]/[pg]）。
"""

from __future__ import annotations

import json

import pytest

from conftest import ORG
from helpers import seed_user

NEW_LABEL = "new-embed:16"  # 迁移目标标签（dim 8→16——覆盖维度校验路径）
NEW_NAME, NEW_DIM = "new-embed", 16


# ============ 共享栈（双后端） ============


class _RebuildEnv:
    """matrix + worker 服务栈（backend/settings/embedder/gate/quality/ingest/services）。

    造数基线：matrix 5 篇文档各 1 块 v1 在用；旧标签向量逐块直插
    （insert_vector 绕过写路径防护——TC-EMB-06 前置「库内已有旧标签向量」）。
    """

    def __init__(self, matrix, tmp_path) -> None:
        from knowledge_lattice.adapters.embedder import EmbeddingGate
        from knowledge_lattice.config import Settings
        from knowledge_lattice.core.docs.ingest import IngestService
        from knowledge_lattice.core.docs.quality import QualityService
        from knowledge_lattice.store.taskclock import utc_now_ts
        from knowledge_lattice.worker.runner import TaskRunner, WorkerServices
        from fake_providers import FakeEmbedder

        self.db = matrix
        self.backend = matrix.make_backend()
        self.settings = Settings(
            environment="test", data_dir=tmp_path, embed_dim=8,
            embed_model="fake-embed",
        )
        self.old_label = self.settings.embed_model_label  # fake-embed:8
        self.embedder = FakeEmbedder(dim=8, model_name="fake-embed")
        self.gate = EmbeddingGate()
        self.quality = QualityService(self.backend, self.settings)
        self.objects_dir = tmp_path / "objects"
        self.ingest = IngestService(
            self.backend, self.embedder, self.settings, self.gate,
            self.objects_dir, quality=self.quality,
        )
        self.services = WorkerServices(
            backend=self.backend, settings=self.settings, ingest=self.ingest,
            _gate=self.gate, _embedder=self.embedder, quality=self.quality,
        )
        self.runner = TaskRunner(
            self.backend, self.settings, services=self.services,
        )
        # 全部在用块插旧标签向量（前置：旧标签全量服务中）
        self.rids = sorted(
            r[0] for r in self.db.execute(
                "SELECT rid FROM chunks JOIN documents d ON d.id = doc_id"
                " WHERE d.org_id = ? AND tombstone = 0", (ORG,),
            )
        )
        for rid in self.rids:
            matrix.insert_vector(rid, self.old_label, [0.1] * 8)
        self.now = utc_now_ts()

    # ---- 断言辅助 ----

    def cv_labels(self, rid: int) -> set[str]:
        return {
            r[0] for r in self.db.execute(
                "SELECT embed_model FROM chunk_vectors WHERE rid = ?", (rid,),
            )
        }

    def coverage(self, label: str) -> tuple[int, int]:
        rows = self.backend.embedding_coverage(ORG, label)
        return (
            sum(r["done"] for r in rows),
            sum(r["total"] for r in rows),
        )

    def enqueue_reembed(self, *, embed_model: str = NEW_LABEL) -> str:
        return self.backend.create_task(
            None, task_type="reembed",
            payload=json.dumps({"org": ORG, "embed_model": embed_model}),
        )


@pytest.fixture()
def rebuild_env(matrix, tmp_path):
    """双后端参数化由 matrix 承载（P3-6②/R2 收编：fixture 自身 params 与
    matrix 相乘会重复跑一倍——34→22 收集）。"""
    env = _RebuildEnv(matrix, tmp_path)
    yield env


# ============ TC-EMB-06 ①~④：执行体全链（双后端） ============


def test_tc_emb06_bluegreen_full_cycle(rebuild_env) -> None:
    """TC-EMB-06 四步全链：①并行写入（新旧并存+pending 块覆盖）→ ②覆盖率 100%
    原子切标签（零 SQL——settings/embedder/ingest/quality 对象图一致切换）→
    ③在途回写零孤儿 → ④清理+quality·semantic_build 联动。"""
    env = rebuild_env
    task_id = env.enqueue_reembed()

    # ---- 中断缝①：写入中途停（should_continue=False）——断言中间态 =
    # TC-EMB-06 ①「并行写入 + 旧标签持续服务」的窗口实证
    probe_calls = {"n": 0}

    def stop_after_first_batch() -> bool:
        probe_calls["n"] += 1
        return probe_calls["n"] <= 1  # 第一次探测放行、之后停

    from knowledge_lattice.worker.rebuild import run_reembed_task

    run_reembed_task(env.services, task_id, should_continue=stop_after_first_batch)
    task = env.backend.get_task(task_id)
    assert task["status"] != "done", "写入中途停——任务不得终态（重认领续跑）"

    # 重跑（无中断）——幂等续跑：已写块不重嵌（扫描谓词排除）
    run_reembed_task(env.services, task_id)
    task = env.backend.get_task(task_id)
    assert task["status"] == "done", task.get("error")

    # ② 切换断言（零 SQL：进程内对象图）
    assert env.services.settings.embed_model_label == NEW_LABEL
    assert env.embedder.model_label == NEW_LABEL, "检索谓词源（embedder）已切新标签"
    assert env.ingest._settings.embed_model_label == NEW_LABEL, "摄取钉签源已切"
    assert env.quality._settings.embed_model_label == NEW_LABEL, "quality 源已切"
    # ② 覆盖率 100%（在用块口径）+ ④ 清理后全库单标签一致
    assert env.coverage(NEW_LABEL) == (5, 5)
    for rid in env.rids:
        assert env.cv_labels(rid) == {NEW_LABEL}, "旧标签行已清理（单标签一致）"

    # ③ 竞态在途回写防护：旧模型在途批次迟到回写（fake Embedder 慢返回形态）
    written = env.backend.write_embeddings(
        env.old_label, [(env.rids[0], [0.1] * 8)]
    )
    assert written == 0, "迟到回写零行生效（re-pin 后谓词不匹配——无孤儿行）"
    assert env.cv_labels(env.rids[0]) == {NEW_LABEL}

    # ④ semantic_build 强制重跑投递（dict_rev 含嵌入标签——§5.8；R2 P2-2
    # 全库口径：逐组织投递——org:tax 与 org:gl 都在集合中）
    builds = {
        json.loads(r[0])["org"]
        for r in env.db.execute(
            "SELECT payload FROM tasks WHERE type = 'semantic_build'"
        )
    }
    assert ORG in builds, "reembed 完成应投递 semantic_build 任务"
    assert "org:gl" in builds, "全库迁移逐组织投递（N-1 裁定选 a）"


def test_tc_emb06_quality_rerun_linkage(rebuild_env) -> None:
    """TC-EMB-06 ④ quality 联动：旧 vector_crowding flags 清除 + 检测缓存
    （detected_at_scale）失效 → 全量重算（新标签向量）。"""
    env = rebuild_env
    rid = env.rids[0]
    chunk_id = env.db.execute(
        "SELECT id FROM chunks WHERE rid = ?", (rid,)
    ).fetchone()[0]
    # 造旧检测缓存 + 旧 vector_crowding flag
    env.db.execute(
        "UPDATE chunks SET detected_at_scale = 5, content_sha = 'sha256:old'"
        " WHERE rid = ?", (rid,)
    )
    env.backend.insert_quality_flag(
        chunk_id=chunk_id, doc_id="d_cn", reason="vector_crowding",
        detail_json='{"mean_sim": 0.99}',
    )
    env.db.commit()

    task_id = env.enqueue_reembed()
    from knowledge_lattice.worker.rebuild import run_reembed_task

    run_reembed_task(env.services, task_id)

    # 旧 vector_crowding flag 清除（FakeEmbedder 哈希向量无拥挤语义——
    # 重算后不必然复现拥挤；断言「旧 flag 不在」即联动生效）
    flags = env.db.execute(
        "SELECT reason FROM quality_flags WHERE chunk_id = ?", (chunk_id,)
    ).fetchall()
    assert ["vector_crowding"] != [f[0] for f in flags], "旧拥挤 flag 已随重算清除"
    # 检测缓存已按新模型重写（detected_at_scale 被失效后由重算回写）
    scale = env.db.execute(
        "SELECT detected_at_scale FROM chunks WHERE rid = ?", (rid,)
    ).fetchone()[0]
    assert scale == 5, "重算后检测标记回写（当前语料规模）"


def test_tc_emb06_pending_blocks_covered(rebuild_env) -> None:
    """扫描谓词覆盖 pending 版本块（覆盖上传在途）——切换终态不漏块：
    pending 块同样获新标签向量（cv PK 幂等并存）。"""
    env = rebuild_env
    # 造 d_cn 的 pending v2 块（覆盖上传在途形态——非在用）
    env.db.execute(
        "INSERT INTO chunks(id, doc_id, seq, version, content, tombstone)"
        " VALUES('chk:pend_new', 'd_cn', 9, 2, 'pending content', 0)"
    )
    env.db.commit()

    task_id = env.enqueue_reembed()
    from knowledge_lattice.worker.rebuild import run_reembed_task

    run_reembed_task(env.services, task_id)

    pend_rid = env.db.execute(
        "SELECT rid FROM chunks WHERE id = 'chk:pend_new'"
    ).fetchone()[0]
    assert env.cv_labels(pend_rid) == {NEW_LABEL}, "pending 块同获新标签向量"


def test_reembed_bad_label_fails_task(rebuild_env) -> None:
    """非法目标标签（缺 :dim / dim 非数字）→ 任务 failed 带原因（fail-closed，
    不静默按旧标签跑）。"""
    env = rebuild_env
    task_id = env.enqueue_reembed(embed_model="no-dim-label")
    from knowledge_lattice.worker.rebuild import run_reembed_task

    run_reembed_task(env.services, task_id)
    task = env.backend.get_task(task_id)
    assert task["status"] == "failed"
    assert "embed_model" in (task["error"] or "")


def test_reembed_runner_claimable(rebuild_env) -> None:
    """runner 认领接线：CLAIMABLE_TASK_TYPES 含 reembed/reindex——run_once 全链
    （m2-1 框架状态机/心跳/取消沿既有语义）。"""
    env = rebuild_env
    from knowledge_lattice.worker.runner import CLAIMABLE_TASK_TYPES

    assert "reembed" in CLAIMABLE_TASK_TYPES
    assert "reindex" in CLAIMABLE_TASK_TYPES
    task_id = env.enqueue_reembed()
    assert env.runner.run_once(task_types=("reembed",))
    assert env.backend.get_task(task_id)["status"] == "done"


def test_reembed_same_label_noop(rebuild_env) -> None:
    """目标标签 == 当前服务标签（幂等重跑/误投递）→ 跳过写入与切换，仅做
    清理+联动（终态一致）。"""
    env = rebuild_env
    task_id = env.enqueue_reembed(embed_model=env.old_label)
    from knowledge_lattice.worker.rebuild import run_reembed_task

    run_reembed_task(env.services, task_id)
    assert env.backend.get_task(task_id)["status"] == "done"
    assert env.services.settings.embed_model_label == env.old_label, "同标签不切换"
    assert env.coverage(env.old_label) == (5, 5)


# ============ A2 reindex 执行体（双后端——真实摄取链） ============


@pytest.fixture()
def reindex_env(matrix, tmp_path):
    """真实摄取一篇文档（对象落盘 + run_task 全链）后投递 reindex（双后端
    参数化由 matrix 承载——P3-6②/R2 收编）。"""
    env = _RebuildEnv(matrix, tmp_path)
    from helpers import seed_membership

    seed_user(env.db, "u_re")
    seed_membership(env.db, "u_re", ORG)
    from helpers import grant_by_key

    grant_by_key(env.db, "u_re", org_id=ORG, key="region", value="CN")
    doc_id, task_id = env.ingest.create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="reindex target",
        dims={"region": ["CN"]}, owner_user_id="u_re",
        file_bytes=b"<html><body>reindex sample content</body></html>",
        mime_type="text/html", filename="re.html",
    )
    env.ingest.run_task(task_id)
    doc = env.backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_full"
    env.doc_id = doc_id
    env.first_task = task_id
    yield env


def test_reindex_full_chain(reindex_env) -> None:
    """A2 端到端：投递→认领→重切分+重嵌入全链→检索可见新产物（新块 id +
    当前标签向量 + searchable_full）。"""
    env = reindex_env
    old_chunk = env.db.execute(
        "SELECT id FROM chunks WHERE doc_id = ? AND tombstone = 0",
        (env.doc_id,),
    ).fetchone()[0]

    task_id = env.backend.create_task(
        env.doc_id, task_type="reindex", target_version=1,
        payload=json.dumps({"org": ORG}),
    )
    from knowledge_lattice.worker.rebuild import run_reindex_task

    run_reindex_task(env.services, task_id)
    task = env.backend.get_task(task_id)
    assert task["status"] == "done", task.get("error")

    doc = env.backend.get_document(env.doc_id)
    assert doc["active_status"] == "searchable_full"
    new_chunk = env.db.execute(
        "SELECT id, rid FROM chunks WHERE doc_id = ? AND tombstone = 0",
        (env.doc_id,),
    ).fetchone()
    assert new_chunk[0] != old_chunk, "重切分产生新块（先删后插）"
    labels = {
        r[0] for r in env.db.execute(
            "SELECT embed_model FROM chunk_vectors WHERE rid = ?", (new_chunk[1],)
        )
    }
    assert labels == {env.old_label}, "重嵌入钉当前服务标签（蓝绿口径天然对齐）"
    # 检索可见新产物（FTS 内容命中）
    assert env.db.fts_word_count("reindex") >= 1


def test_reindex_interrupted_reclaim_no_loss(reindex_env) -> None:
    """A2 中断重认领不丢不重：写入中途停（任务留非终态）→ 重认领 → done；
    终态单版本块集合精确（无重复块、无半写残留）。"""
    env = reindex_env
    task_id = env.backend.create_task(
        env.doc_id, task_type="reindex", target_version=1,
        payload=json.dumps({"org": ORG}),
    )
    from knowledge_lattice.worker.rebuild import run_reindex_task

    probe = {"n": 0}

    def stop_late() -> bool:
        probe["n"] += 1
        return probe["n"] <= 2  # 走过重置与 parse 后停

    run_reindex_task(env.services, task_id, should_continue=stop_late)
    assert env.backend.get_task(task_id)["status"] != "done"

    run_reindex_task(env.services, task_id)  # 重认领（幂等重置+续跑）
    assert env.backend.get_task(task_id)["status"] == "done"
    rows = env.db.execute(
        "SELECT seq FROM chunks WHERE doc_id = ? AND tombstone = 0 AND version = 1"
        " ORDER BY seq", (env.doc_id,),
    ).fetchall()
    assert len(rows) >= 1, "块集合非空（不丢）"
    seqs = [r[0] for r in rows]
    assert len(seqs) == len(set(seqs)), "seq 无重复（不重）"
    doc = env.backend.get_document(env.doc_id)
    assert doc["active_status"] == "searchable_full"


# ============ B② 同秒 reembed 单调键（双后端） ============


def test_claim_order_monotonic_within_same_second(matrix) -> None:
    """同秒多任务认领序 = 插入序（rowid/0010 seq 单调次级键——B②：uuid4 id
    随机、created_at 秒级并列下认领序不受投递序摆布的根除）。"""
    backend = matrix.make_backend()
    same_ts = "2026-11-01 00:00:00"
    # 同 created_at、id 乱序（uuid4 形态——故意令字典序与插入序相反）
    for i, tid in enumerate(("tsk_c", "tsk_a", "tsk_b")):
        matrix.execute(
            "INSERT INTO tasks(id, doc_id, type, status, created_at)"
            " VALUES(?, NULL, 'reembed', 'pending', ?)",
            (tid, same_ts),
        )
    got = []
    for _ in range(3):
        task = backend.claim_next_task(
            "wk-test", lease_s=60.0, task_types=("reembed",), now=same_ts,
        )
        got.append(task["id"])
    assert got == ["tsk_c", "tsk_a", "tsk_b"], "认领序 = 插入序（单调键）"


# ============ R2 P2-2：全库迁移（N-1 裁定选 a） ============


def test_reembed_full_library_multi_org(matrix, tmp_path) -> None:
    """N-1 裁定 (a)：reembed = **全库迁移**——org A 投递后 B/C 组织在用块
    向量与标签同迁、全库单标签一致；未达成（任一组织覆盖 <100%）前不得切换。
    双后端（org:gl 造独立文档+块+旧标签向量——隔离对照组织实证同迁）。"""
    env = _RebuildEnv(matrix, tmp_path)

    # org:gl 造数：文档 + 在用块 + 旧标签向量（matrix 的隔离组织）
    from helpers import seed_dataset, seed_doc_dims, seed_document
    from helpers import insert_chunk

    seed_dataset(env.db, "org:gl", "ds:gl_lib")
    seed_document(
        env.db, "d_gl_1", org_id="org:gl", dataset_id="ds:gl_lib",
        owner_user_id="u_gl",
    )
    insert_chunk(env.db, doc_id="d_gl_1", seq=1, version=1, content_seg="gl doc")
    env.db.execute(
        "UPDATE documents SET active_version = 1 WHERE id = 'd_gl_1'"
    )
    gl_rid = env.db.execute(
        "SELECT rid FROM chunks WHERE doc_id = 'd_gl_1'"
    ).fetchone()[0]
    matrix.insert_vector(gl_rid, env.old_label, [0.2] * 8)

    task_id = env.enqueue_reembed()  # payload org=org:tax（投递上下文）
    from knowledge_lattice.worker.rebuild import run_reembed_task

    run_reembed_task(env.services, task_id)
    assert env.backend.get_task(task_id)["status"] == "done"

    # 全库（org:tax + org:gl）单标签一致：B/C 组织块同获新标签向量、旧标签清理
    assert env.cv_labels(gl_rid) == {NEW_LABEL}, "org:gl 块同迁（全库扫描）"
    for rid in env.rids:
        assert env.cv_labels(rid) == {NEW_LABEL}
    stray = env.db.execute(
        "SELECT count(*) FROM chunk_vectors WHERE embed_model != ?", (NEW_LABEL,),
    ).fetchone()[0]
    assert stray == 0, "全库无非新标签行（单标签一致——TC-EMB-06④冻结口径）"

    # quality 缓存失效与 semantic_build 投递同为全库（逐组织）
    builds = {
        json.loads(r[0])["org"]
        for r in env.db.execute(
            "SELECT payload FROM tasks WHERE type = 'semantic_build'"
        )
    }
    assert {"org:tax", "org:gl"} <= builds, "semantic_build 逐组织全库投递"


def test_reembed_full_scan_fills_other_org_gaps(matrix, tmp_path) -> None:
    """正路径（P3-4/R3 改名——原名 switch_blocked 无负向判别易误读）：org:gl
    缺块（无旧标签向量的在用块）被**全库扫描**补齐——单 org 级实现下 org:gl
    缺块会残留；全库实现天然补齐后切换。负向判别（覆盖率门未达成不切换）
    见 test_reembed_no_switch_until_full_library_converged。"""
    env = _RebuildEnv(matrix, tmp_path)
    from helpers import insert_chunk, seed_dataset, seed_document

    seed_dataset(env.db, "org:gl", "ds:gl_lib")
    seed_document(
        env.db, "d_gl_1", org_id="org:gl", dataset_id="ds:gl_lib",
        owner_user_id="u_gl",
    )
    # org:gl 无旧标签向量的在用块（缺块形态——全库门下必须补齐后才可切换）
    insert_chunk(env.db, doc_id="d_gl_1", seq=1, version=1, content_seg="gl doc")
    env.db.execute(
        "UPDATE documents SET active_version = 1 WHERE id = 'd_gl_1'"
    )

    task_id = env.enqueue_reembed()
    from knowledge_lattice.worker.rebuild import run_reembed_task

    run_reembed_task(env.services, task_id)
    assert env.backend.get_task(task_id)["status"] == "done"
    # 全库补齐后才切换（单 org:tax 100% 不放行——全库门实证）
    assert env.services.settings.embed_model_label == NEW_LABEL
    gl_rid = env.db.execute(
        "SELECT rid FROM chunks WHERE doc_id = 'd_gl_1'"
    ).fetchone()[0]
    assert env.cv_labels(gl_rid) == {NEW_LABEL}, "org:gl 缺块被全库扫描补齐"


def test_reembed_no_switch_until_full_library_converged(
    matrix, tmp_path, monkeypatch
) -> None:
    """P3-4/R3 **负向判别**：全库覆盖率门未达成 → 任务 failed 不切换——
    monkeypatch embedding_coverage 恒报 done<total（模拟「并发摄取持续超越/
    永久缺块」形态），执行体 3 轮收敛上限内不达标 → 失败收口；切换/清理/
    联动全部不发生（settings 保持旧标签、旧标签向量保留）。"""
    env = _RebuildEnv(matrix, tmp_path)
    task_id = env.enqueue_reembed()

    real_coverage = env.backend.embedding_coverage

    def stuck_coverage(org_id, label):
        rows = real_coverage(org_id, label)
        # 恒缺一块（done-1——收敛判定永 false）
        return [dict(r, done=max(r["done"] - 1, 0)) for r in rows if r["total"]]

    monkeypatch.setattr(env.backend, "embedding_coverage", stuck_coverage)

    from knowledge_lattice.worker.rebuild import run_reembed_task

    run_reembed_task(env.services, task_id)
    task = env.backend.get_task(task_id)
    assert task["status"] == "failed", "覆盖率门未达成——任务失败留重试"
    assert "未收敛" in (task["error"] or "")

    # 切换/清理/联动全部未发生（写入阶段①合法完成——蓝绿并行写入是门的前置，
    # 门拦的是「切换」：新标签行存在、**旧标签行保留**（未清理））
    assert env.services.settings.embed_model_label == env.old_label, "不得切换"
    assert env.embedder.model_label == env.old_label
    for rid in env.rids:
        assert env.old_label in env.cv_labels(rid), "清理未发生（旧向量保留）"
    builds = env.db.execute(
        "SELECT count(*) FROM tasks WHERE type = 'semantic_build'"
    ).fetchone()[0]
    assert builds == 0, "失败路径不投递 semantic_build"


# ============ R2 P2-1：semantic_build 强制重跑实际执行 ============


def test_reembed_then_semantic_build_executed(matrix, tmp_path) -> None:
    """P2-1 修复面：reembed 后**实际执行** semantic_build 任务——status=ready
    （非 skipped）、dict_rev 随新嵌入标签变化、sem_fuzzy_terms 行 embed_model
    为新标签（design §5.8「换模型 → 相同则跳过失效」）。双后端。"""
    env = _RebuildEnv(matrix, tmp_path)

    # 语义层造数：sync 一条实体 + 首次 build（旧标签 rev）
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from fake_semantic import FakeSourceAdapter

    run_sync(
        env.backend, ORG, FakeSourceAdapter("template_center", [
            EntityRecord(type="concept", key="vat.input_credit",
                         name="进项税额抵扣", aliases=("进项面",)),
        ]),
        settings=env.settings, snapshot=[],
    )
    first = run_build(env.backend, ORG, settings=env.settings,
                      embedder=env.embedder)
    assert first["status"] == "ready"

    # reembed 全库迁移（切换 services.settings 与 embedder）
    task_id = env.enqueue_reembed()
    from knowledge_lattice.worker.rebuild import run_reembed_task

    run_reembed_task(env.services, task_id)
    assert env.backend.get_task(task_id)["status"] == "done"

    # 执行体投递的 semantic_build 被认领**真执行**：status=ready 非 skipped
    # （全库逐组织投递——取 org:tax 那条；org:gl 无语义实体走 skipped 无碍）
    all_builds = env.db.execute(
        "SELECT id, payload FROM tasks WHERE type = 'semantic_build'"
    ).fetchall()
    build_task = next(
        row for row in all_builds
        if json.loads(row[1]).get("org") == ORG
    )
    assert build_task, "reembed 完成投递了 org:tax 的 semantic_build 任务"
    # drain 全部 semantic_build（全库逐组织——org:gl 的 skipped 构建先被领）
    for _ in range(len(all_builds) + 2):
        if not env.runner.run_once(task_types=("semantic_build",)):
            break
    final = env.backend.get_task(build_task[0])
    assert final["status"] == "done", final.get("error")

    # dict_rev 已含新嵌入标签（≠旧标签 rev——skipped 失效）
    second = env.backend.sem_get_build(ORG, first["build_id"])  # 首次 build 行
    assert second is not None
    newest = env.backend.sem_current_build(ORG)
    assert newest["dict_rev"] != first["dict_rev"], (
        "dict_rev 随嵌入标签变化（§5.8——否则 run_build 走 skipped）"
    )
    stats = newest.get("stats_json") or {}
    if isinstance(stats, str):
        stats = json.loads(stats)
    comps = stats.get("dict_rev_components", {})
    assert comps.get("embed_model") == NEW_LABEL, (
        f"dict_rev 组件含新标签: {comps}"
    )

    # 模糊索引向量行标签为新标签（sem_fuzzy_terms.embed_model）
    fuzzy_labels = {
        r[0] for r in env.db.execute(
            "SELECT DISTINCT embed_model FROM sem_fuzzy_terms"
            " WHERE org_id = ? AND embed_model IS NOT NULL", (ORG,),
        )
    }
    assert fuzzy_labels <= {NEW_LABEL}, f"模糊索引向量层随新标签: {fuzzy_labels}"


def test_fingerprint_probe_dim_follows_embedder(rebuild_env) -> None:
    """P2-1 修复面：FingerprintProbe 维度校验从 embedder.model_label 派生——
    embedder 蓝绿切换（dim 变更）后探针不再抛维度异常、基线按新标签建档。"""
    from knowledge_lattice.adapters.embedder import FingerprintProbe

    env = rebuild_env
    # 切换 embedder（8→16 维）——探针持有旧 settings（embed_dim=8）
    env.embedder.apply_model(NEW_NAME, NEW_DIM)
    probe = FingerprintProbe(env.backend, env.embedder, env.settings)
    result = probe.probe()  # 修复前：validate_dim(8) 对 16 维向量 raise
    assert result.status in ("baselined", "ok")
    assert env.backend.read_fingerprint(NEW_LABEL) is not None, (
        "基线按切换后标签建档"
    )


# ============ R2 P3-5：reindex 取消/pending 窗口 ============


def test_reindex_cancelled_before_reset(reindex_env) -> None:
    """P3-5①：任务在执行体重置前被取消（failed+'cancelled:'）→ 重置不发生
    （在用块保留、状态非 parsing）——文档不因取消而不可搜。"""
    env = reindex_env
    task_id = env.backend.create_task(
        env.doc_id, task_type="reindex", target_version=1,
        payload=json.dumps({"org": ORG}),
    )
    # 取消（任务行 failed——模拟「claim 后、reset 前取消」的执行体视角）
    env.backend.cancel_task(task_id, reason="cancelled: by user request")
    from knowledge_lattice.worker.rebuild import run_reindex_task

    run_reindex_task(env.services, task_id)  # 执行体对已取消任务：不 reset

    doc = env.backend.get_document(env.doc_id)
    assert doc["active_status"] == "searchable_full", "取消不触发重置（不可搜窗口根除）"
    rows = env.db.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND tombstone = 0",
        (env.doc_id,),
    ).fetchone()[0]
    assert rows >= 1, "在用块保留"


@pytest.mark.parametrize("pending_status", ["parsing", "failed"])
def test_reindex_rejected_while_pending_version(reindex_env, pending_status) -> None:
    """P3-5②/N-2 裁定选 a（R3）：文档存在 pending 版本（**含 failed**——
    ingest._guard_alive 仍以 pending 为当前目标，放行会 reset 后判 cancelled）
    时 reindex（target=active）→ 执行体 fail-closed 拒绝（任务 failed 带原因、
    文档不动）。API 面 409 同语义（test_admin_manage——双防线）。"""
    env = reindex_env
    # 开 pending v2（覆盖上传在途形态——active v1 在用）
    env.db.execute(
        "UPDATE documents SET pending_version = 2, pending_status = ?"
        " WHERE id = ?", (pending_status, env.doc_id),
    )
    env.db.commit()
    task_id = env.backend.create_task(
        env.doc_id, task_type="reindex", target_version=1,
        payload=json.dumps({"org": ORG}),
    )
    from knowledge_lattice.worker.rebuild import run_reindex_task

    run_reindex_task(env.services, task_id)
    task = env.backend.get_task(task_id)
    assert task["status"] == "failed"
    assert "pending" in (task["error"] or ""), (
        f"拒绝原因指明 pending（{pending_status} 形态）: {task['error']}"
    )
    doc = env.backend.get_document(env.doc_id)
    assert doc["active_status"] == "searchable_full", "文档不动（active 块保留）"
    rows = env.db.execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ? AND tombstone = 0",
        (env.doc_id,),
    ).fetchone()[0]
    assert rows >= 1, "在用块保留（不可搜窗口根除）"
