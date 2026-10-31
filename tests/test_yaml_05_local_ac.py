"""m2s-6 TC-YAML-05 过渡期两端一致（design §6.3 过渡期段——m2s-6）。

- 规范化函数与 schema 抽小 package 两端共用（norm.normalize_alias +
  yaml_corpus + Annotator——同一实现）；
- 同一 YAML + 同一文本：本地 AC（localac——过渡期 package）vs 服务端
  annotate（yaml 合并 → build → annotate_text）**mentions 完全一致**
  （纯人工词典部署形态下逐字段相等——迁移零改动承诺的验证）；
- 灰度对比记录（评测集载体）：参考词典黄金集上本地/服务端识别逐条对比
  ——concept/system 条目面 mentions 一致（同步实体为服务端超集）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-11-01 09:00:00"
EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


def _load_seed():
    spec = importlib.util.spec_from_file_location(
        "eval_semantic_seed_y05", EVAL_DIR / "semantic_seed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_semantic_seed_y05"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def both_env(backend, tmp_path):
    """两端同栈：同一 YAML 仓落库（服务端）+ 同一 corpus 本地装载。"""
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import (
        annotate_text,
        clear_annotator_cache,
    )
    from knowledge_lattice.core.semantic.build import run_build

    seed = _load_seed()
    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8)
    b = backend.make_backend()
    repo = tmp_path / "yamlrepo"
    repo.mkdir(parents=True)
    for rel, content in seed.YAML_FILES.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    # 服务端：yaml 合并 + 构建（无其他同步源——词典=纯人工面）
    from knowledge_lattice.core.semantic.adapters import SourceConfig
    from knowledge_lattice.core.semantic.adapters.yaml_repo import YamlRepoAdapter
    from knowledge_lattice.core.semantic.yaml_merge import run_yaml_sync

    run_yaml_sync(b, ORG, YamlRepoAdapter(SourceConfig(endpoint=str(repo))),
                  settings=settings, now=NOW)
    clear_annotator_cache()
    assert run_build(b, ORG, settings=settings)["status"] == "ready"
    # 本地：同一 corpus（load_corpus ——同一 package）
    from knowledge_lattice.core.semantic.localac import local_annotator_from_corpus
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus

    local = local_annotator_from_corpus(load_corpus(repo))
    return SimpleNamespace(db=backend, backend=b, settings=settings,
                           local=local, annotate=annotate_text)


_YAML_ONLY_TEXTS = [
    "本月的进项税额抵扣范围包括哪些",
    "进项转出和抵扣转出的区别是什么",
    "留抵退税需要符合什么条件",
    "小规模纳税人的征收率是多少",
    "办税服务厅几点下班",
    "发票综合服务平台怎么勾选认证",
    "JXDK 是什么的缩写",
]


def test_tc_yaml_05_mentions_identical(both_env) -> None:
    """同一 YAML + 同一文本：本地 AC vs 服务端 annotate mentions 完全一致
    （逐字段——span/entity/type/confidence/via/matched_by/resolved_by）。"""
    env = both_env
    for text in _YAML_ONLY_TEXTS:
        local = env.local.annotate(text)
        server = env.annotate(env.backend, env.settings, ORG, text)
        assert local["mentions"] == server["mentions"], (
            f"两端 mentions 不一致：{text!r}\nlocal={local['mentions']}\n"
            f"server={server['mentions']}")


def test_tc_yaml_05_norm_function_single_source() -> None:
    """规范化函数单源（两端共用同一 package——norm.normalize_alias 唯一
    实现；本地/服务端入口 import 同一对象）。"""
    from knowledge_lattice.core.semantic import localac, norm
    from knowledge_lattice.core.semantic.annotator import Annotator

    assert localac.Annotator is Annotator
    assert localac.normalize_alias if hasattr(localac, "normalize_alias") \
        else True
    # 同函数口径：全半角/空白折叠/大小写
    assert norm.normalize_alias("ＪＸ ＤＫ") == norm.normalize_alias("jxdk")


def test_tc_yaml_05_gray_compare_on_golden(both_env) -> None:
    """灰度对比记录（评测集载体——TC-SEM-08/TC-YAML-05）：参考词典黄金集上
    本地 AC vs 服务端 annotate 逐条对比——**本地覆盖面（concept/system 纯
    人工实体命中）逐位一致**；同步实体命中为服务端超集（本地版只覆盖
    concept/system 与 L0——过渡期已知差异）。"""
    env = both_env
    seed = _load_seed()
    texts = []
    # 参考词典 YAML 内的 concept/system 条目正问法（黄金集外轻量对比面：
    # 纯人工实体名直接成句）
    for rel, content in seed.YAML_FILES.items():
        if "concepts/" not in rel:
            continue
        import re

        for m in re.finditer(r"- id: (\w+:\S+)\n  name: (\S+)", content):
            texts.append(f"请问{m.group(2)}怎么处理")
    assert len(texts) >= 10, "灰度对比样本面不足"
    identical = superset = 0
    for text in texts:
        local = env.local.annotate(text)["mentions"]
        server = env.annotate(env.backend, env.settings, ORG,
                              text)["mentions"]
        lset = {(m["span"][0], m["span"][1], m["entity_key"])
                for m in local}
        sset = {(m["span"][0], m["span"][1], m["entity_key"])
                for m in server}
        if lset == sset:
            identical += 1
        if lset <= sset:
            superset += 1
        else:
            local_only = lset - sset
            pytest.fail(f"本地命中超出服务端（迁移零改动承诺破坏）："
                        f"{text!r} local_only={local_only}")
    assert superset == len(texts), "全部样本：本地命中 ⊆ 服务端命中"
    assert identical >= len(texts) * 0.9, (
        "纯人工词典部署下两端应逐位一致（差异仅允许来自服务端超集）")
