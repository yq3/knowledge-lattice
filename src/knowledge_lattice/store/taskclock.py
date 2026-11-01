"""任务队列时间戳工具（M2.1 worker 框架——租约/心跳/取消的时钟口径）。

库内存储 UTC `YYYY-MM-DD HH:MM:SS`（与 CURRENT_TIMESTAMP 及凭证链 P3-10 契约
同格式、同源口径）；租约/心跳的加减秒在调用侧算好以字符串参数下发——
两方言 backend 共用（store 层内部工具，不暴露给 core）。

m2-6 B⑥（格式常量共享）：``TS_FMT`` 是**库内时间格式的单一常量源**——api 侧
expires_at 解析（admin._EXPIRES_LIB_FORMAT 旧双源已收编）与 store 侧
strftime 字面量统一引用本常量；``normalize_expires_at`` 是写路径（API 与
store 直调〔B③〕）共用的归一化入口。
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

TS_FMT = "%Y-%m-%d %H:%M:%S"


def utc_now_ts() -> str:
    """当前 UTC 时间戳（CURRENT_TIMESTAMP 同格式）。"""
    return time.strftime(TS_FMT, time.gmtime())


def add_seconds(ts: str, seconds: float) -> str:
    """时间戳加减秒（租约到期 = now + lease_s；保留天数截尾 = now - days*86400）。"""
    base = datetime.strptime(ts, TS_FMT)
    return (base + timedelta(seconds=seconds)).strftime(TS_FMT)


def normalize_expires_at(raw: str | None) -> str | None:
    """expires_at 严格解析与归一（m2-6 B③/B⑥——api 与 store 直调共用）：
    接受库格式 ``YYYY-MM-DD HH:MM:SS`` 与 ISO 8601（T 分隔，可选 Z/+00:00），
    归一化为库格式字符串；空/None → None（永久）；非法 → ValueError（调用方
    映射 HTTP 400 或协议异常——sqlite 静默 fail-open 与 pg 500 跨方言不一致
    的根除收口，m2-3 R2 P2-2 的 API 面收口延伸到 store 直调面）。"""
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    candidates = [
        (text, TS_FMT),
        (text.replace("T", " ", 1), TS_FMT),  # ISO T 分隔
    ]
    if text.endswith("Z"):
        candidates.append((text[:-1].replace("T", " ", 1), TS_FMT))
    elif "+00:00" in text:
        candidates.append(
            (text.replace("+00:00", "").replace("T", " ", 1), TS_FMT)
        )
    for candidate, fmt in candidates:
        try:
            return datetime.strptime(candidate, fmt).strftime(fmt)
        except ValueError:
            continue
    raise ValueError(
        f"expires_at 非法: {text!r}——须为 'YYYY-MM-DD HH:MM:SS' 或"
        " ISO 8601（UTC）"
    )
