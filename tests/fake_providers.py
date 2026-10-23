"""共享 fake provider fixture（TEST-CASES 口径段 v1.4——TC-EMB 组/TC-RET 降级/TC-ACL-08 共享）。

Embedder 假实现统一形态：
① 确定性向量（按文本 hash 种子，同文本同向量）；
② 可注入延迟与失败（超时 / 不可达）；
③ 换底模模式（`drift`：哨兵文本返回偏移向量——探针用例专用，TC-EMB-03）；
（Reranker none 实现在 adapters/reranker.NoopReranker。）
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from collections.abc import Sequence

from knowledge_lattice.adapters.embedder import SENTINELS


class FakeEmbedder:
    """确定性假嵌入器：维度/失败/延迟/drift 可注入。

    drift 两形态：
    - drift=True：哨兵文本返回强偏移向量（≈0 余弦——拒绝档，TC-EMB-03②）；
    - drift_cos=c（0<c<1）：哨兵向量与基线**精确**余弦 c（Gram-Schmidt 正交构造——
      告警档 0.95~0.99 的确定性造数，TC-EMB-03③）。
    """

    def __init__(
        self,
        *,
        dim: int = 2560,
        fail: bool = False,
        delay_s: float = 0.0,
        drift: bool = False,
        drift_cos: float | None = None,
        model_name: str = "qwen3-embedding-4b",
        return_dim: int | None = None,
    ) -> None:
        self.dim = dim
        self.fail = fail
        self.delay_s = delay_s
        self.drift = drift
        self.drift_cos = drift_cos
        self.model_name = model_name
        # return_dim：故意返回错误维度（TC-EMB-01——mock 返回 1024 ≠ config 2560）
        self.return_dim = return_dim
        self.calls: list[list[str]] = []

    @property
    def model_label(self) -> str:
        return f"{self.model_name}:{self.dim}"

    def _vector(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        rng = random.Random(seed)
        out_dim = self.return_dim if self.return_dim is not None else self.dim
        return [rng.uniform(-1.0, 1.0) for _ in range(out_dim)]

    def _exact_cos_drifted(self, text: str, cos: float) -> list[float]:
        """与基线向量精确余弦 cos 的哨兵向量：c·b̂ + √(1-c²)·e（e 与 b̂ 正交）。"""
        base = self._vector(text)
        norm = math.sqrt(sum(x * x for x in base)) or 1.0
        b_hat = [x / norm for x in base]
        seed = hashlib.sha256((text + "::drift").encode("utf-8")).digest()
        rng = random.Random(seed)
        noise = [rng.uniform(-1.0, 1.0) for _ in base]
        nb = sum(n * bh for n, bh in zip(noise, b_hat))
        orth = [n - nb * bh for n, bh in zip(noise, b_hat)]  # Gram-Schmidt 去共线分量
        on = math.sqrt(sum(x * x for x in orth)) or 1.0
        s = math.sqrt(1.0 - cos * cos)
        return [cos * bh + s * (x / on) for bh, x in zip(b_hat, orth)]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.fail:
            raise ConnectionError("embedding endpoint unreachable (fake)")
        if self.drift_cos is not None:
            return [
                self._exact_cos_drifted(t, self.drift_cos) if t in SENTINELS
                else self._vector(t)
                for t in texts
            ]
        if self.drift:
            return [
                self._exact_cos_drifted(t, 0.0) if t in SENTINELS else self._vector(t)
                for t in texts
            ]
        return [self._vector(t) for t in texts]
