#!/usr/bin/env bash
# C类查证②:rclpy 采样逻辑全文 + runner 何时启动探针
CLEAN=/home/ai4s/ws-clean/world-model
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
P=$(find "$RUNDIR" -name "exploration_probe.py" | head -1)
echo "=== sample_message_topic(rclpy 路径)全文 ==="
sed -n '/def sample_message_topic/,/^def /p' "$P" | head -60
echo "=== runner 侧:探针执行时机(相对 workflow) ==="
grep -rn "RunROSProbes\|runROSProbes\|ROSProbes\b" "$CLEAN/orchestration/sim/internal/tasks/" --include='*.go' | grep -v _test | head -8
echo "=== 执行顺序上下文 ==="
F=$(grep -rln "docker sdk probe" "$CLEAN/orchestration/sim/internal/tasks/" --include='*.go' | head -1)
echo "FILE=$F"
grep -n -B3 -A6 "docker sdk probe" "$F" | head -30
