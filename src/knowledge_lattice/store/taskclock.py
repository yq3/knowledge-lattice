"""任务队列时间戳工具（M2.1 worker 框架——租约/心跳/取消的时钟口径）。

库内存储 UTC `YYYY-MM-DD HH:MM:SS`（与 CURRENT_TIMESTAMP 及凭证链 P3-10 契约
同格式、同源口径）；租约/心跳的加减秒在调用侧算好以字符串参数下发——
两方言 backend 共用（store 层内部工具，不暴露给 core）。
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
