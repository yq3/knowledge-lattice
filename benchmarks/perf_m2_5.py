#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""m2-5 A8：TC-PERF-05 语义 P99 基准（m2s-6 移交性能兜底轮）。

口径（TEST-CASES TC-PERF-05 / NFR-11）：
  - annotate 整体 P99 < 20ms、AC 层 P99 < 5ms；
  - get_entity depth=2 P99 < 50ms；
  - **万级词典 + 高扇出图**样本下达标（~10⁴ 实体 + 1 表 300 列 + 1 模板被
    10 场景 uses——语义 fixture 口径的放大形态）；
  - AC 自动机 (org, dict_rev) 懒加载不重复构建（get_annotator 同 rev
    返回同一实例——identity 断言）。

含 m2-5 G-24④ 修复后的模糊面形态：fuzzy=True 档单列（懒构建后首调摊销
构建、后续零构建；内存面去 dict() 复制）。

用法：uv run python benchmarks/perf_m2_5.py
产物：data/bench-results/m2-5-perf05.json
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_common import save_result  # noqa: E402

from helpers import seed_org  # noqa: E402

ORG = "org:tax"
NOW = "2026-11-01 09:00:00"
N_CONCEPTS = 10_000     # 万级词典
FANOUT_COLS = 300       # 高扇出表（一表 300 列）
FANOUT_SCENARIOS = 10   # 高扇出模板（被 10 场景 uses）
SAMPLES = 100           # P99 采样轮次


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[max(0, math.ceil(p * len(xs)) - 1)] * 1000


def build_env(tmp: Path):
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.backend import SqliteBackend
    from fake_providers import FakeEmbedder
    from fake_semantic import FakeSourceAdapter

    conn = connect(tmp / "perf.db")
    migrate_db(conn)
    seed_org(conn, ORG)
    settings = Settings(environment="test", data_dir=tmp, embed_dim=8,
                        embed_model="fake-embed")
    backend = SqliteBackend(conn)

    # ---- 万级词典 + 高扇出图造数 ----
    recs = [
        EntityRecord(
            type="concept", key=f"c.{i:05d}", name=f"税务术语{i}",
            aliases=(f"术语别名{i}",) if i % 2 == 0 else (),
        )
        for i in range(N_CONCEPTS)
    ]
    # 高扇出表：ods.big 300 列（column_of 边）
    recs.append(EntityRecord(type="table", key="ods.big", name="宽表"))
    recs += [
        EntityRecord(type="column", key=f"ods.big.col_{j:03d}", name=f"列{j}",
                     parent_key="table:ods.big")
        for j in range(FANOUT_COLS)
    ]
    # 高扇出模板：TPL_X 被 10 场景 uses
    recs.append(EntityRecord(type="template", key="TPL_X", name="万能模板"))
    recs += [
        EntityRecord(type="scenario", key=f"SC.{k:02d}", name=f"场景{k}",
                     parent_key="template:TPL_X")
        for k in range(FANOUT_SCENARIOS)
    ]
    rels = [RelationRecord(src=("table", "ods.big"),
                           rel_type="has_column",
                           dst=("column", f"ods.big.col_{j:03d}"))
            for j in range(FANOUT_COLS)]
    rels += [RelationRecord(src=("template", "TPL_X"),
                            rel_type="used_by",
                            dst=("scenario", f"SC.{k:02d}"))
             for k in range(FANOUT_SCENARIOS)]

    t0 = time.perf_counter()
    run_sync(backend, ORG, FakeSourceAdapter("tc", recs), settings=settings,
             snapshot=list(recs), now=NOW)
    t_sync = time.perf_counter() - t0
    clear_annotator_cache()
    t0 = time.perf_counter()
    report = run_build(backend, ORG, settings=settings,
                       embedder=FakeEmbedder(dim=8, model_name="fake-embed"))
    t_build = time.perf_counter() - t0
    assert report["status"] == "ready"
    clear_annotator_cache()
    return backend, settings, {
        "entities": len(recs), "relations": len(rels),
        "sync_s": round(t_sync, 1), "build_s": round(t_build, 1),
        "build_stats": report.get("stats", {}),
    }


def main() -> int:
    import tempfile

    from knowledge_lattice.core.semantic.annotator import (
        Annotator, annotate_text, get_annotator,
    )
    from knowledge_lattice.core.semantic.expand import get_entity

    tmp = Path(tempfile.mkdtemp(prefix="lattice-perf05-"))
    backend, settings, meta = build_env(tmp)
    print(f"造数：{meta['entities']} 实体 / {meta['relations']} 关系"
          f"（sync {meta['sync_s']}s + build {meta['build_s']}s）")

    out: dict = {"n_concepts": N_CONCEPTS, "fanout_cols": FANOUT_COLS,
                 "fanout_scenarios": FANOUT_SCENARIOS, "samples": SAMPLES,
                 "seed_meta": meta}

    # ---- 懒加载不重复构建（TC-PERF-05 验收句） ----
    ann1, rev1 = get_annotator(backend, ORG, settings)
    ann2, rev2 = get_annotator(backend, ORG, settings)
    out["annotator_cached_same_instance"] = ann1 is ann2 and rev1 == rev2

    # ---- annotate 整体 / AC 层（P99） ----
    text_hit = " ".join(f"税务术语{i} 的处理口径" for i in (3, 1200, 9998))
    text_miss = "一段不含词典命中的普通业务叙述文本，用于测量空扫描开销。"

    for tag, text in (("hit", text_hit), ("miss", text_miss)):
        # 整体（annotate_text：快照锚点 + 规范化 + AC + 消歧）
        xs = []
        for _ in range(SAMPLES):
            t0 = time.perf_counter()
            annotate_text(backend, settings, ORG, text)
            xs.append(time.perf_counter() - t0)
        out[f"annotate_overall_{tag}"] = {
            "p50_ms": round(_pct(xs, 0.50), 3), "p99_ms": round(_pct(xs, 0.99), 3)}
        # AC 层（Annotator._scan——构造后的纯自动机扫描）
        from knowledge_lattice.core.semantic.annotator import (
            _normalize_with_map,
        )

        xs = []
        norm = _normalize_with_map(text)[0]
        for _ in range(SAMPLES):
            t0 = time.perf_counter()
            ann1._scan(norm)
            xs.append(time.perf_counter() - t0)
        out[f"annotate_ac_layer_{tag}"] = {
            "p50_ms": round(_pct(xs, 0.50), 3), "p99_ms": round(_pct(xs, 0.99), 3)}

    # ---- fuzzy 档（G-24④ 修复后形态：首调构建摊销 + 稳态零构建） ----
    t0 = time.perf_counter()
    annotate_text(backend, settings, ORG, text_hit + " 申抱", fuzzy=True)
    first_ms = (time.perf_counter() - t0) * 1000
    xs = []
    for _ in range(SAMPLES):
        t0 = time.perf_counter()
        annotate_text(backend, settings, ORG, text_hit + " 申抱", fuzzy=True)
        xs.append(time.perf_counter() - t0)
    out["annotate_fuzzy"] = {
        "first_call_ms": round(first_ms, 1),   # 含懒构建（一次摊销）
        "steady_p99_ms": round(_pct(xs, 0.99), 3),
    }

    # ---- get_entity depth=2（高扇出锚点：ods.big 表 / TPL_X 模板） ----
    table_id = backend.sem_entity_by_key(ORG, "table", "ods.big")["id"]
    tpl_id = backend.sem_entity_by_key(ORG, "template", "TPL_X")["id"]
    for tag, eid, expand in (("table_fanout", table_id, ["has_column"]),
                             ("tpl_fanout", tpl_id, ["uses"])):
        xs = []
        for _ in range(SAMPLES):
            t0 = time.perf_counter()
            get_entity(backend, ORG, entity_id=eid, expand=expand, depth=2,
                       fanout_limit=200)
            xs.append(time.perf_counter() - t0)
        out[f"get_entity_{tag}_depth2"] = {
            "p50_ms": round(_pct(xs, 0.50), 3), "p99_ms": round(_pct(xs, 0.99), 3)}

    # ---- 达标判定（AC<5ms / 整体<20ms / depth2<50ms） ----
    verdict = {}
    for tag in ("hit", "miss"):
        verdict[f"ac_{tag}"] = out[f"annotate_ac_layer_{tag}"]["p99_ms"] < 5
        verdict[f"overall_{tag}"] = out[f"annotate_overall_{tag}"]["p99_ms"] < 20
    for tag in ("table_fanout", "tpl_fanout"):
        verdict[f"depth2_{tag}"] = out[f"get_entity_{tag}_depth2"]["p99_ms"] < 50
    verdict["lazy_cache_same_instance"] = out["annotator_cached_same_instance"]
    out["verdict"] = verdict

    save_result("m2-5-perf05", out)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
