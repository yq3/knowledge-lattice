"""别名规范化（design §4 sem_aliases.alias_norm 列口径）。

NFKC、全角转半角、小写、去空白——与 annotate 的文本规范化**同一函数**
（AC 自动机归 m2s-2，届时复用本模块；TEST-CASES TC-YAML-05 两端一致承诺的
基础件）。
"""

from __future__ import annotations

import unicodedata


def normalize_alias(text: str) -> str:
    """NFKC（含全角→半角）→ 小写 → 去全部 Unicode 空白。"""
    return "".join(unicodedata.normalize("NFKC", text).lower().split())


__all__ = ["normalize_alias"]
