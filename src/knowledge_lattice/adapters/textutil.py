"""文本字符质量工具（design §5.4 mojibake 质量门的判分函数——M1-4）。

分层归属（P3 顺手，R2 修）：`normal_char_ratio` 为**纯字符判分函数**，被
adapters/parser_docling（TXT 编码候选择优）与 core/docs/quality（三档门）共用
——下沉到本共享工具层使两向依赖均合法（adapters 内部 / core→adapters 既有
方向，同 chunking→tokenizer；R1 的 parser→core 倒置已修）。

三档门语义（mojibake_tier）留在 core/docs/quality.py（质量域职责），此处只
提供无业务语义的判分原语与阈值常量。
"""

from __future__ import annotations

# 「正常字符」= CJK 统一表意 + ASCII 可打印 + 常用中文标点/全角区
NORMAL_RANGES: tuple[tuple[int, int], ...] = (
    (0x4E00, 0x9FFF),    # CJK 统一表意
    (0x3400, 0x4DBF),    # CJK 扩展 A
    (0x20, 0x7E),        # ASCII 可打印
    (0x3000, 0x303F),    # CJK 标点
    (0xFF00, 0xFFEF),    # 全角形式
    (0x2018, 0x201D),    # 弯引号
    (0x00A0, 0x00FF),    # Latin-1 补充（西文内容正常态）
)

MOJIBAKE_WARN = 0.55   # 正常字符比 < 0.55 → 告警档（重试）
MOJIBAKE_FAIL = 0.40   # < 0.40 → 失败档（design §5.4 三档）


def _is_normal(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in NORMAL_RANGES)


def normal_char_ratio(text: str) -> float:
    """正常字符比：非空白字符中「正常字符」的占比（空格/换行不计分母）。"""
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 1.0
    return sum(1 for c in chars if _is_normal(c)) / len(chars)
