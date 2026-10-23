"""运行日志装配（design §3——v0.8.5 补缺：可观测性第三类）。

结构化 JSON→stdout（不落文件——容器/systemd 收集、本地可切人读格式，D2 零中间件）；
request_id/task_id 走 contextvars（贯穿主进程与 worker）。请求中间件一行日志、
uvicorn access log 关闭防双打、docling/torch 降噪随 M0a-3 服务壳挂接——本模块先落
装配函数与上下文变量（M0a-1 只落模块与 §3 归属）。

审计 ≠ 日志（design §3 横切面）：业务/权限事实落库走 store 层 Audit 域（不可丢），
运行诊断走 stdout（可丢）——本模块只负责后者。
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)


class JsonFormatter(logging.Formatter):
    """单行 JSON 记录（含上下文 request_id / task_id）。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = request_id_var.get()
        task_id = task_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id
        if task_id is not None:
            payload["task_id"] = task_id
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    """装配 root logger（各层直接用标准库 logging——不构成分层纪律例外）。"""
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:  # human——本地开发人读格式
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
