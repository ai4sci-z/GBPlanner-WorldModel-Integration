#!/usr/bin/env bash
# 在 jazzy 容器里离线提取校准 rosbag
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
BAGDIR=$RUNDIR/rosbag/exploration_rosbag
echo "RUNDIR=$RUNDIR"
ls "$BAGDIR" | head -5
docker run --rm --network none \
  -v "$DIRB":/exp:ro -v "$RUNDIR":/run:ro \
  navlab/official-baseline:jazzy-latest \
  bash -lc "cp -r /run/rosbag/exploration_rosbag /tmp/bag && python3 /exp/cal_bag_extract.py /tmp/bag"
