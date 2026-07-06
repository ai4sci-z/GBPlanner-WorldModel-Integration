#!/usr/bin/env bash
# 应用 late-join 发现补丁 + go build/vet/test 验证。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
python3 /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/patch_probe_latejoin.py || exit 2
cd /home/ai4s/ws-clean/world-model/orchestration/sim || exit 9
echo "==== go build ===="
go build ./... || exit 3
echo "==== go vet ===="
go vet ./internal/tasks/... || exit 4
echo "==== go test ===="
go test ./internal/tasks/... 2>&1 | tail -15
