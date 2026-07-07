#!/usr/bin/env bash
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
echo "RUNDIR=$RUNDIR"
echo "=== sender 启动头/异常 ==="
LOG="$RUNDIR/runtime/logs/mavlink_external_nav.runtime.log"
grep -vE "Failed to parse type hash" "$LOG" | head -15
grep -E "Traceback|Error|error" "$LOG" | grep -v "type hash" | head -5
echo "=== rosbag 计数(lpp/external_nav/slam) ==="
META=$(find "$RUNDIR" -name metadata.yaml | head -1)
grep -E "name:|message_count:" "$META" | paste - - | grep -E "local_position|external_nav|slam/odom|exploration/status" | head -8
echo "=== BIN EKF 消息 ==="
docker run --rm --network none -v "$DIRB":/exp:ro -v "$RUNDIR":/run:ro \
  navlab/official-baseline:jazzy-latest \
  bash -lc "python3 /exp/cal_bin_params.py /run/sitl/logs/00000001.BIN 2>/dev/null" | grep -E "EK3_SRC1_YAW|COMPASS_USE|MSG"
