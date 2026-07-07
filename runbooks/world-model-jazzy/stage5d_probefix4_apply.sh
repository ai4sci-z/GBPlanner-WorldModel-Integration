#!/usr/bin/env bash
# B类根治:frame_contract 预算 45→90(实测匹配延迟 48.96s 超 45s 预算)+ 容器上限 150
set -e
CLEAN=/home/ai4s/ws-clean/world-model
cd "$CLEAN"
python3 - <<'PY'
import io
f1 = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/runtime_specs.go"
src = io.open(f1, encoding="utf-8").read()
old = "ProbeTimeoutSec:         45.0,"
new = ("ProbeTimeoutSec:         90.0, // was 45: micro-ROS agent endpoint matching for a\n"
       "\t\t// late-joining subscription was measured at ~29s in isolation and at 48.96s\n"
       "\t\t// under a fuller participant load, so 45s intermittently starved the wait.")
assert src.count(old) == 1, src.count(old)
io.open(f1, "w", encoding="utf-8", newline="\n").write(src.replace(old, new, 1))
print("PATCHED frame_contract ProbeTimeoutSec 45->90")

f2 = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/runtime_specs.go"
src = io.open(f2, encoding="utf-8").read()
old = '''	if name == "exploration_probe" {'''
new = '''	if name == "frame_contract_probe" {
		// Ceiling for the 90s per-topic budget plus the string batch and the
		// remaining message topics (only the micro-ROS topics are slow).
		return 150
	}
	if name == "exploration_probe" {'''
assert src.count(old) == 1, src.count(old)
io.open(f2, "w", encoding="utf-8", newline="\n").write(src.replace(old, new, 1))
print("PATCHED frame_contract container ceiling -> 150")
PY
export PATH=/usr/local/go/bin:$PATH
cd orchestration/sim
go build ./... && go test ./internal/tasks/... 2>&1 | tail -3
