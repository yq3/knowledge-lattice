"""PostgreSQL 备份快照（design §2 NFR-10 / §8 M2.5 / §4 PG 映射——TC-OPS-05）。

pg_dump（custom format）+ pg_restore（stdin/stdout 流形态）——进程外命令属
部署工具链（不违 D2）。命令解析顺序：

1. `LATTICE_PG_DUMP_CMD` / `LATTICE_PG_RESTORE_CMD`（空格分隔的命令前缀——
   容器形态如 `docker exec lattice-pg pg_dump`：PG 跑容器时工具在容器内）；
2. PATH 上的 `pg_dump` / `pg_restore`；
3. 都不可得 → **BackupToolUnavailable**（store/backup_common.py——中立模块，
   P2-4/R2 两态拆分：工具缺失≠真实失败；子进程非零仍 BackupToolError 上抛
   → maintenance errors → 任务 failed）。

stdout/stdin 流形态对两种部署（本机安装 / docker exec）统一：dump 写本地
文件不经容器文件系统、restore 从本地文件流入。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from knowledge_lattice.store.backup_common import BackupToolError, BackupToolUnavailable

DUMP_CMD_ENV = "LATTICE_PG_DUMP_CMD"
RESTORE_CMD_ENV = "LATTICE_PG_RESTORE_CMD"


def _resolve_command(env_name: str, binary: str) -> list[str]:
    prefix = os.environ.get(env_name)
    if prefix:
        return prefix.split()
    found = shutil.which(binary)
    if found:
        return [found]
    raise BackupToolUnavailable(
        f"{binary} 不可用：设 {env_name}（容器形态如 'docker exec lattice-pg"
        f" {binary}'）或将 {binary} 装入 PATH——备份快照 fail-closed"
    )


def snapshot_database(
    dsn: str, backup_dir: Path, *, schema: str | None = None,
    when: datetime | None = None,
) -> Path:
    """pg_dump -Fc（custom format）→ 本地文件（stdout 流）。schema 非 None 时
    只 dump 该 schema（测试隔离 schema / 多租形态）。"""
    when = when or datetime.now(UTC)
    tag = _tag(when)
    backup_dir.mkdir(parents=True, exist_ok=True)
    out = backup_dir / f"lattice-{tag}.dump"
    cmd = _resolve_command(DUMP_CMD_ENV, "pg_dump") + [
        "--format=custom", "--no-owner", "--no-privileges",
    ]
    if schema is not None:
        cmd += ["--schema", schema]
    cmd.append(dsn)
    try:
        with open(out, "wb") as fh:
            proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        # P2-4/R2：命令二进制不存在（如 docker 未装）——工具缺失态非真实失败
        out.unlink(missing_ok=True)
        raise BackupToolUnavailable(
            f"pg_dump command not found ({' '.join(cmd[:2])}…): {exc}"
        ) from exc
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        raise BackupToolError(
            f"pg_dump failed ({proc.returncode}): {proc.stderr.decode(errors='replace')[:500]}"
        )
    return out


def restore_database(dsn: str, dump_path: Path) -> None:
    """pg_restore 到 dsn（stdin 流——本地 dump 文件不经容器文件系统）。"""
    cmd = _resolve_command(RESTORE_CMD_ENV, "pg_restore") + [
        "--no-owner", "--no-privileges", "--dbname", dsn,
    ]
    try:
        with open(dump_path, "rb") as fh:
            proc = subprocess.run(cmd, stdin=fh, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise BackupToolUnavailable(
            f"pg_restore command not found ({' '.join(cmd[:2])}…): {exc}"
        ) from exc
    if proc.returncode != 0:
        raise BackupToolError(
            f"pg_restore failed ({proc.returncode}):"
            f" {proc.stderr.decode(errors='replace')[:500]}"
        )


def snapshot_objects(objects_dir: Path, backup_dir: Path, *,
                     when: datetime | None = None) -> Path | None:
    """对象目录打包（sqlite/backup.py 同款——标准库 tar.gz）。"""
    when = when or datetime.now(UTC)
    if not objects_dir.is_dir() or not any(objects_dir.iterdir()):
        return None
    tag = _tag(when)
    backup_dir.mkdir(parents=True, exist_ok=True)
    out = backup_dir / f"objects-{tag}.tar.gz"
    with tarfile.open(out, "x:gz") as tar:
        for p in sorted(objects_dir.iterdir()):
            tar.add(p, arcname=p.name)
    return out


def snapshot(dsn: str, backup_dir: Path, objects_dir: Path | None = None, *,
             schema: str | None = None, when: datetime | None = None) -> dict:
    """完整快照：pg_dump + 对象目录 → {database, objects, audit_months,
    created_at}。audit_months 恒 None——pg 审计月分区在库内、pg_dump 天然含
    （无独立月库文件——B3 口径与 sqlite 形态对齐的显式占位）。"""
    when = when or datetime.now(UTC)
    db_out = snapshot_database(dsn, backup_dir, schema=schema, when=when)
    obj_out = (
        snapshot_objects(objects_dir, backup_dir, when=when)
        if objects_dir is not None else None
    )
    return {
        "database": str(db_out),
        "objects": str(obj_out) if obj_out else None,
        "audit_months": None,  # 分区在库内（pg_dump 天然含）——B3 口径
        "created_at": _tag(when),
    }


def _tag(when: datetime) -> str:
    return f"{when.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
