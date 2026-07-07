#!/usr/bin/env bash
export PATH=/usr/local/go/bin:$PATH
cd /home/ai4s/ws-clean/world-model/orchestration/sim
go test ./internal/tasks/ 2>&1 | grep -E "^--- FAIL|^=== RUN.*FAIL|FAIL:|\.go:[0-9]+" | head -8
