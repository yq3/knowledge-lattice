"""共享后端工厂（M2.1 R2 / Committer R1 P2-4——app 与 worker 子进程同源装配）。

此前 worker 默认装配按 LATTICE_PG_DSN 自选 PG 而 app 恒 sqlite——同一部署下
主进程写 sqlite、worker 连 PG 的 split-brain。本工厂是**两侧唯一**的后端构造
入口：app 尚未支持 PG（m2-2 接线），故恒 sqlite；检测到 LATTICE_PG_DSN 时
告警（防操作者误以为已切 PG 后端）。
"""

from __future__ import annotations

import logging
import os

from knowledge_lattice.config import Settings

logger = logging.getLogger(__name__)


def build_backend(settings: Settings):
    """sqlite 后端（连接工厂引导迁移 + ThreadLocalBackend 每线程一连接）——
    app.create_app 与 worker.build_default_services 共用，杜绝装配分叉。"""
    if os.environ.get("LATTICE_PG_DSN"):
        logger.warning(
            "LATTICE_PG_DSN 已设置但 PG 后端未接线（app/worker 一致使用 sqlite——"
            "D24 双后端的 app 侧接入归 m2-2；当前不产生跨库 split-brain）"
        )
    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.threaded import ThreadLocalBackend

    bootstrap = connect(settings.db_path)
    migrate_db(bootstrap)
    bootstrap.close()
    return ThreadLocalBackend(settings.db_path)
