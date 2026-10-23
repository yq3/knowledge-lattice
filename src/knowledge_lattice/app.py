"""FastAPI 入口（design §3）：装配路由/MCP/DB/worker + 内嵌调度器（maintenance 周期投递、指纹探针周期档）。

M0a-3 服务壳落本模块；M0a-1 仅占位（禁引 fastapi 重依赖——按需最小化）。
"""
