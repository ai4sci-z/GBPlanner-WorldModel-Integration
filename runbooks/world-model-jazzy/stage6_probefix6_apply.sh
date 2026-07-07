#!/usr/bin/env bash
# 跑通攻坚·探针修复⑥:frame_contract 的 FCU 位姿采样改到实际被消费的链路
# /ap/v1/pose/filtered(micro-ROS DDS 调试路,无消费者,匹配长尾>90s 不定)
#   → /navlab/fcu/local_position_pose(MAVLink 回发,rclpy 常规发布,系统真实消费同源)
set -e
CLEAN=/home/ai4s/ws-clean/world-model
cd "$CLEAN"
echo "=== 出处确认 ==="
grep -rn '"/ap/v1/pose/filtered"' orchestration/sim/internal/tasks/helpers/runtime_specs.go | head -3
python3 - <<'PY'
import io
f = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/runtime_specs.go"
src = io.open(f, encoding="utf-8").read()
old = 'FCUPoseTopic:            "/ap/v1/pose/filtered",'
new = ('FCUPoseTopic:            "/navlab/fcu/local_position_pose", // was /ap/v1/pose/filtered:\n'
       "\t\t// the DDS debug stream has no consumer in the pipeline and its late-join\n"
       "\t\t// endpoint matching to the micro-ROS agent has an unbounded tail (measured\n"
       "\t\t// 29s..97s+). The contract being probed is 'FCU pose is available', and the\n"
       "\t\t// pipeline actually consumes pose via the MAVLink-republished topic, so\n"
       "\t\t// sample the consumed route.")
assert src.count(old) >= 1, src.count(old)
io.open(f, "w", encoding="utf-8", newline="\n").write(src.replace(old, new, 1))
print("PATCHED FCUPoseTopic -> /navlab/fcu/local_position_pose")
PY
echo "=== 测试断言同步(旧 topic 引用) ==="
grep -rn "/ap/v1/pose/filtered" orchestration/sim/internal/tasks/ --include='*_test.go' | head -5 || echo "(无测试断言引用)"
export PATH=/usr/local/go/bin:$PATH
cd orchestration/sim
go build ./... && go test -count=1 ./internal/tasks/... 2>&1 | tail -3
