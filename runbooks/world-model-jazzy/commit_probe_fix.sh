#!/usr/bin/env bash
# 提交探针修复到 clean 分支 + 重导净 diff。
set -e
CLEAN=/home/ai4s/ws-clean/world-model
MSG=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/commit_msg_probe.txt
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/world-model-PR/CLEAN_REPRO_takeoff_fixes.diff

cd "$CLEAN"
git status --porcelain
git add orchestration/sim/internal/tasks/helpers/templates/python/ros_probe.py.tmpl \
        orchestration/sim/internal/tasks/helpers/runtime_specs.go \
        orchestration/sim/internal/tasks/runtime_specs.go \
        orchestration/sim/internal/tasks/helpers/slam_test.go \
        orchestration/sim/internal/tasks/runtime_artifacts_test.go
git commit -F "$MSG"
echo "==== log ===="
git --no-pager log --oneline -4
echo "==== leftover ===="
git status --porcelain
echo "==== re-export net diff ===="
git --no-pager diff 09a5aa4 HEAD > "$OUT"
wc -l "$OUT"
grep -nE 'DISARM_DELAY 0|EK3_SRC1_POSZ 1|ReadinessTimeoutSec, 90' "$OUT" || echo "NO_HACKS (good)"
