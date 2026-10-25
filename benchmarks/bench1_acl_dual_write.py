"""实验 1（TC-PERF-01，v1.5.2 两档口径）：按块 json_each vs 按文档 visible_docs
——ACL 过滤后可见性查询（编译产物 SQL 真实执行）双写法 P95 对比。

口径（与 TEST-CASES v1.5.2 / design §5.1 性能注对齐）：
- 档位：1 万 / 5 万块两档（10 万档已取消——2026-10-24 用户拍板）；
- 双后端：sqlite（WAL/NORMAL 工厂纪律）+ pg（lattice-pg 容器，psycopg3 单连接
  autocommit，预热后自动 prepared statement）；
- 双写法：同一 AclPlan（core/docs/acl.compile_acl 真实编译——经 backend
  read_grants/read_membership 授权展开，三用户形态 u_narrow/u_broad/u_empty_tax）
  → 各方言 acl_render.render_select（按块 json_each/jsonb 模板）vs
  render_visible_docs_select（visible_docs CTE，纯 JOIN/EXISTS 无 JSON 方言函数）；
- 采样：预热 3 轮后计时（1 万档 n=30 / 5 万档 n=15——nearest-rank P50/P95，
  计时含 fetchall 全结果物化，两写法同口径）；
- 等价性复核（验收 1——性能实验不改变正确性结论）：每组合两写法结果集
  （rid,id,doc_id）多重集逐一比对，任何不等价即以非零退出码上报（停止而非继续）；
- 可移植性判据（D24）：双方言 visible_docs SQL 文本在参数记号归一化后应逐字相同
  （共用 acl_ast.build_visible_docs_parts + 同一渲染器骨架），按块模板则必然携带
  方言函数（json_each vs jsonb_array_elements_text）——程序化比对并输出。

复跑：LATTICE_PG_DSN=... uv run python benchmarks/bench1_acl_dual_write.py
输出：stdout markdown 表 + data/bench-results/bench1.json
"""

from __future__ import annotations

import re
import sys
import time

from bench_common import (
    BENCH_ORG,
    BENCH_USERS,
    md_table,
    machine_profile,
    open_bench_db,
    print_header,
    sample_timings,
    save_result,
    seed_corpus,
)

TIERS: tuple[tuple[int, int], ...] = ((10_000, 30), (50_000, 20))  # (块数, 采样数)
WARMUP = 3
CHUNKS_PER_DOC = 10


def normalize_pg_params(sql: str) -> str:
    """PG pyformat 记号 → sqlite 记号（%(x)s → :x）——可移植性比对的归一化基准。"""
    return re.sub(r"%\((\w+)\)s", r":\1", sql)


def run_tier(dialect: str, n_chunks: int, samples: int) -> tuple[list[dict], list[str]]:
    tag = f"bench1_{dialect}_{n_chunks}"
    rows_out: list[dict] = []
    equiv_lines: list[str] = []
    with open_bench_db(dialect, tag=tag) as db:
        t0 = time.perf_counter()
        seed_corpus(db, n_docs=n_chunks // CHUNKS_PER_DOC, chunks_per_doc=CHUNKS_PER_DOC)
        seed_s = time.perf_counter() - t0

        for user_id in BENCH_USERS:
            plan = db.compile_acl(user_id, BENCH_ORG)
            per_chunk_sql, per_chunk_params = db.render_select(plan)
            visible_sql, visible_params = db.render_visible_docs_select(plan)
            # PG 计划病理修复变体（可见实验记录：CTE 内联后按块重复求值——
            # EXPLAIN loops=chunks；MATERIALIZED 强制按文档一次物化，一词修复）
            mat_sql = visible_sql.replace("AS (", "AS MATERIALIZED (", 1)

            def run_per_chunk() -> list[tuple]:
                return db.execute(per_chunk_sql, per_chunk_params)

            def run_visible() -> list[tuple]:
                return db.execute(visible_sql, visible_params)

            def run_visible_mat() -> list[tuple]:
                return db.execute(mat_sql, visible_params)

            # 等价性复核（每组合必查——不等价属重大发现，立即失败退出）
            a, b = sorted(run_per_chunk()), sorted(run_visible())
            if a != b:
                print(
                    f"FATAL 等价性破坏: dialect={dialect} tier={n_chunks} user={user_id} "
                    f"per_chunk={len(a)} rows visible_docs={len(b)} rows ——停止上报",
                    file=sys.stderr,
                )
                sys.exit(2)
            if dialect == "pg":  # MATERIALIZED 变体同样纳入等价性复核
                m = sorted(run_visible_mat())
                if m != a:
                    print(
                        f"FATAL 等价性破坏(MATERIALIZED): {dialect}/{n_chunks}/{user_id} "
                        f"——{len(m)} vs {len(a)} 行",
                        file=sys.stderr,
                    )
                    sys.exit(2)

            t_per = sample_timings(run_per_chunk, warmup=WARMUP, n=samples)
            t_vis = sample_timings(run_visible, warmup=WARMUP, n=samples)
            forms = [("json_each(按块)", t_per), ("visible_docs(按文档)", t_vis)]
            if dialect == "pg":
                forms.append(
                    ("visible_docs+MATERIALIZED(补充)", sample_timings(run_visible_mat, warmup=WARMUP, n=samples))
                )
            for form, t in forms:
                rows_out.append(
                    {
                        "tier": n_chunks,
                        "dialect": dialect,
                        "user": user_id,
                        "form": form,
                        "rows": len(a),
                        "seed_s": round(seed_s, 1),
                        **t,
                    }
                )
            equiv_lines.append(
                f"{dialect}/{n_chunks}/{user_id}: 两写法（含 MATERIALIZED 变体）结果集逐行等价 ✓（{len(a)} 行）"
            )
        print(f"[{dialect} {n_chunks}] 造数 {seed_s:.1f}s；等价性复核全部通过", flush=True)
    return rows_out, equiv_lines


def portability_check() -> dict[str, str]:
    """D24 可移植性判据：同一 plan 双方言渲染产物，参数记号归一化后比对。"""
    with open_bench_db("sqlite", tag="port_sqlite") as sdb, open_bench_db(
        "pg", tag="port_pg"
    ) as pdb:
        seed_corpus(sdb, n_docs=1, chunks_per_doc=1)
        seed_corpus(pdb, n_docs=1, chunks_per_doc=1)
        plan_s = sdb.compile_acl("u_narrow", BENCH_ORG)
        plan_p = pdb.compile_acl("u_narrow", BENCH_ORG)
        vis_s, _ = sdb.render_visible_docs_select(plan_s)
        vis_p, _ = pdb.render_visible_docs_select(plan_p)
        per_s, _ = sdb.render_select(plan_s)
        per_p, _ = pdb.render_select(plan_p)

    vis_norm_equal = normalize_pg_params(vis_p) == vis_s
    per_norm_equal = normalize_pg_params(per_p) == per_s
    return {
        "visible_docs_归一化后逐字相同": "是" if vis_norm_equal else "否",
        "json_each_归一化后逐字相同": "是" if per_norm_equal else "否（方言函数差异）",
        "visible_docs_sqlite": vis_s,
        "visible_docs_pg_归一化": normalize_pg_params(vis_p),
        "json_each_sqlite": per_s,
        "json_each_pg_归一化": normalize_pg_params(per_p),
    }


_LOOPS_RE = re.compile(r"loops=(\d+)")


def _loops_by_kind(plan_text: str, kind: str) -> int | None:
    """解析 EXPLAIN ANALYZE 文本中含指定节点类型（如 "Anti Join" / "CTE Scan"）
    的行的 max loops——文档级谓词（Anti Join 分支）是按块还是按文档重复求值的
    直接证据。

    P3-H（0 误判边界）：计划文本中**未命中**该节点类型时返回 None（区别于
    命中但 loops=0）——调用方 PASS 判定要求非 None，防"证据缺失"被当作
    loops=0 满足 `<= n_docs` 而误判 PASS。"""
    best: int | None = None
    for line in plan_text.splitlines():
        if kind in line:
            m = _LOOPS_RE.search(line)
            if m:
                loops = int(m.group(1))
                best = loops if best is None else max(best, loops)
    return best


def capture_plans() -> dict[str, str]:
    """计划形态证据（报告引用，P2-5 脚本化）：u_broad 各写法双方言计划——
    sqlite 默认物化 CTE（LIST SUBQUERY + REUSE）；pg inline 按块重复求值
    （文档级谓词反连接分支 loops=块数）vs MATERIALIZED 按文档一次物化
    （CTE 段 loops=文档数）。小规模（200 文档 ×10 块）足以呈现计划形态。"""
    plans: dict[str, str] = {}

    def fill(sql: str, params: dict) -> str:
        for k, v in params.items():
            sql = sql.replace(f"%({k})s", f"'{v}'" if isinstance(v, str) else str(v))
        return sql

    with open_bench_db("sqlite", tag="plan_sqlite") as db:
        seed_corpus(db, n_docs=200, chunks_per_doc=10)
        plan = db.compile_acl("u_broad", BENCH_ORG)
        vis_sql, vis_p = db.render_visible_docs_select(plan)
        per_sql, per_p = db.render_select(plan)
        plans["sqlite_json_each_eqp"] = "\n".join(
            r[-1] for r in db.execute("EXPLAIN QUERY PLAN " + per_sql, per_p)
        )
        plans["sqlite_visible_docs_eqp"] = "\n".join(
            r[-1] for r in db.execute("EXPLAIN QUERY PLAN " + vis_sql, vis_p)
        )
    with open_bench_db("pg", tag="plan_pg") as db:
        seed_corpus(db, n_docs=200, chunks_per_doc=10)
        n_docs = 200
        n_chunks = n_docs * 10
        plan = db.compile_acl("u_broad", BENCH_ORG)
        vis_sql, vis_p = db.render_visible_docs_select(plan)
        per_sql, per_p = db.render_select(plan)
        mat_sql = vis_sql.replace("AS (", "AS MATERIALIZED (", 1)
        plans["pg_json_each_explain"] = "\n".join(
            r[0] for r in db.execute("EXPLAIN (COSTS OFF) " + fill(per_sql, per_p))
        )
        # P2-5：ANALYZE 实测计划——文档级谓词按块（loops=块数 2000）还是按文档
        # （CTE 段 loops=文档数 200）重复求值，逐行可从交付物复现
        plans["pg_visible_docs_explain_analyze"] = "\n".join(
            r[0] for r in db.execute(
                "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF) " + fill(vis_sql, vis_p)
            )
        )
        plans["pg_visible_docs_materialized_explain_analyze"] = "\n".join(
            r[0] for r in db.execute(
                "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF) " + fill(mat_sql, vis_p)
            )
        )
        inline_anti_loops = _loops_by_kind(
            plans["pg_visible_docs_explain_analyze"], "Anti Join"
        )
        mat_anti_loops = _loops_by_kind(
            plans["pg_visible_docs_materialized_explain_analyze"], "Anti Join"
        )
        mat_cte_scan_loops = _loops_by_kind(
            plans["pg_visible_docs_materialized_explain_analyze"], "CTE Scan"
        )
        # P3-H：证据缺失（None）与数值 0 区分——任一分支未命中节点即 FAIL
        evidence_complete = (
            inline_anti_loops is not None
            and mat_anti_loops is not None
            and mat_cte_scan_loops is not None
        )
        verdict = (
            "PASS"
            if evidence_complete
            and inline_anti_loops >= n_chunks
            and mat_anti_loops <= n_docs
            else "FAIL（计划形态与结论不符/证据缺失——需上报）"
        )
        plans["pg_loops_verdict"] = (
            f"{verdict}: inline 文档级谓词（Anti Join 分支）max loops={inline_anti_loops}"
            f"（=块数 {n_chunks}：按块重复求值）；MATERIALIZED CTE 段 Anti Join max loops="
            f"{mat_anti_loops}（=文档数 {n_docs}：按文档一次物化；外层 CTE Scan 对物化集"
            f"按块探查 loops={mat_cte_scan_loops}——semi join 本分，与谓词重求值不同）"
        )
    return plans


V10_SCHEMA_NOTICE = (
    "本实验测量 schema v1.0 的 json_each 按块路 vs visible_docs 双写法（M0b-2）。\n"
    "M0b-3 已拍板删 dims_json/json_each 模板（visible_docs+MATERIALIZED 唯一路径），\n"
    "src 渲染器不再提供按块路——复跑本实验请 checkout M0b-2 提交（a6ffa1c）。"
)


def _guard_v10_schema() -> None:
    """v1.0 实验退役守卫：探测 src 是否仍有按块渲染入口（render_visible_docs_select
    已删/已并轨即视为退役）——退出码 0 + 明示信息，绝不静默产出误导性数据。"""
    try:
        from knowledge_lattice.store.sqlite import acl_render  # noqa: F401
    except Exception as exc:  # pragma: no cover - 环境异常
        raise SystemExit(f"bench1: import failed: {exc}")
    if not hasattr(acl_render, "render_visible_docs_select"):
        print(V10_SCHEMA_NOTICE)
        raise SystemExit(0)


def main() -> None:
    _guard_v10_schema()
    all_rows: list[dict] = []
    equiv: list[str] = []
    for dialect in ("sqlite", "pg"):
        for n_chunks, samples in TIERS:
            rows, lines = run_tier(dialect, n_chunks, samples)
            all_rows.extend(rows)
            equiv.extend(lines)

    print_header("实验 1（TC-PERF-01）ACL 双写法 P95——全部组合")
    table_rows = [
        [
            r["tier"],
            r["dialect"],
            r["user"],
            r["form"],
            r["rows"],
            r["p50_ms"],
            r["p95_ms"],
        ]
        for r in all_rows
    ]
    print(md_table(["块档", "后端", "用户", "写法", "结果行数", "P50 ms", "P95 ms"], table_rows))

    print_header("等价性复核（TC-ACL-07 语义在实验规模）")
    for line in equiv:
        print(f"- {line}")

    port = portability_check()
    print_header("可移植性判据（D24——参数记号归一化后比对）")
    print(f"- visible_docs 双方言归一化后逐字相同：**{port['visible_docs_归一化后逐字相同']}**")
    print(f"- json_each 双方言归一化后逐字相同：**{port['json_each_归一化后逐字相同']}**")
    print("\n```sql")
    print("-- visible_docs（sqlite 原文；pg 归一化后与上逐字相同）：")
    print(port["visible_docs_sqlite"])
    print("")
    print("-- json_each sqlite：")
    print(port["json_each_sqlite"])
    print("")
    print("-- json_each pg（归一化——方言函数不同）：")
    print(port["json_each_pg_归一化"])
    print("```")

    profile = machine_profile()
    plans = capture_plans()
    print_header("机器口径")
    for k, v in profile.items():
        print(f"- {k}: {v}")
    print_header("计划形态证据（双方言——完整文本见 data/bench-results/bench1.json）")
    print(
        "- sqlite visible_docs：CTE 一次物化（LIST SUBQUERY + REUSE）——设计意图形态\n"
        "- pg visible_docs(inline)：CTE 内联为 Semi Join，文档级谓词按块重复求值\n"
        "- pg visible_docs+MATERIALIZED：CTE 强制一次物化——一词修复\n"
        "- 双写法 json_each：双方言均为块级扫描 + 函数展开（无文档级去重）"
    )
    print(f"- **EXPLAIN ANALYZE loops 实测（P2-5 脚本化）：{plans['pg_loops_verdict']}**")

    path = save_result(
        "bench1",
        {
            "profile": profile,
            "rows": all_rows,
            "equivalence": equiv,
            "portability": port,
            "plans": plans,
        },
    )
    print(f"\n结果工件：{path}")


if __name__ == "__main__":
    main()
