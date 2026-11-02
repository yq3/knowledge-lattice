#!/usr/bin/env python
"""YAML 覆盖层仓 CI 校验（design §5.8 合并规则表 CI 责任列 + TC-YAML-04）。

用法：`uv run python scripts/sem_yaml_ci.py <yaml_repo_path> [--l0-budget N]`

- 结构（id/类型域/owner/name/sensitivity）、别名冲突（歧义需消歧或 context）、
  短词/常用词、L0 预算、owner 必填（逐条报）、引用可解析、
  samples ≤3（逐条报）、extra_relations 白名单、JSON Schema 条目级校验
  （`_schema/entry.schema.json` 在场时——R2/边界 1）；
- `--l0-budget` 缺省时读 `LATTICE_SEM_L0_TOKEN_BUDGET` 环境变量
  （Settings.semantic_l0_token_budget 接线——R2/P3-11；最终缺省 1500）；
- 任一 error → 逐条打印（可定位到文件）并 exit 1；仅 warning → exit 0。

Git 平台 CI 集成：合并前拦截（design「CI 在合并前拦截，入库时触发器兜底」）。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_DEFAULT_L0_BUDGET = 1500


def _env_budget() -> int:
    """P3-11/R2：预算从环境变量接线（与 Settings.semantic_l0_token_budget 同源）。"""
    raw = os.environ.get("LATTICE_SEM_L0_TOKEN_BUDGET", "").strip()
    if not raw:
        return _DEFAULT_L0_BUDGET
    try:
        return int(raw)
    except ValueError:
        print(f"[ERROR] LATTICE_SEM_L0_TOKEN_BUDGET 非整数: {raw!r}")
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", help="YAML 仓路径（本地 checkout）")
    parser.add_argument("--l0-budget", type=int, default=None,
                        help="L0 token 预算（缺省读 LATTICE_SEM_L0_TOKEN_BUDGET"
                             f"／最终缺省 {_DEFAULT_L0_BUDGET}——§5.8）")
    args = parser.parse_args(argv)
    l0_budget = args.l0_budget if args.l0_budget is not None else _env_budget()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from knowledge_lattice.core.semantic.yaml_corpus import load_corpus, validate_corpus

    try:
        corpus = load_corpus(args.repo)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {args.repo}: corpus 装载失败: {exc}")
        return 1

    issues = validate_corpus(corpus, l0_budget=l0_budget)
    for issue in issues:
        print(issue)
    errors = [i for i in issues if i.severity == "error"]
    print(f"-- sem_yaml_ci: {len(corpus.entries)} entries, rev={corpus.rev}, "
          f"{len(errors)} error(s), {len(issues) - len(errors)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
