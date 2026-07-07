#!/usr/bin/env bash
# 查 fcu_controller 模板:cmd_vel / mavlink 两路是否有 SPEC 开关;外部导航路由语义
F=/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/templates/python/fcu_controller_runtime.py.tmpl
echo "=== SPEC.get 全部键 ==="
grep -oE 'SPEC\.get\("[a-z_0-9]+"' "$F" | sort -u
echo "=== cmd_vel 发布器创建与 gating ==="
grep -n "cmd_vel_pub\s*=\|cmd_vel_topic\|publish_cmd_vel\|route\|external_nav" "$F" | head -20
echo "=== mavlink setpoint gating ==="
grep -n "mavlink_master\|setpoint_lookahead\|local_setpoint" "$F" | head -15
