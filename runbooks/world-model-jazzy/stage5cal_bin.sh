#!/usr/bin/env bash
# BIN 验尸 + fcu setpoint 状态里 mavlink_local_position_count 佐证
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
echo "RUNDIR=$RUNDIR"
BIN=$(find "$RUNDIR/sitl" -name "*.BIN" | head -1)
echo "BIN=$BIN"
docker run --rm --network none \
  -v "$DIRB":/exp:ro -v "$RUNDIR":/run:ro \
  navlab/official-baseline:jazzy-latest \
  bash -lc "python3 /exp/cal_bin_decode.py /run/sitl/logs/00000001.BIN 2>/dev/null | tail -60"
echo "=== mavlink_local_position_count / setpoint 佐证 ==="
grep -o '"mavlink_local_position_count":[0-9]*' "$RUNDIR"/probes/*.json | sort -u | head
grep -o '"mavlink_setpoint_count":[0-9]*' "$RUNDIR"/probes/*.json | sort -u | head
grep -o '"mavlink_setpoint_error":"[^"]*"' "$RUNDIR"/probes/*.json | sort -u | head
grep -o '"cmd_vel_publish_count":[0-9]*' "$RUNDIR"/probes/*.json | sort -u | head
