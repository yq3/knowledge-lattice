"""FastMCP 单一 server（design §3 mcp/server.py）：docs 组（search/upload/fetch/list_documents）+
semantic 组（get_entity/search_entities/describe_table——m2s-2 首批；annotate M2-S2 后段）
分组注册 + 鉴权中间件（60s 超时）。

M0a-3 已落：server.py（search 工具 + 60s 超时中间件 + D18 组织上下文规则）；
upload/fetch/list_documents 随 M1（凭证三步/版本链）。
"""
