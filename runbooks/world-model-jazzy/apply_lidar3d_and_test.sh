#!/usr/bin/env bash
export PATH=/usr/local/go/bin:$PATH
python3 /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/patch_lidar3d.py || exit 2
cd /home/ai4s/ws-clean/world-model/orchestration/sim || exit 9
echo "==== go build ===="
go build ./... || exit 3
echo "==== go test(tasks 相关) ===="
go test ./internal/tasks/... 2>&1 | grep -E "^(--- FAIL|FAIL|ok)" | head -10
