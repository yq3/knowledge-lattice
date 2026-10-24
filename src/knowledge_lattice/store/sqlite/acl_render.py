"""AclPlan → SQLite SQL：渲染器 + sqlite 方言构造（D24——渲染收口 store/sqlite/ 侧）。

- 节点类型与中性构造层上提至 `store/acl_ast.py`（M0b-1——双方言共享**同一棵
  方言无关 AST**，本模块 re-export 保持既有导入路径不变）；本模块保留 sqlite
  方言差异两件：参数语法 `:name` 的 `_Renderer` 与按块扫描
  `json_each(c.dims_json, '$.k')`（dims_scan 注入）；
- 产物一律由 AST 节点树渲染，**禁止字符串拼接**：授权取值 / org / dataset / doc /
  模型标签全部经绑定参数；JSON path（'$.<key>'）与维度 key 为结构常量（转义渲染）；
- **绑定参数名由渲染器按 AST 遍历顺序自控生成（g<seq>_<i>），与库内数据（维度
  key 等）完全无关**（Committer R1 P1-1：由 key 拼接参数名时，含 SQL 记号的 key
  会截断参数名、残余字符落入 SQL 文本——可注释掉外层常量造成跨组织/跨版本泄露）；
  `InValue.param_prefix` 仅为 trace 标签（标识符白名单校验、绝不进入 SQL）；
- 「无 IN ()」为 Plan 层不变式（acl_ast.InValue 构造约束）：空授权集维度只产
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

from knowledge_lattice.store.acl_ast import (  # noqa: F401  (re-export——既有导入路径不变)
    CHUNKS as _CHUNKS,
    DOCS as _DOCS,
    JE as _JE,
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
    build_visible_docs_parts,
    build_where_ast as _build_where_ast_neutral,
    filter_nodes as _filter_nodes_neutral,
    org_eq as _org_eq,
    tombstone_eq as _tombstone_eq,
    version_eq as _version_eq,
)
from knowledge_lattice.store.backend import AclDimensionRule, AclPlan
from knowledge_lattice.store.sqlite.fts import BM25_WEIGHTS

__all__ = [
    "And", "BindParam", "ColumnRef", "Eq", "Exists", "Expr", "Func", "InSubquery",
    "InValue", "Join", "Literal", "Match", "NotExists", "Or", "Select1", "TableRef",
    "build_dimension_rule_ast", "build_acl_ast", "build_where_ast",
    "build_fts_where_ast", "render_sql", "render_select", "render_fts_select",
    "render_fts_recall_select", "render_visible_docs_select",
]


# ============ 渲染器（AST → SQL 文本 + 参数表；数据值绝不进 SQL 文本） ============


class _Renderer:
    """单趟渲染状态：参数表 + InValue 序列计数（sqlite 参数语法 `:name`）。

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


# ============ AST builder（AclPlan → 节点树；sqlite 方言注入 json_each 扫描） ============


def _dims_scan(dim_key: str) -> Func:
    """json_each(c.dims_json, '$.<key>')——按块模板的表值扫描（SQLite 方言节点）。"""
    return Func("json_each", (ColumnRef(_CHUNKS, "dims_json"), Literal(f"$.{dim_key}")))


def build_dimension_rule_ast(rule: AclDimensionRule) -> Expr:
    """单维统一模板（§5.1 第 3 步）：有值则过滤、空值放行（语义见 acl_ast）。"""
    from knowledge_lattice.store.acl_ast import build_dimension_rule_ast as _build

    return _build(rule, dims_scan=_dims_scan)


def build_acl_ast(plan: AclPlan) -> Expr | None:
    """维度规则合取——FTS/向量/实体三路共享的 ACL 片段（TC-ACL-06）。"""
    return _build_acl_ast_neutral(plan, dims_scan=_dims_scan)


def build_where_ast(plan: AclPlan, *, vector: bool = False) -> And:
    """完整 WHERE（基础/向量/实体路）——TC-ACL-06 / TC-EMB-02（语义见 acl_ast）。"""
    return _build_where_ast_neutral(plan, dims_scan=_dims_scan, vector=vector)


def build_fts_where_ast(plan: AclPlan, *, query: str) -> And:
    """FTS 路 WHERE：`chunks_fts MATCH` + 同一 ACL 片段 + 常量（版本条件移至
    JOIN——render_fts_select；T9）。"""
    parts: list[Expr] = [Match("f", "chunks_fts", BindParam("q", query))]
    acl = build_acl_ast(plan)
    if acl is not None:
        parts.append(acl)
    parts.append(And((_tombstone_eq(), _org_eq(plan))))
    parts.extend(_filter_nodes_neutral(plan))
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


def render_visible_docs_select(plan: AclPlan) -> tuple[str, dict[str, object]]:
    """按文档 visible_docs CTE 备选写法（§5.1 性能注）——同一 AclPlan/授权展开，
    先求可见文档集合再 `c.doc_id IN (visible_docs)`（走 uq_chunks_docver）；
    结果集与 render_select 逐字等价（TC-ACL-07；M0b 实验选定后二删其一）。"""
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
