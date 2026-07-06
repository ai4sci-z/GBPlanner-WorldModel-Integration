#!/usr/bin/env bash
export PATH=/usr/local/go/bin:$PATH
cd /home/ai4s/ws-clean/world-model/orchestration/sim || exit 9
go test ./internal/tasks/ -run TestGenerateRuntimeArtifactsFromConfiguredTasks 2>&1 | grep -vE "WARN|INFO" | head -40
