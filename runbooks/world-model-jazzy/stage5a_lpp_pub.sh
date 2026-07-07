#!/usr/bin/env bash
F=/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/templates/python/fcu_controller_runtime.py.tmpl
echo "=== local_position_pose 发布处 ==="
grep -n "local_position_pose" "$F"
N=$(grep -n "local_position_pose" "$F" | head -1 | cut -d: -f1)
sed -n "$((N-30)),$((N+10))p" "$F"
