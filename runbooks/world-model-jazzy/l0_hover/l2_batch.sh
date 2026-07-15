#!/usr/bin/env bash
# L2 arm rerun after the B21 east-axis fix (wm 908a95a): mainline hover
# (full stack + SLAM-fed external-nav, NO diagnostic profile) ×3.
# Counterfactual against the 07-14 L2 5/5 flip baseline.
# Run detached:  setsid nohup bash l2_batch.sh &
# Verdict authority is the BIN (l1_bin_full_window.py + l15_frame_audit.py),
# not the exit code. requires: companion tag matches wm HEAD, no concurrent
# SITL runs.
set -uo pipefail

WM=${WM:-/home/ai4s/projects/world-model}
RUNS=${RUNS:-3}
DURATION_SEC=${DURATION_SEC:-1500}
OUT=${OUT:-$WM/artifacts/sim/l2_batch_$(date -u +%Y%m%dT%H%M%SZ).log}

exec 9>"/tmp/l1_bisect_batch.lock"
flock -n 9 || { echo "another bisect batch is running"; exit 90; }

{
  echo "batch start: $(date -u +%FT%TZ)"
  echo "wm_head: $(git -C "$WM" rev-parse HEAD)"
  echo "wm_dirty: $(git -C "$WM" status --porcelain | wc -l) files"
} | tee "$OUT"

for i in $(seq 1 "$RUNS"); do
  echo "=== mainline-hover run $i/$RUNS start $(date -u +%FT%TZ) ===" | tee -a "$OUT"
  ( cd "$WM/orchestration/sim" && \
    go run ./cmd/navlab-sim run hover --duration-sec "$DURATION_SEC" ) \
    >>"$OUT" 2>&1
  echo "=== mainline-hover run $i rc=$? end $(date -u +%FT%TZ) ===" | tee -a "$OUT"
  sleep 10
done

echo "batch done: $(date -u +%FT%TZ)" | tee -a "$OUT"
echo "log: $OUT"
