#!/usr/bin/env bash
# Stage4c 前置环境确认(只读,不改任何东西)
CLEAN=/home/ai4s/ws-clean/world-model
TMPL=$CLEAN/orchestration/sim/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl
YAML=$CLEAN/orchestration/sim/configs/tasks/exploration.yaml

echo "=== 1. clean 分支状态 ==="
cd "$CLEAN" && git status --short | head -5 && git log --oneline -n 3

echo "=== 2. external patch 是否已应用到模板 ==="
grep -n 'external' "$TMPL" | head -10 || echo "NOT_PATCHED"

echo "=== 3. exploration.yaml strategy 入口 ==="
sed -n '15,25p' "$YAML"

echo "=== 4. 容器现状 ==="
docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.Image}}' | head -12

echo "=== 5. 探针/桥脚本存在性 ==="
ls -la /mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge/ | grep -E '\.py$'

echo "=== 6. gbplanner_ref 内薄桥 ROS1 侧脚本 ==="
docker exec gbplanner_ref ls -la /tmp/thinbridge_ros1_side.py 2>/dev/null || echo "GBPLANNER_REF_NOT_RUNNING_OR_NO_SCRIPT"

echo "=== 7. workflow 模板 strategy 读取处(SPEC.get strategy 上下文) ==="
grep -n 'strategy' "$TMPL" | head -10

echo "=== ENVCHECK DONE ==="
