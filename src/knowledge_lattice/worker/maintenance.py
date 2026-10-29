"""maintenance 任务体（M2.1 框架 + M2.4 m2-2 扩展——design §3 maintenance
任务族 + §5.3）。

框架形态：app.py 内嵌调度器周期投递 **maintenance 任务行**（形态保留），
执行体进 worker（TaskRunner 的 maintenance executor 调本模块 run_maintenance）。

任务体（**MAINTENANCE_BODIES 注册表**——P3-N11 兑现：新任务体注册进表即被
周期任务携带执行；顺序敏感——ship 先于 seal（防「先封存后搬运」死锁）、
seal 先于 prune）：

1. 未消费凭证回收（M1-3 CredentialService.purge_expired 收编——TC-CRED-05）；
2. 过期成员物理清理（backend.delete_expired_memberships——§5.1）；
3. tombstone 90 天物理清理（backend.delete_aged_tombstones——0004 基准）；
4. maintenance 任务行保留策略（m1-3 P3-19）；
5. **审计搬运**（m2-2 A2）：ship_outbox——outbox → 月库 audit_events +
   回填 shipped_at（TC-OPS-01）；
6. **审计封存**（m2-2 B1）：seal_audit_months——过月月库只读 + 记末哈希；
7. **审计保留期**（m2-2 B3）：prune_audit_months——12 个月整文件/分区删除；
8. **备份快照**（m2-2 D2）：backup_snapshot——VACUUM INTO / pg_dump +
   objects tar（TC-OPS-05；RPO ≤24h 由 maintenance 周期保障）；
9. **outbox 已搬运行保留期**（R2 P3-1，用户裁定边界②）：trim_shipped_outbox
   ——与月库保留期同源（audit_keep_months）只删已搬运行（FR-6 口径完整）。

各任务体相互隔离（单个体失败不阻断其余——收集错误后统一落任务 failed 留痕）。
语义任务体（sem_chunk_entities 对账兜底）归 M2-S3——注册表即扩展位。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from knowledge_lattice.domain.audit_events import EVENT_MAINTENANCE_RUN
from knowledge_lattice.store.taskclock import add_seconds, utc_now_ts

logger = logging.getLogger(__name__)

# ---- P3-N11（m2-1 移交→m2-2 兑现）：任务体注册表 ----
#
# name → callable(ctx) → stats 片段。ctx = (backend, credentials, settings, now)。
# 顺序 = dict 插入序（Python 3.7+）：ship 必须先于 seal（有未搬运行的月份不封
# ——seal 自身也有守卫，双保险）；seal 先于 prune（先封存再删过期）。
MAINTENANCE_BODIES: dict[str, Callable[..., object]] = {}


def _register(name: str) -> Callable:
    def deco(fn):
        MAINTENANCE_BODIES[name] = fn
        return fn
    return deco


@_register("credentials_purged")
def _credentials_body(backend, credentials, settings, now):
    return credentials.purge_expired()["reclaimed"]


@_register("memberships_purged")
def _memberships_body(backend, credentials, settings, now):
    return backend.delete_expired_memberships(now=now)


@_register("tombstones_purged")
def _tombstones_body(backend, credentials, settings, now):
    return backend.delete_aged_tombstones(
        before_ts=add_seconds(now, -settings.tombstone_keep_days * 86400)
    )


@_register("task_rows_trimmed")
def _trim_body(backend, credentials, settings, now):
    return backend.trim_finished_tasks(
        keep_days=settings.maintenance_keep_days,
        keep_count=settings.maintenance_keep_count, now=now,
    )


@_register("audit_shipped")
def _ship_body(backend, credentials, settings, now):
    """A2 搬运：outbox → 月库 audit_events + 回填 shipped_at（TC-OPS-01）。"""
    return backend.ship_outbox(now=now)


@_register("audit_months_sealed")
def _seal_body(backend, credentials, settings, now):
    """B1 封存：过月月库只读 + 记末哈希（TC-OPS-02①）。"""
    return backend.seal_audit_months(now=now)


@_register("audit_months_pruned")
def _prune_body(backend, credentials, settings, now):
    """B3 保留期：audit_keep_months（默认 12）整文件/分区删除（TC-OPS-02③）。"""
    return backend.prune_audit_months(
        keep_months=settings.audit_keep_months, now=now
    )


@_register("backup_snapshot")
def _backup_body(backend, credentials, settings, now):
    """D2 备份快照：VACUUM INTO / pg_dump + objects tar（TC-OPS-05；快照
    落 data_dir/backups——目的地缺口 G-5 维持 known-gaps 登记）。

    节流（RPO 口径）：距上次成功快照 < backup_interval_s（默认 24h）跳过——
    maintenance 周期（300s）不必每次都快照；interval<=0 = 每轮都跑（测试）。

    **两态处置（P2-4/R2）**：工具缺失（BackupToolUnavailable——pg_dump 未配
    置/命令二进制不存在）记 unavailable 状态 + 告警、**不判任务失败**（部署
    面显式未配置）；**真实快照失败（BackupToolError——子进程非零：DSN 错/
    磁盘满/权限）重新上抛** → run_maintenance errors → 任务 failed
    （error 前缀 backup_snapshot——NFR-10 可发现信号）。
    """
    from pathlib import Path

    from knowledge_lattice.store.backup_common import BackupToolUnavailable

    backup_dir = Path(settings.data_dir) / "backups"
    interval = getattr(settings, "backup_interval_s", 86400.0)
    if interval and interval > 0 and backup_dir.is_dir():
        existing = sorted(backup_dir.glob("lattice-*"))
        if existing:
            import time as _time

            age = _time.time() - existing[-1].stat().st_mtime
            if age < interval:
                return "throttled"
    try:
        result = backend.backup_snapshot(
            backup_dir, objects_dir=Path(settings.data_dir) / "objects",
        )
    except BackupToolUnavailable as exc:
        logger.warning("backup tool unavailable (snapshot skipped): %s", exc)
        return f"unavailable: {exc}"
    return {"database": result["database"], "objects": result["objects"]}  # 真实失败上抛（P2-4）


@_register("audit_outbox_trimmed")
def _outbox_trim_body(backend, credentials, settings, now):
    """P3-1/R2（用户裁定边界②）：已搬运 outbox 行纳入保留期清理——
    `DELETE WHERE shipped_at IS NOT NULL AND shipped_at < cutoff`（cutoff 与
    月库保留期同源 audit_keep_months 个月，**只删已搬运行**——未搬运行是
    「业务改了就一定有审计」的未落地承诺，永不删）。返回删除行数。"""
    from knowledge_lattice.store.audit_chain import month_of, month_shift

    cutoff_month = month_shift(month_of(now), -settings.audit_keep_months)
    cutoff = f"{cutoff_month[:4]}-{cutoff_month[4:6]}-01 00:00:00"
    return backend.trim_shipped_outbox(before_ts=cutoff)


def run_maintenance(backend, credentials, settings, task_id: str) -> dict:
    """maintenance 任务执行体（自管任务行状态——与 ingest.run_task 同款形态）。

    凭证回收需要 credentials 服务（core）；其余经 backend 协议方法（core 不碰
    SQL 纪律——SQL 已下沉双方言 backend）。遍历 MAINTENANCE_BODIES 注册表。
    """
    backend.update_task(task_id, status="running")
    stats: dict[str, object] = {}
    errors: list[str] = []
    now = utc_now_ts()

    for name, body in MAINTENANCE_BODIES.items():
        try:
            stats[name] = body(backend, credentials, settings, now)
        except Exception as exc:  # noqa: BLE001 —— 单个体失败不阻断其余
            logger.exception("maintenance body failed: %s", name)
            errors.append(f"{name}: {exc}")

    stats["errors"] = errors
    backend.append_outbox(
        EVENT_MAINTENANCE_RUN,  # P3-12/R2：常量替代字面量（登记处闭环）
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
