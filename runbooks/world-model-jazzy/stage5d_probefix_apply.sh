#!/usr/bin/env bash
# C类修复:exploration_probe 观测预算 35s→90s(覆盖 readiness+window;B16 同族校准)
set -e
CLEAN=/home/ai4s/ws-clean/world-model
SPEC=$CLEAN/orchestration/sim/internal/tasks/helpers/runtime_specs.go
cd "$CLEAN"
echo "=== 修改前(L1127 上下文) ==="
sed -n '1120,1130p' "$SPEC"
python3 - <<'PY'
import io
f = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/runtime_specs.go"
src = io.open(f, encoding="utf-8").read()
old = "ProbeTimeoutSec:        35.0,"
new = ("ProbeTimeoutSec:        90.0, // was 35: probe launches with services and must still be\n"
       "\t\t// observing when exploration completes (readiness ~45s + 26s window); 35s closed\n"
       "\t\t// before slower-converging runs could report ok=true (same calibration family as\n"
       "\t\t// the frame-contract 45s budget).")
assert src.count(old) == 1, src.count(old)
io.open(f, "w", encoding="utf-8", newline="\n").write(src.replace(old, new, 1))
print("PATCHED ProbeTimeoutSec 35->90")
PY
echo "=== 测试断言同步检查(35 引用) ==="
grep -rn "ProbeTimeoutSec.*35\|35.*ProbeTimeoutSec\|\"ProbeTimeoutSec\":35" orchestration/sim/internal/tasks/ --include='*.go' | grep -v "90.0" | head -5 || echo "(无 35 断言残留)"
export PATH=/usr/local/go/bin:$PATH
cd orchestration/sim
go build ./... && go test ./internal/tasks/... 2>&1 | tail -3
git -C "$CLEAN" status --short | head -3
