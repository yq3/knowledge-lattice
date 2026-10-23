"""log.py 骨架（v0.8.5 运行日志装配）：JSON→stdout + request_id/task_id contextvars。"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest


@pytest.fixture()
def _root_logging_state() -> Iterator[None]:
    """P3-21：setup_logging 直接替换 root handlers/level——测试后恢复原状，避免顺序依赖。"""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def test_json_log_line_with_context(
    capsys: pytest.CaptureFixture[str], _root_logging_state: None
) -> None:
    from knowledge_lattice.log import request_id_var, setup_logging, task_id_var

    setup_logging(level="INFO", fmt="json")
    log = logging.getLogger("knowledge_lattice.test")
    token_r = request_id_var.set("req-1")
    token_t = task_id_var.set("task-9")
    try:
        log.info("检索完成")
    finally:
        request_id_var.reset(token_r)
        task_id_var.reset(token_t)

    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["msg"] == "检索完成"
    assert payload["request_id"] == "req-1"
    assert payload["task_id"] == "task-9"


def test_human_format_and_defaults(
    capsys: pytest.CaptureFixture[str], _root_logging_state: None
) -> None:
    from knowledge_lattice.log import request_id_var, setup_logging

    setup_logging(level="WARNING", fmt="human")
    logging.getLogger("x").info("不应出现")  # 低于级别
    logging.getLogger("x").warning("人读格式")
    out = capsys.readouterr().out
    assert "不应出现" not in out
    assert "人读格式" in out
    assert request_id_var.get() is None  # 上下文缺省 None——不进日志
