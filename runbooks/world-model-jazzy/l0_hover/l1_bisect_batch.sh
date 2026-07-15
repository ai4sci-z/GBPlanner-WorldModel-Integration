#!/usr/bin/env bash
# GATE-4b bisection, layers L1 / L1.5 (Review 002 §3.2; evidence doc §7).
# Runs the world-model hover task through the Go harness with the two
# diagnostic simulation profiles added in wm ff919fb:
#   L1   = gps-ekf-services   (full SLAM/companion services, FCU on GPS EKF)
#   L1.5 = truth-external-nav (external-nav fed origin-normalized Gazebo truth)
# Verdict authority is the flight BIN (l0_bin_verdict.py), NOT the task exit
# code — L2r showed probe timeouts masking flips.
# mutates: nothing tracked (artifacts only). requires: docker runtime images
# per pins (companion tag must match wm HEAD), no concurrent SITL runs.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WM=${WM:-/home/ai4s/projects/world-model}
RUNS_PER_ARM=${RUNS_PER_ARM:-3}
OUT=${OUT:-$WM/artifacts/sim/l1_bisect_batch_$(date -u +%Y%m%dT%H%M%SZ).log}

exec 9>"/tmp/l1_bisect_batch.lock"
flock -n 9 || { echo "another bisect batch is running"; exit 90; }

{
  echo "batch start: $(date -u +%FT%TZ)"
  echo "wm_head: $(git -C "$WM" rev-parse HEAD)"
  echo "wm_dirty: $(git -C "$WM" status --porcelain | wc -l) files"
} | tee "$OUT"

run_arm() {
  local profile="$1" n="$2"
  for i in $(seq 1 "$n"); do
    echo "=== $profile run $i/$n start $(date -u +%FT%TZ) ===" | tee -a "$OUT"
    ( cd "$WM/orchestration/sim" && \
      go run ./cmd/navlab-sim run hover --simulation-profile "$profile" ) \
      >>"$OUT" 2>&1
    echo "=== $profile run $i rc=$? end $(date -u +%FT%TZ) ===" | tee -a "$OUT"
    # give SITL/gazebo teardown a moment before the next run
    sleep 10
  done
}

run_arm gps-ekf-services   "$RUNS_PER_ARM"
run_arm truth-external-nav "$RUNS_PER_ARM"

echo "batch done: $(date -u +%FT%TZ)" | tee -a "$OUT"
echo "log: $OUT"
