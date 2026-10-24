"""AclPlan → PostgreSQL SQL：渲染器 + PG 方言构造（D24——M0b-1 PG spike；M0b-3 拍板 1 收敛）。

- 消费**同一棵方言无关 AST**（store/acl_ast.py——节点与中性构造双方言共享，
  语义规则只实现一次）；本模块只做 PG 方言差异一件：参数语法 `%(name)s`
  （psycopg pyformat）；
- **visible_docs CTE 唯一路径**：`AS MATERIALIZED` 钉住一次物化（PG 计划器会把
  内联 CTE 的文档级可见性谓词按块重复求值——报告 §2.3 EXPLAIN ANALYZE loops
  实测 inline=块数 / MATERIALIZED=文档数；jsonb 按块模板已随拍板 1 删除）；
- 安全纪律沿用 M0a-2 R2 后口径（渲染器自控参数名序列 g<seq>_<i> +
  InValue.param_prefix 白名单 fail-closed——约束定义在 acl_ast.InValue，双方言
  同受约束；_Renderer 单趟渲染状态、绝不跨调用拼接片段）；
- 向量路（render_vec_recall_select）：可见集 CTE + `JOIN chunk_vectors cv ON
  cv.rid = c.rid AND cv.embed_model = %(current_model)s`（TC-EMB-02 谓词迁分表
  ——Plan 层不动、渲染层迁移；`<=>` 精确扫描起步，G-6）；
- 本段不含 FTS 路（Match 节点渲染显式拒绝——PG to_tsquery/ts_rank 加权随
  M1，design §5.2 PG 渲染注）。
"""

from __future__ import annotations

from knowledge_lattice.store.acl_ast import (
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
    build_vec_parts as _build_vec_parts_neutral,
    build_visible_docs_cte_where as _build_cte_where_neutral,
    build_visible_docs_outer_where as _build_outer_where_neutral,
)
from knowledge_lattice.store.backend import AclPlan

__all__ = [
    "render_sql", "render_select", "render_vec_recall_select",
    "build_acl_ast", "build_where_ast",
]

# CTE 前缀（MATERIALIZED——PG 计划病理一词修复；与 sqlite 渲染统一加注）
_CTE_PREFIX = "WITH visible_docs(doc_id) AS MATERIALIZED (SELECT d.id FROM documents d WHERE "


# ============ 渲染器（AST → SQL 文本 + 参数表；数据值绝不进 SQL 文本） ============


class _Renderer:
    """单趟渲染状态：参数表 + InValue 序列计数（PG 参数语法 `%(name)s`）。

    绑定参数名由渲染器按 AST 遍历顺序自控生成（g<seq>_<i>）——与库内数据
    （维度 key 等）完全无关；显式命名的参数（org / current_model）为固定常量。
    同名参数（如 CTE 与外层共用 org）单值复用——psycopg pyformat 天然支持。
    单趟纪律：一个 _Renderer 实例只在一次渲染内存活，**绝不跨调用拼接片段**。
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
                "PG FTS 路（to_tsquery 转义 + 加权 ts_rank 求和）随 M1——"
                "本段仅可见性产物与向量列断言（design §5.2 PG 渲染注）"
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


def render_sql(root: Expr) -> tuple[str, dict[str, object]]:
    """AST → (SQL 片段, 参数表)——确定性渲染（同 AST 同文本，逐字 diff 稳定）。"""
    renderer = _Renderer()
    return renderer.expr(root), renderer.params


# ============ 完整召回 SQL（visible_docs + MATERIALIZED 唯一路径） ============


def build_acl_ast(plan: AclPlan):
    """维度规则块序列（方言无关构造的 re-export 面——结构与 acl_ast 一致）。"""
    from knowledge_lattice.store.acl_ast import build_visible_docs_rule_ast

    return tuple(build_visible_docs_rule_ast(rule, plan.org_id) for rule in plan.dimension_rules)


def build_where_ast(plan: AclPlan):
    """基础路外层 WHERE（方言无关构造 re-export——语义见 acl_ast）。"""
    return _build_outer_where_neutral(plan)


def render_select(plan: AclPlan) -> tuple[str, dict[str, object]]:
    """基础路召回 SQL（可见性产物——实体路同形）：visible_docs CTE（MATERIALIZED）
    + 外层常量/过滤。"""
    renderer = _Renderer()  # CTE 与外层同一渲染状态（参数名序列连续、org 复用同名同值）
    sql = (
        f"{_CTE_PREFIX}{renderer.expr(_build_cte_where_neutral(plan))})"
        " SELECT c.rid, c.id, c.doc_id"
        " FROM chunks c JOIN documents d ON d.id = c.doc_id"
        f" WHERE {renderer.expr(_build_outer_where_neutral(plan))}"
    )
    return sql, renderer.params


def render_vec_recall_select(
    plan: AclPlan, query_vec: str, *, top_k: int
) -> tuple[str, dict[str, object]]:
    """向量路召回 SQL（`<=>` 精确扫描——G-6 起步口径；先过滤后距离，§5.2）。

    M0b-3 拍板 2：谓词迁 `chunk_vectors`——`JOIN cv ON cv.rid = c.rid AND
    cv.embed_model = %(current_model)s`（TC-EMB-02 节点语义保持）；cv 无行即未
    嵌入（无 IS NOT NULL 谓词）；距离列 `cv.embedding <=> %(q_vec)s::vector`。
    query_vec 为 pgvector 文本形态（vec.format_vector 产物），经绑定参数 +
    ::vector 显式转型，绝不拼接进 SQL 文本。
    """
    cte_where, cv_join, outer = _build_vec_parts_neutral(plan)
    renderer = _Renderer()
    sql = (
        f"{_CTE_PREFIX}{renderer.expr(cte_where)})"
        " SELECT c.rid, c.id, c.doc_id, cv.embedding <=> %(q_vec)s::vector AS dist"
        " FROM chunks c JOIN documents d ON d.id = c.doc_id"
        f"{renderer.expr(cv_join)}"
        f" WHERE {renderer.expr(outer)}"
        " ORDER BY dist LIMIT %(top_k)s"
    )
    renderer.params["q_vec"] = query_vec
    renderer.params["top_k"] = top_k
    return sql, renderer.params
