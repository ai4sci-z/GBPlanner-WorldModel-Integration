#!/usr/bin/env bash
# L1.5 arm of the GATE-4b bisection (truth-external-nav ×3) — the half of
# l1_bisect_batch.sh that never ran on 2026-07-15 (batch process died with
# its launching terminal mid L1-run-3; L1×3 verdicts already in the BINs).
# Run detached:  setsid nohup bash l15_batch.sh &
# Verdict authority is the BIN (l1_bin_full_window.py), not the exit code.
# mutates: nothing tracked (artifacts only). requires: companion tag matches
# wm HEAD, no concurrent SITL runs.
set -uo pipefail

WM=${WM:-/home/ai4s/projects/world-model}
RUNS=${RUNS:-3}
DURATION_SEC=${DURATION_SEC:-1500}
OUT=${OUT:-$WM/artifacts/sim/l15_batch_$(date -u +%Y%m%dT%H%M%SZ).log}

exec 9>"/tmp/l1_bisect_batch.lock"
flock -n 9 || { echo "another bisect batch is running"; exit 90; }

{
  echo "batch start: $(date -u +%FT%TZ)"
  echo "wm_head: $(git -C "$WM" rev-parse HEAD)"
  echo "wm_dirty: $(git -C "$WM" status --porcelain | wc -l) files"
} | tee "$OUT"

for i in $(seq 1 "$RUNS"); do
  echo "=== truth-external-nav run $i/$RUNS start $(date -u +%FT%TZ) ===" | tee -a "$OUT"
  ( cd "$WM/orchestration/sim" && \
    go run ./cmd/navlab-sim run hover --simulation-profile truth-external-nav --duration-sec "$DURATION_SEC" ) \
    >>"$OUT" 2>&1
  echo "=== truth-external-nav run $i rc=$? end $(date -u +%FT%TZ) ===" | tee -a "$OUT"
  sleep 10
done

echo "batch done: $(date -u +%FT%TZ)" | tee -a "$OUT"
echo "log: $OUT"
