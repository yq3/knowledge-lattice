"""m3-5 A 组：TC-EVAL-03 judge 双语校准——确定性核心（零 LLM，进门禁）。

judge 校准管道三件（``src/knowledge_lattice/eval/judge.py``）：
- **双语 judge prompt**（zh/en/mix 三态——验收原句「judge prompt 双语」）：按
  被评 item 的 lang 态构造，判faithfulness 二值（faithful / unfaithful）；
- **判读解析**：judge 输出（自然语言）→ 二值判定；不可解析 → 显式 ValueError
  （不静默猜）；
- **一致率 / Cohen's κ**：judge vs 人工双评标签的吻合度量（确定性数学——
  离线可测；阈值数值归附录 A-6 监督侧 docs 批定数，本模块不出阈值）。

真实 judge 联调（``run_judge``——经 ragas_bridge ``build_openai_compat_ragas_llm``
的 OpenAI 兼容端点，沿 m2-5 百炼先例）**不进门禁**（沿 m3-4 口径）；
~50 条人工双评材料构建（``build_materials``——确定性、seed 固定可复现）。
"""

from __future__ import annotations

import pytest

from knowledge_lattice.eval.harness import GoldenCase, load_corpus, load_golden
from knowledge_lattice.eval.judge import (
    agreement_rate,
    build_judge_prompt,
    build_materials,
    calibration_report,
    cohens_kappa,
    parse_judge_verdict,
)

EVAL_DIR_CORPUS = "eval/corpus.jsonl"
EVAL_DIR_GOLDEN = "eval/golden.jsonl"


# ============ 一致率 / κ（确定性数学） ============


def test_tc_eval_03_agreement_rate() -> None:
    """一致率 = 吻合数 / 总数；空输入显式拒（校准于空集是上游 bug）。"""
    a = ["faithful", "unfaithful", "faithful", "faithful"]
    b = ["faithful", "faithful", "faithful", "unfaithful"]
    assert agreement_rate(a, b) == pytest.approx(0.5)
    assert agreement_rate(a, a) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        agreement_rate([], [])
    with pytest.raises(ValueError):
        agreement_rate(["faithful"], ["faithful", "unfaithful"])


def test_tc_eval_03_cohens_kappa_known_value() -> None:
    """κ 手算例：po=0.6、pe=0.52 → κ=(0.6-0.52)/(1-0.52)=1/6。"""
    a = ["f", "f", "u", "u", "f"]
    b = ["f", "f", "f", "u", "u"]
    # po = 3/5；pe = (3/5·3/5)+(2/5·2/5) = 0.52；κ = 0.08/0.48 = 1/6
    assert cohens_kappa(a, b) == pytest.approx(1 / 6)


def test_tc_eval_03_cohens_kappa_extremes() -> None:
    """完全一致 κ=1（含退化单类双方一致）；机会一致削尽正吻合。"""
    assert cohens_kappa(["f"] * 5, ["f"] * 5) == pytest.approx(1.0)  # 退化：双方恒同类
    assert cohens_kappa(["f", "u", "f", "u"], ["f", "u", "f", "u"]) == pytest.approx(1.0)
    # 双方边缘分布完全错开（pe=0、po=0）→ κ=0
    assert cohens_kappa(["f", "f"], ["u", "u"]) == pytest.approx(0.0)
    # 对角随机基线：po == pe → κ=0（a/b 独立同分布构造）
    a = ["f", "f", "u", "u"]
    b = ["f", "u", "f", "u"]
    po = 0.5
    pe = 0.5 * 0.5 + 0.5 * 0.5
    assert po == pe  # 基线自检
    assert cohens_kappa(a, b) == pytest.approx(0.0)


def test_tc_eval_03_calibration_report_structure() -> None:
    """校准报告：n/一致率/κ + 判定×人工混淆矩阵（按 judge→human 计数）。"""
    judge = ["faithful", "faithful", "unfaithful", "unfaithful"]
    human = ["faithful", "unfaithful", "unfaithful", "unfaithful"]
    rep = calibration_report(judge, human)
    assert rep["n"] == 4
    assert rep["agreement"] == pytest.approx(0.75)
    assert rep["kappa"] == pytest.approx(
        cohens_kappa(judge, human))
    assert rep["labels"] == ["faithful", "unfaithful"]
    assert rep["confusion"]["faithful"]["faithful"] == 1
    assert rep["confusion"]["faithful"]["unfaithful"] == 1
    assert rep["confusion"]["unfaithful"]["unfaithful"] == 2


# ============ judge prompt 双语 + 判读解析 ============


def _item(lang: str = "zh") -> dict:
    return {
        "item_id": "jm-01", "qid": "q01", "lang": lang,
        "query": "增值税税率是多少",
        "reference": "增值税基本税率为百分之十三，低税率为百分之九。",
        "response": "增值税基本税率为百分之十三。",
        "construction": "faithful",
    }


@pytest.mark.parametrize("lang", ["zh", "en", "mix"])
def test_tc_eval_03_judge_prompt_bilingual(lang: str) -> None:
    """prompt 双语：三态 lang 说明 + 中英双语的判定指令与字段（验收原句）。"""
    prompt = build_judge_prompt(_item(lang), lang=lang)
    # 中英双语指令面（不论被评 item 语言态，指令本身双语给出）
    assert "忠实" in prompt and "faithful" in prompt
    assert "判定" in prompt and "verdict" in prompt.lower()
    # 三态说明按 lang 注入
    assert {"zh": "纯中文", "en": "English", "mix": "中英混排"}[lang] in prompt
    # 被评字段在场（query / response / reference——判 faithfulness 的三要素）
    assert "增值税税率是多少" in prompt
    assert "增值税基本税率为百分之十三。" in prompt
    assert "增值税基本税率为百分之十三，低税率为百分之九。" in prompt


def test_tc_eval_03_parse_verdict_wordings() -> None:
    """judge 输出判读：中英措辞/带解释文本/二值词序陷阱（unfaithful 含
    faithful 子串——必须先判否定形）。"""
    for text, want in [
        ("faithful", "faithful"),
        ("unfaithful", "unfaithful"),
        ("Verdict: faithful", "faithful"),
        ("判定：不忠实", "unfaithful"),
        ("忠实", "faithful"),
        ("结论是 no，存在无依据内容", "unfaithful"),
        ("yes", "faithful"),
        ("否", "unfaithful"),
        ("是", "faithful"),
        ("0", "unfaithful"),
        ("1", "faithful"),
    ]:
        assert parse_judge_verdict(text) == want, text
    with pytest.raises(ValueError):
        parse_judge_verdict("这是一个无法判定的输出")


# ============ ~50 条人工双评材料（确定性构建） ============


def test_tc_eval_03_materials_deterministic_and_covered() -> None:
    """材料构建：50 条、三态覆盖、faithful/unfaithful 两构造、seed 可复现。"""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    corpus = load_corpus(root / "eval" / "corpus.jsonl")
    golden = load_golden(root / "eval" / "golden.jsonl")
    texts = {d.doc_id: d.text for d in corpus}

    items = build_materials(texts, golden, n=50, seed=20261110)
    assert len(items) == 50
    # 三态覆盖（双语校准面——zh/en/mix 都要在场）
    langs = {i["lang"] for i in items}
    assert langs == {"zh", "en", "mix"}
    # 两种构造都在场（faithful 抽取式 / unfaithful 干扰句——供一致率非退化）
    cons = {i["construction"] for i in items}
    assert cons == {"faithful", "unfaithful"}
    # 可复现（同 seed 同产物）
    again = build_materials(texts, golden, n=50, seed=20261110)
    assert again == items
    # 可序列化（材料入库 eval/reports/ 沿 labeling-notes 先例）
    json.dumps(items[0], ensure_ascii=False)

    by_qid = {c.qid: c for c in golden}
    corpus_keys = set(texts)
    for it in items:
        # reference 来自黄金标注语料（标注键 → 语料文本）
        labels = by_qid[it["qid"]].labels
        assert {doc for doc, _ in labels} <= corpus_keys
        assert it["reference"], "reference 非空"
        if it["construction"] == "faithful":
            # 抽取式：response 是 reference 的连续片段（有依据）
            assert it["response"] in it["reference"]
        else:
            # 干扰句：response 不在 reference 内（无依据——幻觉面）
            assert it["response"] not in it["reference"]
            assert it["response"] in json.dumps(
                list(texts.values()), ensure_ascii=False) or any(
                it["response"] in t for t in texts.values()), (
                "干扰句须取自语料文本（真实业务表述，非编造噪声）")


def test_tc_eval_03_materials_lang_state_matches_query() -> None:
    """材料 lang 态与黄金集标注一致（沿 m3-4 lang×文本一致性机检口径）。"""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    corpus = load_corpus(root / "eval" / "corpus.jsonl")
    golden = load_golden(root / "eval" / "golden.jsonl")
    items = build_materials(
        {d.doc_id: d.text for d in corpus}, golden, n=50, seed=20261110)
    by_qid = {c.qid: c for c in golden}
    assert all(i["lang"] == by_qid[i["qid"]].lang for i in items)
    assert all(i["query"] == by_qid[i["qid"]].query for i in items)


# ============ R2 P3-9：answersheet 非空拒写保护（人工标注防静默清空） ============


def _load_m35_script():
    """经路径加载 scripts/eval_judge_m35.py（脚本面单测——cmd_materials 卫）。"""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "eval_judge_m35", Path(__file__).resolve().parent.parent
        / "scripts" / "eval_judge_m35.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_sheet(path, rows: list[dict]) -> None:
    import json as _json

    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(_json.dumps(r, ensure_ascii=False) + "\n")


def _sheet_rows(path) -> list[dict]:
    import json as _json

    return [_json.loads(ln) for ln in
            path.read_text(encoding="utf-8").splitlines() if ln.strip()]


_SHEET_NAME = "judge-human-answersheet-m35.jsonl"
_MATER_NAME = "judge-materials-m35.jsonl"


def test_tc_eval_03_answersheet_blank_template_regenerates(tmp_path, monkeypatch, capsys) -> None:
    """空模板/缺席路径不破坏：无人工标注（label/rater 全空或无文件）时
    --materials 正常生成（首次运行路径）。"""
    mod = _load_m35_script()
    monkeypatch.setattr(mod, "REPORTS", tmp_path)
    # 预置一份「全空」旧模板（如上次生成后未标注）
    _write_sheet(tmp_path / _SHEET_NAME, [
        {"item_id": "jm-01", "qid": "q42", "lang": "en", "label": "", "rater": ""},
    ])
    rc = mod.cmd_materials(n=6)
    assert rc == 0
    rows = _sheet_rows(tmp_path / _SHEET_NAME)
    assert len(rows) == 6 and all(r["label"] == "" and r["rater"] == "" for r in rows)
    assert (tmp_path / _MATER_NAME).is_file()


def test_tc_eval_03_answersheet_annotated_refuses_overwrite(
        tmp_path, monkeypatch, capsys) -> None:
    """非空拒写（P3-9 主路径）：answersheet 含人工标注时 --materials 拒写——
    报错含已检测标注行数与 --force 提示；标注文件原样保留（零清空）。"""
    mod = _load_m35_script()
    monkeypatch.setattr(mod, "REPORTS", tmp_path)
    annotated = [
        {"item_id": "jm-01", "qid": "q42", "lang": "en", "label": "faithful", "rater": "alice"},
        {"item_id": "jm-02", "qid": "q18", "lang": "en", "label": "unfaithful", "rater": "alice"},
        {"item_id": "jm-03", "qid": "q07", "lang": "zh", "label": "", "rater": "bob"},
    ]
    _write_sheet(tmp_path / _SHEET_NAME, annotated)
    rc = mod.cmd_materials(n=6)
    assert rc != 0, "含人工标注的 answersheet 必须拒写（防静默清空）"
    err = capsys.readouterr().err
    assert "3" in err and "--force" in err, (
        f"报错须含已检测标注行数（3——label 或 rater 任一非空）与 --force 提示：{err}")
    # 标注原样保留 + 材料文件不写（原子拒写——防 item_id 集合与旧 sheet 错位）
    assert _sheet_rows(tmp_path / _SHEET_NAME) == annotated
    assert not (tmp_path / _MATER_NAME).exists()


def test_tc_eval_03_answersheet_force_overrides(tmp_path, monkeypatch, capsys) -> None:
    """--force 显式覆盖路径：标注在档仍可重建（用户显式动作语义）。"""
    mod = _load_m35_script()
    monkeypatch.setattr(mod, "REPORTS", tmp_path)
    _write_sheet(tmp_path / _SHEET_NAME, [
        {"item_id": "jm-01", "qid": "q42", "lang": "en", "label": "faithful", "rater": "alice"},
    ])
    rc = mod.cmd_materials(n=6, force=True)
    assert rc == 0
    rows = _sheet_rows(tmp_path / _SHEET_NAME)
    assert len(rows) == 6 and all(r["label"] == "" and r["rater"] == "" for r in rows)
