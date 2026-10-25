"""熔断器（NFR-8 v0.8：连续 3 次失败断开 60s——「慢」与「不可达」的区分机制）。

口径（requirements NFR-8）：熔断＝连续 N 次失败即断开 cooldown 秒（期间直接降级
不等超时），半开探测恢复（放行一次，失败即重新断开、成功回 closed）。超时值是
单次请求硬上限（超时即视同本次不可达走降级）——熔断承担「持续不可达不反复等
超时」的职责，两者非同一事物。

时钟注入：now 参数由调用方传入（time.monotonic() 基准）——测试造数推进注入
时钟、不推进系统时钟（TEST-CASES 口径段纪律）。
"""

from __future__ import annotations

import time


class CircuitBreaker:
    """嵌入 / rerank 查询侧调用的共享熔断器（进程内、按 provider 一枚）。"""

    def __init__(self, *, failures: int = 3, cooldown_s: float = 60.0) -> None:
        self._threshold = failures
        self._cooldown_s = cooldown_s
        self._streak = 0        # 连续失败计数（成功即清零——非累计）
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        """closed（放行）/ open（断开）/ half_open（冷却后探测放行）。"""
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at >= self._cooldown_s:
            return "half_open"
        return "open"

    def allow(self, *, now: float | None = None) -> bool:
        """是否放行调用（open 期间直接降级、不等超时）。"""
        if self._opened_at is None:
            return True
        reference = time.monotonic() if now is None else now
        return reference - self._opened_at >= self._cooldown_s  # half_open 放行探测

    def record_success(self) -> None:
        self._streak = 0
        self._opened_at = None  # 半开探测成功 → 回 closed

    def record_failure(self, *, now: float | None = None) -> None:
        reference = time.monotonic() if now is None else now
        was_tripped = self._opened_at is not None  # open / half_open（success 才清 None）
        self._streak += 1
        if was_tripped or self._streak >= self._threshold:
            # 半开探测失败 → 立即重新断开（单次探测语义）；closed 连续 N 失败 → 断开
            self._opened_at = reference
            self._streak = 0  # 断开后清计数（重开周期重新累计）
