"""熔断器（NFR-8 v0.8：连续 3 次失败断开 60s——「慢」与「不可达」的区分机制）。

口径（requirements NFR-8）：熔断＝连续 N 次失败即断开 cooldown 秒（期间直接降级
不等超时），半开探测恢复（**单次探测**——探测结果回来前不再放行；失败即重新
断开、成功回 closed）。超时值是单次请求硬上限（超时即视同本次不可达走降级）——
熔断承担「持续不可达不反复等超时」的职责，两者非同一事物。

时钟注入：now 参数由调用方传入（time.monotonic() 基准，state/allow/record_failure
一致接受注入——测试造数推进注入时钟、不推进系统时钟，TEST-CASES 口径段纪律）。
线程安全：内部锁保护（多请求共享同一 provider 熔断器）。
"""

from __future__ import annotations

import threading
import time


class CircuitBreaker:
    """嵌入 / rerank 查询侧调用的共享熔断器（进程内、按 provider 一枚）。"""

    def __init__(self, *, failures: int = 3, cooldown_s: float = 60.0) -> None:
        self._threshold = failures
        self._cooldown_s = cooldown_s
        self._streak = 0        # 连续失败计数（成功即清零——非累计）
        self._opened_at: float | None = None
        self._probing = False   # 半开探测在途（单次探测——P3-5：探测结果前不再放行）
        self._lock = threading.Lock()

    def _reference(self, now: float | None) -> float:
        return time.monotonic() if now is None else now

    def state(self, *, now: float | None = None) -> str:
        """closed（放行）/ open（断开）/ half_open（冷却后探测放行）。"""
        with self._lock:
            return self._state_locked(self._reference(now))

    def _state_locked(self, reference: float) -> str:
        if self._opened_at is None:
            return "closed"
        if reference - self._opened_at >= self._cooldown_s:
            return "half_open"
        return "open"

    def allow(self, *, now: float | None = None) -> bool:
        """是否放行调用（open 期间直接降级、不等超时；半开只放一次探测）。"""
        with self._lock:
            reference = self._reference(now)
            state = self._state_locked(reference)
            if state == "closed":
                return True
            if state == "open":
                return False
            # half_open：单次探测——在途探测返回前不再放行（P3-5）
            if self._probing:
                return False
            self._probing = True
            return True

    def record_success(self) -> None:
        with self._lock:
            self._streak = 0
            self._opened_at = None  # 半开探测成功 → 回 closed
            self._probing = False

    def record_failure(self, *, now: float | None = None) -> None:
        with self._lock:
            reference = self._reference(now)
            was_tripped = self._opened_at is not None  # open / half_open（success 才清 None）
            self._streak += 1
            self._probing = False
            if was_tripped or self._streak >= self._threshold:
                # 半开探测失败 → 立即重新断开（单次探测语义）；closed 连续 N 失败 → 断开
                self._opened_at = reference
                self._streak = 0  # 断开后清计数（重开周期重新累计）
