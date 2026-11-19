"""ragas 接入桥（m3-4 D 组——#38 P2 选型落位；design §7 M3 依赖行）。

**选型结论（本模块即载体）**：

- **检索层指标维持自算**（`metrics.py` Recall@k/MRR——黄金 chunk 标注的集合
  运算、零 LLM、进本地门禁）：ragas 的检索面指标（context_precision 等）为
  LLM-judge 形态，与本项目「检索层确定性可离线卡门」的口径不匹配，不引入；
- **ragas 面向响应层**（faithfulness / answer_relevancy——TC-EVAL-03 judge
  主面）：m3-4 完成依赖引入（pyproject `eval` 依赖组——服务端默认依赖不背
  langchain 系全家桶，D2 最小依赖纪律）+ 桥本件；**m3-5 固化接入形态**
  （`response_layer_rows`→`rows_to_ragas_samples`——user_input=query /
  reference=黄金标注语料文本 / response=被评应答；真实 LLM judge 部分不进
  门禁）+ 离线确定性可运行验证（`offline_self_check`）；
- **judge 端点接口已接通**（m3-5 A 组落位）：端点形态沿 m2-5 百炼先例
  （DashScope OpenAI 兼容，``LATTICE_EVAL_LLM_*`` env 零代码切换——
  ``build_openai_compat_ragas_llm``）；双语 judge 校准（TC-EVAL-03——双语
  prompt/判读解析/一致率与 κ/材料构建）核心在 ``eval.judge``，阈值数值归
  附录 A-6（监督侧 docs 批定数）；
- **ragas 0.2.15 × langchain 0.3 系钉版**：ragas 全线（0.2~0.4）顶层 import
  ``langchain_community.chat_models.vertexai``，该模块自 langchain-community
  0.3.27 起移除而 ragas 对 langchain 系未钉版本——按最新解析必
  ModuleNotFoundError，钉 era-consistent 组合（pyproject 注记；上游修复后
  可放宽）。

本模块顶层**不 import ragas**（默认环境无 ragas 也能导入本模块——惰性
import 在工厂/自检函数内）。
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path


def build_openai_compat_ragas_llm():
    """judge/合成生成共用的 OpenAI 兼容 ragas LLM（BaseRagasLLM 实现）。

    env（沿 m2-5 百炼先例——LATTICE_* 零代码切换供应商）：
    - ``LATTICE_EVAL_LLM_API_BASE``（缺省 DashScope compatible-mode）
    - ``LATTICE_EVAL_LLM_KEY`` / fallback ``DASHSCOPE_API_KEY``
    - ``LATTICE_EVAL_LLM_MODEL``（缺省 qwen-plus）

    key 只走环境变量 / .env 运行时读取（不写死、不打印——沿
    benchmarks/calib_m2_5 形态）。**接口先行**：真实 judge 校准归 m3-5
    （TC-EVAL-03——阈值与双语 prompt 标定）。
    """
    from dataclasses import dataclass, field

    from langchain_core.outputs import Generation, LLMResult
    from ragas.llms.base import BaseRagasLLM

    def _api_key() -> str:
        root = Path(__file__).resolve().parents[3]
        for var in ("LATTICE_EVAL_LLM_KEY", "DASHSCOPE_API_KEY"):
            if os.environ.get(var):
                return os.environ[var]
        env_file = root / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                for var in ("LATTICE_EVAL_LLM_KEY", "DASHSCOPE_API_KEY"):
                    if line.startswith(f"{var}="):
                        return line.split("=", 1)[1].strip()
        raise SystemExit(
            "LATTICE_EVAL_LLM_KEY / DASHSCOPE_API_KEY 未配置——judge/生成不可用"
        )

    @dataclass
    class OpenAICompatRagasLLM(BaseRagasLLM):
        """OpenAI 兼容 chat completions 的 ragas LLM 包装（httpx 直连、零
        langchain chat 依赖；endpoint/model 经 env 零代码切换）。"""

        api_base: str = field(default="")
        api_key: str = field(default="", repr=False)
        model: str = field(default="")
        timeout_s: float = field(default=60.0)

        def _chat(self, prompt_text: str, temperature: float) -> list[str]:
            import httpx

            client = httpx.Client(
                base_url=self.api_base,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout_s,
            )
            try:
                resp = client.post(
                    "/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt_text}],
                        "temperature": temperature,
                        "max_tokens": 2048,
                    },
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"] or ""
                return [text]
            finally:
                client.close()

        def generate_text(self, prompt, n=1, temperature=1e-8, stop=None,
                          callbacks=None):
            texts = self._chat(prompt.to_string(), temperature=max(temperature, 0.0))
            return LLMResult(
                generations=[[Generation(text=t)] for t in texts][: max(n, 1)]
            )

        async def agenerate_text(self, prompt, n=1, temperature=None, stop=None,
                                 callbacks=None):
            return self.generate_text(
                prompt, n=n,
                temperature=temperature if temperature is not None else 1e-8,
            )

    return OpenAICompatRagasLLM(
        api_base=os.environ.get(
            "LATTICE_EVAL_LLM_API_BASE",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        api_key=_api_key(),
        model=os.environ.get("LATTICE_EVAL_LLM_MODEL", "qwen-plus"),
    )


def response_layer_rows(
    report: dict, golden: Sequence, texts: dict[str, str],
    responses: dict[str, str] | None = None,
) -> list[dict]:
    """响应层评测输入行（m3-5 B 组接入形态——纯 python、门禁可测）。

    ``user_input``=query 文本、``retrieved_contexts``=命中序语料文本
    （坐标 → 文本解析）、``reference``=黄金标注语料文本（多标注换行拼接
    ——judge 对照面）、``response``=被评应答（``responses[qid]``，缺省
    None——真实 LLM 指标运行时由 ragas 校验必填面）。元数据 qid/lang 保留
    （judge 材料/校准对账键）。

    语料键悬空（report/golden 引用语料外 doc）→ ValueError fail-fast
    （防静默空 context）。reference 的 chunk 边界近似口径：语料全文
    （单 chunk 文档为主——与 judge 材料同口径，如实登记）。
    """
    responses = responses or {}
    by_qid = {c.qid: c for c in golden}
    rows: list[dict] = []
    for q in report.get("per_query", []):
        case = by_qid.get(q["qid"])
        if case is None:
            raise ValueError(f"report qid {q['qid']!r} 不在 golden（数据漂移？）")
        for doc, _seq in case.labels:
            if doc not in texts:
                raise ValueError(
                    f"{q['qid']} 黄金标注语料键悬空：{doc!r}（语料/切分漂移）")
        for doc, _seq in q.get("hits", []):
            if doc not in texts:
                raise ValueError(
                    f"{q['qid']} 命中语料键悬空：{doc!r}（语料漂移）")
        label_docs = list(dict.fromkeys(doc for doc, _ in case.labels))
        rows.append({
            "qid": q["qid"],
            "lang": case.lang,
            "user_input": case.query,
            "response": responses.get(q["qid"]),
            "retrieved_contexts": [texts[doc] for doc, _ in q.get("hits", [])],
            "reference": "\n".join(texts[doc] for doc in label_docs),
        })
    return rows


def rows_to_ragas_samples(rows: list[dict]) -> "list":
    """响应层输入行 → ragas SingleTurnSample（惰性 ragas import——默认
    环境零 ragas 也可导入本模块；字段面 faithfulness/answer_relevancy 直用）。"""
    from ragas.dataset_schema import SingleTurnSample

    return [
        SingleTurnSample(
            user_input=r["user_input"],
            response=r["response"],
            retrieved_contexts=list(r["retrieved_contexts"]),
            reference=r["reference"],
        )
        for r in rows
    ]


def retrieval_report_to_samples(report: dict, golden: Sequence,
                                texts: dict[str, str]) -> "list":
    """检索层报告 + 黄金集 + 语料文本 → ragas SingleTurnSample（响应层输入）。

    m3-5 P3-6 清偿：原签名只收 report，但 per_query 仅 qid/hits——docstring
    承诺的 user_input=query / reference=黄金标注无法兑现（误导陷阱）。现签名
    显式接收 golden 与 texts（语料键 → 文本），语义即 ``response_layer_rows``
    docstring（user_input=query 文本、reference=黄金标注语料文本、
    retrieved_contexts=命中序文本）；response 由调用方经 ``responses`` 注入
    （被评对象=增强器/agent 应答——见 ``response_layer_rows``）。
    """
    return rows_to_ragas_samples(response_layer_rows(report, golden, texts))


def offline_self_check() -> dict:
    """离线确定性自检（D 组「可运行验证」——零 LLM、零网络）。

    用 ragas 非 LLM 指标（``NonLLMStringSimilarity``/``StringPresence``）经
    ``ragas.evaluate`` 全链跑通——证明 ragas 依赖引入完整可运行（指标注册、
    数据集 schema、evaluate 管线）；LLM-judge 面（faithfulness 等）为 m3-5
    主面，本自检不含（接口见 ``build_openai_compat_ragas_llm``）。
    """
    from ragas import evaluate
    from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
    from ragas.metrics import NonLLMStringSimilarity, StringPresence

    samples = [
        SingleTurnSample(response="留抵退税按月申请", reference="留抵退税按月申请"),
        SingleTurnSample(response="完全无关的文本", reference="留抵退税按月申请"),
    ]
    result = evaluate(
        EvaluationDataset(samples),
        [NonLLMStringSimilarity(), StringPresence()],
        show_progress=False,
    )
    scores = result.to_pandas().to_dict("list")
    # 确定性断言：同串=1.0、异串=0.0（字符串包含同理）
    assert scores["non_llm_string_similarity"] == [1.0, 0.0], scores
    assert scores["string_present"] == [1.0, 0.0], scores
    return scores


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ragas 接入桥（m3-4 D 组）")
    parser.add_argument("--self-check", action="store_true",
                        help="离线确定性自检（ragas 非 LLM 指标全链——零网络）")
    args = parser.parse_args()
    if args.self_check:
        print("ragas offline self-check:", offline_self_check())
    else:
        parser.print_help()
