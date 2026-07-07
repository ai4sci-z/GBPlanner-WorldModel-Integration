#!/usr/bin/env bash
TMPL=/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl
echo "=== 模板 L1-240 ==="
sed -n '1,240p' "$TMPL"
