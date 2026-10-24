"""AclPlan → 方言无关 AST：节点类型 + 中性构造层（D24——M0b-1 从 sqlite/acl_render.py 上提）。

节点树为**双方言共享**（同一方言无关 AST）：语义规则（统一空值模板 / 空授权集
单条件 / retired 不生成 /「无 IN ()」Plan 层不变式）与外层常量约束只在这里实现
一次；各方言渲染器（store/sqlite/acl_render.py 与 store/postgres/acl_render.py）
只负责把同一棵树渲染为目标 SQL 文本与参数表——方言差异点仅两处：

- 参数语法：sqlite `:name` / PG `%(name)s`；
- 按块维度扫描（dims_scan 注入）：sqlite `json_each(c.dims_json, '$.k')` /
  PG `jsonb_array_elements_text(jsonb_extract_path(c.dims_json, 'k'))`
  （json_each → jsonb 等价路径谓词——§4 PG 映射；键缺失/空数组两方言都产 0 行，
  空值放行语义逐字同源）。

安全纪律（M0a-2 R2 后沿用——渲染器自控参数名序列 + InValue.param_prefix 白名单
fail-closed；_Renderer 不得跨调用拼接片段）：InValue 构造不变式定义在本模块，
双方言渲染器同等受约束。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from knowledge_lattice.store.backend import AclDimensionRule, AclPlan

# 参数名 trace 标签白名单（fail-closed——构造即拒；渲染参数名另由渲染器序列生成）
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 表别名约定（双方言渲染一致）
CHUNKS = "c"
DOCS = "d"
JE = "je"

# 按块维度扫描工厂：维度 key → 表值扫描节点（方言差异唯一注入点）
DimsScan = Callable[[str], "Func"]

# ============ AST 节点（frozen——结构断言与逐字 diff 的基础） ============


@dataclass(frozen=True)
class ColumnRef:
    table: str | None
    name: str


@dataclass(frozen=True)
class BindParam:
    """绑定参数（值随节点携带——AST 自含，render_sql 产出完整参数表）。"""

    name: str
    value: object


@dataclass(frozen=True)
class Literal:
    """结构常量（tombstone=0 / '$.key' JSON path / 维度 key）——转义渲染，非数据值。"""

    value: int | str


@dataclass(frozen=True)
class Eq:
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True)
class And:
    parts: tuple["Expr", ...]


@dataclass(frozen=True)
class Or:
    parts: tuple["Expr", ...]


@dataclass(frozen=True)
class InValue:
    """expr IN (绑定参数列表)——值集非空为构造不变式（「无 IN ()」Plan 层红线）。

    param_prefix 仅为 trace 标签：标识符白名单校验（fail-closed，构造即拒——
    M0a-2 Committer R1 P1-1 防御纵深），**绝不进入 SQL 文本**——渲染参数名由
    渲染器按遍历顺序自控生成（g<seq>_<i>），与库内数据（维度 key 等）无关。
    """

    expr: "Expr"
    param_prefix: str
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError(
                "InValue 空值集会渲染出非法的 `IN ()`——空授权集维度只产 NotExists "
                "单条件（Plan 层不变式，#34 必修 3 / T22）"
            )
        if not _IDENTIFIER_RE.match(self.param_prefix):
            raise ValueError(
                f"InValue.param_prefix 必须为合法 SQL 标识符（trace 标签，"
                f"不进入 SQL 文本）: {self.param_prefix!r}"
            )


@dataclass(frozen=True)
class InSubquery:
    """expr IN (<固定子查询引用>)——visible_docs CTE 引用（文本为结构常量）。"""

    expr: "Expr"
    subquery: str


@dataclass(frozen=True)
class Match:
    """FTS5 全文匹配谓词：`<别名>.<虚表名> MATCH :<param>`（sqlite 方言节点——
    查询串经绑定参数；PG FTS 路（to_tsquery/ts_rank 加权）随 M0b-2/M1）。"""

    source: str
    fts_name: str
    param: BindParam


@dataclass(frozen=True)
class Func:
    """函数调用（含表值函数 json_each / jsonb 等价）——name 为受限标识符、args 全为节点。"""

    name: str
    args: tuple["Expr", ...]


@dataclass(frozen=True)
class TableRef:
    name: str
    alias: str | None = None


@dataclass(frozen=True)
class Join:
    table: TableRef
    on: "Expr"


@dataclass(frozen=True)
class Select1:
    """SELECT 1 FROM <from> [AS <alias>] [JOIN …] [WHERE …]——EXISTS 子查询的通用形态。"""

    from_table: "Func | TableRef"
    alias: str | None = None
    joins: tuple[Join, ...] = ()
    predicate: "Expr | None" = None


@dataclass(frozen=True)
class Exists:
    subquery: Select1


@dataclass(frozen=True)
class NotExists:
    subquery: Select1


Expr = (
    ColumnRef | BindParam | Literal | Eq | And | Or | InValue | InSubquery | Match
    | Func | Exists | NotExists
)

# ============ 中性构造层（AclPlan → 节点树；方言仅注入 dims_scan） ============


def build_dimension_rule_ast(rule: AclDimensionRule, *, dims_scan: DimsScan) -> Expr:
    """单维统一模板（§5.1 第 3 步）：有值则过滤、空值放行。

    有授权 → Or[NotExists(空值放行), Exists[je.value IN (授权集)]]；
    空授权 → NotExists 单条件（该维只见空值文档——T22；禁止 IN ()）。
    required/enabled 不参与（生命周期与过滤解耦——T4/T20）。
    """
    null_pass = NotExists(Select1(from_table=dims_scan(rule.key)))
    if rule.is_empty:
        return null_pass
    hit = Exists(
        Select1(
            from_table=dims_scan(rule.key),
            alias=JE,
            # param_prefix 为静态 trace 标签（渲染参数名由渲染器序列生成）
            predicate=InValue(ColumnRef(JE, "value"), "dim", rule.grants),
        )
    )
    return Or((null_pass, hit))


def build_acl_ast(plan: AclPlan, *, dims_scan: DimsScan) -> Expr | None:
    """维度规则合取——FTS/向量/实体三路共享的 ACL 片段（TC-ACL-06）。

    无 active 维度（或全部 retired——唯一放宽路径不生成条件，T20④）→ None。
    """
    if not plan.dimension_rules:
        return None
    blocks = [build_dimension_rule_ast(rule, dims_scan=dims_scan) for rule in plan.dimension_rules]
    if len(blocks) == 1:
        return blocks[0]
    return And(tuple(blocks))


def version_eq() -> Eq:
    return Eq(ColumnRef(CHUNKS, "version"), ColumnRef(DOCS, "active_version"))


def tombstone_eq() -> Eq:
    return Eq(ColumnRef(CHUNKS, "tombstone"), Literal(0))


def org_eq(plan: AclPlan) -> Eq:
    return Eq(ColumnRef(DOCS, "org_id"), BindParam("org", plan.org_id))


def filter_nodes(plan: AclPlan) -> tuple[Expr, ...]:
    """dataset/doc 过滤（None=不过滤；空序列=恒假——不产 IN ()）。"""
    nodes: list[Expr] = []
    for column, prefix, ids in (
        ("dataset_id", "ds", plan.dataset_ids),
        ("id", "doc", plan.doc_ids),
    ):
        if ids is None:
            continue
        if ids:
            nodes.append(InValue(ColumnRef(DOCS, column), prefix, tuple(ids)))
        else:
            nodes.append(Eq(Literal(1), Literal(0)))
    return tuple(nodes)


def build_where_ast(
    plan: AclPlan, *, dims_scan: DimsScan, vector: bool = False
) -> And:
    """完整 WHERE（基础/向量/实体路）：维度 ACL + 外层常量约束（固定节点——
    TC-ACL-06）+ dataset/doc 过滤；vector=True 追加 embed_model 谓词
    （TC-EMB-02——三路共用同一 Plan，谓词仅向量路渲染）。"""
    parts: list[Expr] = []
    acl = build_acl_ast(plan, dims_scan=dims_scan)
    if acl is not None:
        parts.append(acl)
    parts.append(And((version_eq(), tombstone_eq(), org_eq(plan))))
    parts.extend(filter_nodes(plan))
    if vector:
        if plan.embed_model is None:
            raise ValueError(
                "vector=True 需要 plan.embed_model（model:dim 标签——D12/TC-EMB-02）"
            )
        parts.append(
            Eq(ColumnRef(CHUNKS, "embed_model"), BindParam("current_model", plan.embed_model))
        )
    return And(tuple(parts))


# ============ visible_docs 备选（双写法之一——纯 JOIN/EXISTS，无 JSON 方言函数） ============


def build_visible_docs_rule_ast(rule: AclDimensionRule, org_id: str) -> Expr:
    """单维 visible_docs 等价块（基于 document_dimensions）：文档在该维无任何行，
    或有一行取值 ∈ 授权集——与按块模板逐字等价（TC-ACL-07）。

    空授权 → 无任何行才可见（与 NOT EXISTS 单条件同义——不出 IN ()）。
    只按 dim.key/org_id 匹配、**不读 dim.status**（M0a-2 Committer R1 P3-1）：
    Plan 规则集编译时点已只含 active 维度，CTE 再读可变状态会在 compile→execute
    竞态下（维度被退役）与按块路（按 Plan 授权集过滤）不等价。
    """
    conds: list[Expr] = [
        Eq(ColumnRef("dd", "doc_id"), ColumnRef("d", "id")),
        Eq(ColumnRef("dim", "key"), Literal(rule.key)),
        Eq(ColumnRef("dim", "org_id"), BindParam("org", org_id)),
    ]
    if not rule.is_empty:
        # 有行且无一行命中授权集 → 该维不可见（NOT EXISTS 反转：可见=无行或有命中）
        inner = Select1(
            from_table=TableRef("document_dimensions", "dd2"),
            joins=(
                Join(
                    TableRef("dimension_values", "v"),
                    And((
                        Eq(ColumnRef("v", "id"), ColumnRef("dd2", "value_id")),
                        Eq(ColumnRef("v", "dimension_id"), ColumnRef("dd2", "dimension_id")),
                        Eq(ColumnRef("v", "status"), Literal("active")),
                    )),
                ),
            ),
            predicate=And((
                Eq(ColumnRef("dd2", "doc_id"), ColumnRef("dd", "doc_id")),
                Eq(ColumnRef("dd2", "dimension_id"), ColumnRef("dd", "dimension_id")),
                InValue(ColumnRef("v", "value"), "dim", rule.grants),
            )),
        )
        conds.append(NotExists(inner))
    return NotExists(
        Select1(
            from_table=TableRef("document_dimensions", "dd"),
            joins=(
                Join(
                    TableRef("dimensions", "dim"),
                    Eq(ColumnRef("dim", "id"), ColumnRef("dd", "dimension_id")),
                ),
            ),
            predicate=And(tuple(conds)),
        )
    )


def build_visible_docs_parts(plan: AclPlan) -> tuple[Expr, Expr]:
    """visible_docs 双写法的两段表达式（方言无关）：CTE WHERE 与外层 WHERE。

    渲染由各方言 render_visible_docs_select 完成（CTE 与外层共用同一渲染状态——
    参数名序列连续、org 复用同名同值；M0b 实验选定后双写法二删其一）。
    """
    blocks = [build_visible_docs_rule_ast(rule, plan.org_id) for rule in plan.dimension_rules]
    cte_where = And((Eq(ColumnRef("d", "org_id"), BindParam("org", plan.org_id)), *blocks))
    outer = And((
        InSubquery(ColumnRef(CHUNKS, "doc_id"), "SELECT doc_id FROM visible_docs"),
        version_eq(),
        tombstone_eq(),
        Eq(ColumnRef(DOCS, "org_id"), BindParam("org", plan.org_id)),
        *filter_nodes(plan),
    ))
    return cte_where, outer
