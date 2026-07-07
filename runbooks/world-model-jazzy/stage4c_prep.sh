#!/usr/bin/env bash
# Stage4c 准备:应用 external patch + 摸清 gbplanner_ref 自启机制
CLEAN=/home/ai4s/ws-clean/world-model
TMPL=$CLEAN/orchestration/sim/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl

echo "=== 1. 应用 external strategy patch(幂等) ==="
python3 /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/patch_external_strategy.py

echo "=== 2. 验证 patch ==="
grep -n 'external' "$TMPL" | head -5

echo "=== 3. gbplanner_ref 容器启动命令 ==="
docker inspect gbplanner_ref --format '{{json .Config.Cmd}} {{json .Config.Entrypoint}} {{json .Path}} {{json .Args}}'

echo "=== 4. gbplanner_ref 内当前进程 ==="
docker exec gbplanner_ref bash -c "ps aux | grep -E 'ros|python' | grep -v grep | head -15"

echo "=== 5. clean 分支 git status(patch 后) ==="
cd "$CLEAN" && git status --short
echo "=== PREP DONE ==="
