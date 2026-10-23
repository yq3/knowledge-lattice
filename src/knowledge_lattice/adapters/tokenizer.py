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
