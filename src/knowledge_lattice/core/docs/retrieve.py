"""检索管线编排（design §5.2——M1-1 完整配方：双路召回 + RRF + rerank + 增强 + 归一）。

流程（§5.2）：
    query ─→ LLM 关键词增强（800ms 硬预算、与原始召回并行；词条作 RRF 第三路
         │   BM25 查询——不重做向量召回；超时/失败丢弃，不标降级）
         ├─→ FTS/BM25 路（五列加权——backend.recall_fts，名次协议）
         ├─→ 向量路（query embed → 先 ACL 过滤后距离——backend.recall_vec，
         │   cv.embed_model JOIN 谓词；嵌入不可达/探针拒绝/超时 → 降级 BM25 单路）
         ─→ RRF 融合（k=60；单路 chunk 自然保留）
         ─→ ACL 兜底断言（rerank 前：不该进模型的内容不进模型——独立重编译可见集）
         ─→ 取 top-rerank_candidates（32，降级开关可 16）→ rerank（content 原文；
         │   Cohere 风格 /rerank 或 none；失败/超时 → 跳过重排用 RRF 序 + 审计）
         ─→ 分数归一 [0,1]（min-max / clamp(IQR) 双分支，ragflow 模式）
         ─→ 返回前二次 ACL 断言 → 阈值（只作用于归一后分数）→ top-k（≤20 硬上限）

降级可观测（v0.8 #42 P1-4）：任何降级（embed_unreachable / rerank_skipped /
probe_reject）统一 notice.degraded 标注 + search.degraded 审计事件（reason 同源）。

分层纪律：编排不碰 SQL——召回/断言源/向量缺失判定全经 StorageBackend；嵌入
（Embedder）/重排（Reranker）/增强（Enhancer）为 provider 接口（D12）；模型
HTTP 调用经线程池（api 层 asyncio.to_thread 下放本函数、MCP sync 工具由
FastMCP 线程池承接——事件循环无长阻塞，NFR-8）。

熔断（NFR-8）：embed/rerank 查询侧调用经 CircuitBreaker（连续 3 失败断开
60s、半开恢复）——open 期间直接降级不等超时（「慢」与「不可达」由熔断区分）。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from knowledge_lattice.adapters import tokenizer
from knowledge_lattice.adapters.embedder import EmbeddingGate
from knowledge_lattice.config import Settings
from knowledge_lattice.core.docs.acl import AclDeniedError, compile_acl

logger = logging.getLogger(__name__)

TOP_K_HARD_LIMIT = 20  # 服务端硬上限（§5.2 / TC-RET-07①）

# 模型调用线程池（query 嵌入 / rerank / LLM 增强——绝不阻塞事件循环，NFR-8；
# 增强与原始召回并行窗口的事实载体）。进程级共享（单进程低 QPS 形态）。
# rerank 专用池（P2-2）：调用线程先取信号量再提交——等待者在调用线程排队、
# 不占池内 worker，池内永不排队 → 超时预算≈实际调用时长（排队时间不计入）。
_MODEL_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="lattice-model")
_RERANK_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="lattice-rerank")

# rerank 并发信号量（§5.2：并发上限信号量保护——按配置值缓存实例）
_RERANK_SEMS: dict[int, threading.Semaphore] = {}
_SEMS_LOCK = threading.Lock()

# 归一离群判定系数（clamp 分支：Q1-1.5·IQR / Q3+1.5·IQR——ragflow 模式双分支
# 实现择型：集中分布 min-max、含离群 clamp 后 min-max；系数申报 M1-4 校准）
_IQR_K = 1.5

# rerank 响应缺项的排序键（P3-4：显式垫底——负分网关下仍低于全部有分项）
_NEG_INF = float("-inf")


def _rerank_sem(limit: int) -> threading.Semaphore:
    with _SEMS_LOCK:
        if limit not in _RERANK_SEMS:
            _RERANK_SEMS[limit] = threading.Semaphore(limit)
        return _RERANK_SEMS[limit]


# ============ RRF 融合与分数归一（纯函数——单测面） ============


def rrf_fuse(
    routes: Sequence[tuple[str, Sequence[int]]], *, k: int = 60
) -> list[tuple[int, float]]:
    """倒数排名融合：score(d) = Σ_route 1/(k + rank_route(d))——rank 1 起。

    各路 rid 序列须按名次升序（调用方经 _rids_by_rank 显式排序——名次协议
    P3-2：rank 字段是唯一消费面，不依赖后端返回的物理顺序）。
    并列（融合分完全相等）按 rid 升序 tie-break（确定性——双后端名次集等价
    断言基础，A-17）；单路 chunk 按该路 RRF 分自然保留（退化兼容，TC-RET-01）。
    """
    scores: dict[int, float] = {}
    for _route, rids in routes:
        for rank, rid in enumerate(rids, start=1):
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def _rids_by_rank(rows: Sequence[dict]) -> list[int]:
    """召回行按 rank 升序取 rid（名次协议防御——后端乱序返回不静默错序）。"""
    return [r["rid"] for r in sorted(rows, key=lambda r: r["rank"])]


def _quantile(sorted_values: Sequence[float], p: float) -> float:
    """线性插值分位数（clamp 分支的离群界——不引入 numpy 依赖，实现自持）。"""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = p * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = position - lower
    return float(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * frac)


def normalize_scores(values: Sequence[float]) -> tuple[list[float], str]:
    """归一 [0,1]（ragflow 模式双分支——§5.2「min-max/clamp 双分支」）。

    - 集中分布（无离群）：min-max（保序、顶格 1.0 / 底格 0.0）；
    - 含离群（超出 Q1-1.5·IQR / Q3+1.5·IQR）：先 clamp 到界内再 min-max——
      离群点不把主体分数压扁（主体区分度保留，TC-RET-03）；
    - 返回 (归一分列表, 分支名)——分支名供观测与测试断言。
    """
    if not values:
        return [], "minmax"
    ordered = sorted(values)
    q1 = _quantile(ordered, 0.25)
    q3 = _quantile(ordered, 0.75)
    lo, hi = q1 - _IQR_K * (q3 - q1), q3 + _IQR_K * (q3 - q1)
    if any(v < lo or v > hi for v in values):
        branch = "clamp"
        source = [min(max(v, lo), hi) for v in values]
    else:
        branch = "minmax"
        source = list(values)
    mn, mx = min(source), max(source)
    if mx == mn:
        return [1.0] * len(source), branch
    return [round((v - mn) / (mx - mn), 4) for v in source], branch


# ============ ACL 兜底断言（rerank 前 / 返回前——防御纵深，TC-ACL-08） ============


def _drop_invisible_pre_rerank(
    candidates: list[dict], visible: set[int], backend, ctx: dict
) -> tuple[list[dict], list[int]]:
    """rerank 前断言：候选 ⊆ 可见集——越权块在外发（进模型）前剔除 + 拦截审计。

    独立函数边界（monkeypatch 面）：TC-ACL-08 防御纵深可测——单独移除任一
    断言时对应用例失败。返回 (净化候选, 被剔除 rid 列表)。
    """
    blocked = [c["rid"] for c in candidates if c["rid"] not in visible]
    if blocked:
        _audit_intercept(backend, ctx, "pre_rerank", blocked)
        return [c for c in candidates if c["rid"] in visible], blocked
    return candidates, []


def _drop_invisible_final(
    ordered: list[dict], visible: set[int], backend, ctx: dict
) -> list[dict]:
    """返回前二次断言：rerank 响应注入 / 中途权限收紧等面的兜底——最终 top-k
    无越权块（FR-4 红线的第二道）。"""
    bad = [c["rid"] for c in ordered if c["rid"] not in visible]
    if bad:
        _audit_intercept(backend, ctx, "pre_return", bad)
        return [c for c in ordered if c["rid"] in visible]
    return ordered


def _audit_intercept(backend, ctx: dict, phase: str, rids: Sequence[int]) -> None:
    try:
        backend.append_outbox(
            "search.acl_intercept",
            json.dumps(
                {
                    "user_id": ctx.get("user_id"),
                    "org_id": ctx.get("org_id"),
                    "phase": phase,
                    "rids": list(rids),
                },
                ensure_ascii=False,
            ),
        )
    except Exception:  # noqa: BLE001 —— 审计失败不阻断检索主路径
        logger.exception("search.acl_intercept audit write failed")


def _audit_degraded(backend, ctx: dict, reasons: Sequence[str]) -> None:
    """search.degraded 审计事件（reason 与 notice.degraded 同源——v0.8 P1-4）。"""
    try:
        backend.append_outbox(
            "search.degraded",
            json.dumps(
                {
                    "user_id": ctx.get("user_id"),
                    "org_id": ctx.get("org_id"),
                    "reasons": sorted(set(reasons)),
                },
                ensure_ascii=False,
            ),
        )
    except Exception:  # noqa: BLE001
        logger.exception("search.degraded audit write failed")


# ============ 检索主入口（MCP/REST 同构契约） ============


def search(
    backend,
    settings: Settings,
    *,
    user_id: str,
    org_id: str,
    query: str,
    top_k: int = 8,
    datasets: Sequence[str] | None = None,
    doc_filter: Sequence[str] | None = None,
    gate: EmbeddingGate | None = None,
    embedder=None,
    reranker=None,
    enhancer=None,
    breakers: dict | None = None,
) -> dict:
    """完整配方检索（§5.2）——AclDeniedError 由调用方转 403 语义。

    返回 MCP/REST 同构契约：{results: [...], notice: {vector_pending, degraded}}。
    provider 注入：embedder / reranker / enhancer（None 或 none 档 = 对应路停用，
    none 档不标降级——配置态非故障）；breakers={"embed":…, "rerank":…} 熔断共享态。
    """
    started = time.monotonic()
    top_k = max(1, min(top_k, TOP_K_HARD_LIMIT))
    plan = compile_acl(backend, user_id, org_id, dataset_ids=datasets, doc_ids=doc_filter)
    vec_plan = compile_acl(
        backend,
        user_id,
        org_id,
        dataset_ids=datasets,
        doc_ids=doc_filter,
        embed_model=(embedder.model_label if embedder is not None else None),
    )
    ctx = {"user_id": user_id, "org_id": org_id}
    degraded: list[str] = []
    # 向量缺失判定的有效标签：跟随 embedder（与写入标签同源）；无 embedder 退 settings
    vec_label = embedder.model_label if embedder is not None else settings.embed_model_label

    # ---- LLM 增强并行窗口（800ms 硬预算——与原始召回并行；超时/失败丢弃）----
    enhance_future: Future | None = None
    enhance_t0 = 0.0
    if enhancer is not None and settings.enhancer != "none":
        enhance_t0 = time.monotonic()
        enhance_future = _MODEL_POOL.submit(enhancer.enhance, query)

    # ---- FTS/BM25 路（五列加权——名次协议；召回窗口给足 NFR-8）----
    tokens = tokenizer.segment_query(query)
    fts_rows = (
        backend.recall_fts(tokens, plan, top_k=settings.recall_window) if tokens else []
    )
    t_fts = time.monotonic() - started

    # ---- 向量路（query embed → 先 ACL 过滤后距离；降级链）----
    if gate is not None and gate.rejected:
        degraded.append("probe_reject")  # 探针拒绝档：跨底模距离无意义（拍板2）——不发嵌入
    vec_rows: list[dict] = []
    query_vec: list[float] | None = None
    # P2-新（m1-1 committer 修复）：熔断探测（allow）只在**确实会发起调用**时进行
    # （embedder 非空且探针未拒绝）——否则「探针拒绝 + 熔断半开」叠加时半开探测
    # 令牌被消耗且无 success/failure 回写，_probing 永不复位（向量路不自愈需重启）。
    embed_breaker_open = (
        not _breaker_allows(breakers, "embed")
        if embedder is not None and not (gate is not None and gate.rejected)
        else False
    )
    vec_skipped = (
        embedder is None
        or (gate is not None and gate.rejected)
        or embed_breaker_open
    )
    if embed_breaker_open and embedder is not None:
        # 熔断开路=「已确认不可达」的降级态（连续失败断开期间直接降级不等超时——
        # NFR-8）；与 none 配置态不同，须标注 + 审计（P1-2）
        degraded.append("embed_unreachable")
    if not vec_skipped:
        query_vec = _embed_query(settings, embedder, query, breakers, degraded)
        if query_vec is not None:
            vec_rows = backend.recall_vec(
                query_vec, vec_plan, top_k=settings.recall_window
            )
    # 向量路整体关闭（P1-1）：静态跳过（无 embedder/探针拒绝/熔断开）**或本次嵌入
    # 失败/超时**——「未就绪或降级」两面俱全（§6.1 vector_pending 契约）
    vec_closed = vec_skipped or (embedder is not None and query_vec is None)
    t_recall = time.monotonic() - started

    # ---- RRF 融合（双路 → 增强词到位则并入第三路 BM25——不重做向量召回）----
    # 名次协议防御（P3-2）：各路 rid 序显式按 rank 升序取——不依赖后端返回顺序
    merged: dict[int, dict] = {r["rid"]: r for r in fts_rows}
    routes: list[tuple[str, list[int]]] = [("fts", _rids_by_rank(fts_rows))]
    if vec_rows:
        routes.append(("vec", _rids_by_rank(vec_rows)))
        merged.update({r["rid"]: r for r in vec_rows})
    if enhance_future is not None:
        extra_terms = _await_enhancement(
            enhance_future, settings.enhance_budget_s - (time.monotonic() - enhance_t0)
        )
        if extra_terms:
            enhanced_rows = backend.recall_fts(
                extra_terms, plan, top_k=settings.recall_window
            )
            if enhanced_rows:
                routes.append(("enhanced", _rids_by_rank(enhanced_rows)))
                for r in enhanced_rows:  # 溯源信息合并（第三路新块补位）
                    merged.setdefault(r["rid"], r)
    fused = rrf_fuse(routes, k=settings.rrf_k)
    t_fuse = time.monotonic() - started

    candidates = [dict(merged[rid], rrf_score=score) for rid, score in fused]
    if not candidates:
        return _finalize(
            backend, settings, ctx, degraded, [], top_k,
            vec_closed=vec_closed, has_results=False, vec_label=vec_label,
            timings=(t_fts, t_recall, t_fuse, time.monotonic() - started),
            routes=len(routes),
        )

    # ---- ACL 兜底断言（rerank 前——独立重编译可见集，TC-ACL-08）----
    # 独立性来自 SQL 路径（基础路 render_select vs FTS/向量召回路）而非编译次数
    # （P3-15 注记：guard_plan 复用 plan 与否留后续优化——语义等价，省 2 次库读）
    guard_plan = compile_acl(
        backend, user_id, org_id, dataset_ids=datasets, doc_ids=doc_filter
    )
    # P2-3：断言数据源按候选集收窄扫描（防宽权限全量 O(N)×2；独立 SQL 路径不变）
    visible = backend.visible_chunk_ids(guard_plan, [c["rid"] for c in candidates])
    candidates, _blocked = _drop_invisible_pre_rerank(candidates, visible, backend, ctx)
    if not candidates:
        return _finalize(
            backend, settings, ctx, degraded, [], top_k,
            vec_closed=vec_closed, has_results=False, vec_label=vec_label,
            timings=(t_fts, t_recall, t_fuse, time.monotonic() - started),
            routes=len(routes),
        )

    # ---- rerank（top-candidates（32 / 降级 16）；content 原文；降级链）----
    candidates = candidates[: settings.rerank_candidates]
    rank_scores: dict[int, float] | None = None
    # P2-新（rerank 侧同款）：none 档/无 reranker（不发起调用）不消耗熔断探测令牌
    rerank_active = reranker is not None and settings.reranker != "none"
    rerank_breaker_open = (
        not _breaker_allows(breakers, "rerank") if rerank_active else False
    )
    if rerank_breaker_open:
        # 熔断开路=已确认不可达的降级态——标注 + 审计（P1-2；none 配置态不标）
        degraded.append("rerank_skipped")
    if rerank_active and not rerank_breaker_open:
        rank_scores = _run_rerank(
            settings, reranker, breakers, query, candidates, degraded
        )
    t_rerank = time.monotonic() - started

    # ---- 最终序（rerank 分降序、tie 用 RRF 序；无 rerank 分 = RRF 序）+ 归一 ----
    if rank_scores is not None:
        # P3-4：响应缺项以 -inf 排序键显式垫底（负分网关下仍低于全部有分项），
        # 归一只消费有分项、缺项归一分 0.0（顶底语义稳定）
        ordered = sorted(
            candidates,
            key=lambda c: (-rank_scores.get(c["rid"], _NEG_INF), -c["rrf_score"]),
        )
        present = [rank_scores[c["rid"]] for c in ordered if c["rid"] in rank_scores]
        normalized_present, _branch = normalize_scores(present)
        score_by_rid = {
            c["rid"]: s
            for c, s in zip(
                [c for c in ordered if c["rid"] in rank_scores], normalized_present
            )
        }
        for row in ordered:
            row["final_score"] = score_by_rid.get(row["rid"], 0.0)
    else:
        ordered = sorted(candidates, key=lambda c: -c["rrf_score"])
        raw_scores = [c["rrf_score"] for c in ordered]
        normalized, _branch = normalize_scores(raw_scores)  # 无 rerank 分→RRF 归一（TC-EMB-05）
        for row, score in zip(ordered, normalized):
            row["final_score"] = score

    # ---- 返回前二次 ACL 断言（独立重取可见集——纵深不共用前断言快照，TC-ACL-08；
    #      P2-3 按 top-k 候选集收窄）→ 阈值（只作用于归一后分数）→ top-k ----
    visible_final = backend.visible_chunk_ids(
        guard_plan, [c["rid"] for c in ordered]
    )
    ordered = _drop_invisible_final(ordered, visible_final, backend, ctx)
    if settings.score_threshold > 0.0:
        ordered = [c for c in ordered if c["final_score"] >= settings.score_threshold]
    ordered = ordered[:top_k]

    return _finalize(
        backend, settings, ctx, degraded, ordered, top_k,
        vec_closed=vec_closed, has_results=bool(fts_rows or vec_rows),
        vec_label=vec_label,
        timings=(t_fts, t_recall, t_fuse, t_rerank),
        routes=len(routes),
    )


def _finalize(
    backend,
    settings: Settings,
    ctx: dict,
    degraded: list[str],
    ordered: list[dict],
    top_k: int,
    *,
    vec_closed: bool,
    has_results: bool,
    vec_label: str,
    timings: tuple[float, float, float, float],
    routes: int,
) -> dict:
    """输出面组装：vector_pending 块级判定 + 双断言后 results + 降级审计 + 耗时日志。"""
    vector_pending = False
    if ordered:
        missing = backend.rids_without_vector([c["rid"] for c in ordered], vec_label)
        # 向量路整体关闭（无 embedder / 降级）且有结果 → 本结果必然缺向量路
        vector_pending = bool(missing) or (vec_closed and has_results)

    if degraded:
        _audit_degraded(backend, ctx, degraded)

    results = []
    for rank, row in enumerate(ordered, start=1):
        content = row.get("content") or ""
        results.append(
            {
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                # `dataset`＝知识库名称（MCP 契约 §6.1 示例）；id 另出 dataset_id（P3-3）
                "dataset": row.get("dataset_name"),
                "dataset_id": row.get("dataset_id"),
                "title": row.get("title"),
                "page_no": row.get("page_no"),
                "sheet_name": row.get("sheet_name"),
                "score": row.get("final_score", 0.0),
                "rank": rank,
                # dims 契约：v1.1 起经 store 聚合回填（document_dimensions——D22 真相源）
                "dims": row.get("dims") or {},
                "source": row.get("source_uri"),
                "snippet": content[:120],
            }
        )
    t_fts, t_recall, t_fuse, t_rerank = timings
    logger.info(
        "search timing: fts=%.1fms recall=%.1fms fuse=%.1fms rerank=%.1fms"
        " routes=%d results=%d degraded=%s",
        t_fts * 1000, t_recall * 1000, t_fuse * 1000, t_rerank * 1000,
        routes, len(results), degraded or "-",
    )
    return {
        "results": results,
        "notice": {"vector_pending": vector_pending, "degraded": degraded},
    }


def _breaker_allows(breakers: dict | None, name: str) -> bool:
    breaker = (breakers or {}).get(name)
    return breaker is None or breaker.allow()


def _embed_query(
    settings: Settings, embedder, query: str, breakers: dict | None, degraded: list[str]
) -> list[float] | None:
    """查询侧嵌入（超时 500ms 硬上限 NFR-8——线程池下放；失败/超时→降级
    embed_unreachable + 熔断计数）。

    维度契约由 provider 保证 == config.embed_dim（Embedder Protocol；写入侧
    校验在摄取链 TC-EMB-01）——查询侧只防空向量，不重复校验。"""
    breaker = (breakers or {}).get("embed")
    future = _MODEL_POOL.submit(embedder.embed, [query])
    try:
        vectors = future.result(timeout=settings.query_embed_timeout_s)
        vector = vectors[0] if vectors else None
        if vector is not None:
            if breaker is not None:
                breaker.record_success()
            return vector
        raise ValueError("query embed returned empty vector")
    except (FutureTimeoutError, Exception) as exc:  # noqa: BLE001
        degraded.append("embed_unreachable")
        if breaker is not None:
            breaker.record_failure()
        logger.warning("query embed degraded: %s", exc)
        return None


def _run_rerank(
    settings: Settings,
    reranker,
    breakers: dict | None,
    query: str,
    candidates: list[dict],
    degraded: list[str],
) -> dict[int, float] | None:
    """rerank 调用：content 原文（可按 token 截断——TC-RET-06 开关）、超时 1000ms
    硬上限（NFR-8）；失败/超时/**空响应** → rerank_skipped 降级（返回 None，
    调用方用 RRF 序）+ 熔断计数。返回 {rid: relevance_score}。

    P2-2：并发信号量在**调用线程** acquire（管线已在线程池——阻塞安全；等待者
    不占 _RERANK_POOL worker）→ 提交后池内不排队，超时预算≈实际调用时长
    （排队时间不计入单次调用超时——与熔断的「慢 vs 不可达」分工一致）。
    P3-3：响应空列表/全部 index 越界（防御丢弃后 scores 空）＝无效响应，视同
    失败走 rerank_skipped（空响应不得伪装「全相关」顶格 1.0）。
    """
    documents = [_truncate_content(c.get("content") or "", settings) for c in candidates]
    breaker = (breakers or {}).get("rerank")
    sem = _rerank_sem(settings.rerank_max_concurrency)
    sem.acquire()  # 调用线程等待（不占池——排队不计入调用超时）
    try:
        future = _RERANK_POOL.submit(
            reranker.rerank, query, documents, top_n=len(documents)
        )
        try:
            ranked = future.result(timeout=settings.rerank_timeout_s)
        except (FutureTimeoutError, Exception) as exc:  # noqa: BLE001
            degraded.append("rerank_skipped")
            if breaker is not None:
                breaker.record_failure()
            logger.warning("rerank degraded: %s", exc)
            return None
    finally:
        sem.release()

    scores: dict[int, float] = {}
    for item in ranked:
        if 0 <= item.index < len(candidates):  # 越界 index 防御丢弃（响应注入面）
            scores[candidates[item.index]["rid"]] = float(item.relevance_score)
    if not scores:  # P3-3：空响应/全越界＝无效响应——视同失败降级
        degraded.append("rerank_skipped")
        if breaker is not None:
            breaker.record_failure()
        logger.warning("rerank degraded: empty/invalid response (%d items)", len(ranked))
        return None
    if breaker is not None:
        breaker.record_success()
    return scores


def _truncate_content(content: str, settings: Settings) -> str:
    """rerank 输入截断（降级开关：rerank_truncate_tokens=None 不截；256=按 jieba
    token 边界截断——NFR-8「rerank 输入截断 256 token」）。

    P2-1：token 间以空格连接——英文/中英混排原文的词间空白不被吞（`"".join`
    会把 `hello world` 改写成 `helloworld`）；中文多出的空格对 cross-encoder
    无语义影响。截断本就是有损降级档，保词边界优先于保逐字原文。
    """
    limit = settings.rerank_truncate_tokens
    if limit is None or not content:
        return content
    tokens = tokenizer.segment(content)
    if len(tokens) <= limit:
        return content
    return " ".join(tokens[:limit])  # 空格保词边界（英文安全、中文无语义损失）


def _await_enhancement(future: Future, remaining_s: float) -> list[str] | None:
    """增强窗口收口：预算内取词条；超时/失败丢弃（不标降级——增益路非可用性前提，
    §5.2「超时丢弃」）。返回 None=无增强。"""
    try:
        terms = future.result(timeout=max(0.0, remaining_s))
        return [t for t in (terms or []) if t and t.strip()]
    except (FutureTimeoutError, Exception):  # noqa: BLE001
        return None


__all__ = [
    "search",
    "TOP_K_HARD_LIMIT",
    "AclDeniedError",
    "rrf_fuse",
    "normalize_scores",
]
