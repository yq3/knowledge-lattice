"""LLM 关键词增强 provider（design §5.2——800ms 硬预算、RRF 第三路 BM25 查询源）。

- `enhance(query) -> list[str]`：返回查询增强关键词（≤8 个）；
- `none`（NoopEnhancer）：不用增强路（默认——增强是增益路非可用性前提）；
- OpenAI 兼容实现：chat completions 固定 prompt、解析逗号/分号/空白分隔词条；
  超时由调用方预算窗口控制（线程池 future.result(timeout)）+ httpx 自身
  timeout 双保险（Enhancer 不自行重试——超时即丢弃，§5.2）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from knowledge_lattice.config import Settings

_MAX_TERMS = 8


@runtime_checkable
class Enhancer(Protocol):
    def enhance(self, query: str) -> list[str]:
        """查询 → 增强关键词列表（空列表＝无增强）。"""
        ...


class NoopEnhancer:
    """none 实现：不增强（返回空——retrieve 按配置跳过增强路）。"""

    def enhance(self, query: str) -> list[str]:
        return []


_ENHANCE_PROMPT = (
    "你是企业税务知识库的检索查询优化器。给定用户查询，输出最多 8 个增强检索"
    "关键词（同义业务术语、上下位词、常见缩写），只输出以逗号分隔的词，不要解释。\n"
    "查询：{query}\n关键词："
)


class OpenAICompatEnhancer:
    """OpenAI 兼容 chat completions 客户端（内部网关 / 本地 ollama——D12 同款形态）。"""

    def __init__(self, settings: Settings) -> None:
        import httpx

        self._settings = settings
        self._client = httpx.Client(
            base_url=settings.enhance_api_base,
            headers={"Authorization": f"Bearer {settings.enhance_api_key}"},
            timeout=settings.enhance_budget_s,  # httpx 层兜底（预算窗口外强杀）
        )

    def enhance(self, query: str) -> list[str]:
        resp = self._client.post(
            "/chat/completions",
            json={
                "model": self._settings.enhance_model,
                "messages": [{"role": "user", "content": _ENHANCE_PROMPT.format(query=query)}],
                "max_tokens": 128,
                "temperature": 0.0,
            },
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"] or ""
        terms: list[str] = []
        for chunk in text.replace("，", ",").replace("；", ",").replace(";", ",").split(","):
            term = chunk.strip()
            if term and term not in terms:
                terms.append(term)
        return terms[:_MAX_TERMS]
