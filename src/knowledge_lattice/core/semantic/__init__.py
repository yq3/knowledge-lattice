"""业务语义（★D23，M2-S1~S3；design §3 core/semantic/）：与 docs 共基础设施（store/domain），
不共享领域模型与 ACL 编译器——包级互斥由测试兜底执法（tests/test_sem_00_layering.py；
import-linter 契约配置随 CI 落——项目不建 Actions，本地门禁承接）。

M2-S1 已落：constants.py（类型白名单三处一致）/ records.py（快照记录）/
norm.py（别名规范化——annotate 同源函数）/ sync.py（同步流程编排）/ adapters/
（SourceAdapter 协议 + template_center / metadata——§5.8）。
后续：annotator.py / expand.py / build.py / yaml_merge.py（M2-S2/S3）。
"""
