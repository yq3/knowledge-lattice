"""REST 控制面（design §3 api/）：upload / documents / datasets / orgs / tasks / search / admin / semantic。

只做协议转换（整理参数与鉴权/组织上下文后调 core，业务校验在 core）。
M0a-3 已落：upload.py（multipart 上传 + Bearer/org 依赖）、documents.py（详情状态）、
tasks.py（任务查询）、search.py（POST /api/search）、admin.py（dev token + 维度/库只读）。
datasets/orgs 全量管理与 semantic 随 M1+/M2-S。
"""
