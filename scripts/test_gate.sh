#!/usr/bin/env bash
# knowledge-lattice 本地测试门禁（M0b-1 起——2026-10-24 用户拍板：不建 GitHub Actions
# CI，项目将移公司内网继续开发；design v1.3.2「CI 必跑 PG、CI 内 skip 视为失败」的
# 意图由本脚本承接）。
#
# 语义：
#   1. 未设置 LATTICE_PG_DSN → 立即非零退出并提示启动容器（绝不静默绿）；
#   2. pg 臂用例收集数 > 0（`[pg]` 参数化条目——防「参数化被删/没收集到」的假绿）；
#   3. 双模式全量 pytest（常规 + python -O）——`-m "not manual"` 排除常驻 manual
#      走查标记（TC-UI 组口径：浏览器人工执行、不进门禁）；
#   4. 任何 failed **或任何 skipped**（含 pg 臂因环境缺失而 skip）→ 非零退出
#      （skip=失败——本地无 CI 兜底，防静默绿灯）。
#
# 可移植性（R2 P3-8）：mktemp 用「模板以 X 结尾」形态（GNU/BSD 通用——公司内网
# Linux 的 GNU mktemp 不接受 BSD `-t` 形态与带后缀模板）；skip 检测匹配 pytest
# 完整 summary 行（不依赖 tail 行数假设）。
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

# ---- pg 臂在场断言：收集期 [pg] 参数化条目 + PG 专用用例 > 0（收集不执行 fixture、无需容器）----
# R2-P3-7：PG_COLLECTED 范围扩为「参数化 [pg] 条目 + PG 专用文件（test_pg_*）
# 收集条目」——防 PG 专用用例被删/没收集到的假绿；${...:-0} 防 set -u 空引用。
PG_PARAM_COLLECTED="$(uv run pytest -m "not manual" --collect-only -q 2>/dev/null | grep -c '\[pg\]' || true)"
PG_ONLY_COLLECTED="$(uv run pytest tests/test_pg_scaff.py tests/test_pg_backend.py -m "not manual" --collect-only -q 2>/dev/null | grep -c '::' || true)"
PG_COLLECTED="$(( ${PG_PARAM_COLLECTED:-0} + ${PG_ONLY_COLLECTED:-0} ))"
if [[ "$PG_COLLECTED" -eq 0 ]]; then
  echo "GATE FAIL: 收集期未发现任何 pg 臂用例（[pg] 参数化 ${PG_PARAM_COLLECTED:-0} + PG 专用 ${PG_ONLY_COLLECTED:-0}）——backend 参数化骨架失守（防「没收集到」的假绿）。" >&2
  exit 1
fi
echo "pg 臂用例收集数：${PG_COLLECTED}（[pg] 参数化 ${PG_PARAM_COLLECTED:-0} + PG 专用 ${PG_ONLY_COLLECTED:-0}，> 0 ✓）"

# 单模式门禁：跑全量 → 退出码拦截 failed → summary 行拦截 skipped
run_mode() {
  local label="$1"
  shift
  local log
  log="$(mktemp "${TMPDIR:-/tmp}/lattice-gate-${label}.XXXXXX")"  # 模板以 X 结尾（GNU/BSD 通用）
  echo "==== [$label] $* -m 'not manual' -q ===="
  if ! "$@" -m "not manual" -q 2>&1 | tee "$log"; then
    echo "GATE FAIL: [$label] 存在 failed 用例（详见 $log）" >&2
    exit 1
  fi
  # 完整 summary 行（最后一个 passed/failed/error 汇总行）上的 skipped 检测
  # R2-P3-2：`|| true` 使 grep 无匹配（无 summary——收集崩溃等）时友好文案可达
  #（原实现 set -e 在赋值处静默退出、诊断信息缺失；fail-closed 语义不变）
  local summary
  summary="$(grep -E '[0-9]+ (passed|failed|error)' "$log" | tail -1 || true)"
  if grep -Eq '[0-9]+ skipped' <<<"$summary"; then
    echo "GATE FAIL: [$label] summary 含 skipped（门禁口径：skip=失败——逐个核对环境或申报理由）" >&2
    echo "  summary: $summary" >&2
    exit 1
  fi
  if [[ -z "$summary" ]]; then
    echo "GATE FAIL: [$label] 未解析到 pytest summary 行（详见 $log）——门禁拒绝无凭据绿灯。" >&2
    exit 1
  fi
  echo "[$label] OK：$summary"
  rm -f "$log"
}

run_mode "pytest" uv run pytest
run_mode "pytest-O" uv run python -O -m pytest

echo "GATE PASS: sqlite+pg 双后端、双模式（常规/python -O）全绿，0 skipped（pg 臂 $PG_COLLECTED 条用例全实跑：[pg] 参数化 ${PG_PARAM_COLLECTED:-0} + PG 专用 ${PG_ONLY_COLLECTED:-0}）"
