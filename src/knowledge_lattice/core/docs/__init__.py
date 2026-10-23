"""文档域（design §3 core/docs/——v0.8.4 对称分包）。

模块随 M0a-2 摄取/检索链实装：ingest.py（摄取管线编排）/ chunking.py（结构感知切分）/
excel_chunking.py / retrieve.py（检索管线）/ acl.py（维度 ACL 编译器——产出 AclPlan，
编译逻辑属 M0a-2）/ quality.py（区分度检测）。M0a-1 仅落包占位。
"""
