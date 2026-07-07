#!/usr/bin/env bash
CLEAN=/home/ai4s/ws-clean/world-model
echo "=== 所有 parm 模板 ==="
find "$CLEAN/orchestration/sim/internal" -name "*.parm*"
echo "=== 谁渲染 gazebo-iris-rangefinder.parm ==="
grep -rn "gazebo-iris-rangefinder" "$CLEAN/orchestration/sim/internal" --include='*.go' | head -5
echo "=== 每个 parm 模板里的 EK3_SRC1_YAW ==="
for f in $(find "$CLEAN/orchestration/sim/internal" -name "*.parm*"); do
  echo "-- $f"; grep -n "EK3_SRC1_YAW\|COMPASS_USE" "$f" || echo "(无)"
done
