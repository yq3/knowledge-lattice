"""查询级异步审计子系统（m3-2 G-22——FR-6 / design §6.3⑥ + §4 + §5.6）。

覆盖入口（裁定②）：REST ``POST /api/search`` + MCP ``search``；REST/MCP
``annotate`` + ``get_entity``（六入口）。``search_entities`` / ``describe_table``
/ ``l0`` 不入（design §6.3⑥ 字面未含——known-gaps 开放点）。

形态（裁定①）：**进程内后台批量 flush**——满 ``flush_interval_s``（默认 5s
= FR-6 丢失窗口上限）或满批（``batch_size``）先刷；月库独立连接（sqlite
月库连接天然独立 / pg 经 backend 协议方法）；uvicorn lifespan 关停 flush；
**不走 outbox、不与业务事务绑定**（异步弱一致——崩溃丢尾部窗口 ≤5s 可接受，
已登记）。热路径仅 ``enqueue``（内存追加 O(1)——NFR-8 检索 SLO 不回归）。

detail_json（§4 字面）：查询词 + 返回 chunk_id / 实体 id 列表；refused 事件
（403 无成员/无权限/停用组织 + get_entity 404 restricted 静默面）带 reason。
action 常量在 domain/audit_events（``search.*``——ops 视图查询道前缀自动路由）。
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import deque

from knowledge_lattice.store.taskclock import utc_now_ts

logger = logging.getLogger(__name__)

# 丢失窗口上限（FR-6 字面）：默认 flush 周期 = 5s（事件最迟在本窗口内落库）
FLUSH_INTERVAL_S = 5.0
BATCH_SIZE = 200          # 满批先刷（裁定①「满 5s 或满批如 200 条先刷」）
MAX_PENDING = 10_000      # 内存队列上界（防无界增长；溢出丢最旧+告警计数）
MAX_RETRIES = 3           # 连续写失败重试上限（防毒丸阻塞——超限丢弃计数）


def build_query_event(
    action: str, *, org_id: str, actor: str,
    outcome: str = "accepted", detail: dict | None = None,
    target_type: str | None = None, target_id: str | None = None,
    request_id: str | None = None,
) -> dict:
    """构造 audit_events 全列行（直写月库形态——不经 outbox_row_to_event）。

    created_at = 入队时刻（查询发生时刻——谁/何时/查了什么的「何时」）。
    """
    return {
        "id": f"aud_{uuid.uuid4()}",
        "org_id": org_id,
        "actor": actor,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "outcome": outcome,
        "request_id": request_id,
        "detail_json": json.dumps(detail or {}, ensure_ascii=False),
        "created_at": utc_now_ts(),
    }


def enqueue_query_event(service, event: dict) -> None:
    """api/mcp 层入队助手：service.query_audit 缺位（未装配/旧壳）静默跳过
    ——审计不阻断查询主路径。"""
    qa = getattr(service, "query_audit", None)
    if qa is None:
        return
    try:
        qa.enqueue(event)
    except Exception:  # noqa: BLE001 —— 入队失败不阻断查询主路径（NFR-8）
        logger.exception("query audit enqueue failed: action=%s", event.get("action"))


class QueryAuditQueue:
    """进程内查询审计队列 + 后台批量 flush 线程（单一消费线程 → 月库串行追加）。

    - ``enqueue``：热路径内存追加（锁内 O(1)）；队列满丢最旧 + ``dropped`` 计数；
    - ``flush``：批量 ``backend.append_query_events``（batch_size 分批）；失败
      回队头重试（连续 ``max_retries`` 次失败后丢弃计数——防毒丸）；
    - ``start`` / ``stop``：后台线程启停（stop 先停线程再 flush 残留——
      uvicorn lifespan 关停口径，正常关停零丢失）；
    - ``backend_factory``（m3-3 G-28③/P2-1）：可选注入 ``Callable[(),
      ContextManager[backend]]``——flush 线程经工厂取**独立连接**的 backend
      写月库（pg 形态：消除与请求线程共享 ``PgBackend._conn`` 单连接的协议
      错乱风险——psycopg 连接无内建跨线程锁；工厂见 store/postgres/
      audit_factory.audit_backend_factory）。缺省 None → 直接用共享
      ``backend``（sqlite 生产形态安全——月库天然独立 mconn 连接）。
    """

    def __init__(self, backend, *, flush_interval_s: float = FLUSH_INTERVAL_S,
                 batch_size: int = BATCH_SIZE, max_pending: int = MAX_PENDING,
                 max_retries: int = MAX_RETRIES,
                 backend_factory=None) -> None:
        self._backend = backend
        self._backend_factory = backend_factory
        self._interval = flush_interval_s
        self._batch = batch_size
        self._max_pending = max_pending
        self._max_retries = max_retries
        self._queue: deque[dict] = deque()
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()  # flush 串行化（drain barrier——
        #   并发 flush 互斥等待：flush() 返回即此前全部事件已提交或已回队）
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failures = 0    # 连续写失败计数（防毒丸）
        self.dropped = 0      # 溢出+超限丢弃计数（观测面）

    # ---- 热路径（api/mcp 层调用） ----

    def enqueue(self, event: dict) -> None:
        with self._lock:
            if len(self._queue) >= self._max_pending:
                self._queue.popleft()  # 丢最旧（保最近查询面）
                self.dropped += 1
                logger.warning(
                    "query audit queue overflow (max_pending=%s)——dropped"
                    " oldest event, total dropped=%d", self._max_pending, self.dropped)
            self._queue.append(event)
        self._wake.set()

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._queue)

    # ---- flush（后台线程 / 显式调用） ----

    def flush(self) -> int:
        """排空队列写月库（分批）；返回本轮写入行数。失败回队头待重试。

        **drain barrier**：全程持 ``_flush_lock``——后台线程与显式调用并发时
        互斥等待，flush() 返回即此前入队事件已提交（或已如实回队/丢弃），
        测试与关停路径读月库不再有 drain-与-commit 间竞态窗。"""
        with self._flush_lock:
            return self._flush_locked()

    def _flush_locked(self) -> int:
        total = 0
        while True:
            with self._lock:
                batch = []
                while self._queue and len(batch) < self._batch:
                    batch.append(self._queue.popleft())
            if not batch:
                return total
            try:
                # m3-3 G-28③/P2-1：工厂注入形态——本轮 flush 经独立连接写
                # 月库（pg 消除共享单连接；工厂自管连接生命周期，flush 间
                # 无并发——_flush_lock 串行化）。缺省直用共享 backend。
                if self._backend_factory is not None:
                    with self._backend_factory() as audit_backend:
                        total += audit_backend.append_query_events(batch)
                else:
                    total += self._backend.append_query_events(batch)
                self._failures = 0
            except Exception:  # noqa: BLE001 —— 写失败不冒泡（后台面）
                with self._lock:
                    self._failures += 1
                    give_up = self._failures >= self._max_retries
                    if give_up:
                        self.dropped += len(batch)
                    else:
                        self._queue.extendleft(reversed(batch))
                if give_up:
                    logger.exception(
                        "query audit flush failed %d consecutive times——drop"
                        " %d events (async weak consistency, FR-6 window)",
                        self._max_retries, len(batch))
                    continue  # 丢弃后继续处理后续批次
                logger.exception(
                    "query audit flush failed——requeued %d events for retry",
                    len(batch))
                return total

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self._interval)
            self._wake.clear()
            try:
                self.flush()
            except Exception:  # noqa: BLE001 —— flush 自吞异常，此为防御
                logger.exception("query audit background flush crashed")

    # ---- 生命周期（app lifespan） ----

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="query-audit-flusher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """关停：停线程 → flush 残留（正常关停零丢失）。"""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None
        self.flush()
