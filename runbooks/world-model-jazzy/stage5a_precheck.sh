#!/usr/bin/env bash
# Stage5a 前置核验:wp_done 可信度 + gate 判据源码
CLEAN=/home/ai4s/ws-clean/world-model

echo "=== 1. 4c 适配器全日志:TRAJ 接收与 wp 推进(看 wp0-3 是运动到达还是平凡到达) ==="
docker logs s4_adapter 2>&1 | grep -E "TRAJ#|INTENT" | head -30
echo "..."
echo "== INTENT 总数与 wp 索引分布 =="
docker logs s4_adapter 2>&1 | grep -oE "wp\[[0-9]+/" | sort | uniq -c

echo "=== 2. exploration gate 判据源码 ==="
grep -rn "exploration" "$CLEAN/orchestration/sim/internal" --include=gate_evaluation.go | head -20
GATEFILE=$(grep -rl "accepted_goals" "$CLEAN/orchestration/sim/internal" --include='*.go' | head -3)
echo "GATEFILES=$GATEFILE"
for f in $GATEFILE; do
  echo "---- $f (accepted_goals/path_length/ok/strategy 上下文) ----"
  grep -n -B2 -A6 "accepted_goals\|path_length_m\|min_accepted" "$f" | head -80
done

echo "=== 3. exploration_probe 返回码 20 的语义 ==="
grep -rn "code 20\|returnCode\|exit(20\|os.Exit(20\|sys.exit(20" "$CLEAN/orchestration/sim/internal" --include='*.go' --include='*.py' --include='*.tmpl' | head -10
grep -rln "exploration_probe" "$CLEAN/orchestration/sim/internal/tasks/helpers/templates" | head -5
echo "=== PRECHECK DONE ==="
