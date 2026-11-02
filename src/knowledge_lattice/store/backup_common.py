"""备份异常类（方言中立——P2-4/R2 + P3-15）。

两态拆分（NFR-10 备份可运维信号）：

- ``BackupToolUnavailable``：**工具缺失**（_resolve_command 找不到 pg_dump/
  pg_restore，或子进程 FileNotFoundError——命令二进制不存在）——部署面显式
  未配置状态：maintenance 记 ``unavailable`` stats + 告警，**不判任务失败**；
- ``BackupToolError``（基类）：**真实快照失败**（子进程非零——DSN 错/磁盘满/
  权限等）——必须落 maintenance errors → 任务 failed（可发现信号）。

放中立模块（而非 store/postgres/backup.py）的理由：worker/maintenance.py 需
按异常类型分态处置，方言包 import 会造成 worker→store.postgres 的反向依赖
（Committer R1 P3-15）。
"""

from __future__ import annotations


class BackupToolError(RuntimeError):
    """备份工具失败基类（子进程非零等真实失败——fail-closed，不静默假快照）。"""


class BackupToolUnavailable(BackupToolError):
    """备份工具缺失/未配置（部署面显式状态——不判任务失败，记 unavailable）。"""
