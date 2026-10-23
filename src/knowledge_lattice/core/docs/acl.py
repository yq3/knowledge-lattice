"""维度 ACL 编译器（design §5.1）——user_id + 组织上下文 → 方言无关 AclPlan。

四步（v0.4 起全部状态字段进计算——P0-1）：
  第 0 步 成员关系校验（含过期；无有效行即拒绝——403 语义。系统管理员豁免仅限
          管理端点，检索路径同样拒绝——D22）；
  第 2 步 授权展开（backend.read_grants 单条 SQL：active 维度 × active 取值 ×
          未过期——停用取值=收紧 T3、过期授权即失效 T1）；
  第 3 步 每个 active 维度一条 AclDimensionRule（统一空值模板 / 空授权集单条件 /
          retired 不生成——语义规则只在编译器实现一次，#34 必修 1/3；
          「无 IN ()」为 Plan 层不变式，由渲染侧 InValue 节点构造约束）；
  第 4 步 外层常量约束（c.version = d.active_version AND c.tombstone = 0 AND
          d.org_id = :org）与 embed_model 谓词为渲染侧固定节点
          （store/sqlite/acl_render.py——TC-ACL-06/TC-EMB-02）。

分层纪律：本模块不碰 SQL——第 0/2 步读取经 AclBackend 协议收口（store/backend.py，
「core 不碰 SQL」由此闭合，v0.8.3）；AclPlan 方言无关，渲染收口各方言包（D24）。
检索路径无 owner 分支（#34 必修 2——owner 兜底走管理面）。
"""

from __future__ import annotations

from collections.abc import Sequence

from knowledge_lattice.store.backend import AclBackend, AclDimensionRule, AclPlan


class AclDeniedError(Exception):
    """第 0 步拒绝：无有效成员关系（403 语义——检索路径不豁免系统管理员，D22）。"""


def compile_acl(
    backend: AclBackend,
    user_id: str,
    org_id: str,
    *,
    now: str | None = None,
    dataset_ids: Sequence[str] | None = None,
    doc_ids: Sequence[str] | None = None,
    embed_model: str | None = None,
) -> AclPlan:
    """编译一次检索的完整 ACL 计划（方言无关 AclPlan）。

    - now：UTC `YYYY-MM-DD HH:MM:SS`（与 SQLite CURRENT_TIMESTAMP 同格式——造数
      时间戳纪律）；缺省 None 交给存储侧用库时钟。
    - dataset_ids / doc_ids：None=不过滤（搜全部权限内文档）。
    - embed_model：向量路查询谓词（model:dim 标签——D12），由检索管线按当前
      config 标签传入（TC-EMB-02）；FTS/实体路置 None、三路共用同一 Plan。
    - 规则按维度 key 排序（产物逐字稳定——T4 逐字 diff 的确定性基础）。
    """
    membership = backend.read_membership(user_id, org_id, now=now)
    if membership is None:
        raise AclDeniedError(
            f"no active membership: user={user_id!r} org={org_id!r}"
            "（检索路径不豁免管理员——D22）"
        )
    grants = backend.read_grants(user_id, org_id, now=now)
    rules = tuple(
        AclDimensionRule(key=key, grants=values) for key, values in sorted(grants.items())
    )
    return AclPlan(
        org_id=org_id,
        dimension_rules=rules,
        dataset_ids=tuple(dataset_ids) if dataset_ids is not None else None,
        doc_ids=tuple(doc_ids) if doc_ids is not None else None,
        embed_model=embed_model,
    )
