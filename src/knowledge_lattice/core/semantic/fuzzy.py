"""模糊兜底纯计算面（design §5.9 第 3 层 / §5.8 构建产物 2「模糊索引」——m2s-6）。

三层（FR-S3）：

1. **拼音完全匹配**（同音错字——「留底」→「留抵」）：fragment 与 term 的
   无声调全拼相等；
2. **编辑距离 ≤1**（仅长度 ≥4 的 name/alias）：deletion neighborhood 桶查
   ——两词编辑距离 ≤1 ⟺ 各自 deletion 键集合相交（O(len) 索引、免两两比对）；
3. **语义近邻**（阈值 0.75 top-3）：fragment 向量 vs sem_fuzzy_terms 向量
   （查询时经 Embedder provider 现嵌——向量层 SQL 走 backend，本模块零 SQL）。

纯计算（拼音/编辑距离/term 构建均可离线确定性复算）；向量生成经注入的
Embedder provider（构建侧一次全量、标签随 config 钉死且入 dict_rev——
换模型强制重算，§5.8 产物 2）。embedder 缺失/失败 → 向量列空（构建降级
态——拼音/编辑距离层仍可用，模糊层非可用性前提不阻断构建）。

term 面（design §5.8「名称/别名/一句话定义」）：

- name：实体规范名（kind='name'——拼音 + 编辑距离 + 向量三层全用）；
- alias：全部别名（含 fuzzy_only——本就是模糊层的输入面；拼音 + 编辑距离
  + 向量）；
- definition：一句话定义首句（kind='definition'——**仅向量层**：拼音/编辑
  距离对长句无意义，不产 pinyin/del 键）。
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable

from knowledge_lattice.core.semantic.norm import normalize_alias

logger = logging.getLogger(__name__)

__all__ = [
    "pinyin_norm", "edit_distance_at_most_1", "del_keys",
    "build_fuzzy_terms", "fuzzy_layers_for_fragment",
    "FUZZY_CONFIDENCE", "EDIT_MIN_TERM_LEN",
]

# 三层 confidence（「一律低于第 1 层」——AC 层 context 档 0.9，模糊层最高 0.75）
FUZZY_CONFIDENCE = {"pinyin": 0.75, "edit": 0.65, "vec": 0.55}
# 编辑距离层 term 长度门槛（design §5.9 第 3 层 b——短词编辑距离 1 误报面大）
EDIT_MIN_TERM_LEN = 4
# 编辑距离层 fragment 长度门槛（与 term 侧对称——长度 ≥4 才查桶）
EDIT_MIN_FRAGMENT_LEN = 4

_SENT_SPLIT = re.compile(r"[。；;，,、\n]")


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def pinyin_norm(text: str) -> str:
    """无声调全拼小写（拼音层键——纯 latin/数字输入原样返回：latin 无同音
    错字面、键即自身，拼音库零调用）。"""
    norm = normalize_alias(text)
    if not norm:
        return ""
    if not _has_cjk(norm):
        return norm.lower()
    from pypinyin import lazy_pinyin

    return "".join(
        p.lower() for p in lazy_pinyin(norm, errors="ignore") if p)


def edit_distance_at_most_1(a: str, b: str) -> bool:
    """编辑距离 ≤1 判定（长度差 >1 短路；单趟指针扫描）。"""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = diff = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        diff += 1
        if diff > 1:
            return False
        if len(a) == len(b):       # 替换：双指针各进一
            i += 1
            j += 1
        else:                      # 插入（b 多一字符）：j 单进
            j += 1
    # 尾部残留 ≤1 字符（长度差）视为一次插入
    return (len(b) - j) + (len(a) - i) <= 1 and diff <= 1


def del_keys(term: str) -> set[str]:
    """deletion neighborhood 键集：{term} ∪ {term 去第 i 位 | i < len(term)}
    ——两词键集相交 ⟺ 编辑距离 ≤1（经典 delete-1 索引）。"""
    return {term} | {term[:i] + term[i + 1:] for i in range(len(term))}


def definition_first_sentence(curated: dict) -> str:
    """一句话定义首句（kind='definition' 的 term 文本——拼音/编辑距离不用）。"""
    d = curated.get("definition") or ""
    return _SENT_SPLIT.split(d.strip(), maxsplit=1)[0].strip() if d else ""


def build_fuzzy_terms(
    snapshot: dict,
    embed_fn: Callable[[list[str]], list[list[float] | None]] | None = None,
    *,
    embed_model_label: str,
) -> tuple[list[dict], list[dict], dict]:
    """快照 → (term_rows, del_rows, stats)——构建产物模糊索引的计算面。

    - restricted 实体**不进**模糊索引（T-S9：无权调用方的 fuzzy 候选同样
      表现为不存在——fail-closed；持权路径的 restricted 识别走 AC 面，不走
      模糊层）；
    - embed_fn(texts) 批量嵌入（构建侧一次全量）；None 或部分失败 → 对应行
      embedding=None（stats.vec_skipped 注记——拼音/编辑距离层不受影响）；
    - del_rows 的 term_idx 指向 term_rows 下标（store 侧映射新插入 id）；
    - 同一实体同文本多别名去重（text_norm+kind 唯一）。
    """
    entities = {e["id"]: e for e in snapshot["entities"]}
    term_rows: list[dict] = []
    seen: set[tuple[int, str, str]] = set()
    pending: list[int] = []            # 需要嵌入的行下标
    for eid, ent in entities.items():
        if ent.get("sensitivity") == "restricted":
            continue
        candidates: list[tuple[str, str]] = [("name", ent["name"])]
        import json

        for a in snapshot["aliases"]:
            if a["entity_id"] != eid:
                continue
            candidates.append(("alias", a["alias"]))
        curated = {}
        try:
            curated = json.loads(ent.get("curated_json") or "{}")
        except (TypeError, ValueError):
            curated = {}
        first = definition_first_sentence(curated)
        if first:
            candidates.append(("definition", first))
        for kind, text in candidates:
            norm = normalize_alias(str(text or ""))
            if not norm:
                continue
            key = (eid, kind, norm)
            if key in seen:
                continue
            seen.add(key)
            row = {
                "entity_id": eid, "kind": kind, "text_norm": norm,
                "term_len": len(norm),
                # NFKC 后 CJK 兼容字符折叠（全角字母等）——拼音键稳定
                "pinyin": pinyin_norm(unicodedata.normalize("NFKC", norm))
                if kind in ("name", "alias") else "",
                "embed_model": embed_model_label,
                "embedding": None,
            }
            term_rows.append(row)
            pending.append(len(term_rows) - 1)

    vec_skipped = False
    if embed_fn is not None and pending:
        texts = [term_rows[i]["text_norm"] for i in pending]
        try:
            vectors = embed_fn(texts)
            for i, vec in zip(pending, vectors):
                if vec is not None:
                    term_rows[i]["embedding"] = list(vec)
                else:
                    vec_skipped = True
        except Exception as exc:  # noqa: BLE001 —— 嵌入不可达不阻断构建（降级注记）
            vec_skipped = True
            logger.warning(
                "fuzzy index vector embed failed (%s: %s)——向量层降级为空"
                "（拼音/编辑距离层不受影响）", type(exc).__name__, exc)

    del_rows: list[dict] = []
    for idx, row in enumerate(term_rows):
        if row["kind"] == "definition":
            continue                       # 一句话定义只进向量层
        if row["term_len"] < EDIT_MIN_TERM_LEN:
            continue                       # 编辑距离层仅长度 ≥4（§5.9 第 3 层 b）
        for key in del_keys(row["text_norm"]):
            del_rows.append({"del_key": key, "term_idx": idx})

    stats = {
        "terms": len(term_rows),
        "dels": len(del_rows),
        "vec_embedded": sum(1 for r in term_rows if r["embedding"] is not None),
        "vec_skipped": vec_skipped,
    }
    return term_rows, del_rows, stats


def fuzzy_layers_for_fragment(
    frag_norm: str,
    *,
    pinyin_index: dict[str, list[dict]],
    del_index: dict[str, list[dict]],
    terms: list[dict],
) -> list[tuple[str, dict]]:
    """fragment → 拼音层/编辑距离层命中（确定性两层——向量层另走注入查询）。

    返回 [(layer, term_row)]——拼音层完全匹配优先、编辑距离层次之；命中即
    短路（同 fragment 只取首个命中层，FR-S3「依次」语义）。term_row 含
    entity_id/text_norm。"""
    if not frag_norm:
        return []
    # ① 拼音完全匹配（同音错字）——fragment 自身恰为某 term 时属 AC 层面，
    # 不算模糊命中（排除）
    pin = pinyin_norm(frag_norm)
    if pin:
        for t in pinyin_index.get(pin, ()):
            if t["text_norm"] != frag_norm:
                return [("pinyin", t)]
    # ② 编辑距离 ≤1（fragment 与 term 均长度 ≥4）——多 term 命中取最短
    #（与 fragment 最相近的长度面；确定性 tie-break：长度 → text_norm 字典序）
    if len(frag_norm) >= EDIT_MIN_FRAGMENT_LEN:
        hits: list[tuple[int, str, dict]] = []
        seen_idx: set[int] = set()
        for key in del_keys(frag_norm):
            for t in del_index.get(key, ()):
                if t["idx"] in seen_idx:
                    continue
                seen_idx.add(t["idx"])
                row = terms[t["idx"]]
                if row["text_norm"] == frag_norm:
                    continue               # AC 层面（精确命中）
                if row["term_len"] < EDIT_MIN_TERM_LEN:
                    continue
                if edit_distance_at_most_1(frag_norm, row["text_norm"]):
                    hits.append((abs(len(frag_norm) - row["term_len"]),
                                 row["text_norm"], row))
        if hits:
            hits.sort(key=lambda h: (h[0], h[1]))
            return [("edit", hits[0][2])]
    return []
