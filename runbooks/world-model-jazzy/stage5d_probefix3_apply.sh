#!/usr/bin/env bash
# C类修复③(B16 补洞):探针类型发现循环也给全预算——
# /ap/v1/pose/filtered 失败实测 latency=2.2s(TOPIC_SAMPLE=2s 类型门),45s 消息预算被挡在门外。
set -e
CLEAN=/home/ai4s/ws-clean/world-model
F=$CLEAN/orchestration/sim/internal/tasks/helpers/templates/python/ros_probe.py.tmpl
cd "$CLEAN"
python3 - <<'PY'
import io
f = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/templates/python/ros_probe.py.tmpl"
src = io.open(f, encoding="utf-8").read()
old = "        type_deadline = time.monotonic() + TOPIC_SAMPLE_TIMEOUT_SEC"
new = ("        # Type discovery for late-joining participants is subject to the same slow\n"
       "        # DDS propagation as endpoint matching (micro-ROS agent topics measured at\n"
       "        # ~29s), so it must use the full probe budget: a 2s gate here starved the\n"
       "        # 45s message-wait budget below and made /ap/v1/pose/filtered sampling flaky.\n"
       "        type_deadline = time.monotonic() + PROBE_TIMEOUT_SEC")
assert src.count(old) == 1, src.count(old)
io.open(f, "w", encoding="utf-8", newline="\n").write(src.replace(old, new, 1))
print("PATCHED type_deadline -> PROBE_TIMEOUT_SEC")
PY
export PATH=/usr/local/go/bin:$PATH
cd orchestration/sim
go build ./... && go test ./internal/tasks/... 2>&1 | tail -3
git -C "$CLEAN" status --short | head -4
