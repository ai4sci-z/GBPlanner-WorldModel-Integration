#!/usr/bin/env bash
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
echo "RUNDIR=$RUNDIR"
docker run --rm --network none \
  -v "$DIRB":/exp:ro -v "$RUNDIR":/run:ro \
  navlab/official-baseline:jazzy-latest \
  bash -lc "python3 /exp/cal_bin_params.py /run/sitl/logs/00000001.BIN 2>/dev/null"
