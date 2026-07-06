#!/usr/bin/env bash
export PATH=/usr/local/go/bin:$PATH
python3 /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/patch_clean_rngfndtest.py || exit 2
cd /home/ai4s/ws-clean/world-model/orchestration/sim || exit 9
echo "==== go build ===="
go build ./... || exit 3
echo "==== go vet ===="
go vet ./... 2>&1 | tail -3
echo "==== go test (all) ===="
go test ./... 2>&1 | grep -E "^(--- FAIL|FAIL|ok)" | head -30
