#!/usr/bin/env python3
# Stage5a·给 exploration workflow 加 "external" 策略(clean 分支,PR 功能素材):
# strategy=external 时内建 workflow 完全让位(不发 intent/status/review topics),
# 由外部规划器(桥接的 GBPlanner)驱动 /navlab/fcu/setpoint/intent 并拥有
# /navlab/exploration/status。幂等。
import io

f = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl"
src = io.open(f, encoding="utf-8").read()

MARK = 'strategy, "")) == "external"'
if MARK in src:
    print("ALREADY")
    raise SystemExit(0)

OLD = """    start = time.monotonic()
    deadline = start + duration_sec + 15.0
    completed_hold_sec = 5.0

    while rclpy.ok() and time.monotonic() < deadline:"""
NEW = """    start = time.monotonic()
    deadline = start + duration_sec + 15.0
    completed_hold_sec = 5.0

    if str(SPEC.get("strategy", "")) == "external":
        # External exploration strategy: an out-of-process planner (e.g. a
        # bridged GBPlanner) drives /navlab/fcu/setpoint/intent and owns
        # /navlab/exploration/status. The built-in workflow stays fully
        # passive for the whole window so the two never interleave.
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.02)
            time.sleep(0.2)
        node.destroy_node()
        rclpy.shutdown()
        return 0

    while rclpy.ok() and time.monotonic() < deadline:"""

if OLD not in src:
    print("PATTERN_NOT_FOUND")
    raise SystemExit(2)
io.open(f, "w", encoding="utf-8", newline="\n").write(src.replace(OLD, NEW, 1))
print("PATCHED external strategy")
