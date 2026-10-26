"""区分度检测与反馈环（design §5.4——core/docs/quality.py，FR-3 用户拍板进 MVP）。

两路信号、零 LLM 成本（检测层）：
- **向量拥挤度**：块向量在「组织内 + 仅在用版本」（tombstone=0 AND
  version=active——#33 P1-10，否则新旧版本互为拥挤近邻制造误报）的 top-N
  近邻 mean(sim) > **绝对阈值**（初值见 config，真实语料重标定随 M1-5）。
  入库单块走 SQL 暴力扫描（backend.neighbor_sims——量小）；
- **词面通用度**：token 平均 IDF < 绝对阈值；**新组织冷启动引用全局语料 IDF**
  （组织在用块数 < quality_cold_start_min 时不因组织语料为空而误判，TC-QUAL-02）。

批量重算（TC-QUAL-04）：候选 = `detected_at_scale IS NULL OR < 当前规模×比例`
∪ 确定性抽样（rid 散列 %100 < sample_percent）；拥挤度批量走 **numpy 分块矩阵
乘**（§5.4 v0.4 更正——10 万×2560 维分钟级可行，真正慢的是 SQL 标量逐行）、
词面通用度走 content_seg 流式 df 统计；重算前清旧 open 标记（覆盖语义）。

LLM 兜底（TC-QUAL-03）：对 open flags 生成关键词写 **`llm_keywords` 独立低权列**
（×0.5~1）+ 一句定位语进 `auto_keywords`；**不动** `keywords`（人工列）与
embedding（口径如实——非 Contextual Retrieval）。provider 缺省 none（不发起调用）。

报告页防旁路（TC-QUAL-05 / T18）：`quality_flags.detail_json` 的近邻信息展示时
**过同一套 ACL**（compile_acl + visible_chunk_ids——不可见近邻整体不出现在响应，
原始 detail_json 不因报告页而改写）。

误报抽查机制（M1.7 验收句的记录形态）：`sample_open_flags` 确定性抽样 open flags
供人工复核；复核结论经 patch_flag 落 state（resolved=误报处置 / ignored=接受通用）
+ manual_tags 审计轨迹——阈值校准实验本身属 M1-5，不在本模块。

分层纪律：SQL 全部经 StorageBackend Quality 域；LLM 经注入的 KeywordGenerator
协议（adapters/enhancer.py 提供 OpenAI 兼容实现与 noop）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from knowledge_lattice.config import Settings
from knowledge_lattice.core.docs.acl import compile_acl

__all__ = [
    "QualityFlagNotFoundError",
    "QualityPermissionError",
    "MojibakeQualityError",
    "KeywordGenerator",
    "NoopKeywordGenerator",
    "QualityService",
    "normal_char_ratio",
    "mojibake_tier",
]

logger = logging.getLogger(__name__)


class QualityFlagNotFoundError(Exception):
    """flag 不存在或跨组织（404 语义——存在性敏感）。"""


class QualityPermissionError(Exception):
    """人工补标/状态迁移操作权限缺失（403 语义——owner/org_admin 操作矩阵）。"""


class MojibakeQualityError(Exception):
    """mojibake 质量门失败档（<0.40）——parse 阶段 raise → 任务 failed（§5.4 三档）。"""


# ============ mojibake 质量门（§5.4 OneRAG 借鉴项——TC-ING-05 三档） ============
# 判分原语下沉 adapters/textutil.py（R2 分层修正：parser 编码择优与本门共用，
# core→adapters 为既有合法方向）；本模块 re-export 维持既有 import 面稳定。

from knowledge_lattice.adapters.textutil import (  # noqa: F401 —— re-export
    MOJIBAKE_FAIL,
    MOJIBAKE_WARN,
    normal_char_ratio,
)


def mojibake_tier(text: str) -> tuple[str, float]:
    """三档判定（TC-ING-05）：('pass' | 'warn' | 'fail', ratio)。

    - pass：ratio ≥ 0.55 正常通过；
    - warn：0.40 ≤ ratio < 0.55 告警（TXT 解码重试下一候选编码——parser 层）；
    - fail：ratio < 0.40 失败（MojibakeQualityError 由摄取阶段抛出）。
    """
    ratio = normal_char_ratio(text)
    if ratio >= MOJIBAKE_WARN:
        return "pass", ratio
    if ratio >= MOJIBAKE_FAIL:
        return "warn", ratio
    return "fail", ratio


# ============ LLM 兜底 provider 协议（实现：adapters/enhancer.py） ============


@runtime_checkable
class KeywordGenerator(Protocol):
    def generate(self, content: str) -> tuple[list[str], str]:
        """chunk 内容 → (关键词列表, 一句定位语)。"""
        ...


class NoopKeywordGenerator:
    """none 档：不生成（quality_llm=none——LLM 兜底关闭，测试/无网关环境）。"""

    def generate(self, content: str) -> tuple[list[str], str]:
        return [], ""


# ============ 服务 ============


class QualityService:
    """区分度检测 / LLM 兜底 / 批量重算 / 报告（ACL 过滤）/ 人工补标。"""

    def __init__(
        self,
        backend,
        settings: Settings,
        *,
        keyword_client: KeywordGenerator | None = None,
    ) -> None:
        self._backend = backend
        self._settings = settings
        self._keywords = keyword_client or NoopKeywordGenerator()

    # ---- 检测路径（入库单块——SQL 暴力扫描） ----

    def _idf_stats(
        self, tokens: Sequence[str], org_id: str
    ) -> tuple[float | None, str, int]:
        """token 平均 IDF（nats）。返回 (avg_idf, scope, N)。

        冷启动（组织在用块数 < quality_cold_start_min）→ 全局语料统计
        （TC-QUAL-02——不因组织语料为空而误判）；tokens 为空 → (None, …)。
        """
        org_n = self._backend.org_active_chunk_count(org_id)
        if org_n < self._settings.quality_cold_start_min:
            scope, n = None, self._backend.org_active_chunk_count(None)
        else:
            scope, n = org_id, org_n
        if not tokens:
            return None, ("global" if scope is None else "org"), n
        df = self._backend.token_doc_frequency(tokens, scope)
        # 未见 token 按 df=1 计（稀有=高 IDF——推高均值、降低误报）
        idfs = [math.log(max(n, 1) / max(df.get(tok, 0), 1)) for tok in tokens]
        return (
            sum(idfs) / len(idfs),
            ("global" if scope is None else "org"),
            n,
        )

    def detect_chunk(
        self, rid: int, *, embed_model: str | None = None
    ) -> dict | None:
        """单块两路检测（入库路径）：拥挤 + 词面通用度 → 写 flags + 检测标记。

        返回 {rid, reason, mean_sim, avg_idf}（reason=None 表示未命中——无 flag）；
        块无向量（未嵌入/标签不符）时跳过拥挤路（仅词面路）。
        """
        label = embed_model or self._settings.embed_model_label
        rows = self._backend.chunks_by_rids([rid])
        if not rows:
            raise KeyError(f"chunk rid not found: {rid}")
        chunk = rows[0]
        org_id = self._backend.get_document(chunk["doc_id"])["org_id"]

        neighbors = self._backend.neighbor_sims(
            rid, label, top_k=self._settings.quality_neighbors
        )
        mean_sim = (
            sum(n["sim"] for n in neighbors) / len(neighbors) if neighbors else None
        )
        crowded = (
            mean_sim is not None
            and mean_sim > self._settings.quality_crowding_threshold
        )

        tokens = (chunk.get("content_seg") or "").split()
        avg_idf, idf_scope, _n = self._idf_stats(tokens, org_id)
        generic = (
            avg_idf is not None and avg_idf < self._settings.quality_low_idf_threshold
        )

        reason = (
            "both" if crowded and generic
            else "vector_crowding" if crowded
            else "low_idf" if generic
            else None
        )
        detail: dict = {"idf_scope": idf_scope}
        if mean_sim is not None:
            detail["mean_sim"] = round(mean_sim, 6)
            detail["neighbors"] = [
                {
                    "rid": n["rid"],
                    "chunk_id": n["chunk_id"],
                    "doc_id": n["doc_id"],
                    "sim": round(n["sim"], 6),
                }
                for n in neighbors
            ]
        if avg_idf is not None:
            detail["avg_idf"] = round(avg_idf, 6)
        flag_id = None
        if reason is not None:
            flag_id = self._backend.insert_quality_flag(
                chunk_id=chunk["chunk_id"],
                doc_id=chunk["doc_id"],
                reason=reason,
                detail_json=json.dumps(detail, ensure_ascii=False),
            )
        # 检测标记：语料规模（org 口径）+ 内容指纹（缓存键随 embed_model 语义——
        # 换模型重嵌入由重算路径覆盖，#42 P1-3）
        self._backend.set_chunk_quality_marks(
            [(rid, "sha256:" + hashlib.sha256(chunk["content"].encode()).hexdigest())],
            scale=self._backend.org_active_chunk_count(org_id),
        )
        logger.info(
            "quality detect rid=%s reason=%s mean_sim=%s avg_idf=%s",
            rid, reason,
            None if mean_sim is None else round(mean_sim, 4),
            None if avg_idf is None else round(avg_idf, 4),
        )
        return {
            "rid": rid, "reason": reason, "flag_id": flag_id,
            "mean_sim": mean_sim, "avg_idf": avg_idf,
        }

    def detect_document(self, doc_id: str, *, org_id: str) -> list[dict]:
        """文档在用版本未检测块的检测入口（摄取管线 quality 阶段调用——
        检测失败不回退 searchable_full，由调用方 best-effort 捕获）。"""
        current = self._backend.org_active_chunk_count(org_id)
        candidates = self._backend.chunks_for_quality_recompute(
            org_id, current_scale=current, rescale_ratio=0.0, sample_percent=0
        )
        return [
            self.detect_chunk(c["rid"])
            for c in candidates
            if c["doc_id"] == doc_id
        ]

    # ---- LLM 兜底（TC-QUAL-03） ----

    def run_llm_keywords(self, *, org_id: str | None = None, doc_id: str | None = None) -> int:
        """open flags → LLM 关键词写 llm_keywords + 定位语写 auto_keywords。

        - **块正文取自 chunks 表**（chunks_by_rids——flag 行不含 content；P1-1：
          R1 误读 flag.get("content") 恒空串直传 provider）；**空内容块跳过**
          （不发起调用）；
        - **terms 为空不写 llm_keywords**（防空串清空既有值——半产出〔只回
          定位语〕仅写 auto_keywords）；
        - noop provider（quality_llm=none）不发起任何调用、返回 0（早返回零成本
          ——P2-2：quality 阶段摄取后自动接入）；
        - doc_id 限定文档作用域（quality 阶段入口）；生成失败单块跳过（告警
          日志——兜底失败不阻断，可重跑）。
        """
        if isinstance(self._keywords, NoopKeywordGenerator):
            return 0
        flags = self._backend.list_quality_flags(
            doc_id=doc_id, org_id=org_id, state="open"
        )
        done = 0
        for flag in flags:
            chunk = self._backend.get_chunk(flag["chunk_id"])
            if chunk is None:
                continue
            rows = self._backend.chunks_by_rids([chunk["rid"]])
            content = rows[0]["content"] if rows else ""
            if not content.strip():
                continue  # 空内容块跳过（P1-1——不发起 provider 调用）
            try:
                terms, locator = self._keywords.generate(content)
            except Exception:  # noqa: BLE001 —— 单块失败跳过、不阻断批次
                logger.exception("llm keyword generation failed: %s", flag["id"])
                continue
            if not terms and not locator:
                continue
            if terms:  # P1-1：空 terms 不写（防空串清空既有 llm_keywords）
                self._backend.set_chunk_llm_keywords(chunk["rid"], " ".join(terms))
            self._backend.set_quality_auto_keywords(flag["id"], locator)
            done += 1
        if done:
            self._backend.append_outbox(
                "quality.llm_keywords",
                json.dumps(
                    {"org_id": org_id, "doc_id": doc_id, "count": done},
                    ensure_ascii=False,
                ),
            )
        return done

    # ---- 批量重算（TC-QUAL-04——numpy 分块矩阵乘 + 流式 df） ----

    def recompute(self, org_id: str) -> dict:
        """规模比例 + 抽样重算。返回 {candidates, flagged, cleared, current_scale}。

        拥挤度：组织内全部在用块向量载入 numpy（float32 归一化），分块矩阵乘取
        候选行 top-N 近邻均值（非 SQL 标量逐行——§5.4 v0.4 更正）。

        词面通用度冷启动（P2-1，R2）：组织在用块数 < quality_cold_start_min 时
        **df 统计切全局语料**（org_active_chunk_segs(None)——与 detect_chunk 的
        _idf_stats 同构口径：小组织自身 IDF 无判别语义，不因组织语料为空而
        误判/漏判）；detail.idf_scope 如实记录 org|global。
        """
        import numpy as np

        settings = self._settings
        label = settings.embed_model_label
        current = self._backend.org_active_chunk_count(org_id)
        candidates = self._backend.chunks_for_quality_recompute(
            org_id,
            current_scale=current,
            rescale_ratio=settings.quality_rescale_ratio,
            sample_percent=settings.quality_sample_percent,
        )
        result = {
            "candidates": len(candidates), "flagged": 0, "cleared": 0,
            "current_scale": current,
        }
        if not candidates:
            return result

        # 拥挤度批量：numpy 归一化 + 分块矩阵乘（候选行 × 全体近邻池）
        mean_topk = self._crowding_means(np, org_id, label, [c["rid"] for c in candidates])

        # 词面通用度批量：content_seg 流式 df 统计（一次载入统计，非逐块 SQL）；
        # 冷启动（P2-1）——组织块数不足时切全局语料统计
        idf_scope = "org"
        segs_org = settings.quality_cold_start_min
        if current < segs_org:
            idf_scope = "global"
            segs = self._backend.org_active_chunk_segs(None)
        else:
            segs = self._backend.org_active_chunk_segs(org_id)
        n_corpus = len(segs)
        df: dict[str, int] = {}
        for seg in segs:
            for tok in set(seg.split()):
                df[tok] = df.get(tok, 0) + 1

        cand_rids = [c["rid"] for c in candidates]
        cleared = self._backend.delete_open_flags(
            cand_rids, ["vector_crowding", "low_idf", "both"]
        )
        marks: list[tuple[int, str | None]] = []
        flagged = 0
        for c in candidates:
            mean_sim = mean_topk.get(c["rid"])
            crowded = (
                mean_sim is not None
                and mean_sim > settings.quality_crowding_threshold
            )
            tokens = (c["content_seg"] or "").split()
            avg_idf = None
            if tokens:
                idfs = [
                    math.log(max(n_corpus, 1) / max(df.get(tok, 0), 1))
                    for tok in tokens
                ]
                avg_idf = sum(idfs) / len(idfs)
            generic = (
                avg_idf is not None
                and avg_idf < settings.quality_low_idf_threshold
            )
            reason = (
                "both" if crowded and generic
                else "vector_crowding" if crowded
                else "low_idf" if generic
                else None
            )
            if reason is not None:
                detail: dict = {"idf_scope": idf_scope, "recomputed": True}
                if mean_sim is not None:
                    detail["mean_sim"] = round(mean_sim, 6)
                if avg_idf is not None:
                    detail["avg_idf"] = round(avg_idf, 6)
                self._backend.insert_quality_flag(
                    chunk_id=c["chunk_id"], doc_id=c["doc_id"],
                    reason=reason, detail_json=json.dumps(detail, ensure_ascii=False),
                )
                flagged += 1
            marks.append(
                (c["rid"], "sha256:" + hashlib.sha256(c["content"].encode()).hexdigest())
            )
        self._backend.set_chunk_quality_marks(marks, scale=current)
        result["flagged"] = flagged
        result["cleared"] = cleared
        logger.info("quality recompute org=%s %s", org_id, result)
        return result

    # 流式分块参数（M1-4 P2-4 / M1-5 改造）：池块宽 / sims 分块行宽
    # （sims 峰值 = 8192×4096 float32 ≈ 128MB；候选驻留矩阵 = n_cand×dim×4B
    # ——抽样档 ~50MB / 全量重算 100k 档 ≈1GB 单块 ndarray，§5.4「载入 numpy」同口径）
    _CROWDING_POOL_BLOCK = 4096
    _CROWDING_SIM_ROWS = 8192

    def _crowding_means(self, np, org_id: str, label: str, cand_rids: Sequence[int]) -> dict[int, float]:
        """候选行 top-N 近邻均值（**流式池 + 候选驻留 + running top-k**——M1-4
        P2-4 / M1-5 改造）。

        近邻池 = 组织内全部在用块向量，经 org_active_chunk_vectors **两次惰性流**
        （packed bytes，不物化 Python float 对象——100k×2560 档 >1GB 根因消除）：
        ① 取候选行 → 驻留 float32 矩阵（归一化一次）+ 顺带数出池规模；
        ② 池分块流过（单遍）：块归一化 → 与候选驻留矩阵分块乘 → running top-k
        （concat+partition，自身按 rid 定位置 -1 排除——与全行扫描语义等价）。
        峰值私有内存 ≈ 候选矩阵 + sims 块 + 池块（实测见
        benchmarks/report-m1-5.md §4）。"""
        cand_set = set(cand_rids)
        cand_packed: dict[int, bytes] = {}
        dim = 0
        pool_n = 0
        for rid, packed in self._backend.org_active_chunk_vectors(org_id, label):
            if not packed:
                continue
            pool_n += 1
            if rid in cand_set:
                d = len(packed) // 4
                if dim == 0:
                    dim = d
                elif d != dim:
                    continue  # 维度异行防御跳过（蓝绿共窗不混算——标签谓词已滤）
                cand_packed[rid] = packed
        if pool_n < 2 or not cand_packed or dim == 0:
            return {}
        kept = [r for r in cand_rids if r in cand_packed]
        cand_mat = np.empty((len(kept), dim), dtype=np.float32)
        for i, rid in enumerate(kept):  # pop 逐行腾挪——峰值 ≈ 单份候选数据
            cand_mat[i] = np.frombuffer(cand_packed.pop(rid), dtype=np.float32)
        norms = np.linalg.norm(cand_mat, axis=1, keepdims=True)
        cand_mat = cand_mat / np.clip(norms, 1e-12, None)
        cand_pos = {rid: i for i, rid in enumerate(kept)}

        k = min(self._settings.quality_neighbors, pool_n - 1)
        if k <= 0:
            return {}
        topk = np.full((len(kept), k), -2.0, dtype=np.float32)
        sim_rows = self._CROWDING_SIM_ROWS
        pblock = self._CROWDING_POOL_BLOCK
        for block_rids, block_mat in self._pool_blocks(np, org_id, label, pblock):
            for cstart in range(0, len(kept), sim_rows):  # sims 分块（内存上界）
                sims = cand_mat[cstart : cstart + sim_rows] @ block_mat.T
                for j, rid in enumerate(block_rids):  # 自身排除（rid 定位——与流序无关）
                    ci = cand_pos.get(rid)
                    if ci is not None and cstart <= ci < cstart + sim_rows:
                        sims[ci - cstart, j] = np.float32(-1.0)
                merged = np.concatenate([topk[cstart : cstart + sim_rows], sims], axis=1)
                topk[cstart : cstart + sim_rows] = np.partition(
                    merged, merged.shape[1] - k, axis=1
                )[:, -k:]
        return {rid: float(topk[i].mean()) for i, rid in enumerate(kept)}

    def _pool_blocks(self, np, org_id: str, label: str, block_n: int):
        """池流 → (rid 列表, 归一化 float32 块) 生成器（块用即弃——峰值 = 单块）。"""
        buf_rids: list[int] = []
        buf: list[bytes] = []
        for rid, packed in self._backend.org_active_chunk_vectors(org_id, label):
            if not packed:
                continue
            buf_rids.append(rid)
            buf.append(packed)
            if len(buf_rids) == block_n:
                yield self._normalized_block(np, buf_rids, buf)
                buf_rids, buf = [], []
        if buf_rids:
            yield self._normalized_block(np, buf_rids, buf)

    @staticmethod
    def _normalized_block(np, rids: list[int], packed: list[bytes]):
        dim = len(packed[0]) // 4
        mat = np.empty((len(rids), dim), dtype=np.float32)
        for i, row in enumerate(packed):
            mat[i] = np.frombuffer(row, dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        return rids, mat / np.clip(norms, 1e-12, None)

    # ---- 报告页（TC-QUAL-05——近邻过同一套 ACL） ----

    def quality_report(self, doc_id: str, *, user_id: str, org_id: str) -> dict:
        """文档质量报告明细：flags + 近邻内容**过请求者 ACL**（不可见近邻整体剔除；
        detail_json 原始存储不改写——展示层过滤，T18）。"""
        plan = compile_acl(self._backend, user_id, org_id)
        flags = self._backend.list_quality_flags(doc_id)
        parsed = []
        all_neighbor_rids: list[int] = []
        for flag in flags:
            detail = json.loads(flag["detail_json"]) if flag["detail_json"] else {}
            all_neighbor_rids.extend(n["rid"] for n in detail.get("neighbors", []))
        visible = (
            self._backend.visible_chunk_ids(plan, sorted(set(all_neighbor_rids)))
            if all_neighbor_rids
            else set()
        )
        contents = {
            c["rid"]: c
            for c in self._backend.chunks_by_rids(sorted(visible))
        } if visible else {}
        open_count = 0
        for flag in flags:
            detail = json.loads(flag["detail_json"]) if flag["detail_json"] else {}
            if flag["state"] == "open":
                open_count += 1
            neighbors = [
                {
                    "chunk_id": contents[n["rid"]]["chunk_id"],
                    "doc_id": n["doc_id"],
                    "sim": n["sim"],
                    "snippet": (contents[n["rid"]]["content"] or "")[:120],
                }
                for n in detail.get("neighbors", [])
                if n["rid"] in visible  # 不可见近邻不出现（过同一套 ACL——T18）
            ]
            parsed.append(
                {
                    "flag_id": flag["id"],
                    "chunk_id": flag["chunk_id"],
                    "reason": flag["reason"],
                    "state": flag["state"],
                    "mean_sim": detail.get("mean_sim"),
                    "avg_idf": detail.get("avg_idf"),
                    "neighbors": neighbors,
                    "auto_keywords": flag["auto_keywords"],
                    "manual_tags": flag["manual_tags"],
                    "created_at": flag["created_at"],
                }
            )
        return {
            "doc_id": doc_id,
            "flags": parsed,
            "open_count": open_count,
            "suggest_annotation": open_count,  # 上传完成页聚合提示（FR-3）
        }

    # ---- 误报抽查（M1.7 记录形态——确定性抽样供人工复核） ----

    def sample_open_flags(
        self, org_id: str, *, n: int = 20, seed: str = "m1"
    ) -> list[dict]:
        """open flags 确定性抽样（sha256(seed:flag_id) 排序取前 n）——复核结论经
        patch_flag 落 state + manual_tags（审计轨迹）。"""
        flags = self._backend.list_quality_flags(org_id=org_id, state="open")
        ordered = sorted(
            flags,
            key=lambda f: hashlib.sha256(f"{seed}:{f['id']}".encode()).hexdigest(),
        )
        out = []
        for flag in ordered[:n]:
            detail = json.loads(flag["detail_json"]) if flag["detail_json"] else {}
            out.append(
                {
                    "flag_id": flag["id"],
                    "chunk_id": flag["chunk_id"],
                    "doc_id": flag["doc_id"],
                    "reason": flag["reason"],
                    "mean_sim": detail.get("mean_sim"),
                    "avg_idf": detail.get("avg_idf"),
                }
            )
        return out

    # ---- 人工补标与状态迁移（PATCH /api/quality-flags/{id} 载体） ----

    def patch_flag(
        self,
        flag_id: str,
        *,
        org_id: str,
        actor_user_id: str,
        keywords: str | None = None,
        tags: str | None = None,
        state: str | None = None,
    ) -> dict:
        """人工补标（keywords/tags → chunks 人工列，原样写入不进 jieba——TC-FTS-04）
        与 state 迁移（open|resolved|ignored）。

        权限：owner 或 org_admin（FR-4 操作矩阵——管理写）；跨组织 flag 404；
        管理动作入 outbox 审计。
        """
        flag = self._backend.get_quality_flag(flag_id)
        if flag is None:
            raise QualityFlagNotFoundError(f"quality flag not found: {flag_id!r}")
        doc = self._backend.get_document(flag["doc_id"])
        if doc is None or doc["org_id"] != org_id:
            raise QualityFlagNotFoundError(f"quality flag not found: {flag_id!r}")
        if doc["owner_user_id"] != actor_user_id:
            membership = self._backend.read_membership(actor_user_id, org_id)
            if membership is None or membership["role"] != "org_admin":
                raise QualityPermissionError(
                    f"operation not permitted: {actor_user_id!r} is neither owner"
                    " nor org_admin"
                )

        chunk_cols: dict | None = None
        touched: list[str] = []
        if keywords or tags:
            chunk = self._backend.get_chunk(flag["chunk_id"])
            if chunk is None:
                raise QualityFlagNotFoundError(
                    f"chunk gone for flag: {flag['chunk_id']!r}"
                )
            chunk_cols = self._backend.append_chunk_manual_terms(
                chunk["rid"],
                keywords=keywords or "",
                tags=tags or "",
            )
            self._backend.append_quality_manual_tags(
                flag_id,
                json.dumps(
                    {
                        "actor": actor_user_id,
                        "at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                        "keywords": keywords,
                        "tags": tags,
                    },
                    ensure_ascii=False,
                ),
            )
            touched.append("manual_terms")
        if state is not None and state != flag["state"]:
            if state not in ("open", "resolved", "ignored"):
                raise ValueError(f"invalid state: {state!r}")
            self._backend.set_quality_flag_state(flag_id, state)
            touched.append("state")

        self._backend.append_outbox(
            "quality_flag.patch",
            json.dumps(
                {
                    "flag_id": flag_id,
                    "org_id": org_id,
                    "actor": actor_user_id,
                    "keywords": keywords,
                    "tags": tags,
                    "state": state,
                },
                ensure_ascii=False,
            ),
        )
        fresh = self._backend.get_quality_flag(flag_id)
        return {
            "flag_id": flag_id,
            "chunk_id": flag["chunk_id"],
            "state": fresh["state"],
            "keywords": (chunk_cols or {}).get("keywords"),
            "tags": (chunk_cols or {}).get("tags"),
            "manual_tags": fresh["manual_tags"],
            "touched": touched,
        }
