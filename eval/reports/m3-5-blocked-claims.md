# m3-5 受阻申报（TC-EVAL-03 judge 联调 / TC-EVAL-02 LLM 候选复跑 / 响应层真实 LLM 基线）

- 申报时间：2026-11-10（m3-5 R1）。沿 m2-5（report-m2-5-blocked.md）/m3-4
  （labeling-notes.md m3-4 节）受阻申报先例：**材料与复跑路径写明、如实登记
  不冒充**。
- 端点：DashScope compatible-mode（沿 m2-5 百炼先例——用户裁定 2026-11-10；
  `LATTICE_EVAL_LLM_*` env 零代码切换），本 key 当日状态：

| 模型面 | 状态 |
|---|---|
| chat：qwen-plus / qwen-flash / qwen-max | **403 Free quota exhausted** |
| chat：qwen-turbo | **429 limit_requests**（持续限流） |
| chat：qwen3-max | 404 model_not_exist |
| embeddings：text-embedding-v4 | ✅ 可用（D 组 MRL 复测即真实调用——见 benchmarks/report-m3-5-g8-mrl-fullset.md） |

与 m3-4（2026-11-08）申报同形态：chat 免费配额耗尽、embeddings 配额独立可用。

## A 组：TC-EVAL-03 judge 校准——真实 judge 联调受阻

- **已交付（不受阻面）**：双语 judge 校准框架全量（`src/knowledge_lattice/
  eval/judge.py`——三态双语 prompt/判读解析/一致率与 Cohen's κ/校准报告；
  门禁确定性用例 `tests/test_eval_judge_m35.py`）+ **50 条人工双评材料与
  格式**（`eval/reports/judge-materials-m35.jsonl` + 标注回流模板
  `judge-human-answersheet-m35.jsonl`——构建确定性 seed=20261110，三态
  20/15/15、构造 faithful 25/unfaithful 25）+ 联调脚本（`scripts/
  eval_judge_m35.py --run-judge/--calibrate`——端点就绪即可跑）。
- **受阻面**：`--run-judge`（真实 LLM 对 50 条材料出判定）与 judge vs 人工
  一致率/κ 出数——chat 端点 403/429 全档不可用。
- **复跑路径**：配额恢复后 `uv run --group eval python scripts/
  eval_judge_m35.py --run-judge` → 人工双评回流（用户侧标注
  judge-human-answersheet-m35.jsonl）→ `--calibrate --judge … --human …`
  → `eval/reports/m3-5-judge-calibration.md`。阈值定数归附录 A-6（监督侧
  docs 批——校准数据出来后）。
- **人工双评双轨口径**（用户裁定 2026-11-10）：用户侧标注回流为主；
  **本轮无代行小样**——代行须真实标注且如实申报，chat 受阻下 judge 侧同样
  无法出数，代行小样无对照面，不构成校准材料（不如实登记的事不做）。

## B 组：响应层指标——真实 LLM judge 基线受阻

- **已交付（不受阻面）**：接入形态固化（ragas_bridge `response_layer_rows`
  →`rows_to_ragas_samples`——user_input=query/reference=黄金标注语料文本/
  response=被评应答；悬空键 fail-fast；P3-6 docstring 陷阱同步清偿）+
  门禁确定性用例（`tests/test_eval_response_m35.py`）。
- **受阻面**：faithfulness / answer_relevancy 真实基线出数（ragas LLM-judge
  指标需 chat 端点——403/429 不可用）。
- **复跑路径**：配额恢复后 `uv run --group eval` 环境以
  `response_layer_rows(...)` + `build_openai_compat_ragas_llm()` 经
  `ragas.evaluate` 跑 faithfulness/answer_relevancy（被评应答来源=增强器/
  agent 应答或 judge 材料的构造 response——如实标注应答来源口径）。

## E 组：TC-EVAL-02 LLM 候选占比收口——复跑受阻（维持 m3-4 申报）

- m3-4 申报的复跑路径（配额恢复后 `uv run --group eval python scripts/
  eval_synth_m34.py` 缺省 LLM 模式产候选、人工复核后**增补**——补位不替换，
  用户裁定 2026-11-09）当日仍不可达（chat 全档 403/429/404）。
- 三态覆盖达标（60q/73docs 全机检）维持 m3-4 完成态；**LLM 候选占比收口
  顺延**——待决-1 状态同步更新归监督侧 docs 批（附录 A-6/known-gaps）。
