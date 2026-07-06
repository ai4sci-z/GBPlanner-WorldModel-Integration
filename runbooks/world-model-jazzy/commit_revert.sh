#!/usr/bin/env bash
# 提交工作树里已撤的 3 个参数 hack 到 clean 分支(不 amend 79643b9,加新 revert commit),
# 然后重新导出净无 hack diff (09a5aa4..HEAD)。
set -e
CLEAN=/home/ai4s/ws-clean/world-model
MSG=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/commit_msg_revert.txt
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/world-model-PR/CLEAN_REPRO_takeoff_fixes.diff

cd "$CLEAN"
git add docker/profiles/navlab-sitl-external-nav.parm \
        orchestration/sim/internal/config/defaults.go \
        orchestration/sim/internal/tasks/helpers/templates/parm/official_external_nav.parm.tmpl
git commit -F "$MSG"
echo "==== log ===="
git --no-pager log --oneline -3
echo "==== status ===="
git status --porcelain
echo "==== re-export net diff 09a5aa4..HEAD -> CLEAN_REPRO_takeoff_fixes.diff ===="
git --no-pager diff 09a5aa4 HEAD > "$OUT"
wc -l "$OUT"
echo "==== hack strings still in exported diff? (should be none) ===="
grep -nE 'DISARM_DELAY 0|EK3_SRC1_POSZ 1|ReadinessTimeoutSec, 90' "$OUT" || echo "NONE (good)"
