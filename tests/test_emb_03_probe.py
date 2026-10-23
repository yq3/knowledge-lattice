"""TC-EMB-03 指纹探针【单测｜M0a——断言范围：建档 / 两档写入拒绝 / notice.degraded 标注】。

M0a 断言落（用例原文「里程碑口径」）：①首部署建档放行（≥3 哨兵、基线入主库）；
②drift<0.95 拒绝档——同标签写入拒绝 + 告警审计 + 摄取 embed 阶段失败可重试、
文档停 searchable_lexical（不 500）、notice.degraded 含 probe_reject；③0.95~0.99
告警档仅告警；④周期探测两档判定。向量路开闭行为断言随 M1（TC-EMB-07 同款理由）、
换标签重嵌入随 M2（TC-EMB-06）。
"""

from __future__ import annotations

import json
import math

from fake_providers import FakeEmbedder

from knowledge_lattice.adapters.embedder import (
    SENTINELS,
    EmbeddingProbeRejected,
    FingerprintProbe,
)

HTML_BYTES = (
    "<html><body><h1>留抵退税指南</h1><p>符合条件的纳税人可申请退还增量留抵税额。</p></body></html>"
).encode("utf-8")


def _probe(ingest_env, embedder):
    return FingerprintProbe(ingest_env["backend"], embedder, ingest_env["settings"])


def _outbox_events(ingest_env) -> list[tuple[str, str]]:
    return [
        (r[0], r[1])
        for r in ingest_env["conn"].execute("SELECT event_type, payload_json FROM audit_outbox")
    ]


def test_first_deployment_baseline_and_pass(ingest_env) -> None:
    """①首部署：无基线 → 探测建档（≥3 哨兵、基线入 embedding_fingerprints）并放行。"""
    probe = _probe(ingest_env, FakeEmbedder(dim=2560))
    result = probe.probe()
    assert result.status == "baselined"
    baseline_json = ingest_env["backend"].read_fingerprint(ingest_env["settings"].embed_model_label)
    assert baseline_json is not None
    baseline = json.loads(baseline_json)
    assert len(baseline) >= 3
    assert [b["sentinel"] for b in baseline] == list(SENTINELS)
    # 二次探测（同底模）→ ok 放行
    assert probe.probe().status == "ok"


def test_drift_reject_blocks_writes_and_audits(ingest_env) -> None:
    """②drift<0.95 拒绝档：建档后换底模 → 拒绝以同标签写入 + 告警审计 + embed 阶段失败可重试。"""
    gate = ingest_env["gate"]
    # 建档
    probe = _probe(ingest_env, FakeEmbedder(dim=2560))
    probe.probe()
    # drift 重启（哨兵返回 ≈0 余弦偏移向量）
    rejected = _probe(ingest_env, FakeEmbedder(dim=2560, drift=True)).probe()
    assert rejected.status == "reject"
    assert rejected.min_cosine is not None and rejected.min_cosine < 0.95
    events = [e for e in _outbox_events(ingest_env) if e[0] == "embedding.probe_reject"]
    assert len(events) == 1  # 告警审计
    assert json.loads(events[0][1])["embed_model"] == ingest_env["settings"].embed_model_label

    # gate 拒绝档：embed 写入被拒（同标签）
    gate.update(rejected)
    assert gate.rejected
    # 摄取：embed 阶段失败可重试、文档停 searchable_lexical（不 500）
    backend = ingest_env["backend"]
    svc = ingest_env["make_service"](FakeEmbedder(dim=2560))
    doc_id, task_id = svc.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="指南",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML_BYTES, mime_type="text/html", filename="g.html",
    )
    svc.run_task(task_id, stop_after="index_fts")
    try:
        svc.run_task(task_id)  # gate 拒绝 → embed 失败
        raise AssertionError("应抛 EmbeddingProbeRejected")
    except EmbeddingProbeRejected:
        pass
    doc = backend.get_document(doc_id)
    assert doc["active_status"] == "searchable_lexical"  # 停住、不 500
    assert "probe rejected" in doc["active_error"]
    assert backend.get_task(task_id)["status"] == "failed"  # 可重试

    # 周期探测同两档（④）：恢复同底模 → ok → gate 放行 → 重试成功
    ok = _probe(ingest_env, FakeEmbedder(dim=2560)).probe()
    assert ok.status == "ok"
    gate.update(ok)
    svc.run_task(task_id)
    assert backend.get_document(doc_id)["active_status"] == "searchable_full"


def test_periodic_reprobe_reject_grade(ingest_env) -> None:
    """④周期探测两档判定：运行中（建档后）换底模被周期探测发现——拒绝档再判定。"""
    probe_ok = _probe(ingest_env, FakeEmbedder(dim=2560))
    probe_ok.probe()  # 建档
    # 周期档 1：告警区间（精确余弦 0.97 ∈ [0.95, 0.99)）
    warn = _probe(ingest_env, FakeEmbedder(dim=2560, drift_cos=0.97)).probe()
    assert warn.status == "warn"
    assert warn.min_cosine is not None and 0.95 <= warn.min_cosine < 0.99
    # 周期档 2：更严重漂移 → 拒绝档（两档判定在同一周期探测路径生效）
    rej = _probe(ingest_env, FakeEmbedder(dim=2560, drift_cos=0.5)).probe()
    assert rej.status == "reject"
    events = [e for e in _outbox_events(ingest_env) if e[0] == "embedding.probe_warn"]
    assert len(events) == 1  # 告警档也审计（告警事件）


def test_warn_grade_keeps_writable(ingest_env) -> None:
    """③0.95~0.99 告警档：仅告警（写入放行——告警不等于拒绝）。"""
    _probe(ingest_env, FakeEmbedder(dim=2560)).probe()  # 建档
    warn = _probe(ingest_env, FakeEmbedder(dim=2560, drift_cos=0.97)).probe()
    gate = ingest_env["gate"]
    gate.update(warn)
    gate.ensure_writable()  # 不抛（仅告警）
    # 写入照常完成
    svc = ingest_env["make_service"](FakeEmbedder(dim=2560))
    doc_id, task_id = svc.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="指南",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML_BYTES, mime_type="text/html", filename="g.html",
    )
    svc.run_task(task_id)
    assert ingest_env["backend"].get_document(doc_id)["active_status"] == "searchable_full"


def test_notice_degraded_contains_probe_reject(ingest_env) -> None:
    """②查询侧（M0a 断言范围）：gate 拒绝档 → 检索响应 notice.degraded 含 probe_reject（不 500）。

    M0a 检索本就 BM25 单路——向量路开闭行为断言随 M1（TC-EMB-07），此处断言
    notice.degraded 标注口径。
    """
    from knowledge_lattice.core.docs.retrieve import search

    backend = ingest_env["backend"]
    svc = ingest_env["make_service"](FakeEmbedder(dim=2560))
    doc_id, task_id = svc.create_document(
        org_id="org:tax", dataset_id="ds:vat_lib", title="留抵退税指南",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=HTML_BYTES, mime_type="text/html", filename="g.html",
    )
    svc.run_task(task_id)

    ingest_env["gate"]._status = "reject"  # 拒绝档状态（探针已判定的运行态）
    resp = search(backend, ingest_env["settings"], gate=ingest_env["gate"], user_id="u_full",
                  org_id="org:tax", query="留抵退税")
    assert "probe_reject" in resp["notice"]["degraded"]  # 不 500、标注降级
    assert resp["results"]  # BM25 单路照常返回命中

    ingest_env["gate"]._status = "ok"
    resp2 = search(backend, ingest_env["settings"], gate=ingest_env["gate"], user_id="u_full",
                   org_id="org:tax", query="留抵退税")
    assert "probe_reject" not in resp2["notice"]["degraded"]
    assert resp2["results"]


def test_baseline_unchanged_by_probes(ingest_env) -> None:
    """探测不重写基线（建档一次；基线漂移检测的锚点稳定）。"""
    probe = _probe(ingest_env, FakeEmbedder(dim=2560))
    probe.probe()
    first = ingest_env["backend"].read_fingerprint(ingest_env["settings"].embed_model_label)
    _probe(ingest_env, FakeEmbedder(dim=2560)).probe()
    assert ingest_env["backend"].read_fingerprint(ingest_env["settings"].embed_model_label) == first


def test_cosine_helper_sanity() -> None:
    """余弦助手数学正确性（正交=0 / 同向=1）。"""
    from knowledge_lattice.adapters.embedder import _cosine

    assert math.isclose(_cosine([1.0, 0.0], [1.0, 0.0]), 1.0)
    assert math.isclose(_cosine([1.0, 0.0], [0.0, 1.0]), 0.0)
    assert math.isclose(_cosine([1.0, 0.0], [-1.0, 0.0]), -1.0)
