"""worker 子进程（design §3 worker/）：任务循环（租约认领/心跳/重试）+ IPC 唤醒协议。

M2.1 落地：runner.py（TaskRunner 执行循环 + 子进程入口 + WorkerSupervisor 监管）、
ipc.py（stdin 字节唤醒协议 + 兜底轮询双通道）、maintenance.py（maintenance 任务族
框架——凭证回收/过期成员清理/tombstone 90 天清理/任务行保留策略）。
任务类型 ingest + maintenance + semantic_sync（M2-S1）+ semantic_build（m2s-2）+
semantic_retag（m2s-5）+ **reindex/reembed（m2-6——rebuild.py 重建类任务执行体：
reindex 幂等重置重切分全链 / reembed 蓝绿四步 TC-EMB-06）** 本段认领；
delete 仍为预留分发位（归后续段）。
"""
