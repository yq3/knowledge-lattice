"""PG 全文查询构造（design §5.2 PG 渲染注——M1-1）。

- tokens（应用层 jieba 预分词产物）→ `to_tsquery('simple', …)` 查询串：
  token 以引号包裹为字面量短语（内部 `"` 剥离——to_tsquery 短语引号不可嵌套），
  token 间以 `&` 连接（design §5.2 钉死口径：「PG 侧 query 经应用层 jieba 分词
  后以 `&` 连接拼 to_tsquery('simple', …)」——与 SQLite 的 OR 拼接是已登记的
  后端差异，排序断言按名次集等价 A-17）；
- 产物经绑定参数 + `'simple'` regconfig 双参进 SQL，绝不拼接进 SQL 文本；
- 五列加权 ts_rank 求和权重（title 3.0 / content 1.0 / keywords 5.0 /
  llm 0.5 / tags 8.0——与 SQLite bm25 五列参数同序同值，§5.2）。
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# 与 adapters/tokenizer.segment_query 同口径：无字词字符的 token 不进表达式
_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]")

# 五列 ts_rank 加权（与 sqlite BM25_WEIGHTS 同值——加权方向差异在 backend 内吸收为名次）
TS_RANK_WEIGHTS = (
    ("title_tsv", 3.0),
    ("content_tsv", 1.0),
    ("keywords_tsv", 5.0),
    ("llm_keywords_tsv", 0.5),
    ("tags_tsv", 8.0),
)

# 加权和 SQL 片段（结构常量——列名/权重为源码字面量，标识符位不变式）；
# `query` 为 render_fts_recall_select 的 CROSS JOIN to_tsquery 产物别名
TS_RANK_SUM = " + ".join(
    f"{weight} * ts_rank({column}, query)" for column, weight in TS_RANK_WEIGHTS
)

# FTS 匹配谓词（任一列命中——五列 OR；{q} 占位由渲染器替换为绑定参数形态）
TS_MATCH_ANY = " OR ".join(
    f"c.{column} @@ to_tsquery('simple', {{q}})" for column, _ in TS_RANK_WEIGHTS
)


def escape_tsquery_token(token: str) -> str:
    """token → to_tsquery 字面量短语（引号包裹、内部 `"` 剥离）。"""
    return '"' + token.replace('"', "") + '"'


def build_tsquery(tokens: Sequence[str]) -> str:
    """token 列表 → to_tsquery('simple', :q) 绑定值（`"a" & "b" …`）。

    纯标点/空白 token 滤除（与 sqlite build_match_expr 同口径自滤一道）；
    空输入返回空串（调用方跳过 FTS 路）。
    """
    quoted = [
        escape_tsquery_token(t) for t in tokens if t.strip() and _WORD_RE.search(t)
    ]
    return " & ".join(quoted)
