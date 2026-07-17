#!/usr/bin/env bash
# WP303 正式入口(唯一):操作者只跑本脚本,自动经 batch_lifecycle.py launch
#   → 独立 session/PGID + task record + monitor,退出码从 monitor 传播给调用者。
# 用法:  bash run_batch.sh <l15|l2|l2fix> [RUNS]
#   real:  BC_ARTIFACT_BASE 默认 $WM/artifacts/sim;需 companion tag 匹配 wm HEAD。
#   dry:   NAVLAB_SIM_CMD='<stub>' 覆盖真实 go run(测试用,不启动 SITL)。
# 锁:主机 SITL 互斥(BC_LOCK_PATH,纯互斥;本脚本持有,launch 期间保持,退出释放)。
# 不递归:本脚本调用 batch_lifecycle.py launch;producer(l15/l2/l2fix_batch.sh)绝不调用 launch。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BL="$HERE/batch_lifecycle.py"
BC_LOCK_PATH="${BC_LOCK_PATH:-/tmp/navlab_sitl_host.lock}"
WM="${WM:-/home/ai4s/projects/world-model}"
BC_ARTIFACT_BASE="${BC_ARTIFACT_BASE:-$WM/artifacts/sim}"
RUNS="${2:-${RUNS:-3}}"
DURATION_SEC="${DURATION_SEC:-1500}"

case "${1:-}" in
  l15)   PRODUCER="l15_batch.sh";   TAG="l15_truth-external-nav" ;;
  l2)    PRODUCER="l2_batch.sh";    TAG="l2_default-mainline" ;;
  l2fix) PRODUCER="l2fix_batch.sh"; TAG="l2fix_imu-flu-correction" ;;
  *) echo "用法: run_batch.sh <l15|l2|l2fix> [RUNS]" >&2; exit 2 ;;
esac

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ROOT="${BC_ROOT:-$BC_ARTIFACT_BASE/batch_${TAG}_${STAMP}}"
mkdir -p "$ROOT/runs" || { echo "无法建 artifact root: $ROOT" >&2; exit 2; }

# 主机 SITL 互斥(纯互斥,非生命探针);launch 期间持有,本脚本退出释放
exec 9>"$BC_LOCK_PATH"
if ! flock -n 9; then
  echo "run_batch: another real SITL batch holds the host lock ($BC_LOCK_PATH)" >&2
  exit 90
fi

# deadline 参数(可 env 覆盖供 dry-run 缩短);真实默认给足启动/收尾预算
python3 "$BL" launch \
  --artifact-root "$ROOT" \
  --batch-id "${TAG}_${STAMP}" \
  --expected-runs "$RUNS" \
  --duration "${WP303_DURATION:-$DURATION_SEC}" \
  --startup-budget "${WP303_STARTUP:-120}" \
  --per-run-teardown "${WP303_TEARDOWN:-30}" \
  --inter-run-gap "${WP303_GAP:-10}" \
  --finalization-budget "${WP303_FINAL:-180}" \
  ${WP303_REQUIRED:+--required "$WP303_REQUIRED"} \
  -- env "BC_ROOT=$ROOT" "RUNS=$RUNS" "DURATION_SEC=$DURATION_SEC" \
       "INTER_RUN_SLEEP=${INTER_RUN_SLEEP:-10}" "NAVLAB_SIM_CMD=${NAVLAB_SIM_CMD:-}" \
       bash "$HERE/$PRODUCER"
rc=$?
echo "run_batch: monitor rc=$rc  root=$ROOT" >&2
exit "$rc"
