"""m3-4 E-1（issue #16）：pg 臂 teardown DROP SCHEMA 不再静默吞失败。

`_pg_db` teardown 原为 ``except psycopg.Error: pass``——DROP 失败无任何可
观测信号（schema 静默泄漏、库房漂移无对账线索）。修复形态：`_drop_pg_schema`
重试（指数退避）+ 持续失败 ``warnings.warn`` 显式登记 **schema 名**与末次
错误（不抛异常——teardown 失败不得覆盖用例原始异常的既有纪律不变）。

用例用假连接注入 DROP 失败（不依赖真实 PG——两臂恒可跑，无 DSN 也绿）。
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import _drop_pg_schema


class _FakeRaw:
    """假 psycopg 连接：SET 正常、DROP 按注入脚本抛错。"""

    def __init__(self, *, drop_errors: int = 0):
        self.drop_errors = drop_errors  # 前 N 次 DROP 抛错（0=恒成功）
        self.calls: list[str] = []

    def execute(self, sql: str, params=None):  # noqa: ANN001
        self.calls.append(sql)
        if sql.startswith("DROP"):
            drops_so_far = sum(1 for s in self.calls if s.startswith("DROP"))
            if drops_so_far <= self.drop_errors:
                raise psycopg.ProgrammingError("injected drop failure")
        return None


def test_e1_drop_failure_warns_with_schema_name() -> None:
    """持续失败 → 不抛、发 warning（含 schema 名与重试次数）、DROP 重试到位。"""
    raw = _FakeRaw(drop_errors=99)  # 恒失败
    with pytest.warns(UserWarning, match="lattice_test_deadbeef") as record:
        ok = _drop_pg_schema(raw, "lattice_test_deadbeef", attempts=3)
    assert ok is False, "持续失败返回 False（可观测，不抛）"
    msg = str(record[0].message)
    assert "已重试 3 次" in msg and "injected drop failure" in msg, (
        "warning 须携带重试次数与末次错误（对账线索）"
    )
    drops = [s for s in raw.calls if s.startswith("DROP")]
    assert len(drops) == 3, "DROP 须重试满 attempts 次"


def test_e1_drop_transient_failure_recovers_silently(recwarn) -> None:
    """瞬时失败（首次抛、第二次成功）→ 自愈成功、零 warning。"""
    raw = _FakeRaw(drop_errors=1)
    ok = _drop_pg_schema(raw, "lattice_test_abc123", attempts=3)
    assert ok is True
    assert len(recwarn) == 0, f"瞬时失败自愈不应发 warning：{[str(w.message) for w in recwarn]}"


def test_e1_drop_success_single_attempt(recwarn) -> None:
    """正常路径：一次成功、零 warning。"""
    raw = _FakeRaw(drop_errors=0)
    ok = _drop_pg_schema(raw, "lattice_test_ok")
    assert ok is True
    drops = [s for s in raw.calls if s.startswith("DROP")]
    assert len(drops) == 1
    assert len(recwarn) == 0
