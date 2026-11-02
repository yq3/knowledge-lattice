"""worker 与主进程的唤醒协议（design §2 部署图：子进程 IPC——unix socket / stdin）。

形态择型（M2.1）：**stdin 字节协议**——主进程向 worker 子进程 stdin 写一个换行
字节即"有新任务"信号；worker 侧在空闲时 `select` stdin（带兜底轮询超时）。
对比 unix socket：零路径管理（无 tmp 文件/socket 文件清理）、子进程生命周期与
管道天然绑定（父进程退出 → stdin EOF → worker 自感知退出，不留孤儿进程）；
承载量级（单 worker、毫秒级唤醒）下无性能差异。D2 零中间件：标准库 select/io。

双通道（design §2「worker 经 IPC 被唤醒 + 兜底轮询」）：
- IPC 唤醒（低延迟）：任务投递方（upload / maintenance 调度器）kick → 立即跑；
- 兜底轮询（可靠性）：stdin 等待超时（settings.worker_poll_s）后照常认领——
  唤醒字节丢失（管道缓冲异常等）不丢任务，租约过期重认领也靠本通道发现。
"""

from __future__ import annotations

import logging
import select
import sys
import threading

logger = logging.getLogger(__name__)

WAKE_BYTE = b"\n"


class StdinWake:
    """worker 侧唤醒监听：wait(timeout) 阻塞至收到唤醒字节（True）或超时（False）。

    stdin EOF（父进程关闭/退出）→ 抛 _ParentGone——调用方（worker 主循环）据此
    干净退出，不残留孤儿 worker。
    """

    def wait(self, timeout_s: float) -> bool:
        try:
            ready, _, _ = select.select([sys.stdin], [], [], timeout_s)
        except (OSError, ValueError):
            return False  # stdin 不可 select（重定向异常等）——退化为纯轮询
        if not ready:
            return False
        data = sys.stdin.buffer.read(1)
        if data == b"":
            raise _ParentGone("worker stdin EOF——主进程已退出")
        return True


class _ParentGone(Exception):
    """父进程不在（stdin EOF）——worker 主循环退出信号。"""


class ParentWake:
    """主进程侧唤醒写入（线程安全）：向 worker 子进程 stdin 写一个字节。

    管道破裂（worker 正在重启/死亡窗口）→ 记日志不抛——兜底轮询通道保证任务
    不丢（worker 拉起后最多等一个 poll 周期）。
    """

    def __init__(self, proc) -> None:
        self._proc = proc
        self._lock = threading.Lock()

    def notify(self) -> None:
        try:
            with self._lock:
                stdin = self._proc.stdin
                if stdin is None:
                    return
                stdin.write(WAKE_BYTE)
                stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            logger.warning(
                "worker wake write failed (restarting window?): %r——兜底轮询兜住",
                exc,
            )
