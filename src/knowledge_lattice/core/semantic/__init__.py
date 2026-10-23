"""业务语义（★D23，M2-S1~S3；design §3 core/semantic/）：与 docs 共基础设施（store/domain），
不共享领域模型与 ACL 编译器——包级互斥由 import-linter 契约执法（M0a-2 起 CI）。

模块规划：annotator.py / expand.py / build.py / yaml_merge.py / sync.py / adapters/（§3）。
M0a/M0b/M1 不含语义层——本包 M0a-1 仅落占位。
"""
