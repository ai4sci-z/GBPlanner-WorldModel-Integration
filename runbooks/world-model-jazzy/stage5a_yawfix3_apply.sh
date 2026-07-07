#!/usr/bin/env bash
# Stage5a 修复 v3:显式 --no-align-yaw-to-fcu(argparse 默认 True,删 flag 无效)
set -e
CLEAN=/home/ai4s/ws-clean/world-model
SPEC=$CLEAN/orchestration/sim/internal/tasks/runtime_specs.go
SPECTEST=$CLEAN/orchestration/sim/internal/tasks/runtime_specs_test.go

echo "=== 修改前(--use-fcu-roll-pitch 行上下文) ==="
grep -n -- "--use-fcu-roll-pitch" "$SPEC"
# 在 --use-fcu-roll-pitch 后插入 --no-align-yaw-to-fcu(sim 外部导航 sender 参数)
sed -i 's/"--use-fcu-roll-pitch",/"--use-fcu-roll-pitch",\n\t\t"--no-align-yaw-to-fcu",/' "$SPEC"
sed -i 's/"--use-fcu-roll-pitch",/"--use-fcu-roll-pitch",\n\t\t"--no-align-yaw-to-fcu",/' "$SPECTEST"
echo "=== 修改后 ==="
grep -n -A1 -- "--use-fcu-roll-pitch" "$SPEC" | head -6
export PATH=/usr/local/go/bin:$PATH
cd "$CLEAN/orchestration/sim"
go build ./... && go test ./internal/tasks/... 2>&1 | tail -3
