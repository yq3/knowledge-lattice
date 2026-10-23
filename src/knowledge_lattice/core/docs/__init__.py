"""文档域（design §3 core/docs/——v0.8.4 对称分包）。

M0a-2 已落：acl.py（维度 ACL 编译器——产出方言无关 AclPlan，§5.1 四步；第 0/2 步
读取经 AclBackend 协议收口、「core 不碰 SQL」）。随 M0a-3+ 再落：retrieve.py
（检索管线编排）/ ingest.py（摄取管线编排）/ chunking.py（结构感知切分）/
excel_chunking.py / quality.py（区分度检测）。
"""
