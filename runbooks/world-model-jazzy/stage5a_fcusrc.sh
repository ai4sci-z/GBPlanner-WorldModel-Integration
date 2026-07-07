#!/usr/bin/env bash
# 读 fcu_controller 模板下发段:intent → cmd_vel / MAVLink 两路的确切语义
CLEAN=/home/ai4s/ws-clean/world-model
F=$(grep -rln "cmd_vel" "$CLEAN/orchestration/sim/internal/tasks/helpers/templates/python" | grep -i "fcu\|controller" | head -1)
echo "FILE=$F"
grep -n "linear_x\|linear_y\|yaw_rate\|LOCAL_NED\|coordinate_frame\|base_link\|SET_POSITION\|set_position\|vx\|vy" "$F" | head -40
echo "---- L340-440 ----"
sed -n '340,440p' "$F"
