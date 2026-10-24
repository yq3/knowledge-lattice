"""AclPlan → 方言无关 AST：节点类型 + 中性构造层（D24——M0b-1 从 sqlite/acl_render.py 上提）。

节点树为**双方言共享**（同一方言无关 AST）：语义规则（统一空值模板 / 空授权集
单条件 / retired 不生成 /「无 IN ()」Plan 层不变式）与外层常量约束只在这里实现
一次；各方言渲染器（store/sqlite/acl_render.py 与 store/postgres/acl_render.py）
只负责把同一棵树渲染为目标 SQL 文本与参数表——方言差异仅参数语法一处：
sqlite `:name` / PG `%(name)s`。

**visible_docs CTE 唯一路径（M0b-3 拍板 1——json_each/jsonb 按块模板已删）**：
ACL 计算统一"先按文档求可见集（CTE、MATERIALIZED——PG 计划器内联病理一词修复，
报告 §2.3）、外层 `c.doc_id IN (visible_docs)`"；CTE 纯 JOIN/EXISTS、无 JSON
方言函数（D24 可移植性判据满分——归一化后双方言逐字相同）。

安全纪律（M0a-2 R2 红线——**标识符路径不变式**，双方言渲染器同等受约束）：

- **绑定参数名由渲染器按 AST 遍历顺序自控生成**（g<seq>_<i>），与库内数据
  （维度 key 等）完全无关；显式命名参数（org / current_model / q / q_vec /
  top_k）为渲染器与构造层的**固定常量**，绝不来自数据；
- `InValue.param_prefix` 仅为 trace 标签：标识符白名单校验（fail-closed——
  构造即拒，`fullmatch` 防尾部换行逃逸）且**绝不进入 SQL 文本**；
- 数据派生文本只有两条出路：授权值/org 经绑定参数；维度 key 经 Literal 转义
  渲染（单引号加倍——任何字符不产生语法作用）；
- **`_Renderer` 单趟渲染状态、绝不跨调用拼接片段**：一次 render_sql 从一棵
  AST 产出完整 (SQL, params)，无中间文本复用/拼接面（防注入的边界即在此）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from knowledge_lattice.store.backend import AclDimensionRule, AclPlan

# 参数名 trace 标签白名单（fail-closed——构造即拒；渲染参数名另由渲染器序列生成）。
# fullmatch（M0a 顺手项④）：match+$ 会接受尾部换行（"abc\n"），fullmatch 关闭该逃逸。
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 表别名约定（双方言渲染一致）
CHUNKS = "c"
DOCS = "d"
CV = "cv"  # chunk_vectors（向量路 JOIN——拍板 2 谓词迁移）

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
    """结构常量（tombstone=0 / 维度 key）——转义渲染，非数据值。"""

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
        if not _IDENTIFIER_RE.fullmatch(self.param_prefix):
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
    查询串经绑定参数；PG FTS 路（to_tsquery/ts_rank 加权）随 M1）。"""

    source: str
    fts_name: str
    param: BindParam


@dataclass(frozen=True)
class Func:
    """函数调用——name 为受限标识符、args 全为节点。"""

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

# ============ 中性构造层（AclPlan → 节点树——visible_docs CTE 唯一路径） ============


def version_eq() -> Eq:
    return Eq(ColumnRef(CHUNKS, "version"), ColumnRef(DOCS, "active_version"))


def tombstone_eq() -> Eq:
    return Eq(ColumnRef(CHUNKS, "tombstone"), Literal(0))


def org_eq(plan: AclPlan) -> Eq:
    return Eq(ColumnRef(DOCS, "org_id"), BindParam("org", plan.org_id))


def filter_nodes(plan: AclPlan) -> tuple[Expr, ...]:
    """dataset/doc 过滤（None=不过滤；空序列=恒假——不产 IN ()）。

    每次调用产出**新节点**（同一 Plan 在 CTE 与外层两处使用时，渲染器为各自
    InValue 生成独立参数名序列——同值不同名，参数表无冲突）。
    """
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


def build_visible_docs_rule_ast(rule: AclDimensionRule, org_id: str) -> Expr:
    """单维 visible_docs 块（基于 document_dimensions）：文档在该维无任何行，
    或有一行取值 ∈ 授权集（§5.1 第 3 步——有值则过滤、空值放行）。

    空授权 → 无任何行才可见（与 NOT EXISTS 单条件同义——不出 IN ()）。
    状态快照口径（M0a-2 P3-1 + M0b-3 ①收口）：**不读 dim.status / v.status**——
    Plan 规则集与授权取值在编译时点已按 active 过滤（read_grants 三重过滤），
    CTE 再读可变状态会在 compile→execute 竞态下（维度退役/取值停用）偏离编译
    快照；停用/退役的收紧与放宽一律经**下次编译**生效（test_v11_schema 竞态
    回归锁定）。
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


def build_visible_docs_cte_where(plan: AclPlan) -> And:
    """visible_docs CTE 的 WHERE（方言无关）：org 限定 + 各维规则块 + **过滤下推**
    （M0a 顺手项⑥——dataset/doc 过滤同时下推进 CTE：CTE 先收窄可见文档集，
    与外层过滤语义等价、性能只会更优；外层保留同条件双保险）。
    """
    blocks = [build_visible_docs_rule_ast(rule, plan.org_id) for rule in plan.dimension_rules]
    return And((org_eq(plan), *blocks, *filter_nodes(plan)))


def visible_docs_insubquery() -> InSubquery:
    """外层可见集引用：c.doc_id IN (SELECT doc_id FROM visible_docs)——结构常量。"""
    return InSubquery(ColumnRef(CHUNKS, "doc_id"), "SELECT doc_id FROM visible_docs")


def build_visible_docs_outer_where(plan: AclPlan) -> And:
    """基础/实体路外层 WHERE：可见集引用 + 外层常量约束（固定节点组——TC-ACL-06）
    + 过滤。"""
    return And((
        visible_docs_insubquery(),
        And((version_eq(), tombstone_eq(), org_eq(plan))),
        *filter_nodes(plan),
    ))


def build_fts_where_ast(plan: AclPlan, *, query: str) -> And:
    """FTS 路外层 WHERE（TC-ACL-06 三路同构）：MATCH + 可见集引用 + 常量 + 过滤；
    版本条件在 chunks/documents JOIN 上（T9——FTS 层无旧版本/tombstone 命中的
    机制前提），不在 WHERE。ACL 维度规则与基础路共用同一 CTE（同一 Plan）。"""
    parts: list[Expr] = [
        Match("f", "chunks_fts", BindParam("q", query)),
        visible_docs_insubquery(),
        And((tombstone_eq(), org_eq(plan))),
    ]
    parts.extend(filter_nodes(plan))
    return And(tuple(parts))


def build_vec_parts(plan: AclPlan) -> tuple[And, Join, And]:
    """向量路三段（TC-EMB-02 谓词迁 chunk_vectors——Plan 层不动、渲染层迁移）：

    - cte_where：与基础路共用同一 CTE（同一 Plan 同一授权展开）；
    - cv_join：`JOIN chunk_vectors cv ON cv.rid = c.rid AND
      cv.embed_model = :current_model`——谓词节点语义保持（Eq + BindParam 固定
      节点、值=Plan.embed_model），仅列引用自 chunks 迁 cv（非当前标签视同未
      嵌入：cv 无行即未嵌入，无 IS NOT NULL 谓词——报告 §3.5）；
    - outer_where：与基础路同一外层 WHERE。
    """
    if plan.embed_model is None:
        raise ValueError(
            "向量路需要 plan.embed_model（model:dim 标签——D12/TC-EMB-02）"
        )
    cv_join = Join(
        TableRef("chunk_vectors", CV),
        And((
            Eq(ColumnRef(CV, "rid"), ColumnRef(CHUNKS, "rid")),
            Eq(ColumnRef(CV, "embed_model"), BindParam("current_model", plan.embed_model)),
        )),
    )
    return build_visible_docs_cte_where(plan), cv_join, build_visible_docs_outer_where(plan)
