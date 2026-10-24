#!/usr/bin/env bash
# knowledge-lattice 本地测试门禁（M0b-1 起——2026-10-24 用户拍板：不建 GitHub Actions
# CI，项目将移公司内网继续开发；design v1.3.2「CI 必跑 PG、CI 内 skip 视为失败」的
# 意图由本脚本承接）。
#
# 语义：
#   1. 未设置 LATTICE_PG_DSN → 立即非零退出并提示启动容器（绝不静默绿）；
#   2. 双模式全量 pytest（常规 + python -O）——`-m "not manual"` 排除常驻 manual
#      走查标记（TC-UI 组口径：浏览器人工执行、不进门禁）；
#   3. 任何 failed **或任何 skipped**（含 pg 臂因环境缺失而 skip）→ 非零退出
#      （skip=失败——本地无 CI 兜底，防静默绿灯）。
#
# 用法：
#   LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice scripts/test_gate.sh
set -euo pipefail

cd "$(dirname "$0")/.."

PG_DSN="${LATTICE_PG_DSN:-}"

if [[ -z "$PG_DSN" ]]; then
  echo "GATE FAIL: LATTICE_PG_DSN 未设置——pg 臂将整体 skip，门禁拒绝静默绿。" >&2
  echo "  请先启动 PG 容器并导出 DSN：" >&2
  echo "    docker start lattice-pg" >&2
  echo "    export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice" >&2
  exit 1
fi

run_mode() {
  local label="$1"
  shift
  local log
  log="$(mktemp -t lattice-gate-${label}).log"
  echo "==== [$label] $* -m 'not manual' -q ===="
  if ! "$@" -m "not manual" -q 2>&1 | tee "$log"; then
    echo "GATE FAIL: [$label] 存在 failed 用例（详见 $log）" >&2
    exit 1
  fi
  if tail -5 "$log" | grep -Eq '[0-9]+ skipped'; then
    echo "GATE FAIL: [$label] 出现 skipped 用例（门禁口径：skip=失败——逐个核对环境或申报理由）" >&2
    tail -5 "$log" >&2
    exit 1
  fi
  echo "[$label] OK：$(tail -1 "$log")"
}

run_mode "pytest" uv run pytest
run_mode "pytest-O" uv run python -O -m pytest

echo "GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped"
