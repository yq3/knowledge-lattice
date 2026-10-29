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

# ---- maintenance（M2.1 沿用） ----

EVENT_MAINTENANCE_RUN = "maintenance.run"

# ---- 语义侧预留（m2s-1 / m2s-3——不实现，注释锚点） ----
# semantic.sync：源系统同步完成（分批 upsert + missing/retired 推进）——归 m2s-1
# semantic.build：构建产物原子切换（dict_rev + AC 自动机）——归 m2s-1/m2s-2
# semantic.yaml_merge：YAML 覆盖层合并（curated 列写入）——归 m2s-2/m2s-3

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

__all__ = [
    "EVENT_DOCUMENT_UPLOAD",
    "EVENT_DOCUMENT_OVERWRITE",
    "EVENT_DOCUMENT_DELETE",
    "EVENT_TASK_CANCEL",
    "EVENT_DOCUMENT_DIMS_CHANGE",
    "EVENT_DATASET_DELETE",
    "EVENT_UPLOAD_CREDENTIAL_ISSUED",
    "EVENT_UPLOAD_CONSUME",
    "EVENT_MAINTENANCE_RUN",
    "EVENT_SEMANTIC_SYNC",
    "EVENT_SEMANTIC_BUILD",
    "EVENT_SEMANTIC_YAML_MERGE",
    "EVENT_GRANTS_REPLACE",
    "EVENT_DIMENSION_VALUE_DISABLE",
    "EVENT_DIMENSION_RETIRE",
]
