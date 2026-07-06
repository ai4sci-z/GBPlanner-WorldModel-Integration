#!/usr/bin/env bash
# Stage4a·低速 FCU 消费验证(混流容忍版):
#   GBPlanner 栈+薄桥+stage4 适配器(默认 disabled)→ world-model 真栈 →
#   bootstrap 后 enable → 触发规划 → 验收:①适配器 INTENT 日志 ②rosbag 里
#   /navlab/fcu/setpoint/output 出现 goal_id=gbp_*(fcu_controller 真消费)③kill 生效。
# 注:frontier_lite workflow 同时在发 intent(混流)——4a 只验消费链路,
#     干净行为(独占 intent)属 Stage5 策略替换。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage4a_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
JRUN() { docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" bash -lc "$1"; }

{
echo "=== STAGE4A START $(date) ==="
echo "--- 0. fresh GBPlanner 栈 + 薄桥 + stage4 适配器(disabled) ---"
docker rm -f thin_ros2 s4_adapter s35_sub >/dev/null 2>&1 || true
docker cp "$DIRB/thinbridge_ros1_side.py" gbplanner_ref:/tmp/thinbridge_ros1_side.py
docker restart gbplanner_ref >/dev/null
sleep 25
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 3
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
docker run -d --network host --name s4_adapter \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/trajectory_to_intent_stage4.py"
sleep 5

echo "--- 1. world-model 真栈起 ---"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/s4_run.log 2>&1 &
RUN_PID=$!
sleep 40

echo "--- 2. ENABLE 运动(显式解锁 fail-closed) ---"
JRUN "timeout 6 ros2 topic pub /gbp/enable std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1; echo enabled"

echo "--- 3. 触发 GBPlanner 规划 ---"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 25

echo "--- 4. 中场:适配器 INTENT 日志(应见限速后速度/wp) ---"
docker logs s4_adapter 2>&1 | grep -E "INTENT|TRAJ#|ENABLED" | tail -8

echo "--- 5. KILL 测试(fail-closed 收尾) ---"
JRUN "timeout 4 ros2 topic pub /gbp/kill std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1; echo killed"
sleep 3
docker logs s4_adapter 2>&1 | grep -E "KILLED" | tail -2

echo "--- 6. 等 run 结束 ---"
wait $RUN_PID
tail -3 /home/ai4s/s4_run.log

echo "--- 7. [核心验收] rosbag:output/intent 里的 gbp_* 消费证据 ---"
RUN=$(ls -t "$CLEAN/artifacts/sim/exploration" | head -1)
python3 "$DIRB/check_output_gbp.py" "$CLEAN/artifacts/sim/exploration/$RUN"
echo "run_id=$RUN"
echo "=== STAGE4A END $(date) ==="
} 2>&1 | tee "$OUT"
