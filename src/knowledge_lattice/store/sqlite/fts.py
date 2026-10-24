"""FTS5 查询侧转义（design §4 查询侧口径——token 双引号包裹、内部 `"` → `""`、OR 拼接）。

M0a-3 落地（acl_render.py 注记的 fts.py）：
- 查询串经 jieba 切分（adapters/tokenizer.segment_query——纯标点 token 已滤）；
- 每个 token 双引号包裹为字面量短语 → AND/NEAR/OR/NOT/*/- 一律不激活为操作符（TC-FTS-01）；
- token 间以 OR 拼接（召回复利：任一 token 命中即召回）；
- 五列加权 bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)（五列按序 title/content/keywords/llm/tags——
  TC-FTS-02；bm25 越小越相关，ORDER BY ASC）。

转义产物经绑定参数进 SQL（acl_render.Match → :q），绝不拼接进 SQL 文本。
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# 五列加权参数（design §5.2——title_seg 3 / content_seg 1 / keywords 5 / llm_keywords 0.5 / tags 8）
BM25_WEIGHTS = "3.0, 1.0, 5.0, 0.5, 8.0"

# 与 adapters/tokenizer.segment_query 同口径：无字词字符的 token 不进表达式
# （unicode61 不索引纯标点；空 token 在部分 FTS5 版本 malformed——TC-FTS-01 防御）
_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]")


def escape_token(token: str) -> str:
    """token → 双引号包裹的 FTS5 字面量短语（内部 `"` 转义为 `""`）。"""
    return '"' + token.replace('"', '""') + '"'


def build_match_expr(tokens: Sequence[str]) -> str:
    """token 列表 → MATCH 表达式（`"a" OR "b" …`）。

    纯标点/空白 token 滤除（自滤一道防御——调用方未必经 segment_query 预滤）；
    空输入返回空串（调用方跳过 MATCH）。
    """
    quoted = [escape_token(t) for t in tokens if t.strip() and _WORD_RE.search(t)]
    return " OR ".join(quoted)
