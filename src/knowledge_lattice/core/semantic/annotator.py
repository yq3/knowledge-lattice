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
import threading
import time
import unicodedata
from collections import defaultdict

import ahocorasick

from knowledge_lattice.core.semantic.fuzzy import (
    build_fuzzy_terms,
    fuzzy_layers_for_fragment,
)
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
    "l0": 0.9, "default": 0.9, "ambiguous": 0.8,
}

# ---- 模糊兜底（§5.9 第 3 层——m2s-6/M2-S3） ----

# jieba 词性筛选（§5.9 第 3 层「名词性片段」的工程口径）：实词族——n*（名词
# 族）/v*（动词族）/a*（形容词族）/eng（英文）/x（未登录词）。**错别字面
# 常被 jieba 判为动词或未登录词**（「留底」「低扣」非词典词），纯名词族会
# 漏掉主要错字面；虚词/代词/量词/介词排除（误报面控制——三层低置信度候选
# 只进 candidates，负样本误报由 neg_fp 门槛把守）。
_SOLID_POS_PREFIXES = ("n", "v", "a", "eng", "x", "j")
_EXCLUDED_POS = ("uj", "ul", "ug", "p", "c", "u", "r", "m", "q", "d", "t",
                 "f", "b")


def _solid_words(text: str) -> list[tuple[str, str]]:
    """jieba 词性切分 → [(word, flag)]（惰性导入——AC-only 路径零开销）。"""
    import jieba.posseg as pseg

    return [(w.word, w.flag) for w in pseg.cut(text)]


def _noun_fragments(text: str) -> list[tuple[str, int, int]]:
    """模糊层候选片段 [(frag, start, end)]：实词片段（长度 ≥2——§5.9 第 3 层
    「长度 ≥2」）+ **相邻实词对拼接**（bigram）——错别字常把两个词黏成一个
    错字面（「纳税申抱」被切为 纳税+申抱），单一词面查不到整别名；窗口 ≤2
    词覆盖该形态。span 落原文坐标（candidates 契约）。"""
    words = _solid_words(text)
    positions = []
    offset = 0
    for word, flag in words:
        start = text.find(word, offset)
        offset = start + len(word) if start >= 0 else offset
        if (flag.startswith(_SOLID_POS_PREFIXES)
                and flag not in _EXCLUDED_POS and len(word.strip()) >= 2):
            positions.append((start, start + len(word), word.strip()))
    frags: list[tuple[str, int, int]] = []
    for i in range(len(positions)):
        s, e, w = positions[i]
        frags.append((w, s, e))
        if i + 1 < len(positions) and positions[i + 1][0] == e:
            frags.append((w + positions[i + 1][2], s, positions[i + 1][1]))
    return [(f, s, e) for f, s, e in frags
            if s >= 0 and len(normalize_alias(f)) >= 2]


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
        # B2/m2s-5 显式缺省主读：curated default_reading 声明 → norm→entity_id
        #（消解第⑤级——消解不再依赖第一候选 (weight,id) 序；多实体重复声明
        # CI 前置拦截，运行时 first-wins by 实体 id 序防御）
        self.default_reading: dict[str, int] = {}
        for eid in sorted(self.entities):
            declared = _loads(self.entities[eid].get("curated_json")).get(
                "default_reading") or ()
            for value in declared:
                norm = normalize_alias(str(value))
                if norm and norm not in self.default_reading:
                    self.default_reading[norm] = eid
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
        # ---- m2s-6：restricted 持权识别面（T-S9 持权路径）----
        # restricted 别名不进主自动机（无权调用方零暴露）；norm → [(eid, alias 行)]
        # 供 include_restricted=True 的调用方线性扫（极少数敏感实体，线性可承受）。
        self.restricted_entries: dict[str, list[dict]] = defaultdict(list)
        for a in snapshot["aliases"]:
            ent = self.entities.get(a["entity_id"])
            if (ent is not None and ent.get("sensitivity") == "restricted"
                    and a["match_mode"] in ("exact", "context") and a["alias_norm"]):
                self.restricted_entries[a["alias_norm"]].append({
                    "entity_id": a["entity_id"], "kind": a["kind"],
                    "match_mode": a["match_mode"], "weight": a["weight"],
                    "alias_norm": a["alias_norm"],
                })
        # ---- m2s-6：模糊兜底内存面（§5.9 第 3 层 a/b——拼音/编辑距离确定性层；
        #      与构建侧 sem_fuzzy_terms 表同源同口径〔fuzzy.build_fuzzy_terms
        #      纯计算〕，向量层走注入 vec_lookup（SQL 在 store））----
        from knowledge_lattice.core.semantic.fuzzy import fuzzy_layers_for_fragment

        # G-24④（m2-5）：**懒构建**——pypinyin 全量计算是万级词典的秒级固定
        # 开销，fuzzy=False（缺省 annotate/search 主路径）不支付；首次
        # fuzzy=True 识别时构建一次（同实例不重建）。R2/P3-6：构建锁 +
        # 哨兵赋值序——fuzzy_terms **最后**赋值（观察者见 terms 非 None 时
        # 索引必已就绪，消除并发首建窗口的候选静默缺失）+ 无锁重复构建。
        self.fuzzy_terms: list[dict] | None = None
        self.fuzzy_stats: dict = {}
        self._fuzzy_pinyin: dict[str, list[dict]] = {}
        self._fuzzy_dels: dict[str, list[dict]] = {}
        self._fuzzy_lock = threading.Lock()
        self._fuzzy_match = fuzzy_layers_for_fragment

    def _ensure_fuzzy_built(self) -> None:
        """模糊面懒构建（G-24④——一次构建；R2/P3-6 锁防并发重复）。

        赋值序（哨兵语义）：本地构建 → 赋 _fuzzy_pinyin/_fuzzy_dels →
        **最后**赋 fuzzy_terms（None=未就绪的完成哨兵——并发请求要么见
        全空（自行抢锁构建）、要么见全就绪，无中间态）。
        """
        if self.fuzzy_terms is not None:
            return
        with self._fuzzy_lock:
            if self.fuzzy_terms is not None:  # 双重检查——竞争者已构建完成
                return
            pinyin, dels, stats, term_rows = self._build_fuzzy_locked()

    def _build_fuzzy_locked(self) -> tuple[dict, dict, dict, list[dict]]:
        """持锁构建（一次性本地结果 → 按哨兵序发布）。"""
        term_rows, _del_rows, stats = build_fuzzy_terms(
            self.snapshot, None, embed_model_label="")
        pinyin: dict[str, list[dict]] = defaultdict(list)
        dels: dict[str, list[dict]] = defaultdict(list)
        for idx, t in enumerate(term_rows):
            if t["pinyin"]:
                pinyin[t["pinyin"]].append(t)
            if t["kind"] != "definition" and t["term_len"] >= 4:
                from knowledge_lattice.core.semantic.fuzzy import del_keys

                for key in del_keys(t["text_norm"]):
                    dels[key].append({"idx": idx})
        self.fuzzy_stats = stats
        self._fuzzy_pinyin = pinyin
        self._fuzzy_dels = dels
        self.fuzzy_terms = term_rows   # 哨兵最后赋值
        return pinyin, dels, stats, term_rows

    # ---- 主入口 ----

    def annotate(
        self, text: str, *, context_entities: list[int] | None = None,
        prefer_types: list[str] | None = None,
        fuzzy: bool = False,
        include_restricted: bool = False,
        vec_lookup=None,
        vec_top: int = 3,
    ) -> dict:
        """文本 → 类型化实体标注（§6.3 契约：mentions + candidates）。

        - fuzzy=True（§5.9 第 3 层——m2s-6）：对未被 AC 层覆盖的名词性片段
          （jieba 词性筛选）跑三层兜底（拼音 → 编辑距离 → 向量近邻），结果
          via='fuzzy'、confidence 一律低于第 1 层、**落 candidates 不进
          mentions**（G-2 并存裁定：中间件注入一行低信任提示）；向量层经
          vec_lookup(frag_text) -> list[{entity_id, sim}] 注入（SQL 在 store）；
          vec_top=向量层每片段实体截断（G-24⑤——m2-5 缺省 3，编排面经
          settings.semantic_fuzzy_vec_top 传入）；
        - include_restricted=True（T-S9 持权路径——semantic:restricted 调用
          方）：restricted 实体别名参与识别（无权调用方零暴露——build 时
          不入主自动机，本参数只对持权请求生效）。"""
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
        if include_restricted and self.restricted_entries:
            hits = self._merge_restricted(hits, self._scan_restricted(norm))
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
            # mixed-mode 候选级门槛（G-21 P3-5）：**维持 span 级行为再挂**——
            # 参考词典存在刻意的 mixed 歧义面（「留抵」＝exact〔retained_
            # credit〕+ context〔retained_refund，带 disambiguation 声明〕），
            # ctx-only 候选按候选级剔除会使歧义消歧面（TC-SEM-03④/L0 兜底）
            # 失去一半候选 → 识别评测 ambiguity 门槛（≥0.85）失守（m2s-6
            # 实测 0.75）。context 模式别名在 mixed span 参与消歧是词典设计
            # 意图（CI 规则：歧义别名至少一方 disambiguation 或标 context）
            # ——候选级门槛需连同词典口径重设计，登记 known-gaps G-21 再挂。
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
        # 歧义候选（TC-SEM-03④——交 agent 追问或自判）；随后统一剥内部键
        #（P3-1/R3：非歧义 mention 也不携带 `_cand_ids`——API/MCP JSON 面
        # 无下划线私有字段）
        for m in mentions:
            if m["ambiguous"]:
                for c in m["_cand_ids"]:
                    candidates.append(self._candidate(m, c))
        for m in mentions:
            m.pop("_cand_ids", None)

        # ---- 第 3 层模糊兜底（fuzzy=True——§5.9；落 candidates 不进 mentions）----
        if fuzzy:
            self._ensure_fuzzy_built()
            candidates.extend(
                self._fuzzy_candidates(text, mentions, vec_lookup=vec_lookup,
                                       vec_top=vec_top))
        return {"mentions": mentions, "candidates": candidates}

    # ---- 内部 ----

    def _scan(self, norm: str) -> list[dict]:
        """AC 扫描 + overlap 择优（最长优先，等长 weight 高者——TC-SEM-02）。

        空自动机防御（R2/IMPL_BUG）：零可用别名（全 restricted/全 fuzzy_only/
        零实体——T-S9「表现为不存在」与 TC-BUILD-02 的合法极端形态）下
        pyahocorasick 空 trie `make_automaton()` 不生效、`iter()` 抛
        AttributeError——len()==0 短路返回零命中（fail-closed 不变 crash，
        该 org 任何文本零标注）。

        hit["ctx_only"]：该 span 内全部命中行均为 context 模式的实体集合
        （mixed-mode 候选级门槛面——G-21 P3-5/m2s-6）。"""
        if not len(self.automaton):
            return []
        raw = []
        for end_idx, recs in self.automaton.iter(norm):
            j = end_idx + 1
            i = j - len(recs[0]["alias_norm"])
            if not _latin_ok(norm, i, j):
                continue
            ctx_only = {r["entity_id"] for r in recs
                        if r["entity_id"] in self.entities
                        and all(x["match_mode"] == "context"
                                for x in recs if x["entity_id"] == r["entity_id"])}
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
                        "kind": _tier_kind(recs),
                        "ctx_only": ctx_only})
        # overlap 择优：长 > weight > 位置
        raw.sort(key=lambda h: (-(h["j"] - h["i"]), -h["weight"], h["i"]))
        chosen: list[dict] = []
        for h in raw:
            if any(not (h["j"] <= c["i"] or h["i"] >= c["j"]) for c in chosen):
                continue
            chosen.append(h)
        chosen.sort(key=lambda h: h["i"])
        return chosen

    def _scan_restricted(self, norm: str) -> list[dict]:
        """restricted 别名线性扫（持权路径——极少数面，线性可承受；与 AC 面
        同构产出 hit：latin 边界 + overlap 择优交并侧统一处理）。"""
        raw = []
        for rnorm, recs in self.restricted_entries.items():
            start = 0
            while True:
                i = norm.find(rnorm, start)
                if i < 0:
                    break
                j = i + len(rnorm)
                start = j
                if not _latin_ok(norm, i, j):
                    continue
                cands = sorted(
                    {r["entity_id"] for r in recs
                     if r["entity_id"] in self.entities},
                    key=lambda eid: (-max(
                        r["weight"] for r in recs if r["entity_id"] == eid), eid))
                if cands:
                    raw.append({"i": i, "j": j, "cands": cands,
                                "weight": max(r["weight"] for r in recs),
                                "is_context": all(
                                    r["match_mode"] == "context" for r in recs),
                                "kind": _tier_kind(recs),
                                "ctx_only": set()})
        return raw

    @staticmethod
    def _merge_restricted(hits: list[dict], restricted_hits: list[dict],
                          ) -> list[dict]:
        """AC hits + restricted hits 统一 overlap 择优（长 > weight > 位置）。"""
        merged = list(hits) + list(restricted_hits)
        merged.sort(key=lambda h: (-(h["j"] - h["i"]), -h["weight"], h["i"]))
        chosen: list[dict] = []
        for h in merged:
            if any(not (h["j"] <= c["i"] or h["i"] >= c["j"]) for c in chosen):
                continue
            chosen.append(h)
        chosen.sort(key=lambda h: h["i"])
        return chosen

    def _fuzzy_candidates(self, text: str, mentions: list[dict],
                          *, vec_lookup, vec_top: int = 3) -> list[dict]:
        """§5.9 第 3 层：未被 AC 层覆盖的名词性片段 × 三层兜底 → candidates。

        - 名词筛选（jieba 词性）+ 长度 ≥2；片段与任一 mention span 重叠即跳过；
        - 拼音完全匹配 → 编辑距离 ≤1（长度 ≥4）→ 向量近邻（阈值 0.75 top-3
          ——vec_lookup 注入），依次短路（同片段只取首个命中层）；
        - via='fuzzy'、confidence 分层且一律低于第 1 层（0.75/0.65/0.55 < 0.9）；
        - 索引直读实例映射（G-24④——m2-5 去除每片段 dict() 全量复制；
          fuzzy_layers_for_fragment 只读 .get 无 mutate）；vec_top 为向量层
          每片段实体截断（G-24⑤——缺省 3，编排面注入 settings 值）。"""
        from knowledge_lattice.core.semantic.fuzzy import FUZZY_CONFIDENCE

        covered = [(m["span"][0], m["span"][1]) for m in mentions]
        out: list[dict] = []
        for word, start, end in _noun_fragments(text):
            if any(start < ce and end > cs for cs, ce in covered):
                continue
            frag_norm = normalize_alias(word)
            if not frag_norm or len(frag_norm) < 2:
                continue
            layer = term = None
            for lay, t in self._fuzzy_match(
                frag_norm, pinyin_index=self._fuzzy_pinyin,
                del_index=self._fuzzy_dels, terms=self.fuzzy_terms or (),
            ):
                layer, term = lay, t
                break
            if layer is None and vec_lookup is not None:
                try:
                    vec_hits = vec_lookup(word) or []
                except Exception as exc:  # noqa: BLE001 —— 向量层失败降级为跳过
                    logger.warning("fuzzy vec_lookup failed: %s", exc)
                    vec_hits = []
                seen: set[int] = set()
                for v in vec_hits:
                    eid = v.get("entity_id")
                    if eid in seen or eid not in self.entities:
                        continue
                    seen.add(eid)
                    out.append(self._fuzzy_candidate(
                        start, end, word, eid, "vec", v.get("text_norm"),
                        confidence=FUZZY_CONFIDENCE["vec"], sim=v.get("sim")))
                    if len(seen) >= max(1, vec_top):
                        break
            elif layer is not None:
                out.append(self._fuzzy_candidate(
                    start, end, word, term["entity_id"], layer,
                    term["text_norm"],
                    confidence=FUZZY_CONFIDENCE[layer]))
        return out

    def _fuzzy_candidate(self, start: int, end: int, surface: str, eid: int,
                         layer: str, term: str, *, confidence: float,
                         sim=None) -> dict:
        ent = self.entities[eid]
        row = {"span": [start, end], "surface": surface, "entity_id": eid,
               "entity_key": f'{ent["type"]}:{ent["key"]}',
               "type": ent["type"], "name": ent["name"], "via": "fuzzy",
               "fuzzy_layer": layer, "confidence": round(confidence, 2),
               "term": term}
        if sim is not None:
            row["sim"] = round(float(sim), 4)
        return row

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
        # ⑤ 显式缺省主读（B2/m2s-5）：YAML default_reading 声明——人工显式
        # 配置证据定案（confidence 上限 0.9——非确证不自动注入）；消解不再
        # 依赖第一候选 (weight,id) 序（G-21 R3：换库/换同步序不翻转读法）
        default_eid = self.default_reading.get(span_norm)
        if default_eid is not None and default_eid in pool:
            return [default_eid], "default"
        return pool, "ambiguous"

    def _mention(self, text, hit, origins, pick, resolved_by) -> dict:
        eid = pick[0]
        ent = self.entities[eid]
        s = origins[hit["i"]]
        e = origins[hit["j"] - 1] + 1
        matched_by = "context" if hit["is_context"] else hit["kind"]
        base = _TIER_CONFIDENCE[matched_by]
        confidence = min(base, _RESOLVED_CEILING[resolved_by])
        mention = {
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
        # G-24⑦（m3-3 裁定①）：mention 契约补可选 disambiguation——
        # design §6.3② 中间件 L1 注入规则字面「概念/系统：name + brief +
        # disambiguation」，数据来源 = curated_json.disambiguation（YAML
        # {not, hint}——自然落位）；无数据不出现该键（向后兼容非决策变更）。
        disamb = self._disambiguation(ent)
        if disamb:
            mention["disambiguation"] = disamb
        return mention

    def _disambiguation(self, ent) -> list[dict]:
        """curated disambiguation 携带面（[{not, hint}] 原样——畸形行防御跳过）。"""
        curated = _loads(ent.get("curated_json"))
        out = []
        for d in curated.get("disambiguation") or ():
            if not isinstance(d, dict):
                continue
            row = {}
            if d.get("not"):
                row["not"] = str(d["not"])
            if d.get("hint"):
                row["hint"] = str(d["hint"])
            if row:
                out.append(row)
        return out

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
        # P2-3/R3：任务 A1「内存占用与构建耗时纳入构建报告」——get_stats()
        # 全量透传：total_size（sizeof_node×nodes，字节）/ links_count（trie
        # 边数）/ words_count（入机词量）
        "memory_bytes": stats.get("total_size", 0),
        "edges": stats.get("links_count", 0),
        "words": stats.get("words_count", 0),
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
    annotate 与 `/semantic/l0` 共用本路径（P2-1 方案 B/R3：同一实例同锚点，
    内容/rev 两侧一致）。

    - 缓存命中（同 rev）→ 同一实例（构建中沿用旧实例——T-S12 热缓存路径）；
    - 无构建 → (None, None)（未构建不服务识别——先构建再识别的操作序）；
    - **G-21 方案 A（m2s-5 收口）**：current build 的快照附表
      （sem_build_snapshots——迁移 0008）优先——**冷缓存/重启后服务 build
      产物而非 live**（rev 锚点失真窗口消除；评测拦下的词典重启后不再被
      服务）；快照与 ready 切换同事务，ready 可见时必已在位；
    - 无快照（0008 之前存量 ready 行）→ 回退 live 快照 + **告警**
      （best-effort 兼容路径——G-21 回退告警保留；live 领先 last ready 的
      drift 告警同款保留）。"""
    current = backend.sem_current_build(org_id)
    rev = current["dict_rev"] if current else None
    cached = _CACHE.get(org_id)
    if cached is not None and cached[0] == rev and cached[1] is not None:
        return cached[1], rev
    if current is None:
        return None, None
    snap_json = backend.sem_load_build_snapshot(org_id, current["id"])
    if snap_json is not None:
        import json

        _CACHE[org_id] = (rev, Annotator(json.loads(snap_json)))
        return _CACHE[org_id][1], rev
    snapshot = backend.sem_active_snapshot(org_id)
    logger.warning(
        "build snapshot missing: org=%s build_id=%s——fallback to live snapshot"
        "（0008 前存量 ready 行的兼容路径——G-21 方案 A 回退面）",
        org_id, current["id"],
    )
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
            "（live 领先 last ready——回退路径的已知失真，G-21 方案 A 收口后"
            "仅存量行可触达）",
            org_id, rev, live_rev)
    _CACHE[org_id] = (rev, ann)
    return ann, rev


def annotate_text(backend, settings, org_id: str, text: str, *,
                  context_entities: list[int] | None = None,
                  prefer_types: list[str] | None = None,
                  fuzzy: bool = False,
                  include_restricted: bool = False,
                  embedder=None,
                  embed_batch=None,
                  gate=None,
                  breakers: dict | None = None,
                  user_id: str | None = None) -> dict:
    """REST/MCP 共用编排：dict_rev 锚点 + mentions（Annotator 内含原文切片）。

    - fuzzy=True（§5.9 第 3 层——m2s-6）：向量层经注入 embedder（缺省
      settings 侧不构造——无 embedder 则该层跳过，拼音/编辑距离层照常）+
      backend.sem_fuzzy_vec_search（阈值 0.75 top-3，SQL 在 store）；
      embed_batch(texts) 可覆盖批量嵌入（评测/测试确定性注入面）；
    - include_restricted=True（T-S9 持权路径）：restricted 实体参与识别——
      由 api/mcp 层按调用方 membership role 判定后传入（core 不查权限）；
    - **G-24⑨后半（m3-3/issue #15）**：fuzzy vec 层嵌入经
      ``settings.query_embed_timeout_s`` 有界等待 + 共享熔断
      （``breakers["embed"]``）+ ``search.degraded``（scope=annotate）降级
      审计——沿 search_entities G-24③ m2-5 实装口径（此前走 embed_timeout_s
      =30s 同步嵌入、无 breaker、无审计）；embed_batch 注入面（评测确定性）
      不走有界/熔断，但 gate 拒绝时 vec 层照常整体关闭；
    - **G-24⑨前半（m3-3）**：``gate.rejected``（探针拒绝档）→ fuzzy vec
      层关闭不发嵌入调用（NFR-8/§5.2「查询侧向量路关闭」跨切面一致）+
      probe_reject 降级审计（与 docs 检索同源语义）。"""
    ann, rev = get_annotator(backend, org_id, settings)
    if ann is None:
        return {"dict_rev": None, "mentions": [], "candidates": []}
    gate_rejected = gate is not None and gate.rejected
    if fuzzy and gate_rejected:
        _audit_annotate_vec_degraded(backend, org_id, user_id, "probe_reject")
        logger.warning("annotate fuzzy vec layer closed: probe rejected")
    vec_lookup = None
    if fuzzy and not gate_rejected:
        if embed_batch is not None:
            def vec_lookup(fragment: str) -> list[dict]:
                vectors = embed_batch([fragment])
                vec = vectors[0] if vectors else None
                if vec is None:
                    return []
                return _vec_hits(backend, settings, org_id, vec)
        elif embedder is not None:
            def vec_lookup(fragment: str) -> list[dict]:
                from knowledge_lattice.core.semantic.lookup import (
                    embed_query_bounded,
                )

                vec = embed_query_bounded(
                    backend, settings, embedder, fragment, org_id=org_id,
                    user_id=user_id, breakers=breakers, scope="annotate",
                )
                if vec is None:
                    return []
                return _vec_hits(backend, settings, org_id, vec)
    result = ann.annotate(
        text, context_entities=context_entities, prefer_types=prefer_types,
        fuzzy=fuzzy, include_restricted=include_restricted,
        vec_lookup=vec_lookup,
        # G-24⑤（m2-5）：vec 实体截断经 settings 注入（LATTICE_SEM_FUZZY_VEC_TOP
        # 端到端消费——此前 store 查询侧已消费、annotator 侧硬编码 3）
        vec_top=max(1, int(getattr(settings, "semantic_fuzzy_vec_top", 3) or 3)),
    )
    return {"dict_rev": rev, **result}


def _vec_hits(backend, settings, org_id: str, vec) -> list[dict]:
    """查询向量 → sem_fuzzy_vec_search 结果整形（实体去重保最优 + min_sim）。"""
    hits = backend.sem_fuzzy_vec_search(
        org_id, vec, embed_model=settings.embed_model_label,
        top_k=settings.semantic_fuzzy_vec_top,
        min_sim=settings.semantic_fuzzy_vec_threshold,
    )
    best: dict[int, dict] = {}
    for h in hits:
        if h["sim"] < settings.semantic_fuzzy_vec_threshold:
            continue
        if h["entity_id"] not in best or h["sim"] > best[h["entity_id"]]["sim"]:
            best[h["entity_id"]] = h
    return sorted(best.values(), key=lambda h: -h["sim"])


def _audit_annotate_vec_degraded(backend, org_id, user_id, reason) -> None:
    """annotate fuzzy vec 层降级审计（G-24⑨——search.degraded scope=annotate；
    写失败仅告警——增益路语义不阻断识别）。"""
    import json as _json

    try:
        backend.append_outbox(
            "search.degraded",
            _json.dumps(
                {"user_id": user_id, "org_id": org_id,
                 "reasons": [reason], "scope": "annotate"},
                ensure_ascii=False,
            ),
        )
    except Exception:  # noqa: BLE001
        logger.exception("search.degraded (annotate) audit write failed")


def _default_embed_batch(backend, settings, org_id, embedder):
    """向量层缺省嵌入通道：embedder 注入（None → 该层恒空——不阻断前两层）。

    m3-3 G-24⑨后半后：本通道仅供未接 query_embed_timeout_s/breaker 的旧
    调用面兼容——REST/MCP 端点已改经 embed_query_bounded（有界+熔断+审计）。"""
    if embedder is None:
        return lambda texts: [None] * len(texts)

    def _embed(texts: list[str]) -> list:
        try:
            return embedder.embed(texts)
        except Exception:  # noqa: BLE001 —— 嵌入失败向量层降级（G-1 语义）
            logger.warning("fuzzy vec embed degraded: org=%s", org_id)
            return [None] * len(texts)

    return _embed


def render_l0(snapshot: dict) -> dict:
    """L0 片段导出（TC-SEM-06）：l0:true 条目渲染 markdown + token 估算。

    片段 = `- **规范名**（type:key）：definition 首句`（why 追加第二句——
    system prompt 紧凑性）；预算超限由 CI 拦截（TC-YAML-02 L0 行——构建侧
    只导出不重复拦截）。"""
    from knowledge_lattice.core.semantic.yaml_corpus import estimate_tokens

    fragments = []
    for e in sorted(snapshot["entities"], key=lambda x: (x["type"], x["key"])):
        # P1-1/R3：restricted 实体不进 L0 导出——L0 是 agent system prompt 的
        # 输入面（semantic:read 全员可见），正文泄露比 alias 命中严重；
        # fail-closed，M2-S3 权限面交付后按 semantic:restricted 放行
        if e.get("sensitivity") == "restricted":
            continue
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
