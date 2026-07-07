#!/usr/bin/env bash
export PATH=/usr/local/go/bin:$PATH
cd /home/ai4s/ws-clean/world-model/orchestration/sim
go test -count=1 -run . ./internal/tasks/ 2>&1 | grep -B2 -A8 "^--- FAIL" | head -30
