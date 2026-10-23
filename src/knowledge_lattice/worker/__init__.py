"""worker 子进程（design §3 worker/）：任务循环（租约认领/心跳/重试）+ IPC 唤醒协议。
任务类型 ingest/reindex/reembed/delete + semantic_* + maintenance。M2 子进程化；M0a-1 仅占位。"""
