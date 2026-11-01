"""实体检索与表详情透传（design §6.3——m2s-2 首批工具的查询面收口；
design §3 未单列本模块、随 m2s-2 增设——search_entities/describe_table 编排）。

- search_entities（TC-SEM-05 前半）：alias_norm 精确 > 前缀 + name 模糊三层
  （拼音/向量 M2-S3——G-1）；q ≤200、top_k ≤50；restricted 实体不出现
  （fail-closed——T-S9）；
- describe_table（T-S11）：只对已登记 table 实体开放（未登记 → 403——防借此
  枚举整个数仓）；透传元数据系统（3s 超时 + 5min 缓存）；不可用 → 本地轻量
  节点 + degraded=true。
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from knowledge_lattice.config import Settings
from knowledge_lattice.core.semantic.constants import SEM_ENTITY_TYPES
from knowledge_lattice.core.semantic.norm import normalize_alias

logger = logging.getLogger(__name__)

__all__ = [
    "search_entities", "describe_table", "DescribeTableDenied",
    "clear_describe_cache", "DESCRIBE_TIMEOUT_S",
]

MAX_Q_LEN = 200       # §6.3 input 契约：q ≤200
MAX_TOP_K = 50        # §6.3：top_k ≤50
DESCRIBE_TIMEOUT_S = 3.0   # T-S11：透传超时 3s
_DESCRIBE_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}

# vec 档嵌入线程池（G-24③——m2-5）：同步 httpx embedder 不阻塞调用线程外的
# 有界等待面；池小（查询侧单条嵌入，语义端点低 QPS）。core 两包互斥——
# 不复用 core/docs/retrieve._MODEL_POOL（test_sem_00_layering 守卫）。
_VEC_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lattice-semvec")


def clear_describe_cache() -> None:
    """清空透传缓存（测试隔离 / 运维强制刷新）。"""
    _DESCRIBE_CACHE.clear()


class DescribeTableDenied(PermissionError):
    """未登记的表名（403——T-S11②：防枚举数仓；非 table 实体同口径）。"""


def _audit_sem_vec_degraded(backend, org_id: str, user_id: str | None,
                            reason: str) -> None:
    """vec 档降级审计（§5.2 同源口径：search.degraded 事件——reason 一致、
    scope 标注来源端点；写失败仅告警不阻断检索——增益路语义）。"""
    try:
        backend.append_outbox(
            "search.degraded",
            json.dumps(
                {"user_id": user_id, "org_id": org_id,
                 "reasons": [reason], "scope": "search_entities"},
                ensure_ascii=False,
            ),
        )
    except Exception:  # noqa: BLE001
        logger.exception("search.degraded (search_entities) audit write failed")


def _embed_query_bounded(
    backend, settings, embedder, q: str, *, org_id: str,
    user_id: str | None, breakers: dict | None,
):
    """vec 档查询嵌入（G-24③——m2-5）：query_embed_timeout_s 有界等待 +
    breaker 计数/开路跳过 + 降级审计。失败/超时返回 None（层跳过，前三档
    照常——与 §5.2 向量路降级链同语义；此处为增益层，不阻断）。"""
    breaker = (breakers or {}).get("embed")
    if breaker is not None and not breaker.allow():
        # 熔断开路=「已确认不可达」——直接降级不等超时（NFR-8：慢与不可达
        # 由熔断区分），降级照常审计
        _audit_sem_vec_degraded(backend, org_id, user_id, "embed_unreachable")
        logger.warning("search_entities vec layer skipped: breaker open")
        return None
    future = _VEC_POOL.submit(embedder.embed, [q])
    try:
        vectors = future.result(timeout=settings.query_embed_timeout_s)
        vector = vectors[0] if vectors else None
        if vector is not None:
            if breaker is not None:
                breaker.record_success()
            return vector
        raise ValueError("search_entities vec embed returned empty vector")
    except (FutureTimeoutError, Exception) as exc:  # noqa: BLE001
        if breaker is not None:
            breaker.record_failure()
        _audit_sem_vec_degraded(backend, org_id, user_id, "embed_unreachable")
        logger.warning("search_entities vec layer degraded: %s", exc)
        return None


def search_entities(
    backend,
    org_id: str,
    q: str,
    *,
    types: list[str] | None = None,
    top_k: int = 10,
    settings=None,
    embedder=None,
    breakers: dict | None = None,
    user_id: str | None = None,
) -> dict:
    """search_entities（§6.3 契约）：entities[{id,type,key,name,brief,score,via}]。

    - 排序链（TC-SEM-05——S3/m2s-6 补齐拼音/向量）：别名精确 1.0 > 前缀
      0.8 > 拼音完全匹配 0.7 > FTS 模糊 0.5 > 向量近邻（sim——embedder
      注入且 settings 给出时启用；via='vec'）；
    - vec 档有界超时/熔断/降级审计（G-24③——m2-5）：嵌入经
      ``settings.query_embed_timeout_s`` 有界等待（非摄入侧 30s）、失败/超时
      记 ``breakers["embed"]`` 熔断计数、开路直接跳过不发调用；降级统一
      ``search.degraded`` 审计事件（reason=embed_unreachable、
      scope=search_entities——§5.2 同源口径；此前仅 warning）；
    - brief 取 curated_json.definition → attrs_json.definition →
      attrs_json.comment（一句话定义）；
    - restricted 实体不出现（fail-closed——T-S9；store 各层谓词同口径）。"""
    if not q or len(q) > MAX_Q_LEN:
        raise ValueError(f"q 长度须在 1..{MAX_Q_LEN}")
    if not (1 <= top_k <= MAX_TOP_K):
        raise ValueError(f"top_k 必须在 1..{MAX_TOP_K}（§6.3 上限）")
    if types:
        bad = set(types) - set(SEM_ENTITY_TYPES)
        if bad:
            raise ValueError(f"types 非法值 {sorted(bad)}（合法：{sorted(SEM_ENTITY_TYPES)}")

    from knowledge_lattice.core.semantic.fuzzy import pinyin_norm

    q_norm = normalize_alias(q)
    rows = backend.sem_search_entities(
        org_id, q_norm, q, types=types, top_k=top_k,
        q_pinyin=pinyin_norm(q) or None,
    )
    # 向量层（m2s-6——TC-SEM-05 第 4 档）：query 嵌入 → sem_fuzzy_terms 近邻；
    # REST/MCP 端点自 m2s-6 R2 起注入 settings/embedder（真实端点生效）；
    # 调用方缺省（core 直调/测试）时跳层——前三档语义不变
    if embedder is not None and settings is not None:
        vec = _embed_query_bounded(
            backend, settings, embedder, q, org_id=org_id, user_id=user_id,
            breakers=breakers,
        )
        if vec is not None:
            min_sim = getattr(settings, "semantic_fuzzy_vec_threshold", 0.75)
            hits = backend.sem_fuzzy_vec_search(
                org_id, vec, embed_model=settings.embed_model_label,
                top_k=top_k, min_sim=min_sim,
            )
            for hit in hits:
                if hit["sim"] < min_sim:
                    continue
                rows.append({"id": hit["entity_id"], "type": None, "key": None,
                             "name": None, "attrs_json": None,
                             "curated_json": None, "score": hit["sim"],
                             "via": "vec", "_vec": True})
    best: dict[int, dict] = {}
    for r in rows:  # 已按 score DESC 排序——首个即该实体最优档
        if r["id"] in best:
            continue
        best[r["id"]] = r
    entities = []
    id_rows = backend.sem_entities_by_ids(
        org_id, [r["id"] for r in best.values() if r.get("_vec")])
    by_id = {r["id"]: r for r in id_rows}
    for r in list(best.values())[:top_k]:
        if r.get("_vec"):
            ent = by_id.get(r["id"])
            if ent is None or ent["sensitivity"] == "restricted" \
                    or ent["status"] != "active":
                continue
            if types and ent["type"] not in set(types):
                continue
            r = {**r, "type": ent["type"], "key": ent["key"],
                 "name": ent["name"], "attrs_json": ent["attrs_json"],
                 "curated_json": ent["curated_json"]}
        curated = _loads(r["curated_json"])
        attrs = _loads(r["attrs_json"])
        brief = (curated.get("definition")
                 or attrs.get("definition") or attrs.get("comment"))
        entities.append({
            "id": r["id"], "type": r["type"], "key": r["key"],
            "name": r["name"], "brief": brief,
            "score": r["score"], "via": r["via"],
        })
    return {"entities": entities}


def describe_table(
    backend,
    settings: Settings,
    org_id: str,
    table: str,
    *,
    columns: list[str] | None = None,
    fetcher=None,
) -> dict:
    """describe_table（T-S11）：已登记 table 实体 → 元数据系统透传
    （{name, columns:[{name,type?,comment?,sample?}]}）+ degraded 标志。

    - 白名单：sem_entities 内 type='table' 的 active 实体才放行（T-S11②）；
    - 缓存 5min（settings.semantic_describe_cache_s——T-S11④，只缓存成功结果）；
    - 降级：透传异常（超时/不可达/未知表/**源未配置或配置畸形**——fetcher
      构造亦在 try 内，P1-1②/R2）→ 本地轻量列节点 + degraded=true（T-S11③
      ——不缓存降级结果，恢复后即透传）；
    - columns 参数：按列名过滤（§6.3 input）。"""
    entity = _resolve_table_entity(backend, org_id, table)

    cache_key = (org_id, entity["key"])
    now = time.monotonic()
    ttl = settings.semantic_describe_cache_s
    cached = _DESCRIBE_CACHE.get(cache_key)
    if cached and ttl > 0 and now - cached[0] < ttl:
        return _shape_describe(entity["key"], cached[1], columns, degraded=False)

    try:
        fetch = fetcher if fetcher is not None else _default_fetcher(settings, org_id)
        detail = fetch(entity["key"])
        # C.5/m2s-3：主路径列级 sensitivity 过滤——restricted 列不随透传吐出
        # （表级白名单 + 列级 restricted 集；降级路径轻量列面由
        # sem_table_columns 的 sensitivity='normal' 谓词同口径覆盖）
        restricted_cols = backend.sem_restricted_column_keys(org_id, entity["id"])
        if restricted_cols:
            prefix = entity["key"] + "."
            dropped = {
                k[len(prefix):] if k.startswith(prefix) else k
                for k in restricted_cols
            }
            detail = {
                **detail,
                "columns": [c for c in detail.get("columns") or ()
                            if c.get("name") not in dropped],
            }
        if ttl > 0:
            _DESCRIBE_CACHE[cache_key] = (now, detail)
        return _shape_describe(entity["key"], detail, columns, degraded=False)
    except Exception as exc:  # noqa: BLE001 —— 透传/构造失败一律降级（T-S11③）
        logger.warning(
            "describe_table degraded: org=%s table=%s (%s: %s)——回退本地轻量节点",
            org_id, entity["key"], type(exc).__name__, exc,
        )
        # 轻量列名 = column key 去表键前缀（与透传 columns[].name 同形）
        prefix = entity["key"] + "."
        light = {
            "name": entity["name"],
            "columns": [
                {"name": c["key"][len(prefix):] if c["key"].startswith(prefix)
                 else c["name"]}
                for c in backend.sem_table_columns(org_id, entity["id"])
            ],
        }
        return _shape_describe(entity["key"], light, columns, degraded=True)


def _resolve_table_entity(backend, org_id: str, table: str) -> dict:
    """table 实体解析：key 或数字 id（§6.3 input "table 实体的 key 或 id"）。"""
    row = None
    if table.isdigit():
        row = backend.sem_entity_by_id(org_id, int(table))
    if row is None:
        row = backend.sem_entity_by_key(org_id, "table", table)
    if (row is None or row["type"] != "table" or row["status"] != "active"
            or row["sensitivity"] == "restricted"):
        raise DescribeTableDenied(
            f"table not registered: {table!r}（describe_table 仅对已登记 table"
            " 实体开放——T-S11②）"
        )
    return row


def _default_fetcher(settings: Settings, org_id: str):
    """默认透传通道：注册工厂覆盖（duck-typed describe_table）优先，否则
    per-org 配置解析 → MetadataAdapter.describe_table（超时钳制 3s——T-S11）。

    默认分支按次构造适配器，**用后即关**（P1-1④/R2：_default_transport
    持有 httpx.Client，不关则 describe 每 5min/表泄漏一个连接池）。"""
    from knowledge_lattice.core.semantic.adapters import (
        ADAPTER_FACTORIES,
        MetadataAdapter,
        SourceConfig,
        resolve_source_config,
    )

    override = ADAPTER_FACTORIES.get("metadata")
    if override is not None:
        adapter = override(org_id, settings)
        describe = getattr(adapter, "describe_table", None)
        if callable(describe):
            return describe

    cfg = resolve_source_config(settings, org_id, "metadata")
    config = SourceConfig(
        endpoint=cfg.endpoint, api_key=cfg.api_key,
        timeout_s=min(cfg.timeout_s, DESCRIBE_TIMEOUT_S),
    )
    adapter = MetadataAdapter(config, refs=())

    def _fetch_once(table_key: str) -> dict:
        try:
            return adapter.describe_table(table_key)
        finally:
            adapter.close()

    # 钳制结果外显（T-S11① 永久断言锚——3s 上限不随配置放大）
    _fetch_once.clamped_timeout_s = config.timeout_s
    return _fetch_once


def _shape_describe(table_key: str, detail: dict, columns, *, degraded: bool) -> dict:
    cols = [
        {"name": c.get("name"),
         **({"type": c["type"]} if c.get("type") else {}),
         **({"comment": c["comment"]} if c.get("comment") else {}),
         **({"sample": str(c["sample"])} if c.get("sample") is not None else {})}
        for c in detail.get("columns") or ()
    ]
    if columns:
        wanted = set(columns)
        cols = [c for c in cols if c["name"] in wanted]
    return {"table": table_key, "name": detail.get("name"),
            "columns": cols, "degraded": degraded}


def _loads(text: str | None) -> dict:
    import json

    try:
        return json.loads(text) if text else {}
    except (TypeError, ValueError):
        return {}
