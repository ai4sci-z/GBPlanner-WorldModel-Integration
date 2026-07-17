#!/usr/bin/env bash
# L2-fix hover ×RUNS(imu-flu-correction 诊断臂)。WP303 契约见 batch_common.sh。
# 干跑:NAVLAB_SIM_CMD='<stub>' 覆盖真实 go run。批退出码=聚合 rc。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/batch_common.sh"
WM=${WM:-/home/ai4s/projects/world-model}
RUNS=${RUNS:-3}
DURATION_SEC=${DURATION_SEC:-1500}
run_cmd() {
  if [ -n "${NAVLAB_SIM_CMD:-}" ]; then ( eval "$NAVLAB_SIM_CMD" ); return $?; fi
  ( cd "$WM/orchestration/sim" &&
    go run ./cmd/navlab-sim run hover --simulation-profile imu-flu-correction --duration-sec "$DURATION_SEC" )
}
bc_init "l2fix_imu-flu-correction" || exit $?
for i in $(seq 1 "$RUNS"); do
  bc_run "$i" run_cmd || true
  sleep "${INTER_RUN_SLEEP:-10}"
done
bc_finalize
exit $?
