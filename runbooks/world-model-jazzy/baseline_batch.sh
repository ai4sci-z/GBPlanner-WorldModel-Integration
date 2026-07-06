#!/usr/bin/env bash
# frontier_lite 基线定档:连跑 N 次 exploration,逐次记录关键指标(只报实测)。
# 用法: baseline_batch.sh [N]
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
VERDICT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/summary_verdict.py
N=${1:-5}
LOG=/home/ai4s/baseline_batch.log
: > "$LOG"
cd "$CLEAN/orchestration/sim" || exit 9
for i in $(seq 1 "$N"); do
  echo "===== RUN $i/$N START $(date) HEAD=$(git -C "$CLEAN" rev-parse --short HEAD) =====" | tee -a "$LOG"
  go run ./cmd/navlab-sim run exploration --live-preflight >> "$LOG" 2>&1
  RC=$?
  RUN=$(ls -t "$CLEAN/artifacts/sim/exploration" | head -1)
  echo "----- RUN $i/$N done rc=$RC run_id=$RUN" | tee -a "$LOG"
  python3 "$VERDICT" "$CLEAN/artifacts/sim/exploration/$RUN" 2>&1 | tee -a "$LOG"
done
echo "BATCH_DONE N=$N"
