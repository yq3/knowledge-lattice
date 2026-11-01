"""审计事件类型常量（design §4 audit_outbox.event_type / audit_events.action）。

本模块是事件类型的**单一登记处**（防字符串散落漂移）：

- docs 侧治理动作（M2.4 m2-2 段接入——业务库同事务写 audit_outbox）；
- maintenance.run（M2.1 沿用——任务级汇总事件）；
- 语义侧三类（**常量预留、不实现**——归 m2s-1/m2s-3；TC-OPS-01 中 #38 P1-7
  语义断言落 TC-BUILD-03 / TC-YAML-03 / T-S9，随语义轨道段验收）；
- 管理面三类（**常量预留**——依赖 m2-3 管理面写端点；本段以既有端点可触发的
  事件验收，管理面落地后补验——TEST-CASES 回写注明分批口径）。
"""

from __future__ import annotations

# ---- docs 侧治理动作（m2-2 A 组接入：与业务写同事务） ----

EVENT_DOCUMENT_UPLOAD = "document.upload"          # 首次上传（m1-2 P3-6 清偿）
EVENT_DOCUMENT_OVERWRITE = "document.overwrite"    # 覆盖上传
EVENT_DOCUMENT_DELETE = "document.delete"          # 删除文档（M1 既有口径）
EVENT_TASK_CANCEL = "task.cancel"                  # 任务取消（m2-1 P3-17 清偿）
EVENT_DOCUMENT_DIMS_CHANGE = "document.dims_change"  # 维度值 PATCH（M1 既有口径）
EVENT_DATASET_DELETE = "dataset.delete"            # 删库（T19 半句收口——M2.4）
EVENT_UPLOAD_CREDENTIAL_ISSUED = "upload.credential_issued"  # 凭证签发（M1 既有口径）
EVENT_UPLOAD_CONSUME = "upload.consume"            # 凭证消费（M1 既有口径）
EVENT_UPLOAD_RECLAIM = "upload.reclaim"            # 过期未消费凭证回收（m1-3 既有——
                                                   # m2-3 B1 常量化收编）

# ---- maintenance（M2.1 沿用） ----

EVENT_MAINTENANCE_RUN = "maintenance.run"

# ---- 语义侧（m2s-1 起：semantic.sync 已接入——同步 run 终态全事件；build/yaml_merge
#      常量已备、事件发射归 m2s-2/m2s-3——TC-BUILD-03 / TC-YAML-03 / T-S9） ----

EVENT_SEMANTIC_SYNC = "semantic.sync"
EVENT_SEMANTIC_BUILD = "semantic.build"
EVENT_SEMANTIC_YAML_MERGE = "semantic.yaml_merge"

# ---- 管理面预留（m2-3——TC-OPS-06/07/08 写端点落地后接入） ----
# grants.replace：members grants 全量替换（TC-OPS-08——审计入 outbox）
# dimension.value_disable：取值停用（TC-OPS-07①）
# dimension.retire：维度退役（TC-OPS-07②——T20 退役审计半句）

EVENT_GRANTS_REPLACE = "grants.replace"
EVENT_DIMENSION_VALUE_DISABLE = "dimension.value_disable"
EVENT_DIMENSION_RETIRE = "dimension.retire"
# ---- 成员关系写路径（m2-6 A3——m2-4 N-1 用户裁定选 a：JIT 后 API 面开通闭环） ----
EVENT_MEMBER_ADD = "member.add"            # 加组织（POST /members）
EVENT_MEMBER_UPDATE = "member.update"      # 角色变更/软停用/续期（PATCH）
EVENT_MEMBER_REMOVE = "member.remove"      # 移出组织（DELETE——级联清授权）
# ---- 维度取值写路径（m2-6 A4——values CRUD + D19 重新启用恢复路径） ----
EVENT_DIMENSION_VALUE_CREATE = "dimension.value_create"  # 新增取值（POST values）
EVENT_DIMENSION_VALUE_ENABLE = "dimension.value_enable"   # 重新启用（D19 解锁路径）

# ---- 认证事件（m2-4 M2.2 生产化认证段——TC-AUTH-03/04/05/T13） ----

EVENT_AUTH_USER_JIT = "auth.user_jit_created"       # SSO 首次登录 JIT 建档（D16）
EVENT_AUTH_DELEGATED = "auth.delegated"             # 委托 token 认证成功（双身份
                                                    #  user+act——TC-AUTH-04）
EVENT_AUTH_SSO_REFUSED = "auth.sso_refused"         # SSO token 拒绝（透传原始
                                                    #  token / act 非法——outcome=refused）
EVENT_AUTH_TRUSTED_SUBSYSTEM = "auth.trusted_subsystem"  # 可信子系统判定（成功
                                                    #  accepted / 越界·冒充·白名单
                                                    #  外·限流 refused——T13）
EVENT_AUTH_PERMISSIONS_IGNORED = "auth.request_permissions_ignored"  # 请求体权限
                                                    #  字段忽略并记审计（FR-4/D18
                                                    #  v0.6.1 统一口径——附录 A-9）

__all__ = [
    "EVENT_DOCUMENT_UPLOAD",
    "EVENT_DOCUMENT_OVERWRITE",
    "EVENT_DOCUMENT_DELETE",
    "EVENT_TASK_CANCEL",
    "EVENT_DOCUMENT_DIMS_CHANGE",
    "EVENT_DATASET_DELETE",
    "EVENT_UPLOAD_CREDENTIAL_ISSUED",
    "EVENT_UPLOAD_CONSUME",
    "EVENT_UPLOAD_RECLAIM",
    "EVENT_MAINTENANCE_RUN",
    "EVENT_SEMANTIC_SYNC",
    "EVENT_SEMANTIC_BUILD",
    "EVENT_SEMANTIC_YAML_MERGE",
    "EVENT_GRANTS_REPLACE",
    "EVENT_DIMENSION_VALUE_DISABLE",
    "EVENT_DIMENSION_RETIRE",
    "EVENT_MEMBER_ADD",
    "EVENT_MEMBER_UPDATE",
    "EVENT_MEMBER_REMOVE",
    "EVENT_DIMENSION_VALUE_CREATE",
    "EVENT_DIMENSION_VALUE_ENABLE",
    "EVENT_AUTH_USER_JIT",
    "EVENT_AUTH_DELEGATED",
    "EVENT_AUTH_SSO_REFUSED",
    "EVENT_AUTH_TRUSTED_SUBSYSTEM",
    "EVENT_AUTH_PERMISSIONS_IGNORED",
]
