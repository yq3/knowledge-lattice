"""maintenance 任务体（M2.1——design §3 maintenance 任务族框架 + §5.3）。

框架形态：app.py 内嵌调度器周期投递 **maintenance 任务行**（形态保留），
执行体进 worker（TaskRunner 的 maintenance executor 调本模块 run_maintenance）。

本段落地三个任务体 + 保留策略（design §3 v0.8.3 清单的前三项）：
1. 未消费凭证回收（M1-3 CredentialService.purge_expired 收编——TC-CRED-05）；
2. 过期成员物理清理（backend.delete_expired_memberships——§5.1「物理删除交
   定时任务」，触发器级联清授权）；
3. tombstone 90 天物理清理（backend.delete_aged_tombstones——§4 chunks 行注释，
   时点基准 = tombstoned_at〔0004 迁移〕）；
4. maintenance 任务行保留策略（m1-3 P3-19——done/failed 行按天数/条数截尾）。

**预留 type 分发位**：审计月库滚动 / 备份快照 / sem_chunk_entities 对账不在
本段（分别归 m2-2 / M2-S3）——MAINTENANCE_BODIES 注册表即扩展点（新任务体
注册进表即被周期任务携带执行；独立任务类型则进 runner 的 executor 分发表）。

各任务体相互隔离（单个体失败不阻断其余——收集错误后统一落任务 failed 留痕）。
"""

from __future__ import annotations

import json
import logging

from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

logger = logging.getLogger(__name__)


def run_maintenance(backend, credentials, settings, task_id: str) -> dict:
    """maintenance 任务执行体（自管任务行状态——与 ingest.run_task 同款形态）。

    凭证回收需要 credentials 服务（core）；成员/tombstone/保留策略经 backend
    Admin 域方法（core 不碰 SQL 纪律——SQL 已下沉双方言 backend）。
    """
    backend.update_task(task_id, status="running")
    stats: dict[str, object] = {}
    errors: list[str] = []
    now = utc_now_ts()

    def _body(name: str, fn) -> None:
        try:
            stats[name] = fn()
        except Exception as exc:  # noqa: BLE001 —— 单个体失败不阻断其余
            logger.exception("maintenance body failed: %s", name)
            errors.append(f"{name}: {exc}")

    _body("credentials_purged", lambda: credentials.purge_expired()["reclaimed"])
    _body("memberships_purged", lambda: backend.delete_expired_memberships(now=now))
    _body(
        "tombstones_purged",
        lambda: backend.delete_aged_tombstones(
            before_ts=add_seconds(now, -settings.tombstone_keep_days * 86400)
        ),
    )
    _body(
        "task_rows_trimmed",
        lambda: backend.trim_finished_tasks(
            keep_days=settings.maintenance_keep_days,
            keep_count=settings.maintenance_keep_count, now=now,
        ),
    )

    stats["errors"] = errors
    backend.append_outbox(
        "maintenance.run",
        json.dumps({"task_id": task_id, "stats": stats}, ensure_ascii=False, default=str),
    )
    if errors:
        backend.update_task(
            task_id, status="failed", error="maintenance partial failure: " + "; ".join(errors)
        )
        raise RuntimeError(f"maintenance partial failure: {errors}")
    backend.update_task(task_id, status="done")
    logger.info("maintenance done: %s", stats)
    return stats
