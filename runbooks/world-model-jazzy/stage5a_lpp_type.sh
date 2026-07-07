#!/usr/bin/env bash
F=/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/templates/python/fcu_controller_runtime.py.tmpl
grep -n "local_position_pose\|PoseStamped" "$F" | head -10
CLEAN=/home/ai4s/ws-clean/world-model
META=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)rosbag/exploration_rosbag/metadata.yaml
grep -B2 -A3 "local_position_pose" "$META" | head -12
