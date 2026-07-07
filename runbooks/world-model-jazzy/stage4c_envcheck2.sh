#!/usr/bin/env bash
# Stage4c 前置确认第二轮:未提交 diff 内容 + 模板 external patch 历史
CLEAN=/home/ai4s/ws-clean/world-model
TMPL=orchestration/sim/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl
cd "$CLEAN" || exit 9

echo "=== 1. 未提交 diff(全文) ==="
git diff

echo "=== 2. 模板文件提交历史 ==="
git log --oneline -n 5 -- "$TMPL"

echo "=== 3. 模板当前 external 状态(带上下文的 while 循环头) ==="
grep -n 'deadline = start' "$TMPL"
grep -n 'completed_hold_sec' "$TMPL"

echo "=== 4. stash 列表(patch 可能被 stash 了) ==="
git stash list
echo "=== DONE ==="
