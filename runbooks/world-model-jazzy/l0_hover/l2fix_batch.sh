#!/usr/bin/env bash
# L2-fix arm: hover with the imu-flu-correction profile ×3, on top of the
# B21 east-axis fix (wm 908a95a). Single-variable counterfactual against the
# post-B21 L2 mainline 3/3 flip: fed yaw measured ≡ truth−180° while fed
# position tracks truth (cos=+1.0000) — hypothesis: Cartographer's flipped
# IMU input (iris roll-180 mount, TF claims identity) flips its orientation
# estimate; the corrector un-flips the data.
# Run detached:  setsid nohup bash l2fix_batch.sh &
# Verdict authority is the BIN + VISP/SIM yaw comparison, not the exit code.
set -uo pipefail

WM=${WM:-/home/ai4s/projects/world-model}
RUNS=${RUNS:-3}
DURATION_SEC=${DURATION_SEC:-1500}
OUT=${OUT:-$WM/artifacts/sim/l2fix_batch_$(date -u +%Y%m%dT%H%M%SZ).log}

exec 9>"/tmp/l1_bisect_batch.lock"
flock -n 9 || { echo "another bisect batch is running"; exit 90; }

{
  echo "batch start: $(date -u +%FT%TZ)"
  echo "wm_head: $(git -C "$WM" rev-parse HEAD)"
  echo "wm_dirty: $(git -C "$WM" status --porcelain | wc -l) files"
} | tee "$OUT"

for i in $(seq 1 "$RUNS"); do
  echo "=== imu-flu-correction run $i/$RUNS start $(date -u +%FT%TZ) ===" | tee -a "$OUT"
  ( cd "$WM/orchestration/sim" && \
    go run ./cmd/navlab-sim run hover --simulation-profile imu-flu-correction --duration-sec "$DURATION_SEC" ) \
    >>"$OUT" 2>&1
  echo "=== imu-flu-correction run $i rc=$? end $(date -u +%FT%TZ) ===" | tee -a "$OUT"
  sleep 10
done

echo "batch done: $(date -u +%FT%TZ)" | tee -a "$OUT"
echo "log: $OUT"
