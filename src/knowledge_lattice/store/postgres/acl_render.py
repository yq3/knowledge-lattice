"""AclPlan → PostgreSQL SQL：渲染器 + PG 方言构造（D24——M0b-1 PG spike）。

- 消费**同一棵方言无关 AST**（store/acl_ast.py——节点与中性构造双方言共享，
  语义规则只实现一次）；本模块只做 PG 方言差异两件：
  ① 参数语法 `%(name)s`（psycopg pyformat）；② 按块维度扫描
  `jsonb_array_elements_text(jsonb_extract_path(c.dims_json, 'k'))`
  ——json_each → jsonb 等价路径谓词（§4 PG 映射；键缺失/空数组产 0 行，
  空值放行语义与 sqlite 逐字同源；扫描输出列名同为 `value`，je.value IN … 同构）；
- 安全纪律沿用 M0a-2 R2 后口径（渲染器自控参数名序列 g<seq>_<i> +
  InValue.param_prefix 白名单 fail-closed——约束定义在 acl_ast.InValue，双方言
  同受约束；_Renderer 单趟渲染状态、绝不跨调用拼接片段）；
- visible_docs 双写法同构渲染（TC-ACL-07）：CTE 基于 document_dimensions、
  纯 JOIN/EXISTS 无 JSON 方言函数——同一中性构造（acl_ast.build_visible_docs_parts）；
- 本段不含 FTS 路（Match 节点渲染显式拒绝——PG to_tsquery/ts_rank 加权随
  M0b-2/M1，design §8 M0b.5 / §5.2 PG 渲染注）。
"""

from __future__ import annotations

from knowledge_lattice.store.acl_ast import (
    CHUNKS as _CHUNKS,
    And,
    BindParam,
    ColumnRef,
    Eq,
    Exists,
    Expr,
    Func,
    InSubquery,
    InValue,
    Join,
    Literal,
    Match,
    NotExists,
    Or,
    Select1,
    TableRef,
    build_acl_ast as _build_acl_ast_neutral,
    build_dimension_rule_ast as _build_dimension_rule_neutral,
    build_visible_docs_parts,
    build_where_ast as _build_where_ast_neutral,
)
from knowledge_lattice.store.backend import AclDimensionRule, AclPlan

__all__ = [
    "render_sql", "render_select", "render_visible_docs_select",
    "build_dimension_rule_ast", "build_acl_ast", "build_where_ast",
]


# ============ 渲染器（AST → SQL 文本 + 参数表；数据值绝不进 SQL 文本） ============


class _Renderer:
    """单趟渲染状态：参数表 + InValue 序列计数（PG 参数语法 `%(name)s`）。

    绑定参数名由渲染器按 AST 遍历顺序自控生成（g<seq>_<i>）——与库内数据
    （维度 key 等）完全无关；显式命名的参数（org / current_model）为固定常量。
    同名参数（如 CTE 与外层共用 org）单值复用——psycopg pyformat 天然支持。
    """

    def __init__(self) -> None:
        self.params: dict[str, object] = {}
        self._invalue_seq = 0

    def expr(self, node: Expr) -> str:
        if isinstance(node, ColumnRef):
            return f"{node.table}.{node.name}" if node.table else node.name
        if isinstance(node, BindParam):
            self.params[node.name] = node.value
            return f"%({node.name})s"
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
                name = f"g{self._invalue_seq}_{i}"  # 渲染器自控序列名（P1-1 同款纪律）
                self.params[name] = value
                names.append(f"%({name})s")
            self._invalue_seq += 1
            return f"{self.expr(node.expr)} IN ({', '.join(names)})"
        if isinstance(node, InSubquery):
            return f"{self.expr(node.expr)} IN ({node.subquery})"
        if isinstance(node, Match):
            raise NotImplementedError(
                "PG FTS 路（to_tsquery 转义 + 加权 ts_rank 求和）随 M0b-2/M1——"
                "本段仅可见性产物与向量列断言（design §5.2 PG 渲染注 / §8 M0b.5）"
            )
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


# InValue/TableRef/Join/Select1/Exists/NotExists/InSubquery 为渲染器 isinstance
# 分派所需节点（顶部统一导入）


def render_sql(root: Expr) -> tuple[str, dict[str, object]]:
    """AST → (SQL 片段, 参数表)——确定性渲染（同 AST 同文本，逐字 diff 稳定）。"""
    renderer = _Renderer()
    return renderer.expr(root), renderer.params


# ============ AST builder（AclPlan → 节点树；PG 方言注入 jsonb 扫描） ============


def _dims_scan(dim_key: str) -> Func:
    """jsonb 等价路径谓词（§4 PG 映射：json_each(c.dims_json, '$.k') 的等价物）——
    键缺失/空数组 → 0 行（空值放行），数组元素以 text 展开为输出列 `value`。"""
    return Func(
        "jsonb_array_elements_text",
        (Func("jsonb_extract_path", (ColumnRef(_CHUNKS, "dims_json"), Literal(dim_key))),),
    )


def build_dimension_rule_ast(rule: AclDimensionRule) -> Expr:
    """单维统一模板（§5.1 第 3 步）——语义见 acl_ast（同一实现，方言仅扫描节点不同）。"""
    return _build_dimension_rule_neutral(rule, dims_scan=_dims_scan)


def build_acl_ast(plan: AclPlan) -> Expr | None:
    """维度规则合取——三路共享的 ACL 片段（TC-ACL-06）。"""
    return _build_acl_ast_neutral(plan, dims_scan=_dims_scan)


def build_where_ast(plan: AclPlan, *, vector: bool = False) -> And:
    """完整 WHERE（基础/向量/实体路）——TC-ACL-06 / TC-EMB-02（语义见 acl_ast）。"""
    return _build_where_ast_neutral(plan, dims_scan=_dims_scan, vector=vector)


# ============ 完整召回 SQL（双写法——TC-ACL-07） ============


def render_select(plan: AclPlan) -> tuple[str, dict[str, object]]:
    """按块 jsonb 模板的基础路召回 SQL（可见性产物——对齐 M0a-2 形态，可在 PG
    真实执行；实体路同形）。"""
    where_sql, params = render_sql(build_where_ast(plan))
    sql = (
        "SELECT c.rid, c.id, c.doc_id"
        " FROM chunks c JOIN documents d ON d.id = c.doc_id"
        f" WHERE {where_sql}"
    )
    return sql, params


def render_vec_recall_select(
    plan: AclPlan, query_vec: str, *, top_k: int
) -> tuple[str, dict[str, object]]:
    """向量路召回 SQL（`<=>` 精确扫描——G-6 起步口径；先过滤后距离，§5.2）。

    本段供向量列距离断言与 M0b-2 实验起步；完整检索管线（降级/名次吸收）随 M1。
    query_vec 为 pgvector 文本形态（vec.format_vector 产物），经绑定参数 + ::vector
    显式转型，绝不拼接进 SQL 文本。
    """
    where_sql, params = render_sql(build_where_ast(plan, vector=True))
    params["q_vec"] = query_vec
    params["top_k"] = top_k
    sql = (
        "SELECT c.rid, c.id, c.doc_id, c.embedding <=> %(q_vec)s::vector AS dist"
        " FROM chunks c JOIN documents d ON d.id = c.doc_id"
        f" WHERE {where_sql} AND c.embedding IS NOT NULL"
        " ORDER BY dist LIMIT %(top_k)s"
    )
    return sql, params


def render_visible_docs_select(plan: AclPlan) -> tuple[str, dict[str, object]]:
    """按文档 visible_docs CTE 备选写法（§5.1 性能注——双写法之二）——同一
    AclPlan/授权展开、同一中性构造（纯 JOIN/EXISTS 无 JSON 方言函数），结果集
    与 render_select 逐字等价（TC-ACL-07；M0b 实验选定后二删其一）。"""
    renderer = _Renderer()  # CTE 与外层同一渲染状态（参数名序列连续、org 复用同名同值）
    cte_where, outer = build_visible_docs_parts(plan)
    sql = (
        "WITH visible_docs(doc_id) AS ("
        "SELECT d.id FROM documents d"
        f" WHERE {renderer.expr(cte_where)})"
        " SELECT c.rid, c.id, c.doc_id"
        " FROM chunks c JOIN documents d ON d.id = c.doc_id"
        f" WHERE {renderer.expr(outer)}"
    )
    return sql, renderer.params
