#!/usr/bin/env bash
# L2 default-mainline hover ×RUNS(无诊断 profile)。WP303 契约见 batch_common.sh。
# 干跑:NAVLAB_SIM_CMD='<stub>' 覆盖真实 go run。批退出码=聚合 rc。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/batch_common.sh"
WM=${WM:-/home/ai4s/projects/world-model}
RUNS=${RUNS:-3}
DURATION_SEC=${DURATION_SEC:-1500}
run_cmd() {
  if [ -n "${NAVLAB_SIM_CMD:-}" ]; then ( eval "$NAVLAB_SIM_CMD" ); return $?; fi
  # NAVLAB_SIM_EXTRA_ARGS:默认空=行为不变;AA002 负责人批准的观测通道
  # (传 --config <定制编排配置>,例如 LOG_DISARMED=1 的 sitl defaults;见
  # open1/AA001_r3_定向分析 §4 与 AA002 计划)。值须无空格路径。
  ( cd "$WM/orchestration/sim" &&
    go run ./cmd/navlab-sim ${NAVLAB_SIM_EXTRA_ARGS:-} run hover --duration-sec "$DURATION_SEC" )
}
bc_init "l2_default-mainline" || exit $?
for i in $(seq 1 "$RUNS"); do
  bc_run "$i" run_cmd || true
  sleep "${INTER_RUN_SLEEP:-10}"
done
bc_finalize
exit $?
