"""AC 自动机识别与消歧（design §5.9——m2s-4 面上段；core 纯内存计算、
零 SQL——快照输入来自 store Semantic 域）。

**A1 自动机**（pyahocorasick）：键 `alias_norm`、值命中记录列表；只收
`match_mode IN ('exact','context')`（fuzzy_only 不进——TC-BUILD-02 防误报）；
restricted 实体别名不入机（T-S9 annotate 侧 fail-closed——表现为不存在，
持权路径 M2-S3 权限面交付前一律不可见）。生命周期：按 `(org, dict_rev)`
懒加载缓存——构建中/失败沿用旧实例、ready 后切换新实例（T-S12）。

**A2 匹配四步**（任务书四步消歧的匹配半边，输出 `matched_by`）：

1. `exact` 精确全词：规范名/业务键（kind=name/code）命中；
2. `alias` 别名：manual/sync/abbr（拉丁面词边界校验——`jxdk` 不命中
   `xxjdkxx` 内部；大小写经规范化折叠，span 回映原文下标）；
3. `context` 上下文短别名：match_mode='context'，仅当同句有其他**确定**命中
   且两者有关系时保留（TC-SEM-04——短词防误报 FR-S3）；
4. overlap 择优：最长匹配优先，等长取 weight 高者（TC-SEM-02）。

**消歧四级**（design §5.9 ③——输出 `resolved_by`，span 对应多实体时按序）：

① `cooccurrence` 上下文共现（同句其他命中实体与候选有 1 跳关系）>
② `focus` 会话焦点（context_entities）> ③ `prior` 类型先验（prefer_types）>
④ **`l0` L0 片段兜底**（任务书 A3——候选 L0 definition 片段的上下文词
佐证：句内除命中面外的词元与片段重叠唯一最大者定案）> ⑤ 仍不定则返回
全部候选 `ambiguous=true`（confidence 不标 1.0——TC-SEM-03④）。

**A3 L0 片段引用面**：`render_l0` 从快照 curated_json（m2s-3 已入）渲染
l0:true 条目 markdown 片段——`GET /semantic/l0` 导出（TC-SEM-06）与
expand/get_entity 的 curated 载荷同源。
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from collections import defaultdict

import ahocorasick

from knowledge_lattice.core.semantic.norm import normalize_alias

logger = logging.getLogger(__name__)

__all__ = [
    "Annotator", "build_automaton", "get_annotator", "clear_annotator_cache",
    "annotate_text", "render_l0", "MAX_TEXT_LEN", "MAX_CONTEXT_ENTITIES",
]

MAX_TEXT_LEN = 4000            # §6.3 契约：≤4000 字（超长拒绝——附录 A-10）
MAX_CONTEXT_ENTITIES = 20      # §6.3：会话焦点实体数上限
_SENTENCE_SPLIT = re.compile(r"[。！？!?；;\n]")
_LATIN = re.compile(r"[a-z0-9]")
_CJK = re.compile(r"[\u4e00-\u9fff]")

# matched_by → 基础 confidence（via='ac'——模糊层 M2-S3）
_TIER_CONFIDENCE = {"exact": 1.0, "alias": 0.95, "context": 0.9}
_RESOLVED_CEILING = {  # resolved_by → confidence 上限（证据强度递减）
    "single": 1.0, "cooccurrence": 1.0, "focus": 0.95, "prior": 0.95,
    "l0": 0.9, "ambiguous": 0.8,
}


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """规范化 + 下标回映：每个规范化字符登记原文下标（span 报原文坐标）。

    与 `norm.normalize_alias` 同一规范化语义（NFKC→小写→去空白）；逐字符
    展开以维护下标映射（罕见 NFKC 跨字符组合以本管道为准——TC-SEM-01
    span 回映的工程口径）。"""
    norm_chars: list[str] = []
    origins: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace():
            continue
        for nc in unicodedata.normalize("NFKC", ch).lower():
            norm_chars.append(nc)
            origins.append(i)
    return "".join(norm_chars), origins


def _latin_ok(norm: str, i: int, j: int) -> bool:
    """拉丁词边界：含 [a-z0-9] 的别名须两侧无拉丁字母/数字（防 substring
    误报——大小写经规范化折叠后由边界保证区分度）。CJK 无边界要求。"""
    if not _LATIN.search(norm[i:j]):
        return True
    if i > 0 and _LATIN.match(norm[i - 1]):
        return False
    if j < len(norm) and _LATIN.match(norm[j]):
        return False
    return True


def _bigrams(text: str) -> frozenset[str]:
    """L0 兜底词元：CJK 连续段二元组 + 拉丁/数字词（小写）。"""
    out: set[str] = set()
    for seg in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", text):
        if _CJK.fullmatch(seg[0]):
            out.update(seg[k:k + 2] for k in range(len(seg) - 1))
        else:
            out.add(seg)
    return frozenset(out)


class Annotator:
    """一次构建快照的只读识别面（§5.8 产物——(org, dict_rev) 懒加载实例）。"""

    def __init__(self, snapshot: dict) -> None:
        self.snapshot = snapshot
        self.entities: dict[int, dict] = {e["id"]: e for e in snapshot["entities"]}
        self.key_map: dict[str, int] = {
            f'{e["type"]}:{e["key"]}': e["id"] for e in snapshot["entities"]}
        self.automaton, self.automaton_meta = build_automaton(snapshot)
        # 1 跳邻接（方向无关——共现/L0 佐证只问「有关系」）
        self.adj: dict[int, set[int]] = defaultdict(set)
        for r in snapshot["relations"]:
            self.adj[r["src_id"]].add(r["dst_id"])
            self.adj[r["dst_id"]].add(r["src_id"])
        # L0 片段词元（兜底消歧的佐证面——仅 l0:true 条目）
        self.l0_terms: dict[int, frozenset[str]] = {}
        for eid, ent in self.entities.items():
            curated = _loads(ent.get("curated_json"))
            if curated.get("l0"):
                frag = " ".join(
                    [curated.get("definition") or "",
                     curated.get("why") or "",
                     " ".join(str(d.get("hint") or "")
                              for d in curated.get("disambiguation") or ())])
                self.l0_terms[eid] = _bigrams(normalize_alias(frag))

    # ---- 主入口 ----

    def annotate(self, text: str, *, context_entities: list[int] | None = None,
                 prefer_types: list[str] | None = None) -> dict:
        """文本 → 类型化实体标注（§6.3 契约：mentions + candidates）。"""
        from knowledge_lattice.core.semantic.constants import SEM_ENTITY_TYPES

        if not text or len(text) > MAX_TEXT_LEN:
            raise ValueError(f"text 长度须在 1..{MAX_TEXT_LEN}（附录 A-10）")
        ctx_ids = list(dict.fromkeys(context_entities or ()))
        if len(ctx_ids) > MAX_CONTEXT_ENTITIES:
            raise ValueError(f"context_entities 至多 {MAX_CONTEXT_ENTITIES} 个")
        if prefer_types:
            bad = set(prefer_types) - set(SEM_ENTITY_TYPES)
            if bad:
                raise ValueError(f"prefer_types 非法值 {sorted(bad)}")

        norm, origins = _normalize_with_map(text)
        hits = self._scan(norm)
        sentence_ends = [m.end() for m in _SENTENCE_SPLIT.finditer(norm)]
        mentions: list[dict] = []
        candidates: list[dict] = []

        # ---- 第 1/2 档（exact/alias）先行定案 ----
        resolved_spans: list[tuple[int, dict]] = []   # (sent_idx, mention)
        context_hits: list = []
        for hit in hits:
            if hit["is_context"]:
                context_hits.append(hit)
                continue
            sent = self._sentence_of(hit["i"], sentence_ends)
            others = self._other_entities(hits, hit, sent, sentence_ends)
            pick, resolved_by = self._disambiguate(
                hit["cands"], others, ctx_ids, prefer_types,
                self._sentence_text(norm, sent, sentence_ends),
                norm[hit["i"]:hit["j"]])
            mention = self._mention(text, hit, origins, pick, resolved_by)
            mentions.append(mention)
            resolved_spans.append((sent, mention))
        # ---- 第 3 档（context 短别名）：同句确定命中 + 有关系才保留 ----
        confirmed_by_sent: dict[int, set[int]] = defaultdict(set)
        for sent, m in resolved_spans:
            if not m["ambiguous"]:
                confirmed_by_sent[sent].add(m["entity_id"])
        for hit in context_hits:
            sent = self._sentence_of(hit["i"], sentence_ends)
            confirmed = confirmed_by_sent.get(sent, set())
            keep = [c for c in hit["cands"]
                    if any(e in self.adj[c] for e in confirmed)]
            if not keep:
                continue    # ②③ 丢弃（TC-SEM-04——无佐证不保留）
            others = self._other_entities(hits, hit, sent, sentence_ends)
            pick, resolved_by = self._disambiguate(
                keep, others, ctx_ids, prefer_types,
                self._sentence_text(norm, sent, sentence_ends),
                norm[hit["i"]:hit["j"]])
            mentions.append(
                self._mention(text, hit, origins, pick, resolved_by))

        mentions.sort(key=lambda m: m["span"][0])
        # 歧义候选（TC-SEM-03④——交 agent 追问或自判）
        for m in mentions:
            if m["ambiguous"]:
                for c in m.pop("_cand_ids"):
                    candidates.append(self._candidate(m, c))
        return {"mentions": mentions, "candidates": candidates}

    # ---- 内部 ----

    def _scan(self, norm: str) -> list[dict]:
        """AC 扫描 + overlap 择优（最长优先，等长 weight 高者——TC-SEM-02）。

        空自动机防御（R2/IMPL_BUG）：零可用别名（全 restricted/全 fuzzy_only/
        零实体——T-S9「表现为不存在」与 TC-BUILD-02 的合法极端形态）下
        pyahocorasick 空 trie `make_automaton()` 不生效、`iter()` 抛
        AttributeError——len()==0 短路返回零命中（fail-closed 不变 crash，
        该 org 任何文本零标注）。"""
        if not len(self.automaton):
            return []
        raw = []
        for end_idx, recs in self.automaton.iter(norm):
            j = end_idx + 1
            i = j - len(recs[0]["alias_norm"])
            if not _latin_ok(norm, i, j):
                continue
            cands = sorted(
                {r["entity_id"] for r in recs if r["entity_id"] in self.entities},
                key=lambda eid: (-max(
                    r["weight"] for r in recs if r["entity_id"] == eid), eid))
            if not cands:
                continue
            raw.append({"i": i, "j": j, "cands": cands,
                        "weight": max(r["weight"] for r in recs),
                        "is_context": all(r["match_mode"] == "context"
                                          for r in recs),
                        "kind": _tier_kind(recs)})
        # overlap 择优：长 > weight > 位置
        raw.sort(key=lambda h: (-(h["j"] - h["i"]), -h["weight"], h["i"]))
        chosen: list[dict] = []
        for h in raw:
            if any(not (h["j"] <= c["i"] or h["i"] >= c["j"]) for c in chosen):
                continue
            chosen.append(h)
        chosen.sort(key=lambda h: h["i"])
        return chosen

    def _disambiguate(self, cands, others, ctx_ids, prefer_types,
                      sentence_ctx, span_norm) -> tuple[list[int], str]:
        """四级消歧（TC-SEM-03 + L0 兜底④）。"""
        if len(cands) == 1:
            return cands, "single"
        # ① 共现定案：候选与同句其他命中实体有 1 跳关系
        passing = [c for c in cands if any(e in self.adj[c] for e in others)]
        if len(passing) == 1:
            return passing, "cooccurrence"
        pool = passing if passing else list(cands)
        # ② 会话焦点
        if ctx_ids:
            passing = [c for c in pool if c in ctx_ids]
            if len(passing) == 1:
                return passing, "focus"
            if passing:
                pool = passing
        # ③ 类型先验
        if prefer_types:
            passing = [c for c in pool
                       if self.entities[c]["type"] in set(prefer_types)]
            if len(passing) == 1:
                return passing, "prior"
            if passing:
                pool = passing
        # ④ L0 片段兜底：句内上下文词（去命中面）与候选 L0 片段重叠——唯一
        # 最大者定案（任务书 A2/A3——m2s-3 已入快照的 curated definition）
        ctx_terms = _bigrams(
            normalize_alias(sentence_ctx.replace(span_norm, "")))
        if ctx_terms:
            scores = {c: len(ctx_terms & self.l0_terms.get(c, frozenset()))
                      for c in pool}
            best = max(scores.values())
            if best > 0:
                winners = [c for c in pool if scores[c] == best]
                if len(winners) == 1:
                    return winners, "l0"
        return pool, "ambiguous"

    def _mention(self, text, hit, origins, pick, resolved_by) -> dict:
        eid = pick[0]
        ent = self.entities[eid]
        s = origins[hit["i"]]
        e = origins[hit["j"] - 1] + 1
        matched_by = "context" if hit["is_context"] else hit["kind"]
        base = _TIER_CONFIDENCE[matched_by]
        confidence = min(base, _RESOLVED_CEILING[resolved_by])
        return {
            "span": [s, e],
            "surface": text[s:e],
            "entity_id": eid,
            "entity_key": f'{ent["type"]}:{ent["key"]}',
            "type": ent["type"],
            "name": ent["name"],
            "confidence": round(confidence, 2),
            "via": "ac",
            "matched_by": matched_by,
            "resolved_by": resolved_by,
            "ambiguous": resolved_by == "ambiguous",
            "brief": self._brief(ent),
            "_cand_ids": pick,
        }

    def _candidate(self, mention, eid) -> dict:
        ent = self.entities[eid]
        return {"span": mention["span"], "entity_id": eid,
                "entity_key": f'{ent["type"]}:{ent["key"]}',
                "type": ent["type"], "name": ent["name"], "via": "ac"}

    def _brief(self, ent) -> str | None:
        curated = _loads(ent.get("curated_json"))
        d = curated.get("definition")
        if not d:
            attrs = _loads(ent.get("attrs_json"))
            d = attrs.get("definition") or attrs.get("comment")
        if not d:
            return None
        first = re.split(r"[。；;]", d, maxsplit=1)[0]
        return first[:80] or None

    @staticmethod
    def _sentence_of(i: int, sentence_ends) -> int:
        return sum(1 for e in sentence_ends if e <= i)

    @staticmethod
    def _sentence_text(norm: str, sent: int, sentence_ends) -> str:
        bounds = [0, *sentence_ends]
        start = bounds[sent] if sent < len(bounds) else 0
        end = bounds[sent + 1] if sent + 1 < len(bounds) else len(norm)
        return norm[start:end]

    @staticmethod
    def _other_entities(hits, hit, sent, sentence_ends) -> set[int]:
        """同句其他命中 span 的候选实体全集（共现①的佐证面——其他命中不必
        已定案，候选之一有关系即可定）。"""
        others: set[int] = set()
        bounds = [0, *sentence_ends]
        s_start = bounds[sent] if sent < len(bounds) else 0
        s_end = bounds[sent + 1] if sent + 1 < len(bounds) else 10 ** 9
        for h in hits:
            if h is hit:
                continue
            if s_start <= h["i"] < s_end:
                others.update(h["cands"])
        return others


def _tier_kind(recs) -> str:
    """命中档位：kind=name/code → exact（精确全词）；其余 exact-mode → alias。"""
    kinds = {r["kind"] for r in recs}
    if kinds <= {"name", "code"}:
        return "exact"
    return "alias"


def build_automaton(snapshot: dict) -> tuple[ahocorasick.Automaton, dict]:
    """快照 → AC 自动机（§5.8 产物 2——键 alias_norm、值命中记录列表）。

    只收 `match_mode IN ('exact','context')`（fuzzy_only 防误报不进——
    TC-BUILD-02）；restricted 实体别名不入机（T-S9）。返回 (automaton, meta)
    ——meta 入构建报告（A4：规模与耗时）。"""
    t0 = time.perf_counter()
    entities = {e["id"]: e for e in snapshot["entities"]}
    entries: dict[str, list[dict]] = {}
    skipped_fuzzy = skipped_restricted = 0
    for a in snapshot["aliases"]:
        ent = entities.get(a["entity_id"])
        if ent is None:            # 非 active 端点别名（防御——快照通常已滤）
            continue
        if ent["sensitivity"] == "restricted":
            skipped_restricted += 1
            continue
        if a["match_mode"] not in ("exact", "context"):
            skipped_fuzzy += 1
            continue
        if not a["alias_norm"]:
            continue
        entries.setdefault(a["alias_norm"], []).append({
            "entity_id": a["entity_id"], "kind": a["kind"],
            "match_mode": a["match_mode"], "weight": a["weight"],
            "alias_norm": a["alias_norm"],
        })
    auto = ahocorasick.Automaton()
    for norm, recs in entries.items():
        auto.add_word(norm, recs)
    auto.make_automaton()
    stats = auto.get_stats()
    meta = {
        "keys": len(auto),
        "nodes": stats.get("nodes_count", 0),
        "build_ms": round((time.perf_counter() - t0) * 1000, 3),
        "skipped_fuzzy_only": skipped_fuzzy,
        "skipped_restricted": skipped_restricted,
    }
    return auto, meta


# ---- 服务面：懒加载缓存（T-S12 生命周期） ----

_CACHE: dict[str, tuple[str | None, Annotator | None]] = {}


def clear_annotator_cache() -> None:
    """清空懒加载缓存（测试隔离 / 运维强制重建）。"""
    _CACHE.clear()


def get_annotator(backend, org_id: str, settings) -> tuple[Annotator | None,
                                                            str | None]:
    """按 (org, dict_rev) 懒加载：current ready 构建的 rev 为锚——

    - 缓存命中（同 rev）→ 同一实例（构建中沿用旧实例——T-S12）；
    - 无构建 → (None, None)（未构建不服务识别——先构建再识别的操作序）；
    - rev 漂移（live 快照领先于 last ready——重启窗口等）→ 以 current rev
      标注服务 live 快照实例 + 告警（best-effort；进程内无漂移由缓存保证）。"""
    current = backend.sem_current_build(org_id)
    rev = current["dict_rev"] if current else None
    cached = _CACHE.get(org_id)
    if cached is not None and cached[0] == rev and cached[1] is not None:
        return cached[1], rev
    if current is None:
        return None, None
    snapshot = backend.sem_active_snapshot(org_id)
    ann = Annotator(snapshot)
    from knowledge_lattice.core.semantic.build import (
        _yaml_rev_of, compute_dict_rev,
    )
    live_rev = compute_dict_rev(
        snapshot, embed_model_label=settings.embed_model_label,
        yaml_rev=_yaml_rev_of(snapshot))
    if live_rev != rev:
        logger.warning(
            "annotator snapshot drift: org=%s current_rev=%s live_rev=%s"
            "（live 领先 last ready——重启窗口兜底，以 current rev 标注）",
            org_id, rev, live_rev)
    _CACHE[org_id] = (rev, ann)
    return ann, rev


def annotate_text(backend, settings, org_id: str, text: str, *,
                  context_entities: list[int] | None = None,
                  prefer_types: list[str] | None = None) -> dict:
    """REST/MCP 共用编排：dict_rev 锚点 + mentions（Annotator 内含原文切片）。"""
    ann, rev = get_annotator(backend, org_id, settings)
    if ann is None:
        return {"dict_rev": None, "mentions": [], "candidates": []}
    result = ann.annotate(text, context_entities=context_entities,
                          prefer_types=prefer_types)
    return {"dict_rev": rev, **result}


def render_l0(snapshot: dict) -> dict:
    """L0 片段导出（TC-SEM-06）：l0:true 条目渲染 markdown + token 估算。

    片段 = `- **规范名**（type:key）：definition 首句`（why 追加第二句——
    system prompt 紧凑性）；预算超限由 CI 拦截（TC-YAML-02 L0 行——构建侧
    只导出不重复拦截）。"""
    from knowledge_lattice.core.semantic.yaml_corpus import estimate_tokens

    fragments = []
    for e in sorted(snapshot["entities"], key=lambda x: (x["type"], x["key"])):
        curated = _loads(e.get("curated_json"))
        if not curated.get("l0"):
            continue
        first = re.split(r"[。；;]", curated.get("definition") or "",
                         maxsplit=1)[0]
        text = f'- **{e["name"]}**（{e["type"]}:{e["key"]}）：{first}。'
        why = curated.get("why")
        if why:
            text += why if len(why) <= 60 else why[:59] + "…"
        fragments.append({"entity_key": f'{e["type"]}:{e["key"]}',
                          "type": e["type"], "name": e["name"],
                          "text": text})
    joined = "\n".join(f["text"] for f in fragments)
    return {"fragments": fragments, "token_estimate": estimate_tokens(joined)}


def _loads(text: str | None) -> dict:
    import json

    try:
        return json.loads(text) if text else {}
    except (TypeError, ValueError):
        return {}
