#!/usr/bin/env bash
# 校准 run rosbag 检查:话题清单 + /slam/odom 与真值/AP位姿逐秒轨迹
CLEAN=/home/ai4s/ws-clean/world-model
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
echo "RUNDIR=$RUNDIR"
BAG=$(find "$RUNDIR" -name "*.mcap" -o -name "*.db3" 2>/dev/null | head -3)
echo "BAG=$BAG"
find "$RUNDIR" -name "metadata.yaml" | head -3
META=$(find "$RUNDIR" -name "metadata.yaml" | head -1)
[ -n "$META" ] && grep -E "name:|message_count:" "$META" | paste - - | sort -t: -k3 -rn | head -25
echo "--- BIN/tlog 物理日志 ---"
find "$RUNDIR" -name "*.BIN" -o -name "*.bin" -o -name "*.tlog" 2>/dev/null | head -5
