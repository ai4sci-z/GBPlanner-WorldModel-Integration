#!/usr/bin/env bash
# Stage4b·FCU 消费直证(修正 4a 两盲区):实时订 /ap/v1/cmd_vel 抓 GBP 特征速度,
# enable 提早(bootstrap 一到就解锁),规划触发提早。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage4b_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
JRUN() { docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" bash -lc "$1"; }

{
echo "=== STAGE4B START $(date) ==="
echo "--- 0. 栈复位(GBPlanner+薄桥+适配器 disabled+cmd_vel 探针) ---"
docker rm -f thin_ros2 s4_adapter s4_cmdvel >/dev/null 2>&1 || true
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
docker run -d --network host --name s4_cmdvel \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/sub_cmdvel_probe.py; sleep 300"
sleep 5

echo "--- 1. world-model 真栈起 ---"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/s4b_run.log 2>&1 &
RUN_PID=$!
sleep 30

echo "--- 2. ENABLE(提早) + 立即触发规划 ---"
JRUN "timeout 5 ros2 topic pub /gbp/enable std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1; echo enabled"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 35

echo "--- 3. 适配器运动日志 ---"
docker logs s4_adapter 2>&1 | grep -E "INTENT" | tail -5

echo "--- 4. [核心验收] cmd_vel 探针:GBP 特征速度出现了吗 ---"
docker logs s4_cmdvel 2>&1 | grep -E "GBP-SIGNATURE" | head -6
docker logs s4_cmdvel 2>&1 | tail -4

echo "--- 5. 等 run 结束 ---"
wait $RUN_PID
tail -2 /home/ai4s/s4b_run.log
docker rm -f s4_cmdvel >/dev/null 2>&1 || true
echo "=== STAGE4B END $(date) ==="
} 2>&1 | tee "$OUT"
