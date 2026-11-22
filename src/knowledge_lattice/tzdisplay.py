"""显示时区解析（2026-11-22 用户走查——时间显示本地化）。

**存储不动**：库内时间一律 UTC `YYYY-MM-DD HH:MM:SS`（``taskclock.TS_FMT``；
SQLite ``CURRENT_TIMESTAMP`` 与 PG 连接纪律 ``SET TIME ZONE 'UTC'`` 同源）——
跨时区部署、审计月库分区、备份文件名、凭证 `expires_at` 契约都建立在这个前提上，
改存储会同时动到审计链与对账语义。**只改展示**：后端把 UTC 原样吐给 REST/MCP，
控制台前端按下发的时区渲染（分工见 ``tests/test_pg_scaff.py`` R2 P2-1：
「后端吐 UTC、前端本地化渲染」）。

显示时区从哪来（本模块唯一职责）：

1. 留空（缺省）→ 返回 ``None``，前端用**浏览器时区**（谁看谁的本地时间；私有化
   部署里浏览器与服务器通常同区，二者等价，零配置即可）；
2. ``LATTICE_DISPLAY_TZ`` 给 IANA 名（如 ``Asia/Shanghai``）→ 固定该区；
3. 写 ``server`` / ``auto`` → "取服务器时区"（走下面的探测链）；
4. 非法 IANA 名 → WARNING 后回落探测链（展示层不 fail-closed——不因时区名写错
   而让服务起不来或页面报错）。

探测链（"服务器时区"，按可靠性排序）：``TZ`` 环境变量（进程时区的事实来源，
容器/进程管理器常显式设）→ ``/etc/localtime`` 符号链接（macOS / 多数 Linux 发行
版）→ ``/etc/timezone`` 文件（Debian 系）。全失败返回 ``None``。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings

log = logging.getLogger(__name__)

AUTO_VALUES = ("auto", "server", "local")  # 空串另有语义：前端用浏览器时区
_LOCALTIME = Path("/etc/localtime")
_TIMEZONE_FILE = Path("/etc/timezone")


def _valid(name: str) -> bool:
    """IANA 时区名可用性（zoneinfo 能建出来即算——含 ``UTC``）。"""
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def _server_zone() -> str | None:
    """探测服务器（进程）时区；探测不到返回 None。"""
    env_tz = (os.environ.get("TZ") or "").strip()
    # TZ 可能是 POSIX 形式（``CST-8``）——只在能当 IANA 名解析时采用
    if env_tz and _valid(env_tz):
        return env_tz
    try:
        real = os.path.realpath(_LOCALTIME)
        marker = "/zoneinfo/"
        if marker in real:
            name = real.split(marker, 1)[1]
            if _valid(name):
                return name
    except OSError:  # pragma: no cover——平台差异（Windows 无此文件）
        pass
    try:
        text = _TIMEZONE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if text and _valid(text):
        return text
    return None


def resolve_display_tz(settings: Settings) -> str | None:
    """解析控制台显示时区：IANA 名 或 None（= 前端用浏览器时区）。"""
    raw = (getattr(settings, "display_tz", "") or "").strip()
    if not raw:
        return None  # 缺省：前端按浏览器时区渲染（不探测、不猜）
    if raw.lower() in AUTO_VALUES:
        return _server_zone()
    if _valid(raw):
        return raw
    log.warning(
        "LATTICE_DISPLAY_TZ=%r 不是合法 IANA 时区名——回落服务器时区探测"
        "（控制台仍可用，时间显示可能不是期望的区）",
        raw,
    )
    return _server_zone()
