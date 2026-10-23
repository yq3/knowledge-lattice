"""Embedder provider（D12 修订——嵌入经 OpenAI 兼容 API，进程内推理取消）+ 指纹探针。

职责（design §5.3 / §3 adapters/embedder.py）：
  · 写入校验 len == config.embed_dim（不符 raise、不写库——TC-EMB-01）；
  · 启动/周期指纹探针（防网关静默换底模——G-8 两档阈值，TC-EMB-03）：
    哨兵 ≥3 条、取最小余弦判定；首部署无基线 → 探测建档放行；余弦 <0.99 告警、
    <0.95 拒绝以同标签写入 + 告警审计；基线存主库 embedding_fingerprints；
  · model_label 兼作向量召回查询谓词（chunks.embed_model——TC-EMB-02）。

分层口径：探针的持久化经 StorageBackend 协议（read/save_fingerprint、append_outbox），
本模块不碰 SQL。
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from knowledge_lattice.config import Settings


class EmbeddingDimensionError(Exception):
    """返回维度 ≠ config.embed_dim——写入前校验拦截（不写库，TC-EMB-01）。"""


class EmbeddingProbeRejected(Exception):
    """指纹探针拒绝档：拒绝以同 embed_model 标签写入（embed 阶段失败可重试——TC-EMB-03）。"""


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """批量嵌入（摄取分批 64；查询侧单条）。维度由实现保证 == config.embed_dim。"""
        ...

    @property
    def model_label(self) -> str:
        """模型标签 `model:dim`（如 qwen3-embedding-4b:2560）——D12。"""
        ...


def validate_dim(vectors: Sequence[Sequence[float]], *, expected: int) -> None:
    """写入前逐向量校验 len == expected（不符 raise——调用方不写库）。"""
    for i, v in enumerate(vectors):
        if len(v) != expected:
            raise EmbeddingDimensionError(
                f"embedding dim mismatch: got {len(v)} != config.embed_dim {expected}"
                f" (vector #{i})——拒绝写入（design §5.3 / TC-EMB-01）"
            )


class OpenAICompatEmbedder:
    """OpenAI 兼容 /embeddings 客户端（httpx——内部网关 / 本地 ollama /v1，D12）。

    M0a 基础实现：同步调用（摄取 worker 侧）；重试/熔断随 M1（NFR-8）。
    """

    def __init__(self, settings: Settings) -> None:
        import httpx

        self._settings = settings
        self._client = httpx.Client(
            base_url=settings.embed_api_base,
            headers={"Authorization": f"Bearer {settings.embed_api_key}"},
            timeout=settings.embed_timeout_s,
        )

    @property
    def model_label(self) -> str:
        return self._settings.embed_model_label

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        resp = self._client.post(
            "/embeddings",
            json={"model": self._settings.embed_model, "input": list(texts)},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        ordered = sorted(data, key=lambda d: d["index"])
        return [item["embedding"] for item in ordered]


# ============ 指纹探针（design §5.3 探针细节——v0.8，#42 P1-1） ============

# 固定哨兵（≥3 条；中英混排、含领域术语——换底模对语义敏感的文本）
SENTINELS: tuple[str, ...] = (
    "增值税一般纳税人销售货物提供应税劳务的申报口径。",
    "企业差旅费报销标准与审批流程说明。",
    "The general taxpayer shall account separately for sales of goods and services.",
)


@dataclass(frozen=True)
class ProbeResult:
    status: str  # ok | warn | reject | baselined（首部署建档放行）
    min_cosine: float | None


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class FingerprintProbe:
    """启动/周期探针：对哨兵取向量与基线比对最小余弦，两档判定。

    拒绝档语义（TC-EMB-03②）：拒绝以同标签写入（embed 阶段 raise）+ 告警审计；
    查询侧向量路开合由 EmbeddingGate 承载（M0a 检索 BM25 单路、gate 影响 notice.degraded）。
    """

    def __init__(self, backend, embedder: Embedder, settings: Settings) -> None:
        self._backend = backend
        self._embedder = embedder
        self._settings = settings

    def probe(self, *, now: str | None = None) -> ProbeResult:
        label = self._embedder.model_label
        vectors = self._embedder.embed(SENTINELS)
        validate_dim(vectors, expected=self._settings.embed_dim)
        baseline_json = self._backend.read_fingerprint(label)
        stamped = now or datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        if baseline_json is None:
            # 首部署：建档放行（≥3 哨兵入基线——存档进主库元数据表）
            self._backend.save_fingerprint(
                label,
                json.dumps(
                    [
                        {"sentinel": s, "vector": v}
                        for s, v in zip(SENTINELS, vectors)
                    ],
                    ensure_ascii=False,
                ),
            )
            return ProbeResult(status="baselined", min_cosine=None)

        baseline = json.loads(baseline_json)
        cosines = [_cosine(b["vector"], v) for b, v in zip(baseline, vectors)]
        min_cos = min(cosines)
        payload = json.dumps(
            {"embed_model": label, "min_cosine": round(min_cos, 6), "at": stamped},
            ensure_ascii=False,
        )
        if min_cos < self._settings.probe_reject_threshold:
            self._backend.append_outbox("embedding.probe_reject", payload)
            return ProbeResult(status="reject", min_cosine=min_cos)
        if min_cos < self._settings.probe_warn_threshold:
            self._backend.append_outbox("embedding.probe_warn", payload)
            return ProbeResult(status="warn", min_cosine=min_cos)
        return ProbeResult(status="ok", min_cosine=min_cos)


class EmbeddingGate:
    """探针结果的进程内状态（§2：探针在主进程跑、其结果直接开合查询侧向量路）。

    M0a：embed 写入侧（拒绝档 raise）与 notice.degraded 标注（probe_reject）
    消费本状态；向量路本体随 M1——届时检索管线按 gate 决定向量路开闭。
    """

    def __init__(self) -> None:
        self._status: str = "ok"  # ok | warn | reject

    @property
    def status(self) -> str:
        return self._status

    @property
    def rejected(self) -> bool:
        return self._status == "reject"

    def update(self, result: ProbeResult) -> None:
        if result.status == "baselined":
            self._status = "ok"
        else:
            self._status = result.status

    def ensure_writable(self) -> None:
        """embed 写入前检查：拒绝档 → 拒绝以同标签写入（可重试）。"""
        if self.rejected:
            raise EmbeddingProbeRejected(
                "embedding fingerprint probe rejected (底模疑似漂移) —— "
                "拒绝以同 embed_model 标签写入（TC-EMB-03）；换标签走重嵌入（M2）"
            )
