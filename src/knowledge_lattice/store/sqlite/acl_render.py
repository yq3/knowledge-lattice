"""AclPlan → SQLite SQL：渲染器 + 基础/FTS/召回路构造（D24——渲染收口 store/sqlite/ 侧）。

- 节点类型与中性构造层在 `store/acl_ast.py`（双方言共享**同一棵方言无关 AST**，
  本模块 re-export 保持既有导入路径不变）；本模块保留 sqlite 方言差异一件：
  参数语法 `:name` 的 `_Renderer`；
- **visible_docs CTE 唯一路径（M0b-3 拍板 1）**：json_each 按块模板（dims_json
  冗余投影）已删——基础路（render_select）/FTS 路（render_fts_select /
  render_fts_recall_select）统一 `WITH visible_docs(doc_id) AS MATERIALIZED (…)`
  前置 + `c.doc_id IN (visible_docs)`；`AS MATERIALIZED` sqlite ≥3.35 同语法
  可用（本就默认物化、关键字为 no-op——双方言统一加注，报告 §2.3）；
- 产物一律由 AST 节点树渲染，**禁止字符串拼接**：授权取值 / org / 模型标签 /
  查询串全部经绑定参数；维度 key 为结构常量（转义渲染）；
- 绑定参数名由渲染器按 AST 遍历顺序自控生成（g<seq>_<i>），与库内数据完全
  无关（M0a-2 R2 P1-1 红线）；`InValue.param_prefix` 仅为 trace 标签（白名单
  fail-closed、绝不进入 SQL）；`_Renderer` 单趟渲染状态、**不跨调用拼接片段**；
- 「无 IN ()」为 Plan 层不变式（acl_ast.InValue 构造约束）：空授权集维度只产
  NotExists 单条件（§5.1 第 3 步 / T22）；
- 三路同构（TC-ACL-06）：FTS / 向量 / 实体路共用同一 Plan 与同一 visible_docs
  CTE；向量路仅追加 chunk_vectors JOIN 谓词（TC-EMB-02——谓词迁 cv，sqlite 向量
  召回渲染随 M1）；FTS 路版本条件在 chunks/documents JOIN 上（T9）。
"""

from __future__ import annotations

from knowledge_lattice.store.acl_ast import (  # noqa: F401  (re-export——既有导入路径不变)
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
    build_fts_where_ast as _build_fts_where_neutral,
    build_vec_parts as _build_vec_parts_neutral,
    build_visible_docs_cte_where as _build_cte_where_neutral,
    build_visible_docs_outer_where as _build_outer_where_neutral,
)
from knowledge_lattice.store.backend import AclPlan
from knowledge_lattice.store.sqlite.fts import BM25_WEIGHTS

__all__ = [
    "And", "BindParam", "ColumnRef", "Eq", "Exists", "Expr", "Func", "InSubquery",
    "InValue", "Join", "Literal", "Match", "NotExists", "Or", "Select1", "TableRef",
    "build_acl_ast", "build_where_ast", "build_fts_where_ast",
    "render_sql", "render_select", "render_fts_select",
    "render_fts_recall_select", "render_vec_recall_select",
]

# CTE 前缀（结构常量——MATERIALIZED 双方言统一；sqlite ≥3.35 同语法，默认物化）
_CTE_PREFIX = "WITH visible_docs(doc_id) AS MATERIALIZED (SELECT d.id FROM documents d WHERE "


# ============ 渲染器（AST → SQL 文本 + 参数表；数据值绝不进 SQL 文本） ============


class _Renderer:
    """单趟渲染状态：参数表 + InValue 序列计数（sqlite 参数语法 `:name`）。

    绑定参数名由渲染器按 AST 遍历顺序自控生成（g<seq>_<i>）——与库内数据
    （维度 key 等）完全无关（P1-1：参数名不得由数据拼接，防 SQL 文本注入）；
    显式命名的参数（org / current_model / q）为渲染器与 builder 的固定常量。
    单趟纪律：一个 _Renderer 实例只在一次渲染内存活（CTE 与外层共用同一渲染
    状态），**绝不跨调用拼接片段**——无中间 SQL 文本复用面。
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


# ============ 完整召回 SQL（visible_docs CTE 唯一路径——M0b-3 拍板 1） ============


def build_acl_ast(plan: AclPlan):
    """维度规则块序列（方言无关构造的 re-export 面——结构与 acl_ast 一致）。"""
    from knowledge_lattice.store.acl_ast import build_visible_docs_rule_ast

    return tuple(build_visible_docs_rule_ast(rule, plan.org_id) for rule in plan.dimension_rules)


def build_where_ast(plan: AclPlan):
    """基础路外层 WHERE（方言无关构造 re-export——语义见 acl_ast）。"""
    return _build_outer_where_neutral(plan)


def build_fts_where_ast(plan: AclPlan, *, query: str):
    """FTS 路 WHERE：`chunks_fts MATCH` + 可见集引用 + 常量 + 过滤（版本条件在
    JOIN 上——T9）；与基础路共用同一 CTE 构造（TC-ACL-06）。"""
    return _build_fts_where_neutral(plan, query=query)


def render_select(plan: AclPlan) -> tuple[str, dict[str, object]]:
    """基础路召回 SQL（实体路同形）——visible_docs CTE + 外层常量/过滤
    （§5.1 编译产物示意；M0b-2 实验选定唯一路径，json_each 模板已删）。"""
    renderer = _Renderer()  # CTE 与外层同一渲染状态（参数名序列连续、org 复用同名同值）
    sql = (
        f"{_CTE_PREFIX}{renderer.expr(_build_cte_where_neutral(plan))})"
        " SELECT c.rid, c.id, c.doc_id"
        " FROM chunks c JOIN documents d ON d.id = c.doc_id"
        f" WHERE {renderer.expr(_build_outer_where_neutral(plan))}"
    )
    return sql, renderer.params


def render_visible_doc_ids(plan: AclPlan) -> tuple[str, dict[str, object]]:
    """文档级可见集 SQL（M1-2 fetch 替代提示的文档可见性判定）：同一 CTE 主体、
    SELECT doc_id FROM visible_docs——与三路召回共用同一 visible_docs 构造
    （TC-ACL-06 同构口径的文档级形态）。"""
    renderer = _Renderer()
    sql = (
        f"{_CTE_PREFIX}{renderer.expr(_build_cte_where_neutral(plan))})"
        " SELECT doc_id FROM visible_docs"
    )
    return sql, renderer.params


def render_fts_select(plan: AclPlan, *, query: str) -> tuple[str, dict[str, object]]:
    """FTS 路召回 SQL：visible_docs CTE + chunks_fts MATCH + 版本条件在 JOIN 上（T9）。"""
    renderer = _Renderer()
    sql = (
        f"{_CTE_PREFIX}{renderer.expr(_build_cte_where_neutral(plan))})"
        " SELECT c.rid, c.id, c.doc_id"
        " FROM chunks_fts f"
        " JOIN chunks c ON c.rid = f.rowid"
        " JOIN documents d ON d.id = c.doc_id AND c.version = d.active_version"
        f" WHERE {renderer.expr(build_fts_where_ast(plan, query=query))}"
    )
    return sql, renderer.params


def render_fts_recall_select(
    plan: AclPlan, match_expr: str, *, top_k: int
) -> tuple[str, dict[str, object]]:
    """M0a-3 BM25 召回（检索链实装形态，TC-FTS-02/TC-E2E-01）：

    - 溯源列一次取齐（chunk_id/doc_id/title/page_no/sheet/dataset/source/content/
      snippet 原文；v1.1 起无 dims_json 投影——dims 由 recall_fts 按
      document_dimensions 聚合回填，拍板 3）；
    - 五列加权 `bm25(chunks_fts, 3.0, 1.0, 5.0, 0.5, 8.0)`（结构常量，参数同列序）——
      越小越相关，ORDER BY ASC；LIMIT :top_k 经绑定参数；
    - match_expr 为 fts.build_match_expr 产物（token 转义后的字面量 OR 串），经 :q 绑定；
      WHERE 与 render_fts_select 同一 builder（build_fts_where_ast——三路同构 TC-ACL-06）。
    """
    renderer = _Renderer()
    sql = (
        f"{_CTE_PREFIX}{renderer.expr(_build_cte_where_neutral(plan))})"
        " SELECT c.rid, c.id AS chunk_id, c.doc_id, d.title, c.page_no, c.sheet_name,"
        " d.source_uri, d.dataset_id, ds.name AS dataset_name, c.content,"
        f" bm25(chunks_fts, {BM25_WEIGHTS}) AS score_raw"
        " FROM chunks_fts f"
        " JOIN chunks c ON c.rid = f.rowid"
        " JOIN documents d ON d.id = c.doc_id AND c.version = d.active_version"
        " JOIN datasets ds ON ds.id = d.dataset_id"
        f" WHERE {renderer.expr(build_fts_where_ast(plan, query=match_expr))}"
        " ORDER BY score_raw ASC"
        " LIMIT :top_k"
    )
    renderer.params["top_k"] = top_k
    return sql, renderer.params


def render_vec_recall_select(
    plan: AclPlan, query_vec: bytes, *, top_k: int
) -> tuple[str, dict[str, object]]:
    """M1-1 向量路召回 SQL（先过滤后距离——§5.2；与 PG 版 render_vec_recall_select 同构）：

    - 与 FTS/基础路共用同一 visible_docs CTE（TC-ACL-06 三路同构）；
    - `JOIN chunk_vectors cv ON cv.rid = c.rid AND cv.embed_model = :current_model`
      （v1.1 拍板 2——非当前标签行不进距离计算，TC-EMB-02/07）；cv 无行即未嵌入；
    - 距离 `vec_distance_cosine(cv.embedding, :q_vec)`（sqlite-vec BLOB——q_vec
      为 pack_f32 产物，经绑定参数绝不拼接进 SQL 文本）；ORDER BY dist ASC；
    - 溯源列与 render_fts_recall_select 对齐（rank 协议输出面）。
    """
    cte_where, cv_join, outer = _build_vec_parts_neutral(plan)
    renderer = _Renderer()
    sql = (
        f"{_CTE_PREFIX}{renderer.expr(cte_where)})"
        " SELECT c.rid, c.id AS chunk_id, c.doc_id, d.title, c.page_no, c.sheet_name,"
        " d.source_uri, d.dataset_id, ds.name AS dataset_name, c.content,"
        " vec_distance_cosine(cv.embedding, :q_vec) AS dist"
        " FROM chunks c"
        " JOIN documents d ON d.id = c.doc_id"
        " JOIN datasets ds ON ds.id = d.dataset_id"
        f"{renderer.expr(cv_join)}"
        f" WHERE {renderer.expr(outer)}"
        " ORDER BY dist"
        " LIMIT :top_k"
    )
    renderer.params["q_vec"] = query_vec
    renderer.params["top_k"] = top_k
    return sql, renderer.params
