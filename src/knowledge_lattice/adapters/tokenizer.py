"""jieba 预分词（design §3 adapters/tokenizer.py——生成 content_seg / title_seg；查询侧切分同源）。

分层口径：语言处理（分词）在 adapters；方言转义（SQLite 双引号包裹 / PG to_tsquery）
收口 store/<dialect>/fts.py（D24——同一分词器产出 token、各自按目标语法转义）。
jieba 首次切分构建前缀词典（~1s，进程内缓存）。
"""

from __future__ import annotations

import re
from functools import lru_cache

_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]")


@lru_cache(maxsize=1)
def _cut() -> None:
    import jieba

    jieba.initialize()


def segment(text: str) -> list[str]:
    """文本 → token 列表（jieba 精确模式；过滤空白片段，保留原大小写）。"""
    if not text:
        return []
    _cut()
    import jieba

    return [t for t in jieba.cut(text) if t.strip()]


def segment_query(query: str) -> list[str]:
    """查询侧切分：过滤纯标点 token（unicode61 不索引纯标点、空 token 有 malformed 风险——TC-FTS-01）。"""
    return [t for t in segment(query) if _WORD_RE.search(t)]


def join_seg(text: str) -> str:
    """分词后空格连接（FTS 索引列存储形态——content_seg / title_seg）。"""
    return " ".join(segment(text))


def token_count(text: str) -> int:
    """token 数（结构感知切分 256–512 的计量单位——TC-ING-02）。"""
    return len(segment(text))


# ============ 中文分词效果判据 + 词表/trigram 兜底判定（M1-1——TC-FTS-05） ============
#
# design §10「jieba 中英混排：tokenizer 独立模块（可换 trigram/自定义词表）；M1
# 真实 query 标注集是判据」；调研沉淀（research/enterprise-rag/blog/04:91、
# blog/10:87）：应用层 jieba 预分词是既有路线，不达标时兜底两路——自定义词表
# （运营可修：业务术语 add_word 后对齐恢复）与 FTS trigram 索引（子串召回，
# schema 变更）。黄金集全量校准留 M1-4（TC-EVAL）；本组函数为判据落点。


def token_alignment(query: str, content: str) -> float:
    """效果判据：query 与语料经同一分词器切分后的 token 对齐率。

    对齐率 = |query tokens ∩ content tokens| / |query tokens|（去重集合比）。
    **零交集（=0.0）⇒ BM25 召回为空**（预分词列只含切出的 token，MATCH/
    tsquery 均无命中）；部分对齐 (0,1) 在 SQLite（OR 拼接）语义下**仍可召回**
    （任一 token 命中即进候选）、在 PG（`&` 全 token AND）语义下不召回——
    后端差异口径（design §5.2 / A-17），黄金集校准须分后端评估。
    """
    q_tokens = {t for t in segment_query(query) if t.strip()}
    if not q_tokens:
        return 1.0  # 空查询无对齐语义（调用方本就不发起 BM25 路）
    c_tokens = set(segment(content))
    return len(q_tokens & c_tokens) / len(q_tokens)


def cjk_fallback_verdict(
    query: str, content: str, *, dict_terms: tuple[str, ...] | list[str] = ()
) -> str:
    """兜底判定：按「交集是否为空」定 zero-recall，(0,1) 单列部分对齐档。

    - "ok"：对齐率 1.0（全 token 对齐——无需兜底）；
    - "partial"：部分对齐 (0,1)——SQLite OR 语义下仍可召回（不触发兜底）；
      PG `&` 语义下不召回，黄金集分后端评估（M1-4）；
    - "dict"：零交集且 query 为已登记业务术语（dict_terms）——add_word 后对齐
      恢复（词表兜底路径，实测有效见 TC-FTS-05）；
    - "trigram"：零交集且词表不可修（未登记 / 仅子串关系可召回）——需 FTS
      trigram 索引/列兜底（schema 变更，M1-4 黄金集校准后按需启用）。
    """
    rate = token_alignment(query, content)
    if rate == 1.0:
        return "ok"
    if rate > 0.0:
        return "partial"
    if query in dict_terms:
        return "dict"
    return "trigram"
