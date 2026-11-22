"""时间显示时区（2026-11-22 用户走查——「页面上的时间都是 UTC，我要本地时间」）。

口径（**存储不动，只改展示**）：

- 库内/接口一律 UTC `YYYY-MM-DD HH:MM:SS`（``taskclock.TS_FMT``；SQLite
  ``CURRENT_TIMESTAMP`` 与 PG 连接纪律 ``SET TIME ZONE 'UTC'`` 同源）——审计月库
  分区、备份文件名、凭证 ``expires_at`` 契约都建立在这个前提上，**本组用例把这条
  钉死**（``test_storage_timestamps_stay_utc``），防"为了显示本地时间改存储"的
  反向修法；
- 展示分工（``tests/test_pg_scaff.py`` R2 P2-1 已定）：后端吐 UTC、前端本地化。
  显示时区由 ``LATTICE_DISPLAY_TZ`` 决定——``""``（缺省）= 浏览器时区，IANA 名 =
  固定该区，``server``/``auto`` = 探测服务器时区；``None`` 下发表示"前端自己定"；
- 输入面（``expires_at`` 文本框）按显示时区填写、提交前换算回 UTC；CSV 导入导出
  **不换算**（交换格式保持 UTC，导出→导入往返不漂移）。

纯静态 + 纯函数断言：不依赖跑浏览器、不依赖机器时区（探测链用例全部 monkeypatch）。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from knowledge_lattice.config import Settings
from knowledge_lattice.store.sqlite import connect
from knowledge_lattice.store.taskclock import TS_FMT
from knowledge_lattice import tzdisplay

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "src/knowledge_lattice/web"
API = WEB / "api.js"
APP = WEB / "app.js"
ACCESS = WEB / "views" / "access.js"
I18N = WEB / "i18n.js"


# ============ 存储口径：不许为了显示去动存储 ============


def test_storage_timestamps_stay_utc(tmp_path) -> None:
    """SQLite 默认值与 ``utc_now_ts`` 都必须是 UTC——**不是**本机时区。"""
    conn = connect(tmp_path / "tz.db")
    try:
        conn.execute("CREATE TABLE probe (ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO probe DEFAULT VALUES")
        conn.commit()
        stored = conn.execute("SELECT ts FROM probe").fetchone()[0]
    finally:
        conn.close()
    utc_now = datetime.now(UTC).replace(tzinfo=None)
    drift = abs((datetime.strptime(stored, TS_FMT) - utc_now).total_seconds())
    assert drift < 30, f"库内时间不是 UTC：存 {stored}，UTC now {utc_now:%Y-%m-%d %H:%M:%S}"

    from knowledge_lattice.store.taskclock import utc_now_ts

    assert abs(
        (datetime.strptime(utc_now_ts(), TS_FMT) - utc_now).total_seconds()
    ) < 30


# ============ 显示时区解析（探测链全部 mock，机器时区无关） ============


@pytest.fixture()
def fake_zones(monkeypatch):
    """把 ``_valid`` 换成固定集合，并用临时路径替换两个系统探测点。"""
    known = {"UTC", "Asia/Shanghai", "Asia/Tokyo"}
    monkeypatch.setattr(tzdisplay, "_valid", lambda name: name in known)
    monkeypatch.delenv("TZ", raising=False)
    return known


def test_explicit_iana_is_used_as_is(fake_zones) -> None:
    assert tzdisplay.resolve_display_tz(Settings(display_tz="Asia/Shanghai")) == "Asia/Shanghai"


def test_empty_means_browser_zone(monkeypatch, fake_zones) -> None:
    """留空 = 不探测、下发 None——前端用浏览器时区（零配置的缺省档）。"""
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    assert tzdisplay.resolve_display_tz(Settings(display_tz="")) is None


def test_server_keyword_uses_detection(monkeypatch, fake_zones) -> None:
    """``server``/``auto``/``local`` = 探测服务器时区（TZ 优先）。"""
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    for raw in ("server", "auto", "local", "SERVER"):
        assert tzdisplay.resolve_display_tz(Settings(display_tz=raw)) == "Asia/Tokyo", raw


def test_invalid_name_falls_back_with_warning(monkeypatch, fake_zones, caplog) -> None:
    """非法 IANA 名 = WARNING + 回落探测（展示层不 fail-closed）。"""
    monkeypatch.setenv("TZ", "UTC")
    with caplog.at_level("WARNING"):
        assert tzdisplay.resolve_display_tz(Settings(display_tz="Mars/Olympus")) == "UTC"
    assert "LATTICE_DISPLAY_TZ" in caplog.text, "非法时区名未留 WARNING（运维无从发现）"


def test_detection_failure_returns_none(monkeypatch, fake_zones, tmp_path) -> None:
    """要求探测但探测不到 → None（前端回落到浏览器时区），不抛错。"""
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(tzdisplay, "_LOCALTIME", tmp_path / "no-such-localtime")
    monkeypatch.setattr(tzdisplay, "_TIMEZONE_FILE", tmp_path / "no-such-timezone")
    assert tzdisplay.resolve_display_tz(Settings(display_tz="server")) is None


def test_system_probes_are_read(tmp_path, monkeypatch, fake_zones) -> None:
    """``/etc/localtime`` 软链与 ``/etc/timezone`` 文件两条探测路径都成立。"""
    root = tmp_path / "zoneinfo" / "Asia"
    root.mkdir(parents=True)
    link = root / "Shanghai"
    link.write_text("", encoding="utf-8")
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(tzdisplay, "_LOCALTIME", link)
    monkeypatch.setattr(tzdisplay, "_TIMEZONE_FILE", tmp_path / "no-such-timezone")
    assert tzdisplay._server_zone() == "Asia/Shanghai"

    monkeypatch.setattr(tzdisplay, "_LOCALTIME", tmp_path / "no-such-localtime")
    tzfile = tmp_path / "timezone"
    tzfile.write_text("Asia/Tokyo\n", encoding="utf-8")
    monkeypatch.setattr(tzdisplay, "_TIMEZONE_FILE", tzfile)
    assert tzdisplay._server_zone() == "Asia/Tokyo"


def test_real_zoneinfo_lookup() -> None:
    """真 ZoneInfo 路径（系统 tzdata）：UTC 可解析、垃圾名被拒。"""
    assert tzdisplay._valid("UTC") is True
    assert tzdisplay._valid("Not/AZone") is False


# ============ boot 端点下发 ============


def test_auth_config_exposes_display_tz(app_env) -> None:
    """``GET /api/auth/config`` 带 ``display_tz``（None 或 IANA 名）——前端据此渲染。"""
    body = app_env["client"].get("/api/auth/config").json()
    assert "display_tz" in body
    assert body["display_tz"] is None or isinstance(body["display_tz"], str)


def test_auth_config_passes_resolved_zone(app_env, monkeypatch) -> None:
    monkeypatch.setattr(
        "knowledge_lattice.api.auth.resolve_display_tz", lambda settings: "Asia/Shanghai"
    )
    assert app_env["client"].get("/api/auth/config").json()["display_tz"] == "Asia/Shanghai"


# ============ 前端渲染/输入换算的静态锚点 ============


def test_shell_formats_utc_into_display_zone() -> None:
    api = API.read_text(encoding="utf-8")
    for name in ("setDisplayTz", "tzName", "tsToEpoch", "fmtTs", "short", "toUtcStr"):
        assert f"function {name}(" in api or f"const {name} =" in api, f"api.js 缺 {name}"
    assert "Intl.DateTimeFormat" in api, "时间未走 Intl（会退回 UTC 字符切片）"
    short_body = re.search(r"function short\(ts\) \{(.+?)\n\}", api, re.S)
    assert short_body, "未找到 short()"
    assert "fmtTs(ts)" in short_body.group(1), "short() 未先换算到显示时区"
    assert "String(ts).slice" not in short_body.group(1), "short() 仍在裸切 UTC 串"
    # 非时间串（"—"/占位符）必须原样透出——对透传结果再切字符会显示成空
    assert "tsToEpoch(ts) == null" in short_body.group(1), "short() 对占位符未做透传保护"

    app = APP.read_text(encoding="utf-8")
    assert "setDisplayTz(config && config.display_tz)" in app, "boot 未接线显示时区"
    assert '+ " UTC"' not in app, "视图里仍有硬编码的 UTC 标注"
    # 时区名进 tooltip（完整时间 + 区名），而不是挂在列头
    assert "${tzName()}" in app


def test_expiry_inputs_convert_back_to_utc() -> None:
    """expires_at 输入面：seed 转显示区（localOf）、提交转 UTC（toUtcStr）。"""
    src = ACCESS.read_text(encoding="utf-8")
    assert "function localOf(ts)" in src, "缺 UTC→显示区的输入种子助手"
    assert src.count("toUtcStr(") >= 3, "提交路径未全部换回 UTC（新建成员/改到期/授权行）"
    assert "map(([k, v]) => [k, localOf(v)])" in src, "抽屉行内初始值未转显示区"
    # CSV 是交换格式：不换算（否则导出→导入漂移）
    assert "expires_at: r.expiresAt" in src, "CSV 行被误加时区换算"


def test_no_utc_suffix_in_time_labels() -> None:
    """列头不再挂 ``(UTC)``——区名由单元格 tooltip 给（避免满屏时区噪声）。"""
    i18n = I18N.read_text(encoding="utf-8")
    bad = [
        (m.group(1), m.group(2))
        for m in re.finditer(r'^\s*"([^"]+)": "([^"]*[（(]UTC[)）][^"]*)",$', i18n, re.M)
    ]
    assert not bad, f"界面文案仍标注 (UTC)：{bad}"
