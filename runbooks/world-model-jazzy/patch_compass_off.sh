#!/usr/bin/env bash
# 坑#15 第二针:external-nav 配置禁用 compass(官方 SLAM 配法:yaw=ExtNav + compass off,
# 否则 DCM 仍用磁 yaw,AHRS 一致性检查照样 "EKF3 Yaw inconsistent")。
set -euo pipefail
F1=/home/ai4s/ws/world-model/docker/profiles/navlab-sitl-external-nav.parm
F2=/home/ai4s/ws/world-model/orchestration/sim/internal/tasks/helpers/templates/parm/official_external_nav.parm.tmpl
for f in "$F1" "$F2"; do
  if grep -q "^COMPASS_USE 0" "$f"; then echo "already patched: $f"; continue; fi
  sed -i '/^EK3_SRC1_YAW 6/a COMPASS_USE 0\nCOMPASS_USE2 0\nCOMPASS_USE3 0' "$f"
done
echo "=== 验证 ==="
grep -n -A3 "EK3_SRC1_YAW" "$F1" "$F2"
