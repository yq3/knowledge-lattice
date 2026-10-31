"""P2-3/R2：sem_expand_graph / sem_search_entities store 级双臂参数化用例
（TEST-CASES 拍板3——T-S6 自 M2-S 起双后端参数化；此前 pg 方言仅 tester 临时
脚本 v1/v2 补验，回归门禁不保护）。

顺带锁死：P2-1（pg score float 类型 + JSON 可序列化）、P3-2（edges 去重 +
节点截断无悬挂边）、P3-4（sem_table_columns 滤 restricted 列）、P3-3
（expand_relations 薄适配）。fixture 语义图经 run_sync 真实链路落库。

图形状（org:tax）：

- 模板链：T --backed_by--> t1 --has_column--> c1/c2/c3；F --maps_to--> c1；
  T --has_field--> F；
- 环：rA --related_to--> rB --related_to--> rC --related_to--> rA；
- 高扇出：big --has_column--> col_0..col_9（10 列，fanout 截断可控造数）；
- restricted：concept R（别名「受限词」）+ t1 的列 c3 置 restricted。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fake_semantic import FakeSourceAdapter
from helpers import seed_org

ORG = "org:tax"

NOW = "2026-10-30 12:00:00"


def _snapshot() -> list:
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

    out: list = [
        EntityRecord(type="template", key="T", name="模板", aliases=("模板词",)),
        EntityRecord(type="template_field", key="T.F", name="字段",
                     parent_key="template:T"),
        EntityRecord(type="table", key="t1", name="表一"),
        EntityRecord(type="column", key="t1.c1", name="列一",
                     parent_key="table:t1"),
        EntityRecord(type="column", key="t1.c2", name="列二",
                     parent_key="table:t1"),
        EntityRecord(type="column", key="t1.c3", name="受限列",
                     parent_key="table:t1"),
        EntityRecord(type="table", key="big", name="大表"),
        EntityRecord(type="concept", key="rA", name="环A"),
        EntityRecord(type="concept", key="rB", name="环B"),
        EntityRecord(type="concept", key="rC", name="环C"),
        EntityRecord(type="concept", key="R", name="受限概念", aliases=("受限词",)),
        EntityRecord(type="concept", key="c_note", name="详解模板词"),
    ]
    rel = [
        (("template", "T"), "has_field", ("template_field", "T.F")),
        (("template", "T"), "backed_by", ("table", "t1")),
        (("template_field", "T.F"), "maps_to", ("column", "t1.c1")),
        (("table", "t1"), "has_column", ("column", "t1.c1")),
        (("table", "t1"), "has_column", ("column", "t1.c2")),
        (("table", "t1"), "has_column", ("column", "t1.c3")),
        (("concept", "rA"), "related_to", ("concept", "rB")),
        (("concept", "rB"), "related_to", ("concept", "rC")),
        (("concept", "rC"), "related_to", ("concept", "rA")),
    ]
    for i in range(10):
        out.append(EntityRecord(type="column", key=f"big.col_{i}", name=f"大列{i}",
                                parent_key="table:big"))
        rel.append((("table", "big"), "has_column", ("column", f"big.col_{i}")))
    out.extend(RelationRecord(src=s, rel_type=r, dst=d) for s, r, d in rel)
    return out


SNAPSHOT = _snapshot()


@pytest.fixture()
def sem_store(backend, tmp_path):
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.sync import run_sync

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path)
    env = SimpleNamespace(db=backend, backend=backend.make_backend(),
                          settings=settings, ids={})
    run_sync(env.backend, ORG, FakeSourceAdapter("template_center", SNAPSHOT),
             settings=settings, snapshot=SNAPSHOT, now=NOW)
    # restricted 造数（同步面无 sensitivity 入口——T-S9 权限面归 M2-S3）
    env.db.execute(
        "UPDATE sem_entities SET sensitivity = 'restricted'"
        " WHERE org_id = ? AND key IN ('R', 't1.c3')", (ORG,))
    env.db.commit()
    for key in ("T", "T.F", "t1", "t1.c1", "t1.c2", "t1.c3", "big", "rA", "rB",
                "rC", "R", "c_note"):
        env.ids[key] = env.db.execute(
            "SELECT id FROM sem_entities WHERE org_id = ? AND key = ?",
            (ORG, key)).fetchone()[0]
    for i in range(10):
        env.ids[f"big.col_{i}"] = env.db.execute(
            "SELECT id FROM sem_entities WHERE org_id = ? AND key = ?",
            (ORG, f"big.col_{i}")).fetchone()[0]
    return env


# ---- expand：环 / 双向 / 方向 / 截断 / restricted 零泄漏 / edges 契约 ----


def test_expand_cycle_terminates_both_directions(sem_store) -> None:
    b, ids = sem_store.backend, sem_store.ids
    rel = ["related_to"]
    out = b.sem_expand_graph(ORG, ids["rA"], outgoing=rel, incoming=rel,
                             depth=2, fanout_limit=50, node_limit=200)
    assert {n["key"] for n in out["nodes"]} == {"rB", "rC"}  # 防环不死循环
    assert out["truncated"] is False
    # 双向 depth2 覆盖环全部三条边（A→B 出向 / C→A 入向 / B→C 二跳——
    # 已访问端点的边照常返回且不重复）
    assert {(e["src"], e["rel"], e["dst"]) for e in out["edges"]} == {
        (ids["rA"], "related_to", ids["rB"]),
        (ids["rB"], "related_to", ids["rC"]),
        (ids["rC"], "related_to", ids["rA"]),
    }


def test_expand_direction_filters(sem_store) -> None:
    """方向后缀的 store 语义：outgoing-only / incoming-only 各取一半。"""
    b, ids = sem_store.backend, sem_store.ids
    rel = ["related_to"]
    out_only = b.sem_expand_graph(ORG, ids["rB"], outgoing=rel, incoming=[],
                                  depth=1, fanout_limit=50, node_limit=200)
    assert {n["key"] for n in out_only["nodes"]} == {"rC"}
    in_only = b.sem_expand_graph(ORG, ids["rB"], outgoing=[], incoming=rel,
                                 depth=1, fanout_limit=50, node_limit=200)
    assert {n["key"] for n in in_only["nodes"]} == {"rA"}


def test_expand_two_hop_chain(sem_store) -> None:
    """模板链 depth=2：T → t1 → 列（restricted 列 c3 不出现——零泄漏）。"""
    b, ids = sem_store.backend, sem_store.ids
    out = b.sem_expand_graph(ORG, ids["T"], outgoing=["backed_by", "has_column"],
                             incoming=[], depth=2, fanout_limit=50, node_limit=200)
    keys = {n["key"] for n in out["nodes"]}
    assert "t1" in keys
    assert f"t1.c1" in keys and "t1.c2" in keys
    assert "t1.c3" not in keys, "restricted 列不得出现（T-S9 fail-closed）"
    assert all(n["depth"] in (1, 2) for n in out["nodes"])


def test_expand_fanout_and_node_limit_truncation(sem_store) -> None:
    """fanout 每节点截断 + node_limit 总量截断 + **无悬挂边**
    （P3-2：截断省略的节点不得作为边端点出现）。"""
    b, ids = sem_store.backend, sem_store.ids
    rel = ["has_column"]
    p3 = b.sem_expand_graph(ORG, ids["big"], outgoing=rel, incoming=[],
                            depth=1, fanout_limit=3, node_limit=200)
    assert len(p3["nodes"]) == 3 and p3["truncated"] is True
    # node_limit=5：10 列收 5，其余不进 nodes 也不进 edges（悬挂边禁绝）
    p5 = b.sem_expand_graph(ORG, ids["big"], outgoing=rel, incoming=[],
                            depth=1, fanout_limit=50, node_limit=5)
    assert len(p5["nodes"]) == 5 and p5["truncated"] is True
    node_ids = {ids["big"]} | {n["id"] for n in p5["nodes"]}
    for edge in p5["edges"]:
        assert edge["src"] in node_ids and edge["dst"] in node_ids, \
            "P3-2：节点截断后不得出现悬挂边"


def test_expand_edges_no_duplicate_and_restricted_root_semantics(sem_store) -> None:
    """①双向查询同关系行只计一次（P3-2 去重——无自环图上同一 (src,rel,dst)
    不重复）；②restricted 端点不出现（邻居零泄漏）。"""
    b, ids = sem_store.backend, sem_store.ids
    both = b.sem_expand_graph(ORG, ids["t1"], outgoing=["has_column"],
                              incoming=["has_column"],
                              depth=1, fanout_limit=50, node_limit=200)
    edge_keys = [(e["src"], e["rel"], e["dst"]) for e in both["edges"]]
    assert len(edge_keys) == len(set(edge_keys)), "P3-2：edges 不得重复"
    # restricted 列 c3 邻接 t1——双向展开零出现
    assert ids["t1.c3"] not in {n["id"] for n in both["nodes"]}
    assert all(ids["t1.c3"] not in (e["src"], e["dst"]) for e in both["edges"])


def test_expand_relations_thin_adapter(sem_store) -> None:
    """P3-3：expand_relations（design §3/NFR-4 命名）= sem_expand_graph 薄适配
    ——多 seed 归并去重、rels 双向。"""
    b, ids = sem_store.backend, sem_store.ids
    out = b.expand_relations(ORG, [ids["T"], ids["big"]], ["backed_by", "has_column"])
    keys = {n["key"] for n in out["nodes"]}
    assert {"t1"} <= keys and any(k.startswith("big.col_") for k in keys)
    edge_keys = [(e["src"], e["rel"], e["dst"]) for e in out["edges"]]
    assert len(edge_keys) == len(set(edge_keys))


# ---- search：三层排序 / ESCAPE / types·top_k / restricted / score 类型 ----


def test_search_three_tier_ranking_and_types(sem_store) -> None:
    b = sem_store.backend
    rows = b.sem_search_entities(ORG, "模板词", "模板词", types=None, top_k=10)
    # 去重前 store 层保留多档（core 收口保最优）——首行=精确档模板
    assert rows[0]["key"] == "T" and rows[0]["via"] == "alias-exact"
    vias = [r["via"] for r in rows]
    assert "alias-prefix" in vias or "name" in vias  # 「详解模板词」name 模糊档
    # types 收窄：concept only → 模板不出现
    only_concept = b.sem_search_entities(ORG, "模板词", "模板词",
                                         types=["concept"], top_k=10)
    assert all(r["type"] == "concept" for r in only_concept)
    assert {r["key"] for r in only_concept} >= {"c_note"}
    # top_k 截断（store 层取 top_k×3 候选——上界钉住）
    capped = b.sem_search_entities(ORG, "列", "列", types=None, top_k=2)
    assert len(capped) <= 6


def test_search_like_escape_semantics(sem_store) -> None:
    """%/_/\ 通配符按字面匹配（ESCAPE——注入形态零误配）。"""
    b = sem_store.backend
    # 字面 % 查询不命中任何内容（库里无含 % 的别名/名）
    assert b.sem_search_entities(ORG, "%", "%", types=None, top_k=10) == []
    assert b.sem_search_entities(ORG, "_", "_", types=None, top_k=10) == []
    # 前缀注入形态：'t1.%' 不被解释为通配——零命中（无该字面别名）
    assert b.sem_search_entities(ORG, "t1.%", "t1.%", types=None, top_k=10) == []


def test_search_restricted_excluded_and_score_type(sem_store) -> None:
    """restricted 无命中（T-S9）+ P2-1：score 双方言均 float 且 JSON 可序列化
    （pg 裸字面量 NUMERIC→Decimal 漂移已 ::float8 收口）。"""
    b = sem_store.backend
    rows = b.sem_search_entities(ORG, "受限词", "受限词", types=None, top_k=10)
    assert rows == [], "restricted 实体 search 零命中"
    hits = b.sem_search_entities(ORG, "环", "环", types=None, top_k=10)
    assert hits
    for r in hits:
        assert isinstance(r["score"], float), f"score 须 float（P2-1）: {r['score']!r}"
        json.dumps({"score": r["score"]})  # FastMCP/json 出参可序列化


def test_sem_table_columns_filters_restricted(sem_store) -> None:
    """P3-4：轻量列节点滤 restricted 列（降级路径不泄露 t1.c3）。"""
    cols = sem_store.backend.sem_table_columns(ORG, sem_store.ids["t1"])
    keys = {c["key"] for c in cols}
    assert keys == {"t1.c1", "t1.c2"}, "restricted 列不得出现在轻量节点（P3-4）"
