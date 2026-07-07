#!/usr/bin/env bash
# C类修复②:exploration_probe 容器级超时 90→150(脚本级预算 90 + 启动开销须容纳)
set -e
CLEAN=/home/ai4s/ws-clean/world-model
F=$CLEAN/orchestration/sim/internal/tasks/runtime_specs.go
cd "$CLEAN"
python3 - <<'PY'
import io
f = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/runtime_specs.go"
src = io.open(f, encoding="utf-8").read()
old = '''	if name == "exploration_probe" {
		return 90
	}'''
new = '''	if name == "exploration_probe" {
		// Container ceiling for the 90s in-script status budget plus interpreter
		// startup; must strictly exceed the script budget or the container is
		// killed as "context deadline exceeded" before the script can report.
		return 150
	}'''
assert src.count(old) == 1, src.count(old)
io.open(f, "w", encoding="utf-8", newline="\n").write(src.replace(old, new, 1))
print("PATCHED exploration_probe container timeout 90->150")
PY
export PATH=/usr/local/go/bin:$PATH
cd orchestration/sim
go build ./... && go test ./internal/tasks/... 2>&1 | tail -3
