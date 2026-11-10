#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""m3-5 A 组：TC-EVAL-03 judge 双语校准（材料构建 / judge 联调 / 一致率·κ 校准）。

口径（检查点 A 组 + 用户裁定 2026-11-10）：
- **judge 端点沿 m2-5 百炼先例**（DashScope OpenAI 兼容 qwen，
  ``LATTICE_EVAL_LLM_*`` env 零代码切换）；联调动作**不进门禁**；
- **人工双评双轨**：本脚本产出 ~50 条双评材料与格式（``--materials``）供
  用户侧标注回流为主；代行小样须如实申报（沿 m2-5/m3-4 受阻先例，不冒充）；
- **阈值数值归附录 A-6**（监督侧 docs 批——校准数据出来后定数）。

用法（materials/calibrate 离线确定性；run-judge 需 eval 依赖组 + 端点凭据）：
  uv run python scripts/eval_judge_m35.py --materials     # 50 条双评材料（eval/reports/）
  uv run --group eval python scripts/eval_judge_m35.py --run-judge   # 真实 judge 联调
  uv run python scripts/eval_judge_m35.py --calibrate \\
      --judge data/eval-judge/m35-judge-labels.jsonl \\
      --human data/eval-judge/m35-human-labels.jsonl     # 一致率/κ 校准报告

人工标注回流格式（JSONL，每行 {"item_id","label","rater"}，label ∈
faithful|unfaithful）——材料文件 judge-materials-m35.jsonl 的 item_id 对账。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

EVAL_DIR = ROOT / "eval"
REPORTS = EVAL_DIR / "reports"
OUT_DIR = ROOT / "data" / "eval-judge"

SEED = 20261110  # 材料确定性（同 seed 同产物——复跑对账友好）


def _load_inputs():
    from knowledge_lattice.eval.harness import load_corpus, load_golden

    corpus = load_corpus(EVAL_DIR / "corpus.jsonl")
    golden = load_golden(EVAL_DIR / "golden.jsonl")
    return {d.doc_id: d.text for d in corpus}, golden


def cmd_materials(n: int) -> int:
    from knowledge_lattice.eval.judge import build_materials

    texts, golden = _load_inputs()
    items = build_materials(texts, golden, n=n, seed=SEED)
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "judge-materials-m35.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    # 人工标注回流模板（双评两列——rater 自定标识）
    sheet = REPORTS / "judge-human-answersheet-m35.jsonl"
    with sheet.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(
                {"item_id": it["item_id"], "qid": it["qid"], "lang": it["lang"],
                 "label": "", "rater": ""},
                ensure_ascii=False) + "\n")
    langs = {ln: sum(1 for i in items if i["lang"] == ln) for ln in ("zh", "en", "mix")}
    cons = {c: sum(1 for i in items if i["construction"] == c)
            for c in ("faithful", "unfaithful")}
    print(f"materials written: {path}（{len(items)} 条；三态 {langs}；构造 {cons}）")
    print(f"human answersheet: {sheet}（标注回流格式见脚本 docstring）")
    return 0


def cmd_run_judge() -> int:
    from knowledge_lattice.eval.judge import run_judge
    from knowledge_lattice.eval.ragas_bridge import build_openai_compat_ragas_llm

    materials = REPORTS / "judge-materials-m35.jsonl"
    if not materials.is_file():
        print(f"材料缺席——先跑 --materials：{materials}", file=sys.stderr)
        return 1
    items = [json.loads(ln) for ln in materials.read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    llm = build_openai_compat_ragas_llm()
    t0 = time.monotonic()
    verdicts = run_judge(llm, items)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "m35-judge-labels.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for it, v in zip(items, verdicts):
            fh.write(json.dumps(
                {"item_id": it["item_id"], "qid": it["qid"], "lang": it["lang"],
                 "construction": it["construction"], "label": v},
                ensure_ascii=False) + "\n")
    agree_construct = sum(
        1 for it, v in zip(items, verdicts) if it["construction"] == v)
    print(f"judge labels written: {out}（{len(verdicts)} 条，"
          f"{time.monotonic() - t0:.1f}s）")
    print(f"  judge vs 构造标签一致率（参考面——非人工双评）: "
          f"{agree_construct}/{len(verdicts)}")
    return 0


def _read_labels(path: Path) -> list[str]:
    from knowledge_lattice.eval.judge import (
        LABELS, VERDICT_FAITHFUL, VERDICT_UNFAITHFUL,
    )

    rows = [json.loads(ln)
            for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for r in rows:
        if r.get("label") not in (VERDICT_FAITHFUL, VERDICT_UNFAITHFUL):
            raise SystemExit(
                f"{path} 存在未标注/非法 label 行：{r}（合法值 {LABELS}）")
    return [r["label"] for r in rows]


def cmd_calibrate(judge_path: Path, human_path: Path) -> int:
    from knowledge_lattice.eval.judge import calibration_report

    judge = _read_labels(judge_path)
    human = _read_labels(human_path)
    if len(judge) != len(human):
        print(f"标签数不齐：judge {len(judge)} vs human {len(human)}"
              "（按材料 item_id 对齐逐行标注）", file=sys.stderr)
        return 1
    rep = calibration_report(judge, human)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "m3-5-judge-calibration.md"
    lines = [
        "# m3-5 TC-EVAL-03 judge 校准记录（judge vs 人工双评）",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- judge 标签：`{judge_path}`；人工标签：`{human_path}`",
        f"- **一致率 = {rep['agreement']:.4f}** / **Cohen's κ = {rep['kappa']:.4f}**"
        f"（n={rep['n']}）",
        "- 阈值判定：归附录 A-6（监督侧 docs 批——本报告只出数不定线）",
        "",
        "## 混淆矩阵（行=judge、列=人工）",
        "",
        "| judge \\ 人工 | " + " | ".join(rep["labels"]) + " |",
        "|---|" + "---|" * len(rep["labels"]),
    ]
    for j in rep["labels"]:
        lines.append(
            f"| {j} | "
            + " | ".join(str(rep["confusion"][j][h]) for h in rep["labels"]) + " |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"calibration report: {out}")
    print(json.dumps({k: v for k, v in rep.items() if k != "confusion"},
                     ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mutex = parser.add_mutually_exclusive_group(required=True)
    mutex.add_argument("--materials", action="store_true",
                       help="构建 ~50 条人工双评材料（离线确定性、seed 固定）")
    mutex.add_argument("--run-judge", action="store_true",
                       help="真实 judge 联调（需 eval 依赖组+端点凭据；不进门禁）")
    mutex.add_argument("--calibrate", action="store_true",
                       help="一致率/κ 校准（--judge/--human 标签文件）")
    mutex.add_argument("--self-check", action="store_true",
                       help="确定性核心自检（离线：prompt/判读/κ 数学）")
    parser.add_argument("--n", type=int, default=50, help="材料条数（缺省 50）")
    parser.add_argument("--judge", type=Path, help="judge 标签文件（--calibrate）")
    parser.add_argument("--human", type=Path, help="人工标签文件（--calibrate）")
    args = parser.parse_args()

    if args.materials:
        return cmd_materials(args.n)
    if args.run_judge:
        return cmd_run_judge()
    if args.calibrate:
        if not (args.judge and args.human):
            parser.error("--calibrate 需 --judge 与 --human")
        return cmd_calibrate(args.judge, args.human)
    # --self-check：离线确定性（κ 数学/判读/材料——零 LLM 零网络）
    from knowledge_lattice.eval.judge import (
        build_judge_prompt, cohens_kappa, parse_judge_verdict,
    )

    assert cohens_kappa(["f"] * 5, ["f"] * 5) == 1.0
    kappa_hand = cohens_kappa(["f", "f", "u", "u", "f"], ["f", "f", "f", "u", "u"])
    assert abs(kappa_hand - 1 / 6) < 1e-9, kappa_hand
    assert parse_judge_verdict("Verdict: faithful") == "faithful"
    assert parse_judge_verdict("判定：不忠实") == "unfaithful"
    assert parse_judge_verdict("yes") == "faithful"
    assert parse_judge_verdict("否") == "unfaithful"
    assert "忠实" in build_judge_prompt(
        {"query": "q", "response": "r", "reference": "s"}, lang="zh")
    print("judge core self-check: OK（κ 数学/判读解析/双语 prompt——离线确定性）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
