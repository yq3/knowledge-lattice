"""worker 子进程（design §3 worker/）：任务循环（租约认领/心跳/重试）+ IPC 唤醒协议。

M2.1 落地：runner.py（TaskRunner 执行循环 + 子进程入口 + WorkerSupervisor 监管）、
ipc.py（stdin 字节唤醒协议 + 兜底轮询双通道）、maintenance.py（maintenance 任务族
框架——凭证回收/过期成员清理/tombstone 90 天清理/任务行保留策略，预留 type 分发位）。
任务类型 ingest + maintenance 本段认领；reindex/reembed/delete/semantic_* 为预留
分发位（归后续段）。
"""
