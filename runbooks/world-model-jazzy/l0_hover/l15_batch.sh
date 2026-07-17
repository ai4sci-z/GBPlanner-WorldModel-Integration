#!/usr/bin/env bash
# L1.5 arm of the GATE-4b bisection (truth-external-nav ×RUNS).
# WP303 契约:结构化 run 记录 + 聚合 rc + 主机 SITL 互斥(见 batch_common.sh)。
# Run detached:  setsid nohup bash l15_batch.sh &
# 判决权威仍是 BIN(l1_bin_full_window.py);批退出码=聚合 rc(任一 run 失败→非零)。
# 干跑结构验证:NAVLAB_SIM_CMD='<stub>' 覆盖真实 go run(不启动 SITL)。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/batch_common.sh"

WM=${WM:-/home/ai4s/projects/world-model}
RUNS=${RUNS:-3}
DURATION_SEC=${DURATION_SEC:-1500}

run_cmd() {
  if [ -n "${NAVLAB_SIM_CMD:-}" ]; then ( eval "$NAVLAB_SIM_CMD" ); return $?; fi
  ( cd "$WM/orchestration/sim" &&
    go run ./cmd/navlab-sim run hover --simulation-profile truth-external-nav --duration-sec "$DURATION_SEC" )
}

bc_init "l15_truth-external-nav" || exit $?
for i in $(seq 1 "$RUNS"); do
  bc_run "$i" run_cmd || true
  sleep "${INTER_RUN_SLEEP:-10}"
done
bc_finalize
exit $?
