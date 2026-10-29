"""SQLite 备份快照（design §2 NFR-10 / §8 M2.5——TC-OPS-05）。

`VACUUM INTO` 单语句原子快照（design 指定口径——写目标新文件、并发写不阻塞、
快照一致性由 VACUUM 事务保证）+ `data/objects/` 一并备份（标准库 tarfile——
不引入新依赖，D2 零中间件）。

恢复 = 快照文件即完整库（VACUUM INTO 产物可直接打开）+ tar 解包对象目录；
迁移幂等重放（user_version 只前进——恢复演练断言面见 benchmarks 演练报告）。
"""

from __future__ import annotations

import shutil
import tarfile
from datetime import UTC, datetime
from pathlib import Path
import uuid


def snapshot_database(conn, backup_dir: Path, *, when: datetime | None = None) -> Path:
    """VACUUM INTO 主库快照（目标不存在才写——时间戳 + 随机后缀防同秒覆盖）。"""
    when = when or datetime.now(UTC)
    tag = _tag(when)
    backup_dir.mkdir(parents=True, exist_ok=True)
    out = backup_dir / f"lattice-{tag}.db"
    conn.execute("VACUUM INTO ?", (str(out),))
    return out


def snapshot_objects(objects_dir: Path, backup_dir: Path, *,
                     when: datetime | None = None) -> Path | None:
    """对象目录打包（tar.gz——标准库；空/不存在目录 → None）。"""
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


def snapshot(conn, backup_dir: Path, objects_dir: Path | None = None, *,
             when: datetime | None = None) -> dict:
    """完整快照：主库 + 对象目录 → {database, objects, created_at}。"""
    when = when or datetime.now(UTC)
    db_out = snapshot_database(conn, backup_dir, when=when)
    obj_out = (
        snapshot_objects(objects_dir, backup_dir, when=when)
        if objects_dir is not None else None
    )
    return {
        "database": str(db_out),
        "objects": str(obj_out) if obj_out else None,
        "created_at": _tag(when),
    }


def restore_database(snapshot_path: Path, target_path: Path) -> Path:
    """恢复主库：快照文件即库（拷贝到目标位；目标先清——演练路径，非在线恢复）。"""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snapshot_path, target_path)
    return target_path


def restore_objects(archive_path: Path, target_dir: Path) -> Path:
    """恢复对象目录（tar 解包到目标位——不覆盖既有同名文件以外的内容）。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(target_dir, filter="data")  # py3.12：data 过滤器（路径穿越防护）
    return target_dir


def _tag(when: datetime) -> str:
    return f"{when.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
