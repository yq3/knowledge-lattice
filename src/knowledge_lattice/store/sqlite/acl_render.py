"""AclPlan → SQLite SQL：AST builder + 渲染器（D24——渲染收口 store/sqlite/ 侧）。

- 产物一律由 AST 节点树渲染，**禁止字符串拼接**：授权取值 / org / dataset / doc /
  模型标签全部经绑定参数；JSON path（'$.<key>'）与维度 key 为结构常量（转义渲染）；
- **绑定参数名由渲染器按 AST 遍历顺序自控生成（g<seq>_<i>），与库内数据（维度
  key 等）完全无关**（Committer R1 P1-1：由 key 拼接参数名时，含 SQL 记号的 key
  会截断参数名、残余字符落入 SQL 文本——可注释掉外层常量造成跨组织/跨版本泄露）；
  `InValue.param_prefix` 仅为 trace 标签（标识符白名单校验、绝不进入 SQL）；
- 「无 IN ()」为 Plan 层不变式：InValue 节点构造即拒绝空值集——空授权集维度只产
  NotExists 单条件（§5.1 第 3 步 / T22）；
- 双写法（§5.1 性能注 / TC-ACL-07）：按块 json_each 模板（render_select /
  render_fts_select——dims_json 冗余投影）与按文档 visible_docs CTE
  （render_visible_docs_select——document_dimensions），同一 AclPlan、同一授权
  展开，结果集逐字等价；M0b 实验选定后删其一；
- 三路同构（TC-ACL-06）：FTS / 向量 / 实体路共用同一 Plan 与同一 ACL 片段；
  向量路仅追加 embed_model 谓词（vector=True——TC-EMB-02）；FTS 路版本条件在
  chunks/documents JOIN 上（T9——FTS 层无旧版本/tombstone 命中的机制前提）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from knowledge_lattice.store.backend import AclDimensionRule, AclPlan
from knowledge_lattice.store.sqlite.fts import BM25_WEIGHTS

# 参数名 trace 标签白名单（fail-closed——构造即拒；渲染参数名另由渲染器序列生成）
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

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
    Committer R1 P1-1 防御纵深），**绝不进入 SQL 文本**——渲染参数名由渲染器
    按遍历顺序自控生成（g<seq>_<i>），与库内数据（维度 key 等）无关。
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
    """FTS5 全文匹配谓词：`<别名>.<虚表名> MATCH :<param>`（查询串经绑定参数——
    token 转义属 store/sqlite/fts.py，M0a-3）。"""

    source: str
    fts_name: str
    param: BindParam


@dataclass(frozen=True)
class Func:
    """函数调用（含表值函数 json_each）——name 为受限标识符、args 全为节点。"""

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

# ============ 渲染器（AST → SQL 文本 + 参数表；数据值绝不进 SQL 文本） ============


class _Renderer:
    """单趟渲染状态：参数表 + InValue 序列计数。

    绑定参数名由渲染器按 AST 遍历顺序自控生成（g<seq>_<i>）——与库内数据
    （维度 key 等）完全无关（P1-1：参数名不得由数据拼接，防 SQL 文本注入）；
    显式命名的参数（org / current_model / q）为渲染器与 builder 的固定常量。
    """

    def __init__(self) -> None:
        self.params: dict[str, object] = {}
        self._invalue_seq = 0

    def expr(self, node: Expr) -> str:
        if isinstance(node, ColumnRef):
            return f"{node.table}.{node.name}" if node.table else node.name
        if isinstance(node, BindParam):
            self.params[node.name] = node.value
            return f":{node.name}"
        if isinstance(node, Literal):
            if isinstance(node.value, str):
                return "'" + node.value.replace("'", "''") + "'"
            return str(node.value)
        if isinstance(node, Eq):
            return f"{self.expr(node.left)} = {self.expr(node.right)}"
        if isinstance(node, And):
            return " AND ".join(self.child(part) for part in node.parts)
        if isinstance(node, Or):
            return " OR ".join(self.child(part) for part in node.parts)
        if isinstance(node, InValue):
            names = []
            for i, value in enumerate(node.values):
                name = f"g{self._invalue_seq}_{i}"  # 渲染器自控序列名（P1-1）
                self.params[name] = value
                names.append(f":{name}")
            self._invalue_seq += 1
            return f"{self.expr(node.expr)} IN ({', '.join(names)})"
        if isinstance(node, InSubquery):
            return f"{self.expr(node.expr)} IN ({node.subquery})"
        if isinstance(node, Match):
            self.params[node.param.name] = node.param.value
            return f"{node.source}.{node.fts_name} MATCH :{node.param.name}"
        if isinstance(node, Func):
            args = ", ".join(self.expr(a) for a in node.args)
            return f"{node.name}({args})"
        if isinstance(node, TableRef):
            return f"{node.name} AS {node.alias}" if node.alias else node.name
        if isinstance(node, Join):
            return f" JOIN {self.expr(node.table)} ON {self.expr(node.on)}"
        if isinstance(node, Select1):
            sql = f"SELECT 1 FROM {self.expr(node.from_table)}"
            if node.alias:
                sql += f" AS {node.alias}"
            for join in node.joins:
                sql += self.expr(join)
            if node.predicate is not None:
                sql += f" WHERE {self.expr(node.predicate)}"
            return sql
        if isinstance(node, Exists):
            return f"EXISTS ({self.expr(node.subquery)})"
        if isinstance(node, NotExists):
            return f"NOT EXISTS ({self.expr(node.subquery)})"
        raise TypeError(f"unknown AST node: {type(node).__name__}")

    def child(self, node: Expr) -> str:
        """And/Or 的子节点：复合项显式括号（无优先级歧义——TC-ACL-01）。"""
        rendered = self.expr(node)
        if isinstance(node, (And, Or)):
            return f"({rendered})"
        return rendered


def render_sql(root: Expr) -> tuple[str, dict[str, object]]:
    """AST → (SQL 片段, 参数表)——确定性渲染（同 AST 同文本，逐字 diff 稳定）。"""
    renderer = _Renderer()
    return renderer.expr(root), renderer.params


# ============ AST builder（AclPlan → 节点树） ============

_CHUNKS = "c"
_DOCS = "d"
_JE = "je"


def _dims_scan(dim_key: str) -> Func:
    """json_each(c.dims_json, '$.<key>')——按块模板的表值扫描（SQLite 方言节点）。"""
    return Func("json_each", (ColumnRef(_CHUNKS, "dims_json"), Literal(f"$.{dim_key}")))


def build_dimension_rule_ast(rule: AclDimensionRule) -> Expr:
    """单维统一模板（§5.1 第 3 步）：有值则过滤、空值放行。

    有授权 → Or[NotExists(空值放行), Exists[je.value IN (授权集)]]；
    空授权 → NotExists 单条件（该维只见空值文档——T22；禁止 IN ()）。
    required/enabled 不参与（生命周期与过滤解耦——T4/T20）。
    """
    null_pass = NotExists(Select1(from_table=_dims_scan(rule.key)))
    if rule.is_empty:
        return null_pass
    hit = Exists(
        Select1(
            from_table=_dims_scan(rule.key),
            alias=_JE,
            # param_prefix 为静态 trace 标签（P1-1：渲染参数名由渲染器序列生成）
            predicate=InValue(ColumnRef(_JE, "value"), "dim", rule.grants),
        )
    )
    return Or((null_pass, hit))


def build_acl_ast(plan: AclPlan) -> Expr | None:
    """维度规则合取——FTS/向量/实体三路共享的 ACL 片段（TC-ACL-06）。

    无 active 维度（或全部 retired——唯一放宽路径不生成条件，T20④）→ None。
    """
    if not plan.dimension_rules:
        return None
    blocks = [build_dimension_rule_ast(rule) for rule in plan.dimension_rules]
    if len(blocks) == 1:
        return blocks[0]
    return And(tuple(blocks))


def _version_eq() -> Eq:
    return Eq(ColumnRef(_CHUNKS, "version"), ColumnRef(_DOCS, "active_version"))


def _tombstone_eq() -> Eq:
    return Eq(ColumnRef(_CHUNKS, "tombstone"), Literal(0))


def _org_eq(plan: AclPlan) -> Eq:
    return Eq(ColumnRef(_DOCS, "org_id"), BindParam("org", plan.org_id))


def _filter_nodes(plan: AclPlan) -> tuple[Expr, ...]:
    """dataset/doc 过滤（None=不过滤；空序列=恒假——不产 IN ()）。"""
    nodes: list[Expr] = []
    for column, prefix, ids in (
        ("dataset_id", "ds", plan.dataset_ids),
        ("id", "doc", plan.doc_ids),
    ):
        if ids is None:
            continue
        if ids:
            nodes.append(InValue(ColumnRef(_DOCS, column), prefix, tuple(ids)))
        else:
            nodes.append(Eq(Literal(1), Literal(0)))
    return tuple(nodes)


def build_where_ast(plan: AclPlan, *, vector: bool = False) -> And:
    """完整 WHERE（基础/向量/实体路）：维度 ACL + 外层常量约束（固定节点——
    TC-ACL-06）+ dataset/doc 过滤；vector=True 追加 embed_model 谓词
    （TC-EMB-02——三路共用同一 Plan，谓词仅向量路渲染）。"""
    parts: list[Expr] = []
    acl = build_acl_ast(plan)
    if acl is not None:
        parts.append(acl)
    parts.append(And((_version_eq(), _tombstone_eq(), _org_eq(plan))))
    parts.extend(_filter_nodes(plan))
    if vector:
        if plan.embed_model is None:
            raise ValueError(
                "vector=True 需要 plan.embed_model（model:dim 标签——D12/TC-EMB-02）"
            )
        parts.append(
            Eq(ColumnRef(_CHUNKS, "embed_model"), BindParam("current_model", plan.embed_model))
        )
    return And(tuple(parts))


def build_fts_where_ast(plan: AclPlan, *, query: str) -> And:
    """FTS 路 WHERE：`chunks_fts MATCH` + 同一 ACL 片段 + 常量（版本条件移至
    JOIN——render_fts_select；T9）。"""
    parts: list[Expr] = [Match("f", "chunks_fts", BindParam("q", query))]
    acl = build_acl_ast(plan)
    if acl is not None:
        parts.append(acl)
    parts.append(And((_tombstone_eq(), _org_eq(plan))))
    parts.extend(_filter_nodes(plan))
    return And(tuple(parts))


# ============ 完整召回 SQL（双写法——TC-ACL-07） ============


def render_select(plan: AclPlan) -> tuple[str, dict[str, object]]:
    """按块 json_each 模板的基础路召回 SQL（§5.1 编译产物示意——实体路同形）。"""
    where_sql, params = render_sql(build_where_ast(plan))
    sql = (
        "SELECT c.rid, c.id, c.doc_id"
        " FROM chunks c JOIN documents d ON d.id = c.doc_id"
        f" WHERE {where_sql}"
    )
    return sql, params


def render_fts_select(plan: AclPlan, *, query: str) -> tuple[str, dict[str, object]]:
    """FTS 路召回 SQL：chunks_fts MATCH + 同一 ACL 片段 + 版本条件在 JOIN 上（T9）。"""
    where_sql, params = render_sql(build_fts_where_ast(plan, query=query))
    sql = (
        "SELECT c.rid, c.id, c.doc_id"
        " FROM chunks_fts f"
        " JOIN chunks c ON c.rid = f.rowid"
        " JOIN documents d ON d.id = c.doc_id AND c.version = d.active_version"
        f" WHERE {where_sql}"
    )
    return sql, params


def render_fts_recall_select(
    plan: AclPlan, match_expr: str, *, top_k: int
) -> tuple[str, dict[str, object]]:
    """M0a-3 BM25 召回（检索链实装形态，TC-FTS-02/TC-E2E-01）：

    - 溯源列一次取齐（chunk_id/doc_id/title/page_no/dims/source/dataset/sheet/content/snippet 原文）；
    - 五列加权 `bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)`（结构常量，参数同列序）——
      越小越相关，ORDER BY ASC；LIMIT :top_k 经绑定参数；
    - match_expr 为 fts.build_match_expr 产物（token 转义后的字面量 OR 串），经 :q 绑定；
      WHERE 与 render_fts_select 同一 builder（build_fts_where_ast——三路同构 TC-ACL-06）。
    """
    where_sql, params = render_sql(build_fts_where_ast(plan, query=match_expr))
    params["top_k"] = top_k
    sql = (
        "SELECT c.id AS chunk_id, c.doc_id, d.title, c.page_no, c.sheet_name, c.dims_json,"
        " d.source_uri, d.dataset_id, ds.name AS dataset_name, c.content,"
        f" bm25(chunks_fts, {BM25_WEIGHTS}) AS score_raw"
        " FROM chunks_fts f"
        " JOIN chunks c ON c.rid = f.rowid"
        " JOIN documents d ON d.id = c.doc_id AND c.version = d.active_version"
        " JOIN datasets ds ON ds.id = d.dataset_id"
        f" WHERE {where_sql}"
        " ORDER BY score_raw ASC"
        " LIMIT :top_k"
    )
    return sql, params


def _visible_docs_rule_ast(rule: AclDimensionRule, org_id: str) -> Expr:
    """单维 visible_docs 等价块（基于 document_dimensions）：文档在该维无任何行，
    或有一行取值 ∈ 授权集——与按块 json_each 模板逐字等价（TC-ACL-07）。

    空授权 → 无任何行才可见（与 NOT EXISTS 单条件同义——不出 IN ()）。
    只按 dim.key/org_id 匹配、**不读 dim.status**（Committer R1 P3-1）：Plan 规则集
    编译时点已只含 active 维度，CTE 再读可变状态会在 compile→execute 竞态下
    （维度被退役）与 json_each 路（按 Plan 授权集过滤）不等价。
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


def render_visible_docs_select(plan: AclPlan) -> tuple[str, dict[str, object]]:
    """按文档 visible_docs CTE 备选写法（§5.1 性能注）——同一 AclPlan/授权展开，
    先求可见文档集合再 `c.doc_id IN (visible_docs)`（走 uq_chunks_docver）；
    结果集与 render_select 逐字等价（TC-ACL-07；M0b 实验选定后二删其一）。"""
    renderer = _Renderer()  # CTE 与外层同一渲染状态（参数名序列连续、org 复用同名同值）
    blocks = [_visible_docs_rule_ast(rule, plan.org_id) for rule in plan.dimension_rules]
    cte_where = renderer.expr(
        And((Eq(ColumnRef("d", "org_id"), BindParam("org", plan.org_id)), *blocks))
    )
    outer = And((
        InSubquery(ColumnRef("c", "doc_id"), "SELECT doc_id FROM visible_docs"),
        _version_eq(),
        _tombstone_eq(),
        Eq(ColumnRef("d", "org_id"), BindParam("org", plan.org_id)),
        *_filter_nodes(plan),
    ))
    sql = (
        "WITH visible_docs(doc_id) AS ("
        "SELECT d.id FROM documents d"
        f" WHERE {cte_where})"
        " SELECT c.rid, c.id, c.doc_id"
        " FROM chunks c JOIN documents d ON d.id = c.doc_id"
        f" WHERE {renderer.expr(outer)}"
    )
    return sql, renderer.params
