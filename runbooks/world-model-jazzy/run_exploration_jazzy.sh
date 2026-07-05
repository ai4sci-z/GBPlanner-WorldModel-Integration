#!/usr/bin/env bash
# jazzy 首跑 exploration(live-preflight)。绝对路径;日志落盘;不信退出码,验 summary。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
cd /home/ai4s/ws/world-model/orchestration/sim || { echo "CD_FAIL"; exit 9; }
LOG=/home/ai4s/run_exploration_jazzy.log
echo "=== JAZZY EXPLORATION RUN START $(date) HEAD=$(git -C /home/ai4s/ws/world-model rev-parse --short HEAD) ===" | tee "$LOG"
go run ./cmd/navlab-sim run exploration --live-preflight 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
echo "=== RUN END rc=${RC} $(date) ===" | tee -a "$LOG"
echo "=== 最新 run 目录与 summary ===" | tee -a "$LOG"
LATEST=$(ls -dt /home/ai4s/ws/world-model/orchestration/sim/artifacts/sim/exploration/*/ 2>/dev/null | head -1)
echo "latest_run_dir=${LATEST}" | tee -a "$LOG"
if [ -n "$LATEST" ] && [ -f "${LATEST}/exploration_summary.json" ]; then
  grep -oE '"status"[^,]*|"blockers"' "${LATEST}/exploration_summary.json" | head -5 | tee -a "$LOG"
fi
exit "$RC"
