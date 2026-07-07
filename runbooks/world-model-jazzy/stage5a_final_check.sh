#!/usr/bin/env bash
CLEAN=/home/ai4s/ws-clean/world-model
echo "=== exploration.yaml strategy(应为 frontier_lite) ==="
grep -n 'strategy:' "$CLEAN/orchestration/sim/configs/tasks/exploration.yaml" | head -2
echo "=== clean 分支状态(应干净,5 commit) ==="
cd "$CLEAN" && git status --short | head -3; git log --oneline -n 5
echo "=== 容器 ==="
docker ps --format '{{.Names}}\t{{.Status}}' | head -6
