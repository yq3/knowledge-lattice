"""M1-3 承接遗留项收口（P3-10 / P3-13 / P3-16 / P3-R2-3 / P3-C——触及即顺手）。

- P3-10：datetime 序列化契约统一 UTC ISO（API 面——凭证 expires_at 即载体）；
- P3-13：上传大小上限默认 200MB（413——TC-CRED-02⑤ 主题，此处锁默认值口径）；
- P3-16：60s 超时中间件**绑定**断言（settings 值真实挂载——非仅 config 默认）；
- P3-R2-3：prod 401 响应体清理内部审查号 "P2-5"（对外错误文案不带内部标记）；
- P3-C（m1-2 R2）：upload 侧新值校验与 helper 两份 → 收敛为同一实现 + 交叉注释
  锚定（本文件以 helper 同款错误文案佐证单一实现）。
"""

from __future__ import annotations

import pytest


def test_p3_10_utc_iso_serialization() -> None:
    """P3-10：UTC 秒级存储 → ISO 8601 Z 后缀（API 序列化统一口径）。"""
    from knowledge_lattice.core.docs.credentials import to_utc_iso, utc_now_ts

    assert to_utc_iso("2026-10-25 08:00:00") == "2026-10-25T08:00:00Z"
    assert to_utc_iso("2026-12-31 23:59:59") == "2026-12-31T23:59:59Z"
    now = utc_now_ts()
    assert to_utc_iso(now).endswith("Z") and "T" in to_utc_iso(now)
    # UTC 语义：与 time.gmtime 一致（无本地时区漂移）
    import time as _time

    assert now == _time.strftime("%Y-%m-%d %H:%M:%S", _time.gmtime())


def test_p3_13_default_upload_cap_200mb() -> None:
    """P3-13：全局上限默认 200MB（413 载体在 TC-CRED-02⑤——此处锁默认值）。"""
    from knowledge_lattice.config import Settings

    assert Settings().upload_max_bytes == 200 * 1024 * 1024


def test_p3_16_timeout_middleware_bound_with_settings_value(app_env) -> None:
    """P3-16：ToolTimeoutMiddleware 以 settings.mcp_timeout_s 真实挂载到 server
    （绑定断言——非默认值注入 7.5s，防硬编码 60 通过）。"""
    from knowledge_lattice.config import Settings
    from knowledge_lattice.mcp.server import ToolTimeoutMiddleware, build_mcp_server

    settings = Settings(environment="test", mcp_timeout_s=7.5)
    server = build_mcp_server(app_env["app"].state.service, settings)
    bound = [m for m in server.middleware if isinstance(m, ToolTimeoutMiddleware)]
    assert bound, "ToolTimeoutMiddleware 未挂载"
    assert bound[0].timeout_s == 7.5


def test_p3_r2_3_prod_401_message_has_no_internal_marker(app_env) -> None:
    """P3-R2-3：prod 401 响应文案不含内部审查号 "P2-5"。"""
    from knowledge_lattice.config import Settings
    from knowledge_lattice.domain.auth import AuthError, authenticate

    prod = Settings(environment="prod")
    with pytest.raises(AuthError) as exc_info:
        authenticate(app_env["app"].state.service.backend, prod, "any-token")
    assert "P2-5" not in str(exc_info.value), "内部审查号泄漏到对外错误文案"
    assert "SSO" in str(exc_info.value) or "production" in str(exc_info.value)


def test_p3_c_upload_grant_check_single_implementation(ingest_env) -> None:
    """P3-C：create_document 新值越权 → 与 PATCH 共用 `_require_values_in_grants`
    的同款错误文案（helper 单一实现——防 upload 链改造时两份漂移）。"""
    from fake_providers import FakeEmbedder
    from knowledge_lattice.core.docs.ingest import UploadPermissionError

    service = ingest_env["make_service"](FakeEmbedder(dim=8))
    with pytest.raises(UploadPermissionError) as exc_info:
        service.create_document(  # u_cn 仅 region=[CN]——OS 越权
            org_id="org:tax", dataset_id="ds:vat_lib", title="t",
            dims={"region": ["OS"]}, owner_user_id="u_cn",
            file_bytes="<html><body>x</body></html>".encode(), mime_type="text/html",
            filename="x.html",
        )
    msg = str(exc_info.value)
    assert "not within actor grants" in msg, "非 helper 同款文案——两份实现漂移"
    assert "FR-4" in msg
