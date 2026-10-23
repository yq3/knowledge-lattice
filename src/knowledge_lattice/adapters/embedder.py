"""Embedder provider 接口（D12 修订——嵌入经 OpenAI 兼容 API，进程内推理取消）。

职责边界（M0a-1 只钉接口，客户端随 M0a-2 摄取链实装）：
  · 写入校验 len == config.embed_dim（不符 raise、不写库——TC-EMB-01）；
  · 启动/周期指纹探针（防网关静默换底模——G-8 两档阈值，TC-EMB-03）；
  · model_label 兼作向量召回查询谓词（chunks.embed_model——TC-EMB-02）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """批量嵌入（摄取分批 64；查询侧单条）。维度由实现保证 == config.embed_dim。"""
        ...

    @property
    def model_label(self) -> str:
        """模型标签 `model:dim`（如 qwen3-embedding-4b:2560）——D12。"""
        ...
