#!/usr/bin/env bash
export PATH=/usr/local/go/bin:$PATH
cd /home/ai4s/ws-clean/world-model/orchestration/sim || exit 9
go test ./internal/tasks/helpers/ -run TestWriteFrameContract -v 2>&1 | head -30
echo ==================
go test ./internal/tasks/helpers/ 2>&1 | grep -E "^(--- FAIL|=== RUN|FAIL|ok)" | head -10
